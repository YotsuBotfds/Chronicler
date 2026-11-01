"""Bounded public grain cargo, with no runtime or simulation imports."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

MAX_PENDING = 64
MAX_PER_DEST = 2
MAX_FRAME = 2 * MAX_PENDING
MAX_ORDER = (1 << 63) - 1
COUNTERS = ("dispatched", "arrived", "sent", "committed_net", "transit_loss", "paid",
            "delivered", "captured_delivery", "unguarded_delivery", "capacity_refusals", "identity_refusals")


def shipment_id(dispatch_turn: int, order: int) -> str:
    """Ordinary monotone-turn trajectory identity; fork provenance is separate."""
    return f"public-grain-shipment:{dispatch_turn}:{order}"


class PublicGrainOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: int = Field(ge=0, lt=MAX_ORDER, strict=True)
    source: int = Field(ge=0, le=65534, strict=True)
    source_name: str = Field(min_length=1, strict=True)
    dest: int = Field(ge=0, le=65534, strict=True)
    dest_name: str = Field(min_length=1, strict=True)
    buyer: int = Field(ge=0, le=253, strict=True)
    buyer_name: str = Field(min_length=1, strict=True)
    seller: int = Field(ge=0, le=253, strict=True)
    seller_name: str = Field(min_length=1, strict=True)
    dispatch_turn: int = Field(ge=0, strict=True)
    due_turn: int = Field(ge=1, strict=True)
    sent: float = Field(gt=0, allow_inf_nan=False, strict=True)
    net: float = Field(gt=0, allow_inf_nan=False, strict=True)
    loss: float = Field(ge=0, allow_inf_nan=False, strict=True)
    paid: int = Field(gt=0, strict=True)


class PublicGrainTransition(PublicGrainOrder):
    id: str = Field(min_length=1, strict=True)
    operation: Literal["dispatched", "arrived"]
    turn: int = Field(ge=0, strict=True)
    keeper: int = Field(ge=-1, le=253, strict=True)


class PublicGrainShipmentState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    accept_orders: bool = True
    next_order: int = Field(default=0, ge=0, le=MAX_ORDER, strict=True)
    last_arrivals_turn: int | None = None
    pending: list[PublicGrainOrder] = Field(default_factory=list, max_length=MAX_PENDING)
    frame_turn: int | None = None
    frame: list[PublicGrainTransition] = Field(default_factory=list, max_length=MAX_FRAME)
    counters: dict[str, float] = Field(default_factory=lambda: {key: 0.0 for key in COUNTERS})
