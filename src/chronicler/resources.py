"""Resource system — terrain probabilities, auto-generation, trade routes."""
from __future__ import annotations

import random

from chronicler.models import Disposition, Event, InfrastructureType, Region, Resource, WorldState


TERRAIN_RESOURCE_PROBS: dict[str, dict[Resource, float]] = {
    "plains":    {Resource.GRAIN: 0.8, Resource.TIMBER: 0.3, Resource.IRON: 0.1, Resource.FUEL: 0.05, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.02},
    "forest":    {Resource.GRAIN: 0.3, Resource.TIMBER: 0.8, Resource.IRON: 0.1, Resource.FUEL: 0.1, Resource.STONE: 0.05, Resource.RARE_MINERALS: 0.05},
    "mountains": {Resource.GRAIN: 0.05, Resource.TIMBER: 0.1, Resource.IRON: 0.6, Resource.FUEL: 0.1, Resource.STONE: 0.7, Resource.RARE_MINERALS: 0.2},
    "coast":     {Resource.GRAIN: 0.4, Resource.TIMBER: 0.2, Resource.IRON: 0.05, Resource.FUEL: 0.3, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.05},
    "desert":    {Resource.GRAIN: 0.05, Resource.TIMBER: 0.02, Resource.IRON: 0.2, Resource.FUEL: 0.4, Resource.STONE: 0.3, Resource.RARE_MINERALS: 0.15},
    "tundra":    {Resource.GRAIN: 0.02, Resource.TIMBER: 0.1, Resource.IRON: 0.3, Resource.FUEL: 0.3, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.2},
    "river":     {Resource.GRAIN: 0.7, Resource.TIMBER: 0.3, Resource.IRON: 0.05, Resource.FUEL: 0.05, Resource.STONE: 0.15, Resource.RARE_MINERALS: 0.02},
    "hills":     {Resource.GRAIN: 0.3, Resource.TIMBER: 0.4, Resource.IRON: 0.4, Resource.FUEL: 0.15, Resource.STONE: 0.5, Resource.RARE_MINERALS: 0.1},
}

DISP_ORDER = {"hostile": 0, "suspicious": 1, "neutral": 2, "friendly": 3, "allied": 4}


def assign_resources(regions: list[Region], seed: int) -> None:
    """Assign specialized_resources to regions that don't have them."""
    for region in regions:
        if region.specialized_resources:
            continue
        rng = random.Random(seed + hash(region.name))
        probs = TERRAIN_RESOURCE_PROBS.get(region.terrain, {})
        resources: list[Resource] = []
        for resource, prob in probs.items():
            if rng.random() < prob:
                resources.append(resource)
        if not resources:
            if probs:
                best = max(probs, key=lambda r: probs[r])
                resources.append(best)
            else:
                resources.append(Resource.GRAIN)
        region.specialized_resources = resources


def get_active_trade_routes(world: WorldState) -> list[tuple[str, str]]:
    """Cross-civ trade routes — direct adjacency, neutral+ disposition, no embargo."""
    routes: set[tuple[str, str]] = set()
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = next((r for r in world.regions if r.name == adj_name), None)
            if r2 is None or r2.controller is None or r1.controller == r2.controller:
                continue
            pair = tuple(sorted([r1.controller, r2.controller]))
            if pair in embargo_set:
                continue
            rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
            rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
            if rel_ab and rel_ba:
                if DISP_ORDER.get(rel_ab.disposition.value, 0) >= 2 and DISP_ORDER.get(rel_ba.disposition.value, 0) >= 2:
                    routes.add(pair)
    # M21: NAVIGATION extends trade to 2-hop coastal routes
    # M21: RAILWAYS extends trade to 2-hop road routes
    civ_focuses = {}
    for civ in world.civilizations:
        if civ.active_focus:
            civ_focuses[civ.name] = civ.active_focus

    capability_fired: set[tuple[str, str]] = set()  # (civ_name, focus) pairs that created routes
    for r1 in world.regions:
        if r1.controller is None or r1.controller not in civ_focuses:
            continue
        focus = civ_focuses[r1.controller]
        if focus not in ("navigation", "railways"):
            continue
        for mid_name in r1.adjacencies:
            mid = next((r for r in world.regions if r.name == mid_name), None)
            if mid is None:
                continue
            # NAVIGATION: intermediate must be coastal
            if focus == "navigation" and mid.terrain != "coast":
                continue
            # RAILWAYS: intermediate must have active roads
            if focus == "railways" and not any(
                i.type == InfrastructureType.ROADS and i.active for i in mid.infrastructure
            ):
                continue
            for hop2_name in mid.adjacencies:
                hop2 = next((r for r in world.regions if r.name == hop2_name), None)
                if hop2 is None or hop2.controller is None or hop2.controller == r1.controller:
                    continue
                pair = tuple(sorted([r1.controller, hop2.controller]))
                if pair in embargo_set or pair in routes:
                    continue
                rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
                rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
                if rel_ab and rel_ba:
                    if DISP_ORDER.get(rel_ab.disposition.value, 0) >= 2 and DISP_ORDER.get(rel_ba.disposition.value, 0) >= 2:
                        routes.add(pair)
                        capability_fired.add((r1.controller, focus))
    # Emit capability events for navigation/railways
    for civ_name, focus in capability_fired:
        world.events_timeline.append(Event(
            turn=world.turn, event_type=f"capability_{focus}",
            actors=[civ_name], description=f"{civ_name} {focus} extends trade routes",
            importance=1,
        ))

    # Federation members get trade routes regardless of adjacency
    for fed in world.federations:
        for i, m1 in enumerate(fed.members):
            for m2 in fed.members[i+1:]:
                pair = tuple(sorted([m1, m2]))
                if pair not in routes:
                    routes.add(pair)
    return list(routes)


def get_self_trade_civs(world: WorldState) -> set[str]:
    """Civs that control both endpoints of an adjacency edge (internal routes)."""
    self_routes: set[str] = set()
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = next((r for r in world.regions if r.name == adj_name), None)
            if r2 and r2.controller == r1.controller:
                self_routes.add(r1.controller)
    return self_routes
