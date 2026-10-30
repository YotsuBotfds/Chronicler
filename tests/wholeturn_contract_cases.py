"""Explicit ordinary-guard cases; no native/product/NumPy/Arrow runtime."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
import wholeturn_protocol as p
import wholeturn_worker as worker
import wholeturn_controller as controller
import wholeturn_records as records


@pytest.fixture
def registration():
    return p.read_json(ROOT/p.REGISTRATION)


def ready(value):
    value = deepcopy(value)
    value["candidate"] = {"source_commit": "1"*40, "native_tree": "2"*40}
    value["root_decision"] = {"kind": "ROOT_REVIEWED_WHOLETURN_CANDIDATE", "protocol": p.PROTOCOL,
        "candidate_source": "1"*40, "candidate_native_tree": "2"*40,
        "source_review_sha256": "3"*64, "live_proof_review_sha256": "4"*64, "approval_id": "fake-source-contract-only"}
    return p.validate_registration(value)


def test_deferred_candidate_refuses_before_hosted_context_or_runtime(registration, monkeypatch, tmp_path):
    (tmp_path/p.REGISTRATION).parent.mkdir(parents=True)
    p.write_new(tmp_path/p.REGISTRATION, registration)
    def forbidden(*args, **kwargs):
        pytest.fail("deferred registration reached hosted/runtime work")
    monkeypatch.setattr(worker.build, "github_context", forbidden)
    monkeypatch.setattr(controller, "official_metadata", forbidden)
    with pytest.raises(p.Refused, match="DEFERRED"):
        worker.main(["role", "--controller-root", str(tmp_path), "--index", "0"])
    with pytest.raises(p.Refused, match="DEFERRED"):
        controller.admission(tmp_path, tmp_path/"runtime")
    assert not (tmp_path/"runtime").exists()


def test_closed_fixed_schedule_preserves_reverse_order_and_profile_seeds(registration):
    requests = p.schedule(registration)
    assert len(requests) == 12 and sum(q["turns"] for q in requests) == 2400
    assert [(q["regions"], q["seed"], q["profiled"], q["arm"]) for q in requests] == [
        (8,42,False,"baseline"),(8,42,False,"candidate"),(8,43,False,"candidate"),(8,43,False,"baseline"),
        (8,42,True,"baseline"),(8,42,True,"candidate"),(32,42,False,"baseline"),(32,42,False,"candidate"),
        (32,43,False,"candidate"),(32,43,False,"baseline"),(32,42,True,"candidate"),(32,42,True,"baseline")]


@pytest.mark.parametrize("field,value", [("horizon",True),("global_rng_seed",False),
    ("run_ref","refs/heads/main"),("windows",[[8,17],[188,196]])])
def test_method_changes_are_refused(registration, field, value):
    registration[field] = value
    with pytest.raises(p.Refused):
        p.validate_registration(registration, ready=False)


def test_root_decision_joins_both_candidate_pins_and_scope(registration):
    value = ready(registration)
    value["root_decision"]["candidate_native_tree"] = "5"*40
    with pytest.raises(p.Refused, match="join"):
        p.validate_registration(value)
    value = ready(registration)
    value["root_decision"]["permit_latest"] = True
    with pytest.raises(p.Refused, match="exact"):
        p.validate_registration(value)


@pytest.mark.parametrize("body", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_duplicate_and_nonfinite_json_refuse(body):
    with pytest.raises(p.Refused):
        p.strict_json(body)


@pytest.mark.parametrize("end", [0, -1, True, None, {"clock_error":"RuntimeError"}])
def test_bad_raw_endpoints_remain_visible_and_never_make_a_ratio(end):
    raw = {"CPU_start_ns":0,"CPU_end_ns":end,"wall_start_ns":0,"wall_end_ns":1}
    value = p.interval(raw)
    assert value["raw"] == raw and not value["numerically_valid"]
    assert p.ratio(value, value)["status"] == "NUMERICAL_REFUSAL"


def test_real_regression_ratio_is_retained():
    def clock(cpu, wall):
        return p.interval(dict(CPU_start_ns=100,CPU_end_ns=100+cpu,wall_start_ns=200,wall_end_ns=200+wall))
    result = p.ratio(clock(10,10), clock(17,13))
    assert result["CPU_candidate_over_baseline"] == 1.7
    assert result["wall_candidate_over_baseline"] == 1.3


def test_clock_exception_and_float_bits_survive_before_validation():
    def fail():
        raise RuntimeError("clock failed")
    assert p.sample_ns(fail) == {"clock_error":"RuntimeError"}
    assert p.sample_ns(lambda:-0.0) == {"invalid_clock_type":"float64","bits":"8000000000000000"}


def test_remaining_roles_cannot_borrow_finalization_reserve(registration):
    assert p.budget_room(registration,elapsed_wall=0,consumed_CPU=0,roles_left=12,comparisons_left=6)
    with pytest.raises(p.Refused, match="reserved"):
        p.budget_room(registration,elapsed_wall=91,consumed_CPU=0,roles_left=12,comparisons_left=6)


@pytest.mark.parametrize("change", ["wrong_source","expired_job"])
def test_official_job_clock_refuses_wrong_source_and_expired_job(change):
    context={"GITHUB_RUN_ID":"19","GITHUB_SHA":"a"*40}
    run={"id":19,"run_attempt":1,"head_sha":"a"*40,"head_branch":p.RUN_REF.removeprefix("refs/heads/"),
         "path":controller.WORKFLOW,"event":"push","status":"in_progress","conclusion":None,
         "repository":{"id":controller.REPOSITORY_ID}}
    jobs={"total_count":1,"jobs":[{"id":20,"name":"wholeturn","run_id":19,"run_attempt":1,
        "head_sha":"a"*40,"status":"in_progress","started_at":"2026-10-30T00:00:00Z"}]}
    date="Fri, 30 Oct 2026 00:01:00 GMT"
    if change=="wrong_source": run["head_sha"]="b"*40
    else: date="Fri, 30 Oct 2026 02:01:00 GMT"
    with pytest.raises(p.Refused): controller.validate_job_clock(run,jobs,date,context,100)


class Journal:
    def __init__(self): self.rows=[]
    def emit(self, value): self.rows.append(deepcopy(value))


class Profile:
    def __init__(self, **kwargs): self.events=[]; self.stats={}
    def enable(self): self.events.append("enable")
    def disable(self): self.events.append("disable")
    def create_stats(self): pass


@pytest.mark.parametrize("profiled", [False, True])
def test_late_boundary_observes_exactly_200_turns_and_two_windows(profiled):
    journal, number = Journal(), iter(range(100,1000))
    observer = worker.Boundary(profiled,[[8,16],[188,196]],journal,Profile,
                               cpu=lambda:next(number),wall=lambda:next(number))
    observer.bind(lambda path:path,{"fixture":"same"})
    assert all(observer.turn_end(SimpleNamespace(turn=t)) is False for t in range(1,201))
    assert observer.last == 200 and [(r["start"],r["end"]) for r in observer.records] == [(8,16),(188,196)]
    assert [r["kind"] for r in journal.rows] == ["WINDOW_START_RAW","WINDOW_RAW"]*2
    assert [x.events for x in observer.profiles] == ([["enable","disable"]]*2 if profiled else [[],[]])


def test_boundary_clock_failure_is_journaled_without_extra_turn():
    journal = Journal()
    observer = worker.Boundary(False,[[8,16],[188,196]],journal,Profile,cpu=lambda:False,wall=lambda:10)
    for turn in range(1,8): observer.turn_end(SimpleNamespace(turn=turn))
    with pytest.raises(p.Refused, match="starting clock"):
        observer.turn_end(SimpleNamespace(turn=8))
    assert observer.last == 8 and journal.rows[-1]["CPU_start_ns"] is False
    assert not observer.records


def test_owned_inventory_rejects_symlink_and_multiple_links(tmp_path):
    (tmp_path/"a").write_bytes(b"body")
    (tmp_path/"link").symlink_to(tmp_path/"a")
    with pytest.raises(p.Refused): controller.inventory(tmp_path,maximum_bytes=100)
    (tmp_path/"link").unlink()
    import os
    os.link(tmp_path/"a",tmp_path/"b")
    with pytest.raises(p.Refused): controller.inventory(tmp_path,maximum_bytes=100)


def test_compact_failure_keeps_all_slots_and_raw_negative_clocks(registration,tmp_path):
    root = tmp_path/"controller"
    p.write_new(root/p.REGISTRATION,registration)
    saved = tmp_path/"saved"
    p.write_new(saved/"raw/roles/0/timing.jsonl", b'{"kind":"WINDOW_RAW","CPU_start_ns":9,"CPU_end_ns":2}\n')
    requests=p.schedule(registration)
    p.write_new(saved/"raw/owner.json", {"roles":[{"request":q,"status":"NOT_ATTEMPTED"} for q in requests],
        "comparisons":[],"status":"FIRST_FAILURE_NO_REPLAY","raw_custody_proven":True,"raw_upload_allowed":True,
        "final_raw_inventory":controller.inventory(saved/"raw",maximum_bytes=p.MIB,hash_bodies=False)})
    selected = records.selected_records(root,saved,"failure")
    output=tmp_path/"original.zip"
    records.pack(selected,output)
    inspected = records.inspect_original(output)["data"]
    assert len(inspected["roles.json"]) == 12 and len(inspected["pairs.json"]) == 6
    assert '"CPU_end_ns":2' in inspected["roles.json"][0]["timing_journal"]
    assert inspected["summary.json"]["actual_step_outcome"] == "failure"
    assert inspected["summary.json"]["scientific_qualification"] is None


def test_compact_cannot_raise_body_budget_to_fit(tmp_path):
    with pytest.raises(p.Refused,match="expanded"):
        records.pack({"summary.json":b"x"*p.MIB,"roles.json":b"[]","pairs.json":b"[]"},tmp_path/"oversize.zip")
    assert not (tmp_path/"oversize.zip").exists()


def test_first_owned_failure_preserves_partial_output_and_prevents_replay(registration,tmp_path):
    value=ready(registration)
    root=tmp_path/"owner"
    for path in ("ordinary","raw/roles","raw/comparisons","raw/shared-rng"): (root/path).mkdir(parents=True,exist_ok=True)
    class Backend:
        calls=0
        def run(self, argv, log, **bounds):
            self.calls+=1
            ordinary=Path(argv[argv.index("--ordinary")+1])
            (ordinary/"partial.json").write_bytes(b'{"partial":true}')
            p.write_new(log,b"first negative\n")
            return {"actual_exit":7,"refusal":None,"quiescent":True,"wall_seconds":0,"command_tree_CPU_seconds":0}
    backend=Backend()
    builds={arm:{"worker_python":"NEVER_EXECUTED"} for arm in ("baseline","candidate")}
    assert controller.run_schedule(value,builds,backend,root,tmp_path,observe=lambda *a,**k:{}) == 2
    saved=p.read_json(root/"raw/owner.json",2*p.MIB)
    assert backend.calls == 1 and saved["roles"][0]["actual"]["actual_exit"] == 7
    assert all(row["status"] == "NOT_ATTEMPTED" for row in saved["roles"][1:])
    assert (root/"raw/roles/0/ordinary-partial/partial.json").read_bytes() == b'{"partial":true}'


# Corrective source contracts: strict global RNG and incomplete custody.
import wholeturn_state_proof as exact_proof
import wholeturn_live_proof as live_proof


def actual_rng_fixture():
    return {"python":[3,[0]*624+[0],0.0],"numpy":["MT19937",[0]*624,0,0,0.0]}


@pytest.mark.parametrize("join",[worker.require_matching_inputs,controller.require_profile_plain])
@pytest.mark.parametrize("field",["initial_rng","final_rng"])
@pytest.mark.parametrize("cache",["python","numpy"])
def test_corrective_signed_zero_global_cache_mismatch_refuses_both_actual_joins(join,field,cache):
    left={"run_config":{},"effective_flags":{},"proof":{},"initial_rng":actual_rng_fixture(),"final_rng":actual_rng_fixture()}
    right=deepcopy(left)
    right[field][cache][2 if cache=="python" else 4]=-0.0
    assert left[field] == right[field]  # the old ordinary-equality blind spot
    with pytest.raises(p.Refused,match="RNG"):
        join(left,right)


@pytest.mark.parametrize("join",[worker.require_matching_inputs,controller.require_profile_plain])
def test_corrective_equal_actual_rng_states_remain_admitted(join):
    left={"run_config":{},"effective_flags":{},"proof":{},"initial_rng":actual_rng_fixture(),"final_rng":actual_rng_fixture()}
    join(left,deepcopy(left))


def test_corrective_measured_end_to_proof_gap_uses_strict_rng(monkeypatch,tmp_path):
    measured=actual_rng_fixture(); at_proof=deepcopy(measured); at_proof["numpy"][4]=-0.0
    calls=[]
    rc=SimpleNamespace(write_checkpoint=lambda *args:calls.append("writer"))
    monkeypatch.setattr(exact_proof,"capture_rng",lambda np:at_proof)
    with pytest.raises(exact_proof.Refused,match="measured-end to proof"):
        live_proof.capture_terminal(lambda path:calls.append("save"),tmp_path/"never.ckpt",rc,(),None,expected_rng=measured)
    assert calls == []


@pytest.mark.parametrize("state",["eventually_quiet","members_remain","leader_not_terminal","membership_unreadable"])
def test_corrective_postkill_group_observation_is_bounded_and_requires_quiescence(state):
    clock=[0.0]; observations=[]; kills=[]
    def members(group,leader):
        observations.append((group,leader))
        if state=="membership_unreadable": raise PermissionError("proc observation unavailable")
        return [] if state=="leader_not_terminal" or state=="eventually_quiet" and len(observations)>1 else [71]
    result=controller.settle_owned_group(70,70,.05,terminal=lambda:state!="leader_not_terminal",
        members=members,kill=lambda *args:kills.append(args),now=lambda:clock[0],pause=lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    assert result["proven"] is (state=="eventually_quiet")
    assert len(kills)==1 and len(observations)<=4 and clock[0]<=.05


def test_corrective_raising_backend_keeps_unknown_exit_and_never_archives_or_inventories(registration,tmp_path,monkeypatch):
    value=ready(registration); root=tmp_path/"raising-owner"
    for name in ("ordinary","raw/roles","raw/comparisons","raw/shared-rng"): (root/name).mkdir(parents=True,exist_ok=True)
    observed=[]
    monkeypatch.setattr(controller,"inventory",lambda *a,**k:observed.append("UNSAFE_INVENTORY"))
    class Backend:
        calls=0
        def run(self,argv,log,**bounds):
            self.calls+=1
            (Path(argv[argv.index("--ordinary")+1])/"still-owned.json").write_bytes(b"partial")
            raise OSError("backend after possible launch")
    backend=Backend(); builds={arm:{"worker_python":"NEVER_EXECUTED"} for arm in ("baseline","candidate")}
    assert controller.run_schedule(value,builds,backend,root,tmp_path,observe=lambda *a,**k:{})==2
    saved=p.read_json(root/"raw/owner.json",2*p.MIB)
    assert backend.calls==1 and saved["roles"][0]["status"]=="FAILED_UNKNOWN_EXIT"
    assert saved["roles"][0]["actual_exit"] is None and not saved["raw_upload_allowed"]
    assert not saved["raw_custody_proven"] and "final_raw_inventory" not in saved and observed==[]
    assert (root/"ordinary/current/still-owned.json").exists()
    assert not (root/"raw/roles/0/ordinary-partial").exists()
    intent=p.read_json(root/"raw/roles/0/launch-intent.json")
    assert not intent["process_started_proven"]


@pytest.mark.parametrize("owner_exists",[False,True])
def test_corrective_unknown_custody_packer_reads_parent_intents_only(registration,tmp_path,monkeypatch,owner_exists):
    ctrl=tmp_path/"ctrl"; p.write_new(ctrl/p.REGISTRATION,registration)
    root=tmp_path/"unsafe"
    request=p.schedule(registration)[0]
    controller.launch_intent(root/"raw/roles/0/launch-intent.json",request,"ROLE_LAUNCH_INTENT")
    p.write_new(root/"raw/roles/0/result.json",b"possibly active child data")
    if owner_exists:
        p.write_new(root/"raw/owner.json",{"status":"FIRST_FAILURE_NO_REPLAY","roles":[{"request":q,"status":"FAILED_UNKNOWN_EXIT" if q["index"]==0 else "NOT_ATTEMPTED"} for q in p.schedule(registration)],
            "comparisons":[],"raw_custody_proven":False,"raw_upload_allowed":False})
    original=records.optional_json
    def only_parent(path,*args):
        assert Path(path).name not in ("result.json","profile-functions.json","timing.jsonl")
        return original(path,*args)
    monkeypatch.setattr(records,"optional_json",only_parent)
    monkeypatch.setattr(records,"profile_projection",lambda *a:pytest.fail("unsafe profile read"))
    selected=records.selected_records(ctrl,root,"failure")
    summary=p.strict_json(selected["summary.json"]); roles=p.strict_json(selected["roles.json"])
    assert not summary["raw_upload_allowed"] and not summary["child_body_reads_allowed"]
    assert roles[0]["role_data"] is None and not roles[0]["parent_launch_intent"]["process_started_proven"]


def test_corrective_comparison_backend_exception_is_durable_attempt_with_unknown_exit(registration,tmp_path,monkeypatch):
    value=ready(registration); root=tmp_path/"pair-failure"
    for name in ("ordinary","raw/roles","raw/comparisons","raw/shared-rng"): (root/name).mkdir(parents=True,exist_ok=True)
    unsafe_inventory=[]; original=controller.inventory
    class Backend:
        calls=0; failed=False
        def run(self,argv,log,**bounds):
            self.calls+=1
            if "compare" in argv:
                self.failed=True
                Path(argv[argv.index("--output")+1]).write_bytes(b"partial comparison")
                raise OSError("possible comparison writer")
            index=int(argv[argv.index("--index")+1]); request=p.schedule(value)[index]
            out=Path(argv[argv.index("--output")+1]); ordinary=Path(argv[argv.index("--ordinary")+1])
            (ordinary/"state.json").write_bytes(b"equal")
            p.write_new(log,b"fake-role-only\n")
            p.write_new(out/"result.json",{"request":request,"proof_complete":True,"run_config":{},"effective_flags":{},"proof":{},
                "initial_rng":actual_rng_fixture(),"final_rng":actual_rng_fixture()})
            return {"actual_exit":0,"refusal":None,"quiescent":True}
    backend=Backend()
    def observed_inventory(*args,**kwargs):
        if backend.failed: unsafe_inventory.append(str(args[0]))
        return original(*args,**kwargs)
    monkeypatch.setattr(controller,"inventory",observed_inventory)
    builds={arm:{"worker_python":"NEVER_EXECUTED"} for arm in ("baseline","candidate")}
    assert controller.run_schedule(value,builds,backend,root,tmp_path,observe=lambda *a,**k:{})==2
    saved=p.read_json(root/"raw/owner.json",2*p.MIB)
    assert backend.calls==3 and len(saved["comparisons"])==1
    assert saved["comparisons"][0]["status"]=="FAILED_UNKNOWN_EXIT"
    assert (root/"raw/comparisons/template-plain-42/launch-intent.json").exists()
    assert unsafe_inventory==[] and not saved["raw_upload_allowed"]


def test_corrective_raw_artifact_workflow_requires_explicit_quiescence_output():
    import yaml
    workflow=yaml.safe_load((ROOT/".github/workflows/matched-wholeturn.yml").read_text())
    uploads=[step for step in workflow["jobs"]["wholeturn"]["steps"] if "/matched-wholeturn/raw/" in str(step.get("with",{}).get("path",""))]
    assert uploads
    for step in uploads:
        assert "steps.compact.outcome == 'success'" in step["if"]
        assert "steps.compact.outputs.raw_upload_allowed == 'true'" in step["if"]
