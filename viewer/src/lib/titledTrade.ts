import { isRecord as object, finite, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/**
 * A4 titled trade (``snapshot.livelihoods.titled_trade``, stage ``A4``):
 * merchants buy owners' surplus food in a retail pilot region, carry it with
 * title and custody as one shipment by stable id and sell it as their own
 * retail claim at another pilot region. Food is in milli-food per retail good
 * (grain, fish, salt, botanicals, exotic); money in milli-units (1000 = one unit
 * of a person's wealth); prices in milli-units per ration; withheld income in
 * wealth units. Types live here (``types.ts`` is pinned).
 *
 * States a reader keeps apart:
 * - ``absent``: no livelihoods record, or one without household retail either;
 * - ``disabled``: a household retail record without this record (titled trade off);
 * - ``malformed``: a record that is not this shape or whose books do not close;
 * - ``unobserved``: no frame for its source turn (unknown, not zero);
 * - ``observed``: a frame whose zeros are recorded zeros.
 */
export type TitledTradeStatus = "absent" | "disabled" | "malformed" | "unobserved" | "observed";

/** ``released_returned``: the carrier was released in transit, so the shipment went back to its
 * origin at once (the holder keeps title there; its cause is the release reason). */
export const OUTCOMES = ["delivered", "returned", "escheated", "pool_reset", "switched_off", "released_returned"] as const;
const RETURN_CAUSES = ["destination_conquered", "quarantine_closure", "route_lost",
  "destination_left_pilot"] as const;
const RELEASE_REASONS = ["migrated", "occupation", "enlisted", "on_trip", "other_work"] as const;
const EVENTS = ["moved", ...OUTCOMES];
export const GOODS = ["grain", "fish", "salt", "botanicals", "exotic"] as const;

export interface ShipmentRecord {
  id: number; goods: "food"; holder: number; carrier: number | null; origin: number; dest: number;
  path: number[]; cursor: number; controllers: (string | null)[]; status: "moving" | "closed";
  dispatched_turn: number; last_moved_turn: number | null; cargo: number[]; cargo_open: number[];
  cost_milli: number; price_milli: number; sellers: number; losses: Record<string, number>;
  delivered: number; returned: number; deposited: number; deposit_reason: string | null;
  outcome: typeof OUTCOMES[number] | null; cause: string | null; closed_turn: number | null;
  closed_region: number | null; released: string | null; withheld: number; withheld_turns: number;
  war_exempt_turns: number; history: [number, string, number][];
}

/** One purchase: the merchant (holder) paid each owner for its surplus, by id. */
export interface PurchaseRecord {
  shipment: number; holder: number; origin: number; dest: number; path: number[]; milli: number; cargo: number[];
  price_milli: number; paid: number; refunded: number; sellers: number;
  /** ``[owner, milli-food taken, milli-units asked, milli-units paid]``, at most 16 rows. */
  seller_rows: [number, number, number, number][];
}

export interface TradeEvent {
  shipment: number; event: string; region: number; reason?: string; cause?: string | null;
  delivered?: number; returned?: number; deposited?: number; losses?: Record<string, number>;
}

export interface WithheldRow { shipment: number; carrier: number; share: number; ordinary: number; deducted: number }
export interface HolderSale { holder: number; region: number; sold: number; cargo_sold: number; credited: number; exact: boolean }

export interface TradeFrame {
  turn: number; dispatched: PurchaseRecord[]; events: TradeEvent[]; withheld: WithheldRow[]; withheld_total: number;
  sales: HolderSale[]; plans: Record<string, number>; live: number;
}

export interface TitledTradeRecord {
  schema_version: 1; stage: "A4"; goods: "food"; source_turn: number;
  units: Record<string, string | number>;
  shipments: ShipmentRecord[]; closed: ShipmentRecord[];
  lots: { holder: number; region: number; milli: number; shipments: number[] }[];
  frame: TradeFrame | null;
  counters: Record<string, number>;
  log: { turn: number; kind: string; shipment: number | null; detail: Record<string, unknown> }[];
  log_dropped: number;
  parameters: Record<string, unknown>;
}

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
const goods = (x: unknown): x is number[] => Array.isArray(x) && x.length === GOODS.length && x.every(count);

function validShipment(x: unknown, regions: number, live: boolean): boolean {
  if (!object(x)) return false;
  const region = (v: unknown) => count(v) && v < regions;
  if (!count(x.id) || !count(x.holder) || (x.carrier !== null && !count(x.carrier)) || !region(x.origin)
    || !region(x.dest) || !Array.isArray(x.path) || x.path.length < 2 || !x.path.every(region)
    || !count(x.cursor) || x.cursor >= x.path.length || x.path[0] !== x.origin || !goods(x.cargo)
    || !goods(x.cargo_open) || !object(x.losses) || !Object.values(x.losses).every(count)
    || !count(x.delivered) || !count(x.returned) || !count(x.deposited) || !count(x.cost_milli)
    || !count(x.price_milli) || !count(x.sellers) || !finite(x.withheld) || x.withheld < 0
    || !count(x.withheld_turns) || !count(x.dispatched_turn)) return false;
  const lost = sum(Object.values(x.losses) as number[]);
  // The cargo closes: what was bought is aboard, lost, delivered, returned or deposited.
  if (sum(x.cargo_open) !== sum(x.cargo) + lost + (x.delivered as number) + (x.returned as number)
    + (x.deposited as number)) return false;
  if (live) return x.status === "moving" && x.outcome === null;
  // A closed shipment has exactly one outcome and nothing aboard.
  return x.status === "closed" && OUTCOMES.includes(x.outcome as typeof OUTCOMES[number]) && sum(x.cargo) === 0
    && (x.outcome !== "returned" || RETURN_CAUSES.includes(x.cause as typeof RETURN_CAUSES[number]))
    && (x.outcome !== "released_returned" || RELEASE_REASONS.includes(x.cause as typeof RELEASE_REASONS[number]));
}

function validFrame(x: unknown, source: number): boolean {
  if (!object(x) || x.turn !== source || !Array.isArray(x.dispatched) || !Array.isArray(x.events)
    || !Array.isArray(x.withheld) || !Array.isArray(x.sales) || !finite(x.withheld_total) || !object(x.plans)
    || !count(x.live)) return false;
  for (const d of x.dispatched) {
    if (!object(d) || !count(d.shipment) || !count(d.holder) || !count(d.milli) || !goods(d.cargo)
      || d.milli !== sum(d.cargo as number[]) || !count(d.paid) || !count(d.refunded) || !count(d.sellers)
      || !Array.isArray(d.seller_rows) || d.seller_rows.length > 16
      || !d.seller_rows.every((r) => Array.isArray(r) && r.length === 4 && r.every(count) && r[3] <= r[2])) return false;
    // When every seller is listed, their payments are the bill.
    if (d.seller_rows.length === d.sellers && sum((d.seller_rows as number[][]).map((r) => r[3])) !== d.paid) return false;
  }
  if (!x.events.every((e) => object(e) && count(e.shipment) && EVENTS.includes(e.event as string))) return false;
  if (!x.withheld.every((w) => object(w) && count(w.shipment) && count(w.carrier) && w.share === 1
    && finite(w.deducted) && finite(w.ordinary) && w.deducted >= 0)) return false;
  if (Math.abs(sum((x.withheld as WithheldRow[]).map((w) => w.deducted)) - x.withheld_total) > 1e-6) return false;
  return x.sales.every((s) => object(s) && count(s.holder) && count(s.sold) && count(s.cargo_sold)
    && count(s.credited) && typeof s.exact === "boolean" && (s.cargo_sold as number) <= (s.sold as number));
}

/** The record's state at one snapshot, and the record when observed or unobserved. */
export function titledTradeAt(snapshot: TurnSnapshot | null, regionCount: number):
  { status: TitledTradeStatus; record: TitledTradeRecord | null } {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return { status: "absent", record: null };
  if (!("titled_trade" in livelihoods)) {
    return { status: livelihoods.household_retail != null ? "disabled" : "absent", record: null };
  }
  const x = livelihoods.titled_trade;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "A4" || x.goods !== "food" || !count(x.source_turn)
    || x.source_turn + 1 !== snapshot?.turn || !object(x.units) || x.units.milli !== 1000
    || !Array.isArray(x.shipments) || x.shipments.length > 64 || !x.shipments.every((s) => validShipment(s, regionCount, true))
    || !Array.isArray(x.closed) || x.closed.length > 32 || !x.closed.every((s) => validShipment(s, regionCount, false))
    || !Array.isArray(x.lots) || !object(x.counters) || !Object.values(x.counters).every(count)
    || !Array.isArray(x.log) || !count(x.log_dropped) || !object(x.parameters)) {
    return { status: "malformed", record: null };
  }
  const ids = [...x.shipments, ...x.closed].map((s) => (s as ShipmentRecord).id);
  if (new Set(ids).size !== ids.length) return { status: "malformed", record: null };
  if (x.frame === null) return { status: "unobserved", record: x as unknown as TitledTradeRecord };
  if (!validFrame(x.frame, x.source_turn as number)) return { status: "malformed", record: null };
  return { status: "observed", record: x as unknown as TitledTradeRecord };
}

/** Milli-units (or milli-food) as whole units. */
export const units = (milli: number) => milli / 1000;

export interface TradeFunnel {
  dispatched: number; delivered: number; returned: number; escheated: number; ended: number;
  /** Shipments whose carrier was released in transit: returned to the origin at once. */
  releasedReturned: number;
  returnedBy: Record<string, number>; releasedBy: Record<string, number>; bought: number; paid: number; transitDecay: number; seaLoss: number;
  consigned: number; returnedFood: number; deposited: number; cargoSold: number; salesCredited: number;
  salesInexact: number; withheld: number; carrierTurns: number; carriersReleased: number;
  /** Merchants' realized sales credits less what they paid owners (wealth units), and the model
   * income withheld from carriers over the same shipments: margins replace it, never stack. */
  netMoney: number;
}

/** Lifetime funnel from the counters (units, not milli-units). Recorded zeros stay zeros. */
export function tradeFunnel(record: TitledTradeRecord): TradeFunnel {
  const c = (key: string) => record.counters[key] ?? 0;
  const returnedBy: Record<string, number> = {};
  for (const cause of RETURN_CAUSES) returnedBy[cause] = c(`returned_${cause}`);
  const releasedBy: Record<string, number> = {};
  for (const reason of RELEASE_REASONS) releasedBy[reason] = c(`released_returned_${reason}`);
  return {
    dispatched: c("dispatched"), delivered: c("delivered"), returned: c("returned"), escheated: c("escheated"),
    ended: c("pool_reset") + c("switched_off"), releasedReturned: c("released_returned"), returnedBy, releasedBy, bought: units(c("bought_milli")), paid: units(c("paid_milli")),
    transitDecay: units(c("transit_decay_milli")), seaLoss: units(c("sea_loss_milli")),
    consigned: units(c("consigned_milli")), returnedFood: units(c("returned_milli")), deposited: units(c("deposited_milli")),
    cargoSold: units(c("cargo_sold_milli")), salesCredited: units(c("cargo_sales_credited_milli")),
    salesInexact: units(c("cargo_sales_inexact_milli")), withheld: c("income_withheld_micro") / 1_000_000,
    carrierTurns: c("carrier_turns"), carriersReleased: c("carriers_released"),
    netMoney: units(c("cargo_sales_credited_milli") - c("paid_milli")),
  };
}
