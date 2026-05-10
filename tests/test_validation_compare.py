"""Tests for validation report comparison tooling."""
from __future__ import annotations

import json
import os


def _report(**statuses):
    names = [
        "community",
        "needs",
        "cohort",
        "era",
        "artifacts",
        "arcs",
        "regression",
        "determinism",
    ]
    return {"results": {name: {"status": statuses.get(name, "PASS")} for name in names}}


def _diagnostic(value, strict_delta, calibrated_delta):
    return {
        "value": value,
        "strict_min": 0.45,
        "calibrated_min": 0.40,
        "max": 0.65,
        "strict_ok": strict_delta >= 0,
        "calibrated_ok": calibrated_delta >= 0,
        "strict_min_delta": strict_delta,
        "calibrated_min_delta": calibrated_delta,
        "max_delta": round(0.65 - value, 6),
    }


def test_compare_detects_new_required_failures_and_resolved_failures():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(needs="FAIL", determinism="SKIP")
    baseline["results"]["needs"]["reason"] = "missing sidecars"
    current = _report(needs="SKIP", determinism="SKIP")
    current["results"]["needs"]["reason"] = "empty sidecars"

    result = compare_validation_reports("subset", baseline, current)

    assert result["profile"] == "subset"
    assert result["baseline_decision"]["ok"] is False
    assert result["current_decision"]["ok"] is False
    assert result["new_required_failures"] == [
        {"oracle": "needs", "status": "SKIP", "reason": "empty sidecars"}
    ]
    assert result["resolved_required_failures"] == [
        {"oracle": "needs", "status": "FAIL", "reason": "missing sidecars"}
    ]
    assert result["oracle_status_changes"] == [
        {
            "oracle": "needs",
            "baseline_status": "FAIL",
            "current_status": "SKIP",
            "baseline_reason": "missing sidecars",
            "current_reason": "empty sidecars",
        }
    ]
    assert result["regression_detected"] is True
    assert "new_required_failures" in result["regression_reasons"]


def test_compare_detects_strict_regression_downgrade_and_metric_deltas():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
        "strict_regression_failed_checks": [],
        "calibrated_floor_relaxed_checks": [],
        "regression_floor_diagnostics": {
            "latest_satisfaction_mean": _diagnostic(0.46, 0.01, 0.06),
        },
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
        "strict_regression_failed_checks": ["latest_satisfaction_mean"],
        "calibrated_floor_relaxed_checks": ["latest_satisfaction_mean"],
        "calibrated_floor_failed_checks": [],
        "regression_floor_diagnostics": {
            "latest_satisfaction_mean": _diagnostic(0.43, -0.02, 0.03),
        },
    }

    result = compare_validation_reports("full", baseline, current)

    assert result["regression_adjudication_change"] == {
        "baseline": "strict",
        "current": "calibrated_floor",
    }
    assert result["strict_regression_downgrade"] is True
    assert result["strict_regression_failed_checks_added"] == ["latest_satisfaction_mean"]
    assert result["calibrated_floor_relaxed_checks_added"] == ["latest_satisfaction_mean"]
    assert result["metric_deltas"]["regression_floor_diagnostics.latest_satisfaction_mean.value"] == {
        "baseline": 0.46,
        "current": 0.43,
        "delta": -0.03,
    }
    assert result["metric_deltas"]["regression_floor_diagnostics.latest_satisfaction_mean.strict_min_delta"]["delta"] == -0.03
    assert result["regression_detected"] is True
    assert "strict_regression_downgrade" in result["regression_reasons"]


def test_compare_detects_missing_strict_evidence_as_downgrade():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
    }
    current = _report()
    current["results"]["regression"] = {"status": "PASS"}

    result = compare_validation_reports("full", baseline, current, fail_on_regression=True)

    assert result["strict_regression_downgrade"] is True
    assert result["regression_detected"] is True
    assert "strict_regression_downgrade" in result["regression_reasons"]
    assert result["exit_code"] == 2


def test_optional_regression_diagnostics_do_not_fail_subset_comparison():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(determinism="SKIP")
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
        "strict_regression_failed_checks": [],
    }
    current = _report(determinism="SKIP")
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
        "strict_regression_failed_checks": ["latest_satisfaction_mean"],
    }

    result = compare_validation_reports("subset", baseline, current, fail_on_regression=True)

    assert result["strict_regression_downgrade"] is True
    assert result["strict_regression_failed_checks_added"] == ["latest_satisfaction_mean"]
    assert result["regression_adjudication_change"] == {
        "baseline": "strict",
        "current": "calibrated_floor",
    }
    assert result["regression_detected"] is False
    assert result["regression_reasons"] == []
    assert result["exit_code"] == 0


def test_optional_regression_diagnostics_do_not_fail_determinism_comparison():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(determinism="PASS")
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
    }
    current = _report(determinism="PASS")
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
        "strict_regression_failed_checks": ["migration_rate_per_agent_turn"],
    }

    result = compare_validation_reports("determinism-off", baseline, current, fail_on_regression=True)

    assert result["regression_detected"] is False
    assert result["regression_reasons"] == []
    assert result["strict_regression_downgrade"] is True
    assert result["strict_regression_failed_checks_added"] == ["migration_rate_per_agent_turn"]
    assert result["exit_code"] == 0


def test_require_strict_regression_still_fails_full_profile_comparison():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(determinism="SKIP")
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
    }
    current = _report(determinism="SKIP")
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
    }

    result = compare_validation_reports(
        "full",
        baseline,
        current,
        require_strict_regression=True,
        fail_on_regression=True,
    )

    assert result["current_decision"]["ok"] is False
    assert result["new_required_failures"] == [
        {
            "oracle": "regression",
            "status": "NON_STRICT",
            "reason": "strict regression required but adjudication=calibrated_floor",
            "adjudication": "calibrated_floor",
        }
    ]
    assert "new_required_failures" in result["regression_reasons"]
    assert result["exit_code"] == 2


def test_compare_cli_writes_json_and_markdown_outputs(tmp_path, capsys):
    from chronicler import validation_compare

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(_report(determinism="SKIP")), encoding="utf-8")
    current = _report(needs="FAIL", determinism="SKIP")
    current["results"]["needs"]["reason"] = "broken"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    decision_path = tmp_path / "compare.json"
    summary_path = tmp_path / "compare.md"

    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
        "--decision-output",
        str(decision_path),
        "--summary-output",
        str(summary_path),
    ]) == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert stdout_payload == decision_payload
    assert decision_payload["regression_detected"] is True
    assert decision_payload["exit_code"] == 0
    summary = summary_path.read_text(encoding="utf-8")
    assert "# Validation report comparison: subset" in summary
    assert "new_required_failures" in summary
    assert "needs" in summary

    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
        "--fail-on-regression",
    ]) == 2
    assert json.loads(capsys.readouterr().out)["exit_code"] == 2


def test_compare_cli_rejects_input_path_collisions(tmp_path, capsys):
    from chronicler import validation_compare

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(_report()), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(baseline_path),
    ]) == 1
    assert "baseline-report and current-report" in json.loads(capsys.readouterr().out)["reason"]

    symlink_path = tmp_path / "current-symlink.json"
    symlink_path.symlink_to(baseline_path)
    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(symlink_path),
    ]) == 1
    assert "baseline-report and current-report" in json.loads(capsys.readouterr().out)["reason"]

    hardlink_path = tmp_path / "current-hardlink.json"
    try:
        os.link(baseline_path, hardlink_path)
    except OSError as exc:  # pragma: no cover - platform/filesystem guard
        import pytest

        pytest.skip(f"hardlinks unavailable: {exc}")
    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(hardlink_path),
    ]) == 1
    assert "baseline-report and current-report" in json.loads(capsys.readouterr().out)["reason"]


def test_compare_markdown_escapes_html_pipes_and_newlines():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    baseline = _report()
    current = _report(needs="FAIL")
    current["results"]["needs"]["reason"] = "<details open>|boom\nline"
    result = compare_validation_reports("subset", baseline, current)

    markdown = format_comparison_markdown(result)

    assert "&lt;details open&gt;" in markdown
    assert "<details open>" not in markdown
    assert "\\|boom" in markdown
    assert "<br>line" in markdown


def test_compare_cli_rejects_nonfinite_metric_deltas(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": 1.0}},
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": float("nan")}},
    }
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "full",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "non-finite numeric diagnostic" in payload["reason"]


def test_compare_markdown_escapes_adjudication_values():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict`",
        "strict_regression_ok": True,
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "`\n<details open>INJECT",
        "strict_regression_ok": False,
    }
    result = compare_validation_reports("full", baseline, current)

    markdown = format_comparison_markdown(result)

    assert "&lt;details open&gt;INJECT" in markdown
    assert "<details open>INJECT" not in markdown
    assert "baseline: `strict``" not in markdown


def test_compare_cli_rejects_one_sided_nonfinite_metric(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report()
    baseline["results"]["regression"] = {"status": "PASS", "regression_floor_diagnostics": {}}
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"new_metric": {"value": float("nan")}},
    }
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "full",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
        "--fail-on-regression",
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "non-finite numeric diagnostic" in payload["reason"]


def test_compare_cli_rejects_nonfinite_adjudication_without_partial_json(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": float("nan"),
        "strict_regression_ok": False,
    }
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "full",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["status"] == "ERROR"
    assert "non-finite numeric diagnostic" in payload["reason"]


def test_compare_markdown_escapes_markdown_image_syntax_in_adjudication():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "![track](https://attacker.invalid/pixel)",
        "strict_regression_ok": False,
    }

    markdown = format_comparison_markdown(compare_validation_reports("full", baseline, current))

    assert "![track](https://attacker.invalid/pixel)" not in markdown
    assert r"\!\[track\]\(https://attacker.invalid/pixel\)" in markdown


def test_compare_cli_rejects_nonfinite_generated_delta(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": -1e308}},
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": 1e308}},
    }
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "full",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "non-finite numeric diagnostic" in payload["reason"]


def test_compare_cli_rejects_huge_integer_diagnostics(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report()
    baseline["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": 0}},
    }
    current = _report()
    current["results"]["regression"] = {
        "status": "PASS",
        "regression_floor_diagnostics": {"metric": {"value": 10**400}},
    }
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "full",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "non-finite numeric diagnostic" in payload["reason"]


def test_compare_cli_rejects_bad_inputs_and_output_collisions(tmp_path, capsys):
    from chronicler import validation_compare

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text("not-json", encoding="utf-8")
    current_path.write_text(json.dumps(_report()), encoding="utf-8")

    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    assert "invalid baseline report JSON" in json.loads(capsys.readouterr().out)["reason"]

    baseline_path.write_text(json.dumps(_report()), encoding="utf-8")
    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
        "--decision-output",
        str(current_path),
    ]) == 1
    assert "decision-output must be different from current-report" in json.loads(capsys.readouterr().out)["reason"]
