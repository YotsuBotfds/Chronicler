"""Batch runner — run multiple chronicles with sequential seeds."""
from __future__ import annotations

import argparse
import copy
import multiprocessing
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from chronicler.batch_manifest import (
    finish_batch_manifest,
    native_identity,
    new_batch_manifest,
    prepare_batch_dir,
    record_batch_run,
    write_batch_manifest,
)
from chronicler.interestingness import score_run
from chronicler.types import RunResult

# Type alias for progress callbacks: (completed, total, current_seed) -> None
ProgressCallback = Callable[[int, int, int], None]

_PARALLEL_NARRATION_ERROR = (
    "--batch --parallel requires --simulate-only. "
    "Parallel workers cannot share LLM connections. "
    "Use sequential batch mode for narrated runs."
)


def parallel_workers(parallel: Any, cpu_count: int | None = None) -> int:
    """Worker processes for a parallel batch.

    An explicit count (``--parallel N``, a Batch Lab worker count) is N
    workers, 1 included. Anything else that asks for a parallel batch (a bare
    ``--parallel``, argparse's ``const=-1``; Batch Lab's ``True``) sizes the
    pool to ``cpu_count - 1``, at least 1. ``None`` and 0 run sequentially and
    never reach here. Results do not depend on the count: each seed runs in
    one worker, deterministically.
    """
    if isinstance(parallel, int) and not isinstance(parallel, bool) and parallel >= 1:
        return parallel
    cores = multiprocessing.cpu_count() if cpu_count is None else cpu_count
    return max(1, cores - 1)


def run_batch(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
    progress_cb: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    tuning_overrides_dict: dict[str, float] | None = None,
) -> Path:
    """Run N chronicles with sequential seeds. Returns the batch directory path.

    The batch directory (``batch_<first seed>`` next to ``args.output``) must
    be new or empty (``BatchDestinationError`` otherwise): validation reads
    every bundle below it. ``batch_manifest.json`` there records the expected
    runs and their identity (``chronicler.batch_manifest``).

    Parameters
    ----------
    progress_cb : optional callback(completed, total, current_seed) called after each seed.
    cancel_event : optional threading.Event; if set, batch stops between seeds.
    tuning_overrides_dict : optional in-memory overrides (bypasses YAML file I/O).
    """
    base_seed = 42 if args.seed is None else args.seed
    count = args.batch
    base_output = Path(args.output).parent if hasattr(args, 'output') else Path("output")
    batch_dir = base_output / f"batch_{base_seed}"
    if args.parallel and not getattr(args, 'simulate_only', True):
        # H-24 (below), checked before the batch directory is claimed.
        raise ValueError(_PARALLEL_NARRATION_ERROR)
    prepare_batch_dir(batch_dir)

    results: list[RunResult] = []

    # Load tuning overrides: prefer in-memory dict, fall back to YAML file
    tuning_overrides: dict[str, float] = tuning_overrides_dict or {}
    if not tuning_overrides and getattr(args, "tuning", None):
        from chronicler.tuning import load_tuning
        tuning_overrides = load_tuning(Path(args.tuning))

    manifest = new_batch_manifest(args, [base_seed + i for i in range(count)], tuning_overrides=tuning_overrides)
    write_batch_manifest(batch_dir, manifest)
    cancelled = False

    if args.parallel:
        # H-24: Parallel batch mode cannot use LLM clients (connections can't
        # cross process boundaries). Fail loudly if narration was requested
        # instead of silently falling back to _DummyClient.
        if not getattr(args, 'simulate_only', True):
            raise ValueError(
                "--batch --parallel requires --simulate-only. "
                "Parallel workers cannot share LLM connections. "
                "Use sequential batch mode for narrated runs."
            )
        workers = parallel_workers(args.parallel)
        run_args = []
        for i in range(count):
            run_seed = base_seed + i
            run_dir = batch_dir / f"seed_{run_seed}"
            run_dir.mkdir(parents=True, exist_ok=True)
            child_args = copy.copy(args)
            child_args.seed = run_seed
            child_args.output = str(run_dir / "chronicle.md")
            child_args.state = str(run_dir / "state.json")
            child_args.tuning_overrides = tuning_overrides
            run_args.append((child_args, scenario_config))

        with multiprocessing.Pool(workers, initializer=_init_parallel_worker) as pool:
            async_results = [pool.apply_async(_run_single_no_llm, a) for a in run_args]
            for i, ar in enumerate(async_results):
                if cancel_event and cancel_event.is_set():
                    pool.terminate()
                    cancelled = True
                    break
                result = ar.get()
                results.append(result)
                record_batch_run(batch_dir, manifest, i, result.total_turns)
                run_seed = base_seed + i
                if progress_cb:
                    progress_cb(i + 1, count, run_seed)
    else:
        for i in range(count):
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break
            run_seed = base_seed + i
            run_dir = batch_dir / f"seed_{run_seed}"
            run_dir.mkdir(parents=True, exist_ok=True)

            child_args = copy.copy(args)
            child_args.seed = run_seed
            child_args.output = str(run_dir / "chronicle.md")
            child_args.state = str(run_dir / "state.json")
            child_args.tuning_overrides = tuning_overrides

            from chronicler.main import execute_run
            result = execute_run(
                child_args,
                sim_client=sim_client,
                narrative_client=narrative_client,
                scenario_config=scenario_config,
            )
            results.append(result)
            record_batch_run(batch_dir, manifest, i, result.total_turns)
            if progress_cb:
                progress_cb(i + 1, count, run_seed)
            print(f"  Batch run {i + 1}/{count} complete (seed {run_seed})")

    if "chronicler_agents.chronicler_agents" in sys.modules:
        # Sequential runs load the extension here: record the loaded module.
        manifest["native"] = native_identity()
    finish_batch_manifest(batch_dir, manifest, cancelled=cancelled)

    # Write summary
    weights = scenario_config.interestingness_weights if scenario_config and hasattr(scenario_config, 'interestingness_weights') else None
    _write_summary(batch_dir, results, weights)

    return batch_dir


def _init_parallel_worker() -> None:
    """Give each batch worker a one-thread rayon pool unless the user sized it.

    Parallel batches already run one simulation per core; per-worker rayon
    threads only oversubscribe the cores at current agent counts. The native
    tick partitions work per region with per-region RNG streams, so results
    do not depend on the thread count. Runs before the worker first imports
    the native extension, whose global pool reads the variable at start.
    """
    os.environ.setdefault("RAYON_NUM_THREADS", "1")


def _run_single_no_llm(args: argparse.Namespace, scenario_config: Any = None) -> RunResult:
    """Worker function for parallel batch (no LLM clients — deterministic only).

    H-24: Parallel workers cannot share LLM client connections across processes.
    This function is only correct for simulate_only runs. The guard in
    run_batch() ensures narrated runs never reach here.
    """
    from chronicler.main import execute_run
    return execute_run(args, scenario_config=scenario_config)


def _write_summary(
    batch_dir: Path,
    results: list[RunResult],
    weights: dict[str, float] | None = None,
) -> None:
    """Write summary.md sorted by interestingness score."""
    scored = [(r, score_run(r, weights)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)

    lines = ["# Batch Summary\n"]
    lines.append("| Rank | Seed | Score | Dominant Faction | Wars | Collapses | Tech | Boring Civs |")
    lines.append("|------|------|-------|------------------|------|-----------|------|-------------|")

    for rank, (result, score) in enumerate(scored, 1):
        boring_str = ", ".join(result.boring_civs) if result.boring_civs else "-"
        lines.append(
            f"| {rank} | {result.seed} | {score:.1f} | {result.dominant_faction} "
            f"| {result.war_count} | {result.collapse_count} "
            f"| {result.tech_advancement_count} | {boring_str} |"
        )

    lines.append("")
    (batch_dir / "summary.md").write_text("\n".join(lines))
