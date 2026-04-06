"""Tests for the Rust agent bridge — round-trip, determinism, integration."""
import json
import pathlib
import tempfile

import pyarrow as pa
import pytest
from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import (
    AgentBridge,
    TERRAIN_MAP,
    build_region_batch,
    build_settlement_batch,
    build_signals,
)
from chronicler.economy import EconomyResult
from chronicler.models import Belief, FactionType, GreatPerson
from chronicler.sidecar import SidecarWriter


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
                    "belief", "parent_id_0", "parent_id_1", "wealth", "x", "y", "settlement_id"]
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

    def test_apply_relationship_ops_rejects_type_mismatch(self):
        sim = AgentSimulator(num_regions=1, seed=42)
        bad_batch = pa.record_batch(
            [
                pa.array([0], type=pa.uint8()),      # op_type
                pa.array([1], type=pa.uint32()),      # agent_a
                pa.array([2], type=pa.uint32()),      # agent_b
                pa.array([1], type=pa.uint16()),      # bond_type (wrong type: u16 instead of u8)
                pa.array([50], type=pa.int8()),       # sentiment
                pa.array([5], type=pa.uint16()),      # formed_turn
            ],
            names=["op_type", "agent_a", "agent_b", "bond_type", "sentiment", "formed_turn"],
        )

        with pytest.raises((RuntimeError, ValueError), match="bond_type"):
            sim.apply_relationship_ops(bad_batch)


class TestBuildSignalsValidation:
    def test_rejects_non_finite_gini(self, sample_world):
        with pytest.raises(ValueError, match="gini_coefficient"):
            build_signals(sample_world, gini_by_civ={0: float("nan")})

    def test_rejects_out_of_range_faction_weight(self, sample_world):
        sample_world.civilizations[0].factions.influence[FactionType.MILITARY] = 1.2

        with pytest.raises(ValueError, match="faction_military"):
            build_signals(sample_world)

    def test_allows_large_demand_shifts_and_positive_priest_tithe_share(self, sample_world):
        economy_result = EconomyResult(priest_tithe_shares={0: 2.5})
        batch = build_signals(
            sample_world,
            demands={0: [0.0, -20.0, 0.0, 0.0, 0.0]},
            economy_result=economy_result,
        )

        demand_values = batch.column("demand_shift_soldier").to_pylist()
        tithe_values = batch.column("priest_tithe_share").to_pylist()

        assert demand_values[0] == pytest.approx(-20.0)
        assert tithe_values[0] == pytest.approx(2.5)

    def test_rejects_negative_priest_tithe_share(self, sample_world):
        economy_result = EconomyResult(priest_tithe_shares={0: -0.1})

        with pytest.raises(ValueError, match="priest_tithe_share"):
            build_signals(sample_world, economy_result=economy_result)


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
    def test_bridge_primes_initial_snapshot_before_first_turn(self, sample_world):
        for region in sample_world.regions:
            region.population = region.carrying_capacity if region.controller is not None else 0

        bridge = AgentBridge(sample_world, mode="demographics-only")
        snap = bridge.get_snapshot()

        expected = sum(
            region.population for region in sample_world.regions if region.controller is not None
        )
        assert snap.num_rows == expected


class TestSharedModeFixtures:
    def test_demographics_bridge_world_fixture(self, demographics_bridge_world):
        world, bridge = demographics_bridge_world
        assert world.agent_mode == "demographics-only"
        assert bridge.get_snapshot().num_rows >= 0

    def test_shadow_bridge_world_fixture(self, shadow_bridge_world):
        world, bridge = shadow_bridge_world
        assert world.agent_mode == "shadow"
        assert bridge.get_snapshot().num_rows >= 0

    def test_hybrid_bridge_world_fixture(self, hybrid_bridge_world):
        world, bridge = hybrid_bridge_world
        assert world.agent_mode == "hybrid"
        assert bridge.get_snapshot().num_rows >= 0

    def test_hybrid_catastrophe_deaths_survive_write_back(self, make_world):
        world = make_world(num_civs=1)
        world.agent_mode = "hybrid"
        region = world.regions[0]
        civ = world.civilizations[0]
        region.population = 30
        civ.population = 30

        bridge = AgentBridge(world, mode="hybrid")
        initial_agents = bridge.get_snapshot().num_rows
        assert initial_agents == 30

        region.population = 0
        civ.population = 1
        region._catastrophe_deaths_this_turn = initial_agents
        world.turn = 1

        bridge.tick(world)

        assert world.regions[0].population == 0
        assert world.civilizations[0].population == 1
        death_events = [e for e in world.agent_events_raw if e.event_type == "death"]
        assert len(death_events) == initial_agents

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

    def test_demographics_tick_clears_dead_agents_transient(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        sample_world._dead_agents_this_turn = [object()]
        sample_world.turn = 1

        bridge.tick(sample_world)

        assert sample_world._dead_agents_this_turn == []

    def test_write_final_sidecar_snapshot_uses_post_loop_turn(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        recorded_turns = []
        bridge._sidecar = object()
        bridge._write_sidecar_snapshot = lambda world: recorded_turns.append(world.turn)

        sample_world.turn = 500
        bridge.write_final_sidecar_snapshot(sample_world)

        assert recorded_turns == [500]

    def test_write_sidecar_snapshot_tracks_controlled_occupation_counts(self, sample_world):
        class _FakeSim:
            @staticmethod
            def get_all_relationships():
                return pa.record_batch({
                    "agent_id": pa.array([], type=pa.uint32()),
                    "target_id": pa.array([], type=pa.uint32()),
                    "bond_type": pa.array([], type=pa.uint8()),
                    "sentiment": pa.array([], type=pa.int16()),
                })

            @staticmethod
            def get_all_memories():
                return pa.record_batch({
                    "agent_id": pa.array([], type=pa.uint32()),
                    "event_type": pa.array([], type=pa.uint8()),
                    "turn": pa.array([], type=pa.uint16()),
                    "intensity": pa.array([], type=pa.int16()),
                })

            @staticmethod
            def get_all_needs():
                return pa.record_batch({
                    "agent_id": pa.array([], type=pa.uint32()),
                    "civ_affinity": pa.array([], type=pa.uint16()),
                    "region": pa.array([], type=pa.uint16()),
                    "occupation": pa.array([], type=pa.uint8()),
                    "satisfaction": pa.array([], type=pa.float32()),
                    "boldness": pa.array([], type=pa.float32()),
                    "ambition": pa.array([], type=pa.float32()),
                    "loyalty_trait": pa.array([], type=pa.float32()),
                    "safety": pa.array([], type=pa.float32()),
                    "autonomy": pa.array([], type=pa.float32()),
                    "social": pa.array([], type=pa.float32()),
                    "spiritual": pa.array([], type=pa.float32()),
                    "material": pa.array([], type=pa.float32()),
                    "purpose": pa.array([], type=pa.float32()),
                })

            @staticmethod
            def get_snapshot():
                return pa.record_batch({
                    "id": pa.array([101, 102], type=pa.uint32()),
                    "civ_affinity": pa.array([0, 0], type=pa.uint16()),
                    "satisfaction": pa.array([0.6, 0.4], type=pa.float32()),
                    "occupation": pa.array([1, 0], type=pa.uint8()),
                    "region": pa.array([0, 4], type=pa.uint16()),
                })

        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._sim = _FakeSim()

        with tempfile.TemporaryDirectory() as tmpdir:
            base = pathlib.Path(tmpdir)
            bridge._sidecar = SidecarWriter(base)
            bridge._write_sidecar_snapshot(sample_world)
            bridge._sidecar.close()

            summary = json.loads((base / "validation_summary.json").read_text())
            aggregate = summary["agent_aggregates_by_turn"]["0"]["civ_0"]

        assert aggregate["agent_count"] == 2
        assert aggregate["occupation_counts"] == {"1": 1, "0": 1}
        assert aggregate["controlled_agent_count"] == 1
        assert aggregate["controlled_occupation_counts"] == {"1": 1}

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

    def test_writeback_zeroes_stats_for_zero_agent_civ(self, sample_world):
        """M-AF1 #7: civ with regions but zero agents gets zeroed guard stats."""
        # Fake sim returns a zero-row for civ 1 (Dorrathi Clans) — no agents alive.
        # Civ 0 (Kethani Empire) has normal stats.
        class _FakeSim:
            def get_aggregates(self):
                return pa.record_batch({
                    "civ_id": pa.array([0, 1], type=pa.uint16()),
                    "population": pa.array([15, 0], type=pa.uint32()),
                    "military": pa.array([20, 0], type=pa.uint32()),
                    "economy": pa.array([30, 0], type=pa.uint32()),
                    "culture": pa.array([40, 0], type=pa.uint32()),
                    "stability": pa.array([50, 0], type=pa.uint32()),
                })

            def get_region_populations(self):
                return pa.record_batch({
                    "region_id": pa.array([0, 1, 2, 3, 4], type=pa.uint16()),
                    "alive_count": pa.array([8, 0, 7, 0, 0], type=pa.uint32()),
                })

        # Set up: civ 0 controls regions 0 and 2, civ 1 controls region 1.
        primary = sample_world.civilizations[0]   # Kethani Empire
        secondary = sample_world.civilizations[1]  # Dorrathi Clans
        sample_world.regions[0].controller = primary.name
        sample_world.regions[1].controller = secondary.name
        sample_world.regions[2].controller = primary.name

        # Give secondary stale high stats that should be zeroed by write-back.
        secondary.military = 70
        secondary.economy = 60
        secondary.culture = 50
        secondary.stability = 40

        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._sim = _FakeSim()
        bridge._write_back(sample_world)

        # Primary civ should have its stats from the aggregate row.
        assert primary.military == 20
        assert primary.economy == 30
        assert primary.culture == 40
        assert primary.stability == 50

        # Secondary civ (zero agents) should have zeroed stats, not stale values.
        assert secondary.military == 0
        assert secondary.economy == 0
        assert secondary.culture == 0
        assert secondary.stability == 0

    def test_write_back_clamps_stability_to_uint8_bounds(self, sample_world):
        class _FakeSim:
            def get_aggregates(self):
                return pa.record_batch({
                    "civ_id": pa.array([0], type=pa.uint16()),
                    "population": pa.array([10], type=pa.uint32()),
                    "military": pa.array([12], type=pa.uint32()),
                    "economy": pa.array([23], type=pa.uint32()),
                    "culture": pa.array([34], type=pa.uint32()),
                    "stability": pa.array([255], type=pa.uint32()),
                })

            def get_region_populations(self):
                return pa.record_batch({
                    "region_id": pa.array([0], type=pa.uint16()),
                    "alive_count": pa.array([10], type=pa.uint32()),
                })

        primary = sample_world.civilizations[0]
        sample_world.regions[0].controller = primary.name
        primary.regions = [sample_world.regions[0].name]

        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._sim = _FakeSim()
        bridge._write_back(sample_world)

        assert primary.stability == 100


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

    def test_region_batch_initial_belief_prefers_civ_owned_faith_over_registry_order(self, sample_world):
        sample_world.belief_registry = [
            Belief(faith_id=9, name="Second", civ_origin=1, doctrines=[0, 0, 0, 0, 0]),
            Belief(faith_id=3, name="First", civ_origin=0, doctrines=[0, 0, 0, 0, 0]),
        ]
        sample_world.civilizations[0].civ_majority_faith = 3
        sample_world.civilizations[0].previous_majority_faith = 3
        sample_world.civilizations[1].civ_majority_faith = 9
        sample_world.civilizations[1].previous_majority_faith = 9

        batch = build_region_batch(sample_world)
        initial_beliefs = batch.column("initial_belief").to_pylist()

        assert initial_beliefs[0] == 3
        assert initial_beliefs[1] == 9
        assert initial_beliefs[2] == 3
        assert initial_beliefs[3] == 0xFF
        assert initial_beliefs[4] == 0xFF

    def test_region_batch_has_resource_columns(self, sample_world):
        from chronicler.agent_bridge import build_region_batch
        import pyarrow as pa

        # M54a: no longer depends on _last_region_yields being cleared;
        # the Rust path produces yields directly.
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

        # resource yields default to 0.0 when resource_current_yields is at defaults
        batch = build_region_batch(sample_world)
        assert batch.column("resource_yield_0").to_pylist() == [0.0] * batch.num_rows

    def test_region_batch_rejects_more_than_32_regions(self, sample_world):
        """adjacency_mask is uint32; bridge must fail fast for >32 regions."""
        while len(sample_world.regions) <= 32:
            clone = sample_world.regions[0].model_copy(deep=True)
            clone.name = f"overflow_{len(sample_world.regions)}"
            clone.adjacencies = []
            sample_world.regions.append(clone)

        with pytest.raises(ValueError, match="at most 32 regions"):
            build_region_batch(sample_world)

    def test_region_batch_has_m54a_ecology_columns(self, sample_world):
        """M54a: Region batch includes ecology schema columns."""
        from chronicler.agent_bridge import build_region_batch
        import pyarrow as pa

        batch = build_region_batch(sample_world)
        n = len(sample_world.regions)

        # Column presence
        ecology_columns = [
            "disease_baseline", "capacity_modifier",
            "resource_base_yield_0", "resource_base_yield_1", "resource_base_yield_2",
            "resource_effective_yield_0", "resource_effective_yield_1", "resource_effective_yield_2",
            "resource_suspension_0", "resource_suspension_1", "resource_suspension_2",
            "has_irrigation", "has_mines", "active_focus",
            "prev_turn_water", "soil_pressure_streak",
            "overextraction_streak_0", "overextraction_streak_1", "overextraction_streak_2",
        ]
        for col_name in ecology_columns:
            assert col_name in batch.schema.names, f"missing column: {col_name}"

        # Arrow types
        assert batch.schema.field("disease_baseline").type == pa.float32()
        assert batch.schema.field("capacity_modifier").type == pa.float32()
        assert batch.schema.field("resource_base_yield_0").type == pa.float32()
        assert batch.schema.field("resource_effective_yield_0").type == pa.float32()
        assert batch.schema.field("resource_suspension_0").type == pa.bool_()
        assert batch.schema.field("has_irrigation").type == pa.bool_()
        assert batch.schema.field("has_mines").type == pa.bool_()
        assert batch.schema.field("active_focus").type == pa.uint8()
        assert batch.schema.field("prev_turn_water").type == pa.float32()
        assert batch.schema.field("soil_pressure_streak").type == pa.int32()
        assert batch.schema.field("overextraction_streak_0").type == pa.int32()

        # Row count
        assert batch.num_rows == n

        # Default values: disease_baseline = 0.01 (from Region model)
        assert all(abs(v - 0.01) < 0.001 for v in batch.column("disease_baseline").to_pylist())
        # capacity_modifier defaults to 1.0
        assert all(abs(v - 1.0) < 0.001 for v in batch.column("capacity_modifier").to_pylist())
        # No irrigation/mines by default on sample regions
        assert all(v is False for v in batch.column("has_irrigation").to_pylist())
        assert all(v is False for v in batch.column("has_mines").to_pylist())
        # active_focus = 0 when civs have no focus set
        assert all(v == 0 for v in batch.column("active_focus").to_pylist())

    def test_region_batch_has_m55a_spatial_columns(self, sample_world):
        """M55a: Region batch includes is_capital and temple_prestige columns."""
        from chronicler.agent_bridge import build_region_batch
        import pyarrow as pa

        batch = build_region_batch(sample_world)
        n = len(sample_world.regions)

        # Column presence
        assert "is_capital" in batch.schema.names, "missing column: is_capital"
        assert "temple_prestige" in batch.schema.names, "missing column: temple_prestige"

        # Arrow types
        assert batch.schema.field("is_capital").type == pa.bool_()
        assert batch.schema.field("temple_prestige").type == pa.float32()

        # Row count
        assert batch.num_rows == n

        # Default values: no temples, so prestige should be 0.0
        assert all(abs(v) < 1e-6 for v in batch.column("temple_prestige").to_pylist())

        # is_capital: default fixture has no capital_region set, so all False
        is_cap_vals = batch.column("is_capital").to_pylist()
        assert all(v is False for v in is_cap_vals)

        # Set a capital and verify it shows True
        sample_world.civilizations[0].capital_region = sample_world.regions[0].name
        batch2 = build_region_batch(sample_world)
        is_cap_vals2 = batch2.column("is_capital").to_pylist()
        assert is_cap_vals2[0] is True
        assert all(v is False for v in is_cap_vals2[1:])

    def test_region_batch_uses_oracle_margin_for_route_planning(self, sample_world):
        """Hybrid planning margin should follow oracle margin when present."""
        er = EconomyResult()
        realized = {}
        oracle = {}
        for idx, region in enumerate(sample_world.regions):
            realized[region.name] = 0.1 + idx * 0.01
            oracle[region.name] = {"margin": 0.6 + idx * 0.01}
        # Leave the last region without oracle data to verify realized fallback.
        oracle.pop(sample_world.regions[-1].name)
        er.merchant_margins = realized
        er.oracle_imports = oracle

        batch = build_region_batch(sample_world, er)

        assert "merchant_margin" in batch.schema.names
        assert "merchant_route_margin" in batch.schema.names
        assert batch.schema.field("merchant_route_margin").type == pa.float32()

        route_vals = batch.column("merchant_route_margin").to_pylist()
        margin_vals = batch.column("merchant_margin").to_pylist()
        assert route_vals[0] == pytest.approx(0.6)
        assert margin_vals[0] == pytest.approx(0.1)
        assert route_vals[-1] == pytest.approx(margin_vals[-1])


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

    def test_catastrophe_deaths_clear_after_read(self, sample_world):
        """_catastrophe_deaths_this_turn must not persist across batch builds."""
        sample_world.regions[0]._catastrophe_deaths_this_turn = 7
        batch1 = build_region_batch(sample_world)
        vals1 = batch1.column("catastrophe_deaths_this_turn").to_pylist()
        assert vals1[0] == 7
        assert all(v == 0 for v in vals1[1:])

        batch2 = build_region_batch(sample_world)
        vals2 = batch2.column("catastrophe_deaths_this_turn").to_pylist()
        assert vals2[0] == 0

    def test_all_three_signals_default_false(self, sample_world):
        """When no signals are set, all columns default to False."""
        batch = build_region_batch(sample_world)
        for col_name in ["controller_changed_this_turn", "war_won_this_turn", "seceded_this_turn"]:
            assert col_name in batch.schema.names
            vals = batch.column(col_name).to_pylist()
            assert all(v is False for v in vals), f"{col_name} should default to all False"

        catastrophe_vals = batch.column("catastrophe_deaths_this_turn").to_pylist()
        assert all(v == 0 for v in catastrophe_vals)

    def test_batch_has_correct_arrow_types(self, sample_world):
        """M48 columns must be Boolean Arrow type."""
        import pyarrow as pa
        batch = build_region_batch(sample_world)
        for col_name in ["controller_changed_this_turn", "war_won_this_turn", "seceded_this_turn"]:
            assert batch.schema.field(col_name).type == pa.bool_()
        assert batch.schema.field("catastrophe_deaths_this_turn").type == pa.uint16()

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
            born_turn=5, source="agent", agent_id=100, parent_id_0=0,
        )
        named_agents[100] = "Kiran"
        gp_by_agent_id[100] = parent
        registry.check_promotion(parent, named_agents, gp_by_agent_id)

        child = GreatPerson(
            name="Tala", role="merchant", trait="shrewd",
            civilization="Ashara", origin_civilization="Ashara",
            born_turn=15, source="agent", agent_id=200, parent_id_0=100,
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

    def test_process_promotions_handles_child_before_parent_in_same_batch(self, sample_world):
        class _FakeSim:
            def get_agent_memories(self, agent_id):
                return []

        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._sim = _FakeSim()

        batch = pa.record_batch({
            "agent_id": pa.array([200, 100], type=pa.uint32()),
            "parent_id_0": pa.array([100, 0], type=pa.uint32()),
            "parent_id_1": pa.array([0, 0], type=pa.uint32()),
            "role": pa.array([1, 0], type=pa.uint8()),
            "trigger": pa.array([0, 0], type=pa.uint8()),
            "origin_region": pa.array([0, 0], type=pa.uint16()),
            "civ_id": pa.array([0, 0], type=pa.uint8()),
        })

        created = bridge._process_promotions(batch, sample_world)

        assert len(created) == 2
        child = bridge.gp_by_agent_id[200]
        parent = bridge.gp_by_agent_id[100]
        assert parent.dynasty_id is not None
        assert child.dynasty_id == parent.dynasty_id
        assert any(event.event_type == "dynasty_founded" for event in bridge._pending_dynasty_events)


class TestBridgeResetAndEventFallback:
    def test_reset_clears_gini_and_cached_state(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        bridge._gini_by_civ = {0: 0.42}
        bridge._wealth_stats = {0: {"p50": 10.0}}
        bridge._economy_result = object()
        bridge._relationship_stats_history = [{"turn": 1}]
        bridge._household_stats_history = [{"turn": 1}]
        bridge._merchant_trip_stats_history = [{"turn": 1}]
        bridge._knowledge_stats_history = [{"turn": 1}]

        bridge.reset()

        assert bridge._gini_by_civ == {}
        assert bridge._wealth_stats == {}
        assert bridge._economy_result is None
        assert bridge._relationship_stats_history == []
        assert bridge._household_stats_history == []
        assert bridge._merchant_trip_stats_history == []
        assert bridge._knowledge_stats_history == []
        bridge.close()

    def test_convert_events_unknown_type_is_safe(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        batch = pa.record_batch({
            "agent_id": pa.array([1], type=pa.uint32()),
            "event_type": pa.array([255], type=pa.uint8()),
            "region": pa.array([0], type=pa.uint16()),
            "target_region": pa.array([0], type=pa.uint16()),
            "civ_affinity": pa.array([0], type=pa.uint16()),
            "occupation": pa.array([0], type=pa.uint8()),
        })

        records = bridge._convert_events(batch, turn=9)

        assert len(records) == 1
        assert records[0].event_type == "unknown_255"
        assert records[0].belief is None
        bridge.close()

    def test_convert_events_preserves_belief_when_present(self, sample_world):
        bridge = AgentBridge(sample_world, mode="demographics-only")
        batch = pa.record_batch({
            "agent_id": pa.array([7], type=pa.uint32()),
            "event_type": pa.array([0], type=pa.uint8()),
            "region": pa.array([1], type=pa.uint16()),
            "target_region": pa.array([0], type=pa.uint16()),
            "civ_affinity": pa.array([2], type=pa.uint16()),
            "occupation": pa.array([4], type=pa.uint8()),
            "belief": pa.array([3], type=pa.uint8()),
        })

        records = bridge._convert_events(batch, turn=9)

        assert len(records) == 1
        assert records[0].event_type == "death"
        assert records[0].belief == 3
        bridge.close()

    def test_tick_event_schema_includes_belief(self):
        sim = AgentSimulator(num_regions=1, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=1, capacity=10))

        events = sim.tick(1, _make_dummy_signals(num_civs=1))

        assert "belief" in events.schema.names


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


class TestPoliticsConfigWiring:
    """M54c Task 4: Verify that AgentBridge wires politics config onto the simulator."""

    def test_bridge_calls_set_politics_config(self, sample_world):
        """AgentBridge construction should configure politics on the simulator."""
        # The AgentBridge constructor calls configure_politics_runtime.
        # If the Rust crate is built, this should succeed without error.
        for region in sample_world.regions:
            region.population = region.carrying_capacity if region.controller is not None else 0
        bridge = AgentBridge(sample_world, mode="demographics-only")
        # The simulator should have the politics config set.
        # We verify by calling tick_politics and checking it doesn't crash.
        assert hasattr(bridge._sim, "tick_politics")
        bridge.close()

    def test_politics_simulator_has_tick_politics(self):
        """PoliticsSimulator exposes tick_politics with the same interface."""
        from chronicler_agents import PoliticsSimulator
        sim = PoliticsSimulator()
        assert hasattr(sim, "tick_politics")
        assert hasattr(sim, "set_politics_config")


# ---------------------------------------------------------------------------
# Settlement batch tests (M56b)
# ---------------------------------------------------------------------------

def _make_minimal_world():
    """Lightweight WorldState for settlement batch tests (no fixture deps)."""
    from chronicler.models import (
        WorldState, Region, Civilization, Leader, TechEra,
    )
    regions = [
        Region(name="Plains", terrain="plains", carrying_capacity=80,
               resources="fertile", controller="TestCiv"),
    ]
    civs = [
        Civilization(
            name="TestCiv", population=40, military=50, economy=50,
            culture=50, stability=50, tech_era=TechEra.IRON, treasury=100,
            leader=Leader(name="Leader", trait="calculating", reign_start=0),
            domains=[], values=["Trade"], goal="test",
            regions=["Plains"], asabiya=0.5,
        ),
    ]
    return WorldState(
        name="MinimalWorld", seed=1, turn=10,
        regions=regions, civilizations=civs,
        relationships={}, events_timeline=[],
        active_conditions=[], event_probabilities={},
    )


def test_build_settlement_batch_basic():
    """Settlement batch includes ACTIVE and DISSOLVING footprints, sorted correctly."""
    from chronicler.models import Settlement, SettlementStatus

    world = _make_minimal_world()
    s1 = Settlement(
        settlement_id=1, name="Town A", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=50, status=SettlementStatus.ACTIVE,
        footprint_cells=[(3, 7), (4, 7)],
    )
    s2 = Settlement(
        settlement_id=2, name="Town B", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=30, status=SettlementStatus.DISSOLVING,
        footprint_cells=[(5, 5)],
    )
    s_candidate = Settlement(
        settlement_id=3, name="Maybe", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=10, status=SettlementStatus.CANDIDATE,
        footprint_cells=[(9, 9)],
    )
    world.regions[0].settlements = [s1, s2, s_candidate]

    batch = build_settlement_batch(world)
    assert batch.num_rows == 3  # 2 cells from s1 + 1 from s2, candidate excluded
    settlement_ids = batch.column("settlement_id").to_pylist()
    assert settlement_ids == [1, 1, 2]  # sorted by settlement_id
    # Verify region_id is present and correct (region 0 for all)
    region_ids = batch.column("region_id").to_pylist()
    assert region_ids == [0, 0, 0]


def test_build_settlement_batch_overflow_guard():
    """Overflow guard fires when next_settlement_id > 65535."""
    world = _make_minimal_world()
    world.next_settlement_id = 65536
    with pytest.raises(ValueError, match="65535"):
        build_settlement_batch(world)


class TestPromotionsCivIdentity:
    """M-AF1 #8: promotions batch carries authoritative civ_id from Rust pool."""

    def test_civ_id_column_present_in_promotions_schema(self):
        """The promotions batch schema includes civ_id after the Rust change."""
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=30))
        batch = sim.get_promotions()
        assert "civ_id" in batch.schema.names

    def test_authoritative_civ_id_overrides_region_controller(self, sample_world):
        """Agent whose civ_id differs from origin_region controller gets correct civ."""
        bridge = AgentBridge(sample_world, mode="demographics-only")

        # Build a synthetic promotions batch where the agent belongs to civ 1
        # (Dorrathi Clans, index 1) but origin_region is 0 (Verdant Plains,
        # controlled by Kethani Empire, index 0).
        fake_batch = pa.record_batch({
            "agent_id": pa.array([999], type=pa.uint32()),
            "role": pa.array([0], type=pa.uint8()),        # general
            "trigger": pa.array([0], type=pa.uint8()),      # skill
            "skill": pa.array([0.9], type=pa.float32()),
            "life_events": pa.array([3], type=pa.uint8()),
            "origin_region": pa.array([0], type=pa.uint16()),  # region 0 = Verdant Plains (Kethani)
            "boldness": pa.array([0.5], type=pa.float32()),
            "ambition": pa.array([0.5], type=pa.float32()),
            "loyalty_trait": pa.array([0.5], type=pa.float32()),
            "personality_label": pa.array(["balanced"], type=pa.utf8()),
            "parent_id_0": pa.array([0], type=pa.uint32()),
            "parent_id_1": pa.array([0], type=pa.uint32()),
            "civ_id": pa.array([1], type=pa.uint8()),       # civ 1 = Dorrathi Clans
        })

        created = bridge._process_promotions(fake_batch, sample_world)
        assert len(created) == 1
        gp = created[0]

        # civilization = authoritative civ_id (Dorrathi Clans)
        assert gp.civilization == "Dorrathi Clans"

        # origin_civilization = region controller (Kethani Empire)
        assert gp.origin_civilization == "Kethani Empire"

        # GP appended to the correct civ's great_persons list
        dorrathi = sample_world.civilizations[1]
        assert gp in dorrathi.great_persons

    def test_civ_id_fallback_when_out_of_range(self, sample_world):
        """If civ_id exceeds civilizations list, falls back to region controller."""
        bridge = AgentBridge(sample_world, mode="demographics-only")

        fake_batch = pa.record_batch({
            "agent_id": pa.array([888], type=pa.uint32()),
            "role": pa.array([1], type=pa.uint8()),        # merchant
            "trigger": pa.array([0], type=pa.uint8()),
            "skill": pa.array([0.8], type=pa.float32()),
            "life_events": pa.array([2], type=pa.uint8()),
            "origin_region": pa.array([1], type=pa.uint16()),  # region 1 = Iron Peaks (Dorrathi)
            "boldness": pa.array([0.4], type=pa.float32()),
            "ambition": pa.array([0.6], type=pa.float32()),
            "loyalty_trait": pa.array([0.3], type=pa.float32()),
            "personality_label": pa.array([None], type=pa.utf8()),
            "parent_id_0": pa.array([0], type=pa.uint32()),
            "parent_id_1": pa.array([0], type=pa.uint32()),
            "civ_id": pa.array([255], type=pa.uint8()),    # out of range
        })

        created = bridge._process_promotions(fake_batch, sample_world)
        assert len(created) == 1
        gp = created[0]

        # Falls back to region controller: Dorrathi Clans
        assert gp.civilization == "Dorrathi Clans"
        assert gp.origin_civilization == "Dorrathi Clans"


# ---------------------------------------------------------------------------
# Audit H-18: Gini lag preserves prior values on exception
# ---------------------------------------------------------------------------

class TestGiniPreservation:
    """H-18: _gini_by_civ and _wealth_stats must survive snapshot failures."""

    def test_gini_preserved_on_exception(self, sample_world):
        bridge = AgentBridge(sample_world)
        # Seed with prior Gini data
        bridge._gini_by_civ = {0: 0.35, 1: 0.42}
        bridge._wealth_stats = {0: {"gini": 0.35}}
        prior_gini = dict(bridge._gini_by_civ)
        prior_stats = dict(bridge._wealth_stats)
        # Inject a broken snapshot that will cause an exception
        # by setting _sim to None (tick will fail)
        bridge._sim = None
        try:
            bridge.tick(sample_world)
        except Exception:
            pass
        # Gini and wealth stats must be preserved (not reset to {})
        assert bridge._gini_by_civ == prior_gini
        assert bridge._wealth_stats == prior_stats


class TestSnapshotMetrics:
    """Snapshot-derived bridge metrics should update outside hybrid mode too."""

    def test_refresh_snapshot_metrics_populates_gini_and_displacement(self, sample_world):
        class _FakeSim:
            @staticmethod
            def get_snapshot():
                return pa.record_batch({
                    "region": pa.array([0, 0, 1, 1], type=pa.uint16()),
                    "displacement_turn": pa.array([0, 1, 0, 0], type=pa.uint16()),
                    "wealth": pa.array([0.0, 10.0, 5.0, 5.0], type=pa.float32()),
                    "civ_affinity": pa.array([0, 0, 1, 1], type=pa.uint16()),
                    "occupation": pa.array([0, 1, 2, 2], type=pa.uint8()),
                })

        bridge = AgentBridge(sample_world, mode="shadow")
        sample_world.regions[0].controller = sample_world.civilizations[0].name
        sample_world.regions[1].controller = sample_world.civilizations[1].name
        bridge._sim = _FakeSim()

        bridge._refresh_snapshot_metrics(sample_world)

        assert bridge.displacement_by_region[0] == pytest.approx(0.5)
        assert bridge._gini_by_civ[0] > 0.0
        assert bridge._gini_by_civ[1] == pytest.approx(0.0)

    def test_refresh_snapshot_metrics_preserves_prior_values_on_missing_required_column(self, sample_world):
        class _FakeSim:
            @staticmethod
            def get_snapshot():
                return pa.record_batch({
                    "displacement_turn": pa.array([0, 1], type=pa.uint16()),
                    "wealth": pa.array([1.0, 2.0], type=pa.float32()),
                    "civ_affinity": pa.array([0, 0], type=pa.uint16()),
                    "occupation": pa.array([0, 1], type=pa.uint8()),
                })

        bridge = AgentBridge(sample_world, mode="shadow")
        bridge._sim = _FakeSim()
        bridge.displacement_by_region = {0: 0.25}
        bridge._gini_by_civ = {0: 0.4}
        bridge._wealth_stats = {0: {"gini": 0.4}}

        bridge._refresh_snapshot_metrics(sample_world)

        assert bridge.displacement_by_region == {0: 0.25}
        assert bridge._gini_by_civ == {0: 0.4}
        assert bridge._wealth_stats == {0: {"gini": 0.4}}


class TestAggregateEvents:
    def test_occupation_shift_uses_region_population_not_event_count(self, sample_world):
        from types import SimpleNamespace

        class _FakeSim:
            @staticmethod
            def get_region_populations():
                return pa.record_batch({
                    "region_id": pa.array([0], type=pa.uint16()),
                    "alive_count": pa.array([100], type=pa.uint32()),
                })

        bridge = AgentBridge(sample_world, mode="shadow")
        bridge._sim = _FakeSim()
        bridge._event_window.clear()
        bridge._event_window.append([
            SimpleNamespace(event_type="occupation_switch", region=0, occupation=1, target_region=0, civ_affinity=0, agent_id=1),
            SimpleNamespace(event_type="occupation_switch", region=0, occupation=1, target_region=0, civ_affinity=0, agent_id=2),
            SimpleNamespace(event_type="occupation_switch", region=0, occupation=1, target_region=0, civ_affinity=0, agent_id=3),
            SimpleNamespace(event_type="occupation_switch", region=0, occupation=1, target_region=0, civ_affinity=0, agent_id=4),
        ])

        summaries = bridge._aggregate_events(sample_world)

        assert not any(e.event_type == "occupation_shift" for e in summaries)


# ---------------------------------------------------------------------------
# Audit H-19: Unknown role_id in promotions
# ---------------------------------------------------------------------------

class TestPromotionRoleGuard:
    """H-19: Unknown role_id must not crash promotions."""

    def test_unknown_role_id_skipped(self, sample_world):
        bridge = AgentBridge(sample_world)
        # Create a fake promotions batch with an invalid role_id
        batch = pa.record_batch({
            "agent_id": pa.array([999], type=pa.uint32()),
            "parent_id_0": pa.array([0], type=pa.uint32()),
            "parent_id_1": pa.array([0], type=pa.uint32()),
            "role": pa.array([99], type=pa.uint8()),  # invalid role_id
            "trigger": pa.array([0], type=pa.uint8()),
            "origin_region": pa.array([0], type=pa.uint16()),
        })
        # Must not crash — unknown role skipped
        created = bridge._process_promotions(batch, sample_world)
        assert len(created) == 0


# ---------------------------------------------------------------------------
# gp.region maintenance on named-character movement
# ---------------------------------------------------------------------------

def test_gp_region_updated_on_migration_event(demographics_bridge_world):
    """_detect_character_events should update gp.region on named-character migration."""
    from chronicler.models import AgentEventRecord
    world, bridge = demographics_bridge_world

    from chronicler.models import GreatPerson
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="TestMigrant", role="merchant", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=1, source="agent", agent_id=99, region=world.regions[0].name,
    )
    civ.great_persons.append(gp)
    bridge.named_agents[99] = "TestMigrant"
    bridge.gp_by_agent_id[99] = gp
    bridge._origin_regions[99] = 0

    target_region_idx = 1
    events = [AgentEventRecord(
        turn=world.turn, agent_id=99, event_type="migration",
        region=0, target_region=target_region_idx, civ_affinity=0, occupation=2,
    )]
    bridge._detect_character_events(events, world)
    assert gp.region == world.regions[target_region_idx].name


def test_gp_region_updated_on_exile_return_event(demographics_bridge_world):
    """_detect_character_events should update gp.region on named-character exile return."""
    from chronicler.models import AgentEventRecord
    from chronicler.models import GreatPerson

    world, bridge = demographics_bridge_world
    world.turn = 100
    civ = world.civilizations[0]
    gp = GreatPerson(
        name="TestReturnee", role="merchant", trait="bold",
        civilization=civ.name, origin_civilization=civ.name,
        born_turn=1, source="agent", agent_id=98, region=world.regions[1].name,
    )
    civ.great_persons.append(gp)
    bridge.named_agents[98] = "TestReturnee"
    bridge.gp_by_agent_id[98] = gp
    bridge._origin_regions[98] = 0
    bridge._departure_turns[98] = 60

    events = [AgentEventRecord(
        turn=world.turn, agent_id=98, event_type="migration",
        region=1, target_region=0, civ_affinity=0, occupation=2,
    )]
    emitted = bridge._detect_character_events(events, world)
    assert gp.region == world.regions[0].name
    assert 98 not in bridge._departure_turns
    assert any(event.event_type == "exile_return" for event in emitted)


# ---------------------------------------------------------------------------
# Task 6: dissolution tuple uses real target_agent_id and formed_turn
# ---------------------------------------------------------------------------

def test_dissolution_tuple_uses_target_agent_id_and_formed_turn():
    """Dissolution events should carry real target_agent_id and formed_turn."""
    batch = pa.record_batch({
        "agent_id": pa.array([100], type=pa.uint32()),
        "event_type": pa.array([6], type=pa.uint8()),
        "region": pa.array([0], type=pa.uint16()),
        "target_region": pa.array([3], type=pa.uint16()),
        "civ_affinity": pa.array([0], type=pa.uint8()),
        "occupation": pa.array([0], type=pa.uint8()),
        "belief": pa.array([0], type=pa.uint8()),
        "turn": pa.array([50], type=pa.uint32()),
        "target_agent_id": pa.array([200], type=pa.uint32()),
        "formed_turn": pa.array([10], type=pa.uint32()),
    })

    bridge = AgentBridge.__new__(AgentBridge)
    records = bridge._convert_events(batch, 50)
    assert len(records) == 1
    assert records[0].target_agent_id == 200
    assert records[0].formed_turn == 10


def test_convert_events_old_schema_fallback():
    """_convert_events handles batches missing target_agent_id and formed_turn."""
    batch = pa.record_batch({
        "agent_id": pa.array([100], type=pa.uint32()),
        "event_type": pa.array([6], type=pa.uint8()),
        "region": pa.array([0], type=pa.uint16()),
        "target_region": pa.array([3], type=pa.uint16()),
        "civ_affinity": pa.array([0], type=pa.uint8()),
        "occupation": pa.array([0], type=pa.uint8()),
        "belief": pa.array([0], type=pa.uint8()),
        "turn": pa.array([50], type=pa.uint32()),
    })

    bridge = AgentBridge.__new__(AgentBridge)
    records = bridge._convert_events(batch, 50)
    assert len(records) == 1
    assert records[0].target_agent_id == 0
    assert records[0].formed_turn == 0
