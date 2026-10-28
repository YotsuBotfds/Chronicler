"""Decision ablations: the CLI switch, checkpoint forks and the batch
manifest's argument groups (chronicler.decision_ablation; native behaviour in
tests/test_decision_ablation_native.py)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from chronicler.decision_ablation import (
    DECISION_ABLATIONS,
    apply_decision_ablation,
    decision_ablation_from_args,
)


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_no_ablation_by_default():
    assert decision_ablation_from_args(_ns(), "hybrid") is None
    assert decision_ablation_from_args(_ns(decision_ablation=None, ablation_start_turn=None), "off") is None


@pytest.mark.parametrize("kw, agents, message", [
    ({"decision_ablation": "needs"}, "hybrid", "requires --ablation-start-turn"),
    ({"ablation_start_turn": 5}, "hybrid", "requires --decision-ablation"),
    ({"decision_ablation": "terms", "ablation_start_turn": 5}, "hybrid", "must be one of"),
    ({"decision_ablation": "needs", "ablation_start_turn": -1}, "hybrid", "integer >= 0"),
    ({"decision_ablation": "needs", "ablation_start_turn": True}, "hybrid", "integer >= 0"),
    ({"decision_ablation": "needs", "ablation_start_turn": 5}, "off", "requires an agent pool"),
])
def test_ablation_arguments_are_checked(kw, agents, message):
    with pytest.raises(ValueError, match=message):
        decision_ablation_from_args(_ns(**kw), agents)


def test_ablation_is_sent_to_the_simulator_only_when_requested():
    calls = []

    class Sim:
        def set_decision_ablation(self, names, start):
            calls.append((names, start))

    apply_decision_ablation(Sim(), None)
    assert calls == []
    for name in DECISION_ABLATIONS:
        apply_decision_ablation(Sim(), (name, 101))
    assert calls == [(["needs"], 101), (["kin_roots"], 101), (["placebo"], 101), (["community_anchor"], 101)]
    with pytest.raises(RuntimeError, match="predates decision ablations"):
        apply_decision_ablation(object(), ("needs", 1))


def test_cli_parses_the_switch_and_checkpoint_turns():
    from chronicler.main import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--decision-ablation", "kin_roots", "--ablation-start-turn", "101",
                              "--checkpoint-turns", "301,101,201,101"])
    assert (args.decision_ablation, args.ablation_start_turn) == ("kin_roots", 101)
    assert args.checkpoint_turns == (101, 201, 301)
    for bad in ("0", "x", ""):
        with pytest.raises(SystemExit):
            parser.parse_args(["--checkpoint-turns", bad])
    with pytest.raises(SystemExit):
        parser.parse_args(["--decision-ablation", "terms"])
    plain = parser.parse_args([])
    assert plain.decision_ablation is None and plain.checkpoint_turns is None


def test_manifest_groups_the_new_arguments():
    from chronicler.batch_manifest import NON_SIMULATION_ARG_KEYS, SIMULATION_ARG_KEYS

    assert {"decision_ablation", "ablation_start_turn"} <= set(SIMULATION_ARG_KEYS)
    assert "checkpoint_turns" in NON_SIMULATION_ARG_KEYS


class _Loaded:
    def __init__(self, simulation_args, turn=101):
        class World:
            pass
        world = World()
        world.turn = turn
        self.state = argparse.Namespace(run_config={"simulation_args": simulation_args, "output_args": {}},
                                        seed=42, num_turns=500, world=world)


def test_an_exact_resume_may_add_an_ablation_but_not_change_one():
    from chronicler.main import _adopt_checkpoint_args, _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--resume", "x.ckpt", "--decision-ablation", "needs", "--ablation-start-turn", "101",
                              "--turns", "122"])
    saved = {"decision_ablation": None, "ablation_start_turn": None, "turns": 500, "agents": "hybrid"}
    assert _adopt_checkpoint_args(parser, args, _Loaded(saved)) == []
    assert (args.decision_ablation, args.ablation_start_turn, args.agents) == ("needs", 101, "hybrid")
    args = parser.parse_args(["--resume", "x.ckpt", "--decision-ablation", "placebo", "--ablation-start-turn", "101"])
    conflicts = _adopt_checkpoint_args(parser, args, _Loaded({**saved, "decision_ablation": "needs",
                                                              "ablation_start_turn": 101}))
    assert conflicts == ["--decision-ablation 'placebo' conflicts with the checkpoint (saved: 'needs')"]


def test_fork_ablation_switches_the_restored_simulator():
    from chronicler.main import _fork_ablation

    class Sim:
        calls = []

        def set_decision_ablation(self, names, start):
            self.calls.append((names, start))

    bridge = argparse.Namespace(_sim=Sim(), decision_ablation=None)
    run_config = {"agent_mode": "hybrid", "simulation_args": {"decision_ablation": None, "turns": 500}}
    _fork_ablation(_ns(decision_ablation=None, ablation_start_turn=None), run_config, bridge, 101)
    assert Sim.calls == [] and "decision_ablation" not in run_config
    _fork_ablation(_ns(decision_ablation="needs", ablation_start_turn=101), run_config, bridge, 101)
    assert Sim.calls == [(["needs"], 101)]
    assert run_config["decision_ablation"] == {"name": "needs", "start_turn": 101, "forked_at": 101}
    assert run_config["simulation_args"]["decision_ablation"] == "needs"
    assert bridge.decision_ablation == ("needs", 101)
    # Resuming the ablated run with its own ablation changes nothing; another is refused.
    _fork_ablation(_ns(decision_ablation="needs", ablation_start_turn=101), run_config, bridge, 150)
    assert Sim.calls == [(["needs"], 101)]
    with pytest.raises(ValueError, match="already runs decision ablation"):
        _fork_ablation(_ns(decision_ablation="placebo", ablation_start_turn=101), run_config, bridge, 150)
    fresh = {"agent_mode": "hybrid", "simulation_args": {}}
    with pytest.raises(ValueError, match="before the checkpoint's turn"):
        _fork_ablation(_ns(decision_ablation="needs", ablation_start_turn=50), fresh, bridge, 101)


@pytest.mark.parametrize("lean_output", [False, True])
def test_ablation_arms_fork_every_seed_and_record_the_manifest(tmp_path, monkeypatch, lean_output):
    pytest.importorskip("pyarrow")
    import json
    import subprocess

    import pyarrow as pa
    import pyarrow.ipc as ipc

    from chronicler import ablation_arms

    batch = tmp_path / "batch_42"
    for seed in (42, 43):
        (batch / f"seed_{seed}").mkdir(parents=True)
        for turn in (101, 201):
            (batch / f"seed_{seed}" / f"checkpoint_turn_{turn}.ckpt").write_bytes(b"ckpt")
    (batch / "batch_manifest.json").write_text(json.dumps({
        "status": "complete", "turns": 300, "runs": [{"seed": 42, "dir": "seed_42"}, {"seed": 43, "dir": "seed_43"}],
    }), encoding="utf-8")
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append((cmd, kwargs["env"].get("RAYON_NUM_THREADS")))
        out = Path(cmd[cmd.index("--output") + 1]).parent
        table = pa.table({"turn": pa.array([1], pa.uint32()), "agent_id": pa.array([1], pa.uint32()),
                          "event_type": pa.array(["migration"])})
        with ipc.new_file(out / "agent_events.arrow", table.schema) as writer:
            writer.write_table(table)
        start = int(cmd[cmd.index("--ablation-start-turn") + 1])
        arm = cmd[cmd.index("--decision-ablation") + 1]
        info = {
            "seed": int(Path(cmd[cmd.index("--resume") + 1]).parent.name.split("_")[-1]),
            "total_turns": int(cmd[cmd.index("--turns") + 1]), "resume": None,
            "decision_ablation": {"name": arm, "start_turn": start, "forked_at": start},
        }
        if "--ablation-output" in cmd:
            from chronicler.artifact_io import atomic_write_json
            atomic_write_json(out / "fork.json", info)
        else:
            (out / "chronicle_bundle.json").write_text(json.dumps({"metadata": info}), encoding="utf-8")
        (out / "memories_x.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ablation_arms.subprocess, "run", fake_run)
    manifest = ablation_arms.run_ablation_arms(batch, tmp_path / "ablation_42", arms=["needs", "kin_roots"],
                                              total_turns=300, parallel=2, env={}, lean_output=lean_output, log=lambda *_: None)
    assert manifest["status"] == "complete" and manifest["fork_count"] == 8
    assert manifest["fork_turns"] == [100, 200]
    first = sorted(cmd for cmd, _env in commands)[0]
    assert first[first.index("--turns") + 1] == "122" and first[first.index("--ablation-start-turn") + 1] == "101"
    assert {threads for _cmd, threads in commands} == {"1"}
    fork = tmp_path / "ablation_42" / "needs" / "seed_42" / "fork_100"
    assert sorted(p.name for p in fork.iterdir()) == ["agent_events.arrow", "fork.json"]
    assert not list(batch.rglob("*.ckpt")), "a seed's checkpoints go once its forks ran"
    written = json.loads((tmp_path / "ablation_42" / "ablation_manifest.json").read_text(encoding="utf-8"))
    assert written["forks"][0]["files"]["agent_events.arrow"]
    with pytest.raises(Exception, match="not empty"):
        ablation_arms.run_ablation_arms(batch, tmp_path / "ablation_42", total_turns=300, env={})


def _load_runner():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "m53b_run_validation.py"
    spec = importlib.util.spec_from_file_location("m53b_run_validation_ablation", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_gate_runner_forks_the_full_profile_by_default_and_subsets_on_request():
    from pathlib import Path

    runner = _load_runner()
    for profile, turns, expected in (("full", 500, ["--checkpoint-turns", "101,201,301,401"]),
                                     ("full", 300, ["--checkpoint-turns", "101,201"])):
        args = _ns(profile=profile, turns=turns, ablation_oracles=None)
        assert runner.ablation_enabled(args)
        assert runner._ablation_args(args) == expected
    # A subset cannot measure the safety pairing: its arms are opt-in.
    assert not runner.ablation_enabled(_ns(profile="subset", turns=200, ablation_oracles=None))
    assert runner._ablation_args(_ns(profile="subset", turns=200, ablation_oracles=None)) == []
    assert runner._ablation_args(_ns(profile="subset", turns=200, ablation_oracles=True)) == [
        "--checkpoint-turns", "101"]
    assert not runner.ablation_enabled(_ns(profile="full", turns=500, ablation_oracles=False))
    assert runner._ablation_args(_ns(profile="full", turns=500, ablation_oracles=False)) == []
    assert not runner.ablation_enabled(_ns(profile="determinism-hybrid", turns=200, ablation_oracles=True))
    assert runner._ablation_dir_for(Path("/x/full_gate/batch_42")) == Path("/x/full_gate/ablation_42")


def test_gate_runner_causal_oracles_are_off_by_default_and_need_the_arms(monkeypatch, tmp_path):
    runner = _load_runner()
    assert runner.require_causal(_ns(require_causal_oracles=None)) is False
    assert runner.require_causal(_ns(require_causal_oracles=True)) is True
    for argv in (["--profile", "subset", "--require-causal-oracles"],
                 ["--profile", "full", "--no-ablation-oracles", "--require-causal-oracles"]):
        monkeypatch.setattr(runner.sys, "argv",
                            ["m53b_run_validation.py", *argv, "--output-root", str(tmp_path / "out")])
        with pytest.raises(SystemExit) as exc_info:
            runner.main()
        assert exc_info.value.code == 2


@pytest.mark.parametrize("require, flag, ok", [
    (None, None, True), (False, "--no-require-causal-oracles", True), (True, "--require-causal-oracles", False),
])
def test_gate_runner_passes_the_causal_mode_to_validate_and_the_gate(monkeypatch, tmp_path, require, flag, ok):
    import json
    import subprocess

    runner = _load_runner()
    cohort = {"status": "PASS", "method_version": 4, "observational_status": "PASS",
              "ablation": {"status": "FAIL", "reason": "members' migration rate ratio 0.99"}}
    report = {"batch_dir": str(tmp_path), "results": {
        "community": {"status": "PASS"}, "needs": {"status": "PASS"}, "cohort": cohort}}
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(report), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.validate_batch(tmp_path, "validate_report_subset.json", tmp_path, {}, "subset",
                          require_causal_oracles=require)
    passed = [arg for arg in calls[0] if "causal" in arg]
    assert passed == ([flag] if flag else [])
    decision = json.loads((tmp_path / "gate_decision_subset.json").read_text(encoding="utf-8"))
    assert decision["ok"] is ok
    assert decision["causal_oracles_required"] is bool(require)
    summary = (tmp_path / "gate_summary_subset.md").read_text(encoding="utf-8")
    assert ("## Causal evidence (required)" if require else "## Causal evidence (not yet required)") in summary
