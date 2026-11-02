"""Persisted, bounded public harvest assessments; no simulation imports."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, Field


def _empty(value) -> bool:
    return not value


def _fixed(value) -> bool:
    return value == "fixed"


def _no_delay(value) -> bool:
    return value is None or value == 0


ForecastObservation = tuple[
    Annotated[int, Field(ge=0, strict=True)],
    Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)],
]


class ForecastCredibilityEvidence(BaseModel):
    """One locally received, three-observation assessment result."""
    report_id: str
    issued_event_id: str = Field(min_length=1, strict=True)
    delivered_event_id: str = Field(min_length=1, strict=True)
    source_region: int = Field(ge=0, strict=True)
    recipient_region: int = Field(ge=0, strict=True)
    owner: int = Field(ge=0, strict=True)
    owner_name: str = Field(strict=True)
    issued_turn: int = Field(ge=0, strict=True)
    delivered_turn: int = Field(ge=0, strict=True)
    resolved_turn: int = Field(ge=0, strict=True)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    observations: list[ForecastObservation] = Field(min_length=3, max_length=3)
    observed_ratio: float = Field(ge=0, allow_inf_nan=False, strict=True)
    outcome_shortfall: bool = Field(strict=True)
    brier: float = Field(ge=0, le=1, allow_inf_nan=False, strict=True)


class HarvestObserver(BaseModel):
    region: int
    # Present/past normalized production per food demand: (turn, ratio).
    observations: list[tuple[int, float]] = Field(default_factory=list)
    # Last four local results across sources/owners, never a global score ring.
    credibility_memory: list[ForecastCredibilityEvidence] = Field(
        default_factory=list, max_length=4, exclude_if=_empty)


def _none(value) -> bool:
    return value is None


class HarvestEstimatorMetadata(BaseModel):
    """Frozen issue-time construction evidence, not actor-visible report text."""
    model_config = {"frozen": True}
    schema_version: Literal[1] = 1
    issued_turn: int
    reported_issuer_region: int
    estimate_origin_region: int
    policy: Literal["normal", "withhold", "shuffle"]
    preparation_policy: Literal["fixed", "local_credibility"]
    base_delivery_lag: int
    extra_delivery_delay: int
    observations: tuple[ForecastObservation, ...] = Field(min_length=3, max_length=6)
    observation_window: Literal[6] = 6
    season_multiplier: float = Field(allow_inf_nan=False)
    shortfall_ratio: float = Field(allow_inf_nan=False)
    noise_draw: float = Field(allow_inf_nan=False)
    claimed_probability: float = Field(allow_inf_nan=False)
    claimed_confidence: float = Field(allow_inf_nan=False)
    claimed_predicted_ratio: float = Field(allow_inf_nan=False)


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
    # Issue-time construction evidence is distinct from actor-known text.
    estimator_metadata: HarvestEstimatorMetadata | None = Field(default=None, exclude_if=_none)
    # Only explicit credibility mode records these present production ratios.
    credibility_observations: list[ForecastObservation] = Field(
        default_factory=list, max_length=3, exclude_if=_empty)

    def __setstate__(self, state):
        super().__setstate__(state)
        self.__dict__.setdefault("estimator_metadata", None)


class HarvestForecastState(BaseModel):
    # Experimental delivery controls; never alter climate or existing RNGs.
    policy: Literal["normal", "withhold", "shuffle"] = "normal"
    preparation_policy: Literal["fixed", "local_credibility"] = Field(
        default="fixed", exclude_if=_fixed)
    report_delay: int | None = Field(default=None, ge=0, le=12, strict=True, exclude_if=_no_delay)
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
