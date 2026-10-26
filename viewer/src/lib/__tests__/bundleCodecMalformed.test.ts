import { describe, expect, it } from "vitest";
import { BundleDecodeError, decodeHistory } from "../bundleCodec";
import { parseBundleJsonPayload } from "../bundleLoader";

// The same cases as tests/test_historical_parity.py (Python codec).
const FIRST = { turn: 1, civ_stats: { A: { population: 1 } }, active_wars: [["A", "B"]] };
const CASES: [string, unknown, string][] = [
  ["index past the list", [FIRST, { active_wars: { "~l": [[5, 1]] } }], "history_delta[1]"],
  ["~l not a list", [FIRST, { active_wars: { "~l": 3 } }], "'~l' must be a list"],
  ["~o names a missing key", [FIRST, { "~o": ["turn", "nope"] }], "'~o'"],
  ["~n not an int", [FIRST, { active_wars: { "~l": [], "~n": "x" } }], "'~n'"],
  ["~n longer than the list", [FIRST, { active_wars: { "~l": [], "~n": 9 } }], "'~n'"],
  ["~d not a list", [FIRST, { "~d": 5 }], "'~d'"],
  ["~d names a missing key", [FIRST, { "~d": ["missing"] }], "'~d'"],
  ["list patch without ~l", [FIRST, { active_wars: { "~t": [1] } }], "needs '~l'"],
  ["list keys against an object", [FIRST, { civ_stats: { "~l": [] } }], "object patch"],
  ["patch against a number", [FIRST, { turn: { "~t": [] } }], "against a number"],
  ["~r with other keys", [FIRST, { turn: { "~r": 2, x: 1 } }], "'~r'"],
  ["snapshot not an object", [FIRST, ["x"]], "must be an object"],
  ["history_delta not a list", { turn: 1 }, "must be a list"],
  ["first item not a snapshot", ["not a snapshot"], "history_delta[0]"],
];

describe("malformed version-6 history patches", () => {
  it.each(CASES)("throws BundleDecodeError for %s", (_name, delta, needle) => {
    expect(() => decodeHistory(delta)).toThrow(BundleDecodeError);
    expect(() => decodeHistory(delta)).toThrow(needle);
  });

  it.each(CASES)("the loader reports %s as a diagnostic", (_name, delta, needle) => {
    const text = JSON.stringify({
      world_state: { events_timeline: null, named_events: null }, history_delta: delta,
      events_timeline: [], named_events: [], chronicle_entries: [], era_reflections: {},
      metadata: { bundle_version: 6 },
    });
    const result = parseBundleJsonPayload(text);
    expect(result.kind).toBe("error");
    if (result.kind === "error") {
      expect(result.diagnostics[0].code).toBe("INVALID_HISTORY_DELTA");
      expect(result.diagnostics[0].message).toContain(needle);
    }
  });

  it("decodes valid patches as before", () => {
    const history = decodeHistory([
      FIRST,
      { turn: 2, active_wars: { "~l": [[0, { "~l": [[1, "C"]] }]], "~t": [["B", "C"]] } },
      { turn: 3, "~d": ["civ_stats"] },
    ]);
    expect(history).toEqual([
      FIRST,
      { turn: 2, civ_stats: { A: { population: 1 } }, active_wars: [["A", "C"], ["B", "C"]] },
      { turn: 3, active_wars: [["A", "C"], ["B", "C"]] },
    ]);
  });
});
