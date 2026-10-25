"""Persisted state of cities (see :mod:`chronicler.cities`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A city is identified by its M56a ``settlement_id``; regions by their
index in ``world.regions`` and civilizations by their index in
``world.civilizations``.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

#: ``City.rank`` names; rank 0 is unused (a settlement below town size).
RANK_NAMES: tuple[str, ...] = ("settlement", "town", "city", "great city")
TOWN, CITY, GREAT_CITY = 1, 2, 3

#: ``City.charter`` names.
CHARTER_NAMES: tuple[str, ...] = ("none", "market rights", "self-government", "free city")
NO_CHARTER, MARKET_RIGHTS, SELF_GOVERNMENT, FREE_CITY = range(len(CHARTER_NAMES))

#: ``City.history`` entry kinds.
HISTORY_KINDS: tuple[str, ...] = (
    "founded", "grew", "declined", "charter", "refused", "revolt", "concession",
    "suppressed", "free_city", "sacked", "walls", "plague", "famine", "lord", "fell",
)

#: Cumulative counters kept on ``CityState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "founded", "rank_ups", "rank_downs", "fallen", "charters", "refusals", "revolts",
    "concessions", "suppressions", "free_cities", "sacks", "walls", "dues", "fees",
    "fines", "plunder", "commerce",
)


class City(BaseModel):
    """One city, from its founding to its fall."""

    settlement_id: int
    region: int                      # region index
    name: str                        # the M56a settlement name
    founded_turn: int
    founder: int                     # civ index at founding (-1 unclaimed)
    lord: int = -1                   # civ index of the region's controller at the last tick
    rank: int = 1
    residents: int = 0               # M56a's population estimate (last detection pass)
    size: float = 0.0                # residents smoothed over turns; ranks read it
    peak_residents: int = 0
    peak_rank: int = 1
    # Residents' occupation shares (farmer, soldier, merchant, scholar,
    # priest) and mean satisfaction, from the agents in the footprint at the
    # last turn with enough of them.
    mix: list[float] = Field(default_factory=lambda: [0.45, 0.15, 0.15, 0.15, 0.10])
    satisfaction: float | None = None
    commerce: float = 0.0            # last turn's commerce
    wealth: float = 0.0              # civic purse
    peak_wealth: float = 0.0
    charter: int = 0
    unrest: float = 0.0
    grievance: float = 0.0
    pull: float = 0.0                # city_pull this city gives its region (read next turn)
    below_turns: int = 0             # consecutive turns below the rank's floor
    empty_turns: int = 0             # consecutive turns below the fall floor
    last_petition: int = -1000
    last_revolt: int = -1000
    last_sack: int = -1000
    predecessor: int = 0             # settlement id of a fallen city of the region (0 none)
    fallen_turn: int | None = None
    fall_cause: str = ""
    # (turn, kind, event id) in order; kinds from HISTORY_KINDS.
    history: list[tuple[int, str, str]] = Field(default_factory=list)


class CityState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.cities``).

    ``owed`` and ``carry`` are indexed by civ index: dues assessed in the
    last Phase 10, paid as ``keep`` treasury in the next Phase 2 with the
    fractional remainder carried.
    """

    cities: list[City] = Field(default_factory=list)   # living, by settlement id
    fallen: list[City] = Field(default_factory=list)   # in order of their fall
    owed: list[float] = Field(default_factory=list)
    carry: list[float] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    last_tick_turn: int | None = None


def cities_on(world) -> bool:
    """True only for a real city state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "cities", None), CityState)
