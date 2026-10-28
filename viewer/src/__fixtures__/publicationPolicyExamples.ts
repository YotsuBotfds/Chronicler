/** Synthetic reader-only metadata examples; zero observations, no runtime qualification or production fallback. */
import type { TurnSnapshot } from "../types";

export function publicationPolicyExample(publication_rule: string): TurnSnapshot {
  return { turn: 2, civ_stats: {}, region_control: {}, relationships: {}, scientific_claims: {
    source_turn: 1, publication_rule, active: false, seats: 0, claims: 0, trials: 0, completed: 0,
    cancelled: 0, failed: 0, trial_spent: 0, effort_spent: 0, evidence_receipts: 0, pending_messages: 0,
    expired_messages: 0, withheld_results: 0,
    controls: { withhold_information: false, transmission_enabled: true, uninformative_tests: false },
    propositions: [], beliefs: [], trials_resolved: [], allocations: [],
  } };
}
