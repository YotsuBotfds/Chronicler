# M47 Tuning Pass — Review Actions

**Source:** `docs/superpowers/reviews/2026-03-19-full-codebase-review.md`
**Purpose:** Actionable instructions for the M47 implementation session. Fix bugs before calibrating, then extract constants, then optimize.

---

## 1. Simulation Bugs to Fix BEFORE Calibration

These must land first. Calibrating on top of buggy mutation routing produces wrong baselines.

### 1a. C-3: Phase 10 double-applies `keep` mutations in hybrid mode

**File:** `src/chronicler/simulation.py` ~lines 1281, 1316-1317
**Problem:** In hybrid mode, `acc.apply_keep()` runs at line 1281, applying all `keep`-category mutations directly. Then `acc` is passed to Phase 10 (line 1316-1317), which may re-apply the same `keep` mutations.
**Investigation:** Trace `run_phase_10()` to confirm whether it calls `acc.apply()` or `acc.apply_keep()` again. If it does, those mutations fire twice.
**Fix options:**
1. Pass `acc=None` to Phase 10 in hybrid mode (matches aggregate mode behavior per CLAUDE.md).
2. Restructure Phase 10 to only route `guard` and `signal` categories, never `keep`.

Option 1 is simpler and consistent with the documented rule: "Phase 10 receives `acc=None` in aggregate mode."
**Effort:** 30 min investigation + 15 min fix + integration test.

### 1b. C-4: Pydantic `validate_assignment=False` — document or fix

**File:** `src/chronicler/models.py` — model config
**Problem:** `Field(ge=0, le=100)` constraints exist on stability, prestige, asabiya, etc., but `validate_assignment=False` means they are never enforced at assignment time. The codebase relies on manual `clamp()` calls instead.
**Decision required:** Either:
1. Remove the misleading `ge=`/`le=` kwargs from Field definitions (they do nothing). Add a comment explaining validation is off for performance.
2. Re-enable `validate_assignment=True` and benchmark the cost.

Option 1 is recommended — re-enabling validation would break direct mutation patterns used throughout.
**Effort:** 20 min to audit all Field constraints and remove or annotate.

### 1c. H-2: Accumulator parameter not threaded to all phase functions

**File:** `src/chronicler/simulation.py` — turn loop
**Problem:** Some functions receive `acc=acc`, others do not. Functions that bypass the accumulator in hybrid mode apply mutations directly, creating silent divergence between aggregate and agent modes.
**Functions to audit and thread `acc` into:**
- `apply_value_drift()` — culture.py
- `apply_asabiya_dynamics()` — simulation.py or politics.py
- `compute_all_stress()` — simulation.py (noted as M-3 in review)
- Any other Phase 1-9 function that mutates civ stats without `acc` parameter

**How to find them:** Search for direct `civ.stability`, `civ.prestige`, `civ.asabiya` assignments inside phase functions that lack an `acc` parameter. Each needs: add `acc` param, route mutation through `acc.add(category, ...)`.
**Effort:** 1-2 hours. Mechanical but requires care — each call site needs the correct accumulator category.

### 1d. H-3: Severity multiplier applied inconsistently

**Files:** `src/chronicler/simulation.py`, `src/chronicler/emergence.py`
**Rule:** Per CLAUDE.md, all negative stat changes go through `get_severity_multiplier()` except treasury and ecology.
**Problem:** Some event types (drought, earthquake) use it; others (pandemic in emergence.py) do not.
**Fix:** Grep for negative stat mutations (stability, prestige, asabiya decrements) and verify each passes through `get_severity_multiplier()`. Add the multiplier where missing.
**Effort:** 1 hour audit + fixes.

### 1e. H-4: Federation/balance functions missing `acc` parameter

**File:** `src/chronicler/politics.py`
**Functions:**
- `check_federation_formation()`
- `trigger_federation_defense()`
- `apply_balance_of_power()`
- `check_twilight_absorption()`

**Problem:** These mutate world state (stability, disposition, etc.) but have no `acc` parameter, so mutations bypass the accumulator in hybrid mode.
**Fix:** Add `acc: StatAccumulator | None = None` parameter to each. Route mutations through `acc.add()` when `acc` is not None, otherwise mutate directly (backward-compatible for aggregate mode).
**Effort:** 1-2 hours. Four functions, each needs parameter addition + routing at mutation sites.

---

## 2. Performance Fixes

### 2a. H-5: O(n) civ signal lookup in Rust tick — pre-index

**File:** `chronicler-agents/src/tick.rs` lines 356-359, 443-448
**Problem:** `signals.civs.iter().find(|c| c.civ_id == civ)` runs per-agent. With 200 agents and 16 civs, this is thousands of linear scans per tick.
**Fix:** Before the agent loop, build a fixed-size array indexed by `civ_id`:
```rust
let civ_lookup: Vec<Option<&CivSignals>> = {
    let mut v = vec![None; max_civ_id + 1];
    for cs in &signals.civs {
        v[cs.civ_id as usize] = Some(cs);
    }
    v
};
```
Then replace `.find()` with `civ_lookup[civ as usize]`.
**Effort:** 30 min.

### 2b. H-6: `_find_volcano_triples()` is O(n^3)

**File:** `src/chronicler/emergence.py` ~lines 131-147
**Problem:** Triple nested loop over all regions. 80 regions = 512,000 iterations.
**Fix:** Build adjacency dict from `world.regions`, then for each region check only its neighbors' neighbors. Reduces to O(n * avg_degree^2) which is typically <1000 iterations.
**Effort:** 45 min.

---

## 3. Constants Extraction into tuning.py

The tuning system (`src/chronicler/tuning.py`) already defines 80+ keys and the `get_override()` / `get_multiplier()` API. The 8 global multiplier keys exist but no simulation code reads them yet.

### 3a. Wire the 8 existing multiplier consumers

Each is a one-liner at the consumption site. The keys already exist in tuning.py:
- `K_AGGRESSION_BIAS` — action_engine.py war weight modifier
- `K_TECH_DIFFUSION_RATE` — simulation.py tech phase
- `K_RESOURCE_ABUNDANCE` — economy.py or resources.py yield calculation
- `K_TRADE_FRICTION` — economy.py trade flow calculation
- `K_SEVERITY_MULTIPLIER` — simulation.py `get_severity_multiplier()` (may already be wired)
- `K_CULTURAL_DRIFT_SPEED` — culture.py drift functions
- `K_RELIGION_INTENSITY` — religion.py conversion/schism rolls
- `K_SECESSION_LIKELIHOOD` — politics.py `check_secession()`

**Pattern:** Replace `HARDCODED_VALUE` with `get_multiplier(world, K_FOO) * HARDCODED_VALUE`.
**Effort:** 30 min total (8 one-liners + imports).

### 3b. Extract hardcoded constants from these files

Each file below has magic numbers that should become tuning keys. Add new `K_` constants to tuning.py, add them to `KNOWN_OVERRIDES`, and replace the hardcoded value with `get_override(world, K_FOO, <current_default>)`.

**`src/chronicler/ecology.py`:**
- `_FLOOR_SOIL`, `_FLOOR_WATER`, `_FLOOR_FOREST` (floor values for ecological stats)
- Famine thresholds
- Overpopulation factor

**`src/chronicler/politics.py`:**
- Secession fraction (1/3)
- Vassalization thresholds (0.3, 0.5, 0.8)
- Tribute rate (0.15)
- Breakaway asabiya (0.7)

**`src/chronicler/culture.py`:**
- Drift rate constants
- Assimilation rate constants

**`src/chronicler/infrastructure.py`:**
- Temple build costs and build times
- Max temples per region

**`src/chronicler/emergence.py`:**
- `_BLACK_SWAN_BASE_PROB` (may already have a key — verify)
- `_EVENT_WEIGHTS` dict

**`src/chronicler/climate.py`:**
- Disaster cooldown duration (hardcoded 10)
- All climate multipliers (currently hardcoded per review finding M-21)

**`src/chronicler/action_engine.py`:**
- 2.5x combined weight cap (M-15)
- War costs: fixed 20/10 treasury amounts (M-12)

**Effort:** 3-4 hours total. Mechanical but voluminous. Each constant needs: key definition, KNOWN_OVERRIDES addition, call-site replacement.

---

## 4. Structural Cleanup

### 4a. H-1: Add Region.region_id and Civilization.civ_id fields

**File:** `src/chronicler/models.py`
**Problem:** Index-based lookups via `civ_index(world, civ.name)` are O(n) string matching in hot paths.
**Fix:** Add `region_id: int` and `civ_id: int` fields, set during world generation (index into their respective lists). Update lookup functions to use IDs.
**Impact:** Eliminates a class of ordering bugs and speeds up accumulator, bridge, and action engine lookups.
**Effort:** 2-3 hours (field addition + world_gen assignment + updating all lookup call sites).

### 4b. M-19: Cache region_map on WorldState

**File:** `src/chronicler/models.py` (WorldState), `src/chronicler/simulation.py`
**Problem:** `{r.name: r for r in world.regions}` is recomputed in 6+ functions every turn.
**Fix:** Add `region_map: dict[str, Region]` as a cached property or recomputed-once-per-turn field on WorldState. Invalidate when regions change (conquest, expansion). Pass through the turn loop.
**Effort:** 1-2 hours.

### 4c. Delete or wire CivThematicContext

**File:** `src/chronicler/models.py`
**Problem:** `CivThematicContext` is defined but never constructed anywhere. Dead infrastructure.
**Decision:** If M45 (Character Arcs) or M47 will use it, wire it now. Otherwise delete it to reduce confusion.
**Effort:** 15 min to delete, or 1-2 hours to wire.

---

## 5. Research Enrichments

These are optional improvements that enhance simulation quality. Include if time permits during M47.

### 5a. Batch Walrasian tatonnement in economy.py

**Current:** Single-pass price discovery per turn.
**Improvement:** Iterate price adjustment 2-3 times per turn for better equilibrium convergence.
**Formula per pass:**
```python
price[g] *= (1.0 + damping * excess[g] / supply[g])
```
Early-exit when max |delta_price| < threshold (e.g., 0.01).
**Where:** `src/chronicler/economy.py`, inside `compute_economy()` or extracted as `_discover_prices()`.
**Effort:** ~80 lines new code, 1-2 hours with testing.

### 5b. Auto-vectorization cleanup in Rust agent tick

**File:** `chronicler-agents/src/tick.rs`, `satisfaction.rs`, `behavior.rs`
**Goal:** Help the compiler auto-vectorize tight loops for 2-4x speedup.
**Actions:**
- Replace indexed loops (`for i in 0..len`) with iterator chains (`.iter().zip()`, `.chunks_exact()`)
- Separate linear math (satisfaction formula) from branchy decisions (behavior selection) into distinct loop passes
- Move branching outside tight loops where possible
- Add `#[inline]` on hot functions called per-agent (`compute_satisfaction`, `select_action`)
- Profile before and after with `cargo flamegraph`

**Effort:** 2-4 hours. Measure-first approach — flamegraph before touching code.

---

## 6. Execution Order

Recommended sequence for the M47 session:

1. **Bug fixes** (Section 1) — 4-6 hours
   - Must land before any calibration work
   - Run `--agents=off` regression test after fixes to verify Phase 4 bit-identical output
2. **200-seed regression baseline** — run in background after bug fixes land
   - This is the pre-calibration baseline (overdue per review: M42+M43a+M43b shipped without it)
3. **Constants extraction** (Section 3) — 3-4 hours
   - Wire multipliers first (30 min), then extract file-by-file
4. **Performance fixes** (Section 2) — 1-2 hours
   - Can interleave with constants work
5. **Structural cleanup** (Section 4) — 3-5 hours
   - region_map caching first (biggest bang for buck)
   - CivThematicContext deletion (quick win)
   - ID fields if time permits
6. **Calibration** — after constants are wired
   - 200-seed runs with multiplier sweeps
   - Compare distributions, tune defaults
7. **Research enrichments** (Section 5) — optional, if session budget allows
   - Walrasian tatonnement first (higher impact on simulation quality)
   - Rust vectorization second (performance, not correctness)

**Total estimated effort:** 12-18 hours across multiple sessions. Prioritize Sections 1-3 in the first session; Sections 4-5 can follow.
