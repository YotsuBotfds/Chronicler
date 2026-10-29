"""Regression tests for documented no-Rust/native build and test lanes."""

from pathlib import Path
import ast
import re
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_rust_extension_msrv_is_explicit_and_matches_arrow_dependency():
    cargo = tomllib.loads(_read("chronicler-agents/Cargo.toml"))

    assert cargo["package"]["rust-version"] == "1.85"


def test_pyo3_extension_module_feature_is_maturin_only_so_cargo_tests_link():
    cargo = tomllib.loads(_read("chronicler-agents/Cargo.toml"))
    maturin = tomllib.loads(_read("chronicler-agents/pyproject.toml"))

    pyo3_dep = cargo["dependencies"]["pyo3"]
    pyo3_features = pyo3_dep.get("features", []) if isinstance(pyo3_dep, dict) else []

    assert "extension-module" not in pyo3_features
    assert "pyo3/extension-module" in maturin["tool"]["maturin"]["features"]


def test_jemalloc_is_opt_in_for_python_extension_import_tls_safety():
    cargo = tomllib.loads(_read("chronicler-agents/Cargo.toml"))
    lib_rs = _read("chronicler-agents/src/lib.rs")

    assert "jemalloc" not in cargo.get("features", {}).get("default", [])
    assert cargo["features"]["jemalloc"] == ["dep:tikv-jemallocator"]
    jemalloc_dep = cargo['target']['cfg(not(target_os = "windows"))']["dependencies"][
        "tikv-jemallocator"
    ]
    assert jemalloc_dep["optional"] is True
    assert 'feature = "jemalloc"' in lib_rs


def test_unix_setup_uses_venv_bound_maturin_and_fail_closed_pipeline():
    script = _read("setup.sh")

    assert "set -euo pipefail" in script
    assert "python -m pip install \"maturin>=1.5,<2\" --quiet" in script
    assert "python -m maturin develop --release" in script
    assert "maturin develop --release 2>&1 | tail -n 1" not in script


def test_windows_setup_uses_venv_bound_maturin_and_checks_errors():
    script = _read("setup.bat")

    assert "python -m pip install \"maturin>=1.5,<2\" --quiet" in script
    assert "python -m maturin develop --release" in script
    assert "if errorlevel 1 exit /b 1" in script


def test_readme_documents_no_rust_and_native_test_lanes():
    readme = _read("README.md")

    assert "Rust 1.85+" in readme
    assert "No-Rust Python lane" in readme
    assert "Native Python lane" in readme
    assert "cargo test --manifest-path chronicler-agents/Cargo.toml --quiet" in readme
    assert "EXTENSION_SUFFIXES" in readme
    assert "find_spec(\"chronicler_agents.chronicler_agents\")" in readme
    assert readme.index("import chronicler_agents as ca") < readme.index("import pytest")
    assert "full = 200 seeds x 500 turns" in readme
    assert "scripts/m53b_run_validation.py --profile full" in readme
    assert "--require-strict-regression" in readme
    assert "python -m chronicler.validation_compare" in readme
    assert "--fail-on-regression" in readme
    assert "compare_decision_*.json" in readme
    assert "Comparator hard failures follow the selected validation profile" in readme
    assert "validation JSON artifacts are written with strict JSON serialization and atomic same-directory replacement" in readme
    assert "new artifact permissions respect the process umask without mutating it" in readme


def test_validation_gate_workflow_builds_native_extension_as_wheel():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "python -m maturin build --release --locked" in workflow
    assert "uv pip install --python ../.venv/bin/python target/wheels/*.whl" in workflow
    assert "python -m maturin develop --release" not in workflow


def test_ci_installs_python_dependencies_from_the_lockfile():
    for path in (".github/workflows/tests.yml", ".github/workflows/validation-gate.yml"):
        workflow = _read(path)
        assert "uv lock --check" in workflow, path
        assert "uv sync --frozen" in workflow, path
        assert "pip install -e ." not in workflow, path
        assert workflow.index("uv sync --frozen") < workflow.index("python -m maturin build"), path


def test_github_tests_workflow_has_a_viewer_job():
    workflow = _read(".github/workflows/tests.yml")
    viewer = workflow[workflow.index("  viewer:"):]

    assert "working-directory: viewer" in viewer
    assert "cache-dependency-path: viewer/package-lock.json" in viewer
    steps = ["npm ci", "npm test -- --maxWorkers=2", "npm run lint", "npm run build"]
    assert all(step in viewer for step in steps)
    assert [viewer.index(step) for step in steps] == sorted(viewer.index(step) for step in steps)


def test_validation_gate_workflow_preserves_reports_as_artifacts():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "actions/upload-artifact@v4" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "if: always()" in workflow
    assert "output/github-validation/${{ github.run_id }}" in workflow
    assert "retention-days: 30" in workflow


def test_validation_gate_workflow_publishes_gate_summary():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "gate_summary_*.md" in workflow
    assert "Publish validation gate summary" in workflow
    assert workflow.index("Publish validation gate summary") < workflow.index("Upload validation reports")


def test_validation_gate_workflow_publishes_compare_summary_when_baseline_is_used():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "baseline_report:" in workflow
    assert "fail_on_regression:" in workflow
    assert "--baseline-report" in workflow
    assert "--fail-on-regression" in workflow
    assert "compare_summary_*.md" in workflow
    assert "BASELINE_REPORT=\"${{ github.event.inputs.baseline_report" not in workflow
    assert "BASELINE_REPORT_INPUT" in workflow
    assert "baseline_report || ''" in workflow


def test_validation_gate_workflow_exposes_strict_regression_ratchet():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "require_strict_regression:" in workflow
    assert "--require-strict-regression" in workflow
    assert "inputs.require_strict_regression" in workflow


def test_github_tests_workflow_has_no_rust_and_native_jobs():
    workflow = _read(".github/workflows/tests.yml")
    jobs = yaml.load(workflow, Loader=yaml.BaseLoader)["jobs"]

    assert "python-no-rust" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "python-native" in workflow
    assert "Assert native extension is absent" in workflow
    assert workflow.count("python -m maturin build --release --locked") == 1
    assert "uv pip install --python ../.venv/bin/python target/wheels/*.whl" in workflow
    assert "python -m maturin develop --release" not in workflow
    steps = jobs["python-native-tests"]["steps"]
    names = [step["name"] for step in steps]
    assert names.index("Verify source producer and whole wheel before install") < names.index("Install the same verified current-source wheel") < names.index("Full default collection then owned module execution")
    command = next(s["run"] for s in steps if s["name"] == "Full default collection then owned module execution")
    assert 'scripts/native_ci_shards.py run --execute --shard "${{ matrix.shard }}"' in command
    controller = _read("scripts/native_ci_shards.py")
    functions = {node.name: node for node in ast.parse(controller).body if isinstance(node, ast.FunctionDef)}
    identity = ast.unparse(functions["current_identity"])
    assert "find_spec('chronicler_agents.chronicler_agents')" in identity
    assert "EXTENSION_SUFFIXES" in identity
    main = ast.unparse(functions["main"])
    assert main.index("current_identity(") < main.index("import pytest") < main.index("pytest.main(")


def _workflow_jobs(path):
    return yaml.load(_read(path), Loader=yaml.BaseLoader)["jobs"]


def test_standard_workflow_preserves_independent_bodies_and_public_gate_names():
    current = _read(".github/workflows/tests.yml")
    historical = _read("tests/fixtures/ci/standard-tests-cbf6e368.yml")
    assert current.split("jobs:\n", 1)[0] == historical.split("jobs:\n", 1)[0]
    def blocks(text):
        return dict(re.findall(r"(?ms)^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", text.split("jobs:\n", 1)[1]))
    old_blocks, current_blocks = blocks(historical), blocks(current)
    for job in ("python-offline", "python-no-rust", "rust", "viewer"):
        assert current_blocks[job] == old_blocks[job], job
    names = [body["name"] for body in _workflow_jobs(".github/workflows/tests.yml").values()]
    for name in ("Python bounded offline", "Python no-Rust", "Python native execution", "Rust", "Python native", "Viewer"):
        assert names.count(name) == 1, name


def test_standard_native_graph_requires_both_shards_and_rust_without_failure_allowance():
    jobs = _workflow_jobs(".github/workflows/tests.yml")
    assert set(jobs) == {"python-offline", "python-no-rust", "python-native-build", "python-native-tests", "python-native-shard-aggregate", "rust", "python-native", "viewer"}
    shards = jobs["python-native-tests"]
    assert shards["needs"] == ["python-native-build"]
    assert shards["strategy"] == {"fail-fast": "false", "matrix": {"shard": ["0", "1"]}}
    aggregate = jobs["python-native-shard-aggregate"]
    assert aggregate["if"] == "always()"
    assert aggregate["needs"] == ["python-native-build", "python-native-tests"]
    barrier = aggregate["steps"][0]
    assert barrier["env"] == {"BUILD_RESULT": "${{ needs.python-native-build.result }}", "SHARD_RESULT": "${{ needs.python-native-tests.result }}"}
    assert barrier["run"].splitlines() == ['test "$BUILD_RESULT" = success', 'test "$SHARD_RESULT" = success']
    summary = jobs["python-native"]
    assert summary["if"] == "always()"
    assert summary["needs"] == ["python-native-shard-aggregate", "rust"]
    assert summary["steps"][0]["env"] == {"PYTHON_RESULT": "${{ needs.python-native-shard-aggregate.result }}", "RUST_RESULT": "${{ needs.rust.result }}"}
    assert summary["steps"][0]["run"].splitlines() == ['test "$PYTHON_RESULT" = success', 'test "$RUST_RESULT" = success']
    for name, body in jobs.items():
        assert "continue-on-error" not in body, name
        for step in body["steps"]:
            assert "continue-on-error" not in step, (name, step["name"])


def test_standard_native_delegation_keeps_the_qualified_v2_bodies():
    from copy import deepcopy

    jobs = _workflow_jobs(".github/workflows/tests.yml")
    qualified = _workflow_jobs("docs/workflows/native-two-shards-v2.yml.in")
    for name in ("python-native-build", "python-native-tests", "python-native-shard-aggregate", "python-native"):
        expected = deepcopy(qualified[name])
        branch_guard = expected.pop("if")
        assert "refs/heads/lead/native-two-shard-qualification-v2-20261029" in branch_guard
        if name in ("python-native-shard-aggregate", "python-native"):
            expected["if"] = "always()"
        if name == "python-native-shard-aggregate":
            expected["name"] = "Python native execution"
        assert jobs[name] == expected, name
    builder_names = [s["name"] for s in jobs["python-native-build"]["steps"]]
    assert builder_names.index("Check turn-wrapper contracts before the full suite") < builder_names.index("Build Rust extension wheel") < builder_names.index("Record the verified current-producer native wheel")


def test_standard_push_does_not_duplicate_closed_qualification_workflows():
    current = yaml.load(_read(".github/workflows/tests.yml"), Loader=yaml.BaseLoader)
    assert current["on"]["pull_request"] == ""
    assert current["on"]["workflow_dispatch"] == ""
    ordinary = current["on"]["push"]["branches"]
    assert "main" in ordinary
    assert all(not any(char in branch for char in "*?![") for branch in ordinary)
    for suffix, branch in (("", "lead/native-two-shard-qualification-20261029"), ("-v2", "lead/native-two-shard-qualification-v2-20261029")):
        path = f".github/workflows/native-two-shards{suffix}.yml"
        closed = yaml.load(_read(path), Loader=yaml.BaseLoader)
        assert closed["on"] == {"push": {"branches": [branch], "paths": [path]}, "workflow_dispatch": ""}
        assert branch not in ordinary
        assert all(f"github.ref == 'refs/heads/{branch}'" in job["if"] for job in closed["jobs"].values())
