"""Shared utilities used across chronicler modules."""

from __future__ import annotations

import hashlib
from enum import Enum


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer value to [low, high]."""
    return max(low, min(high, value))


def _stable_serialize(value: object) -> str:
    """Serialize nested values into a deterministic string representation."""
    if isinstance(value, Enum):
        return f"enum:{value.__class__.__name__}:{_stable_serialize(value.value)}"
    if value is None:
        return "none"
    if isinstance(value, (bool, int, float, str, bytes)):
        return repr(value)
    if isinstance(value, tuple):
        return "(" + ",".join(_stable_serialize(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ",".join(_stable_serialize(item) for item in value) + "]"
    if isinstance(value, (set, frozenset)):
        items = sorted(_stable_serialize(item) for item in value)
        return "{" + ",".join(items) + "}"
    if isinstance(value, dict):
        items = sorted(
            (_stable_serialize(key), _stable_serialize(val))
            for key, val in value.items()
        )
        return "{" + ",".join(f"{key}:{val}" for key, val in items) + "}"
    return repr(value)


def stable_hash_int(*parts: object) -> int:
    """Return a process-stable integer hash for deterministic seeding/tiebreaks."""
    payload = "|".join(_stable_serialize(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


STAT_FLOOR: dict[str, int] = {
    "population": 1,
    "military": 0,
    "economy": 0,
    "culture": 0,
    "stability": 0,
}


def sync_civ_population(civ, world) -> None:
    """Recompute civ.population as sum of controlled region populations."""
    civ.population = sum(
        r.population for r in world.regions if r.controller == civ.name
    )
    if civ.population < 1 and civ.regions:
        civ.population = 1


def sync_all_populations(world) -> None:
    """Recompute population cache for all civilizations."""
    civs = world.civilizations
    if not civs:
        return

    # Keep each owner's populations in world.regions order. Calling sum() on
    # those values preserves the single-civ helper's float/mixed-number behavior.
    populations_by_name = {civ.name: [] for civ in civs}
    for region in world.regions:
        populations = populations_by_name.get(region.controller)
        if populations is not None:
            populations.append(region.population)

    for civ in civs:
        civ.population = sum(populations_by_name[civ.name])
        if civ.population < 1 and civ.regions:
            civ.population = 1


def stage_region_catastrophe_deaths(region, amount: int) -> None:
    """Queue a one-turn catastrophe death count for bridge-backed agent modes."""
    if amount <= 0:
        return
    current = int(getattr(region, "_catastrophe_deaths_this_turn", 0) or 0)
    region._catastrophe_deaths_this_turn = current + int(amount)


# --- Python-owned population ---------------------------------------------------------
#
# Where Python owns population (``--agents off`` and shadow), a region's
# population changes only through these helpers (and the restorations that set
# a region's population with ``set_region_pop``). Each change is one flow:
# ``added`` (births and arrivals from outside the regions), ``removed``
# (deaths), ``emigrated`` (people leaving a region for others) and
# ``immigrated`` (those of them who settle). Migrants who find no room die on
# the way: they emigrated but never immigrated.

POPULATION_FLOWS = ("added", "removed", "emigrated", "immigrated")

#: Environment switch for the debug population ledger (``run_turn`` checks
#: the aggregate turn's population against it).
POPULATION_CHECK_ENV = "CHRONICLER_CHECK_POPULATION"


class PopulationLedger:
    """Debug accounting of one aggregate turn's population flows.

    ``check`` holds when the regions' total changed by exactly ``added -
    removed + immigrated - emigrated`` and migration created no one
    (``immigrated <= emigrated``)."""

    __slots__ = POPULATION_FLOWS

    def __init__(self) -> None:
        for flow in POPULATION_FLOWS:
            setattr(self, flow, 0)

    def record(self, flow: str, amount: int) -> None:
        if amount:
            setattr(self, flow, getattr(self, flow) + amount)

    def net(self) -> int:
        return self.added - self.removed + self.immigrated - self.emigrated

    def check(self, before: int, after: int, turn: object = None) -> None:
        if after - before != self.net() or self.immigrated > self.emigrated:
            flows = ", ".join(f"{f} {getattr(self, f)}" for f in POPULATION_FLOWS)
            raise AssertionError(
                f"population not conserved at turn {turn}: total {before} -> {after} "
                f"({after - before:+d}) against flows {flows} (net {self.net():+d})"
            )


_population_ledger: PopulationLedger | None = None


def start_population_ledger() -> PopulationLedger:
    """Record every population flow until :func:`stop_population_ledger`."""
    global _population_ledger
    _population_ledger = PopulationLedger()
    return _population_ledger


def stop_population_ledger() -> None:
    global _population_ledger
    _population_ledger = None


def _record_flow(flow: str, amount: int) -> None:
    if _population_ledger is not None:
        _population_ledger.record(flow, amount)


def distribute_pop_loss(regions, total_loss: int) -> list[int]:
    """Distribute population loss proportionally across regions and return per-region drains."""
    total_pop = sum(r.population for r in regions)
    if total_pop <= 0:
        return [0 for _ in regions]
    remaining = max(0, total_loss)
    actual_drains: list[int] = []
    for i, r in enumerate(regions):
        if i == len(regions) - 1:
            drain = remaining
        else:
            drain = round(total_loss * r.population / total_pop)
        actual = max(0, min(drain, r.population, remaining))
        r.population = max(r.population - actual, 0)
        remaining -= actual
        actual_drains.append(actual)
        _record_flow("removed", actual)
    return actual_drains


def drain_region_pop(region, amount: int, flow: str = "removed") -> int:
    """Remove up to *amount* population from a region. Returns actual drained.

    ``flow`` is ``removed`` (deaths) or ``emigrated`` (people who leave for
    other regions)."""
    actual = min(amount, region.population)
    region.population -= actual
    _record_flow(flow, actual)
    return actual


def add_region_pop(region, amount: int, cap=None, flow: str = "added") -> int:
    """Add up to *amount* people to a region, never beyond ``cap`` (default
    its effective capacity). Returns the number accepted.

    Correction (2026-10, population-entities): this set the population to
    ``min(population + amount, cap)``, so an arrival in a region already above
    its capacity removed residents (one person added to 100 on room for 48
    left 48). Only the increment is capped now: ``max(0, min(amount, cap -
    population))`` arrive and the residents stay. ``flow`` is ``added``
    (births, arrivals from outside) or ``immigrated`` (migrants from other
    regions); callers account for those not accepted.
    """
    if cap is None:
        from chronicler.ecology import effective_capacity
        cap = effective_capacity(region)
    accepted = max(0, min(amount, cap - region.population))
    region.population += accepted
    _record_flow(flow, accepted)
    return accepted


def set_region_pop(region, population: int) -> None:
    """Set a region's population outright (a restored realm's settlers),
    recording the difference as people added or removed."""
    delta = population - region.population
    region.population = population
    _record_flow("added" if delta > 0 else "removed", abs(delta))


def civ_index(world, name: str) -> int:
    """Return the index of the named civilization in world.civilizations.

    Raises ValueError if not found.
    """
    idx = getattr(world, "civ_index_map", {}).get(name)
    if idx is not None:
        return idx
    if hasattr(world, "invalidate_civ_map"):
        world.invalidate_civ_map()
        idx = getattr(world, "civ_index_map", {}).get(name)
        if idx is not None:
            return idx
    known = ", ".join(civ.name for civ in world.civilizations) or "<none>"
    raise ValueError(
        f"Civilization {name!r} not found in world.civilizations at turn "
        f"{getattr(world, 'turn', 'unknown')}; known civs: {known}"
    )


def get_civ(world, name: str):
    """Return the Civilization with the given name, or None."""
    return getattr(world, "civ_map", {}).get(name)


def get_region_map(world) -> dict[str, object]:
    """Return a region-name lookup, falling back for mock/test worlds.

    Real `WorldState` instances expose `world.region_map`; some focused tests use
    lightweight mocks that only provide `world.regions`.
    """
    region_map = getattr(world, "region_map", None)
    if isinstance(region_map, dict):
        return region_map
    return {region.name: region for region in getattr(world, "regions", [])}


def resolve_civ_faith_id(civ, belief_registry, civ_idx: int | None = None, default: int = 0xFF) -> int:
    """Resolve a civ-owned faith id without assuming registry order is civ order.

    Prefer the civilization's persisted majority-faith fields when they point at
    a live faith id, and only fall back to positional registry lookup for older
    worlds that do not carry explicit faith ownership.
    """
    valid_faith_ids = {
        int(getattr(belief, "faith_id"))
        for belief in (belief_registry or [])
        if hasattr(belief, "faith_id")
    }
    for attr_name in ("civ_majority_faith", "previous_majority_faith"):
        faith_id = getattr(civ, attr_name, default)
        if faith_id != default and faith_id in valid_faith_ids:
            return int(faith_id)

    if civ_idx is not None and 0 <= civ_idx < len(belief_registry or []):
        fallback = getattr(belief_registry[civ_idx], "faith_id", default)
        return int(fallback)

    return default
