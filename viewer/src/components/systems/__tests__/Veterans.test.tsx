import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Veterans } from "../Veterans";
afterEach(cleanup);

/** Constructed observations to test rendering; not a simulation run. */
const placed = {
  record_id: 0, agent_id: 10, civ: 0, army_id: "army-3", war_key: "Avalon:Brook", war_start: 2, cause: "demobilised",
  released_turn: 4, released_region: 1, region: 1, age: 30, status: "placed", reason: null,
  closed_turn: null, closed_reason: null, placements: 1, placed_turns: 2,
  spells: [{ kind: "placed:crew", site: 0, region: 1, start_turn: 5, last_turn: 6, turns: 2, prioritised: true }],
  outcomes: [{ turn: 4, kind: "waiting", detail: { region: 1 } },
    { turn: 5, kind: "placed:crew", detail: { site: 0, region: 1, prioritised: true } }],
  outcomes_dropped: 0,
};
const lost = { ...placed, record_id: 2, agent_id: 12, cause: "desertion", status: "ineligible", reason: "control_lost",
  region: 0, placements: 0, placed_turns: 0, spells: [],
  outcomes: [{ turn: 4, kind: "waiting", detail: { region: 1 } }, { turn: 6, kind: "migrated", detail: { from: 1, to: 0 } },
    { turn: 6, kind: "control_lost", detail: { region: 0, controller: 1 } }] };
const expired = { ...lost, record_id: 3, agent_id: 13, status: "closed", reason: null, region: 1, closed_turn: 6,
  closed_reason: "expired", war_key: null, war_start: null,
  outcomes: [{ turn: 4, kind: "waiting", detail: { region: 1 } }, { turn: 6, kind: "expired", detail: { placed_turns: 0 } }] };
const frame = {
  turn: 6, priority_applied: true,
  captured: [{ agent_id: 20, civ: 0, army_id: "army-5", war_key: "Avalon:Brook", war_start: 2, cause: "scattered", region: 0 }],
  captured_total: 1, captured_by_cause: { scattered: 1 }, offered: [[1, [10, 13]]],
  placed: [{ agent_id: 10, kind: "placed:crew", region: 1, site: 0, prioritised: true, new_spell: false }],
  waiting: [{ agent_id: 13, region: 1, reason: "crew_full" }, { agent_id: 14, region: 0, reason: "no_site" },
    { agent_id: 15, region: 0, reason: "site_idle" }],
  outcomes: [], counts: { open: 2 }, rows_dropped: 0,
};
const record = {
  schema_version: 1, stage: "RS3", enabled: true, mode: "priority", source_turn: 6, frame,
  veterans: [placed, lost], veterans_omitted: 3, closed: [expired],
  counters: { captured: 9, offered: 12, placements: 2, placement_turns: 5, people_placed: 2, closed_expired: 4,
    closed_remobilised: 1, waiting_turns: 30, control_lost: 2 },
  parameters: { eligible_turns: 20 },
};

function props(veteran_reintegration: unknown, turn = 7) {
  const snapshot = { turn, livelihoods: { schema_version: 1, veteran_reintegration } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }],
    civilizations: [{ name: "Avalon" }, { name: "Brook" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("names veterans with their war, cause, release, residence, status and dated outcomes", () => {
  const p = props(record);
  render(<Veterans {...p} />);
  expect(screen.getByRole("heading", { name: "Veterans · snapshot 7" })).toBeInTheDocument();
  expect(screen.getByText(/Nothing is guaranteed/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Veteran funnel at snapshot 7" }));
  expect(funnel.getByRole("row", { name: /Released alive/ })).toHaveTextContent("9");
  expect(funnel.getByRole("row", { name: /People placed/ })).toHaveTextContent("2");
  const outcomes = within(screen.getByRole("table", { name: "Veteran outcomes at snapshot 7" }));
  expect(outcomes.getByRole("row", { name: /Expired/ })).toHaveTextContent("4");
  expect(outcomes.getByRole("row", { name: /Remobilised/ })).toHaveTextContent("1");
  const turn = within(screen.getByRole("table", { name: "Veterans this turn at snapshot 7" }));
  expect(turn.getByRole("row", { name: /Released alive/ })).toHaveTextContent("1 (1 scattered)");
  expect(turn.getByRole("row", { name: /Put first for crews/ })).toHaveTextContent("Ashford Vale: 10, 13");
  expect(turn.getByRole("row", { name: /no opening/ })).toHaveTextContent("2 (1 no site, 1 site idle)");
  expect(turn.getByRole("row", { name: /an opening existed/ })).toHaveTextContent("1 crew full");
  const rows = within(screen.getByRole("table", { name: "Open veteran records at snapshot 7" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("Avalon · army-3");
  expect(rows[1]).toHaveTextContent("Avalon – Brook (from turn 2)");
  expect(rows[1]).toHaveTextContent("Placed this turn");
  expect(rows[1]).toHaveTextContent("turn 5: placed as crew (site 0), put first");
  expect(rows[2]).toHaveTextContent("Not eligible (control lost)");
  expect(rows[2]).toHaveTextContent("turn 6: moved from Ashford Vale to Oldmere");
  expect(screen.getByText(/3 more open records/)).toBeInTheDocument();
  const closed = within(screen.getByRole("table", { name: "Veteran records closed at snapshot 7" })).getAllByRole("row");
  expect(closed[1]).toHaveTextContent("No war record");
  expect(closed[1]).toHaveTextContent("Closed: expired");
  fireEvent.click(within(rows[2]).getByRole("button", { name: "Oldmere" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Oldmere");
});

it("says so when the record is missing and keeps an unobserved turn unknown", () => {
  render(<Veterans {...props(record, 9)} />);
  expect(screen.getByText(/not observed or is unavailable at snapshot 9/)).toBeInTheDocument();
  cleanup();
  render(<Veterans {...props({ ...record, frame: null })} />);
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
  cleanup();
  const control = { ...record, mode: "record_only", veterans: [lost],
    frame: { ...frame, priority_applied: false, offered: null, placed: [], waiting: [] } };
  render(<Veterans {...props(control)} />);
  expect(screen.getByText(/Record-only control/)).toBeInTheDocument();
  const turn = within(screen.getByRole("table", { name: "Veterans this turn at snapshot 7" }));
  expect(turn.getByRole("row", { name: /Would have been put first/ })).toHaveTextContent("Unknown");
  expect(turn.getByRole("row", { name: /no opening/ })).toHaveTextContent("Unknown");
});
