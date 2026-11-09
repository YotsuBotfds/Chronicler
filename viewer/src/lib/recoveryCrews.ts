import { isRecord as object, finite, amount, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

export type CrewOrigin = "site_city" | "urban_farmer" | "rural_farmer" | "veteran";

/** One named crew member's completed turn (milli-units of money). */
export interface CrewMemberRecord {
  agent_id: number; origin: CrewOrigin;
  /** Share of the person's turn reserved for the repair. */
  share: number;
  /** Share worked and withheld from ordinary income. */
  worked: number;
  /** Farm labour removed for this person (farmer-equivalents). */
  farm_time: number; veteran: boolean;
  wage_due_milli: number; wage_milli: number; wage_residual_milli: number;
  /** Null: not observed (unknown, not zero). */
  income_replaced: number | null;
}

/** One RS2 project's named crew (``livelihoods.recovery_crews.receipts``). */
export interface CrewReceiptRecord {
  turn: number; pid: number; kind: "granary" | "workshop"; region: number; payer: number;
  eligible: number; eligible_site_city: number | null;
  planned: number; capacity: number; requested: number; delivered: number;
  members: CrewMemberRecord[];
  /** Granary: the coins RS2 charged for the delivered work; wages reach the crew, the rest is sunk. */
  coin_cost_milli: number; wages_due_milli: number; wages_milli: number; wage_residual_milli: number;
  sunk_milli: number; farm_time_removed: number;
  /** Granary (PL3 review C): the free adult farmers ran out with at least ``min_share`` of the planned work left.
   * Absent in records written before it. */
  short?: boolean;
}

export interface CrewLedgerRecord {
  turn: number; civ: number; coin_cost_milli: number; wages_due_milli: number; wages_milli: number;
  wage_residual_milli: number; sunk_milli: number;
}

export interface RecoveryCrewsRecord {
  schema_version: 1; stage: "PL3"; mode: "paid" | "unpaid"; source_turn: number;
  units: Record<string, string | number>;
  /** Null: no settled Phase 2 in the source turn (unknown, not zero). */
  receipts: CrewReceiptRecord[] | null;
  ledger: CrewLedgerRecord[] | null;
  /** Receipts beyond the frame bound, dropped over the run. */
  rows_dropped: number;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

export type RecoveryCrewsReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: RecoveryCrewsRecord };

const unit = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1 + 1e-9;
const EPS = 1e-6;
const ORIGINS: readonly CrewOrigin[] = ["site_city", "urban_farmer", "rural_farmer", "veteran"];
const MODES = ["paid", "unpaid"];
const MAX_CREW = 4;

function memberProblem(x: unknown): string | null {
  if (!object(x) || !count(x.agent_id) || !ORIGINS.includes(x.origin as CrewOrigin) || !unit(x.share)
    || !amount(x.worked) || !amount(x.farm_time) || typeof x.veteran !== "boolean" || !count(x.wage_due_milli)
    || !count(x.wage_milli) || !count(x.wage_residual_milli) || !(x.income_replaced === null || amount(x.income_replaced)))
    return "malformed crew member";
  const r = x as unknown as CrewMemberRecord;
  if (r.worked > r.share + 1e-9) return "a member worked beyond the reservation";
  if (r.wage_milli + r.wage_residual_milli !== r.wage_due_milli) return "a member's wage does not close";
  return null;
}

function receiptProblem(x: unknown, regions: number, civs: number, source: number, mode: string,
  minShare: number): string | null {
  if (!object(x) || x.turn !== source || !count(x.pid) || (x.kind !== "granary" && x.kind !== "workshop")
    || !count(x.region) || x.region >= regions || !count(x.payer) || x.payer >= civs || !count(x.eligible)
    || ![x.planned, x.capacity, x.requested, x.delivered, x.farm_time_removed].every(amount)
    || ![x.coin_cost_milli, x.wages_due_milli, x.wages_milli, x.wage_residual_milli].every(count)
    || !finite(x.sunk_milli) || !Array.isArray(x.members)) return "malformed crew receipt";
  const r = x as unknown as CrewReceiptRecord;
  for (const m of r.members) {
    const why = memberProblem(m);
    if (why) return why;
  }
  const members = r.members as CrewMemberRecord[];
  if (new Set(members.map((m) => m.agent_id)).size !== members.length) return "a person is twice on one crew";
  const sum = (f: (m: CrewMemberRecord) => number) => members.reduce((a, m) => a + f(m), 0);
  if (r.wages_milli + r.wage_residual_milli !== r.wages_due_milli) return "crew wages do not close";
  if (sum((m) => m.wage_milli) !== r.wages_milli || sum((m) => m.wage_residual_milli) !== r.wage_residual_milli
    || sum((m) => m.wage_due_milli) !== r.wages_due_milli) return "member wages do not add up to the crew's";
  if (r.kind === "granary") {
    if (r.eligible_site_city !== null) return "malformed crew receipt";
    if (members.some((m) => m.origin !== "rural_farmer" && m.origin !== "urban_farmer"))
      return "a granary crew member is not a farmer";
    if (r.coin_cost_milli !== r.wages_milli + r.sunk_milli || r.sunk_milli < 0) return "granary coins do not close";
    if (mode === "unpaid" && r.wages_due_milli !== 0) return "an unpaid crew was paid";
    if (mode === "paid" && r.delivered > 0 && r.wages_due_milli !== r.coin_cost_milli)
      return "a paid crew was not paid the granary's coins";
    if (r.delivered > r.requested + EPS || r.requested > r.planned + EPS || r.requested > r.capacity + 1e-5)
      return "granary work beyond its request";
    if (sum((m) => m.worked) > r.requested + 1e-5) return "a granary crew worked beyond its request";
    if (!members.every((m) => Math.abs(m.farm_time - m.worked) <= EPS)) return "farm time is not the work done";
    if (Math.abs(r.farm_time_removed - r.delivered) > EPS * Math.max(1, r.delivered)) return "farm time does not close";
    if (r.short !== undefined) {
      const left = r.planned - r.capacity;
      if (typeof r.short !== "boolean" || (r.short ? left < minShare - EPS : left >= minShare + EPS))
        return "the shortage flag disagrees with the planned work and the crew";
    }
  } else {
    if (!count(r.eligible_site_city) || r.eligible_site_city > r.eligible) return "malformed workshop pool";
    if (members.length > MAX_CREW) return "a workshop crew beyond its size";
    if (r.coin_cost_milli !== 0 || r.wages_due_milli !== 0 || r.sunk_milli !== 0)
      return "workshop crew money belongs to the RS2 receipt";
    if (members.some((m) => (m.origin === "site_city" || m.origin === "veteran") && m.farm_time !== 0))
      return "farm time removed for time already off the farm";
    if (Math.abs(r.farm_time_removed - sum((m) => m.farm_time)) > EPS) return "farm time does not close";
    if (r.short !== undefined && r.short !== false) return "a workshop crew marked short";
  }
  return null;
}

function ledgerProblem(x: unknown, civs: number, source: number): string | null {
  if (!object(x) || x.turn !== source || !count(x.civ) || x.civ >= civs
    || ![x.coin_cost_milli, x.wages_due_milli, x.wages_milli, x.wage_residual_milli, x.sunk_milli].every(count))
    return "malformed crew ledger";
  const r = x as unknown as CrewLedgerRecord;
  if (r.coin_cost_milli !== r.wages_milli + r.sunk_milli) return "a civ's granary coins do not close";
  if (r.wages_milli + r.wage_residual_milli !== r.wages_due_milli) return "a civ's crew wages do not close";
  return null;
}

/** Strict reading: absent, malformed (with the reason) or a dated, closing record. */
export function readRecoveryCrews(snapshot: TurnSnapshot | null, regionCount: number, civCount: number): RecoveryCrewsReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.recovery_crews === undefined || livelihoods.recovery_crews === null)
    return { status: "absent" };
  const bad = (reason: string): RecoveryCrewsReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.recovery_crews;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "PL3" || !MODES.includes(x.mode as string))
    return bad("unknown recovery-crews schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  if (!object(x.units) || !count(x.rows_dropped) || !object(x.counters) || !Object.values(x.counters).every(amount)
    || !object(x.parameters) || !Object.values(x.parameters).every(finite)) return bad("malformed counters or parameters");
  const c = x.counters as Record<string, number>;
  const get = (k: string) => c[k] ?? 0;
  if (get("granary_coin_cost_milli") !== get("granary_wages_milli") + get("granary_sunk_milli")
    || get("granary_wages_milli") + get("granary_wage_residual_milli") !== get("granary_wages_due_milli"))
    return bad("lifetime granary money does not close");
  if (x.mode === "unpaid" && get("granary_wages_due_milli") !== 0) return bad("the unpaid control paid wages");
  if ((x.receipts === null) !== (x.ledger === null)) return bad("receipts without accounts");
  if (x.receipts !== null) {
    const max = (x.parameters as Record<string, number>).max_frame_rows ?? 64;
    if (!Array.isArray(x.receipts) || x.receipts.length > max || !Array.isArray(x.ledger)) return bad("malformed receipts");
    for (const r of x.receipts) {
      const why = receiptProblem(r, regionCount, civCount, x.source_turn, x.mode as string,
        (x.parameters as Record<string, number>).min_share ?? 0.001);
      if (why) return bad(why);
    }
    for (const l of x.ledger) {
      const why = ledgerProblem(l, civCount, x.source_turn);
      if (why) return bad(why);
    }
    const receipts = x.receipts as CrewReceiptRecord[];
    const ledger = x.ledger as CrewLedgerRecord[];
    const people = receipts.flatMap((r) => r.members.map((m) => m.agent_id));
    if (new Set(people).size !== people.length) return bad("a person is on two crews");
    if (new Set(receipts.map((r) => r.pid)).size !== receipts.length) return bad("a project has two crew receipts");
    if (new Set(ledger.map((l) => l.civ)).size !== ledger.length) return bad("a civ has two crew ledgers");
    if (receipts.length < max) {
      // An unbounded frame: each civ's ledger is the sum of its granary crews.
      const granary = receipts.filter((r) => r.kind === "granary");
      const payers = new Set(granary.map((r) => r.payer));
      if (payers.size !== ledger.length || !ledger.every((l) => payers.has(l.civ))) return bad("crew ledger and receipts disagree");
      for (const l of ledger) {
        const mine = granary.filter((r) => r.payer === l.civ);
        const total = (f: (r: CrewReceiptRecord) => number) => mine.reduce((a, r) => a + f(r), 0);
        if (total((r) => r.coin_cost_milli) !== l.coin_cost_milli || total((r) => r.wages_milli) !== l.wages_milli
          || total((r) => r.wages_due_milli) !== l.wages_due_milli || total((r) => r.sunk_milli) !== l.sunk_milli
          || total((r) => r.wage_residual_milli) !== l.wage_residual_milli) return bad("crew ledger and receipts disagree");
      }
    }
  }
  return { status: "ok", record: x as unknown as RecoveryCrewsRecord };
}

/** A granary crew short of the planned work (the recorded flag; before it, any shortfall with a crew named). */
export function isShort(r: CrewReceiptRecord): boolean {
  if (r.kind !== "granary") return false;
  return r.short ?? (r.members.length > 0 && r.requested + EPS < r.planned);
}

/** This turn's granary money and crew sizes; null when the turn is unknown. */
export function crewTotals(record: RecoveryCrewsRecord): {
  coins: number; wages: number; sunk: number; residual: number; withheld: number | null;
  granaryCrews: number; workshopCrews: number; people: number; farmTime: number; short: number; empty: number;
} | null {
  if (record.receipts === null || record.ledger === null) return null;
  const rows = record.receipts;
  const members = rows.flatMap((r) => r.members);
  const income = members.map((m) => m.income_replaced);
  return {
    coins: record.ledger.reduce((a, l) => a + l.coin_cost_milli, 0),
    wages: record.ledger.reduce((a, l) => a + l.wages_milli, 0),
    sunk: record.ledger.reduce((a, l) => a + l.sunk_milli, 0),
    residual: record.ledger.reduce((a, l) => a + l.wage_residual_milli, 0),
    withheld: income.some((v) => v === null) ? null : income.reduce<number>((a, v) => a + (v as number), 0),
    granaryCrews: rows.filter((r) => r.kind === "granary").length,
    workshopCrews: rows.filter((r) => r.kind === "workshop").length,
    people: members.length,
    farmTime: rows.reduce((a, r) => a + r.farm_time_removed, 0),
    short: rows.filter(isShort).length,
    empty: rows.filter((r) => r.kind === "granary" && r.members.length === 0).length,
  };
}
