"""Persisted state of RS5 funded protection of forest cover from clearing (``--clearing-protection``, default off).

Owned by :mod:`chronicler.clearing_protection`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Recovery-skills groundwork (RS0): only the switch, its mode and scalar
lifetime counters exist yet. The package lane adds its bounded containers
(the adopted protected regions, warden bills and the
``cover_not_cleared`` ledger) here; a world that never enabled the switch has
no sub-state, so feature-off output is unchanged.

``cost_only`` is the cost-retaining control: protection is adopted and
paid identically and applies no cap.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("enforced", "cost_only")


class ClearingProtectionState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["enforced", "cost_only"] = "enforced"
    #: Scalar lifetime counters (bounded: a fixed key set per lane).
    counters: dict[str, int] = Field(default_factory=dict)
