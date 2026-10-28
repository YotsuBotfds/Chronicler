"""Optional Python-authoritative merchant observation identity, not ownership."""
from __future__ import annotations

from pydantic import BaseModel, Field


def _is_none(value):
    return value is None


class ActiveVoyage(BaseModel):
    voyage_id: str | None = None
    start_turn: int | None = None
    origin_region: int
    dest_region: int
    good_slot: int


class TransactionObservation(BaseModel):
    id: str
    source_turn: int
    operation: str
    merchant_id: int
    merchant_civ: int | None
    merchant_civ_name: str | None
    voyage_id: str | None = None
    origin_region: int
    origin_region_name: str
    dest_region: int
    dest_region_name: str
    from_region: int
    to_region: int
    good_slot: int
    quantity: float
    origin_controller: int | None
    origin_controller_name: str | None
    dest_controller: int | None
    dest_controller_name: str | None
    cargo_basis: str             # regional_stock or virtual_shadow
    quantity_basis: str          # native operation, never final cash settlement
    loss_reason: str | None = None
    loss_id: str | None = None
    # Custody/controller observations do not establish private cargo title.
    cargo_title_owner: str | None = None
    financial_eligible: bool = False


class PublicPurchaseObservation(BaseModel):
    id: str
    source_turn: int
    source_region: int
    source_region_name: str
    dest_region: int
    dest_region_name: str
    buyer: int
    buyer_name: str
    keeper: int
    keeper_name: str
    source_controller: int
    source_controller_name: str
    good: str = "grain"
    purchase_kind: str           # own_market, same_realm, foreign
    sent: float
    received: float
    transit_loss: float
    buyer_paid: int
    foreign_ruler_credited: int
    domestic_producer_sink: int
    buyer_treasury_before: int   # replay of existing projected keep ledger
    buyer_treasury_after: int
    seller_treasury_before: int | None
    seller_treasury_after: int | None
    buyer_demand: float
    source_demand: float
    source_market_price: float
    price_basis: str = "procurement_economy_result_food_demand_over_market_supply_floor_0.1"
    treasury_basis: str = "projected_keep_purchase_legs"
    quantity_basis: str = "committed_public_granary_purchase"
    financial_eligible: bool = False


class PublicPurchaseFrame(BaseModel):
    source_turn: int
    phase: str = "phase10_granary_procurement"
    available: bool
    complete: bool
    unavailable_reason: str | None = None
    max_rows: int
    dropped_rows: int = 0
    duplicate_keys: int = 0
    observed_purchases: int = 0
    rows: list[PublicPurchaseObservation] = Field(default_factory=list)
    frame_digest: str
    counters: dict[str, float] = Field(default_factory=dict)


class TransactionReceiptState(BaseModel):
    namespace: str = "trajectory"
    max_rows: int = Field(default=4096, ge=1, le=65536)
    active: dict[int, ActiveVoyage] = Field(default_factory=dict)
    frame: list[TransactionObservation] = Field(default_factory=list)
    source_turn: int | None = None
    frame_digest: str = ""
    complete: bool = False
    mobility_executed: bool = False
    public_purchases: PublicPurchaseFrame | None = Field(default=None, exclude_if=_is_none)
    dropped_rows: int = 0
    counters: dict[str, float] = Field(default_factory=lambda: {
        "frames": 0, "incomplete_frames": 0, "rows": 0, "dropped_rows": 0,
        "observed_starts": 0, "unknown_voyage_rows": 0,
        "regional_cargo_raided": 0.0, "virtual_cargo_raided": 0.0,
    })

    def __setstate__(self, state):
        super().__setstate__(state)
        # Pydantic pickle restores __dict__ directly; old exact checkpoints
        # do not run JSON validators/default filling. Missing means unknown.
        self.__dict__.setdefault("public_purchases", None)


def transaction_receipts_on(world) -> bool:
    return isinstance(getattr(world, "transaction_receipts", None), TransactionReceiptState)
