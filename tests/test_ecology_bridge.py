"""M54a: Ecology bridge tests — schema round-trip across Python and Rust."""
import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import build_region_batch
from chronicler.models import Infrastructure, InfrastructureType, Region


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ecology_region_batch(
    num_regions=2,
    capacity=60,
    populations=None,
    controllers=None,
    disease_baselines=None,
    capacity_modifiers=None,
    resource_base_yields=None,
    resource_effective_yields=None,
    resource_suspensions=None,
    has_irrigations=None,
    has_mines_arr=None,
    active_focuses=None,
    prev_turn_waters=None,
    soil_pressure_streaks=None,
    overextraction_streaks=None,
):
    """Build a minimal region batch with all M54a ecology columns."""
    if populations is None:
        populations = [capacity] * num_regions
    if controllers is None:
        controllers = [0] * num_regions
    if disease_baselines is None:
        disease_baselines = [0.01] * num_regions
    if capacity_modifiers is None:
        capacity_modifiers = [1.0] * num_regions
    if resource_base_yields is None:
        resource_base_yields = [[0.0, 0.0, 0.0]] * num_regions
    if resource_effective_yields is None:
        resource_effective_yields = [[0.0, 0.0, 0.0]] * num_regions
    if resource_suspensions is None:
        resource_suspensions = [[False, False, False]] * num_regions
    if has_irrigations is None:
        has_irrigations = [False] * num_regions
    if has_mines_arr is None:
        has_mines_arr = [False] * num_regions
    if active_focuses is None:
        active_focuses = [0] * num_regions
    if prev_turn_waters is None:
        prev_turn_waters = [0.0] * num_regions
    if soil_pressure_streaks is None:
        soil_pressure_streaks = [0] * num_regions
    if overextraction_streaks is None:
        overextraction_streaks = [[0, 0, 0]] * num_regions

    return pa.record_batch({
        "region_id": pa.array(range(num_regions), type=pa.uint16()),
        "terrain": pa.array([0] * num_regions, type=pa.uint8()),
        "carrying_capacity": pa.array([capacity] * num_regions, type=pa.uint16()),
        "population": pa.array(populations, type=pa.uint16()),
        "soil": pa.array([0.8] * num_regions, type=pa.float32()),
        "water": pa.array([0.6] * num_regions, type=pa.float32()),
        "forest_cover": pa.array([0.3] * num_regions, type=pa.float32()),
        "controller_civ": pa.array(controllers, type=pa.uint8()),
        # M54a ecology columns
        "disease_baseline": pa.array(disease_baselines, type=pa.float32()),
        "capacity_modifier": pa.array(capacity_modifiers, type=pa.float32()),
        "resource_base_yield_0": pa.array([r[0] for r in resource_base_yields], type=pa.float32()),
        "resource_base_yield_1": pa.array([r[1] for r in resource_base_yields], type=pa.float32()),
        "resource_base_yield_2": pa.array([r[2] for r in resource_base_yields], type=pa.float32()),
        "resource_effective_yield_0": pa.array([r[0] for r in resource_effective_yields], type=pa.float32()),
        "resource_effective_yield_1": pa.array([r[1] for r in resource_effective_yields], type=pa.float32()),
        "resource_effective_yield_2": pa.array([r[2] for r in resource_effective_yields], type=pa.float32()),
        "resource_suspension_0": pa.array([r[0] for r in resource_suspensions], type=pa.bool_()),
        "resource_suspension_1": pa.array([r[1] for r in resource_suspensions], type=pa.bool_()),
        "resource_suspension_2": pa.array([r[2] for r in resource_suspensions], type=pa.bool_()),
        "has_irrigation": pa.array(has_irrigations, type=pa.bool_()),
        "has_mines": pa.array(has_mines_arr, type=pa.bool_()),
        "active_focus": pa.array(active_focuses, type=pa.uint8()),
        "prev_turn_water": pa.array(prev_turn_waters, type=pa.float32()),
        "soil_pressure_streak": pa.array(soil_pressure_streaks, type=pa.int32()),
        "overextraction_streak_0": pa.array([r[0] for r in overextraction_streaks], type=pa.int32()),
        "overextraction_streak_1": pa.array([r[1] for r in overextraction_streaks], type=pa.int32()),
        "overextraction_streak_2": pa.array([r[2] for r in overextraction_streaks], type=pa.int32()),
    })


# ---------------------------------------------------------------------------
# FFI round-trip tests
# ---------------------------------------------------------------------------

class TestEcologySchemaFFIRoundTrip:
    """Verify M54a ecology columns survive the Python -> Arrow -> Rust round-trip."""

    def test_ecology_columns_accepted_by_set_region_state(self):
        """set_region_state does not error when M54a columns are present."""
        sim = AgentSimulator(num_regions=2, seed=42)
        batch = _make_ecology_region_batch(num_regions=2, capacity=10)
        sim.set_region_state(batch)
        snap = sim.get_snapshot()
        assert snap.num_rows == 20  # 10 agents per region

    def test_ecology_columns_optional_backward_compat(self):
        """Old-style batches without M54a columns still work (backward compat)."""
        sim = AgentSimulator(num_regions=1, seed=42)
        # Minimal batch with only core columns
        batch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "terrain": pa.array([0], type=pa.uint8()),
            "carrying_capacity": pa.array([10], type=pa.uint16()),
            "population": pa.array([10], type=pa.uint16()),
            "soil": pa.array([0.8], type=pa.float32()),
            "water": pa.array([0.6], type=pa.float32()),
            "forest_cover": pa.array([0.3], type=pa.float32()),
        })
        sim.set_region_state(batch)
        snap = sim.get_snapshot()
        assert snap.num_rows == 10

    def test_ecology_columns_update_on_subsequent_calls(self):
        """Subsequent set_region_state calls update ecology fields."""
        sim = AgentSimulator(num_regions=1, seed=42)
        # First call: init
        batch1 = _make_ecology_region_batch(
            num_regions=1, capacity=10,
            disease_baselines=[0.02],
            capacity_modifiers=[0.85],
        )
        sim.set_region_state(batch1)

        # Second call: update with different values
        batch2 = _make_ecology_region_batch(
            num_regions=1, capacity=10, populations=[10],
            disease_baselines=[0.05],
            capacity_modifiers=[0.5],
            resource_base_yields=[[1.2, 0.8, 0.0]],
            resource_effective_yields=[[1.0, 0.6, 0.0]],
            resource_suspensions=[[False, True, False]],
            has_irrigations=[True],
            has_mines_arr=[True],
            active_focuses=[3],
            prev_turn_waters=[0.55],
            soil_pressure_streaks=[2],
            overextraction_streaks=[[0, 3, 0]],
        )
        sim.set_region_state(batch2)
        # No error means update succeeded; agents survive the update
        snap = sim.get_snapshot()
        assert snap.num_rows > 0

    def test_ecology_batch_row_count_matches(self):
        """Ecology columns must have the same row count as core columns."""
        sim = AgentSimulator(num_regions=3, seed=42)
        batch = _make_ecology_region_batch(num_regions=3, capacity=10)
        sim.set_region_state(batch)
        snap = sim.get_snapshot()
        assert snap.num_rows == 30  # 10 agents per region


# ---------------------------------------------------------------------------
# Python batch construction tests
# ---------------------------------------------------------------------------

class TestBuildRegionBatchEcology:
    """Verify build_region_batch emits M54a ecology columns from Region model data."""

    def test_ecology_columns_present_and_typed(self, sample_world):
        batch = build_region_batch(sample_world)
        n = len(sample_world.regions)

        # Presence and types
        expected_float = [
            "disease_baseline", "capacity_modifier",
            "resource_base_yield_0", "resource_base_yield_1", "resource_base_yield_2",
            "resource_effective_yield_0", "resource_effective_yield_1", "resource_effective_yield_2",
            "prev_turn_water",
        ]
        for col in expected_float:
            assert col in batch.schema.names, f"missing: {col}"
            assert batch.schema.field(col).type == pa.float32(), f"wrong type: {col}"

        expected_bool = [
            "resource_suspension_0", "resource_suspension_1", "resource_suspension_2",
            "has_irrigation", "has_mines",
        ]
        for col in expected_bool:
            assert col in batch.schema.names, f"missing: {col}"
            assert batch.schema.field(col).type == pa.bool_(), f"wrong type: {col}"

        expected_int32 = [
            "soil_pressure_streak",
            "overextraction_streak_0", "overextraction_streak_1", "overextraction_streak_2",
        ]
        for col in expected_int32:
            assert col in batch.schema.names, f"missing: {col}"
            assert batch.schema.field(col).type == pa.int32(), f"wrong type: {col}"

        assert "active_focus" in batch.schema.names
        assert batch.schema.field("active_focus").type == pa.uint8()

        # Row count
        assert batch.num_rows == n

    def test_disease_baseline_from_region_model(self, sample_world):
        sample_world.regions[0].disease_baseline = 0.05
        batch = build_region_batch(sample_world)
        vals = batch.column("disease_baseline").to_pylist()
        assert abs(vals[0] - 0.05) < 0.001

    def test_capacity_modifier_from_region_model(self, sample_world):
        sample_world.regions[1].capacity_modifier = 0.5
        batch = build_region_batch(sample_world)
        vals = batch.column("capacity_modifier").to_pylist()
        assert abs(vals[1] - 0.5) < 0.001

    def test_resource_base_yields_from_region_model(self, sample_world):
        sample_world.regions[0].resource_base_yields = [1.5, 0.8, 0.0]
        batch = build_region_batch(sample_world)
        assert abs(batch.column("resource_base_yield_0").to_pylist()[0] - 1.5) < 0.001
        assert abs(batch.column("resource_base_yield_1").to_pylist()[0] - 0.8) < 0.001
        assert abs(batch.column("resource_base_yield_2").to_pylist()[0] - 0.0) < 0.001

    def test_resource_effective_yields_from_region_model(self, sample_world):
        sample_world.regions[0].resource_effective_yields = [1.2, 0.6, 0.0]
        batch = build_region_batch(sample_world)
        assert abs(batch.column("resource_effective_yield_0").to_pylist()[0] - 1.2) < 0.001

    def test_suspension_from_resource_suspensions(self, sample_world):
        # Set resource_types so slot 1 has a real resource type
        sample_world.regions[0].resource_types = [1, 2, 255]
        # Suspend resource type 2 (slot 1) for 3 turns
        sample_world.regions[0].resource_suspensions = {2: 3}
        batch = build_region_batch(sample_world)
        vals0 = batch.column("resource_suspension_0").to_pylist()
        vals1 = batch.column("resource_suspension_1").to_pylist()
        assert vals0[0] is False
        assert vals1[0] is True

    def test_has_irrigation_detects_active_infrastructure(self, sample_world):
        sample_world.regions[0].infrastructure = [
            Infrastructure(
                type=InfrastructureType.IRRIGATION,
                builder_civ="Kethani Empire",
                built_turn=1,
                active=True,
            )
        ]
        batch = build_region_batch(sample_world)
        vals = batch.column("has_irrigation").to_pylist()
        assert vals[0] is True
        assert vals[1] is False  # no irrigation on region 1

    def test_has_mines_detects_active_infrastructure(self, sample_world):
        sample_world.regions[1].infrastructure = [
            Infrastructure(
                type=InfrastructureType.MINES,
                builder_civ="Dorrathi Clans",
                built_turn=2,
                active=True,
            )
        ]
        batch = build_region_batch(sample_world)
        vals = batch.column("has_mines").to_pylist()
        assert vals[0] is False
        assert vals[1] is True

    def test_inactive_infrastructure_not_detected(self, sample_world):
        sample_world.regions[0].infrastructure = [
            Infrastructure(
                type=InfrastructureType.IRRIGATION,
                builder_civ="Kethani Empire",
                built_turn=1,
                active=False,  # destroyed
            )
        ]
        batch = build_region_batch(sample_world)
        assert batch.column("has_irrigation").to_pylist()[0] is False

    def test_soil_pressure_streak_from_region(self, sample_world):
        sample_world.regions[0].soil_pressure_streak = 5
        batch = build_region_batch(sample_world)
        assert batch.column("soil_pressure_streak").to_pylist()[0] == 5

    def test_overextraction_streaks_from_region(self, sample_world):
        sample_world.regions[0].overextraction_streaks = {0: 2, 2: 4}
        batch = build_region_batch(sample_world)
        assert batch.column("overextraction_streak_0").to_pylist()[0] == 2
        assert batch.column("overextraction_streak_1").to_pylist()[0] == 0
        assert batch.column("overextraction_streak_2").to_pylist()[0] == 4

    def test_prev_turn_water_from_region(self, sample_world):
        sample_world.regions[0].prev_turn_water = 0.55
        batch = build_region_batch(sample_world)
        assert abs(batch.column("prev_turn_water").to_pylist()[0] - 0.55) < 0.001
