import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle } from "../../../types";
import { Granaries } from "../Granaries";
import { record, snapshot } from "../../../__fixtures__/granaryHistory";

afterEach(cleanup);

function props(turn = 5) {
  const history = [snapshot(2), snapshot(5, record()), snapshot(8, record(1, 99))];
  return { bundle: { world_state: { regions: [{ name: "Valley" }, { name: "Market" }],
    grain_reserves: { granaries: [{ grain: 999 }] } }, history } as unknown as Bundle,
  snapshot: history.find((row) => row.turn === turn) ?? null, currentTurn: turn,
  onSeek: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn(), onSelectEvent: vi.fn() };
}

it("renders exact historical stocks, targets, flows and keeper with navigation", () => {
  const p = props();
  render(<Granaries {...p} />);
  const table = screen.getByRole("table", { name: "Granaries at snapshot 5" });
  expect(within(table).getByText("12")).toBeInTheDocument();
  expect(within(table).queryByText("99")).not.toBeInTheDocument();
  expect(within(table).queryByText("999")).not.toBeInTheDocument();
  fireEvent.click(within(table).getByRole("button", { name: "Old realm" }));
  expect(p.onSelectCivilization).toHaveBeenCalledWith("Old realm");
  fireEvent.click(within(table).getByRole("button", { name: "Valley" }));
  expect(p.onSelectRegion).toHaveBeenCalledWith("Valley");
  const flows = screen.getByRole("table", { name: "Granary movements in turn 4" });
  expect(within(flows).getByText("Market (Seller)")).toBeInTheDocument();
  expect(within(flows).getByText("0.5 → 0.8")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Granary ownership over time" })).not.toHaveTextContent("New realm");
});

it("does not infer old missing stock from the final world or next observation", () => {
  render(<Granaries {...props(2)} />);
  expect(screen.getByText(/No granary record at turn 2/)).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("handles older bundles without any granary snapshots", () => {
  const p = props();
  p.bundle.history = [snapshot(5)];
  p.snapshot = p.bundle.history[0];
  render(<Granaries {...p} />);
  expect(screen.getByText(/This bundle has no per-turn granary record/)).toBeInTheDocument();
});

it("keeps an unobserved stock target unknown in the summary as well as the table", () => {
  const p = props();
  p.snapshot!.grain_reserves!.granaries[0].observed = 0;
  render(<Granaries {...p} />);
  const targetTile = screen.getByText("Stock target").closest("div")!;
  expect(within(targetTile).getByText("Not observed")).toBeInTheDocument();
  const row = within(screen.getByRole("table", { name: "Granaries at snapshot 5" })).getAllByRole("row")[1];
  expect(within(row).getByText("Not observed")).toBeInTheDocument();
  expect(within(row).getByText("12")).toBeInTheDocument();
});

it("scrubs keeper changes without retaining future selection data", () => {
  const p = props(8);
  const { rerender } = render(<Granaries {...p} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Granary history" }), { target: { value: "0" } });
  expect(within(screen.getByRole("table", { name: "Granaries at snapshot 8" })).getByText("99")).toBeInTheDocument();
  rerender(<Granaries {...p} snapshot={p.bundle.history[1]} currentTurn={5} />);
  expect(within(screen.getByRole("table", { name: "Granaries at snapshot 5" })).getByText("12")).toBeInTheDocument();
});

function withShipments() {
  const p = props();
  const granaries = p.snapshot!.grain_reserves!;
  granaries.shipments = { schema_version: 1, accept_orders: true, source_turn: 4, pending_count: 1, pending_net: 7,
    transitions: [
      { id: "dispatch:4", operation: "dispatched", turn: 4, dispatch_turn: 4, due_turn: 5,
        source: 1, source_name: "Recorded market", dest: 0, dest_name: "Valley", buyer: 0, buyer_name: "Original payer",
        seller: 1, seller_name: "Recorded seller", keeper: 0, sent: 8, net: 7, loss: 1, paid: 9 },
      { id: "dispatch:3", operation: "arrived", turn: 4, dispatch_turn: 3, due_turn: 4,
        source: 1, source_name: "Recorded market", dest: 0, dest_name: "Valley", buyer: 0, buyer_name: "Original payer",
        seller: 1, seller_name: "Recorded seller", keeper: 0, sent: 6, net: 5, loss: 1, paid: 6 },
    ] };
  granaries.flows.push({ ...granaries.flows[0], kind: "dispatched", amount: 7, sent: 8, cost: 9 },
    { ...granaries.flows[0], kind: "arrived", amount: 5, sent: 0, cost: 0 });
  return p;
}

it("shows observed in-transit cargo, dispatch and arrival without adding cargo to stocks or charging arrival again", () => {
  render(<Granaries {...withShipments()} />);
  const tile = (label: string) => within(screen.getByText(label).closest("div")!);
  expect(tile("Grain stored").getByText("12")).toBeInTheDocument();
  expect(tile("Immediate purchases").getByText("5")).toBeInTheDocument();
  expect(tile("Paid cargo in transit").getByText("7")).toBeInTheDocument();
  expect(tile("Grain dispatched").getByText("7")).toBeInTheDocument();
  expect(tile("Grain arrived").getByText("5")).toBeInTheDocument();
  const table = within(screen.getByRole("table", { name: "Public grain shipments in turn 4" }));
  expect(table.getByText("Dispatched")).toBeInTheDocument();
  expect(table.getByText("Arrived")).toBeInTheDocument();
  expect(table.getAllByText("Recorded market")).toHaveLength(2);
  expect(table.getAllByText("Original payer")).toHaveLength(2);
  expect(table.getByRole("columnheader", { name: "Paid at dispatch" })).toBeInTheDocument();
  expect(table.getByText(/arrivals make no new payment/)).toBeInTheDocument();
  const movements = within(screen.getByRole("table", { name: "Granary movements in turn 4" }));
  const arrived = movements.getByText("arrived").closest("tr")!;
  expect(within(arrived).getAllByRole("cell")[5]).toHaveTextContent("—");
  expect(screen.getByText(/18 treasury paid this turn/)).toBeInTheDocument();
});

it("does not show shipment zeroes for older snapshots or leak future cargo when scrubbing back", () => {
  const p = withShipments();
  const { rerender } = render(<Granaries {...p} />);
  expect(screen.getByRole("region", { name: "Public grain shipments" })).toBeInTheDocument();
  const earlier = snapshot(3, record());
  rerender(<Granaries {...p} snapshot={earlier} currentTurn={3} />);
  expect(screen.queryByRole("region", { name: "Public grain shipments" })).not.toBeInTheDocument();
  expect(screen.queryByText("Paid cargo in transit")).not.toBeInTheDocument();
  expect(screen.getByText("Grain procured")).toBeInTheDocument();
});

it("labels an invalid or future shipment frame unknown instead of displaying its cargo", () => {
  const p = withShipments();
  p.snapshot!.grain_reserves!.shipments!.source_turn = 8;
  render(<Granaries {...p} />);
  expect(screen.getByText(/Shipment details are not observed/)).toBeInTheDocument();
  expect(screen.queryByText("Paid cargo in transit")).not.toBeInTheDocument();
  expect(screen.queryByText("Original payer")).not.toBeInTheDocument();
});
