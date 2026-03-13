"""Technology progression system — advancement checks, era bonuses, war multipliers."""

from __future__ import annotations

from chronicler.models import Civilization, Event, TechEra, WorldState
from chronicler.utils import clamp


_ERA_ORDER = list(TechEra)


def _era_index(era: TechEra) -> int:
    return _ERA_ORDER.index(era)


def _next_era(era: TechEra) -> TechEra | None:
    idx = _era_index(era)
    if idx + 1 < len(_ERA_ORDER):
        return _ERA_ORDER[idx + 1]
    return None


TECH_REQUIREMENTS: dict[TechEra, tuple[int, int, int]] = {
    TechEra.TRIBAL: (4, 4, 10),
    TechEra.BRONZE: (5, 5, 12),
    TechEra.IRON: (6, 6, 15),
    TechEra.CLASSICAL: (7, 7, 18),
    TechEra.MEDIEVAL: (8, 8, 22),
    TechEra.RENAISSANCE: (9, 9, 28),
}

ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 1},
    TechEra.IRON: {"economy": 1},
    TechEra.CLASSICAL: {"culture": 1},
    TechEra.MEDIEVAL: {"military": 1},
    TechEra.RENAISSANCE: {"economy": 2, "culture": 1},
    TechEra.INDUSTRIAL: {"economy": 2, "military": 2},
}


def check_tech_advancement(civ: Civilization, world: WorldState) -> Event | None:
    reqs = TECH_REQUIREMENTS.get(civ.tech_era)
    if reqs is None:
        return None
    min_culture, min_economy, cost = reqs
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < cost:
        return None
    civ.treasury -= cost
    new_era = _next_era(civ.tech_era)
    assert new_era is not None
    civ.tech_era = new_era
    apply_era_bonus(civ, new_era)
    return Event(
        turn=world.turn, event_type="tech_advancement", actors=[civ.name],
        description=f"{civ.name} advances to the {new_era.value} era", importance=7,
    )


def apply_era_bonus(civ: Civilization, era: TechEra) -> None:
    bonuses = ERA_BONUSES.get(era, {})
    for stat, amount in bonuses.items():
        if isinstance(amount, int) and hasattr(civ, stat):
            current = getattr(civ, stat)
            setattr(civ, stat, clamp(current + amount, 1, 10))


def tech_war_multiplier(attacker_era: TechEra, defender_era: TechEra) -> float:
    gap = _era_index(attacker_era) - _era_index(defender_era)
    if abs(gap) >= 4:
        raw_mult = 2.0
    elif abs(gap) >= 2:
        raw_mult = 1.5
    else:
        return 1.0
    if gap > 0:
        return raw_mult
    else:
        return 1.0 / raw_mult
