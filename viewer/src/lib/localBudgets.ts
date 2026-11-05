import type { TurnSnapshot } from "../types";

/** One candidate expenditure of a civ-turn (``decisions[].proposals``). */
export interface BudgetProposalRecord {
  pid: number; service: string; civ: number; source_turn: number; recipients: number[]; site: number | null;
  claims: string[]; cost: number; divisible: boolean; unit: string; expected: number;
  /** Burden relieved per constituency at full cost, in the constituency's own unit. */
  relief: Record<string, number>;
  detail: Record<string, number | string | null>;
}

export interface BudgetAwardRecord { pid: number; amount: number; sponsor: string | null }

/** One ruler's budget decision, made in Phase 10 of ``turn`` for the next turn. */
export interface BudgetDecisionRecord {
  turn: number; civ: number; mode: string; seat: number | null; projected: number; floor: number;
  obligations: number; committed: number; budget: number; influence: Record<string, number>;
  /** Measured burden per constituency; null is unknown, not zero. */
  burdens: Record<string, number | null>;
  proposals: BudgetProposalRecord[]; dropped: number;
  candidates: Record<string, number[][]>; satisfaction: Record<string, Record<string, number>>;
  scores: Record<string, number>; chosen: string | null; outcome: string | null;
  awards: BudgetAwardRecord[]; refused: Array<[number, string]>;
}

/** An envelope: spending authority for one service for one turn, and its settlement. */
export interface BudgetCommitmentRecord {
  cid: number; civ: number; service: string; pid: number; decided_turn: number; for_turn: number;
  recipients: number[]; site: number | null; claims: string[]; amount: number; unit: string; expected: number;
  sponsor: string | null; venue: number | null;
  outcome: "kept" | "deferred" | "lapsed" | null; reason: string | null; spent: number | null;
  delivered: number | null; ratio: number | null; settled_turn: number | null; response: number | null;
  detail: Record<string, number | string | null>;
}

export interface BudgetResponseRecord {
  turn: number; civ: number; settlement_id: number; before: number; raw: number; applied: number; after: number;
}

export interface LocalBudgetsRecord {
  schema_version: 1; stage: "L9"; mode: "bargained" | "fixed_shares"; source_turn: number;
  /** Null: no decision, settlement or response in the source turn (unknown, not zero). */
  decisions: BudgetDecisionRecord[] | null;
  settled: BudgetCommitmentRecord[] | null;
  responses: BudgetResponseRecord[] | null;
  open: BudgetCommitmentRecord[];
  counters: Record<string, number>;
  parameters: Record<string, unknown>;
}

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => finite(x) && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => finite(x) && x >= 0;
const nullable = <T>(x: unknown, check: (v: unknown) => v is T) => x === null || check(x);
const numbers = (x: unknown, check: (v: unknown) => boolean) => object(x) && Object.values(x).every(check);
const MODES = ["bargained", "fixed_shares"];
const OUTCOMES = ["kept", "deferred", "lapsed"];
const EPS = 1e-6;

function validProposal(x: unknown, turn: number, civ: number): x is BudgetProposalRecord {
  return object(x) && count(x.pid) && typeof x.service === "string" && x.civ === civ && x.source_turn === turn
    && Array.isArray(x.recipients) && x.recipients.every(count) && nullable(x.site, count)
    && Array.isArray(x.claims) && x.claims.every((c) => typeof c === "string")
    && count(x.cost) && x.cost >= 1 && typeof x.divisible === "boolean" && typeof x.unit === "string"
    && amount(x.expected) && numbers(x.relief, amount) && object(x.detail);
}

function validDecision(x: unknown, source: number, civs: number): x is BudgetDecisionRecord {
  if (!object(x) || x.turn !== source || !count(x.civ) || x.civ >= civs || !count(x.budget)
    || !finite(x.projected) || !count(x.floor) || !count(x.obligations) || !count(x.committed)
    || !nullable(x.seat, count) || !numbers(x.influence, amount)
    || !numbers(x.burdens, (v) => v === null || amount(v)) || !count(x.dropped)
    || !Array.isArray(x.proposals) || x.proposals.length > 8
    || !x.proposals.every((p, i) => validProposal(p, source, x.civ as number) && p.pid === i)
    || !Array.isArray(x.awards) || !Array.isArray(x.refused)) return false;
  const proposals = x.proposals as BudgetProposalRecord[];
  let spent = 0;
  const claims = new Set<string>();
  for (const a of x.awards) {
    if (!object(a) || !count(a.pid) || a.pid >= proposals.length || !count(a.amount) || a.amount < 1
      || a.amount > proposals[a.pid].cost || !nullable(a.sponsor, (v): v is string => typeof v === "string")) return false;
    spent += a.amount;
    for (const c of proposals[a.pid].claims) {
      if (claims.has(c)) return false;          // incompatible promises never coexist
      claims.add(c);
    }
  }
  return spent <= (x.budget as number)
    && x.refused.every((r) => Array.isArray(r) && r.length === 2 && count(r[0]) && r[0] < proposals.length && typeof r[1] === "string");
}

function validCommitment(x: unknown, civs: number): x is BudgetCommitmentRecord {
  if (!object(x) || !count(x.cid) || !count(x.civ) || x.civ >= civs || typeof x.service !== "string"
    || !count(x.decided_turn) || !count(x.for_turn) || x.for_turn <= x.decided_turn
    || !Array.isArray(x.recipients) || !x.recipients.every(count) || !count(x.amount) || x.amount < 1
    || !amount(x.expected) || !nullable(x.site, count) || !nullable(x.venue, count)
    || !(x.outcome === null || OUTCOMES.includes(x.outcome as string))
    || !nullable(x.spent, count) || !nullable(x.delivered, amount) || !nullable(x.ratio, amount)
    || !nullable(x.response, finite)) return false;
  return x.spent === null || (x.spent as number) <= (x.amount as number);
}

function validResponse(x: unknown, source: number, civs: number): x is BudgetResponseRecord {
  return object(x) && x.turn === source && count(x.civ) && x.civ < civs && count(x.settlement_id)
    && amount(x.before) && x.before <= 1 && amount(x.after) && x.after <= 1 && finite(x.raw) && finite(x.applied)
    && Math.abs((x.after as number) - (x.before as number) - (x.applied as number)) <= EPS;
}

/** Strict reader of ``snapshot.livelihoods.local_budgets``; null when absent,
 * from another schema, misdated or malformed. Unknown values stay null. */
export function localBudgetsAt(snapshot: TurnSnapshot | null, civCount: number): LocalBudgetsRecord | null {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const livelihoods = row?.livelihoods;
  if (!object(livelihoods) || livelihoods.schema_version !== 1) return null;
  const x = livelihoods.local_budgets;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "L9" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn || !object(x.counters)
    || !numbers(x.counters, finite) || !object(x.parameters) || !Array.isArray(x.open)) return null;
  const source = x.source_turn;
  if (!x.open.every((c) => validCommitment(c, civCount) && c.outcome === null && c.for_turn > source)) return null;
  if (x.decisions !== null && !(Array.isArray(x.decisions) && x.decisions.every((d) => validDecision(d, source, civCount)))) return null;
  if (x.settled !== null && !(Array.isArray(x.settled)
    && x.settled.every((c) => validCommitment(c, civCount) && c.outcome !== null && c.settled_turn === source))) return null;
  if (x.responses !== null && !(Array.isArray(x.responses) && x.responses.every((r) => validResponse(r, source, civCount)))) return null;
  if (x.settled === null && x.responses !== null && x.responses.length > 0) return null;
  return x as unknown as LocalBudgetsRecord;
}

/** The services an adopted allocation funded, as "service amount" in award order. */
export function awardedServices(decision: BudgetDecisionRecord): string[] {
  return decision.awards.map((a) => `${decision.proposals[a.pid].service.replace(/_/g, " ")} ${a.amount}`);
}
