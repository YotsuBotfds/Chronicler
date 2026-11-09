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


def test_live_batch_report_preserves_existing_file_when_replace_fails(monkeypatch, tmp_path):
    """The live Batch Lab report is replaced atomically, never truncated in place."""
    from chronicler import artifact_io
    from chronicler.artifact_io import ArtifactIOError
    from chronicler.live import _write_batch_report

    report_path = tmp_path / "batch_report.json"
    report_path.write_text('{"old": true}', encoding="utf-8")

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(artifact_io.os, "replace", failing_replace)
    with pytest.raises(ArtifactIOError, match="could not write artifact"):
        _write_batch_report(tmp_path, {"new": True})

    assert report_path.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.glob(".*.tmp")) == []


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
    # The hint names options the CLI has (it once named a --load that does not exist).
    from chronicler.main import _build_parser
    hint = forked["cli_hint"]
    assert f"--fork {fork_dir / 'state.json'} --seed SEED --turns TURNS" in hint
    parsed = _build_parser().parse_args(
        ["--fork", str(fork_dir / "state.json"), "--seed", "7", "--turns", "5"])
    assert parsed.fork == str(fork_dir / "state.json")


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


def test_start_command_records_session_client_config():
    """Live start should retain client model preferences for later narration."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    start_msg = {
        "type": "start",
        "scenario": None,
        "turns": 12,
        "seed": 7,
        "civs": 4,
        "regions": 8,
        "sim_model": "sim-x",
        "narrative_model": "narr-x",
        "narrator": "local",
        "resume_state": None,
    }

    result = server._handle_start(start_msg)

    assert result is None
    assert server._session_client_config == {
        "sim_model": "sim-x",
        "narrative_model": "narr-x",
        "narrator": "local",
    }


def test_resolve_client_config_prefers_bundle_metadata():
    """Bundle metadata should override session defaults when loading from Batch Lab."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._client_defaults.update({
        "local_url": "http://example.invalid/v1",
        "sim_model": "default-sim",
        "narrative_model": "default-narr",
        "narrator": "local",
    })
    server._session_client_config = {
        "sim_model": "session-sim",
        "narrative_model": "session-narr",
        "narrator": "local",
    }

    config = server._resolve_client_config({
        "sim_model": "bundle-sim",
        "narrative_model": "bundle-narr",
        "narrator_mode": "local",
    })

    assert config["local_url"] == "http://example.invalid/v1"
    assert config["sim_model"] == "bundle-sim"
    assert config["narrative_model"] == "bundle-narr"
    assert config["narrator"] == "local"


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


def _run_paused_commands(commands):
    """Drive one real live pause with queued commands ending in ``continue``."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pause_fn = make_live_pause(command_q, status_q)
    for command in commands(world):
        command_q.put(command)
    command_q.put({"type": "continue"})
    assert pause_fn(world, memories, []) is True
    statuses = []
    while not status_q.empty():
        statuses.append(status_q.get_nowait())
    assert statuses[0]["type"] == "paused"
    assert statuses[-1] == {"type": "ack", "command": "continue", "still_paused": False}
    return world, statuses[1:-1]


@pytest.mark.parametrize("value", [
    float("inf"), float("-inf"), float("nan"), 1e999, "Infinity", "NaN", [1], {}, None, "abc",
])
def test_live_pause_set_refuses_non_integer_value_and_stays_paused(value):
    """A value int() cannot represent is one error; the pause loop keeps serving."""
    def commands(world):
        civ = world.civilizations[0]
        return [
            {"type": "set", "civ": civ.name, "stat": "military", "value": value},
            {"type": "set", "civ": civ.name, "stat": "military", "value": 77},
        ]

    world, statuses = _run_paused_commands(commands)
    assert [s["type"] for s in statuses] == ["error", "ack"]
    assert statuses[0]["message"].startswith("Value must be an integer, got ")
    assert world.civilizations[0].military == 77


@pytest.mark.parametrize(("value", "applied"), [(True, 1), (3.7, 3), ("12", 12), (55, 55)])
def test_live_pause_set_keeps_existing_integer_coercion(value, applied):
    """Values int() accepted before are still truncated and applied unchanged."""
    def commands(world):
        return [{"type": "set", "civ": world.civilizations[0].name, "stat": "military",
                 "value": value}]

    world, statuses = _run_paused_commands(commands)
    assert [s["type"] for s in statuses] == ["ack"]
    assert statuses[0]["value"] == applied
    assert world.civilizations[0].military == applied


@pytest.mark.parametrize("stat", [["x"], {"a": 1}, ["military"], 5, None])
def test_live_pause_set_refuses_non_string_stat(stat):
    """An unhashable or non-string stat is answered as an invalid stat (FIX-11)."""
    def commands(world):
        return [{"type": "set", "civ": world.civilizations[0].name, "stat": stat, "value": 5}]

    _, statuses = _run_paused_commands(commands)
    assert [s["type"] for s in statuses] == ["error"]
    assert statuses[0]["message"].startswith("Invalid stat: ")


@pytest.mark.parametrize("civ", [["x"], {"a": 1}, 0, None])
def test_live_pause_set_refuses_non_string_civ(civ):
    """A non-string civ name is answered as an unknown civilization (FIX-11)."""
    def commands(world):
        return [{"type": "set", "civ": civ, "stat": "military", "value": 5}]

    _, statuses = _run_paused_commands(commands)
    assert [s["type"] for s in statuses] == ["error"]
    assert statuses[0]["message"].startswith("Unknown civilization: ")


def test_coerce_set_value_without_a_thread():
    """The coercion is reachable directly: int or None, never an exception."""
    from chronicler.live import _coerce_set_value

    assert _coerce_set_value(7) == 7
    assert _coerce_set_value(True) == 1
    assert _coerce_set_value(-3.9) == -3
    assert _coerce_set_value("42") == 42
    for bad in (float("inf"), float("nan"), 1e999, "Infinity", [1], {}, None, "4.5"):
        assert _coerce_set_value(bad) is None


@pytest.fixture
def held_port():
    """A localhost port another socket is listening on."""
    import socket

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("localhost", 0))
    holder.listen()
    try:
        yield holder.getsockname()[1]
    finally:
        holder.close()


def test_live_server_start_raises_when_port_is_taken(held_port):
    """A bind failure reaches the caller instead of dying in the server thread (FIX-10)."""
    from chronicler.live import LiveServer, LiveServerStartError

    server = LiveServer(port=held_port)
    with pytest.raises(LiveServerStartError):
        server.start()
    server.thread.join(timeout=5)
    assert not server.thread.is_alive()
    assert isinstance(server._start_error, OSError)
    server.stop()  # nothing to stop; does not raise on the closed loop


def test_live_server_start_raises_when_not_listening_in_time(monkeypatch):
    """start() no longer ignores its wait: a server that never listens is an error."""
    from chronicler import live
    from chronicler.live import LiveServer, LiveServerStartError

    gate = threading.Event()
    monkeypatch.setattr(live, "_START_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(LiveServer, "_run_loop", lambda self, ready: gate.wait(5))
    server = LiveServer(port=0)
    try:
        with pytest.raises(LiveServerStartError, match="not listening after"):
            server.start()
    finally:
        gate.set()
        server.thread.join(timeout=5)


def test_run_live_reports_a_server_that_cannot_start(held_port, tmp_path, capsys):
    """run_live prints the cause and returns None instead of announcing a lobby."""
    import argparse
    from chronicler.live import run_live

    args = argparse.Namespace(
        seed=42, turns=5, civs=2, regions=3, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None, live_port=held_port)
    assert run_live(args) is None
    captured = capsys.readouterr()
    assert "Live server could not start: " in captured.err
    assert "Lobby ready" not in captured.out


@pytest.mark.parametrize("name", ["../x.yaml", "../../etc/passwd", "/etc/passwd", "a/../../x.yaml"])
def test_scenario_names_outside_scenarios_are_refused(name):
    """A lobby or batch scenario cannot name a file outside scenarios/ (FIX-10)."""
    from chronicler.live import LiveServer, _scenario_file

    with pytest.raises(ValueError, match="Scenario must be within scenarios/"):
        _scenario_file(name)
    server = LiveServer(port=0)
    err = server._handle_start({"type": "start", "scenario": name, "turns": 5, "civs": 2,
                                "regions": 3, "seed": 1})
    assert err == {"type": "error",
                   "message": "Start field 'scenario': Scenario must be within scenarios/"}
    assert server._server_state == "lobby" and not server.start_event.is_set()
    assert server._validate_batch_config({"scenario": name}) == (
        "batch_start config 'scenario': Scenario must be within scenarios/")


@pytest.mark.parametrize("name", ["dead_miles.yaml", "sub/x.yaml", "sub/../x.yaml"])
def test_scenario_names_inside_scenarios_keep_their_path(name):
    """Accepted names keep the relative path the session always used."""
    from pathlib import Path
    from chronicler.live import LiveServer, _record_live_world_args, _scenario_file

    assert _scenario_file(name) == Path("scenarios") / name
    server = LiveServer(port=0)
    assert server._validate_batch_config({"scenario": name}) is None
    import argparse
    args = argparse.Namespace()
    _record_live_world_args(args, {"scenario": name})
    assert args.scenario == str(Path("scenarios") / name)
