"""--agent-scale-mode plumbing: CLI -> execute_run -> AgentBridge -> native."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import chronicler.agent_bridge as agent_bridge
import chronicler.main as cli
from chronicler.world_gen import generate_world


def _parse(*extra: str):
    return cli._build_parser().parse_args(
        ["--seed", "3", "--turns", "2", "--civs", "2", "--regions", "4", *extra]
    )


def test_cli_option_defaults_to_unset_and_accepts_both_modes():
    assert _parse().agent_scale_mode is None
    assert _parse("--agent-scale-mode", "exact").agent_scale_mode == "exact"
    assert _parse("--agent-scale-mode", "fast").agent_scale_mode == "fast"


def test_cli_option_rejects_unknown_mode(capsys):
    with pytest.raises(SystemExit):
        _parse("--agent-scale-mode", "approximate")
    assert "invalid choice" in capsys.readouterr().err


def test_fast_mode_requires_an_agent_pool(tmp_path):
    args = _parse(
        "--agents", "off", "--agent-scale-mode", "fast", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"),
    )
    with pytest.raises(ValueError, match="agent-scale-mode fast requires an agent pool"):
        cli.execute_run(args)


def _fake_simulator(monkeypatch, *, has_mode_api: bool = True) -> MagicMock:
    instance = MagicMock(name="AgentSimulator()")
    if not has_mode_api:
        del instance.set_agent_scale_mode
    cls = MagicMock(name="AgentSimulator", return_value=instance)
    monkeypatch.setattr(agent_bridge, "_load_agent_simulator_class", lambda: cls)
    return instance


def _world():
    return generate_world(seed=5, num_regions=4, num_civs=2)


def test_exact_mode_makes_no_native_mode_call(monkeypatch):
    sim = _fake_simulator(monkeypatch)
    bridge = agent_bridge.AgentBridge(_world(), mode="hybrid")
    assert bridge.agent_scale_mode == "exact"
    sim.set_agent_scale_mode.assert_not_called()
    bridge = agent_bridge.AgentBridge(_world(), mode="hybrid", agent_scale_mode="exact")
    sim.set_agent_scale_mode.assert_not_called()


def test_fast_mode_is_sent_to_the_native_simulator(monkeypatch):
    sim = _fake_simulator(monkeypatch)
    bridge = agent_bridge.AgentBridge(_world(), mode="demographics-only", agent_scale_mode="fast")
    assert bridge.agent_scale_mode == "fast"
    sim.set_agent_scale_mode.assert_called_once_with("fast")


def test_unknown_mode_is_rejected_before_construction(monkeypatch):
    _fake_simulator(monkeypatch)
    with pytest.raises(ValueError, match="agent_scale_mode"):
        agent_bridge.AgentBridge(_world(), mode="hybrid", agent_scale_mode="turbo")


def test_fast_mode_needs_a_current_extension(monkeypatch):
    _fake_simulator(monkeypatch, has_mode_api=False)
    with pytest.raises(RuntimeError, match="predates agent scale modes"):
        agent_bridge.AgentBridge(_world(), mode="hybrid", agent_scale_mode="fast")
    # Exact mode still works with an older extension.
    agent_bridge.AgentBridge(_world(), mode="hybrid")


def _native():
    native = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(native, "AgentSimulator", None), type):
        pytest.skip("chronicler_agents is not a compiled extension")
    if not hasattr(native.AgentSimulator, "set_agent_scale_mode"):
        pytest.skip("installed chronicler_agents predates agent scale modes")
    return native


@pytest.mark.native
def test_native_mode_api_round_trip():
    native = _native()
    sim = native.AgentSimulator(num_regions=3, seed=1)
    assert sim.agent_scale_mode == "exact"
    sim.set_agent_scale_mode("fast")
    assert sim.agent_scale_mode == "fast"
    sim.set_agent_scale_mode("exact")
    assert sim.agent_scale_mode == "exact"
    with pytest.raises(ValueError, match="exact' or 'fast"):
        sim.set_agent_scale_mode("bogus")


def _run_digests(tmp_path: Path, name: str, *extra: str) -> dict[str, str]:
    out = tmp_path / name
    args = cli._build_parser().parse_args([
        "--seed", "11", "--turns", "12", "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(out / "chronicle.md"), "--state", str(out / "state.json"), *extra,
    ])
    cli.execute_run(args)
    digests = {}
    for path in sorted(out.iterdir()):
        if path.name == "chronicle_bundle.json":
            continue  # carries a wall-clock generated_at
        digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


@pytest.mark.native
def test_explicit_exact_mode_is_byte_identical_to_default(tmp_path):
    _native()
    default = _run_digests(tmp_path, "default")
    exact = _run_digests(tmp_path, "exact", "--agent-scale-mode", "exact")
    assert default == exact
    assert "state.json" in default


@pytest.mark.native
def test_fast_mode_runs_deterministically(tmp_path):
    _native()
    first = _run_digests(tmp_path, "fast1", "--agent-scale-mode", "fast")
    second = _run_digests(tmp_path, "fast2", "--agent-scale-mode", "fast")
    assert first == second
