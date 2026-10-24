"""Persisted diplomacy state (see :mod:`chronicler.diplomacy`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. Civilization identity is the index in ``world.civilizations`` and region
identity the index in ``world.regions``; nothing here is identified by name
except through those indices.

Tuple orders below are declaration orders: append new kinds at the end,
never reorder (stored rows index into them).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

#: Grievance stocks kept per directed civ pair (``DiplomaticMemory.grievance``
#: holds one value per kind, in this order).
GRIEVANCE_KINDS: tuple[str, ...] = (
    "war",         # battles lost, wars declared on us
    "occupation",  # our land occupied or taken
    "treaty",      # treaties broken against us, revolts against us
    "border",      # border incidents
    "faith",       # persecution of our faith or our people
    "embargo",     # embargoes imposed on us
)
WAR, OCCUPATION, TREATY, BORDER, FAITH, EMBARGO = range(len(GRIEVANCE_KINDS))

#: Treaty kinds (``Treaty.kind``).
TREATY_KINDS: tuple[str, ...] = ("peace", "non_aggression", "alliance", "trade_pact", "tribute")

#: Polity-ladder stages stored on ``VassalRelation.stage`` (annexation ends
#: the relation, so it is not a stage).
LADDER_STAGES: tuple[str, ...] = ("client", "vassal", "union")

#: ``Treaty.status`` values.
TREATY_STATUSES: tuple[str, ...] = ("active", "expired", "broken", "ended")


class DiplomaticMemory(BaseModel):
    """How one civilization regards another (directed).

    Lives on ``Relationship.memory`` of ``world.relationships[a][b]``: ``a``'s
    trust in ``b``, the goodwill ``a`` has accumulated toward ``b`` and ``a``'s
    grievances against ``b``. ``None`` there means no memory yet.
    """

    trust: float = 0.0
    goodwill: float = 0.0
    grievance: list[float] = Field(default_factory=lambda: [0.0] * len(GRIEVANCE_KINDS))

    def total_grievance(self) -> float:
        return sum(self.grievance)


class Treaty(BaseModel):
    """One treaty between two civilizations.

    ``parties`` are civ indices. For ``tribute`` the order is (payer,
    recipient); every other kind stores them ascending. ``terms`` holds the
    kind's terms (all values JSON scalars or lists).
    """

    treaty_id: int
    kind: str
    parties: list[int]
    name: str = ""
    start_turn: int
    expiry_turn: int | None = None
    status: str = "active"
    ended_turn: int | None = None
    broken_by: int | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    # Causal provenance: the signing event (and, once over, the closing one).
    event_id: str = ""
    end_event_id: str = ""


class DiplomacyState(BaseModel):
    """World-level diplomacy switch and bookkeeping (``WorldState.diplomacy``).

    ``None`` on the world means the feature is off. ``subjects`` and
    ``controllers`` mirror the vassal relations and region controllers at the
    end of the previous diplomacy tick, so the next tick can see what changed
    (revolts, lost land) whichever system changed it.
    """

    treaties: list[Treaty] = Field(default_factory=list)
    next_treaty_id: int = 1
    # (proposer civ, target civ, kind, until turn): a rejected offer is not
    # repeated before ``until``.
    cooldowns: list[tuple[int, int, str, int]] = Field(default_factory=list)
    # (overlord civ, vassal civ, stage) at the end of the previous tick.
    subjects: list[tuple[int, int, str]] = Field(default_factory=list)
    # Region index -> controller civ index (-1 = none) at the end of the previous tick.
    controllers: list[int] = Field(default_factory=list)
    # Cumulative counters (signed:<kind>, broken:<kind>, rejected:<kind>, ...).
    counts: dict[str, int] = Field(default_factory=dict)

    def active(self, kind: str | None = None) -> list[Treaty]:
        return [t for t in self.treaties
                if t.status == "active" and (kind is None or t.kind == kind)]


def diplomacy_on(world) -> bool:
    """True only for a real diplomacy state on ``world`` (mocks and None read as off)."""
    return isinstance(getattr(world, "diplomacy", None), DiplomacyState)
