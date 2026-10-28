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
}

export interface ScientificClaimsSnapshot {
  source_turn: number;
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
}

/** Transport support; an empty shape fixture does not qualify merchant finance. */
export interface TransactionReceiptsSnapshot {
  source_turn: number;
  phase: "merchant_mobility";
  complete: boolean;
  mobility_executed: boolean;
  dropped_rows: number;
  max_rows: number;
  active_count: number;
  known_active_count: number;
  counters: Record<string, number>;
  rows: Array<Record<string, unknown>>;
}
