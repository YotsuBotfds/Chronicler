"""One constructed full-main forecast control; not a robustness campaign."""
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip('chronicler_agents')
pytestmark = pytest.mark.native


def test_initial_effective_yield_contract_and_earlier_mismatch():
    from scripts.crisis_forecast_misleading_example import initial_world
    from chronicler.ecology import yield_penalty_factor
    from chronicler.world_gen import generate_world
    world=initial_world(); region=world.regions[2]
    assert region.resource_base_yields == region.resource_effective_yields == [1.8,0.,0.]
    assert yield_penalty_factor(region,0)==1.
    # Original heterogeneous fixture changed base alone, retaining the generated
    # effective value: preserve that negative as a distinct configuration.
    generated=generate_world(seed=42,num_regions=4,num_civs=2)
    region.resource_effective_yields=list(generated.regions[2].resource_effective_yields)
    assert 0 < yield_penalty_factor(region,0) < 1
    assert region.resource_base_yields[0]*yield_penalty_factor(region,0)==pytest.approx(
        generated.regions[2].resource_effective_yields[0])


def test_full_main_false_warning_observation_and_exact_resume(tmp_path):
    from scripts.crisis_forecast_misleading_example import ROOT
    env=os.environ.copy();env['PYTHONHASHSEED']='0'
    env['PYTHONPATH']=str(ROOT/'src')+os.pathsep+str(ROOT)
    out=tmp_path/'case'
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/crisis_forecast_misleading_example.py'),
        str(out),'--simulate-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=90)
    assert proc.returncode==0,proc.stdout+'\n'+proc.stderr
    case=json.loads((out/'case.json').read_text())
    assert case['state']=='validated'
    assert all(case['checkpoint'][k] for k in ('pending_report','history_equal','world_equal',
                                               'native_bytes_equal','python_rng_equal','numpy_rng_equal'))
    starts=[{k:v for k,v in x['start'].items() if k!='policy'} for x in case['arms'].values()]
    assert starts[0]==starts[1]==starts[2]
    admission=case['admission']
    assert admission['contrasting_scored_reports'] and admission['source6_warning_delivered'] and admission['same_budget_diversion']
    outcome=admission['capital2_resolved']['shuffle']
    assert outcome['outcome_shortfall'] is False and .6 <= outcome['observed_ratio'] < 1.
    assert admission['other_resolved']['shuffle']['outcome_shortfall'] is True
    assert admission['signals']['shuffle']['estimator_metadata']['estimate_origin_region']==0
    assert admission['signals']['normal']['estimator_metadata']['estimate_origin_region']==2
    normal=admission['source6_decisions']['normal']['rows']
    shuffle=admission['source6_decisions']['shuffle']['rows']
    def pay(rows,region):return next(r for r in rows if r['decision']['region']==region)
    assert [pay(normal,2)['paid'],pay(normal,3)['paid'],pay(shuffle,2)['paid'],pay(shuffle,3)['paid']]==[0,3,3,0]
    assert all(pay(rows,region)['decision']['opening_budget']==3 for rows in (normal,shuffle) for region in (2,3))
    for name in ('normal','shuffle','withhold'):
        timeline=json.loads((out/name/'observations.json').read_text())
        assert len(timeline)==20
        assert all(s['transaction_receipts']['complete'] and s['transaction_receipts']['dropped_rows']==0 for s in timeline)
        ratios=[]
        for i in (9,10,11):
            native=timeline[i]['food_accounting']['regions'][2]['native']
            ratios.append(native['produced']/native['demand'])
        assert sum(ratios)/3 == pytest.approx(outcome['observed_ratio'])
        assert case['analysis'][name]['private_complete']
    assert case['analysis']['shuffle']['procurement_paid']>case['analysis']['normal']['procurement_paid']
    assert case['analysis']['shuffle']['public_spoiled']>case['analysis']['normal']['public_spoiled']
    assert all(case['analysis'][mode]['region2_public_released']==0 for mode in ('normal','shuffle','withhold'))
