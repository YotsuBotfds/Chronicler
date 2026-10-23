"""Paired snapshot fast-path timings plus unmodified kernel and fresh CLI controls.

Same interpreter/dependencies for both trees. Each worker imports one tree only;
measurements alternate baseline/candidate order. No profile or trace instrumentation
is enabled here. Pair count is bounded to keep this a small diagnostic, not a sweep.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

from benchmark_headless import WORKLOADS


def worker(source: Path, boundary: str):
    sys.path.insert(0, str(source / "src"))
    from chronicler.action_engine import ActionEngine
    from chronicler.intelligence import compute_accuracy, get_perceived_stat
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world
    from chronicler.main import _create_ecology_runtime, _create_politics_runtime
    from benchmark_headless import run

    spec = WORKLOADS["standard"]
    probe = generate_world(seed=42, num_civs=1, num_regions=3)
    if _create_ecology_runtime(probe) is not None or _create_politics_runtime(probe) is not None:
        raise RuntimeError("Controls require the same pure-Python lane as benchmark_headless")

    def kernel():
        world = generate_world(seed=spec["seed"], num_civs=spec["civs"], num_regions=spec["regions"])
        for turn in range(spec["turns"]):
            engine = ActionEngine(world)
            run_turn(world, lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed),
                     lambda w, events: "", seed=world.seed + turn,
                     force_settlement_detection=turn == spec["turns"] - 1)
        return world

    with tempfile.TemporaryDirectory(prefix="chronicler-boundary-") as scratch:
        scratch = Path(scratch)
        if boundary == "snapshot":
            # Identical post-simulation world, including actual factions/relations.
            world = kernel()
            import chronicler.intelligence as intelligence
            fast = getattr(intelligence, "_get_perceived_stat_with_accuracy", None)

            def task():
                result = None
                for _ in range(80):
                    unique_names = len({c.name for c in world.civilizations}) == len(world.civilizations)
                    cache = {(obs.name, tgt.name): compute_accuracy(obs, tgt, world)
                             for obs in world.civilizations for tgt in world.civilizations
                             if obs.name != tgt.name}
                    result = {
                        obs.name: {
                            tgt.name: {
                                stat: value - getattr(tgt, stat)
                                for stat in ("military", "economy", "stability")
                                if (value := (
                                    fast(obs, tgt, stat, world, accuracy=(
                                        cache[(obs.name, tgt.name)] if unique_names
                                        else compute_accuracy(obs, tgt, world)))
                                    if fast else get_perceived_stat(obs, tgt, stat, world)
                                )) is not None
                            }
                            for tgt in world.civilizations
                            if obs.name != tgt.name and cache[(obs.name, tgt.name)] > 0.0
                        } for obs in world.civilizations
                    }
                return result

            task()
        elif boundary == "kernel":
            task = kernel
            kernel()
        elif boundary == "execute":
            # World/artifact generation included, imports warmed.
            run(dict(spec, turns=1), scratch / "warmup")
            task = lambda: run(spec, scratch / "measured")
        elif boundary == "cli":
            env = dict(os.environ, PYTHONPATH=str(source / "src"))
            command = [sys.executable, "-m", "chronicler.main", "--agents", "off", "--simulate-only",
                       "--seed", str(spec["seed"]), "--turns", str(spec["turns"]),
                       "--civs", str(spec["civs"]), "--regions", str(spec["regions"]),
                       "--output", str(scratch / "chronicle.md"), "--state", str(scratch / "state.json")]
            # Prime bytecode/filesystem once; each observation still uses a fresh interpreter.
            subprocess.run(command, cwd=source, env=env, stdout=subprocess.DEVNULL, check=True)
            task = lambda: subprocess.run(command, cwd=source, env=env, stdout=subprocess.DEVNULL, check=True)
        else:
            raise ValueError(boundary)
        gc.collect()
        start_cpu, start = time.process_time(), time.perf_counter()
        result = task()
        elapsed, cpu = time.perf_counter() - start, time.process_time() - start_cpu
        result_hash = None
        if boundary == "snapshot":
            result_hash = hashlib.sha256(json.dumps(result, separators=(",", ":")).encode()).hexdigest()
        elif boundary == "kernel":
            result_hash = hashlib.sha256(result.model_dump_json().encode()).hexdigest()
        return dict(seconds=elapsed, cpu_seconds=cpu if boundary != "cli" else None,
                    output_sha256=result_hash)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pairs", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--worker-source", type=Path)
    parser.add_argument("--boundary", choices=("snapshot", "kernel", "execute", "cli"))
    args = parser.parse_args()
    if args.worker_source:
        print(json.dumps(worker(args.worker_source.resolve(), args.boundary)))
        return 0
    if not (args.baseline_root and args.candidate_root and args.output):
        parser.error("Provide --baseline-root, --candidate-root and --output")
    if args.output.exists():
        parser.error("Output exists; preserve the previous evidence and choose a fresh path")
    sources = {}
    for side, source in (("baseline", args.baseline_root), ("candidate", args.candidate_root)):
        source = source.resolve()
        sources[side] = dict(
            revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
            source_sha256={str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted((source / "src/chronicler").glob("*.py"))},
        )
    report = dict(workload=WORKLOADS["standard"], pairs=args.pairs,
                  snapshot_repeats=80, boundaries={},
                  sources=sources,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  environment=dict(python=sys.version, platform=platform.platform(),
                                   packages={dist.metadata["Name"]: dist.version for dist in distributions()
                                             if dist.metadata["Name"] != "chronicler"}),
                  caveat="Three pairs are diagnostic, not a statistical confidence interval; CLI includes startup.")
    for boundary in ("snapshot", "kernel", "execute", "cli"):
        rows = {"baseline": [], "candidate": []}
        for pair in range(args.pairs):
            order = ("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")
            for side in order:
                source = args.baseline_root if side == "baseline" else args.candidate_root
                command = [sys.executable, str(Path(__file__).resolve()), "--worker-source", str(source),
                           "--boundary", boundary]
                rows[side].append(json.loads(subprocess.check_output(command, text=True)))
        before, after = (statistics.median(row["seconds"] for row in rows[side])
                         for side in ("baseline", "candidate"))
        rows.update(baseline_median_seconds=before, candidate_median_seconds=after,
                    median_speedup=before / after)
        if boundary in ("snapshot", "kernel"):
            hashes = {row["output_sha256"] for side in ("baseline", "candidate") for row in rows[side]}
            if len(hashes) != 1:
                raise RuntimeError(f"{boundary} output mismatch")
        report["boundaries"][boundary] = rows
        print(f"{boundary}: {before:.6f}s -> {after:.6f}s ({before / after:.3f}x)", flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
