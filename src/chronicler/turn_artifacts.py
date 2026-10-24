"""Turn-local handoff types and lazy columns of the Phase-10 historical batch.

These objects never fetch native state or own bridge/world carry. The coordinator
owns publication; consumers borrow economy and death records without mutating
them. Arrow's batch is borrowed unchanged, while named-agent membership is copied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Mapping, cast

import numpy as np
import pyarrow as pa

from chronicler.bridge_contract import FloatColumn, IntColumn
from chronicler.columnar import numeric_array, pylist

if TYPE_CHECKING:
    from chronicler.economy import EconomyResult
    from chronicler.models import AgentEventRecord

Stage = Literal["phase10_entry"]


@dataclass(frozen=True, slots=True)
class Stamp:
    source_turn: int
    stage: Stage

    def __post_init__(self) -> None:
        if self.stage != "phase10_entry":
            raise ValueError("AgentRows requires the phase10_entry observation stage")


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class AgentRows:
    """Read-only view; successful per-field decodes live only as long as this view.

    No eager schema validation: missing columns and decode errors still occur at
    the demanding consumer, after its original gates. The temporary Python list
    from to_pylist() is converted to a tuple without value coercion.
    """

    stamp: Stamp
    batch: pa.RecordBatch
    __columns: dict[str, tuple[int | float | None, ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False,
    )
    __arrays: dict[str, np.ndarray | None] = field(
        default_factory=dict, init=False, repr=False, compare=False,
    )

    def has(self, name: str) -> bool:
        return name in self.batch.schema.names

    def _column(self, name: str) -> tuple[int | float | None, ...]:
        if name not in self.__columns:
            # Assignment happens only after the complete decode succeeds.
            # ``pylist`` equals ``to_pylist()`` (NumPy route for numeric columns).
            self.__columns[name] = tuple(pylist(self.batch.column(name)))
        return self.__columns[name]

    def array(self, name: str) -> np.ndarray | None:
        """Read-only NumPy values of a column, or None (nulls / not numeric).

        Columnar consumers use it and keep their row-by-row path (``ints`` /
        ``floats``, which keep ``None``) for such batches. The native snapshot
        schema is numeric and non-null.
        """
        if name not in self.__arrays:
            values = numeric_array(self.batch.column(name))
            if values is not None and values.flags.writeable:
                values.flags.writeable = False
            self.__arrays[name] = values
        return self.__arrays[name]

    def arrays(self, *names: str) -> tuple[np.ndarray, ...] | None:
        """``array`` of each name, or None if any column is missing or has nulls."""
        if not all(self.has(name) for name in names):
            return None
        values = tuple(self.array(name) for name in names)
        return None if any(v is None for v in values) else values

    def ints(self, name: IntColumn) -> tuple[int | None, ...]:
        return cast(tuple[int | None, ...], self._column(name))

    def floats(self, name: FloatColumn) -> tuple[float | None, ...]:
        return cast(tuple[float | None, ...], self._column(name))


def _check_agent_rows(snapshot, agent_rows: AgentRows | None, *, source_turn: int | None = None) -> None:
    """Reject a mismatched handoff without reading any consumer columns.

    Callers with an explicit source-turn argument can check it. Never infer
    freshness from world.turn, which may already have advanced for runner reads.
    """
    if agent_rows is not None:
        if agent_rows.batch is not snapshot:
            raise ValueError("agent_rows must wrap the supplied snapshot object")
        if source_turn is not None and agent_rows.stamp.source_turn != source_turn:
            raise ValueError("agent_rows source_turn does not match the consumer turn")


@dataclass(frozen=True, slots=True)
class Phase10Inputs:
    source_turn: int
    agents: AgentRows | None
    named_agents: Mapping[int, str] | None
    economy: EconomyResult | None
    deaths: tuple[AgentEventRecord, ...]

    def __post_init__(self) -> None:
        if self.agents is not None:
            _check_agent_rows(self.agents.batch, self.agents, source_turn=self.source_turn)
        if self.named_agents is not None:
            object.__setattr__(self, "named_agents", MappingProxyType(dict(self.named_agents)))
        object.__setattr__(self, "deaths", tuple(self.deaths))


@dataclass(slots=True)
class TurnArtifacts:
    """One invocation's mutable owner; only the coordinator publishes stages."""

    source_turn: int
    economy: EconomyResult | None = None
    conquered_civ_ids: set[int] = field(default_factory=set)
    deaths: tuple[AgentEventRecord, ...] = ()
    phase10: Phase10Inputs | None = None


@dataclass(frozen=True, slots=True)
class TurnObservation:
    source_turn: int
    completed_turn: int
    phase10_agents: AgentRows | None

    def __post_init__(self) -> None:
        if self.phase10_agents is not None:
            _check_agent_rows(self.phase10_agents.batch, self.phase10_agents, source_turn=self.source_turn)
        if self.completed_turn != self.source_turn + 1:
            raise ValueError("completed_turn must label the completed source_turn as N+1")


@dataclass(frozen=True, slots=True)
class TurnResult:
    chronicle_text: str
    observation: TurnObservation
