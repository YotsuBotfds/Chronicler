import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { Apprenticeship } from "../Apprenticeship";
import { record } from "../../../lib/__tests__/apprenticeshipFixture";
afterEach(cleanup);

function props(apprenticeship: unknown, turn = 5) {
  const snapshot = { turn, livelihoods: { schema_version: 1, apprenticeship } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Bram Fen" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("names mentors and apprentices, attendance, costs, wear and unmet sites", () => {
  const p = props(record);
  render(<Apprenticeship {...p} />);
  expect(screen.getByRole("heading", { name: "Workshop apprenticeship · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/not occupation skill/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Apprenticeship funnel at snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Apprentices enrolled/ })).toHaveTextContent("4");
  expect(funnel.getByRole("row", { name: /Stipends paid/ })).toHaveTextContent("0.875");
  const continuity = screen.getByLabelText("Continuity");
  expect(continuity).toHaveTextContent("2 qualified alive anywhere");
  expect(continuity).toHaveTextContent("Unmet: Bram has no qualified person in the region.");
  const rows = within(screen.getByRole("table", { name: "Apprenticeship sites at snapshot 5" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("Ashford");
  expect(rows[1]).toHaveTextContent("0.02 − 0.01 = 0.01");
  expect(rows[1]).toHaveTextContent("21: taught by 7, income given up 0.2");
  expect(rows[1]).toHaveTextContent("22 (veteran) new: taught by 7");
  expect(rows[1]).toHaveTextContent("23: missed (away)");
  expect(rows[1]).toHaveTextContent("0.25 of 0.25 (paid)");
  expect(rows[2]).toHaveTextContent("none (0 seats, 6 eligible)");
  const open = within(screen.getByRole("table", { name: "Open apprenticeships at snapshot 5" })).getAllByRole("row");
  expect(open[1]).toHaveTextContent("3 of 10");
  expect(screen.getByText(/30 at Ashford \(turn 3, completed, qualified\)/)).toBeInTheDocument();
  expect(screen.getByText(/40 at Ashford \(turn 2, migrated\)/)).toBeInTheDocument();
  expect(screen.getByText(/turn 3 teaching lost at Bram \(2\)/)).toBeInTheDocument();
  fireEvent.click(within(rows[1]).getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("keeps a missing, malformed or unobserved record visible as such, re-dated to the snapshot", () => {
  render(<Apprenticeship {...props(undefined, 9)} />);
  expect(screen.getByText("Apprenticeship is not observed at snapshot 9.")).toBeInTheDocument();
  cleanup();
  render(<Apprenticeship {...props(record, 9)} />);
  expect(screen.getByText(/rejected as malformed: misdated observation/)).toBeInTheDocument();
  cleanup();
  render(<Apprenticeship {...props({ ...record, source_turn: 8, receipts: null, continuity: null, mode: "no_qualification" }, 9)} />);
  expect(screen.getByRole("heading", { name: "Workshop apprenticeship · snapshot 9" })).toBeInTheDocument();
  expect(screen.getByText(/continuity this turn is unknown, not zero/)).toBeInTheDocument();
  expect(screen.getByText(/No-qualification control/)).toBeInTheDocument();
});
