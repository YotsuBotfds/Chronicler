"""Persisted state of PL3 recovery crews (``--recovery-crews``, default off).

Owned by :mod:`chronicler.recovery_crews`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: ``region`` is the index in ``world.regions``; ``payer`` is the
index in ``world.civilizations``; ``pid`` is the RS2 project's persisted
sequence number; agent ids are native stable ids. No other identifier is
invented.

Bounded: one completed-turn frame (at most ``MAX_FRAME_ROWS`` crew rows and
one ledger row per paying civilization) and scalar lifetime counters. Crews
are re-planned from the live pool every turn, so nothing id-bound outlives a
turn except the frame, which a rebuilt pool clears (``on_pool_reset``). A
world that never enabled the switch has no sub-state, so feature-off output
is unchanged.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin

#: Modes (first: the default when enabled). ``unpaid`` is the control: the
#: same crews, the same withheld income share and the same treasury charge,
#: with the granary coins leaving the economy as a material sink as before.
MODES: tuple[str, ...] = ("paid", "unpaid")
#: Crew kinds :func:`chronicler.recovery_crews.eligible_ids` serves.
KINDS: tuple[str, ...] = ("granary", "workshop", "woodcut")
#: Where a crew member's time comes from: ``site_city`` (an urban farmer of
#: the workshop's own city, already diverted from farming), ``urban_farmer``
#: (an urban farmer of another city of the region), ``rural_farmer``,
#: ``veteran`` (an RS3 veteran of a non-farming occupation).
ORIGINS: tuple[str, ...] = ("site_city", "urban_farmer", "rural_farmer", "veteran")

#: Every lifetime counter name; ``recovery_crews._bump`` refuses any other.
COUNTERS: frozenset[str] = frozenset({
    "settled_turns", "granary_crews", "granary_crew_person_turns", "granary_work_planned",
    "granary_work_named", "granary_crew_short", "granary_no_crew", "granary_wages_due_milli",
    "granary_wages_milli", "granary_wage_residual_milli", "granary_sunk_milli", "granary_coin_cost_milli",
    "workshop_crews", "workshop_crew_person_turns", "farm_time_removed", "income_replaced",
    "veterans_placed", "rows_dropped", "pool_resets", "turns_discarded",
    *(f"workshop_members_{origin}" for origin in ORIGINS),
    *(f"granary_members_{origin}" for origin in ORIGINS),
})

MAX_FRAME_ROWS = 64


class CrewMember(BaseModel):
    """One named crew member's turn."""

    agent_id: int
    origin: Literal["site_city", "urban_farmer", "rural_farmer", "veteran"]
    #: Share of the person's turn reserved in the work registry (``repair``).
    share: float
    #: Share actually worked and withheld from ordinary income (granary: the
    #: reserved share scaled by the delivered work; workshop: the share).
    worked: float
    #: Farm labour removed for this person (farmer-equivalents).
    farm_time: float = 0.0
    veteran: bool = False
    wage_due_milli: int = 0
    wage_milli: int = 0
    wage_residual_milli: int = 0
    #: Ordinary income the wealth phase withheld (None: not observed).
    income_replaced: float | None = None


class CrewReceipt(BaseModel):
    """One RS2 project's named crew in one completed Phase 2.

    Granary: ``planned`` is the work RS2 could fund and supply before the
    crew was named, ``capacity`` the named crew's farm time, ``requested``
    the native request (``min(planned, capacity)``) and ``delivered`` what
    the storage channel delivered. Paid mode pays ``coin_cost_milli`` (the
    granary's coins per delivered work) to the crew by delivered share; the
    part a wealth ceiling refuses, and in ``unpaid`` all of it, is ``sunk``.
    Workshop: the RS2 crew's composition (wages are RS2's own receipt).
    """

    turn: int
    pid: int
    kind: Literal["granary", "workshop"]
    region: int
    payer: int
    #: Eligible people in the region (after every exclusion) and, for a
    #: workshop, how many of them the site-city pool alone would have had.
    eligible: int
    eligible_site_city: int | None = None
    planned: float = 0.0
    capacity: float = 0.0
    requested: float = 0.0
    delivered: float = 0.0
    #: Granary: the free adult farmers ran out with at least ``MIN_SHARE`` of
    #: the planned work left (a smaller remainder counts as covered).
    short: bool = False
    members: list[CrewMember] = Field(default_factory=list)
    coin_cost_milli: int = 0
    wages_due_milli: int = 0
    wages_milli: int = 0
    wage_residual_milli: int = 0
    sunk_milli: int = 0
    farm_time_removed: float = 0.0


class CivCrewLedger(BaseModel):
    """One civilization's granary crew money in one turn (milli-units).
    Closure: ``coin_cost_milli == wages_milli + sunk_milli`` and
    ``wages_milli + wage_residual_milli == wages_due_milli``; the coin cost
    is the part of RS2's own charge (``CivLedger.coin_cost_milli``) that the
    crews' granaries cost, so the treasury charge is the same in both modes."""

    turn: int
    civ: int
    coin_cost_milli: int
    wages_due_milli: int
    wages_milli: int
    wage_residual_milli: int
    sunk_milli: int


class RecoveryCrewsState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["paid", "unpaid"] = "paid"
    #: The last completed turn's frame (None: that turn had no settled Phase 2).
    frame_turn: int | None = None
    receipts: list[CrewReceipt] | None = None
    ledger: list[CivCrewLedger] | None = None
    rows_dropped: int = 0
    last_settled_turn: int | None = None
    counters: dict[str, float] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 -> Phase 10); never serialized.
    _turn: object | None = PrivateAttr(default=None)

    _FILL_DEFAULTS: ClassVar[bool] = True
    _FILL_PRIVATE: ClassVar[tuple[str, ...]] = ("_turn",)
    _TRANSIENT: ClassVar[tuple[str, ...]] = ("_turn",)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "message": "undeclared recovery-crews counter {key!r}"}
