"""Compare two Chronicler validation reports without rerunning validation."""
from __future__ import annotations

import argparse
import html
import math
import sys
from pathlib import Path
from typing import Any

from chronicler.artifact_io import ArtifactIOError, atomic_write_json, atomic_write_text, strict_json_dumps
from chronicler.validation_gate import (
    PROFILE_CHOICES,
    REQUIRED_ORACLES_BY_PROFILE,
    ValidationGateInputError,
    adjudicate_validation_report,
    load_validation_report,
)


def _failure_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("oracle", "")),
        str(item.get("status", "")),
        str(item.get("reason", "")),
        str(item.get("adjudication", "")),
    )


def _oracle_item(report: dict[str, Any], oracle: str) -> dict[str, Any]:
    result = report.get("results", {}).get(oracle)
    if not isinstance(result, dict):
        return {"status": "MISSING"}
    item: dict[str, Any] = {"status": str(result.get("status") or "MISSING")}
    reason = result.get("reason")
    if reason:
        item["reason"] = str(reason)
    adjudication = result.get("regression_adjudication") or result.get("creation_rate_adjudication")
    if adjudication:
        item["adjudication"] = str(adjudication)
    return item


def _oracle_status_changes(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    names = sorted(set(baseline.get("results", {})) | set(current.get("results", {})))
    changes: list[dict[str, Any]] = []
    for oracle in names:
        left = _oracle_item(baseline, oracle)
        right = _oracle_item(current, oracle)
        if left == right:
            continue
        item: dict[str, Any] = {
            "oracle": oracle,
            "baseline_status": left.get("status"),
            "current_status": right.get("status"),
        }
        for prefix, source in (("baseline", left), ("current", right)):
            if source.get("reason"):
                item[f"{prefix}_reason"] = source["reason"]
            if source.get("adjudication"):
                item[f"{prefix}_adjudication"] = source["adjudication"]
        changes.append(item)
    return changes


def _list_field(report: dict[str, Any], oracle: str, field: str) -> list[str]:
    result = report.get("results", {}).get(oracle)
    if not isinstance(result, dict):
        return []
    value = result.get(field, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _set_delta(baseline: list[str], current: list[str]) -> tuple[list[str], list[str]]:
    left = set(baseline)
    right = set(current)
    return sorted(right - left), sorted(left - right)


def _regression_result(report: dict[str, Any]) -> dict[str, Any]:
    result = report.get("results", {}).get("regression")
    return result if isinstance(result, dict) else {}


def _finite_numeric(value: Any, path: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ValidationGateInputError(f"non-finite numeric diagnostic: {path}") from exc
    if not math.isfinite(numeric):
        raise ValidationGateInputError(f"non-finite numeric diagnostic: {path}")
    return numeric


def _reject_nonfinite(value: Any, path: str) -> None:
    _finite_numeric(value, path)
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}[{index}]")


def _numeric_delta(left: Any, right: Any, key: str) -> dict[str, float] | None:
    left_numeric = _finite_numeric(left, key)
    right_numeric = _finite_numeric(right, key)
    if left_numeric is None or right_numeric is None:
        return None
    delta = right_numeric - left_numeric
    if not math.isfinite(delta):
        raise ValidationGateInputError(f"non-finite numeric diagnostic: {key}")
    return {
        "baseline": round(left_numeric, 6),
        "current": round(right_numeric, 6),
        "delta": round(delta, 6),
    }


def _regression_metric_deltas(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, dict[str, float]]:
    baseline_diag = _regression_result(baseline).get("regression_floor_diagnostics", {})
    current_diag = _regression_result(current).get("regression_floor_diagnostics", {})
    if not isinstance(baseline_diag, dict) or not isinstance(current_diag, dict):
        return {}
    deltas: dict[str, dict[str, float]] = {}
    for metric in sorted(set(baseline_diag) | set(current_diag)):
        left = baseline_diag.get(metric, {})
        right = current_diag.get(metric, {})
        if not isinstance(left, dict) or not isinstance(right, dict):
            continue
        for field in ("value", "strict_min_delta", "calibrated_min_delta", "max_delta"):
            key = f"regression_floor_diagnostics.{metric}.{field}"
            delta = _numeric_delta(left.get(field), right.get(field), key)
            if delta is not None:
                deltas[key] = delta
    return deltas


def _proven_strict_regression(result: dict[str, Any]) -> bool:
    if result.get("strict_regression_ok") is True:
        return True
    if result.get("strict_regression_ok") is False:
        return False
    return result.get("regression_adjudication") == "strict"


def compare_validation_reports(
    profile: str,
    baseline_report: dict[str, Any],
    current_report: dict[str, Any],
    *,
    require_strict_regression: bool = False,
    fail_on_regression: bool = False,
) -> dict[str, Any]:
    _reject_nonfinite(baseline_report, "baseline_report")
    _reject_nonfinite(current_report, "current_report")
    baseline_decision = adjudicate_validation_report(
        profile,
        baseline_report,
        require_strict_regression=require_strict_regression,
    )
    current_decision = adjudicate_validation_report(
        profile,
        current_report,
        require_strict_regression=require_strict_regression,
    )
    baseline_failures = baseline_decision["required_failures"]
    current_failures = current_decision["required_failures"]
    baseline_keys = {_failure_key(item) for item in baseline_failures}
    current_keys = {_failure_key(item) for item in current_failures}
    new_required_failures = [item for item in current_failures if _failure_key(item) not in baseline_keys]
    resolved_required_failures = [item for item in baseline_failures if _failure_key(item) not in current_keys]

    baseline_regression = _regression_result(baseline_report)
    current_regression = _regression_result(current_report)
    baseline_adj = baseline_regression.get("regression_adjudication")
    current_adj = current_regression.get("regression_adjudication")
    adjudication_change = None
    if baseline_adj != current_adj:
        adjudication_change = {"baseline": baseline_adj, "current": current_adj}

    strict_downgrade = _proven_strict_regression(baseline_regression) and not _proven_strict_regression(current_regression)

    added_strict, removed_strict = _set_delta(
        _list_field(baseline_report, "regression", "strict_regression_failed_checks"),
        _list_field(current_report, "regression", "strict_regression_failed_checks"),
    )
    added_relaxed, removed_relaxed = _set_delta(
        _list_field(baseline_report, "regression", "calibrated_floor_relaxed_checks"),
        _list_field(current_report, "regression", "calibrated_floor_relaxed_checks"),
    )

    metric_deltas = _regression_metric_deltas(baseline_report, current_report)
    regression_oracle_required = "regression" in REQUIRED_ORACLES_BY_PROFILE[profile]
    regression_reasons: list[str] = []
    if new_required_failures:
        regression_reasons.append("new_required_failures")
    if regression_oracle_required and strict_downgrade:
        regression_reasons.append("strict_regression_downgrade")
    if regression_oracle_required and added_strict:
        regression_reasons.append("strict_regression_failed_checks_added")

    regression_detected = bool(regression_reasons)
    exit_code = 2 if fail_on_regression and regression_detected else 0
    result: dict[str, Any] = {
        "schema_version": 1,
        "profile": profile,
        "baseline_decision": baseline_decision,
        "current_decision": current_decision,
        "new_required_failures": new_required_failures,
        "resolved_required_failures": resolved_required_failures,
        "oracle_status_changes": _oracle_status_changes(baseline_report, current_report),
        "regression_adjudication_change": adjudication_change,
        "strict_regression_downgrade": strict_downgrade,
        "strict_regression_failed_checks_added": added_strict,
        "strict_regression_failed_checks_removed": removed_strict,
        "calibrated_floor_relaxed_checks_added": added_relaxed,
        "calibrated_floor_relaxed_checks_removed": removed_relaxed,
        "metric_deltas": metric_deltas,
        "regression_detected": regression_detected,
        "regression_reasons": regression_reasons,
        "require_strict_regression": require_strict_regression,
        "fail_on_regression": fail_on_regression,
        "exit_code": exit_code,
    }
    return result


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - exercised via main()
        raise ValidationGateInputError(message)


def _dump_json(payload: dict[str, Any]) -> None:
    try:
        sys.stdout.write(strict_json_dumps(payload))
    except ArtifactIOError:  # pragma: no cover - defensive fallback for malformed error payloads
        sys.stdout.write('{"status":"ERROR","reason":"could not serialize JSON output"}\n')


def _error_payload(reason: str) -> dict[str, Any]:
    return {"status": "ERROR", "reason": reason}


def _load_labeled_report(path: Path, label: str) -> dict[str, Any]:
    try:
        return load_validation_report(path)
    except ValidationGateInputError as exc:
        reason = str(exc)
        if reason.startswith("invalid report JSON"):
            raise ValidationGateInputError(f"invalid {label} report JSON: {reason}") from exc
        raise ValidationGateInputError(f"invalid {label} report: {reason}") from exc


def _paths_collide(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _reject_output_collisions(
    baseline_path: Path,
    current_path: Path,
    decision_path: Path | None,
    summary_path: Path | None,
) -> None:
    if _paths_collide(baseline_path, current_path):
        raise ValidationGateInputError("baseline-report and current-report must be different paths")
    labeled_inputs = (("baseline-report", baseline_path), ("current-report", current_path))
    for output_label, output_path in (("decision-output", decision_path), ("summary-output", summary_path)):
        if output_path is None:
            continue
        for input_label, input_path in labeled_inputs:
            if _paths_collide(output_path, input_path):
                raise ValidationGateInputError(f"{output_label} must be different from {input_label}")
    if decision_path is not None and summary_path is not None and _paths_collide(decision_path, summary_path):
        raise ValidationGateInputError("decision-output and summary-output must be different paths")


def _markdown_cell(value: Any) -> str:
    text = html.escape(str(value), quote=True)
    for char in ("\\", "`", "*", "_", "[", "]", "(", ")", "!"):
        text = text.replace(char, f"\\{char}")
    return (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
        .replace("|", "\\|")
    )


def format_comparison_markdown(result: dict[str, Any]) -> str:
    status = "REGRESSION" if result["regression_detected"] else "NO REGRESSION"
    lines = [
        f"# Validation report comparison: {result['profile']}",
        "",
        f"**Status:** {status}",
        f"**Exit code:** {result['exit_code']}",
        "",
        "## Regression reasons",
        "",
    ]
    if result["regression_reasons"]:
        lines.extend(f"- `{reason}`" for reason in result["regression_reasons"])
    else:
        lines.append("_None._")
    for title, key in (
        ("New required failures", "new_required_failures"),
        ("Resolved required failures", "resolved_required_failures"),
    ):
        lines.extend(["", f"## {title}", ""])
        rows = result[key]
        if not rows:
            lines.append("_None._")
            continue
        lines.extend(["| Oracle | Status | Reason |", "| --- | --- | --- |"])
        for item in rows:
            lines.append(
                "| "
                + " | ".join(_markdown_cell(item.get(field, "")) for field in ("oracle", "status", "reason"))
                + " |"
            )
    if result["regression_adjudication_change"]:
        lines.extend([
            "",
            "## Regression adjudication",
            "",
            f"- baseline: {_markdown_cell(result['regression_adjudication_change']['baseline'])}",
            f"- current: {_markdown_cell(result['regression_adjudication_change']['current'])}",
        ])
    if result["metric_deltas"]:
        lines.extend(["", "## Metric deltas", "", "| Metric | Baseline | Current | Delta |", "| --- | --- | --- | --- |"])
        for metric, delta in result["metric_deltas"].items():
            lines.append(
                f"| {_markdown_cell(metric)} | {delta['baseline']} | {delta['current']} | {delta['delta']} |"
            )
    return "\n".join(lines) + "\n"


def _write_text_output(path: Path, content: str, *, label: str) -> None:
    try:
        atomic_write_text(path, content)
    except ArtifactIOError as exc:
        raise ValidationGateInputError(f"could not write {label}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description="Compare two Chronicler validation reports")
    parser.add_argument("--profile", required=True, choices=PROFILE_CHOICES)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--current-report", required=True, type=Path)
    parser.add_argument("--require-strict-regression", action="store_true")
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--decision-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--text", action="store_true")
    args = None
    try:
        args = parser.parse_args(argv)
        _reject_output_collisions(
            args.baseline_report,
            args.current_report,
            args.decision_output,
            args.summary_output,
        )
        baseline = _load_labeled_report(args.baseline_report, "baseline")
        current = _load_labeled_report(args.current_report, "current")
        result = compare_validation_reports(
            args.profile,
            baseline,
            current,
            require_strict_regression=args.require_strict_regression,
            fail_on_regression=args.fail_on_regression,
        )
        result["baseline_report_path"] = str(args.baseline_report)
        result["current_report_path"] = str(args.current_report)
        if args.decision_output is not None:
            try:
                atomic_write_json(args.decision_output, result)
            except ArtifactIOError as exc:
                raise ValidationGateInputError(f"could not write decision-output: {exc}") from exc
        if args.summary_output is not None:
            _write_text_output(
                args.summary_output,
                format_comparison_markdown(result),
                label="summary-output",
            )
    except ValidationGateInputError as exc:
        _dump_json(_error_payload(str(exc)))
        return 1

    if args.text:
        sys.stdout.write(format_comparison_markdown(result))
    else:
        _dump_json(result)
    return result["exit_code"]


__all__ = [
    "compare_validation_reports",
    "format_comparison_markdown",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
