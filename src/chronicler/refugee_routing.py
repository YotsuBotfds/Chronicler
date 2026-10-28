"""Opt-in capacity-aware routing for Python-owned population movements.

Only destinations are apportioned here: callers retain their eligibility,
source toll, flow accounting and event policies. No people, routes or random
draws are created. See ``docs/integration/refugee-routing.md``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState


DEFAULT_ENABLED_FOR_NEW_WORLDS = False


def capacity_aware_refugees_enabled(world) -> bool:
    return getattr(world, "capacity_aware_refugees", False) is True


def set_capacity_aware_refugees_enabled(world: "WorldState", enabled: bool) -> None:
    world.capacity_aware_refugees = bool(enabled)


def apportion_refugees(world: "WorldState", destinations: Iterable["Region"],
                       migrants: int) -> list[tuple["Region", int]]:
    """Allocate up to ``migrants`` across the destinations' current headroom.

    Equal integer shares are redistributed when a destination fills; residual
    people go to the lowest region index first. Duplicate destinations count
    once and input order has no effect. The result contains positive shares in
    region-index order, bounded by both the budget and each destination's
    effective capacity. Population is not changed here. Unplaced people remain
    the caller's explicit loss, rather than being silently restored at source.
    """
    from chronicler.ecology import effective_capacity

    if migrants <= 0:
        return []
    allowed = {id(region) for region in destinations}
    regions = [region for region in world.regions if id(region) in allowed]
    if len(regions) != len(allowed):
        raise ValueError("Refugee destinations must belong to world.regions")
    room = [max(0, int(effective_capacity(region) - region.population)) for region in regions]
    shares = [0] * len(regions)
    remaining = min(int(migrants), sum(room))
    active = [i for i, available in enumerate(room) if available > 0]
    while remaining > 0:
        equal, remainder = divmod(remaining, len(active))
        filled = [i for i in active if room[i] <= equal]
        if filled:
            # Remove tight capacities before assigning any remainders. Giving
            # an early destination a remainder in multiple rounds would bias
            # the still-open destinations (room 1/100/100, budget 5 -> 1/3/1).
            for i in filled:
                shares[i] = room[i]
                remaining -= room[i]
            active = [i for i in active if room[i] > equal]
        else:
            for position, i in enumerate(active):
                shares[i] = equal + (position < remainder)
            remaining = 0
    return [(region, share) for region, share in zip(regions, shares) if share > 0]
