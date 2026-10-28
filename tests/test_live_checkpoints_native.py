"""Live checkpoints with the real native extension: a hybrid live session
(agent pool, validation sidecars) resumed from its checkpoints writes what
the uninterrupted session writes and shows a connecting viewer the same
history; off mode with the native ecology and politics runtimes as well
(chronicler.live_checkpoints, tests/live_session_harness.py)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import chronicler.run_checkpoint as rc
from chronicler.live_checkpoints import LIVE_CHECKPOINT_DIR
from tests.live_session_harness import outputs, session

pytestmark = pytest.mark.native

START = {"turns": 10, "civs": 3, "regions": 6, "seed": 42, "scenario": None}


@pytest.fixture(autouse=True)
def _native():
    ca = pytest.importorskip("chronicler_agents")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(ca, name, None)
        if not isinstance(cls, type) or not hasattr(cls, "checkpoint_state"):
            pytest.skip("requires a chronicler_agents build with exact checkpoints")


def _args(folder: Path, agents: str, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=None, turns=None, civs=None, regions=None, worldgen=None,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=5, llm_actions=False, scenario=None,
        simulate_only=True, agents=agents, local_url=None, live_port=0, pause_every=5,
        narrator="local", validation_sidecar=agents != "off",
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


@pytest.mark.parametrize("agents", ["hybrid", "off"])
def test_a_live_session_resumes_exactly(tmp_path, agents):
    _, plain, _ = session(_args(tmp_path / "plain", agents), start=START)
    straight = tmp_path / "straight"
    _, viewer, _ = session(_args(straight, agents, checkpoint_every=1,
                                 checkpoint=str(straight / "ckpt" / "turn_{turn:04d}.ckpt")),
                           start=START, at_pause={5: [("checkpoint",)]})
    assert outputs(tmp_path / "plain") == outputs(straight)
    assert plain.views == viewer.views and plain.final_view == viewer.final_view
    loaded_native = rc.read_checkpoint(straight / "ckpt" / "turn_0005.ckpt")
    natives = [s["name"] for s in loaded_native.header["sections"] if s["name"] != "python"]
    assert natives == (["native.agent.0"] if agents == "hybrid"
                       else ["native.ecology.0", "native.politics.0"])

    for k, path in [(2, straight / "ckpt" / "turn_0002.ckpt"),
                    (5, straight / LIVE_CHECKPOINT_DIR / "turn_0005.ckpt"),
                    (7, straight / "ckpt" / "turn_0007.ckpt")]:
        folder = tmp_path / f"resume_{k}"
        args = _args(folder, agents, resume=str(path), turns=10, seed=42, pause_every=None)
        _, resumed, _ = session(args, exact_resume=rc.read_checkpoint(path))
        assert resumed.pauses[0] == (k, "resumed")
        # The per-turn sidecar files of turns up to k are written by the run
        # that played them.
        assert outputs(folder) == outputs(straight, after=k), k
        assert {t: v for t, v in resumed.views.items() if t >= k} == \
            {t: v for t, v in viewer.views.items() if t >= k}
        assert resumed.final_view == viewer.final_view
