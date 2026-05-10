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

from chronicler.validation_gate import (
    PROFILE_CHOICES,
    REQUIRED_ORACLES_BY_PROFILE,
    adjudicate_validation_report,
    build_gate_decision_payload,
    format_gate_failure as _format_gate_failure,
    format_gate_markdown,
    format_gate_summary,
)


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = "src" if not existing else f"src{os.pathsep}{existing}"
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


def _validation_error_report(batch_dir: Path, *, reason: str, returncode: int | None = None) -> dict[str, Any]:
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
    if returncode is not None:
        report["validation_subprocess"] = {"returncode": returncode}
    return report


def _report_from_validation_process(proc: subprocess.CompletedProcess[str], batch_dir: Path) -> tuple[dict[str, Any], str]:
    try:
        report = json.loads(proc.stdout)
        if not isinstance(report, dict):
            raise ValueError("validation report JSON must be an object")
    except (json.JSONDecodeError, ValueError) as exc:
        reason = f"validation subprocess produced invalid JSON: {exc}"
        report = _validation_error_report(batch_dir, reason=reason, returncode=proc.returncode)
        return report, json.dumps(report, indent=2) + "\n"
    if proc.returncode != 0:
        report.setdefault("validation_subprocess", {})["returncode"] = proc.returncode
    return report, proc.stdout


def validate_batch(
    batch_dir: Path,
    report_name: str,
    cwd: Path,
    env: dict[str, str],
    profile: str,
    *,
    require_strict_regression: bool = False,
) -> dict[str, Any]:
    report_path = batch_dir / report_name
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
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Validation report written to {report_path}")
    decision = adjudicate_validation_report(
        profile,
        report,
        require_strict_regression=require_strict_regression,
    )
    decision_path = batch_dir / f"gate_decision_{profile}.json"
    summary_path = batch_dir / f"gate_summary_{profile}.md"
    decision_payload = build_gate_decision_payload(decision, report, report_path=report_path)
    decision_path.write_text(json.dumps(decision_payload, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(format_gate_markdown(decision, report, report_path=report_path), encoding="utf-8")
    print(f"Validation gate decision written to {decision_path}")
    print(f"Validation gate summary written to {summary_path}")
    print(format_gate_summary(decision))
    return {
        "report_path": report_path,
        "decision_path": decision_path,
        "summary_path": summary_path,
        "decision": decision_payload,
    }


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
    args = apply_profile_defaults(parser.parse_args())

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
        )

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
    }
    (batch_dir / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not validation_result["decision"]["ok"]:
        print(_format_gate_failure(validation_result["decision"]), file=sys.stderr)
        raise SystemExit(validation_result["decision"]["exit_code"])


if __name__ == "__main__":
    main()
