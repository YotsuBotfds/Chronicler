"""Invented retained-file/clock/metadata cases only; no actual upload or World."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load('_forecast_publication_test_subject', ROOT / 'scripts/forecast_credibility_publish.py')
S = load('_forecast_publication_study_test_subject', ROOT / 'scripts/forecast_credibility_study.py')
SOURCE = 'a' * 40
BOOT = '00000000-0000-0000-0000-000000000001'


@pytest.fixture
def tmp_path(tmp_path_factory, request):
    name = 'forecast-' + hashlib.sha256(request.node.nodeid.encode()).hexdigest()
    return tmp_path_factory.mktemp(name, numbered=False)


def raw(value):
    return P.canonical(value)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw(value))


def pin(path):
    body = path.read_bytes()
    return {'bytes':len(body), 'sha256':hashlib.sha256(body).hexdigest()}


def budget(now=1100.0):
    return P.Budget(30, 20, now=lambda:now, cpu_now=lambda:0.0)


def fake_binding():
    value = json.loads((ROOT / 'docs/experiments/forecast-credibility-inputs.json').read_bytes())['binding']
    value['candidate'] = dict(source='b'*40, package_digest='c'*64, runner_sha256='d'*64,
        pyproject_sha256='e'*64, lock_sha256='f'*64)
    value['candidate_ci'] = dict(source='b'*40, run_id=123, attempt=1, conclusion='success',
        root_receipt_sha256='1'*64, independent_receipt_sha256='2'*64)
    return value


def fake_clock():
    producer = {'repository':'YotsuBotfds/Chronicler','source':SOURCE,'run_id':700,'attempt':1,
        'workflow':'.github/workflows/forecast-credibility-study.yml','job':'forecast-credibility-study','event':'push'}
    run = {'id':700,'head_sha':SOURCE,'run_attempt':1,'path':producer['workflow'],'event':'push',
        'status':'in_progress','conclusion':None,'head_branch':'lead/cloud-forecast-local-credibility-h26-20261029','repository':{'id':1187468861,'full_name':producer['repository']}}
    job = {'id':701,'run_id':700,'run_attempt':1,'head_sha':SOURCE,'name':producer['job'],
        'status':'in_progress','conclusion':None,'completed_at':None,'started_at':'2026-10-29T19:00:00Z'}
    return S.admit_job_clock(producer, run, {'total_count':1,'jobs':[job]},
        http_date='Thu, 29 Oct 2026 19:01:00 GMT', monotonic_before=1000.0, monotonic_after=1001.0, boot_id=BOOT,
        http_age=None, run_http_age='0', utc_before='2026-10-29T19:00:59Z', utc_after='2026-10-29T19:01:00Z')


def control_fixture(path):
    path.mkdir()
    config = json.loads((ROOT / 'docs/experiments/forecast-credibility-inputs.json').read_bytes())
    config['binding'] = fake_binding()
    config['execution_approval'] = '3'*64  # Invented approval; no owner or runtime is called.
    names = ('scripts/forecast_credibility_owner.py','scripts/forecast_credibility_study.py',
        'scripts/forecast_credibility_publish.py','docs/experiments/forecast-credibility-inputs.json',
        'docs/experiments/forecast-credibility-jobs.json','docs/experiments/forecast-credibility-registration.md',
        'docs/experiments/forecast-credibility-source-pins.json')
    for relative in names[:3]:
        target = path / relative; target.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith('owner.py'):
            target.write_text('CONTROL_FILES = ' + repr(names) + '\n')
        else:
            target.write_bytes((ROOT / relative).read_bytes())
    write(path / names[3], config)
    write(path / names[4], S.JOBS)
    pins = {name:pin(path/name) for name in names[:5]}
    write(path / names[6], pins)
    (path / names[5]).write_text('Invented frozen protocol\nSource manifest SHA-256: `'
        + hashlib.sha256((path/names[6]).read_bytes()).hexdigest() + '`\n')
    return config


def reseal(root, clock, *, complete=True, cleanup=True):
    records = {}
    for name, start in zip(P.ROLE_NAMES, P.STARTS):
        folder = root / 'roles' / name / 'ordinary'
        ordinary = {file.relative_to(folder).as_posix():pin(file) for file in sorted(folder.rglob('*')) if file.is_file()}
        records[name] = {'status':'complete','observed_ticks':26-start,'inventory':ordinary}
    write(root / 'roles.json', records)
    files = {file.relative_to(root).as_posix():pin(file) for file in sorted(root.rglob('*'))
        if file.is_file() and file.name not in P.AUTHORITIES}
    producer = clock['control_producer']
    result = {'complete':complete,'cleanup_complete':cleanup,'errors':[] if complete else [{'stage':'invented_late_failure'}],
        'producer':{'GITHUB_SHA':SOURCE,'GITHUB_RUN_ID':'700','GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':producer['job'],
            'GITHUB_WORKFLOW_REF':producer['repository']+'/'+producer['workflow']+'@refs/heads/lead/cloud-forecast-local-credibility-h26-20261029'},
        'retained_inventory':{'files':files,'file_count':len(files),'bytes':sum(row['bytes'] for row in files.values())},
        'job_clock':{'path':'job-clock.json','sha256':pin(root/'job-clock.json')['sha256'],
            'monotonic_deadline':clock['monotonic_deadline'],'effective_owner_deadline':clock['monotonic_deadline']-255,
            'publication_reserve_seconds':255},
        'role_status':{name:{'status':'complete','observed_ticks':26-start} for name,start in zip(P.ROLE_NAMES,P.STARTS)}}
    if complete:
        result.update(actual_simulation_roles=14, actual_executed_ticks=315, actual_fresh_Worlds=7, actual_restored_roles=7,
            mechanical_readout_sha256=pin(root/'mechanics.json')['sha256'])
    write(root/'result.json', result)
    write(root/'terminal.json', {'complete':complete,'cleanup_complete':cleanup,
        'result_sha256':pin(root/'result.json')['sha256'],'required_wrapper_exit':0})
    return result


def make_study(tmp_path, monkeypatch, *, bodies, shared_control=None):
    control, root = (tmp_path/'control' if shared_control is None else shared_control), tmp_path/'original'
    config = control_fixture(control) if shared_control is None else json.loads((control/'docs/experiments/forecast-credibility-inputs.json').read_bytes())
    root.mkdir()
    for name in P.selected_paths():
        if name not in P.AUTHORITIES:
            write(root/name, {})
    clock = fake_clock();write(root/'job-clock.json', clock)
    write(root/'registration.json', S.registration(config['binding'], deepcopy(S.JOBS)))
    write(root/'mechanics.json', {'complete':True,'scope':'invented upstream metadata, not an actual readout'})
    write(root/'packages-before.json', [{'name':'invented-package','version':'1'}])
    write(root/'packages-after.json', [{'name':'invented-package','version':'1'}])
    for index,name in enumerate(P.ROLE_NAMES) if bodies else ():
        body = root/'roles'/name/'ordinary'/'opaque.fixture'
        body.parent.mkdir(parents=True)
        body.write_bytes(b'invented opaque role body; never decoded')
        log = root/P.RAW_LOGS[index];log.parent.mkdir(parents=True,exist_ok=True);log.write_bytes(b'invented bounded role log\n')
    result = reseal(root, clock)
    monkeypatch.setattr(P.shutil,'disk_usage',lambda _path:SimpleNamespace(free=20*P.GIB))
    return SimpleNamespace(root=root,control=control,clock=clock,result=result,base=tmp_path)


@pytest.fixture(scope='module')
def publication_control(tmp_path_factory,request):
    """One immutable seven-file source fixture; never changed by body tests."""
    name='publication-control-'+hashlib.sha256(request.node.nodeid.encode()).hexdigest()
    control=tmp_path_factory.mktemp(name,numbered=False)/'control'
    control_fixture(control)
    return control


@pytest.fixture
def study(tmp_path, monkeypatch,publication_control):
    """Complete regular-file tree for descriptor/hash/integration and mutations."""
    return make_study(tmp_path,monkeypatch,bodies=True,shared_control=publication_control)


@pytest.fixture
def early_study(tmp_path, monkeypatch):
    """Only early metadata gates; no admitted role-body/inventory claim."""
    return make_study(tmp_path,monkeypatch,bodies=False)


def early_gate(**changes):
    args=dict(source=SOURCE,prepare_outcome='success',metadata_outcome='success',
        publication_outcome='success',serializer_exit='0',metadata_budget_complete='true',
        remaining_wall_milliseconds='19000',remaining_cpu_seconds='9',
        metadata_output=Path('/tmp/invented-publication'),budget=budget(),boot_id=BOOT)
    args.update(changes)
    return P.gate_raw_upload(Path('/tmp/invented-original'),Path('/tmp/invented-control'),**args)


def pure_work():
    root,output=Path('/tmp/invented-original'),Path('/tmp/invented-publication')
    work=P._metadata_work_budget(budget(),root,output,SOURCE,{})
    return {'source':SOURCE,'metadata_only':True,'metadata_work_budget':work},root,output


def prepare(study, **changes):
    return P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='success',budget=budget(),boot_id=BOOT,**changes)


def gate(study, **changes):
    metadata=study.base/'metadata'
    if not metadata.exists():
        P.publish(study.root,metadata,owner_outcome='success',source=SOURCE,prepare_outcome='success',budget=budget())
    publication=json.loads((metadata/'publication.json').read_bytes())
    remaining=P._remaining_metadata(publication['metadata_work_budget'])
    args=dict(source=SOURCE,prepare_outcome='success',metadata_outcome='success',metadata_output=metadata,
        publication_outcome='success',serializer_exit='0',metadata_budget_complete='true',
        **{name:str(value) for name,value in remaining.items()},budget=budget(),boot_id=BOOT)
    args.update(changes)
    return P.gate_raw_upload(study.root,study.control,**args)


def test_positive_raw_manifest_closes_originals_without_copying_or_archive(study):
    original = {f.relative_to(study.root).as_posix():pin(f) for f in study.root.rglob('*') if f.is_file()}
    plan=prepare(study)
    assert plan['raw_eligible'] is plan['complete'] is True
    assert plan['raw_original_artifact_qualified'] is None and plan['phase']=='pre_upload'
    manifest=json.loads((study.root/P.MANIFEST).read_bytes())
    assert plan['manifest']=={'path':P.MANIFEST,**pin(study.root/P.MANIFEST)}
    assert manifest['matrix_state']=='complete' and len(manifest['role_status'])==14
    assert len(manifest['members'])==28 and manifest['observed_selected_files']==28
    assert P.MANIFEST not in manifest['members'] and P.PLAN not in manifest['members']
    assert set(f.relative_to(study.root).as_posix() for f in study.root.rglob('*') if f.is_file())==set(original)|{P.MANIFEST,P.PLAN}
    assert all(pin(study.root/name)==value for name,value in original.items())
    assert gate(study)['upload_raw'] is True


def test_late_negative_uses_only_actual_cleanup_inventory_and_no_complete_claim(study):
    reseal(study.root,study.clock,complete=False,cleanup=True)
    plan=P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='failure',budget=budget(),boot_id=BOOT)
    assert plan['raw_eligible'] is True and plan['matrix_state']=='negative'
    manifest=json.loads((study.root/P.MANIFEST).read_bytes())
    assert manifest['matrix_state']=='negative' and 'actual_executed_ticks' not in manifest
    assert manifest['raw_original_artifact_qualified'] is None


def test_child_cleanup_rows_do_not_upgrade_uncertified_whole_owner(early_study):
    study=early_study
    reseal(study.root,study.clock,complete=False,cleanup=False)
    plan=P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='failure',budget=budget(),boot_id=BOOT)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_CLEANUP'
    assert plan['observed_selected_bytes'] is plan['observed_selected_files'] is None
    assert not (study.root/P.MANIFEST).exists()


@pytest.mark.parametrize('defect',['clock_hash','clock_deadline','clock_boot','clock_job','clock_source','owner_run','source_pins','approval','registration'])
def test_raw_binding_or_actual_clock_substitution_is_ineligible(early_study,defect):
    study=early_study
    if defect.startswith('clock_'):
        value=json.loads((study.root/'job-clock.json').read_bytes())
        if defect=='clock_hash': value['observed']['run']['extra']='changed raw response'
        elif defect=='clock_deadline': value['monotonic_deadline']+=1
        elif defect=='clock_boot': value['boot_id']='00000000-0000-0000-0000-000000000002'
        elif defect=='clock_job': value['observed']['jobs']['jobs'][0]['id']=999
        else: value['control_producer']['source']='f'*40
        write(study.root/'job-clock.json',value)
    elif defect=='owner_run':
        value=json.loads((study.root/'result.json').read_bytes());value['producer']['GITHUB_RUN_ID']='701';write(study.root/'result.json',value)
        terminal=json.loads((study.root/'terminal.json').read_bytes());terminal['result_sha256']=pin(study.root/'result.json')['sha256'];write(study.root/'terminal.json',terminal)
    elif defect=='source_pins': (study.control/'scripts/forecast_credibility_study.py').write_text('# changed source\n')
    elif defect=='approval':
        path=study.control/'docs/experiments/forecast-credibility-inputs.json';value=json.loads(path.read_bytes());value['execution_approval']=None;write(path,value)
    else:
        value=json.loads((study.root/'registration.json').read_bytes());value['seed']=43;write(study.root/'registration.json',value)
        reseal(study.root,study.clock)
    plan=prepare(study)
    assert plan['raw_eligible'] is False and plan['raw_original_artifact_qualified'] is None
    expected='RAW_CLOCK' if defect.startswith('clock_') else 'RAW_BINDING' if defect=='registration' else 'RAW_SOURCE'
    assert plan['refusal_code']==expected


def test_current_original_hash_must_match_actual_retained_owner_inventory(study):
    path=study.root/'roles/local-parent/ordinary/opaque.fixture'
    (study.base/'original-retained-copy').write_bytes(path.read_bytes())
    path.write_bytes(b'changed invented body')
    plan=prepare(study)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_INVENTORY'
    assert path.read_bytes()==b'changed invented body'


def test_missing_fixed_role_log_cannot_be_silently_skipped_by_action(study):
    (study.root/P.RAW_LOGS[13]).rename(study.base/'retained-missing-fixed-log')
    reseal(study.root,study.clock)
    plan=prepare(study)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_FIXED_PATHS'
    assert (study.base/'retained-missing-fixed-log').is_file()


def test_actual_casefold_collisions_are_refused_without_deleting_regular_files(study):
    folder=study.root/'roles/local-parent/ordinary'
    (folder/'CASE').write_bytes(b'one');(folder/'case').write_bytes(b'two')
    reseal(study.root,study.clock)
    plan=prepare(study)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_CASEFOLD'
    assert (folder/'CASE').stat().st_nlink==(folder/'case').stat().st_nlink==1


@pytest.mark.parametrize('kind',['symlink','hardlink','special'])
def test_raw_walk_rejects_fake_alias_or_special_metadata_without_real_links(tmp_path,monkeypatch,kind):
    path=tmp_path/'opaque.fixture';path.write_bytes(b'invented regular body')
    actual=P.os.scandir
    class Entry:
        def __init__(self,entry):self.entry=entry;self.name=entry.name
        def stat(self,**kwargs):
            value=self.entry.stat(**kwargs)
            if self.name!='opaque.fixture':return value
            names=('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            fields={name:getattr(value,name) for name in names}
            if kind=='hardlink':fields['st_nlink']=2
            elif kind=='symlink':fields['st_mode']=stat.S_IFLNK|0o777
            else:fields['st_mode']=stat.S_IFIFO|0o600
            return SimpleNamespace(**fields)
    class Scan:
        def __init__(self,folder):self.entries=actual(folder)
        def __enter__(self):return (Entry(entry) for entry in self.entries)
        def __exit__(self,*args):self.entries.close()
    with monkeypatch.context() as patch:
        patch.setattr(P.os,'scandir',lambda folder:Scan(folder))
        with pytest.raises(P.Refused,match='RAW_SYMLINK|RAW_ALIAS'):
            P.scan_original(tmp_path,budget(),hash_files=True)
    assert path.stat().st_nlink==1 and path.read_bytes()==b'invented regular body'


@pytest.mark.parametrize('extra_bytes,extra_files,expected',[(0,0,True),(1,0,False),(0,1,False)])
def test_joint_cap_counts_original_authorities_new_files_and_all_metadata_copies(extra_bytes,extra_files,expected):
    size=P.ROOT_BYTES-P.MANIFEST_BYTES-P.PLAN_BYTES-P.TOTAL_LIMIT+extra_bytes
    files=P.ROOT_FILES-2-P.FILE_LIMIT+extra_files
    if expected:
        observed=P.joint_reserve(size,files)
        assert observed['original_all_file_bytes']==size and observed['reserved_metadata_copy_bytes']==P.TOTAL_LIMIT
    else:
        with pytest.raises(P.Refused,match='RAW_JOINT_CAP'):P.joint_reserve(size,files)


@pytest.mark.parametrize('bad',[True,-1,None,1.5])
def test_joint_accounting_never_treats_unknown_or_boolean_counts_as_zero(bad):
    with pytest.raises(P.Refused,match='RAW_JOINT_CAP'):P.joint_reserve(0,bad)


def test_manifest_and_plan_occupied_paths_refuse_without_overwrite(tmp_path):
    root,control=tmp_path/'original',tmp_path/'control';root.mkdir();control.mkdir()
    occupied=b'preserved previous attempt';(root/P.PLAN).write_bytes(occupied)
    plan=P.prepare_raw(root,control,source=SOURCE,owner_outcome='success',budget=budget(),boot_id=BOOT)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_OCCUPIED'
    assert (root/P.PLAN).read_bytes()==occupied

def test_prepare_reserves_metadata_and_raw_job_time_before_hashing(early_study):
    study=early_study
    value=P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='success',
        budget=budget(study.clock['monotonic_deadline']-224),boot_id=BOOT)
    assert value['raw_eligible'] is False and value['refusal_code']=='RAW_DEADLINE'
    assert not (study.root/P.MANIFEST).exists()


def test_missing_plan_after_bounded_prepare_interruption_is_closed_negative(study):
    limits=budget();normal=limits.check
    def interrupted():
        normal()
        if (study.root/P.MANIFEST).exists():raise TimeoutError('invented post-manifest termination')
    limits.check=interrupted
    plan=P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='success',budget=limits,boot_id=BOOT)
    assert plan['raw_eligible'] is False and not (study.root/P.PLAN).exists()
    report=P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,prepare_outcome='failure',budget=budget())
    assert report['complete'] is True
    assert report['raw_retention']['local_manifest_eligible'] is False
    assert report['raw_retention']['raw_original_artifact_qualified'] is None
    assert gate(study,prepare_outcome='failure')['upload_raw'] is False


@pytest.mark.parametrize('prepare_outcome,metadata_outcome',[('failure','success'),('success','failure'),(None,'success'),('success',None)])
def test_upload_gate_requires_actual_prepare_and_metadata_action_success(monkeypatch,prepare_outcome,metadata_outcome):
    monkeypatch.setattr(P,'read_regular',lambda *args:(_ for _ in ()).throw(AssertionError('early gate must not read files')))
    result=early_gate(prepare_outcome=prepare_outcome,metadata_outcome=metadata_outcome)
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_PLAN'

def test_upload_gate_rechecks_remaining_time_after_metadata_upload(study):
    assert prepare(study)['raw_eligible'] is True
    result=gate(study,budget=budget(study.clock['monotonic_deadline']-144))
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_UPLOAD_RESERVE'


def test_upload_gate_stat_rescans_without_second_body_hash(study,monkeypatch):
    assert prepare(study)['raw_eligible'] is True
    P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,prepare_outcome='success',budget=budget())
    actual=P.scan_original;called=[]
    def observed(root,limits,*,hash_files):
        called.append(hash_files)
        assert hash_files is False
        return actual(root,limits,hash_files=hash_files)
    monkeypatch.setattr(P,'scan_original',observed)
    assert gate(study)['upload_raw'] is True and called==[False]


@pytest.mark.parametrize('defect',['identity','mtime','content','extra_member'])
def test_late_file_identity_mtime_content_or_member_mutation_cannot_upload(study,defect):
    assert prepare(study)['raw_eligible'] is True
    path=study.root/'roles/local-parent/ordinary/opaque.fixture';before=path.stat();body=path.read_bytes()
    if defect=='identity':
        path.rename(study.base/'retained-original-inode');path.write_bytes(body)
    elif defect=='mtime':os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns+1000000000))
    elif defect=='content':
        (study.base/'retained-before-content').write_bytes(body);path.write_bytes(b'X'+body[1:])
        os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
    else:(path.parent/'unexpected-extra').write_bytes(b'extra')
    result=gate(study)
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_CHANGED'


@pytest.mark.parametrize('defect',['plan_hash','manifest_hash','artifact_name','clock','truncated_plan'])
def test_late_manifest_plan_or_clock_tamper_is_ineligible(study,defect):
    assert prepare(study)['raw_eligible'] is True
    if defect=='manifest_hash':(study.root/P.MANIFEST).write_bytes(b'changed')
    elif defect=='clock':
        clock=json.loads((study.root/'job-clock.json').read_bytes());clock['observed']['run']['extra']='changed';write(study.root/'job-clock.json',clock)
    elif defect=='truncated_plan':(study.root/P.PLAN).write_bytes(b'{')
    else:
        plan=json.loads((study.root/P.PLAN).read_bytes())
        if defect=='plan_hash':plan['manifest']['sha256']='0'*64
        else:plan['expected_artifact_name']='other-artifact'
        write(study.root/P.PLAN,plan)
    assert gate(study)['upload_raw'] is False


def test_metadata_proofs_remain_complete_when_raw_preparation_absent(early_study):
    study=early_study
    report=P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,budget=budget())
    assert report['complete'] is True and report['metadata_only'] is True
    assert report['raw_retention']['local_manifest_eligible'] is False
    assert report['raw_retention']['raw_original_artifact_qualified'] is None
    assert report['raw_payload_retained'] is False
    assert all(name in report['files'] for name in set(P.selected_paths())-{'terminal-failure.json'})


def test_metadata_seal_is_pre_upload_even_when_local_manifest_is_eligible(study):
    assert prepare(study)['raw_eligible'] is True
    report=P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,
        prepare_outcome='success',budget=budget())
    assert report['complete'] is True and report['raw_retention']['local_manifest_eligible'] is True
    assert report['raw_retention']['as_of_metadata_seal'] is True and report['raw_retention']['phase']=='pre_upload'
    assert report['raw_retention']['raw_original_artifact_qualified'] is None
    assert report['retained_bytes']+P.PLAN_BYTES<=P.TOTAL_LIMIT and len(report['files'])+1<=P.FILE_LIMIT


def test_source_client_proof_never_becomes_backend_or_total_RSS_qualification():
    assert P.UPLOAD_CLIENT['upload_concurrency']==1 and P.UPLOAD_CLIENT['buffer_pool_bytes_max']==8*1024**2
    assert P.UPLOAD_CLIENT['backend_original_archive_equivalence'] is None
    assert P.UPLOAD_CLIENT['backend_original_archive_size'] is None and P.UPLOAD_CLIENT['total_RSS'] is None
    assert 'retries may occur' in P.UPLOAD_CLIENT['scope']


def test_inactive_workflow_uploads_metadata_before_exact_hidden_inclusive_raw_paths():
    text=(ROOT/'docs/experiments/forecast-credibility-study.yml.inactive').read_text()
    assert text.index('id: metadata_upload')<text.index('id: raw_gate')<text.index('id: raw_upload')
    assert "ACTIONS_ARTIFACT_UPLOAD_CONCURRENCY: '1'" in text
    assert 'include-hidden-files: true' in text and 'compression-level: 0' in text
    assert 'timeout-minutes: 45' in text and 'timeout-minutes: 1' in text and 'timeout-minutes: 2' in text
    assert '${{ runner.temp }}/forecast-credibility-study/roles' in text
    assert '${{ runner.temp }}/forecast-credibility-study/raw-retention-manifest.json' in text
    for index in range(14):assert '${{ runner.temp }}/forecast-credibility-study/logs/role-'+str(index)+'.log' in text
    assert "steps.metadata_upload.outcome == 'success'" in text
    assert "steps.raw_prepare.outcome == 'success'" in text
    assert "steps.raw_gate.outcome == 'success'" in text
    assert 'FORECAST_CANDIDATE_FULL_CI_BINDING_NULL' in text


def test_hidden_regular_role_members_are_included_in_the_closed_manifest(study):
    hidden=study.root/'roles/local-parent/ordinary/.retained-hidden-fixture'
    hidden.write_bytes(b'invented hidden body')
    reseal(study.root,study.clock)
    assert prepare(study)['raw_eligible'] is True
    manifest=json.loads((study.root/P.MANIFEST).read_bytes())
    assert manifest['members']['roles/local-parent/ordinary/.retained-hidden-fixture']==pin(hidden)
    assert gate(study)['upload_raw'] is True


def test_current_publication_cannot_precede_its_saved_clock_sample(early_study):
    study=early_study
    plan=P.prepare_raw(study.root,study.control,source=SOURCE,owner_outcome='success',budget=budget(1000.0),boot_id=BOOT)
    assert plan['raw_eligible'] is False and plan['refusal_code']=='RAW_CLOCK'


@pytest.mark.parametrize('kind',['walk','depth','hash','metadata'])
def test_prepare_finite_walk_hash_and_metadata_counters_fail_closed(tmp_path,monkeypatch,kind):
    limits=budget();path=tmp_path/'opaque.fixture'
    if kind=='depth':path=tmp_path/'nested/opaque.fixture';path.parent.mkdir()
    path.write_bytes(b'invented bounded body')
    if kind=='walk':monkeypatch.setattr(P,'MAX_ENTRIES',0)
    elif kind=='depth':monkeypatch.setattr(P,'MAX_DEPTH',0)
    elif kind=='hash':limits.hashed=P.ROOT_BYTES
    else:limits.metadata_bytes=P.TOTAL_LIMIT
    with pytest.raises(P.Refused,match='RAW_SCAN|RAW_HASH_CAP|RAW_METADATA_CAP'):
        if kind=='metadata':limits.read(path)
        else:P.scan_original(tmp_path,limits,hash_files=True)
    assert path.read_bytes()==b'invented bounded body' and path.stat().st_nlink==1

@pytest.mark.parametrize('name',['../escape','/absolute','a//b','a/./b','a\\b','x'*513])
def test_raw_archive_names_cannot_escape_or_exceed_the_registered_UTF8_bound(name):
    with pytest.raises(P.Refused,match='RAW_PATH'):P._relative(name)


def test_budget_rejects_actual_deadline_and_CPU_counter_overruns_without_rlimit_changes():
    now=[100.0];cpu=[0.0]
    limits=P.Budget(30,20,now=lambda:now[0],cpu_now=lambda:cpu[0])
    now[0]=131.0
    with pytest.raises(P.Refused,match='RAW_DEADLINE'):limits.check()
    now[0]=100.0;cpu[0]=21.0
    with pytest.raises(P.Refused,match='RAW_CPU'):limits.check()


def test_post_metadata_plan_rewrite_cannot_change_the_uploaded_pair(study):
    assert prepare(study)['raw_eligible'] is True
    P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,prepare_outcome='success',budget=budget())
    plan=json.loads((study.root/P.PLAN).read_bytes())
    plan['scope']='altered after metadata seal'
    write(study.root/P.PLAN,plan)
    result=gate(study)
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_PLAN'


@pytest.mark.parametrize('changes', [
    {'serializer_exit':'1'}, {'serializer_exit':'137'}, {'serializer_exit':'-9'}, {'serializer_exit':None},
    {'publication_outcome':'failure'}, {'publication_outcome':None},
    {'metadata_budget_complete':'false'}, {'metadata_budget_complete':None},
])
def test_actual_serializer_failure_or_missing_postguard_flag_refuses_even_with_valid_plan(monkeypatch,changes):
    # The complete-plan positive is retained separately; these gates must refuse
    # before touching it, even if a stale successful flag or plan would exist.
    monkeypatch.setattr(P,'read_regular',lambda *args:(_ for _ in ()).throw(AssertionError('early gate must not read files')))
    result=early_gate(**changes)
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_PLAN'

@pytest.mark.parametrize('field,value', [
    ('source','b'*40), ('root','/tmp/different-original'), ('output','/tmp/different-metadata'),
    ('scope','second_metadata_allowance'), ('max_wall_seconds',21), ('max_cpu_seconds',11),
])
def test_shared_metadata_ledger_is_bound_to_exact_source_paths_and_job_clock(field,value):
    publication,root,output=pure_work();remaining=P._remaining_metadata(publication['metadata_work_budget'])
    publication['metadata_work_budget'][field]=value
    with pytest.raises(P.Refused,match='RAW_PLAN'):
        P._share_metadata_budget(publication,budget(),source=SOURCE,root=root,output=output,
            **{name:str(value) for name,value in remaining.items()})

@pytest.mark.parametrize('wall,cpu', [
    (float('nan'),1.0), (float('inf'),1.0), (True,1.0), (-1.0,1.0),
    (20.0,1.0), (1.0,10.0), (1.0,9.5), (1.0,float('nan')), (1.0,True),
])
def test_shared_work_charges_cannot_create_nonfinite_overfull_or_zero_CPU_admission(wall,cpu):
    with pytest.raises(P.Refused,match='RAW_PLAN'):
        P._remaining_metadata({'charged_serialization_wall_seconds':wall,'charged_serialization_cpu_seconds':cpu})


def test_late_gate_subtracts_serialization_ACTIVE_work_without_charging_upload_wait(study):
    assert prepare(study)['raw_eligible'] is True
    publication=P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,
        prepare_outcome='success',budget=budget())
    work=publication['metadata_work_budget'];work['charged_serialization_wall_seconds']=12.25
    work['charged_serialization_cpu_seconds']=4.25
    write(study.base/'metadata/publication.json',publication)
    limits=budget(1200.0)
    result=gate(study,budget=limits)
    assert result['upload_raw'] is True
    assert limits.deadline==1207.75 and limits.cpu_limit==5
    assert work['clock_binding']['boot_id']==BOOT
    assert work['clock_binding']['monotonic_deadline']==study.clock['monotonic_deadline']


@pytest.mark.parametrize('changes', [
    {'remaining_wall_milliseconds':'20000'}, {'remaining_cpu_seconds':'10'},
    {'remaining_wall_milliseconds':'019000'}, {'remaining_cpu_seconds':'0'},
])
def test_launcher_remaining_arguments_must_equal_the_sealed_floored_allowance(changes):
    publication,root,output=pure_work();remaining=P._remaining_metadata(publication['metadata_work_budget'])
    args={name:str(value) for name,value in remaining.items()};args.update(changes)
    with pytest.raises(P.Refused,match='RAW_PLAN'):
        P._share_metadata_budget(publication,budget(),source=SOURCE,root=root,output=output,**args)

@pytest.mark.parametrize('which',['wall','cpu'])
def test_final_metadata_write_or_guard_overrun_prevents_completion_flag(monkeypatch,which):
    now=[100.0];cpu=[0.0];outputs=[]
    limits=P.Budget(20,10,now=lambda:now[0],cpu_now=lambda:cpu[0])
    report={'complete':True,'metadata_work_budget':{
        'charged_serialization_wall_seconds':1.0,'charged_serialization_cpu_seconds':0.25}}
    def delayed_publish(*args,**kwargs):
        if which=='wall':now[0]=102.0
        else:cpu[0]=1.0
        return report
    monkeypatch.setattr(P,'_enforce',lambda *args:(20,10))
    monkeypatch.setattr(P,'_launcher_budget',lambda *args:100.0)
    monkeypatch.setattr(P,'Budget',lambda *args,**kwargs:limits)
    monkeypatch.setattr(P,'publish',delayed_publish)
    monkeypatch.setattr(P,'_workflow_output',outputs.append)
    with pytest.raises(P.Refused):
        P.main(['--root','/tmp/invented-original','--output','/tmp/invented-publication',
            '--source',SOURCE,'--launcher-boot-seconds','100.00'])
    assert outputs==[]


def test_kernel_boot_sample_conservatively_charges_interpreter_startup():
    started=P._launcher_budget('metadata','549.20',now=1000.0,boot_now=550.0)
    assert abs(started-999.2)<1e-10


@pytest.mark.parametrize('sample,current',[
    ('bad',550.0), ('nan',550.0), ('549',550.0), ('-1.00',550.0),
    ('551.00',550.0), ('500.00',550.0), ('549.00',float('nan')),
])
def test_invalid_future_or_stale_launch_boot_samples_fail_closed(sample,current):
    with pytest.raises(P.Refused):P._launcher_budget('metadata',sample,now=1000.0,boot_now=current)


def test_late_OS_limits_use_the_reduced_shared_allowance_without_actual_rlimit_changes(monkeypatch):
    limits=[];timers=[]
    monkeypatch.setattr(P.resource,'setrlimit',lambda *args:limits.append(args))
    monkeypatch.setattr(P.signal,'signal',lambda *args:None)
    monkeypatch.setattr(P.signal,'setitimer',lambda *args:timers.append(args))
    monkeypatch.setattr(P,'_cpu',lambda:0.5)
    assert P._enforce('upload-gate','7750','5')==(7.75,5)
    assert (P.resource.RLIMIT_CPU,(5,5)) in limits
    assert (P.signal.ITIMER_REAL,7.75) in timers
    assert (P.signal.ITIMER_PROF,4.5) in timers


def test_dormant_launcher_captures_actual_exit_and_applies_only_remaining_late_budget():
    text=(ROOT/'docs/experiments/forecast-credibility-study.yml.inactive').read_text()
    assert 'serializer_exit=$?' in text and 'serializer_exit=%s' in text
    assert "steps.publication.outcome == 'success'" in text
    assert "steps.publication.outputs.metadata_budget_complete == 'true'" in text
    assert '--serializer-exit "$SERIALIZER_EXIT"' in text
    assert '--remaining-wall-milliseconds "$REMAINING_WALL_MILLISECONDS"' in text
    assert '--remaining-cpu-seconds "$REMAINING_CPU_SECONDS"' in text
    assert 'ulimit -t "$REMAINING_CPU_SECONDS"' in text
    assert '"${gate_wall}s" /usr/bin/python3' in text
    assert 'read -r launch_boot _ < /proc/uptime' in text
    assert 'ulimit -t 20' in text and text.count('ulimit -v 262144')==4



def test_launcher_samples_monotonic_before_boot_time_so_scheduling_delay_only_charges_more(monkeypatch):
    calls=[]
    def monotonic():calls.append('monotonic');return 1000.0
    def boot(clock):calls.append('boot');return 551.0
    monkeypatch.setattr(P.time,'monotonic',monotonic)
    monkeypatch.setattr(P.time,'clock_gettime',boot)
    assert P._launcher_budget('metadata','549.00')==998.0
    assert calls==['monotonic','boot']



def test_sealed_serializer_tail_rearms_hard_timers_through_actual_process_exit(monkeypatch):
    timers=[]
    limits=P.Budget(20,10,now=lambda:100.0,cpu_now=lambda:0.0,enforce_os=True)
    monkeypatch.setattr(P.signal,'setitimer',lambda *args:timers.append(args))
    report={'metadata_work_budget':{'charged_serialization_wall_seconds':1.0,
        'charged_serialization_cpu_seconds':0.25}}
    P._metadata_tail_enforce(report,limits)
    assert limits.deadline==101.0 and limits.cpu_limit==0.25
    assert timers==[(P.signal.ITIMER_REAL,1.0),(P.signal.ITIMER_PROF,0.25)]



def test_malformed_optional_raw_clock_does_not_erase_honest_original_metadata_proofs(study):
    assert prepare(study)['raw_eligible'] is True
    (study.root/'job-clock.json').write_bytes(b'{')
    report=P.publish(study.root,study.base/'metadata',owner_outcome='success',source=SOURCE,
        prepare_outcome='success',budget=budget())
    assert report['complete'] is True and report['metadata_only'] is True
    assert report['metadata_work_budget']['clock_binding'] is None
    assert report['raw_payload_retained'] is False
    assert report['raw_retention']['raw_original_artifact_qualified'] is None
    assert gate(study)['upload_raw'] is False



def test_shared_metadata_ledger_job_clock_binding_is_checked_after_real_file_seal(study):
    assert prepare(study)['raw_eligible'] is True and gate(study)['upload_raw'] is True
    path=study.base/'metadata/publication.json';publication=json.loads(path.read_bytes())
    publication['metadata_work_budget']['clock_binding']={'boot_id':'different','monotonic_deadline':3635.0,'sha256':'0'*64}
    write(path,publication)
    result=gate(study)
    assert result['upload_raw'] is False and result['refusal_code']=='RAW_CLOCK'



@pytest.mark.parametrize('after_guard,eligible',[(104.0,True),(106.0,False)])
def test_raw_output_and_local_guard_are_followed_by_a_fresh_actual_job_reserve_check(monkeypatch,after_guard,eligible):
    # No role tree or actual output file: retain primitive clock/output witnesses.
    now=[100.0];outputs=[];events=[]
    limits=P.Budget(20,10,now=lambda:now[0],cpu_now=lambda:0.0)
    original_guard=limits.check
    def local_guard():
        original_guard()
        if outputs:
            events.append('local_guard_complete');now[0]=after_guard
    limits.check=local_guard
    def admitted_gate(*args,**kwargs):
        assert 250.0-now[0]>=145
        events.append('actual_D_admitted')
        return {'upload_raw':True,'expected_artifact_name':'invented-exact-name','monotonic_deadline':250.0}
    def flushed_output(values):
        assert set(values)=={'upload_raw','expected_artifact_name'}
        outputs.append(dict(values));events.append('output_append_flush_fsync_complete');now[0]=103.0
    monkeypatch.setattr(P,'_enforce',lambda *args:(20,10))
    monkeypatch.setattr(P,'_launcher_budget',lambda *args:100.0)
    monkeypatch.setattr(P,'Budget',lambda *args,**kwargs:limits)
    monkeypatch.setattr(P,'gate_raw_upload',admitted_gate)
    monkeypatch.setattr(P,'_workflow_output',flushed_output)
    argv=['--mode','upload-gate','--root','/tmp/invented-original','--control','/tmp/invented-control',
        '--output','/tmp/invented-publication','--source',SOURCE,'--launcher-boot-seconds','100.00',
        '--prepare-outcome','success','--metadata-outcome','success','--publication-outcome','success',
        '--serializer-exit','0','--metadata-budget-complete','true',
        '--remaining-wall-milliseconds','19000','--remaining-cpu-seconds','9']
    if eligible:assert P.main(argv)==0
    else:
        with pytest.raises(P.Refused,match='RAW_UPLOAD_RESERVE'):P.main(argv)
    assert outputs==[{'upload_raw':True,'expected_artifact_name':'invented-exact-name'}]
    assert events==['actual_D_admitted','output_append_flush_fsync_complete','local_guard_complete']
    # A partial true output alone cannot activate the existing action gate.
    workflow=(ROOT/'docs/experiments/forecast-credibility-study.yml.inactive').read_text()
    assert "steps.raw_gate.outcome == 'success'" in workflow
