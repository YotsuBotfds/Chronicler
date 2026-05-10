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
