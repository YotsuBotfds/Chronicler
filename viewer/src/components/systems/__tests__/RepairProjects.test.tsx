import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { RepairProjects } from "../RepairProjects";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const project = { pid: 2, kind: "workshop", asset: 0, region: 1, settlement_id: 5, cause: "war", war_key: "A:B",
  war_start_turn: 3, damages: [4], opened_turn: 6, opened_condition: 0.4, controller: 0, scope: 4.8,
  delivered: 0.4, credited: 0.4, status: "open", closed_turn: null, closed_reason: null, work_turns: 1,
  stalled_turns: 1, stalls: { no_timber: 1 }, timber_used: 0.4, wages_milli: 400, coin_cost_milli: 0,
  last_crew: [100, 101], history: [] };
const granary = { ...project, pid: 1, kind: "granary", asset: 0, region: 0, settlement_id: null, cause: "wear",
  war_key: null, war_start_turn: null, damages: [], scope: 20, delivered: 0, credited: 0, last_crew: [],
  stalls: { no_timber: 3 }, wages_milli: 0, timber_used: 0 };
const crew = { turn: 7, pid: 2, kind: "workshop", asset: 0, region: 1, payer: 0, status: "progress",
  reasons: ["unqualified"], requested: 0.2, delivered: 0.2, credited: 0.2, rate: 0.5, crew: [100, 101],
  share: 0.2, qualified: [], veterans: [101], timber_held: 0.2, timber_used: 0.2, timber_returned: 0,
  wages_due_milli: 200, wages_milli: 200, wage_residual_milli: 0, coin_cost_milli: 0, envelope: null,
  condition_before: 0.4, condition_after: 0.425, remaining_after: 4.6, income_replaced: 0.8 };
const stalled = { ...crew, pid: 1, kind: "granary", asset: 0, region: 0, status: "stalled", reasons: ["no_timber"],
  requested: 0, delivered: 0, credited: 0, rate: null, crew: [], share: null, veterans: [], timber_held: 0,
  timber_used: 0, wages_due_milli: 0, wages_milli: 0, condition_before: 0.5, condition_after: 0.49,
  remaining_after: 20, income_replaced: null };
const record = { schema_version: 1, stage: "RS2", mode: "repair", source_turn: 7, units: {},
  projects: [granary, project], closed: [{ ...granary, pid: 0, status: "abandoned", closed_turn: 4,
    closed_reason: "no_controller", stalls: {} }],
  damages: [{ did: 4, turn: 5, kind: "workshop", asset: 0, region: 1, event: "sack", war_key: "A:B",
    war_start_turn: 3, amount: 0.25, condition_before: 0.65, condition_after: 0.4, project: 2 }],
  receipts: [stalled, crew], ledger: [{ turn: 7, civ: 0, projects: 2, work_delivered: 0.2, timber_used: 0.2,
    coin_cost_milli: 0, wages_due_milli: 200, wages_applied_milli: 200, wage_residual_milli: 0, charged: 1,
    prepaid_before_milli: 0, prepaid_after_milli: 800, envelope: null }],
  unmet: [{ kind: "granary", asset: 2, region: 2, condition: 0.1, reason: "zero_capacity" }], suspended: [0],
  prepaid: { "0": 800 }, counters: { opened_wear: 2, opened_war: 1, progress_turns: 3, stalled_turns: 4, work_delivered: 1.2, charged: 3 },
  parameters: { open_below: 0.75 } };

function props(repair_projects: unknown, turn = 8) {
  const snapshot = { turn, livelihoods: { schema_version: 1, repair_projects } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Fen" }],
    civilizations: [{ name: "Dorrath" }, { name: "Vrash" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows projects with cause, crew, funding, stalls and dated outcomes", () => {
  const p = props(record);
  render(<RepairProjects {...p} />);
  expect(screen.getByRole("heading", { name: "Repair projects · snapshot 8" })).toBeInTheDocument();
  expect(screen.getByText(/does not by itself repair anything/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Repair funnel at snapshot 8" }));
  expect(funnel.getByRole("row", { name: /opened after war damage/ })).toHaveTextContent("1");
  const rows = within(screen.getByRole("table", { name: "Open repair projects at snapshot 8" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("Granary in Oldmere");
  expect(rows[1]).toHaveTextContent("Stalled: no free timber");
  expect(rows[1]).toHaveTextContent("Farm labour (anonymous)");
  expect(rows[2]).toHaveTextContent("War (A:B, began turn 3)");
  expect(rows[2]).toHaveTextContent("100, 101 (veteran)");
  expect(rows[2]).toHaveTextContent("no qualified repairer");
  expect(rows[2]).toHaveTextContent("Dorrath: wages 0.2");
  const accounts = within(screen.getByRole("table", { name: "Repair accounts at snapshot 8" }));
  expect(accounts.getAllByRole("row")[1]).toHaveTextContent("1 (prepaid 0 → 0.8)");
  expect(screen.getByText(/granary in Fen at 0.1 \(zero capacity\)/)).toBeInTheDocument();
  expect(screen.getByText(/abandoned, no controller turn 4/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Recent war damage at snapshot 8" })).getAllByRole("row")[1])
    .toHaveTextContent("0.65 → 0.4");
  fireEvent.click(screen.getAllByRole("button", { name: "Ashford Vale" })[0]);
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("says so when the record is missing and keeps an unobserved turn unknown", () => {
  render(<RepairProjects {...props(record, 9)} />);
  expect(screen.getByText(/Repair projects: the record at snapshot 9 was rejected as malformed/)).toBeInTheDocument();
  cleanup();
  render(<RepairProjects {...props({ ...record, receipts: null, ledger: null, unmet: null, suspended: null })} />);
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Open repair projects at snapshot 8" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Unknown");
});
