"""Batch runner — run multiple chronicles with sequential seeds."""
from __future__ import annotations

import argparse
import copy
import multiprocessing
import threading
from pathlib import Path
from typing import Any, Callable

from chronicler.interestingness import score_run
from chronicler.types import RunResult

# Type alias for progress callbacks: (completed, total, current_seed) -> None
ProgressCallback = Callable[[int, int, int], None]


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

    Parameters
    ----------
    progress_cb : optional callback(completed, total, current_seed) called after each seed.
    cancel_event : optional threading.Event; if set, batch stops between seeds.
    tuning_overrides_dict : optional in-memory overrides (bypasses YAML file I/O).
    """
    base_seed = args.seed or 42
    count = args.batch
    base_output = Path(args.output).parent if hasattr(args, 'output') else Path("output")
    batch_dir = base_output / f"batch_{base_seed}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []

    # Load tuning overrides: prefer in-memory dict, fall back to YAML file
    tuning_overrides: dict[str, float] = tuning_overrides_dict or {}
    if not tuning_overrides and getattr(args, "tuning", None):
        from chronicler.tuning import load_tuning
        tuning_overrides = load_tuning(Path(args.tuning))

    if args.parallel:
        workers = args.parallel if isinstance(args.parallel, int) and args.parallel > 1 else max(1, multiprocessing.cpu_count() - 1)
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

        with multiprocessing.Pool(workers) as pool:
            async_results = [pool.apply_async(_run_single_no_llm, a) for a in run_args]
            for i, ar in enumerate(async_results):
                if cancel_event and cancel_event.is_set():
                    pool.terminate()
                    break
                result = ar.get()
                results.append(result)
                run_seed = base_seed + i
                if progress_cb:
                    progress_cb(i + 1, count, run_seed)
    else:
        for i in range(count):
            if cancel_event and cancel_event.is_set():
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
            if progress_cb:
                progress_cb(i + 1, count, run_seed)
            print(f"  Batch run {i + 1}/{count} complete (seed {run_seed})")

    # Write summary
    weights = scenario_config.interestingness_weights if scenario_config and hasattr(scenario_config, 'interestingness_weights') else None
    _write_summary(batch_dir, results, weights)

    return batch_dir


def _run_single_no_llm(args: argparse.Namespace, scenario_config: Any = None) -> RunResult:
    """Worker function for parallel batch (no LLM clients — deterministic only)."""
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
