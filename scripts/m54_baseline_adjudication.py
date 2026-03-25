#!/usr/bin/env python3
"""Adjudicate M54 migration regression against preserved same-machine controls."""
from __future__ import annotations

import argparse
import json
import platform
import socket
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CORE_ORACLES = ("community", "needs", "era", "cohort", "artifacts", "arcs")
DECODE_ORDER = ("utf-8", "utf-8-sig", "utf-16", "utf-16le")


@dataclass
class RegressionMetrics:
    status: str
    satisfaction_mean: float | None
    satisfaction_std: float | None
    migration_rate_per_agent_turn: float | None
    rebellion_rate_per_agent_turn: float | None
    gini_in_range_fraction: float | None
    occupation_ok: bool


@dataclass
class ReportSnapshot:
    name: str
    path: str
    core_oracles_ok: bool
    regression: RegressionMetrics
    determinism_status: str | None


def _load_json(path: Path) -> dict:
    raw = path.read_bytes()
    for enc in DECODE_ORDER:
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            continue
    raise ValueError(f"Unable to decode JSON report: {path}")


def _snapshot(name: str, path: Path) -> ReportSnapshot:
    data = _load_json(path)
    results = data.get("results", {})
    core_ok = all(results.get(oracle, {}).get("status") == "PASS" for oracle in CORE_ORACLES)
    reg = results.get("regression", {})
    det = results.get("determinism", {}).get("status")
    metrics = RegressionMetrics(
        status=str(reg.get("status")),
        satisfaction_mean=_as_float(reg.get("satisfaction_mean")),
        satisfaction_std=_as_float(reg.get("satisfaction_std")),
        migration_rate_per_agent_turn=_as_float(reg.get("migration_rate_per_agent_turn")),
        rebellion_rate_per_agent_turn=_as_float(reg.get("rebellion_rate_per_agent_turn")),
        gini_in_range_fraction=_as_float(reg.get("gini_in_range_fraction")),
        occupation_ok=bool(reg.get("occupation_ok")),
    )
    return ReportSnapshot(
        name=name,
        path=str(path),
        core_oracles_ok=core_ok,
        regression=metrics,
        determinism_status=det,
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _only_satisfaction_floor_miss(metrics: RegressionMetrics) -> bool:
    if metrics.status != "FAIL":
        return False
    if metrics.satisfaction_mean is None or metrics.satisfaction_std is None:
        return False
    if metrics.migration_rate_per_agent_turn is None or metrics.rebellion_rate_per_agent_turn is None:
        return False
    if metrics.gini_in_range_fraction is None:
        return False
    return (
        metrics.satisfaction_mean < 0.45
        and 0.10 <= metrics.satisfaction_std <= 0.25
        and 0.05 <= metrics.migration_rate_per_agent_turn <= 0.15
        and 0.02 <= metrics.rebellion_rate_per_agent_turn <= 0.08
        and metrics.gini_in_range_fraction >= 0.20
        and metrics.occupation_ok
    )


def _spread(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def _git_head(path: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return proc.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudicate M54 regression reports against controls")
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--control-report", type=Path, action="append", required=True)
    parser.add_argument("--accepted-baseline-report", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--satisfaction-delta-max", type=float, default=0.005)
    parser.add_argument("--migration-delta-max", type=float, default=0.001)
    parser.add_argument("--rebellion-delta-max", type=float, default=0.001)
    parser.add_argument("--gini-delta-max", type=float, default=0.005)
    args = parser.parse_args()

    candidate = _snapshot("candidate", args.candidate_report)
    controls = [
        _snapshot(f"control_{idx+1}", path)
        for idx, path in enumerate(args.control_report)
    ]
    accepted = (
        _snapshot("accepted_baseline", args.accepted_baseline_report)
        if args.accepted_baseline_report
        else None
    )

    control_sat = [c.regression.satisfaction_mean for c in controls if c.regression.satisfaction_mean is not None]
    control_mig = [c.regression.migration_rate_per_agent_turn for c in controls if c.regression.migration_rate_per_agent_turn is not None]
    control_reb = [c.regression.rebellion_rate_per_agent_turn for c in controls if c.regression.rebellion_rate_per_agent_turn is not None]
    control_gini = [c.regression.gini_in_range_fraction for c in controls if c.regression.gini_in_range_fraction is not None]

    control_mean = {
        "satisfaction_mean": statistics.mean(control_sat) if control_sat else None,
        "migration_rate_per_agent_turn": statistics.mean(control_mig) if control_mig else None,
        "rebellion_rate_per_agent_turn": statistics.mean(control_reb) if control_reb else None,
        "gini_in_range_fraction": statistics.mean(control_gini) if control_gini else None,
    }
    control_spread = {
        "satisfaction_mean": _spread(control_sat),
        "migration_rate_per_agent_turn": _spread(control_mig),
        "rebellion_rate_per_agent_turn": _spread(control_reb),
        "gini_in_range_fraction": _spread(control_gini),
    }

    delta = {
        "satisfaction_mean": (
            candidate.regression.satisfaction_mean - control_mean["satisfaction_mean"]
            if candidate.regression.satisfaction_mean is not None and control_mean["satisfaction_mean"] is not None
            else None
        ),
        "migration_rate_per_agent_turn": (
            candidate.regression.migration_rate_per_agent_turn - control_mean["migration_rate_per_agent_turn"]
            if candidate.regression.migration_rate_per_agent_turn is not None and control_mean["migration_rate_per_agent_turn"] is not None
            else None
        ),
        "rebellion_rate_per_agent_turn": (
            candidate.regression.rebellion_rate_per_agent_turn - control_mean["rebellion_rate_per_agent_turn"]
            if candidate.regression.rebellion_rate_per_agent_turn is not None and control_mean["rebellion_rate_per_agent_turn"] is not None
            else None
        ),
        "gini_in_range_fraction": (
            candidate.regression.gini_in_range_fraction - control_mean["gini_in_range_fraction"]
            if candidate.regression.gini_in_range_fraction is not None and control_mean["gini_in_range_fraction"] is not None
            else None
        ),
    }

    controls_core_ok = all(c.core_oracles_ok for c in controls)
    controls_floor_only = all(_only_satisfaction_floor_miss(c.regression) for c in controls)
    candidate_core_ok = candidate.core_oracles_ok
    candidate_floor_only = _only_satisfaction_floor_miss(candidate.regression)
    candidate_abs_pass = candidate.regression.status == "PASS"

    control_matched = (
        delta["satisfaction_mean"] is not None
        and delta["migration_rate_per_agent_turn"] is not None
        and delta["rebellion_rate_per_agent_turn"] is not None
        and delta["gini_in_range_fraction"] is not None
        and abs(delta["satisfaction_mean"]) <= args.satisfaction_delta_max
        and abs(delta["migration_rate_per_agent_turn"]) <= args.migration_delta_max
        and abs(delta["rebellion_rate_per_agent_turn"]) <= args.rebellion_delta_max
        and abs(delta["gini_in_range_fraction"]) <= args.gini_delta_max
    )

    if candidate_abs_pass and candidate_core_ok:
        decision = "ACCEPT_ABSOLUTE_PASS"
    elif controls_core_ok and controls_floor_only and candidate_core_ok and candidate_floor_only and control_matched:
        decision = "ACCEPT_CONTROL_MATCHED"
    else:
        decision = "REJECT_DIVERGENCE"

    output = {
        "metadata": {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "git_head": _git_head(Path.cwd()),
        },
        "decision": decision,
        "candidate": asdict(candidate),
        "controls": [asdict(c) for c in controls],
        "accepted_baseline": asdict(accepted) if accepted else None,
        "control_mean": control_mean,
        "control_spread": control_spread,
        "candidate_delta_vs_control_mean": delta,
        "tolerances": {
            "satisfaction_delta_max": args.satisfaction_delta_max,
            "migration_delta_max": args.migration_delta_max,
            "rebellion_delta_max": args.rebellion_delta_max,
            "gini_delta_max": args.gini_delta_max,
        },
        "checks": {
            "controls_core_ok": controls_core_ok,
            "controls_floor_only": controls_floor_only,
            "candidate_core_ok": candidate_core_ok,
            "candidate_floor_only": candidate_floor_only,
            "candidate_absolute_pass": candidate_abs_pass,
            "candidate_control_matched": control_matched,
        },
    }

    print(json.dumps(output, indent=2))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return 0 if decision.startswith("ACCEPT") else 2


if __name__ == "__main__":
    raise SystemExit(main())
