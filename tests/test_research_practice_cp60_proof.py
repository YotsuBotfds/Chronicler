"""Scalar/metadata/source fixtures only; never run proof modes or a real World."""
import ast
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import pickle
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest
import yaml

from test_research_practice_trace_reader import frame

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/research-practice-cp60-proof.yml"
BRANCH = "lead/cloud-practice-cp60-proof-20261029"
ACTIVE_GUARD = "${{ github.event_name == 'push' && github.ref == 'refs/heads/"+BRANCH+"' && github.run_attempt == 1 }}"
PREPARED_GUARD = "${{ false && github.event_name == 'push' && github.ref == 'refs/heads/"+BRANCH+"' && github.run_attempt == 1 }}"
WORKFLOW_BODY_SHA256 = "5d50bdda3f7913d728a17ab600e9ce9cc5141f895bc1cd990c6f43db0dbd79b5"


@pytest.fixture
def proof(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("run_research_practice_cp60_proof")


class Observer:
    def __init__(self, module, *, error=None, unavailable=False):
        self.module, self.error, self.unavailable = module, error, unavailable
        self.calls, self.closes, self.source = 0, 0, None

    def run_turn_result(self, world, *args, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        self.source = world.turn
        advance(world)
        return NS(observation=NS(source_turn=self.source, completed_turn=world.turn))

    def read_latest(self, *, expected_source_turn):
        assert expected_source_turn == self.source
        return frame(self.module.T, self.source, self.calls, captured=not self.unavailable)

    def close(self):
        self.closes += 1


def advance(world):
    # Scalar surrogate, deliberately consumes caller RNG once like a caller.
    random.random()
    np.random.random()
    world.scientific_claims.effort_spent += world.turn == 61
    world.turn += 1


def world(module, role, *, effort=9):
    return NS(seed=module.SEED, turn=0 if role == "parent" else 60,
              scientific_claims=NS(effort_spent=effort))


def complete(module, folder, role):
    folder.mkdir()
    observed = Observer(module) if role != "none" else None
    owner = module.ProofOwner(folder, role, observed, checkpoint_effort=None if role == "parent" else 9)
    value = world(module, role)
    if observed is None:
        owner.begin(value, "actual restored World alias after normal configure at Boundary.bind")
    while value.turn < module.END:
        if observed is None:
            advance(value)
        else:
            result = owner.run_turn_result(value, marker="forwarded")
            assert result.observation.completed_turn == value.turn
        owner.record_turn_end(value)
    report = owner.finish()
    owner.close()
    return owner, observed, value, report


@pytest.mark.parametrize("role", ("parent", "none", "observed"))
def test_fixed66_scope_two_frames_and_actual_nonzero_baseline(proof, tmp_path, role):
    before = proof.R.rng_state()
    try:
        owner, observer, value, report = complete(proof, tmp_path / role, role)
        assert value.turn == 62 and report["actual_physics_ticks"] == (62 if role == "parent" else 2)
        assert report["kind"] == "practice-cp60-two-source-observation"
        assert report["initial_effort_spent"] == 9 and report["final_effort_spent"] == 10
        assert [row["source_turn"] for row in report["counters"]] == [60, 61]
        assert report["counters"][1] == dict(source_turn=61, before=9, after=10, delta=1)
        assert report["capture_enabled"] is (role != "none")
        assert len(report["frames"]) == (0 if role == "none" else 2)
        assert len(list((tmp_path / role).iterdir())) == 2
        assert not (tmp_path / role / "practice-trace-index.json").exists()
        assert proof.T.END == proof.C.END == 180 and proof.C.SEEDS == tuple(range(2000, 2008))
        assert not any(value is retained for retained in vars(owner).values())
        if observer:
            assert observer.calls == (62 if role == "parent" else 2) and observer.closes == 1
            assert [row["frame"]["attempt"] for row in report["frames"]] == ([61, 62] if role == "parent" else [1, 2])
            payments = report["frames"][1]["frame"]["rows"][:2]
            assert payments[1]["allowance"] > 0 and payments[1]["payments"][0]["bookkeeping_paid"] == 0
            assert report["frames"][1]["accounting"]["delta"] == 1
            assert all(not row["payments"][0]["event_id"] for row in payments)
        with pytest.raises(TypeError, match="transient"):
            pickle.dumps(owner)
    finally:
        proof.R.restore_rng(before)


def test_observed_none_surrogates_preserve_rng_and_actual_counter_handoff(proof, tmp_path):
    initial = proof.R.rng_state()
    try:
        _, _, left, a = complete(proof, tmp_path / "none", "none")
        after = proof.R.rng_state()
        proof.R.restore_rng(initial)
        _, _, right, b = complete(proof, tmp_path / "observed", "observed")
        assert proof.C.same(after, proof.R.rng_state())
        assert vars(left) == vars(right) and a["counters"] == b["counters"]
    finally:
        proof.R.restore_rng(initial)


@pytest.mark.parametrize("error", [ValueError("capture"), KeyboardInterrupt(), SystemExit(2)])
def test_failed_or_cancelled_observer_never_replays_physics(proof, tmp_path, error):
    observer = Observer(proof, error=error)
    owner = proof.ProofOwner(tmp_path, "observed", observer, checkpoint_effort=9)
    value = world(proof, "observed")
    with pytest.raises(type(error)):
        owner.run_turn_result(value)
    with pytest.raises(ValueError):
        owner.run_turn_result(value)
    assert observer.calls == 1 and value.turn == 60 and owner.failed
    owner.close()


def test_bind_none_uses_actual_configured_loaded_world_and_preserves_false_flag(proof, tmp_path):
    actual = world(proof, "none", effort=11)
    loaded = NS(exact=True, mismatches=[], state=NS(world=actual))
    owner = proof.ProofOwner(tmp_path, "none", None, checkpoint_effort=11)
    boundary = proof.ProofBoundary(tmp_path, {}, owner, loaded)
    config = dict(simulation_args=dict(scientific_research_agendas=True),
                  expansion_experiment=dict(controls_after=dict(proof.C.CONTROLS)))
    boundary.bind(None, config)
    assert owner.baseline["initial_effort_spent"] == 11
    actual.turn += 1
    assert boundary.turn_end(actual) is False
    assert owner.counters[0]["before"] == 11 and owner.counters[0]["delta"] == 0
    with pytest.raises(ValueError, match="actual restored World alias"):
        boundary.turn_end(deepcopy(actual))


@pytest.mark.parametrize("fault", ["counter", "source", "seed", "reused_owner", "metadata_cancel"])
def test_prephysics_refusal_never_calls_observer(proof, tmp_path, monkeypatch, fault):
    observer = Observer(proof)
    owner = proof.ProofOwner(tmp_path, "observed", observer, checkpoint_effort=9)
    value = world(proof, "observed")
    expected = ValueError
    if fault == "counter":
        value.scientific_claims.effort_spent = 8
    elif fault == "source":
        value.turn = 62
    elif fault == "seed":
        value.seed = 2000
    elif fault == "reused_owner":
        owner.begin(value, "fixture")
        value = deepcopy(value)
    else:
        def fail(*args):
            raise KeyboardInterrupt
        monkeypatch.setattr(proof, "write_small", fail)
        expected = KeyboardInterrupt
    with pytest.raises(expected):
        owner.run_turn_result(value)
    assert observer.calls == 0 and owner.failed
    owner.close()


def test_unavailable_postcp_capture_and_incomplete_finish_remain_negative(proof, tmp_path):
    before = proof.R.rng_state()
    observer = Observer(proof, unavailable=True)
    owner = proof.ProofOwner(tmp_path, "observed", observer, checkpoint_effort=9)
    value = world(proof, "observed")
    try:
        owner.run_turn_result(value)
        with pytest.raises(ValueError, match="frame unavailable"):
            owner.record_turn_end(value)
        with pytest.raises(ValueError):
            owner.finish()
        assert owner.failed and observer.calls == 1 and value.turn == 61
        assert not (tmp_path / "proof-observation.json").exists()
    finally:
        owner.close()
        proof.R.restore_rng(before)


def test_metadata_byte_ceiling_refuses_before_file_write(proof, tmp_path):
    with pytest.raises(ValueError, match="ceiling"):
        proof.write_small(tmp_path / "too-big", {"value": "x"*(256*1024)})
    assert list(tmp_path.iterdir()) == []


def test_outer_publication_teardown_transaction_is_exact_qualified_source(proof):
    current = ast.parse((ROOT / "scripts/run_research_practice_cp60_proof.py").read_bytes())
    original = ast.parse((ROOT / "scripts/run_research_practice_continuation.py").read_bytes())
    left = next(n for n in current.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    right = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    changes = 0
    for node in ast.walk(left):
        if isinstance(node, ast.Name) and node.id == "_proof_run":
            node.id = "_run"
            changes += 1
    assert changes == 1
    options = dict(annotate_fields=True, include_attributes=False, indent=None, show_empty=True)
    assert ast.dump(left, **options) == ast.dump(right, **options)
    assert proof.exclusive_subreaper is proof.R.exclusive_subreaper
    assert proof.interruption_guard is proof.R.interruption_guard


def fake_controller(proof, tmp_path, monkeypatch, fault=None):
    root, source = tmp_path / "outputs", tmp_path / "producer"
    source.mkdir()
    freeze = tmp_path / "freeze.json"
    proof.C.write(freeze, {"fixture": True})
    frozen = dict(runtime={"fixture": "metadata only"}, control=dict(git_sha="fixture-source"))
    proof.C.write(tmp_path / "proof-metadata-observation.json",
                  dict(runtime=frozen["runtime"], source_bound_schema_class_calls=3))
    launches, cleaned = [], []
    def verified(*args):
        if fault == "source":
            raise ValueError("fixture source identity refusal")
        return frozen
    def resources(path, admission=False):
        if fault == "heavy" and (root / "execution.json").exists():
            raise ValueError("fixture expiry after serialization")
        if fault == "commit" and (root / "execution-receipt.json").exists():
            raise ValueError("fixture expiry during receipt commit")
        return dict(free_disk=9*1024**3, memory=dict(available=3*1024**3), evidence_bytes=0, evidence_files=0)
    class Child:
        def __init__(self, command, **kwargs):
            role = command[command.index("--role")+1]
            assert command[2] == str(proof.SCRIPT) and "--seed" not in command
            assert kwargs["start_new_session"] is True and kwargs["close_fds"] is True
            launches.append(role)
            self.role, self.pid = role, 100+len(launches)
    def supervise(child, *args):
        proof.C.write(root / child.role / "worker-summary.json", dict(execution_complete=True,
            actual_physics_ticks=62 if child.role == "parent" else 2))
        return dict(returncode=3 if fault == "worker" and child.role == "none" else 0,
                    tree_cpu_seconds=.01, accounting="scalar process fixture")
    def compared(root, source, role, frozen):
        if fault == "identity" and role == "none":
            raise ValueError("fixture ordinary identity failure")
        return {"fixture_identity": True}
    monkeypatch.setattr(proof.R, "verify_freeze", verified)
    monkeypatch.setattr(proof.R, "resources", resources)
    monkeypatch.setattr(proof.R, "process_record", lambda pid: dict(pgrp=pid, session=pid, start_ticks=pid*100))
    monkeypatch.setattr(proof.R, "supervise", supervise)
    monkeypatch.setattr(proof.R, "cleanup", lambda child, known: cleaned.append(child.role))
    monkeypatch.setattr(proof, "inspect_role", lambda *args: {"fixture_inspection": True})
    monkeypatch.setattr(proof, "compare", compared)
    monkeypatch.setattr(proof, "subprocess", NS(Popen=Child, DEVNULL=-3, STDOUT=-2))
    real_path = Path
    monkeypatch.setattr(proof, "Path", lambda value: NS(read_text=lambda: "fixture-boot")
                        if str(value) == "/proc/sys/kernel/random/boot_id" else real_path(value))
    options = NS(source_root=str(source), output_root=str(root), freeze=str(freeze), wheel_receipt=str(tmp_path / "wheel.json"))
    return root, options, launches, cleaned


@pytest.mark.parametrize("fault,expected", [(None, ["parent", "none", "observed"]),
    ("source", []), ("worker", ["parent", "none"]), ("identity", ["parent", "none"])])
def test_three_role_sequence_stops_before_next_launch_on_any_failure(proof, tmp_path, monkeypatch, fault, expected):
    root, options, launches, cleaned = fake_controller(proof, tmp_path, monkeypatch, fault)
    code = proof._proof_run(options)
    assert launches == expected
    execution = proof.C.read(root / "execution.json")
    assert execution["expected_executions"] == 3 and execution["expected_physics_ticks"] == 66
    assert [row["role"] for row in execution["runs"]] == list(proof.ROLES)
    assert execution["execution_complete"] is (fault is None) and code == int(fault is not None)
    if fault:
        assert execution["actual_physics_ticks"] is None
        assert execution["runs"][-1]["status"] == "not_attempted_after_failure"
    else:
        assert execution["actual_physics_ticks"] == 66 and cleaned == list(proof.ROLES)


@pytest.mark.parametrize("fault", ["heavy", "commit"])
def test_proof_expiry_during_heavy_publication_or_final_commit_cannot_leave_positive_seal(proof, tmp_path, monkeypatch, fault):
    root, options, launches, _ = fake_controller(proof, tmp_path, monkeypatch, fault)
    with pytest.raises(ValueError, match="fixture expiry"):
        proof._proof_run(options)
    assert launches == list(proof.ROLES)  # No retry after the publication failure.
    assert not (root / "execution-receipt.json").exists()
    assert not (root / "execution.json").exists()
    assert (root / "incomplete-execution.json").is_file()
    assert (root / "progress-3.json").is_file()


def test_semantic_projection_keeps_native_cache_and_discards_only_pickle_hashes(proof, monkeypatch):
    helper = importlib.import_module("profile_ablation_writer_cadence")
    carried = {key: "0"*64 for key in ("world", "world_extras", "private_signals", "archives", "bridge_python",
        "memories", "history", "chronicle_entries", "era_reflections", "pending_injections", "economy_tracker")}
    monkeypatch.setattr(helper, "state_view", lambda state: dict(turn=62, carried=carried,
        native={"agent.0": dict(bytes=3, sha256="1"*64)}, memory_cache={"fixture": {}},
        python_pickle_sha256="discarded-python", memory_pickle_sha256="discarded-memory"))
    monkeypatch.setattr(proof.C, "sha", lambda path: proof.STATE_VIEW_SHA256)
    monkeypatch.setattr(proof.C, "git", lambda *args: (proof.STATE_VIEW_BLOB+"\n").encode())
    loaded = NS(state=NS(world=NS(), run_config={}, live=None))
    result = proof.decoded_projection(loaded)
    assert result["carried"] == carried and result["native"]["agent.0"]["bytes"] == 3
    assert result["memory_cache"] == {"fixture": {}} and result["transient_state_absent"]
    assert "discarded-" not in json.dumps(result) and "python_pickle_sha256" not in result
    loaded.state.practice_observer = object()
    with pytest.raises(ValueError, match="persisted"):
        proof.decoded_projection(loaded)


def test_source_metadata_and_checkpoint_gates_precede_world_or_trusted_decode(proof):
    tree = ast.parse((ROOT / "scripts/run_research_practice_cp60_proof.py").read_bytes())
    worker = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "worker")
    text = ast.unparse(worker)
    assert text.index("R.verify_freeze(") < text.index("from chronicler import main")
    decode = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == "decode")
    decoded_text = ast.unparse(decode)
    assert decoded_text.index("checked_checkpoint(") < decoded_text.index("value = read_checkpoint(path)")
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "read_checkpoint"
               for node in ast.walk(worker)) == 1
    assert "unstepped-parent-cp60-inspection-after-normal-run" in text
    assert "practice_observer=owner if observer is not None else None" in text
    freeze = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "metadata_freeze")
    calls = [ast.unparse(node.func) for node in ast.walk(freeze) if isinstance(node, ast.Call)]
    assert "cls.checkpoint_schema" in calls and "R.identity" in calls
    assert not any(name.endswith(("execute_run", "run_turn_result", "generate_world")) for name in calls)
    assert proof.SEED == 1999 and proof.FORK == 60 and proof.END == 62
    assert proof.ROLES == ("parent", "none", "observed")


class Column:
    null_count = 0
    def __init__(self, values):
        self.values = values
    def to_pylist(self):
        return self.values


class Batch:
    num_rows, num_columns = 8, 2
    schema = NS(names=["region_id", "alive_count"])
    def __init__(self, ids=None, counts=None):
        self.ids = list(range(8)) if ids is None else ids
        self.counts = [1]*8 if counts is None else counts
    def column(self, name):
        return Column(self.ids if name == "region_id" else self.counts)


@pytest.mark.parametrize("fault", ["empty", "duplicate", "bool_id", "bool_count", "float_count", "negative",
                                    "overflow", "null", "too_many", "wrong_name"])
def test_actual_live_table_contract_refuses_empty_untyped_or_unbounded_rows(proof, fault):
    batch = Batch()
    if fault == "empty":
        batch.counts = [0]*8
    elif fault == "duplicate":
        batch.ids[-1] = 0
    elif fault == "bool_id":
        batch.ids[0] = False
    elif fault in ("bool_count", "float_count", "negative", "overflow", "null"):
        batch.counts[0] = {"bool_count": True, "float_count": 1., "negative": -1,
                           "overflow": 2**32, "null": None}[fault]
    elif fault == "too_many":
        batch.num_rows = 9
        batch.column = lambda name: pytest.fail("unbounded table must be rejected before column export")
    else:
        batch.schema = NS(names=["wrong", "alive_count"])
    with pytest.raises(ValueError):
        proof.live_rows(batch)


@pytest.mark.parametrize("mutation", [None, "native", "python_rng", "numpy_rng", "snapshot_cache"])
def test_readonly_live_getter_retains_counts_and_refuses_any_payload_or_rng_advance(proof, tmp_path, monkeypatch, mutation):
    initial = proof.R.rng_state()
    class Simulator:
        raw = b"fake native payload; never a real pool"
        cache = False
        def checkpoint_state(self):
            return self.raw
        def snapshot_is_cached(self):
            return self.cache
        def get_region_populations(self):
            if mutation == "native":
                self.raw += b"changed"
            elif mutation == "python_rng":
                random.random()
            elif mutation == "numpy_rng":
                np.random.random()
            elif mutation == "snapshot_cache":
                self.cache = True
            return Batch(counts=[0, 2, 0, 0, 0, 0, 0, 3])
    sim = Simulator()
    loaded = NS(state=NS(world=NS(turn=60), agent_bridge=NS(_sim=sim)))
    native_hash = hashlib.sha256(sim.raw).hexdigest()
    monkeypatch.setattr(proof.R, "native_records", lambda *args: {"native.agent.0": dict(sha256=native_hash)})
    monkeypatch.setattr(proof.C, "git", lambda root, verb, name: (proof.LIVE_METHOD_SOURCES[name.removeprefix("HEAD:")][0]+"\n").encode())
    monkeypatch.setattr(proof.C, "sha", lambda path: "fixture-checkpoint-hash")
    frozen = dict(producer=dict(files={name: {"sha256": values[1]} for name, values in proof.LIVE_METHOD_SOURCES.items()}))
    try:
        if mutation:
            with pytest.raises(ValueError, match="changed"):
                proof.live_population(loaded, tmp_path / "fixture.ckpt", frozen)
        else:
            result = proof.live_population(loaded, tmp_path / "fixture.ckpt", frozen)
            assert result["in_bounds_live_count"] == 5 and result["alive_counts"] == [0, 2, 0, 0, 0, 0, 0, 3]
            assert result["native_payload_and_caller_rng_unchanged"] and result["world_turn"] == 60
            assert proof.C.same(initial, proof.R.rng_state())
    finally:
        proof.R.restore_rng(initial)


def checkpoint_fixture(proof, resumed=False):
    c, selected = proof.C, proof.C.P.policy()
    env = dict(python="3.13.17", implementation="CPython", machine="x86_64", affinity_cpu_count=1,
               thread_env={"PYTHONHASHSEED": "0"}, packages=selected["packages"])
    runtime = dict(source=dict(git_sha=c.SOURCE, package_digest=selected["package_digest"]),
        native=dict(status="found", sha256=selected["native_sha256"], bytes=selected["native_bytes"]),
        environment=env, available_compiled_classes=selected["schemas"])
    frozen = dict(runtime=runtime, control=dict(files={proof.REGISTRATION: {"sha256": "fixture-reg-sha"}}))
    receipt = dict(schema_version=1, experiment=proof.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm="parent", intervention_fork=False, applied_before_turn=0, seed=proof.SEED,
        parent_checkpoint=None, previous_experiment=None, controls_after=dict(c.CONTROLS),
        source=runtime["source"], native=runtime["native"],
        registration=dict(path=str(proof.CONTROL / proof.REGISTRATION), sha256="fixture-reg-sha"),
        research_policy=dict(before=dict(enabled=True, enabled_turn=0), after=dict(enabled=True, enabled_turn=0), requested_enabled=None))
    enabled = dict(scholarship=True, techniques=True, scientific_claims=True, scientific_research_agendas=True)
    disabled = dict(health_care=False, harvest_forecasts=False, ritual_gatherings=False, transaction_receipts=False)
    lineage = [dict(resumed_at=60, kind="checkpoint", exact=True)] if resumed else []
    identity_native = {**runtime["native"], "state_layouts": {kind: "v1:"+selected["schemas"][name]["fingerprint"]
        for name, kind in (("AgentSimulator", "agent"), ("EcologySimulator", "ecology"), ("PoliticsSimulator", "politics"))}}
    header = dict(turn=62, seed=1999, start_turn=0, num_turns=62, exact=True, flags={**enabled, **disabled},
        lineage=lineage, run_config=dict(lineage=lineage, resume_info=None, expansion_experiment=receipt,
            simulation_args=dict(agents="hybrid", worldgen="template", regions=8, civs=4, **enabled, **disabled)),
        identity=dict(source=runtime["source"], native=identity_native, environment={**env, "hash_seed": "0"}))
    return frozen, c.checkpoint_projection(header), {"python": {}, "native.agent.0": {}}


@pytest.mark.parametrize("resumed", [False, True])
def test_checked_envelope_accepts_only_declared_exact_source_lineage(proof, monkeypatch, resumed):
    frozen, header, sections = checkpoint_fixture(proof, resumed)
    monkeypatch.setattr(proof.C, "checkpoint_sections", lambda path: (header, sections))
    assert proof.checked_checkpoint("fixture.ckpt", frozen, turn=62, resumed=resumed) == (header, sections)


@pytest.mark.parametrize("fault", ["seed", "turn", "origin", "horizon", "exact", "lineage", "policy", "control",
    "native", "package", "schema", "affinity", "feature", "native_set", "registration", "research_clock"])
def test_checked_envelope_refuses_before_trusted_decode(proof, monkeypatch, fault):
    frozen, header, sections = checkpoint_fixture(proof)
    if fault in ("seed", "turn", "horizon", "exact"):
        header[{"horizon": "num_turns"}.get(fault, fault)] = False if fault == "exact" else 180
    elif fault == "origin":
        header["identity"]["source"]["git_sha"] = "c76-source"
    elif fault == "package":
        header["identity"]["source"]["package_digest"] = "other-package"
    elif fault == "native":
        header["identity"]["native"]["sha256"] = "other-native"
    elif fault == "schema":
        header["identity"]["native"]["state_layouts"]["agent"] = "v99:wrong"
    elif fault == "affinity":
        header["identity"]["environment"]["affinity_cpu_count"] = 2
    elif fault == "lineage":
        header["lineage"] = [dict(resumed_at=1, kind="checkpoint", exact=True)]
    elif fault == "policy":
        header["run_config"]["resume_info"] = {"kind": "experiment-fork"}
    elif fault == "control":
        header["run_config"]["expansion_experiment"]["controls_after"]["uninformative_tests"] = True
    elif fault == "feature":
        header["flags"]["health_care"] = True
    elif fault == "native_set":
        sections["native.ecology.0"] = {}
    elif fault == "registration":
        header["run_config"]["expansion_experiment"]["registration"]["sha256"] = "wrong"
    else:
        policy = header["run_config"]["expansion_experiment"]["research_policy"]
        policy["before"]["enabled_turn"] = policy["after"]["enabled_turn"] = False
    monkeypatch.setattr(proof.C, "checkpoint_sections", lambda path: (header, sections))
    with pytest.raises(ValueError):
        proof.checked_checkpoint("fixture.ckpt", frozen, turn=62, resumed=False)


def workflow_contract(value):
    value = deepcopy(value)
    if True in value:
        assert "on" not in value
        value["on"] = value.pop(True)
    assert value["on"] == {"push": {"branches": [BRANCH], "paths": [".github/workflows/research-practice-cp60-proof.yml"]}}
    job = value["jobs"]["cp60-proof"]
    assert (value["name"], job["if"]) in (
        ("Prepared fresh CP60 practice observer proof", PREPARED_GUARD),
        ("Fresh CP60 practice observer proof", ACTIVE_GUARD))
    value.pop("name")
    job.pop("if")
    assert hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == WORKFLOW_BODY_SHA256


def test_both_closed_prepared_and_future_exact_active_workflow_states():
    value = yaml.safe_load(WORKFLOW.read_bytes())
    workflow_contract(value)
    value["name"], value["jobs"]["cp60-proof"]["if"] = "Fresh CP60 practice observer proof", ACTIVE_GUARD
    workflow_contract(value)


@pytest.mark.parametrize("fault", ["branch", "path", "dispatch", "guard", "producer", "python", "caps", "raw_omission"])
def test_workflow_refuses_offpolicy_triggers_source_budget_or_publication(fault):
    value = yaml.safe_load(WORKFLOW.read_bytes())
    workflow_contract(value)
    trigger = value.get("on", value.get(True))
    if fault == "branch":
        trigger["push"]["branches"] = ["main"]
    elif fault == "path":
        trigger["push"]["paths"] = ["**"]
    elif fault == "dispatch":
        trigger["workflow_dispatch"] = {}
    elif fault == "guard":
        value["jobs"]["cp60-proof"]["if"] = "${{ true }}"
    elif fault == "producer":
        value["jobs"]["cp60-proof"]["steps"][1]["with"]["ref"] = "main"
    elif fault == "python":
        value["jobs"]["cp60-proof"]["steps"][2]["with"]["python-version"] = "3.13"
    elif fault == "caps":
        value["env"]["PYTHON_CPU_COUNT"] = "2"
    else:
        value["jobs"]["cp60-proof"]["steps"].pop()
    with pytest.raises(AssertionError):
        workflow_contract(value)
