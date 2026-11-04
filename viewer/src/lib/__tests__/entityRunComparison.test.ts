import { describe, expect, it } from "vitest";
import type { CompletedRun } from "../completedRunComparison";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { whatIfManifest } from "../../__fixtures__/whatIf";
import { compareEntityRuns, entityRunMatching, orderEntityRunRows } from "../entityRunComparison";

const input = (bundle = comparisonBundle()): CompletedRun => ({ bundle, identity: null, label: "/private/input.json" });
function pair(a = comparisonBundle(), b = comparisonBundle()): [CompletedRun, CompletedRun] {
  const source = { checkpoint: { sha256: "a".repeat(64), name: "/private/common.ckpt" }, header: { exact: true,
    turn: 2, seed: 42, identity: { source: { git_sha: "test-source", package_digest: "b".repeat(64) }, native: { status: "absent" } },
    world: { regions: 2, civilizations: 2, name: "Constructed fixture", geography: false } } };
  Object.assign(a.metadata, { what_if: { ...whatIfManifest, source, arm: "baseline" } });
  Object.assign(b.metadata, { what_if: { ...whatIfManifest, source: structuredClone(source), arm: "intervention" } });
  return [input(a), input(b)];
}
const tag = (run: CompletedRun) => (run.bundle.metadata as unknown as { what_if: { source: { checkpoint: { sha256: string }; header: { identity: { source: { package_digest: string } }; world: { civilizations: number } } }; arm: string } }).what_if;

describe("per-entity cross-run comparison", () => {
  it("checks exact-pair checkpoint/source/world provenance before using checkpoint indices", () => {
    const [a, b] = pair();
    expect(entityRunMatching(a, b)).toMatchObject({ mode: "checkpoint-index", sharedCivilizations: 2, sharedRegions: 2, checkpointTurn: 2 });
    const row = compareEntityRuns(a, b, 2).rows.find((row) => row.name === "A")!;
    expect(row).toMatchObject({ matching: "checkpoint-index", identityVerified: true, left: { index: 0, value: 20 }, right: { index: 0, value: 20 }, delta: 0, percent: 0 });
    tag(b).source.checkpoint.sha256 = "c".repeat(64);
    expect(entityRunMatching(a, b).mode).toBe("observed-name");
    tag(b).source.checkpoint.sha256 = "a".repeat(64);
    tag(b).source.header.identity.source.package_digest = "c".repeat(64);
    expect(entityRunMatching(a, b).mode).toBe("observed-name");
  });
  it("refuses conflicting runtime identity, seed or arm claims", () => {
    const [a, b] = pair();
    b.bundle.metadata.seed = 123;
    expect(entityRunMatching(a, b).mode).toBe("observed-name");
    b.bundle.metadata.seed = 42;
    tag(b).arm = "baseline";
    expect(entityRunMatching(a, b).mode).toBe("observed-name");
    tag(b).arm = "intervention";
    const source = tag(b).source as unknown as Record<string, unknown>;
    source.current_identity = { source: { package_digest: "c".repeat(64) }, native: { status: "absent" } };
    expect(entityRunMatching(a, b).mode).toBe("observed-name");
  });
  it("keeps unrelated matching names explicitly unverified and detects different world indices", () => {
    const a = input(), b = input();
    b.bundle.world_state.civilizations.reverse();
    b.bundle.metadata.seed = 1234;
    b.bundle.history[1].civ_stats.A.population = 30;
    const result = compareEntityRuns(a, b, 2);
    expect(result.matching.mode).toBe("observed-name");
    expect(result.matching.warnings.join(" ")).toContain("different world indices");
    expect(result.rows.find((row) => row.name === "A")).toMatchObject({ matching: "name-only", identityVerified: false,
      left: { index: 0, value: 20 }, right: { index: 1, value: 30 }, delta: 10, percent: 50 });
  });
  it("refuses an exact-pair index join when prefixes have been reordered", () => {
    const [a, b] = pair();
    b.bundle.world_state.civilizations.reverse();
    const result = compareEntityRuns(a, b, 2);
    expect(result.matching.mode).toBe("observed-name");
    expect(result.matching.warnings.join(" ")).toContain("prefixes disagree");
    expect(result.rows.every((row) => !row.identityVerified)).toBe(true);
  });
  it("does not join post-fork new civilizations at equal appended indices or names", () => {
    const [a, b] = pair();
    for (const run of [a, b]) {
      run.bundle.world_state.civilizations.push({ ...run.bundle.world_state.civilizations[0], name: "New realm" });
      run.bundle.history[2].civ_stats["New realm"] = { ...run.bundle.history[2].civ_stats.A, population: 7 };
    }
    const future = compareEntityRuns(a, b, 2);
    expect(JSON.stringify(future)).not.toContain("New realm");
    const result = compareEntityRuns(a, b, 3);
    const rows = result.rows.filter((row) => row.name === "New realm");
    expect(rows).toHaveLength(2);
    expect(rows.every((row) => row.matching === "unmatched" && !row.identityVerified && row.delta === null)).toBe(true);
    expect(rows.map((row) => [row.left.value, row.right.value])).toEqual([[7, null], [null, 7]]);
  });
  it("uses exact source metrics for civilization population, territory, food, treasury and debt", () => {
    const a = input(regionalFixture()), b = input(regionalFixture());
    const row = b.bundle.history[1].civ_stats.A;
    row.population = 30; row.treasury = 15; row.regions = ["A", "B"];
    b.bundle.history[1].food!.sufficiency = [1, 2];
    b.bundle.history[1].finance!.civs.A.debt = 4;
    const expected = { population: [20, 30, 10], territory: [1, 2, 1], food: [0.5, 1.5, 1], treasury: [10, 15, 5], debt: [10, 4, -6] };
    for (const [measure, values] of Object.entries(expected)) {
      const item = compareEntityRuns(a, b, 2, "civilization", measure as keyof typeof expected).rows.find((row) => row.name === "A")!;
      expect([item.left.value, item.right.value, item.delta]).toEqual(values);
    }
    expect(compareEntityRuns(a, b, 2, "civilization", "debt").measureNote).toContain("not necessarily lower cost");
  });
  it("keeps weighted food denominator coverage and finite-difference limits", () => {
    const a = input(regionalFixture()), b = input(regionalFixture());
    b.bundle.history[1].food!.sufficiency[0] = 1;
    const row = compareEntityRuns(a, b, 2, "civilization", "weightedFood").rows.find((row) => row.name === "A")!;
    expect([row.left.value, row.right.value, row.delta]).toEqual([0.5, 1, 0.5]);
    expect(row.left.note).toContain("eligible agents");
    a.bundle.history[1].civ_stats.A.treasury = -1e308;
    b.bundle.history[1].civ_stats.A.treasury = 1e308;
    expect(compareEntityRuns(a, b, 2, "civilization", "treasury").rows.find((row) => row.name === "A")).toMatchObject({ delta: null, percent: null });
  });
  it("does not subtract a native pre-relief ratio from a legacy food ratio", () => {
    const a = input(regionalFixture()), b = input(regionalFixture());
    const snap = b.bundle.history[1];
    delete snap.food;
    const native = { opening: 1, produced: 0, transport_net: 0, craft_input: 0, clamp_correction: 0,
      pre_consumption: 1, consumed: 1, storage_loss: 0, cap_overflow: 0, closing: 0,
      demand: 1, sufficiency: 1.25, balance_residual: 0, balance_tolerance: 0.00001 };
    snap.food_accounting = { schema_version: 1, mode: "hybrid", source_turn: 1, completed_turn: 2,
      timing: "phase2", units: "model_food_goods", transport: "physical_delivery", procurement: [],
      regions: [{ region_id: 0, native_count: 3, model_population: 3, native, sufficiency_after_relief: null, public: null }] };
    const row = compareEntityRuns(a, b, 2, "region", "food").rows.find((item) => item.name === "A")!;
    expect(row).toMatchObject({ left: { value: 0.5 }, right: { value: 1.25 }, delta: null, percent: null });
    expect(row.right.note).toContain("Food bases differ");
    delete a.bundle.history[1].food;
    a.bundle.history[1].food_accounting = structuredClone(snap.food_accounting);
    a.bundle.history[1].food_accounting!.regions[0].native!.sufficiency = 1;
    expect(compareEntityRuns(a, b, 2, "region", "food").rows.find((item) => item.name === "A")!.delta).toBe(0.25);
  });
  it("keeps regional model population separate, follows each input index and never substitutes final populations", () => {
    const a = input(regionalFixture()), b = input(regionalFixture());
    b.bundle.world_state.regions.reverse();
    b.bundle.history[1].regional_population!.counts = [555, 777];
    b.bundle.history[2].regional_population!.counts = [99999, 99999];
    const row = compareEntityRuns(a, b, 2, "region").rows.find((row) => row.name === "A")!;
    expect(row).toMatchObject({ identityVerified: false, left: { index: 0, value: 100 }, right: { index: 1, value: 777 }, delta: 677 });
    delete b.bundle.history[1].regional_population;
    expect(compareEntityRuns(a, b, 2, "region").rows.find((row) => row.name === "A")!.right.value).toBeNull();
  });
  it("leaves selected gaps, shorter tails, pruned rows and zero baselines honest", () => {
    const a = input(comparisonBundle([1, 3])), b = input(comparisonBundle([1, 2]));
    expect(compareEntityRuns(a, b, 3).rows.every((row) => row.right.value === null && row.delta === null)).toBe(true);
    expect(compareEntityRuns(a, b, 2).rows.every((row) => row.left.value === null && row.delta === null)).toBe(true);
    const c = input(), d = input();
    c.bundle.history[1].civ_stats.A.population = 0;
    expect(compareEntityRuns(c, d, 2).rows.find((row) => row.name === "A")).toMatchObject({ delta: 20, percent: null });
    delete d.bundle.history[1].civ_stats.A;
    expect(compareEntityRuns(c, d, 2).rows.find((row) => row.name === "A")).toMatchObject({ right: { value: null }, delta: null });
  });
  it("retains actual landless rows without claiming permanent extinction or zeroing their values", () => {
    const a = input(), b = input();
    const row = compareEntityRuns(a, b, 2).rows.find((row) => row.name === "Fallen")!;
    expect(row.left.value).toBe(9000);
    expect(row.left.status).toContain("permanence unknown");
    expect(compareEntityRuns(a, b, 2, "civilization", "territory").rows.find((row) => row.name === "Fallen")!.left.value).toBe(0);
  });
  it("refuses ambiguous world names and region mappings rather than taking the first array row", () => {
    const a = input(), b = input();
    b.bundle.world_state.civilizations[1].name = "A";
    const row = compareEntityRuns(a, b, 2).rows.find((row) => row.name === "A")!;
    expect(row).toMatchObject({ matching: "ambiguous", delta: null, right: { value: null } });
    const c = input(), d = input();
    d.bundle.world_state.regions[1].name = "A";
    expect(compareEntityRuns(c, d, 2, "civilization", "food").rows.find((row) => row.name === "A")!.right.value).toBeNull();
  });
  it("does not alias different names or expose future founders from final arrays", () => {
    const a = input(), b = input();
    for (const snapshot of b.bundle.history) { snapshot.civ_stats.Renamed = snapshot.civ_stats.A; delete snapshot.civ_stats.A; }
    b.bundle.world_state.civilizations[0].name = "Renamed";
    a.bundle.world_state.civilizations.push({ ...a.bundle.world_state.civilizations[0], name: "Future realm" });
    const result = compareEntityRuns(a, b, 2);
    expect(result.rows.find((row) => row.name === "A")!.right.value).toBeNull();
    expect(result.rows.find((row) => row.name === "Renamed")!.left.value).toBeNull();
    expect(JSON.stringify(result)).not.toContain("Future realm");
  });
  it("orders one measure without mutating inputs and exports no raw world or private source paths", () => {
    const [a, b] = pair();
    b.bundle.history[1].civ_stats.A.population = 10;
    b.bundle.history[1].civ_stats.B.population = 100;
    const before = JSON.stringify([a, b]);
    const result = compareEntityRuns(a, b, 2);
    expect(orderEntityRunRows(result.rows, "higher")[0].name).toBe("B");
    expect(orderEntityRunRows(result.rows, "lower")[0].name).toBe("A");
    expect(JSON.stringify([a, b])).toBe(before);
    const exported = JSON.stringify(result);
    expect(exported).not.toContain("/private/");
    expect(exported).not.toContain("world_state");
    expect(exported).not.toContain("checkpoint\":");
    expect(JSON.parse(exported).matching.checkpointSha256).toBe("a".repeat(64));
  });
  it("keeps duplicate endpoint turns and invalid turn requests unknown", () => {
    const a = input(), b = input();
    b.bundle.history.push(structuredClone(b.bundle.history[1]));
    expect(compareEntityRuns(a, b, 2).rows.every((row) => row.right.value === null && row.delta === null)).toBe(true);
    expect(compareEntityRuns(a, b, -1).rows).toEqual([]);
  });
});
