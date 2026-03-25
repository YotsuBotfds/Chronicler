# M54c: Rust Politics Migration - Implementation Plan

> **For Claude Code:** Read `CLAUDE.md` and `docs/superpowers/progress/phase-6-progress.md` before editing. Execute this plan task-by-task. Steps use checkbox syntax (`- [ ]`) for tracking. M54c is **politics-only**. Do not pull spatial sort, M55 clustering work, or unrelated diplomacy rewrites into this branch.

**Goal:** Move the ordered Phase 10 political consequence sub-pass from Python into Rust while preserving the current semantics for secession, vassal rebellion, federation formation/dissolution, proxy detection, restoration, twilight absorption, forced collapse, bridge transition timing, and next-turn shock routing.

**Architecture:** Rust owns the deterministic 11-step political consequence pass and returns dedicated op batches. Python keeps topology materialization, bridge transition helpers, event object construction, regnal naming, `sync_civ_population()` call sites, and final application of returned ops. Dedicated politics pack/unpack/apply helpers live in `src/chronicler/politics.py`; do not piggyback on `build_region_batch()` or `set_region_state()`. The non-political prelude of `phase_consequences()` stays in Python; only the politics block after `apply_asabiya_dynamics(world)` moves.

**Tech Stack:** Rust (`chronicler-agents/src/politics.rs`, `ffi.rs`, `cargo nextest`), Python (`politics.py`, `simulation.py`, `main.py`, `pytest`), PyO3 / Arrow FFI.

**Spec:** `docs/superpowers/specs/2026-03-22-m54c-rust-politics-migration-design.md`

**Suggested branch:** `codex/m54c-rust-politics` cut from `main` after the accepted M54b wrap is merged.

**Accepted pre-M54c baseline:**
- `tuning/codex_m53_secession_threshold25.yaml`
- `C:/Users/tateb/Documents/opusprogram_m54b/output/m54b/codex_m53_secession_threshold25_full_500turn_bootstrapfix/batch_1/validate_report.json`

**Claude Code execution checklist:**
1. Treat the 11-step Phase 10 order as a hard correctness contract. Do not parallelize or reorder steps while migrating.
2. Keep the existing Python `check_*` politics functions alive as the parity oracle during M54c. Do not delete or inline them away mid-milestone.
3. M54c is politics-only. Do not fold in spatial sort or M55 work just because the roadmap text still mentions it.
4. Leave the non-political prelude inside `phase_consequences()` in Python. M54c starts after `apply_asabiya_dynamics(world)` and ends with forced collapse.
5. Use dedicated politics builders and op reconstruction in `politics.py`. Do not extend `build_region_batch()` or overload `set_region_state()`.
6. Preserve bridge transition timing exactly. `apply_secession_transitions()`, `apply_restoration_transitions()`, and `apply_absorption_transitions()` must still run after the corresponding topology mutations and before final event merge.
7. Preserve next-turn shock semantics. In hybrid mode, returned political shocks append to `pending_shocks` for the next turn, not the current one.
8. Preserve the current Step 11 quirks: `regions[:1]`, integer division for military/economy, and no `sync_civ_population()` call after forced collapse.
9. Recompute step-4 perceived overlord stability/treasury inside Rust from current in-pass state. Do not freeze those values in Python ahead of the pass.
10. Start the Rust politics core fully sequential. Do not add rayon until parity and determinism are already green.
11. `--agents=off` is part of the milestone, unlike M54b. By acceptance, off-mode must run through the dedicated Rust politics wrapper and match the pre-M54c baseline.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `chronicler-agents/src/politics.rs` | Pure Rust Phase 10 politics core: ordered 11-step consequence pass, helper functions, and typed op emission |
| `chronicler-agents/tests/test_politics.rs` | Rust scenario, determinism, and step-order tests for the politics core and FFI entry point |
| `tests/test_politics_bridge.py` | Python round-trip tests for politics builders, tuple unpacking, op reconstruction, apply order, and same-turn event merge semantics |
| `tests/test_politics_parity.py` | Temporary migration parity suite comparing Rust politics output against the Python politics oracle |

### Modified Files

| File | Changes |
|---|---|
| `chronicler-agents/src/lib.rs` | Export `politics` module |
| `chronicler-agents/src/ffi.rs` | Add politics schema helpers, config setter, off-mode wrapper, and `tick_politics()` entry point |
| `src/chronicler/politics.py` | Keep Python oracle; add dedicated FFI batch builders, op reconstruction, and ordered apply helpers |
| `src/chronicler/simulation.py` | Route the Phase 10 politics sub-pass through the Rust wrapper while preserving downstream timing |
| `src/chronicler/main.py` | Construct the dedicated off-mode `PoliticsSimulator` and pass it into turn execution |
| `tests/test_politics.py` | Preserve oracle behavior and add targeted parity/ordering assertions where appropriate |
| `tests/test_agent_bridge.py` | Preserve bridge transition semantics and transient cleanup under the Rust-backed call path |
| `tests/test_main.py` | Verify off-mode wiring and mockable runtime construction |
| `docs/superpowers/progress/phase-6-progress.md` | Record what landed, the final gate result, and any surviving M55 dependency notes after M54c completes |

---

## Task 1: Freeze the Python Politics Oracle and Add Dedicated Builders / Apply Helpers

**Files:**
- Modify: `src/chronicler/politics.py`
- Modify: `tests/test_politics.py`
- Modify: `tests/test_agent_bridge.py`
- Create: `tests/test_politics_bridge.py`

- [ ] **Step 1: Write failing Python tests for the post-spec contract**

Add failing coverage for:
- dedicated `build_politics_*_batch(...)` helpers with stable ordering
- `reconstruct_politics_ops(...)` fixed tuple-order expectations
- `apply_politics_ops(...)` preserving `step + seq` order across mixed op families
- bridge transition helper timing and deterministic event merge
- `_seceded_this_turn` surviving one turn and clearing on the next builder read

- [ ] **Step 2: Freeze the Python oracle before touching Rust**

Keep the existing Python politics logic as the milestone oracle:
- preserve `check_capital_loss()`
- preserve `check_secession()`
- preserve `update_allied_turns()`
- preserve `check_vassal_rebellion()`
- preserve `check_federation_formation()`
- preserve `check_federation_dissolution()`
- preserve `check_proxy_detection()`
- preserve `check_restoration()`
- preserve `check_twilight_absorption()`
- preserve `update_decline_tracking()`
- preserve the inline forced-collapse behavior from `simulation.py`

Do not delete or materially reshape those semantics in this task. The goal is to add dedicated builders and a mechanical apply layer without changing the production runtime yet.

- [ ] **Step 3: Add dedicated politics builders and apply helpers in `politics.py`**

Add helpers with explicit ownership:
- `build_politics_civ_input_batch(...)`
- `build_politics_region_input_batch(...)`
- dedicated topology builders for relationships, vassals, federations, wars, embargoes, proxy wars, and exile modifiers
- scalar-context helper for `turn` and `hybrid_mode`
- `reconstruct_politics_ops(...)`
- `apply_politics_ops(...)`

Guardrails:
- no `build_region_batch()` reuse
- no `set_region_state()` coupling
- no generic wrapper payload object

- [ ] **Step 4: Keep the direct Python call path intact**

The end state of this task should be:
- production runtime unchanged
- Python oracle aligned with the spec
- dedicated FFI builders and ordered apply helpers ready for the Rust path

- [ ] **Step 5: Run focused Python tests**

```bash
python -m pytest tests/test_politics.py tests/test_agent_bridge.py tests/test_politics_bridge.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py tests/test_agent_bridge.py tests/test_politics_bridge.py
git commit -m "refactor(m54c): freeze politics oracle and add ffi builders"
```

---

## Task 2: Implement the Pure Rust Politics Core

**Files:**
- Create: `chronicler-agents/src/politics.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Create: `chronicler-agents/tests/test_politics.rs`

- [ ] **Step 1: Write failing Rust scenario tests**

Cover at least:
- capital-loss reassignment by effective capacity
- secession trigger, region split, and stat conservation
- allied-turn update preceding federation checks
- vassal rebellion using current in-pass perception
- federation create vs dissolve event behavior
- proxy detection mutation and hostility update
- restoration using `recognized_by`
- twilight absorption preserving dead civs with `regions=[]`
- forced collapse preserving the current integer-division and `regions[:1]` quirks
- exact deterministic outputs across repeated runs with the same inputs

- [ ] **Step 2: Create `politics.rs`**

Implement the pure Rust core with explicit structs for:
- civ inputs
- region inputs
- topology registries
- live-pool derived summaries
- all op families
- event-trigger rows
- `PoliticsConfig`

Keep the phase split explicit:
1. capital loss
2. secession
3. allied-turn bookkeeping
4. vassal rebellion
5. federation formation
6. federation dissolution
7. proxy detection
8. restoration
9. twilight absorption
10. decline tracking
11. forced collapse

- [ ] **Step 3: Reimplement the politics helper functions in Rust**

At minimum:
- `graph_distance(...)`
- `effective_capacity(...)` (reuse the landed M54a behavior)
- `get_severity_multiplier(...)`
- the narrow step-4 `compute_accuracy()` / `get_perceived_stat()` subset
- deterministic `stable_hash_int(...)` equivalent

Keep all of this sequential and deterministic:
- no rayon
- no container-order dependence
- explicit tie-break ordering

- [ ] **Step 4: Preserve the current semantic edge cases**

The Rust core must mirror the live Python path on:
- secession grace period and schism modifier
- `rebelled_overlords` within-step ordering
- federation CREATE-only event emission
- `recognized_by` restoration bonus
- twilight absorption not touching vassals/federations
- forced collapse not calling `sync_civ_population()`

- [ ] **Step 5: Run focused Rust tests**

```bash
cargo nextest run -p chronicler-agents test_politics
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/lib.rs chronicler-agents/src/politics.rs chronicler-agents/tests/test_politics.rs
git commit -m "feat(m54c): implement pure rust politics core"
```

---

## Task 3: Add the Politics FFI Surface and Off-Mode Wrapper

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Modify: `src/chronicler/politics.py`
- Modify: `chronicler-agents/tests/test_politics.rs`
- Modify: `tests/test_politics_bridge.py`

- [ ] **Step 1: Add failing FFI contract tests**

Add coverage for:
- each centralized schema helper
- `tick_politics()` fixed tuple order
- primitive `(ref_kind, ref_id)` encoding for `CivRef` / `FederationRef`
- `step` / `seq` ordering columns on every returned op family
- primitive scalar args (`turn`, `hybrid_mode`) instead of a wrapper payload
- the dedicated off-mode `PoliticsSimulator`

- [ ] **Step 2: Add schema helpers and config setter in `ffi.rs`**

Add centralized helpers for:
- civ input
- region input
- relationship input
- vassal input
- federation input
- war input
- embargo input
- proxy-war input
- exile input
- each returned op family
- `set_politics_config(...)`

Keep them near the top of `ffi.rs`, matching the landed ecology/economy pattern.

- [ ] **Step 3: Implement `tick_politics(...)` and the off-mode wrapper**

The FFI should:
- accept the dedicated input batches plus primitive scalar args
- read live pool state directly in agent-backed modes
- call the Rust politics core
- return the fixed tuple of op batches
- expose a lightweight `PoliticsSimulator` for `--agents=off`, analogous to `EcologySimulator`

Do not overload the ecology/economy sync path for politics.

- [ ] **Step 4: Add the Python reconstruction path**

Add a small Python wrapper that:
- builds the dedicated input batches
- calls `tick_politics(...)`
- reconstructs op batches into Python apply inputs
- returns those to the ordered apply helper

Keep the reconstruction mechanical. Do not hide step ordering in ad hoc Python conditionals.

- [ ] **Step 5: Run focused tests**

```bash
cargo nextest run -p chronicler-agents --test test_politics
python -m pytest tests/test_politics.py tests/test_politics_bridge.py tests/test_agent_bridge.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/ffi.rs src/chronicler/politics.py chronicler-agents/tests/test_politics.rs tests/test_politics_bridge.py
git commit -m "feat(m54c): add politics ffi surface and off-mode wrapper"
```

---

## Task 4: Route Hybrid and Off-Mode Phase 10 Through Rust

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/main.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_politics_bridge.py`
- Modify: `tests/test_agent_bridge.py`

- [ ] **Step 1: Rewrite the Phase 10 production call path**

In `simulation.py`:
- keep the Python oracle callable for tests/parity
- thread a dedicated `politics_runtime` through `execute_run(...)`, `run_turn(...)`, and `phase_consequences(...)`, mirroring the ecology runtime pattern
- route the production Phase 10 politics sub-pass through Rust in agent-backed modes
- route `--agents=off` through the dedicated `PoliticsSimulator`
- keep the production call shape at one dedicated Rust pass plus Python materialization

- [ ] **Step 2: Preserve downstream timing exactly**

After the Rust call returns:
1. topology ops apply in `step + seq` order
2. bridge transition helpers run at the same semantic points as today
3. `sync_civ_population()` barriers remain step-local where required
4. hybrid political shocks append to `pending_shocks`
5. event triggers merge deterministically with bridge-helper-returned events
6. later turn-end consumers see the same final world state as before

Do not move these side effects to a new phase boundary while refactoring.

- [ ] **Step 3: Wire off-mode construction in `main.py`**

Explicitly preserve:
- `world.agent_mode is None` in `--agents=off`
- a mockable dedicated politics runtime construction path for tests
- the same `tick_politics(...)` signature and return order on both `AgentSimulator` and `PoliticsSimulator`
- no dependency on the hybrid `AgentBridge` for off-mode politics execution

- [ ] **Step 4: Add focused runtime tests**

Prove:
- off-mode goes through the dedicated wrapper
- hybrid transition helpers still fire on secession/restoration/absorption
- `_seceded_this_turn` still clears on the next builder read
- bridge/helper event ordering is deterministic
- forced collapse and twilight absorption keep their current dead-civ semantics

- [ ] **Step 5: Run focused runtime tests**

```bash
python -m pytest tests/test_main.py tests/test_politics.py tests/test_politics_bridge.py tests/test_agent_bridge.py -q -x
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/main.py tests/test_main.py tests/test_politics_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m54c): route phase 10 politics through rust"
```

---

## Task 5: Build the Parity and Determinism Safety Net

**Files:**
- Create: `tests/test_politics_parity.py`
- Modify: `tests/test_politics.py`
- Modify: `tests/test_politics_bridge.py`
- Modify: `tests/test_agent_bridge.py`
- Modify: `chronicler-agents/tests/test_politics.rs`
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Add the temporary parity suite**

`tests/test_politics_parity.py` should compare Rust against the Python politics oracle on:
- capital loss fixtures
- secession fire/non-fire fixtures
- vassal rebellion fixtures
- federation formation/dissolution fixtures
- restoration fixtures
- twilight absorption fixtures
- multi-turn transition cleanup checks

Comparison rules:
- exact for ids, region membership, controllers, relationship dispositions, event types, and ordering
- exact for step/seq ordering
- explicit checks for next-turn `pending_shocks` semantics and transient cleanup

- [ ] **Step 2: Add determinism coverage**

Prove that:
- repeated runs with the same seed produce identical op batches
- event merge order is stable
- if rayon is introduced later, results match at 1/4/8/16 threads

Do not add rayon in this milestone just to satisfy the cross-thread gate. Sequential equality first.

- [ ] **Step 3: Run the full targeted suite**

```bash
cargo nextest run -p chronicler-agents
python -m pytest tests/test_politics.py tests/test_politics_bridge.py tests/test_politics_parity.py tests/test_agent_bridge.py tests/test_main.py -q
```

- [ ] **Step 4: Run the merge-gate validation**

At minimum:
- sampled-seed parity sweep against the Python politics oracle
- off-mode parity sweep across 20+ seeds
- hybrid determinism smoke on the Rust path
- canonical `200 seeds x 500 turns` regression run with `tuning/codex_m53_secession_threshold25.yaml`
- `python -m chronicler.validate` against the new `output/m54c/.../batch_1`

Record the accepted before/after comparison against:
- `output/m54b/codex_m53_secession_threshold25_full_500turn_bootstrapfix/batch_1/validate_report.json`

- [ ] **Step 5: Commit**

```bash
git add tests/test_politics.py tests/test_politics_bridge.py tests/test_politics_parity.py tests/test_agent_bridge.py tests/test_main.py chronicler-agents/tests/test_politics.rs docs/superpowers/progress/phase-6-progress.md
git commit -m "test(m54c): add politics parity and determinism coverage"
```

---

## Final Gate Checklist

- [ ] `tick_politics()` uses dedicated `PyRecordBatch` inputs/outputs plus primitive scalar args
- [ ] No M54c code path extends `build_region_batch()` or calls `set_region_state()` for politics
- [ ] The 11-step Phase 10 political consequence order is preserved exactly
- [ ] Bridge transition helpers still fire at the correct semantic points
- [ ] `_seceded_this_turn` remains a transient and still clears on the next builder read
- [ ] Step-4 perceived overlord stats are recomputed inside Rust from current in-pass state
- [ ] Forced collapse still uses `regions[:1]`, integer division, and no post-step `sync_civ_population()`
- [ ] Dead civs still remain in `world.civilizations` with `regions=[]`
- [ ] `--agents=off` production behavior now runs through the dedicated Rust politics wrapper
- [ ] Targeted parity suite is green
- [ ] Determinism coverage is green
- [ ] Canonical `200 seeds x 500 turns` regression is recorded against the accepted M54b baseline

---

## Implementation Notes

- The highest-risk failure mode is accidentally migrating the topology materialization into Rust instead of returning explicit ops. Do not do that on M54c.
- Keep the Python politics functions available as the oracle until the final parity gate is green. They are the fastest way to catch subtle step-order regressions.
- Step 4 is the trickiest semantic seam. Do not freeze perceived overlord values in Python before the pass; that breaks the very step ordering the spec is trying to preserve.
- Do not let the old roadmap wording pull spatial sort back into this branch. The clean execution line here is politics-only, then M55 for spatial work.
- Event merge ordering matters. A parity suite that only checks the set of event types is too weak for this milestone.
- After the final gate, update `docs/superpowers/progress/phase-6-progress.md` with what landed, the exact acceptance-run path, and the fact that M54c deliberately stayed politics-only.
