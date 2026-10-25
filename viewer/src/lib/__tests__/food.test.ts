import { describe, expect, it } from "vitest";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, Event, TurnSnapshot } from "../../types";
import {
  aidFlows, DEARTH_COLOR, FAMINE_COLOR, famineRows, faminesAt, famineSpans, foodCrisisSpans, foodSeries,
  hasFamineRecord, hasFoodRecord, hasMigrationRecord, migrationFlows, netMigration, spansOfKind, sufficiencyByRegion,
} from "../food";

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const names = systems.world_state.regions.map((region) => region.name);

function famine(turn: number, region: string | null, episode: Event["episode"], type = "famine"): Event {
  return { turn, event_type: type, region, episode, actors: [], description: "", consequences: [], importance: 5 };
}

function snap(turn: number, extra: Partial<TurnSnapshot> = {}): TurnSnapshot {
  return { turn, civ_stats: {}, region_control: {}, relationships: {}, ...extra };
}

describe("famine spans", () => {
  it("opens a span at onset, counts repeat reports and closes it at the recorded end", () => {
    const spans = famineSpans([
      famine(2, "A", "onset"),
      famine(4, "A", "tick"),
      famine(5, "B", "onset"),
      famine(9, "A", "end", "famine_ended"),
      famine(11, "A", "onset"),
      famine(12, null, "onset"),
      famine(13, "C", "tick"),
    ]);
    expect(spans.map((span) => [span.region, span.start, span.end, span.reports, span.kind])).toEqual([
      ["A", 2, 9, 2, "famine"], ["B", 5, null, 1, "famine"], ["A", 11, null, 1, "famine"],
    ]);
    // A bundle written before the labels reads the same through the labelled spans.
    expect(foodCrisisSpans([
      famine(2, "A", "onset"), famine(4, "A", "tick"), famine(9, "A", "end", "famine_ended"),
    ])).toEqual(spans.filter((span) => span.region === "A" && span.start === 2));
    expect(faminesAt(spans, 8).map((span) => span.region)).toEqual(["A", "B"]);
    expect(faminesAt(spans, 9).map((span) => span.region)).toEqual(["B"]);
    const rows = famineRows(spans, ["B", "A"], 20);
    expect(rows.map((row) => row.id)).toEqual(["B", "A"]);
    expect(rows[1].segments.map((segment) => [segment.start, segment.end])).toEqual([[2, 9], [11, 21]]);
    expect(rows[1].segments[1].label).toContain("still running");
  });

  it("splits one episode where a dearth deepens into famine and eases back", () => {
    const events = [
      famine(0, "A", "onset", "dearth"),
      famine(5, "A", "tick", "dearth"),
      famine(10, "A", "tick", "famine"),
      famine(15, "A", "tick", "famine"),
      famine(20, "A", "tick", "dearth"),
      famine(30, "A", "end", "famine_ended"),
      famine(3, "B", "onset", "dearth"),
      famine(12, "B", "end", "dearth_ended"),
      famine(6, "C", "tick", "famine"),
    ];
    const spans = foodCrisisSpans(events);
    expect(spans.map((span) => [span.region, span.kind, span.start, span.end, span.reports])).toEqual([
      ["A", "dearth", 0, 10, 2], ["B", "dearth", 3, 12, 1], ["A", "famine", 10, 20, 2], ["A", "dearth", 20, 30, 1],
    ]);
    expect(famineSpans(events).map((span) => [span.start, span.end])).toEqual([[10, 20]]);
    expect(spansOfKind(faminesAt(spans, 11), "dearth").map((span) => span.region)).toEqual(["B"]);
    expect(hasFamineRecord([famine(0, "A", "onset", "dearth")])).toBe(true);
    const row = famineRows(spans, ["A", "B"], 40)[0];
    expect(row.segments.map((segment) => segment.color)).toEqual([DEARTH_COLOR, FAMINE_COLOR, DEARTH_COLOR]);
    expect(row.segments[0].label).toContain("A: dearth, turns 0-9");
  });

  it("finds famine records only where events carry region and episode", () => {
    expect(hasFamineRecord(systems.events_timeline)).toBe(true);
    expect(hasFamineRecord(sample.events_timeline)).toBe(false);
    const spans = famineSpans(systems.events_timeline);
    expect(spans.length).toBeGreaterThan(0);
    expect(spans.every((span) => span.end === null || span.end > span.start)).toBe(true);
  });
});

describe("food field", () => {
  it("reads sufficiency and relief convoys by region index", () => {
    expect(hasFoodRecord(systems.history)).toBe(true);
    expect(hasFoodRecord(sample.history)).toBe(false);
    const withAid = systems.history.find((snapshot) => (snapshot.food?.aid.length ?? 0) > 0) ?? null;
    expect(withAid).not.toBeNull();
    const [donor, recipient, amount] = withAid!.food!.aid[0];
    expect(aidFlows(withAid, names)[0]).toEqual({ from: names[donor], to: names[recipient], amount });
    const values = sufficiencyByRegion(withAid, names);
    const observed = withAid!.food!.sufficiency.filter((value) => value !== null).length;
    expect(values.size).toBe(observed);
    expect(sufficiencyByRegion(null, names).size).toBe(0);
  });

  it("counts regions short of food (a gap without the field), in dearth and in famine per snapshot", () => {
    const history = [
      snap(1, { food: { sufficiency: [0.4, 1.2, null], aid: [] } }),
      snap(2),
    ];
    const spans = foodCrisisSpans([famine(1, "A", "onset"), famine(2, "B", "onset", "dearth")]);
    expect(foodSeries(history, spans)).toEqual([
      { turn: 1, "Short of food": 1, "In dearth": 0, "In famine": 1 },
      { turn: 2, "Short of food": null, "In dearth": 1, "In famine": 1 },
    ]);
  });
});

describe("migration field", () => {
  it("sums agent moves over a trailing window and nets them per region", () => {
    const history = [
      snap(1, { migration: [[0, 1, 5]] }),
      snap(2, { migration: [[0, 1, 2], [1, 2, 3]] }),
      snap(3, { migration: [[2, 0, 1]] }),
    ];
    const flows = migrationFlows(history, 2, 2, ["A", "B", "C"]);
    expect(flows).toEqual([{ from: "A", to: "B", amount: 7 }, { from: "B", to: "C", amount: 3 }]);
    expect(migrationFlows(history, 3, 1, ["A", "B", "C"])).toEqual([{ from: "C", to: "A", amount: 1 }]);
    expect(Object.fromEntries(netMigration(flows))).toEqual({ A: -7, B: 4, C: 3 });
    expect(hasMigrationRecord(systems.history)).toBe(true);
    expect(hasMigrationRecord(sample.history)).toBe(false);
  });
});
