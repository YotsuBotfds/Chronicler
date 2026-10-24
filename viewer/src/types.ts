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

export type NarratorMode = "local" | "api" | "gemini";
export type AgentMode = "off" | "demographics-only" | "shadow" | "hybrid";

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
  // Causal provenance (bundle version 4+; absent on older bundles and on
  // events without provenance). See docs/integration/causal-provenance.md.
  event_id?: string;
  causes?: string[];
  region?: string | null;
  civs?: string[];
  episode?: "onset" | "tick" | "repeat" | "end" | null;
  duration?: number | null;
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
  per_pair_accuracy?: Record<string, Record<string, number>>;
  perception_errors?: Record<string, Record<string, Record<string, number>>>;
  settlement_source_turn?: number;
  settlement_count?: number;
  candidate_count?: number;
  total_settlement_population?: number;
  active_settlements?: Array<Record<string, unknown>>;
  founded_this_turn?: number[];
  dissolved_this_turn?: number[];
  urban_agent_count?: number;
  urban_fraction?: number;
  /** M60 campaign layer; present only when the run enabled --campaigns. */
  campaign?: CampaignSnapshot;
  /** Epidemiology; present only when the run enabled --epidemiology. */
  epidemics?: EpidemicSnapshot;
  /** Money, credit and public finance; present only with --finance. */
  finance?: FinanceSnapshot;
  /** Treaties, pair memory and the vassal ladder; present only with --diplomacy. */
  diplomacy?: DiplomacySnapshot;
  /** Diffusing techniques; present only with --techniques. */
  techniques?: TechniquesSnapshot;
  /** Fleets, sea zones and blockades; present only with --maritime. */
  maritime?: MaritimeSnapshot;
}

// --- Default-off simulation systems (history[n].<field>) ---
// Shapes follow each system's snapshot_summary() in src/chronicler/. Every
// field is optional on TurnSnapshot: bundles without the system omit it.

/** One reportable outbreak: a (region, pathogen) row of the SEIRS table. */
export interface EpidemicOutbreak {
  region: string;
  pathogen: string;
  /** Mean infectious share over the last tick (what the region exports). */
  prevalence: number;
  /** Recovered (immune) share. */
  immune: number;
  /** New infections last tick, in people. */
  cases: number;
  /** Deaths last tick. */
  deaths: number;
  /** The population never had an epidemic of this pathogen. */
  virgin: boolean;
}

export interface EpidemicSnapshot {
  active: EpidemicOutbreak[];
  deaths: number;
  deaths_by_pathogen: Record<string, number>;
  deaths_total: number;
  /** Civilizations whose borders are closed this turn. */
  quarantine: string[];
  /** Pathogen name -> strain count (only mutated pathogens). */
  strains: Record<string, number>;
}

export interface FinanceCivSnapshot {
  debt: number;
  foreign_debt: number;
  revenue: number;
  revenue_ema: number;
  upkeep: number;
  court: number;
  debt_service: number;
  interest: number;
  borrowed: number;
  shortfall: number;
  price_index: number;
  inflation: number;
  fineness: number;
  fiscal_stress: number;
  arrears_turns: number;
  defaults: number;
  debasements: number;
  credit_premium: number;
}

export interface FinanceSnapshot {
  /** Living civilizations only. */
  civs: Record<string, FinanceCivSnapshot>;
  /** Number of open credit lines. */
  loans: number;
  totals: Record<string, number>;
}

export interface DiplomacyTreaty {
  id: number;
  kind: string;
  name: string;
  parties: string[];
  start: number;
  expiry: number | null;
}

export interface DiplomacySubject {
  overlord: string;
  vassal: string;
  /** "client", "vassal" or "union". */
  stage: string | null;
  since: number | null;
  integration: number | null;
}

export interface DiplomacyGrievance {
  holder: string;
  target: string;
  grievance: number;
  trust: number;
  goodwill: number;
  kinds: Record<string, number>;
}

/** Directed pair memory as exported: [trust, total grievance] of holder toward target. */
export type DiplomacyPairMemory = [number, number];

export interface DiplomacySnapshot {
  treaties: DiplomacyTreaty[];
  subjects: DiplomacySubject[];
  /** The five largest grievances between living civilizations. */
  top_grievances: DiplomacyGrievance[];
  counts: Record<string, number>;
  /**
   * Holder -> target -> [trust, total grievance] for every living directed
   * pair with a memory. Absent on bundles written before the viewer panels.
   */
  pairs?: Record<string, Record<string, DiplomacyPairMemory>>;
}

export interface TechniquesSnapshot {
  /** Living civilization -> techniques known. */
  known: Record<string, number>;
  /** Living civilization -> techniques practised widely enough to count toward an era. */
  practised: Record<string, number>;
  /** Rows of the regional practice table. */
  rows: number;
  /** Region -> technique key -> practice share (>= 0.03); absent on older bundles. */
  regions?: Record<string, Record<string, number>>;
}

export interface MaritimeZone {
  zone: string;
  /** "uncontested", "contested" or "controlled". */
  status: string;
  controller: string | null;
  pirates: number;
  /** Civilization -> ships in the zone. */
  ships: Record<string, number>;
  sea_trade: number;
  piracy: number;
}

export interface MaritimeFleet {
  id: number;
  name: string;
  civ: string | null;
  zone: string;
  ships: number;
  mission: string;
}

export interface MaritimeBlockade {
  zone: string;
  blockader: string | null;
  target: string | null;
  since: number;
}

export interface MaritimeSnapshot {
  zones: MaritimeZone[];
  fleets: MaritimeFleet[];
  blockades: MaritimeBlockade[];
  blocked_lanes: number;
  counters: Record<string, number>;
}

export interface CampaignArmy {
  id: string;
  name: string;
  civ: string;
  region: string;
  objective: string | null;
  phase: string;
  soldiers: number;
  morale: number;
  rations: number;
  supply_distance: number | null;
  general: string | null;
  war: string;
  siege_turns: number;
}

export interface CampaignBattle {
  turn: number;
  name: string;
  kind: string;
  region: string;
  war_key: string;
  attacker: string;
  defender: string;
  attacker_soldiers: number;
  defender_soldiers: number;
  attacker_power: number;
  defender_power: number;
  attacker_losses: number;
  defender_losses: number;
  winner: string | null;
  attacker_general: string | null;
  defender_general: string | null;
}

export interface CampaignOccupation {
  region: string;
  owner: string;
  occupier: string;
  war_key: string;
  since_turn: number;
  unrest: number;
  revolts: number;
}

export interface CampaignWar {
  war: string;
  attacker: string;
  defender: string;
  aim: string;
  aim_region: string | null;
  score: number;
  start_turn: number;
  battles: number;
}

export interface CampaignSnapshot {
  armies: CampaignArmy[];
  battles: CampaignBattle[];
  occupations: CampaignOccupation[];
  wars: CampaignWar[];
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
  /** Final maritime state (present only with --maritime); the viewer reads zone ports. */
  maritime?: { zones?: Array<{ name: string; kind?: string; ports?: number[] }> } | null;
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
  narrator_mode?: NarratorMode | string;
}

export interface Bundle {
  world_state: WorldState;
  /**
   * Bundle version 5 leaves civilizations that are dead at a turn out of
   * that snapshot's civ_stats, capitals and pairwise tables (each keeps its
   * final row in the snapshot of its death); read rows with lib/civRows.
   */
  history: TurnSnapshot[];
  /** Version 5: the omitted civ_stats rows as change runs (Python restores them; the viewer does not). */
  pruned_civ_stats?: Record<string, unknown[]>;
  events_timeline: Event[];
  named_events: NamedEvent[];
  chronicle_entries: BundleChronicle;
  gap_summaries?: GapSummary[];
  era_reflections: Record<string, string>;
  metadata: BundleMetadata;
  /** In-world chroniclers' accounts (runs with historiography on; absent otherwise). */
  historiography?: HistoriographyField;
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
  narrator: NarratorMode;
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
  causal_chains?: CausalChain[];
  /** In-world accounts the narration drew on (ids "<chronicler>/<event_id>"). */
  accounts?: string[];
}

// --- In-world historiography (optional bundle field; docs/integration/historiography.md) ---

export interface HistoriographyChronicler {
  id: string; // "court:<civ index>" or "temple:<faith id>"
  kind: "court" | "temple" | string;
  name: string; // "the Kethani chronicles"
  civ: number | null;
  civ_name: string | null;
  faith: number | null;
  founded_turn: number;
  active: boolean;
  archive: string;
  accounts: number;
  surviving: number;
}

export interface HistoriographyArchiveLoss {
  turn: number;
  cause: string; // sack, conquest, collapse, fire, quake, flood, plague, desecration, absorption
  event_id: string;
  region: number | null;
  region_name: string | null;
  copies: number;
  lost: number;
  survived: number;
}

export interface HistoriographyArchive {
  id: string;
  owner: string;
  region: number | null;
  region_name: string | null;
  copies: number;
  status: "intact" | "damaged" | "lost" | "empty" | string;
  losses: HistoriographyArchiveLoss[];
}

/** One row of ``accounts``, in the order named by ``account_columns``. */
export type HistoriographyAccountRow = unknown[];

export interface HistoriographyContested {
  event_id: string;
  divergence: string[]; // silence, lost, outcome, magnitude, blame, divine, ruler
}

export interface HistoriographyField {
  version: number;
  enabled_turn: number;
  counts: Record<string, number>;
  chroniclers: HistoriographyChronicler[];
  archives: HistoriographyArchive[];
  account_columns: string[];
  accounts: HistoriographyAccountRow[];
  /** chronicler id -> event ids it told plainly (no transformation, uncontested). */
  plain: Record<string, string[]>;
  contested: HistoriographyContested[];
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
  cause_id?: string;
  effect_id?: string;
  /** "recorded" (stamped by the simulation) or "pattern" (type-pair fallback; the default). */
  provenance?: "recorded" | "pattern";
}

export interface ChainStep {
  event_id: string;
  turn: number;
  event_type: string;
  description: string;
  region?: string | null;
}

/** A recorded cause-to-effect path, root cause first. */
export interface CausalChain {
  steps: ChainStep[];
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
  civs?: number;
  regions?: number;
  scenario?: string | null;
  sim_model?: string | null;
  narrative_model?: string | null;
  narrator?: NarratorMode;
  agents?: AgentMode;
  preset?: string | null;
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
