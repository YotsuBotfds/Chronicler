/**
 * The watershed record (`snapshot.livelihoods.watershed`, schema 1, stage B1):
 * a conserved water account on the drainage graph of a procedural world,
 * written by `chronicler.watershed.snapshot_summary`. Values are rounded to
 * six decimals in the record; the full-precision account stays in the saved
 * state. Kept out of the pinned `types.ts` (precedent: `transactionTypes.ts`).
 */

/** Per-region columns of a settled turn, by region index (water units unless noted). */
export const WATERSHED_COLUMNS = [
  "storage_open", "precipitation", "external_in", "external_out", "inflow", "evaporation",
  "withdrawal", "outflow", "storage", "capacity", "index_observed", "index_derived", "flood_excess",
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
  transfer: number;
  external_out_unmet: number;
  storage_open: number;
  storage_close: number;
  closure_residual: number;
}

export interface WatershedRecord {
  schema_version: 1;
  stage: "B1";
  mode: "record_only";
  source_turn: number;
  completed_turn: number;
  opened_turn: number;
  units: Record<string, string>;
  parameters: Record<string, number | Record<string, number>>;
  /** down[i]: the region index i drains to, `sea` (-1) or `sink` (-2). */
  graph: { down: number[]; sea: -1; sink: -2; river_steps: number };
  observed: boolean;
  phase: string | null;
  regions: WatershedRegions | null;
  floods: WatershedFlood[] | null;
  droughts: { open: WatershedDrought[]; ended: WatershedDrought[] } | null;
  totals: WatershedTotals | null;
  storage: number[];
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
  | { status: "unobserved"; record: WatershedRecord }
  | { status: "ok"; record: WatershedRecord };
