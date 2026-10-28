#!/usr/bin/env python3
"""Read registered proof artifacts without generating or advancing a world."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from chronicler.bundle_codec import load_bundle
from chronicler.run_checkpoint import read_checkpoint


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def differences(a, b, path=""):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for key in a.keys() | b.keys() for p in (
            differences(a[key], b[key], f"{path}/{key}") if key in a and key in b else [f"{path}/{key}"])]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + "/length"]
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in differences(x, y, f"{path}/{i}")]
    return [] if a == b else [path]


def main(root, destination):
    report = json.loads((root / "report.json").read_text())
    errors = []
    for name, expected in report["files"].items():
        if sha(root / name) != expected:
            errors.append("changed recorded file: " + name)
    rows = []
    for seed in (42, 7):
        for arm in ("legacy_direct", "legacy_resume", "v2_fork", "v2_direct"):
            folder = root / f"seed-{seed}" / arm
            summary = json.loads((folder / "mechanical-summary.json").read_text())
            worker = json.loads((folder / "worker-identity.json").read_text())
            bundle = load_bundle(folder / "chronicle_bundle.json")
            history = bundle["history"]
            if [row["turn"] for row in history] != list(range(3, 17)):
                errors.append(f"{seed}/{arm}: history dates differ")
            if worker["before"] != worker["after"] or not worker["identities_stable"]:
                errors.append(f"{seed}/{arm}: worker identity changed")
            parent = root / f"seed-{seed}" / ("v2_direct" if arm == "v2_direct" else "legacy_direct") / "checkpoint_turn_3.ckpt"
            funded = {trial.id: trial.model_dump(mode="json") for trial in read_checkpoint(parent).state.world.scientific_claims.trials}
            frozen_fields = ("inputs", "control_output", "treatment_output", "source_data", "environment_block", "dependence_group")
            unchanged = all(all(trial[key] == funded[trial["id"]][key] for key in frozen_fields)
                            for trial in summary["trials"] if trial["id"] in funded)
            if not unchanged:
                errors.append(f"{seed}/{arm}: funded original measurements changed")
            current = []
            for snapshot in history:
                science = snapshot["scientific_claims"]
                beliefs = science["beliefs"]
                current.append(dict(source_turn=science["source_turn"], archived_receipts=science["evidence_receipts"],
                    policy_belief_rows=len(beliefs), policy_rows_with_groups=sum(row["independent_groups"] > 0 for row in beliefs),
                    confidence_values=sorted({row["confidence"] for row in beliefs}),
                    last_used_dates=sorted({row["last_evidence_turn"] for row in beliefs if row["last_evidence_turn"] is not None}),
                    allocations=science["allocations"]))
            last = history[-1]
            health = [row["health_care"] for row in history]
            transactions = last["transaction_receipts"]
            rows.append(dict(seed=seed, arm=arm, controls=summary["controls"], funded_original_inputs_retained=unchanged,
                trial_spent=summary["trial_spent"], effort_spent=summary["effort_spent"],
                trials=[{key: trial[key] for key in ("id", "claim", "seat", "parent", "payer", "funded_turn", "completion_turn",
                    "resolved_turn", "status", "cost", "control_output", "treatment_output", "observed_control", "observed_treatment", "supports")}
                    for trial in summary["trials"]],
                unresolved_trials=sum(trial["status"] == "running" for trial in summary["trials"]),
                archived_receipts=len(summary["receipts"]),
                remote_receipts=sum(row["sender"] != row["seat"] for row in summary["receipts"]),
                pending_science_messages=last["scientific_claims"]["pending_messages"],
                science_policy_by_source=current,
                health=dict(new_injuries=sum(row["new_injuries"] for row in health),
                    episode_retirements=sum(row["recoveries"] for row in health),
                    censored_episodes=sum(row["censored_episodes"] for row in health),
                    impaired_worker_turns=sum(row["impaired_work"] for row in health),
                    care_worker_turns=sum(row["care_work"] for row in health), active_episodes_at_end=health[-1]["episodes"]),
                forecast_counters=last["harvest_forecasts"]["counters"],
                gathering_counters=last["ritual_gatherings"]["counters"],
                transaction_counters=transactions["counters"],
                public_purchase_counters=transactions["public_purchases"]["counters"],
                transaction_complete_all_sources=all(row["transaction_receipts"]["complete"] for row in history),
                actual_resource_ledger_sidecar=(folder / "validation_resource_ledger.arrow").is_file()))
    scopes = []
    for seed in (42, 7):
        folder = root / f"seed-{seed}"
        a, b = (load_bundle(folder / arm / "chronicle_bundle.json") for arm in ("v2_direct", "v2_fork"))
        scopes.append(dict(seed=seed, v2_complete_bundle_difference_paths=differences(a, b)))
    result = dict(source_report_sha256=sha(root / "report.json"), errors=errors, runs=rows,
                  comparison_scope_details=scopes, reader_sha256=sha(__file__))
    destination.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(dict(errors=errors, runs=len(rows), output=str(destination))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    options = parser.parse_args()
    main(options.root, options.destination)
