#!/usr/bin/env python3
"""Re-score the cohort oracle under methods 1, 2 and 3 on retained sidecars.

``rescore_cohort_oracle.py OUT.json DIR [DIR ...] [--turns N]``

Each ``DIR`` is a batch directory (``seed_*`` below it) or one run's
directory. Runs are read with ``validation_io.load_seed_runs`` when the
directory holds bundles. A directory whose bundles were pruned is read
from its sidecars alone (``validation_relationships.arrow``,
``validation_memory_signatures.arrow``, ``validation_needs.arrow``,
``agent_events.arrow``) with ``--turns`` as every run's length, which is
all the cohort oracle reads. Oracle code only: nothing is simulated.

Where ``DIR`` holds a ``validate_report_*.json`` with a cohort result, the
re-score under that result's method is compared with it field for field.
Prints one line per directory and writes every result to ``OUT.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chronicler import validation_io as vio

SIDECARS = ("validation_relationships.arrow", "validation_memory_signatures.arrow",
            "validation_needs.arrow", "agent_events.arrow")


def _sidecar_runs(directory: Path, turns: int) -> list[dict]:
    """Runs rebuilt from the sidecars of every seed directory below ``directory``."""
    seed_dirs = sorted(path.parent for path in directory.rglob(SIDECARS[0]))
    runs = []
    for seed_dir in seed_dirs:
        if not all((seed_dir / name).exists() for name in SIDECARS):
            continue
        seed = int(seed_dir.name.rpartition("_")[2]) if seed_dir.name.startswith("seed_") else None
        runs.append({
            "seed": seed,
            "seed_dir": seed_dir,
            "bundle": {"metadata": {"total_turns": turns}},
            "events": vio._load_agent_events(seed_dir),
            "deaths": vio._load_agent_deaths(seed_dir),
            "relationship_columns": vio._read_arrow_columns(seed_dir / "validation_relationships.arrow"),
            "memory_columns": vio._read_arrow_columns(seed_dir / "validation_memory_signatures.arrow"),
            "needs_columns": vio._read_arrow_columns(seed_dir / "validation_needs.arrow"),
            "graph_snapshot": None,
            "needs_snapshot": None,
        })
    return runs


def _summary(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "per_seed"}


def rescore(directory: Path, turns: int | None) -> dict:
    has_bundles = any(directory.rglob(vio.BUNDLE_FILENAME))
    if has_bundles:
        runs = vio.load_seed_runs(directory, selected_oracles={"cohort"})
        source = "bundles"
    elif turns:
        runs = _sidecar_runs(directory, turns)
        source = f"sidecars, {turns} turns"
    else:
        raise SystemExit(f"{directory}: no bundles; give --turns to read the sidecars alone")
    out = {
        "directory": str(directory),
        "source": source,
        "seeds": [run.get("seed") for run in runs],
        "turns": sorted({vio._total_turns(run) for run in runs}),
        "method_1": vio.run_cohort_oracle(runs, method_version=1),
        "method_2": vio.run_cohort_oracle(runs, method_version=2),
        "method_3": vio.run_cohort_oracle(runs, method_version=3),
    }
    reports = sorted(directory.glob("validate_report_*.json"))
    if reports:
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        recorded = report.get("results", {}).get("cohort")
        if isinstance(recorded, dict):
            # A result without a method_version is method 1.
            version = recorded.get("method_version", 1)
            out["report"] = str(reports[0])
            out["report_method"] = version
            if version >= vio.COHORT_ORACLE_METHOD_VERSION:
                # Method 4 reads the batch's ablation arms (chronicler.validate --ablation-dir).
                out["rescore_equals_report"] = None
            else:
                out["rescore_equals_report"] = recorded == out.get(f"method_{version}")
    return out


def _line(item: dict) -> str:
    parts = [item["directory"], f"{len(item['seeds'])} seeds x {item['turns']}"]
    for key in ("method_1", "method_2", "method_3"):
        result = item[key]
        if result.get("status") == "SKIP":
            parts.append(f"{key} SKIP ({result.get('reason')})")
            continue
        parts.append(
            f"{key} {result['status']} {result['seeds_with_expected_direction']}/{result['analyzed_seeds']}"
            f" (need {result['required_seed_count']}), median {result['median_effect_size']:.3f}")
    if "rescore_equals_report" in item:
        parts.append(f"method {item['report_method']} equals report: {item['rescore_equals_report']}")
    return " | ".join(parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("dirs", type=Path, nargs="+")
    parser.add_argument("--turns", type=int, default=None,
                        help="run length for directories without bundles")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; choose a new file")
    results = []
    for directory in args.dirs:
        item = rescore(directory, args.turns)
        print(_line(item), flush=True)
        results.append(item)
    args.out.write_text(json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
