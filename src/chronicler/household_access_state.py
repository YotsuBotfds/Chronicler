"""Persisted state of the household access metrics (DEP-7, default off).

Owned by :mod:`chronicler.household_access`. Pure data with no simulation
imports. Observation only: the state holds the last observed turn's derived
frame (world aggregates and the rows of the regions observed in detail) and
cumulative counters with the fixed key set ``COUNTERS``; it stores no
person or household data. Region indices are positions in ``world.regions``.
Tuple orders are declaration orders: append new values at the end.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Cumulative counters (insertion order). Person-turns count people alive in
#: an observed allocation or retail frame; shortfall and deficit are rations.
COUNTERS: tuple[str, ...] = (
    "turns_observed",            # turns with an L2 allocation frame (the world denominator)
    "turns_unobserved",          # turns without one (world metrics None that turn)
    "person_turns",              # people in observed frames (L2 regions plus retail regions)
    "shortfall",                 # ration shortfall summed over them
    "allocation_person_turns",   # people in L2 (non-retail) regions
    "people_poorer_half",        # L2 person-turns in the poorer half of households
    "shortfall_poorer_half",     # their ration shortfall
    "retail_person_turns",       # people in settled household-retail regions
    "priced_out_person_turns",   # retail people priced out of their fair share
    "priced_out_deficit",        # their deficit to the fair share, rations
)


class HouseholdAccessState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: Turn of the last observed frame (None: none yet).
    frame_turn: int | None = None
    #: ``{"world": {...}, "regions": [...]}`` of ``frame_turn``.
    frame: dict | None = None
    counters: dict[str, float] = Field(default_factory=dict)
