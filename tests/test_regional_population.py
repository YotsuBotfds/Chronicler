"""Independent regional population/epoch and backwards transport contracts."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import pickle
import random
from types import SimpleNamespace as NS

import pyarrow as pa
import pytest

from chronicler import regional_population as R
from chronicler.models import TurnSnapshot
from chronicler.turn_artifacts import TurnObservation

ROOT = Path(__file__).resolve().parents[1]


def _batch(counts, ids=None):
    return pa.record_batch({"region_id": list(range(len(counts))) if ids is None else ids,
                            "alive_count": counts})


def _bridge(counts):
    return NS(_sim=NS(get_region_populations=lambda: _batch(counts)))


def _observation(world, weights=None):
    return TurnObservation(world.turn, world.turn + 1, None, weights,
                           R.capture_population_sources(world))


def _world(make_world, mode="hybrid"):
    world = make_world()
    world.agent_mode = mode
    # A duplicate display name and an unowned populated region must keep their
    # own positions, including a known zero. Civilization caches are unrelated.
    world.regions.append(world.regions[0].model_copy(update={"controller": None, "population": 7}))
    for region, count in zip(world.regions, (11, 0, 7), strict=True):
        region.population = count
    world.civilizations[0].population = 987
    world.turn = 4
    return world


@pytest.mark.parametrize("mode,expected", [
    (None, ["python_region_state"] * 3),
    ("off", ["python_region_state"] * 3),
    ("shadow", ["python_region_state"] * 3),
    ("hybrid", ["hybrid_region_state"] * 3),
    ("demographics-only", ["demographics_clamped_region_state"] * 2 + ["uncontrolled_region_state"]),
])
def test_exact_model_counts_and_distinct_raw_pool_by_mode(make_world, mode, expected):
    world = _world(make_world, mode)
    observation = _observation(world)
    world.turn += 1
    before, rng = world.model_dump_json(), random.getstate()
    value = R.snapshot_fields(world, _bridge([19, 2, 9]), observation)["regional_population"]
    assert value == {"schema_version": 1, "mode": mode or "off", "source_turn": 4,
                     "completed_turn": 5, "timing": "completed_turn", "counts": [11, 0, 7],
                     "sources": expected, "agent_counts": None if mode in (None, "off") else [19, 2, 9],
                     "agent_source": None if mode in (None, "off") else "native_region_alive_count",
                     "food_weights": None}
    assert world.model_dump_json() == before and random.getstate() == rng


def test_off_never_touches_even_an_available_pool(make_world):
    world = _world(make_world, "off")
    class Forbidden:
        def __getattribute__(self, name):
            raise AssertionError("aggregate observation must not read native")
    assert R.snapshot_fields(world, Forbidden(), _observation(world))["regional_population"]["agent_counts"] is None


@pytest.mark.parametrize("batch", [None, pa.record_batch({"wrong": [1]}),
    _batch([3, 4], [0, 0]), _batch([3, 4], [1, 0]), _batch([3, 4], [0, 2]),
    _batch([3]), _batch([3, None]), _batch([3, -4]), _batch([3.0, 4.0]),
    _batch([True, False]), _batch([3, 4], [False, True]),
])
def test_missing_or_malformed_native_counts_are_unavailable(make_world, batch):
    world = make_world(); world.agent_mode = "shadow"
    bridge = NS(_sim=NS(get_region_populations=lambda: batch))
    row = R.snapshot_fields(world, bridge, _observation(world))["regional_population"]
    assert row["agent_counts"] is None and row["agent_source"] is None
    assert row["counts"] == [r.population for r in world.regions]


def test_completed_native_counts_include_empty_regions_without_inference(make_world):
    world = _world(make_world)
    result = R.snapshot_fields(world, _bridge([0, 0, 0]), _observation(world))["regional_population"]
    assert result["agent_counts"] == [0, 0, 0]
    assert R.snapshot_fields(world, None, _observation(world))["regional_population"]["agent_counts"] is None


def test_birth_death_migration_and_conquest_do_not_reweight_the_past(make_world):
    world = _world(make_world, "demographics-only")
    pre = pa.record_batch({"region": [0, 0, 0, 0, 1, 1, 1, 2]})
    weights = R.capture_food_weights(world, pre)
    observation = _observation(world, weights)
    # Native ledger: death in 0, birth in 1, and a move 0 -> 2.
    after = [2, 4, 2]
    # A later political transfer changes control but cannot relabel the earlier
    # demographics writeback or the food denominator's controller identities.
    world.regions[0].controller = world.civilizations[1].name
    world.regions[2].controller = world.civilizations[0].name
    for region, count in zip(world.regions, (2, 4, 7), strict=True):
        region.population = count
    world.turn += 1
    value = R.snapshot_fields(world, _bridge(after), observation)["regional_population"]
    assert value["counts"] == [2, 4, 7] and value["agent_counts"] == after
    assert value["food_weights"] == {"source": "phase2_agent_pool", "source_turn": 4,
        "timing": "phase2_entry", "counts": [4, 3, 1], "controller_ids": [0, 1, None]}
    assert value["sources"][-1] == "uncontrolled_region_state"
    value["food_weights"]["counts"][0] = 900
    assert weights.counts == (4, 3, 1)
    with pytest.raises(FrozenInstanceError):
        weights.source_turn = 99
    with pytest.raises(ValueError, match="food_weights source_turn"):
        replace(observation, food_weights=replace(weights, source_turn=5))


@pytest.mark.parametrize("snapshot", [None, pa.record_batch({"wrong": [0]}),
    pa.record_batch({"region": [None]}), pa.record_batch({"region": [-1]}),
    pa.record_batch({"region": [3]}), pa.record_batch({"region": [0.0]}),
    pa.record_batch({"region": [True]}),
])
def test_unavailable_food_rows_are_not_reconstructed(make_world, snapshot):
    assert R.capture_food_weights(_world(make_world), snapshot) is None


def test_empty_food_pool_is_a_real_zero_observation(make_world):
    world = _world(make_world)
    weights = R.capture_food_weights(world, pa.record_batch({"region": pa.array([], type=pa.uint16())}))
    assert weights.counts == (0, 0, 0) and weights.controller_ids == (0, 1, None)
    assert R.capture_food_weights(_world(make_world, "off"), pa.record_batch({"region": [0]})) is None


def test_food_controller_identity_stays_unknown_for_ambiguous_names(make_world):
    world = _world(make_world)
    world.civilizations[1].name = world.civilizations[0].name
    world.regions[0].controller = world.civilizations[0].name
    weights = R.capture_food_weights(world, pa.record_batch({"region": [0]}))
    assert weights.counts == (1, 0, 0)
    assert weights.controller_ids == (None, None, None)


def test_demographics_writeback_retains_clamp_and_uncontrolled_state(make_world):
    from chronicler.agent_bridge import AgentBridge
    world = _world(make_world, "demographics-only")
    world.regions[0].carrying_capacity = 10
    world.regions[1].carrying_capacity = 10
    bridge = object.__new__(AgentBridge)
    bridge._sim = _bridge([30, 3, 50])._sim
    AgentBridge._apply_demographics_clamp(bridge, world)
    observation = _observation(world)
    row = R.snapshot_fields(world, bridge, observation)["regional_population"]
    assert row["counts"] == [12, 3, 7]
    assert row["agent_counts"] == [30, 3, 50]


def test_phase2_handoff_uses_existing_rows_and_posttick_model_sources(make_world, monkeypatch):
    from chronicler import simulation as sim, economy, relationships
    from chronicler.demand_signals import DemandSignalManager
    from test_turn_artifact_lifecycle import _quiet_phases
    world = make_world(); world.agent_mode = "demographics-only"; world.mutual_aid_enabled = False
    world.regions[1].controller = None
    _quiet_phases(monkeypatch, sim, [])
    monkeypatch.setattr(sim, "phase_action", lambda *a, **k: [])
    monkeypatch.setattr(sim, "run_settlement_tick", lambda *a, **k: [])
    monkeypatch.setattr(economy, "build_economy_region_input_batch", lambda *a: None)
    monkeypatch.setattr(economy, "build_economy_trade_route_batch", lambda *a, **k: None)
    monkeypatch.setattr(economy, "reconstruct_economy_result", lambda *a, **k: NS(treasury_tax={}, imports_by_region={}))
    monkeypatch.setattr(relationships, "compute_belief_data", lambda *a: ({}, {}))
    monkeypatch.setattr(relationships, "form_and_sync_relationships", lambda *a: [])
    pre = pa.record_batch({"region": [0, 0, 1]})
    post = pa.record_batch({"region": [0, 1, 1, 1]})
    calls = []
    native = NS(tick_economy=lambda *a: (), get_snapshot=lambda: post)
    class Bridge:
        _sim = native
        _demand_manager = DemandSignalManager()
        named_agents = {}
        dynasty_registry = None
        rust_owns_formation = False
        ecology_simulator = native
        def get_snapshot(self):
            calls.append("snapshot")
            return pre if len(calls) == 1 else post
        def sync_regions(self, world): pass
        def set_economy_result(self, result): pass
        def tick_agents(self, world, **kwargs): return []
        def read_social_edges(self): return []
    def politics(world, **kwargs):
        world.regions[1].controller = world.civilizations[1].name
        return []
    monkeypatch.setattr(sim, "phase_consequences", politics)
    result = sim.run_turn_result(world, lambda *a: None, lambda *a: "", agent_bridge=Bridge())
    assert result.observation.food_weights.as_dict() == {
        "source": "phase2_agent_pool", "source_turn": 0, "timing": "phase2_entry",
        "counts": [2, 1], "controller_ids": [0, None]}
    assert result.observation.population_sources == ("demographics_clamped_region_state", "uncontrolled_region_state")
    assert result.observation.completed_turn == world.turn == 1
    assert calls == ["snapshot", "snapshot"]  # No redundant pool/snapshot fetch.


def test_static_delta_live_reconnect_pickle_and_legacy_roundtrips(make_world):
    from chronicler.bundle_codec import decode_bundle, encode_bundle
    from chronicler.live_checkpoints import LiveView, turn_message
    from chronicler.snapshot_pruning import SnapshotPruner
    from chronicler.transport import snapshot_from_turn_message
    world = _world(make_world, "shadow")
    field = R.snapshot_fields(world, _bridge([1, 2, 3]), _observation(world))
    snapshot = TurnSnapshot(turn=5, civ_stats={}, region_control={}, relationships={}, **field)
    dumped = snapshot.model_dump(mode="json")
    for version in (4, 5, 6):
        bundle = {"metadata": {"bundle_version": version}, "history": [dumped, deepcopy(dumped)],
                  "world_state": {}, "events_timeline": [], "named_events": []}
        if version == 6:
            bundle = encode_bundle(bundle)
            assert "history_delta" in bundle
        decoded = decode_bundle(json.loads(json.dumps(bundle)))
        assert decoded["history"][0]["regional_population"] == field["regional_population"]
    message = turn_message(snapshot, "", [], [], SnapshotPruner())
    assert snapshot_from_turn_message(message) == dumped
    live = LiveView(); live.record_init({"history": [], "chronicle_entries": {}, "events_timeline": [], "named_events": []})
    live.record_turn(message)
    restored = pickle.loads(pickle.dumps(live))
    assert restored.init_data()["history"][0] == dumped
    assert pickle.loads(pickle.dumps(snapshot)).model_dump(mode="json") == dumped
    legacy = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "regional_population" not in legacy.model_dump(mode="json")
    # The real shared transport fixture exercises validated Batch Lab, init and
    # completion paths in test_historical_parity; legacy omission stays intact.
    old = {"metadata": {"bundle_version": 5}, "history": [legacy.model_dump(mode="json")],
           "world_state": {}, "events_timeline": [], "named_events": []}
    assert "regional_population" not in decode_bundle(old)["history"][0]


def test_exact_source_inverse_preserves_parent_and_rejects_all_unrelated_changes():
    from scripts.testing.regional_population_witness import before_regional_population
    witness = json.loads((ROOT / "tests/fixtures/regional_population_source_inverse.json").read_text())
    assert witness["base"] == "c04b32adef05e54c46f597d9fece9568e719c7c7"
    for path, row in witness["files"].items():
        source = (ROOT / path).read_text()
        projected = before_regional_population(source, path)
        assert hashlib.sha256(projected.encode()).hexdigest() == row["sha256"]
        with pytest.raises(AssertionError):
            before_regional_population(source + "\n# unrelated mutation\n", path)
        with pytest.raises(AssertionError):
            before_regional_population(source.replace("\n", "\r\n"), path)
        for patch in row["patches"]:
            with pytest.raises(AssertionError):
                before_regional_population(source.replace(patch["new"], patch["old"], 1), path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
