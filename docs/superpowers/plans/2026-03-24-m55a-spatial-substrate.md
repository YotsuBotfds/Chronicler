# M55a: Spatial Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give agents continuous (x, y) positions, deterministic movement via attractor forces, per-region spatial hash, and generic index-sort infrastructure (region-key + Morton Z-curve).

**Architecture:** New `spatial.rs` and `sort.rs` modules in the Rust crate. Spatial drift inserted as tick step 4.5 (between apply_decisions and demographics). Per-region attractor positions computed once at init, weights updated each tick from RegionState. Spatial hash rebuilt each tick, persisted on AgentSimulator for cross-phase reuse. Two new snapshot columns (`x`, `y`) appended at end. Two new region-batch columns (`is_capital`, `temple_prestige`) for attractor weight computation.

**Tech Stack:** Rust (chronicler-agents crate), PyO3/Arrow FFI, Python (agent_bridge.py, analytics.py)

**Spec:** `docs/superpowers/specs/2026-03-24-m55a-spatial-substrate-design.md`

**Subagent dispatch checklist (from CLAUDE.md):**
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially treasury/tithe/population fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.

---

## File Map

### New Files (Rust)

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/spatial.rs` | Attractor model (RegionAttractors, AttractorType), SpatialGrid, drift computation, migration reset, all spatial constants |
| `chronicler-agents/src/sort.rs` | Radix sort on u64 keys, morton_interleave, sort_by_region, sort_by_morton, sorted_iteration_order, threshold activation |

### Modified Files (Rust)

| File | Changes |
|------|---------|
| `chronicler-agents/src/lib.rs` | Add `pub mod spatial;` and `pub mod sort;` |
| `chronicler-agents/src/agent.rs` | Keep `INITIAL_AGE_STREAM_OFFSET` at 1400, register `SPATIAL_POSITION/DRIFT` at 2000/2001, update collision test |
| `chronicler-agents/src/pool.rs` | Add `x: Vec<f32>`, `y: Vec<f32>` SoA fields. Init in `new()`, both `spawn()` branches, `to_record_batch()` |
| `chronicler-agents/src/region.rs` | Add `is_capital: bool`, `temple_prestige: f32` to RegionState |
| `chronicler-agents/src/ffi.rs` | Parse new region columns in `set_region_state()` (both AgentSimulator and EcologySimulator). Add `x`/`y` to `snapshot_schema()`. Add `get_spatial_diagnostics()` getter. Wire spatial init on first `set_region_state()`. |
| `chronicler-agents/src/tick.rs` | Insert tick step 4.5 (spatial drift) between apply_decisions and demographics. Parent position snapshot before death pass. Newborn placement. |

### Modified Files (Python)

| File | Changes |
|------|---------|
| `src/chronicler/agent_bridge.py` | Add `is_capital` and `temple_prestige` columns to `build_region_batch()`. |
| `src/chronicler/analytics.py` | Add `extract_spatial_diagnostics()` extractor. |

### Test Files

| File | Changes |
|------|---------|
| `chronicler-agents/tests/test_spatial.rs` | New: spatial hash, attractor init, drift convergence, repulsion, migration reset, parent death safety, hotspot formation |
| `chronicler-agents/tests/test_sort.rs` | New: radix sort correctness, morton interleave, determinism, threshold activation |
| `tests/test_agent_bridge.py` | Update `test_snapshot_schema` for new `x`/`y` columns |
| `tests/test_analytics.py` (or nearest analytics suite) | Python-side: `extract_spatial_diagnostics()` coverage |

---

## Task 1: RNG Offset Resolution (Prerequisite)

**Files:**
- Modify: `chronicler-agents/src/agent.rs:107-112` (stream offsets), `chronicler-agents/src/agent.rs:398-410` (collision test)
- Test: `cargo nextest run -p chronicler-agents stream_offset`

- [ ] **Step 1: Write failing test for new offsets**

In `agent.rs`, the collision test at line ~398 will need the spatial offsets in a separate range while leaving the existing age stream untouched. First, update the constants:

```rust
// agent.rs
pub const INITIAL_AGE_STREAM_OFFSET: u64 = 1400;
pub const SPATIAL_POSITION_STREAM_OFFSET: u64 = 2000;
pub const SPATIAL_DRIFT_STREAM_OFFSET: u64 = 2001;
```

- [ ] **Step 2: Update collision test array**

In the collision test (line ~399-410), keep the age stream entry at 1400 and add the spatial streams in the new range:

```rust
// In the test array, keep INITIAL_AGE_STREAM_OFFSET and add spatial:
let offsets = [
    DECISION_STREAM_OFFSET,
    DEMOGRAPHICS_STREAM_OFFSET,
    MIGRATION_STREAM_OFFSET,
    CULTURE_DRIFT_OFFSET,
    CONVERSION_STREAM_OFFSET,
    PERSONALITY_STREAM_OFFSET,
    GOODS_ALLOC_STREAM_OFFSET,
    MEMORY_STREAM_OFFSET,
    MULE_STREAM_OFFSET,
    RELATIONSHIP_STREAM_OFFSET,
    INITIAL_AGE_STREAM_OFFSET,       // 1400
    SPATIAL_POSITION_STREAM_OFFSET,  // 2000
    SPATIAL_DRIFT_STREAM_OFFSET,     // 2001
];
```

- [ ] **Step 3: Run collision test**

Run: `cargo nextest run -p chronicler-agents stream_offset`
Expected: PASS — all offsets unique.

- [ ] **Step 4: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All existing tests pass. The offset move only affects determinism of existing seeds, not test correctness.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/agent.rs
git commit -m "refactor(m55a): register spatial RNG streams without shifting age seeding"
```

---

## Task 2: RegionState Fields + Python Bridge Columns

**Files:**
- Modify: `chronicler-agents/src/region.rs:18-77`, `chronicler-agents/src/ffi.rs:~538`, `chronicler-agents/src/ffi.rs:~2004`
- Modify: `src/chronicler/agent_bridge.py:196-300`
- Test: `cargo nextest run -p chronicler-agents`, `pytest tests/test_agent_bridge.py`

- [ ] **Step 1: Add fields to RegionState**

In `region.rs`, add to the `RegionState` struct:

```rust
pub is_capital: bool,
pub temple_prestige: f32,
```

Update `RegionState::new()` (or `Default`) to set `is_capital: false, temple_prestige: 0.0`.

- [ ] **Step 2: Update all Rust test constructors**

Grep for `RegionState {` and `RegionState::new(` across all test files. Add the new fields with defaults to every constructor call. Remember: no struct literals in tests — use constructor functions if they exist, otherwise add the fields.

Run: `cargo nextest run -p chronicler-agents`
Expected: All existing tests pass with new defaults.

- [ ] **Step 3: Parse new columns in AgentSimulator's set_region_state()**

In `ffi.rs` at the `AgentSimulator` `set_region_state()` method (~line 538), add optional column parsing after existing columns:

```rust
// Optional: is_capital (bool, default false)
let is_capital = rb.column_by_name("is_capital")
    .and_then(|c| c.as_any().downcast_ref::<BooleanArray>())
    .map(|a| a.value(i))
    .unwrap_or(false);

// Optional: temple_prestige (f32, default 0.0)
let temple_prestige = rb.column_by_name("temple_prestige")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>())
    .map(|a| a.value(i))
    .unwrap_or(0.0);
```

Wire these into the `RegionState` construction for each region.

- [ ] **Step 4: Parse new columns in EcologySimulator's set_region_state()**

In `ffi.rs` at `EcologySimulator` `set_region_state()` (~line 2004), add the same optional parsing. Ecology doesn't use these values, but the parser must not reject batches that contain them.

- [ ] **Step 5: Add columns to Python build_region_batch()**

In `agent_bridge.py` `build_region_batch()` (line 196), add after existing columns:

```python
# is_capital: any alive civ has this region as capital
alive_civs = [c for c in world.civilizations if c.regions]
is_capital_flags = [
    any(c.capital_region == r.name for c in alive_civs)
    for r in world.regions
]

# temple_prestige: max prestige of any temple infrastructure in the region
# Use InfrastructureType enum, matching the existing _has_temple() pattern at line 243
from chronicler.models import InfrastructureType
temple_prestiges = []
for r in world.regions:
    max_prest = 0.0
    for inf in r.infrastructure:
        if inf.type == InfrastructureType.TEMPLES and inf.active:
            max_prest = max(max_prest, float(getattr(inf, 'temple_prestige', 0) or 0))
    temple_prestiges.append(max_prest)
```

Add to the RecordBatch construction:

```python
"is_capital": pa.array(is_capital_flags, type=pa.bool_()),
"temple_prestige": pa.array(temple_prestiges, type=pa.float32()),
```

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents` and `pytest tests/test_agent_bridge.py`
Expected: All pass. Existing test batches don't include the new columns, but the optional parsing handles this.

- [ ] **Step 7: Commit**

```
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py
git commit -m "feat(m55a): add is_capital and temple_prestige to RegionState and bridge"
```

---

## Task 3: Pool SoA Fields + Snapshot Schema

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-86` (struct), `chronicler-agents/src/pool.rs:142` (spawn), `chronicler-agents/src/pool.rs:467` (to_record_batch)
- Modify: `chronicler-agents/src/ffi.rs:64` (snapshot_schema)
- Test: `chronicler-agents/tests/test_spatial.rs` (new), `tests/test_agent_bridge.py:64`

- [ ] **Step 1: Add x, y to AgentPool struct**

In `pool.rs` after the `// Spatial` comment (line 20), the `regions` and `origin_regions` fields already exist. Add:

```rust
pub x: Vec<f32>,
pub y: Vec<f32>,
```

- [ ] **Step 2: Initialize in AgentPool::new()**

In the `new()` method, add alongside other Vec allocations:

```rust
x: Vec::with_capacity(capacity),
y: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Initialize in spawn() — both branches**

In `spawn()` (line 142), the function takes parameters and has two branches (free-list reuse vs growth). For now, init to `0.5` (center of unit square). The spatial init system will overwrite this on first `set_region_state()`.

Free-list reuse branch:
```rust
self.x[slot] = 0.5;
self.y[slot] = 0.5;
```

Growth branch:
```rust
self.x.push(0.5);
self.y.push(0.5);
```

- [ ] **Step 4: Add x, y to snapshot_schema()**

In `ffi.rs` `snapshot_schema()` (line 64), append at the END of the field list:

```rust
Field::new("x", DataType::Float32, false),
Field::new("y", DataType::Float32, false),
```

- [ ] **Step 5: Add x, y to to_record_batch()**

In `pool.rs` `to_record_batch()` (line 467), append at the END of the column list:

```rust
Arc::new(Float32Array::from(x_values)) as ArrayRef,
Arc::new(Float32Array::from(y_values)) as ArrayRef,
```

Where `x_values` and `y_values` are collected from alive agents in the same order as other columns.

- [ ] **Step 6: Update Python schema test**

In `tests/test_agent_bridge.py:64` (`test_snapshot_schema`), add `"x"` and `"y"` to the expected column list at the end.

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents` and `pytest tests/test_agent_bridge.py`
Expected: All pass with new schema.

- [ ] **Step 8: Commit**

```
git add chronicler-agents/src/pool.rs chronicler-agents/src/ffi.rs tests/test_agent_bridge.py
git commit -m "feat(m55a): add x, y SoA fields to AgentPool and snapshot schema"
```

---

## Task 4: Spatial Hash (SpatialGrid)

**Files:**
- Create: `chronicler-agents/src/spatial.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Test: `chronicler-agents/tests/test_spatial.rs` (new)

- [ ] **Step 1: Create spatial.rs with constants and SpatialGrid struct**

```rust
// chronicler-agents/src/spatial.rs

use crate::pool::AgentPool;

pub const GRID_SIZE: usize = 10;

pub struct SpatialGrid {
    pub cells: Vec<Vec<u32>>,  // GRID_SIZE × GRID_SIZE, each cell holds slot indices
}

impl SpatialGrid {
    pub fn new() -> Self {
        Self {
            cells: (0..GRID_SIZE * GRID_SIZE).map(|_| Vec::new()).collect(),
        }
    }

    pub fn clear(&mut self) {
        for cell in &mut self.cells {
            cell.clear();
        }
    }

    /// Insert an agent at (x, y) into the grid.
    pub fn insert(&mut self, slot: u32, x: f32, y: f32) {
        let cx = ((x * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        let cy = ((y * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        self.cells[cy * GRID_SIZE + cx].push(slot);
    }

    /// Query neighbors: returns slot indices from 9 cells around (x, y),
    /// sorted by slot index, excluding `exclude_slot`.
    pub fn query_neighbors(&self, x: f32, y: f32, exclude_slot: u32) -> Vec<u32> {
        let cx = ((x * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);
        let cy = ((y * GRID_SIZE as f32) as usize).min(GRID_SIZE - 1);

        let mut result = Vec::new();
        let x_min = cx.saturating_sub(1);
        let x_max = (cx + 1).min(GRID_SIZE - 1);
        let y_min = cy.saturating_sub(1);
        let y_max = (cy + 1).min(GRID_SIZE - 1);

        for row in y_min..=y_max {
            for col in x_min..=x_max {
                for &slot in &self.cells[row * GRID_SIZE + col] {
                    if slot != exclude_slot {
                        result.push(slot);
                    }
                }
            }
        }
        result.sort_unstable();
        result
    }
}
```

- [ ] **Step 2: Register module in lib.rs**

Add `pub mod spatial;` to `chronicler-agents/src/lib.rs` after the existing module declarations.

- [ ] **Step 3: Add rebuild helper for per-tick grid construction**

In `spatial.rs`, add:

```rust
pub fn rebuild_spatial_grids(pool: &AgentPool, grids: &mut Vec<SpatialGrid>, num_regions: u16) {
    if grids.len() != num_regions as usize {
        grids.clear();
        grids.resize_with(num_regions as usize, SpatialGrid::new);
    }
    for g in grids.iter_mut() {
        g.clear();
    }
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let r = pool.regions[slot] as usize;
            if r < grids.len() {
                grids[r].insert(slot as u32, pool.x[slot], pool.y[slot]);
            }
        }
    }
}
```

- [ ] **Step 4: Write tests for SpatialGrid**

Create `chronicler-agents/tests/test_spatial.rs`:

```rust
use chronicler_agents::spatial::SpatialGrid;

#[test]
fn test_grid_insert_and_query() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.15, 0.15);  // cell (1, 1)
    grid.insert(1, 0.16, 0.16);  // cell (1, 1)
    grid.insert(2, 0.85, 0.85);  // cell (8, 8) — far away

    let neighbors = grid.query_neighbors(0.15, 0.15, 0);
    assert!(neighbors.contains(&1));
    assert!(!neighbors.contains(&0));  // self excluded
    assert!(!neighbors.contains(&2));  // far away
}

#[test]
fn test_grid_boundary_clamp() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.0, 0.0);     // cell (0, 0) — corner
    grid.insert(1, 0.05, 0.05);   // cell (0, 0) — same cell
    let neighbors = grid.query_neighbors(0.0, 0.0, 0);
    assert!(neighbors.contains(&1));
}

#[test]
fn test_grid_clear_reuse() {
    let mut grid = SpatialGrid::new();
    grid.insert(0, 0.5, 0.5);
    grid.clear();
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert!(neighbors.is_empty());
    // Reinsert after clear:
    grid.insert(1, 0.5, 0.5);
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert_eq!(neighbors, vec![1]);
}

#[test]
fn test_neighbors_sorted_by_slot() {
    let mut grid = SpatialGrid::new();
    grid.insert(5, 0.5, 0.5);
    grid.insert(2, 0.51, 0.51);
    grid.insert(9, 0.49, 0.49);
    let neighbors = grid.query_neighbors(0.5, 0.5, 99);
    assert_eq!(neighbors, vec![2, 5, 9]);  // sorted
}
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents test_spatial`
Expected: All PASS.

- [ ] **Step 6: Commit**

```
git add chronicler-agents/src/spatial.rs chronicler-agents/src/lib.rs chronicler-agents/tests/test_spatial.rs
git commit -m "feat(m55a): add SpatialGrid with insert, query, and boundary clamping"
```

---

## Task 5: Attractor Model

**Files:**
- Modify: `chronicler-agents/src/spatial.rs`
- Test: `chronicler-agents/tests/test_spatial.rs`

- [ ] **Step 1: Add attractor types, constants, and RegionAttractors struct**

Add to `spatial.rs`:

```rust
use crate::agent::OCCUPATION_COUNT;
use crate::region::RegionState;

pub const MAX_ATTRACTORS: usize = 8;
pub const MIN_ATTRACTOR_SEPARATION: f32 = 0.15;  // [CALIBRATE M61b]

#[derive(Clone, Copy, Debug, PartialEq)]
#[repr(u8)]
pub enum AttractorType {
    River = 0,
    Coast = 1,
    Resource0 = 2,
    Resource1 = 3,
    Resource2 = 4,
    Temple = 5,
    Capital = 6,
    Market = 7,  // reserved, inactive
}

pub struct RegionAttractors {
    pub positions: [(f32, f32); MAX_ATTRACTORS],
    pub weights: [f32; MAX_ATTRACTORS],
    pub types: [AttractorType; MAX_ATTRACTORS],
    pub count: u8,
}

/// Occupation affinity table: [OCCUPATION_COUNT × MAX_ATTRACTORS]
/// Indexed by [occupation][attractor_type]
/// All values [CALIBRATE M61b]
pub const OCCUPATION_AFFINITY: [[f32; MAX_ATTRACTORS]; OCCUPATION_COUNT] = [
    // River, Coast, Res0, Res1, Res2, Temple, Capital, Market
    [0.4, 0.1, 0.8, 0.8, 0.8, 0.05, 0.1, 0.0],  // Farmer
    [0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.7, 0.0],  // Soldier
    [0.2, 0.3, 0.3, 0.3, 0.3, 0.05, 0.5, 0.0],  // Merchant
    [0.1, 0.1, 0.1, 0.1, 0.1, 0.5,  0.5, 0.0],  // Scholar
    [0.1, 0.05, 0.05, 0.05, 0.05, 0.8, 0.3, 0.0], // Priest
];
```

- [ ] **Step 2: Implement attractor initialization**

Add `init_attractors()` function that takes `seed: u64`, `region_id: u16`, and `RegionState`, returns `RegionAttractors`. Use deterministic arithmetic from `(seed, region_id, type_discriminant)` for positions. Implement edge-biased placement for River/Coast, interior for others. Apply minimum separation with priority-based pushing (max 10 iterations).

Key implementation details:
- Edge selection: `(seed ^ (region_id as u64) ^ (type as u64)) % 4`
- Interior jitter: use `seed.wrapping_mul(region_id as u64 + 1).wrapping_add(type as u64)` mapped to `[0.1, 0.9]`
- Clamp all positions to `[0.0, 1.0 - f32::EPSILON]`

- [ ] **Step 3: Implement weight update**

Add `update_attractor_weights(attractors: &mut RegionAttractors, region: &RegionState)` that recomputes weights from live region state. Each weight clamped to `[0.0, 1.0]`.

- [ ] **Step 4: Write attractor tests**

Add to `test_spatial.rs`:

```rust
#[test]
fn test_attractor_separation() {
    // Create a region with river + all 3 resources + temple + capital
    // Verify no two attractors are closer than MIN_ATTRACTOR_SEPARATION
}

#[test]
fn test_attractor_weight_dynamics() {
    // Init attractors with high resource yield
    // Update weights with yield dropped to 0
    // Verify resource attractor weight is 0
}

#[test]
fn test_attractor_determinism() {
    // Same seed + region → identical attractor positions
    let a1 = init_attractors(42, 5, &region);
    let a2 = init_attractors(42, 5, &region);
    assert_eq!(a1.positions, a2.positions);
}
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents test_spatial`
Expected: All PASS.

- [ ] **Step 6: Commit**

```
git add chronicler-agents/src/spatial.rs chronicler-agents/tests/test_spatial.rs
git commit -m "feat(m55a): add attractor model with init, weight update, and separation enforcement"
```

---

## Task 6: Drift Computation

**Files:**
- Modify: `chronicler-agents/src/spatial.rs`
- Test: `chronicler-agents/tests/test_spatial.rs`

- [ ] **Step 1: Add drift constants**

Add all movement constants to `spatial.rs` (see spec Section 4.5 for full list):

```rust
pub const MAX_DRIFT_PER_TICK: f32 = 0.04;
pub const DENSITY_RADIUS: f32 = 0.15;
pub const REPULSION_RADIUS: f32 = 0.05;
pub const DENSITY_ATTRACTION_MAX: f32 = 0.02;
pub const DENSITY_MIN_DIST: f32 = 0.005;
pub const REPULSION_MIN_DIST: f32 = 0.001;
pub const REPULSION_ZERO_DIST_FORCE: f32 = 5.0;
pub const REPULSION_FORCE_CAP: f32 = 50.0;
pub const ATTRACTOR_DEADZONE: f32 = 0.02;
pub const ATTRACTOR_RANGE: f32 = 0.5;
pub const W_ATTRACTOR: f32 = 0.6;
pub const W_DENSITY: f32 = 0.3;
pub const W_REPULSION: f32 = 0.5;
pub const MIGRATION_JITTER: f32 = 0.05;
pub const BIRTH_JITTER: f32 = 0.02;
```

- [ ] **Step 2: Implement compute_drift_for_agent()**

This is the core force computation. Takes: agent position, occupation, RegionAttractors, neighbor positions + IDs (from spatial hash query), agent_id. Returns: new (x, y).

Implementation must follow spec Section 4.3 exactly:
1. Attractor vector with softened linear falloff and deadzone
2. Density vector with mean direction to neighbors, capped, skip co-located
3. Repulsion vector with capped inverse-square, deterministic zero-distance fallback with PI flip for `agent_id < neighbor_id`
4. Weighted sum → clamp magnitude → boundary clamp

- [ ] **Step 3: Implement two-pass spatial drift step**

Add `spatial_drift_step()` with this signature:

```rust
pub fn spatial_drift_step(
    pool: &mut AgentPool,
    grids: &[SpatialGrid],
    attractors: &[RegionAttractors],
)
```

This function does NOT handle migration reset or newborn placement — it only computes drift for agents that are already at valid positions. Migration reset and newborn placement are separate functions called from tick.rs at different points (see Task 8).

Performs the two-pass update:
1. Snapshot all (x, y) into scratch buffers
2. For each alive agent in slot-index order: query neighbors from hash using OLD positions, compute drift, write NEW position
3. Write all new positions back to pool

- [ ] **Step 4: Implement migration_reset_position()**

```rust
pub fn migration_reset_position(
    agent_id: u32,
    occupation: u8,
    attractors: &RegionAttractors,
    master_seed: &[u8; 32],
    dest_region_id: u16,
    turn: u32,
) -> (f32, f32)
```

Returns (x, y) near highest-affinity attractor for the agent's occupation, with jitter from RNG stream `SPATIAL_POSITION_STREAM_OFFSET` keyed deterministically per `(agent_id, dest_region_id, turn)`. Fallback to `(0.5, 0.5)` if no matching attractor.

Also implement `newborn_position()` with similar signature, using `BIRTH_JITTER` instead of `MIGRATION_JITTER`, placed near parent position.

- [ ] **Step 5: Write drift tests**

```rust
#[test]
fn test_drift_convergence() {
    // Place one agent far from a single resource attractor, no neighbors
    // Run drift for 20 iterations
    // Verify agent moved closer to attractor
}

#[test]
fn test_repulsion_separates_colocated() {
    // Place two agents at identical position
    // Run one drift step
    // Verify they are now at different positions (symmetry broken)
}

#[test]
fn test_drift_displacement_cap() {
    // Place agent very far from a very strong attractor
    // Verify single-step displacement <= MAX_DRIFT_PER_TICK
}

#[test]
fn test_migration_reset_near_attractor() {
    // Create attractors with a Resource attractor
    // Reset a Farmer agent → should land near the Resource attractor
}
```

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents test_spatial`
Expected: All PASS.

- [ ] **Step 7: Commit**

```
git add chronicler-agents/src/spatial.rs chronicler-agents/tests/test_spatial.rs
git commit -m "feat(m55a): implement drift computation with attractor/density/repulsion forces"
```

---

## Task 7: Sort Infrastructure

**Files:**
- Create: `chronicler-agents/src/sort.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Test: `chronicler-agents/tests/test_sort.rs` (new)

- [ ] **Step 1: Create sort.rs with morton_interleave and radix sort**

```rust
// chronicler-agents/src/sort.rs

use crate::pool::AgentPool;

pub const SPATIAL_SORT_AGENT_THRESHOLD: usize = 100_000; // [CALIBRATE M61b]

/// Interleave 8-bit x and y into 16-bit Morton/Z-curve code.
pub fn morton_interleave(x: u8, y: u8) -> u16 {
    let mut x32 = x as u32;
    let mut y32 = y as u32;
    // Standard bit-interleave for 8-bit inputs
    x32 = (x32 | (x32 << 8)) & 0x00FF00FF;
    x32 = (x32 | (x32 << 4)) & 0x0F0F0F0F;
    x32 = (x32 | (x32 << 2)) & 0x33333333;
    x32 = (x32 | (x32 << 1)) & 0x55555555;
    y32 = (y32 | (y32 << 8)) & 0x00FF00FF;
    y32 = (y32 | (y32 << 4)) & 0x0F0F0F0F;
    y32 = (y32 | (y32 << 2)) & 0x33333333;
    y32 = (y32 | (y32 << 1)) & 0x55555555;
    (x32 | (y32 << 1)) as u16
}

/// Radix sort on u64 keys. Returns sorted indices.
pub fn radix_sort_u64(keys: &[u64]) -> Vec<usize> { ... }

/// Region-key sort: (region_index << 32) | agent_id
pub fn sort_by_region(pool: &AgentPool) -> Vec<usize> { ... }

/// Morton sort: (region_index << 48) | (morton << 32) | agent_id
pub fn sort_by_morton(pool: &AgentPool) -> Vec<usize> { ... }

/// Public entry point. Below threshold: identity. Above: Morton.
pub fn sorted_iteration_order(pool: &AgentPool) -> Vec<usize> { ... }
```

- [ ] **Step 2: Register module in lib.rs**

Add `pub mod sort;` to `lib.rs`.

- [ ] **Step 3: Write sort tests**

Create `chronicler-agents/tests/test_sort.rs`:

```rust
#[test]
fn test_morton_interleave_known_values() {
    assert_eq!(morton_interleave(0, 0), 0);
    assert_eq!(morton_interleave(0xFF, 0xFF), 0xFFFF);
    assert_eq!(morton_interleave(1, 0), 1);  // x bit 0
    assert_eq!(morton_interleave(0, 1), 2);  // y bit 0
}

#[test]
fn test_radix_sort_preserves_order() {
    let keys = vec![30u64, 10, 20, 10];
    let sorted = radix_sort_u64(&keys);
    assert_eq!(sorted, vec![1, 3, 2, 0]); // stable: 10@1 before 10@3
}

#[test]
fn test_sort_by_region_groups_agents() {
    // Build a small pool with agents in regions 0, 2, 1
    // Verify sort_by_region returns them grouped by region, tiebroken by agent_id
}

#[test]
fn test_sorted_iteration_order_below_threshold() {
    // Small pool (< SPATIAL_SORT_AGENT_THRESHOLD)
    // Verify returns alive slots in ascending slot index order
}

#[test]
fn test_sort_determinism() {
    // Same pool state → identical sort output (run twice, compare)
}
```

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents test_sort`
Expected: All PASS.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/sort.rs chronicler-agents/src/lib.rs chronicler-agents/tests/test_sort.rs
git commit -m "feat(m55a): add sort infrastructure with radix sort, morton interleave, and threshold activation"
```

---

## Task 8: Tick Step 4.5 Integration

**Files:**
- Modify: `chronicler-agents/src/tick.rs:44` (tick_agents), `chronicler-agents/src/ffi.rs` (AgentSimulator state)
- Test: `chronicler-agents/tests/test_spatial.rs`

This is the wiring task — connecting spatial.rs into the tick pipeline and AgentSimulator.

- [ ] **Step 1: Add spatial state to AgentSimulator**

In `ffi.rs`, add to the `AgentSimulator` struct definition:

```rust
spatial_grids: Vec<SpatialGrid>,
attractors: Vec<RegionAttractors>,
spatial_initialized: bool,
```

Then add to the `Self { ... }` block in `AgentSimulator::new()` (ffi.rs ~line 468):

```rust
spatial_grids: Vec::new(),
attractors: Vec::new(),
spatial_initialized: false,
```

The `AgentSimulator::new()` constructor uses a struct literal — every field must be listed or the code won't compile.

- [ ] **Step 2: Wire spatial init on first set_region_state()**

In `set_region_state()`, after existing region setup, add:

```rust
if !self.spatial_initialized {
    let world_seed = u64::from_le_bytes(self.master_seed[0..8].try_into().unwrap());
    self.attractors = (0..region_count)
        .map(|i| init_attractors(world_seed, i as u16, &self.regions[i]))
        .collect();
    // Init agent positions near occupation-appropriate attractors
    // ... (iterate alive agents, set x/y based on occupation + attractor)
    self.spatial_initialized = true;
}
// Always update weights:
for (i, region) in self.regions.iter().enumerate() {
    if i < self.attractors.len() {
        update_attractor_weights(&mut self.attractors[i], region);
    }
}
```

- [ ] **Step 3: Extend tick_agents() signature and insert tick step 4.5**

Add two new parameters to `tick_agents()` (tick.rs line 44):

```rust
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
    wealth_percentiles: &mut [f32],
    spatial_grids: &mut Vec<SpatialGrid>,
    attractors: &[RegionAttractors],
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug)
```

Thread these through from `AgentSimulator::tick()` in `ffi.rs`:

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
);
```

Update all `tick_agents(...)` call sites (including `tick.rs` internal tests) to pass the new spatial arguments.

- [ ] **Step 4: Insert step 4.5a migration reset in decision-apply loop**

Inside the existing migration loop in `tick.rs` (currently around line 187):

```rust
for &(slot, from, to) in &pd.migrations {
    pool.set_region(slot, to);
    pool.set_displacement_turns(slot, 5);
    let (nx, ny) = crate::spatial::migration_reset_position(
        pool.id(slot),
        pool.occupation(slot),
        &attractors[to as usize],
        &master_seed,
        to,
        turn,
    );
    pool.x[slot] = nx;
    pool.y[slot] = ny;
    // existing event emission unchanged...
}
```

- [ ] **Step 5: Insert step 4.5b/4.5c after decisions, before demographics**

After all decision-apply loops and before step 5 demographics:

```rust
crate::spatial::rebuild_spatial_grids(pool, spatial_grids, num_regions as u16);
crate::spatial::spatial_drift_step(pool, spatial_grids, attractors);
```

Ordering must remain:
1. Migration reset (4.5a)
2. Rebuild hash (4.5b)
3. Two-pass drift (4.5c)
4. Demographics (step 5)

Task 9 will layer diagnostics threading on top of this baseline wiring.

- [ ] **Step 6: Parent snapshot + newborn placement in demographics apply**

Before the death pass (currently around line 430), snapshot parent positions for all queued births using `BirthInfo.parent_id` (stable agent id), not slot index:

```rust
let mut parent_pos: HashMap<u32, (f32, f32)> = HashMap::new();
for (dr, _) in &demo_results {
    for birth in &dr.births {
        if let Some(&parent_slot) = id_to_slot.get(&birth.parent_id) {
            if pool.alive[parent_slot] && pool.ids[parent_slot] == birth.parent_id {
                parent_pos.entry(birth.parent_id)
                    .or_insert((pool.x[parent_slot], pool.y[parent_slot]));
            }
        }
    }
}
```

During births (after `pool.spawn(...)`), set:

```rust
let base = parent_pos.get(&birth.parent_id).copied().unwrap_or((0.5, 0.5));
let (bx, by) = crate::spatial::newborn_position(
    pool.id(new_slot),
    birth.region,
    base,
    &master_seed,
    turn,
);
pool.x[new_slot] = bx;
pool.y[new_slot] = by;
```

- [ ] **Step 7: Run tests**

Run:
- `cargo nextest run -p chronicler-agents test_spatial`
- `cargo nextest run -p chronicler-agents determinism`
- `cargo nextest run -p chronicler-agents`

Expected: all pass, with existing behavior unchanged outside new spatial state.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/src/spatial.rs
git commit -m "feat(m55a): wire spatial step 4.5 into tick with migration reset and newborn placement"
```

---

## Task 9: Diagnostics + Sort Runtime Wiring

**Files:**
- Modify: `chronicler-agents/src/spatial.rs`, `chronicler-agents/src/sort.rs`, `chronicler-agents/src/tick.rs`, `chronicler-agents/src/ffi.rs`
- Modify: `src/chronicler/analytics.py`
- Test: `chronicler-agents/tests/test_spatial.rs`, `tests/test_analytics.py` (or nearest analytics suite)

- [ ] **Step 1: Add SpatialDiagnostics struct**

In `spatial.rs`:

```rust
#[derive(Clone, Debug, Default)]
pub struct SpatialDiagnostics {
    pub hotspot_count_by_region: Vec<u16>,
    pub attractor_occupancy: Vec<[f32; MAX_ATTRACTORS]>,
    pub hash_max_cell_occupancy: Vec<u16>,
    pub sort_time_us: u64,
}
```

- [ ] **Step 2: Populate diagnostics during drift**

Update `spatial_drift_step(...)` to accept `&mut SpatialDiagnostics` and:
1. Time `sorted_iteration_order(pool)` and write `sort_time_us`.
2. Fill `hash_max_cell_occupancy` from grid cell sizes.
3. Fill `hotspot_count_by_region` as cells with occupancy `> 2.0 × mean_cell_occupancy`.
4. Fill `attractor_occupancy` using a fixed radius check per attractor.

Keep calculations deterministic (no hash-map iteration dependence).

- [ ] **Step 3: Expose get_spatial_diagnostics()**

In `ffi.rs`, add:

```rust
#[pyo3(name = "get_spatial_diagnostics")]
pub fn get_spatial_diagnostics(&self) -> PyResult<std::collections::HashMap<String, PyObject>> { ... }
```

Store last tick diagnostics on `AgentSimulator` (`last_spatial_diag: SpatialDiagnostics`) and return Python-friendly lists.

Also in this step:
- Extend `tick_agents(...)` to take `spatial_diag: &mut SpatialDiagnostics`.
- In `tick.rs`, create/accumulate diagnostics around step 4.5 and write through that out-parameter.
- In `ffi.rs` `AgentSimulator::tick()`, instantiate `SpatialDiagnostics::default()`, pass it into `tick_agents(...)`, then assign `self.last_spatial_diag = spatial_diag`.
- Update `tick_agents(...)` call sites in `tick.rs` tests to pass a local diagnostics object.

- [ ] **Step 4: Add analytics extractor**

In `src/chronicler/analytics.py`, add:

```python
def extract_spatial_diagnostics(diag_history: list[dict]) -> dict:
    """Summarize per-turn spatial diagnostics emitted by Rust."""
```

This extractor should consume a list of per-turn payloads from `get_spatial_diagnostics()` and emit:
- hotspot persistence stats
- attractor occupancy summaries
- hash occupancy distribution
- sort time trend

Scope note: keep this as a standalone extractor for M55a (no bundle metadata plumbing required in this task).

- [ ] **Step 5: Add tests**

Rust:
- diagnostics vectors sized to `num_regions`
- `sort_time_us >= 0`
- hotspot/hash metrics deterministic for same seed

Python:
- extractor handles missing/empty diagnostics gracefully
- extractor returns stable schema keys

- [ ] **Step 6: Run tests**

Run:
- `cargo nextest run -p chronicler-agents test_spatial`
- `pytest tests/test_analytics.py`

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/spatial.rs chronicler-agents/src/sort.rs chronicler-agents/src/ffi.rs src/chronicler/analytics.py
git commit -m "feat(m55a): add spatial diagnostics and wire sort timing into runtime telemetry"
```

---

## Task 10: Determinism + Integration Gates

**Files:**
- Modify: `chronicler-agents/tests/determinism.rs`, `chronicler-agents/tests/test_spatial.rs`, `chronicler-agents/tests/test_sort.rs`
- Modify: `tests/test_agent_bridge.py`

- [ ] **Step 1: Cross-thread determinism for spatial state**

Add test: same seed, same region batch, run N ticks in 1/4/8/16-thread pools, compare full `x/y` snapshot columns bit-for-bit.

- [ ] **Step 2: Cross-process determinism for spatial state**

Add two-process replay test (existing determinism harness pattern) that compares serialized `id,region,x,y` rows after fixed ticks.

- [ ] **Step 3: Migration reset determinism test**

Force deterministic migration event and assert landed position is identical across reruns for same seed.

- [ ] **Step 4: Parent death + slot reuse safety test**

Construct same-tick parent death and birth with slot reuse pressure; assert newborn still receives parent-position-based placement from snapshot, not reused-slot artifacts.

- [ ] **Step 5: Bridge schema tests**

Update `tests/test_agent_bridge.py`:
- `test_snapshot_schema` expects trailing `x`, `y`
- region batch includes `is_capital`, `temple_prestige`
- minimal batches without new columns still parse (optional column fallback)

- [ ] **Step 6: Run tests**

Run:
- `cargo nextest run -p chronicler-agents determinism`
- `cargo nextest run -p chronicler-agents test_spatial test_sort`
- `pytest tests/test_agent_bridge.py`

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/tests/determinism.rs chronicler-agents/tests/test_spatial.rs chronicler-agents/tests/test_sort.rs tests/test_agent_bridge.py
git commit -m "test(m55a): add determinism and bridge integration gates for spatial substrate"
```

---

## Task 11: Benchmarks + Final Validation

**Files:**
- Modify: `chronicler-agents/benches/cache_bench.rs` (or add a new bench if preferred)
- Modify: `docs/superpowers/progress/phase-6-progress.md` (session update after implementation lands)

- [ ] **Step 1: Add 3-way sort benchmark cases**

Benchmark sizes: 50K, 100K, 500K, 1M agents.
Modes:
1. Arena order (identity)
2. Region-key sort
3. Morton-key sort

Record:
- sort duration
- drift-loop duration (or representative cache-sensitive loop)

- [ ] **Step 2: Run benchmark harness**

Run:
- `cargo bench --bench cache_bench`

Capture median + p95 for each mode/size in benchmark notes.

- [ ] **Step 3: Milestone validation run**

Run full suites:
- `cargo nextest run -p chronicler-agents`
- `pytest tests/test_agent_bridge.py tests/test_analytics.py`

Then run the standard seed comparison workflow for milestone validation (per repo practice).

- [ ] **Step 4: Update progress log**

After implementation completion, update `docs/superpowers/progress/phase-6-progress.md` with:
- completed M55a scope
- residual risks/tuning deferred to M61b
- follow-up hooks for M55b

- [ ] **Step 5: Final commit(s)**

```bash
git add chronicler-agents/benches/cache_bench.rs docs/superpowers/progress/phase-6-progress.md
git commit -m "perf(m55a): add spatial sort benchmarks and complete milestone validation notes"
```

---

## Dependency Graph (Execution Order)

### Track A: Prerequisites (parallel)
1. Task 1 — RNG offsets
2. Task 2 — RegionState + bridge columns
3. Task 3 — Pool SoA + snapshot schema

### Track B: Spatial core (sequential)
4. Task 4 — SpatialGrid
5. Task 5 — Attractors
6. Task 6 — Drift/migration/newborn position helpers

### Track C: Sort infra (parallel with Track B)
7. Task 7 — sort.rs

### Integration (sequential after A+B+C)
8. Task 8 — Tick/FFI wiring
9. Task 9 — Diagnostics + runtime sort telemetry
10. Task 10 — Determinism/integration gates
11. Task 11 — Benchmarks + final validation

This preserves the intended three-track parallelism while keeping behavior-changing integration on a single critical path.
