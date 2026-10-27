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
import sys
from pathlib import Path
from typing import Any

from chronicler.artifact_io import (
    ArtifactIOError,
    atomic_write_json,
    atomic_write_text,
    strict_json_dumps,
    strict_json_loads,
)

REQUIRED_ORACLES_BY_PROFILE = {
    "subset": ["community", "needs", "cohort"],
    "full": ["community", "needs", "era", "cohort", "artifacts", "arcs", "regression"],
    "determinism-off": ["determinism"],
    "determinism-hybrid": ["determinism"],
}

PROFILE_CHOICES = tuple(REQUIRED_ORACLES_BY_PROFILE)

# Needs oracle methods 3 and 4 (docs/integration/needs-followups.md): the binding
# component decides PASS only in these profiles. A subset has about 200
# informative binding pairs and its bound sits within one or two standard
# errors of zero, so elsewhere it is reported as informational.
NEEDS_BINDING_REQUIRED_PROFILES = ("full",)
_NEEDS_POOLED_CRITERIA = frozenset({"net_concordance_lower_bound", "seed_fraction"})

# Causal oracles (docs/integration/ablation-oracles.md): needs method 7 and
# cohort method 4 each hold an observational component (methods 6 and 3, as
# scored before) and an ablation component (the gate's forked arms). Until
# `main` passes the ablations they are computed and reported wherever their
# arms ran, labelled CAUSAL_LABEL_REPORTED, and the observational components
# decide, as before. ``--require-causal-oracles`` (chronicler.validate, this
# gate, the gate runner), or this constant, makes the ablations decide.
CAUSAL_ORACLES_REQUIRED = False
CAUSAL_ORACLES_FLAG = "--require-causal-oracles"
CAUSAL_LABEL_REPORTED = "causal evidence (not yet required)"
CAUSAL_LABEL_REQUIRED = "causal evidence (required)"
# Cohort method 3 passes every synthetic world, reversed ones included
# (oracle-followups.md): its PASS is no evidence.
COHORT_OBSERVATIONAL_NOTE = "non-discriminating: passes synthetic null and reversed worlds"

# Needs oracle method 7 with causal oracles required: which of its components
# decides PASS. The full profile's ablation arms fork every seed four
# (template) or two (procedural) times and measure each pairing's causal
# effect; the observational component (method 6) passes worlds whose needs
# say nothing but rise with age and terms-zeroed subsets, so it is reported
# there. A subset forks once per seed: too few agents below the safety
# threshold to measure that pairing, so its observational verdict decides
# and the ablation is reported. Outside a profile both decide.
NEEDS_COMPONENTS_REQUIRED = {
    "full": ("ablation",),
    "subset": ("observational",),
}
NEEDS_COMPONENTS = ("observational", "ablation")
COHORT_COMPONENTS = ("observational", "ablation")


def causal_label(require_causal: bool) -> str:
    return CAUSAL_LABEL_REQUIRED if require_causal else CAUSAL_LABEL_REPORTED


def causal_oracles_required(report: dict[str, Any] | None = None, require_causal: bool | None = None) -> bool:
    """Whether the ablation components decide: ``require_causal`` when given,
    else what ``report`` records (``causal_oracles_required``), else
    ``CAUSAL_ORACLES_REQUIRED``."""
    if require_causal is not None:
        return bool(require_causal)
    recorded = report.get("causal_oracles_required") if isinstance(report, dict) else None
    if isinstance(recorded, bool):
        return recorded
    return CAUSAL_ORACLES_REQUIRED


def needs_components_required(profile: str | None, require_causal: bool = CAUSAL_ORACLES_REQUIRED) -> tuple[str, ...]:
    """The method 7 components that decide the needs status under ``profile``:
    the observational one unless causal oracles are required."""
    if not require_causal:
        return ("observational",)
    if profile is None:
        return NEEDS_COMPONENTS
    return NEEDS_COMPONENTS_REQUIRED.get(profile, NEEDS_COMPONENTS)


def cohort_components_required(require_causal: bool = CAUSAL_ORACLES_REQUIRED) -> tuple[str, ...]:
    """The method 4 component that decides the cohort status: method 3's
    observational verdict unless causal oracles are required, then the
    kin-roots ablation (in every profile)."""
    return ("ablation",) if require_causal else ("observational",)


def combined_status(statuses: dict[str, str], required: tuple[str, ...]) -> str:
    """PASS when every required component passes; a single required
    component's own status otherwise (FAIL, NOT_RUN, SKIP, ERROR), FAIL when
    several are required."""
    values = [str(statuses.get(name) or "MISSING") for name in required]
    if all(value == "PASS" for value in values):
        return "PASS"
    return values[0] if len(values) == 1 else "FAIL"


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


def _oracle_item(
    report: dict[str, Any], oracle: str, status: str | None = None, require_causal: bool | None = None,
) -> dict[str, Any]:
    result = report.get("results", {}).get(oracle)
    item: dict[str, Any] = {"oracle": oracle, "status": status or _oracle_status(report, oracle)}
    if isinstance(result, dict):
        reason = result.get("reason")
        if oracle == "cohort" and _is_cohort_with_components(result):
            reason = _cohort_status(result, causal_oracles_required(report, require_causal))[1]
        if reason:
            item["reason"] = str(reason)
        adjudication = result.get("regression_adjudication") or result.get("creation_rate_adjudication")
        if adjudication:
            item["adjudication"] = str(adjudication)
    return item


def _is_version(result: dict[str, Any], minimum: int) -> bool:
    version = result.get("method_version")
    return isinstance(version, int) and not isinstance(version, bool) and version >= minimum


def _ablation_detail(ablation: dict[str, Any]) -> str:
    """The reason an ablation component did not pass (its failed pairings)."""
    if ablation.get("reason"):
        return str(ablation["reason"])
    failed = ablation.get("failed_pairings") or []
    return "pairings " + ", ".join(str(name) for name in failed) if failed else ""


def _needs_status_for_profile(
    result: dict[str, Any], profile: str, require_causal: bool = CAUSAL_ORACLES_REQUIRED,
) -> tuple[str, list[dict[str, Any]]]:
    """Needs status under ``profile`` and informational items for the
    components that fail but do not decide there.

    A method 7 result decides by the components ``needs_components_required``
    names for ``profile`` and ``require_causal``, whatever it was scored for:
    its observational component by the method 3-6 rule below, its ablation
    component by its own status. A method 3 or later result counts its
    binding component only in ``NEEDS_BINDING_REQUIRED_PROFILES``
    (``binding_required`` records the profile it was scored for). Other
    results keep their status.
    """
    if (
        _is_version(result, 7) and isinstance(result.get("ablation"), dict)
        and result.get("observational_status") in ("PASS", "FAIL")
    ):
        observational = dict(result)
        observational["status"] = result.get("observational_status")
        observational_status, items = _needs_observational_status(observational, profile)
        ablation = result["ablation"]
        statuses = {"observational": observational_status, "ablation": str(ablation.get("status") or "MISSING")}
        required = needs_components_required(profile, require_causal)
        for name in NEEDS_COMPONENTS:
            if name in required or statuses[name] == "PASS":
                continue
            if name == "ablation":
                if not require_causal:
                    reason = f"{CAUSAL_LABEL_REPORTED}: ablation component {statuses[name]}"
                else:
                    reason = (
                        f"ablation component {statuses[name]}; informational in {profile}, required in "
                        + ", ".join(p for p, names in NEEDS_COMPONENTS_REQUIRED.items() if name in names)
                    )
                detail = _ablation_detail(ablation)
                if detail:
                    reason += f" ({detail})"
            else:
                reason = f"observational component {statuses[name]}; informational in {profile} " \
                         f"while causal oracles are required"
            items.append({"oracle": f"needs_{name}", "status": statuses[name], "reason": reason})
        return combined_status(statuses, required), items
    status, item = _needs_observational_status(result, profile)
    return status, item


def _needs_failure_reason(
    result: dict[str, Any], profile: str, require_causal: bool = CAUSAL_ORACLES_REQUIRED,
) -> str | None:
    """Which required method 7 components fail under ``profile`` (None before method 7)."""
    ablation = result.get("ablation")
    if not _is_version(result, 7) or not isinstance(ablation, dict):
        return None
    parts = []
    required = needs_components_required(profile, require_causal)
    if "observational" in required:
        observational = dict(result)
        observational["status"] = result.get("observational_status")
        if _needs_observational_status(observational, profile)[0] != "PASS":
            parts.append("observational component FAIL")
    if "ablation" in required and ablation.get("status") != "PASS":
        detail = _ablation_detail(ablation)
        parts.append(f"ablation component {ablation.get('status')}" + (f" ({detail})" if detail else ""))
    return "; ".join(parts) or None


def _is_cohort_with_components(result: Any) -> bool:
    return (
        isinstance(result, dict) and _is_version(result, 4)
        and isinstance(result.get("ablation"), dict) and "observational_status" in result
    )


def _cohort_status(
    result: dict[str, Any], require_causal: bool = CAUSAL_ORACLES_REQUIRED,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Cohort status, its reason and informational items.

    A method 4 result with components decides by
    ``cohort_components_required(require_causal)``: method 3's observational
    verdict (``COHORT_OBSERVATIONAL_NOTE``) or the kin-roots ablation; the
    other component is reported when it does not pass. Other results keep
    their status and reason.
    """
    if not _is_cohort_with_components(result):
        reason = result.get("reason")
        return str(result.get("status") or "MISSING"), str(reason) if reason else None, []
    ablation = result["ablation"]
    statuses = {
        "observational": str(result.get("observational_status") or "MISSING"),
        "ablation": str(ablation.get("status") or "MISSING"),
    }
    required = cohort_components_required(require_causal)
    status = combined_status(statuses, required)
    items = []
    if require_causal:
        reason = _ablation_detail(ablation) if status != "PASS" else None
        if statuses["observational"] != "PASS":
            items.append({"oracle": "cohort_observational", "status": statuses["observational"],
                          "reason": f"method 3, {COHORT_OBSERVATIONAL_NOTE}; informational while causal "
                                    f"oracles are required"})
    else:
        observational_reason = result.get("observational_reason")
        reason = f"method 3 (observational), {COHORT_OBSERVATIONAL_NOTE}"
        if status != "PASS" and observational_reason:
            reason = f"{observational_reason}; {reason}"
        if statuses["ablation"] != "PASS":
            detail = _ablation_detail(ablation)
            items.append({"oracle": "cohort_ablation", "status": statuses["ablation"],
                          "reason": f"{CAUSAL_LABEL_REPORTED}: kin-roots ablation {statuses['ablation']}"
                                    + (f" ({detail})" if detail else "")})
    community = _community_component(result)
    if community is not None and community.get("status") != "PASS":
        detail = _ablation_detail(community)
        items.append({"oracle": "cohort_community_ablation", "status": str(community.get("status") or "MISSING"),
                      "reason": "reported, never deciding: community-anchor ablation "
                                f"{community.get('status')}" + (f" ({detail})" if detail else "")})
    return status, reason or None, items


def _community_component(result: dict[str, Any]) -> dict[str, Any] | None:
    """Cohort method 5's community component when its arm ran (None otherwise)."""
    community = result.get("community_ablation") if isinstance(result, dict) else None
    if not isinstance(community, dict) or community.get("status") == "NOT_RUN":
        return None
    return community


def _needs_observational_status(result: dict[str, Any], profile: str) -> tuple[str, list[dict[str, Any]]]:
    """The method 2-6 rule (the observational component of method 7)."""
    status = str(result.get("status") or "MISSING")
    binding = result.get("binding")
    version = result.get("method_version")
    if (
        status not in ("PASS", "FAIL")
        or not isinstance(binding, dict)
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 3
    ):
        return status, []
    failed = set(result.get("failed_criteria") or ()) | set(result.get("informational_failed_criteria") or ())
    pooled_ok = not (failed & _NEEDS_POOLED_CRITERIA)
    lower_bound = binding.get("net_concordance_lower_bound")
    binding_ok = (
        isinstance(lower_bound, (int, float)) and not isinstance(lower_bound, bool) and lower_bound > 0
    )
    if profile in NEEDS_BINDING_REQUIRED_PROFILES:
        return ("PASS" if pooled_ok and binding_ok else "FAIL"), []
    informational = []
    if not binding_ok:
        informational.append({
            "oracle": "needs_binding",
            "status": "FAIL",
            "reason": (
                f"binding lower bound {lower_bound}; informational in {profile}, "
                f"required in {', '.join(NEEDS_BINDING_REQUIRED_PROFILES)}"
            ),
        })
    return ("PASS" if pooled_ok else "FAIL"), informational


def _strict_regression_failure(report: dict[str, Any]) -> dict[str, Any] | None:
    result = report.get("results", {}).get("regression")
    if not isinstance(result, dict):
        return None
    if result.get("status") != "PASS":
        return None
    if result.get("strict_regression_ok") is True or result.get("regression_adjudication") == "strict":
        return None
    adjudication = str(result.get("regression_adjudication") or "unknown")
    failure: dict[str, Any] = {
        "oracle": "regression",
        "status": "NON_STRICT",
        "reason": f"strict regression required but adjudication={adjudication}",
        "adjudication": adjudication,
    }
    for key in (
        "strict_regression_failed_checks",
        "calibrated_floor_failed_checks",
        "calibrated_floor_relaxed_checks",
    ):
        if key in result:
            failure[key] = result[key]
    return failure


def adjudicate_validation_report(
    profile: str,
    report: dict[str, Any],
    *,
    require_strict_regression: bool = False,
    require_causal_oracles: bool | None = None,
) -> dict[str, Any]:
    """Apply profile-specific gate semantics to a validation JSON report
    (``require_causal_oracles``: whether the ablation components decide;
    None reads the report's ``causal_oracles_required``)."""
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

    require_causal = causal_oracles_required(report, require_causal_oracles)
    required_failures: list[dict[str, Any]] = []
    informational_non_pass: list[dict[str, Any]] = []
    if report.get("status") == "ERROR":
        required_failures.append({
            "oracle": "validation_report",
            "status": "ERROR",
            "reason": str(report.get("reason") or "report_status_error"),
        })
    for oracle in all_oracles:
        status = _oracle_status(report, oracle)
        result = report["results"].get(oracle)
        component_items: list[dict[str, Any]] = []
        if oracle == "needs" and isinstance(result, dict):
            status, component_items = _needs_status_for_profile(result, profile, require_causal)
        if oracle == "cohort" and isinstance(result, dict):
            status, _reason, component_items = _cohort_status(result, require_causal)
        item = _oracle_item(report, oracle, status, require_causal)
        if oracle == "needs" and isinstance(result, dict) and status == "FAIL" and "reason" not in item:
            reason = _needs_failure_reason(result, profile, require_causal)
            if reason:
                item["reason"] = reason
        if oracle in required_oracles:
            if status != "PASS":
                required_failures.append(item)
        elif status != "PASS":
            informational_non_pass.append(item)
        informational_non_pass.extend(component_items)

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
        "causal_oracles_required": require_causal,
        "causal_evidence": causal_evidence(report, profile, require_causal),
    }


def _ratio_text(stats: Any) -> str:
    if not isinstance(stats, dict) or stats.get("rate_ratio") is None:
        return "n/a"
    text = f"{stats['rate_ratio']:.3f}"
    interval = stats.get("interval")
    if isinstance(interval, list) and len(interval) == 2 and None not in interval:
        text += f" [{interval[0]:.3f}, {interval[1]:.3f}]"
    return text


def causal_evidence(report: dict[str, Any], profile: str, require_causal: bool) -> list[dict[str, Any]]:
    """One row per ablation component in ``report`` (needs method 7, cohort
    method 4): its status, whether it decides here, its label and its
    effects (rate ratios with 95% intervals)."""
    rows: list[dict[str, Any]] = []
    results = report.get("results") if isinstance(report.get("results"), dict) else {}
    needs = results.get("needs")
    if isinstance(needs, dict) and _is_version(needs, 7) and isinstance(needs.get("ablation"), dict):
        ablation = needs["ablation"]
        pairings = ablation.get("by_pairing") if isinstance(ablation.get("by_pairing"), dict) else {}
        parts = []
        for name, stats in pairings.items():
            if not isinstance(stats, dict):
                continue
            verdict = stats.get("status", "") if stats.get("required", True) else "reported"
            parts.append(f"{name} {_ratio_text(stats)} {verdict}".strip())
        rows.append({
            "oracle": "needs", "component": "ablation (need terms)",
            "status": str(ablation.get("status") or "MISSING"),
            "decides": "ablation" in needs_components_required(profile, require_causal),
            "label": causal_label(require_causal), "detail": "; ".join(parts) or _ablation_detail(ablation),
        })
    cohort = results.get("cohort")
    if _is_cohort_with_components(cohort):
        ablation = cohort["ablation"]
        migration = ablation.get("members_migration")
        detail = (f"members' migration {_ratio_text(migration)}" if isinstance(migration, dict)
                  else _ablation_detail(ablation))
        rows.append({
            "oracle": "cohort", "component": "ablation (kin roots)",
            "status": str(ablation.get("status") or "MISSING"),
            "decides": "ablation" in cohort_components_required(require_causal),
            "label": causal_label(require_causal), "detail": detail,
        })
        community = _community_component(cohort)
        if community is not None:
            migration = community.get("members_migration")
            by_cohort = community.get("migration_by_cohort")
            by_cohort = by_cohort if isinstance(by_cohort, dict) else {}
            parts = [f"members' migration {_ratio_text(migration)}"] if isinstance(migration, dict) else []
            for name, label in (("full_ties", "four ties"), ("no_ties", "no ties")):
                if isinstance(by_cohort.get(name), dict):
                    parts.append(f"{label} {_ratio_text(by_cohort[name])}")
            rows.append({
                "oracle": "cohort_community", "component": "ablation (community anchor)",
                "status": str(community.get("status") or "MISSING"),
                "decides": False,
                "label": "reported", "detail": "; ".join(parts) or _ablation_detail(community),
            })
    return rows


def _causal_heading(require_causal: bool) -> str:
    label = causal_label(require_causal)
    return label[0].upper() + label[1:]


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
    evidence = decision.get("causal_evidence") or []
    if evidence:
        lines.append(
            f"{_causal_heading(bool(decision.get('causal_oracles_required')))}: "
            + ", ".join(f"{row['oracle']} ablation={row['status']}" for row in evidence)
        )
    return "\n".join(lines)


def _decision_exit_code(decision: dict[str, Any]) -> int:
    return 0 if decision["ok"] else 2


def _oracle_statuses(report: dict[str, Any], require_causal: bool | None = None) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    results = report.get("results", {})
    if not isinstance(results, dict):
        return statuses
    for oracle in sorted(results):
        item = _oracle_item(report, oracle, require_causal=require_causal)
        item.pop("oracle", None)
        statuses[oracle] = item
    return statuses


def batch_manifest_summary(report: dict[str, Any]) -> str:
    """One line on whether the report's batch was checked against its manifest."""
    manifest = report.get("batch_manifest")
    if not isinstance(manifest, dict):
        return "not recorded (the report predates batch manifests; its runs were not checked)"
    status = manifest.get("status")
    if status == "verified":
        seeds = manifest.get("seeds")
        count = len(seeds) if isinstance(seeds, list) else "?"
        return f"verified ({count} runs x {manifest.get('turns')} turns)"
    return f"{status} ({manifest.get('reason') or 'runs not checked'})"


def build_gate_decision_payload(
    decision: dict[str, Any],
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Build a stable machine-readable gate decision artifact."""
    oracle_statuses = _oracle_statuses(report, decision.get("causal_oracles_required"))
    for oracle in decision["required_oracles"]:
        oracle_statuses.setdefault(oracle, {"status": "MISSING"})
    return {
        "schema_version": 1,
        "profile": decision["profile"],
        "ok": decision["ok"],
        "exit_code": _decision_exit_code(decision),
        "report_path": str(report_path) if report_path is not None else None,
        "batch_dir": report.get("batch_dir"),
        "required_oracles": decision["required_oracles"],
        "required_failures": decision["required_failures"],
        "informational_non_pass": decision["informational_non_pass"],
        "oracle_statuses": oracle_statuses,
        "require_strict_regression": decision.get("require_strict_regression", False),
        "causal_oracles_required": decision.get("causal_oracles_required", False),
        "causal_evidence": decision.get("causal_evidence", []),
        "batch_manifest": batch_manifest_summary(report),
    }


def _markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
        .replace("|", "\\|")
    )


def _markdown_table(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["_None._"]
    rows = ["| Oracle | Status | Adjudication | Reason |", "| --- | --- | --- | --- |"]
    for item in items:
        rows.append(
            "| "
            + " | ".join(
                _markdown_cell(item.get(key, ""))
                for key in ("oracle", "status", "adjudication", "reason")
            )
            + " |"
        )
    return rows


def format_gate_markdown(
    decision: dict[str, Any],
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
) -> str:
    """Format a concise Markdown summary suitable for CI job summaries."""
    status = "PASS" if decision["ok"] else "FAIL"
    lines = [
        f"# Validation gate: {decision['profile']}",
        "",
        f"**Status:** {status}",
        f"**Exit code:** {_decision_exit_code(decision)}",
    ]
    if report_path is not None:
        lines.append(f"**Report:** `{report_path}`")
    if report.get("batch_dir"):
        lines.append(f"**Batch:** `{report['batch_dir']}`")
    lines.append(f"**Batch manifest:** {_markdown_cell(batch_manifest_summary(report))}")
    lines.extend(["", "## Required failures", ""])
    lines.extend(_markdown_table(decision["required_failures"]))
    lines.extend(["", "## Informational non-PASS", ""])
    lines.extend(_markdown_table(decision["informational_non_pass"]))
    require_causal = bool(decision.get("causal_oracles_required"))
    evidence = decision.get("causal_evidence") or []
    if evidence:
        lines.extend(["", f"## {_causal_heading(require_causal)}", ""])
        if not require_causal:
            lines.extend([
                "Ablation components (docs/integration/ablation-oracles.md), computed and reported; the "
                f"observational components decide until `{CAUSAL_ORACLES_FLAG}`.",
                "",
            ])
        lines.extend([
            "| Oracle | Component | Status | Decides | Effect (rate ratio, 95% interval) |",
            "| --- | --- | --- | --- | --- |",
        ])
        for row in evidence:
            lines.append("| " + " | ".join(_markdown_cell(value) for value in (
                row["oracle"], row["component"], row["status"], "yes" if row["decides"] else "no", row["detail"],
            )) + " |")
    lines.extend(["", "## Oracle statuses", "", "| Oracle | Status | Adjudication | Reason |", "| --- | --- | --- | --- |"])
    for oracle, item in _oracle_statuses(report, require_causal).items():
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    oracle,
                    item.get("status", ""),
                    item.get("adjudication", ""),
                    item.get("reason", ""),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


# Backwards-compatible private name used by the historical validation runner tests.
_format_gate_failure = format_gate_failure


def load_validation_report(report_path: Path) -> dict[str, Any]:
    try:
        report = strict_json_loads(report_path.read_text(encoding="utf-8"), label="report JSON")
    except FileNotFoundError as exc:
        raise ValidationGateInputError(f"report path does not exist: {report_path}") from exc
    except IsADirectoryError as exc:
        raise ValidationGateInputError(f"could not read report: {report_path} is a directory") from exc
    except UnicodeDecodeError as exc:
        raise ValidationGateInputError(f"could not decode report as UTF-8: {exc}") from exc
    except OSError as exc:
        raise ValidationGateInputError(f"could not read report: {exc}") from exc
    except ArtifactIOError as exc:
        raise ValidationGateInputError(f"invalid report JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise ValidationGateInputError("report JSON must be an object")
    return report


def _dump_json(payload: dict[str, Any]) -> None:
    try:
        sys.stdout.write(strict_json_dumps(payload))
    except ArtifactIOError as exc:  # pragma: no cover - defensive fallback for malformed error payloads
        sys.stdout.write('{"status":"ERROR","reason":"could not serialize JSON output"}\n')


def _error_payload(profile: str | None, report_path: Path | None, reason: str) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "profile": profile,
        "report_path": str(report_path) if report_path is not None else None,
        "reason": reason,
    }


def _write_text_output(path: Path, content: str, *, label: str) -> None:
    try:
        atomic_write_text(path, content)
    except ArtifactIOError as exc:
        raise ValidationGateInputError(f"could not write {label}: {exc}") from exc


def _paths_collide(left: Path, right: Path) -> bool:
    if left.resolve() == right.resolve():
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _reject_colliding_output_paths(
    report_path: Path,
    decision_path: Path | None,
    summary_path: Path | None,
) -> None:
    if decision_path is not None:
        if _paths_collide(decision_path, report_path):
            raise ValidationGateInputError("decision-output must be different from report")
    if summary_path is not None:
        if _paths_collide(summary_path, report_path):
            raise ValidationGateInputError("summary-output must be different from report")
    if decision_path is not None and summary_path is not None:
        if _paths_collide(decision_path, summary_path):
            raise ValidationGateInputError("decision-output and summary-output must be different paths")


def main(argv: list[str] | None = None) -> int:
    parser = _ValidationGateArgumentParser(description="Gate an existing Chronicler validation report")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--require-strict-regression",
        action="store_true",
        help="For full profile reports, fail calibrated-floor regression passes.",
    )
    parser.add_argument(
        CAUSAL_ORACLES_FLAG,
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Let the ablation components (needs method 7, cohort method 4) decide (default: what the "
             "report records, else off; docs/integration/ablation-oracles.md).",
    )
    parser.add_argument("--text", action="store_true", help="Print a terminal summary instead of JSON")
    parser.add_argument(
        "--decision-output",
        type=Path,
        help="Optional path for the machine-readable gate decision JSON artifact.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional path for the Markdown gate summary artifact.",
    )
    args = None
    try:
        args = parser.parse_args(argv)
        report = load_validation_report(args.report)
        decision = adjudicate_validation_report(
            args.profile,
            report,
            require_strict_regression=args.require_strict_regression,
            require_causal_oracles=args.require_causal_oracles,
        )
    except ValidationGateInputError as exc:
        _dump_json(_error_payload(
            getattr(args, "profile", None),
            getattr(args, "report", None),
            str(exc),
        ))
        return 1

    try:
        _reject_colliding_output_paths(args.report, args.decision_output, args.summary_output)
        payload = build_gate_decision_payload(decision, report, report_path=args.report)
        if args.decision_output is not None:
            try:
                atomic_write_json(args.decision_output, payload)
            except ArtifactIOError as exc:
                raise ValidationGateInputError(f"could not write decision-output: {exc}") from exc
        if args.summary_output is not None:
            _write_text_output(
                args.summary_output,
                format_gate_markdown(decision, report, report_path=args.report),
                label="summary-output",
            )
    except ValidationGateInputError as exc:
        _dump_json(_error_payload(args.profile, args.report, str(exc)))
        return 1

    if args.text:
        sys.stdout.write(format_gate_summary(decision) + "\n")
    else:
        _dump_json(payload)
    return _decision_exit_code(decision)


__all__ = [
    "REQUIRED_ORACLES_BY_PROFILE",
    "PROFILE_CHOICES",
    "NEEDS_BINDING_REQUIRED_PROFILES",
    "NEEDS_COMPONENTS",
    "NEEDS_COMPONENTS_REQUIRED",
    "COHORT_COMPONENTS",
    "CAUSAL_ORACLES_REQUIRED",
    "CAUSAL_ORACLES_FLAG",
    "CAUSAL_LABEL_REPORTED",
    "CAUSAL_LABEL_REQUIRED",
    "COHORT_OBSERVATIONAL_NOTE",
    "causal_evidence",
    "causal_label",
    "causal_oracles_required",
    "cohort_components_required",
    "combined_status",
    "needs_components_required",
    "ValidationGateInputError",
    "adjudicate_validation_report",
    "batch_manifest_summary",
    "build_gate_decision_payload",
    "format_gate_failure",
    "format_gate_markdown",
    "format_gate_summary",
    "load_validation_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
