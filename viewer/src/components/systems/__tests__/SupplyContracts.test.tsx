import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { TimberOrders } from "../TimberOrders";
import { WarRequisition } from "../WarRequisition";
import { timber, requisition, supplySnapshot } from "../../../lib/__tests__/supplyContractsFixture";
import type { SystemPanelProps } from "../../../lib/systems";
afterEach(cleanup);
const props = (key: string, record: unknown) => ({ bundle: { world_state: { regions: [{ name: "A" },{ name: "B" }], civilizations: [{},{}] } }, snapshot: supplySnapshot(key, record), currentTurn: 3, onSelectRegion: vi.fn(), onSeek: vi.fn() }) as unknown as SystemPanelProps;
it("shows actual timber delivery and escrow as different quantities", () => {
  render(<TimberOrders {...props("timber_orders", timber)}/>);
  expect(screen.getByRole("table", { name: "Timber cargo and escrow" })).toHaveTextContent("Timber order #1");
  expect(screen.getByText(/treasury promise or dispatch is not a delivery/)).toBeInTheDocument();
});
it("shows original due, actually paid and remaining without making claims cash", () => {
  render(<WarRequisition {...props("war_requisition", requisition)}/>);
  expect(screen.getByRole("table", { name: "Restitution liabilities" })).toHaveTextContent("0.8 / 0.3 / 0.5");
  expect(screen.getByText(/liabilities, not spendable household money/)).toBeInTheDocument();
});
it("rejects broken books without displaying their numbers", () => {
  render(<TimberOrders {...props("timber_orders", { ...timber, source_turn: 99 })}/>);
  expect(screen.getByText(/Rejected timber order record/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
