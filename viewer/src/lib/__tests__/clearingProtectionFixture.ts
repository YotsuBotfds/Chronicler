import type { ClearingProtectionRecord, ProtectionReceipt, UnprotectedRegion } from "../clearingProtection";

/** Constructed observations for the reader and panel tests; not a simulation run. */
export function receipt(extra: Partial<ProtectionReceipt> = {}): ProtectionReceipt {
  return { region_id: 0, payer: 1, new: false, cover_before: 0.6, cover_after: 0.6, pressure_planned: true,
    required: 2, envelope: null, paid_planned: 2, p_planned: 1, p_applied: 1, clearing_active: true,
    cover_not_cleared: 0.02, cover_would_keep: 0.02, charged: 2, timber_capacity_kept: null, source: "native", ...extra };
}
export function unprotected(extra: Partial<UnprotectedRegion> = {}): UnprotectedRegion {
  return { region_id: 2, controller: 1, reason: "over_limit", pressure_planned: true, clearing_active: true,
    cover_before: 0.5, cover_after: 0.48, cleared: 0.02, ...extra };
}
export function record(extra: Partial<ClearingProtectionRecord> = {}): ClearingProtectionRecord {
  return { schema_version: 1, units: { cover: "forest_cover", money: "treasury" }, mode: "enforced",
    source_turn: 4, completed_turn: 5,
    parameters: { max_regions: 2, warden_cost: 2, protection: 1, min_cover: 0.2, idle_limit: 12, unfunded_limit: 3,
      forest_clearing: 0.02, forest_pop_ratio: 0.5 },
    observed: true,
    receipts: [receipt(), receipt({ region_id: 1, new: true, paid_planned: 1, p_planned: 0.5, p_applied: 0.5,
      cover_before: 0.7, cover_after: 0.69, cover_not_cleared: 0.01, cover_would_keep: 0.01, charged: 1 })],
    unprotected: [unprotected(), unprotected({ region_id: 3, controller: 2, reason: "not_forested", cover_before: 0.1, cover_after: 0.08 })],
    decisions: [{ turn: 4, region_id: 1, civ: 1, kind: "adopted", reason: "clearing_pressure" },
      { turn: 4, region_id: 3, civ: 2, kind: "ended", reason: "cover_lost" }],
    protections: [
      { region_id: 0, payer: 1, adopted_turn: 2, idle_turns: 0, unfunded_turns: 0, active_turns: 3, charged: 6, cover_not_cleared: 0.06 },
      { region_id: 1, payer: 1, adopted_turn: 4, idle_turns: 0, unfunded_turns: 0, active_turns: 1, charged: 1, cover_not_cleared: 0.01 }],
    counters: { adopted: 3, protected_region_turns: 4, clearing_active_turns: 4, required: 8, paid_planned: 7, charged: 7,
      adoption_over_limit: 1, cover_not_cleared: 0.07, ended_cover_lost: 1 }, ...extra };
}

/** A shallow copy without one key (an older record without that field). */
export function without<T extends object>(value: T, key: string): T {
  const copy = { ...value } as Record<string, unknown>;
  delete copy[key];
  return copy as T;
}
