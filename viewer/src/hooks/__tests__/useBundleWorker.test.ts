/// <reference types="node" />
/**
 * Large uploads decode in a worker (lib/bundleDecode). jsdom has no Worker,
 * so these tests drive the worker's own handler (`answerDecodeRequest`)
 * through a stand-in worker that answers asynchronously with a structured
 * clone, as a real one does; the browser path is exercised by
 * scripts/perf-viewer.mjs and scripts/viewer-equivalence.mjs.
 */
import { createHash, webcrypto } from "node:crypto";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "../../__fixtures__/transport_bundle.json";
import citiesFixture from "../../__fixtures__/cities_bundle.json";
import {
  answerDecodeRequest, assembleParts, bundleParts, decodeInWorker, HISTORY_SLICE, setDecodeWorkerFactory,
  WORKER_MIN_BYTES, type DecodePart, type DecodeReply, type DecodeRequest,
} from "../../lib/bundleDecode";
import { parseBundle } from "../../lib/bundleFile";
import { useBundle } from "../useBundle";

type Mode = "answer" | "crash" | "silent";

class StandInWorker {
  static created: StandInWorker[] = [];
  onmessage: ((event: MessageEvent<DecodeReply>) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  onmessageerror: (() => void) | null = null;
  terminated = false;
  requests = 0;
  readonly mode: Mode;

  constructor(mode: Mode) {
    this.mode = mode;
    StandInWorker.created.push(this);
  }

  postMessage(request: DecodeRequest) {
    this.requests += 1;
    if (this.mode === "crash") {
      setTimeout(() => this.onerror?.({ message: "worker script failed", preventDefault() {} } as unknown as ErrorEvent));
      return;
    }
    if (this.mode === "silent") {
      return;
    }
    // Each message arrives in its own task, as a structured clone (parts first, then the reply).
    const send = (message: DecodePart | DecodeReply) => {
      const copy = structuredClone(message);
      setTimeout(() => {
        if (!this.terminated) {
          this.onmessage?.({ data: copy } as MessageEvent<DecodeReply>);
        }
      });
    };
    void answerDecodeRequest(request, send).then(send);
  }

  terminate() {
    this.terminated = true;
  }
}

function useStandIn(mode: Mode) {
  setDecodeWorkerFactory(() => new StandInWorker(mode) as unknown as Worker);
}

/** A file over the worker threshold: the fixture plus trailing whitespace (still the same JSON). */
function largeText(bundle: unknown = fixture): string {
  return JSON.stringify(bundle) + " ".repeat(WORKER_MIN_BYTES);
}

function malformed(patch: unknown): string {
  const bundle = structuredClone(fixture) as unknown as Record<string, unknown>;
  (bundle.history_delta as unknown[])[3] = patch;
  return largeText(bundle);
}

beforeEach(() => {
  StandInWorker.created = [];
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  cleanup();
  setDecodeWorkerFactory(undefined);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the worker's handler", () => {
  it("decodes as the main thread does, with the identity of the original bytes", async () => {
    const raw = largeText();
    const reply = await answerDecodeRequest({ file: new File([raw], "large.json") });
    expect(reply.kind).toBe("decoded");
    if (reply.kind !== "decoded") return;
    expect(reply.result.bundle).toEqual(parseBundle(raw).bundle);
    expect(reply.result.error).toBeNull();
    expect(reply.result.identity).toEqual({ name: "large.json", byteLength: Buffer.byteLength(raw),
      sha256: createHash("sha256").update(raw).digest("hex") });
  });

  it.each([
    ["a list patch that is not iterable", { active_wars: { "~l": 3 } }],
    ["an index past the list", { active_wars: { "~l": [[99, ["A", "B"]]] } }],
    ["a key order naming a missing key", { "~o": ["turn", "nope"] }],
  ])("returns the main thread's readable error for %s", async (_name, patch) => {
    const raw = malformed(patch);
    const reply = await answerDecodeRequest({ file: new File([raw], "bad.json") });
    expect(reply.kind).toBe("decoded");
    expect(reply.kind === "decoded" && reply.result).toEqual({ bundle: null, error: parseBundle(raw).error, identity: null });
    expect(parseBundle(raw).error).toMatch(/^Invalid bundle history: history_delta\[3\]: /);
  });

  it("reports an unreadable file and an unexpected failure", async () => {
    const unreadable = { name: "gone.json", arrayBuffer: () => Promise.reject(new Error("NotReadableError")) };
    expect(await answerDecodeRequest({ file: unreadable as unknown as Blob })).toEqual({ kind: "read-error" });
    const notBytes = { name: "odd.json", arrayBuffer: () => Promise.resolve("not bytes") };
    const reply = await answerDecodeRequest({ file: notBytes as unknown as Blob });
    expect(reply.kind).toBe("error");
  });
});

describe("the bundle in parts", () => {
  it("reassembles to the same bundle, in the same key order, from history and event slices", () => {
    const bundle = parseBundle(JSON.stringify(citiesFixture)).bundle!;
    expect(bundle.history.length).toBeGreaterThan(HISTORY_SLICE * 2);
    const parts = bundleParts(bundle);
    expect(parts.filter((part) => part.key === "history" && part.append)).toHaveLength(
      Math.ceil(bundle.history.length / HISTORY_SLICE));
    const copies = parts.map((part) => structuredClone(part));
    const assembled = assembleParts(copies);
    expect(Object.keys(assembled)).toEqual(Object.keys(bundle));
    expect(JSON.stringify(assembled)).toBe(JSON.stringify(bundle));
  });

  it("keeps the world state's timeline and named events the bundle's own lists, as decoding does", () => {
    const bundle = parseBundle(JSON.stringify(fixture)).bundle!;
    expect(bundle.world_state.events_timeline).toBe(bundle.events_timeline);
    const assembled = assembleParts(bundleParts(bundle).map((part) => structuredClone(part)));
    expect(assembled.world_state.events_timeline).toBe(assembled.events_timeline);
    expect(assembled.world_state.named_events).toBe(assembled.named_events);
    expect(Object.keys(assembled.world_state)).toEqual(Object.keys(bundle.world_state));
    expect(JSON.stringify(assembled)).toBe(JSON.stringify(bundle));
  });

  it("posts the parts before a reply that counts them, and none for a rejected file", async () => {
    const posted: DecodePart[] = [];
    const reply = await answerDecodeRequest({ file: new File([largeText()], "large.json") }, (part) => posted.push(part));
    expect(reply.kind === "decoded" && reply.parts).toBe(posted.length);
    expect(reply.kind === "decoded" && reply.result.bundle).toBeNull();
    expect(assembleParts(posted)).toEqual(parseBundle(largeText()).bundle);
    const rejected: DecodePart[] = [];
    const bad = await answerDecodeRequest({ file: new File([malformed({ "~r": 1, x: 2 })], "bad.json") },
      (part) => rejected.push(part));
    expect(rejected).toHaveLength(0);
    expect(bad.kind === "decoded" && bad.result.error).toMatch(/history_delta\[3\]: '~r' patch with other keys/);
  });
});

describe("decodeInWorker", () => {
  it("leaves small files and missing workers to the main thread", () => {
    useStandIn("answer");
    expect(decodeInWorker(new File([JSON.stringify(fixture)], "small.json"))).toBeNull();
    setDecodeWorkerFactory(null);
    expect(decodeInWorker(new File([largeText()], "large.json"))).toBeNull();
    setDecodeWorkerFactory(() => {
      throw new Error("SecurityError");
    });
    expect(decodeInWorker(new File([largeText()], "large.json"))).toBeNull();
    // Without a stand-in, jsdom has no Worker at all.
    setDecodeWorkerFactory(undefined);
    expect(decodeInWorker(new File([largeText()], "large.json"))).toBeNull();
  });
});

describe("useBundle with a worker", () => {
  it("loads a large file through the worker and ends loading", async () => {
    useStandIn("answer");
    const raw = largeText();
    const { result } = renderHook(() => useBundle());
    act(() => result.current.loadFromFile(new File([raw], "large.json")));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(StandInWorker.created).toHaveLength(1);
    expect(StandInWorker.created[0].requests).toBe(1);
    expect(StandInWorker.created[0].terminated).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.bundle).toEqual(parseBundle(raw).bundle);
    expect(result.current.bundle?.history).toHaveLength(10);
    expect(result.current.artifactIdentity?.sha256).toBe(createHash("sha256").update(raw).digest("hex"));
  });

  it("shows the strict decode error from the worker", async () => {
    useStandIn("answer");
    const { result } = renderHook(() => useBundle());
    act(() => result.current.loadFromFile(new File([malformed({ "~o": ["turn", "nope"] })], "bad-delta.json")));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.bundle).toBeNull();
    expect(result.current.artifactIdentity).toBeNull();
    expect(result.current.error).toMatch(/^Invalid bundle history: history_delta\[3\]: '~o' must list/);
  });

  it("decodes on the main thread when the worker fails", async () => {
    useStandIn("crash");
    const raw = largeText();
    const { result } = renderHook(() => useBundle());
    act(() => result.current.loadFromFile(new File([raw], "large.json")));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(StandInWorker.created[0].terminated).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.bundle).toEqual(parseBundle(raw).bundle);
  });

  it("stops a superseded worker and keeps the newer bundle", async () => {
    setDecodeWorkerFactory(() => new StandInWorker(StandInWorker.created.length === 0 ? "silent" : "answer") as unknown as Worker);
    const second = structuredClone(fixture) as unknown as { metadata: { seed: number } };
    second.metadata.seed = 4242;
    const { result } = renderHook(() => useBundle());
    act(() => result.current.loadFromFile(new File([largeText()], "first.json")));
    act(() => result.current.loadFromFile(new File([largeText(second)], "second.json")));
    expect(StandInWorker.created[0].terminated).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.bundle?.metadata.seed).toBe(4242);
    expect(result.current.artifactIdentity?.name).toBe("second.json");
  });

  it("stops the worker when the viewer unmounts", () => {
    useStandIn("silent");
    const { result, unmount } = renderHook(() => useBundle());
    act(() => result.current.loadFromFile(new File([largeText()], "large.json")));
    unmount();
    expect(StandInWorker.created[0].terminated).toBe(true);
  });
});
