#!/usr/bin/env python3
"""Run canonical M53b validation profiles.

Profiles:
- subset: 20 seeds x 200 turns, raw validation sidecars
- full: 200 seeds x 500 turns, validation sidecars + condensed summaries
- determinism-off: two duplicate-seed aggregate runs
- determinism-hybrid: two duplicate-seed hybrid runs
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronicler.artifact_io import (
    ArtifactIOError,
    atomic_write_json,
    atomic_write_text,
    strict_json_dumps,
    strict_json_loads,
)
from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown
from chronicler.validation_gate import (
    PROFILE_CHOICES,
    REQUIRED_ORACLES_BY_PROFILE,
    ValidationGateInputError,
    adjudicate_validation_report,
    build_gate_decision_payload,
    format_gate_failure as _format_gate_failure,
    format_gate_markdown,
    format_gate_summary,
    load_validation_report,
)


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    env["PYTHONHASHSEED"] = "0"
    return env


PROFILE_DEFAULTS = {
    "subset": {"seeds": 20, "turns": 200},
    "full": {"seeds": 200, "turns": 500},
    "determinism-off": {"seeds": 2, "turns": 200},
    "determinism-hybrid": {"seeds": 2, "turns": 200},
}


def apply_profile_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Fill omitted seeds/turns from the selected validation profile."""
    defaults = PROFILE_DEFAULTS[args.profile]
    if args.seeds is None:
        args.seeds = defaults["seeds"]
    if args.turns is None:
        args.turns = defaults["turns"]
    return args


def _batch_dir_for(output_root: Path, seed_start: int) -> Path:
    return output_root / f"batch_{seed_start}"


def run_subset(args: argparse.Namespace, cwd: Path, env: dict[str, str]) -> Path:
    output_root = args.output_root / "oracle_subset"
    cmd = [
        sys.executable,
        "-m",
        "chronicler.main",
        "--seed-range",
        f"{args.seed_start}-{args.seed_start + args.seeds - 1}",
        "--turns",
        str(args.turns),
        "--agents",
        "hybrid",
        "--simulate-only",
        "--validation-sidecar",
        "--parallel",
        str(args.parallel),
        "--output",
        str(output_root / "chronicle.md"),
    ]
    _run(cmd, cwd, env)
    return _batch_dir_for(output_root, args.seed_start)


def run_full(args: argparse.Namespace, cwd: Path, env: dict[str, str]) -> Path:
    output_root = args.output_root / "full_gate"
    cmd = [
        sys.executable,
        "-m",
        "chronicler.main",
        "--seed-range",
        f"{args.seed_start}-{args.seed_start + args.seeds - 1}",
        "--turns",
        str(args.turns),
        "--agents",
        "hybrid",
        "--simulate-only",
        "--validation-sidecar",
        "--parallel",
        str(args.parallel),
        "--output",
        str(output_root / "chronicle.md"),
    ]
    _run(cmd, cwd, env)
    return _batch_dir_for(output_root, args.seed_start)


def run_determinism(args: argparse.Namespace, cwd: Path, env: dict[str, str], agents: str) -> Path:
    output_root = args.output_root / f"determinism_{agents}"
    batch_dir = output_root / "batch_42"
    for suffix in ("a", "b"):
        seed_dir = batch_dir / f"seed_42_{suffix}"
        seed_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-m",
            "chronicler.main",
            "--seed",
            "42",
            "--turns",
            str(args.turns),
            "--agents",
            agents,
            "--simulate-only",
            "--output",
            str(seed_dir / "chronicle.md"),
            "--state",
            str(seed_dir / "state.json"),
        ]
        if agents == "hybrid":
            cmd.insert(-4, "--validation-sidecar")
        _run(cmd, cwd, env)
    return batch_dir


STDERR_TAIL_CHARS = 8000


def _stderr_tail(stderr: str | None) -> str | None:
    if not stderr:
        return None
    return stderr[-STDERR_TAIL_CHARS:]


def _validation_error_report(
    batch_dir: Path,
    *,
    reason: str,
    returncode: int | None = None,
    stderr: str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "batch_dir": str(batch_dir),
        "oracles": ["all"],
        "results": {
            "validation_cli": {
                "status": "ERROR",
                "reason": reason,
            }
        },
        "status": "ERROR",
        "reason": reason,
    }
    tail = _stderr_tail(stderr)
    if returncode is not None or tail is not None:
        validation_subprocess: dict[str, Any] = {}
        if returncode is not None:
            validation_subprocess["returncode"] = returncode
        if tail is not None:
            validation_subprocess["stderr_tail"] = tail
        report["validation_subprocess"] = validation_subprocess
    return report


def _report_from_validation_process(proc: subprocess.CompletedProcess[str], batch_dir: Path) -> tuple[dict[str, Any], str]:
    try:
        report = strict_json_loads(proc.stdout, label="validation subprocess JSON")
        if not isinstance(report, dict):
            raise ValueError("validation report JSON must be an object")
    except (ArtifactIOError, ValueError) as exc:
        reason = f"validation subprocess produced invalid JSON: {exc}"
        report = _validation_error_report(
            batch_dir,
            reason=reason,
            returncode=proc.returncode,
            stderr=proc.stderr,
        )
        return report, strict_json_dumps(report)
    if proc.returncode != 0:
        validation_subprocess = report.setdefault("validation_subprocess", {})
        if not isinstance(validation_subprocess, dict):
            validation_subprocess = {}
            report["validation_subprocess"] = validation_subprocess
        validation_subprocess["returncode"] = proc.returncode
        tail = _stderr_tail(proc.stderr)
        if tail is not None:
            validation_subprocess["stderr_tail"] = tail
    return report, strict_json_dumps(report)


def _paths_collide(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _reject_baseline_output_collisions(baseline_report: Path, output_paths: list[tuple[str, Path]]) -> None:
    for label, output_path in output_paths:
        if _paths_collide(baseline_report, output_path):
            raise ValidationGateInputError(f"baseline-report must be different from {label}")


def _markdown_escape(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "`", "*", "_", "[", "]", "(", ")", "!"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _comparison_error_summary(profile: str, reason: str) -> str:
    safe_reason = _markdown_escape(reason)
    return f"# Validation report comparison: {profile}\n\n**Status:** ERROR\n\n{safe_reason}\n"


def _comparison_error_result(
    profile: str,
    baseline_report: Path,
    current_report: Path,
    batch_dir: Path,
    *,
    reason: str,
    fail_on_regression: bool,
    require_strict_regression: bool = False,
) -> dict[str, Any]:
    comparison_path = batch_dir / f"compare_decision_{profile}.json"
    comparison_summary_path = batch_dir / f"compare_summary_{profile}.md"
    comparison = {
        "schema_version": 1,
        "profile": profile,
        "status": "ERROR",
        "reason": reason,
        "baseline_report_path": str(baseline_report),
        "current_report_path": str(current_report),
        "regression_detected": False,
        "regression_reasons": [],
        "require_strict_regression": require_strict_regression,
        "fail_on_regression": fail_on_regression,
        "exit_code": 1,
    }
    atomic_write_json(comparison_path, comparison)
    atomic_write_text(comparison_summary_path, _comparison_error_summary(profile, reason))
    print(f"Validation comparison error written to {comparison_path}")
    return {
        "comparison_path": comparison_path,
        "comparison_summary_path": comparison_summary_path,
        "comparison": comparison,
    }


def compare_batch_report(
    profile: str,
    baseline_report: Path,
    current_report: Path,
    batch_dir: Path,
    *,
    require_strict_regression: bool = False,
    fail_on_regression: bool = False,
) -> dict[str, Any]:
    try:
        baseline = load_validation_report(baseline_report)
        current = load_validation_report(current_report)
        comparison = compare_validation_reports(
            profile,
            baseline,
            current,
            require_strict_regression=require_strict_regression,
            fail_on_regression=fail_on_regression,
        )
    except ValidationGateInputError as exc:
        return _comparison_error_result(
            profile,
            baseline_report,
            current_report,
            batch_dir,
            reason=str(exc),
            fail_on_regression=fail_on_regression,
            require_strict_regression=require_strict_regression,
        )
    comparison["baseline_report_path"] = str(baseline_report)
    comparison["current_report_path"] = str(current_report)
    comparison_path = batch_dir / f"compare_decision_{profile}.json"
    comparison_summary_path = batch_dir / f"compare_summary_{profile}.md"
    atomic_write_json(comparison_path, comparison)
    atomic_write_text(comparison_summary_path, format_comparison_markdown(comparison))
    print(f"Validation comparison decision written to {comparison_path}")
    print(f"Validation comparison summary written to {comparison_summary_path}")
    if comparison["regression_detected"]:
        print("Validation comparison: REGRESSION " + ",".join(comparison["regression_reasons"]))
    else:
        print("Validation comparison: NO REGRESSION")
    return {
        "comparison_path": comparison_path,
        "comparison_summary_path": comparison_summary_path,
        "comparison": comparison,
    }


def validate_batch(
    batch_dir: Path,
    report_name: str,
    cwd: Path,
    env: dict[str, str],
    profile: str,
    *,
    require_strict_regression: bool = False,
    baseline_report: Path | None = None,
    fail_on_regression: bool = False,
) -> dict[str, Any]:
    report_path = batch_dir / report_name
    decision_path = batch_dir / f"gate_decision_{profile}.json"
    summary_path = batch_dir / f"gate_summary_{profile}.md"
    if baseline_report is not None:
        _reject_baseline_output_collisions(
            baseline_report,
            [
                ("current-report", report_path),
                ("gate-decision", decision_path),
                ("gate-summary", summary_path),
                ("compare-decision", batch_dir / f"compare_decision_{profile}.json"),
                ("compare-summary", batch_dir / f"compare_summary_{profile}.md"),
            ],
        )
    cmd = [
        sys.executable,
        "-m",
        "chronicler.validate",
        "--batch-dir",
        str(batch_dir),
        "--oracles",
        "all",
    ]
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    report, report_text = _report_from_validation_process(proc, batch_dir)
    atomic_write_text(report_path, report_text)
    print(f"Validation report written to {report_path}")
    decision = adjudicate_validation_report(
        profile,
        report,
        require_strict_regression=require_strict_regression,
    )
    decision_payload = build_gate_decision_payload(decision, report, report_path=report_path)
    atomic_write_json(decision_path, decision_payload)
    atomic_write_text(summary_path, format_gate_markdown(decision, report, report_path=report_path))
    print(f"Validation gate decision written to {decision_path}")
    print(f"Validation gate summary written to {summary_path}")
    print(format_gate_summary(decision))
    comparison_result: dict[str, Any] = {}
    if baseline_report is not None:
        comparison_result = compare_batch_report(
            profile,
            baseline_report,
            report_path,
            batch_dir,
            require_strict_regression=require_strict_regression,
            fail_on_regression=fail_on_regression,
        )
    result = {
        "report_path": report_path,
        "decision_path": decision_path,
        "summary_path": summary_path,
        "decision": decision_payload,
    }
    result.update(comparison_result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical M53b validation profiles")
    parser.add_argument(
        "--profile",
        required=True,
        choices=PROFILE_CHOICES,
    )
    parser.add_argument("--output-root", type=Path, default=Path("output/m53/canonical"))
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--seeds", type=int, default=None)
    parser.add_argument("--turns", type=int, default=None)
    parser.add_argument("--parallel", type=int, default=12)
    parser.add_argument(
        "--require-strict-regression",
        action="store_true",
        help="For full profile reports, fail calibrated-floor regression passes.",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        help="Optional prior validation report to compare against after the current gate runs.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="When --baseline-report is set, exit 2 for comparator-detected regressions.",
    )
    args = apply_profile_defaults(parser.parse_args())
    if args.fail_on_regression and args.baseline_report is None:
        parser.error("--fail-on-regression requires --baseline-report")

    cwd = Path.cwd()
    env = _build_env()

    if args.profile == "subset":
        batch_dir = run_subset(args, cwd, env)
        validation_result = validate_batch(
            batch_dir,
            "validate_report_subset.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
        )
    elif args.profile == "full":
        batch_dir = run_full(args, cwd, env)
        validation_result = validate_batch(
            batch_dir,
            "validate_report_full.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
        )
    elif args.profile == "determinism-off":
        batch_dir = run_determinism(args, cwd, env, "off")
        validation_result = validate_batch(
            batch_dir,
            "validate_report_determinism_off.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
        )
    else:
        batch_dir = run_determinism(args, cwd, env, "hybrid")
        validation_result = validate_batch(
            batch_dir,
            "validate_report_determinism_hybrid.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
            baseline_report=args.baseline_report,
            fail_on_regression=args.fail_on_regression,
        )

    comparison = validation_result.get("comparison")
    summary = {
        "profile": args.profile,
        "batch_dir": str(batch_dir),
        "report_path": str(validation_result["report_path"]),
        "decision_path": str(validation_result["decision_path"]),
        "summary_path": str(validation_result["summary_path"]),
        "gate_status": "PASS" if validation_result["decision"]["ok"] else "FAIL",
        "gate_exit_code": validation_result["decision"]["exit_code"],
        "seed_start": args.seed_start,
        "seeds": args.seeds,
        "turns": args.turns,
        "parallel": args.parallel,
        "pythonhashseed": env["PYTHONHASHSEED"],
        "require_strict_regression": args.require_strict_regression,
        "baseline_report_path": str(args.baseline_report) if args.baseline_report is not None else None,
        "fail_on_regression": args.fail_on_regression,
        "comparison_path": str(validation_result["comparison_path"]) if comparison is not None else None,
        "comparison_summary_path": str(validation_result["comparison_summary_path"]) if comparison is not None else None,
        "comparison_status": (
            "ERROR" if comparison and comparison.get("status") == "ERROR"
            else "REGRESSION" if comparison and comparison["regression_detected"]
            else "NO_REGRESSION" if comparison else None
        ),
        "comparison_exit_code": comparison["exit_code"] if comparison is not None else None,
        "comparison_reasons": comparison["regression_reasons"] if comparison is not None else [],
        "comparison_error": comparison.get("reason") if comparison is not None and comparison.get("status") == "ERROR" else None,
    }
    atomic_write_json(batch_dir / "run_manifest.json", summary)
    print(strict_json_dumps(summary), end="")
    if not validation_result["decision"]["ok"]:
        print(_format_gate_failure(validation_result["decision"]), file=sys.stderr)
        raise SystemExit(validation_result["decision"]["exit_code"])
    if comparison is not None and comparison["exit_code"] != 0:
        raise SystemExit(comparison["exit_code"])


if __name__ == "__main__":
    main()
