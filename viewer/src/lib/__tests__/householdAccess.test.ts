import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { householdAccessAt } from "../householdAccess";

// The frame chronicler.household_access writes for tests/test_household_access.py's
// L2 totals plus one retail region (source turn 5, read at turn 6).
const allocationRow = {
  region: 1, source: "allocation", alive: 40, calories_met_share: 0.6, shortfall_depth: 0.4,
  below_floor_share: 0.25, poorer_half_shortfall_depth: 0.6, richer_half_shortfall_depth: 0.2,
  poorer_richer_ratio: 3.0, child_shortfall_share: 0.3125, priced_out_persons: null, priced_out_deficit: null,
};
const retailRow = {
  region: 2, source: "retail", alive: 20, calories_met_share: 0.75, shortfall_depth: 0.25,
  below_floor_share: null, poorer_half_shortfall_depth: null, richer_half_shortfall_depth: null,
  poorer_richer_ratio: null, child_shortfall_share: null, priced_out_persons: 4, priced_out_deficit: 2.5,
};
const world = {
  alive: 120, allocation_alive: 100, retail_alive: 20, retail_regions: 1, calories_met_share: 0.791667,
  shortfall_depth: 0.208333, below_floor_share: 0.1, poorer_half_shortfall_depth: 0.3,
  richer_half_shortfall_depth: 0.1, poorer_richer_ratio: 3.0, child_shortfall_share: 0.4,
  priced_out_persons: 4, priced_out_share: 0.2, priced_out_deficit: 2.5,
};
const part = {
  schema_version: 1, stage: "DEP-7", source_turn: 5, world, regions: [allocationRow, retailRow],
  counters: { turns_observed: 1, person_turns: 120, priced_out_person_turns: 4 },
  primaries: { P1_poorer_half_shortfall_per_1000: 300.0, P2_priced_out_per_1000: 33.333333 },
};
const snapshot = (edits: Record<string, unknown> = {}, turn = 6) =>
  ({ turn, livelihoods: { schema_version: 1, household_access: { ...structuredClone(part), ...edits } } }) as unknown as TurnSnapshot;

describe("householdAccessAt", () => {
  it("is absent without the part and reads a recorded frame", () => {
    expect(householdAccessAt(null, 4).status).toBe("absent");
    expect(householdAccessAt({ turn: 6 } as TurnSnapshot, 4).status).toBe("absent");
    expect(householdAccessAt({ turn: 6, livelihoods: { schema_version: 1 } } as unknown as TurnSnapshot, 4).status).toBe("absent");
    const reading = householdAccessAt(snapshot(), 4);
    expect(reading.status).toBe("ok");
    if (reading.status !== "ok") return;
    expect(reading.record.world?.priced_out_persons).toBe(4);
    expect(reading.record.regions?.map((r) => r.source)).toEqual(["allocation", "retail"]);
  });

  it("keeps unobserved (null) distinct from zero", () => {
    const unobserved = householdAccessAt(snapshot({ world: null, regions: null }), 4);
    expect(unobserved.status).toBe("ok");
    if (unobserved.status === "ok") expect(unobserved.record.world).toBeNull();
    const retailOnly = householdAccessAt(snapshot({ world: null, regions: [retailRow] }), 4);
    expect(retailOnly.status).toBe("ok");
    const noPricing = householdAccessAt(snapshot({
      world: { ...world, alive: 100, retail_alive: 0, retail_regions: 0, priced_out_persons: null,
        priced_out_share: null, priced_out_deficit: null, calories_met_share: 0.8, shortfall_depth: 0.2 },
      regions: [allocationRow],
    }), 4);
    expect(noPricing.status).toBe("ok");
  });

  it.each([
    ["misdated", { source_turn: 4 }],
    ["another stage", { stage: "L2" }],
    ["another schema", { schema_version: 2 }],
    ["world without regions", { regions: null }],
    ["region out of range", { regions: [{ ...allocationRow, region: 4 }] }],
    ["repeated region", { regions: [allocationRow, allocationRow] }],
    ["unknown source", { regions: [{ ...retailRow, source: "market" }] }],
    ["share above one", { regions: [{ ...allocationRow, below_floor_share: 1.5 }] }],
    ["calories and shortfall disagree", { regions: [{ ...allocationRow, shortfall_depth: 0.1 }] }],
    ["retail row with L2 metrics", { regions: [{ ...retailRow, below_floor_share: 0 }] }],
    ["allocation row with pricing", { regions: [{ ...allocationRow, priced_out_persons: 0 }] }],
    ["alive does not add up", { world: { ...world, alive: 121 } }],
    ["fractional people", { world: { ...world, priced_out_persons: 4.5 } }],
    ["negative counter", { counters: { person_turns: -1 } }],
    ["missing primaries", { primaries: null }],
  ])("refuses %s", (_name, edits) => {
    expect(householdAccessAt(snapshot(edits as Record<string, unknown>), 4).status).toBe("malformed");
  });
});
