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
        schema_names = batch.schema.names
        if not all(name in schema_names for name in names):
            return None
        columns = [batch.column(name) for name in names]
    except Exception:  # not an Arrow batch: callers keep their own path
        return None
    arrays = tuple(numeric_array(column) for column in columns)
    if any(a is None for a in arrays) or len({len(a) for a in arrays}) > 1:
        return None
    return arrays


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
    unique, first, counts = np.unique(pairs, return_index=True, return_counts=True)
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
    unique, first = np.unique(values, return_index=True)
    return unique[np.argsort(first, kind="stable")].tolist()


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
