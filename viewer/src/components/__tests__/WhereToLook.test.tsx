import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { WhereToLook } from "../WhereToLook";

describe("Where should I look", () => {
  it("opens entity history at the current turn and shows threshold provenance", () => {
    const inspect = vi.fn();
    render(<WhereToLook bundle={regionalFixture()} currentTurn={1} onInspectEntity={inspect} />);
    expect(screen.getByText("Food / need 0.5")).toBeInTheDocument();
    expect(screen.getByText("Snapshot 1 (completed tick 0)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect history: A" }));
    expect(inspect).toHaveBeenCalledWith({ kind: "region", name: "A" });
    expect(screen.getByText(/no earlier recorded snapshot/)).toBeInTheDocument();
  });
  it("caps visibly, groups repeats and lets the user reveal remaining entities", () => {
    const bundle = regionalFixture();
    bundle.world_state.regions = Array.from({ length: 11 }, (_, i) => ({ ...bundle.world_state.regions[0], name: `Region ${i}` }));
    bundle.history[0].food!.sufficiency = Array(11).fill(0.5);
    render(<WhereToLook bundle={bundle} currentTurn={1} onInspectEntity={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 8 of 11");
    expect(screen.getAllByRole("button", { name: /Inspect history:/ })).toHaveLength(8);
    fireEvent.click(screen.getByRole("button", { name: "Show more (3 remaining)" }));
    expect(screen.getAllByRole("button", { name: /Inspect history:/ })).toHaveLength(11);
    expect(screen.queryByRole("button", { name: /Show more/ })).not.toBeInTheDocument();
  });
  it("reports unavailable selected turns without turning missing observations into reassurance", () => {
    render(<WhereToLook bundle={regionalFixture()} currentTurn={0} onInspectEntity={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Selected snapshot unavailable");
    expect(screen.getByText(/Check observation coverage/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Inspect history:/ })).not.toBeInTheDocument();
  });
});
