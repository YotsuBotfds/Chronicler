# M25: Rust Core + Arrow Bridge — Design Spec

**Date:** 2026-03-15
**Status:** Draft
**Prerequisites:** Phase 4 complete (M19–M24), M19b tuning converged, Python 3.12 venv
**Estimated size:** ~800 lines Rust, ~200 lines Python
**Phase:** 5 (Agent-Based Population Model) — first milestone

## Overview

Establish the `chronicler-agents` Rust crate with PyO3 bindings, define the agent data model as struct-of-arrays with arena allocation, build the Arrow FFI data exchange layer via pyo3-arrow, prove rayon parallelism with deterministic scheduling, and implement a minimal demographic tick (age + die only). This is the foundation that M26–M30 build on.

M25 does not add agent decision-making, satisfaction updates, loyalty drift, migration, fertility, or interaction with existing Python simulation systems. Agents age and die via an ecological-stress-weighted mortality model. The `--agents=demographics-only` mode clamps population to `carrying_capacity × 1.2` and is the only mode available until M26.

### Design Principles

1. **Prove the FFI boundary early.** The highest-risk integration point is Arrow data crossing Rust↔Python via PyCapsule. The implementation ordering hits this in step 4 of 9, before investing in arena or rayon.
2. **Schemas stable from day one.** All Arrow schemas (snapshot, aggregates, region state, events) are defined in M25 with their full column sets. Columns that aren't populated until M26+ are zeroed, not absent.
3. **No fertility without feedback.** Age + die only. Fertility without satisfaction feedback is a random walk that muddies the benchmark. Fertility arrives in M26 when satisfaction is real.
4. **Accessor-mediated alive field.** `is_alive(slot)` / `set_dead(slot)` methods, not raw indexing. Enables future BitVec swap (M29) as a one-file change.

## Crate Structure & Build Tooling

```
chronicler-agents/
├── Cargo.toml          # pyo3, pyo3-arrow, rand_chacha, rayon, tikv-jemallocator, criterion
├── pyproject.toml      # maturin build backend, requires-python = ">=3.12,<3.13"
├── src/
│   ├── lib.rs          # PyO3 module entry, jemalloc global allocator (cfg-gated)
│   ├── agent.rs        # Occupation enum, field definitions and constants (no AoS struct)
│   ├── pool.rs         # AgentPool (SoA vecs + free-list arena)
│   ├── ffi.rs          # PyO3 AgentSimulator class, Arrow FFI methods, centralized schemas
│   ├── tick.rs         # Demographic tick (age + die), rayon region partitioning
│   └── region.rs       # RegionState struct (Rust-side mirror of Python region ecology)
├── benches/
│   └── tick_bench.rs   # Criterion benchmark: 6K agents × 1 tick
└── tests/
    ├── determinism.rs  # Same seed × same input → identical output, varying thread counts
    └── arrow_roundtrip.rs  # Pool → RecordBatch → verify schema and values
```

Python side:
```
src/chronicler/
└── agent_bridge.py     # AgentBridge wrapper class, WorldState ↔ Arrow translation
```

### Build Flow

`chronicler-agents/` is a standalone Cargo workspace with its own `pyproject.toml`. No changes to the root `pyproject.toml`. `maturin develop` in the Python 3.12 venv installs `chronicler_agents` as a wheel. The main `chronicler` package imports it as an optional dependency, guarded by the `--agents` flag.

The `chronicler-agents/pyproject.toml` pins `requires-python = ">=3.12,<3.13"` to catch ABI mismatches early. PyO3 compiles against a specific Python ABI; the `maturin develop` call must happen inside the 3.12 venv. The main Chronicler package stays version-flexible.

### Cargo.toml

```toml
[dependencies]
pyo3 = { version = "0.23", features = ["extension-module"] }
pyo3-arrow = "0.5"
rand = "0.8"
rand_chacha = "0.3"
rayon = "1.10"

[target.'cfg(not(target_os = "windows"))'.dependencies]
tikv-jemallocator = "0.6"

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }

[profile.release]
codegen-units = 1
lto = true
opt-level = 3
```

### jemalloc

cfg-gated to non-Windows via `#[cfg(not(target_os = "windows"))]` in `lib.rs`. Windows development uses the system allocator. Performance benchmarks run on WSL or Linux where jemalloc is active.

## Data Structures

### `agent.rs` — Agent Field Definitions and Constants

Module doc: "Agent field definitions and constants — no AoS Agent struct at runtime. Fields are stored as struct-of-arrays in `AgentPool`."

```rust
/// Occupation types. repr(u8) for Arrow serialization and SoA storage.
#[repr(u8)]
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Occupation {
    Farmer = 0,
    Soldier = 1,
    Merchant = 2,
    Scholar = 3,
    Priest = 4,
}

// Mortality base rates by age bracket (per tick)
pub const MORTALITY_YOUNG: f32 = 0.005;   // age 0–19
pub const MORTALITY_ADULT: f32 = 0.01;    // age 20–59
pub const MORTALITY_ELDER: f32 = 0.05;    // age 60+

pub const AGE_ADULT: u16 = 20;
pub const AGE_ELDER: u16 = 60;
```

### `region.rs` — RegionState

Rust-side mirror of Python `Region` ecology fields. `terrain` is stored as `u8` with a matching `Terrain` enum — not used in M25's demographic tick but present in the Arrow schema from day one so M26 doesn't require a schema migration.

```rust
#[repr(u8)]
#[derive(Clone, Copy)]
pub enum Terrain {
    Plains = 0,
    Mountains = 1,
    Coast = 2,
    Forest = 3,
    Desert = 4,
    Tundra = 5,
}

pub struct RegionState {
    pub region_id: u16,
    pub terrain: u8,
    pub carrying_capacity: u16,
    pub population: u16,
    pub soil: f32,
    pub water: f32,
    pub forest_cover: f32,
}
```

### `pool.rs` — AgentPool (SoA + Arena)

```rust
pub struct AgentPool {
    // SoA arrays — each vec indexed by slot
    ids: Vec<u32>,
    regions: Vec<u16>,
    origin_regions: Vec<u16>,
    civ_affinities: Vec<u16>,
    occupations: Vec<u8>,       // Occupation as u8
    loyalties: Vec<f32>,
    satisfactions: Vec<f32>,
    skills: Vec<f32>,
    ages: Vec<u16>,
    displacement_turns: Vec<u16>,
    alive: Vec<bool>,           // 1 byte per agent; accessed via methods only

    // Bookkeeping
    count: usize,                // alive agent count
    next_id: u32,                // monotonic ID counter
    free_slots: Vec<usize>,      // arena: dead slots available for reuse
}
```

**Key operations:**

- `spawn(region, civ, occupation) -> u32` — claims a free slot from `free_slots` (or pushes to grow vecs) and returns the new agent's monotonic ID
- `kill(slot: usize)` — calls `set_dead(slot)`, pushes slot to `free_slots`, decrements `count`
- `is_alive(slot) -> bool` / `set_dead(slot)` — accessor methods for the `alive` field. All code paths use these, never raw `alive[slot]` indexing. This enables a future BitVec swap (M29 profiling) as a one-file change in `pool.rs`
- `increment_age(slot)` — `ages[slot] += 1`
- `partition_by_region() -> Vec<Vec<usize>>` — returns slot indices of alive agents grouped by region, sorted by region index. Returns only indices, not mutable references into the SoA vecs — avoids borrow checker issues with parallel access
- `to_record_batch() -> RecordBatch` — Arrow snapshot of alive agents only (dead slots filtered out)
- `compute_aggregates(regions: &[RegionState]) -> RecordBatch` — per-civ aggregated stats. All five columns present: `population` populated, `military`/`economy`/`culture`/`stability` zeroed in M25
- `region_populations() -> RecordBatch` — per-region `(region_id: u16, alive_count: u32)` pairs for the demographics-only clamp

**Arena behavior:** `spawn` always checks `free_slots` first. Dead slot reuse means no vec reallocation during steady-state simulation. Vecs only grow if all free slots are exhausted (net population increase).

## Arrow FFI & PyO3 Bindings

### `ffi.rs` — AgentSimulator

```rust
#[pyclass]
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    master_seed: [u8; 32],
    turn: u32,
    initialized: bool,           // true after first set_region_state()
}

#[pymethods]
impl AgentSimulator {
    #[new]
    fn new(num_regions: u16, seed: u64) -> Self { ... }

    fn set_region_state(&mut self, batch: PyRecordBatch) -> PyResult<()> { ... }
    fn tick(&mut self, turn: u32) -> PyResult<PyRecordBatch> { ... }
    fn get_snapshot(&self) -> PyResult<PyRecordBatch> { ... }
    fn get_aggregates(&self) -> PyResult<PyRecordBatch> { ... }
    fn get_region_populations(&self) -> PyResult<PyRecordBatch> { ... }
}
```

**Constructor:** `new(num_regions, seed)` takes only region count and seed. No region data in the constructor. Seed conversion: bytes 0–7 = `seed` as little-endian u64, bytes 8–31 = zero. Simple, documented, deterministically verifiable.

**Initialization:** First call to `set_region_state()` initializes `RegionState` objects and spawns agents proportional to carrying capacity. Subsequent calls update ecology state. `tick()` errors if `set_region_state()` was never called (`initialized == false`).

**Arrow method convention:** All methods use **owned** `PyRecordBatch` types (not references). Owned types trigger pyo3-arrow's zero-copy PyCapsule extraction. References silently fall back to IPC serialization.

### Arrow Schemas

Defined in a centralized location (`fn snapshot_schema()`, `fn aggregates_schema()`, `fn events_schema()`, `fn region_state_schema()` — either in `ffi.rs` or a dedicated `schemas.rs`). Referenced everywhere, defined once.

**Snapshot schema** (`get_snapshot`):

| Column | Arrow Type | Notes |
|--------|-----------|-------|
| `id` | `UInt32` | monotonic |
| `region` | `UInt16` | |
| `origin_region` | `UInt16` | |
| `civ_affinity` | `UInt16` | |
| `occupation` | `UInt8` | Occupation enum as u8 |
| `loyalty` | `Float32` | |
| `satisfaction` | `Float32` | |
| `skill` | `Float32` | |
| `age` | `UInt16` | |
| `displacement_turn` | `UInt16` | |

Only alive agents. Dead slots filtered during `to_record_batch()`.

**Aggregates schema** (`get_aggregates`):

| Column | Arrow Type | M25 | M26+ |
|--------|-----------|-----|------|
| `civ_id` | `UInt16` | populated | populated |
| `population` | `UInt32` | populated | populated |
| `military` | `UInt32` | **zero** | from occupation/skill |
| `economy` | `UInt32` | **zero** | from occupation/skill |
| `culture` | `UInt32` | **zero** | from occupation/skill |
| `stability` | `UInt32` | **zero** | from satisfaction |

**Region populations schema** (`get_region_populations`):

| Column | Arrow Type |
|--------|-----------|
| `region_id` | `UInt16` |
| `alive_count` | `UInt32` |

**Events schema** (`tick` return):

Defined with full column set in M25. Returns zero rows until M26 populates rebellion/migration/death events.

**Region state schema** (`set_region_state` input):

| Column | Arrow Type | Notes |
|--------|-----------|-------|
| `region_id` | `UInt16` | |
| `terrain` | `UInt8` | enum-mapped from Python string |
| `carrying_capacity` | `UInt16` | |
| `population` | `UInt16` | current Python-side pop |
| `soil` | `Float32` | |
| `water` | `Float32` | |
| `forest_cover` | `Float32` | |

## Rayon + RNG + Demographic Tick

### `tick.rs`

```rust
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: [u8; 32],
    turn: u32,
) {
    // 1. Partition alive agents by region (slot indices only, no &mut borrows)
    let region_groups: Vec<Vec<usize>> = pool.partition_by_region();

    // 2. Parallel tick — shared &AgentPool reference, writes to PendingEvents only
    let pending: Vec<PendingEvents> = region_groups
        .par_iter()
        .enumerate()
        .map(|(region_id, slots)| {
            let mut rng = ChaCha8Rng::from_seed(master_seed);
            rng.set_stream(region_id as u64 * 1000 + turn as u64);
            tick_region_demographics(pool, slots, &regions[region_id], &mut rng)
        })
        .collect();

    // 3. Sequential apply — deterministic order (region index)
    for p in pending {
        for slot in &p.deaths {
            pool.kill(*slot);
        }
        for &slot in &p.aged {
            pool.increment_age(slot);
        }
    }
}
```

### Determinism Guarantee

Regions processed in index order. `par_iter().map().collect()` preserves result order — rayon's work-stealing reorders execution but the collected `Vec<PendingEvents>` is always in region-index order. The sequential apply step processes pending events in that fixed order.

### RNG Stream Splitting

ChaCha8Rng with native `set_stream()` — cryptographically independent streams by construction. No XOR-based seed derivation.

- Stream ID = `region_id * 1000 + turn`
- The `* 1000` gives headroom for up to 1000 turns before stream IDs from different regions could theoretically alias. With 24 regions and 500 turns, the actual max stream ID is ~24,500 — well within ChaCha's 64-bit stream space.
- Seed: bytes 0–7 = u64 seed as little-endian, bytes 8–31 = zero. Documented in constructor.

### Demographic Tick (M25 Scope: Age + Die Only)

```rust
fn tick_region_demographics(
    pool: &AgentPool,           // shared reference — read only
    slots: &[usize],
    region: &RegionState,
    rng: &mut ChaCha8Rng,
) -> PendingEvents {
    let mut pending = PendingEvents::new();
    let eco_stress = ecological_stress(region);

    for &slot in slots {
        // Mortality: base rate by age bracket × ecological stress multiplier
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
```

**No fertility in M25.** Fertility without satisfaction feedback is a random walk. Population bounds are enforced by the demographics-only clamp on the Python side. Fertility arrives in M26 when the satisfaction model provides real feedback.

### Ecological Stress

```rust
fn ecological_stress(region: &RegionState) -> f32 {
    let eco_health = (region.soil + region.water) / 2.0;  // 0.0–1.0
    1.0 + 2.0 * (1.0 - eco_health)
    // Range: 1.0 (healthy ecology) to 3.0 (total ecological collapse)
}
```

### What M25's Tick Does NOT Do

- No satisfaction updates (static at initialization value)
- No loyalty drift
- No migration, rebellion, occupation switching
- No cross-region effects
- No event emission (events RecordBatch returned with zero rows)
- No fertility (deferred to M26)

## Python Integration

### `agent_bridge.py` — AgentBridge Wrapper

`AgentBridge` owns the `AgentSimulator`, the agent mode, and the full tick lifecycle. `simulation.py` gets one optional parameter that stays stable M25–M30.

```python
class AgentBridge:
    """Owns AgentSimulator lifecycle. Single entry point for simulation.py."""

    def __init__(self, world: WorldState, mode: str = "demographics-only"):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
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
        region_pops = self._sim.get_region_populations()
        for i, region in enumerate(world.regions):
            if region.controller is not None:
                agent_pop = ...  # extract from region_pops by region_id
                region.population = min(agent_pop, int(region.carrying_capacity * 1.2))

    def get_snapshot(self): return self._sim.get_snapshot()
    def get_aggregates(self): return self._sim.get_aggregates()
```

### Terrain Mapping (Python → Rust)

Single source of truth on the Python side. A round-trip test catches drift with the Rust `Terrain` enum.

```python
TERRAIN_MAP = {
    "plains": 0, "mountains": 1, "coast": 2,
    "forest": 3, "desert": 4, "tundra": 5,
}
```

### `build_region_batch`

```python
def build_region_batch(world: WorldState) -> pa.RecordBatch:
    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8()),
        "carrying_capacity": pa.array([r.carrying_capacity for r in world.regions], type=pa.uint16()),
        "population": pa.array([r.population for r in world.regions], type=pa.uint16()),
        "soil": pa.array([r.ecology.soil for r in world.regions], type=pa.float32()),
        "water": pa.array([r.ecology.water for r in world.regions], type=pa.float32()),
        "forest_cover": pa.array([r.ecology.forest_cover for r in world.regions], type=pa.float32()),
    })
```

### Integration Point in `simulation.py`

```python
def run_turn(
    world: WorldState,
    action_selector: ActionSelector,
    narrator: Narrator,
    seed: int = 0,
    agent_bridge: AgentBridge | None = None,  # stable M25–M30
) -> str:
    ...
    # Phase 9: Ecology
    turn_events.extend(tick_ecology(world, climate_phase))
    turn_events.extend(tick_terrain_succession(world))

    # ── Rust agent tick (between Phase 9 and Phase 10) ──
    if agent_bridge is not None:
        turn_events.extend(agent_bridge.tick(world))

    # Phase 10: Consequences
    turn_events.extend(phase_consequences(world))
```

`agent_bridge` defaults to `None` — zero impact on existing callers. The `AgentBridge` is constructed once at simulation start and passed through.

## Testing Strategy

### 1. Rust Determinism Tests (`tests/determinism.rs`)

- Same `seed` + same region state + same turn → identical pool state after tick
- Run twice, compare every SoA vec element
- Vary thread count (1, 4, 16 via `RAYON_NUM_THREADS`) — all produce identical results. Proves rayon collect-order determinism.

### 2. Pool Unit Tests (`pool.rs` module tests)

- `spawn` into empty pool → correct field values, ID monotonically increments
- `kill` → `is_alive(slot)` returns false, slot in `free_slots`, `count` decremented
- `spawn` after `kill` → reuses dead slot, no vec growth
- `partition_by_region` → slot indices grouped correctly, sorted by region index
- Accessors: `is_alive`, `set_dead`, `increment_age` behave correctly

### 3. Arena Stress Test (`pool.rs` or `tests/`)

Simulates high-mortality scenario:
- Spawn 1000 agents, kill 800 in random order, spawn 600 new ones
- Verify: 600 of the 800 free slots reused, zero vec growth
- Verify: `to_record_batch()` returns exactly 800 alive agents (200 survivors + 600 new) with correct field values
- Catches free-list off-by-one errors that only manifest under heavy churn (famine/war scenarios)

### 4. Arrow Round-Trip Test (`tests/arrow_roundtrip.rs`)

- Construct pool with known agents, call `to_record_batch()`
- Verify Arrow schema: correct column names and types
- Verify row count = alive agent count (dead slots excluded)
- Verify column values match pool state

### 5. Python Round-Trip Fidelity Test (`tests/test_agent_bridge.py`)

The highest-value test in M25 — catches PyCapsule/ABI/pyo3-arrow bugs that unit tests on either side alone miss:

- Create `AgentSimulator` from Python via `import chronicler_agents`
- Call `set_region_state()` with a known Arrow RecordBatch (initializes regions + spawns agents)
- Tick 10 turns
- Read snapshot via `get_snapshot()` → convert to polars/pandas DataFrame
- Assert: agent count decreased (some died from mortality), ages incremented, no births
- Assert: `get_region_populations()` matches per-region count from snapshot
- Assert: `get_aggregates()` population column matches snapshot total, other columns zeroed

### 6. Python Determinism Test (`tests/test_agent_bridge.py`)

- Create two `AgentSimulator` instances with the same seed
- Tick both 50 turns with identical region state each turn
- Compare snapshots via **logical column-wise equality** (not byte-level — Arrow in-memory padding can differ between allocations without affecting values)

### 7. Demographics-Only Integration Test (`tests/test_agent_bridge.py`)

- Create `AgentBridge` with a real `WorldState` from `world_gen`
- Run 20 turns through `bridge.tick(world)`
- Assert: population per region never exceeds `carrying_capacity × 1.2`
- Assert: population decreases over time (age + die only, no fertility)
- Assert: no events returned (empty list each turn)

### Benchmark (Deliverable, Not Test)

- 6,000 agents across 24 regions, 1 tick (age + die only)
- Target: < 0.5ms on 9950X
- Via `cargo bench` with criterion
- Run on WSL/Linux with jemalloc active for representative numbers

## Implementation Ordering

The steps below are sequenced as a risk-mitigation strategy. The FFI boundary (step 4) is the highest-risk integration point — if pyo3-arrow has PyCapsule gotchas with Python 3.12, you find out before investing in arena management or rayon complexity.

1. **Crate scaffolding + maturin build** — `Cargo.toml`, `pyproject.toml`, `lib.rs` with jemalloc cfg-gate, empty PyO3 module. Prove `maturin develop` works in the 3.12 venv and `import chronicler_agents` succeeds from Python.

2. **Minimal AgentPool SoA** — `agent.rs` (Occupation enum, constants), `pool.rs` (SoA vecs, spawn/kill, accessors). No arena free-list yet — just plain Vec push. Rust unit tests for spawn/kill.

3. **Arrow FFI** — `ffi.rs` with `AgentSimulator` class, `region.rs` with `RegionState`. Implement `set_region_state()`, `get_snapshot()`, `get_region_populations()`, `get_aggregates()`. Centralized schema definitions. Rust-side `arrow_roundtrip` test.

4. **Python round-trip test** — `agent_bridge.py` with `build_region_batch()` and `TERRAIN_MAP`. `test_agent_bridge.py` with the round-trip fidelity test: create simulator from Python, set region state, read snapshot back as DataFrame, verify values. **This is the de-risk gate. If it fails, debug before proceeding.**

5. **Arena allocation** — add `free_slots` to `AgentPool`. `spawn` checks free-list first. `kill` pushes to free-list. Arena stress test (spawn 1000, kill 800, respawn 600). `AgentPool`'s public API (`partition_by_region`, `to_record_batch`) doesn't change — the free-list is internal bookkeeping.

6. **Rayon + ChaCha8Rng** — `tick.rs` with `tick_agents()`, region partitioning via `partition_by_region()` returning `Vec<Vec<usize>>`, parallel tick with shared `&AgentPool`, sequential apply. Determinism test with varying thread counts.

7. **Demographic tick** — `tick_region_demographics()` with age-bracket mortality × ecological stress. `PendingEvents` with deaths and aged lists. No fertility.

8. **Determinism + benchmark** — Full determinism test from Python (50 turns, two instances, logical equality). Criterion benchmark: 6K agents × 1 tick < 0.5ms.

9. **AgentBridge + integration** — `AgentBridge` wrapper class, `_apply_demographics_clamp` using `get_region_populations()`, `run_turn` signature with optional `agent_bridge` parameter. Demographics-only integration test with real `WorldState`.

## What This Milestone Does NOT Do

- No agent decision-making (no satisfaction updates, loyalty drift, migration, rebellion, occupation switching)
- No fertility (deferred to M26 when satisfaction feedback exists)
- No interaction with existing Python simulation systems beyond population clamp
- No narrative integration
- No oracle comparison
- No event emission (events schema defined, zero rows returned)

## What M26 Will Build On

- Agent decision model (rebel → migrate → switch occupation → loyalty drift)
- Satisfaction formula (ecology, faction dominance, occupation demand)
- Fertility (satisfaction-gated, ecology-scaled)
- Shadow mode: agent tick runs alongside aggregate model, oracle comparison begins
- Events RecordBatch populated with rebellion/migration/death events
- `compute_aggregates` populates military/economy/culture/stability from occupation/skill
