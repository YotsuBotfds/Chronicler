"""Legacy ecology oracle — pre-M54a pure-Python formulas for parity tests.

This file is TEST-ONLY scaffolding. No production code should import from it.
It preserves the old Python ecology formulas so that parity tests can compare
the Rust ecology path against the legacy Python path on identical inputs.

These formulas are copied from src/chronicler/ecology.py as of pre-M54a,
stripped of production imports and WorldState references. All tuning constants
are inlined at their default values.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Terrain tables (frozen copies)
# ---------------------------------------------------------------------------

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

# Resource classification (frozen copies from resources.py)
# ResourceType enum values: GRAIN=0, TIMBER=1, BOTANICALS=2, FISH=3,
#                            SALT=4, ORE=5, PRECIOUS=6, EXOTIC=7
EMPTY_SLOT = 255
FOOD_TYPES = frozenset({0, 2, 3, 4})  # GRAIN, BOTANICALS, FISH, SALT
MINERAL_TYPES = frozenset({5, 6})  # ORE, PRECIOUS
DEPLETABLE = frozenset({0, 2, 3, 5, 6})  # GRAIN, BOTANICALS, FISH, ORE, PRECIOUS

# Season modifiers: SEASON_MOD[resource_type_id][season_id]
SEASON_MOD: list[list[float]] = [
    [0.8, 1.2, 1.5, 0.3],  # GRAIN
    [0.6, 1.0, 1.2, 0.8],  # TIMBER
    [1.2, 0.8, 0.6, 0.2],  # BOTANICALS
    [1.0, 1.0, 0.8, 0.6],  # FISH
    [0.8, 1.2, 1.0, 1.0],  # SALT
    [0.9, 1.0, 1.0, 0.9],  # ORE
    [0.9, 1.0, 1.0, 1.0],  # PRECIOUS
    [1.0, 0.8, 1.2, 0.6],  # EXOTIC
]

# Climate class modifiers: CLIMATE_CLASS_MOD[class_index][climate_phase_index]
CLIMATE_CLASS_MOD: list[list[float]] = [
    [1.0, 0.9, 0.5, 0.7],  # Crop
    [1.0, 0.9, 0.7, 0.8],  # Forestry
    [1.0, 1.0, 0.8, 0.9],  # Marine
    [1.0, 1.0, 1.0, 1.0],  # Mineral
    [1.0, 1.1, 1.2, 0.9],  # Evaporite
]

# Climate phase -> index mapping
CLIMATE_PHASE_INDEX = {"temperate": 0, "warming": 1, "drought": 2, "cooling": 3}


def resource_class_index(rtype: int) -> int:
    """Map ResourceType int to mechanical class index."""
    if rtype in (0, 2, 7):  # GRAIN, BOTANICALS, EXOTIC
        return 0  # Crop
    elif rtype == 1:  # TIMBER
        return 1  # Forestry
    elif rtype == 3:  # FISH
        return 2  # Marine
    elif rtype in (5, 6):  # ORE, PRECIOUS
        return 3  # Mineral
    elif rtype == 4:  # SALT
        return 4  # Evaporite
    return 0


# ---------------------------------------------------------------------------
# Default tuning constants (inlined)
# ---------------------------------------------------------------------------

SOIL_DEGRADATION = 0.005
SOIL_RECOVERY = 0.05
MINE_SOIL_DEGRADATION = 0.03
SOIL_RECOVERY_POP_RATIO = 0.75
AGRICULTURE_SOIL_BONUS = 0.02
METALLURGY_MINE_REDUCTION = 0.5
MECHANIZATION_MINE_MULT = 2.0
SOIL_PRESSURE_THRESHOLD = 0.7
SOIL_PRESSURE_STREAK_LIMIT = 30
SOIL_PRESSURE_DEGRADATION_MULT = 2.0

WATER_DROUGHT = 0.04
WATER_RECOVERY = 0.03
IRRIGATION_WATER_BONUS = 0.03
IRRIGATION_DROUGHT_MULT = 1.5
COOLING_WATER_LOSS = 0.02
WARMING_TUNDRA_WATER_GAIN = 0.05
WATER_FACTOR_DENOMINATOR = 0.5

FOREST_CLEARING = 0.02
FOREST_REGROWTH = 0.01
COOLING_FOREST_DAMAGE = 0.01
FOREST_POP_RATIO = 0.5
FOREST_REGROWTH_WATER_GATE = 0.3

CROSS_EFFECT_FOREST_SOIL = 0.01
CROSS_EFFECT_FOREST_THRESHOLD = 0.5

DISEASE_SEVERITY_CAP = 0.15
DISEASE_DECAY_RATE = 0.25
FLARE_OVERCROWDING_THRESHOLD = 0.8
FLARE_OVERCROWDING_SPIKE = 0.04
FLARE_ARMY_SPIKE = 0.03
FLARE_WATER_SPIKE = 0.02
FLARE_SEASON_SPIKE = 0.02

DEPLETION_RATE = 0.009
EXHAUSTED_TRICKLE_FRACTION = 0.04
RESERVE_RAMP_THRESHOLD = 0.25
RESOURCE_ABUNDANCE = 1.0

OVEREXTRACTION_STREAK_LIMIT = 35
OVEREXTRACTION_YIELD_PENALTY = 0.10
WORKERS_PER_YIELD_UNIT = 200

DEFORESTATION_THRESHOLD = 0.2
DEFORESTATION_WATER_LOSS = 0.05


# ---------------------------------------------------------------------------
# Core formulas
# ---------------------------------------------------------------------------


def effective_capacity(
    carrying_capacity: int,
    soil: float,
    water: float,
    capacity_modifier: float = 1.0,
) -> int:
    """Compute effective capacity from ecology state."""
    water_factor = min(1.0, water / WATER_FACTOR_DENOMINATOR)
    return max(int(carrying_capacity * capacity_modifier * soil * water_factor), 1)


def pressure_multiplier(
    population: int,
    carrying_capacity: int,
    soil: float,
    water: float,
    capacity_modifier: float = 1.0,
) -> float:
    """Compute pressure multiplier for recovery gating."""
    eff = effective_capacity(carrying_capacity, soil, water, capacity_modifier)
    if eff <= 0:
        return 1.0
    return max(0.1, 1.0 - population / eff)


def tick_soil(
    soil: float,
    population: int,
    carrying_capacity: int,
    water: float,
    capacity_modifier: float,
    climate_phase: str,
    has_mine: bool = False,
    active_focus: str | None = None,
    degradation_mult: float = 1.0,
) -> float:
    """Apply one tick of soil dynamics. Returns new soil value."""
    eff = effective_capacity(carrying_capacity, soil, water, capacity_modifier)

    # Degradation: overpopulation
    if population > eff:
        soil -= SOIL_DEGRADATION * degradation_mult

    # Degradation: active mines
    if has_mine:
        mine_rate = MINE_SOIL_DEGRADATION
        if active_focus == "metallurgy":
            mine_rate *= METALLURGY_MINE_REDUCTION
        elif active_focus == "mechanization":
            mine_rate *= MECHANIZATION_MINE_MULT
        soil -= mine_rate

    # Recovery: pressure-gated
    if population < eff * SOIL_RECOVERY_POP_RATIO:
        rate = SOIL_RECOVERY
        pm = pressure_multiplier(population, carrying_capacity, soil, water, capacity_modifier)
        rate *= pm
        if active_focus == "agriculture":
            rate += AGRICULTURE_SOIL_BONUS
        soil += rate

    return soil


def tick_water(
    water: float,
    population: int,
    carrying_capacity: int,
    soil: float,
    capacity_modifier: float,
    climate_phase: str,
    terrain: str,
    has_irrigation: bool = False,
) -> float:
    """Apply one tick of water dynamics. Returns new water value."""
    # Degradation / phase effects
    if climate_phase == "drought":
        rate = WATER_DROUGHT
        if has_irrigation:
            rate *= IRRIGATION_DROUGHT_MULT
        water -= rate
    elif climate_phase == "cooling":
        water -= COOLING_WATER_LOSS
    elif climate_phase == "warming":
        if terrain == "tundra":
            water += WARMING_TUNDRA_WATER_GAIN

    # Recovery
    if climate_phase == "temperate":
        rate = WATER_RECOVERY
        pm = pressure_multiplier(population, carrying_capacity, soil, water, capacity_modifier)
        rate *= pm
        water += rate

    # Irrigation bonus (always, not just temperate, but not during drought)
    if has_irrigation and climate_phase != "drought":
        bonus = IRRIGATION_WATER_BONUS
        pm = pressure_multiplier(population, carrying_capacity, soil, water, capacity_modifier)
        bonus *= pm
        water += bonus

    return water


def tick_forest(
    forest_cover: float,
    population: int,
    carrying_capacity: int,
    soil: float,
    water: float,
    capacity_modifier: float,
    climate_phase: str,
) -> float:
    """Apply one tick of forest dynamics. Returns new forest_cover value."""
    if population > carrying_capacity * FOREST_POP_RATIO:
        forest_cover -= FOREST_CLEARING

    if climate_phase == "cooling":
        forest_cover -= COOLING_FOREST_DAMAGE

    if (population < carrying_capacity * FOREST_POP_RATIO
            and water >= FOREST_REGROWTH_WATER_GATE):
        rate = FOREST_REGROWTH
        pm = pressure_multiplier(population, carrying_capacity, soil, water, capacity_modifier)
        rate *= pm
        forest_cover += rate

    return forest_cover


def apply_cross_effects(soil: float, forest_cover: float) -> float:
    """Forest -> soil bonus. Returns new soil value."""
    if forest_cover > CROSS_EFFECT_FOREST_THRESHOLD:
        soil += CROSS_EFFECT_FOREST_SOIL
    return soil


def clamp_ecology(
    terrain: str,
    soil: float,
    water: float,
    forest_cover: float,
) -> tuple[float, float, float]:
    """Clamp ecology values to terrain caps/floors with round-to-4."""
    caps = TERRAIN_ECOLOGY_CAPS.get(terrain, TERRAIN_ECOLOGY_CAPS["plains"])
    soil = max(_FLOOR_SOIL, min(caps["soil"], round(soil, 4)))
    water = max(_FLOOR_WATER, min(caps["water"], round(water, 4)))
    forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], round(forest_cover, 4)))
    return soil, water, forest_cover


def compute_disease_severity(
    endemic_severity: float,
    disease_baseline: float,
    population: int,
    carrying_capacity: int,
    terrain: str,
    pre_water: float,
    prev_turn_water: float,
    season_id: int = 0,
    army_arrived: bool = False,
    pandemic_active: bool = False,
) -> float:
    """Compute new endemic_severity. Returns the updated value."""
    cap = DISEASE_SEVERITY_CAP
    severity = endemic_severity
    triggered = False

    # Overcrowding
    if carrying_capacity > 0 and population > FLARE_OVERCROWDING_THRESHOLD * carrying_capacity:
        severity += FLARE_OVERCROWDING_SPIKE
        triggered = True

    # Army passage
    if army_arrived:
        severity += FLARE_ARMY_SPIKE
        triggered = True

    # Water quality: low water on non-desert terrain
    if terrain != "desert" and pre_water < 0.3:
        severity += FLARE_WATER_SPIKE
        triggered = True

    # Water quality: inter-turn water drop > 0.1
    if terrain != "desert" and prev_turn_water >= 0:
        water_delta = prev_turn_water - pre_water
        if water_delta > 0.1 and not (pre_water < 0.3):  # Don't double-count
            severity += FLARE_WATER_SPIKE
            triggered = True

    # Seasonal peak
    is_fever = disease_baseline >= 0.02
    is_cholera = terrain == "desert"
    if is_fever and not is_cholera and season_id == 1:  # Summer for Fever
        severity += FLARE_SEASON_SPIKE
        triggered = True
    elif not is_fever and not is_cholera and disease_baseline <= 0.01 and season_id == 3:
        severity += FLARE_SEASON_SPIKE
        triggered = True

    # Pandemic suppression
    if pandemic_active:
        severity = endemic_severity  # Reset to pre-trigger value
        triggered = False

    if triggered:
        severity = min(severity, cap)
    else:
        severity -= DISEASE_DECAY_RATE * (endemic_severity - disease_baseline)

    # Floor at baseline
    if severity < disease_baseline:
        severity = disease_baseline

    return severity


def compute_resource_yields(
    resource_types: list[int],
    resource_base_yields: list[float],
    resource_reserves: list[float],
    resource_suspensions: dict,
    soil: float,
    water: float,
    forest_cover: float,
    carrying_capacity: int,
    capacity_modifier: float,
    population: int,
    season_id: int,
    climate_phase: str,
    worker_count: int,
) -> tuple[list[float], list[float]]:
    """Compute current yields per resource slot.

    Returns (yields, updated_reserves). Mirrors legacy compute_resource_yields.
    Does NOT mutate inputs — returns new reserves list.
    """
    phase_idx = CLIMATE_PHASE_INDEX.get(climate_phase, 0)
    yields = [0.0, 0.0, 0.0]
    reserves = list(resource_reserves)

    eff = effective_capacity(carrying_capacity, soil, water, capacity_modifier)

    for slot in range(3):
        rtype = resource_types[slot]
        if rtype == EMPTY_SLOT:
            continue

        # Suspension check
        if rtype in resource_suspensions:
            continue

        base = resource_base_yields[slot]
        season_mod = SEASON_MOD[rtype][season_id]
        class_idx = resource_class_index(rtype)
        climate_mod = CLIMATE_CLASS_MOD[class_idx][phase_idx]

        # ecology_mod by class
        if class_idx == 0:  # Crop
            ecology_mod = soil * water
        elif class_idx == 1:  # Forestry
            ecology_mod = forest_cover
        else:  # Marine, Mineral, Evaporite
            ecology_mod = 1.0

        # reserve_ramp (minerals only)
        reserve_ramp = 1.0
        if rtype in MINERAL_TYPES:
            r = reserves[slot]
            if r > 0.01 and worker_count > 0:
                target_workers = max(1, eff // 3)
                extraction = base * (worker_count / target_workers)
                reserves[slot] = max(0.0, r - extraction * DEPLETION_RATE)
            r = reserves[slot]
            if r < 0.01:
                yields[slot] = base * EXHAUSTED_TRICKLE_FRACTION
                continue
            reserve_ramp = min(1.0, r / RESERVE_RAMP_THRESHOLD)

        yields[slot] = base * season_mod * climate_mod * ecology_mod * reserve_ramp * RESOURCE_ABUNDANCE

    return yields, reserves


def update_depletion_feedback(
    resource_types: list[int],
    resource_effective_yields: list[float],
    population: int,
    carrying_capacity: int,
    soil_pressure_streak: int,
    overextraction_streaks: dict[int, int],
) -> tuple[int, dict[int, int], list[float], list[str]]:
    """Update soil pressure and overextraction streaks.

    Returns (new_soil_pressure_streak, new_overextraction_streaks,
             new_effective_yields, event_types).
    """
    events: list[str] = []
    eff_yields = list(resource_effective_yields)
    over_streaks = dict(overextraction_streaks)

    # Soil exhaustion (population pressure)
    has_crop = any(
        rtype in (0, 2)  # GRAIN, BOTANICALS
        for rtype in resource_types
        if rtype != EMPTY_SLOT
    )
    if (has_crop and carrying_capacity > 0
            and population > SOIL_PRESSURE_THRESHOLD * carrying_capacity):
        soil_pressure_streak += 1
        if soil_pressure_streak >= SOIL_PRESSURE_STREAK_LIMIT:
            events.append("soil_exhaustion")
    else:
        soil_pressure_streak = 0

    # Overextraction (per-resource)
    for slot in range(3):
        rtype = resource_types[slot]
        if rtype == EMPTY_SLOT or rtype not in DEPLETABLE:
            continue
        eff_yield = eff_yields[slot]
        sustainable = eff_yield * WORKERS_PER_YIELD_UNIT
        worker_count = population // 5 if population > 0 else 0
        if sustainable > 0 and worker_count > sustainable:
            streak = over_streaks.get(slot, 0) + 1
            over_streaks[slot] = streak
            if streak >= OVEREXTRACTION_STREAK_LIMIT:
                eff_yields[slot] *= (1.0 - OVEREXTRACTION_YIELD_PENALTY)
                over_streaks[slot] = 0
                events.append("resource_depletion")
        else:
            over_streaks[slot] = 0

    return soil_pressure_streak, over_streaks, eff_yields, events


def season_id_from_turn(turn: int) -> int:
    """Map turn number to season_id (0-3)."""
    return (turn % 12) // 3
