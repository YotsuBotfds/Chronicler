"""StatAccumulator — M27 core routing logic for stat mutations.

All phase functions route stat mutations through the accumulator instead of
mutating Civilization fields directly. In aggregate mode, apply() replays
mutations bit-identically. In hybrid mode, mutations route by category:
keep → apply, guard → skip, guard-action → demand signal,
signal/guard-shock → shock signal.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from chronicler.models import StatChange, CivShock, DemandSignal

if TYPE_CHECKING:
    from chronicler.models import Civilization, WorldState

STAT_FLOOR: dict[str, int] = {
    "stability": 5,
    "economy": 5,
    "military": 5,
    "culture": 5,
    "population": 0,
}

UNBOUNDED_STATS = {"treasury", "asabiya", "prestige"}

STAT_TO_OCCUPATION = {
    "military": 1,   # Soldier
    "economy": 2,    # Merchant
    "culture": 3,    # Scholar
}

STAT_TO_SHOCK_FIELD = {
    "stability": "stability_shock",
    "economy": "economy_shock",
    "military": "military_shock",
    "culture": "culture_shock",
}

DEMAND_SCALE_FACTOR = 1.0


def normalize_shock(delta: float, stat: float) -> float:
    """Normalize a raw stat delta to a shock value in [-1.0, +1.0].
    delta is a positive number representing the magnitude subtracted.
    """
    return max(-1.0, min(1.0, -abs(delta) / max(stat, 1)))


class StatAccumulator:
    """Captures stat mutations and routes them by category."""

    __slots__ = ("_changes",)

    def __init__(self) -> None:
        self._changes: list[StatChange] = []

    def add(self, civ_idx: int, civ: Civilization, stat: str, delta: float, category: str) -> None:
        """Record a stat mutation. civ_idx is the index into world.civilizations."""
        self._changes.append(StatChange(
            civ_idx, stat, delta, category, getattr(civ, stat, 0),
        ))

    def apply(self, world: WorldState) -> None:
        """Aggregate mode: apply all changes in insertion order. Bit-identical."""
        for c in self._changes:
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            new_val = current + c.delta
            if c.stat in UNBOUNDED_STATS:
                new_val = max(new_val, 0)
            else:
                floor = STAT_FLOOR.get(c.stat, 0)
                new_val = max(floor, min(100, new_val))
            setattr(civ, c.stat, type(current)(new_val))

    def apply_keep(self, world: WorldState) -> None:
        """Agent mode: apply only keep-category changes."""
        for c in self._changes:
            if c.category != "keep":
                continue
            civ = world.civilizations[c.civ_id]
            current = getattr(civ, c.stat)
            new_val = current + c.delta
            if c.stat in UNBOUNDED_STATS:
                new_val = max(new_val, 0)
            else:
                floor = STAT_FLOOR.get(c.stat, 0)
                new_val = max(floor, min(100, new_val))
            setattr(civ, c.stat, type(current)(new_val))

    def to_shock_signals(self) -> list[CivShock]:
        """Convert signal + guard-shock changes to normalized shocks."""
        shocks: dict[int, CivShock] = {}
        for c in self._changes:
            if c.category not in ("signal", "guard-shock"):
                continue
            if c.stat not in STAT_TO_SHOCK_FIELD:
                continue
            shock = shocks.setdefault(c.civ_id, CivShock(c.civ_id))
            field = STAT_TO_SHOCK_FIELD[c.stat]
            current_shock = getattr(shock, field)
            normalized = c.delta / max(c.stat_at_time, 1)
            new_shock = max(-1.0, min(1.0, current_shock + normalized))
            setattr(shock, field, new_shock)
        return list(shocks.values())

    def to_demand_signals(self, civ_capacities: dict[int, int]) -> list[DemandSignal]:
        """Convert guard-action changes to demand signals."""
        signals = []
        for c in self._changes:
            if c.category != "guard-action" or c.stat not in STAT_TO_OCCUPATION:
                continue
            occupation = STAT_TO_OCCUPATION[c.stat]
            capacity = max(civ_capacities.get(c.civ_id, 1), 1)
            magnitude = c.delta / capacity * DEMAND_SCALE_FACTOR
            signals.append(DemandSignal(c.civ_id, occupation, magnitude, turns_remaining=3))
        return signals
