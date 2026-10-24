import { describe, expect, it } from "vitest";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, CivSnapshot, TurnSnapshot } from "../../types";
import { civChartRows, civDisplayRow, civRowAt, civStatSeries, snapshotPositionAt } from "../civRows";

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;

function row(regions: string[], treasury: number): CivSnapshot {
  return {
    population: regions.length ? 10 : 0, military: 5, economy: 5, culture: 5, stability: 50,
    treasury, asabiya: 0.5, tech_era: "tribal", trait: "bold", regions, leader_name: "L",
    alive: regions.length > 0,
  } as CivSnapshot;
}

function snap(turn: number, civ_stats: Record<string, CivSnapshot>): TurnSnapshot {
  return { turn, civ_stats, region_control: {}, relationships: {} };
}

// A lives throughout; B dies at turn 3 (its final row) and is left out of
// later snapshots, as bundle version 5 writes them; C is founded at turn 4.
const pruned: TurnSnapshot[] = [
  snap(1, { A: row(["a"], 1), B: row(["b"], 10) }),
  snap(2, { A: row(["a"], 2), B: row(["b"], 11) }),
  snap(3, { A: row(["a"], 3), B: row([], 12) }),
  snap(4, { A: row(["a"], 4), C: row(["c"], 0) }),
  snap(5, { A: row(["a"], 5), C: row(["c"], 1) }),
];

describe("civ rows over pruned histories", () => {
  it("finds the snapshot shown for a turn", () => {
    expect(snapshotPositionAt(pruned, 0)).toBe(0);
    expect(snapshotPositionAt(pruned, 3)).toBe(2);
    expect(snapshotPositionAt(pruned, 99)).toBe(4);
    expect(snapshotPositionAt([], 3)).toBe(-1);
  });

  it("carries a dead civ's final row past its death", () => {
    expect(civRowAt(pruned, "B", 3)).toMatchObject({ turn: 3, recorded: true });
    const after = civRowAt(pruned, "B", 5);
    expect(after).toMatchObject({ turn: 3, recorded: false });
    expect(after?.row.treasury).toBe(12);
    expect(civDisplayRow(pruned, "B", 5)).toMatchObject({ alive: false, regions: [], treasury: 12 });
  });

  it("has no row before a civ is founded", () => {
    expect(civRowAt(pruned, "C", 2)).toBeNull();
    expect(civDisplayRow(pruned, "C", 2)).toBeNull();
    expect(civRowAt(pruned, "C", 4)).toMatchObject({ turn: 4, recorded: true });
    expect(civRowAt(pruned, "Nobody", 4)).toBeNull();
  });

  it("ends a series where the rows end", () => {
    expect(civStatSeries(pruned, "B", "treasury")).toEqual([10, 11, 12, null, null]);
    expect(civStatSeries(pruned, "C", "treasury")).toEqual([null, null, null, 0, 1]);
    expect(civChartRows(pruned, ["A", "B"], "treasury", "stability")[4]).toEqual({
      turn: 5, A: 5, A_cmp: 50, B: null, B_cmp: null,
    });
  });

  it("reads version-4 histories, which keep every row, unchanged", () => {
    const last = sample.history[sample.history.length - 1];
    for (const name of Object.keys(last.civ_stats)) {
      expect(civRowAt(sample.history, name, last.turn)).toEqual({ row: last.civ_stats[name], turn: last.turn, recorded: true });
    }
  });

  it("reads the real version-5 systems fixture", () => {
    expect(systems.metadata.bundle_version).toBe(5);
    // Khorain Kingdom loses its land by turn 4 and leaves the history after it.
    const final = systems.history.find((s) => s.turn === 4)!.civ_stats["Khorain Kingdom"];
    expect(final).toMatchObject({ alive: false, regions: [] });
    expect(systems.history.filter((s) => s.turn > 4).every((s) => !("Khorain Kingdom" in s.civ_stats))).toBe(true);
    expect(civRowAt(systems.history, "Khorain Kingdom", 120)).toMatchObject({ turn: 4, recorded: false, row: final });
    const series = civStatSeries(systems.history, "Khorain Kingdom", "population");
    expect(series.slice(0, 2).every((v) => v !== null)).toBe(true);
    expect(series.slice(2).every((v) => v === null)).toBe(true);
  });
});
