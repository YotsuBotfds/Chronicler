import { describe, expect, it } from "vitest";
import type { Bundle } from "../../types";
import sample from "../../__fixtures__/sample_bundle.json";
import systems from "../../__fixtures__/systems_bundle.json";
import { comparisonBundle, comparisonSnapshot } from "../../__fixtures__/completedRunHistory";
import { alignCompletedRuns, completedComparisonSummary, completedRunIdentity, comparisonMarkdown, comparisonWarnings,
  type CompletedRun } from "../completedRunComparison";

const input = (bundle: Bundle, name = "run.json"): CompletedRun => ({ bundle, label: name,
  identity: { name, byteLength: 42, sha256: name === "right.json" ? "b".repeat(64) : "a".repeat(64) } });

describe("completed-run exact metrics", () => {
  it("sums current landholding rows once, excludes dead rows and never adds foreign principal twice", () => {
    const bundle = comparisonBundle();
    const row = alignCompletedRuns(bundle, bundle)[0].left!;
    expect(row).toMatchObject({ population: 100, treasury: 40, debt: 40, revenue: 8, economy: 10,
      food: 1, foodObserved: 2, foodRegions: 2, short: 1, wars: 1, incidents: 1 });
    expect(alignCompletedRuns(bundle, bundle)[2].left?.incidents).toBe(2);
  });

  it("uses an unweighted observed-region mean and makes partial totals unknown", () => {
    const bundle = comparisonBundle([1]);
    bundle.history[0].food!.sufficiency = [0.5, null];
    delete bundle.history[0].finance!.civs.B;
    const row = alignCompletedRuns(bundle, bundle)[0].left!;
    expect(row).toMatchObject({ food: 0.5, foodObserved: 1, foodRegions: 2, short: null, debt: null, revenue: null });
    delete bundle.history[0].civ_stats.B;
    expect(alignCompletedRuns(bundle, bundle)[0].left).toMatchObject({ population: null, treasury: null, economy: null });
  });

  it("retains gaps and shorter tails instead of borrowing a final world or a later row", () => {
    const left = comparisonBundle([1, 3]), right = comparisonBundle([1, 2]);
    const points = alignCompletedRuns(left, right);
    expect(points.map((point) => [point.turn, point.left?.population ?? null, point.right?.population ?? null]))
      .toEqual([[1, 100, 100], [2, null, 100], [3, 100, null]]);
    const sparse = alignCompletedRuns(comparisonBundle([1, 1_000_000]), comparisonBundle([1, 1_000_000]));
    expect(sparse.map((point) => point.turn)).toEqual([1, 2, 999_999, 1_000_000]);
    expect(sparse[1].left).toBeNull();
  });

  it("rejects ambiguous duplicate turns and keeps true zero distinct from invalid numeric fields", () => {
    const a = comparisonBundle([1, 2]);
    a.history.push(comparisonSnapshot(1));
    a.history[1].civ_stats.A.population = 0;
    a.history[1].civ_stats.B.population = 0;
    a.history[1].civ_stats.A.treasury = "wrong" as unknown as number;
    a.history[1].food!.sufficiency = "wrong" as unknown as number[];
    a.history[1].active_wars = [["A", "A"]];
    const points = alignCompletedRuns(a, comparisonBundle([1, 2]));
    expect(points[0].left).toBeNull();
    expect(points[1].left).toMatchObject({ population: 0, treasury: null, food: null, wars: null });
  });

  it("reads older and current fixtures without inventing unexported food or finance", () => {
    const old = sample as unknown as Bundle, current = systems as unknown as Bundle;
    const oldRow = alignCompletedRuns(old, old)[0].left!;
    expect(oldRow.food).toBeNull(); expect(oldRow.debt).toBeNull();
    const currentRow = alignCompletedRuns(current, current)[0].left!;
    const food = current.history[0].food!.sufficiency.filter((v): v is number => v !== null);
    expect(currentRow.food).toBeCloseTo(food.reduce((a, b) => a + b, 0) / food.length);
    expect(currentRow.debt).toBeGreaterThanOrEqual(0);
  });

  it("does not carry a fallen civilization's final row into a later aggregate", () => {
    const bundle = comparisonBundle([1, 2]);
    bundle.history[1].civ_stats.B.alive = false;
    bundle.history[1].civ_stats.B.regions = [];
    bundle.history[1].region_control.B = null;
    delete bundle.history[1].civ_stats.Fallen;
    const row = alignCompletedRuns(bundle, bundle)[1].left!;
    expect(row.population).toBe(20); expect(row.debt).toBe(10); expect(row.treasury).toBe(10);
  });
});

describe("comparison provenance and exports", () => {
  it("distinguishes explicitly aggregate mode from missing provenance and records enabled systems", () => {
    const bundle = comparisonBundle();
    Object.assign(bundle.world_state, { agent_mode: null, grain_reserves: { shipments: { accept_orders: true } } });
    const identity = completedRunIdentity(input(bundle));
    expect(identity.agentMode).toBe("off (aggregate)");
    expect(identity.settings.enabledFinalSystems).toEqual(expect.arrayContaining(["Public granaries", "Public grain shipments"]));
    delete (bundle.world_state as unknown as Record<string, unknown>).agent_mode;
    expect(completedRunIdentity(input(bundle)).agentMode).toBeNull();
  });
  it("warns for differing seed, horizon, mode, settings and source without assuming equal seeds control anything", () => {
    const a = comparisonBundle([1]), b = comparisonBundle([1, 2]);
    Object.assign(a.world_state, { agent_mode: "hybrid", tuning_overrides: {} });
    Object.assign(b.world_state, { agent_mode: "off", tuning_overrides: { priority: 1 } });
    Object.assign(a.metadata, { source_commit: "old" }); Object.assign(b.metadata, { source_commit: "new", seed: 8 });
    const warnings = comparisonWarnings(input(a), input(b));
    expect(warnings).toEqual(expect.arrayContaining(["Seeds differ.", "Recorded horizons differ.", "Agent modes differ.",
      "Recorded settings differ.", "Source versions differ."]));
    expect(warnings[0]).toContain("Equal seeds do not establish a controlled experiment");
    expect(completedRunIdentity(input(comparisonBundle())).source).toBeNull();
  });

  it("exports input byte hashes, settings, warnings, null differences, coverage and source limits", () => {
    const left = input(comparisonBundle([1, 3])), right = input(comparisonBundle([1, 2]), "right.json");
    const summary = completedComparisonSummary(left, right, alignCompletedRuns(left.bundle, right.bundle), 3);
    expect(summary.metrics.find((row) => row.key === "population")).toMatchObject({ left: 100, right: null, delta: null,
      coverage: { left: 2, right: 2, leftSnapshots: 2, rightSnapshots: 2 } });
    const text = comparisonMarkdown(summary);
    expect(text).toContain("a".repeat(64)); expect(text).toContain("b".repeat(64));
    expect(text).toContain("Not recorded"); expect(text).toContain("Recorded settings");
    expect(text).toContain("Unweighted mean"); expect(text).toContain("Snapshot 3");
    expect(text).toContain("final-world outcome values are never used");
    expect(JSON.parse(JSON.stringify(summary)).inputs.left.source).toBeNull();
  });
});
