# src/chronicler/politics.py
"""Political topology mechanics for the civilization chronicle generator."""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from chronicler.adjacency import graph_distance
from chronicler.models import (
    ActionType, Civilization, Disposition, Event, Leader, NamedEvent,
    Relationship, VassalRelation, WorldState,
)
from chronicler.utils import clamp, STAT_FLOOR

if TYPE_CHECKING:
    pass


def war_key(a: str, b: str) -> str:
    """Canonical key for a war between two civs (alphabetically sorted)."""
    return ":".join(sorted([a, b]))


def apply_governing_costs(world: WorldState) -> list[Event]:
    """Phase 2: Apply governing costs based on empire size and distance from capital."""
    events: list[Event] = []
    for civ in world.civilizations:
        if len(civ.regions) <= 2 or civ.capital_region is None:
            continue
        region_count = len(civ.regions)
        treasury_cost = (region_count - 2) * 2

        stability_cost = 0
        for region_name in civ.regions:
            if region_name == civ.capital_region:
                continue
            dist = graph_distance(world.regions, civ.capital_region, region_name)
            if dist < 0:
                dist = 1  # fallback if disconnected
            treasury_cost += dist * 2
            stability_cost += dist * 1

        civ.treasury -= treasury_cost
        civ.stability = clamp(civ.stability - stability_cost, STAT_FLOOR["stability"], 100)
    return events


def resolve_move_capital(civ: Civilization, world: WorldState) -> Event:
    """Resolve MOVE_CAPITAL action: relocate capital to most central region."""
    from chronicler.models import ActiveCondition
    civ.treasury -= 15

    def avg_distance(candidate: str) -> float:
        distances = []
        for rn in civ.regions:
            if rn != candidate:
                d = graph_distance(world.regions, candidate, rn)
                distances.append(d if d >= 0 else 1)
        return sum(distances) / max(len(distances), 1)

    target = min(civ.regions, key=avg_distance)
    old_capital = civ.capital_region
    civ.capital_region = target

    condition = ActiveCondition(
        condition_type="capital_relocation",
        affected_civs=[civ.name],
        duration=5,
        severity=10,
    )
    world.active_conditions.append(condition)

    return Event(
        turn=world.turn,
        event_type="move_capital",
        actors=[civ.name],
        description=f"{civ.name} relocated capital from {old_capital} to {target}",
        importance=6,
    )


_SECESSION_PREFIXES = [
    "Free", "Eastern", "Western", "Northern", "Southern",
    "New", "Upper", "Lower", "Greater",
]

_TRAIT_POOL = [
    "aggressive", "cautious", "opportunistic", "zealous", "ambitious",
    "calculating", "visionary", "bold", "shrewd", "stubborn",
]


def check_secession(world: WorldState) -> list[Event]:
    """Phase 10: Check for civil war / secession in unstable empires."""
    events: list[Event] = []
    new_civs: list[Civilization] = []

    for civ in list(world.civilizations):
        if civ.stability >= 20 or len(civ.regions) < 3:
            continue

        prob = (20 - civ.stability) / 100

        for pw in getattr(world, "proxy_wars", []):
            if pw.target_civ == civ.name:
                prob += 0.05
                break

        rng = random.Random(world.seed + world.turn + hash(civ.name))
        if rng.random() >= prob:
            continue

        # Secession fires
        region_map = {r.name: r for r in world.regions}

        def _dist_from_capital(rn: str, _civ=civ) -> int:
            d = graph_distance(world.regions, _civ.capital_region or _civ.regions[0], rn)
            return d if d >= 0 else 0

        sorted_regions = sorted(civ.regions, key=_dist_from_capital, reverse=True)

        breakaway_count = math.ceil(len(civ.regions) / 3)
        breakaway_count = max(1, min(breakaway_count, len(civ.regions) - 1))
        breakaway_regions = sorted_regions[:breakaway_count]
        remaining_regions = [r for r in civ.regions if r not in breakaway_regions]

        ratio = len(breakaway_regions) / len(civ.regions)
        split_pop = math.floor(civ.population * ratio)
        split_mil = math.floor(civ.military * ratio)
        split_eco = math.floor(civ.economy * ratio)
        split_tre = math.floor(civ.treasury * ratio)

        existing_names = {c.name for c in world.civilizations} | {c.name for c in new_civs}
        prefix = _SECESSION_PREFIXES[rng.randint(0, len(_SECESSION_PREFIXES) - 1)]
        base_name = breakaway_regions[0] if rng.random() < 0.5 else civ.name
        breakaway_name = f"{prefix} {base_name}"
        attempts = 0
        while breakaway_name in existing_names and attempts < len(_SECESSION_PREFIXES):
            prefix = _SECESSION_PREFIXES[attempts]
            breakaway_name = f"{prefix} {base_name}"
            attempts += 1
        if breakaway_name in existing_names:
            breakaway_name = f"{prefix} {base_name} {world.turn}"

        parent_trait = civ.leader.trait
        available_traits = [t for t in _TRAIT_POOL if t != parent_trait]
        new_trait = rng.choice(available_traits) if available_traits else parent_trait

        name_pool = civ.leader_name_pool or ["Leader"]
        used = set(world.used_leader_names)
        leader_name = None
        for n in name_pool:
            if n not in used:
                leader_name = n
                break
        if leader_name is None:
            leader_name = f"{breakaway_name} Leader"
        world.used_leader_names.append(leader_name)

        new_values = list(civ.values)
        if new_values:
            _VALUE_POOL = [
                "freedom", "order", "tradition", "progress", "honor",
                "wealth", "knowledge", "faith", "unity", "independence",
            ]
            swap_idx = rng.randint(0, len(new_values) - 1)
            available_values = [v for v in _VALUE_POOL if v not in new_values]
            if available_values:
                new_values[swap_idx] = rng.choice(available_values)

        def _min_dist_to_parent(rn: str) -> int:
            return min(
                (graph_distance(world.regions, rn, pr) for pr in remaining_regions),
                default=0,
            )
        breakaway_capital = min(breakaway_regions, key=_min_dist_to_parent)

        new_leader = Leader(
            name=leader_name,
            trait=new_trait,
            reign_start=world.turn,
            succession_type="secession",
        )

        breakaway_civ = Civilization(
            name=breakaway_name,
            population=max(split_pop, 1),
            military=max(split_mil, 0),
            economy=max(split_eco, 0),
            culture=civ.culture,
            stability=40,
            treasury=split_tre,
            tech_era=civ.tech_era,
            leader=new_leader,
            regions=breakaway_regions,
            capital_region=breakaway_capital,
            domains=list(civ.domains),
            values=new_values,
            asabiya=0.7,
            leader_name_pool=list(civ.leader_name_pool or []),
        )

        civ.population = max(civ.population - split_pop, 1)
        civ.military = max(civ.military - split_mil, 0)
        civ.economy = max(civ.economy - split_eco, 0)
        civ.treasury -= split_tre
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        civ.regions = remaining_regions

        for rn in breakaway_regions:
            if rn in region_map:
                region_map[rn].controller = breakaway_name

        if civ.name not in world.relationships:
            world.relationships[civ.name] = {}
        if breakaway_name not in world.relationships:
            world.relationships[breakaway_name] = {}
        world.relationships[civ.name][breakaway_name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        world.relationships[breakaway_name][civ.name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        for other_civ in world.civilizations:
            if other_civ.name not in (civ.name, breakaway_name):
                if other_civ.name not in world.relationships:
                    world.relationships[other_civ.name] = {}
                world.relationships[breakaway_name][other_civ.name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )
                world.relationships[other_civ.name][breakaway_name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )

        new_civs.append(breakaway_civ)

        events.append(Event(
            turn=world.turn,
            event_type="secession",
            actors=[civ.name, breakaway_name],
            description=f"The Secession of {breakaway_name} from {civ.name}",
            importance=9,
        ))

    world.civilizations.extend(new_civs)
    return events


def check_capital_loss(world: WorldState) -> list[Event]:
    """Phase 10: Check if any civ lost its capital and handle reassignment."""
    events: list[Event] = []
    for civ in world.civilizations:
        if civ.capital_region is None or civ.capital_region in civ.regions:
            continue
        if not civ.regions:
            continue

        # Capital lost
        civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)

        # Pick best remaining region (highest carrying_capacity * fertility)
        region_map = {r.name: r for r in world.regions}
        best_region = max(
            civ.regions,
            key=lambda rn: (
                region_map[rn].carrying_capacity * getattr(region_map[rn], "fertility", 0.8)
                if rn in region_map else 0
            ),
        )
        old_capital = civ.capital_region
        civ.capital_region = best_region

        events.append(Event(
            turn=world.turn,
            event_type="capital_loss",
            actors=[civ.name],
            description=f"{civ.name} lost capital {old_capital}, relocated to {best_region}",
            importance=8,
        ))
    return events


_ABSORPTION_BIAS_TRAITS = {"ambitious", "aggressive", "zealous"}
_VASSAL_BIAS_TRAITS = {"cautious", "shrewd", "visionary", "calculating"}


def choose_vassalize_or_absorb(
    winner: Civilization, loser: Civilization, world: WorldState,
) -> bool:
    """Return True to vassalize, False to absorb."""
    if winner.stability <= 40:
        return False
    rng = random.Random(world.seed + world.turn + hash(winner.name))
    trait = winner.leader.trait
    if trait in _ABSORPTION_BIAS_TRAITS:
        threshold = 0.3
    elif trait in _VASSAL_BIAS_TRAITS:
        threshold = 0.8
    else:
        threshold = 0.5
    return rng.random() < threshold


def resolve_vassalization(winner: Civilization, loser: Civilization, world: WorldState) -> list[Event]:
    """Apply full vassalization resolution steps."""
    events: list[Event] = []

    # Remove from active_wars and war_start_turns
    world.active_wars = [
        w for w in world.active_wars
        if not (set(w) == {winner.name, loser.name})
    ]
    key = war_key(winner.name, loser.name)
    world.war_start_turns.pop(key, None)

    # Create VassalRelation
    world.vassal_relations.append(VassalRelation(
        overlord=winner.name, vassal=loser.name, tribute_rate=0.15,
    ))

    # Set dispositions
    if winner.name not in world.relationships:
        world.relationships[winner.name] = {}
    if loser.name not in world.relationships:
        world.relationships[loser.name] = {}
    world.relationships[winner.name][loser.name] = Relationship(disposition=Disposition.SUSPICIOUS)
    world.relationships[loser.name][winner.name] = Relationship(disposition=Disposition.HOSTILE)

    events.append(Event(
        turn=world.turn,
        event_type="vassalization",
        actors=[winner.name, loser.name],
        description=f"The Subjugation of {loser.name}",
        importance=7,
    ))
    return events


def collect_tribute(world: WorldState) -> list[Event]:
    """Phase 2: Collect tribute from vassals to overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    for vr in world.vassal_relations:
        vassal = civ_map.get(vr.vassal)
        overlord = civ_map.get(vr.overlord)
        if vassal is None or overlord is None:
            continue
        tribute = math.floor(vassal.economy * vr.tribute_rate)
        vassal.treasury -= tribute
        overlord.treasury += tribute
        vr.turns_active += 1
    return events


def check_vassal_rebellion(world: WorldState) -> list[Event]:
    """Phase 10: Check if vassals rebel against weak overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove: list[VassalRelation] = []
    rebelled_overlords: set[str] = set()

    for vr in list(world.vassal_relations):
        overlord = civ_map.get(vr.overlord)
        vassal = civ_map.get(vr.vassal)
        if overlord is None or vassal is None:
            to_remove.append(vr)
            continue

        if overlord.stability >= 25 and overlord.treasury >= 10:
            continue

        rng = random.Random(world.seed + world.turn + hash(vr.vassal))
        prob = 0.05 if vr.overlord in rebelled_overlords else 0.15

        if vr.overlord in rebelled_overlords:
            rel = world.relationships.get(vr.vassal, {}).get(vr.overlord)
            if rel is None or rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue

        if rng.random() >= prob:
            continue

        to_remove.append(vr)
        rebelled_overlords.add(vr.overlord)
        vassal.stability = clamp(vassal.stability + 10, STAT_FLOOR["stability"], 100)
        vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)

        if vr.vassal in world.relationships and vr.overlord in world.relationships[vr.vassal]:
            world.relationships[vr.vassal][vr.overlord].disposition = Disposition.HOSTILE

        events.append(Event(
            turn=world.turn,
            event_type="vassal_rebellion",
            actors=[vr.vassal, vr.overlord],
            description=f"The {vr.vassal} Rebellion against {vr.overlord}",
            importance=8,
        ))

    for vr in to_remove:
        if vr in world.vassal_relations:
            world.vassal_relations.remove(vr)

    return events
