#!/usr/bin/env python3
"""One declared full-main constructed academy loss/restoration development pair."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import random
import shlex
import subprocess
import sys

from scripts.crisis_transport_example import CheckpointBinding

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = {
    'seed':42, 'regions':8, 'civilizations':4, 'turns':20,
    'regional_grain':1000.0, 'regional_crafts':1000.0,
    'civ_treasury':500, 'civ_culture':80, 'civ_stability':80,
    'academy':'first actual controlled adult native Scholar region',
    'ownership_transfer_turn':2, 'peace_and_new_capital_turn':3,
    'restore_preview_turns':[12,18], 'max_pair_turns':7,
    'scope':'constructed development; no manual later topups or forced founding; not held-out',
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def initial_world():
    import pyarrow as pa
    from chronicler.agent_bridge import AgentBridge
    from chronicler.cities import set_cities_enabled
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
    from chronicler.world_gen import generate_world
    world=generate_world(seed=42,num_regions=8,num_civs=4)
    world.agent_mode='hybrid'
    set_cities_enabled(world,True)
    for region in world.regions:
        region.stockpile.goods={'grain':1000.0,'crafts':1000.0}
    for civ in world.civilizations:
        civ.treasury,civ.culture,civ.stability=500,80,80
    probe=AgentBridge(world,mode='hybrid')
    try:
        rows=pa.record_batch(probe._sim.get_snapshot()).to_pylist()
        person=next((x for x in rows if x['occupation']==3 and x['age']>=20
                     and world.regions[x['region']].controller is not None),None)
        if person is None:
            raise RuntimeError('no controlled adult native scholar at declared initialization')
        region=person['region']
        owner=world.civ_index_map[world.regions[region].controller]
    finally:
        probe.close()
        world._agent_bridge=None
    world.scholarship=ScholarshipState(seats=[Seat(region=region,kind=ACADEMY,name='Declared Academy',
        founded_turn=world.turn,founder=owner,lord=owner)])
    return world,region,owner


def generate(output: Path):
    import chronicler_agents.chronicler_agents as native
    from chronicler import main
    from chronicler.pause_academy import preview, TARGET, STAT, paused_context
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.what_if import WhatIfPairs
    from chronicler.war.common import build_context
    from chronicler.war.peace import conclude_peace,open_war,reconcile_wars
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest={'kind':'constructed-academy-full-main','schema_version':1,'state':'starting',
        'conditions':CONDITIONS,'admissions':[],'actions':[],
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'native_source_tree':subprocess.check_output(['git','rev-parse','HEAD:chronicler-agents'],cwd=ROOT,text=True).strip(),
        'native_sha256':hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':['Constructed initial resources and declared control transfer/peace; development only.',
            'Explicit paid restoration is not spontaneous founding; fee does not model construction labor or materials.',
            'Common checkpoint is a full execute_run boundary; a single seed is not an efficacy evaluation.']}
    receipt=output/'crisis-case.json';write(receipt,manifest)
    world,region_id,owner_id=initial_world()
    other_id=next(i for i in range(len(world.civilizations)) if i!=owner_id)
    manifest['selected']={'region_id':region_id,'region_name':world.regions[region_id].name,
        'original_owner':owner_id,'other_civ':other_id,'initial_seat_id':0}
    world.save(output/'constructed_initial_state.json')
    binding=CheckpointBinding(); pairs=WhatIfPairs(output,queue.Queue(),binding)
    paid_before=[]
    held_before=[]
    def pause(current,memories,pending):
        service=current.scholarship.learning_services
        if current.turn==1:
            paid_before.extend(p for p in service.procurement_receipts if p.seat_id==0 and p.purchased>0 and p.paid>0)
        if current.turn==2:
            region=current.regions[region_id];original=current.civilizations[owner_id];other=current.civilizations[other_id]
            teaching=[t for t in service.teaching_receipts if t.seat_id==0 and (t.work_delivered or 0)>0 and (t.crafts_used or 0)>0]
            held_before.extend(i.held for i in service.inventories if i.seat_id==0 and not i.retired)
            if region.controller!=original.name or not paid_before or not teaching or not held_before or held_before[-1]<=0:
                manifest.update(state='partial',reason='source-2 transfer admission: owner, paid supplies, held materials or native teaching absent')
                write(receipt,manifest);return False
            context=build_context(current)
            if not any(set(pair)=={other.name,original.name} for pair in current.active_wars):
                current.active_wars.append((other.name,original.name));open_war(context,other,original)
                current.events_timeline.extend(context.events)
            original.regions=[r for r in original.regions if r!=region.name]
            if region.name not in other.regions:other.regions.append(region.name)
            region.controller=other.name
            manifest['actions'].append({'source_turn':2,'action':'declared controller transfer and existing open_war',
                'from_owner':owner_id,'to_owner':other_id,'region_id':region_id,'applied':True})
        if current.turn==3:
            losses=[x for x in service.supply_losses if x.seat_id==0 and x.lost>0]
            fallen=current.scholarship.seats[0]
            if (fallen.fallen_turn!=2 or not losses or
                    abs(losses[0].lost-held_before[-1])>1e-6):
                manifest.update(state='partial',reason='source-2 academy fall or actual held-material loss missing')
                write(receipt,manifest);return False
            manifest['initial_loss']={'source_turn':2,'held_before':held_before[-1],
                'lost':losses[0].lost,'fallen_turn':fallen.fallen_turn,
                'fall_event_ids':[eid for _,kind,eid in fallen.history if kind=='fell']}
            context=build_context(current);reconcile_wars(context)
            other=current.civilizations[other_id]
            for war in list(current.war_state.wars):
                if other.name in (war.attacker,war.defender):conclude_peace(context,war,'white_peace',None)
            current.events_timeline.extend(context.events)
            other.capital_region=current.regions[region_id].name
            manifest['actions'].append({'source_turn':3,'action':'existing peace and declared capital change',
                'lord':other_id,'region_id':region_id,'applied':True})
        if not 12<=current.turn<=18:return True
        try:
            previewed=preview(current,TARGET,STAT,0)
            if not previewed.changed or previewed.request.region_id!=region_id:
                raise ValueError('fallen seat not currently eligible')
        except ValueError as exc:
            manifest['admissions'].append({'turn':current.turn,'eligible':False,'reason':str(exc)})
            if current.turn==18:
                manifest.update(state='partial',reason='no eligible restoration boundary through source18')
                write(receipt,manifest);return False
            return True
        manifest['admissions'].append({'turn':current.turn,'eligible':True})
        manifest['paused_context']=paused_context(current)
        before=(current.model_dump_json(),bytes(current._agent_bridge._sim.checkpoint_state()),random.getstate())
        request={'type':'what_if_prepare','request_id':'academy-restoration','control':'academy_restoration',
                 'region_id':region_id,'fallen_seat_id':0,'turns':min(7,20-current.turn)}
        pairs.prepare(request,current);pairs.run('academy-restoration')
        job=pairs.jobs['academy-restoration'];job.thread.join(250)
        if job.thread.is_alive() or job.state!='complete':
            raise RuntimeError('exact what-if pair did not complete: '+str(job.message))
        if before!=(current.model_dump_json(),bytes(current._agent_bridge._sim.checkpoint_state()),random.getstate()):
            raise RuntimeError('pair changed the original world, native state or RNG')
        cp=read_checkpoint(job.directory/'common.ckpt')
        try:
            prior_turns=[s.turn for s in cp.state.history]
            if not cp.exact or prior_turns!=list(range(1,current.turn+1)):
                raise RuntimeError('common checkpoint lacks complete prior main history')
            runtimes=[k for k in ('agent_bridge','ecology_runtime','politics_runtime','economy_tracker') if getattr(cp.state,k) is not None]
        finally:cp.state.agent_bridge.close()
        bundles={a:job.result[a]['bundle'] for a in ('baseline','intervention')}
        snapshots=bundles['intervention']['history']; seat_id=None
        for s in snapshots:
            for seat in (s.get('scholarship') or {}).get('seats',[]):
                if seat['region']==current.regions[region_id].name and seat['id']!=0 and seat['name'].startswith('the Lab-restored Academy'):
                    seat_id=seat['id']
        services=[(s.get('scholarship') or {}).get('learning_services') or {} for s in snapshots]
        purchases=[p for svc in services for p in svc.get('procurement_receipts',[]) if p['seat_id']==seat_id and p['purchased']>0 and p['paid']>0]
        teaching=[t for svc in services for t in svc.get('teaching_receipts',[]) if t['seat_id']==seat_id and (t['work_delivered'] or 0)>0 and (t['crafts_used'] or 0)>0]
        events=[e for e in bundles['intervention']['events_timeline'] if e['event_type']=='seat_founded' and '[Lab]' in e['description']]
        baseline_new=[seat for s in bundles['baseline']['history'] if s['turn']>current.turn
            for seat in (s.get('scholarship') or {}).get('seats',[]) if seat['region']==current.regions[region_id].name and seat['id']!=0]
        fee=job.manifest['intervention']['fee']
        causes=set(manifest['initial_loss']['fall_event_ids'])
        causal_event=any(causes.intersection(event.get('causes',[])) for event in events)
        fee_recorded=any((s.get('scholarship') or {}).get('counters',{}).get('fees')==fee
                         for s in snapshots if s['turn']>current.turn)
        complete=bool(fee==30 and fee_recorded and seat_id is not None and causal_event and purchases and teaching and not baseline_new)
        manifest.update(state='validated' if complete else 'partial',reason=None if complete else 'required seat/cause/paid supply/native teaching or baseline control missing',
            admission={'source_turn':current.turn,'complete_prior_history_turns':prior_turns,'runtime_fields':runtimes,
                'original_unchanged':True,'restored_seat_id':seat_id,'founding_events':events,
                'paid_purchases':purchases,'native_teaching':teaching,'baseline_new_seats':baseline_new},
            exact_pair_directory=str(job.directory),pair_manifest=job.manifest)
        for arm,bundle in bundles.items():
            write(output/f'{arm}-observations.json',[{'turn':s['turn'],'scholarship':s.get('scholarship'),
                'food_accounting':s.get('food_accounting')} for s in bundle['history']])
        write(receipt,manifest);return False
    try:
        args=main._build_parser().parse_args(['--seed','42','--turns','20','--regions','8','--civs','4','--agents','hybrid',
            '--cities','--scholarship','--techniques','--academy-services','--simulate-only','--pause-every','1',
            '--output',str(output/'original'/'chronicle.md'),'--state',str(output/'original'/'state.json')])
        main.execute_run(args,world=world,on_pause=pause,pause_every=1,turn_boundary=binding)
    except BaseException as exc:
        manifest.update(state='failed',reason=f'{type(exc).__name__}: {exc}');write(receipt,manifest);raise
    finally:pairs.close()
    if manifest['state']=='validated':
        from chronicler.run_checkpoint import read_header
        checkpoint=Path(manifest['exact_pair_directory'])/'common.ckpt'
        header,_=read_header(checkpoint)
        threads=header['identity']['environment']['thread_env']
        # Exact continuation distinguishes absent variables from explicit 1.
        # Do not silently substitute this shell's current thread settings.
        launch=['env']
        for key,value in threads.items():
            if value is None:launch.extend(['-u',key])
        launch.extend(f'{key}={value}' for key,value in threads.items() if value is not None)
        launch.extend([f'PYTHONPATH={ROOT / "src"}{os.pathsep}{ROOT}',sys.executable,'-m','chronicler.main',
            '--live','--live-port','0','--resume',str(checkpoint),'--turns','20','--simulate-only',
            '--output',str(output/'live'/'chronicle.md'),'--state',str(output/'live'/'state.json')])
        destination=shlex.quote(str(output/'live'))
        command=(f'if test -e {destination} || test -L {destination}; then\n'
            "  echo 'Live output exists; choose a fresh output directory.' >&2\n  exit 1\nfi\n"
            +f'mkdir -m700 -- {destination}\n'
            +shlex.join(launch)+'\n')
        (output/'launch-live.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\numask 077\n'+command)
        (output/'WALKTHROUGH.txt').write_text(
            'Constructed full-main development case, not natural recovery or held-out evidence.\n'
            f'Read crisis-case.json. The common checkpoint has actual snapshots1–{header["turn"]}; '
            'both child bundles preserve this history. Open either child chronicle_bundle.json in the viewer.\n'
            +f'Unchanged world: {Path(manifest["exact_pair_directory"]) / "baseline" / "chronicle_bundle.json"}\n'
            +f'Restored world: {Path(manifest["exact_pair_directory"]) / "intervention" / "chronicle_bundle.json"}\n'
            +'For the paused app, first start the viewer with: cd viewer && npm run build && npm run preview\n'
            'Then copy this launch command (it preserves the checkpoint thread settings and refuses reused output):\n'
            +shlex.join(['bash',str(output/'launch-live.sh')])+'\n'
            'Open the private viewer link printed by the CLI; keep its token out of screenshots and exports.\n'
            'Inspect Learning and the recorded turn2 fall. At the CURRENT paused turn, choose paid academy '
            're-founding, preview the named seat and 30-coin fee, then compare seven further turns. '
            'The original remains paused. In the completed result, inspect the new seat, paid craft purchases '
            'and native teaching with their source/available dates. The fee does not model construction '
            'labor or materials, and paid founding alone does not guarantee service.\n',encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--simulate-only',action='store_true',required=True)
    args=parser.parse_args();raw=args.output.expanduser();output=raw.resolve()
    if raw.is_symlink() or output.exists() or output.is_relative_to(ROOT):parser.error('choose a fresh external output directory')
    if sys.version_info < (3,13) or os.environ.get('PYTHONHASHSEED')!='0' or sys.flags.hash_randomization:
        parser.error('requires Python 3.13+ started with PYTHONHASHSEED=0')
    os.umask(0o077)
    result=generate(output)
    print(json.dumps({'state':result['state'],'output':str(output),'reason':result.get('reason')}))
    if result['state']!='validated':raise SystemExit(2)


if __name__=='__main__':main()
