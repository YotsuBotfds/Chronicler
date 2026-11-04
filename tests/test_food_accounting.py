"""Food observation contracts; synthetic ledgers are not native qualification."""
from dataclasses import replace
import json
import pickle
import random

import pytest

from chronicler.economy import EconomyResult
from chronicler.food_accounting import capture_food_accounting, public_opening, snapshot_fields
from chronicler.grain_reserves import open_granaries, tick_grain_reserves
from chronicler.grain_reserves_state import GrainReserveState, Granary
from chronicler.models import TurnSnapshot
from chronicler.regional_population import FoodWeights
from chronicler.turn_artifacts import TurnObservation


def setup(make_world, *, stock=0, demand=5, consumed=0, reserve=None):
    w = make_world(num_civs=1)
    w.agent_mode = 'hybrid'
    w.regions[0].population = 40
    w.civilizations[0].regions = [w.regions[0].name]
    e = EconomyResult(food_sufficiency={w.regions[0].name: min(2, stock / demand)},
                      market_demand={w.regions[0].name: (demand, 0, 0, 0)},
                      market_supply={w.regions[0].name: (stock, 0, 0, 0)})
    e.food_ledger[0] = (stock, 0, 0, 0, 0, stock, consumed, 0, 0, stock-consumed, demand, min(2, stock/demand))
    if reserve is not None:
        w.grain_reserves = GrainReserveState(granaries=[Granary(owner=0, grain=reserve, target=0)])
    return w,e,FoodWeights(w.turn,(10,),(0,))


@pytest.mark.parametrize('stock,demand,consumed', [(10,5,5),(0,5,0),(2,5,2)])
def test_native_drawdown_balance_is_not_sufficiency_or_model_population(make_world,stock,demand,consumed):
    w,e,weights = setup(make_world,stock=stock,demand=demand,consumed=consumed)
    before,rng = w.model_dump_json(),random.getstate()
    capture = capture_food_accounting(w,e,weights,None)
    row = capture.as_dict(w.turn+1)['regions'][0]
    assert row['native_count'] == 10 and row['model_population'] == 40
    assert row['native']['consumed'] == consumed
    assert row['native']['sufficiency'] == min(2,stock/demand)
    assert row['native']['balance_residual'] == 0
    assert w.model_dump_json() == before and random.getstate() == rng
    assert capture == pickle.loads(pickle.dumps(capture))


def test_public_relief_does_not_rewrite_native_consumption_and_balances_separately(make_world):
    w,e,weights = setup(make_world,stock=2,consumed=2,reserve=4)
    opening = public_opening(w)
    open_granaries(w,e)
    captured = capture_food_accounting(w,e,weights,opening)
    row = captured.as_dict(1)['regions'][0]
    assert row['native']['consumed'] == 2 and row['native']['sufficiency'] == .4
    assert row['public']['released'] == 3
    assert row['sufficiency_after_relief'] == 1
    assert row['public']['spoiled'] == pytest.approx(.03)
    assert row['public']['after_open'] == pytest.approx(.97)
    assert row['public']['balance_residual'] == pytest.approx(0)
    # Later controller/population changes cannot relabel the Phase2 population.
    w.regions[0].population = 99
    assert captured.as_dict(1)['regions'][0]['model_population'] == 40


def test_old_native_output_is_unknown_instead_of_zero_consumed(make_world):
    w,e,weights=setup(make_world,stock=10,consumed=5)
    e.food_ledger.clear()
    row=capture_food_accounting(w,e,weights,None).as_dict(1)['regions'][0]
    assert row['native'] is None and row['sufficiency_after_relief']==2
    assert row['public'] is None


def test_aggregate_does_not_fabricate_native_meals_or_demand(make_world):
    w=make_world(num_civs=1)
    w.agent_mode='off'
    observed=capture_food_accounting(w,None,None,None).as_dict(1)
    assert observed['transport']=='none'
    assert observed['regions'][0]['native'] is None
    assert observed['regions'][0]['native_count'] is None
    assert observed['regions'][0]['sufficiency_after_relief'] is None
    assert observed['procurement']==[]


def test_snapshot_clock_legacy_omission_and_history_roundtrip(make_world):
    w,e,weights=setup(make_world,stock=2,consumed=2)
    captured=capture_food_accounting(w,e,weights,None)
    obs=TurnObservation(0,1,None,food_accounting=captured,food_procurement=((0,4,1),))
    fields=snapshot_fields(w,obs)
    assert fields['food_accounting']['procurement']==[{'civilization_id':0,'budget_initial':4,'budget_remaining':1,'spent':3}]
    snapshot=TurnSnapshot(turn=1,civ_stats={},region_control={},relationships={},**fields)
    assert json.loads(snapshot.model_dump_json())['food_accounting']==fields['food_accounting']
    assert 'food_accounting' not in TurnSnapshot(turn=1,civ_stats={},region_control={},relationships={}).model_dump()
    assert snapshot_fields(w,TurnObservation(0,1,None))=={}
    with pytest.raises(ValueError,match='another source turn'):
        snapshot_fields(w,replace(obs,food_accounting=replace(captured,source_turn=4)))
    with pytest.raises(ValueError,match='completed turn'):
        captured.as_dict(3)


def test_empty_public_budget_is_recorded_at_actual_procurement_boundary(make_world):
    w,e,weights=setup(make_world,stock=0,consumed=0,reserve=0)
    w.civilizations[0].treasury=0
    open_granaries(w,e)
    tick_grain_reserves(w,economy_result=e)
    assert e.food_procurement_budget=={0:(0,0)}
    captured=capture_food_accounting(w,e,weights,(0,))
    row=captured.as_dict(1,((0,0,0),))
    assert row['procurement']==[{'civilization_id':0,'budget_initial':0,'budget_remaining':0,'spent':0}]
    assert row['regions'][0]['public']['released']==0
