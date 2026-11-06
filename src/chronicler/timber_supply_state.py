"""Persisted state of PL1 timber supply (``--timber-supply``, default off).

Owned by :mod:`chronicler.timber_supply`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: ``home``, ``forest`` and every other ``region`` are indices in
``world.regions``; ``civ`` is an index in ``world.civilizations``; crew
members are native stable ids. An expedition's ``eid`` is a persisted
sequence number, never reused; no other identifier is invented.

Units: timber in the goods the economy counts (``slot_output``, stockpiles);
money in whole milli-units (1000 = one treasury or wealth unit); labour in
headcount (one person's whole turn).

Bounded: at most one live expedition per home region and one per forest
region, ``MAX_CLOSED`` closed expeditions, ``MAX_DROPS`` dated crew drops and
``MAX_HISTORY`` dated history entries per expedition, and one completed-turn
frame (one receipt per live expedition, one ledger row per paying civ, one
store row per touched region, at most ``MAX_NEEDS`` need rows). A world that
never enabled the switch has no sub-state, so feature-off output is unchanged.

``cost_only`` is the cost-retaining control: the same expeditions, crews,
travel, wages and home labour removal, but no cutting labour is applied, so
no timber is cut and no stock is debited.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Modes (first: the default when enabled).
MODES: tuple[str, ...] = ("supply", "cost_only")
#: The legs of an expedition, in order (``outbound`` and ``returning`` take
#: one turn per hop; a forest in the home region has neither).
STAGES: tuple[str, ...] = ("outbound", "cutting", "returning")
#: ``returned``: the crew came home with nothing to deliver (cost_only, or
#: nothing cut), never counted as a delivery.
STATUSES: tuple[str, ...] = ("live", "delivered", "abandoned", "returned")
#: Why no expedition was launched for a region with a gap (the first check
#: that failed, in this order).
REFUSALS: tuple[str, ...] = ("no_forest", "too_far", "forest_depleted", "forest_busy", "no_crew", "no_coins")
#: Why a crew member left the crew (observed in Phase 2 or after the tick).
DROP_REASONS: tuple[str, ...] = ("died", "migrated", "enlisted", "on_trip", "other_work")
#: Why an expedition ended before delivering; its cargo is deposited in the
#: forest region's stockpile as commons (``abandoned``). ``no_coins`` is no
#: longer an ending (an unpayable turn recalls the crew) and stays declared.
END_REASONS: tuple[str, ...] = ("crew_lost", "no_coins", "home_lost", "forest_lost", "pool_reset",
                                "switched_off")
#: Why the cutting stage ended (``completed``: all ``CUT_TURNS`` worked;
#: ``recalled``: a turn the civ could not pay).
CUT_ENDS: tuple[str, ...] = ("completed", "forest_depleted", "forest_lost", "recalled")
#: A region's need row: ``supplied`` (no gap worth an expedition), ``expedition``
#: (one is already live for it), ``launched`` or ``refused``.
NEED_STATUSES: tuple[str, ...] = ("supplied", "expedition", "launched", "refused")

#: Every lifetime counter name (``TimberSupplyState.counters``);
#: ``timber_supply._bump`` refuses any other.
COUNTERS: frozenset[str] = frozenset({
    "settled_turns", "launched", "delivered_expeditions", "need_rows", "want", "gap",
    "person_turns", "cut", "lost", "delivered", "released", "store_held", "store_returned",
    "wages_due_milli", "wages_milli", "wage_residual_milli", "charged", "prepaid_written_off_milli",
    "income_withheld", "away_requested", "away_delivered", "crew_labor", "veterans_placed",
    "pool_resets", "launched_veterans",
    "abandoned_cargo", "unpaid_turns", "recalls", "ended", "ended_wages_milli", "ended_person_turns",
    "ended_away", "ended_cut", "ended_delivered", "ended_unpaid_turns",
    "returned_expeditions", "soldier_veterans", "switched_off_cargo", "switched_off_store",
    *(f"refused_{reason}" for reason in REFUSALS),
    *(f"abandoned_{reason}" for reason in END_REASONS),
    *(f"dropped_{reason}" for reason in DROP_REASONS),
    *(f"cut_end_{reason}" for reason in CUT_ENDS),
    *(f"crew_turns_{stage}" for stage in STAGES),
    *(f"need_{status}" for status in NEED_STATUSES),
})

MAX_CLOSED = 32
MAX_DROPS = 16
MAX_HISTORY = 24
MAX_NEEDS = 128


class Expedition(BaseModel):
    """One woodcutting expedition: a named crew from ``home`` cutting the
    first timber slot (``slot``) of ``forest`` and carrying the timber home.

    ``cargo`` is the timber cut and carried, before the transit decay of the
    way home; ``cut`` the lifetime harvest. Always ``cut == cargo + delivered +
    lost + abandoned``: ``lost`` is transit decay only; ``abandoned`` the cargo
    of an expedition that ended without delivering, deposited in the forest
    region's stockpile as commons."""

    eid: int
    civ: int
    home: int
    forest: int
    slot: int
    hops: int
    launched_turn: int
    status: Literal["live", "delivered", "abandoned", "returned"] = "live"
    stage: Literal["outbound", "cutting", "returning"]
    #: Worked turns in the current stage.
    stage_turns: int = 0
    #: Hops travelled on the way out.
    travelled: int = 0
    #: Hops the way home takes (``hops`` once at the forest).
    return_hops: int = 0
    #: The schedule is complete: the crew delivers in this turn's Phase 10.
    arrived: bool = False
    crew: list[int] = Field(default_factory=list)
    launched_crew: list[int] = Field(default_factory=list)
    #: Crew members who held an open RS3 record at launch.
    veterans: list[int] = Field(default_factory=list)
    #: Veterans admitted while of Soldier occupation (RS3's priority list,
    #: on no army roster); Soldier occupation alone does not drop them.
    soldier_veterans: list[int] = Field(default_factory=list)
    #: The home region's gap (timber a turn) the expedition was launched for.
    need: float = 0.0
    cargo: float = 0.0
    cut: float = 0.0
    cut_turns: int = 0
    cut_end: str | None = None
    worked_turns: int = 0
    person_turns: int = 0
    wages_milli: int = 0
    wage_residual_milli: int = 0
    income_withheld: float = 0.0
    away_requested: float = 0.0
    away_delivered: float = 0.0
    delivered: float = 0.0
    lost: float = 0.0
    abandoned: float = 0.0
    #: Return-leg turns walked unpaid (the civ could not pay them).
    unpaid_turns: int = 0
    #: The turn an unpayable turn recalled the crew (None: never recalled).
    recalled_turn: int | None = None
    ended_turn: int | None = None
    end_reason: str | None = None
    #: (turn, stable id, reason), the last ``MAX_DROPS``.
    drops: list[tuple[int, int, str]] = Field(default_factory=list)
    #: (turn, event), the last ``MAX_HISTORY``.
    history: list[tuple[int, str]] = Field(default_factory=list)


class ExpeditionReceipt(BaseModel):
    """One expedition's completed Phase 2 (a turn its crew worked)."""

    turn: int
    eid: int
    civ: int
    home: int
    forest: int
    slot: int
    #: The stage the crew worked this turn.
    stage: Literal["outbound", "cutting", "returning"]
    crew: list[int] = Field(default_factory=list)
    veterans: list[int] = Field(default_factory=list)
    #: (stable id, reason) of members who left the crew at this Phase 2.
    dropped: list[tuple[int, str]] = Field(default_factory=list)
    #: Headcount farm labour asked off the home land and what the economy removed.
    away_requested: float = 0.0
    away_delivered: float = 0.0
    #: Headcount added to the forest's timber slot (0 outside cutting and in cost_only).
    crew_labor: float = 0.0
    #: The crew's marginal harvest (``woodcut_output``).
    cut: float = 0.0
    cargo_after: float = 0.0
    #: The forest slot's L3 account this turn (cutting only; None otherwise).
    stock_before: float | None = None
    stock_after: float | None = None
    capacity: float | None = None
    wages_due_milli: int = 0
    wages_milli: int = 0
    wage_residual_milli: int = 0
    #: Ordinary income the native wealth phase withheld for the paid share
    #: (None: not observed).
    income_withheld: float | None = None
    #: Why the cutting stage ended at the start of this turn, if it did.
    cut_end: str | None = None
    #: The civ could not pay this turn: the crew walked home unpaid
    #: (reserved and away, ordinary income withheld, no wage).
    unpaid: bool = False
    #: This turn's unpayable wages recalled the expedition.
    recalled: bool = False


class WageLedger(BaseModel):
    """One civilization's expedition wages in one turn. The treasury pays whole
    units once; the sub-unit part of the last unit is prepaid toward the
    civ's next wages. Exact closure: ``charged * 1000 + prepaid_before_milli ==
    wages_applied_milli + prepaid_after_milli`` and ``wages_applied_milli +
    wage_residual_milli == wages_due_milli``, both balances in [0, 1000)."""

    turn: int
    civ: int
    expeditions: int
    person_turns: int
    wages_due_milli: int
    wages_applied_milli: int
    wage_residual_milli: int
    charged: int
    prepaid_before_milli: int
    prepaid_after_milli: int


class StoreRow(BaseModel):
    """One region's RS2-earmarked timber store in one turn: ``opening - held
    + returned + delivered - released == closing``."""

    region: int
    opening: float
    held: float = 0.0          # taken by RS2's holds before the economy tick
    returned: float = 0.0      # returned unused by RS2 after it
    delivered: float = 0.0     # cargo that arrived home
    released: float = 0.0      # left in a region without an open project: to the stockpile
    closing: float


class NeedRow(BaseModel):
    """A region with open RS2 projects at this turn's Phase 10: what they could
    use a turn at their caps, the timber already there or on its way, the gap
    and what was done about it."""

    region: int
    civ: int
    want: float
    #: Free timber RS2 sees (stockpile less merchant commitments, plus the store).
    free: float
    store: float
    #: Cargo of the region's live expeditions, after the way home's decay.
    in_transit: float
    gap: float
    status: Literal["supplied", "expedition", "launched", "refused"]
    reason: str | None = None
    eid: int | None = None


class TimberSupplyState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["supply", "cost_only"] = "supply"
    next_eid: int = 0
    #: Live expeditions, ascending ``eid``.
    expeditions: list[Expedition] = Field(default_factory=list)
    #: The last ``MAX_CLOSED`` ended expeditions.
    closed: list[Expedition] = Field(default_factory=list)
    #: region index -> timber delivered and earmarked for RS2 (> 0 only).
    store: dict[int, float] = Field(default_factory=dict)
    #: civ index -> milli-units already charged in whole units and not yet
    #: used (each in [0, 1000)); written off when the civ has no regions or
    #: the switch is turned off.
    prepaid: dict[int, int] = Field(default_factory=dict)
    #: The last completed turn's frame. ``receipts``/``ledger`` are None when
    #: that turn had no Phase 2 (unknown, not zero).
    frame_turn: int | None = None
    receipts: list[ExpeditionReceipt] | None = None
    ledger: list[WageLedger] | None = None
    stores: list[StoreRow] = Field(default_factory=list)
    #: (turn, eid, region, timber): cargo deposited as commons in the frame turn.
    deposits: list[tuple[int, int, int, float]] = Field(default_factory=list)
    #: region -> cargo of expeditions abandoned at a pool rebuild, deposited at
    #: the next Phase 10 (a rebuild can happen after the economy batch packed
    #: the stockpiles).
    pending_deposits: dict[int, float] = Field(default_factory=dict)
    needs: list[NeedRow] = Field(default_factory=list)
    needs_dropped: int = 0
    #: (turn, expeditions ended, cargo deposited, store released) of each
    #: ``--no-timber-supply``, the last 8.
    switched_off: list[tuple[int, int, float, float]] = Field(default_factory=list)
    last_settled_turn: int | None = None
    #: Scalar lifetime counters (bounded: the fixed ``COUNTERS`` key set).
    counters: dict[str, float] = Field(default_factory=dict)
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
