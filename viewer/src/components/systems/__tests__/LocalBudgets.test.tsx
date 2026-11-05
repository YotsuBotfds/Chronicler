import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { localBudgetsRecord } from "../../../lib/__tests__/localBudgetsFixture";
import { LocalBudgets } from "../LocalBudgets";
afterEach(cleanup);

function props(budgets: unknown = localBudgetsRecord(), turn = 31) {
  const snapshot = { turn, livelihoods: { schema_version: 1, local_budgets: budgets } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Verdant Plains" }, { name: "Thornwood" }],
    civilizations: [{ name: "Kethani Empire" }, { name: "Thornwall Confederacy" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows the dated decision, the deferral with its reason and the city's response", () => {
  const p = props(); render(<LocalBudgets {...p} />);
  expect(screen.getByRole("heading", { name: "Local budgets · snapshot 31" })).toBeInTheDocument();
  expect(screen.getByText(/Phase 10 of simulation turn 30/)).toBeInTheDocument();
  const decisions = within(screen.getByRole("table", { name: "Budget decisions at snapshot 31" }));
  const row = decisions.getByRole("row", { name: /Thornwall Confederacy/ });
  expect(row).toHaveTextContent("Unknown");                 // the commons' burden was not observed
  expect(row).toHaveTextContent("workshop 3");
  expect(row).toHaveTextContent("Uncontested");
  const settled = within(screen.getByRole("table", { name: "Settled envelopes at snapshot 31" }));
  expect(settled.getByRole("row", { name: /granary maintain/ })).toHaveTextContent("Deferred (treasury shortfall)");
  expect(settled.getByRole("row", { name: /granary maintain/ })).toHaveTextContent("+0.1");
  expect(screen.getByText(/city 12 0.2 → 0.3/)).toBeInTheDocument();
  fireEvent.click(settled.getByRole("button", { name: "Verdant Plains" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Verdant Plains");
  const funnel = within(screen.getByRole("table", { name: "Budget funnel at snapshot 31" }));
  expect(funnel.getByRole("row", { name: /Coins committed/ })).toHaveTextContent("11");
});

it("labels the fixed-shares control and keeps unobserved turns unknown", () => {
  render(<LocalBudgets {...props({ ...localBudgetsRecord(), mode: "fixed_shares", decisions: null, settled: null, responses: null })} />);
  expect(screen.getByText(/Fixed shares \(control\)/)).toBeInTheDocument();
  expect(screen.getByText(/allocations are unknown, not zero/)).toBeInTheDocument();
  expect(screen.getByText(/deliveries are unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<LocalBudgets {...props(localBudgetsRecord(), 32)} />);
  expect(screen.getByText(/not observed or are unavailable at snapshot 32/)).toBeInTheDocument();
});
