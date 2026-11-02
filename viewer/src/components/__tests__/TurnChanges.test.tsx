import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import source from "../../__fixtures__/systems_bundle.json";
import type { Bundle, Event } from "../../types";
import { TurnChanges } from "../TurnChanges";

function fixture() {
  const bundle = structuredClone(source) as unknown as Bundle;
  const civ = Object.keys(bundle.history[0].civ_stats)[0];
  const event: Event = { turn: 2, event_type: "war", event_id: "comparison-war", actors: [civ],
    description: "An explicitly recorded war", importance: 5, consequences: [] };
  bundle.events_timeline = [event];
  return { bundle, civ, event };
}

describe("What changed controls", () => {
  it("changes endpoints and inspects an event without moving the main timeline; explicit View moves it", () => {
    const { bundle, civ, event } = fixture();
    const onSeek = vi.fn(), onSelectEvent = vi.fn();
    render(<TurnChanges bundle={bundle} currentTurn={12} selectedCivilization={civ}
      onSeek={onSeek} onSelectEvent={onSelectEvent} />);
    fireEvent.change(screen.getByLabelText("Compare to turn"), { target: { value: "3" } });
    expect(screen.getByRole("table", { name: "Changes between recorded turns" })).toBeInTheDocument();
    expect(onSeek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect event" }));
    expect(onSelectEvent).toHaveBeenCalledWith(event);
    expect(onSeek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View turn 3" }));
    expect(onSeek).toHaveBeenCalledWith(3);
  });

  it("keeps regional population unknown and lets a user return to the map selection", () => {
    const { bundle, civ } = fixture();
    const region = bundle.world_state.regions[0].name;
    const onSeek = vi.fn();
    render(<TurnChanges bundle={bundle} currentTurn={12} selectedRegion={region} onSeek={onSeek} />);
    const table = screen.getByRole("table", { name: "Changes between recorded turns" });
    const population = within(table).getByRole("row", { name: /Regional model population/ });
    expect(within(population).getAllByText("Not recorded")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Compare civilization or region"), {
      target: { value: JSON.stringify(["civilization", civ]) },
    });
    fireEvent.click(screen.getByRole("button", { name: `Use map selection: ${region}` }));
    expect(screen.getByLabelText("Compare civilization or region")).toHaveValue(JSON.stringify(["region", region]));
    expect(onSeek).not.toHaveBeenCalled();
  });

  it("removes later endpoints and event content when the selected turn rewinds", () => {
    const { bundle, civ } = fixture();
    const props = { bundle, selectedCivilization: civ, onSeek: vi.fn() };
    const { rerender } = render(<TurnChanges {...props} currentTurn={12} />);
    fireEvent.change(screen.getByLabelText("Compare to turn"), { target: { value: "3" } });
    rerender(<TurnChanges {...props} currentTurn={1} />);
    expect(screen.getByLabelText("Compare to turn")).toHaveValue("1");
    expect(within(screen.getByLabelText("Compare to turn")).getAllByRole("option")).toHaveLength(1);
    expect(screen.queryByText("An explicitly recorded war")).not.toBeInTheDocument();
  });

  it("retains a map-derived comparison target when event inspection replaces the map selection", () => {
    const { bundle, event } = fixture();
    const region = bundle.world_state.regions[1].name;
    event.region = region;
    const onSeek = vi.fn(), onSelectEvent = vi.fn();
    const { rerender } = render(<TurnChanges bundle={bundle} currentTurn={12} selectedRegion={region}
      onSeek={onSeek} onSelectEvent={onSelectEvent} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect event" }));
    rerender(<TurnChanges bundle={bundle} currentTurn={12} onSeek={onSeek} onSelectEvent={onSelectEvent} />);
    expect(screen.getByLabelText("Compare civilization or region")).toHaveValue(JSON.stringify(["region", region]));
    expect(onSelectEvent).toHaveBeenCalledWith(event);
    expect(onSeek).not.toHaveBeenCalled();
  });
});
