# Rust cross-language consolidation — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** guard every Python↔Rust constant mirror (CON-5), remove FFI and `economy.rs` duplication (CON-6), and make Python `compute_economy` a test oracle in its own module (CON-7). All behaviour-preserving.
**Architecture:** parity tests parse Rust source with regex (no native needed); a generic `col` reader and an `EconomyExtras` struct replace macros and wrappers; the oracle bodies move to `src/chronicler/economy_oracle.py` behind a lazy shim.
**Tech stack:** Python 3.13 pytest, Rust 1.85 (pyo3 0.28, arrow 58), maturin.
**Prerequisites:** PR 1, 2 and 3 have none. PR 4 to 7 edit enforced files and need PIN-1 (DEC-1 option A), or a reviewed inverse layer per file. Spec: `docs/superpowers/specs/2026-11-08-rust-cross-language-consolidation-design.md`. Start every PR from fetched `main`.

Preflight command for every file below: `.venv/bin/python scripts/refactor_preflight.py <paths>`. Levels recorded on 2026-11-08: ENFORCED = `ffi/mod.rs`, `ffi/batch.rs`, `economy.rs`, `merchant.rs`, `ecology.rs`, `region.rs`, `lib.rs`, `economy.py`, `ecology.py`, `grain_reserves.py`, `agent_bridge.py`, `simulation.py`, all `tests/test_economy*.py`, `test_audit_batch_d.py`, `test_ffi_constants.py` (shard owner only); REFERENCE = the rest; `health_care.rs` = digest recorded in test data.

## File map
| File | Change |
|---|---|
| `tests/rust_source_constants.py` (new, not collected) | regex readers: `const`, `enum`, `array`, `struct_defaults` |
| `tests/test_ffi_constants.py` | parity rows (PR 1) |
| `scripts/run_python_oracle_checks.py` | add `tests/test_ffi_constants.py` to chunk `core` |
| `src/chronicler/economy_oracle.py` (new) | re-export shim (PR 2), then real bodies (PR 7) |
| 9 test files, 3 scripts | import oracle names from `chronicler.economy_oracle` (PR 2) |
| `tests/test_audit_batch_d.py`, `tests/test_economy_oracle.py` | tautological tithe tests replaced (PR 4) |
| `chronicler-agents/src/ffi/columns.rs` (new), `ffi/mod.rs`, `ffi/batch.rs` | generic `col` (PR 5) |
| `chronicler-agents/src/ffi/tests.rs` (new) | moved `mod tests` (PR 5) |
| `chronicler-agents/src/economy.rs`, `ffi/mod.rs`, `chronicler-agents/tests/*.rs` | derivations and `EconomyExtras` (PR 6) |
| `src/chronicler/economy.py`, `grain_reserves.py`, `chronicler-agents/src/merchant.rs` | oracle removal, single constants (PR 4, 7) |

## PR 1: Constant parity tests (CON-5 stage 1; no source edits)
### Task CON-5a: helper and parity rows
- [ ] Step 1: Preflight `tests/test_ffi_constants.py` (shard-owned: edit contents only) and the Rust and Python files read by the tests (read-only).
- [ ] Step 2: Create `tests/rust_source_constants.py`, copying the regex style of `tests/test_hunger_mortality.py:100-105`. API: `const(path, name) -> float|int`, `enum(path, enum_name) -> dict[str,int]` (explicit `= n` or declaration order), `array(path, name) -> list`, `default_fields(path, "impl Default for EconomyConfig") -> dict`. Evaluate `5.0 * 0.5` with `ast` restricted to numbers and `* / + -`. Raise `AssertionError(f"{name} not found in {path}")` on no match.
- [ ] Step 3: In `tests/test_ffi_constants.py` add one test per row (sources in the spec table). Concrete assertions:
  - `enum("region.rs","Terrain")` lowercased equals `TERRAIN_MAP` minus the aliases `river`, `hills`.
  - `enum("relationships.rs","BondType")` (snake-cased; `ExileBond` maps to `exile_bond`) equals `BOND_TYPES`; the arms of `is_positive_valence` equal `POSITIVE_VALENCE_BONDS`.
  - `const("agent.rs","CULTURAL_VALUE_EMPTY")` equals `VALUE_EMPTY` (verify the exact Rust name first at `agent.rs:193`).
  - `ecology.rs TERRAIN_CAPS` rows, in `TERRAIN_MAP` id order, equal `TERRAIN_ECOLOGY_CAPS[name]` as (soil, water, forest_cover); `TERRAIN_FLOORS` equals `ecology._FLOOR_*`.
  - `SEASON_MOD`, `CLIMATE_CLASS_MOD` equal `resources.py`.
  - Movement: `CREED_*`, `STAGE_*`, `RELIEF_TURNS` and the tuning constants listed at `movements.rs:64-116` against `agent_movements.py:60-130` (map names in a dict in the test; list every pair so a new Rust constant fails loudly only if added to the dict).
  - `politics.rs SCHISM_SECESSION_MODIFIER == religion.SCHISM_SECESSION_MODIFIER`.
  - `economy.rs TITHE_RATE == factions.TITHE_RATE`; `TITHE_FOOD_GATE == 0.5`; `SUPPLY_FLOOR == economy._SUPPLY_FLOOR == grain_reserves.PRICE_SUPPLY_FLOOR`; `merchant.rs FOOD_PRICE_SUFFICIENCY_FLOOR == PRICE_SUPPLY_FLOOR == 0.1`.
  - `EconomyConfig` defaults: call `agent_bridge.configure_economy_runtime(stub, world)` with a recording stub whose `set_economy_config(**kw)` captures kwargs and a default `WorldState` with no overrides; compare each kwarg to `default_fields`. Covers the five tatonnement literals.
  - `money.NATIVE_PURPOSES == wealth_transfer.rs PURPOSES`.
- [ ] Step 4: Add `"tests/test_ffi_constants.py"` to chunk `"core"` in `scripts/run_python_oracle_checks.py` (after `tests/test_ecology.py`). Do not raise the 110-second limit.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_ffi_constants.py tests/test_hunger_mortality.py -q` passes. Mutation check: temporarily change `RELIEF_TURNS` in a scratch copy of `movements.rs` path via monkeypatched reader, confirm the row fails (do not edit the repo file). `.venv/bin/python scripts/run_python_oracle_checks.py` stays green; record the `core` chunk time.
- [ ] Step 6: Ledger — no CONTINUATION entry (tests only). Commit: `Test: parity rows for Python↔Rust constant mirrors (CON-5)`.

## PR 2: Oracle shim and caller migration (CON-7 stage 1)
### Task CON-7a: re-export module
- [ ] Step 1: Preflight `src/chronicler/economy.py` (read only here; ENFORCED, not edited in this PR) and the callers.
- [ ] Step 2: Create `src/chronicler/economy_oracle.py`: docstring "Python economy oracle. Not called by the simulation; the Rust `tick_economy` is authoritative." `from chronicler.economy import (compute_economy, compute_production, compute_demand, compute_prices, allocate_trade_flow, derive_farmer_income_modifier, derive_merchant_margin, derive_merchant_trade_income, accumulate_stockpile, consume_from_stockpile, apply_stockpile_cap, apply_storage_decay, derive_food_sufficiency_from_stockpile, apply_transit_decay)` plus `__all__`.
- [ ] Step 3: Change the oracle-name imports in `tests/test_economy.py`, `test_economy_oracle.py`, `test_economy_bridge.py`, `test_economy_coupling.py`, `test_economy_m43a.py`, `test_fishery_experiment.py`, `test_mutual_aid.py`, `test_ecology_harvest_timing.py`, `test_audit_batch_d.py`, and `scripts/validate_fishery_recovery.py:57`, `scripts/economy_coupling_experiment.py:29`, `scripts/archive/mutual_aid_example.py:16`. Keep production-name imports (`EconomyResult`, `build_*`, `reconstruct_economy_result`) on `chronicler.economy`. `compute_transport_cost` stays on `chronicler.economy`.
- [ ] Step 4: Add `tests/test_economy_oracle.py::test_oracle_module_exposes_every_oracle_name` asserting `economy_oracle.__all__` names resolve and that `compute_economy` is not imported by any module under `src/chronicler` except `economy_oracle` (AST scan of `src/`).
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_economy.py tests/test_economy_oracle.py tests/test_economy_m43a.py tests/test_economy_bridge.py tests/test_audit_batch_d.py tests/test_mutual_aid.py tests/test_fishery_experiment.py tests/test_ecology_harvest_timing.py -q` (native-dependent ones skip as before; compare pass/skip counts to `main`). `.venv/bin/python -m pytest tests/test_economy_coupling.py -q` needs the native build.
- [ ] Step 6: Commit: `Refactor: route oracle callers through economy_oracle (CON-7)`.

## PR 3: Preflight evidence for the pinned moves (no code)
- [ ] Step 1: Run the preflight for every file in PR 4 to 7 and paste the output into the PR description. Confirm PIN-1 has merged; if it has not, stop and mark PR 4 to 7 blocked. Do not author inverse layers here unless DEC-1 chose option B (then one layer per file, using `scripts/testing/reviewed_main_witness.py`).
- [ ] Step 2: Capture the behaviour baseline on current `main`: build native into the separate venv per `scripts/cloud_setup.sh`; `.venv/bin/python scripts/turn_speed_identity.py run output/identity-base` (all cases); `cargo test --manifest-path chronicler-agents/Cargo.toml` and record counts; `.venv/bin/python -m pytest tests -q -k "native or economy or ffi" -p no:cacheprovider` counts. Keep outputs outside commits.

## PR 4: Single in-language constants (CON-5 stage 2; needs PIN-1)
### Task CON-5b
- [ ] Step 1: `economy.py`: hoist `TITHE_FOOD_GATE = 0.5` to module level (next to `TAX_RATE`, line 40) and use it in `compute_economy` (currently local at 2124). `grain_reserves.py:110`: `from chronicler.economy import _SUPPLY_FLOOR as PRICE_SUPPLY_FLOOR` (keep the public name). `economy.rs`: `pub const SUPPLY_FLOOR`; `merchant.rs:534,540`: `pub const PRICE_SUPPLY_FLOOR: f32 = crate::economy::SUPPLY_FLOOR; pub const FOOD_PRICE_SUFFICIENCY_FLOOR: f32 = crate::economy::SUPPLY_FLOOR;` (values stay 0.1; the `MAX_PLANNER_PRICE` constant derives from the same).
- [ ] Step 2: Replace `tests/test_audit_batch_d.py:66-104` with a test that calls the oracle: build the two-region world helper from `tests/test_economy_oracle.py::_make_economy_world`, set `food_sufficiency` through region stockpiles giving averages 0.25, 0.5 and 0.8, call `compute_economy`, and assert `tithe_base` equals `merchant_wealth * min(avg/TITHE_FOOD_GATE, 1.0)`. Update the PR 1 parity row to read the new constant.
- [ ] Step 3: Verify: `cargo test --manifest-path chronicler-agents/Cargo.toml merchant economy` and the full crate `cargo test`; `.venv/bin/python -m pytest tests/test_ffi_constants.py tests/test_audit_batch_d.py tests/test_grain_reserves.py -q`; `.venv/bin/python scripts/turn_speed_identity.py run output/identity-new && .venv/bin/python scripts/turn_speed_identity.py compare output/identity-base output/identity-new` expects identical.
- [ ] Step 4: Commit: `Refactor: one supply-floor and tithe-gate constant per language (CON-5)`. No ledger entry.

## PR 5: FFI column reader and test split (CON-6a, 6b; needs PIN-1)
### Task CON-6a
- [ ] Step 1: Create `ffi/columns.rs` with `pub(crate) trait ArrowLabel { const LABEL: &'static str; }` implemented for `UInt8Array`, `UInt16Array`, `UInt32Array`, `Int8Array`, `Float32Array`, `Float64Array`, `BooleanArray`, `StringArray`, and `pub(crate) fn col<'a, T: Array + ArrowLabel + 'static>(rb: &'a RecordBatch, name: &str, ctx: &str) -> PyResult<&'a T>`. Messages: `"{ctx}missing column {name}"` and `"{ctx}column {name} not {LABEL}"` (ctx is `""`, `"civ input "`, `"region input "`, `"topology "`, `"patch "`). Add `mod columns;` in `ffi/mod.rs`.
- [ ] Step 2: Replace the macros at `mod.rs:1184,1193,1202,2440,3447,3455,3463,3471,4317,4326` and `batch.rs:181,282,336,1245` one site at a time; keep each call's local name (`col_u16!(…)` becomes a one-line `macro_rules!` forwarding to `col::<UInt16Array>(…)` only if a site has more than 15 uses, otherwise call `col` directly). Do not touch text inside `CAREOBS_SOURCE_BEGIN/END` spans.
- [ ] Step 3: Add a Rust unit test in `columns.rs` for missing and wrong-type messages.
### Task CON-6b
- [ ] Step 4: Move `mod tests { … }` (`mod.rs:4758-5824`) to `ffi/tests.rs` verbatim; leave `#[cfg(test)] mod tests;` between the existing `mod health_care_observation_tests;` block and `health_care_policy_tests`. Keep `use super::*;`. Do not move `health_care_policy_tests`.
- [ ] Step 5: Verify: `cargo test --manifest-path chronicler-agents/Cargo.toml ffi` (test names unchanged under `ffi::tests::`; compare the `--list` output before and after), then the full crate. Rebuild native, then `.venv/bin/python -m pytest tests/test_agent_bridge.py tests/test_columnar_paths.py tests/test_ecology_bridge.py tests/test_politics_bridge.py tests/test_economy_bridge.py -q`. `cargo test persist` confirms layout fingerprints (no struct field changed). `turn_speed_identity.py compare` identical.
- [ ] Step 6: PR description names the message-text normalization. Commit: `Refactor: generic Arrow column reader and ffi tests file (CON-6)`.

## PR 6: Economy derivations and wrapper merge (CON-6c, 6d; needs PIN-1)
### Task CON-6c
- [ ] Step 1: In `economy.rs` add `pub fn derive_region_agent_counts(pool: &AgentPool, n_regions: usize, luxury_demand_threshold: f32) -> Vec<RegionAgentCounts>` containing `mod.rs:3785-3830` unchanged (including the transit-merchant second pass), and `pub fn derive_civ_fiscal_inputs(pool: &AgentPool, regions: &[RegionState]) -> (usize, Vec<f32>, Vec<u32>)` from `3833-3868` (confirm the region type name at the `self.regions` declaration). Call both from `tick_economy`. Keep evaluation order and float summation order identical (slot order).
- [ ] Step 2: Replace `let _ = season_id;` (`mod.rs:3438`) with a parameter named `_season_id`; keep the Python-visible position and the five-argument signature. Do not edit `simulation.py`.
- [ ] Step 3: Rust unit tests in `economy.rs`: a hand-built pool with farmers, an enlisted farmer, soldiers, a transit merchant with `trip_origin_region`, wealthy agents above the threshold, and priests; assert the exact counts and the per-civ sums.
### Task CON-6d
- [ ] Step 4: Add `EconomyExtras<'a>` (`granary_work_requested: &'a [f32]`, `woodcut: Option<&'a WoodcutInput<'a>>`, `retail: Option<&'a [Option<RetailRegionInput>]>`, `workshop_owned: Option<&'a [Option<f32>]>`; `Default`, all empty or `None`). Change `tick_economy_core_full` to take `extras: &EconomyExtras`. Keep `tick_economy_core` unchanged in signature. Delete `_with_granary_work`, `_with_woodcut`, `_with_retail`, `_with_inputs` (`economy.rs:1164-1270`). Update the `ffi/mod.rs:3941` call, the callers in `economy.rs` tests (2460, 2496, 2933, 2990, 3055, 3166, 3168), `chronicler-agents/tests/test_household_retail_economy.rs` and `test_household_retail_tick.rs`. `health_care.rs:300,528` call `tick_economy_core` and stay untouched.
- [ ] Step 5: Verify: full `cargo test --manifest-path chronicler-agents/Cargo.toml` (zero test-count loss: compare `-- --list | wc -l` to the PR 3 baseline plus the new tests); rebuild native; `.venv/bin/python -m pytest tests/test_economy_coupling.py tests/test_economy_bridge.py tests/test_city_markets.py tests/test_household_retail_native_ffi.py tests/test_production_ledger_native.py tests/test_food_accounting_native.py tests/test_mutual_aid.py -q`; `turn_speed_identity.py compare` identical on all 9 cases. Because tithe and `clamp_floor_loss` outputs are bit-checked there, any diff blocks the PR.
- [ ] Step 6: Commit: `Refactor: economy derivations in economy.rs; one tick_economy_core_full (CON-6)`. Skip 6e (triad helper) unless a reviewer asks.

## PR 7: Move the oracle bodies (CON-7 stage 2; needs PIN-1)
### Task CON-7b
- [ ] Step 1: Preflight `economy.py`; confirm the 17 `*_source_inverse.json` situation matches PR 3.
- [ ] Step 2: Cut from `economy.py` into `economy_oracle.py`: `compute_economy` (1742-2137), `compute_production` (626), `compute_demand` (995), `compute_prices` (1024), `allocate_trade_flow` (1105), `derive_farmer_income_modifier`, `derive_merchant_margin`, `derive_merchant_trade_income` (1183-1226), `apply_transit_decay`, `apply_storage_decay`, `accumulate_stockpile`, `derive_food_sufficiency_from_stockpile`, `consume_from_stockpile`, `apply_stockpile_cap` (388-514), `_category_totals`, `_decompose_category_flow`, `_extract_*` (1228-1275). Before cutting each, `rg "\bname\b" src scripts` to confirm no production use (done on 2026-11-08: none besides `economy.py`). Leave `compute_allocated_production`, `compute_transport_cost`, `EconomyResult`, constants and all `build_*`/`reconstruct_*`/`decompose_*`/`filter_*`/`detect_*`.
- [ ] Step 3: In the oracle import constants by attribute: `from chronicler import economy as _eco` and use `_eco.TERRAIN_COST` style where a test might patch.
- [ ] Step 4: Add to `economy.py` a module-level `__getattr__(name)` that, for names in `_ORACLE_NAMES`, imports `chronicler.economy_oracle` lazily and returns the attribute (`raise AttributeError` otherwise). Update `EconomyResult`'s docstring (line 560) and `simulation.py:2011`'s comment (comment-only; that file is ENFORCED, so skip the comment edit unless PIN-1 is in force).
- [ ] Step 5: Verify: `rg "def compute_economy" src` shows only the oracle; the PR 2 AST test still passes; `.venv/bin/python -m pytest tests/test_economy*.py tests/test_audit_batch_d.py tests/test_mutual_aid.py tests/test_fishery_experiment.py tests/test_ecology_harvest_timing.py tests/test_native_extension_fallbacks.py -q`; `.venv/bin/python scripts/run_python_oracle_checks.py`; `turn_speed_identity.py compare` identical; `.venv/bin/python -c "from chronicler.economy import compute_economy"` still works through the shim. Run `scripts/validate_fishery_recovery.py --help` and `scripts/economy_coupling_experiment.py --help` as import smoke tests.
- [ ] Step 6: Ledger — CONTINUATION entry: "Python `compute_economy` and its oracle-only helpers moved to `chronicler.economy_oracle` (test oracle; no production caller); `chronicler.economy` keeps a lazy shim. Behaviour-preserving; identity cases unchanged." Commit: `Refactor: economy oracle in its own module (CON-7)`.

## Done when
- [ ] `tests/test_ffi_constants.py` parity rows cover every mirror in the spec table and run in the oracle lane with no native extension.
- [ ] No duplicated supply-floor or tithe-gate literal remains within either language.
- [ ] `ffi/mod.rs` has no `macro_rules!` column readers, no inline `mod tests`, and `tick_economy` has no agent-count loop; `batch.rs` has no `col!`.
- [ ] `economy.rs` has `tick_economy_core` and `tick_economy_core_full` only; all integration tests compile.
- [ ] `compute_economy` exists only in `economy_oracle.py`; `economy.py` is about 770 lines shorter; the shim works.
- [ ] `cargo test`, the native Python tests, the oracle lane and `turn_speed_identity.py compare` (all 9 cases identical) pass on the final PR; `persist` fingerprints unchanged.
- [ ] No pinned hash rewritten; PIN-1 cited in PRs 4 to 7.
