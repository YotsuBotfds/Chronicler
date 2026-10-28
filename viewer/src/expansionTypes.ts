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
