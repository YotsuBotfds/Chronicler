"""Persisted state of A4 titled trade (``--titled-trade``, default off).

Owned by :mod:`chronicler.titled_trade`. Pure data with no simulation imports,
so :mod:`chronicler.livelihoods_state` can import it. A world that never
enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: a shipment is named by a monotone, persisted, never reused id
(``next_shipment``: Program E's ``shipment`` entity); people are native stable
ids (the holder of title, who is the merchant that bought the cargo, and the
carrier while reserved); regions are indices in ``world.regions``. Units:
food in whole milli-food per retail good (``household_retail_state.
RETAIL_GOODS`` order; 1000 = one model food unit = two rations), money in
whole milli-units (1000 = one native wealth unit), prices in milli-units per
ration (retail's price), withheld ordinary income in native wealth units (the
paid-work receipt's f32 values).

Title and custody live here while the cargo travels: it is never in a
region's commons (``region.stockpile``) or in a retail pool. Bought cargo
leaves the origin's retail pool (flow ``sold_merchant``); delivered cargo
becomes the holder's retail claim at the destination (``consigned_in``);
returned cargo the holder's claim at the origin (``returned_in``). Each
shipment closes with exactly one outcome (``OUTCOMES``) and its books close:
``sum(cargo_open) = transit_decay + sea_loss + delivered + returned +
deposited``.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.money import MoneyBook

#: How a shipment ended (append only). ``delivered``: consigned at the
#: destination (or deposited there when its claim was refused);
#: ``returned``: back to the origin at full value (a conquest of the
#: destination, a quarantine closure of its route, the route lost, the
#: destination left the pilot); ``escheated``: the holder died in transit
#: and the cargo went to the commons of the region it stood in;
#: ``pool_reset``: a rebuilt native pool (ids name strangers); cargo to the
#: commons where it stood; ``switched_off``: ``--no-titled-trade``, cargo to
#: the commons where it stood.
OUTCOMES: tuple[str, ...] = ("delivered", "returned", "escheated", "pool_reset", "switched_off")
#: Why a shipment returned (append only).
RETURN_CAUSES: tuple[str, ...] = (
    "destination_conquered", "quarantine_closure", "route_lost", "destination_left_pilot",
)
#: Why a carrier stopped being reserved while its shipment continued (the
#: holder keeps title; append only).
RELEASE_REASONS: tuple[str, ...] = ("migrated", "occupation", "enlisted", "on_trip", "other_work")
#: Why cargo went to a commons instead of a claim (append only).
DEPOSIT_REASONS: tuple[str, ...] = (
    "claims_refused", "not_pilot", "holder_died", "pool_reset", "switched_off",
)
#: Dated log kinds (append only).
LOG_KINDS: tuple[str, ...] = (
    "switched_on", "switched_off", "dispatched", "closed", "carrier_released", "pool_reset",
)
#: Loss kinds of a shipment's cargo (append only).
LOSS_KINDS: tuple[str, ...] = ("transit_decay", "sea_loss")

MAX_SHIPMENTS = 64
MAX_CLOSED = 32
MAX_LOG = 64
MAX_HISTORY = 16
MAX_LOTS = 256
MAX_FRAME_SELLERS = 16

#: Scalar lifetime counters (append only). ``*_milli``: milli-food or
#: milli-units (``paid``, ``credited``); ``income_withheld_micro``: the
#: carriers' withheld ordinary income in millionths of a wealth unit.
COUNTERS: tuple[str, ...] = (
    "dispatched", "delivered", "returned", "escheated", "pool_reset", "switched_off",
    "returned_destination_conquered", "returned_quarantine_closure", "returned_route_lost",
    "returned_destination_left_pilot",
    "bought_milli", "paid_milli", "sellers_paid", "seller_ceiling_refunded_milli",
    "transit_decay_milli", "sea_loss_milli", "consigned_milli", "returned_milli", "deposited_milli",
    "hops", "replanned", "war_exempt_turns", "carrier_turns", "carriers_released",
    "income_withheld_micro", "receipt_rows", "plans_no_margin", "plans_no_offer", "plans_no_cash",
    "plans_no_destination", "shipments_capped", "cargo_sold_milli", "cargo_sales_credited_milli",
    "cargo_sales_inexact_milli", "holder_procurement_credited_milli",
)


def _is_none(value) -> bool:
    return value is None


class _Backfilled(BaseModel):
    """Exact pickle restoration bypasses defaults: fields added later read
    their default when an older pickle lacks them."""

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)


class Shipment(_Backfilled):
    """One titled cargo, from purchase to its single outcome."""

    id: int
    goods: Literal["food"] = "food"
    #: Title: the merchant who bought the cargo (stable id); never changes.
    holder: int
    #: The carrier while reserved (the holder); None once released.
    carrier: int | None = None
    origin: int
    dest: int
    #: Region indices, origin first; ``cursor`` is the index of the current region.
    path: list[int] = Field(default_factory=list)
    cursor: int = 0
    #: Controllers (civ names) of the origin and destination at dispatch.
    controllers: list[str | None] = Field(default_factory=list)
    status: Literal["moving", "closed"] = "moving"
    dispatched_turn: int
    last_moved_turn: int | None = None
    #: Cargo now and at purchase, milli-food per retail good.
    cargo: list[int] = Field(default_factory=list)
    cargo_open: list[int] = Field(default_factory=list)
    #: What the holder paid the owners (milli-units), the origin's price per
    #: ration and how many owners sold.
    cost_milli: int = 0
    price_milli: int = 0
    sellers: int = 0
    #: Losses by kind (LOSS_KINDS), milli-food.
    losses: dict[str, int] = Field(default_factory=dict)
    delivered: int = 0
    returned: int = 0
    deposited: int = 0
    deposit_reason: str | None = None
    outcome: str | None = None
    cause: str | None = None
    closed_turn: int | None = None
    closed_region: int | None = None
    released: str | None = None
    #: Carrier ordinary income withheld while reserved (wealth units) and turns.
    withheld: float = 0.0
    withheld_turns: int = 0
    war_exempt_turns: int = 0
    #: Dated events: ``[turn, event, region]`` (at most MAX_HISTORY).
    history: list[list] = Field(default_factory=list)

    def region(self) -> int:
        return self.path[self.cursor]

    def total(self) -> int:
        return sum(self.cargo)


class Lot(_Backfilled):
    """Delivered cargo still held as the holder's claim at a destination
    (milli-food), for the holder's sales attribution (``consigned`` less what
    the claim lost since, clamped to the claim each turn)."""

    holder: int
    region: int
    milli: int
    shipments: list[int] = Field(default_factory=list)


class TradeRecord(_Backfilled):
    """A dated log record."""

    turn: int
    kind: str
    shipment: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TitledTradeState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    goods: Literal["food"] = "food"
    next_shipment: int = 0
    shipments: list[Shipment] = Field(default_factory=list)
    closed: list[Shipment] = Field(default_factory=list)
    lots: list[Lot] = Field(default_factory=list)
    book: MoneyBook = Field(default_factory=MoneyBook)
    #: Exactly-once guards (persisted): the last turn whose carriers'
    #: receipts were settled and whose Phase 10 trade ran.
    last_settled_turn: int | None = None
    last_trade_turn: int | None = None
    #: The completed turn's frame (JSON-ready; None: none yet).
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    log: list[TradeRecord] = Field(default_factory=list)
    log_dropped: int = 0
    # Transient, within one turn (Phase 2 -> Phase 10); never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        if getattr(self, "__pydantic_private__", None) is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None})
        else:
            self.__pydantic_private__.setdefault("_turn", None)

    def shipment(self, sid: int) -> Shipment | None:
        return next((s for s in self.shipments if s.id == sid), None)
