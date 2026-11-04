import { describe, expect, it } from "vitest";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { availableMapLayers, buildMapLayer, POPULATION_BANDS } from "../mapLayers";
import type { Bundle } from "../../types";

const population = (bundle: Bundle, index: number) => buildMapLayer("population", { bundle, snapshot: bundle.history[index] ?? null, famine: [], technique: null })!;

describe("population and territory map observations", () => {
  it("uses stable region-indexed completed model counts, with native counts separately labelled", () => {
    const bundle = regionalFixture();
    bundle.history[0].regional_population!.counts = [0, 100];
    const view = population(bundle, 0);
    expect(availableMapLayers(bundle)).toContain("population");
    expect(view.fills.get("A")).toBe(POPULATION_BANDS[0].color);
    expect(view.fills.get("B")).toBe(POPULATION_BANDS[3].color);
    expect(view.titles.get("A")).toContain("model population 0");
    expect(view.titles.get("A")).toContain("native alive 5 (separate measure)");
    expect(view.note).toContain("model population units");
  });
  it("keeps old, missing and invalid records unknown without final-world fallthrough", () => {
    const bundle = regionalFixture();
    delete bundle.history[0].regional_population;
    bundle.history[1].regional_population!.completed_turn = 99;
    for (const index of [0, 1, 99]) {
      expect(population(bundle, index).fills.size).toBe(0);
      expect(population(bundle, index).note).toContain("Unknown is not zero");
    }
    delete bundle.history[2].regional_population;
    expect(availableMapLayers(bundle)).not.toContain("population");
  });
  it("uses fixed bins unaffected by future values and avoids ambiguous name fills", () => {
    const bundle = regionalFixture();
    const before = population(bundle, 0);
    bundle.history[2].regional_population!.counts = [999999, 999999];
    expect(population(bundle, 0).fills).toEqual(before.fills);
    expect(population(bundle, 0).legend).toEqual(before.legend);
    bundle.world_state.regions[1].name = "A";
    expect(population(bundle, 0).fills.size).toBe(0);
    expect(population(bundle, 0).titles.get("A")).toContain("ambiguous");
  });
  it("reuses the existing layer view for exact global and civilization-focused ownership changes", () => {
    const bundle = regionalFixture();
    bundle.history[1].region_control.A = "B";
    const input = { bundle, snapshot: bundle.history[1], famine: [], technique: null };
    expect(buildMapLayer("territory", input)!.titles.get("A")).toContain("Transferred · A → B");
    expect(buildMapLayer("territory", { ...input, territoryCivilizationIndex: 0 })!.titles.get("A")).toContain("Lost");
    const invalid = buildMapLayer("territory", { ...input, territoryFromTurn: 3 })!;
    expect(invalid.note).toContain("No ownership change is inferred");
    expect(invalid.legend.find((row) => row.label.startsWith("Unknown"))?.label).toBe("Unknown (2)");
  });
  it("describes missing existing-layer observations as unknown rather than observed absence", () => {
    const bundle = regionalFixture();
    const input = { bundle, snapshot: bundle.history[1], famine: [], technique: "writing" };
    expect(buildMapLayer("epidemics", input)!.titles.get("A")).toContain("unknown");
    expect(buildMapLayer("techniques", input)!.titles.get("A")).toContain("unknown");
    expect(buildMapLayer("migration", input)!.note).toContain("Migration coverage: 0/2");
    bundle.history[1].migration = [];
    expect(buildMapLayer("migration", input)!.note).toContain("Migration coverage: 1/2");
  });
});
