import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { EntityHistory } from "../EntityHistory";
import { chainBundle, snapshotOf } from "../../../lib/__tests__/recoveryChainFixture";
afterEach(cleanup);

describe("linked history navigation", () => {
  it("follows stable entity links and seeks an observed snapshot", () => {
    const bundle = chainBundle(), onSeek = vi.fn(), onSelectRegion = vi.fn();
    render(<EntityHistory bundle={bundle} snapshot={snapshotOf(bundle, 28)} currentTurn={28} onSeek={onSeek} onSelectRegion={onSelectRegion} onSelectCivilization={vi.fn()} onSelectEvent={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText("Recorded entity"), { target: { value: "person:13" } });
    expect(screen.getByRole("table", { name: "Linked history of Person #13" })).toBeInTheDocument();
    expect(screen.getAllByText(/Regional context, not this person's record/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Project #0" })[0]);
    expect(screen.getByLabelText("Recorded entity")).toHaveValue("project:0");
    fireEvent.click(screen.getAllByRole("button", { name: "Snapshot 28" })[0]);
    expect(onSeek).toHaveBeenCalledWith(28);
    fireEvent.click(screen.getAllByRole("button", { name: "Open Sapphire Coast" })[0]);
    expect(onSelectRegion).toHaveBeenCalledWith("Sapphire Coast");
  });
  it("renders nothing for a legacy run without stable entity records", () => {
    const bundle = chainBundle((s) => { delete s.livelihoods; });
    const { container } = render(<EntityHistory bundle={bundle} snapshot={bundle.history[0]} currentTurn={28} onSeek={vi.fn()} onSelectRegion={vi.fn()} onSelectCivilization={vi.fn()} onSelectEvent={vi.fn()}/>);
    expect(container).toBeEmptyDOMElement();
  });
});
