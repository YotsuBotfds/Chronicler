import { readLivelihoodRecord } from "./livelihoodRecord";
import { isRecord as object, finite, amount, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/** One household at the fare gate (``snapshot.livelihoods.relocation_costs.households``). Money in milli-units. */
export interface RelocationHouseholdRecord {
  turn: number; lead: number; from_region: number; to_region: number;
  members: number[]; adults: number[]; children: number; liquid: number;
  reason: "passed" | "short" | "no_local_distress" | "route" | "trip" | "assisted";
  applied: boolean; fare: number; assistance: number; payer: number; movers_share: number;
  /** (id, requested, applied, residual, status) per adult debit. */
  debits: Array<[number, number, number, number, string]>;
  paid: number; residual: number; assistance_status: string | null; is_return: boolean;
}

/** A region's arrivals and departures this turn, and crowding before and after the moves. */
export interface RelocationRegionRecord {
  region: number; capacity: number; alive_before: number; alive_after: number;
  arrivals: number; arrival_households: number; assisted_households: number;
  departures: number; departure_households: number;
  pressure_before: number | null; pressure_after: number | null; food_sufficiency: number | null;
}

/** Last turn's arrivals at their destination this turn (null: unknown, never zero). */
export interface RelocationServiceRecord {
  region: number; arrival_turn: number; food_sufficiency: number | null;
  arrivals_rationed: number | null; arrivals_mean_ration: number | null;
  residents_rationed: number | null; residents_mean_ration: number | null;
}

export interface RelocationAssistanceRecord {
  civ: number; turn: number; granted: number; charged_coins: number; refused: number;
  status: "charged" | "controller_changed" | "treasury_short";
}

export interface RelocationRecord {
  schema_version: 1; stage: "L7"; mode: "paid" | "assisted" | "liquidity_only"; source_turn: number;
  /** Null: no relocation turn completed in the source turn (unknown, not zero). */
  gate: Record<string, number> | null;
  households: RelocationHouseholdRecord[] | null; households_dropped: number | null;
  regions: RelocationRegionRecord[] | null;
  services: RelocationServiceRecord[] | null;
  assistance: RelocationAssistanceRecord[] | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

const GATE_REASONS = ["passed", "short", "no_local_distress", "route", "trip", "assisted"] as const;

const integer = (x: unknown): x is number => finite(x) && Number.isInteger(x);
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown) => x === null || check(x);
const MODES = ["paid", "assisted", "liquidity_only"];
const ASSIST = ["charged", "controller_changed", "treasury_short"];

function validHousehold(x: unknown, regions: number, mode: string): boolean {
  if (!object(x) || !count(x.lead) || !count(x.from_region) || x.from_region >= regions || !count(x.to_region)
    || x.to_region >= regions || !Array.isArray(x.members) || x.members.length === 0 || !x.members.every(count)
    || !Array.isArray(x.adults) || !x.adults.every(count) || !count(x.children)
    || x.adults.length + x.children !== x.members.length || !GATE_REASONS.includes(x.reason as never)
    || typeof x.applied !== "boolean" || !count(x.fare) || !count(x.assistance) || !integer(x.payer)
    || !count(x.paid) || !count(x.residual) || !Array.isArray(x.debits)) return false;
  if (x.reason === "short" && x.applied) return false;                      // a blocked household never moved
  if (x.assistance > x.fare || (x.assistance > 0 && x.reason !== "assisted")) return false;
  if (x.movers_share !== x.fare - x.assistance) return false;
  if (!x.applied || mode === "liquidity_only") return x.debits.length === 0 && x.paid === 0;
  return x.paid + x.residual === (x.reason === "passed" || x.reason === "assisted" ? x.movers_share : 0);
}

function validRegion(x: unknown, regions: number): boolean {
  return object(x) && count(x.region) && x.region < regions && count(x.capacity) && count(x.alive_before)
    && count(x.alive_after) && count(x.arrivals) && count(x.departures) && count(x.arrival_households)
    && count(x.assisted_households) && x.assisted_households <= x.arrival_households
    && maybe(amount)(x.pressure_before) && maybe(amount)(x.pressure_after) && maybe(amount)(x.food_sufficiency);
}

function validService(x: unknown, regions: number): boolean {
  return object(x) && count(x.region) && x.region < regions && count(x.arrival_turn)
    && maybe(amount)(x.food_sufficiency) && maybe(count)(x.arrivals_rationed) && maybe(count)(x.residents_rationed)
    && maybe(amount)(x.arrivals_mean_ration) && maybe(amount)(x.residents_mean_ration);
}

function validAssistance(x: unknown): boolean {
  return object(x) && count(x.civ) && count(x.granted) && count(x.charged_coins) && count(x.refused)
    && ASSIST.includes(x.status as string)
    && (x.status === "charged" ? x.refused === 0 && x.charged_coins * 1000 >= x.granted : x.refused === x.granted);
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function relocationAt(snapshot: TurnSnapshot | null, regionCount: number): RelocationRecord | null {
  const x = readLivelihoodRecord(snapshot, "relocation_costs");
  if (!x || x.stage !== "L7" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !object(x.counters)
    || !Object.values(x.counters).every(amount) || !object(x.parameters)) return null;
  const mode = x.mode as string;
  if (x.gate !== null && !(object(x.gate) && Object.values(x.gate).every(count))) return null;
  if (x.households !== null && !(Array.isArray(x.households) && x.households.length <= 64
    && x.households.every((h) => validHousehold(h, regionCount, mode)))) return null;
  if (x.regions !== null && !(Array.isArray(x.regions) && x.regions.every((r) => validRegion(r, regionCount)))) return null;
  if (x.services !== null && !(Array.isArray(x.services) && x.services.every((s) => validService(s, regionCount)))) return null;
  if (x.assistance !== null && !(Array.isArray(x.assistance) && x.assistance.every(validAssistance))) return null;
  if (mode !== "assisted" && Array.isArray(x.households)
    && (x.households as RelocationHouseholdRecord[]).some((h) => h.assistance > 0)) return null;
  return x as unknown as RelocationRecord;
}

/** Funnel stages from the lifetime counters (households unless named). */
export function relocationFunnel(record: RelocationRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Households proposed", c("groups_proposed")],
    ["Passed with their own means", c("groups_passed")],
    ["Passed with assistance", c("groups_assisted")],
    ["Blocked: short of the fare", c("groups_short")],
    ["Unpriced (route or trip)", c("groups_unpriced")],
    ["Moved", c("groups_applied")],
    ["Paid a fare", c("groups_paid")],
    ["With an unpaid residual", c("groups_with_residual")],
  ];
}

/** Milli-units as wealth units. */
export const units = (milli: number) => milli / 1000;
