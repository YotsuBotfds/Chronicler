## 21 Rust economy (markets, merchants, households, credit, work)

**Map**
- Goods market: `chronicler-agents/src/economy.rs` (2364 non-test lines). `tick_economy_core_full` (economy.rs:1271) runs production, transport, tatonnement (economy.rs:1011), stockpile close-out and civ fiscal (economy.rs:2293-2340).
- FFI: `tick_economy` (ffi/mod.rs:3422-4306, 884 lines). About 500 lines unpack Arrow and derive agent counts (ffi/mod.rs:3785-3800). One core call (ffi/mod.rs:3941). About 370 lines pack output.
- Agent money: `wealth_transfer.rs` (integer milli ledger), `credit.rs`, `household.rs`, `provisioning.rs` (rationing and retail), `merchant.rs` (cargo routing), plus registries in `workshop_work.rs`, `learning_work.rs`, `teaching_work.rs`.
- Turn loop: Phase 2 calls `_sim.tick_economy` (simulation.py:2116), then `reconstruct_economy_result` (economy.py:1508). Wealth phase is tick.rs ~1600-1710.
- Python mirrors: `economy.py` (2137 lines), `household_retail.py` (2606), `money.py`, `wealth_accounting.py`.

**Findings**
1. [high] bug/conservation: Civ money is minted. Treasury tax is credited to the treasury and debited from nobody (economy.rs:2335; simulation.py:1801-1823; wealth_accounting.py:71 says so). In agent mode tithe is paid twice. Priests get `TITHE_RATE x tithe_base` as income (economy.rs:2337; tick.rs:1633). The treasury also gets `TITHE_RATE x compute_tithe_base` (factions.py:426-428), with the same base, gated on clergy influence. Action: decide whether intended; if not, debit merchants for the tax, debit the tithe once, and add a closure test.
2. [high] sim-depth/conservation: Merchant trade income is income by fiat. Hybrid mode credits each merchant `total_delivered_value / merchant_count` (economy.rs:2162-2184, applied at tick.rs:1619-1622). No buyer or seller pays. Farmer income is `BASE x modifier x yield` (tick.rs:1612). merchant.rs has no `pool.wealth` writes, so cargo trips never move money. The only goods-for-money exchange is the household-retail pilot (`settle_food_purchases`, wealth_transfer.rs:444).
3. [med] duplication: `TITHE_FOOD_GATE = 0.5` is hand-copied in economy.py:2124, economy.rs:117 and tests/test_audit_batch_d.py:85,100. `TITHE_RATE` is in factions.py:35 and economy.rs:113, not in `set_economy_config`, so a tuning override desyncs silently. The 0.1 supply floor is in five places: economy.rs:120, economy.py:1021, merchant.rs:534 and 540 (two names), grain_reserves.py:110. `EconomyConfig::default()` (economy.rs:151-178) repeats about 20 Python defaults. Python always pushes its values (agent_bridge.py:1168-1195), so drift is invisible.
4. [med] test-gap: test_audit_batch_d.py:70-104 re-implements the tithe gate inline and never calls production code. It is tautological.
5. [med] dead-code/duplication: Python `compute_economy` (economy.py:1742-2137) has no production caller. Callers are 2 scripts (`scripts/validate_fishery_recovery.py:131`, `scripts/economy_coupling_experiment.py:172,210`) and 21 test files. simulation.py:2011 calls it oracle/test only. Hybrid oracle columns are computed in Rust (economy.rs:1769-1882). Its agent-mode tithe block (economy.py:2107-2137) duplicates economy.rs:2293-2340.
6. [med] complexity: Six wrappers around one core: `tick_economy_core` (economy.rs:1144), `_with_granary_work` (1164), `_with_woodcut` (1186), `_with_retail` (1217), `_with_inputs` (1240), then `_full` (1271). Only `_full` is called from production (ffi/mod.rs:3941). The others are test-only, including health_care.rs test code (~281, ~509).
7. [med] fragile: `tick_economy` discards `season_id` (ffi/mod.rs:3438, `let _ = season_id`). Python passes `is_winter` separately, derived as `season_id == 3` (simulation.py ~2060). The argument is dead and the derivation is duplicated.
8. [med] perf: `IdSlots::new` (pool.rs:23-35) allocates a dense table sized to the largest id ever issued. Ids are monotonic (pool.rs:354-356), so cost grows with run length. It is rebuilt on each of 45 non-test call sites (6 in wealth_transfer.rs).
9. [med] fragile: `settle_food_purchases` panics across FFI: `assert!` (wealth_transfer.rs:459) and `panic!` (wealth_transfer.rs:475), while sibling validators return `Err`. Both are pinned by `should_panic` (wealth_transfer.rs:1184, 1195). If all sale weights are zero, `split_largest_remainder` returns zeros (wealth_transfer.rs:470) and buyer money is neither credited nor refunded. Only Python's identity check catches this (household_retail.py:1668, 1702).
10. [low] fragile: `partial_cmp(..).unwrap()` in sorts (provisioning.rs:275, 847) panics on NaN. learning_work.rs:202 uses `total_cmp`.
11. [low] dead-code: `PURPOSE_RESTITUTION` (wealth_transfer.rs:78), `DEFAULT_AGENT_LIMIT` and `DEFAULT_CANDIDATE_LIMIT` (decision_delivery.rs:13-14) are unused. ffi repeats literals (ffi/mod.rs:4469, 4443). `transaction_receipts::DEFAULT_LIMIT` is test-only.
12. [low] conservation: Stockpile floor clamp books the deficit as `clamp_floor_loss` (economy.rs:1978-1980), which effectively creates goods. analytics.py:2211 treats it as a "repair event". It should be zero in healthy runs.
13. [low] fragile: Wealth is f32; per-row f64-to-f32 casts (wealth_transfer.rs:182, 373) drift sub-milli. `observe_transfer` bookkeeps this as `transfer_rounding`.
14. [low] duplication (parity verified): `largest_remainder` matches across household_retail.py:458 and wealth_transfer.rs:387 (same tie order). `NATIVE_PURPOSES` (money.py:75) hand-copies wealth_transfer.rs:65, checked at runtime. `MAX_SAMPLE` is 24 in Python (household_retail_state.py:110) and 256 in Rust (provisioning.rs:55).

**Authority by mode (b)**: agents off, the economy is frozen and there is no Python economy result. Native: Rust `tick_economy` is authoritative and Python reconstructs the result. Hybrid: Rust computes the oracle shadow and Python requires those columns (economy.py:1529-1541). The Python economy is a test oracle, not a second production implementation. Terrain costs, decay rates and tatonnement knobs match across languages by reading.

**Dead code and panics (c, d)**: no `#[allow(dead_code)]` in these 13 modules; allowances sit in region.rs, agent.rs, behavior.rs and ecology.rs. I grepped every `pub` item across `src/`, `tests/`, `scripts/`, `viewer/` and the Python package. Test-only: the wrappers in finding 6 and `DEFAULT_LIMIT`. Fully unused: `PURPOSE_RESTITUTION`, `DEFAULT_AGENT_LIMIT`, `DEFAULT_CANDIDATE_LIMIT`. Core `assert!`s (economy.rs:1278-1283) are the Python contract. Pins: about 17 `*_source_inverse.json` fixtures pin economy.py, economy.rs or wealth_transfer.rs. Run `scripts/refactor_preflight.py` before moving them.

**Simulation depth (e)**
- Money is one f32 per agent, clamped to [0,100] (agent.rs:229), decayed 2% per tick (agent.rs:230), fed by region signals. Per-agent budgets exist only in pilot regions.
- Route merchant margin through `settle_pairs` (wealth_transfer.rs:319) so buyers pay sellers.
- Extend household food budgets from pilot regions to all regions, reusing provisioning's pro-rata code.
- Give merchants a wealth book and credit.rs a loan book. credit.rs only moves wealth today.

**Confidence**: verified by reading and grep (findings 1-4, 6-11, 14). Inferred: the size of the tithe double count and the share of wealth from merchant income. I did not run cargo, pytest or the simulation.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| economy.rs wrappers `tick_economy_core` … `_with_inputs` (1144-1270) | merge into `_full` with a params struct | ~110 | economy.rs and health_care.rs test callers | low |
| Python `compute_economy` and helpers (economy.py:742-2137) | move to a test oracle; keep constants and production helpers (`bootstrap_region_stockpile`, `build_merchant_route_graph`, `decompose_trade_routes`, `reconstruct_economy_result`) | ~800 (rough) | 21 test files, 2 scripts, ~17 `*_source_inverse.json` pins; run refactor_preflight first | med |
| test_audit_batch_d.py tithe-gate tests (~70-104) | replace with a test that calls production code | ~35 | none | low |
| economy.py agent-mode tithe block (2107-2137) | delete once Python compute_economy is test-only | ~30 | oracle tests only | low |
| `EconomyConfig::default()` (economy.rs:151-178) | keep as test helper or derive from one source | ~30 | economy.rs tests; ffi/mod.rs:240 | med |
| `tick_economy` `season_id` argument (ffi/mod.rs:3438; simulation.py:2116) | drop argument | ~2 | native FFI signature change; needs rebuild and Python edit | med |
| ffi agent-count and merchant-wealth derivation (ffi/mod.rs:3785-3830) | extract to economy.rs | ~80 moved out of FFI | none if bits unchanged | low |
| decision_delivery.rs `DEFAULT_AGENT_LIMIT`, `DEFAULT_CANDIDATE_LIMIT`, plus ffi literals (4469) | delete or use | ~4 | none | low |
| wealth_transfer.rs `PURPOSE_RESTITUTION` (78) | delete | 1 | none; PURPOSES indices unchanged | low |
| Supply floor duplicates (economy.rs:120, economy.py:1021, merchant.rs:534/540, grain_reserves.py:110) | one exported constant | ~5 | Python literal copies | low |
| `settle_food_purchases` assert/panic (wealth_transfer.rs:459, 475) | return `Err` and add a Rust identity check at line 470 | ~0 (fix) | `should_panic` tests at 1184 and 1195 change to `Err` tests | low |
