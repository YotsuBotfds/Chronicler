import type { TurnSnapshot } from "../types";

/** One ruler's reservation, decided in Phase 10 of ``turn`` for the next turn (whole treasury units). */
export interface ReservationDecisionRecord {
  turn: number; civ: number;
  /** RS2's planned per-turn charges for the civ's open projects. */
  planned: number;
  /** The bargained budget the civ would have had without the reservation. */
  budget_before: number;
  /** The declared share of that budget the reservation may take. */
  cap: number;
  reserved: number;
}

/** One ruler's reservation in the turn it was for. */
export interface ReservationUseRecord {
  turn: number; civ: number; reserved: number;
  /** The bargained repairs envelope; null when none was awarded. */
  envelope: number | null;
  /** RS2's whole-unit charge to the civ, split between the reservation and the envelope pro rata to their amounts. */
  charged: number; used: number; returned: number; envelope_spent: number;
  /** The envelope's share of the delivered work, envelope / (reserved + envelope); 1 without a reservation in use.
   * Absent in records written before the pro-rata split (PL3 review C), which paid from the reservation first. */
  envelope_share?: number;
}

/** PL3 review C: the charge split pro rata, as ``maintenance_obligation.split_charge``. */
function splitCharge(charged: number, reserved: number, envelope: number): [number, number] {
  const whole = reserved + envelope;
  if (reserved <= 0 || whole <= 0) return [0, 1];
  return [Math.floor(charged * reserved / whole), envelope / whole];
}

export interface MaintenanceObligationRecord {
  schema_version: 1; stage: "PL3"; mode: "reserve" | "reserve_only"; source_turn: number;
  units: Record<string, string>;
  /** Null: nothing was decided (or settled) in the source turn (unknown, not zero). */
  decisions: ReservationDecisionRecord[] | null;
  uses: ReservationUseRecord[] | null;
  counters: Record<string, number>;
  parameters: { max_budget_share: number; group: string };
}

export type MaintenanceObligationReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: MaintenanceObligationRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const MODES = ["reserve", "reserve_only"];

function decisionProblem(x: unknown, civs: number, source: number, share: number): string | null {
  if (!object(x) || x.turn !== source || !count(x.civ) || x.civ >= civs
    || ![x.planned, x.budget_before, x.cap, x.reserved].every(count)) return "malformed decision";
  const r = x as unknown as ReservationDecisionRecord;
  if (r.cap !== Math.floor(share * r.budget_before + 1e-9)) return "the cap is not the declared share of the budget";
  if (r.reserved !== Math.min(r.planned, r.cap)) return "a reservation is not the planned charges within the cap";
  return null;
}

function useProblem(x: unknown, civs: number, source: number, mode: string): string | null {
  if (!object(x) || x.turn !== source || !count(x.civ) || x.civ >= civs
    || ![x.reserved, x.charged, x.used, x.returned, x.envelope_spent].every(count)
    || !(x.envelope === null || count(x.envelope))) return "malformed reservation use";
  const r = x as unknown as ReservationUseRecord;
  if (r.reserved !== r.used + r.returned) return "reserved is not used plus returned";
  if (r.used + r.envelope_spent !== r.charged) return "the charge is not the reservation's part plus the envelope's";
  if (r.envelope !== null && r.envelope_spent > r.envelope) return "repairs spent beyond their envelope";
  if (r.envelope_share !== undefined && !(finite(r.envelope_share) && r.envelope_share >= 0 && r.envelope_share <= 1))
    return "malformed reservation use";
  if (mode === "reserve_only") {
    return r.used === 0 && (r.envelope_share === undefined || r.envelope_share === 1)
      ? null : "the reserve-only control spent its reservation";
  }
  if (r.envelope_share === undefined) {
    // Written before the pro-rata split: the reservation paid first.
    return r.used === Math.min(r.charged, r.reserved) ? null : "the reservation was not spent first";
  }
  if (r.charged > r.reserved + (r.envelope ?? 0)) return "repairs charged beyond the reservation and envelope";
  const [used, share] = splitCharge(r.charged, r.reserved, r.envelope ?? 0);
  if (r.used !== used || Math.abs(r.envelope_share - share) > 1e-9) return "the charge is not split pro rata";
  return null;
}

/** Strict reading: absent, malformed (with the reason) or a dated, closing record. */
export function readMaintenanceObligation(snapshot: TurnSnapshot | null, civCount: number): MaintenanceObligationReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.maintenance_obligation === undefined || livelihoods.maintenance_obligation === null)
    return { status: "absent" };
  const bad = (reason: string): MaintenanceObligationReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.maintenance_obligation;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "PL3" || !MODES.includes(x.mode as string))
    return bad("unknown maintenance-obligation schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  if (!object(x.units) || !object(x.parameters) || !amount(x.parameters.max_budget_share) || x.parameters.max_budget_share > 1
    || typeof x.parameters.group !== "string") return bad("malformed parameters");
  if (!object(x.counters) || !Object.values(x.counters).every(amount)) return bad("malformed counters");
  const c = x.counters as Record<string, number>;
  const get = (k: string) => c[k] ?? 0;
  if (get("used_coins") + get("envelope_spent_coins") !== get("charged_coins")) return bad("lifetime charges do not close");
  if (x.mode === "reserve_only" && get("used_coins") !== 0) return bad("the reserve-only control spent its reservation");
  const share = x.parameters.max_budget_share as number;
  for (const [key, check] of [["decisions", (r: unknown) => decisionProblem(r, civCount, x.source_turn as number, share)],
    ["uses", (r: unknown) => useProblem(r, civCount, x.source_turn as number, x.mode as string)]] as const) {
    const rows = x[key];
    if (rows === null) continue;
    if (!Array.isArray(rows) || rows.length > civCount) return bad(`malformed ${key}`);
    for (const r of rows) {
      const why = check(r);
      if (why) return bad(why);
    }
    if (new Set(rows.map((r) => (r as { civ: number }).civ)).size !== rows.length) return bad(`a civ has two ${key}`);
  }
  return { status: "ok", record: x as unknown as MaintenanceObligationRecord };
}

/** This turn's reservation totals; null components are unknown. */
export function obligationTotals(record: MaintenanceObligationRecord): {
  planned: number | null; reserved: number | null; capped: number | null;
  used: number | null; returned: number | null; envelopeSpent: number | null; charged: number | null;
} {
  const d = record.decisions;
  const u = record.uses;
  const sum = <T,>(rows: T[] | null, f: (r: T) => number) => rows === null ? null : rows.reduce((a, r) => a + f(r), 0);
  return {
    planned: sum(d, (r) => r.planned), reserved: sum(d, (r) => r.reserved),
    capped: d === null ? null : d.filter((r) => r.planned > r.cap).length,
    used: sum(u, (r) => r.used), returned: sum(u, (r) => r.returned), envelopeSpent: sum(u, (r) => r.envelope_spent),
    charged: sum(u, (r) => r.charged),
  };
}
