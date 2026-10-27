/**
 * A chronicle passage's sources: the feed card's toggle opens the lazily
 * loaded list; a later (retrospective) fact waits for its turn; a source's
 * turn link seeks and an event source opens in the inspector.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle, NewChronicleEntry } from "../../../types";
import { AppShell } from "../AppShell";
import { ChronicleSources } from "../ChronicleSources";
import { preloadPanels } from "../lazyPanels";

beforeAll(() => preloadPanels());
afterEach(cleanup);

const base = systemsFixture as unknown as Bundle;
const events = base.events_timeline;
const late = events.findIndex((event) => event.turn > 60);

function entry(): NewChronicleEntry {
  return {
    turn: 2, covers_turns: [2, 6], events: [], named_events: [],
    narrative: "A king made a vow. Later sorrow came.", importance: 3, narrative_role: "climax",
    causal_links: [],
    provenance: {
      v: 1, narrator: "llm", as_of: 6, names: [],
      facts: [["e5", events[5].turn], ["e6", events[6].turn], [`e${late}`, events[late].turn, "r"], ["w2-6", 6]],
      spans: [[0, 18, ["e5"]], [19, 37, [`e${late}`]]],
    },
  };
}

describe("ChronicleSources", () => {
  it("shows the cited facts, hides a later one until its turn, and links to turns", () => {
    const onJump = vi.fn();
    const onSelect = vi.fn();
    const { rerender } = render(
      <ChronicleSources bundle={base} entry={entry()} currentTurn={10} onJumpToTurn={onJump} onSelectEvent={onSelect} />,
    );
    const panel = screen.getByLabelText("Passage sources");
    expect(panel.textContent).toContain("Cites 2 of the 4 facts given");
    expect(panel.textContent).toContain("1 dated later, shown once their turn has passed");
    const items = within(panel).getAllByRole("listitem");
    expect(items).toHaveLength(1);  // the later citation waits for its turn
    expect(items[0].textContent).toContain(events[5].description);
    fireEvent.click(within(items[0]).getByRole("button"));
    expect(onJump).toHaveBeenCalledWith(events[5].turn);
    expect(onSelect).toHaveBeenCalledWith(events[5]);

    fireEvent.click(within(panel).getByRole("button", { name: "All 3 facts given" }));
    expect(within(panel).getAllByRole("listitem")).toHaveLength(3);

    rerender(<ChronicleSources bundle={base} entry={entry()} currentTurn={events[late].turn}
      onJumpToTurn={onJump} onSelectEvent={onSelect} />);
    const now = screen.getByLabelText("Passage sources");
    expect(now.textContent).not.toContain("dated later");
    expect(within(now).getAllByRole("listitem").some((li) => li.textContent?.includes("later"))).toBe(true);
  });
});

describe("the chronicle feed", () => {
  it("opens a narrated passage's sources from its card", () => {
    const bundle = { ...base, chronicle_entries: [entry()] } as Bundle;
    render(
      <AppShell
        surface="overview" onSurfaceChange={vi.fn()} bundle={bundle} bundleLoading={false} error={null}
        isLive={false} connected={false} serverState="completed" currentTurn={20} playing={false}
        speed={1} onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()} lobbyInit={null}
        starting={false} onOpenBundleFile={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Chronicle" }));
    const toggle = screen.getByRole("button", { name: "Sources (4)" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Passage sources")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Passage sources").textContent).toContain(events[5].description);
    fireEvent.click(toggle);
    expect(screen.queryByLabelText("Passage sources")).toBeNull();
  });
});
