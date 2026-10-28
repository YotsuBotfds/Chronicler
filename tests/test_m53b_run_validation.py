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


@pytest.mark.parametrize("parallel, workers", [("0", 0), ("1", 1), ("3", 3), ("12", 12), (None, 3)])
def test_gate_runner_parallel_is_the_batch_worker_count(monkeypatch, tmp_path, parallel, workers):
    from chronicler.batch import parallel_workers
    from chronicler.main import _build_parser

    runner = _load_runner()
    monkeypatch.setattr(runner, "automatic_workers", lambda: 3)
    commands = []

    class Stop(Exception):
        pass

    real_run_subset = runner.run_subset

    def batch_only(args, cwd, env):
        real_run_subset(args, cwd, env)
        raise Stop

    monkeypatch.setattr(runner, "_run", lambda cmd, cwd, env: commands.append(cmd))
    monkeypatch.setattr(runner, "run_subset", batch_only)
    argv = ["m53b", "--profile", "subset", "--output-root", str(tmp_path / "gate")]
    monkeypatch.setattr(sys, "argv", argv + (["--parallel", parallel] if parallel else []))
    with pytest.raises(Stop):
        runner.main()
    [cmd] = commands
    cli = _build_parser().parse_args(cmd[cmd.index("chronicler.main") + 1:])
    assert cli.parallel == workers
    if workers:
        assert parallel_workers(cli.parallel, cpu_count=64) == workers


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


def test_validate_batch_synthesizes_evidence_for_strict_json_violations(monkeypatch, tmp_path):
    runner = _load_runner()

    for stdout_text, expected_reason in (
        ('{"results": {"needs": {"status": "PASS"}}, "metric": NaN}', "non-finite JSON constant"),
        ('{"results": {"needs": {"status": "FAIL"}, "needs": {"status": "PASS"}}}', "duplicate JSON key: needs"),
    ):
        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=stdout_text, stderr="")

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        result = runner.validate_batch(tmp_path, f"{expected_reason.split()[0]}.json", Path.cwd(), {}, "full")
        report = runner.json.loads(result["report_path"].read_text(encoding="utf-8"))
        assert report["status"] == "ERROR"
        assert expected_reason in report["reason"]
        assert result["decision"]["ok"] is False
        assert '"metric": NaN' not in result["report_path"].read_text(encoding="utf-8")


def test_validate_batch_writes_comparison_artifacts_when_baseline_is_provided(monkeypatch, tmp_path):
    runner = _load_runner()
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
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(baseline), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=runner.json.dumps(current), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.validate_batch(
        tmp_path,
        "current.json",
        Path.cwd(),
        {},
        "full",
        baseline_report=baseline_path,
        fail_on_regression=True,
    )

    assert result["decision"]["ok"] is True
    assert result["comparison"]["regression_detected"] is True
    assert result["comparison"]["exit_code"] == 2
    assert result["comparison_path"].name == "compare_decision_full.json"
    assert result["comparison_summary_path"].name == "compare_summary_full.md"
    assert runner.json.loads(result["comparison_path"].read_text(encoding="utf-8"))["regression_reasons"] == [
        "strict_regression_downgrade",
        "strict_regression_failed_checks_added",
    ]
    assert "strict_regression_downgrade" in result["comparison_summary_path"].read_text(encoding="utf-8")


def test_main_writes_comparison_manifest_and_exits_on_fail_on_regression(monkeypatch, tmp_path):
    runner = _load_runner()
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
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(baseline), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=runner.json.dumps(current), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "run_full", lambda args, cwd, env: tmp_path)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "m53b_run_validation.py",
            "--profile",
            "full",
            "--no-ablation-oracles",
            "--output-root",
            str(tmp_path.parent),
            "--baseline-report",
            str(baseline_path),
            "--fail-on-regression",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2

    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["gate_status"] == "PASS"
    assert manifest["comparison_status"] == "REGRESSION"
    assert manifest["comparison_exit_code"] == 2
    assert manifest["comparison_reasons"] == [
        "strict_regression_downgrade",
        "strict_regression_failed_checks_added",
    ]
    assert Path(manifest["comparison_path"]).exists()
    assert Path(manifest["comparison_summary_path"]).exists()


def test_main_records_comparison_regression_without_failing_unless_requested(monkeypatch, tmp_path):
    runner = _load_runner()
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
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(baseline), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=runner.json.dumps(current), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "run_full", lambda args, cwd, env: tmp_path)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "m53b_run_validation.py",
            "--profile",
            "full",
            "--no-ablation-oracles",
            "--output-root",
            str(tmp_path.parent),
            "--baseline-report",
            str(baseline_path),
        ],
    )

    runner.main()

    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["comparison_status"] == "REGRESSION"
    assert manifest["comparison_exit_code"] == 0
    assert manifest["gate_exit_code"] == 0


def test_main_records_optional_regression_diagnostics_as_no_regression_for_subset(monkeypatch, tmp_path):
    runner = _load_runner()
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
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(baseline), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=runner.json.dumps(current), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "run_subset", lambda args, cwd, env: tmp_path)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "m53b_run_validation.py",
            "--profile",
            "subset",
            "--no-ablation-oracles",
            "--output-root",
            str(tmp_path.parent),
            "--baseline-report",
            str(baseline_path),
            "--fail-on-regression",
        ],
    )

    runner.main()

    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    comparison = runner.json.loads(Path(manifest["comparison_path"]).read_text(encoding="utf-8"))
    assert manifest["comparison_status"] == "NO_REGRESSION"
    assert manifest["comparison_exit_code"] == 0
    assert manifest["comparison_reasons"] == []
    assert comparison["strict_regression_downgrade"] is True
    assert comparison["strict_regression_failed_checks_added"] == ["latest_satisfaction_mean"]


def test_main_rejects_fail_on_regression_without_baseline(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(
        runner.sys,
        "argv",
        ["m53b_run_validation.py", "--profile", "full", "--fail-on-regression"],
    )

    with pytest.raises(SystemExit) as exc_info:
        runner.main()

    assert exc_info.value.code == 2


def test_validate_batch_rejects_baseline_output_collision_before_overwrite(monkeypatch, tmp_path):
    runner = _load_runner()
    current_path = tmp_path / "current.json"
    current_path.write_text("baseline-original", encoding="utf-8")

    def fake_run(*args, **kwargs):  # pragma: no cover - should not be reached
        raise AssertionError("validation subprocess should not run after unsafe baseline collision")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(runner.ValidationGateInputError, match="baseline-report must be different"):
        runner.validate_batch(
            tmp_path,
            "current.json",
            Path.cwd(),
            {},
            "full",
            baseline_report=current_path,
        )
    assert current_path.read_text(encoding="utf-8") == "baseline-original"


def test_main_preserves_manifest_when_comparison_input_becomes_bad_and_gate_fails(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(_report(regression="FAIL", determinism="SKIP"))
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(_report(determinism="SKIP")), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    def run_full_with_changed_baseline(args, cwd, env):
        baseline_path.write_text("not-json", encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(runner, "run_full", run_full_with_changed_baseline)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "m53b_run_validation.py",
            "--profile",
            "full",
            "--no-ablation-oracles",
            "--output-root",
            str(tmp_path.parent),
            "--baseline-report",
            str(baseline_path),
            "--require-strict-regression",
            "--fail-on-regression",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2

    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["gate_status"] == "FAIL"
    assert manifest["gate_exit_code"] == 2
    assert manifest["comparison_status"] == "ERROR"
    assert manifest["comparison_exit_code"] == 1
    assert "invalid report JSON" in manifest["comparison_error"]
    comparison = runner.json.loads(Path(manifest["comparison_path"]).read_text(encoding="utf-8"))
    assert comparison["require_strict_regression"] is True
    assert Path(manifest["comparison_summary_path"]).exists()


def test_main_exits_one_when_gate_passes_but_comparison_input_becomes_bad(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(_report(determinism="SKIP"))
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(_report(determinism="SKIP")), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    def run_full_with_changed_baseline(args, cwd, env):
        baseline_path.write_text("not-json", encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(runner, "run_full", run_full_with_changed_baseline)
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "m53b_run_validation.py",
            "--profile",
            "full",
            "--no-ablation-oracles",
            "--output-root",
            str(tmp_path.parent),
            "--baseline-report",
            str(baseline_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 1
    manifest = runner.json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["gate_status"] == "PASS"
    assert manifest["comparison_status"] == "ERROR"


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
        ["m53b_run_validation.py", "--profile", "full", "--no-ablation-oracles", "--output-root", str(tmp_path.parent)],
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


def test_validate_batch_scores_the_needs_oracle_for_its_profile(monkeypatch, tmp_path):
    runner = _load_runner()
    report_text = runner.json.dumps(_report(determinism="SKIP"))
    commands = []

    def fake_run(*args, **kwargs):
        commands.append(list(args[0]))
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=report_text, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    for profile in ("subset", "full"):
        runner.validate_batch(tmp_path, f"{profile}.json", Path.cwd(), {}, profile)
    assert [cmd[cmd.index("--profile") + 1] for cmd in commands] == ["subset", "full"]
    assert all(cmd[cmd.index("-m") + 1] == "chronicler.validate" for cmd in commands)


# --- Fresh batch directories and manifests (validation-integrity) --------


def test_main_refuses_a_used_batch_directory_before_running(monkeypatch, tmp_path):
    runner = _load_runner()
    used = tmp_path / "oracle_subset" / "batch_42" / "seed_42"
    used.mkdir(parents=True)

    def must_not_run(*args, **kwargs):
        raise AssertionError("the subset must not run into a used directory")

    monkeypatch.setattr(runner, "run_subset", must_not_run)
    monkeypatch.setattr(runner.sys, "argv", ["m53b_run_validation.py", "--profile", "subset", "--output-root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2


def test_profile_batch_dirs_match_the_runs(tmp_path):
    runner = _load_runner()
    args = runner.argparse.Namespace(output_root=tmp_path, seed_start=7)
    for profile, expected in (
        ("subset", tmp_path / "oracle_subset" / "batch_7"),
        ("full", tmp_path / "full_gate" / "batch_7"),
        ("determinism-off", tmp_path / "determinism_off" / "batch_42"),
        ("determinism-hybrid", tmp_path / "determinism_hybrid" / "batch_42"),
    ):
        args.profile = profile
        assert runner._profile_batch_dir(args) == expected


def test_determinism_pair_gets_a_manifest(monkeypatch, tmp_path):
    from chronicler.validation_io import check_batch_manifest

    runner = _load_runner()

    def fake_run(cmd, cwd, env):
        seed_dir = Path(cmd[cmd.index("--output") + 1]).parent
        bundle = {"metadata": {"seed": 42, "total_turns": int(cmd[cmd.index("--turns") + 1])}}
        (seed_dir / "chronicle_bundle.json").write_text(runner.json.dumps(bundle), encoding="utf-8")

    monkeypatch.setattr(runner, "_run", fake_run)
    args = runner.apply_profile_defaults(runner.argparse.Namespace(
        profile="determinism-hybrid", output_root=tmp_path, seeds=None, turns=None, worldgen="template",
        regions=None, civs=None, campaigns=None, cities=False, seed_start=42,
    ))
    batch_dir = runner.run_determinism(args, tmp_path, {}, "hybrid")
    manifest = runner.json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["seeds"] == [42, 42]
    assert [(run["dir"], run["total_turns"]) for run in manifest["runs"]] == [("seed_42_a", 200), ("seed_42_b", 200)]
    assert (manifest["simulation"]["agents"], manifest["simulation"]["cities"]) == ("hybrid", False)
    assert check_batch_manifest(batch_dir)["seeds"] == [42, 42]
    # A second pair into the same directory is refused.
    with pytest.raises(runner.BatchDestinationError):
        runner.run_determinism(args, tmp_path, {}, "hybrid")


@pytest.mark.parametrize("exploratory", [False, True])
def test_main_compares_other_cohorts_only_when_exploratory(monkeypatch, tmp_path, exploratory):
    runner = _load_runner()

    def cohort(seeds):
        report = _report(determinism="SKIP")
        report["results"]["regression"]["final_living_population_by_seed"] = [
            {"seed": seed, "population": 100, "turn": 200} for seed in seeds
        ]
        return report

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(runner.json.dumps(cohort(range(42, 142))), encoding="utf-8")
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=runner.json.dumps(cohort([42])), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "run_subset", lambda args, cwd, env: batch_dir)
    argv = ["m53b_run_validation.py", "--profile", "subset", "--no-ablation-oracles", "--output-root", str(tmp_path / "out"),
            "--baseline-report", str(baseline_path)]
    monkeypatch.setattr(runner.sys, "argv", argv + (["--exploratory-comparison"] if exploratory else []))
    if exploratory:
        runner.main()
    else:
        with pytest.raises(SystemExit) as exc_info:
            runner.main()
        assert exc_info.value.code == 1
    manifest = runner.json.loads((batch_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if exploratory:
        assert manifest["comparison_status"] == "EXPLORATORY_NO_REGRESSION"
        assert manifest["exploratory_comparison"] is True
    else:
        assert manifest["comparison_status"] == "ERROR"
        assert "different cohorts" in manifest["comparison_error"]


@pytest.mark.parametrize(
    "profile", ("subset", "full", "determinism-off", "determinism-hybrid"),
)
@pytest.mark.parametrize(
    "baseline_kind",
    ("missing", "directory", "invalid-json", "array", "duplicate-key", "non-finite", "overflow"),
)
def test_main_rejects_unreadable_baseline_before_simulation(
    monkeypatch, tmp_path, capsys, profile, baseline_kind,
):
    runner = _load_runner()
    baseline_path = tmp_path / "baseline.json"
    if baseline_kind == "directory":
        baseline_path.mkdir()
    elif baseline_kind != "missing":
        contents = {
            "invalid-json": "not-json",
            "array": "[]",
            "duplicate-key": '{"results": {}, "results": {}}',
            "non-finite": '{"value": NaN}',
            "overflow": '{"value": 1e9999}',
        }
        baseline_path.write_text(contents[baseline_kind], encoding="utf-8")
    output_root = tmp_path / "runs"
    launches = []

    def forbidden(*args, **kwargs):
        launches.append((args, kwargs))
        raise AssertionError("invalid baseline must be rejected before simulation or child launch")

    for name in ("run_subset", "run_full", "run_determinism", "run_arms", "validate_batch", "_run"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    monkeypatch.setattr(runner.sys, "argv", [
        "m53b_run_validation.py", "--profile", profile, "--parallel", "1",
        "--output-root", str(output_root), "--baseline-report", str(baseline_path),
    ])
    with pytest.raises(SystemExit) as exc_info:
        runner.main()
    assert exc_info.value.code == 2
    assert "--baseline-report:" in capsys.readouterr().err
    assert launches == []
    assert not output_root.exists()
