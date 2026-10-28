"""Bounded, read-only identity journal; no private title or financial settlement."""
from copy import deepcopy
from types import SimpleNamespace
import random
import pytest

import chronicler.transaction_receipts as T
from chronicler.transaction_receipts_state import TransactionReceiptState


def _world():
    world = SimpleNamespace(seed=42, turn=10, agent_mode="hybrid", transaction_receipts=None,
        regions=[SimpleNamespace(name=f"Region {i}") for i in range(3)],
        civilizations=[SimpleNamespace(name="Amber"), SimpleNamespace(name="Beryl")])
    T.set_transaction_receipts_enabled(world, True)
    return world


def _row(op, *, merchant=41, physical=True, loss=255, quantity=5.0):
    return dict(merchant_id=merchant, merchant_civ=0, operation=op,
        origin_region=0, dest_region=2, from_region=0 if op < 4 else 1, to_region=2,
        good_slot=0, quantity=quantity, origin_controller=0, dest_controller=1,
        physical_stock=physical, loss_reason=loss)


def _consume(world, rows, *, dropped=0, executed=True):
    T.consume_transaction_frame(world, world.turn, world.transaction_receipts.max_rows,
                                dropped, executed, rows)


def test_disabled_does_not_call_native_or_change_rng_or_world():
    world = _world()
    T.set_transaction_receipts_enabled(world, False)
    before, rng = deepcopy(vars(world)), random.getstate()
    sim = SimpleNamespace(configure_transaction_receipts=lambda *args: None)
    T.prepare_transaction_receipts(world, sim)
    T.capture_transaction_receipts(world, object())
    T.consume_transaction_frame(world, 999, 0, 0, False, [])
    assert T.snapshot_summary(world) == {}
    assert vars(world) == before and random.getstate() == rng


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_supported_modes_and_explicit_mode_override(mode):
    world = _world()
    world.agent_mode = mode
    T.validate_transaction_receipts(world)
    assert T.transaction_receipts_active(world)
    world.agent_mode = "off"
    T.validate_transaction_receipts(world, agent_mode=mode)
    with pytest.raises(ValueError, match="require"):
        T.validate_transaction_receipts(world)
    before = world.transaction_receipts.model_dump_json()
    T.capture_transaction_receipts(world, object())
    assert world.transaction_receipts.model_dump_json() == before


def test_native_config_rebuilt_after_resume_and_disabled_missing_api_is_safe():
    world = _world()
    calls = []
    sim = SimpleNamespace(configure_transaction_receipts=lambda *args: calls.append(args))
    T.prepare_transaction_receipts(world, sim)
    T.prepare_transaction_receipts(world, sim)
    T.set_transaction_receipts_enabled(world, False)
    T.prepare_transaction_receipts(world, sim)
    T.prepare_transaction_receipts(world, object())
    assert calls == [(True, 4096), (True, 4096), (False, 4096)]
    T.set_transaction_receipts_enabled(world, True)
    with pytest.raises(RuntimeError, match="native build"):
        T.prepare_transaction_receipts(world, object())


def test_start_departure_arrival_keep_one_stable_identity_and_frozen_names():
    world = _world()
    _consume(world, [_row(0), _row(7)])
    voyage = world.transaction_receipts.frame[0].voyage_id
    assert voyage == "seed:42:voyage:41:10"
    world.turn += 1
    _consume(world, [_row(1, quantity=3), _row(7, quantity=3)])
    assert {r.voyage_id for r in world.transaction_receipts.frame} == {voyage}
    assert world.transaction_receipts.frame[0].quantity == 3
    world.turn += 1
    _consume(world, [_row(6, quantity=3)])
    assert world.transaction_receipts.frame[0].voyage_id == voyage
    assert world.transaction_receipts.active == {}
    world.turn += 1
    snapshot = T.snapshot_summary(world)
    assert snapshot["rows"][0]["quantity_basis"] == "arrival_queued_before_transit_decay"
    world.regions[0].name = "Changed"
    world.civilizations[0].name = "New dynasty"
    world.transaction_receipts.frame[0].quantity = 1
    assert snapshot["rows"][0]["origin_region_name"] == "Region 0"
    assert snapshot["rows"][0]["origin_controller_name"] == "Amber"
    assert snapshot["rows"][0]["quantity"] == 3
    assert "active" not in snapshot


def test_imported_midtrip_is_unknown_not_a_log_ordinal_voyage():
    world = _world()
    _consume(world, [_row(1), _row(7)])
    assert world.transaction_receipts.active[41].voyage_id is None
    world.turn += 1
    _consume(world, [_row(5, loss=1)])
    row = world.transaction_receipts.frame[0]
    assert row.voyage_id is None and row.loss_id.endswith(":loss:raid")
    assert row.cargo_title_owner is None and row.financial_eligible is False
    assert row.origin_controller == 0 and row.merchant_civ == 0
    assert world.transaction_receipts.counters["regional_cargo_raided"] == 5
    assert world.transaction_receipts.active == {}


def test_duplicate_and_restored_reads_cannot_count_a_loss_twice():
    world = _world()
    _consume(world, [_row(0), _row(7)])
    world.turn += 1
    loss = [_row(5, loss=1)]
    _consume(world, loss)
    before = world.transaction_receipts.model_dump_json()
    world.transaction_receipts = TransactionReceiptState.model_validate_json(before)
    _consume(world, loss)
    assert world.transaction_receipts.model_dump_json() == before
    assert world.transaction_receipts.counters["regional_cargo_raided"] == 5
    with pytest.raises(ValueError, match="conflicting"):
        _consume(world, [_row(5, loss=1, quantity=4)])
    assert world.transaction_receipts.model_dump_json() == before


def test_resume_between_start_and_departure_preserves_identity_exactly():
    a, b = _world(), _world()
    for world in (a, b):
        _consume(world, [_row(0), _row(7)])
    b.transaction_receipts = TransactionReceiptState.model_validate_json(b.transaction_receipts.model_dump_json())
    for turn, rows in [(11, [_row(1), _row(7)]), (12, [_row(5), _row(7)]), (13, [_row(6)])]:
        for world in (a, b):
            world.turn = turn
            _consume(world, rows)
        assert a.transaction_receipts.model_dump_json() == b.transaction_receipts.model_dump_json()
    assert a.transaction_receipts.frame[0].voyage_id == "seed:42:voyage:41:10"


def test_return_then_new_reservation_same_tick_has_distinct_voyage():
    world = _world()
    _consume(world, [_row(0), _row(7)])
    world.turn += 1
    _consume(world, [_row(4), _row(0), _row(7)])
    assert [r.voyage_id for r in world.transaction_receipts.frame] == [
        "seed:42:voyage:41:10", "seed:42:voyage:41:11", "seed:42:voyage:41:11"]


@pytest.mark.parametrize("kind", ["overflow", "gap", "unexecuted"])
def test_partial_or_missing_capture_invalidates_identity_without_inferred_loss(kind):
    world = _world()
    _consume(world, [_row(0), _row(7)])
    world.turn += 2 if kind == "gap" else 1
    _consume(world, [] if kind == "unexecuted" else [_row(7)],
             dropped=int(kind == "overflow"), executed=kind != "unexecuted")
    assert all(v.voyage_id is None for v in world.transaction_receipts.active.values())
    assert world.transaction_receipts.counters["regional_cargo_raided"] == 0
    world.turn += 1
    _consume(world, [_row(6)])
    assert world.transaction_receipts.frame[0].voyage_id is None


def test_incomplete_start_never_claims_a_known_voyage_and_state_is_bounded():
    world = _world()
    world.transaction_receipts.max_rows = 2
    _consume(world, [_row(0), _row(7)], dropped=3)
    assert not world.transaction_receipts.complete
    assert all(r.voyage_id is None for r in world.transaction_receipts.frame)
    assert world.transaction_receipts.counters["observed_starts"] == 0
    for turn in range(11, 111):
        world.turn = turn
        _consume(world, [])
    assert world.transaction_receipts.frame == [] and world.transaction_receipts.active == {}
    assert world.transaction_receipts.counters["frames"] == 101


def test_enabled_empty_and_missing_substrate_are_distinct_from_disabled():
    world = _world()
    _consume(world, [])
    world.turn += 1
    snap = T.snapshot_summary(world)
    assert snap["source_turn"] == 10 and snap["complete"] and snap["mobility_executed"]
    _consume(world, [], executed=False)
    world.turn += 1
    snap = T.snapshot_summary(world)
    assert snap["source_turn"] == 11 and not snap["complete"] and not snap["mobility_executed"]
    world.turn += 1
    assert T.snapshot_summary(world) == {}
    T.set_transaction_receipts_enabled(world, False)
    assert T.snapshot_summary(world) == {}


@pytest.mark.parametrize("bad", ["future", "past", "bounds", "quantity", "region", "operation", "duplicate"])
def test_malformed_frames_are_rejected_atomically(bad):
    world = _world()
    before = world.transaction_receipts.model_dump_json()
    rows, turn, limit = [_row(0)], world.turn, 4096
    if bad == "future": turn += 1
    if bad == "past": turn -= 1
    if bad == "bounds": limit = 3
    if bad == "quantity": rows[0]["quantity"] = -1
    if bad == "region": rows[0]["dest_region"] = 999
    if bad == "operation": rows[0]["operation"] = 99
    if bad == "duplicate": rows *= 2
    with pytest.raises(ValueError):
        T.consume_transaction_frame(world, turn, limit, 0, True, rows)
    assert world.transaction_receipts.model_dump_json() == before


def test_virtual_raid_has_no_regional_stock_or_private_financial_claim():
    world = _world()
    world.agent_mode = "shadow"
    _consume(world, [_row(5, physical=False, loss=1)])
    row = world.transaction_receipts.frame[0]
    assert row.cargo_basis == "virtual_shadow" and not row.financial_eligible
    assert row.cargo_title_owner is None
    assert world.transaction_receipts.counters["regional_cargo_raided"] == 0
    assert world.transaction_receipts.counters["virtual_cargo_raided"] == 5


def test_real_world_optional_omission_and_journal_json_roundtrip():
    from chronicler.world_gen import generate_world
    from chronicler.models import WorldState
    world = generate_world(seed=42)
    assert "transaction_receipts" not in world.model_dump_json()
    world.agent_mode = "hybrid"
    T.set_transaction_receipts_enabled(world, True)
    world.turn = 10
    _consume(world, [_row(0), _row(7)])
    restored = WorldState.model_validate_json(world.model_dump_json())
    assert restored.model_dump_json() == world.model_dump_json()
    with pytest.raises(ValueError, match="exact native checkpoint"):
        T.validate_fresh_transaction_receipt_pool(restored)
    # Comparing trusted frames tests state transport, not permission to seed a new pool.
    for current in (world, restored):
        current.turn = 11
        _consume(current, [_row(1), _row(7)])
    assert restored.model_dump_json() == world.model_dump_json()
    T.set_transaction_receipts_enabled(world, False)
    assert "transaction_receipts" not in world.model_dump_json()


def test_successful_capture_reads_same_native_frame_without_draining():
    world = _world()
    batch = SimpleNamespace(to_pylist=lambda: [_row(0), _row(7)])
    sim = SimpleNamespace(get_transaction_receipt_frame=lambda: (10, 4096, 0, True, batch))
    T.capture_transaction_receipts(world, sim)
    before = world.transaction_receipts.model_dump_json()
    T.capture_transaction_receipts(world, sim)
    assert before == world.transaction_receipts.model_dump_json()
    # A restored native transient has no frame; retain the persisted Python view.
    sim.get_transaction_receipt_frame = lambda: (None, 0, 0, False, [])
    T.capture_transaction_receipts(world, sim)
    assert before == world.transaction_receipts.model_dump_json()


def test_fresh_pool_guard_rejects_even_empty_processed_journal_and_allows_explicit_reset():
    world = _world()
    T.validate_fresh_transaction_receipt_pool(world)
    _consume(world, [])
    with pytest.raises(ValueError, match="fresh agent pool"):
        T.validate_fresh_transaction_receipt_pool(world)
    T.set_transaction_receipts_enabled(world, False)
    T.validate_fresh_transaction_receipt_pool(world)
    T.set_transaction_receipts_enabled(world, True)
    T.validate_fresh_transaction_receipt_pool(world)
