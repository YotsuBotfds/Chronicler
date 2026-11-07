import type { Bundle, TurnSnapshot } from "../types";
import { readRecord, type RecordReading } from "./recordReading";

export interface PublicHealthSupply {
  turn: number; civ: number; region: number; source: number | null; seller: number | null;
  need_milli: number; food_milli: number; charged_milli: number; internal_milli: number;
  price_milli: number | null; patients: number; reason: string;
}
export interface PublicHealthDecision {
  civ: number; target: number; report_ids: number[]; expected_loss_units: number; cost_units: number;
  goods_contact_cost_proxy: number; fatality_observed: boolean; close: boolean;
}
export interface PublicHealthEnvironment {
  region: number; source_turn: number; residence_observed: boolean; sanitation_observed: boolean;
  displaced_share: number; water_service: number; crowding_factor: number; flux_factor: number;
}
export interface PublicHealthRecord {
  schema_version: 1; source_turn: number; enabled: boolean; mode: "active" | "cost_only";
  policy: "evidence" | "shuffled"; report_delay: number; report_turn: number | null;
  decisions: PublicHealthDecision[]; environment_turn: number | null; environment: PublicHealthEnvironment[];
  supply_turn: number | null; supplies: PublicHealthSupply[]; totals: Record<string, number>;
  guard_turn: number | null; guards: PublicHealthGuard[];
}
export interface PublicHealthGuard {
  turn: number; civ: number; target: number; need: number; work: number; staffed: boolean; payment: string;
  members: { agent_id: number; region: number; share: number; wage_due_milli: number; wage_paid_milli: number;
    wage_residual_milli: number; income_withheld: number | null }[];
}
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nonnegative = (v: unknown): v is number => number(v) && v >= 0;
const integer = (v: unknown): v is number => nonnegative(v) && Number.isInteger(v);
const idx = (v: unknown, size: number): boolean => integer(v) && v < size;
const nullableIdx = (v: unknown, size: number): boolean => v === null || idx(v, size);
const share = (v: unknown): boolean => number(v) && v >= 0 && v <= 1;

export function publicHealthAt(snapshot: TurnSnapshot, regions: number, civs: number): PublicHealthRecord | null {
  const container = (snapshot as unknown as Record<string, unknown>).livelihoods;
  const r = object(container) ? container.public_health : undefined;
  if (!object(r) || r.schema_version !== 1 || r.source_turn !== snapshot.turn - 1
    || typeof r.enabled !== "boolean" || !["active", "cost_only"].includes(String(r.mode))
    || !["evidence", "shuffled"].includes(String(r.policy)) || !integer(r.report_delay) || r.report_delay > 20
    || ![r.report_turn, r.environment_turn, r.supply_turn].every(t => t === null || t === r.source_turn)
    || !Array.isArray(r.supplies) || !Array.isArray(r.decisions) || !Array.isArray(r.environment)
    || !object(r.totals) || !Object.values(r.totals).every(nonnegative)) return null;
  if (!r.supplies.every(s => object(s) && s.turn === r.source_turn && idx(s.civ, civs) && idx(s.region, regions)
    && nullableIdx(s.source, regions) && nullableIdx(s.seller, civs)
    && [s.need_milli, s.food_milli, s.charged_milli, s.internal_milli].every(integer)
    && Number(s.food_milli) <= Number(s.need_milli) && nonnegative(s.patients)
    && (s.price_milli === null || integer(s.price_milli) && s.price_milli > 0) && typeof s.reason === "string")) return null;
  if (!r.decisions.every(d => object(d) && idx(d.civ, civs) && idx(d.target, civs) && d.civ !== d.target
    && Array.isArray(d.report_ids) && d.report_ids.every(integer)
    && [d.expected_loss_units, d.cost_units, d.goods_contact_cost_proxy].every(nonnegative)
    && typeof d.close === "boolean" && typeof d.fatality_observed === "boolean")) return null;
  if (!r.environment.every(e => object(e) && idx(e.region, regions) && e.source_turn === Number(r.source_turn) - 1
    && typeof e.residence_observed === "boolean" && typeof e.sanitation_observed === "boolean"
    && share(e.displaced_share) && share(e.water_service) && number(e.crowding_factor)
    && e.crowding_factor >= 1 && e.crowding_factor <= 1.25 && share(e.flux_factor))) return null;
  if (r.guard_turn !== undefined && r.guard_turn !== null && r.guard_turn !== r.source_turn) return null;
  if (r.guards !== undefined && (!Array.isArray(r.guards) || !r.guards.every(g => object(g)
    && g.turn === r.source_turn && idx(g.civ, civs) && idx(g.target, civs) && g.civ !== g.target
    && nonnegative(g.need) && nonnegative(g.work) && g.work <= g.need
    && typeof g.staffed === "boolean" && typeof g.payment === "string" && Array.isArray(g.members)
    && g.members.every(m => object(m) && integer(m.agent_id) && idx(m.region, regions) && share(m.share)
      && [m.wage_due_milli, m.wage_paid_milli, m.wage_residual_milli].every(integer)
      && (g.payment !== "paid" || Number(m.wage_paid_milli) + Number(m.wage_residual_milli) === m.wage_due_milli)
      && (m.income_withheld === null || nonnegative(m.income_withheld)))))) return null;
  return { ...r, guard_turn: r.guard_turn ?? null, guards: r.guards ?? [] } as unknown as PublicHealthRecord;
}

export const readPublicHealth = (bundle: Bundle, snapshot: TurnSnapshot | null, turn?: number): RecordReading<PublicHealthRecord> =>
  readRecord({ key: "public_health", label: "Public health", flag: "--public-health", livelihoods: true,
    carries: s => {
      const l = (s as unknown as Record<string, unknown>).livelihoods;
      return object(l) && l.public_health !== undefined && l.public_health !== null;
    }, read: publicHealthAt,
    observed: r => r.environment_turn !== null || r.supply_turn !== null || r.report_turn !== null,
    empty: r => r.supplies.length === 0 && r.decisions.length === 0 && r.environment.every(e => e.displaced_share === 0 && e.water_service === 0),
    zero: "no patient supplies, delivered foreign reports or water service" }, bundle, snapshot, turn);
