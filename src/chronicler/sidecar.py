"""Sidecar Writer/Reader for M53 validation diagnostics.

Writes diagnostic data alongside simulation bundles:
- Graph snapshots (agent relationship graphs + memory signatures)
- Needs snapshots (per-agent need levels from FFI)
- Agent aggregates (per-civ summary statistics)
- Community summaries (region-level cluster summaries)

Per-turn JSON snapshots remain for debugging, but the writer also emits
canonical consolidated artifacts for the validator:
- validation_relationships.arrow
- validation_memory_signatures.arrow
- validation_needs.arrow
- validation_summary.json
- validation_community_summary.json
- validation_resource_ledger.arrow (production ledger, 2026-10: one row per
  region and occupied resource slot per turn; ``chronicler.production_ledger``)
- validation_reserve_ledger.arrow (public granaries, ``--grain-reserves``
  only: one row per granary that held or moved grain per turn;
  ``chronicler.grain_reserves``)

Directory layout::

    <base_dir>/
      validation_summary/
        graph_turn_010.json
        needs_turn_010.json
        aggregate_turn_010.json
        community_turn_100.json
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

try:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False


def _turn_str(turn: int) -> str:
    """Zero-pad turn number to 3 digits for consistent filename sorting."""
    return f"{turn:03d}"


def _rows_to_columns(rows: list[dict[str, Any]]) -> tuple:
    """``rows`` as runs of consecutive rows sharing one key tuple:
    ``([keys, columns, count], ...)``; exact inverse in :func:`_columns_to_rows`."""
    runs: list = []
    keys = None
    columns: list[list[Any]] = []
    for row in rows:
        row_keys = tuple(row)
        if row_keys != keys or not runs:
            keys = row_keys
            columns = [[] for _ in keys]
            runs.append([keys, columns, 0])
        for column, value in zip(columns, row.values()):
            column.append(value)
        runs[-1][2] += 1
    return tuple(tuple(run) for run in runs)


def _columns_to_rows(runs: tuple) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for keys, columns, count in runs:
        if keys:
            rows.extend(dict(zip(keys, values)) for values in zip(*columns))
        else:
            rows.extend({} for _ in range(count))
    return rows


class SidecarWriter:
    """Writes validation sidecar files for a single simulation run."""

    def __init__(self, base_dir: pathlib.Path, *, artifact_budget=None) -> None:
        self._base_dir = base_dir
        self._dir = base_dir / "validation_summary"
        if artifact_budget is None:
            self._dir.mkdir(parents=True, exist_ok=True)
        else:
            artifact_budget.require_healthy()
            artifact_budget.ensure_directory(self._dir)
            self._artifact_budget = artifact_budget
        self._relationship_rows: list[dict[str, Any]] = []
        self._memory_rows: list[dict[str, Any]] = []
        self._needs_rows: list[dict[str, Any]] = []
        self._aggregate_by_turn: dict[str, dict[str, dict[str, Any]]] = {}
        self._community_by_turn: dict[str, dict[str, dict[str, Any]]] = {}
        self._resource_ledger: dict[str, list[Any]] | None = None
        # Each economy snapshot file's text by file name: the summary is
        # built from this run's snapshots, not from whatever the directory
        # holds (a resumed run's directory lacks the earlier turns' files).
        self._economy_texts: dict[str, str] = {}

    # Exact checkpoints (chronicler.run_checkpoint): row lists are pickled as
    # columns (one key tuple per list instead of one dict per row) and
    # rebuilt as the same dicts in the same key order.
    _ROW_LISTS = ("_relationship_rows", "_memory_rows", "_needs_rows")

    def __getstate__(self) -> dict[str, Any]:
        if "_artifact_budget" in self.__dict__:
            raise ValueError("Budgeted sidecar checkpoint support is unqualified")
        state = dict(self.__dict__)
        for name in self._ROW_LISTS:
            state[name] = _rows_to_columns(state[name])
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        state = dict(state)
        for name in self._ROW_LISTS:
            state[name] = _columns_to_rows(state[name])
        self.__dict__.update(state)

    # ------------------------------------------------------------------
    # Graph snapshot
    # ------------------------------------------------------------------

    def write_graph_snapshot(
        self,
        turn: int,
        edges: list[tuple[int, int, int, int]],
        memory_signatures: dict[int, list[tuple[int, int, int]]],
    ) -> None:
        """Write agent relationship graph + memory signatures for a turn.

        Args:
            turn: Simulation turn number.
            edges: List of (agent_a, agent_b, bond_type, strength) tuples.
            memory_signatures: Mapping from agent_id to list of
                (memory_type, weight, valence) tuples.
        """
        payload = {
            "turn": turn,
            "edges": [list(e) for e in edges],
            # JSON keys must be strings; convert int keys to str
            "memory_signatures": {
                str(k): [list(m) for m in v]
                for k, v in memory_signatures.items()
            },
        }
        path = self._dir / f"graph_turn_{_turn_str(turn)}.json"
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(path, json.dumps(payload, separators=(",", ":")))
        else:
            path.write_text(json.dumps(payload, separators=(",", ":")))
        for agent_id, target_id, bond_type, sentiment in edges:
            self._relationship_rows.append({
                "turn": turn,
                "agent_id": agent_id,
                "target_id": target_id,
                "bond_type": bond_type,
                "sentiment": sentiment,
            })
        for agent_id, signatures in memory_signatures.items():
            for event_type, memory_turn, valence_sign in signatures:
                self._memory_rows.append({
                    "turn": turn,
                    "agent_id": agent_id,
                    "event_type": event_type,
                    "memory_turn": memory_turn,
                    "valence_sign": valence_sign,
                })

    # ------------------------------------------------------------------
    # Needs snapshot
    # ------------------------------------------------------------------

    def write_needs_snapshot(
        self,
        turn: int,
        needs_batch: Any,
    ) -> None:
        """Write per-agent need levels for a turn.

        Accepts either a dict mapping need-name → list[float] (direct Python
        data) or a PyArrow RecordBatch (serialized to column-oriented JSON).

        Args:
            turn: Simulation turn number.
            needs_batch: Column data as dict or PyArrow RecordBatch.
        """
        if hasattr(needs_batch, "to_pydict"):
            # PyArrow RecordBatch or Table
            data = needs_batch.to_pydict()
        elif hasattr(needs_batch, "column_names"):
            # arro3 RecordBatch — convert column-by-column
            data = {name: needs_batch.column(name).to_pylist() for name in needs_batch.column_names}
        elif isinstance(needs_batch, dict):
            data = needs_batch
        else:
            raise TypeError(
                f"needs_batch must be a dict or RecordBatch, got {type(needs_batch)}"
            )

        payload = {"turn": turn, "columns": data}
        path = self._dir / f"needs_turn_{_turn_str(turn)}.json"
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(path, json.dumps(payload, separators=(",", ":")))
        else:
            path.write_text(json.dumps(payload, separators=(",", ":")))
        row_count = len(next(iter(data.values()), []))
        for idx in range(row_count):
            row = {"turn": turn}
            for name, values in data.items():
                row[name] = values[idx]
            self._needs_rows.append(row)

    # ------------------------------------------------------------------
    # Agent aggregate
    # ------------------------------------------------------------------

    def write_agent_aggregate(
        self,
        turn: int,
        aggregates: dict[str, dict[str, Any]],
    ) -> None:
        """Write per-civ agent aggregate statistics for a turn.

        Args:
            turn: Simulation turn number.
            aggregates: Mapping from civ key (e.g. "civ_0") to a dict of
                aggregate statistics (satisfaction_mean, occupation_counts, …).
        """
        payload = {"turn": turn, "aggregates": aggregates}
        path = self._dir / f"aggregate_turn_{_turn_str(turn)}.json"
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(path, json.dumps(payload, separators=(",", ":")))
        else:
            path.write_text(json.dumps(payload, separators=(",", ":")))
        self._aggregate_by_turn[str(turn)] = aggregates

    # ------------------------------------------------------------------
    # Community summary
    # ------------------------------------------------------------------

    def write_community_summary(
        self,
        turn: int,
        summary: dict[str, dict[str, Any]],
    ) -> None:
        """Write condensed community summary for gate runs.

        Args:
            turn: Simulation turn number.
            summary: Mapping from region key (e.g. "region_0") to a dict
                containing cluster_count, sizes, dominant_memory_type, etc.
        """
        payload = {"turn": turn, "summary": summary}
        path = self._dir / f"community_turn_{_turn_str(turn)}.json"
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(path, json.dumps(payload, separators=(",", ":")))
        else:
            path.write_text(json.dumps(payload, separators=(",", ":")))
        self._community_by_turn[str(turn)] = summary

    # ------------------------------------------------------------------
    # Economy snapshot (M58b)
    # ------------------------------------------------------------------

    def write_economy_snapshot(self, turn: int, data: dict[str, Any]) -> None:
        """Write per-turn economy convergence data for M58b gate."""
        path = self._dir / f"economy_turn_{_turn_str(turn)}.json"
        text = json.dumps(data, indent=2)
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(path, text)
        else:
            with open(path, "w") as f:
                f.write(text)
        self._economy_texts[path.name] = text

    def _economy_rows(self) -> list[dict[str, Any]]:
        """Collect this run's economy snapshots (as written, in file-name
        order) for the consolidated summary."""
        return [json.loads(self._economy_texts[name]) for name in sorted(self._economy_texts)]

    # ------------------------------------------------------------------
    # Production ledger (2026-10)
    # ------------------------------------------------------------------

    def add_resource_ledger_rows(self, rows: dict[str, list[Any]]) -> None:
        """Append one turn's ledger rows (column lists of
        ``production_ledger.LEDGER_COLUMNS``); written on :meth:`close`."""
        if self._resource_ledger is None:
            self._resource_ledger = {name: [] for name in rows}
        for name, values in rows.items():
            self._resource_ledger[name].extend(values)

    def _write_resource_ledger(self) -> None:
        if not HAS_ARROW or self._resource_ledger is None:
            return
        from chronicler.production_ledger import LEDGER_FILENAME, write_ledger
        if "_artifact_budget" in self.__dict__:
            write_ledger(self._base_dir / LEDGER_FILENAME, self._resource_ledger,
                         artifact_budget=self._artifact_budget)
        else:
            write_ledger(self._base_dir / LEDGER_FILENAME, self._resource_ledger)

    # Public granaries (--grain-reserves): the granary ledger. The attribute
    # exists only once a row arrives, so a run without granaries pickles and
    # writes exactly what it did before.
    def add_reserve_ledger_rows(self, rows: dict[str, list[Any]]) -> None:
        """Append one turn's granary ledger rows (column lists of
        ``grain_reserves.RESERVE_LEDGER_COLUMNS``); written on :meth:`close`."""
        ledger = getattr(self, "_reserve_ledger", None)
        if ledger is None:
            ledger = self._reserve_ledger = {name: [] for name in rows}
        for name, values in rows.items():
            ledger[name].extend(values)

    def _write_reserve_ledger(self) -> None:
        ledger = getattr(self, "_reserve_ledger", None)
        if not HAS_ARROW or ledger is None:
            return
        from chronicler.grain_reserves import RESERVE_LEDGER_FILENAME, write_reserve_ledger
        if "_artifact_budget" in self.__dict__:
            write_reserve_ledger(self._base_dir / RESERVE_LEDGER_FILENAME, ledger,
                                 artifact_budget=self._artifact_budget)
        else:
            write_reserve_ledger(self._base_dir / RESERVE_LEDGER_FILENAME, ledger)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Flush and finalise.  All writes are synchronous, so this is a no-op
        kept for API symmetry and future buffering support."""
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.require_healthy()
        self._write_canonical_artifacts()
        self._write_economy_summary()
        self._write_resource_ledger()
        self._write_reserve_ledger()

    def _write_canonical_artifacts(self) -> None:
        self._write_arrow_file(
            self._base_dir / "validation_relationships.arrow",
            self._relationship_rows,
            {
                "turn": pa.uint32() if HAS_ARROW else None,
                "agent_id": pa.uint32() if HAS_ARROW else None,
                "target_id": pa.uint32() if HAS_ARROW else None,
                "bond_type": pa.uint8() if HAS_ARROW else None,
                "sentiment": pa.int16() if HAS_ARROW else None,
            },
        )
        self._write_arrow_file(
            self._base_dir / "validation_memory_signatures.arrow",
            self._memory_rows,
            {
                "turn": pa.uint32() if HAS_ARROW else None,
                "agent_id": pa.uint32() if HAS_ARROW else None,
                "event_type": pa.uint8() if HAS_ARROW else None,
                "memory_turn": pa.uint16() if HAS_ARROW else None,
                "valence_sign": pa.int8() if HAS_ARROW else None,
            },
        )
        self._write_arrow_file(
            self._base_dir / "validation_needs.arrow",
            self._needs_rows,
            None,
        )
        validation_summary = {
            "turns": sorted(int(turn) for turn in self._aggregate_by_turn.keys()),
            "agent_aggregates_by_turn": self._aggregate_by_turn,
        }
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(
                self._base_dir / "validation_summary.json",
                json.dumps(validation_summary, separators=(",", ":")),
            )
        else:
            (self._base_dir / "validation_summary.json").write_text(
                json.dumps(validation_summary, separators=(",", ":"))
            )
        validation_community_summary = {
            "turns": sorted(int(turn) for turn in self._community_by_turn.keys()),
            "community_summary_by_turn": self._community_by_turn,
        }
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(
                self._base_dir / "validation_community_summary.json",
                json.dumps(validation_community_summary, separators=(",", ":")),
            )
        else:
            (self._base_dir / "validation_community_summary.json").write_text(
                json.dumps(validation_community_summary, separators=(",", ":"))
            )

    def _write_arrow_file(
        self,
        path: pathlib.Path,
        rows: list[dict[str, Any]],
        schema_map: dict[str, Any] | None,
    ) -> None:
        if not HAS_ARROW:
            return
        if rows:
            columns = {name: [row.get(name) for row in rows] for name in rows[0].keys()}
            arrays = {}
            for name, values in columns.items():
                pa_type = schema_map.get(name) if schema_map else None
                arrays[name] = pa.array(values, type=pa_type) if pa_type else pa.array(values)
            batch = pa.record_batch(arrays)
        else:
            arrays = []
            names = []
            for name, pa_type in (schema_map or {}).items():
                if pa_type is None:
                    continue
                names.append(name)
                arrays.append(pa.array([], type=pa_type))
            batch = pa.record_batch(arrays, names=names)
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.require_healthy()
            with pa.BufferOutputStream() as handle:
                writer = ipc.new_file(handle, batch.schema)
                writer.write_batch(batch)
                writer.close()
                content = handle.getvalue().to_pybytes()
            self._artifact_budget.write_bytes(path, content)
        else:
            with pa.OSFile(str(path), "wb") as handle:
                writer = ipc.new_file(handle, batch.schema)
                writer.write_batch(batch)
                writer.close()

    def _write_economy_summary(self) -> None:
        """Consolidate economy snapshots into a single JSON summary file."""
        rows = self._economy_rows()
        if not rows:
            return
        summary = {
            "turns": [r.get("turn", 0) for r in rows],
            "economy_snapshots": rows,
        }
        if "_artifact_budget" in self.__dict__:
            self._artifact_budget.write_text(
                self._base_dir / "validation_economy_summary.json",
                json.dumps(summary, separators=(",", ":")),
            )
        else:
            (self._base_dir / "validation_economy_summary.json").write_text(
                json.dumps(summary, separators=(",", ":"))
            )


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class SidecarReader:
    """Reads validation sidecar files written by :class:`SidecarWriter`."""

    def __init__(self, base_dir: pathlib.Path) -> None:
        self._dir = base_dir / "validation_summary"

    # ------------------------------------------------------------------
    # Graph snapshot
    # ------------------------------------------------------------------

    def read_graph_snapshot(
        self, turn: int
    ) -> dict[str, Any]:
        """Read graph snapshot for *turn*.

        Returns a dict with:
            ``edges`` — list of (agent_a, agent_b, bond_type, strength) tuples
            ``memory_signatures`` — dict mapping int agent_id → list of
                (memory_type, weight, valence) tuples
        """
        path = self._dir / f"graph_turn_{_turn_str(turn)}.json"
        raw = json.loads(path.read_text())
        return {
            "turn": raw["turn"],
            "edges": [tuple(e) for e in raw["edges"]],
            "memory_signatures": {
                int(k): [tuple(m) for m in v]
                for k, v in raw["memory_signatures"].items()
            },
        }

    # ------------------------------------------------------------------
    # Needs snapshot
    # ------------------------------------------------------------------

    def read_needs_snapshot(self, turn: int) -> dict[str, Any]:
        """Read needs snapshot for *turn*.

        Returns a dict with ``turn`` and ``columns`` (column-oriented data).
        """
        path = self._dir / f"needs_turn_{_turn_str(turn)}.json"
        return json.loads(path.read_text())

    # ------------------------------------------------------------------
    # Agent aggregate
    # ------------------------------------------------------------------

    def read_agent_aggregate(self, turn: int) -> dict[str, dict[str, Any]]:
        """Read per-civ agent aggregate for *turn*.

        Returns the aggregates dict (keyed by civ string like "civ_0").
        """
        path = self._dir / f"aggregate_turn_{_turn_str(turn)}.json"
        raw = json.loads(path.read_text())
        return raw["aggregates"]

    # ------------------------------------------------------------------
    # Community summary
    # ------------------------------------------------------------------

    def read_community_summary(self, turn: int) -> dict[str, dict[str, Any]]:
        """Read community summary for *turn*.

        Returns the summary dict (keyed by region string like "region_0").
        """
        path = self._dir / f"community_turn_{_turn_str(turn)}.json"
        raw = json.loads(path.read_text())
        return raw["summary"]

    # ------------------------------------------------------------------
    # Economy snapshot (M58b)
    # ------------------------------------------------------------------

    def read_economy_snapshot(self, turn: int) -> dict[str, Any]:
        """Read economy convergence snapshot for *turn*.

        Returns the full snapshot dict (turn, oracle/agent trade volumes, etc.).
        """
        path = self._dir / f"economy_turn_{_turn_str(turn)}.json"
        return json.loads(path.read_text())
