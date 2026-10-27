"""Ablation arms: forks of a plain batch with one decision term switched off.

The plain batch writes an exact checkpoint after each fork turn T
(``--checkpoint-turns``: world turn T + 1, which holds tick T and its
sidecars). For every seed, fork turn and arm, ``run_ablation_arms`` resumes
that checkpoint with ``--decision-ablation ARM --ablation-start-turn T+1``
and runs it to turn T + W + 2 (ticks T+1 .. T+W+1: the final tick's forced
settlement detection falls after the window). The plain run and the fork
share every tick up to T; afterwards they differ only through the ablated
term. Each fork keeps its agent event stream (``agent_events.arrow``) and
``fork.json``; its other outputs are removed, and a seed's checkpoints once
all its forks ran. ``ablation_manifest.json`` records the arms, forks and
the SHA-256 of every kept file; ``chronicler.validate --ablation-dir``
checks it before the needs (method 7) and cohort (method 4) oracles read
the forks. See docs/integration/ablation-oracles.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from chronicler.artifact_io import atomic_write_json

ABLATION_MANIFEST_FILENAME = "ablation_manifest.json"
ABLATION_MANIFEST_KIND = "chronicler-ablation-arms"
ABLATION_MANIFEST_SCHEMA_VERSION = 1
FORK_EVENTS_FILENAME = "agent_events.arrow"
FORK_INFO_FILENAME = "fork.json"
CHECKPOINT_TURN_FILENAME = "checkpoint_turn_{turn}.ckpt"

# Pre-registered fork rule (docs/integration/ablation-oracles.md): a fork at
# every multiple of ABLATION_FORK_EVERY from ABLATION_FIRST_FORK on whose
# window fits the plain run (T + window < total turns; a run of N turns
# ticks 0 .. N-1). Needs snapshots are written every 10 turns.
ABLATION_FIRST_FORK = 100
ABLATION_FORK_EVERY = 100
ABLATION_WINDOW_TURNS = 20
# The arms the gate runs (the placebo is for calibration).
GATE_ARMS = ("needs", "kin_roots")


def fork_turns(total_turns: int, window: int = ABLATION_WINDOW_TURNS) -> list[int]:
    """Fork turns of a plain run of ``total_turns`` turns."""
    out = []
    turn = ABLATION_FIRST_FORK
    while turn + window < total_turns:
        out.append(turn)
        turn += ABLATION_FORK_EVERY
    return out


def checkpoint_turns(total_turns: int, window: int = ABLATION_WINDOW_TURNS) -> list[int]:
    """The ``--checkpoint-turns`` a plain run writes for its forks (T + 1)."""
    return [turn + 1 for turn in fork_turns(total_turns, window)]


def fork_dir(out_root: Path, arm: str, seed_dir_name: str, fork_turn: int) -> Path:
    return Path(out_root) / arm / seed_dir_name / f"fork_{fork_turn}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain_runs(batch_dir: Path) -> list[dict]:
    manifest_path = Path(batch_dir) / "batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runs = manifest.get("runs") or []
    if manifest.get("status") != "complete" or not runs:
        raise ValueError(f"plain batch {batch_dir} is not complete")
    return [{"seed": int(run["seed"]), "dir": str(run["dir"])} for run in runs]


def _fork_command(python: str, checkpoint: Path, fork_turn: int, window: int, arm: str, out: Path) -> list[str]:
    return [
        python, "-m", "chronicler.main",
        "--resume", str(checkpoint),
        "--turns", str(fork_turn + window + 2),
        "--decision-ablation", arm,
        "--ablation-start-turn", str(fork_turn + 1),
        "--output", str(out / "chronicle.md"),
        "--state", str(out / "state.json"),
    ]


def _compress_events(path: Path) -> None:
    """Rewrite an agent event stream zstd-compressed (same rows and schema)."""
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = ipc.open_file(path).read_all()
    if not pa.Codec.is_available("zstd"):
        return
    tmp = path.with_suffix(".arrow.tmp")
    with ipc.new_file(tmp, table.schema, options=ipc.IpcWriteOptions(compression="zstd")) as writer:
        writer.write_table(table)
    os.replace(tmp, path)


def _keep_fork_outputs(out: Path) -> dict:
    """Keep the fork's event stream (compressed) and a summary of its bundle;
    remove the rest."""
    _compress_events(out / FORK_EVENTS_FILENAME)
    bundle_path = out / "chronicle_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    metadata = bundle.get("metadata", {})
    info = {
        "seed": metadata.get("seed"),
        "total_turns": metadata.get("total_turns"),
        "decision_ablation": metadata.get("decision_ablation"),
        "resume": metadata.get("resume"),
    }
    atomic_write_json(out / FORK_INFO_FILENAME, info)
    for path in sorted(out.rglob("*"), reverse=True):
        if path.name in (FORK_EVENTS_FILENAME, FORK_INFO_FILENAME) and path.parent == out:
            continue
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
    return info


def run_ablation_arms(
    batch_dir: Path,
    out_root: Path,
    *,
    arms: Iterable[str] = GATE_ARMS,
    total_turns: int,
    window: int = ABLATION_WINDOW_TURNS,
    parallel: int = 1,
    python: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    delete_checkpoints: bool = True,
    log=print,
) -> dict:
    """Run every arm's forks of ``batch_dir``'s seeds into ``out_root``
    (which must be new or empty) and write its ``ablation_manifest.json``.

    Raises ``RuntimeError`` naming the first fork that failed (the manifest
    is then written with status ``failed``)."""
    from chronicler.batch_manifest import (
        check_batch_destination, file_sha256, native_identity, source_identity,
    )

    arms = tuple(arms)
    for arm in arms:
        from chronicler.decision_ablation import DECISION_ABLATIONS
        if arm not in DECISION_ABLATIONS:
            raise ValueError(f"unknown ablation arm {arm!r}")
    batch_dir = Path(batch_dir)
    out_root = Path(out_root)
    check_batch_destination(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    python = python or sys.executable
    # A fork resumes a checkpoint that a batch worker wrote, so it runs with
    # the worker's thread environment (chronicler.batch._init_parallel_worker
    # sets a one-thread rayon pool); the checkpoint refuses another.
    env = dict(os.environ if env is None else env)
    env.setdefault("RAYON_NUM_THREADS", "1")
    forks = fork_turns(total_turns, window)
    runs = _plain_runs(batch_dir)
    plain_manifest = batch_dir / "batch_manifest.json"
    manifest: dict[str, Any] = {
        "kind": ABLATION_MANIFEST_KIND,
        "schema_version": ABLATION_MANIFEST_SCHEMA_VERSION,
        "status": "running",
        "started_at": _utc_now(),
        "plain_batch_dir": str(batch_dir),
        "plain_manifest_sha256": file_sha256(plain_manifest),
        "arms": list(arms),
        "window_turns": window,
        "fork_rule": {"first": ABLATION_FIRST_FORK, "every": ABLATION_FORK_EVERY,
                      "plain_total_turns": total_turns},
        "fork_turns": forks,
        "seeds": [run["seed"] for run in runs],
        "source": source_identity(),
        "native": native_identity(),
        "forks": [],
    }
    atomic_write_json(out_root / ABLATION_MANIFEST_FILENAME, manifest)

    jobs = []
    for run in runs:
        seed_dir = batch_dir / run["dir"]
        for fork_turn in forks:
            checkpoint = seed_dir / CHECKPOINT_TURN_FILENAME.format(turn=fork_turn + 1)
            for arm in arms:
                jobs.append((run, seed_dir, fork_turn, checkpoint, arm))
    remaining = {run["dir"]: len(forks) * len(arms) for run in runs}
    failures: list[str] = []
    records: list[dict] = []

    def one(job):
        run, seed_dir, fork_turn, checkpoint, arm = job
        out = fork_dir(out_root, arm, run["dir"], fork_turn)
        out.mkdir(parents=True, exist_ok=False)
        if not checkpoint.is_file():
            return job, None, f"missing checkpoint {checkpoint}"
        start = time.monotonic()
        proc = subprocess.run(
            _fork_command(python, checkpoint, fork_turn, window, arm, out),
            cwd=cwd, env=env, capture_output=True, text=True, check=False,
        )
        seconds = time.monotonic() - start
        if proc.returncode != 0:
            (out / "fork.log").write_text(proc.stdout[-8000:] + "\n" + proc.stderr[-8000:], encoding="utf-8")
            return job, None, f"fork {arm} seed {run['seed']} turn {fork_turn} exited {proc.returncode}"
        info = _keep_fork_outputs(out)
        record = {
            "arm": arm,
            "seed": run["seed"],
            "run_dir": run["dir"],
            "fork_turn": fork_turn,
            "dir": str(out.relative_to(out_root)),
            "seconds": round(seconds, 3),
            "total_turns": info.get("total_turns"),
            "decision_ablation": info.get("decision_ablation"),
            "files": {
                FORK_EVENTS_FILENAME: file_sha256(out / FORK_EVENTS_FILENAME),
                FORK_INFO_FILENAME: file_sha256(out / FORK_INFO_FILENAME),
            },
        }
        return job, record, None

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, int(parallel))) as pool:
        for job, record, error in pool.map(one, jobs):
            run = job[0]
            if error is not None:
                failures.append(error)
                log(f"ablation fork failed: {error}")
            else:
                records.append(record)
            remaining[run["dir"]] -= 1
            if remaining[run["dir"]] == 0 and delete_checkpoints and not failures:
                for fork_turn in forks:
                    path = batch_dir / run["dir"] / CHECKPOINT_TURN_FILENAME.format(turn=fork_turn + 1)
                    if path.exists():
                        path.unlink()
            done = len(records) + len(failures)
            if done % 50 == 0 or done == len(jobs):
                log(f"ablation forks: {done}/{len(jobs)}")
    records.sort(key=lambda r: (r["arm"], r["seed"], r["fork_turn"]))
    manifest["forks"] = records
    manifest["fork_count"] = len(records)
    manifest["seconds"] = round(time.monotonic() - started, 3)
    manifest["finished_at"] = _utc_now()
    manifest["status"] = "failed" if failures else "complete"
    if failures:
        manifest["failures"] = failures
    atomic_write_json(out_root / ABLATION_MANIFEST_FILENAME, manifest)
    if failures:
        raise RuntimeError(f"{len(failures)} ablation fork(s) failed; first: {failures[0]}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run ablation arms for a plain batch with fork checkpoints")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--arms", default=",".join(GATE_ARMS))
    parser.add_argument("--turns", required=True, type=int, help="the plain batch's turns")
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--keep-checkpoints", action="store_true")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    run_ablation_arms(
        args.batch_dir, args.out, arms=[a for a in args.arms.split(",") if a], total_turns=args.turns,
        parallel=args.parallel, env=env, delete_checkpoints=not args.keep_checkpoints,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
