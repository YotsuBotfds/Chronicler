import type { TurnSnapshot } from "../types";

/** The owner's dated knowledge of a stand: the timber account settled in ``turn``. */
export interface StockObservation {
  turn: number; stock: number; capacity: number; extraction: number; water_gate_open: boolean;
}
/** One protected timber slot's completed-turn account (``snapshot.livelihoods.commons_rules``). */
export interface CommonsReceipt {
  region_id: number; slot: number; owner: number; new: boolean; status: "quota" | "rest";
  observation: StockObservation;
  quota: number; stock_cap: number; required: number; institution_share: number; bill: number; paid: number;
  coverage: number; limit: number; applied: boolean; possible: boolean | null; extraction: number;
  /** Enforced mode: the harvest reached an applied limit. Null in cost_only. */
  binding: boolean | null;
  /** Cost_only: harvest above the limit the rule would have applied. Zero when enforced. */
  excess: number;
  city: number | null; grievance_added: number; neighbour_slots: number; neighbour_open_extraction: number;
  raw_imports: number | null; craft_output: number | null; farmer_income_modifier: number | null; food_sufficiency: number | null;
}
export interface CommonsDecision {
  turn: number; region_id: number; slot: number; civ: number; kind: "adopted" | "repealed" | "lapsed"; reason: string;
}
export interface CommonsRule {
  region_id: number; slot: number; owner: number; adopted_turn: number; status: "quota" | "rest";
  unfunded_turns: number; idle_turns: number; binding_turns: number; paid: number; grievance: number;
  observation: StockObservation | null;
}
export interface CommonsRulesRecord {
  schema_version: 1; units: { timber: "timber_goods"; money: "treasury" }; mode: "enforced" | "cost_only";
  source_turn: number; completed_turn: number; parameters: Record<string, number>;
  /** False: no Phase 2 was settled in the source turn; receipts and decisions are unknown, not empty. */
  observed: boolean;
  receipts: CommonsReceipt[] | null; decisions: CommonsDecision[] | null;
  rules: CommonsRule[]; counters: Record<string, number>;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const integer = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const share = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const optional = (x: unknown) => x === null || finite(x);
const STATUS = new Set(["quota", "rest"]);
const KINDS = new Set(["adopted", "repealed", "lapsed"]);
const PARAMETERS = ["adopt_below", "rest_below", "reopen_at", "repeal_at", "quota_share", "admin_cost",
  "unfunded_limit", "idle_limit", "cooldown_turns", "rule_grievance", "grievance_ceiling"] as const;
const TOLERANCE = 1e-9;

function validObservation(x: unknown, before: number): x is StockObservation {
  return object(x) && integer(x.turn) && x.turn < before && amount(x.stock) && amount(x.capacity)
    && amount(x.extraction) && typeof x.water_gate_open === "boolean";
}

function validReceipt(x: unknown, regionCount: number, record: { mode: string; source_turn: number }): x is CommonsReceipt {
  if (!object(x) || !integer(x.region_id) || x.region_id >= regionCount || !integer(x.slot) || x.slot > 2
    || !integer(x.owner) || typeof x.new !== "boolean" || !STATUS.has(x.status as string)
    || !validObservation(x.observation, record.source_turn)
    || ![x.quota, x.stock_cap, x.limit, x.extraction, x.excess, x.grievance_added, x.neighbour_open_extraction].every(amount)
    || ![x.required, x.bill, x.paid, x.neighbour_slots].every(integer) || !share(x.institution_share) || !share(x.coverage)
    || typeof x.applied !== "boolean" || !(x.possible === null || typeof x.possible === "boolean")
    || !(x.city === null || integer(x.city))
    || ![x.raw_imports, x.craft_output, x.farmer_income_modifier, x.food_sufficiency].every(optional)) return false;
  const row = x as unknown as CommonsReceipt;
  if (row.paid > row.bill || row.bill > row.required || row.required === 0) return false;
  if (Math.abs(row.coverage - Math.min(1, row.institution_share + row.paid / row.required)) > TOLERANCE) return false;
  if (row.status === "rest" && row.quota !== 0) return false;
  if (row.limit > row.stock_cap || row.applied !== row.limit < row.stock_cap) return false;
  if (record.mode === "enforced") {
    if (typeof row.binding !== "boolean" || row.excess !== 0) return false;
    if (row.applied && row.extraction > row.limit) return false;
    if (!row.applied && row.binding) return false;
  } else if (row.binding !== null || row.grievance_added !== 0 || (!row.applied && row.excess !== 0)) return false;
  if (row.city === null && row.grievance_added !== 0) return false;
  return row.neighbour_slots > 0 || row.neighbour_open_extraction === 0;
}

function validDecision(x: unknown, regionCount: number, turn: number): x is CommonsDecision {
  return object(x) && x.turn === turn && integer(x.region_id) && x.region_id < regionCount && integer(x.slot) && x.slot <= 2
    && finite(x.civ) && Number.isInteger(x.civ) && x.civ >= -1 && KINDS.has(x.kind as string) && typeof x.reason === "string";
}

function validRule(x: unknown, regionCount: number, completed: number): x is CommonsRule {
  return object(x) && integer(x.region_id) && x.region_id < regionCount && integer(x.slot) && x.slot <= 2
    && integer(x.owner) && integer(x.adopted_turn) && x.adopted_turn < completed && STATUS.has(x.status as string)
    && [x.unfunded_turns, x.idle_turns, x.binding_turns, x.paid].every(integer) && amount(x.grievance)
    && (x.observation === null || validObservation(x.observation, completed));
}

function unique<T extends { region_id: number; slot: number }>(rows: T[]): boolean {
  return new Set(rows.map((r) => `${r.region_id}:${r.slot}`)).size === rows.length;
}

/**
 * Strict reader: null when the record is absent, from another schema, dated to
 * another snapshot or malformed. Never borrows observations from other snapshots.
 */
export function commonsRulesAt(snapshot: TurnSnapshot | null, regionCount: number): CommonsRulesRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.commons_rules;
  if (!object(x) || x.schema_version !== 1 || !object(x.units) || x.units.timber !== "timber_goods" || x.units.money !== "treasury"
    || (x.mode !== "enforced" && x.mode !== "cost_only") || !integer(x.source_turn) || !integer(x.completed_turn)
    || x.completed_turn !== x.source_turn + 1 || x.completed_turn !== snapshot?.turn || typeof x.observed !== "boolean"
    || !object(x.parameters) || !PARAMETERS.every((key) => amount((x.parameters as Record<string, unknown>)[key]))
    || !object(x.counters) || !Object.values(x.counters).every(amount) || !Array.isArray(x.rules)) return null;
  const completed = x.completed_turn;
  if (!x.rules.every((rule) => validRule(rule, regionCount, completed)) || !unique(x.rules as CommonsRule[])) return null;
  if (!x.observed) return x.receipts === null && x.decisions === null ? x as unknown as CommonsRulesRecord : null;
  if (!Array.isArray(x.receipts) || !Array.isArray(x.decisions)) return null;
  const meta = { mode: x.mode, source_turn: x.source_turn };
  if (!x.receipts.every((item) => validReceipt(item, regionCount, meta)) || !unique(x.receipts as CommonsReceipt[])) return null;
  if (!x.decisions.every((item) => validDecision(item, regionCount, x.source_turn as number))) return null;
  return x as unknown as CommonsRulesRecord;
}

/** Turns a protected slot's harvest was held to the rule, as text. */
export function bindingLabel(row: CommonsReceipt): string {
  if (row.binding === null) return row.excess > 0 ? `Would withhold ${row.excess.toLocaleString(undefined, { maximumFractionDigits: 3 })}` : "Would not bind";
  if (!row.applied) return "Not tightened";
  return row.binding ? "Yes" : "No";
}
