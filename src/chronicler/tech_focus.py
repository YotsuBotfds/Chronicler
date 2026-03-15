"""Tech specialization — divergent development paths from deterministic state-based selection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from chronicler.models import (
    ActionType, Civilization, Event, InfrastructureType, Resource, TechEra, WorldState,
)
from chronicler.utils import clamp, STAT_FLOOR


# ---------------------------------------------------------------------------
# Part 1: TechFocus Enum + ERA_FOCUSES
# ---------------------------------------------------------------------------

class TechFocus(str, Enum):
    # Classical
    NAVIGATION = "navigation"
    METALLURGY = "metallurgy"
    AGRICULTURE = "agriculture"
    # Medieval
    FORTIFICATION = "fortification"
    COMMERCE = "commerce"
    SCHOLARSHIP = "scholarship"
    # Renaissance
    EXPLORATION = "exploration"
    BANKING = "banking"
    PRINTING = "printing"
    # Industrial
    MECHANIZATION = "mechanization"
    RAILWAYS = "railways"
    NAVAL_POWER = "naval_power"
    # Information
    NETWORKS = "networks"
    SURVEILLANCE = "surveillance"
    MEDIA = "media"


ERA_FOCUSES: dict[TechEra, list[TechFocus]] = {
    TechEra.CLASSICAL: [TechFocus.NAVIGATION, TechFocus.METALLURGY, TechFocus.AGRICULTURE],
    TechEra.MEDIEVAL: [TechFocus.FORTIFICATION, TechFocus.COMMERCE, TechFocus.SCHOLARSHIP],
    TechEra.RENAISSANCE: [TechFocus.EXPLORATION, TechFocus.BANKING, TechFocus.PRINTING],
    TechEra.INDUSTRIAL: [TechFocus.MECHANIZATION, TechFocus.RAILWAYS, TechFocus.NAVAL_POWER],
    TechEra.INFORMATION: [TechFocus.NETWORKS, TechFocus.SURVEILLANCE, TechFocus.MEDIA],
}


# ---------------------------------------------------------------------------
# Part 2: Scoring Helpers
# ---------------------------------------------------------------------------

def _count_terrain(civ: Civilization, world: WorldState, terrain: str) -> int:
    return sum(1 for r in world.regions if r.controller == civ.name and r.terrain == terrain)


def _count_resource(civ: Civilization, world: WorldState, resource: Resource) -> int:
    return sum(1 for r in world.regions if r.controller == civ.name and resource in r.specialized_resources)


def _count_infra(civ: Civilization, world: WorldState, infra_type: InfrastructureType) -> int:
    return sum(
        1
        for r in world.regions if r.controller == civ.name
        for i in r.infrastructure if i.type == infra_type and i.active
    )


def _count_trade_routes(civ: Civilization, world: WorldState) -> int:
    from chronicler.resources import get_active_trade_routes
    return sum(1 for route in get_active_trade_routes(world) if civ.name in route)


def _count_unclaimed_adjacent(civ: Civilization, world: WorldState) -> int:
    civ_regions = {r.name for r in world.regions if r.controller == civ.name}
    adjacent: set[str] = set()
    for r in world.regions:
        if r.name in civ_regions:
            adjacent.update(r.adjacencies)
    unclaimed: set[str] = set()
    for r in world.regions:
        if r.name in adjacent and r.name not in civ_regions and r.controller is None:
            unclaimed.add(r.name)
    return len(unclaimed)


def _count_border_regions(civ: Civilization, world: WorldState) -> int:
    region_controllers = {r.name: r.controller for r in world.regions}
    count = 0
    for r in world.regions:
        if r.controller != civ.name:
            continue
        for adj_name in r.adjacencies:
            adj_ctrl = region_controllers.get(adj_name)
            if adj_ctrl is not None and adj_ctrl != civ.name:
                count += 1
                break
    return count


def _count_great_persons(civ: Civilization) -> int:
    return sum(1 for gp in civ.great_persons if gp.active)


def _count_civ_movements(civ: Civilization, world: WorldState) -> int:
    return sum(1 for m in world.movements if civ.name in m.adherents)


# ---------------------------------------------------------------------------
# Part 3: Scoring Formulas + GP/Tradition Bonuses + select_tech_focus()
# ---------------------------------------------------------------------------

# Great-person role -> focuses that get +5 bonus
_GP_BONUSES: dict[str, list[TechFocus]] = {
    "scientist": [TechFocus.SCHOLARSHIP, TechFocus.PRINTING, TechFocus.NETWORKS],
    "merchant": [TechFocus.COMMERCE, TechFocus.BANKING, TechFocus.RAILWAYS],
    "general": [TechFocus.METALLURGY, TechFocus.FORTIFICATION, TechFocus.MECHANIZATION],
    "prophet": [TechFocus.AGRICULTURE, TechFocus.SCHOLARSHIP, TechFocus.MEDIA],
}

# Tradition name -> focuses that get +3 bonus
_TRADITION_BONUSES: dict[str, list[TechFocus]] = {
    "scholarly": [TechFocus.SCHOLARSHIP, TechFocus.PRINTING, TechFocus.MEDIA],
    "martial": [TechFocus.METALLURGY, TechFocus.FORTIFICATION, TechFocus.MECHANIZATION],
}

# All-zero fallback: era -> {stat_name -> focus}
_FALLBACK: dict[TechEra, dict[str, TechFocus]] = {
    TechEra.CLASSICAL: {
        "military": TechFocus.METALLURGY,
        "economy": TechFocus.NAVIGATION,
        "culture": TechFocus.AGRICULTURE,
    },
    TechEra.MEDIEVAL: {
        "military": TechFocus.FORTIFICATION,
        "economy": TechFocus.COMMERCE,
        "culture": TechFocus.SCHOLARSHIP,
    },
    TechEra.RENAISSANCE: {
        "military": TechFocus.EXPLORATION,
        "economy": TechFocus.BANKING,
        "culture": TechFocus.PRINTING,
    },
    TechEra.INDUSTRIAL: {
        "military": TechFocus.NAVAL_POWER,
        "economy": TechFocus.MECHANIZATION,
        "culture": TechFocus.RAILWAYS,
    },
    TechEra.INFORMATION: {
        "military": TechFocus.SURVEILLANCE,
        "economy": TechFocus.NETWORKS,
        "culture": TechFocus.MEDIA,
    },
}


def _score_focus(focus: TechFocus, civ: Civilization, world: WorldState) -> float:
    """Compute the raw score for a single focus option."""
    if focus == TechFocus.NAVIGATION:
        coastal = _count_terrain(civ, world, "coast")
        ports = _count_infra(civ, world, InfrastructureType.PORTS)
        return coastal * 3 + ports * 5

    elif focus == TechFocus.METALLURGY:
        iron_regions = _count_resource(civ, world, Resource.IRON)
        mines = _count_infra(civ, world, InfrastructureType.MINES)
        return iron_regions * 4 + mines * 5

    elif focus == TechFocus.AGRICULTURE:
        grain = _count_resource(civ, world, Resource.GRAIN)
        irrigated = _count_infra(civ, world, InfrastructureType.IRRIGATION)
        return grain * 3 + irrigated * 5 + civ.population * 0.1

    elif focus == TechFocus.FORTIFICATION:
        forts = _count_infra(civ, world, InfrastructureType.FORTIFICATIONS)
        borders = _count_border_regions(civ, world)
        return forts * 5 + borders * 3 + civ.military * 0.2

    elif focus == TechFocus.COMMERCE:
        trade = _count_trade_routes(civ, world)
        ports = _count_infra(civ, world, InfrastructureType.PORTS)
        return trade * 5 + civ.treasury * 0.1 + ports * 3

    elif focus == TechFocus.SCHOLARSHIP:
        gps = _count_great_persons(civ)
        return civ.culture * 0.3 + gps * 5 + len(civ.traditions) * 3

    elif focus == TechFocus.EXPLORATION:
        regions = sum(1 for r in world.regions if r.controller == civ.name)
        unclaimed = _count_unclaimed_adjacent(civ, world)
        return regions * 3 + civ.military * 0.15 + unclaimed * 4

    elif focus == TechFocus.BANKING:
        trade = _count_trade_routes(civ, world)
        return civ.treasury * 0.15 + civ.economy * 0.3 + trade * 3

    elif focus == TechFocus.PRINTING:
        movements = _count_civ_movements(civ, world)
        gps = _count_great_persons(civ)
        return civ.culture * 0.2 + movements * 5 + gps * 3

    elif focus == TechFocus.MECHANIZATION:
        mines = _count_infra(civ, world, InfrastructureType.MINES)
        iron_regions = _count_resource(civ, world, Resource.IRON)
        return mines * 5 + iron_regions * 3 + civ.economy * 0.2

    elif focus == TechFocus.RAILWAYS:
        roads = _count_infra(civ, world, InfrastructureType.ROADS)
        regions = sum(1 for r in world.regions if r.controller == civ.name)
        trade = _count_trade_routes(civ, world)
        return roads * 5 + regions * 3 + trade * 2

    elif focus == TechFocus.NAVAL_POWER:
        coastal = _count_terrain(civ, world, "coast")
        ports = _count_infra(civ, world, InfrastructureType.PORTS)
        return coastal * 5 + ports * 5 + civ.military * 0.2

    elif focus == TechFocus.NETWORKS:
        trade = _count_trade_routes(civ, world)
        roads = _count_infra(civ, world, InfrastructureType.ROADS)
        return trade * 5 + roads * 3 + civ.economy * 0.2

    elif focus == TechFocus.SURVEILLANCE:
        regions = sum(1 for r in world.regions if r.controller == civ.name)
        return regions * 3 + civ.stability * 0.3 + civ.population * 0.05

    elif focus == TechFocus.MEDIA:
        movements = _count_civ_movements(civ, world)
        gps = _count_great_persons(civ)
        return civ.culture * 0.3 + movements * 5 + gps * 3

    return 0.0  # pragma: no cover


def _tiebreak_hash(seed: int, civ_name: str, key: str) -> int:
    """Deterministic tiebreak based on seed, civ name, and a key string."""
    raw = f"{seed}:{civ_name}:{key}"
    return int(hashlib.sha256(raw.encode()).hexdigest(), 16)


def select_tech_focus(civ: Civilization, world: WorldState) -> TechFocus | None:
    """Select the best tech focus for *civ* in its current era.

    Returns ``None`` if the civ's era has no focus options (pre-Classical).
    """
    era = civ.tech_era
    options = ERA_FOCUSES.get(era)
    if options is None:
        return None

    # --- Score each option ---
    scores: dict[TechFocus, float] = {}
    for focus in options:
        scores[focus] = _score_focus(focus, civ, world)

    # --- GP bonuses (+5 per matching active GP) ---
    for gp in civ.great_persons:
        if not gp.active:
            continue
        bonuses = _GP_BONUSES.get(gp.role, [])
        for focus in options:
            if focus in bonuses:
                scores[focus] += 5

    # --- Tradition bonuses (+3 per matching tradition) ---
    for tradition in civ.traditions:
        bonuses = _TRADITION_BONUSES.get(tradition, [])
        for focus in options:
            if focus in bonuses:
                scores[focus] += 3

    # --- All-zero fallback ---
    if all(s == 0 for s in scores.values()):
        fallback = _FALLBACK.get(era, {})
        stat_values = {
            "military": civ.military,
            "economy": civ.economy,
            "culture": civ.culture,
        }
        # Find the highest stat, tiebreak by hash
        best_stat = max(
            stat_values,
            key=lambda s: (stat_values[s], _tiebreak_hash(world.seed, civ.name, s)),
        )
        return fallback.get(best_stat)

    # --- Pick highest score, tiebreak by hash ---
    best_focus = max(
        scores,
        key=lambda f: (scores[f], _tiebreak_hash(world.seed, civ.name, f.value)),
    )
    return best_focus


# ---------------------------------------------------------------------------
# Part 4: FOCUS_EFFECTS Table + apply/remove/get_weight_modifiers
# ---------------------------------------------------------------------------

@dataclass
class FocusEffect:
    stat_modifiers: dict[str, int] = field(default_factory=dict)
    weight_modifiers: dict[ActionType, float] = field(default_factory=dict)
    capability: str = ""


FOCUS_EFFECTS: dict[TechFocus, FocusEffect] = {
    TechFocus.NAVIGATION: FocusEffect(
        stat_modifiers={"economy": 5},
        weight_modifiers={ActionType.EXPLORE: 1.5, ActionType.TRADE: 1.3},
        capability="navigation",
    ),
    TechFocus.METALLURGY: FocusEffect(
        stat_modifiers={"military": 15},
        weight_modifiers={ActionType.WAR: 1.3, ActionType.BUILD: 1.2},
        capability="metallurgy",
    ),
    TechFocus.AGRICULTURE: FocusEffect(
        stat_modifiers={"economy": 10},
        weight_modifiers={ActionType.BUILD: 1.3, ActionType.TRADE: 1.2},
        capability="agriculture",
    ),
    TechFocus.FORTIFICATION: FocusEffect(
        stat_modifiers={"military": 10},
        weight_modifiers={ActionType.BUILD: 1.5, ActionType.WAR: 1.2},
        capability="fortification",
    ),
    TechFocus.COMMERCE: FocusEffect(
        stat_modifiers={"economy": 10},
        weight_modifiers={ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.2},
        capability="commerce",
    ),
    TechFocus.SCHOLARSHIP: FocusEffect(
        stat_modifiers={"culture": 10},
        weight_modifiers={ActionType.INVEST_CULTURE: 1.3, ActionType.DIPLOMACY: 1.2},
        capability="scholarship",
    ),
    TechFocus.EXPLORATION: FocusEffect(
        stat_modifiers={"military": 5},
        weight_modifiers={ActionType.EXPLORE: 1.5, ActionType.WAR: 1.2},
        capability="exploration",
    ),
    TechFocus.BANKING: FocusEffect(
        stat_modifiers={"economy": 15},
        weight_modifiers={ActionType.TRADE: 1.3, ActionType.EMBARGO: 1.3},
        capability="banking",
    ),
    TechFocus.PRINTING: FocusEffect(
        stat_modifiers={"culture": 15},
        weight_modifiers={ActionType.INVEST_CULTURE: 1.5, ActionType.DIPLOMACY: 1.3},
        capability="printing",
    ),
    TechFocus.MECHANIZATION: FocusEffect(
        stat_modifiers={"economy": 10},
        weight_modifiers={ActionType.BUILD: 1.5, ActionType.TRADE: 1.2},
        capability="mechanization",
    ),
    TechFocus.RAILWAYS: FocusEffect(
        stat_modifiers={"economy": 5},
        weight_modifiers={ActionType.BUILD: 1.3, ActionType.TRADE: 1.3},
        capability="railways",
    ),
    TechFocus.NAVAL_POWER: FocusEffect(
        stat_modifiers={"military": 15},
        weight_modifiers={ActionType.WAR: 1.5, ActionType.EXPLORE: 1.2},
        capability="naval_power",
    ),
    TechFocus.NETWORKS: FocusEffect(
        stat_modifiers={"economy": 10},
        weight_modifiers={ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.2},
        capability="networks",
    ),
    TechFocus.SURVEILLANCE: FocusEffect(
        stat_modifiers={"stability": 10},
        weight_modifiers={ActionType.DIPLOMACY: 1.3, ActionType.WAR: 1.2},
        capability="surveillance",
    ),
    TechFocus.MEDIA: FocusEffect(
        stat_modifiers={"culture": 15},
        weight_modifiers={ActionType.INVEST_CULTURE: 1.5, ActionType.TRADE: 1.2},
        capability="media",
    ),
}


def apply_focus_effects(civ: Civilization, focus: TechFocus) -> None:
    """Apply stat modifiers from *focus*, set active_focus, and record in history."""
    effect = FOCUS_EFFECTS[focus]
    for stat, mod in effect.stat_modifiers.items():
        floor = STAT_FLOOR.get(stat, 0)
        high = 1000 if stat == "population" else 100
        current = getattr(civ, stat)
        setattr(civ, stat, clamp(current + mod, floor, high))
    civ.active_focus = focus.value
    civ.tech_focuses.append(focus.value)


def remove_focus_effects(civ: Civilization, focus: TechFocus) -> None:
    """Remove (subtract) stat modifiers from *focus*."""
    effect = FOCUS_EFFECTS[focus]
    for stat, mod in effect.stat_modifiers.items():
        floor = STAT_FLOOR.get(stat, 0)
        high = 1000 if stat == "population" else 100
        current = getattr(civ, stat)
        setattr(civ, stat, clamp(current - mod, floor, high))


def get_focus_weight_modifiers(civ: Civilization) -> dict[ActionType, float]:
    """Return action-weight modifiers from *civ*'s active focus, or empty dict."""
    if civ.active_focus is None:
        return {}
    try:
        focus = TechFocus(civ.active_focus)
    except ValueError:
        return {}
    effect = FOCUS_EFFECTS.get(focus)
    if effect is None:
        return {}
    return dict(effect.weight_modifiers)
