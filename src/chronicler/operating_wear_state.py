"""Persisted state of the workshop operating-wear assumption (PL2, ``--operating-wear``, default off).

Owned by :mod:`chronicler.operating_wear`. Pure data with no simulation imports, so
:mod:`chronicler.livelihoods_state` can import it. A world that never enabled the
switch has no sub-state, so feature-off output is unchanged. (``--apprenticeship``
implies the same wear without creating this sub-state: RS1 runs keep their exact
output.)

Identities: ``site`` is the L1 workshop site id; ``region`` is an index in
``world.regions``; qualified people are native stable ids.

Bounded containers: ``frame`` holds the last completed turn's receipts (one per
funded operating site, at most ``workshops_state.MAX_SITES``); ``counters`` use
the fixed key set ``COUNTERS`` (declaration order: append only).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns", "operating_site_turns", "wear", "upkeep_offset", "net_wear",
    "full_offset_site_turns", "covered_site_turns", "repairs",
)


class WearReceipt(BaseModel):
    """One funded operating site's wear in a completed turn: ``net_wear = wear -
    upkeep_offset`` with ``0 <= upkeep_offset <= wear``. The offset is the
    qualified crew's upkeep (RS1); without ``--apprenticeship`` nobody is
    qualified and it is 0."""

    turn: int
    site: int
    region: int
    wear: float
    upkeep_offset: float = 0.0
    net_wear: float
    condition_before: float
    condition_after: float
    #: Qualified members of the turn's crew (RS1; [] without it).
    qualified_on_crew: list[int] = Field(default_factory=list)
    full_offset: bool = False


class OperatingWearState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: Scalar lifetime counters (the fixed key set ``COUNTERS``).
    counters: dict[str, float] = Field(default_factory=dict)
    frame_turn: int | None = None
    frame: list[WearReceipt] = Field(default_factory=list)
    #: Transient, within one Phase 2: (turn, receipts by site) recorded at
    #: workshop settlement and committed by ``finish_phase2``. Never serialized.
    _pending: object | None = PrivateAttr(default=None)
