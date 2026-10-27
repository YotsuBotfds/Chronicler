"""Decision ablations with the real native extension: the switch, its
checkpoint state, the shared history before the start turn, and a fork from
a plain run's checkpoint equal to a run ablated from the same turn
(chronicler-agents/src/scale.rs, chronicler.decision_ablation)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from chronicler.main import execute_run

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    sim = getattr(ca, "AgentSimulator", None)
    if not isinstance(sim, type) or not hasattr(sim, "set_decision_ablation"):
        pytest.skip("requires a chronicler_agents build with decision ablations")
    return ca


def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _events(folder: Path) -> list[tuple]:
    import pyarrow.ipc as ipc
    table = ipc.open_file(folder / "agent_events.arrow").read_all().to_pydict()
    return [tuple(table[c][i] for c in table) for i in range(len(table["turn"]))]


def test_switch_validates_names_and_survives_a_checkpoint():
    ca = _native()
    sim = ca.AgentSimulator(num_regions=4, seed=7)
    assert sim.decision_ablation == ([], 0)
    with pytest.raises(ValueError, match="decision ablation must be"):
        sim.set_decision_ablation(["terms"], 3)
    sim.set_decision_ablation(["kin_roots"], 31)
    assert sim.decision_ablation == (["kin_roots"], 31)
    restored = ca.AgentSimulator.from_checkpoint_state(bytes(sim.checkpoint_state()))
    assert restored.decision_ablation == (["kin_roots"], 31)
    sim.set_decision_ablation([], 31)
    assert sim.decision_ablation == ([], 0)
    _version, _fingerprint, schema = ca.AgentSimulator.checkpoint_schema()
    assert "ablation:DecisionAblation{mask:u8,start_turn:u32,}" in schema


@pytest.mark.parametrize("arm", ["needs", "placebo"])
def test_an_ablated_run_shares_the_plain_history_until_its_start(tmp_path, arm):
    _native()
    execute_run(_args(tmp_path / "plain", 16))
    execute_run(_args(tmp_path / "arm", 16, decision_ablation=arm, ablation_start_turn=9))
    plain, ablated = _events(tmp_path / "plain"), _events(tmp_path / "arm")
    assert [e for e in plain if e[0] < 9] == [e for e in ablated if e[0] < 9]
    if arm == "placebo":
        # Every decision draw comes from another stream from turn 9 on.
        assert [e for e in plain if e[0] >= 9] != [e for e in ablated if e[0] >= 9]
    bundle = json.loads((tmp_path / "arm" / "chronicle_bundle.json").read_text(encoding="utf-8"))
    assert bundle["metadata"]["decision_ablation"] == {"name": arm, "start_turn": 9, "forked_at": None}
    plain_bundle = json.loads((tmp_path / "plain" / "chronicle_bundle.json").read_text(encoding="utf-8"))
    assert "decision_ablation" not in plain_bundle["metadata"]


def test_a_fork_from_a_plain_checkpoint_equals_a_run_ablated_from_that_turn(tmp_path):
    _native()
    from chronicler.run_checkpoint import read_checkpoint

    execute_run(_args(tmp_path / "plain", 18, checkpoint_turns=(9,)))
    checkpoint = tmp_path / "plain" / "checkpoint_turn_9.ckpt"
    assert checkpoint.is_file()
    fork = _args(tmp_path / "fork", 18, resume=str(checkpoint), decision_ablation="needs", ablation_start_turn=9)
    execute_run(fork, checkpoint_resume=read_checkpoint(checkpoint))
    execute_run(_args(tmp_path / "straight", 18, decision_ablation="needs", ablation_start_turn=9))
    assert _events(tmp_path / "fork") == _events(tmp_path / "straight")
    fork_meta = json.loads((tmp_path / "fork" / "chronicle_bundle.json").read_text(encoding="utf-8"))["metadata"]
    assert fork_meta["decision_ablation"] == {"name": "needs", "start_turn": 9, "forked_at": 9}
