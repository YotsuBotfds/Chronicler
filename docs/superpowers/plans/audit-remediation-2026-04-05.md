# Audit Remediation Plan — 2026-04-05 (revised)

## Context

Full-scale audit conducted via 5 parallel review agents (Simulation, Rust, Integration, Test, General), then cross-checked against the existing 2026-04-04 verification audit (`docs/superpowers/audits/4-4-26opusaudit.md`) and the V1-V11 remediation commit (`d818558`). This revision removes false positives, corrects misdiagnoses, and adjusts priorities to match current HEAD.

Status note: this is the planning snapshot for the 2026-04-05 remediation pass. Several items in Tiers 1-2 have since been implemented in the working tree; use `docs/superpowers/progress/phase-6-progress.md` as the source of truth for current completion status.

### What was wrong in the original plan

| Original item | Problem | Resolution |
|---|---|---|
| T1-1 (HashMap determinism — blocking) | Overstated. Knowledge code uses receiver-specific composite RNG streams + canonical buffer sorting. Cross-process determinism test passes. 4-4 audit already downgraded to "discipline gap, not reproduced determinism failure." | Moved to Tier 4 (low). |
| T1-2 injected plague path | Already uses direct mutation on HEAD (`simulation.py:930-933`). Test coverage at `test_acc_hardening.py:213`. | Narrowed to phase_environment path only. |
| T1-4 (tech regression mutations lost) | V1-V11 fix (`d818558`) routed `remove_era_bonus` through accumulator as `keep`. But no third `apply_keep()` after line 1880, so mutations still not flushed. | Revised: routing is correct, missing flush is the remaining bug. |
| T2-4 (test_bundle.py hangs on LM Studio) | Wrong diagnosis. `execute_run()` falls back to `_DummyClient` when no narrative client supplied (`main.py:148`). Tests may be slow but don't hang on LM Studio. | Removed. |
| T3-3 (dead civ stale stats) | Already zeroed on HEAD at `agent_bridge.py:2261-2266`. | Removed. |
| T3-11 (pending builds survive conquest) | Already cleared on HEAD at `action_engine.py:629`. | Removed. |
| T3-18 (kill() non-zeroed fields) | Has regression test at `pool.rs:1596`. Audit overstated risk. | Removed. |
| Verification section | Assumed a known f32 test failure. Full suite was green at 2541 passed, 4 skipped per 4-4 progress log. | Corrected. |

---

## Tier 1: High (fix before next milestone)

### T1-1. Phase_environment plague population loss dropped in hybrid mode
- **Source:** Simulation audit Finding 2
- **File:** `src/chronicler/simulation.py:183-184`
- **Issue:** The phase_environment plague path routes population loss through `acc.add(..., "population", ..., "guard")`. In hybrid mode, `guard` is skipped by `apply_keep()`. Plague is an external catastrophe, not emergent agent behavior. The C-3 famine pattern (always direct mutation) should apply. Note: the injected plague path (`simulation.py:930-933`) already uses direct mutation correctly.
- **Fix:** Replace guard routing at line 183-184 with unconditional `distribute_pop_loss()` + `sync_civ_population()`, matching the C-3 famine pattern in `ecology.py:128-137` and the injected path at line 930-933. Keep stability drain routed through accumulator.
- **Complexity:** Small — ~5 lines.
- **Verify:** `pytest tests/ -k plague` + run hybrid seed confirming plague actually reduces population.

### T1-2. `population` missing from `UNBOUNDED_STATS`
- **Source:** Simulation audit Finding 22
- **File:** `src/chronicler/accumulator.py:42`
- **Issue:** `UNBOUNDED_STATS = {"treasury", "asabiya", "prestige"}` — population is absent. If any population delta goes through `apply()`, it gets clamped to [0, 100]. Civ populations routinely exceed 100. Defensive safety measure.
- **Fix:** `UNBOUNDED_STATS = {"treasury", "asabiya", "prestige", "population"}`
- **Complexity:** One-line change.
- **Verify:** `pytest tests/test_accumulator.py`

### T1-3. Tech regression keep mutations not flushed after second apply_keep
- **Source:** Simulation audit Findings 8 & 9, partially overlaps with V1 (already routed through acc by `d818558`)
- **File:** `src/chronicler/simulation.py:1880` (calls `check_tech_regression` with `acc=acc`), `src/chronicler/tech.py` (`remove_era_bonus` routes through `acc.add(..., "keep")`)
- **Issue:** V1-V11 fix correctly routed `remove_era_bonus` through the accumulator as `keep`. However, `check_tech_regression` runs at line 1880, AFTER the second `apply_keep()` at line 1797. No third flush exists. The `keep` mutations from era bonus removal are added to the accumulator but never applied in hybrid mode.
- **Fix:** Add a targeted `apply_keep()` call after `check_tech_regression` (line 1880), guarded by `if world.agent_mode == "hybrid" and acc is not None`. This is the minimal fix. Alternatively, have `remove_era_bonus` apply directly when called from `check_tech_regression` (rare event, direct mutation is safe).
- **Complexity:** Small — 2-3 lines for the flush, or a conditional in `remove_era_bonus`.
- **Verify:** Test: force tech regression in hybrid mode, confirm civ stats change.

### T1-4. Asabiya collapse doesn't set controller-change signals on released regions
- **Source:** Simulation audit Finding 12
- **File:** `src/chronicler/simulation.py:1186-1188`
- **Issue:** When asabiya collapse strips regions, released regions get `controller = None` but `_controller_changed_this_turn` is never set. Agents in released regions stay aligned to the collapsing civ for one tick.
- **Fix:** Set `region._controller_changed_this_turn = True` on each released region at line 1188.
- **Complexity:** Small — add inside existing loop.
- **Verify:** Test collapse scenario, verify agents in released regions get controller-change signal.

---

## Tier 2: Medium-High (fix soon)

### T2-1. Shadow mode silently drops population growth
- **Source:** Simulation audit Finding 15
- **File:** `src/chronicler/simulation.py:522-524`
- **Issue:** Population growth routes through `guard` when `agent_mode != "off"`. Shadow mode uses `apply_keep()` which skips `guard`. Population growth silently vanishes.
- **Fix:** Change population routing to defer only when agents actually own demographics (`demographics-only` and `hybrid`). Shadow mode should keep aggregate population truth and apply these paths directly in Python.
- **Complexity:** Small — condition change on 3-4 guard checks.
- **Verify:** Run shadow mode 50 turns, verify population growth.

### T2-2. Synchronous LLM calls block async WebSocket event loop
- **Source:** General audit N1/L1
- **File:** `src/chronicler/live.py:550-658`
- **Issue:** `narrate_range` blocks entire event loop during narration. Can cause WebSocket disconnects.
- **Fix:** Wrap in `asyncio.to_thread()`.
- **Complexity:** Small.

### T2-3. WAR 2.5x situational boost always hits cap ceiling — DESIGN REVIEW
- **Source:** Simulation audit Finding 1
- **File:** `src/chronicler/action_engine.py:1103-1104`
- **Issue:** High-military civs with hostile neighbors get WAR pinned at ceiling, overriding all other signal balance.
- **Fix:** Design decision needed — document as absolute ceiling or restructure multiplier chain.
- **Complexity:** Needs tuning review. Not a correctness bug — this is a balance/intent question.

### ~~T2-4. Phase 10 guard-action demand signals dropped~~ DROPPED
- **Source:** Integration audit Finding 4
- **Reason dropped:** `to_demand_signals()` has no `since`/checkpoint parameter — it reprocesses all `_changes` (`accumulator.py:193-203`). Calling it again after Phase 10 would duplicate all Phase 5 demand signals. Additionally, there are no `guard-action` producers in Phase 10; all live `guard-action` call sites are in Phase 5 action resolution (`action_engine.py:171, 618, 706, 721, 735`). The single extraction point at `simulation.py:1716` correctly captures all Phase 5 signals before the agent tick. This item would need a concrete new Phase 10 `guard-action` producer plus a checkpointed demand-extraction API to be actionable.

---

## Tier 3: Medium (fix when touching adjacent code)

### T3-1. `civ_affinity` type mismatch in agent_events.arrow sidecar
- **File:** `src/chronicler/bundle.py:111`
- **Issue:** Written as `pa.uint16()`, Rust schema says `uint8`.
- **Fix:** Change to `pa.uint8()`.

### T3-2. Float `//` diverges from integer semantics in crisis halving
- **File:** `src/chronicler/accumulator.py:113-117`
- **Fix:** Use `int(total // 2)`.

### T3-3. `_secession_score` missing KeyError guard
- **File:** `src/chronicler/politics.py:207`
- **Fix:** Add `rn in region_map` guard.

### T3-4. `persecution_intensity` not clamped
- **File:** `src/chronicler/religion.py:523`
- **Fix:** Clamp `intensity = min(1.0, minority_ratio * religion_mult)`.

### T3-5. Proxy war treasury ignores pending accumulator mutations
- **File:** `src/chronicler/politics.py:798-808`
- **Fix:** Apply same pending-treasury-scan pattern from `simulation.py:344-355`.

### T3-6. Double-COMMERCE stacking produces undocumented 2.25x
- **File:** `src/chronicler/action_engine.py:781-786`
- **Fix:** Document as intentional or gate with `and civ2.active_focus != "commerce"`.

### T3-7. `compute_conversion_deltas` overcounts conversion
- **File:** `src/chronicler/religion.py:396-413`
- **Fix:** Filter to only count regions where `conversion_rate_signal > 0`.

### T3-8. Scorched earth doesn't emit `temple_destroyed` event
- **File:** `src/chronicler/infrastructure.py:192-203`
- **Fix:** Emit event matching `destroy_temple_on_conquest` pattern.

### T3-9. Trade route cache race condition
- **File:** `src/chronicler/resources.py:277-295`
- **Fix:** Separate cache keys or compute both together.

### T3-10. Dynasty extinction on incomplete gp_map
- **File:** `src/chronicler/dynasties.py:107-109`
- **Fix:** Only count members whose `agent_id` exists in `gp_map`.

### T3-11. Reconnect data grows unbounded in live mode
- **File:** `src/chronicler/live.py:693-703`
- **Fix:** Cap to last N turns or paginate.

### T3-12. No prompt length enforcement for LLM calls
- **File:** `src/chronicler/narrative.py:1133-1141`
- **Fix:** Add truncation with priority-based content selection.

### T3-13. Severity multiplier double-applies on asabiya collapse — DESIGN REVIEW
- **File:** `src/chronicler/simulation.py:1192-1198`
- **Fix:** Cap `mil_loss` at pre-multiplier amount, or document as intentional. Not a correctness bug — collapse is inherently catastrophic, and scaling by stress may be the intended behavior.

### T3-14. `urban_safety_pen` consumes penalty budget not in CLAUDE.md — DESIGN REVIEW
- **File:** `chronicler-agents/src/satisfaction.rs:219-231`
- **Fix:** Update CLAUDE.md to list 5-term priority order, or move outside the cap. Not a correctness bug — the penalty math is internally consistent, but the spec doesn't reflect the current implementation.

### T3-15. Schism column zero-vs-absent ambiguity
- **File:** `chronicler-agents/src/ffi/mod.rs:660-661`
- **Fix:** Document the contract on both Python and Rust sides.

### T3-16. `river`/`hills` terrains partially supported
- **Files:** `src/chronicler/resources.py`, `src/chronicler/climate.py`, `src/chronicler/ecology.py`
- **Fix:** Add ecology/climate defaults or remove from resource system.

---

## Tier 4: Low / Notes / Test Infrastructure

### T4-1. HashMap in knowledge propagation (RNG discipline cleanup)
- **File:** `chronicler-agents/src/knowledge.rs:529-564`
- **Issue:** `best_per_receiver` is a `HashMap` iterated at line 564. Current code uses receiver-specific composite RNG streams (line 576-584) and canonical buffer sorting (line 637-645), so iteration order doesn't affect determinism in practice. Cross-process determinism test passes. The 4-4 audit (V10) already landed `set_stream` discipline. Remaining work is consistency cleanup, not a correctness fix.
- **Fix:** Replace with `BTreeMap` for consistency with codebase convention. Low priority.

### T4-2. `compute_shock_penalty` naming
- Rename to `compute_shock_effect` and document sign convention.

### T4-3. `_conquered_this_turn` double-clear dead code
- Remove `hasattr` guard in `action_engine.py:661`.

### T4-4. Stale Gini for dead civs
- Clean up `_gini_by_civ` entries for extinct civs.

### T4-5. Unused `STREAM_OFFSETS`
- Add `// reserved, not consumed` comments.

### T4-6. Test coverage priorities (from test audit)
- **GAP-P1:** Add Phase 9 ecology tick phase-level test
- **GAP-P2:** Add multi-turn hybrid integration test (full chain)
- **GAP-P3:** Complete transient signal 2-turn reset tests
- **GAP-P4:** Add mid-turn extinction tests for phases 6, 8, 10
- **GAP-R1:** Add external integration test for `wealth_tick`
- **GAP-R2:** Add end-to-end satisfaction test with all penalty terms simultaneously
- **HANG-2/3:** Fix test isolation for slow tests in `test_m36_regression.py`

---

## Execution Order

**Batch A — Accumulator & population (T1-1, T1-2, T3-2, T2-1)**
All touch `accumulator.py` or population routing in `simulation.py`.

**Batch B — Turn-loop flush & signals (T1-3, T1-4, T3-13)**
Phase ordering, post-phase mutation timing, controller-change signals.

**Batch C — Religion & factions (T3-4, T3-7, T3-15)**
Persecution clamp, conversion delta, schism contract.

**Batch D — Economy & trade (T3-1, T3-5, T3-6, T3-9)**
Bundle schema, treasury checks, trade stacking, cache.

**Batch E — Live mode & narrative (T2-2, T3-11, T3-12)**
WebSocket and narration pipeline.

**Batch F — Remaining medium (T3-3, T3-8, T3-10, T3-14, T3-16)**
Secession guard, scorched earth events, dynasty, satisfaction docs, terrains.

**Batch G — Low priority & tests (T4-1 through T4-6)**
Cleanup, naming, dead code, test coverage.

---

## Verification

After each batch:
1. `pytest tests/ -x -q` (Python — suite should be fully green)
2. `cargo nextest run` (Rust)
3. For Batch A: write a targeted test that forces a plague `Event` into the `phase_environment` code path in hybrid mode (construct the event directly, don't wait for a natural roll), verify population decreases. The injected path is already correct — the bug is in the natural path at `simulation.py:183`.
4. For Batch B: force tech regression in hybrid mode, verify stats change; collapse scenario with agents
5. After all batches: 200-seed regression comparison
