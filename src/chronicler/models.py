"""Core data models for the civilization chronicle generator.

WorldState is the single source of truth. All simulation and narrative
modules read from and write to WorldState, which serializes to JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# --- Enums ---

class TechEra(str, Enum):
    TRIBAL = "tribal"
    BRONZE = "bronze"
    IRON = "iron"
    CLASSICAL = "classical"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    INFORMATION = "information"


class Resource(str, Enum):
    GRAIN = "grain"
    TIMBER = "timber"
    IRON = "iron"
    FUEL = "fuel"
    STONE = "stone"
    RARE_MINERALS = "rare_minerals"


class ResourceType(int, Enum):
    """M34: Concrete resource types collapsed by mechanical equivalence."""
    GRAIN = 0
    TIMBER = 1
    BOTANICALS = 2
    FISH = 3
    SALT = 4
    ORE = 5
    PRECIOUS = 6
    EXOTIC = 7


EMPTY_SLOT = 255

# Mechanical class groupings for yield formula dispatch
FOOD_TYPES = frozenset({ResourceType.GRAIN, ResourceType.FISH, ResourceType.BOTANICALS, ResourceType.EXOTIC})
MINERAL_TYPES = frozenset({ResourceType.ORE, ResourceType.PRECIOUS})

# M37: Religion constants
DOCTRINE_THEOLOGY = 0
DOCTRINE_ETHICS = 1
DOCTRINE_STANCE = 2
DOCTRINE_OUTREACH = 3
DOCTRINE_STRUCTURE = 4


class Disposition(str, Enum):
    HOSTILE = "hostile"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"
    CLERGY = "clergy"


class Belief(BaseModel):
    """A faith in the world's belief registry."""
    faith_id: int = Field(ge=0, le=15)
    name: str
    civ_origin: int  # civ index that founded this faith
    doctrines: list[int] = Field(min_length=5, max_length=5)
    # [Theology, Ethics, Stance, Outreach, Structure], each -1/0/+1


class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.25,
            FactionType.MERCHANT: 0.25,
            FactionType.CULTURAL: 0.25,
            FactionType.CLERGY: 0.25,
        }
    )
    power_struggle: bool = False
    power_struggle_turns: int = 0
    power_struggle_cooldown: int = 0  # M19b: turns until next struggle eligible
    pending_faction_shift: str | None = None  # M19b: faction to shift after normalization

    @model_validator(mode="after")
    def _ensure_clergy(self) -> "FactionState":
        if FactionType.CLERGY not in self.influence:
            self.influence[FactionType.CLERGY] = 0.08  # floor
        return self


class ActionType(str, Enum):
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    BUILD = "build"
    EMBARGO = "embargo"
    MOVE_CAPITAL = "move_capital"
    FUND_INSTABILITY = "fund_instability"
    EXPLORE = "explore"
    INVEST_CULTURE = "invest_culture"


class InfrastructureType(str, Enum):
    ROADS = "roads"
    FORTIFICATIONS = "fortifications"
    IRRIGATION = "irrigation"
    PORTS = "ports"
    MINES = "mines"
    TEMPLES = "temples"


class ClimatePhase(str, Enum):
    TEMPERATE = "temperate"
    WARMING = "warming"
    DROUGHT = "drought"
    COOLING = "cooling"


class ActionCategory(str, Enum):
    AUTOMATIC = "automatic"
    DELIBERATE = "deliberate"
    REACTION = "reaction"


class Infrastructure(BaseModel):
    type: InfrastructureType
    builder_civ: str
    built_turn: int
    active: bool = True
    faith_id: int = -1
    temple_prestige: int = 0


class PendingBuild(BaseModel):
    type: InfrastructureType
    builder_civ: str
    started_turn: int
    turns_remaining: int
    faith_id: int = -1


class ClimateConfig(BaseModel):
    period: int = 75
    severity: float = 1.0
    start_phase: ClimatePhase = ClimatePhase.TEMPERATE
    phase_offset: int = 0  # M18: supervolcano advances climate by incrementing this


# --- Core entities ---

class RegionEcology(BaseModel):
    soil: float = Field(default=0.8, ge=0.0, le=1.0)
    water: float = Field(default=0.6, ge=0.0, le=1.0)
    forest_cover: float = Field(default=0.3, ge=0.0, le=1.0)


class River(BaseModel):
    name: str
    path: list[str] = Field(min_length=2)


class Region(BaseModel):
    name: str
    terrain: str  # plains, mountains, coast, forest, desert, tundra
    carrying_capacity: int = Field(ge=1, le=100)
    population: int = Field(default=0, ge=0)
    resources: str  # fertile, mineral, timber, maritime, barren
    controller: Optional[str] = None
    x: float | None = None
    y: float | None = None
    cultural_identity: str | None = None
    foreign_control_turns: int = 0
    adjacencies: list[str] = Field(default_factory=list)
    specialized_resources: list[Resource] = Field(default_factory=list)
    ecology: RegionEcology = Field(default_factory=RegionEcology)
    low_forest_turns: int = 0
    forest_regrowth_turns: int = 0
    infrastructure: list[Infrastructure] = Field(default_factory=list)
    pending_build: PendingBuild | None = None
    famine_cooldown: int = Field(default=0, ge=0)
    role: str = "standard"
    disaster_cooldowns: dict[str, int] = Field(default_factory=dict)
    resource_suspensions: dict[int, int] = Field(default_factory=dict)
    depopulated_since: int | None = None
    ruin_quality: int = 0
    route_suspensions: dict[str, int] = Field(default_factory=dict)
    resource_types: list[int] = Field(default_factory=lambda: [255, 255, 255])
    resource_base_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    resource_reserves: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    river_mask: int = 0
    # M35b: Disease, Depletion & Environmental Events
    disease_baseline: float = 0.01
    endemic_severity: float = 0.01
    soil_pressure_streak: int = 0
    overextraction_streaks: dict[int, int] = Field(default_factory=dict)
    resource_effective_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    capacity_modifier: float = 1.0  # Temporary capacity multiplier (flood=0.85, drought=0.5)
    prev_turn_water: float = -1.0  # Previous turn's water level for delta tracking (-1 = unset)
    # M37: Religion
    conquest_conversion_boost: float = 0.0      # decays over 10 turns
    majority_belief: int = 0xFF                  # computed from snapshot in Phase 10
    conquest_conversion_active: bool = False      # one-shot flag set by action engine
    conversion_rate_signal: float = 0.0          # for bridge
    conversion_target_signal: int = 0xFF         # for bridge
    # M38b: Persecution
    persecution_intensity: float = 0.0         # 0.0 = no persecution; computed in Phase 10
    martyrdom_boost: float = 0.0               # decays linearly, same lifecycle as conquest_conversion_boost
    schism_convert_from: int = 0xFF            # 255 = no schism this turn
    schism_convert_to: int = 0xFF              # 255 = no schism this turn
    last_conquered_turn: int = -1              # -1 = never conquered; set by WAR resolution


class Leader(BaseModel):
    name: str
    trait: str
    reign_start: int
    alive: bool = True
    succession_type: str = "founder"
    predecessor_name: str | None = None
    rival_leader: str | None = None
    rival_civ: str | None = None
    secondary_trait: str | None = None
    grudges: list[dict] = Field(default_factory=list)


class Civilization(BaseModel):
    # NOTE: Field constraints (ge/le) are enforced at construction time only.
    # The simulation engine mutates stats via direct assignment with _clamp()
    # to keep values in-bounds. Do NOT enable validate_assignment=True without
    # updating all mutation sites in simulation.py.
    name: str
    population: int = Field(ge=0, le=1000)
    military: int = Field(ge=0, le=100)
    economy: int = Field(ge=0, le=100)
    culture: int = Field(ge=0, le=100)
    stability: int = Field(ge=0, le=100)
    tech_era: TechEra = TechEra.TRIBAL
    treasury: int = 0
    domains: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    leader: Leader
    goal: str = ""
    regions: list[str] = Field(default_factory=list)
    asabiya: float = Field(default=0.5, ge=0.0, le=1.0)
    cultural_milestones: list[str] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    prestige: int = 0
    leader_name_pool: list[str] | None = None
    capital_region: str | None = None
    last_income: int = 0
    merc_pressure_turns: int = 0
    peak_region_count: int = 0
    decline_turns: int = 0
    stats_sum_history: list[int] = Field(default_factory=list)
    known_regions: list[str] | None = None
    great_persons: list[GreatPerson] = Field(default_factory=list)
    traditions: list[str] = Field(default_factory=list)
    legacy_counts: dict[str, int] = Field(default_factory=dict)
    event_counts: dict[str, int] = Field(default_factory=dict)
    war_win_turns: list[int] = Field(default_factory=list)
    folk_heroes: list[dict] = Field(default_factory=list)
    succession_crisis_turns_remaining: int = 0
    succession_candidates: list[dict] = Field(default_factory=list)
    civ_stress: int = 0  # M18: per-civ stress, recomputed each turn
    regions_start_of_turn: int = 0  # M18: snapshot for regression detection
    was_in_twilight: bool = False  # M18: snapshot for regression detection
    capital_start_of_turn: str | None = None  # M18: snapshot for regression detection
    tech_focuses: list[str] = Field(default_factory=list)  # M21: history of focus values
    active_focus: str | None = None  # M21: current era's focus
    factions: FactionState = Field(default_factory=FactionState)
    founded_turn: int = 0
    max_precap_weight: float = 0.0  # M19b: transient, tracks max weight before 2.5x cap
    civ_majority_faith: int = 0  # M37: computed from agent snapshot each turn
    previous_majority_faith: int = 0           # initialized to civ_majority_faith at world-gen


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    treaties: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0
    allied_turns: int = 0
    trade_contact_turns: int = 0
    disposition_drift: int = 0


class HistoricalFigure(BaseModel):
    name: str
    role: str
    traits: list[str] = Field(default_factory=list)
    civilization: str
    alive: bool = True
    deeds: list[str] = Field(default_factory=list)


class GreatPerson(BaseModel):
    name: str
    role: str  # "general", "merchant", "prophet", "scientist", "exile", "hostage"
    trait: str
    civilization: str
    origin_civilization: str
    alive: bool = True
    active: bool = True
    fate: str = "active"  # "active", "retired", "dead", "ascended", "exile"
    born_turn: int
    death_turn: int | None = None
    deeds: list[str] = Field(default_factory=list)
    region: str | None = None
    captured_by: str | None = None
    is_hostage: bool = False
    hostage_turns: int = 0
    cultural_identity: str | None = None
    movement_id: str | None = None  # NOTE: Movement.id is str, not int
    recognized_by: list[str] = Field(default_factory=list)
    source: str = "aggregate"  # "aggregate" or "agent"
    agent_id: int | None = None
    # M38b: Pilgrimages
    pilgrimage_destination: str | None = None
    pilgrimage_return_turn: int | None = None
    arc_type: str | None = None
    pilgrimage_skill_bonus: float = 0.0


class Event(BaseModel):
    turn: int
    event_type: str
    actors: list[str]
    description: str
    consequences: list[str] = Field(default_factory=list)
    importance: int = Field(default=5, ge=1, le=10)
    source: str = "aggregate"  # "aggregate" or "agent"


class NamedEvent(BaseModel):
    """A historically significant event with a generated name."""
    name: str
    event_type: str  # battle, treaty, cultural_work, tech_breakthrough, coup, legacy, rival_fall
    turn: int
    actors: list[str]
    region: str | None = None
    description: str
    importance: int = Field(default=5, ge=1, le=10)


class ActiveCondition(BaseModel):
    condition_type: str
    affected_civs: list[str]
    duration: int
    severity: int = Field(ge=1, le=100)


class VassalRelation(BaseModel):
    overlord: str
    vassal: str
    tribute_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    turns_active: int = 0


class Federation(BaseModel):
    name: str
    members: list[str]
    founded_turn: int


class ProxyWar(BaseModel):
    sponsor: str
    target_civ: str
    target_region: str
    treasury_per_turn: int = 8
    turns_active: int = 0
    detected: bool = False


class ExileModifier(BaseModel):
    original_civ_name: str
    absorber_civ: str
    conquered_regions: list[str]
    turns_remaining: int = 20
    recognized_by: list[str] = Field(default_factory=list)


class Movement(BaseModel):
    """M16b: An ideological movement that spreads between civilizations."""
    id: str
    origin_civ: str
    origin_turn: int
    value_affinity: str
    adherents: dict[str, int] = Field(default_factory=dict)


class PandemicRegion(BaseModel):
    """Tracks pandemic spread per-region. Part of M18 emergence system."""
    region_name: str
    severity: int  # 1-3, keyed off active infrastructure count
    turns_remaining: int  # 4-6, decrements each turn


class TerrainTransitionRule(BaseModel):
    """Configurable terrain transformation rule for ecological succession."""
    from_terrain: str
    to_terrain: str
    condition: str  # "low_forest" or "forest_regrowth"
    threshold_turns: int  # Consecutive turns before transform triggers


# --- M27: Agent integration data structures ---

@dataclass(slots=True)
class StatChange:
    civ_id: int
    stat: str
    delta: float
    category: str       # "guard", "guard-action", "guard-shock", "signal", "keep"
    stat_at_time: float  # stat value when mutation was recorded


@dataclass
class CivShock:
    civ_id: int
    stability_shock: float = 0.0
    economy_shock: float = 0.0
    military_shock: float = 0.0
    culture_shock: float = 0.0


@dataclass
class DemandSignal:
    civ_id: int
    occupation: int      # 0=farmer, 1=soldier, 2=merchant, 3=scholar, 4=priest
    magnitude: float
    turns_remaining: int  # starts at 3


@dataclass(slots=True)
class AgentEventRecord:
    turn: int
    agent_id: int
    event_type: str
    region: int
    target_region: int
    civ_affinity: int
    occupation: int


# --- Top-level state ---

class WorldState(BaseModel):
    name: str
    seed: int
    turn: int = 0
    regions: list[Region] = Field(default_factory=list)
    civilizations: list[Civilization] = Field(default_factory=list)
    relationships: dict[str, dict[str, Relationship]] = Field(default_factory=dict)
    historical_figures: list[HistoricalFigure] = Field(default_factory=list)
    events_timeline: list[Event] = Field(default_factory=list)
    active_conditions: list[ActiveCondition] = Field(default_factory=list)
    event_probabilities: dict[str, float] = Field(default_factory=dict)
    named_events: list[NamedEvent] = Field(default_factory=list)
    used_leader_names: list[str] = Field(default_factory=list)
    action_history: dict[str, list[str]] = Field(default_factory=dict)
    war_start_turns: dict[str, int] = Field(default_factory=dict)
    scenario_name: str | None = None
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
    mercenary_companies: list[dict] = Field(default_factory=list)
    vassal_relations: list[VassalRelation] = Field(default_factory=list)
    federations: list[Federation] = Field(default_factory=list)
    proxy_wars: list[ProxyWar] = Field(default_factory=list)
    exile_modifiers: list[ExileModifier] = Field(default_factory=list)
    movements: list[Movement] = Field(default_factory=list)
    next_movement_id: int = 0
    peace_turns: int = 0
    balance_of_power_turns: int = 0
    climate_config: ClimateConfig = Field(default_factory=ClimateConfig)
    fog_of_war: bool = False
    retired_persons: list[GreatPerson] = Field(default_factory=list)
    character_relationships: list[dict] = Field(default_factory=list)
    great_person_cooldowns: dict[str, dict[str, int]] = Field(default_factory=dict)
    # M18: Emergence and Chaos
    stress_index: int = 0  # Global stress aggregate (max across civs)
    black_swan_cooldown: int = 0  # Turns until next black swan eligible
    chaos_multiplier: float = 1.0  # Scalar on black swan probability (from ScenarioConfig)
    black_swan_cooldown_turns: int = 30  # Configurable cooldown length (from ScenarioConfig)
    pandemic_state: list[PandemicRegion] = Field(default_factory=list)
    pandemic_recovered: list[str] = Field(default_factory=list)  # Regions already hit; prevents re-infection
    terrain_transition_rules: list[TerrainTransitionRule] = Field(
        default_factory=lambda: [
            TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                                  condition="low_forest", threshold_turns=50),
            TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                                  condition="forest_regrowth", threshold_turns=100),
        ]
    )
    tuning_overrides: dict[str, float] = Field(default_factory=dict)
    # M27: Agent integration
    agent_mode: str | None = None       # None/"off", "demographics-only", "shadow", "hybrid"
    pending_shocks: list = Field(default_factory=list)   # list[CivShock]
    agent_events_raw: list = Field(default_factory=list)  # list[AgentEventRecord]
    # M35a: Rivers
    rivers: list[River] = Field(default_factory=list)
    # M37: Religion
    belief_registry: list[Belief] = Field(default_factory=list)  # max 16 faiths

    def save(self, path: Path) -> None:
        """Persist world state to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> WorldState:
        """Load world state from a JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"No state file at {path}")
        return cls.model_validate_json(path.read_text())


# --- Snapshot models (for viewer bundle — never persisted to state.json) ---

class CivSnapshot(BaseModel):
    """Per-turn snapshot of a civilization's stats."""
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
    folk_heroes: list[dict] = Field(default_factory=list)
    active_crisis: bool = False
    civ_stress: int = 0
    active_focus: str | None = None  # M21: tech focus for viewer/analytics
    factions: FactionState | None = None
    action_counts: dict[str, int] = Field(default_factory=dict)  # M19b: cumulative action counts
    max_precap_weight: float = 0.0  # M19b: max weight before 2.5x cap
    last_action: str | None = None  # M19b: most recent action taken


class RelationshipSnapshot(BaseModel):
    """Per-turn snapshot of disposition between two civs."""
    disposition: str


class TurnSnapshot(BaseModel):
    """Complete snapshot of world state at a single turn."""
    turn: int
    civ_stats: dict[str, CivSnapshot]
    region_control: dict[str, str | None]
    relationships: dict[str, dict[str, RelationshipSnapshot]]
    trade_routes: list[tuple[str, str]] = Field(default_factory=list)
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
    ecology: dict[str, dict[str, float]] = Field(default_factory=dict)
    mercenary_companies: list[dict] = Field(default_factory=list)
    vassal_relations: list[dict] = Field(default_factory=list)
    federations: list[dict] = Field(default_factory=list)
    proxy_wars: list[dict] = Field(default_factory=list)
    exile_modifiers: list[dict] = Field(default_factory=list)
    capitals: dict[str, str] = Field(default_factory=dict)
    peace_turns: int = 0
    region_cultural_identity: dict[str, str | None] = Field(default_factory=dict)
    movements_summary: list[dict] = Field(default_factory=list)
    stress_index: int = 0
    pandemic_regions: list[str] = Field(default_factory=list)
    climate_phase: str = ""
    active_conditions: list[dict] = Field(default_factory=list)
    per_pair_accuracy: dict[str, dict[str, float]] = Field(default_factory=dict)
    perception_errors: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)


# --- M20a: Narration Pipeline v2 models ---

class NarrativeRole(str, Enum):
    """Narrative arc position for a curated moment."""
    INCITING = "inciting"
    ESCALATION = "escalation"
    CLIMAX = "climax"
    RESOLUTION = "resolution"
    CODA = "coda"


class CausalLink(BaseModel):
    """Connection between a cause event and its effect."""
    cause_turn: int
    cause_event_type: str
    effect_turn: int
    effect_event_type: str
    pattern: str  # e.g., "drought→famine"


class GapSummary(BaseModel):
    """Mechanical summary of unnarrated turns between curated moments."""
    turn_range: tuple[int, int]  # inclusive
    event_count: int
    top_event_type: str
    stat_deltas: dict[str, dict[str, int]]  # {civ_name: {stat_name: delta}}
    territory_changes: int


class CivThematicContext(BaseModel):
    """Per-civ thematic data for narrator prompts."""
    name: str
    trait: str
    domains: list[str]
    dominant_terrain: str
    tech_era: str
    active_tech_focus: str | None = None
    active_named_events: list[str] = Field(default_factory=list)


class NarrativeMoment(BaseModel):
    """Curator output: a selected narratively important moment."""
    anchor_turn: int
    turn_range: tuple[int, int]  # inclusive
    events: list[Event]
    named_events: list[NamedEvent]
    score: float
    causal_links: list[CausalLink]
    narrative_role: NarrativeRole
    bonus_applied: float  # internal, not serialized to bundle


class AgentContext(BaseModel):
    """Agent narrative context for the narrator prompt (M30)."""
    named_characters: list[dict] = Field(default_factory=list)
    population_mood: str = "content"  # "desperate" > "restless" > "content"
    displacement_fraction: float = 0.0


class NarrationContext(BaseModel):
    """Per-moment LLM context for batch narration."""
    moment: NarrativeMoment
    snapshot: TurnSnapshot
    before_summary: str
    after_summary: str
    role_instruction: str
    causes: list[str]
    consequences: list[str]
    previous_prose: str | None
    civ_context: dict[str, CivThematicContext]
    agent_context: AgentContext | None = None


class ChronicleEntry(BaseModel):
    """A narrated chronicle entry covering a range of turns."""
    turn: int  # anchor turn
    covers_turns: tuple[int, int]  # inclusive range
    events: list[Event]
    named_events: list[NamedEvent]
    narrative: str  # LLM prose or mechanical fallback
    importance: float
    narrative_role: NarrativeRole
    causal_links: list[CausalLink]
