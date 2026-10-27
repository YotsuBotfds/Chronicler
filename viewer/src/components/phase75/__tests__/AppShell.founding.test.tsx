import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle, CivSnapshot } from "../../../types";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";
import { buildCivilizationViews, isFounded } from "../../../lib/civilizationViews";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.tsx).
beforeAll(() => preloadPanels());
afterEach(cleanup);

// A civilization founded at turn 60 (a secession, say): no history row
// before, and an end-of-run world state with its final values.
const base = systemsFixture as unknown as Bundle;
const donor = base.world_state.civilizations[0];
const FOUNDED = 60;
const lateRow = (snapshotRow: CivSnapshot): CivSnapshot => ({
  ...snapshotRow, population: 777, regions: ["R2"], leader_name: "Late Leader", alive: true,
});
const bundle: Bundle = {
  ...base,
  world_state: {
    ...base.world_state,
    civilizations: [
      ...base.world_state.civilizations,
      {
        ...donor, name: "Late Realm", population: 1000, military: 99, economy: 98, treasury: 997,
        regions: ["R2"], leader: { ...donor.leader, name: "Final Leader" },
      },
    ],
  },
  history: base.history.map((snapshot) => (snapshot.turn < FOUNDED ? snapshot : {
    ...snapshot,
    civ_stats: { ...snapshot.civ_stats, "Late Realm": lateRow(Object.values(snapshot.civ_stats)[0]) },
  })),
};

function renderAt(currentTurn: number) {
  return render(
    <AppShell
      surface="overview"
      onSurfaceChange={vi.fn()}
      bundle={bundle}
      bundleLoading={false}
      error={null}
      isLive={false}
      connected={false}
      serverState="completed"
      currentTurn={currentTurn}
      playing={false}
      speed={1}
      onSeek={vi.fn()}
      onPlay={vi.fn()}
      onPause={vi.fn()}
      onSetSpeed={vi.fn()}
      lobbyInit={null}
      starting={false}
      onOpenBundleFile={vi.fn()}
    />,
  );
}

function statRow(label: string): string {
  const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
  const rows = Array.from(inspector.querySelectorAll(".phase75-stat-row"));
  const found = rows.find((element) => element.querySelector("span")?.textContent === label);
  return found?.querySelector("strong")?.textContent ?? "";
}

describe("a civilization before its founding", () => {
  it("has no chip, ranking or summary at turn 1, and no end-of-run values anywhere", () => {
    renderAt(1);
    expect(screen.queryByRole("button", { name: "Late Realm" })).toBeNull();
    const shell = document.body.textContent ?? "";
    expect(shell).not.toContain("Late Realm");
    expect(shell).not.toContain("Final Leader");
  });

  it("shows unavailable values when it stays selected while scrubbing back", () => {
    const view = renderAt(120);
    fireEvent.click(screen.getByRole("button", { name: "Late Realm" }));
    expect(statRow("Status")).toBe("Active");
    expect(statRow("Leader")).toBe("Late Leader");
    view.rerender(
      <AppShell
        surface="overview" onSurfaceChange={vi.fn()} bundle={bundle} bundleLoading={false} error={null}
        isLive={false} connected={false} serverState="completed" currentTurn={1} playing={false} speed={1}
        onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()} lobbyInit={null}
        starting={false} onOpenBundleFile={vi.fn()}
      />,
    );
    expect(statRow("Civilization")).toBe("Late Realm");
    expect(statRow("Status")).toBe("Not yet founded");
    expect(statRow("Leader")).toBe("Unavailable");
    expect(statRow("Treasury")).toBe("Unavailable");
    expect(screen.queryByRole("button", { name: "Late Realm" })).toBeNull();
  });

  it("builds a pending view without values, and the founded view from its first row", () => {
    const first = base.history[0];
    const [pending] = buildCivilizationViews(bundle, first).filter((c) => c.name === "Late Realm");
    expect(isFounded(pending)).toBe(false);
    expect(pending).toEqual({ founded: false, name: "Late Realm", values: donor.values, goal: donor.goal,
                              status: "Not yet founded" });
    const later = bundle.history.find((s) => s.turn >= FOUNDED)!;
    const [founded] = buildCivilizationViews(bundle, later).filter((c) => c.name === "Late Realm");
    expect(isFounded(founded) && founded.population).toBe(777);
  });

  it("uses the world state only when there is no history at all (a live session before turn 1)", () => {
    const empty: Bundle = { ...bundle, history: [] };
    const views = buildCivilizationViews(empty, null);
    expect(views.every(isFounded)).toBe(true);
  });
});
