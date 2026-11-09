"""scripts/regression_smoke.py, its fixture, and the DEP-9 workflows' contracts.

Reads files only (no child process, network or native import).
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "regression_smoke.py"
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "regression-smoke.yml"
SWEEP_WORKFLOW = ROOT / ".github" / "workflows" / "hashseed-sweep.yml"


@pytest.fixture(scope="module")
def RS():
    spec = importlib.util.spec_from_file_location("regression_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fixture(RS):
    return json.loads(RS.FIXTURE.read_text(encoding="utf-8"))


def _report(RS, **overrides):
    results = {oracle: {"status": "PASS"} for oracle, _key in RS.METRIC_PATHS}
    for oracle, key in RS.METRIC_PATHS:
        results[oracle][key] = 1
    results["regression"]["civ_survival_counts"] = [3, 4]
    for path, value in overrides.items():
        oracle, key = path.split(".")
        results[oracle][key] = value
    return {"results": results}


def test_fixture_is_well_formed(RS, fixture):
    assert set(fixture) == {"schema_version", "provenance", "invocation", "statuses", "metrics"}
    assert fixture["schema_version"] == RS.SCHEMA_VERSION
    assert fixture["provenance"]["commit"] and fixture["provenance"]["platform"]
    assert fixture["invocation"] == RS.EXPECTED_INVOCATION
    assert list(fixture["metrics"]) == [f"{oracle}.{key}" for oracle, key in RS.METRIC_PATHS]
    assert fixture["statuses"]["regression"] in ("PASS", "FAIL")
    assert len(fixture["metrics"]["regression.final_living_population_counts"]) == 4


def test_extract_and_compare(RS, fixture):
    manifest = dict(RS.EXPECTED_INVOCATION, parallel=3)
    actual = RS.extract(_report(RS), manifest)
    assert actual["invocation"] == RS.EXPECTED_INVOCATION
    assert RS.compare(actual, copy.deepcopy(actual)) == []
    changed = RS.extract(_report(RS, **{"needs.net_concordance": 1.0001}), manifest)
    assert RS.compare(actual, changed) == ["metrics needs.net_concordance: fixture 1, run 1.0001"]
    assert RS.compare(actual, changed, abs_tol=0.001) == []
    status = RS.extract(_report(RS, **{"era.status": "FAIL"}), manifest)
    assert RS.compare(actual, status) == ["statuses era: fixture 'PASS', run 'FAIL'"]
    lists = RS.extract(_report(RS, **{"regression.civ_survival_counts": [3, 3]}), manifest)
    assert RS.compare(actual, lists)[0].startswith("metrics regression.civ_survival_counts")
    other = RS.extract(_report(RS), dict(manifest, turns=200))
    assert RS.compare(actual, other) == ["invocation turns: fixture 100, run 200"]
    flag = RS.extract(_report(RS, **{"needs.analyzed_seeds": True}), manifest)
    assert RS.compare(actual, flag)


def test_cli_compare_and_write(RS, tmp_path, capsys):
    batch = tmp_path / "batch_42"
    batch.mkdir()
    with pytest.raises(FileNotFoundError):
        RS.main(["compare", str(batch)])
    (batch / RS.REPORT_NAME).write_text(json.dumps(_report(RS)), encoding="utf-8")
    (batch / RS.RUN_MANIFEST_NAME).write_text(json.dumps(RS.EXPECTED_INVOCATION), encoding="utf-8")
    out = tmp_path / "fixture.json"
    assert RS.main(["write", str(batch), "--fixture", str(out), "--commit", "abc", "--platform", "p"]) == 0
    assert RS.main(["compare", str(batch), "--fixture", str(out)]) == 0
    (batch / RS.REPORT_NAME).write_text(json.dumps(_report(RS, **{"era.collapse_episode_count": 9})),
                                        encoding="utf-8")
    assert RS.main(["compare", str(batch), "--fixture", str(out)]) == 1
    assert "DRIFT" in capsys.readouterr().out
    (batch / RS.RUN_MANIFEST_NAME).write_text(json.dumps(dict(RS.EXPECTED_INVOCATION, seeds=20)),
                                              encoding="utf-8")
    assert RS.main(["write", str(batch), "--fixture", str(out), "--commit", "abc", "--platform", "p"]) == 2


def _workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_smoke_workflow_runs_the_fixture_invocation(RS):
    workflow = _workflow(SMOKE_WORKFLOW)
    assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
    steps = workflow["jobs"]["smoke"]["steps"]
    run = next(s["run"] for s in steps if s.get("name") == "Run the smoke batch")
    inv = RS.EXPECTED_INVOCATION
    for flag in (f"--profile {inv['profile']}", f"--seeds {inv['seeds']}", f"--turns {inv['turns']}"):
        assert flag in run
    assert "--hash-seed" not in run and "--seed-start" not in run and "--worldgen" not in run
    assert any("scripts/regression_smoke.py compare" in s.get("run", "") for s in steps)


def test_hashseed_sweep_stays_disabled_until_cor1():
    workflow = _workflow(SWEEP_WORKFLOW)
    jobs = workflow["jobs"]
    for name in ("sweep", "compare"):
        assert jobs[name]["if"] == "false", name
    assert jobs["sweep"]["strategy"]["matrix"]["h"] == ["0", "1", "2", "random"]
    text = SWEEP_WORKFLOW.read_text(encoding="utf-8")
    assert text.count("TODO(COR-1)") == 2
    assert "--profile determinism-off" in text and '--hash-seed "$HASH_SEED"' in text
    real = jobs["real-process"]
    assert "if" not in real
    assert "pytest -m real_process" in real["steps"][-1]["run"]
