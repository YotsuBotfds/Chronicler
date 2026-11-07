"""A6 bounded, dated personal experience; no second residence authority."""
from typing import Literal

from pydantic import BaseModel, Field


class AdaptiveLivelihoodsState(BaseModel):
    enabled: bool = True
    mode: Literal["adapt", "record_only", "shuffled"] = "adapt"
    rules: Literal["1", "2"] = "2"
    memory: list[dict] = Field(default_factory=list)
    work: list[dict] = Field(default_factory=list)
    last_turn: int = -1
    frame: dict | None = None
    counters: dict[str, int] = Field(default_factory=dict)
