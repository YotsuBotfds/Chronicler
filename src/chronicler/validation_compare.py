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


def _oracle_method_version(report: dict[str, Any], oracle: str) -> int | None:
    """An oracle result's ``method_version``; a result without one is method 1."""
    result = report.get("results", {}).get(oracle)
    if not isinstance(result, dict):
        return None
    version = result.get("method_version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValidationGateInputError(f"invalid method_version for oracle {oracle}: {version!r}")
    return version


def _oracle_method_changes(baseline: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Oracles scored by different methods in the two reports (needs: method 1
    before 2026-10-25, method 2 before the binding component of method 3,
    method 3 before method 4's outcome window after the snapshot turn, 5
    and 6 before method 7's ablation component; cohort: method 1 before
    method 2's outcome window after the snapshot turn, 3 before method 4's
    ablation).

    Their statuses are not comparable: re-score the baseline batch with the
    current oracle to compare them.
    """
    changes: list[dict[str, Any]] = []
    for oracle in sorted(set(baseline.get("results", {})) & set(current.get("results", {}))):
        left = _oracle_method_version(baseline, oracle)
        right = _oracle_method_version(current, oracle)
        if left is not None and right is not None and left != right:
            changes.append({
                "oracle": oracle,
                "baseline_method_version": left,
                "current_method_version": right,
                "baseline_status": _oracle_item(baseline, oracle)["status"],
                "current_status": _oracle_item(current, oracle)["status"],
            })
    return changes


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


def _report_worlds(report: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """The world shapes a report measured; a report without ``worlds`` ran
    on the template world only (docs/integration/procedural-gates.md)."""
    worlds = report.get("worlds")
    if worlds is None:
        return [("template", None, None)]
    if not isinstance(worlds, list):
        raise ValidationGateInputError("report worlds must be a list")
    shapes = set()
    for item in worlds:
        if not isinstance(item, dict):
            raise ValidationGateInputError("report worlds entries must be objects")
        shapes.add((str(item.get("generator")), item.get("regions"), item.get("civs")))
    return sorted(shapes, key=lambda shape: (shape[0], shape[1] or 0, shape[2] or 0))


EXPLORATORY_FLAG = "--exploratory"

STATUS_MEANING = (
    "NO REGRESSION means no required gate newly fails in the current report (and, where regression is "
    "required, no strict-regression downgrade or newly failed strict check). It does not mean the "
    "distributions are unchanged: see the metric deltas and the oracle status changes."
)
EXPLORATORY_MEANING = (
    "EXPLORATORY: the reports measure different cohorts, so this comparison is not regression evidence."
)

# Validation evidence by category. The oracles of a report measure execution
# (the batch ran and validated), determinism, balance (bands on rates,
# shares and distributions) and mechanism (that a mechanism produces the
# association it should); they do not measure conservation, performance or
# rendering, so a pass here says nothing about those.
EVIDENCE_CATEGORIES = {
    "execution": (),
    "determinism": ("determinism",),
    "balance": ("regression", "artifacts", "arcs"),
    "mechanism": ("needs", "community", "cohort", "era"),
}
UNMEASURED_CATEGORIES = ("conservation", "performance", "rendering")


def _int_list(values: Any) -> list[int] | None:
    if not isinstance(values, list) or not values:
        return None
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return None
    return sorted(values)


def _report_profile(report: dict[str, Any]) -> str | None:
    profile = report.get("profile")
    if isinstance(profile, str):
        return profile
    needs = report.get("results", {}).get("needs")
    if isinstance(needs, dict) and isinstance(needs.get("profile"), str):
        return needs["profile"]
    return None


def report_cohort(report: dict[str, Any]) -> dict[str, Any]:
    """What a report says it measured: its seeds (sorted, with repeats),
    turns, worlds, requested simulation configuration and gate profile, each
    None when the report cannot tell.

    A report of a manifest-checked batch (``batch_manifest.status`` is
    ``verified``) carries them. Older reports give their seeds and final
    turns through the regression oracle's per-seed population rows and the
    needs result's profile, but not the simulation configuration.
    """
    worlds = _report_worlds(report)
    manifest = report.get("batch_manifest")
    if isinstance(manifest, dict) and manifest.get("status") == "verified":
        turns = manifest.get("turns")
        simulation = manifest.get("simulation")
        return {
            "source": "batch_manifest",
            "seeds": _int_list(manifest.get("seeds")),
            "turns": [turns] if isinstance(turns, int) and not isinstance(turns, bool) else None,
            "worlds": worlds,
            "simulation": simulation if isinstance(simulation, dict) else None,
            "profile": _report_profile(report),
        }
    regression = report.get("results", {}).get("regression")
    rows = regression.get("final_living_population_by_seed") if isinstance(regression, dict) else None
    seeds = turns = None
    if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
        seeds = _int_list([row.get("seed") for row in rows])
        final_turns = _int_list([row.get("turn") for row in rows])
        turns = sorted(set(final_turns)) if final_turns is not None else None
    return {
        "source": "per-seed results" if seeds is not None or turns is not None else "none",
        "seeds": seeds,
        "turns": turns,
        "worlds": worlds,
        "simulation": None,
        "profile": _report_profile(report),
    }


def _describe_seeds(seeds: list[int]) -> str:
    distinct = sorted(set(seeds))
    ranges: list[str] = []
    start = previous = distinct[0]
    for seed in distinct[1:] + [None]:
        if seed is not None and seed == previous + 1:
            previous = seed
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        if seed is not None:
            start = previous = seed
    shown = ", ".join(ranges[:4]) + (", ..." if len(ranges) > 4 else "")
    repeats = f", {len(seeds) - len(distinct)} repeated" if len(seeds) != len(distinct) else ""
    return f"{len(seeds)} run(s) of seeds {shown}{repeats}"


def _describe_field(field: str, baseline: Any, current: Any) -> str:
    if field == "seeds":
        return f"seeds: baseline {_describe_seeds(baseline)}, current {_describe_seeds(current)}"
    if field == "simulation":
        keys = sorted(set(baseline) | set(current))
        differing = [
            f"{key} {baseline.get(key)!r} vs {current.get(key)!r}" for key in keys if baseline.get(key) != current.get(key)
        ]
        return "simulation configuration: " + ", ".join(differing)
    return f"{field}: baseline {baseline} vs current {current}"


def compare_cohorts(baseline_report: dict[str, Any], current_report: dict[str, Any]) -> dict[str, Any]:
    """Cohort fields that differ between the reports (``mismatches``) and
    those one of them does not record (``unverified``)."""
    baseline = report_cohort(baseline_report)
    current = report_cohort(current_report)
    mismatches: list[dict[str, Any]] = []
    unverified: list[str] = []
    for field in ("seeds", "turns", "worlds", "simulation", "profile"):
        left, right = baseline[field], current[field]
        if left is None or right is None:
            unverified.append(field)
        elif field == "simulation":
            # A setting one manifest does not name (an argument added since)
            # was not requested: its CLI default, as None.
            if any(left.get(key) != right.get(key) for key in set(left) | set(right)):
                mismatches.append({"field": field, "description": _describe_field(field, left, right)})
        elif left != right:
            mismatches.append({"field": field, "description": _describe_field(field, left, right)})
    return {
        "comparable": not mismatches,
        "mismatches": mismatches,
        "unverified": unverified,
        "baseline_source": baseline["source"],
        "current_source": current["source"],
        "baseline": baseline,
        "current": current,
    }


# Gate rows that belong to an oracle's category without being an oracle.
_CATEGORY_SUB_ROWS = {"needs_binding": "needs", "needs_observational": "needs", "needs_ablation": "needs"}


def _category_cell(report: dict[str, Any], decision: dict[str, Any], category: str) -> str:
    """A category's status in one report: FAIL when a required oracle of it
    fails, PASS when every one of its oracles passes, and otherwise which
    passed and which did not (informational under the profile); NOT CHECKED
    or NOT PASSED when nothing in it passed."""
    if category == "execution":
        if report.get("status") == "ERROR":
            return "ERROR: " + str(report.get("reason") or "validation report error")
        manifest = report.get("batch_manifest")
        status = manifest.get("status") if isinstance(manifest, dict) else None
        if status == "verified":
            seeds = manifest.get("seeds")
            count = len(seeds) if isinstance(seeds, list) else "?"
            return f"PASS (batch manifest verified: {count} runs x {manifest.get('turns')} turns)"
        if status == "unchecked":
            return "NOT CHECKED (no batch manifest)"
        return "NOT CHECKED (report predates batch manifests)"
    members = EVIDENCE_CATEGORIES[category]
    oracles = [oracle for oracle in members if oracle in report.get("results", {})]
    if not oracles:
        return "not in report"

    def _in_category(item: dict[str, Any]) -> bool:
        oracle = str(item.get("oracle"))
        return _CATEGORY_SUB_ROWS.get(oracle, oracle) in members

    failed = [f"{item['oracle']} {item['status']}" for item in decision["required_failures"] if _in_category(item)]
    informational = [
        f"{item['oracle']} {item['status']}" for item in decision["informational_non_pass"] if _in_category(item)
    ]
    not_passed = {
        str(item.get("oracle")) for item in decision["required_failures"] + decision["informational_non_pass"]
    }
    passed = [oracle for oracle in oracles if oracle not in not_passed]
    if failed:
        cell = "FAIL: " + ", ".join(failed)
        if informational:
            cell += "; informational: " + ", ".join(informational)
        return cell
    if not informational:
        return "PASS"
    if not passed:
        return "NOT PASSED (informational only): " + ", ".join(informational)
    return "PASS: " + ", ".join(passed) + "; informational non-PASS: " + ", ".join(informational)


def evidence_by_category(
    baseline_report: dict[str, Any],
    current_report: dict[str, Any],
    baseline_decision: dict[str, Any],
    current_decision: dict[str, Any],
) -> list[dict[str, str]]:
    """Per evidence category, the oracles it covers and each report's status."""
    return [
        {
            "category": category,
            "oracles": ", ".join(oracles) if oracles else "batch and report",
            "baseline": _category_cell(baseline_report, baseline_decision, category),
            "current": _category_cell(current_report, current_decision, category),
        }
        for category, oracles in EVIDENCE_CATEGORIES.items()
    ]


def compare_validation_reports(
    profile: str,
    baseline_report: dict[str, Any],
    current_report: dict[str, Any],
    *,
    require_strict_regression: bool = False,
    fail_on_regression: bool = False,
    exploratory: bool = False,
) -> dict[str, Any]:
    """Compare two reports of the same cohort under ``profile``.

    Reports whose seeds, turns, worlds, simulation configuration or gate
    profile differ (``compare_cohorts``) are refused unless ``exploratory``;
    the result is then labelled exploratory. Fields one report does not
    record are listed as unverified.
    """
    _reject_nonfinite(baseline_report, "baseline_report")
    _reject_nonfinite(current_report, "current_report")
    cohort = compare_cohorts(baseline_report, current_report)
    if not cohort["comparable"] and not exploratory:
        worlds = [item for item in cohort["mismatches"] if item["field"] == "worlds"]
        prefix = (
            f"baseline and current reports measure different worlds: "
            f"{cohort['baseline']['worlds']} vs {cohort['current']['worlds']}; "
            if worlds else "baseline and current reports measure different cohorts: "
        )
        raise ValidationGateInputError(
            prefix
            + "; ".join(item["description"] for item in cohort["mismatches"] if item["field"] != "worlds" or not worlds)
            + f". Pass {EXPLORATORY_FLAG} for an exploratory comparison (not regression evidence)."
        )
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
    method_changes = _oracle_method_changes(baseline_report, current_report)
    method_changed = {item["oracle"] for item in method_changes}
    baseline_failures = baseline_decision["required_failures"]
    current_failures = current_decision["required_failures"]
    baseline_keys = {_failure_key(item) for item in baseline_failures}
    current_keys = {_failure_key(item) for item in current_failures}
    new_required_failures = [
        item for item in current_failures
        if _failure_key(item) not in baseline_keys and item.get("oracle") not in method_changed
    ]
    resolved_required_failures = [
        item for item in baseline_failures
        if _failure_key(item) not in current_keys and item.get("oracle") not in method_changed
    ]
    method_changed_required_failures = [
        item for item in current_failures if item.get("oracle") in method_changed
    ]

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
        "status": "REGRESSION" if regression_detected else "NO_REGRESSION",
        "status_meaning": STATUS_MEANING,
        "exploratory": not cohort["comparable"],
        "cohort": cohort,
        "evidence_by_category": evidence_by_category(
            baseline_report, current_report, baseline_decision, current_decision
        ),
        "unmeasured_categories": list(UNMEASURED_CATEGORIES),
        "baseline_decision": baseline_decision,
        "current_decision": current_decision,
        "new_required_failures": new_required_failures,
        "resolved_required_failures": resolved_required_failures,
        "oracle_method_changes": method_changes,
        "method_changed_required_failures": method_changed_required_failures,
        "rebaseline_required": bool(method_changes),
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


def _cohort_lines(cohort: dict[str, Any]) -> list[str]:
    current = cohort["current"]
    parts = []
    if current.get("seeds"):
        parts.append(_describe_seeds(current["seeds"]))
    if current.get("turns"):
        parts.append(f"{'/'.join(str(turn) for turn in current['turns'])} turns")
    lines = ["", "## Cohort", ""]
    if cohort["mismatches"]:
        lines.append("The reports measure different cohorts:")
        lines.append("")
        lines.extend(f"- {_markdown_cell(item['description'])}" for item in cohort["mismatches"])
    else:
        lines.append("Same cohort" + (f": {_markdown_cell(', '.join(parts))}" if parts else "") + ".")
    if cohort["unverified"]:
        lines.extend([
            "",
            "Not recorded by "
            + ("both reports" if cohort["baseline_source"] == cohort["current_source"] == "none" else "one report")
            + ", so not checked: "
            + ", ".join(cohort["unverified"])
            + f" (baseline from {cohort['baseline_source']}, current from {cohort['current_source']}).",
        ])
    return lines


def format_comparison_markdown(result: dict[str, Any]) -> str:
    status = "REGRESSION" if result["regression_detected"] else "NO REGRESSION"
    exploratory = bool(result.get("exploratory"))
    lines = [
        f"# Validation report comparison: {result['profile']}" + (" (EXPLORATORY)" if exploratory else ""),
        "",
        f"**Status:** {'EXPLORATORY, ' if exploratory else ''}{status}",
        f"**Exit code:** {result['exit_code']}",
        "",
    ]
    if exploratory:
        lines.extend([f"_{EXPLORATORY_MEANING}_", ""])
    lines.extend([f"_{STATUS_MEANING}_"])
    if result.get("cohort"):
        lines.extend(_cohort_lines(result["cohort"]))
    if result.get("evidence_by_category"):
        lines.extend([
            "",
            "## Evidence by category",
            "",
            "A pass in one category is not a pass in another.",
            "",
            "| Category | Oracles | Baseline | Current |",
            "| --- | --- | --- | --- |",
        ])
        for row in result["evidence_by_category"]:
            lines.append(
                "| " + " | ".join(_markdown_cell(row[key]) for key in ("category", "oracles", "baseline", "current")) + " |"
            )
        unmeasured = result.get("unmeasured_categories") or []
        if unmeasured:
            lines.extend(["", "Not measured by validation reports: " + ", ".join(unmeasured) + "."])
    lines.extend(["", "## Regression reasons", ""])
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
    if result.get("oracle_method_changes"):
        lines.extend([
            "",
            "## Oracle method changes",
            "",
            "Scored by different methods; their statuses are not compared. Re-score the "
            "baseline batch with the current oracle (re-baseline) to compare them.",
            "",
            "| Oracle | Baseline method | Baseline status | Current method | Current status |",
            "| --- | --- | --- | --- | --- |",
        ])
        for item in result["oracle_method_changes"]:
            fields = ("oracle", "baseline_method_version", "baseline_status", "current_method_version", "current_status")
            lines.append("| " + " | ".join(_markdown_cell(item.get(field, "")) for field in fields) + " |")
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
    parser.add_argument(EXPLORATORY_FLAG, action="store_true",
                        help="compare reports of different cohorts (seeds, turns, worlds, simulation "
                             "configuration or profile); the result is labelled exploratory")
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
            exploratory=args.exploratory,
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
    "EVIDENCE_CATEGORIES",
    "EXPLORATORY_FLAG",
    "UNMEASURED_CATEGORIES",
    "compare_cohorts",
    "compare_validation_reports",
    "evidence_by_category",
    "format_comparison_markdown",
    "main",
    "report_cohort",
]


if __name__ == "__main__":
    raise SystemExit(main())
