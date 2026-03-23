# Full-Scale Code Review & Tech Debt Scan

**Date:** 2026-03-19
**Scope:** All 53 Python files (~22k lines), 14 Rust files (~7k lines), 27 TypeScript/React files (~5.3k lines)
**Reviewer:** Claude (Opus 4.6)

---

## Executive Summary

The Chronicler codebase is well-engineered with excellent test coverage (~99%), consistent architecture, and strong separation between simulation, agent, and narration layers. The Rust crate is clean with minimal unsafe code. The viewer is functional with modern React patterns.

That said, this review surfaces **~120 actionable findings** across five severity tiers. The most impactful items are: a few logic bugs in the simulation core (transient signal ordering, accumulator routing), a security issue in live.py, performance hotspots in both Python and Rust, and significant type-safety gaps in the viewer. None are blocking, but several should be addressed before M47 calibration to prevent compounding.

**Finding distribution:**

| Severity | Python Sim | Python Infra | Rust | Viewer | Total |
|----------|-----------|-------------|------|--------|-------|
| Critical | 5 | 1 | 0 | 0 | 6 |
| High | 12 | 4 | 2 | 5 | 23 |
| Medium | 25 | 12 | 5 | 14 | 56 |
| Low | 15 | 10 | 6 | 10 | 41 |

---

## 1. Critical Findings

### C-1: Transient signal cleared AFTER bridge tick, not BEFORE

**File:** `simulation.py` ~line 1257
**Rule violated:** CLAUDE.md transient signal rule
**Impact:** `_conquered_this_turn` is consumed by bridge tick, then cleared. Should be cleared first so bridge sees fresh state. Current behavior means the Rust tick sees stale conquest data from the previous clearing cycle.
**Fix:** Swap ordering — clear → tick → populate for next turn.

### C-2: Invalid accumulator category `"guard-shock"`

**File:** `politics.py` lines 473, 740
**Rule violated:** CLAUDE.md specifies 4 categories: `keep`, `guard`, `guard-action`, `signal`
**Impact:** `"guard-shock"` is not a recognized category. `StatAccumulator.add()` stores it but `to_shock_signals()` filters for `"signal"` and `"guard-shock"` — meaning it works by accident but violates the documented contract.
**Fix:** Change to `"signal"` at both call sites.

### C-3: Phase 10 acc logic potentially double-applies mutations

**File:** `simulation.py` ~lines 1316-1317
**Impact:** In hybrid mode, `acc` is passed to Phase 10. But `acc` already applied `keep` mutations earlier (line 1281). Phase 10 mutations may double-apply.
**Fix:** Either pass `acc=None` to Phase 10 in hybrid mode, or restructure so Phase 10 only routes guards.

### C-4: Pydantic validation disabled globally

**File:** `models.py` — `validate_assignment=False`
**Impact:** `Field(ge=0, le=100)` constraints are never checked at assignment time. Bugs that set stats > 100 or < 0 are silently accepted. The codebase relies on manual `clamp()` calls instead.
**Fix:** Either re-enable validation (performance cost) or remove the misleading Field constraints. Document which approach is chosen.

### C-5: `normalize_shock()` is unused; `to_shock_signals()` reimplements differently

**File:** `accumulator.py` lines 46, 91-105
**Impact:** Two normalization paths exist. `normalize_shock()` uses `-abs(delta)`, while `to_shock_signals()` divides delta by stat value. The standalone function is never called but its existence creates confusion about the normalization contract.
**Fix:** Delete `normalize_shock()`. Document that `to_shock_signals()` is the canonical path.

### C-6: Path traversal vulnerability in live.py WebSocket handler

**File:** `live.py` ~lines 256-268
**Impact:** `batch_load_report()` accepts arbitrary file paths from WebSocket clients. An attacker on the local network can read any file the process can access.
**Fix:** Validate path is within `output/` directory using `resolve()` + prefix check.

---

## 2. High-Priority Findings

### H-1: No `Region.region_id` or `Civilization.civ_id` fields

**File:** `models.py`
**Impact:** Index-based lookups are fragile. `civ_index(world, civ.name)` is O(n) string matching, called repeatedly in hot paths (accumulator, bridge, action engine). Adding ID fields would make lookups O(1) and eliminate a class of ordering bugs.

### H-2: Accumulator parameter not threaded consistently

**File:** `simulation.py` — multiple functions
**Impact:** Some phase functions pass `acc=acc`, others omit it. Functions like `apply_value_drift()` and `apply_asabiya_dynamics()` don't receive acc, so their mutations bypass the accumulator in hybrid mode. This creates silent divergence between aggregate and agent modes.

### H-3: Severity multiplier applied inconsistently

**File:** `simulation.py`, `emergence.py`
**Impact:** Some event types (drought, earthquake) apply `get_severity_multiplier()`; others (pandemic in emergence.py) don't. Per CLAUDE.md, all negative stat changes should go through the severity multiplier except treasury and ecology.

### H-4: Federation/balance functions missing `acc` parameter

**File:** `politics.py` — `check_federation_formation()`, `trigger_federation_defense()`, `apply_balance_of_power()`, `check_twilight_absorption()`
**Impact:** These functions mutate world state but can't route through the accumulator. Incomplete hybrid mode support.

### H-5: O(n) civ signal lookups in Rust hot path

**File:** `tick.rs` lines 356-359, 443-448
**Impact:** `signals.civs.iter().find(|c| c.civ_id == civ)` runs per-agent per-tick. With 200+ agents × 16 civs, this is millions of linear searches per game. Pre-indexing into a fixed array would be trivial.

### H-6: `_find_volcano_triples()` is O(n³)

**File:** `emergence.py` ~lines 131-147
**Impact:** Nested triple loop over all regions. With 80+ regions = 512,000 iterations per check. Should use adjacency graph traversal instead.

### H-7: `culture._culture_investment_active` flag — missing cleanup

**File:** `culture.py`
**Impact:** Flag is set to True but no corresponding clear is found in the codebase. Potential sticky state bug. Per CLAUDE.md, this exact pattern was fixed before in M36 — verify this isn't a regression.

### H-8: Bare `except Exception: pass` swallows agent errors

**File:** `simulation.py` ~lines 1302-1305, 1333-1336
**Also:** `agent_bridge.py` (4 instances at FFI boundary)
**Impact:** Failed agent snapshots are invisible. No logging means debugging agent-mode failures requires adding print statements.

### H-9: `gp.deeds` defined but never populated

**File:** `models.py` line 334, `narrative.py` line 173
**Impact:** Known issue (documented in progress.md for M45), but `narrative.py` reads `gp.deeds[-3:]` which returns `[]` silently. No error, but narration quality suffers.

### H-10: Viewer build error — unused imports in BatchAnalytics.tsx

**File:** `viewer/src/components/BatchAnalytics.tsx` lines 4-5
**Impact:** `BarChart` and `Bar` imported but unused. TypeScript strict mode flags this as a compilation error.

### H-11: Global counter in InterventionPanel creates non-unique keys

**File:** `viewer/src/components/InterventionPanel.tsx` line 11
**Impact:** Module-level `let nextId = 0` persists across mounts/unmounts. React key collisions possible.

### H-12: Arrow schema u8→u16 upcast wastes memory

**File:** `pool.rs` lines 374, 409
**Impact:** `civ_affinities` and `displacement_turns` stored as u16 but values are always 0-255. Wastes 8 bytes per agent in serialization.

---

## 3. Medium-Priority Findings

### Python Simulation

| ID | File | Issue |
|----|------|-------|
| M-1 | simulation.py | Mercenary system: unhired mercs persist forever (no spawn decay) |
| M-2 | simulation.py | Condition penalty sums raw severity (50-100 range) — inconsistent scaling |
| M-3 | simulation.py | `compute_all_stress()` mutates directly, no acc routing |
| M-4 | simulation.py | Arc classification may run on dying characters before `retired_persons` update |
| M-5 | models.py | `Resource` enum appears unused (only `ResourceType` used in simulation) |
| M-6 | models.py | `EMPTY_SLOT = 255` as sentinel — no guard against collision with real ResourceType |
| M-7 | models.py | `FactionState.influence` not normalized to sum=1.0 |
| M-8 | models.py | Belief registry hard-capped at 16 faiths with no error message |
| M-9 | models.py | `ActiveCondition.condition_type` is raw string, not enum |
| M-10 | accumulator.py | `STAT_TO_OCCUPATION` missing "population" → farmer mapping |
| M-11 | accumulator.py | `apply()` and `apply_keep()` have near-duplicate code |
| M-12 | action_engine.py | War costs are fixed amounts (20/10 treasury) regardless of military scale |
| M-13 | action_engine.py | Hostage capture logic: defender captures from attacker on win — seems inverted |
| M-14 | action_engine.py | Holy war uses string literals instead of Disposition enum |
| M-15 | action_engine.py | 2.5x weight cap hardcoded, not in tuning constants |
| M-16 | economy.py | `compute_economy()` is 316-line monolith |
| M-17 | politics.py | `check_secession()` is 196 lines — extract 4 sub-functions |
| M-18 | politics.py | `check_congress()` is 114 lines — extract 4 sub-functions |
| M-19 | politics.py | `region_map` recomputed in 6+ functions — should be passed or cached |

### Python Infrastructure

| ID | File | Issue |
|----|------|-------|
| M-20 | great_persons.py | Snapshot accessor can IndexError if `idx >= len(_snap_belief)` |
| M-21 | climate.py | All climate multipliers hardcoded, not in tuning system |
| M-22 | infrastructure.py | `handle_build()` 79 lines with deep nesting — extract sub-functions |
| M-23 | relationships.py | O(n) civ lookups via `next(c for c in world.civilizations...)` — use dict |
| M-24 | dynasties.py | Linear search for dynasty by ID — cache in dict |
| M-25 | live.py | WebSocket race condition between lock release and try block |
| M-26 | live.py | Batch cancel event not propagated to simulation worker thread |
| M-27 | resources.py | `DISP_ORDER` dict duplicates Disposition enum ordering |
| M-28 | world_gen.py | Silent `except (json.JSONDecodeError, KeyError): pass` in LLM enrichment |

### Rust

| ID | File | Issue |
|----|------|-------|
| M-29 | ffi.rs | No validation that optional resource columns exist in expected combinations |
| M-30 | ffi.rs | `set_region_state` is 560+ lines — should split into extract + spawn |
| M-31 | agent.rs | `GOODS_ALLOC_STREAM_OFFSET` declared but never used |
| M-32 | tick.rs | `tick_agents` is 329-line monolith |
| M-33 | ffi.rs | Macro column extraction assumes non-nullable without checking |

### Viewer

| ID | File | Issue |
|----|------|-------|
| M-34 | types.ts | 7 fields use `Record<string, unknown>` — defeats TypeScript safety |
| M-35 | useLiveConnection.ts | Stale closure pattern with manual ref wrapper |
| M-36 | useLiveConnection.ts | No retry limit — reconnects forever at 10s intervals |
| M-37 | useLiveConnection.ts | No `default` case in message type switch |
| M-38 | TerritoryMap.tsx | No `role="img"` or `aria-label` on SVG |
| M-39 | TerritoryMap.tsx | Tooltip can render off-screen |
| M-40 | StatGraphs.tsx | Missing `React.memo` — re-renders on every parent update |
| M-41 | App.tsx | No error boundary wrapping the application |
| M-42 | SetupLobby.tsx | 439-line component — extract sub-forms |
| M-43 | BatchCompare.tsx | Silent `catch { }` on JSON parse of user-dropped files |
| M-44 | useBundle.ts | `as unknown as Bundle` bypasses type checking |

---

## 4. Low-Priority Findings

### Constants & Calibration

Multiple files have hardcoded numbers that should be marked `[CALIBRATE]` or moved to tuning.py for M47:

- `ecology.py`: `_FLOOR_SOIL`, `_FLOOR_WATER`, `_FLOOR_FOREST`, famine thresholds, overpopulation factor
- `politics.py`: secession fraction (1/3), vassalization thresholds (0.3, 0.5, 0.8), tribute rate (0.15), breakaway asabiya (0.7)
- `emergence.py`: `_BLACK_SWAN_BASE_PROB`, `_EVENT_WEIGHTS`
- `factions.py`: `FACTION_FLOOR`
- `culture.py`: multiple drift and assimilation constants
- `infrastructure.py`: temple build costs/times, max temples
- `climate.py`: disaster cooldown durations (hardcoded 10)

### Code Quality

- `politics.py` line 6: `TYPE_CHECKING` imported but conditional block is empty
- `economy.py`: `EconomyTracker.update_stockpile()` and `.update_imports()` are near-identical — extract shared EMA logic
- `Disposition` comparisons sometimes use strings, sometimes enum — standardize
- Several `Event` creation sites vary parameter ordering
- `arcs.py`: claims "pure function" but mutates `matches` list via side effects
- `resources.py`: `SEASON_MOD` arrays use hardcoded indices tied to ResourceType enum — fragile
- Viewer: hard-coded colors instead of Tailwind/CSS variables
- Viewer: no localStorage persistence for dark mode / tab preferences
- Viewer: limited test coverage for chart components

### Documentation

- `accumulator.py`: `"guard-shock"` category not documented in file or CLAUDE.md
- `STAT_TO_SHOCK_FIELD` partial mapping (only 4 of 8 stats) — no comment explaining why
- `behavior.rs` line 46-48: `personality_modifier` clamping unexplained
- `satisfaction.rs`: priority-clamping formula lacks algorithmic comment

---

## 5. Structural Debt Summary

### Missing regression baselines

Three milestones (M42 + M43a + M43b) have shipped without the 200-seed regression comparison required by CLAUDE.md. This is the **top structural risk** — calibration constants can't be tuned without baselines. Blocked on calibration values, but should be prioritized before M47.

### `CivThematicContext` is dead infrastructure

Defined in models.py, referenced in M43b progress notes. Field `trade_dependency_summary` exists but `CivThematicContext` is never constructed anywhere. Either wire it or delete it.

### `region_map` / `civ_map` recomputation

At least 15 functions independently compute `{r.name: r for r in world.regions}`. This should be a cached property on WorldState or passed as a parameter through the turn loop.

### Tuning system incomplete

`tuning.py` defines 8 multiplier keys and CLI flags, but no simulation code reads them yet (documented as M47 scope). The wiring sites are one-liners, but the keys exist in an unusable state.

---

## 6. Recommended Action Plan

### Before M45 implementation

1. **Fix C-1** (transient signal ordering) — 15 min, prevents subtle agent-mode bugs
2. **Fix C-2** (invalid accumulator category) — 5 min, two-line change
3. **Fix C-6** (path traversal in live.py) — 10 min, security fix
4. **Fix H-10** (viewer build error) — 2 min, remove unused imports

### During M47 tuning pass

5. Extract all `[CALIBRATE]`-worthy constants from ecology, politics, culture, infrastructure, emergence into tuning.py
6. Wire multiplier consumers (8 one-liners per CLAUDE.md)
7. Run 200-seed regression baseline before and after calibration
8. Add `region_map` caching on WorldState

### Backlog (opportunistic)

9. Add `Region.region_id` and `Civilization.civ_id` for O(1) lookups (H-1)
10. Thread `acc` parameter through federation/balance functions (H-4)
11. Pre-index civ signals in Rust tick loop (H-5)
12. Refactor 200+ line functions (M-16 through M-19, M-30, M-32)
13. Delete or wire `CivThematicContext`
14. Add error boundary and discriminated union types in viewer
15. Delete unused `normalize_shock()` and `Resource` enum

---

*End of review.*
