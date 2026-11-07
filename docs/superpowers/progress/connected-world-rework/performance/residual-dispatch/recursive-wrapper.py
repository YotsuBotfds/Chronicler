#!/usr/bin/env python3
"""Cost ranking of an unchanged corrected profile case; not a timing baseline."""
from __future__ import annotations

import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import resource
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


plan_path, tool_path, profile_path = map(Path, sys.argv[1:4])
plan = json.loads(plan_path.read_text())
if plan["kernel_cpu_limit_seconds"] != 450:
    raise ValueError("diagnostic requires its approved 450-second CPU ceiling")
resource.setrlimit(resource.RLIMIT_CPU, (450, 450))
if profile_path.exists():
    raise ValueError("choose a new diagnostic artifact; never replace evidence")
spec = importlib.util.spec_from_file_location("corrected_profile_measurement", tool_path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
if sha(tool_path) != plan["wrapper_sha256"]:
    raise ValueError("profile measurement tool differs from frozen plan")

import chronicler.main as cm

profile = cProfile.Profile(timer=time.process_time)
original_execute = cm.execute_run


def execute(*args, **kwargs):
    return profile.runcall(original_execute, *args, **kwargs)


cm.execute_run = execute
try:
    code = tool.child(plan_path)
finally:
    profile.dump_stats(profile_path)
    stats = pstats.Stats(profile)
    rows = [{"file": key[0], "line": key[1], "name": key[2],
             "primitive_calls": value[0], "calls": value[1],
             "self_cpu_seconds": value[2], "cumulative_cpu_seconds": value[3]}
            for key, value in stats.stats.items()]
    metadata = {"kind": "same-scale corrected-source cProfile diagnostic, not an unwrapped timing comparison",
                "timer": "time.process_time", "kernel_cpu_limit_seconds": 450,
                "source": plan["source_snapshot"], "case": plan["case"],
                "native_sha256": plan["native_sha256"], "measurement_wrapper_sha256": sha(tool_path),
                "diagnostic_wrapper_sha256": sha(__file__), "total_calls": stats.total_calls,
                "primitive_calls": stats.prim_calls, "profiled_functions": len(rows),
                "total_profile_cpu": stats.total_tt, "pstats_sha256": sha(profile_path),
                "top_cumulative": sorted(rows, key=lambda row: -row["cumulative_cpu_seconds"])[:70],
                "top_self": sorted(rows, key=lambda row: -row["self_cpu_seconds"])[:50]}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    metadata["post_validation_and_stats_resource_usage"] = {
        "process_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "peak_rss_kib": usage.ru_maxrss,
        "scope": "process startup through model, exact readbacks, full bundle load, strict CWR extraction and diagnostic stats construction"}
    profile_path.with_suffix(".summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    profile_path.with_suffix(".all-functions.json").write_text(json.dumps(rows, indent=2) + "\n")
raise SystemExit(code)
