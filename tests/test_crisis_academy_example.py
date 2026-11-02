"""One fixed full-main native academy development example, not a campaign gate."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip('chronicler_agents')
pytestmark = pytest.mark.native


def test_full_main_case_keeps_declared_history_and_real_observations(tmp_path):
    from scripts.crisis_academy_example import CONDITIONS, ROOT
    env=os.environ.copy()
    env['PYTHONHASHSEED']='0'
    env['PYTHONPATH']=str(ROOT/'src')+os.pathsep+str(ROOT)
    output=tmp_path/'case'
    cmd=[sys.executable,str(ROOT/'scripts/crisis_academy_example.py'),str(output),'--simulate-only']
    result=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0, result.stdout+'\n'+result.stderr
    manifest=json.loads((output/'crisis-case.json').read_text())
    assert manifest['conditions']==CONDITIONS
    assert manifest['state'] in ('validated','partial')
    if manifest['state']=='partial':
        assert manifest['reason']
        return
    admission=manifest['admission']; turn=admission['source_turn']
    assert 12<=turn<=18 and admission['complete_prior_history_turns']==list(range(1,turn+1))
    assert 'agent_bridge' in admission['runtime_fields'] and 'economy_tracker' in admission['runtime_fields']
    assert admission['original_unchanged'] and not admission['baseline_new_seats']
    assert manifest['initial_loss']['lost']>0 and admission['founding_events']
    assert manifest['pair_manifest']['intervention']['fee']==30
    assert admission['paid_purchases'] and admission['native_teaching']
    assert all(p['purchased']>0 and p['paid']>0 for p in admission['paid_purchases'])
    assert all(t['work_delivered']>0 and t['crafts_used']>0 for t in admission['native_teaching'])
    assert (Path(manifest['exact_pair_directory'])/'common.ckpt').is_file()
