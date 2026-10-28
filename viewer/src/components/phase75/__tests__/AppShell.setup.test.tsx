/**
 * The shell's setup form launches a live run from labelled fields (browser
 * QA, scripts/qa-live-checkpoint.mjs, found the seed field without a name).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AppShell } from "../AppShell";

afterEach(cleanup);

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
});
