#!/usr/bin/env python3
"""Strict same-configuration performance admission; timing alone never passes.

Use the optimized decoder on both old and new supported bundle encodings.
Only metadata.generated_at is normalized. Checkpoint envelopes have different
source identities; their actual native state and same-source semantic exports
must agree, including private X1 rows and other persisted livelihood state.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
from pathlib import Path
import re


MEASUREMENTS = {"plan.json", "profile.json", "run.log", "turns.csv", "stages.csv",
                "stage-timings.json", "checkpoint-semantics.json"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def decoded_bundle(path):
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(path)
    bundle["metadata"]["generated_at"] = None
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    for chunk in encoder.iterencode(bundle):
        digest.update(chunk.encode())
    result = {"sha256": digest.hexdigest(), "snapshots": len(bundle["history"]),
              "normalizations": ["metadata.generated_at only"]}
    del bundle
    gc.collect()
    return result


def files(directory):
    return {p.relative_to(directory).as_posix(): p for p in directory.rglob("*")
            if p.is_file() and p.name not in MEASUREMENTS and p.suffix != ".ckpt"}


def stages(directory):
    data = json.loads((directory / "stage-timings.json").read_text())
    if data.get("all_calls_recorded") is not True or data.get("cumulative_not_additive") is not True:
        raise ValueError("stage timing receipt does not state its measurement scope")
    rows = data["rows"]
    with (directory / "stages.csv").open(newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    decoded = [{"source_turn": int(row["source_turn"]) if row["source_turn"] else None,
                "scope": row["scope"], "stage": row["stage"], "calls": int(row["calls"]),
                "timed": {"True": True, "False": False}[row["timed"]],
                "cpu_seconds": float(row["cpu_seconds"]) if row["cpu_seconds"] else None,
                "wall_seconds": float(row["wall_seconds"]) if row["wall_seconds"] else None}
               for row in csv_rows]
    if decoded != rows:
        raise ValueError("whole stage CSV differs from its complete measurement receipt")
    totals = {}
    for row in rows:
        if data.get("instrumented_stages", {}).get(row["stage"]) != {"timed": row["timed"]}:
            raise ValueError("stage receipt differs from the declared measurement scope")
        value = totals.setdefault(row["stage"], {"calls": 0, "timed": row["timed"],
            "cpu_seconds": 0.0 if row["timed"] else None, "wall_seconds": 0.0 if row["timed"] else None})
        value["calls"] += row["calls"]
        if row["timed"]:
            value["cpu_seconds"] += row["cpu_seconds"]
            value["wall_seconds"] += row["wall_seconds"]
        elif row["cpu_seconds"] is not None or row["wall_seconds"] is not None:
            raise ValueError("untimed helper cost was fabricated rather than left null")
    return totals


def complete_measurements(directory, profile, stage_totals):
    expected = profile["case"]["turns"]
    rows = profile["turns"]
    if len(rows) != expected or [row["source_turn"] for row in rows] != list(range(expected)):
        raise ValueError("per-turn measurement is incomplete or misdated")
    with (directory / "turns.csv").open(newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    decoded = [{"source_turn": int(row["source_turn"]), "wall_seconds": float(row["wall_seconds"]),
                "cpu_seconds": float(row["cpu_seconds"]), "native_agents": int(row["native_agents"])}
               for row in csv_rows]
    if decoded != rows:
        raise ValueError("whole per-turn CSV differs from the complete measurement receipt")
    if any(not math.isfinite(profile[key]) or profile[key] <= 0
           for key in ("run_cpu_seconds", "run_wall_seconds", "run_peak_rss_kib")):
        raise ValueError("unavailable or invalid whole-run timing/RSS")
    for filename, key in (("chronicle_bundle.json", "bundle_bytes"), ("state.json", "state_bytes")):
        if (directory / filename).stat().st_size != profile[key]:
            raise ValueError(f"reported {key} differs from the actual saved artifact")
    for stage in ("bundle_assembly", "bundle_write", "history_encoding"):
        if stage_totals.get(stage, {}).get("calls") != 1:
            raise ValueError(f"missing or duplicate complete-stage timing: {stage}")
    if profile["case"]["arm"] == "full" and stage_totals.get("timber_planning", {}).get("calls") != expected:
        raise ValueError("FULL timber-planning stage measurement is incomplete")


def compare(before, after):
    previous = json.loads((before / "profile.json").read_text())
    current = json.loads((after / "profile.json").read_text())
    from chronicler import bundle_codec
    expected_package = Path(current["identity"]["python_source"]).resolve().parent
    if Path(bundle_codec.__file__).resolve().parent != expected_package:
        raise ValueError("comparison decoder must come from the measured optimized source")
    problems = []
    if previous["case"] != current["case"]:
        problems.append("declared case/flags/scale/horizon differ")
    if previous["identity"]["native_sha256"] != current["identity"]["native_sha256"]:
        problems.append("native artifact differs; not an isolated Python optimization comparison")
    if previous["identity"]["python_version"] != current["identity"]["python_version"]:
        problems.append("interpreter differs")
    if [row["native_agents"] for row in previous["turns"]] != [row["native_agents"] for row in current["turns"]]:
        problems.append("actual native population trajectory differs")
    if previous.get("extraction_problems") or current.get("extraction_problems"):
        problems.append("strict integrated extraction did not pass")
    left, right = files(before), files(after)
    if left.keys() != right.keys():
        problems.append(f"output inventory differs: {sorted(left.keys() ^ right.keys())}")
    byte_equal, different = [], []
    for name in sorted(left.keys() & right.keys()):
        if name == "chronicle_bundle.json":
            continue
        (byte_equal if sha(left[name]) == sha(right[name]) else different).append(name)
    if different:
        problems.append(f"non-bundle simulation outputs differ: {different}")
    bundle_before, bundle_after = decoded_bundle(before / "chronicle_bundle.json"), decoded_bundle(after / "chronicle_bundle.json")
    if bundle_before != bundle_after:
        problems.append("decoded complete bundle differs after timestamp-only normalization")
    checkpoint_before = json.loads((before / "checkpoint-semantics.json").read_text())
    checkpoint_after = json.loads((after / "checkpoint-semantics.json").read_text())
    for data, profile in ((checkpoint_before, previous), (checkpoint_after, current)):
        if data.get("same_source_exact_reads_only") is not True:
            raise ValueError("checkpoint receipt does not establish exact same-source reads")
        if len(data["checkpoints"]) != len(profile["case"]["checkpoints"]):
            raise ValueError("declared checkpoints remain unmeasured")
        if sorted(row["turn"] for row in data["checkpoints"].values()) != sorted(profile["case"]["checkpoints"]):
            raise ValueError("checkpoint semantic dates differ from the declared boundaries")
        if any(row.get("exact") is not True or not row.get("native_raw_sha256")
               for row in data["checkpoints"].values()):
            raise ValueError("checkpoint native identity or exact restore unavailable")
        for row in data["checkpoints"].values():
            if not {"residence_ledger", "adaptive_livelihoods", "public_health", "war_requisition", "timber_orders"}.issubset(
                    row.get("livelihood_checkpoint_components", {})):
                raise ValueError("checkpoint omits private or persisted authority evidence")
            hashes = [row.get("world_json_sha256"), row.get("history_json_sha256"),
                      *row["native_raw_sha256"].values(), *row["livelihood_checkpoint_components"].values(),
                      *row.get("other_authority_components", {}).values()]
            if any(not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None for value in hashes):
                raise ValueError("checkpoint semantic/native hashes are unavailable or malformed")
    for directory, data in ((before, checkpoint_before), (after, checkpoint_after)):
        for name, checkpoint in data["checkpoints"].items():
            if sha(directory / name) != checkpoint.get("artifact_sha256"):
                raise ValueError("checkpoint artifact differs from its exact-read semantic receipt")

    def semantic(data):
        # Whole-file hashes include each build's different envelope identity.
        # Keep and verify them above; compare every exported actual value here.
        return {name: {key: value for key, value in row.items() if key != "artifact_sha256"}
                for name, row in data["checkpoints"].items()}

    if semantic(checkpoint_before) != semantic(checkpoint_after):
        problems.append("checkpoint semantic/native/authority components differ")
    old_stages, new_stages = stages(before), stages(after)
    complete_measurements(before, previous, old_stages)
    complete_measurements(after, current, new_stages)
    return {"case": current["case"], "passed": not problems, "problems": problems,
            "before_source": previous["source_snapshot"], "after_source": current["source_snapshot"],
            "native_sha256": current["identity"]["native_sha256"],
            "before": {key: previous[key] for key in ("run_cpu_seconds", "run_wall_seconds", "run_peak_rss_kib", "bundle_bytes", "state_bytes", "native_initial_agents", "native_peak_agents")},
            "after": {key: current[key] for key in ("run_cpu_seconds", "run_wall_seconds", "run_peak_rss_kib", "bundle_bytes", "state_bytes", "native_initial_agents", "native_peak_agents")},
            "ratios_after_over_before": {key: current[key] / previous[key] for key in ("run_cpu_seconds", "run_wall_seconds", "run_peak_rss_kib", "bundle_bytes")},
            "whole_non_bundle_byte_equal": byte_equal, "non_bundle_differences": different,
            "decoded_bundle_before": bundle_before, "decoded_bundle_after": bundle_after,
            "same_source_checkpoint_count": len(checkpoint_after["checkpoints"]),
            "checkpoint_components_equal": semantic(checkpoint_before) == semantic(checkpoint_after),
            "checkpoint_artifact_hashes_before": {name: row["artifact_sha256"] for name, row in checkpoint_before["checkpoints"].items()},
            "checkpoint_artifact_hashes_after": {name: row["artifact_sha256"] for name, row in checkpoint_after["checkpoints"].items()},
            "cumulative_stages_not_additive": True, "stage_totals_before": old_stages,
            "stage_totals_after": new_stages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("choose a new comparison receipt")
    before = json.loads((args.before / "runs.json").read_text())
    after = json.loads((args.after / "runs.json").read_text())
    old = {row["name"]: row for row in before}
    new = {row["name"]: row for row in after}
    old_plan = json.loads((args.before / "plan.json").read_text())
    new_plan = json.loads((args.after / "plan.json").read_text())
    if old_plan["cases"] != new_plan["cases"]:
        raise ValueError("planned cases and controls differ")
    if not old or old.keys() != new.keys() or len(old) != len(before) or len(new) != len(after):
        raise ValueError("missing or duplicate case outcomes")
    if set(old) != {case["name"] for case in old_plan["cases"]}:
        raise ValueError("planned cases remain unrun")
    if any(row["exit_code"] != 0 for row in [*before, *after]):
        raise ValueError("a failed case cannot enter a speedup comparison")
    for root, records in ((args.before, before), (args.after, after)):
        for record in records:
            directory = root / record["name"]
            actual = {p.relative_to(directory).as_posix(): p for p in directory.rglob("*") if p.is_file()}
            if actual.keys() != record["files"].keys():
                raise ValueError("case inventory differs from the recorded producer manifest")
            for name, path in actual.items():
                saved = record["files"][name]
                if path.stat().st_size != saved["bytes"] or sha(path) != saved["sha256"]:
                    raise ValueError(f"artifact changed after measurement: {directory / name}")
            plan = json.loads((directory / "plan.json").read_text())
            profile = json.loads((directory / "profile.json").read_text())
            if plan["case"] != profile["case"] or plan["source_snapshot"] != profile["source_snapshot"] \
                    or plan["native_sha256"] != profile["identity"]["native_sha256"]:
                raise ValueError("case/source/native metadata differs from its frozen producer plan")
    results = [compare(args.before / name, args.after / name) for name in sorted(old)]
    result = {"kind": "same-configuration complete-evidence optimization admission",
              "passed": all(row["passed"] for row in results), "cases": results,
              "timing_note": "Single serial runs, process CPU and shared-host wall separated; no qualification or universal speed guarantee."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "cases": len(results), "out": str(args.out)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
