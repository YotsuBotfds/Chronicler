"""Static restrictions on the single-artifact HTTP diagnostic workflow.

These checks execute no shell command, HTTP request, native code or study.
"""
from copy import deepcopy
from pathlib import Path
import shlex

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ".github/workflows/natural-wheel-diagnostics.yml"
BRANCH = "lead/cloud-natural-wheel-diagnostics-20261029"
CLOSED_GATE = "${{ github.event_name == 'push' && github.ref == 'refs/heads/" + BRANCH + "' }}"
INACTIVE_GATE = CLOSED_GATE[:-3] + " && false }}"
CONTRACTS = {
    "control/tests/test_research_natural_wheel.py",
    "control/tests/test_research_natural_runtime_policy.py",
    "control/tests/test_research_natural_continuation.py",
    "control/tests/test_research_natural_readout.py",
    "control/tests/test_research_natural_wheel_http_diagnostics.py",
    "control/tests/test_research_natural_wheel_diagnostic_workflow.py",
}


def load():
    return yaml.safe_load((ROOT / PATH).read_text())


def validate(workflow):
    # PyYAML's YAML1.1 parser may expose GitHub's 'on' key as True.
    triggers = workflow.get("on", workflow.get(True))
    assert triggers == {"push": {"branches": [BRANCH], "paths": [PATH]}}
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert set(workflow["jobs"]) == {"fixed-http-diagnostic"}
    job = workflow["jobs"]["fixed-http-diagnostic"]
    # Activation is a separately reviewed exact-branch gate, never a broad hook.
    assert job["if"] in (INACTIVE_GATE, CLOSED_GATE)
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] == 15
    steps = job["steps"]
    checkouts = [s for s in steps if s.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2
    assert checkouts[0]["with"] == {"path": "control", "persist-credentials": False}
    assert checkouts[1]["with"] == {"ref": "c76efe8552b4c6c288ebb1f813e2c0a58e5957b1",
        "path": "producer", "persist-credentials": False}
    setups = [s for s in steps if s.get("uses", "").startswith("actions/setup-python@")]
    assert len(setups) == 1 and setups[0]["with"]["python-version"] == "3.13.17"
    runs = [(index, step) for index, step in enumerate(steps) if "run" in step]
    probe = [(index, step) for index, step in runs if "fetch_research_natural_wheel.py" in step["run"]]
    assert len(probe) == 1
    probe_index, probe_step = probe[0]
    assert probe_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "if" not in probe_step and probe_step["shell"] == "bash"
    tokens = shlex.split(probe_step["run"].replace("\\\n", " "))
    assert tokens[-5:] == ["--diagnostic", "--source-root", "$GITHUB_WORKSPACE/producer",
        "--output-root", "$RUNNER_TEMP/natural-wheel-diagnostic"]
    tests = [(index, step) for index, step in runs if "-m pytest" in step["run"]]
    assert len(tests) == 1 and tests[0][0] < probe_index
    assert tests[0][1]["env"] == {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": "${{ github.workspace }}/control/scripts/testing:${{ github.workspace }}/producer/src",
        "CHRONICLER_OFFLINE_GUARD_REPORT": "${{ runner.temp }}/natural-wheel-diagnostic-contracts/guard.json"}
    assert "-p python_oracle_guard -p no:cacheprovider" in tests[0][1]["run"]
    assert "if" not in tests[0][1]
    selected = {token for token in shlex.split(tests[0][1]["run"].replace("\\\n", " ")) if token.startswith("control/tests/")}
    assert selected == CONTRACTS
    for _, step in runs:
        assert step["shell"] == "bash" and step["run"].startswith("set -euo pipefail\n")
        command = step["run"]
        assert not any(word in command for word in ("run_research_natural_continuation.py", "read_research_natural_continuation.py",
            "maturin", "cargo ", "uv pip install", ".whl", "curl ", "wget ", "gh api", "continue-on-error", "--freeze"))
        assert not any(key in step.get("env", {}) for key in ("GH_TOKEN", "GITHUB_TOKEN")) or step is probe_step
    assert workflow["env"]["PYTHON_CPU_COUNT"] == "1"
    assert "taskset -c \"$DIAGNOSTIC_CPU\"" in probe_step["run"]
    combined = "\n".join(step["run"] for _, step in runs)
    assert "uv==0.12.23" in combined and "uv sync --project producer --frozen --no-install-project" in combined
    uploads = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(uploads) == 1 and uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"].splitlines() == [
        "${{ runner.temp }}/natural-wheel-diagnostic-contracts/", "${{ runner.temp }}/natural-wheel-diagnostic/"]
    assert uploads[0]["with"]["retention-days"] == 30


def test_diagnostic_workflow_has_only_the_closed_preflight_and_one_fixed_probe():
    validate(load())


def test_reviewed_activation_can_only_remove_the_false_gate_on_the_same_branch():
    workflow = load()
    workflow["jobs"]["fixed-http-diagnostic"]["if"] = CLOSED_GATE
    validate(workflow)


@pytest.mark.parametrize("fault", ["broad_trigger", "broad_gate", "other_source", "extra_probe", "study_command", "token_scope", "tests_after_probe"])
def test_workflow_rejects_scope_expansion_or_preflight_bypass(fault):
    workflow = deepcopy(load())
    job = workflow["jobs"]["fixed-http-diagnostic"]
    steps = job["steps"]
    if fault == "broad_trigger":
        workflow.get("on", workflow.get(True))["push"]["branches"] = ["**"]
    elif fault == "broad_gate":
        job["if"] = "${{ true }}"
    elif fault == "other_source":
        steps[1]["with"]["ref"] = "main"
    elif fault == "extra_probe":
        steps.insert(-1, deepcopy(next(s for s in steps if "fetch_research_natural_wheel.py" in s.get("run", ""))))
    elif fault == "study_command":
        steps[-2]["run"] += "\npython control/scripts/run_research_natural_continuation.py run\n"
    elif fault == "token_scope":
        next(s for s in steps if "-m pytest" in s.get("run", ""))["env"]["GH_TOKEN"] = "${{ github.token }}"
    else:
        first = next(i for i, s in enumerate(steps) if "-m pytest" in s.get("run", ""))
        second = next(i for i, s in enumerate(steps) if "fetch_research_natural_wheel.py" in s.get("run", ""))
        steps[first], steps[second] = steps[second], steps[first]
    with pytest.raises(AssertionError):
        validate(workflow)
