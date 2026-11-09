import type { Bundle, HouseholdMobilitySnapshot } from "../types";
import { exactSnapshot } from "./historyComparison";

const count = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const quantity = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const reasons = ["sufficient", "insufficient", "no_local_distress", "unknown_destination", "on_trip"];

/** Only the exact selected snapshot is eligible. Missing and malformed frames remain unknown. */
export function householdMobilityAt(bundle: Bundle, turn: number): HouseholdMobilitySnapshot | null {
  if (!count(turn) || turn < 1) return null;
  const snapshot = exactSnapshot(bundle, turn);
  const frame = snapshot?.household_mobility;
  if (!frame || frame.schema_version !== 1 || frame.source_turn !== turn - 1 || frame.completed_turn !== turn
    || frame.timing !== "agent_decision_post_consolidation" || typeof frame.mode !== "string"
    || frame.wealth_units !== "native_agent_wealth" || frame.person_units !== "native_agents"
    || frame.passed_means !== "gate_passed_not_observed_move" || !quantity(frame.requirement_per_native_person)
    || ![frame.proposed_groups, frame.proposed_native_persons, frame.passed_groups, frame.passed_native_persons,
      frame.blocked_groups, frame.blocked_native_persons, frame.dropped_samples].every(count)
    || frame.passed_groups + frame.blocked_groups !== frame.proposed_groups
    || frame.passed_native_persons + frame.blocked_native_persons !== frame.proposed_native_persons
    || !Array.isArray(frame.samples) || frame.samples.length > 128
    || frame.samples.length + frame.dropped_samples !== frame.proposed_groups) return null;
  let passedGroups = 0, blockedGroups = 0, passedPeople = 0, blockedPeople = 0;
  for (const row of frame.samples) {
    if (!row || !count(row.group_id) || !count(row.origin_region_id) || !count(row.destination_region_id)
      || !count(row.native_persons) || row.native_persons === 0
      || !(row.local_food_sufficiency === null || finite(row.local_food_sufficiency))
      || !quantity(row.native_adult_liquid_wealth) || !quantity(row.required_liquid)
      || !reasons.includes(row.reason)) return null;
    if (row.reason === "insufficient") { blockedGroups++; blockedPeople += row.native_persons; }
    else { passedGroups++; passedPeople += row.native_persons; }
  }
  if (!Number.isSafeInteger(passedPeople) || !Number.isSafeInteger(blockedPeople)
    || passedGroups > frame.passed_groups || blockedGroups > frame.blocked_groups
    || passedPeople > frame.passed_native_persons || blockedPeople > frame.blocked_native_persons) return null;
  // Each omitted group contains at least one person; an entirely retained
  // category must account for its complete aggregate person count.
  for (const [groups, people] of [[frame.passed_groups - passedGroups, frame.passed_native_persons - passedPeople],
    [frame.blocked_groups - blockedGroups, frame.blocked_native_persons - blockedPeople]]) {
    if (people < groups || (groups === 0 && people !== 0)) return null;
  }
  return frame;
}
