"""M16a: Culture as property -- value drift, assimilation, prestige."""

from __future__ import annotations

from chronicler.models import ActiveCondition, Disposition, NamedEvent, WorldState
from chronicler.utils import clamp

VALUE_OPPOSITIONS: dict[str, str] = {
    "Freedom": "Order",
    "Order": "Freedom",
    "Liberty": "Order",
    "Tradition": "Knowledge",
    "Knowledge": "Tradition",
    "Honor": "Cunning",
    "Cunning": "Honor",
    "Piety": "Cunning",
    "Self-reliance": "Trade",
    "Trade": "Self-reliance",
}

_DISPOSITION_ORDER = list(Disposition)


def _upgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[min(idx + 1, len(_DISPOSITION_ORDER) - 1)]


def _downgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[max(idx - 1, 0)]


def apply_value_drift(world: WorldState) -> None:
    """Accumulate disposition drift from shared/opposing values."""
    from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD

    civs = world.civilizations
    for i, civ_a in enumerate(civs):
        for civ_b in civs[i + 1:]:
            shared = sum(1 for v in civ_a.values if v in civ_b.values)
            opposing = sum(
                1 for va in civ_a.values for vb in civ_b.values
                if VALUE_OPPOSITIONS.get(va) == vb
            )
            net_drift = (shared * 2) - (opposing * 2)
            if net_drift == 0:
                continue

            for a_name, b_name in [(civ_a.name, civ_b.name), (civ_b.name, civ_a.name)]:
                rel = world.relationships.get(a_name, {}).get(b_name)
                if rel is None:
                    continue
                rel.disposition_drift += net_drift
                if rel.disposition_drift >= 10:
                    rel.disposition = _upgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0
                elif rel.disposition_drift <= -10:
                    rel.disposition = _downgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0

    # Movement co-adoption effects (accumulate only — threshold applied next cycle)
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for idx_a, name_a in enumerate(adherent_names):
            for name_b in adherent_names[idx_a + 1:]:
                divergence = abs(movement.adherents[name_a] - movement.adherents[name_b])
                movement_drift = 5 if divergence < SCHISM_DIVERGENCE_THRESHOLD else -5
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel is None:
                        continue
                    rel.disposition_drift += movement_drift


ASSIMILATION_THRESHOLD = 15
ASSIMILATION_STABILITY_DRAIN = 3
RECONQUEST_COOLDOWN = 10


def tick_cultural_assimilation(world: WorldState) -> None:
    """Tick cultural assimilation for all regions."""
    for region in world.regions:
        if region.controller is None:
            continue

        if region.cultural_identity is None:
            region.cultural_identity = region.controller
            continue

        if region.cultural_identity == region.controller:
            if region.foreign_control_turns > 0:
                region.foreign_control_turns = 0
                world.active_conditions.append(ActiveCondition(
                    condition_type="restless_population",
                    affected_civs=[region.controller],
                    duration=RECONQUEST_COOLDOWN,
                    severity=5,
                ))
            continue

        region.foreign_control_turns += 1

        if region.foreign_control_turns >= ASSIMILATION_THRESHOLD:
            region.cultural_identity = region.controller
            region.foreign_control_turns = 0
            world.named_events.append(NamedEvent(
                name=f"Assimilation of {region.name}",
                event_type="cultural_assimilation",
                turn=world.turn,
                actors=[region.controller],
                region=region.name,
                description=f"{region.name} has been culturally assimilated by {region.controller}.",
                importance=6,
            ))
        elif region.foreign_control_turns >= RECONQUEST_COOLDOWN:
            controller = next(
                (c for c in world.civilizations if c.name == region.controller), None
            )
            if controller:
                controller.stability = clamp(
                    controller.stability - ASSIMILATION_STABILITY_DRAIN, 0, 100
                )


PROPAGANDA_COST = 5
PROPAGANDA_ACCELERATION = 3
COUNTER_PROPAGANDA_COST = 3
CULTURE_PROJECTION_THRESHOLD = 60


def _counter_propaganda_reaction(world: WorldState, defender, region, seed: int) -> int:
    if defender.treasury >= COUNTER_PROPAGANDA_COST:
        defender.treasury -= COUNTER_PROPAGANDA_COST
        return -PROPAGANDA_ACCELERATION
    return 0


def resolve_invest_culture(civ, world: WorldState):
    """Resolve INVEST_CULTURE action: project propaganda into a rival region."""
    import hashlib
    from chronicler.models import Event, NamedEvent
    from chronicler.tech import get_era_bonus

    projection_range = get_era_bonus(civ.tech_era, "culture_projection_range", default=1)
    global_projection = projection_range == -1

    candidates = [
        r for r in world.regions
        if r.controller is not None
        and r.controller != civ.name
        and r.cultural_identity != civ.name
    ]

    if global_projection:
        targets = candidates
    else:
        civ_regions = {r.name for r in world.regions if r.controller == civ.name}
        adjacent = set()
        for r in world.regions:
            if r.name in civ_regions:
                adjacent.update(r.adjacencies)
        targets = [r for r in candidates if r.name in adjacent]

    if not targets or civ.treasury < PROPAGANDA_COST:
        return Event(
            turn=world.turn, event_type="action", actors=[civ.name],
            description=f"{civ.name} attempts cultural influence but finds no valid target.",
            importance=1,
        )

    targets.sort(key=lambda r: r.foreign_control_turns, reverse=True)
    max_fct = targets[0].foreign_control_turns
    tied = [r for r in targets if r.foreign_control_turns == max_fct]
    if len(tied) > 1:
        salt = f"{world.seed}:{world.turn}:propaganda:{civ.name}"
        tied.sort(key=lambda r: hashlib.sha256(f"{salt}:{r.name}".encode()).hexdigest())
    target = tied[0]

    civ.treasury -= PROPAGANDA_COST

    defender = next((c for c in world.civilizations if c.name == target.controller), None)
    adjustment = 0
    if defender:
        adjustment = _counter_propaganda_reaction(world, defender, target, world.seed)

    net_acceleration = PROPAGANDA_ACCELERATION + adjustment
    target.foreign_control_turns += net_acceleration

    world.named_events.append(NamedEvent(
        name=f"Propaganda in {target.name}",
        event_type="propaganda_campaign",
        turn=world.turn,
        actors=[civ.name],
        region=target.name,
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    ))

    return Event(
        turn=world.turn, event_type="invest_culture", actors=[civ.name],
        description=f"{civ.name} projects cultural influence into {target.name}.",
        importance=5,
    )


def tick_prestige(world: WorldState) -> None:
    """Decay prestige and award trade income bonus."""
    for civ in world.civilizations:
        civ.prestige = max(0, civ.prestige - 1)
        trade_bonus = civ.prestige // 5
        if trade_bonus > 0:
            civ.treasury += trade_bonus
