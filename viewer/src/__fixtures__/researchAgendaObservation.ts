import producer from "../../../tests/fixtures/scientific_research/source0.json";
import type { TurnSnapshot } from "../types";

/** Actual producer UNIT summary, not a complete world or qualification bundle.
 * Empty core snapshot scaffolding is test-only; never a production fallback.
 * Mutations in reader tests below this seam are synthetic/adversarial cases.
 */
export function researchAgendaObservation(): TurnSnapshot {
  return { ...structuredClone(producer.history[0]), civ_stats: {}, region_control: {}, relationships: {} } as TurnSnapshot;
}

export const researchAgendaEvents = producer.events_timeline;
