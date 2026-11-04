"""Read-only capacity diagnosis of saved community-method-2 counters.

This is conditional on the saved counters, not independent verification of
sidecars, a new oracle, or a change to any existing verdict.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import math
import os
from pathlib import Path
import stat

from .artifact_io import strict_json_dumps, strict_json_loads
from .validation_communities import (
    COMMUNITY_ORACLE_METHOD_VERSION,
    ORACLE1_COUNT_BAND,
    ORACLE1_MIN_SIZE,
    ORACLE1_REGION_SHARE_MAX,
)

MAX_REPORT_BYTES = 64 * 1024 * 1024
_SCOPE = "detected_community_snapshot_observations"
_NOTES = [
    "Counts are repeated detected-community/snapshot observations, not independent groups.",
    "Regions without detected communities are outside these counters.",
    "Minimum-size capacity admits a community of five; larger communities can still fail.",
    "The global community-count band is unscaled across world sizes.",
    "Greater regional population does not establish detection or any oracle PASS.",
    "Original report counters and verdicts are unchanged and not independently verified.",
]


def _object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _count(value, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def diagnose_report(report: dict) -> dict:
    """Describe structural share failures using an existing validation report."""
    report = _object(report, "report")
    threshold = math.ceil(
        Fraction(ORACLE1_MIN_SIZE) / Fraction(str(ORACLE1_REGION_SHARE_MAX))
    )
    base = {
        "diagnostic_version": 1,
        "scope": _SCOPE,
        "conditional_on_saved_counters": True,
        "minimum_community_size": ORACLE1_MIN_SIZE,
        "maximum_region_share": ORACLE1_REGION_SHARE_MAX,
        "minimum_region_population": threshold,
        "global_community_count_band": list(ORACLE1_COUNT_BAND),
        "notes": list(_NOTES),
    }

    def unavailable(reason: str) -> dict:
        return {**base, "status": "unavailable", "reason": reason}

    if "results" not in report:
        return unavailable("results_missing")
    results = _object(report["results"], "results")
    if "community" not in results:
        return unavailable("community_result_missing")
    community = _object(results["community"], "results.community")
    if "method_version" not in community:
        return unavailable("legacy_or_unversioned_community_result")
    version = _count(community["method_version"], "community.method_version")
    if version != COMMUNITY_ORACLE_METHOD_VERSION:
        return unavailable("unsupported_community_method")

    oracle_status = community.get("status")
    if oracle_status not in ("PASS", "FAIL", "SKIP"):
        raise ValueError("community.status must be PASS, FAIL or SKIP")
    spec = _object(community.get("spec"), "community.spec")
    spec_status = spec.get("status")
    if spec_status == "SKIP":
        return unavailable("spec_component_skipped")
    if spec_status not in ("PASS", "FAIL"):
        raise ValueError("community.spec.status must be PASS, FAIL or SKIP")

    total = _count(spec.get("communities"), "spec.communities")
    share = _object(spec.get("region_share"), "spec.region_share")
    above = _count(share.get("communities_above"), "communities_above")
    large = _object(
        share.get("communities_in_regions_of_at_least"),
        "communities_in_regions_of_at_least",
    )
    population = _count(large.get("population"), "population threshold")
    eligible = _count(large.get("communities"), "capacity-eligible communities")
    if population != threshold:
        raise ValueError("saved population threshold differs from method-2 criteria")
    if above > total or eligible > total:
        raise ValueError("component count exceeds total communities")
    forced = total - eligible
    if above < forced:
        raise ValueError("share failures are fewer than structurally forced failures")
    if spec_status == "PASS" and above:
        raise ValueError("spec PASS contradicts recorded region-share failures")

    return {
        **base,
        "status": "assessed" if total else "no_observations",
        "original_community_status": oracle_status,
        "original_spec_status": spec_status,
        "observations": total,
        "minimum_size_capacity_eligible_observations": eligible,
        "structurally_forced_region_share_failures": forced,
        "region_share_failures_among_capacity_eligible_observations": above - forced,
        "observations_within_region_share_bound": total - above,
        "fraction_structurally_forced_failures": forced / total if total else None,
        "structural_constraint_observed": bool(forced) if total else None,
    }


def _read_regular_report(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("report input must be a regular file")
        if info.st_size > MAX_REPORT_BYTES:
            raise ValueError("report exceeds byte limit")
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("report exceeds byte limit")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Existing validation-report JSON")
    args = parser.parse_args(argv)
    try:
        raw = _read_regular_report(args.report)
        report = strict_json_loads(raw.decode("utf-8"), label="validation report")
        result = {
            "input_report_sha256": hashlib.sha256(raw).hexdigest(),
            "input_bytes": len(raw),
            "diagnostic": diagnose_report(report),
        }
        output = strict_json_dumps(result)
    except (OSError, ValueError, RecursionError) as error:
        parser.error(str(error))
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
