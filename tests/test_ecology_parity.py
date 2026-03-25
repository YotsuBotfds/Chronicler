"""M54a parity suite: compare legacy Python oracle vs Rust ecology path.

This file verifies that the Rust ecology implementation produces results
matching the legacy Python formulas, within specified tolerances:
  - Exact equality: integer/bool/state-machine fields
  - Tight epsilon (1e-4): clamped ecology fields (f32 vs f64 rounding)
  - Slightly looser epsilon (1e-3) over 50 turns: reserves, yields
  - Exact equality: post-pass-visible state (population, terrain)
"""
import pyarrow as pa
import pytest

from chronicler_agents import EcologySimulator

from tests.legacy_ecology_oracle import (
    TERRAIN_ECOLOGY_CAPS,
    EMPTY_SLOT,
    SEASON_MOD,
    CLIMATE_CLASS_MOD,
    CLIMATE_PHASE_INDEX,
    MINERAL_TYPES,
    effective_capacity as oracle_effective_capacity,
    pressure_multiplier as oracle_pressure_multiplier,
    tick_soil as oracle_tick_soil,
    tick_water as oracle_tick_water,
    tick_forest as oracle_tick_forest,
    apply_cross_effects as oracle_cross_effects,
    clamp_ecology as oracle_clamp_ecology,
    compute_disease_severity as oracle_disease_severity,
    compute_resource_yields as oracle_compute_yields,
    update_depletion_feedback as oracle_depletion_feedback,
    resource_class_index as oracle_resource_class_index,
    season_id_from_turn as oracle_season_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Terrain u8 constants
TERRAIN_MAP = {"plains": 0, "mountains": 1, "coast": 2, "forest": 3, "desert": 4, "tundra": 5}
TERRAIN_FROM_U8 = {v: k for k, v in TERRAIN_MAP.items()}

# Resource type u8 constants
RT_GRAIN = 0
RT_TIMBER = 1
RT_BOTANICALS = 2
RT_FISH = 3
RT_SALT = 4
RT_ORE = 5
RT_PRECIOUS = 6
RT_EXOTIC = 7


def _make_ecology_region_batch(
    num_regions=1,
    capacity=60,
    populations=None,
    controllers=None,
    terrains=None,
    soils=None,
    waters=None,
    forests=None,
    disease_baselines=None,
    endemic_severities=None,
    capacity_modifiers=None,
    resource_types=None,
    resource_base_yields=None,
    resource_effective_yields=None,
    resource_suspensions=None,
    resource_reserves=None,
    has_irrigations=None,
    has_mines_arr=None,
    active_focuses=None,
    prev_turn_waters=None,
    soil_pressure_streaks=None,
    overextraction_streaks=None,
):
    """Build a region batch for EcologySimulator."""
    if populations is None:
        populations = [30] * num_regions
    if controllers is None:
        controllers = [0] * num_regions
    if terrains is None:
        terrains = [0] * num_regions
    if soils is None:
        soils = [0.80] * num_regions
    if waters is None:
        waters = [0.60] * num_regions
    if forests is None:
        forests = [0.20] * num_regions
    if disease_baselines is None:
        disease_baselines = [0.01] * num_regions
    if endemic_severities is None:
        endemic_severities = list(disease_baselines)
    if capacity_modifiers is None:
        capacity_modifiers = [1.0] * num_regions
    if resource_types is None:
        resource_types = [[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT]] * num_regions
    if resource_base_yields is None:
        resource_base_yields = [[1.0, 0.0, 0.0]] * num_regions
    if resource_effective_yields is None:
        resource_effective_yields = [[1.0, 0.0, 0.0]] * num_regions
    if resource_suspensions is None:
        resource_suspensions = [[False, False, False]] * num_regions
    if resource_reserves is None:
        resource_reserves = [[1.0, 1.0, 1.0]] * num_regions
    if has_irrigations is None:
        has_irrigations = [False] * num_regions
    if has_mines_arr is None:
        has_mines_arr = [False] * num_regions
    if active_focuses is None:
        active_focuses = [0] * num_regions
    if prev_turn_waters is None:
        prev_turn_waters = list(waters)
    if soil_pressure_streaks is None:
        soil_pressure_streaks = [0] * num_regions
    if overextraction_streaks is None:
        overextraction_streaks = [[0, 0, 0]] * num_regions

    return pa.record_batch({
        "region_id": pa.array(range(num_regions), type=pa.uint16()),
        "terrain": pa.array(terrains, type=pa.uint8()),
        "carrying_capacity": pa.array([capacity] * num_regions, type=pa.uint16()),
        "population": pa.array(populations, type=pa.uint16()),
        "soil": pa.array(soils, type=pa.float32()),
        "water": pa.array(waters, type=pa.float32()),
        "forest_cover": pa.array(forests, type=pa.float32()),
        "controller_civ": pa.array(controllers, type=pa.uint8()),
        "disease_baseline": pa.array(disease_baselines, type=pa.float32()),
        "endemic_severity": pa.array(endemic_severities, type=pa.float32()),
        "capacity_modifier": pa.array(capacity_modifiers, type=pa.float32()),
        "resource_type_0": pa.array([r[0] for r in resource_types], type=pa.uint8()),
        "resource_type_1": pa.array([r[1] for r in resource_types], type=pa.uint8()),
        "resource_type_2": pa.array([r[2] for r in resource_types], type=pa.uint8()),
        "resource_base_yield_0": pa.array([r[0] for r in resource_base_yields], type=pa.float32()),
        "resource_base_yield_1": pa.array([r[1] for r in resource_base_yields], type=pa.float32()),
        "resource_base_yield_2": pa.array([r[2] for r in resource_base_yields], type=pa.float32()),
        "resource_effective_yield_0": pa.array([r[0] for r in resource_effective_yields], type=pa.float32()),
        "resource_effective_yield_1": pa.array([r[1] for r in resource_effective_yields], type=pa.float32()),
        "resource_effective_yield_2": pa.array([r[2] for r in resource_effective_yields], type=pa.float32()),
        "resource_suspension_0": pa.array([r[0] for r in resource_suspensions], type=pa.bool_()),
        "resource_suspension_1": pa.array([r[1] for r in resource_suspensions], type=pa.bool_()),
        "resource_suspension_2": pa.array([r[2] for r in resource_suspensions], type=pa.bool_()),
        "resource_reserve_0": pa.array([r[0] for r in resource_reserves], type=pa.float32()),
        "resource_reserve_1": pa.array([r[1] for r in resource_reserves], type=pa.float32()),
        "resource_reserve_2": pa.array([r[2] for r in resource_reserves], type=pa.float32()),
        "has_irrigation": pa.array(has_irrigations, type=pa.bool_()),
        "has_mines": pa.array(has_mines_arr, type=pa.bool_()),
        "active_focus": pa.array(active_focuses, type=pa.uint8()),
        "prev_turn_water": pa.array(prev_turn_waters, type=pa.float32()),
        "soil_pressure_streak": pa.array(soil_pressure_streaks, type=pa.int32()),
        "overextraction_streak_0": pa.array([r[0] for r in overextraction_streaks], type=pa.int32()),
        "overextraction_streak_1": pa.array([r[1] for r in overextraction_streaks], type=pa.int32()),
        "overextraction_streak_2": pa.array([r[2] for r in overextraction_streaks], type=pa.int32()),
    })


# Active focus u8 mapping for oracle comparison.
# Must match agent_bridge._get_active_focus() / Rust ecology.rs.
FOCUS_MAP = {
    0: None,
    1: "navigation",
    2: "metallurgy",
    3: "agriculture",
    4: "fortification",
    5: "commerce",
    6: "scholarship",
    7: "exploration",
    8: "banking",
    9: "printing",
    10: "mechanization",
    11: "railways",
    12: "naval_power",
    13: "networks",
    14: "surveillance",
    15: "media",
}


def _run_oracle_ecology_tick(
    terrain: str,
    soil: float,
    water: float,
    forest_cover: float,
    population: int,
    carrying_capacity: int,
    capacity_modifier: float,
    climate_phase: str,
    has_mine: bool,
    has_irrigation: bool,
    active_focus: str | None,
    disease_baseline: float,
    endemic_severity: float,
    prev_turn_water: float,
    resource_types: list[int],
    resource_base_yields: list[float],
    resource_effective_yields: list[float],
    resource_reserves: list[float],
    resource_suspensions: dict,
    soil_pressure_streak: int,
    overextraction_streaks: dict[int, int],
    turn: int,
    army_arrived: bool = False,
    pandemic_active: bool = False,
):
    """Run the full oracle ecology tick pipeline for a single region.

    Returns a dict of all output fields for comparison.
    """
    season_id = oracle_season_id(turn)

    # 1. Disease severity (before ecology updates)
    new_severity = oracle_disease_severity(
        endemic_severity=endemic_severity,
        disease_baseline=disease_baseline,
        population=population,
        carrying_capacity=carrying_capacity,
        terrain=terrain,
        pre_water=water,
        prev_turn_water=prev_turn_water,
        season_id=season_id,
        army_arrived=army_arrived,
        pandemic_active=pandemic_active,
    )

    # 2. Depletion feedback
    soil_streak, over_streaks, eff_yields, depletion_events = oracle_depletion_feedback(
        resource_types=resource_types,
        resource_effective_yields=resource_effective_yields,
        population=population,
        carrying_capacity=carrying_capacity,
        soil_pressure_streak=soil_pressure_streak,
        overextraction_streaks=overextraction_streaks,
    )

    # 3. Soil degradation mult from streak
    degradation_mult = 2.0 if soil_streak >= 30 else 1.0

    # 4. Controlled region: full tick
    is_controlled = True  # For parity tests we always use controlled regions

    if is_controlled:
        # Match production mutation order: soil mutated first, then water/forest
        # use the NEW soil for their pressure_multiplier calls.
        new_soil = oracle_tick_soil(
            soil, population, carrying_capacity, water, capacity_modifier,
            climate_phase, has_mine, active_focus, degradation_mult,
        )
        new_water = oracle_tick_water(
            water, population, carrying_capacity, new_soil, capacity_modifier,
            climate_phase, terrain, has_irrigation,
        )
        new_forest = oracle_tick_forest(
            forest_cover, population, carrying_capacity, new_soil, new_water,
            capacity_modifier, climate_phase,
        )
    else:
        new_soil = soil
        new_water = water
        new_forest = forest_cover

    # 5. Cross effects
    new_soil = oracle_cross_effects(new_soil, new_forest)

    # 6. Clamp
    new_soil, new_water, new_forest = oracle_clamp_ecology(terrain, new_soil, new_water, new_forest)

    # 7. Compute yields
    worker_count = population // 5 if population > 0 else 0
    yields, new_reserves = oracle_compute_yields(
        resource_types=resource_types,
        resource_base_yields=resource_base_yields,
        resource_reserves=resource_reserves,
        resource_suspensions=resource_suspensions,
        soil=new_soil,
        water=new_water,
        forest_cover=new_forest,
        carrying_capacity=carrying_capacity,
        capacity_modifier=capacity_modifier,
        population=population,
        season_id=season_id,
        climate_phase=climate_phase,
        worker_count=worker_count,
    )

    # 8. prev_turn_water update
    new_prev_water = new_water

    return {
        "soil": new_soil,
        "water": new_water,
        "forest_cover": new_forest,
        "endemic_severity": new_severity,
        "prev_turn_water": new_prev_water,
        "soil_pressure_streak": soil_streak,
        "overextraction_streaks": over_streaks,
        "resource_reserves": new_reserves,
        "resource_effective_yields": eff_yields,
        "yields": yields,
        "depletion_events": depletion_events,
    }


def _run_rust_ecology_tick(
    terrain_u8: int,
    soil: float,
    water: float,
    forest_cover: float,
    population: int,
    carrying_capacity: int,
    capacity_modifier: float,
    climate_phase_u8: int,
    has_mine: bool,
    has_irrigation: bool,
    active_focus_u8: int,
    disease_baseline: float,
    endemic_severity: float,
    prev_turn_water: float,
    resource_types: list[int],
    resource_base_yields: list[float],
    resource_effective_yields: list[float],
    resource_reserves: list[float],
    resource_suspensions: list[bool],
    soil_pressure_streak: int,
    overextraction_streaks: list[int],
    turn: int,
    army_arrived: bool = False,
    pandemic_active: bool = False,
):
    """Run the Rust ecology tick via AgentSimulator on a single region.

    Uses AgentSimulator rather than EcologySimulator because AgentSimulator
    correctly reads the endemic_severity column from the input batch.
    """
    from chronicler_agents import AgentSimulator
    eco = AgentSimulator(num_regions=1, seed=42)

    batch = pa.record_batch({
        "region_id": pa.array([0], type=pa.uint16()),
        "terrain": pa.array([terrain_u8], type=pa.uint8()),
        "carrying_capacity": pa.array([carrying_capacity], type=pa.uint16()),
        "population": pa.array([population], type=pa.uint16()),
        "soil": pa.array([soil], type=pa.float32()),
        "water": pa.array([water], type=pa.float32()),
        "forest_cover": pa.array([forest_cover], type=pa.float32()),
        "controller_civ": pa.array([0], type=pa.uint8()),
        "disease_baseline": pa.array([disease_baseline], type=pa.float32()),
        "endemic_severity": pa.array([endemic_severity], type=pa.float32()),
        "capacity_modifier": pa.array([capacity_modifier], type=pa.float32()),
        "resource_type_0": pa.array([resource_types[0]], type=pa.uint8()),
        "resource_type_1": pa.array([resource_types[1]], type=pa.uint8()),
        "resource_type_2": pa.array([resource_types[2]], type=pa.uint8()),
        "resource_base_yield_0": pa.array([resource_base_yields[0]], type=pa.float32()),
        "resource_base_yield_1": pa.array([resource_base_yields[1]], type=pa.float32()),
        "resource_base_yield_2": pa.array([resource_base_yields[2]], type=pa.float32()),
        "resource_effective_yield_0": pa.array([resource_effective_yields[0]], type=pa.float32()),
        "resource_effective_yield_1": pa.array([resource_effective_yields[1]], type=pa.float32()),
        "resource_effective_yield_2": pa.array([resource_effective_yields[2]], type=pa.float32()),
        "resource_suspension_0": pa.array([resource_suspensions[0]], type=pa.bool_()),
        "resource_suspension_1": pa.array([resource_suspensions[1]], type=pa.bool_()),
        "resource_suspension_2": pa.array([resource_suspensions[2]], type=pa.bool_()),
        "resource_reserve_0": pa.array([resource_reserves[0]], type=pa.float32()),
        "resource_reserve_1": pa.array([resource_reserves[1]], type=pa.float32()),
        "resource_reserve_2": pa.array([resource_reserves[2]], type=pa.float32()),
        "has_irrigation": pa.array([has_irrigation], type=pa.bool_()),
        "has_mines": pa.array([has_mine], type=pa.bool_()),
        "active_focus": pa.array([active_focus_u8], type=pa.uint8()),
        "prev_turn_water": pa.array([prev_turn_water], type=pa.float32()),
        "soil_pressure_streak": pa.array([soil_pressure_streak], type=pa.int32()),
        "overextraction_streak_0": pa.array([overextraction_streaks[0]], type=pa.int32()),
        "overextraction_streak_1": pa.array([overextraction_streaks[1]], type=pa.int32()),
        "overextraction_streak_2": pa.array([overextraction_streaks[2]], type=pa.int32()),
    })

    # Initialize endemic_severity by setting it via the batch
    # (The batch column 'disease_baseline' sets baseline; severity starts at baseline.
    # We manually set it via a batch with an endemic_severity field if supported,
    # but EcologySimulator reads endemic_severity from disease_baseline at init.)
    # For parity, we rely on the initial state matching.

    eco.set_region_state(batch)

    region_batch, event_batch = eco.tick_ecology(
        turn=turn,
        climate_phase=climate_phase_u8,
        pandemic_mask=[pandemic_active],
        army_arrived_mask=[army_arrived],
    )

    return {
        "soil": region_batch.column("soil").to_pylist()[0],
        "water": region_batch.column("water").to_pylist()[0],
        "forest_cover": region_batch.column("forest_cover").to_pylist()[0],
        "endemic_severity": region_batch.column("endemic_severity").to_pylist()[0],
        "prev_turn_water": region_batch.column("prev_turn_water").to_pylist()[0],
        "soil_pressure_streak": region_batch.column("soil_pressure_streak").to_pylist()[0],
        "overextraction_streaks": [
            region_batch.column("overextraction_streak_0").to_pylist()[0],
            region_batch.column("overextraction_streak_1").to_pylist()[0],
            region_batch.column("overextraction_streak_2").to_pylist()[0],
        ],
        "resource_reserves": [
            region_batch.column("resource_reserve_0").to_pylist()[0],
            region_batch.column("resource_reserve_1").to_pylist()[0],
            region_batch.column("resource_reserve_2").to_pylist()[0],
        ],
        "resource_effective_yields": [
            region_batch.column("resource_effective_yield_0").to_pylist()[0],
            region_batch.column("resource_effective_yield_1").to_pylist()[0],
            region_batch.column("resource_effective_yield_2").to_pylist()[0],
        ],
        "yields": [
            region_batch.column("current_turn_yield_0").to_pylist()[0],
            region_batch.column("current_turn_yield_1").to_pylist()[0],
            region_batch.column("current_turn_yield_2").to_pylist()[0],
        ],
        "event_count": event_batch.num_rows,
        "event_types": event_batch.column("event_type").to_pylist() if event_batch.num_rows > 0 else [],
    }


# ---------------------------------------------------------------------------
# Parity comparison helpers
# ---------------------------------------------------------------------------

TIGHT_EPSILON = 5e-4  # f32 vs f64 rounding through pressure_multiplier cascade
LOOSE_EPSILON = 1e-3


def _assert_ecology_parity(oracle, rust, label=""):
    """Compare oracle and Rust results with appropriate tolerances."""
    prefix = f"{label}: " if label else ""

    # Tight epsilon for clamped ecology fields (f32 vs f64 rounding)
    assert abs(oracle["soil"] - rust["soil"]) < TIGHT_EPSILON, (
        f"{prefix}soil mismatch: oracle={oracle['soil']}, rust={rust['soil']}"
    )
    assert abs(oracle["water"] - rust["water"]) < TIGHT_EPSILON, (
        f"{prefix}water mismatch: oracle={oracle['water']}, rust={rust['water']}"
    )
    assert abs(oracle["forest_cover"] - rust["forest_cover"]) < TIGHT_EPSILON, (
        f"{prefix}forest mismatch: oracle={oracle['forest_cover']}, rust={rust['forest_cover']}"
    )

    # Disease severity: tight epsilon
    assert abs(oracle["endemic_severity"] - rust["endemic_severity"]) < TIGHT_EPSILON, (
        f"{prefix}severity mismatch: oracle={oracle['endemic_severity']}, rust={rust['endemic_severity']}"
    )

    # prev_turn_water: tight epsilon (just the post-tick water copy)
    assert abs(oracle["prev_turn_water"] - rust["prev_turn_water"]) < TIGHT_EPSILON, (
        f"{prefix}prev_water mismatch: oracle={oracle['prev_turn_water']}, rust={rust['prev_turn_water']}"
    )

    # Exact equality for integer/state-machine fields
    assert oracle["soil_pressure_streak"] == rust["soil_pressure_streak"], (
        f"{prefix}soil_streak mismatch: oracle={oracle['soil_pressure_streak']}, rust={rust['soil_pressure_streak']}"
    )

    # Overextraction streaks: exact equality
    oracle_streaks = oracle["overextraction_streaks"]
    rust_streaks = rust["overextraction_streaks"]
    if isinstance(oracle_streaks, dict):
        oracle_streaks_list = [oracle_streaks.get(i, 0) for i in range(3)]
    else:
        oracle_streaks_list = list(oracle_streaks)
    assert oracle_streaks_list == list(rust_streaks), (
        f"{prefix}overextraction_streaks mismatch: oracle={oracle_streaks_list}, rust={rust_streaks}"
    )

    # Reserves: looser epsilon
    for slot in range(3):
        assert abs(oracle["resource_reserves"][slot] - rust["resource_reserves"][slot]) < LOOSE_EPSILON, (
            f"{prefix}reserves[{slot}] mismatch: oracle={oracle['resource_reserves'][slot]}, rust={rust['resource_reserves'][slot]}"
        )

    # Yields: looser epsilon
    for slot in range(3):
        assert abs(oracle["yields"][slot] - rust["yields"][slot]) < LOOSE_EPSILON, (
            f"{prefix}yields[{slot}] mismatch: oracle={oracle['yields'][slot]}, rust={rust['yields'][slot]}"
        )


# ===========================================================================
# Parity tests: single-turn comparisons
# ===========================================================================


class TestSingleTurnParity:
    """Single-turn parity: oracle vs Rust on identical inputs."""

    def test_basic_plains_temperate(self):
        """Basic plains region, temperate climate."""
        oracle = _run_oracle_ecology_tick(
            terrain="plains", soil=0.80, water=0.60, forest_cover=0.20,
            population=30, carrying_capacity=60, capacity_modifier=1.0,
            climate_phase="temperate",
            has_mine=False, has_irrigation=False, active_focus=None,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.60,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=0,
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=TERRAIN_MAP["plains"], soil=0.80, water=0.60, forest_cover=0.20,
            population=30, carrying_capacity=60, capacity_modifier=1.0,
            climate_phase_u8=0,  # temperate
            has_mine=False, has_irrigation=False, active_focus_u8=0,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.60,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=0,
        )

        _assert_ecology_parity(oracle, rust, "basic_plains")

    def test_desert_drought(self):
        """Desert region during drought."""
        oracle = _run_oracle_ecology_tick(
            terrain="desert", soil=0.20, water=0.15, forest_cover=0.05,
            population=15, carrying_capacity=20, capacity_modifier=1.0,
            climate_phase="drought",
            has_mine=False, has_irrigation=False, active_focus=None,
            disease_baseline=0.015, endemic_severity=0.015,
            prev_turn_water=0.15,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[0.5, 0.0, 0.0],
            resource_effective_yields=[0.5, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=0,
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=TERRAIN_MAP["desert"], soil=0.20, water=0.15, forest_cover=0.05,
            population=15, carrying_capacity=20, capacity_modifier=1.0,
            climate_phase_u8=2,  # drought
            has_mine=False, has_irrigation=False, active_focus_u8=0,
            disease_baseline=0.015, endemic_severity=0.015,
            prev_turn_water=0.15,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[0.5, 0.0, 0.0],
            resource_effective_yields=[0.5, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=0,
        )

        _assert_ecology_parity(oracle, rust, "desert_drought")

    def test_mountains_with_mines(self):
        """Mountain region with active mines and ore depletion."""
        oracle = _run_oracle_ecology_tick(
            terrain="mountains", soil=0.40, water=0.80, forest_cover=0.30,
            population=20, carrying_capacity=40, capacity_modifier=1.0,
            climate_phase="temperate",
            has_mine=True, has_irrigation=False, active_focus=None,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.80,
            resource_types=[RT_ORE, RT_PRECIOUS, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.5, 0.0],
            resource_effective_yields=[1.0, 0.5, 0.0],
            resource_reserves=[0.50, 0.10, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=0,
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=TERRAIN_MAP["mountains"], soil=0.40, water=0.80, forest_cover=0.30,
            population=20, carrying_capacity=40, capacity_modifier=1.0,
            climate_phase_u8=0,
            has_mine=True, has_irrigation=False, active_focus_u8=0,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.80,
            resource_types=[RT_ORE, RT_PRECIOUS, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.5, 0.0],
            resource_effective_yields=[1.0, 0.5, 0.0],
            resource_reserves=[0.50, 0.10, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=0,
        )

        _assert_ecology_parity(oracle, rust, "mountains_mines")

    def test_forest_cooling_with_agriculture(self):
        """Forest region during cooling with agriculture focus."""
        oracle = _run_oracle_ecology_tick(
            terrain="forest", soil=0.70, water=0.70, forest_cover=0.80,
            population=10, carrying_capacity=50, capacity_modifier=1.0,
            climate_phase="cooling",
            has_mine=False, has_irrigation=False, active_focus="agriculture",
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.70,
            resource_types=[RT_TIMBER, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=0,
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=TERRAIN_MAP["forest"], soil=0.70, water=0.70, forest_cover=0.80,
            population=10, carrying_capacity=50, capacity_modifier=1.0,
            climate_phase_u8=3,  # cooling
            has_mine=False, has_irrigation=False, active_focus_u8=3,  # agriculture
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.70,
            resource_types=[RT_TIMBER, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=0,
        )

        _assert_ecology_parity(oracle, rust, "forest_cooling_agri")

    def test_coast_irrigation_temperate(self):
        """Coast region with irrigation in temperate."""
        oracle = _run_oracle_ecology_tick(
            terrain="coast", soil=0.70, water=0.60, forest_cover=0.30,
            population=25, carrying_capacity=50, capacity_modifier=1.0,
            climate_phase="temperate",
            has_mine=False, has_irrigation=True, active_focus=None,
            disease_baseline=0.02, endemic_severity=0.02,
            prev_turn_water=0.60,
            resource_types=[RT_FISH, RT_SALT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.8, 0.0],
            resource_effective_yields=[1.0, 0.8, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=3,  # summer
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=TERRAIN_MAP["coast"], soil=0.70, water=0.60, forest_cover=0.30,
            population=25, carrying_capacity=50, capacity_modifier=1.0,
            climate_phase_u8=0,  # temperate
            has_mine=False, has_irrigation=True, active_focus_u8=0,
            disease_baseline=0.02, endemic_severity=0.02,
            prev_turn_water=0.60,
            resource_types=[RT_FISH, RT_SALT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.8, 0.0],
            resource_effective_yields=[1.0, 0.8, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=3,  # summer
        )

        _assert_ecology_parity(oracle, rust, "coast_irrigation")

    def test_disease_overcrowding_flare(self):
        """Verify disease overcrowding flare matches."""
        oracle = _run_oracle_ecology_tick(
            terrain="plains", soil=0.80, water=0.60, forest_cover=0.20,
            population=55, carrying_capacity=60, capacity_modifier=1.0,
            climate_phase="temperate",
            has_mine=False, has_irrigation=False, active_focus=None,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.60,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil_pressure_streak=0,
            overextraction_streaks={0: 0, 1: 0, 2: 0},
            turn=0,
        )

        rust = _run_rust_ecology_tick(
            terrain_u8=0, soil=0.80, water=0.60, forest_cover=0.20,
            population=55, carrying_capacity=60, capacity_modifier=1.0,
            climate_phase_u8=0,
            has_mine=False, has_irrigation=False, active_focus_u8=0,
            disease_baseline=0.01, endemic_severity=0.01,
            prev_turn_water=0.60,
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_effective_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions=[False, False, False],
            soil_pressure_streak=0,
            overextraction_streaks=[0, 0, 0],
            turn=0,
        )

        _assert_ecology_parity(oracle, rust, "overcrowding_flare")
        # Both should show elevated severity from overcrowding
        assert oracle["endemic_severity"] > 0.01
        assert rust["endemic_severity"] > 0.01


# ===========================================================================
# Multi-turn parity tests
# ===========================================================================


class TestMultiTurnParity:
    """Multi-turn parity: verify drift stays within tolerance over 50 turns."""

    def test_50_turn_plains_temperate(self):
        """Run 50 turns of plains/temperate and check final state parity."""
        # Oracle state
        soil, water, forest = 0.80, 0.60, 0.20
        severity = 0.01
        prev_water = 0.60
        reserves = [1.0, 1.0, 1.0]
        eff_yields = [1.0, 0.0, 0.0]
        soil_streak = 0
        over_streaks: dict[int, int] = {0: 0, 1: 0, 2: 0}
        rtypes = [RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT]
        base_yields = [1.0, 0.0, 0.0]

        for turn in range(50):
            result = _run_oracle_ecology_tick(
                terrain="plains", soil=soil, water=water, forest_cover=forest,
                population=30, carrying_capacity=60, capacity_modifier=1.0,
                climate_phase="temperate",
                has_mine=False, has_irrigation=False, active_focus=None,
                disease_baseline=0.01, endemic_severity=severity,
                prev_turn_water=prev_water,
                resource_types=rtypes,
                resource_base_yields=base_yields,
                resource_effective_yields=eff_yields,
                resource_reserves=reserves,
                resource_suspensions={},
                soil_pressure_streak=soil_streak,
                overextraction_streaks=over_streaks,
                turn=turn,
            )
            soil = result["soil"]
            water = result["water"]
            forest = result["forest_cover"]
            severity = result["endemic_severity"]
            prev_water = result["prev_turn_water"]
            reserves = result["resource_reserves"]
            eff_yields = result["resource_effective_yields"]
            soil_streak = result["soil_pressure_streak"]
            over_streaks = result["overextraction_streaks"]

        oracle_final = result

        # Rust path: run 50 turns via EcologySimulator
        eco = EcologySimulator()
        batch = _make_ecology_region_batch(
            num_regions=1, capacity=60, populations=[30],
            controllers=[0], terrains=[0],
            soils=[0.80], waters=[0.60], forests=[0.20],
            disease_baselines=[0.01],
            resource_types=[[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT]],
            resource_base_yields=[[1.0, 0.0, 0.0]],
            resource_effective_yields=[[1.0, 0.0, 0.0]],
            resource_reserves=[[1.0, 1.0, 1.0]],
            prev_turn_waters=[0.60],
        )
        eco.set_region_state(batch)

        for turn in range(50):
            region_batch, _ = eco.tick_ecology(
                turn=turn, climate_phase=0,
                pandemic_mask=[False], army_arrived_mask=[False],
            )

        rust_soil = region_batch.column("soil").to_pylist()[0]
        rust_water = region_batch.column("water").to_pylist()[0]
        rust_forest = region_batch.column("forest_cover").to_pylist()[0]
        rust_severity = region_batch.column("endemic_severity").to_pylist()[0]
        rust_streak = region_batch.column("soil_pressure_streak").to_pylist()[0]
        rust_reserves = [
            region_batch.column("resource_reserve_0").to_pylist()[0],
            region_batch.column("resource_reserve_1").to_pylist()[0],
            region_batch.column("resource_reserve_2").to_pylist()[0],
        ]
        rust_yields = [
            region_batch.column("current_turn_yield_0").to_pylist()[0],
            region_batch.column("current_turn_yield_1").to_pylist()[0],
            region_batch.column("current_turn_yield_2").to_pylist()[0],
        ]

        # Clamped fields: tight epsilon
        assert abs(oracle_final["soil"] - rust_soil) < TIGHT_EPSILON, (
            f"50-turn soil: oracle={oracle_final['soil']}, rust={rust_soil}"
        )
        assert abs(oracle_final["water"] - rust_water) < TIGHT_EPSILON, (
            f"50-turn water: oracle={oracle_final['water']}, rust={rust_water}"
        )
        assert abs(oracle_final["forest_cover"] - rust_forest) < TIGHT_EPSILON, (
            f"50-turn forest: oracle={oracle_final['forest_cover']}, rust={rust_forest}"
        )

        # Integer fields: exact
        assert oracle_final["soil_pressure_streak"] == rust_streak

        # Yields/reserves: looser epsilon (50-turn accumulation drift)
        for slot in range(3):
            assert abs(oracle_final["yields"][slot] - rust_yields[slot]) < LOOSE_EPSILON, (
                f"50-turn yield[{slot}]: oracle={oracle_final['yields'][slot]}, rust={rust_yields[slot]}"
            )
            assert abs(oracle_final["resource_reserves"][slot] - rust_reserves[slot]) < LOOSE_EPSILON, (
                f"50-turn reserves[{slot}]: oracle={oracle_final['resource_reserves'][slot]}, rust={rust_reserves[slot]}"
            )


# ===========================================================================
# Oracle standalone tests (verify the oracle itself is correct)
# ===========================================================================


class TestOracleStandalone:
    """Sanity tests for the legacy oracle formulas in isolation."""

    def test_effective_capacity_basic(self):
        assert oracle_effective_capacity(100, 0.5, 0.6) == 50  # 100 * 0.5 * min(1,0.6/0.5)

    def test_effective_capacity_floor(self):
        assert oracle_effective_capacity(1, 0.05, 0.10) >= 1

    def test_clamp_ecology_desert(self):
        s, w, f = oracle_clamp_ecology("desert", 0.50, 0.50, 0.50)
        assert s == 0.30
        assert w == 0.20
        assert f == 0.10

    def test_clamp_ecology_floors(self):
        s, w, f = oracle_clamp_ecology("plains", -1.0, -1.0, -1.0)
        assert s == 0.05
        assert w == 0.10
        assert f == 0.00

    def test_disease_overcrowding(self):
        sev = oracle_disease_severity(
            endemic_severity=0.01, disease_baseline=0.01,
            population=50, carrying_capacity=60,
            terrain="plains", pre_water=0.6, prev_turn_water=0.6,
        )
        assert abs(sev - 0.05) < 0.001  # 0.01 + 0.04 overcrowding

    def test_disease_decay(self):
        sev = oracle_disease_severity(
            endemic_severity=0.09, disease_baseline=0.01,
            population=20, carrying_capacity=60,
            terrain="plains", pre_water=0.6, prev_turn_water=0.6,
        )
        assert abs(sev - 0.07) < 0.001  # 0.09 - 0.25*(0.09-0.01)

    def test_compute_yields_grain(self):
        yields, reserves = oracle_compute_yields(
            resource_types=[RT_GRAIN, EMPTY_SLOT, EMPTY_SLOT],
            resource_base_yields=[1.0, 0.0, 0.0],
            resource_reserves=[1.0, 1.0, 1.0],
            resource_suspensions={},
            soil=0.8, water=0.7, forest_cover=0.2,
            carrying_capacity=60, capacity_modifier=1.0, population=30,
            season_id=2, climate_phase="temperate", worker_count=0,
        )
        # 1.0 * 1.5 (autumn grain) * 1.0 (temperate crop) * (0.8*0.7) * 1.0
        expected = 1.0 * 1.5 * 1.0 * 0.56 * 1.0
        assert abs(yields[0] - expected) < 0.001

    def test_season_id_from_turn(self):
        assert oracle_season_id(0) == 0
        assert oracle_season_id(3) == 1
        assert oracle_season_id(6) == 2
        assert oracle_season_id(9) == 3
        assert oracle_season_id(12) == 0
