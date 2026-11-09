"""Checkpointed A4-3 timber procurement, title and real escrow (default off)."""
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, PrivateAttr
from chronicler.money import MoneyBook
from chronicler.switch_state import SwitchStateMixin

COUNTERS = (
    "dispatched", "delivered", "cancelled", "seized", "pool_reset", "expired",
    "bought_milli", "delivered_milli", "lost_milli", "deposited_milli",
    "purchase_milli", "escrowed_milli", "carrier_credited_milli", "refunded_milli",
    "ceiling_refused_milli", "carrier_turns", "income_withheld_micro", "orders_capped",
)
MAX_ORDERS, MAX_CLOSED, MAX_EVENTS = 64, 32, 256

class TimberOrder(BaseModel):
    id: int
    holder: int
    origin: int
    dest: int
    seller: int
    payer: int
    path: list[int]
    cursor: int = 0
    dispatched_turn: int
    last_moved_turn: int | None = None
    status: Literal["moving", "closed"] = "moving"
    outcome: str | None = None
    closed_turn: int | None = None
    cargo_open_milli: int
    cargo_milli: int
    delivered_milli: int = 0
    lost_milli: int = 0
    deposited_milli: int = 0
    purchase_milli: int
    sale_price_milli: int
    price_turn: int
    cash: int = 0
    escrowed_milli: int = 0
    credited_milli: int = 0
    refunded_milli: int = 0
    withheld: float = 0.0

class TimberOrdersState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    next_order: int = 0
    orders: list[TimberOrder] = Field(default_factory=list)
    closed: list[TimberOrder] = Field(default_factory=list)
    prices: dict[int, tuple[int, int]] = Field(default_factory=dict)
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    book: MoneyBook = Field(default_factory=MoneyBook)
    _turn: Any = PrivateAttr(default=None)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "message": "undeclared timber order counter {key}", "coerce": int}
    # Not _TRANSIENT: this always pickles exactly {"_turn": None}, even for a
    # missing or empty private dict.
    def __getstate__(self):
        state = super().__getstate__()
        state["__pydantic_private__"] = {"_turn": None}
        return state
