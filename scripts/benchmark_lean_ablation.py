#!/usr/bin/env python3
"""Paired whole-worker/orchestrator measurements of the lean output policy.

Run only during a reserved quiet window. This is exact-equivalence/performance
measurement, never a causal gate. Every destination is new; failed evidence is
retained. Select a clean immutable source checkout and a matching native build.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--seeds", default="42,43")
    parser.add_argument("--turns", type=int, default=500)
    parser.add_argument("--civs", type=int, default=4)
    parser.add_argument("--regions", type=int, default=8)
    return parser


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inventory(folder):
    return {path.relative_to(folder).as_posix(): {"bytes": path.stat().st_size, "sha256": _sha(path)}
            for path in sorted(folder.rglob("*")) if path.is_file()}


def _bytes(inventory):
    return sum(item["bytes"] for item in inventory.values())


def _child_cpu():
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime + usage.ru_stime
    except (ImportError, AttributeError):
        return None


def _difference(after, before):
    return None if after is None or before is None else after - before


def _paired_summary(pairs, metric="seconds"):
    """Only complete measured pairs enter a performance summary."""
    ratios = [pair["full"][metric] / pair["lean"][metric] for pair in pairs]
    return {"pairs": len(ratios), "median_full_over_lean": statistics.median(ratios),
            "min_full_over_lean": min(ratios), "max_full_over_lean": max(ratios),
            "median_full_seconds": statistics.median(pair["full"][metric] for pair in pairs),
            "median_lean_seconds": statistics.median(pair["lean"][metric] for pair in pairs)}


def main(argv=None):
    args = _parser().parse_args(argv)
    source = args.source_root.resolve()
    out = args.output_root.resolve()
    seeds = [int(value) for value in args.seeds.split(",")]
    if (args.trials < 5 or not seeds or len(seeds) != len(set(seeds))
            or min(seeds) < 0 or min(args.civs, args.regions) < 1):
        raise ValueError("use at least five trials, unique nonnegative seeds and positive world dimensions")
    if out == source or source in out.parents:
        raise ValueError("keep benchmark artifacts outside the immutable source checkout")
    git = ["git", "-C", str(source)]
    def git_text(*arguments):
        return subprocess.check_output(git + list(arguments), text=True).strip()
    revision = git_text("rev-parse", "HEAD")
    if git_text("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("benchmark source must have no tracked modifications")
    if "chronicler" in sys.modules:
        raise ValueError("select source before importing Chronicler")
    sys.path.insert(0, str(source / "src"))
    from chronicler.artifact_io import atomic_write_json
    from chronicler.ablation_arms import (
        ABLATION_WINDOW_TURNS, GATE_ARMS, _fork_command, _keep_fork_outputs,
        checkpoint_turns, fork_turns,
    )
    from chronicler.batch_manifest import native_identity, package_digest, source_identity
    from chronicler.run_checkpoint import describe, runtime_identity
    from chronicler.validation_ablation import load_ablation_arms, needs_ablation_component, cohort_ablation_result
    from chronicler.validation_io import load_seed_runs

    forks = fork_turns(args.turns)
    if len(forks) < 2:
        raise ValueError("the timing design needs at least two pre-registered fork points")
    chosen = (forks[0], forks[-1])
    # Set the parent harness and every fresh child to the same exact-resume
    # environment before the identity is cached or any native pool is created.
    for key in ("RAYON_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise ValueError(f"launch this harness with {key}=1")
    env = dict(os.environ, PYTHONPATH=str(source / "src"))
    native = native_identity()
    if native.get("status") != "found":
        raise ValueError("a real matching native extension is required")
    digest = package_digest()
    script = Path(__file__).resolve()
    script_sha = _sha(script)
    def frozen():
        if (git_text("rev-parse", "HEAD") != revision
                or git_text("status", "--porcelain", "--untracked-files=no")
                or package_digest() != digest or _sha(script) != script_sha
                or native_identity().get("sha256") != native.get("sha256")):
            raise RuntimeError("source, runner or native identity changed during measurement")
    out.mkdir(parents=True, exist_ok=False)
    evidence = {
        "schema_version": 1, "kind": "chronicler-lean-ablation-benchmark", "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(), "source_root": str(source),
        "source": source_identity(), "runtime": runtime_identity(),
        "runner": {"path": str(script), "sha256": script_sha},
        "parameters": {"seeds": seeds, "total_turns": args.turns, "trials": args.trials,
                       "civs": args.civs, "regions": args.regions, "window": ABLATION_WINDOW_TURNS,
                       "direct_forks": list(chosen), "orchestrator_forks": forks,
                       "arms": list(GATE_ARMS), "parallel": 1},
        "limits": "performance/equivalence fixture; not a causal gate; host quietness is externally scheduled",
        "parents": [], "worker_pairs": [], "orchestrator_pairs": [], "commands": [],
    }
    receipt = out / "benchmark.json"
    def persist():
        atomic_write_json(receipt, evidence)
    persist()
    logs = out / "logs"
    logs.mkdir()
    def run(command, label):
        frozen()
        before_cpu = _child_cpu()
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=source, env=env, capture_output=True, text=True, check=False)
        seconds = time.perf_counter() - started
        cpu = _difference(_child_cpu(), before_cpu)
        (logs / f"{label}.stdout").write_text(proc.stdout)
        (logs / f"{label}.stderr").write_text(proc.stderr)
        record = {"label": label, "command": list(map(str, command)), "seconds": seconds,
                  "child_cpu_seconds": cpu, "exit_code": proc.returncode}
        evidence["commands"].append(record)
        persist()
        frozen()
        if proc.returncode:
            raise RuntimeError(f"{label} exited {proc.returncode}; see retained logs")
        return dict(record)
    try:
        batch = out / "plain"
        batch.mkdir()
        for seed in seeds:
            folder = batch / f"seed_{seed}"
            folder.mkdir()
            result = run([
                sys.executable, "-m", "chronicler.main", "--seed", str(seed),
                "--turns", str(args.turns), "--civs", str(args.civs), "--regions", str(args.regions),
                "--agents", "hybrid", "--simulate-only", "--validation-sidecar",
                "--checkpoint-turns", ",".join(map(str, checkpoint_turns(args.turns))),
                "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json"),
            ], f"parent-{seed}")
            result["seed"] = seed
            result["checkpoints"] = {
                str(turn): {"sha256": _sha(folder / f"checkpoint_turn_{turn + 1}.ckpt"),
                            "header": describe(folder / f"checkpoint_turn_{turn + 1}.ckpt")}
                for turn in forks}
            evidence["parents"].append(result)
            persist()
        # Both orchestrator profiles read the same plain-manifest bytes.
        atomic_write_json(batch / "batch_manifest.json", {
            "status": "complete", "turns": args.turns,
            "runs": [{"seed": seed, "dir": f"seed_{seed}"} for seed in seeds],
        })
        for seed in seeds:
            for fork in chosen:
                for trial in range(args.trials):
                    pair = {"seed": seed, "fork_turn": fork, "trial": trial}
                    order = ("full", "lean") if trial % 2 == 0 else ("lean", "full")
                    for profile in order:
                        label = f"worker-{seed}-{fork}-{trial}-{profile}"
                        folder = out / label
                        folder.mkdir()
                        checkpoint = batch / f"seed_{seed}" / f"checkpoint_turn_{fork + 1}.ckpt"
                        record = run(_fork_command(sys.executable, checkpoint, fork, ABLATION_WINDOW_TURNS,
                                                   "needs", folder, lean_output=profile == "lean"), label)
                        record["before_cleanup"] = _inventory(folder)
                        started = time.perf_counter()
                        _keep_fork_outputs(folder, lean_output=profile == "lean", seed=seed,
                                           fork_turn=fork, window=ABLATION_WINDOW_TURNS, arm="needs")
                        record["cleanup_seconds"] = time.perf_counter() - started
                        record["whole_fork_seconds"] = record["seconds"] + record["cleanup_seconds"]
                        record["retained"] = _inventory(folder)
                        record["bytes_before_cleanup"] = _bytes(record["before_cleanup"])
                        record["bytes_retained"] = _bytes(record["retained"])
                        pair[profile] = record
                        # Persist an unfinished pair too; never invent its missing arm.
                        evidence["current_pair"] = pair
                        persist()
                    if pair["full"]["retained"] != pair["lean"]["retained"]:
                        raise RuntimeError(f"retained event/receipt bytes differ for {label}")
                    evidence["worker_pairs"].append(pair)
                    evidence.pop("current_pair", None)
                    persist()
        runs = load_seed_runs(batch)
        for trial in range(args.trials):
            pair = {"trial": trial}
            order = ("lean", "full") if trial % 2 == 0 else ("full", "lean")
            for profile in order:
                label = f"orchestrator-{trial}-{profile}"
                folder = out / label
                command = [sys.executable, "-m", "chronicler.ablation_arms", "--batch-dir", str(batch),
                           "--out", str(folder), "--arms", ",".join(GATE_ARMS), "--turns", str(args.turns),
                           "--parallel", "1", "--keep-checkpoints"]
                if profile == "full":
                    command.append("--full-output")
                record = run(command, label)
                manifest = json.loads((folder / "ablation_manifest.json").read_text())
                if manifest["status"] != "complete":
                    raise RuntimeError(f"{label} has incomplete manifest")
                record["forks"] = [{key: fork[key] for key in
                                    ("arm", "seed", "fork_turn", "total_turns", "decision_ablation", "files")}
                                   for fork in manifest["forks"]]
                record["bytes_retained"] = _bytes(_inventory(folder))
                loaded = load_ablation_arms(folder, batch)
                record["oracles"] = {
                    "needs": needs_ablation_component(runs, loaded["arms"]["needs"]),
                    "cohort": cohort_ablation_result(runs, loaded["arms"]["kin_roots"]),
                }
                pair[profile] = record
                evidence["current_pair"] = pair
                persist()
            if (pair["full"]["forks"] != pair["lean"]["forks"]
                    or pair["full"]["oracles"] != pair["lean"]["oracles"]):
                raise RuntimeError("orchestrator retained inputs or downstream oracle results differ")
            evidence["orchestrator_pairs"].append(pair)
            evidence.pop("current_pair", None)
            persist()
        frozen()
        evidence["summary"] = {
            "workers": {f"seed_{seed}_fork_{fork}": {
                metric: _paired_summary([pair for pair in evidence["worker_pairs"]
                                        if pair["seed"] == seed and pair["fork_turn"] == fork], metric)
                for metric in ("seconds", "whole_fork_seconds")}
                for seed in seeds for fork in chosen},
            "orchestrator": _paired_summary(evidence["orchestrator_pairs"]),
        }
        evidence["status"] = "complete"
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        persist()
    print(json.dumps(evidence["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
