"""Profile-aware validation report gating.

This module gates an existing ``chronicler.validate`` JSON report without
re-running the simulation or oracles.  It intentionally separates raw oracle
execution from profile-specific release semantics:

* required oracle non-PASS statuses fail the selected profile;
* non-required non-PASS statuses remain informational;
* optional strict regression ratcheting can fail a full-profile report that
  only passed through calibrated regression adjudication.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_ORACLES_BY_PROFILE = {
    "subset": ["community", "needs", "cohort"],
    "full": ["community", "needs", "era", "cohort", "artifacts", "arcs", "regression"],
    "determinism-off": ["determinism"],
    "determinism-hybrid": ["determinism"],
}

PROFILE_CHOICES = tuple(REQUIRED_ORACLES_BY_PROFILE)


class ValidationGateInputError(ValueError):
    """Invalid profile, report path, or report JSON for validation gating."""


class _ValidationGateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - exercised via main()
        raise ValidationGateInputError(message)


def _oracle_status(report: dict[str, Any], oracle: str) -> str:
    result = report.get("results", {}).get(oracle)
    if not isinstance(result, dict):
        return "MISSING"
    status = result.get("status")
    return str(status) if status else "MISSING"


def _oracle_item(report: dict[str, Any], oracle: str, status: str | None = None) -> dict[str, Any]:
    result = report.get("results", {}).get(oracle)
    item: dict[str, Any] = {"oracle": oracle, "status": status or _oracle_status(report, oracle)}
    if isinstance(result, dict):
        reason = result.get("reason")
        if reason:
            item["reason"] = str(reason)
        adjudication = result.get("regression_adjudication") or result.get("creation_rate_adjudication")
        if adjudication:
            item["adjudication"] = str(adjudication)
    return item


def _strict_regression_failure(report: dict[str, Any]) -> dict[str, Any] | None:
    result = report.get("results", {}).get("regression")
    if not isinstance(result, dict):
        return None
    if result.get("status") != "PASS":
        return None
    if result.get("strict_regression_ok") is True or result.get("regression_adjudication") == "strict":
        return None
    adjudication = str(result.get("regression_adjudication") or "unknown")
    return {
        "oracle": "regression",
        "status": "NON_STRICT",
        "reason": f"strict regression required but adjudication={adjudication}",
        "adjudication": adjudication,
    }


def adjudicate_validation_report(
    profile: str,
    report: dict[str, Any],
    *,
    require_strict_regression: bool = False,
) -> dict[str, Any]:
    """Apply profile-specific gate semantics to a validation JSON report."""
    if profile not in REQUIRED_ORACLES_BY_PROFILE:
        raise ValidationGateInputError(f"unknown profile: {profile}")
    if not isinstance(report, dict):
        raise ValidationGateInputError("report JSON must be an object")
    if not isinstance(report.get("results"), dict):
        raise ValidationGateInputError("validation report must contain a results object")

    required_oracles = REQUIRED_ORACLES_BY_PROFILE[profile]
    all_oracles = list(report["results"])
    for oracle in required_oracles:
        if oracle not in all_oracles:
            all_oracles.append(oracle)

    required_failures: list[dict[str, Any]] = []
    informational_non_pass: list[dict[str, Any]] = []
    for oracle in all_oracles:
        status = _oracle_status(report, oracle)
        item = _oracle_item(report, oracle, status)
        if oracle in required_oracles:
            if status != "PASS":
                required_failures.append(item)
        elif status != "PASS":
            informational_non_pass.append(item)

    if require_strict_regression and "regression" in required_oracles:
        strict_failure = _strict_regression_failure(report)
        if strict_failure is not None:
            required_failures.append(strict_failure)

    return {
        "profile": profile,
        "ok": not required_failures,
        "required_oracles": required_oracles,
        "required_failures": required_failures,
        "informational_non_pass": informational_non_pass,
        "require_strict_regression": require_strict_regression,
    }


def format_gate_failure(decision: dict[str, Any]) -> str:
    failures = ", ".join(
        f"{item['oracle']}={item['status']}"
        + (f" ({item['reason']})" if item.get("reason") else "")
        for item in decision["required_failures"]
    )
    return f"Validation gate failed for profile {decision['profile']}: {failures}"


def format_gate_summary(decision: dict[str, Any]) -> str:
    if decision["ok"]:
        lines = [f"Validation gate passed for profile {decision['profile']}"]
    else:
        lines = [format_gate_failure(decision)]
    if decision["informational_non_pass"]:
        lines.append(
            "Informational non-PASS statuses: "
            + ", ".join(
                f"{item['oracle']}={item['status']}" for item in decision["informational_non_pass"]
            )
        )
    return "\n".join(lines)


# Backwards-compatible private name used by the historical validation runner tests.
_format_gate_failure = format_gate_failure


def load_validation_report(report_path: Path) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationGateInputError(f"report path does not exist: {report_path}") from exc
    except IsADirectoryError as exc:
        raise ValidationGateInputError(f"could not read report: {report_path} is a directory") from exc
    except UnicodeDecodeError as exc:
        raise ValidationGateInputError(f"could not decode report as UTF-8: {exc}") from exc
    except OSError as exc:
        raise ValidationGateInputError(f"could not read report: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationGateInputError(f"invalid report JSON: {exc.msg}") from exc
    if not isinstance(report, dict):
        raise ValidationGateInputError("report JSON must be an object")
    return report


def _dump_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _error_payload(profile: str | None, report_path: Path | None, reason: str) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "profile": profile,
        "report_path": str(report_path) if report_path is not None else None,
        "reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _ValidationGateArgumentParser(description="Gate an existing Chronicler validation report")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--require-strict-regression",
        action="store_true",
        help="For full profile reports, fail calibrated-floor regression passes.",
    )
    parser.add_argument("--text", action="store_true", help="Print a terminal summary instead of JSON")
    args = None
    try:
        args = parser.parse_args(argv)
        report = load_validation_report(args.report)
        decision = adjudicate_validation_report(
            args.profile,
            report,
            require_strict_regression=args.require_strict_regression,
        )
    except ValidationGateInputError as exc:
        _dump_json(_error_payload(
            getattr(args, "profile", None),
            getattr(args, "report", None),
            str(exc),
        ))
        return 1

    if args.text:
        sys.stdout.write(format_gate_summary(decision) + "\n")
    else:
        _dump_json(decision)
    return 0 if decision["ok"] else 2


__all__ = [
    "REQUIRED_ORACLES_BY_PROFILE",
    "PROFILE_CHOICES",
    "ValidationGateInputError",
    "adjudicate_validation_report",
    "format_gate_failure",
    "format_gate_summary",
    "load_validation_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
