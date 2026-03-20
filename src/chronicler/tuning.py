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
K_REGRESSION_CULTURE_RESISTANCE_FLOOR = "regression.culture_resistance_floor"
K_REGRESSION_CULTURE_RESISTANCE_DIVISOR = "regression.culture_resistance_divisor"

# Ecology — additional thresholds
K_COOLING_WATER_LOSS = "ecology.cooling_water_loss"
K_WARMING_TUNDRA_WATER_GAIN = "ecology.warming_tundra_water_gain"
K_WATER_FACTOR_DENOMINATOR = "ecology.water_factor_denominator"
K_SOIL_RECOVERY_POP_RATIO = "ecology.soil_recovery_pop_ratio"
K_FOREST_POP_RATIO = "ecology.forest_pop_ratio"
K_FOREST_REGROWTH_WATER_GATE = "ecology.forest_regrowth_water_gate"
K_CROSS_EFFECT_FOREST_SOIL = "ecology.cross_effect_forest_soil_bonus"
K_CROSS_EFFECT_FOREST_THRESHOLD = "ecology.cross_effect_forest_threshold"
K_EXHAUSTED_TRICKLE_FRACTION = "ecology.exhausted_trickle_fraction"
K_RESERVE_RAMP_THRESHOLD = "ecology.reserve_ramp_threshold"
K_METALLURGY_MINE_REDUCTION = "ecology.metallurgy_mine_reduction"
K_SOIL_PRESSURE_DEGRADATION_MULT = "ecology.soil_pressure_degradation_multiplier"
K_FAMINE_POP_LOSS = "ecology.famine_pop_loss"
K_FAMINE_REFUGEE_POP = "ecology.famine_refugee_pop"

# Politics
K_SECESSION_STABILITY_THRESHOLD = "politics.secession_stability_threshold"
K_SECESSION_SURVEILLANCE_THRESHOLD = "politics.secession_surveillance_threshold"
K_PROXY_WAR_SECESSION_BONUS = "politics.proxy_war_secession_bonus"
K_BALANCE_OF_POWER_DOMINANCE = "politics.balance_of_power_dominance_threshold"
K_BALANCE_OF_POWER_PERIOD = "politics.balance_of_power_period"
K_VASSAL_TRIBUTE_RATE = "politics.vassal_tribute_rate"
K_FEDERATION_ALLIED_TURNS = "politics.federation_allied_turns"
K_CONGRESS_PROBABILITY = "politics.congress_probability"
K_CAPITAL_LOSS_STABILITY = "politics.capital_loss_stability_drain"
K_FEDERATION_EXIT_STABILITY = "politics.federation_exit_stability_drain"
K_FEDERATION_REMAINING_STABILITY = "politics.federation_remaining_stability_drain"
K_EXILE_DURATION = "politics.exile_duration"
K_VASSAL_REBELLION_BASE_PROB = "politics.vassal_rebellion_base_probability"
K_VASSAL_REBELLION_REDUCED_PROB = "politics.vassal_rebellion_reduced_probability"
K_RESTORATION_BASE_PROB = "politics.restoration_base_probability"
K_RESTORATION_RECOGNITION_BONUS = "politics.restoration_recognition_bonus"
K_TWILIGHT_DECLINE_TURNS = "politics.twilight_decline_turns"
K_TWILIGHT_ABSORPTION_DECLINE = "politics.twilight_absorption_decline_turns"
K_TWILIGHT_POP_DRAIN = "politics.twilight_pop_drain"
K_TWILIGHT_CULTURE_DRAIN = "politics.twilight_culture_drain"
K_FALLEN_EMPIRE_PEAK_REGIONS = "politics.fallen_empire_peak_regions"
K_FALLEN_EMPIRE_ASABIYA_BOOST = "politics.fallen_empire_asabiya_boost"
K_MOVE_CAPITAL_COST = "politics.move_capital_cost"
K_PROXY_WAR_STABILITY_DRAIN = "politics.proxy_war_stability_drain"
K_PROXY_WAR_ECONOMY_DRAIN = "politics.proxy_war_economy_drain"
K_SECESSION_STABILITY_LOSS = "politics.secession_stability_loss"

# Culture
K_ASSIMILATION_THRESHOLD = "culture.assimilation_threshold"
K_ASSIMILATION_STABILITY_DRAIN = "culture.assimilation_stability_drain"
K_RECONQUEST_COOLDOWN = "culture.reconquest_cooldown"
K_ASSIMILATION_AGENT_THRESHOLD = "culture.assimilation_agent_threshold"
K_ASSIMILATION_GUARD_TURNS = "culture.assimilation_guard_turns"
K_PROPAGANDA_COST = "culture.propaganda_cost"
K_PROPAGANDA_ACCELERATION = "culture.propaganda_acceleration"
K_COUNTER_PROPAGANDA_COST = "culture.counter_propaganda_cost"
K_CULTURE_PROJECTION_THRESHOLD = "culture.culture_projection_threshold"
K_PRESTIGE_DECAY = "culture.prestige_decay_per_turn"
K_PRESTIGE_TRADE_DIVISOR = "culture.prestige_trade_bonus_divisor"

# Infrastructure
K_TEMPLE_BUILD_COST = "infrastructure.temple_build_cost"
K_TEMPLE_BUILD_TURNS = "infrastructure.temple_build_turns"
K_MAX_TEMPLES_PER_REGION = "infrastructure.max_temples_per_region"
K_MAX_TEMPLES_PER_CIV = "infrastructure.max_temples_per_civ"
K_TEMPLE_CONVERSION_BOOST = "infrastructure.temple_conversion_boost"
K_TEMPLE_PRESTIGE_PER_TURN = "infrastructure.temple_prestige_per_turn"
K_CIV_PRESTIGE_PER_TEMPLE = "infrastructure.civ_prestige_per_temple"
K_SCORCHED_EARTH_TRAIT_BONUS = "infrastructure.scorched_earth_trait_bonus"

# Climate
K_DISASTER_COOLDOWN = "climate.disaster_cooldown"
K_EARTHQUAKE_SOIL_LOSS = "climate.earthquake_soil_loss"
K_FLOOD_WATER_GAIN = "climate.flood_water_gain"
K_WILDFIRE_FOREST_LOSS = "climate.wildfire_forest_loss"
K_WILDFIRE_SUSPENSION_TURNS = "climate.wildfire_suspension_turns"
K_SANDSTORM_SUSPENSION_TURNS = "climate.sandstorm_suspension_turns"
K_MIGRATION_CAPACITY_RATIO = "climate.migration_capacity_ratio"

# Emergence — additional thresholds
K_SEVERITY_STRESS_DIVISOR = "emergence.severity_stress_divisor"
K_SEVERITY_STRESS_SCALE = "emergence.severity_stress_scale"
K_SEVERITY_CAP = "emergence.severity_cap"
K_STRESS_WAR_WEIGHT = "emergence.stress_war_weight"
K_STRESS_FAMINE_WEIGHT = "emergence.stress_famine_weight"
K_STRESS_SECESSION_RISK = "emergence.stress_secession_risk"
K_STRESS_PANDEMIC_WEIGHT = "emergence.stress_pandemic_weight"
K_STRESS_TWILIGHT_WEIGHT = "emergence.stress_twilight_weight"
K_STRESS_OVEREXTENSION_THRESHOLD = "emergence.stress_overextension_threshold"
K_VOLCANO_POP_DRAIN = "emergence.volcano_pop_drain"
K_VOLCANO_STABILITY_DRAIN = "emergence.volcano_stability_drain"
K_VOLCANIC_WINTER_DURATION = "emergence.volcanic_winter_duration"
K_PANDEMIC_LEADER_KILL_PROB = "emergence.pandemic_leader_kill_probability"
K_TECH_ACCIDENT_SOIL_LOSS = "emergence.tech_accident_soil_loss"
K_TECH_ACCIDENT_NEIGHBOR_SOIL_LOSS = "emergence.tech_accident_neighbor_soil_loss"

# Action Engine
K_DEVELOP_COST_BASE = "action.develop_cost_base"
K_DEVELOP_COST_SCALE = "action.develop_cost_economy_divisor"
K_DEVELOP_GAIN = "action.develop_gain"
K_EXPAND_MILITARY_THRESHOLD = "action.expand_military_threshold"
K_EXPAND_MILITARY_COST = "action.expand_military_cost"
K_WAR_ATTACKER_TREASURY_COST = "action.war_attacker_treasury_cost"
K_WAR_DEFENDER_TREASURY_COST = "action.war_defender_treasury_cost"
K_WAR_DECISIVE_RATIO = "action.war_decisive_ratio"
K_WAR_WINNER_MILITARY_LOSS = "action.war_winner_military_loss"
K_WAR_LOSER_MILITARY_LOSS = "action.war_loser_military_loss"
K_WAR_STALEMATE_MILITARY_LOSS = "action.war_stalemate_military_loss"
K_WAR_STABILITY_LOSS = "action.war_stability_loss"
K_EMBARGO_STABILITY_DAMAGE = "action.embargo_stability_damage"
K_EMBARGO_BANKING_DAMAGE = "action.embargo_banking_damage"
K_FORT_DEFENSE_BONUS = "action.fort_defense_bonus"
K_MARTIAL_TRADITION_BONUS = "action.martial_tradition_bonus"
K_NAVAL_POWER_BONUS = "action.naval_power_defense_bonus"
K_WEIGHT_CAP = "action.weight_cap"
K_STREAK_LIMIT = "action.streak_limit"
K_STUBBORN_STREAK_LIMIT = "action.stubborn_streak_limit"
K_POWER_STRUGGLE_FACTOR = "action.power_struggle_factor"
K_SECONDARY_TRAIT_BOOST = "action.secondary_trait_boost"
K_RIVAL_WAR_BOOST = "action.rival_war_boost"
K_MOVE_CAPITAL_TREASURY_REQ = "action.move_capital_treasury_requirement"
K_FUND_INSTABILITY_TREASURY_REQ = "action.fund_instability_treasury_requirement"
K_INVEST_CULTURE_THRESHOLD = "action.invest_culture_culture_threshold"

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
    K_REGRESSION_CULTURE_RESISTANCE_FLOOR, K_REGRESSION_CULTURE_RESISTANCE_DIVISOR,
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
    # Ecology — additional thresholds
    K_COOLING_WATER_LOSS, K_WARMING_TUNDRA_WATER_GAIN,
    K_WATER_FACTOR_DENOMINATOR, K_SOIL_RECOVERY_POP_RATIO,
    K_FOREST_POP_RATIO, K_FOREST_REGROWTH_WATER_GATE,
    K_CROSS_EFFECT_FOREST_SOIL, K_CROSS_EFFECT_FOREST_THRESHOLD,
    K_EXHAUSTED_TRICKLE_FRACTION, K_RESERVE_RAMP_THRESHOLD,
    K_METALLURGY_MINE_REDUCTION, K_SOIL_PRESSURE_DEGRADATION_MULT,
    K_FAMINE_POP_LOSS, K_FAMINE_REFUGEE_POP,
    # Politics
    K_SECESSION_STABILITY_THRESHOLD, K_SECESSION_SURVEILLANCE_THRESHOLD,
    K_PROXY_WAR_SECESSION_BONUS, K_BALANCE_OF_POWER_DOMINANCE,
    K_BALANCE_OF_POWER_PERIOD, K_VASSAL_TRIBUTE_RATE,
    K_FEDERATION_ALLIED_TURNS, K_CONGRESS_PROBABILITY,
    K_CAPITAL_LOSS_STABILITY, K_FEDERATION_EXIT_STABILITY,
    K_FEDERATION_REMAINING_STABILITY,
    K_EXILE_DURATION, K_VASSAL_REBELLION_BASE_PROB,
    K_VASSAL_REBELLION_REDUCED_PROB,
    K_RESTORATION_BASE_PROB, K_RESTORATION_RECOGNITION_BONUS,
    K_TWILIGHT_DECLINE_TURNS, K_TWILIGHT_ABSORPTION_DECLINE,
    K_TWILIGHT_POP_DRAIN, K_TWILIGHT_CULTURE_DRAIN,
    K_FALLEN_EMPIRE_PEAK_REGIONS, K_FALLEN_EMPIRE_ASABIYA_BOOST,
    K_MOVE_CAPITAL_COST, K_PROXY_WAR_STABILITY_DRAIN,
    K_PROXY_WAR_ECONOMY_DRAIN, K_SECESSION_STABILITY_LOSS,
    # Culture
    K_ASSIMILATION_THRESHOLD, K_ASSIMILATION_STABILITY_DRAIN,
    K_RECONQUEST_COOLDOWN, K_ASSIMILATION_AGENT_THRESHOLD,
    K_ASSIMILATION_GUARD_TURNS, K_PROPAGANDA_COST,
    K_PROPAGANDA_ACCELERATION, K_COUNTER_PROPAGANDA_COST,
    K_CULTURE_PROJECTION_THRESHOLD, K_PRESTIGE_DECAY, K_PRESTIGE_TRADE_DIVISOR,
    # Infrastructure
    K_TEMPLE_BUILD_COST, K_TEMPLE_BUILD_TURNS,
    K_MAX_TEMPLES_PER_REGION, K_MAX_TEMPLES_PER_CIV,
    K_TEMPLE_CONVERSION_BOOST, K_TEMPLE_PRESTIGE_PER_TURN,
    K_CIV_PRESTIGE_PER_TEMPLE, K_SCORCHED_EARTH_TRAIT_BONUS,
    # Climate
    K_DISASTER_COOLDOWN, K_EARTHQUAKE_SOIL_LOSS,
    K_FLOOD_WATER_GAIN, K_WILDFIRE_FOREST_LOSS,
    K_WILDFIRE_SUSPENSION_TURNS, K_SANDSTORM_SUSPENSION_TURNS,
    K_MIGRATION_CAPACITY_RATIO,
    # Emergence — additional
    K_SEVERITY_STRESS_DIVISOR, K_SEVERITY_STRESS_SCALE, K_SEVERITY_CAP,
    K_STRESS_WAR_WEIGHT, K_STRESS_FAMINE_WEIGHT, K_STRESS_SECESSION_RISK,
    K_STRESS_PANDEMIC_WEIGHT, K_STRESS_TWILIGHT_WEIGHT,
    K_STRESS_OVEREXTENSION_THRESHOLD,
    K_VOLCANO_POP_DRAIN, K_VOLCANO_STABILITY_DRAIN, K_VOLCANIC_WINTER_DURATION,
    K_PANDEMIC_LEADER_KILL_PROB,
    K_TECH_ACCIDENT_SOIL_LOSS, K_TECH_ACCIDENT_NEIGHBOR_SOIL_LOSS,
    # Action Engine
    K_DEVELOP_COST_BASE, K_DEVELOP_COST_SCALE, K_DEVELOP_GAIN,
    K_EXPAND_MILITARY_THRESHOLD, K_EXPAND_MILITARY_COST,
    K_WAR_ATTACKER_TREASURY_COST, K_WAR_DEFENDER_TREASURY_COST,
    K_WAR_DECISIVE_RATIO, K_WAR_WINNER_MILITARY_LOSS,
    K_WAR_LOSER_MILITARY_LOSS, K_WAR_STALEMATE_MILITARY_LOSS,
    K_WAR_STABILITY_LOSS, K_EMBARGO_STABILITY_DAMAGE,
    K_EMBARGO_BANKING_DAMAGE, K_FORT_DEFENSE_BONUS,
    K_MARTIAL_TRADITION_BONUS, K_NAVAL_POWER_BONUS,
    K_WEIGHT_CAP, K_STREAK_LIMIT, K_STUBBORN_STREAK_LIMIT,
    K_POWER_STRUGGLE_FACTOR, K_SECONDARY_TRAIT_BOOST,
    K_RIVAL_WAR_BOOST, K_MOVE_CAPITAL_TREASURY_REQ,
    K_FUND_INSTABILITY_TREASURY_REQ, K_INVEST_CULTURE_THRESHOLD,
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
