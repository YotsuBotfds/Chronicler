"""Internal output policy and fail-closed ablation artifact handling."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler import ablation_arms as aa
from chronicler.main import _adopt_checkpoint_args, _build_parser, execute_run


def test_output_profile_is_hidden_output_only_and_explicitly_overridable():
    from chronicler.batch_manifest import OUTPUT_ARG_KEYS, SIMULATION_ARG_KEYS

    parser = _build_parser()
    assert parser.parse_args([]).ablation_output is False
    assert parser.parse_args(["--ablation-output"]).ablation_output is True
    assert "--ablation-output" not in parser.format_help()
    assert "ablation_output" in OUTPUT_ARG_KEYS
    assert "ablation_output" not in SIMULATION_ARG_KEYS
    # A parent checkpoint's ordinary profile must not undo the worker's choice.
    state = SimpleNamespace(run_config={"output_args": {"ablation_output": False}},
                            seed=42, num_turns=122, world=SimpleNamespace(turn=101))
    args = parser.parse_args(["--ablation-output"])
    assert _adopt_checkpoint_args(parser, args, SimpleNamespace(state=state)) == []
    assert args.ablation_output is True


@pytest.mark.parametrize("changes,loaded,match", [
    ({}, False, "compatible exact checkpoint"),
    ({}, "mismatched", "compatible exact checkpoint"),
    ({}, True, "decision-ablation arm"),
    ({"decision_ablation": "needs", "simulate_only": False}, True, "simulate-only"),
    ({"decision_ablation": "needs", "narrator": "api"}, True, "local narrator"),
    ({"decision_ablation": "needs", "live": True}, True, "noninteractive"),
])
def test_profile_rejects_inappropriate_calls_before_world_or_native_work(tmp_path, monkeypatch, changes, loaded, match):
    parser = _build_parser()
    args = parser.parse_args(["--seed", "42", "--turns", "122", "--simulate-only", "--ablation-output"])
    args.output, args.state = str(tmp_path / "chronicle.md"), str(tmp_path / "state.json")
    for key, value in changes.items():
        setattr(args, key, value)
    checkpoint = None
    if loaded:
        checkpoint = SimpleNamespace(state=SimpleNamespace(seed=42, scenario_config=None, run_config={}, world=SimpleNamespace(turn=101)),
                                     mismatches=["different native build"] if loaded == "mismatched" else [])
    def unexpected(*args, **kwargs):
        pytest.fail("invalid output profile reached world/native setup")
    monkeypatch.setattr("chronicler.main.generate_world", unexpected)
    monkeypatch.setattr("chronicler.main.NarrativeEngine", unexpected)
    with pytest.raises(ValueError, match=match):
        execute_run(args, checkpoint_resume=checkpoint)
    assert not list(tmp_path.iterdir())


def _batch(tmp_path):
    batch = tmp_path / "plain"
    for seed in (42, 43):
        directory = batch / f"seed_{seed}"
        directory.mkdir(parents=True)
        (directory / "checkpoint_turn_101.ckpt").write_bytes(b"exact checkpoint")
    (batch / "batch_manifest.json").write_text(json.dumps({
        "status": "complete", "turns": 122,
        "runs": [{"seed": seed, "dir": f"seed_{seed}"} for seed in (42, 43)],
    }))
    return batch


def _write_outputs(cmd, failure):
    import pyarrow as pa
    import pyarrow.ipc as ipc
    from chronicler.artifact_io import atomic_write_json

    out = Path(cmd[cmd.index("--output") + 1]).parent
    seed = int(Path(cmd[cmd.index("--resume") + 1]).parent.name.rsplit("_", 1)[1])
    table = pa.table({"turn": [100], "agent_id": [1], "event_type": ["migration"]})
    with ipc.new_file(out / aa.FORK_EVENTS_FILENAME, table.schema) as writer:
        writer.write_table(table)
    info = {"seed": seed, "total_turns": 122, "resume": None,
            "decision_ablation": {"name": "needs", "start_turn": 101, "forked_at": 101}}
    # Seed 42 succeeds first: a later failure must preserve its checkpoint too.
    if seed == 43:
        if failure == "horizon":
            info["total_turns"] = 121
        elif failure == "identity":
            info["seed"] = 99
        elif failure == "ablation":
            info["decision_ablation"]["forked_at"] = 100
        elif failure == "missing-events":
            (out / aa.FORK_EVENTS_FILENAME).unlink()
    (out / "discardable.txt").write_text("retain on failure")
    if "--ablation-output" in cmd:
        if seed != 43 or failure != "missing-receipt":
            atomic_write_json(out / aa.FORK_INFO_FILENAME, info)
    else:
        atomic_write_json(out / "chronicle_bundle.json", {"metadata": info})
    return subprocess.CompletedProcess(cmd, 0, "worker stdout", "worker stderr")


@pytest.mark.parametrize("failure", ["horizon", "identity", "ablation", "missing-events", "missing-receipt", "launch", "exit"])
def test_failed_or_incomplete_workers_write_failed_manifest_and_preserve_all_checkpoints(tmp_path, monkeypatch, failure):
    pytest.importorskip("pyarrow")
    batch = _batch(tmp_path)
    out_root = tmp_path / "forks"
    def worker(cmd, **kwargs):
        if "seed_43" in cmd[cmd.index("--resume") + 1]:
            if failure == "launch":
                raise OSError("cannot launch test worker")
            if failure == "exit":
                return subprocess.CompletedProcess(cmd, 9, "incomplete", "test failure")
        return _write_outputs(cmd, failure)
    monkeypatch.setattr(aa.subprocess, "run", worker)
    with pytest.raises(RuntimeError, match="1 ablation fork"):
        aa.run_ablation_arms(batch, out_root, arms=["needs"], total_turns=122, env={}, log=lambda *_: None)
    manifest = json.loads((out_root / aa.ABLATION_MANIFEST_FILENAME).read_text())
    assert manifest["status"] == "failed" and len(manifest["failures"]) == 1
    assert manifest["fork_count"] == 1
    assert len(list(batch.rglob("*.ckpt"))) == 2
    failed = aa.fork_dir(out_root, "needs", "seed_43", 100)
    assert (failed / "fork.log").is_file()
    if failure not in ("launch", "exit"):
        assert (failed / "discardable.txt").read_text() == "retain on failure"
    with pytest.raises(Exception, match="not empty"):
        aa.run_ablation_arms(batch, out_root, total_turns=122, env={})


def test_duplicate_arm_names_fail_before_creating_a_study(tmp_path):
    with pytest.raises(ValueError, match="arms must be unique"):
        aa.run_ablation_arms(tmp_path / "plain", tmp_path / "forks", arms=["needs", "needs"], total_turns=122)
    assert not (tmp_path / "forks").exists()
