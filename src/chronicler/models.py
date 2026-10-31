"""Core data models for the Chronicler civilization simulator."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from chronicler.artifact_io import atomic_write_json


class TechEra(str, Enum):
    TRIBAL = "tribal"
    BRONZE = "bronze"
    IRON = "iron"
    CLASSICAL = "classical"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    INFORMATION = "information"


class Disposition(str, Enum):
    HOSTILE = "hostile"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class ActionType(str, Enum):
    DEVELOP = "develop"
    TRADE = "trade"
    WAR = "war"
    FORTIFY = "fortify"
    RESEARCH = "research"
    COLONIZE = "colonize"


class Region(BaseModel):
    name: str
    terrain: str
    carrying_capacity: int
    resources: str
    controller: str | None = None
    population: int = 0
    x: float | None = None
    y: float | None = None
    soil: float = 0.8
    water: float = 0.6
    forest_cover: float = 0.3
    majority_belief: int = 0xFF
    cultural_identity: str | None = None


class Leader(BaseModel):
    name: str
    trait: str
    reign_start: int
    succession_type: str = "founder"
    predecessor_name: str | None = None
    rival_leader: str | None = None
    rival_civ: str | None = None
    secondary_trait: str | None = None
    agent_id: int | None = None
    dynasty_id: int | None = None


class GreatPerson(BaseModel):
    name: str
    role: str
    trait: str
    civilization: str
    origin_civilization: str | None = None
    born_turn: int
    source: str = "system"
    agent_id: int | None = None
    active: bool = True
    arc_summary: str | None = None
    arc_type: str | None = None
    dynasty_id: int | None = None
    parent_id_0: int | None = None
    parent_id_1: int | None = None


class Civilization(BaseModel):
    name: str
    population: int
    military: int
    economy: int
    culture: int
    stability: int
    leader: Leader
    treasury: int = 0
    asabiya: float = 0.5
    tech_era: TechEra = TechEra.TRIBAL
    trait: str = "cautious"
    regions: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    capital_region: str | None = None
    great_persons: list[GreatPerson] = Field(default_factory=list)
    traditions: list[str] = Field(default_factory=list)
    folk_heroes: list[str] = Field(default_factory=list)
    cultural_milestones: list[str] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    leader_name_pool: list[str] | None = None
    decline_turns: int = 0
    stats_sum_history: list[int] = Field(default_factory=list)
    founded_turn: int = 0
    active_focus: str | None = None
    civ_majority_faith: int = 0xFF
    previous_majority_faith: int = 0xFF
    civ_stress: int = 0
    secession_occurred_count: int = 0
    capital_lost_count: int = 0
    is_vassal: bool = False
    is_fallen_empire: bool = False
    in_twilight: bool = False
    federation_name: str | None = None
    prestige: int = 0
    active_crisis: bool = False
    last_income: int = 0
    active_trade_routes: int = 0


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    treaties: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0
    allied_turns: int = 0


class Event(BaseModel):
    turn: int
    event_type: str
    actors: list[str]
    description: str
    importance: int = 5
    region: str | None = None


class NamedEvent(BaseModel):
    name: str
    event_type: str
    turn: int
    actors: list[str]
    region: str | None = None
    description: str
    importance: int = 5


class ActiveCondition(BaseModel):
    type: str
    severity: int
    duration: int


class AgentEventRecord(BaseModel):
    turn: int
    agent_id: int
    event_type: str
    region: int
    target_region: int
    civ_affinity: int
    occupation: int
    belief: int | None = None
    target_agent_id: int = 0
    formed_turn: int = 0


class WorldState(BaseModel):
    name: str
    seed: int
    turn: int = 0
    regions: list[Region] = Field(default_factory=list)
    civilizations: list[Civilization] = Field(default_factory=list)
    relationships: dict[str, dict[str, Relationship]] = Field(default_factory=dict)
    events_timeline: list[Event] = Field(default_factory=list)
    named_events: list[NamedEvent] = Field(default_factory=list)
    used_leader_names: list[str] = Field(default_factory=list)
    action_history: dict[str, list[str]] = Field(default_factory=dict)
    scenario_name: str | None = None
    agent_events_raw: list[AgentEventRecord] = Field(default_factory=list)
    agent_mode: str | None = None
    tuning_overrides: dict[str, float] = Field(default_factory=dict)
    climate_phase: str = "temperate"
    active_conditions: list[ActiveCondition] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)

    def save(self, path: Path) -> None:
        """Serialize to JSON via an atomic replace."""
        atomic_write_json(Path(path), self.model_dump(mode="json"))

    @classmethod
    def load(cls, path: Path) -> "WorldState":
        """Load from a JSON file."""
        import json
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"No saved state at {path}")
        return cls.model_validate(json.loads(path.read_text()))


# --- Narrative models ---


class NarrativeRole(str, Enum):
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"


class CausalLink(BaseModel):
    cause_turn: int
    cause_event_type: str
    effect_turn: int
    effect_event_type: str
    pattern: str


class GapSummary(BaseModel):
    turn_range: tuple[int, int]
    event_count: int
    top_event_type: str
    stat_deltas: dict[str, dict[str, int]]
    territory_changes: int


class NarrativeMoment(BaseModel):
    anchor_turn: int
    turn_range: tuple[int, int]
    events: list[Event] = Field(default_factory=list)
    named_events: list[NamedEvent] = Field(default_factory=list)
    score: float
    causal_links: list[CausalLink] = Field(default_factory=list)
    narrative_role: NarrativeRole
    bonus_applied: float = 0.0


class ChronicleEntry(BaseModel):
    turn: int
    covers_turns: tuple[int, int]
    events: list[Event] = Field(default_factory=list)
    named_events: list[NamedEvent] = Field(default_factory=list)
    narrative: str
    importance: float
    narrative_role: NarrativeRole
    causal_links: list[CausalLink] = Field(default_factory=list)


# --- Snapshot models ---


class CivSnapshot(BaseModel):
    population: int
    military: int
    economy: int
    culture: int
    stability: int
    treasury: int
    asabiya: float
    tech_era: TechEra
    trait: str
    regions: list[str]
    leader_name: str
    alive: bool
    last_income: int = 0
    active_trade_routes: int = 0
    is_vassal: bool = False
    is_fallen_empire: bool = False
    in_twilight: bool = False
    federation_name: str | None = None
    prestige: int = 0
    capital_region: str | None = None
    great_persons: list[dict] = Field(default_factory=list)
    traditions: list[str] = Field(default_factory=list)
    folk_heroes: list[str] = Field(default_factory=list)
    active_crisis: bool = False
    civ_stress: int = 0
    active_focus: str | None = None
    last_action: str | None = None
    max_precap_weight: float = 0.0
    urban_agents: int = 0
    urban_fraction: float = 0.0
    gini: float = 0.0
    factions: dict | None = None
    governance: dict | None = None


class RelationshipSnapshot(BaseModel):
    disposition: str
    trade_volume: int = 0
    allied_turns: int = 0


class SettlementSnapshot(BaseModel):
    settlement_id: int
    name: str
    region_name: str
    founding_turn: int
    population_estimate: int


class TurnSnapshot(BaseModel):
    turn: int
    civ_stats: dict[str, CivSnapshot]
    region_control: dict[str, str | None]
    relationships: dict[str, dict[str, RelationshipSnapshot]]
    trade_routes: list = Field(default_factory=list)
    active_wars: list = Field(default_factory=list)
    embargoes: list = Field(default_factory=list)
    ecology: dict = Field(default_factory=dict)
    mercenary_companies: list = Field(default_factory=list)
    vassal_relations: list = Field(default_factory=list)
    federations: list = Field(default_factory=list)
    proxy_wars: list = Field(default_factory=list)
    exile_modifiers: list = Field(default_factory=list)
    capitals: dict = Field(default_factory=dict)
    peace_turns: int = 0
    region_cultural_identity: dict = Field(default_factory=dict)
    movements_summary: list = Field(default_factory=list)
    stress_index: int = 0
    pandemic_regions: list = Field(default_factory=list)
    climate_phase: str = ""
    active_conditions: list = Field(default_factory=list)
    settlement_count: int = 0
    candidate_count: int = 0
    active_settlements: list = Field(default_factory=list)
    founded_this_turn: list = Field(default_factory=list)
    dissolved_this_turn: list = Field(default_factory=list)
    settlement_source_turn: int = 0
    urban_agent_count: int = 0
    urban_fraction: float = 0.0
    food: dict | None = None
    migration: list = Field(default_factory=list)
    epidemics: dict | None = None
    finance: dict | None = None
    diplomacy: dict | None = None
    techniques: dict | None = None
    maritime: dict | None = None
    campaign: dict | None = None
    contact: dict | None = None
    nomads: dict | None = None
    gp_agendas: dict | None = None
    historiography: dict | None = None
    languages: dict | None = None
    scholarship: dict | None = None
    grain_reserves: dict | None = None
    cities: dict | None = None
    agent_movements: dict | None = None
    guilds: dict | None = None
