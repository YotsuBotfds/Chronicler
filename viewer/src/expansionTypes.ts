/** Optional per-turn observations. Missing fields are unknown history, not zero. */
export interface HealthCareRegion {
  region: number;
  region_name: string;
  civ: number | null;
  civ_name: string | null;
  episodes: number;
  new_injuries: number;
  recoveries: number;
  impaired_work: number;
  care_work: number;
  care_recipients: number;
  recovery_progress: number;
  cared_recovery_progress: number;
}

export interface HealthCareSnapshot {
  source_turn: number;
  units: "worker-turns";
  episodes: number;
  new_injuries: number;
  recoveries: number;
  impaired_work: number;
  care_work: number;
  care_recipients: number;
  recovery_progress?: number;
  cared_recovery_progress?: number;
  regions: HealthCareRegion[];
}

export interface HarvestForecastReport {
  id: string;
  source_region: number;
  source_region_name: string;
  recipient_region: number;
  recipient_region_name: string;
  owner: number;
  owner_name: string;
  issued_turn: number;
  delivery_turn: number;
  expires_turn: number;
  target_start: number;
  target_end: number;
  probability: number;
  confidence: number;
  predicted_ratio: number;
  status: string;
  delivered_turn: number | null;
  resolved_turn: number | null;
  outcome_shortfall: boolean | null;
  observed_ratio: number | null;
  brier: number | null;
  issued_event_id?: string;
  delivered_event_id?: string;
}

export interface HarvestPreparedness {
  region: number;
  region_name: string;
  owner: number;
  owner_name: string;
  forecast_id: string;
  base_target: number;
  extra_target: number;
  /** Actual received purchases and payments in this completed tick, not excess caused by a warning. */
  bought_during_warning: number;
  paid_during_warning: number;
}

export interface HarvestForecastSnapshot {
  source_turn: number;
  reports: HarvestForecastReport[];
  outcomes: HarvestForecastReport[];
  preparedness: HarvestPreparedness[];
  counters: Record<string, number>;
  /** Five probability bins, each [count, probability sum, observed shortfalls]. */
  calibration: Array<[number, number, number]>;
}

export interface RitualGatheringSchedule {
  gathering_id: string;
  region: number;
  region_name: string;
  cadence: number;
  season_step: number;
  next_turn: number;
  last_turn: number | null;
  last_status: string | null;
}

export interface RitualGatheringOutcome {
  gathering_id: string;
  turn: number;
  region: number;
  region_name: string;
  host: number;
  host_name: string | null;
  faith: number | null;
  faith_name: string | null;
  purpose: string;
  status: "held" | "cancelled";
  reason: string | null;
  attendee_ids: number[];
  food: number;
  funds: number;
  contact_units: number;
  bond_ops: number;
}

export interface RitualGatheringsSnapshot {
  source_turn: number;
  schedules: RitualGatheringSchedule[];
  outcomes: RitualGatheringOutcome[];
  counters: Record<string, number>;
}

export interface ScientificContext {
  crop: string;
  soil_band: number;
  water_band: number;
  season: number;
  climate_phase: string;
  crew: number;
  protocol: string;
}

export interface ScientificProposition {
  id: number;
  recipe: string;
  origin_seat: number;
  context: ScientificContext;
  threshold: number;
  proposed_turn?: number;
  event_id?: string;
  /** Full canonical protocol is recorded only by finite research agendas. */
  metric?: string;
  comparator?: number;
  intervention?: number;
  horizon?: number;
}

export interface ScientificBelief {
  seat: number;
  seat_name: string;
  region: number;
  region_name: string;
  owner: number;
  owner_name: string | null;
  claim: number;
  confidence: number;
  independent_groups: number;
  last_evidence_turn: number | null;
  last_evidence_event_id?: string;
}

export interface ScientificTrial {
  id: number;
  claim: number;
  seat: number;
  payer: number;
  funded_turn: number;
  completion_turn: number;
  resolved_turn: number | null;
  cost: number;
  parent: number;
  method: string;
  source_data: string;
  environment_block: string;
  dependence_group: string;
  inputs: { context?: ScientificContext; region?: number; name?: string; turn?: number; environment?: string };
  control_output: number;
  treatment_output: number;
  observed_control: number | null;
  observed_treatment: number | null;
  informative: boolean;
  supports: boolean | null;
  status: "running" | "completed" | "cancelled" | "failed";
  reason: string;
  event_id?: string;
  funded_event_id?: string;
}

export interface ScientificAllocation {
  seat: number;
  region: number;
  recipe: string;
  share: number;
  confidence: number;
  /** Whole seat expense appears on its first row; other rows carry zero. */
  paid: number;
  event_id?: string;
  /** Actual topic used at payment, independent of later end-turn beliefs. */
  claim_id?: number | null;
}

export interface ScientificResearchCycle {
  id: number;
  legacy_adopted: boolean;
  opening_roster_complete: boolean;
  opened_turn: number | null;
  origin_seat: number;
  participants: number[];
  claims: number[];
  trials: number[];
  announcement_event_id: string;
  closed_turn: number | null;
  close_reason: string;
  unfunded_originals: number[];
  unfunded_replications: number[];
  slot_reasons: Record<string, string>;
  original_deadline: number | null;
  funding_deadline: number | null;
  next_open_not_before: number | null;
  opening_roster_scope: "observed_at_legacy_activation" | "frozen_at_actual_opening";
}

export type ResearchCapacityKey = "topics" | "trials" | "proposals" | "receipts" | "messages" | "cycles" | "seats";

export interface ScientificResearchAgendas {
  schema_version: 1;
  rule: "finite-retained-v1";
  enabled: boolean;
  enabled_turn: number;
  current_cycle_id: number | null;
  next_open_turn: number;
  opening_interval: 25;
  funding_window: 24;
  original_window: 12;
  effort_started_turn: number | null;
  effort_cadence: 6;
  paid_use_seasons: number[];
  origin_cursor: number;
  blocked_reason: string;
  blocked_turn: number | null;
  capacity: Record<ResearchCapacityKey, { used: number; reserved: number; limit: number }>;
  archive: {
    retained_topics: number;
    retained_trials: number;
    retained_proposals: number;
    retained_receipts: number;
    raw_records_retained: true;
    trial_details_scope: "resolved_this_source_turn_only";
    historical_export_completeness: "not_inferred";
  };
  cycles: ScientificResearchCycle[];
}

export interface ScientificClaimsSnapshot {
  source_turn: number;
  /** Omitted by legacy current-context-v1 exports; future values remain explicit unknowns. */
  publication_rule?: string;
  active: boolean;
  seats: number;
  claims: number;
  trials: number;
  completed: number;
  cancelled: number;
  failed: number;
  trial_spent: number;
  effort_spent: number;
  evidence_receipts: number;
  pending_messages: number;
  expired_messages: number;
  withheld_results: number;
  controls: { withhold_information: boolean; transmission_enabled: boolean; uninformative_tests: boolean };
  propositions: ScientificProposition[];
  beliefs: ScientificBelief[];
  trials_resolved: ScientificTrial[];
  allocations: ScientificAllocation[];
  /** Absent legacy metadata preserves the single-cohort reader behavior. */
  research_agendas?: ScientificResearchAgendas;
}

export type { TransactionReceiptsSnapshot } from "./transactionTypes";
