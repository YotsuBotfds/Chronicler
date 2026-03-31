# M-AF1: Runtime Correctness & Safety — Design Spec

**Date:** 2026-03-31
**Status:** Approved
**Baseline commit:** `d9baf0a` (M59b merge on `main`)
**Source:** Cross-referenced audits from Opus 4.6 (22 subagents) and GPT-5 (6 subagents + local verification), 2026-03-31.

---

## Goal

Fix all bugs where the simulation produces wrong results or can hard-crash in supported modes (`--agents=off`, `--agents=demographics-only`, `--agents=shadow`, `--agents=hybrid`). Gate with 200-seed adjudicated comparison against the baseline.

This is not a tuning pass. It is a wiring/correctness pass. Behavioral shifts are expected and documented, not suppressed.

---

## Scope: 15 Fixes + 1 Semantic Verification

### M-AF1a — Runtime Correctness

#### 1. Guard-shock channel semantics verification
- **Problem:** Positive event deltas (discovery, renaissance, religious movement) are routed as `guard-shock`. The audit flagged this as potentially penalizing agents, but existing code in `accumulator.py:126` preserves positive sign and Rust tests in `satisfaction.rs:596` assert that positive shock boosts satisfaction.
- **Expected behavior:** If the end-to-end chain correctly treats positive guard-shock as a boost: document and close with a test. If any path inverts the sign: reroute to `guard-action` or `guard`.
- **Fix direction:** Trace the full path: accumulator positive delta → `to_shock_signals()` → Rust `compute_shock_penalty`. Verify sign preservation. Add a targeted test either way.
- **Regression coverage:** Test that a positive guard-shock delta does not worsen agent satisfaction.
- **Expected macro effect:** Depends on finding. If already correct, none.

#### 2. TRADE pays out without active route
- **Problem:** TRADE eligibility uses relationship quality, not route existence. `resolve_trade()` pays out even when no active trade route connects the two civs.
- **Expected behavior:** TRADE should only resolve between civs connected by an active route.
- **Fix direction:** Add route-existence check in TRADE eligibility or resolution; fall back to DEVELOP if no route.
- **Regression coverage:** Test that TRADE between non-adjacent, non-route-connected civs falls back.
- **Expected macro effect:** Slightly fewer trade events in sparse maps.

#### 3. Resolved-action bookkeeping mismatch
- **Problem:** `phase_action()` records the selected action into `action_history`, `action_counts`, streaks, weariness, trait evolution, and analytics — even when WAR falls back to DEVELOP in `action_engine.py:294`. All downstream consumers see "war" when the civ actually developed.
- **Expected behavior:** All bookkeeping should reflect the action actually resolved.
- **Fix direction:** Return resolved action type from resolution; record that in `action_history`, `action_counts`, and all downstream consumers.
- **Regression coverage:** Test that WAR falling back to DEVELOP records "develop" in history and counts.
- **Expected macro effect:** War weariness, streak logic, and analytics become more accurate.

#### 4. `war_start_turns` never populated
- **Problem:** Only assigned in `trigger_federation_defense()` (dead code). Congress power formula always divides by 1 instead of war duration.
- **Expected behavior:** Congress power weighting should account for how long wars have been running.
- **Fix direction:** Stamp `war_start_turns[key] = world.turn` when wars begin in normal war resolution; clean up entry on war end.
- **Regression coverage:** Test that a war started on turn 10 has a nonzero duration at a turn 20 congress.
- **Expected macro effect:** Congress outcomes may shift for long wars.

#### 5. Federation defense unimplemented
- **Problem:** `trigger_federation_defense()` is defined but never called from production code. Federations provide zero mutual defense despite the M14 spec requiring it.
- **Expected behavior:** Federation members should enter war when an ally is attacked.
- **Fix direction:** Wire `trigger_federation_defense()` into `_resolve_war_action()` when the defender is in a federation.
- **Regression coverage:** Test that attacking a federation member pulls allies into war.
- **Expected macro effect:** More war entanglement; federations become meaningful alliances.

#### 6. Governing cost stability always zero
- **Problem:** `gov_cost_per_dist = int(get_override(world, K_GOVERNING_COST, 0.5))` truncates 0.5 to 0. Stability cost from governing distance is always zero.
- **Expected behavior:** Distant governance should impose nonzero stability pressure when configured.
- **Fix direction:** Preserve fractional configured cost until after distance multiplication; do not truncate the base rate before applying.
- **Regression coverage:** Test that nonzero configured governing cost produces nonzero stability penalty for distant regions.
- **Expected macro effect:** Large empires modestly less stable.

#### 7. Zero-agent civ aggregate writeback gap
- **Problem:** Civs that control regions but have zero live agents are absent from the Rust aggregate batch. `_write_back()` skips them, leaving stale military/economy/culture/stability values from the previous turn.
- **Expected behavior:** Write-back should handle missing civ rows deterministically for civs that still control regions.
- **Fix direction:** Emit a deterministic synthetic zero-row for missing civ IDs that still control regions (positive controlled capacity). Extinct civs with no regions are not affected — they are already handled by the dead-civ path.
- **Regression coverage:** Test that a civ with regions but zero agents gets zeroed stats after write-back, not stale values.
- **Expected macro effect:** Edge-case civs don't carry phantom stats.

#### 8. Promotions FFI lacks authoritative civ identity
- **Problem:** Python reconstructs `civilization` from the region's current controller in `agent_bridge.py:1418`. This is wrong after migration, conquest, or secession — a migrated agent promoted in a foreign region is attributed to the wrong civ.
- **Expected behavior:** Promoted agent's current civilization should come from the agent's own civ affinity, not the region's current controller. `origin_civilization` remains best-effort (current semantics) — fixing origin identity authoritatively is deferred.
- **Fix direction:** Carry authoritative `civ_id` from Rust in the promotions Arrow batch (agent affinity is known in `named_characters.rs`). Python reads it directly instead of inferring from region controller. `origin_civilization` continues to use existing logic.
- **Regression coverage:** Test that a migrated agent promoted in a foreign region gets correct civ identity.
- **Expected macro effect:** Named character attribution more accurate.

#### 9. Severity multiplier gaps
- **Problem:** Plague stability drain (`simulation.py:168`) and ongoing-war bankruptcy stability drain (`simulation.py:325`) bypass `get_severity_multiplier()`. Cross-cutting rule requires all negative stat changes (except treasury, ecology) to go through it.
- **Expected behavior:** Both drains should scale with civ stress.
- **Fix direction:** Apply `* mult` to both. Audit remaining negative stat drains for any other gaps.
- **Regression coverage:** Test that plague stability drain and war bankruptcy drain scale with civ stress.
- **Expected macro effect:** Slightly larger drains on stressed civs.

#### 10. Schism conversion dead-wired
- **Problem:** `schism_convert_from`/`schism_convert_to` are set in Python, passed through FFI, but never consumed in Rust `conversion_tick.rs`. Schisms create new faiths with zero adherents.
- **Expected behavior:** Schisms should convert a fraction of agents from the parent faith to the new faith.
- **Fix direction:** Consume the schism conversion fields in `conversion_tick.rs`; apply a one-turn conversion pulse to agents of the source faith in affected regions.
- **Regression coverage:** Test that a schism event produces nonzero agent conversions from parent to new faith.
- **Expected macro effect:** Religious distributions may shift; schisms become mechanically real.

#### 11. Martyrdom boost never decays
- **Problem:** `decay_martyrdom_boosts()` is implemented in `religion.py:594` but never called from the turn loop.
- **Expected behavior:** Martyrdom boost should decay over time, not persist permanently.
- **Fix direction:** Wire `decay_martyrdom_boosts()` into the turn loop. Ordering constraint: decay existing boost before adding current-turn martyrdom inputs, so a new persecution death does not get immediately decayed on the same turn.
- **Regression coverage:** Test that martyrdom boost decreases over 10 turns without new persecution deaths.
- **Expected macro effect:** Conversion rates stabilize after persecution ends.

#### 12. Martyrdom boost applies to all deaths
- **Problem:** `compute_martyrdom_boosts()` receives all agent deaths (old age, war, disease, famine), not just persecution-related deaths.
- **Expected behavior:** Only deaths in persecuted regions where the dead agent's belief mismatches the regional majority should contribute. This is a proxy filter — death-cause data is not available at this call site, so non-persecution deaths (e.g., famine, old age) in a persecuted region will still count. Requiring a death-cause signal is out of scope for this milestone.
- **Fix direction:** Filter death list to agents whose belief mismatches region majority AND region has active persecution. Ordering: this filter runs after decay (item 11), so only newly qualifying deaths contribute to the current turn's boost.
- **Regression coverage:** Test that deaths in a non-persecuted region do not increase martyrdom boost. Note: deaths of majority-faith agents in a persecuted region should also not count.
- **Expected macro effect:** Martyrdom narrows from universal death effect to a regional persecution proxy. Some false positives remain (non-persecution deaths in persecuted regions).

#### 13. Rewilding structurally impossible
- **Problem:** Regrowth counter requires `forest_cover > 0.7` but Rust clamps plains at 0.40 every tick. Counter can never increment for plains regions.
- **Expected behavior:** Plains regions should be able to rewild under sustained low-population, high-moisture conditions.
- **Fix direction:** Lower the regrowth threshold to a value achievable under plains terrain caps (e.g., `> 0.35`), or use a different regrowth signal that doesn't compete with the clamp.
- **Regression coverage:** Test that a depopulated plains region with high water eventually increments the regrowth counter.
- **Expected macro effect:** Some ecological succession may occur where it couldn't before.

#### 14. `conquest_conversion_active` stale in off-mode
- **Problem:** Flag is cleared only when `compute_conversion_signals` runs with a non-None snapshot. In `--agents=off`, no snapshot exists, so the flag persists indefinitely on conquered regions.
- **Expected behavior:** Transient flags should be cleared each turn regardless of agent mode.
- **Fix direction:** Clear `conquest_conversion_active` unconditionally at turn start (before any phase reads it). The invariant is mode-independent clearing, not call-path-specific cleanup.
- **Regression coverage:** Test that the flag resets after one turn in off-mode.
- **Expected macro effect:** Off-mode parity improved.

#### 15. Vassalization path dead-wired
- **Problem:** `choose_vassalize_or_absorb()` and `resolve_vassalization()` exist but are never called. The live war path in `action_engine.py:300` always absorbs conquered regions.
- **Expected behavior:** Wars should sometimes produce vassals instead of absorption.
- **Fix direction:** Wire the existing vassalize-vs-absorb decision into decisive war resolution. Tuning the decision criteria is out of scope for this milestone.
- **Regression coverage:** Test that a decisive war produces a vassal relation instead of absorption, using a deterministic fixture or seeded RNG that forces the vassalization branch of the existing chooser.
- **Expected macro effect:** Some wars produce vassals; political topology becomes richer.

#### 16. Black-market leakage only checks first region
- **Problem:** Code breaks after checking the first controlled region for smuggling routes (`simulation.py:300`). Multi-region embargoed civs miss valid routes via other regions.
- **Expected behavior:** All controlled regions should be checked; break when a valid route is found.
- **Fix direction:** Iterate all civ regions, break on first valid black market route found.
- **Regression coverage:** Test that a multi-region embargoed civ finds a smuggling route via its second region when its first has none.
- **Expected macro effect:** Embargoed civs slightly more resilient.

### M-AF1b — Runtime Safety

#### 17. `replace_social_edges()` positional unwrap
- **Problem:** Only FFI function using positional `.column(N)` with chained `.unwrap()`. Schema mismatch aborts the Python process.
- **Expected behavior:** FFI boundary should return Python exceptions, never abort.
- **Fix direction:** Replace with `column_by_name()`, convert downcast failures to `PyErr` via `ok_or_else`.
- **Regression coverage:** Test that a malformed batch produces a Python exception, not a process abort.

---

## Verification Gate

1. **Per-fix regression tests** — each work item ships with at least one targeted test proving the fix or documenting the finding.
2. **Full suites green** — Python and Rust suites pass with no new failures. Exact counts recorded at signoff.
3. **200-seed adjudicated comparison** — against baseline commit `d9baf0a`.
   - **Hard gate:** no crashes, no new invariant violations, no pathological outcomes (e.g., all civs dead by turn 50).
   - **Adjudicated:** expected directional shifts are acceptable when they match fixes. Unexpected shifts require investigation.
4. **Behavior shift note** — brief doc explaining observed macro changes vs. expectations from this spec's "expected macro effect" entries.

---

## Out of Scope

- **War frequency tuning (M47d)** — fix wiring first, tune after. The dead-wired bugs contaminate the signal.
- **Embargo expiry** — design decision, not a correctness bug.
- **Performance optimizations** — separate work (Tier 5 from audit).
- **Architecture splits** (ffi.rs, AgentBridge, validate.py, politics boundary) — M-AF3.
- **Tooling/validation fixes** (fail-open validator, hidden test/ tree, viewer lint, --compare) — M-AF2.
- **Leader trait → CLERGY mapping** — design decision, not a bug fix.
- **Dead code cleanup** — M-AF3.
- **Economy oracle barren-region crash** — M-AF2 (oracle/test surface only).
- **Vassalization tuning criteria** — wire the decision in M-AF1; tune thresholds later.
