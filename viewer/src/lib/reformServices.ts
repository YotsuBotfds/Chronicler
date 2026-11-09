import { isRecord as object, amount, count } from "./recordGuards";
import type { Bundle, TurnSnapshot } from "../types";
import { readRecord, type RecordReading } from "./recordReading";

/**
 * Reader of D1a poor relief as a real service (`snapshot.livelihoods.reform_services`,
 * `--reform-services`; Python reference `chronicler.reform_services.record_status`).
 * Types live here, not in the pinned `types.ts`.
 *
 * The six readings of `recordReading.ts` stay distinct: `disabled` (no snapshot of
 * the run carries the record), `absent` (the run records it, this snapshot does not:
 * unknown, not zero), `malformed` (present and refused), `unobserved` (a valid record
 * whose turn was not observed: `frame: null`), `recorded_zero` (observed: no relief
 * money was paid in, spent or returned and nothing was bought or delivered) and
 * `recorded`. Inside a frame zeros are recorded zeros and nulls unknown: a delivery's
 * `delivered_at_least` is null in current records because gross outbound food
 * is unobserved. Historical positive estimates remain readable, but are not
 * presented as established delivery evidence. An unobserved delivery has no pool
 * reading at all. Relief food is pooled with the commons, so what reached people is
 * bounded per region, never attributed to persons. Never reads final-world state.
 */
export const MODES = ["service", "cost_only"] as const;
const PATHS = ["upkeep", "institution"] as const;
export type ReliefMode = (typeof MODES)[number];

export interface CivRelief {
  civ: number; reform: number | null; path: (typeof PATHS)[number] | null;
  fund_open_milli: number; to_fund_milli: number; sunk_units: number; spent_milli: number;
  residual_milli: number; refunded_milli: number; fund_close_milli: number; cap_milli: number;
}

export interface ReliefPurchase {
  region: number; civ: number; reform: number; unmet_rations: number; price_milli: number;
  food_milli: number; goods_milli: number[]; rations: number; cost_milli: number;
  credited_milli: number; residual_milli: number; sellers: number;
}

export interface ReliefDelivery {
  region: number; civ: number; bought_turn: number; rations_bought: number; observed: boolean;
  free_rations: number | null; free_given: number | null; free_unallocated: number | null;
  delivered_at_least: number | null; delivered_at_most: number | null;
  priced_out_persons: number | null; unmet_rations: number | null;
}

export interface ReliefFrame { turn: number; civs: CivRelief[]; purchases: ReliefPurchase[]; deliveries: ReliefDelivery[] }

export interface ReliefRecord {
  schema_version: 1; stage: "D1a"; mode: ReliefMode; source_turn: number;
  frame: ReliefFrame | null; funds: Record<string, number>; counters: Record<string, number>;
  log: { turn: number; kind: string; civ: number | null; region: number | null; milli: number | null; note: string }[];
  log_dropped: number; parameters: Record<string, unknown>;
}

const index = (x: unknown, n: number): x is number => count(x) && x < n;
const maybe = (x: unknown) => x === null || amount(x);
const TOL = 1e-6;

function civProblem(x: unknown, civs: number): string | null {
  if (!object(x) || !index(x.civ, civs) || !(x.reform === null || count(x.reform))
    || !(x.path === null || PATHS.includes(x.path as (typeof PATHS)[number]))
    || !["fund_open_milli", "to_fund_milli", "sunk_units", "spent_milli", "residual_milli", "refunded_milli",
      "fund_close_milli", "cap_milli"].every((k) => count(x[k]))) return "malformed relief fund row";
  const c = x as unknown as CivRelief;
  if (c.fund_open_milli + c.to_fund_milli - c.spent_milli - c.refunded_milli !== c.fund_close_milli)
    return "a relief fund does not close (open + paid in - spent - refunded != close)";
  return null;
}

function purchaseProblem(x: unknown, regions: number, civs: number): string | null {
  if (!object(x) || !index(x.region, regions) || !index(x.civ, civs) || !count(x.reform) || !amount(x.unmet_rations)
    || !count(x.price_milli) || !count(x.food_milli) || !Array.isArray(x.goods_milli) || !x.goods_milli.every(count)
    || !amount(x.rations) || !count(x.cost_milli) || !count(x.credited_milli) || !count(x.residual_milli)
    || !count(x.sellers)) return "malformed relief purchase";
  const p = x as unknown as ReliefPurchase;
  if (p.food_milli <= 0 || p.cost_milli <= 0 || p.price_milli <= 0 || p.sellers <= 0) return "an empty relief purchase";
  if (p.goods_milli.reduce((a, b) => a + b, 0) !== p.food_milli) return "a relief purchase's goods do not sum to its food";
  if (p.credited_milli + p.residual_milli !== p.cost_milli) return "a relief purchase's payments do not close";
  return null;
}

function deliveryProblem(x: unknown, regions: number, civs: number): string | null {
  if (!object(x) || !index(x.region, regions) || !index(x.civ, civs) || !count(x.bought_turn)
    || !amount(x.rations_bought) || typeof x.observed !== "boolean") return "malformed relief delivery";
  const fields = ["free_rations", "free_given", "free_unallocated", "delivered_at_least", "delivered_at_most",
    "unmet_rations"] as const;
  if (!fields.every((k) => maybe(x[k])) || !(x.priced_out_persons === null || count(x.priced_out_persons)))
    return "malformed relief delivery";
  const d = x as unknown as ReliefDelivery;
  if (!d.observed) {
    return [...fields, "priced_out_persons" as const].every((k) => d[k] === null) ? null
      : "an unobserved delivery carries readings";
  }
  if (d.free_rations === null || d.free_given === null || d.free_unallocated === null || d.delivered_at_most === null)
    return "an observed delivery lacks its pool reading";
  if (Math.abs(d.free_given + d.free_unallocated - d.free_rations) > TOL * Math.max(1, d.free_rations))
    return "a delivery's free pool does not close";
  if (d.delivered_at_most > Math.min(d.rations_bought, d.free_given) + TOL) return "a delivery exceeds what was bought or given";
  if (d.delivered_at_least !== null && d.delivered_at_least > d.delivered_at_most + TOL) return "a delivery's bounds cross";
  return null;
}

/** Strict reading of one record; the reason it is refused, or the record. */
export function reliefRecordAt(snapshot: TurnSnapshot | null, regions: number, civs: number):
  { record: ReliefRecord; reason: null } | { record: null; reason: string } {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  const x = object(livelihoods) ? livelihoods.reform_services : undefined;
  const refuse = (reason: string) => ({ record: null, reason });
  if (!object(x) || x.schema_version !== 1 || x.stage !== "D1a") return refuse("unknown relief-services schema");
  if (!MODES.includes(x.mode as ReliefMode) || !count(x.source_turn) || !object(x.funds) || !object(x.counters)
    || !Array.isArray(x.log) || !count(x.log_dropped)) return refuse("malformed relief-services record");
  if (!Object.values(x.funds).every(count) || !Object.values(x.counters).every(count))
    return refuse("malformed relief funds or counters");
  const f = x.frame;
  if (f !== null) {
    if (!object(f) || f.turn !== x.source_turn) return refuse("misdated frame");
    if (!Array.isArray(f.civs) || !Array.isArray(f.purchases) || !Array.isArray(f.deliveries))
      return refuse("malformed frame");
    for (const c of f.civs) { const why = civProblem(c, civs); if (why) return refuse(why); }
    if (new Set(f.civs.map((c) => (c as CivRelief).civ)).size !== f.civs.length) return refuse("a realm has two fund rows");
    for (const p of f.purchases) { const why = purchaseProblem(p, regions, civs); if (why) return refuse(why); }
    for (const d of f.deliveries) { const why = deliveryProblem(d, regions, civs); if (why) return refuse(why); }
    if ((x.mode as ReliefMode) === "cost_only" && (f.purchases.length > 0
      || f.civs.some((c) => (c as CivRelief).to_fund_milli > 0))) return refuse("the cost-only control bought or held money");
  }
  return { record: x as unknown as ReliefRecord, reason: null };
}

const carries = (snapshot: TurnSnapshot) => {
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods;
  return object(livelihoods) && livelihoods.reform_services !== undefined && livelihoods.reform_services !== null;
};

/** Whether nothing moved in an observed frame (recorded zero). */
function reliefEmpty(frame: ReliefFrame): boolean {
  return frame.purchases.length === 0 && frame.deliveries.length === 0
    && frame.civs.every((c) => c.to_fund_milli === 0 && c.spent_milli === 0 && c.refunded_milli === 0 && c.sunk_units === 0);
}

const REFORM_SERVICES = {
  key: "reform_services", label: "Poor relief services", flag: "--reform-services", livelihoods: true,
  carries, read: (s: TurnSnapshot, regions: number, civs: number) => reliefRecordAt(s, regions, civs).record,
  observed: (r: ReliefRecord) => r.frame !== null,
  empty: (r: ReliefRecord) => r.frame !== null && reliefEmpty(r.frame),
  zero: "no relief money was paid in, spent or returned, and nothing was bought or delivered",
};

export const readReformServices = (bundle: Bundle | null | undefined, snapshot: TurnSnapshot | null,
  turn?: number): RecordReading<ReliefRecord> => readRecord(REFORM_SERVICES, bundle, snapshot, turn);

/** Whether any snapshot of the run carries the record (the panel mounts on the run). */
export function reformServicesOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((s) => s !== null && typeof s === "object" && carries(s));
}

/** Per region of a frame: rations bought, and the delivery bounds read this turn. */
export function reliefByRegion(frame: ReliefFrame): { region: number; bought: number; atMost: number | null;
  atLeast: number | null; observed: boolean }[] {
  const rows = new Map<number, { region: number; bought: number; atMost: number | null; atLeast: number | null; observed: boolean }>();
  for (const p of frame.purchases) {
    const r = rows.get(p.region) ?? { region: p.region, bought: 0, atMost: null, atLeast: null, observed: true };
    r.bought += p.rations;
    rows.set(p.region, r);
  }
  for (const d of frame.deliveries) {
    const r = rows.get(d.region) ?? { region: d.region, bought: 0, atMost: null, atLeast: null, observed: true };
    r.observed = r.observed && d.observed;
    if (d.delivered_at_most !== null) r.atMost = (r.atMost ?? 0) + d.delivered_at_most;
    // Legacy records estimated a lower bound without observing gross exports.
    // Retain their raw record, but never present that estimate as established.
    rows.set(d.region, r);
  }
  return [...rows.values()].sort((a, b) => a.region - b.region);
}
