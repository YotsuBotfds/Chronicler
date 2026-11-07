/// <reference types="node" />
import { createHash, webcrypto } from "node:crypto";
import { gzipSync } from "node:zlib";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import legacy from "../../__fixtures__/sample_bundle.json";
import transport from "../../__fixtures__/transport_bundle.json";
import { answerDecodeRequest, assembleParts, type DecodePart } from "../bundleDecode";
import { decodeBundleBytes, expandBundleBytes, parseBundleBytes } from "../bundleFile";
import { entityHistory, indexEntityHistory } from "../entityHistory";
import { chainBundle } from "./recoveryChainFixture";

const bytes = (text: string): ArrayBuffer => new TextEncoder().encode(text).buffer;
const archive = (raw: ArrayBuffer): ArrayBuffer => Uint8Array.from(gzipSync(new Uint8Array(raw))).buffer;
const sha = (raw: ArrayBuffer): string => createHash("sha256").update(new Uint8Array(raw)).digest("hex");
const file = (raw: ArrayBuffer, name = "world.json.gz") => ({ name, arrayBuffer: async () => raw }) as Blob & { name: string };

beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => vi.unstubAllGlobals());

describe("optional lossless gzip bundle containers", () => {
  it.each([["legacy", legacy], ["version-6 transport", transport]])("preserves every decoded %s value and key order, hashing the uploaded archive", async (_name, fixture) => {
    const raw = bytes(JSON.stringify(fixture));
    const compressed = archive(raw);
    const plain = await decodeBundleBytes("world.json", raw);
    const zipped = await decodeBundleBytes("world.json.gz", compressed);
    expect(plain.error).toBeNull();
    expect(zipped.error).toBeNull();
    expect(zipped.bundle).toEqual(plain.bundle);
    expect(JSON.stringify(zipped.bundle)).toBe(JSON.stringify(plain.bundle));
    expect(zipped.identity).toEqual({ name: "world.json.gz", byteLength: compressed.byteLength, sha256: sha(compressed) });
    expect(zipped.identity?.sha256).not.toBe(plain.identity?.sha256);
    expect(await expandBundleBytes(compressed)).toEqual(raw);
  });

  it("preserves complete linked observations, queries, pointers and missing states", async () => {
    // Constructed codec fixture: embed the natural chain's unchanged saved
    // records in a complete display shell. This is not a simulated alternate.
    const chain = chainBundle();
    const rich = { ...legacy, history: chain.history.map(row => ({ ...legacy.history[0], ...row })),
      metadata: { ...legacy.metadata, total_turns: 29 }, world_state: { ...legacy.world_state, turn: 29 } };
    const raw = bytes(JSON.stringify(rich));
    const plain = await decodeBundleBytes("constructed.json", raw);
    const zipped = await decodeBundleBytes("constructed.json.gz", archive(raw));
    expect(plain.error).toBeNull();
    expect(zipped.error).toBeNull();
    const left = indexEntityHistory(plain.bundle!);
    const right = indexEntityHistory(zipped.bundle!);
    expect(left.entities.length).toBeGreaterThan(10);
    expect(JSON.stringify(right)).toBe(JSON.stringify(left));
    for (const entity of left.entities) {
      for (const turn of [undefined, 22, 28]) {
        expect(entityHistory(right, entity, turn)).toEqual(entityHistory(left, entity, turn));
      }
    }
    expect(entityHistory(right, { kind: "person", id: 13 }).some(row => row.package === "recovery_crews" && row.state === "recorded")).toBe(true);
  });

  it("recognizes magic rather than extensions and retains BOM decoding", async () => {
    const text = JSON.stringify(legacy);
    const utf16 = new Uint8Array(2 + text.length * 2);
    utf16.set([0xff, 0xfe]);
    const view = new DataView(utf16.buffer);
    for (let i = 0; i < text.length; i++) view.setUint16(2 + i * 2, text.charCodeAt(i), true);
    for (const raw of [bytes("\ufeff" + text + "\n "), utf16.buffer]) {
      expect((await decodeBundleBytes("misnamed.json", archive(raw))).bundle).toEqual(parseBundleBytes(raw).bundle);
      expect((await decodeBundleBytes("plain.gz", raw)).error).toBeNull();
      expect(await expandBundleBytes(raw)).toBe(raw);
    }
  });

  it("runs the same worker paths, with no parts emitted until archive verification succeeds", async () => {
    const compressed = archive(bytes(JSON.stringify(transport)));
    const direct = await decodeBundleBytes("world.json.gz", compressed);
    const unchunked = await answerDecodeRequest({ file: file(compressed) });
    expect(unchunked.kind === "decoded" && unchunked.result).toEqual(direct);
    const parts: DecodePart[] = [];
    const chunked = await answerDecodeRequest({ file: file(compressed) }, part => parts.push(structuredClone(part)));
    expect(chunked.kind === "decoded" && chunked.parts).toBe(parts.length);
    expect(chunked.kind === "decoded" && chunked.result.identity).toEqual(direct.identity);
    expect(JSON.stringify(assembleParts(parts))).toBe(JSON.stringify(direct.bundle));
    expect(chunked.kind === "decoded" && chunked.timings?.decode).toBeGreaterThan(0);

    const corrupt = new Uint8Array(compressed.slice(0));
    corrupt[corrupt.length - 8] ^= 1; // CRC: decompressed text alone would look valid.
    const posted: DecodePart[] = [];
    const rejected = await answerDecodeRequest({ file: file(corrupt.buffer) }, part => posted.push(part));
    expect(posted).toHaveLength(0);
    expect(rejected.kind === "decoded" && rejected.result).toMatchObject({ bundle: null, identity: null, error: expect.stringContaining("Could not decompress gzip") });
  });

  it("rejects truncation and corruption while retaining ordinary JSON diagnostics after successful inflation", async () => {
    const good = archive(bytes(JSON.stringify(legacy)));
    const badMethod = new Uint8Array(good.slice(0));
    badMethod[2] = 0xff;
    for (const broken of [good.slice(0, 2), good.slice(0, 12), good.slice(0, -1), badMethod.buffer]) {
      expect(await decodeBundleBytes("broken.gz", broken)).toMatchObject({ bundle: null, identity: null, error: expect.stringContaining("Could not decompress gzip") });
    }
    const invalid = bytes("not JSON");
    expect((await decodeBundleBytes("invalid.gz", archive(invalid))).error).toBe(parseBundleBytes(invalid).error);
    vi.stubGlobal("DecompressionStream", undefined);
    expect(await decodeBundleBytes("valid.gz", good)).toMatchObject({ bundle: null, identity: null, error: expect.stringContaining("This browser cannot open gzip archives") });
    expect((await decodeBundleBytes("plain.json", bytes(JSON.stringify(legacy)))).error).toBeNull();
  });

  it("retains the checkpoint header-only notice through an archive without deserializing sections", async () => {
    const magic = new Uint8Array([0x89, ...new TextEncoder().encode("CHRONICLER-CKPT\r\n"), 0x1a, 0x0a]);
    const header = bytes(JSON.stringify({ format: "chronicler-run-checkpoint", version: 1, world: { name: "Aetheris" },
      seed: 42, turn: 7, sections: [{ name: "python", offset: 0, length: 3 }] }));
    const raw = new Uint8Array(magic.length + 4 + header.byteLength + 3);
    raw.set(magic);
    new DataView(raw.buffer).setUint32(magic.length, header.byteLength, true);
    raw.set(new Uint8Array(header), magic.length + 4);
    raw.set([0x80, 5, 0xff], magic.length + 4 + header.byteLength);
    const plain = await decodeBundleBytes("run.ckpt", raw.buffer);
    const zipped = await decodeBundleBytes("run.ckpt.gz", archive(raw.buffer));
    expect(zipped).toEqual(plain);
    expect(zipped.error).toContain("header only; not a viewable bundle");
    expect(zipped.error).toContain("never deserializes");
  });
});
