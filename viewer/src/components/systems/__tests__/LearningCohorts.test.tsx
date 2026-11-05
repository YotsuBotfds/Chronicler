import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LearningCohorts } from "../LearningCohorts";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const member = { agent_id: 11, joined_turn: 1, occupation: 2, skill_at_join: 0.05, attended: 2,
  last_attended_turn: 3, absent_streak: 0, status: "active", completed_turn: null, exit_turn: null,
  exit_reason: null, skill_before: null, skill_after: null };
const cohort = { cohort_id: 3, seat_id: 0, region: 1, founder: 0, founded_turn: 0, seat_name: "Declared Academy",
  formed_turn: 1, status: "open", closed_turn: null, closed_reason: null,
  members: [member, { ...member, agent_id: 15, status: "exited", exit_turn: 2, exit_reason: "migrated" }],
  sessions: 2, idle_streak: 1, last_session_turn: 2 };
const receipt = { turn: 3, cohort_id: 3, seat_id: 0, region: 1, members_active: 1, available: [11],
  unavailable: {}, reserved: [11], attended: [], no_seat: [11], absent: [], session: false,
  no_session_reason: "no_supplies", teaching_work_delivered: null, teaching_learners_delivered: null,
  income_charged: 0, supplies_used: 0, completed: [], exited: {} };
const record = { schema_version: 1, stage: "L5", mode: "learn", source_turn: 3, cohorts: [cohort],
  archive: [{ cohort_id: 2, seat_id: 0, region: 1, seat_name: "Declared Academy", formed_turn: 0, closed_turn: 1,
    closed_reason: "academy_lost", sessions: 1, members: 2, completed: 0, exited: 2 }],
  graduates: [{ agent_id: 4, cohort_id: 1, region: 1, occupation: 1, completed_turn: 2, skill_before: 0.25,
    skill_after: 0.5, granted: true }],
  receipts: [receipt], counters: { academy_turns: 4, cohorts_formed: 2, learners_enrolled: 4, sessions: 2,
    learner_turns_attended: 3, completions: 1, capability_changes: 1, attendance_income_charged: 0.12 },
  parameters: {} };

function props(learning_cohorts: unknown, turn = 4) {
  const snapshot = { turn, livelihoods: { schema_version: 1, learning_cohorts } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows the funnel, who attended and why a cohort did not meet", () => {
  const p = props(record);
  render(<LearningCohorts {...p} />);
  expect(screen.getByRole("heading", { name: "Academy learners · snapshot 4" })).toBeInTheDocument();
  expect(screen.getByText(/does not by itself mean anyone learned/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Learning funnel at snapshot 4" }));
  expect(funnel.getByRole("row", { name: /Cohorts formed/ })).toHaveTextContent("2");
  expect(funnel.getByRole("row", { name: /Capability changes/ })).toHaveTextContent("1");
  const row = within(screen.getByRole("table", { name: "Open cohorts at snapshot 4" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("1 active of 2");
  expect(row).toHaveTextContent("11 Merchant 2");
  expect(row).toHaveTextContent("0 attended, 1 without a seat");
  expect(row).toHaveTextContent("no supplies");
  const graduates = within(screen.getByRole("table", { name: "Recent graduates at snapshot 4" }));
  expect(graduates.getAllByRole("row")[1]).toHaveTextContent("Soldier");
  expect(graduates.getAllByRole("row")[1]).toHaveTextContent("0.25 → 0.5");
  expect(screen.getByText(/academy lost: 0 completed, 2 left/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("says so when the record is missing and keeps an unobserved turn unknown", () => {
  render(<LearningCohorts {...props(record, 9)} />);
  expect(screen.getByText(/not observed or are unavailable at snapshot 9/)).toBeInTheDocument();
  cleanup();
  render(<LearningCohorts {...props({ ...record, receipts: null, mode: "no_learning", graduates: [] })} />);
  expect(screen.getByText(/No-learning control/)).toBeInTheDocument();
  expect(screen.getByText(/attendance is unknown, not zero/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Open cohorts at snapshot 4" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Unknown");
});
