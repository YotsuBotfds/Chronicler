"""Provenance and post-fork coverage are prerequisites for descriptive contrasts."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest
from chronicler.bundle_codec import dumps_bundle
from chronicler.expansion_audit import AuditError, Limits
from chronicler.expansion_compare import compare_paths, main, render_markdown


def identity():
    return {"source": {"git_sha": "a"*40, "package_digest": "b"*64, "package_dir": "/PRIVATE/SOURCE"},
            "native": {"status": "found", "sha256": "d"*64, "module_file": "/PRIVATE/NATIVE"}}


def observation(turn, care):
    values = dict(episodes=5, new_injuries=1, recoveries=0, impaired_work=2,
        care_work=care, care_recipients=2 if care else 0, recovery_progress=1,
        cared_recovery_progress=1 if care else 0)
    return {"source_turn": turn, "units": "worker-turns", **values,
            "regions": [{"region": 0, "region_name": "R", **values}]}


def write_run(root, arm, seed=42, *, parent=False):
    source=identity()
    controls=dict(care_enabled=True, injury_rate=.01, impairment=.5, care_fraction=.2, recovery_work=2)
    after={**controls, "care_enabled": arm != "no_care"}
    env={"python":"3.13.5","implementation":"CPython","machine":"x86_64","hash_seed":"0",
         "packages":{"pydantic":"2.12.5"},"thread_env":{"RAYON_NUM_THREADS":"1"},"affinity_cpu_count":4}
    receipt=dict(schema_version=1, experiment="probe", feature="health_care", cohort="development",
        arm=arm, seed=seed, applied_before_turn=0 if parent else 1, intervention_fork=not parent,
        controls_before=controls, controls_after=after, registration=None, **source,
        parent_checkpoint=None if parent else {"sha256":"c"*64,"turn":1,"seed":seed,"exact":True,
            "path":"/PRIVATE/PARENT.ckpt","identity":{**source,"environment":env},
            "flags":{"health_care":True,"grain_reserves":False}})
    history=[{"turn":t+1,"health_care":observation(t,99 if t==0 else .4 if after["care_enabled"] else 0)} for t in range(4)]
    bundle={"metadata":{"seed":seed,"total_turns":4,"expansion_experiment":receipt},
        "world_state":{"turn":4,"marker":"same" if after["care_enabled"] else "alternative"},
        "history":history,"events_timeline":[]}
    folder=root/f"seed_{seed}"/arm
    folder.mkdir(parents=True)
    path=folder/"chronicle_bundle.json"
    path.write_text(dumps_bundle(bundle))
    (folder/"worker_identity.json").write_text(json.dumps({"before":{**source,"environment":env},
                                                        "after":{**source,"environment":env}}))
    return path


def change(path, fn):
    from chronicler.bundle_codec import load_bundle
    data=load_bundle(path)
    fn(data)
    path.write_text(dumps_bundle(data))


@pytest.fixture
def runs(tmp_path):
    parent=write_run(tmp_path,"parent",parent=True)
    base=write_run(tmp_path,"care")
    alt=write_run(tmp_path,"no_care")
    return parent,base,alt


def test_only_postfork_metrics_are_compared_with_exact_disclosures(runs):
    report=compare_paths(runs)
    assert report["status"]=="descriptive_only"
    assert report["summary"]["matched_contrasts"]==1 and report["summary"]["recorded_seed_ids"]==[42]
    pair=report["pairs"][0]
    assert pair["comparable_recorded_window"] and not pair["blockers"]
    assert pair["arm_minus_baseline"]["care_worker_turns"]==pytest.approx(-1.2)
    assert pair["arm_minus_baseline"]["censored_episodes"] is None
    base=next(r for r in report["runs"] if r["arm"]=="care")
    assert base["metrics"]["care_worker_turns"]==pytest.approx(1.2)  # shared prefix 99 excluded
    assert base["window"]=={"start":1,"end_exclusive":4}
    assert base["worker_source_binary_verified"] and base["identity"]["native_sha256"]=="d"*64
    assert report["noop_checks"][0]["final_exported_python_world_equal"] is True
    assert "/PRIVATE" not in json.dumps(report) and "/PRIVATE" not in render_markdown(report)


@pytest.mark.parametrize("field,value,blocker", [
    ("source",{"git_sha":"e"*40,"package_digest":"b"*64},"source_or_binary_mismatch"),
    ("native",{"status":"found","sha256":"e"*64},"source_or_binary_mismatch"),
    ("controls_after",dict(care_enabled=True,injury_rate=.01,impairment=.5,care_fraction=.2,recovery_work=2),"named_arm_control_mismatch"),
    ("cohort","confirmatory","baseline_missing_or_ambiguous"),
])
def test_mismatched_identity_control_or_cohort_blocks_pooling(runs,field,value,blocker):
    change(runs[2],lambda b:b["metadata"]["expansion_experiment"].__setitem__(field,value))
    report=compare_paths(runs)
    pair=report["pairs"][0]
    assert blocker in pair["blockers"] and pair["arm_minus_baseline"] is None


@pytest.mark.parametrize("change_kind,blocker", [
    ("checkpoint","parent_checkpoint_mismatch"),("flags","feature_flag_mismatch"),
    ("env","parent_environment_receipt_mismatch"),("prefix","pre_intervention_history_mismatch"),
    ("window","window_mismatch"),("gap","incomplete_treatment_window"),
    ("integrity","record_integrity_failed"),("health_controls","non_care_health_controls_differ"),
])
def test_boundaries_controls_prefix_and_completeness_are_checked(runs,change_kind,blocker):
    def mutate(b):
        r=b["metadata"]["expansion_experiment"]
        if change_kind=="checkpoint":r["parent_checkpoint"]["sha256"]="e"*64
        elif change_kind=="flags":r["parent_checkpoint"]["flags"]["grain_reserves"]=True
        elif change_kind=="env":r["parent_checkpoint"]["identity"]["environment"]["thread_env"]["RAYON_NUM_THREADS"]="2"
        elif change_kind=="prefix":
            b["history"][0]["health_care"]["episodes"]=7
            b["history"][0]["health_care"]["regions"][0]["episodes"]=7
        elif change_kind=="window":
            b["metadata"]["total_turns"]=5
            b["world_state"]["turn"]=5
        elif change_kind=="gap":b["history"].pop(2)
        elif change_kind=="health_controls":r["controls_after"]["injury_rate"]=.02
        else:b["history"][1]["health_care"]["care_work"]=-1
    change(runs[2],mutate)
    pair=compare_paths(runs)["pairs"][0]
    assert blocker in pair["blockers"] and not pair["comparable_recorded_window"]


def test_worker_before_after_must_match_and_missing_is_unknown(runs):
    path=runs[2].parent/"worker_identity.json"
    data=json.loads(path.read_text())
    data["after"]["native"]["sha256"]="e"*64
    path.write_text(json.dumps(data))
    assert "worker_identity_changed_or_mismatched" in compare_paths(runs)["pairs"][0]["blockers"]
    path.unlink()
    assert "worker_identity_unavailable" in compare_paths(runs)["pairs"][0]["blockers"]


def test_parent_controls_must_match_and_missing_controls_cannot_be_noop(runs):
    change(runs[2],lambda b:b["metadata"]["expansion_experiment"]["controls_before"].__setitem__("injury_rate",.02))
    assert "parent_control_mismatch" in compare_paths(runs)["pairs"][0]["blockers"]
    change(runs[1],lambda b:b["metadata"]["expansion_experiment"].update(controls_before=None,controls_after=None))
    assert compare_paths(runs)["noop_checks"]==[]


def test_unknown_units_and_limited_scan_cannot_produce_numeric_treatment_delta(runs):
    def unknown(b):b["history"][2]["health_care"]["units"]="kg"
    change(runs[2],unknown)
    result=compare_paths(runs)
    assert result["pairs"][0]["arm_minus_baseline"]["care_worker_turns"] is None
    limited=compare_paths(runs,audit_limits=Limits(max_snapshots=1))
    assert not limited["pairs"][0]["comparable_recorded_window"]
    assert all(r["audit"]["status"]=="partial" for r in limited["runs"])
    assert all(v is None for r in limited["runs"] for v in r["metrics"].values())


def test_duplicate_roles_missing_baselines_and_file_bounds_are_explicit(runs,tmp_path):
    duplicate=tmp_path/"duplicate"
    duplicate.mkdir()
    for name in ("chronicle_bundle.json","worker_identity.json"):
        (duplicate/name).write_bytes((runs[1].parent/name).read_bytes())
    assert "baseline_missing_or_ambiguous" in compare_paths([*runs,duplicate])["pairs"][0]["blockers"]
    assert "baseline_missing_or_ambiguous" in compare_paths([runs[2]])["pairs"][0]["blockers"]
    with pytest.raises(AuditError,match="more than once"):compare_paths([runs[1],runs[1]])
    with pytest.raises(AuditError,match="max_runs"):compare_paths(runs,max_runs=2)


def test_deterministic_escaped_exports_and_source_worker_overwrite_protection(runs,tmp_path,capsys):
    a,b=compare_paths(runs),compare_paths(reversed(runs))
    assert a==b and render_markdown(a)==render_markdown(b)
    before=[p.read_bytes() for p in runs]
    out=tmp_path/"out.json"
    assert main([*[str(p) for p in runs],"--format","json","--json",str(out)])==0
    assert json.loads(capsys.readouterr().out)==a and [p.read_bytes() for p in runs]==before
    for target in (runs[1],runs[1].parent/"worker_identity.json"):
        assert main([*[str(p) for p in runs],"--json",str(target)])==2
        assert "must not overwrite" in capsys.readouterr().err


def test_parent_only_and_legacy_bundles_are_unpaired_not_qualified(runs,tmp_path):
    assert compare_paths([runs[0]])["status"]=="blocked_or_unpaired"
    old=tmp_path/"old.json"
    old.write_text(json.dumps({"metadata":{"total_turns":1},"history":[{"turn":1}]}))
    report=compare_paths([old])
    assert report["status"]=="blocked_or_unpaired"
    assert "missing_or_unknown_experiment_receipt" in report["runs"][0]["blockers"]


def test_unknown_feature_is_named_but_never_interpreted(runs):
    change(runs[2],lambda b:b["metadata"]["expansion_experiment"].update(feature="scientific_claims"))
    report=compare_paths(runs)
    unknown=next(r for r in report["runs"] if r["feature"]=="scientific_claims")
    assert unknown["metrics"]=={} and "missing_or_unknown_experiment_receipt" in unknown["blockers"]
    assert not next(p for p in report["pairs"] if p["feature"]=="scientific_claims")["comparable_recorded_window"]


def test_malformed_nonfinite_metadata_is_unknown_and_never_exported_as_nan(runs):
    def mutate(b):
        r=b["metadata"]["expansion_experiment"]
        r["applied_before_turn"]=float("nan")
        r["parent_checkpoint"]["seed"]=float("nan")
        r["controls_after"]["injury_rate"]=float("nan")
    from chronicler.bundle_codec import load_bundle
    data=load_bundle(runs[2])
    mutate(data)
    # Deliberately malformed JSON numerics bypass the normal strict writer.
    runs[2].write_text(json.dumps(data))
    report=compare_paths(runs)
    assert not report["pairs"][0]["comparable_recorded_window"]
    json.dumps(report,allow_nan=False)


def test_invalid_environment_paths_are_withheld_and_block_comparison(runs):
    change(runs[2],lambda b:b["metadata"]["expansion_experiment"]["parent_checkpoint"]["identity"]["environment"]["thread_env"].update(RAYON_NUM_THREADS="/PRIVATE/UNKNOWN"))
    report=compare_paths(runs)
    assert "parent_flags_or_environment_unavailable" in report["pairs"][0]["blockers"]
    assert "/PRIVATE" not in json.dumps(report)


def test_python_world_identity_is_unknown_when_final_state_is_missing(runs):
    change(runs[1],lambda b:b.pop("world_state"))
    report=compare_paths(runs)
    assert report["noop_checks"][0]["final_exported_python_world_equal"] is None


def test_discovery_and_export_alias_limits(runs,tmp_path,capsys):
    assert main([str(tmp_path),"--max-runs","2"])==2
    assert "max_runs" in capsys.readouterr().err
    alias=tmp_path/"bundle-alias.json"
    alias.hardlink_to(runs[1])
    assert main([*[str(p) for p in runs],"--json",str(alias)])==2
    assert "must not overwrite" in capsys.readouterr().err


def test_actual_worker_environment_changes_block_without_parent_header_backfill(runs):
    path=runs[2].parent/"worker_identity.json"
    data=json.loads(path.read_text())
    data["after"]["environment"]["thread_env"]["RAYON_NUM_THREADS"]="2"
    path.write_text(json.dumps(data))
    result=compare_paths(runs)
    assert "worker_environment_changed" in result["pairs"][0]["blockers"]
    arm=next(r for r in result["runs"] if r["arm"]=="no_care")
    assert arm["environment"] is None and arm["parent_environment"]["thread_env"]["RAYON_NUM_THREADS"]=="1"


def test_missing_worker_environment_is_distinct_from_observed_instability(runs):
    path=runs[2].parent/"worker_identity.json"
    data=json.loads(path.read_text())
    for side in ("before","after"):data[side].pop("environment")
    path.write_text(json.dumps(data))
    blockers=compare_paths(runs)["pairs"][0]["blockers"]
    assert "worker_environment_unavailable" in blockers and "worker_environment_changed" not in blockers


def test_parent_environment_is_disclosed_without_becoming_measured_worker_environment(runs):
    for path in runs[1:]:
        change(path,lambda b:b["metadata"]["expansion_experiment"]["parent_checkpoint"]["identity"]["environment"]["thread_env"].update(RAYON_NUM_THREADS="4"))
    result=compare_paths(runs)
    assert result["pairs"][0]["comparable_recorded_window"]
    arm=next(r for r in result["runs"] if r["arm"]=="no_care")
    assert arm["environment"]["thread_env"]["RAYON_NUM_THREADS"]=="1"
    assert arm["parent_environment"]["thread_env"]["RAYON_NUM_THREADS"]=="4"


def test_missing_required_tables_do_not_become_zero_treatment_metrics(runs):
    change(runs[2],lambda b:b["history"][2]["health_care"].pop("regions"))
    result=compare_paths(runs)
    assert "incomplete_feature_receipts" in result["pairs"][0]["blockers"]
    assert all(v is None for v in next(r for r in result["runs"] if r["arm"]=="no_care")["metrics"].values())


def test_declared_runtime_environment_must_match_measured_worker(runs):
    def mutate(b):
        r=b["metadata"]["expansion_experiment"]
        r["environment"]=copy.deepcopy(r["parent_checkpoint"]["identity"]["environment"])
        r["environment"]["thread_env"]["RAYON_NUM_THREADS"]="2"
    change(runs[2],mutate)
    assert "runtime_environment_mismatch" in compare_paths(runs)["pairs"][0]["blockers"]


def test_recorded_worker_instability_and_external_runner_differences_block(runs):
    for path,digest in ((runs[1],"e"*64),(runs[2],"f"*64)):
        worker_path=path.parent/"worker_identity.json"
        data=json.loads(worker_path.read_text())
        data["runner_sha256"]=digest
        worker_path.write_text(json.dumps(data))
    assert "external_runner_mismatch" in compare_paths(runs)["pairs"][0]["blockers"]
    worker_path=runs[2].parent/"worker_identity.json"
    data=json.loads(worker_path.read_text())
    data["identities_stable"]=False
    worker_path.write_text(json.dumps(data))
    assert "worker_reported_instability" in compare_paths(runs)["pairs"][0]["blockers"]


def test_external_runner_before_after_hash_must_remain_stable(runs):
    worker_path=runs[2].parent/"worker_identity.json"
    data=json.loads(worker_path.read_text())
    data.update(runner_sha256="e"*64,runner_sha256_after="f"*64)
    worker_path.write_text(json.dumps(data))
    assert "external_runner_changed" in compare_paths(runs)["pairs"][0]["blockers"]


def test_actual_batch_manifest_environment_schema_is_normalized_without_parent_backfill(runs):
    for path in runs:
        worker_path=path.parent/"worker_identity.json"
        data=json.loads(worker_path.read_text())
        for side in ("before","after"):
            env=data[side]["environment"]
            env.pop("hash_seed")
            env["thread_env"]["PYTHONHASHSEED"]="0"
            env.update(executable="/PRIVATE/ACTUAL-WORKER",platform="Linux-x86_64",cpu_count=4,process_cpu_count=4)
        worker_path.write_text(json.dumps(data))
    report=compare_paths(runs)
    assert report["pairs"][0]["comparable_recorded_window"]
    base=next(r for r in report["runs"] if r["arm"]=="care")
    assert base["environment"]["hash_seed"]=="0"
    assert base["environment"]["platform"]=="Linux-x86_64" and base["environment"]["process_cpu_count"]==4
    assert base["environment"]["executable_path_sha256"]
    assert "/PRIVATE" not in json.dumps(report)
