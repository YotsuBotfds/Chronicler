import { isRecord as object, finite, amount, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/** One scarce region's allocation (``snapshot.livelihoods.food_allocation.regions``). */
export interface FoodAllocationRegion {
  region: number; scarce: number; phase2_alive: number; alive: number; households: number;
  sufficiency: number; rations_available: number;
  /** Null: the pre-release sufficiency was unknown, so the release share is unknown (not zero). */
  relief_available: number | null; allocated: number;
  unallocated: number; relief_to_targeted: number | null; shortfall: number; below_floor: number;
  fully_fed: number; min_ration: number; max_ration: number; people_poorer_half: number;
  shortfall_poorer_half: number; people_richer_half: number; shortfall_richer_half: number;
  children: number; shortfall_children: number;
}

export interface FoodAllocationRecord {
  schema_version: 1; stage: "L2"; regime: "equal" | "floor_means" | "targeted_relief"; source_turn: number;
  /** Null: no allocation ran in the source turn (unknown, not zero). */
  totals: Record<string, number> | null;
  regions: FoodAllocationRegion[] | null;
  sample: Array<[number, number, number, number, boolean]> | null;
  sample_columns: string[];
  counters: Record<string, number>;
}

const REGIMES = ["equal", "floor_means", "targeted_relief"];
const NUMBERS = ["phase2_alive", "alive", "households", "sufficiency", "rations_available",
  "allocated", "unallocated", "shortfall", "below_floor", "min_ration", "max_ration",
  "people_poorer_half", "shortfall_poorer_half", "people_richer_half", "shortfall_richer_half"] as const;
/** Totals the panel shows; each must be present (missing is unknown, never zero). */
const TOTAL_COUNTS = ["scarce_regions", "alive", "people_poorer_half", "people_richer_half", "children"] as const;
const TOTAL_AMOUNTS = ["allocated", "unallocated", "shortfall", "shortfall_poorer_half",
  "shortfall_richer_half", "shortfall_children", "relief_to_targeted"] as const;

function validTotals(x: unknown): boolean {
  return object(x) && TOTAL_COUNTS.every((key) => count(x[key])) && TOTAL_AMOUNTS.every((key) => amount(x[key]))
    && (x.relief_unknown_regions === undefined || count(x.relief_unknown_regions));
}

function validSample(x: unknown, regions: number): boolean {
  return Array.isArray(x) && x.length === 5 && count(x[0]) && count(x[1]) && x[1] < regions && count(x[2])
    && amount(x[3]) && x[3] <= 1 + 1e-6 && typeof x[4] === "boolean";
}

function validRegion(x: unknown, regions: number): x is FoodAllocationRegion {
  if (!object(x) || !finite(x.region) || x.region < 0 || x.region >= regions
    || !NUMBERS.every((key) => finite(x[key]) && (x[key] as number) >= 0)
    || !["relief_available", "relief_to_targeted"].every((key) => x[key] === null || (finite(x[key]) && (x[key] as number) >= 0))) return false;
  const r = x as unknown as FoodAllocationRegion;
  const scale = Math.max(1, r.rations_available);
  return Math.abs(r.allocated + r.unallocated - r.rations_available) <= 1e-5 * scale
    && r.min_ration <= r.max_ration + 1e-9 && r.max_ration <= 1 + 1e-6;
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function foodAllocationAt(snapshot: TurnSnapshot | null, regionCount: number): FoodAllocationRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.food_allocation;
  if (!object(x) || x.schema_version !== 1 || !REGIMES.includes(x.regime as string) || !finite(x.source_turn)
    || x.source_turn + 1 !== snapshot?.turn || !object(x.counters)) return null;
  if (x.totals === null) return x.regions === null && x.sample === null ? x as unknown as FoodAllocationRecord : null;
  if (!validTotals(x.totals) || !Array.isArray(x.regions) || !Array.isArray(x.sample)
    || !x.regions.every((r) => validRegion(r, regionCount))
    || !x.sample.every((s) => validSample(s, regionCount))) return null;
  return x as unknown as FoodAllocationRecord;
}

/** Mean ration shortfall per person (0 = everyone fed); null without people. */
export function meanShortfall(total: number, people: number): number | null {
  return people > 0 ? total / people : null;
}
