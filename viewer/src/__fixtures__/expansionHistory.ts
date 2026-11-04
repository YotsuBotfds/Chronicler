/** Small explicit observations for history contract tests; never a production fallback. */
import type { HarvestForecastReport, HarvestForecastSnapshot, HealthCareSnapshot, RitualGatheringsSnapshot, TurnSnapshot } from "../types";

export function healthObservation(source_turn = 6): HealthCareSnapshot {
  return { source_turn, units: "worker-turns", episodes: 2, new_injuries: 1, recoveries: 0, impaired_work: 0.75,
    care_work: 0.25, care_recipients: 1, recovery_progress: 0.2, cared_recovery_progress: 0.1,
    regions: [{ region: 0, region_name: "Valley", civ: 0, civ_name: "Old realm", episodes: 2,
      new_injuries: 1, recoveries: 0, impaired_work: 0.75, care_work: 0.25, care_recipients: 1,
      recovery_progress: 0.2, cared_recovery_progress: 0.1 }] };
}

export function report(overrides: Partial<HarvestForecastReport> = {}): HarvestForecastReport {
  return { id: "harvest:0:5", source_region: 1, source_region_name: "Hill", recipient_region: 0,
    recipient_region_name: "Valley", owner: 0, owner_name: "Old realm", issued_turn: 5, delivery_turn: 7,
    expires_turn: 11, target_start: 9, target_end: 11, probability: 0.7, confidence: 0.5,
    predicted_ratio: 0.6, status: "pending", delivered_turn: null, resolved_turn: null,
    outcome_shortfall: null, observed_ratio: null, brier: null, ...overrides };
}

export function forecastObservation(source_turn = 6): HarvestForecastSnapshot {
  return { source_turn, reports: [report()], outcomes: [], preparedness: [],
    counters: { resolved: 0, brier_sum: 0 }, calibration: Array.from({ length: 5 }, (): [number, number, number] => [0, 0, 0]) };
}

export function gatheringObservation(source_turn = 6): RitualGatheringsSnapshot {
  return { source_turn, schedules: [{ gathering_id: "harvest:0", region: 0, region_name: "Valley", cadence: 12,
    season_step: 8, next_turn: 20, last_turn: source_turn, last_status: "held" }],
    outcomes: [{ gathering_id: "harvest:0", turn: source_turn, region: 0, region_name: "Valley", host: 0,
      host_name: "Old realm", faith: 3, faith_name: "The Old Faith", purpose: "harvest", status: "held",
      reason: null, attendee_ids: [11, 22], food: 1.5, funds: 2, contact_units: 1, bond_ops: 2 }],
    counters: { scheduled: 1, held: 1, cancelled: 0, attendees: 2, food: 1.5, funds: 2, contact_units: 1, bond_ops: 2 } };
}

export function expansionSnapshot(turn: number, recorded = true): TurnSnapshot {
  return { turn, civ_stats: {}, region_control: {}, relationships: {}, ...(recorded ? {
    health_care: healthObservation(turn - 1), harvest_forecasts: forecastObservation(turn - 1),
    ritual_gatherings: gatheringObservation(turn - 1),
  } : {}) };
}
