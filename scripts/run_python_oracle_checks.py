"""Run the bounded offline Python oracle gate, independently of local native installs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/test_adjacency.py",
    "tests/test_politics.py",
    "tests/test_action_engine.py",
    "tests/test_politics_bridge.py::TestApplyPoliticsOps",
    "tests/test_politics_bridge.py::TestOraclePreservation",
    "tests/test_agents_off_determinism.py",
    "tests/test_validate.py",
    "tests/test_validation_split_imports.py",
    "tests/test_utils_civ_helpers.py",
    "tests/test_climate.py",
    "tests/test_ecology.py",
    "tests/test_intelligence.py",
    "tests/test_hostage_intelligence_lifecycle.py",
    "tests/test_performance_equivalence.py",
    "tests/test_analytics.py",
    "tests/test_simulation.py::TestAutomaticEffects",
    "tests/test_severity.py::TestSeverityAtWarBankruptcy",
    "tests/test_native_extension_fallbacks.py::test_ecology_tick_without_runtime_recovers_soil_without_native_extension",
    "tests/test_save_directory.py",
    "tests/test_memory.py",
    "tests/test_models.py",
    "tests/test_leaders.py",
    "tests/test_tuning.py",
    "tests/test_schisms.py",
    "tests/test_turn_artifact_views.py",
    "tests/test_resources.py",
    "tests/test_world_gen.py",
    "tests/test_scenario.py",
    "tests/test_emergence.py::TestResourceDiscovery",
    "tests/test_bundle.py::TestBundleAssembly",
    "tests/test_bundle.py::TestViewerFixtureContract",
    "tests/test_main.py::TestRunChronicle",
    "tests/test_main.py::TestRunChronicleWithScenario",
    "tests/test_main.py::TestExecuteRun",
    "tests/test_main.py::TestNewCLIFlags",
    "tests/test_main.py::TestMutualExclusions",
    "tests/test_main.py::TestAgentsFlag",
    "tests/test_main.py::TestNarratorArgument",
    "tests/test_main.py::TestNarratorValidation",
    "tests/test_main.py::test_goal_enrichment_failure_logs_warning",
    "tests/test_main.py::test_llm_actions_logs_deprecation_warning",
    "tests/test_main.py::test_on_turn_callback_fires_each_turn",
    "tests/test_main.py::test_quit_check_stops_simulation_early",
    "tests/test_main.py::test_compare_without_analyze_rejected",
    "tests/test_main.py::test_narrate_output_without_narrate_rejected",
    "tests/test_main.py::TestApiNarrationIntegration::test_api_mode_produces_curated_entries_with_metadata",
    "tests/test_main.py::TestApiNarrationIntegration::test_run_narrate_api_mode_writes_metadata",
    "tests/test_fork.py",
    "tests/test_m10_integration.py::TestForkFromBatch",
    "tests/test_m10_integration.py::TestMemoryPersistenceInRun",
    "tests/test_m19_integration.py::TestM19Integration::test_batch_then_analyze",
    "tests/test_m19_integration.py::TestM19Integration::test_tuning_overrides_in_batch",
    "tests/test_bundle.py::TestWriteBundle",
    "tests/test_bundle.py::TestSnapshotCapture",
    "tests/test_bundle.py::TestArcSummaryIsolation",
    "tests/test_bundle.py::TestTransientSerializationHygiene",
    "tests/test_checkpoint_replay.py",
    "tests/test_m15_integration.py::TestM15Integration::test_20_turn_smoke_test",
    "tests/test_import_compatibility.py",
    "tests/test_institutions.py",
    "tests/test_elite_metrics.py",
    "tests/test_governance_capital.py",
    "tests/test_ruler_ambitions.py",
    "tests/test_governance_kernel_harness.py",
    "tests/test_governance_dormancy.py",
    "tests/test_bridge_contract.py",
    "tests/test_diplomacy.py",
    "tests/test_techniques.py",
    "tests/test_maritime.py",
    "tests/test_gp_agendas.py",
    "tests/test_nomads.py",
    "tests/test_snapshot_pruning.py",
    "tests/test_historiography.py"
]
EXCLUDED = "Cross-process determinism/replay, POSIX persistence, native and broader socket/subprocess suites"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--list", action="store_true", help="Print selected pytest node IDs without executing")
parser.add_argument("--output-dir", type=Path, help="New evidence directory (default: ignored output/python-oracle/<UTC timestamp>)")
args = parser.parse_args()
if args.list:
    print("\n".join(TESTS))
    raise SystemExit(0)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
out = (args.output_dir or ROOT / "output/python-oracle" / stamp).resolve()
out.mkdir(parents=True, exist_ok=False)
guard_report = out / "guard.json"
env = {key: value for key, value in os.environ.items() if key.upper() in {
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATH", "PATHEXT",
    "LOCALAPPDATA", "APPDATA", "USERPROFILE", "LANG", "LC_ALL",
}}
env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONHASHSEED="0",
           PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", OMP_NUM_THREADS="1",
           OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
           PYTHONPATH=os.pathsep.join(map(str, [ROOT / "src", ROOT, ROOT / "scripts/testing"])),
           CHRONICLER_OFFLINE_GUARD_REPORT=str(guard_report))
command = [sys.executable, "-B", "-m", "pytest", "-q", "-x", "--tb=short", *TESTS,
           "-p", "python_oracle_guard", "-p", "no:cacheprovider", "--basetemp", str(out / "pytest"),
           "-k", "not test_real_cli_and_cross_process_resume_with_different_hashseeds and not test_cross_process_deterministic_with_randomized_python_hash_seed"]
sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
           for folder in ("src/chronicler", "scripts/testing")
           for path in sorted((ROOT / folder).rglob("*.py"))}
for selected in TESTS:
    path = ROOT / selected.split("::", 1)[0]
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
git = ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT)]
head = subprocess.check_output(git + ["rev-parse", "HEAD"], timeout=10).decode().strip()
start = time.monotonic()
report = {"at_utc": stamp, "commit": head, "python": sys.version, "command": command,
          "source_sha256": sources, "excluded": EXCLUDED,
          "environment_policy": "Runtime-path allowlist; no inherited provider credentials; one-thread caps"}
try:
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=110)
    (out / "pytest.txt").write_bytes(result.stdout)
    guard = json.loads(guard_report.read_text(encoding="utf-8"))
    report.update(exit_code=result.returncode, guard=guard,
                  passed=result.returncode == 0 and guard["state"] == "PASS")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(result.stdout.decode("utf-8", errors="replace"), end="")
except subprocess.TimeoutExpired as error:
    (out / "pytest.txt").write_bytes(error.stdout or b"")
    report.update(exit_code=1, passed=False, error="110-second test limit exceeded")
finally:
    report["seconds"] = time.monotonic() - start
    (out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"Evidence: {out}")
raise SystemExit(0 if report.get("passed") else 1)
