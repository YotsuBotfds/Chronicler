import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { cityHistorySelection, institutionHistoryFixture } from "../../__fixtures__/institutionHistory";
import { InstitutionHistory } from "../InstitutionHistory";

describe("city institution history component", () => {
  it("shows dated city values and makes seeking distinct from inspecting relationships/events", () => {
    const inspect = vi.fn(), event = vi.fn(), seek = vi.fn();
    render(<InstitutionHistory bundle={institutionHistoryFixture()} currentTurn={3} selection={cityHistorySelection}
      onInspectRelated={inspect} onSelectEvent={event} onViewRecordedTurn={seek} />);
    expect(screen.getByText("New Harbor · settlement ID 41")).toBeInTheDocument();
    expect(screen.getByText("sacked · snapshot 3 (source tick 2)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect region: B" }));
    expect(inspect).toHaveBeenCalledWith({ kind: "region", name: "B" });
    fireEvent.click(screen.getByRole("button", { name: "Inspect recorded event: sacked" }));
    expect(event).toHaveBeenCalledWith(expect.objectContaining({ event_id: "city-41-sacked", turn: 2 }));
    expect(seek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View snapshot 1" }));
    expect(seek).toHaveBeenCalledWith(1);
  });

  it("removes future observation and lifecycle details immediately on rewind", () => {
    const bundle = institutionHistoryFixture();
    const { rerender } = render(<InstitutionHistory bundle={bundle} currentTurn={10} selection={cityHistorySelection} />);
    expect(screen.getByText(/FUTURE_SECRET_CITY · settlement/)).toBeInTheDocument();
    rerender(<InstitutionHistory bundle={bundle} currentTurn={1} selection={cityHistorySelection} />);
    expect(screen.getByText("Old Harbor · settlement ID 41")).toBeInTheDocument();
    expect(screen.queryByText(/FUTURE_SECRET/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sacked · snapshot/)).not.toBeInTheDocument();
  });

  it("shows city-first coverage and unresolved selection without fabricating a lifecycle", () => {
    const { rerender } = render(<InstitutionHistory bundle={institutionHistoryFixture()} currentTurn={3} selection={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Choose a city");
    rerender(<InstitutionHistory bundle={institutionHistoryFixture()} currentTurn={3} selection={{ ...cityHistorySelection, identity: null }} />);
    expect(screen.getByRole("status")).toHaveTextContent("identity is unresolved");
    expect(screen.queryByText("Dated lifecycle records")).not.toBeInTheDocument();
  });

  it("keeps an absent selected row distinct from destruction or a last-known owner", () => {
    render(<InstitutionHistory bundle={institutionHistoryFixture()} currentTurn={6} selection={cityHistorySelection} onInspectRelated={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("ID absent");
    expect(screen.queryByRole("button", { name: /Inspect region:/ })).not.toBeInTheDocument();
    expect(screen.getByText("fell · snapshot 6 (source tick 5)")).toBeInTheDocument();
    expect(screen.getByText(/do not establish an institution's causal benefit or recovery/)).toBeInTheDocument();
  });

  it("bounds initial history rendering with keyboard-operable reveal controls", () => {
    const bundle = institutionHistoryFixture();
    const snapshot = bundle.history[0];
    bundle.history = Array.from({ length: 20 }, (_, index) => ({ ...snapshot, turn: index + 1 }));
    render(<InstitutionHistory bundle={bundle} currentTurn={20} selection={cityHistorySelection} />);
    expect(screen.getByText("Showing up to 8 recent entries per list.")).toBeInTheDocument();
    expect(screen.queryByText("Snapshot 1: recorded")).not.toBeInTheDocument();
    const reveal = screen.getByRole("button", { name: "Show 8 more history entries" });
    reveal.focus();
    expect(reveal).toHaveFocus();
    fireEvent.click(reveal);
    expect(screen.getByText("Showing up to 16 recent entries per list.")).toBeInTheDocument();
  });
});
