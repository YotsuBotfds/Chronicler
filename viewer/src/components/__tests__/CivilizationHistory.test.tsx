import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import type { Event } from "../../types";
import { CivilizationHistory } from "../CivilizationHistory";

afterEach(cleanup);
const event: Event = { turn: 0, event_type: "collapse", actors: ["A"], description: "Explicit recorded collapse", importance: 8, consequences: [], event_id: "collapse-0" };

describe("Civilization life history panel", () => {
  it("inspects sourced events and regions without seeking; View turn alone moves timeline", () => {
    const bundle = comparisonBundle();
    bundle.events_timeline = [event];
    const seek = vi.fn(), inspect = vi.fn(), region = vi.fn();
    render(<CivilizationHistory bundle={bundle} currentTurn={2} civilizationIndex={0}
      onSeek={seek} onInspectEvent={inspect} onInspectRegion={region} />);
    expect(screen.getByRole("heading", { name: "Civilization life history: A" })).toBeInTheDocument();
    expect(screen.getByText('Source: history[0].civ_stats["A"]')).toBeInTheDocument();
    expect(screen.getByText(/events_timeline: tick 0, type collapse, event_id collapse-0/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect event: collapse" }));
    expect(inspect).toHaveBeenCalledWith(event);
    fireEvent.click(screen.getAllByRole("button", { name: "Inspect region: A" })[0]);
    expect(region).toHaveBeenCalledWith(0, "A");
    fireEvent.change(screen.getByRole("combobox", { name: "Civilization history entries" }), { target: { value: "events" } });
    expect(seek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View turn 1" }));
    expect(seek).toHaveBeenCalledExactlyOnceWith(1);
  });
  it("hides future names and shows unavailable identity honestly", () => {
    const bundle = comparisonBundle();
    bundle.world_state.civilizations[1].name = "Future Empire";
    render(<CivilizationHistory bundle={bundle} currentTurn={1} civilizationIndex={1} />);
    expect(screen.queryByText(/Future Empire/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No unambiguous civilization observation");
    expect(screen.queryByRole("button", { name: /View turn/ })).not.toBeInTheDocument();
  });
  it("shows missing/pruned rows as unknown and provides visible rules for life claims", () => {
    const bundle = comparisonBundle();
    delete bundle.history[1].civ_stats.A;
    bundle.pruned_civ_stats = { A: [{ from_turn: 2, snapshots: 1 }] };
    render(<CivilizationHistory bundle={bundle} currentTurn={2} civilizationIndex={0} onSeek={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Civilization row not recorded at selected turn 2");
    expect(screen.getByText("Values unknown at this date. Earlier rows are not carried forward.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View turn 2" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Sources and selection rules"));
    expect(screen.getByText(/First observation is not a foundation/)).toBeVisible();
    expect(screen.getByText(/Version-5 pruning can omit/)).toBeVisible();
    expect(screen.getByText(/recorded alive flag measures whether/)).toBeVisible();
  });
  it("bounds dates and same-date events with explicit reveal controls", () => {
    const bundle = comparisonBundle(Array.from({ length: 24 }, (_, index) => index + 1));
    bundle.events_timeline = Array.from({ length: 9 }, (_, index) => ({ ...event, event_id: `event-${index}`, description: `Recorded event ${index}` }));
    const seek = vi.fn();
    render(<CivilizationHistory bundle={bundle} currentTurn={24} civilizationIndex={0} onSeek={seek} onInspectEvent={vi.fn()} />);
    expect(screen.queryByRole("heading", { name: "Turn 1" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: /^Turn / })).toHaveLength(20);
    fireEvent.click(screen.getByRole("button", { name: "Show earlier dates (4 remaining)" }));
    expect(screen.getAllByRole("heading", { name: /^Turn / })).toHaveLength(24);
    expect(screen.getAllByRole("button", { name: "Inspect event: collapse" })).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: "Show more events (3 remaining)" }));
    expect(screen.getAllByRole("button", { name: "Inspect event: collapse" })).toHaveLength(9);
    expect(seek).not.toHaveBeenCalled();
  });
  it("preserves named events without fabricating selectable event refs", () => {
    const bundle = comparisonBundle();
    bundle.events_timeline = [event, { ...event }];
    bundle.named_events = [{ turn: 0, event_type: "coup", actors: ["A"], name: "Named coup", description: "Named coup description", region: null, importance: 8 }];
    const inspect = vi.fn();
    render(<CivilizationHistory bundle={bundle} currentTurn={1} civilizationIndex={0} onInspectEvent={inspect} />);
    expect(screen.getByText(/Named coup description/)).toBeInTheDocument();
    expect(screen.getByText(/Named event preserved as a source record/)).toBeInTheDocument();
    expect(screen.getAllByText(/key is ambiguous/)).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Inspect event:/ })).not.toBeInTheDocument();
    expect(inspect).not.toHaveBeenCalled();
  });
  it("shows only explicitly validated secession lineage", () => {
    const bundle = comparisonBundle();
    bundle.events_timeline = [{ ...event, event_type: "secession", actors: ["A", "B"], turn: 1 }];
    render(<CivilizationHistory bundle={bundle} currentTurn={2} civilizationIndex={1} />);
    const lineage = screen.getByRole("heading", { name: "Recorded lineage" }).nextElementSibling!;
    expect(within(lineage as HTMLElement).getByText(/recorded secession from A \(index 0\) to B \(index 1\)/)).toBeInTheDocument();
  });
});
