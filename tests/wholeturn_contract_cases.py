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
    value = p.read_json(ROOT/p.REGISTRATION)
    value["candidate"] = {"source_commit": None, "native_tree": None}
    value["root_decision"] = None
    return value


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


def _legacy_workflow_before_cache_identity_pilot(path, body):
    """Validate only the reviewed pilot addition, then expose exact legacy bytes."""
    import hashlib

    assert type(body) is bytes
    if path == ".github/workflows/wholeturn-cache-identity-pilot.yml":
        assert hashlib.sha256(body).hexdigest() == "b149edf1e029174e58a5e3ba76f93fa2920f3233f8c5287dc0a6dcd5f4b74be7"
        return body.decode("utf-8")
    if path == ".github/workflows/tests.yml":
        added = b", lead/wholeturn-cache-identity-pilot-tests-20261030"
        legacy = b", lead/wholeturn-file-integrity-tests-20261030]"
        current = legacy[:-1] + added + b"]"
        assert body.count(added) == body.count(current) == 1
        body = body.replace(current, legacy, 1)
        expected = "77f407483a17c58452bc19a8f7b41aabe246f7f2ca727eb333aff45c09db9c59"
    elif path == ".github/workflows/workflow-semantics.yml":
        added = b", lead/wholeturn-cache-identity-pilot-semantics-20261030"
        legacy = b", lead/wholeturn-file-integrity-semantics-20261030]"
        current = legacy[:-1] + added + b"]"
        guard = b" || github.ref == 'refs/heads/lead/wholeturn-cache-identity-pilot-semantics-20261030'"
        old_guard = b" || github.ref == 'refs/heads/lead/wholeturn-file-integrity-semantics-20261030'"
        assert body.count(added) == body.count(current) == body.count(guard) == 1
        assert body.count(old_guard + guard + b"\n") == 1
        body = body.replace(current, legacy, 1).replace(old_guard + guard + b"\n", old_guard + b"\n", 1)
        expected = "0d43caa2d58e870e5acd5d4669c9a68c5aee5dde9d00a3dcfd32be4eb47ed538"
    else:
        raise AssertionError("unreviewed workflow projection")
    assert hashlib.sha256(body).hexdigest() == expected
    return body.decode("utf-8")


def test_current_ready_candidate_reviews_and_exact_activation_inventory():
    import yaml

    actual = p.read_json(ROOT/p.REGISTRATION)
    assert p.validate_registration(actual) is actual
    assert actual["candidate"] == {
        "source_commit":"643cda4d73edd9cfdfe83c619932906c579f7473",
        "native_tree":"0dca68c36baa2663c66dcf45bb4afd0c5696b18f",
    }
    assert actual["root_decision"] == {
        "kind":"ROOT_REVIEWED_WHOLETURN_CANDIDATE", "protocol":p.PROTOCOL,
        "candidate_source":"643cda4d73edd9cfdfe83c619932906c579f7473",
        "candidate_native_tree":"0dca68c36baa2663c66dcf45bb4afd0c5696b18f",
        "source_review_sha256":"29e1d8bcf02a5a0a07fe580665bd7d5ec6fb34019eb3d7d4199192d1db1c0503",
        "live_proof_review_sha256":"161ff1198de1345e40aeb1e5d46b408331652c4bc501d6181588a51ee08501a3",
        "approval_id":"root-wholeturn-ready-643cda4d-20261030",
    }
    workflows = sorted(path.relative_to(ROOT).as_posix()
        for path in (ROOT/".github/workflows").rglob("*") if path.suffix in (".yml",".yaml"))
    pilot = ".github/workflows/wholeturn-cache-identity-pilot.yml"
    _legacy_workflow_before_cache_identity_pilot(pilot, (ROOT/pilot).read_bytes())
    assert workflows.count(pilot) == 1
    workflows.remove(pilot)
    assert workflows == [
        ".github/workflows/matched-wholeturn.yml",
        ".github/workflows/native-two-shards-v2.yml",
        ".github/workflows/native-two-shards.yml",
        ".github/workflows/tests.yml",
        ".github/workflows/validation-gate.yml",
        ".github/workflows/workflow-semantics.yml",
    ]
    tests = yaml.load(_legacy_workflow_before_cache_identity_pilot(".github/workflows/tests.yml", (ROOT/".github/workflows/tests.yml").read_bytes()),Loader=yaml.BaseLoader)
    branches = tests["on"]["push"]["branches"]
    assert branches.count("lead/wholeturn-staging-tests-20261030") == 1
    assert not set(branches) & {"lead/wholeturn-staging-ready-source-20261030",
        "lead/wholeturn-staging-semantics-20261030","lead/wholeturn-staging-run002-20261030"}
    semantic = yaml.load(_legacy_workflow_before_cache_identity_pilot(".github/workflows/workflow-semantics.yml", (ROOT/".github/workflows/workflow-semantics.yml").read_bytes()),Loader=yaml.BaseLoader)
    assert semantic["on"]["push"]["branches"] == ["lead/workflow-semantics-20261030",
        "lead/simulation-staging004-semantics-20261030","lead/wholeturn-staging-semantics-20261030","lead/wholeturn-file-integrity-semantics-20261030"]
    assert semantic["jobs"]["actionlint"]["if"] == (
        "github.event_name == 'pull_request' || github.ref == 'refs/heads/lead/workflow-semantics-20261030'"
        " || github.ref == 'refs/heads/lead/simulation-staging004-semantics-20261030'"
        " || github.ref == 'refs/heads/lead/wholeturn-staging-semantics-20261030' || github.ref == 'refs/heads/lead/wholeturn-file-integrity-semantics-20261030'")
    benchmark = yaml.load((ROOT/".github/workflows/matched-wholeturn.yml").read_text(),Loader=yaml.BaseLoader)
    assert benchmark["on"]["push"]["branches"] == ["lead/wholeturn-staging-run002-20261030"]
    assert benchmark["jobs"]["wholeturn"]["if"] == "github.ref == 'refs/heads/lead/wholeturn-staging-run002-20261030'"


def _file_integrity_execute_fixture(registration, tmp_path, monkeypatch):
    """Real small files, fake build/context seam; never import compiled modules."""
    import time

    ctrl = tmp_path/"controller"
    p.write_new(ctrl/p.REGISTRATION, ready(registration))
    root = tmp_path/"admitted"
    root.mkdir()
    context = {"GITHUB_SHA":"a"*40, "GITHUB_REF":p.RUN_REF,
        "GITHUB_RUN_ID":"123", "GITHUB_RUN_ATTEMPT":"1", "GITHUB_JOB":"wholeturn"}
    drivers = {"wholeturn_protocol.py":{"bytes":1,"sha256":"d"*64}}
    monkeypatch.setattr(controller.build,"github_context",lambda *_:context)
    monkeypatch.setattr(controller.build,"driver_pins",lambda *_:drivers)
    monkeypatch.setattr(controller.build,"validate_builds",lambda *args:args[1])
    p.write_new(root/"admission.json", {"github":context,"root":str(root),
        "registration":p.pin(ctrl/p.REGISTRATION),"drivers":drivers,
        "job_clock":{"deadline_monotonic_ns":time.monotonic_ns()+4920*10**9}})
    values, paths = {}, {}
    for arm in ("baseline","candidate"):
        base = tmp_path/arm
        source = base/"source.fixture"
        native = base/"installed-native.fixture"
        wheel = base/"wheels/own-wheel.fixture"
        for path in (source,native,wheel):p.write_new(path,b"five!")
        values[arm] = {"arm":arm,"measured_root":str(base),"sealed_source":{"fixture":arm},
            "native_file":str(native),"wheel_dir":str(wheel.parent),
            "wheel_receipt":{"installed_native":p.pin(native),
                "wheel":{"filename":wheel.name,**p.pin(wheel)}}}
        paths[arm] = {"source":source,"installed_native":native,"wheel":wheel}
        p.write_new(root/"metadata"/arm/"build.json",values[arm])
    def source_manifest(path,value):
        p.pin(paths[value["arm"]]["source"],64*p.MIB)
        return value["sealed_source"]
    monkeypatch.setattr(controller.build,"source_manifest",source_manifest)
    def no_backend_or_role(*args,**kwargs):
        pytest.fail("failed preflight reached backend or role scheduling")
    monkeypatch.setattr(controller,"SystemBackend",no_backend_or_role)
    monkeypatch.setattr(controller,"run_schedule",no_backend_or_role)
    return ctrl,root,values,paths


def test_file_integrity_pin_keeps_unique_refusal_and_bounded_observed_metadata(tmp_path):
    import os
    target = tmp_path/"owned.fixture"
    p.write_new(target,b"five!")
    expected = p.pin(target)
    os.link(target,tmp_path/"alias.fixture")
    with pytest.raises(p.Refused,match="^bounded unique regular file$") as caught:
        p.pin(target,5)
    detail = caught.value.pin_failure
    assert detail["path"] == str(target) and not detail["path_truncated"]
    assert detail["lstat"]["nlink"] == 2 and detail["lstat"]["bytes"] == 5
    assert detail["maximum"] == 5
    (tmp_path/"alias.fixture").unlink()
    assert p.pin(target,5) == expected


def test_file_integrity_own_install_copy_flags_and_early_native_attestation():
    import ast
    import yaml
    workflow = yaml.load((ROOT/".github/workflows/matched-wholeturn.yml").read_text(),Loader=yaml.BaseLoader)
    installs = [step["run"] for step in workflow["jobs"]["wholeturn"]["steps"]
        if step.get("id") in ("baseline","candidate")]
    assert len(installs) == 2
    for arm,command in zip(("baseline","candidate"),installs):
        line = 'uv pip install --link-mode copy --python "$RUNNER_TEMP/wholeturn-venv-'+arm+'/bin/python" "$RUNNER_TEMP/matched-wholeturn/metadata/'+arm+'/wheels/"*.whl'
        assert command.splitlines().count(line) == 1
    source = (ROOT/"scripts/wholeturn_build.py").read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=="record_build")
    body = ast.get_source_segment(source,function)
    assert body.index("p.pin(native_path, 64*p.MIB)") < body.index("schemas = {}") < body.index("p.write_new(output")
    assert 'wheel["installed_native"][k]' in body


@pytest.mark.parametrize("arm,stage",[("baseline","installed_native"),("candidate","installed_native"),
    ("baseline","source"),("baseline","wheel")])
def test_file_integrity_failed_pin_stage_is_durable_before_backend(registration,tmp_path,monkeypatch,arm,stage):
    import os
    ctrl,root,values,paths = _file_integrity_execute_fixture(registration,tmp_path,monkeypatch)
    target = paths[arm][stage]
    os.link(target,tmp_path/"second-owner.fixture")
    with pytest.raises(p.Refused,match="bounded unique regular file"):
        controller.execute(ctrl,root,root/"metadata/baseline/build.json",root/"metadata/candidate/build.json")
    failure = p.read_json(root/"metadata/execute-preflight-failure.json")
    assert failure["status"] == "PRE_RUN_SCHEDULE_FAILURE"
    assert failure["stage"] == "recheck_build" and failure["arm"] == arm
    assert failure["build_recheck_stage"] == stage
    assert failure["error"]["type"] == "Refused" and failure["error"]["reason"] == "bounded unique regular file"
    assert failure["pin_failure"]["path"] == str(target)
    assert failure["pin_failure"]["lstat"]["nlink"] == 2
    assert failure["child_launch_attempted"] is False
    assert not (root/"raw").exists() and not (root/"ordinary").exists()


def test_file_integrity_non_pin_failure_is_not_misidentified_as_native_ownership(registration,tmp_path,monkeypatch):
    ctrl,root,values,paths = _file_integrity_execute_fixture(registration,tmp_path,monkeypatch)
    def unequal(*args):raise p.Refused("unequal paired build environment/schema: fixture")
    monkeypatch.setattr(controller.build,"validate_builds",unequal)
    with pytest.raises(p.Refused,match="unequal paired"):
        controller.execute(ctrl,root,root/"metadata/baseline/build.json",root/"metadata/candidate/build.json")
    failure = p.read_json(root/"metadata/execute-preflight-failure.json")
    assert failure["stage"] == "paired_builds" and failure["arm"] is None
    assert failure["pin_failure"] is None and failure["build_recheck_stage"] is None
    assert failure["error"]["reason"] == "unequal paired build environment/schema: fixture"
    assert failure["child_launch_attempted"] is False


def test_file_integrity_unadmitted_root_is_never_given_a_parent_failure_record(registration,tmp_path,monkeypatch):
    ctrl,root,values,paths = _file_integrity_execute_fixture(registration,tmp_path,monkeypatch)
    admission = p.read_json(root/"admission.json")
    admission["root"] = str(tmp_path/"different-root")
    monkeypatch.setattr(controller.p,"read_json",lambda path,*args:admission if Path(path)==root/"admission.json" else pytest.fail("unadmitted root reached build read"))
    monkeypatch.setattr(controller.p,"load_registration",lambda *args:ready(registration))
    with pytest.raises(p.Refused,match="same admitted source/root"):
        controller.execute(ctrl,root,root/"metadata/baseline/build.json",root/"metadata/candidate/build.json")
    assert not (root/"metadata/execute-preflight-failure.json").exists()


def test_file_integrity_ownerless_compact_keeps_canonical_builds_and_parent_failure(registration,tmp_path,monkeypatch):
    ctrl = tmp_path/"controller"
    p.write_new(ctrl/p.REGISTRATION,registration)
    root = tmp_path/"runtime"
    fields = ("kind","protocol","arm","source_commit","native_tree","controller_commit","github",
        "driver_pins","registration","wheel_receipt","schemas","python","package_digest","python_binary",
        "distributions","uv_lock","cargo_lock","cargo_manifest","toolchain","build_flags")
    originals = {}
    for arm in ("baseline","candidate"):
        value = {field:{"fixture":field} for field in fields}
        value.update(arm=arm,sealed_source={"count":7,"digest":"a"*64})
        path = root/"metadata"/arm/"build.json"
        p.write_new(path,value)
        originals[arm] = p.pin(path)
        p.write_new(root/(arm+"-build.json"),{"wrong":"legacy role copy must not replace canonical build"})
    failure = {"kind":"MATCHED_WHOLETURN_EXECUTE_PREFLIGHT_FAILURE","status":"PRE_RUN_SCHEDULE_FAILURE",
        "stage":"recheck_build","arm":"baseline","build_recheck_stage":"installed_native",
        "error":{"type":"Refused","reason":"fixture diagnostic"},"pin_failure":{"fixture":True},
        "child_launch_attempted":False}
    p.write_new(root/"metadata/execute-preflight-failure.json",failure)
    original = records.optional_json
    def no_legacy_copy(path,*args):
        assert Path(path) not in (root/"baseline-build.json",root/"candidate-build.json")
        return original(path,*args)
    monkeypatch.setattr(records,"optional_json",no_legacy_copy)
    selected = records.selected_records(ctrl,root,"failure")
    summary = p.strict_json(selected["summary.json"])
    assert summary["owner"] is None and summary["status"] == "NO_COMPLETE_OWNER_RECORD"
    assert summary["preflight_failure"] == failure
    assert summary["preflight_failure_original"] == p.pin(root/"metadata/execute-preflight-failure.json",65536)
    for arm in ("baseline","candidate"):
        assert summary["builds"][arm]["original"] == originals[arm]
        assert summary["builds"][arm]["data"]["arm"] == arm
        assert summary["builds"][arm]["sealed_source"] == {"count":7,"digest":"a"*64}
    assert not summary["raw_upload_allowed"] and not summary["child_body_reads_allowed"]
    assert all(row["role_data"] is None for row in p.strict_json(selected["roles.json"]))
    assert summary["scientific_qualification"] is summary["performance_qualification"] is None


def test_file_integrity_current_raw_refs_preserve_policy_and_unrelated_drift():
    import hashlib
    import yaml
    tests_body = (ROOT/".github/workflows/tests.yml").read_bytes()
    tests_text = _legacy_workflow_before_cache_identity_pilot(".github/workflows/tests.yml", tests_body)
    tests = yaml.load(tests_text,Loader=yaml.BaseLoader)
    current = "lead/wholeturn-file-integrity-tests-20261030"
    semantic_ref = "lead/wholeturn-file-integrity-semantics-20261030"
    inert = "lead/wholeturn-file-integrity-source-20261030"
    run = "lead/wholeturn-staging-run002-20261030"
    branches = tests["on"]["push"]["branches"]
    assert branches.count(current) == branches.count("lead/wholeturn-staging-tests-20261030") == 1
    assert not {semantic_ref,inert,run} & set(branches)
    assert tests["permissions"] == {"contents":"read"}
    assert tests["on"]["pull_request"] == tests["on"]["workflow_dispatch"] == ""
    header = tests_text.split("jobs:\n",1)[0]
    historical = (ROOT/"tests/fixtures/ci/standard-tests-cbf6e368.yml").read_text().split("jobs:\n",1)[0]
    added = ", lead/wholeturn-staging-tests-20261030, "+current
    assert header.count(added) == 1 and header.replace(added,"",1) == historical
    drift = header.replace("contents: read","contents: write",1)
    assert drift != header and drift.replace(added,"",1) != historical
    semantic_body = (ROOT/".github/workflows/workflow-semantics.yml").read_bytes()
    semantic_text = _legacy_workflow_before_cache_identity_pilot(".github/workflows/workflow-semantics.yml", semantic_body)
    semantic = yaml.load(semantic_text,Loader=yaml.BaseLoader)
    assert semantic["on"]["push"]["branches"][-1] == semantic_ref
    assert semantic["permissions"] == {"contents":"read"} and "pull_request" in semantic["on"] and "workflow_dispatch" in semantic["on"]
    selector = ", "+semantic_ref
    guard = " || github.ref == 'refs/heads/"+semantic_ref+"'"
    def inverse(value):
        assert value.count(selector) == value.count(guard) == 1
        return value.replace(selector,"",1).replace(guard,"",1)
    assert hashlib.sha256(inverse(semantic_text).encode()).hexdigest() == "5077ae50703cebb1ebb7e1d65a2292c4930586fbf18493c7e1df4a944df73dc0"
    drift = semantic_text.replace("timeout-minutes: 5","timeout-minutes: 6",1)
    assert drift != semantic_text
    assert hashlib.sha256(inverse(drift).encode()).hexdigest() != "5077ae50703cebb1ebb7e1d65a2292c4930586fbf18493c7e1df4a944df73dc0"
    benchmark = yaml.load((ROOT/".github/workflows/matched-wholeturn.yml").read_text(),Loader=yaml.BaseLoader)
    assert benchmark["on"]["push"]["branches"] == [run]
    assert benchmark["jobs"]["wholeturn"]["if"] == "github.ref == 'refs/heads/"+run+"'"
    assert benchmark["permissions"] == {"contents":"read","actions":"read"}
    # Wrong selectors/guard location and unrelated changes cannot be projected.
    added = b", lead/wholeturn-cache-identity-pilot-tests-20261030"
    guard = b" || github.ref == 'refs/heads/lead/wholeturn-cache-identity-pilot-semantics-20261030'"
    for path, changed in [
        (".github/workflows/tests.yml", tests_body.replace(added, b", lead/wrong-tests", 1)),
        (".github/workflows/tests.yml", tests_body.replace(added, b"", 1) + b"#" + added + b"\n"),
        (".github/workflows/tests.yml", tests_body.replace(b"contents: read", b"contents: write", 1)),
        (".github/workflows/workflow-semantics.yml", semantic_body.replace(guard, b"", 1)),
        (".github/workflows/workflow-semantics.yml", semantic_body.replace(guard, b"", 1) + b"#" + guard + b"\n"),
        (".github/workflows/workflow-semantics.yml", semantic_body.replace(guard, guard + guard, 1)),
        (".github/workflows/wholeturn-cache-identity-pilot.yml", (ROOT/".github/workflows/wholeturn-cache-identity-pilot.yml").read_bytes() + b"# drift\n"),
    ]:
        with pytest.raises(AssertionError):
            _legacy_workflow_before_cache_identity_pilot(path, changed)

