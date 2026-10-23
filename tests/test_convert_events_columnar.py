"""The columnar agent-event conversion equals the per-row conversion it replaced."""
from __future__ import annotations

import dataclasses
import random

import pyarrow as pa
import pytest

from chronicler.agent_bridge import EVENT_TYPE_MAP, AgentBridge
from chronicler.models import AgentEventRecord


def _reference_convert(batch, turn):
    """The pre-columnar per-row ``as_py()`` conversion, verbatim."""
    records = []
    belief_col = batch.column("belief") if "belief" in batch.schema.names else None
    target_agent_id_col = batch.column("target_agent_id") if "target_agent_id" in batch.schema.names else None
    formed_turn_col = batch.column("formed_turn") if "formed_turn" in batch.schema.names else None
    for i in range(batch.num_rows):
        event_type_code = batch.column("event_type")[i].as_py()
        records.append(AgentEventRecord(
            turn=turn,
            agent_id=batch.column("agent_id")[i].as_py(),
            event_type=EVENT_TYPE_MAP.get(event_type_code, f"unknown_{event_type_code}"),
            region=batch.column("region")[i].as_py(),
            target_region=batch.column("target_region")[i].as_py(),
            civ_affinity=batch.column("civ_affinity")[i].as_py(),
            occupation=batch.column("occupation")[i].as_py(),
            belief=belief_col[i].as_py() if belief_col is not None else None,
            target_agent_id=target_agent_id_col[i].as_py() if target_agent_id_col is not None else 0,
            formed_turn=formed_turn_col[i].as_py() if formed_turn_col is not None else 0,
        ))
    return records


def _value_types(record):
    return tuple(type(getattr(record, f.name)) for f in dataclasses.fields(record))


def _batch(rng, rows, optional):
    columns = {
        "agent_id": pa.array([rng.randint(0, 2**32 - 1) for _ in range(rows)], type=pa.uint32()),
        "event_type": pa.array([rng.choice(list(EVENT_TYPE_MAP) + [250, 255]) for _ in range(rows)],
                               type=pa.uint8()),
        "region": pa.array([rng.randint(0, 65535) for _ in range(rows)], type=pa.uint16()),
        "target_region": pa.array([rng.randint(0, 40) for _ in range(rows)], type=pa.uint16()),
        "civ_affinity": pa.array([rng.randint(0, 9) for _ in range(rows)], type=pa.uint16()),
        "occupation": pa.array([rng.randint(0, 4) for _ in range(rows)], type=pa.uint8()),
        "turn": pa.array([7] * rows, type=pa.uint32()),
    }
    if "belief" in optional:
        columns["belief"] = pa.array([rng.choice([None, 0, 3, 255]) for _ in range(rows)], type=pa.uint8())
    if "target_agent_id" in optional:
        columns["target_agent_id"] = pa.array([rng.randint(0, 999) for _ in range(rows)], type=pa.uint32())
    if "formed_turn" in optional:
        columns["formed_turn"] = pa.array([rng.randint(0, 300) for _ in range(rows)], type=pa.uint32())
    return pa.record_batch(columns)


@pytest.mark.parametrize("optional", [(), ("belief",), ("belief", "target_agent_id", "formed_turn"),
                                      ("target_agent_id",), ("formed_turn",)])
@pytest.mark.parametrize("rows", [0, 1, 37])
def test_columnar_convert_events_matches_per_row_conversion(optional, rows):
    rng = random.Random(rows * 31 + len(optional))
    batch = _batch(rng, rows, optional)
    bridge = AgentBridge.__new__(AgentBridge)
    records = bridge._convert_events(batch, 12)
    expected = _reference_convert(batch, 12)
    assert records == expected
    assert [_value_types(r) for r in records] == [_value_types(r) for r in expected]


@pytest.mark.parametrize("optional", [(), ("belief", "target_agent_id", "formed_turn")])
def test_columnar_convert_events_matches_on_arro3_batches(optional):
    """The native runtime hands back arro3 batches; check that array type too."""
    arro3 = pytest.importorskip("arro3.core")
    batch = arro3.RecordBatch.from_arrow(_batch(random.Random(3), 25, optional))
    bridge = AgentBridge.__new__(AgentBridge)
    assert bridge._convert_events(batch, 4) == _reference_convert(batch, 4)
