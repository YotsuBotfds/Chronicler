"""Ablation arms: forks of a plain batch with one decision term switched off.

The plain batch writes an exact checkpoint after each fork turn T
(``--checkpoint-turns``: world turn T + 1, which holds tick T and its
sidecars). For every seed, fork turn and arm, ``run_ablation_arms`` resumes
that checkpoint with ``--decision-ablation ARM --ablation-start-turn T+1``
and runs it to turn T + W + 2 (ticks T+1 .. T+W+1: the final tick's forced
settlement detection falls after the window). The plain run and the fork
share every tick up to T; afterwards they differ only through the ablated
term. Each fork keeps its agent event stream (``agent_events.arrow``) and
``fork.json``; its other outputs are removed, and the plain checkpoints only after
every fork succeeds. ``ablation_manifest.json`` records the arms, forks and
the SHA-256 of every kept file; ``chronicler.validate --ablation-dir``
checks it before the needs and cohort oracles read the forks. See
docs/integration/ablation-oracles.md.

Fork designs (``ABLATION_DESIGN``; the manifest records its design):

* design 1 (``schema_version`` 1; needs method 7, cohort method 4): a fork
  every 100 turns from turn 100 in every world;
* design 2 (``schema_version`` 2; needs method 8, cohort method 5): every
  100 turns in template worlds, every 20 in procedural worlds
  (``fork_every``): there the agents short of material goods or safety are
  few (a procedural fork has 3.6 below the material threshold where a
  template fork has 18), and forks every 20 turns tile the window from
  turn 101 without overlap, which gives each required needs pairing the
  power the first pre-registration assumed (docs/integration/community-anchoring.md,
  section 6). Template worlds keep design 1's forks.

Batches forked under design 1 are re-scored by needs method 7 and cohort
method 4 as before.
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
# The manifest's schema version is its fork design (1 or 2, above).
ABLATION_MANIFEST_SCHEMA_VERSION = 2
ABLATION_DESIGNS = (1, 2)
ABLATION_DESIGN = 2
FORK_EVENTS_FILENAME = "agent_events.arrow"
FORK_INFO_FILENAME = "fork.json"
CHECKPOINT_TURN_FILENAME = "checkpoint_turn_{turn}.ckpt"

# Pre-registered fork rule (docs/integration/ablation-oracles.md): a fork at
# every ``fork_every`` turns from ABLATION_FIRST_FORK on whose window fits
# the plain run (T + window < total turns; a run of N turns ticks
# 0 .. N-1). Needs snapshots are written every 10 turns.
ABLATION_FIRST_FORK = 100
ABLATION_FORK_EVERY = 100
# Design 2, procedural worlds: forks tile the turns from 101 (window 20).
ABLATION_FORK_EVERY_PROCEDURAL = 20
ABLATION_WINDOW_TURNS = 20
# The arms the gate runs (the placebo is for calibration; community_anchor
# is added when the batch runs --community-anchoring).
GATE_ARMS = ("needs", "kin_roots")
COMMUNITY_ARM = "community_anchor"


def fork_every(worldgen: str | None = None, design: int = ABLATION_DESIGN) -> int:
    """Turns between forks under ``design`` for a plain run of ``worldgen``
    (``None`` or ``"template"``: template worlds)."""
    if design not in ABLATION_DESIGNS:
        raise ValueError(f"unknown ablation design {design!r}")
    if design >= 2 and worldgen == "procedural":
        return ABLATION_FORK_EVERY_PROCEDURAL
    return ABLATION_FORK_EVERY


def fork_turns(total_turns: int, window: int = ABLATION_WINDOW_TURNS, every: int = ABLATION_FORK_EVERY) -> list[int]:
    """Fork turns of a plain run of ``total_turns`` turns, a fork every ``every`` turns."""
    out = []
    turn = ABLATION_FIRST_FORK
    while turn + window < total_turns:
        out.append(turn)
        turn += every
    return out


def checkpoint_turns(total_turns: int, window: int = ABLATION_WINDOW_TURNS,
                     every: int = ABLATION_FORK_EVERY) -> list[int]:
    """The ``--checkpoint-turns`` a plain run writes for its forks (T + 1)."""
    return [turn + 1 for turn in fork_turns(total_turns, window, every)]


def batch_worldgen(manifest: dict) -> str | None:
    """The world generator a plain batch manifest records (None: template)."""
    simulation = manifest.get("simulation") if isinstance(manifest.get("simulation"), dict) else {}
    worldgen = simulation.get("worldgen")
    return worldgen if isinstance(worldgen, str) else None


def fork_dir(out_root: Path, arm: str, seed_dir_name: str, fork_turn: int) -> Path:
    return Path(out_root) / arm / seed_dir_name / f"fork_{fork_turn}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain_runs(batch_dir: Path) -> tuple[list[dict], dict]:
    manifest_path = Path(batch_dir) / "batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runs = manifest.get("runs") or []
    if manifest.get("status") != "complete" or not runs:
        raise ValueError(f"plain batch {batch_dir} is not complete")
    return [{"seed": int(run["seed"]), "dir": str(run["dir"])} for run in runs], manifest


def _fork_command(python: str, checkpoint: Path, fork_turn: int, window: int, arm: str, out: Path,
                  *, lean_output: bool = True) -> list[str]:
    command = [
        python, "-m", "chronicler.main",
        "--resume", str(checkpoint),
        "--turns", str(fork_turn + window + 2),
        "--decision-ablation", arm,
        "--ablation-start-turn", str(fork_turn + 1),
        "--output", str(out / "chronicle.md"),
        "--state", str(out / "state.json"),
    ]
    if lean_output:
        command.append("--ablation-output")
    return command


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


def fork_info(metadata: dict) -> dict:
    """The existing retained receipt, shared by full and lean output paths."""
    return {key: metadata.get(key) for key in
            ("seed", "total_turns", "decision_ablation", "resume")}


def _keep_fork_outputs(out: Path, *, lean_output: bool, seed: int,
                       fork_turn: int, window: int, arm: str) -> dict:
    """Validate completed outputs before compressing or deleting any artifacts."""
    if lean_output:
        info = json.loads((out / FORK_INFO_FILENAME).read_text(encoding="utf-8"))
        if not isinstance(info, dict) or set(info) != set(fork_info({})):
            raise ValueError("malformed lean fork receipt")
    else:
        bundle = json.loads((out / "chronicle_bundle.json").read_text(encoding="utf-8"))
        info = fork_info(bundle.get("metadata", {}))
    expected = {"name": arm, "start_turn": fork_turn + 1, "forked_at": fork_turn + 1}
    if (type(info.get("seed")) is not int or info["seed"] != seed
            or type(info.get("total_turns")) is not int
            or info["total_turns"] != fork_turn + window + 2
            or info.get("decision_ablation") != expected):
        raise ValueError(f"incomplete or mismatched fork receipt: {info!r}")
    _compress_events(out / FORK_EVENTS_FILENAME)
    if not lean_output:
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
    lean_output: bool = True,
    launch_backend: str = "fresh",
    log=print,
) -> dict:
    """Run every arm's forks of ``batch_dir``'s seeds into ``out_root``
    (which must be new or empty) and write its ``ablation_manifest.json``.
    ``lean_output=False`` retains the full worker export path for equivalence
    checks; both profiles keep identical files after validated cleanup.
    Only the existing ``fresh`` backend is available. The prospective opt-in
    models forkserver refuses before claiming any destination.

    Raises ``RuntimeError`` naming the first fork that failed (the manifest
    is then written with status ``failed``)."""
    if type(launch_backend) is not str or launch_backend != "fresh":
        from chronicler.ablation_launch import refuse_unqualified_backend
        refuse_unqualified_backend(launch_backend, arms=arms, parallel=parallel,
                                   lean_output=lean_output, window=window)

    from chronicler.batch_manifest import (
        check_batch_destination, file_sha256, native_identity, source_identity,
    )

    arms = tuple(arms)
    if len(set(arms)) != len(arms):
        raise ValueError("ablation arms must be unique")
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
    runs, plain = _plain_runs(batch_dir)
    worldgen = batch_worldgen(plain)
    every = fork_every(worldgen)
    forks = fork_turns(total_turns, window, every)
    plain_manifest = batch_dir / "batch_manifest.json"
    manifest: dict[str, Any] = {
        "kind": ABLATION_MANIFEST_KIND,
        "schema_version": ABLATION_MANIFEST_SCHEMA_VERSION,
        "design": ABLATION_DESIGN,
        "status": "running",
        "started_at": _utc_now(),
        "plain_batch_dir": str(batch_dir),
        "plain_manifest_sha256": file_sha256(plain_manifest),
        "arms": list(arms),
        "window_turns": window,
        "fork_rule": {"first": ABLATION_FIRST_FORK, "every": every, "worldgen": worldgen or "template",
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
    failures: list[str] = []
    records: list[dict] = []

    def one(job):
        run, seed_dir, fork_turn, checkpoint, arm = job
        out = fork_dir(out_root, arm, run["dir"], fork_turn)
        out.mkdir(parents=True, exist_ok=False)
        if not checkpoint.is_file():
            return job, None, f"missing checkpoint {checkpoint}"
        start = time.monotonic()
        try:
            proc = subprocess.run(
                _fork_command(python, checkpoint, fork_turn, window, arm, out, lean_output=lean_output),
                cwd=cwd, env=env, capture_output=True, text=True, check=False,
            )
        except OSError as exc:
            error = f"fork {arm} seed {run['seed']} turn {fork_turn} launch failed: {exc}"
            (out / "fork.log").write_text(error, encoding="utf-8")
            return job, None, error
        seconds = time.monotonic() - start
        if proc.returncode != 0:
            (out / "fork.log").write_text(proc.stdout[-8000:] + "\n" + proc.stderr[-8000:], encoding="utf-8")
            return job, None, f"fork {arm} seed {run['seed']} turn {fork_turn} exited {proc.returncode}"
        try:
            info = _keep_fork_outputs(out, lean_output=lean_output, seed=run["seed"],
                                      fork_turn=fork_turn, window=window, arm=arm)
        except Exception as exc:
            error = f"fork {arm} seed {run['seed']} turn {fork_turn} output failed: {type(exc).__name__}: {exc}"
            (out / "fork.log").write_text(
                proc.stdout[-8000:] + "\n" + proc.stderr[-8000:] + "\n" + error, encoding="utf-8")
            return job, None, error
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
            if error is not None:
                failures.append(error)
                log(f"ablation fork failed: {error}")
            else:
                records.append(record)
            done = len(records) + len(failures)
            if done % 50 == 0 or done == len(jobs):
                log(f"ablation forks: {done}/{len(jobs)}")
    if delete_checkpoints and not failures:
        for run in runs:
            for fork_turn in forks:
                path = batch_dir / run["dir"] / CHECKPOINT_TURN_FILENAME.format(turn=fork_turn + 1)
                path.unlink(missing_ok=True)
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
    parser.add_argument("--full-output", action="store_true", help="Use full worker exports (equivalence/timing)")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    run_ablation_arms(
        args.batch_dir, args.out, arms=[a for a in args.arms.split(",") if a], total_turns=args.turns,
        parallel=args.parallel, env=env, delete_checkpoints=not args.keep_checkpoints,
        lean_output=not args.full_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
