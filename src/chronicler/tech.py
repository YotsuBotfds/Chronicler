"""Technology progression system — advancement checks, era bonuses, war multipliers."""

from __future__ import annotations

from chronicler.models import Civilization, Event, Resource, TechEra, WorldState
from chronicler.utils import clamp, STAT_FLOOR


_ERA_ORDER = list(TechEra)


def _era_index(era: TechEra) -> int:
    return _ERA_ORDER.index(era)


def _next_era(era: TechEra) -> TechEra | None:
    idx = _era_index(era)
    if idx + 1 < len(_ERA_ORDER):
        return _ERA_ORDER[idx + 1]
    return None


def _prev_era(era: TechEra) -> TechEra | None:
    """Return the previous era, or None for TRIBAL."""
    idx = _era_index(era)
    if idx > 0:
        return _ERA_ORDER[idx - 1]
    return None


TECH_REQUIREMENTS: dict[TechEra, tuple[int, int, int]] = {
    TechEra.TRIBAL: (40, 40, 100),
    TechEra.BRONZE: (50, 50, 120),
    TechEra.IRON: (60, 60, 150),
    TechEra.CLASSICAL: (70, 70, 180),
    TechEra.MEDIEVAL: (80, 80, 220),
    TechEra.RENAISSANCE: (90, 90, 280),
    TechEra.INDUSTRIAL: (90, 80, 350),
}

ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 10, "military_multiplier": 1.0},
    TechEra.IRON: {"economy": 10, "military_multiplier": 1.3},
    TechEra.CLASSICAL: {"culture": 10, "fortification_multiplier": 1.0},
    TechEra.MEDIEVAL: {"military": 10, "fortification_multiplier": 2.0},
    TechEra.RENAISSANCE: {"economy": 20, "culture": 10},
    TechEra.INDUSTRIAL: {"economy": 20, "military": 20},
    TechEra.INFORMATION: {"culture": 10, "economy": 5, "culture_projection_range": -1},
}


def get_era_bonus(era: TechEra, key: str, default: float = 0.0) -> float:
    """Look up an era-specific bonus. Returns default if key not present for this era."""
    return ERA_BONUSES.get(era, {}).get(key, default)


RESOURCE_REQUIREMENTS: dict[TechEra, tuple[set[Resource] | None, int]] = {
    TechEra.TRIBAL: ({Resource.IRON, Resource.TIMBER}, 2),
    TechEra.BRONZE: ({Resource.IRON, Resource.TIMBER, Resource.GRAIN}, 3),
    TechEra.IRON: (None, 3),
    TechEra.CLASSICAL: (None, 4),
    TechEra.MEDIEVAL: (None, 4),
    TechEra.RENAISSANCE: (None, 5),
    TechEra.INDUSTRIAL: ({Resource.FUEL}, 5),
}


def _get_civ_resources(civ: Civilization, world: WorldState) -> set[Resource]:
    resources: set[Resource] = set()
    for r in world.regions:
        if r.controller == civ.name:
            resources.update(r.specialized_resources)
    return resources


def _check_resource_requirements(civ: Civilization, world: WorldState) -> bool:
    reqs = RESOURCE_REQUIREMENTS.get(civ.tech_era)
    if reqs is None:
        return True
    required_types, min_count = reqs
    civ_resources = _get_civ_resources(civ, world)
    if required_types and not required_types.issubset(civ_resources):
        return False
    if len(civ_resources) < min_count:
        return False
    return True


def check_tech_advancement(civ: Civilization, world: WorldState, acc=None) -> Event | None:
    reqs = TECH_REQUIREMENTS.get(civ.tech_era)
    if reqs is None:
        return None
    if not _check_resource_requirements(civ, world):
        return None
    min_culture, min_economy, cost = reqs
    if civ.active_focus == "scholarship":
        effective_cost = int(cost * 0.8)
        world.events_timeline.append(Event(
            turn=world.turn, event_type="capability_scholarship",
            actors=[civ.name], description=f"{civ.name} scholarship reduces tech cost",
            importance=1,
        ))
    else:
        effective_cost = cost
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < effective_cost:
        return None
    if acc is not None:
        civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
        acc.add(civ_idx, civ, "treasury", -effective_cost, "keep")
    else:
        civ.treasury -= effective_cost
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


def remove_era_bonus(civ: Civilization, era: TechEra) -> None:
    """Reverse of apply_era_bonus — subtract integer stat bonuses for an era."""
    bonuses = ERA_BONUSES.get(era, {})
    for stat, amount in bonuses.items():
        if isinstance(amount, int) and hasattr(civ, stat):
            current = getattr(civ, stat)
            setattr(civ, stat, clamp(current - amount, STAT_FLOOR.get(stat, 0), 100))


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
