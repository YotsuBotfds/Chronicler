# M54a: Rust Ecology Migration — Implementation Plan

> **For Claude Code:** Read `CLAUDE.md` and `docs/superpowers/progress/phase-6-progress.md` before editing. Execute this plan task-by-task. Steps use checkbox syntax (`- [ ]`) for tracking. Keep `--agents=off` working throughout the migration; do not delete the Python ecology path until both hybrid mode and off mode are proven on the Rust path.

**Goal:** Move Phase 9 ecology from Python into Rust while preserving the existing turn structure, preserving the current Phase 9 yield semantics, and establishing the full-batch + narrow-patch migration contract that M54b and M54c can reuse.

**Architecture:** Pure ecology logic lives in `chronicler-agents/src/ecology.rs`. Rust owns the Phase 9 ecology state machine, returns region-state + trigger batches, and accepts a narrow post-pass patch from Python after famine / soil-floor / terrain-succession work. Hybrid mode uses `AgentSimulator`; `--agents=off` uses a dedicated `EcologySimulator` wrapper with the same ecology methods but no agent pool. `AgentBridge` must be split so the ecology path performs exactly one full region sync per turn.

**Tech Stack:** Rust (`region.rs`, `ffi.rs`, new `ecology.rs`, `cargo nextest`), Python (`agent_bridge.py`, `ecology.py`, `simulation.py`, `main.py`, `pytest`), PyO3 / Arrow FFI.

**Spec:** `docs/superpowers/specs/2026-03-21-m54a-rust-ecology-migration-design.md`

**Suggested branch:** `codex/m54a-rust-ecology`

**Claude Code execution checklist:**
1. Before each task, verify the current signatures and file layout in the live codebase. The Rust FFI surface has drifted before; do not blindly trust older line references.
2. Treat the bridge split as a correctness requirement, not a cleanup. The ecology path must not call `build_region_batch()` twice in the same turn.
3. Preserve the current Phase 9 yield split. `current_turn_yields` stay base-yield-derived in M54a; `resource_effective_yield_*` stays a separate persistent degradation track.
4. Any new one-turn signal or patch-local transient crossing Python/Rust must follow the repo rule: clear before return and add a 2-turn reset test.
5. Run the targeted Rust and Python tests after each task. Do not stack multiple unfinished tasks before validating the earlier ones.
6. Keep the canonical M53 passing baseline handy and use it for the final regression gate:
   - `tuning/codex_m53_secession_threshold25.yaml`
   - `output/m53/codex_m53_secession_threshold25_full/batch_1/validate_report.json`
7. Keep the three yield concepts separate all the way through the migration:
   - full-sync inputs: `resource_base_yield_*`, `resource_effective_yield_*`, `resource_suspension_*`
   - Rust-side mutable same-turn yields: `RegionState.resource_yields`
   - return-only outputs: `current_turn_yield_*`
   Do not keep feeding legacy `resource_yield_*` input columns from `_last_region_yields` once Rust owns Phase 9.
8. Before deleting Python ecology helpers, account for every direct importer. Today `tests/test_ecology.py`, `tests/test_agent_bridge.py`, `tests/test_m34_regression.py`, `tests/test_m35b_disease.py`, and `tests/test_terrain.py` all depend on the current helper surface in some form.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `chronicler-agents/src/ecology.rs` | Pure Rust Phase 9 ecology logic: disease, depletion, soil/water/forest tick, clamp, river cascade, yield computation, typed ecology events |
| `chronicler-agents/tests/test_ecology.rs` | Rust determinism + scenario tests for the ecology core |
| `tests/legacy_ecology_oracle.py` | Frozen pre-M54a Python formulas used only by parity/oracle tests after production helpers are deleted |
| `tests/test_ecology_bridge.py` | Python round-trip integration tests for full batch → ecology tick → post-pass patch → agent tick |
| `tests/test_ecology_parity.py` | Temporary migration-parity suite comparing legacy Python ecology against the new Rust path |

### Modified Files

| File | Changes |
|---|---|
| `chronicler-agents/src/lib.rs` | Export `ecology` module |
| `chronicler-agents/src/region.rs` | Add missing ecology-owned persistent fields and ecology input fields |
| `chronicler-agents/src/ffi.rs` | Add ecology config/topology setters, ecology tick return batches, post-pass patch method, `EcologySimulator` wrapper, shared schema helpers |
| `src/chronicler/agent_bridge.py` | Expand region batch builder, add post-pass patch builder, split full sync from the later agent tick |
| `src/chronicler/ecology.py` | Rewrite `tick_ecology()` into Rust orchestration + Python post-pass + event materialization |
| `src/chronicler/simulation.py` | Pass the correct runtime into Phase 9 and use the split bridge contract |
| `src/chronicler/main.py` | Instantiate `EcologySimulator` in `--agents=off` mode and thread it into the run path |
| `tests/test_agent_bridge.py` | Update region-batch schema expectations and bridge-transient assertions for the new ecology contract |
| `tests/test_ecology.py` | Keep existing ecology behavior tests passing on the new orchestration path |
| `tests/test_m34_regression.py` | Preserve M34 yield/reserve behavior after helper deletion or oracle extraction |
| `tests/test_m35b_disease.py` | Preserve M35b disease behavior on the Rust path |
| `tests/test_rivers.py` | Preserve river-cascade behavior on the Rust path |
| `tests/test_terrain.py` | Preserve terrain/ecology cap behavior after `_clamp_ecology()` leaves production code |
| `tests/test_main.py` | Cover `--agents=off` ecology-runtime wiring |

---

## Task 1: Expand the Ecology Region Schema

**Files:**
- Modify: `chronicler-agents/src/region.rs`
- Modify: `chronicler-agents/src/ffi.rs`
- Modify: `src/chronicler/agent_bridge.py`
- Test: `chronicler-agents/tests/test_ecology.rs`
- Test: `tests/test_agent_bridge.py`
- Test: `tests/test_ecology_bridge.py`

- [ ] **Step 1: Write failing schema/round-trip tests**

Add tests that fail until the ecology-owned and ecology-input fields exist end-to-end:
- Rust-side test that `RegionState::new()` provides sane defaults for new fields such as `disease_baseline`, `capacity_modifier`, `prev_turn_water`, `soil_pressure_streak`, `overextraction_streak_*`, `resource_base_yield_*`, `resource_effective_yield_*`, `resource_suspension_*`, `has_irrigation`, `has_mines`, and `active_focus`.
- Python-side integration test that `build_region_batch()` includes those columns with the expected Arrow dtypes and row counts.
- Update the existing `tests/test_agent_bridge.py` schema assertions so they stop treating legacy input `resource_yield_*` columns as the source of truth for the full sync, and remove the new `_last_region_yields.clear()` dependency from that test class once the full batch no longer reads the ecology cache.

- [ ] **Step 2: Extend `RegionState`**

Add the missing fields required by the spec:
- persistent Rust-owned ecology state
- read-only ecology inputs sent from Python
- enough data to recompute same-turn yields during the post-pass patch without needing a second full sync

Keep the naming split explicit:
- `disease_baseline` is the immutable world-gen baseline input
- `endemic_severity` is the mutable persistent disease state
- `current_turn_yield_*` is return-only and must not become a stored full-sync input field

Keep fixed-slot arrays instead of dict-like structures for all per-slot ecology fields.

- [ ] **Step 3: Extend `set_region_state()` and schema helpers in `ffi.rs`**

Parse the new columns in both the initialization branch and the update branch. Centralize the field names in helper builders rather than scattering string literals across multiple methods; M54b and M54c will reuse this pattern.

- [ ] **Step 4: Expand `build_region_batch()` in Python**

Emit the full ecology payload expected by Rust:
- `disease_baseline`
- `endemic_severity`
- `capacity_modifier`
- `resource_base_yield_0..2`
- `resource_effective_yield_0..2`
- `resource_suspension_0..2`
- `has_irrigation`
- `has_mines`
- `active_focus`
- `prev_turn_water`
- fixed-slot streak columns

Replace the legacy `resource_yield_0..2` full-sync input contract rather than extending it. `current_turn_yield_*` is return-only in M54a, so the new full batch must stop depending on `_get_yield()` / `_last_region_yields`.

Do not change the existing transient-clear behavior in this task; that belongs to the bridge-split task later. Only the full-sync ecology schema should change here.

- [ ] **Step 5: Run focused tests**

```bash
cargo nextest run -p chronicler-agents test_region_new_has
python -m pytest tests/test_agent_bridge.py tests/test_ecology_bridge.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py chronicler-agents/tests/test_ecology.rs tests/test_agent_bridge.py tests/test_ecology_bridge.py
git commit -m "feat(m54a): expand ecology region schema across Python and Rust"
```

---

## Task 2: Implement the Pure Rust Ecology Core

**Files:**
- Create: `chronicler-agents/src/ecology.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Test: `chronicler-agents/tests/test_ecology.rs`

- [ ] **Step 1: Write failing Rust scenario tests**

Cover at least these scenarios:
- basic plains tick
- uncontrolled-region divergence
- disease flare + pandemic suppression
- soil pressure streak threshold
- overextraction event emission
- river cascade second clamp
- reserve depletion / exhausted trickle
- mixed terrain caps/floors

Add one determinism harness helper that can run the same scenario under 1 / 4 / 8 / 16 rayon threads and compare exact outputs.

- [ ] **Step 2: Create `ecology.rs`**

Implement:
- `EcologyConfig`
- `RiverTopology`
- `EcologyEvent`
- helper functions (`effective_capacity`, `pressure_multiplier`, clamp helpers)
- `tick_ecology(...) -> (Vec<[f32; 3]>, Vec<EcologyEvent>)`

Execution order must match the spec:
1. disease
2. depletion feedback
3. soil/water/forest
4. cross-effects
5. clamp
6. river cascade
7. per-turn yields + reserve depletion
8. finalize `prev_turn_water`

- [ ] **Step 3: Preserve the M54a yield split**

Implement `current_turn_yields` using the legacy Phase 9 formula:
- derived from `resource_base_yields`
- modified by season / climate / ecology / reserve ramp

`resource_effective_yield_*` should still be updated only by depletion/recovery logic and carried forward as its own persistent state. Do not collapse the two formulas.

- [ ] **Step 4: Keep parallelism gated**

Start with deterministic plain iteration if needed, but keep the structure ready for rayon. The exact-output determinism tests are more important than enabling `par_iter_mut` on the first commit.

- [ ] **Step 5: Run Rust tests**

```bash
cargo nextest run -p chronicler-agents test_ecology
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/lib.rs chronicler-agents/src/ecology.rs chronicler-agents/tests/test_ecology.rs
git commit -m "feat(m54a): implement pure Rust ecology core"
```

---

## Task 3: Add the FFI Ecology Surface and the Off-Mode Wrapper

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Test: `chronicler-agents/tests/test_ecology.rs`
- Test: `tests/test_agent_bridge.py`
- Test: `tests/test_ecology_bridge.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Add failing wrapper/FFI tests**

Add coverage for:
- `AgentSimulator.tick_ecology()` returning two batches with stable schemas
- `apply_region_postpass_patch()` updating only patched regions
- subset yield recompute when patch changes `soil`, `water`, `forest_cover`, `terrain`, or `carrying_capacity`
- `EcologySimulator` existing without an `AgentPool` boot path

- [ ] **Step 2: Add ecology methods to `AgentSimulator`**

Expose:
- `set_ecology_config(...)`
- `set_river_topology(...)`
- `tick_ecology(...)`
- `apply_region_postpass_patch(...)`

The region-state return batch should include all Rust-owned fields plus `current_turn_yield_*`. The ecology-event batch should use sorted deterministic order.
`tick_ecology(...)` should also persist the minimal recompute context needed by `apply_region_postpass_patch()` (for example season/climate identifiers from the immediately preceding tick) so the patch schema can stay narrow.

- [ ] **Step 3: Implement `EcologySimulator`**

Expose the same ecology-facing methods as the agent-mode wrapper, but do not create or manage an `AgentPool`. Reuse the same `RegionState`, `EcologyConfig`, `RiverTopology`, and `ecology.rs` logic instead of forking a second implementation.

- [ ] **Step 4: Implement patch-time yield recompute**

`apply_region_postpass_patch()` must:
- patch the narrow set of post-pass fields
- detect whether the patch changed an ecology-affecting input
- reuse the recompute context stored by the preceding `tick_ecology()` call instead of widening the patch schema
- recompute `RegionState.resource_yields` only for those regions
- leave population-only updates alone

- [ ] **Step 5: Run focused tests**

```bash
cargo nextest run -p chronicler-agents --test test_ecology
python -m pytest tests/test_agent_bridge.py tests/test_ecology_bridge.py tests/test_main.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_ecology.rs tests/test_agent_bridge.py tests/test_ecology_bridge.py tests/test_main.py
git commit -m "feat(m54a): add ecology ffi surface and off-mode simulator"
```

---

## Task 4: Rewrite Python Phase 9 Orchestration and Split the Bridge Contract

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `src/chronicler/ecology.py`
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/main.py`
- Test: `tests/test_agent_bridge.py`
- Test: `tests/test_ecology.py`
- Test: `tests/test_ecology_bridge.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Split `AgentBridge.tick()`**

Refactor the bridge into two explicit phases:
- `sync_regions(world)` or equivalent full-region send
- `tick_current_state(world, shocks, demands, conquered)` or equivalent signal send + agent tick

Keep a compatibility wrapper if helpful, but the Phase 9 path in `simulation.py` must use the split form so it does not issue a second full `set_region_state()` call after Rust ecology already ran.

Also expose an ecology-capable simulator handle cleanly for Phase 9:
- agent modes: `tick_ecology()` should call the ecology methods on the underlying Rust simulator through a deliberate accessor/property, not through an ad hoc private reach-in from multiple call sites
- off mode: `tick_ecology()` should receive the dedicated `EcologySimulator`

- [ ] **Step 2: Add Python helpers for the ecology orchestration path**

In `agent_bridge.py`, add `build_region_postpass_patch_batch(world)` next to `build_region_batch()`. It must be side-effect free and must not clear any one-turn signals. In `ecology.py`, add small helpers for:
- collecting `pandemic_mask`
- collecting `army_arrived_mask`
- writing returned Rust ecology state back onto Python `Region`
- materializing typed ecology trigger rows into `Event` objects

Keep famine / refugee / soil-floor / counter / terrain-succession logic in Python exactly where the spec says it belongs.

- [ ] **Step 3: Rewrite `tick_ecology()`**

The new orchestration flow should be:
1. full region sync to the Rust simulator
2. Rust ecology tick
3. write-back to Python `Region`
4. Python famine / soil floor / counters / `tick_terrain_succession()` / population sync
5. narrow post-pass patch back to Rust
6. return ecology events to the caller

In agent modes, use `AgentSimulator` through the split bridge. In `--agents=off`, use the dedicated `EcologySimulator`.

- [ ] **Step 4: Wire `--agents=off` runtime creation in `main.py`**

Instantiate the off-mode ecology runtime once, configure it once, and pass it into the run path. Do not create a hidden per-turn simulator.

Keep the current `tests/test_main.py` contract intact:
- `--agents=off` still leaves `world.agent_mode` as `None`
- off-mode runtime construction should be mockable in tests the same way `AgentBridge` construction already is, so the suite does not require the Rust wrapper to be built just to verify wiring

- [ ] **Step 5: Update `simulation.py`**

Phase 9 should now:
- pass an explicit `ecology_runtime` into `tick_ecology()` (`AgentBridge`-owned runtime in agent modes, `EcologySimulator` in off mode)
- use the split bridge path before the later agent tick
- preserve the current Phase 9 → agent tick ordering
- remove the standalone `tick_terrain_succession(world)` call after `tick_ecology()` so the post-pass runs exactly once

- [ ] **Step 6: Run focused Python tests**

```bash
python -m pytest tests/test_agent_bridge.py tests/test_ecology.py tests/test_ecology_bridge.py tests/test_main.py -q -x
```

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/ecology.py src/chronicler/simulation.py src/chronicler/main.py tests/test_agent_bridge.py tests/test_ecology.py tests/test_ecology_bridge.py tests/test_main.py
git commit -m "feat(m54a): rewrite phase 9 orchestration around rust ecology"
```

---

## Task 5: Build the Migration Safety Net

**Files:**
- Create: `tests/legacy_ecology_oracle.py`
- Create: `tests/test_ecology_bridge.py`
- Create: `tests/test_ecology_parity.py`
- Modify: `chronicler-agents/tests/test_ecology.rs`
- Modify: `tests/test_agent_bridge.py`
- Modify: `tests/test_ecology.py`
- Modify: `tests/test_m34_regression.py`
- Modify: `tests/test_m35b_disease.py`
- Modify: `tests/test_rivers.py`
- Modify: `tests/test_terrain.py`

- [ ] **Step 1: Freeze a legacy Python oracle for tests**

Before deleting production helpers, copy the pre-M54a pure formulas needed for oracle-style assertions into `tests/legacy_ecology_oracle.py`. This file is test-only scaffolding:
- no production imports should point at it
- it should preserve the old formulas closely enough to act as the parity oracle
- it should own the direct-formula assertions that cannot survive production-helper deletion

- [ ] **Step 2: Finish the Rust determinism suite**

The Rust test file should prove:
- exact output equality across 1 / 4 / 8 / 16 threads
- deterministic event ordering
- exact `current_turn_yields`
- exact patched-yield recompute behavior

- [ ] **Step 3: Finish the Python round-trip suite**

`tests/test_ecology_bridge.py` should prove:
- every returned field reaches Python `Region`
- post-pass patch survives multiple turns
- patched yields are visible before the agent tick
- no double full-sync occurs on the ecology path
- `--agents=off` can run the same Phase 9 Rust path without an agent pool
- the full-sync path no longer depends on `_last_region_yields`

- [ ] **Step 4: Build the temporary parity suite**

`tests/test_ecology_parity.py` should compare:
- the frozen legacy oracle / legacy path snapshot
- the new Rust ecology path

Keep the comparison rules aligned with the spec:
- exact for integer/state-machine fields
- tight epsilon for clamped ecology fields
- looser epsilon for long-run reserves/yields
- preserve the explicit yield split instead of silently "fixing" it in the migration

Port the current direct-helper tests accordingly:
- `tests/test_ecology.py` should stop importing deleted production helpers directly once cleanup begins; move formula-level assertions either to the new parity/oracle suite or to integration tests that hit the Rust path
- `tests/test_m34_regression.py`, `tests/test_m35b_disease.py`, and `tests/test_terrain.py` must either target the Rust path or import from `tests/legacy_ecology_oracle.py`, not from deleted names in `chronicler.ecology`
- `tests/test_agent_bridge.py` should stop importing `_last_region_yields` once the full-sync batch no longer relies on it

- [ ] **Step 5: Run the targeted ecology suite**

```bash
cargo nextest run -p chronicler-agents --test test_ecology
python -m pytest tests/test_agent_bridge.py tests/test_ecology.py tests/test_m34_regression.py tests/test_m35b_disease.py tests/test_m35b_events.py tests/test_m35b_regression.py tests/test_rivers.py tests/test_terrain.py tests/test_ecology_bridge.py tests/test_ecology_parity.py -q
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/tests/test_ecology.rs tests/legacy_ecology_oracle.py tests/test_agent_bridge.py tests/test_ecology.py tests/test_m34_regression.py tests/test_m35b_disease.py tests/test_m35b_events.py tests/test_m35b_regression.py tests/test_rivers.py tests/test_terrain.py tests/test_ecology_bridge.py tests/test_ecology_parity.py
git commit -m "test(m54a): add rust ecology determinism and parity coverage"
```

---

## Task 6: Cleanup and Merge Gate

**Files:**
- Modify: `src/chronicler/ecology.py`
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `tests/test_agent_bridge.py`
- Modify: `tests/test_ecology.py`
- Modify: `tests/test_m34_regression.py`
- Modify: `tests/test_m35b_disease.py`
- Modify: `tests/test_terrain.py`
- Modify: any now-dead helper imports/callers

- [ ] **Step 1: Remove dead Python ecology internals**

Only after the Rust path is working in both hybrid and off mode:
- delete `_tick_soil()`, `_tick_water()`, `_tick_forest()`, `_apply_cross_effects()`, `_clamp_ecology()`
- delete `compute_disease_severity()`
- delete `compute_resource_yields()` and `update_depletion_feedback()`
- delete `_last_region_yields`
- delete the legacy Python river-cascade loop

Before deleting:
- port or re-home every direct test import from the deleted names (`tests/test_ecology.py`, `tests/test_agent_bridge.py`, `tests/test_m34_regression.py`, `tests/test_m35b_disease.py`, `tests/test_terrain.py`)
- ensure `tests/test_ecology_parity.py` only depends on the test-only oracle, not on deleted production helpers
- grep for all production call sites and imports

- [ ] **Step 2: Run the full targeted validation stack**

```bash
cargo nextest run -p chronicler-agents
python -m pytest tests/test_agent_bridge.py tests/test_ecology.py tests/test_m34_regression.py tests/test_m35b_disease.py tests/test_m35b_events.py tests/test_m35b_regression.py tests/test_rivers.py tests/test_terrain.py tests/test_ecology_bridge.py tests/test_ecology_parity.py tests/test_main.py -q
```

- [ ] **Step 3: Run the merge-gate smoke checks**

At minimum:
- `--agents=off` smoke run
- duplicate-seed determinism smoke in `--agents=off`
- duplicate-seed determinism smoke in `--agents=hybrid`
- 200-turn / 200-seed regression against the M53 baseline profile

Record any accepted tolerance deltas explicitly; do not wave them through verbally.

- [ ] **Step 4: Commit cleanup**

```bash
git add src/chronicler/ecology.py src/chronicler/agent_bridge.py
git commit -m "refactor(m54a): remove legacy python ecology path"
```

---

## Final Gate Checklist

- [ ] Rust ecology core passes exact determinism tests at 1 / 4 / 8 / 16 threads
- [ ] Hybrid mode uses one full region sync plus one narrow post-pass patch in Phase 9
- [ ] `--agents=off` uses `EcologySimulator`, not `AgentSimulator`
- [ ] Post-pass terrain/ecology mutations recompute same-turn yields before the agent tick
- [ ] Existing disease / river / depletion behavior remains within the parity tolerances
- [ ] No full-sync path still reads `_last_region_yields` or legacy `resource_yield_*` inputs
- [ ] No surviving tests import deleted production helpers from `chronicler.ecology`
- [ ] Python ecology dead code and `_last_region_yields` are deleted only after both execution paths are proven
- [ ] 200-seed regression is recorded against the M53 passing baseline

---

## Implementation Notes

- The biggest failure mode is not the Rust math. It is accidentally leaving the old bridge contract in place and silently calling `set_region_state()` twice in one turn. Treat that as a first-class test target.
- `EcologySimulator` should share the same schema helpers and the same `ecology.rs` core as `AgentSimulator`. If you find yourself copying the Rust ecology code path, stop and refactor first.
- Keep the current `current_turn_yield` vs `resource_effective_yield` split explicit in tests and code comments. M54a is an infrastructure migration, not the right place for a stealth behavior rewrite.
- `build_region_batch()` currently populates legacy `resource_yield_*` columns from `_last_region_yields`. M54a should replace that input contract with explicit base/effective/suspension columns; otherwise Phase 9 Rust would be seeded from stale Python-derived yields.
- `build_region_postpass_patch_batch(world)` should stay intentionally narrow and side-effect free. It must not clear one-turn transient signals or become a second copy of `build_region_batch()`.
- If direct-formula assertions are still valuable after helper deletion, keep them in `tests/legacy_ecology_oracle.py` only. Do not leave dead production helpers around just to satisfy tests.
- After the cleanup commit, update `docs/superpowers/progress/phase-6-progress.md` with what landed, the final gate status, and any surviving gotchas for M54b / M54c.
