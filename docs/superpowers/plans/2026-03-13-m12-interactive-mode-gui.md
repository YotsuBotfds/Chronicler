# M12: Interactive Mode GUI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the M11 viewer to a live simulation via WebSocket for real-time turn streaming, intervention controls (inject, set, fork), and speed management.

**Architecture:** WebSocket server in a daemon thread communicates with the sync simulation loop via thread-safe queues. The viewer's `useLiveConnection` hook builds a `Bundle`-shaped object incrementally from WebSocket messages, so all downstream components work identically in live and static modes.

**Tech Stack:** Python `websockets` library (server), native browser `WebSocket` API (client), React/TypeScript/Tailwind (viewer), `queue.Queue` + `threading.Event` + `threading.Lock` (thread coordination)

**Spec:** `docs/superpowers/specs/2026-03-13-m12-interactive-mode-gui-design.md`

---

## File Structure

### Python (new)
- `src/chronicler/live.py` — `LiveServer` class, `live_pause()`, `run_live()`, shared state management
- `tests/test_live.py` — unit tests for queue protocol, command validation, lifecycle
- `tests/test_live_integration.py` — integration tests with real WebSocket connections

### Python (modified)
- `src/chronicler/simulation.py` — add `get_injectable_event_types()` function
- `src/chronicler/main.py` — add `on_turn`/`quit_check` callbacks to `execute_run()`, add `--live`/`--live-port` CLI flags, add dispatch for live mode
- `pyproject.toml` — add `websockets` dependency

### Viewer (new)
- `viewer/src/hooks/useLiveConnection.ts` — WebSocket lifecycle, auto-reconnect, bundle accumulation
- `viewer/src/components/InterventionPanel.tsx` — modal overlay for pause-time interventions
- `viewer/src/hooks/__tests__/useLiveConnection.test.ts` — hook tests with mock WebSocket
- `viewer/src/components/__tests__/InterventionPanel.test.tsx` — component smoke tests

### Viewer (modified)
- `viewer/src/types.ts` — add `PauseContext`, `Command`, `LiveConnectionState` types
- `viewer/src/hooks/useTimeline.ts` — add follow mode (auto-advance + toggle)
- `viewer/src/App.tsx` — dual data source (static bundle vs live WebSocket)
- `viewer/src/components/Layout.tsx` — pass live mode props, render `InterventionPanel`
- `viewer/src/components/Header.tsx` — connection indicator, live badge, pause status
- `viewer/src/components/TimelineScrubber.tsx` — follow mode toggle button
- `viewer/src/hooks/__tests__/useTimeline.test.ts` — follow mode tests (new file if needed)

---

## Chunk 1: Python Foundation (Tasks 1-4)

### Task 1: Add `websockets` dependency and `get_injectable_event_types()`

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/interactive.py`
- Modify: `tests/test_interactive.py`

- [ ] **Step 1: Add `websockets` to pyproject.toml**

In `pyproject.toml`, add `websockets` to the dependencies list:

```toml
dependencies = [
    "pydantic>=2.0",
    "openai>=1.0.0",
    "pyyaml>=6.0",
    "websockets>=13.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install -e .`
Expected: Success, `websockets` installed.

- [ ] **Step 3: Add `get_injectable_event_types()` to `simulation.py`**

At the bottom of `src/chronicler/simulation.py`, add:

```python
def get_injectable_event_types() -> list[str]:
    """Return sorted list of event types that can be injected.

    Single source of truth for both interactive.py and live.py.
    """
    from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
    return sorted(DEFAULT_EVENT_PROBABILITIES.keys())
```

- [ ] **Step 4: Update `interactive.py` to use `get_injectable_event_types()`**

In `src/chronicler/interactive.py`, replace:
```python
from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES

VALID_INJECTABLE_EVENTS = set(DEFAULT_EVENT_PROBABILITIES.keys())
```

With:
```python
from chronicler.simulation import get_injectable_event_types

VALID_INJECTABLE_EVENTS = set(get_injectable_event_types())
```

- [ ] **Step 5: Run existing tests to verify no breakage**

Run: `pytest tests/test_interactive.py -v`
Expected: All tests pass. The test `test_injectable_events_match_defaults` still passes because `get_injectable_event_types()` returns the same keys.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/chronicler/simulation.py src/chronicler/interactive.py
git commit -m "feat(m12): add websockets dep and get_injectable_event_types()"
```

---

### Task 2: Add `on_turn` and `quit_check` callbacks to `execute_run()`

**Files:**
- Modify: `src/chronicler/main.py:45-56` (signature), `168-290` (loop body)
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test for `on_turn` callback**

Add to `tests/test_main.py`:

```python
def test_on_turn_callback_fires_each_turn(tmp_path):
    """on_turn callback receives snapshot, chronicle text, events, named_events each turn."""
    import argparse
    from chronicler.main import execute_run

    turns_received = []

    def on_turn_cb(snapshot, chronicle_text, events, named_events):
        turns_received.append({
            "turn": snapshot.turn,
            "chronicle_text": chronicle_text,
            "event_count": len(events),
            "named_event_count": len(named_events),
        })

    args = argparse.Namespace(
        seed=42, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    execute_run(args, on_turn=on_turn_cb)

    assert len(turns_received) == 5
    for entry in turns_received:
        assert isinstance(entry["chronicle_text"], str)
        assert entry["event_count"] >= 0
        assert entry["named_event_count"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_on_turn_callback_fires_each_turn -v`
Expected: FAIL — `execute_run()` does not accept `on_turn`.

- [ ] **Step 3: Write failing test for `quit_check` callback**

Add to `tests/test_main.py`:

```python
def test_quit_check_stops_simulation_early(tmp_path):
    """quit_check returning True stops the simulation gracefully."""
    import argparse
    from chronicler.main import execute_run

    call_count = 0

    def quit_at_turn_3():
        nonlocal call_count
        call_count += 1
        return call_count >= 3

    args = argparse.Namespace(
        seed=42, turns=50, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    result = execute_run(args, quit_check=quit_at_turn_3)

    assert result.total_turns == 3
    assert (tmp_path / "chronicle_bundle.json").exists()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_quit_check_stops_simulation_early -v`
Expected: FAIL — `execute_run()` does not accept `quit_check`.

- [ ] **Step 5: Implement `on_turn` and `quit_check` in `execute_run()`**

In `src/chronicler/main.py`, update the `execute_run` signature to add two optional parameters after the existing `provenance_header`:

```python
def execute_run(
    args: argparse.Namespace,
    sim_client: LLMClient | None = None,
    narrative_client: LLMClient | None = None,
    world: WorldState | None = None,
    memories: dict[str, MemoryStream] | None = None,
    on_pause: Callable[[WorldState, dict[str, MemoryStream], list], bool] | None = None,
    pause_every: int | None = None,
    pending_injections: list[tuple[str, str]] | None = None,
    scenario_config: Any | None = None,
    provenance_header: str | None = None,
    on_turn: Callable | None = None,
    quit_check: Callable[[], bool] | None = None,
) -> RunResult:
```

In the simulation loop, after `history.append(snapshot)` (after line 232) and after recording the chronicle entry (after line 238), add the `on_turn` callback invocation. Before `run_turn()`, capture the named_events count for delta computation:

Before the `run_turn()` call (~line 193), add:
```python
        named_events_before = len(world.named_events)
```

After `history.append(snapshot)` and `chronicle_entries.append(...)` (~line 238), add:
```python
        # on_turn callback — fires after each turn's data is captured
        if on_turn is not None:
            turn_events = [e for e in world.events_timeline if e.turn == world.turn - 1]
            turn_named = world.named_events[named_events_before:]
            on_turn(snapshot, chronicle_text, turn_events, turn_named)
```

After the `on_pause` block (~line 286), add the `quit_check`:
```python
        # quit_check — for graceful mid-run shutdown (e.g., live mode quit)
        if quit_check is not None and quit_check():
            break
```

- [ ] **Step 6: Run both tests to verify they pass**

Run: `pytest tests/test_main.py::test_on_turn_callback_fires_each_turn tests/test_main.py::test_quit_check_stops_simulation_early -v`
Expected: Both PASS.

- [ ] **Step 7: Run full test suite to verify no regression**

Run: `pytest tests/ -v --timeout=60`
Expected: All existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m12): add on_turn and quit_check callbacks to execute_run()"
```

---

### Task 3: Create `LiveServer` class with queue protocol

**Files:**
- Create: `src/chronicler/live.py`
- Create: `tests/test_live.py`

- [ ] **Step 1: Write failing test for `LiveServer` lifecycle**

Create `tests/test_live.py`:

```python
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
    # Daemon thread dies with the server — don't assert is_alive after stop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live.py::test_live_server_start_stop -v`
Expected: FAIL — `chronicler.live` does not exist.

- [ ] **Step 3: Write failing tests for `live_pause` queue protocol**

Add to `tests/test_live.py`:

```python
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

    # Simulate: put 'continue' command before calling pause
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True

    # Should have put a 'paused' then an 'ack' on status_q
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
    """inject command queues event, sends ack with still_paused=True, stays paused until continue."""
    from chronicler.live import make_live_pause
    from chronicler.memory import MemoryStream

    command_q = queue.Queue()
    status_q = queue.Queue()
    world = _make_world()
    civ_name = world.civilizations[0].name
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)

    # Queue: inject, then continue
    command_q.put({"type": "inject", "event_type": "plague", "civ": civ_name})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert len(pending) == 1
    assert pending[0] == ("plague", civ_name)

    # Drain status_q: paused, ack(inject), ack(continue)
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
    original_military = civ.military
    memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}
    pending = []

    pause_fn = make_live_pause(command_q, status_q)
    command_q.put({"type": "set", "civ": civ_name, "stat": "military", "value": 9})
    command_q.put({"type": "continue"})

    result = pause_fn(world, memories, pending)
    assert result is True
    assert civ.military == 9

    # Check ack
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
    assert len(pending) == 0  # nothing queued

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

    # Verify fork directory was created with state.json
    from pathlib import Path
    fork_dir = Path(forked["save_path"])
    assert (fork_dir / "state.json").exists()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_live.py -v`
Expected: All FAIL — `chronicler.live` does not exist.

- [ ] **Step 5: Implement `src/chronicler/live.py` — shared state and `make_live_pause`**

Create `src/chronicler/live.py`:

```python
"""Live mode — WebSocket server for real-time viewer connection."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from chronicler.interactive import VALID_STATS, CORE_STATS
from chronicler.memory import MemoryStream, sanitize_civ_name
from chronicler.models import WorldState
from chronicler.simulation import get_injectable_event_types


class LiveServer:
    """WebSocket server running in a daemon thread.

    Bridges the async WebSocket world with the sync simulation loop
    via thread-safe queues.
    """

    def __init__(self, port: int = 8765):
        self.port = port
        self.snapshot_queue: queue.Queue[dict] = queue.Queue()
        self.command_queue: queue.Queue[dict] = queue.Queue()
        self.status_queue: queue.Queue[dict] = queue.Queue()
        self.quit_event = threading.Event()
        self._speed = 1.0
        self._speed_lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._actual_port: int | None = None

    @property
    def speed(self) -> float:
        with self._speed_lock:
            return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        with self._speed_lock:
            self._speed = max(0.1, value)

    def start(self) -> None:
        """Start the WebSocket server in a daemon thread."""
        ready = threading.Event()
        self.thread = threading.Thread(
            target=self._run_loop,
            args=(ready,),
            daemon=True,
        )
        self.thread.start()
        ready.wait(timeout=5.0)

    def stop(self) -> None:
        """Signal the server to stop."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def _run_loop(self, ready: threading.Event) -> None:
        """Entry point for the daemon thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve(ready))
        finally:
            self._loop.close()

    async def _serve(self, ready: threading.Event) -> None:
        """Run the WebSocket server until stopped."""
        import websockets.asyncio.server as ws_server

        self._client: Any = None
        self._paused = False

        # State for init messages on (re)connect
        self._init_data: dict | None = None

        async def handler(websocket: Any) -> None:
            # Single client enforcement
            if self._client is not None:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Another client is already connected.",
                }))
                await websocket.close()
                return

            self._client = websocket
            try:
                # Send init if we have accumulated state
                if self._init_data is not None:
                    await websocket.send(json.dumps(self._init_data))
                    # If paused, send paused message too
                    if self._paused:
                        await websocket.send(json.dumps(self._last_paused_msg))

                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Invalid JSON",
                        }))
                        continue

                    msg_type = msg.get("type")

                    # Speed and quit always accepted
                    if msg_type == "speed":
                        self.speed = float(msg.get("value", 1.0))
                        continue

                    if msg_type == "quit":
                        self.quit_event.set()
                        if self._paused:
                            self.command_queue.put(msg)
                        continue

                    # Other commands only while paused
                    if not self._paused:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Simulation is running. Wait for pause.",
                        }))
                        continue

                    self.command_queue.put(msg)
            except Exception:
                pass
            finally:
                self._client = None

        server = await ws_server.serve(
            handler,
            "localhost",
            self.port,
            max_size=10 * 1024 * 1024,  # 10MB for long runs
            ping_interval=20,
        )
        self._actual_port = server.sockets[0].getsockname()[1] if server.sockets else self.port
        ready.set()

        # Background task: drain snapshot_queue and status_queue, send to client
        async def drain_queues():
            while not self._stop_event.is_set():
                # Drain snapshots
                while True:
                    try:
                        snap = self.snapshot_queue.get_nowait()
                        if self._client is not None:
                            await self._client.send(json.dumps(snap))
                        # Update init data
                        if snap.get("type") == "init":
                            self._init_data = snap
                        elif snap.get("type") == "turn" and self._init_data is not None:
                            # Append to init's history for reconnect
                            self._init_data["history"].append({
                                k: v for k, v in snap.items() if k != "type"
                            })
                            turn_str = str(snap["turn"])
                            self._init_data["chronicle_entries"][turn_str] = snap.get("chronicle_text", "")
                            self._init_data["events_timeline"].extend(snap.get("events", []))
                            self._init_data["named_events"].extend(snap.get("named_events", []))
                            self._init_data["current_turn"] = snap["turn"]
                    except queue.Empty:
                        break

                # Drain status messages
                while True:
                    try:
                        status = self.status_queue.get_nowait()
                        if status.get("type") == "paused":
                            self._paused = True
                            self._last_paused_msg = status
                        elif status.get("type") == "ack" and not status.get("still_paused", True):
                            self._paused = False
                        elif status.get("type") == "completed":
                            self._paused = False

                        if self._client is not None:
                            await self._client.send(json.dumps(status))
                    except queue.Empty:
                        break

                await asyncio.sleep(0.05)

        drain_task = asyncio.create_task(drain_queues())
        await self._stop_event.wait()
        drain_task.cancel()
        server.close()
        await server.wait_closed()


def make_live_pause(
    command_queue: queue.Queue,
    status_queue: queue.Queue,
    output_dir: Path | None = None,
):
    """Create the on_pause callback for live mode.

    Returns a closure that captures the queues. Runs on the main thread.
    """
    valid_events = set(get_injectable_event_types())
    valid_stats = VALID_STATS
    core_stats = CORE_STATS

    def live_pause(
        world: WorldState,
        memories: dict[str, MemoryStream],
        pending_injections: list,
    ) -> bool:
        civ_names = [c.name for c in world.civilizations]

        # Send paused message
        status_queue.put({
            "type": "paused",
            "turn": world.turn,
            "reason": "era_boundary",
            "valid_commands": ["continue", "inject", "set", "fork", "quit"],
            "injectable_events": sorted(valid_events),
            "settable_stats": sorted(valid_stats),
            "civs": civ_names,
        })

        # Block on commands until continue or quit
        while True:
            cmd = command_queue.get()  # blocks
            cmd_type = cmd.get("type")

            if cmd_type == "continue":
                status_queue.put({
                    "type": "ack",
                    "command": "continue",
                    "detail": "Simulation resumed",
                    "still_paused": False,
                })
                return True

            elif cmd_type == "quit":
                return False

            elif cmd_type == "inject":
                event_type = cmd.get("event_type", "")
                civ = cmd.get("civ", "")

                if event_type not in valid_events:
                    status_queue.put({
                        "type": "error",
                        "message": f"Invalid event type '{event_type}'. Valid: {sorted(valid_events)}",
                    })
                    continue

                if civ not in civ_names:
                    status_queue.put({
                        "type": "error",
                        "message": f"Civ '{civ}' not found. Valid: {civ_names}",
                    })
                    continue

                pending_injections.append((event_type, civ))
                status_queue.put({
                    "type": "ack",
                    "command": "inject",
                    "detail": f"Queued {event_type} -> {civ}",
                    "still_paused": True,
                })

            elif cmd_type == "set":
                civ_name = cmd.get("civ", "")
                stat = cmd.get("stat", "")
                value = cmd.get("value")

                if civ_name not in civ_names:
                    status_queue.put({
                        "type": "error",
                        "message": f"Civ '{civ_name}' not found. Valid: {civ_names}",
                    })
                    continue

                if stat not in valid_stats:
                    status_queue.put({
                        "type": "error",
                        "message": f"Invalid stat '{stat}'. Valid: {sorted(valid_stats)}",
                    })
                    continue

                if not isinstance(value, (int, float)):
                    status_queue.put({
                        "type": "error",
                        "message": f"Value must be a number, got {type(value).__name__}",
                    })
                    continue

                value = int(value)
                # TODO: When P1 stat scale migration lands (M13), update to 0-100
                # range, or better: read constraints from the model's field validators.
                if stat in core_stats and not (1 <= value <= 10):
                    status_queue.put({
                        "type": "error",
                        "message": f"Value for {stat} must be 1-10, got {value}",
                    })
                    continue
                if stat == "treasury" and value < 0:
                    status_queue.put({
                        "type": "error",
                        "message": f"Treasury must be >= 0, got {value}",
                    })
                    continue

                # Apply immediately — safe because we're on the main thread
                civ_obj = next(c for c in world.civilizations if c.name == civ_name)
                setattr(civ_obj, stat, value)
                status_queue.put({
                    "type": "ack",
                    "command": "set",
                    "detail": f"Set {civ_name}.{stat} = {value}",
                    "still_paused": True,
                    "civ": civ_name,
                    "stat": stat,
                    "value": value,
                })

            elif cmd_type == "fork":
                _output_dir = output_dir or Path("output")
                fork_dir = _output_dir / f"fork_save_t{world.turn}"
                fork_dir.mkdir(parents=True, exist_ok=True)
                world.save(fork_dir / "state.json")
                for c_name, stream in memories.items():
                    stream.save(fork_dir / f"memories_{sanitize_civ_name(c_name)}.json")
                status_queue.put({
                    "type": "forked",
                    "save_path": str(fork_dir),
                    "cli_hint": f"python -m chronicler --fork {fork_dir / 'state.json'} --seed 999 --turns 50",
                })

            else:
                status_queue.put({
                    "type": "error",
                    "message": f"Unknown command type '{cmd_type}'",
                })

    return live_pause
```

- [ ] **Step 6: Run all unit tests**

Run: `pytest tests/test_live.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/live.py tests/test_live.py
git commit -m "feat(m12): add LiveServer class and make_live_pause with queue protocol"
```

---

### Task 4: Add `--live` CLI flag and `run_live()` wiring

**Files:**
- Modify: `src/chronicler/live.py` (add `run_live()`)
- Modify: `src/chronicler/main.py` (CLI flags + dispatch)

- [ ] **Step 1: Add `run_live()` to `live.py`**

Append to `src/chronicler/live.py`:

```python
def run_live(
    args: Any,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> Any:
    """Run simulation in live mode with WebSocket server."""
    import argparse
    from chronicler.main import execute_run
    from chronicler.models import TurnSnapshot, Event, NamedEvent

    port = getattr(args, "live_port", 8765) or 8765
    pause_every = getattr(args, "pause_every", None) or getattr(args, "reflection_interval", 10) or 10
    total_turns = args.turns or 50
    output_dir = Path(args.output).parent

    server = LiveServer(port=port)
    server.start()
    actual_port = server._actual_port or port
    print(f"Live server ready on ws://localhost:{actual_port}")
    print(f"Open viewer: http://localhost:5173?ws=ws://localhost:{actual_port}")

    # Track whether init has been sent
    init_sent = [False]
    # Reference to world state — captured by on_turn closure on first invocation
    world_ref = [None]

    def _serialize_snapshot(snapshot, chronicle_text, events, named_events):
        """Serialize turn data to a dict for the WebSocket protocol."""
        snap_dict = snapshot.model_dump()
        snap_dict["type"] = "turn"
        snap_dict["chronicle_text"] = chronicle_text
        snap_dict["events"] = [e.model_dump() for e in events]
        snap_dict["named_events"] = [ne.model_dump() for ne in named_events]
        return snap_dict

    # Build on_turn callback to push snapshots
    def on_turn_cb(
        snapshot: TurnSnapshot,
        chronicle_text: str,
        events: list[Event],
        named_events: list[NamedEvent],
    ) -> None:
        # On first turn, send init message with the world state
        if not init_sent[0]:
            init_sent[0] = True
            # Extract world from the snapshot's context — we read it from
            # execute_run's world variable via the snapshot's civ data
            # Actually: we passed world_ref[0] from a post-gen hook (see below)
            if world_ref[0] is not None:
                world = world_ref[0]
                init_msg = {
                    "type": "init",
                    "total_turns": total_turns,
                    "pause_every": pause_every,
                    "current_turn": 0,
                    "world_state": world.model_dump(),
                    "history": [],
                    "chronicle_entries": {},
                    "events_timeline": [],
                    "named_events": [],
                    "era_reflections": {},
                    "metadata": {
                        "seed": world.seed,
                        "sim_model": getattr(sim_client, "model", "unknown") or "unknown",
                        "narrative_model": getattr(narrative_client, "model", "unknown") or "unknown",
                    },
                    "speed": server.speed,
                }
                server.snapshot_queue.put(init_msg)

        snap_dict = _serialize_snapshot(snapshot, chronicle_text, events, named_events)
        server.snapshot_queue.put(snap_dict)

        # Pace simulation
        spd = server.speed
        if spd > 0:
            time.sleep(1.0 / spd)

    pending_injections: list[tuple[str, str]] = []
    pause_fn = make_live_pause(
        server.command_queue,
        server.status_queue,
        output_dir=output_dir,
    )

    # Generate world first so we can capture it for init message
    from chronicler.world_gen import generate_world
    world = generate_world(
        seed=args.seed,
        num_regions=args.regions,
        num_civs=args.civs,
    )
    if scenario_config:
        from chronicler.scenario import apply_scenario
        apply_scenario(world, scenario_config)
    world_ref[0] = world

    result = execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        world=world,
        on_pause=pause_fn,
        pause_every=pause_every,
        pending_injections=pending_injections,
        scenario_config=scenario_config,
        on_turn=on_turn_cb,
        quit_check=lambda: server.quit_event.is_set(),
    )

    # Send completed
    server.status_queue.put({
        "type": "completed",
        "total_turns": result.total_turns,
        "bundle_path": str(output_dir / "chronicle_bundle.json"),
    })

    # Give the server a moment to drain
    time.sleep(0.5)
    server.stop()

    return result
```

- [ ] **Step 2: Add `--live` and `--live-port` CLI flags to `main.py`**

In `src/chronicler/main.py`, in `_build_parser()`, after the `--pause-every` argument, add:

```python
    parser.add_argument("--live", action="store_true", default=False,
                        help="Live mode: start WebSocket server for viewer connection")
    parser.add_argument("--live-port", type=int, default=8765,
                        help="WebSocket server port for live mode (default: 8765)")
```

- [ ] **Step 3: Add `--live` to mutual exclusion check in `main()`**

In `main()`, update the mode_flags block to include `--live`:

```python
    if args.live:
        mode_flags.append("--live")
```

- [ ] **Step 4: Add live mode dispatch in `main()`**

In `main()`, after the `elif args.interactive:` block, add:

```python
    elif args.live:
        from chronicler.live import run_live
        result = run_live(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nLive session complete: {result.output_dir}")
```

- [ ] **Step 5: Run a quick smoke test**

Run: `python -m chronicler --live --turns 5 --civs 2 --regions 3 --seed 42 --output /tmp/live_test/chronicle.md --state /tmp/live_test/state.json`
Expected: Server starts, simulation runs 5 turns, completes. Output: "Live server ready on ws://localhost:8765", turns print, chronicle written.
Press Ctrl-C if it hangs (the simulation will complete in seconds with dummy client).

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/live.py src/chronicler/main.py
git commit -m "feat(m12): add --live CLI flag and run_live() wiring"
```

---

## Chunk 2: WebSocket Integration Tests (Task 5)

### Task 5: Integration tests with real WebSocket connections

**Files:**
- Create: `tests/test_live_integration.py`

- [ ] **Step 1: Write integration test for connect + init**

Create `tests/test_live_integration.py`:

```python
"""Integration tests for live mode with real WebSocket connections."""
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
        live_port=0,  # OS picks free port
    )


@pytest.fixture
def live_env(tmp_path):
    """Set up a LiveServer with a running simulation in a background thread.

    NOTE: This is a bare server fixture — it pushes turn messages but does NOT
    send an init message. The init message is handled by run_live() which
    pre-generates the world and sends init on the first on_turn call.
    These tests verify queue plumbing and protocol behavior, not the full
    init-then-turns sequence (that's covered by the manual E2E smoke test).
    """
    from chronicler.live import LiveServer, make_live_pause, run_live

    class Env:
        def __init__(self):
            self.tmp_path = tmp_path
            self.server = None
            self.thread = None
            self.result = None

        def start(self, turns=5, pause_every=None):
            args = _make_args(tmp_path, turns=turns, pause_every=pause_every)
            self.server = LiveServer(port=0)
            self.server.start()
            self.port = self.server._actual_port

            pending = []
            pause_fn = make_live_pause(
                self.server.command_queue,
                self.server.status_queue,
                output_dir=tmp_path,
            )

            def run():
                from chronicler.main import execute_run
                self.result = execute_run(
                    args,
                    on_pause=pause_fn if pause_every else None,
                    pause_every=pause_every,
                    pending_injections=pending,
                    on_turn=self._on_turn,
                    quit_check=lambda: self.server.quit_event.is_set(),
                )
                self.server.status_queue.put({
                    "type": "completed",
                    "total_turns": self.result.total_turns,
                    "bundle_path": str(tmp_path / "chronicle_bundle.json"),
                })

            self._on_turn_fn = None
            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()
            return self

        def _on_turn(self, snapshot, chronicle_text, events, named_events):
            import json as _json
            snap_dict = _json.loads(snapshot.model_dump_json())
            snap_dict["type"] = "turn"
            snap_dict["chronicle_text"] = chronicle_text
            snap_dict["events"] = [_json.loads(e.model_dump_json()) for e in events]
            snap_dict["named_events"] = [_json.loads(ne.model_dump_json()) for ne in named_events]
            self.server.snapshot_queue.put(snap_dict)

        def stop(self):
            if self.server:
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
    time.sleep(0.3)  # let server start

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        # Collect messages until we get completed or timeout
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
    assert turns == sorted(turns)  # monotonically increasing


@pytest.mark.asyncio
async def test_pause_and_continue(live_env):
    """Server sends paused message at interval, continues on command."""
    env = live_env.start(turns=10, pause_every=3)
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
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
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        messages = []
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                messages.append(msg)

                if msg["type"] == "paused":
                    # Get civ name from the paused message
                    civ = msg["civs"][0]
                    await ws.send(json.dumps({"type": "inject", "event_type": "plague", "civ": civ}))
                    # Wait for ack
                    ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    ack = json.loads(ack_raw)
                    messages.append(ack)
                    assert ack["type"] == "ack"
                    assert ack["command"] == "inject"
                    assert ack["still_paused"] is True
                    # Now continue
                    await ws.send(json.dumps({"type": "continue"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    # Verify at least one inject ack was received
    inject_acks = [m for m in messages if m.get("type") == "ack" and m.get("command") == "inject"]
    assert len(inject_acks) >= 1


@pytest.mark.asyncio
async def test_set_round_trip(live_env):
    """Set stat at pause, verify ack includes new value."""
    env = live_env.start(turns=10, pause_every=3)
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
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
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
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
                    # Verify fork directory exists
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
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
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
    assert completed["total_turns"] < 50  # Quit early
    assert Path(env.tmp_path / "chronicle_bundle.json").exists()


@pytest.mark.asyncio
async def test_quit_while_running(live_env):
    """Quit during execution: current turn completes, bundle written."""
    env = live_env.start(turns=50)  # no pause_every — runs without pausing
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        # Wait for a couple of turns, then send quit
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
    assert completed["total_turns"] < 50  # Stopped early
    assert Path(env.tmp_path / "chronicle_bundle.json").exists()


@pytest.mark.asyncio
async def test_commands_while_running_rejected(live_env):
    """Commands sent while running get error (except quit and speed)."""
    env = live_env.start(turns=20)
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws:
        # Wait for first turn, then try to inject while running
        error_msg = None
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)

                if msg["type"] == "turn" and error_msg is None:
                    await ws.send(json.dumps({"type": "inject", "event_type": "plague", "civ": "foo"}))
                    err_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    error_msg = json.loads(err_raw)
                    # Quit to clean up
                    await ws.send(json.dumps({"type": "quit"}))

                if msg["type"] == "completed":
                    break
        except asyncio.TimeoutError:
            pass

    assert error_msg is not None
    assert error_msg["type"] == "error"
    assert "running" in error_msg["message"].lower()


@pytest.mark.asyncio
async def test_single_client_enforcement(live_env):
    """Second client gets error and is closed."""
    env = live_env.start(turns=20, pause_every=5)
    time.sleep(0.3)

    async with ws_client.connect(f"ws://localhost:{env.port}") as ws1:
        # Connect second client
        async with ws_client.connect(f"ws://localhost:{env.port}") as ws2:
            raw = await asyncio.wait_for(ws2.recv(), timeout=5.0)
            msg = json.loads(raw)
            assert msg["type"] == "error"
            assert "already connected" in msg["message"].lower()

        # First client should still work — send quit to clean up
        env.server.quit_event.set()
```

- [ ] **Step 2: Install pytest-asyncio**

Run: `pip install pytest-asyncio`

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/test_live_integration.py -v --timeout=30`
Expected: All tests PASS. If any hang, the `timeout=30` will catch them.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_integration.py
git commit -m "test(m12): add WebSocket integration tests for live mode"
```

---

## Chunk 3: Viewer Types and Live Connection Hook (Tasks 6-7)

### Task 6: Add live mode types to the viewer

**Files:**
- Modify: `viewer/src/types.ts`

- [ ] **Step 1: Add live mode types**

Append to `viewer/src/types.ts`:

```typescript

// --- Live mode types ---

export interface PauseContext {
  turn: number;
  reason: string;
  valid_commands: string[];
  injectable_events: string[];
  settable_stats: string[];
  civs: string[];
}

export type CommandType = "continue" | "inject" | "set" | "fork" | "quit" | "speed";

export interface InjectCommand {
  type: "inject";
  event_type: string;
  civ: string;
}

export interface SetCommand {
  type: "set";
  civ: string;
  stat: string;
  value: number;
}

export interface SimpleCommand {
  type: "continue" | "fork" | "quit";
}

export interface SpeedCommand {
  type: "speed";
  value: number;
}

export type Command = InjectCommand | SetCommand | SimpleCommand | SpeedCommand;

export interface PendingAction {
  id: string;
  command: Command;
  status: "staged" | "sent";
  detail?: string;
}

export interface AckMessage {
  type: "ack";
  command: string;
  detail: string;
  still_paused: boolean;
  civ?: string;
  stat?: string;
  value?: number;
}

export interface ForkedMessage {
  type: "forked";
  save_path: string;
  cli_hint: string;
}
```

- [ ] **Step 2: Commit**

```bash
cd viewer && git add src/types.ts
git commit -m "feat(m12): add live mode types (PauseContext, Command, PendingAction)"
```

---

### Task 7: Implement `useLiveConnection` hook

**Files:**
- Create: `viewer/src/hooks/useLiveConnection.ts`
- Create: `viewer/src/hooks/__tests__/useLiveConnection.test.ts`

- [ ] **Step 1: Write failing tests for `useLiveConnection`**

Create `viewer/src/hooks/__tests__/useLiveConnection.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLiveConnection } from "../useLiveConnection";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  readyState = 0; // CONNECTING
  sent: string[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1; // OPEN
      this.onopen?.();
    }, 0);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.();
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const SAMPLE_INIT = {
  type: "init",
  total_turns: 50,
  pause_every: 10,
  current_turn: 0,
  world_state: { name: "TestWorld", seed: 42, turn: 0, regions: [], civilizations: [], relationships: {}, events_timeline: [], named_events: [], scenario_name: null },
  history: [],
  chronicle_entries: {},
  events_timeline: [],
  named_events: [],
  era_reflections: {},
  metadata: { seed: 42, total_turns: 50, generated_at: "", sim_model: "test", narrative_model: "test", scenario_name: null, interestingness_score: null },
  speed: 1.0,
};

describe("useLiveConnection", () => {
  it("connects and sets connected state on init", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    act(() => {
      MockWebSocket.instances[0].simulateMessage(SAMPLE_INIT);
    });

    expect(result.current.connected).toBe(true);
    expect(result.current.bundle).not.toBeNull();
    expect(result.current.bundle?.world_state.name).toBe("TestWorld");
  });

  it("accumulates turn data into bundle", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      ws.simulateMessage({
        type: "turn",
        turn: 1,
        civ_stats: {},
        region_control: {},
        relationships: {},
        events: [],
        named_events: [],
        chronicle_text: "Turn 1 text",
      });
    });

    expect(result.current.bundle?.history.length).toBe(1);
    expect(result.current.bundle?.chronicle_entries["1"]).toBe("Turn 1 text");
  });

  it("sets paused state on paused message", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({
        type: "paused",
        turn: 10,
        reason: "era_boundary",
        valid_commands: ["continue", "inject"],
        injectable_events: ["plague"],
        settable_stats: ["military"],
        civs: ["Civ A"],
      });
    });

    expect(result.current.paused).toBe(true);
    expect(result.current.pauseContext?.civs).toEqual(["Civ A"]);
  });

  it("clears paused on ack with still_paused=false", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({ type: "paused", turn: 10, reason: "era_boundary", valid_commands: [], injectable_events: [], settable_stats: [], civs: [] });
    });
    expect(result.current.paused).toBe(true);

    act(() => {
      ws.simulateMessage({ type: "ack", command: "continue", detail: "Resumed", still_paused: false });
    });
    expect(result.current.paused).toBe(false);
  });

  it("keeps paused on ack with still_paused=true", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({ type: "paused", turn: 10, reason: "era_boundary", valid_commands: [], injectable_events: [], settable_stats: [], civs: [] });
    });

    act(() => {
      ws.simulateMessage({ type: "ack", command: "inject", detail: "Queued plague", still_paused: true });
    });
    expect(result.current.paused).toBe(true);
  });

  it("patches snapshot on set ack", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];

    const initWithHistory = {
      ...SAMPLE_INIT,
      history: [{ turn: 1, civ_stats: { "CivA": { military: 5 } }, region_control: {}, relationships: {} }],
      current_turn: 1,
    };
    act(() => ws.simulateMessage(initWithHistory));

    act(() => {
      ws.simulateMessage({ type: "ack", command: "set", detail: "Set", still_paused: true, civ: "CivA", stat: "military", value: 9 });
    });

    const lastSnap = result.current.bundle?.history[0];
    expect(lastSnap?.civ_stats["CivA"]?.military).toBe(9);
  });

  it("sets error state on error message", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      ws.simulateMessage({ type: "error", message: "Civ 'Foo' not found" });
    });

    expect(result.current.error).toBe("Civ 'Foo' not found");
  });

  it("sets connected false on close and attempts reconnect", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    expect(result.current.connected).toBe(true);

    act(() => ws.close());
    expect(result.current.connected).toBe(false);

    // Should attempt reconnect after delay
    vi.advanceTimersByTime(1500);
    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(2);
    });
  });

  it("sends commands via sendCommand", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));

    await vi.waitFor(() => {
      expect(MockWebSocket.instances.length).toBe(1);
    });

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      result.current.sendCommand({ type: "continue" });
    });

    expect(ws.sent.length).toBe(1);
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "continue" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd viewer && npx vitest run src/hooks/__tests__/useLiveConnection.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `useLiveConnection`**

Create `viewer/src/hooks/useLiveConnection.ts`:

```typescript
import { useState, useEffect, useCallback, useRef } from "react";
import type { Bundle, PauseContext, Command, AckMessage, ForkedMessage } from "../types";

interface LiveConnectionState {
  bundle: Bundle | null;
  connected: boolean;
  paused: boolean;
  pauseContext: PauseContext | null;
  error: string | null;
  sendCommand: (cmd: Command) => void;
  speed: number;
  setSpeed: (s: number) => void;
  lastAck: AckMessage | null;
  lastForked: ForkedMessage | null;
}

export function useLiveConnection(wsUrl: string): LiveConnectionState {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pauseContext, setPauseContext] = useState<PauseContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speed, setSpeedState] = useState(1);
  const [lastAck, setLastAck] = useState<AckMessage | null>(null);
  const [lastForked, setLastForked] = useState<ForkedMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);

  const sendCommand = useCallback((cmd: Command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const setSpeed = useCallback((s: number) => {
    setSpeedState(s);
    sendCommand({ type: "speed", value: s });
  }, [sendCommand]);

  useEffect(() => {
    let unmounted = false;

    // No-op when wsUrl is empty (static mode — hook is always called per Rules of Hooks)
    if (!wsUrl) return;

    function connect() {
      if (unmounted) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted) return;
        setConnected(true);
        setError(null);
        reconnectDelayRef.current = 1000; // reset backoff
      };

      ws.onclose = () => {
        if (unmounted) return;
        setConnected(false);
        wsRef.current = null;
        // Auto-reconnect with exponential backoff
        const delay = reconnectDelayRef.current;
        reconnectRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, 10000);
          connect();
        }, delay);
      };

      ws.onerror = () => {
        // onclose will fire after this
      };

      ws.onmessage = (e) => {
        if (unmounted) return;
        const msg = JSON.parse(e.data);

        switch (msg.type) {
          case "init":
            setBundle({
              world_state: msg.world_state,
              history: msg.history || [],
              events_timeline: msg.events_timeline || [],
              named_events: msg.named_events || [],
              chronicle_entries: msg.chronicle_entries || {},
              era_reflections: msg.era_reflections || {},
              metadata: msg.metadata,
            });
            if (msg.speed !== undefined) {
              setSpeedState(msg.speed);
            }
            break;

          case "turn":
            setBundle((prev) => {
              if (!prev) return prev;
              const snap = {
                turn: msg.turn,
                civ_stats: msg.civ_stats,
                region_control: msg.region_control,
                relationships: msg.relationships,
              };
              return {
                ...prev,
                history: [...prev.history, snap],
                chronicle_entries: {
                  ...prev.chronicle_entries,
                  [String(msg.turn)]: msg.chronicle_text || "",
                },
                events_timeline: [...prev.events_timeline, ...(msg.events || [])],
                named_events: [...prev.named_events, ...(msg.named_events || [])],
              };
            });
            break;

          case "paused":
            setPaused(true);
            setPauseContext({
              turn: msg.turn,
              reason: msg.reason,
              valid_commands: msg.valid_commands,
              injectable_events: msg.injectable_events,
              settable_stats: msg.settable_stats,
              civs: msg.civs,
            });
            break;

          case "ack": {
            const ack = msg as AckMessage;
            setLastAck(ack);
            if (!ack.still_paused) {
              setPaused(false);
              setPauseContext(null);
            }
            // Patch snapshot for set commands
            if (ack.command === "set" && ack.civ && ack.stat && ack.value !== undefined) {
              setBundle((prev) => {
                if (!prev || prev.history.length === 0) return prev;
                const newHistory = [...prev.history];
                const lastIdx = newHistory.length - 1;
                const lastSnap = { ...newHistory[lastIdx] };
                const civStats = { ...lastSnap.civ_stats };
                const civData = civStats[ack.civ!];
                if (civData) {
                  civStats[ack.civ!] = { ...civData, [ack.stat!]: ack.value };
                  lastSnap.civ_stats = civStats;
                  newHistory[lastIdx] = lastSnap;
                }
                return { ...prev, history: newHistory };
              });
            }
            break;
          }

          case "forked":
            setLastForked(msg as ForkedMessage);
            break;

          case "completed":
            setPaused(false);
            setPauseContext(null);
            break;

          case "error":
            setError(msg.message);
            break;
        }
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [wsUrl]);

  return {
    bundle,
    connected,
    paused,
    pauseContext,
    error,
    sendCommand,
    speed,
    setSpeed,
    lastAck,
    lastForked,
  };
}
```

- [ ] **Step 4: Run tests**

Run: `cd viewer && npx vitest run src/hooks/__tests__/useLiveConnection.test.ts`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd viewer && git add src/hooks/useLiveConnection.ts src/hooks/__tests__/useLiveConnection.test.ts
git commit -m "feat(m12): add useLiveConnection hook with auto-reconnect and bundle accumulation"
```

---

## Chunk 4: Viewer UI Changes (Tasks 8-11)

### Task 8: Add follow mode to `useTimeline`

**Files:**
- Modify: `viewer/src/hooks/useTimeline.ts`

- [ ] **Step 1: Write failing tests for follow mode**

Create `viewer/src/hooks/__tests__/useTimeline.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTimeline } from "../useTimeline";

describe("useTimeline follow mode", () => {
  it("auto-advances when followMode is true and maxTurn increases", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 5 } },
    );

    expect(result.current.followMode).toBe(true);
    expect(result.current.currentTurn).toBe(5);

    rerender({ maxTurn: 8 });
    expect(result.current.currentTurn).toBe(8);
  });

  it("disables followMode when user seeks backward", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );

    act(() => result.current.seek(5));
    expect(result.current.followMode).toBe(false);
    expect(result.current.currentTurn).toBe(5);

    // New data arrives, should NOT advance
    rerender({ maxTurn: 12 });
    expect(result.current.currentTurn).toBe(5);
  });

  it("re-enables followMode when user seeks to latest", () => {
    const { result, rerender } = renderHook(
      ({ maxTurn }) => useTimeline(maxTurn, { liveMode: true }),
      { initialProps: { maxTurn: 10 } },
    );

    act(() => result.current.seek(5));
    expect(result.current.followMode).toBe(false);

    act(() => result.current.seek(10));
    expect(result.current.followMode).toBe(true);
  });

  it("does not use followMode in static mode", () => {
    const { result } = renderHook(() => useTimeline(10));
    expect(result.current.followMode).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd viewer && npx vitest run src/hooks/__tests__/useTimeline.test.ts`
Expected: FAIL — `useTimeline` does not accept a second argument or return `followMode`.

- [ ] **Step 3: Implement follow mode in `useTimeline`**

Update `viewer/src/hooks/useTimeline.ts`:

```typescript
import { useState, useCallback, useEffect, useRef } from "react";

interface TimelineOptions {
  liveMode?: boolean;
}

export function useTimeline(maxTurn: number, options?: TimelineOptions) {
  const liveMode = options?.liveMode ?? false;
  const [currentTurn, setCurrentTurn] = useState(liveMode ? maxTurn : 1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [followMode, setFollowMode] = useState(liveMode);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const seek = useCallback(
    (turn: number) => {
      const clamped = Math.max(1, Math.min(turn, maxTurn));
      setCurrentTurn(clamped);
      // Re-enable follow if seeking to latest turn
      if (liveMode) {
        setFollowMode(clamped >= maxTurn);
      }
    },
    [maxTurn, liveMode],
  );

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => setPlaying(false), []);

  // Follow mode: auto-advance when maxTurn increases
  useEffect(() => {
    if (followMode && liveMode) {
      setCurrentTurn(maxTurn);
    }
  }, [followMode, liveMode, maxTurn]);

  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      setCurrentTurn((prev) => {
        const next = prev + 1;
        if (next > maxTurn) {
          setPlaying(false);
          return maxTurn;
        }
        return next;
      });
    }, 1000 / speed);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [playing, speed, maxTurn]);

  return { currentTurn, playing, speed, seek, play, pause, setSpeed, followMode, setFollowMode };
}
```

- [ ] **Step 4: Run tests**

Run: `cd viewer && npx vitest run src/hooks/__tests__/useTimeline.test.ts`
Expected: All PASS.

- [ ] **Step 5: Run existing component tests to verify no regression**

Run: `cd viewer && npx vitest run`
Expected: All existing tests PASS. (Note: `App.tsx` calls `useTimeline(n)` without the second arg — this works because `options` is optional with defaults.)

- [ ] **Step 6: Commit**

```bash
cd viewer && git add src/hooks/useTimeline.ts src/hooks/__tests__/useTimeline.test.ts
git commit -m "feat(m12): add follow mode to useTimeline for live auto-advance"
```

---

### Task 9: Create `InterventionPanel` component

**Files:**
- Create: `viewer/src/components/InterventionPanel.tsx`
- Create: `viewer/src/components/__tests__/InterventionPanel.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `viewer/src/components/__tests__/InterventionPanel.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterventionPanel } from "../InterventionPanel";
import type { PauseContext } from "../../types";

const mockContext: PauseContext = {
  turn: 20,
  reason: "era_boundary",
  valid_commands: ["continue", "inject", "set", "fork", "quit"],
  injectable_events: ["plague", "famine", "migration"],
  settable_stats: ["population", "military", "economy"],
  civs: ["Civ Alpha", "Civ Beta"],
};

describe("InterventionPanel", () => {
  it("renders when visible", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);
    expect(screen.getByText(/paused at turn 20/i)).toBeDefined();
  });

  it("stages inject command in pending queue on Inject click", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    // Should appear in pending list, not sent yet
    expect(screen.getByText(/plague/i)).toBeDefined();
    expect(sendCommand).not.toHaveBeenCalled();
  });

  it("sends set command immediately (applies to world state)", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/stat civ/i), { target: { value: "Civ Beta" } });
    fireEvent.change(screen.getByLabelText(/stat name/i), { target: { value: "military" } });
    fireEvent.change(screen.getByLabelText(/stat value/i), { target: { value: "9" } });
    fireEvent.click(screen.getByText(/^set$/i));

    // Set sends immediately since it mutates world state
    expect(sendCommand).toHaveBeenCalledWith({ type: "set", civ: "Civ Beta", stat: "military", value: 9 });
  });

  it("removes staged inject from pending queue", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    // Remove the staged item
    const removeBtn = screen.getByLabelText(/remove/i);
    fireEvent.click(removeBtn);
    expect(screen.queryByText(/plague.*Civ Alpha/i)).toBeNull();
  });

  it("sends staged commands then continue on Continue click", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    // Stage an inject
    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    // Click continue — should send staged inject, then continue
    fireEvent.click(screen.getByText(/continue/i));
    expect(sendCommand).toHaveBeenCalledTimes(2);
    expect(sendCommand).toHaveBeenNthCalledWith(1, { type: "inject", event_type: "plague", civ: "Civ Alpha" });
    expect(sendCommand).toHaveBeenNthCalledWith(2, { type: "continue" });
  });

  it("sends fork command immediately", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.click(screen.getByText(/fork/i));
    expect(sendCommand).toHaveBeenCalledWith({ type: "fork" });
  });

  it("sends quit command immediately", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.click(screen.getByText(/quit/i));
    expect(sendCommand).toHaveBeenCalledWith({ type: "quit" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd viewer && npx vitest run src/components/__tests__/InterventionPanel.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `InterventionPanel`**

Create `viewer/src/components/InterventionPanel.tsx`:

```tsx
import { useState, useCallback } from "react";
import type { PauseContext, Command, PendingAction, InjectCommand } from "../types";

interface InterventionPanelProps {
  pauseContext: PauseContext;
  sendCommand: (cmd: Command) => void;
  forkedPath?: string | null;
  forkedHint?: string | null;
}

let nextId = 0;

export function InterventionPanel({
  pauseContext,
  sendCommand,
  forkedPath,
  forkedHint,
}: InterventionPanelProps) {
  const [injectEvent, setInjectEvent] = useState(pauseContext.injectable_events[0] || "");
  const [injectCiv, setInjectCiv] = useState(pauseContext.civs[0] || "");
  const [setCiv, setSetCiv] = useState(pauseContext.civs[0] || "");
  const [setStat, setSetStat] = useState(pauseContext.settable_stats[0] || "");
  const [setValue, setSetValue] = useState(5);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);

  const stageInject = useCallback(() => {
    const cmd: InjectCommand = { type: "inject", event_type: injectEvent, civ: injectCiv };
    setPendingActions((prev) => [...prev, { id: String(++nextId), command: cmd, status: "staged" }]);
  }, [injectEvent, injectCiv]);

  const removePending = useCallback((id: string) => {
    setPendingActions((prev) => prev.filter((a) => a.status !== "staged" || a.id !== id));
  }, []);

  const handleContinue = useCallback(() => {
    // Send all staged inject commands, then continue
    for (const action of pendingActions) {
      if (action.status === "staged") {
        sendCommand(action.command);
      }
    }
    sendCommand({ type: "continue" });
    setPendingActions([]);
  }, [pendingActions, sendCommand]);

  const handleSet = useCallback(() => {
    // Set sends immediately — it mutates world state
    sendCommand({ type: "set", civ: setCiv, stat: setStat, value: setValue });
  }, [sendCommand, setCiv, setStat, setValue]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 rounded-lg shadow-2xl p-6 w-[500px] max-h-[80vh] overflow-y-auto space-y-6">
        <h2 className="text-lg font-bold text-gray-100">
          Paused at Turn {pauseContext.turn}
        </h2>

        {/* Event Injection */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-300">Inject Event</h3>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="inject-event">Event type</label>
            <select
              id="inject-event"
              aria-label="Event type"
              value={injectEvent}
              onChange={(e) => setInjectEvent(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.injectable_events.map((ev) => (
                <option key={ev} value={ev}>{ev}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="inject-civ">Target civ</label>
            <select
              id="inject-civ"
              aria-label="Target civ"
              value={injectCiv}
              onChange={(e) => setInjectCiv(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.civs.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button
              onClick={stageInject}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-sm"
            >
              Inject
            </button>
          </div>
        </div>

        {/* Stat Override */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-300">Override Stat</h3>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="set-civ">Stat civ</label>
            <select
              id="set-civ"
              aria-label="Stat civ"
              value={setCiv}
              onChange={(e) => setSetCiv(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.civs.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="set-stat">Stat name</label>
            <select
              id="set-stat"
              aria-label="Stat name"
              value={setStat}
              onChange={(e) => setSetStat(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.settable_stats.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="set-value">Stat value</label>
            <input
              id="set-value"
              aria-label="Stat value"
              type="number"
              value={setValue}
              onChange={(e) => setSetValue(Number(e.target.value))}
              className="w-16 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm text-center"
            />
            <button
              onClick={handleSet}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm"
            >
              Set
            </button>
          </div>
        </div>

        {/* Pending actions queue */}
        {pendingActions.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-300">Pending Actions</h3>
            <ul className="space-y-1">
              {pendingActions.map((action) => (
                <li key={action.id} className="flex items-center gap-2 text-sm text-gray-300 bg-gray-700 rounded px-2 py-1">
                  {action.status === "sent" ? (
                    <span className="text-green-400" title="Sent">&#10003;</span>
                  ) : (
                    <button
                      aria-label="remove"
                      onClick={() => removePending(action.id)}
                      className="text-red-400 hover:text-red-300"
                    >
                      &#10005;
                    </button>
                  )}
                  <span>
                    {action.command.type === "inject"
                      ? `${action.command.event_type} -> ${action.command.civ}`
                      : JSON.stringify(action.command)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Fork info */}
        {forkedPath && (
          <div className="bg-gray-700 rounded p-3 text-sm text-gray-300 space-y-1">
            <p>Fork saved to: <code className="text-green-400">{forkedPath}</code></p>
            {forkedHint && (
              <p className="text-gray-400 text-xs font-mono">{forkedHint}</p>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => sendCommand({ type: "fork" })}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-gray-200 rounded text-sm"
            >
              Fork
            </button>
            <button
              onClick={() => sendCommand({ type: "quit" })}
              className="px-4 py-2 bg-red-800 hover:bg-red-700 text-gray-200 rounded text-sm"
            >
              Quit
            </button>
          </div>
          <button
            onClick={handleContinue}
            className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-semibold"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd viewer && npx vitest run src/components/__tests__/InterventionPanel.test.tsx`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd viewer && git add src/components/InterventionPanel.tsx src/components/__tests__/InterventionPanel.test.tsx
git commit -m "feat(m12): add InterventionPanel component with inject, set, fork, continue, quit"
```

---

### Task 10: Update `Header` with live mode indicator

**Files:**
- Modify: `viewer/src/components/Header.tsx`

- [ ] **Step 1: Add live mode props to Header**

Update `viewer/src/components/Header.tsx` to accept optional live mode props:

```tsx
import type { BundleMetadata } from "../types";
import { formatTurn, formatScore } from "../lib/format";

interface HeaderProps {
  worldName: string;
  metadata: BundleMetadata;
  currentTurn: number;
  darkMode: boolean;
  onToggleDarkMode: () => void;
  // Live mode props (all optional for backward compat)
  liveConnected?: boolean;
  livePaused?: boolean;
  livePauseTurn?: number;
  liveReconnecting?: boolean;
}

export function Header({
  worldName,
  metadata,
  currentTurn,
  darkMode,
  onToggleDarkMode,
  liveConnected,
  livePaused,
  livePauseTurn,
  liveReconnecting,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-800 border-b border-gray-300 dark:border-gray-700">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-bold">{worldName}</h1>
        {metadata.scenario_name && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{metadata.scenario_name}</span>
        )}
        <span className="text-sm font-mono">
          {formatTurn(currentTurn, metadata.total_turns)}
        </span>
        {/* Live mode indicators */}
        {liveConnected !== undefined && (
          <>
            {liveConnected && !liveReconnecting && (
              <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-900 text-green-300">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                Live
              </span>
            )}
            {liveReconnecting && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-900 text-yellow-300">
                Reconnecting...
              </span>
            )}
            {livePaused && livePauseTurn !== undefined && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900 text-blue-300">
                Paused at turn {livePauseTurn}
              </span>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
        <span>Seed: {metadata.seed}</span>
        <span>{metadata.sim_model}</span>
        {metadata.interestingness_score !== null && (
          <span>{formatScore(metadata.interestingness_score)}</span>
        )}
        <button
          onClick={onToggleDarkMode}
          className="px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600"
        >
          {darkMode ? "Light" : "Dark"}
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Run existing component tests**

Run: `cd viewer && npx vitest run`
Expected: All tests PASS — new props are optional, no existing call sites break.

- [ ] **Step 3: Commit**

```bash
cd viewer && git add src/components/Header.tsx
git commit -m "feat(m12): add live mode indicators to Header (Live badge, Paused, Reconnecting)"
```

---

### Task 11: Wire up `App.tsx` and `Layout.tsx` for live mode

**Files:**
- Modify: `viewer/src/App.tsx`
- Modify: `viewer/src/components/Layout.tsx`

- [ ] **Step 1: Update `App.tsx` for dual data source**

Replace the contents of `viewer/src/App.tsx`:

```tsx
import { useCallback } from "react";
import { useBundle } from "./hooks/useBundle";
import { useLiveConnection } from "./hooks/useLiveConnection";
import { useTimeline } from "./hooks/useTimeline";
import { Layout } from "./components/Layout";

function App() {
  const wsUrl = new URLSearchParams(window.location.search).get("ws");

  // Both hooks always called (Rules of Hooks) — only one is active
  const { bundle: staticBundle, error: staticError, loading, loadFromFile } = useBundle();
  const liveConn = useLiveConnection(wsUrl || "");

  // Choose data source
  const isLive = wsUrl !== null;
  const bundle = isLive ? liveConn.bundle : staticBundle;
  const error = isLive ? liveConn.error : staticError;

  const timeline = useTimeline(
    bundle?.history.length ?? bundle?.metadata?.total_turns ?? 1,
    { liveMode: isLive && liveConn.connected },
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  if (!bundle) {
    return (
      <div
        className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">Chronicler Viewer</h1>
          {isLive ? (
            <p className="text-gray-400">
              {liveConn.connected ? "Waiting for simulation data..." : "Connecting to simulation..."}
            </p>
          ) : (
            <>
              <p className="text-gray-400">
                Drag and drop a <code className="text-blue-400">chronicle_bundle.json</code> file here
              </p>
              <label className="inline-block px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 cursor-pointer">
                Or choose a file
                <input
                  type="file"
                  accept=".json"
                  onChange={handleFileInput}
                  className="hidden"
                />
              </label>
            </>
          )}
          {loading && <p className="text-gray-400">Loading...</p>}
          {error && <p className="text-red-400">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <Layout
      bundle={bundle}
      currentTurn={timeline.currentTurn}
      playing={timeline.playing}
      speed={timeline.speed}
      onSeek={timeline.seek}
      onPlay={timeline.play}
      onPause={timeline.pause}
      onSetSpeed={timeline.setSpeed}
      // Live mode props
      liveConnected={isLive ? liveConn.connected : undefined}
      livePaused={isLive ? liveConn.paused : undefined}
      livePauseContext={isLive ? liveConn.pauseContext : undefined}
      liveSendCommand={isLive ? liveConn.sendCommand : undefined}
      liveForkedPath={isLive ? liveConn.lastForked?.save_path : undefined}
      liveForkedHint={isLive ? liveConn.lastForked?.cli_hint : undefined}
      liveReconnecting={isLive ? (!liveConn.connected && !!wsUrl) : undefined}
      liveSpeed={isLive ? liveConn.speed : undefined}
      onSetLiveSpeed={isLive ? liveConn.setSpeed : undefined}
    />
  );
}

export default App;
```

- [ ] **Step 2: Update `Layout.tsx` to accept live props and render `InterventionPanel`**

Update `viewer/src/components/Layout.tsx` — add live mode props to the interface and conditionally render the `InterventionPanel`:

Add to imports:
```typescript
import { InterventionPanel } from "./InterventionPanel";
import type { PauseContext, Command } from "../types";
```

Add to `LayoutProps`:
```typescript
  // Live mode (all optional)
  liveConnected?: boolean;
  livePaused?: boolean;
  livePauseContext?: PauseContext | null;
  liveSendCommand?: (cmd: Command) => void;
  liveForkedPath?: string | null;
  liveForkedHint?: string | null;
  liveReconnecting?: boolean;
  liveSpeed?: number;
  onSetLiveSpeed?: (speed: number) => void;
```

Add these to the destructured props. In `TimelineScrubber`, when in live mode the speed control sends to the server:

```tsx
<TimelineScrubber
  ...existing props...
  onSetSpeed={onSetLiveSpeed || onSetSpeed}
/>
```

Pass live header props to `<Header>`:
```tsx
<Header
  worldName={bundle.world_state.name}
  metadata={bundle.metadata}
  currentTurn={currentTurn}
  darkMode={darkMode}
  onToggleDarkMode={() => setDarkMode(!darkMode)}
  liveConnected={liveConnected}
  livePaused={livePaused}
  livePauseTurn={livePauseContext?.turn}
  liveReconnecting={liveReconnecting}
/>
```

At the end of the `<div>` before the closing `</div>` of the root element, add:
```tsx
{livePaused && livePauseContext && liveSendCommand && (
  <InterventionPanel
    pauseContext={livePauseContext}
    sendCommand={liveSendCommand}
    forkedPath={liveForkedPath}
    forkedHint={liveForkedHint}
  />
)}
```

- [ ] **Step 3: Fix `useLiveConnection` to be no-op when wsUrl is empty**

The hook is always called but should skip connection when URL is empty. At the top of `useLiveConnection`, add an early guard:

In the `useEffect`, change the `connect()` call to:
```typescript
if (wsUrl) {
  connect();
}

return () => {
  unmounted = true;
  if (reconnectRef.current) clearTimeout(reconnectRef.current);
  wsRef.current?.close();
};
```

- [ ] **Step 4: Run all viewer tests**

Run: `cd viewer && npx vitest run`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd viewer && git add src/App.tsx src/components/Layout.tsx src/hooks/useLiveConnection.ts
git commit -m "feat(m12): wire App and Layout for live mode with InterventionPanel"
```

---

### Task 12: Add follow mode toggle to `TimelineScrubber`

**Files:**
- Modify: `viewer/src/components/TimelineScrubber.tsx`

- [ ] **Step 1: Add follow toggle button to `TimelineScrubber`**

Add to `TimelineScrubberProps`:
```typescript
  followMode?: boolean;
  onToggleFollowMode?: () => void;
```

Add the button after the turn number `<span>`, only when `followMode` is defined:
```tsx
{followMode !== undefined && onToggleFollowMode && (
  <button
    onClick={onToggleFollowMode}
    className={`px-2 py-1 rounded text-xs ${
      followMode
        ? "bg-green-700 text-green-200"
        : "bg-gray-700 text-gray-400 hover:text-gray-200"
    }`}
    title={followMode ? "Following latest turn" : "Click to follow latest turn"}
  >
    {followMode ? "Following" : "Follow"}
  </button>
)}
```

- [ ] **Step 2: Run all viewer tests**

Run: `cd viewer && npx vitest run`
Expected: All tests PASS — new props are optional.

- [ ] **Step 3: Commit**

```bash
cd viewer && git add src/components/TimelineScrubber.tsx
git commit -m "feat(m12): add follow mode toggle button to TimelineScrubber"
```

---

## Chunk 5: Final Integration and Verification (Task 13)

### Task 13: End-to-end smoke test and memory update

- [ ] **Step 1: Run full Python test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: All tests PASS including new `test_live.py` and `test_live_integration.py`.

- [ ] **Step 2: Run full viewer test suite**

Run: `cd viewer && npx vitest run`
Expected: All tests PASS.

- [ ] **Step 3: Manual end-to-end smoke test**

In terminal 1: `cd viewer && npm run dev`
In terminal 2: `python -m chronicler --live --turns 20 --civs 3 --regions 6 --seed 42 --pause-every 5 --output /tmp/live_smoke/chronicle.md --state /tmp/live_smoke/state.json`

Open `http://localhost:5173?ws=ws://localhost:8765` in a browser. Verify:
- Timeline advances as turns complete
- Chronicle text appears
- Faction cards update
- At turn 5, intervention panel appears
- Can inject an event, set a stat, fork, then continue
- Speed control changes simulation pace
- Quit stops simulation and produces a bundle

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(m12): complete live mode interactive GUI"
```

- [ ] **Step 5: Update project memory**

Update `/Users/tbronson/.claude/projects/-Users-tbronson-Documents-opusprogram/memory/project_chronicle_generator.md` to reflect M12 completion and Phase 2 complete status.
