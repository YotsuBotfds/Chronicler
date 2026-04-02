"""Validation CLI facade with backwards-compatible re-exports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .validation_io import *  # noqa: F401,F403
from .validation_io import __all__ as _validation_io_all
from .validation_oracles import *  # noqa: F401,F403
from .validation_oracles import __all__ as _validation_oracle_all

ORACLE_RUNNERS = {
    "determinism": run_determinism_gate,
    "community": run_community_oracle,
    "needs": run_needs_oracle,
    "era": run_era_oracle,
    "cohort": run_cohort_oracle,
    "artifacts": run_artifact_oracle,
    "arcs": run_arc_oracle,
    "regression": run_regression_summary,
}

SEED_RUN_ORACLES = set(ORACLE_RUNNERS) - {"determinism"}


def _normalize_requested_oracles(oracles: list[str]) -> set[str]:
    selected = set(oracles)
    if "all" in selected:
        return set(ORACLE_RUNNERS)
    unknown = sorted(selected - set(ORACLE_RUNNERS))
    if unknown:
        raise ValidationRequestError(f"unknown_oracles: {', '.join(unknown)}")
    return selected


def run_oracles(batch_dir: Path, oracles: list[str]) -> dict:
    """Run specified oracles and return a structured report."""
    selected = _normalize_requested_oracles(oracles)
    results: dict[str, dict] = {}
    seed_runs: list[dict] | None = None

    def ensure_seed_runs() -> list[dict]:
        nonlocal seed_runs
        if seed_runs is None:
            seed_runs = load_seed_runs(batch_dir, selected_oracles=selected & SEED_RUN_ORACLES)
        return seed_runs

    for oracle_name in sorted(selected):
        runner = ORACLE_RUNNERS[oracle_name]
        try:
            if oracle_name == "determinism":
                results[oracle_name] = runner(batch_dir)
            else:
                results[oracle_name] = runner(ensure_seed_runs())
        except (ValidationRequestError, ValidationDependencyError):
            raise
        except Exception as exc:
            results[oracle_name] = {
                "status": "ERROR",
                "reason": f"{type(exc).__name__}: {exc}",
            }

    return {
        "batch_dir": str(batch_dir),
        "oracles": sorted(selected),
        "results": results,
    }


def _error_report(batch_dir: Path, oracles: list[str], reason: str) -> dict:
    return {
        "batch_dir": str(batch_dir),
        "oracles": list(oracles),
        "results": {},
        "status": "ERROR",
        "reason": reason,
    }


def _dump_report(report: dict) -> None:
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    args = parser.parse_args(argv)
    try:
        report = run_oracles(args.batch_dir, args.oracles)
    except (ValidationRequestError, ValidationDependencyError) as exc:
        _dump_report(_error_report(args.batch_dir, args.oracles, str(exc)))
        return 1

    _dump_report(report)
    if any(result.get("status") == "ERROR" for result in report["results"].values()):
        return 1
    return 0


__all__ = list(_validation_io_all) + list(_validation_oracle_all) + [
    "ORACLE_RUNNERS",
    "SEED_RUN_ORACLES",
    "_normalize_requested_oracles",
    "run_oracles",
    "_error_report",
    "_dump_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
