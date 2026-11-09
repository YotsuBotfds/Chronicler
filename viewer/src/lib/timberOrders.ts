/** A4-3 actual timber cargo and treasury escrow. Milli-timber/milli-money are distinct. */
import { isRecord as object, finite, safeCount as count } from "./recordGuards";
import type { TurnSnapshot } from "../types";
export interface TimberOrder {
  id: number; holder: number; origin: number; dest: number; seller: number; payer: number;
  path: number[]; cursor: number; dispatched_turn: number; last_moved_turn: number | null;
  status: "moving" | "closed"; outcome: string | null; closed_turn: number | null;
  cargo_open_milli: number; cargo_milli: number; delivered_milli: number; lost_milli: number; deposited_milli: number;
  purchase_milli: number; sale_price_milli: number; price_turn: number;
  cash: number; escrowed_milli: number; credited_milli: number; refunded_milli: number; withheld: number;
}
export interface TimberOrderEvent {
  kind: string; order: number; holder: number; origin: number; dest: number; region: number;
  bought_milli?: number; purchase_milli?: number; escrowed_milli?: number;
  delivered_milli?: number; deposited_milli?: number; credited_milli?: number; refunded_milli?: number;
}
export interface TimberOrdersRecord {
  schema_version: 1; stage: "A4-3"; source_turn: number; orders: TimberOrder[]; closed: TimberOrder[];
  frame: null | { turn: number; events: TimberOrderEvent[]; events_dropped: number;
    withheld: { order: number; holder: number; ordinary: number; deducted: number }[];
    dispatched: Record<string, number>; spent: Record<string, number> };
  counters: Record<string, number>; parameters: Record<string, number>;
}
const outcomes = ["delivered", "holder_died", "carrier_released", "recipient_lost", "expired", "route_lost", "seized", "pool_reset", "switched_off"];
export function timberOrdersAt(snapshot: TurnSnapshot | null, regions: number, civs: number):
  { status: "absent" | "malformed" | "unobserved" | "observed"; record: TimberOrdersRecord | null } {
  const lh = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  if (lh == null || (object(lh) && lh.timber_orders == null)) return { status: "absent", record: null };
  const bad = () => ({ status: "malformed" as const, record: null });
  if (!object(lh) || lh.schema_version !== 1) return bad();
  const x = lh.timber_orders, region = (r: unknown) => count(r) && r < regions, civ = (r: unknown) => count(r) && r < civs;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "A4-3" || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn
    || !Array.isArray(x.orders) || x.orders.length > 64 || !Array.isArray(x.closed) || x.closed.length > 32
    || !object(x.counters) || !Object.values(x.counters).every(count) || !object(x.parameters)
    || !Object.values(x.parameters).every((n) => finite(n) && n >= 0)) return bad();
  const ids = new Set<number>();
  for (const [live, rows] of [[true, x.orders], [false, x.closed]] as const) for (const r of rows) {
    if (!object(r) || !count(r.id) || ids.has(r.id) || !count(r.holder) || !region(r.origin) || !region(r.dest) || !civ(r.seller) || !civ(r.payer)
      || !Array.isArray(r.path) || r.path.length < 2 || !r.path.every(region) || r.path[0] !== r.origin || r.path.at(-1) !== r.dest
      || !count(r.cursor) || r.cursor >= r.path.length || !count(r.dispatched_turn) || r.dispatched_turn > x.source_turn
      || !count(r.price_turn) || r.price_turn >= r.dispatched_turn || (r.last_moved_turn !== null && (!count(r.last_moved_turn) || r.last_moved_turn > x.source_turn))
      || !finite(r.withheld) || r.withheld < 0) return bad();
    for (const k of ["cargo_open_milli", "cargo_milli", "delivered_milli", "lost_milli", "deposited_milli", "purchase_milli", "sale_price_milli", "cash", "escrowed_milli", "credited_milli", "refunded_milli"]) if (!count(r[k])) return bad();
    const o = r as unknown as TimberOrder;
    if (o.cargo_open_milli !== o.cargo_milli + o.delivered_milli + o.lost_milli + o.deposited_milli
      || o.escrowed_milli !== o.cash + o.credited_milli + o.refunded_milli
      || (live ? o.status !== "moving" || o.outcome !== null || o.closed_turn !== null
        : o.status !== "closed" || !outcomes.includes(o.outcome ?? "") || !count(o.closed_turn) || o.closed_turn > x.source_turn || o.cargo_milli !== 0 || o.cash !== 0)) return bad();
    ids.add(o.id);
  }
  if (x.frame === null) return { status: "unobserved", record: x as unknown as TimberOrdersRecord };
  const f = x.frame;
  if (!object(f) || f.turn !== x.source_turn || !Array.isArray(f.events) || f.events.length > 256 || !count(f.events_dropped)
    || !Array.isArray(f.withheld) || !object(f.dispatched) || !Object.values(f.dispatched).every(count)
    || !object(f.spent) || !Object.values(f.spent).every(count)) return bad();
  for (const e of f.events) {
    if (!object(e) || !["dispatched", ...outcomes].includes(e.kind as string) || !count(e.order) || !count(e.holder) || !region(e.origin) || !region(e.dest) || !region(e.region)) return bad();
    for (const [k, v] of Object.entries(e)) if (k.endsWith("_milli") && !count(v)) return bad();
  }
  if (!f.withheld.every((r) => object(r) && count(r.order) && count(r.holder) && finite(r.ordinary) && finite(r.deducted) && r.deducted >= 0)) return bad();
  return { status: "observed", record: x as unknown as TimberOrdersRecord };
}
