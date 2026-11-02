"""Bounded report delay and then-known procurement receipts; no native pool."""
from __future__ import annotations

from dataclasses import asdict
import random
import pytest

import chronicler.grain_reserves as G
import chronicler.harvest_forecasts as H
from chronicler.contact_ledger import ContactLedgerState
from test_grain_reserves import _economy
from test_harvest_forecasts import _world, _forecast_tick, _publish, _warning, AMBER, FROST


def test_zero_and_missing_delay_preserve_existing_world_output_and_rng():
    baseline, explicit = _world(), _world()
    from copy import deepcopy
    from chronicler.harvest_forecasts_state import HarvestForecastState
    old_pickle = deepcopy(explicit.harvest_forecasts.__getstate__())
    old_pickle["__dict__"].pop("report_delay", None)
    old = HarvestForecastState.__new__(HarvestForecastState)
    old.__setstate__(old_pickle)
    explicit.harvest_forecasts = old
    before = explicit.model_dump_json()
    H.set_report_delay(explicit, None)
    H.set_report_delay(explicit, 0)
    assert "report_delay" not in explicit.harvest_forecasts.__dict__
    assert explicit.model_dump_json() == before
    rng = random.getstate()
    a, b = _publish(baseline), _publish(explicit)
    assert {i: r.model_dump_json() for i, r in a.items()} == {i: r.model_dump_json() for i, r in b.items()}
    assert baseline.model_dump_json() == explicit.model_dump_json()
    assert random.getstate() == rng


@pytest.mark.parametrize("bad", [-1, 13, True, 1.5, "3"])
def test_delay_rejects_invalid_inputs_without_mutation(bad):
    world = _world()
    before = world.model_dump_json(), random.getstate()
    with pytest.raises(ValueError, match="integer from 0 to 12"):
        H.set_report_delay(world, bad)
    assert (world.model_dump_json(), random.getstate()) == before


def test_only_future_issues_use_delay_existing_schedule_and_expiry_are_fixed():
    world = _world()
    world.contact_ledger = ContactLedgerState(edges=[(AMBER, FROST, 1.0, 0.0, 0.0, 0.0)], last_update_turn=4)
    H.set_report_delay(world, 3)
    reports = _publish(world)
    local, contact = reports[AMBER], reports[FROST]
    assert (local.issued_turn, local.delivery_turn, local.expires_turn) == (5, 9, 11)
    assert (contact.issued_turn, contact.delivery_turn, contact.expires_turn) == (5, 10, 11)
    H.set_report_delay(world, 12)
    assert (local.delivery_turn, contact.delivery_turn) == (9, 10)
    for turn in range(6, 10):
        world.turn = turn
        _forecast_tick(world)
    assert local.delivered_turn == 9 and contact.delivered_turn is None
    world.turn = 10
    _forecast_tick(world)
    assert contact.delivered_turn == 10
    for turn in range(11, 18):
        world.turn = turn
        _forecast_tick(world)
    next_report = next(r for r in world.harvest_forecasts.reports if r.recipient_region == AMBER)
    assert next_report.id != local.id and next_report.issued_turn == 17
    assert next_report.delivery_turn == 30 and next_report.expires_turn == 23


def test_past_expiry_never_delivers_but_original_harvest_evaluation_is_preserved():
    world = _world()
    H.set_report_delay(world, 12)
    report = _publish(world)[AMBER]
    assert report.delivery_turn == 18 and report.expires_turn == report.target_end == 11
    for turn in range(6, 13):
        world.turn = turn
        _forecast_tick(world)
        assert report.delivered_turn is None
    assert report.resolved_turn == 12
    assert report.status == "resolved" and report.evaluation_count == 3
    assert report in world.harvest_forecasts.outcomes
    assert report.id not in {r.id for r in world.harvest_forecasts.reports}


def test_last_expiry_turn_is_still_a_legal_delivery():
    world = _world()
    H.set_report_delay(world, 5)
    report = _publish(world)[AMBER]
    assert report.delivery_turn == report.expires_turn == 11
    for turn in range(6, 12):
        world.turn = turn
        _forecast_tick(world)
    assert report.status == "delivered" and report.delivered_turn == 11
    world.turn = 12
    _forecast_tick(world)
    assert report.resolved_turn == 12


def _capture_in_real_procurement(monkeypatch, world, economy):
    from chronicler.finance import _projections
    original = G._route_graph
    captured = []
    def observe(candidate):
        money = _projections(candidate, None)
        budgets = [int(G.BUDGET_SHARE * max(0, money[i] - G.TREASURY_FLOOR)) if civ.regions else 0
                   for i, civ in enumerate(candidate.civilizations)]
        before, rng = candidate.model_dump_json(), random.getstate()
        from chronicler.public_grain_shipments import inbound_by_destination, shipment_state
        inbound = inbound_by_destination(candidate) if shipment_state(candidate) is not None else None
        captured.append(H.begin_forecast_decisions(candidate, economy, budgets, inbound))
        assert candidate.model_dump_json() == before and random.getstate() == rng
        return original(candidate)
    monkeypatch.setattr(G, "_route_graph", observe)
    G.tick_grain_reserves(world, economy_result=economy)
    assert len(captured) == 1
    return captured[0]


def test_receipt_freezes_current_reports_targets_and_actual_paid_purchase(monkeypatch):
    world = _world()
    report = _warning(world)
    world.regions[AMBER].stockpile.goods["grain"] = 100
    economy = _economy(world)
    G.open_granaries(world, economy)
    owner = world.civ_index_map[world.regions[AMBER].controller]
    before_treasury = world.civilizations[owner].treasury
    batch = _capture_in_real_procurement(monkeypatch, world, economy)
    before, rng = world.model_dump_json(), random.getstate()
    receipts = H.finish_forecast_decisions(world, batch)
    assert world.model_dump_json() == before and random.getstate() == rng
    row = next(r for r in receipts if r.decision.region == AMBER)
    assert row.turn == 6 and row.decision.owner == owner
    assert row.decision.reports[0].id == report.id
    known = row.decision.reports[0]
    assert (known.issued_turn, known.planned_delivery_turn, known.delivered_turn, known.expires_turn) == (5, 6, 6, 11)
    assert row.decision.target_before == 0 and row.decision.requested_target > 0
    assert row.decision.granary_stock == 0 and row.decision.food_demand > 0
    assert row.decision.pending_inbound is None and row.decision.opening_budget > 0
    assert row.purchased_grain > 0 and row.committed_grain == 0 and row.paid > 0
    assert row.paid == before_treasury - world.civilizations[owner].treasury
    assert row.purchased_grain == pytest.approx(world.grain_reserves.granaries[AMBER].grain)
    assert row.attempted is None
    assert not {"observed_ratio", "outcome_shortfall", "resolved_turn", "brier"} & set(asdict(known))
    with pytest.raises((AttributeError, TypeError)):
        row.paid = 0


def test_no_warning_and_stale_report_are_unknown_not_fabricated(monkeypatch):
    world = _world()
    stale = _warning(world)
    stale.expires_turn = 5
    economy = _economy(world)
    G.open_granaries(world, economy)
    batch = _capture_in_real_procurement(monkeypatch, world, economy)
    row = next(r for r in H.finish_forecast_decisions(world, batch) if r.decision.region == AMBER)
    assert row.decision.reports == () and row.decision.target_before is None
    assert row.decision.pending_inbound is None
    assert row.purchased_grain == row.committed_grain == row.paid == 0
    assert row.attempted is None


def test_receipt_rejects_contradictory_reports_without_writes():
    world = _world()
    report = _warning(world)
    economy = _economy(world)
    G.open_granaries(world, economy)
    H.tick_harvest_forecasts(world, economy)
    H.apply_preparedness(world, economy)
    world.harvest_forecasts.reports.append(report.model_copy(deep=True))
    before, rng = world.model_dump_json(), random.getstate()
    with pytest.raises(ValueError, match="contradictory eligible"):
        H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations))
    assert world.model_dump_json() == before and random.getstate() == rng


def test_delay_does_not_change_issued_signal_or_global_random_stream():
    normal, delayed = _world(), _world()
    H.set_report_delay(delayed, 4)
    rng = random.getstate()
    a, b = _publish(normal), _publish(delayed)
    assert random.getstate() == rng
    for rid in a:
        left, right = a[rid], b[rid]
        assert right.delivery_turn == left.delivery_turn + 4
        assert (right.id, right.issued_turn, right.expires_turn, right.target_start,
                right.target_end, right.probability, right.confidence, right.predicted_ratio) == (
                left.id, left.issued_turn, left.expires_turn, left.target_start,
                left.target_end, left.probability, left.confidence, left.predicted_ratio)


def test_receipt_records_actual_delayed_foreign_commitment(monkeypatch):
    from chronicler import public_grain_shipments as shipments
    world = _world()
    _warning(world)
    from chronicler.models import Disposition
    for relationships in world.relationships.values():
        for relation in relationships.values():
            relation.disposition = Disposition.NEUTRAL
    G._ensure(world)
    # No fictitious order: provide real foreign surplus and suppress other
    # regions' domestic reserve needs before production procurement runs.
    for rid, (region, granary) in enumerate(zip(world.regions, world.grain_reserves.granaries)):
        if region.controller:
            granary.owner = world.civ_index_map[region.controller]
            granary.grain = 0 if rid == AMBER else 1000.0
    foreign = next(i for i, r in enumerate(world.regions)
                   if r.controller != world.regions[AMBER].controller
                   and r.name in world.regions[AMBER].adjacencies and r.controller)
    world.regions[foreign].stockpile.goods["grain"] = 200.0
    shipments.set_public_grain_shipments_enabled(world, True)
    economy = _economy(world)
    G.open_granaries(world, economy)
    batch = _capture_in_real_procurement(monkeypatch, world, economy)
    row = next(r for r in H.finish_forecast_decisions(world, batch) if r.decision.region == AMBER)
    pending = world.grain_reserves.shipments.pending
    assert pending and all(order.dest == AMBER for order in pending)
    assert row.decision.pending_inbound == 0
    assert row.purchased_grain == 0 and row.committed_grain == pytest.approx(sum(o.net for o in pending))
    assert row.paid == sum(o.paid for o in pending) > 0
    assert row.attempted is None


def test_prior_target_vector_and_inbound_are_never_guessed():
    world = _world()
    report = _warning(world)
    economy = _economy(world)
    G.open_granaries(world, economy)
    H.tick_harvest_forecasts(world, economy)
    H.apply_preparedness(world, economy)
    prior = [None] * len(world.regions)
    prior[AMBER] = world.harvest_forecasts.preparedness[0]["base_target"]
    inbound = [0.0] * len(world.regions)
    inbound[AMBER] = 3.5
    batch = H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations),
                                       inbound, target_before=prior)
    row = next(r for r in batch.decisions if r.region == AMBER)
    assert row.target_before == prior[AMBER] and row.pending_inbound == 3.5
    before = world.model_dump_json(), random.getstate()
    prior[AMBER] += 1
    with pytest.raises(ValueError, match="prior target conflicts"):
        H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations),
                                   inbound, target_before=prior)
    assert (world.model_dump_json(), random.getstate()) == before
    assert row.reports[0].id == report.id


def test_receipt_rejects_flow_reset_and_contradictory_delivery_dates():
    world = _world()
    report = _warning(world)
    economy = _economy(world)
    G.open_granaries(world, economy)
    H.tick_harvest_forecasts(world, economy)
    H.apply_preparedness(world, economy)
    batch = H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations))
    original = world.grain_reserves.flows
    world.grain_reserves.flows = list(original)
    with pytest.raises(ValueError, match="no longer matches"):
        H.finish_forecast_decisions(world, batch)
    world.grain_reserves.flows = original
    report.delivered_turn = report.issued_turn
    before = world.model_dump_json(), random.getstate()
    with pytest.raises(ValueError, match="contradictory forecast decision report"):
        H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations))
    assert (world.model_dump_json(), random.getstate()) == before


def test_known_warning_keeps_its_granary_keeper_during_late_control_change():
    world = _world()
    report = _warning(world)
    economy = _economy(world)
    G.open_granaries(world, economy)
    H.tick_harvest_forecasts(world, economy)
    # Politics can change region control after opening but before procurement.
    new_owner = next(i for i in range(len(world.civilizations)) if i != report.owner)
    world.regions[AMBER].controller = world.civilizations[new_owner].name
    H.apply_preparedness(world, economy)
    batch = H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations))
    row = next(r for r in batch.decisions if r.region == AMBER)
    assert row.owner == report.owner and row.controller == new_owner
    assert row.reports[0].id == report.id
    assert row.requested_target > row.target_before
    assert H.finish_forecast_decisions(world, batch)[0].attempted is None
