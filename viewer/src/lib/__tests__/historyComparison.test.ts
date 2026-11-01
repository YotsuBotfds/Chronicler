import { describe, expect, it } from "vitest";
import source from "../../__fixtures__/systems_bundle.json";
import type { Bundle, CivSnapshot, Event, TurnSnapshot } from "../../types";
import { changeEvents, compareReadings, comparisonEntities, comparisonTurns, exactSnapshot,
  largestRelativeChanges, readEntityTurn, type HistoryEntity } from "../historyComparison";

const A = { kind: "civilization", name: "A" } as const;
const B = { kind: "civilization", name: "B" } as const;
const North = { kind: "region", name: "North" } as const;
const baseRow = Object.values(source.history[0].civ_stats)[0] as CivSnapshot;
const baseFinance = Object.values(source.history[0].finance.civs)[0];
const row = (population: number, treasury: number, regions: string[], alive = true): CivSnapshot =>
  ({ ...baseRow, population, treasury, regions, alive });

export function comparisonFixture(): Bundle {
  const bundle = structuredClone(source) as unknown as Bundle;
  bundle.world_state.regions = [{ ...bundle.world_state.regions[0], name: "North", population: 99999 },
    { ...bundle.world_state.regions[1], name: "South" }];
  bundle.world_state.civilizations = [{ ...bundle.world_state.civilizations[0], name: "A", population: 99999 },
    { ...bundle.world_state.civilizations[1], name: "B", population: 77777 }];
  const snapshot = (turn: number, civ_stats: Record<string, CivSnapshot>): TurnSnapshot => ({
    turn, civ_stats, region_control: { North: "A", South: null }, relationships: {},
    food: { sufficiency: [0.5, 1], aid: [] }, ecology: { North: { soil: 0.5, water: 0, forest_cover: 0.2 } },
  });
  bundle.history = [snapshot(1, { A: row(100, 10, ["North", "North"]) }),
    snapshot(3, { A: row(150, 0, ["North", "South"]) }),
    snapshot(5, { A: row(0, 0, [], false), B: row(60, 20, ["South"]) }),
    snapshot(6, { B: row(70, 25, ["South"]) }),
    snapshot(9, { Future: row(999, 999, ["North"]) })];
  bundle.history[0].finance = { civs: { A: { ...baseFinance, debt: 12, foreign_debt: 5 } }, loans: 2, totals: {} };
  bundle.history[1].finance = { civs: { A: { ...baseFinance, debt: 17, foreign_debt: 10 } }, loans: 2, totals: {} };
  bundle.metadata.total_turns = 9;
  bundle.events_timeline = [];
  return bundle;
}
const values = (bundle: Bundle, entity: HistoryEntity = A, turn = 1) => Object.fromEntries(
  readEntityTurn(bundle, entity, turn).metrics.map((metric) => [metric.id, metric.value]));
const event = (turn: number, event_type: string, extra: Partial<Event> = {}): Event => ({
  turn, event_type, actors: ["A"], description: `${event_type} at ${turn}`, importance: 5, consequences: [], ...extra,
});

describe("exact-turn comparison", () => {
  it("reads source endpoints, unique territory and total debt without foreign double counting", () => {
    const bundle = comparisonFixture();
    const first = values(bundle), last = values(bundle, A, 3);
    expect(first).toMatchObject({ population: 100, treasury: 10, territory: 1, debt: 12, food: 0.5, short: 1 });
    expect(last).toMatchObject({ population: 150, treasury: 0, territory: 2, debt: 17, food: 0.75, short: 1 });
    const changes = compareReadings(readEntityTurn(bundle, A, 1), readEntityTurn(bundle, A, 3));
    expect(changes.find((metric) => metric.id === "debt")).toMatchObject({ before: 12, after: 17, delta: 5 });
    expect(changes.find((metric) => metric.id === "population")).toMatchObject({ delta: 50, percent: 50 });
    expect(largestRelativeChanges(changes).map((metric) => metric.id)).toEqual(["territory", "treasury", "population"]);
  });

  it("never fills sparse/missing/duplicate snapshots or births and extinctions with final or stale values", () => {
    const bundle = comparisonFixture();
    expect(values(bundle, A, 2).population).toBeNull();
    expect(readEntityTurn(bundle, B, 1).status).toBe("No record yet");
    expect(values(bundle, B, 1).population).toBeNull();
    expect(readEntityTurn(bundle, A, 6).status).toBe("Fallen; no row at this turn");
    expect(values(bundle, A, 6).population).toBeNull();
    expect(values(bundle, A, 5).population).toBe(0); // Measured zero is preserved.
    bundle.history.push(structuredClone(bundle.history[0]));
    expect(exactSnapshot(bundle, 1)).toBeNull();
    expect(comparisonTurns(bundle, 6)).toEqual([3, 5, 6]);
    expect(values(bundle).population).toBeNull();
  });

  it("limits entities and available endpoints to the selected turn", () => {
    const bundle = comparisonFixture();
    expect(comparisonTurns(bundle, 4)).toEqual([1, 3]);
    expect(comparisonEntities(bundle, 4).filter((entity) => entity.kind === "civilization")).toEqual([A]);
    expect(comparisonEntities(bundle, 6).filter((entity) => entity.kind === "civilization")).toEqual([A, B]);
  });

  it("keeps incomplete food, missing finance and regional population unknown", () => {
    const bundle = comparisonFixture();
    bundle.history[1].food!.sufficiency[1] = null;
    delete bundle.history[1].finance;
    expect(values(bundle, A, 3)).toMatchObject({ food: null, short: null, debt: null });
    const region = readEntityTurn(bundle, North, 1);
    expect(region.metrics.find((metric) => metric.id === "population")?.value).toBeNull();
    expect(region.metrics.find((metric) => metric.id === "water")?.value).toBe(0);
    expect(region.controller).toBe("A");
    bundle.history[0].region_control.North = null;
    expect(readEntityTurn(bundle, North, 1).controller).toBe("Uncontrolled");
    delete bundle.history[0].region_control.North;
    expect(readEntityTurn(bundle, North, 1).controller).toBe("Not recorded");
  });

  it("requires granary demand evidence for targets, and never adds duplicate region records", () => {
    const bundle = comparisonFixture();
    const granary = { region: 0, region_name: "North", owner: 0, owner_name: "A", controller: "A", grain: 0, target: 0, observed: 0 };
    bundle.history[0].grain_reserves = { source_turn: 0, granaries: [granary], flows: [], counters: {} };
    const reading = () => Object.fromEntries(readEntityTurn(bundle, North, 1).metrics.map((metric) => [metric.id, metric.value]));
    expect(reading()).toMatchObject({ grain: 0, target: null });
    granary.observed = 1;
    expect(reading()).toMatchObject({ grain: 0, target: 0 });
    bundle.history[0].grain_reserves.granaries.push({ ...granary });
    expect(reading()).toMatchObject({ grain: null, target: null });
  });

  it("links explicitly attributed events in (from,to] after their completed simulation tick", () => {
    const bundle = comparisonFixture();
    const war = event(2, "war", { region: "North", event_id: "war-2" });
    bundle.events_timeline = [event(0, "trade"), war, { ...war }, event(3, "war", { event_id: "next-tick" }),
      event(3, "occupational_injury", { region: "North" }), event(9, "war", { region: "North" }),
      event(2, "noise", { actors: ["Other"], description: "A North mentioned only in prose" })];
    expect(changeEvents(bundle, A, 1, 3, 3).map((row) => row.event.event_type)).toEqual(["war"]);
    expect(changeEvents(bundle, North, 1, 3, 3).map((row) => row.event.event_type)).toEqual(["war"]);
    expect(changeEvents(bundle, North, 3, 4, 4).map((row) => row.visibleTurn)).toEqual([4]);
    expect(changeEvents(bundle, North, 3, 4, 3)).toEqual([]);
  });

  it("keeps distinct legacy events and disables ambiguous inspector keys", () => {
    const bundle = comparisonFixture();
    bundle.events_timeline = [event(2, "war"), event(2, "war", { description: "Another recorded battle" })];
    const matches = changeEvents(bundle, A, 1, 3, 3);
    expect(matches).toHaveLength(2);
    expect(matches.every((row) => !row.canPin)).toBe(true);
  });

  it("does not mutate sources and leaves missing or zero-baseline percentages undefined", () => {
    const bundle = comparisonFixture();
    bundle.history.reverse();
    const before = JSON.stringify(bundle);
    const changes = compareReadings(readEntityTurn(bundle, A, 5), readEntityTurn(bundle, A, 6));
    expect(changes.find((metric) => metric.id === "population")).toMatchObject({ before: 0, after: null, delta: null, percent: null });
    const zero = compareReadings(readEntityTurn(bundle, A, 5), readEntityTurn(bundle, A, 3));
    expect(zero.find((metric) => metric.id === "treasury")?.percent).toBeNull();
    expect(JSON.stringify(bundle)).toBe(before);
  });
});
