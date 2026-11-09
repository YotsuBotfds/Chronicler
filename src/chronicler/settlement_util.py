"""Helpers shared by the settlement layers: cities and agent movements.

Each owner module keeps its own private names as aliases (``cities._q``,
``agent_movements._rng`` ...), so callers and tests are unchanged. Counter
bumps go through the owner state's ``bump`` (``SwitchStateMixin``).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Iterable

from chronicler.utils import stable_hash_int

if TYPE_CHECKING:
    from chronicler.models import Event

#: Stored floats are rounded to this many decimals.
QUANTUM_DIGITS = 4


def q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def rng(owner: str, world, namespace: str, *parts) -> random.Random:
    """A draw stream keyed by the owner module, the namespace, seed, turn and parts."""
    return random.Random(stable_hash_int(owner, namespace, world.seed, world.turn, *parts))


def emit(t, event_type: str, actors: Iterable[str], description: str, *,
         importance: int = 5, region: str | None = None,
         causes: Iterable[str | None] = ()) -> "Event":
    """Append an event to the tick ``t`` (``t.world``, ``t.events``)."""
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type,
               actors=[a for a in actors if a], description=description,
               importance=importance, region=region)
    provenance.cite(ev, *causes)
    # Same-tick chains (revolt -> free city) resolve in order.
    provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def max_civs() -> int:
    from chronicler.ffi_constants import MAX_CIV_RECORDS
    return MAX_CIV_RECORDS
