"""Dated evidence and material receipts for opt-in connected public health."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chronicler.money import MoneyBook


class OutbreakReport(BaseModel):
    id: int
    recipient: int
    source: int
    target: int
    pathogen: int
    issued: int
    delivery: int
    expires: int
    prevalence: float


class SupplyReceipt(BaseModel):
    turn: int
    civ: int
    region: int
    source: int | None = None
    seller: int | None = None
    need_milli: int
    food_milli: int = 0
    charged_milli: int = 0
    internal_milli: int = 0
    price_milli: int | None = None
    patients: float = 0.0
    reason: str = "unavailable"


class PublicHealthState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["active", "cost_only"] = "active"
    policy: Literal["evidence", "shuffled"] = "evidence"
    report_delay: int = Field(default=0, ge=0, le=20)
    next_report: int = 0
    reports: list[OutbreakReport] = Field(default_factory=list)
    report_turn: int | None = None
    decisions: list[dict] = Field(default_factory=list)
    # Observed own outbreak deaths / infectious person turns, by civ/pathogen.
    fatality: dict[str, list[float]] = Field(default_factory=dict)
    sanitation_turn: int | None = None
    sanitation: list[float] = Field(default_factory=list)
    environment_turn: int | None = None
    environment: list[dict] = Field(default_factory=list)
    supply_turn: int | None = None
    supplies: list[SupplyReceipt] = Field(default_factory=list)
    prices: dict[int, int] = Field(default_factory=dict)
    price_turn: int | None = None
    book: MoneyBook = Field(default_factory=MoneyBook)
    totals: dict[str, float] = Field(default_factory=dict)
