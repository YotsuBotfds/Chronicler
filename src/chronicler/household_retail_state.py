"""Persisted state of L6b household food retail (``--household-retail``, default off).

Owned by :mod:`chronicler.household_retail`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: people are native stable ids (never slot indexes); regions are
indices in ``world.regions``. Food is in whole milli-food (1000 = one model
food unit = two rations); money in whole milli-units (1000 = one native
wealth unit = one treasury unit), as the native wealth transfer counts it.

One entry per pilot region holds the owned food: ``goods`` (milli-food per
food good, in ``RETAIL_GOODS`` order) and ``claims`` (owner stable id ->
milli-food), with sum(claims) == sum(goods) exactly. Everything else is
bounded: the claims cap (``MAX_CLAIMS`` entries over the world; a farmer or
heir beyond it is refused and counted, the share stays commons), one
completed-turn frame (one row per pilot region, a bounded person sample),
a rolling dated record log (``MAX_LOG``) and scalar lifetime counters.
Owned food is never in ``region.stockpile`` (that is the commons).

The ledger is id-bound: a rebuilt native pool closes every claim to the
commons, dated (``household_retail.on_pool_reset``).

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Modes (first: the default when enabled). Native ``set_household_retail``
#: codes: retail 0, no_relief 1, free_exchange 2; record_only installs nothing.
MODES: tuple[str, ...] = ("retail", "no_relief", "free_exchange", "record_only")
NATIVE_MODES: dict[str, int] = {"retail": 0, "no_relief": 1, "free_exchange": 2}
#: Pilot boundaries (first: the default).
BOUNDARIES: tuple[str, ...] = ("market", "paid_work", "all")
#: Food goods of the owned pool, in the FFI column order
#: (``retail_owned_<good>``, ``retail_titled_<good>``, ...).
RETAIL_GOODS: tuple[str, ...] = ("grain", "fish", "salt", "botanicals", "exotic")
#: Why a region entered the pilot.
OPEN_REASONS: tuple[str, ...] = ("capital", "paid_work", "all")
#: Flows of the owned pool. Each moves goods (per good) and claims (per
#: owner) by the same total, except ``inherited_in``/``inherited_out``, which
#: move claims between owners of one region and never goods.
FLOW_KINDS: tuple[str, ...] = (
    "titled", "own_eaten", "sold", "procured", "decay", "overflow", "war_loss", "to_commons",
    "inherited_in", "inherited_out",
)
#: Signs of the flows in ``close = open + sum(sign x flow)``.
FLOW_SIGNS: dict[str, int] = {
    "titled": 1, "own_eaten": -1, "sold": -1, "procured": -1, "decay": -1, "overflow": -1,
    "war_loss": -1, "to_commons": -1, "inherited_in": 1, "inherited_out": -1,
}
#: Why owned food went to the region's commons (``region.stockpile``).
COMMONS_REASONS: tuple[str, ...] = (
    "untitled", "claims_refused", "escheat", "pilot_closed", "pool_reset", "switch_off",
)
#: Dated record kinds.
RECORD_KINDS: tuple[str, ...] = (
    "pilot_opened", "pilot_closed", "war_loss", "inherited", "escheat", "pool_reset",
    "claims_refused", "switch_off",
)
#: Person sample statuses (native code order).
SAMPLE_STATUSES: tuple[str, ...] = ("fed", "priced_out", "offer_short")

MAX_CLAIMS = 4096
MAX_LOG = 64
MAX_SAMPLE = 24

#: Lifetime counters (insertion order). ``*_milli`` are milli-food or
#: milli-units (money: ``paid``, ``credited``, ``refunded``, ``procurement``).
COUNTERS: tuple[str, ...] = (
    "turns_settled", "turns_unobserved", "turns_not_taken", "pilot_region_turns",
    "regions_opened", "regions_closed", "claims_refused", "owners_titled",
    "titled_milli", "untitled_milli", "own_eaten_milli", "sold_milli", "procured_milli",
    "decay_milli", "overflow_milli", "war_loss_milli", "to_commons_milli", "inherited_milli",
    "escheat_milli", "deaths", "pool_resets",
    "paid_milli", "credited_milli", "refunded_milli",
    "procurement_flows", "procurement_credited_milli", "procurement_residual_milli",
    "procurement_unpaid_milli", "requisition_exempt_region_turns",
    "priced_out_persons", "offer_short_persons", "income_replaced_rows",
    "crew_farm_time_person_turns", "crew_farm_time_micro",
)


def _is_none(value) -> bool:
    return value is None


class RetailRegion(BaseModel):
    """One pilot region's owned food. ``sum(claims) == sum(goods)``."""

    region: int
    opened_turn: int
    reason: str                                         # OPEN_REASONS
    goods: list[int] = Field(default_factory=lambda: [0] * len(RETAIL_GOODS))
    #: owner stable id -> milli-food (ascending id; positive entries only).
    claims: dict[int, int] = Field(default_factory=dict)
    #: Lifetime flows of this pilot entry, milli-food (FLOW_KINDS keys).
    totals: dict[str, int] = Field(default_factory=dict)


class RetailRecord(BaseModel):
    """A dated record: openings, closures, war losses, inheritance, escheat."""

    turn: int
    region: int
    kind: str                                           # RECORD_KINDS
    milli: int = 0
    owner: int | None = None                            # the owner concerned (the deceased for inheritance)
    other: int | None = None                            # the heir
    note: str | None = None


class RegionFrame(BaseModel):
    """One pilot region's completed turn. Food in milli-food; money milli-units.

    ``flows`` and ``commons`` are this turn's owned-pool flows (FLOW_KINDS,
    COMMONS_REASONS); ``open_milli + sum(sign x flows) == close_milli``.
    ``phase2`` copies the native economy's retail columns (food units),
    ``provisioning`` the native retail frame row (None: not observed this
    turn); ``price_milli`` and ``free_rations`` are what was installed."""

    region: int
    opened_turn: int
    open_milli: int
    close_milli: int
    goods_close: list[int]
    owners: int
    flows: dict[str, int] = Field(default_factory=dict)
    commons: dict[str, int] = Field(default_factory=dict)
    price_milli: int | None = None
    free_rations: float | None = None
    phase2: dict[str, float] | None = None
    provisioning: dict[str, float] | None = None
    #: record_only: what retail would have done this turn (title, price,
    #: free rations); None in every other mode.
    would_be: dict[str, float] | None = None


class HouseholdRetailState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["retail", "no_relief", "free_exchange", "record_only"] = "retail"
    boundary: Literal["market", "paid_work", "all"] = "market"
    #: Open pilot regions, ascending region index.
    regions: list[RetailRegion] = Field(default_factory=list)
    #: Exactly-once guards (persisted): the last turn whose harvest was
    #: titled, whose provisioning receipts were settled and whose
    #: procurement credits were paid.
    last_title_turn: int | None = None
    last_settled_turn: int | None = None
    last_procured_turn: int | None = None
    # One completed-turn frame.
    frame_turn: int | None = None
    frame: list[RegionFrame] = Field(default_factory=list)
    money: dict[str, int] = Field(default_factory=dict)
    income: dict[str, float] = Field(default_factory=dict)
    sample: list[list] = Field(default_factory=list)
    sample_dropped: int = 0
    #: Rolling dated record log (the last MAX_LOG records).
    log: list[RetailRecord] = Field(default_factory=list)
    log_dropped: int = 0
    #: Scalar lifetime counters (bounded: the fixed ``COUNTERS`` key set).
    counters: dict[str, int] = Field(default_factory=dict)
    income_replaced_total: float = 0.0
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

    def claims_count(self) -> int:
        return sum(len(r.claims) for r in self.regions)

    def region(self, rid: int) -> RetailRegion | None:
        return next((r for r in self.regions if r.region == rid), None)
