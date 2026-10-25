import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../../types";
import { famineSpans, FAMINE_COLOR } from "../../../lib/food";
import { AppShell, type AppSurface } from "../AppShell";

afterEach(cleanup);

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;

function renderShell(bundle: Bundle, currentTurn: number, surface: AppSurface = "overview") {
  return render(
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

function node(name: string): SVGCircleElement {
  // Layer nodes carry a hover title that starts with the region's name.
  const found = [...document.querySelectorAll<SVGCircleElement>(".phase75-region-node")].find((circle) => {
    const title = circle.querySelector("title")?.textContent ?? "";
    return title === name || title.startsWith(`${name} · `);
  });
  if (!found) {
    throw new Error(`no node for ${name}`);
  }
  return found;
}

describe("AppShell map layers", () => {
  it("offers no layer bar for a bundle without system data", () => {
    renderShell(sample, sample.history[sample.history.length - 1].turn);
    expect(screen.queryByRole("radiogroup", { name: "Map layer" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Map layer legend")).not.toBeInTheDocument();
  });

  it("recolours regions by famine on the food layer and explains it in a legend", () => {
    const spans = famineSpans(systems.events_timeline);
    const snapshot = systems.history.find((entry) =>
      spans.some((span) => span.start <= entry.turn && (span.end === null || span.end > entry.turn)))!;
    const span = spans.find((entry) => entry.start <= snapshot.turn && (entry.end === null || entry.end > snapshot.turn))!;
    renderShell(systems, snapshot.turn);
    const layers = screen.getByRole("radiogroup", { name: "Map layer" });
    expect(within(layers).getAllByRole("radio").map((radio) => radio.textContent)).toEqual([
      "Control", "Food", "Epidemics", "Wars", "Migration", "Techniques", "Sea",
    ]);
    expect(within(layers).getByRole("radio", { name: "Control" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(layers).getByRole("radio", { name: "Food" }));
    expect(node(span.region)).toHaveAttribute("fill", FAMINE_COLOR);
    expect(node(span.region).querySelector("title")?.textContent).toContain(`famine since T${span.start}`);
    expect(screen.getByLabelText("Map layer legend")).toHaveTextContent("famine");
    fireEvent.click(within(layers).getByRole("radio", { name: "Control" }));
    expect(screen.queryByLabelText("Map layer legend")).not.toBeInTheDocument();
  });

  it("opens the campaign surface on the war layer with army markers", () => {
    const snapshot = systems.history.find((entry) => (entry.campaign?.armies.length ?? 0) > 0)!;
    renderShell(systems, snapshot.turn, "campaign");
    expect(screen.getByRole("radio", { name: "Wars" })).toHaveAttribute("aria-checked", "true");
    expect(document.querySelectorAll(".phase75-layer-marker").length).toBeGreaterThanOrEqual(snapshot.campaign!.armies.length);
  });

  it("draws sea zones with spokes to their ports and picks a technique to shade", () => {
    renderShell(systems, 101);
    fireEvent.click(screen.getByRole("radio", { name: "Sea" }));
    expect(document.querySelectorAll(".phase75-sea-hub")).toHaveLength(systems.history.find((entry) => entry.turn === 101)!
      .maritime!.zones.length);
    expect(document.querySelectorAll(".phase75-sea-spoke").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("radio", { name: "Techniques" }));
    const select = screen.getByRole("combobox", { name: "Technique" });
    fireEvent.change(select, { target: { value: "writing" } });
    expect(screen.getByLabelText("Map layer legend")).toHaveTextContent("Writing");
  });

  it("draws migration flows as arrows", () => {
    renderShell(systems, 120);
    fireEvent.click(screen.getByRole("radio", { name: "Migration" }));
    const flows = document.querySelectorAll(".phase75-layer-flow");
    expect(flows.length).toBeGreaterThan(0);
    expect(flows[0].getAttribute("marker-end")).toMatch(/^url\(#layer-arrow-migration-/);
  });
});
