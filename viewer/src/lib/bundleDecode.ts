/**
 * Decoding a large uploaded bundle off the main thread.
 *
 * Parsing a bundle file and expanding its version-6 history take hundreds
 * of milliseconds for a large run, which froze the page while it loaded.
 * A file of `WORKER_MIN_BYTES` or more is handed to a dedicated worker
 * (`bundleDecode.worker.ts`) as the `File` itself (a cheap handle; the
 * worker reads the bytes): the worker reads, parses, checks and decodes it
 * (`bundleFile.decodeBundleBytes`, the same code as the main thread) and
 * hashes the original bytes. One worker per load, terminated once it
 * answers or when a newer load supersedes it.
 *
 * The decoded bundle comes back in parts (`DecodePart`): each top-level
 * field in order, with the history and the event timeline in slices. Each
 * message is received (structured-clone deserialized) in its own task, so
 * the main thread is never blocked for the whole bundle at once and the
 * worker serializes one part while the main thread receives the previous
 * one. Values the version-6 decoder shares between consecutive snapshots
 * stay shared within a slice; the first snapshot of a slice is a copy.
 * Nothing renders until the last part is in, so the shell sees the same
 * complete bundle as before.
 *
 * Where a worker cannot run (no `Worker`, as in jsdom; a worker that fails
 * to start or crashes; a reply that cannot be received), the caller decodes
 * on the main thread as before. Malformed bundles give the same readable
 * messages either way: the loader's diagnostics (`INVALID_HISTORY_DELTA`
 * for a `BundleDecodeError`), "Failed to read file" for an unreadable
 * file, "Could not read bundle: ..." for anything else.
 */
import type { Bundle } from "../types";
import { identifyArtifact } from "./artifactIdentity";
import { decodeBundleBytes, decodeBundleText, parseBundle, type DecodedBundleFile } from "./bundleFile";

/** Files at least this large are decoded in a worker (smaller ones decode faster than a worker starts). */
export const WORKER_MIN_BYTES = 1024 * 1024;
/** Snapshots per history part. */
export const HISTORY_SLICE = 25;
/** Events per event-timeline part. */
export const EVENT_SLICE = 2000;

export interface DecodeRequest {
  file: Blob & { name?: string };
}

/** When the worker started (epoch ms) and how long it spent reading and decoding (for the performance report). */
export interface DecodeTimings {
  startedAt: number;
  read: number;
  decode: number;
}

/**
 * One top-level field of the decoded bundle, or (`append`) a slice of a list
 * field. `shared` names fields of this (object) value that are the bundle's
 * own top-level fields of that name: the version-6 decoder points
 * `world_state.events_timeline` and `named_events` at the top-level lists,
 * and the reassembled bundle does too (one copy, as on the main thread).
 */
export interface DecodePart {
  kind: "part";
  key: string;
  value: unknown;
  append?: boolean;
  shared?: string[];
}

export type DecodeReply =
  | { kind: "decoded"; result: DecodedBundleFile; timings?: DecodeTimings; parts?: number }
  | { kind: "read-error" }
  | { kind: "error"; message: string };

const SLICED: Record<string, number> = { history: HISTORY_SLICE, events_timeline: EVENT_SLICE };

/** The parts of a bundle, in its key order. */
export function bundleParts(bundle: Bundle): DecodePart[] {
  const top = bundle as unknown as Record<string, unknown>;
  const parts: DecodePart[] = [];
  for (const [key, value] of Object.entries(top)) {
    const size = SLICED[key];
    if (size && Array.isArray(value)) {
      parts.push({ kind: "part", key, value: [] });
      for (let start = 0; start < value.length; start += size) {
        parts.push({ kind: "part", key, value: value.slice(start, start + size), append: true });
      }
      continue;
    }
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      const fields = value as Record<string, unknown>;
      const shared = Object.keys(fields).filter((field) => field !== key && fields[field] !== null
        && typeof fields[field] === "object" && fields[field] === top[field]);
      if (shared.length > 0) {
        // Placeholders keep the field order; the receiver points them at the top-level fields.
        const stripped = { ...fields };
        for (const field of shared) {
          stripped[field] = null;
        }
        parts.push({ kind: "part", key, value: stripped, shared });
        continue;
      }
    }
    parts.push({ kind: "part", key, value });
  }
  return parts;
}

/** Put the parts back together, in their order. */
export function assembleParts(parts: DecodePart[]): Bundle {
  const bundle: Record<string, unknown> = {};
  for (const part of parts) {
    if (part.append) {
      (bundle[part.key] as unknown[]).push(...(part.value as unknown[]));
    } else {
      bundle[part.key] = part.value;
    }
  }
  for (const part of parts) {
    for (const field of part.shared ?? []) {
      (part.value as Record<string, unknown>)[field] = bundle[field];
    }
  }
  return bundle as unknown as Bundle;
}

/**
 * What the worker does with one request (also callable directly, as the
 * tests do). With `post`, a decoded bundle is sent in parts first and the
 * reply carries their count instead of the bundle.
 */
export async function answerDecodeRequest(
  request: DecodeRequest,
  post?: (part: DecodePart) => void,
): Promise<DecodeReply> {
  const started = performance.now();
  const startedAt = performance.timeOrigin + started;
  let bytes: ArrayBuffer;
  try {
    bytes = await request.file.arrayBuffer();
  } catch {
    return { kind: "read-error" };
  }
  const read = performance.now();
  try {
    if (!post) {
      const result = await decodeBundleBytes(request.file.name ?? "", bytes);
      return { kind: "decoded", result, timings: { startedAt, read: read - started, decode: performance.now() - read } };
    }
    // The hash runs alongside the parse; it is kept only for a bundle (as decodeBundleBytes does).
    const hashing = identifyArtifact(request.file.name ?? "", bytes);
    const parsed = parseBundle(decodeBundleText(bytes));
    const identity = parsed.bundle ? await hashing : null;
    const timings = { startedAt, read: read - started, decode: performance.now() - read };
    if (!parsed.bundle) {
      return { kind: "decoded", result: { bundle: null, error: parsed.error, identity }, timings };
    }
    const parts = bundleParts(parsed.bundle);
    for (const part of parts) {
      post(part);
    }
    return { kind: "decoded", result: { bundle: null, error: parsed.error, identity }, timings, parts: parts.length };
  } catch (error) {
    return { kind: "error", message: error instanceof Error ? error.message : String(error) };
  }
}

/**
 * A user-timing mark with the worker's phases and the main thread's receive
 * times (`chronicler:bundle-decoded`; scripts/perf-viewer.mjs reports it).
 */
function markDecoded(detail: DecodeTimings & { receive: number; longestReceive: number; parts: number }) {
  try {
    performance.mark("chronicler:bundle-decoded", { detail });
  } catch {
    // User timing is optional.
  }
}

export interface DecodeJob {
  /** The worker's reply; rejects when the worker could not do the job (decode on the main thread instead). */
  reply: Promise<DecodeReply>;
  /** Stop the worker (a newer load superseded this one). */
  cancel: () => void;
}

/** The worker constructor, or null where workers are unavailable. Tests replace it. */
export type WorkerFactory = (() => Worker) | null;

function defaultWorkerFactory(): WorkerFactory {
  if (typeof Worker === "undefined") {
    return null;
  }
  return () => new Worker(new URL("./bundleDecode.worker.ts", import.meta.url), { type: "module" });
}

let workerFactory: WorkerFactory | undefined;

/** Replace the worker constructor (tests); `undefined` restores the default. */
export function setDecodeWorkerFactory(factory: WorkerFactory | undefined): void {
  workerFactory = factory;
}

/**
 * Decode `file` in a worker, or null when it should be decoded on the main
 * thread (a small file, or no worker available).
 */
export function decodeInWorker(file: File): DecodeJob | null {
  const factory = workerFactory === undefined ? defaultWorkerFactory() : workerFactory;
  if (!factory || file.size < WORKER_MIN_BYTES) {
    return null;
  }
  let worker: Worker;
  try {
    worker = factory();
  } catch {
    return null;
  }
  let settled = false;
  const parts: DecodePart[] = [];
  let receive = 0;
  let longestReceive = 0;
  const reply = new Promise<DecodeReply>((resolve, reject) => {
    const finish = (outcome: () => void) => {
      if (settled) {
        return;
      }
      settled = true;
      worker.terminate();
      outcome();
    };
    worker.onmessage = (event: MessageEvent<DecodePart | DecodeReply>) => {
      if (settled) {
        return;
      }
      // Reading `data` deserializes the message on this thread.
      const start = performance.now();
      const data = event.data;
      const took = performance.now() - start;
      receive += took;
      longestReceive = Math.max(longestReceive, took);
      if (data.kind === "part") {
        parts.push(data);
        return;
      }
      if (data.kind === "decoded" && data.parts !== undefined) {
        if (parts.length !== data.parts) {
          finish(() => reject(new Error(`Received ${parts.length} of ${data.parts} bundle parts`)));
          return;
        }
        const bundle = assembleParts(parts);
        if (data.timings) {
          markDecoded({ ...data.timings, receive, longestReceive, parts: parts.length });
        }
        finish(() => resolve({ ...data, result: { ...data.result, bundle } }));
        return;
      }
      finish(() => resolve(data));
    };
    worker.onerror = (event: ErrorEvent) => {
      event.preventDefault();
      finish(() => reject(new Error(event.message || "The bundle worker failed")));
    };
    worker.onmessageerror = () => finish(() => reject(new Error("The decoded bundle could not be received")));
    try {
      worker.postMessage({ file } satisfies DecodeRequest);
    } catch (error) {
      finish(() => reject(error));
    }
  });
  return {
    reply,
    cancel: () => {
      if (!settled) {
        settled = true;
        worker.terminate();
      }
    },
  };
}
