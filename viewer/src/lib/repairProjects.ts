import type { TurnSnapshot } from "../types";

/** One repair or reconstruction project (``snapshot.livelihoods.repair_projects``). */
export interface RepairProjectRecord {
  pid: number; kind: "granary" | "workshop";
  /** Granary: the region index; workshop: the L1 site id. */
  asset: number; region: number; settlement_id: number | null;
  cause: "wear" | "war"; war_key: string | null; war_start_turn: number | null; damages: number[];
  opened_turn: number; opened_condition: number; controller: number;
  /** Work units the deficit needed at opening plus every attached war damage. */
  scope: number; delivered: number; credited: number;
  status: "open" | "completed" | "abandoned"; closed_turn: number | null; closed_reason: string | null;
  work_turns: number; stalled_turns: number; stalls: Record<string, number>;
  timber_used: number; wages_milli: number; coin_cost_milli: number;
  last_crew: number[]; history: Array<[number, string, number, number]>;
}

export interface WarDamageRecord {
  did: number; turn: number; kind: "granary" | "workshop"; asset: number; region: number;
  event: "conquest" | "sack" | "seizure"; war_key: string | null; war_start_turn: number | null;
  amount: number; condition_before: number; condition_after: number; project: number | null;
}

/** One open project's completed Phase 2 of the source turn. */
export interface RepairReceiptRecord {
  turn: number; pid: number; kind: "granary" | "workshop"; asset: number; region: number; payer: number;
  status: "progress" | "stalled"; reasons: string[];
  requested: number; delivered: number; credited: number; rate: number | null;
  crew: number[]; share: number | null; qualified: number[]; veterans: number[];
  timber_held: number; timber_used: number; timber_returned: number;
  wages_due_milli: number; wages_milli: number; wage_residual_milli: number; coin_cost_milli: number;
  envelope: number | null; condition_before: number; condition_after: number; remaining_after: number;
  /** Ordinary income the wealth phase withheld for the paid share; null: not observed. */
  income_replaced: number | null;
}

/** One civilization's repair accounts: whole units charged once a turn, the
 * sub-unit remainder prepaid toward its next repair costs. */
export interface CivLedgerRecord {
  turn: number; civ: number; projects: number; work_delivered: number; timber_used: number;
  coin_cost_milli: number; wages_due_milli: number; wages_applied_milli: number; wage_residual_milli: number;
  charged: number; prepaid_before_milli: number; prepaid_after_milli: number; envelope: number | null;
}

export interface UnmetNeedRecord {
  kind: "granary" | "workshop"; asset: number; region: number; condition: number; reason: string;
}

export interface RepairProjectsRecord {
  schema_version: 1; stage: "RS2"; mode: "repair" | "cost_only"; source_turn: number;
  units: Record<string, string | number>;
  projects: RepairProjectRecord[]; closed: RepairProjectRecord[]; damages: WarDamageRecord[];
  /** Null: no Phase 2 was completed in the source turn (unknown, not zero). */
  receipts: RepairReceiptRecord[] | null;
  ledger: CivLedgerRecord[] | null;
  unmet: UnmetNeedRecord[] | null;
  suspended: number[] | null;
  /** civ index -> milli-units charged and not yet used (each below one unit). */
  prepaid: Record<string, number>;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

/** Declaration order (append only); ``no_people`` is the PL3 correction: a granary
 * project suspended while its region has no farmer. */
export const REASONS = ["no_timber", "no_coins", "no_labor", "no_envelope", "unqualified", "no_people"] as const;
const KINDS = ["granary", "workshop"];
const CAUSES = ["wear", "war"];
const MODES = ["repair", "cost_only"];
const EVENTS = ["conquest", "sack", "seizure"];
const ABANDON = ["asset_closed", "no_controller", "switched_off"];
const UNMET = ["no_controller", "zero_capacity", "building", "no_people"];
const MAX_CREW = 4;
const EPS = 1e-6;

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const integer = (x: unknown): x is number => finite(x) && Number.isInteger(x);
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const unit = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const ids = (x: unknown, max = MAX_CREW): x is number[] =>
  Array.isArray(x) && x.length <= max && x.every(count) && new Set(x).size === x.length;
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown) => x === null || check(x);
const near = (a: number, b: number) => Math.abs(a - b) <= EPS * Math.max(1, Math.abs(a), Math.abs(b));

function validProject(x: unknown, regions: number, open: boolean): boolean {
  if (!object(x) || !count(x.pid) || !KINDS.includes(x.kind as string) || !count(x.asset) || !count(x.region)
    || x.region >= regions || !maybe(count)(x.settlement_id) || !CAUSES.includes(x.cause as string)
    || !maybe((v): v is string => typeof v === "string")(x.war_key) || !maybe(count)(x.war_start_turn)
    || !Array.isArray(x.damages) || !x.damages.every(count) || !count(x.opened_turn) || !unit(x.opened_condition)
    || !integer(x.controller) || !amount(x.scope) || !amount(x.delivered) || !amount(x.credited)
    || x.credited > (x.delivered as number) + EPS || !count(x.work_turns) || !count(x.stalled_turns)
    || !object(x.stalls) || !Object.entries(x.stalls).every(([k, v]) => REASONS.includes(k as never) && count(v))
    || !amount(x.timber_used) || !count(x.wages_milli) || !count(x.coin_cost_milli) || !ids(x.last_crew)
    || !Array.isArray(x.history)) return false;
  if ((x.war_key === null) !== (x.war_start_turn === null)) return false;
  if (x.kind === "granary" && (x.asset !== x.region || x.last_crew.length > 0)) return false;
  if (open) return x.status === "open" && x.closed_turn === null && (x.delivered as number) < (x.scope as number) + EPS;
  if (!count(x.closed_turn)) return false;
  if (x.status === "completed") return (x.delivered as number) >= (x.scope as number) - EPS;
  return x.status === "abandoned" && ABANDON.includes(x.closed_reason as string);
}

function validDamage(x: unknown, regions: number): boolean {
  return object(x) && count(x.did) && count(x.turn) && KINDS.includes(x.kind as string) && count(x.asset)
    && count(x.region) && x.region < regions && EVENTS.includes(x.event as string)
    && (x.war_key === null) === (x.war_start_turn === null)
    && (x.war_key === null || typeof x.war_key === "string") && maybe(count)(x.war_start_turn)
    && unit(x.amount) && (x.amount as number) > 0 && unit(x.condition_before) && unit(x.condition_after)
    && near((x.condition_before as number) - (x.amount as number), x.condition_after as number)
    && maybe(count)(x.project);
}

function validReceipt(x: unknown, regions: number, source: number, mode: string): boolean {
  if (!object(x) || x.turn !== source || !count(x.pid) || !KINDS.includes(x.kind as string) || !count(x.asset)
    || !count(x.region) || x.region >= regions || !integer(x.payer) || x.payer < 0
    || !["progress", "stalled"].includes(x.status as string) || !Array.isArray(x.reasons)
    || !x.reasons.every((r) => REASONS.includes(r as never)) || !amount(x.requested) || !amount(x.delivered)
    || !amount(x.credited) || !maybe(unit)(x.rate) || !ids(x.crew) || !maybe(unit)(x.share)
    || !ids(x.qualified) || !ids(x.veterans) || !amount(x.timber_held) || !amount(x.timber_used)
    || !amount(x.timber_returned) || !count(x.wages_due_milli) || !count(x.wages_milli)
    || !count(x.wage_residual_milli) || !count(x.coin_cost_milli) || !maybe(count)(x.envelope)
    || !unit(x.condition_before) || !unit(x.condition_after) || !amount(x.remaining_after)
    || !maybe(amount)(x.income_replaced)) return false;
  const delivered = x.delivered as number;
  if (delivered > (x.requested as number) + EPS) return false;          // never beyond the plan
  if ((x.status === "progress") !== (delivered > 0)) return false;
  if (mode === "cost_only" ? x.credited !== 0 : !near(x.credited as number, delivered)) return false;
  if (!near(x.timber_held as number, (x.timber_used as number) + (x.timber_returned as number))) return false;
  if ((x.wages_milli as number) + (x.wage_residual_milli as number) !== x.wages_due_milli) return false;
  const crew = new Set(x.crew as number[]);
  if (!(x.qualified as number[]).every((a) => crew.has(a)) || !(x.veterans as number[]).every((a) => crew.has(a))) return false;
  if (x.kind === "granary") return crew.size === 0 && x.wages_due_milli === 0;
  return x.coin_cost_milli === 0;
}

function validLedger(x: unknown, civs: number, source: number): boolean {
  return object(x) && x.turn === source && count(x.civ) && x.civ < civs && count(x.projects)
    && amount(x.work_delivered) && amount(x.timber_used) && count(x.coin_cost_milli) && count(x.wages_due_milli)
    && count(x.wages_applied_milli) && count(x.wage_residual_milli) && count(x.charged)
    && count(x.prepaid_before_milli) && x.prepaid_before_milli < 1000
    && count(x.prepaid_after_milli) && x.prepaid_after_milli < 1000 && maybe(count)(x.envelope)
    && x.charged * 1000 + x.prepaid_before_milli === x.coin_cost_milli + x.wages_applied_milli + x.prepaid_after_milli
    && x.wages_applied_milli + x.wage_residual_milli === x.wages_due_milli
    && (x.envelope === null || x.charged <= (x.envelope as number));
}

function validUnmet(x: unknown, regions: number): boolean {
  return object(x) && KINDS.includes(x.kind as string) && count(x.asset) && count(x.region) && x.region < regions
    && unit(x.condition) && UNMET.includes(x.reason as string);
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function repairProjectsAt(snapshot: TurnSnapshot | null, regionCount: number, civCount: number): RepairProjectsRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.repair_projects;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "RS2" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !object(x.units)
    || !Array.isArray(x.projects) || x.projects.length > regionCount + 4
    || !x.projects.every((p) => validProject(p, regionCount, true))
    || !Array.isArray(x.closed) || x.closed.length > 16 || !x.closed.every((p) => validProject(p, regionCount, false))
    || !Array.isArray(x.damages) || x.damages.length > 32 || !x.damages.every((d) => validDamage(d, regionCount))
    || !object(x.prepaid) || !Object.entries(x.prepaid).every(([k, v]) => /^\d+$/.test(k) && Number(k) < civCount
      && count(v) && v > 0 && v < 1000)
    || !object(x.counters) || !Object.values(x.counters).every(finite) || !object(x.parameters)) return null;
  const projects = x.projects as RepairProjectRecord[];
  const assets = new Set(projects.map((p) => `${p.kind}:${p.asset}`));
  if (assets.size !== projects.length) return null;                     // one open project per asset
  if (x.mode === "cost_only" && [...projects, ...(x.closed as RepairProjectRecord[])].some((p) => p.credited > 0)) return null;
  const source = x.source_turn as number;
  if ((x.receipts === null) !== (x.ledger === null)) return null;
  if (x.receipts !== null && !(Array.isArray(x.receipts)
    && x.receipts.every((r) => validReceipt(r, regionCount, source, x.mode as string)))) return null;
  if (x.ledger !== null && !(Array.isArray(x.ledger) && x.ledger.every((r) => validLedger(r, civCount, source)))) return null;
  if (x.unmet !== null && !(Array.isArray(x.unmet) && x.unmet.every((u) => validUnmet(u, regionCount)))) return null;
  if (x.suspended !== null && !(Array.isArray(x.suspended) && x.suspended.every((r) => count(r) && r < regionCount))) return null;
  if (Array.isArray(x.receipts)) {
    // A worker is on at most one crew; the ledger sums its civ's receipts.
    const crew = (x.receipts as RepairReceiptRecord[]).flatMap((r) => r.crew);
    if (new Set(crew).size !== crew.length) return null;
    for (const l of x.ledger as CivLedgerRecord[]) {
      const mine = (x.receipts as RepairReceiptRecord[]).filter((r) => r.payer === l.civ);
      if (mine.length !== l.projects
        || mine.reduce((s, r) => s + r.coin_cost_milli, 0) !== l.coin_cost_milli
        || mine.reduce((s, r) => s + r.wages_milli, 0) !== l.wages_applied_milli) return null;
    }
  }
  return x as unknown as RepairProjectsRecord;
}

/** Activation funnel from the lifetime counters (zero only once the record exists). */
export function repairFunnel(record: RepairProjectsRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Projects opened for wear", c("opened_wear")],
    ["Projects opened after war damage", c("opened_war")],
    ["Project-turns with work", c("progress_turns")],
    ["Project-turns stalled", c("stalled_turns")],
    ["Projects completed", c("completed")],
    ["Projects abandoned", c("abandoned_asset_closed") + c("abandoned_no_controller") + c("abandoned_switched_off")],
    ["War damage records", c("damages")],
    ["Named repairer-turns", c("crew_person_turns")],
  ];
}

/** Share of the scope delivered, in [0, 1]. */
export function progress(p: RepairProjectRecord): number {
  return p.scope > 0 ? Math.min(1, p.delivered / p.scope) : 1;
}
