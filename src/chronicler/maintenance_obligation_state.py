"""Persisted state of the PL3 maintenance obligation (``--maintenance-obligation``, default off).

Owned by :mod:`chronicler.maintenance_obligation`. Pure data with no
simulation imports, so :mod:`chronicler.livelihoods_state` can import it.

Identities: ``civ`` is an index in ``world.civilizations``. The reservation
itself is recorded by L9 in its decision (``Decision.reserved["maintenance"]``);
this state keeps only the last decision's and the last execution's per-civ
rows and scalar counters. A world that never enabled the switch has no
sub-state, so feature-off output is unchanged.

Tuple orders below are declaration orders: append new values at the end.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Modes (first: the default when enabled). ``reserve_only`` is the
#: crowding-out control: the same reservation, repairs held to their
#: bargained envelope and the reservation returned unspent.
MODES: tuple[str, ...] = ("reserve", "reserve_only")

COUNTERS: frozenset[str] = frozenset({
    "decision_civ_turns", "planned_coins", "capped_coins", "reserved_coins", "cap_binding",
    "execution_civ_turns", "used_coins", "returned_coins", "envelope_spent_coins", "charged_coins",
    "settled_turns", "turns_discarded",
})


class ReservationDecision(BaseModel):
    """One civ's reservation, decided in Phase 10 of ``turn`` for the next
    turn: RS2's planned per-turn charges (whole units), the cap (a declared
    share of the budget the civ would have without the reservation) and the
    amount reserved (``min(planned, cap)``)."""

    turn: int
    civ: int
    planned: int
    budget_before: int
    cap: int
    reserved: int


class ReservationUse(BaseModel):
    """One civ's reservation in the turn it was for. Closure:
    ``reserved == used + returned`` and ``used + envelope_spent == charged``
    (RS2's whole-unit charge to the civ); ``used == 0`` in ``reserve_only``.
    The charge is split pro rata to the reservation and the envelope
    (``maintenance_obligation.split_charge``)."""

    turn: int
    civ: int
    reserved: int
    envelope: int | None = None
    charged: int
    used: int
    returned: int
    envelope_spent: int
    #: The envelope's share of the delivered work, ``envelope / (reserved +
    #: envelope)`` (1.0 without a reservation in use; ``reserve_only``).
    envelope_share: float = 1.0


class MaintenanceObligationState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["reserve", "reserve_only"] = "reserve"
    decision_turn: int | None = None
    decisions: list[ReservationDecision] = Field(default_factory=list)
    #: The last completed turn's execution rows (None: no settled Phase 2).
    frame_turn: int | None = None
    uses: list[ReservationUse] | None = None
    last_settled_turn: int | None = None
    counters: dict[str, float] = Field(default_factory=dict)
    # Transient, within one turn; never serialized: the decision staged by
    # L9's capped obligation (read by the same decision's RS2 proposal) and
    # this turn's execution rows (Phase 2 -> Phase 10).
    _staged: object | None = PrivateAttr(default=None)
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and (private.get("_turn") is not None or private.get("_staged") is not None):
            state = {**state, "__pydantic_private__": {**private, "_turn": None, "_staged": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None, "_staged": None})
        else:
            private.setdefault("_turn", None)
            private.setdefault("_staged", None)
