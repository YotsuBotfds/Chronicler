/**
 * Characterization of the shell's navigation: cancelling the compare
 * dialog, rewinding through the timeline (keyboard, pointer and live
 * bounds) and the one selection shared by the map, region list,
 * civilization chips and inspector. These cases pin the behavior before
 * the shell's presentation components are split out of AppShell.tsx.
 */
import type { ComponentProps } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../../types";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.ts).
beforeAll(() => preloadPanels());
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const systems = systemsFixture as unknown as Bundle;
const total = systems.metadata.total_turns;

function shell(overrides: Partial<ComponentProps<typeof AppShell>> = {}) {
  const props: ComponentProps<typeof AppShell> = {
    surface: "overview", onSurfaceChange: vi.fn(), bundle: systems, bundleLoading: false, error: null,
    isLive: false, connected: false, serverState: "completed", currentTurn: total, playing: false, speed: 1,
    onSeek: vi.fn(), onPlay: vi.fn(), onPause: vi.fn(), onSetSpeed: vi.fn(), lobbyInit: null, starting: false,
    onOpenBundleFile: vi.fn(), ...overrides,
  };
  return <AppShell {...props} />;
}

function inspector(): HTMLElement {
  return document.querySelector(".phase75-right-rail") as HTMLElement;
}

function statRow(label: string): string {
  const rows = Array.from(inspector().querySelectorAll(".phase75-stat-row"));
  const found = rows.find((element) => element.querySelector("span")?.textContent === label);
  return found?.querySelector("strong")?.textContent ?? "";
}

const regionList = () => screen.getByRole("combobox", { name: "Inspect a region" });
const regionNode = (name: string) => screen.getByRole("button", { name: `Inspect region ${name}` });
const slider = () => screen.getByRole("slider", { name: "Historical turn" });
const compareDialog = () => screen.queryByRole("dialog", { name: "Compare saved runs and reports" });

describe("cancelling the compare dialog", () => {
  it("closes on Escape, Close and the backdrop, returns focus and leaves the world as it was", () => {
    const onSeek = vi.fn();
    const onSurfaceChange = vi.fn();
    const region = systems.world_state.regions[1].name;
    render(shell({ currentTurn: 60, onSeek, onSurfaceChange }));
    fireEvent.click(regionNode(region));
    const opener = screen.getByRole("button", { name: "Compare saved runs" });

    opener.focus();
    fireEvent.click(opener);
    let dialog = compareDialog()!;
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "Completed runs" })).toHaveAttribute("aria-pressed", "true");
    // A choice made in the dialog is discarded with it.
    fireEvent.click(within(dialog).getByRole("button", { name: "Batch reports" }));
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(compareDialog()).not.toBeInTheDocument();
    expect(opener).toHaveFocus();

    fireEvent.click(opener);
    dialog = compareDialog()!;
    expect(within(dialog).getByRole("button", { name: "Completed runs" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(within(dialog).getByRole("heading", { name: "Compare runs or batch reports" }));
    expect(compareDialog()).toBeInTheDocument();
    fireEvent.click(within(dialog.querySelector(".phase75-modal-header") as HTMLElement).getByRole("button", { name: "Close" }));
    expect(compareDialog()).not.toBeInTheDocument();

    fireEvent.click(opener);
    fireEvent.click(document.querySelector(".phase75-modal-backdrop")!);
    expect(compareDialog()).not.toBeInTheDocument();

    expect(statRow("Region")).toBe(region);
    expect(document.querySelector(".phase75-playhead-label")).toHaveTextContent("T60");
    expect(onSeek).not.toHaveBeenCalled();
    expect(onSurfaceChange).not.toHaveBeenCalled();
  });

  it("opens from the batch report health on batch reports, and from the header on completed runs", () => {
    render(shell({ surface: "batch", bundle: null, currentTurn: 1 }));
    fireEvent.click(within(inspector()).getByRole("button", { name: "Open Overlay" }));
    expect(within(compareDialog()!).getByRole("button", { name: "Batch reports" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(compareDialog()!, { key: "Escape" });
    expect(compareDialog()).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Compare saved runs" }));
    expect(within(compareDialog()!).getByRole("button", { name: "Completed runs" })).toHaveAttribute("aria-pressed", "true");
  });

  it("hides a paused session's intervention dialog while open and shows it again when cancelled", async () => {
    const send = vi.fn();
    const civs = systems.world_state.civilizations.slice(0, 2).map((civ) => civ.name);
    const context = { turn: 60, reason: "interval", civs, valid_commands: ["continue", "inject", "set", "quit"],
      injectable_events: ["plague"], settable_stats: ["stability"] };
    render(shell({ isLive: true, connected: true, serverState: "running", currentTurn: 60, livePaused: true,
      livePauseContext: context, liveSendCommand: send }));
    expect(await screen.findByRole("dialog", { name: "Paused simulation at turn 60" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Compare saved runs" }));
    expect(screen.queryByRole("dialog", { name: "Paused simulation at turn 60" })).not.toBeInTheDocument();
    fireEvent.keyDown(compareDialog()!, { key: "Escape" });
    expect(compareDialog()).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Paused simulation at turn 60" })).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });
});

describe("rewinding through the timeline", () => {
  it("seeks by keyboard within the run and moves the playhead, header and map caption on a rewind", () => {
    const onSeek = vi.fn();
    const view = render(shell({ currentTurn: 60, onSeek }));
    expect(slider()).toHaveAttribute("aria-valuemin", "1");
    expect(slider()).toHaveAttribute("aria-valuemax", String(total));
    expect(slider()).toHaveAttribute("aria-valuenow", "60");
    expect(slider()).toHaveAttribute("tabindex", "0");
    for (const [key, turn] of [["ArrowLeft", 59], ["ArrowRight", 61], ["PageUp", 70], ["PageDown", 50],
      ["Home", 1], ["End", total]] as const) {
      fireEvent.keyDown(slider(), { key });
      expect(onSeek).toHaveBeenLastCalledWith(turn);
    }
    onSeek.mockClear();
    fireEvent.keyDown(slider(), { key: "Enter" });
    expect(onSeek).not.toHaveBeenCalled();

    view.rerender(shell({ currentTurn: 1, onSeek }));
    fireEvent.keyDown(slider(), { key: "ArrowLeft" });
    expect(onSeek).toHaveBeenLastCalledWith(1);
    fireEvent.keyDown(slider(), { key: "PageDown" });
    expect(onSeek).toHaveBeenLastCalledWith(1);
    view.rerender(shell({ currentTurn: total, onSeek }));
    fireEvent.keyDown(slider(), { key: "PageUp" });
    expect(onSeek).toHaveBeenLastCalledWith(total);

    view.rerender(shell({ currentTurn: 30, onSeek }));
    const playhead = document.querySelector(".phase75-playhead") as HTMLElement;
    expect(playhead).toHaveTextContent("T30");
    expect(playhead.style.left).toBe(`${(29 / (total - 1)) * 100}%`);
    expect(slider()).toHaveAttribute("aria-valuenow", "30");
    expect(screen.getByText(`30 / ${total}`)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: `Turn 30 of ${total}` })).toBeInTheDocument();
  });

  it("seeks the turn under a click on the track, clamped to the run", () => {
    const onSeek = vi.fn();
    render(shell({ currentTurn: 60, onSeek }));
    vi.spyOn(slider(), "getBoundingClientRect").mockReturnValue(
      { left: 100, width: 400, top: 0, height: 20, right: 500, bottom: 20, x: 100, y: 0, toJSON: () => ({}) } as DOMRect);
    for (const [clientX, turn] of [[300, 61], [200, 31], [0, 1], [900, total]] as const) {
      fireEvent.click(slider(), { clientX });
      expect(onSeek).toHaveBeenLastCalledWith(turn);
    }
  });

  it("bounds a live timeline by its latest received turn", () => {
    const onSeek = vi.fn();
    const onReturnToLive = vi.fn();
    const liveTimeline = { followMode: false, inspectionLocked: true, newTurns: 3, latestTurn: 80,
      onReturnToLive, onLock: vi.fn() };
    render(shell({ isLive: true, connected: true, serverState: "running", currentTurn: 75, liveTimeline, onSeek }));
    expect(slider()).toHaveAttribute("aria-valuemax", "80");
    fireEvent.keyDown(slider(), { key: "End" });
    expect(onSeek).toHaveBeenLastCalledWith(80);
    fireEvent.keyDown(slider(), { key: "PageUp" });
    expect(onSeek).toHaveBeenLastCalledWith(80);
    const controls = screen.getByLabelText("Live timeline controls");
    expect(controls).toHaveTextContent("Latest advanced by 3 turns since lock");
    fireEvent.click(within(controls).getByRole("button", { name: "Return to live" }));
    expect(onReturnToLive).toHaveBeenCalledTimes(1);
  });

  it("wires play, pause and speed, and leaves the timeline inert without a world", () => {
    const onPlay = vi.fn();
    const onPause = vi.fn();
    const onSetSpeed = vi.fn();
    const onSeek = vi.fn();
    const handlers = { onPlay, onPause, onSetSpeed, onSeek };
    const view = render(shell(handlers));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(onPlay).toHaveBeenCalledTimes(1);
    const speed = screen.getByRole("combobox", { name: "Playback speed" }) as HTMLSelectElement;
    expect([...speed.options].map((option) => option.textContent)).toEqual(["1x", "2x", "5x", "10x"]);
    fireEvent.change(speed, { target: { value: "5" } });
    expect(onSetSpeed).toHaveBeenCalledExactlyOnceWith(5);
    view.rerender(shell({ ...handlers, playing: true, speed: 5 }));
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(onPause).toHaveBeenCalledTimes(1);

    view.rerender(shell({ ...handlers, surface: "setup", bundle: null, currentTurn: 1 }));
    expect(screen.getByRole("button", { name: "Play" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Playback speed" })).toBeDisabled();
    expect(slider()).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(slider(), { key: "End" });
    fireEvent.click(slider(), { clientX: 10 });
    expect(onSeek).not.toHaveBeenCalled();
    expect(screen.getByText("Your timeline appears when a run is loaded.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open a saved run or start a new world" })).toBeInTheDocument();
    expect(document.querySelector(".phase75-playhead")).toBeNull();
  });

  it("keeps the whole-run marks while the playhead rewinds", () => {
    // Ten named moments (the fixture has none): the track marks the eight most important, whatever the turn.
    const named: Bundle = { ...systems, named_events: Array.from({ length: 10 }, (_, index) => ({
      name: `Moment ${index}`, event_type: "war", turn: 10 + index * 10, actors: [], region: null,
      description: "", importance: (index * 7) % 10,
    })) };
    const view = render(shell({ bundle: named }));
    const marks = () => ({
      eras: [...document.querySelectorAll<HTMLElement>(".phase75-era-band")].map((band) => `${band.textContent}@${band.style.left}`),
      spans: document.querySelectorAll(".phase75-narrated-span").length,
      markers: [...document.querySelectorAll(".phase75-track-marker")].map((marker) => marker.getAttribute("title")),
    });
    const atEnd = marks();
    expect(atEnd.eras.length).toBeGreaterThan(0);
    expect(atEnd.markers).toEqual(["Moment 7", "Moment 4", "Moment 1", "Moment 8", "Moment 5", "Moment 2", "Moment 9",
      "Moment 6"]);
    view.rerender(shell({ bundle: named, currentTurn: 5 }));
    expect(marks()).toEqual(atEnd);
    view.unmount();
    render(shell({ bundle: named, currentTurn: 5 }));
    expect(marks()).toEqual(atEnd);
  });
});

describe("one selection across the map, list, chips and inspector", () => {
  it("selects from map nodes, the region list, the keyboard and the civilization chips", () => {
    const [first, second] = systems.world_state.regions.map((region) => region.name);
    render(shell());
    fireEvent.click(regionNode(first));
    expect(regionNode(first)).toHaveClass("selected");
    expect(regionList()).toHaveValue(first);
    expect(statRow("Region")).toBe(first);
    expect(inspector()).toHaveTextContent(`Region selected: ${first}.`);

    fireEvent.change(regionList(), { target: { value: second } });
    expect(regionNode(second)).toHaveClass("selected");
    expect(regionNode(first)).not.toHaveClass("selected");
    expect(statRow("Region")).toBe(second);

    fireEvent.keyDown(regionNode(first), { key: "Enter" });
    expect(statRow("Region")).toBe(first);
    fireEvent.keyDown(regionNode(second), { key: " " });
    expect(statRow("Region")).toBe(second);
    fireEvent.keyDown(regionNode(first), { key: "a" });
    expect(statRow("Region")).toBe(second);

    const chip = document.querySelector(".phase75-civ-chip") as HTMLElement;
    fireEvent.click(chip);
    expect(chip).toHaveClass("active");
    expect(statRow("Civilization")).toBe(chip.textContent);
    expect(regionList()).toHaveValue("");
    expect(inspector()).toHaveTextContent(`Focus selected: ${chip.textContent}.`);
    expect(document.querySelector(".phase75-region-node.selected")).toBeNull();
  });

  it("moves focus between the map and the selection details", () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      render(shell());
      fireEvent.click(screen.getByRole("button", { name: "View selection details" }));
      expect(document.activeElement).toBe(screen.getByRole("complementary", { name: "Selection details" }));
      expect(scrollIntoView).toHaveBeenLastCalledWith({ block: "start" });
      fireEvent.click(screen.getByRole("button", { name: "Back to map" }));
      expect(document.activeElement).toBe(screen.getByRole("region", { name: "World map investigation" }));
      expect(scrollIntoView).toHaveBeenCalledTimes(2);
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("keeps the selection across surfaces and rewinds, and a collapsed section across selections", () => {
    const [first, second] = systems.world_state.regions.map((region) => region.name);
    const view = render(shell());
    fireEvent.click(regionNode(first));
    for (const surface of ["trade", "campaign", "character", "overview"] as const) {
      view.rerender(shell({ surface }));
      expect(statRow("Region")).toBe(first);
    }
    view.rerender(shell({ surface: "campaign" }));
    expect(screen.getByRole("radio", { name: "Wars" })).toHaveAttribute("aria-checked", "true");
    view.rerender(shell());
    expect(screen.getByRole("radio", { name: "Control" })).toHaveAttribute("aria-checked", "true");
    view.rerender(shell({ currentTurn: 10 }));
    expect(statRow("Region")).toBe(first);
    expect(regionList()).toHaveValue(first);

    const toggle = within(inspector()).getByRole("button", { name: /^Selection/ });
    expect(toggle).toHaveTextContent("−");
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent("+");
    expect(statRow("Region")).toBe("");
    fireEvent.click(regionNode(second));
    expect(statRow("Region")).toBe("");
    fireEvent.click(toggle);
    expect(statRow("Region")).toBe(second);
  });
});
