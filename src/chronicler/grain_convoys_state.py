"""Persisted state of the L4 public grain convoys (default off).

Owned by its package lane (:mod:`chronicler.grain_convoys`). Pure data with
no simulation imports, so :mod:`chronicler.livelihoods_state` can import it.

A convoy is a paid, buyer-titled public grain order bought from a foreign
market more than one route step from the buyer's granary. Region identity is
the index in ``world.regions`` and civilization identity the index in
``world.civilizations``; each record also keeps the names it was created
with so an edited universe is refused rather than silently rebound.

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values and counters are keyed by them).
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from chronicler.switch_state import SwitchStateMixin

MAX_ACTIVE = 64            # convoys on the road at once (all buyers)
MAX_PER_DEST = 2           # convoys bound for one granary at once
MAX_LEGS = 3               # route edges planned at dispatch or by one reroute
MAX_REROUTES = 2           # reroutes per convoy
MAX_ROUTE_NODES = 1 + MAX_LEGS * (1 + MAX_REROUTES)
MAX_FRAME = 2 * MAX_ACTIVE  # one movement transition per convoy plus this turn's dispatches
MAX_ID = (1 << 63) - 1

ROUTE_POLICIES: tuple[str, ...] = ("adaptive", "cheapest", "safest")
#: Statuses of a convoy still on the road (finished convoys leave the list).
ACTIVE_STATUSES: tuple[str, ...] = ("en_route", "waiting", "returning")
#: Transition operations (one per convoy per turn, plus dispatches).
OPERATIONS: tuple[str, ...] = (
    "dispatched", "advanced", "waited", "turned_back",
    "arrived", "captured", "lost", "returned", "stranded",
)
#: Why the next edge could not be taken this turn (then-current facts).
CLOSURES: tuple[str, ...] = ("uncontrolled", "hostile_holder", "hostile_army", "embargo", "route_closed")
#: Kinds of threat on an open edge (``sea``: pirates; ``brigands``: no captor).
THREATS: tuple[str, ...] = ("sea", "army", "frontier", "brigands")
#: Named sinks of cargo that leaves the convoy without reaching its granary.
SINKS: tuple[str, ...] = (
    "piracy", "raid", "captor_market", "captor_without_market", "origin_market", "stranded_market",
)

#: Cumulative counters (insertion order). Grain closure:
#: ``committed_net = delivered + captured_grain + lost_grain + returned_grain
#: + stranded_grain + cargo still on the road``.
COUNTERS: tuple[str, ...] = (
    "eligible", "no_budget", "no_route", "unaffordable", "capacity_refusals", "identity_refusals",
    "dispatched", "sent", "committed_net", "transit_loss", "paid", "escorted", "escort_paid",
    "legs", "waits", "reroutes", "turned_back", "threats", "repelled",
    "arrived", "delivered", "captured_delivery", "unguarded_delivery",
    "captured", "captured_grain", "lost", "lost_grain", "returned", "returned_grain",
    "stranded", "stranded_grain", "escort_wasted", "escort_wasted_paid",
)


def convoy_id(dispatch_turn: int, convoy: int) -> str:
    """Ordinary monotone-turn trajectory identity of one convoy."""
    return f"public-grain-convoy:{dispatch_turn}:{convoy}"


class GrainConvoy(BaseModel):
    """One convoy on the road (``GrainConvoyState.convoys``)."""

    model_config = ConfigDict(extra="forbid")
    convoy: int = Field(ge=0, lt=MAX_ID, strict=True)
    source: int = Field(ge=0, le=65534, strict=True)   # origin market region (seller's)
    source_name: str = Field(min_length=1, strict=True)
    dest: int = Field(ge=0, le=65534, strict=True)     # destination granary region
    dest_name: str = Field(min_length=1, strict=True)
    buyer: int = Field(ge=0, le=253, strict=True)      # title holder and payer
    buyer_name: str = Field(min_length=1, strict=True)
    seller: int = Field(ge=0, le=253, strict=True)     # origin market's ruler, paid at dispatch
    seller_name: str = Field(min_length=1, strict=True)
    dispatch_turn: int = Field(ge=0, strict=True)
    policy: Literal["adaptive", "cheapest", "safest"]
    route: list[int] = Field(min_length=2, max_length=MAX_ROUTE_NODES)  # region indices
    leg: int = Field(ge=0, strict=True)            # index in ``route`` of the node it is at or last left
    progress: int = Field(ge=0, strict=True)       # turns spent on the current edge (0: at ``route[leg]``)
    leg_turns: int = Field(ge=0, strict=True)      # turns the current edge takes (0: at a node)
    status: Literal["en_route", "waiting", "returning"]
    escorted: bool
    escort_fee: int = Field(ge=0, strict=True)     # paid at dispatch to the escort sink
    sent: float = Field(gt=0, allow_inf_nan=False)    # grain that left the origin market
    net: float = Field(gt=0, allow_inf_nan=False)     # grain loaded after transit decay
    loss: float = Field(ge=0, allow_inf_nan=False)    # transit decay booked at dispatch
    cargo: float = Field(gt=0, allow_inf_nan=False)   # grain still carried
    paid: int = Field(gt=0, strict=True)           # price paid to the seller's ruler
    waits: int = Field(ge=0, strict=True)          # consecutive turns blocked at the current node
    reroutes: int = Field(ge=0, strict=True)
    threats: int = Field(ge=0, strict=True)        # threats met on the road
    repelled: int = Field(ge=0, strict=True)       # threats an escort beat off
    # The choice at dispatch, from facts known then (no later information).
    exposed_route: list[int] = Field(min_length=2, max_length=MAX_LEGS + 1)
    exposed_risk: float = Field(ge=0, le=1, allow_inf_nan=False)
    exposed_turns: int = Field(ge=1, strict=True)
    escorted_route: list[int] = Field(min_length=2, max_length=MAX_LEGS + 1)
    escorted_risk: float = Field(ge=0, le=1, allow_inf_nan=False)
    escorted_turns: int = Field(ge=1, strict=True)


class ConvoyTransition(BaseModel):
    """What one convoy did in the recorded turn (``GrainConvoyState.frame``)."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    convoy: int = Field(ge=0, lt=MAX_ID, strict=True)
    turn: int = Field(ge=0, strict=True)
    operation: Literal["dispatched", "advanced", "waited", "turned_back",
                       "arrived", "captured", "lost", "returned", "stranded"]
    buyer: int = Field(ge=0, le=253, strict=True)
    buyer_name: str = Field(min_length=1)
    source: int = Field(ge=0, le=65534, strict=True)
    dest: int = Field(ge=0, le=65534, strict=True)
    at: int = Field(ge=0, le=65534, strict=True)   # region the convoy is in (or leaving) after this turn
    at_name: str = Field(min_length=1)
    route: list[int] = Field(min_length=2, max_length=MAX_ROUTE_NODES)
    leg: int = Field(ge=0, strict=True)
    progress: int = Field(ge=0, strict=True)
    status: str = Field(min_length=1)              # active status, or the final operation
    cargo: float = Field(ge=0, allow_inf_nan=False)  # cargo carried into this transition
    escorted: bool
    rerouted: bool = False
    closure: str | None = None                     # why the next edge was closed
    threat: str | None = None                      # threat met on the edge started this turn
    threat_risk: float | None = None               # then-current probability of a threat on that edge
    repelled: bool = False
    keeper: int | None = None                      # arrived: the granary's keeper (-1 none)
    sink: str | None = None                        # captured/lost/returned/stranded: where the cargo went
    sink_region: int | None = None
    captor: int | None = None
    paid: int | None = None                        # dispatched: price paid to the seller's ruler
    escort_fee: int | None = None                  # dispatched: escort sink payment


class GrainConvoyState(SwitchStateMixin, BaseModel):
    """``WorldState.livelihoods.grain_convoys``; None while never enabled."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    enabled: bool = True                           # accept new convoys (disabled: drain)
    route_policy: Literal["adaptive", "cheapest", "safest"] = "adaptive"
    next_convoy: int = Field(default=0, ge=0, le=MAX_ID, strict=True)
    convoys: list[GrainConvoy] = Field(default_factory=list, max_length=MAX_ACTIVE)
    moved_turn: int | None = None                  # last turn the movement pass ran
    dispatch_turn: int | None = None               # last turn the dispatch pass ran
    frame_turn: int | None = None
    frame: list[ConvoyTransition] = Field(default_factory=list, max_length=MAX_FRAME)
    counters: dict[str, float] = Field(default_factory=lambda: {key: 0.0 for key in COUNTERS})
    # Exact pickle restoration bypasses Pydantic defaults (the L0 stub
    # state had only ``schema_version`` and ``enabled``).
    _FILL_DEFAULTS: ClassVar[bool] = True
