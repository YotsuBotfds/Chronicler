/**
 * Live streaming appends turns: each `turn` message brings new history and
 * timeline arrays (useLiveConnection), and the shell's indexes are keyed by
 * those arrays (lib/bundleIndex). At every streamed turn the mounted shell
 * must render what a fresh shell renders from a copy of the same bundle.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../../types";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.ts).
beforeAll(() => preloadPanels());
afterEach(cleanup);

const base = systemsFixture as unknown as Bundle;

function shell(bundle: Bundle, currentTurn: number) {
  return (
    <AppShell
      surface="overview" onSurfaceChange={vi.fn()} bundle={bundle} bundleLoading={false} error={null}
      isLive connected serverState="running" currentTurn={currentTurn} playing={false} speed={1}
      onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()} lobbyInit={null}
      starting={false} onOpenBundleFile={vi.fn()}
    />
  );
}

/** The live bundle after `count` snapshots: new arrays, the same snapshot and event objects. */
function streamed(count: number): Bundle {
  const history = base.history.slice(0, count);
  const through = history[history.length - 1].turn;
  return {
    ...base,
    history,
    events_timeline: base.events_timeline.filter((event) => event.turn < through),
    named_events: base.named_events.filter((event) => event.turn < through),
  };
}

/** The same viewer state in both shells: the Event Log open and a region pinned. */
function focus(container: HTMLElement) {
  fireEvent.click(within(container).getByRole("button", { name: "Event Log" }));
  fireEvent.click(container.querySelectorAll(".phase75-region-node")[1]);
}

function dom(container: HTMLElement): string {
  return container.innerHTML.replace(/recharts\d+/g, "rechartsN");
}

function fresh(bundle: Bundle, turn: number): string {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const view = render(shell(structuredClone(bundle), turn), { container: host });
  focus(host);
  const html = dom(host);
  view.unmount();
  host.remove();
  return html;
}

describe("a live session's streamed turns", () => {
  it("renders each appended turn as a fresh shell renders the same bundle", () => {
    let bundle = streamed(2);
    const live = render(shell(bundle, bundle.history[1].turn));
    focus(live.container);
    for (const count of [3, 4, 6, 9, 12, base.history.length]) {
      bundle = streamed(count);
      const turn = bundle.history[count - 1].turn;
      live.rerender(shell(bundle, turn));
      expect(dom(live.container)).toBe(fresh(bundle, turn));
      // Scrubbing back within the streamed turns reads the same indexes.
      const earlier = bundle.history[Math.floor(count / 2)].turn;
      live.rerender(shell(bundle, earlier));
      expect(dom(live.container)).toBe(fresh(bundle, earlier));
      live.rerender(shell(bundle, turn));
    }
    expect(live.container.querySelectorAll(".phase75-left-rail .phase75-event-row").length).toBeGreaterThan(0);
  }, 60000);

  it("shows an intervention's changed stat (the last snapshot replaced)", () => {
    const bundle = streamed(6);
    const turn = bundle.history[5].turn;
    const live = render(shell(bundle, turn));
    focus(live.container);
    const last = bundle.history[5];
    const civ = Object.keys(last.civ_stats)[0];
    // useLiveConnection's `ack` for a `set` command: a new history array with a new last snapshot.
    const changed: Bundle = {
      ...bundle,
      history: [...bundle.history.slice(0, -1),
        { ...last, civ_stats: { ...last.civ_stats, [civ]: { ...last.civ_stats[civ], treasury: 987654 } } }],
    };
    live.rerender(shell(changed, turn));
    expect(dom(live.container)).toBe(fresh(changed, turn));
  });
});
