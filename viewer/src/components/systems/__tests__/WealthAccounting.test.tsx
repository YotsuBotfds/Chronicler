import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { WealthAccounting } from "../WealthAccounting";
import { frame, record } from "../../../lib/__tests__/wealthAccountingFixture";
afterEach(cleanup);

function props(livelihoods: Record<string, unknown> | null, turn = 10) {
  const snapshot = { turn, livelihoods: livelihoods === null ? null : { schema_version: 1, ...livelihoods } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" }],
    civilizations: [{ name: "Selurian" }] } } as unknown as Bundle, snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const row = (table: string, label: RegExp) => within(screen.getByRole("table", { name: table })).getByRole("row", { name: label });

it("shows the balance identity, typed flows, withheld income and the treasury side", () => {
  const p = props({ wealth_accounting: record() });
  render(<WealthAccounting {...p} />);
  expect(screen.getByRole("heading", { name: "Wealth accounting · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/nothing wrote agent wealth between turns/)).toBeInTheDocument();
  const world = "Agent wealth at snapshot 10";
  expect(row(world, /Opening balance/)).toHaveTextContent("100 (40)");
  expect(row(world, /Typed flows in/)).toHaveTextContent("3 · 1");
  expect(row(world, /Native model residual/)).toHaveTextContent("1.5");
  expect(row("Typed flows at snapshot 10", /Granary crew wages/)).toHaveTextContent("2");
  expect(row("Typed flows at snapshot 10", /Granary procurement/)).toHaveTextContent("0.5");
  expect(screen.getByText(/All 2 package closures held/)).toBeInTheDocument();
  expect(screen.getByText(/name no region; region residuals below include them/)).toBeInTheDocument();
  expect(row("Paid-work income withheld at snapshot 10", /Granary crews \(PL3\)/)).toHaveTextContent("0.5");
  expect(screen.getByText(/PL3 granary crews 0.5 and workshop crews 0.25 of PL3's own 0.75/)).toBeInTheDocument();
  expect(screen.getByText(/retail replaced by sales this turn: 1.25/)).toBeInTheDocument();
  expect(row("Treasury side at snapshot 10", /tithe: potential \(an upper bound, not created money\)/)).toHaveTextContent("9 · 3");
  expect(row("Treasury side at snapshot 10", /Treasury tax created/)).toHaveTextContent("4");
  fireEvent.click(screen.getByRole("button", { name: "Ashford Vale" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Ashford Vale");
});

it("keeps unobserved, malformed and broken readings distinct from recorded zeros", () => {
  render(<WealthAccounting {...props({ wealth_accounting: record({ frame: null }) })} />);
  expect(screen.getByText(/Simulation turn 9 was not observed.*unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<WealthAccounting {...props({ wealth_accounting: record({ stage: "X" }) })} />);
  expect(screen.getByText(/rejected as malformed: unknown wealth-accounting schema/)).toBeInTheDocument();
  cleanup();
  const broken = { ...frame, continuity: { status: "broken", reason: null, previous_close_turn: 8, difference: 5,
    agents_difference: 0, regions: [[1, 5, 0]], regions_dropped: 0 } };
  render(<WealthAccounting {...props({ wealth_accounting: record({ frame: broken }) })} />);
  expect(screen.getByText(/Something wrote agent wealth between the previous closing and this opening: 5 in all/)).toBeInTheDocument();
  cleanup();
  const solo = { ...frame, withheld: { paid_work_active: false, rows: null, deducted: null, packages: null,
    unattributed_rows: null, unattributed_pl3_dropped_rows: null, unattributed_deducted: null, conflicts: null,
    recovery_crews: null, retail_active: true, retail_income_replaced: null } };
  render(<WealthAccounting {...props({ wealth_accounting: record({ frame: solo }) })} />);
  expect(screen.getByText(/paid-work withholding is not recorded \(unknown, not zero\)/)).toBeInTheDocument();
  expect(screen.getByText(/replaced by sales this turn: Unknown/)).toBeInTheDocument();
});

it("the livelihoods tab reads a ledger-only record instead of naming no package", () => {
  const p = { ...props({ wealth_accounting: record() }), onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...p} />);
  expect(screen.queryByText(/names no package this viewer reads/)).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Wealth accounting · snapshot 10" })).toBeInTheDocument();
});
