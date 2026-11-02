"""Paid academy materials and dated aggregate work contracts, without native claims."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import pickle
import random
from types import SimpleNamespace as NS

import pytest

import chronicler.learning_services as L
import chronicler.scholarship as scholarship
from chronicler.accumulator import StatAccumulator
from chronicler.learning_services_state import LearningServicesState
from chronicler.scholarship_state import ACADEMY, LIBRARY, ScholarshipState, Seat
from chronicler.war.common import projected_treasury
from test_scholarship import _world, _seat, _rows, _no_draw, VERDANT


def setup(monkeypatch, *, crafts=8, treasury=200):
    _no_draw(monkeypatch, .999)
    world = _world(agent_mode="hybrid")
    seat_id, seat = _seat(world, VERDANT, level=1)
    seat.level_turn = world.turn
    world.scholarship.learning_services = LearningServicesState()
    region = world.regions[VERDANT]
    region.stockpile.goods["crafts"] = crafts
    world.civilizations[seat.lord].treasury = treasury
    return world, seat_id, seat


def phase(world, *, scholars=1, learners=8, price=1.0):
    region = world.regions[VERDANT]
    return replace(_rows(world, {VERDANT: scholars}, others=learners),
                   economy=NS(region_goods={region.name: NS(prices={"craft": price})}))


def upkeep_and_purchase(world, seat_id, *, staff=1, learners=8, price=1.0, commitments=0.0, acc=None):
    ph = phase(world, scholars=staff, learners=learners, price=price)
    upkeep = {}
    scholarship.tick_scholarship(world, phase10=ph, service_upkeep=upkeep, acc=acc)
    rows = L.procure_learning_supplies(world, ph, upkeep,
        commitments={world.regions[VERDANT].name: {"crafts": commitments}}, acc=acc)
    return next(r for r in rows if r.seat_id == seat_id), upkeep


def counts(world, staff=1, learners=8):
    scholars = [0] * len(world.regions)
    population = [0] * len(world.regions)
    scholars[VERDANT], population[VERDANT] = staff, learners
    return L.LearningCounts(world.turn, tuple(scholars), tuple(population))


def actual(plan, *, available=1.0, reserved=1.0, delivered=.5):
    rows = [(i, 0.0, req, 0.0, 0.0) for i, req in enumerate(plan.requests)]
    rows[VERDANT] = (VERDANT, available, plan.requests[VERDANT], reserved, delivered)
    return (plan.source_turn, rows, [(7, VERDANT, reserved, delivered)], 0)


def test_off_is_noop_legacy_pickle_and_original_effect(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    world.scholarship.learning_services = None
    before, rng = world.model_dump_json(), random.getstate()
    assert L.procure_learning_supplies(world, None, None, commitments=None) == ()
    requests, plan = L.prepare_learning_work(world, None)
    assert not any(requests) and plan is None
    assert L.finish_learning_work(world, None, None) == ()
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 1
    assert world.model_dump_json() == before and random.getstate() == rng
    old = deepcopy(world.scholarship.__getstate__())
    old["__dict__"].pop("learning_services", None)
    restored = ScholarshipState.__new__(ScholarshipState)
    restored.__setstate__(old)
    assert restored.learning_services is None
    assert "learning_services" not in restored.model_dump()
    assert pickle.loads(pickle.dumps(restored)).learning_services is None


def test_initial_unknown_then_paid_supply_then_actual_partial_work(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    owner = world.civilizations[seat.lord]
    original_research = scholarship.research_factor(world, owner)
    opening = L.learning_inventory_totals(world)
    requests, initial_plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 0
    [unknown] = L.finish_learning_work(world, initial_plan, None)
    assert unknown.upkeep_satisfied is None and unknown.work_delivered is None
    assert unknown.crafts_used is None and unknown.learners_delivered is None
    before_money = owner.treasury
    purchase, upkeep = upkeep_and_purchase(world, seat_id)
    assert (upkeep[seat_id].due, upkeep[seat_id].paid, upkeep[seat_id].satisfied) == (0, 0, True)
    assert (purchase.upkeep_due, purchase.upkeep_amount_paid, purchase.upkeep_satisfied) == (0, 0, True)
    assert purchase.purchased == 8 and purchase.paid == 8
    assert owner.treasury == before_money - 8
    assert world.regions[VERDANT].stockpile.goods["crafts"] == 0
    assert purchase.held_before == 0 and purchase.held_after == 8
    after_purchase = L.learning_inventory_totals(world)
    assert L.learning_inventory_turn_balance(opening, after_purchase) == {
        "opening": 0, "purchased": 8, "used": 0, "lost": 0, "closing": 8}
    world.turn += 1
    assert scholarship.learning_factors(world)[0][VERDANT] == 1.0
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 1 and L.learning_work_pending(world)
    before_work_cash = owner.treasury
    [service] = L.finish_learning_work(world, plan, actual(plan))
    assert not L.learning_work_pending(world)
    assert service.source_turn == world.turn and service.available_turn == world.turn + 1
    assert (service.work_requested, service.work_reserved, service.work_delivered) == (1, 1, .5)
    assert (service.learners_delivered, service.crafts_used, service.held_after) == (4, 4, 4)
    assert owner.treasury == before_work_cash
    end = L.learning_inventory_totals(world)
    assert L.learning_inventory_turn_balance(after_purchase, end) == {
        "opening": 8, "purchased": 0, "used": 4, "lost": 0, "closing": 4}
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 0
    world.turn += 1
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == .5
    assert scholarship.learning_factors(world)[0][VERDANT] == pytest.approx(1.2)
    assert scholarship.research_factor(world, owner) == original_research


def test_missing_delivered_or_stale_counts_never_consume_supplies(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    stale = L.LearningCounts(world.turn - 1, counts(world).scholars, counts(world).learners)
    requests, plan = L.prepare_learning_work(world, stale)
    assert requests[VERDANT] == 0
    [row] = L.finish_learning_work(world, plan, None)
    assert row.work_delivered is None and row.crafts_used is None and row.held_after == 8
    world.turn += 1
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 0


def test_no_supplies_and_unknown_price_or_commitments_cannot_buy(monkeypatch):
    world, seat_id, _ = setup(monkeypatch, crafts=0)
    row, _ = upkeep_and_purchase(world, seat_id)
    assert row.upkeep_satisfied and row.paid == row.purchased == 0 and row.held_after == 0
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 0
    L.finish_learning_work(world, plan, None)
    world.turn += 1
    ph = phase(world, price=0)
    row = L.procure_learning_supplies(world, ph, {}, commitments={})[0]
    assert row.upkeep_satisfied is None and row.craft_price is None
    assert row.market_commitments is None and row.paid == row.purchased == 0


def test_funding_and_commitments_projected_before_any_work(monkeypatch):
    world, seat_id, seat = setup(monkeypatch, crafts=10, treasury=3)
    acc = StatAccumulator()
    owner = world.civilizations[seat.lord]
    acc.add(seat.lord, owner, "treasury", -1, "keep")
    row, _ = upkeep_and_purchase(world, seat_id, price=1.5, commitments=8.0, acc=acc)
    assert row.market_commitments == 8 and row.purchased == pytest.approx(2 / 1.5)
    assert row.paid == 2 and row.held_after == pytest.approx(2 / 1.5)
    assert world.regions[VERDANT].stockpile.goods["crafts"] >= 8
    assert projected_treasury(NS(world=world, acc=acc), owner) == 0
    assert owner.treasury == 3
    acc.apply_keep(world)
    assert owner.treasury == 0


def test_duplicate_host_fails_before_purchase_or_work(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    world.scholarship.seats.append(seat.model_copy(update={"name": "another academy"}))
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="duplicate live academy host"):
        L.procure_learning_supplies(world, phase(world), {}, commitments={})
    with pytest.raises(ValueError, match="duplicate live academy host"):
        L.prepare_learning_work(world, counts(world))
    assert world.model_dump_json() == before


def test_bad_native_work_is_rejected_without_debit_then_cancelled(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    _, plan = L.prepare_learning_work(world, counts(world))
    before = world.model_dump_json()
    for bad in (actual(plan, delivered=1.01), (world.turn + 1, [], [], 0), (world.turn, [], [], 0)):
        with pytest.raises(ValueError):
            L.finish_learning_work(world, plan, bad)
        assert world.model_dump_json() == before
    L.cancel_learning_work(world, plan)
    assert not L.learning_work_pending(world)
    assert world.scholarship.learning_services.inventories[0].held == 8
    with pytest.raises(ValueError, match="lifecycle"):
        L.cancel_learning_work(world, plan)


def test_conquest_preserves_held_goods_and_actual_work_then_fall_loses_once(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    _, plan = L.prepare_learning_work(world, counts(world))
    [service] = L.finish_learning_work(world, plan, actual(plan))
    old_owner = seat.lord
    new_owner = next(i for i in range(len(world.civilizations)) if i != old_owner)
    world.regions[VERDANT].controller = world.civilizations[new_owner].name
    seat.lord = new_owner
    world.turn += 1
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == .5
    assert world.scholarship.learning_services.inventories[0].held == 4
    opening = L.learning_inventory_totals(world)
    seat.fallen_turn = world.turn
    L.procure_learning_supplies(world, phase(world), {}, commitments={})
    state = world.scholarship.learning_services
    assert len(state.supply_losses) == 1
    loss = state.supply_losses[0]
    assert (loss.held_before, loss.lost, loss.held_after) == (4, 4, 0)
    assert L.learning_inventory_turn_balance(opening, L.learning_inventory_totals(world)) == {
        "opening": 4, "purchased": 0, "used": 0, "lost": 4, "closing": 0}
    world.turn += 1
    L.procure_learning_supplies(world, phase(world), {}, commitments={})
    assert state.supply_losses == []


def test_legacy_prototype_receipt_is_not_actual_work_or_known_stock(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    state = world.scholarship.learning_services
    state.last_source_turn = world.turn - 1
    before = L.learning_inventory_totals(world)
    assert all(x is None for x in before.values())
    row, _ = upkeep_and_purchase(world, seat_id)
    assert row.held_before is None and row.held_after is None
    assert row.paid == row.purchased == 0 and "held_unknown" in row.shortfalls
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 0
    [receipt] = L.finish_learning_work(world, plan, None)
    assert receipt.learners_delivered is None and receipt.crafts_used is None
    assert all(x is None for x in L.learning_inventory_totals(world).values())


def test_pre_phase2_counts_read_raw_native_shape_and_reject_unknown(monkeypatch):
    import pyarrow as pa
    world, _, _ = setup(monkeypatch)
    batch = phase(world).agents.batch
    result = L.learning_counts_from_snapshot(batch, world.turn, len(world.regions))
    assert result.source_turn == world.turn
    assert result.scholars[VERDANT] == 1 and result.learners == (8,) * len(world.regions)
    assert L.learning_counts_from_snapshot(None, world.turn, len(world.regions)) is None
    assert L.learning_counts_from_snapshot(batch, True, len(world.regions)) is None
    for region, occupation in (([VERDANT, None], [3, 0]), ([99], [3]), ([VERDANT], [5]),
                               ([float(VERDANT)], [3]), ([VERDANT], [True])):
        invalid = pa.record_batch([pa.array(region), pa.array(occupation)], names=["region", "occupation"])
        assert L.learning_counts_from_snapshot(invalid, world.turn, len(world.regions)) is None


def test_pause_retains_paid_stock_and_passively_records_later_destruction(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    before = L.learning_inventory_totals(world)
    L.set_learning_services_enabled(world, False)
    assert not L.learning_services_active(world)
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 1
    assert L.learning_inventory_totals(world) == before
    snapshot = L.learning_services_snapshot(world)
    assert snapshot["schema_version"] == 1 and not snapshot["enabled"] and not snapshot["active"]
    snapshot["inventories"][0]["held"] = 999
    assert L.learning_inventory_totals(world) == before
    assert L.procure_learning_supplies(world, None, None, commitments=None) == ()
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert not any(requests) and plan is None
    world.turn += 1
    seat.fallen_turn = world.turn
    losses = L.reconcile_learning_assets(world)
    assert len(losses) == 1 and losses[0].lost == 8
    assert not L.reconcile_learning_assets(world)
    assert len(world.scholarship.learning_services.supply_losses) == 1
    assert L.learning_inventory_turn_balance(before, L.learning_inventory_totals(world)) == {
        "opening": 8, "purchased": 0, "used": 0, "lost": 8, "closing": 0}
    L.set_learning_services_enabled(world, True)
    assert L.learning_services_active(world)
    assert world.scholarship.learning_services.inventories[0].retired


def test_reconcile_then_procure_keeps_single_same_turn_loss(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    seat.fallen_turn = world.turn
    assert len(L.reconcile_learning_assets(world)) == 1
    assert L.procure_learning_supplies(world, phase(world), {}, commitments={}) == ()
    assert len(world.scholarship.learning_services.supply_losses) == 1
    assert world.scholarship.learning_services.supply_losses[0].lost == 8
    world.turn += 1
    assert L.reconcile_learning_assets(world) == ()
    assert world.scholarship.learning_services.supply_losses == []


def test_pending_plan_cannot_be_pickled_or_paused(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    _, plan = L.prepare_learning_work(world, counts(world))
    with pytest.raises(ValueError, match="cannot checkpoint pending"):
        pickle.dumps(world.scholarship)
    with pytest.raises(RuntimeError, match="while work is pending"):
        L.set_learning_services_enabled(world, False)
    L.cancel_learning_work(world, plan)
    restored = pickle.loads(pickle.dumps(world.scholarship))
    assert restored.learning_services.inventories[0].held == 8


def test_saved_enabled_config_is_dormant_without_hybrid_agents(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    stock = L.learning_inventory_totals(world)
    world.agent_mode = "off"
    assert not L.learning_services_active(world)
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 1
    assert L.procure_learning_supplies(world, None, None, commitments=None) == ()
    assert L.learning_inventory_totals(world) == stock
    assert not L.learning_services_snapshot(world)["active"]


def test_enabling_requires_scholarship_and_missing_state_stays_off():
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42)
    assert world.scholarship is None
    L.set_learning_services_enabled(world, False)
    with pytest.raises(ValueError, match="require scholarship"):
        L.set_learning_services_enabled(world, True)
    assert world.scholarship is None


def test_unpaid_upkeep_blocks_procurement_then_actual_paid_recovery(monkeypatch):
    world, seat_id, seat = setup(monkeypatch, crafts=8, treasury=0)
    seat.level = seat.peak_level = 2
    seat.owed = .9
    first, observed = upkeep_and_purchase(world, seat_id)
    assert observed[seat_id].due > 0 and not observed[seat_id].satisfied
    assert first.upkeep_satisfied is False and first.upkeep_amount_paid == 0
    assert first.purchased == first.paid == 0
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 0
    [unavailable] = L.finish_learning_work(world, plan, None)
    assert unavailable.work_delivered is None
    world.civilizations[seat.lord].treasury = 200
    second, observed = upkeep_and_purchase(world, seat_id)
    assert observed[seat_id].satisfied and observed[seat_id].due > 0
    assert observed[seat_id].paid == observed[seat_id].due
    assert second.purchased == second.paid == 8
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 1
    L.cancel_learning_work(world, plan)


def test_new_patron_keeps_stock_but_needs_own_actual_upkeep(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    purchase, upkeep = upkeep_and_purchase(world, seat_id)
    old_owner = seat.lord
    new_owner = next(i for i in range(len(world.civilizations)) if i != old_owner)
    world.regions[VERDANT].controller = world.civilizations[new_owner].name
    seat.lord = new_owner
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 0
    [blocked] = L.finish_learning_work(world, plan, None)
    assert blocked.upkeep_lord == old_owner and blocked.upkeep_applies is False
    assert blocked.upkeep_amount_paid == upkeep[seat_id].paid and blocked.held_after == 8
    new_purchase, new_upkeep = upkeep_and_purchase(world, seat_id)
    assert new_upkeep[seat_id].lord == new_owner and new_upkeep[seat_id].satisfied
    assert new_purchase.purchased == 0 and new_purchase.held_after == 8
    world.turn += 1
    requests, plan = L.prepare_learning_work(world, counts(world))
    assert requests[VERDANT] == 1
    [service] = L.finish_learning_work(world, plan, actual(plan))
    assert service.lord == new_owner and service.upkeep_lord == new_owner
    assert service.upkeep_applies is True and service.crafts_used == 4 and service.held_after == 4
    assert purchase.paid == 8


def test_replacement_loses_old_stock_once_and_new_seat_starts_empty(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    opening = L.learning_inventory_totals(world)
    world.turn += 1
    world.scholarship.seats[seat_id] = seat.model_copy(update={"founded_turn": world.turn, "name": "replacement"})
    losses = L.reconcile_learning_assets(world)
    assert len(losses) == 1 and losses[0].lost == 8
    L.procure_learning_supplies(world, phase(world), {}, commitments={})
    inventory = world.scholarship.learning_services.inventories
    assert len(inventory) == 2 and inventory[0].retired and not inventory[1].retired
    assert inventory[1].held == 0
    assert L.learning_inventory_turn_balance(opening, L.learning_inventory_totals(world)) == {
        "opening": 8, "purchased": 0, "used": 0, "lost": 8, "closing": 0}
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 0


def test_reserved_teacher_dies_before_work_paid_supplies_remain(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    _, plan = L.prepare_learning_work(world, counts(world))
    [row] = L.finish_learning_work(world, plan, actual(plan, available=1, reserved=1, delivered=0))
    assert (row.work_requested, row.work_reserved, row.work_delivered) == (1, 1, 0)
    assert (row.learners_delivered, row.crafts_used, row.held_after) == (0, 0, 8)
    world.turn += 1
    assert L.academy_service_fraction(world, seat_id, turn=world.turn) == 0


def test_conquest_before_patron_update_blocks_service_without_erasing_stock(monkeypatch):
    world, seat_id, seat = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    world.turn += 1
    new_owner = next(i for i in range(len(world.civilizations)) if i != seat.lord)
    world.regions[VERDANT].controller = world.civilizations[new_owner].name
    request, plan = L.prepare_learning_work(world, counts(world))
    assert request[VERDANT] == 0
    [row] = L.finish_learning_work(world, plan, None)
    assert row.held_after == 8 and row.work_delivered is None
    assert L.learning_inventory_totals(world)["held"] == 8


def test_no_scholar_capacity_and_legacy_service_state_survives_pickle(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    row, _ = upkeep_and_purchase(world, seat_id, staff=0)
    assert row.scholar_upper_bound == 0 and row.purchased == row.paid == 0
    state = world.scholarship.learning_services
    old = deepcopy(state.__getstate__())
    for name in ("enabled", "inventories", "procurement_receipts", "supply_losses",
                 "teaching_receipts", "last_procurement_turn", "last_service_turn"):
        old["__dict__"].pop(name, None)
    restored = LearningServicesState.__new__(LearningServicesState)
    restored.__setstate__(old)
    assert restored.enabled is True and restored.inventories is None
    assert pickle.loads(pickle.dumps(restored)).inventories is None


def test_corrupt_paid_upkeep_cannot_produce_work_or_mutate_inventory(monkeypatch):
    world, seat_id, _ = setup(monkeypatch)
    upkeep_and_purchase(world, seat_id)
    asset = world.scholarship.learning_services.inventories[0]
    asset.upkeep_due = 1
    assert asset.upkeep_amount_paid == 0 and asset.upkeep_satisfied is True
    world.turn += 1
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="invalid academy upkeep evidence"):
        L.prepare_learning_work(world, counts(world))
    assert world.model_dump_json() == before
