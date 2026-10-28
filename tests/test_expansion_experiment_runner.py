"""Evidence-harness failures, parent sharing and fresh-configuration boundary."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    spec = importlib.util.spec_from_file_location("expansion_runner", ROOT / "scripts/run_expansion_experiment.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._load_source(ROOT)
    return module


def _args(runner, path, *extra):
    return runner.build_parser().parse_args([
        "--feature", "harvest_forecasts", "--cohort", "development", "--seeds", "42",
        "--turns", "12", "--output-root", str(path), *extra,
    ])


def test_seed_ranges_do_not_manufacture_replicates():
    runner = _runner()
    assert runner.parse_seeds("7,0-2,42") == [0, 1, 2, 7, 42]
    for value in ("", "1,1", "2-1", "1-3,3", "-1", "true", "1-999999999"):
        with pytest.raises(ValueError):
            runner.parse_seeds(value)


def test_worker_calls_real_entrypoint_without_supplying_a_preconfigured_world(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler import main
    directory = tmp_path / "run"
    directory.mkdir()
    config = {"feature": "harvest_forecasts", "worldgen": "template", "regions": 8, "civs": 4}
    cli = runner._simulation_args(42, 4, directory, config, checkpoint=4)
    request = {"feature": "harvest_forecasts", "arm": "parent"}
    path = directory / "job.json"
    path.write_text(json.dumps({"source_root": str(ROOT), "simulation_args": cli, "request": request}))
    calls = []

    def capture(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(main, "execute_run", capture)
    runner.run_job(path)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert "world" not in kwargs and kwargs["checkpoint_resume"] is None
    assert kwargs["expansion_experiment"] == request
    assert args.harvest_forecasts is args.grain_reserves is args.contact_ledger is True
    assert args.health_care is args.ritual_gatherings is None
    assert args.agents == "hybrid" and args.simulate_only is True
    identity = json.loads((directory / "worker_identity.json").read_text())
    assert runner._identity_key(identity["before"]) == runner._identity_key(identity["after"])


def test_all_arms_reference_one_parent_and_keep_their_full_controls(tmp_path, monkeypatch):
    runner = _runner()
    from chronicler.ablation_arms import CHECKPOINT_TURN_FILENAME
    calls = []

    def execute(path, seed, horizon, args, request, env):
        path.mkdir(parents=True)
        calls.append((path, horizon, args, request))
        if request["arm"] == "parent":
            (path / CHECKPOINT_TURN_FILENAME.format(turn=4)).write_bytes(b"parent-fixture")
        return {"seed": seed, "arm": request["arm"], "status": "complete"}

    monkeypatch.setattr(runner, "_execute", execute)
    config = {"feature": "ritual_gatherings", "name": "registered", "cohort": "development",
              "registration": None, "controls": {}, "fork_turn": 4, "turns": 12,
              "worldgen": "template", "regions": 8, "civs": 4, "arms": list(runner.ARMS["ritual_gatherings"])}
    records = runner._seed_runs(42, tmp_path, config, {})
    assert len(records) == 5
    assert calls[0][3]["fork"] is False
    parents = [call[3]["parent_checkpoint"] for call in calls[1:]]
    assert all(parent == parents[0] for parent in parents)
    assert parents[0]["sha256"] == runner.file_sha256(Path(parents[0]["path"]))
    assert all(call[3]["fork"] is True and call[1] == 12 for call in calls[1:])
    assert {call[3]["arm"]: call[3]["controls"] for call in calls[1:]} == runner.ARMS["ritual_gatherings"]


def test_a_failed_parent_never_launches_its_treatment_arms(tmp_path, monkeypatch):
    runner = _runner()
    calls = []
    monkeypatch.setattr(runner, "_execute", lambda *a: calls.append(a) or {"status": "failed"})
    config = {"feature": "harvest_forecasts", "name": "test", "cohort": "development",
              "registration": None, "controls": {}, "fork_turn": 4, "turns": 12,
              "worldgen": "template", "regions": 8, "civs": 4, "arms": ["normal", "withheld"]}
    assert runner._seed_runs(42, tmp_path, config, {}) == [{"status": "failed"}]
    assert len(calls) == 1


def test_used_destinations_and_unregistered_control_changes_are_refused(tmp_path):
    runner = _runner()
    out = tmp_path / "used"
    out.mkdir()
    existing = out / "keep.txt"
    existing.write_text("preserve me")
    with pytest.raises(ValueError, match="not empty"):
        runner.run_experiment(_args(runner, out))
    assert existing.read_text() == "preserve me" and sorted(p.name for p in out.iterdir()) == ["keep.txt"]
    controls = tmp_path / "controls.json"
    controls.write_text('{"policy":"withhold"}')
    with pytest.raises(ValueError, match="arm-defining"):
        runner.run_experiment(_args(runner, tmp_path / "new", "--controls", str(controls)))
    assert not (tmp_path / "new").exists()
    with pytest.raises(ValueError, match="registration"):
        runner.run_experiment(_args(runner, tmp_path / "confirmatory", "--cohort", "confirmatory"))


@pytest.mark.parametrize("exit_code,completed", [(7, None), (0, 6)])
def test_failed_or_truncated_workers_are_hashed_failures_not_completed_runs(
    tmp_path, monkeypatch, exit_code, completed,
):
    runner = _runner()

    def child(command, **kwargs):
        if completed is not None:
            path = Path(command[-1]).parent / "chronicle_bundle.json"
            path.write_text(json.dumps({"world_state": {"turn": completed}, "metadata": {"seed": 42}}))
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(runner.subprocess, "run", child)
    row = runner._execute(tmp_path / "worker", 42, 12, [],
                          {"arm": "normal", "feature": "harvest_forecasts"}, {})
    assert row["status"] == "failed" and row["error"]["type"] == "RuntimeError"
    assert row["command"][-2] == "--job"
    assert "job.json" in row["files"] and "worker.log" in row["files"]
    assert "receipt" not in row


def test_source_changes_cannot_be_labelled_a_completed_experiment(tmp_path, monkeypatch):
    runner = _runner()
    before = {"git_sha": "before", "package_digest": "same"}
    after = {"git_sha": "after", "package_digest": "changed"}
    source = iter([before, after])
    monkeypatch.setattr(runner, "source_identity", lambda: next(source))
    native = runner.native_identity()

    def seed_runs(seed, root, config, env):
        return [{"seed": seed, "arm": arm, "status": "complete", "receipt": {
            "source": before, "native": native}} for arm in ("parent", *config["arms"])]

    monkeypatch.setattr(runner, "_seed_runs", seed_runs)
    manifest = runner.run_experiment(_args(runner, tmp_path / "changed"))
    assert manifest["status"] == "failed" and manifest["identities_stable"] is False
    saved = json.loads((tmp_path / "changed" / runner.MANIFEST).read_text())
    assert saved["source_after"] == after and len(saved["runs"]) == 4


def test_worker_import_source_labels_do_not_confuse_identical_native_bytes():
    runner = _runner()
    left = {"source": {"git_sha": "a", "package_digest": "b"},
            "native": {"status": "found", "source": "import_path", "sha256": "c"}}
    right = {"source": left["source"],
             "native": {"status": "found", "source": "imported", "sha256": "c"}}
    assert runner._identity_key(left) == runner._identity_key(right)
