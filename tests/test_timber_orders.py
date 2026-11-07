"""A4-3 real stock and escrow lifecycle with a keyed native-contract stand-in."""
from types import SimpleNamespace as NS
import pickle
import pyarrow as pa
import pytest
from chronicler import money as M, timber_orders as T, timber_supply as TS, titled_trade as TT
from chronicler.timber_orders_state import TimberOrdersState
from tests.test_money import FakeSim, _world

class CarrierSim(FakeSim):
    def get_snapshot(self):
        ids = sorted(self.wealth)
        return pa.record_batch({"id": ids, "wealth": [self.wealth[i] for i in ids], "region": [0] * len(ids),
                                "occupation": [2] * len(ids), "age": [30] * len(ids)})
    def trip_agent_ids(self):
        return []
    def work_reservation_categories(self):
        return ["workshop", "learning", "apprentice", "repair", "trade"]
    def reserve_work(self, *args):
        pass
    def extend_paid_work(self, *args):
        pass
    def cancel_paid_work(self):
        pass
    def take_paid_work_receipt(self):
        return []
    def settle_pairs(self, *args):
        raise AssertionError("timber uses collections and escrow credits, not pairwise minting")

@pytest.fixture
def lane(monkeypatch):
    from chronicler import repair_projects as RP
    state = TimberOrdersState()
    world = _world((50, 50))
    world.turn, world.agent_mode = 2, "hybrid"
    world.regions = [NS(name="Forest", controller="C0", stockpile=NS(goods={"timber": 10.0}), occupied_by=None, last_conquered_turn=None),
                     NS(name="Town", controller="C1", stockpile=NS(goods={"timber": 0.0}), occupied_by=None, last_conquered_turn=None)]
    world.livelihoods = NS(timber_orders=state, titled_trade=None)
    world.war_state = NS(armies=[])
    sim = CarrierSim({17: 10.0})
    monkeypatch.setattr(RP, "_commitments", lambda *_: {})
    monkeypatch.setattr(TS, "_wants", lambda *_: {})
    monkeypatch.setattr(TS, "store_free", lambda *_: 0.0)
    monkeypatch.setattr(TT, "_graph", lambda *_: ({(0, 1): (False, -1.0)}, set()))
    monkeypatch.setattr(T, "_needs", lambda *_: [])
    store = {}
    monkeypatch.setattr(TS, "deliver_ordered_store", lambda _w, r, q: store.update({r: store.get(r, 0) + q}))
    return world, state, sim, store


def buy(lane, **kwargs):
    world, state, sim, _ = lane
    t = T._begin(world, sim)
    return T.dispatch(world, state, t, sim, 0, 1, 17, [0, 1], kwargs.pop("quantity", 2000), (1, 1000), kwargs.pop("budget", 10), **kwargs)


def test_real_stock_real_origin_payment_and_real_destination_escrow(lane):
    world, state, sim, _ = lane
    order = buy(lane)
    assert order.cargo_milli == 2000 and order.purchase_milli == 2000
    assert world.regions[0].stockpile.goods["timber"] == 8
    assert sim.wealth[17] == 8 and world.civilizations[0].treasury == 52
    assert world.civilizations[1].treasury == 47 and order.cash == 3000
    assert buy(lane) is None  # one title/carrier at a time
    T.check_order(order)
    assert state.next_order == 1


def test_delivery_credits_only_delivered_timbers_and_refunds_real_balance(lane):
    world, state, sim, store = lane
    order = buy(lane)
    world.turn += 1
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert order.status == "closed" and order.outcome == "delivered"
    assert order.delivered_milli == 1980 and order.lost_milli == 20
    assert store == {1: 1.98} and world.regions[1].stockpile.goods["timber"] == 0
    assert order.credited_milli == 1980 * order.sale_price_milli // 1000
    assert order.refunded_milli + order.credited_milli == order.escrowed_milli
    assert sim.wealth[17] == pytest.approx(8 + order.credited_milli / 1000)
    assert order.cash == 0
    T.check_order(order)


def test_ceiling_refusal_refunds_payer_instead_of_minting(lane):
    world, state, sim, store = lane
    order = buy(lane)
    sim.wealth[17] = 100
    world.turn += 1
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert order.credited_milli == 0 and order.refunded_milli == 3000
    assert world.civilizations[1].treasury == 50 and sim.wealth[17] == 100
    assert store[1] == 1.98
    M.check_book(state.book)


def test_cancelled_route_deposits_physical_cargo_locally_and_refunds_destination(lane, monkeypatch):
    world, state, sim, store = lane
    order = buy(lane)
    monkeypatch.setattr(TT, "_graph", lambda *_: ({}, {(0, 1)}))
    world.turn += 1
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert order.outcome == "route_lost" and order.deposited_milli == 2000
    assert world.regions[0].stockpile.goods["timber"] == 10
    assert world.civilizations[1].treasury == 50 and sim.wealth[17] == 8
    assert not store and order.credited_milli == 0
    T.check_order(order)


def test_whole_bill_refusal_leaves_every_balance_and_stock_unchanged(lane):
    world, state, sim, _ = lane
    assert buy(lane, budget=0) is None
    sim.wealth[17] = .001
    assert buy(lane) is None
    assert world.regions[0].stockpile.goods["timber"] == 10
    assert [c.treasury for c in world.civilizations] == [50, 50]
    assert not state.orders and state.next_order == 0 and state.book.settled == []


def test_exact_checkpoint_preserves_real_escrow_and_monotone_id(lane):
    world, state, sim, _ = lane
    order = buy(lane)
    clone = pickle.loads(pickle.dumps(state))
    assert clone.orders[0].model_dump() == order.model_dump() and clone._turn is None
    world.livelihoods.timber_orders = clone
    world.turn += 1
    T.on_pool_reset(world)
    assert clone.closed[0].outcome == "pool_reset" and clone.closed[0].cash == 0
    assert clone.next_order == 1 and not clone.orders and world.civilizations[1].treasury == 50


def test_unknown_escrow_is_rejected_before_native_mutation(lane):
    world, _state, sim, _ = lane
    bill = M.Bill(purpose="timber_freight", batch=1, phase="phase10", payer=M.escrow(99), lines=((M.agent(17), 1000),))
    with pytest.raises(M.MoneyError, match="escrow"):
        M.pay(world, bill, turn=world.turn, book=M.MoneyBook(), sim=sim, escrows={})
    assert sim.calls == 0


def test_same_or_future_price_is_rejected_before_stock_or_money(lane):
    world, state, sim, _ = lane
    with pytest.raises(RuntimeError, match="plan prices"):
        T.dispatch(world, state, T._begin(world, sim), sim, 0, 1, 17, [0, 1], 2000, (2, 1000), 10)
    assert state.book.settled == []


def test_divisible_order_stays_within_finite_envelope_and_merchant_cash(lane):
    world, state, sim, _ = lane
    order = buy(lane, budget=1)
    assert order.cash == 1000 and 0 < order.cargo_milli < 2000
    assert world.civilizations[1].treasury == 49
    assert state._turn.spent == {1: 1}


def test_refused_gap_subtracts_existing_orders_and_never_reorders_them(lane, monkeypatch):
    from chronicler.timber_supply_state import NeedRow
    world, state, _sim, _ = lane
    order = buy(lane)
    world.livelihoods.timber_supply = NS(_turn=NS(turn=world.turn, needs=[
        NeedRow(region=1,civ=1,want=2,free=0,store=0,in_transit=0,gap=2,status="refused",reason="no_forest")]), frame_turn=None)
    monkeypatch.undo()
    # Exactly the order already on the road counts as expected delivered timber.
    expected = order.cargo_milli * .99 / 1000
    needs = T._needs(world)
    assert len(needs) == 1 and needs[0][2] == pytest.approx(2 - expected)


def test_stock_commitments_and_origin_repair_need_are_never_bought(lane, monkeypatch):
    from chronicler import repair_projects as RP
    world, state, sim, _ = lane
    monkeypatch.setattr(RP, "_commitments", lambda *_: {"Forest": {"timber": 9.0}})
    monkeypatch.setattr(TS, "_wants", lambda *_: {0: 1.0})
    assert buy(lane) is None
    assert world.regions[0].stockpile.goods["timber"] == 10 and not state.orders


def test_war_seizes_timber_as_timber_and_records_value_liability(lane, monkeypatch):
    from chronicler import war_requisition as WR
    world, state, sim, store = lane
    order = buy(lane)
    noted = []
    monkeypatch.setattr(WR, "war_requisition_active", lambda *_: True)
    monkeypatch.setattr("chronicler.war.common.at_war", lambda *_: True)
    monkeypatch.setattr(WR, "note_cargo_seizure", lambda _world, **row: noted.append(row))
    world.war_state.armies = [NS(army_id=4, region="Forest",soldiers=20,civ="C1",phase="sieging",roster=[])]
    world.turn += 1
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert order.outcome == "seized" and order.deposited_milli == 2000
    assert world.regions[0].stockpile.goods["timber"] == 10 and not store
    assert noted == [dict(owner=17,region=0,actor="C1",value_milli=2000,shipment=0,goods="timber",quantity_milli=2000)]
    assert world.civilizations[1].treasury == 50
