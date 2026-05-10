"""Tests for profile-aware M53b validation gate adjudication."""

from pathlib import Path
import importlib.util
import os
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "m53b_run_validation.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("m53b_run_validation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_subset_gate_passes_when_subset_oracles_pass_even_if_full_gate_oracles_non_pass():
    runner = _load_runner()
    report = _report(
        era="FAIL",
        artifacts="PARTIAL",
        arcs="FAIL",
        regression="FAIL",
        determinism="SKIP",
    )

    decision = runner.adjudicate_validation_report("subset", report)

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


@pytest.mark.parametrize("oracle", ["community", "needs", "cohort"])
@pytest.mark.parametrize("status", ["FAIL", "PARTIAL", "SKIP", "ERROR", "MISSING"])
def test_subset_gate_fails_when_required_subset_oracle_non_pass(oracle, status):
    runner = _load_runner()
    report = _report()
    if status == "MISSING":
        del report["results"][oracle]
    else:
        report["results"][oracle]["status"] = status

    decision = runner.adjudicate_validation_report("subset", report)

    assert decision["ok"] is False
    assert decision["required_failures"] == [{"oracle": oracle, "status": status}]


def test_full_gate_fails_on_full_gate_oracle_non_pass_but_allows_determinism_skip():
    runner = _load_runner()
    report = _report(artifacts="PARTIAL", regression="FAIL", determinism="SKIP")

    decision = runner.adjudicate_validation_report("full", report)

    assert decision["ok"] is False
    assert decision["required_failures"] == [
        {"oracle": "artifacts", "status": "PARTIAL"},
        {"oracle": "regression", "status": "FAIL"},
    ]
    assert decision["informational_non_pass"] == [{"oracle": "determinism", "status": "SKIP"}]


def test_determinism_profiles_require_determinism_pass():
    runner = _load_runner()

    assert runner.adjudicate_validation_report("determinism-hybrid", _report())["ok"] is True
    assert runner.adjudicate_validation_report("determinism-off", _report(determinism="SKIP"))["ok"] is False


def test_profile_defaults_match_documented_validation_scales():
    runner = _load_runner()

    subset = runner.apply_profile_defaults(runner.argparse.Namespace(profile="subset", seeds=None, turns=None))
    full = runner.apply_profile_defaults(runner.argparse.Namespace(profile="full", seeds=None, turns=None))
    det = runner.apply_profile_defaults(runner.argparse.Namespace(profile="determinism-hybrid", seeds=None, turns=None))
    override = runner.apply_profile_defaults(runner.argparse.Namespace(profile="full", seeds=3, turns=7))

    assert (subset.seeds, subset.turns) == (20, 200)
    assert (full.seeds, full.turns) == (200, 500)
    assert (det.seeds, det.turns) == (2, 200)
    assert (override.seeds, override.turns) == (3, 7)


def test_build_env_prepends_absolute_repo_src(monkeypatch):
    runner = _load_runner()

    monkeypatch.setenv("PYTHONPATH", "/already/on/path")
    env = runner._build_env()

    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[:2] == [str(runner.SRC), "/already/on/path"]
    assert env["PYTHONHASHSEED"] == "0"


@pytest.mark.parametrize("module", ["chronicler.main", "chronicler.validate"])
def test_m53b_child_module_commands_resolve_from_non_repo_cwd(monkeypatch, tmp_path, module):
    runner = _load_runner()

    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = runner._build_env()
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir()

    proc = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=outside_cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_validate_batch_writes_report_and_profile_gate_artifacts(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(
        _report(artifacts="PARTIAL", regression="FAIL", determinism="SKIP")
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    subset = runner.validate_batch(tmp_path, "subset.json", Path.cwd(), {}, "subset")
    assert runner.json.loads(subset["report_path"].read_text(encoding="utf-8")) == runner.json.loads(report_text)
    assert subset["decision_path"].name == "gate_decision_subset.json"
    assert subset["summary_path"].name == "gate_summary_subset.md"
    assert subset["decision"]["ok"] is True
    assert subset["decision"]["informational_non_pass"]
    assert "determinism" in subset["summary_path"].read_text(encoding="utf-8")

    full = runner.validate_batch(tmp_path, "full.json", Path.cwd(), {}, "full")
    assert full["decision"]["ok"] is False
    assert full["decision"]["exit_code"] == 2
    assert full["decision_path"].exists()
    assert full["summary_path"].exists()
    assert "Validation gate: full" in full["summary_path"].read_text(encoding="utf-8")


def test_validate_batch_can_require_strict_regression(monkeypatch, tmp_path):
    runner = _load_runner()
    report = _report(determinism="SKIP")
    report["results"]["regression"] = {
        "status": "PASS",
        "regression_adjudication": "calibrated_floor",
        "strict_regression_ok": False,
        "calibrated_floor_ok": True,
    }
    report_text = runner.json.dumps(report)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    default = runner.validate_batch(tmp_path, "default.json", Path.cwd(), {}, "full")
    assert default["decision"]["ok"] is True
    strict = runner.validate_batch(
        tmp_path,
        "strict.json",
        Path.cwd(),
        {},
        "full",
        require_strict_regression=True,
    )
    assert strict["decision"]["ok"] is False
    assert strict["decision"]["required_failures"][0]["status"] == "NON_STRICT"


def test_validate_batch_preserves_structured_report_from_nonzero_validate_cli(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(_report(regression="ERROR", determinism="SKIP"))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout=report_text, stderr="boom")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    subset = runner.validate_batch(tmp_path, "subset.json", Path.cwd(), {}, "subset")
    report = runner.json.loads(subset["report_path"].read_text(encoding="utf-8"))
    assert report["validation_subprocess"]["returncode"] == 1
    assert report["validation_subprocess"]["stderr_tail"] == "boom"
    assert subset["decision"]["ok"] is True
    assert subset["decision"]["oracle_statuses"]["regression"] == {"status": "ERROR"}
    assert subset["decision"]["informational_non_pass"] == [
        {"oracle": "regression", "status": "ERROR"},
        {"oracle": "determinism", "status": "SKIP"},
    ]
    assert subset["decision_path"].exists()
    assert subset["summary_path"].exists()


def test_validate_batch_synthesizes_evidence_for_invalid_validate_cli_output(monkeypatch, tmp_path):
    runner = _load_runner()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="not-json", stderr="boom")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.validate_batch(tmp_path, "full.json", Path.cwd(), {}, "full")
    report = runner.json.loads(result["report_path"].read_text(encoding="utf-8"))
    assert report["status"] == "ERROR"
    assert report["results"]["validation_cli"]["status"] == "ERROR"
    assert report["validation_subprocess"] == {"returncode": 1, "stderr_tail": "boom"}
    assert result["decision"]["ok"] is False
    assert result["decision"]["exit_code"] == 2
    failures = result["decision"]["required_failures"]
    assert failures[0]["oracle"] == "validation_report"
    assert failures[0]["status"] == "ERROR"
    assert "invalid JSON" in failures[0]["reason"]
    assert {item["status"] for item in failures[1:]} == {"MISSING"}
    assert result["decision_path"].exists()
    assert result["summary_path"].exists()


def test_main_writes_manifest_before_gate_failure(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(_report(regression="FAIL", determinism="SKIP"))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "run_full", lambda args, cwd, env: tmp_path)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        ["m53b_run_validation.py", "--profile", "full", "--output-root", str(tmp_path.parent)],
    )

    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2

    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["gate_status"] == "FAIL"
    assert manifest["gate_exit_code"] == 2
    assert Path(manifest["report_path"]).exists()
    assert Path(manifest["decision_path"]).exists()
    assert Path(manifest["summary_path"]).exists()
