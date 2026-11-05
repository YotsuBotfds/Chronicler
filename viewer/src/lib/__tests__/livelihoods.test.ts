import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { foodAllocationAt, meanShortfall } from "../foodAllocation";
import { presentSystems, SYSTEM_KEYS } from "../systems";
import { workshopsAt } from "../workshops";

/** Constructed observations to test the readers; not a simulation run. */
const receipt = { turn: 4, site: 0, region: 1, settlement_id: 7, rank: 2, diverted_fraction: 0.3,
  resident_adult_farmers: 3, excluded_trip: 0, excluded_army: 1, excluded_assigned: 0, eligible: 2,
  crew: [11, 15], crew_ages: [30, 41], work_available: 0.6, allocated: 0.6, realized: 0.3,
  legacy_craft_ceiling: 1.5, region_craft_output: 0.6, region_craft_input: { timber: 0.5, ore: 0.1 },
  asset: "open", payer: 0, funded: true, craft_ceiling: 1.2, paid: { upkeep: 3 }, arrears_after: 0,
  condition_after: 1, affected_ordinary_income_share: 0 };
const workshops = { schema_version: 1, stage: "L1B", mode: "operate", source_turn: 4,
  sites: [{ site: 0, region: 1, settlement_id: 7, city_name: "Ashford", selected_turn: 2, status: "open",
    closed_turn: null, closed_reason: null, asset: "open" }], closed: [], receipts: [receipt], counters: {} };
const region = { region: 1, scarce: 1, phase2_alive: 4, alive: 4, households: 2, sufficiency: 0.7,
  rations_available: 2.8, relief_available: 0, allocated: 2.8, unallocated: 0, relief_to_targeted: 0,
  shortfall: 1.2, below_floor: 0, fully_fed: 2, min_ration: 0.5, max_ration: 1, people_poorer_half: 2,
  shortfall_poorer_half: 1, people_richer_half: 2, shortfall_richer_half: 0.2, children: 1, shortfall_children: 0.5 };
const food = { schema_version: 1, stage: "L2", regime: "floor_means", source_turn: 4,
  totals: { scarce_regions: 1, alive: 4, allocated: 2.8, unallocated: 0, shortfall: 1.2, people_poorer_half: 2,
    shortfall_poorer_half: 1, people_richer_half: 2, shortfall_richer_half: 0.2, children: 1, shortfall_children: 0.5,
    relief_to_targeted: 0 },
  regions: [region], sample: [[11, 1, 11, 0.5, false]], sample_columns: [], counters: {} };
const snap = (livelihoods: unknown, turn = 5) => ({ turn, livelihoods } as unknown as TurnSnapshot);

describe("livelihoods readers", () => {
  it("read dated, well-formed records only", () => {
    expect(workshopsAt(snap({ schema_version: 1, workshops }), 3)?.sites[0].city_name).toBe("Ashford");
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: food }), 3)?.regime).toBe("floor_means");
    expect(workshopsAt(snap({ schema_version: 1, workshops }, 6), 3)).toBeNull();
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: food }, 6), 3)).toBeNull();
    expect(workshopsAt(snap({ schema_version: 1, workshops }), 1)).toBeNull();          // region out of range
    expect(workshopsAt(snap(null), 3)).toBeNull();
  });

  it("refuse impossible work and unclosed allocations", () => {
    const tooMuch = { ...workshops, receipts: [{ ...receipt, realized: 0.9 }] };
    expect(workshopsAt(snap({ schema_version: 1, workshops: tooMuch }), 3)).toBeNull();
    const nine = { ...workshops, receipts: [{ ...receipt, crew: [1, 2, 3, 4, 5, 6, 7, 8, 9], eligible: 9 }] };
    expect(workshopsAt(snap({ schema_version: 1, workshops: nine }), 3)).toBeNull();
    const open = { ...food, regions: [{ ...region, unallocated: 0.5 }] };
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: open }), 3)).toBeNull();
  });

  it("accepts unknown relief as null and still refuses negative relief", () => {
    const unknown = { ...food, regions: [{ ...region, relief_available: null, relief_to_targeted: null }] };
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: unknown }), 3)?.regions?.[0].relief_available).toBeNull();
    const negative = { ...food, regions: [{ ...region, relief_available: -1 }] };
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: negative }), 3)).toBeNull();
  });

  it("keeps unobserved turns unknown, not zero", () => {
    const unobserved = { ...food, totals: null, regions: null, sample: null };
    expect(foodAllocationAt(snap({ schema_version: 1, food_allocation: unobserved }), 3)?.totals).toBeNull();
    expect(workshopsAt(snap({ schema_version: 1, workshops: { ...workshops, receipts: null } }), 3)?.receipts).toBeNull();
    expect(meanShortfall(1, 0)).toBeNull();
    expect(meanShortfall(1, 2)).toBe(0.5);
  });

  it("show the Livelihoods tab only when a record exists", () => {
    expect(SYSTEM_KEYS).toContain("livelihoods");
    const plain = [{ turn: 1, civ_stats: {} }] as unknown as TurnSnapshot[];
    expect(presentSystems(plain)).not.toContain("livelihoods");
    const withRecord = [{ turn: 1, civ_stats: {}, livelihoods: { schema_version: 1 } }] as unknown as TurnSnapshot[];
    expect(presentSystems(withRecord)).toContain("livelihoods");
  });
});
