import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import type { TimberStockRecord } from "../../../lib/timberStock";
import { TimberStock } from "../TimberStock";
afterEach(cleanup);

/** Constructed observation to test rendering; not a simulation run. */
function record(): TimberStockRecord {
  return { schema_version: 1, units: "timber_goods", source_turn: 4, completed_turn: 5, enforce_cap: true,
    parameters: { regrowth_rate: 0.03, seed_fraction: 0.05, reference_crews_at_msy: 1 }, observed: true,
    regions: [
      { region_id: 0, slot: 0, opening: 100, cleared: 10, extraction: 30, overdraft: 0, regrowth: 2.5, removed: 0,
        stock: 62.5, capacity: 90, cap: 90, capped: false, water_gate_open: true },
      { region_id: 1, slot: 1, opening: 0, cleared: 0, extraction: 0, overdraft: 0, regrowth: 0, removed: 0,
        stock: 0, capacity: 10, cap: 0, capped: null, water_gate_open: false },
    ],
    totals: { opening: 100, cleared: 10, extraction: 30, overdraft: 0, regrowth: 2.5, removed: 0, stock: 62.5,
      capacity: 100, slots: 2, capped_slots: 0 } };
}
function props(timber: unknown = record(), turn = 5) {
  const snapshot = { turn, livelihoods: { schema_version: 1, timber_stock: timber } } as unknown as TurnSnapshot;
  return { bundle: { world_state: { regions: [{ name: "Thornwood" }, { name: "Mistwood" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}

it("shows dated accounts, separate cover loss and unobservable binding", () => {
  const p = props(); render(<TimberStock {...p} />);
  expect(screen.getByRole("heading", { name: "Timber stock · snapshot 5" })).toBeInTheDocument();
  expect(screen.getByText(/Phase 2 of simulation turn 4/)).toBeInTheDocument();
  const totals = within(screen.getByRole("table", { name: "Timber totals at snapshot 5" }));
  expect(totals.getByRole("row", { name: /Cleared with cover/ })).toHaveTextContent("10");
  expect(totals.getByRole("row", { name: /Slots where the cap bound/ })).toHaveTextContent("0 of 2");
  expect(totals.queryByRole("row", { name: /Overdraft/ })).not.toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Timber accounts at snapshot 5" }));
  expect(rows.getByText("Not observable")).toBeInTheDocument();
  expect(rows.getByText("0 (dry)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mistwood" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Mistwood");
});

it("labels the ablation and shows overdraft instead of binding", () => {
  const ablation = record();
  ablation.enforce_cap = false;
  ablation.regions = [{ ...ablation.regions![0], cap: null, capped: null, extraction: 110, overdraft: 20, stock: 2.5 }];
  ablation.totals = { ...ablation.totals!, overdraft: 20, slots: 1 };
  render(<TimberStock {...props(ablation)} />);
  expect(screen.getByText(/Ablation: the stock is accounted but no harvest cap/)).toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Timber totals at snapshot 5" })).getByRole("row", { name: /Overdraft/ })).toHaveTextContent("20");
  expect(screen.getByRole("columnheader", { name: "Overdraft" })).toBeInTheDocument();
});

it("keeps unobserved and malformed records unknown", () => {
  render(<TimberStock {...props({ ...record(), observed: false, regions: null, totals: null })} />);
  expect(screen.getByText(/flows are unknown, not zero/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  cleanup();
  render(<TimberStock {...props({ ...record(), source_turn: 5 })} />);
  expect(screen.getByText(/the record at snapshot 5 was rejected as malformed/)).toBeInTheDocument();
  cleanup();
  render(<TimberStock {...props(record(), 6)} />);
  expect(screen.getByText(/the record at snapshot 6 was rejected as malformed/)).toBeInTheDocument();
});
