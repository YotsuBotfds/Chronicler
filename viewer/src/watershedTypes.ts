/**
 * The watershed record (`snapshot.livelihoods.watershed`, schema 1, stage B1):
 * a conserved water account on the drainage graph of a procedural world,
 * written by `chronicler.watershed.snapshot_summary`. Values are rounded to
 * six decimals in the record; the full-precision account stays in the saved
 * state. Kept out of the pinned `types.ts` (precedent: `transactionTypes.ts`).
 */

/**
 * Per-region columns of a settled turn, by region index (water units unless
 * noted). Outflow is not recorded: it is each region's residual by
 * construction, derived by `watershedOutflow`.
 */
export const WATERSHED_COLUMNS = [
  "storage_open", "precipitation", "external_in", "external_out", "inflow", "evaporation",
  "withdrawal", "storage", "capacity", "index_observed", "index_derived", "flood_excess",
] as const;
export type WatershedColumn = typeof WATERSHED_COLUMNS[number];

export type WatershedRegions = Record<WatershedColumn, number[]> & { drought_turns: number[] };

export interface WatershedFlood {
  turn: number;
  region: number;
  excess: number;
  arrivals: number;
  channel: number;
  precipitation: number;
  inflow: number;
  external_in: number;
  storage_open: number;
  capacity: number;
  /** [tributary region index, outflow it sent this turn]. */
  tributaries: Array<[number, number]>;
  upstream_cover: number | null;
  upstream_deforested: number;
}

/** An open drought after its declaration (its conditions are in its declaration and end records). */
export interface WatershedOpenDrought {
  region: number;
  start_turn: number;
  turns: number;
  declared_turn: number;
  min_fraction: number;
}

/** An external flow by recorded source (non-zero entries only). */
export interface WatershedExternal {
  region: number;
  direction: "in" | "out";
  source: "coastal_flood" | "unattributed";
  amount: number;
}

export interface WatershedDrought {
  region: number;
  start_turn: number;
  turns: number;
  declared_turn: number | null;
  end_turn: number | null;
  min_fraction: number;
  precipitation: number;
  normal_precipitation: number;
  inflow: number;
  evaporation: number;
  withdrawal: number;
  upstream_withdrawal: number;
  upstream_cover: number | null;
}

export interface WatershedTotals {
  precipitation: number;
  external_in: number;
  external_out: number;
  evaporation: number;
  withdrawal: number;
  to_sea: number;
  to_sink: number;
  to_lake: number;
  transfer: number;
  external_out_unmet: number;
  external_in_coastal_flood: number;
  external_in_unattributed: number;
  external_out_unattributed: number;
  storage_open: number;
  storage_close: number;
  closure_residual: number;
}

/** down[i]: the region index i drains to, `sea` (-1), `sink` (-2) or `lake` (-3). */
export interface WatershedGraph { down: number[]; sea: -1; sink: -2; lake: -3; river_steps: number }

/** The static part of a record (graph, parameters, units). */
export interface WatershedStatic {
  opened_turn: number;
  units: Record<string, string>;
  parameters: Record<string, number | Record<string, number>>;
  graph: WatershedGraph;
}

export interface WatershedRecord {
  schema_version: 1;
  stage: "B1";
  mode: "record_only";
  source_turn: number;
  completed_turn: number;
  opened_turn: number;
  /** The static part, in every record (a history segment reads on its own). */
  units: Record<string, string>;
  parameters: Record<string, number | Record<string, number>>;
  graph: WatershedGraph;
  observed: boolean;
  phase: string | null;
  /** The baseline index was not observed after the previous tick: external flows unattributed. */
  stale_baseline: boolean | null;
  regions: WatershedRegions | null;
  floods: WatershedFlood[] | null;
  droughts: { declared: WatershedDrought[]; open: WatershedOpenDrought[]; ended: WatershedDrought[] } | null;
  external: WatershedExternal[] | null;
  totals: WatershedTotals | null;
  /** The account's storage, recorded only when the turn is unobserved (else `regions.storage`). */
  storage: number[] | null;
  cumulative: Record<string, number>;
  counters: Record<string, number>;
}

/**
 * One snapshot's reading. `disabled`: no snapshot of the run carries the
 * record (the switch was off). `absent`: the run has it, this snapshot does
 * not. `malformed`: present but refused (with the reason). `unobserved`: a
 * valid record whose turn settled no account (its per-turn values are
 * unknown, not zero). `ok`: a settled turn, where a zero is a recorded zero.
 */
export type WatershedReading =
  | { status: "disabled" }
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "unobserved"; record: WatershedRecord; statics: WatershedStatic }
  | { status: "ok"; record: WatershedRecord; statics: WatershedStatic };
