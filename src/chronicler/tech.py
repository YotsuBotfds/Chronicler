"""Technology progression system — advancement checks, era bonuses, war multipliers."""

from __future__ import annotations

from chronicler.models import Civilization, Event, TechEra, WorldState
from chronicler.utils import clamp, STAT_FLOOR


_ERA_ORDER = list(TechEra)


def _era_index(era: TechEra) -> int:
    return _ERA_ORDER.index(era)


def _next_era(era: TechEra) -> TechEra | None:
    idx = _era_index(era)
    if idx + 1 < len(_ERA_ORDER):
        return _ERA_ORDER[idx + 1]
    return None


TECH_REQUIREMENTS: dict[TechEra, tuple[int, int, int]] = {
    TechEra.TRIBAL: (40, 40, 100),
    TechEra.BRONZE: (50, 50, 120),
    TechEra.IRON: (60, 60, 150),
    TechEra.CLASSICAL: (70, 70, 180),
    TechEra.MEDIEVAL: (80, 80, 220),
    TechEra.RENAISSANCE: (90, 90, 280),
}

ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 10},
    TechEra.IRON: {"economy": 10},
    TechEra.CLASSICAL: {"culture": 10},
    TechEra.MEDIEVAL: {"military": 10},
    TechEra.RENAISSANCE: {"economy": 20, "culture": 10},
    TechEra.INDUSTRIAL: {"economy": 20, "military": 20},
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
            setattr(civ, stat, clamp(current + amount, STAT_FLOOR.get(stat, 0), 100))


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
