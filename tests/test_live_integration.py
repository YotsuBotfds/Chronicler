"""Integration tests for live mode with real WebSocket connections.

NOTE: This is a bare server fixture — it pushes turn messages but does NOT
send an init message. The init message is handled by run_live() which
pre-generates the world and sends init on the first on_turn call.
These tests verify queue plumbing and protocol behavior, not the full
init-then-turns sequence.
"""
import asyncio
import argparse
import json
import threading
import time
from pathlib import Path

import pytest
import websockets.asyncio.client as ws_client


def _make_args(tmp_path, turns=5, pause_every=None):
    return argparse.Namespace(
        seed=42, turns=turns, civs=2, regions=3,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None,
        pause_every=pause_every,
        live_port=0,
    )


def _make_running_init_data():
    return {
        "type": "init",
        "state": "running",
        "total_turns": 3,
        "pause_every": 10,
        "current_turn": 3,
        "world_state": {
            "name": "Validation World",
            "seed": 42,
            "turn": 3,
            "regions": [],
            "civilizations": [],
            "relationships": {},
            "events_timeline": [],
            "named_events": [],
            "scenario_name": None,
        },
        "history": [
            {"turn": 1},
            {"turn": 2},
            {"turn": 3},
        ],
        "chronicle_entries": {},
        "events_timeline": [],
        "named_events": [],
        "era_reflections": {},
        "metadata": {
            "seed": 42,
            "total_turns": 3,
            "generated_at": "2026-04-01T00:00:00",
            "sim_model": "sim-test",
            "narrative_model": "narr-test",
            "scenario_name": None,
            "interestingness_score": None,
        },
    }


@pytest.fixture
def running_live_server():
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._server_state = "running"
    server._init_data = _make_running_init_data()
    server.start()

    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def live_env(tmp_path):
    """Set up a LiveServer with a running simulation in a background thread.

    The ``start()`` method starts only the WebSocket server. Call
    ``launch_sim()`` after the WS client has connected so that no turn
    messages are lost due to a race between the simulation and the
    client connection.
    """
    from chronicler.live import LiveServer, make_live_pause

    class Env:
        def __init__(self):
            self.tmp_path = tmp_path
            self.server = None
            self.thread = None
            self.result = None
            self._sim_started = threading.Event()

        def start(self, turns=5, pause_every=None):
            """Start the WebSocket server only. Call launch_sim() to begin the simulation."""
            self._turns = turns
            self._pause_every = pause_every
            self.server = LiveServer(port=0)
            self.server.start()
            self.port = self.server._actual_port
            return self

        def launch_sim(self):
            """Launch the simulation in a background thread.

            Call this after the WS client has connected so no messages are lost.
            """
            args = _make_args(self.tmp_path, turns=self._turns, pause_every=self._pause_every)
            pending = []
            pause_fn = make_live_pause(
                self.server.command_queue,
                self.server.status_queue,
                output_dir=self.tmp_path,
            )

            def run():
                from chronicler.main import execute_run
                self.result = execute_run(
                    args,
                    on_pause=pause_fn if self._pause_every else None,
                    pause_every=self._pause_every,
                    pending_injections=pending,
                    on_turn=self._on_turn,
                    quit_check=lambda: self.server.quit_event.is_set(),
                )
                self.server.status_queue.put({
                    "type": "completed",
                    "total_turns": self.result.total_turns,
                    "bundle_path": str(self.tmp_path / "chronicle_bundle.json"),
                })

            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()

        def _on_turn(self, snapshot, chronicle_text, events, named_events):
            snap_dict = snapshot.model_dump()
            snap_dict["type"] = "turn"
            snap_dict["chronicle_text"] = chronicle_text
            snap_dict["events"] = [e.model_dump() for e in events]
            snap_dict["named_events"] = [ne.model_dump() for ne in named_events]
            self.server.snapshot_queue.put(snap_dict)
            # Small delay so the WS drain loop can push messages and
            # quit_check can observe the quit_event between turns.
            time.sleep(0.02)

        def stop(self):
            if self.server:
                self.server.quit_event.set()
                self.server.stop()
            if self.thread:
                self.thread.join(timeout=10)

    env = Env()
    yield env
    env.stop()


@pytest.mark.asyncio
async def test_connect_and_receive_turns(live_env):
    """Connect to live server, receive turn messages."""
    env = live_env.start(turns=5)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        # Launch simulation only after WS client is connected
        env.launch_sim()

        messages = []
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                messages.append(msg)
                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    turn_msgs = [m for m in messages if m["type"] == "turn"]
    assert len(turn_msgs) == 5
    assert all("chronicle_text" in m for m in turn_msgs)
    assert all("events" in m for m in turn_msgs)
    turns = [m["turn"] for m in turn_msgs]
    assert turns == sorted(turns)


@pytest.mark.asyncio
async def test_pause_and_continue(live_env):
    """Server sends paused message at interval, continues on command."""
    env = live_env.start(turns=10, pause_every=3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        messages = []
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                messages.append(msg)

                if msg["type"] == "paused":
                    await ws.send(json.dumps({"type": "continue"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    paused_msgs = [m for m in messages if m["type"] == "paused"]
    assert len(paused_msgs) >= 1

    ack_msgs = [m for m in messages if m["type"] == "ack" and m.get("command") == "continue"]
    assert len(ack_msgs) >= 1
    assert all(m["still_paused"] is False for m in ack_msgs)


@pytest.mark.asyncio
async def test_inject_round_trip(live_env):
    """Inject at pause, verify ack, continue, verify event in next turn."""
    env = live_env.start(turns=10, pause_every=3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        messages = []
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                messages.append(msg)

                if msg["type"] == "paused":
                    civ = msg["civs"][0]
                    await ws.send(json.dumps({"type": "inject", "event_type": "plague", "civ": civ}))
                    ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    ack = json.loads(ack_raw)
                    messages.append(ack)
                    assert ack["type"] == "ack"
                    assert ack["command"] == "inject"
                    assert ack["still_paused"] is True
                    await ws.send(json.dumps({"type": "continue"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    inject_acks = [m for m in messages if m.get("type") == "ack" and m.get("command") == "inject"]
    assert len(inject_acks) >= 1


@pytest.mark.asyncio
async def test_set_round_trip(live_env):
    """Set stat at pause, verify ack includes new value."""
    env = live_env.start(turns=10, pause_every=3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        messages = []
        set_ack = None
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                messages.append(msg)

                if msg["type"] == "paused" and set_ack is None:
                    civ = msg["civs"][0]
                    await ws.send(json.dumps({"type": "set", "civ": civ, "stat": "military", "value": 9}))
                    ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    set_ack = json.loads(ack_raw)
                    assert set_ack["type"] == "ack"
                    assert set_ack["command"] == "set"
                    assert set_ack["still_paused"] is True
                    assert set_ack["civ"] == civ
                    assert set_ack["stat"] == "military"
                    assert set_ack["value"] == 9
                    await ws.send(json.dumps({"type": "continue"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    assert set_ack is not None


@pytest.mark.asyncio
async def test_fork_round_trip(live_env):
    """Fork at pause, verify response with save_path and cli_hint."""
    env = live_env.start(turns=10, pause_every=3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        forked_msg = None
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)

                if msg["type"] == "paused" and forked_msg is None:
                    await ws.send(json.dumps({"type": "fork"}))
                    fork_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    forked_msg = json.loads(fork_raw)
                    assert forked_msg["type"] == "forked"
                    assert "save_path" in forked_msg
                    assert "cli_hint" in forked_msg
                    assert Path(forked_msg["save_path"]).exists()
                    assert (Path(forked_msg["save_path"]) / "state.json").exists()
                    await ws.send(json.dumps({"type": "continue"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    assert forked_msg is not None


@pytest.mark.asyncio
async def test_quit_while_paused(live_env):
    """Quit while paused produces completed message and bundle."""
    env = live_env.start(turns=50, pause_every=3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        completed = None
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)

                if msg["type"] == "paused":
                    await ws.send(json.dumps({"type": "quit"}))

                if msg["type"] == "completed":
                    completed = msg
                    break
        except asyncio.TimeoutError:
            pass

    assert completed is not None
    assert completed["total_turns"] < 50
    assert Path(env.tmp_path / "chronicle_bundle.json").exists()


@pytest.mark.asyncio
async def test_quit_while_running(live_env):
    """Quit during execution: current turn completes, bundle written."""
    env = live_env.start(turns=50)  # no pause_every

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        turn_count = 0
        completed = None
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)

                if msg["type"] == "turn":
                    turn_count += 1
                    if turn_count == 3:
                        await ws.send(json.dumps({"type": "quit"}))

                if msg["type"] == "completed":
                    completed = msg
                    break
        except asyncio.TimeoutError:
            pass

    assert completed is not None
    assert completed["total_turns"] < 50
    assert Path(env.tmp_path / "chronicle_bundle.json").exists()


@pytest.mark.asyncio
async def test_commands_while_running_rejected(live_env):
    """Commands sent while running get error (except quit and speed)."""
    env = live_env.start(turns=20)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        env.launch_sim()
        error_msg = None
        injected = False
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)

                if msg["type"] == "turn" and not injected:
                    # Send an inject command while the simulation is running
                    await ws.send(json.dumps({"type": "inject", "event_type": "plague", "civ": "foo"}))
                    injected = True

                if msg["type"] == "error" and error_msg is None:
                    error_msg = msg
                    await ws.send(json.dumps({"type": "quit"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    assert error_msg is not None
    assert error_msg["type"] == "error"
    assert "paused" in error_msg["message"].lower()


@pytest.mark.asyncio
async def test_single_client_enforcement(live_env):
    """Second client gets error and is closed."""
    env = live_env.start(turns=20, pause_every=5)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws1:
        async with ws_client.connect(f"ws://localhost:{env.port}") as ws2:
            raw = await asyncio.wait_for(ws2.recv(), timeout=5.0)
            msg = json.loads(raw)
            assert msg["type"] == "error"
            assert "already connected" in msg["message"].lower()

        env.server.quit_event.set()


@pytest.mark.asyncio
async def test_batch_load_bundle_round_trip(tmp_path, monkeypatch):
    """Client can load a batch result bundle directly into the viewer session."""
    from chronicler.live import LiveServer

    monkeypatch.chdir(tmp_path)
    bundle_dir = tmp_path / "output" / "batch_gui_test" / "seed_101"
    bundle_dir.mkdir(parents=True)
    bundle_path = bundle_dir / "chronicle_bundle.json"
    bundle_path.write_text(json.dumps({
        "world_state": {
            "name": "Batch World",
            "seed": 101,
            "turn": 12,
            "regions": [],
            "civilizations": [],
            "relationships": {},
            "events_timeline": [],
            "named_events": [],
            "scenario_name": None,
        },
        "history": [],
        "events_timeline": [],
        "named_events": [],
        "chronicle_entries": {},
        "era_reflections": {},
        "metadata": {
            "seed": 101,
            "total_turns": 12,
            "generated_at": "2026-03-31T00:00:00",
            "sim_model": "sim-test",
            "narrative_model": "narr-test",
            "scenario_name": None,
            "interestingness_score": 64.0,
        },
    }))

    server = LiveServer(port=0)
    server.start()

    try:
        async with ws_client.connect(f"ws://localhost:{server._actual_port}") as ws:
            await ws.send(json.dumps({
                "type": "batch_load_bundle",
                "path": str(bundle_path),
            }))

            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg = json.loads(raw)

        assert msg["type"] == "bundle_loaded"
        assert msg["path"] == str(bundle_path.resolve())
        assert msg["bundle"]["metadata"]["seed"] == 101
        assert msg["bundle"]["world_state"]["name"] == "Batch World"
        assert server._init_data is not None
        assert server._init_data["current_turn"] == 12
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_batch_load_bundle_rejects_unsupported_manifest(tmp_path, monkeypatch):
    """Live bundle loading should fail cleanly on unsupported bundle v2 manifests."""
    from chronicler.live import LiveServer

    monkeypatch.chdir(tmp_path)
    bundle_dir = tmp_path / "output" / "batch_gui_test" / "seed_102"
    bundle_dir.mkdir(parents=True)
    bundle_path = bundle_dir / "chronicle_bundle.json"
    bundle_path.write_text(json.dumps({
        "manifest_version": 1,
        "layers": [],
    }))

    server = LiveServer(port=0)
    server.start()

    try:
        async with ws_client.connect(f"ws://localhost:{server._actual_port}") as ws:
            await ws.send(json.dumps({
                "type": "batch_load_bundle",
                "path": str(bundle_path),
            }))

            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            msg = json.loads(raw)

        assert msg["type"] == "batch_error"
        assert "Bundle v2 manifests are not supported" in msg["message"]
        assert server._init_data is None
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_rejects_non_object_and_bad_narrate_range(running_live_server):
    """Malformed live messages get explicit errors instead of disappearing."""
    async with ws_client.connect(f"ws://localhost:{running_live_server._actual_port}") as ws:
        init_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        init_msg = json.loads(init_raw)
        assert init_msg["state"] == "running"

        await ws.send(json.dumps([]))
        root_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        assert root_error["type"] == "error"
        assert "JSON objects" in root_error["message"]

        await ws.send(json.dumps({
            "type": "narrate_range",
            "start_turn": 3,
            "end_turn": 2,
        }))
        order_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        assert order_error["type"] == "error"
        assert "start_turn" in order_error["message"]

        await ws.send(json.dumps({
            "type": "narrate_range",
            "start_turn": 0,
            "end_turn": 2,
        }))
        bounds_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        assert bounds_error["type"] == "error"
        assert "available turns" in bounds_error["message"]


@pytest.mark.asyncio
async def test_start_and_batch_path_type_validation():
    """Start and batch loading reject malformed payload types."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._lobby_init = {
        "type": "init",
        "state": "lobby",
        "scenarios": [],
        "models": [],
        "defaults": {"turns": 50, "civs": 4, "regions": 8, "seed": None},
    }
    server.start()

    try:
        async with ws_client.connect(f"ws://localhost:{server._actual_port}") as ws:
            lobby_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            lobby_msg = json.loads(lobby_raw)
            assert lobby_msg["state"] == "lobby"

            await ws.send(json.dumps({
                "type": "start",
                "scenario": None,
                "turns": "bad",
                "seed": 42,
                "civs": 2,
                "regions": 3,
                "sim_model": "sim",
                "narrative_model": "narr",
                "resume_state": None,
            }))
            start_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert start_error["type"] == "error"
            assert "turns" in start_error["message"]

            await ws.send(json.dumps({
                "type": "batch_load_bundle",
                "path": 123,
            }))
            path_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert path_error["type"] == "error"
            assert "path" in path_error["message"]

            await ws.send(json.dumps({
                "type": "batch_start",
                "config": {
                    "seed_start": 1,
                    "seed_count": 2,
                    "turns": 3,
                    "workers": "bad",
                },
            }))
            batch_error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
            assert batch_error["type"] == "batch_error"
            assert "workers" in batch_error["message"]
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_narrate_range_passes_great_persons_and_agent_name_map(running_live_server, monkeypatch):
    """Live narrate_range threads great_persons and agent_name_map from _init_data."""
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        CivSnapshot, Event, NarrativeMoment, NarrativeRole, TurnSnapshot,
    )

    captured_kwargs = {}

    def spy_narrate_batch(self_engine, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(NarrativeEngine, "narrate_batch", spy_narrate_batch)

    # Inject GP data
    running_live_server._init_data["world_state"]["civilizations"] = [{
        "name": "TestCiv", "regions": ["Region0"],
        "leader": {"name": "TestLeader", "personality": "bold"},
        "great_persons": [{
            "name": "Kiran", "role": "general", "trait": "bold",
            "civilization": "TestCiv", "origin_civilization": "TestCiv",
            "born_turn": 1, "source": "agent", "agent_id": 42,
        }],
        "population": 100, "military": 50, "economy": 40,
        "culture": 30, "stability": 60, "treasury": 20,
        "asabiya": 0.5, "tech_era": "iron", "trait": "bold", "alive": True,
    }]
    running_live_server._init_data["world_state"]["retired_persons"] = []

    # Inject valid TurnSnapshot-shaped history
    running_live_server._init_data["history"] = [{
        "turn": 1,
        "civ_stats": {
            "TestCiv": {
                "population": 100, "military": 50, "economy": 40,
                "culture": 30, "stability": 60, "treasury": 20,
                "asabiya": 0.5, "tech_era": "iron", "trait": "bold",
                "regions": ["Region0"], "leader_name": "TestLeader", "alive": True,
            }
        },
        "region_control": {}, "relationships": {},
    }]

    # Inject events
    running_live_server._init_data["events_timeline"] = [{
        "turn": 1, "event_type": "campaign", "actors": ["TestCiv"],
        "description": "A great campaign", "importance": 8, "source": "agent",
    }]

    # Monkeypatch curate for determinism
    known_moment = NarrativeMoment(
        anchor_turn=1, turn_range=(1, 1),
        events=[Event(turn=1, event_type="campaign", actors=["TestCiv"],
                      description="A great campaign", importance=8, source="agent")],
        named_events=[], score=8.0, causal_links=[],
        narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
    )
    monkeypatch.setattr(
        "chronicler.curator.curate",
        lambda *args, **kwargs: ([known_moment], []),
    )

    async with ws_client.connect(f"ws://localhost:{running_live_server._actual_port}") as ws:
        init_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)

        await ws.send(json.dumps({
            "type": "narrate_range", "start_turn": 1, "end_turn": 1,
        }))

        # narration_started arrives BEFORE narrate_batch runs — drain until captured_kwargs populated
        deadline = asyncio.get_event_loop().time() + 5.0
        while not captured_kwargs:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break

    assert "great_persons" in captured_kwargs
    assert captured_kwargs["great_persons"] is not None
    assert any(gp.name == "Kiran" for gp in captured_kwargs["great_persons"])
    assert "agent_name_map" in captured_kwargs
    assert captured_kwargs["agent_name_map"] is not None
    assert captured_kwargs["agent_name_map"].get(42) == "Kiran"
    assert captured_kwargs.get("gini_by_civ") is None
    assert captured_kwargs.get("social_edges") is None
    assert captured_kwargs.get("dissolved_edges_by_turn") is None
    assert captured_kwargs.get("displacement_by_region") is None
    assert captured_kwargs.get("dynasty_registry") is None
    assert captured_kwargs.get("economy_result") is None
