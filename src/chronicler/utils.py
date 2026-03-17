"""Shared utilities used across chronicler modules."""

from __future__ import annotations


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer value to [low, high]."""
    return max(low, min(high, value))


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


def distribute_pop_loss(regions, total_loss: int) -> None:
    """Distribute population loss proportionally across regions."""
    total_pop = sum(r.population for r in regions)
    if total_pop <= 0:
        return
    remaining = total_loss
    for i, r in enumerate(regions):
        if i == len(regions) - 1:
            drain = remaining
        else:
            drain = round(total_loss * r.population / total_pop)
        actual = min(drain, r.population)
        r.population = max(r.population - actual, 0)
        remaining -= actual


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

    Raises StopIteration if not found.
    """
    return next(i for i, c in enumerate(world.civilizations) if c.name == name)


def get_civ(world, name: str):
    """Return the Civilization with the given name, or None."""
    for c in world.civilizations:
        if c.name == name:
            return c
    return None
