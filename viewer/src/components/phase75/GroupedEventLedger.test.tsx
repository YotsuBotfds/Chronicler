import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Event } from "../../types";
import { GroupedEventLedger } from "./GroupedEventLedger";

const event = (i: number, patch: Partial<Event> = {}): Event => ({ turn: 4, event_type: "migration", actors: ["Alpha"],
  description: `Record ${i}`, consequences: ["Recorded consequence"], importance: 2, ...patch });
const expand = () => screen.getAllByRole("button", { name: /events on this page/ }).forEach(button => {
  if (button.getAttribute("aria-expanded") === "false") fireEvent.click(button);
});
afterEach(cleanup);

describe("GroupedEventLedger", () => {
  it("distinguishes empty types/actors and literal all from the unfiltered state", () => {
    const events = [event(0, { actors: ["all"], event_type: "" }), event(1, { actors: [""] }), event(2)];
    const view = render(<GroupedEventLedger events={events} currentTurn={4} />);
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: JSON.stringify("") } });
    expect(screen.getByRole("status")).toHaveTextContent("1–1 of 1 events");
    expect(screen.getByText("Record 0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    fireEvent.change(screen.getByLabelText("Civilization"), { target: { value: JSON.stringify("") } });
    expect(screen.getByText("Record 1")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1–1 of 1 events");
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} selectedCivilization="all" />);
    expect(screen.getByLabelText("Civilization")).toHaveValue(JSON.stringify("all"));
    expect(screen.getByText("Record 0")).toBeInTheDocument();
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("1–3 of 3 events");
  });

  it("keeps an active type visible after rewind and does not resurrect clamped late pages", () => {
    const events = [event(0, { turn: 1, event_type: "early" }), ...Array.from({ length: 54 }, (_, i) => event(i + 1))];
    const view = render(<GroupedEventLedger events={events} currentTurn={4} />);
    fireEvent.change(screen.getByLabelText("Event type"), { target: { value: JSON.stringify("migration") } });
    view.rerender(<GroupedEventLedger events={events} currentTurn={1} />);
    expect(screen.getByLabelText("Event type")).toHaveValue(JSON.stringify("migration"));
    expect(screen.getByRole("option", { name: "migration" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("0–0 of 0 events");
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} />);
    fireEvent.click(screen.getByRole("button", { name: "Next events" }));
    view.rerender(<GroupedEventLedger events={events.slice(0, 2)} currentTurn={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 1");
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 3");
  });

  it("moves keyboard focus to the available navigation button at either page boundary", () => {
    render(<GroupedEventLedger events={Array.from({ length: 25 }, (_, i) => event(i))} currentTurn={4} />);
    const next = screen.getByRole("button", { name: "Next events" });
    const previous = screen.getByRole("button", { name: "Previous events" });
    next.focus();
    fireEvent.click(next);
    expect(previous).toHaveFocus();
    expect(next).toBeDisabled();
    fireEvent.click(previous);
    expect(next).toHaveFocus();
    expect(previous).toBeDisabled();
  });

  it("expands a >24 burst losslessly across pages with exact source callbacks and accessible navigation", () => {
    const events = Array.from({ length: 55 }, (_, i) => event(i, { description: "Identical appearance" }));
    const onSelectEvent = vi.fn();
    render(<GroupedEventLedger events={events} currentTurn={4} onSelectEvent={onSelectEvent} />);
    expect(screen.getByRole("status")).toHaveTextContent("1–24 of 55 events · Page 1 of 3");
    expect(screen.getByRole("button", { name: "Previous events" })).toBeDisabled();
    const seen: number[] = [];
    for (let page = 1; page <= 3; page++) {
      const toggle = screen.getByRole("button", { name: /events on this page/ });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      const controlled = document.getElementById(toggle.getAttribute("aria-controls")!);
      expect(controlled).toHaveAttribute("hidden");
      for (let repeat = 0; repeat < 3; repeat++) {
        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        expect(screen.getAllByText("Identical appearance")).toHaveLength(page === 3 ? 7 : 24);
        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "false");
      }
      fireEvent.click(toggle);
      const buttons = screen.getAllByRole("button", { name: /Inspect source event/ });
      buttons.forEach(button => fireEvent.click(button));
      seen.push(...buttons.map(button => Number(button.textContent!.split("#")[1]) - 1));
      if (page < 3) fireEvent.click(screen.getByRole("button", { name: "Next events" }));
    }
    expect(seen).toEqual(events.map((_, i) => i));
    expect(new Set(seen).size).toBe(55);
    seen.forEach((sourceIndex, i) => {
      expect(onSelectEvent.mock.calls[i][0]).toBe(events[sourceIndex]);
      expect(onSelectEvent.mock.calls[i][1]).toBe(sourceIndex);
    });
    expect(screen.getByRole("button", { name: "Next events" })).toBeDisabled();
    expect(within(screen.getByRole("navigation", { name: "Event ledger pages" })).getAllByRole("button")).toHaveLength(2);
  });

  it("resets late pages and interrupted expansions on each filter change without unrelated backfill", () => {
    const events = Array.from({ length: 40 }, (_, i) => event(i, { actors: i < 3 ? ["Beta"] : ["Alpha"] }));
    events.push(event(99, { turn: 99, description: "Future secret", event_type: "future_type", actors: ["Future civ"] }));
    render(<GroupedEventLedger events={events} currentTurn={4} />);
    fireEvent.click(screen.getByRole("button", { name: "Next events" }));
    expand();
    fireEvent.change(screen.getByLabelText("Civilization"), { target: { value: JSON.stringify("Beta") } });
    expect(screen.getByRole("status")).toHaveTextContent("1–3 of 3 events · Page 1 of 1");
    expand();
    expect(screen.queryByText("Record 3")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Actors: Beta/)).toHaveLength(3);
    expect(screen.queryByText(/Future secret|Future civ|future_type/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Civilization"), { target: { value: "" } });
    expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 2");
    expect(screen.getByRole("button", { name: /events on this page/ })).toHaveAttribute("aria-expanded", "false");
    for (const [label, value] of [["Event type", "migration"], ["From turn", "4"], ["Through turn", "4"]]) {
      fireEvent.click(screen.getByRole("button", { name: "Next events" }));
      fireEvent.change(screen.getByLabelText(label), { target: { value: label === "Event type" ? JSON.stringify(value) : value } });
      expect(screen.getByRole("status")).toHaveTextContent("Page 1 of 2");
    }
    fireEvent.change(screen.getByLabelText("From turn"), { target: { value: "5" } });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("From turn")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("button", { name: /events on this page/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByRole("status")).toHaveTextContent("1–24 of 40");
  });

  it("handles empty/missing actors and empty results without inventing actor or entity scope", () => {
    const missing = event(1, { actors: undefined }) as Event;
    const events = [event(0, { actors: [] }), missing, event(2, { event_type: "war", turn: 2 })];
    render(<GroupedEventLedger events={events} currentTurn={4} civilizations={["Alpha", "Nobody"]} />);
    expand();
    expect(screen.getAllByText(/No actors recorded/)).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Civilization"), { target: { value: JSON.stringify("Nobody") } });
    expect(screen.getByRole("status")).toHaveTextContent("0–0 of 0 events · Page 1 of 1");
    expect(screen.getByText(/No events match/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next events" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Civilization"), { target: { value: JSON.stringify("Alpha") } });
    expect(screen.getByText("Record 2")).toBeInTheDocument();
  });

  it("resets on external focus/cutoff changes, clamps source shrinkage, and supports independent instances", () => {
    const events = Array.from({ length: 55 }, (_, i) => event(i, { turn: i < 3 ? 1 : 4 }));
    const view = render(<GroupedEventLedger events={events} currentTurn={4} />);
    fireEvent.click(screen.getByRole("button", { name: "Next events" }));
    view.rerender(<GroupedEventLedger events={events} currentTurn={1} />);
    expect(screen.getByRole("status")).toHaveTextContent("1–3 of 3 events · Page 1 of 1");
    expand();
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} selectedCivilization="Nobody" />);
    expect(screen.getByLabelText("Civilization")).toHaveValue(JSON.stringify("Nobody"));
    expect(screen.getByRole("status")).toHaveTextContent("0–0 of 0");
    view.rerender(<GroupedEventLedger events={events} currentTurn={4} selectedCivilization="Alpha" />);
    fireEvent.click(screen.getByRole("button", { name: "Next events" }));
    view.rerender(<GroupedEventLedger events={events.slice(0, 2)} currentTurn={4} selectedCivilization="Alpha" />);
    expect(screen.getByRole("status")).toHaveTextContent("1–2 of 2 events · Page 1 of 1");
    view.rerender(<><GroupedEventLedger events={events} currentTurn={4} /><GroupedEventLedger events={events} currentTurn={4} /></>);
    const ids = screen.getAllByRole("button", { name: /events on this page/ }).map(b => b.getAttribute("aria-controls"));
    expect(new Set(ids).size).toBe(ids.length);
    ids.forEach(id => expect(document.getElementById(id!)).not.toBeNull());
  });
});
