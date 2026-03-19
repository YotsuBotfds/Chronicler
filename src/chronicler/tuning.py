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
K_REBELLION_STABILITY = "stability.drain.rebellion"
K_LEADER_DEATH_STABILITY = "stability.drain.leader_death"
K_BORDER_INCIDENT_STABILITY = "stability.drain.border_incident"
K_RELIGIOUS_MOVEMENT_STABILITY = "stability.drain.religious_movement"
K_MIGRATION_STABILITY = "stability.drain.migration"
K_TWILIGHT_STABILITY = "stability.drain.twilight"

# Stability recovery
K_STABILITY_RECOVERY = "stability.recovery_per_turn"

# Ecology
K_SOIL_DEGRADATION = "ecology.soil_degradation_rate"
K_SOIL_RECOVERY = "ecology.soil_recovery_rate"
K_MINE_SOIL_DEGRADATION = "ecology.mine_soil_degradation_rate"
K_WATER_DROUGHT = "ecology.water_drought_rate"
K_WATER_RECOVERY = "ecology.water_recovery_rate"
K_FOREST_CLEARING = "ecology.forest_clearing_rate"
K_FOREST_REGROWTH = "ecology.forest_regrowth_rate"
K_COOLING_FOREST_DAMAGE = "ecology.cooling_forest_damage_rate"
K_IRRIGATION_WATER_BONUS = "ecology.irrigation_water_bonus"
K_IRRIGATION_DROUGHT_MULT = "ecology.irrigation_drought_multiplier"
K_AGRICULTURE_SOIL_BONUS = "ecology.agriculture_soil_bonus"
K_MECHANIZATION_MINE_MULT = "ecology.mechanization_mine_multiplier"
K_FAMINE_WATER_THRESHOLD = "ecology.famine_water_threshold"
K_SUBSISTENCE_BASELINE = "ecology.subsistence_baseline"
K_FAMINE_YIELD_THRESHOLD = "ecology.famine_yield_threshold"
K_PEAK_YIELD = "ecology.peak_yield"
K_DEPLETION_RATE = "ecology.depletion_rate"
# M35a: Rivers
K_RIVER_WATER_BONUS = "ecology.river_water_bonus"
K_RIVER_CAPACITY_MULTIPLIER = "ecology.river_capacity_multiplier"
K_DEFORESTATION_THRESHOLD = "ecology.deforestation_threshold"
K_DEFORESTATION_WATER_LOSS = "ecology.deforestation_water_loss"
# M35b: Disease
K_DISEASE_BASELINE_FEVER = "ecology.disease_baseline_fever"
K_DISEASE_BASELINE_CHOLERA = "ecology.disease_baseline_cholera"
K_DISEASE_BASELINE_PLAGUE = "ecology.disease_baseline_plague"
K_DISEASE_SEVERITY_CAP = "ecology.disease_severity_cap"
K_DISEASE_DECAY_RATE = "ecology.disease_decay_rate"
K_FLARE_OVERCROWDING_THRESHOLD = "ecology.flare_overcrowding_threshold"
K_FLARE_OVERCROWDING_SPIKE = "ecology.flare_overcrowding_spike"
K_FLARE_ARMY_SPIKE = "ecology.flare_army_spike"
K_FLARE_WATER_SPIKE = "ecology.flare_water_spike"
K_FLARE_SEASON_SPIKE = "ecology.flare_season_spike"
# M35b: Depletion
K_SOIL_PRESSURE_THRESHOLD = "ecology.soil_pressure_threshold"
K_SOIL_PRESSURE_STREAK_LIMIT = "ecology.soil_pressure_streak_limit"
K_OVEREXTRACTION_STREAK_LIMIT = "ecology.overextraction_streak_limit"
K_OVEREXTRACTION_YIELD_PENALTY = "ecology.overextraction_yield_penalty"
K_WORKERS_PER_YIELD_UNIT = "ecology.workers_per_yield_unit"
# M35b: Environmental events
K_LOCUST_PROBABILITY = "emergence.locust_probability"
K_FLOOD_PROBABILITY = "emergence.flood_probability"
K_COLLAPSE_PROBABILITY = "emergence.collapse_probability"
K_DROUGHT_INTENSIFICATION_PROBABILITY = "emergence.drought_intensification_probability"
K_COLLAPSE_MORTALITY_SPIKE = "emergence.collapse_mortality_spike"
K_ECOLOGICAL_RECOVERY_PROBABILITY = "emergence.ecological_recovery_probability"
K_ECOLOGICAL_RECOVERY_FRACTION = "emergence.ecological_recovery_fraction"

# Military
K_MILITARY_FREE_THRESHOLD = "military.maintenance_free_threshold"

# Emergence
K_BLACK_SWAN_BASE_PROB = "emergence.black_swan_base_probability"
K_BLACK_SWAN_COOLDOWN = "emergence.black_swan_cooldown_turns"

# Regression
K_REGRESSION_CAPITAL_COLLAPSE = "regression.capital_collapse_probability"
K_REGRESSION_TWILIGHT = "regression.entered_twilight_probability"
K_REGRESSION_BLACK_SWAN = "regression.black_swan_stressed_probability"

# --- Global simulation multipliers (Tier 1 CLI knobs) ---
# Each defaults to 1.0 (no change). Values > 1.0 amplify, < 1.0 dampen.
K_AGGRESSION_BIAS = "multiplier.aggression_bias"
K_TECH_DIFFUSION_RATE = "multiplier.tech_diffusion_rate"
K_RESOURCE_ABUNDANCE = "multiplier.resource_abundance"
K_TRADE_FRICTION = "multiplier.trade_friction"
K_SEVERITY_MULTIPLIER = "multiplier.severity"
K_CULTURAL_DRIFT_SPEED = "multiplier.cultural_drift_speed"
K_RELIGION_INTENSITY = "multiplier.religion_intensity"
K_SECESSION_LIKELIHOOD = "multiplier.secession_likelihood"

# Complete set of known override keys
KNOWN_OVERRIDES: set[str] = {
    K_DROUGHT_STABILITY, K_DROUGHT_ONGOING, K_PLAGUE_STABILITY,
    K_FAMINE_STABILITY, K_WAR_COST_STABILITY, K_GOVERNING_COST,
    K_CONDITION_ONGOING_DRAIN,
    K_REBELLION_STABILITY, K_LEADER_DEATH_STABILITY,
    K_BORDER_INCIDENT_STABILITY, K_RELIGIOUS_MOVEMENT_STABILITY,
    K_MIGRATION_STABILITY, K_TWILIGHT_STABILITY,
    K_STABILITY_RECOVERY,
    K_SOIL_DEGRADATION, K_SOIL_RECOVERY, K_MINE_SOIL_DEGRADATION,
    K_WATER_DROUGHT, K_WATER_RECOVERY,
    K_FOREST_CLEARING, K_FOREST_REGROWTH, K_COOLING_FOREST_DAMAGE,
    K_IRRIGATION_WATER_BONUS, K_IRRIGATION_DROUGHT_MULT,
    K_AGRICULTURE_SOIL_BONUS, K_MECHANIZATION_MINE_MULT, K_FAMINE_WATER_THRESHOLD,
    K_SUBSISTENCE_BASELINE, K_FAMINE_YIELD_THRESHOLD, K_PEAK_YIELD, K_DEPLETION_RATE,
    K_MILITARY_FREE_THRESHOLD, K_BLACK_SWAN_BASE_PROB, K_BLACK_SWAN_COOLDOWN,
    K_REGRESSION_CAPITAL_COLLAPSE, K_REGRESSION_TWILIGHT, K_REGRESSION_BLACK_SWAN,
    K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
    K_DISEASE_BASELINE_FEVER, K_DISEASE_BASELINE_CHOLERA, K_DISEASE_BASELINE_PLAGUE,
    K_DISEASE_SEVERITY_CAP, K_DISEASE_DECAY_RATE,
    K_FLARE_OVERCROWDING_THRESHOLD, K_FLARE_OVERCROWDING_SPIKE,
    K_FLARE_ARMY_SPIKE, K_FLARE_WATER_SPIKE, K_FLARE_SEASON_SPIKE,
    K_SOIL_PRESSURE_THRESHOLD, K_SOIL_PRESSURE_STREAK_LIMIT,
    K_OVEREXTRACTION_STREAK_LIMIT, K_OVEREXTRACTION_YIELD_PENALTY,
    K_WORKERS_PER_YIELD_UNIT,
    K_LOCUST_PROBABILITY, K_FLOOD_PROBABILITY, K_COLLAPSE_PROBABILITY,
    K_DROUGHT_INTENSIFICATION_PROBABILITY, K_COLLAPSE_MORTALITY_SPIKE,
    K_ECOLOGICAL_RECOVERY_PROBABILITY, K_ECOLOGICAL_RECOVERY_FRACTION,
    # Global simulation multipliers
    K_AGGRESSION_BIAS, K_TECH_DIFFUSION_RATE, K_RESOURCE_ABUNDANCE,
    K_TRADE_FRICTION, K_SEVERITY_MULTIPLIER, K_CULTURAL_DRIFT_SPEED,
    K_RELIGION_INTENSITY, K_SECESSION_LIKELIHOOD,
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
    for key, value in flat.items():
        if key.startswith("multiplier.") and value <= 0:
            raise ValueError(
                f"Multiplier '{key}' must be > 0, got {value}"
            )
    return flat


def get_override(world: "WorldState", key: str, default: float) -> float:
    """Read a tunable constant with override fallback."""
    return world.tuning_overrides.get(key, default)


def get_multiplier(world: "WorldState", key: str) -> float:
    """Read a global simulation multiplier (defaults to 1.0)."""
    return world.tuning_overrides.get(key, 1.0)


# --- Presets: compound parameter bundles ---
PRESETS: dict[str, dict[str, float]] = {
    "pangaea": {
        K_TRADE_FRICTION: 0.5,
        K_AGGRESSION_BIAS: 1.3,
    },
    "archipelago": {
        K_TRADE_FRICTION: 1.8,
        K_TECH_DIFFUSION_RATE: 0.6,
    },
    "golden-age": {
        K_RESOURCE_ABUNDANCE: 2.0,
        K_AGGRESSION_BIAS: 0.5,
        K_TECH_DIFFUSION_RATE: 2.0,
        K_SEVERITY_MULTIPLIER: 0.6,
    },
    "dark-age": {
        K_SEVERITY_MULTIPLIER: 1.8,
        K_SECESSION_LIKELIHOOD: 1.8,
        K_RESOURCE_ABUNDANCE: 0.7,
    },
    "ice-age": {
        K_SEVERITY_MULTIPLIER: 1.5,
        K_RESOURCE_ABUNDANCE: 0.6,
    },
    "silk-road": {
        K_TRADE_FRICTION: 0.4,
        K_CULTURAL_DRIFT_SPEED: 2.0,
        K_TECH_DIFFUSION_RATE: 1.5,
    },
}


def apply_preset(overrides: dict[str, float], preset_name: str) -> None:
    """Merge preset values into overrides dict (preset values don't override explicit values)."""
    preset = PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"Unknown preset: {preset_name}. Available: {', '.join(sorted(PRESETS))}")
    for key, value in preset.items():
        if key not in overrides:
            overrides[key] = value
