"""One named pause control for an already-enabled public-granary policy.

This is a closed whitelist, not a general tuning or world-field editor.
"""
from __future__ import annotations

from chronicler.grain_reserves import grain_reserves_enabled
from chronicler.tuning import K_GRAIN_RESERVES_SHORTFALL_PRIORITY

CONTROL = "granary_shortfall_priority"
TARGET = "@world"
STAT = K_GRAIN_RESERVES_SHORTFALL_PRIORITY


def validate_policy_command(civ: str, stat: str, value: int) -> None:
    if civ != TARGET or stat != STAT or type(value) is not int or value not in (0, 1):
        raise ValueError("Only set @world grain_reserves.shortfall_priority 0|1 is supported")


def policy_value(world) -> int:
    if getattr(world, "agent_mode", None) != "hybrid" or not grain_reserves_enabled(world):
        raise ValueError("Granary policy requires already-enabled grain reserves and hybrid mode")
    overrides = getattr(world, "tuning_overrides", None)
    if type(overrides) is not dict:
        raise ValueError("Granary policy requires a valid saved tuning map")
    value = overrides.get(STAT, 0.0)
    if type(value) not in (int, float) or value not in (0, 1):
        raise ValueError("Saved granary shortfall priority must be 0 or 1")
    return int(value)


def set_policy_value(world, civ: str, stat: str, value: int) -> None:
    validate_policy_command(civ, stat, value)
    before = policy_value(world)
    if before != value:
        world.tuning_overrides[STAT] = float(value)
    # An unchanged value preserves the exact saved representation, including
    # an omitted default, signed zero or an existing integer/float value.
