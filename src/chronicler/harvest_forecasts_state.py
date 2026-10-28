"""Persisted, bounded public harvest assessments; no simulation imports."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class HarvestObserver(BaseModel):
    region: int
    # Present/past normalized production per food demand: (turn, ratio).
    observations: list[tuple[int, float]] = Field(default_factory=list)


class HarvestReport(BaseModel):
    id: str
    source_region: int
    source_region_name: str
    recipient_region: int
    recipient_region_name: str
    owner: int
    owner_name: str
    issued_turn: int
    delivery_turn: int
    expires_turn: int
    target_start: int
    target_end: int
    probability: float
    confidence: float
    predicted_ratio: float
    status: str = "pending"
    delivered_turn: int | None = None
    resolved_turn: int | None = None
    # Evaluation is production/demand BEFORE reserve releases, not hunger.
    outcome_shortfall: bool | None = None
    observed_ratio: float | None = None
    brier: float | None = None
    evaluation_sum: float = 0.0
    evaluation_count: int = 0
    issued_event_id: str = ""
    delivered_event_id: str = ""


class HarvestForecastState(BaseModel):
    # Experimental delivery controls; never alter climate or existing RNGs.
    policy: Literal["normal", "withhold", "shuffle"] = "normal"
    observers: list[HarvestObserver] = Field(default_factory=list)
    reports: list[HarvestReport] = Field(default_factory=list)
    outcomes: list[HarvestReport] = Field(default_factory=list)
    preparedness: list[dict] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=lambda: {
        "issued": 0, "delivered": 0, "withheld": 0, "cancelled": 0,
        "resolved": 0, "unscored": 0, "brier_sum": 0.0,
        "bought_during_warning": 0.0, "paid_during_warning": 0.0,
    })
    # Five probability bins: [count, probability_sum, observed_shortfalls].
    calibration: list[list[float]] = Field(default_factory=lambda: [[0.0, 0.0, 0.0] for _ in range(5)])
    last_tick_turn: int | None = None


def harvest_forecasts_on(world) -> bool:
    return isinstance(getattr(world, "harvest_forecasts", None), HarvestForecastState)
