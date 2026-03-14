"""Terrain mechanical effects — pure functions on Region properties.

No state. No side effects. Other modules import and call these.
Unknown terrain types fall through to plains defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Region


@dataclass(frozen=True)
class TerrainEffect:
    defense: int
    fertility_cap: float
    trade_mod: int


TERRAIN_EFFECTS: dict[str, TerrainEffect] = {
    "plains":    TerrainEffect(defense=0,  fertility_cap=0.9, trade_mod=0),
    "forest":    TerrainEffect(defense=10, fertility_cap=0.7, trade_mod=0),
    "mountains": TerrainEffect(defense=20, fertility_cap=0.6, trade_mod=0),
    "coast":     TerrainEffect(defense=0,  fertility_cap=0.8, trade_mod=2),
    "desert":    TerrainEffect(defense=5,  fertility_cap=0.3, trade_mod=0),
    "tundra":    TerrainEffect(defense=10, fertility_cap=0.2, trade_mod=0),
}

_DEFAULT = TERRAIN_EFFECTS["plains"]

ROLE_EFFECTS: dict[str, TerrainEffect] = {
    "standard":   TerrainEffect(defense=0,  fertility_cap=1.0, trade_mod=0),
    "crossroads": TerrainEffect(defense=-5, fertility_cap=1.0, trade_mod=3),
    "frontier":   TerrainEffect(defense=10, fertility_cap=1.0, trade_mod=-2),
    "chokepoint": TerrainEffect(defense=0,  fertility_cap=1.0, trade_mod=5),
}

_DEFAULT_ROLE = ROLE_EFFECTS["standard"]


def _get_effect(region: Region) -> TerrainEffect:
    return TERRAIN_EFFECTS.get(region.terrain, _DEFAULT)


def terrain_defense_bonus(region: Region) -> int:
    """Military defense modifier for combat in this region."""
    return _get_effect(region).defense


def terrain_fertility_cap(region: Region) -> float:
    """Maximum fertility for this terrain type. Hard ceiling."""
    return _get_effect(region).fertility_cap


def terrain_trade_modifier(region: Region) -> int:
    """Additional trade income for routes through this region."""
    return _get_effect(region).trade_mod


def total_defense_bonus(region: Region) -> int:
    """Terrain + role defense combined."""
    terrain = terrain_defense_bonus(region)
    role = ROLE_EFFECTS.get(region.role, _DEFAULT_ROLE).defense
    return terrain + role


def total_trade_modifier(region: Region) -> int:
    """Terrain + role trade modifier combined."""
    terrain = terrain_trade_modifier(region)
    role = ROLE_EFFECTS.get(region.role, _DEFAULT_ROLE).trade_mod
    return terrain + role


def effective_capacity(region: Region) -> int:
    """Single source of truth for region carrying capacity.

    max(int(carrying_capacity * min(fertility, terrain_fertility_cap)), 1).
    Floor of 1 prevents division-by-zero in famine/migration calculations.
    """
    cap = terrain_fertility_cap(region)
    return max(int(region.carrying_capacity * min(region.fertility, cap)), 1)
