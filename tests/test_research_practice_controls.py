"""Pure source, boundary and metadata fixtures; never execute a study mode."""
import ast
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def controls(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return tuple(importlib.import_module(name) for name in (
        "research_practice_contract", "run_research_practice_continuation",
        "read_research_practice_continuation", "research_practice_trace_reader",
        "fetch_research_practice_wheel"))


def test_qualified_process_accounting_and_reader_transactions_keep_exact_asts():
    proof = json.loads((ROOT / "tests/fixtures/research_practice_control_source.json").read_bytes())
    assert proof["original_control"] == "3caa9a9c2eb07a20bcb83491ca81bca956bf0725"
    assert proof["canonical_ast_options"]["show_empty"] is True
    checked = 0
    for file, expected in proof["functions"].items():
        functions = {node.name: node for node in ast.parse((ROOT / "scripts" / file).read_bytes()).body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name, digest in expected.items():
            actual = ast.dump(functions[name], **proof["canonical_ast_options"])
            assert hashlib.sha256(actual.encode()).hexdigest() == digest, (file, name)
            checked += 1
    assert checked == 31
    assert hashlib.sha256((ROOT / "scripts/research_practice_resources.py").read_bytes()).hexdigest() == proof["resource_helper_sha256"]


@pytest.mark.parametrize("role,enabled", [("parent", True), ("active", True), ("pause_new_trials", False)])
def test_boundary_harvest_is_not_a_checkpoint_intervention(controls, tmp_path, role, enabled):
    c, runner, *_ = controls
    world, calls = NS(turn=61), []
    owner = NS(role=role, record_turn_end=lambda received: calls.append(received) or {"truthy": True})
    boundary = runner.BoundaryCapture(tmp_path, {}, owner, parent=role == "parent")
    config = dict(simulation_args=dict(scientific_research_agendas=enabled),
                  expansion_experiment=dict(controls_after=dict(c.CONTROLS)))
    boundary.bind(None, config)
    assert boundary.turn_end(world) is False and calls == [world] and not boundary.captured
    assert boundary.live_record() is None


def test_parent_cp60_retains_harvest_then_real_checkpoint_rng_order(controls, tmp_path, monkeypatch):
    c, runner, *_ = controls
    calls, world = [], NS(turn=60, seed=2001)
    owner = NS(role="parent", record_turn_end=lambda received: calls.append("harvest") or {"truthy": True})
    frozen = dict(runtime={"fixed": True}, controls={"registered": "hash"})
    boundary = runner.BoundaryCapture(tmp_path, frozen, owner, parent=True)
    monkeypatch.setattr(c, "checkpoint_sections", lambda path: (calls.append("checkpoint") or dict(turn=60, seed=2001, exact=True), {}))
    monkeypatch.setattr(c, "sha", lambda path: "actual-checkpoint-sha")
    monkeypatch.setattr(runner, "rng_state", lambda: calls.append("rng") or {"actual": "state"})
    original_write = c.write
    monkeypatch.setattr(c, "write", lambda path, value: (calls.append("write"), original_write(path, value))[-1])
    assert boundary.turn_end(world) is False and boundary.captured
    assert calls == ["harvest", "checkpoint", "rng", "write", "rng"]
    saved = c.read(tmp_path / "boundary-rng.json")
    assert saved["turn"] == 60 and saved["checkpoint_sha256"] == "actual-checkpoint-sha"


@pytest.mark.parametrize("disk,ram,admission,passes", [
    (6, 2, True, True), (5, 2, True, False), (6, 1, True, False),
    (3, 1, False, True), (2, 1, False, False), (3, 0, False, False),
])
def test_original_disk_and_ram_floors_remain_distinct_without_probes(controls, tmp_path, monkeypatch, disk, ram, admission, passes):
    c, runner, *_ = controls
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda path: NS(free=disk*1024**3))
    monkeypatch.setattr(runner, "memory_available", lambda: dict(available=ram*1024**3, fixture=True))
    if passes:
        observed = runner.resources(tmp_path, admission=admission)
        assert observed["evidence_files"] == observed["evidence_bytes"] == 0
    else:
        with pytest.raises(c.ContractError):
            runner.resources(tmp_path, admission=admission)
    assert (c.AGGREGATE_CPU, c.WORKER_CPU, c.AGGREGATE_WALL, c.WORKER_WALL) == (900, 90, 1800, 900)
    assert (c.MAX_FILES, c.MAX_BYTES) == (5000, 2*1024**3)


def test_closed_new_policy_preserves_all_seeds_and_frozen_producer(controls):
    c, runner, _, _, fetch = controls
    selected = c.P.policy()
    assert c.SEEDS == tuple(range(2000, 2008)) and c.ROLES == ("parent", "active", "pause_new_trials")
    assert sum(c.END if role == "parent" else c.END-c.FORK for seed in c.SEEDS for role in c.ROLES) == 3360
    assert c.SOURCE == selected["producer_sha"] == "cbf6e368ebd218c1f54179bee4accffc1ab2a4c0"
    assert c.P.NAMES == ("cloud-cbf-3ee",)
    assert selected["artifact"]["id"] == 12882944002 and selected["artifact"]["run_id"] == 40841527996
    assert selected["native_sha256"] == "3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0"
    assert fetch.endpoint().endswith("/actions/artifacts/12882944002")
    assert fetch.run_endpoint().endswith("/actions/runs/40841527996")
    for invalid in ("local-fb20", "cloud-fullgate-06db", "arbitrary", None):
        with pytest.raises(ValueError):
            c.P.policy(invalid)
    selected["artifact"]["id"] = 0
    assert c.P.policy()["artifact"]["id"] == 12882944002
    assert all((ROOT / name).is_file() for name in c.control_files())
    assert not any(name.endswith(".yml") for name in c.control_files())


def producer_fixture(c):
    a = c.P.policy()["artifact"]
    return dict(id=a["run_id"], head_sha=a["control_sha"], head_branch=a["branch"],
                status="completed", conclusion="success", run_attempt=1, event="workflow_dispatch",
                path=".github/workflows/tests.yml", repository=dict(full_name=a["repository"]))


@pytest.mark.parametrize("fault", ["source", "package", "native", "schema", "python", "affinity", "thread"])
def test_prospective_runtime_accepts_only_exact_actual_metadata(controls, fault):
    c, *_ = controls
    selected = c.P.policy()
    threads = {name: "1" for name in c.THREADS}
    threads.update(PYTHON_CPU_COUNT="1", PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
    actual = dict(source=dict(git_sha=c.SOURCE, package_digest=selected["package_digest"]),
        native=dict(status="found", sha256=selected["native_sha256"], bytes=selected["native_bytes"], module_file="/fixture/native.so"),
        compiled_origin="/fixture/native.so", available_compiled_classes=deepcopy(selected["schemas"]),
        environment=dict(python="3.13.17", implementation="CPython", platform="Linux-fixture", machine="x86_64",
                         affinity_cpu_count=1, packages=deepcopy(selected["packages"]), thread_env=threads))
    assert c.P.validate_runtime(c.P.DEFAULT_POLICY, actual, c.same) == selected
    if fault in ("source", "package"):
        actual["source"]["git_sha" if fault == "source" else "package_digest"] = "wrong"
    elif fault == "native":
        actual["native"]["sha256"] = "0"*64
    elif fault == "schema":
        actual["available_compiled_classes"]["AgentSimulator"]["version"] = True
    elif fault == "python":
        actual["environment"]["python"] = "3.13.5"
    elif fault == "affinity":
        actual["environment"]["affinity_cpu_count"] = True
    else:
        actual["environment"]["thread_env"]["OMP_NUM_THREADS"] = "2"
    with pytest.raises(ValueError):
        c.P.validate_runtime(c.P.DEFAULT_POLICY, actual, c.same)


@pytest.mark.parametrize("field,value", [("id", 0), ("head_sha", "different"), ("head_branch", "main"),
    ("status", "in_progress"), ("conclusion", "failure"), ("run_attempt", True),
    ("event", "push"), ("path", "another.yml"), ("repository", {"full_name": "other/repo"})])
def test_fixed_completed_producer_rejects_each_wrong_fact(controls, field, value):
    c, _, _, _, fetch = controls
    fixture = producer_fixture(c)
    assert fetch.producer_contract(fixture, c.P.policy()["artifact"])["conclusion"] == "success"
    fixture[field] = value
    with pytest.raises(c.ContractError):
        fetch.producer_contract(fixture, c.P.policy()["artifact"])


def test_worker_source_routes_public_observer_once_and_late_harvest_has_no_new_physics():
    tree = ast.parse((ROOT / "scripts/run_research_practice_continuation.py").read_bytes())
    worker = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "worker")
    calls = [n for n in ast.walk(worker) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "main" and n.func.attr == "execute_run"]
    assert len(calls) == 1 and {k.arg for k in calls[0].keywords} == {"checkpoint_resume", "expansion_experiment", "turn_boundary", "practice_observer"}
    assert next(k.value for k in calls[0].keywords if k.arg == "practice_observer").id == "owner"
    boundary = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BoundaryCapture")
    turn_end = next(n for n in boundary.body if isinstance(n, ast.FunctionDef) and n.name == "turn_end")
    assert isinstance(turn_end.body[0], ast.Expr) and ast.unparse(turn_end.body[0].value) == "self.owner.record_turn_end(world)"
    assert isinstance(turn_end.body[-1], ast.Return) and turn_end.body[-1].value.value is False


@pytest.mark.parametrize("files,size,extra,passes", [
    (4999, 0, {"receipt": {"bytes": 1}}, True),
    (5000, 0, {"receipt": {"bytes": 1}}, False),
    (0, 2*1024**3-1, {"receipt": {"bytes": 1}}, True),
    (0, 2*1024**3, {"receipt": {"bytes": 1}}, False),
])
def test_readout_counts_against_same_global_evidence_caps(controls, files, size, extra, passes):
    c, _, reader, *_ = controls
    raw = dict(evidence_files=files, evidence_bytes=size)
    if passes:
        assert reader.combined_evidence_budget(raw, extra) == dict(evidence_files=files+1, evidence_bytes=size+1)
    else:
        with pytest.raises(c.ContractError, match="combined"):
            reader.combined_evidence_budget(raw, extra)


def test_trace_exemption_is_exact_top_level_path_not_arbitrary_basename(controls):
    _, _, reader, *_ = controls
    assert "practice-trace.jsonl" not in reader.OBSERVER_FILES
    ordinary = reader.ordinary({"nested/practice-trace.jsonl": {"bytes": 1}, "state.json": {"bytes": 2}})
    assert set(ordinary) == {"nested/practice-trace.jsonl", "state.json"}


def test_preexecution_refusal_retains_all_eight_unknown_rows(controls):
    c, _, reader, *_ = controls
    result = reader.refusal_result(ValueError("fixture admission refusal"))
    assert not result["mechanics_verified"] and result["scientific_standing"] == "refused"
    assert [row["seed"] for row in result["seeds"]] == list(c.SEEDS)
    assert all(row["exposure"] == {} and row["practice_trace"] == {} and not row["paired"] for row in result["seeds"])
    rendered = reader.markdown(result)
    assert all(str(seed) in rendered for seed in c.SEEDS) and rendered.count("unknown") == 8*5
