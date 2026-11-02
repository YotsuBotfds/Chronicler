import { comparisonBundle } from "./completedRunHistory";
import type { Bundle } from "../types";

export function regionalFixture(): Bundle {
  const bundle = comparisonBundle();
  bundle.history.forEach((snapshot) => {
    snapshot.regional_population = { schema_version: 1, mode: "shadow", source_turn: snapshot.turn - 1,
      completed_turn: snapshot.turn, timing: "completed_turn", counts: [100, 200],
      sources: ["python_region_state", "uncontrolled_region_state"], agent_counts: [5, 7],
      agent_source: "native_region_alive_count", food_weights: { source: "phase2_agent_pool",
        source_turn: snapshot.turn - 1, timing: "phase2_entry", counts: [10, 90], controller_ids: [0, 1] } };
  });
  return bundle;
}
