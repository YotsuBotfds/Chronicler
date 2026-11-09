import { readLivelihoodRecord } from "./livelihoodRecord";
import { isRecord as object, amount, count as integer } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/** One timber slot's completed-turn account (``snapshot.livelihoods.timber_stock``). */
export interface TimberStockRow {
  region_id: number; slot: number;
  opening: number; cleared: number; extraction: number; overdraft: number;
  regrowth: number; removed: number; stock: number; capacity: number;
  cap: number | null; capped: boolean | null; water_gate_open: boolean;
}
export interface TimberStockTotals {
  opening: number; cleared: number; extraction: number; overdraft: number;
  regrowth: number; removed: number; stock: number; capacity: number;
  slots: number; capped_slots: number;
}
export interface TimberStockRecord {
  schema_version: 1; units: "timber_goods"; source_turn: number; completed_turn: number;
  enforce_cap: boolean;
  parameters: { regrowth_rate: number; seed_fraction: number; reference_crews_at_msy: number };
  /** False: no account was settled in the source turn; rows and totals are unknown, not zero. */
  observed: boolean;
  regions: TimberStockRow[] | null; totals: TimberStockTotals | null;
}

const FLOWS = ["opening", "cleared", "extraction", "overdraft", "regrowth", "removed", "stock", "capacity"] as const;
const PARAMETERS = ["regrowth_rate", "seed_fraction", "reference_crews_at_msy"] as const;

/** Ledger identity: opening − cleared − (extraction − overdraft) + regrowth − removed = stock. */
export function timberResidual(row: Pick<TimberStockRow, (typeof FLOWS)[number]>): number {
  return row.opening - row.cleared - (row.extraction - row.overdraft) + row.regrowth - row.removed - row.stock;
}

function closes(row: TimberStockRow): boolean {
  const scale = Math.max(1, row.opening, row.capacity, row.extraction);
  return Math.abs(timberResidual(row)) <= 1e-6 * scale;
}

function validRow(x: unknown, regionCount: number, enforced: boolean): x is TimberStockRow {
  if (!object(x) || !integer(x.region_id) || x.region_id >= regionCount || !integer(x.slot) || x.slot > 2
    || !FLOWS.every((key) => amount(x[key])) || typeof x.water_gate_open !== "boolean"
    || !(x.cap === null || amount(x.cap)) || !(x.capped === null || typeof x.capped === "boolean")) return false;
  const row = x as unknown as TimberStockRow;
  if (enforced ? row.overdraft !== 0 : row.cap !== null || row.capped !== null) return false;
  if (row.cap !== null && row.extraction > row.cap) return false;
  return row.overdraft <= row.extraction && closes(row);
}

/**
 * Strict reader: null when the record is absent, from another schema, dated to
 * another snapshot or malformed. Never borrows observations from other snapshots.
 */
export function timberStockAt(snapshot: TurnSnapshot | null, regionCount: number): TimberStockRecord | null {
  const x = readLivelihoodRecord(snapshot, "timber_stock");
  if (!x || x.units !== "timber_goods" || !integer(x.source_turn)
    || !integer(x.completed_turn) || x.completed_turn !== x.source_turn + 1 || x.completed_turn !== snapshot?.turn
    || typeof x.enforce_cap !== "boolean" || typeof x.observed !== "boolean"
    || !object(x.parameters) || !PARAMETERS.every((key) => amount((x.parameters as Record<string, unknown>)[key]))) return null;
  if (!x.observed) return x.regions === null && x.totals === null ? x as unknown as TimberStockRecord : null;
  if (!Array.isArray(x.regions) || !object(x.totals)) return null;
  const seen = new Set<string>();
  for (const item of x.regions) {
    if (!validRow(item, regionCount, x.enforce_cap)) return null;
    const key = `${item.region_id}:${item.slot}`;
    if (seen.has(key)) return null;
    seen.add(key);
  }
  const totals = x.totals;
  if (!FLOWS.every((key) => amount(totals[key])) || totals.slots !== x.regions.length || !integer(totals.capped_slots)
    || totals.capped_slots > x.regions.length) return null;
  return x as unknown as TimberStockRecord;
}
