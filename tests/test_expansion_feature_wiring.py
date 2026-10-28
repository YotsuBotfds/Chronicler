"""Expansion switches preserve intent across entrypoints and historical transport.

These are configuration/transport tests, not evidence that a native injury,
forecast or gathering mechanism is scientifically qualified. Native runtime
construction is replaced only at its boundary; the real parser, configuration,
state, manifest, checkpoint and transport code is exercised.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ("harvest_forecasts", "health_care", "ritual_gatherings")


def _parser():
    from chronicler.main import _build_parser
    return _build_parser()


def _args(path: Path, *flags: str, mode: str = "hybrid"):
    return _parser().parse_args([
        "--seed", "42", "--turns", "4", "--regions", "8", "--civs", "4",
        "--agents", mode, "--simulate-only", "--output", str(path / "chronicle.md"),
        "--state", str(path / "state.json"), *flags,
    ])


def _switch(world, feature: str, enabled: bool):
    module = importlib.import_module(f"chronicler.{feature}")
    getattr(module, f"set_{feature}_enabled")(world, enabled)
    return module


def _world():
    from chronicler.world_gen import generate_world
    return generate_world(seed=42)


@pytest.fixture
def configure_without_native(monkeypatch, tmp_path):
    """Keep the real configuration path, stopping at native construction."""
    from chronicler import agent_bridge, main

    constructions = []

    class BridgeBoundary:
        def __init__(self, world, **kwargs):
            constructions.append((world, kwargs))

    monkeypatch.setattr(agent_bridge, "AgentBridge", BridgeBoundary)
    monkeypatch.setattr(main, "_create_ecology_runtime", lambda world: None)
    monkeypatch.setattr(main, "_create_politics_runtime", lambda world: None)

    def configure(world, *flags, mode="hybrid", fresh=False):
        args = _args(tmp_path, *flags, mode=mode)
        result = main._configure_run(args, world, fresh, tmp_path / "chronicle.md")
        return args, result[-1]

    configure.constructions = constructions
    return configure


@pytest.mark.parametrize("feature", FEATURES)
def test_switch_intent_is_tristate_and_part_of_the_simulation_cohort(feature):
    from chronicler.batch_manifest import (
        NON_SIMULATION_ARG_KEYS, OUTPUT_ARG_KEYS, SIMULATION_ARG_KEYS, simulation_config,
    )
    parser = _parser()
    assert feature in SIMULATION_ARG_KEYS
    assert feature not in OUTPUT_ARG_KEYS + NON_SIMULATION_ARG_KEYS
    for flags, expected in (([], None), (["--" + feature.replace("_", "-")], True),
                            (["--no-" + feature.replace("_", "-")], False)):
        args = parser.parse_args(flags)
        assert getattr(args, feature) is expected
        assert simulation_config(args)[feature] is expected


def test_old_worlds_and_snapshots_do_not_invent_expansion_state(tmp_path):
    from chronicler.models import TurnSnapshot, WorldState
    world = _world()
    world_path = tmp_path / "old.json"
    world.save(world_path)
    loaded = WorldState.load(world_path)
    snapshot = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    for feature in FEATURES:
        assert getattr(loaded, feature) is None
        assert feature not in json.loads(world_path.read_text())
        assert feature not in json.loads(snapshot.model_dump_json())


@pytest.mark.parametrize("feature", FEATURES)
def test_fresh_default_off_and_explicit_opt_in_reach_real_configuration(
    feature, configure_without_native,
):
    default_world = _world()
    configure_without_native(default_world, fresh=True)
    assert getattr(default_world, feature) is None

    world = _world()
    flag = "--" + feature.replace("_", "-")
    # Both prerequisite flags are harmless for the other two experiments.
    args, config = configure_without_native(
        world, "--grain-reserves", "--contact-ledger", flag, fresh=True,
    )
    assert getattr(world, feature) is not None
    assert config["simulation_args"][feature] is True
    assert getattr(args, feature) is True
    assert configure_without_native.constructions[-1][1]["mode"] == "hybrid"


@pytest.mark.parametrize("feature", FEATURES)
def test_loaded_omitted_preserves_state_and_explicit_off_clears_it(
    feature, configure_without_native,
):
    world = _world()
    _switch(world, feature, True)
    state = getattr(world, feature)
    _args_out, config = configure_without_native(world, "--grain-reserves", "--contact-ledger")
    assert getattr(world, feature) is state
    assert config["simulation_args"][feature] is None

    configure_without_native(world, "--no-" + feature.replace("_", "-"), mode="off")
    assert getattr(world, feature) is None
    assert feature not in json.loads(world.model_dump_json())


@pytest.mark.parametrize("feature,mode", [
    ("harvest_forecasts", "off"),
    ("health_care", "off"), ("health_care", "shadow"), ("health_care", "demographics-only"),
    ("ritual_gatherings", "off"), ("ritual_gatherings", "shadow"),
    ("ritual_gatherings", "demographics-only"),
])
def test_explicit_native_experiments_reject_invalid_modes_before_runtime_creation(
    feature, mode, configure_without_native,
):
    before = len(configure_without_native.constructions)
    with pytest.raises(ValueError):
        configure_without_native(
            _world(), "--" + feature.replace("_", "-"),
            "--contact-ledger", mode=mode,
        )
    assert len(configure_without_native.constructions) == before


def test_explicit_forecasts_require_granaries_before_constructing_native_runtime(
    configure_without_native,
):
    with pytest.raises(ValueError, match="[Gg]rain|granari"):
        configure_without_native(_world(), "--harvest-forecasts", "--contact-ledger")
    assert not configure_without_native.constructions


@pytest.mark.parametrize("feature", FEATURES)
def test_saved_experiments_are_dormant_in_off_mode_until_explicitly_reenabled(
    feature, configure_without_native,
):
    world = _world()
    world.agent_mode = "hybrid"
    module = _switch(world, feature, True)
    state = getattr(world, feature)
    configure_without_native(world, mode="off")
    assert getattr(world, feature) is state
    assert getattr(module, f"{feature}_active")(world) is False
    assert module.snapshot_summary(world) == {}


def test_exact_world_checkpoint_keeps_enabled_state_and_feature_header(tmp_path):
    from chronicler.run_checkpoint import feature_flags, read_checkpoint, save_world
    world = _world()
    world.agent_mode = "hybrid"
    for feature in FEATURES:
        _switch(world, feature, True)
    path = tmp_path / "expansion.ckpt"
    save_world(path, world)
    loaded = read_checkpoint(path)
    for feature in FEATURES:
        assert loaded.header["flags"][feature] is True
        assert feature_flags(loaded.state.world)[feature] is True
        assert getattr(loaded.state.world, feature) == getattr(world, feature)


@pytest.mark.parametrize("feature", FEATURES)
def test_exact_resume_adopts_saved_switch_and_rejects_explicit_conflict(tmp_path, feature):
    from chronicler.main import _adopt_checkpoint_args
    parser = _parser()
    saved = SimpleNamespace(state=SimpleNamespace(
        run_config={"simulation_args": {feature: True}}, seed=42, num_turns=4,
        world=SimpleNamespace(turn=2),
    ))
    args = _args(tmp_path)
    assert _adopt_checkpoint_args(parser, args, saved) == []
    assert getattr(args, feature) is True
    conflict = _args(tmp_path, "--no-" + feature.replace("_", "-"))
    messages = _adopt_checkpoint_args(parser, conflict, saved)
    assert len(messages) == 1 and "conflicts with the checkpoint" in messages[0]


def _gate_runner():
    spec = importlib.util.spec_from_file_location(
        "expansion_gate_runner", ROOT / "scripts/m53b_run_validation.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("enabled", [True, False])
def test_all_gate_generation_paths_forward_the_same_experiment_intent(
    enabled, tmp_path, monkeypatch,
):
    runner = _gate_runner()
    commands = []
    monkeypatch.setattr(runner, "_run", lambda cmd, cwd, env: commands.append(cmd))
    # This test exercises command generation, not fabricated simulation data.
    monkeypatch.setattr(runner, "record_batch_run", lambda *a, **k: None)
    monkeypatch.setattr(runner, "finish_batch_manifest", lambda *a, **k: None)
    args = argparse.Namespace(
        profile="subset", seeds=1, turns=4, seed_start=42, parallel=1,
        output_root=tmp_path, worldgen="template", grain_reserves=True,
        **{feature: enabled for feature in FEATURES},
    )
    runner.run_subset(args, tmp_path, {})
    runner.run_full(args, tmp_path, {})
    runner.run_determinism(args, tmp_path, {}, "hybrid")
    assert len(commands) == 4
    for command in commands:
        actual = _parser().parse_args(command[3:])
        for feature in FEATURES:
            assert getattr(actual, feature) is enabled
    manifest_args = runner._determinism_manifest_args(args, "hybrid")
    for feature in FEATURES:
        assert getattr(manifest_args, feature) is enabled


@pytest.mark.parametrize("feature", FEATURES)
def test_batch_lab_rejects_truthy_non_boolean_feature_values(feature):
    from chronicler.live import LiveServer
    server = LiveServer()
    for value in (None, True, False):
        assert server._validate_batch_config({feature: value}) is None
    for value in ("true", 1, 0, [], {}):
        message = server._validate_batch_config({feature: value})
        assert message is not None and feature in message


@pytest.mark.parametrize("explicit", [None, False, True])
def test_batch_lab_forwards_feature_defaults_and_explicit_overrides(monkeypatch, explicit):
    from chronicler import batch
    from chronicler.live import LiveServer
    import threading

    received = []

    def capture(args, **kwargs):
        received.append(args)
        raise RuntimeError("configuration captured before batch execution")

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
    server._client_defaults.update({feature: True for feature in FEATURES})
    config = {} if explicit is None else {feature: explicit for feature in FEATURES}
    assert server._handle_batch_start({"type": "batch_start", "config": config}) is None
    assert len(received) == 1
    for feature in FEATURES:
        assert getattr(received[0], feature) is (True if explicit is None else explicit)


def test_live_cli_defaults_reach_batch_lab_before_the_lobby_starts(tmp_path, monkeypatch):
    from chronicler import live

    class LobbyBoundary(Exception):
        pass

    server = live.LiveServer()

    def stop_before_socket_start():
        raise LobbyBoundary

    monkeypatch.setattr(server, "start", stop_before_socket_start)
    monkeypatch.setattr(live, "build_lobby_init", lambda args: {})
    flags = ["--" + feature.replace("_", "-") for feature in FEATURES]
    args = _args(tmp_path, "--grain-reserves", "--contact-ledger", *flags)
    with pytest.raises(LobbyBoundary):
        live.run_live(args, server=server)
    for feature in (*FEATURES, "grain_reserves", "contact_ledger"):
        assert server._client_defaults[feature] is True


@pytest.mark.parametrize("feature", FEATURES)
def test_live_fresh_world_opts_in_and_raw_resume_preserves_saved_state(tmp_path, feature):
    from chronicler.live import _live_world
    flag = "--" + feature.replace("_", "-")
    args = _args(tmp_path, flag, "--grain-reserves", "--contact-ledger")
    world, _ = _live_world(args, {"seed": 42, "regions": 8, "civs": 4})
    assert getattr(world, feature) is not None
    resumed, _ = _live_world(_args(tmp_path), {"resume_state": world.model_dump()})
    assert getattr(resumed, feature) == getattr(world, feature)


def test_live_transport_carries_new_readings_without_backfilling_older_history():
    from chronicler.live import _build_init_data_from_bundle, apply_turn_message
    from chronicler.models import TurnSnapshot
    from chronicler.transport import SNAPSHOT_SYSTEMS, snapshot_from_turn_message

    old = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={}).model_dump()
    readings = {feature: {"source_turn": 1, "recorded": [feature]} for feature in FEATURES}
    recent = TurnSnapshot(turn=2, civ_stats={}, region_control={}, relationships={}, **readings).model_dump()
    bundle = {"world_state": {feature: {"future": True} for feature in FEATURES},
              "history": [old], "metadata": {"total_turns": 1}}
    init = _build_init_data_from_bundle(bundle)
    message = dict(recent, type="turn", chronicle_text="", events=[], named_events=[])
    assert snapshot_from_turn_message(message) == recent
    apply_turn_message(init, message)
    assert init["history"] == [old, recent]
    for feature in FEATURES:
        assert feature in SNAPSHOT_SYSTEMS
        assert feature not in init["history"][0]
        assert init["history"][1][feature] == readings[feature]
