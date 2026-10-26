"""Columnar helpers for Arrow batches (pyarrow or arro3) that keep exact results.

* ``pylist`` is ``column.to_pylist()``: for a null-free integer, float or
  boolean column it converts through NumPy (``to_numpy().tolist()`` gives the
  same Python ints, floats - float32 widened exactly - and bools, about 20x
  faster than arro3's element-wise ``to_pylist``); anything else is converted
  by Arrow as before.
* ``numeric_array`` is the NumPy view used by vectorized consumers, or None
  when the column has nulls or is not numeric, so callers keep their
  row-by-row path (and its ``None`` handling) for such batches.
* ``ordered_counts`` rebuilds ``{key: Counter({value: count})}`` exactly as
  a row loop of ``counts.setdefault(key, Counter())[value] += 1`` would,
  including dict insertion orders (first appearance of each key, and of each
  value within its key), which ``Counter.most_common`` ties and dict
  iteration depend on.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

_NUMERIC_KINDS = frozenset("iufb")

# Recently read batches and their column names. arro3 builds a new schema
# object on every ``batch.schema`` access (about 30 us for the native
# snapshot), and the same few batches are asked about many times a turn.
# Arrow batches are immutable, so a batch's names never change; holding the
# batches here only delays their release until four newer ones were read.
_SCHEMA_NAMES: list[tuple[object, tuple[str, ...]]] = []


def schema_names(batch) -> tuple[str, ...]:
    """``batch.schema.names`` as a tuple, read once per batch."""
    for held, names in _SCHEMA_NAMES:
        if held is batch:
            return names
    names = tuple(batch.schema.names)
    _SCHEMA_NAMES.insert(0, (batch, names))
    del _SCHEMA_NAMES[4:]
    return names


def numeric_array(column) -> np.ndarray | None:
    """NumPy values of a null-free numeric/bool Arrow column, else None."""
    try:
        if column.null_count != 0:
            return None
        values = np.asarray(column.to_numpy())
    except Exception:  # non-primitive types (strings, lists, ...) or non-Arrow stand-ins
        return None
    return values if values.dtype.kind in _NUMERIC_KINDS and values.ndim == 1 else None


def pylist(column) -> list:
    """``column.to_pylist()``, through NumPy where that yields equal values."""
    values = numeric_array(column)
    return values.tolist() if values is not None else column.to_pylist()


def batch_arrays(batch, names) -> tuple[np.ndarray, ...] | None:
    """``numeric_array`` of each named column, or None if any is unusable."""
    if batch is None:
        return None
    try:
        present = schema_names(batch)
        if not all(name in present for name in names):
            return None
        columns = [batch.column(name) for name in names]
    except Exception:  # not an Arrow batch: callers keep their own path
        return None
    arrays = tuple(numeric_array(column) for column in columns)
    if any(a is None for a in arrays) or len({len(a) for a in arrays}) > 1:
        return None
    return arrays


def _distinct(codes: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``np.unique(codes, return_index=True, return_counts=True)`` for codes >= 0.

    Small code ranges use ``bincount`` and ``minimum.at`` (linear time)
    instead of sorting; both give the distinct codes ascending, the first
    row of each and its count.
    """
    n = len(codes)
    span = int(codes.max()) + 1 if n else 0
    if n and span <= max(4 * n, 1 << 16):
        counts = np.bincount(codes, minlength=span)
        first = np.full(span, n, dtype=np.int64)
        np.minimum.at(first, codes, np.arange(n, dtype=np.int64))
        present = np.flatnonzero(counts)
        return present, first[present], counts[present]
    return np.unique(codes, return_index=True, return_counts=True)


def group_rows(keys: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """``[(key, rows)]`` for each distinct key ascending; rows in row order.

    Equal to ``np.flatnonzero(keys == key)`` per key. Keys that fit 16 bits
    are sorted by the (stable) radix path of a narrow dtype.
    """
    keys = np.asarray(keys)
    if len(keys) == 0:
        return []
    lo, hi = int(keys.min()), int(keys.max())
    sortable = (keys - lo).astype(np.uint16) if hi - lo < (1 << 16) else keys
    order = np.argsort(sortable, kind="stable")
    sorted_keys = keys[order]
    bounds = np.flatnonzero(sorted_keys[1:] != sorted_keys[:-1]) + 1
    starts = np.concatenate(([0], bounds))
    return [(int(sorted_keys[s]), rows) for s, rows in zip(starts.tolist(), np.split(order, bounds))]


def ordered_counts(keys: np.ndarray, values: np.ndarray) -> dict[int, Counter]:
    """Per-key value Counters in a row loop's insertion order (Python ints)."""
    keys = np.asarray(keys, dtype=np.int64)
    values = np.asarray(values, dtype=np.int64)
    result: dict[int, Counter] = {}
    if len(keys) == 0:
        return result
    k0, v0 = int(keys.min()), int(values.min())
    width = int(values.max()) - v0 + 1
    pairs = (keys - k0) * width + (values - v0)
    unique, first, counts = _distinct(pairs)
    order = np.argsort(first, kind="stable")
    for pair, count in zip(unique[order].tolist(), counts[order].tolist()):
        key, value = divmod(pair, width)
        counter = result.get(key + k0)
        if counter is None:
            counter = result[key + k0] = Counter()
        counter[value + v0] = count
    return result


def first_appearance(values: np.ndarray) -> list[int]:
    """Distinct values in order of first appearance (Python ints)."""
    values = np.asarray(values)
    if len(values) == 0:
        return []
    lo = int(values.min())
    unique, first, _ = _distinct(values.astype(np.int64) - lo)
    return (unique[np.argsort(first, kind="stable")] + lo).tolist()


def last_row_of(ids: np.ndarray, wanted) -> dict[int, int]:
    """``{id: row}`` for wanted ids present in ``ids``; the last row wins.

    Equal to ``{aid: i for i, aid in enumerate(ids)}`` restricted to ``wanted``.
    """
    ids = np.asarray(ids)
    wanted = [w for w in wanted if w is not None]
    if not wanted or len(ids) == 0:
        return {}
    order = np.argsort(ids, kind="stable")
    sorted_ids = ids[order]
    query = np.asarray(wanted, dtype=np.int64)
    pos = np.searchsorted(sorted_ids, query, side="right") - 1
    found = (pos >= 0) & (sorted_ids[np.maximum(pos, 0)] == query)
    return {int(w): int(order[p]) for w, p, ok in zip(query.tolist(), pos.tolist(), found.tolist()) if ok}
