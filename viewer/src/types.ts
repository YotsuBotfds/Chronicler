import type { HarvestForecastSnapshot, HealthCareSnapshot, RitualGatheringsSnapshot, ScientificClaimsSnapshot, TransactionReceiptsSnapshot } from "./expansionTypes";
export type {
  HarvestForecastReport, HarvestForecastSnapshot, HarvestPreparedness, HealthCareRegion, HealthCareSnapshot,
  RitualGatheringOutcome, RitualGatheringSchedule, RitualGatheringsSnapshot,
  ScientificAllocation, ScientificBelief, ScientificClaimsSnapshot, ScientificContext, ScientificProposition, ScientificTrial,
  TransactionReceiptsSnapshot,
} from "./expansionTypes";
export type { NativeTransactionObservation, PublicPurchaseFrame, PublicPurchaseObservation } from "./transactionTypes";

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
  // Agent migration events (`mass_migration`, `notable_migration`): the
  // largest utility term of the moves (e.g. "frontier", "famine_memory").
  // Absent on bundles written before it and on every other event.
  driver?: string | null;
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
  /** Governance runtime stats; present only while governance is on. */
  governance?: GovernanceSnapshot;
}

/** `civ_stats[civ].governance` (`governance_runtime.governance_snapshot`). */
export interface GovernanceSnapshot {
  institutions: string[];
  institution_legitimacy: number[];
  funding_ratio: number;
  enforcement_cost: number;
  ruler_legitimacy: number;
  political_capital: number;
  legitimacy_sources: Record<string, number>;
  reign_id: string | null;
  ambitions: Array<{ type: string; target: string | null; deadline: number; status: string }>;
  elite_positions: number;
  elite_qualifiers: number;
  office_holders: number;
  frustrated_aspirants: number;
  consumption_index: number;
  mmp: number;
  emp: number;
  sfd: number;
  /** Political stress index (Turchin-style; higher is more unrest). */
  psi: number;
  psi_crisis: boolean;
  institutional_regime: string;
  cycle_phase: string;
  government_form: string;
  selectorate_ratio: number;
  revolts_total: number;
  civil_wars_total: number;
  secession_suppressions: number;
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
  /** Contact and trade-flow ledger summary; present only with the contact ledger. */
  contact?: ContactSnapshot;
  /** Great-person agendas; present only with --gp-agendas. */
  gp_agendas?: GpAgendasSnapshot;
  /** Subsistence modes, herds, tribute and hordes; present only with --nomads. */
  nomads?: NomadsSnapshot;
  /** Living cities, the fallen count and running totals; present only with --cities. */
  cities?: CitiesSnapshot;
  /** Living movements, lasting reforms and running totals; present only with --agent-movements. */
  agent_movements?: AgentMovementsSnapshot;
  /** Living guilds, burgher influence and running totals; present only with --guilds. */
  guilds?: GuildsSnapshot;
  /** Living seats of learning, the fallen count and running totals; present only with --scholarship. */
  scholarship?: ScholarshipSnapshot;
  /**
   * Regional food sufficiency and relief convoys of the completed turn;
   * present only when mutual aid runs on an agent-backed economy (bundles
   * written after the viewer map layers).
   */
  food?: FoodSnapshot;
  /** Public granaries at this snapshot, only with active --grain-reserves. */
  grain_reserves?: GrainReservesSnapshot;
  /** Actual hybrid injury and household-care observations; absent when off. */
  health_care?: HealthCareSnapshot;
  /** Delayed harvest reports and actual preparedness purchases; absent when off. */
  harvest_forecasts?: HarvestForecastSnapshot;
  /** Actual local gatherings, payments and immutable schedules; absent when off. */
  ritual_gatherings?: RitualGatheringsSnapshot;
  /** Contextual institutional claims and paid trials, recorded only when enabled. */
  scientific_claims?: ScientificClaimsSnapshot;
  /** Optional source-dated merchant observations, carried unchanged by transport. */
  transaction_receipts?: TransactionReceiptsSnapshot;
  /**
   * Agent migrations of the completed turn as [from region index, to region
   * index, agents]; present only in hybrid and shadow runs written after the
   * viewer map layers.
   */
  migration?: MigrationFlow[];
}

export interface ContactTradePair {
  a: string;
  b: string;
  trade: number;
  /** How much of a's trade goes through b (0-1), and the reverse. */
  dependence_ab: number;
  dependence_ba: number;
}

export interface ContactSnapshot {
  edges: number;
  contact_pairs: number;
  trade_pairs: number;
  /** Flow added this turn per channel (trade, people, soldiers, pilgrims). */
  inflow: Record<string, number>;
  /** Decayed stock per channel. */
  stock: Record<string, number>;
  top_trade_pairs: ContactTradePair[];
}

export interface GpAgenda {
  gp: string;
  /** general, merchant, prophet or scientist. */
  role: string;
  /** Civilization index in `world_state.civilizations`. */
  civ: number;
  kind: string;
  /** Civ index (trade routes), region name, technique key, era or null, by kind. */
  target: string | null;
  deadline: number;
  renown: number;
}

export interface GpAgendasSnapshot {
  open: GpAgenda[];
  bonds: Record<string, number>;
  /** Running totals: declared, fulfilled, failed, coups, coups_failed. */
  totals: Record<string, number>;
}

export interface NomadsSnapshot {
  /** Living civilization -> sedentary, agro_pastoral or nomadic. */
  modes: Record<string, string>;
  /** Civilization -> herd head on the regions it controls. */
  herds: Record<string, number>;
  herd_total: number;
  tributes: Array<{ payer: string; recipient: string; amount: number }>;
  hordes: Array<{ name: string; khan: string; members: string[] }>;
  counters: Record<string, number>;
}

/** One living city at a turn (`cities.snapshot_summary`). */
export interface CitySnapshotRow {
  /** The M56a settlement id, the city's identity. */
  id: number;
  name: string;
  region: string | null;
  lord: string | null;
  /** 1 town, 2 city, 3 great city. */
  rank: number;
  residents: number;
  /** Civic purse. */
  wealth: number;
  /** 0 none, 1 market rights, 2 self-government, 3 free city. */
  charter: number;
  unrest: number;
  satisfaction: number | null;
  /** Wares the city made in the turn (2026-10 crafts); absent in older bundles. */
  crafts?: number;
}

export interface CitiesSnapshot {
  cities: CitySnapshotRow[];
  fallen: number;
  /** Running totals (founded, charters, revolts, sacks, dues, commerce, ...). */
  counters: Record<string, number>;
}

/** One living guild at a turn (`guilds.snapshot_summary`; `--guilds`). */
export interface GuildSnapshotRow {
  /** Index in the world's guild list, the guild's identity. */
  id: number;
  name: string;
  /** Settlement id of its city (`CitySnapshotRow.id`). */
  city: number;
  region: string | null;
  /** "craft" or "merchant". */
  kind: string;
  /** Merchants and craftworkers at the reference scale. */
  masters: number;
  /** The guild's purse. */
  wealth: number;
  /** A monopoly on its city's wares (granted with market rights). */
  monopoly: boolean;
  /** A say in civic dues (granted with self-government). */
  say: boolean;
  /** Present while the lord's raised dues last. */
  levy?: boolean;
  /** Index of the guild charter (a lasting reform) it holds. */
  charter?: number;
  /** Index of its living guild movement. */
  movement?: number;
}

export interface GuildsSnapshot {
  guilds: GuildSnapshotRow[];
  dissolved: number;
  /** Burgher faction influence by civ name, for realms that have one. */
  burghers: Record<string, number>;
  /** Running totals (founded, privileges, levies, threats, movements, charters, ...). */
  counters: Record<string, number>;
}

/** One living seat of learning at a turn (`scholarship.snapshot_summary`; `--scholarship`). */
export interface SeatSnapshotRow {
  /** Index in the world's seat list, the seat's identity. */
  id: number;
  name: string;
  /** "academy", "temple school" or "library". */
  kind: string;
  region: string | null;
  /** The region's ruler (an academy's patron). */
  lord: string | null;
  /** 1 modest, 2 renowned, 3 great. */
  level: number;
  /** Scholar body at the reference scale (scholar agents, great scholars, refugees). */
  scholars: number;
  /** Great scholars (great-person scientists) of its ruler teaching there. */
  masters: number;
  /** Scholars come from fallen seats; present while any remain. */
  refugees?: number;
  /** Failed upkeep payments in a row; present while the patron fails to pay. */
  unpaid?: number;
}

export interface ScholarshipSnapshot {
  seats: SeatSnapshotRow[];
  fallen: number;
  /** Running totals (founded, rises, declines, fallen, refuges, carried, upkeep, ...). */
  counters: Record<string, number>;
}

/** One living movement at a turn (`agent_movements.snapshot_summary`). */
export interface MovementSnapshotRow {
  /** Index in the world's movement list, the movement's identity. */
  id: number;
  name: string;
  /** "commons", "liberty", "sect" or "guild" (--guilds). */
  creed: string;
  /** Civ index of the ruler it opposes. */
  target: number;
  /** "gathering", "pressing", "suppressed", "rising" or "satisfied". */
  stage: string;
  members: number;
  /** Members' share of the target realm's adults. */
  strength: number;
  /** Region index of its stronghold, -1 none. */
  stronghold: number;
  martyrs: number;
  /** The great person who leads it (bundles from slice 2 on). */
  leader?: string;
  /** Index of the repealed reform it wants restored. */
  restores?: number;
}

/** A lasting reform in force at a turn. */
export interface ReformSnapshotRow {
  /** Index in the world's reform list. */
  id: number;
  /** "relief", "home_rule" or "toleration". */
  kind: string;
  /** Civ index of the ruler who granted it. */
  civ: number;
  since: number;
  /** Index of the movement that won it. */
  movement: number;
  /** Home rule: the chartered region indices. */
  regions?: number[];
  /** Toleration: the tolerated faith (permanent id; a slot in older bundles). */
  faith?: number;
  /** Toleration of the ruler's own faith: its church reformed. */
  church?: boolean;
  /** The governance institution it enacted or upholds. */
  institution?: string;
}

export interface AgentMovementsSnapshot {
  living: MovementSnapshotRow[];
  ended: number;
  /** Running totals (founded, demands, reforms, risings, repealed, ...). */
  counters: Record<string, number>;
  /** Lasting reforms in force (bundles from slice 2 on). */
  reforms?: ReformSnapshotRow[];
}

/**
 * A faith's permanent identity (`world_state.faiths[id]`): assigned at its
 * founding and never reused, unlike the native slot it holds.
 */
export interface FaithRecord {
  name: string;
  /** null: not determined (a rebuilt record of an older bundle). */
  founded_turn: number | null;
  /** Founding civilization (index). */
  civ: number;
  /** founding, schism, sect (a movement's) or unrecorded. */
  origin: string;
  /** The native slot it holds, or last held. */
  slot: number;
  /** The turn its slot passed to another faith (absent while it holds it). */
  released_turn?: number | null;
  /** Permanent id of the faith it broke from. */
  parent?: number | null;
  /** Region index of a schism. */
  region?: number | null;
  /** A sect's movement (index) and that movement's leader at the schism. */
  movement?: number | null;
  leader?: string | null;
  doctrines?: number[];
  /** Rebuilt from an older record: "reconstructed" or "unresolved" (earlier holders of its slot unknown). */
  legacy?: string | null;
}

/** A movement in the final `world_state.agent_movements` (fields the viewer reads). */
export interface MovementRecord {
  name: string;
  /** Index into commons, liberty, sect. */
  creed: number;
  founded_turn: number;
  home_region: number;
  target: number;
  leader: string;
  peak_members: number;
  demands: number;
  martyrs: number;
  ended_turn: number | null;
  /** Index into `END_LABELS` (0 while living). */
  end: number;
  /** Index of the lasting reform it won, -1 none. */
  reform?: number;
  /** (turn, kind, event id) in order. */
  history: Array<[number, string, string]>;
  /** Members' commonest faith at its last record (a permanent id; a slot in older bundles; 255 none). */
  faith?: number;
  /** A sect's schism: its turn, the church it broke from and the church it became. */
  schism_turn?: number | null;
  schism_from?: number;
  schism_to?: number;
}

/** A lasting reform in the final `world_state.agent_movements` (fields the viewer reads). */
export interface ReformRecord {
  /** Index into relief, home rule, toleration. */
  kind: number;
  civ: number;
  movement: number;
  enacted_turn: number;
  regions: number[];
  faith: number;
  church?: boolean;
  institution: string;
  repealed_turn: number | null;
  /** Index into `REPEAL_LABELS` (0 in force). */
  repeal: number;
  event_id: string;
  repeal_event_id: string;
}

/** A seat of learning in the final `world_state.scholarship` (living or fallen). */
export interface SeatRecord {
  /** Region index. */
  region: number;
  /** 0 academy, 1 temple school, 2 library. */
  kind: number;
  name: string;
  founded_turn: number;
  /** Civ index of the region's ruler at founding (-1 none). */
  founder: number;
  level: number;
  peak_level: number;
  peak_scholars: number;
  /** Great persons who taught there, by name. */
  teachers?: string[];
  fallen_turn: number | null;
  /** Index into "sack", "famine", "persecution", "patronage" (-1 standing). */
  fall_cause: number;
  /** Seat index its scholars fled to (-1 none). */
  refuge: number;
  /** (turn, kind, event id) in order. */
  history: Array<[number, string, string]>;
}

/** A city in the final `world_state.cities` (living or fallen). */
export interface CityRecord {
  settlement_id: number;
  name: string;
  /** Region index. */
  region: number;
  founded_turn: number;
  rank: number;
  peak_rank: number;
  peak_residents: number;
  peak_wealth: number;
  charter: number;
  fallen_turn: number | null;
  fall_cause: string;
  /** (turn, kind, event id) in order. */
  history: Array<[number, string, string]>;
}

export interface FoodSnapshot {
  /** Per region index: food on hand over need (0-2), null where not observed. */
  sufficiency: Array<number | null>;
  /** Relief convoys: [donor region index, recipient region index, food delivered]. */
  aid: Array<[number, number, number]>;
}

/** [from region index, to region index, agents]. */
export type MigrationFlow = [number, number, number];

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
  /** Who funds domestic loans; present only with --domestic-credit. */
  domestic_credit?: DomesticCreditSnapshot;
}

/**
 * Who holds one borrower's debt at the turn boundary
 * (`finance.domestic_credit.holders`, bundles written with --domestic-credit
 * since the holders view). Empty parts are omitted.
 */
export interface DebtHoldersRecord {
  /** Foreign lender civilization -> [principal, rate per turn]. */
  foreign?: Record<string, [number, number]>;
  /** Rate per turn of the domestic line. */
  rate?: number;
  /** Merchants' claims by region name. */
  merchants?: Record<string, number>;
  /** Cities' claims by city name. */
  cities?: Record<string, number>;
  /** Guilds' claims by guild name. */
  guilds?: Record<string, number>;
  /** Debt written off on this civilization so far (cumulative). */
  written_off?: number;
}

export interface DomesticCreditSnapshot {
  /** Outstanding domestic claims of all borrowers by kind of lender (merchants, guild, city, legacy, houses). */
  claims: Record<string, number>;
  /** Per living borrower: its domestic claims by kind of lender, non-zero only. */
  civs: Record<string, Record<string, number>>;
  /** Number of funder claims on open lines. */
  lenders: number;
  /** Merchant credits (or debits) not yet applied to the agents' wealth. */
  merchant_due: number;
  /** Merchants' grievance toward a defaulting lord, by region (0.01 and above). */
  grievance: Record<string, number>;
  /** Per borrower, who holds its debt; absent in older bundles and when nobody owes anything. */
  holders?: Record<string, DebtHoldersRecord>;
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
  /** Final city state (present only with --cities); the viewer reads each city's history. */
  cities?: { cities?: CityRecord[]; fallen?: CityRecord[] } | null;
  /** Final seats of learning, living and fallen (present only with --scholarship). */
  scholarship?: { seats?: SeatRecord[] } | null;
  /** Final movement state (present only with --agent-movements): records and lasting reforms. */
  agent_movements?: { movements?: MovementRecord[]; reforms?: ReformRecord[] } | null;
  /**
   * The live faiths by native slot (`faith_id`) at the end of the run. A slot
   * can pass to a later faith; records name faiths by permanent id
   * (`faiths`), older bundles by slot (lib/faiths rebuilds their identities).
   */
  belief_registry?: Array<{ faith_id: number; name: string; civ_origin?: number }>;
  /** Permanent faith identities (index = id; bundles from docs/integration/permanent-faiths.md on). */
  faiths?: FaithRecord[];
  /**
   * Procedural geography (absent on template worlds); the viewer reads the
   * sea zones' map positions, in the regions' coordinate space.
   */
  geography?: {
    generator?: string;
    sea_zones?: Array<{ name: string; kind?: string; x?: number; y?: number; coastal_regions?: string[] }>;
  } | null;
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

export interface GranarySnapshotRow {
  region: number;
  region_name: string;
  /** Recorded keeper, a civ index; -1 means no public keeper. */
  owner: number;
  owner_name: string | null;
  /** Territorial controller can differ until the next Phase 2 owner settlement. */
  controller: string | null;
  grain: number;
  target: number;
  observed: number;
}

export interface GranaryFlow {
  kind: "bought" | "released" | "spoiled" | "seized" | "abandoned" | "captured";
  region: number;
  amount: number;
  source: number;
  seller: number;
  buyer: number;
  buyer_name: string | null;
  seller_name: string | null;
  sent: number;
  cost: number;
  before: number;
  after: number;
}

export interface GrainReservesSnapshot {
  /** Completed simulation turn: history turn T records source_turn T-1. */
  source_turn: number;
  granaries: GranarySnapshotRow[];
  flows: GranaryFlow[];
  counters: Record<string, number>;
}

export interface Bundle {
  world_state: WorldState;
  /**
   * Bundle version 5 leaves civilizations that are dead at a turn out of
   * that snapshot's civ_stats, capitals and pairwise tables (each keeps its
   * final row in the snapshot of its death); read rows with lib/civRows.
   * Version-6 files store it as deltas (`history_delta`); the loader
   * decodes them into this field (lib/bundleCodec).
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
  /** In-world languages and names (runs with languages on; absent otherwise). */
  languages?: LanguagesField;
  /** The names table of narrated entries' provenance (narrated bundles only). */
  narration_provenance?: { version: number; names: string[] };
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

export type CommandType = "continue" | "inject" | "set" | "fork" | "quit" | "speed" | "checkpoint";

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
  type: "continue" | "fork" | "quit" | "checkpoint";
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

/**
 * The last exact checkpoint the viewer asked for (the live `checkpoint`
 * message). The server names the file, under the run's output directory.
 */
export type CheckpointStatus =
  | { state: "saving" }
  | { state: "saved"; turn: number; path: string; resumeHint: string }
  | { state: "error"; message: string };

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
  /** The facts the narrator was given and what each sentence cites (narrated bundles only). */
  provenance?: PassageProvenance;
}

/**
 * Narration provenance (docs/integration/narration-provenance.md). Fact ids
 * name the bundle's records: `e<i>` is `events_timeline[i]`, `n<i>`
 * `named_events[i]`, `<chronicler>/e<i>` an in-world account, `p<agent id>` a
 * character, `art<id>` an artifact, `s<S>.<what>.<key>` a value of snapshot
 * S, `d<S1>-<S2>.<key>` a change between two snapshots, `w<a>-<b>` the
 * events of turns a..b, `o<T>.<what>` an observation, `L.<kind><ref>` in-world
 * names, `k<j>` the entry's causal_links[j].
 */
export interface PassageProvenance {
  v: number;
  /** "mechanical" (sentences built from the facts) or "llm" (the model's own citations). */
  narrator: string;
  /** The last completed turn the passage narrates. */
  as_of: number;
  /** A bare id (dated as_of), [id, turn] or [id, turn, "r"] (given as retrospective: after the moment). */
  facts: Array<string | [string, number | null] | [string, number | null, string]>;
  /** Characters, civilizations, regions and faiths the facts name (in a file: indices into `narration_provenance.names`). */
  names: Array<string | number>;
  /** [start, end, ids] over the entry's narrative. */
  spans: Array<[number, number, string[]]>;
}

// --- In-world historiography (optional bundle field; docs/integration/historiography.md) ---

export interface HistoriographyChronicler {
  id: string; // "court:<civ index>", "temple:<faith id>" or "seat:<seat index>" (--scholarship)
  kind: "court" | "temple" | "seat" | string;
  name: string; // "the Kethani chronicles"
  civ: number | null;
  civ_name: string | null;
  faith: number | null; // permanent faith id (temple chroniclers; a slot in older bundles)
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

// --- In-world languages and names (optional bundle field; docs/integration/languages.md) ---

/** A sound change: [turn, rule id, description, words changed, spread from (language id) or null, prehistoric]. */
export type LanguageChange = [number, string, string, number, number | null, boolean];

export interface LanguageInfo {
  id: number;
  name: string; // "Kethani", "Proto-Highland", "Iron Peaks Kethani"
  parent: number | null;
  family: number;
  origin: "proto" | "founding" | "prehistory" | "secession" | "separation" | string;
  turn: number;
  status: "living" | "extinct" | "reconstructed" | string;
  last_spoken: number | null;
  style: string;
  civs: number[];
  native: string | null; // its speakers' name for themselves
  phonology: {
    consonants: string;
    vowels: string;
    onsets: string[];
    finals: string;
    syllables: string[];
    order: "mh" | "hm" | string;
    join: string;
    stress: string;
  };
  changes: LanguageChange[];
}

/** One row of ``words``, in the order named by ``word_columns``. */
export type LanguageWordRow = unknown[];

export interface LanguagesField {
  version: number;
  enabled_turn: number;
  counts: Record<string, number>;
  languages: LanguageInfo[];
  word_columns: string[];
  words: LanguageWordRow[];
  /** civ index -> [[turn, language id], ...] */
  civs: Array<{ civ: number; name: string | null; lang: Array<[number, number]> }>;
  /** region index -> speech history and story ([turn, kind, civ index or language id]). */
  regions: Array<{
    region: number;
    name: string | null;
    speech: Array<[number, number]>;
    story: Array<[number, string, number]>;
  }>;
  settlements: Array<{ id: number; name: string; region: number }>;
  faiths: Array<{ faith: number; name: string; civ: number }>;
  persons: Array<{ key: string; name: string; civ: number; role: string }>;
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
