// --- Enums (matching Python str enums) ---

export type TechEra =
  | "tribal"
  | "bronze"
  | "iron"
  | "classical"
  | "medieval"
  | "renaissance"
  | "industrial";

export type Disposition =
  | "hostile"
  | "suspicious"
  | "neutral"
  | "friendly"
  | "allied";

export type ActionType = "expand" | "develop" | "trade" | "diplomacy" | "war";

// --- Core entities ---

export interface Region {
  name: string;
  terrain: string;
  carrying_capacity: number;
  resources: string;
  controller: string | null;
  x: number | null;
  y: number | null;
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
  tech_era: TechEra;
  trait: string;
  regions: string[];
  leader_name: string;
  alive: boolean;
}

export interface RelationshipSnapshot {
  disposition: string;
}

export interface TurnSnapshot {
  turn: number;
  civ_stats: Record<string, CivSnapshot>;
  region_control: Record<string, string | null>;
  relationships: Record<string, Record<string, RelationshipSnapshot>>;
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
}

export interface Bundle {
  world_state: WorldState;
  history: TurnSnapshot[];
  events_timeline: Event[];
  named_events: NamedEvent[];
  chronicle_entries: Record<string, string>;
  era_reflections: Record<string, string>;
  metadata: BundleMetadata;
}
