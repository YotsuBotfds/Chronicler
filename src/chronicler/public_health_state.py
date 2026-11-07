"""Dated evidence and material receipts for opt-in connected public health."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

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
    # Persisted default is historical: old JSON and exact pickles must retain
    # their model. New enable paths explicitly choose density_only.
    crowding: Literal["legacy_displacement", "density_only"] = "legacy_displacement"
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
    guard_plan: list[dict] = Field(default_factory=list)
    guard_turn: int | None = None
    guards: list[dict] = Field(default_factory=list)
    guard_capacity_turn: int | None = None
    guard_capacity: list[tuple[int, int]] = Field(default_factory=list)
    funding_turn: int | None = None
    funding: list[dict] = Field(default_factory=list)
    _guard_tick: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_guard_tick") is not None:
            state = {**state, "__pydantic_private__": {**private, "_guard_tick": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_guard_tick": None})
        else:
            private.setdefault("_guard_tick", None)
