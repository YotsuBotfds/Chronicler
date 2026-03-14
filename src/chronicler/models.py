"""Core data models for the civilization chronicle generator.

WorldState is the single source of truth. All simulation and narrative
modules read from and write to WorldState, which serializes to JSON.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


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


class Disposition(str, Enum):
    HOSTILE = "hostile"
    SUSPICIOUS = "suspicious"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class ActionType(str, Enum):
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    BUILD = "build"
    EMBARGO = "embargo"
    MOVE_CAPITAL = "move_capital"


class ActionCategory(str, Enum):
    AUTOMATIC = "automatic"
    DELIBERATE = "deliberate"
    REACTION = "reaction"


# --- Core entities ---

class Region(BaseModel):
    name: str
    terrain: str  # plains, mountains, coast, forest, desert, tundra
    carrying_capacity: int = Field(ge=1, le=100)
    resources: str  # fertile, mineral, timber, maritime, barren
    controller: Optional[str] = None
    x: float | None = None
    y: float | None = None
    adjacencies: list[str] = Field(default_factory=list)
    specialized_resources: list[Resource] = Field(default_factory=list)
    fertility: float = Field(default=0.8, ge=0.0, le=1.0)
    infrastructure_level: int = Field(default=0, ge=0)
    famine_cooldown: int = Field(default=0, ge=0)


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


class Civilization(BaseModel):
    # NOTE: Field constraints (ge/le) are enforced at construction time only.
    # The simulation engine mutates stats via direct assignment with _clamp()
    # to keep values in-bounds. Do NOT enable validate_assignment=True without
    # updating all mutation sites in simulation.py.
    name: str
    population: int = Field(ge=1, le=100)
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
    leader_name_pool: list[str] | None = None
    capital_region: str | None = None
    last_income: int = 0
    merc_pressure_turns: int = 0


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    treaties: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0
    allied_turns: int = 0


class HistoricalFigure(BaseModel):
    name: str
    role: str
    traits: list[str] = Field(default_factory=list)
    civilization: str
    alive: bool = True
    deeds: list[str] = Field(default_factory=list)


class Event(BaseModel):
    turn: int
    event_type: str
    actors: list[str]
    description: str
    consequences: list[str] = Field(default_factory=list)
    importance: int = Field(default=5, ge=1, le=10)


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
    fertility: dict[str, float] = Field(default_factory=dict)
    mercenary_companies: list[dict] = Field(default_factory=list)
