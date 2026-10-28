"""Interactive checkpoints with the real native extension: a hybrid session
(agent pool, validation sidecars) and an off session with the native
ecology and politics runtimes, with a stat set and an injection at a pause,
resumed from checkpoints before, at and after it, write what the
uninterrupted session writes (chronicler.interactive)."""
from __future__ import annotations

from pathlib import Path

import pytest

import chronicler.interactive as interactive
import chronicler.run_checkpoint as rc
from tests.live_session_harness import outputs
from tests.test_interactive_checkpoints import Terminal, _args

pytestmark = pytest.mark.native

TURNS = 10


@pytest.fixture(autouse=True)
def _native():
    ca = pytest.importorskip("chronicler_agents")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(ca, name, None)
        if not isinstance(cls, type) or not hasattr(cls, "checkpoint_state"):
            pytest.skip("requires a chronicler_agents build with exact checkpoints")


def _native_args(folder: Path, agents: str, **extra):
    return _args(folder, turns=TURNS, agents=agents, reflection_interval=5, pause_every=5,
                 validation_sidecar=agents != "off", **extra)


@pytest.mark.parametrize("agents", ["hybrid", "off"])
def test_an_interactive_session_resumes_exactly(tmp_path, monkeypatch, agents):
    from chronicler.world_gen import generate_world
    civ = generate_world(seed=42, num_regions=6, num_civs=3).civilizations[0].name
    script = {5: [f'set "{civ}" military 90', f'inject plague "{civ}"']}
    Terminal(monkeypatch, at_pause=script)
    interactive.run_interactive(_native_args(tmp_path / "plain", agents))
    straight = tmp_path / "straight"
    Terminal(monkeypatch, at_pause=script)
    interactive.run_interactive(_native_args(
        straight, agents, checkpoint_every=1,
        checkpoint=str(straight / "ckpt" / "turn_{turn:04d}.ckpt")))
    assert outputs(tmp_path / "plain") == outputs(straight)
    loaded = rc.read_checkpoint(straight / "ckpt" / "turn_0005.ckpt")
    assert [i["command"] for i in loaded.state.run_config["interventions"]] == ["set", "inject"]
    natives = [s["name"] for s in loaded.header["sections"] if s["name"] != "python"]
    assert natives == (["native.agent.0"] if agents == "hybrid"
                       else ["native.ecology.0", "native.politics.0"])

    for k in (2, 5, 7):
        folder = tmp_path / f"resume_{k}"
        path = straight / "ckpt" / f"turn_{k:04d}.ckpt"
        terminal = Terminal(monkeypatch, at_pause={t: lines for t, lines in script.items() if t > k})
        interactive.run_interactive(_native_args(folder, agents, resume=str(path)),
                                    exact_resume=rc.read_checkpoint(path))
        assert terminal.pauses[0] == (k, "resumed")
        # The per-turn sidecar files of turns up to k are written by the run
        # that played them.
        assert outputs(folder) == outputs(straight, after=k), k
