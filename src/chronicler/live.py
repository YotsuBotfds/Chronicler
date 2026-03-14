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
    """WebSocket server that bridges the simulation thread and a browser viewer.

    Communication happens via three thread-safe queues:
    - snapshot_queue: simulation -> server (turn snapshots for the viewer)
    - command_queue: server -> simulation (user commands from the viewer)
    - status_queue: simulation -> server (paused/ack/error messages)
    """

    def __init__(self, port: int = 8765) -> None:
        self.port = port
        self.snapshot_queue: queue.Queue[dict] = queue.Queue()
        self.command_queue: queue.Queue[dict] = queue.Queue()
        self.status_queue: queue.Queue[dict] = queue.Queue()
        self.quit_event = threading.Event()
        self._speed: float = 1.0
        self._speed_lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._actual_port: int | None = None
        self._paused: bool = False
        self._init_data: dict | None = None
        self._last_paused_msg: dict | None = None
        self.start_event = threading.Event()
        self._start_params: dict | None = None
        self._server_state: str = "lobby"
        self._lobby_init: dict | None = None

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
        self.thread = threading.Thread(target=self._run_loop, args=(ready,), daemon=True)
        self.thread.start()
        ready.wait(timeout=5)

    def stop(self) -> None:
        """Signal the server to stop."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)

    def _handle_start(self, msg: dict) -> dict | None:
        """Handle a start command. Returns an error dict if rejected, None on success."""
        if self._server_state != "lobby":
            return {"type": "error", "message": "Simulation already running"}
        self._start_params = msg
        self._server_state = "running"
        self.start_event.set()
        return None

    def _run_loop(self, ready: threading.Event) -> None:
        """Entry point for the server thread — creates and runs the event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve(ready))
        finally:
            self._loop.close()

    async def _serve(self, ready: threading.Event) -> None:
        """Run the async WebSocket server."""
        import websockets.asyncio.server as ws_server

        client_ws = None
        client_lock = asyncio.Lock()

        async def handler(websocket):
            nonlocal client_ws
            async with client_lock:
                if client_ws is not None:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Another client is already connected",
                    }))
                    await websocket.close()
                    return
                client_ws = websocket

            try:
                # Send init data based on server state
                if self._server_state == "lobby" and self._lobby_init is not None:
                    await websocket.send(json.dumps(self._lobby_init))
                elif self._server_state == "running" and self._init_data is not None:
                    await websocket.send(json.dumps(self._init_data))
                elif self._server_state == "running" and self._init_data is None:
                    # World generation in progress — send minimal ack
                    await websocket.send(json.dumps({"type": "init", "state": "starting"}))
                # Send last paused msg if paused
                if self._paused and self._last_paused_msg is not None:
                    await websocket.send(json.dumps(self._last_paused_msg))

                async for raw_msg in websocket:
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Invalid JSON",
                        }))
                        continue

                    msg_type = msg.get("type")

                    # speed and quit are always accepted
                    if msg_type == "speed":
                        self.speed = float(msg.get("value", 1.0))
                        continue

                    if msg_type == "quit":
                        self.quit_event.set()
                        if self._paused:
                            self.command_queue.put(msg)
                        continue

                    if msg_type == "start":
                        err = self._handle_start(msg)
                        if err is not None:
                            await websocket.send(json.dumps(err))
                        continue

                    # Other commands only accepted while paused
                    if not self._paused:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Commands only accepted while paused",
                        }))
                        continue

                    self.command_queue.put(msg)

            except Exception:
                pass
            finally:
                async with client_lock:
                    client_ws = None

        async def drain_queues():
            """Background task: drain snapshot_queue and status_queue, send to client."""
            while not self._stop_event.is_set():
                # Drain snapshot queue
                try:
                    while True:
                        snapshot = self.snapshot_queue.get_nowait()
                        # Only store init messages as reconnect data;
                        # turn messages update the existing init data below
                        if snapshot.get("type") == "init":
                            self._init_data = snapshot
                        elif snapshot.get("type") == "turn" and self._init_data is not None:
                            # Append turn data to init for reconnect
                            self._init_data["history"].append({
                                k: v for k, v in snapshot.items() if k != "type"
                            })
                            turn_str = str(snapshot["turn"])
                            self._init_data["chronicle_entries"][turn_str] = snapshot.get("chronicle_text", "")
                            self._init_data["events_timeline"].extend(snapshot.get("events", []))
                            self._init_data["named_events"].extend(snapshot.get("named_events", []))
                            self._init_data["current_turn"] = snapshot["turn"]
                        async with client_lock:
                            if client_ws is not None:
                                try:
                                    await client_ws.send(json.dumps(snapshot))
                                except Exception:
                                    pass
                except queue.Empty:
                    pass

                # Drain status queue
                try:
                    while True:
                        status = self.status_queue.get_nowait()
                        if status.get("type") == "paused":
                            self._paused = True
                            self._last_paused_msg = status
                        elif status.get("type") == "ack" and not status.get("still_paused", True):
                            self._paused = False
                            self._last_paused_msg = None
                        async with client_lock:
                            if client_ws is not None:
                                try:
                                    await client_ws.send(json.dumps(status))
                                except Exception:
                                    pass
                except queue.Empty:
                    pass

                await asyncio.sleep(0.05)

        server = await ws_server.serve(
            handler,
            host="localhost",
            port=self.port,
            max_size=10 * 1024 * 1024,
            ping_interval=20,
        )

        # Record actual port (useful when port=0)
        for sock in server.sockets:
            addr = sock.getsockname()
            self._actual_port = addr[1]
            break

        ready.set()

        drain_task = asyncio.create_task(drain_queues())

        try:
            await self._stop_event.wait()
        finally:
            drain_task.cancel()
            try:
                await drain_task
            except asyncio.CancelledError:
                pass
            server.close()
            await server.wait_closed()


def make_live_pause(
    command_queue: queue.Queue,
    status_queue: queue.Queue,
    output_dir: Path | None = None,
):
    """Create a pause callback for live mode that communicates via queues.

    Returns a closure ``live_pause(world, memories, pending_injections) -> bool``
    that blocks on the command_queue until a ``continue`` or ``quit`` command
    is received.
    """

    def live_pause(
        world: WorldState,
        memories: dict[str, MemoryStream],
        pending_injections: list,
    ) -> bool:
        civ_names = [c.name for c in world.civilizations]
        injectable_events = get_injectable_event_types()

        # Put paused status on the queue
        status_queue.put({
            "type": "paused",
            "turn": world.turn,
            "reason": "pause_interval",
            "valid_commands": ["continue", "quit", "inject", "set", "fork"],
            "injectable_events": injectable_events,
            "settable_stats": sorted(VALID_STATS),
            "civs": civ_names,
        })

        # Block waiting for commands
        while True:
            cmd = command_queue.get()  # blocks
            cmd_type = cmd.get("type")

            if cmd_type == "continue":
                status_queue.put({
                    "type": "ack",
                    "command": "continue",
                    "still_paused": False,
                })
                return True

            elif cmd_type == "quit":
                return False

            elif cmd_type == "inject":
                event_type = cmd.get("event_type", "")
                civ = cmd.get("civ", "")

                # Validate civ
                if civ not in civ_names:
                    status_queue.put({
                        "type": "error",
                        "message": f"Unknown civilization: '{civ}'. Valid civs: {civ_names}",
                    })
                    continue

                # Validate event type
                if event_type not in injectable_events:
                    status_queue.put({
                        "type": "error",
                        "message": f"Unknown event type: '{event_type}'. Valid types: {injectable_events}",
                    })
                    continue

                pending_injections.append((event_type, civ))
                status_queue.put({
                    "type": "ack",
                    "command": "inject",
                    "still_paused": True,
                })

            elif cmd_type == "set":
                civ_name = cmd.get("civ", "")
                stat = cmd.get("stat", "")
                value = cmd.get("value")

                # Validate civ
                civ_obj = next((c for c in world.civilizations if c.name == civ_name), None)
                if civ_obj is None:
                    status_queue.put({
                        "type": "error",
                        "message": f"Unknown civilization: '{civ_name}'. Valid civs: {civ_names}",
                    })
                    continue

                # Validate stat
                if stat not in VALID_STATS:
                    status_queue.put({
                        "type": "error",
                        "message": f"Invalid stat: '{stat}'. Valid stats: {sorted(VALID_STATS)}",
                    })
                    continue

                # Validate value range
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    status_queue.put({
                        "type": "error",
                        "message": f"Value must be an integer, got '{value}'",
                    })
                    continue

                if stat in CORE_STATS and not (1 <= value <= 10):
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

                # Apply the change
                setattr(civ_obj, stat, value)
                status_queue.put({
                    "type": "ack",
                    "command": "set",
                    "still_paused": True,
                    "civ": civ_name,
                    "stat": stat,
                    "value": value,
                })

            elif cmd_type == "fork":
                fork_output = output_dir or Path("output")
                fork_dir = fork_output / f"fork_save_t{world.turn}"
                fork_dir.mkdir(parents=True, exist_ok=True)

                # Save world state
                world.save(fork_dir / "state.json")

                # Save memories
                for mem_civ_name, stream in memories.items():
                    stream.save(fork_dir / f"memories_{sanitize_civ_name(mem_civ_name)}.json")

                status_queue.put({
                    "type": "forked",
                    "save_path": str(fork_dir),
                    "cli_hint": f"Resume from fork: --load {fork_dir / 'state.json'}",
                })

            else:
                status_queue.put({
                    "type": "error",
                    "message": f"Unknown command type: '{cmd_type}'",
                })

    return live_pause


def _get_available_models(args: Any) -> list[str]:
    """Return list of available model names for the lobby dropdowns."""
    models: list[str] = []
    sim_model = getattr(args, "sim_model", None)
    narrative_model = getattr(args, "narrative_model", None)
    if sim_model:
        models.append(sim_model)
    if narrative_model and narrative_model not in models:
        models.append(narrative_model)

    # Try LM Studio /v1/models with 500ms timeout
    local_url = getattr(args, "local_url", None)
    if local_url:
        try:
            import urllib.request
            req = urllib.request.Request(f"{local_url.rstrip('/')}/models")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read())
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if model_id and model_id not in models:
                        models.append(model_id)
        except Exception:
            pass

    # Always include a fallback if nothing found
    if not models:
        models.append("")  # empty string = LM Studio uses loaded model

    return models


def build_lobby_init(args: Any, scenario_dir: Path | None = None) -> dict:
    """Build the lobby init message by scanning scenario YAML files.

    Reads scenario data directly from YAML — no world generation.
    """
    import yaml

    if scenario_dir is None:
        scenario_dir = Path("scenarios")

    scenarios: list[dict] = []
    if scenario_dir.exists():
        for f in sorted(scenario_dir.glob("*.yaml")):
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
            scenarios.append({
                "file": f.name,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "world_name": data.get("world_name", f.stem),
                "civs": [
                    {"name": c["name"], "values": c.get("values", [])}
                    for c in data.get("civilizations", []) or []
                ],
                "regions": [
                    {
                        "name": r["name"],
                        "terrain": r.get("terrain", ""),
                        "x": r.get("x"),
                        "y": r.get("y"),
                    }
                    for r in data.get("regions", []) or []
                ],
            })

    return {
        "type": "init",
        "state": "lobby",
        "scenarios": scenarios,
        "models": _get_available_models(args),
        "defaults": {
            "turns": 50,
            "civs": 4,
            "regions": 8,
            "seed": None,
        },
    }


def resolve_start_seed(seed: int | None) -> int:
    """Resolve seed from start command. None means server-generated random."""
    import random
    if seed is None:
        return random.randint(0, 2**31 - 1)
    return seed


def run_live(
    args: Any,
) -> Any:
    """Run simulation in live mode with WebSocket server.

    Phase 1: Start WebSocket server in lobby state, wait for client to send start.
    Phase 2: Generate world from client params, run simulation.
    """
    import random
    from chronicler.main import execute_run
    from chronicler.models import TurnSnapshot, Event, NamedEvent
    from chronicler.llm import create_clients

    port = getattr(args, "live_port", 8765) or 8765

    # --- Phase 1: Lobby ---
    server = LiveServer(port=port)
    server._lobby_init = build_lobby_init(args)
    server.start()
    actual_port = server._actual_port or port
    print(f"Lobby ready on ws://localhost:{actual_port}")
    print(f"Open viewer: http://localhost:5173?ws=ws://localhost:{actual_port}")
    print("Waiting for client to launch simulation...")

    # Block until client sends start (interruptible via Ctrl+C)
    while not server.start_event.wait(timeout=1.0):
        pass

    params = server._start_params
    if params is None:
        raise RuntimeError("start_event set but no _start_params")

    # --- Phase 2: Simulation ---

    # Resolve world and scenario from client params
    scenario_config = None
    if params.get("resume_state"):
        world = WorldState.model_validate(params["resume_state"])
    else:
        seed = resolve_start_seed(params.get("seed"))

        from chronicler.world_gen import generate_world
        world = generate_world(
            seed=seed,
            num_regions=params.get("regions", 8),
            num_civs=params.get("civs", 4),
        )
        if params.get("scenario"):
            from chronicler.scenario import load_scenario, apply_scenario
            scenario_config = load_scenario(Path("scenarios") / params["scenario"])
            apply_scenario(world, scenario_config)

    # Construct LLM clients from client-selected models
    sim_model = params.get("sim_model") or getattr(args, "sim_model", None)
    narrative_model = params.get("narrative_model") or getattr(args, "narrative_model", None)
    sim_client, narrative_client = create_clients(
        local_url=getattr(args, "local_url", "http://localhost:1234/v1"),
        sim_model=sim_model,
        narrative_model=narrative_model,
    )

    pause_every = getattr(args, "pause_every", None) or getattr(args, "reflection_interval", 10) or 10
    total_turns = params.get("turns") or args.turns or 50
    output_dir = Path(args.output).parent

    init_sent = [False]
    world_ref = [world]

    def _serialize_snapshot(snapshot, chronicle_text, events, named_events):
        """Serialize turn data to a dict for the WebSocket protocol."""
        snap_dict = snapshot.model_dump(mode="json")
        snap_dict["type"] = "turn"
        snap_dict["chronicle_text"] = chronicle_text
        snap_dict["events"] = [e.model_dump(mode="json") for e in events]
        snap_dict["named_events"] = [ne.model_dump(mode="json") for ne in named_events]
        return snap_dict

    def on_turn_cb(
        snapshot: TurnSnapshot,
        chronicle_text: str,
        events: list[Event],
        named_events: list[NamedEvent],
    ) -> None:
        if not init_sent[0]:
            init_sent[0] = True
            w = world_ref[0]
            init_msg = {
                "type": "init",
                "state": "running",
                "total_turns": total_turns,
                "pause_every": pause_every,
                "current_turn": 0,
                "world_state": w.model_dump(mode="json"),
                "history": [],
                "chronicle_entries": {},
                "events_timeline": [],
                "named_events": [],
                "era_reflections": {},
                "metadata": {
                    "seed": w.seed,
                    "total_turns": total_turns,
                    "generated_at": "",
                    "sim_model": getattr(sim_client, "model", "unknown") or "unknown",
                    "narrative_model": getattr(narrative_client, "model", "unknown") or "unknown",
                    "scenario_name": getattr(w, "scenario_name", None),
                    "interestingness_score": None,
                },
                "speed": server.speed,
            }
            server.snapshot_queue.put(init_msg)

        snap_dict = _serialize_snapshot(snapshot, chronicle_text, events, named_events)
        server.snapshot_queue.put(snap_dict)

        spd = server.speed
        if spd > 0:
            time.sleep(1.0 / spd)

    pending_injections: list[tuple[str, str]] = []
    pause_fn = make_live_pause(
        server.command_queue,
        server.status_queue,
        output_dir=output_dir,
    )

    # Override args with client params for execute_run
    args.turns = total_turns
    args.seed = world.seed

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

    server.status_queue.put({
        "type": "completed",
        "total_turns": result.total_turns,
        "bundle_path": str(output_dir / "chronicle_bundle.json"),
    })

    time.sleep(0.5)
    server.stop()

    return result
