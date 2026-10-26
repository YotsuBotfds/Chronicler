import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../../types";
import { AppShell, type AppSurface } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.tsx).
beforeAll(() => preloadPanels());
afterEach(cleanup);

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;

function renderShell(bundle: Bundle, currentTurn: number, surface: AppSurface = "overview") {
  const onSeek = vi.fn();
  render(
    <AppShell
      surface={surface}
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
      onSeek={onSeek}
      onPlay={vi.fn()}
      onPause={vi.fn()}
      onSetSpeed={vi.fn()}
      lobbyInit={null}
      starting={false}
      onOpenBundleFile={vi.fn()}
    />,
  );
  return { onSeek };
}

describe("AppShell simulation systems", () => {
  it("adds nothing for a bundle that records no system", () => {
    renderShell(sample, sample.history[sample.history.length - 1].turn);
    expect(screen.queryByRole("region", { name: "Simulation systems" })).not.toBeInTheDocument();
    fireEvent.click(document.querySelector(".phase75-region-node") as Element);
    expect(screen.queryByLabelText(/^Systems in /)).not.toBeInTheDocument();
  });

  it("shows the systems panel and the selected region's epidemic and technique state", () => {
    renderShell(systems, 120);
    const panel = screen.getByRole("region", { name: "Simulation systems" });
    fireEvent.click(within(screen.getByRole("table", { name: "Outbreaks at turn 120" }))
      .getByRole("button", { name: "Dililene Coast" }));
    const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
    expect(within(inspector).getByText("Dililene Coast")).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Epidemics in Dililene Coast")).toHaveTextContent("Marsh fever");
    expect(within(inspector).getByLabelText("Techniques in Dililene Coast")).toHaveTextContent("Writing");
    expect(panel).toBeInTheDocument();
  });

  it("pins a panel event in the inspector with its recorded causes", () => {
    const ids = new Set(systems.events_timeline.map((event) => event.event_id));
    const cited = systems.events_timeline.find((event) =>
      event.event_type === "loan_taken" && (event.causes ?? []).some((cause) => ids.has(cause)));
    expect(cited).toBeDefined();
    const { onSeek } = renderShell(systems, 120, "trade");
    expect(screen.getByRole("tab", { name: "Finance" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: "Loans" }));
    const list = screen.getByRole("list", { name: "Finance events" });
    fireEvent.click(within(list).getAllByText(cited!.description)[0]);
    expect(onSeek).toHaveBeenCalledWith(cited!.turn);
    const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
    expect(within(inspector).getByText("loan_taken")).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Recorded causes")).toBeInTheDocument();
  });
});
