/// <reference types="node" />
import { webcrypto } from "node:crypto";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import fixture from "../../__fixtures__/transport_bundle.json";
import { useBundle } from "../useBundle";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

// Valid JSON whose version-6 history patches are malformed.
function malformed(patch: unknown): string {
  const bundle = structuredClone(fixture) as unknown as Record<string, unknown>;
  const delta = bundle.history_delta as unknown[];
  delta[3] = patch;
  return JSON.stringify(bundle);
}

it.each([
  ["a list patch that is not iterable", { active_wars: { "~l": 3 } }],
  ["an index past the list", { active_wars: { "~l": [[99, ["A", "B"]]] } }],
  ["a key order naming a missing key", { "~o": ["turn", "nope"] }],
])("ends loading with a readable error for %s", async (_name, patch) => {
  vi.stubGlobal("crypto", webcrypto);
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File([malformed(patch)], "bad-delta.json")));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.bundle).toBeNull();
  expect(result.current.error).toMatch(/history_delta\[3\]/);
});

it("still loads the valid fixture", async () => {
  vi.stubGlobal("crypto", webcrypto);
  const { result } = renderHook(() => useBundle());
  act(() => result.current.loadFromFile(new File([JSON.stringify(fixture)], "transport.json")));
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.error).toBeNull();
  expect(result.current.bundle?.history).toHaveLength(10);
});
