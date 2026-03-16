"""Coupled ecology system --- three-variable tick replacing single fertility.

Public API: tick_ecology(), effective_capacity()
No state. All functions operate on WorldState/Region passed in.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.models import ClimatePhase, Event, InfrastructureType, RegionEcology
from chronicler.tuning import (
    K_SOIL_DEGRADATION, K_SOIL_RECOVERY, K_MINE_SOIL_DEGRADATION,
    K_WATER_DROUGHT, K_WATER_RECOVERY,
    K_FOREST_CLEARING, K_FOREST_REGROWTH, K_COOLING_FOREST_DAMAGE,
    K_IRRIGATION_WATER_BONUS, K_IRRIGATION_DROUGHT_MULT,
    K_AGRICULTURE_SOIL_BONUS, K_MECHANIZATION_MINE_MULT,
    K_FAMINE_WATER_THRESHOLD,
    get_override,
)

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState

TERRAIN_ECOLOGY_DEFAULTS: dict[str, RegionEcology] = {
    "plains":    RegionEcology(soil=0.90, water=0.60, forest_cover=0.20),
    "forest":    RegionEcology(soil=0.70, water=0.70, forest_cover=0.90),
    "mountains": RegionEcology(soil=0.40, water=0.80, forest_cover=0.30),
    "coast":     RegionEcology(soil=0.70, water=0.80, forest_cover=0.30),
    "desert":    RegionEcology(soil=0.20, water=0.10, forest_cover=0.05),
    "tundra":    RegionEcology(soil=0.15, water=0.50, forest_cover=0.10),
}

TERRAIN_ECOLOGY_CAPS: dict[str, dict[str, float]] = {
    "plains":    {"soil": 0.95, "water": 0.70, "forest_cover": 0.40},
    "forest":    {"soil": 0.80, "water": 0.80, "forest_cover": 0.95},
    "mountains": {"soil": 0.50, "water": 0.90, "forest_cover": 0.40},
    "coast":     {"soil": 0.80, "water": 0.90, "forest_cover": 0.40},
    "desert":    {"soil": 0.30, "water": 0.20, "forest_cover": 0.10},
    "tundra":    {"soil": 0.20, "water": 0.60, "forest_cover": 0.15},
}

_FLOOR_SOIL = 0.05
_FLOOR_WATER = 0.10
_FLOOR_FOREST = 0.00


def effective_capacity(region: Region) -> int:
    soil = region.ecology.soil
    water_factor = min(1.0, region.ecology.water / 0.5)
    return max(int(region.carrying_capacity * soil * water_factor), 1)


def _pressure_multiplier(region: Region) -> float:
    eff = effective_capacity(region)
    if eff <= 0:
        return 1.0
    return max(0.1, 1.0 - region.population / eff)


def _tick_soil(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    eff = effective_capacity(region)

    # Degradation: overpopulation
    if region.population > eff:
        rate = get_override(world, K_SOIL_DEGRADATION, 0.005)
        region.ecology.soil -= rate

    # Degradation: active mines
    has_mine = any(
        i.type == InfrastructureType.MINES and i.active for i in region.infrastructure
    )
    if has_mine:
        mine_rate = get_override(world, K_MINE_SOIL_DEGRADATION, 0.03)
        if civ and civ.active_focus == "metallurgy":
            mine_rate *= 0.5
            world.events_timeline.append(Event(
                turn=world.turn, event_type="capability_metallurgy",
                actors=[civ.name],
                description=f"{civ.name} metallurgy reduces mine degradation",
                importance=1,
            ))
        elif civ and civ.active_focus == "mechanization":
            mine_rate *= get_override(world, K_MECHANIZATION_MINE_MULT, 2.0)
        region.ecology.soil -= mine_rate

    # Recovery: pressure-gated
    if region.population < eff * 0.75:
        rate = get_override(world, K_SOIL_RECOVERY, 0.05)
        rate *= _pressure_multiplier(region)
        if civ and civ.active_focus == "agriculture":
            rate += get_override(world, K_AGRICULTURE_SOIL_BONUS, 0.02)
        region.ecology.soil += rate


def _tick_water(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    has_irrigation = any(
        i.type == InfrastructureType.IRRIGATION and i.active for i in region.infrastructure
    )

    # Degradation / phase effects
    if climate_phase == ClimatePhase.DROUGHT:
        rate = get_override(world, K_WATER_DROUGHT, 0.04)
        if has_irrigation:
            rate *= get_override(world, K_IRRIGATION_DROUGHT_MULT, 1.5)
        region.ecology.water -= rate
    elif climate_phase == ClimatePhase.COOLING:
        region.ecology.water -= 0.02
    elif climate_phase == ClimatePhase.WARMING:
        if region.terrain == "tundra":
            region.ecology.water += 0.05

    # Recovery
    if climate_phase == ClimatePhase.TEMPERATE:
        rate = get_override(world, K_WATER_RECOVERY, 0.03)
        rate *= _pressure_multiplier(region)
        region.ecology.water += rate

    # Irrigation bonus (always, not just temperate, but not during drought)
    if has_irrigation and climate_phase != ClimatePhase.DROUGHT:
        bonus = get_override(world, K_IRRIGATION_WATER_BONUS, 0.03)
        bonus *= _pressure_multiplier(region)
        region.ecology.water += bonus


def _tick_forest(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    if region.population > region.carrying_capacity * 0.5:
        rate = get_override(world, K_FOREST_CLEARING, 0.02)
        region.ecology.forest_cover -= rate

    if climate_phase == ClimatePhase.COOLING:
        region.ecology.forest_cover -= get_override(world, K_COOLING_FOREST_DAMAGE, 0.01)

    if region.population < region.carrying_capacity * 0.5 and region.ecology.water >= 0.3:
        rate = get_override(world, K_FOREST_REGROWTH, 0.01)
        rate *= _pressure_multiplier(region)
        region.ecology.forest_cover += rate


def _apply_cross_effects(region: Region) -> None:
    if region.ecology.forest_cover > 0.5:
        region.ecology.soil += 0.01


def _clamp_ecology(region: Region) -> None:
    caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
    region.ecology.soil = max(_FLOOR_SOIL, min(caps["soil"], round(region.ecology.soil, 4)))
    region.ecology.water = max(_FLOOR_WATER, min(caps["water"], round(region.ecology.water, 4)))
    region.ecology.forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], round(region.ecology.forest_cover, 4)))


def _check_famine(world: WorldState, acc=None) -> list[Event]:
    """Region-level famine check: water < threshold."""
    from chronicler.utils import drain_region_pop, sync_civ_population, add_region_pop, clamp, STAT_FLOOR
    from chronicler.emergence import get_severity_multiplier

    events: list[Event] = []
    threshold = get_override(world, K_FAMINE_WATER_THRESHOLD, 0.20)

    for region in world.regions:
        if region.controller is None or region.famine_cooldown > 0:
            continue
        if region.ecology.water >= threshold:
            continue
        if region.population <= 0:
            continue

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        mult = get_severity_multiplier(civ)
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "population", -int(5 * mult), "guard")
        else:
            drain_region_pop(region, int(5 * mult))
            sync_civ_population(civ, world)
        drain = int(get_override(world, "stability.drain.famine_immediate", 3))
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = next((c for c in world.civilizations if c.name == adj.controller), None)
                if neighbor:
                    add_region_pop(adj, 5)
                    sync_civ_population(neighbor, world)
                    if acc is not None:
                        neighbor_idx = next(i for i, c in enumerate(world.civilizations) if c.name == neighbor.name)
                        acc.add(neighbor_idx, neighbor, "stability", -5, "signal")
                    else:
                        neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)

        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events


def _update_ecology_counters(world: WorldState) -> None:
    """Update low_forest_turns and forest_regrowth_turns for terrain succession."""
    for region in world.regions:
        if region.ecology.forest_cover < 0.2:
            region.low_forest_turns += 1
        else:
            region.low_forest_turns = 0
        if region.ecology.forest_cover > 0.7 and region.population < 5:
            region.forest_regrowth_turns += 1
        else:
            region.forest_regrowth_turns = 0


def tick_ecology(world: WorldState, climate_phase: ClimatePhase, acc=None) -> list[Event]:
    """Phase 9 ecology tick. Replaces phase_fertility."""
    for region in world.regions:
        if region.controller is None:
            continue
        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        _tick_soil(region, civ, climate_phase, world)
        _tick_water(region, civ, climate_phase, world)
        _tick_forest(region, civ, climate_phase, world)
        _apply_cross_effects(region)
        _clamp_ecology(region)

        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1

    # Uncontrolled regions: natural recovery + climate effects only (no civ bonuses)
    for region in world.regions:
        if region.controller is not None:
            continue
        # Natural soil recovery (no civ bonuses)
        eff = effective_capacity(region)
        if region.population < eff * 0.75:
            rate = get_override(world, K_SOIL_RECOVERY, 0.05)
            rate *= _pressure_multiplier(region)
            region.ecology.soil += rate
        # Water: climate effects only
        if climate_phase == ClimatePhase.DROUGHT:
            region.ecology.water -= get_override(world, K_WATER_DROUGHT, 0.04)
        elif climate_phase == ClimatePhase.COOLING:
            region.ecology.water -= 0.02
        elif climate_phase == ClimatePhase.WARMING and region.terrain == "tundra":
            region.ecology.water += 0.05
        elif climate_phase == ClimatePhase.TEMPERATE:
            rate = get_override(world, K_WATER_RECOVERY, 0.03)
            rate *= _pressure_multiplier(region)
            region.ecology.water += rate
        # Forest: natural regrowth (water gate applies)
        if region.population < region.carrying_capacity * 0.5 and region.ecology.water >= 0.3:
            rate = get_override(world, K_FOREST_REGROWTH, 0.01)
            rate *= _pressure_multiplier(region)
            region.ecology.forest_cover += rate
        if climate_phase == ClimatePhase.COOLING:
            region.ecology.forest_cover -= get_override(world, K_COOLING_FOREST_DAMAGE, 0.01)
        _apply_cross_effects(region)
        _clamp_ecology(region)

    events = _check_famine(world, acc=acc)

    from chronicler.traditions import apply_soil_floor
    apply_soil_floor(world)

    _update_ecology_counters(world)

    from chronicler.utils import sync_all_populations
    sync_all_populations(world)
    return events
