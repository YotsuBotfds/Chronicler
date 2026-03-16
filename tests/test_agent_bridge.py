"""Tests for the Rust agent bridge — round-trip, determinism, integration."""
import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import build_region_batch, TERRAIN_MAP, AgentBridge


def _make_dummy_signals(num_civs=3):
    """Minimal civ-signals batch for tests that don't exercise signal logic."""
    return pa.record_batch({
        "civ_id": pa.array(range(num_civs), type=pa.uint8()),
        "stability": pa.array([50] * num_civs, type=pa.uint8()),
        "is_at_war": pa.array([False] * num_civs, type=pa.bool_()),
        "dominant_faction": pa.array([0] * num_civs, type=pa.uint8()),
        "faction_military": pa.array([0.33] * num_civs, type=pa.float32()),
        "faction_merchant": pa.array([0.33] * num_civs, type=pa.float32()),
        "faction_cultural": pa.array([0.34] * num_civs, type=pa.float32()),
    })


def _make_region_batch(num_regions=3, capacity=60):
    return pa.record_batch({
        "region_id": pa.array(range(num_regions), type=pa.uint16()),
        "terrain": pa.array([0] * num_regions, type=pa.uint8()),
        "carrying_capacity": pa.array([capacity] * num_regions, type=pa.uint16()),
        "population": pa.array([capacity] * num_regions, type=pa.uint16()),
        "soil": pa.array([0.8] * num_regions, type=pa.float32()),
        "water": pa.array([0.6] * num_regions, type=pa.float32()),
        "forest_cover": pa.array([0.3] * num_regions, type=pa.float32()),
    })


class TestPythonRoundTrip:
    """De-risk gate: prove Arrow data crosses the FFI boundary correctly."""

    def test_create_simulator(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        assert sim is not None

    def test_set_region_state_initializes_agents(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=60))
        snap = sim.get_snapshot()
        assert snap.num_rows == 180  # 60 × 3

    def test_snapshot_schema(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=10))
        snap = sim.get_snapshot()
        expected = ["id", "region", "origin_region", "civ_affinity", "occupation",
                    "loyalty", "satisfaction", "skill", "age", "displacement_turn"]
        assert snap.schema.names == expected

    def test_aggregates_population_matches_and_metrics_in_range(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=30))
        agg = sim.get_aggregates()
        total_pop = sum(agg.column("population").to_pylist())
        assert total_pop == sim.get_snapshot().num_rows
        for col_name in ["military", "economy", "culture", "stability"]:
            values = agg.column(col_name).to_pylist()
            assert all(0 <= v <= 100 for v in values)

    def test_tick_before_set_region_state_errors(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        with pytest.raises((RuntimeError, ValueError), match="set_region_state"):
            sim.tick(0, _make_dummy_signals())


class TestTickBehavior:
    """Tests that depend on the real tick implementation. Runnable after Task 12."""

    def test_tick_reduces_population(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=60))
        initial_count = sim.get_snapshot().num_rows
        region_batch = _make_region_batch(num_regions=3, capacity=60)
        for turn in range(10):
            sim.set_region_state(region_batch)
            events = sim.tick(turn, _make_dummy_signals())
        # M26: events RecordBatch is populated (deaths, births, etc.) — just check pop decreased
        assert sim.get_snapshot().num_rows < initial_count

    def test_ages_increment(self):
        sim = AgentSimulator(num_regions=1, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=1, capacity=20))
        region_batch = _make_region_batch(num_regions=1, capacity=20)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn, _make_dummy_signals(num_civs=1))
        ages = sim.get_snapshot().column("age").to_pylist()
        assert all(a == 5 for a in ages)

    def test_region_populations_matches_snapshot(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=40))
        region_batch = _make_region_batch(num_regions=3, capacity=40)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn, _make_dummy_signals())
        snap = sim.get_snapshot()
        region_pops = sim.get_region_populations()
        regions_col = snap.column("region").to_pylist()
        snap_counts = {}
        for r in regions_col:
            snap_counts[r] = snap_counts.get(r, 0) + 1
        for rid, count in zip(region_pops.column("region_id").to_pylist(), region_pops.column("alive_count").to_pylist()):
            assert count == snap_counts.get(rid, 0)


class TestDemographicsOnlyIntegration:
    def test_demographics_only_20_turns(self, sample_world):
        # Seed region populations from carrying_capacity so the bridge has agents to tick
        for region in sample_world.regions:
            if region.controller is not None:
                region.population = region.carrying_capacity
        bridge = AgentBridge(sample_world, mode="demographics-only")
        initial_pops = {r.name: r.population for r in sample_world.regions if r.controller is not None}
        for turn in range(20):
            sample_world.turn = turn
            events = bridge.tick(sample_world)
            assert events == []
            for region in sample_world.regions:
                if region.controller is not None:
                    assert region.population <= int(region.carrying_capacity * 1.2)
        final_pops = {r.name: r.population for r in sample_world.regions if r.controller is not None}
        # M26 has fertility, so population may not strictly decrease.
        # Just verify it stayed bounded (carrying_capacity * 1.2 check above) and didn't explode.
        assert sum(final_pops.values()) < sum(initial_pops.values()) * 2


class TestRegionBatchResourceColumns:
    """M34: Region batch includes resource/season columns."""

    def test_region_batch_has_resource_columns(self, sample_world):
        from chronicler.agent_bridge import build_region_batch
        import pyarrow as pa

        batch = build_region_batch(sample_world)

        # All new column names are present
        assert "resource_type_0" in batch.schema.names
        assert "resource_type_1" in batch.schema.names
        assert "resource_type_2" in batch.schema.names
        assert "resource_yield_0" in batch.schema.names
        assert "resource_yield_1" in batch.schema.names
        assert "resource_yield_2" in batch.schema.names
        assert "resource_reserve_0" in batch.schema.names
        assert "resource_reserve_1" in batch.schema.names
        assert "resource_reserve_2" in batch.schema.names
        assert "season" in batch.schema.names
        assert "season_id" in batch.schema.names

        # Arrow types are correct
        assert batch.schema.field("resource_type_0").type == pa.uint8()
        assert batch.schema.field("resource_type_1").type == pa.uint8()
        assert batch.schema.field("resource_type_2").type == pa.uint8()
        assert batch.schema.field("resource_yield_0").type == pa.float32()
        assert batch.schema.field("resource_yield_1").type == pa.float32()
        assert batch.schema.field("resource_yield_2").type == pa.float32()
        assert batch.schema.field("resource_reserve_0").type == pa.float32()
        assert batch.schema.field("resource_reserve_1").type == pa.float32()
        assert batch.schema.field("resource_reserve_2").type == pa.float32()
        assert batch.schema.field("season").type == pa.uint8()
        assert batch.schema.field("season_id").type == pa.uint8()

        # Row count matches number of regions
        assert batch.num_rows == len(sample_world.regions)

        # season and season_id are consistent with turn=0
        from chronicler.resources import get_season_step, get_season_id
        expected_season = get_season_step(sample_world.turn)
        expected_season_id = get_season_id(sample_world.turn)
        assert batch.column("season").to_pylist() == [expected_season] * batch.num_rows
        assert batch.column("season_id").to_pylist() == [expected_season_id] * batch.num_rows

        # resource_yield_0 defaults to 0.0 when ecology hasn't run
        assert batch.column("resource_yield_0").to_pylist() == [0.0] * batch.num_rows


class TestPythonDeterminism:
    def test_determinism_50_turns(self):
        sim_a = AgentSimulator(num_regions=3, seed=12345)
        sim_b = AgentSimulator(num_regions=3, seed=12345)
        region_batch = _make_region_batch(num_regions=3, capacity=50)
        signals = _make_dummy_signals()
        sim_a.set_region_state(region_batch)
        sim_b.set_region_state(region_batch)
        for turn in range(50):
            sim_a.set_region_state(region_batch)
            sim_b.set_region_state(region_batch)
            sim_a.tick(turn, signals)
            sim_b.tick(turn, signals)
        snap_a = sim_a.get_snapshot()
        snap_b = sim_b.get_snapshot()
        assert snap_a.num_rows == snap_b.num_rows
        for col_name in snap_a.schema.names:
            assert snap_a.column(col_name).to_pylist() == snap_b.column(col_name).to_pylist()
