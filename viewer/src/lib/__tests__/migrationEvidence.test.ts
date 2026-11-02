import { describe, expect, it } from "vitest";
import type { Event, MigrationFlow } from "../../types";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { readMigrationEvidence } from "../migrationEvidence";

const report = (turn: number, region: string, driver?: string): Event => ({
  turn, region, driver, event_type: "mass_migration", description: `Report at ${turn} in ${region}`,
  actors: [], consequences: [], importance: 5,
});

describe("exact migration evidence", () => {
  it("reuses pair aggregation, preserving all repeated raw triple sources and native units", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 3], [0, 1, 2], [1, 0, 1]];
    bundle.history[0].migration = [[0, 1, 999]];
    bundle.history[2].migration = [[1, 0, 888]];
    const result = readMigrationEvidence(bundle, 2, 0);
    expect(result.status).toBe("recorded");
    expect(result.sourceTick).toBe(1);
    expect(result.completedTick).toBe(1);
    expect(result.totalAgents).toBe(6);
    expect(result.netAgents).toBe(-4);
    expect(result.flows).toEqual([
      { fromIndex: 0, toIndex: 1, fromName: "A", toName: "B", agents: 5,
        sourcePointers: ["/history/1/migration/0", "/history/1/migration/1"], reason: null },
      { fromIndex: 1, toIndex: 0, fromName: "B", toName: "A", agents: 1,
        sourcePointers: ["/history/1/migration/2"], reason: null },
    ]);
  });

  it("distinguishes absent, recorded empty, and recorded zero movement in a selected region", () => {
    const bundle = regionalFixture();
    expect(readMigrationEvidence(bundle, 2).status).toBe("not-recorded");
    expect(readMigrationEvidence(bundle, 2).totalAgents).toBeNull();
    bundle.history[1].migration = [];
    const empty = readMigrationEvidence(bundle, 2, 1);
    expect(empty.status).toBe("recorded");
    expect(empty.totalAgents).toBe(0);
    expect(empty.netAgents).toBe(0);
    expect(empty.note).toContain("Recorded empty");
    bundle.history[1].migration = [[0, 0, 2]];
    const outside = readMigrationEvidence(bundle, 2, 1);
    expect(outside.totalAgents).toBe(0);
    expect(outside.netAgents).toBe(0);
    expect(outside.note).toContain("no movement involving this region");
  });

  it.each([
    "bad", [[0, 1]], [[0, 1, 2, 4]], [[0, 2, 1]], [[-1, 1, 2]], [[0.5, 1, 2]],
    [[0, 1, -1]], [[0, 1, 1.5]], [[0, 1, Infinity]], [[0, 1, NaN]],
    [[0, 1, Number.MAX_SAFE_INTEGER], [1, 0, 1]], [Object.assign(new Array(3), { 0: 0, 2: 2 })],
  ].map((rows) => ({ rows })))("rejects the entire malformed or out-of-universe record: $rows", ({ rows }) => {
    const bundle = regionalFixture();
    bundle.history[1].migration = rows as unknown as MigrationFlow[];
    const reading = readMigrationEvidence(bundle, 2);
    expect(reading.status).toBe("invalid");
    expect(reading.flows).toEqual([]);
    expect(reading.totalAgents).toBeNull();
    expect(reading.netAgents).toBeNull();
  });

  it("requires one exact snapshot and rejects invalid turns and index scopes", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 2]];
    for (const index of [-1, 2, 0.5, NaN]) {
      expect(readMigrationEvidence(bundle, 2, index).status).toBe("unavailable");
    }
    for (const turn of [0, 1.5, NaN, 99]) {
      expect(readMigrationEvidence(bundle, turn).status).toBe("unavailable");
    }
    bundle.history.push(structuredClone(bundle.history[1]));
    expect(readMigrationEvidence(bundle, 2).status).toBe("unavailable");
    expect(readMigrationEvidence(bundle, 2).flows).toEqual([]);
  });

  it("uses index scopes through conquest, duplicate names, disconnected layouts and future owner changes", () => {
    const bundle = regionalFixture();
    bundle.world_state.regions[0].name = "B";
    bundle.world_state.regions[0].controller = "Future conqueror";
    bundle.world_state.regions[0].adjacencies = [];
    bundle.world_state.regions[1].adjacencies = [];
    bundle.history[1].region_control = { B: "Old owner" };
    bundle.history[1].migration = [[0, 1, 7]];
    const origin = readMigrationEvidence(bundle, 2, 0);
    const destination = readMigrationEvidence(bundle, 2, 1);
    expect(origin.netAgents).toBe(-7);
    expect(destination.netAgents).toBe(7);
    expect(origin.flows[0].fromIndex).toBe(0);
    expect(origin.flows[0].toIndex).toBe(1);
    expect(JSON.stringify(origin)).not.toContain("Future conqueror");
    expect(JSON.stringify(origin)).not.toContain("Old owner");
  });

  it("keeps group driver reports separate, exact-clocked and scoped to unambiguous source regions", () => {
    const bundle = regionalFixture();
    bundle.history[1].migration = [[0, 1, 4]];
    bundle.events_timeline = [report(0, "A", "battle_memory"), report(1, "A", "wage"),
      report(1, "B", "frontier"), report(2, "A", "persecution"), report(1, "Unknown", "chain")];
    const reading = readMigrationEvidence(bundle, 2, 0);
    expect(reading.context).toHaveLength(1);
    expect(reading.context[0].event).toBe(bundle.events_timeline[1]);
    expect(reading.context[0].sourcePointer).toBe("/events_timeline/1");
    expect(reading.context[0].dominantUtilityTerm).toBe("seeking work");
    expect(reading.flows.every((flow) => flow.reason === null)).toBe(true);
    bundle.world_state.regions[1].name = "A";
    expect(readMigrationEvidence(bundle, 2).context).toEqual([]);
  });

  it("compares actual consecutive model counts separately without matching them to native net movement", () => {
    const bundle = regionalFixture();
    bundle.history[0].regional_population!.counts[0] = 100;
    bundle.history[1].regional_population!.counts[0] = 90;
    bundle.history[1].migration = [[0, 1, 2]];
    const reading = readMigrationEvidence(bundle, 2, 0);
    expect(reading.netAgents).toBe(-2);
    expect(reading.populationChange).toEqual({ before: 100, after: 90, delta: -10,
      sourcePointers: ["/history/0/regional_population/counts/0", "/history/1/regional_population/counts/0"],
      beforeSource: "python_region_state", afterSource: "python_region_state", beforeMode: "shadow", afterMode: "shadow" });
    bundle.history = bundle.history.filter((snapshot) => snapshot.turn !== 2);
    expect(readMigrationEvidence(bundle, 3, 0).populationChange).toBeNull();
  });

  it("does not borrow invalid, ambiguous or absent population observations", () => {
    const bundle = regionalFixture();
    bundle.history[0].regional_population!.source_turn = 999;
    expect(readMigrationEvidence(bundle, 2, 0).populationChange).toBeNull();
    delete bundle.history[0].regional_population;
    expect(readMigrationEvidence(bundle, 2, 0).populationChange).toBeNull();
    bundle.history.push(structuredClone(bundle.history[0]));
    expect(readMigrationEvidence(bundle, 2, 0).populationChange).toBeNull();
  });
});
