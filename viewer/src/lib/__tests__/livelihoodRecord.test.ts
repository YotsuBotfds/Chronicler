import { describe, expect, it } from "vitest";
import { readLivelihoodRecord } from "../livelihoodRecord";
import type { TurnSnapshot } from "../../types";

const snap = (livelihoods: unknown) => ({ turn: 3, livelihoods }) as unknown as TurnSnapshot;

describe("readLivelihoodRecord", () => {
  it("returns the keyed record when both envelopes are schema version 1", () => {
    const record = { schema_version: 1, source_turn: 2 };
    expect(readLivelihoodRecord(snap({ schema_version: 1, workshops: record }), "workshops")).toBe(record);
  });

  it.each([
    ["a null snapshot", null],
    ["an undefined snapshot", undefined],
    ["no livelihoods", snap(undefined)],
    ["null livelihoods", snap(null)],
    ["array livelihoods", snap([])],
    ["livelihoods of another schema", snap({ schema_version: 2, workshops: { schema_version: 1 } })],
    ["livelihoods schema as a string", snap({ schema_version: "1", workshops: { schema_version: 1 } })],
    ["livelihoods without a schema", snap({ workshops: { schema_version: 1 } })],
    ["a missing key", snap({ schema_version: 1 })],
    ["a null keyed record", snap({ schema_version: 1, workshops: null })],
    ["an array keyed record", snap({ schema_version: 1, workshops: [] })],
    ["a keyed record of another schema", snap({ schema_version: 1, workshops: { schema_version: 2 } })],
    ["a keyed record without a schema", snap({ schema_version: 1, workshops: {} })],
  ])("returns null for %s", (_label, snapshot) => {
    expect(readLivelihoodRecord(snapshot as TurnSnapshot | null | undefined, "workshops")).toBeNull();
  });

  it("does not check source turns (each reader keeps its own rule)", () => {
    const record = { schema_version: 1, source_turn: 99 };
    expect(readLivelihoodRecord(snap({ schema_version: 1, timber_stock: record }), "timber_stock")).toBe(record);
  });
});
