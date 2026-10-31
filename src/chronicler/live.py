"""Live server: WebSocket bridge between the simulation and the TUI viewer."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Any, Callable

from chronicler.artifact_io import atomic_write_json


def _write_batch_report(batch_dir: Path, report: dict) -> None:
    """Write the live Batch Lab report atomically."""
    atomic_write_json(Path(batch_dir) / "batch_report.json", report)


class LiveServer:
    """WebSocket server for live simulation viewing.

    Runs in a daemon thread; communicates with the simulation via queues.
    """

    def __init__(self, port: int = 0, origin: str | None = None):
        self.port = port
        self.origin = origin
        self.thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server = None
        self._clients: set = set()
        self._command_queue: queue.Queue = queue.Queue()
        self._status_queue: queue.Queue = queue.Queue()
        self._init_data: dict | None = None
        self._start_params: dict | None = None
        self._server_state: str = "lobby"
        self._lobby_init: dict | None = None
        self._session_client_config: dict | None = None
        self._client_defaults: dict = {}
        self.start_event = threading.Event()

    def start(self) -> None:
        """Start the server in a daemon thread."""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Stop the server."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self.thread is not None:
            self.thread.join(timeout=2)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _handle_start(self, msg: dict) -> dict | None:
        """Handle a 'start' command from the lobby."""
        if self._server_state != "lobby":
            return {"type": "error", "message": "Simulation already running"}
        self._session_client_config = {
            "sim_model": msg.get("sim_model"),
            "narrative_model": msg.get("narrative_model"),
            "narrator": msg.get("narrator", "local"),
        }
        self._start_params = msg
        self._server_state = "running"
        self.start_event.set()
        return None

    def _resolve_client_config(self, bundle_metadata: dict) -> dict:
        """Resolve client config, preferring bundle metadata over session defaults."""
        config = dict(self._client_defaults)
        if self._session_client_config:
            for key in ("sim_model", "narrative_model", "narrator"):
                value = self._session_client_config.get(key)
                if value is not None:
                    config[key] = value
        for key in ("sim_model", "narrative_model"):
            value = bundle_metadata.get(key)
            if value is not None:
                config[key] = value
        narrator_mode = bundle_metadata.get("narrator_mode")
        if narrator_mode is not None:
            config["narrator"] = narrator_mode
        return config


def resolve_start_seed(seed: int | None) -> int:
    """Return the seed, or generate a random one."""
    if seed is not None:
        return seed
    import random
    return random.randrange(2**31)


def _get_available_models(args: Any) -> list[str]:
    """Return available model names, deduplicated."""
    models: list[str] = []
    for attr in ("sim_model", "narrative_model"):
        value = getattr(args, attr, None)
        if value is not None and value not in models:
            models.append(value)
    if not models:
        # Try LM Studio
        try:
            import urllib.request
            url = getattr(args, "local_url", "http://localhost:1234/v1")
            req = urllib.request.Request(f"{url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
            for model in data.get("data", []):
                name = model.get("id")
                if name and name not in models:
                    models.append(name)
        except Exception:
            pass
    if not models:
        models.append("local-model")
    return models


def build_lobby_init(args: Any, scenario_dir: Path | None = None) -> dict:
    """Build the init payload sent to a newly connected client in lobby state."""
    scenarios: list[dict] = []
    if scenario_dir is not None and scenario_dir.is_dir():
        import yaml
        for path in sorted(scenario_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            scenarios.append({
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "civs": [
                    {"name": c.get("name", ""), "values": c.get("values", [])}
                    for c in data.get("civilizations", [])
                ],
                "regions": [
                    {"name": r.get("name", ""), "terrain": r.get("terrain", "")}
                    for r in data.get("regions", [])
                ],
                "file": path.name,
            })

    defaults = {
        "turns": 50,
        "seed": getattr(args, "seed", None),
        "civs": getattr(args, "civs", 4),
        "regions": getattr(args, "regions", 8),
    }
    return {
        "type": "init",
        "state": "lobby",
        "scenarios": scenarios,
        "models": _get_available_models(args),
        "defaults": defaults,
    }


def make_live_pause(
    command_queue: queue.Queue,
    status_queue: queue.Queue,
    output_dir: Path | None = None,
) -> Callable:
    """Create a live_pause callable for use as the pause hook in run_turn loops.

    The returned function blocks until a 'continue' or 'quit' command arrives.
    'inject' commands are appended to pending_injections; 'set' commands modify
    world state directly; 'fork' saves state. Returns True to continue, False to quit.
    """
    def live_pause(world: Any, memories: dict, pending_injections: list) -> bool:
        status_queue.put({"type": "paused", "turn": world.turn})
        while True:
            command = command_queue.get()
            cmd_type = command.get("type")

            if cmd_type == "continue":
                status_queue.put({"type": "ack", "command": "continue", "still_paused": False})
                return True
            elif cmd_type == "quit":
                status_queue.put({"type": "ack", "command": "quit", "still_paused": False})
                return False
            elif cmd_type == "inject":
                event_type = command.get("event_type")
                civ_name = command.get("civ")
                civ_names = {c.name for c in world.civilizations}
                if civ_name not in civ_names:
                    status_queue.put({
                        "type": "error",
                        "message": f"Unknown civilization: {civ_name}",
                    })
                    continue
                pending_injections.append((event_type, civ_name))
                status_queue.put({"type": "ack", "command": "inject", "still_paused": True})
            elif cmd_type == "set":
                civ_name = command.get("civ")
                stat = command.get("stat")
                value = command.get("value")
                civ = next((c for c in world.civilizations if c.name == civ_name), None)
                if civ is None:
                    status_queue.put({"type": "error", "message": f"Unknown civilization: {civ_name}"})
                    continue
                valid_stats = {"military", "economy", "culture", "stability", "treasury", "population"}
                if stat not in valid_stats:
                    status_queue.put({"type": "error", "message": f"Unknown stat: {stat}"})
                    continue
                setattr(civ, stat, value)
                status_queue.put({
                    "type": "ack", "command": "set", "still_paused": True,
                    "civ": civ_name, "stat": stat, "value": value,
                })
            elif cmd_type == "fork":
                if output_dir is None:
                    status_queue.put({"type": "error", "message": "Fork requires an output directory"})
                    continue
                fork_dir = Path(output_dir) / f"fork_turn_{world.turn}"
                fork_dir.mkdir(parents=True, exist_ok=True)
                state_path = fork_dir / "state.json"
                world.save(state_path)
                status_queue.put({
                    "type": "forked",
                    "save_path": str(fork_dir),
                    "cli_hint": f"chronicler --fork {state_path} --seed SEED --turns TURNS",
                })
            else:
                status_queue.put({"type": "error", "message": f"Unknown command: {cmd_type}"})

    return live_pause
