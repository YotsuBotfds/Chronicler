/// <reference types="node" />
import { webcrypto, createHash } from "node:crypto";
import { afterEach, expect, it, vi } from "vitest";
import { identifyArtifact } from "../artifactIdentity";

afterEach(() => vi.unstubAllGlobals());

it("hashes raw BOM and whitespace bytes rather than normalized JSON", async () => {
  vi.stubGlobal("crypto", webcrypto);
  const bytes = new TextEncoder().encode('\ufeff{ "seed": 1 }\n');
  const identity = await identifyArtifact("original.json", bytes.buffer);
  expect(identity).toEqual({ name: "original.json", byteLength: bytes.byteLength,
    sha256: createHash("sha256").update(bytes).digest("hex") });
  expect(identity.sha256).not.toBe(createHash("sha256").update('{"seed":1}').digest("hex"));
});

it("keeps file identity metadata when hashing is unavailable", async () => {
  vi.stubGlobal("crypto", {});
  expect(await identifyArtifact("old.json", new ArrayBuffer(4))).toEqual({ name: "old.json", byteLength: 4, sha256: null });
});
