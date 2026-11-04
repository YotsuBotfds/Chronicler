/**
 * Characterization of the shell across worlds and loads: which choices are
 * keyed to the loaded world (history focus, search evidence, the history
 * inspector's own state), which carry over (map layer, overlays, inspector
 * sections, a selection the next world also records), and what an
 * interrupted or failed load leaves on screen. The shell owns this state;
 * these cases pin it before its presentation components are split out.
 */
import type { ComponentProps } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../../types";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.ts).
beforeAll(() => preloadPanels());
afterEach(cleanup);

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const identityA = { name: "world.json", byteLength: 1, sha256: "a".repeat(64) };
const identityB = { name: "world.json", byteLength: 1, sha256: "b".repeat(64) };

function shell(overrides: Partial<ComponentProps<typeof AppShell>> = {}) {
  const props: ComponentProps<typeof AppShell> = {
    surface: "overview", onSurfaceChange: vi.fn(), bundle: systems, bundleLoading: false, error: null,
    isLive: false, connected: false, serverState: "completed", currentTurn: 120, playing: false, speed: 1,
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
const sectionToggle = (title: string) => within(inspector()).getByRole("button", { name: new RegExp(`^${title}`) });

describe("switching worlds", () => {
  it("keeps a selection the next world records, and otherwise selects its leading civilization", () => {
    const region = systems.world_state.regions[0].name;
    const view = render(shell());
    fireEvent.click(regionNode(region));
    expect(statRow("Region")).toBe(region);

    // A re-export of the same world (another generated_at) is another world key with the same names.
    const reexport: Bundle = { ...systems, metadata: { ...systems.metadata, generated_at: "2026-11-04T00:00:00+00:00" } };
    view.rerender(shell({ bundle: reexport }));
    expect(statRow("Region")).toBe(region);
    expect(regionList()).toHaveValue(region);

    // A world without that region: its leading civilization (the first chip) is selected.
    view.rerender(shell({ bundle: sample, currentTurn: 10 }));
    const chips = document.querySelectorAll(".phase75-civ-chip");
    expect(chips.length).toBeGreaterThan(0);
    const lead = chips[0].textContent ?? "";
    expect(chips[0]).toHaveClass("active");
    expect(statRow("Civilization")).toBe(lead);
    expect(inspector()).toHaveTextContent(`Focus selected: ${lead}.`);
    expect(regionList()).toHaveValue("");
    expect(document.querySelectorAll(".phase75-region-node")).toHaveLength(sample.world_state.regions.length);
    expect(screen.queryByRole("region", { name: "Simulation systems" })).not.toBeInTheDocument();
  });

  it("returns history focus and search evidence with their own world only, and remounts the history inspector", async () => {
    const region = systems.world_state.regions[2].name;
    const view = render(shell({ artifactIdentity: identityA }));
    fireEvent.click(screen.getByText("Search recorded entities"));
    fireEvent.change(await screen.findByLabelText("Name or dated alias"), { target: { value: region } });
    fireEvent.click(await screen.findByRole("button", { name: `Inspect: ${region}` }));
    expect(screen.getByText(`Selected search evidence: ${region}`)).toBeInTheDocument();
    const history = await screen.findByRole("combobox", { name: "Region" });
    expect(history).toHaveValue(region);
    const metric = screen.getByRole("combobox", { name: "Metric" }) as HTMLSelectElement;
    const initialMetric = metric.value;
    const chosenMetric = [...metric.options].map((option) => option.value).find((value) => value !== initialMetric)!;
    fireEvent.change(metric, { target: { value: chosenMetric } });

    // Pinning an event keeps the history inspector on the focused region.
    fireEvent.click(screen.getByRole("button", { name: "Event Log" }));
    fireEvent.click(document.querySelector(".phase75-event-row")!);
    expect(statRow("Event")).not.toBe("");
    expect(screen.getByRole("combobox", { name: "Region" })).toHaveValue(region);

    // The same records under another identity: another world, so neither choice applies.
    view.rerender(shell({ artifactIdentity: identityB }));
    expect(statRow("Event")).not.toBe("");
    expect(screen.queryByText(/^Selected search evidence/)).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Region" })).not.toHaveValue(region);
    expect(screen.getByRole("combobox", { name: "Metric" })).toHaveValue(initialMetric);

    // Back to the first world: its focus and evidence return; the inspector starts afresh.
    view.rerender(shell({ artifactIdentity: identityA }));
    expect(screen.getByText(`Selected search evidence: ${region}`)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Region" })).toHaveValue(region);
    expect(screen.getByRole("combobox", { name: "Metric" })).toHaveValue(initialMetric);
  });

  it("carries the map layer, overlays and inspector sections across worlds, showing a layer only where it is recorded", () => {
    const view = render(shell());
    fireEvent.click(screen.getByRole("radio", { name: "Food" }));
    fireEvent.click(screen.getByRole("button", { name: "settlements" }));
    fireEvent.click(sectionToggle("Metrics"));
    expect(sectionToggle("Metrics")).toHaveTextContent("+");
    expect(document.querySelectorAll(".phase75-region-label")).toHaveLength(0);

    view.rerender(shell({ bundle: sample, currentTurn: 10 }));
    const layers = screen.getByRole("radiogroup", { name: "Map layer" });
    expect(within(layers).getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["Control", "Territory changes"]);
    expect(within(layers).getByRole("radio", { name: "Control" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("button", { name: "settlements" })).not.toHaveClass("active");
    expect(document.querySelectorAll(".phase75-region-label")).toHaveLength(0);
    expect(sectionToggle("Metrics")).toHaveTextContent("+");

    view.rerender(shell());
    expect(screen.getByRole("radio", { name: "Food" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("Map layer legend")).toHaveTextContent("famine");
  });
});

describe("loading a world", () => {
  it("keeps the loaded world, its selection, history panel and turn through an interrupted load", async () => {
    const onSeek = vi.fn();
    const onSurfaceChange = vi.fn();
    const region = systems.world_state.regions[2].name;
    const view = render(shell({ currentTurn: 60, onSeek, onSurfaceChange }));
    fireEvent.click(regionNode(region));
    fireEvent.click(screen.getByText("Compare turns and inspect history"));
    expect(await screen.findByRole("combobox", { name: "Region" })).toHaveValue(region);

    view.rerender(shell({ currentTurn: 60, onSeek, onSurfaceChange, bundleLoading: true }));
    expect(screen.getByText("Reading saved world…")).toHaveAttribute("role", "status");
    expect(document.querySelector(".phase75-map-loading")).toHaveTextContent("Loading bundle...");
    expect(document.querySelectorAll(".phase75-region-node")).toHaveLength(systems.world_state.regions.length);
    expect(statRow("Region")).toBe(region);
    expect(document.querySelector(".phase75-playhead-label")).toHaveTextContent("T60");

    view.rerender(shell({ currentTurn: 60, onSeek, onSurfaceChange, error: "Could not read bundle: decode interrupted" }));
    const banner = document.querySelector(".phase75-error-banner") as HTMLElement;
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent("Could not read bundle: decode interrupted");
    expect(banner).toHaveTextContent("The loaded world is still available. Choose another file with Open Existing.");
    expect(screen.queryByText("Reading saved world…")).not.toBeInTheDocument();
    expect(document.querySelector(".phase75-map-loading")).toBeNull();
    expect(statRow("Region")).toBe(region);
    expect(regionList()).toHaveValue(region);
    expect(screen.getByRole("combobox", { name: "Region" })).toHaveValue(region);
    expect(document.querySelector(".phase75-playhead-label")).toHaveTextContent("T60");
    expect(onSeek).not.toHaveBeenCalled();
    expect(onSurfaceChange).not.toHaveBeenCalled();

    // The next successful load replaces the message and the world.
    view.rerender(shell({ bundle: sample, currentTurn: 10, onSeek, onSurfaceChange }));
    expect(document.querySelector(".phase75-error-banner")).toBeNull();
    expect(document.querySelectorAll(".phase75-region-node")).toHaveLength(sample.world_state.regions.length);
  });

  it("without a world, shows the load's statuses and then the error alone", () => {
    const view = render(shell({ surface: "setup", bundle: null, currentTurn: 1, bundleLoading: true }));
    expect(screen.getByText("Reading saved world…")).toBeInTheDocument();
    expect(document.querySelector(".phase75-map-loading")).toHaveTextContent("Loading bundle...");
    view.rerender(shell({ surface: "setup", bundle: null, currentTurn: 1, error: "Invalid JSON in bad.json" }));
    const banner = document.querySelector(".phase75-error-banner") as HTMLElement;
    expect(banner.textContent).toBe("Invalid JSON in bad.json");
    expect(screen.queryByText("Reading saved world…")).not.toBeInTheDocument();
    expect(within(inspector()).getByRole("heading", { level: 3 })).toHaveTextContent("Launch details");
    expect(screen.getByRole("slider", { name: "Historical turn" })).toHaveAttribute("tabindex", "-1");
  });

  it("passes the chosen file on and clears the input so the same file can be chosen again", () => {
    const onOpenBundleFile = vi.fn();
    render(shell({ onOpenBundleFile }));
    const input = screen.getByLabelText("Open saved world file") as HTMLInputElement;
    const click = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: "Open Existing" }));
    expect(click).toHaveBeenCalledTimes(1);
    // jsdom keeps no chosen file of its own, so the input's value is observed directly.
    const assigned: string[] = [];
    Object.defineProperty(input, "value", { configurable: true, get: () => "C:\\fakepath\\world.json",
      set: (next: string) => { assigned.push(next); } });
    const file = new File(["{}"], "world.json", { type: "application/json" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onOpenBundleFile).toHaveBeenCalledExactlyOnceWith(file);
    expect(assigned).toEqual([""]);
  });
});
