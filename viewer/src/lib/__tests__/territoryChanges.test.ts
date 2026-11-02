import { describe, expect, it } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { compareTerritory, territoryEarlierTurns } from "../territoryChanges";

describe("exact territory comparisons", () => {
  it("defaults to the previous recorded endpoint and never interpolates or uses future/final control", () => {
    const bundle = comparisonBundle([1, 4, 9]);
    bundle.history[1].region_control.A = "B";
    bundle.history[2].region_control.A = null;
    bundle.world_state.regions[0].controller = "A";
    expect(territoryEarlierTurns(bundle, 4)).toEqual([1]);
    const result = compareTerritory(bundle, 4);
    expect(result).toMatchObject({ fromTurn: 1, toTurn: 4, valid: true });
    expect(result.rows[0]).toMatchObject({ regionId: 0, status: "transferred", before: { civilizationId: 0 }, after: { civilizationId: 1 } });
    for (const [selected, from] of [[3, 1], [4, 3], [4, 9], [4, 4]]) {
      const unknown = compareTerritory(bundle, selected, from);
      expect(unknown.valid).toBe(false);
      expect(unknown.rows.every((row) => row.status === "unknown")).toBe(true);
    }
  });
  it("reports gained/lost for stable civilization focus and global transfers", () => {
    const bundle = comparisonBundle();
    bundle.history[1].region_control = { A: "B", B: "A" };
    const global = compareTerritory(bundle, 2);
    expect(global.counts.transferred).toBe(2);
    expect(compareTerritory(bundle, 2, undefined, 0).rows.map((row) => row.status)).toEqual(["lost", "gained"]);
    expect(compareTerritory(bundle, 2, undefined, 1).rows.map((row) => row.status)).toEqual(["gained", "lost"]);
  });
  it("distinguishes explicitly uncontrolled from missing controllers", () => {
    const bundle = comparisonBundle();
    bundle.history[0].region_control.A = null;
    delete bundle.history[0].region_control.B;
    const result = compareTerritory(bundle, 2);
    expect(result.rows[0]).toMatchObject({ status: "gained", before: { known: true, civilizationId: null } });
    expect(result.rows[1]).toMatchObject({ status: "unknown", before: { known: false } });
    bundle.history[0].region_control.A = "A";
    bundle.history[1].region_control.A = null;
    expect(compareTerritory(bundle, 2).rows[0].status).toBe("lost");
  });
  it("never infers a region rename or a civilization rename as a conquest", () => {
    const bundle = comparisonBundle();
    bundle.history[0].region_control = { OldRegion: "A", B: "OldEmpire" };
    bundle.history[0].civ_stats.OldEmpire = bundle.history[0].civ_stats.B;
    delete bundle.history[0].civ_stats.B;
    const result = compareTerritory(bundle, 2);
    expect(result.rows.map((row) => row.status)).toEqual(["unknown", "unknown"]);
    expect(result.counts.transferred).toBe(0);
    expect(result.rows[0].before.reason).toContain("no historical alias");
    expect(result.rows[1].before.reason).toContain("civilization identity");
  });
  it("requires both an unambiguous world identity and an endpoint civilization record", () => {
    const bundle = comparisonBundle();
    delete bundle.history[0].civ_stats.A;
    expect(compareTerritory(bundle, 2).rows[0].status).toBe("unknown");
    bundle.world_state.civilizations[1].name = "A";
    expect(compareTerritory(bundle, 2).rows.every((row) => row.status === "unknown")).toBe(true);
    expect(compareTerritory(bundle, 2, undefined, 0).valid).toBe(false);
    expect(compareTerritory(bundle, 2, undefined, 99).valid).toBe(false);
  });
  it("does not merge regions with duplicate legacy names or choose duplicate turns", () => {
    const bundle = comparisonBundle();
    bundle.world_state.regions[1].name = "A";
    expect(compareTerritory(bundle, 2).rows.every((row) => !row.inspectable && row.status === "unknown")).toBe(true);
    bundle.history.push(structuredClone(bundle.history[1]));
    expect(compareTerritory(bundle, 2).valid).toBe(false);
    expect(compareTerritory(bundle, 3).fromTurn).toBe(1);
  });
  it("counts unchanged held, unchanged uncontrolled and outside-focus regions separately", () => {
    const bundle = comparisonBundle();
    expect(compareTerritory(bundle, 2).counts.unchanged).toBe(2);
    expect(compareTerritory(bundle, 2, undefined, 0).counts).toMatchObject({ unchanged: 1, outside: 1 });
    bundle.history[0].region_control.B = null;
    bundle.history[1].region_control.B = null;
    expect(compareTerritory(bundle, 2).rows[1].status).toBe("unchanged");
  });
});
