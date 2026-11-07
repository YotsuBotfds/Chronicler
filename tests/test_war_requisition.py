"""D4 physical debits, capacity, custody, restitution and exact state restore.

Constructed unit worlds; no held cohort is used by these tests.
"""
from __future__ import annotations
import pickle
from types import SimpleNamespace
import pytest
from chronicler import war_requisition as WR
from chronicler.war_requisition_state import WarRequisitionState
from chronicler.war.common import build_graph
from chronicler.war.occupation import _requisition
from tests.war_fixtures import war_world, start_war, place_army


def _world(mode="transfer"):
    world = war_world()
    world.agent_mode = "hybrid"
    # Root integrates this field into LivelihoodsState; the lane's tests use
    # the same pure-data state without concurrently editing shared schemas.
    from chronicler.livelihoods_state import LivelihoodsState
    world.livelihoods = LivelihoodsState()
    object.__setattr__(world.livelihoods, "war_requisition", WarRequisitionState(mode=mode))
    ctx, war = start_war(world)
    return world, ctx, war


def test_requisition_debits_once_and_converts_food_to_existing_army_kits():
    world, _, war = _world()
    region = world.region_map["Crag"]
    region.stockpile.goods = {"grain": 10.0, "fish": 5.0, "timber": 8.0}
    army = place_army(world, "A", "Crag", 10, war.war_key)
    army.rations = 0
    _requisition(region, .8, world, cause="occupation", actor=world.civilizations[0])
    assert region.stockpile.goods == {"grain": 8.0, "fish": 4.0, "timber": 8.0}
    assert army.rations == 6
    state = WR._state(world)
    row = state.events[-1]
    assert row["removed_milli"] == 3000
    assert row["removed_milli"] == sum(a["rations"] for a in row["allocations"]) * 500 + row["destroyed_milli"]
    # A distinct second event has a new physical debit. No multiplier is
    # inferred later from last_conquered_turn.
    _requisition(region, .8, world, cause="occupation", actor=world.civilizations[0])
    assert state.counters["events"] == 2
    assert army.rations == 10  # 2.4 food => four whole kits; 0.4 explicitly lost
    assert state.events[-1]["destroyed_milli"] == 400


def test_full_army_or_absent_actor_records_destruction_without_minting():
    world, _, war = _world()
    region = world.region_map["Crag"]
    region.stockpile.goods = {"grain": 10.0}
    army = place_army(world, "A", "Crag", 3, war.war_key)
    old = army.rations
    _requisition(region, .8, world, cause="siege", actor=world.civilizations[0])
    assert army.rations == old
    assert WR._state(world).events[-1]["destroyed_milli"] == 2000
    _requisition(region, .8, world, cause="siege", actor=None)
    assert army.rations == old


def test_real_supply_never_duplicates_requisition_and_second_tick_is_refused():
    world, _, war = _world()
    region = world.region_map["Avalon"]
    region.stockpile.goods = {"grain": 2.25}
    army = place_army(world, "A", "Avalon", 3, war.war_key)
    army.rations = 15  # capacity18, only room for 3
    graph, idx, _ = build_graph(world)
    assert WR.supply(world, army, 9, 0, (idx["Avalon"],), graph, idx["Avalon"]) == (3, 0)
    assert region.stockpile.goods["grain"] == .75
    with pytest.raises(RuntimeError, match="already executed"):
        WR.supply(world, army, 9, 0, (idx["Avalon"],), graph, idx["Avalon"])


def test_no_physical_food_means_no_generated_refill_in_transfer_mode():
    world, _, war = _world()
    army = place_army(world, "A", "Avalon", 3, war.war_key)
    army.rations = 0
    graph, idx, _ = build_graph(world)
    assert WR.supply(world, army, 9, 0, (0, 1), graph, 0) == (0, 0)


def test_cost_only_pays_physical_cost_and_retains_legacy_ration_credit():
    world, _, war = _world("cost_only")
    region = world.region_map["Avalon"]
    region.stockpile.goods = {"grain": 4.0}
    army = place_army(world, "A", "Avalon", 3, war.war_key)
    army.rations = 0
    graph, _, _ = build_graph(world)
    assert WR.supply(world, army, 9, 0, (0,), graph, 0) == (9, 0)
    assert region.stockpile.goods["grain"] == 0.0
    enemy = world.region_map["Crag"]
    enemy.stockpile.goods = {"grain": 10.0}
    army.region = "Crag"
    _requisition(enemy, .8, world, cause="siege", actor=world.civilizations[0])
    assert army.rations == 0
    assert WR._state(world).events[-1]["destroyed_milli"] == 2000


def test_disabled_uses_legacy_supply_and_does_not_touch_physical_food():
    world, _, war = _world()
    state = WR._state(world)
    state.enabled = False
    army = place_army(world, "A", "Avalon", 3, war.war_key)
    world.regions[0].stockpile.goods = {"grain": 5.0}
    assert WR.supply(world, army, 9, 1, (0,), {}, 0) == (9, 1)
    assert world.regions[0].stockpile.goods["grain"] == 5.0
    assert state.counters == {}


def test_cargo_needs_actual_hostile_custody_then_closes_once(monkeypatch):
    from chronicler.titled_trade_state import Shipment, TitledTradeState
    from chronicler.titled_trade import _Turn
    world, _, war = _world()
    ship = Shipment(id=0, holder=7, carrier=7, origin=2, dest=0, path=[2, 1, 0],
                    controllers=["B", "A"], dispatched_turn=0,
                    cargo=[1000, 0, 0, 0, 0], cargo_open=[1000, 0, 0, 0, 0], cost_milli=2000)
    tt = TitledTradeState(shipments=[ship])
    t = _Turn(0, None)
    assert not WR.seize_cargo(world, ship, tt, t)
    army = place_army(world, "A", "Crag", 3, war.war_key)
    army.rations = 0
    assert WR.seize_cargo(world, ship, tt, t)
    assert army.rations == 2 and not tt.shipments
    assert ship.outcome == "seized" and ship.losses == {"war_seizure": 1000}
    claim = WR._state(world).claims[0]
    assert (claim.owner, claim.payer, claim.due_milli, claim.source) == (7, 0, 2000, "cargo")
    # Trade loop removes closed cargo. Calling seizure on closed cargo is
    # rejected before any second transfer.
    assert not WR.seize_cargo(world, ship, tt, t)


def test_claim_ids_and_guards_survive_exact_pickle_restore():
    world, _, _ = _world()
    state = WR._state(world)
    WR._claim(world, state, 0, 7, 0, 1500, "cargo")
    WR._claim(world, state, 0, 7, 0, 500, "cargo")
    state.supply_turn, state.supplied = 0, ["army-1:tick"]
    restored = pickle.loads(pickle.dumps(state))
    assert restored.model_dump() == state.model_dump()
    assert restored.claims[0].id == 0 and restored.next_claim == 1
    assert restored.claims[0].due_milli == 2000
    WR.on_pool_reset(SimpleNamespace(livelihoods=SimpleNamespace(war_requisition=restored)))
    assert restored.claims[0].status == "pool_reset"
    assert restored.counters["claims_lapsed_milli"] == 2000


def test_restitution_uses_payer_cash_ceiling_refusals_stay_due(monkeypatch):
    from chronicler import money as M
    from chronicler.wealth_accounting_state import MONEY_PURPOSE_CHANNELS
    from tests.test_money import FakeSim
    # Shared purpose table is integrated by lead with the native build.
    monkeypatch.setitem(M.PURPOSES, "restitution", 10)
    if "restitution" not in M.NATIVE_PURPOSES:
        monkeypatch.setattr(M, "NATIVE_PURPOSES", (*M.NATIVE_PURPOSES, "restitution"))
    if "restitution" not in M.TREASURY_AGENT_PURPOSES:
        monkeypatch.setattr(M, "TREASURY_AGENT_PURPOSES", (*M.TREASURY_AGENT_PURPOSES, "restitution"))
    monkeypatch.setitem(MONEY_PURPOSE_CHANNELS, "restitution", "restitution")
    world, _, _ = _world()
    world.civilizations[0].treasury = 1
    state = WR._state(world)
    WR._claim(world, state, 0, 7, 0, 1500, "cargo")
    sim = FakeSim({7: 99.75}, purposes=M.NATIVE_PURPOSES)
    WR._settle(world, state, sim, None)
    assert sim.wealth[7] == 100.0
    assert state.claims[0].paid_milli == 250
    assert state.claims[0].status == "open"
    assert world.civilizations[0].treasury == 0
    assert state.book.carry["0:restitution"] == 750
    world.turn = 1
    sim.wealth[7] = 90.0
    WR._settle(world, state, sim, None)
    assert state.claims[0].paid_milli == 1000
    assert sim.wealth[7] == 90.75
    assert state.book.carry == {}


def test_native_service_uses_actual_meal_and_preserves_released_ids_for_this_tick():
    world, _, war = _world()
    army = place_army(world, "A", "Avalon", 4, war.war_key, roster=[(7, 0), (8, 0), (9, 1), (10, 1)])
    army.rations = 2
    assert WR.enlisted_service_rows(world) == [(7, 0.0), (8, 0.0), (9, 0.0), (10, 0.0)]
    army.rations -= 2
    WR.note_consumption(world, army, 2, 4)
    assert WR.enlisted_service_rows(world, after_logistics=True) == [(7, .5), (8, .5), (9, .5), (10, .5)]
    assert army.rations == 0
    army.roster = [(7, 0), (8, 0)]
    army.soldiers = 2
    # Repeated input build is idempotent and cannot eat another meal.
    assert WR.enlisted_service_rows(world, after_logistics=True) == [(7, .5), (8, .5), (9, .5), (10, .5)]
    world.turn += 1
    assert WR.enlisted_service_rows(world) == [(7, .5), (8, .5)]
    assert WR.enlisted_service_rows(world, after_logistics=True) == [(7, 0.0), (8, 0.0)]


def test_occupation_owned_food_liability_matches_actual_claim_debit():
    from tests.test_household_retail_war import _pilot
    from tests.test_household_retail import Harness
    h = Harness()
    reg = _pilot(h)
    h.world.turn += 1
    old = dict(reg.claims)
    state = WarRequisitionState()
    object.__setattr__(h.world.livelihoods, "war_requisition", state)
    region = h.world.regions[reg.region]
    actor = next(c for c in h.world.civilizations if c.name != region.controller)
    _requisition(region, .8, h.world, cause="occupation", actor=actor)
    expected = {aid: (amount - reg.claims.get(aid, 0)) * 2 for aid, amount in old.items()}
    assert {c.owner: c.due_milli for c in state.claims} == expected
    assert sum(expected.values()) == state.counters["claims_due_milli"]
    assert state.events[-1]["owned_milli"] == sum(expected.values()) // 2


def test_timber_seizure_only_records_acquisition_liability_without_creating_food():
    world, _, war = _world()
    army = place_army(world, "A", "Crag", 3, war.war_key)
    army.rations = 0
    WR.note_cargo_seizure(world, owner=7, region=2, actor="A", value_milli=1200,
                         shipment=4, quantity_milli=5000)
    state = WR._state(world)
    assert army.rations == 0
    assert state.claims[0].source == "timber" and state.claims[0].due_milli == 1200
    assert state.events[-1]["package"] == "timber_orders"
    assert state.events[-1]["quantity_milli"] == 5000


def test_phase5_recruit_keeps_civilian_meal_and_starts_army_meals_next_turn():
    world, ctx, war = _world()
    assert WR.enlisted_service_rows(world) == []  # Phase 2 census before muster
    army = place_army(world, "A", "Avalon", 3, war.war_key, roster=[(1, 0), (2, 0), (3, 0)])
    old_rations = army.rations
    assert WR.enlisted_ids(world) == []
    assert WR.ration_demand(world, army, 3) == 0
    assert WR.enlisted_service_rows(world, after_logistics=True) == []
    assert army.rations == old_rations  # before-tick input never consumes a meal
    world.turn += 1
    assert WR.enlisted_service_rows(world) == [(1, 0.0), (2, 0.0), (3, 0.0)]
    assert WR.ration_demand(world, army, 3) == 3


def test_post_logistics_food_input_requires_a_phase2_census():
    world, _, _ = _world()
    with pytest.raises(RuntimeError, match="Phase 2"):
        WR.enlisted_service_rows(world, after_logistics=True)


def test_pool_replacement_cannot_give_a_reused_id_an_old_army_meal():
    world, _, war = _world()
    army = place_army(world, "A", "Avalon", 1, war.war_key, roster=[(7, 0)])
    army.rations = 4
    WR.enlisted_service_rows(world)
    WR.note_consumption(world, army, 1, 1)
    state = WR._state(world)
    state.supply_turn, state.supplied = world.turn, [army.army_id + ":tick"]
    canceled = []
    state._sim = SimpleNamespace(cancel_enlisted_service=lambda: canceled.append(True))
    WR.on_pool_reset(world)
    assert canceled == [True] and state._sim is None
    assert state.census_turn is state.feeding_turn is state.supply_turn is None
    assert not state.census_ids and not state.fed_ids and not state.feeding and not state.supplied
    # A reconstructed roster can reuse 7; its predecessor's meal is gone.
    assert WR.enlisted_service_rows(world) == [(7, 0.0)]
    assert army.rations == 4  # physical stores have a separate authority
