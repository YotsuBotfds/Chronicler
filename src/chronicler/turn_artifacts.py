"""Turn-local handoff types and lazy columns of the Phase-10 historical batch.

These objects never fetch native state or own bridge/world carry. The coordinator
owns publication; consumers borrow economy and death records without mutating
them. Arrow's batch is borrowed unchanged, while named-agent membership is copied.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType, MethodDescriptorType
from typing import TYPE_CHECKING, Literal, Mapping, cast

import numpy as np
import pyarrow as pa
from arro3.core import RecordBatch as Arro3RecordBatch

from chronicler.bridge_contract import FloatColumn, IntColumn
from chronicler.columnar import numeric_array, ordered_counts, pylist, schema_names

if TYPE_CHECKING:
    from chronicler.economy import EconomyResult
    from chronicler.models import AgentEventRecord

Stage = Literal["phase10_entry"]

# Closed immutable Arrow batch classes; names/protocols do not admit duck batches.
_IMMUTABLE_RECORD_BATCH_TYPES = (pa.RecordBatch, Arro3RecordBatch)


def _immutable_record_batch(batch) -> bool:
    """Known Arrow classes or the source-verified frozen raw PyO3 Arrow class.

    This is the trusted Arrow data contract, not arbitrary-extension attestation.
    Owned C descriptors reject Python name/module spoofs, borrowed methods and
    subclasses without calling an exporter or an instance metadata getter.
    """
    cls = type(batch)
    if any(cls is known for known in _IMMUTABLE_RECORD_BATCH_TYPES):
        return True
    if type(cls) is not type:
        return False
    namespace = type.__getattribute__(cls, "__dict__")
    module = type.__getattribute__(cls, "__module__")
    if (type(module) is not str or module != "arro3.core._core"
            or type.__getattribute__(cls, "__name__") != "RecordBatch"
            or type.__getattribute__(cls, "__base__") is not object):
        return False
    return all(type(namespace.get(name)) is MethodDescriptorType
               and namespace[name].__objclass__ is cls
               for name in ("__arrow_c_array__", "column"))


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

    # One successful filtered region/belief summary. Tuples own their order and
    # counts; every caller receives fresh mutable dicts/Counters as before.
    __religion_region_counts: list[tuple[tuple[int, tuple[tuple[int, int], ...]], ...]] = field(
        default_factory=list, init=False, repr=False, compare=False,
    )

    def _region_faith_counts(self) -> dict[int, Counter] | None:
        """Private belief!=255 grouping for the immutable historical region rows.

        Keep column demand before cache lookup. Only exact integer arrays of a
        declared immutable batch retain a successful summary; all other shapes,
        nulls, numeric coercions and errors preserve the original grouping path.
        """
        arrays = self.arrays("region", "belief")
        if arrays is None:
            return None
        keys, beliefs = arrays
        cacheable = (_immutable_record_batch(self.batch)
            and all(type(a) is np.ndarray and a.ndim == 1 and a.dtype.kind in "iu"
                    for a in arrays) and len(keys) == len(beliefs))
        if cacheable and self.__religion_region_counts:
            return {key: Counter(dict(items)) for key, items in self.__religion_region_counts[0]}
        has_faith = beliefs != 0xFF
        counts = ordered_counts(keys[has_faith], beliefs[has_faith])
        if cacheable:
            self.__religion_region_counts.append(tuple(
                (key, tuple(values.items())) for key, values in counts.items()))
        return counts

    def has(self, name: str) -> bool:
        return name in schema_names(self.batch)

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
