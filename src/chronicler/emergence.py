"""M18 Emergence and Chaos — black swans, stress, regression, ecological succession.

All cross-system emergence logic centralized in one module. Called from
existing turn phases via distributed hooks in simulation.py.
"""
from __future__ import annotations

from chronicler.models import Civilization, WorldState
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
