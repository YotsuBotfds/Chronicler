import { isRecord as object, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/**
 * Reader of the X1 residence ledger (`snapshot.livelihoods.residence_ledger`,
 * `--residence-ledger`; Python reference `chronicler.residence_ledger.record_status`).
 * Types live here, not in the pinned `types.ts`. Panels read it through
 * `recordReading.ts` (`readResidenceLedger`), which keeps disabled, absent,
 * malformed, unobserved, recorded-zero and recorded apart.
 *
 * A frame holds the completed turn's aggregates: open displacement spells by
 * residence region, cause and home-region anchor, and by origin; this turn's
 * departures and arrivals by driver group; spell openings and closures; people
 * on army rosters by home region (and those whose army is elsewhere); merchants
 * in transit. `events` are the turn's spell openings and closures by stable id
 * (bounded). Zeros inside an observed frame are recorded zeros; history before
 * `observed_from` is unknown, not zero. Never reads final-world state.
 */
export const CAUSES = ["flight", "hunger"] as const;
const ANCHORS = ["war", "famine", "persecution", "none"] as const;
/** Optional physical-arrival diagnostics added after the original X1 records. */
const ARRIVAL_COUNT_KEYS = ["recent_residence_arrivals", "recent_residence_arrivals_unknown_reason"] as const;
const CLOSURES = ["returned", "resettled", "died", "pool_reset", "unobserved_gap"] as const;
/** ``residence_ledger_state.REGION_KEYS`` (declaration order). */
const REGION_KEYS = [
  "region", "residents",
  "displaced", "displaced_flight", "displaced_hunger",
  "displaced_war", "displaced_famine", "displaced_persecution", "displaced_none",
  "displaced_from",
  "arrivals", "arrivals_displaced",
  "departures", "departures_flight", "departures_hunger", "departures_voluntary", "departures_other",
  "opened", "returned", "resettled", "died_displaced", "deaths",
  "attached", "attached_away", "in_transit",
  // Review M1 (appended): arrivals and departures by cause and anchor.
  "opened_flight", "opened_hunger",
  "opened_war", "opened_famine", "opened_persecution", "opened_none",
  "returned_war", "returned_famine", "returned_persecution", "returned_none",
  "displaced_from_war", "displaced_from_famine", "displaced_from_persecution", "displaced_from_none",
  "arrivals_flight", "arrivals_hunger", "arrivals_voluntary", "arrivals_other",
  "arrivals_displaced_war", "arrivals_displaced_famine", "arrivals_displaced_persecution", "arrivals_displaced_none",
] as const;
/** ``residence_ledger_state.TOTAL_KEYS`` (declaration order). */
export const TOTAL_KEYS = [
  "alive", "observed", "deferred",
  "displaced", "displaced_flight", "displaced_hunger",
  "displaced_war", "displaced_famine", "displaced_persecution", "displaced_none",
  "anchor_any_war", "anchor_any_famine", "anchor_any_persecution", "anchor_war_or_famine", "anchor_partial",
  "moves", "moves_flight", "moves_hunger", "moves_voluntary", "moves_other",
  "opened", "returned", "resettled", "died", "pool_reset", "unobserved_gap", "rehomed", "deaths",
  "attached", "attached_away", "in_transit",
  "new_rows", "newborn_rows", "trip_relocations", "unexplained_relocations", "move_origin_mismatches",
  "recent_movers_native", "away_from_birth_region",
  "opened_flight", "opened_hunger",
  "opened_war", "opened_famine", "opened_persecution", "opened_none",
  "returned_war", "returned_famine", "returned_persecution", "returned_none",
  "displaced_from_war", "displaced_from_famine", "displaced_from_persecution", "displaced_from_none",
  "arrivals_flight", "arrivals_hunger", "arrivals_voluntary", "arrivals_other",
  "arrivals_displaced_war", "arrivals_displaced_famine", "arrivals_displaced_persecution", "arrivals_displaced_none",
  "invalid_moves",
] as const;
/** Totals that are all zero in a recorded-zero frame (``residence_ledger._ZERO_KEYS``). */
const ZERO_KEYS = ["displaced", "attached", "moves", "opened", ...CLOSURES, "deaths"] as const;

export type Cause = (typeof CAUSES)[number];
export type Anchor = (typeof ANCHORS)[number];
export type Closure = (typeof CLOSURES)[number];
export type RegionKey = (typeof REGION_KEYS)[number];
export type TotalKey = (typeof TOTAL_KEYS)[number];
export type ResidenceRegionRow = Record<RegionKey, number> & Partial<Record<typeof ARRIVAL_COUNT_KEYS[number], number>>;
export type ResidenceTotals = Record<TotalKey, number> & Partial<Record<typeof ARRIVAL_COUNT_KEYS[number], number>>;
export interface ArrivalDiagnostics {
  window_turns: 20; coverage_complete: boolean; window_complete: boolean; complete: boolean;
}

export interface ResidenceFrame {
  turn: number;
  observed_from: number;
  totals: ResidenceTotals;
  regions: ResidenceRegionRow[];
  arrival_diagnostics?: ArrivalDiagnostics;
}

export interface SpellEvent {
  id: number; kind: "opened" | Closure; turn: number; region: number;
  start: number; origin: number; cause: Cause; anchor: Anchor; length: number;
  /** The opening move's native driver code (kept across onward moves); null: no driver. */
  driver: number | null;
  /** Not an applied migration (a trip that ended away from home, or unexplained). */
  relocation?: boolean;
}

export interface ResidenceLedgerRecord {
  schema_version: 1; stage: "X1"; source_turn: number; observed_from: number | null;
  frame: ResidenceFrame | null; events: SpellEvent[] | null; events_dropped: number;
  counters: Record<string, number>;
  log: { turn: number; kind: string; detail: Record<string, unknown> }[]; log_dropped: number;
  labels: Record<string, string>; parameters: Record<string, unknown>;
}

const among = <T extends string>(values: readonly T[], x: unknown): x is T => values.includes(x as T);

function validRegion(r: unknown, regions: number): boolean {
  return object(r) && REGION_KEYS.every((k) => count(r[k])) && (r.region as number) < regions;
}

function validEvent(e: unknown, regions: number, source: number): boolean {
  if (!object(e)) return false;
  const kinds = ["opened", ...CLOSURES];
  return count(e.id) && among(kinds, e.kind) && e.turn === source && count(e.region) && e.region < regions
    && count(e.start) && e.start <= source && count(e.origin) && e.origin < regions && among(CAUSES, e.cause)
    && among(ANCHORS, e.anchor) && e.length === source - (e.start as number)
    && (e.driver === null || count(e.driver))
    && (e.relocation === undefined || e.relocation === true);
}

function validFrame(f: unknown, regions: number, source: number): f is ResidenceFrame {
  if (!object(f) || f.turn !== source || !count(f.observed_from) || f.observed_from > source) return false;
  const t = f.totals;
  if (!object(t) || !TOTAL_KEYS.every((k) => count(t[k]))) return false;
  if (!Array.isArray(f.regions) || !f.regions.every((r) => validRegion(r, regions))) return false;
  const rows = f.regions as ResidenceRegionRow[];
  if (new Set(rows.map((r) => r.region)).size !== rows.length) return false;
  const sum = (key: RegionKey) => rows.reduce((a, r) => a + r[key], 0);
  const totals = t as ResidenceTotals;
  const arrival = f.arrival_diagnostics;
  const hasArrivalCounts = ARRIVAL_COUNT_KEYS.some(k => t[k] !== undefined || rows.some(r => r[k] !== undefined));
  if (arrival !== undefined || hasArrivalCounts) {
    if (!object(arrival) || arrival.window_turns !== 20
      || ![arrival.coverage_complete, arrival.window_complete, arrival.complete].every(v => typeof v === "boolean")
      || arrival.complete !== (arrival.coverage_complete && arrival.window_complete)
      || !ARRIVAL_COUNT_KEYS.every(k => count(t[k]) && rows.every(r => count(r[k])))) return false;
    const [arrived, unknown] = ARRIVAL_COUNT_KEYS;
    if (Number(t[unknown]) > Number(t[arrived]) || Number(t[arrived]) > totals.observed
      || rows.some(r => Number(r[unknown]) > Number(r[arrived]) || Number(r[arrived]) > r.residents)
      || !ARRIVAL_COUNT_KEYS.every(k => rows.reduce((n,r) => n + Number(r[k]), 0) === t[k])) return false;
  }
  // Region rows add up to the world totals they share.
  return sum("residents") === totals.observed && sum("displaced") === totals.displaced
    && sum("displaced_from") === totals.displaced && sum("departures") === totals.moves
    && sum("arrivals") === totals.moves && sum("opened") === totals.opened && sum("attached") === totals.attached
    && totals.displaced_flight + totals.displaced_hunger === totals.displaced
    && ANCHORS.reduce((a, k) => a + totals[`displaced_${k}`], 0) === totals.displaced;
}

/** The residence ledger record of one snapshot, or null when it is absent or malformed. */
export function residenceLedgerAt(snapshot: TurnSnapshot | null, regions: number): ResidenceLedgerRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.residence_ledger;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "X1" || !count(x.source_turn)
    || x.source_turn + 1 !== snapshot?.turn || !object(x.counters) || !Object.values(x.counters).every(count)
    || !Array.isArray(x.log) || !count(x.log_dropped) || !object(x.labels) || !object(x.parameters)
    || !count(x.events_dropped) || !(x.observed_from === null || count(x.observed_from))) return null;
  const source = x.source_turn as number;
  if (x.frame === null) return x.events === null ? x as unknown as ResidenceLedgerRecord : null;
  if (!validFrame(x.frame, regions, source) || x.frame.observed_from !== x.observed_from) return null;
  if (!Array.isArray(x.events) || !x.events.every((e) => validEvent(e, regions, source))) return null;
  const events = x.events as SpellEvent[];
  const totals = x.frame.totals;
  if (x.events_dropped === 0 && (events.filter((e) => e.kind === "opened").length !== totals.opened
    || CLOSURES.some((c) => events.filter((e) => e.kind === c).length !== totals[c]))) return null;
  return x as unknown as ResidenceLedgerRecord;
}

/** Whether an observed frame records nothing: no one displaced or attached, no move, opening, closure or death. */
export function residenceZero(frame: ResidenceFrame): boolean {
  return ZERO_KEYS.every((k) => frame.totals[k] === 0)
    && !(frame.arrival_diagnostics && Number(frame.totals.recent_residence_arrivals) > 0);
}

/** Whether any snapshot of the run carries a residence ledger record. */
export function residenceLedgerOn(history: readonly TurnSnapshot[] | undefined): boolean {
  return (history ?? []).some((s) => {
    const lh = (s as unknown as Record<string, unknown> | null)?.livelihoods;
    return object(lh) && lh.residence_ledger !== undefined && lh.residence_ledger !== null;
  });
}

/** A share as a percentage with one decimal, or "Unknown" without a denominator. */
export function percent(part: number, whole: number): string {
  return whole > 0 ? `${((100 * part) / whole).toFixed(1)}%` : "Unknown";
}
