import type { TurnSnapshot } from "../types";

/**
 * Household access metrics (DEP-7, observation only, default off;
 * `snapshot.livelihoods.household_access`, Python `chronicler.household_access`).
 * Rations: 1.0 is a full ration. Null is unobserved (or without people), never zero.
 */
export interface HouseholdAccessMetrics {
  alive: number;
  calories_met_share: number | null;
  shortfall_depth: number | null;
  /** L2 (food allocation) regions only; null in retail rows. */
  below_floor_share: number | null;
  poorer_half_shortfall_depth: number | null;
  richer_half_shortfall_depth: number | null;
  poorer_richer_ratio: number | null;
  child_shortfall_share: number | null;
  /** Household retail regions only; null where nothing was priced. */
  priced_out_persons: number | null;
  priced_out_deficit: number | null;
}

export interface HouseholdAccessWorld extends HouseholdAccessMetrics {
  allocation_alive: number; retail_alive: number; retail_regions: number; priced_out_share: number | null;
}

export interface HouseholdAccessRegion extends HouseholdAccessMetrics {
  region: number; source: "allocation" | "retail";
}

export interface HouseholdAccessRecord {
  schema_version: 1; stage: "DEP-7"; source_turn: number;
  /** Null: no allocation frame in the source turn (unknown, not zero). */
  world: HouseholdAccessWorld | null;
  /** Null: nothing observed in the source turn. */
  regions: HouseholdAccessRegion[] | null;
  counters: Record<string, number>;
  primaries: { P1_poorer_half_shortfall_per_1000: number | null; P2_priced_out_per_1000: number | null };
}

export type HouseholdAccessReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: HouseholdAccessRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const share = (x: unknown): boolean => x === null || (amount(x) && x <= 1 + 1e-6);
const optional = (x: unknown): boolean => x === null || amount(x);
const SHARES = ["calories_met_share", "shortfall_depth", "below_floor_share", "poorer_half_shortfall_depth",
  "richer_half_shortfall_depth", "child_shortfall_share"] as const;
const L2_ONLY = ["below_floor_share", "poorer_half_shortfall_depth", "richer_half_shortfall_depth",
  "poorer_richer_ratio", "child_shortfall_share"] as const;

function metricsProblem(x: Record<string, unknown>): string | null {
  if (!count(x.alive)) return "alive";
  const bad = SHARES.find((key) => !share(x[key]));
  if (bad) return bad;
  if (!optional(x.poorer_richer_ratio)) return "poorer_richer_ratio";
  if (!(x.priced_out_persons === null || count(x.priced_out_persons))) return "priced_out_persons";
  if (!optional(x.priced_out_deficit)) return "priced_out_deficit";
  if (finite(x.calories_met_share) && finite(x.shortfall_depth)
    && Math.abs(x.calories_met_share + x.shortfall_depth - 1) > 1e-5) return "calories and shortfall do not sum to one";
  return null;
}

function regionProblem(x: unknown, regions: number, seen: Set<number>): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || seen.has(x.region)) return "region";
  seen.add(x.region);
  if (x.source !== "allocation" && x.source !== "retail") return "source";
  const problem = metricsProblem(x);
  if (problem) return problem;
  if (x.source === "retail" && L2_ONLY.some((key) => x[key] !== null)) return "retail row with allocation metrics";
  if (x.source === "allocation" && (x.priced_out_persons !== null || x.priced_out_deficit !== null)) {
    return "allocation row with retail metrics";
  }
  return null;
}

function worldProblem(x: unknown): string | null {
  if (!object(x)) return "world";
  if (!count(x.allocation_alive) || !count(x.retail_alive) || !count(x.retail_regions)) return "world counts";
  const problem = metricsProblem(x);
  if (problem) return problem;
  if (x.alive !== x.allocation_alive + x.retail_alive) return "alive does not add up";
  if (!share(x.priced_out_share)) return "priced_out_share";
  return null;
}

/** Strict reader: absent without the part; malformed when from another schema, misdated or inconsistent. */
export function householdAccessAt(snapshot: TurnSnapshot | null, regionCount: number): HouseholdAccessReading {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  const x = object(livelihoods) ? livelihoods.household_access : undefined;
  if (x == null) return { status: "absent" };
  const bad = (reason: string): HouseholdAccessReading => ({ status: "malformed", reason });
  if (!object(x) || x.schema_version !== 1 || x.stage !== "DEP-7") return bad("schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("source_turn");
  if (!object(x.counters) || !Object.values(x.counters).every(amount)) return bad("counters");
  const p = x.primaries;
  if (!object(p) || !optional(p.P1_poorer_half_shortfall_per_1000) || !optional(p.P2_priced_out_per_1000)) {
    return bad("primaries");
  }
  if (x.regions === null) {
    return x.world === null ? { status: "ok", record: x as unknown as HouseholdAccessRecord } : bad("world without regions");
  }
  if (!Array.isArray(x.regions)) return bad("regions");
  const seen = new Set<number>();
  for (const row of x.regions) {
    const problem = regionProblem(row, regionCount, seen);
    if (problem) return bad(`region row: ${problem}`);
  }
  if (x.world !== null) {
    const problem = worldProblem(x.world);
    if (problem) return bad(`world: ${problem}`);
  }
  return { status: "ok", record: x as unknown as HouseholdAccessRecord };
}
