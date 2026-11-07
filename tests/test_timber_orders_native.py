"""Constructed A4-3 dispatch/delivery contract on the real compiled extension.

This is a native payment/physical custody regression, not a natural activation
or held-screen claim. A development census supplies an actual adult merchant;
only commons timber and public treasuries are explicitly endowed for the test.
"""
from __future__ import annotations
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def test_actual_native_carrier_purchase_escrow_delivery_and_refund_close(request):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.world_gen import generate_world
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.timber_orders_state import TimberOrdersState
    from chronicler.timber_supply_state import TimberSupplyState
    from chronicler.repair_projects_state import RepairProjectsState
    from chronicler.local_budgets_state import LocalBudgetState
    from chronicler.timber_stock_state import TimberStockState
    from chronicler.grain_reserves import set_grain_reserves_enabled
    from chronicler.grain_storage import enable_storage
    from chronicler import timber_orders as T, timber_supply as TS, titled_trade as TT, money as M

    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    request.addfinalizer(bridge.close)
    sim = bridge._sim
    people = TT._people(sim.get_snapshot())
    edges, _ = TT._graph(world)
    choices = sorted((aid, origin, dest) for aid, (origin, occupation, age, wealth) in people.items()
        if occupation == TT.MERCHANT and age >= TT.ADULT_AGE and wealth >= .2
        for start, dest in edges if start == origin and world.regions[origin].controller != world.regions[dest].controller)
    assert choices, "the development census must provide a cross-polity adult merchant"
    holder, origin, dest = choices[0]
    seller, payer = T._controller(world, origin), T._controller(world, dest)
    assert seller != payer and edges[origin, dest][1] <= 0
    world.turn = 2
    state, supply = TimberOrdersState(), TimberSupplyState()
    world.livelihoods = LivelihoodsState(timber_orders=state, timber_supply=supply,
        repair_projects=RepairProjectsState(), local_budgets=LocalBudgetState(),
        timber_stock=TimberStockState())
    set_grain_reserves_enabled(world, True)
    enable_storage(world)
    world.regions[origin].stockpile.goods["timber"] = 10.0
    for civ in world.civilizations:
        civ.treasury = 100
    opening_wealth = TT._balances(sim, [holder])[holder]
    opening_destination_timber = world.regions[dest].stockpile.goods.get("timber", 0.0)

    def total_money():
        return (sum(c.treasury for c in world.civilizations) + sum(state.book.carry.values()) / 1000
                + TT._balances(sim, [holder])[holder] + sum(o.cash for o in state.orders + state.closed) / 1000)

    opening_money = total_money()
    t = T._begin(world, sim)
    order = T.dispatch(world, state, t, sim, origin, dest, holder, [origin, dest], 200, (1, 1000), 2)
    assert order is not None and order.purchase_milli == 200
    assert M.PURPOSES["timber_purchase"] not in (8, 9)
    assert M.PURPOSES["timber_freight"] not in (8, 9)
    assert TT._balances(sim, [holder])[holder] == pytest.approx(opening_wealth - .2, abs=2e-5)
    assert world.regions[origin].stockpile.goods["timber"] == pytest.approx(9.8)
    assert world.civilizations[payer].treasury == 99 and order.cash == 1000
    assert state.book.carry[f"{seller}:timber_purchase"] == 200
    assert total_money() == pytest.approx(opening_money, abs=2e-5)
    assert T.dispatch(world, state, t, sim, origin, dest, holder, [origin, dest], 200, (1, 1000), 2) is None

    world.turn = 3
    TS._begin(world, supply, sim)
    T.phase10_before_reserves(world, None, None, bridge)
    assert order.status == "closed" and order.outcome == "delivered"
    assert order.delivered_milli == 198 and order.lost_milli == 2
    assert supply.store[dest] == pytest.approx(.198)
    assert world.regions[dest].stockpile.goods.get("timber", 0.0) == opening_destination_timber
    assert order.cash == 0 and order.credited_milli > 0
    assert order.credited_milli + order.refunded_milli == order.escrowed_milli == 1000
    assert TT._balances(sim, [holder])[holder] == pytest.approx(opening_wealth - .2 + order.credited_milli / 1000, abs=2e-5)
    assert state.book.carry[f"{payer}:timber_escrow"] == order.refunded_milli
    assert total_money() == pytest.approx(opening_money, abs=2e-5)
    T.phase10(world, None, None, bridge)
    TS.phase10(world, None, None, bridge)
    T.check_order(order)
    M.check_book(state.book)
    TS.check_store(next(row for row in supply.stores if row.region == dest))
    assert state.frame["events"][0]["kind"] == "delivered"
