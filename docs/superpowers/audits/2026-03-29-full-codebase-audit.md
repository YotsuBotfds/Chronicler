# Chronicler Full Codebase Audit — 2026-03-29

10-agent team audit covering correctness, code quality, architecture, and project direction across all 53 Python files, the Rust agent crate, and the React/TS viewer.

**Test suite status at time of audit:** 2,193 Python tests passed (4 skipped), 680 Rust tests passed (2 skipped). Zero failures.

---

## Executive Summary

The codebase is in strong shape for a 21K-line Python + 7K-line Rust + 5K-line TypeScript project at milestone M57b. Architecture is sound, determinism is well-maintained, test coverage is thorough, and the Phase 6-8 roadmap is well-structured.

That said, the audit found **8 real bugs**, **6 behavioral divergences between aggregate/hybrid modes**, **4 dead code paths**, and a handful of design-level concerns that should be addressed before Phase 8 adds institutional complexity.

### Top 5 findings by impact:

1. **Dual `STAT_FLOOR` definitions** (accumulator=5, utils=0) silently produce different stat clamping depending on code path and mode
2. **Crisis halving + war cost treasury check** are both broken in hybrid/accumulator mode — behavioral divergence between `--agents=off` and `--agents=hybrid`
3. **Proxy detection gives +5 stability instead of -5** (sign error)
4. **15 bare `except Exception: pass`** blocks in `agent_bridge.py` silencing real errors including stale Gini data
5. **FactionDashboard sparklines actively broken** — maxVal hardcoded to Phase 2 scales (10) when stats are now 0-100

---

## Part 1: Bugs (fix these)

### P0 — Correctness bugs affecting simulation behavior

| # | Bug | Location | Description |
|---|-----|----------|-------------|
| 1 | **Dual STAT_FLOOR** | `accumulator.py:16-22` vs `utils.py:44-50` | Accumulator floors stats at 5, direct mutations floor at 0. Same stat change produces different results depending on code path. Latent mode divergence. |
| 2 | **Crisis halving no-op in hybrid mode** | `simulation.py:552-559` | Accumulator doesn't mutate stats directly, so before/after comparison always sees no change. Civs in succession crises get full stat gains in hybrid mode but halved in aggregate. |
| 3 | **War cost treasury check stale in acc mode** | `simulation.py:317-320` | Checks `c.treasury <= 0` but the -3 deduction went through the accumulator, not the field. Civ at treasury=2 skips stability drain in hybrid but correctly drains in aggregate. |
| 4 | **Proxy detection sign error** | `politics.py:823-828` | Gives +5 stability to target on detection. Being caught funding separatists should be destabilizing, not stabilizing. |
| 5 | **`detect_reformation` reads unset `_current_turn`** | `religion.py:894` | `getattr(civ, '_current_turn', 0)` — attribute is never written anywhere. All Reformation events report turn=0. |
| 6 | **`reset()` doesn't clear `_gini_by_civ`** | `agent_bridge.py:1938-1949` | In batch mode reuse, stale Gini from a previous seed leaks into the next run's first tick, corrupting satisfaction calculations. |
| 7 | **Drought stability drain skips severity multiplier** | `simulation.py:139-142` | Uses raw `K_DROUGHT_STABILITY` without `mult`. Economy drain correctly uses `int(10 * mult)`. Violates the cross-cutting rule. |
| 8 | **`check_rival_fall` called without `acc`** | `simulation.py:715` | +10 culture bonus bypasses accumulator in hybrid mode, applied as direct mutation inconsistent with all other stat changes. |

### P1 — Latent bugs / fragile code

| # | Bug | Location | Description |
|---|-----|----------|-------------|
| 9 | **Adjacency mask overflow >32 regions** | `agent_bridge.py:201-207` | `1 << idx` stored as `pa.uint32()`. Worlds with 33+ regions silently corrupt adjacency data. No guard on either side. |
| 10 | **Duplicate `build_region_postpass_patch_batch`** | `agent_bridge.py:412-445` | Function defined identically twice. First definition is dead code (Python takes second). |
| 11 | **`CivSnapshot.alive` always True** | `main.py:344` | Hardcoded `alive=True` for all civs including dead ones. Dead civs appear as valid narrative actors. |
| 12 | **Disposition set wrong direction on proxy detection** | `politics.py:830-832` | Sets sponsor's view of target to HOSTILE. Should set target's view of sponsor (target discovered the espionage). |
| 13 | **`_dead_agents_this_turn` never set** | `simulation.py:973` | Attribute never written anywhere. `compute_martyrdom_boosts` always receives None, returns immediately. Martyrdom is dead-wired. |
| 14 | **`prev_turn_water` double-write** | `ecology.py:377` vs Rust `ecology.rs:802` | Python post-pass overwrites Rust's value. Rust disease delta detection may use stale water on next tick. |
| 15 | **`EVENT_TYPE_MAP` hard-indexes without `.get()`** | `agent_bridge.py:1215` | New Rust event type codes not in the map would crash. |
| 16 | **Path traversal guard uses string prefix** | `live.py:260` | `str.startswith()` is bypassable on Windows with case differences. Should use `Path.is_relative_to()`. |
| 17 | **15 bare `except Exception: pass`** | `agent_bridge.py` (15 sites) | Silences real errors. Most critical: line 889 (Gini computation failure retains stale data), lines 1473-1619 (`set_agent_civ` failures cause Python/Rust polity divergence). |

### P2 — Low priority

| # | Bug | Location | Description |
|---|-----|----------|-------------|
| 18 | **Empty civs list crashes** | `simulation.py:130-133, 684` | `rng.sample([], k=1)` raises ValueError. Unlikely but unguarded. |
| 19 | **Dead civs in disaster targeting** | `simulation.py:130-134` | `rng.sample(world.civilizations)` includes dead civs. Effects apply to corpses. |
| 20 | **Treasury tax truncation** | `simulation.py:1487` | `int(tax)` truncates toward zero. Small civs with merchant_wealth < 20 always pay 0 tax. |
| 21 | **`_civ_id` monkey-patched onto Pydantic model** | `religion.py:830` | `detect_schisms` writes `civ._civ_id` as transient attr. Fragile — should pass as parameter. |
| 22 | **Stockpile cap zeroes goods in zero-pop regions** | `economy.py:451` | All stockpiled goods destroyed when population hits 0, even temporarily. |
| 23 | **`normalize_influence` division-by-zero edge** | `factions.py:112-114` | If all factions at zero, `over_total` could be 0 in redistribution. Currently recovers by accident. |

---

## Part 2: Dead Code & Behavioral Gaps

| Item | Location | Notes |
|------|----------|-------|
| **Power struggle trigger unreachable** | `factions.py:205` | `second[1] > 0.40` with 4 factions summing to 1.0 is nearly impossible. Designed for 3 factions, stranded after clergy added as 4th. Entire power struggle subsystem is dead in practice. |
| **Clergy can never win power struggles** | `factions.py:133-150` | `_event_is_win` has no clergy branch. `count_faction_wins` always returns 0 for clergy. |
| **`choose_vassalize_or_absorb` never called** | `politics.py:420-472` | Decision function exists with tests but is never invoked. Wars always absorb. |
| **`LIFE_EVENT_PILGRIMAGE` unused** | `religion.py:66` | Constant defined, never consumed in Python or Rust. |
| **`thread_domains` is a no-op** | `narrative.py:768-777` | Function exists, returns input unchanged. Dead code. |
| **`invalidate_region_map()` never called** | `models.py:735-737` | The centralized `region_map` is largely unused — 15+ call sites build ad-hoc maps instead. |
| **`to_remove` list in `check_twilight_absorption`** | `politics.py:1289-1424` | Built but never consumed. Incomplete refactor. |
| **`FUND_INSTABILITY` target selection** | `politics.py:1518` | Always picks `candidates[0]` — no hostility ranking. "Most hostile neighbor" intent not implemented. |
| **Economic boom window cap** | `agent_bridge.py:727,1826` | Window maxlen=10 but code takes `min(len, 20)`. 20-turn detection is impossible. |
| **`civ_signals_schema()` stale** | `ffi.rs:166-177` | Declares 7 fields, actual batch has 25+. Dead code marked `#[allow(dead_code)]`. |

---

## Part 3: Code Quality

### Systemic patterns

**Silent exception swallowing.** 15 bare `except Exception: pass` blocks in `agent_bridge.py` alone. These hide real failures — Rust panics, column mismatches, polity state divergence. At minimum, add `logger.exception()` to the core tick path sites.

**Monkey-patched transient attributes.** `world._conquered_this_turn`, `region._seceded_this_turn`, `world._economy_result`, `world._agent_snapshot`, `world._named_agents`, `region._stockpile_bootstrap_pending`, plus settlement transients. Some are PrivateAttr, most are bare dot-assignment. Invisible to serialization, IDE tooling, and model introspection.

**Repeated `region_map` construction.** `{r.name: r for r in world.regions}` built 15+ times per turn across economy, politics, ecology, religion, factions. `world.region_map` exists but is rarely used.

**Inline imports.** 25+ deferred imports in `simulation.py`, 12+ in `politics.py`, 7+ in `religion.py`. Most are circular-import avoidance; some are redundant (importing at function level when already imported at module level).

### Per-module concerns

| Module | Lines | Concern |
|--------|-------|---------|
| `politics.py` | 3,165 | Largest Python file. Mixes 5 concerns (mechanics, FFI builders, Arrow conversion, op reconstruction, Rust config). Should split before Phase 8. |
| `ffi.rs` | 4,613 | Largest Rust file. Highest change frequency. Should split into schema/simulator/signals before Phase 8. |
| `apply_automatic_effects` | 240 lines | Mega-function bundles Phases 2-4. Single largest readability obstacle in simulation.py. |
| `check_twilight_absorption` | 154 lines | Two near-identical absorption paths (~80% duplicated logic). Should extract shared helper. |
| `build_agent_context_for_moment` | 17 params | Function signature has grown across milestones. Needs a context builder class. |
| `AgentPool.spawn()` | 12 params, dual branches | 50 Vec fields with manual 3-way sync (struct def, reuse branch, grow branch). No compile-time completeness check. |
| Phase numbering | `simulation.py` | Inline comments, function names, docstring, and CLAUDE.md all use different numbering. |

### Performance notes (non-critical)

| Item | Location | Impact |
|------|----------|--------|
| `partition_by_region` called 8x/tick | `tick.rs` | 3 calls post-demographics could share one result. |
| O(n*c) civ signal lookup per agent | `tick.rs:922, 1010` | Linear scan of `signals.civs` per agent in wealth_tick and satisfaction. Pre-build lookup array. |
| `id_to_slot` map built 3x/tick | `tick.rs:152, 485` + `relationships.rs:285` | Same HashMap constructed three times. Pass once. |
| Full `events_timeline` scan in factions | `factions.py:156, 218, 280` | O(total_events) per civ per turn. Turn-indexed dict would be O(1). |
| `_controller_values` called 3x/region | `agent_bridge.py:357-364` | Each call does linear civ scan. Compute once per region. |

---

## Part 4: Architecture Assessment

### What's working well

**Phase loop + StatAccumulator.** The 5-category routing (keep/guard/guard-action/guard-shock/signal) cleanly separates what applies in all modes from what agents produce emergently. Has survived 25+ milestones without restructuring. Sound design.

**Arrow FFI bridge.** Name-based column access with optional fallbacks makes the protocol forward-compatible. New Python columns don't break old Rust code. Zero-copy where possible via PyCapsule exchange. Clean one-way data flow.

**Deterministic simulation.** ChaCha8Rng with per-region per-turn per-system stream offsets. Collision test in `agent.rs`. Parallel sections use deterministic index-based collection. Zero `unsafe` code in the entire Rust crate.

**SoA agent pool.** Cache-friendly layout at 68 bytes/agent. Free-list arena avoids allocation churn. Morton-ordered spatial sort for L1-friendly iteration. 50K agents fit in L2 cache.

**Validation pipeline.** 7 oracles testing simulation *outcomes* (not just code paths) across 200 seeds. This catches emergent behavioral regressions that unit tests can't.

**Conservation law tracking.** Economy tracks production, transit_loss, consumption, storage_loss, cap_overflow, clamp_floor_loss. Global balance equation verified in tests.

**Curation pipeline.** Purely functional, well-decomposed: scoring -> causal linking -> clustering -> selection -> diversity penalty -> role assignment -> gap summaries. Clean design.

### What needs attention before Phase 8

1. **`politics.py` (3,165 lines) and `ffi.rs` (4,613 lines)** are complexity hotspots. Phase 8 institutions will touch both deeply. Split before adding institutional mechanics.

2. **CivSignals struct (25 fields, growing)** needs a builder/default pattern for tests. Every new field requires updating every Rust test file.

3. **Power struggle subsystem is dead** with 4 factions. Either fix the threshold or redesign the trigger for the current faction count.

4. **Vassalization decision never fires.** The infrastructure exists (tribute, rebellion checks) but wars never produce vassals. Wire it or remove it.

5. **Mode divergences** (bugs 1-3, 8) mean `--agents=off` and `--agents=hybrid` silently produce different behavior for crisis halving, war costs, drought severity, and rival fall. These should either be reconciled or documented as intentional.

---

## Part 5: Test Suite Assessment

### Strengths
- 1.15:1 test-to-source ratio (Python)
- Every module has corresponding tests
- Determinism tests at multiple levels (module, simulation, cross-thread)
- Performance regression tests with concrete timing targets
- Per-milestone regression tests with 200-seed validation
- Zero test failures, zero TODO/FIXME markers

### Gaps
- **No property-based tests** — key candidates: satisfaction in [0,1], penalties never exceed budgets, conservation laws hold
- **No FFI fuzz testing** — malformed Arrow batches could panic Rust
- **No transient signal lifecycle registry** — CLAUDE.md requires 2-turn tests but no automated inventory
- **`signals.rs` has zero tests** — relies entirely on Python bridge tests
- **`conftest.py` fixtures lag behind model evolution** — create Phase 2-era models, missing faith/traditions/stockpiles/ecology
- **E2E test is shallow** — checks file existence, not simulation invariants
- **CivSignals construction in Rust tests is brittle** — 25-field struct literal in every test, no builder

### Recommended test additions
1. `CivSignals::test_default()` builder for Rust tests
2. Rust-side FFI schema validation tests (construct RecordBatch, verify parsing)
3. Simulation invariant test (50-100 turns: no negative stats, alive civs have regions, conservation holds)
4. Update `conftest.py` fixtures with Phase 6+ field defaults

---

## Part 6: Project Direction

### The project is heading in the right direction.

The architecture has scaled well from Phase 2 through Phase 6 (16 milestones merged). The milestone progression follows the stated principle of "each system needs the prior substrate." The split into a/b sub-milestones works well for calibration isolation. The validation pipeline with 7 oracles is a strong quality gate.

### Risks to the roadmap

1. **Calibration cost growing superlinearly.** Each new system's constants interact with all existing systems. Phase 8 will add 60+ constants to calibrate against everything. Without automated sensitivity analysis tools, each tuning pass takes longer than the last.

2. **Phase 8 institutions will stress the two largest modules.** `politics.py` and `action_engine.py` are the two most complex files. Institutions modify action weights, governing costs, satisfaction, and faction power — touching both deeply. Pre-Phase-8 refactoring pass recommended.

3. **2.5x action weight cap needs revision.** Designed for 3 contributors; Phase 7 already has 4 (Mule), Phase 8 adds a 5th (institutions). Already flagged in Phase 8 brainstorm `[REVIEW B-5]`.

4. **Agent count scaling (50K -> 500K-1M) is untested.** Regression tests run at 6K-10K. Formation scan is O(n^2) within regions. May surface algorithmic surprises at 500K.

5. **Viewer debt accumulating.** Phases 3-7 deferred viewer integration. 5,300-line viewer will need substantial updates for settlements, relationships, spatial positions, memory, needs, households. Risk of surfacing data model issues late.

---

## Appendix: Transport Cost Divergence (Python vs Rust)

The Python `compute_economy()` (test oracle) and Rust `tick_economy_core()` (production) use different transport cost formulas:

| Factor | Python (`economy.py:479`) | Rust (`economy.rs:346`) |
|--------|--------------------------|------------------------|
| Terrain | `max(cost_a, cost_b)` | `(cost_a + cost_b) / 2.0` |
| River + coastal | `min(river, coastal)` — only better discount | Both applied multiplicatively — they stack |

Example: plains(1.0) -> mountains(2.0): Python = 0.20, Rust = 0.15 (33% discrepancy).

Only Rust runs in production. The Python version is test/oracle-only. Not a production bug, but parity tests comparing transport costs will produce false positives.
