import { describe, expect, it } from "vitest";
import { comparisonBundle, comparisonSnapshot } from "../../__fixtures__/completedRunHistory";
import type { Event } from "../../types";
import { civilizationHistory } from "../civilizationHistory";

const event = (turn: number, event_type = "collapse", actors = ["A"]): Event => ({ turn, event_type, actors,
  description: `Recorded ${event_type}`, importance: 5, consequences: [], event_id: `${event_type}:${turn}` });

describe("bounded civilization life history", () => {
  it("uses exact dated rows and excludes future values, names and events", () => {
    const bundle = comparisonBundle([1, 4, 9]);
    bundle.history[0].civ_stats.A.population = 12;
    bundle.history[1].civ_stats.A.population = 15;
    bundle.history[2].civ_stats.A.population = 99999;
    bundle.events_timeline = [event(3), event(4, "restoration"), event(8)];
    bundle.world_state.civilizations[0].leader.name = "Future ruler";
    const result = civilizationHistory(bundle, 4, 0);
    expect(result.entries.map((row) => row.turn)).toEqual([1, 4]);
    expect(result.entries.map((row) => row.population)).toEqual([12, 15]);
    expect(result.entries[1].events.map((ref) => ref.event.event_type)).toEqual(["collapse"]);
    expect(result.entries[1].events[0].visibleTurn).toBe(4);
    expect(JSON.stringify(result)).not.toContain("Future ruler");
    expect(result.entries[1].source).toBe('history[1].civ_stats["A"]');
  });
  it("does not expose a final name, foundation date or values before any bounded record", () => {
    const bundle = comparisonBundle();
    bundle.world_state.civilizations[1].name = "Future empire";
    bundle.world_state.civilizations[1].founded_turn = 999;
    bundle.events_timeline = [event(2, "secession", ["A", "Future empire"])];
    const result = civilizationHistory(bundle, 1, 1);
    expect(result).toMatchObject({ name: null, entries: [], lineage: [] });
    expect(JSON.stringify(result)).not.toContain("Future empire");
    expect(JSON.stringify(result)).not.toContain("999");
  });
  it("retains source-dated observations across sparse/pruned gaps without synthesizing state", () => {
    const bundle = comparisonBundle([1, 2, 5]);
    delete bundle.history[1].civ_stats.A;
    bundle.pruned_civ_stats = { A: [{ from_turn: 2, snapshots: 1, changes: { treasury: [[1, 999, null]] } }] };
    bundle.history[2].civ_stats.A.leader_name = "New recorded name";
    bundle.history[2].civ_stats.A.alive = false;
    bundle.events_timeline = [];
    const result = civilizationHistory(bundle, 5, 0);
    expect(result.entries[1]).toMatchObject({ recorded: false, population: null, treasury: null, alive: null, leader: null });
    expect(result.entries[2].observations.join(" ")).toContain("leader name A → New recorded name; reason not inferred");
    expect(result.entries[2].observations.join(" ")).toContain("no collapse or restoration is inferred");
    expect(result.entries[2].observations.join(" ")).toContain("intermediate states are not reconstructed");
    expect(result.lineage).toEqual([]);
  });
  it("keeps an unrecorded selected turn unknown even with earlier valid data", () => {
    const result = civilizationHistory(comparisonBundle([1, 4]), 3, 0);
    expect(result.entries.at(-1)).toMatchObject({ turn: 3, recorded: false, population: null, status: "Snapshot not recorded" });
    expect(result.status).toContain("selected turn 3");
  });
  it("labels the first observation without assuming foundation or using world founded_turn", () => {
    const bundle = comparisonBundle([4, 8]);
    bundle.world_state.civilizations[0].founded_turn = 77;
    const result = civilizationHistory(bundle, 4, 0);
    expect(result.entries.find((entry) => entry.recorded)!.observations[0]).toContain("First recorded observation");
    expect(result.entries.find((entry) => entry.recorded)!.observations[0]).toContain("foundation date unknown");
    expect(JSON.stringify(result.entries)).not.toContain("77");
  });
  it("does not infer restoration from disappearance/reappearance or overloaded restoration events", () => {
    const bundle = comparisonBundle();
    delete bundle.history[1].civ_stats.A;
    bundle.events_timeline = [event(2, "restoration", ["A", "Ruler name"])];
    const result = civilizationHistory(bundle, 3, 0);
    expect(result.civilizationIndex).toBe(0);
    expect(result.lineage).toEqual([]);
    expect(result.entries[2].events[0].event.description).toBe("Recorded restoration");
    expect(result.notes.join(" ")).toContain("realm or an individual ruler");
  });
  it("requires explicit secession actor roles, unique identities and exact rows to establish lineage", () => {
    const bundle = comparisonBundle();
    bundle.events_timeline = [event(1, "secession", ["A", "B"])];
    const result = civilizationHistory(bundle, 2, 1);
    expect(result.lineage).toMatchObject([{ parentIndex: 0, childIndex: 1, parentName: "A", childName: "B", visibleTurn: 2 }]);
    expect(civilizationHistory(bundle, 1, 1).lineage).toEqual([]);
    delete bundle.history[1].civ_stats.B;
    expect(civilizationHistory(bundle, 2, 0).lineage).toEqual([]);
    bundle.history[1].civ_stats.B = comparisonSnapshot(2).civ_stats.B;
    bundle.world_state.civilizations[1].name = "A";
    expect(civilizationHistory(bundle, 2, 0)).toMatchObject({ name: null, entries: [], lineage: [] });
  });
  it("keeps duplicate snapshots ambiguous and duplicate event keys unselectable", () => {
    const bundle = comparisonBundle();
    bundle.history.push(structuredClone(bundle.history[1]));
    bundle.events_timeline = [event(1), event(1)];
    const result = civilizationHistory(bundle, 2, 0);
    expect(result.entries.at(-1)).toMatchObject({ recorded: false, population: null, status: "Snapshot ambiguous (duplicate turn)" });
    expect(result.entries.at(-1)!.events.every((ref) => !ref.inspectable)).toBe(true);
  });
  it("does not map aliases, duplicate region names or successor relationships from names alone", () => {
    const bundle = comparisonBundle();
    bundle.history[0].civ_stats.A.regions = ["Old land", "B"];
    bundle.world_state.regions[0].name = "B";
    bundle.events_timeline = [event(0, "restoration", ["A", "B"])];
    const result = civilizationHistory(bundle, 1, 0);
    expect(result.entries[0].regions!.every((region) => region.regionIndex === null)).toBe(true);
    expect(result.lineage).toEqual([]);
    bundle.world_state.civilizations[0].name = "Renamed empire";
    expect(civilizationHistory(bundle, 1, 0).name).toBeNull();
  });
  it("keeps separately stored named leadership events without inventing timeline records", () => {
    const bundle = comparisonBundle();
    bundle.events_timeline = [];
    bundle.named_events = [{ name: "Recorded coup", turn: 0, event_type: "coup", actors: ["A"], region: null, description: "Recorded change of ruler", importance: 8 },
      { name: "Future coup", turn: 2, event_type: "coup", actors: ["A"], region: null, description: "Future ruler", importance: 8 }];
    const result = civilizationHistory(bundle, 1, 0);
    expect(result.entries[0].events).toHaveLength(1);
    expect(result.entries[0].events[0]).toMatchObject({ timelineEvent: null, inspectable: false, event: { name: "Recorded coup" } });
    expect(result.entries[0].events[0].source).toContain("named_events");
  });
  it("rejects invalid indices/turns without borrowing another identity", () => {
    for (const index of [-1, 99, 0.5]) expect(civilizationHistory(comparisonBundle(), 2, index).entries).toEqual([]);
    expect(civilizationHistory(comparisonBundle(), 0, 0).name).toBeNull();
  });
});
