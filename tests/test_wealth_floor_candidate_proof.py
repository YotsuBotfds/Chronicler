"""Pure candidate-proof admission contracts; no native, worlds or real probes.

The staged build fixture deliberately stubs the separately qualified paired-
build classifier and wheel inspector. It tests this reader's file/producer
bindings, not compiler, wheel-format or scientific qualification.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import xml.etree.ElementTree as ET

import pytest
from scripts import wealth_floor_candidate_proof as P


pytestmark = pytest.mark.skipif(os.name != "posix", reason="candidate proof requires safe POSIX descriptors")
NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)
BASELINE_NATIVE = "a" * 64
CANDIDATE_NATIVE = "b" * 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(raw):
    return dict(bytes=len(raw), sha256=sha(raw))


def write(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def write_json(root, name, value):
    return write(root, name, P.B.canonical_bytes(value))


@pytest.fixture
def staged_build(tmp_path, monkeypatch):
    """Tiny, fully hash-linked files; paired-native algorithms are stubbed."""
    staged = tmp_path / "staged"
    root = staged / "fixture-build"
    root.mkdir(parents=True)
    context = dict(fixture_only="common recorded context")
    context_hash = P.B.digest(context)
    loader = dict(fixture_only="selected Python loader")
    payloads = {}
    phases = {}
    wheel_facts = {}
    for role, native in (("baseline", BASELINE_NATIVE), ("candidate", CANDIDATE_NATIVE)):
        snapshot = P.B.canonical_bytes(dict(fixture_only=role))
        probe = dict(fixture_only=role, native_sha256=native)
        for name, raw in (("source-before.json", snapshot), ("source-after.json", snapshot),
                          ("context.json", P.B.canonical_bytes(context)),
                          ("probe.json", P.B.canonical_bytes(probe)),
                          ("trace-summary.json", P.B.canonical_bytes(dict(fixture_only="trace")))):
            payloads[role + "/" + name] = raw
        wheel = (role + " synthetic wheel bytes; never installed").encode()
        facts = dict(filename=P.B.WHEEL_NAME, bytes=len(wheel), sha256=sha(wheel),
                     native_sha256=native, native_member=P.B.NATIVE_MEMBER)
        wheel_facts[wheel] = facts
        payloads[f"wheels/{role}/{P.B.WHEEL_NAME}"] = wheel
        phases[role] = dict(source_before_sha256=sha(snapshot), source_after_sha256=sha(snapshot),
                            context=context, probe=probe, wheel=facts)
    for name in ("source-control-before.json", "source-control-after.json", "cache-retirement.json"):
        payloads[name] = P.B.canonical_bytes(dict(fixture_only=name))
    payloads["candidate/regression-loader.json"] = P.B.canonical_bytes(loader)
    core = dict(schema_version=1, kind="wealth-floor-native-build-bridge", status="build_complete_pending_job",
                classification="fresh_baseline_required", historical_reuse_eligible=False,
                candidate_worlds_admitted=False, baseline_context_sha256=context_hash,
                candidate_context_sha256=context_hash)
    producer = dict(control_sha="c" * 40, run_id="7", run_attempt="1", job_key="paired-native-build")
    manifest = dict(**core, phases=phases, measured=dict(fixture_only=True), producer=producer,
                    publication_status="provisional_until_matching_completion_seal", regression_loader=loader)
    manifest_raw = P.B.canonical_bytes(manifest)
    for name, raw in payloads.items():
        write(root, name, raw)
    write(root, "build-manifest.json", manifest_raw)
    raw_inventory = dict(files={n:record(b) for n,b in payloads.items()}, file_count=len(payloads),
                         total_bytes=sum(map(len, payloads.values())))
    write_json(root, "raw-inventory.json", raw_inventory)
    light = {}
    for name in P.C.LIGHT_NAMES:
        raw = (root / name).read_bytes()
        light[name] = record(raw)
        write(root, "light/" + name, raw)
    write_json(root, "light/index.json", dict(files=light))
    sealed = {n:record((root/n).read_bytes()) for n in ("build-manifest.json", "raw-inventory.json", "light/index.json")}
    completion = dict(schema_version=1, kind="wealth-floor-native-build-completion", publication_complete=True, files=sealed)
    write_json(root, "completion.json", completion)
    pins = dict(control_sha=producer["control_sha"], run_id=7, job_id=8, attempt=1, artifact_id=9, artifact_bytes=4096,
        artifact_sha256="d"*64, artifact_expires_at="2026-11-28T00:00:00Z", root_prefix="fixture-build",
        completion_sha256=sha((root/"completion.json").read_bytes()), manifest_sha256=sha(manifest_raw),
        inventory_sha256=sealed["raw-inventory.json"]["sha256"], light_index_sha256=sealed["light/index.json"]["sha256"],
        baseline_wheel_sha256=phases["baseline"]["wheel"]["sha256"], candidate_wheel_sha256=phases["candidate"]["wheel"]["sha256"],
        baseline_native_sha256=BASELINE_NATIVE, candidate_native_sha256=CANDIDATE_NATIVE, context_sha256=context_hash)
    metadata = dict(
        run=dict(id=7,run_attempt=1,head_sha=producer["control_sha"],head_branch=P.B.ACTIVE_BRANCH,path=P.B.WORKFLOW_PATH,
                 status="completed",conclusion="success",repository=dict(full_name=P.REPOSITORY)),
        jobs=dict(jobs=[dict(id=8,run_id=7,head_sha=producer["control_sha"],status="completed",conclusion="success")]),
        artifact=dict(id=9,size_in_bytes=4096,digest="sha256:"+pins["artifact_sha256"],expired=False,
                      expires_at=pins["artifact_expires_at"],name="wealth-native-raw-7-1",
                      workflow_run=dict(id=7,head_sha=producer["control_sha"])))
    monkeypatch.setattr(P, "REVIEWED_BUILD", MappingProxyType(pins))
    monkeypatch.setattr(P.B, "classify_pair", lambda *_args:deepcopy(core))
    monkeypatch.setattr(P.B, "inspect_wheel", lambda raw,name:deepcopy(wheel_facts[raw]))
    return SimpleNamespace(staged=staged, root=root, pins=pins, metadata=metadata, manifest=manifest, core=core)


def test_default_is_inert_without_registration_or_execution(monkeypatch, capsys):
    def forbidden(*_a, **_k): pytest.fail("inert default entered proof IO")
    monkeypatch.setattr(P, "registration", forbidden)
    monkeypatch.setattr(P, "proof", forbidden)
    monkeypatch.setattr(P, "child", forbidden)
    assert P.main([]) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "inactive" and row["candidate_worlds_admitted"] is False


@pytest.mark.parametrize("entry", ["admit", "proof", "cli-registration", "cli-child", "cli-metadata"])
def test_pending_registration_refuses_before_path_environment_or_artifact_io(monkeypatch, entry):
    monkeypatch.setattr(P, "REVIEWED_BUILD", MappingProxyType(dict.fromkeys(P.REVIEWED_BUILD)))
    def forbidden(*_a, **_k):pytest.fail("pending registration accessed inputs")
    monkeypatch.setattr(P, "inventory", forbidden)
    monkeypatch.setattr(P, "validate_publication", forbidden)
    monkeypatch.setattr(P, "source_bindings", forbidden)
    monkeypatch.setattr(P, "hosted_vm_precondition", forbidden)
    monkeypatch.setattr(P.C, "make_supervisor", forbidden)
    with pytest.raises(P.ProofRefused, match="pending"):
        if entry == "admit":P.admit_build(object(), object(), now=NOW)
        elif entry == "proof":P.proof(SimpleNamespace())
        elif entry=="cli-registration":P.main(["--registration"])
        elif entry=="cli-child":P.main(["--child","negative"])
        else:P.main(["--validate-publication"])


@pytest.mark.parametrize("field,value", [
    ("run_id",True),("job_id","8"),("attempt",0),("artifact_id",-1),("artifact_bytes",P.MAX_INPUT_BYTES+1),
    ("control_sha","C"*40),("candidate_native_sha256","nope"),
    ("candidate_native_sha256",BASELINE_NATIVE),("root_prefix","../escape"),("root_prefix","/absolute"),
    ("root_prefix","back\\slash"),("artifact_expires_at","2026-11-28T00:00:00+00:00"),
    ("artifact_expires_at","2026-99-99T00:00:00Z")])
def test_registration_facts_are_strict(staged_build, monkeypatch, field, value):
    pins = dict(staged_build.pins);pins[field]=value
    monkeypatch.setattr(P, "REVIEWED_BUILD", MappingProxyType(pins))
    with pytest.raises(P.ProofRefused):P.registration()


def test_complete_staged_pair_admits_content_without_claiming_a_build(staged_build):
    checks=[]
    build=P.admit_build(staged_build.staged, staged_build.metadata, now=NOW, check=lambda:checks.append(True))
    assert type(build) is P.AdmittedBuild and build.root==staged_build.root and checks
    assert P.parse(build.manifest_bytes)["classification"]=="fresh_baseline_required"
    P.recheck_build(build)


@pytest.mark.parametrize("fault", ["run-in-progress","run-failed","wrong-run-attempt","wrong-source", "wrong-job",
    "job-in-progress","job-failed","job-bool-id","wrong-artifact","wrapper-size","wrapper-digest","expired",
    "wrong-expiry","wrong-artifact-origin","float-artifact-origin","unknown-metadata"])
def test_completed_producer_and_exact_publication_are_required_before_content(staged_build, monkeypatch, fault):
    m=deepcopy(staged_build.metadata)
    if fault=="run-in-progress":m["run"]["status"]="in_progress"
    elif fault=="run-failed":m["run"]["conclusion"]="failure"
    elif fault=="wrong-run-attempt":m["run"]["run_attempt"]=2
    elif fault=="wrong-source":m["run"]["head_sha"]="0"*40
    elif fault=="wrong-job":m["jobs"]["jobs"][0]["id"]=10
    elif fault=="job-in-progress":m["jobs"]["jobs"][0]["status"]="in_progress"
    elif fault=="job-failed":m["jobs"]["jobs"][0]["conclusion"]="failure"
    elif fault=="job-bool-id":m["jobs"]["jobs"][0]["id"]=True
    elif fault=="wrong-artifact":m["artifact"]["id"]=10
    elif fault=="wrapper-size":m["artifact"]["size_in_bytes"]=1
    elif fault=="wrapper-digest":m["artifact"]["digest"]="sha256:"+"0"*64
    elif fault=="expired":m["artifact"]["expired"]=True
    elif fault=="wrong-expiry":m["artifact"]["expires_at"]="2030-01-01T00:00:00Z"
    elif fault=="wrong-artifact-origin":m["artifact"]["workflow_run"]["id"]=10
    elif fault=="float-artifact-origin":m["artifact"]["workflow_run"]["id"]=7.0
    elif fault=="unknown-metadata":m["unexpected"]={}
    monkeypatch.setattr(P,"inventory",lambda *_a,**_k:pytest.fail("invalid publication reached staged content"))
    with pytest.raises(P.ProofRefused):P.admit_build(staged_build.staged,m,now=NOW)


def test_expired_registered_wrapper_refuses(staged_build):
    with pytest.raises(P.ProofRefused, match="expired"):
        P.admit_build(staged_build.staged,staged_build.metadata,now=datetime(2026,12,1,tzinfo=timezone.utc))


@pytest.mark.parametrize("fault", ["changed-payload","missing-payload","extra-payload","completion","manifest","inventory","light-index","empty-tree","symlink","hardlink"])
def test_staged_bytes_set_and_completion_cannot_be_substituted(staged_build, fault):
    root=staged_build.root
    if fault=="changed-payload":(root/"baseline/probe.json").write_bytes(b"tampered")
    elif fault=="missing-payload":(root/"baseline/probe.json").unlink()
    elif fault=="extra-payload":write(root,"extra.txt",b"unexpected")
    elif fault=="completion":(root/"completion.json").write_bytes(b"{}")
    elif fault=="manifest":(root/"build-manifest.json").write_bytes(b"{}")
    elif fault=="inventory":(root/"raw-inventory.json").write_bytes(b"{}")
    elif fault=="light-index":(root/"light/index.json").write_bytes(b"{}")
    elif fault=="empty-tree":(root/"unexpected-empty").mkdir()
    else:
        path=root/"baseline/probe.json";path.unlink()
        if fault=="symlink":path.symlink_to(root/"candidate/probe.json")
        else:os.link(root/"candidate/probe.json",path)
    with pytest.raises((P.ProofRefused,OSError)):
        P.admit_build(staged_build.staged,staged_build.metadata,now=NOW)


def test_recheck_refuses_file_drift_and_ad_hoc_objects(staged_build):
    build=P.admit_build(staged_build.staged,staged_build.metadata,now=NOW)
    with pytest.raises(P.ProofRefused,match="factory"):
        P.recheck_build(dict(root=build.root))
    write(staged_build.root,"baseline/probe.json",b"changed after admission")
    with pytest.raises(P.ProofRefused,match="changed"):P.recheck_build(build)


def test_recheck_cannot_reset_registration(staged_build,monkeypatch):
    build=P.admit_build(staged_build.staged,staged_build.metadata,now=NOW)
    changed=dict(staged_build.pins);changed["job_id"]=9
    monkeypatch.setattr(P,"REVIEWED_BUILD",MappingProxyType(changed))
    with pytest.raises(P.ProofRefused,match="registration drift"):P.recheck_build(build)


def test_inventory_enforces_total_byte_and_file_bounds(tmp_path):
    write(tmp_path,"one",b"12");write(tmp_path,"two",b"34")
    with pytest.raises(P.ProofRefused,match="bounds"):P.inventory(tmp_path,max_bytes=3)
    with pytest.raises(P.ProofRefused):P.inventory(tmp_path,max_files=1)


def junit(*, omitted=(), extra=(), classname="tests.test_run_checkpoint_native", tag=None, suite=None):
    root=ET.Element("testsuites")
    s=ET.SubElement(root,"testsuite",dict(tests="6",failures="0",errors="0",skipped="0",**(suite or {})))
    for name in [n for n in sorted(P.CASE_NAMES) if n not in omitted]+list(extra):
        case=ET.SubElement(s,"testcase",dict(name=name,classname=classname))
        if tag:ET.SubElement(case,tag)
    return ET.tostring(root,encoding="utf-8")


def test_exact_six_native_checkpoint_parents_must_all_pass():
    row=P.checkpoint_junit(junit())
    assert row["passed"]==6 and row["skipped"]==0 and row["physics_ticks"]==126
    assert set(row["cases"])==P.CASE_NAMES


@pytest.mark.parametrize("fault", ["skip","failure","error","missing","duplicate","extra","wrong-class","suite-skips","suite-errors","dtd","invalid"])
def test_junit_cannot_turn_skip_missing_or_unrelated_parents_into_pass(fault):
    first=next(iter(P.CASE_NAMES))
    if fault in ("skip","failure","error"):raw=junit(tag={"skip":"skipped","failure":"failure","error":"error"}[fault])
    elif fault=="missing":raw=junit(omitted=(first,))
    elif fault=="duplicate":raw=junit(omitted=(first,),extra=(sorted(P.CASE_NAMES-{first})[0],))
    elif fault=="extra":raw=junit(extra=("test_unrelated",))
    elif fault=="wrong-class":raw=junit(classname="test_run_checkpoint_native")
    elif fault=="suite-skips":raw=junit().replace(b'skipped="0"',b'skipped="1"')
    elif fault=="suite-errors":raw=junit().replace(b'errors="0"',b'errors="1"')
    elif fault=="dtd":raw=b'<!DOCTYPE testsuites []>'+junit()
    else:raw=b"<testsuites>"
    with pytest.raises(P.ProofRefused):P.checkpoint_junit(raw)


@pytest.fixture
def repeats(tmp_path):
    def create(worldgen="template"):
        root=tmp_path/worldgen;root.mkdir()
        runs=[]
        for suffix in ("a","b"):
            name=f"seed_42_{suffix}/chronicle_bundle.json"
            raw=P.B.canonical_bytes(dict(synthetic_fixture=True,metadata=dict(seed=42,total_turns=200)))
            write(root,name,raw)
            runs.append(dict(seed=42,dir=f"seed_42_{suffix}",bundle=name,total_turns=200,files={name:sha(raw)}))
        manifest=dict(status="complete",seeds=[42,42],turns=200,native=dict(sha256=CANDIDATE_NATIVE),
            simulation=dict(agents="hybrid",turns=200,worldgen="procedural" if worldgen=="procedural" else None,
                            regions=32 if worldgen=="procedural" else None,civs=10 if worldgen=="procedural" else None),runs=runs)
        summary=dict(profile="determinism-hybrid",worldgen=worldgen,gate_status="PASS",gate_exit_code=0,turns=200,ablation_oracles=False)
        report=dict(results=dict(determinism=dict(status="PASS",pairs_checked=1,duplicate_seeds=[42],mismatches=[],reason="bundles_match")))
        write_json(root,"batch_manifest.json",manifest);write_json(root,"run_manifest.json",summary)
        write_json(root,"validate_report_determinism_hybrid.json",report)
        return root,manifest,summary,report
    return create


@pytest.mark.parametrize("worldgen",["template","procedural"])
def test_actual_repeat_file_contract_preserves_duplicate_seed_in_distinct_files(repeats,worldgen):
    root,*_=repeats(worldgen);checks=[]
    row=P.determinism_result(root,worldgen,CANDIDATE_NATIVE,lambda:checks.append(True))
    assert row["status"]=="PASS" and row["seed"]==42 and row["independent_runs"]==2 and checks
    assert row["physics_ticks"]==400 and len(row["bundles"])==2
    # Equal content remains valid; their physical files must be independent.
    assert row["bundles"][0]["sha256"]==row["bundles"][1]["sha256"]


@pytest.mark.parametrize("fault",["wrong-seeds","single-run","same-run-dir","wrong-run-seed","short-run","bool-turns","wrong-native",
    "skip-oracle","zero-pairs","wrong-duplicate-seed","oracle-mismatch","wrong-oracle-reason", "wrong-mode","wrong-world",
    "side-effects","failed-gate","changed-bundle","hardlink","symlink"])
def test_repeat_proof_refuses_false_cohorts_and_physical_aliases(repeats,fault):
    root,m,s,r=repeats()
    if fault=="wrong-seeds":m["seeds"]=[42,43]
    elif fault=="single-run":m["runs"]=m["runs"][:1]
    elif fault=="same-run-dir":m["runs"][1]=deepcopy(m["runs"][0])
    elif fault=="wrong-run-seed":m["runs"][1]["seed"]=43
    elif fault=="short-run":m["runs"][1]["total_turns"]=20
    elif fault=="bool-turns":m["turns"]=True
    elif fault=="wrong-native":m["native"]["sha256"]=BASELINE_NATIVE
    elif fault=="skip-oracle":r["results"]["determinism"]["status"]="SKIP"
    elif fault=="zero-pairs":r["results"]["determinism"]["pairs_checked"]=0
    elif fault=="wrong-duplicate-seed":r["results"]["determinism"]["duplicate_seeds"]=[43]
    elif fault=="oracle-mismatch":r["results"]["determinism"]["mismatches"]=[{"synthetic_difference":True}]
    elif fault=="wrong-oracle-reason":r["results"]["determinism"]["reason"]="no_duplicate_seeds"
    elif fault=="wrong-mode":m["simulation"]["agents"]="off"
    elif fault=="wrong-world":s["worldgen"]="procedural"
    elif fault=="side-effects":s["ablation_oracles"]=True
    elif fault=="failed-gate":s["gate_status"]="FAIL"
    elif fault=="changed-bundle":write(root,"seed_42_b/chronicle_bundle.json",b"mutated after manifest")
    else:
        a=root/"seed_42_a/chronicle_bundle.json";b=root/"seed_42_b/chronicle_bundle.json";b.unlink()
        if fault=="hardlink":os.link(a,b)
        else:b.symlink_to(a)
    write_json(root,"batch_manifest.json",m);write_json(root,"run_manifest.json",s);write_json(root,"validate_report_determinism_hybrid.json",r)
    with pytest.raises((P.ProofRefused,OSError)):P.determinism_result(root,"template",CANDIDATE_NATIVE,lambda:None)


def test_procedural_proof_requires_exact_registered_dimensions(repeats):
    root,m,*_=repeats("procedural");m["simulation"]["regions"]=8
    write_json(root,"batch_manifest.json",m)
    with pytest.raises(P.ProofRefused,match="dimensions"):P.determinism_result(root,"procedural",CANDIDATE_NATIVE,lambda:None)


def cross_native():
    return dict(status="PASS",checkpoint_sha256="e"*64,candidate_native_sha256=CANDIDATE_NATIVE,
        observed_native_sha256=BASELINE_NATIVE,exception="CheckpointIncompatible",mismatch_fields=["native extension"],
        native_restore_calls=0,python_restore_calls=0,allow_mismatch=False,source_sha=P.B.CANDIDATE_SOURCE)


def test_cross_native_only_proves_native_identity_refusal_before_restore():
    value=cross_native()
    assert P.negative_result(value,"e"*64,CANDIDATE_NATIVE,BASELINE_NATIVE)==value


@pytest.mark.parametrize("field,value",[("mismatch_fields",["native extension","source package digest"]),
    ("mismatch_fields",["environment python"]),("native_restore_calls",1),("native_restore_calls",False),
    ("python_restore_calls",1),("allow_mismatch",True),("exception","CheckpointError"),("status","SKIP"),
    ("checkpoint_sha256","0"*64),("observed_native_sha256",CANDIDATE_NATIVE),("source_sha",P.B.BASELINE_SOURCE)])
def test_cross_native_unrelated_or_post_restore_failures_are_not_accepted(field,value):
    row=cross_native();row[field]=value
    with pytest.raises(P.ProofRefused):P.negative_result(row,"e"*64,CANDIDATE_NATIVE,BASELINE_NATIVE)


def test_kernel_commands_preserve_all_six_parents_and_full_registered_profiles(tmp_path):
    python=tmp_path/"python";source=tmp_path/"source";out=tmp_path/"output"
    checkpoint=P.kernel_command(python,source,"checkpoint",out)
    assert "tests/test_run_checkpoint_native.py" in checkpoint and "-k" not in checkpoint
    assert checkpoint[checkpoint.index("-m")+1]=="pytest" and "--junitxml="+str(out/"checkpoint.xml") in checkpoint
    for worldgen in ("template","procedural"):
        command=P.kernel_command(python,source,worldgen,out)
        assert command[command.index("--profile")+1]=="determinism-hybrid"
        assert command[command.index("--worldgen")+1]==worldgen
        assert "--turns" not in command and "--seeds" not in command


@pytest.mark.parametrize("absolute",[False,True])
def test_pytest_current_alias_to_last_shared_prefix_directory_keeps_every_physical_file(tmp_path,absolute):
    scratch=tmp_path/"scratch";scratch.mkdir();retained=tmp_path/"retained"
    prefix="test_resume_identity_in_each_m"
    for number in range(4):write(scratch,prefix+str(number)+"/c6.ckpt",b"synthetic checkpoint bytes "+str(number).encode())
    war="test_war_roster_marker_is_rebo";write(scratch,war+"0/c30.ckpt",b"synthetic war checkpoint")
    target=scratch/(prefix+"3")
    (scratch/(prefix+"current")).symlink_to(target if absolute else target.name,target_is_directory=True)
    checks=[];row=P.retain_pytest_outputs(scratch,retained,lambda:checks.append(True))
    assert row["physical_files"]==5 and checks
    assert row["pytest_scratch_aliases"]==[dict(path=prefix+"current",target=str(target) if absolute else target.name)]
    assert not (retained/(prefix+"current")).exists()
    for number in range(4):assert (retained/(prefix+str(number))/"c6.ckpt").read_bytes()==(scratch/(prefix+str(number))/"c6.ckpt").read_bytes()


@pytest.mark.parametrize("fault",["wrong-prefix","outside","number-four","file-link"])
def test_pytest_aliases_cannot_add_outside_or_unregistered_scientific_outputs(tmp_path,fault):
    scratch=tmp_path/"scratch";scratch.mkdir();retained=tmp_path/"retained"
    prefix="test_resume_identity_in_each_m";write(scratch,prefix+"3/c6.ckpt",b"retained physical fixture")
    alias=scratch/(prefix+"current")
    if fault=="wrong-prefix":
        write(scratch,"unregistered0/payload",b"fixture");alias=scratch/"unregisteredcurrent";target=scratch/"unregistered0"
    elif fault=="outside":
        target=tmp_path/(prefix+"3");target.mkdir();(target/"payload").write_bytes(b"outside fixture")
    elif fault=="number-four":
        write(scratch,prefix+"4/payload",b"unregistered repeat");target=scratch/(prefix+"4")
    else:
        (scratch/"foreign.ckpt").symlink_to(scratch/(prefix+"3/c6.ckpt"))
        target=None
    if target is not None:alias.symlink_to(target,target_is_directory=True)
    with pytest.raises((P.ProofRefused,OSError)):P.retain_pytest_outputs(scratch,retained,lambda:None)


def test_workflow_contract_accepts_dormant_and_identical_known_active_bytes():
    root=Path(__file__).parents[1];raw=(root/P.TEMPLATE_PATH).read_bytes();text=raw.decode()
    P.workflow_contract(raw)
    P.workflow_contract(raw,active_text=raw)
    active=root/P.WORKFLOW_PATH
    if active.exists():P.workflow_contract(raw,active_text=active.read_bytes())
    assert "branches: ["+P.ACTIVE_BRANCH+"]" in text and "paths: ["+P.WORKFLOW_PATH+"]" in text
    assert P.B.CANDIDATE_SOURCE in text
    assert text.index("--registration")<text.index("Check out exact candidate Python source")
    assert text.index("--validate-publication")<text.index("Stage exact completed build payload")


@pytest.mark.parametrize("fault",["candidate-source","branch","path","body","different-active"])
def test_workflow_changes_cannot_silently_schedule_or_change_proof(fault):
    text=(Path(__file__).parents[1]/P.TEMPLATE_PATH).read_text();active=None
    if fault=="candidate-source":text=text.replace(P.B.CANDIDATE_SOURCE,P.B.BASELINE_SOURCE)
    elif fault=="branch":text=text.replace(P.ACTIVE_BRANCH,"main")
    elif fault=="path":text=text.replace(P.WORKFLOW_PATH,".github/workflows/other.yml")
    elif fault=="body":text+="\n# changed registered body\n"
    else:active=text+"\n# different active body\n"
    with pytest.raises(P.ProofRefused):P.workflow_contract(text.encode(),active_text=None if active is None else active.encode())


@pytest.fixture
def preflight(tmp_path,monkeypatch):
    for key,value in (("GITHUB_SHA","c"*40),("GITHUB_RUN_ID","7"),("GITHUB_RUN_ATTEMPT","1"),
                      ("GITHUB_REF","refs/heads/"+P.ACTIVE_BRANCH),("RUNNER_TEMP",str(tmp_path))):
        monkeypatch.setenv(key,value)
    row=dict(started_monotonic=100.0,control_sha="c"*40,run_id="7",attempt="1",wall_limit_seconds=180)
    write_json(tmp_path,"wealth-proof-preflight.json",row)
    return tmp_path,row


@pytest.mark.parametrize("elapsed",[0.0,180.0])
def test_staging_clock_admits_only_the_closed_registered_window(preflight,elapsed):
    root,_=preflight
    row=P.staging_observation(root,clock=lambda:100.0+elapsed)
    assert row["elapsed_wall_seconds"]==elapsed and row["wall_limit_seconds"]==180


@pytest.mark.parametrize("fault",["late","backwards","bool-start","zero-start","nan-start","wrong-control","wrong-run",
    "wrong-attempt","bool-limit","extra-field","missing-field"])
def test_staging_clock_and_current_producer_facts_cannot_be_fabricated(preflight,fault):
    root,row=preflight;clock=lambda:110.0
    if fault=="late":clock=lambda:281.0
    elif fault=="backwards":clock=lambda:99.0
    elif fault=="bool-start":row["started_monotonic"]=True
    elif fault=="zero-start":row["started_monotonic"]=0
    elif fault=="nan-start":row["started_monotonic"]=float("nan")
    elif fault=="wrong-control":row["control_sha"]="0"*40
    elif fault=="wrong-run":row["run_id"]="8"
    elif fault=="wrong-attempt":row["attempt"]="2"
    elif fault=="bool-limit":row["wall_limit_seconds"]=True
    elif fault=="extra-field":row["unregistered"]=True
    elif fault=="missing-field":row.pop("attempt")
    write(root,"wealth-proof-preflight.json",json.dumps(row).encode())
    with pytest.raises(P.ProofRefused):P.staging_observation(root,clock=clock)


@pytest.mark.parametrize("field,environment,value",[("control_sha","GITHUB_SHA",None),("run_id","GITHUB_RUN_ID",None),
    ("attempt","GITHUB_RUN_ATTEMPT",None),("control_sha","GITHUB_SHA","garbage"),("run_id","GITHUB_RUN_ID","0"),
    ("attempt","GITHUB_RUN_ATTEMPT","not-a-number"),("attempt","GITHUB_RUN_ATTEMPT","2")])
def test_staging_marker_never_binds_missing_or_unregistered_current_identity(preflight,monkeypatch,field,environment,value):
    root,row=preflight;row[field]=value
    if value is None:monkeypatch.delenv(environment)
    else:monkeypatch.setenv(environment,value)
    write_json(root,"wealth-proof-preflight.json",row)
    monkeypatch.setattr(P,"read_json",lambda *_a,**_k:pytest.fail("invalid current identity read marker"))
    with pytest.raises(P.ProofRefused):P.staging_observation(root,clock=lambda:110.0)


def test_registration_marker_is_created_after_injected_deployment_and_ram_admission(staged_build,preflight,monkeypatch):
    import wealth_floor_build_resources as resources
    root,_=preflight;marker=root/"wealth-proof-preflight.json";marker.unlink();events=[]
    output=root/"github-output";monkeypatch.setenv("GITHUB_OUTPUT",str(output))
    monkeypatch.setattr(P.platform,"python_version",lambda:P.B.PYTHON_VERSION)
    monkeypatch.setattr(P.time,"monotonic",lambda:123.0)
    monkeypatch.setattr(P,"hosted_vm_precondition",lambda:events.append("deployment") or dict(fixture=True))
    monkeypatch.setattr(P.shutil,"disk_usage",lambda path:events.append("disk") or SimpleNamespace(free=12*1024**3))
    monkeypatch.setattr(resources,"memory_admission",lambda:events.append("memory") or dict(available_bytes=2*1024**3))
    def written(path,value):
        events.append("marker");write_json(path.parent,path.name,value)
    monkeypatch.setattr(P.C,"write_json",written)
    assert P.main(["--registration"])==0
    assert events==["deployment","disk","memory","marker"]
    marker_row=json.loads(marker.read_text())
    assert marker_row==dict(started_monotonic=123.0,control_sha="c"*40,run_id="7",attempt="1",wall_limit_seconds=180)
    assert output.read_text()=="run_id=7\nartifact_id=9\n"


@pytest.mark.parametrize("failure",["deployment","disk","memory"])
def test_failed_registration_never_writes_a_preflight_marker(staged_build,preflight,monkeypatch,failure):
    import wealth_floor_build_resources as resources
    root,_=preflight;(root/"wealth-proof-preflight.json").unlink()
    monkeypatch.setattr(P.platform,"python_version",lambda:P.B.PYTHON_VERSION)
    def deploy():
        if failure=="deployment":raise ValueError("injected deployment refusal")
        return dict(fixture=True)
    monkeypatch.setattr(P,"hosted_vm_precondition",deploy)
    monkeypatch.setattr(P.shutil,"disk_usage",lambda path:SimpleNamespace(free=(12*1024**3-1 if failure=="disk" else 12*1024**3)))
    monkeypatch.setattr(resources,"memory_admission",lambda:dict(available_bytes=(2*1024**3-1 if failure=="memory" else 2*1024**3)))
    monkeypatch.setattr(P.C,"write_json",lambda *_a,**_k:pytest.fail("failed preflight wrote marker"))
    with pytest.raises((P.ProofRefused,ValueError)):P.main(["--registration"])
    assert not (root/"wealth-proof-preflight.json").exists()


def test_metadata_cli_validates_registration_branch_marker_and_publication_before_staging(staged_build,preflight,monkeypatch):
    root,_=preflight;events=[];observed=P.staging_observation;validate=P.validate_publication
    write_json(root,"wealth-build-publication.json",staged_build.metadata)
    def marker(path):
        events.append("marker");return observed(path,clock=lambda:110.0)
    def publication(metadata,pins,*,now):
        events.append("publication");return validate(metadata,pins,now=NOW)
    monkeypatch.setattr(P,"staging_observation",marker);monkeypatch.setattr(P,"validate_publication",publication)
    monkeypatch.setattr(P,"hosted_vm_precondition",lambda:pytest.fail("metadata CLI probed host"))
    monkeypatch.setattr(P,"inventory",lambda *_a,**_k:pytest.fail("metadata CLI staged payloads"))
    assert P.main(["--validate-publication"])==0
    assert events==["marker","publication"]


@pytest.mark.parametrize("fault",["branch","marker","publication"])
def test_metadata_cli_refuses_before_staging_on_preflight_or_origin_failure(staged_build,preflight,monkeypatch,fault):
    root,_=preflight;metadata=deepcopy(staged_build.metadata);original=P.staging_observation
    if fault=="branch":monkeypatch.setenv("GITHUB_REF","refs/heads/main")
    elif fault=="marker":(root/"wealth-proof-preflight.json").unlink()
    elif fault=="publication":metadata["run"]["status"]="in_progress"
    write_json(root,"wealth-build-publication.json",metadata)
    monkeypatch.setattr(P,"staging_observation",lambda path:original(path,clock=lambda:110.0))
    monkeypatch.setattr(P,"inventory",lambda *_a,**_k:pytest.fail("refused metadata reached payloads"))
    with pytest.raises((P.ProofRefused,OSError)):P.main(["--validate-publication"])


def test_authority_completion_counts_its_own_file_within_the_32_file_limit():
    files={f"receipt-{number}.json":dict(bytes=0,sha256="a"*64) for number in range(31)}
    completion=P.authority_completion(files)
    assert completion["publication_complete"] is True and completion["candidate_worlds_admitted"] is False
    assert len(completion["files"])+1==32
    files["one-too-many.json"]=dict(bytes=0,sha256="b"*64)
    with pytest.raises(P.ProofRefused,match="include completion"):P.authority_completion(files)


def test_authority_byte_boundary_includes_canonical_completion_without_allocating_payloads():
    limit=8*P.B.MIB
    files={"synthetic-payload.bin":dict(bytes=limit-4096,sha256="a"*64)}
    initial=P.authority_completion(files)
    spare=limit-(files["synthetic-payload.bin"]["bytes"]+len(P.B.canonical_bytes(initial)))
    assert spare>0
    files["synthetic-payload.bin"]["bytes"]+=spare
    boundary=P.authority_completion(files)
    assert files["synthetic-payload.bin"]["bytes"]+len(P.B.canonical_bytes(boundary))==limit
    files["synthetic-payload.bin"]["bytes"]+=1
    with pytest.raises(P.ProofRefused,match="include completion"):P.authority_completion(files)


@pytest.mark.parametrize("name,row",[("completion.json",dict(bytes=0,sha256="a"*64)),
    ("../escape",dict(bytes=0,sha256="a"*64)),("/absolute",dict(bytes=0,sha256="a"*64)),
    ("valid.json",dict(bytes=True,sha256="a"*64)),("valid.json",dict(bytes=-1,sha256="a"*64)),
    ("valid.json",dict(bytes=0,sha256="not-a-digest")),("valid.json",dict(bytes=0,sha256="a"*64,extra=True))])
def test_authority_completion_refuses_recursive_unsafe_or_untyped_rows(name,row):
    with pytest.raises(P.ProofRefused):P.authority_completion({name:row})


def synthetic_raw_index():
    """Names from a genuine proof layout; no payloads or stage trees allocated."""
    roots={"progress.jsonl","checkpoint.xml","checkpoint-index.json","cross-native.json",
        "control-sources-before.json","control-sources-after.json","control-git-before.json","control-git-after.json",
        "candidate-source-before.json","candidate-source-after.json","candidate-probe.json","baseline-probe.json"}
    nested={"checkpoints/test_resume_identity_in_each_m0/straight/c6.ckpt",
        "template/determinism_hybrid/batch_42/seed_42_a/chronicle_bundle.json",
        "procedural/determinism_hybrid/batch_42/seed_42_b/chronicle_bundle.json",
        "logs/checkpoint-six-native-parents.stdout.log"}
    return {name:dict(bytes=1,sha256="a"*64) for name in roots|nested},roots


def test_raw_upload_workflow_covers_every_indexed_file_and_all_twelve_root_receipts():
    files,roots=synthetic_raw_index()
    assert P.raw_upload_coverage(files)==files
    assert set(P.RAW_ROOT_FILES)==roots and len(roots)==12
    text=(Path(__file__).parents[1]/P.TEMPLATE_PATH).read_text()
    raw_step=text.split("name: wealth-candidate-proof-raw-",1)[1]
    prefix="${{ runner.temp }}/wealth-candidate-proof/"
    uploaded={line.strip()[len(prefix):] for line in raw_step.splitlines() if line.strip().startswith(prefix)}
    directories={"checkpoints/","template/","procedural/","logs/","publication/"}
    assert uploaded==roots|directories
    assert all(name in uploaded or any(name.startswith(directory) for directory in directories) for name in files)


@pytest.mark.parametrize("fault",["missing-root","extra-indexed-root","scratch","recursive-publication"])
def test_raw_upload_coverage_refuses_unpublished_or_excluded_index_entries(fault):
    files,_=synthetic_raw_index()
    if fault=="missing-root":files.pop("control-git-after.json")
    elif fault=="extra-indexed-root":files["unpublished.json"]=dict(bytes=1,sha256="a"*64)
    elif fault=="scratch":files["scratch/test_resume_identity_in_each_m0/c6.ckpt"]=dict(bytes=1,sha256="a"*64)
    else:files["publication/raw-payload-index.json"]=dict(bytes=1,sha256="a"*64)
    with pytest.raises(P.ProofRefused):P.raw_upload_coverage(files)


def test_failure_checkpoint_retention_reports_absent_or_existing_copy_without_qualifying(tmp_path):
    def forbidden():pytest.fail("no new copy should need a budget reset")
    absent=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=forbidden)
    assert absent==dict(status="not_created",failed_producer=True)
    write(tmp_path,"scratch/c6.ckpt",b"original failed output")
    write(tmp_path,"checkpoints/existing.ckpt",b"already retained unqualified")
    original=(tmp_path/"checkpoints/existing.ckpt").read_bytes()
    existing=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=forbidden)
    assert existing==dict(status="existing_copy_preserved_unqualified",failed_producer=True)
    assert (tmp_path/"checkpoints/existing.ckpt").read_bytes()==original


def test_failure_checkpoint_retention_copies_genuine_tiny_files_and_preserves_failed_completion(tmp_path):
    raw=b"synthetic failed-kernel checkpoint; not decoded"
    write(tmp_path,"scratch/test_resume_identity_in_each_m0/c6.ckpt",raw)
    failed=P.B.canonical_bytes(dict(publication_complete=False,status="incomplete"))
    write(tmp_path,"publication/completion.json",failed)
    checks=[]
    result=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=lambda:checks.append(True))
    assert result["status"]=="retained_for_failed_producer" and result["failed_producer"] is True
    assert result["retention"]["physical_files"]==1 and checks
    assert (tmp_path/"checkpoints/test_resume_identity_in_each_m0/c6.ckpt").read_bytes()==raw
    assert (tmp_path/"publication/completion.json").read_bytes()==failed
    assert (tmp_path/"scratch/test_resume_identity_in_each_m0/c6.ckpt").read_bytes()==raw


@pytest.mark.parametrize("cleanup,children",[(False,True),(True,False)])
def test_failure_checkpoint_retention_requires_confirmed_owned_cleanup_before_copy(tmp_path,monkeypatch,cleanup,children):
    write(tmp_path,"scratch/c6.ckpt",b"failed output")
    monkeypatch.setattr(P,"retain_pytest_outputs",lambda *_a,**_k:pytest.fail("unconfirmed cleanup copied outputs"))
    result=P.failure_checkpoint_retention(tmp_path,cleanup_complete=cleanup,children_gone=children,
        check=lambda:pytest.fail("unconfirmed cleanup reset budget"))
    assert result["status"]=="retention_incomplete" and result["failed_producer"] is True
    assert not (tmp_path/"checkpoints").exists()


def test_failure_checkpoint_retention_expired_budget_refuses_before_any_copy(tmp_path):
    write(tmp_path,"scratch/c6.ckpt",b"failed output");calls=[]
    def expired():calls.append(True);raise P.ProofRefused("injected exhausted remaining budget")
    result=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=expired)
    assert result["status"]=="retention_incomplete" and result["failed_producer"] is True and calls==[True]
    assert not (tmp_path/"checkpoints").exists() and (tmp_path/"scratch/c6.ckpt").read_bytes()==b"failed output"


def test_failure_checkpoint_retention_late_budget_failure_keeps_copy_unqualified(tmp_path,monkeypatch):
    write(tmp_path,"scratch/c6.ckpt",b"failed output");done=[];original=P.retain_pytest_outputs
    def copy(*args):
        result=original(*args);done.append(True);return result
    def check():
        if done:raise P.ProofRefused("injected late budget crossing")
    monkeypatch.setattr(P,"retain_pytest_outputs",copy)
    result=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=check)
    assert result["status"]=="retention_incomplete" and result["failed_producer"] is True
    assert (tmp_path/"scratch/c6.ckpt").read_bytes()==(tmp_path/"checkpoints/c6.ckpt").read_bytes()==b"failed output"


@pytest.mark.parametrize("fault",["scratch-symlink","file-hardlink","copy-error"])
def test_failure_checkpoint_retention_never_follows_or_qualifies_unsafe_failed_outputs(tmp_path,monkeypatch,fault):
    if fault=="scratch-symlink":
        target=tmp_path/"outside";target.mkdir();write(target,"c6.ckpt",b"outside synthetic bytes")
        (tmp_path/"scratch").symlink_to(target,target_is_directory=True)
    else:
        write(tmp_path,"scratch/c6.ckpt",b"failed physical bytes")
        if fault=="file-hardlink":os.link(tmp_path/"scratch/c6.ckpt",tmp_path/"scratch/alias.ckpt")
        else:
            def error(*_a,**_k):raise OSError(5,"private dynamic copy error")
            monkeypatch.setattr(P,"retain_pytest_outputs",error)
    result=P.failure_checkpoint_retention(tmp_path,cleanup_complete=True,children_gone=True,check=lambda:None)
    assert result["status"]=="retention_incomplete" and result["failed_producer"] is True
    assert "private" not in json.dumps(result) and "qualification" in result["scope"]
    if fault=="scratch-symlink":
        assert not (tmp_path/"checkpoints").exists() and (target/"c6.ckpt").read_bytes()==b"outside synthetic bytes"


def test_bounded_retention_reader_refuses_excess_metadata_before_file_reads(tmp_path,monkeypatch):
    scratch=tmp_path/"scratch";scratch.mkdir()
    for number in range(3):write(scratch,f"{number}.ckpt",b"tiny")
    monkeypatch.setattr(P,"MAX_OUTPUT_FILES",2)
    monkeypatch.setattr(P.os,"walk",lambda *_a,**_k:pytest.fail("retention used unbounded os.walk"))
    monkeypatch.setattr(P,"regular",lambda *_a,**_k:pytest.fail("excess directory metadata reached payload reads"))
    with pytest.raises(P.ProofRefused,match="entry bound"):
        P.retain_pytest_outputs(scratch,tmp_path/"retained",lambda:None)


def test_workflow_requires_fresh_no_native_control_environment_before_execution():
    text=(Path(__file__).parents[1]/P.TEMPLATE_PATH).read_text()
    preflight=text.split("name: Complete guarded pure preflight in a fresh no-native control env",1)[1].split("- name: Run owned fixed mechanical proof matrix",1)[0]
    assert "wealth-proof-control-env" in preflight and "--frozen --no-install-project" in preflight
    assert "find_spec('chronicler_agents')" in preflight and "distribution('chronicler-agents')" in preflight
    assert "timeout 110s" in preflight and "-p python_oracle_guard" in preflight
    assert "CHRONICLER_OFFLINE_GUARD_REPORT" in preflight and "--junitxml=" in preflight and "tee " in preflight
    assert "wealth-candidate-proof-contracts-" in text and "wealth-proof-contracts/" in text
