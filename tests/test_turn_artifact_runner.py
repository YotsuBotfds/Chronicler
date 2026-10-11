"""Runner handoff checks; structural rows doubles isolate slice-3 ownership.

The explicit a01_test_doubles plugin supplies only absent upstream interfaces.
After integration, run these tests against real TurnResult/TurnObservation types.
"""
import argparse
import gc
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import weakref

import pyarrow as pa
import pytest

from chronicler import checkpoint_replay as replay
from chronicler.main import execute_run
from chronicler.turn_artifacts import Stamp, TurnObservation, TurnResult


class RowsProbe:
    """Observe demands without implementing the slice-1 column cache."""
    def __init__(self, source_turn, batch, calls):
        self.stamp = Stamp(source_turn, "phase10_entry")
        self.batch = batch
        self.calls = calls

    def has(self, name):
        self.calls.append(("has", name))
        return name in self.batch.column_names

    def ints(self, name):
        self.calls.append(("ints", name))
        return tuple(self.batch.column(name).to_pylist())


def runner_args(tmp_path, *, turns=1, mode="hybrid"):
    return argparse.Namespace(
        seed=42, turns=turns, civs=2, regions=2,
        output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=100, llm_actions=False,
        scenario=None, simulate_only=True, agents=mode,
    )


@pytest.fixture
def runner_bridge(monkeypatch):
    bridge = MagicMock()
    bridge._gini_by_civ = {}
    bridge._collect_rel_stats = False
    bridge.relationship_stats = []
    bridge.displacement_by_region = {}
    monkeypatch.setattr("chronicler.agent_bridge.AgentBridge", lambda *a, **k: bridge)
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda _: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda _: None)
    return bridge


@pytest.mark.parametrize("batch,expected", [
    (None, (0, 0.0, 0, 0)),
    (pa.record_batch({"civ_affinity": [], "settlement_id": [], "region": []}), (0, 0.0, 0, 0)),
    (pa.record_batch({"civ_affinity": [0, 1], "other": [1, 1]}), (0, 0.0, 0, 0)),
    (pa.record_batch({"civ_affinity": [0, 1, 9, None], "settlement_id": [1, 0, 1, 1]}), (1, 0.5, 1, 0)),
    (pa.record_batch({"civ_affinity": [0, 1, 0, 1, 99],
                      "settlement_id": [1, 0, 1, 0, 1], "region": [0, 0, None, 99, 99]}),
     (2, 0.5, 1, 1)),
])
def test_urban_uses_historical_rows_and_end_turn_controllers(
    batch, expected, make_world, tmp_path, monkeypatch, runner_bridge,
):
    world = make_world()
    calls, weak_rows, seen = [], [], []

    def tick(world, **kwargs):
        source_turn = world.turn
        # Territory changes after the phase-10 batch was captured.
        world.regions[0].controller = world.civilizations[1].name
        # Poison legacy scratch: main must never read it.
        world._agent_snapshot = object()
        world._named_agents = object()
        rows = None if batch is None else RowsProbe(source_turn, batch, calls)
        if rows is not None:
            weak_rows.append(weakref.ref(rows))
        world.turn += 1
        return TurnResult("deterministic", TurnObservation(source_turn, world.turn, rows))

    def capture(snapshot, text, events, named):
        gc.collect()
        assert all(ref() is None for ref in weak_rows)
        assert snapshot.turn == world.turn == 1
        assert text == "deterministic"
        seen.append((snapshot.urban_agent_count, snapshot.urban_fraction,
                     snapshot.civ_stats["Civ0"].urban_agents,
                     snapshot.civ_stats["Civ1"].urban_agents))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    execute_run(runner_args(tmp_path), world=world, on_turn=capture)
    assert seen == [expected]
    decoded = [name for method, name in calls if method == "ints"]
    assert decoded == ([] if batch is None or "settlement_id" not in batch.column_names else
                       ["civ_affinity", "settlement_id"] + (["region"] if "region" in batch.column_names else []))
    runner_bridge.write_final_sidecar_snapshot.assert_called_once_with(world)
    runner_bridge.close.assert_called_once()


def test_two_turns_release_each_view_before_mutating_callback(
    make_world, tmp_path, monkeypatch, runner_bridge,
):
    world = make_world()
    references, calls, observed, forwarded = [], [], [], []
    batch = pa.record_batch({"civ_affinity": [0], "settlement_id": [1], "region": [0]})

    def tick(world, **kwargs):
        source_turn = world.turn
        rows = RowsProbe(source_turn, batch, calls)
        references.append(weakref.ref(rows))
        forwarded.append((kwargs["seed"], kwargs["force_settlement_detection"], kwargs["pending_injections"]))
        world.turn += 1
        return TurnResult(str(source_turn), TurnObservation(source_turn, world.turn, rows))

    def capture(snapshot, text, *_):
        assert all(ref() is None for ref in references)
        observed.append((snapshot.turn, text, snapshot.civ_stats["Civ0"].urban_agents,
                         snapshot.civ_stats["Civ1"].urban_agents))
        world.regions[0].controller = "Civ1"

    pending = []
    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    execute_run(runner_args(tmp_path, turns=2), world=world, on_turn=capture, pending_injections=pending)
    assert observed == [(1, "0", 1, 0), (2, "1", 0, 1)]
    assert [(seed, force) for seed, force, _ in forwarded] == [(42, False), (43, True)]
    assert all(injections is pending for _, _, injections in forwarded)


@pytest.mark.parametrize("error", ["source", "completed", "stamp", "stage"])
def test_rejects_wrong_explicit_handoff_stamp(
    error, make_world, tmp_path, monkeypatch, runner_bridge,
):
    world = make_world()
    callbacks = []

    def tick(world, **kwargs):
        source_turn = world.turn
        rows = RowsProbe(source_turn, pa.record_batch({"other": []}), [])
        if error == "stamp":
            rows.stamp = Stamp(source_turn - 1, "phase10_entry")
        elif error == "stage":
            rows.stamp = SimpleNamespace(source_turn=source_turn, stage="post_politics")
        world.turn += 1
        # Forge a foreign result to test the runner boundary independently of
        # production constructors, which already reject these invalid labels.
        return SimpleNamespace(chronicle_text="", observation=SimpleNamespace(
            source_turn=source_turn - (error == "source"),
            completed_turn=world.turn + (error == "completed"), phase10_agents=rows))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    with pytest.raises(AssertionError):
        execute_run(runner_args(tmp_path), world=world, on_turn=lambda *_: callbacks.append(1))
    assert callbacks == []
    assert world.turn == 1  # an invalid handoff does not roll back a mutated turn


@pytest.mark.parametrize("batch,exception", [
    (pa.record_batch({"settlement_id": [1]}), KeyError),
    (pa.record_batch({"civ_affinity": [0], "settlement_id": [None]}), TypeError),
])
def test_required_column_failures_remain_at_urban_access(
    batch, exception, make_world, tmp_path, monkeypatch, runner_bridge,
):
    world = make_world()

    def tick(world, **kwargs):
        source_turn = world.turn
        rows = RowsProbe(source_turn, batch, [])
        world.turn += 1
        return TurnResult("", TurnObservation(source_turn, world.turn, rows))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    with pytest.raises(exception):
        execute_run(runner_args(tmp_path), world=world)
    assert world.turn == 1


def test_off_mode_does_not_decode_supplied_rows(make_world, tmp_path, monkeypatch, runner_bridge):
    calls = []

    def tick(world, **kwargs):
        source_turn = world.turn
        rows = RowsProbe(source_turn, pa.record_batch({"settlement_id": [1]}), calls)
        world.turn += 1
        return TurnResult("", TurnObservation(source_turn, world.turn, rows))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    execute_run(runner_args(tmp_path, mode="off"), world=make_world())
    assert calls == []


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_checkpoint_rejects_agent_modes_without_retired_aliases(mode, make_world, tmp_path):
    world = make_world()
    world.agent_mode = mode
    assert not hasattr(world, "_agent_snapshot") and not hasattr(world, "_named_agents")
    with pytest.raises(replay.CheckpointError, match="unsupported agent mode"):
        replay.save_checkpoint(world, tmp_path / "checkpoint.json")
    assert not (tmp_path / "checkpoint.json").exists()


@pytest.mark.parametrize("name", ["_agent_bridge", "_economy_result", "_agent_snapshot", "_named_agents"])
def test_checkpoint_residual_guards_survive_cutover(name, make_world, tmp_path):
    world = make_world()
    setattr(world, name, {} if name == "_named_agents" else object())
    with pytest.raises(replay.CheckpointError):
        replay.save_checkpoint(world, tmp_path / "checkpoint.json")
    assert not (tmp_path / "checkpoint.json").exists()


def test_new_turn_module_changes_source_identity_and_rejects_checkpoint(make_world, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "checkpoint_replay.py").write_bytes(Path(replay.__file__).read_bytes())
    monkeypatch.setattr(replay, "__file__", str(source / "checkpoint_replay.py"))
    checkpoint = tmp_path / "checkpoint.json"
    replay.save_checkpoint(make_world(), checkpoint)
    before = replay._runtime_identity()["source_sha256"]
    (source / "turn_artifacts.py").write_text("# new contract module\n")
    after = replay._runtime_identity()["source_sha256"]
    assert before != after
    with pytest.raises(replay.CheckpointError, match="source/Python/dependency runtime mismatch"):
        replay.load_checkpoint(checkpoint)


def _evidence_reports(tmp_path):
    import json
    from scripts.a01_acceptance import BASELINE
    directories = [tmp_path / "baseline", tmp_path / "candidate"]
    for directory in directories:
        (directory / "artifacts").mkdir(parents=True)
        for name in ("turns.jsonl", "narrator.jsonl", "rng.jsonl"):
            (directory / name).write_text('[1,{"event":"same"}]\n')
        report = {"identity": {"head": BASELINE, "dirty": "", "native_source_sha256": {}, "source_sha256": {},
                                "committed_source_sha256": {}, "committed_native_source_sha256": {}},
                  "input": {"fixture_sha256": "frozen"}, "environment": {"python": "same"},
                  "driver_sha256": "same", "runtime": "Python off", "test_doubles": False,
                  "metrics": {}, "artifacts": {}, "checkpoint": None}
        (directory / "report.json").write_text(json.dumps(report))
    return directories


@pytest.mark.parametrize("kind", ["fixture", "environment", "baseline", "dirty", "native", "artifact", "hidden_source", "candidate_dirty", "candidate_hidden_source", "candidate_head"])
def test_evidence_comparison_rejects_identity_or_artifact_drift(kind, tmp_path):
    import json
    from scripts.a01_acceptance import compare
    baseline, candidate = _evidence_reports(tmp_path)
    path = (baseline if kind in ("baseline", "dirty", "hidden_source") else candidate) / "report.json"
    report = json.loads(path.read_text())
    if kind == "fixture":
        report["input"]["fixture_sha256"] = "changed"
    elif kind == "environment":
        report["environment"]["python"] = "changed"
    elif kind == "baseline":
        report["identity"]["head"] = "edf7299"
    elif kind in ("dirty", "candidate_dirty"):
        report["identity"]["dirty"] = " M src/chronicler/main.py"
    elif kind in ("hidden_source", "candidate_hidden_source"):
        report["identity"]["source_sha256"] = {"main.py": "unreported-change"}
    elif kind == "candidate_head":
        report["identity"]["head"] = "unexpected-candidate"
    elif kind == "native":
        report["identity"]["native_source_sha256"] = {"changed.rs": "changed"}
    else:
        (candidate / "artifacts" / "unrecorded.json").write_text('{}')
    path.write_text(json.dumps(report))
    result = compare(baseline, candidate, expected_candidate_head=(
        "expected-candidate" if kind == "candidate_head" else None))
    assert not result["exact_comparison_passed"]
    assert result["first_divergence"] is not None


@pytest.mark.parametrize("name", ["turns.jsonl", "narrator.jsonl", "rng.jsonl"])
def test_evidence_comparison_reports_first_record_and_field(name, tmp_path):
    from scripts.a01_acceptance import compare
    baseline, candidate = _evidence_reports(tmp_path)
    (candidate / name).write_text('[1,{"event":"changed"}]\n')
    result = compare(baseline, candidate)
    assert result["first_divergence"] == {"artifact": name, "record": 0, "path": "root[1].event"}


def test_evidence_doubles_cannot_claim_integrated_acceptance(tmp_path):
    import json
    from scripts.a01_acceptance import compare
    baseline, candidate = _evidence_reports(tmp_path)
    path = candidate / "report.json"
    report = json.loads(path.read_text())
    report["test_doubles"] = True
    path.write_text(json.dumps(report))
    result = compare(baseline, candidate)
    assert result["exact_comparison_passed"]
    assert not result["integrated_python_off_acceptance"]
    assert not result["integrated_acceptance"]


def test_evidence_diagnostics_keep_signed_zero_and_encoding(tmp_path):
    from scripts.a01_acceptance import compare
    baseline, candidate = _evidence_reports(tmp_path)
    (baseline / "turns.jsonl").write_text('[0.0]\n')
    (candidate / "turns.jsonl").write_text('[-0.0]\n')
    result = compare(baseline, candidate)
    assert result["first_divergence"]["path"] == "root[0]"
    (candidate / "turns.jsonl").write_text('[ 0.0 ]\n')
    assert compare(baseline, candidate)["first_divergence"]["path"] == "encoding/bytes"
