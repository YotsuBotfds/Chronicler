#!/usr/bin/env python3
"""M28 Oracle Gate — 200-seed validation of hybrid vs aggregate mode."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from chronicler.shadow_oracle import OracleResult, CorrelationResult, OracleReport

METRICS = ["population", "military", "economy", "culture", "stability"]


def load_comparison_data(
    agg_dir: Path,
    hyb_dir: Path,
    checkpoints: list[int] | None = None,
) -> dict[str, list]:
    """Load aggregate and hybrid bundles, extract civ stats at checkpoints.

    Returns columnar dict matching shadow_oracle's expected format:
    keys: turn, agent_{metric}, agg_{metric} for each metric.
    """
    if checkpoints is None:
        checkpoints = [100, 250, 500]

    columns: dict[str, list] = {"turn": []}
    for m in METRICS:
        columns[f"agent_{m}"] = []
        columns[f"agg_{m}"] = []

    agg_seeds = _find_seed_dirs(agg_dir)
    hyb_seeds = _find_seed_dirs(hyb_dir)
    common_seeds = sorted(set(agg_seeds) & set(hyb_seeds))

    for seed_name in common_seeds:
        agg_bundle = _load_bundle(agg_dir / seed_name)
        hyb_bundle = _load_bundle(hyb_dir / seed_name)
        if agg_bundle is None or hyb_bundle is None:
            continue

        agg_snaps = {s["turn"]: s for s in agg_bundle["history"]}
        hyb_snaps = {s["turn"]: s for s in hyb_bundle["history"]}

        for turn in checkpoints:
            agg_snap = agg_snaps.get(turn)
            hyb_snap = hyb_snaps.get(turn)
            if agg_snap is None or hyb_snap is None:
                continue

            common_civs = set(agg_snap["civ_stats"]) & set(hyb_snap["civ_stats"])
            for civ_name in sorted(common_civs):
                agg_stats = agg_snap["civ_stats"][civ_name]
                hyb_stats = hyb_snap["civ_stats"][civ_name]
                columns["turn"].append(turn)
                for m in METRICS:
                    columns[f"agent_{m}"].append(hyb_stats[m])
                    columns[f"agg_{m}"].append(agg_stats[m])

    return columns


def _find_seed_dirs(batch_dir: Path) -> list[str]:
    """Find seed_N directories in a batch directory."""
    if not batch_dir.exists():
        return []
    return [d.name for d in sorted(batch_dir.iterdir())
            if d.is_dir() and d.name.startswith("seed_")]


def _load_bundle(seed_dir: Path) -> dict | None:
    """Load chronicle_bundle.json from a seed directory."""
    bundle_path = seed_dir / "chronicle_bundle.json"
    if not bundle_path.exists():
        return None
    with open(bundle_path) as f:
        return json.load(f)


def format_terminal_report(
    report: OracleReport,
    seeds: int,
    turns: int,
    agg_dir: str,
    hyb_dir: str,
    report_path: str,
) -> str:
    """Format oracle report as terminal-friendly text."""
    checkpoints = [100, 250, 500]
    lines = [
        "=== Oracle Gate Report ===",
        f"Seeds: {seeds}  Turns: {turns}  Checkpoints: {', '.join(str(c) for c in checkpoints)}",
        "",
        "--- Distribution Tests (KS + Anderson-Darling) ---",
    ]

    # Header
    cp_headers = "".join(f"Turn {c:<12}" for c in checkpoints)
    lines.append(f"{'':17}{cp_headers}")

    # Build lookup: (metric, turn) -> OracleResult
    dist_lookup: dict[tuple[str, int], OracleResult] = {}
    for r in report.results:
        if isinstance(r, OracleResult):
            dist_lookup[(r.metric, r.turn)] = r

    for metric in METRICS:
        cells = []
        for turn in checkpoints:
            r = dist_lookup.get((metric, turn))
            if r is None:
                cells.append(f"{'N/A':16}")
            elif r.passed:
                cells.append(f"PASS ({r.ks_p:.3f})   ")
            else:
                cells.append(f"FAIL ({r.ks_p:.3f})   ")
        lines.append(f"{metric:17}{''.join(cells)}")

    lines.append("")
    lines.append(f"Distribution: {report.ks_pass_count}/{report.ks_total} passed "
                 f"(threshold: 12/{report.ks_total})")

    # Correlation
    lines.append("")
    lines.append("--- Correlation Structure ---")
    lines.append(f"{'':17}{cp_headers}")

    corr_lookup: dict[tuple[str, str, int], CorrelationResult] = {}
    for r in report.results:
        if isinstance(r, CorrelationResult):
            corr_lookup[(r.metric1, r.metric2, r.turn)] = r

    for m1, m2 in [("military", "economy"), ("culture", "stability")]:
        cells = []
        for turn in checkpoints:
            r = corr_lookup.get((m1, m2, turn))
            if r is None:
                cells.append(f"{'N/A':16}")
            else:
                cells.append(f"{r.delta:<16.2f}")
        label = f"{m1[:3]}/{m2[:4]}"
        lines.append(f"{label:17}{''.join(cells)}")

    lines.append("")
    corr_status = "ALL PASSED" if report.correlation_passed else "FAILED"
    lines.append(f"Correlation: {corr_status} (threshold: delta < 0.15)")

    # Summary
    lines.append("")
    lines.append("--- Summary ---")
    overall = "PASS" if report.passed else "FAIL"
    lines.append(f"RESULT: {overall} ({report.ks_pass_count}/{report.ks_total} distribution, "
                 f"correlation {'OK' if report.correlation_passed else 'FAILED'})")
    lines.append("")
    lines.append(f"Aggregate dir: {agg_dir}")
    lines.append(f"Hybrid dir:    {hyb_dir}")
    lines.append(f"Report:        {report_path}")

    return "\n".join(lines)


def build_json_report(
    report: OracleReport,
    comparison_data: dict,
    seeds: int,
    turns: int,
    agg_dir: str,
    hyb_dir: str,
) -> dict:
    """Build JSON-serializable oracle report."""
    checkpoints = [100, 250, 500]

    dist_tests = []
    for r in report.results:
        if isinstance(r, OracleResult):
            dist_tests.append({
                "metric": r.metric,
                "turn": r.turn,
                "ks_stat": round(r.ks_stat, 6),
                "ks_p": round(r.ks_p, 6),
                "ad_p": round(r.ad_p, 6),
                "alpha": round(r.alpha, 6),
                "passed": r.passed,
            })

    # Compute raw correlations for JSON (not stored in CorrelationResult)
    turns_arr = np.array(comparison_data["turn"])
    corr_tests = []
    for r in report.results:
        if isinstance(r, CorrelationResult):
            mask = turns_arr == r.turn
            agent_m1 = np.array(comparison_data[f"agent_{r.metric1}"])[mask]
            agent_m2 = np.array(comparison_data[f"agent_{r.metric2}"])[mask]
            agg_m1 = np.array(comparison_data[f"agg_{r.metric1}"])[mask]
            agg_m2 = np.array(comparison_data[f"agg_{r.metric2}"])[mask]
            agent_corr = float(np.corrcoef(agent_m1, agent_m2)[0, 1]) if len(agent_m1) >= 3 else 0.0
            agg_corr = float(np.corrcoef(agg_m1, agg_m2)[0, 1]) if len(agg_m1) >= 3 else 0.0
            corr_tests.append({
                "metric1": r.metric1,
                "metric2": r.metric2,
                "turn": r.turn,
                "agent_corr": round(agent_corr, 6),
                "agg_corr": round(agg_corr, 6),
                "delta": round(r.delta, 6),
                "passed": r.passed,
            })

    return {
        "metadata": {
            "seeds": seeds,
            "turns": turns,
            "checkpoints": checkpoints,
            "aggregate_dir": str(agg_dir),
            "hybrid_dir": str(hyb_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "distribution_tests": dist_tests,
        "correlation_tests": corr_tests,
        "summary": {
            "distribution_passed": report.ks_pass_count,
            "distribution_total": report.ks_total,
            "distribution_threshold": 12,
            "correlation_all_passed": report.correlation_passed,
            "overall": "PASS" if report.passed else "FAIL",
        },
    }
