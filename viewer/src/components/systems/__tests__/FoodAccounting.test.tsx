import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, FoodAccountingSnapshot, TurnSnapshot } from "../../../types";
import { FoodAccounting } from "../FoodAccounting";
import { foodAccountingAt } from "../../../lib/foodAccounting";
afterEach(cleanup);
const record = (): FoodAccountingSnapshot => ({ schema_version: 1, mode: "hybrid", source_turn: 4, completed_turn: 5,
  timing: "phase2", units: "model_food_goods", transport: "physical_delivery",
  regions: [{ region_id: 0, native_count: 2, model_population: 100, native: { opening: 2, produced: 3, transport_net: -1,
    craft_input: 0, clamp_correction: 0, pre_consumption: 4, consumed: 4, storage_loss: 0, cap_overflow: 0,
    closing: 0, demand: 10, sufficiency: 0.4, balance_residual: 0, balance_tolerance: 0.001 },
    sufficiency_after_relief: 0.6, public: { owner_id: -1, opening: 4, released: 2, spoiled: 1, abandoned: 0,
      captured: 4, after_open: 1, balance_residual: 0 } }],
  procurement: [{ civilization_id: 0, budget_initial: 0, budget_remaining: 0, spent: 0 }] });
function props() {
  const snapshot = { turn: 5, food_accounting: record() } as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Valley" }, { name: "Hill" }], civilizations: [{ name: "Realm" }] } } as Bundle,
    snapshot, currentTurn: 5, onSelectRegion: vi.fn() };
}
it("shows separate native, public and later budget evidence", () => {
  const p = props(); render(<FoodAccounting {...p} />);
  expect(screen.getByText(/physical imports and returns minus departures/)).toBeInTheDocument();
  expect(screen.getByText(/public release did not cover/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Public food accounting" })).getByText("Unowned")).toBeInTheDocument();
  expect(screen.getByText(/late Phase 10 budget receipts/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Valley" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Valley");
});
it("leaves old, future, malformed and duplicate data unknown", () => {
  const p = props(); const good = p.snapshot.food_accounting!;
  for (const bad of [undefined, { ...good, schema_version: 2 }, { ...good, source_turn: 5 },
    { ...good, regions: [good.regions[0], good.regions[0]] },
    { ...good, regions: [{ ...good.regions[0], region_id: 2 }] },
    { ...good, regions: [{ ...good.regions[0], native: { ...good.regions[0].native!, consumed: NaN } }] },
    { ...good, procurement: [good.procurement[0], good.procurement[0]] }]) {
    expect(foodAccountingAt({ ...p.snapshot, food_accounting: bad } as TurnSnapshot, 2, 1)).toBeNull();
  }
  render(<FoodAccounting {...p} snapshot={{ turn: 2 } as TurnSnapshot} />);
  expect(screen.getByText(/not observed or is unavailable at snapshot 2/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
it("preserves null observations and handles partial region lists", () => {
  const p = props();
  p.snapshot.food_accounting!.regions[0] = { ...record().regions[0], native: null, native_count: null, public: null, sufficiency_after_relief: null };
  p.snapshot.food_accounting!.procurement = [];
  render(<FoodAccounting {...p} />);
  expect(screen.getByText(/Native food accounting is not observed/)).toBeInTheDocument();
  expect(screen.getByText(/Public granary accounting is not observed/)).toBeInTheDocument();
  expect(screen.getByText(/No procurement budget receipts recorded/)).toBeInTheDocument();
  expect(screen.queryByText(/Aggregate mode has no native kernel/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Region accounting" }), { target: { value: "1" } });
  expect(screen.getByText(/Accounting for this region is not observed/)).toBeInTheDocument();
});
