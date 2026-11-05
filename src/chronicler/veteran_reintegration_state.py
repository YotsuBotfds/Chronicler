"""Persisted state of RS3 veteran reintegration (``--veteran-reintegration``, default off).

Owned by :mod:`chronicler.veteran_reintegration`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Recovery-skills groundwork (RS0): only the switch, its mode and scalar
lifetime counters exist yet. The package lane adds its bounded containers
(the bounded veteran records captured at roster releases and their
dated outcomes) here; a world that never enabled the switch has
no sub-state, so feature-off output is unchanged.

``record_only`` is the control: veterans are captured and tracked
without priority.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("priority", "record_only")
#: Dated outcome kinds of a veteran record (phase plan RS3), in declaration
#: order (append only). Other lanes report placements through
#: :func:`chronicler.veteran_reintegration.note_outcome`.
OUTCOMES: tuple[str, ...] = (
    "placed:crew", "placed:apprentice", "placed:repair", "waiting", "remobilised",
    "died", "migrated", "control_lost", "expired",
)


class VeteranReintegrationState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["priority", "record_only"] = "priority"
    #: Scalar lifetime counters (bounded: a fixed key set per lane).
    counters: dict[str, int] = Field(default_factory=dict)
