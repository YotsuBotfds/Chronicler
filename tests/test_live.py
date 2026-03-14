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
    command_q.put({"type": "set", "civ": civ_name, "stat": "military", "value": 9})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert civ.military == 9

    _ = status_q.get_nowait()  # paused
    set_ack = status_q.get_nowait()
    assert set_ack["type"] == "ack"
    assert set_ack["command"] == "set"
    assert set_ack["still_paused"] is True
    assert set_ack["civ"] == civ_name
    assert set_ack["stat"] == "military"
    assert set_ack["value"] == 9


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
