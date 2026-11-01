/** Small constructed comparison fixture; never presented as simulation evidence. */
import sample from "./sample_bundle.json";
import type { Bundle, CivSnapshot, TurnSnapshot } from "../types";

export function comparisonSnapshot(turn: number): TurnSnapshot {
  const civ = (name: string, population: number, treasury: number): CivSnapshot => ({
    population, treasury, economy: population / 10, military: 1, culture: 1, stability: 50,
    asabiya: 0.5, tech_era: "tribal", trait: "cautious", leader_name: name, alive: true, regions: [name],
  });
  return { turn, civ_stats: { A: civ("A", 20, 10), B: civ("B", 80, 30),
    Fallen: { ...civ("Fallen", 9000, 9000), alive: false, regions: [] } },
  region_control: { A: "A", B: "B" }, relationships: {}, active_wars: [["A", "B"], ["B", "A"]],
  food: { sufficiency: [0.5, 1.5], aid: [] },
  finance: { civs: {
    A: { debt: 10, foreign_debt: 5, revenue: 2 }, B: { debt: 30, foreign_debt: 9, revenue: 6 },
    Fallen: { debt: 9000, foreign_debt: 9000, revenue: 9000 },
  } as unknown as NonNullable<TurnSnapshot["finance"]>["civs"], loans: 2, totals: { issued_foreign: 1000 } } };
}

export function comparisonBundle(turns = [1, 2, 3]): Bundle {
  const bundle = structuredClone(sample) as unknown as Bundle;
  bundle.metadata = { ...bundle.metadata, total_turns: turns.at(-1) ?? 0, bundle_version: 5 };
  bundle.world_state = { ...bundle.world_state, name: "Constructed comparison fixture", turn: turns.at(-1) ?? 0,
    regions: bundle.world_state.regions.slice(0, 2).map((region, index) => ({ ...region, name: index ? "B" : "A", controller: index ? "B" : "A" })),
    civilizations: bundle.world_state.civilizations.slice(0, 2).map((row, index) => ({ ...row, name: index ? "B" : "A", regions: [index ? "B" : "A"], population: 99999 })) };
  bundle.history = turns.map(comparisonSnapshot);
  const event = { turn: 0, event_type: "war_declared", actors: ["A", "B"], description: "Fixture conflict",
    consequences: [], importance: 5, event_id: "fixture-war" };
  bundle.events_timeline = [event, { ...event }, { ...event, turn: 2, event_type: "battle", event_id: "fixture-battle" }];
  bundle.named_events = [];
  return bundle;
}
