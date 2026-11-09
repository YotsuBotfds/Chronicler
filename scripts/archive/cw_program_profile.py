#!/usr/bin/env python3
"""Serial declared-scale Connected World development profiling, never held runs.

Requires a frozen checkout and expected release artifact. Every case runs in a
fresh child, copies timing operands without proxying the native simulator, and
reads its exact checkpoints under the same source before returning. No source,
seed registry, defaults or runtime limits are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time


PROGRAM_FLAGS = {
    "--workshop-economics": 0, "--workshop-economics-rules": 1,
    "--titled-trade": 0, "--infrastructure-condition": 0, "--infrastructure-condition-mode": 1,
    "--harvest-cover": 0, "--harvest-cover-mode": 1, "--timber-orders": 0,
    "--epidemic-care": 0, "--public-health": 0, "--public-health-mode": 1,
    "--reform-services": 0, "--guild-leagues": 0, "--movement-branches": 0, "--movement-branches-mode": 1,
    "--residence-ledger": 0, "--attribution-records": 0, "--wealth-accounting": 0, "--wealth-accounting-mode": 1,
    "--war-requisition": 0, "--war-requisition-mode": 1, "--war-consequences": 0, "--war-consequences-mode": 1,
    "--adaptive-livelihoods": 0, "--adaptive-livelihoods-mode": 1, "--adaptive-livelihoods-rules": 1,
    "--quarantine-mode": 1, "--quarantine-channels": 1, "--watershed": 0, "--watershed-mode": 1,
}


def screen(source):
    path = source / "scripts/cw_integrated_screen.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("cw_profile_screen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(source):
    files = sorted([*source.glob("src/chronicler/**/*.py"), *source.glob("chronicler-agents/src/**/*.rs"),
                    *(source / "chronicler-agents" / name for name in ("Cargo.toml", "Cargo.lock", "build.rs", "pyproject.toml")),
                    source / "scripts/cw_integrated_screen.py"])
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
            "files": len(files), "sha256": digest.hexdigest()}


def native_identity():
    import chronicler
    import chronicler_agents.chronicler_agents as native
    path = Path(native.__file__).resolve()
    return {"python_source": str(Path(chronicler.__file__).resolve()), "interpreter": sys.executable,
            "python_version": sys.version, "extension": str(path), "native_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "agent_schema": native.AgentSimulator.checkpoint_schema()[:2],
            "environment": {key: os.environ.get(key) for key in ("RAYON_NUM_THREADS", "PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")}}


def verify(source, expected, native_sha):
    actual = snapshot(source)
    if actual != expected:
        raise RuntimeError(f"source changed: expected {expected}, actual {actual}")
    identity = native_identity()
    if not Path(identity["python_source"]).is_relative_to(source / "src"):
        raise RuntimeError(f"wrong Python source import: {identity}")
    if identity["native_sha256"] != native_sha:
        raise RuntimeError(f"wrong native extension: {identity}")
    return identity


def configurations(source):
    cw = screen(source)
    full = list(cw.BASE) + list(cw.ARMS["FULL"][0])
    off, i = [], 0
    while i < len(full):
        key = full[i]
        if key in PROGRAM_FLAGS:
            i += PROGRAM_FLAGS[key] + 1
        else:
            off.append(key)
            i += 1
    # Same all-region enrollment rule; the baseline predates A5's stock rules.
    off += ["--household-retail-rules", "1", "--quarantine-mode", "legacy"]
    worlds = [(f"template_s{s}", s, 8, 4, 200, 0, False, (50, 100, 150, 199)) for s in (5, 23)]
    worlds += [(f"proc32_s{s}", s, 32, 10, 200, 0, True, (50, 100, 150, 199)) for s in (19, 31)]
    worlds += [("scaled22k_s42", 42, 12, 4, 30, 18800, False, (10, 20, 29)),
               ("scaled52k_s7", 7, 12, 4, 20, 43700, False, (5, 10, 15, 19)),
               ("proc48_s42", 42, 48, 10, 150, 0, True, (50, 100, 149))]
    cases = []
    for name, seed, regions, civs, turns, target, procedural, checkpoints in worlds:
        for arm, flags in (("off", off), ("full", full)):
            cli = [*flags, "--seed", str(seed), "--regions", str(regions), "--civs", str(civs), "--turns", str(turns),
                   "--validation-sidecar", "--checkpoint-turns", ",".join(map(str, checkpoints))]
            if procedural:
                cli += ["--worldgen", "procedural"]
                if arm == "full":
                    cli += ["--watershed", "--watershed-mode", "flow"]
            cases.append({"name": f"{name}-{arm}", "world": name, "arm": arm, "seed": seed, "turns": turns,
                          "regions": regions, "civs": civs, "target": target, "checkpoints": list(checkpoints), "cli": cli})
    return cases


def cpu():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def summary(values):
    return {"median": statistics.median(values), "min": min(values), "max": max(values), "sum": sum(values)} if values else None


def arrows(directory):
    import pyarrow as pa
    result = {}
    for path in sorted(directory.rglob("*.arrow")):
        with pa.memory_map(str(path), "r") as data:
            try:
                table = pa.ipc.open_file(data).read_all()
            except pa.ArrowInvalid:
                data.seek(0)
                table = pa.ipc.open_stream(data).read_all()
            result[path.relative_to(directory).as_posix()] = {"bytes": path.stat().st_size, "rows": table.num_rows,
                "columns": len(table.column_names), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def child(plan_path):
    plan = json.loads(Path(plan_path).read_text())
    source, out = Path(plan["source"]), Path(plan["out"])
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != plan["tool_sha256"]:
        raise RuntimeError("profile measurement tool changed after planning")
    identity = verify(source, plan["source_snapshot"], plan["native_sha256"])
    import chronicler.main as cm
    import chronicler.agent_bridge as ab
    from chronicler import run_checkpoint as rc
    from chronicler.utils import sync_civ_population
    original_generate, original_init = cm.generate_world, ab.AgentBridge.__init__
    original_turn, original_write = cm.run_turn_result, rc.write_checkpoint
    bridges, turn_rows, checkpoints, marks = [], [], [], []
    initial = {}

    def generate(*args, **kwargs):
        world = original_generate(*args, **kwargs)
        base = sum(r.population for r in world.regions)
        if plan["case"]["target"]:
            multiplier = plan["case"]["target"] / max(1, base)
            for region in world.regions:
                region.carrying_capacity = max(1, round(region.carrying_capacity * multiplier))
                region.population = round(region.population * multiplier)
                if max(region.carrying_capacity, region.population) > 65535:
                    raise RuntimeError("scaled world exceeds native u16 region range")
            for civ in world.civilizations:
                sync_civ_population(civ, world)
        initial.update(base_population=base, scaled_population=sum(r.population for r in world.regions))
        return world

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        initial["native_initial_agents"] = self._sim.get_snapshot().num_rows
        bridges.append(self)

    def turn(*args, **kwargs):
        wall, process = time.perf_counter(), cpu()
        result = original_turn(*args, **kwargs)
        bridge = kwargs.get("agent_bridge") or (bridges[-1] if bridges else None)
        turn_rows.append({"source_turn": args[0].turn - 1, "wall_seconds": time.perf_counter() - wall,
                          "cpu_seconds": cpu() - process, "native_agents": int(bridge._sim.last_tick_alive) if bridge else None})
        return result

    def write(path, state, **kwargs):
        report = original_write(path, state, **kwargs)
        checkpoints.append({"turn": state.world.turn, "path": str(path), "bytes": report.bytes,
                            "raw_bytes": report.raw_bytes, "sections": report.sections,
                            "write_seconds": report.seconds, "write_stages": report.timings})
        return report

    def on_turn(*args):
        marks.append((time.perf_counter(), cpu()))

    cm.generate_world, ab.AgentBridge.__init__, cm.run_turn_result, rc.write_checkpoint = generate, init, turn, write
    args = cm._build_parser().parse_args([*plan["case"]["cli"], "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    start = time.perf_counter(), cpu()
    cm.execute_run(args, on_turn=on_turn)
    run_wall, run_cpu = time.perf_counter() - start[0], cpu() - start[1]
    run_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    verify(source, plan["source_snapshot"], plan["native_sha256"])
    # Never allow mismatches. These reads happen before the frozen child exits.
    for checkpoint in checkpoints:
        loaded = rc.read_checkpoint(Path(checkpoint["path"]))
        if not loaded.exact or loaded.mismatches or loaded.state.world.turn != checkpoint["turn"]:
            raise RuntimeError("profile checkpoint was not an exact same-source restore")
        checkpoint.update(read_seconds=loaded.seconds, read_stages=loaded.timings, identity=loaded.header["identity"])
        del loaded
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(out / "chronicle_bundle.json")
    physical = {p.relative_to(out).as_posix(): p.stat().st_size for p in out.rglob("*") if p.is_file()}
    intervals = [(b[0] - a[0], b[1] - a[1]) for a, b in zip([start] + marks, marks)]
    metrics = {"case": plan["case"], "identity": identity, "source_snapshot": plan["source_snapshot"], **initial,
               "run_wall_seconds": run_wall, "run_cpu_seconds": run_cpu, "run_peak_rss_kib": run_peak,
               "process_peak_rss_with_read_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "turns": turn_rows, "simulation_turn_wall": summary([r["wall_seconds"] for r in turn_rows]),
               "simulation_turn_cpu": summary([r["cpu_seconds"] for r in turn_rows]),
               "callback_interval_wall": summary([r[0] for r in intervals[3:]]),
               "callback_interval_cpu": summary([r[1] for r in intervals[3:]]),
               "callback_interval_note": "drops first3 turns; includes preceding post-callback checkpoint/memory work",
               "native_peak_agents": max(r["native_agents"] for r in turn_rows), "checkpoints": checkpoints,
               "bundle_bytes": physical["chronicle_bundle.json"], "state_bytes": physical["state.json"],
               "output_bytes": sum(physical.values()),
               "simulation_output_bytes": sum(size for name, size in physical.items() if name not in ("plan.json", "run.log")),
               "file_bytes": physical, "sidecars": arrows(out), "tool_sha256": plan["tool_sha256"]}
    if plan["case"]["arm"] == "full":
        cw = screen(source)
        bundle["_cw6_events"] = cw.event_sidecar(out / "agent_events.arrow")
        observations, problems = cw.extract(bundle, cw.ARMS["FULL"][0])
        metrics["cw6_observations"], metrics["extraction_problems"] = observations, problems
        metrics["cw6_metrics_row_bytes"] = len(json.dumps(observations, separators=(",", ":")).encode())
    metrics["measurement_bytes"] = 0
    for _ in range(3):
        metrics["measurement_bytes"] = len(json.dumps(metrics, separators=(",", ":")).encode())
    (out / "profile.json").write_text(json.dumps(metrics, indent=2) + "\n")
    verify(source, plan["source_snapshot"], plan["native_sha256"])
    return 0


def run(args):
    source, out = Path(args.source_root).resolve(), Path(args.out).resolve()
    if out.exists():
        raise ValueError("profile output exists; preserve it and choose another path")
    frozen = snapshot(source)
    if frozen["commit"] != args.expect_commit:
        raise ValueError("checkout HEAD differs from the authorized frozen commit")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True)
    if dirty:
        raise ValueError("profile requires a clean frozen checkout")
    cases = configurations(source)
    if args.case:
        cases = [case for case in cases if case["name"] in args.case]
        if set(args.case) != {case["name"] for case in cases}:
            raise ValueError("unknown profile case")
    out.mkdir(parents=True)
    machine = {"logical_cpus": os.cpu_count(), "affinity_cpus": sorted(os.sched_getaffinity(0)),
               "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
               "memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
               "note": "shared host; serial profiler may overlap two separately scheduled one-job pilots"}
    (out / "machine.json").write_text(json.dumps(machine, indent=2) + "\n")
    env = {**os.environ, "PYTHONPATH": str(source / "src"), "RAYON_NUM_THREADS": str(args.rayon_threads),
           "PYTHONHASHSEED": "0", "CHRONICLER_QUIET": "1"}
    result = []
    for case in cases:
        if snapshot(source) != frozen:
            raise RuntimeError("frozen source changed between profile cases")
        directory = out / case["name"]
        directory.mkdir()
        plan = {"source": str(source), "source_snapshot": frozen, "native_sha256": args.native_sha256,
                "out": str(directory), "case": case, "rayon_threads": args.rayon_threads,
                "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        plan_path = directory / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        command = [args.python, str(Path(__file__).resolve()), "child", str(plan_path)]
        usage, wall = resource.getrusage(resource.RUSAGE_CHILDREN), time.monotonic()
        with (directory / "run.log").open("w") as log:
            proc = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        row = {"name": case["name"], "exit_code": proc.returncode, "command": command,
               "process_wall_seconds": time.monotonic() - wall,
               "child_cpu_seconds": after.ru_utime + after.ru_stime - usage.ru_utime - usage.ru_stime,
               "directory_bytes_after_exit": sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()),
               "file_bytes_after_exit": {p.relative_to(directory).as_posix(): p.stat().st_size
                                         for p in directory.rglob("*") if p.is_file()}}
        result.append(row)
        (out / "runs.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(row), flush=True)
    return int(any(row["exit_code"] for row in result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    parent = commands.add_parser("run")
    parent.add_argument("out")
    parent.add_argument("--source-root", required=True)
    parent.add_argument("--expect-commit", required=True)
    parent.add_argument("--native-sha256", required=True)
    parent.add_argument("--python", default=sys.executable)
    parent.add_argument("--rayon-threads", type=int, choices=(1, 2), default=1)
    parent.add_argument("--case", action="append")
    child_parser = commands.add_parser("child")
    child_parser.add_argument("plan")
    args = parser.parse_args(argv)
    return child(args.plan) if args.command == "child" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
