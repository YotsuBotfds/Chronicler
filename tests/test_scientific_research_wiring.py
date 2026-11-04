"""Shared research configuration and exact continuation, without native claims."""
import pickle
from types import SimpleNamespace

import pytest

from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.expansion_features import expansion_arguments
from chronicler.main import _adopt_checkpoint_args
from test_expansion_feature_wiring import (
    _args, _gate_runner, _parser, _world, configure_without_native,
)
from test_scientific_research import advance, research_world


def test_research_switch_is_tristate_and_omitted_configuration_stays_legacy():
    assert "scientific_research_agendas" in SIMULATION_ARG_KEYS
    for flags, expected in (([], None), (["--scientific-research-agendas"], True),
                            (["--no-scientific-research-agendas"], False)):
        args = _parser().parse_args(flags)
        assert args.scientific_research_agendas is expected
        config = simulation_config(args)
        if expected is None:
            assert "scientific_research_agendas" not in config
            assert expansion_arguments(args) == []
        else:
            assert config["scientific_research_agendas"] is expected
            assert expansion_arguments(args) == flags


def test_shared_fresh_configuration_activates_and_loaded_omission_or_pause_retains(configure_without_native):
    world = _world()
    _args_out, config = configure_without_native(world, "--scientific-claims", "--scholarship",
        "--techniques", "--scientific-research-agendas", fresh=True, mode="off")
    plan = world.scientific_claims.research_agendas
    assert plan.enabled and config["simulation_args"]["scientific_research_agendas"] is True
    _args_out, config = configure_without_native(world, mode="off")
    assert world.scientific_claims.research_agendas is plan
    assert config["simulation_args"]["scientific_research_agendas"] is True
    _args_out, config = configure_without_native(world, "--no-scientific-research-agendas", mode="off")
    assert world.scientific_claims.research_agendas is plan and not plan.enabled
    assert config["simulation_args"]["scientific_research_agendas"] is False
    configure_without_native(world, "--no-scientific-claims", mode="off")
    assert world.scientific_claims is None


@pytest.mark.parametrize("flags", [[], ["--no-scientific-claims"],
    ["--scientific-claims", "--no-scholarship"], ["--scientific-claims", "--scholarship", "--no-techniques"]])
def test_invalid_research_opt_in_fails_before_runtime_creation(configure_without_native, flags):
    with pytest.raises(ValueError):
        configure_without_native(_world(), *flags, "--scientific-research-agendas", mode="off")
    assert not configure_without_native.constructions


@pytest.mark.parametrize("enabled", [True, False])
def test_research_checkpoint_roundtrip_preserves_mode_births_and_archive(tmp_path, enabled):
    from chronicler.run_checkpoint import save_world, read_checkpoint
    from chronicler.scientific_research import set_research_agendas_enabled, validate_state
    world = research_world()
    advance(world, 0, 2)
    set_research_agendas_enabled(world, enabled)
    before = world.model_dump()
    path = tmp_path / "research.ckpt"
    save_world(path, world)
    loaded = read_checkpoint(path)
    assert loaded.header["flags"]["scientific_research_agendas"] is enabled
    assert loaded.state.world.model_dump() == before
    validate_state(loaded.state.world)


@pytest.mark.parametrize("mode", [None, True, False])
def test_exact_resume_adopts_real_mode_and_rejects_policy_change_even_for_old_checkpoints(tmp_path, mode):
    from chronicler.scientific_research import set_research_agendas_enabled
    world = _world() if mode is None else research_world()
    world.turn = 2
    if mode is False:
        set_research_agendas_enabled(world, False)
    loaded = SimpleNamespace(state=SimpleNamespace(world=world, seed=42, num_turns=4,
        run_config={"simulation_args": {}}))  # old config has no research field
    args = _args(tmp_path)
    before = pickle.dumps(world, protocol=5)
    assert _adopt_checkpoint_args(_parser(), args, loaded) == []
    assert args.scientific_research_agendas is mode
    changed = "--no-scientific-research-agendas" if mode is True else "--scientific-research-agendas"
    messages = _adopt_checkpoint_args(_parser(), _args(tmp_path, changed), loaded)
    assert len(messages) == 1 and "declared experiment fork" in messages[0]
    assert pickle.dumps(world, protocol=5) == before


def test_legacy_checkpoint_header_omits_research_instead_of_inventing_false():
    from chronicler.run_checkpoint import feature_flags
    world = _world()
    before = pickle.dumps(world, protocol=5)
    assert "scientific_research_agendas" not in feature_flags(world)
    assert pickle.dumps(world, protocol=5) == before


@pytest.mark.parametrize("enabled", [True, False])
def test_all_gate_commands_forward_research_intent(enabled, tmp_path, monkeypatch):
    import argparse
    runner = _gate_runner()
    commands = []
    monkeypatch.setattr(runner, "_run", lambda cmd, cwd, env: commands.append(cmd))
    monkeypatch.setattr(runner, "record_batch_run", lambda *a, **k: None)
    monkeypatch.setattr(runner, "finish_batch_manifest", lambda *a, **k: None)
    args = argparse.Namespace(profile="subset", seeds=1, turns=4, seed_start=42, parallel=1,
        output_root=tmp_path, worldgen="template", scientific_research_agendas=enabled)
    runner.run_subset(args, tmp_path, {})
    runner.run_full(args, tmp_path, {})
    runner.run_determinism(args, tmp_path, {}, "hybrid")
    assert len(commands) == 4
    assert all(_parser().parse_args(cmd[3:]).scientific_research_agendas is enabled for cmd in commands)
    assert runner._determinism_manifest_args(args, "hybrid").scientific_research_agendas is enabled


def test_live_batch_configuration_checks_and_forwards_research_switch():
    from chronicler.live import LiveServer
    server = LiveServer()
    for value in (None, False, True):
        assert server._validate_batch_config({"scientific_research_agendas": value}) is None
    for value in (1, "true", [], {}):
        assert "scientific_research_agendas" in server._validate_batch_config({"scientific_research_agendas": value})


@pytest.mark.parametrize("explicit", [None, False, True])
def test_live_batch_lab_forwards_saved_default_and_explicit_research_policy(monkeypatch, explicit):
    import threading
    from chronicler import batch
    from chronicler.live import LiveServer
    received = []

    def capture(args, **kwargs):
        received.append(args)
        raise RuntimeError("captured configuration before executing a batch")

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def is_alive(self):
            return False

        def start(self):
            self.target()

    monkeypatch.setattr(batch, "run_batch", capture)
    monkeypatch.setattr(threading, "Thread", InlineThread)
    server = LiveServer()
    server._client_defaults["scientific_research_agendas"] = True
    config = {} if explicit is None else {"scientific_research_agendas": explicit}
    assert server._handle_batch_start({"type": "batch_start", "config": config}) is None
    assert len(received) == 1
    assert received[0].scientific_research_agendas is (True if explicit is None else explicit)
