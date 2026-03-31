# Chronicler Full Codebase Audit — Opus 4.6

**Date:** 2026-03-31
**Model:** Claude Opus 4.6 (1M context)
**Scope:** Complete codebase at commit `d9baf0a` (post-M59b merge on `main`)
**Method:** 22 specialized subagents covering Rust quality, simulation logic, test coverage, cross-boundary integration, dead code, next steps, viewer, Pydantic models, performance, security, economy, git/deps, architecture (Phoebe), narrative/LLM, religion/culture, spatial/settlements, social systems, politics/diplomacy, ecology/climate, action engine/emergence, CLI/scenarios, and naming/style.

---

## Executive Summary

The codebase is architecturally sound and impressively disciplined for a 57K-line project built in a single month (1,171 commits, zero reverts). The 10-phase turn loop + agent tick design has survived 30+ milestones without structural failure. The Rust agent layer is clean, deterministic, and well-tested (762 tests). Python test coverage is extensive (2,246 tests).

However, this audit found **7 blocking/critical bugs**, **12 high-severity issues**, **28 medium-severity issues**, and numerous low/info items. The most dangerous findings are: positive events routed as negative shocks in the accumulator (penalizing agents for good things), several core political systems that are dead-wired (federations don't defend, vassalization never triggers, governing distance costs zero stability), religion subsystems that never fire (schism conversion, martyrdom decay), and a structural impossibility in the ecology system (rewilding can never occur).

**Recommendation:** Address blocking bugs and high-severity items before proceeding to M60a. The political dead-wiring and accumulator misrouting are the highest-impact fixes — they affect simulation behavior every turn.

---

## Codebase Statistics

| Metric | Value |
|--------|-------|
| Python source files | 57 |
| Python source lines | ~31,500 |
| Rust source files | 26 |
| Rust source lines | ~26,000 |
| Viewer (React/TS) lines | ~5,700 |
| Python tests | 2,246 passing (4 skipped) |
| Rust tests | 762 passing (2 skipped) |
| Viewer tests | 83 passing |
| Total commits | 1,171 (all March 2026) |
| Reverted commits | 0 |
| Stale branches | 0 (main only) |

**Note:** CLAUDE.md claims ~21K Python / ~7K Rust. Actual counts are ~31.5K / ~26K — significantly outdated.

---

## BLOCKING / CRITICAL Findings

### B-1: Positive events routed as `guard-shock` penalize agents instead of helping them
**Files:** `simulation.py:759-778`, `accumulator.py:137`
**Source:** Simulation Reviewer

Discovery events route `economy +10` and `culture +10` as `"guard-shock"`. In `to_shock_signals()`, positive deltas produce positive normalized shock values. In Rust's `compute_shock_penalty`, positive shock values **increase** the penalty (worse satisfaction). This means:
- A lucky discovery **penalizes** merchants and scholars
- A cultural renaissance **penalizes** scholars and priests
- A religious movement culture gain **penalizes** agents

Same issue affects `cultural_renaissance` (`culture +20`, `stability +10`) and `religious_movement` (`culture +10`). All positive guard-shock deltas worsen satisfaction.

**Fix:** Route positive event gains as `"guard-action"` (demand signals) or `"guard"` (skip in agent mode). Do not use `"guard-shock"` for windfalls.

### B-2: `replace_social_edges()` FFI uses positional `.unwrap()` — process abort on bad input
**File:** `ffi.rs:2636-2639`
**Source:** Rust Reviewer, Integration Reviewer

The only FFI function that accesses Arrow columns by position (`.column(0)` through `.column(3)`) with chained `.unwrap()`. Every other column access in ffi.rs uses `column_by_name()` with graceful error returns. A column reordering in Python or unexpected type would panic and abort the entire Python process — PyO3 0.28 does not catch Rust panics.

**Fix:** Replace with `column_by_name("agent_a")` etc., convert downcast failures to `PyErr`.

### B-3: Schism conversion is dead-wired — schisms never split religious populations
**File:** `conversion_tick.rs`, `religion.py`
**Source:** Religion/Culture Reviewer

`schism_convert_from` / `schism_convert_to` are set in Python, passed through FFI to Rust, but **never consumed** in `conversion_tick.rs` or `tick.rs`. Schisms create new faiths with zero adherents. The entire schism system is narrative-only — it never actually converts agents at the agent level.

### B-4: Martyrdom boost never decays — permanent conversion rate inflation
**File:** `religion.py:594`
**Source:** Religion/Culture Reviewer

`decay_martyrdom_boosts()` is implemented but **never called**. Not imported in `simulation.py`. Once martyrdom boost accumulates (up to 0.20 cap), it persists permanently on the region, inflating conversion rates forever.

### B-5: Martyrdom boost applies to ALL deaths, not persecution deaths
**File:** `religion.py`
**Source:** Religion/Culture Reviewer

`compute_martyrdom_boosts()` receives all agent deaths (old age, war, disease, famine), not just deaths caused by persecution. Any death in a region increases martyrdom boost regardless of cause or faith. Should filter for minority-faith deaths in persecuted regions.

### B-6: Rewilding (plains → forest) is structurally impossible
**Files:** `ecology.py:169`, `ecology.rs:86`
**Source:** Ecology Reviewer

The rewilding counter requires `forest_cover > 0.7` for plains regions, but Rust ecology clamps plains forest at 0.40 every tick (`TERRAIN_CAPS`). The counter can never increment. The M54a Rust migration likely re-broke this. Rewilding was reported fixed in M19b, but the Rust hard clamp makes it impossible.

### B-7: Federations provide zero mutual defense — core spec feature unimplemented
**File:** `politics.py:719-741`
**Source:** Politics Reviewer

`trigger_federation_defense()` is defined but **never called** from production code. The M14 spec explicitly states federation members should automatically enter war when an ally is attacked. `_resolve_war_action()` never calls it. Federations are cosmetic alliances.

---

## HIGH Severity Findings

### H-1: `war_start_turns` never populated — congress ignores war duration
**File:** `politics.py:732, 875-879`
**Source:** Politics Reviewer

Only assigned in `trigger_federation_defense()` (dead code). Congress power formula always divides by 1 instead of war duration. Short and long wars have identical congress leverage.

### H-2: Vassalization path is dead code — wars always absorb
**File:** `politics.py:420-472`
**Source:** Politics Reviewer, Next Steps Analyst

`choose_vassalize_or_absorb()` and `resolve_vassalization()` exist but are never called. War resolution always takes regions directly. Vassals can only exist from initial state or Rust politics ops.

### H-3: Governing cost stability penalty is always zero
**File:** `politics.py:68`
**Source:** Politics Reviewer

`gov_cost_per_dist = int(get_override(world, K_GOVERNING_COST, 0.5))` — `int(0.5)` = 0. Large empires pay treasury costs but suffer zero stability penalty for governing distance.

### H-4: `thread_domains()` is a complete no-op
**File:** `narrative.py:768-777`
**Source:** Narrative Reviewer

Function accepts text, civ_name, and civ_domains but always returns text unchanged. Tests verify it returns input unchanged. Should be deleted or implemented.

### H-5: 16 open P0 bugs from March 29 audit remain unaddressed
**Source:** Next Steps Analyst

The March 29 audit identified 23 bugs. Only 7 were fixed in the hardening pass. 16 remain open including: crisis halving no-op in hybrid mode, war cost treasury check stale in acc mode, adjacency mask overflow >32 regions, CivSnapshot.alive hardcoded True, duplicate `build_region_postpass_patch_batch`, dead agents never set (martyrdom dead-wired), prev_turn_water double-write, EVENT_TYPE_MAP hard-indexes, path traversal guard (now fixed per security audit), empty civs list crash, dead civs in disaster targeting.

### H-6: No leader trait maps to CLERGY faction
**File:** `leaders.py`
**Source:** Religion/Culture Reviewer

`zealous` maps to CULTURAL, not CLERGY. Clergy never gets the leader alignment bonus the other 3 factions enjoy. Clergy dominance is structurally harder than intended.

### H-7: M47d War Frequency fix not yet implemented
**Source:** Next Steps Analyst

Spec and plan written, Phoebe-reviewed. 4 mechanisms designed (damper, weariness, peace dividend, secession modifier). War frequency is 204-508 per 500-turn run vs target 5-40. Building M60a campaign logistics on top of 10-50x excessive war frequency will create calibration hell.

### H-8: `ffi.rs` at 4,955 lines — must split before M60a
**Source:** Phoebe Architecture Review

Every new system touches this file. M60a will add campaign state serialization, pushing it past 5,500+. Split into: `ffi_schemas.rs`, `ffi_simulator.rs`, `ffi_ecology.rs`, `ffi_politics.rs`, `ffi_signals.rs`.

### H-9: `events_timeline` grows unboundedly with O(turns×C) scans per turn
**Files:** `models.py:664`, `factions.py:300`
**Source:** Performance Reviewer

`tick_factions()` linearly scans the full timeline per civ per turn. At turn 500 with 8 civs: 40,000+ event checks per turn. Never trimmed.

### H-10: `graph_distance()` rebuilds adjacency map from scratch on every call
**File:** `adjacency.py:38-45`
**Source:** Performance Reviewer

Called ~72 times per turn from governing costs, secession checks, capital relocation. Each call constructs a full adjacency dict and runs BFS. O(R × BFS) per call.

### H-11: `get_snapshot()` serializes full agent pool 2-3x per turn
**Files:** `simulation.py:1602`, `agent_bridge.py:920`
**Source:** Performance Reviewer

Each call serializes ~5000 agents × ~30 columns into Arrow RecordBatch (~600KB), then converts columns to Python lists via `.to_pylist()`. 1.2-1.8MB of data created and discarded per turn.

### H-12: `conquest_conversion_active` persists indefinitely in `--agents=off` mode
**File:** `agent_bridge.py:269-289`
**Source:** Simulation Reviewer

Flag is cleared only when `compute_conversion_signals` runs with a non-None snapshot. In off-mode, snapshots don't exist, so the flag is never cleared. Conquered regions accumulate stale True flags.

---

## MEDIUM Severity Findings

### M-1: `deprecated social.rs` still compiled and allocated on every `AgentSimulator`
**Files:** `lib.rs:21`, `ffi.rs:1648`
**Source:** Rust Reviewer, Social Systems Reviewer

`SocialGraph` field is dead weight, allocated but never meaningfully read/written.

### M-2: `partition_by_region()` called 7+ times per tick — redundant O(capacity) work
**File:** `tick.rs:195,370,415,462,763,788,807`
**Source:** Rust Reviewer

Each call allocates fresh `Vec<Vec<usize>>` and iterates all pool slots. Only 2 calls are structurally required (pre-decision and post-migration).

### M-3: Per-agent `iter().find()` O(C) scans in hot loops
**File:** `tick.rs:961,1050`
**Source:** Rust Reviewer

`signals.civs.iter().find(|c| c.civ_id == civ)` runs inside per-agent loops. With 5000 agents × 8 civs = 80,000 linear scans per turn. Comments already describe the O(1) fix (pre-build lookup array) but it hasn't been applied.

### M-4: `region_map` rebuilt ~25 times per turn ad-hoc
**Source:** Performance Reviewer, Dead Code Scanner

22 ad-hoc `{r.name: r for r in world.regions}` rebuilds across 10 files. `invalidate_region_map()` is defined but never called.

### M-5: Transport cost formula differs between Python oracle and Rust
**File:** `economy.py:483` vs `economy.rs:410-423`
**Source:** Economy Reviewer

Python uses `max(cost_a, cost_b)` for terrain factor; Rust uses `(cost_a + cost_b) / 2.0`. Python treats river/coastal as mutually exclusive; Rust stacks both (0.5 × 0.6 = 0.3). Three different transport cost functions exist total.

### M-6: Rust zero-population stockpile cap destroys goods Python would preserve
**File:** `economy.rs:1165`
**Source:** Economy Reviewer

Python `apply_stockpile_cap` skips zero-pop regions. Rust computes `cap = 2.5 * 0 = 0.0`, zeroing all stockpiled goods.

### M-7: Embargoes are permanent — no expiry, decay, or removal mechanism
**File:** `action_engine.py:370`
**Source:** Action Engine Reviewer

Embargoes only grow via `.append()`. DIPLOMACY action clears wars but not embargoes. Late-game trade networks permanently degrade.

### M-8: `NarrationContext` model defined but never instantiated
**File:** `models.py:896`
**Source:** Narrative Reviewer

The structured model was bypassed during implementation. `_prepare_narration_prompts()` builds raw dicts instead. Dead code that misleads developers.

### M-9: No retry/backoff on API LLM clients
**File:** `llm.py`
**Source:** Narrative Reviewer

`AnthropicClient.complete()` and `GeminiClient.complete()` have zero retry logic. Transient failures silently degrade to mechanical summaries.

### M-10: Live mode `narrate_range` blocks WebSocket handler
**File:** `live.py`
**Source:** Narrative Reviewer

Synchronous LLM calls (30-60s at 2-3 tk/s) block the entire WebSocket handler. Other messages (speed, quit) cannot be processed during narration.

### M-11: WebSocket `JSON.parse` has no try/catch — malformed message kills processing
**File:** `viewer/src/hooks/useLiveConnection.ts`
**Source:** Viewer Reviewer

Malformed server message throws in `onmessage` handler. Connection silently stops processing all future messages with no user-visible error.

### M-12: `bundle_version` field absent from bundle despite CLAUDE.md claiming it exists
**Files:** `bundle.py`, CLAUDE.md
**Source:** Multiple reviewers

`assemble_bundle()` never writes `bundle_version` into metadata. Viewer doesn't declare it either. Documentation says it exists.

### M-13: `--agent-narrative` flag documented in CLAUDE.md but doesn't exist in code
**Source:** CLI Reviewer

Zero usage in production code. The flag was either removed or never implemented as a CLI flag.

### M-14: Governing cost stability always zero (`int(0.5)` = 0)
**(Duplicate of H-3, listed here for completeness)**

### M-15: Dead faiths accumulate in `belief_registry` — can fill MAX_FAITHS (16)
**Source:** Religion/Culture Reviewer

When a faith has zero adherents, the Belief object remains. Schisms creating new faiths can exhaust the 16-slot limit with dead faiths.

### M-16: Plague stability drain skips severity multiplier
**File:** `simulation.py:168`
**Source:** Ecology Reviewer

`drain = int(get_override(world, K_PLAGUE_STABILITY, 3))` — missing `* mult`. Population loss correctly uses multiplier, but stability drain is flat.

### M-17: No top-level exception handler — agent bridge leaks on unhandled errors
**File:** `main.py`
**Source:** CLI Reviewer

If `execute_run()` throws, `agent_bridge.close()` is skipped. File handles leak, shadow logger truncates.

### M-18: WebSocket scenario path traversal via unsanitized `params["scenario"]`
**File:** `live.py:710`
**Source:** Security Reviewer

Client can send `"../../sensitive_file.yaml"`. Mitigated by localhost-only binding, but the read itself succeeds.

### M-19: 42 unused tuning constants in `tuning.py`
**Source:** Dead Code Scanner

Out of 192 total. Mostly ecology-related constants orphaned when ecology moved to Rust (M54a).

### M-20: 29 dead imports across Python source files
**Source:** Dead Code Scanner

6 in `simulation.py`, 4 in `narrative.py`, 3 in `action_engine.py`, 4 in `infrastructure.py`. Plus 154 dead imports in test files.

### M-21: Ecology-satisfaction same-turn echo loop drives fast cascade behavior
**Source:** Integration Reviewer

Ecology degrades → satisfaction drops → rebellion/migration → population drops → next ecology tick sees different population. No delay buffer between ecology and satisfaction.

### M-22: Asabiya not sent as FFI signal — agents don't know regional solidarity
**Source:** Integration Reviewer

`civ.asabiya` is computed before the bridge tick but not sent as part of `CivSignals`. Agents make migration/rebellion decisions without knowledge of their region's solidarity state.

### M-23: Marriage scan is O(E²) per region with no pair-evaluation cap
**File:** `formation.rs`
**Source:** Spatial/Settlement Reviewer

Unlike `formation_scan` (which has `MAX_NEW_BONDS_PER_REGION`), marriage_scan evaluates ALL eligible pairs. A capital region with 1000+ eligible agents would evaluate 500K+ pairs.

### M-24: `pending_shocks` dual-use semantics — same-turn vs next-turn not distinguished
**File:** `simulation.py:1580`
**Source:** Integration Reviewer

Comment says "Fold pending_shocks from last turn's Phase 10" but Phase 1 conditions also write same-turn shocks to the same list. Two buffering semantics through one list.

### M-25: `civ_id` type mismatch — `UInt16` in schema, `u8` in `compute_aggregates`
**Files:** `ffi.rs:92`, `pool.rs:725`
**Source:** Integration Reviewer

Schema declares `civ_id` as `UInt16`, but the internal key is `u8`. Civ IDs > 255 would overflow the u8 key without error.

### M-26: Double serialization in bundle assembly
**File:** `bundle.py`
**Source:** Narrative Reviewer

`json.loads(model.model_dump_json())` serializes to JSON string then immediately parses back to dict. `model.model_dump()` would produce the dict directly.

### M-27: Duplicated twilight absorption code blocks with divergent exile data
**File:** `politics.py:1286-1436`
**Source:** Politics Reviewer

Two nearly identical absorption paths diverge in exile `conquered_regions` construction.

### M-28: `create_exile()` function is dead code
**File:** `politics.py:968`
**Source:** Politics Reviewer

Never called. War-eliminated civs never get exile modifiers — governments-in-exile only form from twilight absorption.

---

## Architecture Assessment (Phoebe Review)

### What's Working Well
- **Turn loop + agent tick model** has survived 30+ milestones without structural failure
- **Accumulator pattern** (5 routing categories) correctly separates aggregate vs. agent mode
- **SoA agent pool** in Rust is cache-friendly and well-parallelized
- **Knowledge packet substrate** (M59a/b) is well-designed with clear extension points
- **Economy layering** (M42 goods on top of abstract) is clean
- **Determinism** is rock-solid — explicit seeded RNG throughout, no global state

### Pre-M60a Blocking Work
1. **Split `ffi.rs`** (4,955 lines) — campaign FFI will push past 5,500
2. **Extract `run_turn` parameters** into `RuntimeServices` dataclass (currently 8 params, M60a adds more)

### Pre-M60a High Priority
3. **Systematic mode parity audit** on 86 `if acc is not None` sites
4. **CivSignals test builder** — every Rust test breaks when a field is added
5. **RegionState test helper** — same cascading breakage problem
6. **M47d war frequency** — building campaigns on 10-50x excessive wars is backwards

### Observations
- Per-agent byte budget is ~290, not documented 242
- Knowledge packet 4-slot count should be validated at M61b scale
- Tick sub-phase numbering (0, 0.5, 0.75, 0.8, 0.9, 0.95, 1, 2, 3, 4, 4.5, 5, 5.1, 8) is accretive
- Bundle v2 should define stable vs. provisional layers for Phase 7.5

---

## Performance Hot Spots (Top 10)

| Rank | Issue | Impact | Scaling |
|------|-------|--------|---------|
| 1 | `events_timeline` unbounded + O(turns×C) scans | High | O(turns × C) per turn |
| 2 | `graph_distance()` rebuilds adj map per call (~72/turn) | High | O(R × BFS) × 72 |
| 3 | `get_snapshot()` full pool serialization 2-3x/turn | High | O(agents × cols) × 3 |
| 4 | `get_active_trade_routes()` O(R²) called 3x/turn | High | O(R² × A) × 3 |
| 5 | `region_map` rebuilt ~25x/turn ad-hoc | High | O(R) × 25 |
| 6 | `agent_events_raw` unbounded growth | High | O(events × turns) |
| 7 | `civ_index()` O(C) linear scan, 58 call sites | Medium | O(C²) aggregate |
| 8 | `to_pylist()` Arrow→Python in nested loops | Medium | O(agents × regions) |
| 9 | `signals.civs.iter().find()` O(C) per agent in Rust | Medium | O(agents × C) |
| 10 | `partition_by_region()` dead-slot scan, 7+ calls/tick | Medium | O(capacity) × 7 |

**At 32 civs / 50K agents:** Python-side overhead dominates. `get_snapshot()` becomes ~6MB per call (2-3x/turn = 12-18MB). `events_timeline` scans become 800K+ comparisons. `civ_index()` becomes 1,856 linear scans. Rust tick scales well via rayon.

---

## Test Coverage Gaps

### Untested Simulation Phases
- **Phase 3 (Politics):** No integration test verifying accumulator routing
- **Phase 4 (Military):** No dedicated test class for maintenance phase
- **Phase 5 (Diplomacy):** No integration test in `test_simulation.py`
- **Phase 7 (Tech):** Single smoke test, no accumulator verification

### Untested Rust Modules
- `named_characters.rs` — zero tests anywhere
- `conversion_tick.rs` — no dedicated tests
- `culture_tick.rs` — no dedicated tests
- `demographics.rs` — only indirect coverage via determinism tests

### Missing Cross-Cutting Tests
- **0.40 satisfaction penalty cap** — tested in Rust only, not end-to-end from Python
- **2.5x action weight cap** — untested in both suites
- **EXPAND vs WAR `conquered_this_turn`** — no negative test confirming EXPAND doesn't set it
- **Economy→Satisfaction→Migration chain** — tested only at unit level, never end-to-end

### Regression Methodology Weakness
- `test_m36_regression.py` asserts `>= 0` (trivially true, not a regression)
- 3 integration tests hang since M47 (silently not running)
- No `pytest-timeout` configured — hanging tests block CI indefinitely
- `conftest.py` fixtures missing agent mode variants and Phase 6-7 field defaults

---

## Security Assessment

| Severity | Finding |
|----------|---------|
| Medium | Scenario path traversal via WebSocket (`live.py:710`) — unsanitized `params["scenario"]` |
| Medium | `WorldState.model_validate()` from WebSocket (`live.py:698`) — adversarial payload could cause OOM |
| Low | No WebSocket authentication (localhost-only mitigates) |
| Low | No WebSocket origin validation (CORS) |
| Low | Prompt injection from simulation data into LLM (output-only, no code execution) |
| None | No pickle, eval, exec, subprocess in source |
| None | No hardcoded secrets; API keys from env vars |
| None | No temporary files created |
| Fixed | Path traversal in `batch_load_report` (March 29 item, now uses `is_relative_to`) |

---

## Technical Debt Inventory

### Deprecated Code Still Active
- `social.rs` — marked DEPRECATED M50a, still compiled and allocated
- `replace_social_edges()` — marked "will be removed in M50b", still called from Python
- `check_marriage_formation()` in Python — marked DEPRECATED M57a, still called at runtime

### Dead Code
- `trigger_federation_defense()` — never called (HIGH impact)
- `choose_vassalize_or_absorb()` / `resolve_vassalization()` — never called (HIGH impact)
- `create_exile()` — never called
- `thread_domains()` — complete no-op
- `NarrationContext` model — defined, never instantiated
- `ActionCategory` enum — defined, never used
- `HistoricalFigure` model — defined, never populated during simulation
- 42 unused tuning constants
- 29 dead imports in source files

### Documentation Drift
- CLAUDE.md line counts outdated (claims 21K Python/7K Rust, actual 31.5K/26K)
- CLAUDE.md lists `--agent-narrative` flag that doesn't exist
- CLAUDE.md file tables missing 31 Python files and 11 Rust files
- Penalty cap priority order undocumented for `urban_safety` and `memory` terms
- Phase numbering in `simulation.py` docstring doesn't match actual execution order

### Stale Worktrees
- `.worktrees/m10-workflow-features` — dead directory
- `.worktrees/m36-cultural-identity` — dead directory
- `.worktrees/m52-artifacts` — dead directory

---

## Deferred Items Inventory

### Deferred from M59b (by design)
- Loyalty coupling (requires `source_civ` on packets)
- Religious signal consumers (producer-only)
- Packet layout expansion

### Deferred to M47/Tuning
- M42+M43a 200-seed regression (never run)
- `K_PEAK_YIELD` has no consumer
- 19 sites still rebuild region_map ad-hoc
- 3 integration tests hang

### Deferred to M61b
- Market attractor (reserved, inactive)
- Disease proximity spreading
- Settlement calibration constants
- 200-seed regression sweep (blocked on hybrid smoke)

### Deferred to Future (Unspecified)
- M44: Sequential batch token bleed across seeds
- M48: Promotion intent not generated Python-side
- M48: Victory memories not civ-filtered
- M49: 10 calibration flags (persecution stacking, famine double-counting)
- M50b: Dissolution events lack dead target's agent_id
- M51: Legitimacy activation rate unmeasured
- M57a: Regression dip investigation

---

## Recommended Pre-M60a Priority Order

### Priority 1: Blocking Bugs (fix immediately)
1. **B-1:** Fix positive guard-shock routing — discovery/renaissance/religious_movement
2. **B-2:** Fix `replace_social_edges` positional unwrap
3. **B-3:** Wire schism conversion in `conversion_tick.rs`
4. **B-4:** Wire `decay_martyrdom_boosts()` into turn loop
5. **B-5:** Filter martyrdom to persecution deaths only
6. **B-6:** Fix rewilding counter threshold vs terrain cap
7. **B-7:** Wire `trigger_federation_defense()` into war resolution

### Priority 2: High-Impact Fixes
8. **H-3:** Fix governing cost `int(0.5)` = 0
9. **H-1:** Populate `war_start_turns` in war resolution
10. **H-7:** Implement M47d war frequency (spec + plan exist, Phoebe-reviewed)

### Priority 3: Pre-M60a Architecture
11. **H-8:** Split `ffi.rs` into sub-modules
12. Extract `run_turn` parameters into `RuntimeServices`
13. Add `CivSignals::test_default()` and `RegionState` test helpers
14. Fix the 3 hanging integration tests

### Priority 4: Remaining March 29 Audit Items
15. Address the 16 open P0/P1 bugs from the prior audit
16. Systematic mode parity audit on accumulator sites

### Priority 5: Performance (before M61b scale)
17. Cache `graph_distance` adjacency map per turn
18. Cache `get_active_trade_routes()` (called 3x with same inputs)
19. Use `world.region_map` instead of ad-hoc rebuilds (22 sites)
20. Add turn-index to `events_timeline` or trim old events
21. Pre-build `[Option<&CivSignals>; 256]` lookup in Rust tick

### Priority 6: Cleanup
22. Remove deprecated `social.rs` and its shim
23. Delete dead code (federation defense, vassalization, create_exile, thread_domains)
24. Clean up 42 unused tuning constants
25. Remove 29 dead imports
26. Update CLAUDE.md line counts, file tables, flag documentation

---

## Strengths Worth Preserving

- **Commit discipline:** Consistent conventional commits, zero reverts, clear milestone scoping
- **Determinism guarantees:** Explicit seeded RNG, stream offsets, no global state
- **Accumulator pattern:** Correctly encapsulates the aggregate/agent mode split
- **Conservation law tracking:** Production = consumption + sinks, verified per turn
- **Anti-omniscience rule:** Packets exist but unprofitable → no oracle fallback
- **Viewer quality:** Strict TypeScript, zero `any`, 83 tests, minimal dependencies
- **Scenario system:** Thorough validation, proper precedence resolution
- **Rust agent layer:** SoA layout, rayon parallelism, saturating arithmetic, no unsafe

---

*Generated by Claude Opus 4.6 (1M context) across 22 specialized subagents. Total analysis covered all 57 Python source files, 26 Rust source files, 25 viewer files, 97 Python test files, 22 Rust test files, progress/roadmap/spec/plan documentation, and git history.*
