# Dead-Code Removal (Python, Rust, Pinned) — Design Spec

> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** DEAD-2, DEAD-3, DEAD-5 (viewer DEAD-1/DEAD-4 belong to another writer)
> **Depends on:** PIN-1 (DEC-1 option A) for DEAD-5 only; DEAD-2 and DEAD-3 are independent
> **Feeds:** CON-5, CON-6, CON-7, CON-11, COR-8, DEP-4, DEP-7, HYG-6
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scouts 27, 01, 02, 07, 08, 09, 12, 13, 15, 19, 20, 21, 22, 28, 31)

## 1. Goal and scope

Remove symbols that nothing in production reads, without changing any outcome. Every audit candidate was re-grepped over `src/ tests/ scripts/ chronicler-agents/ viewer/src .github`, excluding `tests/fixtures/reference_baselines/` (frozen copy; this exclusion was wrong for `events.py`, see 2.3 item 14: those sources are exec'd against live modules and must be part of re-greps), including string dispatch (`getattr`, `import_module`, `set_{name}_enabled`/`{name}_active`), `@register_action`, pydantic decorators and `tests/test_import_compatibility.py` (it covers only `field`/`_pick_regnal_name` aliases; no candidate is in it). Result: about 40 audit items were confirmed, and 13 were **wrong or should be kept** (section 2.3). No CLI flag, saved field or serialized key is removed.

Not in scope: viewer; `compute_economy` as oracle (CON-7); `economy.rs` wrapper merge (CON-6); Python formation fallback (CON-11); moving the 29 unreachable modules (LAB-1); unread tuning keys (COR-8).

## 2. Current behaviour (verified)

### 2.1 Classification table

| Symbol | Verdict | Evidence |
|---|---|---|
| `adjacency.is_chokepoint` (`adjacency.py:82`) | test-only, delete | only `tests/test_adjacency.py:4,80-81` |
| `war/common.held_regions` (`war/common.py:153`) | fully unused, delete | `peace.py:247` is an unrelated local |
| `named_events` 4 `generate_*_name` + 6 word lists (`named_events.py:96-163`) | test-only, delete | only `tests/test_culture.py:636-670`; lists used nowhere else |
| `traditions.apply_prophet_martyrdom` (`traditions.py:204-239`) | test-only, delete | only `tests/test_traditions.py:13,213-228`; live path is `religion.compute_martyrdom_boosts` |
| `culture.ASSIMILATION_STABILITY_DRAIN`, `ASSIMILATION_AGENT_THRESHOLD`, `CULTURE_PROJECTION_THRESHOLD` (`culture.py:144,146,322`) | fully unused, delete | live code reads `get_override(..., literal)` (`culture.py:250,277,310,313`) |
| `culture.py:19` import of `K_CULTURE_PROJECTION_THRESHOLD` | unused import, delete import only | key stays in `tuning.py:192,359` (see 2.3) |
| `narrative.thread_domains` (`narrative.py:828`) | test-only no-op, delete | `tests/test_narrative.py:15-26` |
| `narrative.build_before_summary` / `build_after_summary` (572, 654) | test-only wrappers, delete | repoint `tests/test_batch_narration.py:35,57` to `before_changes`/`after_changes`; production inlines the join (`narrative.py:1499-1503`) |
| `exploration.filter_targets_by_fog` (`exploration.py:223`) | fully unused, delete | digest level is provenance only (2.4) |
| `reform_services._service` (176), `narration_provenance.fact_ids` (695), `ritual_gatherings.ritual_gatherings_enabled` (44) | fully unused, delete | no other hit; `{name}_enabled` is never dispatched, only `set_{name}_enabled` |
| `religion.PERSECUTION_REBEL_BOOST/MIGRATE_BOOST` (`religion.py:43-44`) | fully unused, delete | live values `agent.rs:221-222` (0.18, 0.20; the Python 0.30 is stale) |
| `analytics` set A: `extract_schism_count`, `extract_dynasty_count`, `extract_arc_distribution`, `extract_stockpile_levels`, `extract_conversion_rates` (1816-1893) | test-only, delete | not in the report registry (`analytics.py:1334-1349`); tests `test_analytics.py:720-778` |
| `events.roll_for_event`, `apply_probability_cascade` (`events.py:208-259`) | re-export only; **keep in `events.py`** (2.3 item 14) | DEAD-5a removes only the `simulation.py:53-54` re-export; the A01 reference baseline imports the helpers from `chronicler.events` at run time |
| Rust `behavior.rs:1274-1398` `evaluate_region_decisions_v1` | fully unused (already `#[cfg(test)]`, no caller) | name occurs only in its own header |
| Rust `sort::sort_by_region` | bench-only, delete | `benches/cache_bench.rs:139,155-159` |
| Rust `satisfaction::resource_satisfaction`, `trade_satisfaction` (+ `is_food`, `FAMINE_YIELD_THRESHOLD`, `PEAK_YIELD`, `m34_tests`) | test-only, delete | callers only `satisfaction.rs:613-638` |
| Rust `decision_delivery::DEFAULT_AGENT_LIMIT/CANDIDATE_LIMIT` | fully unused mirrors of Python defaults (`decision_delivery.py:121`) | delete (CON-5 may re-add as exported) |
| Rust `relationships::drift_relationships`, `remove_symmetric`, `is_symmetric`; `named_characters::find_candidates`; `spatial::spatial_drift_step_with_kernel` | used only by in-crate `#[cfg(test)]` code | add `#[cfg(test)]` |
| Pinned: `main.run_chronicle` (`main.py:2013`) | test-only (`test_main.py` x6, `test_e2e.py` x2) | witness: `main.py` is in 9 source-inverse fixtures (e.g. `tests/fixtures/crisis_candidate_source_inverse.json`) plus `reviewed_main_witness.py` |
| Pinned: `sidecar.SidecarReader` + 5 readers (`sidecar.py:498-577`) | test-only; the tests are writer round trips | witness: `public_grain_shipments_*_inverse.json`; move class into `tests/test_sidecar.py` |
| Pinned: `economy.derive_farmer_income_modifier` (1183), `compute_production` (626), `classify_upstream_source` (263) | test-only | 7 enforced witnesses, e.g. `academy_candidate`, `crisis_candidate`, `food_accounting`, `livelihoods_pl4` inverse fixtures (`academy_candidate` and `livelihoods_pl4` quote `compute_production`) |
| Pinned: `harvest_forecasts.harvest_forecasts_enabled` (233) | fully unused | `information_candidate_source_inverse.json`, `public_grain_shipments_*` |
| Pinned: `tick.rs` `let old_occ` / `let _ = old_occ` (897, 919) | no-op | 12 inverse fixtures incl. `livelihoods_l2/l5/l6/l7` |
| Pinned: `region.rs` `is_adjacent_to` (256), `Terrain::from_u8` (test-only) | `#[cfg(test)]` candidates | `livelihoods_rs5_source_inverse.json` |

### 2.2 Dependencies that decide placement
- `tests/test_main.py::TestRunChronicle` and `::TestRunChronicleWithScenario` are selected **by class name** in `scripts/run_python_oracle_checks.py:132-133`. Keep both class names.
- `scripts/testing/native_shards_manifest.json:493` `expected_successful_subtests: 623` counts pytest-subtests results (`scripts/native_ci_shards.py:261`), not test functions. None of the test files edited here uses `subtests`/`subTest` (the 15 files that do are listed in the plan). Deleting test **functions** leaves 623 unchanged. Deleting a whole test **module** would change the 460-owner assertion (`tests/test_native_ci_shards.py:357`) and the partition hash, so no PR deletes a module.
- Integration tests in `chronicler-agents/tests/*.rs` compile as separate crates, so anything they call must stay `pub` without `cfg(test)`.

### 2.3 Audit claims that are wrong, or items to keep
1. `accumulator.DEMAND_SCALE_FACTOR` is read at `accumulator.py:211`. Keep (a tuning hook; the `*1.0` is harmless).
2. `economy.INFRASTRUCTURE_DISCOUNT` is read at `economy.py:539` and imported by `tests/test_economy_m43a.py:15`. Keep (documented road placeholder).
3. `sandstorm` labels: `climate.py:246,339-343` emits `event_type="sandstorm"`. Keep `analytics.py:364`, `historiography.py:173` (scout 28 #9 is wrong).
4. `scripts/wealth_floor_outcome_checkpoints.py` (v1) is not free: `tests/test_wealth_floor_outcome_checkpoints_v2.py:122-123` hashes its bytes. Deleting needs the test and its hash removed, which is a pin rewrite. Hand to HYG-6 / PIN-1; not done here.
5. `tick.rs:586-588` vs `1509-1511` are not duplicates: one resets before allocation, the other is the end-of-tick transient clear (AGENTS.md contract); `2115` reads the vectors in between. Keep both.
6. `PURPOSE_RESTITUTION` (`wealth_transfer.rs:78`) is code 10 of the append-only `PURPOSES` table (line 65). Keep; add it to the code-order test (`wealth_transfer.rs:753`).
7. `formation::marriage_scan`, `marriage_scan_reference`, `spatial_drift_step`, `_with_mode` are called by `tests/test_m57a_marriage.rs`, `test_agent_scale_mode.rs`, `determinism.rs`, `test_spatial.rs`. Keep `pub`.
8. `economy.rs` `tick_economy_core*` wrappers are called by `tests/test_economy.rs`, `test_merchant.rs`, `test_household_retail_*.rs`. Not deletable here; CON-6.
9. The 8 zero-Python-caller FFI methods (`get_community_ties`, `has_pending_learning_attendance`, `movements_enabled`, `pending_targeted_death_count`, `set_spatial_sort_profiling`, `spatial_sort_profiling`, `snapshot_is_cached`, `work_reservation_conflicts`) are the observation surface of 10+ native-only tests (`test_learning_cohorts_native.py`, `test_rust_turn_speed.py`, ...). The offline lane skips them, so deletion would only fail in native CI. Keep.
10. `K_CULTURE_PROJECTION_THRESHOLD` is a valid tuning key (`tuning.py:192,359`, enforced). Removing it is COR-8's decision.
11. Analytics set B (`extract_household_stats`, `extract_knowledge_stats`, `extract_stockpiles`, `extract_settlement_diagnostics`, `extract_conservation_diagnostics`) read bundle metadata that production does emit (`agent_bridge.py:1665,1713,1831,1841`). Keep for DEP-7 wiring; open question 1.
12. Keep: `ScenarioConfig.secession_pool` (public scenario schema, `test_politics.py:52`), `Relationship.grievances`, `Event.consequences` (serialized; `viewer/src/types.ts:139`), `provenance.backfill_ids` (old-save contract; COR-5), `render_because` (public renderer), `build_chronicle_prompt` (3-line compat wrapper), `timber_supply.pending_bills` (docstring says reserved; scout 07 #1 may need it for a shared Phase-2 bill ledger), `ecology.rs` `FOCUS_NONE`/`TERRAIN_*` (encoding table; COR-8 hills work), `ASABIYA_*` locals (`simulation.py:766-768`, deliberate dormant D5/D6 constants).
13. `check_food_yield`, `Terrain` variants, `agent.rs` RNG offsets: keep (scouts 12, 27).
14. `events.roll_for_event` and `apply_probability_cascade` are not dead. `tests/test_turn_artifact_lifecycle.py::_baseline_simulation` `exec()`s the frozen `tests/fixtures/reference_baselines/2ab3b48.../src/chronicler/simulation.py` against the live `chronicler` package; its line 33 imports both helpers from `chronicler.events` and calls them at run time. Removing them fails `test_exact_baseline_two_turns_events_narration_state_and_rng` and `test_snapshot_consumers_add_no_rng_and_preserve_raw_semantics` (native shard 1, not the oracle lane). Keep both in `events.py`. The `reference_baselines/` sources are therefore executed against current modules, not inert: future re-greps must include `tests/fixtures/reference_baselines/` and treat its imports as live callers.

### 2.4 Digest-level files
`exploration.py` has three "digest" hits (`tests/fixtures/performance/corrected_423a67c.json`, `corrected_eef5719.json`, `reference_baselines/.../MANIFEST.json`). They are recorded provenance of older source; no test compares them with the current file (`rg source_sha256 tests` finds only writer-side uses), and `test_performance_equivalence.py` compares fixtures with each other. Treated as reference; confirmed by running that test.

## 3. Design

**DEAD-2** (Python, unpinned): delete the symbols above, their imports and their tests; repoint the two narrative test files. Unused-import fallout is checked with `python -m pyflakes` (if absent, `python -W error -c "import chronicler.<module>"` plus `rg`). Split as PR 1 (leaf modules) and PR 2 (`narrative.py`, `analytics.py`).

**DEAD-3** (Rust, unpinned files): PR 3 deletes `evaluate_region_decisions_v1`, `sort_by_region` and its bench arm, the two satisfaction functions with their dead constants and `m34_tests`, and the two decision-delivery constants. It gates five items under `#[cfg(test)]` and extends one test. `cargo check` must stay warning-free; the gated functions must not leave non-test code dead (`remove_directed`, `drift_relationships_with_lookup`, `find_candidates_with` stay used).

**DEAD-5** (pinned; blocked until PIN-1 lands and AGENTS.md/DEVELOPMENT.md change): PR 4 (Python) removes `events` legacy helpers plus the `simulation.py:54` re-export, `run_chronicle`, `harvest_forecasts_enabled`, the three `economy.py` helpers, and moves `SidecarReader` into the test. PR 5 (Rust) gates `is_adjacent_to` and `Terrain::from_u8` and removes `old_occ`. Under PIN-1 option A the witness lane is historical, so no inverse layer is written; if the owner picks B, each file needs a reviewed inverse and DEAD-5 should shrink to `run_chronicle` only. `economy.py` helpers: if CON-7 moves `compute_economy` to a test oracle first, move these three there instead of deleting.

## 4. Compatibility
Saved bundles, checkpoints, CLI flags, viewer: unchanged. Import paths: `chronicler.simulation.roll_for_event` and `apply_probability_cascade` disappear in PR 4 (marked "historical module attributes"; no importer of the `simulation` path in repo; external callers are unverified); `chronicler.events.roll_for_event` and `apply_probability_cascade` stay (2.3 item 14). `chronicler.main.run_chronicle` disappears in PR 4; the replacement `tests/run_chronicle_compat.py` keeps the Namespace shape for tests.

## 5. Pins and preflight (run 2026-11-08)
- No pin (reference only): `events, accumulator, adjacency, war/common, timber_supply, named_events, traditions, culture, narrative, reform_services, narration_provenance, ritual_gatherings, religion, analytics, historiography, provenance`; Rust `behavior, sort, satisfaction, wealth_transfer, decision_delivery, formation, spatial, relationships, named_characters, benches/cache_bench.rs`.
- Digest: `exploration.py` (provenance only), `scripts/wealth_floor_outcome_checkpoints.py` (byte-hash test; untouched).
- Enforced: `tuning.py` (not touched), `models.py` (not touched), `harvest_forecasts.py`, `main.py`, `sidecar.py`, `economy.py`, `simulation.py`, Rust `region.rs`, `ecology.rs` (not touched), `economy.rs` (not touched), `tick.rs`, `ffi/mod.rs` (not touched). All DEAD-5.
- Test files: preflight reports "enforced" only as native-shard/oracle-chunk **ownership**; editing contents is allowed, deleting or moving the module is not.

## 6. Classification
Behaviour-preserving refactor throughout; no correction. Baseline proof: `turn_speed_identity.py run/compare` (9 cases) before/after PR 1, 2 and 4; `cargo test` for PR 3 and 5 (no FFI or tick behaviour change; PR 5 touches `tick.rs`, so also run identity with the native extension). A 200-seed gate is not required (no outcome change); do not claim it.

## 7. Tests
Deleted: `test_adjacency.py::test_is_chokepoint`; `test_culture.py::TestNameGenerators` (5); `test_traditions.py::test_prophet_martyrdom_boosts_movement`; `test_narrative.py::TestDomainThreading` (2); five `test_analytics.py` extractor tests (lines 720-778); `test_events.py::TestRollForEvent` (4) and `TestProbabilityCascade` (3); Rust `m34_tests` (4). Repointed: `test_batch_narration.py` (2). Moved: `test_sidecar.py` reader. Added: `tests/run_chronicle_compat.py` helper; one Rust assert for `PURPOSE_RESTITUTION`.

## 8. Risks, open questions, rollback
1. Analytics set B and the four name generators may be wanted by DEP-7 and DEP-4. Owner call: delete (default here: set A and generators go; set B stays).
2. `filter_targets_by_fog` unused suggests fog filtering of targets is not applied anywhere; deleting hides that gap. Not investigated; flag to the fog owner.
3. External importers of the removed re-exports are unverifiable.
4. Native-only tests are not run offline; PR 3/5 need a native CI run. Rollback: each PR is a pure deletion and reverts cleanly.

## 9. Size
About 300 Python src lines and 150 test lines (PR 1-2), 230 Rust lines (PR 3), 120 Python and 15 Rust lines (PR 4-5, gated). Five PRs.
