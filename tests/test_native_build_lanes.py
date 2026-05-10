"""Regression tests for documented no-Rust/native build and test lanes."""

from pathlib import Path
import tomllib


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


def test_validation_gate_workflow_builds_native_extension_as_wheel():
    workflow = _read(".github/workflows/validation-gate.yml")

    assert "python -m maturin build --release" in workflow
    assert "python -m pip install target/wheels/*.whl" in workflow
    assert "python -m maturin develop --release" not in workflow


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


def test_github_tests_workflow_has_no_rust_and_native_jobs():
    workflow = _read(".github/workflows/tests.yml")

    assert "python-no-rust" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "python-native" in workflow
    assert "Assert native extension is absent" in workflow
    assert "Run Python tests with real native extension preloaded" in workflow
    assert "python -m maturin build --release" in workflow
    assert "python -m pip install target/wheels/*.whl" in workflow
    assert "EXTENSION_SUFFIXES" in workflow
    assert "find_spec(\"chronicler_agents.chronicler_agents\")" in workflow
    assert workflow.index("import chronicler_agents as ca") < workflow.index("import pytest")
    assert "python -m maturin develop --release" not in workflow
