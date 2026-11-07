"""Measurement-only wrapper around the frozen declared-scale profiler.

Keeps the exact case/flags/checkpoints and source/native identity guards.  The
profile adds overhead, so compare uninstrumented runs for timing conclusions.
"""
from __future__ import annotations

import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import sys
import time


def main():
    source, directory = map(Path, sys.argv[1:3])
    if directory.exists():
        raise SystemExit("Choose a new evidence directory")
    directory.mkdir(parents=True)
    tool = source / "scripts/cw_program_profile.py"
    spec = importlib.util.spec_from_file_location("program_profile", tool)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    case = next(c for c in module.configurations(source) if c["name"] == "proc32_s19-full")
    frozen = module.snapshot(source)
    expected_native = "59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617"
    identity = module.verify(source, frozen, expected_native)
    (directory / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    plan = {"source": str(source), "source_snapshot": frozen,
            "native_sha256": expected_native, "out": str(directory),
            "case": case, "rayon_threads": 1,
            "tool_sha256": hashlib.sha256(tool.read_bytes()).hexdigest()}
    plan_path = directory / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    import chronicler.main as cm
    original = cm.execute_run
    profile = cProfile.Profile(timer=time.process_time)

    def measured(*args, **kwargs):
        profile.enable()
        try:
            return original(*args, **kwargs)
        finally:
            profile.disable()
            profile.dump_stats(str(directory / "calls.pstats"))

    cm.execute_run = measured
    code = module.child(str(plan_path))
    stats = pstats.Stats(profile)
    rows = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        rows.append({"file": filename, "line": line, "name": name,
                     "primitive_calls": primitive, "calls": calls,
                     "self_cpu_seconds": own, "cumulative_cpu_seconds": cumulative})
    report = {"kind": "cProfile diagnostic; not an uninstrumented timing baseline",
              "timer": "time.process_time", "source": frozen, "identity": identity,
              "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "profiled_functions": len(rows), "total_calls": stats.total_calls,
              "primitive_calls": stats.prim_calls, "total_profile_cpu": stats.total_tt,
              "top_cumulative": sorted(rows, key=lambda r: r["cumulative_cpu_seconds"], reverse=True)[:200],
              "top_self": sorted(rows, key=lambda r: r["self_cpu_seconds"], reverse=True)[:200]}
    (directory / "calls-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    for order in ("cumulative", "tottime"):
        with (directory / f"calls-{order}.txt").open("w") as output:
            pstats.Stats(profile, stream=output).sort_stats(order).print_stats(100)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
