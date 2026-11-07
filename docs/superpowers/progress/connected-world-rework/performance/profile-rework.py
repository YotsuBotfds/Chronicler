#!/usr/bin/env python3
"""Serial, frozen-source CWR profiles using the established declared-scale tool.

Only measurement wrappers and explicit CLI choices change. No simulator proxy,
record truncation, world-size reduction or default/parser modification is used.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pickle
import resource
import subprocess
import sys
import time

WORLDS = {"template_s5", "proc32_s19", "scaled22k_s42", "scaled52k_s7", "proc48_s42"}
OPTIONS = {"--adaptive-livelihoods-rules": "3",
           "--adaptive-livelihoods-decision-channels": "all",
           "--public-health-crowding": "density_only"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def option(flags, key):
    values = [flags[index + 1] for index, value in enumerate(flags) if value == key and index + 1 < len(flags)]
    return values[-1] if values else None


def cpu_limit_seconds(remaining):
    """A kernel process-CPU ceiling, rounded up to RLIMIT_CPU's seconds."""
    if not math.isfinite(remaining) or remaining <= 0:
        raise ValueError("remaining CPU budget must be finite and positive")
    return math.ceil(remaining)


def core(source, *, expected_case=None):
    path = source / "scripts/cw_program_profile.py"
    spec = importlib.util.spec_from_file_location("cwr_profile_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_screen = module.screen
    original_snapshot = module.snapshot

    def snapshot(root):
        result = original_snapshot(root)
        digest = hashlib.sha256(result["sha256"].encode() + b"\0")
        validation = {}
        for relative in ("scripts/cw_rework_screen.py", "scripts/cw_health_screen.py", "scripts/screen_runner.py"):
            path = root / relative
            validation[relative] = sha(path)
            digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
        return {**result, "base_sha256": result["sha256"], "sha256": digest.hexdigest(),
                "files": result["files"] + len(validation), "validation_sha256": validation}

    module.snapshot = snapshot

    cwr_path = source / "scripts/cw_rework_screen.py"
    cwr_spec = importlib.util.spec_from_file_location("cwr_profile_validator", cwr_path)
    cwr = importlib.util.module_from_spec(cwr_spec)
    # Its sibling screen modules use the checkout's scripts directory.
    sys.path.insert(0, str(cwr_path.parent))
    cwr_spec.loader.exec_module(cwr)

    def screen(root):
        screen_module = original_screen(root)
        screen_module.BASE = tuple(cwr.BASE)
        full = tuple(cwr.ARMS["AD"][0])
        if any(option([*cwr.BASE, *full], key) != value for key, value in OPTIONS.items()):
            raise ValueError("CWR AD does not explicitly select the declared corrected profile options")
        screen_module.ARMS = {"FULL": (full, None)}

        def extract(bundle, flags):
            observations, problems = cwr.extract(bundle, flags,
                expected_turns=expected_case["turns"] if expected_case is not None else None)
            if expected_case is not None:
                if bundle.get("metadata", {}).get("seed") != expected_case["seed"]:
                    problems.append("profile metadata seed differs from the declared case")
                if len(bundle.get("world_state", {}).get("regions", [])) != expected_case["regions"]:
                    problems.append("profile world region count differs from the declared case")
            return observations, problems

        screen_module.extract = extract
        return screen_module

    module.screen = screen
    # The established OFF control removes the complete Connected World stack,
    # including these newly explicit parameters; it retains the prior chain.
    module.PROGRAM_FLAGS.update({key: 1 for key in OPTIONS})
    module.PROGRAM_FLAGS["--household-retail-mode"] = 1
    return module


def child(plan_path):
    plan = json.loads(Path(plan_path).read_text())
    limit = cpu_limit_seconds(plan["remaining_cpu_budget_seconds"])
    if limit != plan["kernel_cpu_limit_seconds"]:
        raise RuntimeError("CPU limit differs from the frozen measurement plan")
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    if sha(__file__) != plan["wrapper_sha256"]:
        raise RuntimeError("measurement wrapper changed after planning")
    source, out = Path(plan["source"]), Path(plan["out"])
    module = core(source, expected_case=plan["case"])
    module.verify(source, plan["source_snapshot"], plan["native_sha256"])
    import chronicler.main as cm
    from chronicler import bundle_codec, run_checkpoint, timber_orders, titled_trade

    # These timers are cumulative, so nested stage times must not be added.
    # Counts and time are recorded for every call, never sampled.
    active_turn = None
    stages = {}
    restored = {}

    def json_digest(value):
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    def history_digest(history):
        digest = hashlib.sha256(b"[")
        for index, row in enumerate(history):
            if index:
                digest.update(b",")
            value = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
            digest.update(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"]")
        return digest.hexdigest()

    original_read = run_checkpoint.read_checkpoint

    def read(path, **kwargs):
        # The established child already reads every checkpoint against the same
        # source. Export semantic evidence from those exact reads; never bypass
        # an identity refusal or load one build's pickle under another build.
        loaded = original_read(path, **kwargs)
        if not loaded.exact or loaded.mismatches:
            raise RuntimeError("profile checkpoint was not an exact same-source restore")
        state = loaded.state
        header, body = run_checkpoint.read_header(Path(path))
        native = {section["name"]: hashlib.sha256(run_checkpoint._section(
            Path(path), header, body, section["name"])).hexdigest()
            for section in header["sections"] if section["name"].startswith("native.")}
        livelihood = getattr(state.world, "livelihoods", None)
        components = ({name: hashlib.sha256(pickle.dumps(getattr(livelihood, name), protocol=5)).hexdigest()
                       for name in type(livelihood).model_fields} if livelihood is not None else {})
        authorities = {name: hashlib.sha256(pickle.dumps(getattr(state.world, name, None), protocol=5)).hexdigest()
                       for name in ("health_care", "grain_reserves", "war_state", "household_mobility",
                                    "transaction_receipts", "scientific_claims")}
        restored[Path(path).name] = {"turn": state.world.turn, "exact": True, "artifact_sha256": sha(path),
            "world_json_sha256": json_digest(state.world), "history_json_sha256": history_digest(state.history),
            "native_raw_sha256": native, "livelihood_checkpoint_components": components,
            "other_authority_components": authorities, "flags": header["flags"], "run_config": header["run_config"]}
        return loaded

    run_checkpoint.read_checkpoint = read

    instrumented = {}

    def instrument(owner, attribute, label, *, timed=True):
        original = getattr(owner, attribute)
        instrumented[label] = {"timed": timed}

        def measured(*args, **kwargs):
            if timed:
                start_cpu, start_wall = time.process_time(), time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                key = (active_turn, label)
                row = stages.setdefault(key, {"calls": 0, "timed": timed,
                    "cpu_seconds": 0.0 if timed else None, "wall_seconds": 0.0 if timed else None})
                row["calls"] += 1
                if timed:
                    row["cpu_seconds"] += time.process_time() - start_cpu
                    row["wall_seconds"] += time.perf_counter() - start_wall

        setattr(owner, attribute, measured)

    for owner, name, label, timed in (
        (timber_orders, "phase10_before_reserves", "timber_planning", True),
        (timber_orders, "dispatch", "timber_dispatch", False),
        (timber_orders, "_price", "timber_price", False),
        (titled_trade, "_people", "trade_people", False),
        (titled_trade, "_bfs", "trade_bfs", False),
        (cm, "assemble_bundle", "bundle_assembly", True),
        (cm, "write_bundle", "bundle_write", True),
        (bundle_codec, "encode_history", "history_encoding", True),
    ):
        instrument(owner, name, label, timed=timed)
    original_turn = cm.run_turn_result

    def turn(*args, **kwargs):
        nonlocal active_turn
        old = active_turn
        active_turn = int(args[0].turn)
        try:
            return original_turn(*args, **kwargs)
        finally:
            active_turn = old

    cm.run_turn_result = turn
    code = module.child(plan_path)
    metrics = json.loads((out / "profile.json").read_text())
    if len(metrics["turns"]) != plan["case"]["turns"]:
        raise RuntimeError("measured horizon differs from the fixed declared case")
    if metrics.get("extraction_problems"):
        raise RuntimeError(f"strict extraction problems: {metrics['extraction_problems']}")
    with (out / "turns.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_turn", "wall_seconds", "cpu_seconds", "native_agents"))
        writer.writeheader()
        writer.writerows(metrics["turns"])
    stage_rows = [{"source_turn": key[0], "scope": "outside_turn" if key[0] is None else "simulation",
                   "stage": key[1], **row} for key, row in stages.items()]
    stage_rows.sort(key=lambda row: (-1 if row["source_turn"] is None else row["source_turn"], row["stage"]))
    with (out / "stages.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_turn", "scope", "stage", "calls", "timed", "cpu_seconds", "wall_seconds"))
        writer.writeheader()
        writer.writerows(stage_rows)
    (out / "stage-timings.json").write_text(json.dumps({
        "cumulative_not_additive": True, "all_calls_recorded": True, "rows": stage_rows,
        "instrumented_stages": instrumented,
        "note": "High-frequency helper calls are counted only to avoid per-call timing bias; their time is null, not zero. Outer planning and serialization stages are timed.",
        "wrapper_sha256": plan["wrapper_sha256"]}, indent=2) + "\n")
    (out / "checkpoint-semantics.json").write_text(json.dumps({
        "same_source_exact_reads_only": True,
        "note": "Envelope source identities differ across builds. Compare native bytes, decoded world/history and all persisted livelihood component values, including JSON-excluded X1 person rows.",
        "checkpoints": restored}, indent=2) + "\n")
    if sha(__file__) != plan["wrapper_sha256"] or sha(source / "scripts/cw_program_profile.py") != plan["tool_sha256"]:
        raise RuntimeError("measurement source changed while the case ran")
    return code


def run(args):
    source, out = Path(args.source_root).resolve(), Path(args.out).resolve()
    if out.exists():
        raise ValueError("choose a new evidence directory; existing runs are never overwritten")
    if not math.isfinite(args.cpu_budget_seconds) or args.cpu_budget_seconds <= 0:
        raise ValueError("CPU budget must be finite and positive")
    module = core(source)
    frozen = module.snapshot(source)
    if frozen["commit"] != args.expect_commit:
        raise ValueError("source HEAD differs from the frozen declared reference")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True):
        raise ValueError("source must be clean and frozen")
    module.verify(source, frozen, args.native_sha256)
    cases = [case for case in module.configurations(source) if case["world"] in WORLDS]
    if args.case:
        cases = [case for case in cases if case["name"] in args.case]
        if {case["name"] for case in cases} != set(args.case):
            raise ValueError("case is outside the declared five-world matrix")
    out.mkdir(parents=True)
    wrapper_sha, core_sha = sha(__file__), sha(source / "scripts/cw_program_profile.py")
    (out / "plan.json").write_text(json.dumps({"source": frozen, "cases": cases,
        "native_sha256": args.native_sha256, "wrapper_sha256": wrapper_sha,
        "core_sha256": core_sha, "cpu_budget_seconds": args.cpu_budget_seconds}, indent=2) + "\n")
    (out / "machine.json").write_text(json.dumps({
        "logical_cpus": os.cpu_count(), "affinity_cpus": sorted(os.sched_getaffinity(0)),
        "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        "memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
        "serial": True, "rayon_threads": 1, "cpu_budget_seconds": args.cpu_budget_seconds,
        "source": frozen, "wrapper_sha256": sha(__file__), "explicit_full_options": OPTIONS,
        "note": "Same declared scales and complete observations; no held seeds or qualification."}, indent=2) + "\n")
    env = {**os.environ, "PYTHONPATH": str(source / "src"), "RAYON_NUM_THREADS": "1",
           "PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "CHRONICLER_QUIET": "1"}
    results, charged = [], 0.0
    for case in cases:
        if module.snapshot(source) != frozen:
            raise RuntimeError("source changed during the frozen suite")
        if sha(__file__) != wrapper_sha or sha(source / "scripts/cw_program_profile.py") != core_sha:
            raise RuntimeError("measurement source changed during the frozen suite")
        if charged >= args.cpu_budget_seconds:
            raise RuntimeError("declared CPU budget exhausted; retain completed/failed cases")
        directory = out / case["name"]
        directory.mkdir()
        plan = {"source": str(source), "source_snapshot": frozen, "native_sha256": args.native_sha256,
                "out": str(directory), "case": case, "rayon_threads": 1,
                "tool_sha256": core_sha, "wrapper_sha256": wrapper_sha,
                "remaining_cpu_budget_seconds": args.cpu_budget_seconds - charged,
                "kernel_cpu_limit_seconds": cpu_limit_seconds(args.cpu_budget_seconds - charged)}
        plan_path = directory / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        command = [args.python, str(Path(__file__).resolve()), "child", str(plan_path)]
        usage, wall = resource.getrusage(resource.RUSAGE_CHILDREN), time.monotonic()
        with (directory / "run.log").open("w") as log:
            try:
                result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=min(600.0, 2 * (args.cpu_budget_seconds - charged)))
                exit_code, error = result.returncode, None
            except subprocess.TimeoutExpired:
                exit_code, error = 124, "bounded profile child wall limit exceeded"
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        child_cpu = after.ru_utime + after.ru_stime - usage.ru_utime - usage.ru_stime
        charged += child_cpu
        row = {"name": case["name"], "exit_code": exit_code, "error": error, "command": command,
               "process_wall_seconds": time.monotonic() - wall, "child_cpu_seconds": child_cpu,
               "charged_cpu_seconds": charged,
               "files": {p.relative_to(directory).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p)}
                         for p in sorted(directory.rglob("*")) if p.is_file()}}
        results.append(row)
        (out / "runs.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({key: row[key] for key in ("name", "exit_code", "error", "process_wall_seconds", "child_cpu_seconds", "charged_cpu_seconds")}), flush=True)
        if exit_code or charged > args.cpu_budget_seconds:
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    parent = commands.add_parser("run")
    parent.add_argument("out")
    parent.add_argument("--source-root", required=True)
    parent.add_argument("--expect-commit", required=True)
    parent.add_argument("--native-sha256", required=True)
    parent.add_argument("--python", default=sys.executable)
    parent.add_argument("--cpu-budget-seconds", type=float, default=1350.0)
    parent.add_argument("--case", action="append")
    worker = commands.add_parser("child")
    worker.add_argument("plan")
    args = parser.parse_args()
    return child(args.plan) if args.command == "child" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
