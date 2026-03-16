"""Tests for the Rust agent bridge — round-trip, determinism, integration."""
import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import build_region_batch, TERRAIN_MAP, AgentBridge


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

    def test_aggregates_population_matches_and_others_zeroed(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=30))
        agg = sim.get_aggregates()
        total_pop = sum(agg.column("population").to_pylist())
        assert total_pop == sim.get_snapshot().num_rows
        for col_name in ["military", "economy", "culture", "stability"]:
            assert all(v == 0 for v in agg.column(col_name).to_pylist())

    def test_tick_before_set_region_state_errors(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        with pytest.raises((RuntimeError, ValueError), match="set_region_state"):
            sim.tick(0)


class TestTickBehavior:
    """Tests that depend on the real tick implementation. Runnable after Task 12."""

    def test_tick_reduces_population(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=60))
        initial_count = sim.get_snapshot().num_rows
        region_batch = _make_region_batch(num_regions=3, capacity=60)
        for turn in range(10):
            sim.set_region_state(region_batch)
            events = sim.tick(turn)
            assert events.num_rows == 0
        assert sim.get_snapshot().num_rows < initial_count

    def test_ages_increment(self):
        sim = AgentSimulator(num_regions=1, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=1, capacity=20))
        region_batch = _make_region_batch(num_regions=1, capacity=20)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn)
        ages = sim.get_snapshot().column("age").to_pylist()
        assert all(a == 5 for a in ages)

    def test_region_populations_matches_snapshot(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=40))
        region_batch = _make_region_batch(num_regions=3, capacity=40)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn)
        snap = sim.get_snapshot()
        region_pops = sim.get_region_populations()
        regions_col = snap.column("region").to_pylist()
        snap_counts = {}
        for r in regions_col:
            snap_counts[r] = snap_counts.get(r, 0) + 1
        for rid, count in zip(region_pops.column("region_id").to_pylist(), region_pops.column("alive_count").to_pylist()):
            assert count == snap_counts.get(rid, 0)


class TestPythonDeterminism:
    def test_determinism_50_turns(self):
        sim_a = AgentSimulator(num_regions=3, seed=12345)
        sim_b = AgentSimulator(num_regions=3, seed=12345)
        region_batch = _make_region_batch(num_regions=3, capacity=50)
        sim_a.set_region_state(region_batch)
        sim_b.set_region_state(region_batch)
        for turn in range(50):
            sim_a.set_region_state(region_batch)
            sim_b.set_region_state(region_batch)
            sim_a.tick(turn)
            sim_b.tick(turn)
        snap_a = sim_a.get_snapshot()
        snap_b = sim_b.get_snapshot()
        assert snap_a.num_rows == snap_b.num_rows
        for col_name in snap_a.schema.names:
            assert snap_a.column(col_name).to_pylist() == snap_b.column(col_name).to_pylist()
