"""Persisted state of the public granaries (see :mod:`chronicler.grain_reserves`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. A granary is identified by its region: ``GrainReserveState.granaries[i]``
is the granary of ``world.regions[i]``; its owner is a civilization index in
``world.civilizations`` (-1 none).

Tuple orders below are declaration orders: append new values at the end,
never reorder (stored values index into them).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr

#: ``ReserveFlow.kind`` names: what moved grain into or out of a granary
#: this turn. ``bought`` comes from a market (``source`` region, its
#: ``seller`` civ: the owner itself or a foreign one); ``released`` is eaten
#: by the region's people; ``spoiled`` is storage loss; ``seized`` is the
#: share a conquest or an occupying army took; ``abandoned`` is grain left to
#: the region's market when its granary has no owner; ``captured`` records a
#: new owner taking the granary (no grain moves).
FLOW_KINDS: tuple[str, ...] = ("bought", "released", "spoiled", "seized", "abandoned", "captured")
BOUGHT, RELEASED, SPOILED, SEIZED, ABANDONED, CAPTURED = range(len(FLOW_KINDS))

#: Cumulative counters kept on ``GrainReserveState.counters`` (insertion order).
COUNTER_KEYS: tuple[str, ...] = (
    "bought_own", "bought_realm", "bought_foreign", "sent", "transit_loss", "paid_own",
    "paid_foreign", "released", "released_severe", "spoiled", "seized", "abandoned",
    "captured", "openings", "exhausted",
)


class Granary(BaseModel):
    """The public granary of one region (index-aligned with ``world.regions``)."""

    owner: int = -1                  # civ index of the ruler who keeps it (-1 none)
    grain: float = 0.0               # grain held (goods units)
    target: float = 0.0              # stock target at the last tick (grain)
    harvest_mean: float = 0.0        # EMA of the region's own food harvest / food demand
    harvest_sq: float = 0.0          # EMA of its square
    observed: int = 0                # turns observed (the EMA's age)
    releasing: bool = False          # it released grain last turn (an opening is under way)
    announced: bool = False          # the opening under way has been recorded as an event
    emptied: bool = False            # it ran out during the opening under way


class ReserveFlow(BaseModel):
    """One movement of granary grain this turn (``GrainReserveState.flows``)."""

    kind: int
    region: int                      # the granary's region index
    amount: float                    # grain into (bought: received) or out of the granary
    source: int = -1                 # bought: the market region it came from
    seller: int = -1                 # bought: civ index of the seller's ruler
    buyer: int = -1                  # bought / captured: the granary owner's civ index
    sent: float = 0.0                # bought: grain that left the source market
    cost: int = 0                    # bought: treasury paid
    before: float = 0.0              # released: food sufficiency before the release
    after: float = 0.0               # released: food sufficiency after it


class GrainReserveState(BaseModel):
    """World-level switch and bookkeeping (``WorldState.grain_reserves``).

    ``flows`` lists this turn's movements (replaced each turn when the Phase 2
    tick runs; the Phase 10 purchases are appended), read by the snapshot,
    the resource ledger and the narration."""

    granaries: list[Granary] = Field(default_factory=list)
    flows: list[ReserveFlow] = Field(default_factory=list)
    flows_turn: int | None = None
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0.0 for k in COUNTER_KEYS})
    # The turn's resource ledger (``grain_reserves.ReserveLedger``) from the
    # Phase 2 tick to the end of the Phase 10 tick; None between turns.
    _ledger: object | None = PrivateAttr(default=None)


def grain_reserves_on(world) -> bool:
    """True only for a real granary state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "grain_reserves", None), GrainReserveState)
