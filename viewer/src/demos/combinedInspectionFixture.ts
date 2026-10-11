import type { Event } from "../types";
import type { SettlementSnapshot } from "../lib/settlementInspection";

const quay = { settlement_id: 7, name: "River Quay", region_name: "Alpha Delta", population_estimate: 23,
  centroid_x: 1.25, centroid_y: -2.75, founding_turn: 2, status: "active" };
const ferry = { ...quay, settlement_id: 9, name: "Upper Ferry", region_name: "Alpha Upland",
  population_estimate: 40, centroid_x: 8, centroid_y: 3.125 };
const hill = { ...quay, settlement_id: 21, name: "Hill Watch", region_name: "Beta Ridge",
  population_estimate: 71, centroid_x: -5, centroid_y: 6 };

// Independent hand-authored histories: no producer, terminal world, or inferred join.
// Alpha: no snapshot at 4; Quay dissolves at 5; missing source fields at 6.
// Turns 24/25 retain the unchanged turn-23 Ferry observation and its source label.
export const combinedCivilizations = ["Alpha", "Beta", "Nobody"] as const;
export type ExampleCivilization = typeof combinedCivilizations[number];
export const combinedHistories: Record<ExampleCivilization, readonly SettlementSnapshot[]> = {
  Alpha: Array.from({ length: 32 }, (_, index): SettlementSnapshot | null => {
    const turn = index + 1;
    if (turn === 4) return null;
    if (turn === 6) return { turn, active_settlements: [{ settlement_id: 9, name: ferry.name, region_name: ferry.region_name }] };
    return { turn, settlement_source_turn: turn === 3 ? 2 : turn === 24 || turn === 25 ? 23 : turn,
      active_settlements: turn < 2 ? [] : turn < 5 ? [quay, ferry] : [ferry],
      founded_this_turn: turn === 2 ? [7, 9] : [], dissolved_this_turn: turn === 5 ? [7] : [] };
  }).filter((snapshot): snapshot is SettlementSnapshot => snapshot !== null),
  Beta: Array.from({ length: 32 }, (_, index) => ({ turn: index + 1, settlement_source_turn: index + 1,
    active_settlements: index < 1 ? [] : [hill], founded_this_turn: index === 1 ? [21] : [], dissolved_this_turn: [] })),
  Nobody: [],
};
export const defaultSettlement: Record<ExampleCivilization, number | null> = { Alpha: 7, Beta: 21, Nobody: null };

const event = (turn: number, actors: string[], event_type: string, description: string): Event => ({
  turn, actors, event_type, description, importance: 3, consequences: [],
});
// Source order is deliberate. Alpha's 55-record burst crosses three 24-record pages.
export const combinedEvents: readonly Event[] = [
  event(1, ["Alpha"], "survey", "Alpha river survey recorded."),
  event(2, ["Alpha"], "founding", "Alpha records the founding of River Quay and Upper Ferry."),
  ...Array.from({ length: 55 }, (_, i) => event(3, ["Alpha"], "migration", `Alpha migration record ${i + 1}.`)),
  ...Array.from({ length: 8 }, (_, i) => event(3, ["Beta"], "migration", `Beta migration record ${i + 1}.`)),
  event(3, ["Alpha", "Beta"], "treaty", "Alpha and Beta record a shared river treaty."),
  event(3, [], "weather", "Actorless weather observation; no civilization may backfill it."),
  event(5, ["Alpha"], "dissolution", "Alpha records River Quay dissolution."),
  event(6, ["Alpha"], "survey", "Alpha survey with an incomplete settlement observation."),
  event(23, ["Alpha"], "survey", "Alpha records the turn-23 Ferry survey."),
  event(32, ["Beta"], "survey", "Beta records a turn-32 ridge survey."),
  event(33, ["Alpha", "Beta", "Future civilization"], "future_sentinel", "FUTURE SENTINEL — never visible in the bounded preview."),
];
