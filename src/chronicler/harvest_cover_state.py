"""B4 canopy response to the existing L3 timber stock; no second stock."""
from typing import Literal

from pydantic import BaseModel, Field

MODES = ("loss", "record_only")
COUNTERS = ("turns", "regions_stressed", "cover_loss", "proposed_loss")


class CoverRow(BaseModel):
    region: int
    slots: list[int]
    standing: float
    capacity: float
    ratio: float
    cover_before: float
    supported_cover: float
    proposed_loss: float
    loss: float
    cover_after: float


class HarvestCoverState(BaseModel):
    enabled: bool = True
    mode: Literal["loss", "record_only"] = "loss"
    frame_turn: int | None = None
    rows: list[CoverRow] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
