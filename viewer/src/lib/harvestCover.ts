import { isRecord as object, amount } from "./recordGuards";
import type { TurnSnapshot } from "../types";

export interface CoverRow {
  region: number; slots: number[]; standing: number; capacity: number; ratio: number;
  cover_before: number; supported_cover: number; proposed_loss: number; loss: number; cover_after: number;
}
export interface CoverRecord { schema_version: 1; stage: "B4"; source_turn: number; mode: "loss" | "record_only"; rows: CoverRow[] | null }
export function harvestCoverAt(snapshot: TurnSnapshot | null, regions: number): { status: "absent" | "malformed" | "unobserved" | "recorded"; record?: CoverRecord } {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  const x = object(livelihoods) ? livelihoods.harvest_cover : undefined;
  if (x == null) return { status: "absent" };
  const bad = (): { status: "malformed" } => ({ status: "malformed" });
  if (!object(x) || x.schema_version !== 1 || x.stage !== "B4" || !Number.isInteger(x.source_turn) || x.source_turn !== (snapshot?.turn ?? 0) - 1
    || (x.mode !== "loss" && x.mode !== "record_only") || (x.rows !== null && !Array.isArray(x.rows))) return bad();
  if (x.rows !== null) {
    const ids = new Set();
    for (const row of x.rows as unknown[]) {
      if (!object(row) || !Number.isInteger(row.region) || (row.region as number) < 0 || (row.region as number) >= regions
        || ids.has(row.region) || !Array.isArray(row.slots) || row.slots.length === 0 || new Set(row.slots).size !== row.slots.length || !row.slots.every((s) => Number.isInteger(s) && s >= 0 && s < 3)
        || !["standing", "capacity", "ratio", "cover_before", "supported_cover", "proposed_loss", "loss", "cover_after"].every((k) => amount(row[k]))) return bad();
      ids.add(row.region);
      const r = row as unknown as CoverRow;
      if (r.capacity <= 0 || r.ratio > 1 + 1e-8 || r.cover_before > 1 || r.cover_after > 1 || r.supported_cover > 1
        || Math.abs(r.standing / r.capacity - r.ratio) > 1e-8
        || r.loss > r.proposed_loss + 1e-8 || r.cover_after + 1e-8 < r.supported_cover
        || Math.abs(r.cover_before - r.loss - r.cover_after) > 1e-8 || (x.mode === "record_only" && r.loss !== 0)) return bad();
    }
  }
  return { status: x.rows === null ? "unobserved" : "recorded", record: x as unknown as CoverRecord };
}
