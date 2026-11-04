/// <reference types="node" />
import { createHash, webcrypto } from "node:crypto";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import fixture from "../../__fixtures__/region_inspection_bundle.json";
import * as identity from "../../lib/artifactIdentity";
import * as bundleFile from "../../lib/bundleFile";
import { useBundle } from "../useBundle";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("reads original bytes, accepts a UTF-8 BOM and retains matching raw identity", async () => {
  vi.stubGlobal("crypto", webcrypto);
  const raw = '\ufeff' + JSON.stringify(fixture, null, 2) + '\n';
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File([raw], "raw-fixture.json")));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBeNull();
  expect(result.current.bundle?.metadata.seed).toBe(1701);
  expect(result.current.artifactIdentity).toEqual({ name: "raw-fixture.json",
    byteLength: new TextEncoder().encode(raw).byteLength,
    sha256: createHash("sha256").update(raw).digest("hex") });
});

it("does not let an older delayed hash replace a newer bundle and identity", async () => {
  let resolveFirst!: (value: identity.ArtifactIdentity) => void;
  const identify = vi.spyOn(identity, "identifyArtifact")
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockResolvedValueOnce({ name: "second.json", byteLength: 456, sha256: "second-hash" });
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File([JSON.stringify(fixture)], "first.json")));
  await waitFor(() => expect(identify).toHaveBeenCalledTimes(1));
  const second = structuredClone(fixture);
  second.metadata.seed = 1702;
  act(() => result.current.loadFromFile(new File([JSON.stringify(second)], "second.json")));
  await waitFor(() => expect(result.current.bundle?.metadata.seed).toBe(1702));
  await act(async () => resolveFirst({ name: "first.json", byteLength: 123, sha256: "first-hash" }));
  expect(result.current.bundle?.metadata.seed).toBe(1702);
  expect(result.current.artifactIdentity?.sha256).toBe("second-hash");
});

it.each([true, false])("preserves BOM-marked UTF-16 input compatibility (littleEndian=%s)", async (littleEndian) => {
  vi.stubGlobal("crypto", webcrypto);
  const text = JSON.stringify(fixture);
  const bytes = new ArrayBuffer(2 + text.length * 2);
  const view = new DataView(bytes);
  view.setUint16(0, 0xfeff, littleEndian);
  for (let index = 0; index < text.length; index++) view.setUint16(2 + index * 2, text.charCodeAt(index), littleEndian);
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File([bytes], "utf16.json")));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.bundle?.metadata.seed).toBe(1701);
  expect(result.current.artifactIdentity?.sha256).toBe(createHash("sha256").update(new Uint8Array(bytes)).digest("hex"));
});

it("clears bundle identity on a rejected JSON file", async () => {
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File(["invalid json"], "bad.json")));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toContain("Invalid JSON");
  expect(result.current.bundle).toBeNull();
  expect(result.current.artifactIdentity).toBeNull();
});

it("retains the loaded world and original identity after failure, then accepts repeated and corrected loads", async () => {
  vi.stubGlobal("crypto", webcrypto);
  const { result } = renderHook(() => useBundle());
  const file = new File([JSON.stringify(fixture)], "world.json");
  act(() => result.current.loadFromFile(file));
  await waitFor(() => expect(result.current.bundle).not.toBeNull());
  const loaded = result.current.bundle;
  const original = result.current.artifactIdentity;
  for (const bad of ["not JSON", JSON.stringify({ ...fixture, metadata: null }), JSON.stringify(fixture.world_state)]) {
    act(() => result.current.loadFromFile(new File([bad], "bad.json")));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).not.toBeNull();
    expect(result.current.bundle).toBe(loaded);
    expect(result.current.artifactIdentity).toBe(original);
  }
  act(() => result.current.loadFromFile(file));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBeNull();
  expect(result.current.artifactIdentity).toEqual(original);
  const corrected = structuredClone(fixture);
  corrected.metadata.seed = 1703;
  act(() => result.current.loadFromFile(new File([JSON.stringify(corrected)], "corrected.json")));
  await waitFor(() => expect(result.current.bundle?.metadata.seed).toBe(1703));
  expect(result.current.artifactIdentity?.name).toBe("corrected.json");
});

it("ignores an older reader failure while a newer successful world is loaded", async () => {
  const readers: FileReader[] = [];
  const NativeReader = FileReader;
  vi.stubGlobal("FileReader", class extends NativeReader {
    constructor() { super(); readers.push(this); }
    readAsArrayBuffer() { /* Tests deliver read results explicitly. */ }
  });
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File(["bad"], "old.json")));
  act(() => result.current.loadFromFile(new File(["valid"], "new.json")));
  await act(async () => readers[1].onload?.({ target: { result: new TextEncoder().encode(JSON.stringify(fixture)).buffer } } as ProgressEvent<FileReader>));
  expect(result.current.artifactIdentity?.name).toBe("new.json");
  act(() => readers[0].onerror?.({} as ProgressEvent<FileReader>));
  expect(result.current.error).toBeNull();
  expect(result.current.loading).toBe(false);
  expect(result.current.bundle?.metadata.seed).toBe(1701);
});

it("retains the world after an unexpected decoder exception or file read failure", async () => {
  const { result } = renderHook(() => useBundle());
  const file = new File([JSON.stringify(fixture)], "world.json");
  act(() => result.current.loadFromFile(file));
  await waitFor(() => expect(result.current.loading).toBe(false));
  const loaded = result.current.bundle;
  const original = result.current.artifactIdentity;
  vi.spyOn(bundleFile, "decodeBundleBytes").mockRejectedValueOnce(new Error("decode interrupted"));
  act(() => result.current.loadFromFile(file));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toContain("decode interrupted");
  expect(result.current.bundle).toBe(loaded);
  expect(result.current.artifactIdentity).toBe(original);
  const read = vi.spyOn(FileReader.prototype, "readAsArrayBuffer").mockImplementationOnce(() => { throw new Error("file unavailable"); });
  act(() => result.current.loadFromFile(file));
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toContain("file unavailable");
  expect(result.current.bundle).toBe(loaded);
  expect(result.current.artifactIdentity).toBe(original);
  read.mockRestore();
  act(() => result.current.loadFromFile(file));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBeNull();
});
