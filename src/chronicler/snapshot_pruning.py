"""Dead civilizations leave the per-turn history snapshots (bundle version 5).

Civilization records are never removed and secessions keep adding them, so a
version-4 snapshot carried every civilization that ever existed: its
``civ_stats`` row, its ``capitals`` entry and every pair it belongs to in
``relationships``, ``per_pair_accuracy`` and ``perception_errors``. In long
worlds most of those rows belonged to the dead.

A snapshot records a civilization when, in that snapshot,

* it holds a region (its ``civ_stats`` row has non-empty ``regions``), or
* an exile modifier names it (``original_civ_name``): a government in exile
  can be restored to its old land (``politics.check_restoration``), or
* it was recorded live in the previous snapshot, so the first snapshot in
  which a civilization is dead still carries its final row and a chart can end
  its line there, or
* the snapshot is the first of the history (every civilization is recorded).

Every other civilization is dead at that turn: its ``civ_stats`` row, its
``capitals`` entry and its pairs are left out. A civilization that is live
again (a restoration, or a later record reusing the name) is recorded again.
Records are matched by name, as the snapshot keys are. Region-keyed fields and
world records that mention a dead civilization (``region_control``,
``region_cultural_identity``, ``exile_modifiers``, vassal relations,
federations, movements, the per-system summaries) are not per-civ rows and are
kept as they are. ``world_state`` (the final state, used for resume) is
untouched.

The omitted ``civ_stats`` rows are not all copies of the final row: the
production phase still pays a dead civilization its frozen economy's income,
so its treasury keeps growing. The bundle's ``pruned_civ_stats`` records every
difference from the final row as compact runs, and :func:`restore_history`
rebuilds the version-4 ``civ_stats`` exactly. Readers that measure over every
civilization (the validation oracles, batch analytics, report scripts) read
restored histories; the viewer reads the pruned history directly. The pair
tables of dead civilizations are not recorded anywhere and cannot be restored.

``pruned_civ_stats`` maps a civilization's name to its omitted segments, in
history order::

    {"from_turn": 34, "snapshots": 467, "changes": {"treasury": [[467, 214, 20]]}}

The civilization is missing from ``snapshots`` consecutive snapshots starting
with the one whose ``turn`` is ``from_turn``. In each its row equals the
civilization's last recorded row, except the fields in ``changes``. A field's
runs ``[count, first, step]`` cover the segment in order: the next ``count``
snapshots hold ``first``, ``first + step``, ``first + 2 * step``... (integers),
or ``first`` throughout when ``step`` is null.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PRUNED_BUNDLE_VERSION = 5
PRUNED_CIV_STATS_KEY = "pruned_civ_stats"
# Snapshot fields keyed by civilization name.
CIV_KEYED_FIELDS = ("capitals",)
# Snapshot fields keyed by civilization name, then by the other civilization.
PAIR_FIELDS = ("relationships", "per_pair_accuracy", "perception_errors")


def _row_live(row: Any) -> bool:
    """A civ row holds land (legacy rows without ``regions`` use ``alive``)."""
    if not isinstance(row, Mapping):
        return True
    if "regions" in row:
        return bool(row["regions"])
    return bool(row.get("alive", True))


def live_civ_names(snapshot: Mapping[str, Any]) -> set[str]:
    """Civilizations of a serialized snapshot that hold land or can be restored."""
    civ_stats = snapshot.get("civ_stats")
    live = {name for name, row in civ_stats.items() if _row_live(row)} if isinstance(civ_stats, Mapping) else set()
    for modifier in snapshot.get("exile_modifiers") or ():
        name = modifier.get("original_civ_name") if isinstance(modifier, Mapping) else None
        if isinstance(name, str):
            live.add(name)
    return live


def _same(a: Any, b: Any) -> bool:
    """JSON equality that also keeps types (1 is not 1.0 or True) and key order."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return list(a) == list(b) and all(_same(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _is_int(value: Any) -> bool:
    return type(value) is int


def prune_snapshot(snapshot: Mapping[str, Any], pruned: set[str]) -> dict[str, Any]:
    """A copy of a serialized snapshot without the rows of the ``pruned`` civs."""
    out = dict(snapshot)
    if not pruned:
        return out
    civ_stats = snapshot.get("civ_stats")
    if isinstance(civ_stats, Mapping):
        out["civ_stats"] = {name: row for name, row in civ_stats.items() if name not in pruned}
    for field in CIV_KEYED_FIELDS:
        value = snapshot.get(field)
        if isinstance(value, Mapping):
            out[field] = {name: item for name, item in value.items() if name not in pruned}
    for field in PAIR_FIELDS:
        value = snapshot.get(field)
        if isinstance(value, Mapping):
            out[field] = {
                name: ({other: item for other, item in inner.items() if other not in pruned}
                       if isinstance(inner, Mapping) else inner)
                for name, inner in value.items() if name not in pruned
            }
    return out


class _Segment:
    """The omitted rows of one civ between two recorded rows, as change runs."""

    __slots__ = ("turn", "base", "count", "runs")

    def __init__(self, turn: Any, base: Mapping[str, Any]):
        self.turn = turn
        self.base = base
        self.count = 0
        self.runs: dict[str, list[list[Any]]] = {}

    def add(self, row: Mapping[str, Any]) -> None:
        for field, value in row.items():
            runs = self.runs.get(field)
            if runs is None:
                if _same(value, self.base[field]):
                    continue
                runs = self.runs[field] = [[self.count, self.base[field], None]] if self.count else []
                runs.append([1, value, None])
                continue
            last = runs[-1]
            count, first, step = last
            if step is None:
                if _same(value, first):
                    last[0] += 1
                    continue
                if count == 1 and _is_int(first) and _is_int(value):
                    last[0], last[2] = 2, value - first
                    continue
            elif _is_int(value) and value == first + step * count:
                last[0] += 1
                continue
            runs.append([1, value, None])
        self.count += 1

    def record(self) -> dict[str, Any]:
        return {"from_turn": self.turn, "snapshots": self.count, "changes": self.runs}


class SnapshotPruner:
    """Prune serialized snapshots one at a time, in history order.

    With ``record_tails`` (the default) the omitted ``civ_stats`` rows are
    kept as change runs; :meth:`finish` returns them as ``pruned_civ_stats``.
    A live stream that never restores passes ``record_tails=False``.
    """

    def __init__(self, *, record_tails: bool = True):
        self._first = True
        self._prev_live: set[str] = set()
        self._last_recorded: dict[str, Mapping[str, Any]] = {}
        self._open: dict[str, _Segment] = {}
        self._tails: dict[str, list[dict[str, Any]]] = {}
        self._record_tails = record_tails

    def prune(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        civ_stats = snapshot.get("civ_stats")
        if not isinstance(civ_stats, Mapping):
            return dict(snapshot)
        live = live_civ_names(snapshot)
        pruned: set[str] = set()
        if not self._first:
            for name, row in civ_stats.items():
                if name in live or name in self._prev_live:
                    continue
                base = self._last_recorded.get(name)
                # Only same-shaped rows are encoded as changes; a row that
                # gains or loses a field (or has no recorded row) stays.
                if base is None or not isinstance(row, Mapping) or list(row) != list(base):
                    continue
                pruned.add(name)
        for name, row in civ_stats.items():
            if name not in pruned:
                self._close(name)
                self._last_recorded[name] = row
            elif self._record_tails:
                segment = self._open.get(name)
                if segment is None:
                    segment = self._open[name] = _Segment(snapshot.get("turn"), self._last_recorded[name])
                segment.add(row)
        self._prev_live = live
        self._first = False
        return prune_snapshot(snapshot, pruned)

    def _close(self, name: str) -> None:
        segment = self._open.pop(name, None)
        if segment is not None:
            self._tails.setdefault(name, []).append(segment.record())

    def finish(self) -> dict[str, list[dict[str, Any]]]:
        """Close every open segment and return ``pruned_civ_stats``."""
        for name in list(self._open):
            self._close(name)
        return self._tails


def prune_history(snapshots: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prune a serialized history; returns the snapshots and ``pruned_civ_stats``."""
    pruner = SnapshotPruner()
    history = [pruner.prune(snapshot) for snapshot in snapshots]
    return history, pruner.finish()


class _Cursor:
    """Replays one segment's rows."""

    __slots__ = ("base", "left", "fields")

    def __init__(self, segment: Mapping[str, Any], base: Mapping[str, Any]):
        self.base = base
        self.left = segment["snapshots"]
        # field -> [runs, run index, position in run]
        self.fields = {field: [runs, 0, 0] for field, runs in segment.get("changes", {}).items()}

    def next(self) -> dict[str, Any]:
        row = dict(self.base)
        for field, state in self.fields.items():
            runs, index, position = state
            count, first, step = runs[index]
            row[field] = first if step is None else first + step * position
            position += 1
            if position == count:
                index, position = index + 1, 0
            state[1], state[2] = index, position
        self.left -= 1
        return row


def restore_history(history: list[Mapping[str, Any]], pruned_civ_stats: Mapping[str, Any] | None) -> list[Any]:
    """Rebuild the version-4 ``civ_stats`` of a pruned history.

    Returns new snapshot dicts (shallow copies; restored rows share unchanged
    nested values with the final row, so treat them as read-only). Without
    ``pruned_civ_stats`` (a version-4 history) the history is returned as is.
    """
    if not pruned_civ_stats:
        return list(history)
    pending = {name: list(segments) for name, segments in pruned_civ_stats.items()}
    order: list[str] = []
    seen: set[str] = set()
    last: dict[str, Mapping[str, Any]] = {}
    active: dict[str, _Cursor] = {}
    restored: list[Any] = []
    for snapshot in history:
        civ_stats = snapshot.get("civ_stats") if isinstance(snapshot, Mapping) else None
        if not isinstance(civ_stats, Mapping):
            restored.append(snapshot)
            continue
        for name in civ_stats:
            if name not in seen:
                seen.add(name)
                order.append(name)
        turn = snapshot.get("turn")
        rows: dict[str, Any] = {}
        filled = False
        for name in order:
            if name in civ_stats:
                if name in active:
                    raise ValueError(f"pruned_civ_stats: {name!r} is recorded inside its omitted segment")
                rows[name] = last[name] = civ_stats[name]
                continue
            cursor = active.get(name)
            if cursor is None:
                segments = pending.get(name)
                if not segments or segments[0].get("from_turn") != turn:
                    continue
                if name not in last:
                    raise ValueError(f"pruned_civ_stats: {name!r} has no recorded row before turn {turn}")
                cursor = active[name] = _Cursor(segments.pop(0), last[name])
            rows[name] = cursor.next()
            filled = True
            if cursor.left == 0:
                del active[name]
        restored.append({**snapshot, "civ_stats": rows} if filled else snapshot)
    if active or any(pending.values()):
        unmatched = sorted(set(active) | {name for name, segments in pending.items() if segments})
        raise ValueError(f"pruned_civ_stats does not match the history: {', '.join(unmatched)}")
    return restored


def restore_bundle(bundle: Any) -> Any:
    """A bundle whose history carries every civ row, as version 4 wrote it.

    Version-4 bundles (and anything that is not a bundle) are returned as is.
    Otherwise a shallow copy is returned with ``history`` restored and
    ``pruned_civ_stats`` removed; metadata keeps the bundle version.
    """
    if not isinstance(bundle, dict) or PRUNED_CIV_STATS_KEY not in bundle:
        return bundle
    history = bundle.get("history")
    out = {key: value for key, value in bundle.items() if key != PRUNED_CIV_STATS_KEY}
    if isinstance(history, list):
        out["history"] = restore_history(history, bundle.get(PRUNED_CIV_STATS_KEY))
    return out


def prune_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Convert a version-4 bundle to version 5 (pruned history plus runs).

    A bundle that already carries ``pruned_civ_stats`` is returned as is. The
    result has the same key order as :func:`chronicler.bundle.assemble_bundle`
    writes, so converting a version-4 bundle gives the bytes a version-5 run
    of the same world writes (apart from ``generated_at``).
    """
    if PRUNED_CIV_STATS_KEY in bundle:
        return bundle
    history, pruned = prune_history(bundle.get("history", []))
    out: dict[str, Any] = {}
    for key, value in bundle.items():
        if key == "history":
            out["history"] = history
            out[PRUNED_CIV_STATS_KEY] = pruned
        else:
            out[key] = value
    if "history" not in out:
        out[PRUNED_CIV_STATS_KEY] = pruned
    metadata = out.get("metadata")
    if isinstance(metadata, dict):
        out["metadata"] = {**metadata, "bundle_version": PRUNED_BUNDLE_VERSION}
    return out
