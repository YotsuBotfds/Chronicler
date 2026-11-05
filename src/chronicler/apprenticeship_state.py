"""Persisted state of RS1 apprenticeship and skill continuity (``--apprenticeship``, default off).

Owned by :mod:`chronicler.apprenticeship`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Recovery-skills groundwork (RS0): only the switch, its mode and scalar
lifetime counters exist yet. The package lane adds its bounded containers
(workshop qualifications by stable id, mentor/apprentice cohorts per
site and the continuity records) here; a world that never enabled the switch has
no sub-state, so feature-off output is unchanged.

``no_qualification`` is the cost-retaining control: the same wear, attendance
and costs, and no new qualifications.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("train", "no_qualification")


class ApprenticeshipState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["train", "no_qualification"] = "train"
    #: Scalar lifetime counters (bounded: a fixed key set per lane).
    counters: dict[str, int] = Field(default_factory=dict)
