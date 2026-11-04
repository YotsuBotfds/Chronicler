import { describe, expect, it } from "vitest";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import type { Bundle, RegionalPopulationSnapshot } from "../../types";
import { populationWeightedFood, readRegionalPopulation } from "../regionalPopulation";
import { readEntityTurn } from "../historyComparison";
import { inspectRegionHistory, regionMetrics } from "../regionHistory";
import { alignCompletedRuns, completedComparisonSummary } from "../completedRunComparison";
import { classifyParsedBundlePayload } from "../bundleLoader";
import { validateBundleStructure, validateViewableBundle } from "../bundleValidation";
import { savedWorldSummary } from "../savedWorldSummary";

const metric = (bundle: Bundle, kind: "region" | "civilization", name: string, id: string) =>
  readEntityTurn(bundle, { kind, name }, 1).metrics.find((row) => row.id === id);

describe("regional model/native observations and phase2 food weighting", () => {
  it("keeps separate completed model, native, civilization and final-world populations", () => {
    const bundle = regionalFixture();
    expect(metric(bundle, "region", "A", "population")).toMatchObject({ value: 100, label: "Regional model population" });
    expect(metric(bundle, "region", "A", "nativePopulation")?.value).toBe(5);
    expect(metric(bundle, "civilization", "A", "population")?.value).toBe(20);
    const population = regionMetrics(bundle).find((row) => row.id === "population")!;
    expect(inspectRegionHistory(bundle, "A", population, 1, 3).rows.map((row) => row.value)).toEqual([100, 100, 100]);
    const points = alignCompletedRuns(bundle, bundle);
    expect(points[0].left).toMatchObject({ population: 100, regionalPopulation: 300, nativePopulation: 12, food: 1, weightedFood: 1.4 });
    expect(savedWorldSummary(bundle).recorded).toContain("Regional model population");
  });
  it("uses phase2 entry ownership even after conquest, never model/native/end counts", () => {
    const bundle = regionalFixture(), snapshot = bundle.history[0];
    snapshot.region_control = { A: "B", B: "A" };
    snapshot.civ_stats.A.regions = ["B"];
    expect(metric(bundle, "civilization", "A", "food")?.value).toBe(1.5);
    expect(metric(bundle, "civilization", "A", "weightedFood")?.value).toBe(0.5);
    expect(populationWeightedFood(bundle, snapshot)).toMatchObject({ value: 1.4, observedPopulation: 100, eligiblePopulation: 100 });
    snapshot.food!.sufficiency[1] = null;
    expect(populationWeightedFood(bundle, snapshot)).toMatchObject({ value: 0.5, observedPopulation: 10, eligiblePopulation: 100, observedRegions: 1, eligibleRegions: 2 });
    const run = { bundle, identity: null, label: "constructed" };
    expect(completedComparisonSummary(run, run, alignCompletedRuns(bundle, bundle), 1).weightedFoodCoverage.left).toContain("10 / 100 eligible agents");
  });
  it("does not invent weights for aggregate, older, missing or zero-denominator records", () => {
    const bundle = regionalFixture(), snapshot = bundle.history[0];
    snapshot.regional_population!.food_weights!.counts = [0, 0];
    expect(populationWeightedFood(bundle, snapshot)).toMatchObject({ value: null, observedPopulation: 0 });
    snapshot.regional_population!.food_weights = null;
    snapshot.regional_population!.agent_counts = null; snapshot.regional_population!.agent_source = null;
    snapshot.regional_population!.mode = "off";
    expect(readRegionalPopulation(bundle, snapshot)?.counts).toEqual([100, 200]);
    expect(populationWeightedFood(bundle, snapshot).value).toBeNull();
    delete snapshot.regional_population;
    expect(metric(bundle, "region", "A", "population")?.value).toBeNull();
    expect(populationWeightedFood(bundle, snapshot).eligiblePopulation).toBeNull();
  });
  it.each([
    { schema_version: 2 }, { counts: [100] }, { counts: [-1, 2] }, { counts: [1.5, 2] },
    { counts: Array(2) }, { sources: Array(2) },
    { sources: ["unknown", "python_region_state"] }, { source_turn: 8 }, { timing: "phase2_entry" },
    { agent_counts: [1] }, { agent_source: null }, { food_weights: {} },
    { food_weights: { source: "phase2_agent_pool", source_turn: 0, timing: "phase2_entry", counts: [1, 2], controller_ids: [0, 2] } },
  ])("treats malformed/unsupported additive record as unknown: %j", (override) => {
    const bundle = regionalFixture(), snapshot = bundle.history[0];
    snapshot.regional_population = { ...snapshot.regional_population, ...override } as RegionalPopulationSnapshot;
    expect(readRegionalPopulation(bundle, snapshot)).toBeNull();
    expect(metric(bundle, "region", "A", "population")?.value).toBeNull();
    expect(populationWeightedFood(bundle, snapshot).value).toBeNull();
    // The optional record cannot make an otherwise supported historical bundle unreadable.
    expect(validateBundleStructure(bundle as unknown as Record<string, unknown>)).toBeNull();
    expect(validateViewableBundle(bundle as unknown as Record<string, unknown>)).toBeNull();
    expect(classifyParsedBundlePayload(bundle).kind).toBe("legacy");
  });
  it("preserves additive observations through loader and does not mutate input", () => {
    const bundle = regionalFixture(), before = JSON.stringify(bundle);
    const result = classifyParsedBundlePayload(bundle);
    expect(result.kind).toBe("legacy");
    if (result.kind === "legacy") expect(readRegionalPopulation(result.bundle, result.bundle.history[0])?.counts).toEqual([100, 200]);
    populationWeightedFood(bundle, bundle.history[0]);
    expect(JSON.stringify(bundle)).toBe(before);
  });
});
