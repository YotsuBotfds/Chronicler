"""Evidence-observer checks; actual native trajectories are a separate probe."""
from __future__ import annotations

from collections import deque
import importlib.util
from pathlib import Path

from pydantic import BaseModel, Field
import pytest


@pytest.fixture(scope="module")
def diagnostic():
    path = Path(__file__).resolve().parents[1] / "scripts/profile_ablation_writer_cadence.py"
    spec = importlib.util.spec_from_file_location("writer_cadence_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_excluded_pending_fields_remain_visible_to_observer(diagnostic):
    class Carried(BaseModel):
        public: int = 1
        pending: list[int] = Field(default_factory=list, exclude=True)

    first, second = Carried(), Carried(pending=[7])
    assert first.model_dump() == second.model_dump()
    assert diagnostic.signature(first) != diagnostic.signature(second)


def test_bounded_queue_capacity_is_carried_and_unsupported_objects_fail_closed(diagnostic):
    assert diagnostic.signature(deque([1], maxlen=2)) != diagnostic.signature(deque([1], maxlen=3))
    with pytest.raises(TypeError, match="unsupported diagnostic state"):
        diagnostic.signature(object())


def test_observing_memory_cache_does_not_encode_missing_entries(diagnostic):
    from chronicler.memory import MemoryStream

    stream = MemoryStream("test")
    stream.add("first", 1)
    stream.json_text()  # The real writer creates the first cached row.
    stream.add("second", 2)
    rows = stream.__dict__["_encoded"]["entries"]
    cached_row = rows[0]
    before = diagnostic.memory_cache({"test": stream})
    assert before["test"]["entries"]["rows"] == 1
    assert len(stream.entries) == 2 and len(rows) == 1 and rows[0] is cached_row
    stream.json_text()
    assert before != diagnostic.memory_cache({"test": stream})
