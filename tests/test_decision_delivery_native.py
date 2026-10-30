"""Fresh compiled API contracts using tiny direct Arrow fixtures, no world generator.

No-native environments skip explicitly. A present compiled extension must expose
the new API; an older installed wheel is not qualification for this source.
"""
from __future__ import annotations

from importlib.machinery import EXTENSION_SUFFIXES

import pytest

pytestmark = pytest.mark.native


def _native():
    package = pytest.importorskip("chronicler_agents", reason="native extension absent")
    compiled = pytest.importorskip("chronicler_agents.chronicler_agents", reason="compiled submodule absent")
    if not any(str(getattr(compiled, "__file__", "")).endswith(s) for s in EXTENSION_SUFFIXES):
        pytest.skip("requires the real compiled chronicler_agents submodule")
    assert isinstance(package.AgentSimulator, type)
    assert package.AgentSimulator is compiled.AgentSimulator
    assert hasattr(package.AgentSimulator, "configure_decision_delivery"), "fresh decision-delivery build required"
    assert hasattr(package.AgentSimulator, "get_decision_delivery_frame")
    return package


def _setup():
    native = _native()
    pa = pytest.importorskip("pyarrow")
    sim = native.AgentSimulator(num_regions=2, seed=42)
    sim.set_region_state(pa.record_batch({
        "region_id": pa.array([0, 1], type=pa.uint16()),
        "terrain": pa.array([0, 0], type=pa.uint8()),
        "carrying_capacity": pa.array([40, 40], type=pa.uint16()),
        "population": pa.array([8, 8], type=pa.uint16()),
        "soil": pa.array([0.8, 0.8], type=pa.float32()),
        "water": pa.array([0.6, 0.6], type=pa.float32()),
        "forest_cover": pa.array([0.3, 0.3], type=pa.float32()),
        "controller_civ": pa.array([0, 0], type=pa.uint8()),
        "food_sufficiency": pa.array([1.0, 1.0], type=pa.float32()),
        "adjacency_mask": pa.array([2, 1], type=pa.uint32()),
    }))
    return sim


def _signals():
    import pyarrow as pa

    return pa.record_batch({
        "civ_id": pa.array([0], type=pa.uint8()),
        "stability": pa.array([55], type=pa.uint8()),
        "is_at_war": pa.array([False], type=pa.bool_()),
        "dominant_faction": pa.array([0], type=pa.uint8()),
        "faction_military": pa.array([0.3], type=pa.float32()),
        "faction_merchant": pa.array([0.4], type=pa.float32()),
        "faction_cultural": pa.array([0.3], type=pa.float32()),
    })


def _frame(sim):
    import pyarrow as pa

    header, decisions, candidates = (pa.record_batch(b) for b in sim.get_decision_delivery_frame())
    assert header.num_rows == 1
    return header.to_pylist()[0], decisions, candidates


def test_decision_delivery_api_configuration_is_transient_and_keeps_recorded_schema():
    sim = _setup()
    before = bytes(sim.checkpoint_state())
    version, fingerprint, schema = sim.checkpoint_schema()
    assert version == 1 and fingerprint == "dcf0c34097c88451"  # recorded a470/06db
    assert "decision_delivery" not in schema
    sim.configure_decision_delivery(True, 32, 64)
    assert bytes(sim.checkpoint_state()) == before
    header, decisions, candidates = _frame(sim)
    assert header["enabled"] and header["source_turn"] is None
    assert not header["decision_capture_complete"]
    assert not header["applied_move_provenance_complete"]
    assert not header["counterfactual_marginals_computed"]
    assert decisions.num_rows == candidates.num_rows == 0
    for args in ((True, 0, 64), (True, 32, 65537)):
        with pytest.raises(ValueError, match="limits"):
            sim.configure_decision_delivery(*args)
    for ids in ([2, 1], [1, 1]):
        with pytest.raises(ValueError, match="sorted, unique"):
            sim.configure_decision_delivery(True, selected_agent_ids=ids)
    assert bytes(sim.checkpoint_state()) == before


def test_decision_delivery_api_preserves_events_payload_and_actual_tick_mask():
    plain, observed = _setup(), _setup()
    for sim in (plain, observed):
        sim.set_decision_ablation(["needs"], 43)
    observed.configure_decision_delivery(True, 64, 128)
    for turn in (42, 43):
        assert plain.tick(turn, _signals()).equals(observed.tick(turn, _signals()))
        assert bytes(plain.checkpoint_state()) == bytes(observed.checkpoint_state())
        assert plain.get_snapshot().equals(observed.get_snapshot())
        header, decisions, candidates = _frame(observed)
        assert header["source_turn"] == turn
        assert header["active_ablation"] == (1 if turn == 43 else 0)
        assert header["decision_capture_complete"] and decisions.num_rows > 0
        assert candidates.num_rows > 0, "the fixture must exercise actual destination capture"
        assert candidates.num_rows == header["admissible_candidates_all"]
        assert header["alive_seen_all"] >= decisions.num_rows
        assert decisions.schema.field("utility_migrate_bits").type.bit_width == 32
        rows = decisions.to_pylist()
        evaluated = [r for r in rows if r["final_utilities_valid"]]
        assert evaluated, "the fixture must execute actual native decisions"
        assert all(r["needs_computed"] == (turn == 42) for r in evaluated)
        again, again_decisions, again_candidates = _frame(observed)
        assert header == again and decisions.equals(again_decisions) and candidates.equals(again_candidates)


def test_decision_delivery_api_truncation_selection_disable_and_empty_turn():
    sim = _setup()
    ids = sorted(sim.get_snapshot().column("id").to_pylist())[:4]
    sim.configure_decision_delivery(True, 1, 1, ids)
    sim.tick(0, _signals())
    header, decisions, _ = _frame(sim)
    assert header["selection_is_explicit"] and header["selected_ids_requested"] == 4
    assert header["dropped_agent_rows"] > 0 and not header["decision_capture_complete"]
    assert set(decisions.column("agent_id").to_pylist()) <= set(ids)
    sim.configure_decision_delivery(False)
    header, decisions, candidates = _frame(sim)
    assert not header["enabled"] and header["source_turn"] is None
    assert decisions.num_rows == candidates.num_rows == 0
    sim.configure_decision_delivery(True, 32, 64, [])
    sim.tick(1, _signals())
    header, decisions, candidates = _frame(sim)
    assert header["enabled"] and header["source_turn"] == 1
    assert header["selection_is_explicit"] and header["selected_ids_requested"] == 0
    assert header["decision_capture_complete"]
    assert decisions.num_rows == candidates.num_rows == 0


def test_decision_delivery_api_restore_disables_observer_then_rebinds_fresh_frame():
    native = _native()
    sim = _setup()
    sim.configure_decision_delivery(True, 64, 128)
    sim.tick(0, _signals())
    blob = bytes(sim.checkpoint_state())
    restored = native.AgentSimulator.from_checkpoint_state(blob)
    assert bytes(restored.checkpoint_state()) == blob
    header, decisions, candidates = _frame(restored)
    assert not header["enabled"] and header["source_turn"] is None
    assert decisions.num_rows == candidates.num_rows == 0
    restored.configure_decision_delivery(True, 64, 128)
    assert sim.tick(1, _signals()).equals(restored.tick(1, _signals()))
    assert bytes(sim.checkpoint_state()) == bytes(restored.checkpoint_state())
    left, right = _frame(sim), _frame(restored)
    assert left[0] == right[0] and left[1].equals(right[1]) and left[2].equals(right[2])


def test_decision_delivery_api_failed_tick_cannot_publish_an_old_frame():
    sim = _setup()
    import pyarrow as pa

    sim.configure_decision_delivery(True, 64, 128)
    sim.tick(0, _signals())
    assert _frame(sim)[0]["source_turn"] == 0
    bad = pa.record_batch({"unexpected": pa.array([0], type=pa.uint8())})
    with pytest.raises(ValueError, match="civ_id"):
        sim.tick(1, bad)
    header, decisions, candidates = _frame(sim)
    assert header["enabled"] and header["source_turn"] is None
    assert not header["decision_capture_complete"]
    assert decisions.num_rows == candidates.num_rows == 0
    sim.tick(1, _signals())
    assert _frame(sim)[0]["source_turn"] == 1


# Raw pyo3-arrow classes may differ from the runtime arro3 class by identity.
# This first-hosted-CI contract must exercise actual raw snapshot reuse, no tick.
def test_raw_native_snapshot_reuses_filtered_religion_counts_without_tick(monkeypatch):
    import pyarrow as pa
    import chronicler.turn_artifacts as artifacts
    from chronicler.religion import compute_majority_belief

    native = _native()
    sim = native.AgentSimulator(num_regions=2, seed=42)
    sim.set_region_state(pa.record_batch({
        "region_id": pa.array([0, 1], type=pa.uint16()),
        "terrain": pa.array([0, 0], type=pa.uint8()),
        "carrying_capacity": pa.array([40, 40], type=pa.uint16()),
        "population": pa.array([8, 8], type=pa.uint16()),
        "soil": pa.array([0.8, 0.8], type=pa.float32()),
        "water": pa.array([0.6, 0.6], type=pa.float32()),
        "forest_cover": pa.array([0.3, 0.3], type=pa.float32()),
        "controller_civ": pa.array([0, 0], type=pa.uint8()),
        "food_sufficiency": pa.array([1.0, 1.0], type=pa.float32()),
        "adjacency_mask": pa.array([2, 1], type=pa.uint32()),
        "initial_belief": pa.array([0, 1], type=pa.uint8()),
    }))
    raw = sim.get_snapshot()  # retain the real returned type; no normalization
    assert raw.num_rows > 0 and artifacts._immutable_record_batch(raw)
    before = bytes(sim.checkpoint_state())
    expected = compute_majority_belief(raw)
    assert expected == {0: 0, 1: 1}
    rows = artifacts.AgentRows(artifacts.Stamp(0, "phase10_entry"), raw)
    original, calls = artifacts.ordered_counts, []

    def grouped(keys, values):
        calls.append(True)
        return original(keys, values)

    monkeypatch.setattr(artifacts, "ordered_counts", grouped)
    assert compute_majority_belief(raw, agent_rows=rows) == expected
    assert compute_majority_belief(raw, agent_rows=rows) == expected
    assert compute_majority_belief(raw, agent_rows=rows) == expected
    assert len(calls) == 1
    assert bytes(sim.checkpoint_state()) == before
