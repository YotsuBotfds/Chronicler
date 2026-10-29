"""Tiny fake jobs/metadata/files only; no product, native, process or network."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

import pytest

@pytest.fixture
def tmp_path(tmp_path_factory, request):
    """Retained regular-only fixture namespace; avoid pytest current symlinks."""
    name = "forecast-" + hashlib.sha256(request.node.nodeid.encode()).hexdigest()
    return tmp_path_factory.mktemp(name, numbered=False)


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('_test_forecast_' + name, ROOT / 'scripts' / ('forecast_credibility_' + name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S, O, P, T = (load(name) for name in ('study', 'owner', 'publish', 'transport'))


def binding():
    value = json.loads((ROOT / 'docs/experiments/forecast-credibility-inputs.json').read_bytes())['binding']
    value['candidate'] = dict(source='a'*40, package_digest='b'*64, runner_sha256='c'*64, pyproject_sha256='d'*64, lock_sha256='e'*64)
    value['candidate_ci'] = dict(source='a'*40, run_id=123, attempt=1, conclusion='success', root_receipt_sha256='f'*64, independent_receipt_sha256='1'*64)
    return value


def test_literal_matrix_is_closed_and_accounts_for_actual_turns():
    jobs = json.loads((ROOT / 'docs/experiments/forecast-credibility-jobs.json').read_bytes())
    assert S.validate_jobs(jobs) == S.JOBS
    assert sum(26 - row['start_turn'] for row in jobs) == 315
    assert sum(row['parent'] is None for row in jobs) == 7
    assert [r['start_turn'] for r in jobs if r['kind'] == 'exact'] == [4, 6, 8, 10, 13]


@pytest.mark.parametrize('index', range(14))
def test_each_literal_role_rejects_changed_start(index):
    jobs = deepcopy(S.JOBS); jobs[index]['start_turn'] += 1
    with pytest.raises(S.Refused): S.validate_jobs(jobs)


@pytest.mark.parametrize('change', ['order', 'extra', 'fewer', 'bool', 'checkpoint', 'policy'])
def test_matrix_rejects_adaptive_or_unregistered_changes(change):
    jobs = deepcopy(S.JOBS)
    if change == 'order': jobs.reverse()
    elif change == 'extra': jobs.append(deepcopy(jobs[-1]))
    elif change == 'fewer': jobs.pop()
    elif change == 'bool': jobs[0]['start_turn'] = False
    elif change == 'checkpoint': jobs[5]['checkpoint_turns'] = [5]
    else: jobs[5]['mode'] = 'fixed'
    with pytest.raises(S.Refused): S.validate_jobs(jobs)


def test_dormant_binding_and_all_execution_entrypoints_refuse():
    config = json.loads((ROOT / 'docs/experiments/forecast-credibility-inputs.json').read_bytes())
    assert config['execution_approval'] is None and O.EXECUTION_APPROVAL is None
    assert all(v is None for v in config['binding']['candidate'].values())
    assert all(v is None for v in config['binding']['candidate_ci'].values())
    with pytest.raises(S.Refused): S.validate_binding(config['binding'])
    for call in (lambda: O.main([]), lambda: O.execute(None), lambda: O.child(None)):
        with pytest.raises(O.Refused, match='null'): call()


@pytest.mark.parametrize('change', ['candidate', 'ci_source', 'attempt', 'ci_result', 'native', 'wheel', 'producer', 'baseline', 'extra'])
def test_reviewed_binding_cannot_borrow_or_substitute_inputs(change):
    value = binding()
    if change == 'candidate': value['candidate']['source'] = None
    elif change == 'ci_source': value['candidate_ci']['source'] = '2'*40
    elif change == 'attempt': value['candidate_ci']['attempt'] = True
    elif change == 'ci_result': value['candidate_ci']['conclusion'] = 'failure'
    elif change == 'native': value['native']['sha256'] = '2'*64
    elif change == 'wheel': value['native']['wheel_bytes'] += 1
    elif change == 'producer': value['native']['producer']['source'] = '2'*40
    elif change == 'baseline': value['baseline']['package_digest'] = '2'*64
    else: value['unknown'] = {}
    with pytest.raises(S.Refused): S.validate_binding(value)


def test_valid_fake_binding_is_detached_and_null_claims_remain_null():
    value = binding(); observed = S.registration(value, deepcopy(S.JOBS))
    assert observed['unsupported'] and all(v is None for v in observed['unsupported'].values())
    assert len(observed['checkpoint_comparisons']) == 5
    observed['binding']['candidate']['source'] = '0'*40
    assert value['candidate']['source'] == 'a'*40


def job(index, **kw):
    return S.simulation_job(deepcopy(S.JOBS[index]), root='/tmp/fake-study', sources={'baseline':'/tmp/fake-baseline','candidate':'/tmp/fake-candidate'}, registration_path='/tmp/fake-control/registration.md', registration_sha256='a'*64, **kw)


@pytest.mark.parametrize('index', [0,1,2,3,4,9,10,11,12,13])
def test_plain_and_exact_jobs_use_production_cli_without_new_request(index):
    value = job(index)
    assert value['request'] is None and value['entrypoint'] == 'stock_cli'
    assert value['simulation_args'][value['simulation_args'].index('--turns') + 1] == '26'
    if index >= 9:
        assert '--resume' in value['simulation_args']
        assert '--harvest-forecasts' not in value['simulation_args']
        assert '--resume-allow-mismatch' not in value['simulation_args']


def test_reference_preserves_parent_request_and_only_output_checkpoint_arguments_change():
    parent, reference = job(5), job(8)
    assert parent['request'] == reference['request']
    def stripped(args):
        args = list(args)
        for key in ('--output','--state','--checkpoint-turns'):
            at = args.index(key); del args[at:at+2]
        return args
    assert stripped(parent['simulation_args']) == stripped(reference['simulation_args'])
    assert parent['request']['controls'] == {'preparation_policy':'local_credibility'}


@pytest.mark.parametrize('index,policy', [(6,'normal'),(7,'withhold')])
def test_stock_forks_bind_same_actual_parent_and_only_delivery_control(index,policy):
    value = job(index,parent_sha256='b'*64)
    assert value['entrypoint'] == 'normal_runner_job'
    assert value['request']['fork'] is True
    assert value['request']['controls'] == {'policy':policy,'preparation_policy':'local_credibility'}
    assert value['request']['parent_checkpoint'] == {'path':'/tmp/fake-study/roles/local-parent/ordinary/checkpoint_turn_4.ckpt','sha256':'b'*64}


def test_unregistered_spec_and_missing_parent_hash_refuse():
    with pytest.raises(S.Refused): job(6)
    spec=deepcopy(S.JOBS[0]);spec['mode']='local'
    with pytest.raises(S.Refused): S.simulation_job(spec,root='/tmp/f',sources={'baseline':'/tmp/b','candidate':'/tmp/c'},registration_path='/tmp/r',registration_sha256='a'*64)


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'])
def test_control_and_publication_strict_json_refuse(raw):
    for parse in (S.strict_json,P.strict_json):
        with pytest.raises(ValueError): parse(raw)


def test_child_environment_is_closed_nonsecret_and_hash_caps_fixed(monkeypatch):
    monkeypatch.setenv('GH_TOKEN','fake-secret'); monkeypatch.setenv('ACTIONS_RUNTIME_TOKEN','fake-secret')
    monkeypatch.setenv('PYTHONPATH','/fake'); monkeypatch.setenv('LD_PRELOAD','/fake')
    selected=O.child_environment()
    assert not set(selected) & {'GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN','PYTHONPATH','LD_PRELOAD'}
    assert selected['PYTHONHASHSEED']=='0' and selected['RAYON_NUM_THREADS']=='1'
    assert O.python_command('/tmp/python','fake.py') == ['/tmp/python','-P','-s','-B','-X','cpu_count=1','fake.py']


def test_inventory_hashes_all_files_and_refuses_caps(tmp_path):
    (tmp_path/'data').write_bytes(b'abc')
    observed=O.inventory(tmp_path,max_bytes=3,max_files=1)
    assert observed == {'files':{'data':{'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}},'file_count':1,'bytes':3}
    with pytest.raises(O.Refused): O.inventory(tmp_path,max_bytes=2,max_files=1)
    with pytest.raises(O.Refused): O.inventory(tmp_path,max_bytes=3,max_files=0)


def test_finalizer_requires_inventory_and_keeps_negative_authority(tmp_path):
    report={'errors':[],'cleanup_complete':False}
    assert O.finalize(tmp_path,report,False,lambda:None,0,0,S.LIMITS) is False
    assert json.loads((tmp_path/'terminal-failure.json').read_bytes())['complete'] is False
    assert json.loads((tmp_path/'result.json').read_bytes())['complete'] is False


def test_postterminal_guard_failure_invalidates_written_positive(tmp_path,monkeypatch):
    report={'errors':[],'cleanup_complete':True,'retained_inventory':{'bytes':0,'file_count':0}}
    calls=[]
    def guard():
        calls.append(1)
        if len(calls)==2: raise O.Refused('fake late resource loss')
    monkeypatch.setattr(O.time,'monotonic',lambda:1); monkeypatch.setattr(O,'cpu_seconds',lambda:1)
    assert O.finalize(tmp_path,report,True,guard,0,0,S.LIMITS) is False
    assert len(calls)==2
    assert json.loads((tmp_path/'terminal.json').read_bytes())['complete'] is False
    assert (tmp_path/'terminal-failure.json').exists()


def publication_fixture(root):
    root.mkdir()
    values={name:{} for name in P.selected_paths() if name!='terminal-failure.json'}
    values.update({'packages-before.json':[{'name':'fake','version':'1'}],'packages-after.json':[{'name':'fake','version':'1'}],
                   'mechanics.json':{'complete':True}})
    result={'complete':True,'cleanup_complete':True,'errors':[],'actual_simulation_roles':14,'actual_executed_ticks':315,
            'actual_fresh_Worlds':7,'actual_restored_roles':7,'producer':{'GITHUB_SHA':'a'*40}}
    raw=lambda value:(json.dumps(value,sort_keys=True)+'\n').encode()
    result['mechanical_readout_sha256']=hashlib.sha256(raw(values['mechanics.json'])).hexdigest()
    values['result.json']=result
    values['terminal.json']={'complete':True,'cleanup_complete':True,'required_wrapper_exit':0,'result_sha256':hashlib.sha256(raw(result)).hexdigest()}
    for name,value in values.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw(value))
    return values


def test_fake_publication_closes_only_metadata_and_keeps_original_qualification_null(tmp_path):
    root=tmp_path/'root';publication_fixture(root)
    result=P.publish(root,tmp_path/'published',owner_outcome='success',source='a'*40)
    assert result['complete'] is True and result['source_publication_qualified'] is False
    assert result['raw_payload_retained'] is False and result['retained_bytes'] < P.TOTAL_LIMIT
    assert not any(name.endswith(('.ckpt','.arrow','.so')) for name in result['files'])


@pytest.mark.parametrize('change',['owner','terminal','result_hash','readout','missing','packages','sentinel'])
def test_fake_publication_rejects_missing_failed_or_changed_authority(tmp_path,change):
    root=tmp_path/'root'; values=publication_fixture(root)
    if change=='terminal': (root/'terminal.json').write_text('{}')
    elif change=='result_hash': (root/'result.json').write_text('{}')
    elif change=='readout': (root/'mechanics.json').write_text('{"complete":false}')
    elif change=='missing': (root/'admission.json').rename(root/'not-admission.json')
    elif change=='packages': (root/'packages-after.json').write_text('[]')
    elif change=='sentinel': (root/'terminal-failure.json').write_text('{}')
    result=P.publish(root,tmp_path/'published',owner_outcome='failure' if change=='owner' else 'success',source='a'*40)
    assert result['complete'] is False
    assert (tmp_path/'published/publication.json').exists()


def fake_zip(rows):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,body in rows: archive.writestr(name,body)
    stream.seek(0);return stream


def test_transport_checks_closed_member_bytes_not_archive_paths():
    content=b'fake wheel metadata'; registered={'registered':{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}}
    observed,kept=T.verify_zip(fake_zip([('registered',content)]),registered,expanded_limit=100,member_limit=100,keep=('registered',))
    assert observed==registered and kept=={'registered':content}
    for rows in ([('../escape',content)],[('registered',b'wrong')],[('registered',content),('extra',b'x')]):
        with pytest.raises(T.Refusal): T.verify_zip(fake_zip(rows),registered,expanded_limit=100,member_limit=100)


def test_four_helper_and_transport_bytes_remain_exact_donors():
    config=json.loads((ROOT/'docs/experiments/forecast-credibility-inputs.json').read_bytes())
    for name,pin in config['helper_pins'].items():
        raw=(ROOT/'scripts'/name).read_bytes()
        assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    assert hashlib.sha256((ROOT/'scripts/forecast_credibility_transport.py').read_bytes()).hexdigest()==config['transport_donor_sha256']


# Authenticated-current-job clock admission: invented metadata only.
def current_job_clock_inputs():
    producer = {'repository':S.REPOSITORY,'source':'a'*40,'run_id':7,'attempt':1,
                'workflow':S.STUDY_WORKFLOW,'job':S.STUDY_JOB,'event':'push'}
    run = {'id':7,'head_sha':'a'*40,'run_attempt':1,'path':S.STUDY_WORKFLOW,'event':'push',
           'head_branch':S.STUDY_BRANCH,
           'status':'in_progress','conclusion':None,'repository':{'id':S.REPOSITORY_ID,'full_name':S.REPOSITORY}}
    job = {'id':9,'run_id':7,'run_attempt':1,'head_sha':'a'*40,'name':S.STUDY_JOB,
           'status':'in_progress','conclusion':None,'completed_at':None,'started_at':'2026-10-29T18:59:00Z'}
    return producer, run, {'total_count':1,'jobs':[job]}


def admit_clock(producer=None, run=None, jobs=None, **kw):
    inputs = current_job_clock_inputs()
    return S.admit_job_clock(inputs[0] if producer is None else producer,
           inputs[1] if run is None else run, inputs[2] if jobs is None else jobs,
           http_date=kw.pop('http_date','Thu, 29 Oct 2026 19:00:00 GMT'),
           http_age=kw.pop('http_age',None),run_http_age=kw.pop('run_http_age',None),
           utc_before=kw.pop('utc_before','2026-10-29T18:59:59.500000Z'),
           utc_after=kw.pop('utc_after','2026-10-29T19:00:00.500000Z'),
           monotonic_before=kw.pop('monotonic_before',100.0),monotonic_after=kw.pop('monotonic_after',101.0),
           boot_id=kw.pop('boot_id','01234567-89ab-cdef-0123-456789abcdef'),**kw)


def test_current_job_clock_uses_actual_server_date_and_conservative_start_sample():
    producer,run,jobs=current_job_clock_inputs()
    result=admit_clock(producer,run,jobs)
    assert result['monotonic_deadline']==2735.0
    assert result['observed']['monotonic_before']==100.0
    assert result['observed']['monotonic_after']==101.0
    assert result['control_producer']==producer and result['complete'] is True
    run['head_sha']='b'*40
    assert result['observed']['run']['head_sha']=='a'*40


@pytest.mark.parametrize('field,value',[
    ('repository','other/repo'),('source','bad'),('run_id',True),('run_id',0),('attempt',True),
    ('attempt',2),('workflow','.github/workflows/other.yml'),('job','other'),('event','workflow_dispatch'),
])
def test_current_job_clock_rejects_wrong_control_producer(field,value):
    producer,run,jobs=current_job_clock_inputs();producer[field]=value
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)


@pytest.mark.parametrize('field,value',[
    ('id',8),('id',True),('head_sha','b'*40),('run_attempt',2),('run_attempt',True),
    ('path','.github/workflows/other.yml'),('event','workflow_dispatch'),('head_branch','other'),('status','completed'),
    ('conclusion','success'),('repository',{'id':S.REPOSITORY_ID,'full_name':'other/repo'}),
    ('repository',{'id':True,'full_name':S.REPOSITORY}),
])
def test_current_job_clock_rejects_wrong_or_completed_run(field,value):
    producer,run,jobs=current_job_clock_inputs();run[field]=value
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)


@pytest.mark.parametrize('defect',['missing','duplicate','count_bool','count_wrong'])
def test_current_job_clock_requires_the_single_exact_current_job(defect):
    producer,run,jobs=current_job_clock_inputs()
    if defect=='missing':jobs['jobs']=[]
    elif defect=='duplicate':jobs['jobs'].append(deepcopy(jobs['jobs'][0]))
    elif defect=='count_bool':jobs['total_count']=True
    else:jobs['total_count']=2
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)


@pytest.mark.parametrize('field,value',[
    ('id',False),('run_id',8),('run_attempt',True),('head_sha','b'*40),('name','other'),
    ('status','queued'),('status','completed'),('conclusion','failure'),('completed_at','2026-10-29T19:00:00Z'),
])
def test_current_job_clock_requires_actual_in_progress_job_source_and_attempt(field,value):
    producer,run,jobs=current_job_clock_inputs();jobs['jobs'][0][field]=value
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)


@pytest.mark.parametrize('started',[
    None,'2026-10-29Z','2026-10-29T19:00:01Z','2026-10-29T18:10:00Z','2026-10-29T18:59:00+00:00',
])
def test_current_job_clock_refuses_missing_future_expired_or_noncanonical_start(started):
    producer,run,jobs=current_job_clock_inputs();jobs['jobs'][0]['started_at']=started
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)


@pytest.mark.parametrize('dated',[None,'bad','Thu, 29 Oct 2026 19:00:00 +0000','Thu, 29 Oct 2026 19:00:00 PST'])
def test_current_job_clock_requires_authenticated_canonical_http_date(dated):
    with pytest.raises(S.Refused):admit_clock(http_date=dated)


@pytest.mark.parametrize('before,after',[(True,101.0),(100.0,99.0),(100.0,116.0),(float('nan'),101.0),(100.0,float('inf'))])
def test_current_job_clock_rejects_unbounded_or_inconsistent_monotonic_samples(before,after):
    with pytest.raises(S.Refused):admit_clock(monotonic_before=before,monotonic_after=after)


def test_clock_refuses_insufficient_publication_reserve_and_wrong_boot_shape():
    producer,run,jobs=current_job_clock_inputs();jobs['jobs'][0]['started_at']='2026-10-29T18:19:00Z'
    with pytest.raises(S.Refused):admit_clock(producer,run,jobs)
    with pytest.raises(S.Refused):admit_clock(boot_id='not-a-boot-identity')


def test_effective_owner_deadline_reserves_publication_without_increasing_owner_cap():
    assert S.effective_owner_deadline(100.0,3000.0,110.0)==2500.0
    assert S.effective_owner_deadline(100.0,2735.0,110.0)==2480.0
    assert S.effective_owner_deadline(100.0,1000.0,110.0)==745.0
    assert S.LIMITS['owner_wall_seconds']==2400 and S.LIMITS['owner_cpu_seconds']==1800
    assert S.LIMITS['final_wall_reserve']==150 and S.LIMITS['final_cpu_reserve']==100


@pytest.mark.parametrize('started,deadline,now',[(100.0,400.0,110.0),(100.0,3000.0,99.0),(100.0,float('inf'),110.0)])
def test_effective_owner_deadline_refuses_missing_final_reserve_or_bad_clock(started,deadline,now):
    with pytest.raises(S.Refused):S.effective_owner_deadline(started,deadline,now)


def test_supervisor_soft_and_final_deadlines_tighten_together_without_extension():
    supervisor=SimpleNamespace(overall_deadline=2500.0,deadline=2475.0)
    O.tighten_deadlines(supervisor,2400.0)
    assert supervisor.overall_deadline==2400.0 and supervisor.deadline==2375.0
    with pytest.raises(O.Refused):O.tighten_deadlines(supervisor,2450.0)
    assert supervisor.overall_deadline==2400.0 and supervisor.deadline==2375.0


class FakeClockConnection:
    def __init__(self,run,jobs,*,oversize=False):
        self.rows=[run,jobs];self.paths=[];self.checks=0;self.oversize=oversize
    def api(self,path):
        self.paths.append(path)
        data=json.dumps(self.rows[len(self.paths)-1]).encode()
        if self.oversize:data=b'x'*(2*1024**2+1)
        stream=io.BytesIO(data);stream.headers={'Date':'Thu, 29 Oct 2026 19:00:00 GMT'}
        return stream
    def check(self):self.checks+=1


def test_clock_intake_uses_only_two_closed_metadata_endpoints_and_server_header():
    producer,run,jobs=current_job_clock_inputs();connection=FakeClockConnection(run,jobs)
    observed=iter([100.0,101.0])
    utc=iter(['2026-10-29T18:59:59.500000Z','2026-10-29T19:00:00.500000Z'])
    result=O.observe_job_clock(S,connection,producer,'01234567-89ab-cdef-0123-456789abcdef',
            monotonic=lambda:next(observed),utcnow=lambda:next(utc))
    assert result==admit_clock(producer,run,jobs)
    assert connection.paths==['/actions/runs/7','/actions/runs/7/jobs?filter=latest&per_page=100']
    assert connection.checks==2


def test_clock_intake_does_not_clip_metadata_overflow_or_accept_injected_endpoint():
    producer,run,jobs=current_job_clock_inputs();connection=FakeClockConnection(run,jobs,oversize=True)
    with pytest.raises(O.Refused):O.observe_job_clock(S,connection,producer,'01234567-89ab-cdef-0123-456789abcdef')
    assert len(connection.paths)==1
    producer['run_id']='7/../../private';connection=FakeClockConnection(run,jobs)
    with pytest.raises(O.Refused):O.observe_job_clock(S,connection,producer,'01234567-89ab-cdef-0123-456789abcdef')
    assert connection.paths==[]


@pytest.mark.parametrize('age',['1','60','00','bad',' 0',0,True])
def test_current_job_clock_rejects_nonzero_or_malformed_cache_age(age):
    with pytest.raises(S.Refused):admit_clock(http_age=age)


def test_current_job_clock_rejects_aged_run_response_even_with_fresh_jobs():
    with pytest.raises(S.Refused):admit_clock(run_http_age='60')


def test_current_job_clock_admits_exact_zero_age_only_with_fresh_request_witnesses():
    result=admit_clock(http_age='0',run_http_age='0')
    assert result['monotonic_deadline']==2735.0
    assert result['observed']['http_age']==result['observed']['run_http_age']=='0'


@pytest.mark.parametrize('date,before,after',[
    ('Thu, 29 Oct 2026 19:00:00 GMT','2026-10-29T19:00:20Z','2026-10-29T19:00:21Z'),
    ('Thu, 29 Oct 2026 19:00:10 GMT','2026-10-29T18:59:59.500000Z','2026-10-29T19:00:00.500000Z'),
])
def test_authenticated_but_stale_or_future_server_date_is_not_fresh_enough(date,before,after):
    with pytest.raises(S.Refused):admit_clock(http_date=date,http_age='0',utc_before=before,utc_after=after)


@pytest.mark.parametrize('before,after',[
    ('2026-10-29T19:00:00Z','2026-10-29T18:59:59Z'),
    ('2026-10-29T19:00:00Z','2026-10-29T19:00:10Z'),
    ('2026-10-29T19:00:00+00:00','2026-10-29T19:00:01Z'),
])
def test_clock_step_or_noncanonical_request_utc_refuses_instead_of_retiming_job(before,after):
    with pytest.raises(S.Refused):admit_clock(utc_before=before,utc_after=after)
