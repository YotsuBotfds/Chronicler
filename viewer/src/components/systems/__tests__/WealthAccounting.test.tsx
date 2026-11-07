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

it("shows a failed closure on an observed frame instead of rejecting it", () => {
  const typed = [frame.typed[0], frame.typed[1], { ...frame.typed[2], unlocated_in_milli: -115 }];
  const closures = [...frame.closures, { channel: "remittance", check: "located flows do not exceed the package's total",
    lhs: 1115, rhs: 1500, closes: false }];
  const broken = { ...frame, typed, closures, world: { ...frame.world, unlocated_in_milli: 385 } };
  render(<WealthAccounting {...props({ wealth_accounting: record({ frame: broken }) })} />);
  expect(screen.queryByText(/rejected as malformed/)).not.toBeInTheDocument();
  expect(screen.getByText(/Closures that did not hold: Remittances \(RS4\): located flows do not exceed the package's total \(1115 against 1500\)/)).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Agent wealth at snapshot 10" })).toBeInTheDocument();
});

it("shows native modeled effects and transfer receipt differences as distinct observations", () => {
  const native = { source_turn: 9, rows: [{ region: 0, component: "income_applied", amount: 5 },
    { region: 0, component: "decay", amount: -3.5 }, { region: 1, component: "transfer_actual", amount: 2 }],
    totals: { income_applied: 5, decay: -3.5, transfer_actual: 2 }, modeled_net: 1.5, transfer_actual: 2,
    balance_closure: 0, typed_receipt_difference: 0, typed_rounding_or_unobserved: 0, observed_complete: true,
    coverage: "native stages and exact transfer deltas observed; receipt rounding reported separately" };
  render(<WealthAccounting {...props({ wealth_accounting: record({ frame: { ...frame, native } }) })} />);
  expect(screen.getByRole("table", { name: "Native wealth stages at snapshot 10" })).toHaveTextContent("decay-3.5");
  expect(screen.getByText(/Modeled stage net: 1.5.*Actual transfer delta: 2.*Balance closure discrepancy: 0/)).toBeInTheDocument();
  expect(screen.queryByText("Native model residual")).toBeNull();
});
