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
