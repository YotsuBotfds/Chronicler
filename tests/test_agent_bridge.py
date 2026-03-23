"""Tests for the Rust agent bridge — round-trip, determinism, integration."""
import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import build_region_batch, TERRAIN_MAP, AgentBridge
from chronicler.models import GreatPerson


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


def _make_region_batch(num_regions=3, capacity=60, populations=None, controllers=None):
    if populations is None:
        populations = [capacity] * num_regions
    columns = {
        "region_id": pa.array(range(num_regions), type=pa.uint16()),
        "terrain": pa.array([0] * num_regions, type=pa.uint8()),
        "carrying_capacity": pa.array([capacity] * num_regions, type=pa.uint16()),
        "population": pa.array(populations, type=pa.uint16()),
        "soil": pa.array([0.8] * num_regions, type=pa.float32()),
        "water": pa.array([0.6] * num_regions, type=pa.float32()),
        "forest_cover": pa.array([0.3] * num_regions, type=pa.float32()),
    }
    if controllers is not None:
        columns["controller_civ"] = pa.array(controllers, type=pa.uint8())
    return pa.record_batch(columns)


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

    def test_set_region_state_honors_population_column(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=60, populations=[12, 0]))
        snap = sim.get_snapshot()
        assert snap.num_rows == 12
        assert set(snap.column("region").to_pylist()) == {0}

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

    def test_aggregates_group_controlled_population_under_controller(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(
            _make_region_batch(
                num_regions=2,
                capacity=12,
                populations=[12, 12],
                controllers=[0, 1],
            )
        )
        snap = sim.get_snapshot()
        for agent_id, region_id in zip(snap.column("id").to_pylist(), snap.column("region").to_pylist()):
            if region_id == 0:
                sim.set_agent_civ(agent_id, 1)

        agg = sim.get_aggregates()
        civ_ids = agg.column("civ_id").to_pylist()
        populations = agg.column("population").to_pylist()

        assert dict(zip(civ_ids, populations)) == {0: 12, 1: 12}

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
            sim.tick(turn, _make_dummy_signals())
        final_count = sim.get_snapshot().num_rows
        # M26 includes both births and deaths; population should evolve, but not
        # explode immediately under a steady repeated region state.
        assert final_count != initial_count
        assert 0 < final_count < initial_count * 2

    def test_ages_increment(self):
        sim = AgentSimulator(num_regions=1, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=1, capacity=20))
        initial = sim.get_snapshot()
        initial_ids = initial.column("id").to_pylist()
        initial_ages = initial.column("age").to_pylist()
        initial_age_by_id = {
            agent_id: age for agent_id, age in zip(initial_ids, initial_ages)
        }
        region_batch = _make_region_batch(num_regions=1, capacity=20)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn, _make_dummy_signals(num_civs=1))
        final = sim.get_snapshot()
        final_ids = final.column("id").to_pylist()
        final_ages = final.column("age").to_pylist()
        survivors_checked = 0
        for agent_id, age in zip(final_ids, final_ages):
            if agent_id not in initial_age_by_id:
                continue
            survivors_checked += 1
            assert age == initial_age_by_id[agent_id] + 5
        assert survivors_checked > 0

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

    def test_write_final_sidecar_snapshot_uses_post_loop_turn(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        recorded_turns = []
        bridge._sidecar = object()
        bridge._write_sidecar_snapshot = lambda world: recorded_turns.append(world.turn)

        sample_world.turn = 500
        bridge.write_final_sidecar_snapshot(sample_world)

        assert recorded_turns == [500]

    def test_write_back_resyncs_regions_and_population_from_controller_truth(self, sample_world):
        class _FakeSim:
            def get_aggregates(self):
                return pa.record_batch({
                    "civ_id": pa.array([0], type=pa.uint16()),
                    "population": pa.array([18], type=pa.uint32()),
                    "military": pa.array([12], type=pa.uint32()),
                    "economy": pa.array([23], type=pa.uint32()),
                    "culture": pa.array([34], type=pa.uint32()),
                    "stability": pa.array([45], type=pa.uint32()),
                })

            def get_region_populations(self):
                return pa.record_batch({
                    "region_id": pa.array([0, 1, 2], type=pa.uint16()),
                    "alive_count": pa.array([7, 11, 0], type=pa.uint32()),
                })

        primary = sample_world.civilizations[0]
        other = sample_world.civilizations[1]
        sample_world.regions[0].controller = primary.name
        sample_world.regions[1].controller = primary.name
        sample_world.regions[2].controller = other.name
        primary.regions = [sample_world.regions[0].name]

        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._sim = _FakeSim()
        bridge._write_back(sample_world)

        assert sample_world.regions[0].population == 7
        assert sample_world.regions[1].population == 11
        assert primary.population == 18
        assert set(primary.regions) == {
            sample_world.regions[0].name,
            sample_world.regions[1].name,
        }
        assert primary.military == 12
        assert primary.economy == 23
        assert primary.culture == 34
        assert primary.stability == 45


class TestSecessionTransitions:
    def test_realign_region_agents_to_civ_moves_only_matching_region_agents(self, sample_world):
        class _Column:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        class _Snapshot:
            def __init__(self, columns):
                self._columns = columns
                self.num_rows = len(columns["id"])

            def column(self, name):
                return _Column(self._columns[name])

        class _FakeSim:
            def __init__(self, columns):
                self._snapshot = _Snapshot(columns)
                self.calls = []

            def get_snapshot(self):
                return self._snapshot

            def set_agent_civ(self, agent_id, new_civ_id):
                self.calls.append((agent_id, new_civ_id))

        bridge = AgentBridge(sample_world, mode="demographics-only")
        fake_sim = _FakeSim({
            "id": [101, 102, 103, 104],
            "region": [0, 0, 1, 0],
            "civ_affinity": [0, 1, 0, 0],
        })
        bridge._sim = fake_sim

        moved = bridge.realign_region_agents_to_civ(
            world=sample_world,
            region_names={sample_world.regions[0].name},
            old_civ_id=0,
            new_civ_id=7,
        )

        assert moved == {101, 104}
        assert sorted(fake_sim.calls) == [(101, 7), (104, 7)]

    def test_apply_secession_transitions_moves_region_agents_to_new_civ(self, sample_world):
        class _Column:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        class _Snapshot:
            def __init__(self, columns):
                self._columns = columns
                self.num_rows = len(columns["id"])

            def column(self, name):
                return _Column(self._columns[name])

        class _FakeSim:
            def __init__(self, columns):
                self._snapshot = _Snapshot(columns)
                self.calls = []

            def get_snapshot(self):
                return self._snapshot

            def set_agent_civ(self, agent_id, new_civ_id):
                self.calls.append((agent_id, new_civ_id))

        old_civ = sample_world.civilizations[0]
        breakaway = sample_world.civilizations[1].model_copy(deep=True)
        breakaway.name = "Breakaway Realm"
        breakaway.great_persons = []

        seceding_region = sample_world.regions[0].name
        gp = GreatPerson(
            name="Asha",
            role="merchant",
            trait="cunning",
            civilization=old_civ.name,
            origin_civilization=old_civ.name,
            born_turn=0,
            region=seceding_region,
            source="agent",
            agent_id=101,
        )
        old_civ.great_persons = [gp]

        bridge = AgentBridge(sample_world, mode="demographics-only")
        fake_sim = _FakeSim({
            "id": [101, 102, 103],
            "region": [0, 0, 1],
            "civ_affinity": [0, 0, 0],
        })
        bridge._sim = fake_sim

        events = bridge.apply_secession_transitions(
            old_civ,
            breakaway,
            [seceding_region],
            new_civ_id=7,
            turn=12,
            world=sample_world,
            old_civ_id=0,
        )

        assert sorted(fake_sim.calls) == [(101, 7), (102, 7)]
        assert gp not in old_civ.great_persons
        assert gp in breakaway.great_persons
        assert gp.civilization == breakaway.name
        assert events[0].event_type == "secession_defection"


class TestPoliticalTransitions:
    def test_apply_restoration_transitions_moves_region_agents_to_restored_civ(self, sample_world):
        class _Column:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        class _Snapshot:
            def __init__(self, columns):
                self._columns = columns
                self.num_rows = len(columns["id"])

            def column(self, name):
                return _Column(self._columns[name])

        class _FakeSim:
            def __init__(self, columns):
                self._snapshot = _Snapshot(columns)
                self.calls = []

            def get_snapshot(self):
                return self._snapshot

            def set_agent_civ(self, agent_id, new_civ_id):
                self.calls.append((agent_id, new_civ_id))

        absorber = sample_world.civilizations[0]
        restored = sample_world.civilizations[1].model_copy(deep=True)
        restored.name = "Restored Realm"
        restored.great_persons = []

        restored_region = sample_world.regions[0].name
        gp = GreatPerson(
            name="Nara",
            role="prophet",
            trait="zealous",
            civilization=absorber.name,
            origin_civilization=absorber.name,
            born_turn=0,
            region=restored_region,
            source="agent",
            agent_id=201,
        )
        absorber.great_persons = [gp]

        bridge = AgentBridge(sample_world, mode="demographics-only")
        fake_sim = _FakeSim({
            "id": [201, 202, 203],
            "region": [0, 0, 1],
            "civ_affinity": [0, 0, 0],
        })
        bridge._sim = fake_sim

        bridge.apply_restoration_transitions(
            absorber,
            restored,
            [restored_region],
            absorber_civ_id=0,
            restored_civ_id=7,
            world=sample_world,
        )

        assert sorted(fake_sim.calls) == [(201, 7), (202, 7)]
        assert gp not in absorber.great_persons
        assert gp in restored.great_persons
        assert gp.civilization == restored.name

    def test_apply_absorption_transitions_moves_region_agents_to_absorber_civ(self, sample_world):
        class _Column:
            def __init__(self, values):
                self._values = values

            def to_pylist(self):
                return list(self._values)

        class _Snapshot:
            def __init__(self, columns):
                self._columns = columns
                self.num_rows = len(columns["id"])

            def column(self, name):
                return _Column(self._columns[name])

        class _FakeSim:
            def __init__(self, columns):
                self._snapshot = _Snapshot(columns)
                self.calls = []

            def get_snapshot(self):
                return self._snapshot

            def set_agent_civ(self, agent_id, new_civ_id):
                self.calls.append((agent_id, new_civ_id))

        losing_civ = sample_world.civilizations[0]
        absorber = sample_world.civilizations[1]
        absorbed_region = sample_world.regions[0].name
        gp = GreatPerson(
            name="Suri",
            role="scientist",
            trait="visionary",
            civilization=losing_civ.name,
            origin_civilization=losing_civ.name,
            born_turn=0,
            region=absorbed_region,
            source="agent",
            agent_id=301,
        )
        losing_civ.great_persons = [gp]

        bridge = AgentBridge(sample_world, mode="demographics-only")
        fake_sim = _FakeSim({
            "id": [301, 302, 303],
            "region": [0, 0, 1],
            "civ_affinity": [0, 0, 0],
        })
        bridge._sim = fake_sim

        bridge.apply_absorption_transitions(
            losing_civ,
            absorber,
            [absorbed_region],
            losing_civ_id=0,
            absorber_civ_id=1,
            world=sample_world,
        )

        assert sorted(fake_sim.calls) == [(301, 1), (302, 1)]
        assert gp not in losing_civ.great_persons
        assert gp in absorber.great_persons
        assert gp.civilization == absorber.name


class TestRegionBatchResourceColumns:
    """M34: Region batch includes resource/season columns."""

    def test_region_batch_has_resource_columns(self, sample_world):
        from chronicler.agent_bridge import build_region_batch
        from chronicler.ecology import _last_region_yields
        import pyarrow as pa

        _last_region_yields.clear()
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

        # resource yields default to 0.0 when the ecology cache is empty
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
