import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../../types";
import { AppShell } from "../AppShell";

afterEach(cleanup);

// Bundle version 5: Khorain Kingdom dies by turn 4 and is left out of every
// later snapshot. Give its end-of-run world state a different treasury so
// the inspector can only show its final row by reading the history.
const base = systemsFixture as unknown as Bundle;
const bundle: Bundle = {
  ...base,
  world_state: {
    ...base.world_state,
    civilizations: base.world_state.civilizations.map((civ) => (
      civ.name === "Khorain Kingdom" ? { ...civ, treasury: 999 } : civ
    )),
  },
};
const finalRow = base.history.find((s) => s.turn === 4)!.civ_stats["Khorain Kingdom"];

function renderAt(currentTurn: number) {
  render(
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
  fireEvent.click(screen.getByRole("button", { name: "Khorain Kingdom" }));
  return document.querySelector(".phase75-right-rail") as HTMLElement;
}

function statRow(inspector: HTMLElement, label: string): string {
  const rows = Array.from(inspector.querySelectorAll(".phase75-stat-row"));
  const found = rows.find((element) => element.querySelector("span")?.textContent === label);
  return found?.querySelector("strong")?.textContent ?? "";
}

describe("AppShell civ inspector over a pruned history", () => {
  it("shows a living civ as active", () => {
    const inspector = renderAt(1);
    expect(statRow(inspector, "Status")).toBe("Active");
  });

  it("shows the death row in the snapshot of the death", () => {
    const inspector = renderAt(4);
    expect(statRow(inspector, "Status")).toBe("Fallen");
    expect(statRow(inspector, "Treasury")).toBe(String(finalRow.treasury));
  });

  it("keeps the final row when scrubbed past the death", () => {
    const inspector = renderAt(120);
    expect(statRow(inspector, "Status")).toBe("Fallen (final record, turn 4)");
    expect(statRow(inspector, "Treasury")).toBe(String(finalRow.treasury));
    expect(statRow(inspector, "Leader")).toBe(finalRow.leader_name);
    expect(within(inspector).getByText("Khorain Kingdom")).toBeInTheDocument();
  });
});
