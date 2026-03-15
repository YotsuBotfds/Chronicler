"""Tuning override system — key constants, YAML loading, validation."""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from chronicler.models import WorldState

# --- Key constants: one per tunable parameter ---

# Stability drains
K_DROUGHT_STABILITY = "stability.drain.drought_immediate"
K_DROUGHT_ONGOING = "stability.drain.drought_ongoing"
K_PLAGUE_STABILITY = "stability.drain.plague_immediate"
K_FAMINE_STABILITY = "stability.drain.famine_immediate"
K_WAR_COST_STABILITY = "stability.drain.war_cost"
K_GOVERNING_COST = "stability.drain.governing_per_distance"
K_CONDITION_ONGOING_DRAIN = "stability.drain.condition_ongoing"

# Fertility
K_FERTILITY_DEGRADATION = "fertility.degradation_rate"
K_FERTILITY_RECOVERY = "fertility.recovery_rate"
K_FAMINE_THRESHOLD = "fertility.famine_threshold"

# Military
K_MILITARY_FREE_THRESHOLD = "military.maintenance_free_threshold"

# Emergence
K_BLACK_SWAN_BASE_PROB = "emergence.black_swan_base_probability"
K_BLACK_SWAN_COOLDOWN = "emergence.black_swan_cooldown_turns"

# Complete set of known override keys
KNOWN_OVERRIDES: set[str] = {
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY, K_GOVERNING_COST,
    K_CONDITION_ONGOING_DRAIN,
    K_FERTILITY_DEGRADATION, K_FERTILITY_RECOVERY, K_FAMINE_THRESHOLD,
    K_MILITARY_FREE_THRESHOLD, K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
}


def _flatten(d: dict, prefix: str = "") -> dict[str, float]:
    """Recursively join dict keys with '.' separator.

    Leaf values must be numeric (int or float). Raises ValueError on
    non-dict, non-numeric leaves (strings, lists, etc.).
    """
    result: dict[str, float] = {}
    for key, value in d.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten(value, full_key))
        elif isinstance(value, (int, float)):
            result[full_key] = float(value)
        else:
            raise ValueError(
                f"Tuning YAML contains non-numeric leaf at '{full_key}': "
                f"{type(value).__name__} = {value!r}"
            )
    return result


def load_tuning(path: Path) -> dict[str, float]:
    """Load hierarchical YAML, flatten to dot-notation keys, validate."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Tuning YAML must be a mapping, got {type(raw).__name__}")
    flat = _flatten(raw)
    unknown = set(flat.keys()) - KNOWN_OVERRIDES
    if unknown:
        for key in sorted(unknown):
            warnings.warn(f"Unknown tuning key: {key}")
    return flat


def get_override(world: "WorldState", key: str, default: float) -> float:
    """Read a tunable constant with override fallback."""
    return world.tuning_overrides.get(key, default)
