# Chronicler Full Codebase Audit — 2026-04-02

25-agent coordinated audit across Python simulation (~32k lines, 57 files), Rust agent crate (~26k lines), viewer, and test suites. Goal: verify stability baseline before next milestones.

---

## Executive Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 6 | Bugs that silently produce wrong results or break invariants |
| **HIGH** | 25 | Correctness issues, spec violations, accumulator misrouting |
| **WARNING/MEDIUM** | 38 | Logic gaps, transient signal issues, dead code risks |
| **LOW/NOTE** | 45+ | Quality, documentation, edge cases, minor inconsistencies |
| **Test Gaps** | 18 | Missing coverage for critical invariants |

**Worst findings:** A CRITICAL bug silently disables holy war bonuses (string vs enum comparison). Governing cost is permanently zero due to `int(0.5)==0`. Eight accumulator bypass sites break Phase 10 checkpoint tracking. The Rust culture_tick RNG can alias with other streams at high turn counts.

---

## Tier 1: CRITICAL — Fix Before Any New Milestone

### C1. Holy war disposition uses strings instead of Disposition enum
- **Agent:** #3 (Action Engine) | **File:** `action_engine.py:929`
- `rel.disposition in ("hostile", "suspicious")` never matches because `rel.disposition` is a `Disposition` enum instance. `HOLY_WAR_WEIGHT_BONUS = 1.75` is silently dead — militant faiths never get the combat weight boost.
- **Fix:** Change to `rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS)`.

### C2. Governing cost permanently disabled — `int(0.5) == 0`
- **Agent:** #5 (Politics) | **File:** `politics.py:68`
- `gov_cost_per_dist = int(get_override(world, K_GOVERNING_COST, 0.5))` — the `int()` truncates 0.5 to 0. Stability cost for governing is always zero unless overridden to >= 1.
- **Fix:** Remove the `int()` cast, or change default to `1`.

### C3. Accumulator bypass — 8 sites use direct `world.pending_shocks.append()`
- **Agent:** #15 (Accumulator) | **Files:** `politics.py` (6 sites), `simulation.py` (2 sites)
- All bypass `acc.add()`, breaking Phase 10 checkpoint tracking. `to_shock_signals(since=_phase10_checkpoint)` misses these shocks entirely.
- **Fix:** Route all 8 sites through `acc.add(..., "guard-shock")` and remove `if world.agent_mode == "hybrid"` direct-append pattern.

### C4. `tick_temple_prestige` bypasses accumulator entirely
- **Agent:** #15 (Accumulator) | **File:** `infrastructure.py:284`
- Direct `civ.prestige += ...` mutation, never tracked by accumulator watermark system.
- **Fix:** Add `acc=None` parameter, route through `acc.add(civ_idx, civ, "prestige", amount, "keep")`.

### C5. Analytics uses `civ_data.get("alive", True)` — field doesn't exist
- **Agent:** #19 (Bundle/Analytics) | **File:** `analytics.py` (12+ call sites)
- `Civilization` has no `alive` field (documented gotcha). Every `get("alive", True)` always returns `True`, making dead civs invisible in all analytics: summaries, faction dominance, action entropy, everything.
- **Fix:** Either add computed `alive` to snapshot serialization, or replace with `len(civ_data.get("regions", [])) > 0` at all sites.

### C6. Rust culture_tick RNG stream collision at high turn counts
- **Agent:** #23 (Behavior/Demographics) | **File:** `culture_tick.rs:61`
- Stream = `region_id * 1000 + turn + CULTURE_DRIFT_OFFSET(500)`. At turn 500+, this aliases with decision/demographics streams. `conversion_tick.rs` already uses correct bit-packing — culture_tick doesn't.
- **Fix:** Adopt `conversion_tick.rs`'s bit-packing formula: `region_id << 48 | turn << 16 | offset`.

---

## Tier 2: HIGH — Fix Before M47 Tuning Pass

### Accumulator Routing Errors

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H1 | #3 | `action_engine.py:412` | EMBARGO stability penalty routed as `"signal"` instead of `"guard-action"` |
| H2 | #9 | `factions.py:436` | Power struggle stability drain uses `"signal"` instead of `"guard-shock"` |
| H3 | #5 | `politics.py:319,388,694,706,960` | Political shocks (secession, capital loss, federation exit, congress) use `"signal"` instead of `"guard-shock"` |
| H4 | #10 | `culture.py:246-255` | Assimilation drain uses `"signal"` — semantically should be `"guard-shock"` |

### Severity Multiplier Bypasses

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H5 | #2 | `action_engine.py:660-667` | Stalemate military losses skip M18 severity multiplier |
| H6 | #7 | `emergence.py:433` | Supervolcano population loss — no severity multiplier in accumulator path |
| H7 | #5 | `politics.py:831-835` | Proxy detection stability penalty — no severity multiplier |

### Logic Bugs

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H8 | #2 | `action_engine.py:287-302` | Dead civs (0 regions) can be selected as WAR targets — wastes resources, spurious events |
| H9 | #8 | `religion.py:513` | `persecution_intensity` not reset when region has zero believers — persists indefinitely |
| H10 | #8 | `agent_bridge.py:279-280` | Schism signals (`schism_convert_from/to`) never cleared in `--agents=off` mode — persist across all turns |
| H11 | #13 | No handler | Orphaned active GPs on eliminated civs never retired in aggregate path — inflates global cap count |
| H12 | #17 | `world_gen.py:290-292` | `previous_majority_faith=0` for all civs at world gen — only correct for civ index 0 |
| H13 | #11 | `dynasties.py:39-40` | Same-batch promotion ordering can permanently miss dynasty creation if child is processed before parent |
| H14 | #10 | `culture.py:413-434` | Prestige trade bonus: hybrid mode uses un-decayed prestige, aggregate uses decayed — mode divergence |
| H15 | #18 | `narrative.py:1118-1130` | `civ_idx` never passed to agent context — M41 Gini wealth-inequality narration context always 0.0 |
| H16 | #5 | `politics.py:1339,1414` | Twilight absorption clears `capital_region` before emit loop — `is_capital` always False |

### FFI / Bridge Issues

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H17 | #16 | `agent_bridge.py:2185` | Write-back from Rust UInt32 stability not clamped to [0,100] — out-of-bounds value propagates |
| H18 | #4 | `economy.py:464-488 vs 921-939` | Two divergent transport cost functions — max(terrain) vs average, different costs in hybrid vs Python mode |

### Rust Issues

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H19 | #22 | `satisfaction.rs:136` | Shock effects bypass non-ecological -0.40 cap — undocumented exception to CLAUDE.md invariant |
| H20 | #22 | `satisfaction.rs:220` | `three_term` not explicitly clamped before downstream budget math — safe now but fragile to recalibration |
| H21 | #22 | `tick.rs:857-867` | `region_groups` stale after migration — war survival flag uses pre-migration partition |
| H22 | #21 | `pool.rs:198` | `next_id += 1` wraps silently in release builds — could collide with PARENT_NONE=0 at u32::MAX |

### Spec / Cap Issues

| # | Agent | File:Line | Issue |
|---|-------|-----------|-------|
| H23 | #3,#9 | `action_engine.py:993-998` | 2.5x weight cap applied to post-situational absolute weight, not to the tradition×focus×faction product as spec states |
| H24 | #8,#10 | `satisfaction.rs:221-228` | Urban safety penalty consumes cap budget at undocumented priority slot — CLAUDE.md Decision 10 needs update |
| H25 | #18 | `narrative.py:938-958` | Dead `select_action`/`action_selector` code — if re-wired, violates LLM-never-decides invariant |

---

## Tier 3: WARNING/MEDIUM — Address During M47 or Next Relevant Milestone

### Transient Signal Issues
- `_seceded_this_turn` never cleared in aggregate mode (politics.py:331 / agent_bridge.py:289)
- `_conquered_this_turn` clear placed before Phases 6-9 rather than immediately before bridge tick (simulation.py:1608-1610)
- `prev_turn_water` double-written per turn in ecology (ecology.py:251,382)
- `tech_advanced` counter never reset after Scientist GP spawn (great_persons.py:201-211)
- Shadow mode dynasty events accumulated but never drained (agent_bridge.py — shadow branch)

### Data Model Issues
- 12+ undeclared transient attributes on WorldState via `world._foo` pattern — `_treasury_tax_carry` lost on serialize (models.py)
- `FactionState._ensure_clergy` doesn't renormalize — 4-faction sum = 1.08 until next tick (models.py:102-106)
- `HistoricalFigure` model is completely dead code (models.py:437-443)
- `faith_id` sentinel mismatch: `-1` on Infrastructure/PendingBuild vs `0` on `civ_majority_faith` (infrastructure.py:209-218)
- `validate_assignment=False` relies on Pydantic v2 default, never explicitly set (models.py)

### Logic Issues
- Climate flood ignores terrain-specific water cap (climate.py:145)
- Migration removes full surplus even when destinations at capacity — population destroyed (climate.py:241)
- Movement adoption probability not clamped — can exceed 100% if trade_volume is large (movements.py:100)
- Faction schisms counted as clergy "wins" — semantically backwards (factions.py:165-169)
- Conquered-region pending builds continue under new controller (infrastructure.py:83-133)
- Scorched earth doesn't cancel pending builds (infrastructure.py:136-160)
- GP global cap enforcement only evicts from spawning civ, not globally (great_persons.py:142-150)
- Three RNG sources use `random.Random(world.seed + world.turn)` without domain separation — correlated (politics.py:644,865,1051)
- Causal link matching uses only `(turn, event_type)` — can attach to wrong event on same turn (curator.py:582-587)
- `_SUPPLY_FLOOR` forward reference in economy.py (economy.py:414)
- Zero climate severity silently disables all disasters (climate.py:91)
- Dead civs in federations can trigger exit checks and receive stability penalties (politics.py:672-679)
- Unused `season_id` computed in ecology tick (ecology.py:352)
- SEASON_MOD and resource_class_index() defined but never used (resources.py:240-251, 267-279)

### Relationships / Deprecated Code
- `replace_social_edges` deprecated but still wired as fallback — sentiment-destructive if exercised (ffi/mod.rs:1034)
- `check_marriage_formation` (Python) deprecated but still in call list (relationships.py:319)
- Dead-agent counterpart relationship slots not cleaned on death (relationships.py:57-82)
- `dissolve_edges` doesn't notify Rust side (relationships.py:57-82)

### Rust Quality
- `powf(1.20)` in per-agent hot path — not a bug but slow (behavior.rs:564-566)
- BTreeMap sorts on already-sorted data — defensive no-ops (behavior.rs:373-374)
- `drift_relationships` builds BTreeMap every tick — HashMap would be faster (relationships.rs:296-300)
- `MIGRATION_STREAM_OFFSET=200` registered but never consumed (agent.rs:94)
- `kill()` partial zeroing leaves stale fields on dead slots (pool.rs:342-358)
- Stale `dominant_faction` enum comment omits clergy (signals.rs:33)

### CLI / Live Mode
- `narrate_range` WebSocket handler always uses LM Studio regardless of session narrator (live.py:456)
- `batch_start` handler namespace missing narrator/agents/preset flags (live.py:166-188)
- Path traversal anchor uses relative `Path("output")`, drifts on CWD change (live.py:338,361)
- `run_chronicle()` legacy wrapper namespace incomplete (main.py:819-831)

### Bundle / Analytics
- `bundle_version` hardcoded as `1`, never incremented (bundle.py:67)
- `model_dump_json()` + `json.loads()` double-serializes — use `model_dump(mode="json")` (bundle.py:36)
- Arrow IPC file sink not closed on exception (bundle.py:110, shadow.py:36)
- SHADOW_SCHEMA uses uint32 but aggregate civ fields are floats — silent truncation (shadow.py:13-24)
- `extract_schism_count` matches "Schism" (capital S) but events likely lowercase (analytics.py:1652)
- `format_text_report` reads politics keys with wrong suffixes — always shows 0 (analytics.py:1383)
- Several analytics extractors defined but never called from `generate_report` (analytics.py:1934-2047)

---

## Tier 4: Test Coverage Gaps

### Critical Test Gaps
1. **Transient signal 2-turn integration tests incomplete** — tests mock clearing rather than exercising actual `run_turn` clearing path
2. **No Rust tick.rs orchestration test** — no test verifies all Rust phases fire in sequence with known inputs
3. **`--agents=off` regression test only checks determinism**, not bit-identical comparison to pre-agent baseline

### High Test Gaps
4. Satisfaction -0.40 penalty cap priority clamping order not tested (no test where cultural+religious+persecution = 0.40 verifies class tension is absorbed)
5. `food_sufficiency` being outside the cap not explicitly tested
6. `wealth_tick` per-occupation accumulation rates not directly tested
7. `RegionGoods` transient signal has no 2-turn reset test
8. `signals.rs` parsing has no Rust-side unit test
9. 200-seed regression alpha threshold (0.003) not self-documenting in code

### Medium Test Gaps
10. No conftest fixtures for hybrid/shadow agent modes
11. Phase 5 (Diplomacy) has no isolated test
12. Action fallback paths (TRADE→DEVELOP, EXPLORE→nothing) don't test `action_history` bookkeeping
13. Rust struct literals in 7+ test files violate "use constructor functions" rule
14. Shadow mode write path (`ShadowArrowLogger`) has no test
15. No WebSocket live-mode message contract test
16. Single-civ world edge case untested
17. `test_economy_result_overwrites_each_turn` is tautological (tests Python reference semantics)
18. M36 regression tests silently skip when Rust extension unavailable — CI should fail instead

---

## Cross-Cutting Themes

### Theme 1: Accumulator Discipline
The accumulator routing system is the most broadly violated invariant. Between the 8 direct `world.pending_shocks.append()` sites, the `tick_temple_prestige` bypass, and the 5+ call sites using wrong categories ("signal" vs "guard-shock"), approximately **15 accumulator interactions are incorrect**. This is the single largest category of bugs and the highest priority to fix systematically.

### Theme 2: Severity Multiplier Coverage
Three paths bypass the M18 severity multiplier: stalemate military losses, supervolcano population, and proxy detection stability. The multiplier was supposed to be universal (except treasury/ecology), but these gaps mean some negative events hit harder than intended.

### Theme 3: Transient Signal Lifecycle
Multiple transient signals have incomplete clearing in non-hybrid modes: `_seceded_this_turn`, `schism_convert_from/to`, `_conquered_this_turn` (cleared but placed fragily), `tech_advanced` (never cleared). The CLAUDE.md rule ("clear BEFORE the return") is followed in the bridge but violated in several Python-only paths.

### Theme 4: Dead/Deprecated Code Risk
`select_action`/`action_selector` in narrative.py could violate LLM-never-decides if re-wired. `replace_social_edges` is sentiment-destructive. `check_marriage_formation` duplicates Rust M57a. Several analytics extractors are orphaned. `HistoricalFigure` model is dead. Cleaning these reduces the surface area for accidental re-activation.

### Theme 5: Mode Divergence
Several systems behave differently in aggregate vs hybrid mode beyond the intended guard/keep routing: prestige trade bonus calculation, transport cost functions, population floor, transient signal clearing. These should be documented or unified before M47 tuning, since tuning one mode may not fix the other.

---

## Recommended Fix Priority

**Phase A — Before any new milestone (CRITICAL fixes):**
1. Fix holy war enum comparison (C1) — 1 line
2. Fix governing cost int cast (C2) — 1 line
3. Route all 8 accumulator bypass sites through acc.add (C3) — 8 sites
4. Add acc parameter to tick_temple_prestige (C4) — small refactor
5. Fix analytics alive check (C5) — 12 sites, mechanical
6. Fix culture_tick RNG bit-packing (C6) — adopt conversion_tick pattern

**Phase B — Before M47 tuning pass (HIGH fixes):**
7. Fix all accumulator category misroutes (H1-H4)
8. Add severity multiplier to 3 bypass paths (H5-H7)
9. Block dead-civ WAR targeting (H8)
10. Reset persecution_intensity on zero-believer regions (H9)
11. Clear schism signals in aggregate mode (H10)
12. Retire orphaned GPs on civ elimination (H11)
13. Fix world_gen previous_majority_faith (H12)
14. Two-pass promotion in dynasty detection (H13)
15. Clamp stability in _write_back (H17)
16. Unify transport cost functions (H18)
17. Document shock effects cap exemption (H19)
18. Fix stale region_groups for war survival (H21)
19. Guard next_id overflow (H22)
20. Remove dead LLM decision code (H25)

**Phase C — During M47 or next relevant milestone:**
21. Fix transient signal clearing gaps (5 signals)
22. Declare WorldState transient attrs as PrivateAttr
23. Address remaining logic issues (migration population loss, movement probability clamp, etc.)
24. Clean up deprecated relationship code
25. Fix analytics key mismatches and case sensitivity
26. Add missing test coverage (18 gaps)
