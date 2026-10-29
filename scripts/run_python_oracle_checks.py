"""Run the bounded offline Python oracle gate, independently of local native installs.

The selection runs in chunks. Each chunk is its own pytest process under the
offline guard, with its own guard receipt and the same time limit; the runner
stops at the first failing chunk. When a chunk nears its limit, move files to
another chunk or start a new one instead of raising the limit.
"""
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
CHUNK_LIMIT_SECONDS = 110
CHUNKS = {
    "arc-event-types": [
        "tests/test_arc_event_types.py",
    ],
    "diagnostics": [
        "tests/test_community_admissibility.py::test_decomposes_saved_counters_without_changing_report_or_verdict",
        "tests/test_community_admissibility.py::test_capacity_does_not_imply_region_share_pass",
        "tests/test_community_admissibility.py::test_empty_exposure_never_becomes_a_pass",
        "tests/test_community_admissibility.py::test_missing_legacy_future_or_skipped_evidence_is_unavailable",
        "tests/test_community_admissibility.py::test_version_aliases_are_rejected",
        "tests/test_community_admissibility.py::test_invalid_or_inconsistent_counters_fail_closed",
        "tests/test_community_admissibility.py::test_report_cannot_claim_fewer_failures_than_mathematically_forced",
        "tests/test_community_admissibility.py::test_malformed_known_structure_is_not_missing_evidence",
        "tests/test_community_admissibility.py::test_spec_pass_cannot_contradict_recorded_share_failures",
        "tests/test_artifact_io.py::test_strict_json_loads_rejects_numeric_overflow",
        "tests/test_artifact_io.py::test_strict_json_loads_preserves_finite_numeric_semantics",
        "tests/test_artifact_io.py::test_strict_json_loads_still_rejects_invalid_numeric_syntax",
        "tests/test_factions.py::test_faction_history_queries_preserve_counts_and_resync",
        "tests/test_factions.py::test_faction_history_ties_preserve_contender_order",
        "tests/test_m53b_run_validation.py::test_main_rejects_unreadable_baseline_before_simulation",
        "tests/test_m36_regression.py::TestCultureObservationIsolation",
    ],
    "core": [
        "tests/test_adjacency.py",
        "tests/test_politics.py",
        "tests/test_action_engine.py",
        "tests/test_politics_bridge.py::TestApplyPoliticsOps",
        "tests/test_politics_bridge.py::TestOraclePreservation",
        "tests/test_agents_off_determinism.py",
        "tests/test_validate.py",
        "tests/test_procedural_gates.py",
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
    ],
    "governance": [
        "tests/test_institutions.py",
        "tests/test_elite_metrics.py",
        "tests/test_governance_capital.py",
        "tests/test_ruler_ambitions.py",
        "tests/test_governance_kernel_harness.py",
        "tests/test_governance_dormancy.py",
        "tests/test_bridge_contract.py",
    ],
    "systems-1": [
        "tests/test_diplomacy.py",
        "tests/test_techniques.py",
        "tests/test_maritime.py",
        "tests/test_food_logistics.py",
        "tests/test_food_crisis_labels.py",
        "tests/test_migration_driver_labels.py",
        "tests/test_cities.py",
        "tests/test_city_markets.py",
        "tests/test_bulk_trade.py",
        "tests/test_guilds.py",
    ],
    "systems-2": [
        "tests/test_gp_agendas.py",
        "tests/test_nomads.py",
        "tests/test_snapshot_pruning.py",
        "tests/test_bundle_codec.py",
        "tests/test_historiography.py",
        "tests/test_languages.py",
        "tests/test_viewer_snapshot_fields.py",
        "tests/test_agent_movements.py",
        "tests/test_hunger_mortality.py",
        "tests/test_farmland_climate.py",
        "tests/test_mines_forests.py",
        "tests/test_crafts.py",
    ],
    "narration": [
        "tests/test_narration_context.py",
        "tests/test_curator.py",
        "tests/test_narrative.py",
        "tests/test_batch_narration.py",
        "tests/test_chronicle.py",
        "tests/test_historical_parity.py",
        "tests/test_narration_provenance.py",
    ],
    "history-forensics": [
        "tests/test_history_forensics.py",
    ],
    "expansion-audit": [
        "tests/test_expansion_audit.py",
    ],
    "scientific-receipts": [
        "tests/test_scientific_receipts_audit.py",
        "tests/test_scientific_research_audit.py",
    ],
    "expansion-comparison": [
        "tests/test_expansion_compare.py",
    ],
    "proof-contracts": [
        "tests/test_scientific_research_native_proof.py",
        "tests/test_agent_bridge_stat_order.py",
    ],
    "qualification-tools": [
        "tests/test_writer_cadence_diagnostic.py",
        "tests/test_scientific_native_proof_reader.py::test_success_creates_only_new_external_output_and_keeps_inputs",
        "tests/test_scientific_native_proof_reader.py::test_any_output_inside_evidence_is_rejected_before_analysis",
        "tests/test_scientific_native_proof_reader.py::test_existing_destination_and_aliases_never_overwrite[ordinary]",
        "tests/test_scientific_native_proof_reader.py::test_unsafe_inventory_paths_are_rejected_before_output",
        "tests/test_scientific_native_proof_reader.py::test_missing_changed_unrecorded_and_unbounded_inputs_fail_closed",
        "tests/test_scientific_native_proof_reader.py::test_input_hashes_are_rechecked_before_any_output",
        "tests/test_rust_debug_info_experiment.py::test_assertions_overflow_optimization_and_debug_info_are_independent_requirements",
        "tests/test_rust_debug_info_experiment.py::test_disk_guard_stops_before_floor_while_other_workers_can_still_grow",
        "tests/test_rust_debug_info_experiment.py::test_partial_or_filtered_test_log_cannot_claim_full_qualification",
        "tests/test_rust_debug_info_experiment.py::test_successful_child_cannot_hide_a_last_write_over_storage_limit",
        "tests/test_rust_debug_info_experiment.py::test_matching_source_does_not_allow_prepare_execute_environment_drift",
        "tests/test_python_qualification.py::test_no_optional_shell_or_pytest_selection_passthrough",
        "tests/test_python_qualification.py::test_environment_removes_inherited_test_filters_and_paths",
        "tests/test_python_qualification.py::test_native_absence_does_not_accept_a_replacement_module",
        "tests/test_python_qualification.py::test_compiled_native_bytes_must_match_the_requested_hash",
        "tests/test_python_qualification.py::test_junit_must_describe_actual_executed_test_cases",
        "tests/test_python_qualification.py::test_pytest9_successful_subtests_require_matching_terminal_evidence",
        "tests/test_python_qualification.py::test_unreconciled_or_unsuccessful_subtests_cannot_earn_a_pass",
        "tests/test_python_qualification.py::test_cancel_requires_the_matching_before_test_boundary",
        "tests/test_python_qualification.py::test_cancel_refuses_any_evidence_that_tests_or_finalization_began",
        "tests/test_python_qualification.py::test_cancel_requires_a_reason_and_refuses_unsupported_signalling",
        "tests/test_python_qualification.py::test_recovered_unknown_cancellation_refuses_any_new_signal",
        "tests/test_parent_extra_archive.py::test_actual_roundtrip_preserves_every_parent_file_and_protected_input",
        "tests/test_parent_extra_archive.py::test_gzip_and_index_are_deterministic_for_identical_inputs",
        "tests/test_parent_extra_archive.py::test_unfinalized_or_inconsistent_manifest_is_refused_before_output",
        "tests/test_parent_extra_archive.py::test_manifest_input_is_never_selected_even_with_allowlisted_name",
        "tests/test_parent_extra_archive.py::test_changed_required_input_and_wrong_manifest_anchor_fail_closed",
        "tests/test_parent_extra_archive.py::test_unsafe_manifest_and_index_paths_are_refused",
        "tests/test_parent_extra_archive.py::test_outputs_are_exclusive_and_outside_all_source_inputs",
        "tests/test_parent_extra_archive.py::test_unhashed_ledger_change_during_compression_blocks_success",
        "tests/test_parent_extra_archive.py::test_manifest_change_after_actual_restore_blocks_completion",
        "tests/test_parent_extra_archive.py::test_verify_and_restore_require_the_explicit_index_hash",
        "tests/test_parent_extra_archive.py::test_trusted_index_still_cannot_restore_protected_or_escaping_names",
        "tests/test_parent_extra_archive.py::test_gzip_corruption_members_and_uncompressed_bounds_fail_closed",
        "tests/test_parent_extra_archive.py::test_restoration_survives_source_relocation_and_never_overwrites",
        "tests/test_parent_extra_archive.py::test_large_single_member_is_bounded_and_decodes_exactly",
        "tests/test_parent_extra_archive.py::test_changing_source_size_is_bounded_before_archive_can_succeed",
        "tests/test_parent_extra_archive.py::test_empty_regular_files_have_exact_restores",
        "tests/test_parent_extra_archive.py::test_parent_size_bound_is_checked_before_hashing_large_file",
        "tests/test_parent_extra_archive.py::test_entry_bound_includes_directories_and_stops_before_any_hash",
        "tests/test_parent_extra_archive.py::test_hashing_a_growing_stream_reads_only_recorded_size_plus_one",
        "tests/test_parent_extra_archive.py::test_decode_bounds_compressed_growth_after_its_initial_snapshot",
        "tests/test_parent_extra_archive.py::test_stream_writes_reserve_next_block_before_writing",
        "tests/test_parent_extra_archive.py::test_index_size_is_bounded_before_creation_with_the_same_reader_cap",
        "tests/test_parent_extra_archive.py::test_metadata_reserves_encoded_bytes_before_exclusive_creation",
        "tests/test_parent_extra_archive.py::test_oversized_metadata_never_opens_a_destination",
        "tests/test_parent_extra_archive.py::test_duplicate_index_keys_are_rejected_even_with_matching_trusted_hash",
        "tests/test_parent_extra_archive.py::test_malformed_manifest_object_or_boolean_schema_is_refused",
        "tests/test_parent_extra_archive.py::test_malformed_index_object_or_boolean_schema_is_refused",
        "tests/test_parent_extra_archive.py::test_fixed_source_and_space_bounds_refuse_before_archive_output",
        "tests/test_parent_extra_archive.py::test_no_raw_delete_or_unbounded_command_is_exposed",
    ],
    "turn-speed": [
        "tests/test_turn_speed.py",
        "tests/test_serialization_dormant_fields.py",
    ],
    "validation-tooling": [
        "tests/test_batch_manifest.py",
        "tests/test_batch_manifest_inputs.py",
        "tests/test_batch_manifest_reconciliation.py",
        "tests/test_validation_turn_index.py",
        "tests/test_batch.py",
        "tests/test_validation_gate.py",
        "tests/test_validation_compare.py",
        "tests/test_validation_ablation.py",
        "tests/test_decision_ablation.py",
        "tests/test_ablation_output.py",
        "tests/test_spec_communities.py",
    ],
    "learning": [
        "tests/test_scholarship.py",
    ],
    "population": [
        "tests/test_population_conservation.py",
        "tests/test_population_entities_native.py",
    ],
    "production-ledger": [
        "tests/test_production_ledger.py",
        "tests/test_production_ledger_native.py",
    ],
    "refugee-routing": [
        "tests/test_refugee_routing.py",
    ],
    "checkpoint": [
        "tests/test_run_checkpoint.py",
        "tests/test_run_checkpoint_native.py",
    ],
    "live-checkpoints": [
        "tests/test_live_checkpoints.py",
        "tests/test_live_checkpoints_native.py",
    ],
    "interactive-checkpoints": [
        "tests/test_interactive.py",
        "tests/test_interactive_checkpoints.py",
        "tests/test_interactive_checkpoints_native.py",
    ],
    "grain-reserves": [
        "tests/test_grain_reserves.py",
    ],
    "expansion-wiring": [
        "tests/test_expansion_feature_wiring.py",
        "tests/test_expansion_experiment.py",
        "tests/test_health_care.py",
        "tests/test_harvest_forecasts.py",
    ],
    "ritual-gatherings": [
        "tests/test_ritual_gatherings.py",
        "tests/test_narration_expansion_context.py",
    ],
    "scientific-claims": [
        "tests/test_scientific_claims.py",
        "tests/test_scientific_research_lifecycle_audit.py",
    ],
    "scientific-publication": [
        "tests/test_scientific_publication.py",
    ],
    "scientific-research": [
        "tests/test_scientific_research_state.py",
        "tests/test_scientific_research.py",
        "tests/test_scientific_research_wiring.py",
        "tests/test_scientific_research_experiment.py",
    ],
    "transaction-receipts": [
        "tests/test_transaction_receipts.py",
        "tests/test_public_purchase_receipts.py",
    ],
    "expansion-experiments": [
        "tests/test_expansion_experiment_runner.py",
    ],
    "domestic-credit": [
        "tests/test_domestic_credit.py",
    ],
    "faiths": [
        "tests/test_permanent_faiths.py",
    ],
}
TESTS = [node for nodes in CHUNKS.values() for node in nodes]
if len(set(TESTS)) != len(TESTS):
    raise SystemExit("A pytest node ID is listed in more than one chunk")
DESELECT = ("not test_real_cli_and_cross_process_resume_with_different_hashseeds"
            " and not test_cross_process_deterministic_with_randomized_python_hash_seed")
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
(out / "pytest").mkdir()
base_env = {key: value for key, value in os.environ.items() if key.upper() in {
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATH", "PATHEXT",
    "LOCALAPPDATA", "APPDATA", "USERPROFILE", "LANG", "LC_ALL",
}}
base_env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONHASHSEED="0",
                PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", OMP_NUM_THREADS="1",
                OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                PYTHONPATH=os.pathsep.join(map(str, [ROOT / "src", ROOT, ROOT / "scripts/testing"])))
sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
           for folder in ("src/chronicler", "scripts/testing")
           for path in sorted((ROOT / folder).rglob("*.py"))}
for selected in TESTS:
    path = ROOT / selected.split("::", 1)[0]
    sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
git = ["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT)]
head = subprocess.check_output(git + ["rev-parse", "HEAD"], timeout=10).decode().strip()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
start = time.monotonic()
report = {"at_utc": stamp, "commit": head, "python": sys.version,
          "chunk_limit_seconds": CHUNK_LIMIT_SECONDS, "deselect": DESELECT,
          "source_sha256": sources, "excluded": EXCLUDED,
          "environment_policy": "Runtime-path allowlist; no inherited provider credentials; one-thread caps",
          "chunks": []}
try:
    for name, nodes in CHUNKS.items():
        guard_report = out / f"guard-{name}.json"
        command = [sys.executable, "-B", "-m", "pytest", "-q", "-x", "--tb=short", *nodes,
                   "-p", "python_oracle_guard", "-p", "no:cacheprovider",
                   "--basetemp", str(out / "pytest" / name), "-k", DESELECT]
        chunk = {"name": name, "node_ids": len(nodes), "command": command}
        report["chunks"].append(chunk)
        print(f"== chunk {name}: {len(nodes)} node IDs, {CHUNK_LIMIT_SECONDS}-second limit", flush=True)
        chunk_start = time.monotonic()
        try:
            result = subprocess.run(command, cwd=ROOT, env=dict(base_env, CHRONICLER_OFFLINE_GUARD_REPORT=str(guard_report)),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=CHUNK_LIMIT_SECONDS)
            (out / f"pytest-{name}.txt").write_bytes(result.stdout)
            print(result.stdout.decode("utf-8", errors="replace"), end="", flush=True)
            guard = json.loads(guard_report.read_text(encoding="utf-8")) if guard_report.exists() else None
            chunk.update(exit_code=result.returncode, guard=guard,
                         passed=result.returncode == 0 and guard is not None and guard["state"] == "PASS")
            if guard is None:
                chunk["error"] = "guard receipt missing"
        except subprocess.TimeoutExpired as error:
            (out / f"pytest-{name}.txt").write_bytes(error.stdout or b"")
            chunk.update(exit_code=1, passed=False, error=f"{CHUNK_LIMIT_SECONDS}-second chunk limit exceeded")
        finally:
            chunk["seconds"] = time.monotonic() - chunk_start
        if not chunk["passed"]:
            break
    report["passed"] = len(report["chunks"]) == len(CHUNKS) and all(chunk["passed"] for chunk in report["chunks"])
finally:
    report.setdefault("passed", False)
    report["seconds"] = time.monotonic() - start
    (out / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
for chunk in report["chunks"]:
    state = "PASS" if chunk.get("passed") else f"FAIL ({chunk.get('error', 'exit %s' % chunk.get('exit_code'))})"
    counts = (chunk.get("guard") or {}).get("test_reports", {})
    print(f"chunk {chunk['name']}: {state}, {chunk['seconds']:.1f} s of {CHUNK_LIMIT_SECONDS} s; "
          f"{counts.get('passed', 0)} passed, {counts.get('skipped', 0)} skipped, {counts.get('failed', 0)} failed")
for name in list(CHUNKS)[len(report["chunks"]):]:
    print(f"chunk {name}: not run")
print(f"Lane: {'PASS' if report['passed'] else 'FAIL'} in {report['seconds']:.1f} s")
print(f"Evidence: {out}")
raise SystemExit(0 if report["passed"] else 1)
