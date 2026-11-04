import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../../types";
import { crisesAtSnapshot, famineSpans, FAMINE_COLOR } from "../../../lib/food";
import { AppShell, type AppSurface } from "../AppShell";
import { preloadPanels } from "../lazyPanels";
import { NO_DATA_OPACITY } from "../../../lib/mapLayers";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.tsx).
beforeAll(() => preloadPanels());
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
  it("does not carry prior ownership across a missing turn or confuse unknown with uncontrolled", () => {
    const bundle = structuredClone(sample);
    const region = bundle.world_state.regions[0].name;
    bundle.history = bundle.history.filter((row) => row.turn !== 2);
    const mounted = renderShell(bundle, 2);
    expect(node(region)).toHaveAttribute("fill-opacity", String(NO_DATA_OPACITY));
    expect(node(region).querySelector("title")).toHaveTextContent("Ownership unknown at T2");
    mounted.unmount();
    bundle.history[0].region_control[region] = null;
    renderShell(bundle, bundle.history[0].turn);
    expect(node(region)).not.toHaveAttribute("fill-opacity");
    expect(node(region).querySelector("title")).toHaveTextContent("Uncontrolled");
  });
  it("offers territory history for legacy bundles with recorded ownership", () => {
    renderShell(sample, sample.history[sample.history.length - 1].turn);
    expect(within(screen.getByRole("radiogroup", { name: "Map layer" })).getAllByRole("radio").map((row) => row.textContent)).toEqual(["Control", "Territory changes"]);
    expect(screen.queryByLabelText("Map layer legend")).not.toBeInTheDocument();
  });

  it("recolours regions by famine on the food layer and explains it in a legend", () => {
    const spans = famineSpans(systems.events_timeline);
    const snapshot = systems.history.find((entry) => crisesAtSnapshot(spans, entry.turn).length > 0)!;
    const span = crisesAtSnapshot(spans, snapshot.turn)[0];
    renderShell(systems, snapshot.turn);
    const layers = screen.getByRole("radiogroup", { name: "Map layer" });
    expect(within(layers).getAllByRole("radio").map((radio) => radio.textContent)).toEqual([
      "Control", "Territory changes", "Food", "Epidemics", "Wars", "Migration", "Techniques", "Sea",
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
