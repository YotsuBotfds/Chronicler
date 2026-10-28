"""Synthetic full-size metadata tests; no worlds, native pools or oracle reruns."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from chronicler import validation_compare, validation_gate
from chronicler.batch_manifest import batch_cohort
from chronicler.validation_communities import community_method_2_result
from test_validation_compare import _manifest_report
from test_validation_ablation import _NEEDS_7, _COHORT_4

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cloud_full_gate_comparison", ROOT / "scripts" / "cloud_full_gate_comparison.py")
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)
MODULES = {"validation_compare": validation_compare, "validation_gate": validation_gate}


def _raw(value):
    return Q._encoded(value)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _record(raw):
    return {"bytes": len(raw), "sha256": _sha(raw)}


def _environment():
    return {
        "python": "3.13.17", "implementation": "CPython", "machine": "x86_64",
        "platform": "Linux-synthetic", "executable": "/synthetic/python",
        "cpu_count": 4, "process_cpu_count": 2, "affinity_cpu_count": 2,
        "thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                       "MKL_NUM_THREADS": "1", "BLIS_NUM_THREADS": "1",
                       "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                       "GOTO_NUM_THREADS": "1", "RAYON_NUM_THREADS": "1",
                       "PYTHON_CPU_COUNT": "2", "PYTHONHASHSEED": "0"},
        "packages": {"numpy": "2.0", "scipy": "1.0", "pyarrow": "20.0",
                     "pydantic": "2.0", "arro3-core": "0.6", "chronicler-agents": "0.1"},
    }


def _build():
    return {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-build", "qualified": True,
        "baseline_sha": Q.BASELINE, "candidate_sha": Q.CANDIDATE, "control_sha": "c" * 40,
        "github_run_id": "1234", "github_run_attempt": "1", "crate_tree": Q.CRATE_TREE,
        "lock_sha256": "1" * 64, "pyproject_sha256": "2" * 64, "python_version": "3.13.17",
        "source_snapshot_before_sha256": "3" * 64, "source_snapshot_after_sha256": "3" * 64,
        "native": {"sha256": "a" * 64, "schemas": {
            name: {"version": 1, "fingerprint": "schema-" + name, "schema_sha256": "f" * 64}
            for name in Q.CLASSES}},
        "wheel": {"filename": "chronicler_agents-0.1-cp313-cp313-linux_x86_64.whl",
                  "bytes": 2048, "sha256": "e" * 64,
                  "native_member": "chronicler_agents/chronicler_agents.so", "native_sha256": "a" * 64},
        "environment": _environment(), "budget_seconds": 4800, "elapsed_wall_seconds": 1.0,
    }


def _cohort(root, role, build_raw, *, fail=False, smoke=False):
    root.mkdir()
    (root / "report").mkdir()
    worldgen, arm = role.split("-")
    expected = Q.expected_cohort(worldgen)
    if smoke:
        expected.update(profile="subset", seed_count=2, turns=125, fork_turns=[100],
                        checkpoint_turns=[101], fork_count=4, require_strict_regression=False)
    source = Q.BASELINE if arm == "baseline" else Q.CANDIDATE
    seeds = list(range(42, 42 + expected["seed_count"]))
    source_info = {"git_sha": source, "package_digest": ("b" if arm == "baseline" else "d") * 64}
    native = {"status": "found", "source": "imported", "module_file": "/synthetic/native.so",
              "bytes": 1234, "sha256": "a" * 64}
    simulation = Q.registered_simulation(expected)
    batch = {
        "schema_version": 1, "kind": "chronicler-batch", "status": "complete",
        "completed_at": "synthetic", "seeds": seeds, "turns": expected["turns"],
        "parallel_requested": 2, "source": source_info, "native": native,
        "simulation": simulation, "environment": _environment(),
        "runs": [{"seed": seed, "dir": "seed_" + str(seed),
                  "bundle": f"seed_{seed}/chronicle_bundle.json", "total_turns": expected["turns"],
                  "files": {f"seed_{seed}/" + name: "4" * 64 for name in (
                      "chronicle_bundle.json", "agent_events.arrow", "validation_needs.arrow",
                      "validation_relationships.arrow", "validation_memory_signatures.arrow",
                      "validation_summary.json", "validation_community_summary.json")}} for seed in seeds],
    }
    batch_raw = _raw(batch)
    forks = [{
        "arm": which, "seed": seed, "run_dir": "seed_" + str(seed), "fork_turn": turn,
        "dir": f"{which}/seed_{seed}/fork_{turn}", "total_turns": turn + 22,
        "decision_ablation": {"name": which, "start_turn": turn + 1, "forked_at": turn + 1},
        "files": {"agent_events.arrow": "5" * 64, "fork.json": "6" * 64},
    } for seed in seeds for turn in expected["fork_turns"] for which in expected["arms"]]
    ablation = {
        "schema_version": 2, "kind": "chronicler-ablation-arms", "design": 2,
        "status": "complete", "seeds": seeds, "window_turns": 20,
        "arms": expected["arms"], "fork_turns": expected["fork_turns"],
        "fork_count": expected["fork_count"], "forks": forks,
        "fork_rule": {"first": 100, "every": 20 if worldgen == "procedural" else 100,
                      "worldgen": worldgen, "plain_total_turns": expected["turns"]},
        "plain_manifest_sha256": _sha(batch_raw), "source": source_info, "native": native,
    }
    ablation_raw = _raw(ablation)
    report = _manifest_report(seeds, turns=expected["turns"], simulation=simulation, profile=expected["profile"])
    report["batch_manifest"] = batch_cohort(batch, _sha(batch_raw))
    report["causal_oracles_required"] = False
    if worldgen == "procedural":
        report["worlds"] = [{"generator": "procedural", "regions": 32, "civs": 10}]
    needs, cohort = deepcopy(_NEEDS_7), deepcopy(_COHORT_4)
    needs["method_version"] = 8
    needs["ablation"]["fork_design"] = 2
    cohort.update(method_version=6, community_method_version=2)
    cohort["ablation"]["fork_design"] = 2
    report["results"].update(needs=needs, cohort=cohort,
        community=community_method_2_result({"status": "PASS"}, {"status": "FAIL", "reason": "synthetic small regions"}))
    report["results"]["regression"].update(
        regression_adjudication="strict", strict_regression_ok=True,
        strict_regression_failed_checks=[], calibrated_floor_relaxed_checks=[])
    if fail:
        report["results"]["era"] = {"status": "FAIL", "reason": "synthetic registered criterion failure"}
    report["ablation_arms"] = {
        "status": "verified", "manifest_sha256": _sha(ablation_raw), "design": 2,
        "arms": expected["arms"], "fork_turns": expected["fork_turns"], "window_turns": 20,
        "forks": expected["fork_count"], "native_sha256": "a" * 64,
        "history_identity": "every fork's agent events equal the plain run's up to the fork turn",
    }
    decision = validation_gate.build_gate_decision_payload(
        validation_gate.adjudicate_validation_report(expected["profile"], report,
                                                     require_strict_regression=expected["require_strict_regression"],
                                                     require_causal_oracles=False),
        report, report_path=Path("/synthetic/original/validate_report_full.json"))
    run = {
        "profile": expected["profile"], "worldgen": worldgen, "seed_start": 42,
        "seeds": expected["seed_count"], "turns": expected["turns"], "parallel": 2,
        "ablation_oracles": True, "ablation_arms": expected["arms"],
        "ablation_fork_turns": expected["fork_turns"], "ablation_forks": expected["fork_count"],
        "causal_oracles_required": False, "require_strict_regression": expected["require_strict_regression"],
        "batch_manifest_status": "verified", "exploratory_comparison": False,
        "gate_status": "PASS" if decision["ok"] else "FAIL", "gate_exit_code": decision["exit_code"],
    }
    payloads = {
        "build-manifest.json": build_raw,
        "report/batch_manifest.json": batch_raw,
        "report/ablation_manifest.json": ablation_raw,
        "report/validate_report_full.json": _raw(report),
        "report/gate_decision_full.json": _raw(decision),
        "report/gate_summary_full.md": b"synthetic original summary\n",
        "report/run_manifest.json": _raw(run),
    }
    raw_files = {}
    for name in Q.REPORT_FILES:
        path = ("raw/full_gate/ablation_42/" if name == "ablation_manifest.json"
                else "raw/full_gate/batch_42/") + name
        raw_files[path] = _record(payloads["report/" + name])
    for row in batch["runs"]:
        for name, digest in row["files"].items():
            raw_files["raw/full_gate/batch_42/" + name] = {"bytes": 1, "sha256": digest}
    for row in ablation["forks"]:
        for name, digest in row["files"].items():
            raw_files["raw/full_gate/ablation_42/" + row["dir"] + "/" + name] = {"bytes": 1, "sha256": digest}
    for phase in ("before", "after"):
        raw_files["source-snapshot-" + phase + ".json"] = {"bytes": 1, "sha256": "7" * 64}
    inventory = {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-raw-inventory",
        "complete": True,
        "scope": "worker payload before derived light copies; excludes final receipts and inventory",
        "file_count": len(raw_files), "total_bytes": sum(v["bytes"] for v in raw_files.values()),
        "files": raw_files,
    }
    payloads["raw-inventory.json"] = _raw(inventory)
    probe = {"source": source_info, "native": {**native, "schemas": _build()["native"]["schemas"]},
             "environment": _environment(), "affinity": [2, 3],
             "prefix": "/synthetic", "source_file": "/synthetic/source/src/chronicler/__init__.py"}
    provenance = {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-provenance",
        "stage": "smoke" if smoke else "full", "arm": arm, "worldgen": worldgen, "source_sha": source,
        "control_sha": "c" * 40, "github_run_id": "1234", "github_run_attempt": "1",
        "identities_stable": True, "build_manifest_sha256": _sha(build_raw),
        "wheel_sha256": "e" * 64, "native_sha256": "a" * 64,
        "source_snapshot_before_sha256": "7" * 64, "source_snapshot_after_sha256": "7" * 64,
        "before": probe, "after": deepcopy(probe),
    }
    payloads["provenance.json"] = _raw(provenance)
    for name, raw in payloads.items():
        (root / name).write_bytes(raw)
    _seal(root, role=role, expected=expected, source=source, decision=decision)
    if smoke:
        result = json.loads((root / "result.json").read_text())
        result["kind"] = "chronicler-cloud-full-gate-smoke"
        result.update(stage="smoke", qualified=False, smoke_pass=True, budget_seconds=4800)
        (root / "result.json").write_bytes(_raw(result))


def _seal(root, *, role=None, expected=None, source=None, decision=None):
    if role is None:
        old = json.loads((root / "result.json").read_text())
        role = old["worldgen"] + "-" + old["arm"]
        expected, source = old["expected"], old["source_sha"]
        decision = json.loads((root / "report/gate_decision_full.json").read_text())
    worldgen, arm = role.split("-")
    files = {name: _record((root / name).read_bytes()) for name in Q.INDEXED_FILES}
    index = {"schema_version": 1, "kind": "chronicler-cloud-full-gate-light-index",
             "complete": True, "missing": [], "files": files,
             "file_count": len(files), "total_bytes": sum(v["bytes"] for v in files.values())}
    (root / "artifact-index.json").write_bytes(_raw(index))
    result = {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-cohort",
        "arm": arm, "worldgen": worldgen, "source_sha": source, "expected": expected,
        "stage": "full", "execution_complete": True, "identities_stable": True,
        "qualified": decision["ok"], "budget_seconds": 19800, "elapsed_wall_seconds": 1.0,
        "gate_pass": decision["ok"], "gate_exit_code": decision["exit_code"],
        "build_manifest_sha256": files["build-manifest.json"]["sha256"],
        "wheel_sha256": "e" * 64, "native_sha256": "a" * 64,
        "provenance_sha256": files["provenance.json"]["sha256"],
        "raw_inventory_sha256": files["raw-inventory.json"]["sha256"],
        "light_index_sha256": _sha(_raw(index)),
    }
    (root / "result.json").write_bytes(_raw(result))


def _reseal_reports(root):
    """Keep every legitimate report/manifest/hash link coherent after a mutation."""
    batch = json.loads((root / "report/batch_manifest.json").read_text())
    batch_raw = _raw(batch)
    ablation = json.loads((root / "report/ablation_manifest.json").read_text())
    ablation["plain_manifest_sha256"] = _sha(batch_raw)
    (root / "report/ablation_manifest.json").write_bytes(_raw(ablation))
    report = json.loads((root / "report/validate_report_full.json").read_text())
    report["batch_manifest"] = batch_cohort(batch, _sha(batch_raw))
    report["ablation_arms"]["manifest_sha256"] = _sha(_raw(ablation))
    (root / "report/validate_report_full.json").write_bytes(_raw(report))
    saved = json.loads((root / "report/gate_decision_full.json").read_text())
    decision = validation_gate.build_gate_decision_payload(
        validation_gate.adjudicate_validation_report(
            "full", report, require_strict_regression=True, require_causal_oracles=False),
        report, report_path=Path(saved["report_path"]))
    (root / "report/gate_decision_full.json").write_bytes(_raw(decision))
    run = json.loads((root / "report/run_manifest.json").read_text())
    run.update(gate_status="PASS" if decision["ok"] else "FAIL", gate_exit_code=decision["exit_code"])
    (root / "report/run_manifest.json").write_bytes(_raw(run))
    inventory = json.loads((root / "raw-inventory.json").read_text())
    for name in Q.REPORT_FILES:
        path = ("raw/full_gate/ablation_42/" if name == "ablation_manifest.json"
                else "raw/full_gate/batch_42/") + name
        inventory["files"][path] = _record((root / "report" / name).read_bytes())
    inventory["total_bytes"] = sum(row["bytes"] for row in inventory["files"].values())
    (root / "raw-inventory.json").write_bytes(_raw(inventory))
    _seal(root)


@pytest.fixture
def matrix(tmp_path):
    build_raw = _raw(_build())
    roots = {}
    for role in Q.ROLES:
        roots[role] = tmp_path / role
        _cohort(roots[role], role, build_raw)
    return roots, _sha(build_raw)



def _retention_envelope(*, remove=None, jobs="success"):
    observed = datetime.now(timezone.utc)
    artifacts = []
    for number, role in enumerate(Q.ROLES, 1):
        worldgen, arm = role.split("-")
        artifacts.append({
            "id": number, "name": f"full-gates-raw-{arm}-{worldgen}-1234-1",
            "size_in_bytes": 1234, "digest": "sha256:" + "8" * 64, "expired": False,
            "created_at": (observed - timedelta(seconds=1)).isoformat(),
            "expires_at": (observed + timedelta(days=30)).isoformat(),
            "workflow_run": {"id": 1234, "head_sha": "c" * 40},
        })
    if remove is not None:
        artifacts.pop(remove)
    response = {"total_count": len(artifacts), "artifacts": artifacts}
    raw = json.dumps(response)
    return {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-retention-index",
        "repo_full_name": "YotsuBotfds/Chronicler", "github_run_id": "1234",
        "github_run_attempt": "1", "control_sha": "c" * 40,
        "cohort_job_result": jobs, "complete": True, "observed_at": observed.isoformat(),
        "api_url": "https://api.github.com/repos/YotsuBotfds/Chronicler/actions/runs/1234/artifacts?per_page=100",
        "raw_response": raw, "raw_response_sha256": _sha(raw.encode()),
        "total_count": len(artifacts), "artifacts": artifacts,
    }


def _retention_file(tmp_path, envelope=None):
    path = tmp_path / "retention-index.json"
    path.write_bytes(_raw(envelope if envelope is not None else _retention_envelope()))
    return path


def _run(matrix, tmp_path, **kwargs):
    roots, anchor = matrix
    if "retention_index" not in kwargs:
        kwargs["retention_index"] = _retention_file(tmp_path)
    return Q.run(roots, tmp_path / "comparison", anchor=anchor, run_id="1234", attempt="1",
                 control_sha="c" * 40, modules=MODULES, candidate_source=ROOT, **kwargs)


def _mutate(root, name, change, *, seal=True):
    value = json.loads((root / name).read_text())
    change(value)
    (root / name).write_bytes(_raw(value))
    if seal:
        _seal(root)


def test_complete_four_cohorts_compare_original_policy_and_keep_causal_failures(matrix, tmp_path):
    roots, _ = matrix
    before = {str(path): path.read_bytes() for root in roots.values() for path in root.rglob("*") if path.is_file()}
    result = _run(matrix, tmp_path)
    assert result["execution_complete"] and result["scientific_comparison_pass"]
    assert not result["causal_required_all_pass"]
    assert result["pipeline_qualified"] is True
    assert result["retention"]["raw_publication_verified"] is True
    assert all(item["ok"] for item in result["original_decisions"].values())
    assert all(not item["ok"] for item in result["causal_required_decisions"].values())
    for value in result["comparisons"].values():
        assert value["status"] == "NO_REGRESSION"
        assert value["require_strict_regression"] and value["fail_on_regression"]
        assert not value["exploratory"] and not value["rebaseline_required"]
        assert value["cohort"]["unverified"] == []
    assert all(Path(path).read_bytes() == raw for path, raw in before.items())
    receipt = json.loads((tmp_path / "comparison/receipt.json").read_text())
    assert receipt["execution_complete"] and receipt["scientific_comparison_pass"]
    for name, record in receipt["files"].items():
        assert _record((tmp_path / "comparison" / name).read_bytes()) == record


def test_same_original_failures_do_not_become_qualification_from_no_regression(tmp_path):
    build_raw = _raw(_build())
    roots = {}
    for role in Q.ROLES:
        roots[role] = tmp_path / role
        _cohort(roots[role], role, build_raw, fail=True)
    result = _run((roots, _sha(build_raw)), tmp_path)
    assert result["execution_complete"] and not result["scientific_comparison_pass"]
    assert all(not decision["ok"] for decision in result["original_decisions"].values())
    assert all(value["status"] == "NO_REGRESSION" for value in result["comparisons"].values())
    assert "one or more original strict gates failed" in result["unqualified_reasons"]


@pytest.mark.parametrize("change", [
    lambda result: result.update(execution_complete=False),
    lambda result: result.update(identities_stable=False),
    lambda result: result.update(source_sha=Q.BASELINE),
    lambda result: result["expected"].update(seed_count=99),
    lambda result: result.update(gate_pass=False),
    lambda result: result.update(gate_exit_code=2),
    lambda result: result.update(finalization_error="synthetic late copy failure"),
    lambda result: result.update(receipt_recovery_errors=["synthetic negative receipt write failure"]),
])
def test_incomplete_wrong_source_or_forged_gate_receipts_fail_before_output(matrix, tmp_path, change):
    _mutate(matrix[0]["procedural-candidate"], "result.json", change, seal=False)
    with pytest.raises(Q.ComparisonInputError):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


@pytest.mark.parametrize("name,change", [
    ("provenance.json", lambda p: p.update(github_run_id="another-run")),
    ("provenance.json", lambda p: p["after"]["environment"]["thread_env"].update(OMP_NUM_THREADS="2")),
    ("provenance.json", lambda p: p["after"]["native"].update(sha256="9" * 64)),
    ("provenance.json", lambda p: p["before"]["native"]["schemas"]["AgentSimulator"].update(version=2)),
    ("provenance.json", lambda p: p.update(source_snapshot_after_sha256="9" * 64)),
    ("provenance.json", lambda p: p["after"]["source"].update(package_digest="9" * 64)),
    ("build-manifest.json", lambda p: p["wheel"].update(sha256="9" * 64)),
])
def test_runtime_source_schema_and_external_builder_anchors_cannot_be_waived(matrix, tmp_path, name, change):
    _mutate(matrix[0]["template-candidate"], name, change)
    with pytest.raises(Q.ComparisonInputError):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_duplicate_fork_is_rejected_even_after_all_light_and_raw_hashes_are_resealed(matrix, tmp_path):
    root = matrix[0]["procedural-candidate"]
    _mutate(root, "report/ablation_manifest.json",
            lambda value: value["forks"].__setitem__(1, deepcopy(value["forks"][0])), seal=False)
    _reseal_reports(root)
    with pytest.raises(Q.ComparisonInputError, match="duplicate"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


@pytest.mark.parametrize("kind", ["missing", "extra", "changed", "symlink", "hardlink", "nested-root", "existing-output", "input-output"])
def test_missing_changed_aliased_or_overwriting_paths_are_rejected(matrix, tmp_path, kind):
    roots, anchor = matrix
    path = roots["template-baseline"] / "report/gate_summary_full.md"
    output = tmp_path / "comparison"
    if kind == "missing":
        path.unlink()
    elif kind == "extra":
        (roots["template-baseline"] / "unexpected.json").write_text("{}")
    elif kind == "changed":
        path.write_text("changed")
    elif kind == "symlink":
        path.unlink()
        path.symlink_to(roots["template-candidate"] / "report/gate_summary_full.md")
    elif kind == "hardlink":
        path.unlink()
        path.hardlink_to(roots["template-candidate"] / "report/gate_summary_full.md")
    elif kind == "nested-root":
        roots = {**roots, "template-candidate": roots["template-baseline"] / "report"}
    elif kind == "existing-output":
        output.mkdir()
        (output / "preserve.txt").write_text("preserve")
    elif kind == "input-output":
        output = roots["template-baseline"] / "derived"
    with pytest.raises(Q.ComparisonInputError):
        Q.run(roots, output, anchor=anchor, run_id="1234", attempt="1",
              control_sha="c" * 40, modules=MODULES, candidate_source=ROOT)
    if kind == "existing-output":
        assert (output / "preserve.txt").read_text() == "preserve"
    else:
        assert not output.exists()


def test_bounds_reject_before_attempting_a_large_read(matrix, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "MAX_ROOT_BYTES", 1)
    def forbidden_read(*args, **kwargs):
        raise AssertionError("aggregate byte admission must reject before opening")
    monkeypatch.setattr(Q, "_read", forbidden_read)
    with pytest.raises(Q.ComparisonInputError, match="bound"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_inputs_are_rechecked_after_analysis_before_output(matrix, tmp_path, monkeypatch):
    original = Q.analyze

    def change_after_analysis(cohorts, modules):
        result = original(cohorts, modules)
        (matrix[0]["template-baseline"] / "report/gate_summary_full.md").write_text("changed late")
        return result

    monkeypatch.setattr(Q, "analyze", change_after_analysis)
    with pytest.raises(Q.ComparisonInputError, match="unchanged input"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_frozen_reader_bootstrap_requires_detached_exact_candidate(tmp_path):
    candidate = tmp_path / "candidate"
    (candidate / ".git").mkdir(parents=True)
    (candidate / ".git/HEAD").write_text(Q.BASELINE + "\n")
    with pytest.raises(Q.ComparisonInputError, match="detached candidate"):
        Q.frozen_modules(candidate)


def test_frozen_reader_bootstrap_rejects_changed_reader_code_before_import(tmp_path):
    candidate = tmp_path / "candidate"
    (candidate / ".git").mkdir(parents=True)
    (candidate / ".git/HEAD").write_text(Q.CANDIDATE + "\n")
    first = next(iter(Q.FROZEN_FILES))
    path = candidate / first
    path.parent.mkdir(parents=True)
    path.write_text("changed source\n")
    with pytest.raises(Q.ComparisonInputError, match="frozen reader file"):
        Q.frozen_modules(candidate)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":1e9999}', b'{"x":NaN}'])
def test_ambiguous_or_nonfinite_artifact_json_is_rejected(raw):
    with pytest.raises(Q.ComparisonInputError):
        Q._json(raw, "synthetic artifact")

def test_self_consistent_smoke_artifacts_cannot_be_used_as_full_cohorts(tmp_path):
    build_raw = _raw(_build())
    roots = {}
    before = {}
    for role in Q.ROLES:
        roots[role] = tmp_path / role
        _cohort(roots[role], role, build_raw, smoke=True)
        index = json.loads((roots[role] / "artifact-index.json").read_text())
        for name, record in index["files"].items():
            assert _record((roots[role] / name).read_bytes()) == record
        for path in roots[role].rglob("*"):
            if path.is_file():
                before[str(path)] = path.read_bytes()
    with pytest.raises(Q.ComparisonInputError, match="kind"):
        _run((roots, _sha(build_raw)), tmp_path)
    assert not (tmp_path / "comparison").exists()
    assert all(Path(path).read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("source", ["parent", "fork"])
def test_missing_raw_validation_link_cannot_be_hidden_by_resealed_light_hashes(matrix, tmp_path, source):
    root = matrix[0]["template-baseline"]
    raw = json.loads((root / "raw-inventory.json").read_text())
    prefix = "raw/full_gate/batch_42/seed_42/" if source == "parent" else "raw/full_gate/ablation_42/needs/seed_42/fork_100/"
    del raw["files"][prefix + ("validation_needs.arrow" if source == "parent" else "fork.json")]
    raw["file_count"] = len(raw["files"])
    raw["total_bytes"] = sum(value["bytes"] for value in raw["files"].values())
    (root / "raw-inventory.json").write_bytes(_raw(raw))
    _seal(root)
    with pytest.raises(Q.ComparisonInputError, match="raw validation input is missing"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


@pytest.mark.parametrize("setting,value", [("finance", False), ("governance", False),
                                          ("agent_scale_mode", "fast"), ("tuning_overrides", {"x": 1})])
def test_omitted_defaults_cannot_be_replaced_by_shared_explicit_overrides(matrix, tmp_path, setting, value):
    for root in matrix[0].values():
        # Same override everywhere; all links and original decisions stay coherent.
        _mutate(root, "report/batch_manifest.json",
                lambda b: b["simulation"].update({setting: value}), seal=False)
        if setting in Q.FEATURE_ARGUMENTS:
            _mutate(root, "report/run_manifest.json", lambda r: r.update({setting: value}), seal=False)
        _reseal_reports(root)
    with pytest.raises(Q.ComparisonInputError, match="registered simulation configuration"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


@pytest.mark.parametrize("oracle,version", [("needs", 7), ("cohort", 5), ("community", True)])
def test_old_or_aliased_methods_cannot_be_rebaselined(matrix, tmp_path, oracle, version):
    root = matrix[0]["template-candidate"]
    _mutate(root, "report/validate_report_full.json",
            lambda r: r["results"][oracle].update(method_version=version), seal=False)
    _reseal_reports(root)
    with pytest.raises(Q.ComparisonInputError, match="method"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_missing_core_parent_sidecar_cannot_be_hidden_by_complete_counts(matrix, tmp_path):
    root = matrix[0]["template-baseline"]
    _mutate(root, "report/batch_manifest.json",
            lambda b: b["runs"][0]["files"].pop("seed_42/validation_needs.arrow"), seal=False)
    _reseal_reports(root)
    with pytest.raises(Q.ComparisonInputError, match="parent validation hashes"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_known_oversize_artifact_is_refused_before_open(matrix, tmp_path):
    path = matrix[0]["template-baseline"] / "report/gate_summary_full.md"
    with path.open("wb") as stream:
        stream.truncate(Q.MAX_FILE_BYTES + 1)
    with pytest.raises(Q.ComparisonInputError, match="byte bound"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()


def test_original_gates_and_no_regression_cannot_hide_one_missing_raw_archive(matrix, tmp_path):
    path = _retention_file(tmp_path, _retention_envelope(remove=0))
    result = _run(matrix, tmp_path, retention_index=path)
    assert result["scientific_comparison_pass"]
    assert all(decision["ok"] for decision in result["original_decisions"].values())
    assert all(value["status"] == "NO_REGRESSION" for value in result["comparisons"].values())
    assert result["pipeline_qualified"] is False
    assert not result["retention"]["raw_publication_verified"]
    assert len(result["retention"]["missing"]) == 1


@pytest.mark.parametrize("kind", ["omitted", "api-failure", "invalid-json", "wrong-run"])
def test_unknown_or_invalid_retention_preserves_science_but_never_qualifies_pipeline(matrix, tmp_path, kind):
    if kind == "omitted":
        path = None
    else:
        envelope = _retention_envelope()
        if kind == "api-failure":
            envelope.update(complete=False, error="artifact metadata request failed")
        elif kind == "wrong-run":
            envelope["github_run_id"] = "other-run"
        path = _retention_file(tmp_path, envelope)
        if kind == "invalid-json":
            path.write_text("{")
    result = _run(matrix, tmp_path, retention_index=path)
    assert result["scientific_comparison_pass"]
    assert result["pipeline_qualified"] is None
    assert "qualification_pass" not in result
    assert (tmp_path / "comparison/receipt.json").is_file()
    assert all(item["ok"] for item in result["original_decisions"].values())


@pytest.mark.parametrize("jobs", ["failure", "cancelled", "skipped", None])
def test_published_raw_archives_cannot_hide_unsuccessful_or_unknown_producers(matrix, tmp_path, jobs):
    result = _run(matrix, tmp_path,
                  retention_index=_retention_file(tmp_path, _retention_envelope(jobs=jobs)))
    assert result["scientific_comparison_pass"]
    assert result["retention"]["raw_publication_verified"]
    assert result["pipeline_qualified"] is (None if jobs is None else False)


@pytest.mark.parametrize("change", [
    lambda e: e.update(total_count=101),
    lambda e: e["artifacts"][0].update(digest=None),
    lambda e: e["artifacts"][0].update(expired=True),
    lambda e: e["artifacts"][0].update(expires_at="2020-01-01T00:00:00+00:00"),
    lambda e: e["artifacts"][0].update(size_in_bytes=0),
    lambda e: e["artifacts"][0]["workflow_run"].update(head_sha="9" * 40),
    lambda e: e["artifacts"][0]["workflow_run"].update(id=999),
    lambda e: e["artifacts"][1].update(id=e["artifacts"][0]["id"]),
])
def test_invalid_archive_metadata_is_not_publication_evidence(change):
    envelope = _retention_envelope()
    change(envelope)
    # Reseal the exact raw API body too, so semantic checks are exercised.
    response = {"total_count": envelope["total_count"], "artifacts": envelope["artifacts"]}
    envelope["raw_response"] = json.dumps(response)
    envelope["raw_response_sha256"] = _sha(envelope["raw_response"].encode())
    with pytest.raises(Q.ComparisonInputError):
        Q.validate_retention(envelope, run_id="1234", attempt="1", control_sha="c" * 40)


def test_missing_retention_makes_cli_nonzero_while_retaining_scientific_readout(matrix, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "frozen_modules", lambda root: MODULES)
    args = ["--candidate-source", str(ROOT), "--build-manifest-sha256", matrix[1],
            "--control-sha", "c" * 40, "--github-run-id", "1234", "--github-run-attempt", "1",
            "--output", str(tmp_path / "comparison")]
    for role, path in matrix[0].items():
        args += ["--" + role, str(path)]
    assert Q.main(args) != 0
    result = json.loads((tmp_path / "comparison/comparison.json").read_text())
    assert result["scientific_comparison_pass"] and result["pipeline_qualified"] is None


def test_float_fork_seed_cannot_alias_a_registered_integer_after_raw_paths_are_resealed(matrix, tmp_path):
    root = matrix[0]["template-baseline"]
    ablation = json.loads((root / "report/ablation_manifest.json").read_text())
    row = ablation["forks"][0]
    old_directory = row["dir"]
    row.update(seed=42.0, run_dir="seed_42.0", dir="needs/seed_42.0/fork_100")
    (root / "report/ablation_manifest.json").write_bytes(_raw(ablation))
    inventory = json.loads((root / "raw-inventory.json").read_text())
    for name in ("agent_events.arrow", "fork.json"):
        before = "raw/full_gate/ablation_42/" + old_directory + "/" + name
        after = "raw/full_gate/ablation_42/" + row["dir"] + "/" + name
        inventory["files"][after] = deepcopy(inventory["files"][before])
    inventory["file_count"] = len(inventory["files"])
    inventory["total_bytes"] = sum(v["bytes"] for v in inventory["files"].values())
    (root / "raw-inventory.json").write_bytes(_raw(inventory))
    _reseal_reports(root)
    with pytest.raises(Q.ComparisonInputError, match="fork seed must be an integer"):
        _run(matrix, tmp_path)
    assert not (tmp_path / "comparison").exists()
