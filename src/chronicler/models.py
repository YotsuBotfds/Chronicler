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


# --- Core entities ---

class Region(BaseModel):
    name: str
    terrain: str  # plains, mountains, coast, forest, desert, tundra
    carrying_capacity: int = Field(ge=1, le=10)
    resources: str  # fertile, mineral, timber, maritime, barren
    controller: Optional[str] = None


class Leader(BaseModel):
    name: str
    trait: str
    reign_start: int
    alive: bool = True


class Civilization(BaseModel):
    # NOTE: Field constraints (ge/le) are enforced at construction time only.
    # The simulation engine mutates stats via direct assignment with _clamp()
    # to keep values in-bounds. Do NOT enable validate_assignment=True without
    # updating all mutation sites in simulation.py.
    name: str
    population: int = Field(ge=1, le=10)
    military: int = Field(ge=1, le=10)
    economy: int = Field(ge=1, le=10)
    culture: int = Field(ge=1, le=10)
    stability: int = Field(ge=1, le=10)
    tech_era: TechEra = TechEra.TRIBAL
    treasury: int = 0
    domains: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    leader: Leader
    goal: str = ""
    regions: list[str] = Field(default_factory=list)
    asabiya: float = Field(default=0.5, ge=0.0, le=1.0)


class Relationship(BaseModel):
    disposition: Disposition = Disposition.NEUTRAL
    treaties: list[str] = Field(default_factory=list)
    grievances: list[str] = Field(default_factory=list)
    trade_volume: int = 0


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


class ActiveCondition(BaseModel):
    condition_type: str
    affected_civs: list[str]
    duration: int
    severity: int = Field(ge=1, le=10)


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
