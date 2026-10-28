"""Optional Python-authoritative merchant observation identity, not ownership."""
from __future__ import annotations

from pydantic import BaseModel, Field


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


class TransactionReceiptState(BaseModel):
    namespace: str = "trajectory"
    max_rows: int = Field(default=4096, ge=1, le=65536)
    active: dict[int, ActiveVoyage] = Field(default_factory=dict)
    frame: list[TransactionObservation] = Field(default_factory=list)
    source_turn: int | None = None
    frame_digest: str = ""
    complete: bool = False
    mobility_executed: bool = False
    dropped_rows: int = 0
    counters: dict[str, float] = Field(default_factory=lambda: {
        "frames": 0, "incomplete_frames": 0, "rows": 0, "dropped_rows": 0,
        "observed_starts": 0, "unknown_voyage_rows": 0,
        "regional_cargo_raided": 0.0, "virtual_cargo_raided": 0.0,
    })


def transaction_receipts_on(world) -> bool:
    return isinstance(getattr(world, "transaction_receipts", None), TransactionReceiptState)
