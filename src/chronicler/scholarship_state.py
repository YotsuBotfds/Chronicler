"""Persisted state of seats of learning (see :mod:`chronicler.scholarship`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A seat is identified by its index in ``ScholarshipState.seats`` (fallen
seats stay in the list); its place by its region index in ``world.regions``;
rulers by their index in ``world.civilizations``; a library's city by its
M56a ``settlement_id``; a temple school's faith by its faith id.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

#: ``Seat.kind`` names, each with its patron: an academy is kept by the
#: ruler of its region (treasury), a temple school by its temple (the
#: offerings: temple prestige), a library by its city (the civic purse).
KIND_NAMES: tuple[str, ...] = ("academy", "temple school", "library")
ACADEMY, TEMPLE_SCHOOL, LIBRARY = range(len(KIND_NAMES))
PATRON_NAMES: tuple[str, ...] = ("ruler", "faith", "city")

#: ``Seat.level`` names; level 0 is a fallen seat.
LEVEL_NAMES: tuple[str, ...] = ("fallen", "modest", "renowned", "great")

#: Why a seat fell (``Seat.fall_cause``).
FALL_CAUSES: tuple[str, ...] = ("sack", "famine", "persecution", "patronage")
SACK, FAMINE, PERSECUTION, PATRONAGE = range(len(FALL_CAUSES))

#: ``Seat.history`` entry kinds.
HISTORY_KINDS: tuple[str, ...] = (
    "founded", "rose", "declined", "patron", "unpaid", "struck", "refugees", "fled", "fell",
    "master",
)

#: Cumulative counters kept on ``ScholarshipState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "founded", "academies", "temple_schools", "libraries", "rises", "declines", "fallen",
    "fall_sack", "fall_famine", "fall_persecution", "fall_patronage", "strikes", "unpaid",
    "patron_changes", "upkeep", "fees", "refuges", "carried", "practice_lost",
)


class Seat(BaseModel):
    """One seat of learning, from its founding to its fall."""

    region: int                      # region index
    kind: int = ACADEMY
    name: str
    founded_turn: int
    founder: int = -1                # civ index of the region's ruler at founding (-1 none)
    lord: int = -1                   # civ index of the region's ruler at the last tick
    faith: int = 0xFF                # the scholars' faith (a temple school's: its temple's)
    city: int = 0                    # a library's city (settlement id); 0 otherwise
    level: int = 1
    peak_level: int = 1
    scholars: float = 0.0            # the scholar body at the last tick (reference scale)
    peak_scholars: float = 0.0
    masters: int = 0                 # great scholars of its ruler teaching there
    teachers: list[str] = Field(default_factory=list)   # great persons who taught there, by name
    refugees: float = 0.0            # scholars come from fallen seats (decaying)
    owed: float = 0.0                # upkeep owed but not yet paid (the fraction carried)
    unpaid: int = 0                  # consecutive turns the patron could not pay
    persecuted: int = 0              # consecutive turns its scholars' faith was persecuted
    level_turn: int = 0              # turn of its last change of level
    last_strike: int = -1000
    pull: float = 0.0                # seat_pull it gives its region (read by the next batch)
    fallen_turn: int | None = None
    fall_cause: int = -1
    refuge: int = -1                 # seat index its scholars fled to (-1 none)
    # (turn, kind, event id) in order; kinds from HISTORY_KINDS.
    history: list[tuple[int, str, str]] = Field(default_factory=list)


class ScholarshipState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.scholarship``).

    ``carries`` are knowledge moves from fallen seats, consumed by the next
    technique tick: (source region, refuge region or -1, source ruler's civ
    index, seat index)."""

    seats: list[Seat] = Field(default_factory=list)
    carries: list[tuple[int, int, int, int]] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0 for k in COUNTER_KEYS})
    last_tick_turn: int | None = None


def scholarship_on(world) -> bool:
    """True only for a real scholarship state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "scholarship", None), ScholarshipState)
