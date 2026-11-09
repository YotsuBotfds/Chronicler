import { isRecord as object, finite, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/** One sender's row (``snapshot.livelihoods.remittances.receipts``). Money in milli-units. */
export interface RemittanceReceiptRecord {
  turn: number; sender: number; recipient: number; bond: "marriage" | "kin"; sentiment: number;
  /** The recipient's region (the sender's origin) and the sender's region. */
  origin: number; destination: number;
  wealth_milli: number; amount: number; fee_requested: number;
  sent: number; fee: number; credited: number; refunded: number;
  status: "applied" | "limited" | "absent" | "not_sent";
}

/** An eligible sender with no linked recipient this turn. */
export interface UnmetSenderRecord {
  id: number; origin: number; destination: number;
  reason: "no_bond" | "recipient_away" | "recipient_on_trip"; surplus_milli: number;
}

/** An applied native migration of this turn, as the diaspora ledger read it. */
export interface DiasporaMoveRecord {
  id: number; from_region: number; to_region: number;
  kind: "departure" | "onward" | "return" | "unrecorded"; qualified: boolean; driver: number | null;
}

export interface DiasporaClosureRecord {
  id: number; origin: number; destination: number; departure_turn: number; closed_turn: number;
  reason: "return" | "death" | "pool_reset" | "unobserved_gap";
}

/** A region's diaspora this turn: losses and gains separately, the stock after the turn, money in and out. */
export interface DiasporaRegionRecord {
  region: number; departures: number; arrivals: number; returns_home: number;
  qualified_departures: number; qualified_arrivals: number;
  diaspora_out: number; diaspora_in: number; qualified_out: number; qualified_in: number;
  senders: number; recipients: number; outflow_milli: number; fee_milli: number;
  refunded_milli: number; inflow_milli: number;
}

export interface RemittancesRecord {
  schema_version: 1; stage: "RS4"; mode: "send" | "record_only"; source_turn: number;
  /** Null: no remittance turn completed in the source turn (unknown, not zero). */
  funnel: Record<string, number> | null; totals: Record<string, number> | null;
  regions: DiasporaRegionRecord[] | null;
  moves: DiasporaMoveRecord[] | null; moves_dropped: number | null;
  closures: DiasporaClosureRecord[] | null; closures_dropped: number | null;
  receipts: RemittanceReceiptRecord[] | null; receipts_dropped: number | null;
  unmet: UnmetSenderRecord[] | null; unmet_dropped: number | null;
  last_pool_reset: { turn: number; entries_closed: number; reason: string } | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

const RECEIPT_STATUSES = ["applied", "limited", "absent", "not_sent"] as const;
const UNLINKED_REASONS = ["no_bond", "recipient_away", "recipient_on_trip"] as const;
const CLOSE_REASONS = ["return", "death", "pool_reset", "unobserved_gap"] as const;
const MOVE_KINDS = ["departure", "onward", "return", "unrecorded"] as const;

const integer = (x: unknown): x is number => finite(x) && Number.isInteger(x);
const among = (list: readonly string[], x: unknown) => typeof x === "string" && list.includes(x);
const counts = (x: unknown): x is Record<string, number> => object(x) && Object.values(x).every(count);
const MODES = ["send", "record_only"];
const REGION_FIELDS = ["departures", "arrivals", "returns_home", "qualified_departures", "qualified_arrivals",
  "diaspora_out", "diaspora_in", "qualified_out", "qualified_in", "senders", "recipients", "outflow_milli",
  "fee_milli", "refunded_milli", "inflow_milli"] as const;

const region = (x: unknown, regions: number): x is number => count(x) && x < regions;

function validReceipt(x: unknown, regions: number, source: number, mode: string): boolean {
  if (!object(x) || x.turn !== source || !count(x.sender) || !count(x.recipient) || x.sender === x.recipient
    || !among(["marriage", "kin"], x.bond) || !integer(x.sentiment) || !region(x.origin, regions)
    || !region(x.destination, regions) || x.origin === x.destination || !count(x.wealth_milli)
    || !count(x.amount) || x.amount === 0 || !count(x.fee_requested) || !count(x.sent) || !count(x.fee)
    || !count(x.credited) || !count(x.refunded) || !among(RECEIPT_STATUSES, x.status)) return false;
  if (x.sent !== x.fee + x.credited + x.refunded) return false;              // nothing created or lost
  if (x.sent > x.amount + x.fee_requested || x.fee > x.fee_requested) return false;
  if (mode === "record_only") return x.status === "not_sent" && x.sent === 0;
  if (x.status === "not_sent") return false;
  if (x.status === "absent") return x.sent === 0;
  if (x.status === "applied") return x.sent === x.amount + x.fee_requested && x.refunded === 0;
  return true;
}

function validUnmet(x: unknown, regions: number): boolean {
  return object(x) && count(x.id) && region(x.origin, regions) && region(x.destination, regions)
    && x.origin !== x.destination && among(UNLINKED_REASONS, x.reason) && count(x.surplus_milli);
}

function validMove(x: unknown, regions: number): boolean {
  return object(x) && count(x.id) && region(x.from_region, regions) && region(x.to_region, regions)
    && x.from_region !== x.to_region && among(MOVE_KINDS, x.kind) && typeof x.qualified === "boolean"
    && (x.driver === null || count(x.driver));
}

function validClosure(x: unknown, regions: number, source: number): boolean {
  return object(x) && count(x.id) && region(x.origin, regions) && region(x.destination, regions)
    && count(x.departure_turn) && x.closed_turn === source && x.departure_turn <= source
    && among(CLOSE_REASONS, x.reason);
}

function validRegion(x: unknown, regions: number): boolean {
  if (!object(x) || !region(x.region, regions) || !REGION_FIELDS.every((k) => count(x[k]))) return false;
  const r = x as unknown as DiasporaRegionRecord;
  return r.returns_home <= r.arrivals && r.qualified_departures <= r.departures
    && r.qualified_arrivals <= r.arrivals && r.qualified_out <= r.diaspora_out && r.qualified_in <= r.diaspora_in
    && r.fee_milli <= r.outflow_milli;
}

const list = <T,>(x: unknown, max: number, check: (v: unknown) => boolean): x is T[] =>
  Array.isArray(x) && x.length <= max && x.every(check);

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function remittancesAt(snapshot: TurnSnapshot | null, regionCount: number): RemittancesRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.remittances;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "RS4" || !among(MODES, x.mode)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !counts(x.counters)
    || !object(x.parameters) || !Object.values(x.parameters).every(count)) return null;
  const source = x.source_turn as number;
  const mode = x.mode as string;
  const reset = x.last_pool_reset;
  if (reset !== null && !(object(reset) && count(reset.turn) && reset.turn <= source + 1
    && count(reset.entries_closed) && typeof reset.reason === "string")) return null;
  const observed = ["funnel", "totals", "regions", "moves", "moves_dropped", "closures", "closures_dropped",
    "receipts", "receipts_dropped", "unmet", "unmet_dropped"];
  const nulls = observed.filter((k) => x[k] === null).length;
  if (nulls === observed.length) return x as unknown as RemittancesRecord;    // the turn is unknown, not zero
  if (nulls !== 0) return null;                                              // half a frame is malformed
  if (!counts(x.funnel) || !counts(x.totals) || !count(x.moves_dropped) || !count(x.closures_dropped)
    || !count(x.receipts_dropped) || !count(x.unmet_dropped)) return null;
  if (!list(x.regions, regionCount, (r) => validRegion(r, regionCount))
    || !list(x.moves, 64, (m) => validMove(m, regionCount))
    || !list(x.closures, 64, (c) => validClosure(c, regionCount, source))
    || !list(x.receipts, 64, (r) => validReceipt(r, regionCount, source, mode))
    || !list(x.unmet, 32, (u) => validUnmet(u, regionCount))) return null;
  const t = x.totals as Record<string, number>;
  const money = ["sent_milli", "fee_milli", "credited_milli", "refunded_milli", "debited_milli"];
  if (!money.every((k) => count(t[k]))) return null;
  if (t.debited_milli !== t.credited_milli + t.fee_milli || t.sent_milli !== t.debited_milli + t.refunded_milli) return null;
  if (mode === "record_only" && t.sent_milli !== 0) return null;
  const regions = x.regions as DiasporaRegionRecord[];
  if (new Set(regions.map((r) => r.region)).size !== regions.length) return null;
  const sum = (key: keyof DiasporaRegionRecord) => regions.reduce((a, r) => a + (r[key] as number), 0);
  if (sum("inflow_milli") !== t.credited_milli || sum("outflow_milli") !== t.debited_milli) return null;
  if (sum("departures") !== sum("arrivals")) return null;                    // every move leaves one region for another
  return x as unknown as RemittancesRecord;
}

/** Lifetime funnel stages from the counters; zero only once the record exists. */
export function remittancesFunnel(record: RemittancesRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Migrant-turns evaluated (open ledger entries)", c("sender_turns_evaluated")],
    ["Eligible senders (adult, settled, at their destination)", c("eligible_sender_turns")],
    ["Linked to a Marriage or Kin partner at home", c("linked_sender_turns")],
    ["Unmet: eligible, no linked recipient", c("unlinked_sender_turns")],
    ["Linked, nothing above the reserve", c("no_surplus_sender_turns")],
    ["Remittance rows", c("rows")],
    ["Applied in full", c("rows_applied")],
    ["Limited (sender's means or recipient's ceiling)", c("rows_limited")],
    ["Absent party: nothing moved", c("rows_absent")],
    ["Recorded, not sent (control)", c("rows_not_sent")],
  ];
}

/** Lifetime diaspora counts from the counters. */
export function diasporaCounts(record: RemittancesRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Applied moves seen", c("moves_seen")],
    ["Departures (entries opened)", c("departures")],
    ["Onward moves", c("onward_moves")],
    ["Returns home", c("returns")],
    ["Deaths abroad", c("deaths")],
    ["Departures not recorded (ledger full)", c("entries_refused")],
    ["Qualified departures (skill leaving)", c("qualified_departures")],
    ["Qualified returns", c("qualified_returns")],
  ];
}

/** Milli-units as wealth units. */
export const units = (milli: number) => milli / 1000;
