"""M16b: Ideas as entities — emergence, spread, adoption, variant drift, schism detection."""

from __future__ import annotations

import hashlib

from chronicler.models import Event, Movement, NamedEvent, TechEra, WorldState
from chronicler.culture import VALUE_OPPOSITIONS

MOVEMENT_EMERGENCE_INTERVAL = 30
SCHISM_DIVERGENCE_THRESHOLD = 3
VARIANT_DRIFT_INTERVAL = 10
SEEDED_OFFSET_RANGE = 3

_ERA_BONUS: dict[TechEra, float] = {
    TechEra.TRIBAL: 0.0, TechEra.BRONZE: 0.0,
    TechEra.IRON: 0.1, TechEra.CLASSICAL: 0.1,
    TechEra.MEDIEVAL: 0.2, TechEra.RENAISSANCE: 0.2,
    TechEra.INDUSTRIAL: 0.3,
    TechEra.INFORMATION: 0.3,
}

STAT_MAX = 100


def _seeded_offset(civ_name: str, movement_id: str) -> int:
    return int(hashlib.sha256(
        (civ_name + movement_id).encode()
    ).hexdigest(), 16) % SEEDED_OFFSET_RANGE


def _check_emergence(world: WorldState) -> None:
    if world.turn == 0 or world.turn % MOVEMENT_EMERGENCE_INTERVAL != 0:
        return

    scored: list[tuple[float, str]] = []
    for civ in world.civilizations:
        if not civ.values:
            continue
        era_bonus = _ERA_BONUS.get(civ.tech_era, 0.3)
        score = (civ.culture / STAT_MAX) + (1 - civ.stability / STAT_MAX) + era_bonus
        scored.append((score, civ.name))

    if not scored:
        return

    max_score = max(s for s, _ in scored)
    tied = [name for s, name in scored if s == max_score]

    if len(tied) > 1:
        salt = f"{world.seed}:{world.turn}:movement_origin"
        tied.sort(key=lambda name: hashlib.sha256(
            f"{salt}:{name}".encode()
        ).hexdigest())

    winner_name = tied[0]
    winner = next(c for c in world.civilizations if c.name == winner_name)

    movement_id = f"movement_{world.next_movement_id}"
    movement = Movement(
        id=movement_id,
        origin_civ=winner.name,
        origin_turn=world.turn,
        value_affinity=winner.values[0],
        adherents={winner.name: _seeded_offset(winner.name, movement_id)},
    )
    world.movements.append(movement)
    world.next_movement_id += 1

    world.named_events.append(NamedEvent(
        name=f"Rise of {movement_id.replace('_', ' ').title()}",
        event_type="movement_emergence",
        turn=world.turn,
        actors=[winner.name],
        description=f"A new ideological movement emerges from {winner.name}, rooted in {movement.value_affinity}.",
        importance=6,
    ))


def _process_spread(world: WorldState) -> None:
    for movement in world.movements:
        current_adherents = list(movement.adherents.keys())
        for adopter_name in current_adherents:
            for civ in world.civilizations:
                if not civ.regions:
                    continue
                if civ.name == adopter_name or civ.name in movement.adherents:
                    continue
                rel = world.relationships.get(adopter_name, {}).get(civ.name)
                if rel is None or rel.trade_volume <= 0:
                    continue

                if movement.value_affinity in civ.values:
                    compatibility = 100
                elif VALUE_OPPOSITIONS.get(movement.value_affinity) in civ.values:
                    compatibility = 0
                else:
                    compatibility = 50

                adoption_probability = rel.trade_volume * compatibility / 100
                # M21: PRINTING doubles movement adoption probability
                if civ.active_focus == "printing":
                    adoption_probability *= 2
                    world.events_timeline.append(Event(
                        turn=world.turn, event_type="capability_printing",
                        actors=[civ.name], description=f"{civ.name} printing doubles movement adoption",
                        importance=1,
                    ))
                adoption_probability = min(adoption_probability, 100)
                roll = int(hashlib.sha256(
                    f"{world.seed}:{world.turn}:{movement.id}:{civ.name}:spread".encode()
                ).hexdigest(), 16) % 100

                if roll < adoption_probability:
                    movement.adherents[civ.name] = _seeded_offset(civ.name, movement.id)
                    world.named_events.append(NamedEvent(
                        name=f"{civ.name} adopts {movement.id.replace('_', ' ')}",
                        event_type="movement_adoption",
                        turn=world.turn,
                        actors=[civ.name, movement.origin_civ],
                        description=f"{civ.name} adopts a {movement.value_affinity}-aligned movement from {movement.origin_civ}.",
                        importance=5,
                    ))
                    world.events_timeline.append(Event(
                        turn=world.turn, event_type="movement_adoption",
                        actors=[civ.name, movement.origin_civ],
                        description=f"{civ.name} adopts a {movement.value_affinity}-aligned movement from {movement.origin_civ}.",
                        importance=5,
                    ))


def _increment_variants(world: WorldState) -> None:
    for movement in world.movements:
        if (world.turn - movement.origin_turn) % VARIANT_DRIFT_INTERVAL == 0:
            for civ_name in movement.adherents:
                movement.adherents[civ_name] += 1


def _detect_schisms(world: WorldState) -> None:
    from itertools import combinations
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for a, b in combinations(adherent_names, 2):
            divergence = abs(movement.adherents[a] - movement.adherents[b])
            if divergence >= SCHISM_DIVERGENCE_THRESHOLD:
                already_fired = any(
                    ne.event_type == "movement_schism"
                    and a in ne.actors and b in ne.actors
                    and movement.id in ne.description
                    for ne in world.named_events
                )
                if not already_fired:
                    world.named_events.append(NamedEvent(
                        name=f"Schism of {movement.id.replace('_', ' ')}",
                        event_type="movement_schism",
                        turn=world.turn,
                        actors=[a, b],
                        description=f"[{movement.id}] Schism between {a} and {b}.",
                        importance=7,
                    ))


def tick_movements(world: WorldState) -> None:
    _check_emergence(world)
    _process_spread(world)
    _increment_variants(world)
    _detect_schisms(world)
