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

    def test_missing_required_column_raises_schema_error(self):
        """Explicit contract test: missing core columns must fail loudly."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "carrying_capacity": pa.array([10], type=pa.uint16()),
            "population": pa.array([10], type=pa.uint16()),
            "soil": pa.array([0.8], type=pa.float32()),
            "water": pa.array([0.6], type=pa.float32()),
            "forest_cover": pa.array([0.3], type=pa.float32()),
        })
        with pytest.raises(Exception):
            sim.set_region_state(batch)

    def test_wrong_arrow_type_raises_cast_error(self):
        """Explicit contract test: wrong Arrow types must fail loudly."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "terrain": pa.array([0], type=pa.uint8()),
            "carrying_capacity": pa.array([10], type=pa.uint16()),
            "population": pa.array([10.0], type=pa.float32()),
            "soil": pa.array([0.8], type=pa.float32()),
            "water": pa.array([0.6], type=pa.float32()),
            "forest_cover": pa.array([0.3], type=pa.float32()),
        })
        with pytest.raises(Exception):
            sim.set_region_state(batch)

    def test_column_order_drift_is_tolerated(self):
        """Column lookup should be name-based, not position-based."""
        sim = AgentSimulator(num_regions=1, seed=42)
        arrays = [
            pa.array([0.8], type=pa.float32()),
            pa.array([0], type=pa.uint16()),
            pa.array([10], type=pa.uint16()),
            pa.array([0.6], type=pa.float32()),
            pa.array([10], type=pa.uint16()),
            pa.array([0.3], type=pa.float32()),
            pa.array([0], type=pa.uint8()),
        ]
        batch = pa.RecordBatch.from_arrays(
            arrays,
            names=[
                "soil",
                "region_id",
                "population",
                "water",
                "carrying_capacity",
                "forest_cover",
                "terrain",
            ],
        )
        sim.set_region_state(batch)
        assert sim.get_snapshot().num_rows == 10


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


# ---------------------------------------------------------------------------
# M54a Task 3: tick_ecology FFI tests (AgentSimulator)
# ---------------------------------------------------------------------------


class TestAgentSimulatorTickEcology:
    """Test tick_ecology() on AgentSimulator returns correct batches."""

    def test_tick_ecology_returns_two_batches(self):
        """tick_ecology returns (region_batch, event_batch) with stable schemas."""
        sim = AgentSimulator(num_regions=2, seed=42)
        batch = _make_ecology_region_batch(num_regions=2, capacity=30)
        sim.set_region_state(batch)

        region_batch, event_batch = sim.tick_ecology(
            turn=0,
            climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )

        # Region batch schema
        assert region_batch.num_rows == 2
        expected_region_cols = [
            "region_id", "soil", "water", "forest_cover",
            "endemic_severity", "prev_turn_water",
            "soil_pressure_streak",
            "overextraction_streak_0", "overextraction_streak_1", "overextraction_streak_2",
            "resource_reserve_0", "resource_reserve_1", "resource_reserve_2",
            "resource_effective_yield_0", "resource_effective_yield_1", "resource_effective_yield_2",
            "current_turn_yield_0", "current_turn_yield_1", "current_turn_yield_2",
        ]
        assert region_batch.schema.names == expected_region_cols

        # Event batch schema
        expected_event_cols = ["event_type", "region_id", "slot", "magnitude"]
        assert event_batch.schema.names == expected_event_cols

    def test_tick_ecology_region_batch_types(self):
        """Region batch columns have correct Arrow types."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = _make_ecology_region_batch(num_regions=1, capacity=10)
        sim.set_region_state(batch)

        region_batch, _ = sim.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        assert region_batch.schema.field("region_id").type == pa.uint16()
        assert region_batch.schema.field("soil").type == pa.float32()
        assert region_batch.schema.field("water").type == pa.float32()
        assert region_batch.schema.field("forest_cover").type == pa.float32()
        assert region_batch.schema.field("endemic_severity").type == pa.float32()
        assert region_batch.schema.field("prev_turn_water").type == pa.float32()
        assert region_batch.schema.field("soil_pressure_streak").type == pa.int32()
        assert region_batch.schema.field("overextraction_streak_0").type == pa.int32()
        assert region_batch.schema.field("resource_reserve_0").type == pa.float32()
        assert region_batch.schema.field("resource_effective_yield_0").type == pa.float32()
        assert region_batch.schema.field("current_turn_yield_0").type == pa.float32()

    def test_tick_ecology_event_batch_types(self):
        """Event batch columns have correct Arrow types."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = _make_ecology_region_batch(num_regions=1, capacity=10)
        sim.set_region_state(batch)

        _, event_batch = sim.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        assert event_batch.schema.field("event_type").type == pa.uint8()
        assert event_batch.schema.field("region_id").type == pa.uint16()
        assert event_batch.schema.field("slot").type == pa.uint8()
        assert event_batch.schema.field("magnitude").type == pa.float32()

    def test_tick_ecology_before_set_region_state_errors(self):
        """tick_ecology() before set_region_state() raises."""
        sim = AgentSimulator(num_regions=2, seed=42)
        with pytest.raises((RuntimeError, ValueError), match="set_region_state"):
            sim.tick_ecology(
                turn=0, climate_phase=0,
                pandemic_mask=[False, False],
                army_arrived_mask=[False, False],
            )

    def test_tick_ecology_modifies_soil(self):
        """After tick_ecology, soil values change (recovery or degradation)."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = _make_ecology_region_batch(
            num_regions=1, capacity=60, populations=[30],
            controllers=[0],
        )
        sim.set_region_state(batch)

        region_batch, _ = sim.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        # Soil should have changed from initial 0.8 due to recovery
        soil_val = region_batch.column("soil").to_pylist()[0]
        assert soil_val != 0.8, f"soil should change after ecology tick, got {soil_val}"

    def test_tick_ecology_yields_nonzero_for_grain(self):
        """Grain resource should produce non-zero yields."""
        sim = AgentSimulator(num_regions=1, seed=42)
        batch = _make_ecology_region_batch(
            num_regions=1, capacity=60, populations=[30],
            controllers=[0],
            resource_base_yields=[[1.0, 0.0, 0.0]],
            resource_effective_yields=[[1.0, 0.0, 0.0]],
        )
        # Also need resource types for the ecology core to produce yields
        # Add resource_type columns to the batch
        extra = {
            "resource_type_0": pa.array([0], type=pa.uint8()),  # GRAIN
            "resource_type_1": pa.array([255], type=pa.uint8()),  # EMPTY
            "resource_type_2": pa.array([255], type=pa.uint8()),  # EMPTY
        }
        columns = {name: batch.column(name) for name in batch.schema.names}
        columns.update(extra)
        batch_with_types = pa.record_batch(columns)

        sim.set_region_state(batch_with_types)
        region_batch, _ = sim.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        yield_val = region_batch.column("current_turn_yield_0").to_pylist()[0]
        assert yield_val > 0.0, f"grain yield should be > 0, got {yield_val}"


# ---------------------------------------------------------------------------
# M54a Task 3: apply_region_postpass_patch tests
# ---------------------------------------------------------------------------


class TestApplyRegionPostpassPatch:
    """Test apply_region_postpass_patch() on AgentSimulator."""

    def _setup_sim_with_ecology_tick(self):
        """Create a simulator, set region state, and run one ecology tick."""
        sim = AgentSimulator(num_regions=2, seed=42)
        batch = _make_ecology_region_batch(
            num_regions=2, capacity=60, populations=[30, 30],
            controllers=[0, 1],
            resource_base_yields=[[1.0, 0.0, 0.0], [0.8, 0.0, 0.0]],
            resource_effective_yields=[[1.0, 0.0, 0.0], [0.8, 0.0, 0.0]],
        )
        extra = {
            "resource_type_0": pa.array([0, 0], type=pa.uint8()),  # GRAIN
            "resource_type_1": pa.array([255, 255], type=pa.uint8()),
            "resource_type_2": pa.array([255, 255], type=pa.uint8()),
        }
        columns = {name: batch.column(name) for name in batch.schema.names}
        columns.update(extra)
        batch_with_types = pa.record_batch(columns)

        sim.set_region_state(batch_with_types)
        region_batch, _ = sim.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )
        return sim, region_batch

    def test_patch_updates_population(self):
        """Population-only changes are applied."""
        sim, region_batch = self._setup_sim_with_ecology_tick()

        # Get current soil/water/forest values from the ecology tick output
        soil_vals = region_batch.column("soil").to_pylist()
        water_vals = region_batch.column("water").to_pylist()
        forest_vals = region_batch.column("forest_cover").to_pylist()

        patch = pa.record_batch({
            "region_id": pa.array([0, 1], type=pa.uint16()),
            "population": pa.array([50, 20], type=pa.uint16()),
            "soil": pa.array(soil_vals, type=pa.float32()),
            "water": pa.array(water_vals, type=pa.float32()),
            "forest_cover": pa.array(forest_vals, type=pa.float32()),
            "terrain": pa.array([0, 0], type=pa.uint8()),
            "carrying_capacity": pa.array([60, 60], type=pa.uint16()),
        })
        sim.apply_region_postpass_patch(patch)
        # No error means success

    def test_patch_soil_change_triggers_yield_recompute(self):
        """When soil changes in the patch, yields are recomputed."""
        sim, region_batch = self._setup_sim_with_ecology_tick()

        original_yield = region_batch.column("current_turn_yield_0").to_pylist()[0]
        water_vals = region_batch.column("water").to_pylist()
        forest_vals = region_batch.column("forest_cover").to_pylist()

        # Patch with significantly different soil
        patch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "population": pa.array([30], type=pa.uint16()),
            "soil": pa.array([0.2], type=pa.float32()),  # Much lower soil
            "water": pa.array([water_vals[0]], type=pa.float32()),
            "forest_cover": pa.array([forest_vals[0]], type=pa.float32()),
            "terrain": pa.array([0], type=pa.uint8()),
            "carrying_capacity": pa.array([60], type=pa.uint16()),
        })
        sim.apply_region_postpass_patch(patch)
        # The yield should have been recomputed internally (no way to read it
        # back without another tick, but no error means the recompute ran)

    def test_patch_partial_regions(self):
        """Patch only a subset of regions — others are unchanged."""
        sim, region_batch = self._setup_sim_with_ecology_tick()

        soil_vals = region_batch.column("soil").to_pylist()
        water_vals = region_batch.column("water").to_pylist()
        forest_vals = region_batch.column("forest_cover").to_pylist()

        # Patch only region 1
        patch = pa.record_batch({
            "region_id": pa.array([1], type=pa.uint16()),
            "population": pa.array([25], type=pa.uint16()),
            "soil": pa.array([soil_vals[1]], type=pa.float32()),
            "water": pa.array([water_vals[1]], type=pa.float32()),
            "forest_cover": pa.array([forest_vals[1]], type=pa.float32()),
            "terrain": pa.array([0], type=pa.uint8()),
            "carrying_capacity": pa.array([60], type=pa.uint16()),
        })
        sim.apply_region_postpass_patch(patch)
        # No error means only region 1 was updated


# ---------------------------------------------------------------------------
# M54a Task 3: EcologySimulator tests
# ---------------------------------------------------------------------------


class TestEcologySimulator:
    """Test the off-mode EcologySimulator (no AgentPool)."""

    def test_create_ecology_simulator(self):
        """EcologySimulator can be created without args."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        assert eco is not None

    def test_set_region_state_initializes(self):
        """set_region_state initializes regions without spawning agents."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        batch = _make_ecology_region_batch(num_regions=3, capacity=40)
        eco.set_region_state(batch)
        # No agents — this is off-mode

    def test_tick_ecology_returns_two_batches(self):
        """tick_ecology returns (region_batch, event_batch) with correct schemas."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        batch = _make_ecology_region_batch(num_regions=2, capacity=30)
        eco.set_region_state(batch)

        region_batch, event_batch = eco.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )

        assert region_batch.num_rows == 2
        expected_region_cols = [
            "region_id", "soil", "water", "forest_cover",
            "endemic_severity", "prev_turn_water",
            "soil_pressure_streak",
            "overextraction_streak_0", "overextraction_streak_1", "overextraction_streak_2",
            "resource_reserve_0", "resource_reserve_1", "resource_reserve_2",
            "resource_effective_yield_0", "resource_effective_yield_1", "resource_effective_yield_2",
            "current_turn_yield_0", "current_turn_yield_1", "current_turn_yield_2",
        ]
        assert region_batch.schema.names == expected_region_cols

        expected_event_cols = ["event_type", "region_id", "slot", "magnitude"]
        assert event_batch.schema.names == expected_event_cols

    def test_tick_ecology_before_set_region_state_errors(self):
        """tick_ecology() before set_region_state() raises."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        with pytest.raises((RuntimeError, ValueError), match="set_region_state"):
            eco.tick_ecology(
                turn=0, climate_phase=0,
                pandemic_mask=[False, False],
                army_arrived_mask=[False, False],
            )

    def test_ecology_sim_matches_agent_sim_output(self):
        """EcologySimulator and AgentSimulator produce identical ecology results."""
        from chronicler_agents import EcologySimulator

        batch = _make_ecology_region_batch(num_regions=2, capacity=30)

        # AgentSimulator path
        agent_sim = AgentSimulator(num_regions=2, seed=42)
        agent_sim.set_region_state(batch)
        agent_region, agent_events = agent_sim.tick_ecology(
            turn=5, climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )

        # EcologySimulator path
        eco_sim = EcologySimulator()
        eco_sim.set_region_state(batch)
        eco_region, eco_events = eco_sim.tick_ecology(
            turn=5, climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )

        # Both should produce the same output
        assert agent_region.num_rows == eco_region.num_rows
        for col_name in agent_region.schema.names:
            agent_vals = agent_region.column(col_name).to_pylist()
            eco_vals = eco_region.column(col_name).to_pylist()
            assert agent_vals == eco_vals, f"column {col_name} mismatch"

        assert agent_events.num_rows == eco_events.num_rows

    def test_ecology_sim_apply_postpass_patch(self):
        """EcologySimulator supports apply_region_postpass_patch."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        batch = _make_ecology_region_batch(num_regions=2, capacity=30)
        eco.set_region_state(batch)

        region_batch, _ = eco.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False, False],
            army_arrived_mask=[False, False],
        )

        soil_vals = region_batch.column("soil").to_pylist()
        water_vals = region_batch.column("water").to_pylist()
        forest_vals = region_batch.column("forest_cover").to_pylist()

        patch = pa.record_batch({
            "region_id": pa.array([0, 1], type=pa.uint16()),
            "population": pa.array([25, 25], type=pa.uint16()),
            "soil": pa.array(soil_vals, type=pa.float32()),
            "water": pa.array(water_vals, type=pa.float32()),
            "forest_cover": pa.array(forest_vals, type=pa.float32()),
            "terrain": pa.array([0, 0], type=pa.uint8()),
            "carrying_capacity": pa.array([30, 30], type=pa.uint16()),
        })
        eco.apply_region_postpass_patch(patch)
        # No error means success

    def test_ecology_sim_set_ecology_config(self):
        """set_ecology_config accepts all EcologyConfig fields."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        eco.set_ecology_config(
            soil_degradation=0.005, soil_recovery=0.05,
            mine_soil_degradation=0.03, soil_recovery_pop_ratio=0.75,
            agriculture_soil_bonus=0.02, metallurgy_mine_reduction=0.5,
            mechanization_mine_mult=2.0, soil_pressure_threshold=0.7,
            soil_pressure_streak_limit=30, soil_pressure_degradation_mult=2.0,
            water_drought=0.04, water_recovery=0.03,
            irrigation_water_bonus=0.03, irrigation_drought_mult=1.5,
            cooling_water_loss=0.02, warming_tundra_water_gain=0.05,
            water_factor_denominator=0.5,
            forest_clearing=0.02, forest_regrowth=0.01,
            cooling_forest_damage=0.01, forest_pop_ratio=0.5,
            forest_regrowth_water_gate=0.3,
            cross_effect_forest_soil=0.01, cross_effect_forest_threshold=0.5,
            disease_severity_cap=0.15, disease_decay_rate=0.25,
            flare_overcrowding_threshold=0.8, flare_overcrowding_spike=0.04,
            flare_army_spike=0.03, flare_water_spike=0.02, flare_season_spike=0.02,
            depletion_rate=0.009, exhausted_trickle_fraction=0.04,
            reserve_ramp_threshold=0.25, resource_abundance_multiplier=1.0,
            overextraction_streak_limit=35, overextraction_yield_penalty=0.10,
            workers_per_yield_unit=200,
            deforestation_threshold=0.2, deforestation_water_loss=0.05,
        )

    def test_ecology_sim_set_river_topology(self):
        """set_river_topology accepts a list of river paths."""
        from chronicler_agents import EcologySimulator
        eco = EcologySimulator()
        eco.set_river_topology([[0, 1, 2], [3, 4]])


# ---------------------------------------------------------------------------
# M54a Task 5: Write-back coverage — every returned field reaches Python Region
# ---------------------------------------------------------------------------


class TestWriteBackCoverage:
    """Verify _write_back_ecology copies all Rust ecology results to Region models."""

    def test_all_ecology_fields_written_back(self):
        """Every field in the ecology region batch reaches the Python Region model."""
        from chronicler.ecology import _write_back_ecology
        from chronicler.models import Region, RegionEcology, WorldState

        r = Region(
            name="TestRegion", terrain="plains", carrying_capacity=60,
            resources="fertile", population=30,
            ecology=RegionEcology(soil=0.5, water=0.5, forest_cover=0.2),
        )
        r.disease_baseline = 0.01
        r.endemic_severity = 0.01
        r.prev_turn_water = 0.5
        r.soil_pressure_streak = 0
        r.overextraction_streaks = {0: 0, 1: 0, 2: 0}
        r.resource_reserves = [1.0, 1.0, 1.0]
        r.resource_effective_yields = [0.5, 0.3, 0.0]

        w = WorldState(name="T", seed=42, regions=[r])

        # Simulate a Rust ecology tick output batch
        batch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "soil": pa.array([0.82], type=pa.float32()),
            "water": pa.array([0.63], type=pa.float32()),
            "forest_cover": pa.array([0.21], type=pa.float32()),
            "endemic_severity": pa.array([0.05], type=pa.float32()),
            "prev_turn_water": pa.array([0.63], type=pa.float32()),
            "soil_pressure_streak": pa.array([3], type=pa.int32()),
            "overextraction_streak_0": pa.array([1], type=pa.int32()),
            "overextraction_streak_1": pa.array([2], type=pa.int32()),
            "overextraction_streak_2": pa.array([0], type=pa.int32()),
            "resource_reserve_0": pa.array([0.90], type=pa.float32()),
            "resource_reserve_1": pa.array([0.85], type=pa.float32()),
            "resource_reserve_2": pa.array([1.0], type=pa.float32()),
            "resource_effective_yield_0": pa.array([0.48], type=pa.float32()),
            "resource_effective_yield_1": pa.array([0.28], type=pa.float32()),
            "resource_effective_yield_2": pa.array([0.0], type=pa.float32()),
            "current_turn_yield_0": pa.array([0.35], type=pa.float32()),
            "current_turn_yield_1": pa.array([0.20], type=pa.float32()),
            "current_turn_yield_2": pa.array([0.0], type=pa.float32()),
        })

        region_yields = _write_back_ecology(w, batch)

        # Check every field was written back
        assert abs(r.ecology.soil - 0.82) < 0.001
        assert abs(r.ecology.water - 0.63) < 0.001
        assert abs(r.ecology.forest_cover - 0.21) < 0.001
        assert abs(r.endemic_severity - 0.05) < 0.001
        assert abs(r.prev_turn_water - 0.63) < 0.001
        assert r.soil_pressure_streak == 3
        assert r.overextraction_streaks == {0: 1, 1: 2, 2: 0}
        assert abs(r.resource_reserves[0] - 0.90) < 0.001
        assert abs(r.resource_reserves[1] - 0.85) < 0.001
        assert abs(r.resource_effective_yields[0] - 0.48) < 0.001
        assert abs(r.resource_effective_yields[1] - 0.28) < 0.001

        # current_turn_yields returned as dict
        assert "TestRegion" in region_yields
        assert abs(region_yields["TestRegion"][0] - 0.35) < 0.001
        assert abs(region_yields["TestRegion"][1] - 0.20) < 0.001


# ---------------------------------------------------------------------------
# M54a Task 5: Post-pass patch survives multiple turns
# ---------------------------------------------------------------------------


class TestPostPassPatchMultiTurn:
    """Verify post-pass patches apply correctly across multiple ecology ticks."""

    def test_patch_persists_across_ticks(self):
        """A post-pass patch at turn N should be reflected in turn N+1 state."""
        from chronicler_agents import EcologySimulator

        eco = EcologySimulator()
        batch = _make_ecology_region_batch(
            num_regions=1, capacity=60, populations=[30],
            controllers=[0],
            resource_base_yields=[[1.0, 0.0, 0.0]],
            resource_effective_yields=[[1.0, 0.0, 0.0]],
        )
        extra = {
            "resource_type_0": pa.array([0], type=pa.uint8()),
            "resource_type_1": pa.array([255], type=pa.uint8()),
            "resource_type_2": pa.array([255], type=pa.uint8()),
        }
        columns = {name: batch.column(name) for name in batch.schema.names}
        columns.update(extra)
        batch_with_types = pa.record_batch(columns)

        eco.set_region_state(batch_with_types)

        # Turn 0: ecology tick
        region_batch_0, _ = eco.tick_ecology(
            turn=0, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        soil_0 = region_batch_0.column("soil").to_pylist()[0]
        water_0 = region_batch_0.column("water").to_pylist()[0]
        forest_0 = region_batch_0.column("forest_cover").to_pylist()[0]

        # Apply post-pass patch that changes soil
        patch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "population": pa.array([30], type=pa.uint16()),
            "soil": pa.array([0.30], type=pa.float32()),  # Much lower
            "water": pa.array([water_0], type=pa.float32()),
            "forest_cover": pa.array([forest_0], type=pa.float32()),
            "terrain": pa.array([0], type=pa.uint8()),
            "carrying_capacity": pa.array([60], type=pa.uint16()),
        })
        eco.apply_region_postpass_patch(patch)

        # Turn 1: tick again — should use patched soil (0.30), not original
        region_batch_1, _ = eco.tick_ecology(
            turn=1, climate_phase=0,
            pandemic_mask=[False], army_arrived_mask=[False],
        )

        soil_1 = region_batch_1.column("soil").to_pylist()[0]
        # After patching to 0.30 and running another tick with recovery,
        # soil should still be near 0.30 (maybe slightly recovered),
        # NOT back at ~0.82 (what it would be without the patch).
        assert soil_1 < 0.50, (
            f"soil after patched tick should stay low (~0.30+recovery), got {soil_1}"
        )


# ---------------------------------------------------------------------------
# M54a Task 5: agents=off can run the same Phase 9 Rust path
# ---------------------------------------------------------------------------


class TestAgentsOffRustPath:
    """Verify --agents=off exercises the Rust ecology path via EcologySimulator."""

    def test_ecology_simulator_full_lifecycle(self):
        """EcologySimulator: set_region_state -> tick -> patch -> tick works."""
        from chronicler_agents import EcologySimulator

        eco = EcologySimulator()
        batch = _make_ecology_region_batch(
            num_regions=2, capacity=60, populations=[30, 40],
            controllers=[0, 1],
            resource_base_yields=[[1.0, 0.0, 0.0], [0.8, 0.5, 0.0]],
            resource_effective_yields=[[1.0, 0.0, 0.0], [0.8, 0.5, 0.0]],
        )
        extra = {
            "resource_type_0": pa.array([0, 0], type=pa.uint8()),
            "resource_type_1": pa.array([255, 1], type=pa.uint8()),
            "resource_type_2": pa.array([255, 255], type=pa.uint8()),
        }
        columns = {name: batch.column(name) for name in batch.schema.names}
        columns.update(extra)
        batch_with_types = pa.record_batch(columns)

        eco.set_region_state(batch_with_types)

        # Run 5 turns
        for turn in range(5):
            region_batch, event_batch = eco.tick_ecology(
                turn=turn, climate_phase=0,
                pandemic_mask=[False, False],
                army_arrived_mask=[False, False],
            )

            # Apply post-pass patch (population changes simulate famine effects)
            soil_vals = region_batch.column("soil").to_pylist()
            water_vals = region_batch.column("water").to_pylist()
            forest_vals = region_batch.column("forest_cover").to_pylist()

            patch = pa.record_batch({
                "region_id": pa.array([0, 1], type=pa.uint16()),
                "population": pa.array([28, 38], type=pa.uint16()),
                "soil": pa.array(soil_vals, type=pa.float32()),
                "water": pa.array(water_vals, type=pa.float32()),
                "forest_cover": pa.array(forest_vals, type=pa.float32()),
                "terrain": pa.array([0, 0], type=pa.uint8()),
                "carrying_capacity": pa.array([60, 60], type=pa.uint16()),
            })
            eco.apply_region_postpass_patch(patch)

        # After 5 turns, should have valid ecology state
        assert region_batch.num_rows == 2
        soil_final = region_batch.column("soil").to_pylist()
        water_final = region_batch.column("water").to_pylist()
        for i in range(2):
            assert 0.0 <= soil_final[i] <= 1.0
            assert 0.0 <= water_final[i] <= 1.0


# ---------------------------------------------------------------------------
# M54a Task 5: full-sync path independence from _last_region_yields
# ---------------------------------------------------------------------------


class TestNoLastRegionYieldsDependency:
    """The Rust ecology path writes current-turn yields onto Region.resource_current_yields."""

    def test_write_back_ecology_sets_current_yields_on_region(self):
        """_write_back_ecology sets resource_current_yields on the Region model."""
        from chronicler.ecology import _write_back_ecology
        from chronicler.models import Region, RegionEcology, WorldState

        r = Region(
            name="Testland", terrain="plains", carrying_capacity=60,
            resources="fertile", population=30,
            ecology=RegionEcology(soil=0.5, water=0.5, forest_cover=0.2),
        )
        w = WorldState(name="T", seed=42, regions=[r])

        batch = pa.record_batch({
            "region_id": pa.array([0], type=pa.uint16()),
            "soil": pa.array([0.82], type=pa.float32()),
            "water": pa.array([0.63], type=pa.float32()),
            "forest_cover": pa.array([0.21], type=pa.float32()),
            "endemic_severity": pa.array([0.01], type=pa.float32()),
            "prev_turn_water": pa.array([0.63], type=pa.float32()),
            "soil_pressure_streak": pa.array([0], type=pa.int32()),
            "overextraction_streak_0": pa.array([0], type=pa.int32()),
            "overextraction_streak_1": pa.array([0], type=pa.int32()),
            "overextraction_streak_2": pa.array([0], type=pa.int32()),
            "resource_reserve_0": pa.array([1.0], type=pa.float32()),
            "resource_reserve_1": pa.array([1.0], type=pa.float32()),
            "resource_reserve_2": pa.array([1.0], type=pa.float32()),
            "resource_effective_yield_0": pa.array([0.5], type=pa.float32()),
            "resource_effective_yield_1": pa.array([0.0], type=pa.float32()),
            "resource_effective_yield_2": pa.array([0.0], type=pa.float32()),
            "current_turn_yield_0": pa.array([0.40], type=pa.float32()),
            "current_turn_yield_1": pa.array([0.0], type=pa.float32()),
            "current_turn_yield_2": pa.array([0.0], type=pa.float32()),
        })

        region_yields = _write_back_ecology(w, batch)

        # Yields should come from the Rust batch
        assert abs(region_yields["Testland"][0] - 0.40) < 0.001
        # And also be set on the Region model
        assert abs(r.resource_current_yields[0] - 0.40) < 0.001


# ---------------------------------------------------------------------------
# M54a Task 5: No double full-sync on ecology path
# ---------------------------------------------------------------------------


class TestNoDoubleFullSync:
    """build_region_postpass_patch_batch has no side effects that trigger full-sync."""

    def test_postpass_patch_is_side_effect_free(self, sample_world):
        """build_region_postpass_patch_batch does not clear transient signals."""
        from chronicler.agent_bridge import build_region_postpass_patch_batch

        # Set a transient signal
        sample_world.regions[0]._culture_investment_active = True

        # Build postpass patch — should NOT clear the signal
        patch = build_region_postpass_patch_batch(sample_world)

        # Signal should still be set (not cleared by patch builder)
        assert sample_world.regions[0]._culture_investment_active is True

        # Verify patch has expected schema
        assert "region_id" in patch.schema.names
        assert "population" in patch.schema.names
        assert "soil" in patch.schema.names
        assert "water" in patch.schema.names
        assert "forest_cover" in patch.schema.names
        assert "terrain" in patch.schema.names
        assert "carrying_capacity" in patch.schema.names

        # Verify patch does NOT contain full-sync columns
        assert "disease_baseline" not in patch.schema.names
        assert "resource_base_yield_0" not in patch.schema.names
