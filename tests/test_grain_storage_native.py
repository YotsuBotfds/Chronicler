"""Real native work, stock/cost and active construction continuation controls."""
import random
from copy import deepcopy

import pytest

pytest.importorskip('chronicler_agents')
pytestmark = pytest.mark.native

from chronicler.grain_storage import enable_storage, set_storage_policy
from chronicler.grain_storage_state import StorageAsset
from chronicler.grain_reserves import set_grain_reserves_enabled, _ensure


def _world(*, reserve, market, treasury=1000, num_civs=1):
    from chronicler.world_gen import generate_world
    w=generate_world(seed=42,num_regions=3,num_civs=num_civs)
    w.agent_mode='hybrid'
    civ=w.civilizations[0]
    for other in w.civilizations[1:]:
        other.regions=[]
        other.population=0
    civ.regions=[r.name for r in w.regions]
    civ.capital_region=w.regions[0].name
    civ.treasury=treasury
    for i,r in enumerate(w.regions):
        r.controller=civ.name
        r.population=100
        r.carrying_capacity=100
        r.adjacencies=[w.regions[j].name for j in range(3) if j!=i]
        r.stockpile.goods={'timber':100.0,'grain':market}
        # Constructed post-harvest land; remaining forage is computed normally.
        r.resource_types=[255,255,255]
        r.resource_base_yields=[0.0,0.0,0.0]
    civ.population=300
    set_grain_reserves_enabled(w,True)
    state=_ensure(w)
    for g in state.granaries:g.owner=0;g.grain=0
    state.granaries[0].grain=reserve
    storage=enable_storage(w)
    storage.assets=[StorageAsset(capacity=max(200,2*reserve),condition=.5,owner=0) for _ in w.regions]
    return w


def _tick(w,b):
    from chronicler.simulation import run_turn_result
    from chronicler.action_engine import ActionEngine
    engine=ActionEngine(w)
    return run_turn_result(w,lambda c,world:engine.select_action(c,seed=world.seed),lambda *_:'',seed=w.seed+w.turn,agent_bridge=b)


def _pair(w):
    from chronicler.agent_bridge import AgentBridge
    a,b=deepcopy(w),deepcopy(w)
    set_storage_policy(a,0,'neglect',0)
    set_storage_policy(b,0,'maintain',4)
    aa,bb=AgentBridge(a,mode='hybrid'),AgentBridge(b,mode='hybrid')
    rng=random.getstate()
    ar=_tick(a,aa)
    random.setstate(rng)
    br=_tick(b,bb)
    return a,aa,ar,b,bb,br


def test_real_paid_maintenance_preserves_stored_food_and_consumes_work_and_material(monkeypatch):
    monkeypatch.setenv('CHRONICLER_CHECK_RESOURCES','1')
    a,aa,ar,b,bb,br=_pair(_world(reserve=2000,market=1000))
    try:
        paid=b.grain_reserves.storage.receipts[0]
        assert paid.delivered==paid.requested==4
        assert paid.treasury_paid==8
        assert paid.timber_used==4 and paid.timber_returned==0
        assert b.grain_reserves.storage.assets[0].condition > a.grain_reserves.storage.assets[0].condition
        assert b.grain_reserves.granaries[0].grain > a.grain_reserves.granaries[0].grain
        before=ar.observation.food_accounting.regions[0].as_dict()['native']
        after=br.observation.food_accounting.regions[0].as_dict()['native']
        assert after['produced'] < before['produced']
        for result in [ar,br]:
            for row in result.observation.food_accounting.regions:
                native=row.as_dict()['native']
                assert abs(native['balance_residual'])<=native['balance_tolerance']
    finally:aa.close();bb.close()


def test_real_empty_granary_investment_can_worsen_present_food_shortfall(monkeypatch):
    monkeypatch.setenv('CHRONICLER_CHECK_RESOURCES','1')
    a,aa,ar,b,bb,br=_pair(_world(reserve=0,market=0,treasury=8))
    try:
        paid=b.grain_reserves.storage.receipts[0]
        assert paid.delivered > 0 and paid.treasury_paid > 0
        before=ar.observation.food_accounting.regions[0].as_dict()
        after=br.observation.food_accounting.regions[0].as_dict()
        assert before['public']['released']==after['public']['released']==0
        assert after['native']['demand']==before['native']['demand']>0
        assert after['native']['consumed'] < before['native']['consumed']
        assert after['sufficiency_after_relief'] < before['sufficiency_after_relief']
    finally:aa.close();bb.close()


def test_partly_built_storage_exact_resume_and_ownership_preserve_asset(tmp_path,monkeypatch):
    from chronicler.agent_bridge import AgentBridge
    from test_crisis_transport_native import _checkpoint
    monkeypatch.setenv('CHRONICLER_CHECK_RESOURCES','1')
    world=_world(reserve=50,market=1000)
    set_storage_policy(world,0,'expand',2)
    bridge=AgentBridge(world,mode='hybrid')
    _tick(world,bridge)
    assert world.grain_reserves.storage.assets[0].expansion_progress==2
    restored,resumed=_checkpoint(tmp_path,world,bridge)
    try:
        for _ in range(3):
            rng=random.getstate();one=_tick(world,bridge);after=random.getstate()
            random.setstate(rng);two=_tick(restored,resumed)
            assert random.getstate()==after
            assert world.model_dump_json()==restored.model_dump_json()
            assert bytes(bridge._sim.checkpoint_state())==bytes(resumed._sim.checkpoint_state())
            assert one.observation.food_accounting==two.observation.food_accounting
        assert world.grain_reserves.storage.assets[0].expansion_progress==8
        # Abandonment changes custody, never resets paid work or condition.
        old=world.grain_reserves.storage.assets[0].model_copy(deep=True)
        world.regions[0].controller=None
        _tick(world,bridge)
        asset=world.grain_reserves.storage.assets[0]
        assert asset.owner==-1
        assert asset.capacity==old.capacity and asset.expansion_progress==old.expansion_progress
        assert asset.condition<old.condition
    finally:bridge.close();resumed.close()


def test_damaged_capacity_returns_grain_and_conquest_keeps_paid_work(monkeypatch):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.grain_reserves_state import STORAGE_RETURNED
    monkeypatch.setenv('CHRONICLER_CHECK_RESOURCES','1')
    world=_world(reserve=100,market=1000,num_civs=2)
    # Constructed damaged asset at the incident boundary, before overflow settles.
    world.grain_reserves.storage.assets[0]=StorageAsset(capacity=100,condition=.2,owner=0,expansion_progress=6)
    bridge=AgentBridge(world,mode='hybrid')
    try:
        _tick(world,bridge)
        returned=[f for f in world.grain_reserves.flows if f.kind==STORAGE_RETURNED and f.region==0]
        assert len(returned)==1 and returned[0].amount>0
        asset=world.grain_reserves.storage.assets[0]
        assert world.grain_reserves.granaries[0].grain<=asset.capacity*asset.condition+1e-9
        assert world.grain_reserves.storage.receipts[0].capacity_returned==returned[0].amount
        old=asset.model_copy(deep=True)
        old_civ,new_civ=world.civilizations
        name=world.regions[0].name
        old_civ.regions=[r for r in old_civ.regions if r!=name]
        new_civ.regions=[name]
        world.regions[0].controller=new_civ.name
        world.regions[0]._controller_changed_this_turn=True
        set_storage_policy(world,0,'neglect',0)
        _tick(world,bridge)
        asset=world.grain_reserves.storage.assets[0]
        assert asset.owner==1
        assert asset.capacity==old.capacity and asset.expansion_progress==old.expansion_progress
        assert asset.condition<old.condition
    finally:bridge.close()


def test_complete_first_turn_goods_balance_includes_paid_storage_material(monkeypatch):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.grain_reserves_state import RELEASED, SPOILED, BOUGHT
    monkeypatch.setenv('CHRONICLER_CHECK_RESOURCES','1')
    world=_world(reserve=2000,market=1000)
    set_storage_policy(world,0,'maintain',4)
    total=lambda: sum(sum(r.stockpile.goods.values()) for r in world.regions)+sum(g.grain for g in world.grain_reserves.granaries)
    before=total()
    bridge=AgentBridge(world,mode='hybrid')
    try:
        _tick(world,bridge)
        c=world._economy_result.conservation
        used=sum(r.timber_used for r in world.grain_reserves.storage.receipts)
        assert used==4
        public_loss=sum(f.amount for f in world.grain_reserves.flows if f.kind in (RELEASED,SPOILED))
        public_loss+=sum(f.sent-f.amount for f in world.grain_reserves.flows if f.kind==BOUGHT)
        expected=(before+c['production']+c['clamp_floor_loss']-c['consumption']-c['storage_loss']
                  -c['cap_overflow']-c['transit_loss']-c['in_transit_delta']-used-public_loss)
        assert total()==pytest.approx(expected,rel=2e-6,abs=1e-5)
    finally:bridge.close()
