# Chronicler Comprehensive Audit — April 1, 2026

## Fleet Summary

22 agents examined ~65,000 lines across 53 Python files, 26 Rust files, ~5,300 lines of TypeScript, all tests, all docs, and all cross-boundary interactions. They collectively made ~1,100 tool calls over ~90 minutes of parallel execution.

---

## Severity Counts

| Tier | Count | Meaning |
|------|-------|---------|
| **BLOCKING** | 3 | Actively broken — wrong behavior in hybrid mode right now |
| **CRITICAL** | 14 | Will crash, silently corrupt data, or violate documented invariants |
| **HIGH** | 28 | Logic errors, missing safety nets, significant test gaps |
| **MEDIUM** | ~40 | Design inconsistencies, fragile patterns, performance |
| **STRATEGIC** | 3 | Architecture decisions affecting project trajectory |

---

## BLOCKING — Fix Immediately

### B-1. Stability recovery is dead code in hybrid mode

**Source:** Integration Reviewer (FFI-1)
**Files:** `simulation.py:526`, `agent_bridge.py:2120`, `pool.rs:760`

Stability recovery routes as `"keep"`, gets applied to `civ.stability` before the Rust tick, then `_write_back` unconditionally overwrites it with Rust's formula (`mean_sat * mean_loy * 100`). The recovery never takes effect. Hybrid mode has no working stability recovery — this causes runaway collapse.

**Fix:** Either route stability recovery as `"signal"` (becomes a shock input to Rust), or remove stability from the Rust write-back set and let Python own it.

---

### B-2. Persecution intensity formula is inverted

**Source:** Religion audit (Issue 3)
**File:** `religion.py:525`

```python
intensity = 1.0 * (1.0 - minority_ratio) * (_gm(world, _KRI) if world else 1.0)
```

This means tiny minorities (10%) get intensity 0.9, while large minorities (50%) get 0.5. It's backwards. Larger minorities should be persecuted less, not more.

**Fix:** Change to `intensity = minority_ratio * majority_dominance_factor` or similar.

---

### B-3. Persecution satisfaction penalty constant defined but never used

**Source:** Religion audit (Issue 1)
**File:** `religion.py:41`

`PERSECUTION_SAT_PENALTY = 0.15` is defined but never referenced anywhere. Persecution computes `persecution_intensity` on regions and sends it to Rust, but no satisfaction penalty is ever applied from the Python side. The Rust side (`satisfaction.rs`) does apply a penalty via `PERSECUTION_SAT_WEIGHT`, but it incorrectly fires for agents with `BELIEF_NONE` (see C-5 below). The Python constant is dead.

---

## CRITICAL — Fix Before Next Milestone

### C-1. `att_idx`/`def_idx` crash risk in `resolve_war()`

**Source:** Action Engine audit (Issue 1)
**File:** `action_engine.py:638-663`

Variables assigned inside `if acc is not None` block but referenced in war outcome branches. In non-vassalization paths, if `acc is not None`, the variables work by coincidence (same scope). But the pattern is fragile and the Simulation Reviewer confirmed the dependency chain is load-bearing only because `acc` can't change mid-function.

**Fix:** Assign `att_idx` and `def_idx` unconditionally at the top of `resolve_war()`.

---

### C-2. "guard" accumulator category silently dropped

**Source:** Action Engine audit (Issue 2)
**File:** `accumulator.py:111-124`

14+ call sites use `"guard"` category, but `apply_keep()` only handles `"keep"`. Guard mutations are recorded but never applied or routed in hybrid mode. Silent data loss for population, military, economy mutations.

**Fix:** Define explicit behavior for `"guard"` category — either treat as `"keep"` or document that it's intentionally dropped in hybrid mode.

---

### C-3. `KeyError` crashes in dynasty checks

**Source:** Relationships audit (Issues 1-2)
**Files:** `dynasties.py:107`, `dynasties.py:125-127`

Direct `gp_map[mid]` access will KeyError if a dynasty member's agent_id is missing from the gp_map. Can happen if a dead agent is pruned before `check_extinctions` runs.

**Fix:** Use `.get()` with fallback, or add `if mid in gp_map` guard.

---

### C-4. Pandemic skips severity multiplier (M18 violation)

**Source:** Simulation Reviewer (Finding 12)
**File:** `emergence.py:322, 326`

`tick_pandemic` applies population and economy losses without `get_severity_multiplier()`. Every other negative stat change in the codebase uses it per the M18 cross-cutting rule. The nearby supervolcano handler correctly applies it.

**Fix:** Add `mult = get_severity_multiplier(civ, world)` in the `tick_pandemic` per-civ damage loop.

---

### C-5. Persecution penalty fires for BELIEF_NONE agents in Rust

**Source:** Rust Reviewer (H6)
**File:** `satisfaction.rs:192-195`

Agents with `BELIEF_NONE` (0xFF) receive persecution penalty when `agent_belief != majority_belief`. The religious mismatch penalty at line 183 correctly excludes BELIEF_NONE with a guard. The persecution penalty doesn't have this guard.

**Fix:** Add `inp.agent_belief != crate::agent::BELIEF_NONE` guard to the persecution penalty block.

---

### C-6. `upsert_symmetric` EvictSlot leaves `rel_count` stale

**Source:** Rust Reviewer (H4)
**File:** `relationships.rs:220-254`

When an eviction path overwrites an existing bond slot, `swap_remove_rel` is not called, so `rel_count` stays too high by 1. This corrupts the relationship slot tracking over time.

**Fix:** In `commit_resolved` for the `EvictSlot` arm, call `swap_remove_rel` before writing the new bond.

---

### C-7. `unwrap()` in production PyO3 method — UB risk

**Source:** Rust Reviewer (H5)
**File:** `ffi.rs:2278`

```rust
let world_seed = u64::from_le_bytes(self.master_seed[0..8].try_into().unwrap());
```

Panic across FFI boundary is undefined behavior in Rust. The `try_into()` on a known-length slice should always succeed, but the `unwrap()` is still a panic vector.

**Fix:** Replace with `map_err` propagation to `PyResult`, or use `expect()` with a clear message and wrap in a `catch_unwind`.

---

### C-8. Shadow mode uses wrong accumulator path

**Source:** Integration Reviewer (MP-1)
**File:** `simulation.py:1604-1608`

Shadow/demographics-only modes use `acc.apply()` (applies guard mutations) while hybrid uses `acc.apply_keep()` (skips them). Shadow comparison is fundamentally unfair — shadow mode applies guard mutations that hybrid doesn't.

**Fix:** Shadow mode should use `acc.apply_keep()` to match hybrid semantics.

---

### C-9. Bare `civ.regions[0]` without empty-guard

**Source:** Simulation Reviewer (Finding 3)
**File:** `simulation.py:1281`

In `phase_cultural_milestones` artifact-intent code. Can `IndexError` if regions empties between the outer guard and this line.

**Fix:** `_art_region = civ.capital_region or (civ.regions[0] if civ.regions else "unknown")`

---

### C-10. No accumulator routing for any religion events

**Source:** Religion audit (Issue 2)
**Files:** `religion.py:437-555`, `religion.py:558-619`

`compute_persecution()` and `compute_martyrdom_boosts()` mutate region state directly without any `acc.add()` calls. No guard-shock or signal categorization exists for religious events. This bypasses the accumulator system entirely.

**Fix:** Route persecution and martyrdom stat changes through `acc.add()` with appropriate categories.

---

### C-11. Arc summary mutates world state (LLM feedback loop)

**Source:** Narrative audit (Critical-1)
**File:** `narrative.py:1280`

`_update_arc_summary()` mutates `GreatPerson` objects in-place, and those get serialized into the bundle via `world.model_dump_json()`. LLM narration content feeds back into persistent state, violating "LLM never decides."

**Fix:** Store arc summaries separately from world state, or deep-copy gp objects before mutation.

---

### C-12. Satisfaction formula test comments reference old divisor

**Source:** Rust Reviewer (C1)
**Files:** `satisfaction.rs:110`, `satisfaction.rs:484`

Formula divides by `200.0`, all three test comments reference the old `300.0` divisor. Tests pass only because assertions use wide ranges (`> 0.90 && <= 1.0`). The tests are actively misleading.

**Fix:** Verify intended divisor, update test comments, tighten test assertions.

---

### C-13. TypeScript types drastically incomplete vs Python models

**Source:** Viewer Data Contract audit
**File:** `viewer/src/types.ts`

- Region: 8 fields in TS, 55+ in Python
- CivSnapshot: missing 14+ fields
- TurnSnapshot: missing 18+ fields
- All silently return `undefined` at runtime

**Fix:** Regenerate types from Python models or maintain single source of truth. Required for Phase 7.5.

---

### C-14. 0.40 penalty cap and 2.5x weight cap have zero tests

**Source:** Test Reviewer
**Files:** No test file covers either invariant

Both documented cross-cutting rules (non-ecological penalty budget, combined action weight cap) have no test anywhere in the suite. The weight cap implementation doesn't even match documented semantics — it caps absolute weight value, not multiplier product.

**Fix:** Add dedicated test classes for both invariants.

---

## HIGH — Prioritized Fixes

### Economy

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-1 | Tithe extracted without food sufficiency check — priests extract tithes during famine | economy.py | 1477-1481 |
| H-2 | Wealth conservation only tracks goods, not treasury flows — potential undetected wealth creation/destruction | economy.py | 519-524 |
| H-3 | Zero-farmer regions produce massive farmer income signals (500x) | economy.py | 1430-1432 |

### Politics

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-4 | Absorbed civ `capital_region` not cleared (3 code paths) — dangling reference | politics.py | 1322, 1396, 2413 |
| H-5 | Restoration stat mutations bypass accumulator entirely — hybrid mode desync | politics.py | 1072-1077 |

### Relationships & Dynasties

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-6 | Hostage trapped forever if origin civ is extinct — no cleanup mechanism | relationships.py | 379-382 |
| H-7 | Mentorship formation: no seniority tiebreaker for same-turn births — peers paired as mentor/mentee | relationships.py | 119-157 |

### Ecology

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-8 | Terrain transitions don't clamp ecology values to `TERRAIN_ECOLOGY_CAPS` | emergence.py | 704-717 |
| H-9 | No Python validation of Rust ecology write-back values — trusts Rust entirely | ecology.py | 211-254 |

### Agent Bridge

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-10 | Gini lag resets to empty dict on snapshot exception instead of preserving prior values | agent_bridge.py | 969-973 |
| H-11 | Unprotected `ROLE_MAP[role_id]` KeyError in promotions — crash if Rust sends unexpected role | agent_bridge.py | 1397 |

### CLI / Bundle / Live Mode

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-12 | Arrow IPC file handle not wrapped in context manager — file descriptor leak | bundle.py | 97 |
| H-13 | LiveServer race condition on client disconnect — sends to None without lock | live.py | 259-283 |
| H-14 | Live narration silently dropped — dict vs array chronicle format mismatch | useLiveConnection.ts:227, live.py:480 | |

### Rust Performance

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-15 | O(n*m) `CivSignals` lookup in 3 hot loops (wealth, satisfaction, demographics) | tick.rs | 968, 1057, 1259 |
| H-16 | `partition_by_region` called 6x per tick — several consecutive stages don't move agents | tick.rs | multiple |

### Religion

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-17 | Schisms can create zero-follower faiths that clutter the registry | religion.py | 678-747 |
| H-18 | `_persecuted_regions` accumulates forever without reset — events can only fire once per simulation | simulation.py | 991-992 |

### Simulation Logic

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-19 | Holy war weight bonus is additive (`+=`) while all others are multiplicative (`*=`) | action_engine.py | 920-933 |
| H-20 | Weight cap implementation caps absolute weight, not multiplier product — effective cap is 12.5x not 2.5x | action_engine.py | 993-997 |

### Documentation

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-21 | `--agent-narrative` flag documented in CLAUDE.md but doesn't exist in CLI | CLAUDE.md | line 111 |
| H-22 | Line counts 52% stale (Python: claims ~21K, actual ~32K), 277% stale (Rust: claims ~7K, actual ~26K) | CLAUDE.md | lines 4-7 |
| H-23 | `bundle_version` documented in CLAUDE.md but never written to bundle metadata | CLAUDE.md, bundle.py | |
| H-24 | "Phase 4 bit-identical" claim between off and hybrid is false when economy tick is active | CLAUDE.md, simulation.py | |

### Cross-Boundary

| # | Finding | File | Line(s) |
|---|---------|------|---------|
| H-25 | Dead-civ population floor of 1 in Python diverges from Rust zero-count | agent_bridge.py | 2115 |
| H-26 | Great persons not cleaned up on civ extinction — modifiers still apply | action_engine.py | 573-575 |
| H-27 | Faith init before turn 0 — `civ_majority_faith` defaults to 0 before first snapshot | infrastructure.py | 216 |
| H-28 | `_conquered_this_turn` is a lazy transient attribute — not cleared in `AgentBridge.reset()`, risks leaking across batch reuse | simulation.py, agent_bridge.py | |

---

## Test Coverage Gaps (from Test Reviewer)

### CRITICAL gaps — invariants with zero test coverage

1. **0.40 satisfaction penalty cap** — no test anywhere (Python or Rust)
2. **2.5x combined weight cap** — no test anywhere
3. **Phases 4, 6, 7, 8** — no dedicated phase-function tests in `test_simulation.py`
4. **`culture_tick.rs` / `conversion_tick.rs`** — no external integration tests
5. **`demographics.rs`** — no external integration test
6. **`--agents=off` bit-identical guarantee** — no test verifies this claim
7. **Empty agent pool mid-simulation** — untested in Rust tick
8. **Schema lock tests** for region batch and civ signals — missing
9. **200-seed regression gate** — not programmatically enforced in CI

### HIGH gaps

10. MAX_WEALTH clamp not in external Rust tests
11. `satisfaction.rs` no combined-inputs external test
12. conftest fixtures miss dead-civ, single-civ, late-game worlds
13. `_stockpile_bootstrap_pending` lacks a 2-turn integration test
14. Deleted `test_m36_culture.py` / `test_m38a_factions.py` replacement coverage unclear

### Test suite stats

- **Python:** 2,308 tests across 29 test files
- **Rust:** 762 tests across 19 test files
- **Viewer:** Component smoke tests only

---

## STRATEGIC — Architecture Findings (from Phoebe)

### S-1. `ffi.rs` at 5,000 lines is the highest-risk module

Two simulator implementations, 60+ column parsers, all PyO3 bindings. Every new system adds code in 3+ locations within this one file. Most likely source of subtle bugs when new columns are added.

**Resolution:** Split into separate modules — schema definitions, batch conversion utilities, AgentSimulator impl, and EcologySimulator impl.

### S-2. Python critical path limits 9950X utilization ceiling

Phase 10 + settlement detection + economy post-processing all run single-threaded in Python after the parallel Rust tick. This is on the critical path and can't be parallelized with Rust.

**Resolution:** Continue M54-series migration trajectory. Prioritize migrating `build_region_batch()` and settlement detection to Rust.

### S-3. `politics.py` at 3,157 lines doing two jobs

Game logic (1,600 lines) and FFI integration layer (1,400 lines) share one file. Different change frequencies, different testing patterns.

**Resolution:** Split into `politics.py` (simulation mechanics) + `politics_bridge.py` (Rust FFI integration). Mirrors existing `agent_bridge.py` pattern.

---

## Module Complexity Budget (from Phoebe)

### Python (lines, approximate)

| Module | Lines | Concern |
|--------|-------|---------|
| politics.py | 3,157 | HIGH — split needed |
| agent_bridge.py | 2,243 | HIGH — extract batch builders |
| analytics.py | 2,068 | Medium — sustainable pattern |
| simulation.py | 1,771 | Medium — complex but well-structured |
| economy.py | 1,483 | Medium — stable |
| narrative.py | 1,325 | Medium — stable |
| main.py | 1,244 | Medium — orchestration, grows naturally |
| action_engine.py | 1,053 | Acceptable |
| religion.py | 930 | Acceptable |
| live.py | 923 | Acceptable |
| models.py | 918 | Acceptable |

### Rust (lines, approximate)

| Module | Lines | Concern |
|--------|-------|---------|
| ffi.rs | 4,982 | HIGH — two simulators, massive |
| politics.rs | 3,265 | HIGH — mirrors Python complexity |
| tick.rs | 1,921 | Medium — complex orchestration |
| formation.rs | 1,845 | Medium — formation scan |
| behavior.rs | 1,785 | Medium |
| pool.rs | 1,505 | Medium |
| economy.rs | 1,410 | Medium |
| merchant.rs | 1,183 | Acceptable |

---

## Clean Bills of Health

| Area | Auditor | Result |
|------|---------|--------|
| **Data models** | Models audit | Zero gotcha violations across entire codebase. All 6 known gotchas respected everywhere. Score: 9.8/10 |
| **RNG determinism** | RNG audit | All 17 stream offsets unique. Seed chain from CLI to Rust airtight. No unseeded random calls. Same seed = same output |
| **Dead code** | Dead code scan | Minimal — one unused Python function (`household_effective_wealth_py`), deprecated `social.rs`, 11 reserved Rust constants |
| **Faction weight pipeline** | Culture+Factions audit | 2.5x cap correctly enforced through action engine. Four factions properly integrated |
| **Design principles** | Phoebe | "LLM narrates, never decides" — clean (except C-11). Determinism — well-maintained. Accumulator routing — intact core |
| **Phase 6 roadmap** | Phoebe | Substantially delivered with no drift. All five capability pillars landed. Implementation tracked roadmap faithfully |
| **Bundle format** | Phoebe | Simple, forward-compatible. Arrow sidecar pattern for agent events is sound |
| **Module cohesion** | Phoebe | No circular dependencies detected. Import graph flows cleanly |

---

## Rust-Specific Findings (from Rust Reviewer)

### Determinism Concerns (fragile but currently safe)

| ID | File | Issue |
|----|------|-------|
| C2 | tick.rs:1015 | HashMap iteration in `wealth_tick` — safe only because each civ group is independent. Should use BTreeMap |
| C3 | behavior.rs:273 | `civ_data` HashMap — safe only because of post-sort. Fragile pattern |
| C4 | spatial.rs | `SPATIAL_DRIFT_STREAM_OFFSET` registered but never consumed — spatial drift is pure physics with no RNG |

### Performance

| ID | File | Issue |
|----|------|-------|
| H1 | tick.rs:968 | O(n*m) civ signal lookup in wealth loop — build lookup array before loop |
| H2 | tick.rs:64,752,889 | `alive_slots` rebuilt 3 times per tick unnecessarily |
| M9 | tick.rs:196+ | `partition_by_region` called 6+ times; reusable across non-migration stages |

### Naming / Clarity

| ID | File | Issue |
|----|------|-------|
| H3 | satisfaction.rs:127 | `shock_pen` is added (not subtracted) — naming inversion confuses auditors |
| M4 | satisfaction.rs:118-123 | Magic numbers 0.08, 0.05, 0.10 not promoted to named constants |
| L2 | agent.rs:77 | `SWITCH_OVERSUPPLY_THRESH` comment says "2.0" but value is 1.0 |

### Safety

| ID | File | Issue |
|----|------|-------|
| M2 | pool.rs:340 | `kill()` doesn't zero fields — dead slots hold stale data. Debug-mode sentinels would catch liveness check omissions |
| L1 | lib.rs:75 | `social.rs` deprecated but still compiled and re-exported |
| L3 | ffi.rs:95,141 | `civ_id` is `UInt8` in some schemas, `UInt16` in others |

### Satisfaction Formula

| ID | File | Issue |
|----|------|-------|
| M7 | satisfaction.rs:222 | Good memories can zero out persecution/cultural penalties — intent unclear |
| M8 | ffi.rs:154 | `region_state_schema` suppressed with `#[allow(dead_code)]` — no consumer |

---

## Viewer-Specific Findings

### From Viewer Components Audit

| Severity | Issue | File |
|----------|-------|------|
| CRITICAL | Logic bug — missing closing brace causes incorrect surface transitions | App.tsx:76-84 |
| HIGH | No error boundary — any component throw = white screen | App.tsx |
| HIGH | `key={i}` in event lists — React reconciliation bugs | EventLog.tsx:87, ChroniclePanel.tsx:44 |
| MEDIUM | TerritoryMap d3-force recalculates on every turn change — frame drops on large sims | TerritoryMap.tsx:150-244 |
| MEDIUM | AppShell is monolithic at 2,481 lines — unmemoized render calculations | AppShell.tsx |
| MEDIUM | No runtime validation for WebSocket JSON messages | useLiveConnection.ts:121 |

### From Viewer Data Contract Audit

| Severity | Issue |
|----------|-------|
| CRITICAL | Region interface: 8 fields in TS vs 55+ in Python |
| CRITICAL | CivSnapshot missing 14+ fields (prestige, great_persons, factions, etc.) |
| CRITICAL | TurnSnapshot missing 18+ fields (settlements, ecology, wars, climate, etc.) |
| CRITICAL | Chronicle entries: dict format in live mode, array format in bundles — format mismatch |
| HIGH | `narration_complete` handler silently drops entries in legacy dict format |
| MEDIUM | `useTimeline` maxTurn=0 edge case — incorrect initial turn |
| MEDIUM | WebSocket reconnection doesn't reset bundle state — stale data possible |

---

## Documentation Staleness (from Docs Audit)

| Severity | Issue | Location |
|----------|-------|----------|
| CRITICAL | `--agent-narrative` flag documented but doesn't exist | CLAUDE.md line 111 |
| CRITICAL | `bundle_version` documented but never written to bundles | CLAUDE.md line 109 |
| HIGH | Python line count: claims ~21K, actual ~32K (52% stale) | CLAUDE.md line 4 |
| HIGH | Rust line count: claims ~7K, actual ~26K (277% stale) | CLAUDE.md line 5 |
| MEDIUM | `--narrator` supports `gemini` mode, undocumented | CLAUDE.md line 111 |
| MEDIUM | M44 API narration described in future tense but is implemented | CLAUDE.md line 9 |
| MEDIUM | "Current Focus" section says M43b is next — M43b through M59b are done | CLAUDE.md line 202 |
| LOW | M47d war frequency fix not mentioned in cross-cutting rules | CLAUDE.md lines 129-146 |

---

## Cross-Boundary Integration Findings (from Integration Reviewer)

| ID | Boundary | Severity | Description |
|----|----------|----------|-------------|
| FFI-1 | Python-Rust | BLOCKING | Stability recovery (keep) applied then overwritten by Rust write-back every turn |
| MP-1 | Mode Parity | CRITICAL | Shadow mode uses `acc.apply()` while hybrid uses `acc.apply_keep()` — unfair comparison |
| SIG-1 | Signal Flow | WARNING | Climate shocks bypass accumulator via `pending_shocks` — inconsistent with other signals |
| WB-2 | Write-Back | WARNING | Dead-civ population floor of 1 in Python diverges from Rust zero-count |
| CS-1 | Cross-System | WARNING | Tech advancement rate diverges between off and hybrid — "Phase 4 bit-identical" claim overstated |
| CS-2 | Cross-System | WARNING | `_conquered_this_turn` is lazy transient attribute — risks leaking across batch reuse |
| BUN-1 | Bundle | WARNING | `bundle_version` absent from `assemble_bundle()` despite CLAUDE.md claim |
| BUN-3 | Bundle | NOTE | Live mode uses legacy dict chronicle format; `narration_complete` drops entries |
| WS-2 | WebSocket | NOTE | `JSON.parse` in viewer has no try/catch — NaN/inf from Python would break handler |

---

## Dead Code (from Dead Code Scan)

### Safe to Delete Now

- `agent_bridge.py:2217` — `household_effective_wealth_py()` — diagnostics helper, never called

### Delete After Migration

- `social.rs` (entire file) — deprecated M50a, still compiled and re-exported
- `ffi.rs:1650` — `social_graph` field in `AgentSimulator` — unused holdover

### Reserved Constants (11 unused Rust stream offsets)

These are registered in `STREAM_OFFSETS` but never consumed. Either consume them when the corresponding feature adds RNG, or document as reserved:

- `MIGRATION_STREAM_OFFSET = 200`
- `GOODS_ALLOC_STREAM_OFFSET = 800`
- `MEMORY_STREAM_OFFSET = 900`
- `MULE_STREAM_OFFSET = 1300`
- `RELATIONSHIP_STREAM_OFFSET = 1100`
- `SPATIAL_DRIFT_STREAM_OFFSET = 2001`
- `MERCHANT_ROUTE_STREAM_OFFSET = 1700`
- `MARRIAGE_STREAM_OFFSET = 1600`
- `PROMOTION_DEFAULT_INTENSITY = 70`
- `SETTLEMENT_GRID_SIZE = 10`
- `PACKET_TYPE_EMPTY = 0`

---

## Recommended Fix Ordering

### Phase 1: Blocking (do first)

1. B-1 — Stability write-back override
2. B-2 — Inverted persecution intensity
3. B-3 + C-5 — Wire persecution satisfaction penalty correctly (Python constant + Rust BELIEF_NONE guard)

### Phase 2: Critical correctness

4. C-4 — Pandemic severity multiplier
5. C-6 — EvictSlot rel_count corruption
6. C-2 — Guard category behavior definition
7. C-8 — Shadow mode accumulator path
8. C-9 — Bare `civ.regions[0]` guard
9. C-10 — Religion accumulator routing
10. C-1 — `att_idx`/`def_idx` unconditional assignment
11. C-3 — Dynasty KeyError guards
12. C-7 — FFI unwrap safety
13. C-11 — Arc summary world state mutation

### Phase 3: High-priority fixes

14. H-4 — Absorbed civ capital_region cleanup
15. H-5 — Restoration accumulator routing
16. H-6 — Hostage extinction cleanup
17. H-10 — Gini lag exception handling
18. H-18 — `_persecuted_regions` reset
19. H-17 — Zero-follower faith cleanup
20. H-1 — Tithe food sufficiency check

### Phase 4: Test coverage

21. C-14 — 0.40 penalty cap test
22. C-14 — 2.5x weight cap test
23. Phase function tests (4, 6, 7, 8)
24. culture_tick / conversion_tick external tests
25. `--agents=off` bit-identical test
26. Schema lock tests for region batch

### Phase 5: Documentation

27. H-21 — Remove `--agent-narrative` from CLAUDE.md
28. H-22 — Update line counts
29. H-23 — Clarify `bundle_version` status
30. H-24 — Fix "Phase 4 bit-identical" claim
31. Update "Current Focus" section

### Phase 6: Architecture (next milestone window)

32. S-3 — Split `politics.py`
33. S-1 — Split `ffi.rs`
34. Extract `agent_bridge.py` batch builders
35. Consolidate `pending_shocks` routing pattern

---

## Audit Agents

| # | Agent Type | Scope | Duration | Tool Calls |
|---|-----------|-------|----------|------------|
| 1 | Rust Reviewer | chronicler-agents/src/ full crate | ~6 min | 50 |
| 2 | Simulation Reviewer | Python simulation logic, all phases | ~7 min | 69 |
| 3 | Test Reviewer | tests/ + Rust tests, coverage gaps | ~11 min | 137 |
| 4 | Integration Reviewer | FFI, viewer-bundle, cross-system | ~10 min | 88 |
| 5 | Phoebe | Architecture alignment, vision, roadmap | ~8 min | 79 |
| 6 | Explore | economy.py — goods, pricing, trade | ~2 min | 47 |
| 7 | Explore | politics.py — governance, secession | ~3 min | 53 |
| 8 | Explore | action_engine.py + accumulator.py | ~2 min | 31 |
| 9 | Explore | ecology.py + climate.py | ~2 min | 34 |
| 10 | Explore | religion.py — faith, schisms | ~2 min | 30 |
| 11 | Explore | relationships.py + dynasties.py | ~2 min | 34 |
| 12 | Explore | agent_bridge.py — FFI bridge | ~3 min | 57 |
| 13 | Explore | models.py — Pydantic consistency | ~3 min | 109 |
| 14 | Explore | narrative.py + curator.py | ~2 min | 49 |
| 15 | Explore | world_gen.py + resources.py + infrastructure.py | ~2.5 min | 55 |
| 16 | Explore | Viewer components — React/TS | ~2 min | 57 |
| 17 | Explore | Viewer data contract — types vs bundle | ~2 min | 46 |
| 18 | Explore | Documentation staleness — specs vs code | ~2 min | 49 |
| 19 | Explore | Dead code scan | ~4 min | 68 |
| 20 | Explore | RNG determinism — seeding, streams | ~3.5 min | 81 |
| 21 | Explore | CLI + bundle + analytics + validate | ~2 min | 34 |
| 22 | Explore | Culture + factions — four factions | ~2 min | 52 |
