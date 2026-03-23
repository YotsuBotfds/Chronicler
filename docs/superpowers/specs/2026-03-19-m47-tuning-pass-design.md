# M47: Phase 6 Tuning Pass — Design Spec

> **Status:** Design complete. Ready for implementation planning.
>
> **Date:** 2026-03-19
>
> **Dependencies:** M36-M45 all merged. No blocking prerequisites.
>
> **Phoebe review items incorporated:** M47a/b/c split (sequential → parallel for a/b), Rust FFI consumer audit, severity composition risk, preset validation, dark-age + religion-intensity cascade test.
>
> **Phoebe spec review (round 1):** B-1 (resource abundance yield cap), B-2 (aggression bias insertion point), O-1 through O-8 all resolved. See Review Notes section.
>
> **Review actions integrated:** Simulation bug fixes from `docs/superpowers/reviews/m47-review-actions.md` Sections 1, 2a, 3b, 5a folded into execution sequence. Civ-removal stale-index bug discovered during 4a investigation — added to Tier A.

---

## Overview

M47 calibrates all Phase 6 constants and validates that the interconnected Living Society systems produce coherent, narratively rich outcomes. Five milestones (M42, M43a, M43b, M44, M45) have landed without a batch regression run — the largest validation gap in project history.

**Split into three deliverables plus pre-calibration bug fixes:**

```
Tier A bug fixes (1a, 1c, 1e, civ-removal)
    ↓
--agents=off bit-identical check (single seed, 5 min)
    ↓
M47a (consumer wiring + 1d severity + tatonnement + 1b cleanup)
    ↓
M47b-prep (extractors + 4b region_map + 4c CivThematicContext)
    ↓  dispatch
┌─── M47b-run (200 seeds)                      background
├─── 3b constants extraction                   background worktree
└─── Auto-vectorization + 2a pre-index         background
         ↓
M47c (calibration + narrative)                 3 days time-box
```

M47a and M47b execute in parallel after bug fixes land. Both feed M47c. All multipliers default to 1.0, so the health check runs on current behavior regardless of whether consumer wiring has landed.

**Critical path estimate:** 13-18 hours pre-M47c (Tier A 1-2h → M47a 8-10h → M47b-prep 4-6h → dispatch). Revised from 14-21h after clearing 1a/1c/1e as non-bugs; 25-site severity scope adds ~1-2h.

**Effort discrepancy note:** The review actions doc (`m47-review-actions.md` Section 3a) estimates consumer wiring at "30 min (8 one-liners)." This brainstorm revealed 4-6 hours due to FFI threading (2 CivSignals columns), severity composition cap, tech cost division-by-zero guard, Rust test fixture updates, and 11 severity call site changes. The review doc underestimated by ~10x.

---

## Tier A: Pre-Calibration Bug Fixes

**Goal:** Fix simulation correctness issues that would invalidate calibration baselines. Must land before any metrics are gathered.

**Estimate:** 4-6 hours total.

**Gate:** After Tier A, run `--agents=off` bit-identical check: run seed 42 twice with `--agents=off`, verify identical output between runs (determinism). This verifies Tier A didn't break aggregate mode. ~5 min. If it fails, fix before proceeding. Note: this gate captures the *pre-M47a* baseline. Criterion 0 in M47b captures the *post-M47a* authoritative reference (after 1d severity fix and tatonnement change aggregate-mode behavior).

### 1a. Phase 10 double-applies `keep` mutations in hybrid mode

**File:** `simulation.py` ~lines 1281, 1316-1317
**Problem:** `acc.apply_keep()` runs at line 1281, then `acc` is passed to Phase 10 which may re-apply the same `keep` mutations.
**Fix:** Pass `acc=None` to Phase 10 in hybrid mode (matches documented rule: "Phase 10 receives `acc=None` in aggregate mode").
**Effort:** 30 min investigation + 15 min fix + integration test.

### 1c. Accumulator not threaded to all phase functions

**File:** `simulation.py` — turn loop
**Problem:** Some functions bypass the accumulator in hybrid mode, applying mutations directly. Creates silent divergence between aggregate and agent modes.
**Functions to audit:** `apply_value_drift()`, `apply_asabiya_dynamics()`, `compute_all_stress()`, and any other Phase 1-9 function that mutates civ stats without `acc` parameter.
**Fix:** Add `acc` param to each, route mutations through `acc.add(category, ...)`.
**Effort:** 1-2 hours.

### 1e. Federation/balance functions missing `acc` parameter

**File:** `politics.py`
**Functions:** `check_federation_formation()`, `trigger_federation_defense()`, `apply_balance_of_power()`, `check_twilight_absorption()`
**Fix:** Add `acc: StatAccumulator | None = None` parameter. Route mutations through `acc.add()` when not None.
**Effort:** 1-2 hours.

### Civ-removal stale-index bug (CRITICAL)

**File:** `politics.py:1197`, `agent_bridge.py:1004`
**Problem:** `world.civilizations.remove(civ)` in twilight absorption shifts all indices above the removed position. Rust-side `civ_affinity` values become stale — `_write_back()` either crashes (`IndexError`) or writes stats to the wrong civ (silent data corruption) on the next turn.
**Root cause:** List indices used as stable identifiers, but list mutations invalidate them. Single `remove()` call at `politics.py:1197`.
**Fix (option a — stable indices):**
1. Delete the `world.civilizations.remove(civ)` call. Dead civs stay in the list (already the convention: "check `len(civ.regions) > 0`").
2. Add guard in `_write_back()`: `if len(world.civilizations[civ_id].regions) == 0: continue` — skips dead civs whose agents haven't loyalty-flipped yet.
3. Audit all loops over `world.civilizations` for implicit "all civs are alive" assumptions. Add `if len(civ.regions) > 0` guards where needed.
**Effort:** 1-2 hours.

---

## M47a: Consumer Wiring

**Goal:** Wire all 8 Tier 1 multipliers to their consumer sites. All default to 1.0 (no behavioral change until explicitly set). Presets become functional. Also includes severity inconsistency fix (1d), Pydantic cleanup (1b), and batch tatonnement.

**Estimate:** 6-9 hours. Rust test fixture updates ~50% of consumer wiring time. Tatonnement ~1-2 hours.

### Consumer Site Table

| Multiplier | Consumer Function | File:Line | Mechanism |
|---|---|---|---|
| `K_AGGRESSION_BIAS` | WAR weight (final, pre-cap) | `action_engine.py:797` | `weights[ActionType.WAR] *= get_multiplier(self.world, K_AGGRESSION_BIAS)` inserted after raider incentive (line 796), before streak-breaker (line 798). Applied to the fully-stacked WAR weight so the multiplier has predictable 1:1 effect on the final pre-cap value. 2.5x cap (line 809) still normalizes downstream. |
| `K_TRADE_FRICTION` | `compute_transport_cost()` | `economy.py:419` | `return cost * get_multiplier(world, K_TRADE_FRICTION)`. Higher value = more expensive trade = reduced margins in `allocate_trade_flow()`. |
| `K_RESOURCE_ABUNDANCE` | `compute_resource_yields()` | `ecology.py:118` | `yields[slot] *= get_multiplier(world, K_RESOURCE_ABUNDANCE)` applied to final yield. **No yield cap exists** — `K_PEAK_YIELD` is defined in `tuning.py` but has no consumer. Downstream bounds: `food_sufficiency` clamps to [0.0, 2.0], stockpile caps per region. Unbounded yields at extreme abundance (>3.0) could distort stockpile dynamics — document as known limitation for M47c calibration. |
| `K_SEVERITY_MULTIPLIER` | `get_severity_multiplier()` | `emergence.py:87` | `return min(base * get_multiplier(world, K_SEVERITY_MULTIPLIER), 2.0)`. Composed cap at 2.0x prevents dark-age (1.8) + max stress (1.5) death spirals. Signature changes to `get_severity_multiplier(civ, world)`. |
| `K_SECESSION_LIKELIHOOD` | Secession probability | `politics.py:126` | `prob *= get_multiplier(world, K_SECESSION_LIKELIHOOD)` then `min(prob, 1.0)`. |
| `K_TECH_DIFFUSION_RATE` | `check_tech_advancement()` cost | `tech.py:99,102` | `effective_cost = int(cost / max(get_multiplier(world, K_TECH_DIFFUSION_RATE), 0.1))`. Rate > 1 = cheaper = faster. Floor at 0.1 is defense-in-depth; primary guard is `load_tuning()` validation (see below). **Stacking note:** Composes multiplicatively with scholarship focus (0.8x cost). Golden-age preset (rate=2.0) + scholarship = `int(cost * 0.8 / 2.0)` = 40% of base cost. This is intentional. |
| `K_CULTURAL_DRIFT_SPEED` | Rust `drift_agent()` + Python `apply_value_drift()` | `culture_tick.rs:64`, `culture.py:69` | **FFI required.** New `cultural_drift_multiplier: f32` on `CivSignals`. Rust: `CULTURAL_DRIFT_RATE * multiplier` (per-agent value mutation rate). Python: multiply `net_drift` magnitude in `apply_value_drift()` (inter-civ disposition response). **Note:** These are asymmetric consumers — Rust controls how fast agents change values, Python controls how fast civs change disposition based on similarity. At multiplier >1, both compound: faster agent convergence feeds larger similarity which gets amplified in disposition. Calibration target measures the Rust effect (value variance); disposition amplification shows up in diplomatic outcomes. |
| `K_RELIGION_INTENSITY` | Rust conversion + Python religion | `conversion_tick.rs:64`, `religion.py:27,50,514` | **FFI required.** New `religion_intensity_multiplier: f32` on `CivSignals`. Rust: multiply `CONQUEST_CONVERSION_RATE` and `region.conversion_rate`. Python: multiply `BASE_CONVERSION_RATE`, scale `SCHISM_MINORITY_THRESHOLD` inversely with floor (`max(threshold / multiplier, 0.10)`), scale persecution intensity. Floor prevents degenerate schism cascading at high intensity values. |

### FFI Additions

- 2 new `f32` fields on `CivSignals` struct in `signals.rs`: `cultural_drift_multiplier`, `religion_intensity_multiplier`
- 2 new columns in `build_civ_batch()` in `agent_bridge.py`
- 2 reads in `CivSignals` parsing in `signals.rs` — default to 1.0 for missing columns (multiplicative identity), matching existing optional field pattern
- Consumer sites in `culture_tick.rs` and `conversion_tick.rs`

### Severity Composition Cap

`get_severity_multiplier()` gains a `world` parameter. New implementation:

```python
def get_severity_multiplier(civ: Civilization, world: WorldState) -> float:
    base = 1.0 + (civ.civ_stress / 20) * 0.5
    return min(base * get_multiplier(world, K_SEVERITY_MULTIPLIER), 2.0)
```

11 call sites need the `world` argument added:
- **simulation.py (9):** drought (line 137), plague (156), earthquake (179), leader death (640), rebellion (665), religious movement (681), migration (706), border incident (713), ongoing conditions (800)
- **ecology.py (1):** `_check_famine_yield` (line 283) — `world` already in scope as parameter
- **factions.py (1):** `tick_factions` (line 413) — `world` already in scope as parameter
- **test_emergence.py (4 tests):** lines 292-309, test the old signature — update to pass `world`

### Multiplier Validation in `load_tuning()`

Add validation after flattening: any key matching `multiplier.*` with value <= 0 raises `ValueError`:

```
Multiplier 'multiplier.severity' must be > 0, got 0.0
```

**Note:** This guards the `load_tuning()` YAML path. `apply_preset()` is not guarded — current presets are all hardcoded with positive values. If preset definitions are ever externalized (user-defined presets), add validation there too. For now, defense-in-depth is adequate.

### Test Requirements

- **Unit test per Python consumer:** Multiplier at 2.0 produces expected scaled output (6 tests).
- **Severity cap unit test:** `get_severity_multiplier(civ_at_max_stress, dark_age_world)` returns exactly 2.0, not 2.7. Directly verifies the composition cap.
- **Rust tests:** `CivSignals` fixtures updated with new fields. Culture tick and conversion tick verify multiplier effect at 2.0 vs 1.0.
- **`--agents=off` bit-identical verification:** Runs after consumer wiring (step 1) but *before* 1d severity fix and tatonnement (steps 3-4). Verifies wiring is a no-op at default multipliers. See M47a implementation order below.
- **Preset integration tests (50 turns, 1-2 seeds each, seed-matched against default baseline):**

| Preset | Assertion |
|---|---|
| dark-age | WAR% > baseline, secession count > baseline |
| golden-age | WAR% < baseline, food_sufficiency mean > baseline |
| silk-road | TRADE% > baseline, cultural value variance lower (faster convergence) |
| pangaea | WAR% > baseline (aggression 1.3), TRADE% > baseline (friction 0.5) |
| archipelago | Tech advancement turns > baseline (cost / 0.6 = 67% more expensive) |
| ice-age | Food_sufficiency mean < baseline |

### M47a Implementation Order

Order matters — steps 3-4 intentionally change `--agents=off` output. The bit-identical test validates step 1 in isolation.

1. **Wire 8 multiplier consumers** + FFI additions + severity cap + tech floor + validation
2. **Run `--agents=off` bit-identical test** (verifies consumer wiring is no-op at defaults — single seed, must pass)
3. **Apply 1d** (severity inconsistency fix — intentional behavioral change, adds `get_severity_multiplier()` calls where missing)
4. **Apply tatonnement** (intentional behavioral change — price convergence improves)
5. **Apply 1b** (Pydantic cleanup — no behavioral change)

**Commit boundaries:** Step 1-2 as one commit (consumer wiring, verified no-op). Steps 3, 4, 5 as separate commits. Git history shows which change caused any regression.

After M47a completes, criterion 0 in M47b captures the post-M47a authoritative baseline.

### 1d. Severity multiplier applied inconsistently (folded into M47a, step 3)

**Files:** `simulation.py`, `emergence.py`
**Rule:** Per CLAUDE.md, all negative stat changes go through `get_severity_multiplier()` except treasury and ecology.
**Problem:** Some event types use it; others do not. Audit during the severity signature change (all 11 call sites already being touched).
**Fix:** Grep for negative stat mutations and verify each passes through the multiplier. Add where missing.
**Effort:** Included in consumer wiring — same call sites.

### 1b. Pydantic `validate_assignment=False` cleanup (folded into M47a)

**File:** `models.py`
**Problem:** `Field(ge=0, le=100)` constraints exist but `validate_assignment=False` means they're never enforced. Misleading.
**Fix:** Remove the `ge=`/`le=` kwargs from Field definitions. Add comment explaining validation is off for performance and clamping is manual.
**Effort:** 20 min.

### Batch Walrasian Tatonnement (folded into M47a)

**File:** `economy.py`, inside `compute_economy()` or extracted as `_discover_prices()`
**Rationale:** Changes price convergence behavior, which changes `food_sufficiency`, `merchant_margin`, trade flow volumes, and stockpile accumulation — exactly the metrics M47b measures and M47c calibrates. Landing this after calibration would invalidate the tuned constants. Small scope (80 lines), high impact on calibration quality.
**Implementation:**
```python
for pass_num in range(MAX_PASSES):  # MAX_PASSES = 3
    price[g] *= (1.0 + damping * excess[g] / max(supply[g], 0.01))
    if max(abs(delta_price)) < CONVERGENCE_THRESHOLD:  # 0.01
        break
```
Early-exit on convergence. Deliberately don't over-converge (Victoria 3 insight: price drift creates realistic overshooting).
**Damping constant:** `TATONNEMENT_DAMPING = 0.2` `[CALIBRATE]`. Range 0.1-0.3 for stability. Per-pass clamp: price adjustment factor clamped to [0.5, 2.0] to prevent single-pass oscillation when `excess/supply` is large.
**Effort:** ~80 lines, 1-2 hours with tests.

---

## M47b: Simulation Health Check

**Goal:** First batch run of Phase 6 at full feature depth. Establishes absolute thresholds for non-degenerate behavior. Not a regression — no pre-M42 baseline exists. The last valid baseline is `m19b-post-m24-tuning-report.md` (Phase 3-5, 34 criteria).

**Split into two phases:**
- **M47b-prep:** Implement 9 new analytics extractors + aggregation harness + structural improvements. ~4-6 hours implementation.
- **M47b-run:** Dispatch 200-seed health check as background agent. Pure CPU, no LLM calls.

### Structural Improvements (bundled with M47b-prep)

**4b. Cache `region_map` on WorldState** (~1-2 hours)
- `{r.name: r for r in world.regions}` is recomputed in 6+ functions every turn. 200 seeds × 500 turns × 6 rebuilds = 600,000 unnecessary dict constructions during health check.
- Add `region_map: dict[str, Region]` as a cached property or recomputed-once-per-turn field. Invalidate on region changes (conquest, expansion).

**4c. Delete `CivThematicContext`** (~15 min)
- Defined in `models.py` but never constructed. Dead infrastructure. Remove while touching `models.py` for the Gini `CivSnapshot` field.

### Run Configuration

```
--agents hybrid --simulate-only
--turns 500 --civs 4 --regions 8
--seed-range 1-200
```

No tuning YAML, no preset. Default constants only.

### New Extractors (M47b-prep)

9 new extractors in `analytics.py`, each reading from existing data sources:

| Extractor | Source | Output |
|---|---|---|
| `extract_gini_trajectory()` | **Requires adding Gini to `CivSnapshot`** — `AgentBridge._gini_by_civ` is transient (overwritten each turn, not persisted to bundle). Implementation: add `gini: float` field to `CivSnapshot` in `models.py`, populate from `_gini_by_civ` during snapshot assembly. Extractor then reads from `history` snapshots like all other extractors. | Gini per civ per turn |
| `extract_conversion_rates()` | `events_timeline` — **verify actual event_type strings** during M47b-prep. Conversion events may surface as `"religious_shift"` or similar, not `"conversion"`. Check `religion.py` and `agent_bridge.py` event emission. | Count per faith per run |
| `extract_schism_count()` | `events_timeline` filter `event_type == "schism"` | Count per run |
| `extract_dynasty_count()` | Unique `dynasty_id` values from great persons | Count per run |
| `extract_arc_distribution()` | `arc_type` field on `GreatPerson` | Count per archetype per run |
| `extract_food_sufficiency()` | `EconomyResult.food_sufficiency` signals | Mean/min per civ per turn |
| `extract_trade_volume()` | `EconomyResult` trade flow totals | Volume per turn |
| `extract_stockpile_levels()` | `Region.stockpile` at final turn | Per-region at turn 500 |
| `extract_trade_flow_by_distance()` | `EconomyResult` trade flow per route + hop count | Volume per category per hop distance |

### Health Check Criteria

| # | Criterion | Threshold | Type |
|---|---|---|---|
| 0 | `--agents=off` determinism | Run seed 42 twice with `--agents=off`. Verify bit-identical `history` list of `TurnSnapshot` objects, field-by-field, all 500 turns. Any difference between the two runs = FAIL. This is the *post-M47a* authoritative reference (differs from Tier A gate if 1d/tatonnement changed aggregate behavior). Captured output also serves as Phase 5 proxy baseline for M47c cultural drift calibration. | Invariant |
| 1 | No civ extinct by turn 25 | 0 in >95% of seeds | Structural |
| 2 | Population median @ 500 (surviving civs only) | >= 100 agents per surviving civ (exclude extinct civs from denominator) | Structural |
| 3 | Stability median @ 100 | > 30 | Regression (M19b) |
| 4 | Action distribution | No single action > 60% | Structural |
| 5 | War frequency | 5-40 per 500-turn run | Structural |
| 6 | Famine frequency | 5-50 per 500-turn run. **Note:** M19b showed bimodal distribution (cliff at 0.10-0.13 threshold). If >30% of seeds show <5 famines AND >30% show >40, flag as BIMODAL rather than PASS — the mean may be in range while the distribution is unhealthy. | Borderline |
| 7 | Tech advancement | >= 1 era transition per civ median | Structural |
| 8 | Gini range | 0.2-0.8 at turn 500 | Structural |
| 9 | Schism frequency | >= 1 in >50% of seeds | Phase 6 |
| 10 | Conversion events | >= 1 in >80% of seeds | Phase 6 |
| 11 | Dynasty detection | >= 1 per run in >60% of seeds | Phase 6 |
| 12 | Arc classification | >= 3 distinct archetypes total | Phase 6 |
| 13 | Food sufficiency mean | 0.5-1.5 at turn 500 | Phase 6 |
| 14 | Trade volume | > 0 in >90% of turns after turn 10 | Phase 6 |
| 15 | Stockpile non-zero | > 0 in >80% of regions @ 500 | Phase 6 |

**Report format:** Matches `m19b-post-m24-tuning-report.md` — criterion table with PASS / BORDERLINE / STRUCTURAL per row, plus raw metric distributions for M47c reference.

**`--agents=off` baseline:** The criterion 0 run also serves as the Phase 5 proxy for cultural drift calibration in M47c (compare aggregate cultural convergence timeline vs agent-mode).

---

## M47c: Calibration + Narrative Review

**Goal:** Adjust Phase 6 constants so interconnected systems produce coherent, narratively rich outcomes. Time-boxed to 3 days — M53 (Phase 7) handles the next calibration round.

**Dependency:** M47a (multiplier consumers wired) + M47b (health check results available). Structural failures from M47b must be fixed before calibration begins.

### Calibration Targets

| Constant | Module | Target | Metric |
|---|---|---|---|
| `CULTURAL_DRIFT_RATE` | M36/Rust | Agent-mode convergence within 2x of `--agents=off` proxy | Cultural value variance over time, agent vs aggregate |
| `BASE_CONVERSION_RATE` | M37/Python | Proselytizing faiths 1.5-2x insular spread rate | Conversion events per faith, grouped by doctrine |
| Holy war bonus | M37 | Militant-faith civs +20-40% wars | WAR frequency: militant vs non-militant |
| `TITHE_RATE` | M38 | Clergy treasury 5-15% of merchant wealth | Tithe income / merchant income ratio |
| Schism threshold | M38 | 1-3 per 500-turn run in diverse civs | From M47b criterion 9 |
| Persecution → migration | M38b | `migration(persecuted) >= 3x migration(non-persecuted)` | Migration events in regions with `persecution_intensity > 0` vs without, same turn window |
| Dynasty depth | M39 | 2-5 dynasties per run | From M47b criterion 11 |
| `STARTING_WEALTH` / accumulation | M41 | Gini 0.3-0.7, log-normal shape | From M47b criterion 8 + distribution shape |
| Transport costs | M43a | Food profitable 1-2 hops, luxury 4+ | `extract_trade_flow_by_distance()`: per-category volume by hop count |
| `RAIDER_THRESHOLD` | M43b | `raids_when(stockpile > 2x regional_mean) / total_wars` in 10-20% | WAR actions where raider bonus > 0, denominated by total wars |
| Arc thresholds | M45 | >= 4 archetypes per run, balanced distribution | From M47b criterion 12 + per-archetype counts |

### Calibration Method

1. Start from M47b health check results as baseline.
2. Identify constants where observed values fall outside target range.
3. Adjust Python-side constants first (fast YAML iteration via `--tuning`, no recompile).
4. Adjust Rust-side constants second (recompile per change).
5. 20-seed verification per adjustment.
6. Final 200-seed confirmation once all constants converge.

### Preset Validation Matrix

Each preset gets a 20-seed pass. Assertions are directional, seed-matched against default-multiplier baseline:

| Preset | Key Assertions |
|---|---|
| dark-age | WAR% up, secession count up, population lower, food_sufficiency lower |
| golden-age | WAR% down, food_sufficiency up, tech faster, population higher |
| silk-road | TRADE% up, cultural convergence faster, Gini lower |
| pangaea | WAR% up (aggression 1.3), TRADE% up (friction 0.5) |
| archipelago | Tech advancement slower (cost / 0.6), TRADE% lower |
| ice-age | Food_sufficiency lower, population lower, famine frequency higher |
| **dark-age + religion-intensity 1.5** | Schism frequency up, persecution events up. Explicit severity cascade test. |

### Narrative Quality Review

20 curated + narrated chronicles (`--narrator api --budget 50`). Manual evaluation:

- [ ] Personalities appear in prose ("the cautious Vesh...")
- [ ] Dynasty arcs thread across multiple entries
- [ ] Cultural tensions drive conflict narration
- [ ] Religious schisms produce narrative drama
- [ ] Economic class appears in narrative tone
- [ ] Supply crises create compelling moments
- [ ] Social relationships produce narrative callbacks
- [ ] Material world feels real (specific crops, trade goods, seasonal references)
- [ ] Arc summaries reference character deeds

### Deliverables

- Calibrated constants committed with rationale per change
- 200-seed health check report (updated post-calibration)
- Preset validation results (20-seed per preset)
- Narrative quality notes + prompt adjustments if needed
- Structural issues flagged for Phase 7 backlog

---

## Background Tasks (parallel with M47b-run)

These run after M47a merges, concurrent with the 200-seed health check. None affect simulation output.

### 3b. Constants extraction into tuning.py

**Source:** `m47-review-actions.md` Section 3b
**Scope:** Extract hardcoded magic numbers from `ecology.py`, `politics.py`, `culture.py`, `infrastructure.py`, `emergence.py`, `climate.py`, `action_engine.py` into `tuning.py` keys. Each needs: key definition, `KNOWN_OVERRIDES` addition, call-site replacement with `get_override(world, K_FOO, <current_default>)`.
**Dispatch:** Background agent in worktree. Mechanical work, no design decisions.
**Effort:** 3-4 hours.

### Auto-vectorization + civ signal pre-index (2a)

**Source:** `chronicler-simulation-research.md` Section 5.1, `m47-review-actions.md` Section 2a
**Scope:**
- **Auto-vectorization:** Rewrite hot Rust loops as iterators, separate linear math from branchy decisions, add `#[inline]` on hot functions. Profile with `cargo flamegraph` before and after. Targets: `tick.rs`, `satisfaction.rs`, `behavior.rs`.
- **2a:** Pre-index civ signals lookup in `tick.rs` (replace O(n) `.find()` with array indexed by `civ_id`). 30 min.
**Dispatch:** Background agent. Measure-first — flamegraph captures M47a's FFI additions.
**Effort:** 2-4 hours.

## Deferred

- **4a (region_id/civ_id fields):** Pure performance once civ-removal bug is fixed (indices stable). Defer to Phase 7.
- **2b (`_find_volcano_triples()` O(n^3)):** Performance fix in `emergence.py`. Bundle with auto-vectorization background task if touching `emergence.py`, otherwise defer.
- **`analytics.py` size evaluation:** Maintenance. Tackle opportunistically.
- **`civ_index()` caching:** O(n) at n=6-12 is negligible with stable indices. Defer.

---

## Risk Register

| Risk | Mitigation |
|---|---|
| Civ-removal stale-index crash/corruption in hybrid mode | Tier A fix: stop removing civs from list, add dead-civ guard in `_write_back()` |
| Severity composition cascade (dark-age 1.8 * stress 1.5) | Composed cap at 2.0x in `get_severity_multiplier()` |
| Presets assume geography they don't control (silk-road assumes trade routes) | Per-preset 20-seed validation pass with directional assertions |
| 5 milestones without regression — structural bugs hidden | M47b health check on current defaults before any calibration |
| Calibration loop has no natural termination | 3-day time-box; M53 handles next round |
| Rust FFI test fixture updates cascade | Estimate includes 50% of M47a time for fixture work |
| Multiplier value <= 0 causes division by zero or sign flip | `load_tuning()` validation rejects `multiplier.*` keys <= 0 |
| Cultural drift "within 2x of Phase 5" unmeasurable | Use `--agents=off` aggregate run as Phase 5 proxy |
| Gini not persisted to bundle — extractor can't read transient data | Add `gini: float` to `CivSnapshot` (small data model change in M47b-prep) |
| Cultural drift speed compound effect (Rust agent mutation + Python disposition) | Documented in consumer table. Calibration target measures Rust effect; M47c should also check diplomatic outcomes |
| Schism threshold inverse scaling degenerate at high intensity | Floor at `max(threshold / multiplier, 0.10)` prevents cascading. Values above ~3.0 still aggressive. |
| Resource abundance unbounded (no yield cap exists) | Downstream `food_sufficiency` clamps at 2.0. Document that `K_RESOURCE_ABUNDANCE > 3.0` may distort stockpile dynamics. |

---

## Phoebe Review Notes (Round 1)

**B-1 (K_RESOURCE_ABUNDANCE / K_PEAK_YIELD):** `K_PEAK_YIELD` is defined in `tuning.py` but has no consumer anywhere in the codebase — the spec incorrectly referenced it as an existing guard. Fixed: consumer table now documents that yields scale linearly with no upper bound, and relies on downstream `food_sufficiency` clamping at [0.0, 2.0] as the effective guard.

**B-2 (K_AGGRESSION_BIAS insertion point):** Line 605 was `TRAIT_WEIGHTS` dict declaration, not the compute_weights method. Fixed: insertion point is now `action_engine.py:797` — after raider incentive, before streak-breaker. Applied to fully-stacked WAR weight for predictable 1:1 scaling. The 2.5x cap normalizes if total weight exceeds the ceiling.

**O-1 (Gini extractor):** `AgentBridge._gini_by_civ` is transient. Fixed: add `gini: float` to `CivSnapshot` during M47b-prep. Small data model change.

**O-2 (Tech + scholarship stacking):** Documented in consumer table. Multiplicative composition is intentional.

**O-3 (Cultural drift asymmetric consumers):** Documented in consumer table with explanation of Rust vs Python effects and compounding behavior. Added to M47c calibration considerations.

**O-4 (Schism threshold floor):** Added `max(threshold / multiplier, 0.10)` to consumer table for `K_RELIGION_INTENSITY`.

**O-5 (Famine bimodal):** Added bimodal distribution check to criterion 6 — if >30% of seeds below 5 AND >30% above 40, classify as BIMODAL not PASS.

**O-6 (Population criterion denominator):** Clarified "surviving civs only" — extinct civs excluded from median.

**O-7 (Conversion event_type):** Added note to verify actual event_type strings during M47b-prep implementation.

**O-8 (Bit-identical comparison scope):** Criterion 0 now specifies full `history` list comparison, field-by-field, all 500 turns.

**Round 2 (O-9 through O-11):**

**O-9 (Severity call sites):** Total is 11, not 9. Added `ecology.py:283` and `factions.py:413` plus 4 tests in `test_emergence.py`.

**O-10 (load_tuning validation scope):** `apply_preset()` not guarded. Current presets hardcoded positive — documented as defense-in-depth note for future externalization.

**O-11 (Severity cap direct test):** Added targeted unit test: `get_severity_multiplier(max_stress_civ, dark_age_world) == 2.0`. Directly verifies cap, not just downstream effects.
