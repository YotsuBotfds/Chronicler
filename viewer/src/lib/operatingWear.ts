import type { TurnSnapshot } from "../types";

/** One funded operating site's wear in a completed turn (``livelihoods.operating_wear.receipts``). */
export interface WearReceiptRecord {
  turn: number; site: number; region: number;
  /** The declared wear, the qualified crew's upkeep offset (RS1; 0 without it) and their difference. */
  wear: number; upkeep_offset: number; net_wear: number;
  condition_before: number; condition_after: number;
  /** Qualified members of the turn's crew (RS1; [] without it). */
  qualified_on_crew: number[];
  full_offset: boolean;
}

export interface OperatingWearRecord {
  schema_version: 1; stage: "PL2"; source_turn: number;
  /** Null: no completed Phase 2 in the source turn (unknown, not zero). */
  receipts: WearReceiptRecord[] | null;
  /** Lifetime counters; a key appears once it was first counted. */
  counters: Record<string, number>;
  parameters: { operating_wear: number };
  /** RS1 applies the same wear itself; the switch then only records it. */
  with_apprenticeship: boolean;
}

export type OperatingWearReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: OperatingWearRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const unit = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const ids = (x: unknown, max: number): x is number[] => Array.isArray(x) && x.length <= max && x.every(count)
  && new Set(x).size === x.length;
const near = (a: number, b: number) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
/** The fixed counter key set (``operating_wear_state.COUNTERS``). */
export const COUNTERS = ["turns", "operating_site_turns", "wear", "upkeep_offset", "net_wear",
  "full_offset_site_turns", "covered_site_turns", "repairs"] as const;
const MAX_SITES = 64;

function receiptProblem(x: unknown, regions: number, source: number, gross: number, rs1: boolean): string | null {
  if (!object(x) || x.turn !== source || !count(x.site) || !count(x.region) || x.region >= regions
    || !amount(x.wear) || !amount(x.upkeep_offset) || !amount(x.net_wear) || !unit(x.condition_before)
    || !unit(x.condition_after) || !ids(x.qualified_on_crew, 8) || typeof x.full_offset !== "boolean")
    return "malformed wear receipt";
  if (x.wear !== gross) return "a receipt's wear is not the declared operating wear";
  if (x.upkeep_offset > x.wear + 1e-12 || !near(x.net_wear, Math.max(0, x.wear - x.upkeep_offset)))
    return "wear does not close";
  if (x.full_offset !== (x.net_wear === 0)) return "the full-offset flag disagrees with the net wear";
  if (!near(x.condition_after, Math.max(0, x.condition_before - x.net_wear))) return "condition does not close";
  if (!rs1 && (x.upkeep_offset !== 0 || x.qualified_on_crew.length > 0))
    return "an offset without apprenticeship (nobody else qualifies anyone)";
  return null;
}

/** Strict reading: absent, malformed (with the reason) or a dated, closing record. */
export function readOperatingWear(snapshot: TurnSnapshot | null, regionCount: number): OperatingWearReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.operating_wear === undefined || livelihoods.operating_wear === null)
    return { status: "absent" };
  const bad = (reason: string): OperatingWearReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.operating_wear;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "PL2") return bad("unknown operating-wear schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  if (!object(x.parameters) || !amount(x.parameters.operating_wear) || typeof x.with_apprenticeship !== "boolean")
    return bad("malformed parameters");
  const counters = x.counters;
  if (!object(counters) || !Object.entries(counters).every(([k, v]) => COUNTERS.includes(k as never) && amount(v))
    || ["turns", "operating_site_turns", "full_offset_site_turns", "covered_site_turns", "repairs"]
      .some((k) => counters[k] !== undefined && !count(counters[k]))) return bad("malformed counters");
  const c = counters as Record<string, number>;
  const get = (k: string) => c[k] ?? 0;
  if (Math.abs(get("wear") - get("upkeep_offset") - get("net_wear")) > 1e-6 * Math.max(1, get("wear")))
    return bad("lifetime wear does not close");
  if (get("full_offset_site_turns") > get("operating_site_turns") || get("covered_site_turns") > get("operating_site_turns"))
    return bad("lifetime site-turns do not add up");
  if (x.receipts !== null) {
    if (!Array.isArray(x.receipts) || x.receipts.length > MAX_SITES) return bad("malformed receipts");
    for (const r of x.receipts) {
      const why = receiptProblem(r, regionCount, x.source_turn, x.parameters.operating_wear as number, x.with_apprenticeship);
      if (why) return bad(why);
    }
    if (new Set(x.receipts.map((r) => (r as WearReceiptRecord).site)).size !== x.receipts.length)
      return bad("a site was worn twice in one turn");
  }
  return { status: "ok", record: x as unknown as OperatingWearRecord };
}

/** This turn's totals; null when the turn is unknown. */
export function wearTotals(record: OperatingWearRecord): { sites: number; wear: number; offset: number; net: number;
  fullOffset: number; covered: number; stopping: number } | null {
  const rows = record.receipts;
  if (rows === null) return null;
  const sum = (f: (r: WearReceiptRecord) => number) => rows.reduce((a, r) => a + f(r), 0);
  return { sites: rows.length, wear: sum((r) => r.wear), offset: sum((r) => r.upkeep_offset), net: sum((r) => r.net_wear),
    fullOffset: rows.filter((r) => r.full_offset).length, covered: rows.filter((r) => r.qualified_on_crew.length > 0).length,
    stopping: rows.filter((r) => r.condition_before >= 0.5 && r.condition_after < 0.5).length };
}
