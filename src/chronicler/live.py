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
        # Batch state
        self._batch_thread: threading.Thread | None = None
        self._batch_cancel_event = threading.Event()

    @property
    def speed(self) -> float:
        with self._speed_lock:
            return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        with self._speed_lock:
            self._speed = max(0.1, value)

    @staticmethod
    def _is_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _validate_batch_config(self, config: dict) -> str | None:
        for field in ("seed_start", "seed_count", "turns"):
            if field not in config:
                continue
            value = config.get(field)
            if not self._is_int(value) or value <= 0:
                return f"batch_start config '{field}' must be a positive integer"

        if "simulate_only" in config and not isinstance(config.get("simulate_only"), bool):
            return "batch_start config 'simulate_only' must be a boolean"

        if "parallel" in config:
            value = config.get("parallel")
            if not isinstance(value, bool):
                if not self._is_int(value) or value <= 0:
                    return "batch_start config 'parallel' must be a boolean or positive integer"

        if "workers" in config:
            value = config.get("workers")
            if value is not None and (not self._is_int(value) or value <= 0):
                return "batch_start config 'workers' must be a positive integer or null"

        if "tuning_overrides" in config:
            value = config.get("tuning_overrides")
            if value is not None:
                if not isinstance(value, dict):
                    return "batch_start config 'tuning_overrides' must be an object or null"
                for key, override in value.items():
                    if not isinstance(key, str):
                        return "batch_start config 'tuning_overrides' keys must be strings"
                    if not self._is_number(override):
                        return "batch_start config 'tuning_overrides' values must be numbers"

        return None

    async def _send_error(self, websocket, message: str) -> None:
        await websocket.send(json.dumps({
            "type": "error",
            "message": message,
        }))

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
        for field in ("turns", "civs", "regions"):
            value = msg.get(field)
            if not self._is_int(value) or value <= 0:
                return {"type": "error", "message": f"Start field '{field}' must be a positive integer"}
        seed = msg.get("seed")
        if seed is not None and not self._is_int(seed):
            return {"type": "error", "message": "Start field 'seed' must be an integer or null"}
        for field in ("scenario", "sim_model", "narrative_model"):
            value = msg.get(field)
            if value is not None and not isinstance(value, str):
                return {"type": "error", "message": f"Start field '{field}' must be a string or null"}
        resume_state = msg.get("resume_state")
        if resume_state is not None and not isinstance(resume_state, dict):
            return {"type": "error", "message": "Start field 'resume_state' must be an object or null"}
        self._start_params = msg
        self._server_state = "running"
        self.start_event.set()
        return None

    def _handle_batch_start(self, msg: dict) -> dict | None:
        """Handle a batch_start command. Runs batch in a background thread."""
        if self._batch_thread is not None and self._batch_thread.is_alive():
            return {"type": "batch_error", "message": "Batch already running"}

        config = msg.get("config", {})
        if not isinstance(config, dict):
            return {"type": "batch_error", "message": "batch_start config must be an object"}
        config_error = self._validate_batch_config(config)
        if config_error is not None:
            return {"type": "batch_error", "message": config_error}
        self._batch_cancel_event.clear()

        def _batch_worker():
            import argparse as _argparse
            from datetime import datetime
            from chronicler.batch import run_batch
            from chronicler.analytics import generate_report

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            batch_output = f"output/batch_gui_{timestamp}"

            args = _argparse.Namespace(
                seed=config.get("seed_start", 1),
                batch=config.get("seed_count", 200),
                turns=config.get("turns", 500),
                simulate_only=config.get("simulate_only", True),
                parallel=config.get("parallel", True),
                output=f"{batch_output}/chronicle.md",
                state=f"{batch_output}/state.json",
                tuning=None,
                civs=4,
                regions=8,
                resume=None,
                reflection_interval=10,
                local_url="http://localhost:1234/v1",
                sim_model=None,
                narrative_model=None,
                llm_actions=False,
                scenario=None,
                fork=None,
                interactive=False,
                pause_every=None,
                seed_range=None,
            )

            try:
                workers = config.get("workers")
                if workers:
                    args.parallel = workers

                tuning_dict = config.get("tuning_overrides") or None

                def on_progress(completed: int, total: int, current_seed: int):
                    self.snapshot_queue.put({
                        "type": "batch_progress",
                        "completed": completed,
                        "total": total,
                        "current_seed": current_seed,
                    })

                batch_dir = run_batch(
                    args,
                    progress_cb=on_progress,
                    cancel_event=self._batch_cancel_event,
                    tuning_overrides_dict=tuning_dict,
                )

                if self._batch_cancel_event.is_set():
                    self.snapshot_queue.put({
                        "type": "batch_cancelled",
                    })
                    return

                # Auto-run analytics and save report to disk
                try:
                    report = generate_report(batch_dir)
                    report_path = batch_dir / "batch_report.json"
                    report_path.write_text(json.dumps(report, indent=2))
                    self.snapshot_queue.put({
                        "type": "batch_complete",
                        "report": report,
                    })
                except Exception as exc:
                    self.snapshot_queue.put({
                        "type": "batch_error",
                        "message": f"Batch completed but analytics failed: {exc}",
                    })
            except Exception as exc:
                self.snapshot_queue.put({
                    "type": "batch_error",
                    "message": str(exc),
                })

        self._batch_thread = threading.Thread(target=_batch_worker, daemon=True)
        self._batch_thread.start()
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
                        await self._send_error(websocket, "Invalid JSON")
                        continue

                    if not isinstance(msg, dict):
                        await self._send_error(websocket, "Live messages must be JSON objects")
                        continue

                    msg_type = msg.get("type")
                    if not isinstance(msg_type, str) or not msg_type:
                        await self._send_error(websocket, "Live messages must include a string 'type'")
                        continue

                    # speed and quit are always accepted
                    if msg_type == "speed":
                        value = msg.get("value", 1.0)
                        if not self._is_number(value):
                            await self._send_error(websocket, "speed.value must be a number")
                            continue
                        self.speed = float(value)
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

                    if msg_type == "batch_start":
                        err = self._handle_batch_start(msg)
                        if err is not None:
                            await websocket.send(json.dumps(err))
                        continue

                    if msg_type == "batch_cancel":
                        self._batch_cancel_event.set()
                        continue

                    if msg_type == "batch_load_report":
                        report_path = msg.get("path", "")
                        if not isinstance(report_path, str):
                            await self._send_error(websocket, "batch_load_report.path must be a string")
                            continue
                        try:
                            resolved = Path(report_path).resolve()
                            allowed = Path("output").resolve()
                            if not resolved.is_relative_to(allowed):
                                raise ValueError(f"Path must be within output/: {report_path}")
                            report = json.loads(resolved.read_text(encoding="utf-8"))
                            await websocket.send(json.dumps({
                                "type": "batch_report_loaded",
                                "report": report,
                            }))
                        except Exception as exc:
                            await websocket.send(json.dumps({
                                "type": "batch_error",
                                "message": f"Failed to load report: {exc}",
                            }))
                        continue

                    # H-25: Load a bundle file and populate _init_data for narration
                    if msg_type == "batch_load_bundle":
                        bundle_path = msg.get("path", "")
                        if not isinstance(bundle_path, str):
                            await self._send_error(websocket, "batch_load_bundle.path must be a string")
                            continue
                        try:
                            resolved = Path(bundle_path).resolve()
                            allowed = Path("output").resolve()
                            if not resolved.is_relative_to(allowed):
                                raise ValueError(f"Path must be within output/: {bundle_path}")
                            bundle = json.loads(resolved.read_text(encoding="utf-8"))
                            # H-25: Populate _init_data so narrate_range works
                            self._init_data = {
                                "type": "init",
                                "world_state": bundle.get("world_state", {}),
                                "history": bundle.get("history", []),
                                "events_timeline": bundle.get("events_timeline", []),
                                "named_events": bundle.get("named_events", []),
                                "chronicle_entries": bundle.get("chronicle_entries", {}),
                                "metadata": bundle.get("metadata", {}),
                                "current_turn": bundle.get("metadata", {}).get("turns", 0),
                            }
                            await websocket.send(json.dumps({
                                "type": "bundle_loaded",
                                "bundle": bundle,
                                "path": str(resolved),
                                "turns": len(bundle.get("history", [])),
                            }))
                        except Exception as exc:
                            await websocket.send(json.dumps({
                                "type": "batch_error",
                                "message": f"Failed to load bundle: {exc}",
                            }))
                        continue

                    if msg_type == "narrate_range":
                        # H-25: Guard against missing _init_data (no sim run yet)
                        if self._init_data is None:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": "No simulation data available for narration. "
                                           "Start a simulation first.",
                            }))
                            continue

                        start_turn = msg.get("start_turn")
                        end_turn = msg.get("end_turn")
                        if not self._is_int(start_turn) or not self._is_int(end_turn):
                            await self._send_error(websocket, "narrate_range.start_turn and end_turn must be integers")
                            continue
                        if start_turn > end_turn:
                            await self._send_error(websocket, "narrate_range start_turn must be <= end_turn")
                            continue
                        if not self._init_data:
                            await self._send_error(websocket, "narrate_range requires initialized history")
                            continue
                        history_turns = [
                            snap.get("turn")
                            for snap in self._init_data.get("history", [])
                            if isinstance(snap, dict) and self._is_int(snap.get("turn"))
                        ]
                        if not history_turns:
                            await self._send_error(websocket, "narrate_range requires history turns")
                            continue
                        min_turn = min(history_turns)
                        max_turn = max(history_turns)
                        if start_turn < min_turn or end_turn > max_turn:
                            await self._send_error(
                                websocket,
                                f"narrate_range must stay within available turns {min_turn}-{max_turn}",
                            )
                            continue
                        await websocket.send(json.dumps({
                            "type": "narration_started",
                            "start_turn": start_turn,
                            "end_turn": end_turn,
                        }))

                        from chronicler.models import Event, NamedEvent, TurnSnapshot
                        from chronicler.curator import curate
                        from chronicler.narrative import NarrativeEngine
                        from chronicler.llm import create_clients

                        all_events = [Event.model_validate(e) for e in self._init_data.get("events_timeline", [])]
                        all_named = [NamedEvent.model_validate(e) for e in self._init_data.get("named_events", [])]
                        all_history = [TurnSnapshot.model_validate(s) for s in self._init_data.get("history", [])]
                        seed = self._init_data.get("metadata", {}).get("seed", 0)

                        range_events = [e for e in all_events if start_turn <= e.turn <= end_turn]

                        # M40: Collect named character names
                        named_chars = set()
                        for civ_data in self._init_data.get("world_state", {}).get("civilizations", []):
                            for gp in civ_data.get("great_persons", []):
                                if gp.get("active") and gp.get("agent_id") is not None:
                                    named_chars.add(gp.get("name", ""))

                        moments, _ = curate(
                            range_events, all_named, all_history, budget=1, seed=seed,
                            named_characters=named_chars if named_chars else None,
                        )
                        if moments:
                            _, narrative_client = create_clients()
                            engine = NarrativeEngine(sim_client=narrative_client, narrative_client=narrative_client)
                            entries = engine.narrate_batch(moments, all_history, [])
                            if entries:
                                await websocket.send(json.dumps({
                                    "type": "narration_complete",
                                    "entry": entries[0].model_dump(),
                                }))
                        continue

                    # Other commands only accepted while paused
                    if not self._paused:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Commands only accepted while paused",
                        }))
                        continue

                    self.command_queue.put(msg)

            except Exception as exc:
                # H-26: Log disconnect explicitly instead of silently swallowing
                import logging
                logger = logging.getLogger("chronicler.live")
                logger.info("Client disconnected: %s", exc)
                try:
                    await self._send_error(websocket, f"Unhandled live message error: {exc}")
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
                                    # H-26: Log dropped messages on disconnect
                                    import logging
                                    logging.getLogger("chronicler.live").warning(
                                        "Dropped snapshot (type=%s, turn=%s) — client disconnected",
                                        snapshot.get("type"), snapshot.get("turn"),
                                    )
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
                                    # H-26: Log dropped status on disconnect
                                    import logging
                                    logging.getLogger("chronicler.live").warning(
                                        "Dropped status (type=%s) — client disconnected",
                                        status.get("type"),
                                    )
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

                if stat in CORE_STATS and not (1 <= value <= 100):
                    status_queue.put({
                        "type": "error",
                        "message": f"Value for {stat} must be 1-100, got {value}",
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
