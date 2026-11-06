import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { WorkshopEconomics } from "../WorkshopEconomics";
import { economics, receipt, terms } from "../../../lib/__tests__/workshopEconomicsFixture";
import { payroll } from "../../../lib/__tests__/workshopFinanceFixture";
afterEach(cleanup);

function props(livelihoods: unknown, turn = 5) {
  const snapshot = { turn, livelihoods } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }, { name: "Third" }],
    civilizations: [{ name: "Selurian" }] } } as unknown as Bundle,
  snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const a3 = (workshop_economics: unknown) => ({ schema_version: 1, workshop_payroll: payroll, workshop_economics });

it("shows each firm's cash, inputs, customers, payroll, arrears, unsold wares and subsidy", () => {
  const p = props(a3(economics));
  render(<WorkshopEconomics {...p} />);
  expect(screen.getByRole("heading", { name: "Workshop economics · snapshot 5" })).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Workshop firms' economics at snapshot 5" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("Selurian");
  expect(row).toHaveTextContent("operating");
  expect(row).toHaveTextContent("0.6 · 0.48");          // inputs used · paid
  expect(row).toHaveTextContent("0.14 (0.07 · 1)");     // household sales (bought · priced out)
  expect(row).toHaveTextContent("0.615");               // unsold wares
  expect(row).toHaveTextContent("no academy customer");
  const funnel = within(screen.getByRole("table", { name: "Workshop economics funnel to snapshot 5" }));
  expect(funnel.getByRole("row", { name: /Firms opened/ })).toHaveTextContent("1 (11)");
  fireEvent.click(screen.getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("keeps disabled, unobserved, malformed, absent and a recorded zero distinct", () => {
  render(<WorkshopEconomics {...props({ schema_version: 1, workshop_payroll: payroll })} />);
  expect(screen.getByText(/Workshop economics is off at snapshot 5/)).toBeInTheDocument();
  cleanup();
  render(<WorkshopEconomics {...props(a3({ ...economics, receipts: null }))} />);
  expect(screen.getByText(/unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<WorkshopEconomics {...props(a3({ ...economics, receipts: [{ ...receipt, cash_close: 1 }] }))} />);
  expect(screen.getByText(/malformed or does not close/)).toBeInTheDocument();
  cleanup();
  render(<WorkshopEconomics {...props(null)} />);
  expect(screen.getByText(/No workshop economics record at snapshot 5/)).toBeInTheDocument();
  cleanup();
  render(<WorkshopEconomics {...props(a3({ ...economics, firms: [], receipts: [] }))} />);
  expect(screen.getByText(/No firm was open in simulation turn 4 \(a recorded zero\)/)).toBeInTheDocument();
});

it("names closed firms and their reason", () => {
  const closed = { ...terms, status: "closed", closed_turn: 4, closed_reason: "idle" };
  const closedReceipt = { ...receipt, status: "closed", event: "closed_idle" };
  render(<WorkshopEconomics {...props(a3({ ...economics, firms: [], closed: [closed], receipts: [closedReceipt] }))} />);
  expect(screen.getByText(/Ashford Vale \(turn 4, idle, capital 11\)/)).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Workshop firms' economics at snapshot 5" })).getAllByRole("row")[1];
  expect(row).toHaveTextContent("closed (idle)");
});
