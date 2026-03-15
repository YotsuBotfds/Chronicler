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
