"""Persisted state of RS4 migration, knowledge and household support (``--remittances``, default off).

Owned by :mod:`chronicler.remittances`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it.

Recovery-skills groundwork (RS0): only the switch, its mode and scalar
lifetime counters exist yet. The package lane adds its bounded containers
(the bounded diaspora ledger, per-sender ``last_settled_turn`` and the
remittance receipts) here; a world that never enabled the switch has
no sub-state, so feature-off output is unchanged.

``record_only`` is the control: the diaspora ledger is kept and nothing is
sent.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("send", "record_only")


class RemittancesState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["send", "record_only"] = "send"
    #: Scalar lifetime counters (bounded: a fixed key set per lane).
    counters: dict[str, int] = Field(default_factory=dict)
