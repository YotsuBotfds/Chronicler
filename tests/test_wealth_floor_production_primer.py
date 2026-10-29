"""Pure fixed-primer contracts; fixture bytes never become scientific evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import wealth_floor_production_primer as M

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def runtime():
    return dict(python=M.B.PYTHON_VERSION, logical_cpu_count=2, affinity=[2, 7],
        caps={key: "1" for key in M.THREAD_KEYS})


def metadata():
    pins = M.BOOTSTRAP
    return dict(run=dict(id=pins["run_id"], run_attempt=1, head_sha=pins["control_sha"],
        head_branch=M.P.ACTIVE_BRANCH, path=M.P.WORKFLOW_PATH, repository=dict(full_name=M.P.REPOSITORY),
        status="completed", conclusion="success"),
        jobs=dict(jobs=[dict(id=pins["job_id"], run_id=pins["run_id"], head_sha=pins["control_sha"], status="completed", conclusion="success")]),
        artifact=dict(id=pins["artifact_id"], size_in_bytes=pins["artifact_bytes"], digest="sha256:"+pins["artifact_sha256"],
            expired=False, expires_at=pins["artifact_expires_at"], name="wealth-candidate-proof-light-40824399844-1",
            workflow_run=dict(id=pins["run_id"], head_sha=pins["control_sha"])))


def checkpoint_report():
    worlds = []
    for plan in M.plans():
        rows = []
        for turn in plan["checkpoint_turns"]:
            rows.append(dict(turn=turn, path=f"checkpoints/{plan['worldgen']}/straight/checkpoint_turn_{turn}.ckpt",
                bytes=100, sha256="c"*64, identity_matches=True,
                header=dict(exact=True, seed=42, turn=turn, identity=dict(native=dict(sha256=M.P.REVIEWED_BUILD["candidate_native_sha256"])),
                    run_config=dict(agent_mode="hybrid"), sections=[dict(name="python"), dict(name="native.agent.0")]),
                comparison=dict(status="PASS", expected_files=4, actual_files=4, keys_sha256="d"*64,
                    expected_outputs_sha256="e"*64, actual_outputs_sha256="e"*64, mismatches=[])))
        worlds.append(dict(plan=plan, checkpoints=rows))
    return dict(runtime=runtime(), source_sha=M.B.CANDIDATE_SOURCE, native_sha256=M.P.REVIEWED_BUILD["candidate_native_sha256"],
        worlds=worlds, executions=15, physics_ticks=2297)


def test_registered_schedule_has_all_late_windows_and_exact_work():
    template, procedural = M.plans()
    assert template == dict(worldgen="template", seed=42, turns=422, regions=8, civs=4,
        checkpoint_turns=[101,201,301,401], executions=5, physics_ticks=1106)
    assert procedural == dict(worldgen="procedural", seed=42, turns=282, regions=32, civs=10,
        checkpoint_turns=[101,121,141,161,181,201,221,241,261], executions=10, physics_ticks=1191)
    assert sum(p["executions"] for p in M.plans()) + 4 == 19
    assert sum(p["physics_ticks"] for p in M.plans()) + 800 == 3097
    assert M.plans()[0]["checkpoint_turns"] is not template["checkpoint_turns"]


@pytest.mark.parametrize("worldgen", ["template", "procedural"])
def test_repeat_is_genuine_registered_profile_with_explicit_requested_parallel(worldgen):
    command = M.repeat_command("PY", Path("SOURCE"), worldgen, Path("OUTPUT"))
    assert command == ["PY", "-B", "SOURCE/scripts/m53b_run_validation.py", "--profile", "determinism-hybrid",
        "--worldgen", worldgen, "--output-root", "OUTPUT/"+worldgen, "--parallel", "2"]
    assert "serial scientific subprocesses" in M.REPEAT_EXECUTION_SCOPE
    assert "not concurrent-worker coverage" in M.REPEAT_EXECUTION_SCOPE


def test_runtime_accepts_actual_two_cpu_observation():
    assert M.validate_runtime(runtime()) == runtime()


def test_runtime_observation_includes_and_enforces_veclib_cap():
    assert "VECLIB_MAXIMUM_THREADS" in M.THREAD_KEYS
    observation=runtime(); observation["caps"]["VECLIB_MAXIMUM_THREADS"]="2"
    with pytest.raises(M.P.ProofRefused, match="thread caps1"):
        M.validate_runtime(observation)


@pytest.mark.parametrize("key,value", [("python", "3.13.5"), ("logical_cpu_count", 4), ("logical_cpu_count", True),
    ("affinity", [0,1,2,3]), ("affinity", [1]), ("affinity", [1,1]), ("affinity", [1,0]),
    ("affinity", [False,1]), ("affinity", [-1,0]), ("caps", {}), ("caps", {"RAYON_NUM_THREADS":"2"})])
def test_runtime_refuses_wrong_affinity_logical_count_or_caps(key, value):
    observation = runtime(); observation[key] = value
    with pytest.raises(M.P.ProofRefused):
        M.validate_runtime(observation)


def test_bootstrap_official_origin_is_fresh_and_closed():
    M.validate_bootstrap_publication(metadata(), now=NOW)


@pytest.mark.parametrize("section,key,value", [
    ("run", "head_sha", "0"*40), ("run", "head_branch", "main"), ("run", "run_attempt", 2),
    ("run", "id", True), ("run", "conclusion", "failure"), ("run", "path", "wrong.yml"),
    ("artifact", "id", 1), ("artifact", "digest", "sha256:"+"0"*64), ("artifact", "expired", True),
    ("artifact", "expires_at", "2026-11-29T05:38:30Z"), ("artifact", "size_in_bytes", 1),
    ("artifact", "name", "wealth-candidate-proof-raw-40824399844-1")])
def test_bootstrap_rejects_wrong_official_origin(section, key, value):
    meta = metadata(); meta[section][key] = value
    with pytest.raises(M.P.ProofRefused):
        M.validate_bootstrap_publication(meta, now=NOW)


def test_bootstrap_refuses_expiry_or_unsuccessful_job():
    with pytest.raises(M.P.ProofRefused, match="expired"):
        M.validate_bootstrap_publication(metadata(), now=M.P.expiry(M.BOOTSTRAP["artifact_expires_at"]))
    meta = metadata(); meta["jobs"]["jobs"][0]["conclusion"] = "failure"
    with pytest.raises(M.P.ProofRefused):
        M.validate_bootstrap_publication(meta, now=NOW)


def test_all_thirteen_candidate_owned_checkpoint_comparisons_are_required():
    assert M.validate_checkpoint_report(checkpoint_report())["physics_ticks"] == 2297


def test_comparison_uses_every_remaining_native_kernel_value_without_extra_scrubbing():
    expected = {"chronicle_bundle.json":b'{"fixture":"already decoded"}', "state.json":b'{"turn":422}', "raw.arrow":b"raw bytes"}
    report = M.compare_outputs(expected, dict(reversed(list(expected.items()))))
    assert report["status"] == "PASS" and report["expected_files"] == 3
    assert report["expected_outputs_sha256"] == report["actual_outputs_sha256"]
    for changed in ({**expected,"raw.arrow":b"different"}, {**expected,"extra.json":b"{}"}, {"state.json":expected["state.json"]}):
        with pytest.raises(M.P.ProofRefused):
            M.compare_outputs(expected, changed)
    with pytest.raises(M.P.ProofRefused): M.compare_outputs({}, {})


def test_publication_binds_all_thirteen_checkpoints_and_four_repeat_bundles():
    report=dict(checkpoint=checkpoint_report())
    files={"payload/"+row["path"]:dict(bytes=row["bytes"],sha256=row["sha256"])
        for world in report["checkpoint"]["worlds"] for row in world["checkpoints"]}
    for worldgen in ("template","procedural"):
        bundles=[dict(path=f"seed_42_{suffix}/chronicle_bundle.json",bytes=20,sha256="a"*64) for suffix in ("a","b")]
        report[worldgen]=dict(status="PASS",explicit_parallel=2,execution_scope=M.REPEAT_EXECUTION_SCOPE,bundles=bundles)
        for row in bundles:
            files[f"payload/repeats/{worldgen}/determinism_hybrid/batch_42/"+row["path"]]=dict(bytes=row["bytes"],sha256=row["sha256"])
    assert M.bind_scientific_payload(report,files)
    for name in list(files):
        changed=deepcopy(files); changed[name]["sha256"]="0"*64
        with pytest.raises(M.P.ProofRefused): M.bind_scientific_payload(report,changed)
    report["template"]["execution_scope"]="concurrent two-worker coverage"
    with pytest.raises(M.P.ProofRefused): M.bind_scientific_payload(report,files)


@pytest.fixture
def bootstrap_authority(tmp_path, monkeypatch):
    root = tmp_path/"bootstrap"; root.mkdir()
    negative = dict(status="PASS", checkpoint_sha256="0495e6f149ec55c9f7ec0c5e4e01228b3e15a5eb0cd6c93af24d07dfd0059198",
        candidate_native_sha256=M.P.REVIEWED_BUILD["candidate_native_sha256"], observed_native_sha256=M.B.OLD_NATIVE,
        exception="CheckpointIncompatible", mismatch_fields=["native extension"], native_restore_calls=0, python_restore_calls=0,
        allow_mismatch=False, source_sha=M.B.CANDIDATE_SOURCE)
    proof = dict(status="proof_complete_pending_job", physics_ticks_registered=926,
        producer=dict(control_sha=M.BOOTSTRAP["control_sha"], run_id=str(M.BOOTSTRAP["run_id"]), run_attempt="1", job_key="proof"),
        fixture_only="Synthetic authority tests transport binding, not science")
    files={}
    for name, value in (("proof.json",proof),("cross-native.json",negative)):
        raw=M.B.canonical_bytes(value); (root/name).write_bytes(raw)
        files[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    completion=M.B.canonical_bytes(dict(publication_complete=True, candidate_worlds_admitted=False, files=files))
    (root/"completion.json").write_bytes(completion)
    pins=dict(M.BOOTSTRAP, proof_sha256=files["proof.json"]["sha256"], negative_sha256=files["cross-native.json"]["sha256"],
        completion_sha256=hashlib.sha256(completion).hexdigest())
    monkeypatch.setattr(M,"BOOTSTRAP",pins)
    return root


def test_bootstrap_admission_requires_all_original_sealed_files(bootstrap_authority):
    original=M.admit_bootstrap(bootstrap_authority,metadata(),now=NOW)
    assert "cross-native.json" in M.P.parse(original)
    (bootstrap_authority/"unexpected.json").write_bytes(b"{}")
    with pytest.raises(M.P.ProofRefused,match="sealed authority"):
        M.admit_bootstrap(bootstrap_authority,metadata(),now=NOW)


@pytest.mark.parametrize("name",["proof.json","cross-native.json","completion.json"])
def test_bootstrap_authority_mutation_cannot_be_reused(bootstrap_authority,name):
    with (bootstrap_authority/name).open("ab") as stream: stream.write(b"\n")
    with pytest.raises(M.P.ProofRefused):
        M.admit_bootstrap(bootstrap_authority,metadata(),now=NOW)


def test_bootstrap_content_refuses_official_origin_before_opening_input(monkeypatch,tmp_path):
    value=metadata(); value["run"]["conclusion"]="failure"
    def forbidden(*_a,**_k): raise AssertionError("input access before origin")
    monkeypatch.setattr(M.P,"inventory",forbidden)
    with pytest.raises(M.P.ProofRefused,match="origin"):
        M.admit_bootstrap(tmp_path/"nonexistent",value,now=NOW)


@pytest.mark.parametrize("case", ["wrong_source", "old_native", "missing_world", "shifted_window", "missing_cp", "old_path", "wrong_header_turn",
    "nonexact", "unverified", "wrong_sections", "wrong_header_native", "mode_off", "different_key_count", "different_outputs", "mismatch", "skip", "wrong_ticks", "wrong_executions"])
def test_checkpoint_report_rejects_incomplete_ownership_or_comparison(case):
    value = checkpoint_report(); row = value["worlds"][0]["checkpoints"][0]
    if case == "wrong_source": value["source_sha"] = "0"*40
    elif case == "old_native": value["native_sha256"] = M.B.OLD_NATIVE
    elif case == "missing_world": value["worlds"].pop()
    elif case == "shifted_window": value["worlds"][0]["plan"]["checkpoint_turns"][0] = 100
    elif case == "missing_cp": value["worlds"][0]["checkpoints"].pop()
    elif case == "old_path": row["path"] = "historical/c101.ckpt"
    elif case == "wrong_header_turn": row["header"]["turn"] = 100
    elif case == "nonexact": row["header"]["exact"] = False
    elif case == "unverified": row["identity_matches"] = False
    elif case == "wrong_sections": row["header"]["sections"] = [dict(name="python")]
    elif case == "wrong_header_native": row["header"]["identity"]["native"]["sha256"] = M.B.OLD_NATIVE
    elif case == "mode_off": row["header"]["run_config"]["agent_mode"] = "off"
    elif case == "different_key_count": row["comparison"]["actual_files"] = 3
    elif case == "different_outputs": row["comparison"]["actual_outputs_sha256"] = "f"*64
    elif case == "mismatch": row["comparison"]["mismatches"] = ["state.json"]
    elif case == "skip": row["comparison"]["status"] = "SKIP"
    elif case == "wrong_ticks": value["physics_ticks"] = 2296
    elif case == "wrong_executions": value["executions"] = 14
    with pytest.raises(M.P.ProofRefused):
        M.validate_checkpoint_report(value)


def test_workflow_is_closed_dormant_exact_copy():
    root = Path(__file__).resolve().parents[1]
    template = (root / M.TEMPLATE_PATH).read_bytes()
    assert M.workflow_contract(template, template)
    assert b"workflow_dispatch" not in template and b"--parallel" not in template  # child command owns the fixed2
    assert M.ACTIVE_BRANCH.encode() in template and M.WORKFLOW_PATH.encode() in template
    assert b"github.event_name == 'push'" in template
    if (root / M.WORKFLOW_PATH).exists():
        assert M.workflow_contract(template, (root / M.WORKFLOW_PATH).read_bytes())
    with pytest.raises(M.P.ProofRefused): M.workflow_contract(template+b"\n", template+b"\n")
    with pytest.raises(M.P.ProofRefused): M.workflow_contract(template, template+b"\n")


def test_qualified_dependencies_stay_frozen_and_final_a_null():
    root = Path(__file__).resolve().parents[1]
    rows = M.source_bindings(root)
    assert rows["scripts/wealth_floor_candidate_proof.py"]["sha256"] == M.P_SHA256
    for name, digest in M.P.DEPENDENCIES.items():
        assert rows[name]["sha256"] == digest
    import scripts.wealth_floor_baseline_admission as A
    assert all(value is None for value in A.REVIEWED_CANDIDATE_PROOFS.values())
    assert M.registration()["bootstrap_root_review_sha256"] == "208b35e77f662d182984cc772ab6281fbe906d950e9a6a6858246716c2d37196"


def test_default_is_inactive_without_deployment_resource_or_runtime_probe(monkeypatch, capsys):
    def forbidden(*a, **k): raise AssertionError("actual probe/world forbidden")
    monkeypatch.setattr(M, "observe_runtime", forbidden)
    monkeypatch.setattr(M.P, "hosted_vm_precondition", forbidden)
    monkeypatch.setattr(M.C, "legacy_helpers", forbidden)
    assert M.main([]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "inactive" and value["physics_ticks_registered"] == 3097


def test_child_bad_runtime_refuses_before_scientific_source_import(monkeypatch, tmp_path):
    def refused(): raise M.P.ProofRefused("actual two-CPU affinity required")
    def forbidden(*a, **k): raise AssertionError("source access before runtime admission")
    monkeypatch.setattr(M, "observe_runtime", refused)
    monkeypatch.setattr(M.P, "read_bytes", forbidden)
    with pytest.raises(M.P.ProofRefused, match="two-CPU"):
        M.child(SimpleNamespace(source=tmp_path, output=tmp_path, child="checkpoints"))


@pytest.mark.parametrize("failure", ["build", "bootstrap"])
def test_prerequisite_failure_precedes_native_environment_or_world_commands(monkeypatch, tmp_path, failure):
    control, source, temporary = tmp_path/"control", tmp_path/"candidate", tmp_path/"temp"
    control.mkdir(); source.mkdir(); temporary.mkdir()
    monkeypatch.setattr(M, "SCRIPT", control/"scripts/wealth_floor_production_primer.py")
    for key, val in dict(GITHUB_WORKSPACE=str(tmp_path), RUNNER_TEMP=str(temporary), GITHUB_REF="refs/heads/"+M.ACTIVE_BRANCH,
        GITHUB_JOB="primer", GITHUB_RUN_ID="101", GITHUB_RUN_ATTEMPT="1", GITHUB_SHA="a"*40).items(): monkeypatch.setenv(key,val)
    monkeypatch.setattr(M.platform, "python_version", lambda: M.B.PYTHON_VERSION)
    monkeypatch.setattr(M, "staging_observation", lambda *_: {})
    monkeypatch.setattr(M, "source_bindings", lambda *_: {"fixture":"unchanged"})
    monkeypatch.setattr(M, "workflow_contract", lambda *_: True)
    monkeypatch.setattr(M.P, "read_bytes", lambda *_: b"fixture")
    monkeypatch.setattr(M.P, "read_json", lambda *_: {})
    monkeypatch.setattr(M.P, "hosted_vm_precondition", lambda: {"fixture_only":True})
    monkeypatch.setattr(M.C, "legacy_helpers", lambda *_: None)
    monkeypatch.setattr(M.C, "direct_children", lambda: [])
    monkeypatch.setattr(M.os, "sched_getaffinity", lambda _: {0,1,2,3})
    monkeypatch.setattr(M.os, "sched_setaffinity", lambda *_: None)
    monkeypatch.setattr(M.C, "source_snapshot", lambda *_: {"fixture":"unchanged"})
    calls=[]
    class Lease:
        def __enter__(self): return self
        def __exit__(self,*_): return False
    class Cancellation(Lease): cancelled=False
    class Supervisor:
        cleanup_complete=True
        def admission(self,*_): pass
        def check(self,**_): pass
        def command(self,*_a,**_k): calls.append("COMMAND"); raise AssertionError("native/environment command before prerequisites")
    monkeypatch.setattr(M.C,"SubreaperLease",Lease)
    monkeypatch.setattr(M.C,"Cancellation",Cancellation)
    monkeypatch.setattr(M.C,"make_supervisor",lambda *_:Supervisor())
    def build(*_a,**_k):
        calls.append("build")
        if failure=="build": raise M.P.ProofRefused("synthetic unqualified build")
        return object()
    def bootstrap(*_a,**_k):
        calls.append("bootstrap"); raise M.P.ProofRefused("synthetic unqualified bootstrap")
    monkeypatch.setattr(M.P,"admit_build",build)
    monkeypatch.setattr(M,"admit_bootstrap",bootstrap)
    root=temporary/"wealth-production-primer"
    assert M.proof(SimpleNamespace(source=str(source),output=str(root))) == 1
    assert calls == (["build"] if failure=="build" else ["build","bootstrap"])
    complete=json.loads((root/"publication/completion.json").read_bytes())
    assert complete["publication_complete"] is False and complete["failure_stage"] == "prerequisite_content_admission"


def test_failed_retention_preserves_partial_and_original_payload(tmp_path):
    (tmp_path/"scratch").mkdir(); (tmp_path/"scratch/real.ckpt").write_bytes(b"synthetic CP bytes")
    (tmp_path/"payload").mkdir(); (tmp_path/"payload/partial.ckpt").write_bytes(b"partial")
    with pytest.raises(M.P.ProofRefused):
        M.retain_payload(tmp_path, cleanup_complete=True, children_gone=True, check=lambda:None)
    assert (tmp_path/"scratch/real.ckpt").read_bytes() == b"synthetic CP bytes"
    assert (tmp_path/"payload/partial.ckpt").read_bytes() == b"partial"


def test_physical_retention_copies_complete_exports_without_scientific_exclusions(tmp_path):
    scratch=tmp_path/"scratch"; (scratch/"checkpoints").mkdir(parents=True)
    (scratch/"checkpoints/own.ckpt").write_bytes(b"synthetic CP")
    (scratch/"state.json").write_bytes(b"{}")
    retained=M.retain_payload(tmp_path,cleanup_complete=True,children_gone=True,check=lambda:None)
    assert retained["physical_files"] == 2
    assert (tmp_path/"payload/checkpoints/own.ckpt").read_bytes() == b"synthetic CP"
    assert (scratch/"checkpoints/own.ckpt").exists()
