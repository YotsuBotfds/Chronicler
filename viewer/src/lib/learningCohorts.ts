import { readLivelihoodRecord } from "./livelihoodRecord";
import { isRecord as object, finite, amount, count } from "./recordGuards";
import type { TurnSnapshot } from "../types";

/** One enrolled person (``snapshot.livelihoods.learning_cohorts.cohorts[].members``). */
export interface CohortMemberRecord {
  agent_id: number; joined_turn: number; occupation: number; skill_at_join: number;
  attended: number; last_attended_turn: number | null; absent_streak: number;
  status: "active" | "completed" | "exited";
  completed_turn: number | null; exit_turn: number | null; exit_reason: string | null;
  /** At completion: the learned trade's skill before and after (equal in the no-learning control). */
  skill_before: number | null; skill_after: number | null;
}

/** An open cohort of one academy incarnation. */
export interface CohortRecord {
  cohort_id: number; seat_id: number; region: number; founder: number; founded_turn: number;
  seat_name: string; formed_turn: number; status: "open" | "closed";
  closed_turn: number | null; closed_reason: string | null;
  members: CohortMemberRecord[]; sessions: number; idle_streak: number; last_session_turn: number | null;
}

/** A closed cohort, summarized. */
export interface ArchivedCohortRecord {
  cohort_id: number; seat_id: number; region: number; seat_name: string; formed_turn: number;
  closed_turn: number | null; closed_reason: string | null; sessions: number;
  members: number; completed: number; exited: number;
}

/** One cohort's completed turn. ``attended`` never exceeds the academy's delivered learners. */
export interface CohortReceiptRecord {
  turn: number; cohort_id: number; seat_id: number; region: number; members_active: number;
  available: number[]; unavailable: Record<string, number>; reserved: number[];
  attended: number[]; no_seat: number[]; absent: number[];
  session: boolean; no_session_reason: string | null;
  teaching_work_delivered: number | null; teaching_learners_delivered: number | null;
  income_charged: number; supplies_used: number;
  completed: number[]; exited: Record<string, number[]>;
}

export interface GraduateRecord {
  agent_id: number; cohort_id: number; region: number; occupation: number; completed_turn: number;
  skill_before: number; skill_after: number; granted: boolean;
}

export interface LearningCohortsRecord {
  schema_version: 1; stage: "L5"; mode: "learn" | "no_learning"; source_turn: number;
  cohorts: CohortRecord[]; archive: ArchivedCohortRecord[]; graduates: GraduateRecord[];
  /** Null: no cohort turn was completed in the source turn (unknown, not zero). */
  receipts: CohortReceiptRecord[] | null;
  counters: Record<string, number>;
  parameters: Record<string, number>;
}

export const OCCUPATIONS = ["Farmer", "Soldier", "Merchant", "Scholar", "Priest"] as const;

const skill = (x: unknown): x is number => finite(x) && x >= 0 && x <= 1;
const ids = (x: unknown, max = 8): x is number[] => Array.isArray(x) && x.length <= max && x.every(count);
const maybe = <T,>(check: (v: unknown) => v is T) => (x: unknown) => x === null || check(x);
const MODES = ["learn", "no_learning"];
const STATUSES = ["active", "completed", "exited"];

function validMember(x: unknown): boolean {
  if (!object(x) || !count(x.agent_id) || !count(x.joined_turn) || !count(x.occupation) || x.occupation > 4
    || !skill(x.skill_at_join) || !count(x.attended) || !count(x.absent_streak)
    || !STATUSES.includes(x.status as string) || !maybe(count)(x.last_attended_turn)
    || !maybe(skill)(x.skill_before) || !maybe(skill)(x.skill_after)) return false;
  if (x.status === "completed") {
    return count(x.completed_turn) && skill(x.skill_before) && skill(x.skill_after)
      && (x.skill_after as number) >= (x.skill_before as number);
  }
  return x.status !== "exited" || (count(x.exit_turn) && typeof x.exit_reason === "string");
}

function validCohort(x: unknown, regions: number): boolean {
  return object(x) && count(x.cohort_id) && count(x.seat_id) && count(x.region) && x.region < regions
    && typeof x.seat_name === "string" && count(x.formed_turn) && x.status === "open" && count(x.sessions)
    && count(x.idle_streak) && Array.isArray(x.members) && x.members.length <= 8 && x.members.every(validMember);
}

function validArchived(x: unknown, regions: number): boolean {
  return object(x) && count(x.cohort_id) && count(x.region) && x.region < regions && typeof x.seat_name === "string"
    && count(x.sessions) && count(x.members) && x.members <= 8 && count(x.completed) && count(x.exited)
    && x.completed + x.exited <= x.members;
}

function validGraduate(x: unknown, regions: number): boolean {
  return object(x) && count(x.agent_id) && count(x.cohort_id) && count(x.region) && x.region < regions
    && count(x.occupation) && x.occupation <= 4 && count(x.completed_turn) && skill(x.skill_before)
    && skill(x.skill_after) && x.skill_after >= x.skill_before && typeof x.granted === "boolean"
    && x.granted === x.skill_after > x.skill_before;
}

function validReceipt(x: unknown, regions: number, source: number): boolean {
  if (!object(x) || x.turn !== source || !count(x.cohort_id) || !count(x.region) || x.region >= regions
    || !ids(x.reserved) || !ids(x.attended) || !ids(x.no_seat) || !ids(x.absent) || !ids(x.completed)
    || typeof x.session !== "boolean" || !amount(x.income_charged) || !amount(x.supplies_used)
    || !maybe(amount)(x.teaching_work_delivered) || !maybe(amount)(x.teaching_learners_delivered)
    || !object(x.unavailable) || !object(x.exited)) return false;
  const reserved = new Set(x.reserved);
  const outcomes = [...x.attended, ...x.no_seat, ...x.absent];
  if (outcomes.length !== reserved.size || !outcomes.every((id) => reserved.has(id))) return false;
  if (x.session !== x.attended.length > 0) return false;
  if (x.attended.length > 0 && (x.teaching_learners_delivered === null
    || x.attended.length > Math.floor((x.teaching_learners_delivered as number) + 1e-6))) return false;
  return x.attended.length > 0 || x.income_charged === 0;
}

/** Strict reader; null when absent, from another schema, misdated or malformed. */
export function learningCohortsAt(snapshot: TurnSnapshot | null, regionCount: number): LearningCohortsRecord | null {
  const x = readLivelihoodRecord(snapshot, "learning_cohorts");
  if (!x || x.stage !== "L5" || !MODES.includes(x.mode as string)
    || !count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn
    || !Array.isArray(x.cohorts) || x.cohorts.length > 8 || !x.cohorts.every((c) => validCohort(c, regionCount))
    || !Array.isArray(x.archive) || x.archive.length > 16 || !x.archive.every((c) => validArchived(c, regionCount))
    || !Array.isArray(x.graduates) || x.graduates.length > 32
    || !x.graduates.every((g) => validGraduate(g, regionCount))
    || !object(x.counters) || !Object.values(x.counters).every(amount) || !object(x.parameters)) return null;
  if (x.mode === "no_learning" && (x.graduates as GraduateRecord[]).some((g) => g.granted)) return null;
  if (x.receipts !== null && !(Array.isArray(x.receipts)
    && x.receipts.every((r) => validReceipt(r, regionCount, x.source_turn as number)))) return null;
  return x as unknown as LearningCohortsRecord;
}

/** Funnel stages from the lifetime counters; missing counters are zero only once the record exists. */
export function learningFunnel(record: LearningCohortsRecord): Array<[string, number]> {
  const c = (key: string) => record.counters[key] ?? 0;
  return [
    ["Academy-turns observed", c("academy_turns")],
    ["Cohorts formed", c("cohorts_formed")],
    ["Learners enrolled", c("learners_enrolled")],
    ["Learner-turns reserved", c("learner_turns_reserved")],
    ["Sessions (teacher and supplies delivered)", c("sessions")],
    ["Learner-turns attended", c("learner_turns_attended")],
    ["Completions", c("completions")],
    ["Capability changes", c("capability_changes")],
  ];
}
