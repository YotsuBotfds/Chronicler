"""Pure fixed-controller contracts; no installed wheel, host probe or worlds."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import MappingProxyType,SimpleNamespace

import pytest
from scripts import wealth_floor_outcome_qualification as O

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,30,tzinfo=timezone.utc)


@pytest.mark.parametrize("worldgen,stage,executions,ticks",[
    ("template","smoke",6,334),("procedural","smoke",6,334),
    ("template","full",1800,133600),("procedural","full",1900,67800)])
def test_fixed_work_uses_original_scientific_configuration(worldgen,stage,executions,ticks):
    helpers=O.scientific_helpers(ROOT);plan=O.work_plan(worldgen,stage,helpers)
    assert plan["config"]==helpers.expected(worldgen,stage)
    assert (plan["executions"],plan["physics_ticks"])==(executions,ticks)
    assert (plan["entry_disk_gib"],plan["entry_effective_available_memory_gib"],plan["running_disk_floor_gib"],plan["running_memory_floor_gib"])==(20,6,3,1)
    assert plan["wall_limit_seconds"]==(80*60 if stage=="smoke" else 330*60)
    original=O.runner_command("PY",Path("SOURCE"),worldgen,Path("OUTPUT"),stage,helpers)
    retained=O.retained_command("PY",Path("SOURCE"),Path("CONTROL"),worldgen,Path("OUTPUT"),stage,helpers)
    assert retained==[original[0],"CONTROL/scripts/wealth_floor_retained_outcome_driver.py",*original[2:]]
    assert "--baseline-report" not in original and "--exploratory-comparison" not in original


@pytest.mark.parametrize("args",[["--execute"],["--registration"],["--validate-publication"]])
def test_null_v2_refuses_before_path_or_host_work(monkeypatch,args):
    monkeypatch.setattr(O.V,"REVIEWED_PREREQUISITES",{key:None for key in O.V.PREREQUISITE_KEYS})
    monkeypatch.setattr(O.V,"REVIEWED_PRIMER",{key:None for key in O.V.PRIMER_KEYS})
    monkeypatch.setattr(O.V,"REVIEWED_WORKER_SMOKES",{key:None for key in O.V.WORKER_KEYS})
    monkeypatch.setattr(O.V,"ROOT_PREREQUISITE_PACKET_SHA256",None)
    monkeypatch.setattr(O.V,"ROOT_WORKER_SMOKE_PACKET_SHA256",None)
    def forbidden(*_a,**_k):pytest.fail("work before closed V2 admission")
    monkeypatch.setattr(O,"scientific_helpers",forbidden)
    monkeypatch.setattr(O.P,"hosted_vm_precondition",forbidden)
    monkeypatch.setattr(O.P,"read_json",forbidden)
    with pytest.raises(O.P.ProofRefused,match="remain NULL"):
        O.main(args+["--stage","smoke","--worldgen","template","--source","unused","--output","unused"])


def test_default_is_inactive_without_resource_or_native_probe(monkeypatch,capsys):
    def forbidden(*_a,**_k):pytest.fail("default performed actual work")
    monkeypatch.setattr(O.P,"hosted_vm_precondition",forbidden);monkeypatch.setattr(O.M,"observe_runtime",forbidden)
    assert O.main([])==0
    v=json.loads(capsys.readouterr().out)
    assert v["status"]=="inactive_source_only" and v["production_executions"]==3700 and v["production_ticks"]==201400


@pytest.mark.parametrize("code",[0,2])
def test_actual_owned_event_supplies_status_not_captured_stdout(monkeypatch,code):
    events=[dict(event="child_cleanup",label="original-runner",complete=True,cleanup_error=None),
        dict(event="child_exit",label="original-runner",returncode=code)]
    raw=b''.join(O.B.canonical_bytes(row) for row in events);calls=[]
    class Supervisor:
        def check(self):pass
        def command(self,*a,**kw):calls.append((a,kw));return b"misleading fixture stdout returncode=9"
    monkeypatch.setattr(O.P,"read_bytes",lambda *_a,**_k:raw)
    assert O.command_exit(Supervisor(),"original-runner",["PY"],{},Path("SOURCE"),Path("OUTPUT"))==code
    assert calls[0][1]==dict(allowed_exit_codes=(0,2))


@pytest.mark.parametrize("fault",["no_exit","duplicate","unclean","cleanup_error","bool_exit","wrong_label"])
def test_uncertain_child_status_refuses_completion(monkeypatch,fault):
    events=[dict(event="child_cleanup",label="original-runner",complete=True,cleanup_error=None),dict(event="child_exit",label="original-runner",returncode=2)]
    if fault=="no_exit":events.pop()
    elif fault=="duplicate":events.append(dict(events[-1]))
    elif fault=="unclean":events[0]["complete"]=False
    elif fault=="cleanup_error":events[0]["cleanup_error"]="fixture"
    elif fault=="bool_exit":events[1]["returncode"]=False
    else:events[1]["label"]="different"
    monkeypatch.setattr(O.P,"read_bytes",lambda *_a,**_k:b''.join(O.B.canonical_bytes(row) for row in events))
    supervisor=SimpleNamespace(command=lambda *_a,**_k:b"",check=lambda:None)
    with pytest.raises(O.P.ProofRefused):O.command_exit(supervisor,"original-runner",[],{},Path("SOURCE"),Path("OUTPUT"))


@pytest.mark.parametrize("stage",["smoke","full"])
def test_dormant_phase_workflow_is_closed_and_byte_pinned(stage):
    path=O.SMOKE_TEMPLATE_PATH if stage=="smoke" else O.TEMPLATE_PATH
    raw=(ROOT/path).read_bytes();O.workflow_contract(stage,raw,raw)
    assert b"workflow_dispatch" not in raw and b"max-parallel: 2" in raw and b"503070175e3e78d9014add158ead8f16ce940843" in raw
    assert b"steps.outcome.outputs.failed_checkpoint_paths" in raw and b"failure-metadata-" in raw
    assert b"failed-checkpoint-body-selection.json" in raw
    assert O.verify_workflow_paths(ROOT,stage)
    with pytest.raises(O.P.ProofRefused):O.workflow_contract(stage,raw+b"\n",raw+b"\n")
    with pytest.raises(O.P.ProofRefused):O.workflow_contract(stage,raw,raw+b"\n")


@pytest.mark.parametrize("stage",["smoke","full"])
@pytest.mark.parametrize("mode",["absent","exact","changed","symlink","broken_symlink"])
def test_same_high_level_workflow_check_accepts_only_absent_or_exact_regular_copy(tmp_path,stage,mode):
    template=O.SMOKE_TEMPLATE_PATH if stage=="smoke" else O.TEMPLATE_PATH
    active=O.SMOKE_WORKFLOW_PATH if stage=="smoke" else O.WORKFLOW_PATH
    raw=(ROOT/template).read_bytes();target=tmp_path/template;target.parent.mkdir(parents=True);target.write_bytes(raw)
    target=tmp_path/active;target.parent.mkdir(parents=True)
    if mode=="exact":target.write_bytes(raw)
    elif mode=="changed":target.write_bytes(raw+b"\n")
    elif mode=="symlink":target.symlink_to(tmp_path/template)
    elif mode=="broken_symlink":target.symlink_to(tmp_path/"missing")
    if mode in ("absent","exact"):assert O.verify_workflow_paths(tmp_path,stage)
    else:
        with pytest.raises((O.P.ProofRefused,OSError)):O.verify_workflow_paths(tmp_path,stage)


def test_late_failure_invalidates_both_result_copies_and_seal_preserving_evidence(tmp_path):
    (tmp_path/"light").mkdir()
    original=b"synthetic captured header/SHA evidence";(tmp_path/"candidate-checkpoint-index.json").write_bytes(original)
    for name in ("result.json","light/result.json"):
        O.C.write_json(tmp_path/name,dict(qualified=True,smoke_pass=True))
    O.C.write_json(tmp_path/"light/completion.json",dict(publication_complete=True))
    O.invalidate_publication(tmp_path,dict(execution_complete=True),O.P.ProofRefused("fixture late fault"),"bounded_publication")
    for name in ("result.json","light/result.json"):
        v=json.loads((tmp_path/name).read_bytes());assert v["qualified"] is False and v["smoke_pass"] is False and v["publication_complete"] is False
    assert json.loads((tmp_path/"light/completion.json").read_bytes())["publication_complete"] is False
    assert (tmp_path/"candidate-checkpoint-index.json").read_bytes()==original


@pytest.mark.parametrize("fault",["copy","extend"])
def test_copy_and_extension_faults_observe_only_negative_authoritative_receipts(monkeypatch,tmp_path,fault):
    desired=dict(qualified=True,smoke_pass=True,execution_complete=True);calls=[]
    original=b"synthetic captured CP metadata";(tmp_path/"candidate-checkpoint-index.json").write_bytes(original)
    def assert_negative():
        for name in ("result.json","light/result.json"):
            v=json.loads((tmp_path/name).read_bytes());assert v["qualified"] is False and v["smoke_pass"] is False and v["publication_complete"] is False
        assert json.loads((tmp_path/"light/completion.json").read_bytes())["publication_complete"] is False
    def copy(*_a,**_k):
        calls.append("copy");assert_negative()
        if fault=="copy":raise O.P.ProofRefused("fixture copy failure")
        return dict(files={})
    def extend(*_a,**_k):
        calls.append("extend");assert_negative();raise O.P.ProofRefused("fixture extension failure")
    monkeypatch.setattr(O,"copy_required_light",copy);monkeypatch.setattr(O,"extend_light",extend)
    with pytest.raises(O.P.ProofRefused):O.publish_light(tmp_path,desired,object(),"smoke",lambda:None)
    assert_negative();assert desired["qualified"] is True and desired["smoke_pass"] is True
    assert calls==(["copy"] if fault=="copy" else ["copy","extend"])
    assert (tmp_path/"candidate-checkpoint-index.json").read_bytes()==original


def test_failure_uploader_receives_original_paths_and_fixed_bound(monkeypatch,tmp_path):
    output=tmp_path/"github-output";monkeypatch.setenv("GITHUB_OUTPUT",str(output))
    selection=dict(selected=[dict(source_path="/original/raw/seed_42/checkpoint_turn_101.ckpt"),dict(source_path="/original/raw/seed_43/checkpoint_turn_101.ckpt")])
    O.emit_failed_body_outputs(selection)
    raw=output.read_text();assert "failed_checkpoint_count=2" in raw and "/original/raw/seed_42/checkpoint_turn_101.ckpt" in raw
    with pytest.raises(O.P.ProofRefused):O.emit_failed_body_outputs(dict(selected=[dict(source_path="bad\npath")]))


@pytest.fixture
def small_journal(monkeypatch,tmp_path):
    # Exercise the ACTUAL frozen C60 event writer, with only O-owned segment
    # limits reduced for tiny fixtures. No command/process/admission is run.
    monkeypatch.setattr(O,'JOURNAL_SEGMENT_BYTES',1024)
    monkeypatch.setattr(O,'JOURNAL_MAX_SEGMENTS',3)
    monkeypatch.setattr(O,'JOURNAL_MAX_BYTES',3072)
    monkeypatch.setattr(O,'JOURNAL_MAX_ROW_BYTES',256)
    class Base:
        def __init__(self,root,deadline,**_):self.root=root;self.deadline=deadline
    supervisor=O.C.make_supervisor(SimpleNamespace(Supervisor=Base),tmp_path,1000,object())
    journal=O.SegmentedJournal(tmp_path,supervisor.event,lambda:None)
    return journal,supervisor,tmp_path


def test_segmented_journal_preserves_every_original_row_in_order_and_seals_durably(small_journal):
    journal,_,root=small_journal
    for i in range(18):journal.event('resources',phase='fixture:running',ordinal=i)
    rows=list(journal.events());assert [r['ordinal'] for r in rows]==list(range(18))
    assert len(journal.closed)>=1
    journal.seal();index=json.loads((root/'progress-segments/index.json').read_bytes())
    assert index['journal_complete'] is True and index['publication_complete'] is False
    assert index['event_count']==18 and index['total_bytes']==sum(r['bytes'] for r in index['segments'])
    assert all(r['bytes']<=1024 for r in index['segments']) and index['total_bytes']<=3072
    for row in index['segments']:
        assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256']
    with pytest.raises(O.P.ProofRefused):journal.event('resources',ordinal=19)


@pytest.mark.parametrize('fault',['missing','changed','partial','writer_refused','aggregate'])
def test_segment_faults_latch_incomplete_and_cannot_seal(small_journal,fault):
    journal,_,root=small_journal
    desired=dict(qualified=True,smoke_pass=True);O.establish_negative_receipts(root,desired)
    for i in range(12):journal.event('resources',phase='fixture:running',ordinal=i)
    if fault in ('missing','changed'):
        path=root/journal.closed[0]['path']
        if fault=='missing':path.unlink()
        else:path.write_bytes(path.read_bytes().replace(b'ordinal',b'Ordinal',1))
        with pytest.raises((O.P.ProofRefused,OSError)):journal.seal()
    else:
        if fault=='partial':
            def partial(*_a,**_k):
                with (root/'progress.jsonl').open('ab') as stream:stream.write(b'{"event":')
            journal.writer=partial
        elif fault=='writer_refused':
            def refused(*_a,**_k):raise O.P.ProofRefused('fixture writer refusal')
            journal.writer=refused
        else:journal.total_bytes=3072
        with pytest.raises(O.P.ProofRefused):journal.event('resources',ordinal=99)
        with pytest.raises(O.P.ProofRefused):journal.seal()
    index=json.loads((root/'progress-segments/index.json').read_bytes())
    assert index['journal_complete'] is False and journal.failed is True
    for name in ('result.json','light/result.json'):
        value=json.loads((root/name).read_bytes());assert value['qualified'] is False and value['smoke_pass'] is False
    assert json.loads((root/'light/completion.json').read_bytes())['publication_complete'] is False


def test_command_exit_binds_exit_and_cleanup_across_complete_ordered_segments(small_journal):
    journal,_,root=small_journal
    journal.event('child_cleanup',label='original-runner',complete=True,cleanup_error=None)
    for i in range(16):journal.event('resources',phase='fixture:running',ordinal=i)
    journal.event('child_exit',label='original-runner',returncode=2)
    supervisor=SimpleNamespace(outcome_journal=journal,command=lambda *_a,**_k:b'misleading returncode=0')
    assert len(journal.closed)>=1 and O.command_exit(supervisor,'original-runner',[],{},root,root)==2
    (root/journal.closed[0]['path']).unlink()
    with pytest.raises((O.P.ProofRefused,OSError)):O.command_exit(supervisor,'original-runner',[],{},root,root)


def test_journal_index_write_failure_refuses_before_first_event(monkeypatch,tmp_path):
    desired=dict(qualified=True,smoke_pass=True);O.establish_negative_receipts(tmp_path,desired)
    def refused(*_a,**_k):raise O.P.ProofRefused('fixture durable index refusal')
    monkeypatch.setattr(O.K,'durable_json',refused)
    with pytest.raises(O.P.ProofRefused):O.SegmentedJournal(tmp_path,lambda *_a,**_k:pytest.fail('writer before initial durable index'),lambda:None)
    assert not (tmp_path/'progress.jsonl').exists()
    assert json.loads((tmp_path/'light/result.json').read_bytes())['qualified'] is False


@pytest.fixture
def publication(monkeypatch):
    pins=dict(control_sha="c"*40,run_id=71,job_id=72,attempt=1,artifact_id=73,artifact_bytes=4096,
        artifact_sha256="d"*64,artifact_expires_at="2099-01-01T00:00:00Z",completion_sha256="e"*64,proof_sha256="f"*64)
    monkeypatch.setattr(O.V,"REVIEWED_PRIMER",MappingProxyType(pins))
    monkeypatch.setattr(O.V,"REVIEWED_PREREQUISITES",MappingProxyType(dict(baseline_audit="a"*64)))
    delegated=[]
    monkeypatch.setattr(O.P,"validate_publication",lambda *_a,**_k:delegated.append("build"))
    monkeypatch.setattr(O.M,"validate_bootstrap_publication",lambda *_a,**_k:delegated.append("bootstrap"))
    monkeypatch.setattr(O.A,"validate_publication",lambda _meta,pin,_now:delegated.append(pin.role))
    monkeypatch.setattr(O.A,"validate_completed_job",lambda *_a,**_k:delegated.append("baseline_audit"))
    packet=dict(proofs=dict(baseline_audit=dict(producer=dict(control_sha="a"*40,run_id=7,job_id=8))))
    primer=dict(run=dict(id=71,head_sha=pins["control_sha"],head_branch=O.M.ACTIVE_BRANCH,path=O.M.WORKFLOW_PATH,
        run_attempt=1,status="completed",conclusion="success",repository=dict(full_name=O.P.REPOSITORY)),
        jobs=dict(jobs=[dict(id=72,run_id=71,head_sha=pins["control_sha"],status="completed",conclusion="success")]),
        artifact=dict(id=73,size_in_bytes=4096,digest="sha256:"+pins["artifact_sha256"],expired=False,expires_at=pins["artifact_expires_at"],
            name="wealth-production-primer-raw-71-1",workflow_run=dict(id=71,head_sha=pins["control_sha"])))
    metadata=dict(build={},bootstrap={},primer=primer,historical_template={},historical_procedural={},baseline_audit_job={})
    return packet,metadata,delegated


def test_fresh_checks_delegate_all_original_authorities_and_pin_primer(publication):
    packet,metadata,calls=publication
    assert O.validate_publications(metadata,packet,now=NOW)
    assert calls==["build","bootstrap","template-candidate","procedural-candidate","baseline_audit"]


@pytest.mark.parametrize("area,key,value",[("run","head_sha","0"*40),("run","head_branch","main"),("run","run_attempt",2),
    ("run","conclusion","failure"),("artifact","digest","sha256:"+"0"*64),("artifact","expired",True),
    ("artifact","size_in_bytes",1),("artifact","expires_at","2098-01-01T00:00:00Z"),("artifact","id",74)])
def test_wrong_primer_publication_refuses_before_wheel_admission(publication,area,key,value):
    packet,metadata,_=publication;metadata["primer"][area][key]=value
    with pytest.raises(O.P.ProofRefused):O.validate_publications(metadata,packet,now=NOW)


def test_current_source_dependencies_and_original_null_A_are_preserved():
    rows=O.source_bindings(ROOT)
    for name,digest in O.P.DEPENDENCIES.items():assert rows[name]["sha256"]==digest
    assert all(v is None for v in O.A.REVIEWED_CANDIDATE_PROOFS.values())
    if all(v is None for v in O.V.REVIEWED_PREREQUISITES.values()):
        assert O.V.ROOT_PREREQUISITE_PACKET_SHA256 is None and all(v is None for v in O.V.REVIEWED_PRIMER.values())
        assert O.V.ROOT_WORKER_SMOKE_PACKET_SHA256 is None and all(v is None for v in O.V.REVIEWED_WORKER_SMOKES.values())
    else:
        O.V.recheck_plan(O.load_plan(ROOT,"smoke"))
        if O.V.ROOT_WORKER_SMOKE_PACKET_SHA256 is not None or any(v is not None for v in O.V.REVIEWED_WORKER_SMOKES.values()):
            O.V.recheck_plan(O.load_plan(ROOT,"full"))
        else:
            with pytest.raises(O.P.ProofRefused,match="full cohort refused"):O.V.registration("full")


@pytest.mark.parametrize("failure",["publication","build"])
def test_execute_rejects_bad_inputs_before_any_environment_or_world_command(monkeypatch,tmp_path,failure):
    # Use a short owned fake workspace to satisfy the real bounded uploader-path
    # deployment rule. Its path is retained beside JUnit fixtures for inspection.
    assert shutil.disk_usage(ROOT).free>=3*1024**3+1024**2
    workspace=Path(tempfile.mkdtemp(prefix="wf-ofault-"))
    (tmp_path/"fake-workspace.txt").write_text(str(workspace))
    control=workspace/"control";source=workspace/"candidate";temporary=workspace/"temp"
    for p in (control,source,temporary):p.mkdir()
    root=temporary/"wealth-outcome-smoke-template"
    helpers=O.scientific_helpers(ROOT)
    monkeypatch.setattr(O,"SCRIPT",control/"scripts/wealth_floor_outcome_qualification.py")
    monkeypatch.setattr(O,"registration",lambda *_:dict(fixture_only=True))
    monkeypatch.setattr(O,"scientific_helpers",lambda *_:helpers)
    monkeypatch.setattr(O,"source_bindings",lambda *_:dict(fixture_only="source unchanged"))
    monkeypatch.setattr(O,"workflow_contract",lambda *_:True)
    monkeypatch.setattr(O,"staging_observation",lambda *_:None)
    monkeypatch.setattr(O.P,"read_bytes",lambda *_a,**_k:b"fixture workflow")
    monkeypatch.setattr(O.P,"read_json",lambda *_a,**_k:dict(build={}))
    monkeypatch.setattr(O.P,"hosted_vm_precondition",lambda:dict(fixture_only=True))
    monkeypatch.setattr(O.platform,"python_version",lambda:O.B.PYTHON_VERSION)
    monkeypatch.setattr(O.os,"sched_getaffinity",lambda _: {0,1})
    monkeypatch.setattr(O.os,"sched_setaffinity",lambda *_:None)
    for key,value in dict(GITHUB_REF="refs/heads/"+O.SMOKE_BRANCH,GITHUB_JOB="smoke",GITHUB_RUN_ATTEMPT="1",GITHUB_RUN_ID="123",GITHUB_SHA="a"*40,
        GITHUB_WORKSPACE=str(workspace),RUNNER_TEMP=str(temporary),GITHUB_OUTPUT=str(workspace/"github-output")).items():monkeypatch.setenv(key,value)
    calls=[]
    class Lease:
        def __enter__(self):return self
        def __exit__(self,*_):return False
    class Cancellation(Lease):cancelled=False
    class Supervisor:
        cleanup_complete=True
        def event(self,*_a,**_k):pass
        def admission(self,*_):pass
        def check(self,**_):pass
        def command(self,*_a,**_k):pytest.fail("input refusal reached environment/native/world command")
    monkeypatch.setattr(O.C,"Cancellation",Cancellation)
    monkeypatch.setattr(O.C,"SubreaperLease",Lease)
    monkeypatch.setattr(O.C,"legacy_helpers",lambda *_:None)
    monkeypatch.setattr(O.C,"make_supervisor",lambda *_:Supervisor())
    monkeypatch.setattr(O.C,"direct_children",lambda:[])
    def load(*_):calls.append("plan");return SimpleNamespace(prerequisite_packet=O.B.canonical_bytes(dict(fixture_only=True)))
    def publication(*_a,**_k):
        calls.append("publication")
        if failure=="publication":raise O.P.ProofRefused("fixture publication refusal")
    def build(*_a,**_k):calls.append("build");raise O.P.ProofRefused("fixture build refusal")
    monkeypatch.setattr(O,"load_plan",load);monkeypatch.setattr(O,"validate_publications",publication)
    monkeypatch.setattr(O.P,"admit_build",build)
    monkeypatch.setattr(O.K,"failure_body_selection",lambda *_a,**_k:dict(selected=[]))
    assert O.execute(SimpleNamespace(stage="smoke",worldgen="template",source=str(source),output=str(root)))==1
    assert calls==(["plan","publication"] if failure=="publication" else ["plan","publication","build"])
    result=json.loads((root/"light/completion.json").read_bytes())
    assert result["publication_complete"] is False and result["failure_stage"]=="source_and_prerequisite_content"
