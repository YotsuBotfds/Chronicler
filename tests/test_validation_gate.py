"""Tests for report-only validation gate adjudication."""
from __future__ import annotations

import json

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


def test_subset_gate_passes_when_only_non_required_oracles_are_non_pass():
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report(
        era="FAIL",
        artifacts="PARTIAL",
        arcs="FAIL",
        regression="FAIL",
        determinism="SKIP",
    )

    decision = adjudicate_validation_report("subset", report)

    assert decision["ok"] is True
    assert decision["required_oracles"] == ["community", "needs", "cohort"]
    assert decision["required_failures"] == []
    assert {item["oracle"] for item in decision["informational_non_pass"]} == {
        "era",
        "artifacts",
        "arcs",
        "regression",
        "determinism",
    }


@pytest.mark.parametrize("status", ["FAIL", "PARTIAL", "SKIP", "ERROR"])
def test_required_failure_includes_reason_when_present(status):
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report()
    report["results"]["needs"] = {"status": status, "reason": "no_needs_sidecars"}

    decision = adjudicate_validation_report("subset", report)

    assert decision["ok"] is False
    assert decision["required_failures"] == [
        {"oracle": "needs", "status": status, "reason": "no_needs_sidecars"}
    ]


def test_missing_required_oracle_fails_closed():
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report()
    del report["results"]["artifacts"]

    decision = adjudicate_validation_report("full", report)

    assert decision["ok"] is False
    assert {item["oracle"]: item["status"] for item in decision["required_failures"]} == {
        "artifacts": "MISSING"
    }


def test_full_gate_default_allows_calibrated_floor_regression_pass():
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report()
    report["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
    }

    decision = adjudicate_validation_report("full", report)

    assert decision["ok"] is True
    assert decision["required_failures"] == []


def test_strict_regression_ratchet_rejects_calibrated_floor_pass():
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report()
    report["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
        "strict_regression_failed_checks": ["satisfaction_mean", "migration_rate_per_agent_turn"],
        "calibrated_floor_relaxed_checks": ["satisfaction_mean", "migration_rate_per_agent_turn"],
        "calibrated_floor_failed_checks": [],
    }

    decision = adjudicate_validation_report(
        "full",
        report,
        require_strict_regression=True,
    )

    assert decision["ok"] is False
    assert len(decision["required_failures"]) == 1
    failure = decision["required_failures"][0]
    assert failure["oracle"] == "regression"
    assert failure["status"] == "NON_STRICT"
    assert failure["adjudication"] == "calibrated_floor"
    assert failure["strict_regression_failed_checks"] == [
        "satisfaction_mean",
        "migration_rate_per_agent_turn",
    ]
    assert failure["calibrated_floor_relaxed_checks"] == [
        "satisfaction_mean",
        "migration_rate_per_agent_turn",
    ]
    assert failure["calibrated_floor_failed_checks"] == []
    assert "strict" in failure["reason"]


def test_strict_regression_ratchet_accepts_strict_pass():
    from chronicler.validation_gate import adjudicate_validation_report

    report = _report()
    report["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "strict",
        "strict_regression_ok": True,
        "calibrated_floor_ok": True,
    }

    decision = adjudicate_validation_report(
        "full",
        report,
        require_strict_regression=True,
    )

    assert decision["ok"] is True
    assert decision["required_failures"] == []


def test_cli_json_exit_codes(tmp_path, capsys):
    from chronicler import validation_gate

    pass_report = tmp_path / "pass.json"
    pass_report.write_text(json.dumps(_report()), encoding="utf-8")

    assert validation_gate.main(["--profile", "subset", "--report", str(pass_report)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True

    fail_report = tmp_path / "fail.json"
    report = _report(needs="SKIP")
    report["results"]["needs"]["reason"] = "no_needs_sidecars"
    fail_report.write_text(json.dumps(report), encoding="utf-8")

    assert validation_gate.main(["--profile", "subset", "--report", str(fail_report)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["required_failures"] == [
        {"oracle": "needs", "status": "SKIP", "reason": "no_needs_sidecars"}
    ]

    malformed = tmp_path / "bad.json"
    malformed.write_text("not-json", encoding="utf-8")

    assert validation_gate.main(["--profile", "subset", "--report", str(malformed)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "invalid report JSON" in payload["reason"]

    top_level_list = tmp_path / "list.json"
    top_level_list.write_text("[]", encoding="utf-8")

    assert validation_gate.main(["--profile", "subset", "--report", str(top_level_list)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "report JSON must be an object" in payload["reason"]

    assert validation_gate.main(["--profile", "subset", "--report", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "could not read report" in payload["reason"]

    bad_utf8 = tmp_path / "bad-utf8.json"
    bad_utf8.write_bytes(b"\xff\xfe{")

    assert validation_gate.main(["--profile", "subset", "--report", str(bad_utf8)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "could not decode report" in payload["reason"]

    assert validation_gate.main([
        "--profile",
        "not-a-profile",
        "--report",
        str(pass_report),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "unknown profile" in payload["reason"]

    same_output = tmp_path / "same-output"
    assert validation_gate.main([
        "--profile",
        "subset",
        "--report",
        str(pass_report),
        "--decision-output",
        str(same_output),
        "--summary-output",
        str(same_output),
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "must be different paths" in payload["reason"]


def test_gate_decision_payload_includes_statuses_paths_and_required_failures(tmp_path):
    from chronicler.validation_gate import adjudicate_validation_report, build_gate_decision_payload

    report = _report(needs="SKIP", determinism="SKIP")
    report["batch_dir"] = "/tmp/batch"
    report["results"]["needs"]["reason"] = "no_needs_sidecars"
    report_path = tmp_path / "validate_report_subset.json"

    decision = adjudicate_validation_report("subset", report)
    payload = build_gate_decision_payload(decision, report, report_path=report_path)

    assert payload["schema_version"] == 1
    assert payload["profile"] == "subset"
    assert payload["ok"] is False
    assert payload["exit_code"] == 2
    assert payload["report_path"] == str(report_path)
    assert payload["batch_dir"] == "/tmp/batch"
    assert payload["oracle_statuses"]["needs"] == {
        "status": "SKIP",
        "reason": "no_needs_sidecars",
    }
    assert payload["oracle_statuses"]["determinism"] == {"status": "SKIP"}
    assert payload["required_failures"] == [
        {"oracle": "needs", "status": "SKIP", "reason": "no_needs_sidecars"}
    ]


def test_cli_writes_decision_and_summary_outputs_on_gate_failure(tmp_path, capsys):
    from chronicler import validation_gate

    report_path = tmp_path / "fail.json"
    report = _report(needs="SKIP", determinism="SKIP")
    report["batch_dir"] = "/tmp/batch"
    report["results"]["needs"]["reason"] = "no_needs_sidecars"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    decision_path = tmp_path / "decision.json"
    summary_path = tmp_path / "summary.md"

    assert validation_gate.main([
        "--profile",
        "subset",
        "--report",
        str(report_path),
        "--decision-output",
        str(decision_path),
        "--summary-output",
        str(summary_path),
    ]) == 2

    stdout_payload = json.loads(capsys.readouterr().out)
    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert stdout_payload == decision_payload
    assert decision_payload["exit_code"] == 2
    assert decision_payload["required_failures"][0]["reason"] == "no_needs_sidecars"
    summary = summary_path.read_text(encoding="utf-8")
    assert "# Validation gate: subset" in summary
    assert "needs" in summary
    assert "no_needs_sidecars" in summary


def test_cli_writes_decision_and_summary_outputs_on_pass_with_informational_non_pass(tmp_path, capsys):
    from chronicler import validation_gate

    report_path = tmp_path / "pass.json"
    report = _report(determinism="SKIP")
    report_path.write_text(json.dumps(report), encoding="utf-8")
    decision_path = tmp_path / "decision.json"
    summary_path = tmp_path / "summary.md"

    assert validation_gate.main([
        "--profile",
        "subset",
        "--report",
        str(report_path),
        "--decision-output",
        str(decision_path),
        "--summary-output",
        str(summary_path),
    ]) == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert stdout_payload == decision_payload
    assert decision_payload["ok"] is True
    assert decision_payload["exit_code"] == 0
    assert decision_payload["informational_non_pass"] == [{"oracle": "determinism", "status": "SKIP"}]
    summary = summary_path.read_text(encoding="utf-8")
    assert "**Status:** PASS" in summary
    assert "Informational non-PASS" in summary
    assert "determinism" in summary


def test_cli_text_summary_reports_informational_non_pass(tmp_path, capsys):
    from chronicler import validation_gate

    report_path = tmp_path / "subset.json"
    report_path.write_text(json.dumps(_report(determinism="SKIP")), encoding="utf-8")

    assert validation_gate.main([
        "--profile",
        "subset",
        "--report",
        str(report_path),
        "--text",
    ]) == 0

    output = capsys.readouterr().out
    assert "Validation gate passed for profile subset" in output
    assert "Informational non-PASS statuses: determinism=SKIP" in output
