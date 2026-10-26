import { describe, expect, it } from "vitest";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, TurnSnapshot } from "../../types";
import { crisesAtSnapshot, DEARTH_COLOR, famineSpans, FAMINE_COLOR } from "../food";
import {
  availableMapLayers, buildMapLayer, defaultTechnique, practisedTechniques, type MapLayerKey,
} from "../mapLayers";

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const famine = famineSpans(systems.events_timeline);
const names = systems.world_state.regions.map((region) => region.name);

function at(turn: number): TurnSnapshot {
  const snapshot = systems.history.find((entry) => entry.turn === turn);
  if (!snapshot) {
    throw new Error(`fixture has no turn ${turn}`);
  }
  return snapshot;
}

function layer(key: MapLayerKey, snapshot: TurnSnapshot, technique: string | null = null) {
  const view = buildMapLayer(key, { bundle: systems, snapshot, famine, technique });
  if (!view) {
    throw new Error(`no view for ${key}`);
  }
  return view;
}

describe("map layers", () => {
  it("offers only the layers a bundle has data for", () => {
    expect(availableMapLayers(systems)).toEqual(["control", "food", "epidemics", "wars", "migration", "techniques", "sea"]);
    expect(availableMapLayers(sample)).toEqual(["control"]);
    expect(availableMapLayers(null)).toEqual(["control"]);
    expect(buildMapLayer("control", { bundle: systems, snapshot: at(120), famine, technique: null })).toBeNull();
  });

  it("colours famine regions and draws relief convoys on the food layer", () => {
    const snapshot = systems.history.find((entry) => (entry.food?.aid.length ?? 0) > 0)!;
    const view = layer("food", snapshot);
    const [donor, recipient] = snapshot.food!.aid[0];
    expect(view.flows[0]).toMatchObject({ from: names[donor], to: names[recipient] });
    const running = crisesAtSnapshot(famine, snapshot.turn);
    for (const span of running) {
      expect(view.fills.get(span.region)).toBe(FAMINE_COLOR);
      expect(view.titles.get(span.region)).toContain(`famine since T${span.start}`);
    }
    expect(view.legend.map((item) => item.label)).toContain("relief convoy");
  });

  it("tells dearth from famine on the food layer", () => {
    const snapshot = systems.history.find((entry) => (entry.food?.aid.length ?? 0) > 0)!;
    const observed = names.filter((_, index) => snapshot.food!.sufficiency[index] != null);
    const [hungry, lean] = [observed[0], observed[1]];
    const spans = [
      { region: hungry, start: 0, end: null, reports: 3, kind: "famine" as const },
      { region: lean, start: 0, end: null, reports: 1, kind: "dearth" as const },
    ];
    const withFood = buildMapLayer("food", { bundle: systems, snapshot, famine: spans, technique: null })!;
    expect(withFood.fills.get(hungry)).toBe(FAMINE_COLOR);
    expect(withFood.titles.get(lean)).toContain("dearth since T0");
    // With the food field a dearth keeps the region's shortage shading.
    expect(withFood.fills.get(lean)).not.toBe(DEARTH_COLOR);
    const bare = { ...snapshot, food: undefined };
    const noFood = buildMapLayer("food", { bundle: systems, snapshot: bare, famine: spans, technique: null })!;
    expect(noFood.fills.get(lean)).toBe(DEARTH_COLOR);
    expect(noFood.fills.get(hungry)).toBe(FAMINE_COLOR);
    expect(noFood.legend.map((item) => item.label)).toEqual(["famine", "dearth", "not observed"]);
  });

  it("fills each outbreak region with its strongest pathogen", () => {
    const snapshot = systems.history.find((entry) => (entry.epidemics?.active.length ?? 0) > 1)!;
    const view = layer("epidemics", snapshot);
    const regions = new Set(snapshot.epidemics!.active.map((outbreak) => outbreak.region));
    expect(view.fills.size).toBe(regions.size);
    for (const opacity of view.opacity.values()) {
      expect(opacity).toBeGreaterThanOrEqual(0.35);
      expect(opacity).toBeLessThanOrEqual(1);
    }
  });

  it("places armies, their marches and occupations on the war layer", () => {
    const snapshot = systems.history.find((entry) => (entry.campaign?.armies.length ?? 0) > 0)!;
    const view = layer("wars", snapshot);
    expect(view.dimControl).toBe(true);
    expect(view.markers.filter((marker) => marker.shape === "dot")).toHaveLength(snapshot.campaign!.armies.length);
    const marching = snapshot.campaign!.armies.filter((army) => army.objective && army.objective !== army.region);
    expect(view.flows).toHaveLength(marching.length);
    expect(view.flows.every((flow) => flow.dashed)).toBe(true);
    const occupied = systems.history.find((entry) => (entry.campaign?.occupations.length ?? 0) > 0)!;
    expect(layer("wars", occupied).outlines.size).toBe(occupied.campaign!.occupations.length);
  });

  it("draws the largest agent moves of the trailing window on the migration layer", () => {
    const view = layer("migration", at(120));
    expect(view.flows.length).toBeGreaterThan(0);
    const widths = view.flows.map((flow) => flow.width);
    expect([...widths].sort((left, right) => right - left)).toEqual(widths);
  });

  it("names what moved the mass departures of the window when the bundle records it", () => {
    const wave = (turn: number, region: string, driver?: string) => ({
      turn, event_type: "mass_migration", region, actors: [], description: "", consequences: [], importance: 5,
      ...(driver ? { driver } : {}),
    });
    const bundle = {
      ...systems,
      events_timeline: [
        ...systems.events_timeline.filter((event) => event.event_type !== "mass_migration"),
        wave(118, names[0], "frontier"), wave(119, names[1], "famine_memory"), wave(119, names[2], "frontier"),
        wave(117, names[3]), wave(100, names[4], "chain"),
      ],
    };
    const view = buildMapLayer("migration", { bundle, snapshot: at(120), famine, technique: null })!;
    expect(view.note).toContain("Mass departures: 2 settling new land, 1 fleeing hunger.");
    expect(view.titles.get(names[1])).toContain("mass departure T119: fleeing hunger");
    expect(view.titles.get(names[3])).toContain("mass departure T117");
    expect(view.titles.get(names[3])).not.toContain(":");
    expect(view.titles.get(names[4])).not.toContain("mass departure");  // outside the window
  });

  it("shades regions by the chosen technique and picks a spreading one by default", () => {
    const options = practisedTechniques(systems.history);
    expect(options).toContain("writing");
    const chosen = defaultTechnique(at(120), options);
    expect(chosen).not.toBeNull();
    const view = layer("techniques", at(120), "writing");
    const practising = Object.entries(at(120).techniques!.regions!).filter(([, practice]) => practice.writing !== undefined);
    expect(view.fills.size).toBe(practising.length);
    expect(view.note).toContain("Writing");
  });

  it("links each sea zone to its ports, at its procedural position", () => {
    const snapshot = at(101);
    const view = layer("sea", snapshot);
    expect(view.hubs).toHaveLength(snapshot.maritime!.zones.length);
    const morendor = view.hubs.find((hub) => hub.id === "the Morendor Bight")!;
    expect(morendor.x).not.toBeNull();
    expect(morendor.ports.length).toBeGreaterThan(0);
    const blockaded = new Set(snapshot.maritime!.blockades.map((blockade) => blockade.zone));
    expect(view.hubs.filter((hub) => hub.ring !== null).map((hub) => hub.id).sort()).toEqual([...blockaded].sort());
  });
});
