#!/usr/bin/env python3
"""Full-main replay of one declared corrected-yield forecast development case.

This is a constructed case, not a held-out estimate of misinformation harm.
The only changed input between the three arms is the existing report policy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import random
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CONDITIONS={'seed':42,'regions':4,'civs':2,'turns':20,'population_each':60,'capacity_each':100,
    'initial_treasury_each':45,'region2_base_yield':[1.8,0.,0.],
    'region2_effective_yield':[1.8,0.,0.], 'regional_storage_capacity':100.,
    'qualification':'constructed development after earlier nulls; not held-out'}


def initial_world():
    from chronicler.contact_ledger import set_contact_ledger_enabled
    from chronicler.grain_reserves import set_grain_reserves_enabled,_ensure
    from chronicler.grain_storage import enable_storage
    from chronicler.grain_storage_state import StorageAsset
    from chronicler.harvest_forecasts import set_harvest_forecasts_enabled
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world
    world=generate_world(seed=42,num_regions=4,num_civs=2);world.agent_mode='hybrid'
    for ci,civ in enumerate(world.civilizations):
        civ.regions=[world.regions[2*ci].name,world.regions[2*ci+1].name]
        civ.capital_region=world.regions[2*ci].name;civ.population=120;civ.treasury=45
    for rid,region in enumerate(world.regions):
        region.controller=world.civilizations[rid//2].name;region.population=60;region.carrying_capacity=100
        region.adjacencies=[r.name for j,r in enumerate(world.regions) if j!=rid]
        region.stockpile.goods={'grain':0.0 if rid==0 else 120.0}
        region.resource_types=[255,255,255] if rid==0 else [0,255,255]
        region.resource_base_yields=[[0.,0.,0.],[1.8,0.,0.],[1.8,0.,0.],[1.8,0.,0.]][rid]
    for rid in (1,2,3):
        region=world.regions[rid];region.ecology.soil=1.;region.ecology.water=1.
        region.stockpile.goods={'grain':150.,'salt':150.}
    world.regions[2].resource_effective_yields=[1.8,0.,0.]
    set_grain_reserves_enabled(world,True)
    reserves=_ensure(world)
    for rid,g in enumerate(reserves.granaries):g.owner=rid//2;g.grain=0.
    storage=enable_storage(world)
    storage.assets=[StorageAsset(capacity=100.,condition=1.,owner=rid//2) for rid in range(4)]
    set_contact_ledger_enabled(world,True);set_harvest_forecasts_enabled(world,True)
    set_transaction_receipts_enabled(world,True)
    from chronicler.ecology import yield_penalty_factor
    assert yield_penalty_factor(world.regions[2],0)==1.
    return world


def _sha(body):return hashlib.sha256(body).hexdigest()
def _json(path,data):path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


class StartWitness:
    def __init__(self,directory):self.directory=directory;self.start=None
    def bind(self,save,run_config):
        import numpy as np
        from chronicler.run_checkpoint import read_checkpoint
        self.save=save
        path=save(str(self.directory/'start.ckpt'))
        cp=read_checkpoint(path)
        try:
            w=cp.state.world; raw=w.model_dump(mode='json')
            policy=raw['harvest_forecasts']['policy'];raw['harvest_forecasts']['policy']='normal'
            self.start={'turn':w.turn,'policy':policy,'normalized_world_sha256':_sha(json.dumps(raw,sort_keys=True).encode()),
                'native_sha256':_sha(bytes(cp.state.agent_bridge._sim.checkpoint_state())),
                'python_rng_sha256':_sha(pickle.dumps(random.getstate())),
                'numpy_rng_sha256':_sha(pickle.dumps(np.random.get_state())),
                'runtime_fields':[k for k in ('agent_bridge','ecology_runtime','politics_runtime','economy_tracker') if getattr(cp.state,k) is not None]}
        finally:cp.state.agent_bridge.close()
    def live_record(self):return None
    def turn_end(self,world):return False


def generate(output:Path):
    import numpy as np
    import chronicler_agents.chronicler_agents as native
    from chronicler import main
    from chronicler.bundle_codec import load_bundle
    from chronicler.models import WorldState
    from chronicler.run_checkpoint import read_checkpoint
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest={'kind':'corrected-yield-full-main','state':'starting','conditions':CONDITIONS,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'rust_tree':subprocess.check_output(['git','rev-parse','HEAD:chronicler-agents'],cwd=ROOT,text=True).strip(),
        'native_sha256':_sha(Path(native.__file__).read_bytes()),'arms':{},'qualification':
        'full main, finite constructed case; threshold .6 is severe production shortfall, not full demand or household meals'}
    _json(output/'case.json',manifest)
    common=initial_world().model_dump_json();(output/'initial-world.json').write_text(common)
    bundles={};rng_at={};normalized_witness=None
    try:
        for mode in ('normal','shuffle','withhold'):
            directory=output/mode;directory.mkdir()
            world=WorldState.model_validate_json(common);world.harvest_forecasts.policy=mode
            random.seed(42);np.random.seed(42)
            witness=StartWitness(directory)
            def on_turn(snapshot,text,events,named):
                if snapshot.turn in (6,20):rng_at[(mode,snapshot.turn)]=(random.getstate(),np.random.get_state())
            args=main._build_parser().parse_args(['--seed','42','--turns','20','--regions','4','--civs','2',
                '--agents','hybrid','--grain-reserves','--grain-storage','--contact-ledger','--harvest-forecasts',
                '--transaction-receipts','--simulate-only','--checkpoint-turns','6,20',
                '--output',str(directory/'chronicle.md'),'--state',str(directory/'state.json')])
            main.execute_run(args,world=world,on_turn=on_turn,turn_boundary=witness)
            start=witness.start
            if start is None or start['turn']!=0:raise RuntimeError('missing initial full-main witness')
            key={k:v for k,v in start.items() if k!='policy'}
            if normalized_witness is None:normalized_witness=key
            elif key!=normalized_witness:raise RuntimeError('arms did not start with identical world/native/RNG/runtime')
            bundle=load_bundle(directory/'chronicle_bundle.json');bundles[mode]=bundle
            if len(bundle['history'])!=20:raise RuntimeError('full-main history incomplete')
            manifest['arms'][mode]={'start':start,'bundle':str(directory/'chronicle_bundle.json')}
        # Resume normal exactly from source boundary 6, when first reports are pending.
        cp=read_checkpoint(output/'normal'/'checkpoint_turn_6.ckpt')
        if not cp.exact or not any(r.status=='pending' for r in cp.state.world.harvest_forecasts.reports):
            raise RuntimeError('normal checkpoint has no pending report')
        resume_dir=output/'normal-resumed';resume_dir.mkdir()
        args=main._build_parser().parse_args(['--seed','42','--turns','20','--regions','4','--civs','2',
            '--agents','hybrid','--simulate-only','--checkpoint-turns','20',
            '--output',str(resume_dir/'chronicle.md'),'--state',str(resume_dir/'state.json')])
        random.setstate(rng_at[('normal',6)][0]);np.random.set_state(rng_at[('normal',6)][1])
        resumed_rng={}
        def resumed_on_turn(snapshot,text,events,named):
            if snapshot.turn==20:resumed_rng['final']=(random.getstate(),np.random.get_state())
        main.execute_run(args,checkpoint_resume=cp,on_turn=resumed_on_turn)
        resumed=load_bundle(resume_dir/'chronicle_bundle.json')
        history_equal=bundles['normal']['history']==resumed['history']
        original_final=read_checkpoint(output/'normal'/'checkpoint_turn_20.ckpt')
        resumed_final=read_checkpoint(resume_dir/'checkpoint_turn_20.ckpt')
        try:
            world_equal=original_final.state.world.model_dump_json()==resumed_final.state.world.model_dump_json()
            native_equal=(original_final.state.agent_bridge._sim.checkpoint_state()==resumed_final.state.agent_bridge._sim.checkpoint_state())
        finally:
            original_final.state.agent_bridge.close();resumed_final.state.agent_bridge.close()
        py_rng_equal=rng_at[('normal',20)][0]==resumed_rng['final'][0]
        np_rng_equal=pickle.dumps(rng_at[('normal',20)][1])==pickle.dumps(resumed_rng['final'][1])
        manifest['checkpoint']={'source_boundary':6,'pending_report':True,'history_equal':history_equal,
            'world_equal':world_equal,'native_bytes_equal':native_equal,
            'python_rng_equal':py_rng_equal,'numpy_rng_equal':np_rng_equal}
        if not (history_equal and world_equal and native_equal and py_rng_equal and np_rng_equal):raise RuntimeError('checkpoint continuation mismatch')
        history={mode:b['history'] for mode,b in bundles.items()}
        for mode,h in history.items():
            _json(output/mode/'observations.json',[{'turn':s['turn'],'harvest_forecasts':s.get('harvest_forecasts'),
                'food_accounting':s.get('food_accounting'),'transaction_receipts':s.get('transaction_receipts'),
                'grain_reserves':s.get('grain_reserves')} for s in h])
        def snap(mode,source):return history[mode][source]
        issue={m:snap(m,5)['harvest_forecasts']['reports'] for m in history}
        outcomes={m:snap(m,12)['harvest_forecasts']['outcomes'] for m in history}
        def byid(rows,key):return next((r for r in rows if r['id']==key),None)
        signals={m:byid(issue[m],'harvest:0:2:2') for m in history}
        resolved={m:byid(outcomes[m],'harvest:0:2:2') for m in history}
        severe={m:byid(outcomes[m],'harvest:0:0:1') for m in history}
        decision={m:snap(m,6)['harvest_forecasts']['procurement_decisions'] for m in history}
        admitted=all(signals[m] is not None and resolved[m] is not None and severe[m] is not None for m in history)
        admitted=bool(admitted and signals['normal']['probability']<.6<=signals['shuffle']['probability'] and
            resolved['shuffle']['outcome_shortfall'] is False and severe['shuffle']['outcome_shortfall'] is True)
        analysis={}
        for mode,h in history.items():
            rows=[row for s in h for row in s['harvest_forecasts']['procurement_decisions']['rows']]
            flow=[row for s in h for row in s['grain_reserves']['flows']]
            private=[s['transaction_receipts'] for s in h]
            for s in h:
                for region in s['food_accounting']['regions']:
                    ledger=region['native'];public=region['public']
                    if abs(ledger['balance_residual'])>ledger['balance_tolerance']:
                        raise RuntimeError('native food balance exceeded its tolerance')
                    if public is not None and abs(public['balance_residual'])>1e-7:
                        raise RuntimeError('public food balance failed')
            analysis[mode]={'procurement_paid':sum(row['paid'] for row in rows),
                'warning_paid':h[-1]['harvest_forecasts']['counters']['paid_during_warning'],
                'public_spoiled':sum(row['amount'] for row in flow if row['kind']=='spoiled'),
                'region2_public_released':sum(row['amount'] for row in flow if row['kind']=='released' and row['region']==2),
                'private_complete':all(x['complete'] and x['dropped_rows']==0 for x in private),
                'region3_opening_after_decision':h[7]['food_accounting']['regions'][3]['public']['opening'],
                'region3_later':{str(i):h[i]['food_accounting']['regions'][3] for i in (9,10,17,18)},
                'final_treasuries':{name:c['treasury'] for name,c in h[-1]['civ_stats'].items()}}
        def selected(mode,rid):return next(r for r in decision[mode]['rows'] if r['decision']['region']==rid)
        n2,n3,s2,s3=(selected('normal',2),selected('normal',3),selected('shuffle',2),selected('shuffle',3))
        allocation=(n2['decision']['opening_budget']==n3['decision']['opening_budget']==
            s2['decision']['opening_budget']==s3['decision']['opening_budget']==3 and
            [n2['paid'],n3['paid'],s2['paid'],s3['paid']]==[0,3,3,0])
        delivered=next((r for r in snap('shuffle',6)['harvest_forecasts']['reports']
                        if r['id']=='harvest:0:2:2' and r['status']=='delivered'),None)
        complete=bool(admitted and delivered and allocation and all(x['private_complete'] for x in analysis.values()))
        manifest.update(state='validated' if complete else 'partial',admission={'contrasting_scored_reports':admitted,
            'source6_warning_delivered':bool(delivered),'same_budget_diversion':allocation,
            'signals':signals,'capital2_resolved':resolved,'other_resolved':severe,'source6_decisions':decision},analysis=analysis)
        _json(output/'case.json',manifest)
        write_walkthrough(output, manifest)
    except BaseException as exc:
        manifest.update(state='failed',reason=f'{type(exc).__name__}: {exc}');_json(output/'case.json',manifest);raise
    return manifest


def write_walkthrough(output: Path, manifest: dict):
    """Explain actual outputs and qualification without promising an admission."""
    lines = [
        'Corrected-yield forecast development comparison',
        f"Qualification state: {manifest['state']}",
        'Constructed seed 42 case, not held-out or a policy recommendation.',
        'Open the production viewer and load normal/chronicle_bundle.json.',
        'Open Compare runs and load shuffle/chronicle_bundle.json; repeat for withhold.',
        'Inspect Granaries / Harvest forecasts at snapshots 6, 7 and 13.',
        'Snapshot 6 records reports; snapshot 7 records source-6 procurement.',
        'Snapshot 13 records resolution. Earlier snapshots cannot show future outcomes.',
        'The severe-production threshold is 0.6, distinct from full food demand 1.0.',
        'Food accounting separates native stock/demand before relief from public relief.',
        'Neither observation measures household meals.',
        'Read case.json for actual admissions, budget allocation, costs, spoilage and limits.',
        'A partial or failed case does not establish the intended contrast.',
        'Exact checkpoints require the same Python source, native binary and runtime identity.',
    ]
    (output / 'WALKTHROUGH.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--simulate-only',action='store_true',required=True);args=parser.parse_args()
    output=args.output.resolve()
    if args.output.is_symlink() or output.exists() or output.is_relative_to(ROOT):parser.error('choose a fresh external directory')
    if sys.version_info<(3,13) or os.environ.get('PYTHONHASHSEED')!='0' or sys.flags.hash_randomization:
        parser.error('requires CPython3.13+ and PYTHONHASHSEED=0')
    os.umask(0o077);result=generate(output);print(json.dumps({'state':result['state'],'output':str(output)}))
    return 0 if result['state']=='validated' else 1

if __name__=='__main__':raise SystemExit(main())
