import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SetupLobby } from "../SetupLobby";
import type { LobbyInit } from "../../types";

const LOBBY_INIT: LobbyInit = {
  scenarios: [
    {
      file: "test.yaml",
      name: "Test Scenario",
      description: "A test scenario for unit tests",
      world_name: "TestWorld",
      civs: [
        { name: "Civ A", values: ["Honor", "Trade"] },
        { name: "Civ B", values: ["War"] },
      ],
      regions: [
        { name: "Plains", terrain: "plains", x: null, y: null },
        { name: "Mountains", terrain: "mountain", x: null, y: null },
      ],
    },
    {
      file: "minimal.yaml",
      name: "Minimal",
      description: "No civs or regions",
      world_name: "Minimal",
      civs: [],
      regions: [],
    },
  ],
  models: ["model-a", "model-b"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
};

describe("SetupLobby", () => {
  it("renders all six control sections", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    expect(screen.getByLabelText("Scenario")).toBeTruthy();
    expect(screen.getByLabelText("Seed")).toBeTruthy();
    expect(screen.getByLabelText("Turns")).toBeTruthy();
    expect(screen.getByLabelText("Civs")).toBeTruthy();
    expect(screen.getByLabelText("Regions")).toBeTruthy();
    expect(screen.getByLabelText("Sim Model")).toBeTruthy();
    expect(screen.getByLabelText("Narrative Model")).toBeTruthy();
    expect(screen.getByRole("button", { name: /launch/i })).toBeTruthy();
  });

  it("disables civs when scenario has civs", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    expect(screen.getByLabelText("Civs")).toBeDisabled();
  });

  it("disables regions when scenario has regions", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    expect(screen.getByLabelText("Regions")).toBeDisabled();
  });

  it("enables civs/regions independently for scenarios without them", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "minimal.yaml" } });
    expect(screen.getByLabelText("Civs")).not.toBeDisabled();
    expect(screen.getByLabelText("Regions")).not.toBeDisabled();
  });

  it("disables launch button when starting", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={true} error={null} />
    );

    expect(screen.getByRole("button", { name: /starting/i })).toBeDisabled();
  });

  it("calls onLaunch with correct params", () => {
    const onLaunch = vi.fn();
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={onLaunch} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Turns"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: /launch/i }));

    expect(onLaunch).toHaveBeenCalledTimes(1);
    const params = onLaunch.mock.calls[0][0];
    expect(params.turns).toBe(100);
    expect(params.seed).toBe(42);
    expect(params.scenario).toBeNull();
    expect(params.civs).toBe(4);
    expect(params.regions).toBe(8);
    expect(params.sim_model).toBe("model-a");
    expect(params.narrative_model).toBe("model-a");
    expect(params.resume_state).toBeNull();
  });

  it("shows resume badge and disables fields on valid state.json", async () => {
    const onLaunch = vi.fn();
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={onLaunch} starting={false} error={null} />
    );

    const stateJson = JSON.stringify({
      turn: 22,
      name: "TestWorld",
      seed: 42,
      civilizations: [{ name: "CivA" }, { name: "CivB" }],
      regions: [{ name: "R1", controller: "CivA" }],
      relationships: {},
      events_timeline: [],
      named_events: [],
      scenario_name: null,
    });
    const file = new File([stateJson], "state.json", { type: "application/json" });

    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await vi.waitFor(() => {
      expect(screen.getByText(/resuming from turn 22/i)).toBeTruthy();
    });

    expect(screen.getByLabelText("Civs")).toBeDisabled();
    expect(screen.getByLabelText("Regions")).toBeDisabled();
    expect(screen.getByLabelText("Scenario")).toBeDisabled();
  });

  it("shows error on invalid resume file", async () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    const badJson = JSON.stringify({ foo: "bar" });
    const file = new File([badJson], "bad.json", { type: "application/json" });
    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await vi.waitFor(() => {
      expect(screen.getByText(/invalid save file/i)).toBeTruthy();
    });
  });

  it("clears resume on clear button click", async () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    const stateJson = JSON.stringify({
      turn: 10, name: "W", seed: 1,
      civilizations: [{ name: "C" }], regions: [{ name: "R", controller: null }],
      relationships: {}, events_timeline: [], named_events: [], scenario_name: null,
    });
    const file = new File([stateJson], "state.json", { type: "application/json" });
    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await vi.waitFor(() => {
      expect(screen.getByText(/resuming from turn 10/i)).toBeTruthy();
    });

    fireEvent.click(screen.getByLabelText("Clear resume"));
    expect(screen.queryByText(/resuming/i)).toBeNull();
    expect(screen.getByLabelText("Civs")).not.toBeDisabled();
  });

  it("shows error banner when error is set", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error="Scenario not found" />
    );

    expect(screen.getByText("Scenario not found")).toBeTruthy();
  });

  it("shows preview when scenario selected", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    expect(screen.getByRole("heading", { name: "Test Scenario" })).toBeTruthy();
    expect(screen.getByText("A test scenario for unit tests")).toBeTruthy();
  });
});
