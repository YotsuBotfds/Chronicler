"""StatAccumulator — M27 core routing logic for stat mutations.

All phase functions route stat mutations through the accumulator instead of
mutating Civilization fields directly. In aggregate mode, apply() replays
mutations bit-identically. In hybrid mode, mutations route by category:

Routing categories (Batch A contract):
  keep         — Apply directly in ALL modes. Used for treasury, prestige,
                 asabiya, and any stat that must take effect regardless of
                 whether agents are running.  Examples: tax income, prestige
                 decay, stability recovery.
  guard        — INTENTIONALLY SKIPPED in hybrid mode.  These mutations
                 represent stats that agents produce emergently (population,
                 military, economy via occupation counts).  In aggregate mode
                 (--agents=off), apply() replays them.  17 call sites verified:
                 population growth/loss, military maintenance, mercenary hire,
                 secession splits, twilight pop drain, congress redistribution.
  guard-action — Action engine outcomes routed to DemandSignals for the Rust
                 agent tick.  Converted via to_demand_signals().
  guard-shock  — Phase-generated shocks (leader events, vassalage, proxy wars,
                 cultural milestones) routed to ShockSignals for the Rust tick.
                 Converted via to_shock_signals().
  signal       — External shocks (disasters, stability drains) routed to
                 ShockSignals.  Converted via to_shock_signals().

Flush semantics:
  apply()      — Aggregate mode: apply ALL categories in insertion order.
  apply_keep() — Hybrid/shadow mode: apply only "keep" category, skip rest.
                 Can be called multiple times (idempotent per change via
                 _applied flag).
  to_shock_signals()  — Extract "signal" + "guard-shock" as normalized shocks.
  to_demand_signals() — Extract "guard-action" as demand signals.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from chronicler.models import StatChange, CivShock, DemandSignal
from chronicler.utils import STAT_FLOOR

if TYPE_CHECKING:
    from chronicler.models import Civilization, WorldState

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
SHOCK_NORMALIZATION_FLOORS = {
    "stability": 10.0,
    "economy": 5.0,
}


def _shock_denominator(stat: float, stat_name: str | None = None) -> float:
    """Return the denominator used to normalize civ shocks."""
    return max(float(stat), SHOCK_NORMALIZATION_FLOORS.get(stat_name, 1.0))


def normalize_shock(delta: float, stat: float, stat_name: str | None = None) -> float:
    """Normalize a punitive stat delta to a negative shock in [-1.0, 0.0].

    `delta` is the magnitude of a loss. Use direct `CivShock` fields for
    positive boosts instead of this helper.
    """
    return max(-1.0, min(1.0, -abs(delta) / _shock_denominator(stat, stat_name)))


class StatAccumulator:
    """Captures stat mutations and routes them by category."""

    __slots__ = ("_changes", "_keep_applied_up_to")

    def __init__(self) -> None:
        self._changes: list[StatChange] = []
        self._keep_applied_up_to: int = 0  # watermark: keep changes applied up to this index

    def add(self, civ_idx: int, civ: Civilization, stat: str, delta: float, category: str) -> None:
        """Record a stat mutation. civ_idx is the index into world.civilizations."""
        self._changes.append(StatChange(
            civ_idx, stat, delta, category, getattr(civ, stat, 0),
        ))

    def checkpoint(self) -> int:
        """Return the current change-list length for slice-based post-processing."""
        return len(self._changes)

    def halve_positive_deltas(self, civ_idx: int, stats: tuple[str, ...], start_index: int) -> None:
        """Halve net positive deltas for a civ/stat subset in a tail slice.

        Used by succession-crisis action halving in accumulator mode. This mirrors
        aggregate behavior (halve net gain, keep losses unchanged).
        """
        if start_index >= len(self._changes):
            return

        # Net deltas by stat for changes emitted after start_index.
        net: dict[str, float] = {s: 0.0 for s in stats}
        for change in self._changes[start_index:]:
            if change.civ_id == civ_idx and change.stat in net:
                net[change.stat] += change.delta

        # For each stat with net positive gain, reduce positive deltas until
        # net gain equals floor(net_gain / 2), matching pre-existing integer behavior.
        for stat, total in net.items():
            if total <= 0:
                continue
            target = total // 2
            remaining_reduction = total - target

            for idx in range(len(self._changes) - 1, start_index - 1, -1):
                change = self._changes[idx]
                if (
                    change.civ_id != civ_idx
                    or change.stat != stat
                    or change.delta <= 0
                    or remaining_reduction <= 0
                ):
                    continue
                reduction = min(change.delta, remaining_reduction)
                change.delta -= reduction
                remaining_reduction -= reduction
                if remaining_reduction <= 0:
                    break

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
        """Agent mode: apply only keep-category changes.

        Safe to call multiple times — uses a watermark to skip already-applied
        changes.  This supports the two-flush pattern: once before the agent
        tick (Phases 1-9 keep mutations) and once after Phase 10 (Phase 10
        keep mutations like stability drains and faction effects).
        """
        start = self._keep_applied_up_to
        for i in range(start, len(self._changes)):
            c = self._changes[i]
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
        self._keep_applied_up_to = len(self._changes)

    def to_shock_signals(self, since: int = 0) -> list[CivShock]:
        """Convert signal + guard-shock changes to normalized shocks.

        Args:
            since: Only process changes from this index onward.  Default 0
                   processes all changes (backward compatible).
        """
        shocks: dict[int, CivShock] = {}
        for c in self._changes[since:]:
            if c.category not in ("signal", "guard-shock"):
                continue
            if c.stat not in STAT_TO_SHOCK_FIELD:
                continue
            shock = shocks.setdefault(c.civ_id, CivShock(c.civ_id))
            field = STAT_TO_SHOCK_FIELD[c.stat]
            current_shock = getattr(shock, field)
            normalized = c.delta / _shock_denominator(c.stat_at_time, c.stat)
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
