/**
 * Feature options in the requests the viewer sends: Batch Lab's batch_start
 * config, the legacy lobby's and the shell's start command. Nothing selected
 * (or an older server without a catalog) sends exactly what it sent before.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import served from "../../__fixtures__/featureCatalog.json";
import type { LobbyInit, WorldState } from "../../types";
import { BatchPanel } from "../BatchPanel";
import { SetupLobby } from "../SetupLobby";
import { AppShell } from "../phase75/AppShell";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const OLD_CONFIG_KEYS = ["parallel", "seed_count", "seed_start", "simulate_only", "tuning_overrides", "turns", "workers"];

function batch(onStart = vi.fn(), { featureCatalog }: { featureCatalog: unknown } = { featureCatalog: served }) {
  render(
    <BatchPanel batchState="idle" report={null} progress={null} error={null} featureCatalog={featureCatalog}
      onStart={onStart} onCancel={vi.fn()} onReset={vi.fn()} />,
  );
  return onStart;
}

function openFeatures() {
  fireEvent.click(screen.getByRole("button", { name: /Experimental features/ }));
}

describe("Batch Lab", () => {
  it("sends the same config as before when nothing is selected", () => {
    for (const catalog of [served, undefined]) {
      const onStart = batch(vi.fn(), { featureCatalog: catalog });
      fireEvent.click(screen.getByRole("button", { name: /Run Batch/i }));
      expect(Object.keys(onStart.mock.calls[0][0]).sort()).toEqual(OLD_CONFIG_KEYS);
      cleanup();
    }
  });

  it("hides the section for an older server", () => {
    batch(vi.fn(), { featureCatalog: undefined });
    expect(screen.queryByRole("button", { name: /Experimental features/ })).toBeNull();
  });

  it("sends the selected features and agent mode", () => {
    const catalog = structuredClone(served);
    catalog.surfaces.batch.agents = "off";
    const onStart = batch(vi.fn(), { featureCatalog: catalog });
    openFeatures();
    fireEvent.change(screen.getByRole("combobox", { name: /Agent mode for these runs/ }), { target: { value: "hybrid" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /^Workshops/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Workshop mode/ }), { target: { value: "cost_only" } });
    fireEvent.click(screen.getByRole("button", { name: /Run Batch/i }));
    const config = onStart.mock.calls[0][0];
    expect(config.agents).toBe("hybrid");
    expect(config.features).toEqual({ workshops: true, workshop_mode: "cost_only" });
  });
});

const LOBBY: LobbyInit = {
  scenarios: [],
  models: ["m"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
  feature_catalog: served,
};

describe("the legacy setup lobby", () => {
  it("launches a new world with the selected features", () => {
    const onLaunch = vi.fn();
    render(<SetupLobby lobbyInit={LOBBY} onLaunch={onLaunch} starting={false} error={null} />);
    openFeatures();
    fireEvent.click(screen.getByRole("checkbox", { name: /^Food allocation/ }));
    fireEvent.click(screen.getByRole("button", { name: /launch/i }));
    expect(onLaunch.mock.calls[0][0].features).toEqual({ food_allocation: true });
  });

  it("sends no features field when nothing is selected or the server sent no catalog", () => {
    for (const lobby of [LOBBY, { ...LOBBY, feature_catalog: undefined }]) {
      const onLaunch = vi.fn();
      render(<SetupLobby lobbyInit={lobby} onLaunch={onLaunch} starting={false} error={null} />);
      fireEvent.click(screen.getByRole("button", { name: /launch/i }));
      expect("features" in onLaunch.mock.calls[0][0]).toBe(false);
      cleanup();
    }
  });
});

describe("the shell's setup form", () => {
  function shell(onLaunch = vi.fn(), lobbyInit: LobbyInit = LOBBY) {
    render(
      <AppShell
        surface="setup" onSurfaceChange={vi.fn()} bundle={null} bundleLoading={false} error={null}
        isLive connected serverState="lobby" currentTurn={1} playing={false} speed={1}
        onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()}
        lobbyInit={lobbyInit} starting={false} onLaunch={onLaunch} onOpenBundleFile={vi.fn()}
      />,
    );
    return onLaunch;
  }

  it("launches with the selected features, and without them by default", () => {
    const plain = shell();
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect("features" in plain.mock.calls[0][0]).toBe(false);
    cleanup();
    const onLaunch = shell();
    openFeatures();
    fireEvent.click(screen.getByRole("checkbox", { name: /^Grain reserves/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /^Local budgets/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Local budget mode/ }), { target: { value: "fixed_shares" } });
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect(onLaunch.mock.calls[0][0].features).toEqual({
      grain_reserves: true, local_budgets: true, local_budget_mode: "fixed_shares",
    });
  });

  it("hides the section for an older server", () => {
    shell(vi.fn(), { ...LOBBY, feature_catalog: undefined });
    expect(screen.queryByRole("button", { name: /Experimental features/ })).toBeNull();
  });

  it("does not send features with a resumed save", async () => {
    const onLaunch = vi.fn();
    render(
      <AppShell
        surface="setup" onSurfaceChange={vi.fn()} bundle={null} bundleLoading={false} error={null}
        isLive connected serverState="lobby" currentTurn={1} playing={false} speed={1}
        onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()}
        lobbyInit={LOBBY} starting={false} onLaunch={onLaunch} onOpenBundleFile={vi.fn()}
      />,
    );
    openFeatures();
    fireEvent.click(screen.getByRole("checkbox", { name: /^Food allocation/ }));
    const save: Partial<WorldState> = { name: "Saved", turn: 3, civilizations: [], regions: [] };
    fireEvent.drop(screen.getByText("Drop `state.json` or click to browse"),
      { dataTransfer: { files: [new File([JSON.stringify(save)], "state.json")] } });
    expect(await screen.findByText("Resuming from turn 3")).toBeInTheDocument();
    expect(screen.getByRole("note").textContent).toMatch(/apply to new worlds only/);
    expect((screen.getByRole("checkbox", { name: /^Food allocation/ }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect("features" in onLaunch.mock.calls[0][0]).toBe(false);
  });
});
