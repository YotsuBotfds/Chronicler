import { describe, expect, it } from "vitest";
import sample from "../../__fixtures__/sample_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import citiesFixture from "../../__fixtures__/cities_bundle.json";
import regionInspectionFixture from "../../__fixtures__/region_inspection_bundle.json";
import transportFixture from "../../__fixtures__/transport_bundle.json";
import faithsFixture from "../../__fixtures__/faiths_bundle.json";
import { parseBundleBytes } from "../bundleFile";
import { parseBundleJsonPayload } from "../bundleLoader";
import { validateBundle, validateBundleStructure, validateViewableBundle } from "../bundleValidation";

type Raw = Record<string, unknown> & {
  history: Record<string, unknown>[];
  events_timeline: Record<string, unknown>[];
  named_events: Record<string, unknown>[];
  world_state: { civilizations: Record<string, unknown>[] };
};

/** A fixture as the loader hands it to validation (version-6 history expanded). */
function raw(fixture: unknown = sample): Raw {
  const parsed = parseBundleJsonPayload(JSON.stringify(fixture));
  if (parsed.kind !== "legacy") throw new Error("fixture is not a bundle");
  return parsed.bundle as unknown as Raw;
}
const bytes = (bundle: unknown) => new TextEncoder().encode(JSON.stringify(bundle)).buffer as ArrayBuffer;
const SUFFIX = ". Open a complete chronicle_bundle.json export.";

/** The two checks as file loading ran them before the single walk: structure, then the shell's fields. */
function twoWalks(bundle: Record<string, unknown>) {
  const structural = validateBundleStructure(bundle);
  return { structural, viewable: structural ? null : validateViewableBundle(bundle) };
}

describe("bundle validation in one walk", () => {
  it("reports a structural error at snapshot 9 before a viewable error at snapshot 2", () => {
    const bundle = raw();
    expect(bundle.history).toHaveLength(10);
    bundle.history[2].food = { sufficiency: ["not a number"] };
    delete bundle.history[9].relationships;
    expect(validateBundle(bundle, true)).toEqual({
      structural: "history[9].relationships has a missing or invalid value",
      viewable: null,
    });
    expect(parseBundleBytes(bytes(bundle))).toEqual({
      bundle: null,
      error: `Invalid bundle: history[9].relationships has a missing or invalid value${SUFFIX}`,
    });
  });

  it("reports the viewable error once the structure passes", () => {
    const bundle = raw();
    bundle.history[2].food = { sufficiency: ["not a number"] };
    expect(validateBundle(bundle, true)).toEqual({
      structural: null,
      viewable: "history[2].food.sufficiency has a missing or invalid value",
    });
    expect(validateBundle(bundle, false)).toEqual({ structural: null, viewable: null });
    expect(parseBundleBytes(bytes(bundle))).toEqual({
      bundle: null,
      error: `Incomplete or invalid viewer bundle: history[2].food.sufficiency has a missing or invalid value${SUFFIX}`,
    });
  });

  it("keeps the viewable order: civilizations, named events, timeline, history", () => {
    const bundle = raw();
    bundle.history[1].turn = 0;
    expect(validateBundle(bundle, true).viewable).toBe("history[1].turn must follow the previous recorded turn");
    bundle.events_timeline[3].causes = "not a list";
    expect(validateBundle(bundle, true).viewable).toBe("events_timeline[3].causes must be a list of text");
    bundle.named_events = [{ ...bundle.events_timeline[0] }];
    expect(validateBundle(bundle, true).viewable).toBe("named_events[0].name has a missing or invalid value");
    delete bundle.world_state.civilizations[1].goal;
    expect(validateBundle(bundle, true).viewable).toBe("world_state.civilizations[1].goal has a missing or invalid value");
    expect(validateBundle(bundle, true)).toEqual(twoWalks(bundle));
  });

  // Four fixtures pass both checks, transport through its version-6 history;
  // cities lacks the shell's civilization fields, faiths fails structure.
  const fixtures: Array<[string, unknown]> = [
    ["sample", sample], ["systems", systemsFixture], ["region inspection", regionInspectionFixture],
    ["transport", transportFixture], ["cities", citiesFixture], ["faiths", faithsFixture],
  ];
  const mutations: Array<[string, (bundle: Raw) => void]> = [
    ["unchanged", () => {}],
    ["a late structural and an early viewable error", (bundle) => {
      bundle.history[0].food = { sufficiency: [null, "x"] };
      bundle.history[bundle.history.length - 1].civ_stats = [];
    }],
    ["out-of-order snapshots", (bundle) => { bundle.history.reverse(); }],
    ["an event without consequences text", (bundle) => { bundle.events_timeline.at(-1)!.consequences = [1]; }],
    ["a timeline row without a turn", (bundle) => { delete bundle.events_timeline.at(-1)!.turn; }],
    ["a named event without a name", (bundle) => { bundle.named_events.push({ ...bundle.events_timeline[0] }); }],
    ["a leader without a trait", (bundle) => {
      // The region inspection fixture has no civilizations.
      if (bundle.world_state.civilizations[0]) bundle.world_state.civilizations[0].leader = { name: "Nobody" };
    }],
    ["no era reflections", (bundle) => { bundle.era_reflections = null; }],
  ];

  describe.each(fixtures)("%s fixture", (_name, fixture) => {
    it.each(mutations)("%s: the same errors as two walks", (_mutation, mutate) => {
      const bundle = raw(fixture);
      mutate(bundle);
      expect(validateBundle(bundle, true)).toEqual(twoWalks(bundle));
    });
  });
});
