/**
 * The shell at an earlier scrubbed turn shows that turn's record, never the
 * end-of-run state (consistency follow-ups; each case failed on main
 * dae4ba5). Synthetic records are added to the real-shaped systems fixture.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import { sampleField } from "../../../__fixtures__/historiographyField";
import type { Bundle, Event, NewChronicleEntry } from "../../../types";
import { UNCONTROLLED_COLOR } from "../../../lib/colors";
import { AppShell, type AppSurface } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.tsx).
beforeAll(() => preloadPanels());
afterEach(cleanup);

const base = systemsFixture as unknown as Bundle;

function shell(bundle: Bundle, currentTurn: number, surface: AppSurface = "overview", onSeek = vi.fn()) {
  return (
    <AppShell
      surface={surface} onSurfaceChange={vi.fn()} bundle={bundle} bundleLoading={false} error={null}
      isLive={false} connected={false} serverState="completed" currentTurn={currentTurn} playing={false}
      speed={1} onSeek={onSeek} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()} lobbyInit={null}
      starting={false} onOpenBundleFile={vi.fn()}
    />
  );
}

function inspector(): HTMLElement {
  return document.querySelector(".phase75-right-rail") as HTMLElement;
}

function statRow(label: string): string {
  const rows = Array.from(inspector().querySelectorAll(".phase75-stat-row"));
  const found = rows.find((element) => element.querySelector("span")?.textContent === label);
  return found?.querySelector("strong")?.textContent ?? "";
}

function selectRegion(index: number) {
  fireEvent.click(document.querySelectorAll(".phase75-region-node")[index]);
}

/** Pin an event from the Event Log (it lists the 24 latest events up to the turn). */
function pinEvent(event: Event) {
  fireEvent.click(screen.getByRole("button", { name: "Event Log" }));
  const row = [...document.querySelectorAll(".phase75-event-row")]
    .find((element) => element.textContent?.includes(event.description));
  expect(row).toBeDefined();
  fireEvent.click(row!);
}

/** An event with an id that the Event Log lists at its own turn. */
function listedAtItsTurn(events: Event[], test: (event: Event) => boolean): Event {
  const found = events.find((event) => {
    if (!event.event_id || !test(event)) return false;
    const visible = events.filter((other) => other.turn <= event.turn).sort((a, b) => b.turn - a.turn).slice(0, 24);
    return visible.includes(event);
  });
  expect(found).toBeDefined();
  return found!;
}

describe("a turn before the first snapshot", () => {
  // A resumed run: its history starts at turn 201.
  const late: Bundle = {
    ...base,
    metadata: { ...base.metadata, total_turns: 320 },
    history: base.history.map((snapshot) => ({ ...snapshot, turn: snapshot.turn + 200 })),
  };

  it("shows no later snapshot: no civilization values, chips or controllers", () => {
    // Main dae4ba5 showed the first snapshot (turn 201) at turn 100.
    render(shell(late, 100));
    expect(document.querySelectorAll(".phase75-civ-chip")).toHaveLength(0);
    const fills = [...document.querySelectorAll(".phase75-region-node")].map((node) => node.getAttribute("fill"));
    expect(fills.length).toBeGreaterThan(0);
    expect(new Set(fills)).toEqual(new Set([UNCONTROLLED_COLOR]));
    for (const name of Object.keys(late.history[0].civ_stats)) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });

  it("says Unavailable for a civilization selected at a later turn", () => {
    const shown = late.history.filter((snapshot) => snapshot.turn <= 250).at(-1)!;
    const civ = Object.entries(shown.civ_stats).find(([, row]) => row.alive !== false && row.regions.length > 0)![0];
    const view = render(shell(late, 250));
    fireEvent.click(screen.getByRole("button", { name: civ }));
    expect(statRow("Status")).toBe("Active");
    view.rerender(shell(late, 100));
    expect(statRow("Civilization")).toBe(civ);
    expect(statRow("Status")).toBe("Unavailable");
    expect(statRow("Leader")).toBe("Unavailable");
    expect(statRow("Treasury")).toBe("Unavailable");
  });

  it("shows the first snapshot from its own turn", () => {
    render(shell(late, 201));
    expect(document.querySelectorAll(".phase75-civ-chip").length).toBeGreaterThan(0);
  });
});

describe("dated records on the map and in the inspector", () => {
  const region = base.world_state.regions[0];

  it.each(["harvest_preparedness", "scientific_research_agenda_opened", "scientific_research_agenda_closed", "scientific_research_capacity_blocked"])("navigates %s to its containing snapshot and hides it when scrubbing back", (kind) => {
    const receipt: Event = { turn: 10, event_type: kind, event_id: "receipt", actors: [],
      importance: 3, description: "Actual purchases recorded after tick ten.", consequences: [] };
    const bundle = { ...base, events_timeline: [receipt] };
    const onSeek = vi.fn();
    const view = render(shell(bundle, 11, "overview", onSeek));
    pinEvent(receipt);
    expect(onSeek).toHaveBeenLastCalledWith(11);
    expect(statRow("Event")).toBe(receipt.event_type);
    view.rerender(shell(bundle, 10, "overview", onSeek));
    expect(statRow("Event")).toBe("Unavailable");
    expect(inspector().textContent).not.toContain(receipt.description);
    expect(document.querySelector(".phase75-left-rail")?.textContent).not.toContain(receipt.description);
  });

  it("marks a named event's region only from its turn", () => {
    const bundle: Bundle = {
      ...base,
      named_events: [{ name: "The Sack of the Mire", event_type: "sack", turn: 90, actors: [], region: region.name,
                       description: "Sacked.", importance: 8 }],
    };
    const view = render(shell(bundle, 50));
    expect(document.querySelectorAll(".phase75-event-marker")).toHaveLength(0);
    view.rerender(shell(bundle, 90));
    expect(document.querySelectorAll(".phase75-event-marker")).toHaveLength(1);
  });

  it("gives a region's terrain at the turn, from its dated transitions", () => {
    // The final terrain is the world state's; the region was plains until turn 80.
    const transition: Event = {
      turn: 80, event_type: "terrain_transition", actors: [], importance: 6, consequences: [],
      description: `${region.name} transforms from plains to ${region.terrain}`,
    } as unknown as Event;
    const bundle: Bundle = { ...base, events_timeline: [...base.events_timeline, transition] };
    const view = render(shell(bundle, 50));
    selectRegion(0);
    expect(statRow("Region")).toBe(region.name);
    expect(statRow("Terrain")).toBe("plains");
    view.rerender(shell(bundle, 80));
    expect(statRow("Terrain")).toBe(region.terrain);
  });

  it("does not show an event pinned at a later turn, nor consequences recorded after the turn", () => {
    const events = base.events_timeline;
    const effectsOf = (event: Event) => events.filter((other) => (other.causes ?? []).includes(event.event_id!));
    const target = listedAtItsTurn(events, (event) => event.turn >= 1 && effectsOf(event).length > 0
      && effectsOf(event).every((effect) => effect.turn > event.turn));
    const lastEffect = Math.max(...effectsOf(target).map((effect) => effect.turn));

    // At its own turn its consequences are later: none listed (main dae4ba5 listed them).
    const view = render(shell(base, target.turn));
    pinEvent(target);
    expect(statRow("Event")).toBe(target.event_type);
    expect(within(inspector()).queryByLabelText("Recorded consequences")).toBeNull();
    view.rerender(shell(base, lastEffect));
    expect(within(inspector()).getByLabelText("Recorded consequences")).toHaveTextContent(
      `${effectsOf(target).length} event`);

    // Scrubbed back before it: the pinned event is not described.
    view.rerender(shell(base, target.turn - 1));
    expect(statRow("Event")).toBe("Unavailable");
    expect(inspector()).toHaveTextContent(`Not yet recorded at turn ${target.turn - 1}.`);
    expect(inspector().textContent).not.toContain(target.description);
    expect(inspector()).toHaveTextContent(`Pinned event not yet recorded at turn ${target.turn - 1}.`);
  });

  it("tells an account whose archive falls later as it stood at the turn", () => {
    const target = listedAtItsTurn(base.events_timeline, (event) => event.turn >= 1 && event.turn <= 100);
    const field = sampleField(target.event_id);
    const lostAt = target.turn + 5;
    // court:1's copy is lost at turn target + 5 (the fixture's loss moved later).
    field.accounts = field.accounts.map((row) => (row[1] === "court:1" && row[0] === target.event_id
      ? row.map((value, index) => (index === 7 ? lostAt : value)) : row));
    field.archives = field.archives.map((archive) => ({
      ...archive, losses: archive.losses.map((loss) => ({ ...loss, turn: lostAt })),
    }));
    const bundle: Bundle = { ...base, historiography: field };
    const view = render(shell(bundle, target.turn));
    pinEvent(target);
    const accounts = within(inspector()).getByLabelText("In-world accounts");
    expect(accounts).toHaveTextContent("The Kethani host gave ground in good order.");
    expect(accounts.textContent).not.toContain("lost: their archive");
    expect(accounts).toHaveTextContent("contested (magnitude, ruler, silence)");
    view.rerender(shell(bundle, lostAt));
    const later = within(inspector()).getByLabelText("In-world accounts");
    expect(later).toHaveTextContent(`lost: their archive was sacked (turn ${lostAt})`);
    expect(later).toHaveTextContent("contested (lost, magnitude, ruler, silence)");
  });
});

describe("the chronicle feed and the technique layer", () => {
  it("shows a narrated moment and a gap summary once their last turn has passed", () => {
    const entry = {
      turn: 40, covers_turns: [40, 60], events: [], named_events: [], narrative: "The long war ended at the ford.",
      importance: 8, narrative_role: "climax", causal_links: [],
    } as NewChronicleEntry;
    const bundle: Bundle = {
      ...base,
      chronicle_entries: [entry],
      gap_summaries: [{ turn_range: [61, 80], event_count: 12, top_event_type: "war", stat_deltas: {},
                        territory_changes: 2 }],
    };
    const view = render(shell(bundle, 50));
    expect(document.body.textContent).not.toContain("The long war ended at the ford.");
    view.rerender(shell(bundle, 60));
    expect(document.body.textContent).toContain("The long war ended at the ford.");
    expect(document.body.textContent).not.toContain("Mechanical window 61-80");
    view.rerender(shell(bundle, 80));
    expect(document.body.textContent).toContain("Mechanical window 61-80");
  });

  it("offers on the technique layer only techniques practised by the turn", () => {
    // In the fixture sailing is first practised at turn 111.
    const view = render(shell(base, 50));
    fireEvent.click(screen.getByRole("radio", { name: "Techniques" }));
    const options = () => [...(within(document.querySelector(".phase75-layer-select") as HTMLElement)
      .getByRole("combobox") as HTMLSelectElement).options].map((option) => option.value);
    expect(options()).not.toContain("sailing");
    expect(options()).toContain("writing");
    view.rerender(shell(base, 111));
    expect(options()).toContain("sailing");
  });
});
