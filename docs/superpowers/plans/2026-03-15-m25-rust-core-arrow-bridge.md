# M25: Rust Core + Arrow Bridge Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the `chronicler-agents` Rust crate with PyO3 bindings, SoA agent pool with arena, Arrow FFI, rayon parallelism, and a demographic tick (age + die only).

**Architecture:** Standalone Rust crate (`chronicler-agents/`) built with maturin into a Python 3.12 wheel. `AgentPool` stores agent fields as struct-of-arrays with a free-list arena. Arrow RecordBatches cross the FFI boundary via pyo3-arrow PyCapsule (zero-copy). Rayon parallelizes the per-region tick with ChaCha8Rng stream splitting for determinism. Python-side `AgentBridge` wrapper integrates into `simulation.py` between Phase 9 and Phase 10.

**Tech Stack:** Rust (stable), PyO3, pyo3-arrow, rand_chacha, rayon, tikv-jemallocator (Linux/WSL), maturin, Python 3.12, pyarrow, pytest, criterion

**Spec:** `docs/superpowers/specs/2026-03-15-m25-rust-core-arrow-bridge-design.md`

**Implementation notes from Phoebe's review:**
- `partition_by_region` and `pool` passed to parallel tick must be two separate let-bindings (not chained) to make borrow lifetimes obvious
- Stream ID `region_id * 1000 + turn` is a readability convention — ChaCha streams are independent regardless of arithmetic relationships
- `_apply_demographics_clamp` writes to controlled regions only — M26 migration may place agents in uncontrolled regions
- Demographics-only clamp uses raw `carrying_capacity * 1.2`, not `effective_capacity()` — Rust-side ecological stress already accounts for soil/water in mortality

---

## File Structure

| File | Responsibility |
|---|---|
| `chronicler-agents/Cargo.toml` (NEW) | Crate dependencies, release profile, jemalloc cfg-gate |
| `chronicler-agents/pyproject.toml` (NEW) | maturin build backend, Python 3.12 ABI pin |
| `chronicler-agents/src/lib.rs` (NEW) | PyO3 module entry, jemalloc global allocator (cfg-gated) |
| `chronicler-agents/src/agent.rs` (NEW) | Occupation enum, age bracket constants, mortality rates |
| `chronicler-agents/src/region.rs` (NEW) | Terrain enum, RegionState struct |
| `chronicler-agents/src/pool.rs` (NEW) | AgentPool SoA + free-list arena, spawn/kill/accessors, Arrow serialization |
| `chronicler-agents/src/ffi.rs` (NEW) | PyO3 AgentSimulator class, Arrow schemas, all #[pymethods] |
| `chronicler-agents/src/tick.rs` (NEW) | tick_agents (rayon), tick_region_demographics, PendingEvents, ecological_stress |
| `chronicler-agents/tests/determinism.rs` (NEW) | Rust-side determinism tests with varying thread counts |
| `chronicler-agents/src/pool.rs` (tests section) | Arrow round-trip tests (schema and value verification) |
| `chronicler-agents/benches/tick_bench.rs` (NEW) | Criterion benchmark: 6K agents × 1 tick |
| `src/chronicler/agent_bridge.py` (NEW) | AgentBridge wrapper, build_region_batch, TERRAIN_MAP, demographics clamp |
| `src/chronicler/simulation.py` (MODIFY) | Add optional `agent_bridge` param to `run_turn`, insert tick between Phase 9 and 10 |
| `tests/test_agent_bridge.py` (NEW) | Python round-trip, determinism, demographics-only integration tests |

---

## Chunk 1: Crate Scaffolding + Build Verification

### Task 1: Create Cargo.toml and pyproject.toml

**Files:**
- Create: `chronicler-agents/Cargo.toml`
- Create: `chronicler-agents/pyproject.toml`

- [ ] **Step 1: Create chronicler-agents directory**

```bash
mkdir -p chronicler-agents/src
```

- [ ] **Step 2: Write Cargo.toml**

Create `chronicler-agents/Cargo.toml`:

```toml
[package]
name = "chronicler-agents"
version = "0.1.0"
edition = "2021"

[lib]
name = "chronicler_agents"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
pyo3-arrow = "0.5"
arrow = { version = "54", default-features = false, features = ["ffi"] }
rand = "0.8"
rand_chacha = "0.3"
rayon = "1.10"

[target.'cfg(not(target_os = "windows"))'.dependencies]
tikv-jemallocator = "0.6"

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
rayon = "1.10"
arrow = { version = "54", default-features = false, features = ["ffi"] }

[profile.release]
codegen-units = 1
lto = true
opt-level = 3

[[bench]]
name = "tick_bench"
harness = false
```

- [ ] **Step 3: Write pyproject.toml**

Create `chronicler-agents/pyproject.toml`:

```toml
[build-system]
requires = ["maturin>=1.5,<2.0"]
build-backend = "maturin"

[project]
name = "chronicler-agents"
version = "0.1.0"
description = "Rust agent simulation core for Chronicler"
requires-python = ">=3.12,<3.13"

[tool.maturin]
features = ["pyo3/extension-module"]
```

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/Cargo.toml chronicler-agents/pyproject.toml
git commit -m "feat(m25): scaffold chronicler-agents crate with Cargo.toml and pyproject.toml"
```

---

### Task 2: Create lib.rs with PyO3 Module Entry

**Files:**
- Create: `chronicler-agents/src/lib.rs`

- [ ] **Step 1: Write lib.rs with jemalloc cfg-gate and empty PyO3 module**

Create `chronicler-agents/src/lib.rs`:

```rust
//! Chronicler agent simulation core.
//!
//! Provides a Rust-backed agent-based population model with PyO3 bindings
//! and Arrow FFI for zero-copy data exchange with the Python orchestrator.

use pyo3::prelude::*;

// jemalloc: cfg-gated to non-Windows. Windows dev uses system allocator.
// Performance benchmarks run on WSL/Linux where jemalloc is active.
#[cfg(not(target_os = "windows"))]
use tikv_jemallocator::Jemalloc;

#[cfg(not(target_os = "windows"))]
#[global_allocator]
static GLOBAL: Jemalloc = Jemalloc;

/// Python module entry point.
#[pymodule]
fn chronicler_agents(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // AgentSimulator will be registered here in Task 7
    Ok(())
}
```

- [ ] **Step 2: Verify Rust compilation**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors (warnings about unused imports are OK at this stage)

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/lib.rs
git commit -m "feat(m25): add lib.rs with PyO3 module entry and jemalloc cfg-gate"
```

---

### Task 3: Verify maturin Build and Python Import

**Files:**
- No new files — verifies the build pipeline works end-to-end

- [ ] **Step 1: Build with maturin develop**

Run (from the Python 3.12 venv):
```bash
cd chronicler-agents && maturin develop
```
Expected: builds the wheel and installs `chronicler_agents` into the active venv

- [ ] **Step 2: Verify Python import succeeds**

Run:
```bash
python -c "import chronicler_agents; print('import OK')"
```
Expected: prints `import OK`

- [ ] **Step 3: Commit (if any build config needed adjustment)**

Only commit if Step 1 or 2 required fixes. If everything worked, no commit needed — the build pipeline is verified.

---

## Chunk 2: Agent Data Model (agent.rs, region.rs, pool.rs without arena)

### Task 4: Create agent.rs — Occupation Enum and Constants

**Files:**
- Create: `chronicler-agents/src/agent.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `mod agent;`)

- [ ] **Step 1: Write agent.rs**

Create `chronicler-agents/src/agent.rs`:

```rust
//! Agent field definitions and constants — no AoS Agent struct at runtime.
//! Fields are stored as struct-of-arrays in `AgentPool`.

/// Occupation types. repr(u8) for Arrow serialization and SoA storage.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Occupation {
    Farmer = 0,
    Soldier = 1,
    Merchant = 2,
    Scholar = 3,
    Priest = 4,
}

impl Occupation {
    /// Convert from u8. Returns None for invalid values.
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Farmer),
            1 => Some(Self::Soldier),
            2 => Some(Self::Merchant),
            3 => Some(Self::Scholar),
            4 => Some(Self::Priest),
            _ => None,
        }
    }
}

// Age bracket boundaries (in turns)
pub const AGE_ADULT: u16 = 20;
pub const AGE_ELDER: u16 = 60;

// Mortality base rates by age bracket (per tick)
pub const MORTALITY_YOUNG: f32 = 0.005; // age 0–19
pub const MORTALITY_ADULT: f32 = 0.01;  // age 20–59
pub const MORTALITY_ELDER: f32 = 0.05;  // age 60+

/// Number of occupation variants.
pub const OCCUPATION_COUNT: usize = 5;
```

- [ ] **Step 2: Register module in lib.rs**

Add `mod agent;` to `chronicler-agents/src/lib.rs`, before the `#[pymodule]` function:

```rust
mod agent;
```

- [ ] **Step 3: Verify compilation**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/lib.rs
git commit -m "feat(m25): add agent.rs with Occupation enum and mortality constants"
```

---

### Task 5: Create region.rs — Terrain Enum and RegionState

**Files:**
- Create: `chronicler-agents/src/region.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `mod region;`)

- [ ] **Step 1: Write region.rs**

Create `chronicler-agents/src/region.rs`:

```rust
//! Rust-side mirror of Python Region ecology fields.
//!
//! `terrain` is stored as u8 via the Terrain enum — not used in M25's
//! demographic tick but present in the Arrow schema from day one so M26
//! doesn't require a schema migration.

/// Terrain types matching Python's Region.terrain strings.
/// Discriminant values must match TERRAIN_MAP in agent_bridge.py.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Terrain {
    Plains = 0,
    Mountains = 1,
    Coast = 2,
    Forest = 3,
    Desert = 4,
    Tundra = 5,
}

impl Terrain {
    /// Convert from u8. Returns None for invalid values.
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Plains),
            1 => Some(Self::Mountains),
            2 => Some(Self::Coast),
            3 => Some(Self::Forest),
            4 => Some(Self::Desert),
            5 => Some(Self::Tundra),
            _ => None,
        }
    }
}

/// Region state passed from Python via Arrow each tick.
/// Mirrors the ecology fields from Python's Region + RegionEcology models.
#[derive(Clone, Debug)]
pub struct RegionState {
    pub region_id: u16,
    pub terrain: u8,
    /// Python max is 100 (models.py Field(ge=1, le=100)); u16 chosen for that constraint.
    pub carrying_capacity: u16,
    pub population: u16,
    pub soil: f32,
    pub water: f32,
    pub forest_cover: f32,
}

impl RegionState {
    pub fn new(region_id: u16) -> Self {
        Self {
            region_id,
            terrain: Terrain::Plains as u8,
            carrying_capacity: 60,
            population: 0,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
        }
    }
}
```

- [ ] **Step 2: Register module in lib.rs**

Add `mod region;` to `chronicler-agents/src/lib.rs`:

```rust
mod agent;
mod region;
```

- [ ] **Step 3: Verify compilation**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/lib.rs
git commit -m "feat(m25): add region.rs with Terrain enum and RegionState struct"
```

---

### Task 6: Create pool.rs — AgentPool SoA (No Arena Yet)

**Files:**
- Create: `chronicler-agents/src/pool.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `mod pool;`)

- [ ] **Step 1: Write the failing tests first**

Create `chronicler-agents/src/pool.rs` with the struct, basic methods, and tests at the bottom. Start with the test module — we'll fill in the implementation to make them pass:

```rust
//! AgentPool — struct-of-arrays storage for agent fields.
//!
//! All access to the `alive` field goes through `is_alive()`/`set_dead()` methods,
//! enabling a future BitVec swap (M29) as a one-file change.

use crate::agent::Occupation;

/// Struct-of-arrays agent storage.
pub struct AgentPool {
    // SoA arrays — each vec indexed by slot
    ids: Vec<u32>,
    regions: Vec<u16>,
    origin_regions: Vec<u16>,
    civ_affinities: Vec<u16>,
    occupations: Vec<u8>,
    loyalties: Vec<f32>,
    satisfactions: Vec<f32>,
    skills: Vec<f32>,
    ages: Vec<u16>,
    displacement_turns: Vec<u16>,
    alive: Vec<bool>,

    // Bookkeeping
    count: usize,
    next_id: u32,
    // Arena free-list added in Task 11
}

impl AgentPool {
    /// Create an empty pool.
    pub fn new() -> Self {
        Self {
            ids: Vec::new(),
            regions: Vec::new(),
            origin_regions: Vec::new(),
            civ_affinities: Vec::new(),
            occupations: Vec::new(),
            loyalties: Vec::new(),
            satisfactions: Vec::new(),
            skills: Vec::new(),
            ages: Vec::new(),
            displacement_turns: Vec::new(),
            alive: Vec::new(),
            count: 0,
            next_id: 0,
        }
    }

    /// Spawn a new agent. Returns the agent's monotonic ID.
    /// In this initial version, always appends (no free-list yet).
    pub fn spawn(&mut self, region: u16, civ: u16, occupation: Occupation) -> u32 {
        let id = self.next_id;
        self.next_id += 1;

        self.ids.push(id);
        self.regions.push(region);
        self.origin_regions.push(region);
        self.civ_affinities.push(civ);
        self.occupations.push(occupation as u8);
        self.loyalties.push(0.5);
        self.satisfactions.push(0.5);
        self.skills.push(0.3);
        self.ages.push(0);
        self.displacement_turns.push(0);
        self.alive.push(true);
        self.count += 1;

        id
    }

    /// Mark an agent as dead by slot index.
    pub fn kill(&mut self, slot: usize) {
        debug_assert!(self.is_alive(slot), "killing already-dead slot {slot}");
        self.set_dead(slot);
        self.count -= 1;
    }

    // --- Alive field accessors (all alive access goes through these) ---

    /// Check if the agent at `slot` is alive.
    #[inline]
    pub fn is_alive(&self, slot: usize) -> bool {
        self.alive[slot]
    }

    /// Mark slot as dead. Private — callers use `kill()`.
    #[inline]
    fn set_dead(&mut self, slot: usize) {
        self.alive[slot] = false;
    }

    // --- Field accessors ---

    #[inline]
    pub fn age(&self, slot: usize) -> u16 {
        self.ages[slot]
    }

    #[inline]
    pub fn increment_age(&mut self, slot: usize) {
        self.ages[slot] += 1;
    }

    #[inline]
    pub fn region(&self, slot: usize) -> u16 {
        self.regions[slot]
    }

    #[inline]
    pub fn civ_affinity(&self, slot: usize) -> u16 {
        self.civ_affinities[slot]
    }

    #[inline]
    pub fn occupation(&self, slot: usize) -> u8 {
        self.occupations[slot]
    }

    #[inline]
    pub fn satisfaction(&self, slot: usize) -> f32 {
        self.satisfactions[slot]
    }

    #[inline]
    pub fn id(&self, slot: usize) -> u32 {
        self.ids[slot]
    }

    /// Number of alive agents.
    pub fn alive_count(&self) -> usize {
        self.count
    }

    /// Total slots allocated (alive + dead).
    pub fn capacity(&self) -> usize {
        self.ids.len()
    }

    /// Return slot indices of alive agents grouped by region, sorted by region index.
    /// Returns Vec<Vec<usize>> — only indices, no mutable references into SoA vecs.
    pub fn partition_by_region(&self, num_regions: u16) -> Vec<Vec<usize>> {
        let mut groups: Vec<Vec<usize>> = (0..num_regions as usize).map(|_| Vec::new()).collect();
        for slot in 0..self.ids.len() {
            if self.is_alive(slot) {
                let r = self.regions[slot] as usize;
                if r < groups.len() {
                    groups[r].push(slot);
                }
            }
        }
        groups
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    #[test]
    fn test_spawn_into_empty_pool() {
        let mut pool = AgentPool::new();
        let id0 = pool.spawn(0, 1, Occupation::Farmer);
        let id1 = pool.spawn(0, 1, Occupation::Soldier);

        assert_eq!(id0, 0);
        assert_eq!(id1, 1);
        assert_eq!(pool.alive_count(), 2);
        assert_eq!(pool.capacity(), 2);
        assert!(pool.is_alive(0));
        assert!(pool.is_alive(1));
        assert_eq!(pool.age(0), 0);
        assert_eq!(pool.region(0), 0);
        assert_eq!(pool.civ_affinity(0), 1);
        assert_eq!(pool.occupation(0), Occupation::Farmer as u8);
    }

    #[test]
    fn test_kill_marks_dead_and_decrements_count() {
        let mut pool = AgentPool::new();
        pool.spawn(0, 0, Occupation::Farmer);
        pool.spawn(1, 0, Occupation::Soldier);
        assert_eq!(pool.alive_count(), 2);

        pool.kill(0);
        assert!(!pool.is_alive(0));
        assert!(pool.is_alive(1));
        assert_eq!(pool.alive_count(), 1);
        // capacity doesn't shrink
        assert_eq!(pool.capacity(), 2);
    }

    #[test]
    fn test_increment_age() {
        let mut pool = AgentPool::new();
        pool.spawn(0, 0, Occupation::Farmer);
        assert_eq!(pool.age(0), 0);

        pool.increment_age(0);
        assert_eq!(pool.age(0), 1);

        pool.increment_age(0);
        assert_eq!(pool.age(0), 2);
    }

    #[test]
    fn test_partition_by_region() {
        let mut pool = AgentPool::new();
        // Region 0: 2 agents, Region 1: 1 agent, Region 2: 1 agent
        pool.spawn(0, 0, Occupation::Farmer);   // slot 0
        pool.spawn(0, 0, Occupation::Soldier);  // slot 1
        pool.spawn(1, 1, Occupation::Merchant); // slot 2
        pool.spawn(2, 1, Occupation::Scholar);  // slot 3

        // Kill slot 1 (region 0)
        pool.kill(1);

        let groups = pool.partition_by_region(3);
        assert_eq!(groups.len(), 3);
        assert_eq!(groups[0], vec![0]);       // region 0: only slot 0 alive
        assert_eq!(groups[1], vec![2]);       // region 1: slot 2
        assert_eq!(groups[2], vec![3]);       // region 2: slot 3
    }

    #[test]
    fn test_ids_are_monotonic() {
        let mut pool = AgentPool::new();
        let ids: Vec<u32> = (0..10).map(|_| pool.spawn(0, 0, Occupation::Farmer)).collect();
        for (i, id) in ids.iter().enumerate() {
            assert_eq!(*id, i as u32);
        }
    }
}
```

- [ ] **Step 2: Register module in lib.rs**

Add `mod pool;` to `chronicler-agents/src/lib.rs`:

```rust
mod agent;
mod pool;
mod region;
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test`
Expected: all 5 tests pass

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/lib.rs
git commit -m "feat(m25): add AgentPool SoA with spawn/kill/accessors and unit tests"
```

---

## Chunk 3: Arrow FFI Layer

### Task 7: Create ffi.rs — Arrow Schemas and AgentSimulator Shell

**Files:**
- Create: `chronicler-agents/src/ffi.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `mod ffi;`, register AgentSimulator)

- [ ] **Step 1: Write ffi.rs with schemas and AgentSimulator**

Create `chronicler-agents/src/ffi.rs`:

```rust
//! PyO3 bindings and Arrow FFI layer.
//!
//! All Arrow methods use owned PyRecordBatch types (not references)
//! to trigger pyo3-arrow's zero-copy PyCapsule extraction.

use std::sync::Arc;

use arrow::array::{
    Float32Array, UInt8Array, UInt16Array, UInt32Array,
    ArrayRef,
};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use pyo3_arrow::PyRecordBatch;

use crate::agent::Occupation;
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Convert ArrowError to PyErr for use with ? in #[pymethods].
fn arrow_err(e: arrow::error::ArrowError) -> PyErr {
    PyRuntimeError::new_err(e.to_string())
}

// --- Centralized Arrow Schemas ---
// Defined once, referenced everywhere. M26 adds rows to events, not columns.

pub fn snapshot_schema() -> Schema {
    Schema::new(vec![
        Field::new("id", DataType::UInt32, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("origin_region", DataType::UInt16, false),
        Field::new("civ_affinity", DataType::UInt16, false),
        Field::new("occupation", DataType::UInt8, false),
        Field::new("loyalty", DataType::Float32, false),
        Field::new("satisfaction", DataType::Float32, false),
        Field::new("skill", DataType::Float32, false),
        Field::new("age", DataType::UInt16, false),
        Field::new("displacement_turn", DataType::UInt16, false),
    ])
}

pub fn aggregates_schema() -> Schema {
    Schema::new(vec![
        Field::new("civ_id", DataType::UInt16, false),
        Field::new("population", DataType::UInt32, false),
        Field::new("military", DataType::UInt32, false),
        Field::new("economy", DataType::UInt32, false),
        Field::new("culture", DataType::UInt32, false),
        Field::new("stability", DataType::UInt32, false),
    ])
}

pub fn region_populations_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("alive_count", DataType::UInt32, false),
    ])
}

pub fn events_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_id", DataType::UInt32, false),
        Field::new("event_type", DataType::UInt8, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("target_region", DataType::UInt16, false),
        Field::new("civ_affinity", DataType::UInt16, false),
        Field::new("turn", DataType::UInt32, false),
    ])
}

pub fn region_state_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("terrain", DataType::UInt8, false),
        Field::new("carrying_capacity", DataType::UInt16, false),
        Field::new("population", DataType::UInt16, false),
        Field::new("soil", DataType::Float32, false),
        Field::new("water", DataType::Float32, false),
        Field::new("forest_cover", DataType::Float32, false),
    ])
}

#[pyclass]
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    master_seed: [u8; 32],
    num_regions: u16,
    turn: u32,
    initialized: bool,
}

#[pymethods]
impl AgentSimulator {
    /// Create a new simulator.
    /// Seed conversion: bytes 0–7 = seed as little-endian u64, bytes 8–31 = zero.
    #[new]
    fn new(num_regions: u16, seed: u64) -> Self {
        let mut master_seed = [0u8; 32];
        master_seed[..8].copy_from_slice(&seed.to_le_bytes());

        Self {
            pool: AgentPool::new(),
            regions: Vec::new(),
            master_seed,
            num_regions,
            turn: 0,
            initialized: false,
        }
    }

    /// Initialize or update region state from an Arrow RecordBatch.
    /// First call spawns agents proportional to carrying capacity.
    /// Subsequent calls update ecology state only.
    fn set_region_state(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        // NOTE: pyo3-arrow 0.5 API — verify the exact conversion method
        // (batch.into(), batch.into_inner(), RecordBatch::from(batch)).
        // The implementer should check pyo3-arrow docs for the correct method.
        let rb: RecordBatch = batch.into();

        let region_ids = rb.column(0).as_any().downcast_ref::<UInt16Array>().unwrap();
        let terrains = rb.column(1).as_any().downcast_ref::<UInt8Array>().unwrap();
        let capacities = rb.column(2).as_any().downcast_ref::<UInt16Array>().unwrap();
        let populations = rb.column(3).as_any().downcast_ref::<UInt16Array>().unwrap();
        let soils = rb.column(4).as_any().downcast_ref::<Float32Array>().unwrap();
        let waters = rb.column(5).as_any().downcast_ref::<Float32Array>().unwrap();
        let forests = rb.column(6).as_any().downcast_ref::<Float32Array>().unwrap();

        if !self.initialized {
            // First call: create regions and spawn agents
            self.regions.clear();
            for i in 0..rb.num_rows() {
                let rs = RegionState {
                    region_id: region_ids.value(i),
                    terrain: terrains.value(i),
                    carrying_capacity: capacities.value(i),
                    population: populations.value(i),
                    soil: soils.value(i),
                    water: waters.value(i),
                    forest_cover: forests.value(i),
                };
                // Spawn agents proportional to carrying capacity
                // Distribute as ~60% farmer, ~15% soldier, ~10% merchant, ~10% scholar, ~5% priest
                let cap = rs.carrying_capacity as usize;
                let occupations = [
                    (Occupation::Farmer, cap * 60 / 100),
                    (Occupation::Soldier, cap * 15 / 100),
                    (Occupation::Merchant, cap * 10 / 100),
                    (Occupation::Scholar, cap * 10 / 100),
                    (Occupation::Priest, cap.saturating_sub(cap * 60 / 100 + cap * 15 / 100 + cap * 10 / 100 + cap * 10 / 100)),
                ];
                let region_id = rs.region_id;
                let civ = 0u16; // Will be set from Python region.controller mapping
                for (occ, count) in &occupations {
                    for _ in 0..*count {
                        self.pool.spawn(region_id, civ, *occ);
                    }
                }
                self.regions.push(rs);
            }
            self.initialized = true;
        } else {
            // Subsequent calls: update ecology state
            for i in 0..rb.num_rows() {
                let rid = region_ids.value(i) as usize;
                if rid < self.regions.len() {
                    self.regions[rid].terrain = terrains.value(i);
                    self.regions[rid].carrying_capacity = capacities.value(i);
                    self.regions[rid].population = populations.value(i);
                    self.regions[rid].soil = soils.value(i);
                    self.regions[rid].water = waters.value(i);
                    self.regions[rid].forest_cover = forests.value(i);
                }
            }
        }

        Ok(())
    }

    /// Run one demographic tick. Returns events RecordBatch (empty in M25).
    /// Errors if set_region_state() was never called.
    fn tick(&mut self, turn: u32) -> PyResult<PyRecordBatch> {
        if !self.initialized {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "tick() called before set_region_state()"
            ));
        }
        self.turn = turn;

        crate::tick::tick_agents(
            &mut self.pool,
            &self.regions,
            self.master_seed,
            turn,
        );

        // M25: return empty events batch (schema only, zero rows)
        let schema = Arc::new(events_schema());
        let empty = RecordBatch::new_empty(schema);
        Ok(PyRecordBatch::new(empty))
    }

    /// Return Arrow RecordBatch of all alive agents.
    fn get_snapshot(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.to_record_batch().map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return per-civ aggregated stats.
    /// M25: population populated, military/economy/culture/stability zeroed.
    fn get_aggregates(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.compute_aggregates().map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return per-region (region_id, alive_count) pairs.
    fn get_region_populations(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.region_populations(self.num_regions).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }
}
```

**NOTE:** This references `pool.to_record_batch()`, `pool.compute_aggregates()`, `pool.region_populations()`, and `crate::tick::tick_agents` which don't exist yet. They'll be added in the next steps. For now the code won't compile — that's expected.

- [ ] **Step 2: Register module and AgentSimulator in lib.rs**

Update `chronicler-agents/src/lib.rs`:

```rust
mod agent;
mod ffi;
mod pool;
mod region;

use pyo3::prelude::*;

#[cfg(not(target_os = "windows"))]
use tikv_jemallocator::Jemalloc;

#[cfg(not(target_os = "windows"))]
#[global_allocator]
static GLOBAL: Jemalloc = Jemalloc;

#[pymodule]
fn chronicler_agents(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ffi::AgentSimulator>()?;
    Ok(())
}
```

- [ ] **Step 3: Do NOT try to compile yet**

This task creates the FFI shell. It depends on Arrow serialization methods in pool.rs (Task 8) and tick.rs (Task 11) which come next. Leave it uncommitted until Task 8 makes it compile.

---

### Task 8: Add Arrow Serialization Methods to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs` (add `to_record_batch`, `compute_aggregates`, `region_populations`)

- [ ] **Step 1: Add Arrow imports and serialization methods to pool.rs**

Add these imports at the top of `chronicler-agents/src/pool.rs`:

```rust
use std::sync::Arc;
use std::collections::HashMap;

use arrow::array::{
    Float32Array, UInt8Array, UInt16Array, UInt32Array, ArrayRef,
};
use arrow::record_batch::RecordBatch;

use crate::ffi;
```

Add these methods to `impl AgentPool`:

```rust
    /// Arrow snapshot of alive agents only. Dead slots filtered out.
    pub fn to_record_batch(&self) -> Result<RecordBatch, arrow::error::ArrowError> {
        let mut ids = Vec::new();
        let mut regions = Vec::new();
        let mut origin_regions = Vec::new();
        let mut civ_affinities = Vec::new();
        let mut occupations = Vec::new();
        let mut loyalties = Vec::new();
        let mut satisfactions = Vec::new();
        let mut skills = Vec::new();
        let mut ages = Vec::new();
        let mut displacement_turns = Vec::new();

        for slot in 0..self.ids.len() {
            if self.is_alive(slot) {
                ids.push(self.ids[slot]);
                regions.push(self.regions[slot]);
                origin_regions.push(self.origin_regions[slot]);
                civ_affinities.push(self.civ_affinities[slot]);
                occupations.push(self.occupations[slot]);
                loyalties.push(self.loyalties[slot]);
                satisfactions.push(self.satisfactions[slot]);
                skills.push(self.skills[slot]);
                ages.push(self.ages[slot]);
                displacement_turns.push(self.displacement_turns[slot]);
            }
        }

        let schema = Arc::new(ffi::snapshot_schema());
        RecordBatch::try_new(schema, vec![
            Arc::new(UInt32Array::from(ids)) as ArrayRef,
            Arc::new(UInt16Array::from(regions)) as ArrayRef,
            Arc::new(UInt16Array::from(origin_regions)) as ArrayRef,
            Arc::new(UInt16Array::from(civ_affinities)) as ArrayRef,
            Arc::new(UInt8Array::from(occupations)) as ArrayRef,
            Arc::new(Float32Array::from(loyalties)) as ArrayRef,
            Arc::new(Float32Array::from(satisfactions)) as ArrayRef,
            Arc::new(Float32Array::from(skills)) as ArrayRef,
            Arc::new(UInt16Array::from(ages)) as ArrayRef,
            Arc::new(UInt16Array::from(displacement_turns)) as ArrayRef,
        ])
    }

    /// Per-civ aggregated stats.
    /// M25: population populated, military/economy/culture/stability zeroed.
    pub fn compute_aggregates(&self) -> Result<RecordBatch, arrow::error::ArrowError> {
        let mut civ_pop: HashMap<u16, u32> = HashMap::new();
        for slot in 0..self.ids.len() {
            if self.is_alive(slot) {
                *civ_pop.entry(self.civ_affinities[slot]).or_insert(0) += 1;
            }
        }

        let mut civ_ids: Vec<u16> = civ_pop.keys().copied().collect();
        civ_ids.sort();

        let populations: Vec<u32> = civ_ids.iter().map(|c| civ_pop[c]).collect();
        let zeroes: Vec<u32> = vec![0; civ_ids.len()];

        let schema = Arc::new(ffi::aggregates_schema());
        RecordBatch::try_new(schema, vec![
            Arc::new(UInt16Array::from(civ_ids)) as ArrayRef,
            Arc::new(UInt32Array::from(populations)) as ArrayRef,
            Arc::new(UInt32Array::from(zeroes.clone())) as ArrayRef, // military
            Arc::new(UInt32Array::from(zeroes.clone())) as ArrayRef, // economy
            Arc::new(UInt32Array::from(zeroes.clone())) as ArrayRef, // culture
            Arc::new(UInt32Array::from(zeroes)) as ArrayRef,         // stability
        ])
    }

    /// Per-region (region_id, alive_count) pairs.
    pub fn region_populations(&self, num_regions: u16) -> Result<RecordBatch, arrow::error::ArrowError> {
        let mut counts: Vec<u32> = vec![0; num_regions as usize];
        for slot in 0..self.ids.len() {
            if self.is_alive(slot) {
                let r = self.regions[slot] as usize;
                if r < counts.len() {
                    counts[r] += 1;
                }
            }
        }

        let region_ids: Vec<u16> = (0..num_regions).collect();
        let schema = Arc::new(ffi::region_populations_schema());
        RecordBatch::try_new(schema, vec![
            Arc::new(UInt16Array::from(region_ids)) as ArrayRef,
            Arc::new(UInt32Array::from(counts)) as ArrayRef,
        ])
    }
```

- [ ] **Step 2: Create a stub tick.rs so ffi.rs compiles**

Create `chronicler-agents/src/tick.rs`:

```rust
//! Demographic tick — age + die with rayon parallelism.
//! Full implementation in Task 11. This stub enables ffi.rs to compile.

use crate::pool::AgentPool;
use crate::region::RegionState;

pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: [u8; 32],
    turn: u32,
) {
    // Stub: will be implemented with rayon in Task 12
}
```

Add `mod tick;` to `lib.rs`:

```rust
mod agent;
mod ffi;
mod pool;
mod region;
mod tick;
```

- [ ] **Step 3: Verify compilation**

Run: `cd chronicler-agents && cargo check`
Expected: compiles. Warnings about unused variables in the stub are OK.

- [ ] **Step 4: Run existing pool tests**

Run: `cd chronicler-agents && cargo test`
Expected: all 5 pool tests still pass

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/pool.rs chronicler-agents/src/tick.rs chronicler-agents/src/lib.rs
git commit -m "feat(m25): add Arrow FFI layer with AgentSimulator, schemas, and serialization"
```

---

### Task 9: Arrow Round-Trip Test (Rust Side)

**Files:**
- Modify: `chronicler-agents/src/pool.rs` (add Arrow tests to `#[cfg(test)] mod tests`)

Note: These tests live in `pool.rs` module tests (not `tests/arrow_roundtrip.rs`) because they need access to `AgentPool` internals which are private to the crate.

- [ ] **Step 1: Add Arrow round-trip tests to pool.rs**

Add these tests to the existing `#[cfg(test)] mod tests` in `pool.rs`:

```rust
    #[test]
    fn test_to_record_batch_filters_dead() {
        let mut pool = AgentPool::new();
        pool.spawn(0, 1, Occupation::Farmer);
        pool.spawn(0, 1, Occupation::Soldier);
        pool.spawn(1, 2, Occupation::Merchant);

        pool.kill(1); // kill the soldier

        let batch = pool.to_record_batch().unwrap();
        assert_eq!(batch.num_rows(), 2); // only 2 alive
        assert_eq!(batch.num_columns(), 10); // snapshot schema has 10 columns

        // Verify schema field names
        let schema = batch.schema();
        let names: Vec<&str> = schema.fields().iter().map(|f| f.name().as_str()).collect();
        assert_eq!(names, vec![
            "id", "region", "origin_region", "civ_affinity", "occupation",
            "loyalty", "satisfaction", "skill", "age", "displacement_turn",
        ]);

        // Verify values — the alive agents are slot 0 (Farmer) and slot 2 (Merchant)
        let ids = batch.column(0).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
        assert_eq!(ids.value(0), 0); // first agent
        assert_eq!(ids.value(1), 2); // third agent (second was killed)
    }

    #[test]
    fn test_compute_aggregates_zeroes_non_population() {
        let mut pool = AgentPool::new();
        pool.spawn(0, 1, Occupation::Farmer);
        pool.spawn(0, 1, Occupation::Soldier);
        pool.spawn(1, 2, Occupation::Merchant);

        let batch = pool.compute_aggregates().unwrap();
        // 2 civs: civ 1 (2 agents) and civ 2 (1 agent)
        assert_eq!(batch.num_rows(), 2);

        let civ_ids = batch.column(0).as_any().downcast_ref::<arrow::array::UInt16Array>().unwrap();
        let pops = batch.column(1).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
        let military = batch.column(2).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();

        // Sorted by civ_id
        assert_eq!(civ_ids.value(0), 1);
        assert_eq!(pops.value(0), 2);
        assert_eq!(civ_ids.value(1), 2);
        assert_eq!(pops.value(1), 1);

        // military/economy/culture/stability all zeroed in M25
        for col_idx in 2..6 {
            let col = batch.column(col_idx).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
            for row in 0..batch.num_rows() {
                assert_eq!(col.value(row), 0, "column {col_idx} row {row} should be zero");
            }
        }
    }

    #[test]
    fn test_region_populations() {
        let mut pool = AgentPool::new();
        pool.spawn(0, 0, Occupation::Farmer);
        pool.spawn(0, 0, Occupation::Farmer);
        pool.spawn(1, 1, Occupation::Soldier);
        pool.spawn(2, 1, Occupation::Merchant);

        pool.kill(0); // kill one in region 0

        let batch = pool.region_populations(3).unwrap();
        assert_eq!(batch.num_rows(), 3);

        let counts = batch.column(1).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
        assert_eq!(counts.value(0), 1); // region 0: 1 alive (was 2, killed 1)
        assert_eq!(counts.value(1), 1); // region 1
        assert_eq!(counts.value(2), 1); // region 2
    }
```

- [ ] **Step 2: Run tests**

Run: `cd chronicler-agents && cargo test`
Expected: all 8 tests pass (5 original + 3 new Arrow tests)

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "test(m25): add Arrow round-trip tests for snapshot, aggregates, and region populations"
```

---

## Chunk 4: Python Round-Trip (FFI De-Risk Gate)

### Task 10: Build maturin and Write Python Round-Trip Test

**Files:**
- Create: `src/chronicler/agent_bridge.py`
- Create: `tests/test_agent_bridge.py`

This is the **de-risk gate**. If pyo3-arrow PyCapsule doesn't work with Python 3.12, we find out here before investing in arena/rayon.

- [ ] **Step 1: Write agent_bridge.py with build_region_batch and TERRAIN_MAP**

Create `src/chronicler/agent_bridge.py`:

```python
"""Bridge between Python WorldState and Rust AgentSimulator.

Translates Region ecology → Arrow RecordBatch for set_region_state(),
reads aggregates back, and manages the --agents flag lifecycle.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa

from chronicler_agents import AgentSimulator

if TYPE_CHECKING:
    from chronicler.models import Event, WorldState

# Terrain string → u8 mapping. Must match Terrain enum in region.rs.
# A round-trip test catches drift.
TERRAIN_MAP = {
    "plains": 0,
    "mountains": 1,
    "coast": 2,
    "forest": 3,
    "desert": 4,
    "tundra": 5,
}


def build_region_batch(world: WorldState) -> pa.RecordBatch:
    """Convert world.regions to Arrow RecordBatch for Rust consumption."""
    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "terrain": pa.array(
            [TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8(),
        ),
        "carrying_capacity": pa.array(
            [r.carrying_capacity for r in world.regions], type=pa.uint16(),
        ),
        "population": pa.array(
            [r.population for r in world.regions], type=pa.uint16(),
        ),
        "soil": pa.array(
            [r.ecology.soil for r in world.regions], type=pa.float32(),
        ),
        "water": pa.array(
            [r.ecology.water for r in world.regions], type=pa.float32(),
        ),
        "forest_cover": pa.array(
            [r.ecology.forest_cover for r in world.regions], type=pa.float32(),
        ),
    })


class AgentBridge:
    """Owns AgentSimulator lifecycle. Single entry point for simulation.py."""

    def __init__(self, world: WorldState, mode: str = "demographics-only"):
        self._sim = AgentSimulator(
            num_regions=len(world.regions), seed=world.seed,
        )
        self._mode = mode

    def tick(self, world: WorldState) -> list[Event]:
        """Run one agent tick. Called between Phase 9 and Phase 10."""
        self._sim.set_region_state(build_region_batch(world))
        _agent_events = self._sim.tick(world.turn)

        if self._mode == "demographics-only":
            self._apply_demographics_clamp(world)

        # M25: return empty list. M26+: convert agent_events to Event list.
        return []

    def _apply_demographics_clamp(self, world: WorldState) -> None:
        """Write agent-derived population back with capacity clamp.

        Uses get_region_populations() (per-region), not get_aggregates() (per-civ).
        Only writes to controlled regions — uncontrolled regions keep Python-side pop.
        Uses raw carrying_capacity * 1.2, not effective_capacity() — Rust-side
        ecological stress already accounts for soil/water in mortality.
        """
        region_pops = self._sim.get_region_populations()
        pop_map = dict(zip(
            region_pops.column("region_id").to_pylist(),
            region_pops.column("alive_count").to_pylist(),
        ))
        for i, region in enumerate(world.regions):
            if region.controller is not None:
                agent_pop = pop_map.get(i, 0)
                region.population = min(
                    agent_pop, int(region.carrying_capacity * 1.2),
                )

    def get_snapshot(self):
        """Delegate to AgentSimulator.get_snapshot()."""
        return self._sim.get_snapshot()

    def get_aggregates(self):
        """Delegate to AgentSimulator.get_aggregates()."""
        return self._sim.get_aggregates()
```

- [ ] **Step 2: Rebuild maturin**

Run: `cd chronicler-agents && maturin develop`
Expected: builds and installs successfully

- [ ] **Step 3: Write Python round-trip fidelity test**

Create `tests/test_agent_bridge.py`:

```python
"""Tests for the Rust agent bridge — round-trip, determinism, integration."""
import pyarrow as pa
import pytest

from chronicler_agents import AgentSimulator
from chronicler.agent_bridge import build_region_batch, TERRAIN_MAP, AgentBridge


def _make_region_batch(num_regions=3, capacity=60):
    """Create a minimal region state batch for testing."""
    return pa.record_batch({
        "region_id": pa.array(range(num_regions), type=pa.uint16()),
        "terrain": pa.array([0] * num_regions, type=pa.uint8()),  # all plains
        "carrying_capacity": pa.array([capacity] * num_regions, type=pa.uint16()),
        "population": pa.array([capacity] * num_regions, type=pa.uint16()),
        "soil": pa.array([0.8] * num_regions, type=pa.float32()),
        "water": pa.array([0.6] * num_regions, type=pa.float32()),
        "forest_cover": pa.array([0.3] * num_regions, type=pa.float32()),
    })


class TestPythonRoundTrip:
    """De-risk gate: prove Arrow data crosses the FFI boundary correctly."""

    def test_create_simulator(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        # Should not raise
        assert sim is not None

    def test_set_region_state_initializes_agents(self):
        sim = AgentSimulator(num_regions=3, seed=42)
        batch = _make_region_batch(num_regions=3, capacity=60)
        sim.set_region_state(batch)

        snap = sim.get_snapshot()
        # Should have agents (60 per region × 3 regions = 180)
        assert snap.num_rows == 180

    def test_snapshot_schema(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=10))

        snap = sim.get_snapshot()
        expected_names = [
            "id", "region", "origin_region", "civ_affinity", "occupation",
            "loyalty", "satisfaction", "skill", "age", "displacement_turn",
        ]
        assert snap.schema.names == expected_names

    # NOTE: test_tick_reduces_population, test_ages_increment, and
    # test_region_populations_matches_snapshot are in TestTickBehavior below.
    # They depend on the real tick implementation (Task 12) and will be
    # run after maturin rebuild in Task 12 Step 3.

    def test_aggregates_population_matches_and_others_zeroed(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=2, capacity=30))

        agg = sim.get_aggregates()
        total_pop = sum(agg.column("population").to_pylist())
        snap_count = sim.get_snapshot().num_rows
        assert total_pop == snap_count

        # military/economy/culture/stability all zeroed in M25
        for col_name in ["military", "economy", "culture", "stability"]:
            values = agg.column(col_name).to_pylist()
            assert all(v == 0 for v in values), f"{col_name} should be all zeroes"

    def test_tick_before_set_region_state_errors(self):
        sim = AgentSimulator(num_regions=2, seed=42)
        with pytest.raises(RuntimeError, match="set_region_state"):
            sim.tick(0)


class TestPythonDeterminism:
    """Two simulators with same seed must produce identical results."""

    def test_determinism_50_turns(self):
        sim_a = AgentSimulator(num_regions=3, seed=12345)
        sim_b = AgentSimulator(num_regions=3, seed=12345)

        region_batch = _make_region_batch(num_regions=3, capacity=50)

        sim_a.set_region_state(region_batch)
        sim_b.set_region_state(region_batch)

        for turn in range(50):
            sim_a.set_region_state(region_batch)
            sim_b.set_region_state(region_batch)
            sim_a.tick(turn)
            sim_b.tick(turn)

        snap_a = sim_a.get_snapshot()
        snap_b = sim_b.get_snapshot()

        assert snap_a.num_rows == snap_b.num_rows

        # Logical column-wise equality (not byte-level — Arrow padding can differ)
        for col_name in snap_a.schema.names:
            vals_a = snap_a.column(col_name).to_pylist()
            vals_b = snap_b.column(col_name).to_pylist()
            assert vals_a == vals_b, f"column {col_name} differs"


class TestTickBehavior:
    """Tests that depend on the real tick implementation.
    Written here in Task 10 but only runnable after Task 12 (tick.rs).
    Task 12 Step 3 rebuilds maturin and runs these.
    """

    def test_tick_reduces_population(self):
        """Tick 10 turns — some agents should die from mortality."""
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=60))

        initial_count = sim.get_snapshot().num_rows
        assert initial_count == 180

        # Tick 10 turns
        region_batch = _make_region_batch(num_regions=3, capacity=60)
        for turn in range(10):
            sim.set_region_state(region_batch)
            events = sim.tick(turn)
            # M25: events batch is empty (zero rows)
            assert events.num_rows == 0

        final_count = sim.get_snapshot().num_rows
        # Some agents should have died (mortality rates are 0.5%–5%)
        assert final_count < initial_count

    def test_ages_increment(self):
        """After ticking, agent ages should be > 0."""
        sim = AgentSimulator(num_regions=1, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=1, capacity=20))

        region_batch = _make_region_batch(num_regions=1, capacity=20)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn)

        snap = sim.get_snapshot()
        ages = snap.column("age").to_pylist()
        # All surviving agents should have aged 5 turns
        assert all(a == 5 for a in ages)

    def test_region_populations_matches_snapshot(self):
        """get_region_populations() count should match per-region snapshot count."""
        sim = AgentSimulator(num_regions=3, seed=42)
        sim.set_region_state(_make_region_batch(num_regions=3, capacity=40))

        region_batch = _make_region_batch(num_regions=3, capacity=40)
        for turn in range(5):
            sim.set_region_state(region_batch)
            sim.tick(turn)

        snap = sim.get_snapshot()
        region_pops = sim.get_region_populations()

        # Count per region from snapshot
        regions_col = snap.column("region").to_pylist()
        snap_counts = {}
        for r in regions_col:
            snap_counts[r] = snap_counts.get(r, 0) + 1

        # Compare with region_populations
        pop_region_ids = region_pops.column("region_id").to_pylist()
        pop_counts = region_pops.column("alive_count").to_pylist()
        for rid, count in zip(pop_region_ids, pop_counts):
            assert count == snap_counts.get(rid, 0), (
                f"region {rid}: region_populations={count}, snapshot={snap_counts.get(rid, 0)}"
            )
```

- [ ] **Step 4: Run the Python tests (FFI de-risk gate only)**

Run: `pytest tests/test_agent_bridge.py::TestPythonRoundTrip -v`
Expected: all FFI tests pass (constructor, set_region_state, snapshot schema, aggregates, tick-before-init error). **If they fail, debug now. Do not proceed until the FFI round-trip works.**

Note: `TestTickBehavior` and `TestPythonDeterminism` tests will fail at this stage because `tick.rs` is a stub. They become runnable after Task 12 rebuilds maturin with the real tick.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m25): add agent_bridge.py and Python round-trip fidelity tests"
```

---

## Chunk 5: Arena Allocation

### Task 11: Add Free-List Arena to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs`

- [ ] **Step 1: Write the arena stress test first**

Add this test to the `#[cfg(test)] mod tests` in `pool.rs`:

```rust
    #[test]
    fn test_arena_stress_spawn_kill_respawn() {
        let mut pool = AgentPool::new();

        // Spawn 1000 agents
        for _ in 0..1000 {
            pool.spawn(0, 0, Occupation::Farmer);
        }
        assert_eq!(pool.alive_count(), 1000);
        assert_eq!(pool.capacity(), 1000);

        // Kill 800 in a scattered pattern (every 5th agent, then fill)
        let mut kill_order: Vec<usize> = (0..1000).step_by(5).collect();
        // Add more until we have 800 kills
        for i in 0..1000 {
            if kill_order.len() >= 800 { break; }
            if !kill_order.contains(&i) {
                kill_order.push(i);
            }
        }
        kill_order.truncate(800);
        for &slot in &kill_order {
            pool.kill(slot);
        }
        assert_eq!(pool.alive_count(), 200);
        assert_eq!(pool.free_slot_count(), 800);

        // Respawn 600 — should reuse dead slots, no vec growth
        let capacity_before = pool.capacity();
        for _ in 0..600 {
            pool.spawn(0, 0, Occupation::Soldier);
        }
        assert_eq!(pool.alive_count(), 800); // 200 survivors + 600 new
        assert_eq!(pool.capacity(), capacity_before); // no growth!
        assert_eq!(pool.free_slot_count(), 200); // 800 - 600 = 200 remaining

        // Verify snapshot returns exactly 800 alive agents
        let batch = pool.to_record_batch().unwrap();
        assert_eq!(batch.num_rows(), 800);
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd chronicler-agents && cargo test test_arena_stress`
Expected: FAIL — `free_slot_count()` doesn't exist yet, and spawn doesn't check free-list.

- [ ] **Step 3: Add free_slots field and update spawn/kill**

Update `AgentPool` struct to add the `free_slots` field (it's in the struct definition from the spec but wasn't wired up):

In the `AgentPool::new()` constructor, `free_slots` is already there if you followed the spec struct. If not, add `free_slots: Vec<usize>` to the struct and `free_slots: Vec::new()` to `new()`.

Update `spawn` to check free-list first:

```rust
    pub fn spawn(&mut self, region: u16, civ: u16, occupation: Occupation) -> u32 {
        let id = self.next_id;
        self.next_id += 1;

        if let Some(slot) = self.free_slots.pop() {
            // Reuse dead slot
            self.ids[slot] = id;
            self.regions[slot] = region;
            self.origin_regions[slot] = region;
            self.civ_affinities[slot] = civ;
            self.occupations[slot] = occupation as u8;
            self.loyalties[slot] = 0.5;
            self.satisfactions[slot] = 0.5;
            self.skills[slot] = 0.3;
            self.ages[slot] = 0;
            self.displacement_turns[slot] = 0;
            self.alive[slot] = true;
        } else {
            // No free slots — grow vecs
            self.ids.push(id);
            self.regions.push(region);
            self.origin_regions.push(region);
            self.civ_affinities.push(civ);
            self.occupations.push(occupation as u8);
            self.loyalties.push(0.5);
            self.satisfactions.push(0.5);
            self.skills.push(0.3);
            self.ages.push(0);
            self.displacement_turns.push(0);
            self.alive.push(true);
        }

        self.count += 1;
        id
    }
```

Update `kill` to push to free-list:

```rust
    pub fn kill(&mut self, slot: usize) {
        debug_assert!(self.is_alive(slot), "killing already-dead slot {slot}");
        self.set_dead(slot);
        self.free_slots.push(slot);
        self.count -= 1;
    }
```

Add the `free_slot_count` accessor:

```rust
    /// Number of free slots in the arena.
    pub fn free_slot_count(&self) -> usize {
        self.free_slots.len()
    }
```

- [ ] **Step 4: Run all tests**

Run: `cd chronicler-agents && cargo test`
Expected: all tests pass including the new arena stress test

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "feat(m25): add free-list arena to AgentPool with stress test"
```

---

## Chunk 6: Rayon + RNG + Demographic Tick

### Task 12: Implement tick.rs — Rayon Parallel Tick with Demographics

**Files:**
- Modify: `chronicler-agents/src/tick.rs` (replace stub)

- [ ] **Step 1: Write the full tick.rs**

Replace the stub in `chronicler-agents/src/tick.rs`:

```rust
//! Demographic tick — age + die with rayon parallelism.
//!
//! M25 scope: agents age each turn and die based on age-bracket mortality
//! × ecological stress. No fertility, no decisions, no cross-region effects.
//! M26 replaces ecological_stress with a per-variable formula and adds
//! the decision model (satisfaction, loyalty drift, migration, rebellion).

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;

use crate::agent::{AGE_ADULT, AGE_ELDER, MORTALITY_ADULT, MORTALITY_ELDER, MORTALITY_YOUNG};
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Side effects collected during the parallel tick for sequential application.
/// M26 extends this with births, migrations, and events.
struct PendingEvents {
    deaths: Vec<usize>,
    aged: Vec<usize>,
}

impl PendingEvents {
    fn new() -> Self {
        Self {
            deaths: Vec::new(),
            aged: Vec::new(),
        }
    }
}

/// Run one agent tick across all regions in parallel.
///
/// Borrow note: `partition_by_region` returns owned data, so its borrow on
/// `pool` is released before the `par_iter` closure captures `pool` as `&AgentPool`.
/// These MUST be two separate let-bindings, not chained, to make lifetimes obvious.
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: [u8; 32],
    turn: u32,
) {
    // 1. Partition alive agents by region (slot indices only, no &mut borrows)
    let region_groups = pool.partition_by_region(regions.len() as u16);

    // 2. Parallel tick in a scoped block.
    //    pool_ref is a shared &AgentPool reborrow — the Send+Sync closure can
    //    capture it. The scope ends before the sequential apply step, so pool
    //    reverts to &mut AgentPool for kill()/increment_age().
    let pending: Vec<PendingEvents> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                // ChaCha8Rng with stream splitting — cryptographically independent streams.
                // Stream ID = region_id * 1000 + turn (readability convention, not a
                // correctness requirement — ChaCha streams are independent regardless).
                let mut rng = ChaCha8Rng::from_seed(master_seed);
                rng.set_stream(region_id as u64 * 1000 + turn as u64);
                tick_region_demographics(pool_ref, slots, &regions[region_id], &mut rng)
            })
            .collect()
    };

    // 3. Sequential apply — deterministic order (region index).
    //    pool is &mut AgentPool again (scoped reborrow ended above).
    for p in pending {
        for slot in &p.deaths {
            pool.kill(*slot);
        }
        for &slot in &p.aged {
            pool.increment_age(slot);
        }
    }
}

/// Tick a single region's agents. Read-only access to pool.
/// M25: age + die only. No fertility, no decisions.
fn tick_region_demographics(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    rng: &mut ChaCha8Rng,
) -> PendingEvents {
    let mut pending = PendingEvents::new();
    let eco_stress = ecological_stress(region);

    for &slot in slots {
        let age = pool.age(slot);
        let base_rate = match age {
            0..AGE_ADULT => MORTALITY_YOUNG,
            AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
            _ => MORTALITY_ELDER,
        };
        if rng.gen::<f32>() < base_rate * eco_stress {
            pending.deaths.push(slot);
        } else {
            pending.aged.push(slot);
        }
    }

    pending
}

/// Ecological stress multiplier on mortality.
/// Range: 1.0 (healthy) to 3.0 (total ecological collapse).
/// NOTE: M26 replaces this with a per-variable formula
/// (1.0 + max(0, 0.5-soil) + max(0, 0.5-water), range 1.0–2.0).
fn ecological_stress(region: &RegionState) -> f32 {
    let eco_health = (region.soil + region.water) / 2.0;
    1.0 + 2.0 * (1.0 - eco_health)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::region::RegionState;

    fn make_healthy_region(id: u16) -> RegionState {
        RegionState {
            region_id: id,
            terrain: 0,
            carrying_capacity: 60,
            population: 60,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
        }
    }

    #[test]
    fn test_ecological_stress_healthy() {
        let region = make_healthy_region(0);
        let stress = ecological_stress(&region);
        // soil=0.8, water=0.6 → eco_health=0.7 → stress = 1.0 + 2.0*0.3 = 1.6
        assert!((stress - 1.6).abs() < 0.01);
    }

    #[test]
    fn test_ecological_stress_collapsed() {
        let mut region = make_healthy_region(0);
        region.soil = 0.0;
        region.water = 0.0;
        let stress = ecological_stress(&region);
        // eco_health=0.0 → stress = 1.0 + 2.0*1.0 = 3.0
        assert!((stress - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_tick_agents_reduces_population() {
        let mut pool = AgentPool::new();
        let regions = vec![make_healthy_region(0)];

        // Spawn 100 agents in region 0
        for _ in 0..100 {
            pool.spawn(0, 0, Occupation::Farmer);
        }

        let mut seed = [0u8; 32];
        seed[0] = 42;

        tick_agents(&mut pool, &regions, seed, 0);

        // Some should have died, all survivors aged +1
        assert!(pool.alive_count() < 100);
        assert!(pool.alive_count() > 0); // not all dead with healthy ecology
    }

    #[test]
    fn test_tick_deterministic() {
        let regions = vec![make_healthy_region(0), make_healthy_region(1)];
        let mut seed = [0u8; 32];
        seed[0] = 99;

        // Run twice with identical setup
        let mut pool_a = AgentPool::new();
        let mut pool_b = AgentPool::new();
        for _ in 0..50 {
            pool_a.spawn(0, 0, Occupation::Farmer);
            pool_b.spawn(0, 0, Occupation::Farmer);
        }
        for _ in 0..50 {
            pool_a.spawn(1, 1, Occupation::Soldier);
            pool_b.spawn(1, 1, Occupation::Soldier);
        }

        for turn in 0..10 {
            tick_agents(&mut pool_a, &regions, seed, turn);
            tick_agents(&mut pool_b, &regions, seed, turn);
        }

        assert_eq!(pool_a.alive_count(), pool_b.alive_count());
        // Verify all agents match
        let batch_a = pool_a.to_record_batch().unwrap();
        let batch_b = pool_b.to_record_batch().unwrap();
        assert_eq!(batch_a.num_rows(), batch_b.num_rows());
    }
}
```

- [ ] **Step 2: Run all Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: all tests pass (pool tests + tick tests)

- [ ] **Step 3: Rebuild maturin and run ALL Python tests (including tick-dependent)**

Run:
```bash
cd chronicler-agents && maturin develop && cd .. && pytest tests/test_agent_bridge.py -v
```
Expected: ALL tests pass — including `TestTickBehavior` (tick_reduces_population, ages_increment, region_populations_matches_snapshot) and `TestPythonDeterminism` which were not runnable with the stub tick

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m25): implement rayon parallel demographic tick with ChaCha8Rng stream splitting"
```

---

### Task 13: Rust Determinism Tests with Varying Thread Counts

**Files:**
- Create: `chronicler-agents/tests/determinism.rs`

Since the pool and tick modules are private, this integration test needs public re-exports. Add to `lib.rs`:

- [ ] **Step 1: Add test-only public re-exports to lib.rs**

Add this at the bottom of `chronicler-agents/src/lib.rs`:

```rust
// Re-exports for integration tests. Not part of the Python API.
#[doc(hidden)]
pub use agent::Occupation;
#[doc(hidden)]
pub use pool::AgentPool;
#[doc(hidden)]
pub use region::RegionState;
#[doc(hidden)]
pub use tick::tick_agents;
```

- [ ] **Step 2: Write the determinism integration test**

Create `chronicler-agents/tests/determinism.rs`:

```rust
//! Determinism tests: same seed + same input → identical output.
//! Tests with varying thread counts to prove rayon collect-order determinism.

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};

fn make_test_regions() -> Vec<RegionState> {
    (0..5)
        .map(|i| RegionState {
            region_id: i,
            terrain: 0,
            carrying_capacity: 60,
            population: 60,
            soil: 0.5 + (i as f32) * 0.1, // vary ecology per region
            water: 0.4 + (i as f32) * 0.05,
            forest_cover: 0.3,
        })
        .collect()
}

fn make_test_pool(regions: &[RegionState]) -> AgentPool {
    let mut pool = AgentPool::new();
    for region in regions {
        for _ in 0..region.carrying_capacity {
            pool.spawn(region.region_id, region.region_id, Occupation::Farmer);
        }
    }
    pool
}

fn run_simulation(seed: [u8; 32], turns: u32) -> (usize, Vec<u16>) {
    let regions = make_test_regions();
    let mut pool = make_test_pool(&regions);

    for turn in 0..turns {
        tick_agents(&mut pool, &regions, seed, turn);
    }

    let batch = pool.to_record_batch().unwrap();
    let ages_col = batch
        .column(8) // "age" is column index 8
        .as_any()
        .downcast_ref::<arrow::array::UInt16Array>()
        .unwrap();
    let ages: Vec<u16> = (0..ages_col.len()).map(|i| ages_col.value(i)).collect();

    (pool.alive_count(), ages)
}

#[test]
fn test_determinism_same_seed_same_result() {
    let mut seed = [0u8; 32];
    seed[0] = 42;

    let (count_a, ages_a) = run_simulation(seed, 20);
    let (count_b, ages_b) = run_simulation(seed, 20);

    assert_eq!(count_a, count_b);
    assert_eq!(ages_a, ages_b);
}

#[test]
fn test_determinism_different_seed_different_result() {
    let mut seed_a = [0u8; 32];
    seed_a[0] = 42;
    let mut seed_b = [0u8; 32];
    seed_b[0] = 99;

    let (count_a, _) = run_simulation(seed_a, 20);
    let (count_b, _) = run_simulation(seed_b, 20);

    // Different seeds should (with very high probability) produce different results
    assert_ne!(count_a, count_b);
}

#[test]
fn test_determinism_across_thread_counts() {
    // Run with 1, 4, and 16 threads — all must produce identical results
    let mut seed = [0u8; 32];
    seed[0] = 77;

    let mut results = Vec::new();
    for threads in [1, 4, 16] {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        let result = pool.install(|| run_simulation(seed, 30));
        results.push(result);
    }

    // All thread counts must produce identical results
    for i in 1..results.len() {
        assert_eq!(
            results[0].0, results[i].0,
            "alive count differs between thread counts"
        );
        assert_eq!(
            results[0].1, results[i].1,
            "ages differ between thread counts"
        );
    }
}
```

- [ ] **Step 3: Run determinism tests**

Run: `cd chronicler-agents && cargo test --test determinism`
Expected: all 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/determinism.rs chronicler-agents/src/lib.rs
git commit -m "test(m25): add determinism integration tests with varying rayon thread counts"
```

---

## Chunk 7: Benchmark + Python Integration + Final Tests

### Task 14: Criterion Benchmark

**Files:**
- Create: `chronicler-agents/benches/tick_bench.rs`

- [ ] **Step 1: Create benchmark directory and file**

```bash
mkdir -p chronicler-agents/benches
```

Create `chronicler-agents/benches/tick_bench.rs`:

```rust
//! Benchmark: 6K agents × 1 tick (age + die only).
//! Target: < 0.5ms on 9950X.

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};

fn setup_6k_pool() -> (AgentPool, Vec<RegionState>) {
    let regions: Vec<RegionState> = (0..24u16)
        .map(|i| RegionState {
            region_id: i,
            terrain: 0,
            carrying_capacity: 250,  // 250 × 24 = 6000
            population: 250,
            soil: 0.7,
            water: 0.5,
            forest_cover: 0.3,
        })
        .collect();

    let mut pool = AgentPool::new();
    for region in &regions {
        for _ in 0..250 {
            pool.spawn(region.region_id, region.region_id, Occupation::Farmer);
        }
    }

    (pool, regions)
}

fn bench_tick_6k(c: &mut Criterion) {
    let mut seed = [0u8; 32];
    seed[0] = 42;

    c.bench_function("tick_6k_agents", |b| {
        // iter_batched: fresh pool each iteration so we always benchmark 6K agents.
        // Without this, the pool drains across iterations as agents die,
        // producing increasingly fast (but unrepresentative) timings.
        b.iter_batched(
            setup_6k_pool,
            |(mut pool, regions)| {
                tick_agents(black_box(&mut pool), black_box(&regions), seed, 0);
            },
            criterion::BatchSize::SmallInput,
        )
    });
}

criterion_group!(benches, bench_tick_6k);
criterion_main!(benches);
```

- [ ] **Step 2: Run benchmark**

Run: `cd chronicler-agents && cargo bench`
Expected: reports time per iteration. Target: < 0.5ms (500μs).

Note: on Windows with system allocator, numbers may be higher. Run on WSL/Linux with jemalloc for representative numbers.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/benches/tick_bench.rs
git commit -m "bench(m25): add criterion benchmark for 6K agents × 1 tick"
```

---

### Task 15: Integrate AgentBridge into simulation.py

**Files:**
- Modify: `src/chronicler/simulation.py:891-970` (run_turn function)

- [ ] **Step 1: Add agent_bridge parameter to run_turn**

In `src/chronicler/simulation.py`, modify the `run_turn` function signature (line 891):

Change:
```python
def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
) -> str:
```

To:
```python
def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
    agent_bridge: object | None = None,
) -> str:
```

(`object | None` instead of `AgentBridge | None` to avoid importing agent_bridge at module level — the import is only needed when agents are enabled.)

- [ ] **Step 2: Insert agent tick between Phase 9 and Phase 10**

In `run_turn`, after the terrain succession block (after `turn_events.extend(tick_terrain_succession(world))`), and before `# Phase 10: Consequences`, add:

```python
    # ── Rust agent tick (between Phase 9 and Phase 10) ──
    if agent_bridge is not None:
        turn_events.extend(agent_bridge.tick(world))
```

- [ ] **Step 3: Run existing simulation tests to verify no regression**

Run: `pytest tests/test_simulation.py -v`
Expected: all existing tests pass. The new parameter defaults to `None`, so existing callers are unaffected.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m25): add optional agent_bridge to run_turn between Phase 9 and Phase 10"
```

---

### Task 16: Demographics-Only Integration Test

**Files:**
- Modify: `tests/test_agent_bridge.py` (add integration test class)

- [ ] **Step 1: Add demographics-only integration test**

Add this class to `tests/test_agent_bridge.py`:

```python
class TestDemographicsOnlyIntegration:
    """Integration test: AgentBridge with a real WorldState from world_gen."""

    def test_demographics_only_20_turns(self, sample_world):
        """Run 20 turns with demographics-only mode."""
        bridge = AgentBridge(sample_world, mode="demographics-only")

        initial_pops = {r.name: r.population for r in sample_world.regions
                        if r.controller is not None}

        for turn in range(20):
            sample_world.turn = turn
            events = bridge.tick(sample_world)
            # M25: no events
            assert events == []

            # Population per region never exceeds cap × 1.2
            for region in sample_world.regions:
                if region.controller is not None:
                    assert region.population <= int(region.carrying_capacity * 1.2), (
                        f"region {region.name}: pop {region.population} > cap*1.2 {int(region.carrying_capacity * 1.2)}"
                    )

        # Population should decrease over time (age + die only, no fertility)
        final_pops = {r.name: r.population for r in sample_world.regions
                      if r.controller is not None}
        total_initial = sum(initial_pops.values())
        total_final = sum(final_pops.values())
        assert total_final < total_initial, (
            f"population should decrease: initial={total_initial}, final={total_final}"
        )
```

This test uses the `sample_world` fixture from `conftest.py` which provides a real `WorldState` with 5 regions, 2 civilizations, and all terrain types.

- [ ] **Step 2: Run the full test suite**

Run: `pytest tests/test_agent_bridge.py -v`
Expected: all tests pass including the new integration test.

- [ ] **Step 3: Also run the full project test suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_bridge.py
git commit -m "test(m25): add demographics-only integration test with real WorldState"
```

---

### Task 17: Final Verification and Cleanup

**Files:**
- No new files — verification pass

- [ ] **Step 1: Run full Rust test suite**

Run: `cd chronicler-agents && cargo test`
Expected: all tests pass

- [ ] **Step 2: Run full Python test suite**

Run: `pytest tests/ -v`
Expected: all tests pass (existing + new agent bridge tests)

- [ ] **Step 3: Run benchmark**

Run: `cd chronicler-agents && cargo bench`
Expected: tick_6k_agents < 0.5ms

- [ ] **Step 4: Verify import works cleanly**

Run: `python -c "from chronicler.agent_bridge import AgentBridge; print('AgentBridge import OK')"`
Expected: prints `AgentBridge import OK`

- [ ] **Step 5: Final commit (if any cleanup was needed)**

If any fixes were needed, commit them. Otherwise, M25 is complete.

```bash
git log --oneline -15
```

Expected: clean sequence of M25 commits following the implementation ordering.
