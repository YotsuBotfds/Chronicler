"""Exact checkpoints of a live session (docs/integration/checkpoint-continuation.md).

A live run (``--live``) writes the same exact checkpoints as a single run
(``--checkpoint-every``, ``--checkpoint``), and an authenticated viewer can
ask for one at a turn boundary with the ``checkpoint`` message. The server
names the file: ``<output dir>/live_checkpoints/turn_<turn>.ckpt``, one per
turn, never a path the client sends.

Two pieces run on the simulation thread:

* :class:`LiveView` keeps what a newly connecting viewer is sent (the
  ``init`` message as first sent and every ``turn`` message since, with the
  snapshot pruner that shapes them). Every checkpoint of a live run carries
  it (``RunState.live``), so a resumed session presents the earlier history
  as the uninterrupted one does.
* :class:`LiveCheckpoints` is ``execute_run``'s turn boundary: it writes the
  requested checkpoints after the turn (and while paused) and records the
  viewer's interventions (``inject``, ``set``) in the run configuration.
  A pause that changed the run makes ``execute_run`` write that turn's
  scheduled checkpoints again, so a checkpoint always holds the state the
  next turn starts from.

The intervention record and that rewrite are :class:`PauseInterventions`,
which an interactive (terminal) session uses as its turn boundary too
(``chronicler.interactive``).

Pure Python: no sockets (the server in ``chronicler.live`` feeds the
request queue).
"""
from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any, Callable

from chronicler.snapshot_pruning import SnapshotPruner

#: Client-requested checkpoints, under the run's output directory.
LIVE_CHECKPOINT_DIR = "live_checkpoints"
LIVE_CHECKPOINT_NAME = "turn_{turn:04d}.ckpt"
LIVE_VIEW_VERSION = 1


class LiveCheckpointError(ValueError):
    """A client-requested checkpoint that cannot be written."""


def apply_turn_message(init_data: dict[str, Any], message: dict[str, Any]) -> None:
    """Append a live ``turn`` message to the reconnect ``init`` data."""
    from chronicler.transport import snapshot_from_turn_message
    init_data["history"].append(snapshot_from_turn_message(message))
    init_data["chronicle_entries"][str(message["turn"])] = message.get("chronicle_text", "")
    init_data["events_timeline"].extend(message.get("events", []))
    init_data["named_events"].extend(message.get("named_events", []))
    init_data["current_turn"] = message["turn"]


class LiveView:
    """The live session's presentation state, kept for checkpoints.

    ``init`` is the ``init`` message as first sent (JSON text: the server
    keeps extending its own copy); ``turns`` the ``turn`` messages since, the
    same objects the server sends (never changed after they are queued).
    The server's reconnect data is ``init`` with every turn applied
    (:meth:`init_data`)."""

    def __init__(self) -> None:
        self.init: str | None = None
        self.turns: list[dict[str, Any]] = []
        self.pruner = SnapshotPruner(record_tails=False)

    def record_init(self, message: dict[str, Any]) -> None:
        self.init = json.dumps(message)

    def record_turn(self, message: dict[str, Any]) -> None:
        self.turns.append(message)

    def record(self, *, speed: float, pause_every: int) -> dict[str, Any]:
        """The checkpoint's ``live`` entry (pickled with the run)."""
        return {"version": LIVE_VIEW_VERSION, "init": self.init, "turns": self.turns,
                "pruner": self.pruner, "speed": speed, "pause_every": pause_every}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "LiveView":
        if not isinstance(record, dict) or record.get("version") != LIVE_VIEW_VERSION:
            raise LiveCheckpointError(f"unsupported live view in the checkpoint: {record!r:.80}")
        view = cls()
        view.init = record["init"]
        view.turns = list(record["turns"])
        view.pruner = record["pruner"]
        return view

    def init_data(self, *, total_turns: int | None = None,
                  pause_every: int | None = None) -> dict[str, Any] | None:
        """The ``init`` message a viewer connecting now is sent."""
        if self.init is None:
            return None
        data = json.loads(self.init)
        for message in self.turns:
            apply_turn_message(data, message)
        # A resume that extends the run (--turns) shows the new length.
        if total_turns is not None and data.get("total_turns") != total_turns:
            data["total_turns"] = total_turns
            if isinstance(data.get("metadata"), dict):
                data["metadata"]["total_turns"] = total_turns
        if pause_every is not None:
            data["pause_every"] = pause_every
        return data


def turn_message(snapshot: Any, chronicle_text: str, events: list, named_events: list,
                 pruner: SnapshotPruner) -> dict[str, Any]:
    """The live ``turn`` message of a completed turn (dead civs pruned)."""
    message = pruner.prune(snapshot.model_dump(mode="json"))
    message["type"] = "turn"
    message["chronicle_text"] = chronicle_text
    message["events"] = [e.model_dump(mode="json") for e in events]
    message["named_events"] = [ne.model_dump(mode="json") for ne in named_events]
    return message


def rebuilt_view(state: Any, init_message: dict[str, Any]) -> LiveView:
    """A view for a checkpoint no live session wrote (a single or batch run).

    The simulation resumes exactly either way; this view is rebuilt from the
    run's history: each turn's snapshot, chronicle text and the events and
    named events dated in it, with ``init_message`` (the checkpoint's world)
    as the first message."""
    world = state.world
    view = LiveView()
    view.record_init(init_message)
    texts = {entry.turn: entry.narrative for entry in state.chronicle_entries}
    events: dict[int, list] = {}
    for event in world.events_timeline:
        events.setdefault(event.turn, []).append(event)
    named: dict[int, list] = {}
    for event in world.named_events:
        named.setdefault(event.turn, []).append(event)
    for snapshot in state.history:
        view.record_turn(turn_message(snapshot, texts.get(snapshot.turn, ""),
                                      events.get(snapshot.turn - 1, []),
                                      named.get(snapshot.turn - 1, []), view.pruner))
    return view


class PauseInterventions:
    """``execute_run``'s turn boundary for a run whose pauses take commands.

    The pause commands that change the run (``inject``, ``set``) are
    recorded in ``run_config["interventions"]`` (``{"turn", "command",
    ...}``, carried by every later checkpoint), and ``turn_end`` tells
    ``execute_run`` after the pause that the run changed, so it writes that
    turn's scheduled checkpoints again: they hold what the next turn starts
    from. Interactive sessions use it as it is, live sessions through
    :class:`LiveCheckpoints`. Runs on the simulation thread."""

    def __init__(self) -> None:
        self._save: Callable[[str], Path] | None = None
        self._run_config: dict | None = None
        self._changed = False

    def bind(self, save: Callable[[str], Path] | None, run_config: dict) -> None:
        """``save(template)`` writes an exact checkpoint of the run as it
        stands; interventions are recorded in ``run_config``."""
        self._save = save
        self._run_config = run_config

    def live_record(self) -> dict[str, Any] | None:
        """The checkpoint's ``live`` entry: None outside a live session."""
        return None

    def note_intervention(self, world: Any, command: dict[str, Any]) -> None:
        """An ``inject`` or ``set`` at a pause: recorded in the run
        configuration (and so in every later checkpoint); this boundary's
        scheduled checkpoints are written again."""
        self._changed = True
        if self._run_config is not None:
            self._run_config["interventions"] = [
                *self._run_config.get("interventions", []), {"turn": world.turn, **command}]

    def turn_end(self, world: Any) -> bool:
        """At a turn boundary, after its pause: True when an intervention
        changed the run since the last boundary."""
        changed, self._changed = self._changed, False
        return changed


class LiveCheckpoints(PauseInterventions):
    """Client-requested checkpoints and interventions at turn boundaries.

    ``request`` is called by the server thread; everything else runs on the
    simulation thread. ``execute_run`` binds the writer (``bind``) and calls
    ``turn_end`` after each turn's pause."""

    def __init__(self, output_dir: Path, status_queue: "queue.Queue[dict]", view: LiveView,
                 speed: Callable[[], float], pause_every: int) -> None:
        super().__init__()
        self.output_dir = Path(output_dir)
        self.status_queue = status_queue
        self.view = view
        self._speed = speed
        self.pause_every = pause_every
        self._requests: "queue.Queue[None]" = queue.Queue()
        self._lock = threading.Lock()
        self._closed = False

    # --- server thread -------------------------------------------------------

    def request(self) -> bool:
        """Queue a checkpoint for the next turn boundary; False once the run ended."""
        with self._lock:
            if self._closed:
                return False
            self._requests.put(None)
            return True

    @property
    def closed(self) -> bool:
        return self._closed

    # --- simulation thread ---------------------------------------------------

    def live_record(self) -> dict[str, Any]:
        return self.view.record(speed=self._speed(), pause_every=self.pause_every)

    def path_for(self, turn: int) -> Path:
        """``<output dir>/live_checkpoints/turn_<turn>.ckpt``, refusing a
        directory or file that leads outside the output directory."""
        if isinstance(turn, bool) or not isinstance(turn, int) or turn < 0:
            raise LiveCheckpointError(f"invalid checkpoint turn {turn!r}")
        root = self.output_dir.resolve()
        directory = self.output_dir / LIVE_CHECKPOINT_DIR
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise LiveCheckpointError(f"{directory} leads outside the run's output directory")
        path = directory / LIVE_CHECKPOINT_NAME.format(turn=turn)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise LiveCheckpointError(f"{path} is not a regular file")
        return path

    def save_now(self, world: Any) -> dict[str, Any]:
        """Write a checkpoint of this turn boundary; the reply goes to the client."""
        try:
            if self._save is None:
                raise LiveCheckpointError("the run is not ready to checkpoint")
            path = self.path_for(world.turn)
            # The writer formats {turn} templates: keep the path's own braces.
            written = self._save(str(path).replace("{", "{{").replace("}", "}}"))
            reply = {
                "type": "checkpoint_saved",
                "turn": world.turn,
                "path": str(written),
                "bytes": written.stat().st_size,
                "exact": (self._run_config or {}).get("resume_info") is None,
                "resume_hint": f"--live --resume {written}",
            }
        except Exception as exc:  # reported to the client; the run continues
            reply = {"type": "checkpoint_error", "turn": getattr(world, "turn", None),
                     "message": f"Checkpoint not written: {exc}"}
        self.status_queue.put(reply)
        return reply

    def service(self, world: Any) -> int:
        """Write one checkpoint for the requests queued so far (one reply each)."""
        count = 0
        while True:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                break
            count += 1
        if count:
            reply = self.save_now(world)
            for _ in range(count - 1):
                self.status_queue.put(dict(reply))
        return count

    def turn_end(self, world: Any) -> bool:
        """At a turn boundary: write requested checkpoints; True when an
        intervention changed the run since the last boundary."""
        self.service(world)
        return super().turn_end(world)

    def close(self, message: str) -> None:
        """The run ended: refuse queued and later requests."""
        with self._lock:
            self._closed = True
        while True:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                return
            self.status_queue.put({"type": "checkpoint_error", "message": message})
