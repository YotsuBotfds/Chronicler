import type { SettlementSnapshot } from "../../../lib/settlementInspection";

const quay = { settlement_id: 7, name: "River Quay", region_name: "Delta", population_estimate: 23,
  centroid_x: 1.25, centroid_y: -2.75, founding_turn: 2, status: "active" };
const ferry = { settlement_id: 9, name: "Upper Ferry", region_name: "Upland", population_estimate: 40,
  centroid_x: 8, centroid_y: 3.125, founding_turn: 2, status: "active" };

// Deliberate gap at 4, dissolution at 5, missing timestamp/fields at 6.
export const settlementDemoHistory: SettlementSnapshot[] = [
  { turn: 1, settlement_source_turn: 1, active_settlements: [], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 2, settlement_source_turn: 2, active_settlements: [quay, ferry], founded_this_turn: [7, 9], dissolved_this_turn: [] },
  { turn: 3, settlement_source_turn: 2, active_settlements: [{ ...quay, population_estimate: 31, centroid_x: 1.5 }, ferry], founded_this_turn: [], dissolved_this_turn: [] },
  { turn: 5, settlement_source_turn: 5, active_settlements: [ferry], founded_this_turn: [], dissolved_this_turn: [7] },
  { turn: 6, active_settlements: [{ settlement_id: 9, name: "Upper Ferry", region_name: "Upland" }] },
];
