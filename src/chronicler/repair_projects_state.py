"""Persisted state of RS2 maintenance, reconstruction and repair projects (``--repair-projects``, default off).

Owned by :mod:`chronicler.repair_projects`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Recovery-skills groundwork (RS0): only the switch, its mode and scalar
lifetime counters exist yet. The package lane adds its bounded containers
(open projects per workshop site and granary, war-damage records
and the per-turn receipts) here; a world that never enabled the switch has
no sub-state, so feature-off output is unchanged.

``cost_only`` is the cost-retaining control: projects reserve, pay and use
timber identically but do not change condition.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("repair", "cost_only")


class RepairProjectsState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["repair", "cost_only"] = "repair"
    #: Scalar lifetime counters (bounded: a fixed key set per lane).
    counters: dict[str, int] = Field(default_factory=dict)
