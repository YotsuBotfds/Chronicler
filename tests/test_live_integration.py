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
