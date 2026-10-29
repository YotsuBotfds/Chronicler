#!/usr/bin/env python3
"""Read the fixed research-admission contrast without changing generic comparators.

No simulation/native import, checkpoint unpickling, oracle rescoring or worker
launch occurs here. This is a study-specific development readout, not efficacy
qualification. Original producer verdicts and artifacts are never rewritten.
"""
from __future__ import annotations

import argparse
import ast
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import resource
import signal
import sys
import time

import research_natural_contract as C

class ReadoutBudgetExceeded(BaseException):
    """One-shot asynchronous censoring must bypass artifact-error catches."""


CONTROL = Path(__file__).resolve().parents[1]
OBSERVER_FILES = {"worker.log", "worker-summary.json", "worker-identity.json", "request.json",
    "launch-resources.json", "process-lease.json", "cleanup.json", "initial-rng.json", "boundary-rng.json", "restore.json", "restored-rng.json", "raw-history.json"}


def codec(source, frozen):
    path = Path(source) / "src/chronicler/bundle_codec.py"
    C.require(C.sha(path) == frozen["producer"]["files"]["src/chronicler/bundle_codec.py"]["sha256"], "frozen codec changed")
    namespace = {"__name__": "frozen_research_study_bundle_codec"}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    prune_path = Path(source) / "src/chronicler/snapshot_pruning.py"
    C.require(C.sha(prune_path) == frozen["producer"]["files"]["src/chronicler/snapshot_pruning.py"]["sha256"], "frozen pruning source changed")
    tree = ast.parse(prune_path.read_bytes(), filename=str(prune_path))
    removed = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "chronicler.bundle_codec"]
    C.require(len(removed) == 1 and [(n.name, n.asname) for n in removed[0].names] == [("decode_bundle", None)], "pruner codec import contract differs")
    tree.body.remove(removed[0])
    prune_namespace = {"__name__": "frozen_research_study_snapshot_pruning", "decode_bundle": namespace["decode_bundle"]}
    exec(compile(tree, str(prune_path), "exec"), prune_namespace)
    return namespace["decode_bundle"], namespace["same"], prune_namespace["prune_history"]


def ordinary(files):
    selected = {}
    for name, value in files.items():
        basename = Path(name).name
        if basename in OBSERVER_FILES or re.fullmatch(r"checkpoint_turn_(?:60|180)\.ckpt", basename):
            continue
        turn = re.search(r"_turn_(\d+)\.json$", basename)
        if turn and int(turn.group(1)) <= C.FORK:
            continue
        selected[name] = value
    return selected


def receipt_checks(receipt, seed, role, frozen, parent=None):
    C.closed(receipt, {"schema_version", "experiment", "cohort", "feature", "arm", "intervention_fork",
        "applied_before_turn", "seed", "controls_before", "controls_after", "parent_checkpoint", "registration",
        "source", "native", "previous_experiment", "research_policy"}, "experiment receipt")
    C.closed(receipt["research_policy"], {"before", "after", "requested_enabled"}, "research policy receipt")
    expected = dict(schema_version=1, experiment=C.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm=role, intervention_fork=role != "parent", applied_before_turn=0 if role == "parent" else C.FORK, seed=seed)
    for name, value in expected.items():
        C.require(type(receipt.get(name)) is type(value) and receipt[name] == value, "experiment receipt field differs: " + name)
    C.require(C.same(receipt["source"], frozen["runtime"]["source"])
              and C.same(receipt["native"], frozen["runtime"]["native"]), "receipt producer/native differs")
    C.require(C.same(receipt["registration"], dict(path=str((CONTROL / C.REGISTRATION).resolve()),
              sha256=frozen["controls"][C.REGISTRATION])), "registration provenance differs")
    C.require(C.same(receipt["controls_after"], C.CONTROLS), "shared ordinary controls differ")
    policy = receipt["research_policy"]
    if role == "parent":
        C.require(receipt["parent_checkpoint"] is None and receipt["previous_experiment"] is None,
                  "fresh parent claims a previous intervention")
        before = dict(C.CONTROLS, publication_rule="current-context-v1")
        C.require(C.same(receipt["controls_before"], before), "natural fresh science controls were not recorded")
        C.require(C.same(policy["before"], policy["after"]) and policy["requested_enabled"] is None,
                  "parent publication selection changed research admission state")
        C.require(policy["after"]["enabled"] is True and policy["after"]["enabled_turn"] == 0,
                  "finite research not activated before initial natural tick")
    else:
        C.require(C.same(receipt["controls_before"], C.CONTROLS), "fork ordinary controls before differs")
        h = parent["header"]
        expected_parent = dict(path=str(parent["path"]), sha256=parent["checkpoint_sha256"], turn=C.FORK,
            seed=seed, identity=h["identity"], flags=h["flags"], exact=True)
        C.require(C.same(receipt["parent_checkpoint"], expected_parent), "fork parent receipt differs")
        C.require(C.same(receipt["previous_experiment"], parent["run_config"]["expansion_experiment"]), "previous experiment lineage differs")
        old = parent["world"]["scientific_claims"]["research_agendas"]
        C.require(C.same(policy["before"], {"mode": old["rule"], **old}), "fork pre-policy program differs")
        new = deepcopy(old)
        if role == "pause_new_trials":
            new.update(enabled=False, policy_changed_turn=C.FORK)
        C.require(C.same(policy["after"], {"mode": old["rule"], **new}) and
                  policy["requested_enabled"] is (role == "active"), "undeclared program intervention")


SUMMARY_FIELDS = {"schema_version", "seed", "role", "execution_complete", "actual_physics_ticks", "final_turn",
    "native_sections", "final_rng", "final_rng_sha256", "parent_checkpoint_sha256", "run_config", "header",
    "experiment_receipt", "raw_history_sha256", "raw_world_sha256", "pause", "exposure", "seconds", "runtime_policy"}


def inspect_role(root, seed, role, frozen, decode, prune):
    selected = C.selected_policy(frozen)
    folder = root / f"seed-{seed}" / role
    C.require(type(seed) is int and seed in C.SEEDS and role in C.ROLES, "unregistered role identity")
    summary = C.read(folder / "worker-summary.json")
    C.closed(summary, SUMMARY_FIELDS, "worker summary")
    C.require(type(summary["schema_version"]) is int and summary["schema_version"] == 1, "worker schema differs")
    C.nonnegative(summary["seconds"], "worker seconds")
    for name in ("seed", "final_turn", "actual_physics_ticks"):
        C.nonnegative(summary[name], name, integer=True)
    cleanup = C.read(folder / "cleanup.json")
    C.closed(cleanup, {"complete", "identities", "accounting"}, "cleanup")
    C.closed(cleanup["accounting"], {"returncode", "tree_cpu_seconds", "accounting"}, "cleanup accounting")
    C.require(cleanup["complete"] is True and type(cleanup["accounting"]["returncode"]) is int
              and cleanup["accounting"]["returncode"] == 0, "producer process cleanup unverified")
    C.nonnegative(cleanup["accounting"]["tree_cpu_seconds"], "cleanup tree CPU seconds")
    C.require(cleanup["accounting"]["tree_cpu_seconds"] <= C.WORKER_CPU, "worker tree CPU allowance exceeded")
    identity = C.read(folder / "worker-identity.json")
    C.require(identity["identities_stable"] is True and C.same(identity["before"], frozen)
              and C.same(identity["after"], frozen), "actual worker producer/control/runtime observations differ")
    C.require(summary["seed"] == seed and summary["role"] == role and summary["execution_complete"] is True
              and summary["final_turn"] == C.END and summary["actual_physics_ticks"] == (C.END if role == "parent" else C.END - C.FORK),
              "worker identity/horizon differs")
    C.require(summary["runtime_policy"] == selected["name"], "worker runtime policy differs")
    bundle = decode(C.read(folder / "chronicle_bundle.json"))
    state = C.read(folder / "state.json")
    C.require(state["turn"] == bundle["metadata"]["total_turns"] == C.END
              and state["seed"] == bundle["metadata"]["seed"] == seed
              and state["agent_mode"] == "hybrid" and len(state["regions"]) == 8
              and len(state["civilizations"]) >= 4, "registered natural world shape differs")
    header, sections = C.checkpoint_sections(folder / "checkpoint_turn_180.ckpt")
    C.require(C.same(header, summary["header"]) and header["turn"] == C.END and header["seed"] == seed,
              "actual final checkpoint header differs")
    C.checkpoint_build_identity(header, frozen)
    C.require(header["exact"] is (role == "parent"), "checkpoint fork label differs")
    C.require(header["flags"]["scientific_research_agendas"] is (role != "pause_new_trials"), "research flag differs")
    for flag in ("health_care", "harvest_forecasts", "ritual_gatherings", "transaction_receipts"):
        C.require(header["flags"][flag] is False, "unregistered expansion feature enabled")
    native = {name: row for name, row in sections.items() if name.startswith("native.")}
    C.require(set(native) == set(summary["native_sections"]) == {"native.agent.0"}, "active native section set differs")
    for name, row in native.items():
        C.require(all(summary["native_sections"][name][key] == value for key, value in row.items())
                  and C.sha(folder / (name + "-final.bin")) == row["sha256"], "retained raw native section differs")
        recorded = summary["native_sections"][name]
        C.require(recorded["class_name"] == "AgentSimulator" and all(recorded[k] == v for k, v in
                  frozen["runtime"]["available_compiled_classes"]["AgentSimulator"].items()), "active native schema differs")
    C.require(C.same(state["scientific_claims"], bundle["world_state"]["scientific_claims"]), "exported science differs")
    C.require(C.digest(state) == summary["raw_world_sha256"], "raw exported world hash differs")
    raw_history = C.read(folder / "raw-history.json")
    C.require(type(raw_history) is list and [row["turn"] for row in raw_history] == list(range(1, C.END + 1)), "raw history coverage differs")
    C.require(C.digest(raw_history) == summary["raw_history_sha256"], "raw history attestation differs")
    pruned, tails = prune(raw_history)
    C.require(C.same(pruned, bundle["history"]) and C.same(tails, bundle["pruned_civ_stats"]),
              "source-pruned raw history does not match bundle history/tails")
    C.require([row["turn"] for row in bundle["history"]] == list(range(1, C.END + 1)), "history coverage differs")
    C.require(C.same(C.checkpoint_projection(summary["run_config"]), header["run_config"]), "checkpoint run configuration differs")
    simulation = summary["run_config"]["simulation_args"]
    for key, value in dict(agents="hybrid", worldgen="template", regions=8, civs=4,
                          scholarship=True, techniques=True, scientific_claims=True).items():
        C.require(type(simulation.get(key)) is type(value) and simulation[key] == value,
                  "registered simulation input differs: " + key)
    C.require(summary["run_config"]["simulation_args"]["scientific_research_agendas"] is (role != "pause_new_trials"), "effective research argument differs")
    C.require(C.digest(summary["final_rng"]) == summary["final_rng_sha256"], "reported final RNG state hash differs")
    C.validate_rng_json(summary["final_rng"])
    parent = None
    if role == "parent":
        C.require(summary["parent_checkpoint_sha256"] is None and summary["pause"] is None, "parent falsely claims a fork")
        initial = C.read(folder / "initial-rng.json")
        C.require(type(initial["seed"]) is int and initial["seed"] == seed, "initial external seed differs")
        C.validate_rng_json(initial["state"])
    else:
        parent = C.read(folder / "restore.json")
        parent["path"] = str((root / f"seed-{seed}/parent/checkpoint_turn_60.ckpt").resolve())
        actual_header, actual_sections = C.checkpoint_sections(parent["path"])
        C.require(C.same(parent["header"], actual_header) and actual_header["exact"] is True
                  and actual_header["turn"] == C.FORK and actual_header["seed"] == seed
                  and parent["checkpoint_sha256"] == C.sha(parent["path"]), "actual shared parent differs")
        C.checkpoint_build_identity(actual_header, frozen)
        C.require(summary["parent_checkpoint_sha256"] == parent["checkpoint_sha256"], "worker parent linkage differs")
        C.require(type(parent["history"]) is list and len(parent["history"]) == C.FORK
                  and C.same(raw_history[:C.FORK], parent["history"]), "restored raw history prefix differs")
        prefix_events = parent["world"]["events_timeline"]
        C.require(C.same(state["events_timeline"][:len(prefix_events)], prefix_events), "restored event prefix differs")
        C.require(C.same(C.checkpoint_projection(parent["run_config"]), actual_header["run_config"]), "parent run configuration differs")
        C.require(all(all(parent["native_sections"][name][k] == v for k, v in row.items())
                      for name, row in actual_sections.items() if name.startswith("native.")), "parent native section attestation differs")
        rng = C.read(Path(parent["path"]).parent / "boundary-rng.json")
        C.validate_rng_json(rng["state"])
        restored = C.read(folder / "restored-rng.json")
        C.require(rng["seed"] == seed and rng["turn"] == C.FORK
                  and rng["checkpoint_sha256"] == parent["checkpoint_sha256"]
                  and C.same(rng["checkpoint_sections"], actual_sections)
                  and rng["state_sha256"] == C.digest(rng["state"])
                  and C.same(rng["producer_runtime"], frozen["runtime"])
                  and rng["controls_sha256"] == C.digest(frozen["controls"])
                  and restored["sidecar_sha256"] == C.sha(Path(parent["path"]).parent / "boundary-rng.json")
                  and restored["state_sha256"] == rng["state_sha256"], "external boundary RNG evidence differs")
    receipt = bundle["metadata"]["expansion_experiment"]
    C.require(C.same(receipt, summary["experiment_receipt"]) and C.same(receipt, summary["run_config"]["expansion_experiment"]), "bundle/run receipt differs")
    receipt_checks(receipt, seed, role, frozen, parent)
    expected_request = dict(schema_version=1, experiment=C.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm=role, controls=dict(C.CONTROLS), fork=role != "parent", registration=receipt["registration"])
    if parent:
        expected_request["controls"]["research_enabled"] = role == "active"
        expected_request["parent_checkpoint"] = dict(path=parent["path"], sha256=parent["checkpoint_sha256"])
    C.require(C.same(C.read(folder / "request.json"), expected_request), "declared requested arm differs")
    expected_resume = None if role == "parent" else dict(kind="experiment-fork", exact=False, turn=C.FORK)
    C.require(bundle["metadata"].get("resume") == expected_resume
              and ("resume" in bundle["metadata"]) is (expected_resume is not None)
              and summary["run_config"]["resume_info"] == expected_resume, "resume provenance differs")
    lineage = [] if role == "parent" else deepcopy(parent["run_config"]["lineage"]) + [
        dict(resumed_at=C.FORK, kind="checkpoint", exact=True),
        dict(resumed_at=C.FORK, kind="experiment-fork", exact=False, experiment=receipt)]
    C.require(C.same(C.checkpoint_projection(lineage), header["lineage"]) and C.same(lineage, summary["run_config"]["lineage"]), "checkpoint lineage differs")
    science = state["scientific_claims"]
    C.require(C.same({key: science[key] for key in C.CONTROLS}, C.CONTROLS), "actual final science controls differ")
    C.require(science["research_agendas"]["enabled"] is (role != "pause_new_trials")
              and science["research_agendas"]["enabled_turn"] == 0, "actual retained research mode/activation differs")
    C.require(science["trial_spent"] == sum(t["cost"] for t in science["trials"]), "trial expense accounting differs")
    if role == "pause_new_trials":
        C.require(C.same(C.pause_archive(parent["world"]["scientific_claims"], science), summary["pause"]), "pause assessment differs")
    observed = C.exposure(science, bundle["history"])
    C.require(C.same(observed, summary["exposure"]), "source-dated exposure does not reconcile")
    return dict(summary=summary, bundle=bundle, raw_history=raw_history, state=state, parent=parent, exposure=observed, receipt_validated=True,
                cleanup_accounting=cleanup["accounting"], files=C.inventory(folder))


def active_identity(parent, active, strict):
    C.require(parent.get("receipt_validated") is True and active.get("receipt_validated") is True,
              "writer provenance must be validated before normalization")
    files_a, files_b = ordinary(parent["files"]), ordinary(active["files"])
    common, results = sorted(files_a.keys() & files_b.keys()), {}
    a, b = deepcopy(parent["bundle"]), deepcopy(active["bundle"])
    raw = C.differences(a, b)
    for bundle in (a, b):
        generated = bundle["metadata"].pop("generated_at")
        C.require(type(generated) is str and datetime.fromisoformat(generated).utcoffset() is not None, "invalid writer timestamp")
        # Only these exact writer-owned records, already validated in full.
        bundle["metadata"].pop("resume", None)
        bundle["metadata"].pop("expansion_experiment")
    normalized = C.differences(a, b)
    for name in common:
        results[name] = strict(a, b) if name == "chronicle_bundle.json" else files_a[name] == files_b[name]
    C.require("chronicle_bundle.json" in results and "state.json" in results, "required ordinary outputs missing")
    return dict(file_set_equal=files_a.keys() == files_b.keys(), files=results,
        raw_bundle_differences=raw, normalized_bundle_differences=normalized,
        raw_world_equal=parent["summary"]["raw_world_sha256"] == active["summary"]["raw_world_sha256"],
        raw_history_equal=parent["summary"]["raw_history_sha256"] == active["summary"]["raw_history_sha256"],
        actual_native_sections_equal=C.same(parent["summary"]["native_sections"], active["summary"]["native_sections"]),
        final_external_global_rng_equal=C.same(parent["summary"]["final_rng"], active["summary"]["final_rng"]))


EXECUTION_FIELDS = {"schema_version", "kind", "execution_complete", "qualified", "scientific_standing",
    "controller_started_monotonic", "boot_id", "freeze_sha256", "source_sha", "control_sha", "expected_executions",
    "expected_physics_ticks", "actual_physics_ticks", "aggregate_cpu_seconds", "aggregate_wall_seconds", "runs", "error", "files", "runtime_policy"}


def execution_contract(execution):
    C.closed(execution, EXECUTION_FIELDS, "execution record")
    C.require(type(execution["schema_version"]) is int and execution["schema_version"] == 1
              and execution["kind"] == "natural-research-continuation-execution", "execution schema differs")
    C.require(type(execution["execution_complete"]) is bool and execution["qualified"] is False, "execution verdict type differs")
    C.P.policy(execution["runtime_policy"])
    for name in ("aggregate_cpu_seconds", "aggregate_wall_seconds", "controller_started_monotonic"):
        C.nonnegative(execution[name], name)
    for name, expected in (("expected_executions", 24), ("expected_physics_ticks", 3360)):
        C.require(type(execution[name]) is int and execution[name] == expected, "registered cohort size differs")
    C.require(execution["actual_physics_ticks"] is None or type(execution["actual_physics_ticks"]) is int
              and 0 <= execution["actual_physics_ticks"] <= 3360, "actual physics count differs")
    C.require(type(execution["runs"]) is list and len(execution["runs"]) <= 24, "execution row bound differs")
    for row in execution["runs"]:
        status = row.get("status")
        fields = {"seed", "role", "status"}
        if status == "complete":
            fields |= {"returncode", "elapsed_seconds", "tree_cpu_seconds"}
            C.nonnegative(row.get("tree_cpu_seconds"), "worker tree CPU seconds")
            C.require(row["tree_cpu_seconds"] <= C.WORKER_CPU, "worker tree CPU allowance exceeded")
            C.require(type(row.get("returncode")) is int and row["returncode"] == 0, "completed execution lacks successful return code")
        elif status == "failed":
            fields |= {"error", "elapsed_seconds"}
            if "cleanup_error" in row:
                fields.add("cleanup_error")
            C.closed(row.get("error"), {"type", "message"}, "execution error")
        else:
            C.require(status in ("budget_censored", "not_attempted_after_failure"), "execution status differs")
        C.closed(row, fields, "execution role")
        C.require(type(row["seed"]) is int and row["seed"] in C.SEEDS and type(row["role"]) is str
                  and row["role"] in C.ROLES, "execution role identity differs")
        if "elapsed_seconds" in row:
            C.nonnegative(row["elapsed_seconds"], "execution elapsed seconds")
            if status == "complete":
                C.require(row["elapsed_seconds"] <= C.WORKER_WALL, "worker wall allowance exceeded")
    if execution["execution_complete"]:
        C.require(execution["actual_physics_ticks"] == 3360 and execution["error"] is None, "complete execution accounting differs")



EXECUTION_RECEIPT_FIELDS = {"schema_version", "kind", "publication_complete", "execution_sha256",
    "measured_to_seal_cpu_seconds", "finalization_cpu_reserve_seconds", "charged_aggregate_cpu_seconds",
    "aggregate_wall_seconds", "controller_started_monotonic", "boot_id"}


def execution_accounting(root, execution):
    """Close execution accounting after its heavy payload serialization/hash."""
    receipt = C.read(Path(root) / "execution-receipt.json")
    C.closed(receipt, EXECUTION_RECEIPT_FIELDS, "execution accounting receipt")
    C.require(type(receipt["schema_version"]) is int and receipt["schema_version"] == 1
              and receipt["kind"] == "natural-research-execution-receipt"
              and type(receipt["publication_complete"]) is bool, "execution accounting receipt schema differs")
    C.require(not execution["execution_complete"] or receipt["publication_complete"] is True,
              "complete execution lacks its committed accounting receipt")
    C.require(receipt["execution_sha256"] == C.sha(Path(root) / "execution.json"), "execution accounting payload hash differs")
    C.require(C.same(receipt["controller_started_monotonic"], execution["controller_started_monotonic"])
              and C.same(receipt["boot_id"], execution["boot_id"]), "execution accounting clock differs")
    for name in ("measured_to_seal_cpu_seconds", "charged_aggregate_cpu_seconds", "aggregate_wall_seconds"):
        C.nonnegative(receipt[name], "closed " + name)
    reserve = 1.0 if receipt["publication_complete"] else 0.0
    C.require(type(receipt["finalization_cpu_reserve_seconds"]) is float
              and receipt["finalization_cpu_reserve_seconds"] == reserve, "execution finalization reserve differs")
    C.require(C.same(receipt["charged_aggregate_cpu_seconds"], receipt["measured_to_seal_cpu_seconds"] + reserve),
              "closed execution CPU charge does not include the declared finalization reserve")
    C.require(receipt["measured_to_seal_cpu_seconds"] >= execution["aggregate_cpu_seconds"]
              and receipt["aggregate_wall_seconds"] >= execution["aggregate_wall_seconds"],
              "closed execution accounting predates payload work")
    if receipt["publication_complete"]:
        C.require(receipt["charged_aggregate_cpu_seconds"] <= C.AGGREGATE_CPU
                  and receipt["aggregate_wall_seconds"] <= C.AGGREGATE_WALL, "closed execution budget exceeds allowance")
    return receipt


def reconcile_worker_accounting(row, cleanup):
    C.require(C.same(cleanup["tree_cpu_seconds"], row["tree_cpu_seconds"])
              and C.same(cleanup["returncode"], row["returncode"]), "execution/cleanup worker accounting differs")


def boundary_facts(world, snapshot):
    """Raw boundary owners and previous-source capacity retain distinct clocks."""
    science = world["scientific_claims"]
    scholarship = world.get("scholarship")
    C.require(type(scholarship) is dict and type(scholarship.get("seats")) is list, "boundary scholarship unavailable")
    academies = []
    for index, seat in enumerate(scholarship["seats"]):
        if seat["kind"] != 0:
            continue
        region = seat["region"]
        valid_region = type(region) is int and 0 <= region < len(world["regions"])
        living = (seat["founded_turn"] <= C.FORK and seat["fallen_turn"] is None and seat["level"] > 0 and valid_region)
        owner_name = world["regions"][region]["controller"] if valid_region else None
        owner = next((i for i, civ in enumerate(world["civilizations"]) if civ["name"] == owner_name), -1)
        academies.append(dict(seat=index, record=seat, living_at_boundary=living, enrolled=index in science["seat_ids"],
            owner=owner, owner_name=owner_name, treasury=world["civilizations"][owner]["treasury"] if owner >= 0 else None))
    capacity = snapshot["research_agendas"]["capacity"]
    C.require(type(capacity) is dict and set(capacity) == {"topics", "trials", "proposals", "receipts", "messages", "cycles", "seats"}, "boundary capacity fields differ")
    for row in capacity.values():
        C.closed(row, {"used", "reserved", "limit"}, "boundary capacity row")
        for name in row:
            C.nonnegative(row[name], "boundary capacity " + name, integer=True)
        C.require(row["used"] + row["reserved"] <= row["limit"], "boundary capacity accounting exceeds limit")
    return dict(world_turn=C.FORK, source_observation_turn=C.FORK - 1, academies=academies,
        living_academies=sum(a["living_at_boundary"] for a in academies), enrolled_seats=list(science["seat_ids"]),
        academy_births=science["research_agendas"]["academy_births"], capacity_previous_source=capacity,
        capacity_scope="snapshot source59 reservations; boundary World60 owners and seat records are separate observations")


def build_readout(root, source, guard=lambda: None, policy_name=C.P.DEFAULT_POLICY):
    root, source = Path(root).resolve(), Path(source).resolve()
    execution = C.read(root / "execution.json")
    execution_contract(execution)
    accounting = execution_accounting(root, execution)
    accounting_sha256 = C.sha(root / "execution-receipt.json")
    C.require(execution["qualified"] is False, "original execution verdict was rewritten")
    recorded = execution["files"]
    observed = C.inventory(root, omit=("execution.json", "execution-receipt.json"))
    C.require(recorded == observed, "execution payload set/hash linkage differs")
    frozen = C.read(root / "freeze.json")
    selected = C.selected_policy(frozen)
    C.require(selected["name"] == policy_name == execution["runtime_policy"], "readout runtime policy differs")
    from run_research_natural_continuation import policy_evidence
    evidence_path = frozen["runtime_policy_evidence"]["path"] if frozen["runtime_policy_evidence"] else None
    C.require(C.same(frozen["runtime_policy_evidence"], policy_evidence(source, selected, evidence_path)),
              "official wheel policy evidence differs")
    C.require(C.sha(root / "freeze.json") == execution["freeze_sha256"], "prospective freeze hash differs")
    C.require(C.same(frozen["producer"], C.source_snapshot(source, C.SOURCE)), "producer source snapshot differs")
    C.require(C.same(frozen["control"], C.source_snapshot(CONTROL, frozen["control"]["git_sha"])), "control source snapshot differs")
    C.require(frozen["controls"] == {name: C.sha(CONTROL / name) for name in C.control_files(policy_name)}, "observer/registration hashes differ")
    C.require(execution["source_sha"] == C.SOURCE and execution["control_sha"] == frozen["control"]["git_sha"], "execution source/control differs")
    C.require(execution["expected_executions"] == 24 and execution["expected_physics_ticks"] == 3360, "registered cohort size differs")
    roles = {(row["seed"], row["role"]): row for row in execution["runs"]}
    C.require(len(roles) == len(execution["runs"]) and set(roles) <= {(s, r) for s in C.SEEDS for r in C.ROLES}, "duplicate/unregistered execution rows")
    decode, strict, prune = codec(source, frozen)
    seeds, errors = [], []
    for seed in C.SEEDS:
        guard()
        inspected = {}
        for role in C.ROLES:
            guard()
            row = roles.get((seed, role))
            if row is None or row["status"] != "complete":
                errors.append(dict(seed=seed, role=role, reason="missing_or_censored_execution", status=row["status"] if row else "missing"))
                continue
            try:
                C.require(type(row.get("returncode")) is int and row["returncode"] == 0,
                          "complete execution row has no successful exit code")
                inspected[role] = inspect_role(root, seed, role, frozen, decode, prune)
                cleanup = inspected[role]["cleanup_accounting"]
                reconcile_worker_accounting(row, cleanup)
            except Exception as exc:
                errors.append(dict(seed=seed, role=role, reason=type(exc).__name__, message=str(exc)))
        entry = dict(seed=seed, complete_roles=sorted(inspected), paired=False,
                     exposure={role: row["exposure"] for role, row in inspected.items()})
        if set(inspected) == set(C.ROLES):
            parent, active, pause = (inspected[r] for r in C.ROLES)
            try:
                C.require(C.same(active["parent"], pause["parent"]), "forks did not observe the same original checkpoint")
                flags = parent["summary"]["header"]["flags"]
                config = parent["summary"]["run_config"]["simulation_args"]
                for role, inspected_role in (("active", active), ("pause_new_trials", pause)):
                    actual_flags = dict(inspected_role["summary"]["header"]["flags"])
                    actual_config = dict(inspected_role["summary"]["run_config"]["simulation_args"])
                    actual_flags["scientific_research_agendas"] = True
                    actual_config["scientific_research_agendas"] = True
                    C.require(C.same(actual_flags, flags) and C.same(actual_config, config),
                              "undeclared feature or simulation configuration differs")
                original = active["parent"]["world"]["scientific_claims"]
                boundary_science = parent["bundle"]["history"][C.FORK - 1].get("scientific_claims")
                C.require(type(boundary_science) is dict and boundary_science["source_turn"] == C.FORK - 1
                          and boundary_science["research_agendas"]["rule"] == "finite-retained-v1"
                          and boundary_science["research_agendas"]["enabled"] is True,
                          "dated common pre-intervention program observation unavailable")
                entry["boundary"] = dict(science=original, facts=boundary_facts(active["parent"]["world"], boundary_science), world_turn=C.FORK, source_turn=C.FORK - 1,
                    checkpoint_sha256=active["parent"]["checkpoint_sha256"],
                    prefix_scope="raw Python checkpoint prefixes attested by pinned worker; checkpoint Python section not unpickled by reader")
                entry["active_noop"] = active_identity(parent, active, strict)
                check = entry["active_noop"]
                okay = check["file_set_equal"] and all(check["files"].values()) and all(check[k] for k in
                    ("raw_world_equal", "raw_history_equal", "actual_native_sections_equal", "final_external_global_rng_equal"))
                C.require(okay, "active continuation differs from uninterrupted parent")
                entry["pause"] = pause["summary"]["pause"]
                entry["paired"] = True
                entry["active_minus_pause"] = {key: active["exposure"][key] - pause["exposure"][key] for key in
                    ("new_agendas", "new_trials", "new_trial_cost", "outcome_receipts_received", "outcome_receipts_from_new_trials", "paid_adoption_cost")}
            except Exception as exc:
                errors.append(dict(seed=seed, reason=type(exc).__name__, message=str(exc)))
        seeds.append(entry)
    complete = execution["execution_complete"] is True and len(roles) == 24 and not errors and all(row["paired"] for row in seeds)
    within = accounting["charged_aggregate_cpu_seconds"] <= C.AGGREGATE_CPU and accounting["aggregate_wall_seconds"] <= C.AGGREGATE_WALL
    C.require(C.same(frozen["producer"], C.source_snapshot(source, C.SOURCE))
              and C.same(frozen["control"], C.source_snapshot(CONTROL, frozen["control"]["git_sha"])),
              "producer/control source changed during readout")
    C.require(C.inventory(root, omit=("execution.json", "execution-receipt.json")) == observed, "evidence changed during readout")
    C.require(C.sha(root / "execution-receipt.json") == accounting_sha256, "execution accounting receipt changed during readout")
    total_keys = ("new_agendas", "new_trials", "new_trial_cost", "outcome_receipts_received", "outcome_receipts_from_new_trials", "paid_adoption_cost")
    totals = {role: {key: sum(row["exposure"][role][key] for row in seeds if role in row["exposure"]) for key in total_keys}
              for role in C.ROLES}
    total_scope = {role: dict(observed_seeds=[row["seed"] for row in seeds if role in row["exposure"]],
        all_eight_observed=all(role in row["exposure"] for row in seeds)) for role in C.ROLES}
    return dict(schema_version=1, kind="natural-research-continuation-development-readout",
        execution_complete=execution["execution_complete"], mechanics_verified=complete and within,
        scientific_standing="descriptive_development_exposure" if complete and within else "blocked_or_censored",
        efficacy_qualified=False, default_promotion=False, source_sha=C.SOURCE, control_sha=frozen["control"]["git_sha"], runtime_policy=selected,
        execution_receipt_sha256=accounting_sha256, execution_sha256=C.sha(root / "execution.json"), freeze_sha256=C.sha(root / "freeze.json"),
        inspected_payloads=len(observed), registered_seed_ids=list(C.SEEDS), paired_seed_rows=sum(s["paired"] for s in seeds),
        seeds=seeds, stage_totals=totals, totals_coverage=total_scope,
        active_minus_pause_totals={key: sum(row["active_minus_pause"][key] for row in seeds if row["paired"]) for key in total_keys},
        difference_totals_scope=dict(paired_seed_ids=[row["seed"] for row in seeds if row["paired"]], all_eight_paired=all(row["paired"] for row in seeds)),
        errors=errors, budgets=dict(controller_charged_upper_bound_cpu_seconds=accounting["charged_aggregate_cpu_seconds"],
            controller_measured_to_seal_cpu_seconds=accounting["measured_to_seal_cpu_seconds"],
            controller_finalization_cpu_reserve_seconds=accounting["finalization_cpu_reserve_seconds"],
            aggregate_wall_seconds=accounting["aggregate_wall_seconds"], within_registered_limits=within),
        limitations=["Natural generation under declared experimental switches; no natural-benefit or independent-group claim.",
            "Global RNG uses an explicit external boundary sidecar, not a RunState checkpoint field.",
            "Checkpoint raw/packed sections verified without unpickling; runtime/object binding and raw-prefix checks are pinned worker attestations.",
            "Publication/receipt/paid-use stages differ; same-source Phase10 receipts do not explain earlier Phase4 allocations.",
            "Generic expansion_compare guards remain unchanged; this reader accepts only the specifically registered admission-policy contrast."])


def markdown(result):
    lines = ["# Natural finite-research continuation development readout", "", result["scientific_standing"], "",
        "| Seed | Complete roles | Paired mechanism check | Active new trials | Paused new trials |", "| --- | --- | --- | --- | --- |"]
    for row in result["seeds"]:
        exposures = row["exposure"]
        lines.append(f"| {row['seed']} | {', '.join(row['complete_roles']) or 'none'} | {row['paired']} | "
            f"{exposures.get('active', {}).get('new_trials', 'unknown')} | {exposures.get('pause_new_trials', {}).get('new_trials', 'unknown')} |")
    lines += ["", "Every fixed seed is retained. Unknown/censored exposure is not a scientific zero.",
              "No efficacy or default-promotion result is produced.", "", *["- " + x for x in result["limitations"]]]
    return "\n".join(lines) + "\n"


def publish_readout(output, result, guard, *, started, budget_observation):
    """Commit the authoritative receipt only while all final work is bounded.

    readout.json is provisional until receipt.json exists and links its bytes.
    If a guard or timer fires even after the atomic receipt rename, all partial
    publications are retained under incomplete-* names and cannot be accepted.
    """
    output = Path(output)
    try:
        guard()
        result["publication_status"] = "provisional_until_matching_completion_seal"
        result.setdefault("budgets", {}).update(budget_observation())
        C.write(output / "readout.json", result)
        guard()  # Covers JSON serialization and writing, not only construction.
        if "seeds" in result:
            with (output / "readout.md").open("x", encoding="utf-8") as stream:
                stream.write(markdown(result))
            guard()
        files = C.inventory(output)
        guard()  # Covers all final payload hashing.
        receipt = dict(schema_version=1, kind="natural-research-readout-receipt", publication_complete=True,
            mechanics_verified=result["mechanics_verified"], efficacy_qualified=False,
            elapsed_seconds=time.monotonic() - started, native_modules_loaded=False,
            worlds_or_native_pools_created=0, budget_observation=budget_observation(), files=files)
        C.write(output / "pending-receipt.json", receipt)
        guard()  # Includes serialization/hash work before the atomic commit.
        os.replace(output / "pending-receipt.json", output / "receipt.json")
        guard()  # An expiry during final publication invalidates the receipt.
    except BaseException:
        for name in ("receipt.json", "pending-receipt.json", "readout.json", "readout.md"):
            path = output / name
            if path.exists():
                os.replace(path, output / ("incomplete-" + name))
        raise


def invalidate_publication(output):
    """Keep every failed attempt, with no authoritative completion path."""
    output = Path(output)
    for name in ("completion.json", "pending-completion.json", "receipt.json", "pending-receipt.json", "readout.json", "readout.md"):
        path = output / name
        if path.exists():
            destination = output / ("incomplete-" + name)
            index = 1
            while destination.exists():
                destination = output / (f"incomplete-{index}-" + name)
                index += 1
            os.replace(path, destination)


def complete_transaction(output, operation, finalize, guard, budget_observation):
    """A caller-level transaction includes asynchronous timer finalization.

    The receipt is provisional until completion.json binds its bytes. The
    outer catch covers operation, timer disarm/handler restoration, seal
    serialization, rename and the final budget check. A non-success path
    preserves those attempted outputs under incomplete-* names.
    """
    output = Path(output)
    try:
        try:
            result = operation()
            seal = dict(schema_version=1, kind="natural-research-readout-completion", publication_complete=True,
                receipt_sha256=C.sha(output / "receipt.json"), budget_observation=budget_observation())
            C.write(output / "pending-completion.json", seal)
            guard()
            os.replace(output / "pending-completion.json", output / "completion.json")
            guard()
        finally:
            finalize()  # Still inside the outer invalidation catch.
        guard()  # Explicit clocks also cover timer/handler restoration.
        return result
    except BaseException:
        invalidate_publication(output)
        raise


def validate_completion(output):
    """Consumers accept a positive readout only with this matching final seal."""
    output = Path(output)
    seal = C.read(output / "completion.json")
    C.closed(seal, {"schema_version", "kind", "publication_complete", "receipt_sha256", "budget_observation"}, "readout completion seal")
    C.require(type(seal["schema_version"]) is int and seal["schema_version"] == 1
              and seal["kind"] == "natural-research-readout-completion" and seal["publication_complete"] is True,
              "readout completion seal differs")
    C.require(seal["receipt_sha256"] == C.sha(output / "receipt.json"), "readout completion receipt hash differs")
    receipt = C.read(output / "receipt.json")
    C.require(receipt["publication_complete"] is True and receipt["files"] == C.inventory(output,
        omit=("receipt.json", "completion.json")), "readout completion payload hashes differ")
    return seal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--runtime-policy", choices=C.P.NAMES, default=C.P.DEFAULT_POLICY)
    args = parser.parse_args(argv)
    root, output = Path(args.evidence_root).resolve(), Path(args.output_root).resolve()
    C.require(not output.exists() and not output.is_relative_to(root) and not output.is_relative_to(CONTROL)
              and not output.is_relative_to(Path(args.source_root).resolve()), "fresh external readout required")
    output.mkdir(parents=True)
    started, before_modules = time.monotonic(), set(sys.modules)
    self0, child0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    base_cpu = self0.ru_utime + self0.ru_stime + child0.ru_utime + child0.ru_stime
    original_handler = signal.getsignal(signal.SIGALRM)
    C.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "reader requires an unleased real timer")
    def cpu():
        own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime - base_cpu
    def timeout(signum, frame):
        raise ReadoutBudgetExceeded("registered aggregate study/readout wall budget crossed")
    def finalize():
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original_handler)
    try:
        execution = C.read(root / "execution.json")
        execution_contract(execution)
        C.require(execution["runtime_policy"] == args.runtime_policy, "explicit readout runtime policy differs")
        accounting = execution_accounting(root, execution)
        C.require(execution["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  "original controller clock is not visible on this host; no fresh budget inferred")
        def budgets():
            used = cpu()
            return dict(reader_cpu_seconds=used,
                controller_charged_upper_bound_cpu_seconds=accounting["charged_aggregate_cpu_seconds"],
                controller_measured_to_seal_cpu_seconds=accounting["measured_to_seal_cpu_seconds"],
                controller_finalization_cpu_reserve_seconds=accounting["finalization_cpu_reserve_seconds"],
                controller_charge_plus_reader_measured_cpu_upper_bound_seconds=accounting["charged_aggregate_cpu_seconds"] + used,
                total_cpu_accounting_scope="conservative controller charge plus measured reader CPU; not measured total CPU",
                controller_to_readout_wall_seconds=time.monotonic() - execution["controller_started_monotonic"])
        elapsed = time.monotonic() - execution["controller_started_monotonic"]
        C.require(elapsed >= accounting["aggregate_wall_seconds"], "closed execution accounting is ahead of the visible clock")
        remaining = C.AGGREGATE_WALL - elapsed
        C.require(0 < remaining <= C.AGGREGATE_WALL, "registered controller/readout wall budget exhausted or clock changed")
        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        from run_research_natural_continuation import resources
        def guard():
            resources(root)
            observed = budgets()
            if observed["controller_charge_plus_reader_measured_cpu_upper_bound_seconds"] > C.AGGREGATE_CPU:
                raise ReadoutBudgetExceeded("registered controller/readout aggregate CPU budget crossed")
            if not 0 <= observed["controller_to_readout_wall_seconds"] <= C.AGGREGATE_WALL:
                raise ReadoutBudgetExceeded("registered controller/readout aggregate wall budget crossed")
        def operation():
            guard()
            result = build_readout(root, args.source_root, guard, args.runtime_policy)
            C.require(not any(n.startswith("chronicler_agents") for n in set(sys.modules) - before_modules), "reader unexpectedly loaded native code")
            publish_readout(output, result, guard, started=started, budget_observation=budgets)
            return result
        result = complete_transaction(output, operation, finalize, guard, budgets)
    except BaseException as exc:
        # This outer catch also covers interrupts during final timer teardown.
        invalidate_publication(output)
        try:
            finalize()
        except BaseException as final_error:
            exc = final_error
        result = dict(schema_version=1, scientific_standing="refused", mechanics_verified=False, efficacy_qualified=False,
                      error=dict(type=type(exc).__name__, message=str(exc)))
        C.write(output / "readout.json", result)
        C.write(output / "receipt.json", dict(schema_version=1, kind="natural-research-readout-receipt",
            publication_complete=False, mechanics_verified=False, efficacy_qualified=False,
            elapsed_seconds=time.monotonic() - started,
            native_modules_loaded=any(n.startswith("chronicler_agents") for n in set(sys.modules) - before_modules),
            worlds_or_native_pools_created=0, files=C.inventory(output)))
    return 0 if result["mechanics_verified"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
