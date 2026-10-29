"""Pure full-only publication metadata boundaries; no proof/world activation."""
import ast
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import sys
from types import MappingProxyType,SimpleNamespace

import pytest
from scripts import wealth_floor_outcome_qualification as O

V=O.V
ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,30,tzinfo=timezone.utc)


def prerequisite():
    return dict(proofs=dict(baseline_audit=dict(producer=dict(control_sha='a'*40,run_id=7,job_id=8))))


def worker_metadata():
    p=V.worker_publication_registration()
    run=dict(id=p['run_id'],head_sha=p['control_sha'],head_branch=p['branch'],path=p['workflow_path'],run_attempt=1,
        event='push',status='completed',conclusion='success',repository=dict(full_name=O.P.REPOSITORY))
    jobs=[dict(id=ident,run_id=p['run_id'],head_sha=p['control_sha'],run_attempt=1,name=f'smoke ({world})',status='completed',conclusion='success') for world,ident in p['jobs'].items()]
    result=dict(worker_smoke_run=dict(run=run,jobs=dict(total_count=2,jobs=jobs)))
    for world,rows in p['artifacts'].items():
        for kind,row in rows.items():result[f'worker_smoke_{world}_{kind}']=dict(id=row['id'],name=row['name'],size_in_bytes=row['bytes'],digest='sha256:'+row['sha256'],
            expires_at=row['expires_at'],expired=False,workflow_run=dict(id=p['run_id'],head_sha=p['control_sha'],head_branch=p['branch']))
    return result


def test_source_publication_facts_are_not_full_authority_and_return_is_detached(monkeypatch):
    monkeypatch.setattr(V,'ROOT_WORKER_SMOKE_PACKET_SHA256',None)
    monkeypatch.setattr(V,'REVIEWED_WORKER_SMOKES',{world:None for world in V.WORKER_KEYS})
    assert V.ROOT_WORKER_SMOKE_PACKET_SHA256 is None and all(v is None for v in V.REVIEWED_WORKER_SMOKES.values())
    value=V.worker_publication_registration();value['terminal']['root_consumer_sha256']='0'*64
    assert V.worker_publication_registration()['terminal']['root_consumer_sha256']=='5f3c14a82a4ac534238e81d6fdff45579b3fd5bc6d430ff188b6297c04509715'
    with pytest.raises(O.P.ProofRefused,match='full cohort refused'):V.registration('full')


@pytest.mark.parametrize('fault',['missing_world','extra_kind','duplicate_id','job_alias','missing_terminal','boolean_terminal','wrong_exit','missing_exit','expiry_shape'])
def test_source_metadata_schema_is_closed_and_receipt_hashes_are_not_booleans(monkeypatch,fault):
    value=V.worker_publication_registration()
    if fault=='missing_world':value['artifacts'].pop('procedural')
    elif fault=='extra_kind':value['artifacts']['template']['other']={}
    elif fault=='duplicate_id':value['artifacts']['procedural']['raw']['id']=value['artifacts']['template']['raw']['id']
    elif fault=='job_alias':value['jobs']['template']=True
    elif fault=='missing_terminal':value['terminal'].pop('root_consumer_sha256')
    elif fault=='boolean_terminal':value['terminal']['metadata_peer_sha256']=True
    elif fault=='wrong_exit':value['terminal']['exit_code']=False
    elif fault=='missing_exit':value['terminal'].pop('exit_code')
    else:value['artifacts']['template']['raw']['expires_at']='2026-11-28T09:08:00+00:00'
    monkeypatch.setattr(V,'WORKER_PUBLICATION_PINS',MappingProxyType(value))
    with pytest.raises((O.P.ProofRefused,ValueError)):V.worker_publication_registration()


def test_default_smoke_transport_is_byte_identical_to_frozen2b05():
    raw=(ROOT/'tests/fixtures/wealth_floor/source2b_transport_plan.py.txt').read_bytes()
    namespace=dict(vars(O));exec(compile(raw,'frozen2b05_transport','exec'),namespace)
    packet=prerequisite();old=namespace['transport_plan'](packet);new=O.transport_plan(packet)
    assert O.B.canonical_bytes(old)==O.B.canonical_bytes(new) and len(new)==6
    full=O.transport_plan(packet,'full');assert len(full)==13
    assert full['worker_smoke_run']==dict(run_id=40847120432)
    assert len({row['artifact_id'] for key,row in full.items() if key.startswith('worker_smoke_') and key!='worker_smoke_run'})==6


@pytest.mark.parametrize('stage',['smoke','full'])
def test_real_transport_row_shapes_assemble_run_jobs_only_without_invented_artifact(stage):
    plan=O.transport_plan(prerequisite(),stage);calls=[]
    def read(name):calls.append(name);return dict(metadata_file=name)
    result=O.assemble_publication_metadata(plan,read)
    assert set(result)==set(plan)
    if stage=='full':
        assert set(result['worker_smoke_run'])=={'run','jobs'} and 'worker_smoke_run-artifact.json' not in calls
        assert len([n for n in calls if n.startswith('worker_smoke_') and n.endswith('-artifact.json')])==6
    else:assert not any(n.startswith('worker_smoke_') for n in calls)


@pytest.mark.parametrize('fault',['single_world','wrong_job','duplicate_job','job_attempt','job_failed','job_run','run_attempt','run_sha','run_path','run_branch','run_event',
    'missing_artifact','deleted_artifact','wrong_id','duplicate_id','artifact_sha','artifact_size_alias','artifact_expiry','expired','artifact_run','artifact_source','artifact_branch','artifact_origin_unobservable'])
def test_fresh_full_producer_or_artifact_drift_refuses(fault):
    metadata=worker_metadata();wrapper=metadata['worker_smoke_run'];run=wrapper['run'];jobs=wrapper['jobs'];key='worker_smoke_template_raw';artifact=metadata[key]
    if fault=='single_world':jobs['jobs'].pop();jobs['total_count']=1
    elif fault=='wrong_job':jobs['jobs'][0]['id']=99
    elif fault=='duplicate_job':jobs['jobs'][1]=deepcopy(jobs['jobs'][0])
    elif fault=='job_attempt':jobs['jobs'][0]['run_attempt']=2
    elif fault=='job_failed':jobs['jobs'][1]['conclusion']='failure'
    elif fault=='job_run':jobs['jobs'][0]['run_id']+=1
    elif fault=='run_attempt':run['run_attempt']=2
    elif fault=='run_sha':run['head_sha']='0'*40
    elif fault=='run_path':run['path']='other.yml'
    elif fault=='run_branch':run['head_branch']='main'
    elif fault=='run_event':run['event']='workflow_dispatch'
    elif fault=='missing_artifact':metadata.pop(key)
    elif fault=='deleted_artifact':metadata[key]=None
    elif fault=='wrong_id':artifact['id']+=1
    elif fault=='duplicate_id':artifact['id']=metadata['worker_smoke_procedural_raw']['id']
    elif fault=='artifact_sha':artifact['digest']='sha256:'+'0'*64
    elif fault=='artifact_size_alias':artifact['size_in_bytes']=True
    elif fault=='artifact_expiry':artifact['expires_at']='2099-01-01T00:00:00Z'
    elif fault=='expired':artifact['expired']=True
    elif fault=='artifact_run':artifact['workflow_run']['id']+=1
    elif fault=='artifact_source':artifact['workflow_run']['head_sha']='0'*40
    elif fault=='artifact_branch':artifact['workflow_run']['head_branch']='main'
    else:artifact['workflow_run']=None
    with pytest.raises((O.P.ProofRefused,KeyError)):O.validate_worker_publications(metadata,now=NOW)


def test_exact_fresh_publications_preserve_earliest_original_expiry_and_expired_refusal():
    metadata=worker_metadata();earliest=O.validate_worker_publications(metadata,now=NOW)
    want=min((p['expires_at'] for rows in V.worker_publication_registration()['artifacts'].values() for p in rows.values()),key=V.strict_expiry)
    assert earliest==want
    with pytest.raises(O.P.ProofRefused,match='expired'):O.validate_worker_publications(metadata,now=V.strict_expiry(want))


@pytest.mark.parametrize('old_input_expired',[False,True])
def test_full_effective_retention_includes_earlier_original_inputs(monkeypatch,old_input_expired):
    metadata=worker_metadata();pins=V.REVIEWED_PRIMER
    metadata.update(build={},bootstrap={},historical_template={},historical_procedural={},baseline_audit_job={},primer=dict(
        run=dict(id=pins['run_id'],head_sha=pins['control_sha'],head_branch=O.M.ACTIVE_BRANCH,path=O.M.WORKFLOW_PATH,run_attempt=1,
            status='completed',conclusion='success',repository=dict(full_name=O.P.REPOSITORY)),
        jobs=dict(jobs=[dict(id=pins['job_id'],run_id=pins['run_id'],head_sha=pins['control_sha'],status='completed',conclusion='success')]),
        artifact=dict(id=pins['artifact_id'],size_in_bytes=pins['artifact_bytes'],digest='sha256:'+pins['artifact_sha256'],expired=False,
            expires_at=pins['artifact_expires_at'],name=f"wealth-production-primer-raw-{pins['run_id']}-1",workflow_run=dict(id=pins['run_id'],head_sha=pins['control_sha']))))
    monkeypatch.setattr(O.P,'validate_publication',lambda *_a,**_k:None)
    monkeypatch.setattr(O.M,'validate_bootstrap_publication',lambda *_a,**_k:None)
    monkeypatch.setattr(O.A,'validate_publication',lambda *_a,**_k:None)
    monkeypatch.setattr(O.A,'validate_completed_job',lambda *_a,**_k:None)
    if old_input_expired:
        build=dict(O.P.REVIEWED_BUILD);build['artifact_expires_at']='2026-10-29T00:00:00Z';monkeypatch.setattr(O.P,'REVIEWED_BUILD',MappingProxyType(build))
        with pytest.raises(O.P.ProofRefused,match='earliest nested'):O.validate_publications(metadata,prerequisite(),now=NOW,stage='full')
    else:
        retention=O.validate_publications(metadata,prerequisite(),now=NOW,stage='full')
        assert retention['effective_earliest_expires_at']==retention['original_input_earliest_expires_at']=='2026-11-28T01:15:25Z'
        assert V.strict_expiry(retention['effective_earliest_expires_at'])<V.strict_expiry(retention['worker_smoke_earliest_expires_at'])
        assert retention['original_retention_extended'] is False


@pytest.mark.parametrize('fault',[None,'fresh_failure','metadata_missing'])
def test_full_load_plan_fresh_validation_precedes_worker_read_and_actual_full_admit(monkeypatch,fault):
    calls=[];fresh=[False]
    monkeypatch.setattr(O,'registration',lambda stage:calls.append(('registration',stage)))
    def read(_control,path):
        calls.append(('read',path))
        if path==O.WORKER_PACKET_PATH:assert fresh[0]
        return {'base':True} if path==O.PREREQUISITE_PATH else {'worker':True}
    monkeypatch.setattr(O.P,'read_json',read)
    def validate(*_a,**kw):
        calls.append(('fresh',kw['stage']))
        if fault=='fresh_failure':raise O.P.ProofRefused('fixture fresh origin refused')
        fresh[0]=True
    def admit(packet,stage,worker):calls.append(('admit',stage));assert fresh[0] and worker=={'worker':True};return 'fixture_plan'
    monkeypatch.setattr(O,'validate_publications',validate);monkeypatch.setattr(V,'admit_plan',admit)
    if fault:
        with pytest.raises(O.P.ProofRefused):O.load_plan(ROOT,'full',metadata=None if fault=='metadata_missing' else {},now=NOW)
        assert ('read',O.WORKER_PACKET_PATH) not in calls and ('admit','full') not in calls
    else:
        assert O.load_plan(ROOT,'full',metadata={},now=NOW)=='fixture_plan'
        assert calls==[('registration','full'),('read',O.PREREQUISITE_PATH),('fresh','full'),('read',O.WORKER_PACKET_PATH),('admit','full')]


def test_full_preflight_reads_only_base_proof_and_source_metadata_transport(monkeypatch,tmp_path):
    calls=[];packet=prerequisite()
    monkeypatch.setattr(O,'registration',lambda stage:calls.append(('registration',stage)))
    def load(_control,stage,**kw):calls.append(('load',stage));assert stage=='smoke' and not kw;return SimpleNamespace(prerequisite_packet=O.B.canonical_bytes(packet))
    monkeypatch.setattr(O,'load_plan',load)
    monkeypatch.setattr(O.P,'read_json',lambda *_a,**_k:pytest.fail('full preflight read worker proof before GET'))
    monkeypatch.setattr(O.P,'hosted_vm_precondition',lambda:{'fixture_only':True})
    resource_module=sys.modules['wealth_floor_build_resources'];monkeypatch.setattr(resource_module,'memory_admission',lambda:dict(available_bytes=3*1024**3))
    monkeypatch.setattr(O.shutil,'disk_usage',lambda _:SimpleNamespace(free=13*1024**3))
    monkeypatch.setattr(O.platform,'python_version',lambda:O.B.PYTHON_VERSION)
    for key,value in dict(GITHUB_REF='refs/heads/'+O.ACTIVE_BRANCH,GITHUB_RUN_ATTEMPT='1',GITHUB_SHA='a'*40,GITHUB_RUN_ID='9',RUNNER_TEMP=str(tmp_path),GITHUB_OUTPUT=str(tmp_path/'github-output')).items():monkeypatch.setenv(key,value)
    assert O.preflight(SimpleNamespace(stage='full',worldgen='template'))==0
    assert calls==[('registration','full'),('load','smoke')]
    plan=json.loads((tmp_path/'wealth-outcome-transport-plan.json').read_bytes());assert len(plan)==13 and plan['worker_smoke_run']==dict(run_id=40847120432)


def test_smoke_validate_cli_keeps_original_plan_before_metadata_order(monkeypatch):
    calls=[]
    monkeypatch.setattr(O,'registration',lambda stage:calls.append('registration'))
    monkeypatch.setattr(O,'staging_observation',lambda *_:None)
    monkeypatch.setattr(O,'load_plan',lambda *_a,**_k:(calls.append('plan') or SimpleNamespace(prerequisite_packet=O.B.canonical_bytes({}))))
    monkeypatch.setattr(O.P,'read_json',lambda *_a,**_k:(calls.append('metadata') or {}))
    monkeypatch.setattr(O,'validate_publications',lambda *_a,**_k:calls.append('validate'))
    monkeypatch.setenv('RUNNER_TEMP','fixture-unused')
    assert O.main(['--validate-publication','--stage','smoke','--worldgen','template'])==0
    assert calls==['registration','plan','metadata','validate']
