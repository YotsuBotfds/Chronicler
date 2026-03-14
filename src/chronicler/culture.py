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


def tick_prestige(world: WorldState) -> None:
    """Decay prestige and award trade income bonus."""
    for civ in world.civilizations:
        civ.prestige = max(0, civ.prestige - 1)
        trade_bonus = civ.prestige // 5
        if trade_bonus > 0:
            civ.treasury += trade_bonus
