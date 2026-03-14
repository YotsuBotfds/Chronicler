"""M16b: Ideas as entities — emergence, spread, adoption, variant drift, schism detection."""

from __future__ import annotations

import hashlib

from chronicler.models import Movement, NamedEvent, TechEra, WorldState
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


def tick_movements(world: WorldState) -> None:
    _check_emergence(world)
