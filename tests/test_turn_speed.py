"""Turn-speed changes that must keep every value: helpers against their originals."""
from __future__ import annotations

import importlib
import os

import pyarrow as pa
import pytest

import chronicler
import chronicler.politics  # noqa: F401  (politics_bridge imports politics first)
from chronicler.politics_bridge import _batch_to_dict


def _reference_batch_to_dict(batch) -> dict:
    """The conversion before the turn-speed work (``to_pylist`` per column)."""
    return {batch.schema.field(i).name: batch.column(i).to_pylist() for i in range(batch.num_columns)}


def _batches():
    columns = {
        "step": pa.array([3, 1, 2], pa.uint16()),
        "seq": pa.array([0, 7, 2**40], pa.uint64()),
        "civ": pa.array([0, 255, 4], pa.uint8()),
        "delta": pa.array([-1, 0, 5], pa.int32()),
        "value": pa.array([0.1, -2.5, 3.0e-8], pa.float32()),
        "flag": pa.array([True, False, True]),
        "name": pa.array(["a", "", "ç"]),
        "region_indices": pa.array([[1, 2], [], [65535]], pa.list_(pa.uint16())),
    }
    full = pa.record_batch(columns)
    yield full
    yield full.slice(0, 0)
    yield pa.record_batch({"nullable": pa.array([1, None, 3], pa.uint16())})
    import arro3.core as ac
    yield ac.RecordBatch.from_arrow(full)
    yield ac.RecordBatch.from_arrow(full.slice(0, 0))


@pytest.mark.parametrize("batch", list(_batches()))
def test_politics_batch_to_dict_matches_to_pylist(batch):
    got = _batch_to_dict(batch)
    expected = _reference_batch_to_dict(batch)
    assert list(got) == list(expected)
    for name in expected:
        assert got[name] == expected[name]
        assert [type(v) for v in got[name]] == [type(v) for v in expected[name]]


def test_openblas_spin_timeout_is_a_default(monkeypatch):
    monkeypatch.delenv("OPENBLAS_THREAD_TIMEOUT", raising=False)
    importlib.reload(chronicler)
    assert os.environ["OPENBLAS_THREAD_TIMEOUT"] == "16"
    monkeypatch.setenv("OPENBLAS_THREAD_TIMEOUT", "28")
    importlib.reload(chronicler)
    assert os.environ["OPENBLAS_THREAD_TIMEOUT"] == "28"


def _reference_people_and_farmers(snapshot, n_regions):
    workers = [0] * n_regions
    people = [0] * n_regions
    for rid, occupation in zip(snapshot.column("region").to_pylist(),
                               snapshot.column("occupation").to_pylist()):
        if 0 <= rid < n_regions:
            people[rid] += 1
            if occupation == 0:
                workers[rid] += 1
    return people, workers


@pytest.mark.parametrize("n_regions", [0, 1, 5, 9])
def test_fishery_region_counts_match_the_row_loop(n_regions):
    import arro3.core as ac
    import numpy as np

    from chronicler.experimental.fisheries import _region_people_and_farmers

    rng = np.random.default_rng(n_regions)
    batch = pa.record_batch({
        "region": pa.array(rng.integers(0, 12, 500), pa.uint16()),
        "occupation": pa.array(rng.integers(0, 5, 500), pa.uint8()),
    })
    for b in (batch, ac.RecordBatch.from_arrow(batch), batch.slice(0, 0)):
        people, farmers = _region_people_and_farmers(b, n_regions)
        assert (people, farmers) == _reference_people_and_farmers(b, n_regions)
        assert all(type(v) is int for v in people + farmers)
    nullable = pa.record_batch({
        "region": pa.array([0, None], pa.uint16()), "occupation": pa.array([0, 0], pa.uint8()),
    })
    assert _region_people_and_farmers(nullable, 3) is None


def test_schema_names_are_each_batchs_own():
    import arro3.core as ac

    from chronicler.columnar import schema_names

    batches = []
    for i in range(7):
        b = pa.record_batch({f"a{i}": pa.array([1]), f"b{i}": pa.array([2.0])})
        batches.append(b if i % 2 else ac.RecordBatch.from_arrow(b))
    for _ in range(2):  # more batches than the cache holds, twice over
        for b in batches:
            assert schema_names(b) == tuple(b.schema.names)
    b = batches[-1]
    assert schema_names(b) is schema_names(b)
    with pytest.raises(AttributeError):
        schema_names(object())
