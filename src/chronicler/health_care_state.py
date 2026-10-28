"""Optional authoritative injury state; native work inputs are derived each turn."""
from pydantic import BaseModel, Field, PrivateAttr


class InjuryEpisode(BaseModel):
    agent_id: int = Field(gt=0)
    onset_turn: int
    remaining: float = Field(gt=0.0, allow_inf_nan=False)
    origin_region: int = Field(ge=0)


class HealthCareState(BaseModel):
    episodes: list[InjuryEpisode] = Field(default_factory=list)
    injury_rate: float = Field(default=0.01, ge=0.0, le=0.25, allow_inf_nan=False)
    impairment: float = Field(default=0.5, ge=0.0, le=1.0, allow_inf_nan=False)
    care_fraction: float = Field(default=0.2, ge=0.0, le=1.0, allow_inf_nan=False)
    recovery_work: float = Field(default=2.0, ge=1.0, le=10.0, allow_inf_nan=False)
    care_enabled: bool = True
    last_tick_turn: int = -1
    summary: dict = Field(default_factory=dict)
    # This turn's assignment is recreated before economy; no slots persist.
    _prepared: list | None = PrivateAttr(default=None)
