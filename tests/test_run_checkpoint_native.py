"""Exact checkpoints with the real native extension: agent modes, the
off-mode ecology/politics runtimes, shadow output and the war rosters'
simulator marker (chronicler.run_checkpoint, chronicler-agents/src/persist.rs).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import chronicler.run_checkpoint as rc
from chronicler.bundle_codec import load_bundle
from chronicler.main import execute_run

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"):
        cls = getattr(ca, name, None)
        if not isinstance(cls, type) or not hasattr(cls, "checkpoint_state"):
            pytest.skip("requires a chronicler_agents build with exact checkpoints")
    return ca


def _args(folder: Path, turns: int, agents: str, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents=agents, tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _content(path: Path) -> bytes:
    if path.name == "chronicle_bundle.json":
        data = load_bundle(path)
        data["metadata"].pop("generated_at", None)
        return json.dumps(data, sort_keys=True).encode()
    return path.read_bytes()


def _outputs(folder: Path, after: int = -1) -> dict[str, bytes]:
    """Every file but checkpoints and the per-turn sidecar files of turns up
    to ``after`` (written only by the run that played those turns)."""
    out = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt":
            continue
        stem = path.stem
        if "_turn_" in stem and int(stem.rsplit("_", 1)[1]) <= after:
            continue
        out[path.relative_to(folder).as_posix()] = _content(path)
    return out


@pytest.mark.parametrize("agents,extra", [
    ("hybrid", {"validation_sidecar": True}),
    ("demographics-only", {}),
    ("shadow", {}),
    ("off", {}),
])
def test_resume_identity_in_each_mode(tmp_path, agents, extra):
    _native()
    straight = tmp_path / "straight"
    execute_run(_args(straight, 14, agents, checkpoint_every=6,
                      checkpoint=str(straight / "c{turn}.ckpt"), **extra))
    header = rc.describe(straight / "c6.ckpt")
    names = [s["name"] for s in header["sections"]]
    if agents == "off":
        assert names == ["python", "native.ecology.0", "native.politics.0"]
    else:
        assert names == ["python", "native.agent.0"]
    assert header["run_config"]["agent_mode"] == agents
    for k in (6, 12):
        resumed = tmp_path / f"resumed_{k}"
        execute_run(_args(resumed, 14, "off"), checkpoint_resume=rc.read_checkpoint(straight / f"c{k}.ckpt"))
        expected = _outputs(straight, after=k)
        got = _outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []
    if agents == "shadow":
        assert "shadow.arrow" in got


def test_simulator_state_round_trips_and_refuses_another_simulator():
    ca = _native()
    sim = ca.AgentSimulator(num_regions=3, seed=42)
    blob = sim.checkpoint_state()
    again = ca.AgentSimulator.from_checkpoint_state(blob)
    assert again.checkpoint_state() == blob
    with pytest.raises(ValueError, match="kind"):
        ca.AgentSimulator.from_checkpoint_state(ca.EcologySimulator().checkpoint_state())
    with pytest.raises(ValueError, match="truncated"):
        ca.AgentSimulator.from_checkpoint_state(blob[:-1])
    with pytest.raises(ValueError, match="bad magic"):
        ca.PoliticsSimulator.from_checkpoint_state(b"x" * 40)
    version, fingerprint, schema = ca.AgentSimulator.checkpoint_schema()
    assert version == 1 and len(fingerprint) == 16 and "pool:AgentPool{ids:Vec<u32>," in schema


def test_war_roster_marker_is_rebound_to_the_restored_simulator(tmp_path):
    _native()
    straight = tmp_path / "straight"
    execute_run(_args(straight, 30, "hybrid", checkpoint_every=30,
                      checkpoint=str(straight / "c{turn}.ckpt")))
    loaded = rc.read_checkpoint(straight / "c30.ckpt")
    world, bridge = loaded.state.world, loaded.state.agent_bridge
    assert world._agent_bridge is bridge
    if loaded.state.markers.get("war_roster_bound"):
        assert world._war_roster_sim == id(bridge._sim)
    else:
        assert getattr(world, "_war_roster_sim", None) != id(bridge._sim)
