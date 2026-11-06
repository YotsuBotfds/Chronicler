/**
 * Constructed productive-recovery observations (timber supply, operating wear,
 * recovery crews, maintenance obligation and RS1 schema 2) to test the readers
 * and panels; not a simulation run. Four regions, two civilizations, source
 * turn 9 (snapshot 10). Every record closes; tests break one identity at a time.
 */
import { apprentice, qualification, receipt as v1Receipt, record as v1Record } from "./apprenticeshipFixture";

// ---------------------------------------------------------------- timber supply
export const liveCutting = { eid: 3, civ: 0, home: 0, forest: 1, slot: 0, hops: 1, launched_turn: 8, status: "live",
  stage: "cutting", stage_turns: 1, travelled: 1, return_hops: 0, arrived: false, crew: [10, 11, 12],
  launched_crew: [10, 11, 12, 13], veterans: [11], need: 1.5, cargo: 2, cut: 2, cut_turns: 1, cut_end: null,
  worked_turns: 2, person_turns: 7, wages_milli: 3500, wage_residual_milli: 0, income_withheld: 1.2,
  away_requested: 5, away_delivered: 5, delivered: 0, lost: 0, abandoned: 0, unpaid_turns: 0, recalled_turn: null,
  ended_turn: null, end_reason: null, drops: [[9, 13, "migrated"]], history: [[8, "launched"], [9, "at_forest"]] };
export const liveRecalled = { ...liveCutting, eid: 4, civ: 1, home: 3, forest: 2, stage: "returning", stage_turns: 0,
  return_hops: 1, crew: [20], launched_crew: [20], veterans: [], cargo: 0.5, cut: 0.5, person_turns: 2,
  wages_milli: 500, income_withheld: 0.4, away_requested: 2, away_delivered: 2, unpaid_turns: 1, recalled_turn: 9,
  drops: [], history: [[7, "launched"], [9, "recalled"]] };
export const delivered = { ...liveCutting, eid: 1, civ: 1, home: 2, forest: 3, status: "delivered", stage: "returning",
  crew: [14, 15], launched_crew: [14, 15], veterans: [], cargo: 0, cut: 3, delivered: 2.97, lost: 0.03,
  person_turns: 6, wages_milli: 3000, away_delivered: 4, away_requested: 4, ended_turn: 7, drops: [] };
export const abandoned = { ...liveCutting, eid: 2, crew: [], launched_crew: [16, 17], veterans: [], cargo: 0, cut: 1,
  abandoned: 1, person_turns: 3, wages_milli: 1500, away_delivered: 2, away_requested: 2, status: "abandoned",
  ended_turn: 9, end_reason: "crew_lost", drops: [[9, 16, "died"], [9, 17, "died"]] };
export const cutReceipt = { turn: 9, eid: 3, civ: 0, home: 0, forest: 1, slot: 0, stage: "cutting", crew: [10, 11, 12],
  veterans: [11], dropped: [[13, "migrated"]], away_requested: 3, away_delivered: 3, crew_labor: 3, cut: 2,
  cargo_after: 2, stock_before: 100, stock_after: 98.5, capacity: 120, wages_due_milli: 1500, wages_milli: 1500,
  wage_residual_milli: 0, income_withheld: 0.6, cut_end: null, unpaid: false, recalled: false };
export const unpaidReceipt = { ...cutReceipt, eid: 4, civ: 1, home: 3, forest: 2, stage: "returning", crew: [20],
  veterans: [], dropped: [], away_requested: 1, away_delivered: 1, crew_labor: 0, cut: 0, cargo_after: 0.5,
  stock_before: null, stock_after: null, capacity: null, wages_due_milli: 0, wages_milli: 0, income_withheld: 0.2,
  unpaid: true, recalled: true };
export const timberLedger = { turn: 9, civ: 0, expeditions: 1, person_turns: 3, wages_due_milli: 1500,
  wages_applied_milli: 1500, wage_residual_milli: 0, charged: 2, prepaid_before_milli: 0, prepaid_after_milli: 500 };
export const needs = [
  { region: 0, civ: 0, want: 4, free: 0.5, store: 0, in_transit: 1.98, gap: 1.52, status: "expedition", reason: null, eid: 3 },
  { region: 1, civ: 1, want: 4, free: 0, store: 0, in_transit: 0, gap: 4, status: "refused", reason: "forest_busy", eid: null },
  { region: 2, civ: 1, want: 1, free: 2.17, store: 2.17, in_transit: 0, gap: 0, status: "supplied", reason: null, eid: null },
];
export const timberSupply = { schema_version: 1, stage: "PL1", mode: "supply", source_turn: 9,
  units: { money: "milli_treasury_units", timber: "goods", labor: "headcount", milli: 1000 },
  expeditions: [liveCutting, liveRecalled], closed: [delivered, abandoned], store: { "2": 2.17 },
  receipts: [cutReceipt, unpaidReceipt], ledger: [timberLedger],
  stores: [{ region: 2, opening: 2.97, held: 1, returned: 0.2, delivered: 0, released: 0, closing: 2.17 }],
  needs, needs_dropped: 0, deposits: [[9, 2, 1, 1]],
  per_expedition: { ended: 2, wages_milli: 2250, person_turns: 4.5, farm_labor_away: 3, unpaid_turns: 0, cut: 2,
    delivered: 1.485 },
  prepaid: { "0": 500 },
  counters: { settled_turns: 9, launched: 4, launched_veterans: 1, delivered_expeditions: 1, ended: 2, cut: 6.5,
    delivered: 2.97, lost: 0.03, abandoned_cargo: 1, released: 0, store_held: 3, store_returned: 0.5,
    wages_due_milli: 9000, wages_milli: 9000, wage_residual_milli: 0, charged: 9, income_withheld: 4,
    away_requested: 12, away_delivered: 12, crew_labor: 9, person_turns: 19, crew_turns_outbound: 6,
    crew_turns_cutting: 9, crew_turns_returning: 4, recalls: 1, unpaid_turns: 1, refused_forest_busy: 3,
    refused_no_forest: 5, abandoned_crew_lost: 1, dropped_migrated: 1, dropped_died: 2, veterans_placed: 2,
    ended_wages_milli: 4500, ended_person_turns: 9, ended_away: 6, ended_cut: 4, ended_delivered: 2.97,
    ended_unpaid_turns: 0 },
  parameters: { crew_cap: 4, max_hops: 2, cut_turns: 3, guard_share: 0.5, min_gap: 0.5, share: 1, wage_milli: 500,
    transit_decay: 0.01 } };

// ---------------------------------------------------------------- operating wear
export const wearReceipts = [
  { turn: 9, site: 0, region: 1, wear: 0.02, upkeep_offset: 0.005, net_wear: 0.015, condition_before: 0.6,
    condition_after: 0.585, qualified_on_crew: [7], full_offset: false },
  { turn: 9, site: 1, region: 2, wear: 0.02, upkeep_offset: 0.02, net_wear: 0, condition_before: 0.9,
    condition_after: 0.9, qualified_on_crew: [8, 9], full_offset: true },
  { turn: 9, site: 2, region: 3, wear: 0.02, upkeep_offset: 0, net_wear: 0.02, condition_before: 0.51,
    condition_after: 0.49, qualified_on_crew: [], full_offset: false },
];
export const operatingWear = { schema_version: 1, stage: "PL2", source_turn: 9, receipts: wearReceipts,
  counters: { turns: 10, operating_site_turns: 20, wear: 0.4, upkeep_offset: 0.1, net_wear: 0.3,
    full_offset_site_turns: 3, covered_site_turns: 8, repairs: 1 },
  parameters: { operating_wear: 0.02 }, with_apprenticeship: true };

// ---------------------------------------------------------------- recovery crews
export const granaryCrew = { turn: 9, pid: 4, kind: "granary", region: 1, payer: 0, eligible: 3, eligible_site_city: null,
  planned: 2, capacity: 1.8, requested: 1.8, delivered: 1.8,
  members: [
    { agent_id: 30, origin: "rural_farmer", share: 1, worked: 1, farm_time: 1, veteran: true, wage_due_milli: 2000,
      wage_milli: 2000, wage_residual_milli: 0, income_replaced: 0.3 },
    { agent_id: 31, origin: "urban_farmer", share: 0.8, worked: 0.8, farm_time: 0.8, veteran: false, wage_due_milli: 1600,
      wage_milli: 1500, wage_residual_milli: 100, income_replaced: 0.2 },
  ],
  coin_cost_milli: 3600, wages_due_milli: 3600, wages_milli: 3500, wage_residual_milli: 100, sunk_milli: 100,
  farm_time_removed: 1.8 };
export const emptyCrew = { ...granaryCrew, pid: 5, region: 2, payer: 1, eligible: 0, planned: 1, capacity: 0,
  requested: 0, delivered: 0, members: [], coin_cost_milli: 0, wages_due_milli: 0, wages_milli: 0,
  wage_residual_milli: 0, sunk_milli: 0, farm_time_removed: 0 };
export const workshopCrew = { turn: 9, pid: 6, kind: "workshop", region: 3, payer: 1, eligible: 9, eligible_site_city: 2,
  planned: 0, capacity: 0, requested: 0.6, delivered: 0.6,
  members: [
    { agent_id: 40, origin: "site_city", share: 0.2, worked: 0.2, farm_time: 0, veteran: false, wage_due_milli: 0,
      wage_milli: 0, wage_residual_milli: 0, income_replaced: 0 },
    { agent_id: 41, origin: "rural_farmer", share: 0.2, worked: 0.2, farm_time: 0.2, veteran: false, wage_due_milli: 0,
      wage_milli: 0, wage_residual_milli: 0, income_replaced: 0.05 },
    { agent_id: 42, origin: "veteran", share: 0.2, worked: 0.2, farm_time: 0, veteran: true, wage_due_milli: 0,
      wage_milli: 0, wage_residual_milli: 0, income_replaced: 0.04 },
  ],
  coin_cost_milli: 0, wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0, sunk_milli: 0, farm_time_removed: 0.2 };
export const recoveryCrews = { schema_version: 1, stage: "PL3", mode: "paid", source_turn: 9,
  units: { money: "milli_treasury_units", work: "work_units", milli: 1000 },
  receipts: [granaryCrew, emptyCrew, workshopCrew],
  ledger: [
    { turn: 9, civ: 0, coin_cost_milli: 3600, wages_due_milli: 3600, wages_milli: 3500, wage_residual_milli: 100, sunk_milli: 100 },
    { turn: 9, civ: 1, coin_cost_milli: 0, wages_due_milli: 0, wages_milli: 0, wage_residual_milli: 0, sunk_milli: 0 },
  ],
  rows_dropped: 0,
  counters: { settled_turns: 9, granary_crews: 6, granary_no_crew: 2, granary_crew_short: 1, granary_crew_person_turns: 11,
    granary_work_planned: 9, granary_work_named: 8.4, granary_coin_cost_milli: 10000, granary_wages_due_milli: 10000,
    granary_wages_milli: 9500, granary_wage_residual_milli: 500, granary_sunk_milli: 500, workshop_crews: 3,
    workshop_crew_person_turns: 9, workshop_members_site_city: 3, workshop_members_rural_farmer: 5,
    workshop_members_veteran: 1, farm_time_removed: 9.5, income_replaced: 2.5, veterans_placed: 4 },
  parameters: { age_adult: 20, min_share: 0.001, granary_coins_per_work: 2, granary_wage_batch: 1, max_frame_rows: 64 } };

// ---------------------------------------------------------------- maintenance obligation
export const decisions = [
  { turn: 9, civ: 0, planned: 6, budget_before: 10, cap: 5, reserved: 5 },
  { turn: 9, civ: 1, planned: 2, budget_before: 30, cap: 15, reserved: 2 },
];
/** The charge split pro rata (PL3 review C): civ 0 pays floor(6 x 4 / 7) = 3 from its reservation. */
export const uses = [
  { turn: 9, civ: 0, reserved: 4, envelope: 3, charged: 6, used: 3, returned: 1, envelope_spent: 3, envelope_share: 3 / 7 },
  { turn: 9, civ: 1, reserved: 3, envelope: null, charged: 1, used: 1, returned: 2, envelope_spent: 0, envelope_share: 0 },
];
export const maintenanceObligation = { schema_version: 1, stage: "PL3", mode: "reserve", source_turn: 9,
  units: { money: "treasury_units" }, decisions, uses,
  counters: { settled_turns: 10, decision_civ_turns: 20, planned_coins: 20, capped_coins: 60, reserved_coins: 15,
    cap_binding: 2, execution_civ_turns: 14, used_coins: 9, returned_coins: 4, envelope_spent_coins: 3, charged_coins: 12 },
  parameters: { max_budget_share: 0.5, group: "maintenance" } };
/** L9's decisions of the same turn: the budget left to bargain after each reservation. */
const budgetDecision = { turn: 9, civ: 0, mode: "bargained", seat: null, projected: 100, floor: 20, obligations: 5,
  committed: 0, budget: 9, influence: {}, burdens: {}, proposals: [], dropped: 0, candidates: {}, satisfaction: {},
  scores: {}, chosen: null, outcome: null, awards: [], refused: [] };
export const localBudgets = { schema_version: 1, stage: "L9", mode: "bargained", source_turn: 9,
  decisions: [budgetDecision, { ...budgetDecision, civ: 1, budget: 29 }], settled: null, responses: null, open: [],
  counters: {}, parameters: { envelope_share: 0.25 } };

// ---------------------------------------------------------------- RS1 schema 2
const v2Fields = { absent: 0, first_site: 0, entry_age: 24, transfers: 0 };
export const crewSeat = { agent_id: 21, new: false, veteran: false, mentor: 7, outcome: "attended", reason: null,
  ending: null, share: 0, income_forgone: null, stipend_due: 0, stipend_paid: 0, stipend_status: null, aboard: "crew" };
export const attachedSeat = { ...crewSeat, agent_id: 22, new: true, veteran: true, share: 0.5, income_forgone: 0.1,
  stipend_due: 125, stipend_paid: 125, stipend_status: "paid", aboard: "attached" };
export const movedSeat = { ...crewSeat, agent_id: 24, outcome: "missed", reason: "no_mentor", mentor: null,
  aboard: undefined, transferred_from: 1 };
export const v2Receipt = { ...v1Receipt, crew: [7, 8, 9, 21], seats: [crewSeat, attachedSeat, movedSeat],
  stipend_status: "paid", graduates_on_crew: [], covered: true, full_offset: false,
  offset_by_via: { apprenticeship: 0, service: 0.01 }, offset_by_graduates: 0 };
export const v2Record = { ...v1Record, schema_version: 2, rules_version: 2,
  qualifications: [qualification, { ...qualification, agent_id: 30, via: "apprenticeship", earned_turn: 3, seen_settlement: 0 }],
  apprenticeships: [
    { ...apprentice, ...v2Fields, on_crew: 2, attached: 1 },
    { ...apprentice, ...v2Fields, agent_id: 22, started_turn: 4, attended: 1, veteran: true, on_crew: 0, attached: 1 },
    { ...apprentice, ...v2Fields, agent_id: 24, attended: 2, gap: 1, interruptions: 1, transfers: 1, on_crew: 1, attached: 1 },
    { ...apprentice, ...v2Fields, agent_id: 25, site: 2, region: 2, settlement_id: 6, attended: 1, gap: 2, absent: 2,
      interruptions: 2, on_crew: 0, attached: 1 },
  ],
  archive: [{ ...apprentice, ...v2Fields, agent_id: 30, status: "completed", ended_turn: 3, ended_reason: "completed",
    granted: true, attended: 10, on_crew: 6, attached: 4 },
  { ...apprentice, ...v2Fields, agent_id: 40, status: "ended", ended_turn: 2, ended_reason: "long_absence", absent: 5,
    on_crew: 3, attached: 0 }],
  graduates: [{ agent_id: 30, completed_turn: 3, site: 0, region: 1, granted: true, crew_turns: 0, upkeep_offset: 0,
    last_crew_turn: null }],
  receipts: [v2Receipt, v1Record.receipts[1]],
  detached: [{ ...crewSeat, agent_id: 25, outcome: "missed", reason: "absent", mentor: null, aboard: undefined }],
  counters: { ...v1Record.counters, miss_away: 0, end_migrated: 0, miss_absent: 3, miss_no_room: 1, end_long_absence: 1,
    transferred: 2, apprentice_turns_on_crew: 4, apprentice_turns_attached: 3, covered_site_turns: 4,
    full_offset_site_turns: 1, qualified_crew_turns: 5, graduate_crew_turns: 0, graduates: 1,
    upkeep_offset_service: 0.04, upkeep_offset_apprenticeship: 0.01 },
  parameters: { per_mentor: 2, per_site: 4, long_absence_turns: 4, completion_turns: 10, operating_wear: 0.02,
    apprentice_fraction: 0.5, max_entry_age: 50 } };

/** A snapshot holding the given livelihoods records (default turn: the fixtures' snapshot 10). */
export const snapWith = (records: Record<string, unknown>, turn = 10) =>
  ({ turn, livelihoods: { schema_version: 1, ...records } });
