#!/usr/bin/env python3
"""Complete declared case with one outer retail-dispatch CPU/wall timer per turn."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


plan_path, tool_path, report_path = map(Path, sys.argv[1:4])
plan = json.loads(plan_path.read_text())
if plan["kernel_cpu_limit_seconds"] != 450:
    raise ValueError("scoped diagnostic requires approved 450-second CPU ceiling")
resource.setrlimit(resource.RLIMIT_CPU, (450, 450))
if report_path.exists():
    raise ValueError("choose a new evidence artifact")
spec = importlib.util.spec_from_file_location("scoped_profile_measurement", tool_path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
if sha(tool_path) != plan["wrapper_sha256"]:
    raise ValueError("measurement wrapper differs from frozen plan")

from chronicler import titled_trade

original = titled_trade._dispatch
rows = []


def dispatch(world, *args, **kwargs):
    start_cpu, start_wall = time.process_time(), time.perf_counter()
    try:
        return original(world, *args, **kwargs)
    finally:
        rows.append({"source_turn": int(world.turn), "cpu_seconds": time.process_time() - start_cpu,
                     "wall_seconds": time.perf_counter() - start_wall})


titled_trade._dispatch = dispatch
status = "incomplete"
try:
    code = tool.child(plan_path)
    status = "complete" if code == 0 else "failed"
finally:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report_path.write_text(json.dumps({"kind": "complete-world outer-stage diagnostic; no recursive profiler",
        "status": status, "case": plan["case"], "source": plan["source_snapshot"],
        "native_sha256": plan["native_sha256"], "measurement_wrapper_sha256": sha(tool_path),
        "diagnostic_wrapper_sha256": sha(__file__), "kernel_cpu_limit_seconds": 450,
        "scope": "One CPU/wall pair around titled_trade._dispatch per call, every physical turn preserved; nested Fraction functions are not instrumented.",
        "rows": rows, "calls": len(rows), "total_cpu_seconds": sum(row["cpu_seconds"] for row in rows),
        "total_wall_seconds": sum(row["wall_seconds"] for row in rows),
        "post_validation_process_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "post_validation_peak_rss_kib": usage.ru_maxrss}, indent=2) + "\n")
raise SystemExit(code)
