"""Tests for profile-aware M53b validation gate adjudication."""

from pathlib import Path
import importlib.util
import subprocess

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


def test_validate_batch_writes_report_and_enforces_profile_gate(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(
        _report(artifacts="PARTIAL", regression="FAIL", determinism="SKIP")
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    subset_path = runner.validate_batch(tmp_path, "subset.json", Path.cwd(), {}, "subset")
    assert subset_path.read_text() == report_text

    with pytest.raises(SystemExit, match="Validation gate failed for profile full"):
        runner.validate_batch(tmp_path, "full.json", Path.cwd(), {}, "full")
