import { describe, expect, it } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { whereToLook } from "../whereToLook";
import type { GovernanceSnapshot } from "../../types";

describe("selected-turn inspection prompts", () => {
  it("groups thresholds per entity and states exact values/windows without causal ranking", () => {
    const bundle = regionalFixture();
    bundle.history[1].regional_population!.counts[0] = 70;
    bundle.history[1].finance!.civs.A.arrears_turns = 2;
    bundle.history[1].migration = [[0, 1, 3], [0, 1, 2]];
    const result = whereToLook(bundle, 2);
    const a = result.items.find((row) => row.entity.kind === "region" && row.entity.name === "A")!;
    expect(a.reasons.map((row) => row.kind)).toEqual(["Food distress", "Sharp population change", "Displacement / movement"]);
    expect(a.reasons[1]).toMatchObject({ window: "Snapshots 1 → 2", values: "Model population 100 → 70 (-30%)" });
    expect(a.reasons[2].values).toContain("5 out");
    expect(result.items.find((row) => row.entity.kind === "civilization" && row.entity.name === "A")?.reasons[0].kind).toBe("Debt trouble");
  });
  it("never leaks a future population, debt, migration or recovery condition", () => {
    const bundle = regionalFixture();
    const first = JSON.stringify(whereToLook(bundle, 1));
    bundle.history[2].regional_population!.counts = [0, 99999];
    bundle.history[2].finance!.civs.A.arrears_turns = 999;
    bundle.history[2].migration = [[0, 1, 999]];
    expect(JSON.stringify(whereToLook(bundle, 1))).toBe(first);
    expect(whereToLook(bundle, 0).status).toBe("Selected snapshot unavailable");
  });
  it("keeps earliest, missing, duplicate and extinct histories honest", () => {
    const bundle = comparisonBundle();
    const first = whereToLook(bundle, 1);
    expect(first.coverage.join(" ")).toContain("no earlier recorded snapshot");
    expect(first.items.some((row) => row.entity.name === "Fallen")).toBe(false);
    expect(whereToLook(bundle, 2).coverage.join(" ")).toContain("selected regional model counts unknown");
    delete bundle.history[1].food;
    expect(whereToLook(bundle, 2).items).toHaveLength(0);
    bundle.history.push(structuredClone(bundle.history[1]));
    expect(whereToLook(bundle, 2).items).toHaveLength(0);
    expect(whereToLook(bundle, 2).coverage[0]).toContain("unambiguous");
  });
  it("reads only valid regional recovery source clocks and recorded governance trouble", () => {
    const bundle = regionalFixture(), snapshot = bundle.history[0];
    snapshot.civ_stats.A.governance = { funding_ratio: 0.4, psi_crisis: true } as GovernanceSnapshot;
    expect(whereToLook(bundle, 1).items.find((item) => item.entity.kind === "civilization")?.reasons[0].kind).toBe("Institutions");
    snapshot.health_care = { source_turn: 0, units: "worker-turns", episodes: 1, new_injuries: 0, recoveries: 2,
      impaired_work: 0, care_work: 1, care_recipients: 1, regions: [{ region: 0, region_name: "A", civ: 0, civ_name: "A",
        episodes: 1, new_injuries: 0, recoveries: 2, impaired_work: 0, care_work: 1, care_recipients: 1, recovery_progress: 1, cared_recovery_progress: 1 }] };
    expect(whereToLook(bundle, 1).items[0].reasons.map((row) => row.kind)).toContain("Recovery");
    snapshot.health_care.source_turn = 9;
    expect(whereToLook(bundle, 1).items[0].reasons.map((row) => row.kind)).not.toContain("Recovery");
  });
});
