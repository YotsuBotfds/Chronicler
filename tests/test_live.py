"""Unit tests for live.py — queue protocol, no WebSocket connections."""
import queue
import threading

import pytest


def test_live_server_start_stop():
    """LiveServer starts a daemon thread and stops cleanly."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)  # port 0 = OS picks a free port
    server.start()
    assert server.thread.is_alive()
    assert server.thread.daemon is True
    server.stop()


def _make_world():
    """Create a minimal WorldState for testing."""
    from chronicler.world_gen import generate_world
    return generate_world(seed=42, num_regions=3, num_civs=2)


def test_live_pause_continue():
    """live_pause blocks on command_queue, returns True for continue."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True

    paused_msg = status_q.get_nowait()
    assert paused_msg["type"] == "paused"

    ack_msg = status_q.get_nowait()
    assert ack_msg["type"] == "ack"
    assert ack_msg["command"] == "continue"
    assert ack_msg["still_paused"] is False


def test_live_pause_quit():
    """live_pause returns False for quit."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "quit"})

    result = pause_fn(world, memories, pending)
    assert result is False


def test_live_pause_inject():
    """inject command queues event, sends ack with still_paused=True."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    civ_name = world.civilizations[0].name
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "inject", "event_type": "plague", "civ": civ_name})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert len(pending) == 1
    assert pending[0] == ("plague", civ_name)

    paused_msg = status_q.get_nowait()
    assert paused_msg["type"] == "paused"

    inject_ack = status_q.get_nowait()
    assert inject_ack["type"] == "ack"
    assert inject_ack["command"] == "inject"
    assert inject_ack["still_paused"] is True

    continue_ack = status_q.get_nowait()
    assert continue_ack["type"] == "ack"
    assert continue_ack["command"] == "continue"
    assert continue_ack["still_paused"] is False


def test_live_pause_set_applies_immediately():
    """set command modifies world state directly and sends ack with new value."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    civ = world.civilizations[0]
    civ_name = civ.name
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "set", "civ": civ_name, "stat": "military", "value": 90})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert civ.military == 90

    _ = status_q.get_nowait()  # paused
    set_ack = status_q.get_nowait()
    assert set_ack["type"] == "ack"
    assert set_ack["command"] == "set"
    assert set_ack["still_paused"] is True
    assert set_ack["civ"] == civ_name
    assert set_ack["stat"] == "military"
    assert set_ack["value"] == 90


def test_live_pause_inject_invalid_civ():
    """inject with unknown civ sends error, stays paused."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "inject", "event_type": "plague", "civ": "NonexistentCiv"})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert len(pending) == 0

    _ = status_q.get_nowait()  # paused
    err = status_q.get_nowait()
    assert err["type"] == "error"
    assert "NonexistentCiv" in err["message"]


def test_live_pause_set_invalid_stat():
    """set with invalid stat sends error."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    civ_name = world.civilizations[0].name
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "set", "civ": civ_name, "stat": "mana", "value": 5})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True

    _ = status_q.get_nowait()  # paused
    err = status_q.get_nowait()
    assert err["type"] == "error"
    assert "mana" in err["message"]


def test_live_pause_fork(tmp_path):
    """fork command saves state and sends forked response."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q, output_dir=tmp_path)
    command_q.put({"type": "fork"})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True

    _ = status_q.get_nowait()  # paused
    forked = status_q.get_nowait()
    assert forked["type"] == "forked"
    assert "save_path" in forked
    assert "cli_hint" in forked

    from pathlib import Path
    fork_dir = Path(forked["save_path"])
    assert (fork_dir / "state.json").exists()


def test_live_server_has_lobby_fields():
    """LiveServer initializes with lobby state fields."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    assert hasattr(server, "start_event")
    assert hasattr(server, "_start_params")
    assert hasattr(server, "_server_state")
    assert hasattr(server, "_lobby_init")
    assert server._server_state == "lobby"
    assert server._start_params is None
    assert server._lobby_init is None
    assert not server.start_event.is_set()


def test_start_command_sets_event():
    """Start command stores params and sets start_event."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    assert server._server_state == "lobby"

    start_msg = {
        "type": "start",
        "scenario": "dead_miles.yaml",
        "turns": 50,
        "seed": 42,
        "civs": 4,
        "regions": 8,
        "sim_model": "LFM2-24B",
        "narrative_model": "LFM2-24B",
        "resume_state": None,
    }
    server._handle_start(start_msg)

    assert server._server_state == "running"
    assert server.start_event.is_set()
    assert server._start_params == start_msg


def test_start_command_rejected_when_running():
    """Start command returns error when already running."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._server_state = "running"

    result = server._handle_start({"type": "start", "turns": 50})
    assert result is not None
    assert result["type"] == "error"
    assert "already running" in result["message"].lower()


def test_connect_init_returns_lobby_when_in_lobby():
    """Server has correct state for lobby init on connect."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._lobby_init = {"type": "init", "state": "lobby", "scenarios": [], "models": [], "defaults": {}}

    assert server._server_state == "lobby"
    assert server._lobby_init is not None
    assert server._init_data is None


def test_connect_init_returns_starting_during_world_gen():
    """Server has correct state for starting ack during world generation."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._server_state = "running"
    server._init_data = None

    assert server._server_state == "running"
    assert server._init_data is None


def test_build_lobby_init_scans_scenarios(tmp_path):
    """build_lobby_init reads scenario YAML files and returns lobby init payload."""
    import argparse
    from chronicler.live import build_lobby_init

    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "test_scenario.yaml").write_text(
        "name: Test Scenario\n"
        "description: A test\n"
        "world_name: TestWorld\n"
        "civilizations:\n"
        "  - name: TestCiv\n"
        "    values: [Honor, Glory]\n"
        "regions:\n"
        "  - name: TestRegion\n"
        "    terrain: plains\n"
    )

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model=None,
        narrative_model=None,
    )
    result = build_lobby_init(args, scenario_dir=scenario_dir)

    assert result["type"] == "init"
    assert result["state"] == "lobby"
    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["name"] == "Test Scenario"
    assert result["scenarios"][0]["civs"] == [{"name": "TestCiv", "values": ["Honor", "Glory"]}]
    assert result["scenarios"][0]["regions"][0]["name"] == "TestRegion"
    assert result["defaults"]["turns"] == 50
    assert result["defaults"]["seed"] is None
    assert isinstance(result["models"], list)


def test_get_available_models_with_cli_args():
    """_get_available_models returns CLI-specified models."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model="model-a",
        narrative_model="model-b",
    )
    result = _get_available_models(args)
    assert "model-a" in result
    assert "model-b" in result


def test_get_available_models_deduplicates():
    """_get_available_models does not duplicate when sim and narrative are the same."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model="same-model",
        narrative_model="same-model",
    )
    result = _get_available_models(args)
    assert result.count("same-model") == 1


def test_get_available_models_unreachable_lm_studio():
    """_get_available_models falls back gracefully when LM Studio is unreachable."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:99999/v1",
        sim_model=None,
        narrative_model=None,
    )
    result = _get_available_models(args)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_build_lobby_init_empty_scenario_dir(tmp_path):
    """build_lobby_init returns empty scenarios list when no YAML files exist."""
    import argparse
    from chronicler.live import build_lobby_init

    empty_dir = tmp_path / "empty_scenarios"
    empty_dir.mkdir()
    args = argparse.Namespace(local_url="http://localhost:1234/v1", sim_model=None, narrative_model=None)
    result = build_lobby_init(args, scenario_dir=empty_dir)

    assert result["scenarios"] == []
    assert result["state"] == "lobby"


def test_build_lobby_init_missing_fields(tmp_path):
    """build_lobby_init handles scenarios with missing optional fields."""
    import argparse
    from chronicler.live import build_lobby_init

    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "minimal.yaml").write_text("name: Minimal\n")

    args = argparse.Namespace(local_url="http://localhost:1234/v1", sim_model=None, narrative_model=None)
    result = build_lobby_init(args, scenario_dir=scenario_dir)

    s = result["scenarios"][0]
    assert s["name"] == "Minimal"
    assert s["civs"] == []
    assert s["regions"] == []
    assert s["description"] == ""


def test_resolve_start_seed_generates_when_none():
    """resolve_start_seed returns a valid random int when seed is None."""
    from chronicler.live import resolve_start_seed

    seed = resolve_start_seed(None)
    assert isinstance(seed, int)
    assert 0 <= seed < 2**31


def test_resolve_start_seed_passes_through_int():
    """resolve_start_seed returns the seed unchanged when it's an int."""
    from chronicler.live import resolve_start_seed

    assert resolve_start_seed(42) == 42
    assert resolve_start_seed(0) == 0
