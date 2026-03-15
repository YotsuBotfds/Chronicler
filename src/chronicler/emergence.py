"""M18 Emergence and Chaos — black swans, stress, regression, ecological succession.

All cross-system emergence logic centralized in one module. Called from
existing turn phases via distributed hooks in simulation.py.
"""
from __future__ import annotations

import random

from chronicler.models import (
    ActiveCondition, Civilization, Event, PandemicRegion, Region,
    Resource, TechEra, WorldState,
)
from chronicler.resources import get_active_trade_routes
from chronicler.utils import clamp, STAT_FLOOR


# ---------------------------------------------------------------------------
# Stress Index & Cascade Severity
# ---------------------------------------------------------------------------

def compute_civ_stress(civ: Civilization, world: WorldState) -> int:
    """Compute per-civ stress from current world state. Returns 0-20."""
    stress = 0

    # Active wars: 3 per war (active_wars is list[tuple[str, str]])
    stress += sum(1 for w in world.active_wars if civ.name in w) * 3

    # Famine in controlled regions: 2 per famine region
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.famine_cooldown > 0
    ) * 2

    # Active secession risk: 4 if stability < 20 with 3+ regions
    if civ.stability < 20 and len(civ.regions) >= 3:
        stress += 4

    # Active pandemic in controlled regions: 2 per infected region
    infected_region_names = {p.region_name for p in world.pandemic_state}
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.name in infected_region_names
    ) * 2

    # Recent turbulent succession: 2 if general/usurper within last 5 turns
    if (civ.leader.succession_type in ("general", "usurper")
            and world.turn - civ.leader.reign_start <= 5):
        stress += 2

    # In twilight: 3
    if civ.decline_turns > 0:
        stress += 3

    # Active disaster conditions: 2 per qualifying condition
    stress += sum(
        1 for c in world.active_conditions
        if civ.name in c.affected_civs
        and c.condition_type in ("drought", "volcanic_winter")
    ) * 2

    # Overextension: 1 per region beyond 6
    stress += max(0, len(civ.regions) - 6)

    return min(stress, 20)


def compute_all_stress(world: WorldState) -> None:
    """Recompute stress for all civs and set global aggregate."""
    for civ in world.civilizations:
        civ.civ_stress = compute_civ_stress(civ, world)
    if world.civilizations:
        world.stress_index = max(c.civ_stress for c in world.civilizations)
    else:
        world.stress_index = 0


def get_severity_multiplier(civ: Civilization) -> float:
    """Return cascade severity multiplier based on civ stress. Range: 1.0-1.5."""
    return 1.0 + (civ.civ_stress / 20) * 0.5


# ---------------------------------------------------------------------------
# Black Swan Events
# ---------------------------------------------------------------------------

_BLACK_SWAN_BASE_PROB = 0.005  # 0.5% per turn
_DEFAULT_COOLDOWN = 30

# Event type names (shared constant for detection in simulation.py)
BLACK_SWAN_EVENT_TYPES = frozenset({"pandemic", "supervolcano", "resource_discovery", "tech_accident"})

# Weights for event type selection
_EVENT_WEIGHTS = {
    "pandemic": 3,
    "supervolcano": 2,
    "resource_discovery": 2,
    "tech_accident": 1,
}


def _count_trade_partners(civ_name: str, world: WorldState) -> int:
    """Count distinct trading partners for a civ."""
    routes = get_active_trade_routes(world)
    partners = set()
    for a, b in routes:
        if a == civ_name:
            partners.add(b)
        elif b == civ_name:
            partners.add(a)
    # M17: merchant great person adds +1 to partner count
    for civ in world.civilizations:
        if civ.name == civ_name:
            for gp in civ.great_persons:
                if gp.role == "merchant" and gp.active:
                    return len(partners) + 1
            break
    return len(partners)


def _find_volcano_triples(world: WorldState) -> list[tuple[Region, Region, Region]]:
    """Find all region triples where each pair is adjacent and at least one is controlled."""
    regions = world.regions
    triples = []
    for i, a in enumerate(regions):
        for j, b in enumerate(regions):
            if j <= i:
                continue
            if b.name not in a.adjacencies:
                continue
            for k, c in enumerate(regions):
                if k <= j:
                    continue
                if c.name not in a.adjacencies or c.name not in b.adjacencies:
                    continue
                if a.controller or b.controller or c.controller:
                    triples.append((a, b, c))
    return triples


def _get_eligible_types(world: WorldState) -> dict[str, int]:
    """Return eligible black swan types with their weights."""
    eligible = {}

    # Pandemic: any civ has 3+ distinct trading partners
    for civ in world.civilizations:
        if _count_trade_partners(civ.name, world) >= 3:
            eligible["pandemic"] = _EVENT_WEIGHTS["pandemic"]
            break

    # Supervolcano: any cluster of 3 mutually adjacent regions with at least one controlled
    if _find_volcano_triples(world):
        eligible["supervolcano"] = _EVENT_WEIGHTS["supervolcano"]

    # Resource discovery: any region with 0 specialized resources
    if any(len(r.specialized_resources) == 0 for r in world.regions):
        eligible["resource_discovery"] = _EVENT_WEIGHTS["resource_discovery"]

    # Tech accident: any civ at INDUSTRIAL+
    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    if any(c.tech_era in industrial_plus for c in world.civilizations):
        eligible["tech_accident"] = _EVENT_WEIGHTS["tech_accident"]

    return eligible


def check_black_swans(world: WorldState, seed: int) -> list[Event]:
    """Roll for black swan event. Called after Phase 1 (Environment)."""
    if world.black_swan_cooldown > 0:
        return []

    rng = random.Random(seed + world.turn * 997)
    prob = _BLACK_SWAN_BASE_PROB * world.chaos_multiplier
    if rng.random() >= prob:
        return []

    # Roll succeeded — check eligibility
    eligible = _get_eligible_types(world)
    if not eligible:
        return []  # No eligible types, roll wasted, no cooldown set

    # Weighted selection
    types = list(eligible.keys())
    weights = [eligible[t] for t in types]
    chosen = rng.choices(types, weights=weights, k=1)[0]

    # Set cooldown
    world.black_swan_cooldown = world.black_swan_cooldown_turns

    # Dispatch to specific handler
    handlers = {
        "pandemic": _apply_pandemic_origin,
        "supervolcano": _apply_supervolcano,
        "resource_discovery": _apply_resource_discovery,
        "tech_accident": _apply_tech_accident,
    }
    return handlers[chosen](world, seed)


def _apply_pandemic_origin(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 12."""
    return []


def _apply_supervolcano(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 14."""
    return []


def _apply_resource_discovery(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 15."""
    return []


def _apply_tech_accident(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 16."""
    return []
