// --- Enums (matching Python str enums) ---

export type TechEra =
  | "tribal"
  | "bronze"
  | "iron"
  | "classical"
  | "medieval"
  | "renaissance"
  | "industrial"
  | "information";

export type Disposition =
  | "hostile"
  | "suspicious"
  | "neutral"
  | "friendly"
  | "allied";

export type ActionType =
  | "expand"
  | "develop"
  | "trade"
  | "diplomacy"
  | "war"
  | "build"
  | "embargo"
  | "move_capital"
  | "fund_instability"
  | "explore"
  | "invest_culture";

// --- Core entities ---

export interface Region {
  name: string;
  terrain: string;
  carrying_capacity: number;
  population?: number;
  resources: string;
  controller: string | null;
  x: number | null;
  y: number | null;
  cultural_identity?: string | null;
  foreign_control_turns?: number;
  adjacencies?: string[];
  ecology?: {
    soil: number;
    water: number;
    forest_cover: number;
  };
  stockpile?: {
    goods: Record<string, number>;
  };
  infrastructure?: Array<{
    type: string;
    builder_civ: string;
    built_turn: number;
    active: boolean;
    faith_id?: number;
  }>;
  role?: string;
  settlements?: Array<{
    settlement_id: number;
    name: string;
    region_name: string;
    population_estimate: number;
    status: string;
  }>;
}

export interface Leader {
  name: string;
  trait: string;
  reign_start: number;
  alive: boolean;
  succession_type: string;
  predecessor_name: string | null;
  rival_leader: string | null;
  rival_civ: string | null;
  secondary_trait: string | null;
}

export interface FactionState {
  influence: Record<string, number>;
  power_struggle?: boolean;
  power_struggle_turns?: number;
}

export interface Civilization {
  name: string;
  population: number;
  military: number;
  economy: number;
  culture: number;
  stability: number;
  tech_era: TechEra;
  treasury: number;
  domains: string[];
  values: string[];
  leader: Leader;
  goal: string;
  regions: string[];
  asabiya: number;
  cultural_milestones: string[];
  action_counts: Record<string, number>;
  leader_name_pool: string[] | null;
  prestige?: number;
  capital_region?: string | null;
  last_income?: number;
  peak_region_count?: number;
  decline_turns?: number;
  traditions?: string[];
  active_focus?: string | null;
  factions?: FactionState;
  war_weariness?: number;
  peace_momentum?: number;
  civ_majority_faith?: number;
  founded_turn?: number;
}

export interface Relationship {
  disposition: Disposition;
  treaties: string[];
  grievances: string[];
  trade_volume: number;
}

export interface Event {
  turn: number;
  event_type: string;
  actors: string[];
  description: string;
  consequences: string[];
  importance: number;
}

export interface NamedEvent {
  name: string;
  event_type: string;
  turn: number;
  actors: string[];
  region: string | null;
  description: string;
  importance: number;
}

// --- Snapshot types ---

export interface CivSnapshot {
  population: number;
  military: number;
  economy: number;
  culture: number;
  stability: number;
  treasury: number;
  asabiya: number;
  asabiya_variance?: number;
  tech_era: TechEra;
  trait: string;
  regions: string[];
  leader_name: string;
  alive: boolean;
  last_income?: number;
  active_trade_routes?: number;
  is_vassal?: boolean;
  is_fallen_empire?: boolean;
  in_twilight?: boolean;
  federation_name?: string | null;
  gini?: number;
  urban_agents?: number;
  urban_fraction?: number;
  prestige?: number;
  capital_region?: string | null;
  great_persons?: Array<Record<string, unknown>>;
  traditions?: string[];
  folk_heroes?: Array<Record<string, unknown>>;
  active_crisis?: boolean;
  civ_stress?: number;
  active_focus?: string | null;
  factions?: FactionState | null;
  action_counts?: Record<string, number>;
  last_action?: string | null;
  war_weariness?: number;
  peace_momentum?: number;
}

export interface RelationshipSnapshot {
  disposition: string;
}

export interface TurnSnapshot {
  turn: number;
  civ_stats: Record<string, CivSnapshot>;
  region_control: Record<string, string | null>;
  relationships: Record<string, Record<string, RelationshipSnapshot>>;
  trade_routes?: Array<[string, string]>;
  active_wars?: Array<[string, string]>;
  embargoes?: Array<[string, string]>;
  ecology?: Record<string, Record<string, number>>;
  mercenary_companies?: Array<Record<string, unknown>>;
  vassal_relations?: Array<Record<string, unknown>>;
  federations?: Array<Record<string, unknown>>;
  proxy_wars?: Array<Record<string, unknown>>;
  exile_modifiers?: Array<Record<string, unknown>>;
  capitals?: Record<string, string>;
  peace_turns?: number;
  region_cultural_identity?: Record<string, string | null>;
  movements_summary?: Array<Record<string, unknown>>;
  stress_index?: number;
  pandemic_regions?: string[];
  climate_phase?: string;
  active_conditions?: Array<Record<string, unknown>>;
  settlement_count?: number;
  candidate_count?: number;
  total_settlement_population?: number;
  active_settlements?: Array<Record<string, unknown>>;
  urban_agent_count?: number;
  urban_fraction?: number;
}

// --- World state ---

export interface WorldState {
  name: string;
  seed: number;
  turn: number;
  regions: Region[];
  civilizations: Civilization[];
  relationships: Record<string, Record<string, Relationship>>;
  events_timeline: Event[];
  named_events: NamedEvent[];
  scenario_name: string | null;
}

// --- Bundle ---

export interface BundleMetadata {
  seed: number;
  total_turns: number;
  generated_at: string;
  sim_model: string;
  narrative_model: string;
  scenario_name: string | null;
  interestingness_score: number | null;
  bundle_version?: number;
  narrator_mode?: string;
}

export interface Bundle {
  world_state: WorldState;
  history: TurnSnapshot[];
  events_timeline: Event[];
  named_events: NamedEvent[];
  chronicle_entries: BundleChronicle;
  gap_summaries?: GapSummary[];
  era_reflections: Record<string, string>;
  metadata: BundleMetadata;
}

// --- Live mode types ---

export interface PauseContext {
  turn: number;
  reason: string;
  valid_commands: string[];
  injectable_events: string[];
  settable_stats: string[];
  civs: string[];
}

export type CommandType = "continue" | "inject" | "set" | "fork" | "quit" | "speed";

export interface InjectCommand {
  type: "inject";
  event_type: string;
  civ: string;
}

export interface SetCommand {
  type: "set";
  civ: string;
  stat: string;
  value: number;
}

export interface SimpleCommand {
  type: "continue" | "fork" | "quit";
}

export interface SpeedCommand {
  type: "speed";
  value: number;
}

export type Command = InjectCommand | SetCommand | SimpleCommand | SpeedCommand;

export interface PendingAction {
  id: string;
  command: Command;
  status: "staged" | "sent";
  detail?: string;
}

export interface AckMessage {
  type: "ack";
  command: string;
  detail: string;
  still_paused: boolean;
  civ?: string;
  stat?: string;
  value?: number;
}

export interface ForkedMessage {
  type: "forked";
  save_path: string;
  cli_hint: string;
}

// --- Setup lobby types ---

export interface ScenarioInfo {
  file: string;
  name: string;
  description: string;
  world_name: string;
  civs: { name: string; values: string[] }[];
  regions: { name: string; terrain: string; x: number | null; y: number | null }[];
}

export interface LobbyInit {
  scenarios: ScenarioInfo[];
  models: string[];
  defaults: {
    turns: number;
    civs: number;
    regions: number;
    seed: number | null;
  };
}

export interface StartCommand {
  type: "start";
  scenario: string | null;
  turns: number;
  seed: number | null;
  civs: number;
  regions: number;
  sim_model: string;
  narrative_model: string;
  resume_state: WorldState | null;
}

// --- M20a: Narration Pipeline v2 types ---

export interface NewChronicleEntry {
  turn: number;
  covers_turns: [number, number];
  events: Event[];
  named_events: NamedEvent[];
  narrative: string;
  importance: number;
  narrative_role: "inciting" | "escalation" | "climax" | "resolution" | "coda";
  causal_links: CausalLink[];
}

export interface GapSummary {
  turn_range: [number, number];
  event_count: number;
  top_event_type: string;
  stat_deltas: Record<string, Record<string, number>>;
  territory_changes: number;
}

export interface CausalLink {
  cause_turn: number;
  cause_event_type: string;
  effect_turn: number;
  effect_event_type: string;
  pattern: string;
}

// --- M20b: Batch Runner types ---

export interface BatchConfig {
  seed_start: number;
  seed_count: number;
  turns: number;
  simulate_only: boolean;
  parallel: boolean;
  workers: number | null;
  tuning_overrides: Record<string, number> | null;
}

export interface BatchReport {
  metadata: {
    runs: number;
    turns_per_run: number;
    seed_range: [number, number];
    checkpoints: number[];
    timestamp: string;
    version: string;
    report_schema_version: number;
    tuning_file: string | null;
  };
  stability: {
    percentiles_by_turn: Record<string, PercentileData>;
    zero_rate_by_turn: Record<string, number>;
  };
  resources: Record<string, unknown>;
  politics: Record<string, unknown>;
  climate: Record<string, unknown>;
  memetic: Record<string, unknown>;
  great_persons: Record<string, unknown>;
  emergence: Record<string, unknown>;
  general: Record<string, unknown>;
  event_firing_rates: Record<string, number>;
  anomalies: AnomalyFlag[];
  run_summaries?: BatchRunSummary[];
}

export interface PercentileData {
  min: number;
  p10: number;
  p25: number;
  median: number;
  p75: number;
  p90: number;
  max: number;
}

export interface AnomalyFlag {
  name: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  detail: string;
}

export interface BatchRunSummary {
  rank: number;
  seed: number | null;
  interestingness_score: number | null;
  dominant_faction: string;
  war_count: number;
  collapse_count: number;
  named_event_count: number;
  tech_advancement_count: number;
  major_event_count: number;
  signal_flags: string[];
  bundle_path: string;
}

export type BundleChronicle =
  | Record<string, string>       // legacy: turn → text
  | NewChronicleEntry[];          // new: sparse entries

export function isLegacyBundle(
  chronicle: BundleChronicle,
): chronicle is Record<string, string> {
  return !Array.isArray(chronicle);
}
