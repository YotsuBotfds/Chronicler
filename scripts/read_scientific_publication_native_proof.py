#!/usr/bin/env python3
"""Read registered proof artifacts without generating or advancing a world."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from chronicler.bundle_codec import load_bundle
from chronicler.run_checkpoint import read_checkpoint


def sha(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(block)
    return checksum.hexdigest()


MAX_FILES = 4096
MAX_PATH_CHARS = 1024
MAX_REPORT_BYTES = 8 << 20
MAX_FILE_BYTES = 128 << 20
MAX_TOTAL_BYTES = 512 << 20


class EvidenceInputs:
    """Bounded evidence paths with an exclusive output outside their root."""

    def __init__(self, root, destination):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("evidence root must be a directory")
        self.destination = self._destination(destination)
        self.report_path = self._resolve("report.json")
        if self.report_path.stat().st_size > MAX_REPORT_BYTES:
            raise ValueError("report exceeds the reader byte limit")
        raw = self.report_path.read_bytes()
        self.report_sha256 = hashlib.sha256(raw).hexdigest()
        self.report = json.loads(raw)
        members = self.report.get("files") if isinstance(self.report, dict) else None
        if not isinstance(members, dict) or len(members) > MAX_FILES:
            raise ValueError("report files must be a bounded inventory")
        self.members, self.paths = members, {}
        total = 0
        for name, expected in members.items():
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("inventory requires SHA-256 content identities")
            path = self._resolve(name)
            total += path.stat().st_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("inventory exceeds the total byte limit")
            if sha(path) != expected:
                raise ValueError("changed recorded file: " + name)
            self.paths[name] = path

    def _destination(self, destination):
        candidate = Path(destination)
        # Includes dangling symlinks and existing hard-link aliases.
        if os.path.lexists(candidate):
            raise FileExistsError("reader destination must not already exist")
        parent = candidate.parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError("reader destination parent must be a directory")
        resolved = parent / candidate.name
        if resolved.is_relative_to(self.root):
            raise ValueError("reader destination must be outside evidence root")
        return resolved

    def _resolve(self, name):
        if (not isinstance(name, str) or not name or len(name) > MAX_PATH_CHARS
                or "\\" in name or PureWindowsPath(name).drive
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or str(PurePosixPath(name)) != name or name == "."):
            raise ValueError("inventory members must be bounded relative file paths")
        resolved = (self.root / name).resolve(strict=True)
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError("inventory member escapes evidence root or is not a file")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("inventory member exceeds the file byte limit")
        return resolved

    def input(self, name):
        if name not in self.paths:
            raise ValueError("reader input is missing from recorded inventory: " + name)
        path = self._resolve(name)
        if path != self.paths[name]:
            raise ValueError("recorded input path changed during read")
        return path

    def write_result(self, result):
        payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if self._resolve("report.json") != self.report_path or sha(self.report_path) != self.report_sha256:
            raise ValueError("report changed during read")
        for name, expected in self.members.items():
            if sha(self.input(name)) != expected:
                raise ValueError("changed recorded file before write: " + name)
        destination = self._destination(self.destination)
        # Exclusive creation also rejects a file or alias appearing after validation.
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(payload)


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
    evidence = EvidenceInputs(root, destination)
    errors = []
    rows = []
    for seed in (42, 7):
        for arm in ("legacy_direct", "legacy_resume", "v2_fork", "v2_direct"):
            prefix = f"seed-{seed}/{arm}/"
            summary = json.loads(evidence.input(prefix + "mechanical-summary.json").read_text())
            worker = json.loads(evidence.input(prefix + "worker-identity.json").read_text())
            bundle = load_bundle(evidence.input(prefix + "chronicle_bundle.json"))
            history = bundle["history"]
            if [row["turn"] for row in history] != list(range(3, 17)):
                errors.append(f"{seed}/{arm}: history dates differ")
            if worker["before"] != worker["after"] or not worker["identities_stable"]:
                errors.append(f"{seed}/{arm}: worker identity changed")
            parent_arm = "v2_direct" if arm == "v2_direct" else "legacy_direct"
            parent = evidence.input(f"seed-{seed}/{parent_arm}/checkpoint_turn_3.ckpt")
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
                actual_resource_ledger_sidecar=evidence.input(prefix + "validation_resource_ledger.arrow").is_file()))
    scopes = []
    for seed in (42, 7):
        a, b = (load_bundle(evidence.input(f"seed-{seed}/{arm}/chronicle_bundle.json")) for arm in ("v2_direct", "v2_fork"))
        scopes.append(dict(seed=seed, v2_complete_bundle_difference_paths=differences(a, b)))
    result = dict(source_report_sha256=evidence.report_sha256, errors=errors, runs=rows,
                  comparison_scope_details=scopes, reader_sha256=sha(__file__))
    evidence.write_result(result)
    print(json.dumps(dict(errors=errors, runs=len(rows), output=str(destination))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    options = parser.parse_args()
    main(options.root, options.destination)
