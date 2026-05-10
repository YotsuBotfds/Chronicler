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

from chronicler.validation_gate import (
    REQUIRED_ORACLES_BY_PROFILE,
    adjudicate_validation_report,
    format_gate_failure as _format_gate_failure,
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


def validate_batch(
    batch_dir: Path,
    report_name: str,
    cwd: Path,
    env: dict[str, str],
    profile: str,
    *,
    require_strict_regression: bool = False,
) -> Path:
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
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=True)
    report_path.write_text(proc.stdout, encoding="utf-8")
    print(f"Validation report written to {report_path}")
    report = json.loads(proc.stdout)
    decision = adjudicate_validation_report(
        profile,
        report,
        require_strict_regression=require_strict_regression,
    )
    if not decision["ok"]:
        raise SystemExit(_format_gate_failure(decision))
    if decision["informational_non_pass"]:
        print(
            "Informational non-PASS statuses: "
            + ", ".join(
                f"{item['oracle']}={item['status']}" for item in decision["informational_non_pass"]
            )
        )
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run canonical M53b validation profiles")
    parser.add_argument(
        "--profile",
        required=True,
        choices=["subset", "full", "determinism-off", "determinism-hybrid"],
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
        report_path = validate_batch(
            batch_dir,
            "validate_report_subset.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
        )
    elif args.profile == "full":
        batch_dir = run_full(args, cwd, env)
        report_path = validate_batch(
            batch_dir,
            "validate_report_full.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
        )
    elif args.profile == "determinism-off":
        batch_dir = run_determinism(args, cwd, env, "off")
        report_path = validate_batch(
            batch_dir,
            "validate_report_determinism_off.json",
            cwd,
            env,
            args.profile,
            require_strict_regression=args.require_strict_regression,
        )
    else:
        batch_dir = run_determinism(args, cwd, env, "hybrid")
        report_path = validate_batch(
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
        "report_path": str(report_path),
        "seed_start": args.seed_start,
        "seeds": args.seeds,
        "turns": args.turns,
        "parallel": args.parallel,
        "pythonhashseed": env["PYTHONHASHSEED"],
        "require_strict_regression": args.require_strict_regression,
    }
    (batch_dir / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
