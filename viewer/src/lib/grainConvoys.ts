/**
 * Public grain convoys (``--grain-convoys``), read only from the per-turn
 * record ``snapshot.livelihoods.grain_convoys``; never the final world.
 *
 * The record is optional and absent from ``types.ts``, so it is read through
 * loose typing and checked field by field. Anything malformed, from another
 * source turn or of an unknown version reads as null: absent is not zero. A
 * record whose ``transitions`` is null knows the convoys on the road but not
 * what happened in its turn (unknown); an empty list means nothing happened.
 */
import { amount } from "./recordGuards";
import type { TurnSnapshot } from "../types";

export const CONVOY_COUNTERS = [
  "eligible", "no_budget", "no_route", "unaffordable", "capacity_refusals", "identity_refusals",
  "dispatched", "sent", "committed_net", "transit_loss", "paid", "escorted", "escort_paid",
  "legs", "waits", "reroutes", "turned_back", "threats", "repelled",
  "arrived", "delivered", "captured_delivery", "unguarded_delivery",
  "captured", "captured_grain", "lost", "lost_grain", "returned", "returned_grain",
  "stranded", "stranded_grain", "escort_wasted", "escort_wasted_paid",
] as const;
export type ConvoyCounter = typeof CONVOY_COUNTERS[number];

const CONVOY_POLICIES = ["adaptive", "cheapest", "safest"] as const;
const CONVOY_STATUSES = ["en_route", "waiting", "returning"] as const;
const CONVOY_OPERATIONS = ["dispatched", "advanced", "waited", "turned_back",
  "arrived", "captured", "lost", "returned", "stranded"] as const;
const FINAL = new Set<string>(["arrived", "captured", "lost", "returned", "stranded"]);
const MAX_ACTIVE = 64;
const MAX_FRAME = 128;
const MAX_ROUTE = 10;

export interface GrainConvoyRow {
  id: string; convoy: number; source: number; source_name: string; dest: number; dest_name: string;
  buyer: number; buyer_name: string; seller: number; seller_name: string; dispatch_turn: number;
  policy: typeof CONVOY_POLICIES[number]; route: number[]; route_names: (string | null)[];
  leg: number; progress: number; leg_turns: number; status: typeof CONVOY_STATUSES[number];
  escorted: boolean; escort_fee: number; sent: number; net: number; cargo: number; paid: number;
  waits: number; reroutes: number; threats: number; repelled: number;
  exposed_route: number[]; exposed_risk: number; exposed_turns: number;
  escorted_route: number[]; escorted_risk: number; escorted_turns: number;
}

export interface GrainConvoyTransition {
  id: string; convoy: number; turn: number; operation: typeof CONVOY_OPERATIONS[number];
  buyer: number; buyer_name: string; source: number; dest: number; at: number; at_name: string;
  route: number[]; leg: number; progress: number; status: string; cargo: number; escorted: boolean;
  rerouted: boolean; closure: string | null; threat: string | null; threat_risk: number | null;
  repelled: boolean; keeper: number | null; sink: string | null; sink_region: number | null;
  captor: number | null; paid: number | null; escort_fee: number | null;
}

export interface GrainConvoysRecord {
  source_turn: number; enabled: boolean; route_policy: typeof CONVOY_POLICIES[number];
  moved: boolean; dispatch_ran: boolean; active_count: number;
  in_transit_cargo: number; returning_cargo: number;
  active: GrainConvoyRow[];
  /** null: the source turn's transitions were not recorded (unknown, not zero). */
  transitions: GrainConvoyTransition[] | null;
  counters: Record<ConvoyCounter, number>;
}

type Row = Record<string, unknown>;
const object = (v: unknown): v is Row => typeof v === "object" && v !== null && !Array.isArray(v);
const integer = (v: unknown, min = 0): v is number => Number.isSafeInteger(v) && (v as number) >= min;
const name = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length <= 512;
const optional = <T>(v: unknown, check: (x: unknown) => x is T) => v === null || check(v);
const oneOf = <T extends string>(values: readonly T[]) => (v: unknown): v is T => values.includes(v as T);
const route = (v: unknown, max = MAX_ROUTE): v is number[] => Array.isArray(v) && v.length >= 2
  && v.length <= max && v.every((r) => integer(r));
const risk = (v: unknown): v is number => amount(v) && v <= 1;

function convoyRow(v: unknown, source: number): v is GrainConvoyRow {
  if (!object(v)) return false;
  const r = v;
  return name(r.id) && integer(r.convoy) && integer(r.source) && name(r.source_name) && integer(r.dest)
    && name(r.dest_name) && r.source !== r.dest && integer(r.buyer) && name(r.buyer_name) && integer(r.seller)
    && name(r.seller_name) && r.buyer !== r.seller && integer(r.dispatch_turn) && r.dispatch_turn <= source
    && oneOf(CONVOY_POLICIES)(r.policy) && route(r.route) && r.route[0] === r.source && r.route[r.route.length - 1] === r.dest
    && Array.isArray(r.route_names) && r.route_names.length === r.route.length
    && r.route_names.every((n) => n === null || name(n))
    && integer(r.leg) && r.leg < r.route.length && integer(r.progress) && integer(r.leg_turns)
    && (r.progress === 0) === (r.leg_turns === 0) && oneOf(CONVOY_STATUSES)(r.status)
    && typeof r.escorted === "boolean" && integer(r.escort_fee) && (r.escorted || r.escort_fee === 0)
    && [r.sent, r.net, r.cargo].every(amount) && (r.net as number) > 0 && (r.cargo as number) > 0
    && (r.sent as number) >= (r.net as number) && (r.cargo as number) <= (r.net as number) * (1 + 1e-9)
    && integer(r.paid, 1) && [r.waits, r.reroutes, r.threats, r.repelled].every((n) => integer(n))
    && (r.repelled as number) <= (r.threats as number)
    && route(r.exposed_route, 4) && risk(r.exposed_risk) && integer(r.exposed_turns, 1)
    && route(r.escorted_route, 4) && risk(r.escorted_risk) && integer(r.escorted_turns, 1);
}

function transitionRow(v: unknown, source: number): v is GrainConvoyTransition {
  if (!object(v)) return false;
  const r = v;
  if (!(name(r.id) && integer(r.convoy) && r.turn === source && oneOf(CONVOY_OPERATIONS)(r.operation)
    && integer(r.buyer) && name(r.buyer_name) && integer(r.source) && integer(r.dest) && integer(r.at)
    && name(r.at_name) && route(r.route) && integer(r.leg) && integer(r.progress) && name(r.status)
    && amount(r.cargo) && typeof r.escorted === "boolean" && typeof r.rerouted === "boolean"
    && typeof r.repelled === "boolean" && optional(r.closure, name) && optional(r.threat, name)
    && optional(r.threat_risk, risk) && optional(r.keeper, (k): k is number => integer(k, -1))
    && optional(r.sink, name) && optional(r.sink_region, (k): k is number => integer(k))
    && optional(r.captor, (k): k is number => integer(k))
    && optional(r.paid, (k): k is number => integer(k, 1)) && optional(r.escort_fee, (k): k is number => integer(k)))) return false;
  // A final operation names its own status; delivery records its keeper,
  // a capture its captor and market, every other ending its sink.
  if (FINAL.has(r.operation as string) !== (r.status === r.operation)) return false;
  if (r.operation === "arrived" && r.keeper === null) return false;
  if (r.operation === "captured" && (r.captor === null || r.sink_region === null)) return false;
  if (["captured", "lost", "returned", "stranded"].includes(r.operation as string) && r.sink === null) return false;
  if (r.operation === "dispatched" && (r.paid === null || r.escort_fee === null)) return false;
  return true;
}

/** The dated convoy record of a snapshot, or null (absent, stale or malformed). */
export function readGrainConvoys(snapshot: TurnSnapshot | null | undefined): GrainConvoysRecord | null {
  if (!snapshot) return null;
  const livelihoods = (snapshot as unknown as Row).livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const r = livelihoods.grain_convoys;
  if (!object(r) || r.schema_version !== 1 || !integer(r.source_turn) || r.source_turn !== snapshot.turn - 1) return null;
  const source = r.source_turn;
  if (typeof r.enabled !== "boolean" || !oneOf(CONVOY_POLICIES)(r.route_policy) || typeof r.moved !== "boolean"
    || typeof r.dispatch_ran !== "boolean" || !integer(r.active_count) || r.active_count > MAX_ACTIVE
    || !amount(r.in_transit_cargo) || !amount(r.returning_cargo)
    || !Array.isArray(r.active) || r.active.length !== r.active_count
    || !r.active.every((row) => convoyRow(row, source))) return null;
  const ids = new Set((r.active as GrainConvoyRow[]).map((row) => row.convoy));
  if (ids.size !== r.active.length) return null;
  if (!(r.transitions === null || (Array.isArray(r.transitions) && r.transitions.length <= MAX_FRAME
    && r.transitions.every((row) => transitionRow(row, source))))) return null;
  if (!object(r.counters) || !CONVOY_COUNTERS.every((key) => amount((r.counters as Row)[key]))) return null;
  const counters = Object.fromEntries(CONVOY_COUNTERS.map((key) => [key, (r.counters as Row)[key] as number])) as Record<ConvoyCounter, number>;
  return {
    source_turn: source, enabled: r.enabled, route_policy: r.route_policy, moved: r.moved,
    dispatch_ran: r.dispatch_ran, active_count: r.active_count, in_transit_cargo: r.in_transit_cargo,
    returning_cargo: r.returning_cargo, active: r.active as GrainConvoyRow[],
    transitions: r.transitions as GrainConvoyTransition[] | null, counters,
  };
}

/** True when the snapshot carries any convoy record, readable or not. */
export function hasGrainConvoysRecord(snapshot: TurnSnapshot | null | undefined): boolean {
  if (!snapshot) return false;
  const livelihoods = (snapshot as unknown as Row).livelihoods;
  return object(livelihoods) && Object.hasOwn(livelihoods, "grain_convoys");
}

/** Cumulative activation funnel from the recorded counters (whole run so far). */
export function convoyFunnel(record: GrainConvoysRecord) {
  const k = record.counters;
  return {
    eligible: k.eligible, noBudget: k.no_budget, noRoute: k.no_route, unaffordable: k.unaffordable,
    refused: k.capacity_refusals + k.identity_refusals, dispatched: k.dispatched,
    arrived: k.arrived, captured: k.captured, lost: k.lost, returned: k.returned, stranded: k.stranded,
    onRoad: record.active_count, delivered: k.delivered,
    escorted: k.escorted, escortPaid: k.escort_paid, escortWasted: k.escort_wasted,
  };
}
