"""Observe actual existing grain procurement, not a private merchant account."""
from copy import deepcopy
import pickle
import random
import pytest

import chronicler.grain_reserves as G
import chronicler.public_purchase_receipts as P
import chronicler.transaction_receipts as T
from chronicler.accumulator import StatAccumulator
from chronicler.finance import _projections
from chronicler.grain_reserves_state import BOUGHT
from chronicler.models import WorldState
from chronicler.transaction_receipts_state import TransactionReceiptState
from test_grain_reserves import (
    _world, _economy, _target, _tick, VERDANT, THORNWOOD, ASHARA, THORNWALL, SELURIAN,
)


def _scenario(kind="foreign", enabled=True):
    world = _world()
    if enabled:
        T.set_transaction_receipts_enabled(world, True)
    src = VERDANT
    dest = {"own_market": VERDANT, "same_realm": THORNWOOD, "foreign": ASHARA}[kind]
    world.regions[src].stockpile.goods = {"grain": 80.0}
    result = _economy(world, pop={src: 20, dest: 10})
    granary = _target(world, dest, 30.0 if kind == "own_market" else 12.0)
    if kind == "foreign":
        for i, civ in enumerate(world.civilizations):
            if i != SELURIAN:
                civ.treasury = 0
    return world, result, src, dest, granary


def _basis(world, result, acc=None):
    return dict(economy_result=result, opening_treasuries=_projections(world, acc),
                demand=[G._demand(result, r.name) for r in world.regions],
                price=[G._food_price(result, r.name) for r in world.regions])


@pytest.mark.parametrize("kind", ["own_market", "same_realm", "foreign"])
@pytest.mark.parametrize("accumulated", [False, True])
def test_actual_public_purchase_legs_quantities_and_accumulator_projection(kind, accumulated):
    world, result, src, dest, granary = _scenario(kind)
    buyer = granary.owner
    acc = StatAccumulator() if accumulated else None
    if acc is not None:
        acc.add(buyer, world.civilizations[buyer], "treasury", 40, "keep")
        acc.apply_keep(world)
        acc.add(buyer, world.civilizations[buyer], "treasury", -30, "keep")
        if kind == "foreign":
            acc.add(THORNWALL, world.civilizations[THORNWALL], "treasury", 7, "keep")
    inputs = _basis(world, result, acc)
    before = inputs["opening_treasuries"]
    _tick(world, result, acc)
    frame = world.transaction_receipts.public_purchases
    assert frame.available and frame.complete and frame.phase == "phase10_granary_procurement"
    [row] = frame.rows
    [flow] = [f for f in world.grain_reserves.flows if f.kind == BOUGHT]
    assert row.id == f"seed:42:public-grain:{world.turn}:{buyer}:{dest}:{src}"
    assert row.purchase_kind == kind
    assert row.buyer == row.keeper == flow.buyer == granary.owner
    assert row.source_controller == flow.seller
    assert row.sent == flow.sent and row.received == flow.amount
    assert row.sent == pytest.approx(row.received + row.transit_loss)
    assert row.buyer_paid == flow.cost > 0
    assert row.buyer_treasury_before == before[buyer]
    assert row.buyer_treasury_after == before[buyer]-flow.cost
    assert row.source_market_price == inputs["price"][src]
    assert row.source_demand == inputs["demand"][src]
    assert row.buyer_demand == inputs["demand"][dest]
    assert not row.financial_eligible
    if kind == "foreign":
        assert row.foreign_ruler_credited == flow.cost and row.domestic_producer_sink == 0
        assert row.seller_treasury_after == before[flow.seller]+flow.cost
        assert row.seller_treasury_before == before[flow.seller]
    else:
        assert row.domestic_producer_sink == flow.cost and row.foreign_ruler_credited == 0
        assert row.seller_treasury_before is None and row.seller_treasury_after is None
    actual = _projections(world, acc)
    assert actual[buyer] == row.buyer_treasury_after
    if kind == "foreign":
        assert actual[flow.seller] == row.seller_treasury_after
    # Repeated observation cannot issue another payment or count the first twice.
    snapshot = world.model_dump_json()
    P.capture_public_purchases(world, **inputs)
    assert world.model_dump_json() == snapshot
    if acc is not None:
        acc.apply_keep(world)
        assert world.civilizations[buyer].treasury == row.buyer_treasury_after


@pytest.mark.parametrize("kind", ["own_market", "same_realm", "foreign"])
def test_recording_does_not_change_any_public_economic_state_events_or_rng(kind):
    plain, result_a, _, _, _ = _scenario(kind, enabled=False)
    recorded, result_b, _, _, _ = _scenario(kind)
    rng = random.getstate()
    expected = _tick(plain, result_a)
    after = random.getstate()
    random.setstate(rng)
    actual = _tick(recorded, result_b)
    assert random.getstate() == after
    assert actual == expected
    assert plain.model_dump(mode="json", exclude={"transaction_receipts"}) == recorded.model_dump(
        mode="json", exclude={"transaction_receipts"})
    assert "transaction_receipts" not in plain.model_dump_json()


def test_empty_unavailable_and_unknown_are_distinct_and_do_not_republish_old_rows():
    world, result, _, _, _ = _scenario()
    assert P.snapshot_summary(world)["source_turn"] is None
    world.regions[VERDANT].stockpile.goods = {}
    _tick(world, result)
    frame = world.transaction_receipts.public_purchases
    assert frame.complete and frame.available and frame.rows == []
    world.turn += 1
    assert P.snapshot_summary(world)["source_turn"] == world.turn-1
    G.tick_grain_reserves(world, economy_result=None)
    world.turn += 1
    unavailable = P.snapshot_summary(world)
    assert unavailable["source_turn"] == world.turn-1 and not unavailable["available"]
    assert unavailable["unavailable_reason"] == "economy_unavailable"
    world.turn += 1
    unknown = P.snapshot_summary(world)
    assert unknown["source_turn"] is None and unknown["rows"] == []


def test_schema_old_pydantic_pickle_restores_public_capture_as_unknown_not_empty():
    world, _, _, _, _ = _scenario()
    old = world.transaction_receipts
    old.source_turn = world.turn - 1
    old.complete, old.mobility_executed = True, True
    old.__dict__.pop("public_purchases")
    old.__pydantic_fields_set__.discard("public_purchases")
    restored = pickle.loads(pickle.dumps(old))
    assert isinstance(restored, TransactionReceiptState) and restored.public_purchases is None
    world.transaction_receipts = restored
    assert "public_purchases" not in restored.model_dump_json()
    assert P.snapshot_summary(world)["source_turn"] is None
    assert not P.snapshot_summary(world)["complete"]
    assert T.snapshot_summary(world)["public_purchases"]["source_turn"] is None
    # Old-shaped World exact pickle and JSON loading both preserve unknown.
    again = pickle.loads(pickle.dumps(world))
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert again.transaction_receipts.public_purchases is None
    assert loaded.transaction_receipts.public_purchases is None


def test_both_domains_keep_independent_clocks_and_snapshots_detach_names():
    world, result, _, _, _ = _scenario()
    _tick(world, result)
    assert world.transaction_receipts.source_turn is None  # no native tick was fabricated
    world.turn += 1
    snap = T.snapshot_summary(world)
    assert snap["source_turn"] is None and snap["public_purchases"]["source_turn"] == world.turn-1
    [row] = snap["public_purchases"]["rows"]
    world.regions[row["source_region"]].name = "Changed"
    world.civilizations[row["buyer"]].name = "Changed"
    world.transaction_receipts.public_purchases.rows[0].buyer_paid = 0
    assert row["buyer_name"] != "Changed" and row["source_region_name"] != "Changed"
    assert row["buyer_paid"] > 0


def test_overflow_duplicates_and_conflicts_are_explicit_without_financial_actions():
    world, result, _, _, _ = _scenario()
    inputs = _basis(world, result)
    _tick(world, result)
    row = deepcopy(world.grain_reserves.flows[-1])
    world.turn += 1
    world.grain_reserves.flows_turn = world.turn
    world.transaction_receipts.max_rows = 1
    world.grain_reserves.flows = [row, deepcopy(row)]
    # Trusted committed-flow fixture: this observer itself never applies a leg.
    before = [c.treasury for c in world.civilizations]
    P.capture_public_purchases(world, **inputs)
    frame = world.transaction_receipts.public_purchases
    assert not frame.complete and frame.available and frame.dropped_rows == 1
    assert frame.duplicate_keys == 1 and len(frame.rows) == 1
    assert before == [c.treasury for c in world.civilizations]
    snapshot = frame.model_dump_json()
    world.grain_reserves.flows[1].cost += 1
    with pytest.raises(ValueError, match="conflicting"):
        P.capture_public_purchases(world, **inputs)
    assert frame.model_dump_json() == snapshot


def test_json_and_pickle_resume_preserve_current_frame_counters_and_waiting_boundary():
    world, result, _, _, _ = _scenario()
    _tick(world, result)
    world.turn += 1
    resumed = WorldState.model_validate_json(world.model_dump_json())
    pickled = pickle.loads(pickle.dumps(world))
    for current in (world, resumed, pickled):
        current.regions[VERDANT].stockpile.goods = {}
        _tick(current, result)
    assert world.model_dump_json() == resumed.model_dump_json() == pickled.model_dump_json()
    assert world.transaction_receipts.public_purchases.counters["frames"] == 2
    assert world.transaction_receipts.public_purchases.rows == []


@pytest.mark.parametrize("block", ["route", "treasury", "market"])
def test_blocked_procurement_records_complete_empty_without_inventing_cash_or_grain(block):
    world, result, _, dest, _ = _scenario("same_realm")
    if block == "route":
        world.regions[dest].route_suspensions = {"trade_route": 3}
    elif block == "treasury":
        world.civilizations[THORNWALL].treasury = 0
    else:
        world.regions[VERDANT].stockpile.goods = {}
    before = [c.treasury for c in world.civilizations]
    _tick(world, result)
    frame = world.transaction_receipts.public_purchases
    assert frame.complete and frame.available and frame.rows == []
    assert [c.treasury for c in world.civilizations] == before
    assert frame.observed_purchases == 0


def test_actual_two_purchase_overflow_retains_authoritative_flows_and_full_scalar_totals():
    world, result, _, _, _ = _scenario("same_realm")
    _target(world, VERDANT, 12.0)
    world.transaction_receipts.max_rows = 1
    before = world.civilizations[THORNWALL].treasury
    _tick(world, result)
    purchases = [f for f in world.grain_reserves.flows if f.kind == BOUGHT]
    assert len(purchases) == 2
    frame = world.transaction_receipts.public_purchases
    assert frame.available and not frame.complete and frame.dropped_rows == 1
    assert frame.duplicate_keys == 0 and len(frame.rows) == 1
    assert frame.observed_purchases == 2
    assert frame.counters["buyer_paid"] == sum(f.cost for f in purchases)
    assert before-world.civilizations[THORNWALL].treasury == sum(f.cost for f in purchases)


def test_reversed_public_clock_rejects_before_journal_mutation():
    world, result, _, _, _ = _scenario()
    inputs = _basis(world, result)
    _tick(world, result)
    before = world.transaction_receipts.model_dump_json()
    world.turn -= 1
    with pytest.raises(ValueError, match="ahead of the world"):
        P.capture_public_purchases(world, **inputs)
    assert world.transaction_receipts.model_dump_json() == before
