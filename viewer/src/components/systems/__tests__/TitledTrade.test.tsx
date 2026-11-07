import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { TitledTrade } from "../TitledTrade";
import { frame, trade } from "../../../lib/__tests__/titledTradeFixture";
afterEach(cleanup);

function props(livelihoods: unknown, turn = 5) {
  const snapshot = { turn, livelihoods } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Third" }],
    civilizations: [{ name: "Selurian" }] } } as unknown as Bundle,
  snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const a4 = (titled_trade: unknown) => ({ schema_version: 1, household_retail: { stage: "L6b" }, titled_trade });

it("shows shipments in transit, purchases from owners, outcomes and the funnel", () => {
  const p = props(a4(trade));
  render(<TitledTrade {...p} />);
  expect(screen.getByRole("heading", { name: "Titled trade · snapshot 5" })).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Shipments in transit at snapshot 5" })).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("#3 (bought turn 3)");
  expect(rows[1]).toHaveTextContent("90 (reserved)");
  expect(rows[1]).toHaveTextContent("at Ashford Vale, 1 hop(s) to go");
  expect(rows[1]).toHaveTextContent("1.5 grain, 0.2 fish");
  const purchases = within(screen.getByRole("table", { name: "Purchases from owners in simulation turn 4" }));
  expect(purchases.getAllByRole("row")[1]).toHaveTextContent("11: 0.4; 12: 0.2 → 93");
  expect(screen.getByText(/returned to the origin at full value, because the destination conquered/)).toBeInTheDocument();
  expect(screen.getByText(/91 sold 0.5 at Third for 0.6/)).toBeInTheDocument();
  const funnel = within(screen.getByRole("table", { name: "Titled trade funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Shipments bought/ })).toHaveTextContent("4 · 1 · 1 · 0 · 0");
  expect(funnel.getByRole("row", { name: /net money/ })).toHaveTextContent("-1.96");
  fireEvent.click(screen.getAllByRole("button", { name: "Oldmere" })[0]);
  expect(p.onSelectRegion).toHaveBeenCalledWith("Oldmere");
});

it("keeps disabled, unobserved, malformed, absent and a recorded zero distinct", () => {
  render(<TitledTrade {...props({ schema_version: 1, household_retail: { stage: "L6b" } })} />);
  expect(screen.getByText(/Titled trade is off at snapshot 5/)).toBeInTheDocument();
  cleanup();
  render(<TitledTrade {...props(a4({ ...trade, frame: null }))} />);
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<TitledTrade {...props(a4({ ...trade, frame: { ...frame, turn: 1 } }))} />);
  expect(screen.getByText(/malformed or its books do not close/)).toBeInTheDocument();
  cleanup();
  render(<TitledTrade {...props(null)} />);
  expect(screen.getByText(/No titled trade record at snapshot 5/)).toBeInTheDocument();
  cleanup();
  render(<TitledTrade {...props(a4({ ...trade, shipments: [],
    frame: { ...frame, dispatched: [], events: [], withheld: [], withheld_total: 0, sales: [] } }))} />);
  expect(screen.getByText(/No shipment was in transit after simulation turn 4 \(a recorded zero\)/)).toBeInTheDocument();
  expect(screen.getByText(/No merchant bought owned food in simulation turn 4 \(a recorded zero\)/)).toBeInTheDocument();
});
