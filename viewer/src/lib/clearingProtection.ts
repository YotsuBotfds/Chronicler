import type { TurnSnapshot } from "../types";

/** One protected region-turn's account (``snapshot.livelihoods.clearing_protection.receipts``). */
export interface ProtectionReceipt {
  region_id: number; payer: number; new: boolean;
  cover_before: number; cover_after: number;
  /** The planning saw the population above the clearing threshold, so a warden bill was due. */
  pressure_planned: boolean;
  required: number;
  /** The L9 envelope cap; null without local budgets. */
  envelope: number | null;
  paid_planned: number;
  /** Funded share: protection x paid / warden cost. */
  p_planned: number;
  /** What the ecology tick received (0 in the cost-only control). */
  p_applied: number;
  /** The authoritative ecology receipt: population-driven clearing fired. */
  clearing_active: boolean;
  cover_not_cleared: number;
  /** What the paid share keeps from an active clearing (equals cover_not_cleared when enforced). */
  cover_would_keep: number;
  /** Paid only for region-turns whose clearing was active. */
  charged: number;
  timber_capacity_kept: number | null;
  source: "native" | "python";
}
export type UnprotectedReason = "over_limit" | "unaffordable" | "not_forested" | "not_planned";
/** A controlled region under pressure, or clearing, without protection this turn. */
export interface UnprotectedRegion {
  region_id: number; controller: number; reason: UnprotectedReason;
  pressure_planned: boolean; clearing_active: boolean;
  cover_before: number; cover_after: number;
  /** Cover the tick's clearing removed (nominal); 0 when it did not fire. */
  cleared: number;
}
export type EndReason = "controller_changed" | "uncontrolled" | "cover_lost" | "idle" | "unfunded";
export interface ProtectionDecision {
  turn: number; region_id: number; civ: number; kind: "adopted" | "ended"; reason: "clearing_pressure" | EndReason;
}
export interface Protection {
  region_id: number; payer: number; adopted_turn: number; idle_turns: number; unfunded_turns: number;
  active_turns: number; charged: number; cover_not_cleared: number;
}
export interface ClearingProtectionRecord {
  schema_version: 1; units: { cover: "forest_cover"; money: "treasury" }; mode: "enforced" | "cost_only";
  source_turn: number; completed_turn: number;
  parameters: Record<string, number>;
  /** False: no Phase 9 was settled in the source turn; the turn's accounts are unknown, not empty. */
  observed: boolean;
  receipts: ProtectionReceipt[] | null;
  /** Null when unobserved; undefined in a record written before the field existed (unknown). */
  unprotected?: UnprotectedRegion[] | null;
  decisions: ProtectionDecision[] | null;
  protections: Protection[];
  counters: Record<string, number>;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const integer = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const share = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const bool = (x: unknown): x is boolean => typeof x === "boolean";
const PARAMETERS = ["max_regions", "warden_cost", "protection", "min_cover", "idle_limit", "unfunded_limit"] as const;
export const END_REASONS: readonly EndReason[] = ["controller_changed", "uncontrolled", "cover_lost", "idle", "unfunded"];
const UNPROTECTED: readonly UnprotectedReason[] = ["over_limit", "unaffordable", "not_forested", "not_planned"];
/** float32 (native) against float64 (Python) receipts of one nominal clearing. */
const TOLERANCE = 1e-6;

function validReceipt(x: unknown, regionCount: number, mode: string, p: Record<string, number>): x is ProtectionReceipt {
  if (!object(x) || !integer(x.region_id) || x.region_id >= regionCount || !integer(x.payer) || !bool(x.new)
    || !share(x.cover_before) || !share(x.cover_after) || !bool(x.pressure_planned) || !integer(x.required)
    || !(x.envelope === null || integer(x.envelope)) || !integer(x.paid_planned) || !share(x.p_planned)
    || !share(x.p_applied) || !bool(x.clearing_active) || !amount(x.cover_not_cleared) || !amount(x.cover_would_keep)
    || !integer(x.charged) || !(x.timber_capacity_kept === null || amount(x.timber_capacity_kept))
    || (x.source !== "native" && x.source !== "python")) return false;
  const r = x as unknown as ProtectionReceipt;
  if (r.required !== (r.pressure_planned ? p.warden_cost : 0) || r.paid_planned > r.required) return false;
  if (r.envelope !== null && r.paid_planned > r.envelope) return false;
  const funded = r.required ? p.protection * r.paid_planned / p.warden_cost : 0;
  if (Math.abs(r.p_planned - funded) > 1e-9) return false;
  if (r.p_applied !== (mode === "enforced" ? r.p_planned : 0)) return false;
  if (r.charged !== (r.clearing_active ? r.paid_planned : 0)) return false;
  if (!r.clearing_active && (r.cover_not_cleared !== 0 || r.cover_would_keep !== 0)) return false;
  if (mode === "cost_only" ? r.cover_not_cleared !== 0 : Math.abs(r.cover_not_cleared - r.cover_would_keep) > TOLERANCE) return false;
  return !(r.new && !r.pressure_planned);
}

function validUnprotected(x: unknown, regionCount: number): x is UnprotectedRegion {
  if (!object(x) || !integer(x.region_id) || x.region_id >= regionCount || !integer(x.controller)
    || !UNPROTECTED.includes(x.reason as UnprotectedReason) || !bool(x.pressure_planned) || !bool(x.clearing_active)
    || !share(x.cover_before) || !share(x.cover_after) || !amount(x.cleared)) return false;
  if ((x.reason === "not_planned") === x.pressure_planned) return false;
  if (!x.pressure_planned && !x.clearing_active) return false;
  return x.clearing_active || x.cleared === 0;
}

function validDecision(x: unknown, regionCount: number, turn: number): x is ProtectionDecision {
  if (!object(x) || x.turn !== turn || !integer(x.region_id) || x.region_id >= regionCount
    || !finite(x.civ) || !Number.isInteger(x.civ) || x.civ < -1) return false;
  if (x.kind === "adopted") return x.reason === "clearing_pressure" && x.civ >= 0;
  return x.kind === "ended" && END_REASONS.includes(x.reason as EndReason);
}

function validProtection(x: unknown, regionCount: number, completed: number): x is Protection {
  return object(x) && integer(x.region_id) && x.region_id < regionCount && integer(x.payer) && integer(x.adopted_turn)
    && x.adopted_turn < completed && [x.idle_turns, x.unfunded_turns, x.active_turns, x.charged].every(integer)
    && amount(x.cover_not_cleared);
}

const unique = (rows: Array<{ region_id: number }>) => new Set(rows.map((r) => r.region_id)).size === rows.length;

/**
 * Strict reader of the selected snapshot's clearing protection record: null
 * when absent (an older bundle or the switch off), from another schema, dated
 * to another snapshot or malformed. Never borrows values from other snapshots.
 */
export function clearingProtectionAt(snapshot: TurnSnapshot | null, regionCount: number): ClearingProtectionRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.clearing_protection;
  if (!object(x) || x.schema_version !== 1 || !object(x.units) || x.units.cover !== "forest_cover" || x.units.money !== "treasury"
    || (x.mode !== "enforced" && x.mode !== "cost_only") || !integer(x.source_turn) || !integer(x.completed_turn)
    || x.completed_turn !== x.source_turn + 1 || x.completed_turn !== snapshot?.turn || !bool(x.observed)
    || !object(x.parameters) || !Object.values(x.parameters).every(amount)
    || !PARAMETERS.every((key) => amount((x.parameters as Record<string, unknown>)[key]))
    || !integer((x.parameters as Record<string, unknown>).warden_cost) || (x.parameters.warden_cost as number) < 1
    || !share((x.parameters as Record<string, unknown>).protection)
    || !object(x.counters) || !Object.values(x.counters).every(amount) || !Array.isArray(x.protections)) return null;
  const completed = x.completed_turn;
  const protections = x.protections;
  if (!protections.every((p) => validProtection(p, regionCount, completed)) || !unique(protections as Protection[])) return null;
  const held = protections as Protection[];
  if (held.length > 0 && Math.max(...Object.values(
    held.reduce<Record<number, number>>((n, p) => ({ ...n, [p.payer]: (n[p.payer] ?? 0) + 1 }), {}))) > (x.parameters.max_regions as number)) return null;
  if (!x.observed) {
    return x.receipts === null && x.decisions === null && (x.unprotected === null || x.unprotected === undefined)
      ? x as unknown as ClearingProtectionRecord : null;
  }
  if (!Array.isArray(x.receipts) || !Array.isArray(x.decisions)) return null;
  const params = x.parameters as Record<string, number>;
  if (!x.receipts.every((r) => validReceipt(r, regionCount, x.mode as string, params)) || !unique(x.receipts as ProtectionReceipt[])) return null;
  if (!x.decisions.every((d) => validDecision(d, regionCount, x.source_turn as number))) return null;
  const receipts = x.receipts as ProtectionReceipt[];
  // The completed turn's protections are exactly the receipts' (same payer);
  // a new receipt has its adoption decision.
  const byRegion = new Map(held.map((p) => [p.region_id, p]));
  if (receipts.length !== held.length || !receipts.every((r) => byRegion.get(r.region_id)?.payer === r.payer)) return null;
  const adopted = new Set((x.decisions as ProtectionDecision[]).filter((d) => d.kind === "adopted").map((d) => d.region_id));
  if (!receipts.every((r) => r.new === adopted.has(r.region_id)) || adopted.size !== receipts.filter((r) => r.new).length) return null;
  if (x.unprotected !== undefined) {
    if (!Array.isArray(x.unprotected) || !x.unprotected.every((u) => validUnprotected(u, regionCount))
      || !unique(x.unprotected as UnprotectedRegion[])
      || (x.unprotected as UnprotectedRegion[]).some((u) => byRegion.has(u.region_id))) return null;
  }
  return x as unknown as ClearingProtectionRecord;
}

/** This turn's cover kept and lost, and its bills; null components are unknown, never zero. */
export interface ClearingSummary {
  kept: number; wouldKeep: number;
  /** Cover cleared in protected regions whose protection was not fully paid; null without the clearing rate. */
  clearedProtected: number | null;
  /** Cover cleared in unprotected controlled regions; null when the record does not list them. */
  clearedElsewhere: number | null;
  required: number; paid: number; charged: number; underfunded: number;
}

export function clearingSummary(record: ClearingProtectionRecord): ClearingSummary | null {
  if (!record.observed || !record.receipts) return null;
  const rows = record.receipts;
  const sum = (values: number[]) => values.reduce((a, b) => a + b, 0);
  const rate = record.parameters.forest_clearing;
  return {
    kept: sum(rows.map((r) => r.cover_not_cleared)),
    wouldKeep: sum(rows.map((r) => r.cover_would_keep)),
    clearedProtected: finite(rate) ? sum(rows.filter((r) => r.clearing_active).map((r) => {
      const lost = rate - r.cover_not_cleared;            // float32 receipts: ignore rounding residue
      return lost > TOLERANCE ? lost : 0;
    })) : null,
    clearedElsewhere: Array.isArray(record.unprotected) ? sum(record.unprotected.map((u) => u.cleared)) : null,
    required: sum(rows.map((r) => r.required)),
    paid: sum(rows.map((r) => r.paid_planned)),
    charged: sum(rows.map((r) => r.charged)),
    underfunded: rows.filter((r) => r.paid_planned < r.required).length,
  };
}

/** Funding of one protected region-turn, as text. */
export function fundingLabel(row: ProtectionReceipt): string {
  if (row.required === 0) return "Not due (no pressure)";
  if (row.paid_planned >= row.required) return "Full";
  return row.paid_planned === 0 ? "Unfunded" : `Partial (${row.paid_planned} of ${row.required})`;
}
