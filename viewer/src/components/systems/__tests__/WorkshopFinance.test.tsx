import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { WorkshopFinance } from "../WorkshopFinance";
import { firm, payroll, receipt } from "../../../lib/__tests__/workshopFinanceFixture";
afterEach(cleanup);

function props(workshop_payroll: unknown, turn = 5) {
  const snapshot = { turn, livelihoods: { schema_version: 1, workshop_payroll } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Third" }],
    civilizations: [{ name: "Selurian" }] } } as unknown as Bundle,
  snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows who bought, what the crew were paid and what they gave up", () => {
  const p = props(payroll);
  render(<WorkshopFinance {...p} />);
  expect(screen.getByRole("heading", { name: "Workshop payroll · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/sales fund wages that replace the crew's ordinary income share/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Workshop firms at snapshot 5" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Ashford");
  expect(row).toHaveTextContent("Selurian");
  expect(row).toHaveTextContent("1.3 / 0.3");
  expect(row).toHaveTextContent("(insolvent 1 turns)");
  const funnel = within(screen.getByRole("table", { name: "Payroll funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /paying customer/ })).toHaveTextContent("2");
  expect(funnel.getByRole("row", { name: /Crew net/ })).toHaveTextContent("0.8");
  fireEvent.click(screen.getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("keeps an unobserved turn unknown and names closed firms", () => {
  const closed = { ...firm, site: 1, status: "closed", closed_turn: 4, closed_reason: "insolvent" };
  render(<WorkshopFinance {...props({ ...payroll, receipts: null, transfers: null, closed: [closed] })} />);
  expect(screen.getByText(/sales and wages are unknown, not zero/)).toBeInTheDocument();
  expect(screen.getByText(/Ashford \(turn 4, insolvent\)/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Workshop firms at snapshot 5" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Unknown");
});

it("says when the record is absent or does not close", () => {
  render(<WorkshopFinance {...props({ ...payroll, receipts: [{ ...receipt, cash_close: 1 }] })} />);
  expect(screen.getByText(/not observed or is unavailable at snapshot 5/)).toBeInTheDocument();
});
