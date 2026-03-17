"""Fog-of-war, exploration, first contact, and ruins.

Visibility layer — does not change mechanics of discovered regions.
known_regions as list[str] | None: None = omniscient (fog disabled).
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, Region, WorldState

from chronicler.models import Event, Relationship
from chronicler.utils import civ_index


def initialize_fog(world: WorldState) -> None:
    """Called at world gen. Seeds each civ's known_regions if fog is active."""
    if not world.fog_of_war:
        return

    region_map = {r.name: r for r in world.regions}

    for civ in world.civilizations:
        known: set[str] = set()
        for rname in civ.regions:
            known.add(rname)
            region = region_map.get(rname)
            if region:
                for adj in region.adjacencies:
                    known.add(adj)
        civ.known_regions = sorted(known)


def is_explore_eligible(world: WorldState, civ: Civilization) -> bool:
    """EXPLORE is eligible when: fog active, treasury >= 5, unknown adjacent regions exist."""
    if not world.fog_of_war or civ.known_regions is None:
        return False
    if civ.treasury < 5:
        return False

    known_set = set(civ.known_regions)
    region_map = {r.name: r for r in world.regions}

    for rname in civ.known_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj in region.adjacencies:
            if adj not in known_set:
                return True
    return False


def _get_unknown_adjacent(world: WorldState, civ: Civilization) -> list[str]:
    """Return unknown regions adjacent to known regions."""
    if civ.known_regions is None:
        return []
    known_set = set(civ.known_regions)
    region_map = {r.name: r for r in world.regions}
    candidates: list[str] = []

    for rname in civ.known_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj in region.adjacencies:
            if adj not in known_set and adj not in candidates:
                candidates.append(adj)
    return candidates


def handle_explore(world: WorldState, civ: Civilization, acc=None) -> Event:
    """EXPLORE action handler. Reveals 1 unknown adjacent region + its adjacencies."""
    candidates = _get_unknown_adjacent(world, civ)
    region_map = {r.name: r for r in world.regions}

    if not candidates:
        return Event(
            turn=world.turn, event_type="explore_failed",
            actors=[civ.name],
            description=f"{civ.name} found nothing new to explore",
            importance=2,
        )

    idx_hash = int(hashlib.sha256(
        f"{world.seed}:{world.turn}:{civ.name}:explore".encode()
    ).hexdigest(), 16)
    target_name = candidates[idx_hash % len(candidates)]

    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", -5, "keep")
    else:
        civ.treasury -= 5

    known_set = set(civ.known_regions) if civ.known_regions else set()
    known_set.add(target_name)
    target = region_map.get(target_name)
    if target:
        for adj in target.adjacencies:
            known_set.add(adj)
    civ.known_regions = sorted(known_set)

    first_contact_events = []
    if target and target.controller:
        other_civ = target.controller
        if other_civ != civ.name:
            rels = world.relationships.get(civ.name, {})
            if other_civ not in rels:
                fc_event = handle_first_contact(world, civ.name, other_civ, target_name)
                if fc_event:
                    first_contact_events.append(fc_event)

    ruin_event = None
    if target and target.depopulated_since is not None:
        if (world.turn - target.depopulated_since) >= 20 and target.ruin_quality > 0:
            ruin_event = _discover_ruins(world, civ, target, acc=acc)

    event = Event(
        turn=world.turn, event_type="exploration",
        actors=[civ.name],
        description=f"{civ.name} explores {target_name}",
        importance=5,
    )

    for fc in first_contact_events:
        world.events_timeline.append(fc)
    if ruin_event:
        world.events_timeline.append(ruin_event)

    return event


def handle_first_contact(
    world: WorldState, discoverer: str, discovered: str, contact_region: str,
) -> Event | None:
    """Create relationship, share regions within 2 hops of contact point."""
    if discoverer not in world.relationships:
        world.relationships[discoverer] = {}
    if discovered not in world.relationships:
        world.relationships[discovered] = {}

    world.relationships[discoverer][discovered] = Relationship()
    world.relationships[discovered][discoverer] = Relationship()

    region_map = {r.name: r for r in world.regions}
    contact = region_map.get(contact_region)
    if contact:
        nearby: set[str] = {contact_region}
        frontier = [contact_region]
        for _ in range(2):
            next_frontier = []
            for rn in frontier:
                rr = region_map.get(rn)
                if rr:
                    for adj in rr.adjacencies:
                        if adj not in nearby:
                            nearby.add(adj)
                            next_frontier.append(adj)
            frontier = next_frontier

        for cname in (discoverer, discovered):
            c = next((c for c in world.civilizations if c.name == cname), None)
            if c and c.known_regions is not None:
                known_set = set(c.known_regions)
                known_set.update(nearby)
                c.known_regions = sorted(known_set)

    return Event(
        turn=world.turn, event_type="first_contact",
        actors=[discoverer, discovered],
        description=f"First contact between {discoverer} and {discovered}",
        importance=8,
    )


def mark_depopulated(region: Region, turn: int) -> None:
    """Called when region.controller becomes None."""
    region.depopulated_since = turn
    region.ruin_quality = len([i for i in region.infrastructure if i.active])
    for infra in region.infrastructure:
        infra.active = False


def _discover_ruins(
    world: WorldState, civ: Civilization, region: Region, acc=None,
) -> Event | None:
    """Culture boost with diminishing returns. Resets ruin state."""
    if region.ruin_quality <= 0:
        return None

    boost = int(region.ruin_quality * 5 * (1.0 - civ.culture / 100))
    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "culture", boost, "guard-shock")
    else:
        civ.culture = min(civ.culture + boost, 100)

    importance = 6 + min(region.ruin_quality, 4)
    event = Event(
        turn=world.turn, event_type="ruin_discovery",
        actors=[civ.name],
        description=f"{civ.name} discovers ancient ruins in {region.name} (+{boost} culture)",
        importance=importance,
    )

    region.depopulated_since = None
    region.ruin_quality = 0
    return event


def reveal_migration_source(civ: Civilization, source_region: str) -> None:
    """Called when migration arrives from an unknown region."""
    if civ.known_regions is None:
        return
    if source_region not in civ.known_regions:
        civ.known_regions.append(source_region)
        civ.known_regions.sort()


def filter_targets_by_fog(
    world: WorldState, civ: Civilization, target_regions: list[str],
) -> list[str]:
    """Remove regions the civ doesn't know about. No-op if fog disabled."""
    if not world.fog_of_war or civ.known_regions is None:
        return target_regions
    known_set = set(civ.known_regions)
    return [r for r in target_regions if r in known_set]


def tick_trade_knowledge_sharing(world: WorldState) -> list[Event]:
    """Called from apply_automatic_effects (phase 2)."""
    from chronicler.resources import get_active_trade_routes

    events: list[Event] = []
    region_map = {r.name: r for r in world.regions}

    for route in get_active_trade_routes(world):
        civ_a_name = route[0]
        civ_b_name = route[1]

        rel_a = world.relationships.get(civ_a_name, {}).get(civ_b_name)
        rel_b = world.relationships.get(civ_b_name, {}).get(civ_a_name)
        if rel_a:
            rel_a.trade_contact_turns += 1
        if rel_b:
            rel_b.trade_contact_turns += 1

        contact_turns = rel_a.trade_contact_turns if rel_a else 0
        max_hops = min(2 + contact_turns // 3, 5)

        civ_a = next((c for c in world.civilizations if c.name == civ_a_name), None)
        civ_b = next((c for c in world.civilizations if c.name == civ_b_name), None)
        if not civ_a or not civ_b:
            continue
        if civ_a.known_regions is None or civ_b.known_regions is None:
            continue

        # BFS from both civ regions that are endpoints of the trade route
        # Trade routes are tuples (civ_a_name, civ_b_name), find shared border regions
        a_regions = set(civ_a.regions)
        b_regions = set(civ_b.regions)
        endpoints: set[str] = set()
        for rname in a_regions:
            r = region_map.get(rname)
            if r:
                for adj in r.adjacencies:
                    if adj in b_regions:
                        endpoints.add(rname)
                        endpoints.add(adj)
        if not endpoints:
            # Fallback: use first regions
            if civ_a.regions:
                endpoints.add(civ_a.regions[0])
            if civ_b.regions:
                endpoints.add(civ_b.regions[0])

        nearby: set[str] = set(endpoints)
        frontier = list(endpoints)
        for _ in range(max_hops):
            next_frontier = []
            for rn in frontier:
                rr = region_map.get(rn)
                if rr:
                    for adj in rr.adjacencies:
                        if adj not in nearby:
                            nearby.add(adj)
                            next_frontier.append(adj)
            frontier = next_frontier

        a_known = set(civ_a.known_regions)
        b_known = set(civ_b.known_regions)
        new_for_b = (a_known & nearby) - b_known
        new_for_a = (b_known & nearby) - a_known

        if new_for_b:
            b_known.update(new_for_b)
            civ_b.known_regions = sorted(b_known)
        if new_for_a:
            a_known.update(new_for_a)
            civ_a.known_regions = sorted(a_known)

        for rname in new_for_b:
            r = region_map.get(rname)
            if r and r.controller and r.controller != civ_b_name:
                if r.controller not in world.relationships.get(civ_b_name, {}):
                    fc = handle_first_contact(world, civ_b_name, r.controller, rname)
                    if fc:
                        events.append(fc)
        for rname in new_for_a:
            r = region_map.get(rname)
            if r and r.controller and r.controller != civ_a_name:
                if r.controller not in world.relationships.get(civ_a_name, {}):
                    fc = handle_first_contact(world, civ_a_name, r.controller, rname)
                    if fc:
                        events.append(fc)

    return events
