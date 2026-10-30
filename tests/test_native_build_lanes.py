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


def _project_only_reviewed_disabled_native_cache(text):
    """Remove only four exact reviewed flag0 additions inside the builder job."""
    from hashlib import sha256

    assert text.count("  python-native-build:\n") == 1
    prefix, tail = text.split("  python-native-build:\n", 1)
    following = re.search(r"(?m)^  [\w-]+:\n", tail)
    assert following is not None
    builder, suffix = tail[:following.start()], tail[following.start():]
    assert "NATIVE_RELEASE_CACHE_" not in prefix + suffix
    assert builder.count('CHRONICLER_NATIVE_RELEASE_CACHE: "0"') == 1
    reviewed = {'DEFAULT': '2500c4489fea62d1116a5cb520d35d87ec178212a1451662e68e38a4dfbf5286', 'OLD_RESTORE': '78a91fb4e9b26fd61ec1c305dbb4e89d4ab9d1528133f27e3e432179ce354751', 'PREPARE': 'dbae689b85d8ac5b04f57cd75679e9daafe696e005f13b0e218276ef32dc356c', 'SEAL': '742f236f6e54dc43c6c9b46604467ec2e31b61ca17724a42cd50ac63f56db810'}
    lines = builder.splitlines(keepends=True)
    for marker, expected in reviewed.items():
        begin = "# NATIVE_RELEASE_CACHE_" + marker + "_BEGIN"
        end = "# NATIVE_RELEASE_CACHE_" + marker + "_END"
        starts = [i for i, line in enumerate(lines) if line.strip() == begin]
        ends = [i for i, line in enumerate(lines) if line.strip() == end]
        assert len(starts) == len(ends) == 1 and starts[0] < ends[0]
        stop = ends[0] + 1
        if marker in ("PREPARE", "SEAL"):
            assert lines[stop] == "\n"
            stop += 1
        block = "".join(lines[starts[0]:stop])
        assert sha256(block.encode("utf-8")).hexdigest() == expected
        del lines[starts[0]:stop]
    projected = "".join(lines)
    assert "CHRONICLER_NATIVE_RELEASE_CACHE" not in projected
    return prefix + "  python-native-build:\n" + projected + suffix


def test_standard_native_delegation_keeps_the_qualified_v2_bodies():
    from copy import deepcopy

    current = _read(".github/workflows/tests.yml")
    projected = _project_only_reviewed_disabled_native_cache(current)
    jobs = yaml.load(projected, Loader=yaml.BaseLoader)["jobs"]
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

    # Unrelated legacy mutations remain visible after the exact projection.
    mutated = current.replace("Build Rust extension wheel", "Unrelated mutated build step", 1)
    assert mutated != current
    changed_jobs = yaml.load(_project_only_reviewed_disabled_native_cache(mutated), Loader=yaml.BaseLoader)["jobs"]
    assert changed_jobs["python-native-build"] != jobs["python-native-build"]
    for changed in (
        current.replace('CHRONICLER_NATIVE_RELEASE_CACHE: "0"', 'CHRONICLER_NATIVE_RELEASE_CACHE: "1"', 1),
        current.replace("Prepare dormant exact native cache context", "Unreviewed dormant cache context", 1),
    ):
        assert changed != current
        try:
            _project_only_reviewed_disabled_native_cache(changed)
        except AssertionError:
            pass
        else:
            raise AssertionError("unreviewed cache shape was projected away")


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


def test_validation_workflow_selects_full_source_sha_and_world_family():
    workflow = _read(".github/workflows/validation-gate.yml")
    inputs = yaml.load(workflow, Loader=yaml.BaseLoader)["on"]["workflow_dispatch"]["inputs"]
    assert inputs["source_sha"]["default"] == ""
    assert inputs["worldgen"]["default"] == "template"
    assert inputs["worldgen"]["options"] == ["template", "procedural"]
    assert '^[0-9a-f]{40}$' in workflow
    assert 'ref: ${{ steps.validation_source.outputs.sha }}' in workflow
    assert '--worldgen "$WORLDGEN_INPUT"' in workflow and '--parallel 3' in workflow


def test_validation_workflow_records_actual_source_and_own_compiled_wheel():
    workflow = _read(".github/workflows/validation-gate.yml")
    assert 'VALIDATION_CONTROLLER_SHA: ${{ github.workflow_sha }}' in workflow
    assert '"checked_out_source_sha": source' in workflow and '"controller_sha":' in workflow
    assert 'type(native.__spec__.loader) is ExtensionFileLoader' in workflow
    assert 'getattr(package, name, None) is getattr(native, name)' in workflow
    assert 'receipt = wheel_receipt(' in workflow
    assert 'manifest["native"]["sha256"] == identity["wheel_receipt"]["installed_native"]["sha256"]' in workflow
    assert 'GITHUB_SHA=' not in workflow and 'GITHUB_JOB=' not in workflow
    assert 'native_ci_shards.py record-build' not in workflow


def test_validation_workflow_keeps_raw_upload_and_bounded_compact_evidence():
    workflow = _read(".github/workflows/validation-gate.yml")
    steps = yaml.load(workflow, Loader=yaml.BaseLoader)["jobs"]["canonical-validation"]["steps"]
    raw = next(step for step in steps if step["name"] == "Upload validation reports")
    assert raw["if"] == "always()"
    assert raw["with"]["path"] == 'output/github-validation/${{ github.run_id }}'
    assert raw["with"]["retention-days"] == "30"
    compact = next(step for step in steps if step["name"] == "Upload compact validation evidence")
    assert compact["if"] == "always()" and compact["with"]["retention-days"] == "30"
    assert 'MAX_COMPACT_BYTES = 7 * 1024 * 1024' in workflow
    assert 'REFUSED_COMPACT_SIZE' in workflow and 'compact_manifest.json' in workflow
    assert 'batch_manifest.json' in workflow and 'ablation_manifest.json' in workflow
    assert 'frames' not in compact["with"]["path"]


def test_validation_workflow_retains_profile_defaults_and_explicit_comparison_policy():
    workflow = _read(".github/workflows/validation-gate.yml")
    run = _read("scripts/m53b_run_validation.py")
    assert '"full": {"seeds": 200, "turns": 500}' in run
    assert '"full": {"seeds": 100, "turns": 300}' in run
    assert '"regions": 32, "civs": 10' in run
    assert '--seeds' not in workflow and '--turns' not in workflow
    assert '--exploratory-comparison' not in workflow
    assert 'baseline_report:' in workflow and '--baseline-report "$BASELINE_REPORT"' in workflow
    assert '--require-strict-regression' in workflow and '--fail-on-regression' in workflow


def _validation_resource_policy_for_test():
    steps = yaml.load(_read(".github/workflows/validation-gate.yml"), Loader=yaml.BaseLoader)["jobs"]["canonical-validation"]["steps"]
    step = next(row for row in steps if row["name"] == "Admit resources before World")
    source = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    parsed = ast.parse(source)
    function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "assess_resource_policy")
    # Execute only the pure counter policy with fakes. None of the inline OS,
    # native, file, build or World collection statements are in this module.
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<validation-resource-policy>", "exec"), namespace)
    return namespace["assess_resource_policy"]


def _validation_resource_fake_counters():
    return {"host_available_memory_bytes": 16 * 1024**3,
            "memory_headroom_bytes": [8 * 1024**3],
            "cpu_slot_limits": [8, 8, 3], "output_free_bytes": 16 * 1024**3,
            "output_free_inodes": 100000, "errors": []}


def test_validation_resource_policy_accepts_exact_boundaries_without_measuring_fit():
    policy = _validation_resource_policy_for_test()
    counters = _validation_resource_fake_counters()
    before = repr(counters)
    result = policy(counters)
    assert result["admitted"] and all(result["checks"].values())
    assert result["effective_counters"]["available_memory_bytes"] == 8 * 1024**3
    assert result["effective_counters"]["effective_cpu_slots"] == 3
    assert result["bounds"] == {"available_memory_bytes": 8 * 1024**3,
        "output_free_bytes": 16 * 1024**3, "output_free_inodes": 100000, "effective_cpu_slots": 3}
    assert result["measured_source_fit"] is False and repr(counters) == before


def test_validation_resource_policy_refuses_low_unknown_and_cgroup_limited_counters():
    policy = _validation_resource_policy_for_test()
    # Each literal exercises a different policy boundary without an OS probe.
    changes = [
        ("host", {"host_available_memory_bytes": 8 * 1024**3 - 1}),
        ("ancestor-headroom", {"memory_headroom_bytes": [64 * 1024**3, 8 * 1024**3 - 1]}),
        ("quota", {"cpu_slot_limits": [16, 16, 2]}),
        ("affinity", {"cpu_slot_limits": [16, 2, 16]}),
        ("disk", {"output_free_bytes": 16 * 1024**3 - 1}),
        ("inodes", {"output_free_inodes": 99999}),
        ("unknown", {"host_available_memory_bytes": None}),
        ("boolean", {"output_free_inodes": True}),
        ("unreadable", {"errors": ["cgroup-read-denied"]}),
    ]
    for name, changed in changes:
        counters = _validation_resource_fake_counters()
        counters.update(changed)
        result = policy(counters)
        assert not result["admitted"], name
        assert result["measured_source_fit"] is False, name


def test_validation_resource_admission_is_before_world_and_bound_to_compact_evidence():
    workflow = _read(".github/workflows/validation-gate.yml")
    steps = yaml.load(workflow, Loader=yaml.BaseLoader)["jobs"]["canonical-validation"]["steps"]
    names = [step["name"] for step in steps]
    assert names.index("Record actual validation source and own compiled wheel") < names.index("Admit resources before World") < names.index("Run canonical validation gate")
    resource = next(step for step in steps if step["name"] == "Admit resources before World")
    assert "continue-on-error" not in resource
    assert 'from chronicler.cpu_budget import _cgroup_limits' in resource["run"]
    assert 'os.O_EXCL | os.O_NOFOLLOW' in resource["run"] and 'os.fsync' in resource["run"]
    assert resource["run"].index('os.fchmod(stream.fileno(), 0o444)') < resource["run"].index('if not decision["admitted"]:')
    assert '"resource_admission.json"' in workflow and '"resource_admission_sha256"' in workflow
    assert '"build_identity_sha256"' in resource["run"]
