"""Read-only, provenance-matched comparisons of recorded expansion experiment arms."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from chronicler.bundle_codec import decode_bundle
from chronicler.expansion_audit import AuditError, Limits, _md, audit_bundle
from chronicler.historical_context import AsOf
from chronicler.scientific_receipts_audit import COUNTERS as SCIENCE_COUNTERS, LEGACY_RULE, PUBLICATION_RULES

FEATURES = {
    "harvest_forecasts": ("policy",),
    "ritual_gatherings": ("contact_enabled", "bonds_enabled"),
    "health_care": ("care_enabled", "injury_rate", "impairment", "care_fraction", "recovery_work"),
    "scientific_claims": ("withhold_information", "transmission_enabled", "uninformative_tests", "publication_rule"),
}
BASELINES = {"harvest_forecasts": "normal", "ritual_gatherings": "normal", "health_care": "care", "scientific_claims": "normal"}
ENV_KEYS = ("python", "implementation", "machine", "hash_seed", "packages", "thread_env", "affinity_cpu_count")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
CONTROL_BOUNDS = {"injury_rate": (0, .25), "impairment": (0, 1), "care_fraction": (0, 1), "recovery_work": (1, 10)}
INTERPRETATION = (
    "These are descriptive comparisons of recorded post-intervention receipts. Matched provenance "
    "and complete records do not qualify efficacy, independent replication, forecast skill, "
    "clinical recovery, avoided deaths or successful bond formation. Each paired seed is one unit."
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identity(raw):
    if not isinstance(raw, Mapping):
        return None
    source, native = raw.get("source"), raw.get("native")
    if not isinstance(source, Mapping) or not isinstance(native, Mapping):
        return None
    git, package, binary = source.get("git_sha"), source.get("package_digest"), native.get("sha256")
    if (not isinstance(git, str) or not re.fullmatch(r"[0-9a-f]{40}", git)
            or any(not isinstance(s, str) or not re.fullmatch(r"[0-9a-f]{64}", s) for s in (package, binary))
            or native.get("status") != "found"):
        return None
    return {"git_sha": git, "package_digest": package, "native_sha256": binary}


def _read(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise AuditError(f"{path.name} exceeds max_file_bytes")
    return raw, json.loads(raw)


def _environment(raw):
    if not isinstance(raw, Mapping) or any(key not in raw for key in ENV_KEYS if key != "hash_seed"):
        return None
    out = {key: raw.get(key) for key in ENV_KEYS}
    if "hash_seed" not in raw:
        thread_env = raw.get("thread_env")
        if not isinstance(thread_env, Mapping) or "PYTHONHASHSEED" not in thread_env:
            return None
        out["hash_seed"] = thread_env["PYTHONHASHSEED"]
    if any(not isinstance(out[key], str) or not out[key] for key in ("python", "implementation", "machine")):
        return None
    for key in ("python", "implementation", "machine", "hash_seed"):
        value = out[key]
        if value is not None and (not isinstance(value, str) or len(value) > 128 or "/" in value or "\\" in value):
            return None
    if out["affinity_cpu_count"] is not None and (type(out["affinity_cpu_count"]) is not int or out["affinity_cpu_count"] < 1):
        return None
    for key in ("packages", "thread_env"):
        values = out[key]
        if (not isinstance(values, Mapping) or not values or len(values) > 100
                or any(not isinstance(k, str) or len(k) > 128 or not k.replace("-", "_").isidentifier()
                       or (v is not None and (not isinstance(v, str) or len(v) > 128 or "/" in v or "\\" in v))
                       for k, v in values.items())):
            return None
        out[key] = dict(values)
    platform = raw.get("platform")
    if platform is not None and (not isinstance(platform, str) or len(platform) > 256 or "/" in platform or "\\" in platform):
        return None
    out["platform"] = platform
    for key in ("cpu_count", "process_cpu_count"):
        value = raw.get(key)
        if value is not None and (type(value) is not int or value < 1):
            return None
        out[key] = value
    executable = raw.get("executable")
    if executable is not None and (not isinstance(executable, str) or not 1 <= len(executable) <= 4096):
        return None
    out["executable_path_sha256"] = hashlib.sha256(executable.encode()).hexdigest() if executable is not None else None
    return out


def _controls(raw, feature, blockers):
    fields = FEATURES.get(feature, ())
    if (feature == "scientific_claims" and isinstance(raw, Mapping)
            and set(raw) == set(fields) - {"publication_rule"}):
        # The original source-owned serialization omits the legacy default.
        raw = {**raw, "publication_rule": LEGACY_RULE}
    if not isinstance(raw, Mapping) or set(raw) != set(fields):
        blockers.append("incomplete_or_unknown_controls")
        return None
    if any(type(v) not in (bool, int, float, str) for v in raw.values()):
        blockers.append("malformed_controls")
        return None
    for name, value in raw.items():
        if name.endswith("enabled") or name in ("withhold_information", "uninformative_tests"):
            valid = type(value) is bool
        elif name == "policy":
            valid = value in ("normal", "withhold", "shuffle")
        elif name == "publication_rule":
            valid = value in PUBLICATION_RULES
        else:
            low, high = CONTROL_BOUNDS[name]
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
            except OverflowError:
                valid = False
        if not valid:
            blockers.append("malformed_controls")
            return None
    # Avoid exporting any unregistered metadata fields or paths.
    return {key: raw[key] for key in fields}


def _window_metrics(feature, observed, start):
    if feature == "scientific_claims":
        row = observed[feature]
        return {key: row[key] for key in ("funding_events", "evidence_receipt_events",
            "receipt_events_with_forwarded_cause", "resolved_trial_receipts", "completed_trial_receipts",
            "cancelled_trial_receipts", "failed_trial_receipts", "resolved_replication_receipts",
            "costs_attached_to_resolved_trials", "allocation_rows", "paid_seat_allocations",
            "allocation_funds", "reported_allocation_events", "current_policy_belief_rows",
            "belief_rows_with_declared_groups", "unique_declared_dependence_groups")}
    if feature == "health_care":
        row = observed[feature]
        return {k: row[k] for k in ("episode_turns", "new_injuries", "episode_retirements",
            "censored_episodes", "impaired_worker_turns", "care_worker_turns")}
    if feature == "ritual_gatherings":
        row = observed[feature]
        return {k: row[k] for k in ("occurrences", "held", "cancelled", "selected_attendances",
            "food", "funds", "contact_units", "bond_attempts", "arrival_receipts")}
    if feature == "harvest_forecasts":
        row = observed[feature]
        chains = row["report_chains"]
        scored = [r for r in chains if r["brier"] is not None
                  and r["resolved_turn"] is not None and r["resolved_turn"] >= start]
        return {"reports_observed_in_window": row["unique_report_ids"],
            "reports_issued_in_window": sum(r["issued_turn"] >= start for r in chains),
            "actual_deliveries_in_window": sum(r["delivered_turn"] is not None and r["delivered_turn"] >= start for r in chains),
            "closed_reports_in_window": sum(r["resolved_turn"] is not None and r["resolved_turn"] >= start for r in chains),
            "scored_reports_in_window": len(scored),
            "mean_recorded_brier": sum(r["brier"] for r in scored) / len(scored) if scored else None,
            "preparation_receipts": row["preparation_receipts"],
            "paid_preparation_receipts": row["paid_preparation_receipts"],
            "grain_bought_during_warnings": row["grain_bought_during_warnings"],
            "funds_paid_during_warnings": row["funds_paid_during_warnings"]}
    return {}


def _inspect(path, limits):
    raw, encoded = _read(path, limits.max_file_bytes)
    input_limited = False
    if isinstance(encoded, Mapping):
        field = "history_delta" if isinstance(encoded.get("history_delta"), list) else "history"
        values = encoded.get(field)
        if isinstance(values, list) and len(values) > limits.max_snapshots:
            encoded = {**encoded, field: values[:limits.max_snapshots]}
            input_limited = True
    bundle = decode_bundle(encoded)
    if not isinstance(bundle, Mapping):
        raise AuditError(f"{path.name} must contain a bundle object")
    metadata = bundle.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise AuditError("bundle metadata must be an object")
    receipt = metadata.get("expansion_experiment")
    if not isinstance(receipt, Mapping):
        receipt = {}
    feature = receipt.get("feature")
    feature = feature if isinstance(feature, str) and IDENTIFIER.fullmatch(feature) else None
    arm = receipt.get("arm")
    arm = arm if isinstance(arm, str) and IDENTIFIER.fullmatch(arm) else None
    experiment = receipt.get("experiment")
    experiment = experiment if isinstance(experiment, str) and IDENTIFIER.fullmatch(experiment) else None
    cohort = receipt.get("cohort") if receipt.get("cohort") in ("development", "confirmatory") else None
    seed = receipt.get("seed") if type(receipt.get("seed")) is int else None
    start = receipt.get("applied_before_turn") if type(receipt.get("applied_before_turn")) is int else None
    end = metadata.get("total_turns") if type(metadata.get("total_turns")) is int else None
    blockers = []
    if receipt.get("schema_version") != 1 or feature not in FEATURES:
        blockers.append("missing_or_unknown_experiment_receipt")
    if type(seed) is not int or seed != metadata.get("seed"):
        blockers.append("seed_receipt_mismatch")
    if arm is None:
        blockers.append("missing_arm")
    if receipt.get("cohort") not in ("development", "confirmatory"):
        blockers.append("unknown_cohort")
    if experiment is None:
        blockers.append("missing_experiment")
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        blockers.append("invalid_window")
    world = bundle.get("world_state")
    if isinstance(world, Mapping) and type(world.get("turn")) is int and world["turn"] != end:
        blockers.append("declared_horizon_mismatch")
    controls_before = _controls(receipt.get("controls_before"), feature, blockers)
    controls_after = _controls(receipt.get("controls_after"), feature, blockers)
    if controls_after is not None:
        expected = ({"normal": {"policy": "normal"}, "withheld": {"policy": "withhold"},
                     "shuffled": {"policy": "shuffle"}} if feature == "harvest_forecasts" else
                    {"normal": {"contact_enabled": True, "bonds_enabled": True},
                     "no_contact": {"contact_enabled": False, "bonds_enabled": True},
                     "no_bonds": {"contact_enabled": True, "bonds_enabled": False},
                     "cost_only": {"contact_enabled": False, "bonds_enabled": False}}
                    if feature == "ritual_gatherings" else
                    {"normal": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": False},
                     "withheld": {"withhold_information": True, "transmission_enabled": True, "uninformative_tests": False},
                     "no_transmission": {"withhold_information": False, "transmission_enabled": False, "uninformative_tests": False},
                     "uninformative": {"withhold_information": False, "transmission_enabled": True, "uninformative_tests": True}}
                    if feature == "scientific_claims" else
                    {"care": {"care_enabled": True}, "no_care": {"care_enabled": False}}).get(arm)
        if expected is not None and any(controls_after.get(k) != v for k, v in expected.items()):
            blockers.append("named_arm_control_mismatch")
    identity = _identity(receipt)
    if identity is None:
        blockers.append("source_or_binary_identity_unavailable")
    parent = receipt.get("parent_checkpoint")
    fork = receipt.get("intervention_fork") is True
    parent_view = None
    if fork:
        if not isinstance(parent, Mapping):
            blockers.append("parent_checkpoint_unavailable")
        else:
            digest = parent.get("sha256")
            parent_view = {"sha256": digest if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None,
                           "turn": parent.get("turn") if type(parent.get("turn")) is int else None,
                           "seed": parent.get("seed") if type(parent.get("seed")) is int else None,
                           "exact": parent.get("exact") is True}
            if (parent_view["sha256"] is None or parent_view["turn"] != start
                    or parent_view["seed"] != seed or not parent_view["exact"]):
                blockers.append("parent_boundary_or_exactness_mismatch")
            if _identity(parent.get("identity")) != identity:
                blockers.append("parent_source_or_binary_mismatch")
    else:
        blockers.append("fresh_parent_not_a_paired_intervention")
    parent_environment = None
    flags = None
    if isinstance(parent, Mapping):
        flags = parent.get("flags") if isinstance(parent.get("flags"), Mapping) else None
        if flags is not None and (len(flags) > 100 or any(not isinstance(k, str) or not k.isidentifier()
                                                        or type(v) is not bool for k, v in flags.items())):
            flags = None
        parent_identity = parent.get("identity")
        env = parent_identity.get("environment") if isinstance(parent_identity, Mapping) else None
        parent_environment = _environment(env)
        if flags is None or parent_environment is None:
            blockers.append("parent_flags_or_environment_unavailable")
    worker_path = path.parent / "worker_identity.json"
    worker_sha, worker_verified, environment, runner_sha = None, False, None, None
    before_env, after_env = None, None
    if worker_path.is_file():
        worker_raw, worker = _read(worker_path, limits.max_file_bytes)
        worker_sha = hashlib.sha256(worker_raw).hexdigest()
        if isinstance(worker, Mapping):
            candidate_runner = worker.get("runner_sha256")
            if candidate_runner is not None:
                if isinstance(candidate_runner, str) and re.fullmatch(r"[0-9a-f]{64}", candidate_runner):
                    runner_sha = candidate_runner
                else:
                    blockers.append("invalid_external_runner_identity")
            runner_after = worker.get("runner_sha256_after")
            if runner_after is not None:
                if not isinstance(runner_after, str) or not re.fullmatch(r"[0-9a-f]{64}", runner_after):
                    blockers.append("invalid_external_runner_identity")
                elif runner_sha is None or runner_after != runner_sha:
                    blockers.append("external_runner_changed")
            worker_verified = _identity(worker.get("before")) == identity == _identity(worker.get("after")) and identity is not None
            before = worker.get("before")
            after = worker.get("after")
            before_env = _environment(before.get("environment")) if isinstance(before, Mapping) else None
            after_env = _environment(after.get("environment")) if isinstance(after, Mapping) else None
            if before_env is None or after_env is None:
                blockers.append("worker_environment_unavailable")
            elif before_env != after_env:
                blockers.append("worker_environment_changed")
            else:
                environment = before_env
            if worker.get("environment_stable") is False or worker.get("identities_stable") is False:
                blockers.append("worker_reported_instability")
        if not worker_verified:
            blockers.append("worker_identity_changed_or_mismatched")
    else:
        blockers.append("worker_identity_unavailable")
        blockers.append("worker_environment_unavailable")
    declared_environment = _environment(receipt.get("environment"))
    if "environment" in receipt and declared_environment is None:
        blockers.append("declared_runtime_environment_invalid")
    if declared_environment is not None and environment != declared_environment:
        blockers.append("runtime_environment_mismatch")
    registration = receipt.get("registration")
    reg_hash = registration.get("sha256") if isinstance(registration, Mapping) else None
    if reg_hash is not None and (not isinstance(reg_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", reg_hash)):
        reg_hash = None
        blockers.append("invalid_registration_identity")
    if receipt.get("cohort") == "confirmatory" and not reg_hash:
        blockers.append("registration_identity_unavailable")
    full = audit_bundle(bundle, limits=limits)
    if full["finding_counts"]["error"]:
        blockers.append("record_integrity_failed")
    if not full["scan_complete"] or input_limited:
        blockers.append("full_audit_truncated")
    metrics, coverage, prefix_sha, final_world_sha = {}, None, None, None
    if "invalid_window" not in blockers:
        history = bundle.get("history") or []
        # No final-state backfill: treatment-window quantities come solely
        # from snapshots stamped after the intervention was applied.
        selected = [r for r in history if isinstance(r, Mapping) and type(r.get("turn")) is int
                    and start <= r["turn"] - 1 < end]
        window = audit_bundle({**bundle, "history": selected},
            limits=replace(limits, max_details=min(10000, limits.max_rows)))
        coverage = window["coverage"]["systems"].get(feature)
        window_complete = (coverage is not None and coverage["completed_turn_spans"] == [[start, end - 1]]
                           and coverage["recorded_snapshots"] == end - start)
        if not window_complete:
            blockers.append("incomplete_treatment_window")
        if not window["scan_complete"]:
            blockers.append("window_audit_truncated")
        if feature == "harvest_forecasts" and window["details_omitted"]["report_chains"]:
            blockers.append("forecast_chain_detail_limit")
        metrics = _window_metrics(feature, window["observed_mechanisms"], start)
        if feature == "scientific_claims":
            for row in selected:
                section = row.get(feature)
                if isinstance(section, Mapping) and controls_after is not None:
                    recorded = section.get("controls")
                    recorded = {**recorded, "publication_rule": section.get("publication_rule", LEGACY_RULE)} if isinstance(recorded, Mapping) else None
                    if recorded != controls_after:
                        blockers.append("science_snapshot_controls_mismatch")
            boundary = [row for row in history if isinstance(row, Mapping) and row.get("turn") == start]
            boundary_audit = audit_bundle({**bundle, "history": boundary}, as_of=AsOf.after(start - 1), limits=limits)
            boundary_science = boundary_audit["observed_mechanisms"][feature]
            before = (boundary_science["latest_cumulative_counters"]
                      if boundary_science["latest_counter_source_turn"] == start - 1
                      and boundary_audit["scan_complete"] and not boundary_audit["finding_counts"]["error"] else None)
            latest = window["observed_mechanisms"][feature]
            after = latest["latest_cumulative_counters"] if latest["latest_counter_source_turn"] == end - 1 else None
            for key in SCIENCE_COUNTERS:
                value = (after[key] - before[key] if before is not None and after is not None
                         and type(before.get(key)) is int and before[key] >= 0 else None)
                metrics["cumulative_" + key + "_change"] = value
        required_tables = {"health_care": ("regions",), "ritual_gatherings": ("outcomes", "schedules"),
                           "harvest_forecasts": ("reports", "outcomes", "preparedness"),
                           "scientific_claims": ("propositions", "trials_resolved", "beliefs", "allocations")}.get(feature, ())
        if any(window["verified_checks"].get(f"{feature}.{table}_recorded", {}).get("unavailable", 0)
               for table in required_tables):
            blockers.append("incomplete_feature_receipts")
            metrics = {key: None for key in metrics}
        if not window_complete or not window["scan_complete"] or input_limited:
            metrics = {key: None for key in metrics}
        prefix = [r for r in history if isinstance(r, Mapping) and type(r.get("turn")) is int and r["turn"] <= start]
        events = [r for r in bundle.get("events_timeline", []) if isinstance(r, Mapping)
                  and type(r.get("turn")) is int and r["turn"] < start]
        prefix_sha = _digest({"history": prefix, "events": events})
        if isinstance(bundle.get("world_state"), Mapping):
            # Equality of exported Python world state is a no-op check only;
            # it does not establish native pool or every output byte identity.
            final_world_sha = _digest(bundle["world_state"])
    return {"input_name": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "input_bytes": len(raw),
        "experiment": experiment, "feature": feature, "cohort": cohort,
        "seed": seed, "arm": arm, "intervention_fork": fork, "window": {"start": start, "end_exclusive": end},
        "controls_before": controls_before, "controls_after": controls_after, "identity": identity,
        "parent_checkpoint": parent_view, "flags": flags, "environment": environment,
        "worker_environment_before": before_env, "worker_environment_after": after_env,
        "parent_environment": parent_environment, "declared_runtime_environment": declared_environment,
        "registration_sha256": reg_hash, "worker_identity_sha256": worker_sha,
        "worker_source_binary_verified": worker_verified, "external_runner_sha256": runner_sha,
        "pre_intervention_prefix_sha256": prefix_sha,
        "final_exported_python_world_sha256": final_world_sha, "coverage": coverage, "metrics": metrics,
        "audit": {"status": "partial" if input_limited and full["status"] != "issues_found" else full["status"],
                  "finding_counts": full["finding_counts"],
                  "scan_complete": full["scan_complete"] and not input_limited,
                  "truncated_by": sorted(set(full["truncated_by"] + (["max_snapshots"] if input_limited else []))),
                  "findings": full["findings"][:10]},
        "blockers": sorted(set(blockers))}


def compare_paths(paths, *, baseline=None, max_runs=64, audit_limits=None):
    """Compare explicit files/directories; never follow paths embedded in receipts."""
    if type(max_runs) is not int or not 1 <= max_runs <= 512:
        raise AuditError("max_runs must be in 1..512")
    files = _discover(paths, max_runs)
    limits = audit_limits or Limits()
    runs = [_inspect(path, limits) for path in sorted(files)]
    for index, run in enumerate(runs):
        run["run_id"] = f"r{index}"
    groups = {}
    for run in runs:
        key = (run["feature"], run["experiment"], run["cohort"], run["seed"])
        groups.setdefault(key, []).append(run)
    pairs, noops = [], []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        feature, experiment, cohort, seed = key
        baseline_arm = baseline or BASELINES.get(feature)
        candidates = [r for r in group if r["arm"] == baseline_arm and r["intervention_fork"]]
        parents = [r for r in group if not r["intervention_fork"] and r["arm"] == "parent"]
        for run in group:
            if (run["intervention_fork"] and run["controls_before"] is not None
                    and run["controls_before"] == run["controls_after"] and len(parents) == 1):
                parent = parents[0]
                a, b = run["final_exported_python_world_sha256"], parent["final_exported_python_world_sha256"]
                equal = a == b if a is not None and b is not None else None
                noops.append({"seed": seed, "feature": feature, "fork_run": run["run_id"], "parent_run": parent["run_id"],
                              "final_exported_python_world_equal": equal,
                              "provenance_matched": run["identity"] is not None and run["identity"] == parent["identity"]
                                  and run["environment"] is not None and run["environment"] == parent["environment"]
                                  and run["worker_source_binary_verified"] and parent["worker_source_binary_verified"],
                              "scope": "Serialized Python world only; native pool and all output files unobserved"})
        arms = [r for r in group if r["intervention_fork"] and r["arm"] != baseline_arm]
        for arm in arms:
            blockers = list(arm["blockers"])
            base = candidates[0] if len(candidates) == 1 else None
            if base is None:
                blockers.append("baseline_missing_or_ambiguous")
            if sum(r["arm"] == arm["arm"] and r["intervention_fork"] for r in group) != 1:
                blockers.append("duplicate_arm_for_seed")
            if base is not None:
                blockers += base["blockers"]
                for field, code in (("identity", "source_or_binary_mismatch"), ("window", "window_mismatch"),
                    ("parent_checkpoint", "parent_checkpoint_mismatch"), ("flags", "feature_flag_mismatch"),
                    ("environment", "environment_mismatch"), ("registration_sha256", "registration_mismatch"),
                    ("parent_environment", "parent_environment_receipt_mismatch"),
                    ("pre_intervention_prefix_sha256", "pre_intervention_history_mismatch"),
                    ("controls_before", "parent_control_mismatch")):
                    if base[field] != arm[field]:
                        blockers.append(code)
                if feature == "health_care" and base["controls_after"] and arm["controls_after"]:
                    if any(base["controls_after"][k] != arm["controls_after"][k]
                           for k in FEATURES[feature] if k != "care_enabled"):
                        blockers.append("non_care_health_controls_differ")
                if feature == "scientific_claims" and base["controls_after"] and arm["controls_after"]:
                    if base["controls_after"]["publication_rule"] != arm["controls_after"]["publication_rule"]:
                        blockers.append("publication_rule_mismatch")
                if (base["external_runner_sha256"] is not None and arm["external_runner_sha256"] is not None
                        and base["external_runner_sha256"] != arm["external_runner_sha256"]):
                    blockers.append("external_runner_mismatch")
            blockers = sorted(set(blockers))
            deltas = None
            if not blockers:
                deltas = {key: (arm["metrics"][key] - value if type(value) in (int, float)
                    and type(arm["metrics"].get(key)) in (int, float) else None)
                    for key, value in base["metrics"].items()}
            pairs.append({"feature": feature, "experiment": experiment, "cohort": cohort, "seed": seed,
                "baseline_arm": baseline_arm, "arm": arm["arm"], "baseline_run": base["run_id"] if base else None,
                "arm_run": arm["run_id"], "comparable_recorded_window": not blockers,
                "blockers": blockers, "arm_minus_baseline": deltas})
    blocked = sum(not p["comparable_recorded_window"] for p in pairs)
    return {"schema_version": 1, "status": "descriptive_only" if pairs and not blocked else "blocked_or_unpaired",
        "interpretation": INTERPRETATION, "runs": runs, "pairs": pairs, "noop_checks": noops,
        "summary": {"input_runs": len(runs), "paired_seed_contrasts": len(pairs),
            "matched_contrasts": len(pairs) - blocked, "blocked_contrasts": blocked,
            "recorded_seed_ids": sorted({r["seed"] for r in runs if type(r["seed"]) is int}),
            "cohorts": sorted({r["cohort"] for r in runs if isinstance(r["cohort"], str)})},
        "limits": {"max_runs": max_runs, "per_bundle": asdict_limits(limits)},
        "limitations": ["Paired seeds are units; repeated turns, attendees, regions and forecast IDs are not independent replicates.",
            "Development cohorts are not confirmatory evidence. Registration identity is disclosed, not proof of preregistration quality.",
            "Embedded identities and worker receipts are producer assertions, not authenticated attestations.",
            "No causal efficacy, calibrated forecasting, clinical benefit or successful native friendship is inferred.",
            "Censoring and any unrecorded metric remain null rather than zero."]}


def _discover(paths, max_runs):
    if type(max_runs) is not int or not 1 <= max_runs <= 512:
        raise AuditError("max_runs must be in 1..512")
    files = []
    for raw in paths:
        path = Path(raw)
        candidates = path.rglob("chronicle_bundle.json") if path.is_dir() else [path]
        for candidate in candidates:
            files.append(candidate)
            if len(files) > max_runs:
                raise AuditError("input discovery exceeds max_runs; no partial comparison produced")
    if not files:
        raise AuditError("no bundle files supplied or discovered")
    # Same input given twice is a duplicate, not another independent run.
    seen = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            raise AuditError("a bundle input was supplied more than once")
        seen.add(resolved)
    return files


def asdict_limits(limits):
    from dataclasses import asdict
    return asdict(limits)


def render_markdown(report):
    lines = ["# Expansion experiment comparison", "", report["interpretation"], "",
        f"Status: **{_md(report['status'])}**; {_md(report['summary'])}.", "",
        "## Recorded runs", "", "| Run | Feature / arm / seed | Window | Source / package / native | Controls | Blockers |",
        "| --- | --- | --- | --- | --- | --- |"]
    for row in report["runs"]:
        lines.append(f"| {_md(row['run_id'])} | {_md(row['feature'])} / {_md(row['arm'])} / {_md(row['seed'])} | "
            f"{_md(row['window'])} | {_md(row['identity'])} | {_md(row['controls_after'])} | {_md(row['blockers'])} |")
    lines += ["", "## Exact provenance and coverage", ""]
    for row in report["runs"]:
        lines += [f"### {_md(row['run_id'])} — {_md(row['experiment'])} / {_md(row['arm'])}", "",
            f"Bundle {_md(row['input_name'])}, SHA-256 \u0060{row['sha256']}\u0060; {row['input_bytes']} bytes.",
            f"Source/package/native: {_md(row['identity'])}.",
            f"Parent checkpoint: {_md(row['parent_checkpoint'])}; worker receipt SHA {_md(row['worker_identity_sha256'])}, "
            f"source/binary match before/after {_md(row['worker_source_binary_verified'])}; registration SHA {_md(row['registration_sha256'])}.",
            f"External runner SHA: {_md(row['external_runner_sha256'])}.",
            f"Parent feature flags: {_md(row['flags'])}; parent environment: {_md(row['parent_environment'])}.",
            f"Measured worker environment: {_md(row['environment'])}; declared runtime environment: {_md(row['declared_runtime_environment'])}.",
            f"Captured worker environment before/after: {_md(row['worker_environment_before'])} → {_md(row['worker_environment_after'])}.",
            f"Controls before/after: {_md(row['controls_before'])} → {_md(row['controls_after'])}.",
            f"Post-fork coverage: {_md(row['coverage'])}; observed metrics: {_md(row['metrics'])}.",
            f"Record audit: {_md(row['audit'])}.", ""]
    lines += ["", "## Paired post-intervention contrasts", ""]
    for pair in report["pairs"]:
        lines.append(f"- {_md(pair['feature'])}, seed {_md(pair['seed'])}, {_md(pair['arm'])} minus "
            f"{_md(pair['baseline_arm'])}: " + (f"observed deltas {_md(pair['arm_minus_baseline'])}."
            if pair["comparable_recorded_window"] else f"withheld: {_md(pair['blockers'])}."))
    lines += ["", "## No-op fork checks", ""]
    for row in report["noop_checks"]:
        lines.append(f"- {_md(row['feature'])}, seed {row['seed']}: exported Python world equal "
                     f"{row['final_exported_python_world_equal']}; {_md(row['scope'])}.")
    lines += ["", "## Limits and interpretation", "", *[f"- {_md(s)}" for s in report["limitations"]]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Bundle files or study directories")
    parser.add_argument("--baseline")
    parser.add_argument("--max-runs", type=int, default=64)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        # Protect every source bundle/companion even when discovered in directories.
        source_files = _discover(args.inputs, args.max_runs)
        protected = source_files + [p.parent / "worker_identity.json" for p in source_files]
        outputs = [p for p in (args.json, args.markdown) if p is not None]
        for output in outputs:
            for source in protected:
                if output.resolve() == source.resolve() or (output.exists() and source.exists() and output.samefile(source)):
                    raise AuditError("report output must not overwrite a source bundle or worker receipt")
        if len(outputs) == 2 and (outputs[0].resolve() == outputs[1].resolve()
                or (outputs[0].exists() and outputs[1].exists() and outputs[0].samefile(outputs[1]))):
            raise AuditError("JSON and Markdown outputs must be different")
        report = compare_paths(source_files, baseline=args.baseline, max_runs=args.max_runs)
        js = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        md = render_markdown(report)
        for path, content in ((args.json, js), (args.markdown, md)):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        print(js if args.format == "json" else md, end="")
        return 0 if report["status"] == "descriptive_only" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"expansion-comparison: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
