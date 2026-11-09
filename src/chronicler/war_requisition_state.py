"""D4 persisted physical food transfers and public restitution liabilities.

Food is milli-food; army kits are whole rations (one food = two rations).
No second spendable balance: liabilities are promises, paid only by money.py.
"""
from __future__ import annotations
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, PrivateAttr
from chronicler.money import MoneyBook
from chronicler.switch_state import SwitchStateMixin

MODES = ("transfer", "cost_only")
MAX_ROWS = 256
MAX_CLAIMS = 4096
COUNTERS = ("events", "removed_milli", "rations_credited", "destroyed_milli",
            "refill_requested", "refill_credited", "refill_food_milli", "forage_food_milli",
            "initial_requested", "initial_credited", "cargo_seized_milli", "claims_due_milli",
            "restitution_paid_milli", "claims_lapsed_milli", "claims_unrecorded_milli",
            "pool_resets", "frames")

class RestitutionClaim(BaseModel):
    id: int
    turn: int
    payer: int
    owner: int
    region: int
    due_milli: int
    paid_milli: int = 0
    source: str
    status: str = "open"

class WarRequisitionState(SwitchStateMixin, BaseModel):
    _sim: Any = PrivateAttr(default=None)
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["transfer", "cost_only"] = "transfer"
    next_claim: int = 0
    claims: list[RestitutionClaim] = Field(default_factory=list)
    book: MoneyBook = Field(default_factory=MoneyBook)
    counters: dict[str, int] = Field(default_factory=dict)
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    events_turn: int | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    events_dropped: int = 0
    last_settled_turn: int | None = None
    # Physical logistics must execute at most once for each army and source turn.
    supply_turn: int | None = None
    supplied: list[str] = Field(default_factory=list)
    feeding_turn: int | None = None
    feeding: dict[str, float] = Field(default_factory=dict)
    fed_ids: dict[int, float] = Field(default_factory=dict)
    census_turn: int | None = None
    census_ids: list[int] = Field(default_factory=list)

    _FILL_DEFAULTS: ClassVar[bool] = True
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "coerce": int}
