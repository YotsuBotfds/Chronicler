# M55a: Spatial Substrate — Design Spec

> **Status:** Approved for implementation.
> **Author:** Cici (Opus 4.6), with Tate directing design decisions and second-opinion review.
> **Date:** 2026-03-24
> **Depends on:** M54a (merged)
> **Blocks:** M55b, M56a, M57a, M58a, M59a, M60a

---

## 1. Goal & Scope

Give agents continuous `(x, y)` positions within their region's unit square `[0, 1)²`, deterministic movement via attractor/density/repulsion forces, per-region spatial hash for O(1) neighborhood queries, and a generic index-sort module supporting both region-key and Morton Z-curve ordering.

### In Scope

- Per-agent `x`, `y` SoA fields (+8 bytes/agent)
- Deterministic attractor placement from region features (static positions, dynamic weights)
- Occupation-weighted drift toward attractors + density attraction + repulsion
- Tick step 4.5 integration (after migration apply, before demographics, within the Rust agent tick — not Python turn loop Phase 4)
- Per-region spatial hash (10×10 grid), persisted through tick, Rust-internal
- Generic index-sort module: region-key + Morton Z-curve, with `SPATIAL_SORT_AGENT_THRESHOLD` activation and 3-way benchmark harness (arena vs region vs Morton)
- `x`, `y` columns appended to Arrow snapshot schema
- Spatial diagnostics via Rust tick telemetry (not bundle)
- RNG stream offset 2000/2001 for spatial init/drift (`INITIAL_AGE_STREAM_OFFSET` stays on 1400 to preserve the calibrated demographic baseline)

### Out of Scope

- Disease proximity spreading (enrichment, later milestone)
- Formation behavior change (hash available, Phase 10 semantics unchanged)
- Bundle/export schema changes (Phase 7.5 contract unaffected)
- Global `Region.x`/`Region.y` population (Morton uses `region_index` in high bits)
- Python FFI for spatial hash queries (Rust-internal only)
- Market attractor activation (reserved slot, inactive until M58a)

### Fan-Out

M55a unblocks: M55b (Spatial Asabiya), M56a (Settlement Detection), M57a (Marriage Matching), M58a (Merchant Mobility), M59a (Information Packets), M60a (Campaign Logistics).

---

## 2. Data Model

### 2.1 Per-Agent SoA Fields

Two new `Vec<f32>` fields on `AgentPool` (pool.rs), +8 bytes/agent:

| Field | Type | Init (spawn) | Init (birth) |
|-------|------|-------------|--------------|
| `x` | `Vec<f32>` | Near occupation-appropriate attractor, jittered via `SPATIAL_POSITION_STREAM_OFFSET` (2000) keyed on `(seed, agent_id, region_id, 0)` | Near parent's post-drift position, jittered via `SPATIAL_POSITION_STREAM_OFFSET` (2000) keyed on `(seed, child_agent_id, region_id, turn)` |
| `y` | `Vec<f32>` | Same, second component | Same, second component |

Both fields follow the existing SoA pattern: preallocate in `new()`, initialize in both spawn branches (free-list reuse and growth), clamp to `[0.0, 1.0 - f32::EPSILON]`.

### 2.2 Attractor Model

New file: `spatial.rs`.

```rust
pub const MAX_ATTRACTORS: usize = 8;

pub enum AttractorType {
    River,      // edge-biased, from river_mask
    Coast,      // edge-biased, from terrain
    Resource0,  // interior, from resource_effective_yield[0]
    Resource1,  // interior, from resource_effective_yield[1]
    Resource2,  // interior, from resource_effective_yield[2]
    Temple,     // interior, from has_temple
    Capital,    // interior, from is_capital
    Market,     // reserved for M58a, inactive
}

pub struct RegionAttractors {
    pub positions: [(f32, f32); MAX_ATTRACTORS],
    pub weights: [f32; MAX_ATTRACTORS],
    pub types: [AttractorType; MAX_ATTRACTORS],
    pub count: u8,
}
```

- Up to 8 attractor slots: 1 river, 1 coast, 3 resources (one per non-trivial yield slot), 1 temple, 1 capital, 1 market (reserved).
- Positions computed once at simulation init from `(world_seed, region_id, attractor_type)` via deterministic arithmetic (no Python-side hash needed).
- Weights recomputed each tick from live region state. Positions are static across turns.
- Stored in a `Vec<RegionAttractors>` on `AgentSimulator`, indexed by region.

### 2.3 Spatial Hash

```rust
pub struct SpatialGrid {
    pub cells: Vec<Vec<u32>>,  // GRID_SIZE × GRID_SIZE cells, each containing agent slot indices
    pub grid_size: u8,         // 10 for ~500 agents/region
}
```

- One `SpatialGrid` per region, stored in a `Vec<SpatialGrid>` on `AgentSimulator`.
- **Allocation reuse**: `Vec<SpatialGrid>` persists across ticks. Each tick, cell `Vec`s are cleared and refilled — no reallocation.
- **M61b optimization note**: At high agent density (multiple thousands per region after settlements form), the 100 inner `Vec`s create heap fragmentation. A flat `Vec<u32>` with offset/count pairs per cell would be more cache-friendly. Acceptable at M55a scope; revisit during M61b profiling.
- Cell index from position: `(coord * grid_size as f32) as usize`, safe because positions are clamped to `[0.0, 1.0 - eps]`.
- Neighbor query: scan 9 cells (center + 8 adjacent), **clamped at grid boundaries** (no toroidal wrapping), return candidate slot indices in **sorted order by slot index** for determinism.
- Self excluded from neighbor sets.

---

## 3. Attractor System

### 3.1 Initialization (Once, at Simulation Start)

For each region, scan its `RegionState` and activate applicable attractor types:

| Type | Activation Condition | Base Position | Weight Source |
|------|---------------------|---------------|---------------|
| River | `river_mask != 0` | Edge-biased: one of 4 edges chosen deterministically from `(seed, region_id, River)`. Position on the chosen edge within `[0.02, 0.15]` from boundary. | `water` level |
| Coast | `terrain == coast` | Edge-biased: one of 4 edges chosen deterministically from `(seed, region_id, Coast)`. Distance to the chosen edge is in `[0.02, 0.15]` (equivalently `[0.02, 0.15]` for left/bottom, `[0.85, 0.98]` for right/top on the corresponding axis). | Fixed 1.0 (geography) |
| Resource0/1/2 | `resource_effective_yield[slot] > 0.0` | Interior `[0.1, 0.9]`, from `(seed, region_id, type)` | `resource_effective_yield[slot]` |
| Temple | `has_temple == true` | Interior `[0.1, 0.9]`, from `(seed, region_id, Temple)` | `temple_prestige` (1.0 if unavailable) |
| Capital | `is_capital == true` | Interior, center-biased `[0.35, 0.65]`, jittered from `(seed, region_id, Capital)` | `population` (normalized) |
| Market | Reserved for M58a | — | — (inactive, weight 0) |

Edge selection: `(seed XOR region_id XOR type_discriminant) % 4` → top/bottom/left/right.

### 3.2 Minimum Separation

After computing all attractor positions for a region, enforce `MIN_ATTRACTOR_SEPARATION` (e.g., 0.15 `[CALIBRATE M61b]`):

- If any two attractors are closer than the threshold, push the lower-priority one outward along the displacement vector.
- Priority order: River > Coast > Capital > Temple > Resource2 > Resource1 > Resource0 (geographic features win ties).
- Maximum 10 push iterations. If unresolved after 10 passes, accept current positions.
- Final clamp to `[0.0, 1.0 - eps]` after all pushes.

### 3.3 Occupation Affinity Table

Each agent's effective attractor force scales by occupation affinity. The table is a `[OCCUPATION_COUNT × MAX_ATTRACTORS]` f32 matrix (use the `OCCUPATION_COUNT` constant from `agent.rs`, not a magic `5`), all values `[CALIBRATE M61b]`:

| Occupation | River | Coast | Resource | Temple | Capital |
|------------|-------|-------|----------|--------|---------|
| Farmer | 0.4 | 0.1 | **0.8** | 0.05 | 0.1 |
| Soldier | 0.1 | 0.1 | 0.1 | 0.05 | **0.7** |
| Merchant | 0.2 | 0.3 | 0.3 | 0.05 | **0.5** |
| Scholar | 0.1 | 0.1 | 0.1 | **0.5** | **0.5** |
| Priest | 0.1 | 0.05 | 0.05 | **0.8** | 0.3 |

Market column omitted (inactive). When Market activates (M58a), merchants redistribute affinity toward it. Until then, merchant pull comes from Capital and Resource — no special fallback logic needed.

### 3.4 Dynamic Weight Updates

Each tick, before Phase 4.5, recompute attractor weights from the current `RegionState` (received via `set_region_state()`). Positions remain fixed. Weight changes create emergent spatial dynamics:

- Famine (dropping `resource_effective_yield`) weakens resource attractors → agents drift away from exhausted areas.
- Temple destruction removes temple attractor weight → clergy disperse.
- Capital transfer (`MOVE_CAPITAL`) flips `is_capital` between regions → admin agents migrate toward the new capital attractor.

Individual weights clamped to `[0.0, 1.0]` before force computation. The `MAX_DRIFT_PER_TICK` displacement cap is the ultimate bound on movement magnitude.

---

## 4. Movement Mechanics

### 4.1 Tick Step 4.5 — Integration

> **Note on numbering:** "Step 4.5" refers to placement within the Rust agent tick (`tick_agents()` in `tick.rs`), NOT the Python turn loop's Phase 4 (Military). The Rust tick runs between Python Phase 9 and Phase 10. Within the Rust tick, step 4 is `apply_decisions` and step 5 is `demographics`.

After tick step 4 applies decisions (including migration), insert spatial drift:

```
Tick step 4: apply_decisions (migration changes agent.region)
  4.5a: Reset migrant positions (agents whose region changed this tick)
  4.5b: Rebuild spatial hash (all regions, includes migrants at correct positions)
  4.5c: Two-pass drift for all alive agents (read old → compute new → write)
Tick step 5: demographics (births inherit parent position post-drift)
```

### 4.2 Migration Reset (4.5a)

When an agent migrates to a new region:

```
target_attractor = highest_affinity_attractor(agent.occupation, dest_region)
pos = target_attractor.position + jitter(±MIGRATION_JITTER)
```

Jitter from `SPATIAL_POSITION_STREAM_OFFSET` (2000) keyed on `(seed, agent_id, dest_region_id, turn)`. Region-specific and deterministic.

If no attractor matches the occupation (e.g., priest migrating to a temple-less region), fall back to region center `(0.5, 0.5)` with jitter.

### 4.3 Drift Computation (4.5c)

Per agent, in stable slot-index order within each region:

1. **Attractor vector**: Sum over active attractors. Uses a **softened linear** falloff — no inverse-distance singularity:
   ```
   for each active attractor i:
     delta = attractor_pos[i] - agent_pos
     dist = |delta|
     if dist < ATTRACTOR_DEADZONE (e.g., 0.02):
       skip (agent is already at the attractor)
     direction = delta / dist   // safe: dist >= ATTRACTOR_DEADZONE
     pull = affinity[occ][i] × weight[i] × min(dist, ATTRACTOR_RANGE) / ATTRACTOR_RANGE
     attractor_vec += pull × direction
   ```
   The `min(dist, ATTRACTOR_RANGE) / ATTRACTOR_RANGE` term gives linear pull that maxes out at `ATTRACTOR_RANGE` (e.g., 0.5) and drops to zero inside `ATTRACTOR_DEADZONE`. No singularity at zero distance. Agents that reach an attractor stay there (deadzone) until other forces move them.

2. **Density vector**: Mean direction to neighbors within `DENSITY_RADIUS`. Capped at `DENSITY_ATTRACTION_MAX` to prevent runaway clustering. **Zero-distance handling**: if `dist < DENSITY_MIN_DIST` (e.g., 0.005), skip the neighbor — treat co-located agents as already clustered.

3. **Repulsion vector**: Sum of repulsion from neighbors within `REPULSION_RADIUS`. Uses capped inverse-square with deterministic zero-distance fallback:
   ```
   for each neighbor within REPULSION_RADIUS:
     delta = agent_pos - neighbor_pos
     dist = |delta|
     if dist < REPULSION_MIN_DIST:
       // Deterministic fallback: opposite directions for each agent in the pair
       angle = ((agent_id ^ neighbor_id) % 360) as f32 × (PI / 180.0)
       if agent_id < neighbor_id:
         angle += PI   // flip direction so the pair separates
       direction = (cos(angle), sin(angle))
       force = REPULSION_ZERO_DIST_FORCE
     else:
       direction = delta / dist
       force = min(1.0 / (dist × dist), REPULSION_FORCE_CAP)  // capped inverse-square
     repulsion_vec += force × direction
   ```
   **Symmetry breaking**: XOR is commutative, so both agents in a co-located pair compute the same base angle. The `agent_id < neighbor_id` check flips one agent's direction by PI, giving deterministic opposite escape directions. Equal IDs are impossible (self excluded from neighbor sets).

   **Force capping**: `REPULSION_FORCE_CAP` (e.g., 50.0 `[CALIBRATE M61b]`) prevents the inverse-square term from producing extreme values near `REPULSION_MIN_DIST`, ensuring a smooth transition from the capped zone to the zero-distance fallback.

4. **Weighted sum**:
   ```
   drift = W_ATTRACTOR × attractor_vec + W_DENSITY × density_vec + W_REPULSION × repulsion_vec
   ```

5. **Clamp magnitude**: `min(|drift|, MAX_DRIFT_PER_TICK)`

6. **Boundary clamp**: Result clamped to `[0.0, 1.0 - f32::EPSILON]`

**Two-pass update**: Read all positions into a scratch buffer, compute all new positions from old positions, write all back. No agent sees another agent's updated position within the same tick. Deterministic regardless of iteration order. Memory overhead: `2 × alive_count × sizeof(f32)` = 8 bytes/agent scratch. At 1M agents = 8MB, fits comfortably.

**`displacement_turns` interaction**: Agents with `displacement_turns > 0` (recently migrated, tracked in pool.rs) drift normally. M55a does not differentiate displaced vs. settled agents in drift computation. Downstream milestones (M56a settlement detection) may distinguish transients from settlers using this field.

### 4.4 Newborn Placement (Tick Step 5)

Newborns placed at `parent_pos + jitter(±BIRTH_JITTER)`, clamped to bounds. No drift applied until next tick.

**Parent death safety**: Before the death pass in Phase 5, snapshot `(x, y)` for all agents that are pending parents (have births queued). Births read parent position from the snapshot, not the live pool slot (which may be reused after parent death). Same pattern as existing `parent_ids` handling.

Jitter from `SPATIAL_POSITION_STREAM_OFFSET` (2000) keyed on `(seed, child_agent_id, region_id, turn)`.

### 4.5 Constants

All `[CALIBRATE M61b]`:

| Constant | Role | Tentative Value |
|----------|------|-----------------|
| `MAX_DRIFT_PER_TICK` | Displacement cap per tick | 0.04 |
| `DENSITY_RADIUS` | Neighbor attraction range | 0.15 |
| `REPULSION_RADIUS` | Hard push range | 0.05 |
| `DENSITY_ATTRACTION_MAX` | Cap on density pull magnitude | 0.02 |
| `DENSITY_MIN_DIST` | Skip co-located neighbors in density calc | 0.005 |
| `REPULSION_MIN_DIST` | Threshold for deterministic fallback direction | 0.001 |
| `REPULSION_ZERO_DIST_FORCE` | Force magnitude at zero distance (fallback) | 5.0 |
| `REPULSION_FORCE_CAP` | Max inverse-square repulsion force | 50.0 |
| `ATTRACTOR_DEADZONE` | Distance below which attractor pull is zero | 0.02 |
| `ATTRACTOR_RANGE` | Distance at which attractor pull maxes out | 0.5 |
| `W_ATTRACTOR` | Attractor force weight | 0.6 |
| `W_DENSITY` | Density attraction weight | 0.3 |
| `W_REPULSION` | Repulsion weight | 0.5 |
| `MIGRATION_JITTER` | Position scatter on region entry | 0.05 |
| `BIRTH_JITTER` | Position scatter for newborns | 0.02 |
| `MIN_ATTRACTOR_SEPARATION` | Minimum distance between attractors | 0.15 |

---

## 5. Sort Infrastructure

> **Note:** The roadmap (D2, lines 411-425) assigned shared sort infrastructure to M54a, with M55a extending it to Morton. M54a landed without any sort infrastructure — no `sort.rs` exists in the crate. M55a absorbs the full scope: both the region-key baseline and the Morton extension are greenfield work in this milestone. The region-key path serves as benchmark control and fallback; Morton is the runtime path.

### 5.1 Module: `sort.rs`

New file providing generic index-sort infrastructure with two key modes. This is entirely new code — no pre-existing sort module to extend.

**Public API:**

```rust
/// Returns sorted iteration order for alive agents.
/// Below SPATIAL_SORT_AGENT_THRESHOLD: alive-slot identity order (ascending slot index).
/// Above threshold: Morton-sorted index.
pub fn sorted_iteration_order(pool: &AgentPool) -> Vec<usize>

/// Region-key sort (benchmark/control/fallback).
pub fn sort_by_region(pool: &AgentPool) -> Vec<usize>

/// Morton Z-curve sort (runtime path).
pub fn sort_by_morton(pool: &AgentPool) -> Vec<usize>
```

`sorted_iteration_order()` is the single entry point for tick phases that want cache-efficient iteration.

### 5.2 Sort Keys

| Mode | Key Construction | Bits |
|------|-----------------|------|
| Region | `(region_index as u64) << 32 \| agent_id as u64` | 64-bit: 32 region + 32 id |
| Morton | `(region_index as u64) << 48 \| (morton_interleave(x_q, y_q) as u64) << 32 \| agent_id as u64` | 64-bit: 16 region + 16 morton + 32 id |

- `morton_interleave` takes 8-bit quantized `x` and `y` (from `(coord × 256.0) as u8`) and interleaves bits into a 16-bit Z-curve pattern.
- Region index in high bits keeps same-region agents contiguous.
- **Secondary key = `agent_id`** (from `pool.ids`): ensures deterministic ordering for agents with identical region/morton keys. No arena-order tiebreak. (Roadmap guardrail: chronicler-phase7-roadmap.md line 910.)

### 5.3 Algorithm

Radix sort on 64-bit keys. At 1M agents, radix sort is O(n) — faster than introsort O(n log n) at scale.

- Sort operates on an index array — produces a permutation of alive slot indices, not a rearrangement of SoA data.
- **Only alive slots**: Dead/free-list slots excluded from the sort.
- **Return type**: `Vec<usize>` to match pool indexing convention.

### 5.4 Threshold Activation

```rust
pub const SPATIAL_SORT_AGENT_THRESHOLD: usize = 100_000; // [CALIBRATE M61b]
```

Below threshold: `sorted_iteration_order()` returns identity permutation. Above threshold: returns Morton-sorted index.

### 5.5 Benchmark Harness

Three-way comparison at synthetic pool sizes (50K, 100K, 500K, 1M):

| Mode | Description |
|------|------------|
| Arena | No sort, identity permutation |
| Region | `sort_by_region` — isolates value of region-contiguous iteration |
| Morton | `sort_by_morton` — adds within-region Z-curve locality |

Measures: sort time, tick duration with each ordering. Region-key serves as the control baseline — it isolates the value of Morton's within-region ordering from the baseline benefit of region-contiguous iteration.

### 5.6 Determinism

Radix sort is stable, and the secondary `agent_id` key makes the sort fully deterministic. Verified by seed comparison test across thread counts and processes.

---

## 6. FFI Surface & Python Integration

### 6.1 Existing Path Changes

**`build_region_batch()` / `set_region_state()`** — two new columns:

| Column | Type | Source |
|--------|------|--------|
| `is_capital` | bool | `any(civ.capital_region == region.name for civ in world.civilizations if civ.regions)` |
| `temple_prestige` | f32 | Max `temple_prestige` from region's infrastructure list (0.0 if no temple) |

**Rust struct changes:** `is_capital: bool` (default `false`) and `temple_prestige: f32` (default `0.0`) are new fields on `RegionState` in `region.rs`. Must be added to:
- `RegionState` struct definition and `RegionState::new()` defaults
- All Rust test constructors that build `RegionState` directly
- `set_region_state()` parsing in `AgentSimulator` (ffi.rs ~line 538)
- `set_region_state()` parsing in `EcologySimulator` (ffi.rs ~line 2004) — ecology doesn't need these columns, but the parser must handle them gracefully with `None` defaults

Parsed with `column_by_name().and_then(...)` optional-column pattern (matching existing backward-compatible parsing in `set_region_state()`). Existing test batches without these columns still pass.

**`snapshot_schema` / `to_record_batch()`** — two new columns appended at end:

| Column | Type |
|--------|------|
| `x` | f32 |
| `y` | f32 |

No mid-schema insertion. Existing column indices unchanged. Schema test in `test_agent_bridge.py` updated to expect new columns.

### 6.2 Spatial Initialization

Handled internally on the first `set_region_state()` call:

1. `AgentSimulator` detects first call (flag or null check on attractor storage).
2. Computes attractor positions for all regions from seed + region state.
3. **Then** sets initial agent `(x, y)` based on occupation-appropriate attractors + `SPATIAL_POSITION_STREAM_OFFSET` (2000). Order matters: attractors must exist before agent position init so agents spawn at meaningful locations.

No new Python-callable init method. `AgentSimulator` already holds the seed from construction.

> **RNG convention note:** The existing agent tick RNG convention (agent.rs lines 90-91) is `stream = region_id × 1000 + turn + OFFSET` for region-parallel stages. Spatial position init/migration/birth jitter must use **deterministic per-agent substreams** keyed by `(agent_id, region_id, turn)` under `SPATIAL_POSITION_STREAM_OFFSET` so each agent gets unique, repeatable jitter. Avoid shared mutable RNG state across agents/threads. Drift (if stochastic noise is enabled later) remains on `SPATIAL_DRIFT_STREAM_OFFSET` in the regional pattern.

### 6.3 Spatial Diagnostics

New PyO3 getter on `AgentSimulator`, following the `get_demographic_debug()` / `get_relationship_stats()` pattern:

```rust
pub fn get_spatial_diagnostics(&self) -> PyResult<PyObject> {
    // Returns a Python dict with:
    //   hotspot_count_by_region: list[int]      — cells with >2× mean density, per region
    //   attractor_occupancy: list[list[float]]   — fraction of agents within radius of each attractor
    //   hash_max_cell_occupancy: list[int]       — max agents in any cell, per region
    //   sort_time_us: int                        — sort duration in microseconds
}
```

Called by Python after tick if diagnostics are requested. Consumed by a new `extract_spatial_diagnostics()` analytics extractor.

### 6.4 `--agents=off` Compatibility

Spatial positions are agent-mode only. `--agents=off` skips Phase 4.5 entirely. In off mode there is no Rust agent snapshot, so `x`/`y` are absent by construction. No impact on aggregate-mode determinism.

---

## 7. Determinism, RNG & Testing

### 7.1 RNG Offset Resolution (Prerequisite)

Execute before any other M55a code:

1. Keep `INITIAL_AGE_STREAM_OFFSET = 1400` in `agent.rs` so spawn-age seeding stays aligned with the calibrated pre-M55 demographic baseline.
2. Register `SPATIAL_POSITION_STREAM_OFFSET = 2000` (init-time position seeding and deterministic jitter).
3. Register `SPATIAL_DRIFT_STREAM_OFFSET = 2001` (reserved per-tick drift noise, if stochastic spatial noise is enabled later).
4. Update the collision test array with all three changes.

Separate streams for init vs. drift prevents cross-concern correlation. Final closeout kept the age stream unchanged and moved the spatial system instead after the canonical gate showed the age-stream shuffle was the biggest branch-level calibration risk.

### 7.2 Determinism Merge Gates

| Gate | Verification | Test Type |
|------|-------------|-----------|
| Cross-process | Same seed → identical `(x, y)` after N ticks | Two-process seed replay, snapshot comparison |
| Cross-thread | Same seed, 1/4/8/16 threads → identical positions | `rayon::ThreadPoolBuilder` override, snapshot comparison |
| Sort stability | Sorted index identical across runs for same pool state | Seed replay + sort output comparison |
| Migration reset | Migrant lands at identical position regardless of tick ordering | Targeted: force migration, verify position |

### 7.3 Integration Test Coverage

| Test | Purpose |
|------|---------|
| Spatial hash correctness | 9-cell neighbor query returns exactly the agents within radius |
| Drift convergence | Agent near attractor with no neighbors → converges toward attractor over ~20 ticks |
| Repulsion separation | Two agents at same position → pushed apart within 1 tick |
| Migration reset | Agent migrating → position near occupation-appropriate attractor in dest region |
| Newborn placement | Newborn position within `BIRTH_JITTER` of parent's post-drift position |
| Sort determinism | Morton sort identical permutation across processes and thread counts |
| Attractor separation | No two attractors in same region closer than `MIN_ATTRACTOR_SEPARATION` |
| Parent death safety | Parent dies + slot reused same tick → newborn still gets correct parent position |
| Hotspot formation | After 50 ticks with active resource attractor, density near attractor > 2× mean |
| Attractor weight dynamics | Dropping `resource_effective_yield` → resource attractor weight decreases |

### 7.4 Implementation Guardrails

- New region-batch columns (`is_capital`, `temple_prestige`) parsed with default fallback so minimal test batches still pass.
- Snapshot schema test updated to include `x`, `y` at end.
- Collision test array updated for all offset changes.
- Two-pass drift update (read old → compute → write) for tick-internal determinism.
- Spatial hash neighbor iteration sorted by slot index before force computation.
- Jitter generation stateless/deterministic per agent — no shared mutable RNG across threads.

---

## 8. Design Decisions Summary

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | M55a absorbs sort infrastructure from M54a gap | Roadmap D2 requires shared sort infra + Morton. Region-key baseline needed for benchmark/control. |
| D2 | Attractor positions via deterministic template anchors + bounded jitter | Meets roadmap "deterministic attractor seeds." Static positions produce persistent hotspots for M56a. No new RNG stream needed. |
| D3 | Movement at Phase 4.5 (after migration, before demographics) | Avoids same-tick spatial→satisfaction feedback. Migrants land at meaningful positions before births. |
| D4 | Spatial hash persisted through tick, Rust-internal only | Hash is cheap (~40KB), useful to multiple phases. No Python FFI exposure — keeps API surface minimal. |
| D5 | Additive force vectors with displacement cap | Transparent, tunable, deterministic. Three forces with clear weights + hard cap prevents teleportation and oscillation. |
| D6 | Snapshot includes (x,y), bundle does not | Python diagnostics/narrative get spatial access. Phase 7.5 bundle contract unaffected. |
| D7 | `INITIAL_AGE_STREAM_OFFSET` stays 1400, M55a claims 2000/2001 | Preserves the calibrated demographic baseline while still giving spatial init/drift dedicated non-colliding streams. |
| D8 | All enrichments out of M55a scope | M55a is substrate only. Disease/proximity consumers belong in later milestones. |
| D9 | Formation semantics unchanged | Hash available but no behavior change. Avoids coupling two tuning surfaces. First authoritative consumers: M57a/M59a. |
| D10 | Agent positions in snapshot, not bundle | Positions are live simulation state, not chronicle output. Bundle schema stable for Phase 7.5. |

---

## 9. Constants Registry

### New Constants (all `[CALIBRATE M61b]`)

| Constant | Module | Role |
|----------|--------|------|
| `MAX_DRIFT_PER_TICK` | `spatial.rs` | Displacement cap per tick |
| `DENSITY_RADIUS` | `spatial.rs` | Neighbor attraction range |
| `REPULSION_RADIUS` | `spatial.rs` | Hard push range |
| `DENSITY_ATTRACTION_MAX` | `spatial.rs` | Cap on density pull magnitude |
| `DENSITY_MIN_DIST` | `spatial.rs` | Skip co-located neighbors in density calc |
| `REPULSION_MIN_DIST` | `spatial.rs` | Threshold for deterministic fallback direction |
| `REPULSION_ZERO_DIST_FORCE` | `spatial.rs` | Force magnitude at zero distance (fallback) |
| `REPULSION_FORCE_CAP` | `spatial.rs` | Max inverse-square repulsion force |
| `ATTRACTOR_DEADZONE` | `spatial.rs` | Distance below which attractor pull is zero |
| `ATTRACTOR_RANGE` | `spatial.rs` | Distance at which attractor pull maxes out |
| `W_ATTRACTOR` | `spatial.rs` | Attractor force weight |
| `W_DENSITY` | `spatial.rs` | Density attraction weight |
| `W_REPULSION` | `spatial.rs` | Repulsion weight |
| `MIGRATION_JITTER` | `spatial.rs` | Position scatter on region entry |
| `BIRTH_JITTER` | `spatial.rs` | Position scatter for newborns |
| `MIN_ATTRACTOR_SEPARATION` | `spatial.rs` | Minimum distance between attractors in a region |
| `SPATIAL_SORT_AGENT_THRESHOLD` | `sort.rs` | Agent count above which Morton sort activates |
| `SPATIAL_POSITION_STREAM_OFFSET` | `agent.rs` | RNG stream for position initialization |
| `SPATIAL_DRIFT_STREAM_OFFSET` | `agent.rs` | RNG stream for drift noise |

### Moved Constants

| Constant | Old Value | New Value | Reason |
|----------|-----------|-----------|--------|
| `INITIAL_AGE_STREAM_OFFSET` | 1400 | 1400 | Kept unchanged after full-gate recovery showed the age-stream move was the highest-risk calibration shift in the M55 stack |

### Occupation Affinity Matrix

5 × MAX_ATTRACTORS f32 matrix, all values `[CALIBRATE M61b]`. See Section 3.3 for tentative values.
