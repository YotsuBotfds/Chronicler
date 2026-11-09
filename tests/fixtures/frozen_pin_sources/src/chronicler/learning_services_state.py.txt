"""Opt-in academy service receipts, retained separately from seat identity."""
from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr


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


class AcademyMaterialInventory(BaseModel):
    """One seat incarnation's separate, paid institution-held crafts."""
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    held: float | None  # None means legacy holdings were not observed
    purchased_total: float | None
    used_total: float | None
    lost_total: float | None
    retired: bool = False
    upkeep_source_turn: int | None = None
    upkeep_lord: int | None = None
    upkeep_due: int | None = None
    upkeep_amount_paid: int | None = None
    upkeep_satisfied: bool | None = None


class AcademyProcurementReceipt(BaseModel):
    model_config = {"frozen": True}
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    lord: int
    source_turn: int
    upkeep_source_turn: int | None
    upkeep_due: int | None
    upkeep_amount_paid: int | None
    upkeep_satisfied: bool | None
    scholar_upper_bound: int | None
    learner_upper_bound: int | None
    craft_price: float | None
    market_stock: float
    market_commitments: float | None
    budget_before: int | None
    held_before: float | None
    purchased: float
    paid: int
    held_after: float | None
    shortfalls: tuple[str, ...] = ()


class AcademySupplyLoss(BaseModel):
    model_config = {"frozen": True}
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    source_turn: int
    held_before: float | None
    lost: float | None
    held_after: float | None
    reason: str = "seat_destroyed_or_replaced"


class AcademyTeachingReceipt(BaseModel):
    model_config = {"frozen": True}
    seat_id: int
    region: int
    founder: int
    founded_turn: int
    seat_name: str
    lord: int
    source_turn: int
    available_turn: int
    learner_upper_bound: int | None
    scholar_upper_bound: int | None
    upkeep_source_turn: int | None
    upkeep_lord: int | None
    upkeep_due: int | None
    upkeep_amount_paid: int | None
    upkeep_satisfied: bool | None
    upkeep_applies: bool | None
    held_before: float | None
    work_requested: float
    work_available: float | None
    work_reserved: float | None
    work_delivered: float | None
    learners_delivered: float | None
    crafts_used: float | None
    held_after: float | None
    native_dropped: int | None


class LearningServicesState(BaseModel):
    enabled: bool = Field(default=True, exclude_if=lambda v: v is True)
    last_source_turn: int | None = None
    receipts: list[AcademyServiceReceipt] = Field(default_factory=list)
    inventories: list[AcademyMaterialInventory] | None = Field(default=None, exclude_if=lambda v: v is None)
    procurement_receipts: list[AcademyProcurementReceipt] | None = Field(default=None, exclude_if=lambda v: v is None)
    supply_losses: list[AcademySupplyLoss] | None = Field(default=None, exclude_if=lambda v: v is None)
    teaching_receipts: list[AcademyTeachingReceipt] | None = Field(default=None, exclude_if=lambda v: v is None)
    last_procurement_turn: int | None = Field(default=None, exclude_if=lambda v: v is None)
    last_service_turn: int | None = Field(default=None, exclude_if=lambda v: v is None)
    material_balance: dict | None = Field(default=None, exclude_if=lambda v: v is None)
    _active_plan: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        if getattr(self, "_active_plan", None) is not None:
            raise ValueError("cannot checkpoint pending academy teaching work")
        return super().__getstate__()

    def __setstate__(self, state):
        super().__setstate__(state)
        self.__dict__.setdefault("enabled", True)
        for name in ("inventories", "procurement_receipts", "supply_losses", "teaching_receipts",
                     "last_procurement_turn", "last_service_turn"):
            self.__dict__.setdefault(name, None)
