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
                    "loyalty", "satisfaction", "skill", "age", "displacement_turn",
                    "boldness", "ambition", "loyalty_trait",
                    "cultural_value_0", "cultural_value_1", "cultural_value_2",
                    "belief", "parent_id", "wealth"]
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


class TestTransientSignalCleanup:
    """M36 regression: transient one-turn signals must clear after build_region_batch."""

    def test_culture_investment_flag_clears_after_read(self, sample_world):
        """M36 sticky flag regression: _culture_investment_active must not persist."""
        # Set the flag on region 0
        sample_world.regions[0]._culture_investment_active = True

        # First batch should see True
        batch1 = build_region_batch(sample_world)
        vals1 = batch1.column("culture_investment_active").to_pylist()
        assert vals1[0] is True

        # Second batch (no new INVEST_CULTURE) should see False
        batch2 = build_region_batch(sample_world)
        vals2 = batch2.column("culture_investment_active").to_pylist()
        assert vals2[0] is False


class TestM48TransientMemorySignals:
    """M48: Per-region transient memory signals clear after build_region_batch."""

    def test_controller_changed_flag_clears_after_read(self, sample_world):
        """_controller_changed_this_turn must not persist across batch builds."""
        sample_world.regions[0]._controller_changed_this_turn = True
        batch1 = build_region_batch(sample_world)
        vals1 = batch1.column("controller_changed_this_turn").to_pylist()
        assert vals1[0] is True
        assert all(v is False for v in vals1[1:])

        batch2 = build_region_batch(sample_world)
        vals2 = batch2.column("controller_changed_this_turn").to_pylist()
        assert vals2[0] is False

    def test_war_won_flag_clears_after_read(self, sample_world):
        """_war_won_this_turn must not persist across batch builds."""
        sample_world.regions[1]._war_won_this_turn = True
        batch1 = build_region_batch(sample_world)
        vals1 = batch1.column("war_won_this_turn").to_pylist()
        assert vals1[1] is True
        assert vals1[0] is False

        batch2 = build_region_batch(sample_world)
        vals2 = batch2.column("war_won_this_turn").to_pylist()
        assert vals2[1] is False

    def test_seceded_flag_clears_after_read(self, sample_world):
        """_seceded_this_turn must not persist across batch builds."""
        sample_world.regions[2]._seceded_this_turn = True
        batch1 = build_region_batch(sample_world)
        vals1 = batch1.column("seceded_this_turn").to_pylist()
        assert vals1[2] is True

        batch2 = build_region_batch(sample_world)
        vals2 = batch2.column("seceded_this_turn").to_pylist()
        assert vals2[2] is False

    def test_all_three_signals_default_false(self, sample_world):
        """When no signals are set, all columns default to False."""
        batch = build_region_batch(sample_world)
        for col_name in ["controller_changed_this_turn", "war_won_this_turn", "seceded_this_turn"]:
            assert col_name in batch.schema.names
            vals = batch.column(col_name).to_pylist()
            assert all(v is False for v in vals), f"{col_name} should default to all False"

    def test_batch_has_correct_arrow_types(self, sample_world):
        """M48 columns must be Boolean Arrow type."""
        import pyarrow as pa
        batch = build_region_batch(sample_world)
        for col_name in ["controller_changed_this_turn", "war_won_this_turn", "seceded_this_turn"]:
            assert batch.schema.field(col_name).type == pa.bool_()

    def test_multiple_signals_on_different_regions(self, sample_world):
        """Multiple signals on different regions are all captured and cleared."""
        sample_world.regions[0]._controller_changed_this_turn = True
        sample_world.regions[0]._war_won_this_turn = True
        sample_world.regions[1]._seceded_this_turn = True
        batch = build_region_batch(sample_world)
        assert batch.column("controller_changed_this_turn").to_pylist()[0] is True
        assert batch.column("war_won_this_turn").to_pylist()[0] is True
        assert batch.column("seceded_this_turn").to_pylist()[1] is True
        # All cleared after
        batch2 = build_region_batch(sample_world)
        for col_name in ["controller_changed_this_turn", "war_won_this_turn", "seceded_this_turn"]:
            assert all(v is False for v in batch2.column(col_name).to_pylist())


class TestDynastyIntegration:
    """M39: Verify dynasty system is wired into AgentBridge."""

    def test_gp_by_agent_id_empty_at_init(self, sample_world):
        """gp_by_agent_id dict starts empty before any promotions."""
        bridge = AgentBridge(sample_world, mode="demographics-only")
        assert bridge.gp_by_agent_id == {}
        assert bridge.named_agents == {}

    def test_gp_by_agent_id_mirrors_named_agents_unit(self):
        """Every named_agents entry must have a corresponding gp_by_agent_id entry.

        Uses direct dict manipulation to verify the structural invariant
        without requiring a full hybrid-mode run (which needs arro3).
        """
        from chronicler.models import GreatPerson
        from chronicler.dynasties import DynastyRegistry

        registry = DynastyRegistry()
        named_agents: dict[int, str] = {}
        gp_by_agent_id: dict[int, GreatPerson] = {}

        # Simulate two promotions: parent then child
        parent = GreatPerson(
            name="Kiran", role="general", trait="bold",
            civilization="Ashara", origin_civilization="Ashara",
            born_turn=5, source="agent", agent_id=100, parent_id=0,
        )
        named_agents[100] = "Kiran"
        gp_by_agent_id[100] = parent
        registry.check_promotion(parent, named_agents, gp_by_agent_id)

        child = GreatPerson(
            name="Tala", role="merchant", trait="shrewd",
            civilization="Ashara", origin_civilization="Ashara",
            born_turn=15, source="agent", agent_id=200, parent_id=100,
        )
        named_agents[200] = "Tala"
        gp_by_agent_id[200] = child
        events = registry.check_promotion(child, named_agents, gp_by_agent_id)

        # Structural invariant: keys match
        assert set(gp_by_agent_id.keys()) == set(named_agents.keys())
        # Every value is a GreatPerson with correct agent_id
        for agent_id, gp in gp_by_agent_id.items():
            assert isinstance(gp, GreatPerson)
            assert gp.agent_id == agent_id
            assert gp.source == "agent"
        # Dynasty was detected
        assert len(events) == 1
        assert events[0].event_type == "dynasty_founded"
        assert child.dynasty_id == parent.dynasty_id

    def test_dynasty_registry_exists_on_bridge(self, sample_world):
        """DynastyRegistry is initialized on AgentBridge."""
        from chronicler.dynasties import DynastyRegistry
        bridge = AgentBridge(sample_world, mode="demographics-only")
        assert isinstance(bridge.dynasty_registry, DynastyRegistry)
        assert bridge.dynasty_registry.dynasties == []


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
