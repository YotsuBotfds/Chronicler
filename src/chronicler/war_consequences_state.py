"""D3 persisted war experience; native identities remain pool-scoped."""
from typing import Literal

from pydantic import BaseModel, Field


class WarConsequencesState(BaseModel):
    enabled: bool = True
    mode: Literal["active", "record_only"] = "active"
    last_turn: int = -1
    pending: list[dict] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    history_dropped: int = 0
    frame: dict | None = None
    separation: dict | None = None
    counters: dict[str, int] = Field(default_factory=dict)
