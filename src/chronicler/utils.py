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
    for civ in world.civilizations:
        sync_civ_population(civ, world)


def stage_region_catastrophe_deaths(region, amount: int) -> None:
    """Queue a one-turn catastrophe death count for bridge-backed agent modes."""
    if amount <= 0:
        return
    current = int(getattr(region, "_catastrophe_deaths_this_turn", 0) or 0)
    region._catastrophe_deaths_this_turn = current + int(amount)


def distribute_pop_loss(regions, total_loss: int) -> list[int]:
    """Distribute population loss proportionally across regions and return per-region drains."""
    total_pop = sum(r.population for r in regions)
    if total_pop <= 0:
        return [0 for _ in regions]
    remaining = total_loss
    actual_drains: list[int] = []
    for i, r in enumerate(regions):
        if i == len(regions) - 1:
            drain = remaining
        else:
            drain = round(total_loss * r.population / total_pop)
        actual = min(drain, r.population)
        r.population = max(r.population - actual, 0)
        remaining -= actual
        actual_drains.append(actual)
    return actual_drains


def drain_region_pop(region, amount: int) -> int:
    """Remove up to *amount* population from a region. Returns actual drained."""
    actual = min(amount, region.population)
    region.population -= actual
    return actual


def add_region_pop(region, amount: int, cap=None) -> None:
    """Add population to a region, capped at effective_capacity."""
    if cap is None:
        from chronicler.ecology import effective_capacity
        cap = effective_capacity(region)
    region.population = min(region.population + amount, cap)


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
