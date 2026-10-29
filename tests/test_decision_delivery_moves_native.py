"""Compiled Stage 2 contracts using direct Arrow regions, no world generator."""
from __future__ import annotations

import pytest

from tests.test_decision_delivery_native import _frame, _native, _signals

pytestmark = pytest.mark.native


def _setup():
    native = _native()
    assert hasattr(native.AgentSimulator, "get_decision_delivery_move_frame"), "fresh applied-move build required"
    pa = pytest.importorskip("pyarrow")
    sim = native.AgentSimulator(num_regions=2, seed=42)
    # A crowded, food-poor origin and a fed destination exercise actual moves.
    # These are controlled input states, with unchanged production coefficients.
    sim.set_region_state(pa.record_batch({
        "region_id": pa.array([0, 1], type=pa.uint16()),
        "terrain": pa.array([0, 0], type=pa.uint8()),
        "carrying_capacity": pa.array([20, 100], type=pa.uint16()),
        "population": pa.array([32, 8], type=pa.uint16()),
        "soil": pa.array([0.2, 1.0], type=pa.float32()),
        "water": pa.array([0.2, 1.0], type=pa.float32()),
        "forest_cover": pa.array([0.1, 0.3], type=pa.float32()),
        "controller_civ": pa.array([0, 0], type=pa.uint8()),
        "food_sufficiency": pa.array([0.05, 2.0], type=pa.float32()),
        "adjacency_mask": pa.array([2, 1], type=pa.uint32()),
    }))
    return sim


def _moves(sim):
    import pyarrow as pa

    header, rows = (pa.record_batch(batch) for batch in sim.get_decision_delivery_move_frame())
    assert header.num_rows == 1
    return header.to_pylist()[0], rows


def test_move_delivery_api_keeps_old_positional_and_three_batch_schema_contract():
    sim = _setup()
    import pyarrow as pa

    before = bytes(sim.checkpoint_state())
    original = sim.get_decision_delivery_frame()
    assert len(original) == 3
    schemas = tuple(pa.record_batch(batch).schema for batch in original)
    sim.configure_decision_delivery(True, 32, 64, None)  # existing four positional arguments
    old = sim.get_decision_delivery_frame()
    assert tuple(pa.record_batch(batch).schema for batch in old) == schemas
    assert _frame(sim)[0]["schema_version"] == 1
    header, rows = _moves(sim)
    assert header["schema_version"] == 2 and header["move_limit"] == 16384
    assert header["source_turn"] is None and not header["capture_finished"]
    assert not header["applied_move_provenance_complete"] and rows.num_rows == 0
    assert bytes(sim.checkpoint_state()) == before
    assert sim.checkpoint_schema()[1] == "dcf0c34097c88451"
    for limit in (0, 65537):
        with pytest.raises(ValueError, match="move row limit"):
            sim.configure_decision_delivery(True, max_move_rows=limit)
    with pytest.raises(TypeError):
        sim.configure_decision_delivery(True, 32, 64, None, 16)
    assert bytes(sim.checkpoint_state()) == before


def test_move_delivery_api_links_actual_full_event_ordinals_and_preserves_future_state():
    plain, observed = _setup(), _setup()
    import pyarrow as pa

    for sim in (plain, observed):
        sim.set_decision_ablation(["needs"], 1)
    observed.configure_decision_delivery(True, max_move_rows=8192)
    applied_count = 0
    for turn in (0, 1):
        plain_events = pa.record_batch(plain.tick(turn, _signals()))
        events = pa.record_batch(observed.tick(turn, _signals()))
        assert plain_events.equals(events)
        assert bytes(plain.checkpoint_state()) == bytes(observed.checkpoint_state())
        assert plain.get_snapshot().equals(observed.get_snapshot())
        header, batch = _moves(observed)
        assert header["source_turn"] == turn and header["active_ablation"] == turn
        assert header["capture_finished"] and header["applied_move_provenance_complete"]
        assert header["native_event_ordinals_are_zero_based"]
        rows = batch.to_pylist()
        assert [row["operation_ordinal"] for row in rows] == list(range(header["operations_selected"]))
        by_ordinal = {row["operation_ordinal"]: row for row in rows}
        event_rows = events.to_pylist()
        applied = [row for row in rows if row["applied"]]
        assert len(applied) == header["applied_all"] == sum(e["event_type"] == 2 for e in event_rows)
        for row in applied:
            event = event_rows[row["native_event_ordinal"]]
            assert (event["event_type"], event["agent_id"], event["region"], event["target_region"], event["turn"]) == (2, row["agent_id"], row["from_region"], row["to_region"], turn)
            assert event["migration_driver"] == row["migration_driver"]
            assert row["origin_valid"] and row["role"] in (0, 1, 2)
            origin = by_ordinal[row["origin_operation_ordinal"]]
            assert origin["operation"] in (1, 3) and origin["agent_id"] == row["agent_id"]
            assert origin["to_region"] == row["to_region"]
        applied_count += len(applied)
        again, again_rows = _moves(observed)
        assert header == again and batch.equals(again_rows)
        assert bytes(plain.checkpoint_state()) == bytes(observed.checkpoint_state())
    assert applied_count > 0, "the direct fixture must apply actual native migrations"


def test_move_delivery_api_independent_caps_never_claim_a_truncated_prefix_complete():
    complete = _setup()
    complete.configure_decision_delivery(True, 1, 1, max_move_rows=8192)
    complete.tick(0, _signals())
    assert not _frame(complete)[0]["decision_capture_complete"]
    header, rows = _moves(complete)
    assert header["applied_move_provenance_complete"] and rows.num_rows > 1
    capped = _setup()
    capped.configure_decision_delivery(True, 1, 1, max_move_rows=1)
    capped.tick(0, _signals())
    header, rows = _moves(capped)
    assert rows.num_rows == 1 and header["dropped_move_rows"] > 0
    assert header["tracked_origins_peak"] <= 1
    assert not header["applied_move_provenance_complete"]
    assert bytes(complete.checkpoint_state()) == bytes(capped.checkpoint_state())


def test_move_delivery_api_positive_selection_is_independent_of_stage1_rows():
    reference = _setup()
    reference.configure_decision_delivery(True, max_move_rows=8192)
    expected_events = reference.tick(0, _signals())
    reference_header, reference_rows = _moves(reference)
    applied_ids = sorted({row["agent_id"] for row in reference_rows.to_pylist() if row["applied"]})
    assert applied_ids, "select a genuinely applied agent in the direct fixture"
    selected = [applied_ids[0]]
    sim = _setup()
    sim.configure_decision_delivery(True, 1, 1, selected, max_move_rows=8192)
    assert sim.tick(0, _signals()).equals(expected_events)
    assert bytes(sim.checkpoint_state()) == bytes(reference.checkpoint_state())
    header, rows = _moves(sim)
    assert header["selection_is_explicit"] and header["selected_ids_requested"] == 1
    assert header["operations_seen_all"] == reference_header["operations_seen_all"]
    assert header["applied_move_provenance_complete"] and header["applied_selected"] >= 1
    assert rows.num_rows == header["operations_selected"]
    assert set(rows.column("agent_id").to_pylist()) == set(selected)


@pytest.mark.parametrize("selection", [[], [2**32 - 1]])
def test_move_delivery_api_empty_or_absent_id_selection_is_an_explicit_empty_frame(selection):
    sim = _setup()
    sim.configure_decision_delivery(True, 1, 1, selection, max_move_rows=1)
    sim.tick(0, _signals())
    header, rows = _moves(sim)
    assert header["source_turn"] == 0 and header["capture_finished"]
    assert header["selection_is_explicit"] and header["selected_ids_requested"] == len(selection)
    assert header["operations_selected"] == header["dropped_move_rows"] == 0
    assert header["applied_move_provenance_complete"] and rows.num_rows == 0


def test_move_delivery_api_restore_failed_tick_and_reset_cannot_reuse_a_stale_frame():
    sim = _setup()
    import pyarrow as pa

    sim.configure_decision_delivery(True, max_move_rows=8192)
    sim.tick(0, _signals())
    assert _moves(sim)[0]["source_turn"] == 0
    blob = bytes(sim.checkpoint_state())
    restored = _native().AgentSimulator.from_checkpoint_state(blob)
    header, rows = _moves(restored)
    assert not header["enabled"] and header["source_turn"] is None and rows.num_rows == 0
    restored.configure_decision_delivery(True, max_move_rows=8192)
    assert sim.tick(1, _signals()).equals(restored.tick(1, _signals()))
    assert bytes(sim.checkpoint_state()) == bytes(restored.checkpoint_state())
    left, right = _moves(sim), _moves(restored)
    assert left[0] == right[0] and left[1].equals(right[1])
    with pytest.raises(ValueError, match="civ_id"):
        sim.tick(2, pa.record_batch({"unexpected": [0]}))
    header, rows = _moves(sim)
    assert header["enabled"] and header["source_turn"] is None
    assert not header["capture_finished"] and not header["applied_move_provenance_complete"]
    assert rows.num_rows == 0 and _frame(sim)[0]["source_turn"] is None
    sim.configure_decision_delivery(False, max_move_rows=0)
    header, rows = _moves(sim)
    assert not header["enabled"] and header["source_turn"] is None and rows.num_rows == 0
