/**
 * The shell's lazy panels (lazyPanels.tsx): before their chunks arrive the
 * rest of the shell renders and each panel holds a polite loading status;
 * then the panels render in place. This file loads the chunks itself (the
 * other AppShell tests preload them).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle, LanguagesField } from "../../../types";
import { sampleLanguages } from "../../../__fixtures__/languagesField";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

afterEach(cleanup);

const bundle = {
  ...(systemsFixture as unknown as Bundle),
  languages: sampleLanguages() as LanguagesField,
};

function shell() {
  return (
    <AppShell
      surface="overview" onSurfaceChange={vi.fn()} bundle={bundle} bundleLoading={false} error={null}
      isLive={false} connected={false} serverState="completed" currentTurn={bundle.history[3].turn} playing={false}
      speed={1} onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()} lobbyInit={null}
      starting={false} onOpenBundleFile={vi.fn()}
    />
  );
}

describe("lazy panels", () => {
  it("shows the shell with loading statuses, then the panels in their place", async () => {
    render(shell());
    // The map, rail and inspector are there before the panels' chunks.
    expect(document.querySelectorAll(".phase75-region-node").length).toBe(bundle.world_state.regions.length);
    const statuses = screen.getAllByRole("status");
    expect(statuses.map((status) => status.textContent)).toEqual(expect.arrayContaining([
      "Loading the languages...", "Loading the simulation systems...",
    ]));
    for (const status of statuses) {
      expect(status).toHaveAttribute("aria-busy", "true");
    }
    expect(screen.queryByRole("tablist", { name: "Simulation systems" })).not.toBeInTheDocument();

    await act(async () => {
      await preloadPanels();
    });
    // React reveals a boundary's content on its next retry after the chunk arrives.
    expect(await screen.findByRole("tablist", { name: "Simulation systems" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Languages")).toBeInTheDocument();
    expect(document.querySelector("[data-lazy-fallback]")).toBeNull();
  });

  it("renders the panels at once on a later mount", () => {
    render(shell());
    expect(screen.getByRole("tablist", { name: "Simulation systems" })).toBeInTheDocument();
    expect(document.querySelector("[data-lazy-fallback]")).toBeNull();
  });
});
