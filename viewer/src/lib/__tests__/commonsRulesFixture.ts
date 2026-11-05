import type { CommonsReceipt, CommonsRulesRecord } from "../commonsRules";

/** Constructed observation for the reader and panel tests; not a simulation run. */
export function receipt(extra: Partial<CommonsReceipt> = {}): CommonsReceipt {
  return { region_id: 0, slot: 0, owner: 1, new: false, status: "rest",
    observation: { turn: 3, stock: 10, capacity: 100, extraction: 2, water_gate_open: true },
    quota: 0, stock_cap: 9.5, required: 2, institution_share: 0, bill: 2, paid: 2, coverage: 1, limit: 0,
    applied: true, possible: true, extraction: 0, binding: true, excess: 0, city: 7, grievance_added: 0.02,
    neighbour_slots: 0, neighbour_open_extraction: 0, raw_imports: 0.5, craft_output: 1.25, farmer_income_modifier: 1.1,
    food_sufficiency: 0.9, ...extra };
}
export function record(extra: Partial<CommonsRulesRecord> = {}): CommonsRulesRecord {
  return { schema_version: 1, units: { timber: "timber_goods", money: "treasury" }, mode: "enforced",
    source_turn: 4, completed_turn: 5,
    parameters: { adopt_below: 0.5, rest_below: 0.25, reopen_at: 0.4, repeal_at: 0.8, quota_share: 1, admin_cost: 2,
      unfunded_limit: 3, idle_limit: 12, cooldown_turns: 12, rule_grievance: 0.02, grievance_ceiling: 0.25 },
    observed: true, receipts: [receipt()],
    decisions: [{ turn: 4, region_id: 1, slot: 0, civ: 2, kind: "repealed", reason: "recovered" }],
    rules: [{ region_id: 0, slot: 0, owner: 1, adopted_turn: 2, status: "rest", unfunded_turns: 0, idle_turns: 0,
      binding_turns: 2, paid: 6, grievance: 0.04, observation: { turn: 3, stock: 10, capacity: 100, extraction: 2, water_gate_open: true } }],
    counters: { adopted: 1, rule_slot_turns: 3, paid: 6, required: 6, binding_turns: 2, excess: 0 }, ...extra };
}
