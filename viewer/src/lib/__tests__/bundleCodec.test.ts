import { describe, expect, it } from "vitest";
import { decodeBundlePayload, decodeHistory, isEncodedBundle } from "../bundleCodec";
import { classifyParsedBundlePayload, parseBundleJsonPayload } from "../bundleLoader";
import citiesFixture from "../../__fixtures__/cities_bundle.json";
import citiesV6 from "../../__fixtures__/cities_bundle_v6.json";
import sampleBundle from "../../__fixtures__/sample_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";

// cities_bundle_v6.json is what the Python writer (src/chronicler/bundle_codec.py)
// writes for cities_bundle.json at bundle version 6 (tests/test_bundle_codec.py).
const citiesAtVersion6 = {
  ...citiesFixture,
  metadata: { ...citiesFixture.metadata, bundle_version: 6 },
};

describe("bundleCodec", () => {
  it("decodes a version-6 file written by the Python encoder", () => {
    const raw = citiesV6 as unknown as Record<string, unknown>;
    expect(isEncodedBundle(raw)).toBe(true);
    expect("history" in raw).toBe(false);
    expect((raw.world_state as Record<string, unknown>).events_timeline).toBeNull();
    const decoded = decodeBundlePayload(raw);
    expect(decoded).toEqual(citiesAtVersion6);
    expect("history_delta" in decoded).toBe(false);
    expect(Object.keys(decoded)).toEqual(Object.keys(citiesFixture));
  });

  it("loads version-6 text through the bundle loader", () => {
    const result = parseBundleJsonPayload(JSON.stringify(citiesV6));
    expect(result.kind).toBe("legacy");
    if (result.kind === "legacy") {
      expect(result.bundle.history).toHaveLength(250);
      expect(result.bundle.history).toEqual(citiesFixture.history);
      expect(result.bundle.world_state.events_timeline).toEqual(citiesFixture.events_timeline);
      expect(result.bundle.metadata.bundle_version).toBe(6);
    }
  });

  it("returns older and decoded bundles unchanged", () => {
    for (const fixture of [sampleBundle, systemsFixture, citiesFixture]) {
      const raw = fixture as unknown as Record<string, unknown>;
      expect(isEncodedBundle(raw)).toBe(false);
      expect(decodeBundlePayload(raw)).toBe(raw);
      const result = classifyParsedBundlePayload(fixture);
      expect(result.kind).toBe("legacy");
      if (result.kind === "legacy") {
        expect(result.bundle).toBe(fixture);
      }
    }
    const decoded = decodeBundlePayload(citiesV6 as unknown as Record<string, unknown>);
    expect(decodeBundlePayload(decoded)).toBe(decoded);
  });

  it("applies object, list and replacement patches", () => {
    const history = decodeHistory([
      { turn: 1, civ_stats: { A: { population: 5, regions: ["r0"] }, B: { population: 3 } },
        wars: [{ turns: 1 }, { turns: 2 }, { turns: 3 }], x: [1, 2], order: { a: 1, b: 2 } },
      { turn: 2, civ_stats: { A: { population: 6 } }, wars: { "~l": [[0, { turns: 2 }]], "~n": 2 },
        x: { "~r": { y: 1 } }, order: { "~o": ["b", "a"] } },
      { turn: 3, civ_stats: { C: { population: 1 }, "~d": ["B"] }, wars: { "~l": [], "~t": [{ turns: 9 }] },
        x: [3] },
      {},
    ]);
    expect(history).toEqual([
      { turn: 1, civ_stats: { A: { population: 5, regions: ["r0"] }, B: { population: 3 } },
        wars: [{ turns: 1 }, { turns: 2 }, { turns: 3 }], x: [1, 2], order: { a: 1, b: 2 } },
      { turn: 2, civ_stats: { A: { population: 6, regions: ["r0"] }, B: { population: 3 } },
        wars: [{ turns: 2 }, { turns: 2 }], x: { y: 1 }, order: { b: 2, a: 1 } },
      { turn: 3, civ_stats: { A: { population: 6, regions: ["r0"] }, C: { population: 1 } },
        wars: [{ turns: 2 }, { turns: 2 }, { turns: 9 }], x: [3], order: { b: 2, a: 1 } },
      { turn: 3, civ_stats: { A: { population: 6, regions: ["r0"] }, C: { population: 1 } },
        wars: [{ turns: 2 }, { turns: 2 }, { turns: 9 }], x: [3], order: { b: 2, a: 1 } },
    ]);
    expect(Object.keys((history[1] as { order: object }).order)).toEqual(["b", "a"]);
    // The first snapshot is not changed by later patches.
    expect((history[0] as { wars: unknown[] }).wars).toHaveLength(3);
  });
});
