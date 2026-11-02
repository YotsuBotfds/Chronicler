"""Narrow v4 academy restoration pair and real native continuation."""
import math
import os
import pickle
import queue
import random
import sys
from types import SimpleNamespace

import pytest
from chronicler import what_if as wi
from chronicler.interactive import parse_command
from chronicler.pause_academy import TARGET, STAT, CONTROL


def request(**kw):
    return {"type":"what_if_prepare", "request_id":"restore", "control":CONTROL,
            "region_id":2, "fallen_seat_id":0, "turns":7, **kw}


@pytest.mark.parametrize('changes', [dict(region_id=True),dict(region_id=-1),dict(fallen_seat_id=True),
    dict(fallen_seat_id=-1),dict(turns=True),dict(turns=21),dict(path='/tmp/a')])
def test_bad_request(changes):
    with pytest.raises(wi.WhatIfError):
        wi._request_fields(request(**changes))


def test_command_and_manifest_are_strict():
    item={"command":"set", "civ":TARGET, "stat":STAT, "value":0, "region_id":2, "fallen_seat_id":0}
    assert wi.intervention_command(item) == {k:item[k] for k in ('command','civ','stat','value')}
    assert parse_command('set @academy lab.academy_restore 0') == ('set',(TARGET,STAT,0))
    for changed in ({'fallen_seat_id':1},{'region_id':True},{'value':-1},{'civ':'@world'}):
        with pytest.raises(wi.WhatIfError):
            wi.intervention_command({**item, **changed})
    assert parse_command('set @academy lab.academy_restore -1')[0] == 'error'
    assert parse_command('set @academy lab.academy_restore 0 extra')[0] == 'error'


def _fallen_world():
    from test_learning_services_native import _paid_service_setup, _service_turn
    from chronicler.techniques import set_techniques_enabled
    from chronicler.war.common import build_context
    from chronicler.war.peace import conclude_peace, open_war, reconcile_wars
    world, bridge, region, owner = _paid_service_setup()
    set_techniques_enabled(world, True)
    original = world.civilizations[owner]
    other_i = next(i for i, civ in enumerate(world.civilizations) if i != owner)
    other = world.civilizations[other_i]
    other.treasury, other.culture, other.stability = 500, 80, 80
    for r in world.regions:
        r.stockpile.goods['grain'] = 1000.0
    world.regions[region].stockpile.goods['crafts'] = 1000.0
    _service_turn(world, bridge)
    procurement = world.scholarship.learning_services.procurement_receipts[0]
    assert procurement.purchased > 0 and procurement.paid == math.ceil(procurement.purchased * procurement.craft_price)
    _service_turn(world, bridge)
    teaching = world.scholarship.learning_services.teaching_receipts[0]
    assert teaching.work_delivered > 0 and teaching.crafts_used > 0
    held = world.scholarship.learning_services.inventories[0].held
    context = build_context(world)
    if not any(set(pair) == {other.name, original.name} for pair in world.active_wars):
        world.active_wars.append((other.name, original.name))
        open_war(context, other, original)
        world.events_timeline.extend(context.events)
    name = world.regions[region].name
    original.regions = [r for r in original.regions if r != name]
    if name not in other.regions:
        other.regions.append(name)
    world.regions[region].controller = other.name
    _service_turn(world, bridge)
    assert world.scholarship.seats[0].fallen_turn == 2
    assert world.scholarship.learning_services.supply_losses[0].lost == pytest.approx(held)
    context = build_context(world)
    reconcile_wars(context)
    for war in list(world.war_state.wars):
        if other.name in (war.attacker, war.defender):
            conclude_peace(context, war, 'white_peace', None)
    world.events_timeline.extend(context.events)
    other.capital_region = name
    while world.turn < 13:
        _service_turn(world, bridge)
    return world, bridge, region, other_i, held


def test_native_real_fallen_academy_pair(tmp_path):
    pytest.importorskip('chronicler_agents')
    if os.name != 'posix' or os.environ.get('PYTHONHASHSEED') != '0' or sys.flags.hash_randomization:
        pytest.skip('requires POSIX and interpreter started with PYTHONHASHSEED=0')
    import numpy as np
    from chronicler import main
    from chronicler.batch_manifest import simulation_config, output_config
    from chronicler.run_checkpoint import RunState, write_checkpoint, read_checkpoint
    world, bridge, region, owner, held = _fallen_world()
    pair = None
    try:
        args = main._build_parser().parse_args(['--seed','42','--turns','20','--regions','8','--civs','4',
            '--agents','hybrid','--cities','--scholarship','--techniques','--academy-services',
            '--simulate-only','--output',str(tmp_path/'out.md'),'--state',str(tmp_path/'state.json')])
        config={'agent_mode':'hybrid','agent_scale_mode':'fixed','validation_sidecar':False,
                'relationship_stats':False,'simulation_args':simulation_config(args),'output_args':output_config(args)}
        state=RunState(world=world,agent_bridge=bridge,memories={},history=[],chronicle_entries=[],
            era_reflections={},pending_injections=[],start_turn=0,seed=42,num_turns=20,run_config=config)
        pair=wi.WhatIfPairs(tmp_path,queue.Queue(),SimpleNamespace(save_private=lambda path:write_checkpoint(path,state)))
        before,native,rng=world.model_dump_json(),bridge._sim.checkpoint_state(),random.getstate()
        numpy_rng=pickle.dumps(np.random.get_state())
        from chronicler.pause_academy import paused_context
        view=paused_context(world)
        assert view['schema_version']==1 and view['turn']==13 and view['supported']
        row=next(row for row in view['candidates'] if row['fallen_seat_id']==0)
        assert row['eligible'] and row['current_lord']==owner and row['fee']==30
        assert row['treasury_after']==row['treasury_before']-30 and row['reason'] is None
        assert world.model_dump_json()==before and bridge._sim.checkpoint_state()==native and random.getstate()==rng
        saved_treasury=world.civilizations[owner].treasury
        world.civilizations[owner].treasury=59
        ineligible=next(row for row in paused_context(world)['candidates'] if row['fallen_seat_id']==0)
        assert not ineligible['eligible'] and ineligible['reason'] and ineligible['fee'] is None
        world.civilizations[owner].treasury=saved_treasury
        assert world.model_dump_json()==before
        msg=request(region_id=region)
        status=pair.prepare(msg,world)
        m=status['manifest']; action=m['intervention']
        assert m['schema_version']==4 and action['fallen_seat_id']==0 and action['region_id']==region
        assert action['current_lord']==owner and action['fee']==30
        assert action['treasury_after']==action['treasury_before']-30
        assert world.model_dump_json()==before and bridge._sim.checkpoint_state()==native and random.getstate()==rng
        assert pair.prepare(msg,world)['state']=='prepared'
        with pytest.raises(wi.WhatIfError,match='different'):
            pair.prepare(request(region_id=region+1),world)
        tampered={**action,'current_lord':(owner+1)%len(world.civilizations)}
        with pytest.raises(wi.WhatIfError,match='differs'):
            wi.validate_academy_checkpoint(pair.jobs['restore'].directory/'common.ckpt',tampered)
        pair.run('restore'); job=pair.jobs['restore'];job.thread.join(35)
        assert not job.thread.is_alive() and job.state=='complete',job.message
        assert world.model_dump_json()==before and bridge._sim.checkpoint_state()==native and random.getstate()==rng
        assert pickle.dumps(np.random.get_state()) == numpy_rng
        output={arm:read_checkpoint(job.directory/arm/'final.ckpt') for arm in ('baseline','intervention')}
        try:
            plain,changed=output['baseline'].state.world,output['intervention'].state.world
            assert all(x.exact for x in output.values())
            assert not [s for s in plain.scholarship.seats[1:] if s.region==region]
            rebuilt=[(i,s) for i,s in enumerate(changed.scholarship.seats) if i>0 and s.region==region]
            assert len(rebuilt)==1
            seat_id,seat=rebuilt[0]
            assert seat.founded_turn==13 and seat.founder==owner
            events=[e for e in changed.events_timeline if e.event_type=='seat_founded' and e.region==world.regions[region].name and '[Lab]' in e.description]
            assert len(events)==1 and events[0].event_id and events[0].causes
            assert events[0].causes[0] in {eid for _,kind,eid in world.scholarship.seats[0].history if kind=='fell'}
            assert output['intervention'].state.run_config['interventions'][-1] == {'turn':13,'command':'set','civ':TARGET,'stat':STAT,'value':0}
            # The pair's real per-turn history must show paid supplies and delivered native work.
            snapshots=job.result['intervention']['bundle']['history']
            assert snapshots[0]['scholarship']['counters']['fees'] == 30
            services=[s['scholarship']['learning_services'] for s in snapshots]
            bought=[p for service in services for p in service['procurement_receipts']
                    if p['seat_id']==seat_id and p['purchased']>0 and p['paid']>0]
            taught=[t for service in services for t in service['teaching_receipts']
                    if t['seat_id']==seat_id and (t['work_delivered'] or 0)>0]
            assert bought and taught
            assert all(t['crafts_used']>0 and t['upkeep_satisfied'] for t in taught)
            assert any(p['source_turn'] < t['source_turn'] and
                       t['crafts_used'] == pytest.approx(8 * t['work_delivered'])
                       for p in bought for t in taught)
            assert changed.scholarship.learning_services.inventories[0].lost_total == pytest.approx(held)
        finally:
            for x in output.values():x.state.agent_bridge.close()
    finally:
        if pair:pair.close()
        bridge.close()


def test_paused_context_bounds_and_reconnect(monkeypatch):
    from chronicler import lab_academy
    from chronicler.pause_academy import paused_context
    from chronicler.scholarship_state import ACADEMY
    from chronicler.live import LiveServer
    monkeypatch.setattr(lab_academy, '_boundary', lambda *args: None)
    seats = [SimpleNamespace(kind=ACADEMY,region=i,fallen_turn=1,founder=0,founded_turn=0,name=f'seat {i}') for i in range(70)]
    world = SimpleNamespace(turn=2, scholarship=SimpleNamespace(seats=seats),
        regions=[SimpleNamespace(name=f'region {i}',controller=None) for i in range(70)], civilizations=[])
    data=paused_context(world)
    assert data['supported'] and data['turn']==2 and data['total_candidates']==70
    assert len(data['candidates'])==64 and data['omitted']==6
    assert [r['region_id'] for r in data['candidates']]==list(range(64))
    assert all(not r['eligible'] and r['reason'] and r['current_lord'] is None for r in data['candidates'])
    server=LiveServer()
    server._record_status({'type':'paused','turn':2,'academy_restoration':data})
    next_data={**data,'candidates':[]}
    server._record_status({'type':'ack','still_paused':True,'academy_restoration':next_data})
    assert server._last_paused_msg['academy_restoration']==next_data


def test_paused_context_reports_unsupported():
    from chronicler.pause_academy import paused_context
    world=SimpleNamespace(turn=0,agent_mode='off',_agent_bridge=None,cities=None,scholarship=None)
    data=paused_context(world)
    assert not data['supported'] and data['turn']==0 and data['unavailable_reason']
    assert data['candidates']==[] and data['total_candidates']==data['omitted']==0
