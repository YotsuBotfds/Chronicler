import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle, GrainStorageSnapshot } from "../../../types";
import { record, snapshot } from "../../../__fixtures__/granaryHistory";
import { granaryAmounts, granaryStorageAt } from "../../../lib/granaries";
import { Granaries } from "../Granaries";
afterEach(cleanup);

/** Constructed observation to test source dates and rendering; not a simulation run. */
function storage(): GrainStorageSnapshot {
  return { schema_version: 1, receipt_turn: 4,
    assets: [{ capacity: 30, condition: .5, repair_progress: 2, expansion_progress: 3, owner: 0 }, null],
    policies: [{ policy: "maintain", work_budget: 3 }, { policy: "neglect", work_budget: 0 }],
    receipts: [{ turn: 4, region: 0, owner: 0, policy: "maintain", requested: 3, delivered: 2,
      timber_reserved: 6, timber_used: 4, timber_returned: 2, treasury_paid: 4,
      condition_before: .4, condition_after: .5, capacity_before: 30, capacity_after: 30,
      repair_progress: 2, expansion_progress: 3, target_requested: 20, target_feasible: 15, capacity_returned: 7 }] };
}
function props() {
  const granary = record(); granary.storage = storage();
  granary.granaries.push({ ...granary.granaries[0], region: 1, region_name: "Market" });
  granary.flows.push({ ...granary.flows[0], kind: "storage_returned", amount: 7, cost: 99 });
  const history = [snapshot(2), snapshot(5, granary), snapshot(8, { ...record(), storage: { ...storage(), receipt_turn: 7 } })];
  return { bundle: { world_state: { regions: [{ name: "Valley" }, { name: "Market" }], civilizations: [{ name: "Old realm" }] }, history } as unknown as Bundle,
    snapshot: history[1], currentTurn: 5, onSeek: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn(), onSelectEvent: vi.fn() };
}
it("renders recorded storage work, capacity and conservative return using the existing selector", () => {
  const p = props(); render(<Granaries {...p} />);
  const assets = screen.getByRole("table", { name: "Storage assets at snapshot 5" });
  expect(within(assets).getByText("15")).toBeInTheDocument();
  expect(within(assets).getAllByText("Not observed").length).toBeGreaterThan(0);
  const work = screen.getByRole("table", { name: "Storage work at snapshot 5" });
  expect(within(work).getByText("3 / 2")).toBeInTheDocument();
  expect(within(work).getByText("6 / 4 / 2")).toBeInTheDocument();
  expect(within(work).getByText("20 / 15")).toBeInTheDocument();
  expect(within(work).getByText("Work receipt not observed.")).toBeInTheDocument();
  expect(screen.getByText("capacity return to market")).toBeInTheDocument();
  expect(granaryAmounts(p.snapshot.grain_reserves!)).toMatchObject({ bought: 5, spoiled: .25, paid: 9, storageReturned: 7 });
  fireEvent.change(screen.getByLabelText("Granary history"), { target: { value: "0" } });
  expect(within(screen.getByRole("table", { name: "Storage work at snapshot 5" })).queryByText("Market")).not.toBeInTheDocument();
});
it("leaves missing, stale and malformed storage unknown without hiding granaries", () => {
  const p = props(), frame = p.snapshot.grain_reserves!.storage!;
  const view = render(<Granaries {...p} />);
  for (const broken of [ { ...storage(), schema_version: 2 }, { ...storage(), receipt_turn: 5 },
    { ...storage(), receipt_turn: 3 }, { ...storage(), receipts: [frame.receipts[0], frame.receipts[0]] },
    { ...storage(), receipts: [{ ...frame.receipts[0], turn: 5 }] }, { ...storage(), assets: [] },
    { ...storage(), assets: [{ ...frame.assets[0], condition: NaN }, null] },
    { ...storage(), receipts: [{ ...frame.receipts[0], region: 2 }] } ]) {
    Object.assign(p.snapshot.grain_reserves!, { storage: broken });
    expect(granaryStorageAt(p.snapshot, 2, 1)).toBeNull();
  }
  view.rerender(<Granaries {...p} />);
  expect(screen.getByText(/Storage assets and work are not observed/)).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Granaries at snapshot 5" })).toBeInTheDocument();
  view.rerender(<Granaries {...p} snapshot={p.bundle.history[0]} currentTurn={2} />);
  expect(screen.queryByText("20 / 15")).not.toBeInTheDocument();
});
