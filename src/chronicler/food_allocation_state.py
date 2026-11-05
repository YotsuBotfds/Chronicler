"""Persisted state of the L2 household food allocation (default off).

Region indices are positions in ``world.regions``; person and household keys
are native stable ids. Only the last completed allocation is kept (scarce
regions' rows and a bounded person sample) plus scalar counters. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

REGIMES: tuple[str, ...] = ("equal", "floor_means", "targeted_relief")   # native codes 0, 1, 2
#: Person receipts kept per completed turn (stable: ascending id, region order).
SNAPSHOT_SAMPLE = 24


class FoodAllocationState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    regime: Literal["equal", "floor_means", "targeted_relief"] = "floor_means"
    frame_turn: int | None = None
    regions: list[dict] = Field(default_factory=list)
    totals: dict[str, float] = Field(default_factory=dict)
    sample: list[list] = Field(default_factory=list)
    sample_dropped: int = 0
    counters: dict[str, float] = Field(default_factory=dict)
    _phase2: object | None = PrivateAttr(default=None)
    _installed: int | None = PrivateAttr(default=None)
