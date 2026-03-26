# M56b: Urban Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire M56a settlement footprints into per-agent urban/rural classification with behavioral effects in needs, satisfaction, culture, and conversion; plus narrator context enrichment and analytics.

**Architecture:** Python builds a flat Arrow settlement-footprint batch and sends it to Rust each tick. Rust constructs per-region 10×10 grids and performs dual-pass assignment (pre-needs + post-migration). Four Rust subsystems read `settlement_id` to apply urban modifiers. Python aggregates urban metrics for snapshots, narration, and analytics.

**Tech Stack:** Rust (chronicler-agents crate, PyO3/Arrow FFI), Python (Pydantic models, pyarrow), pytest, cargo nextest.

**Spec:** `docs/superpowers/specs/2026-03-26-m56b-urban-effects-design.md`

---

## File Structure

### Rust (chronicler-agents/src/)
| File | Changes |
|------|---------|
| `agent.rs` | 9 new urban constants + `SETTLEMENT_GRID_SIZE` |
| `pool.rs` | `settlement_ids: Vec<u16>` SoA field in struct, `new()`, `spawn()`, `to_record_batch()` |
| `ffi.rs` | `settlement_grids` on `AgentSimulator`, `set_settlement_footprints()` method, `snapshot_schema()` field |
| `tick.rs` | `assign_settlement_ids()` function, dual-pass calls in `tick_agents()` |
| `needs.rs` | Urban multipliers in `restore_needs()` |
| `satisfaction.rs` | `is_urban` on `SatisfactionInputs`, material bonus + safety penalty in priority clamp |
| `culture_tick.rs` | Urban drift multiplier |
| `conversion_tick.rs` | Urban conversion multiplier |

### Python (src/chronicler/)
| File | Changes |
|------|---------|
| `agent_bridge.py` | `build_settlement_batch()`, wire into `sync_regions()`/`tick()`, snapshot urban aggregation |
| `models.py` | `CivSnapshot.urban_agents/urban_fraction`, `TurnSnapshot.urban_agent_count/urban_fraction`, `AgentContext.urban_fraction_delta_20t/top_settlements` |
| `main.py` | Urban fraction in CivSnapshot build, TurnSnapshot urban fields |
| `narrative.py` | AgentContext urbanization enrichment |
| `analytics.py` | Extend `extract_settlement_diagnostics()` |

### Tests
| File | Scope |
|------|-------|
| `chronicler-agents/tests/test_urban.rs` | Grid construction, assignment, tie-break, directional needs/satisfaction/culture/conversion, dual-pass, cap |
| `tests/test_agent_bridge.py` | Settlement batch construction, overflow guard |
| `tests/test_main.py` or `tests/test_simulation.py` | Urban snapshot aggregation |
| `tests/test_analytics.py` | Extended settlement diagnostics |

---

## Task 1: Rust Constants and AgentPool Field

**Files:**
- Modify: `chronicler-agents/src/agent.rs`
- Modify: `chronicler-agents/src/pool.rs:17-142` (struct + `new()`)
- Modify: `chronicler-agents/src/pool.rs:147-268` (`spawn()`)
- Modify: `chronicler-agents/src/pool.rs:476-540` (`to_record_batch()`)
- Modify: `chronicler-agents/src/ffi.rs:64-88` (`snapshot_schema()`)

- [ ] **Step 1: Add urban constants to `agent.rs`**

Add at end of constants block in `agent.rs`:

```rust
// M56b: Urban effects constants [CALIBRATE M61b]
pub const SETTLEMENT_GRID_SIZE: usize = 10; // mirrors settlements.py:GRID_SIZE
pub const URBAN_SAFETY_RESTORATION_MULT: f32 = 0.90;
pub const URBAN_SOCIAL_RESTORATION_MULT: f32 = 1.08;
pub const URBAN_FOOD_SUFFICIENCY_MULT: f32 = 0.92;
pub const URBAN_WEALTH_RESTORATION_MULT: f32 = 1.10;
pub const URBAN_MATERIAL_SATISFACTION_BONUS: f32 = 0.02;
pub const URBAN_SAFETY_SATISFACTION_PENALTY: f32 = 0.04;
pub const URBAN_CULTURE_DRIFT_MULT: f32 = 1.15;
pub const URBAN_CONVERSION_MULT: f32 = 1.06;
```

- [ ] **Step 2: Add `settlement_ids` field to `AgentPool` struct**

In `pool.rs`, add after the `y: Vec<f32>` field (line ~79):

```rust
    // M56b: Per-agent settlement assignment (0 = rural, >0 = settlement_id)
    pub settlement_ids: Vec<u16>,
```

- [ ] **Step 3: Initialize `settlement_ids` in `AgentPool::new()`**

In the `new()` method (pool.rs:93), add before `alive`:

```rust
            settlement_ids: Vec::with_capacity(capacity),
```

- [ ] **Step 4: Set `settlement_ids` in `spawn()` — both reuse and grow paths**

In the reuse branch (after `self.y[slot] = 0.5;`, pool.rs ~212):

```rust
            self.settlement_ids[slot] = 0;
```

In the grow branch (after `self.y.push(0.5);`, pool.rs ~264):

```rust
            self.settlement_ids.push(0);
```

- [ ] **Step 5: Add `settlement_id` to `snapshot_schema()`**

In `ffi.rs`, add after the `y` field in `snapshot_schema()` (after line ~86):

```rust
        Field::new("settlement_id", DataType::UInt16, false),
```

- [ ] **Step 6: Add `settlement_id` builder in `to_record_batch()`**

In `pool.rs` `to_record_batch()`, add a new builder alongside the existing ones:

```rust
        let mut settlement_id_col = UInt16Builder::with_capacity(live);
```

In the alive-agent loop, add:

```rust
            settlement_id_col.append_value(self.settlement_ids[slot]);
```

In the final `RecordBatch::try_new(snapshot_schema().into(), vec![...])`, add the new column:

```rust
                Arc::new(settlement_id_col.finish()),
```

Position it after `y_col` to match the schema field order.

- [ ] **Step 7: Run `cargo nextest run` to verify compilation and existing tests pass**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All existing tests pass. No regressions.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m56b): urban constants, settlement_ids pool field, snapshot schema"
```

---

## Task 2: Rust Grid Construction and Assignment Function

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:1644-1681` (`AgentSimulator` struct)
- Modify: `chronicler-agents/src/ffi.rs` (add `set_settlement_footprints()` method)
- Modify: `chronicler-agents/src/tick.rs` (add `assign_settlement_ids()`)
- Create: `chronicler-agents/tests/test_urban.rs`

- [ ] **Step 1: Write the grid construction + assignment test**

Create `chronicler-agents/tests/test_urban.rs`:

```rust
//! M56b: Urban effects tests

/// Build a settlement grid from flat footprint data.
/// Returns Vec<[u16; 100]> indexed by region_id.
fn build_settlement_grids(
    num_regions: usize,
    region_ids: &[u16],
    settlement_ids: &[u16],
    cell_xs: &[u8],
    cell_ys: &[u8],
) -> Vec<[u16; 100]> {
    // Inline the function under test so it's self-contained
    crate::tick::build_settlement_grids(num_regions, region_ids, settlement_ids, cell_xs, cell_ys)
}

#[test]
fn test_grid_construction_basic() {
    // One settlement (id=1) in region 0 with 2 footprint cells
    let grids = crate::tick::build_settlement_grids(
        2,
        &[0, 0],
        &[1, 1],
        &[3, 4],
        &[7, 7],
    );
    assert_eq!(grids.len(), 2);
    assert_eq!(grids[0][7 * 10 + 3], 1); // cell (3,7) → settlement 1
    assert_eq!(grids[0][7 * 10 + 4], 1); // cell (4,7) → settlement 1
    assert_eq!(grids[0][0], 0);           // empty cell → 0
    assert_eq!(grids[1][0], 0);           // region 1 is empty
}

#[test]
fn test_grid_tiebreak_lowest_id_wins() {
    // Two settlements claim the same cell (3,7) in region 0
    // Settlement 5 and settlement 2 — sorted by settlement_id ascending,
    // so 2 is processed first and wins.
    let grids = crate::tick::build_settlement_grids(
        1,
        &[0, 0],
        &[2, 5],
        &[3, 3],
        &[7, 7],
    );
    assert_eq!(grids[0][7 * 10 + 3], 2); // lowest id wins
}

#[test]
fn test_assignment_basic() {
    use chronicler_agents::pool::AgentPool;
    let mut pool = AgentPool::new(4);
    // Spawn 2 agents in region 0
    let s0 = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let s1 = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    // Place agent 0 inside settlement footprint, agent 1 outside
    pool.x[s0] = 0.35;
    pool.y[s0] = 0.72;
    pool.x[s1] = 0.95;
    pool.y[s1] = 0.95;

    // Build grid: settlement 1 in region 0, cell (3,7)
    let grids = crate::tick::build_settlement_grids(
        1,
        &[0],
        &[1],
        &[3],
        &[7],
    );
    crate::tick::assign_settlement_ids(&mut pool, &grids);

    assert_eq!(pool.settlement_ids[s0], 1); // inside footprint
    assert_eq!(pool.settlement_ids[s1], 0); // outside → rural
}
```

- [ ] **Step 2: Add `build_settlement_grids()` and `assign_settlement_ids()` to `tick.rs`**

Add at the end of `tick.rs` (before the `wealth_tick` function):

```rust
// ---------------------------------------------------------------------------
// M56b: Settlement grid construction and per-agent assignment
// ---------------------------------------------------------------------------

/// Build per-region settlement lookup grids from flat footprint data.
/// Input arrays must be pre-sorted by (region_id, settlement_id, cell_y, cell_x).
/// Tie-break: lowest settlement_id wins (first write persists).
pub fn build_settlement_grids(
    num_regions: usize,
    region_ids: &[u16],
    settlement_ids: &[u16],
    cell_xs: &[u8],
    cell_ys: &[u8],
) -> Vec<[u16; 100]> {
    let mut grids = vec![[0u16; 100]; num_regions];
    for i in 0..region_ids.len() {
        let rid = region_ids[i] as usize;
        if rid >= num_regions {
            continue;
        }
        let cx = cell_xs[i].min(9) as usize;
        let cy = cell_ys[i].min(9) as usize;
        let idx = cy * 10 + cx;
        // First write wins (lowest settlement_id due to pre-sorted input)
        if grids[rid][idx] == 0 {
            grids[rid][idx] = settlement_ids[i];
        }
    }
    grids
}

/// Assign settlement_id to each alive agent based on position and settlement grids.
pub fn assign_settlement_ids(
    pool: &mut AgentPool,
    settlement_grids: &[[u16; 100]],
) {
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) {
            continue;
        }
        let region = pool.regions[slot] as usize;
        if region >= settlement_grids.len() {
            pool.settlement_ids[slot] = 0;
            continue;
        }
        let cx = (pool.x[slot] * 10.0).min(9.0) as usize;
        let cy = (pool.y[slot] * 10.0).min(9.0) as usize;
        pool.settlement_ids[slot] = settlement_grids[region][cy * 10 + cx];
    }
}
```

- [ ] **Step 3: Add `settlement_grids` field to `AgentSimulator`**

In `ffi.rs`, add after `politics_config` field (line ~1680):

```rust
    // M56b: Per-region settlement lookup grids
    settlement_grids: Vec<[u16; 100]>,
```

Initialize in `AgentSimulator::new()` (in the `Self { ... }` block):

```rust
            settlement_grids: Vec::new(),
```

- [ ] **Step 4: Add `set_settlement_footprints()` PyO3 method**

In `ffi.rs`, add a new `#[pymethods]` method on `AgentSimulator`:

```rust
    /// M56b: Ingest settlement footprint batch and build per-region grids.
    pub fn set_settlement_footprints(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        if rb.num_rows() == 0 {
            self.settlement_grids = vec![[0u16; 100]; self.num_regions];
            return Ok(());
        }

        macro_rules! col_u16 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column: {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt16", $name)))?
            }};
        }
        macro_rules! col_u8 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column: {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt8Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt8", $name)))?
            }};
        }

        let region_ids = col_u16!("region_id");
        let settlement_ids = col_u16!("settlement_id");
        let cell_xs = col_u8!("cell_x");
        let cell_ys = col_u8!("cell_y");

        self.settlement_grids = crate::tick::build_settlement_grids(
            self.num_regions,
            region_ids.values(),
            settlement_ids.values(),
            cell_xs.values(),
            cell_ys.values(),
        );
        Ok(())
    }
```

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: New tests in `test_urban.rs` pass. Existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/test_urban.rs
git commit -m "feat(m56b): grid construction, assignment function, FFI ingestion"
```

---

## Task 3: Rust Dual-Pass Wiring in tick_agents()

**Files:**
- Modify: `chronicler-agents/src/tick.rs:44-54` (`tick_agents` signature)
- Modify: `chronicler-agents/src/tick.rs` (insert Pass A + Pass B calls)
- Modify: `chronicler-agents/src/ffi.rs:2290` (pass grids to `tick_agents`)
- Modify: `chronicler-agents/tests/test_urban.rs`

- [ ] **Step 1: Write dual-pass test**

Add to `chronicler-agents/tests/test_urban.rs`:

```rust
#[test]
fn test_dual_pass_assignment() {
    use chronicler_agents::pool::AgentPool;
    let mut pool = AgentPool::new(4);
    let s0 = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Agent starts at (0.35, 0.72) → cell (3,7) which is urban
    pool.x[s0] = 0.35;
    pool.y[s0] = 0.72;

    let grids = crate::tick::build_settlement_grids(1, &[0], &[1], &[3], &[7]);

    // Pass A: assign from current position
    crate::tick::assign_settlement_ids(&mut pool, &grids);
    assert_eq!(pool.settlement_ids[s0], 1, "Pass A should assign urban");

    // Simulate migration: move agent to (0.95, 0.95) → cell (9,9) which is rural
    pool.x[s0] = 0.95;
    pool.y[s0] = 0.95;

    // Pass B: reassign from new position
    crate::tick::assign_settlement_ids(&mut pool, &grids);
    assert_eq!(pool.settlement_ids[s0], 0, "Pass B should assign rural after move");
}
```

- [ ] **Step 2: Add `settlement_grids` parameter to `tick_agents()`**

In `tick.rs`, modify `tick_agents` signature (line 44) to accept settlement grids:

```rust
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
    wealth_percentiles: &mut [f32],
    spatial_grids: &mut Vec<crate::spatial::SpatialGrid>,
    attractors: &[crate::spatial::RegionAttractors],
    spatial_diag: &mut crate::spatial::SpatialDiagnostics,
    settlement_grids: &[[u16; 100]],  // M56b
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug) {
```

- [ ] **Step 3: Insert Pass A after wealth_tick (before update_needs)**

In `tick_agents()`, after the `wealth_tick(...)` call (line ~86) and before `update_needs(...)` (line ~91), insert:

```rust
    // -----------------------------------------------------------------------
    // M56b Pass A: assign settlement_id from pre-movement position
    // -----------------------------------------------------------------------
    assign_settlement_ids(pool, settlement_grids);
```

- [ ] **Step 4: Insert Pass B after death cleanup (before cultural drift)**

After the death cleanup sweep section (step 5.1, around line ~633) and before cultural drift (step 6, around line ~636), insert:

```rust
    // -----------------------------------------------------------------------
    // M56b Pass B: reassign settlement_id from post-movement position
    // -----------------------------------------------------------------------
    assign_settlement_ids(pool, settlement_grids);
```

- [ ] **Step 5: Update `ffi.rs` `tick()` call to pass settlement_grids**

In `ffi.rs` at the `tick_agents` call (line ~2290), add the new parameter:

```rust
        let (events, kin_failures, formation_stats, demo_debug) = crate::tick::tick_agents(
            &mut self.pool,
            &self.regions,
            &signals,
            self.master_seed,
            turn,
            &mut self.wealth_percentiles,
            &mut self.spatial_grids,
            &self.attractors,
            &mut spatial_diag,
            &self.settlement_grids,  // M56b
        );
```

- [ ] **Step 6: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass including new dual-pass test.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/test_urban.rs
git commit -m "feat(m56b): dual-pass settlement assignment in tick_agents"
```

---

## Task 4: Rust Needs Modifiers

**Files:**
- Modify: `chronicler-agents/src/needs.rs:183-250` (`restore_needs()`)
- Modify: `chronicler-agents/tests/test_urban.rs`

- [ ] **Step 1: Write directional needs tests**

Add to `chronicler-agents/tests/test_urban.rs`:

```rust
#[test]
fn test_urban_safety_restores_slower() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Set identical starting need
    pool_urban.need_safety[su] = 0.3;
    pool_rural.need_safety[sr] = 0.3;
    // Mark urban
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    let regions = vec![RegionState::default()];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![chronicler_agents::signals::CivSignals::default()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    crate::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    crate::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    // Urban safety should restore less than rural
    assert!(pool_urban.need_safety[su] < pool_rural.need_safety[sr],
        "Urban safety {:.4} should be < rural {:.4}",
        pool_urban.need_safety[su], pool_rural.need_safety[sr]);
}

#[test]
fn test_urban_material_food_contribution_reduced() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_urban.need_material[su] = 0.3;
    pool_rural.need_material[sr] = 0.3;
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    // Set high food_sufficiency, zero wealth → isolates food contribution
    let mut region = RegionState::default();
    region.food_sufficiency = 1.2;
    let regions = vec![region];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![chronicler_agents::signals::CivSignals::default()],
        contested_regions: vec![false],
    };
    let wp = vec![0.0_f32]; // zero wealth → only food term contributes

    crate::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    crate::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    // With zero wealth, only food term contributes to material.
    // Urban food contribution is 0.92x, so urban material should be lower.
    assert!(pool_urban.need_material[su] < pool_rural.need_material[sr],
        "Urban material (food only) {:.4} should be < rural {:.4}",
        pool_urban.need_material[su], pool_rural.need_material[sr]);
}

#[test]
fn test_urban_social_restores_faster() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_urban.need_social[su] = 0.3;
    pool_rural.need_social[sr] = 0.3;
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    let regions = vec![RegionState::default()];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![chronicler_agents::signals::CivSignals::default()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    crate::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    crate::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    assert!(pool_urban.need_social[su] > pool_rural.need_social[sr],
        "Urban social {:.4} should be > rural {:.4}",
        pool_urban.need_social[su], pool_rural.need_social[sr]);
}

#[test]
fn test_rural_agent_unchanged_from_baseline() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_a = AgentPool::new(2);
    let mut pool_b = AgentPool::new(2);

    let sa = pool_a.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sb = pool_b.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_a.need_safety[sa] = 0.3;
    pool_a.need_material[sa] = 0.3;
    pool_a.need_social[sa] = 0.3;
    pool_b.need_safety[sb] = 0.3;
    pool_b.need_material[sb] = 0.3;
    pool_b.need_social[sb] = 0.3;

    // Both rural (settlement_id = 0)
    pool_a.settlement_ids[sa] = 0;
    pool_b.settlement_ids[sb] = 0;

    let regions = vec![RegionState::default()];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![chronicler_agents::signals::CivSignals::default()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    crate::needs::update_needs(&mut pool_a, &regions, &signals, &wp);
    crate::needs::update_needs(&mut pool_b, &regions, &signals, &wp);

    // Two identical rural agents should produce identical results
    assert!((pool_a.need_safety[sa] - pool_b.need_safety[sb]).abs() < 1e-6);
    assert!((pool_a.need_material[sa] - pool_b.need_material[sb]).abs() < 1e-6);
    assert!((pool_a.need_social[sa] - pool_b.need_social[sb]).abs() < 1e-6);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo nextest run -E 'test(urban)'`
Expected: FAIL — `settlement_ids` field exists but `restore_needs()` doesn't read it yet, so urban and rural will be identical.

- [ ] **Step 3: Implement urban modifiers in `restore_needs()`**

In `needs.rs` `restore_needs()` (line 183), add after the `let region = &regions[region_idx];` line:

```rust
        let is_urban = pool.settlement_ids[slot] != 0;
```

In the **Safety** block (around line 225), before `pool.need_safety[slot] += delta;`, add:

```rust
            if is_urban {
                delta *= agent::URBAN_SAFETY_RESTORATION_MULT;
            }
```

In the **Material** block (around line 228-244), modify to apply per-term multipliers:

```rust
        // ----- Material -----
        {
            let deficit = 1.0 - pool.need_material[slot];
            let mut delta = 0.0_f32;

            // Food sufficiency (per-term urban modifier)
            let mut food_contribution = agent::MATERIAL_RESTORE_FOOD
                * region.food_sufficiency.min(1.5) * deficit;
            if is_urban {
                food_contribution *= agent::URBAN_FOOD_SUFFICIENCY_MULT;
            }
            delta += food_contribution;

            // Per-agent wealth percentile (per-term urban modifier)
            let wp = if slot < wealth_percentiles.len() {
                wealth_percentiles[slot]
            } else {
                0.0
            };
            let mut wealth_contribution = agent::MATERIAL_RESTORE_WEALTH * wp * deficit;
            if is_urban {
                wealth_contribution *= agent::URBAN_WEALTH_RESTORATION_MULT;
            }
            delta += wealth_contribution;

            pool.need_material[slot] += delta;
        }
```

In the **Social** block, before `pool.need_social[slot] += delta;` (or its equivalent), add:

```rust
            if is_urban {
                delta *= agent::URBAN_SOCIAL_RESTORATION_MULT;
            }
```

Note: the social restoration uses a helper function `social_restoration()`. Apply the multiplier to its return value before adding to the pool:

```rust
        // ----- Social -----
        {
            let mut delta = social_restoration(pool, slot, region);
            if is_urban {
                delta *= agent::URBAN_SOCIAL_RESTORATION_MULT;
            }
            pool.need_social[slot] += delta;
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo nextest run -E 'test(urban)'`
Expected: All urban needs tests pass.

- [ ] **Step 5: Run full test suite**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass. No regressions.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/needs.rs chronicler-agents/tests/test_urban.rs
git commit -m "feat(m56b): urban needs restoration modifiers"
```

---

## Task 5: Rust Satisfaction Modifiers

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs:132-159` (`SatisfactionInputs`)
- Modify: `chronicler-agents/src/satisfaction.rs:162+` (`compute_satisfaction_with_culture()`)
- Modify: `chronicler-agents/src/tick.rs` (populate `is_urban` in `update_satisfaction()`)
- Modify: `chronicler-agents/tests/test_urban.rs`

- [ ] **Step 1: Write satisfaction tests**

Add to `chronicler-agents/tests/test_urban.rs`:

```rust
#[test]
fn test_urban_satisfaction_material_bonus() {
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};

    let mut base = SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.5, pop_over_capacity: 0.0,
        civ_at_war: false, region_contested: false,
        occ_matches_faction: false, is_displaced: false,
        trade_routes: 1, faction_influence: 0.0,
        shock: chronicler_agents::signals::CivShock::default(),
        agent_values: [0, 0, 0], controller_values: [0, 0, 0],
        agent_belief: 0, majority_belief: 0, has_temple: false,
        persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
        is_urban: false,
    };
    let rural = compute_satisfaction_with_culture(&base);
    base.is_urban = true;
    let urban = compute_satisfaction_with_culture(&base);

    let diff = urban - rural;
    // Urban should be higher by approximately URBAN_MATERIAL_SATISFACTION_BONUS (0.02)
    // minus URBAN_SAFETY_SATISFACTION_PENALTY (0.04), net = -0.02
    // But material bonus is positive and safety penalty is negative, so net is:
    // +0.02 (material) - 0.04 (safety) = -0.02
    assert!(diff > -0.03 && diff < -0.01,
        "Urban-rural diff {:.4} should be ~-0.02", diff);
}

#[test]
fn test_urban_safety_penalty_respects_cap() {
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};

    // Max out three_term: cultural(0.15) + religious(0.05) + persecution(0.15) = 0.35
    // Leaves 0.05 for urban safety (0.04) + class tension
    let mut inp = SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.5, pop_over_capacity: 0.0,
        civ_at_war: false, region_contested: false,
        occ_matches_faction: false, is_displaced: false,
        trade_routes: 1, faction_influence: 0.0,
        shock: chronicler_agents::signals::CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [0, 1, 5], // max cultural mismatch
        agent_belief: 1, majority_belief: 2,                     // religious mismatch
        has_temple: false,
        persecution_intensity: 1.0,                               // max persecution
        gini_coefficient: 1.0, wealth_percentile: 0.0,          // max class tension
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
        is_urban: true,
    };
    let urban_sat = compute_satisfaction_with_culture(&inp);
    inp.is_urban = false;
    let rural_sat = compute_satisfaction_with_culture(&inp);

    // Both should hit the cap. Urban has material bonus but penalty is capped.
    // The difference should be approximately +0.02 (material bonus, outside cap)
    let diff = urban_sat - rural_sat;
    assert!(diff > 0.01 && diff < 0.03,
        "At cap, urban-rural diff {:.4} should be ~+0.02 (material bonus only)", diff);
}
```

- [ ] **Step 2: Add `is_urban` field to `SatisfactionInputs`**

In `satisfaction.rs`, add after `memory_score: f32` (line ~158):

```rust
    // M56b: Urban context
    pub is_urban: bool,
```

- [ ] **Step 3: Grep for all `SatisfactionInputs` construction sites and add `is_urban: false`**

Run: `grep -rn "SatisfactionInputs {" chronicler-agents/src/ chronicler-agents/tests/`

Add `is_urban: false,` (or `is_urban: pool.settlement_ids[slot] != 0,` in `update_satisfaction`) to every construction site. This is critical — missing one causes a compile error.

In `tick.rs` `update_satisfaction()`, where `SatisfactionInputs` is built per-agent, set:

```rust
                is_urban: pool.settlement_ids[slot] != 0,
```

In all test construction sites, set `is_urban: false` unless the test specifically tests urban behavior.

- [ ] **Step 4: Add urban terms to `compute_satisfaction_with_culture()`**

In `satisfaction.rs` `compute_satisfaction_with_culture()`, after computing `three_term` and before the class tension calculation:

```rust
    // M56b: Urban safety penalty — priority 2 (after three_term, before class tension)
    let urban_safety_pen = if inp.is_urban {
        crate::agent::URBAN_SAFETY_SATISFACTION_PENALTY
    } else {
        0.0
    };
    let urban_safety_clamped = urban_safety_pen
        .min((crate::agent::PENALTY_CAP - three_term).max(0.0));
```

Modify the class tension clamp to account for urban safety:

```rust
    let class_tension_clamped = class_tension_pen
        .min((crate::agent::PENALTY_CAP - three_term - urban_safety_clamped).max(0.0));
```

Modify the memory penalty remaining budget:

```rust
    let memory_penalty = if inp.memory_score < 0.0 {
        (-inp.memory_score).min((crate::agent::PENALTY_CAP - three_term - urban_safety_clamped - class_tension_clamped).max(0.0))
    } else {
        -inp.memory_score
    };
```

Modify the total penalty:

```rust
    let total_non_eco_penalty = (three_term + urban_safety_clamped + class_tension_clamped + memory_penalty)
        .min(crate::agent::PENALTY_CAP)
        .max(0.0);
```

Add urban material bonus (outside penalty cap, positive):

```rust
    // M56b: Urban material bonus (positive, outside penalty cap)
    let urban_material_bonus = if inp.is_urban {
        crate::agent::URBAN_MATERIAL_SATISFACTION_BONUS
    } else {
        0.0
    };
```

Add to the final satisfaction return value (wherever the base satisfaction is summed):

```rust
    base + urban_material_bonus - total_non_eco_penalty - food_penalty
```

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass including new satisfaction tests.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs chronicler-agents/tests/test_urban.rs
git commit -m "feat(m56b): urban satisfaction modifiers with priority clamp"
```

---

## Task 6: Rust Culture Drift and Conversion Modifiers

**Files:**
- Modify: `chronicler-agents/src/culture_tick.rs:32+`
- Modify: `chronicler-agents/src/conversion_tick.rs:23+`
- Modify: `chronicler-agents/tests/test_urban.rs`

- [ ] **Step 1: Write culture drift test**

Add to `chronicler-agents/tests/test_urban.rs`:

```rust
#[test]
fn test_urban_culture_drifts_faster() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_urban = AgentPool::new(10);
    let mut pool_rural = AgentPool::new(10);

    // Spawn enough agents with same starting values
    let mut urban_slots = Vec::new();
    let mut rural_slots = Vec::new();
    for _ in 0..5 {
        let su = pool_urban.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let sr = pool_rural.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        pool_urban.settlement_ids[su] = 1;
        pool_rural.settlement_ids[sr] = 0;
        urban_slots.push(su);
        rural_slots.push(sr);
    }

    let mut region = RegionState::default();
    region.controller_values = [1, 2, 3]; // different from agent default (0,0,0)
    region.culture_investment_active = true;
    region.population = 5;

    let seed = [42u8; 32];
    crate::culture_tick::culture_tick(&mut pool_urban, &urban_slots, &region, seed, 1, 0, 1.0);
    crate::culture_tick::culture_tick(&mut pool_rural, &rural_slots, &region, seed, 1, 0, 1.0);

    // Count how many values changed in urban vs rural
    let urban_changes: u32 = urban_slots.iter().map(|&s| {
        (pool_urban.cultural_value_0[s] != 0) as u32 +
        (pool_urban.cultural_value_1[s] != 0) as u32 +
        (pool_urban.cultural_value_2[s] != 0) as u32
    }).sum();
    let rural_changes: u32 = rural_slots.iter().map(|&s| {
        (pool_rural.cultural_value_0[s] != 0) as u32 +
        (pool_rural.cultural_value_1[s] != 0) as u32 +
        (pool_rural.cultural_value_2[s] != 0) as u32
    }).sum();

    // Urban should have at least as many changes (probabilistically more due to 1.15x)
    // This is a directional test — with enough agents the probability of equality is low
    assert!(urban_changes >= rural_changes,
        "Urban changes {} should be >= rural changes {}", urban_changes, rural_changes);
}
```

- [ ] **Step 2: Write conversion test**

Add to `chronicler-agents/tests/test_urban.rs`:

```rust
#[test]
fn test_urban_conversion_higher_probability() {
    use chronicler_agents::pool::AgentPool;
    use chronicler_agents::region::RegionState;

    let mut pool_urban = AgentPool::new(100);
    let mut pool_rural = AgentPool::new(100);
    let mut urban_slots = Vec::new();
    let mut rural_slots = Vec::new();

    for _ in 0..50 {
        let su = pool_urban.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let sr = pool_rural.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        pool_urban.settlement_ids[su] = 1;
        pool_rural.settlement_ids[sr] = 0;
        // Start with belief 0, conversion target is 1
        pool_urban.beliefs[su] = 0;
        pool_rural.beliefs[sr] = 0;
        urban_slots.push(su);
        rural_slots.push(sr);
    }

    let mut region = RegionState::default();
    region.conversion_rate = 0.5;
    region.conversion_target_belief = 1;
    region.majority_belief = 1;

    let seed = [42u8; 32];
    crate::conversion_tick::conversion_tick(&mut pool_urban, &urban_slots, &region, seed, 1, 0, 1.0);
    crate::conversion_tick::conversion_tick(&mut pool_rural, &rural_slots, &region, seed, 1, 0, 1.0);

    let urban_converted: u32 = urban_slots.iter().map(|&s| (pool_urban.beliefs[s] == 1) as u32).sum();
    let rural_converted: u32 = rural_slots.iter().map(|&s| (pool_rural.beliefs[s] == 1) as u32).sum();

    assert!(urban_converted >= rural_converted,
        "Urban conversions {} should be >= rural conversions {}", urban_converted, rural_converted);
}
```

- [ ] **Step 3: Implement culture drift modifier**

In `culture_tick.rs`, in `culture_tick()`, find where the per-agent drift probability or rate is computed. The function processes each agent's cultural values with a probability of adopting the region's dominant values.

Add the urban multiplier to the effective drift rate. Find the per-agent drift roll section and multiply the drift probability/weight by the urban multiplier:

```rust
        let urban_mult = if pool.settlement_ids[slot] != 0 {
            crate::agent::URBAN_CULTURE_DRIFT_MULT
        } else {
            1.0
        };
```

Apply `urban_mult` as a multiplier on the drift probability for this agent.

Note: the exact application point depends on how `culture_tick` computes per-agent drift. Read the function to find where the per-agent roll or weight is applied, and multiply by `urban_mult` there. The implementer must read `culture_tick.rs` to find the right insertion point.

- [ ] **Step 4: Implement conversion modifier**

In `conversion_tick.rs`, in the per-agent conversion loop (around line 47), multiply the conversion probability by the urban multiplier:

```rust
        let urban_mult = if pool.settlement_ids[slot] != 0 {
            crate::agent::URBAN_CONVERSION_MULT
        } else {
            1.0
        };
```

Apply `urban_mult` to the conversion roll threshold or probability before comparing to the RNG output.

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/culture_tick.rs chronicler-agents/src/conversion_tick.rs chronicler-agents/tests/test_urban.rs
git commit -m "feat(m56b): urban culture drift and conversion modifiers"
```

---

## Task 7: Python Settlement Batch and Bridge Wiring

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `tests/test_agent_bridge.py`

- [ ] **Step 1: Write `build_settlement_batch()` test**

Add to `tests/test_agent_bridge.py`:

```python
def test_build_settlement_batch_basic():
    """Settlement batch includes ACTIVE and DISSOLVING footprints, sorted correctly."""
    from chronicler.agent_bridge import build_settlement_batch
    from chronicler.models import WorldState, Region, Settlement, SettlementStatus

    world = _make_minimal_world()  # use existing test helper
    s1 = Settlement(
        settlement_id=1, name="Town A", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=50, status=SettlementStatus.ACTIVE,
        footprint_cells=[(3, 7), (4, 7)],
    )
    s2 = Settlement(
        settlement_id=2, name="Town B", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=30, status=SettlementStatus.DISSOLVING,
        footprint_cells=[(5, 5)],
    )
    s_candidate = Settlement(
        settlement_id=3, name="Maybe", region_name=world.regions[0].name,
        last_seen_turn=10, population_estimate=10, status=SettlementStatus.CANDIDATE,
        footprint_cells=[(9, 9)],
    )
    world.regions[0].settlements = [s1, s2, s_candidate]

    batch = build_settlement_batch(world)
    assert batch.num_rows == 3  # 2 cells from s1 + 1 from s2, candidate excluded
    # Verify sort order: (region_id, settlement_id, cell_y, cell_x)
    region_ids = batch.column("region_id").to_pylist()
    settlement_ids = batch.column("settlement_id").to_pylist()
    assert settlement_ids == [1, 1, 2]  # sorted by settlement_id


def test_build_settlement_batch_overflow_guard():
    """Overflow guard fires when next_settlement_id > 65535."""
    from chronicler.agent_bridge import build_settlement_batch

    world = _make_minimal_world()
    world.next_settlement_id = 65536
    import pytest
    with pytest.raises(ValueError, match="65535"):
        build_settlement_batch(world)
```

- [ ] **Step 2: Implement `build_settlement_batch()`**

Add to `agent_bridge.py`:

```python
def build_settlement_batch(world: WorldState) -> pa.RecordBatch:
    """Build settlement footprint Arrow batch for Rust-side grid construction.

    Includes ACTIVE and DISSOLVING settlements. Excludes CANDIDATE and DISSOLVED.
    Sorted by (region_id, settlement_id, cell_y, cell_x).
    """
    from chronicler.models import SettlementStatus

    if world.next_settlement_id > 65535:
        raise ValueError(
            f"next_settlement_id ({world.next_settlement_id}) exceeds u16 max 65535"
        )

    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    rows: list[tuple[int, int, int, int]] = []

    for region in world.regions:
        region_id = region_name_to_idx[region.name]
        for settlement in region.settlements:
            if settlement.status not in (SettlementStatus.ACTIVE, SettlementStatus.DISSOLVING):
                continue
            for cell_x, cell_y in settlement.footprint_cells:
                rows.append((region_id, settlement.settlement_id, cell_y, cell_x))

    # Deterministic sort: (region_id, settlement_id, cell_y, cell_x)
    rows.sort()

    if not rows:
        return pa.RecordBatch.from_pydict(
            {
                "region_id": pa.array([], type=pa.uint16()),
                "settlement_id": pa.array([], type=pa.uint16()),
                "cell_x": pa.array([], type=pa.uint8()),
                "cell_y": pa.array([], type=pa.uint8()),
            }
        )

    region_ids, settlement_ids, cell_ys, cell_xs = zip(*rows)
    return pa.RecordBatch.from_pydict(
        {
            "region_id": pa.array(region_ids, type=pa.uint16()),
            "settlement_id": pa.array(settlement_ids, type=pa.uint16()),
            "cell_x": pa.array(cell_xs, type=pa.uint8()),
            "cell_y": pa.array(cell_ys, type=pa.uint8()),
        }
    )
```

- [ ] **Step 3: Wire `build_settlement_batch` into `sync_regions()`**

In `agent_bridge.py`, modify `sync_regions()` (line ~733) to also send settlement footprints:

```python
    def sync_regions(self, world: WorldState) -> None:
        self._sim.set_region_state(build_region_batch(world, self._economy_result))
        # M56b: Send settlement footprints for urban classification
        settlement_batch = build_settlement_batch(world)
        self._sim.set_settlement_footprints(settlement_batch)
```

Also add the same call in the `tick()` compatibility wrapper if it calls `set_region_state` directly, or in the `__init__` method where the initial `set_region_state` is called.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_agent_bridge.py -v -k "settlement_batch"`
Expected: Both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m56b): build_settlement_batch and bridge wiring"
```

---

## Task 8: Python Snapshot and Model Additions

**Files:**
- Modify: `src/chronicler/models.py:748` (`CivSnapshot`)
- Modify: `src/chronicler/models.py:792` (`TurnSnapshot`)
- Modify: `src/chronicler/models.py:868` (`AgentContext`)
- Modify: `src/chronicler/main.py:330-366` (snapshot build)

- [ ] **Step 1: Add model fields**

In `models.py`, add to `CivSnapshot` (after `gini: float = 0.0`):

```python
    urban_agents: int = 0
    urban_fraction: float = 0.0
```

In `TurnSnapshot`, add after `dissolved_this_turn`:

```python
    # M56b: Urban metrics
    urban_agent_count: int = 0
    urban_fraction: float = 0.0
```

In `AgentContext`, add after `trade_dependent_regions`:

```python
    # M56b: Urbanization context
    urban_fraction_delta_20t: float = 0.0
    top_settlements: list[dict] = Field(default_factory=list)
```

- [ ] **Step 2: Add urban aggregation in snapshot build**

In `main.py`, after the CivSnapshot construction block (line ~364), compute urban fractions from the agent snapshot.

The agent snapshot is stored on `world._agent_snapshot` (an Arrow RecordBatch from `get_snapshot()`). If the snapshot has a `settlement_id` column, aggregate:

```python
        # M56b: Urban fraction aggregation from agent snapshot
        urban_by_civ: dict[str, tuple[int, int]] = {}  # civ_name → (urban_count, total_count)
        if agent_bridge and hasattr(world, '_agent_snapshot') and world._agent_snapshot is not None:
            snap = world._agent_snapshot
            if "settlement_id" in snap.column_names:
                civ_col = snap.column("civ_affinity").to_pylist()
                sid_col = snap.column("settlement_id").to_pylist()
                for civ_id, sid in zip(civ_col, sid_col):
                    civ_name = world.civilizations[civ_id].name if civ_id < len(world.civilizations) else None
                    if civ_name:
                        u, t = urban_by_civ.get(civ_name, (0, 0))
                        urban_by_civ[civ_name] = (u + (1 if sid > 0 else 0), t + 1)
```

Then update the CivSnapshot entries:

```python
        for civ_name, cs in snapshot.civ_stats.items():
            if civ_name in urban_by_civ:
                u, t = urban_by_civ[civ_name]
                cs.urban_agents = u
                cs.urban_fraction = u / t if t > 0 else 0.0
```

And set TurnSnapshot urban totals:

```python
        total_urban = sum(u for u, _ in urban_by_civ.values())
        total_agents = sum(t for _, t in urban_by_civ.values())
        snapshot.urban_agent_count = total_urban
        snapshot.urban_fraction = total_urban / total_agents if total_agents > 0 else 0.0
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_main.py tests/test_simulation.py -v`
Expected: Existing tests pass. New fields default to 0 in test scenarios.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py src/chronicler/main.py
git commit -m "feat(m56b): urban snapshot fields and aggregation"
```

---

## Task 9: Narrator Context Enrichment

**Files:**
- Modify: `src/chronicler/narrative.py`
- Modify: `tests/test_narrative.py`

- [ ] **Step 1: Write narration context test**

Add to `tests/test_narrative.py`:

```python
def test_agent_context_has_urban_fields():
    """AgentContext includes urbanization fields when populated."""
    from chronicler.models import AgentContext
    ctx = AgentContext(
        urban_fraction_delta_20t=0.05,
        top_settlements=[{"name": "Ur", "population_estimate": 500}],
    )
    assert ctx.urban_fraction_delta_20t == 0.05
    assert len(ctx.top_settlements) == 1
```

- [ ] **Step 2: Enrich AgentContext in narration pipeline**

Find where `AgentContext` is built in `narrative.py` (search for `AgentContext(`). Add the urbanization fields:

```python
    # M56b: Urbanization context
    urban_fraction_delta_20t = 0.0
    if len(history) >= 20:
        past_turn = current_turn - 20
        past_snapshot = next((s for s in history if s.turn == past_turn), None)
        if past_snapshot and civ_name in past_snapshot.civ_stats:
            past_frac = past_snapshot.civ_stats[civ_name].urban_fraction
            current_frac = current_snapshot.civ_stats.get(civ_name, None)
            if current_frac is not None:
                urban_fraction_delta_20t = current_frac.urban_fraction - past_frac

    # Top settlements for this civ's regions
    top_settlements = []
    for region in world.regions:
        if region.controller == civ_name:
            for s in sorted(region.settlements, key=lambda s: s.population_estimate, reverse=True)[:3]:
                if s.status.value in ("active", "dissolving"):
                    top_settlements.append({
                        "name": s.name,
                        "population_estimate": s.population_estimate,
                        "region_name": s.region_name,
                        "status": s.status.value,
                    })
    top_settlements.sort(key=lambda s: s["population_estimate"], reverse=True)
    top_settlements = top_settlements[:3]
```

Pass these into the `AgentContext` constructor:

```python
    agent_context = AgentContext(
        ...,  # existing fields
        urban_fraction_delta_20t=urban_fraction_delta_20t,
        top_settlements=top_settlements,
    )
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_narrative.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat(m56b): narrator context urbanization enrichment"
```

---

## Task 10: Analytics Extension

**Files:**
- Modify: `src/chronicler/analytics.py:1862+` (`extract_settlement_diagnostics()`)
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write analytics test**

Add to `tests/test_analytics.py`:

```python
def test_settlement_diagnostics_includes_urbanization():
    """extract_settlement_diagnostics includes urban fraction time series."""
    from chronicler.analytics import extract_settlement_diagnostics
    from chronicler.models import TurnSnapshot, CivSnapshot

    # Build minimal history with urban fractions
    history = []
    for t in range(5):
        snap = _make_minimal_snapshot(turn=t)  # use existing test helper
        # Set urban fields
        for civ_name in snap.civ_stats:
            snap.civ_stats[civ_name].urban_agents = t * 10
            snap.civ_stats[civ_name].urban_fraction = t * 0.1
        snap.urban_agent_count = t * 10
        snap.urban_fraction = t * 0.1
        history.append(snap)

    result = extract_settlement_diagnostics(history)
    assert "urbanization" in result
    assert "global_trend" in result["urbanization"]
    assert len(result["urbanization"]["global_trend"]) == 5
```

- [ ] **Step 2: Extend `extract_settlement_diagnostics()`**

In `analytics.py`, in `extract_settlement_diagnostics()`, add after the existing settlement extraction logic:

```python
    # M56b: Urbanization time series
    urbanization = {
        "global_trend": [],
        "per_civ": {},
    }
    for snap in history:
        urbanization["global_trend"].append({
            "turn": snap.turn,
            "urban_agent_count": snap.urban_agent_count,
            "urban_fraction": snap.urban_fraction,
        })
        for civ_name, cs in snap.civ_stats.items():
            if civ_name not in urbanization["per_civ"]:
                urbanization["per_civ"][civ_name] = []
            urbanization["per_civ"][civ_name].append({
                "turn": snap.turn,
                "urban_agents": cs.urban_agents,
                "urban_fraction": cs.urban_fraction,
            })
    result["urbanization"] = urbanization
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_analytics.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/analytics.py tests/test_analytics.py
git commit -m "feat(m56b): urbanization analytics time series"
```

---

## Task 11: Off-Mode Validation and Integration Smoke

**Files:**
- No new files. Validation commands only.

- [ ] **Step 1: Run off-mode smoke test**

Run:
```bash
$env:PYTHONPATH = "src"
python -m chronicler.main --seed 42 --turns 30 --agents off --simulate-only
```
Expected: Completes without error. No urban metrics (settlement detection is no-op in off-mode).

- [ ] **Step 2: Run all Python tests**

Run: `python -m pytest tests/ -q`
Expected: All tests pass.

- [ ] **Step 3: Run all Rust tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass.

- [ ] **Step 4: Run hybrid smoke (if Workstream 0 is fixed)**

Run:
```bash
$env:PYTHONPATH = "src"
python -m chronicler.main --seed 42 --turns 30 --agents hybrid --simulate-only
```
Expected: If hybrid blocker is fixed, completes without error. If still blocked, note the failure and skip — this is documented in the spec as a blocked merge gate.

- [ ] **Step 5: Commit any test fixes needed**

If any integration issues surface, fix and commit individually.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "test(m56b): off-mode validation and integration smoke"
```

---

## Merge Gates (from spec section 8.3)

1. All unit + directional tests green (Tasks 1-6)
2. Off-mode 30-turn run clean (Task 11 step 1)
3. Hybrid 30-turn run clean (Task 11 step 4) — blocked until Workstream 0
4. 200-seed regression sweep — deferred to M61b
