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

it("scrubs keeper changes without retaining future selection data", () => {
  const p = props(8);
  const { rerender } = render(<Granaries {...p} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Granary history" }), { target: { value: "0" } });
  expect(within(screen.getByRole("table", { name: "Granaries at snapshot 8" })).getByText("99")).toBeInTheDocument();
  rerender(<Granaries {...p} snapshot={p.bundle.history[1]} currentTurn={5} />);
  expect(within(screen.getByRole("table", { name: "Granaries at snapshot 5" })).getByText("12")).toBeInTheDocument();
});
