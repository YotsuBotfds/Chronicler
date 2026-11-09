# Dead-Code Removal (Python, Rust, Pinned) — Implementation Plan

> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** remove verified-dead symbols (DEAD-2, DEAD-3, DEAD-5) with no outcome change.
**Architecture:** pure deletions plus test repointing; pinned files wait for PIN-1.
**Tech stack:** Python 3.13 (`.venv/bin/python`), pytest, Rust crate `chronicler-agents` (cargo).
**Prerequisites:** start from fetched `main`. PRs 1-3 have none. PRs 4-5 need PIN-1 merged (witness lane no longer enforced on current source, AGENTS.md and DEVELOPMENT.md updated). If DEC-1 picks option B, do only `run_chronicle` in PR 4 with a reviewed inverse layer and skip PR 5.

Rules for every PR: before each file run `.venv/bin/python scripts/refactor_preflight.py <path>`. Re-grep every symbol immediately before deleting (`rg -nw <sym> src tests scripts chronicler-agents viewer/src --glob '!tests/fixtures/reference_baselines/**'`); if a new hit appears, keep the symbol and say so in the PR. Do **not** delete any test module (the shard manifest owns 460 modules, `tests/test_native_ci_shards.py:357`) and do not touch `scripts/testing/native_shards_manifest.json`: `expected_successful_subtests` (623) counts pytest-subtests, and none of the files edited here uses `subtests`/`subTest` (the 15 that do: `test_campaign_order_preview`, `test_evidence_admission`, `test_experiment_sessions`, `test_health_care_experiment_policy`, `test_health_care_policy`, `test_memome_candidate_preview`, `test_memome_experiment`, `test_native_ci_shards`, `test_operator_submission_workflow`, `test_pd_input_boundaries`, `test_python_qualification`, `test_reviewed_base_submission`, `test_session_io_boundaries`, `test_session_operations`, `test_session_read_bounds`). Check once per PR: `rg -l "subtests|subTest" <edited test files>` must print nothing.

## File map

| File | Change | PR |
|---|---|---|
| `src/chronicler/adjacency.py`, `war/common.py`, `named_events.py`, `traditions.py`, `culture.py`, `exploration.py`, `reform_services.py`, `narration_provenance.py`, `ritual_gatherings.py`, `religion.py` | delete dead symbols | 1 |
| `tests/test_adjacency.py`, `test_culture.py`, `test_traditions.py` | delete matching tests/imports | 1 |
| `src/chronicler/narrative.py`, `analytics.py` | delete wrappers / 5 extractors | 2 |
| `tests/test_narrative.py`, `test_batch_narration.py`, `test_analytics.py` | delete / repoint | 2 |
| `chronicler-agents/src/{behavior,sort,satisfaction,decision_delivery,relationships,named_characters,spatial,wealth_transfer}.rs`, `benches/cache_bench.rs` | delete / `#[cfg(test)]` | 3 |
| `src/chronicler/{events,simulation,main,harvest_forecasts,sidecar,economy}.py`, `tests/{test_events,test_main,test_e2e,test_sidecar,test_economy,test_audit_batch_d,test_economy_m43b}.py`, new `tests/run_chronicle_compat.py` | pinned removals | 4 |
| `chronicler-agents/src/{region,tick}.rs` | pinned removals | 5 |
| `docs/CONTINUATION.md`, `docs/integration/*` if they name a symbol | one ledger line per PR | all |

## PR 1: Python leaf modules (DEAD-2a)

### Task DEAD-2a: unpinned leaf deletions
Preflight (all reference-level, none enforced): the ten `src/` files above and the three test files.
- [ ] Step 1: `adjacency.py:82-105` delete `is_chokepoint` (leave `deque` import if `_build_adj_map`/`connected_components` use it; check). `tests/test_adjacency.py:4` remove `is_chokepoint` from the import; delete `test_is_chokepoint` (lines 77-82).
- [ ] Step 2: `war/common.py:153-154` delete `held_regions` (and its blank line). Confirm `holds` is still used.
- [ ] Step 3: `named_events.py:96-163` delete the six word lists and `generate_movement_name`, `generate_schism_name`, `generate_propaganda_name`, `generate_cultural_milestone_name`; keep `deduplicate_name` (165) and everything above 96. Remove now-unused imports (`history_index`, `stable_hash_int`, `random` only if no other use; check with pyflakes). `tests/test_culture.py:636-671` delete the import block and `class TestNameGenerators`; keep `from chronicler.simulation import run_turn` (673).
- [ ] Step 4: `traditions.py:202-239` delete the "Task 23" header and `apply_prophet_martyrdom`; drop unused imports (`NamedEvent`, `Disposition`, `GreatPerson` if no other use). `tests/test_traditions.py:13` remove import; delete lines 211-229 (header + test); update the module docstring ("and prophet martyrdom") at line 2.
- [ ] Step 5: `culture.py` delete `ASSIMILATION_STABILITY_DRAIN` (144), `ASSIMILATION_AGENT_THRESHOLD` (146), `CULTURE_PROJECTION_THRESHOLD` (322); remove `K_CULTURE_PROJECTION_THRESHOLD` from the import at line 19 only. Keep `tuning.py` untouched. Keep the other six constants (tests import them).
- [ ] Step 6: `exploration.py:223-231` delete `filter_targets_by_fog`. `reform_services.py:176-181` delete `_service`. `narration_provenance.py:694-696` delete the `fact_ids` property (decorator included). `ritual_gatherings.py:44-45` delete `ritual_gatherings_enabled`. `religion.py:43-44` delete both persecution constants.
- [ ] Step 7: Verify.
  - `.venv/bin/python -m pyflakes <each edited src file>` (or `python -c "import chronicler.<mod>"` per module) reports no new unused import.
  - `.venv/bin/python -m pytest -q tests/test_adjacency.py tests/test_culture.py tests/test_traditions.py tests/test_politics.py tests/test_performance_equivalence.py tests/test_import_compatibility.py` all pass (the performance test proves the `exploration.py` digest hits are provenance only).
  - `.venv/bin/python scripts/run_python_oracle_checks.py` passes.
  - `.venv/bin/python scripts/turn_speed_identity.py run out_base --case off_s42` on `main` and on the branch, then `compare out_base out_new`: identical.
- [ ] Step 8: Ledger. Commit `Remove dead Python leaf helpers (DEAD-2a)`; CONTINUATION line: "dead-code removal, no behaviour change, identity off_s42 equal". Not a correction.

## PR 2: Python core (DEAD-2b)

### Task DEAD-2b: narrative and analytics
Preflight: `narrative.py`, `analytics.py` (reference/historical only), `tests/test_narrative.py`, `test_batch_narration.py`, `test_analytics.py`.
- [ ] Step 1: `narrative.py:828-837` delete `thread_domains`. `tests/test_narrative.py`: remove `thread_domains` from the import (line 7) and delete `class TestDomainThreading` (lines 15-26).
- [ ] Step 2: `narrative.py:572-583` and `654-665` delete `build_before_summary`, `build_after_summary` (keep `before_changes`, `after_changes`). In `tests/test_batch_narration.py` replace the import (line 8) with `before_changes, after_changes, NarrativeEngine`, add
  `def _bullets(changes): return "\n".join(f"- {t}" for _k, _a, t in changes[2]) if changes[2] else ""` and change line 35 to `summary = _bullets(before_changes(history, moment, None))` and line 57 to `summary = _bullets(after_changes(history, moment, next_moment))` (confirm `after_changes` returns the same 3-tuple shape: read `narrative.py:668-700`). Expected bullet lists in the assertions stay unchanged.
- [ ] Step 3: keep `build_chronicle_prompt` and `render_because` (public wrappers; see spec 2.3).
- [ ] Step 4: `analytics.py:1816-1893` delete `extract_schism_count`, `extract_dynasty_count`, `extract_arc_distribution`, `extract_stockpile_levels`, `extract_conversion_rates` (ends before `extract_artifacts` at 1895). Do **not** touch `extract_household_stats`, `extract_knowledge_stats`, `extract_stockpiles`, `extract_settlement_diagnostics`, `extract_conservation_diagnostics` (spec 2.3 #11). `tests/test_analytics.py:720-778` delete the "M47b Extractor Tests" header and its five tests; keep `test_extract_faction_dominance_includes_clergy` (780). Remove helper functions only they used (pyflakes).
- [ ] Step 5: Verify: `.venv/bin/python -m pytest -q tests/test_narrative.py tests/test_batch_narration.py tests/test_analytics.py tests/test_causal_provenance.py`; `scripts/run_python_oracle_checks.py` (`test_analytics.py` is in oracle chunk `run_python_oracle_checks.py:115`, so run the whole lane); `turn_speed_identity` as in PR 1 plus `--case off_s7`.
- [ ] Step 6: Ledger/commit `Remove test-only narrative wrappers and analytics extractors (DEAD-2b)`.

## PR 3: Rust unpinned (DEAD-3)

### Task DEAD-3: Rust deletions and test-only gating
Preflight: all listed `.rs` files are reference-only (checked); do not touch `ecology.rs`, `economy.rs`, `ffi/mod.rs`, `tick.rs`.
- [ ] Step 1: `behavior.rs:1274-1398` delete the section header, `#[cfg(test)] #[allow(dead_code)]` and `evaluate_region_decisions_v1` (through its closing `}` at 1398; the next separator starts at 1400). Then `cargo test --no-run` and remove any import or constant that now warns (only under `cfg(test)`).
- [ ] Step 2: `sort.rs:65-83` delete `sort_by_region`. `benches/cache_bench.rs:139` change the import to `use chronicler_agents::sort::{sort_by_morton, sorted_iteration_order};` and delete the `region_sort_{}` `bench_function` (155-159). Update `chronicler-agents/benches/BENCHMARK_README.md` only if it names `region_sort` (an `rg` found none).
- [ ] Step 3: `satisfaction.rs` delete `FAMINE_YIELD_THRESHOLD` (7), the `PEAK_YIELD` comment and const (8-11), `is_food` (32), `resource_satisfaction` (36-41), `trade_satisfaction` (43-55), and the whole `#[cfg(test)] mod m34_tests` (starts line 600; ends before the next `#[cfg(test)] mod tests`). Remove the `RegionState` import if `cargo check` says unused.
- [ ] Step 4: `decision_delivery.rs:13-14` delete `DEFAULT_AGENT_LIMIT`, `DEFAULT_CANDIDATE_LIMIT` (keep `DEFAULT_MOVE_LIMIT`, `MAX_LIMIT`).
- [ ] Step 5: add `#[cfg(test)]` above `relationships.rs` `drift_relationships` (288), `remove_symmetric` (275), `is_symmetric` (56); `named_characters.rs:148` `find_candidates`; `spatial.rs:1274-1277` `spatial_drift_step_with_kernel` (keep `#[doc(hidden)]` off, it is test-only). Do **not** gate `marriage_scan`, `marriage_scan_reference`, `spatial_drift_step`, `spatial_drift_step_with_mode` (integration tests in `chronicler-agents/tests/` call them), nor any `tick_economy_core*` wrapper (CON-6).
- [ ] Step 6: `wealth_transfer.rs:753` extend the code-order assertion with `assert_eq!(PURPOSE_RESTITUTION, 10);` (the constant stays).
- [ ] Step 7: Verify from `chronicler-agents/`:
  - `cargo check --locked -j 2` prints zero warnings (baseline was zero);
  - `cargo check --locked -j 2 --tests --benches --examples` compiles (benches and integration tests are separate crates);
  - `cargo test --locked --quiet` passes (the CI command, `.github/workflows/tests.yml:504`);
  - per the AGENTS.md native rule, no extension rebuild is needed (no FFI or tick change), and say so in the PR.
- [ ] Step 8: Commit `Remove dead Rust helpers and gate test-only API (DEAD-3)`; ledger line.

## PR 4: Python pinned (DEAD-5a) — blocked on PIN-1

Preflight: `simulation.py`, `main.py`, `sidecar.py`, `economy.py`, `harvest_forecasts.py` are enforced; confirm that PIN-1 changed `scripts/refactor_preflight.py` output (or the witness tests are marked historical) before starting. Witnesses that today enforce these files: `tests/fixtures/{academy_candidate,crisis_candidate,food_accounting,household_candidate,information_candidate,public_grain_shipments_*,livelihoods_*}_source_inverse.json`, `scripts/testing/reviewed_main_witness.py`, and the nine `tests/test_*_witness.py`.
- [ ] Step 1 (amended in review: only the `simulation.py:53-54` re-export goes; `events.py` and `tests/test_events.py` stay unchanged because `tests/test_turn_artifact_lifecycle.py` exec's the A01 reference baseline, which imports both helpers from `chronicler.events`; spec 2.3 item 14). Original text: `events.py:206-259` delete the "Legacy helpers" header, `roll_for_event`, `apply_probability_cascade`, and `import random` (only use is line 220); update the module docstring if it mentions them. `simulation.py:53-54` delete the comment and the re-export line. `tests/test_events.py` remove the two imports and delete `TestRollForEvent` and `TestProbabilityCascade` (lines 12-58); keep `TestEnvironmentEvents`.
- [ ] Step 2: `main.py:2013-2049` delete `run_chronicle`. Create `tests/run_chronicle_compat.py` (a plain helper like `tests/reference_baselines.py`, not a `test_*` module) containing the old body as `run_chronicle(...)`, built on `execute_run`. In `tests/test_main.py` change line 12 to import `execute_run` only, add `from run_chronicle_compat import run_chronicle`; same in `tests/test_e2e.py:5`. Keep the class names `TestRunChronicle` and `TestRunChronicleWithScenario` (oracle chunks select them by name, `run_python_oracle_checks.py:132-133`). `test_grain_reserves.py:734` is a comment: leave it.
- [ ] Step 3: `harvest_forecasts.py:233-234` delete `harvest_forecasts_enabled`.
- [ ] Step 4: `sidecar.py:498-578` delete `SidecarReader` (verify the exact span first). Move the class body into `tests/test_sidecar.py` as a private helper, change line 1 to import `SidecarWriter` only, and use the local class in the three round-trip tests (lines 12, 28, 49). Net: round-trip coverage kept.
- [ ] Step 5: `economy.py:263`, `626`, `1183` delete `classify_upstream_source`, `compute_production`, `derive_farmer_income_modifier`. If CON-7 has landed, move them to the oracle test module instead. Update `tests/test_economy.py` (imports 15, 22; tests 91-116, 141, 308-326), `tests/test_audit_batch_d.py` (126-153, 655-666) and `tests/test_economy_m43b.py` (126, 122-130 block): delete only the tests that call them; if a test also checks another function (e.g. `FARMER_INCOME_MODIFIER_FLOOR`), keep that part. Leave `INFRASTRUCTURE_DISCOUNT` and `ASABIYA_*` alone.
- [ ] Step 6: Verify: focused pytest on every edited test file; `scripts/run_python_oracle_checks.py`; `turn_speed_identity` run/compare for `off_s42`, `off_s7` and, with the native extension built into the same venv, `hybrid_s42`. Report any witness test that still fails as PIN-1's gap, never edit a fixture hash.
- [ ] Step 7: Commit `Remove dead code from formerly pinned Python files (DEAD-5a)`; ledger lists each removed symbol and the PIN-1 PR it relies on.

## PR 5: Rust pinned (DEAD-5b) — blocked on PIN-1

Witness: `tests/fixtures/livelihoods_rs5_source_inverse.json` (`region.rs`), twelve inverse fixtures incl. `livelihoods_l2/l5/l6/l7` (`tick.rs`).
- [ ] Step 1: `region.rs:256` add `#[cfg(test)]` to `is_adjacent_to`; `region.rs` add `#[cfg(test)]` to `Terrain::from_u8` (the impl-level `#[allow(dead_code)]` at 13 stays unless `cargo check` flags it).
- [ ] Step 2: `tick.rs:897` delete `let old_occ = pool.occupation(slot);` and `tick.rs:919` `let _ = old_occ;`. Leave `tick.rs:586-588` and `1509-1511` (spec 2.3 #5) and `ecology.rs` constants untouched.
- [ ] Step 3: Verify from `chronicler-agents/`: `cargo check --locked -j 2` zero warnings; `cargo test --locked --quiet`. Rebuild the extension into the cloud-setup venv (`scripts/cloud_setup.sh`), verify the compiled classes, then `turn_speed_identity.py run/compare` for `hybrid_s42` and `hybrid_s7` against `main` built the same way (tick.rs changed, so byte identity is the gate; no 200-seed gate because nothing observable changes).
- [ ] Step 4: Commit `Remove dead Rust code from formerly pinned files (DEAD-5b)`; ledger with source and build identities.

## Done when
- [ ] PRs 1-3 merged; PRs 4-5 merged or explicitly deferred with the PIN-1 reason.
- [ ] Every removed symbol re-grepped clean; every "keep" in spec 2.3 still present.
- [ ] `scripts/run_python_oracle_checks.py`, `cargo test --locked`, and `turn_speed_identity` compare identical for each PR.
- [ ] `scripts/testing/native_shards_manifest.json` and `tests/test_native_ci_shards.py` unchanged (module count 460, subtests 623).
- [ ] CONTINUATION has one line per PR; no gate described as complete that was not run.
- [ ] Open questions answered or recorded: analytics set B, name generators vs DEP-4, `filter_targets_by_fog` fog gap, v1 wealth-floor script (HYG-6).
