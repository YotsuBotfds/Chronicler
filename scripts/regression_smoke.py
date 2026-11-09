#!/usr/bin/env python3
"""Nightly regression smoke: compare a small hybrid batch's summary metrics to a fixture.

``.github/workflows/regression-smoke.yml`` runs 4 template seeds x 100 turns
(``m53b_run_validation.py --profile subset --seeds 4 --turns 100``) and then::

    python scripts/regression_smoke.py compare BATCH_DIR

``BATCH_DIR`` is the subset batch (``OUTPUT_ROOT/oracle_subset/batch_42``). The
metrics are the oracle statuses and the rounded summary values of its validation
report (``validate_report_subset.json``): any change is drift, intended or not.
Four seeds are too few for the gate's verdict, so a FAIL status there is a
recorded value, not a failure of the smoke; a difference from the fixture is.

After an intended outcome change, regenerate the fixture from a run of the new
source and commit it with the change::

    python scripts/regression_smoke.py write BATCH_DIR --commit SHA --platform TEXT

It reads files only; it never runs a simulation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "regression_smoke.json"
REPORT_NAME = "validate_report_subset.json"
RUN_MANIFEST_NAME = "run_manifest.json"
SCHEMA_VERSION = 1

# The run the fixture describes; compared exactly before any metric.
INVOCATION_KEYS = ("profile", "seed_start", "seeds", "turns", "worldgen", "pythonhashseed")
EXPECTED_INVOCATION = {"profile": "subset", "seed_start": 42, "seeds": 4, "turns": 100,
                       "worldgen": "template", "pythonhashseed": "0"}

# Report values compared, as (oracle, key) paths into ``results``.
METRIC_PATHS = (
    ("regression", "satisfaction_mean"),
    ("regression", "satisfaction_std"),
    ("regression", "latest_satisfaction_mean"),
    ("regression", "latest_satisfaction_std"),
    ("regression", "final_sample_satisfaction_mean"),
    ("regression", "migration_rate_per_agent_turn"),
    ("regression", "rebellion_rate_per_agent_turn"),
    ("regression", "gini_in_range_fraction"),
    ("regression", "occupation_violation_fraction"),
    ("regression", "latest_occupation_violation_fraction"),
    ("regression", "final_living_population_counts"),
    ("regression", "civ_survival_counts"),
    ("regression", "extinct_world_count"),
    ("regression", "treasury_bad_seed_count"),
    ("needs", "analyzed_seeds"),
    ("needs", "total_pairs"),
    ("needs", "informative_pairs"),
    ("needs", "concordant_pairs"),
    ("needs", "discordant_pairs"),
    ("needs", "net_concordance"),
    ("era", "collapse_episode_count"),
    ("era", "seeds_with_inflections"),
    ("artifacts", "total_artifacts"),
    ("artifacts", "loss_destruction_count"),
    ("arcs", "family_count"),
    ("community", "qualifying_seed_count"),
)


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract(report: Mapping, run_manifest: Mapping) -> dict:
    """The invocation, oracle statuses and metrics of one smoke batch."""
    results = report.get("results") or {}
    metrics = {}
    for oracle, key in METRIC_PATHS:
        section = results.get(oracle)
        metrics[f"{oracle}.{key}"] = section.get(key) if isinstance(section, Mapping) else None
    return {
        "invocation": {key: run_manifest.get(key) for key in INVOCATION_KEYS},
        "statuses": {name: (section or {}).get("status") for name, section in sorted(results.items())},
        "metrics": metrics,
    }


def load_batch(batch_dir: Path) -> dict:
    batch_dir = Path(batch_dir)
    missing = [name for name in (REPORT_NAME, RUN_MANIFEST_NAME) if not (batch_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{batch_dir}: missing {', '.join(missing)} (did the run finish?)")
    return extract(_read_json(batch_dir / REPORT_NAME), _read_json(batch_dir / RUN_MANIFEST_NAME))


def _equal(expected, actual, abs_tol: float) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) <= abs_tol
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_equal(e, a, abs_tol) for e, a in zip(expected, actual))
    return expected == actual


def compare(expected: Mapping, actual: Mapping, abs_tol: float = 0.0) -> list[str]:
    """Differences between the fixture's run and this run (empty when they match)."""
    problems = []
    for key in INVOCATION_KEYS:
        if expected["invocation"].get(key) != actual["invocation"].get(key):
            problems.append(f"invocation {key}: fixture {expected['invocation'].get(key)!r}, "
                            f"run {actual['invocation'].get(key)!r}")
    if problems:
        return problems
    for section in ("statuses", "metrics"):
        names = sorted(set(expected[section]) | set(actual[section]))
        for name in names:
            want, got = expected[section].get(name), actual[section].get(name)
            if not _equal(want, got, abs_tol):
                problems.append(f"{section} {name}: fixture {want!r}, run {got!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a regression-smoke batch to its fixture")
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_parser = sub.add_parser("compare", help="exit 1 when the batch differs from the fixture")
    cmp_parser.add_argument("batch_dir", type=Path)
    cmp_parser.add_argument("--fixture", type=Path, default=FIXTURE)
    cmp_parser.add_argument("--abs-tol", type=float, default=0.0,
                            help="absolute tolerance for numbers (default 0: the report rounds them)")
    write_parser = sub.add_parser("write", help="write the fixture from a batch")
    write_parser.add_argument("batch_dir", type=Path)
    write_parser.add_argument("--fixture", type=Path, default=FIXTURE)
    write_parser.add_argument("--commit", required=True, help="source commit the batch ran")
    write_parser.add_argument("--platform", required=True, help="machine, OS, Python and Rust of the run")
    write_parser.add_argument("--note", default="")
    args = parser.parse_args(argv)

    actual = load_batch(args.batch_dir)
    if args.command == "write":
        if actual["invocation"] != EXPECTED_INVOCATION:
            print(f"refusing: the batch ran {actual['invocation']}, not {EXPECTED_INVOCATION}", file=sys.stderr)
            return 2
        fixture = {"schema_version": SCHEMA_VERSION,
                   "provenance": {"commit": args.commit, "platform": args.platform, "note": args.note},
                   **actual}
        args.fixture.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.fixture}")
        return 0
    expected = _read_json(args.fixture)
    if expected.get("schema_version") != SCHEMA_VERSION:
        print(f"fixture schema_version {expected.get('schema_version')!r}, expected {SCHEMA_VERSION}",
              file=sys.stderr)
        return 2
    problems = compare(expected, actual, args.abs_tol)
    for line in problems:
        print(line)
    print(f"regression smoke: {'DRIFT' if problems else 'MATCH'} against {args.fixture} "
          f"(fixture from {expected['provenance']['commit']})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
