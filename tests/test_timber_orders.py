"""A4-3 real stock and escrow lifecycle with a keyed native-contract stand-in."""
from types import SimpleNamespace as NS
import pickle
import pyarrow as pa
import pytest
from chronicler import money as M, timber_orders as T, timber_supply as TS, titled_trade as TT
from chronicler.timber_orders_state import TimberOrdersState
from tests.test_money import FakeSim, _world

_measured_needs = T._needs

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


def test_configuration_uses_supplied_mode_before_world_runtime_is_synchronized():
    from types import SimpleNamespace as NS
    world = NS(agent_mode="off", livelihoods=NS(timber_orders=None,
        timber_supply=NS(enabled=True), local_budgets=NS(enabled=True)))
    T.set_timber_orders_enabled(world, True, agent_mode="hybrid")
    assert world.livelihoods.timber_orders.enabled


def test_rules2_trade_gate_blocks_unknown_market_before_stock_or_escrow_moves(lane):
    world,state,sim,_ = lane
    world.livelihoods.adaptive_livelihoods = NS(enabled=True,rules="2",mode="adapt",trade_experience=[],counters={})
    sim.usable_trade_destinations = lambda ids,turn: [(aid,[]) for aid in ids]
    assert buy(lane) is None
    assert not state.orders and state.next_order == 0 and sim.wealth[17] == 10
    assert world.regions[0].stockpile.goods["timber"] == 10
    assert [c.treasury for c in world.civilizations] == [50,50]
    sim.usable_trade_destinations = lambda ids,turn: [(aid,[1]) for aid in ids]
    assert buy(lane) is not None


def test_rules2_personal_timber_route_failure_cools_down_known_destination(lane,monkeypatch):
    world,state,sim,_ = lane
    memory = world.livelihoods.adaptive_livelihoods = NS(enabled=True,rules="2",mode="adapt",trade_experience=[],counters={})
    sim.usable_trade_destinations = lambda ids,turn: [(aid,[1]) for aid in ids]
    order = buy(lane)
    assert order is not None
    monkeypatch.setattr(TT,"_graph",lambda *_: ({},set()))
    world.turn += 1
    T.phase10_before_reserves(world,None,None,NS(_sim=sim))
    assert order.outcome == "route_lost"
    assert memory.trade_experience == [{"turn":3,"id":17,"region":1,"kind":"shipment","outcome":"route_lost","cause":None,"shipment":order.id,"package":"timber_orders"}]
    world.turn += 1
    monkeypatch.setattr(TT,"_graph",lambda *_: ({(0,1):(False,-1.0)},set()))
    assert buy(lane) is None
    assert memory.counters["trade_personal_return_refusal"] == 1
    # Record-only observes the failure but leaves the dispatch decision unchanged.
    memory.mode = "record_only"
    assert buy(lane) is not None


def test_b3_and_rs2_refusals_share_one_regional_gap_and_one_inflight_credit(lane, monkeypatch):
    from chronicler.timber_supply_state import NeedRow
    world,state,sim,_ = lane
    order=buy(lane)
    row=NeedRow(region=1,civ=1,want=2,free=0,store=0,in_transit=0,gap=2,status="refused",reason="no_forest")
    world.livelihoods.timber_supply=NS(_turn=NS(turn=world.turn,needs=[row]),frame_turn=None)
    infrastructure=world.livelihoods.infrastructure_condition=NS(enabled=True,timber_needs_turn=world.turn,timber_needs=[NS(region=1,civ=1,gap=3,status="refused",reason="no_forest")])
    assert _measured_needs(world)==[(1,1,pytest.approx(5-order.cargo_milli*.99/1000))]
    infrastructure.timber_needs_turn-=1
    assert _measured_needs(world)==[(1,1,pytest.approx(2-order.cargo_milli*.99/1000))]
    infrastructure.timber_needs_turn=world.turn;infrastructure.enabled=False
    assert _measured_needs(world)==[(1,1,pytest.approx(2-order.cargo_milli*.99/1000))]
    world.livelihoods.timber_supply._turn=None
    assert _measured_needs(world)==[]
    infrastructure.enabled=True
    assert _measured_needs(world)==[(1,1,pytest.approx(3-order.cargo_milli*.99/1000))]


def test_actual_arrival_is_not_immediately_reordered_from_prearrival_need(lane):
    from chronicler.timber_supply_state import NeedRow
    world,state,sim,store=lane
    order=buy(lane)
    world.livelihoods.timber_supply=NS(_turn=NS(turn=world.turn,needs=[
        NeedRow(region=1,civ=1,want=2,free=0,store=0,in_transit=0,gap=2,status="refused",reason="no_forest")]),frame_turn=None)
    assert _measured_needs(world)[0][2] == pytest.approx(.02)
    T._close(world,state,state._turn,order,"delivered",sim)
    assert store=={1:2.0} and _measured_needs(world)==[]
    T.phase10(world,None,None,NS(_sim=sim))
    assert _measured_needs(world)==[]  # Closing a frame cannot erase arrival relief.
    assert pickle.loads(pickle.dumps(state))._turn is None


def test_origin_infrastructure_need_is_protected_from_export(lane,monkeypatch):
    world,state,sim,_=lane
    monkeypatch.setattr(TS,"_works_wants",lambda *_:[(0,10.0,[5])],raising=False)
    assert buy(lane) is None
    assert world.regions[0].stockpile.goods["timber"]==10 and not state.orders
    monkeypatch.setattr(TS,"_works_wants",lambda *_:[(0,9.0,[5])],raising=False)
    order=buy(lane)
    assert order.cargo_milli==1000 and world.regions[0].stockpile.goods["timber"]==9


def test_order_requires_current_cross_civilization_seller_and_payer(lane):
    world,state,sim,_=lane
    world.regions[1].controller="C0"
    assert buy(lane) is None
    assert not state.orders and world.regions[0].stockpile.goods["timber"]==10


def _road_stake_world():
    from tests.test_infrastructure_condition import _pl1_world, ROADS
    from chronicler.local_budgets_state import LocalBudgetState
    world = _pl1_world(work_region=0, kind=ROADS)
    world.livelihoods.local_budgets = LocalBudgetState()
    world.livelihoods.timber_orders = TimberOrdersState(prices={1: (world.turn - 1, 1000)})
    return world


def test_timber_proposal_values_bounded_road_worker_time_never_timber_as_food(monkeypatch):
    from chronicler import infrastructure_condition as I
    world = _road_stake_world()
    monkeypatch.setattr(T, "_needs", lambda _: [(0, 0, 2.0)])
    (proposal,) = T.BUDGET_PROVIDER.proposals(world, 0, NS(turn=world.turn))
    assert proposal["expected"] == 2.0 and proposal["unit"] == "timber dispatched"
    assert proposal["relief"] == {"patricians": 4.0}
    assert "commons" not in proposal["relief"]
    assert proposal["detail"]["potential_repair_work"] <= I.road_work_burden(world, 0)
    assert "repair and service restoration unproved" in proposal["detail"]["promise"]
    road = next(w for w in world.livelihoods.infrastructure_condition.works if w.kind == "roads")
    road.scope = road.delivered + .1
    assert T.BUDGET_PROVIDER.proposals(world, 0, NS(turn=world.turn))[0]["relief"]["patricians"] == pytest.approx(.1)
    assert T.BUDGET_PROVIDER.proposals(world, 0, NS(turn=world.turn - 1)) == []
    assert T.BUDGET_PROVIDER.proposals(world, 1, NS(turn=world.turn)) == []


def test_irrigation_input_claims_precede_road_stake_without_becoming_food_relief(monkeypatch):
    from chronicler import infrastructure_condition as I
    from chronicler.models import Infrastructure, InfrastructureType
    world = _road_stake_world()
    world.regions[0].infrastructure.append(Infrastructure(type=InfrastructureType.IRRIGATION,
        built_turn=0, builder_civ=world.civilizations[0].name))
    I.reconcile(world)
    irrigation = next(a for a in world.livelihoods.infrastructure_condition.assets if a.kind == "irrigation")
    irrigation.condition = .2
    I.phase10_before_reserves(world, None, None, None)
    # The first timber unit serves irrigation. Only the next unit can support
    # two road worker-turns. No speculative irrigation food benefit is added.
    assert T.potential_repair_work(world, 0, [(0, 1.0)], NS(turn=world.turn)) == {}
    assert T.potential_repair_work(world, 0, [(0, 2.0)], NS(turn=world.turn)) == {0: 2.0}
    world.livelihoods.infrastructure_condition.mode = "record_only"
    assert T.potential_repair_work(world, 0, [(0, 2.0)], NS(turn=world.turn)) == {}


def test_workshop_stake_uses_current_idle_work_and_existing_condition_conversion(monkeypatch):
    from tests.test_repair_projects import _world
    from chronicler import repair_projects as R
    world = _world(granary=1.0, site=.1, policy="neglect")
    R.phase10_before_reserves(world, None, None, None)
    workshops = world.livelihoods.workshops
    workshops.frame_turn, workshops.frame = world.turn, [NS(site=0, region=1, work_available=.6, allocated=0.0)]
    project = next(p for p in world.livelihoods.repair_projects.projects if p.kind == "workshop")
    value = T.potential_repair_work(world, 0, [(1, 20.0)], NS(turn=world.turn))[1]
    assert 0 < value <= min(.6, project.scope - project.delivered)
    workshops.frame_turn -= 1
    assert T.potential_repair_work(world, 0, [(1, 20.0)], NS(turn=world.turn)) == {}


def test_granary_only_gap_has_no_invented_food_or_idle_work_value():
    from tests.test_repair_projects import _world
    from chronicler import repair_projects as R
    world = _world(granary=.2, policy="neglect")
    R.phase10_before_reserves(world, None, None, None)
    assert any(p.kind == "granary" for p in world.livelihoods.repair_projects.projects)
    assert T.potential_repair_work(world, 0, [(0, 10.0)], NS(turn=world.turn)) == {}


def test_unpromised_destination_cannot_use_another_regions_timber_envelope(lane, monkeypatch):
    import chronicler.local_budgets as LB
    world, state, sim, _ = lane
    monkeypatch.setattr(T, "_needs", lambda _: [(1, 1, 2.0)])
    calls = []
    def authority(world, civ, service, **kwargs):
        calls.append((civ, service, kwargs))
        return 0 if kwargs.get("region") == 1 else 10
    monkeypatch.setattr(LB, "envelope", authority)
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert calls == [(1, T.SERVICE, {"region": 1})]
    assert not state.orders and not state.book.settled and world.regions[0].stockpile.goods["timber"] == 10.0


def _plan_needs(world, state, monkeypatch, needs):
    from chronicler import local_budgets as LB
    state.prices[0] = (world.turn - 1, 1000)
    monkeypatch.setattr(T, "_needs", lambda _: needs)
    monkeypatch.setattr(LB, "envelope", lambda *_args, **_kwargs: 10)


@pytest.mark.parametrize("needs", [[], [(1, 1, 2.0)]])
def test_no_dispatch_builds_no_unused_population_projection(lane, monkeypatch, needs):
    from chronicler import adaptive_livelihoods as A, local_budgets as LB
    world, state, sim, _ = lane
    visits = []

    class CountedPeople(dict):
        def items(self):
            visits.append(len(self))
            return super().items()

    sim.wealth = {aid: 10.0 for aid in range(100)}
    people = CountedPeople({aid: (0, TT.MERCHANT, 30, 10.0) for aid in sim.wealth})
    monkeypatch.setattr(TT, "_people", lambda _: people)
    monkeypatch.setattr(A, "trade_destinations", lambda *_: None)
    monkeypatch.setattr(T, "_needs", lambda _: needs)
    monkeypatch.setattr(LB, "envelope", lambda *_args, **_kwargs: 0)
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert not state.orders and not state.book.settled
    assert sim.wealth == {aid: 10.0 for aid in range(100)}
    assert [c.treasury for c in world.civilizations] == [50, 50]
    assert world.regions[0].stockpile.goods["timber"] == 10.0
    assert visits == []


def test_unknown_market_candidates_preserve_refusals_without_population_rescans(lane, monkeypatch):
    world, state, sim, _ = lane
    sim.wealth = {aid: 10.0 for aid in range(100)}
    memory = world.livelihoods.adaptive_livelihoods = NS(
        enabled=True, rules="2", mode="adapt", trade_experience=[], counters={})
    sim.usable_trade_destinations = lambda ids, turn: [(aid, []) for aid in ids]
    _plan_needs(world, state, monkeypatch, [(1, 1, 2.0)])
    calls, original = [], TT._people

    def measured(snapshot):
        calls.append(snapshot.num_rows)
        return original(snapshot)

    monkeypatch.setattr(TT, "_people", measured)
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert memory.counters["trade_unknown_destination"] == 100
    assert not state.orders and not state.book.settled
    assert sim.wealth == {aid: 10.0 for aid in range(100)}
    assert [c.treasury for c in world.civilizations] == [50, 50]
    assert world.regions[0].stockpile.goods["timber"] == 10.0
    # Measured production hotspot: the old planner rebuilt the full population
    # once for each rejected candidate (101 reads here).  This bound permits
    # one initial and one post-arrival refresh, not an O(candidates*people) scan.
    assert len(calls) <= 2


def test_planning_reads_wallet_after_same_turn_freight_credit(lane, monkeypatch):
    world, state, sim, _ = lane
    old = buy(lane)
    assert old is not None
    sim.wealth[17] = 0.0
    world.turn += 1
    _plan_needs(world, state, monkeypatch, [(1, 1, 2.0)])
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert old.status == "closed" and old.credited_milli > 2000
    assert len(state.orders) == 1
    new = state.orders[0]
    assert new.holder == 17 and new.purchase_milli == 2000
    assert sim.wealth[17] == pytest.approx((old.credited_milli - new.purchase_milli) / 1000)
    T.check_order(old)
    T.check_order(new)
    M.check_book(state.book)


def test_planning_eligibility_facts_never_supply_a_stale_wallet(lane):
    world, state, sim, _ = lane
    physical = {17: (0, TT.MERCHANT, 30)}
    sim.wealth[17] = 0.0
    assert buy(lane, _planning_people=physical) is None
    assert not state.orders and not state.book.settled
    assert world.regions[0].stockpile.goods["timber"] == 10.0
    assert [c.treasury for c in world.civilizations] == [50, 50]


@pytest.mark.parametrize("region,occupation,age", [(1, TT.MERCHANT, 30), (0, 0, 30), (0, TT.MERCHANT, 2)])
def test_accepted_planned_candidate_rechecks_current_native_eligibility(lane, region, occupation, age):
    world, state, sim, _ = lane
    physical = {17: (0, TT.MERCHANT, 30)}
    sim.get_snapshot = lambda: pa.record_batch({"id": [17], "wealth": [10.0], "region": [region],
                                               "occupation": [occupation], "age": [age]})
    assert buy(lane, _planning_people=physical) is None
    assert not state.orders and not state.book.settled
    assert world.regions[0].stockpile.goods["timber"] == 10.0
    assert [c.treasury for c in world.civilizations] == [50, 50]


def test_multiple_destinations_keep_live_stock_wallets_and_carrier_booking(lane, monkeypatch):
    world, state, sim, _ = lane
    world.regions.append(NS(name="OtherTown", controller="C1", stockpile=NS(goods={"timber": 0.0}),
                            occupied_by=None, last_conquered_turn=None))
    world.regions[0].stockpile.goods["timber"] = 3.0
    sim.wealth[18] = 10.0
    edges = {(0, 1): (False, -1.0), (0, 2): (False, -1.0)}
    monkeypatch.setattr(TT, "_graph", lambda *_: (edges, set()))
    _plan_needs(world, state, monkeypatch, [(1, 1, 2.0), (2, 1, 2.0)])
    calls, original = [], TT._bfs

    def measured(graph, origin):
        calls.append(origin)
        return original(graph, origin)

    monkeypatch.setattr(TT, "_bfs", measured)
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert [(o.holder, o.dest, o.cargo_milli) for o in state.orders] == [(17, 1, 2000), (18, 2, 1000)]
    assert sim.wealth == {17: 8.0, 18: 9.0}
    assert world.regions[0].stockpile.goods["timber"] == 0.0
    assert [c.treasury for c in world.civilizations] == [53, 45]
    assert calls == [0]
    for order in state.orders:
        T.check_order(order)
    M.check_book(state.book)


def test_later_turn_rebuilds_route_and_dated_price_facts(lane, monkeypatch):
    world, state, sim, _ = lane
    world.regions.append(NS(name="Waystation", controller="C1", stockpile=NS(goods={"timber": 0.0}),
                            occupied_by=None, last_conquered_turn=None))
    _plan_needs(world, state, monkeypatch, [(1, 1, 2.0)])
    sim.wealth[17] = 0.0
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert not state.orders
    world.turn += 1
    state.prices[0] = (world.turn - 1, 2000)
    sim.wealth[17] = 10.0
    monkeypatch.setattr(TT, "_graph", lambda *_: ({(0, 2): (False, -1.0), (2, 1): (False, -1.0)}, set()))
    T.phase10_before_reserves(world, None, None, NS(_sim=sim))
    assert len(state.orders) == 1
    order = state.orders[0]
    assert order.path == [0, 2, 1] and order.price_turn == world.turn - 1
    assert order.purchase_milli == 4000 and sim.wealth[17] == 6.0
    T.check_order(order)
