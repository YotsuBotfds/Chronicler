"""Python expectations for the existing native agent snapshot payload.

The producer is ``chronicler-agents/src/ffi/schema.rs::snapshot_schema``.
This is a snapshot-only ratchet, not a new wire version or batch builder.
All 23 native fields are required and non-nullable. The explicit validator
checks names, count, order, Arrow types and nullability, ignoring metadata.

Runtime consumers intentionally demand smaller subsets after their own gates:
* culture: civ_affinity/region and cultural_value_0/1/2;
* religion: region/civ_affinity, belief, and id/occupation for named agents;
* pilgrimages: id/occupation/loyalty_trait/loyalty, with optional belief;
* settlements: region/x/y, after the detection interval gate;
* runner urban counts: civ_affinity/settlement_id, optional region; the whole
  read is skipped when settlement_id is absent;
* bridge metrics: region/displacement_turn, then wealth/civ_affinity/occupation
  only when wealth is present;
* economy: region/occupation/wealth/civ_affinity; mutual aid: region;
* sidecar aggregates: id/civ_affinity/satisfaction/occupation/region;
* polity realignment: id/region/civ_affinity after the empty-batch gate.

The full native contract has no optional fields. The consumer compatibility
paths above remain independent: do not call this validator from AgentRows,
snapshot capture, or a consumer. Those paths still allow extra/reordered fields,
defer missing-column failures, and decode without type coercion or validation.
The column aliases below retain the existing Phase-10 view's supported reads.
"""
from __future__ import annotations

from typing import Literal

import pyarrow as pa

IntColumn = Literal[
    "id", "region", "civ_affinity", "occupation", "belief",
    "cultural_value_0", "cultural_value_1", "cultural_value_2", "settlement_id",
]
FloatColumn = Literal["x", "y", "loyalty_trait", "loyalty"]

SNAPSHOT_SCHEMA = pa.schema([
    pa.field("id", pa.uint32(), nullable=False),
    pa.field("region", pa.uint16(), nullable=False),
    pa.field("origin_region", pa.uint16(), nullable=False),
    pa.field("civ_affinity", pa.uint8(), nullable=False),
    pa.field("occupation", pa.uint8(), nullable=False),
    pa.field("loyalty", pa.float32(), nullable=False),
    pa.field("satisfaction", pa.float32(), nullable=False),
    pa.field("skill", pa.float32(), nullable=False),
    pa.field("age", pa.uint16(), nullable=False),
    pa.field("displacement_turn", pa.uint16(), nullable=False),
    pa.field("boldness", pa.float32(), nullable=False),
    pa.field("ambition", pa.float32(), nullable=False),
    pa.field("loyalty_trait", pa.float32(), nullable=False),
    pa.field("cultural_value_0", pa.uint8(), nullable=False),
    pa.field("cultural_value_1", pa.uint8(), nullable=False),
    pa.field("cultural_value_2", pa.uint8(), nullable=False),
    pa.field("belief", pa.uint8(), nullable=False),
    pa.field("parent_id_0", pa.uint32(), nullable=False),
    pa.field("parent_id_1", pa.uint32(), nullable=False),
    pa.field("wealth", pa.float32(), nullable=False),
    pa.field("x", pa.float32(), nullable=False),
    pa.field("y", pa.float32(), nullable=False),
    pa.field("settlement_id", pa.uint16(), nullable=False),
])
SNAPSHOT_FIELD_NAMES = tuple(SNAPSHOT_SCHEMA.names)


def validate_snapshot_schema(schema: pa.Schema) -> None:
    """Strict, opt-in native-schema check; never decode or inspect row values.

    Missing fields raise KeyError, wrong Arrow types raise TypeError, and extra,
    duplicate, reordered or nullable fields raise ValueError. Additions require
    an intentional update alongside the native schema; metadata is unrestricted.
    """
    names = tuple(schema.names)
    missing = [name for name in SNAPSHOT_FIELD_NAMES if name not in names]
    if missing:
        raise KeyError(f"snapshot missing required columns {missing!r}")
    extra = [name for name in names if name not in SNAPSHOT_FIELD_NAMES]
    if extra:
        raise ValueError(f"snapshot has unexpected columns {extra!r}")
    if len(names) != len(set(names)):
        raise ValueError("snapshot has duplicate columns")
    for expected in SNAPSHOT_SCHEMA:
        actual = schema.field(expected.name)
        if actual.type != expected.type:
            raise TypeError(
                f"snapshot column {expected.name!r} requires {expected.type}, got {actual.type}"
            )
        if actual.nullable != expected.nullable:
            raise ValueError(f"snapshot column {expected.name!r} must be non-nullable")
    if names != SNAPSHOT_FIELD_NAMES:
        raise ValueError("snapshot column order differs from the native contract")
