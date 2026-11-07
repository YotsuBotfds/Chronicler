"""Persisted state of poor relief as a real service (D1a, ``--reform-services``, default off).

Owned by :mod:`chronicler.reform_services`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it. A world that
never enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: regions are indices in ``world.regions``; civilizations are
indices in ``world.civilizations``; a reform is its index in
``MovementState.reforms``. No person's id is persisted here (owners are paid by
stable id through the payment seam, whose book keeps only the last settled
turn's flows).

Units: money in whole milli-units (1000 = one treasury unit = one native wealth
unit, the payment seam's unit); food in whole milli-food (the retail ledger's
unit); rations (one person's food for a turn) as floats rounded to six digits.

Everything is bounded: one fund per civilization, the purchases awaiting
their delivery reading (at most one per pilot region), one completed-turn
frame, a rolling dated log (``MAX_LOG``) and scalar counters with the fixed key
set ``COUNTERS``. Tuple orders are declaration orders: append, never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.money import MoneyBook

#: ``--reform-services-mode`` choices (the first is the default when enabled).
MODES: tuple[str, ...] = ("service", "cost_only")
#: Where a turn's relief money came from.
PATHS: tuple[str, ...] = ("upkeep", "institution")
#: Dated log kinds.
LOG_KINDS: tuple[str, ...] = (
    "switched_on", "switched_off", "fund_refunded", "purchase_refused", "institution_share_unknown",
    "delivery_unobserved",
)
MAX_LOG = 64
#: Scalar lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns", "credit_rows_withheld", "upkeep_to_fund_units", "institution_to_fund_units", "sunk_units",
    "purchases", "food_bought_milli", "cost_milli", "credited_milli", "residual_milli",
    "refunded_to_treasury_milli", "purchases_refused", "need_without_owned_food", "need_without_fund",
    "deliveries_measured", "deliveries_unobserved", "delivered_at_least_milli", "delivered_at_most_milli",
)


class Purchase(BaseModel):
    """Food a relief fund bought from a pilot region's owners this turn, into the
    region's commons (the free pool of the next provisioning)."""

    region: int
    civ: int
    reform: int
    #: The provisioning's recorded unmet need (persons - rations) that asked for it.
    unmet_rations: float
    price_milli: int                 # the region's installed ask, milli per ration
    food_milli: int                  # bought from owners, milli-food
    goods_milli: list[int] = Field(default_factory=list)   # per good (retail goods order)
    rations: float                   # food_milli / (ration x 1000)
    cost_milli: int                  # the bill: ceil(food x price / ration)
    credited_milli: int              # applied to the owners by stable id
    residual_milli: int              # refused by a wealth ceiling, back in the fund
    sellers: int


class Delivery(BaseModel):
    """The next provisioning of a region where relief food was bought: the free
    pool it joined and what that pool gave. The relief food is pooled with the
    commons, so what reached people is bounded, never attributed by person:
    at most ``min(bought, free given)``; at least what the free pool gave beyond
    everything else in it (``min(bought, free pool) - free unallocated``)."""

    region: int
    civ: int
    bought_turn: int
    rations_bought: float
    observed: bool = True
    free_rations: float | None = None
    free_given: float | None = None
    free_unallocated: float | None = None
    delivered_at_least: float | None = None
    delivered_at_most: float | None = None
    priced_out_persons: int | None = None
    unmet_rations: float | None = None


class CivRelief(BaseModel):
    """One civilization's relief money in one turn."""

    civ: int
    reform: int | None = None        # the relief in force (None: none; the fund is refunded)
    path: str | None = None          # PATHS: how this turn's relief money was paid
    fund_open_milli: int = 0
    to_fund_milli: int = 0           # this turn's upkeep (or institution share) paid into the fund
    sunk_units: int = 0              # this turn's relief payment beyond the fund's cap, sunk as before
    spent_milli: int = 0             # purchase bills applied
    residual_milli: int = 0          # ceiling residuals returned to the fund
    refunded_milli: int = 0          # returned to the treasury (the relief ended)
    fund_close_milli: int = 0
    cap_milli: int = 0


class ReliefFrame(BaseModel):
    turn: int
    civs: list[CivRelief] = Field(default_factory=list)
    purchases: list[Purchase] = Field(default_factory=list)
    deliveries: list[Delivery] = Field(default_factory=list)


class ReliefRecord(BaseModel):
    turn: int
    kind: str                        # LOG_KINDS
    civ: int | None = None
    region: int | None = None
    milli: int | None = None
    note: str = ""


class ReformServicesState(BaseModel):
    """What poor relief as a service must remember across turns."""

    enabled: bool = True
    mode: Literal["service", "cost_only"] = "service"
    #: Each civilization's relief fund, milli (civ index -> balance; zero omitted).
    funds: dict[int, int] = Field(default_factory=dict)
    #: The payment seam's book (settled keys, treasury carries, last turn's flows).
    book: MoneyBook = Field(default_factory=MoneyBook)
    #: Purchases of the last turn whose delivery the next provisioning shows.
    pending: list[Purchase] = Field(default_factory=list)
    pending_turn: int | None = None
    frame: ReliefFrame | None = None
    frame_turn: int | None = None
    log: list[ReliefRecord] = Field(default_factory=list)
    log_dropped: int = 0
    counters: dict[str, int] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 -> Phase 10): civ -> CivRelief of this
    # turn's payments into the fund. Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state
