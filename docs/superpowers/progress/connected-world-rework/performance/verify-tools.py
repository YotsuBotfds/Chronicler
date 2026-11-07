#!/usr/bin/env python3
"""Synthetic negative controls for the measurement/admission tools, not a run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.write_text(json.dumps(value, separators=(",", ":")))


def profile_write(directory, profile):
    profile["bundle_bytes"] = (directory / "chronicle_bundle.json").stat().st_size
    profile["state_bytes"] = (directory / "state.json").stat().st_size
    write_json(directory / "profile.json", profile)
    with (directory / "turns.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_turn", "wall_seconds", "cpu_seconds", "native_agents"))
        writer.writeheader()
        writer.writerows(profile["turns"])


def fixture(directory, timestamp):
    import chronicler
    directory.mkdir()
    bundle = {"history": [{"turn": 1, "livelihoods": {"test": {"agent_id": 7, "unknown": None, "signed_zero": 0.0}}}],
              "metadata": {"generated_at": timestamp, "bundle_version": 6}}
    write_json(directory / "chronicle_bundle.json", bundle)
    write_json(directory / "state.json", {"agent_id": 7, "wealth": 2.0})
    profile = {"case": {"name": "synthetic-off", "arm": "off", "turns": 1, "checkpoints": [1], "cli": []},
               "identity": {"native_sha256": "a" * 64, "python_version": sys.version,
                            "python_source": str(Path(chronicler.__file__).resolve())},
               "source_snapshot": {"commit": "synthetic", "sha256": "b" * 64},
               "run_cpu_seconds": 1.0, "run_wall_seconds": 1.0, "run_peak_rss_kib": 100.0,
               "native_initial_agents": 100, "native_peak_agents": 100,
               "turns": [{"source_turn": 0, "wall_seconds": .5, "cpu_seconds": .5, "native_agents": 100}],
               "extraction_problems": []}
    profile_write(directory, profile)
    stage_rows = [{"source_turn": None, "scope": "outside_turn", "stage": stage, "calls": 1,
                   "timed": True, "cpu_seconds": .1, "wall_seconds": .1}
                  for stage in ("bundle_assembly", "bundle_write", "history_encoding")]
    write_json(directory / "stage-timings.json", {"all_calls_recorded": True, "cumulative_not_additive": True,
        "instrumented_stages": {row["stage"]: {"timed": row["timed"]} for row in stage_rows}, "rows": stage_rows})
    with (directory / "stages.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=stage_rows[0])
        writer.writeheader()
        writer.writerows(stage_rows)
    checkpoint = directory / "checkpoint_turn_1.ckpt"
    checkpoint.write_bytes(b"Synthetic comparator-control artifact; not a simulator checkpoint")
    write_json(directory / "checkpoint-semantics.json", {"same_source_exact_reads_only": True, "checkpoints": {
        checkpoint.name: {"turn": 1, "exact": True, "artifact_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            "world_json_sha256": "d" * 64, "history_json_sha256": "e" * 64,
            "native_raw_sha256": {"native.agent.0": "f" * 64},
            "livelihood_checkpoint_components": {name: "1" * 64 for name in
                ("residence_ledger", "adaptive_livelihoods", "public_health", "war_requisition", "timber_orders")},
            "other_authority_components": {"health_care": "2" * 64}, "flags": {}, "run_config": {}}}})
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("choose a new verification receipt")
    here = Path(__file__).resolve().parent
    runner = load("cwr_measurement", here / "profile-rework.py")
    comparator = load("cwr_admission", here / "compare-profiles.py")
    checks = []
    module = runner.core(args.source_root.resolve())
    cases = [case for case in module.configurations(args.source_root.resolve()) if case["world"] in runner.WORLDS]
    assert len(cases) == 10
    for case in cases:
        if case["arm"] == "full":
            assert all(runner.option(case["cli"], key) == value for key, value in runner.OPTIONS.items())
        else:
            assert all(key not in case["cli"] for key in (*runner.OPTIONS, "--household-retail-mode"))
    assert {(c["world"], c["turns"], c["regions"], c["civs"], c["target"]) for c in cases} == {
        ("template_s5", 200, 8, 4, 0), ("proc32_s19", 200, 32, 10, 0),
        ("scaled22k_s42", 30, 12, 4, 18800), ("scaled52k_s7", 20, 12, 4, 43700),
        ("proc48_s42", 150, 48, 10, 0)}
    checks.append("all ten fixed corrected/OFF cases and complete scales/horizons")
    assert runner.cpu_limit_seconds(450.0) == 450
    assert runner.cpu_limit_seconds(0.1) == 1
    assert runner.cpu_limit_seconds(450.1) == 451
    for invalid in (0, -1, float("nan"), float("inf")):
        try:
            runner.cpu_limit_seconds(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid process-CPU limit accepted")
    checks.append("kernel CPU budget rejects invalid limits and rounds up to whole seconds")
    with tempfile.TemporaryDirectory(prefix="cwr-measurement-controls-") as temporary:
        root = Path(temporary)

        def check(name, mutation=None, reason=None):
            index = len(checks)
            before, after = root / f"before-{index}", root / f"after-{index}"
            fixture(before, "before")
            current = fixture(after, "after")
            if mutation:
                mutation(after, current)
            try:
                result = comparator.compare(before, after)
            except (ValueError, FileNotFoundError) as error:
                assert reason and reason in str(error), (name, str(error), reason)
            else:
                if reason:
                    assert not result["passed"] and any(reason in problem for problem in result["problems"]), (name, result)
                else:
                    assert result["passed"], result
            checks.append(name)

        def change_bundle(directory, profile, field, value):
            bundle = json.loads((directory / "chronicle_bundle.json").read_text())
            bundle["history"][0]["livelihoods"]["test"][field] = value
            write_json(directory / "chronicle_bundle.json", bundle)
            profile_write(directory, profile)

        check("generated timestamp alone is normalized")
        check("unknown to zero rejected", lambda d, p: change_bundle(d, p, "unknown", 0), "decoded complete bundle differs")
        check("stable person identity change rejected", lambda d, p: change_bundle(d, p, "agent_id", 8), "decoded complete bundle differs")
        check("signed zero change rejected", lambda d, p: change_bundle(d, p, "signed_zero", -0.0), "decoded complete bundle differs")

        def native(directory, profile):
            profile["identity"]["native_sha256"] = "c" * 64
            profile_write(directory, profile)

        check("different native artifact rejected", native, "native artifact differs")

        def flags(directory, profile):
            profile["case"]["cli"] = ["--disable-something"]
            profile_write(directory, profile)

        check("changed physical flags rejected", flags, "declared case/flags/scale/horizon differ")

        def trajectory(directory, profile):
            profile["turns"][0]["native_agents"] = 99
            profile_write(directory, profile)

        check("different actual population trajectory rejected", trajectory, "actual native population trajectory differs")

        def horizon(directory, profile):
            profile["turns"] = []
            profile_write(directory, profile)

        check("missing whole-turn observations rejected", horizon, "per-turn measurement is incomplete")
        check("truncated whole CSV rejected", lambda d, p: (d / "turns.csv").write_text("source_turn,wall_seconds,cpu_seconds,native_agents\n"),
              "whole per-turn CSV differs")
        check("reported artifact size must match actual bytes", lambda d, p: write_json(d / "profile.json", {**p, "bundle_bytes": 1}),
              "reported bundle_bytes differs")

        def unknown_cost(directory, profile):
            rows = json.loads((directory / "stage-timings.json").read_text())
            rows["instrumented_stages"]["trade_people"] = {"timed": False}
            rows["rows"].append({"source_turn": 0, "scope": "simulation", "stage": "trade_people", "calls": 1,
                                 "timed": False, "cpu_seconds": 0.0, "wall_seconds": 0.0})
            write_json(directory / "stage-timings.json", rows)
            with (directory / "stages.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows["rows"][0])
                writer.writeheader()
                writer.writerows(rows["rows"])

        check("untimed helper cost cannot be fabricated as zero", unknown_cost, "untimed helper cost was fabricated")

        def private_state(directory, profile):
            data = json.loads((directory / "checkpoint-semantics.json").read_text())
            data["checkpoints"]["checkpoint_turn_1.ckpt"]["livelihood_checkpoint_components"]["residence_ledger"] = "3" * 64
            write_json(directory / "checkpoint-semantics.json", data)

        check("private X1 checkpoint state cannot change unseen", private_state, "checkpoint semantic/native/authority components differ")
        check("checkpoint artifact remains bound to its exact-read receipt",
              lambda d, p: (d / "checkpoint_turn_1.ckpt").write_bytes(b"changed"),
              "checkpoint artifact differs")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"kind": "synthetic measurement-tool controls; no simulation/native runtime",
        "passed": True, "checks": checks, "count": len(checks), "source_root": str(args.source_root.resolve()),
        "python": sys.version, "tools": {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
        for name in ("profile-rework.py", "compare-profiles.py", "verify-tools.py")}}, indent=2) + "\n")
    print(json.dumps({"passed": True, "checks": len(checks), "out": str(args.out)}))


if __name__ == "__main__":
    main()
