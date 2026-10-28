"""A live session without sockets, for the live checkpoint tests.

``QuietServer`` is a ``LiveServer`` that serves no WebSocket; ``Viewer``
plays the client through the server's queues: it records each message as
the server's drain loop does (``_record_snapshot``, ``_record_status``),
routes what it sends as the message handler does, and keeps what a viewer
connecting after each turn is sent (``json.dumps(server._init_data)``).
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

from chronicler.live import LiveServer, run_live


class QuietServer(LiveServer):
    """A live server without the WebSocket server (no sockets, no event loop)."""

    def __init__(self, start: dict[str, Any] | None = None) -> None:
        super().__init__(port=0)
        self.authorized_path = f"/?token={self.token}"
        if start is not None:
            error = self._handle_start({"type": "start", **start})
            assert error is None, error

    def start(self) -> None:
        self._actual_port = 0

    def stop(self) -> None:
        pass


class Viewer(threading.Thread):
    """A scripted client. ``at_pause[turn]`` lists what it sends while paused
    at that turn (before ``continue``): ``("checkpoint",)``, ``("set", civ,
    stat, value)``, ``("inject", event, civ)``; ``on_turn[turn]`` what it sends
    when that turn's message arrives (while the run goes on). A resumed
    session's first pause (reason ``resumed``) gets ``at_resume``."""

    def __init__(self, server: LiveServer, *, at_pause: dict | None = None,
                 on_turn: dict | None = None, at_resume: list | None = None,
                 timeout: float = 120.0) -> None:
        super().__init__(daemon=True)
        self.server = server
        self.at_pause = at_pause or {}
        self.on_turn = on_turn or {}
        self.at_resume = at_resume or []
        self.timeout = timeout
        self.messages: list[dict] = []
        self.views: dict[int, str] = {}
        self.final_view: str | None = None
        self.saved: list[dict] = []
        self.pauses: list[tuple[int, str]] = []
        self.error: BaseException | None = None
        self._deadline = time.monotonic() + timeout
        self.done = threading.Event()
        self.ended = threading.Event()  # set when run_live has returned

    # --- what the drain loop does --------------------------------------------

    def _pump(self) -> list[dict]:
        """Record every queued message as the server's drain loop does."""
        got = []
        for q, record in ((self.server.snapshot_queue, self.server._record_snapshot),
                          (self.server.status_queue, self.server._record_status)):
            while True:
                try:
                    msg = q.get_nowait()
                except queue.Empty:
                    break
                record(msg)
                self.messages.append(msg)
                got.append(msg)
                if msg.get("type") == "turn":
                    self.views[msg["turn"]] = json.dumps(self.server._init_data)
                elif msg.get("type") == "checkpoint_saved":
                    self.saved.append(msg)
        return got

    # --- what the message handler does ---------------------------------------

    def send(self, msg: dict) -> dict | None:
        """Route ``msg`` as ``LiveServer``'s handler does; its direct reply."""
        server = self.server
        kind = msg.get("type")
        if kind == "speed":
            server.speed = float(msg["value"])
            return None
        if kind == "quit":
            server.quit_event.set()
            if server._paused:
                server.command_queue.put(msg)
            return None
        if kind == "checkpoint":
            return server.checkpoint_reply(msg, origin=None, path=self.server.authorized_path)
        if not server._paused:
            return {"type": "error", "message": "Commands only accepted while paused"}
        server.command_queue.put(msg)
        return None

    def _wait_for(self, kinds: set[str]) -> dict:
        while time.monotonic() < self._deadline:
            for msg in self._pump():
                if msg.get("type") in kinds:
                    return msg
            time.sleep(0.002)
        raise TimeoutError(f"no {sorted(kinds)} message")

    def _perform(self, actions: list) -> None:
        for action in actions:
            if action[0] == "checkpoint":
                reply = self.send({"type": "checkpoint"})
                assert reply is not None and reply["type"] == "checkpoint_requested", reply
                self._wait_for({"checkpoint_saved", "checkpoint_error"})
            elif action[0] == "set":
                _, civ, stat, value = action
                self.send({"type": "set", "civ": civ, "stat": stat, "value": value})
                self._wait_for({"ack", "error"})
            elif action[0] == "inject":
                _, event, civ = action
                self.send({"type": "inject", "event_type": event, "civ": civ})
                self._wait_for({"ack", "error"})
            elif action[0] == "quit":
                self.send({"type": "quit"})
            else:
                raise ValueError(action)

    def run(self) -> None:
        try:
            while time.monotonic() < self._deadline:
                ended = self.ended.is_set()
                for msg in self._pump():
                    kind = msg.get("type")
                    if kind == "turn" and msg["turn"] in self.on_turn:
                        for action in self.on_turn[msg["turn"]]:
                            assert action == ("checkpoint",), action
                            reply = self.send({"type": "checkpoint"})
                            assert reply is not None and reply["type"] == "checkpoint_requested", reply
                    elif kind == "paused":
                        turn, reason = msg["turn"], msg["reason"]
                        self.pauses.append((turn, reason))
                        if reason == "resumed":
                            self.views[turn] = json.dumps(self.server._init_data)
                            actions = self.at_resume
                        else:
                            actions = self.at_pause.get(turn, [])
                        self._perform(actions)
                        if ("quit",) in actions:
                            continue
                        self.send({"type": "continue"})
                    elif kind == "completed":
                        self.final_view = json.dumps(self.server._init_data)
                        return
                if ended:  # the session ended without completing (a quit)
                    return
                time.sleep(0.002)
            raise TimeoutError("the live session did not complete")
        except BaseException as exc:  # reported by session()
            self.error = exc
        finally:
            self.done.set()


def session(args: Any, *, start: dict | None = None, exact_resume: Any = None,
            **script: Any) -> tuple[Any, Viewer, QuietServer]:
    """Run ``run_live(args)`` against a scripted viewer; (result, viewer, server)."""
    server = QuietServer(start=start)
    server.speed = 1000.0  # 1 ms a turn
    viewer = Viewer(server, **script)
    viewer.start()
    try:
        result = run_live(args, exact_resume=exact_resume, server=server)
    finally:
        viewer.ended.set()
        viewer.done.wait(timeout=30)
    if viewer.error is not None:
        raise viewer.error
    # Anything queued after the last message the viewer waited for.
    viewer._pump()
    return result, viewer, server


def outputs(folder: Path, after: int = -1) -> dict[str, bytes]:
    """Every file but checkpoints and the per-turn sidecar files of turns up
    to ``after``; the bundle without ``generated_at``."""
    from chronicler.bundle_codec import load_bundle
    out = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt":
            continue
        stem = path.stem
        if "_turn_" in stem and int(stem.rsplit("_", 1)[1]) <= after:
            continue
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            content = json.dumps(data, sort_keys=True).encode()
        else:
            content = path.read_bytes()
        out[path.relative_to(folder).as_posix()] = content
    return out
