"""Integrated A01 coordinator lifecycle and explicit handoff checks."""
from __future__ import annotations

from dataclasses import dataclass, field
import gc
import importlib
import inspect
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType, ModuleType, SimpleNamespace
import weakref

import pyarrow as pa
import pytest

BASE = "2ab3b4814abb665c7b3d5c255152cf5767bbf25a"


@pytest.fixture
def api():
    """Use the integrated production interfaces without dependency stand-ins."""
    return importlib.import_module("chronicler.turn_artifacts")


def _rows(api, batch, turn=0, stage="phase10_entry"):
    return api.AgentRows(batch=batch, stamp=api.Stamp(source_turn=turn, stage=stage))


def _baseline_simulation():
    repo = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ["git", "-C", str(repo), "show", f"{BASE}:src/chronicler/simulation.py"], text=True,
    )
    module = ModuleType("chronicler._a01_baseline_simulation")
    exec(compile(source, "a01-baseline/simulation.py", "exec"), module.__dict__)
    return module


def test_result_wrapper_preserves_signature_and_arguments(api, monkeypatch, sample_world):
    from chronicler import simulation as sim
    assert list(inspect.signature(sim.run_turn).parameters) == list(
        inspect.signature(sim.run_turn_result).parameters)
    call = []
    text = "unchanged text"

    def result(*args):
        call.append(args)
        return api.TurnResult(text, api.TurnObservation(0, 1, None))

    monkeypatch.setattr(sim, "run_turn_result", result)
    args = (sample_world, object(), object(), 43, object(), object(), object(), object(), True, [])
    assert sim.run_turn(*args) == text
    assert call == [args]


def _quiet_phases(monkeypatch, sim, log):
    for name in ("phase_environment", "apply_automatic_effects", "phase_technology",
                 "phase_cultural_milestones", "phase_random_events", "phase_leader_dynamics"):
        monkeypatch.setattr(sim, name, lambda *a, _name=name, **kw: log.append(_name) or [])
    monkeypatch.setattr(sim, "phase_production", lambda *a, **kw: log.append("production"))
    from chronicler import ecology, emergence, artifacts, economy
    for name in ("check_black_swans", "check_environmental_events", "check_tech_regression"):
        monkeypatch.setattr(emergence, name, lambda *a, **kw: [])
    monkeypatch.setattr(emergence, "compute_all_stress", lambda *a: None)
    monkeypatch.setattr(ecology, "tick_ecology", lambda *a, **kw: log.append("ecology") or [])
    monkeypatch.setattr(artifacts, "tick_artifacts", lambda *a: [])
    monkeypatch.setattr(economy, "settle_pending_stockpile_bootstraps", lambda *a: log.append("bootstrap"))


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_coordinator_order_identities_and_prior_publication(api, monkeypatch, make_world, mode):
    from chronicler import simulation as sim, economy, mutual_aid, relationships
    from chronicler.models import AgentEventRecord, CivShock, Event
    from chronicler.demand_signals import DemandSignalManager
    world = make_world()
    world.agent_mode = mode
    world.mutual_aid_enabled = True
    log, seen, owners, observations = [], [], [], []
    _quiet_phases(monkeypatch, sim, log)
    artifact_class = api.TurnArtifacts

    def owner(**kwargs):
        result = artifact_class(**kwargs)
        owners.append(result)
        return result

    monkeypatch.setattr(api, "TurnArtifacts", owner)
    raw = [pa.record_batch({"region": [0], "x": [0.1], "y": [0.2]}) for _ in range(9)]
    death = AgentEventRecord(agent_id=7, event_type="death", turn=0, region=0,
                             civ_affinity=0, target_region=0, occupation=0)
    old_shock = CivShock(civ_id=0, stability_shock=-0.1)
    world.pending_shocks = [old_shock] if mode == "hybrid" else []
    monkeypatch.setattr(mutual_aid, "read_stockpile_commitments", lambda *a: {})
    monkeypatch.setattr(mutual_aid, "dispatch_mutual_aid", lambda w, snapshot, **kw: log.append("dispatch") or [])
    monkeypatch.setattr(mutual_aid, "observe_mutual_aid", lambda w, result, snapshot:
                        seen.append(("pre_economy", w.turn, snapshot, result)))
    results = [SimpleNamespace(treasury_tax={}, imports_by_region={}) for _ in range(2)]
    monkeypatch.setattr(economy, "build_economy_region_input_batch", lambda *a: None)
    monkeypatch.setattr(economy, "build_economy_trade_route_batch", lambda *a, **kw: None)
    monkeypatch.setattr(economy, "reconstruct_economy_result", lambda *a, **kw: results[world.turn])
    gates = []

    def action(w, **kwargs):
        gates.append(getattr(w, "_economy_result", None))
        assert w._dead_agents_this_turn == [] and w._conquered_this_turn == set()
        w._conquered_this_turn.update({1, 0})
        return [Event(turn=w.turn, event_type="war", actors=[], description="ordered action")]

    monkeypatch.setattr(sim, "phase_action", action)

    class Native:
        def tick_economy(self, *args):
            log.append("economy")
            return ()

        def get_snapshot(self):
            log.append("phase10_snapshot")
            return raw[world.turn * 3 + 1]

    class Bridge:
        _sim = Native()
        _demand_manager = DemandSignalManager()
        named_agents = {7: "Before"}
        dynasty_registry = None
        rust_owns_formation = False
        economy_simulator = None

        @property
        def ecology_simulator(self):
            return self._sim

        def get_snapshot(self):
            stage = "post_politics" if "consequences" in log else "pre_economy"
            log.append(stage)
            return (raw[world.turn * 3 + 2] if stage == "post_politics"
                    else (None if world.turn == 2 else raw[world.turn * 3]))

        def set_economy_result(self, result):
            seen.append(("bridge_economy", world.turn, result))

        def sync_regions(self, w):
            log.append("sync")

        def tick_agents(self, w, *, conquered, death_output, shocks=None, demands=None):
            log.append("tick")
            assert w._conquered_this_turn == set()
            assert conquered == {i: True for i in owners[-1].conquered_civ_ids}
            if mode == "hybrid" and w.turn == 0:
                assert shocks[-1] is old_shock and w.pending_shocks == []
            self.named_agents[7] = f"Published {w.turn}"
            death_output.extend([death] if mode != "demographics-only" and w.turn == 0 else [])
            return []

        def read_social_edges(self):
            return []

    bridge = Bridge()

    def settlements(w, source_turn, force, *, agent_rows):
        log.append("settlements")
        assert source_turn == w.turn
        assert agent_rows.batch is raw[w.turn * 3 + 1]
        return []

    monkeypatch.setattr(sim, "run_settlement_tick", settlements)

    def consequences(w, *, phase10, acc, politics_runtime):
        log.append("consequences")
        assert phase10 is owners[-1].phase10
        assert phase10.economy is (results[w.turn] if w.turn < 2 else None)
        assert any(e.event_type == "war" and e.turn == w.turn for e in w.events_timeline)
        assert phase10.deaths == ((death,) if mode != "demographics-only" and w.turn == 0 else ())
        assert phase10.named_agents[7] == f"Published {w.turn}"
        with pytest.raises(TypeError):
            phase10.named_agents[7] = "forbidden"
        bridge.named_agents[7] = "Later"
        assert phase10.named_agents[7] == f"Published {w.turn}"
        w.regions[0].controller = w.civilizations[1].name
        if acc is not None:
            acc.add(0, w.civilizations[0], "stability", -2, "guard-shock")
        return [Event(turn=w.turn, event_type="collapse", actors=[], description="ordered tail")]

    monkeypatch.setattr(sim, "phase_consequences", consequences)
    monkeypatch.setattr(relationships, "compute_belief_data", lambda snapshot, *a:
                        seen.append(("post_politics", world.turn, snapshot)) or ({}, {}))
    monkeypatch.setattr(relationships, "form_and_sync_relationships", lambda *a: [])

    def narrator(w, events):
        log.append("narrator")
        assert events[-1] is w.events_timeline[-1]
        assert w.turn == len(observations)
        return f"turn {w.turn}"

    for n in range(3):
        log.clear()
        output = sim.run_turn_result(world, lambda *a: None, narrator, agent_bridge=bridge)
        observations.append(output.observation)
        assert output.chronicle_text == f"turn {n}"
        assert output.observation.source_turn == n and output.observation.completed_turn == n + 1
        assert output.observation.phase10_agents is owners[n].phase10.agents
        assert output.observation.phase10_agents.batch is raw[n * 3 + 1]
        assert world.regions[0].controller == world.civilizations[1].name
        stages = [log.index(name) for name in ("pre_economy", "sync", "ecology", "tick",
                  "bootstrap", "phase10_snapshot", "settlements", "consequences", "post_politics", "narrator")]
        assert stages == sorted(stages)
        assert log.count("phase10_snapshot") == log.count("pre_economy") == log.count("post_politics") == 1
        if mode == "hybrid":
            assert world.pending_shocks  # Phase 10 signals survive until next tick.
    assert gates == [None, results[0], results[1]]
    assert world._economy_result is None  # Missing Phase-2 input publishes None at the old boundary.
    assert len({id(owner) for owner in owners}) == 3
    for n in range(3):
        assert ("pre_economy", n, raw[n * 3] if n < 2 else None,
                results[n] if n < 2 else None) in seen
        assert ("post_politics", n, raw[n * 3 + 2]) in seen
    assert observations[0].phase10_agents.batch is raw[1]  # Historical after two later turns.
    assert not any(isinstance(v, artifact_class) for v in vars(world).values())


def test_snapshot_failure_publishes_none_not_last_good(api, monkeypatch, sample_world, caplog):
    from chronicler import simulation as sim
    _quiet_phases(monkeypatch, sim, [])
    sample_world._agent_snapshot = pa.record_batch({"region": [0]})
    sample_world._dead_agents_this_turn = [object()]
    monkeypatch.setattr(sim, "phase_action", lambda *a, **kw: [])
    monkeypatch.setattr(sim, "phase_consequences", lambda *a, **kw: [])

    class Native:
        def get_snapshot(self):
            raise RuntimeError("new snapshot unavailable")

    bridge = SimpleNamespace(
        _sim=Native(), named_agents={}, dynasty_registry=None, rust_owns_formation=True,
        ecology_simulator=None, get_snapshot=lambda: None, sync_regions=lambda w: None,
        tick_agents=lambda *a, **kw: [], read_social_edges=lambda: [],
    )
    output = sim.run_turn_result(sample_world, lambda *a: None, lambda *a: "", agent_bridge=bridge)
    assert output.observation.phase10_agents is None
    assert sample_world._agent_snapshot.num_rows == 1  # Legacy scratch is ignored, not republished.
    assert sample_world._dead_agents_this_turn == []
    assert "Failed to fetch agent snapshot" in caplog.text


@pytest.mark.parametrize("failure", ["tick", "consequences", "narrator"])
def test_failed_turn_has_no_published_owner_or_retry_claim(api, monkeypatch, sample_world, failure):
    from chronicler import simulation as sim
    _quiet_phases(monkeypatch, sim, [])
    monkeypatch.setattr(sim, "phase_action", lambda *a, **kw: [])

    def fail(*a, **kw):
        raise RuntimeError(failure)

    monkeypatch.setattr(sim, "phase_consequences", fail if failure == "consequences" else lambda *a, **kw: [])
    bridge = SimpleNamespace(
        _sim=SimpleNamespace(get_snapshot=lambda: None), named_agents={}, dynasty_registry=None,
        rust_owns_formation=True, ecology_simulator=None, get_snapshot=lambda: None,
        sync_regions=lambda w: None, tick_agents=fail if failure == "tick" else lambda *a, **kw: [],
        read_social_edges=lambda: [],
    )
    with pytest.raises(RuntimeError, match=failure):
        sim.run_turn_result(sample_world, lambda *a: None,
                            fail if failure == "narrator" else lambda *a: "", agent_bridge=bridge)
    assert sample_world.turn == 0
    assert not any(isinstance(v, api.TurnArtifacts) for v in vars(sample_world).values())


@pytest.mark.parametrize("turn,stage", [(1, "phase10_entry"), (0, "post_politics")])
def test_invalid_stamps_fail_before_mutation(api, make_world, turn, stage):
    from chronicler.simulation import phase_consequences
    from chronicler.settlements import run_settlement_tick
    w = make_world()
    before = w.model_dump_json()
    batch = pa.record_batch({"region": [0]})
    # Production containers reject malformed input before publication.
    with pytest.raises(ValueError):
        rows = _rows(api, batch, turn, stage)
        api.Phase10Inputs(0, rows, None, None, ())
    # Also exercise consumer boundaries with explicitly forged foreign inputs.
    rows = SimpleNamespace(batch=batch, stamp=SimpleNamespace(source_turn=turn, stage=stage))
    payload = SimpleNamespace(source_turn=0, agents=rows, named_agents=None, economy=None, deaths=())
    with pytest.raises(ValueError, match="stamp"):
        phase_consequences(w, phase10=payload)
    with pytest.raises(ValueError, match="stamp"):
        run_settlement_tick(w, source_turn=0, agent_rows=rows)
    assert w.model_dump_json() == before
    with pytest.raises(ValueError, match="source turn"):
        phase_consequences(w, phase10=api.Phase10Inputs(1, None, None, None, ()))


def test_settlement_gates_identity_missing_empty_and_raw_parity(api, make_world):
    from chronicler.settlements import run_settlement_tick, _parse_snapshot_by_region
    malformed = pa.record_batch({"region": [0]})
    w = make_world()
    w._agent_snapshot = malformed
    assert run_settlement_tick(w, 1, agent_rows=_rows(api, malformed, 1)) == []
    assert w._settlement_diagnostics["reason"] == "not_detection_turn"
    assert run_settlement_tick(w, 0, agent_rows=None) == []
    assert w._settlement_diagnostics["reason"] == "mode_off_no_snapshot"
    with pytest.raises(KeyError):
        run_settlement_tick(w, 0, agent_rows=_rows(api, malformed))
    with pytest.raises(ValueError, match="supplied snapshot"):
        _parse_snapshot_by_region(pa.record_batch({"region": []}), 2, agent_rows=_rows(api, malformed))
    for empty in (False, True):
        batch = pa.record_batch({"region": [] if empty else [0] * 10,
                                 "x": [] if empty else [0.1] * 10,
                                 "y": [] if empty else [0.2] * 10})
        raw_world, view_world = make_world(), make_world()
        raw_world._agent_snapshot = batch
        rows = _rows(api, batch)
        assert run_settlement_tick(raw_world, 0) == run_settlement_tick(view_world, 0, agent_rows=rows)
        assert raw_world.model_dump_json() == view_world.model_dump_json()
        assert raw_world._settlement_diagnostics == view_world._settlement_diagnostics


def test_phase10_uses_explicit_payload_and_forwards_all_readers(api, monkeypatch, make_world):
    from chronicler import simulation as sim, religion, great_persons, factions
    from chronicler.models import Belief
    w = make_world()
    w.belief_registry = [Belief(faith_id=0, name="Faith", civ_origin=0, doctrines=[0, 1, 2, 0, 1])]
    batch = pa.record_batch({"region": [0], "belief": [0], "occupation": [4], "civ_affinity": [0]})
    rows = _rows(api, batch)
    economy, deaths, named = object(), (object(),), MappingProxyType({9: "Prophet"})
    payload = api.Phase10Inputs(0, rows, named, economy, deaths)
    w._agent_snapshot = object()
    w._named_agents = object()
    w._economy_result = object()
    w._dead_agents_this_turn = [object()]
    calls = []
    for owner, names, result in (
        (sim, ("apply_value_drift", "tick_cultural_assimilation"), None),
        (religion, ("compute_majority_belief", "compute_civ_majority_faith"), {}),
        (religion, ("compute_conversion_signals",), {}),
        (religion, ("compute_persecution", "detect_schisms"), []),
        (great_persons, ("check_pilgrimages",), []),
    ):
        for name in names:
            def reader(*args, _name=name, _result=result, agent_rows=None, **kwargs):
                assert agent_rows is rows
                if _name == "compute_conversion_signals":
                    assert kwargs["named_agents"] is payload.named_agents
                    assert kwargs["named_agents"] == named
                calls.append(_name)
                return _result
            monkeypatch.setattr(owner, name, reader)
    monkeypatch.setattr(religion, "compute_martyrdom_boosts",
                        lambda regions, records: calls.append("deaths") or (records is deaths or pytest.fail("legacy deaths")))
    monkeypatch.setattr(factions, "tick_factions",
                        lambda world, **kwargs: calls.append("economy") or (kwargs["economy_result"] is economy and []))
    sim.phase_consequences(w, phase10=payload)
    assert calls == ["apply_value_drift", "tick_cultural_assimilation", "compute_majority_belief",
                     "compute_civ_majority_faith", "compute_conversion_signals", "compute_persecution",
                     "deaths", "detect_schisms", "check_pilgrimages", "economy"]
    assert w._prev_belief_distribution == {0: {0: 1}}
    assert w._prev_priest_counts == {w.civilizations[0].name: 1}


def test_exact_baseline_two_turns_events_narration_state_and_rng(api, sample_world, tmp_path):
    from chronicler import simulation as sim
    from chronicler.models import ActionType
    from scripts.benchmark_headless import rng_trace
    baseline = _baseline_simulation()
    results = []
    for label, implementation in (("baseline", baseline.run_turn), ("candidate", sim.run_turn)):
        world = sample_world.model_copy(deep=True)
        world.agent_mode = "off"
        captures = []

        def narrator(w, events):
            captures.append((w.turn, [e.model_dump(mode="json") for e in events],
                             [e.model_dump(mode="json") for e in w.named_events], w.model_dump_json()))
            return str(captures[-1][1])

        with rng_trace(tmp_path / f"{label}.jsonl") as trace:
            text = [implementation(world, lambda *a: ActionType.DEVELOP, narrator, seed=42) for _ in range(2)]
        results.append((captures, text, world.model_dump_json(), trace))
    assert results[0] == results[1]


def test_snapshot_consumers_add_no_rng_and_preserve_raw_semantics(api, sample_world, tmp_path):
    """Exercise a present view; slice-1 forwarding adapters remain dependency-gated."""
    from chronicler import simulation as sim
    from chronicler.models import Belief
    from chronicler.settlements import run_settlement_tick
    from scripts.benchmark_headless import rng_trace
    baseline = _baseline_simulation()
    batch = pa.record_batch({
        "id": [9, 2], "region": [0, 1], "civ_affinity": [0, 1],
        "occupation": [4, 0], "belief": [0, 0],
        "cultural_value_0": [0, 1], "cultural_value_1": [2, 3],
        "cultural_value_2": [255, 255], "loyalty_trait": [0.5, 0.7],
        "loyalty": [0.6, 0.9], "x": [0.1, 0.2], "y": [0.2, 0.3],
    })
    initial = sample_world.model_copy(deep=True)
    initial.agent_mode = "off"
    initial.belief_registry = [Belief(faith_id=0, name="Faith", civ_origin=0, doctrines=[0] * 5)]
    results = []
    for label in ("baseline", "candidate"):
        world = initial.model_copy(deep=True)
        world._agent_snapshot = batch
        world._named_agents = {9: "Prophet"}
        world._dead_agents_this_turn = []
        world._economy_result = None
        rows = _rows(api, batch)
        with rng_trace(tmp_path / f"snapshot-{label}.jsonl") as trace:
            if label == "baseline":
                settlements = run_settlement_tick(world, source_turn=0)
                events = baseline.phase_consequences(world)
            else:
                settlements = run_settlement_tick(world, source_turn=0, agent_rows=rows)
                events = sim.phase_consequences(world, phase10=api.Phase10Inputs(
                    0, rows, MappingProxyType({9: "Prophet"}), None, (),
                ))
        results.append(([e.model_dump(mode="json") for e in settlements + events],
                        world.model_dump_json(), world._prev_belief_distribution,
                        world._prev_priest_counts, trace))
    assert results[0] == results[1]


def test_str_wrapper_does_not_retain_view_after_return(api, monkeypatch, make_world):
    # The temporary bridge is test-only. Real native mode lifetime remains gated.
    if not hasattr(api, "DEPENDENCY_GATE"):
        pytest.skip("Mock weak-reference probe; integrated view lifetime belongs to slice 3")
    from chronicler import simulation as sim
    _quiet_phases(monkeypatch, sim, [])
    monkeypatch.setattr(sim, "phase_action", lambda *a, **kw: [])
    monkeypatch.setattr(sim, "phase_consequences", lambda *a, **kw: [])
    batch = pa.record_batch({"region": [0], "x": [0.1], "y": [0.2]})
    refs = []
    view_class = api.AgentRows

    def view(**kwargs):
        result = view_class(**kwargs)
        refs.append(weakref.ref(result))
        return result

    monkeypatch.setattr(api, "AgentRows", view)
    bridge = SimpleNamespace(
        _sim=SimpleNamespace(get_snapshot=lambda: batch), named_agents={}, dynasty_registry=None,
        rust_owns_formation=True, ecology_simulator=None, get_snapshot=lambda: None,
        sync_regions=lambda w: None, tick_agents=lambda *a, **kw: [], read_social_edges=lambda: [],
    )
    w = make_world()
    for _ in range(8):
        assert sim.run_turn(w, lambda *a: None, lambda *a: "", agent_bridge=bridge) == ""
        gc.collect()
        assert all(ref() is None for ref in refs)


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
@pytest.mark.parametrize("entry", ["tick", "tick_agents"])
def test_bridge_death_output_keeps_processing_order_and_legacy_api(
    api, monkeypatch, make_world, mode, entry,
):
    from collections import deque
    from chronicler.agent_bridge import AgentBridge
    from chronicler.dynasties import DynastyRegistry
    from chronicler.models import AgentEventRecord
    from chronicler import economy
    world = make_world()
    log = []
    bridge = AgentBridge.__new__(AgentBridge)
    bridge._sim = SimpleNamespace(
        set_region_state=lambda *a: log.append("sync_regions"),
        set_settlement_footprints=lambda *a: None,
        set_merchant_route_graph=lambda *a: log.append("routes"),
        tick=lambda *a: log.append("native_tick") or object(),
        get_household_stats=lambda: {}, get_merchant_trip_stats=lambda: {},
        get_knowledge_stats=lambda: {}, get_promotions=lambda: object(),
        get_aggregates=lambda: object(),
    )
    bridge._mode = mode
    bridge._event_window = deque(maxlen=20)
    bridge._shadow_logger = bridge._sidecar = None
    bridge.named_agents = {}
    bridge.gp_by_agent_id = {}
    bridge.dynasty_registry = DynastyRegistry()
    bridge._pending_dynasty_events = []
    bridge._economy_result = None
    bridge._gini_by_civ = {}
    bridge._collect_rel_stats = False
    bridge._household_stats_history = []
    bridge._merchant_trip_stats_history = []
    bridge._knowledge_stats_history = []
    raw = [AgentEventRecord(0, i, kind, 0, 0, 0, 0)
           for i, kind in ((9, "death"), (4, "birth"), (2, "death"))]
    monkeypatch.setattr(economy, "build_merchant_route_graph", lambda *a: object())
    monkeypatch.setattr(bridge, "_refresh_snapshot_metrics", lambda w: log.append("metrics"))
    monkeypatch.setattr(bridge, "_write_back", lambda w: log.append("writeback"))
    monkeypatch.setattr(bridge, "_process_promotions", lambda *a: log.append("promotions"))
    monkeypatch.setattr(bridge, "_convert_events", lambda *a: log.append("convert") or raw)

    def process_deaths(events, w):
        log.append("process_deaths")
        assert output == [raw[0], raw[2]]
        assert output[0] is w._dead_agents_this_turn[0]
        return []

    monkeypatch.setattr(bridge, "_process_deaths", process_deaths)
    monkeypatch.setattr(bridge, "_detect_character_events", lambda *a: log.append("characters") or [])
    monkeypatch.setattr(bridge, "_aggregate_events", lambda *a: log.append("aggregate") or [])
    monkeypatch.setattr(bridge, "_apply_demographics_clamp", lambda *a: log.append("demographics"))
    monkeypatch.setattr(bridge, "_write_economy_sidecar", lambda *a: log.append("economy_sidecar"))
    output = []
    assert getattr(bridge, entry)(world, death_output=output) == []
    assert log.index("native_tick") < log.index("metrics") < log.index("economy_sidecar")
    if mode == "demographics-only":
        assert output == [] and world._dead_agents_this_turn == []
    else:
        assert [e.agent_id for e in output] == [9, 2]
        assert world.agent_events_raw == raw
        assert log.index("metrics") < log.index("promotions") < log.index("convert") < log.index("process_deaths")
    # The old standalone entry still works with no output keyword.
    monkeypatch.setattr(bridge, "_process_deaths", lambda *a: [])
    assert getattr(bridge, entry)(world) == []
