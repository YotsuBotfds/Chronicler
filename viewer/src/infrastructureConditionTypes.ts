/**
 * Record types of B3 infrastructure condition (`--infrastructure-condition`,
 * `livelihoods.infrastructure_condition`, schema 1, stage "B3"). Kept out of
 * the pinned `types.ts`; the strict reader is `lib/infrastructureCondition.ts`.
 */

export const INFRA_MODES = ["repair", "record_only", "wear_only", "cost_only"] as const;
export const INFRA_WORK_MODES = ["repair", "cost_only"] as const;
export const INFRA_KINDS = ["irrigation", "roads"] as const;
export const INFRA_LIVE = ["serving", "failed"] as const;
export const INFRA_TERMINAL = ["inactive", "destroyed"] as const;
export const INFRA_END_CAUSES = ["scorch", "earthquake", "depopulation", "unknown", "record_removed"] as const;
export const INFRA_REASONS = ["no_timber", "no_coins", "no_labor", "no_envelope", "granary_first"] as const;
export const INFRA_DAMAGE_EVENTS = ["conquest", "sack", "flood"] as const;

export type InfraMode = typeof INFRA_MODES[number];
export type InfraKind = typeof INFRA_KINDS[number];
export type InfraReason = typeof INFRA_REASONS[number];
/** `[turn, event, civ, milli]`. */
export type InfraHistoryEntry = [number, string, number, number];

export interface InfraAsset {
  aid: number;
  kind: InfraKind;
  region: number;
  record_index: number;
  built_turn: number;
  builder_civ: string;
  opened_turn: number;
  condition: number;
  status: "serving" | "failed" | "inactive" | "destroyed";
  status_turn: number;
  cause: string | null;
  responsible: number;
  wear: number;
  damage: number;
  credited: number;
  failed_turn: number | null;
  /** Irrigation: food lost over L9's horizon without repair (observed each Phase 10); null when unobserved. */
  food_at_risk: number | null;
  history: InfraHistoryEntry[];
  /** What consumers read (1.0 in record_only and for a terminal asset). */
  service: number;
  /** `min(1, condition / 0.5)` whatever the mode (0 for a terminal asset). */
  condition_service: number;
}

export interface InfraWork {
  wid: number;
  aid: number;
  kind: InfraKind;
  region: number;
  cause: string;
  status: "open" | "completed" | "abandoned";
  opened_turn: number;
  opened_condition: number;
  controller: number;
  scope: number;
  delivered: number;
  credited: number;
  timber_used: number;
  coin_cost_milli: number;
  work_turns: number;
  stalled_turns: number;
  stalls: Partial<Record<InfraReason, number>>;
  damages: number[];
  war_key: string | null;
  war_start_turn: number | null;
  closed_turn: number | null;
  closed_reason: string | null;
  history: InfraHistoryEntry[];
}

export interface InfraDamage {
  did: number;
  turn: number;
  aid: number;
  kind: InfraKind;
  region: number;
  event: string;
  war_key: string | null;
  war_start_turn: number | null;
  ref: string | null;
  amount: number;
  condition_before: number;
  condition_after: number;
  work: number | null;
}

export interface InfraReceipt {
  turn: number;
  wid: number;
  aid: number;
  kind: InfraKind;
  region: number;
  payer: number;
  status: "progress" | "stalled";
  reasons: InfraReason[];
  requested: number;
  delivered: number;
  credited: number;
  granary_request: number;
  shared: boolean;
  timber_held: number;
  timber_used: number;
  timber_returned: number;
  coin_cost_milli: number;
  envelope: number | null;
  condition_before: number;
  condition_after: number;
  remaining_after: number;
}

export interface InfraLedger {
  turn: number;
  civ: number;
  works: number;
  work_delivered: number;
  timber_used: number;
  coin_cost_milli: number;
  charged: number;
  prepaid_before_milli: number;
  prepaid_after_milli: number;
  envelope: number | null;
  rs2_charged: number;
}

export interface InfraUnmet {
  aid: number;
  kind: InfraKind;
  region: number;
  condition: number;
  reason: string;
}

export interface InfraRecord {
  schema_version: 1;
  stage: "B3";
  mode: InfraMode;
  source_turn: number;
  works_enabled: boolean;
  units: Record<string, string | number>;
  assets: InfraAsset[];
  terminal: InfraAsset[];
  works: InfraWork[];
  closed: InfraWork[];
  damages: InfraDamage[];
  receipts: InfraReceipt[] | null;
  ledger: InfraLedger[] | null;
  unmet: InfraUnmet[] | null;
  shared: number[] | null;
  prepaid: Record<string, number>;
  sink_milli: number;
  counters: Record<string, number>;
  parameters: Record<string, unknown>;
}

/**
 * `disabled`: the run never recorded the switch; `absent`: on in the run,
 * missing at this snapshot (unknown); `malformed`: unreadable, with the
 * reason; `ok` with the frame: `settled` (this turn's Phase 2 receipts),
 * `unsettled` (a work mode without a settled Phase 2: unknown, not zero) or
 * `no_works` (record_only and wear_only open no works).
 */
export type InfraReading =
  | { status: "disabled" }
  | { status: "absent" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; frame: "settled" | "unsettled" | "no_works"; record: InfraRecord };

/** One asset's condition at each readable snapshot of the run. */
export interface InfraConditionPoint { turn: number; condition: number; status: InfraAsset["status"] }

/** The run's most stalled work: the "underfunded public works" story, directly recorded. */
export interface InfraWorksStory {
  work: InfraWork;
  asset: InfraAsset | null;
  /** Snapshot at which the work was last seen. */
  seen_turn: number;
  /** The turn the asset failed (condition 0), if it did while the run was read. */
  failed_turn: number | null;
  stalls: Array<[InfraReason, number]>;
}
