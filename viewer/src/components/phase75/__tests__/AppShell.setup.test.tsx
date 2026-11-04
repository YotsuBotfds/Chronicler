/**
 * The shell's setup form launches a live run from labelled fields (browser
 * QA, scripts/qa-live-checkpoint.mjs, found the seed field without a name).
 * The later cases characterize the form's other states (no lobby, custom
 * models, a scenario's fixed world size, a dropped save) before the form is
 * split out of AppShell.tsx.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { LobbyInit } from "../../../types";
import { AppShell } from "../AppShell";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function setup(lobbyInit: LobbyInit | null, onLaunch = vi.fn()) {
  return render(
    <AppShell
      surface="setup" onSurfaceChange={vi.fn()} bundle={null} bundleLoading={false} error={null}
      isLive={lobbyInit !== null} connected={lobbyInit !== null} serverState={lobbyInit ? "lobby" : "connecting"}
      currentTurn={1} playing={false} speed={1} onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()}
      onSetSpeed={vi.fn()} lobbyInit={lobbyInit} starting={false} onLaunch={onLaunch} onOpenBundleFile={vi.fn()}
    />,
  );
}

const lobby: LobbyInit = {
  models: ["alpha", "beta"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
  scenarios: [{
    file: "s.yaml", name: "Scenario S", description: "", world_name: "World S",
    civs: [{ name: "Ash", values: [] }, { name: "Birch", values: [] }, { name: "Cedar", values: [] }],
    regions: [{ name: "R1", terrain: "plains", x: 1, y: 1 }, { name: "R2", terrain: "forest", x: 2, y: 2 }],
  }],
};

function inspectorRow(label: string): string {
  const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
  const row = [...inspector.querySelectorAll(".phase75-stat-row")].find((element) => element.querySelector("span")?.textContent === label);
  return row?.querySelector("strong")?.textContent ?? "";
}

describe("the setup form", () => {
  it("names every world field and launches with their values", () => {
    const onLaunch = vi.fn();
    render(
      <AppShell
        surface="setup" onSurfaceChange={vi.fn()} bundle={null} bundleLoading={false} error={null}
        isLive connected serverState="lobby" currentTurn={1} playing={false} speed={1}
        onSeek={vi.fn()} onPlay={vi.fn()} onPause={vi.fn()} onSetSpeed={vi.fn()}
        lobbyInit={{ scenarios: [], models: [""], defaults: { turns: 50, civs: 4, regions: 8, seed: null } }}
        starting={false} onLaunch={onLaunch} onOpenBundleFile={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Turns"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Civilizations"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Regions"), { target: { value: "6" } });
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect(onLaunch).toHaveBeenCalledTimes(1);
    expect(onLaunch.mock.calls[0][0]).toMatchObject({ seed: 42, turns: 20, civs: 3, regions: 6, scenario: null });
  });

  it("disables every field without a lobby and says how to begin", () => {
    setup(null);
    for (const label of ["Scenario", "Seed", "Turns", "Civilizations", "Regions", "Sim Model", "Narrative Model"]) {
      expect(screen.getByLabelText(label)).toBeDisabled();
    }
    expect(screen.getByRole("button", { name: "Randomize" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run World" })).toBeDisabled();
    expect(screen.getByText(/Start the viewer from a live session to create a run/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Procedural world preview" })).toBeInTheDocument();
  });

  it("launches with a custom model endpoint, a scenario's fixed world size and a randomized seed", () => {
    const onLaunch = vi.fn();
    setup(lobby, onLaunch);
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "s.yaml" } });
    expect(screen.getByLabelText("Civilizations")).toBeDisabled();
    expect(screen.getByLabelText("Regions")).toBeDisabled();
    expect(screen.getAllByRole("button", { name: /^Inspect region / })).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Scenario S" })).toBeInTheDocument();
    expect(inspectorRow("World")).toBe("World S");
    expect(inspectorRow("Civilizations")).toBe("3");

    expect(screen.queryByLabelText("Custom Sim Endpoint")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sim Model"), { target: { value: "__custom__" } });
    fireEvent.change(screen.getByLabelText("Custom Sim Endpoint"), { target: { value: "http://local/sim" } });
    fireEvent.change(screen.getByLabelText("Narrative Model"), { target: { value: "beta" } });
    expect(screen.queryByLabelText("Custom Narrative Endpoint")).not.toBeInTheDocument();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    fireEvent.click(screen.getByRole("button", { name: "Randomize" }));
    expect(screen.getByLabelText("Seed")).toHaveValue(1073741823);
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect(onLaunch).toHaveBeenCalledExactlyOnceWith({
      scenario: "s.yaml", turns: 50, seed: 1073741823, civs: 3, regions: 2, sim_model: "http://local/sim",
      narrative_model: "beta", narrator: "local", resume_state: null,
    });
  });

  it("launches a dropped save with its world size until it is cleared, and says why a save is refused", async () => {
    const onLaunch = vi.fn();
    setup(lobby, onLaunch);
    const save = {
      turn: 7, name: "Saved World", seed: 9,
      civilizations: [{ name: "Ash", values: ["Honor"] }, { name: "Birch", values: [] }],
      regions: [
        { name: "R1", terrain: "plains", x: 1, y: 1, controller: "Ash" },
        { name: "R2", terrain: "hills", x: 3, y: 2, controller: null },
        { name: "R3", terrain: "coast", x: 2, y: 4, controller: "Birch" },
      ],
    };
    const dropzone = () => screen.getByText("Drop `state.json` or click to browse");
    const resumeInput = document.querySelectorAll<HTMLInputElement>('input[type="file"]')[1];
    const browse = vi.spyOn(resumeInput, "click");
    fireEvent.click(dropzone());
    expect(browse).toHaveBeenCalledTimes(1);

    fireEvent.drop(dropzone(), { dataTransfer: { files: [new File([JSON.stringify(save)], "state.json")] } });
    expect(await screen.findByText("Resuming from turn 7")).toBeInTheDocument();
    expect(screen.getByLabelText("Scenario")).toBeDisabled();
    expect(screen.getByLabelText("Civilizations")).toBeDisabled();
    expect(screen.getByLabelText("Regions")).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Resumed world preview" })).toBeInTheDocument();
    expect(within(document.querySelector(".phase75-topbar") as HTMLElement).getByText("Saved World")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Inspect region / })).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Run World" }));
    expect(onLaunch).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      scenario: null, seed: null, civs: 2, regions: 3, resume_state: save,
    }));

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText("Resuming from turn 7")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Civilizations")).toBeEnabled();
    fireEvent.drop(dropzone(), { dataTransfer: { files: [new File(["not json"], "state.json")] } });
    expect(await screen.findByText("Invalid save file - not valid JSON")).toBeInTheDocument();
    fireEvent.drop(dropzone(), { dataTransfer: { files: [new File([JSON.stringify({ civilizations: [] })], "state.json")] } });
    expect(await screen.findByText("Invalid save file - missing required fields")).toBeInTheDocument();
    expect(screen.getByLabelText("Civilizations")).toBeEnabled();
  });
});
