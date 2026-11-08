# Rust cross-language consolidation — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** CON-5, CON-6, CON-7
> **Depends on:** PIN-1 (DEC-1 option A) for every edit to an enforced file; CON-7 stage 1 and CON-5 stage 1 need nothing.
> **Feeds:** FIX-6 (money-path `Err`), COR-8 (`TITHE_RATE` pass-through), DEAD-3/DEAD-5, LAB-1 (final home of the oracle)
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scout reports 19, 21, 20, 22, 12, 11, 13, 05, 03)

## 1. Goal and scope
Three behaviour-preserving refactors that shrink the Python/Rust seam.
- **CON-5:** every Python↔Rust constant mirror is checked by one parity test file that runs with no native extension. Where a pinned-file edit is needed to remove an in-language copy, it waits for PIN-1.
- **CON-6:** the FFI loses its duplicated column readers and its 1,070-line inline test module. `tick_economy` loses its agent-count and civ-fiscal derivation. `economy.rs` loses four test-only wrappers.
- **CON-7:** the Python `compute_economy` shadow (about 770 lines) moves out of `economy.py` into `economy_oracle.py`, with every caller migrated.

Out of scope: any outcome change (`TITHE_RATE` pass-through is COR-8; tithe double count and minted tax are findings, not this spec); `settle_food_purchases` panics (FIX-6); the eight zero-caller exports and `PURPOSE_RESTITUTION` (DEAD-3); struct-field changes (they change the `persist::py::describe` fingerprint).

## 2. Current behaviour (verified)
**Mirrors.** Hand-copied, one comment-linked each:
- Terrain ids: `ffi_constants.py:16-28` vs `region.rs:5-9`. Bond ids: `ffi_constants.py:51-70` vs `relationships.rs:7-18,47-49`. `VALUE_EMPTY`: `ffi_constants.py:43`.
- Terrain caps and defaults: `ecology.py:50-73` vs `ecology.rs:85-95`. Season and climate tables: `resources.py:358,373` vs `ecology.rs:52-80`.
- Movement enums and `RELIEF_TURNS`: `agent_movements_state.py:21-58`, `agent_movements.py:137` vs `movements.rs:31-46,96`.
- `SCHISM_SECESSION_MODIFIER`: `religion.py:52` vs `politics.rs:19-20`.
- `TITHE_RATE`: `factions.py:35` vs `economy.rs:113`. `TITHE_FOOD_GATE`: `economy.py:2124` (a local), `economy.rs:117`, and `tests/test_audit_batch_d.py:85,100`.
- Supply floor 0.1: `economy.rs:120`, `economy.py:1021`, `merchant.rs:534,540`, `grain_reserves.py:110`.
- `EconomyConfig::default` (`economy.rs:151-178`) vs Python module constants pushed at `agent_bridge.py:1171-1195`. Python always pushes all 19 values, but the five tatonnement values are literals there (`agent_bridge.py:1191-1195`). `NATIVE_PURPOSES` (`money.py:75`) vs `wealth_transfer.rs:65`.

**Audit claims that are wrong or stale.**
- `tests/test_bond_types.py` does not exist (the `ffi_constants.py:47` comment is stale). No test checks bond ids against Rust today.
- Hunger is already guarded: `tests/test_hunger_mortality.py:98-112` regex-parses `demographics.rs` for both mortality constants, `HUNGER_FAMINE_TURNS` and the 0.6 threshold. Scout 05 said only 0.6 was asserted. This is the pattern to copy.
- `tick_economy`'s `season_id` is dead, but dropping it breaks about 25 test calls and 5 scripts (`tick_economy(batch, routes, 0, False, 1.0)`). It stays.
- The `economy.rs` wrappers are not "test-only inside the crate": `tick_economy_core` has about 60 callers in `chronicler-agents/tests/` (`test_economy.rs`, `test_merchant.rs`, `test_production_ledger.rs`), so it stays. The four middle wrappers have about 25 external callers (`test_household_retail_economy.rs`, `test_household_retail_tick.rs`, `economy.rs` tests).
- `ffi/mod.rs` already has test submodules (`mod agent_context_tests;`, `mod health_care_observation_tests;` at 4751-4756, `health_care_policy_tests` at 5825). Only `mod tests` (4758-5824) is inline.
- `#[pymethods]` cannot hold macro-generated methods without PyO3's `multiple-pymethods` feature (a new dependency). The take/cancel/set "triads" are 3 to 12 lines each with different bodies (`mod.rs:518,558,586,917,949,1048,1071`), so the audit's 40-80 line saving is not credible.
- `compute_economy`: no production caller (`simulation.py:2011` is a comment). The audit's "21 test files" is 9 test files plus 3 scripts (`validate_fishery_recovery.py:131`, `economy_coupling_experiment.py:172,210`, `archive/mutual_aid_example.py:72`).

**Message text.** The 14 column macros produce six message styles (`missing column X`, `missing column: X`, `missing or wrong type: X`, prefixed `civ input …`, `region input …`, `topology …`, `patch …`). No test in `tests/*.py` or `chronicler-agents/tests/` matches any of them.

## 3. Design
### CON-5: parity tests, not generation
Options evaluated:
- **(a) Parity tests only.** Python literals stay and work with no extension. A test parses Rust source with regex (the `test_hunger_mortality.py` pattern). It needs no native build, runs in the oracle lane and has no wheel impact.
- **(b) Checked-in data file loaded by both.** Rejected. `chronicler-agents` is its own maturin project (`chronicler-agents/pyproject.toml`), and the root package ships `src/chronicler`. `include_str!` of a file outside either tree breaks `cargo package` and maturin sdists, and a copy in each tree is again a mirror. `build.rs` (currently only a rustc probe) would need to generate typed `const f32` arrays and the `Terrain` and `BondType` enums, which is more machinery than the 60 lines saved. It would also touch about 15 enforced files.
- **(c) Rust `constants()` pyfunction.** Rejected as the primary route. It edits `lib.rs` (enforced), needs a rebuild, and the test then runs only with native installed.

**Recommendation: (a).** Add `tests/rust_source_constants.py` (a helper, not collected; `tests.legacy_ecology_oracle` shows `tests.*` imports work) with `const(path, name)`, `enum(path, name)` and `array(path, name)` regex readers. Extend `tests/test_ffi_constants.py` (already shard-owned) with one test per row of the table below, and add that file to an oracle chunk (`scripts/run_python_oracle_checks.py`, "core"). Adding a new `test_*.py` would instead need `tests/test_native_ci_shards.py:187` additions plus a manifest entry.

| Row | Python | Rust |
|---|---|---|
| terrain ids, bond ids, `is_positive_valence`, `VALUE_EMPTY` | `ffi_constants.py` | `region.rs`, `relationships.rs`, `agent.rs:193` |
| terrain caps (9 rows, hills excluded) | `ecology.py:63-73` | `ecology.rs:85-95` |
| season and climate tables | `resources.py:358,373` | `ecology.rs:52-80` |
| movement creed/stage/end/reform ids, `RELIEF_TURNS` and the tuning constants | `agent_movements_state.py`, `agent_movements.py` | `movements.rs` |
| `SCHISM_SECESSION_MODIFIER` | `religion.py:52` | `politics.rs:20` |
| `TITHE_RATE`, tithe gate, supply floors | `factions.py`, `economy.py`, `grain_reserves.py` | `economy.rs:113-120`, `merchant.rs:534,540` |
| `EconomyConfig::default` fields | module constants plus the tatonnement literals in `configure_economy_runtime` | `economy.rs:151-178` |
| `NATIVE_PURPOSES` | `money.py:75` | `wealth_transfer.rs:65` |

Unparseable expressions (`5.0 * 0.5`) are evaluated by a tiny whitelisted evaluator in the helper. Stage 2 (after PIN-1) removes the in-language copies: `merchant.rs` uses `economy::SUPPLY_FLOOR` (made `pub`), `grain_reserves.py` imports `economy._SUPPLY_FLOOR`, and `economy.py` hoists `TITHE_FOOD_GATE` to module level. The tautological tests at `test_audit_batch_d.py:70-104` are replaced by an oracle test that calls `compute_economy` at gate boundaries (0.25, 0.5, 0.8), which keeps their intent and uses production code.

### CON-6: FFI generics and splits (names of Python-visible methods unchanged)
- **6a Column reader.** Add `ffi/columns.rs` with `pub(crate) fn col<'a, T: Array + ArrowLabel + 'static>(rb, name, ctx: &str) -> PyResult<&'a T>`. `ArrowLabel::LABEL` gives "UInt16" and so on. It replaces the 10 macros in `mod.rs` and the 4 in `batch.rs`. Message text is normalized to `{ctx}missing column {name}` and `{ctx}column {name} not {LABEL}`. This is an intentional text-only change, stated in the PR; nothing asserts it.
- **6b Tests out.** Move `mod tests` (4758-5824) to `ffi/tests.rs` (`#[cfg(test)] mod tests;`; `use super::*` preserved). `health_care_policy_tests` stays.
- **6c `tick_economy`.** Add `economy::derive_region_agent_counts(pool, n_regions, luxury_threshold)` (from `mod.rs:3785-3830`) and `economy::derive_civ_fiscal_inputs(pool, regions)` (from `3833-3868`). Both stay outside the `CAREOBS_SOURCE` markers (3875-4021), whose text is embedded in fixtures. Keep `season_id` with a named `_season_id` binding, no `let _ =`. Expected: `tick_economy` shrinks from 884 to about 800 lines. Its further 500-line column unpack is not touched.
- **6d Wrappers.** Add `pub struct EconomyExtras<'a> { granary_work_requested, woodcut, retail, workshop_owned }` with `Default`. Make `tick_economy_core_full` the one implementation (signature `…, extras: &EconomyExtras`). Keep `tick_economy_core` as the thin convenience for the 60 integration-test callers. Delete `_with_granary_work`, `_with_woodcut`, `_with_retail` and `_with_inputs`, and migrate their about 25 callers to `EconomyExtras { .. }`.
- **6e Triads (optional).** Skip the macro. At most add `fn take_slot<T>(&mut Option<T>) -> bool` for the 4 one-line `cancel_*` bodies; declared low value.

### CON-7: oracle move
Stage 1 (no pin): add `src/chronicler/economy_oracle.py` that re-exports the oracle names from `chronicler.economy` (`compute_economy`, `compute_production`, `compute_demand`, `compute_prices`, `allocate_trade_flow`, `derive_farmer_income_modifier`, `derive_merchant_margin`, `derive_merchant_trade_income`, `accumulate_stockpile`, `consume_from_stockpile`, `apply_stockpile_cap`, `apply_storage_decay`, `derive_food_sufficiency_from_stockpile`, `apply_transit_decay`). Migrate the 9 test files and 3 scripts to import from it.
Stage 2 (needs PIN-1): move the bodies into `economy_oracle.py` (compute_economy 1742-2137, plus `compute_production` 626, `compute_demand` 995, `compute_prices` 1024, `allocate_trade_flow` 1105, the `derive_*` helpers 1183-1226, stockpile and decay helpers 388-514, `_decompose_category_flow`, `_category_totals`, `_extract_*` 1228-1275). Leave in `economy.py`: constants, `EconomyResult`, `compute_allocated_production` (used by `scientific_claims.py:124`), `bootstrap_region_stockpile`, `build_*_batch`, `build_merchant_route_graph`, `decompose_trade_routes`, `filter_goods_trade_routes`, `reconstruct_economy_result`, `detect_supply_shocks`, `compute_transport_cost` (used by the batch builders). `economy.py` gains a module `__getattr__` shim that lazily imports the moved names, so old imports keep working for one release. The oracle imports shared constants by module attribute. No test patches an oracle-only name (checked: the 16 `monkeypatch.setattr(economy, …)` calls name only production helpers). Final location may move to `chronicler_lab` under LAB-1.

## 4. Compatibility
No saved-field, checkpoint or CLI change. The `persist::py::describe` fingerprints do not change (no struct fields touched; `EconomyExtras` is a transient argument struct). Python method names and `tick_economy`'s five-argument signature stay. Old `chronicler.economy.compute_economy` imports keep working through the shim.

## 5. Pins and preflight
- ENFORCED, so PIN-1 first (or one reviewed inverse layer per file): `ffi/mod.rs` (about 18 fixtures, plus the sha256 at `tests/test_health_care_policy.py:1018-1027`), `ffi/batch.rs`, `economy.rs`, `merchant.rs`, `ecology.rs`, `region.rs`, `lib.rs`, `economy.py`, `ecology.py`, `grain_reserves.py`, `agent_bridge.py`, `simulation.py`. All edits to them are stage 2 or later.
- REFERENCE only: `ffi_constants.py`, `agent_movements*.py`, `religion.py`, `politics.py`, `factions.py`, `resources.py`, `money.py`, `relationships.rs`, `demographics.rs`, `movements.rs`, `politics.rs`, `wealth_transfer.rs`, `scripts/validate_fishery_recovery.py`, `scripts/economy_coupling_experiment.py`.
- `health_care.rs` has a recorded digest (treat as pinned): CON-6d edits its two test calls (281, 509) only if those use a deleted wrapper; they use `tick_economy_core`, which stays, so it is not touched.
- Test files `test_economy*.py`, `test_audit_batch_d.py`, `test_ffi_constants.py` are shard-owned: edit contents only, never rename or move.

## 6. Classification
All three are behaviour-preserving refactors. Proofs: `cargo test` (all targets), the `tests/*_native.py` set, `scripts/turn_speed_identity.py run/compare` on the 9 cases before and after, the oracle lane, and the new parity tests. The only observable change is FFI error-message text in 6a.

## 7. Tests
New: parity rows in `tests/test_ffi_constants.py`, helper `tests/rust_source_constants.py`, a boundary test in `tests/test_economy_oracle.py`. Changed: 9 test files import from `chronicler.economy_oracle`; `test_audit_batch_d.py` tithe tests rewritten. Rust: `economy.rs` and integration tests migrated to `EconomyExtras`; a unit test for each extracted derivation against a hand-built pool.

## 8. Risks and rollback
- A regex parser breaks on Rust reformatting. Mitigation: fail loudly with the constant name.
- The `ffi/mod.rs` edits can invalidate the CAREOBS inverse text; keep the marked spans byte-identical.
- The shim hides stale imports; remove it in the next release.
- Rollback: each PR is independent and reverts cleanly.
- Open: whether to normalize message text (default yes) and whether to attempt 6e (default no).

## 9. Size
CON-5: about +250 test lines, -4 duplicated literals (PR 1 and a small PR 4). CON-6: about -260 net (columns -90, wrappers -110, triad 0, derivation moved 0, `tests.rs` moved 1,070). CON-7: about -770 from `economy.py`, +800 in the oracle file (net +30; the production module shrinks by a third). Total 7 PRs.
