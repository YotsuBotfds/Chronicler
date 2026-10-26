"""Tests for validation report comparison tooling."""
from __future__ import annotations

import json
import os

import pytest


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
    assert "invalid current report JSON" in payload["reason"]
    assert "non-finite JSON constant" in payload["reason"]


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
    assert "invalid current report JSON" in payload["reason"]
    assert "non-finite JSON constant" in payload["reason"]


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
    assert "invalid current report JSON" in payload["reason"]
    assert "non-finite JSON constant" in payload["reason"]


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


def test_compare_cli_rejects_duplicate_keys_in_report_json(tmp_path, capsys):
    from chronicler import validation_compare

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(_report()), encoding="utf-8")
    current_path.write_text(
        '{"results": {"needs": {"status": "FAIL"}, "needs": {"status": "PASS"}}}',
        encoding="utf-8",
    )

    assert validation_compare.main([
        "--profile",
        "subset",
        "--baseline-report",
        str(baseline_path),
        "--current-report",
        str(current_path),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "invalid current report JSON" in payload["reason"]
    assert "duplicate JSON key: needs" in payload["reason"]


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


# --- Needs oracle method 2 against method 1 reports ----------------------


def _needs_method(report, status, version):
    report["results"]["needs"] = {"status": status, "method_version": version}
    return report


def test_compare_does_not_count_a_needs_method_change_as_a_new_failure():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(determinism="SKIP")  # method 1: no method_version
    current = _needs_method(_report(determinism="SKIP"), "FAIL", 2)

    result = compare_validation_reports("subset", baseline, current, fail_on_regression=True)

    assert result["new_required_failures"] == []
    assert result["regression_detected"] is False
    assert result["exit_code"] == 0
    assert result["rebaseline_required"] is True
    assert result["oracle_method_changes"] == [{
        "oracle": "needs",
        "baseline_method_version": 1,
        "current_method_version": 2,
        "baseline_status": "PASS",
        "current_status": "FAIL",
    }]
    assert result["method_changed_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
    # The current report still fails its own gate.
    assert result["current_decision"]["ok"] is False


def test_compare_does_not_count_a_needs_method_change_as_resolved():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(needs="FAIL", determinism="SKIP")
    current = _needs_method(_report(determinism="SKIP"), "PASS", 2)

    result = compare_validation_reports("subset", baseline, current)

    assert result["resolved_required_failures"] == []
    assert result["method_changed_required_failures"] == []
    assert result["rebaseline_required"] is True


def test_compare_same_needs_method_keeps_new_failure_detection():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _needs_method(_report(determinism="SKIP"), "PASS", 2)
    current = _needs_method(_report(determinism="SKIP"), "FAIL", 2)

    result = compare_validation_reports("subset", baseline, current)

    assert result["new_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
    assert result["regression_reasons"] == ["new_required_failures"]
    assert result["oracle_method_changes"] == []
    assert result["rebaseline_required"] is False


def test_compare_rejects_a_malformed_method_version():
    import pytest
    from chronicler.validation_compare import compare_validation_reports
    from chronicler.validation_gate import ValidationGateInputError

    current = _needs_method(_report(determinism="SKIP"), "PASS", "2")
    with pytest.raises(ValidationGateInputError, match="invalid method_version for oracle needs"):
        compare_validation_reports("subset", _report(determinism="SKIP"), current)


def test_compare_cli_old_needs_report_against_new_one(tmp_path, capsys):
    from chronicler import validation_compare

    baseline = _report(determinism="SKIP")
    baseline["results"]["needs"].update(
        seeds_with_expected_sign=16, required_seed_count=12, total_pairs=34, median_effect_size=1.17,
    )
    current = _needs_method(_report(determinism="SKIP"), "FAIL", 2)
    current["results"]["needs"].update(net_concordance=0.02, net_concordance_lower_bound=-0.05)
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    summary_path = tmp_path / "compare.md"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    assert validation_compare.main([
        "--profile", "subset",
        "--baseline-report", str(baseline_path),
        "--current-report", str(current_path),
        "--summary-output", str(summary_path),
        "--fail-on-regression",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["regression_detected"] is False
    assert payload["rebaseline_required"] is True
    summary = summary_path.read_text(encoding="utf-8")
    assert "## Oracle method changes" in summary
    assert "| needs | 1 | PASS | 2 | FAIL |" in summary


def test_compare_needs_method_2_against_method_3_requires_rebaselining(tmp_path):
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    baseline = _needs_method(_report(determinism="SKIP"), "PASS", 2)
    current = _needs_method(_report(determinism="SKIP"), "FAIL", 3)
    current["results"]["needs"]["failed_criteria"] = ["binding_lower_bound"]

    result = compare_validation_reports("subset", baseline, current, fail_on_regression=True)

    assert result["new_required_failures"] == []
    assert result["exit_code"] == 0
    assert result["rebaseline_required"] is True
    assert result["oracle_method_changes"][0]["baseline_method_version"] == 2
    assert result["oracle_method_changes"][0]["current_method_version"] == 3
    assert result["current_decision"]["ok"] is False
    assert "| needs | 2 | PASS | 3 | FAIL |" in format_comparison_markdown(result)

    # Method 3 against method 3 counts a new failure again.
    baseline = _needs_method(_report(determinism="SKIP"), "PASS", 3)
    result = compare_validation_reports("subset", baseline, current)
    assert result["new_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
    assert result["rebaseline_required"] is False


def test_compare_needs_method_3_against_method_4_requires_rebaselining():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    # Method 4 counts outcomes after the snapshot turn; a method 3 PASS
    # against a method 4 FAIL is a method change, not a new failure.
    baseline = _needs_method(_report(determinism="SKIP"), "PASS", 3)
    current = _needs_method(_report(determinism="SKIP"), "FAIL", 4)
    current["results"]["needs"]["failed_criteria"] = ["net_concordance_lower_bound"]

    for profile in ("subset", "full"):
        result = compare_validation_reports(profile, baseline, current, fail_on_regression=True)
        assert result["new_required_failures"] == []
        assert result["exit_code"] == 0
        assert result["rebaseline_required"] is True
        assert [(c["baseline_method_version"], c["current_method_version"]) for c in result["oracle_method_changes"]] == [
            (3, 4)]
        assert result["method_changed_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
        assert "| needs | 3 | PASS | 4 | FAIL |" in format_comparison_markdown(result)

    # Method 4 against method 4 counts a new failure again.
    baseline = _needs_method(_report(determinism="SKIP"), "PASS", 4)
    result = compare_validation_reports("subset", baseline, current)
    assert result["new_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
    assert result["rebaseline_required"] is False


def test_compare_cohort_method_1_against_method_2_requires_rebaselining():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    # Cohort method 2 counts outcomes after the snapshot turn; its results
    # carry method_version 2, method 1 results none.
    baseline = _report(determinism="SKIP")
    current = _report(determinism="SKIP")
    current["results"]["cohort"] = {"status": "FAIL", "method_version": 2, "outcome_window_start_offset": 1}

    for profile in ("subset", "full"):
        result = compare_validation_reports(profile, baseline, current, fail_on_regression=True)
        assert result["new_required_failures"] == []
        assert result["exit_code"] == 0
        assert result["rebaseline_required"] is True
        assert result["oracle_method_changes"] == [{
            "oracle": "cohort", "baseline_method_version": 1, "current_method_version": 2,
            "baseline_status": "PASS", "current_status": "FAIL",
        }]
        assert result["method_changed_required_failures"] == [{"oracle": "cohort", "status": "FAIL"}]
        assert "| cohort | 1 | PASS | 2 | FAIL |" in format_comparison_markdown(result)

    # Method 2 against method 2 counts a new failure again.
    baseline["results"]["cohort"] = {"status": "PASS", "method_version": 2}
    result = compare_validation_reports("subset", baseline, current)
    assert result["new_required_failures"] == [{"oracle": "cohort", "status": "FAIL"}]
    assert result["rebaseline_required"] is False


def _needs_binding(report, lower_bound, *, required):
    binding_ok = lower_bound > 0
    report["results"]["needs"] = {
        "status": "PASS" if binding_ok or not required else "FAIL",
        "method_version": 3,
        "failed_criteria": [] if binding_ok or not required else ["binding_lower_bound"],
        "informational_failed_criteria": [] if binding_ok or required else ["binding_lower_bound"],
        "binding_required": required,
        "binding": {"status": "PASS" if binding_ok else "FAIL", "net_concordance_lower_bound": lower_bound},
    }
    return report


def test_compare_subset_informational_binding_failure_is_no_regression():
    from chronicler.validation_compare import compare_validation_reports

    baseline = _needs_binding(_report(determinism="SKIP"), 0.07, required=False)
    # Scored for the subset (binding informational) or without a profile
    # (binding decides the result's own status): the subset gate ignores it.
    for required in (False, True):
        current = _needs_binding(_report(determinism="SKIP"), -0.028, required=required)
        result = compare_validation_reports("subset", baseline, current, fail_on_regression=True)
        assert result["new_required_failures"] == []
        assert result["regression_detected"] is False
        assert result["exit_code"] == 0
        assert result["current_decision"]["ok"] is True
        assert result["rebaseline_required"] is False

        # The full profile requires the binding component: a new failure there.
        result = compare_validation_reports("full", baseline, current, fail_on_regression=True)
        assert result["new_required_failures"] == [{"oracle": "needs", "status": "FAIL"}]
        assert result["exit_code"] == 2


# --- Comparable cohorts (docs/integration/validation-integrity.md) -------


def _cohort_report(seeds, turns=200, **statuses):
    """A report of an old batch: its seeds and final turns only in the
    regression oracle's per-seed population rows."""
    report = _report(determinism="SKIP", **statuses)
    report["results"]["regression"]["final_living_population_by_seed"] = [
        {"seed": seed, "population": 100, "turn": turns} for seed in seeds
    ]
    return report


def _manifest_report(seeds=range(42, 62), turns=200, simulation=None, profile="subset", **statuses):
    report = _cohort_report(seeds, turns, **statuses)
    report["batch_manifest"] = {
        "status": "verified", "seeds": list(seeds), "turns": turns,
        "simulation": {"turns": turns, "agents": "hybrid", "cities": None, **(simulation or {})},
    }
    report["profile"] = profile
    return report


def test_compare_refuses_a_hundred_seeds_against_one():
    import pytest
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown
    from chronicler.validation_gate import ValidationGateInputError

    baseline = _cohort_report(range(42, 142))
    current = _cohort_report([42])
    with pytest.raises(ValidationGateInputError, match="different cohorts: seeds: baseline 100 run\\(s\\) of seeds "
                                                       "42-141, current 1 run\\(s\\) of seeds 42.*--exploratory"):
        compare_validation_reports("subset", baseline, current)

    result = compare_validation_reports("subset", baseline, current, exploratory=True)
    assert result["exploratory"] is True and result["status"] == "NO_REGRESSION"
    assert [item["field"] for item in result["cohort"]["mismatches"]] == ["seeds"]
    summary = format_comparison_markdown(result)
    assert "(EXPLORATORY)" in summary and "**Status:** EXPLORATORY, NO REGRESSION" in summary
    assert "not regression evidence" in summary


@pytest.mark.parametrize("change, field", [
    (lambda: (_cohort_report(range(42, 62), 200), _cohort_report(range(42, 62), 500)), "turns"),
    (lambda: (_cohort_report(range(42, 62)), _cohort_report(range(62, 82))), "seeds"),
    (lambda: (_manifest_report(), _manifest_report(simulation={"cities": False})), "simulation"),
    (lambda: (_manifest_report(), _manifest_report(profile="full")), "profile"),
])
def test_compare_refuses_other_cohort_differences(change, field):
    from chronicler.validation_compare import compare_validation_reports
    from chronicler.validation_gate import ValidationGateInputError

    baseline, current = change()
    with pytest.raises(ValidationGateInputError, match="different cohorts"):
        compare_validation_reports("subset", baseline, current)
    result = compare_validation_reports("subset", baseline, current, exploratory=True)
    assert [item["field"] for item in result["cohort"]["mismatches"]] == [field]


def test_compare_names_the_simulation_settings_that_differ():
    from chronicler.validation_compare import compare_cohorts

    cohort = compare_cohorts(_manifest_report(), _manifest_report(simulation={"cities": False, "agents": "off"}))
    assert cohort["mismatches"] == [{
        "field": "simulation",
        "description": "simulation configuration: agents 'hybrid' vs 'off', cities None vs False",
    }]


def test_compare_a_setting_named_by_one_manifest_only_is_its_default():
    from chronicler.validation_compare import compare_cohorts

    newer = _manifest_report()
    newer["batch_manifest"]["simulation"]["a_later_switch"] = None
    assert compare_cohorts(_manifest_report(), newer)["mismatches"] == []
    newer["batch_manifest"]["simulation"]["a_later_switch"] = True
    assert compare_cohorts(_manifest_report(), newer)["mismatches"][0]["description"] == (
        "simulation configuration: a_later_switch None vs True")


def test_compare_same_cohort_and_unverified_fields():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    # Both from manifests: everything checked.
    result = compare_validation_reports("subset", _manifest_report(), _manifest_report())
    cohort = result["cohort"]
    assert (cohort["comparable"], cohort["unverified"], result["exploratory"]) == (True, [], False)
    # Markdown-escaped: "Same cohort: 20 run(s) of seeds 42-61, 200 turns."
    assert "Same cohort: 20 run\\(s\\) of seeds 42-61, 200 turns." in format_comparison_markdown(result)

    # An old baseline: seeds and turns from its per-seed rows; the
    # simulation configuration and profile are not recorded there.
    result = compare_validation_reports("subset", _cohort_report(range(42, 62)), _manifest_report())
    cohort = result["cohort"]
    assert cohort["comparable"] is True and result["exploratory"] is False
    assert cohort["unverified"] == ["simulation", "profile"]
    assert (cohort["baseline_source"], cohort["current_source"]) == ("per-seed results", "batch_manifest")
    summary = format_comparison_markdown(result)
    assert "so not checked: simulation, profile" in summary

    # Reports that record nothing (synthetic or very old): nothing to refuse.
    assert compare_validation_reports("subset", _report(), _report())["cohort"]["unverified"] == [
        "seeds", "turns", "simulation", "profile"]


def test_compare_determinism_pairs_keep_their_repeated_seed():
    from chronicler.validation_compare import compare_cohorts, report_cohort

    pair = _cohort_report([42, 42])
    assert report_cohort(pair)["seeds"] == [42, 42]
    assert compare_cohorts(pair, _cohort_report([42]))["mismatches"][0]["field"] == "seeds"


def test_compare_old_needs_profile_is_read_from_the_needs_result():
    from chronicler.validation_compare import compare_cohorts

    baseline, current = _cohort_report(range(42, 62)), _cohort_report(range(42, 62))
    baseline["results"]["needs"]["profile"] = "subset"
    current["results"]["needs"]["profile"] = "full"
    assert [item["field"] for item in compare_cohorts(baseline, current)["mismatches"]] == ["profile"]


def test_compare_worlds_still_name_the_worlds_and_allow_exploration():
    from chronicler.validation_compare import compare_validation_reports
    from chronicler.validation_gate import ValidationGateInputError

    procedural = _report(determinism="SKIP")
    procedural["worlds"] = [{"generator": "procedural", "regions": 32, "civs": 10, "seeds": 20}]
    with pytest.raises(ValidationGateInputError, match="measure different worlds: .*--exploratory"):
        compare_validation_reports("subset", _report(determinism="SKIP"), procedural)
    result = compare_validation_reports("subset", _report(determinism="SKIP"), procedural, exploratory=True)
    assert [item["field"] for item in result["cohort"]["mismatches"]] == ["worlds"]


def test_compare_status_says_what_no_regression_means():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    result = compare_validation_reports("subset", _manifest_report(), _manifest_report())
    assert result["status"] == "NO_REGRESSION"
    assert "no required gate newly fails" in result["status_meaning"]
    summary = format_comparison_markdown(result)
    assert "**Status:** NO REGRESSION" in summary
    assert "does not mean the distributions are unchanged" in summary


def test_compare_lists_evidence_by_category():
    from chronicler.validation_compare import compare_validation_reports, format_comparison_markdown

    baseline = _manifest_report()
    current = _manifest_report(needs="FAIL")
    result = compare_validation_reports("subset", baseline, current)
    rows = {row["category"]: row for row in result["evidence_by_category"]}
    assert list(rows) == ["execution", "determinism", "balance", "mechanism"]
    assert rows["mechanism"]["current"] == "FAIL: needs FAIL"
    assert rows["mechanism"]["baseline"] == "PASS"
    assert rows["balance"]["current"] == "PASS"
    # A skipped oracle is not a pass.
    assert rows["determinism"]["current"] == "NOT PASSED (informational only): determinism SKIP"
    assert rows["execution"]["current"] == "PASS (batch manifest verified: 20 runs x 200 turns)"
    # Informational failures under the subset profile stay visible.
    current = _manifest_report(era="FAIL", regression="FAIL", artifacts="FAIL", arcs="FAIL")
    rows = {row["category"]: row for row in compare_validation_reports("subset", baseline, current)["evidence_by_category"]}
    assert rows["mechanism"]["current"] == "PASS: needs, community, cohort; informational non-PASS: era FAIL"
    assert rows["balance"]["current"] == (
        "NOT PASSED (informational only): artifacts FAIL, arcs FAIL, regression FAIL")
    assert result["unmeasured_categories"] == ["conservation", "performance", "rendering"]
    summary = format_comparison_markdown(result)
    assert "## Evidence by category" in summary
    assert "Not measured by validation reports: conservation, performance, rendering." in summary
    old = compare_validation_reports("subset", _report(), _report())
    assert {row["category"]: row["current"] for row in old["evidence_by_category"]}["execution"] == (
        "NOT CHECKED (report predates batch manifests)")


def test_compare_cli_exploratory_flag(tmp_path, capsys):
    from chronicler import validation_compare

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    summary_path = tmp_path / "compare.md"
    baseline_path.write_text(json.dumps(_cohort_report(range(42, 142))), encoding="utf-8")
    current_path.write_text(json.dumps(_cohort_report([42])), encoding="utf-8")
    argv = ["--profile", "subset", "--baseline-report", str(baseline_path), "--current-report", str(current_path)]

    assert validation_compare.main(argv) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR" and "different cohorts" in payload["reason"]

    assert validation_compare.main(argv + ["--exploratory", "--summary-output", str(summary_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exploratory"] is True
    assert "EXPLORATORY" in summary_path.read_text(encoding="utf-8")
