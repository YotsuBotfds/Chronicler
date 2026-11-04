import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { historicalSearchFixture } from "../../__fixtures__/historicalSearch";
import { comparisonSnapshot } from "../../__fixtures__/completedRunHistory";
import { HistoricalSearch } from "../HistoricalSearch";

afterEach(() => vi.useRealTimers());
describe("historical search controls", () => {
  it("finds an old actor after many observations and updates on turn changes", () => {
    vi.useFakeTimers();
    const bundle = historicalSearchFixture();
    bundle.history = Array.from({ length: 250 }, (_, i) => comparisonSnapshot(i + 1));
    bundle.history[0].civ_stats.A.leader_name = "Ancient Unique Actor";
    bundle.history[249].civ_stats.A.leader_name = "Future Unique Actor";
    const { rerender } = render(<HistoricalSearch bundle={bundle} currentTurn={250} onInspect={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Ancient Unique Actor" } });
    act(() => vi.advanceTimersByTime(160));
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 1");
    expect(screen.getByRole("button", { name: "Inspect: Ancient Unique Actor" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Future Unique Actor" } });
    act(() => vi.advanceTimersByTime(160));
    rerender(<HistoricalSearch bundle={bundle} currentTurn={249} onInspect={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 0");
  });
  it("inspects without seeking and makes viewing a recorded turn a separate action", () => {
    const inspect = vi.fn(), seek = vi.fn();
    render(<HistoricalSearch bundle={historicalSearchFixture()} currentTurn={4} onInspect={inspect} onViewRecordedTurn={seek} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect: Old Realm" }));
    expect(inspect).toHaveBeenCalledWith(expect.objectContaining({ name: "Old Realm", turn: 3, identity: { namespace: "civilization", index: 0 } }));
    expect(seek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View recorded turn 3: Old Realm" }));
    expect(seek).toHaveBeenCalledWith(inspect.mock.calls[0][0]);
  });

  it("debounces name matching and supports native keyboard-operable controls", () => {
    vi.useFakeTimers();
    render(<HistoricalSearch bundle={historicalSearchFixture()} currentTurn={3} onInspect={vi.fn()} />);
    const search = screen.getByRole("searchbox", { name: "Name or dated alias" });
    search.focus();
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "aru confederacy" } });
    expect(screen.getByRole("status")).toHaveTextContent("Updating search");
    act(() => vi.advanceTimersByTime(160));
    expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 1");
    expect(screen.getByRole("button", { name: "Inspect: Old Realm" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Entity type" }), { target: { value: "actor" } });
    expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 0");
    expect(screen.getByText(/Missing observations do not establish/)).toBeInTheDocument();
  });

  it("immediately removes future records on timeline rewind, even with a pending query", () => {
    vi.useFakeTimers();
    const bundle = historicalSearchFixture();
    const { rerender } = render(<HistoricalSearch bundle={bundle} currentTurn={10} onInspect={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Inspect: FUTURE_SECRET_REALM" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "FUTURE_SECRET" } });
    rerender(<HistoricalSearch bundle={bundle} currentTurn={3} onInspect={vi.fn()} />);
    expect(screen.queryByText(/FUTURE_SECRET_REALM/)).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(160));
    expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 0");
  });

  it("provides identity and alias coverage without requiring a seek handler", () => {
    render(<HistoricalSearch bundle={historicalSearchFixture()} currentTurn={3} onInspect={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /View recorded turn/ })).not.toBeInTheDocument();
    expect(screen.getByText("Search coverage and identity")).toBeInTheDocument();
    expect(screen.getByText(/Person IDs are unavailable/)).toBeInTheDocument();
    expect(screen.getAllByText(/identity unresolved/).length).toBeGreaterThan(0);
    expect(screen.getByText(/No dated historical observation/)).toBeInTheDocument();
  });
});
