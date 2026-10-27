"""Decision ablations: the CLI switch, checkpoint forks and the batch
manifest's argument groups (chronicler.decision_ablation; native behaviour in
tests/test_decision_ablation_native.py)."""
from __future__ import annotations

import argparse

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
    assert calls == [(["needs"], 101), (["kin_roots"], 101), (["placebo"], 101)]
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


def test_gate_runner_forks_only_the_subset_and_full_profiles():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "m53b_run_validation.py"
    spec = importlib.util.spec_from_file_location("m53b_run_validation_ablation", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    for profile, turns, expected in (("full", 500, ["--checkpoint-turns", "101,201,301,401"]),
                                     ("full", 300, ["--checkpoint-turns", "101,201"]),
                                     ("subset", 200, ["--checkpoint-turns", "101"])):
        args = _ns(profile=profile, turns=turns, ablation_oracles=None)
        assert runner.ablation_enabled(args)
        assert runner._ablation_args(args) == expected
    assert not runner.ablation_enabled(_ns(profile="full", turns=500, ablation_oracles=False))
    assert runner._ablation_args(_ns(profile="full", turns=500, ablation_oracles=False)) == []
    assert not runner.ablation_enabled(_ns(profile="determinism-hybrid", turns=200, ablation_oracles=None))
    assert runner._ablation_dir_for(Path("/x/full_gate/batch_42")) == Path("/x/full_gate/ablation_42")
