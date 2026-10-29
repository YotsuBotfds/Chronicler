#!/usr/bin/env python3
"""Read the fixed research-admission contrast without changing generic comparators.

No simulation/native import, checkpoint unpickling, oracle rescoring or worker
launch occurs here. This is a study-specific development readout, not efficacy
qualification. Original producer verdicts and artifacts are never rewritten.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import resource
import signal
import sys
import time

import research_natural_contract as C

CONTROL = Path(__file__).resolve().parents[1]
OBSERVER_FILES = {"worker.log", "worker-summary.json", "worker-identity.json", "request.json",
    "launch-resources.json", "process-lease.json", "cleanup.json", "initial-rng.json", "boundary-rng.json", "restore.json", "restored-rng.json"}


def codec(source, frozen):
    path = Path(source) / "src/chronicler/bundle_codec.py"
    C.require(C.sha(path) == frozen["producer"]["files"]["src/chronicler/bundle_codec.py"]["sha256"], "frozen codec changed")
    namespace = {"__name__": "frozen_research_study_bundle_codec"}
    exec(compile(path.read_bytes(), str(path), "exec"), namespace)
    return namespace["decode_bundle"], namespace["same"]


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
    expected = dict(schema_version=1, experiment=C.EXPERIMENT, cohort="development", feature="scientific_claims",
        arm=role, intervention_fork=role != "parent", applied_before_turn=0 if role == "parent" else C.FORK, seed=seed)
    for name, value in expected.items():
        C.require(type(receipt.get(name)) is type(value) and receipt[name] == value, "experiment receipt field differs: " + name)
    C.require(C.same(receipt["source"], frozen["runtime"]["source"])
              and C.same(receipt["native"], frozen["runtime"]["native"]), "receipt producer/native differs")
    C.require(receipt["registration"] == dict(path=str((CONTROL / C.REGISTRATION).resolve()),
              sha256=frozen["controls"][C.REGISTRATION]), "registration provenance differs")
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
        C.require(receipt["parent_checkpoint"] == expected_parent, "fork parent receipt differs")
        C.require(C.same(receipt["previous_experiment"], parent["run_config"]["expansion_experiment"]), "previous experiment lineage differs")
        old = parent["world"]["scientific_claims"]["research_agendas"]
        C.require(C.same(policy["before"], {"mode": old["rule"], **old}), "fork pre-policy program differs")
        new = deepcopy(old)
        if role == "pause_new_trials":
            new.update(enabled=False, policy_changed_turn=C.FORK)
        C.require(C.same(policy["after"], {"mode": old["rule"], **new}) and
                  policy["requested_enabled"] is (role == "active"), "undeclared program intervention")


def inspect_role(root, seed, role, frozen, decode):
    folder = root / f"seed-{seed}" / role
    summary = C.read(folder / "worker-summary.json")
    C.require(C.read(folder / "cleanup.json")["complete"] is True, "producer process cleanup unverified")
    identity = C.read(folder / "worker-identity.json")
    C.require(identity["identities_stable"] is True and C.same(identity["before"], frozen)
              and C.same(identity["after"], frozen), "actual worker producer/control/runtime observations differ")
    C.require(summary["seed"] == seed and summary["role"] == role and summary["execution_complete"] is True
              and summary["final_turn"] == C.END and summary["actual_physics_ticks"] == (C.END if role == "parent" else C.END - C.FORK),
              "worker identity/horizon differs")
    bundle = decode(C.read(folder / "chronicle_bundle.json"))
    state = C.read(folder / "state.json")
    C.require(state["turn"] == bundle["metadata"]["total_turns"] == C.END
              and state["seed"] == bundle["metadata"]["seed"] == seed
              and state["agent_mode"] == "hybrid" and len(state["regions"]) == 8
              and len(state["civilizations"]) >= 4, "registered natural world shape differs")
    header, sections = C.checkpoint_sections(folder / "checkpoint_turn_180.ckpt")
    C.require(header == summary["header"] and header["turn"] == C.END and header["seed"] == seed,
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
    C.require([row["turn"] for row in bundle["history"]] == list(range(1, C.END + 1)), "history coverage differs")
    C.require(C.same(summary["run_config"], header["run_config"]), "checkpoint run configuration differs")
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
        initial = C.read(folder / "initial-rng.json")
        C.require(type(initial["seed"]) is int and initial["seed"] == seed, "initial external seed differs")
        C.validate_rng_json(initial["state"])
    else:
        parent = C.read(folder / "restore.json")
        parent["path"] = str((root / f"seed-{seed}/parent/checkpoint_turn_60.ckpt").resolve())
        actual_header, actual_sections = C.checkpoint_sections(parent["path"])
        C.require(parent["header"] == actual_header and actual_header["exact"] is True
                  and actual_header["turn"] == C.FORK and actual_header["seed"] == seed
                  and parent["checkpoint_sha256"] == C.sha(parent["path"]), "actual shared parent differs")
        C.checkpoint_build_identity(actual_header, frozen)
        C.require(C.same(parent["run_config"], actual_header["run_config"]), "parent run configuration differs")
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
    C.require(C.same(lineage, header["lineage"]) and C.same(lineage, summary["run_config"]["lineage"]), "checkpoint lineage differs")
    science = state["scientific_claims"]
    C.require(C.same({key: science[key] for key in C.CONTROLS}, C.CONTROLS), "actual final science controls differ")
    C.require(science["research_agendas"]["enabled"] is (role != "pause_new_trials")
              and science["research_agendas"]["enabled_turn"] == 0, "actual retained research mode/activation differs")
    C.require(science["trial_spent"] == sum(t["cost"] for t in science["trials"]), "trial expense accounting differs")
    if role == "pause_new_trials":
        C.require(C.same(C.pause_archive(parent["world"]["scientific_claims"], science), summary["pause"]), "pause assessment differs")
    observed = C.exposure(science, bundle["history"])
    C.require(C.same(observed, summary["exposure"]), "source-dated exposure does not reconcile")
    return dict(summary=summary, bundle=bundle, state=state, parent=parent, exposure=observed, receipt_validated=True,
                files=C.inventory(folder))


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


def build_readout(root, source, guard=lambda: None):
    root, source = Path(root).resolve(), Path(source).resolve()
    execution = C.read(root / "execution.json")
    C.require(execution["qualified"] is False, "original execution verdict was rewritten")
    recorded = execution["files"]
    observed = C.inventory(root, omit=("execution.json",))
    C.require(recorded == observed, "execution payload set/hash linkage differs")
    frozen = C.read(root / "freeze.json")
    C.require(C.sha(root / "freeze.json") == execution["freeze_sha256"], "prospective freeze hash differs")
    C.require(C.same(frozen["producer"], C.source_snapshot(source, C.SOURCE)), "producer source snapshot differs")
    C.require(C.same(frozen["control"], C.source_snapshot(CONTROL, frozen["control"]["git_sha"])), "control source snapshot differs")
    C.require(frozen["controls"] == {name: C.sha(CONTROL / name) for name in C.CONTROL_FILES}, "observer/registration hashes differ")
    C.require(execution["source_sha"] == C.SOURCE and execution["control_sha"] == frozen["control"]["git_sha"], "execution source/control differs")
    C.require(execution["expected_executions"] == 24 and execution["expected_physics_ticks"] == 3360, "registered cohort size differs")
    roles = {(row["seed"], row["role"]): row for row in execution["runs"]}
    C.require(len(roles) == len(execution["runs"]) and set(roles) <= {(s, r) for s in C.SEEDS for r in C.ROLES}, "duplicate/unregistered execution rows")
    decode, strict = codec(source, frozen)
    seeds, errors = [], []
    for seed in C.SEEDS:
        guard()
        inspected = {}
        for role in C.ROLES:
            row = roles.get((seed, role))
            if row is None or row["status"] != "complete":
                errors.append(dict(seed=seed, role=role, reason="missing_or_censored_execution", status=row["status"] if row else "missing"))
                continue
            try:
                C.require(type(row.get("returncode")) is int and row["returncode"] == 0,
                          "complete execution row has no successful exit code")
                inspected[role] = inspect_role(root, seed, role, frozen, decode)
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
                entry["boundary"] = dict(science=original, world_turn=C.FORK, source_turn=C.FORK - 1,
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
                    ("new_trials", "new_trial_cost", "outcome_receipts_received", "outcome_receipts_from_new_trials", "paid_adoption_cost")}
            except Exception as exc:
                errors.append(dict(seed=seed, reason=type(exc).__name__, message=str(exc)))
        seeds.append(entry)
    complete = execution["execution_complete"] is True and len(roles) == 24 and not errors and all(row["paired"] for row in seeds)
    within = (type(execution["aggregate_cpu_seconds"]) in (int, float) and execution["aggregate_cpu_seconds"] <= C.AGGREGATE_CPU
              and type(execution["aggregate_wall_seconds"]) in (int, float) and execution["aggregate_wall_seconds"] <= C.AGGREGATE_WALL)
    C.require(C.inventory(root, omit=("execution.json",)) == observed, "evidence changed during readout")
    return dict(schema_version=1, kind="natural-research-continuation-development-readout",
        execution_complete=execution["execution_complete"], mechanics_verified=complete and within,
        scientific_standing="descriptive_development_exposure" if complete and within else "blocked_or_censored",
        efficacy_qualified=False, default_promotion=False, source_sha=C.SOURCE, control_sha=frozen["control"]["git_sha"],
        execution_sha256=C.sha(root / "execution.json"), freeze_sha256=C.sha(root / "freeze.json"),
        inspected_payloads=len(observed), registered_seed_ids=list(C.SEEDS), paired_seed_rows=sum(s["paired"] for s in seeds),
        seeds=seeds, errors=errors, budgets=dict(aggregate_cpu_seconds=execution["aggregate_cpu_seconds"],
            aggregate_wall_seconds=execution["aggregate_wall_seconds"], within_registered_limits=within),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args(argv)
    root, output = Path(args.evidence_root).resolve(), Path(args.output_root).resolve()
    C.require(not output.exists() and not output.is_relative_to(root) and not output.is_relative_to(CONTROL)
              and not output.is_relative_to(Path(args.source_root).resolve()), "fresh external readout required")
    output.mkdir(parents=True)
    started, before_modules = time.monotonic(), set(sys.modules)
    self0, child0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    base_cpu = self0.ru_utime + self0.ru_stime + child0.ru_utime + child0.ru_stime
    original_handler = signal.getsignal(signal.SIGALRM)
    def cpu():
        own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime - base_cpu
    def timeout(signum, frame):
        raise C.ContractError("registered aggregate study/readout wall budget crossed")
    try:
        execution = C.read(root / "execution.json")
        C.require(execution["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                  "original controller clock is not visible on this host; no fresh budget inferred")
        remaining = C.AGGREGATE_WALL - (time.monotonic() - execution["controller_started_monotonic"])
        C.require(0 < remaining <= C.AGGREGATE_WALL, "registered controller/readout wall budget exhausted or clock changed")
        signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        from run_research_natural_continuation import resources
        def guard():
            resources(root)
            C.require(execution["aggregate_cpu_seconds"] + cpu() <= C.AGGREGATE_CPU,
                      "registered controller/readout aggregate CPU budget crossed")
        guard()
        result = build_readout(root, args.source_root, guard)
        guard()
        result["budgets"].update(reader_cpu_seconds=cpu(), controller_plus_reader_cpu_seconds=execution["aggregate_cpu_seconds"] + cpu(),
            controller_to_readout_wall_seconds=time.monotonic() - execution["controller_started_monotonic"])
    except Exception as exc:
        result = dict(schema_version=1, scientific_standing="refused", mechanics_verified=False, efficacy_qualified=False,
                      error=dict(type=type(exc).__name__, message=str(exc)))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original_handler)
    C.require(not any(n.startswith("chronicler_agents") for n in set(sys.modules) - before_modules), "reader unexpectedly loaded native code")
    C.write(output / "readout.json", result)
    if "seeds" in result:
        with (output / "readout.md").open("x", encoding="utf-8") as stream:
            stream.write(markdown(result))
    C.write(output / "receipt.json", dict(schema_version=1, kind="natural-research-readout-receipt",
        mechanics_verified=result["mechanics_verified"], efficacy_qualified=False,
        elapsed_seconds=time.monotonic() - started, native_modules_loaded=False,
        worlds_or_native_pools_created=0, files=C.inventory(output)))
    return 0 if result["mechanics_verified"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
