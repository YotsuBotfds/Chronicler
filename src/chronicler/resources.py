"""Resource system — terrain probabilities, auto-generation, trade routes."""
from __future__ import annotations

import random

from chronicler.models import Disposition, Event, InfrastructureType, Region, Resource, WorldState
from chronicler.models import EMPTY_SLOT, ResourceType
from chronicler.utils import get_region_map, stable_hash_int

# --- M34: Resource type constants ---

RESOURCE_BASE: dict[int, float] = {rt: 1.0 for rt in ResourceType}

TERRAIN_PRIMARY: dict[str, int] = {
    "plains": ResourceType.GRAIN, "forest": ResourceType.TIMBER,
    "mountains": ResourceType.ORE, "coast": ResourceType.FISH,
    "desert": ResourceType.EXOTIC, "tundra": ResourceType.EXOTIC,
    "river": ResourceType.GRAIN, "hills": ResourceType.GRAIN,
}

TERRAIN_SECONDARY: dict[str, list[tuple[int, float]]] = {
    "plains": [(ResourceType.BOTANICALS, 0.30)],
    "forest": [(ResourceType.BOTANICALS, 0.50)],
    "mountains": [(ResourceType.PRECIOUS, 0.40)],
    "coast": [(ResourceType.SALT, 0.60)],
    "desert": [(ResourceType.SALT, 0.50)],
    "tundra": [(ResourceType.ORE, 0.15)],
    "river": [(ResourceType.FISH, 0.40)],
    "hills": [(ResourceType.ORE, 0.30)],
}

TERRAIN_TERTIARY: dict[str, list[tuple[int, float]]] = {
    "plains": [(ResourceType.PRECIOUS, 0.05)],
    "forest": [(ResourceType.ORE, 0.10)],
    "mountains": [(ResourceType.SALT, 0.10)],
    "coast": [(ResourceType.BOTANICALS, 0.15)],
    "desert": [(ResourceType.PRECIOUS, 0.20)],
    "tundra": [],
    "river": [(ResourceType.BOTANICALS, 0.20)],
    "hills": [(ResourceType.TIMBER, 0.20)],
}


def assign_resource_types(regions: list[Region], seed: int) -> None:
    """M34: Assign resource_types and resource_base_yields per region."""
    for region in regions:
        if region.resource_types[0] != EMPTY_SLOT:
            continue  # Already assigned
        rng = random.Random(stable_hash_int("resource_types", seed, region.name))

        # Slot 1: deterministic primary
        primary = TERRAIN_PRIMARY.get(region.terrain, ResourceType.GRAIN)
        region.resource_types[0] = primary
        variance = rng.uniform(-0.2, 0.2)
        region.resource_base_yields[0] = RESOURCE_BASE[primary] * (1.0 + variance)

        # Slot 2: probabilistic secondary
        for rtype, prob in TERRAIN_SECONDARY.get(region.terrain, []):
            if rng.random() < prob:
                region.resource_types[1] = rtype
                variance = rng.uniform(-0.2, 0.2)
                region.resource_base_yields[1] = RESOURCE_BASE[rtype] * (1.0 + variance)
                break

        # Slot 3: rare tertiary
        for rtype, prob in TERRAIN_TERTIARY.get(region.terrain, []):
            if rng.random() < prob:
                region.resource_types[2] = rtype
                variance = rng.uniform(-0.2, 0.2)
                region.resource_base_yields[2] = RESOURCE_BASE[rtype] * (1.0 + variance)
                break


# M34→legacy bridge: ResourceType ID → old Resource enum values
_RESOURCE_TYPE_TO_LEGACY: dict[int, list[Resource]] = {
    ResourceType.GRAIN: [Resource.GRAIN],
    ResourceType.TIMBER: [Resource.TIMBER],
    ResourceType.BOTANICALS: [],  # No direct legacy equivalent
    ResourceType.FISH: [],
    ResourceType.SALT: [],
    ResourceType.ORE: [Resource.IRON, Resource.STONE],
    ResourceType.PRECIOUS: [Resource.RARE_MINERALS],
    ResourceType.EXOTIC: [Resource.FUEL],
}


def populate_legacy_resources(regions: list[Region]) -> None:
    """Auto-populate deprecated specialized_resources from resource_types."""
    for region in regions:
        if region.specialized_resources:
            continue
        legacy: list[Resource] = []
        for rtype in region.resource_types:
            if rtype == EMPTY_SLOT:
                continue
            legacy.extend(_RESOURCE_TYPE_TO_LEGACY.get(rtype, []))
        region.specialized_resources = legacy


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


def _trade_disposition_score(rel) -> int:
    """Treat missing relationships as neutral for route eligibility."""
    if rel is None:
        return DISP_ORDER["neutral"]
    disposition = getattr(rel.disposition, "value", rel.disposition)
    return DISP_ORDER.get(disposition, DISP_ORDER["neutral"])


def assign_resources(regions: list[Region], seed: int) -> None:
    """Assign specialized_resources to regions that don't have them."""
    for region in regions:
        if region.specialized_resources:
            continue
        rng = random.Random(stable_hash_int("resources", seed, region.name))
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


def _compute_active_trade_routes(
    world: WorldState,
    *,
    emit_events: bool = False,
) -> list[tuple[str, str]]:
    """Cross-civ trade routes — direct adjacency, neutral+ disposition, no embargo.

    H-6: Pure query by default. Set emit_events=True at the dedicated point
    in the turn loop (Phase 2) to emit capability events. All other callers
    (intelligence, snapshots, action engine) get a side-effect-free read.
    """
    routes: set[tuple[str, str]] = set()
    region_map = get_region_map(world)
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = region_map.get(adj_name)
            if r2 is None or r2.controller is None or r1.controller == r2.controller:
                continue
            pair = tuple(sorted([r1.controller, r2.controller]))
            if pair in embargo_set:
                continue
            rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
            rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
            if _trade_disposition_score(rel_ab) >= 2 and _trade_disposition_score(rel_ba) >= 2:
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
            mid = region_map.get(mid_name)
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
                hop2 = region_map.get(hop2_name)
                if hop2 is None or hop2.controller is None or hop2.controller == r1.controller:
                    continue
                pair = tuple(sorted([r1.controller, hop2.controller]))
                if pair in embargo_set or pair in routes:
                    continue
                rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
                rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
                if _trade_disposition_score(rel_ab) >= 2 and _trade_disposition_score(rel_ba) >= 2:
                    routes.add(pair)
                    capability_fired.add((r1.controller, focus))

    # H-6: Only emit capability events when explicitly requested (Phase 2 call site)
    if emit_events:
        for civ_name, focus in sorted(capability_fired):
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
    return sorted(routes)


def set_active_trade_routes_snapshot(
    world: WorldState,
    routes: list[tuple[str, str]],
) -> None:
    """Seed the current turn's route cache for downstream read-only consumers."""
    route_list = sorted(routes)
    world._trade_route_cache_turn = world.turn
    world._active_trade_routes_cache = list(route_list)
    world._active_trade_route_pairs_cache = set(route_list)


def clear_active_trade_routes_snapshot(world: WorldState) -> None:
    """Clear the transient per-turn route cache."""
    if hasattr(world, "invalidate_trade_route_cache"):
        world.invalidate_trade_route_cache()
    else:
        world._trade_route_cache_turn = None
        world._active_trade_routes_cache = None
        world._active_trade_route_pairs_cache = None
        world._self_trade_civs_cache = None


def get_active_trade_route_pairs(world: WorldState) -> set[tuple[str, str]]:
    """Return active trade routes as a normalized pair set."""
    cached_turn = getattr(world, "_trade_route_cache_turn", None)
    cached_pairs = getattr(world, "_active_trade_route_pairs_cache", None)
    if cached_turn == world.turn and cached_pairs is not None:
        return set(cached_pairs)
    return set(get_active_trade_routes(world))


def get_active_trade_routes(world: WorldState, *, emit_events: bool = False) -> list[tuple[str, str]]:
    """Return the current turn's trade-route graph.

    In `run_turn()`, Phase 2 may seed the current turn's route cache so later
    read-only consumers do not keep rebuilding the same route graph. Route-
    affecting mutations are expected to invalidate that cache before the next
    read.
    """
    if not emit_events:
        cached_routes = getattr(world, "_active_trade_routes_cache", None)
        cached_turn = getattr(world, "_trade_route_cache_turn", None)
        if cached_routes is not None and cached_turn == world.turn:
            return list(cached_routes)
    routes = _compute_active_trade_routes(world, emit_events=emit_events)
    set_active_trade_routes_snapshot(world, routes)
    return routes


def get_self_trade_civs(world: WorldState) -> set[str]:
    """Civs that control both endpoints of an adjacency edge (internal routes)."""
    cached_turn = getattr(world, "_trade_route_cache_turn", None)
    cached_self = getattr(world, "_self_trade_civs_cache", None)
    if cached_self is not None and cached_turn == world.turn:
        return set(cached_self)

    self_routes: set[str] = set()
    region_map = get_region_map(world)
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = region_map.get(adj_name)
            if r2 and r2.controller == r1.controller:
                self_routes.add(r1.controller)
    world._trade_route_cache_turn = world.turn
    world._self_trade_civs_cache = set(self_routes)
    return self_routes


# --- M34: Season and Climate ---

def get_season_step(turn: int) -> int:
    return turn % 12


def get_season_id(turn: int) -> int:
    return (turn % 12) // 3


# SEASON_MOD[resource_type_id][season_id] — all [CALIBRATE]
SEASON_MOD: list[list[float]] = [
    # Spring Summer Autumn Winter
    [0.8,   1.2,   1.5,   0.3],   # GRAIN
    [0.6,   1.0,   1.2,   0.8],   # TIMBER
    [1.2,   0.8,   0.6,   0.2],   # BOTANICALS
    [1.0,   1.0,   0.8,   0.6],   # FISH
    [0.8,   1.2,   1.0,   1.0],   # SALT
    [0.9,   1.0,   1.0,   0.9],   # ORE
    [0.9,   1.0,   1.0,   1.0],   # PRECIOUS
    [1.0,   0.8,   1.2,   0.6],   # EXOTIC
]

# CLIMATE_CLASS_MOD[class_index][climate_phase_index]
# Classes: 0=Crop, 1=Forestry, 2=Marine, 3=Mineral, 4=Evaporite
# Phases: 0=TEMPERATE, 1=WARMING, 2=DROUGHT, 3=COOLING
CLIMATE_CLASS_MOD: list[list[float]] = [
    [1.0, 0.9, 0.5, 0.7],  # Crop
    [1.0, 0.9, 0.7, 0.8],  # Forestry
    [1.0, 1.0, 0.8, 0.9],  # Marine
    [1.0, 1.0, 1.0, 1.0],  # Mineral
    [1.0, 1.1, 1.2, 0.9],  # Evaporite
]

_CLIMATE_PHASE_INDEX = {"temperate": 0, "warming": 1, "drought": 2, "cooling": 3}


def resource_class_index(rtype: int) -> int:
    """Map ResourceType to mechanical class index for CLIMATE_CLASS_MOD."""
    if rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS, ResourceType.EXOTIC):
        return 0  # Crop
    elif rtype == ResourceType.TIMBER:
        return 1  # Forestry
    elif rtype == ResourceType.FISH:
        return 2  # Marine
    elif rtype in (ResourceType.ORE, ResourceType.PRECIOUS):
        return 3  # Mineral
    elif rtype == ResourceType.SALT:
        return 4  # Evaporite
    return 0  # Fallback
