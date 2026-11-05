import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { learningCohortsAt, learningFunnel } from "../learningCohorts";

/** Constructed observations to test the reader; not a simulation run. */
const member = { agent_id: 11, joined_turn: 1, occupation: 0, skill_at_join: 0.05, attended: 2,
  last_attended_turn: 3, absent_streak: 0, status: "active", completed_turn: null, exit_turn: null,
  exit_reason: null, skill_before: null, skill_after: null };
const cohort = { cohort_id: 0, seat_id: 0, region: 1, founder: 0, founded_turn: 0, seat_name: "Declared Academy",
  formed_turn: 1, status: "open", closed_turn: null, closed_reason: null, members: [member, { ...member, agent_id: 15 }],
  sessions: 2, idle_streak: 0, last_session_turn: 3 };
const receipt = { turn: 3, cohort_id: 0, seat_id: 0, region: 1, members_active: 2, available: [11, 15],
  unavailable: {}, reserved: [11, 15], attended: [11], no_seat: [15], absent: [], session: true,
  no_session_reason: null, teaching_work_delivered: 0.125, teaching_learners_delivered: 1,
  income_charged: 0.05, supplies_used: 1, completed: [], exited: {} };
const graduate = { agent_id: 4, cohort_id: 0, region: 1, occupation: 1, completed_turn: 2, skill_before: 0.25,
  skill_after: 0.5, granted: true };
const record = { schema_version: 1, stage: "L5", mode: "learn", source_turn: 3, cohorts: [cohort],
  archive: [{ cohort_id: 7, seat_id: 0, region: 1, seat_name: "Old", formed_turn: 0, closed_turn: 2,
    closed_reason: "academy_lost", sessions: 1, members: 3, completed: 0, exited: 3 }],
  graduates: [graduate], receipts: [receipt],
  counters: { academy_turns: 4, cohorts_formed: 1, sessions: 2, completions: 1, capability_changes: 1 },
  parameters: { sessions_to_complete: 4 } };
const snap = (learning_cohorts: unknown, turn = 4) =>
  ({ turn, livelihoods: { schema_version: 1, learning_cohorts } } as unknown as TurnSnapshot);

describe("learning cohorts reader", () => {
  it("reads dated, well-formed records only", () => {
    expect(learningCohortsAt(snap(record), 3)?.cohorts[0].seat_name).toBe("Declared Academy");
    expect(learningCohortsAt(snap(record, 5), 3)).toBeNull();               // misdated
    expect(learningCohortsAt(snap(record), 1)).toBeNull();                  // region out of range
    expect(learningCohortsAt(snap({ ...record, stage: "L4" }), 3)).toBeNull();
    expect(learningCohortsAt(null, 3)).toBeNull();
  });

  it("refuses attendance beyond delivered teaching and unaccounted reservations", () => {
    const crowded = { ...receipt, attended: [11, 15], no_seat: [] };
    expect(learningCohortsAt(snap({ ...record, receipts: [crowded] }), 3)).toBeNull();
    const unknownTeacher = { ...receipt, teaching_learners_delivered: null };
    expect(learningCohortsAt(snap({ ...record, receipts: [unknownTeacher] }), 3)).toBeNull();
    const lost = { ...receipt, no_seat: [] };
    expect(learningCohortsAt(snap({ ...record, receipts: [lost] }), 3)).toBeNull();
    const freeTime = { ...receipt, attended: [], no_seat: [11, 15], session: false, income_charged: 0.1 };
    expect(learningCohortsAt(snap({ ...record, receipts: [freeTime] }), 3)).toBeNull();
    const nine = { ...cohort, members: Array.from({ length: 9 }, (_, i) => ({ ...member, agent_id: i })) };
    expect(learningCohortsAt(snap({ ...record, cohorts: [nine] }), 3)).toBeNull();
  });

  it("refuses a granted skill in the no-learning control or a skill that falls", () => {
    expect(learningCohortsAt(snap({ ...record, mode: "no_learning" }), 3)).toBeNull();
    const control = { ...graduate, skill_after: 0.25, granted: false };
    expect(learningCohortsAt(snap({ ...record, mode: "no_learning", graduates: [control] }), 3)?.mode).toBe("no_learning");
    expect(learningCohortsAt(snap({ ...record, graduates: [{ ...graduate, skill_after: 0.2 }] }), 3)).toBeNull();
  });

  it("keeps an unobserved turn unknown, not zero, and orders the funnel", () => {
    expect(learningCohortsAt(snap({ ...record, receipts: null }), 3)?.receipts).toBeNull();
    const parsed = learningCohortsAt(snap(record), 3)!;
    const funnel = learningFunnel(parsed);
    expect(funnel[0]).toEqual(["Academy-turns observed", 4]);
    expect(funnel.find(([k]) => k === "Learners enrolled")?.[1]).toBe(0);
    expect(funnel.at(-1)).toEqual(["Capability changes", 1]);
  });
});
