"""Snapshot contract ratchets and compatibility at existing consumer gates."""
from typing import get_args

import pyarrow as pa
import pytest

from chronicler.bridge_contract import (
    FloatColumn, IntColumn, SNAPSHOT_FIELD_NAMES, SNAPSHOT_SCHEMA,
    validate_snapshot_schema,
)
from chronicler.culture import compute_civ_cultural_profile
from chronicler.religion import compute_conversion_signals, compute_majority_belief
from chronicler.settlements import run_settlement_tick
from chronicler.turn_artifacts import AgentRows, Stamp

from test_turn_artifact_views import CountingBatch, consumer_batch, rows_for


@pytest.mark.parametrize("rows", [0, 1])
def test_explicit_check_is_schema_only_and_accepts_metadata(rows):
    batch = pa.RecordBatch.from_arrays(
        [pa.array([0] * rows, type=field.type) for field in SNAPSHOT_SCHEMA],
        schema=SNAPSHOT_SCHEMA.with_metadata({b"diagnostic": b"allowed"}),
    )
    probe = CountingBatch(batch)
    validate_snapshot_schema(probe.schema)
    assert not probe.accesses and not probe.calls


@pytest.mark.parametrize("name", SNAPSHOT_FIELD_NAMES[:-1])
def test_missing_native_field_is_rejected_even_without_rows(name):
    schema = pa.schema([field for field in SNAPSHOT_SCHEMA if field.name != name])
    with pytest.raises(KeyError, match=name):
        validate_snapshot_schema(schema)


def test_a_capture_from_before_the_movement_column_is_accepted():
    """The snapshot without ``movement_id`` (its last field) is the layout
    every capture had before agent movements; it stays valid. Dropping any
    other field from it is still rejected."""
    legacy = pa.schema([field for field in SNAPSHOT_SCHEMA if field.name != "movement_id"])
    validate_snapshot_schema(legacy)
    with pytest.raises(KeyError, match="settlement_id"):
        validate_snapshot_schema(pa.schema([f for f in legacy if f.name != "settlement_id"]))
    with pytest.raises(ValueError, match="order"):
        validate_snapshot_schema(pa.schema([SNAPSHOT_SCHEMA.field("movement_id"), *legacy]))


@pytest.mark.parametrize("name", SNAPSHOT_FIELD_NAMES)
def test_wrong_arrow_type_is_rejected_without_coercion(name):
    index = SNAPSHOT_SCHEMA.get_field_index(name)
    schema = SNAPSHOT_SCHEMA.set(index, pa.field(name, pa.string(), nullable=False))
    with pytest.raises(TypeError, match=name):
        validate_snapshot_schema(schema)


@pytest.mark.parametrize("name", SNAPSHOT_FIELD_NAMES)
def test_native_nullability_is_ratcheted(name):
    index = SNAPSHOT_SCHEMA.get_field_index(name)
    schema = SNAPSHOT_SCHEMA.set(index, SNAPSHOT_SCHEMA.field(name).with_nullable(True))
    with pytest.raises(ValueError, match=name):
        validate_snapshot_schema(schema)


@pytest.mark.parametrize("schema, message", [
    (SNAPSHOT_SCHEMA.append(pa.field("future_field", pa.uint8())), "unexpected"),
    (SNAPSHOT_SCHEMA.append(SNAPSHOT_SCHEMA.field("id")), "duplicate"),
    (pa.schema(list(SNAPSHOT_SCHEMA)[::-1]), "order"),
])
def test_native_additions_duplicates_and_order_require_contract_update(schema, message):
    with pytest.raises(ValueError, match=message):
        validate_snapshot_schema(schema)


def test_phase10_aliases_are_existing_native_fields_of_the_right_kind():
    assert set(get_args(IntColumn)).isdisjoint(get_args(FloatColumn))
    for name in get_args(IntColumn):
        assert pa.types.is_unsigned_integer(SNAPSHOT_SCHEMA.field(name).type)
    for name in get_args(FloatColumn):
        assert SNAPSHOT_SCHEMA.field(name).type == pa.float32()


@pytest.mark.parametrize("consumer", [compute_majority_belief, compute_civ_cultural_profile])
def test_consumer_subset_still_allows_extra_and_reordered_fields(consumer):
    batch = consumer_batch()
    extended = batch.append_column("future_field", pa.array(["unused"] * batch.num_rows))
    reordered = extended.select(extended.schema.names[::-1])
    probe = CountingBatch(reordered)
    assert consumer(probe, agent_rows=rows_for(probe)) == consumer(batch)
    assert not probe.accesses["future_field"]


def test_view_does_not_add_eager_missing_or_wrong_type_validation():
    batch = pa.record_batch({"belief": pa.array(["raw", None], type=pa.string())})
    probe = CountingBatch(batch)
    rows = rows_for(probe)
    assert not probe.accesses
    assert rows.ints("belief") == ("raw", None)  # Existing decode is uncoerced.
    with pytest.raises(KeyError):
        rows.ints("region")


@pytest.mark.parametrize("name", ["id", "occupation"])
@pytest.mark.parametrize("cached", [False, True])
def test_conversion_requires_columns_even_without_named_agents(name, cached):
    batch = consumer_batch()
    batch = batch.select([field for field in batch.schema.names if field != name])
    kwargs = {"agent_rows": rows_for(batch)} if cached else {}
    with pytest.raises(KeyError, match=name):
        compute_conversion_signals([], {}, [], batch, named_agents={}, **kwargs)


def test_settlement_interval_still_defers_missing_columns(sample_world):
    probe = CountingBatch(consumer_batch().select(["id"]))
    rows = AgentRows(Stamp(1, "phase10_entry"), probe)
    assert run_settlement_tick(sample_world, 1, agent_rows=rows) == []
    assert not probe.accesses
    with pytest.raises(KeyError, match="region"):
        run_settlement_tick(sample_world, 1, force=True, agent_rows=rows)


@pytest.mark.native
@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_existing_native_snapshot_matches_contract_before_and_after_tick(sample_world, mode):
    native = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(native, "AgentSimulator", None), type):
        pytest.skip("requires chronicler_agents Rust extension")
    from chronicler.agent_bridge import AgentBridge
    from conftest import _prime_agent_mode_world

    world = _prime_agent_mode_world(sample_world.model_copy(deep=True), mode)
    bridge = AgentBridge(world, mode=mode)
    for tick in [False, True]:
        if tick:
            bridge.tick(world)
        snapshot = bridge.get_snapshot()
        validate_snapshot_schema(snapshot.schema)
        assert snapshot.num_rows > 0
