"""Inactive adapter contracts: no study worker, native pool or physics tick.

The real main-entry ordering case stops at bind, before its first turn. Natural
cohort outcomes must not be sampled by a setup test.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import research_natural_contract as contract
    def load(name):
        spec = importlib.util.spec_from_file_location(name + "_test_observer", ROOT / "scripts" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return contract, load("run_research_natural_continuation"), load("read_research_natural_continuation")


@pytest.mark.parametrize("left,right", [(True, 1), (1, 1.0), (0.0, -0.0), ({"a": 1, "b": 2}, {"b": 2, "a": 1})])
def test_strict_nested_equality_and_diff_keep_types_order_and_signed_zero(modules, left, right):
    c, _, _ = modules
    assert not c.same({"nested": [left]}, {"nested": [right]})
    assert c.differences({"nested": [left]}, {"nested": [right]})


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":1e9999}', '{"a":NaN}', '{"a":Infinity}'])
def test_bounded_metadata_reader_rejects_ambiguous_or_nonfinite_json(modules, tmp_path, raw):
    c, _, _ = modules
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(c.ContractError):
        c.read(path)
    path.write_text('{"a":1}')
    with pytest.raises(c.ContractError, match="bound"):
        c.read(path, maximum=2)


def test_parent_and_forks_use_the_fixed_public_cli_without_forced_worlds(modules, tmp_path):
    from chronicler.main import _build_parser
    c, r, _ = modules
    for role in c.ROLES:
        args = _build_parser().parse_args(r.simulation_args(tmp_path, 2000, role))
        assert args.turns == 180 and args.seed == 2000 and args.worldgen == "template"
        assert args.regions == 8 and args.civs == 4 and args.agents == "hybrid"
        assert args.scientific_research_agendas is args.scientific_claims is args.scholarship is args.techniques is True
        assert args.health_care is args.harvest_forecasts is args.ritual_gatherings is args.transaction_receipts is False
        assert args.checkpoint_turns == ((60, 180) if role == "parent" else (180,))
    assert c.SEEDS == tuple(range(2000, 2008))
    assert sum(180 if role == "parent" else 120 for _seed in c.SEEDS for role in c.ROLES) == 3360


def test_global_rng_sidecar_restores_both_gaussian_caches_losslessly(modules):
    import numpy as np
    c, r, _ = modules
    saved_python, saved_numpy = random.getstate(), np.random.get_state()
    try:
        random.seed(2000)
        np.random.seed(2000)
        random.gauss(0, 1)
        np.random.normal()
        boundary = r.rng_state()
        expected = [random.gauss(0, 1), random.random(), float(np.random.normal()), float(np.random.random())]
        random.seed(99)
        np.random.seed(99)
        r.restore_rng(json.loads(json.dumps(boundary)))
        assert c.same(r.rng_state(), boundary)
        actual = [random.gauss(0, 1), random.random(), float(np.random.normal()), float(np.random.random())]
        assert c.same(actual, expected)
        malformed = deepcopy(boundary)
        malformed["numpy"][1][0] = True
        before = r.rng_state()
        with pytest.raises(c.ContractError):
            r.restore_rng(malformed)
        assert c.same(before, r.rng_state())  # Both validate before either global changes.
    finally:
        random.setstate(saved_python)
        np.random.set_state(saved_numpy)


def test_actual_natural_fresh_entry_activates_then_applies_v2_before_first_tick(modules, tmp_path, monkeypatch):
    from chronicler import main, agent_bridge
    from chronicler.batch_manifest import file_sha256
    c, r, _ = modules
    generated = []
    ordinary_generate = main.generate_world
    def generate(**kwargs):
        generated.append((kwargs, ordinary_generate(**kwargs)))
        return generated[-1][1]
    monkeypatch.setattr(main, "generate_world", generate)
    monkeypatch.setattr(agent_bridge, "AgentBridge", lambda *a, **k: SimpleNamespace())
    class BeforeFirstTick(Exception):
        pass
    def no_tick(*a, **k):
        pytest.fail("ordering test must stop before any physics tick")
    monkeypatch.setattr(main, "run_turn_result", no_tick)
    class Probe:
        def bind(self, save, config):
            assert len(generated) == 1
            kwargs, world = generated[0]
            assert kwargs == dict(seed=2000, num_regions=8, num_civs=4, worldgen="template")
            assert world.turn == 0 and world.scientific_claims.research_agendas.enabled is True
            assert world.scientific_claims.research_agendas.enabled_turn == 0
            assert world.scientific_claims.publication_rule == "funded-context-v2"
            assert world.scientific_claims.trials == [] and world.scientific_claims.trial_spent == 0
            assert config["expansion_experiment"]["controls_after"] == c.CONTROLS
            raise BeforeFirstTick
        def live_record(self):
            return None
    registration = ROOT / c.REGISTRATION
    request = r.request(2000, "parent", dict(path=str(registration), sha256=file_sha256(registration)))
    args = main._build_parser().parse_args(r.simulation_args(tmp_path, 2000, "parent"))
    with pytest.raises(BeforeFirstTick):
        main.execute_run(args, expansion_experiment=request, turn_boundary=Probe())


def test_source_callback_order_is_after_reflections_and_scheduled_checkpoint(modules):
    import ast
    import inspect
    from chronicler import main
    tree = ast.parse(inspect.getsource(main.execute_run))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    def first(name):
        return min(node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == name)
    boundary = min(node.lineno for node in calls if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "turn_boundary" and node.func.attr == "turn_end")
    save = min(node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "_save_exact"
        and any(isinstance(a, ast.Name) and a.id == "_checkpoint_turn_template" for a in node.args))
    assert first("on_turn") < first("generate_reflection") < save < boundary


def test_boundary_rng_requires_actual_checkpoint_and_does_not_change_globals(modules, tmp_path, monkeypatch):
    c, r, _ = modules
    frozen = dict(runtime={"observed": True}, controls={"contract": "pinned"})
    callback = r.BoundaryCapture(tmp_path, frozen)
    callback.bind(None, dict(simulation_args={"scientific_research_agendas": True}, expansion_experiment={"controls_after": c.CONTROLS}))
    monkeypatch.setattr(c, "checkpoint_sections", lambda path: (_ for _ in ()).throw(c.ContractError("checkpoint missing")))
    with pytest.raises(c.ContractError, match="checkpoint missing"):
        callback.turn_end(SimpleNamespace(turn=60, seed=2000))
    assert not (tmp_path / "boundary-rng.json").exists()
    path = tmp_path / "checkpoint_turn_60.ckpt"
    path.write_bytes(b"checkpoint boundary fixture")
    monkeypatch.setattr(c, "checkpoint_sections", lambda path: (dict(turn=60, seed=2000, exact=True), {"python": {"sha256": "fixture"}}))
    before = r.rng_state()
    assert callback.turn_end(SimpleNamespace(turn=59, seed=2000)) is False
    assert callback.turn_end(SimpleNamespace(turn=60, seed=2000)) is False
    saved = c.read(tmp_path / "boundary-rng.json")
    assert c.same(saved["state"], before) and c.same(r.rng_state(), before)
    assert saved["checkpoint_sha256"] == c.sha(path)
    with pytest.raises(c.ContractError, match="twice"):
        callback.turn_end(SimpleNamespace(turn=60, seed=2000))


def test_admission_failure_starts_no_worker_and_retains_negative_execution(modules, tmp_path, monkeypatch):
    c, r, _ = modules
    freeze = tmp_path / "prospective.json"
    c.write(freeze, {"fixture": True})
    monkeypatch.setattr(r, "verify_freeze", lambda *a: {"control": {"git_sha": "fixture"}})
    def refuse(*a, **k):
        raise c.ContractError("registered disk floor not met")
    monkeypatch.setattr(r, "resources", refuse)
    monkeypatch.setattr(r.subprocess, "Popen", lambda *a, **k: pytest.fail("admission failed; no child allowed"))
    options = SimpleNamespace(source_root=str(tmp_path / "producer"), output_root=str(tmp_path / "evidence"), freeze=str(freeze))
    assert r.run(options) == 1
    result = c.read(Path(options.output_root) / "execution.json")
    assert result["execution_complete"] is False and result["qualified"] is False
    assert result["runs"] == [] and result["actual_physics_ticks"] is None
    assert result["error"]["message"] == "registered disk floor not met"


def test_null_exposure_is_zero_but_missing_science_is_not(modules):
    c, _, _ = modules
    science = dict(trials=[], proposals=[], receipts=[], trial_spent=0, effort_spent=0, claims=[],
        research_agendas=dict(cycles=[], blocked_reason="", blocked_turn=None))
    history = [dict(turn=61, scientific_claims=dict(source_turn=60, allocations=[]))]
    result = c.exposure(science, history)
    assert result["new_trials"] == result["paid_adoption_cost"] == 0
    with pytest.raises(c.ContractError, match="unavailable"):
        c.exposure(science, [dict(turn=61, scientific_claims=None)])


def test_phase10_receipt_does_not_explain_same_source_phase4_payment(modules):
    c, _, _ = modules
    science = dict(trials=[dict(id=0, claim=0, funded_turn=60, cost=2, resolved_turn=61, status="completed")],
        proposals=[], receipts=[dict(seat=0, trial=0, received_turn=61)], trial_spent=2, effort_spent=2,
        claims=[dict(id=0)], research_agendas=dict(cycles=[], blocked_reason="", blocked_turn=None))
    allocation = dict(seat=0, claim_id=0, paid=1, share=1.0, confidence=.5)
    history = [dict(turn=s + 1, scientific_claims=dict(source_turn=s, allocations=[allocation])) for s in (61, 62)]
    rows = c.exposure(science, history)["paid_adoption_rows"]
    assert [row["prior_new_trial_receipts"] for row in rows] == [0, 1]


def test_active_strict_comparison_keeps_unvalidated_world_changes(modules):
    c, _, reader = modules
    bundle = dict(metadata=dict(generated_at="2026-10-29T00:00:00+00:00", expansion_experiment={"validated": True}),
        world_state={"value": -0.0}, history=[{"turn": 180}], events_timeline=[])
    summary = dict(raw_world_sha256="world", raw_history_sha256="history", native_sections={"native.agent.0": {"sha256": "raw"}}, final_rng={"state": "same"})
    files = {name: dict(bytes=1, sha256="same") for name in ("chronicle_bundle.json", "state.json")}
    parent = dict(bundle=bundle, summary=summary, files=files, receipt_validated=True)
    active = deepcopy(parent)
    active["bundle"]["metadata"].update(generated_at="2026-10-29T00:01:00+00:00", resume={"kind": "experiment-fork"})
    assert reader.active_identity(parent, active, c.same)["files"]["chronicle_bundle.json"] is True
    active["bundle"]["world_state"]["value"] = 0.0
    result = reader.active_identity(parent, active, c.same)
    assert result["files"]["chronicle_bundle.json"] is False
    assert result["normalized_bundle_differences"][0]["path"] == "$.world_state.value"


def test_cleanup_refuses_a_reused_numeric_process_identity(modules, monkeypatch):
    c, r, _ = modules
    child = SimpleNamespace(pid=1234, poll=lambda: None)
    monkeypatch.setattr(r, "owned_group", lambda pid: [dict(pid=1234, start_ticks=99)])
    monkeypatch.setattr(r.os, "killpg", lambda *a: pytest.fail("reused process group must not be signaled"))
    with pytest.raises(c.ContractError, match="identity cannot be established"):
        r.cleanup(child, {1234: 98})
