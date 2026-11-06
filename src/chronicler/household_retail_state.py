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

Rules versions (A5-1, ``--household-retail-rules``). Version 1 is the
checkpoint-2/3 rules: a conquest's share of owned stock is applied once per
turn, inferred from ``Region.last_conquered_turn``, and occupation and siege
do not reach owned stock. Version 2 (the default of every new state) applies
each war event once, at the event, with its cause, actor and victim
(``household_retail.on_conquest`` and ``on_war_loss``). A state saved before
A5 has no version field and reads as version 1, and a version-1 state omits
the field and every version-2 field, so its JSON keeps its bytes; pickles
written before A5 restore with the version-2 fields at their defaults.

A2R (connected-world lane, all opt-in): the ``schedule`` boundary
(``--household-retail-schedule PATH``) stores its frozen ``{region: opening
turn}`` map and the SHA-256 of its canonical JSON, both omitted while unset;
version 2 also keeps ``opened_turn`` (each region's first pilot turn, never
removed on closure) and writes the turn's household-group cohorts (RL5) into
the frame. A version-1 state writes neither, so its bytes stay checkpoint-3's.

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
#: Pilot boundaries (first: the default). ``schedule`` (A2R): a frozen
#: ``{region: opening turn}`` map read from ``--household-retail-schedule``.
BOUNDARIES: tuple[str, ...] = ("market", "paid_work", "all", "schedule")
#: Food goods of the owned pool, in the FFI column order
#: (``retail_owned_<good>``, ``retail_titled_<good>``, ...).
RETAIL_GOODS: tuple[str, ...] = ("grain", "fish", "salt", "botanicals", "exotic")
#: Why a region entered the pilot.
OPEN_REASONS: tuple[str, ...] = ("capital", "paid_work", "all", "schedule")
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
#: Rules versions (``--household-retail-rules`` choices are their strings);
#: the last is the default of a new state.
RULES_VERSIONS: tuple[int, ...] = (1, 2)
RULES_VERSION = 2
#: Version 2: causes of a war loss of owned stock, each applied once per event
#: (``conquest``: ``action_engine.apply_region_conquest``, aggregate WAR wins,
#: annexed occupations and treaty cessions alike; ``siege`` and
#: ``occupation``: ``war.occupation._requisition``).
WAR_CAUSES: tuple[str, ...] = ("conquest", "siege", "occupation")

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
    # Rules version 2 (A5-1): war losses by cause and the war events observed.
    "war_loss_conquest_milli", "war_loss_siege_milli", "war_loss_occupation_milli", "war_events",
    # Rules version 2 (A2R, RL4): owned grain a pilot market held above this
    # turn's storage cap at Phase 10, withheld from granary procurement.
    "owned_grain_above_cap_milli",
)
#: RL5 (version 2): household groups of the people provisioned in a pilot
#: region, in this order (a partition; ``household_retail.cohort_groups``).
COHORT_GROUPS: tuple[str, ...] = ("crew", "crew_children", "children_alone", "nonfarm_adults", "other")
#: Per-group fields of a cohort record (None: not attributable exactly).
COHORT_FIELDS: tuple[str, ...] = (
    "persons", "priced_out", "paid_milli", "refunded_milli", "credited_milli", "income_replaced", "wages_milli",
)


def _is_none(value) -> bool:
    return value is None


def _is_one(value) -> bool:
    return value == 1


class _Backfilled(BaseModel):
    """Exact pickle restoration bypasses defaults: fields added later read
    their default when an older pickle lacks them."""

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)


class RetailRegion(_Backfilled):
    """One pilot region's owned food. ``sum(claims) == sum(goods)``."""

    region: int
    opened_turn: int
    reason: str                                         # OPEN_REASONS
    goods: list[int] = Field(default_factory=lambda: [0] * len(RETAIL_GOODS))
    #: owner stable id -> milli-food (ascending id; positive entries only).
    claims: dict[int, int] = Field(default_factory=dict)
    #: Lifetime flows of this pilot entry, milli-food (FLOW_KINDS keys).
    totals: dict[str, int] = Field(default_factory=dict)
    #: ``last_conquered_turn`` of the last conquest whose loss was applied
    #: (version 2: of the last conquest the hook observed, loss or not).
    war_loss_turn: int = -1
    #: Version 2: war events observed in this pilot entry (monotone; None and
    #: omitted in a version-1 state).
    war_events: int | None = Field(default=None, exclude_if=_is_none)


class RetailRecord(_Backfilled):
    """A dated record: openings, closures, war losses, inheritance, escheat."""

    turn: int
    region: int
    kind: str                                           # RECORD_KINDS
    milli: int = 0
    owner: int | None = None                            # the owner concerned (the deceased for inheritance)
    other: int | None = None                            # the heir
    note: str | None = None
    #: Version 2 war losses (omitted when None, so version-1 logs keep their
    #: bytes): the cause (WAR_CAUSES), the acting civilization (conqueror,
    #: besieger or occupier) and the victim (the region's ruler at the event),
    #: each as its index in ``world.civilizations`` and its name at the event.
    cause: str | None = Field(default=None, exclude_if=_is_none)
    actor: int | None = Field(default=None, exclude_if=_is_none)
    actor_name: str | None = Field(default=None, exclude_if=_is_none)
    victim: int | None = Field(default=None, exclude_if=_is_none)
    victim_name: str | None = Field(default=None, exclude_if=_is_none)


class RegionFrame(_Backfilled):
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
    #: Ordinary farm income replaced this turn for the region's farmers, and rows.
    income_replaced: float | None = None
    income_rows: int | None = None
    #: Lead decision 7: food merchants committed from the commons this turn,
    #: and the owned food (milli-food) they could not load (foregone at most).
    merchant_food_departing: float | None = None
    owned_food_unloadable_milli: int | None = None
    #: Version 2 (A2R, RL5): the household-group cohorts of the people
    #: provisioned here this turn (``household_retail.cohorts``); omitted in a
    #: version-1 state and in a region without a provisioning row.
    cohorts: dict | None = Field(default=None, exclude_if=_is_none)


class HouseholdRetailState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["retail", "no_relief", "free_exchange", "record_only"] = "retail"
    boundary: Literal["market", "paid_work", "all", "schedule"] = "market"
    #: Retail rules version (RULES_VERSIONS). 1 when absent (a state saved
    #: before A5) and omitted while 1; a saved state keeps its version.
    rules_version: Literal[1, 2] = Field(default=1, exclude_if=_is_one)
    #: The ``schedule`` boundary (A2R): region index -> opening turn, ascending
    #: region, and the SHA-256 of its canonical JSON (compact, ascending
    #: region); fixed for the state's life, omitted while unset.
    schedule: dict[int, int] | None = Field(default=None, exclude_if=_is_none)
    schedule_sha256: str | None = Field(default=None, exclude_if=_is_none)
    #: Version 2 (A2R): each region's first pilot turn (region index -> turn),
    #: kept after a closure, so a bundle names every opening. A version-2
    #: state saved before A2R starts it from its open regions. Omitted in a
    #: version-1 state.
    opened_turn: dict[int, int] | None = Field(default=None, exclude_if=_is_none)
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

    @property
    def rules(self) -> str:
        """The rules version as the ``--household-retail-rules`` choice ("2" or "1")."""
        return str(self.rules_version)

    def claims_count(self) -> int:
        return sum(len(r.claims) for r in self.regions)

    def region(self, rid: int) -> RetailRegion | None:
        return next((r for r in self.regions if r.region == rid), None)
