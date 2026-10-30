"""Invented APIs, worker records and clocks only; never Native or real processes."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = spec_from_file_location("paired_contract_source",
    Path(__file__).resolve().parents[1]/"scripts/paired_context_benchmark.py")
pair = module_from_spec(_spec)
_spec.loader.exec_module(pair)


class TinySimulator:
    def get_agent_memories(self, agent):return []
    def get_agent_needs(self, agent):return (.5,)*6 if agent in (1,2) else None
    def get_agent_relationships(self, agent):return [] if agent in (1,2) else None
    def get_agent_context_batch(self, ids):
        return [(a,self.get_agent_memories(a),self.get_agent_needs(a),
            self.get_agent_relationships(a)) for a in ids]


def test_single_trial_uses_real_trial_order_and_keeps_zero_CPU(monkeypatch):
    core=pair.b
    monkeypatch.setattr(core,"RECORDS",2);monkeypatch.setattr(core,"WARMUP_RECORDS",2)
    spec=dict(case=0,slots=2,requests=1,layout="prefix",bond_slots=0)
    for cpu,status in ((Clock(),"complete"),(Clock(0),"refused")):
        journal=io.BytesIO()
        result=core.condition_trial(spec,TinySimulator(),[1,2],journal,Clock(),cpu,1)
        samples=[json.loads(line) for line in journal.getvalue().splitlines()]
        assert [r["helper"] for r in samples]==["batch","scalar"]
        assert all(r["case"]==0 and r["trial"]==1 for r in samples)
        assert result["trial"]==1 and result["status"]==status and len(samples)==2
        assert core.PAIRS==3 and "wall_ratio_scalar_over_batch" not in result
        if status=="refused":assert all(r["process_CPU_ns"]==0 and not r["accepted"] for r in samples)


class Clock:
    def __init__(self, step=100):
        self.value, self.step = 0, step

    def __call__(self):
        self.value += self.step
        return self.value


def workflow():
    return dict(GITHUB_SHA="c"*40,GITHUB_REF=pair.RUN_REF,GITHUB_JOB="benchmark",
        GITHUB_RUN_ID="1",GITHUB_RUN_ATTEMPT="1")


def builds():
    values = {}
    for role in pair.SOURCES:
        source, native = pair.SOURCES[role]
        values[role] = dict(kind="PAIRED_OWN_MEASURED_BUILD", method=pair.METHOD,
            role=role, source_commit=source, native_tree=native,
            controller_commit="c"*40, controller_tree="d"*40, driver={"script":"fake"},
            github=workflow(),
            controller_root="/fake/controller",measured_root="/fake/source-"+role,
            wheel_dir="/fake/wheels-"+role,venv_prefix="/fake/venv-"+role,
            worker_python="/fake/venv-"+role+"/bin/python",
            native_file="/fake/venv-"+role+"/native.so",
            python=dict(version="3.13.fake",binary="same-fake-binary"),host=dict(uname=["fake"],runner={}),
            distributions=[["pyarrow","fake"]],uv_lock="same-lock",cargo_lock="same-cargo",
            toolchain="same-tools",build_flags=dict(CARGO_BUILD_JOBS="1",CARGO_INCREMENTAL="0",
                RUSTFLAGS="",CARGO_TARGET_DIR="/fake/target-"+role),
            wheel_receipt=dict(wheel=dict(filename="own.whl",bytes=10,sha256="a"*64)))
    return values


def rows(job, *, zero=False, batch_wall=100):
    spec = pair.b.conditions()[job["case"]]
    ids, positions = pair.b.query_ids(list(range(1,spec["slots"]+1)),spec)
    expected = sum(agent+(0 if spec["layout"] == "missing" else 12+11*spec["bond_slots"])
        for agent in ids)*(20000//spec["requests"])
    order = ["scalar","batch"] if (job["case"]+job["trial"])%2 == 0 else ["batch","scalar"]
    timings = []
    for side in order:
        wall = batch_wall if side == "batch" else 100
        cpu = 0 if zero and side == "scalar" else 10
        timings.append(dict(case=job["case"],trial=job["trial"],helper=side,order=order,
            wall_start_ns=1000,wall_end_ns=1000+wall,wall_ns=wall,
            process_CPU_start_ns=2000,process_CPU_end_ns=2000+cpu,process_CPU_ns=cpu,
            checksum=expected,accepted=cpu>0))
    result = dict(spec,trial=job["trial"],request_ids=ids,slot_positions=positions,
        expected_checksum=expected,ordered_payload_sha256="a"*64,
        control_payload_sha256="b"*64,records_per_helper_trial=20000,
        repetitions=20000//spec["requests"],warmup_records_per_helper=200,
        status="refused" if zero else "complete")
    return [dict(kind="worker_start",role=job["role"],case=job["case"],trial=job["trial"],
        source_commit=pair.SOURCES[job["role"]][0],native_tree=pair.SOURCES[job["role"]][1],
        worker_pid=100+job["ordinal"],clock_info={key:dict(implementation="fake",monotonic=True,
            adjustable=False,resolution=.001) for key in ("wall","CPU")}),*timings,dict(kind="worker_end",result=result)]


def encoded(records):
    return b"".join((json.dumps(row,sort_keys=True,separators=(",",":"))+"\n").encode()
        for row in records)


def parsed(records,job):
    return pair.parse_fragment(encoded(records),job,100+job["ordinal"])


def small_schedule(monkeypatch,count=4):
    jobs = pair.schedule()[:count]
    monkeypatch.setattr(pair,"schedule",lambda:deepcopy(jobs))
    monkeypatch.setattr(pair,"plan",lambda:dict(kind="FAKE_PLAN",planned_workers=len(jobs),planned_timings=2*len(jobs)))
    return jobs


class FakeBackend:
    def __init__(self,zero_at=None,fail_at=None,cpu_us=20):
        self.zero_at,self.fail_at,self.cpu_us=zero_at,fail_at,cpu_us
        self.calls,self.closed,self.active=[],0,False

    def run(self,job,build,fragment,errors):
        assert self.active is False
        self.active=True
        self.calls.append(deepcopy(job))
        data=rows(job,zero=job["ordinal"] == self.zero_at)
        failed=job["ordinal"] == self.fail_at
        if failed:
            data=data[:2]+[dict(kind="worker_error",error=dict(type="Synthetic",message="first fault"))]
        fragment.write_bytes(encoded(data))
        errors.write_bytes(b"synthetic first fault" if failed else b"")
        self.active=False
        return dict(returncode=2 if failed else 0,worker_pid=100+job["ordinal"],cpu_us=self.cpu_us,
            waited_user_seconds=self.cpu_us/1000000,waited_system_seconds=0,
            maximum_worker_RSS_kib=1)

    def close(self):
        self.active=False
        self.closed+=1


def test_disabled_default_has_no_work(monkeypatch,capsys):
    def forbidden(*args,**kwargs):raise AssertionError("disabled mode performed work")
    for name in ("record_build","controller_limits","worker","record_owner","run_schedule"):
        monkeypatch.setattr(pair,name,forbidden)
    assert pair.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"


def test_fixed_schedule_orders_and_dose():
    jobs=pair.schedule();plan=pair.plan()
    assert len(jobs)==126 and len({(j["role"],j["case"],j["trial"]) for j in jobs})==126
    assert [j["ordinal"] for j in jobs] == list(range(126))
    for first,second in zip(jobs[::2],jobs[1::2]):
        assert (first["case"],first["trial"]) == (second["case"],second["trial"])
        expected=["parent","child"] if (first["case"]+first["trial"])%2==0 else ["child","parent"]
        assert [first["role"],second["role"]] == first["source_order"] == second["source_order"] == expected
    assert sum(j["role"]=="parent" for j in jobs[::2])==32
    assert plan["planned_timings"]==252 and plan["records_per_helper_trial"]==20000
    assert plan["warmup_records"]==200 and plan["trials"]==3
    assert len(plan["conditions"])==21 and plan["pool_lifetime"].startswith("fresh per")
    assert pair.CONTROLLER_AS+pair.WORKER_AS==pair.TOTAL_AS==2*1024**3
    assert pair.CPU_SECONDS==24 and pair.WORKER_CREDIT_US==512000000


@pytest.mark.parametrize("field,value,message",[
    ("role","child","build_role"),("source_commit","0"*40,"source_whitelist"),
    ("native_tree","0"*40,"source_whitelist"),("controller_commit","0"*40,"controller_identity"),
    ("driver",{},"controller_identity"),("worker_python","relative","build_path")])
def test_build_role_source_driver_and_path(field,value,message):
    build=builds()["parent"];build[field]=value
    with pytest.raises(ValueError,match=message):
        pair.validate_build(build,"parent","c"*40,{"script":"fake"},workflow())


@pytest.mark.parametrize("field,value",[("GITHUB_SHA","0"*40),("GITHUB_REF","refs/heads/main"),
    ("GITHUB_RUN_ATTEMPT","2"),("GITHUB_JOB","native"),("GITHUB_RUN_ID","2")])
def test_workflow_identity_is_controller_identity(field,value):
    build=builds()["parent"];build["github"][field]=value
    with pytest.raises(ValueError,match="actual_workflow_identity"):
        pair.validate_build(build,"parent","c"*40,{"script":"fake"},workflow())


def test_common_builds_isolation_and_wheel_bound():
    value=builds();pair.match_builds(value,verify_files=False)
    for field in ("python","host","github","distributions","uv_lock","cargo_lock","toolchain"):
        bad=deepcopy(value);bad["child"][field]="different"
        with pytest.raises(ValueError,match="unequal_build_environment"):
            pair.match_builds(bad,verify_files=False)
    for field in ("venv_prefix","wheel_dir"):
        bad=deepcopy(value);bad["child"][field]=bad["parent"][field]
        with pytest.raises(ValueError,match="isolated_environments"):
            pair.match_builds(bad,verify_files=False)
    value["parent"]["wheel_receipt"]["wheel"]["bytes"]=pair.b.MAX_WHEEL//2
    value["child"]["wheel_receipt"]["wheel"]["bytes"]=pair.b.MAX_WHEEL//2
    pair.match_builds(value,verify_files=False)
    value["child"]["wheel_receipt"]["wheel"]["bytes"]+=1
    with pytest.raises(ValueError,match="joint_wheel_limit"):pair.match_builds(value,verify_files=False)


def test_build_flags_and_separate_targets():
    for field,value in (("CARGO_TARGET_DIR","/fake/target-parent"),("CARGO_BUILD_JOBS","2"),
                        ("CARGO_INCREMENTAL","1"),("RUSTFLAGS","-C opt-level=0")):
        bad=builds();bad["child"]["build_flags"][field]=value
        with pytest.raises(ValueError):pair.match_builds(bad,verify_files=False)


@pytest.mark.parametrize("fault",["source","duplicate_helper","clock_join","accepted_zero","dose","status"])
def test_fragment_joins_identity_clock_and_dose(fault):
    job=pair.schedule()[0];value=rows(job,zero=fault in ("accepted_zero","status"))
    if fault=="source":value[0]["source_commit"]="0"*40
    if fault=="duplicate_helper":value[2]["helper"]=value[1]["helper"]
    if fault=="clock_join":value[1]["wall_end_ns"]+=1
    if fault=="accepted_zero":value[1]["accepted"]=True
    if fault=="dose":value[-1]["result"]["records_per_helper_trial"]-=1
    if fault=="status":value[-1]["result"]["status"]="complete"
    with pytest.raises(ValueError):parsed(value,job)


@pytest.mark.parametrize("field,value",[("ordered_payload_sha256","c"*64),
    ("control_payload_sha256","c"*64),("request_ids",[999]),("slot_positions",[999])])
def test_cross_source_payload_and_order(field,value):
    jobs=pair.schedule();parent=parsed(rows(jobs[0]),jobs[0])
    child=parsed(rows(jobs[1]),jobs[1]);pair.join_pair(parent,child)
    child[field]=value
    with pytest.raises(ValueError,match="cross_source_payload"):pair.join_pair(parent,child)


def test_worker_PID_must_match_the_reaped_process():
    job=pair.schedule()[0]
    with pytest.raises(ValueError):pair.parse_fragment(encoded(rows(job)),job,101+job["ordinal"])


def test_zero_CPU_retained_and_schedule_continues(tmp_path,monkeypatch):
    jobs=small_schedule(monkeypatch);backend=FakeBackend(zero_at=0)
    state=pair.run_schedule(builds(),tmp_path/"results",backend,Clock(),Clock())
    assert state["status"]=="refused" and len(backend.calls)==len(jobs)==4
    assert state["completed_workers"]==4 and state["retained_sample_rows"]==8
    assert [row["status"] for row in state["workers"]]==["refused","complete","complete","complete"]
    raw=[json.loads(line) for line in (tmp_path/"results/journal.jsonl").read_text().splitlines()]
    assert sum(r.get("process_CPU_ns")==0 for r in raw)==1
    assert backend.closed==1 and not backend.active
    assert not (tmp_path/"results/active.jsonl").exists()


def test_failed_worker_keeps_partial_and_not_run(tmp_path,monkeypatch):
    jobs=small_schedule(monkeypatch);backend=FakeBackend(fail_at=0)
    state=pair.run_schedule(builds(),tmp_path/"results",backend,Clock(),Clock())
    assert state["status"]=="failed" and len(backend.calls)==1
    assert state["completed_workers"]==0 and state["retained_sample_rows"]==1
    assert state["planned_timings"]==2*len(jobs) and state["retained_sample_rows"]!=state["planned_timings"]
    assert [r["status"] for r in state["workers"]]==["failed"]+["not_run"]*(len(jobs)-1)
    assert (tmp_path/"results/active.jsonl").exists()
    error=json.loads((tmp_path/"results/worker-error.json").read_text())
    assert bytes.fromhex(error["stderr_hex"])==b"synthetic first fault"
    assert backend.closed==1


def test_CPU_reservation_boundary(tmp_path,monkeypatch):
    assert pair.credit_admits(488000000) and not pair.credit_admits(488000001)
    assert not pair.credit_admits(-1) and not pair.credit_admits(False)
    small_schedule(monkeypatch);monkeypatch.setattr(pair,"WORKER_CREDIT_US",24000010)
    backend=FakeBackend(cpu_us=20)
    state=pair.run_schedule(builds(),tmp_path/"results",backend,Clock(),Clock())
    assert state["status"]=="resource_refused" and len(backend.calls)==1
    assert state["waited_worker_CPU_us"]==20 and state["retained_sample_rows"]==2
    assert [r["status"] for r in state["workers"]][1:]==["not_run"]*3


def test_deadline_leaves_registered_not_run(tmp_path,monkeypatch):
    small_schedule(monkeypatch);monkeypatch.setattr(pair,"WALL_NS",1);backend=FakeBackend()
    state=pair.run_schedule(builds(),tmp_path/"results",backend,Clock(1),Clock())
    assert state["status"]=="resource_refused" and backend.calls==[]
    assert state["retained_sample_rows"]==state["completed_workers"]==0 and backend.closed==1


def test_summary_keeps_regression_and_scalar_control():
    completed=[]
    for job in pair.schedule()[:6]:
        completed.append(parsed(rows(job,batch_wall=200 if job["role"]=="child" else 100),job))
    result=pair.summaries(completed)[0]
    assert result["child_change_percent"]["batch"]["wall_ns"]==100
    assert result["child_change_percent"]["scalar"]["wall_ns"]==0
    completed[0]["status"]="refused"
    assert pair.summaries(completed)==[dict(case=0,status="refused")]


@pytest.mark.parametrize("extra,refused",[(0,False),(1,True)])
def test_owner_counts_itself_at_boundary(extra,refused):
    value=dict(files=[],evidence_retention="within_body_cap",refusal=None)
    initial=(json.dumps(value,sort_keys=True,indent=2)+"\n").encode()
    result,body=pair.encode_owner(value,2048-len(initial)+extra,2048,1024)
    assert (result["refusal"] is not None) is refused
    assert len(body)<=1024
    if not refused:assert 2048-len(initial)+len(body)==2048
    assert value["refusal"] is None


def test_owner_inventory_refusal_is_bounded():
    result,body=pair.encode_owner(dict(files=["x"*3000],evidence_retention="within_body_cap",refusal=None),1,4096,512)
    assert result["files"]==[] and result["evidence_retention"]=="refused" and len(body)<=512


@pytest.mark.parametrize("truncated",[False,True])
def test_partial_build_keeps_structured_preplan_without_wheel_admission(tmp_path,monkeypatch,truncated):
    root=tmp_path/"evidence";root.mkdir();(root/"plan.json").write_text('{"planned_timings":252}')
    if truncated:
        (root/"comparison").mkdir();(root/"comparison/result.json").write_text("{")
    monkeypatch.setenv("GITHUB_OUTPUT",str(tmp_path/"outputs"))
    def absent(*args):raise ValueError("synthetic_missing_build")
    monkeypatch.setattr(pair,"read_build",absent)
    value=pair.record_owner(root,tmp_path/"wheels")
    assert value["refusal"] is None and value["evidence_retention"]=="within_body_cap"
    assert value["wheels_allowed"] is False and "synthetic_missing_build" in value["wheel_refusal"]
    assert value["actual_samples"] is None
    assert [r["path"] for r in value["files"]]==(["comparison/result.json","plan.json"] if truncated else ["plan.json"])


@pytest.mark.skipif(os.name!="posix",reason="POSIX tracked executable modes")
def test_seal_empty_and_executable(tmp_path):
    empty,script=tmp_path/"empty",tmp_path/"tool"
    empty.write_bytes(b"");script.write_bytes(b"abc");script.chmod(0o755)
    stage=b"100644 "+b"0"*40+b" 0\tempty\0"+b"100755 "+b"1"*40+b" 0\ttool\0"
    result=pair.seal_sources(tmp_path,stage)
    assert result["files"]==2 and result["bytes"]==3 and len(result["aggregate_sha256"])==64
    assert empty.stat().st_mode&0o777==0o444 and script.stat().st_mode&0o777==0o555


@pytest.mark.skipif(not hasattr(os,"wait4"),reason="POSIX wait4 lifecycle")
@pytest.mark.parametrize("broken",[False,True])
def test_system_backend_waits_serially_and_reaps_after_wait_failure(tmp_path,monkeypatch,broken):
    events=[];process=SimpleNamespace(pid=43210,returncode=None)
    process.kill=lambda:events.append("kill")
    paths={r:tmp_path/(r+".json") for r in pair.SOURCES}
    backend=pair.SystemBackend(paths);job=pair.schedule()[9];build=builds()[job["role"]]
    monkeypatch.setenv("GITHUB_SHA","c"*40);monkeypatch.setenv("GITHUB_JOB","benchmark")
    def bootstrap(pid):
        assert pid==os.getpid();events.append("bootstrap")
    monkeypatch.setattr(pair,"worker_bootstrap",bootstrap)
    def popen(argv,**kw):
        events.append("popen")
        assert argv[0]==build["worker_python"] and argv[1]=="-B"
        assert argv[argv.index("--role")+1]==job["role"]
        assert argv[argv.index("--case")+1]==str(job["case"])
        assert argv[argv.index("--trial")+1]==str(job["trial"])
        assert argv[-1]==str(paths[job["role"]])
        assert kw["env"]["GITHUB_SHA"]=="c"*40 and kw["env"]["GITHUB_JOB"]=="benchmark"
        assert not kw.get("start_new_session",False)
        kw["preexec_fn"]()  # Only the mocked bootstrap runs.
        return process
    calls=[]
    def wait(pid,options):
        events.append("wait");calls.append(pid)
        assert pid==43210 and options==0 and backend.active is process
        with pytest.raises(ValueError,match="overlapping_workers"):
            backend.run(job,build,tmp_path/"other",tmp_path/"other-error")
        if broken and len(calls)==1:raise RuntimeError("synthetic_wait_failure")
        return pid,0,SimpleNamespace(ru_utime=.125,ru_stime=.25,ru_maxrss=17)
    monkeypatch.setattr(pair.subprocess,"Popen",popen);monkeypatch.setattr(pair.os,"wait4",wait)
    args=(job,build,tmp_path/"fragment",tmp_path/"error")
    if broken:
        with pytest.raises(RuntimeError,match="synthetic_wait_failure"):backend.run(*args)
        assert events==["popen","bootstrap","wait","kill","wait"]
    else:
        result=backend.run(*args)
        assert result["cpu_us"]==375000 and result["worker_pid"]==43210
        assert events==["popen","bootstrap","wait"]
    assert backend.active is None and process.returncode==0


def test_failed_journal_fsync_retains_active_fragment_before_unlink(tmp_path,monkeypatch):
    jobs=small_schedule(monkeypatch);backend=FakeBackend()
    def failed(fd):raise OSError("synthetic_fsync_failure")
    monkeypatch.setattr(pair.os,"fsync",failed)
    state=pair.run_schedule(builds(),tmp_path/"results",backend,Clock(),Clock())
    assert state["status"]=="failed" and len(backend.calls)==1
    assert [r["status"] for r in state["workers"]]==["failed"]+["not_run"]*(len(jobs)-1)
    assert (tmp_path/"results/active.jsonl").exists() and backend.closed==1
