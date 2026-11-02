"""Opt-in academy service receipts, retained separately from seat identity."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AcademyServiceReceipt(BaseModel):
    seat_id: int
    # The seat index plus its founding identity binds the receipt to one incarnation.
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    lord: int
    source_turn: int
    available_turn: int
    promised: int | None
    demand: int | None
    # Whether current upkeep was satisfied; zero due is satisfied with zero paid.
    upkeep_paid: bool | None
    upkeep_due: int | None = None
    upkeep_amount_paid: int | None = None
    funded: bool | None
    native_staff: int | None
    staff_capacity: int | None
    craft_price: float | None
    crafts_stock: float
    crafts_committed: float | None
    crafts_available: float | None
    budget_initial: int
    attempted: float
    delivered: float
    # One purchase, consumed immediately; these are aliases, not two withdrawals.
    crafts_purchased: float
    crafts_used: float
    purchase_paid: int
    budget_remaining: int
    shortfalls: list[str] = Field(default_factory=list)


class LearningServicesState(BaseModel):
    last_source_turn: int | None = None
    receipts: list[AcademyServiceReceipt] = Field(default_factory=list)
