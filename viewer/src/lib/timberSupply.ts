import type { TurnSnapshot } from "../types";

export type ExpeditionStage = "outbound" | "cutting" | "returning";

/** One woodcutting expedition (``livelihoods.timber_supply.expeditions`` and ``closed``).
 * Timber in goods, money in milli-units, labour in headcount. */
export interface ExpeditionRecord {
  eid: number; civ: number; home: number; forest: number; slot: number; hops: number; launched_turn: number;
  status: "live" | "delivered" | "abandoned"; stage: ExpeditionStage; stage_turns: number; travelled: number;
  return_hops: number; arrived: boolean; crew: number[]; launched_crew: number[]; veterans: number[];
  need: number; cargo: number; cut: number; cut_turns: number; cut_end: string | null; worked_turns: number;
  person_turns: number; wages_milli: number; wage_residual_milli: number; income_withheld: number;
  away_requested: number; away_delivered: number; delivered: number;
  /** Transit decay on the way home: the only loss. */
  lost: number;
  /** Cargo of an expedition that ended without delivering, deposited at the forest as commons. */
  abandoned: number;
  unpaid_turns: number; recalled_turn: number | null; ended_turn: number | null; end_reason: string | null;
  drops: Array<[number, number, string]>; history: Array<[number, string]>;
}

/** One expedition's completed Phase 2 (a turn its crew worked). */
export interface ExpeditionReceiptRecord {
  turn: number; eid: number; civ: number; home: number; forest: number; slot: number; stage: ExpeditionStage;
  crew: number[]; veterans: number[]; dropped: Array<[number, string]>;
  away_requested: number; away_delivered: number; crew_labor: number; cut: number; cargo_after: number;
  /** The forest slot's L3 account while cutting; null otherwise. */
  stock_before: number | null; stock_after: number | null; capacity: number | null;
  wages_due_milli: number; wages_milli: number; wage_residual_milli: number;
  /** Null: not observed (unknown, not zero). */
  income_withheld: number | null;
  cut_end: string | null; unpaid: boolean; recalled: boolean;
}

export interface TimberWageLedgerRecord {
  turn: number; civ: number; expeditions: number; person_turns: number; wages_due_milli: number;
  wages_applied_milli: number; wage_residual_milli: number; charged: number;
  prepaid_before_milli: number; prepaid_after_milli: number;
}

export interface TimberStoreRecord {
  region: number; opening: number; held: number; returned: number; delivered: number; released: number; closing: number;
}

export interface TimberNeedRecord {
  region: number; civ: number; want: number; free: number; store: number; in_transit: number; gap: number;
  status: "supplied" | "expedition" | "launched" | "refused"; reason: string | null; eid: number | null;
}

export interface PerExpeditionRecord {
  ended: number; wages_milli: number; person_turns: number; farm_labor_away: number; unpaid_turns: number;
  cut: number; delivered: number;
}

export interface TimberSupplyRecord {
  schema_version: 1; stage: "PL1"; mode: "supply" | "cost_only"; source_turn: number;
  units: Record<string, string | number>;
  expeditions: ExpeditionRecord[]; closed: ExpeditionRecord[];
  /** region index -> timber delivered and earmarked for repairs. */
  store: Record<string, number>;
  /** Null: no Phase 2 in the source turn (unknown, not zero). */
  receipts: ExpeditionReceiptRecord[] | null; ledger: TimberWageLedgerRecord[] | null;
  /** Null: the source turn's frame was not recorded (unknown, not zero). */
  stores: TimberStoreRecord[] | null; needs: TimberNeedRecord[] | null; needs_dropped: number | null;
  /** [turn, expedition, forest region, timber]: cargo deposited as commons in the source turn. */
  deposits: Array<[number, number, number, number]> | null;
  /** Means over ended expeditions; null before any ended. */
  per_expedition: PerExpeditionRecord | null;
  prepaid: Record<string, number>;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

export type TimberSupplyReading =
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; record: TimberSupplyRecord };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const ids = (x: unknown, max: number): x is number[] => Array.isArray(x) && x.length <= max && x.every(count)
  && new Set(x).size === x.length;
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown) => x === null || check(x);
const close = (a: number, b: number, scale = 1) => Math.abs(a - b) <= 1e-6 * Math.max(1, scale, Math.abs(a), Math.abs(b));
const subset = (a: number[], b: number[]) => a.every((v) => b.includes(v));

const MODES = ["supply", "cost_only"];
export const STAGES: readonly ExpeditionStage[] = ["outbound", "cutting", "returning"];
/** Why no expedition was launched for a region with a gap, in check order. */
export const REFUSALS = ["no_forest", "too_far", "forest_depleted", "forest_busy", "no_crew", "no_coins"] as const;
export const DROP_REASONS = ["died", "migrated", "enlisted", "on_trip", "other_work"] as const;
export const END_REASONS = ["crew_lost", "no_coins", "home_lost", "forest_lost", "pool_reset", "switched_off"] as const;
export const CUT_ENDS = ["completed", "forest_depleted", "forest_lost", "recalled"] as const;
const NEED_STATUSES = ["supplied", "expedition", "launched", "refused"];
const MAX_CLOSED = 32;
const MAX_NEEDS = 128;

function expeditionProblem(x: unknown, regions: number, civs: number, crewCap: number, live: boolean): string | null {
  if (!object(x) || !count(x.eid) || !count(x.civ) || x.civ >= civs || !count(x.home) || x.home >= regions
    || !count(x.forest) || x.forest >= regions || !count(x.slot) || !count(x.hops) || !count(x.launched_turn)
    || !STAGES.includes(x.stage as ExpeditionStage) || !count(x.stage_turns) || !count(x.travelled)
    || !count(x.return_hops) || typeof x.arrived !== "boolean" || !ids(x.crew, crewCap) || !ids(x.launched_crew, crewCap)
    || !ids(x.veterans, crewCap) || !amount(x.need)
    || ![x.cargo, x.cut, x.income_withheld, x.away_requested, x.away_delivered, x.delivered, x.lost, x.abandoned].every(amount)
    || ![x.cut_turns, x.worked_turns, x.person_turns, x.wages_milli, x.wage_residual_milli, x.unpaid_turns].every(count)
    || !maybe(count)(x.recalled_turn) || !maybe(count)(x.ended_turn)
    || !(x.cut_end === null || CUT_ENDS.includes(x.cut_end as never))
    || !Array.isArray(x.drops) || !Array.isArray(x.history)) return "malformed expedition";
  const r = x as unknown as ExpeditionRecord;
  if (!r.drops.every((d) => Array.isArray(d) && d.length === 3 && count(d[0]) && count(d[1])
    && DROP_REASONS.includes(d[2] as never))) return "malformed crew drops";
  if (!subset(r.crew as number[], r.launched_crew as number[]) || !subset(r.veterans as number[], r.launched_crew as number[]))
    return "a crew member was not launched with the expedition";
  if (!close(r.cut as number, r.cargo + r.delivered + r.lost + r.abandoned, r.cut as number))
    return "an expedition's timber does not close (cut = cargo + delivered + lost + abandoned)";
  if (r.away_delivered > r.away_requested + 1e-6) return "more farm labour removed than asked";
  if (live) {
    if (r.status !== "live" || r.ended_turn !== null || r.end_reason !== null) return "a live expedition has ended";
    if (r.delivered !== 0 || r.abandoned !== 0 || r.lost !== 0) return "a live expedition has delivered";
    return null;
  }
  if (!count(r.ended_turn)) return "a closed expedition has no end";
  if (r.status === "delivered") return r.end_reason === null && r.cargo === 0 ? null : "a delivered expedition kept cargo";
  if (r.status !== "abandoned" || !END_REASONS.includes(r.end_reason as never) || r.cargo !== 0 || r.delivered !== 0)
    return "malformed abandoned expedition";
  return null;
}

function receiptProblem(x: unknown, regions: number, civs: number, source: number, mode: string,
  p: Record<string, number>): string | null {
  if (!object(x) || x.turn !== source || !count(x.eid) || !count(x.civ) || x.civ >= civs || !count(x.home)
    || x.home >= regions || !count(x.forest) || x.forest >= regions || !count(x.slot)
    || !STAGES.includes(x.stage as ExpeditionStage) || !ids(x.crew, p.crew_cap) || !ids(x.veterans, p.crew_cap)
    || !Array.isArray(x.dropped) || ![x.away_requested, x.away_delivered, x.crew_labor, x.cut, x.cargo_after].every(amount)
    || ![x.wages_due_milli, x.wages_milli, x.wage_residual_milli].every(count)
    || !maybe(amount)(x.stock_before) || !maybe(amount)(x.stock_after) || !maybe(amount)(x.capacity)
    || !maybe(amount)(x.income_withheld) || !(x.cut_end === null || CUT_ENDS.includes(x.cut_end as never))
    || typeof x.unpaid !== "boolean" || typeof x.recalled !== "boolean") return "malformed expedition receipt";
  const r = x as unknown as ExpeditionReceiptRecord;
  if (!r.dropped.every((d) => Array.isArray(d) && d.length === 2 && count(d[0]) && DROP_REASONS.includes(d[1] as never)
    && !(r.crew as number[]).includes(d[0] as number))) return "a dropped member is still on the crew";
  if (!subset(r.veterans as number[], r.crew as number[])) return "a veteran is not on the crew";
  if (r.away_delivered > r.away_requested + 1e-6) return "more farm labour removed than asked";
  if (r.wages_milli + r.wage_residual_milli !== r.wages_due_milli) return "expedition wages do not close";
  if (r.wages_due_milli !== (r.unpaid ? 0 : (r.crew as number[]).length * p.wage_milli))
    return r.unpaid ? "an unpaid turn was paid" : "wages are not the crew at the declared wage";
  const cutting = r.stage === "cutting";
  if (r.crew_labor > 0 && (!cutting || mode === "cost_only")) return "crew labour on the forest outside supplied cutting";
  if (r.cut > 0 && !r.crew_labor) return "timber cut without crew labour";
  if (r.cargo_after < r.cut - 1e-9) return "the cargo is less than this turn's cut";
  const account = [r.stock_before, r.stock_after, r.capacity];
  if (account.some((v) => v === null) !== account.every((v) => v === null)) return "a partial forest account";
  if (!cutting && account.some((v) => v !== null)) return "a forest account outside cutting";
  if (r.unpaid && r.crew_labor > 0) return "nobody cuts on an unpaid turn";
  return null;
}

function ledgerProblem(x: unknown, civs: number, source: number): string | null {
  if (!object(x) || x.turn !== source || !count(x.civ) || x.civ >= civs
    || ![x.expeditions, x.person_turns, x.wages_due_milli, x.wages_applied_milli, x.wage_residual_milli, x.charged,
      x.prepaid_before_milli, x.prepaid_after_milli].every(count)) return "malformed wage ledger";
  const r = x as unknown as TimberWageLedgerRecord;
  if (r.prepaid_before_milli >= 1000 || r.prepaid_after_milli >= 1000) return "a prepaid balance of a whole unit";
  if (r.charged * 1000 + r.prepaid_before_milli !== r.wages_applied_milli + r.prepaid_after_milli)
    return "the treasury charge does not close";
  if (r.wages_applied_milli + r.wage_residual_milli !== r.wages_due_milli) return "a civ's wages do not close";
  return null;
}

function storeProblem(x: unknown, regions: number): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions
    || ![x.opening, x.held, x.returned, x.delivered, x.released, x.closing].every(amount)) return "malformed store row";
  const r = x as unknown as TimberStoreRecord;
  const expected = r.opening - r.held + r.returned + r.delivered - r.released;
  const scale = Math.max(1, r.opening as number, r.held as number, r.delivered as number);
  return Math.abs(expected - r.closing) <= 1e-6 * scale ? null : "a timber store does not close";
}

function needProblem(x: unknown, regions: number, civs: number, minGap: number): string | null {
  if (!object(x) || !count(x.region) || x.region >= regions || !count(x.civ) || x.civ >= civs
    || ![x.want, x.free, x.store, x.in_transit, x.gap].every(amount) || !NEED_STATUSES.includes(x.status as string)
    || !maybe(count)(x.eid) || !(x.reason === null || typeof x.reason === "string")) return "malformed need row";
  const r = x as unknown as TimberNeedRecord;
  if (!close(r.gap as number, Math.max(0, r.want - r.free - r.in_transit), r.want as number))
    return "a need's gap does not close (gap = want - free - in transit)";
  if (r.store > r.free + 1e-6) return "the store exceeds the free timber";
  if (r.status === "refused") return REFUSALS.includes(r.reason as never) && r.eid === null && r.gap >= minGap - 1e-9
    ? null : "a refusal without its reason";
  if (r.reason !== null) return "a reason on a need that was not refused";
  if (r.status === "supplied") return r.eid === null && r.gap < minGap ? null : "a supplied need with a gap";
  if (r.status === "launched" && r.gap < minGap - 1e-9) return "a launch without a gap";
  return r.eid !== null ? null : "a need's expedition is not named";
}

/** Strict reading: absent, malformed (with the reason) or a dated, closing record. */
export function readTimberSupply(snapshot: TurnSnapshot | null, regionCount: number, civCount: number): TimberSupplyReading {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.timber_supply === undefined || livelihoods.timber_supply === null)
    return { status: "absent" };
  const bad = (reason: string): TimberSupplyReading => ({ status: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.timber_supply;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "PL1" || !MODES.includes(x.mode as string))
    return bad("unknown timber-supply schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated observation");
  const p = x.parameters;
  if (!object(p) || !Object.values(p).every(finite) || !count(p.crew_cap) || !count(p.wage_milli) || !amount(p.min_gap)
    || !object(x.units)) return bad("malformed parameters");
  const params = p as Record<string, number>;
  if (!object(x.counters) || !Object.values(x.counters).every(amount)) return bad("malformed counters");
  const c = x.counters as Record<string, number>;
  const get = (k: string) => c[k] ?? 0;
  if (get("wages_milli") + get("wage_residual_milli") !== get("wages_due_milli")) return bad("lifetime wages do not close");
  if (!close(get("cut"), get("delivered") + get("lost") + get("abandoned_cargo")
    + [...(x.expeditions as unknown[] ?? [])].reduce<number>((a, e) => a + (object(e) && amount(e.cargo) ? e.cargo : 0), 0), get("cut")))
    return bad("lifetime timber does not close (cut = delivered + lost + abandoned + cargo on the road)");
  if (x.mode === "cost_only" && (get("cut") !== 0 || get("crew_labor") !== 0)) return bad("the cost-only control cut timber");
  for (const [key, list, max, live] of [["expeditions", x.expeditions, regionCount, true],
    ["closed", x.closed, MAX_CLOSED, false]] as const) {
    if (!Array.isArray(list) || list.length > max) return bad(`malformed ${key}`);
    for (const e of list) {
      const why = expeditionProblem(e, regionCount, civCount, params.crew_cap, live);
      if (why) return bad(why);
      if (x.mode === "cost_only" && ((e as ExpeditionRecord).cut !== 0)) return bad("the cost-only control cut timber");
    }
  }
  const live = x.expeditions as ExpeditionRecord[];
  if (new Set(live.map((e) => e.home)).size !== live.length || new Set(live.map((e) => e.forest)).size !== live.length)
    return bad("two live expeditions share a home or a forest");
  const known = new Set([...live, ...(x.closed as ExpeditionRecord[])].map((e) => e.eid));
  if (known.size !== live.length + (x.closed as unknown[]).length) return bad("an expedition is listed twice");
  const keyed = (v: unknown, check: (n: unknown) => boolean, bound: number) => object(v)
    && Object.entries(v).every(([k, n]) => /^\d+$/.test(k) && Number(k) < bound && check(n));
  if (!keyed(x.store, (n) => amount(n) && (n as number) > 0, regionCount)) return bad("malformed store");
  if (!keyed(x.prepaid, (n) => count(n) && (n as number) > 0 && (n as number) < 1000, civCount)) return bad("malformed prepaid balances");
  if ((x.receipts === null) !== (x.ledger === null)) return bad("receipts without accounts");
  if (x.receipts !== null) {
    if (!Array.isArray(x.receipts) || !Array.isArray(x.ledger)) return bad("malformed receipts");
    for (const r of x.receipts) {
      const why = receiptProblem(r, regionCount, civCount, x.source_turn, x.mode as string, params);
      if (why) return bad(why);
      if (!known.has((r as ExpeditionReceiptRecord).eid)) return bad("a receipt names no listed expedition");
    }
    for (const l of x.ledger) {
      const why = ledgerProblem(l, civCount, x.source_turn);
      if (why) return bad(why);
    }
    const receipts = x.receipts as ExpeditionReceiptRecord[];
    const ledger = x.ledger as TimberWageLedgerRecord[];
    if (new Set(receipts.map((r) => r.eid)).size !== receipts.length) return bad("an expedition has two receipts");
    const people = receipts.flatMap((r) => r.crew);
    if (new Set(people).size !== people.length) return bad("a person is on two expeditions");
    // Each civ's ledger is the sum of its paid receipts (an unpaid turn charges nothing).
    const paid = receipts.filter((r) => !r.unpaid);
    const payers = new Set(paid.map((r) => r.civ));
    if (payers.size !== ledger.length || !ledger.every((l) => payers.has(l.civ))) return bad("wage ledger and receipts disagree");
    for (const l of ledger) {
      const mine = paid.filter((r) => r.civ === l.civ);
      const total = (f: (r: ExpeditionReceiptRecord) => number) => mine.reduce((a, r) => a + f(r), 0);
      if (mine.length !== l.expeditions || total((r) => r.crew.length) !== l.person_turns
        || total((r) => r.wages_due_milli) !== l.wages_due_milli || total((r) => r.wages_milli) !== l.wages_applied_milli
        || total((r) => r.wage_residual_milli) !== l.wage_residual_milli) return bad("wage ledger and receipts disagree");
    }
  }
  const frame = [x.stores, x.needs, x.needs_dropped, x.deposits];
  if (frame.some((v) => v === null) !== frame.every((v) => v === null)) return bad("a partial frame");
  if (x.stores !== null) {
    if (!Array.isArray(x.stores) || !Array.isArray(x.needs) || x.needs.length > MAX_NEEDS || !count(x.needs_dropped)
      || !Array.isArray(x.deposits)) return bad("malformed frame");
    for (const s of x.stores) {
      const why = storeProblem(s, regionCount);
      if (why) return bad(why);
    }
    if (new Set(x.stores.map((s) => (s as TimberStoreRecord).region)).size !== x.stores.length) return bad("a store is listed twice");
    for (const n of x.needs) {
      const why = needProblem(n, regionCount, civCount, params.min_gap);
      if (why) return bad(why);
    }
    if (new Set(x.needs.map((n) => (n as TimberNeedRecord).region)).size !== x.needs.length) return bad("a need is listed twice");
    if (!x.deposits.every((d) => Array.isArray(d) && d.length === 4 && d[0] === x.source_turn && count(d[1])
      && count(d[2]) && d[2] < regionCount && amount(d[3]))) return bad("malformed deposits");
  }
  if (x.per_expedition !== null) {
    const e = x.per_expedition;
    if (!object(e) || !count(e.ended) || e.ended < 1 || e.ended !== get("ended")
      || ![e.wages_milli, e.person_turns, e.farm_labor_away, e.unpaid_turns, e.cut, e.delivered].every(amount))
      return bad("malformed per-expedition means");
    if (!close((e.wages_milli as number) * e.ended, get("ended_wages_milli"), get("ended_wages_milli"))
      || !close((e.cut as number) * e.ended, get("ended_cut"), get("ended_cut"))
      || !close((e.delivered as number) * e.ended, get("ended_delivered"), get("ended_delivered")))
      return bad("per-expedition means disagree with the counters");
  } else if (get("ended") !== 0) return bad("ended expeditions without per-expedition means");
  return { status: "ok", record: x as unknown as TimberSupplyRecord };
}

/** Refusals by reason (lifetime, non-zero only), in check order. */
export function refusalCounts(record: TimberSupplyRecord): Array<[string, number]> {
  return REFUSALS.map((k): [string, number] => [k, record.counters[`refused_${k}`] ?? 0]).filter(([, v]) => v > 0);
}

/** Endings without delivery and crew drops by reason (lifetime, non-zero only). */
export function lossCounts(record: TimberSupplyRecord): { abandoned: Array<[string, number]>; dropped: Array<[string, number]> } {
  const pick = (prefix: string, keys: readonly string[]) => keys
    .map((k): [string, number] => [k, record.counters[prefix + k] ?? 0]).filter(([, v]) => v > 0);
  return { abandoned: pick("abandoned_", END_REASONS), dropped: pick("dropped_", DROP_REASONS) };
}
