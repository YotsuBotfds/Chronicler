"""Infrastructure lifecycle — build, tick, destroy.

Typed infrastructure persists through conquest, takes multiple turns to build,
and interacts with terrain. Scorched earth is the first REACTION_REGISTRY consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, Region, WorldState

from chronicler.models import Event, InfrastructureType as IType, Infrastructure, PendingBuild
from chronicler.tuning import (
    K_TEMPLE_BUILD_COST, K_TEMPLE_BUILD_TURNS,
    K_MAX_TEMPLES_PER_REGION, K_MAX_TEMPLES_PER_CIV,
    K_TEMPLE_CONVERSION_BOOST, K_TEMPLE_PRESTIGE_PER_TURN,
    K_CIV_PRESTIGE_PER_TEMPLE, K_SCORCHED_EARTH_TRAIT_BONUS,
    get_override,
)
from chronicler.utils import civ_index, get_region_map, stable_hash_int


@dataclass(frozen=True)
class BuildSpec:
    cost: int
    turns: int
    terrain_req: str | None
    terrain_exclude: str | None


TEMPLE_BUILD_COST = 10
TEMPLE_BUILD_TURNS = 3
MAX_TEMPLES_PER_REGION = 1
MAX_TEMPLES_PER_CIV = 3
TEMPLE_CONVERSION_BOOST = 0.50

BUILD_SPECS: dict[IType, BuildSpec] = {
    IType.ROADS:          BuildSpec(cost=10, turns=2, terrain_req=None, terrain_exclude=None),
    IType.FORTIFICATIONS: BuildSpec(cost=15, turns=3, terrain_req=None, terrain_exclude=None),
    IType.IRRIGATION:     BuildSpec(cost=12, turns=2, terrain_req=None, terrain_exclude="desert"),
    IType.PORTS:          BuildSpec(cost=15, turns=3, terrain_req="coast", terrain_exclude=None),
    IType.MINES:          BuildSpec(cost=10, turns=2, terrain_req=None, terrain_exclude=None),
    IType.TEMPLES:        BuildSpec(cost=TEMPLE_BUILD_COST, turns=TEMPLE_BUILD_TURNS, terrain_req=None, terrain_exclude=None),
}


def _region_has_temple(region) -> bool:
    return any(i.type == IType.TEMPLES and i.active for i in region.infrastructure)


def _count_civ_temples(world, civ_name: str) -> int:
    """Count active temples in regions controlled by this civ."""
    count = 0
    for r in world.regions:
        if getattr(r, 'controller', None) != civ_name:
            continue
        for i in r.infrastructure:
            if i.type == IType.TEMPLES and i.active:
                count += 1
    return count


def valid_build_types(region: Region) -> list[IType]:
    """Return infrastructure types that can be built in this region."""
    if region.pending_build is not None:
        return []

    existing = {i.type for i in region.infrastructure if i.active}
    result = []
    for itype, spec in BUILD_SPECS.items():
        if itype in existing:
            continue
        if spec.terrain_req and region.terrain != spec.terrain_req:
            continue
        if spec.terrain_exclude and region.terrain == spec.terrain_exclude:
            continue
        result.append(itype)
    return result


def tick_infrastructure(world: WorldState) -> list:
    """Called from apply_automatic_effects (phase 2)."""
    from chronicler.models import Event

    events = []
    for region in world.regions:
        if region.pending_build is not None:
            region.pending_build.turns_remaining -= 1
            # M21: FORTIFICATION reduces fort build time by 1 turn
            if (region.pending_build.type == IType.FORTIFICATIONS and region.controller):
                ctrl_civ = next((c for c in world.civilizations if c.name == region.controller), None)
                if ctrl_civ and ctrl_civ.active_focus == "fortification":
                    region.pending_build.turns_remaining = max(0, region.pending_build.turns_remaining - 1)
                    world.events_timeline.append(Event(
                        turn=world.turn, event_type="capability_fortification",
                        actors=[ctrl_civ.name], description=f"{ctrl_civ.name} fortification speeds construction",
                        importance=1,
                    ))
            if region.pending_build.turns_remaining <= 0:
                completed = Infrastructure(
                    type=region.pending_build.type,
                    builder_civ=region.pending_build.builder_civ,
                    built_turn=world.turn,
                    faith_id=region.pending_build.faith_id,
                )
                region.infrastructure.append(completed)
                events.append(Event(
                    turn=world.turn,
                    event_type="infrastructure_completed",
                    actors=[region.pending_build.builder_civ],
                    description=f"{region.pending_build.type.value} completed in {region.name}",
                    importance=4,
                ))
                # M52: Temple relic creation (only for temples, not other infrastructure)
                if completed.type == IType.TEMPLES:
                    from chronicler.models import ArtifactIntent, ArtifactType as _AT
                    world._artifact_intents.append(ArtifactIntent(
                        artifact_type=_AT.RELIC,
                        trigger="temple_construction",
                        creator_name=None,
                        creator_born_turn=None,
                        holder_name=None,
                        holder_born_turn=None,
                        civ_name=region.pending_build.builder_civ,
                        region_name=region.name,
                        anchored=True,
                        context=f"Sacred relic consecrated in the temple of {region.name}",
                    ))
                region.pending_build = None

    return events


def scorched_earth_check(
    world: WorldState, defender: Civilization, lost_region: Region, seed: int,
) -> list:
    """REACTION_REGISTRY['region_lost'] handler."""
    import hashlib
    from chronicler.models import Event

    scorched_bonus = get_override(world, K_SCORCHED_EARTH_TRAIT_BONUS, 0.2)
    trait_bonus = scorched_bonus if defender.leader.trait == "aggressive" else 0.0
    prob = min(1.0 - defender.stability / 100 + trait_bonus, 1.0)

    roll_input = f"{seed}:{lost_region.name}:{world.turn}:scorch"
    roll = int(hashlib.sha256(roll_input.encode()).hexdigest(), 16) % 10000 / 10000

    if roll < prob and any(i.active for i in lost_region.infrastructure):
        for infra in lost_region.infrastructure:
            infra.active = False
        return [Event(
            turn=world.turn,
            event_type="scorched_earth",
            actors=[defender.name],
            description=f"{defender.name} scorched {lost_region.name} during retreat",
            importance=6,
        )]
    return []


# Trait-weighted type preferences for BUILD action
TRAIT_BUILD_PRIORITY: dict[str, list[IType]] = {
    "aggressive":   [IType.FORTIFICATIONS, IType.MINES, IType.ROADS, IType.PORTS, IType.IRRIGATION, IType.TEMPLES],
    "bold":         [IType.FORTIFICATIONS, IType.ROADS, IType.MINES, IType.PORTS, IType.IRRIGATION, IType.TEMPLES],
    "cautious":     [IType.FORTIFICATIONS, IType.ROADS, IType.IRRIGATION, IType.PORTS, IType.MINES, IType.TEMPLES],
    "mercantile":   [IType.ROADS, IType.PORTS, IType.MINES, IType.IRRIGATION, IType.FORTIFICATIONS, IType.TEMPLES],
    "expansionist": [IType.IRRIGATION, IType.ROADS, IType.MINES, IType.PORTS, IType.FORTIFICATIONS, IType.TEMPLES],
    "diplomatic":   [IType.ROADS, IType.TEMPLES, IType.PORTS, IType.IRRIGATION, IType.MINES, IType.FORTIFICATIONS],
}
_DEFAULT_PRIORITY = [IType.ROADS, IType.FORTIFICATIONS, IType.IRRIGATION, IType.PORTS, IType.MINES, IType.TEMPLES]


def handle_build(civ: Civilization, world: WorldState, acc=None):
    """BUILD action handler. Registered via ACTION_REGISTRY[ActionType.BUILD].
    Replaces the old _resolve_build handler from M13b-1.
    """
    import hashlib
    from chronicler.models import Event

    seed = stable_hash_int("build_action", world.seed, world.turn, civ.name)

    region_map = get_region_map(world)
    candidates: list[tuple] = []
    for rname in civ.regions:
        region = region_map.get(rname)
        if region is None:
            continue
        vtypes = valid_build_types(region)
        if vtypes:
            candidates.append((region, vtypes))

    if not candidates:
        return None

    idx = int(hashlib.sha256(
        f"{seed}:{world.turn}:{civ.name}:build_region".encode()
    ).hexdigest(), 16) % len(candidates)
    target_region, valid_types = candidates[idx]

    trait = civ.leader.trait if civ.leader else "bold"
    priority = TRAIT_BUILD_PRIORITY.get(trait, _DEFAULT_PRIORITY)
    selected_type = None
    for ptype in priority:
        if ptype not in valid_types or BUILD_SPECS[ptype].cost > civ.treasury:
            continue
        if ptype == IType.TEMPLES:
            if _count_civ_temples(world, civ.name) >= int(get_override(world, K_MAX_TEMPLES_PER_CIV, 3)):
                continue
            existing_temple = next(
                (i for i in target_region.infrastructure if i.type == IType.TEMPLES and i.active),
                None,
            )
            if existing_temple:
                builder_faith = getattr(civ, 'civ_majority_faith', -1)
                if existing_temple.faith_id == builder_faith:
                    continue  # can't build same-faith duplicate
                # M38a: foreign temple — destroy and replace
                evt = destroy_temple_for_replacement(target_region, world)
                if evt:
                    world.events_timeline.append(evt)
        selected_type = ptype
        break
    if selected_type is None:
        affordable = [(t, BUILD_SPECS[t].cost) for t in valid_types
                      if BUILD_SPECS[t].cost <= civ.treasury]
        if not affordable:
            return None
        selected_type = min(affordable, key=lambda x: x[1])[0]

    faith_id = getattr(civ, 'civ_majority_faith', -1) if selected_type == IType.TEMPLES else -1

    spec = BUILD_SPECS[selected_type]
    if acc is not None:
        civ_idx = civ_index(world, civ.name)
        acc.add(civ_idx, civ, "treasury", -spec.cost, "keep")
    else:
        civ.treasury -= spec.cost
    target_region.pending_build = PendingBuild(
        type=selected_type,
        builder_civ=civ.name,
        started_turn=world.turn,
        turns_remaining=spec.turns,
        faith_id=faith_id,
    )

    return Event(
        turn=world.turn, event_type="build_started",
        actors=[civ.name],
        description=f"{civ.name} begins building {selected_type.value} in {target_region.name}",
        importance=3,
    )


TEMPLE_PRESTIGE_PER_TURN = 1
CIV_PRESTIGE_PER_TEMPLE = 1


def tick_temple_prestige(world, acc=None):
    """Per-turn: increment temple prestige and award civ prestige.

    Civ prestige is awarded to the region controller, not the original builder.
    Phase 10 placement: one-turn delay intentional — temple prestige is slow-moving
    (+1/turn) and the delay has negligible behavioral impact.
    Note: temple_prestige is uncapped — M38b pilgrimage targeting consumes it.
    """
    temple_prestige_rate = int(get_override(world, K_TEMPLE_PRESTIGE_PER_TURN, 1))
    civ_prestige_rate = int(get_override(world, K_CIV_PRESTIGE_PER_TEMPLE, 1))
    civ_temple_counts = {}
    for region in world.regions:
        controller = getattr(region, 'controller', None)
        for infra in region.infrastructure:
            if infra.type == IType.TEMPLES and infra.active:
                infra.temple_prestige += temple_prestige_rate
                if controller:
                    civ_temple_counts[controller] = civ_temple_counts.get(controller, 0) + 1

    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        count = civ_temple_counts.get(civ.name, 0)
        if count > 0:
            delta = civ_prestige_rate * count
            if acc is not None:
                acc.add(civ_index(world, civ.name), civ, "prestige", delta, "keep")
            else:
                civ.prestige += delta


def destroy_temple_on_conquest(region, attacker_civ, world) -> "Event | None":
    from chronicler.models import Event
    for infra in region.infrastructure:
        if infra.type == IType.TEMPLES and infra.active:
            infra.active = False
            return Event(
                turn=world.turn, event_type="temple_destroyed",
                actors=[attacker_civ.name],
                description=f"Temple of faith {infra.faith_id} destroyed in {getattr(region, 'name', '?')}",
                importance=5,
            )
    return None


def destroy_temple_for_replacement(region, world) -> "Event | None":
    from chronicler.models import Event
    for infra in region.infrastructure:
        if infra.type == IType.TEMPLES and infra.active:
            infra.active = False
            return Event(
                turn=world.turn, event_type="temple_destroyed",
                actors=[],
                description=f"Temple of faith {infra.faith_id} replaced in {getattr(region, 'name', '?')}",
                importance=5,
            )
    return None
