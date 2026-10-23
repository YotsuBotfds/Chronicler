"""Small, exact-output headless benchmark; no narration clients or native runtime.

Run this same script against both source trees with --source-root. Timings include
world generation, simulation, snapshots and artifact I/O, but exclude imports,
profiling, tracing, artifact hashing and tracemalloc. Reports are never overwritten.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, redirect_stdout
import cProfile
from datetime import datetime, timezone
import gc
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import pstats
import random
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch


WORKLOADS = {
    "single": dict(seed=321, turns=20, civs=1, regions=3),
    "standard": dict(seed=42, turns=60, civs=4, regions=12),
    "wide": dict(seed=77, turns=40, civs=6, regions=12),
}


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 10, 5, tzinfo=timezone.utc)
        return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextmanager
def rng_trace(path: Path):
    """Observe ordered primitive draws and seeds without subclassing Random.

    Patching methods in place preserves Random's selected _randbelow algorithm.
    Primitive float results use float.hex() so the trace loses no bits. Object
    identity is represented by monotonic construction order, never memory address.
    This is an untimed diagnostic, restricted to single-threaded Python off mode.
    """
    counts = {}
    instances = {}  # Retain instances: addresses cannot be reused within a trace.
    state = {}
    with path.open("w", encoding="utf-8", newline="\n") as log, ExitStack() as stack:
        for method in ("seed", "random", "getrandbits"):
            original = getattr(random.Random, method)

            def wrapped(self, *args, _method=method, _original=original, **kwargs):
                result = _original(self, *args, **kwargs)
                if self not in instances:
                    instances[self] = len(instances)
                counts[_method] = counts.get(_method, 0) + 1
                record = [instances[self], _method, args, kwargs,
                          result.hex() if isinstance(result, float) else result]
                log.write(json.dumps(record, separators=(",", ":")) + "\n")
                return result

            stack.enter_context(patch.object(random.Random, method, wrapped))
        yield state
    state.update(sha256=digest(path.read_bytes()), counts=counts,
                 instances=len(instances))


def run(workload: dict, output: Path, on_turn=None):
    from chronicler.main import execute_run

    args = argparse.Namespace(
        **workload, output=str(output / "chronicle.md"),
        state=str(output / "state.json"), resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, simulate_only=True, agents="off",
        governance=False,  # frozen pre-governance oracles; see docs/governance/runtime-integration.md
    )
    with open(os.devnull, "w") as sink, redirect_stdout(sink), \
            patch("chronicler.bundle.datetime", FixedDateTime):
        return execute_run(args, on_turn=on_turn)


def profile_summary(profile: cProfile.Profile):
    stats = pstats.Stats(profile)
    rows = []
    for (filename, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items():
        if "/chronicler/" in filename:
            rows.append(dict(file="chronicler/" + filename.split("/chronicler/")[-1],
                             line=line, function=name, calls=calls, primitive=primitive,
                             own_seconds=own, cumulative_seconds=cumulative))
    return dict(total_seconds=stats.total_tt,
                hotspots=sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:25],
                intelligence=[row for row in rows if row["file"] == "chronicler/intelligence.py"])


def benchmark(name: str, spec: dict, root: Path, repetitions: int):
    folder = root / name
    folder.mkdir()
    samples = []
    cpu_samples = []
    with tempfile.TemporaryDirectory(prefix="chronicler-perf-") as scratch:
        scratch = Path(scratch)
        run(dict(spec, turns=1), scratch / "warmup")
        for index in range(repetitions):
            gc.collect()
            start_cpu, start = time.process_time(), time.perf_counter()
            run(spec, scratch / f"timed-{index}")
            samples.append(time.perf_counter() - start)
            cpu_samples.append(time.process_time() - start_cpu)
        gc.collect()
        profile = cProfile.Profile()
        profile.runcall(run, spec, scratch / "profile")
        profile.dump_stats(str(folder / "profile.prof"))
        gc.collect()
        tracemalloc.start()
        run(spec, scratch / "memory")
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    turn_hashes = []

    def capture(snapshot, text, events, named):
        data = [snapshot.model_dump(mode="json"), text,
                [event.model_dump(mode="json") for event in events],
                [event.model_dump(mode="json") for event in named]]
        turn_hashes.append(digest(json.dumps(data, ensure_ascii=False,
                                           separators=(",", ":")).encode()))

    with rng_trace(folder / "rng.jsonl") as trace:
        run(spec, folder / "artifacts", on_turn=capture)
    artifacts = {
        path.name: dict(sha256=digest(path.read_bytes()), bytes=path.stat().st_size)
        for path in sorted((folder / "artifacts").iterdir()) if path.is_file()
    }
    return dict(workload=spec, seconds=samples, cpu_seconds=cpu_samples,
                median_seconds=statistics.median(samples),
                peak_tracemalloc_bytes=peak, profile=profile_summary(profile),
                equivalence=dict(artifacts=artifacts, turn_sha256=turn_hashes, rng=trace))


def compare(reference: dict, current: dict):
    if reference["workloads"].keys() != current["workloads"].keys():
        raise ValueError("Reports have different workloads")
    rows = {}
    environment_equal = reference["environment"] == current["environment"]
    for name, before in reference["workloads"].items():
        after = current["workloads"][name]
        same = before["workload"] == after["workload"] and before["equivalence"] == after["equivalence"]
        rows[name] = dict(exact_equivalence=same,
                          median_speedup=before["median_seconds"] / after["median_seconds"],
                          peak_bytes_delta=after["peak_tracemalloc_bytes"] - before["peak_tracemalloc_bytes"])
    return dict(environment_equal=environment_equal, workloads=rows,
                passed=environment_equal and all(row["exact_equivalence"] for row in rows.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--repetitions", type=int, default=3, choices=range(1, 6))
    args = parser.parse_args()
    source = args.source_root.resolve()
    sys.path.insert(0, str(source / "src"))
    from chronicler.main import _create_ecology_runtime, _create_politics_runtime
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_civs=1, num_regions=3)
    if _create_ecology_runtime(world) is not None or _create_politics_runtime(world) is not None:
        parser.error("Benchmark requires the pure-Python lane (native runtimes absent)")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    source_hashes = {str(path.relative_to(source)): digest(path.read_bytes())
                     for path in sorted((source / "src/chronicler").glob("*.py"))}
    report = dict(schema_version=1,
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
                  source_sha256=source_hashes,
                  environment=dict(python=sys.version, platform=platform.platform(),
                                   packages={dist.metadata["Name"]: dist.version for dist in distributions()
                                             if dist.metadata["Name"] != "chronicler"}),
                  mode="pure-Python off; execute_run; warmed imports; artifact I/O included",
                  generated_at="fixed 2026-10-05T00:00:00+00:00 for byte equivalence only",
                  repetitions=args.repetitions, workloads={})
    for name, spec in WORKLOADS.items():
        report["workloads"][name] = benchmark(name, spec, args.report_dir, args.repetitions)
        (args.report_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {report['workloads'][name]['median_seconds']:.6f}s", flush=True)
    (args.report_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.reference:
        decision = compare(json.loads(args.reference.read_text()), report)
        (args.report_dir / "comparison.json").write_text(json.dumps(decision, indent=2) + "\n")
        print(json.dumps(decision, indent=2))
        return 0 if decision["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
