"""Persisted state of L7 costly voluntary relocation (``--relocation-costs``).

Owned by :mod:`chronicler.relocation_costs`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: regions are indices in ``world.regions``; civilizations are
indices in ``world.civilizations``; people are native stable ids; a
household is named by its lead (lowest member id) and the turn it moved.
Money is in whole milli-units (1000 = one native wealth unit = one treasury
unit, the equivalence the L6a wealth transfer uses). Everything is bounded:
one completed-turn frame (a bounded household sample, touched regions,
service receipts and assistance charges), the previous turn's tracked
arrivals and scalar lifetime counters.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values, native codes and counters are keyed by them).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Modes (first: the default when enabled). ``liquidity_only`` is the
#: control: the same fare gate, nothing paid.
MODES: tuple[str, ...] = ("paid", "assisted", "liquidity_only")
#: Native gate reason codes (``relocation.rs``), in code order.
GATE_REASONS: tuple[str, ...] = ("passed", "short", "no_local_distress", "route", "trip", "assisted")
#: Settlement statuses of an assistance grant (append only).
ASSISTANCE_STATUSES: tuple[str, ...] = ("charged", "controller_changed", "treasury_short")
#: Native wealth-transfer row statuses, in code order.
TRANSFER_STATUSES: tuple[str, ...] = ("applied", "limited", "absent")

MAX_HOUSEHOLDS = 64
MAX_TRACKED = 256

#: Lifetime counters (insertion order; the funnel reads them). ``*_milli``
#: are money; the rest count households (``groups``) or people (``persons``).
COUNTERS: tuple[str, ...] = (
    "turns", "groups_proposed", "persons_proposed",
    "groups_passed", "groups_assisted", "groups_short", "groups_unpriced",
    "persons_short", "groups_applied", "persons_applied", "children_applied",
    "groups_paid", "fare_due_milli", "fare_debited_milli", "fare_residual_milli",
    "fare_not_charged_milli", "assistance_granted_milli", "assistance_charged_milli",
    "assistance_refused_milli", "travel_sink_milli", "groups_with_residual",
    "returns", "service_receipts", "assistance_rounding_milli",
)


class HouseholdMove(BaseModel):
    """One priced or unpriced household group at the gate, and what was paid."""

    turn: int
    lead: int
    from_region: int
    to_region: int
    members: list[int] = Field(default_factory=list)
    adults: list[int] = Field(default_factory=list)
    children: int = 0
    liquid: int = 0                     # adult movers' liquid milli at the gate
    reason: str
    applied: bool = False
    fare: int = 0                       # the household's whole fare
    assistance: int = 0                 # granted by the destination's ruler
    payer: int = -1
    movers_share: int = 0               # fare - assistance
    debits: list[tuple[int, int, int, int, str]] = Field(default_factory=list)  # (id, requested, applied, residual, status)
    paid: int = 0                       # actually debited (positive)
    residual: int = 0                   # movers' share not debited
    assistance_status: str | None = None
    is_return: bool = False


class RegionPressure(BaseModel):
    """A region's arrivals and departures this turn, with crowding before and after the moves."""

    region: int
    capacity: int
    alive_before: int
    alive_after: int
    arrivals: int = 0
    arrival_households: int = 0
    assisted_households: int = 0
    departures: int = 0
    departure_households: int = 0
    pressure_before: float | None = None
    pressure_after: float | None = None
    food_sufficiency: float | None = None


class ServiceReceipt(BaseModel):
    """Last turn's tracked arrivals in the region where they now live: the food
    signal they read this turn and, with an L2 allocation, their own rations
    against the residents' (None: unknown, never zero)."""

    region: int
    arrival_turn: int
    food_sufficiency: float | None = None
    arrivals_rationed: int | None = None
    arrivals_mean_ration: float | None = None
    residents_rationed: int | None = None
    residents_mean_ration: float | None = None


class AssistanceCharge(BaseModel):
    civ: int
    turn: int
    granted: int                        # milli-units promised at the gate
    charged_coins: int = 0              # whole treasury units paid (ceil of the granted milli)
    refused: int = 0                    # milli-units left unfunded (a residual)
    status: str


class RelocationCostsState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["paid", "assisted", "liquidity_only"] = "paid"
    last_settled_turn: int | None = None
    last_assistance_turn: int | None = None
    frame_turn: int | None = None
    gate: dict[str, int] = Field(default_factory=dict)
    households: list[HouseholdMove] = Field(default_factory=list)
    households_dropped: int = 0
    regions: list[RegionPressure] = Field(default_factory=list)
    services: list[ServiceReceipt] | None = None
    assistance: list[AssistanceCharge] = Field(default_factory=list)
    tracked: list[int] = Field(default_factory=list)
    tracked_turn: int | None = None
    #: Each tracked arrival's origin region (to name returns next time).
    origins: dict[int, int] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)
    _pending: object | None = PrivateAttr(default=None)
    _assist: object | None = PrivateAttr(default=None)
