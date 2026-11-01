/**
 * A chronicle passage's sources: the feed card's toggle opens the lazily
 * loaded list; a later (retrospective) fact waits for its turn; a source's
 * event link pins without seeking, and its separate turn link seeks.
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
    fireEvent.click(within(items[0]).getByRole("button", { name: /^Inspect source event:/ }));
    expect(onJump).not.toHaveBeenCalled();
    expect(onSelect).toHaveBeenCalledWith(events[5]);
    fireEvent.click(within(items[0]).getByRole("button", { name: /^Go to source turn/ }));
    expect(onJump).toHaveBeenCalledExactlyOnceWith(events[5].turn);
    expect(onSelect).toHaveBeenCalledTimes(1);

    fireEvent.click(within(panel).getByRole("button", { name: "All 3 facts given" }));
    expect(within(panel).getAllByRole("listitem")).toHaveLength(3);

    rerender(<ChronicleSources bundle={base} entry={entry()} currentTurn={events[late].turn}
      onJumpToTurn={onJump} onSelectEvent={onSelect} />);
    const now = screen.getByLabelText("Passage sources");
    expect(now.textContent).not.toContain("dated later");
    expect(within(now).getAllByRole("listitem").some((li) => li.textContent?.includes("later"))).toBe(true);
  });

  it("keeps an explicit turn jump when no event inspector callback is supplied", () => {
    const onJump = vi.fn();
    render(<ChronicleSources bundle={base} entry={entry()} currentTurn={10} onJumpToTurn={onJump} />);
    expect(screen.queryByRole("button", { name: /^Inspect source event:/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Go to source turn/ }));
    expect(onJump).toHaveBeenCalledExactlyOnceWith(events[5].turn);
  });

  it("keeps non-event sources as explicit turn jumps", () => {
    const onJump = vi.fn();
    const passage = entry();
    passage.provenance!.facts = [["w2-6", 6]];
    passage.provenance!.spans = [[0, 18, ["w2-6"]]];
    render(<ChronicleSources bundle={base} entry={passage} currentTurn={10} onJumpToTurn={onJump} onSelectEvent={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /^Go to source turn 6:/ }));
    expect(onJump).toHaveBeenCalledExactlyOnceWith(6);
  });

  it("waits for a completed-tick source's snapshot and uses its clock for the explicit turn jump", () => {
    const receipt = { ...events[5], turn: 10, event_type: "harvest_preparedness", description: "Paid receipt at tick ten." };
    const bundle = { ...base, events_timeline: [receipt] };
    const passage = entry();
    passage.provenance!.facts = [["e0", 10]];
    passage.provenance!.spans = [[0, 18, ["e0"]]];
    const onJump = vi.fn();
    const onSelect = vi.fn();
    const view = render(<ChronicleSources bundle={bundle} entry={passage} currentTurn={10} onJumpToTurn={onJump} onSelectEvent={onSelect} />);
    expect(screen.queryByRole("button", { name: /^Inspect source event:/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Paid receipt/)).not.toBeInTheDocument();
    view.rerender(<ChronicleSources bundle={bundle} entry={passage} currentTurn={11} onJumpToTurn={onJump} onSelectEvent={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /^Inspect source event:/ }));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith(receipt);
    expect(onJump).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /^Go to source turn 11:/ }));
    expect(onJump).toHaveBeenCalledExactlyOnceWith(11);
  });

  it("renders nothing for a passage without provenance", () => {
    const passage = entry();
    delete passage.provenance;
    const { container } = render(<ChronicleSources bundle={base} entry={passage} currentTurn={10} onJumpToTurn={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
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
