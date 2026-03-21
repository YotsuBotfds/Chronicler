"""Sidecar Writer/Reader for M53 validation diagnostics.

Writes diagnostic data alongside simulation bundles:
- Graph snapshots (agent relationship graphs + memory signatures)
- Needs snapshots (per-agent need levels from FFI)
- Agent aggregates (per-civ summary statistics)
- Community summaries (region-level cluster summaries)

All formats are JSON for simplicity — this is a diagnostic tool,
not a production pipeline.

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


def _turn_str(turn: int) -> str:
    """Zero-pad turn number to 3 digits for consistent filename sorting."""
    return f"{turn:03d}"


class SidecarWriter:
    """Writes validation sidecar files for a single simulation run."""

    def __init__(self, base_dir: pathlib.Path) -> None:
        self._dir = base_dir / "validation_summary"
        self._dir.mkdir(parents=True, exist_ok=True)

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
        path.write_text(json.dumps(payload, separators=(",", ":")))

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
        elif isinstance(needs_batch, dict):
            data = needs_batch
        else:
            raise TypeError(
                f"needs_batch must be a dict or PyArrow RecordBatch, got {type(needs_batch)}"
            )

        payload = {"turn": turn, "columns": data}
        path = self._dir / f"needs_turn_{_turn_str(turn)}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))

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
        path.write_text(json.dumps(payload, separators=(",", ":")))

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
        path.write_text(json.dumps(payload, separators=(",", ":")))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Flush and finalise.  All writes are synchronous, so this is a no-op
        kept for API symmetry and future buffering support."""


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
