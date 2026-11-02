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
from test_expansion_feature_wiring import configure_without_native


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


def test_real_storage_cap_records_requested_and_feasible_separately():
    from chronicler import grain_storage as storage
    world = _world()
    report = _warning(world)
    economy = _economy(world)
    G.open_granaries(world, economy)
    state = G._ensure(world)
    demand = economy.market_demand[world.regions[AMBER].name][0]
    state.granaries[AMBER].target = 3 * demand
    storage.enable_storage(world)
    demands = [economy.market_demand[r.name][0] for r in world.regions]
    plan = storage.prepare_storage_work(world, demands, commitments={})
    storage.finish_storage_work(world, plan, [0.0] * len(world.regions))
    H.tick_harvest_forecasts(world, economy)
    before = [g.target for g in state.granaries]
    H.apply_preparedness(world, economy)
    requested = tuple(g.target for g in state.granaries)
    storage.settle_storage_capacity(world)
    feasible = state.granaries[AMBER].target
    assert requested[AMBER] > feasible
    original, rng = world.model_dump_json(), random.getstate()
    batch = H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
        target_before=before, requested_targets=requested, capacity_records=state.storage.receipts)
    row = next(r for r in batch.decisions if r.region == AMBER)
    assert row.reports[0].id == report.id
    assert row.target_before == pytest.approx(before[AMBER])
    assert row.requested_target == pytest.approx(requested[AMBER])
    assert row.feasible_target == pytest.approx(feasible)
    assert world.model_dump_json() == original and random.getstate() == rng
    with pytest.raises(ValueError, match="lacks actual storage cap evidence"):
        H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
            target_before=before, requested_targets=requested)
    with pytest.raises(ValueError, match="not the current authoritative"):
        H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
            target_before=before, requested_targets=requested,
            capacity_records=list(state.storage.receipts))
    record = next(r for r in state.storage.receipts if r.region == AMBER)
    value = record.target_feasible
    record.target_feasible += 1
    with pytest.raises(ValueError, match="conflicts with targets or capacity"):
        H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
            target_before=before, requested_targets=requested, capacity_records=state.storage.receipts)
    record.target_feasible = value
    state.storage.receipts.append(record.model_copy())
    with pytest.raises(ValueError, match="invalid or duplicate"):
        H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
            target_before=before, requested_targets=requested, capacity_records=state.storage.receipts)
    state.storage.receipts.pop()
    state.storage.receipt_turn -= 1
    with pytest.raises(ValueError, match="not the current authoritative"):
        H.begin_forecast_decisions(world, economy, [20] * len(world.civilizations),
            target_before=before, requested_targets=requested, capacity_records=state.storage.receipts)


def test_no_cap_receipt_remains_compatible_with_previous_call(monkeypatch):
    world = _world()
    _warning(world)
    world.regions[AMBER].stockpile.goods["grain"] = 100
    economy = _economy(world)
    G.open_granaries(world, economy)
    batch = _capture_in_real_procurement(monkeypatch, world, economy)
    row = next(r for r in H.finish_forecast_decisions(world, batch) if r.decision.region == AMBER)
    assert row.decision.requested_target == row.decision.feasible_target


def test_original_assessor_observations_are_frozen_at_issue_and_legacy_unknown():
    from copy import deepcopy
    from chronicler.harvest_forecasts_state import HarvestReport
    world = _world()
    report = _publish(world)[AMBER]
    meta = report.estimator_metadata
    assert meta.schema_version == 1 and meta.policy == "normal"
    assert meta.reported_issuer_region == meta.estimate_origin_region == report.source_region
    assert meta.issued_turn == report.issued_turn
    assert len(meta.observations) == 6
    assert all(0 <= report.issued_turn - turn < H.OBSERVATIONS for turn, _ in meta.observations)
    observer = next(o for o in world.harvest_forecasts.observers if o.region == meta.estimate_origin_region)
    assert meta.observations == tuple(observer.observations)
    import math
    predicted = math.fsum(value for _, value in meta.observations) / len(meta.observations) * meta.season_multiplier
    assert predicted == meta.claimed_predicted_ratio
    assert len(meta.observations) / meta.observation_window == meta.claimed_confidence
    assert min(.95, max(.05, .5 + .5 * (meta.shortfall_ratio - predicted) / meta.shortfall_ratio
                         + meta.noise_draw)) == meta.claimed_probability
    assert (meta.claimed_probability, meta.claimed_confidence, meta.claimed_predicted_ratio) == (
        report.probability, report.confidence, report.predicted_ratio)
    assert meta.base_delivery_lag + meta.extra_delivery_delay == report.delivery_turn - report.issued_turn
    with pytest.raises(ValueError):
        meta.issued_turn = 100
    old = deepcopy(report.__getstate__())
    old["__dict__"].pop("estimator_metadata")
    legacy = HarvestReport.__new__(HarvestReport)
    legacy.__setstate__(old)
    assert legacy.estimator_metadata is None and "estimator_metadata" not in legacy.model_dump(mode="json")
    as_json = report.model_dump(mode="json")
    assert as_json["estimator_metadata"]["observations"] == [list(x) for x in meta.observations]
    captured = meta.observations
    world.harvest_forecasts.policy = "shuffle"
    world.turn = 6
    _forecast_tick(world)
    assert meta.policy == "normal" and meta.observations == captured
    assert all(turn <= meta.issued_turn for turn, _ in captured)


def test_shuffle_records_real_estimator_origin_without_relabeling_issuer():
    normal, shuffled = _world(), _world("shuffle")
    ratios = {2: .05, 3: 1.0, 5: 3.5, 7: 2.0}
    a, b = _publish(normal, ratios), _publish(shuffled, ratios)
    by_source = {r.source_region: r for r in a.values()}
    assert any(r.estimator_metadata.estimate_origin_region != r.source_region for r in b.values())
    for row in b.values():
        meta = row.estimator_metadata
        source = by_source[meta.estimate_origin_region]
        assert meta.policy == "shuffle" and meta.reported_issuer_region == row.source_region
        assert meta.observations == source.estimator_metadata.observations
        assert meta.noise_draw == source.estimator_metadata.noise_draw
        assert (row.probability, row.confidence, row.predicted_ratio) == (
            source.probability, source.confidence, source.predicted_ratio)


def test_issued_source_controller_change_does_not_rewrite_delivered_claim():
    world = _world()
    report = _warning(world)
    report.source_region = 3
    report.source_region_name = world.regions[3].name
    world.regions[3].controller = None
    economy = _economy(world)
    G.open_granaries(world, economy)
    H.tick_harvest_forecasts(world, economy)
    H.apply_preparedness(world, economy)
    batch = H.begin_forecast_decisions(world, economy, [0] * len(world.civilizations))
    row = next(r for r in batch.decisions if r.region == AMBER)
    assert row.reports[0].source_region == 3 and row.reports[0].id == report.id
    assert not hasattr(row.reports[0], "estimator_metadata")


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_shared_configuration_uses_existing_forecast_modes_and_cohort(configure_without_native, mode):
    from chronicler.main import _build_parser
    from chronicler.batch_manifest import simulation_config
    from chronicler.world_gen import generate_world
    assert "harvest_report_delay" not in simulation_config(_build_parser().parse_args([]))
    world = generate_world(seed=42)
    _, config = configure_without_native(world, "--grain-reserves", "--contact-ledger",
        "--harvest-forecasts", "--harvest-report-delay", "3", mode=mode)
    assert H.get_report_delay(world.harvest_forecasts) == 3
    assert config["simulation_args"]["harvest_report_delay"] == 3
    _, dormant = configure_without_native(world, mode="off")
    assert H.get_report_delay(world.harvest_forecasts) == 3
    assert dormant["simulation_args"]["harvest_report_delay"] == 3


@pytest.mark.parametrize("flags", [
    ["--harvest-report-delay", "3"],
    ["--grain-reserves", "--contact-ledger", "--harvest-forecasts", "--harvest-report-delay", "13"],
    ["--grain-reserves", "--contact-ledger", "--harvest-forecasts", "--harvest-report-delay", "-1"],
])
def test_bad_delay_configuration_refused_before_runtime(configure_without_native, flags):
    from chronicler.world_gen import generate_world
    with pytest.raises(ValueError):
        configure_without_native(generate_world(seed=42), *flags)
    assert not configure_without_native.constructions


def test_exact_resume_retains_delay_and_existing_report_schedules():
    from types import SimpleNamespace as NS
    import pickle
    from chronicler.main import _adopt_checkpoint_args, _build_parser
    world = _world()
    H.set_report_delay(world, 3)
    reports = _publish(world)
    report = reports[AMBER]
    assert report.delivery_turn == 9
    saved = NS(state=NS(world=world, seed=42, num_turns=world.turn + 14,
        run_config={"simulation_args": {"harvest_report_delay": 3}}))
    parser = _build_parser()
    args = parser.parse_args([])
    before = pickle.dumps(world)
    assert _adopt_checkpoint_args(parser, args, saved) == []
    assert args.harvest_report_delay == 3
    for value in ("0", "12"):
        changed = parser.parse_args(["--harvest-report-delay", value])
        assert any("--harvest-report-delay conflicts" in c for c in _adopt_checkpoint_args(parser, changed, saved))
    assert report.delivery_turn == 9 and pickle.dumps(world) == before
