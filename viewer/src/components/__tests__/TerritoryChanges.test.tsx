import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { TerritoryChanges } from "../TerritoryChanges";

afterEach(cleanup);

describe("Territory changes", () => {
  it("keeps controls and history inspection at the selected turn; only View turn seeks", () => {
    const bundle = comparisonBundle([1, 4, 9]);
    bundle.history[1].region_control.A = "B";
    const inspect = vi.fn(), seek = vi.fn(), comparison = vi.fn();
    render(<TerritoryChanges bundle={bundle} currentTurn={4} onInspectEntity={inspect} onSeek={seek} onComparisonChange={comparison} />);
    const earlier = screen.getByRole("combobox", { name: "Territory earlier turn" });
    expect(within(earlier).getAllByRole("option").map((row) => row.textContent)).toEqual(["1"]);
    expect(screen.getByRole("status")).toHaveTextContent("T1 → T4");
    fireEvent.change(screen.getByRole("combobox", { name: "Territory civilization focus" }), { target: { value: "0" } });
    expect(comparison).toHaveBeenCalledWith(1, 0);
    expect(screen.getByText("Gained: 0 · Lost: 1 · Unchanged: 0 · Outside focus: 1 · Unknown: 0")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Territory region scope" }), { target: { value: "lost" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect history: A" }));
    expect(inspect).toHaveBeenCalledWith({ kind: "region", name: "A" });
    expect(seek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View turn 1" }));
    expect(seek).toHaveBeenCalledExactlyOnceWith(1);
  });
  it("updates the earlier endpoint without seeking and can use a changed map civilization", () => {
    const bundle = comparisonBundle();
    const comparison = vi.fn(), seek = vi.fn();
    const props = { bundle, currentTurn: 3, onInspectEntity: vi.fn(), onSeek: seek, onComparisonChange: comparison };
    const view = render(<TerritoryChanges {...props} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Territory earlier turn" }), { target: { value: "1" } });
    expect(comparison).toHaveBeenCalledWith(1, null);
    view.rerender(<TerritoryChanges {...props} selectedCivilization="B" />);
    fireEvent.click(screen.getByRole("button", { name: "Use map civilization: B" }));
    expect(comparison).toHaveBeenLastCalledWith(1, 1);
    expect(seek).not.toHaveBeenCalled();
    view.rerender(<TerritoryChanges {...props} currentTurn={2} />);
    expect(screen.getByRole("combobox", { name: "Territory earlier turn" })).toHaveValue("1");
  });
  it("reports unknown exact endpoints and hides explicit seek buttons without two valid records", () => {
    render(<TerritoryChanges bundle={comparisonBundle([1, 4, 9])} currentTurn={3} onInspectEntity={vi.fn()} onSeek={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Selected snapshot not recorded or ambiguous");
    expect(screen.queryByRole("button", { name: /View turn/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Unknown: 2/)).toBeInTheDocument();
  });
  it("caps visible regions and reveals remaining history links on request", () => {
    const bundle = comparisonBundle();
    bundle.world_state.regions = Array.from({ length: 23 }, (_, index) => ({ ...bundle.world_state.regions[0], name: `Region ${index}` }));
    render(<TerritoryChanges bundle={bundle} currentTurn={2} onInspectEntity={vi.fn()} selectedRegion="Region 0" />);
    expect(screen.getAllByRole("button", { name: /Inspect history:/ })).toHaveLength(20);
    expect(screen.getByRole("row", { name: /Region 0 Unknown/ })).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByRole("button", { name: "Show more regions (3 remaining)" }));
    expect(screen.getAllByRole("button", { name: /Inspect history:/ })).toHaveLength(23);
    expect(screen.queryByRole("button", { name: /View turn/ })).not.toBeInTheDocument();
  });
  it("does not offer ambiguous civilization names, future names or duplicate-name history links", () => {
    const bundle = comparisonBundle();
    bundle.world_state.civilizations[0].name = "Future";
    bundle.world_state.civilizations[1].name = "Future";
    bundle.world_state.regions[1].name = "A";
    render(<TerritoryChanges bundle={bundle} currentTurn={2} selectedCivilization="Future" onInspectEntity={vi.fn()} />);
    const focus = screen.getByRole("combobox", { name: "Territory civilization focus" });
    expect(within(focus).getAllByRole("option")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Inspect history:/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("Ambiguous region name")).toHaveLength(2);
  });
});
