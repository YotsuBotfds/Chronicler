"""Synthetic artifact contracts, not generated worlds or scientific outcomes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import random
import struct
import zlib

import pytest

from test_research_natural_continuation import modules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def synthetic(modules, tmp_path, monkeypatch):
    # Reuse the script loader fixture without importing any native runtime.
    c, runner, reader = modules
    import numpy as np
    from chronicler.main import _build_parser
    from chronicler.batch_manifest import simulation_config
    root = tmp_path / "synthetic-artifacts"
    root.mkdir()
    selected = c.P.policy()
    schema = selected["schemas"]
    threads = {name: "1" for name in (*c.THREADS, "PYTHON_CPU_COUNT")}
    threads.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
    observed_runtime = dict(source=dict(package_digest=selected["package_digest"], git_sha=c.SOURCE),
        native=dict(status="found", sha256=c.NATIVE, bytes=selected["native_bytes"], module_file="/synthetic/compiled.so"),
        compiled_origin="/synthetic/compiled.so", available_compiled_classes=schema,
        environment=dict(python=selected["python"], implementation="CPython", machine="x86_64", platform="Linux-explicit-synthetic-fixture", affinity_cpu_count=1,
                         thread_env=threads, packages=selected["packages"]))
    frozen = dict(runtime=observed_runtime, runtime_policy=selected, runtime_policy_evidence=None,
                  controls={name: c.sha(ROOT / name) for name in c.CONTROL_FILES})
    registration = dict(path=str((ROOT / c.REGISTRATION).resolve()), sha256=frozen["controls"][c.REGISTRATION])
    identity = dict(source=observed_runtime["source"], native={
        **{key: observed_runtime["native"][key] for key in ("status", "sha256", "bytes")},
        "state_layouts": {kind: "v1:" + schema[name]["fingerprint"] for name, kind in
            (("AgentSimulator", "agent"), ("EcologySimulator", "ecology"), ("PoliticsSimulator", "politics"))}},
        environment={**{key: observed_runtime["environment"][key] for key in
            ("python", "implementation", "machine", "affinity_cpu_count", "thread_env", "packages")}, "hash_seed": "0"})
    python = random.Random(2000).getstate()
    numpy = np.random.RandomState(2000).get_state()
    rng = dict(python=[python[0], list(python[1]), python[2]], numpy=[numpy[0], numpy[1].tolist(), *numpy[2:]])
    plan = dict(schema_version=1, rule="finite-retained-v1", enabled=True, enabled_turn=0, policy_changed_turn=0,
        next_open_turn=0, origin_cursor=-1, cycles=[], blocked_reason="", blocked_turn=None,
        host_seal="0" * 64, academy_births=[])
    science = dict(seat_ids=[], claims=[], trials=[], proposals=[], receipts=[], trial_spent=0, effort_spent=0,
        research_agendas=plan, **c.CONTROLS)
    def header(turn, config, role):
        flags = dict(scholarship=True, techniques=True, scientific_claims=True, health_care=False,
            harvest_forecasts=False, ritual_gatherings=False, transaction_receipts=False,
            scientific_research_agendas=role != "pause_new_trials")
        return dict(format="chronicler-run-checkpoint", version=1, turn=turn, seed=2000, exact=role == "parent",
                    identity=identity, flags=flags, run_config=config, lineage=config["lineage"])
    def checkpoint(path, value):
        value = deepcopy(value)
        body, sections = b"", []
        for name, raw in (("python", b"synthetic opaque bytes; deliberately never unpickled"),
                          ("native.agent.0", b"synthetic opaque native bytes; deliberately never loaded")):
            packed = zlib.compress(raw)
            sections.append(dict(name=name, offset=len(body), length=len(packed), raw_length=len(raw),
                                 sha256=c.hashlib.sha256(packed).hexdigest()))
            body += packed
        value["sections"] = sections
        raw_header = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        path.write_bytes(c.MAGIC + struct.pack("<I", len(raw_header)) + raw_header + body)
        return c.checkpoint_sections(path)
    seed_root = root / "seed-2000"
    for role in c.ROLES:
        (seed_root / role).mkdir(parents=True)
    parent_folder = seed_root / "parent"
    parent_receipt = dict(schema_version=1, experiment=c.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm="parent", intervention_fork=False, applied_before_turn=0, seed=2000,
        controls_before=dict(c.CONTROLS, publication_rule="current-context-v1"), controls_after=dict(c.CONTROLS),
        parent_checkpoint=None, registration=registration, source=observed_runtime["source"], native=observed_runtime["native"],
        previous_experiment=None, research_policy=dict(before={"mode": plan["rule"], **plan},
            after={"mode": plan["rule"], **plan}, requested_enabled=None))
    simulation = simulation_config(_build_parser().parse_args(runner.simulation_args(parent_folder, 2000, "parent")))
    parent_config = dict(simulation_args=simulation, expansion_experiment=parent_receipt, resume_info=None, lineage=[])
    parent_path = parent_folder / "checkpoint_turn_60.ckpt"
    parent_header, parent_sections = checkpoint(parent_path, header(60, parent_config, "parent"))
    c.write(parent_folder / "boundary-rng.json", dict(seed=2000, turn=60, checkpoint_sha256=c.sha(parent_path),
        checkpoint_sections=parent_sections, state=rng, state_sha256=c.digest(rng), producer_runtime=observed_runtime,
        controls_sha256=c.digest(frozen["controls"])))
    c.write(parent_folder / "initial-rng.json", dict(seed=2000, state=rng))
    def history(role):
        return [dict(turn=turn, scientific_claims=dict(source_turn=turn - 1, allocations=[],
            research_agendas=dict(rule="finite-retained-v1", enabled=role != "pause_new_trials" or turn <= 60)))
            for turn in range(1, 181)]
    parent_world = dict(seed=2000, turn=60, agent_mode="hybrid", regions=[{} for _ in range(8)],
                        civilizations=[dict(name="civ" + str(i), treasury=1) for i in range(4)], scholarship=dict(seats=[]), scientific_claims=deepcopy(science), events_timeline=[])
    restore = dict(checkpoint_sha256=c.sha(parent_path), header=parent_header, run_config=parent_config,
        world=parent_world, history=history("parent")[:60], native_sections={"native.agent.0": {
            **parent_sections["native.agent.0"], "class_name": "AgentSimulator", **schema["AgentSimulator"]}})
    for role in c.ROLES:
        folder = seed_root / role
        current_science = deepcopy(science)
        receipt, config, resume = deepcopy(parent_receipt), deepcopy(parent_config), None
        if role != "parent":
            expected_parent = dict(path=str(parent_path.resolve()), sha256=c.sha(parent_path), turn=60, seed=2000,
                identity=parent_header["identity"], flags=parent_header["flags"], exact=True)
            receipt.update(arm=role, intervention_fork=True, applied_before_turn=60,
                controls_before=dict(c.CONTROLS), parent_checkpoint=expected_parent, previous_experiment=deepcopy(parent_receipt))
            receipt["research_policy"]["requested_enabled"] = role == "active"
            if role == "pause_new_trials":
                current_science["research_agendas"].update(enabled=False, policy_changed_turn=60)
                receipt["research_policy"]["after"].update(enabled=False, policy_changed_turn=60)
            resume = dict(kind="experiment-fork", exact=False, turn=60)
            config.update(expansion_experiment=receipt, resume_info=resume, lineage=[
                dict(resumed_at=60, kind="checkpoint", exact=True),
                dict(resumed_at=60, kind="experiment-fork", exact=False, experiment=receipt)])
            config["simulation_args"]["scientific_research_agendas"] = role == "active"
            c.write(folder / "restore.json", restore)
            c.write(folder / "restored-rng.json", dict(sidecar_sha256=c.sha(parent_folder / "boundary-rng.json"), state_sha256=c.digest(rng)))
        world = {**deepcopy(parent_world), "turn": 180, "scientific_claims": current_science}
        rows = history(role)
        metadata = dict(seed=2000, total_turns=180, generated_at="2026-10-29T00:00:00+00:00", expansion_experiment=receipt)
        if resume:
            metadata["resume"] = resume
        bundle = dict(world_state=world, history=rows, pruned_civ_stats={}, events_timeline=[], metadata=metadata)
        c.write(folder / "raw-history.json", rows)
        c.write(folder / "state.json", world)
        c.write(folder / "chronicle_bundle.json", bundle)
        h, sections = checkpoint(folder / "checkpoint_turn_180.ckpt", header(180, config, role))
        native_record = {"native.agent.0": {**sections["native.agent.0"], "class_name": "AgentSimulator", **schema["AgentSimulator"]}}
        (folder / "native.agent.0-final.bin").write_bytes(b"synthetic opaque native bytes; deliberately never loaded")
        c.write(folder / "worker-identity.json", dict(identities_stable=True, before=frozen, after=frozen))
        c.write(folder / "cleanup.json", dict(complete=True, identities={"1": 1}, accounting=dict(returncode=0, tree_cpu_seconds=0.1, accounting="synthetic")))
        c.write(folder / "request.json", runner.request(2000, role, registration, parent_path if role != "parent" else None))
        summary = dict(schema_version=1, seconds=0.1, runtime_policy=selected["name"], parent_checkpoint_sha256=c.sha(parent_path) if role != "parent" else None, seed=2000, role=role, execution_complete=True, final_turn=180,
            actual_physics_ticks=180 if role == "parent" else 120, header=h, run_config=config,
            native_sections=native_record, raw_world_sha256=c.digest(world), raw_history_sha256=c.digest(rows),
            final_rng=rng, final_rng_sha256=c.digest(rng), experiment_receipt=receipt,
            pause=c.pause_archive(science, current_science) if role == "pause_new_trials" else None,
            exposure=c.exposure(current_science, rows))
        c.write(folder / "worker-summary.json", summary)
    from chronicler.bundle_codec import decode_bundle
    from chronicler.snapshot_pruning import prune_history
    return c, reader, root, frozen, decode_bundle, prune_history


def test_synthetic_complete_roles_reconcile_native_checkpoint_rng_and_null_exposure(synthetic):
    c, reader, root, frozen, decode, prune = synthetic
    roles = {role: reader.inspect_role(root, 2000, role, frozen, decode, prune) for role in c.ROLES}
    assert all(row["exposure"]["new_trials"] == 0 for row in roles.values())
    compared = reader.active_identity(roles["parent"], roles["active"], c.same)
    assert compared["file_set_equal"] and all(compared["files"].values())
    assert compared["normalized_bundle_differences"] == []
    assert roles["pause_new_trials"]["summary"]["pause"]["no_new_trial_funding"] is True


@pytest.mark.parametrize("field", ["publication", "rng", "native", "request"])
def test_readout_refuses_unregistered_control_or_broken_raw_link(synthetic, field):
    c, reader, root, frozen, decode, prune = synthetic
    folder = root / "seed-2000/active"
    if field == "publication":
        bundle = c.read(folder / "chronicle_bundle.json")
        bundle["metadata"]["expansion_experiment"]["controls_after"]["publication_rule"] = "current-context-v1"
        (folder / "chronicle_bundle.json").write_bytes(c.encoded(bundle))
    elif field == "rng":
        restored = c.read(folder / "restored-rng.json")
        restored["state_sha256"] = "not-the-boundary"
        (folder / "restored-rng.json").write_bytes(c.encoded(restored))
    elif field == "native":
        (folder / "native.agent.0-final.bin").write_bytes(b"different native bytes")
    else:
        request = c.read(folder / "request.json")
        request["controls"]["research_enabled"] = False
        (folder / "request.json").write_bytes(c.encoded(request))
    with pytest.raises(c.ContractError):
        reader.inspect_role(root, 2000, "active", frozen, decode, prune)


def test_actual_sorted_checkpoint_projection_preserves_science_strictness(synthetic):
    c, reader, root, frozen, decode, prune = synthetic
    folder = root / "seed-2000/active"
    summary = c.read(folder / "worker-summary.json")
    # The actual checkpoint writer recursively sorts JSON, unlike RunState.
    assert list(summary["run_config"]) != list(summary["header"]["run_config"])
    assert reader.inspect_role(root, 2000, "active", frozen, decode, prune)["receipt_validated"]
    assert not c.same({"science": {"a": 1, "b": -0.0}}, {"science": {"b": -0.0, "a": 1}})
    assert not c.same({"science": -0.0}, {"science": 0.0})
    broken = deepcopy(summary["header"])
    broken["identity"]["environment"]["affinity_cpu_count"] = True
    with pytest.raises(c.ContractError, match="projection"):
        c.checkpoint_build_identity(broken, frozen)


@pytest.mark.parametrize("target", ["raw", "tail"])
def test_raw_history_must_reconcile_with_frozen_pruning_not_just_its_attestation(synthetic, target):
    c, reader, root, frozen, decode, prune = synthetic
    folder = root / "seed-2000/active"
    if target == "raw":
        raw = c.read(folder / "raw-history.json")
        raw[-1]["scientific_claims"]["allocations"] = [{"changed": True}]
        (folder / "raw-history.json").write_bytes(c.encoded(raw))
        summary = c.read(folder / "worker-summary.json")
        summary["raw_history_sha256"] = c.digest(raw)
        (folder / "worker-summary.json").write_bytes(c.encoded(summary))
    else:
        bundle = c.read(folder / "chronicle_bundle.json")
        bundle["pruned_civ_stats"] = {"invented": []}
        (folder / "chronicle_bundle.json").write_bytes(c.encoded(bundle))
    with pytest.raises(c.ContractError, match="source-pruned"):
        reader.inspect_role(root, 2000, "active", frozen, decode, prune)


@pytest.mark.parametrize("moment", ["serialization", "hashing", "receipt_commit"])
def test_publication_expiry_cannot_leave_an_authoritative_positive_receipt(modules, tmp_path, monkeypatch, moment):
    c, _, reader = modules
    output = tmp_path / "readout"
    output.mkdir()
    state = {"expired": False}
    original_encoded, original_sha = c.encoded, c.sha
    if moment == "serialization":
        def encode(value):
            answer = original_encoded(value)
            state["expired"] = True
            return answer
        monkeypatch.setattr(c, "encoded", encode)
    if moment == "hashing":
        def sha(path):
            answer = original_sha(path)
            state["expired"] = True
            return answer
        monkeypatch.setattr(c, "sha", sha)
    def guard():
        if moment == "receipt_commit" and (output / "receipt.json").exists():
            state["expired"] = True
        if state["expired"]:
            raise c.ContractError("registered budget expired during final publication")
    with pytest.raises(c.ContractError, match="final publication"):
        reader.publish_readout(output, {"mechanics_verified": True}, guard,
            started=reader.time.monotonic(), budget_observation=lambda: {})
    assert not (output / "receipt.json").exists()
    assert not (output / "readout.json").exists()
    assert (output / "incomplete-readout.json").exists()
    if moment == "receipt_commit":
        assert c.read(output / "incomplete-receipt.json")["mechanics_verified"] is True


def test_publication_receipt_links_final_readout_bytes(modules, tmp_path):
    c, _, reader = modules
    output = tmp_path / "readout"
    output.mkdir()
    reader.publish_readout(output, {"mechanics_verified": True}, lambda: None,
        started=reader.time.monotonic(), budget_observation=lambda: {"observed": 0})
    receipt = c.read(output / "receipt.json")
    assert receipt["publication_complete"] is True
    assert receipt["files"]["readout.json"]["sha256"] == c.sha(output / "readout.json")
    assert c.read(output / "readout.json")["publication_status"] == "provisional_until_matching_completion_seal"


def test_frozen_reader_loads_codec_and_pruner_without_production_imports(modules):
    c, _, reader = modules
    frozen = {"producer": {"files": {name: {"sha256": c.sha(ROOT / name)} for name in
        ("src/chronicler/bundle_codec.py", "src/chronicler/snapshot_pruning.py")}}}
    decode, strict, prune = reader.codec(ROOT, frozen)
    raw = [{"turn": 1, "civ_stats": {"dead": {"regions": [], "treasury": 1}}},
           {"turn": 2, "civ_stats": {"dead": {"regions": [], "treasury": 2}}}]
    rows, tails = prune(raw)
    assert decode({"history": rows})["history"] == rows
    assert tails["dead"][0]["from_turn"] == 2
    assert not strict(-0.0, 0.0)


def test_execution_accounting_refuses_boolean_negative_nonfinite_and_unknown_rows(modules):
    c, _, reader = modules
    execution = dict(schema_version=1, kind="natural-research-continuation-execution", execution_complete=False,
        qualified=False, scientific_standing="incomplete_or_censored", controller_started_monotonic=1.0,
        boot_id="synthetic", freeze_sha256="synthetic", source_sha=c.SOURCE, control_sha="synthetic",
        expected_executions=24, expected_physics_ticks=3360, actual_physics_ticks=None,
        aggregate_cpu_seconds=1.0, aggregate_wall_seconds=1.0, runs=[], error=None, files={}, runtime_policy=c.P.DEFAULT_POLICY)
    reader.execution_contract(execution)
    for value in (True, -1, float("inf"), float("nan")):
        broken = deepcopy(execution)
        broken["aggregate_cpu_seconds"] = value
        with pytest.raises(c.ContractError):
            reader.execution_contract(broken)
    for row in ({"seed": True, "role": "parent", "status": "budget_censored"},
                {"seed": 2000, "role": "unknown", "status": "budget_censored"},
                {"seed": 2000, "role": "parent", "status": "budget_censored", "hidden": True}):
        broken = deepcopy(execution)
        broken["runs"] = [row]
        with pytest.raises(c.ContractError):
            reader.execution_contract(broken)


def test_boundary_owners_and_previous_source_capacity_are_distinct_clocks(modules):
    c, _, reader = modules
    live = dict(region=0, kind=0, founded_turn=10, fallen_turn=None, level=1)
    fallen = dict(region=0, kind=0, founded_turn=1, fallen_turn=40, level=0)
    world = dict(scholarship=dict(seats=[live, fallen]), regions=[dict(controller="owner")],
        civilizations=[dict(name="owner", treasury=17)], scientific_claims=dict(seat_ids=[0, 1],
            research_agendas=dict(academy_births=[{"seat": 0}, {"seat": 1}])))
    capacity = {name: dict(used=0, reserved=0, limit=40) for name in
        ("topics", "trials", "proposals", "receipts", "messages", "cycles", "seats")}
    result = reader.boundary_facts(world, {"research_agendas": {"capacity": capacity}})
    assert result["world_turn"] == 60 and result["source_observation_turn"] == 59
    assert result["living_academies"] == 1 and result["enrolled_seats"] == [0, 1]
    assert result["academies"][0]["owner"] == 0 and result["academies"][0]["treasury"] == 17
    assert result["academies"][1]["living_at_boundary"] is False
    capacity["trials"]["reserved"] = True
    with pytest.raises(c.ContractError):
        reader.boundary_facts(world, {"research_agendas": {"capacity": capacity}})


def execution_fixture(c):
    return dict(schema_version=1, kind="natural-research-continuation-execution", execution_complete=False,
        qualified=False, scientific_standing="incomplete_or_censored", controller_started_monotonic=1.0,
        boot_id="synthetic", freeze_sha256="synthetic", source_sha=c.SOURCE, control_sha="synthetic",
        expected_executions=24, expected_physics_ticks=3360, actual_physics_ticks=None,
        aggregate_cpu_seconds=1.0, aggregate_wall_seconds=1.0, runs=[], error=None, files={}, runtime_policy=c.P.DEFAULT_POLICY)


@pytest.mark.parametrize("field,value", [("tree_cpu_seconds", 100.0), ("elapsed_seconds", 901.0)])
def test_complete_worker_cannot_spend_another_workers_allowance(modules, field, value):
    c, _, reader = modules
    execution = execution_fixture(c)
    row = dict(seed=2000, role="parent", status="complete", returncode=0, elapsed_seconds=1.0, tree_cpu_seconds=1.0)
    row[field] = value
    execution["runs"] = [row]
    with pytest.raises(c.ContractError, match="worker .* allowance"):
        reader.execution_contract(execution)


def test_worker_cleanup_accounting_must_match_execution_row(modules):
    c, _, reader = modules
    row = dict(returncode=0, tree_cpu_seconds=10.0)
    reader.reconcile_worker_accounting(row, dict(returncode=0, tree_cpu_seconds=10.0))
    for cleanup in (dict(returncode=0, tree_cpu_seconds=11.0), dict(returncode=False, tree_cpu_seconds=10.0)):
        with pytest.raises(c.ContractError, match="execution/cleanup"):
            reader.reconcile_worker_accounting(row, cleanup)


@pytest.mark.parametrize("fault", ["hash", "old_cpu", "clock", "extra", "uncommitted"])
def test_execution_final_accounting_is_closed_and_bound_to_provisional_payload(modules, tmp_path, fault):
    c, _, reader = modules
    execution = execution_fixture(c)
    execution.update(execution_complete=True, actual_physics_ticks=3360)
    c.write(tmp_path / "execution.json", execution)
    receipt = dict(schema_version=1, kind="natural-research-execution-receipt", publication_complete=True,
        execution_sha256=c.sha(tmp_path / "execution.json"), measured_to_seal_cpu_seconds=2.0,
        finalization_cpu_reserve_seconds=1.0, charged_aggregate_cpu_seconds=3.0, aggregate_wall_seconds=2.0,
        controller_started_monotonic=execution["controller_started_monotonic"], boot_id=execution["boot_id"])
    if fault == "hash":
        receipt["execution_sha256"] = "different"
    elif fault == "old_cpu":
        receipt["measured_to_seal_cpu_seconds"] = .5
        receipt["charged_aggregate_cpu_seconds"] = 1.5
    elif fault == "clock":
        receipt["controller_started_monotonic"] = 2.0
    elif fault == "extra":
        receipt["extra"] = True
    else:
        receipt["publication_complete"] = False
    c.write(tmp_path / "execution-receipt.json", receipt)
    with pytest.raises(c.ContractError):
        reader.execution_accounting(tmp_path, execution)


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_timer_finalization_interrupt_invalidates_receipt_and_completion_seal(modules, tmp_path, failure):
    c, _, reader = modules
    output = tmp_path / "readout"
    output.mkdir()
    def operation():
        result = {"mechanics_verified": True}
        reader.publish_readout(output, result, lambda: None, started=reader.time.monotonic(), budget_observation=lambda: {})
        return result
    def finalize():
        raise failure("interrupted while disarming timer")
    with pytest.raises(failure):
        reader.complete_transaction(output, operation, finalize, lambda: None, lambda: {})
    assert not (output / "receipt.json").exists()
    assert not (output / "completion.json").exists()
    assert (output / "incomplete-receipt.json").exists()
    assert (output / "incomplete-completion.json").exists()


def test_positive_receipt_requires_matching_final_completion_seal(modules, tmp_path):
    c, _, reader = modules
    output = tmp_path / "readout"
    output.mkdir()
    def operation():
        result = {"mechanics_verified": True}
        reader.publish_readout(output, result, lambda: None, started=reader.time.monotonic(), budget_observation=lambda: {})
        return result
    reader.complete_transaction(output, operation, lambda: None, lambda: None, lambda: {})
    assert reader.validate_completion(output)["publication_complete"] is True
    (output / "readout.json").write_bytes(b"changed")
    with pytest.raises(c.ContractError, match="payload hashes"):
        reader.validate_completion(output)


@pytest.mark.parametrize("fault", ["unknown_receipt", "unknown_policy", "numeric_parent_exact"])
def test_normalized_provenance_has_closed_typed_receipt_schema(synthetic, fault):
    c, reader, root, frozen, decode, prune = synthetic
    folder = root / "seed-2000/active"
    summary = c.read(folder / "worker-summary.json")
    receipt = summary["experiment_receipt"]
    parent = c.read(folder / "restore.json")
    parent["path"] = str((root / "seed-2000/parent/checkpoint_turn_60.ckpt").resolve())
    if fault == "unknown_receipt":
        receipt["hidden_override"] = True
    elif fault == "unknown_policy":
        receipt["research_policy"]["override"] = True
    else:
        receipt["parent_checkpoint"]["exact"] = 1
    with pytest.raises(c.ContractError):
        reader.receipt_checks(receipt, 2000, "active", frozen, parent)


def test_reader_cpu_admission_uses_closed_controller_charge_not_earlier_sample(modules, tmp_path, monkeypatch):
    from types import SimpleNamespace
    c, runner, reader = modules
    root = tmp_path / "evidence"
    root.mkdir()
    execution = execution_fixture(c)
    execution.update(controller_started_monotonic=reader.time.monotonic() - 2,
        boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(), aggregate_cpu_seconds=.1)
    c.write(root / "execution.json", execution)
    c.write(root / "execution-receipt.json", dict(schema_version=1, kind="natural-research-execution-receipt",
        publication_complete=True, execution_sha256=c.sha(root / "execution.json"), measured_to_seal_cpu_seconds=898.9,
        finalization_cpu_reserve_seconds=1.0, charged_aggregate_cpu_seconds=899.9, aggregate_wall_seconds=1.0,
        controller_started_monotonic=execution["controller_started_monotonic"], boot_id=execution["boot_id"]))
    calls = {"count": 0}
    def usage(which):
        calls["count"] += 1
        return SimpleNamespace(ru_utime=0.0 if calls["count"] <= 2 else .2, ru_stime=0.0)
    monkeypatch.setattr(reader.resource, "getrusage", usage)
    monkeypatch.setattr(runner, "resources", lambda root: {})
    monkeypatch.setattr(reader, "build_readout", lambda *a: pytest.fail("closed charge already exhausts admission"))
    output = tmp_path / "readout"
    assert reader.main(["--evidence-root", str(root), "--source-root", str(tmp_path / "source"), "--output-root", str(output)]) == 1
    assert c.read(output / "readout.json")["error"]["type"] == "ReadoutBudgetExceeded"
    assert c.read(output / "receipt.json")["publication_complete"] is False
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize("field,value", [("finalization_cpu_reserve_seconds", 0.0),
    ("charged_aggregate_cpu_seconds", 2.0), ("charged_aggregate_cpu_seconds", 901.0)])
def test_closed_controller_charge_retains_original_cap_and_full_reserve(modules, tmp_path, field, value):
    c, _, reader = modules
    execution = execution_fixture(c)
    c.write(tmp_path / "execution.json", execution)
    receipt = dict(schema_version=1, kind="natural-research-execution-receipt", publication_complete=True,
        execution_sha256=c.sha(tmp_path / "execution.json"), measured_to_seal_cpu_seconds=2.0,
        finalization_cpu_reserve_seconds=1.0, charged_aggregate_cpu_seconds=3.0, aggregate_wall_seconds=2.0,
        controller_started_monotonic=1.0, boot_id="synthetic")
    receipt[field] = value
    c.write(tmp_path / "execution-receipt.json", receipt)
    with pytest.raises(c.ContractError):
        reader.execution_accounting(tmp_path, execution)


def test_one_shot_budget_expiry_during_role_is_not_reclassified_and_continued(modules, tmp_path, monkeypatch):
    c, _, reader = modules
    root = tmp_path / "evidence"
    root.mkdir()
    execution = execution_fixture(c)
    execution.update(execution_complete=True, actual_physics_ticks=3360, runs=[dict(seed=seed, role=role,
        status="complete", returncode=0, tree_cpu_seconds=.1, elapsed_seconds=.1) for seed in c.SEEDS for role in c.ROLES])
    c.write(root / "execution.json", execution)
    c.write(root / "execution-receipt.json", dict(schema_version=1, kind="natural-research-execution-receipt",
        publication_complete=True, execution_sha256=c.sha(root / "execution.json"), measured_to_seal_cpu_seconds=2.0,
        finalization_cpu_reserve_seconds=1.0, charged_aggregate_cpu_seconds=3.0, aggregate_wall_seconds=2.0,
        controller_started_monotonic=1.0, boot_id="synthetic"))
    snapshot = dict(git_sha="synthetic")
    c.write(root / "freeze.json", dict(producer=snapshot, control=snapshot, runtime_policy_evidence=None,
        controls={name: c.sha(ROOT / name) for name in c.CONTROL_FILES}))
    execution["freeze_sha256"] = c.sha(root / "freeze.json")
    (root / "execution.json").write_bytes(c.encoded(execution))
    receipt = c.read(root / "execution-receipt.json")
    receipt["execution_sha256"] = c.sha(root / "execution.json")
    (root / "execution-receipt.json").write_bytes(c.encoded(receipt))
    monkeypatch.setattr(c, "inventory", lambda *a, **k: {})
    monkeypatch.setattr(c, "source_snapshot", lambda *a, **k: snapshot)
    monkeypatch.setattr(c, "selected_policy", lambda *a: c.P.policy())
    monkeypatch.setattr(reader, "codec", lambda *a: (None, None, None))
    calls = []
    def expire(*args):
        calls.append(args[2])
        raise reader.ReadoutBudgetExceeded("one-shot timer expired during metadata parsing")
    monkeypatch.setattr(reader, "inspect_role", expire)
    with pytest.raises(reader.ReadoutBudgetExceeded, match="one-shot"):
        reader.build_readout(root, tmp_path / "source")
    assert calls == ["parent"]


def test_negative_execution_receipt_can_report_partial_evidence_without_positive_reserve(modules, tmp_path):
    c, _, reader = modules
    execution = execution_fixture(c)
    c.write(tmp_path / "execution.json", execution)
    receipt = dict(schema_version=1, kind="natural-research-execution-receipt", publication_complete=False,
        execution_sha256=c.sha(tmp_path / "execution.json"), measured_to_seal_cpu_seconds=2.0,
        finalization_cpu_reserve_seconds=0.0, charged_aggregate_cpu_seconds=2.0, aggregate_wall_seconds=2.0,
        controller_started_monotonic=1.0, boot_id="synthetic")
    c.write(tmp_path / "execution-receipt.json", receipt)
    assert reader.execution_accounting(tmp_path, execution)["publication_complete"] is False
    execution.update(execution_complete=True, actual_physics_ticks=3360)
    (tmp_path / "execution.json").write_bytes(c.encoded(execution))
    receipt["execution_sha256"] = c.sha(tmp_path / "execution.json")
    (tmp_path / "execution-receipt.json").write_bytes(c.encoded(receipt))
    with pytest.raises(c.ContractError, match="committed accounting"):
        reader.execution_accounting(tmp_path, execution)
