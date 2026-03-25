# M54b: Rust Economy Migration - Implementation Plan

> **For Claude Code:** Read `CLAUDE.md` and `docs/superpowers/progress/phase-6-progress.md` before editing. Execute this plan task-by-task. Steps use checkbox syntax (`- [ ]`) for tracking. Keep `--agents=off` behavior frozen throughout M54b. Do not broaden runtime scope just because the Rust economy path exists.

**Goal:** Move the Phase 2 goods economy hot path from Python into Rust while preserving the current semantics for stockpiles, pricing, trade dependency, supply shocks, raider incentives, and same-turn agent signals.

**Architecture:** Rust owns the deterministic Phase 2 state machine and returns five dedicated Arrow batches: region result, civ result, observability, upstream sources, and conservation. Python keeps route decomposition, `_economy_result` reconstruction, `EconomyTracker`, `detect_supply_shocks()`, narration consumers, and accumulator routing. Dedicated economy builders live in `src/chronicler/economy.py`; do not piggyback on `build_region_batch()` or `set_region_state()`.

**Tech Stack:** Rust (`chronicler-agents/src/economy.rs`, `ffi.rs`, `cargo nextest`), Python (`economy.py`, `simulation.py`, `pytest`), PyO3 / Arrow FFI.

**Spec:** `docs/superpowers/specs/2026-03-21-m54b-rust-economy-migration-design.md`

**Suggested branch:** `codex/m54b-rust-economy` cut from `main` after the accepted M54a wrap is merged. Do not stack M54b implementation work directly on the current M54a branch.

**Accepted pre-M54b baseline:**
- `tuning/codex_m53_secession_threshold25.yaml`
- `output/m54a/codex_m53_secession_threshold25_full_500turn_controlled_occ/batch_1/validate_report.json`

**Claude Code execution checklist:**
1. Treat the dedicated economy FFI surface as a correctness requirement. Do not extend `build_region_batch()` or route M54b through `set_region_state()`.
2. Keep `compute_economy()` intact as the Python oracle during M54b. Do not delete it, inline it away, or force direct-import tests to chase a new location mid-milestone.
3. Fix the Python oracle first where the spec has already moved ahead of code. In particular, add `clamp_floor_loss` to the conservation contract before you start judging Rust parity.
4. Preserve call order in `simulation.py`: Rust economy tick -> immediate stockpile write-back -> bridge sees same-turn signals -> tracker/shock consumers -> accumulator tax routing -> later `_economy_result` readers.
5. Keep `--agents=off` frozen. The production runtime should still skip Rust economy there; `compute_economy(agent_mode=False)` remains an oracle/test surface, not a reason to expand runtime scope.
6. Derive region agent counts, occupation counts, merchant wealth, and priest counts inside Rust from the live simulator pool. Python should not pre-aggregate them for FFI.
7. Start the Rust trade kernel fully sequential. Do not add rayon until parity and determinism are already green.
8. Keep observability timing exact:
   - `imports_by_region` / `import_share` are pre-transit-decay final-pass category numbers
   - `stockpile_levels` are post-lifecycle category totals
   - `trade_route_count` is decomposed boundary-pair count before zero-flow pruning
9. If a step seems to require `agent_bridge.py` changes, sanity-check whether the real issue is an `EconomyResult` reconstruction mismatch. The goal is to keep current bridge consumers stable.
10. Guard the Phase 10 fiscal reader explicitly. `tick_factions()` must keep consuming `tithe_base` from `_economy_result` with no same-turn regression.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `chronicler-agents/src/economy.rs` | Pure Rust Phase 2 core: production, demand, tatonnement, trade allocation, transit decay, stockpile lifecycle, signals, observability, conservation |
| `chronicler-agents/tests/test_economy.rs` | Rust scenario, determinism, and conservation tests for the economy core and FFI entry point |
| `tests/test_economy_bridge.py` | Python round-trip tests for dedicated economy builders, tuple unpacking, stockpile write-back, and same-turn consumer visibility |
| `tests/test_economy_parity.py` | Temporary migration parity suite comparing Rust economy outputs against Python `compute_economy()` |

### Modified Files

| File | Changes |
|---|---|
| `chronicler-agents/src/lib.rs` | Export `economy` module |
| `chronicler-agents/src/ffi.rs` | Add economy schema helpers, config setter, and `tick_economy()` entry point |
| `src/chronicler/economy.py` | Keep Python oracle; add dedicated FFI batch builders, Rust wrapper, result reconstruction, and conservation shadow helpers |
| `src/chronicler/simulation.py` | Route agent-backed Phase 2 through the Rust wrapper while preserving downstream Python consumer order |
| `tests/test_factions.py` | Preserve Phase 10 tithe consumption from `_economy_result.tithe_base` |
| `tests/test_economy.py` | Update container/conservation expectations for `clamp_floor_loss` and retained oracle behavior |
| `tests/test_economy_m43a.py` | Preserve stockpile, perishability, and conservation behavior against the updated oracle contract |
| `tests/test_economy_m43b.py` | Preserve trade dependency, upstream-source, raider, and `_economy_result` semantics on the Rust-backed runtime |
| `docs/superpowers/progress/phase-6-progress.md` | Record what landed, the final gate result, and any surviving M54c dependencies after M54b completes |

---

## Task 1: Freeze the Python Oracle and Add Dedicated Economy Builders

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`
- Modify: `tests/test_economy_m43a.py`
- Modify: `tests/test_economy_m43b.py`
- Create: `tests/test_economy_bridge.py`

- [ ] **Step 1: Write failing Python tests for the post-spec contract**

Add failing coverage for:
- `EconomyResult.conservation` including `clamp_floor_loss`
- dedicated `build_economy_region_input_batch(...)` output shape and fixed good-slot ordering
- dedicated `build_economy_trade_route_batch(...)` output shape and stable route ordering
- reconstruction of a Python `EconomyResult` from the five Rust return batches
- same-turn visibility of reconstructed fields to existing consumers (`trade_route_count`, `farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`, `priest_tithe_shares`, `tithe_base`)

- [ ] **Step 2: Fix the Python oracle before touching Rust**

Update `compute_economy()` and related helpers so the Python oracle matches the spec:
- add `clamp_floor_loss` to the conservation dict and conservation tests
- keep field names stable for existing consumers and tests
- do not change gameplay semantics beyond the explicit spec contract already locked

- [ ] **Step 3: Add dedicated economy batch helpers in `economy.py`**

Add helpers with explicit ownership:
- `build_economy_region_input_batch(...)`
- `build_economy_trade_route_batch(...)`
- scalar-context helper for `season_id`, `is_winter`, `trade_friction`
- `reconstruct_economy_result(...)`

Guardrails:
- no `build_region_batch()` reuse
- no `set_region_state()` coupling
- no Python-side pre-aggregation of Rust-owned counts

- [ ] **Step 4: Keep `compute_economy()` as the oracle**

Do not remove or demote the current Python path in this task. The goal is:
- production runtime still unchanged
- Python oracle aligned with spec
- dedicated FFI builders ready for the Rust path

- [ ] **Step 5: Run focused Python tests**

```bash
python -m pytest tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_economy_bridge.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_economy_bridge.py
git commit -m "refactor(m54b): freeze economy oracle and add ffi builders"
```

---

## Task 2: Implement the Pure Rust Economy Core

**Files:**
- Create: `chronicler-agents/src/economy.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Create: `chronicler-agents/tests/test_economy.rs`

- [ ] **Step 1: Write failing Rust scenario tests**

Cover at least:
- single-region production and demand
- two-region trade allocation with stable route ordering
- tatonnement convergence behavior with capped passes
- pre-transit observability vs post-lifecycle stockpiles
- salt preservation during storage decay
- stockpile cap and `clamp_floor_loss`
- civ fiscal outputs from merchant wealth / priest counts
- exact deterministic outputs across repeated runs with the same inputs

- [ ] **Step 2: Create `economy.rs`**

Implement the pure Rust core with explicit structs for:
- region inputs
- derived per-region agent aggregates
- trade-route rows
- region outputs
- civ outputs
- observability rows
- upstream-source rows
- conservation summary
- `EconomyConfig`

Keep the phase split explicit:
1. production and demand extraction
2. sequential trade kernel
3. stockpile lifecycle and region signals
4. civ fiscal outputs and conservation

- [ ] **Step 3: Keep the core sequential first**

Use deterministic iteration only:
- stable route sort by `(origin_region_id, dest_region_id)`
- no rayon
- no RNG
- explicit float accumulation order

Rayon is a later optimization task, not part of first-pass correctness.

- [ ] **Step 4: Preserve the current semantic edge cases**

The Rust core must mirror the live Python path on:
- single-slot production using `resource_type_0` / `resource_effective_yield_0`
- pre-transit `imports_by_region`
- post-lifecycle `stockpile_levels`
- `merchant_margin` vs `merchant_trade_income` timing mismatch
- `trade_route_count` before profitability filtering

- [ ] **Step 5: Run focused Rust tests**

```bash
cargo nextest run -p chronicler-agents test_economy
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/lib.rs chronicler-agents/src/economy.rs chronicler-agents/tests/test_economy.rs
git commit -m "feat(m54b): implement pure rust economy core"
```

---

## Task 3: Add the Economy FFI Surface and Python Reconstruction Path

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Modify: `src/chronicler/economy.py`
- Modify: `chronicler-agents/tests/test_economy.rs`
- Modify: `tests/test_economy_bridge.py`

- [ ] **Step 1: Add failing FFI contract tests**

Add coverage for:
- each centralized schema helper
- `tick_economy()` return tuple order
- fixed good-slot column order on input and output batches
- stable `upstream_sources_batch` grouping and `source_ordinal`
- dedicated scalar args (`season_id`, `is_winter`, `trade_friction`) instead of a wrapper payload

- [ ] **Step 2: Add schema helpers and config setter in `ffi.rs`**

Add:
- `economy_region_input_schema()`
- `economy_trade_route_schema()`
- `economy_region_result_schema()`
- `economy_civ_result_schema()`
- `economy_observability_schema()`
- `economy_upstream_sources_schema()`
- `economy_conservation_schema()`
- `set_economy_config(...)`

Keep these centralized near the top of `ffi.rs`, matching the M54a ecology pattern.

- [ ] **Step 3: Implement `AgentSimulator.tick_economy(...)`**

The method should:
- accept the two dedicated input batches plus primitive scalar args
- derive region agent counts, occupation counts, merchant wealth, and priest counts from the live simulator pool
- call the Rust core
- return five dedicated `PyRecordBatch` values in the fixed order locked by the spec

Do not store per-turn economy state on `RegionState` or overload the ecology sync path.

- [ ] **Step 4: Add a Python wrapper in `economy.py`**

Add a small orchestrator helper that:
- builds the input batches
- calls `sim.tick_economy(...)`
- reconstructs a Python `EconomyResult`
- returns that object after immediate stockpile write-back

Keep field names and container shapes aligned with existing Python consumers so `agent_bridge.py`, `action_engine.py`, and `tick_factions()` do not need a new contract.

- [ ] **Step 5: Run focused tests**

```bash
cargo nextest run -p chronicler-agents --test test_economy
python -m pytest tests/test_economy.py tests/test_economy_bridge.py tests/test_economy_m43a.py tests/test_economy_m43b.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/ffi.rs src/chronicler/economy.py chronicler-agents/tests/test_economy.rs tests/test_economy_bridge.py
git commit -m "feat(m54b): add economy ffi surface and reconstruction path"
```

---

## Task 4: Route Agent-Backed Phase 2 Through Rust

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_factions.py`
- Modify: `tests/test_economy_bridge.py`
- Modify: `tests/test_economy_m43b.py`

- [ ] **Step 1: Rewrite the Phase 2 agent-mode call path**

In `simulation.py`, for runs with an agent-backed snapshot:
- stop calling Python `compute_economy()` as the production path
- call the new Rust wrapper instead
- immediately hand the reconstructed result to `agent_bridge.set_economy_result(...)`

Keep `compute_economy()` callable for tests and parity. This is a runtime switch, not an oracle deletion.

- [ ] **Step 2: Preserve downstream consumer order exactly**

After the Rust call returns:
1. stockpiles must already be written back
2. the bridge must see same-turn economy signals
3. `EconomyTracker` updates run from the reconstructed result
4. `detect_supply_shocks()` runs in Python
5. treasury tax is routed through the accumulator
6. later phases still read `world._economy_result`, especially `tick_factions()` via `tithe_base`

Do not reorder those consumers while refactoring.

- [ ] **Step 3: Keep `--agents=off` behavior frozen**

Explicitly preserve:
- no Rust economy runtime in production `--agents=off`
- `compute_economy(agent_mode=False)` remains a Python oracle/test surface
- no new `main.py` or CLI wiring for off-mode economy in this milestone

- [ ] **Step 4: Add focused integration tests**

Prove:
- `_economy_result` still overwrites each turn
- same-turn raider logic still sees written-back stockpiles
- same-turn bridge consumers still see region/civ economy signals
- Phase 10 `tick_factions()` still consumes `tithe_base` from the reconstructed `_economy_result`
- supply shock actor ordering is unchanged

- [ ] **Step 5: Run focused runtime tests**

```bash
python -m pytest tests/test_economy_bridge.py tests/test_economy_m43b.py tests/test_factions.py tests/test_m36_regression.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_economy_bridge.py tests/test_economy_m43b.py tests/test_factions.py
git commit -m "feat(m54b): route phase 2 through rust economy"
```

---

## Task 5: Build the Parity and Conservation Safety Net

**Files:**
- Create: `tests/test_economy_parity.py`
- Modify: `tests/test_economy.py`
- Modify: `tests/test_economy_m43a.py`
- Modify: `tests/test_economy_m43b.py`
- Modify: `chronicler-agents/tests/test_economy.rs`

- [ ] **Step 1: Add the temporary parity suite**

`tests/test_economy_parity.py` should compare Rust against Python `compute_economy()` on:
- single-region fixtures
- two-region trade fixtures
- multi-route trade fixtures
- storage decay / preservation fixtures
- multi-turn drift checks

Comparison rules:
- exact for ids, counts, route ordering, booleans, and fixed slot ordering
- tight epsilon for stockpile and signal floats
- explicit checks for pre-transit observability vs post-lifecycle stockpiles

- [ ] **Step 2: Add a Python shadow conservation check**

Prove that:
- Rust inline conservation matches the reconstructed result
- Python oracle conservation matches the same scenario
- `clamp_floor_loss` is accounted for consistently on both sides

Keep this as validation/test infrastructure. Do not invent new production runtime dependencies just to expose conservation.

- [ ] **Step 3: Run the full targeted suite**

```bash
cargo nextest run -p chronicler-agents
python -m pytest tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_economy_bridge.py tests/test_economy_parity.py tests/test_m36_regression.py -q
python -m pytest tests/test_factions.py -q
```

- [ ] **Step 4: Run the merge-gate validation**

At minimum:
- sampled-seed parity sweep against Python `compute_economy()`
- duplicate-run determinism smoke on the Rust path
- canonical `200 seeds x 500 turns` regression run with `tuning/codex_m53_secession_threshold25.yaml`
- `python -m chronicler.validate` against the new `output/m54b/.../batch_1`

Record the accepted before/after comparison against:
- `output/m54a/codex_m53_secession_threshold25_full_500turn_controlled_occ/batch_1/validate_report.json`

- [ ] **Step 5: Commit**

```bash
git add tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_economy_bridge.py tests/test_economy_parity.py chronicler-agents/tests/test_economy.rs
git commit -m "test(m54b): add economy parity and conservation coverage"
```

---

## Final Gate Checklist

- [ ] `tick_economy()` uses dedicated `PyRecordBatch` inputs/outputs plus primitive scalar args
- [ ] No M54b code path extends `build_region_batch()` or calls `set_region_state()` for economy
- [ ] Same-turn stockpile write-back happens before tracker, shock, accumulator, and bridge consumers
- [ ] `_economy_result` remains the canonical transient handoff object and still overwrites each turn
- [ ] `tick_factions()` still reads `tithe_base` from `_economy_result` in Phase 10
- [ ] `--agents=off` production behavior remains unchanged
- [ ] Python `compute_economy()` remains available as the parity oracle through milestone acceptance
- [ ] Rust derives agent counts and fiscal aggregates from the live simulator pool, not Python-precomputed inputs
- [ ] Inline Rust conservation and Python shadow conservation both pass
- [ ] Targeted parity suite is green
- [ ] Canonical `200 seeds x 500 turns` regression is recorded against the accepted M54a baseline

---

## Implementation Notes

- The highest-risk failure mode is accidentally coupling M54b to the generic region-sync path because it already exists. Do not do that. Dedicated economy builders are part of the milestone contract.
- `clamp_floor_loss` is the first oracle mismatch to fix. If it is missing on the Python side, every later conservation comparison will be noisy and misleading.
- Keep Python route decomposition in Python. Rust should not quietly absorb `decompose_trade_routes()` scope during this milestone.
- If `agent_bridge.py` starts needing large changes, stop and verify that the reconstructed `EconomyResult` shape still matches the old one. The bridge should mostly keep reading the same fields.
- Do not use the existence of `compute_economy(agent_mode=False)` tests as justification for enabling Rust economy in aggregate mode. The spec explicitly freezes that runtime behavior.
- Defer rayon until parity is already proven. The sequential trade kernel is the determinism anchor, and premature parallelism is the easiest way to waste days here.
- After the final gate, update `docs/superpowers/progress/phase-6-progress.md` with what landed, the exact acceptance-run path, and any surviving M54c dependency notes.
