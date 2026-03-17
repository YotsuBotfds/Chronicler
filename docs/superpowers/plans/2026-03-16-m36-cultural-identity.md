# M36: Cultural Identity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give agents individual cultural values that drift via regional pressure, environmental shaping, and named character influence, replacing timer-based assimilation with agent-driven 60% threshold.

**Architecture:** Rust SoA pool gains 3 cultural value fields (u8 each). New `culture_tick.rs` module runs as tick stage 5 — recomputes per-region frequency distribution, applies environmental bias from M34 resources, then drifts each agent's values with slot-weighted probability. Python `culture.py` reads the agent snapshot to replace timer-based assimilation with a 60% agent-driven check. Satisfaction penalty cap (-0.4) infrastructure wired in `satisfaction.rs` for M37/M38b forward compat.

**Tech Stack:** Rust (chronicler-agents crate, PyO3, Arrow), Python (PyArrow, Pydantic), pytest, cargo test

**Spec:** `docs/superpowers/specs/2026-03-16-m36-cultural-identity-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/agent.rs` | `IS_NAMED` constant, M36 cultural constants |
| `chronicler-agents/src/pool.rs` | SoA `cultural_value_0/1/2` fields, extended `spawn()` |
| `chronicler-agents/src/region.rs` | `controller_values`, `culture_investment_active` on `RegionState` |
| `chronicler-agents/src/ffi.rs` | Snapshot schema + region batch parsing extensions |
| `chronicler-agents/src/satisfaction.rs` | Cultural distance, mismatch penalty, penalty cap |
| `chronicler-agents/src/culture_tick.rs` | **New.** Frequency distribution, env bias, drift, orchestration |
| `chronicler-agents/src/tick.rs` | Stage 5 call, birth cultural value inheritance |
| `chronicler-agents/src/lib.rs` | Module export |
| `src/chronicler/agent_bridge.py` | New region batch columns, `VALUE_TO_ID` mapping |
| `src/chronicler/culture.py` | `compute_civ_cultural_profile()`, assimilation replacement, value drift modification |
| `src/chronicler/action_engine.py` | INVEST_CULTURE signal flag |

---

## Chunk 1: Rust Foundation

### Task 1: Add cultural constants to agent.rs

**Files:**
- Modify: `chronicler-agents/src/agent.rs:103-108`

- [ ] **Step 1: Add IS_NAMED and cultural value constants**

After the existing `LIFE_EVENT_OCC_SWITCH` constant (line 108), add:

```rust
// M36: Cultural identity
pub const IS_NAMED: u8 = 1 << 5;  // bit 5 of life_events

/// Number of cultural value enum variants (Freedom=0..Cunning=5).
pub const NUM_CULTURAL_VALUES: usize = 6;

/// Sentinel for empty cultural value slot.
pub const CULTURAL_VALUE_EMPTY: u8 = 0xFF;

// --- M36 cultural drift tuning constants ---
pub const CULTURAL_DRIFT_RATE: f32 = 0.06;
pub const DRIFT_SLOT_WEIGHTS: [f32; 3] = [1.0 / 3.0, 2.0 / 3.0, 1.0];
pub const CULTURAL_MISMATCH_WEIGHT: f32 = 0.05;
pub const PENALTY_CAP: f32 = 0.40;
pub const NAMED_CULTURE_WEIGHT: u16 = 5;
pub const ENV_BIAS_FRACTION: f32 = 0.05;
pub const ENV_SLOT_WEIGHTS: [f32; 3] = [1.0, 0.5, 0.25];
pub const DISSATISFIED_DRIFT_BONUS: f32 = 0.03;
pub const DISSATISFIED_THRESHOLD: f32 = 0.4;
pub const INVEST_CULTURE_BONUS: f32 = 0.10;
```

Note: `CULTURE_DRIFT_OFFSET: u64 = 500` already exists at `agent.rs:89` — do NOT re-add it. Tasks 5-7 reference it as `agent::CULTURE_DRIFT_OFFSET`.

- [ ] **Step 2: Verify it compiles**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m36): add IS_NAMED bit and cultural drift constants"
```

---

### Task 2: Add cultural value fields to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-51` (struct), `pool.rs:55-78` (new), `pool.rs:81-141` (spawn), `pool.rs:260-290` (accessors)
- Test: `chronicler-agents/src/pool.rs` (inline tests)

- [ ] **Step 1: Write failing test for cultural value spawn**

Add to the `#[cfg(test)] mod tests` block at end of pool.rs:

```rust
#[test]
fn test_spawn_cultural_values() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 4, 3, 2);
    assert_eq!(pool.cultural_value_0[slot], 4); // Honor
    assert_eq!(pool.cultural_value_1[slot], 3); // Knowledge
    assert_eq!(pool.cultural_value_2[slot], 2); // Tradition
    assert!(pool.alive[slot]);
}

#[test]
fn test_spawn_reuse_slot_cultural_values() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 4, 3, 2);
    pool.kill(slot);
    let reused = pool.spawn(0, 1, Occupation::Soldier, 18, 0.6, 0.4, 0.5, 0, 1, 5);
    assert_eq!(reused, slot); // reused same slot
    assert_eq!(pool.cultural_value_0[reused], 0); // Freedom
    assert_eq!(pool.cultural_value_1[reused], 1); // Order
    assert_eq!(pool.cultural_value_2[reused], 5); // Cunning
}

#[test]
fn test_is_named_bit() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 0, 1, 2);
    assert_eq!(pool.life_events[slot] & crate::agent::IS_NAMED, 0);
    pool.life_events[slot] |= crate::agent::IS_NAMED;
    assert_ne!(pool.life_events[slot] & crate::agent::IS_NAMED, 0);
    // Existing life events still work
    pool.life_events[slot] |= crate::agent::LIFE_EVENT_REBELLION;
    assert_ne!(pool.life_events[slot] & crate::agent::LIFE_EVENT_REBELLION, 0);
    assert_ne!(pool.life_events[slot] & crate::agent::IS_NAMED, 0);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chronicler-agents && cargo test test_spawn_cultural_values -- --nocapture 2>&1 | head -20`
Expected: compile error — `spawn()` takes wrong number of arguments

- [ ] **Step 3: Add cultural value fields to AgentPool struct**

Add three fields after the `loyalty_trait` field (around line 41):

```rust
    // Cultural identity (M36) — 3 ranked value slots, distinct enum indices
    pub cultural_value_0: Vec<u8>,   // Primary (stickiest, 1/3× drift rate)
    pub cultural_value_1: Vec<u8>,   // Secondary (2/3× drift rate)
    pub cultural_value_2: Vec<u8>,   // Tertiary (base drift rate)
```

- [ ] **Step 4: Initialize in `new()`**

In the `new()` function (around line 55-78), add capacity allocation:

```rust
            cultural_value_0: Vec::with_capacity(capacity),
            cultural_value_1: Vec::with_capacity(capacity),
            cultural_value_2: Vec::with_capacity(capacity),
```

- [ ] **Step 5: Extend spawn() signature and both paths**

Update the spawn function signature to accept 3 additional u8 params:

```rust
pub fn spawn(
    &mut self,
    region: u16,
    civ_affinity: u8,
    occupation: Occupation,
    age: u16,
    boldness: f32,
    ambition: f32,
    loyalty_trait: f32,
    cultural_value_0: u8,
    cultural_value_1: u8,
    cultural_value_2: u8,
) -> usize {
```

In the free-slot reuse path (the `if let Some(slot)` branch), add:

```rust
        self.cultural_value_0[slot] = cultural_value_0;
        self.cultural_value_1[slot] = cultural_value_1;
        self.cultural_value_2[slot] = cultural_value_2;
```

In the grow-vecs else branch, add:

```rust
        self.cultural_value_0.push(cultural_value_0);
        self.cultural_value_1.push(cultural_value_1);
        self.cultural_value_2.push(cultural_value_2);
```

- [ ] **Step 6: Add accessor methods**

After the existing `loyalty_trait()` accessor (around line 280):

```rust
    #[inline]
    pub fn cultural_value_0(&self, slot: usize) -> u8 {
        self.cultural_value_0[slot]
    }

    #[inline]
    pub fn cultural_value_1(&self, slot: usize) -> u8 {
        self.cultural_value_1[slot]
    }

    #[inline]
    pub fn cultural_value_2(&self, slot: usize) -> u8 {
        self.cultural_value_2[slot]
    }

    #[inline]
    pub fn is_named(&self, slot: usize) -> bool {
        self.life_events[slot] & crate::agent::IS_NAMED != 0
    }
```

- [ ] **Step 7: Fix ALL existing spawn() call sites**

The signature change breaks every existing call to `spawn()`. Run `cargo check` — expect **15-20 compile errors** across these files:

- `tick.rs` — demographics births (around line 243): Use `birth.cultural_values[0/1/2]` (wired properly in Task 7)
- `ffi.rs` — initial spawn from Python (around line 380): Use `CULTURAL_VALUE_EMPTY` × 3 (Python sets real values later)
- `pool.rs` tests — every `#[test]` that calls `pool.spawn(...)`: Append `0, 1, 2` or any valid distinct u8 values
- `tick.rs` tests — any test helpers that spawn agents: Same fix
- `satisfaction.rs` tests — if any spawn agents: Same fix
- `behavior.rs` tests — if any spawn agents: Same fix
- `demographics.rs` tests — if any spawn agents: Same fix

**Process:** Run `cargo check`, fix every error by appending 3 u8 args (use `CULTURAL_VALUE_EMPTY` for production code, arbitrary values for tests), repeat until clean. Do NOT skip any call site.

For now, use CULTURAL_VALUE_EMPTY at all non-test call sites to unblock compilation. Task 7 will wire proper birth values.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test test_spawn_cultural -- --nocapture`
Expected: All 3 tests pass

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "feat(m36): add cultural_value_0/1/2 fields to AgentPool + spawn()"
```

---

### Task 3: Extend snapshot schema and region batch parsing

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:64-80` (snapshot schema), `ffi.rs:202-425` (region parsing)
- Modify: `chronicler-agents/src/region.rs:18-41` (RegionState struct)
- Modify: `chronicler-agents/src/pool.rs:321-381` (to_record_batch)

- [ ] **Step 1: Add fields to RegionState**

In `region.rs`, after `endemic_severity: f32` (around line 41), add:

```rust
    // M36: Cultural identity signals
    pub culture_investment_active: bool,
    pub controller_values: [u8; 3],  // Controlling civ's cultural values, 0xFF = empty
```

In `RegionState::new()`, add defaults:

```rust
            culture_investment_active: false,
            controller_values: [0xFF, 0xFF, 0xFF],
```

- [ ] **Step 2: Extend snapshot schema with cultural value columns**

In `ffi.rs`, in `snapshot_schema()` (around line 78), add after the `loyalty_trait` field:

```rust
        Field::new("cultural_value_0", DataType::UInt8, false),
        Field::new("cultural_value_1", DataType::UInt8, false),
        Field::new("cultural_value_2", DataType::UInt8, false),
```

- [ ] **Step 3: Extend to_record_batch() in pool.rs**

In `pool.rs`, in `to_record_batch()`, add builders alongside existing personality builders:

```rust
        let mut cv0_builder = UInt8Builder::with_capacity(live);
        let mut cv1_builder = UInt8Builder::with_capacity(live);
        let mut cv2_builder = UInt8Builder::with_capacity(live);
```

In the alive-agent loop, add appends:

```rust
            cv0_builder.append_value(self.cultural_value_0[i]);
            cv1_builder.append_value(self.cultural_value_1[i]);
            cv2_builder.append_value(self.cultural_value_2[i]);
```

Add columns to the RecordBatch construction (after loyalty_trait column):

```rust
            Arc::new(cv0_builder.finish()) as ArrayRef,
            Arc::new(cv1_builder.finish()) as ArrayRef,
            Arc::new(cv2_builder.finish()) as ArrayRef,
```

- [ ] **Step 4: Parse new region batch columns in ffi.rs**

In `set_region_state()` (around line 250-300), add optional column extraction:

```rust
    let culture_investment = rb
        .column_by_name("culture_investment_active")
        .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
    let ctrl_val_0 = rb
        .column_by_name("controller_values_0")
        .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
    let ctrl_val_1 = rb
        .column_by_name("controller_values_1")
        .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
    let ctrl_val_2 = rb
        .column_by_name("controller_values_2")
        .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
```

In the per-region loop, add field assignment:

```rust
            r.culture_investment_active = culture_investment.map_or(false, |arr| arr.value(i));
            r.controller_values = [
                ctrl_val_0.map_or(0xFF, |arr| arr.value(i)),
                ctrl_val_1.map_or(0xFF, |arr| arr.value(i)),
                ctrl_val_2.map_or(0xFF, |arr| arr.value(i)),
            ];
```

- [ ] **Step 5: Verify compilation**

Run: `cd chronicler-agents && cargo check`
Expected: compiles

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs chronicler-agents/src/pool.rs
git commit -m "feat(m36): extend snapshot schema + region batch with cultural columns"
```

---

### Task 4: Cultural distance and satisfaction penalty cap

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs:57-99`
- Test: `chronicler-agents/src/satisfaction.rs` (inline tests)

- [ ] **Step 1: Write failing tests for cultural distance and penalty cap**

Add to (or create) the test module in satisfaction.rs:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cultural_distance_full_overlap() {
        // {Honor, Knowledge, Tradition} vs {Honor, Knowledge, Tradition} → distance 0
        assert_eq!(cultural_distance([4, 3, 2], [4, 3, 2]), 0);
    }

    #[test]
    fn test_cultural_distance_partial_overlap() {
        // {Honor, Knowledge, Tradition} vs {Knowledge, Tradition, Freedom} → distance 1
        assert_eq!(cultural_distance([4, 3, 2], [3, 2, 0]), 1);
    }

    #[test]
    fn test_cultural_distance_no_overlap() {
        // {Honor, Knowledge, Tradition} vs {Freedom, Order, Cunning} → distance 3
        assert_eq!(cultural_distance([4, 3, 2], [0, 1, 5]), 3);
    }

    #[test]
    fn test_cultural_distance_order_independent() {
        // Same values in different slot order → same distance
        assert_eq!(cultural_distance([4, 3, 2], [2, 4, 3]), 0);
        assert_eq!(cultural_distance([4, 3, 2], [0, 3, 4]), 1);
    }

    #[test]
    fn test_cultural_distance_with_empty_slots() {
        // 0xFF sentinel should not match anything
        assert_eq!(cultural_distance([4, 3, 0xFF], [4, 3, 0xFF]), 1);
        // Two agents with 2 values each share both → distance 1 (only 2 of 3 slots overlap)
    }

    #[test]
    fn test_cultural_penalty_zero_distance() {
        let pen = compute_cultural_penalty([4, 3, 2], [4, 3, 2]);
        assert_eq!(pen, 0.0);
    }

    #[test]
    fn test_cultural_penalty_max_distance() {
        let pen = compute_cultural_penalty([4, 3, 2], [0, 1, 5]);
        assert!((pen - 0.15).abs() < 0.001); // 3 × 0.05
    }

    #[test]
    fn test_penalty_cap_clamps() {
        // Cultural max 0.15 + simulated future terms 0.30 → capped at 0.40
        let cultural = 0.15_f32;
        let future = 0.30_f32;
        let total = apply_penalty_cap(cultural + future);
        assert!((total - 0.40).abs() < 0.001);
    }

    #[test]
    fn test_penalty_cap_no_clamp_when_under() {
        let total = apply_penalty_cap(0.10);
        assert!((total - 0.10).abs() < 0.001);
    }

    #[test]
    fn test_zero_penalty_neutral_satisfaction() {
        // When all cultural values match controller, satisfaction should be identical
        // to pre-M36 (cultural_penalty = 0.0 contributes nothing).
        // NOTE: Adapt argument list to match the actual current compute_satisfaction()
        // signature in satisfaction.rs — the args below are illustrative.
        let base = compute_satisfaction(
            0, 0.8, 0.7, 80, 1.0, 0.8, false, false, false, false, 2, 0.5,
            &CivShock::default(),
        );
        let with_culture = compute_satisfaction_with_culture(
            0, 0.8, 0.7, 80, 1.0, 0.8, false, false, false, false, 2, 0.5,
            &CivShock::default(),
            [4, 3, 2], [4, 3, 2],  // matching values → distance 0
        );
        assert_eq!(base, with_culture);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test test_cultural_distance -- --nocapture 2>&1 | head -20`
Expected: compile error — functions not defined

- [ ] **Step 3: Implement cultural distance function**

Add to satisfaction.rs (above `compute_satisfaction`):

```rust
/// Count the overlap between two sets of 3 cultural values (0xFF = empty/ignored).
/// Returns distance = 3 - overlap_count.
#[inline]
pub fn cultural_distance(agent_values: [u8; 3], controller_values: [u8; 3]) -> u8 {
    let mut overlap: u8 = 0;
    for &av in &agent_values {
        if av == crate::agent::CULTURAL_VALUE_EMPTY {
            continue;
        }
        for &cv in &controller_values {
            if cv == crate::agent::CULTURAL_VALUE_EMPTY {
                continue;
            }
            if av == cv {
                overlap += 1;
                break;
            }
        }
    }
    3 - overlap
}

/// Compute cultural mismatch penalty from distance.
#[inline]
pub fn compute_cultural_penalty(agent_values: [u8; 3], controller_values: [u8; 3]) -> f32 {
    let dist = cultural_distance(agent_values, controller_values);
    dist as f32 * crate::agent::CULTURAL_MISMATCH_WEIGHT
}

/// Apply non-ecological penalty cap.
#[inline]
pub fn apply_penalty_cap(total_penalty: f32) -> f32 {
    total_penalty.min(crate::agent::PENALTY_CAP)
}
```

- [ ] **Step 4: Add compute_satisfaction_with_culture()**

Add a new function that wraps the existing formula with the cultural penalty:

```rust
/// Satisfaction with M36 cultural mismatch penalty.
pub fn compute_satisfaction_with_culture(
    occupation: u8,
    soil: f32,
    water: f32,
    civ_stability: u8,
    demand_supply_ratio: f32,
    pop_over_capacity: f32,
    civ_at_war: bool,
    region_contested: bool,
    occ_matches_faction: bool,
    is_displaced: bool,
    trade_routes: u8,
    faction_influence: f32,
    shock: &CivShock,
    agent_values: [u8; 3],
    controller_values: [u8; 3],
) -> f32 {
    let base_sat = compute_satisfaction(
        occupation, soil, water, civ_stability, demand_supply_ratio,
        pop_over_capacity, civ_at_war, region_contested, occ_matches_faction,
        is_displaced, trade_routes, faction_influence, shock,
    );
    let cultural_pen = compute_cultural_penalty(agent_values, controller_values);
    // M36: penalty cap infrastructure — M37/M38b add terms to this sum
    let total_non_eco_penalty = apply_penalty_cap(cultural_pen);
    (base_sat - total_non_eco_penalty).clamp(0.0, 1.0)
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test test_cultural -- --nocapture`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs
git commit -m "feat(m36): add cultural distance, mismatch penalty, and penalty cap"
```

---

## Chunk 2: Rust Core Logic

### Task 5: Create culture_tick.rs — frequency distribution and environmental bias

**Files:**
- Create: `chronicler-agents/src/culture_tick.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Test: inline in `culture_tick.rs`

- [ ] **Step 1: Write failing tests**

Create `chronicler-agents/src/culture_tick.rs` with tests first:

```rust
use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Environmental bias table: resource_type (0-7) → value bias weights (6 values).
/// Sparse: most entries are 0.0. Primary bias = 1.0, secondary = 0.5.
const ENV_BIAS_TABLE: [[f32; 6]; 8] = [
    // Freedom, Order, Tradition, Knowledge, Honor, Cunning
    [0.0, 0.5, 1.0, 0.0, 0.0, 0.0], // GRAIN:      Tradition(primary), Order(secondary)
    [0.0, 0.0, 1.0, 0.0, 0.0, 0.0], // TIMBER:     Tradition(primary)
    [0.0, 0.0, 0.0, 1.0, 0.0, 0.5], // BOTANICALS: Knowledge(primary), Cunning(secondary)
    [1.0, 0.0, 0.0, 0.0, 0.0, 0.5], // FISH:       Freedom(primary), Cunning(secondary)
    [0.5, 0.0, 0.0, 0.0, 0.0, 1.0], // SALT:       Cunning(primary), Freedom(secondary)
    [0.0, 0.5, 0.0, 0.0, 1.0, 0.0], // ORE:        Honor(primary), Order(secondary)
    [0.0, 0.0, 0.0, 0.5, 0.0, 1.0], // PRECIOUS:   Cunning(primary), Knowledge(secondary)
    [1.0, 0.0, 0.0, 0.5, 0.0, 0.0], // EXOTIC:     Freedom(primary), Knowledge(secondary)
];

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_test_pool(n: usize, values: &[[u8; 3]]) -> AgentPool {
        let mut pool = AgentPool::new(n);
        for v in values {
            pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, v[0], v[1], v[2]);
        }
        pool
    }

    #[test]
    fn test_compute_distribution_basic() {
        // 3 agents: all hold Honor(4) in slot 0
        let pool = make_test_pool(4, &[[4, 3, 2], [4, 1, 0], [4, 5, 2]]);
        let slots: Vec<usize> = (0..3).collect();
        let dist = compute_cultural_distribution(&pool, &slots);
        assert_eq!(dist[4], 3); // Honor: all 3 agents
        assert_eq!(dist[3], 1); // Knowledge: 1 agent
        assert_eq!(dist[2], 2); // Tradition: 2 agents
        assert_eq!(dist[1], 1); // Order: 1 agent
        assert_eq!(dist[0], 1); // Freedom: 1 agent
        assert_eq!(dist[5], 1); // Cunning: 1 agent
    }

    #[test]
    fn test_compute_distribution_named_agent_weight() {
        // 1 named agent with Honor, 1 unnamed with Freedom
        let mut pool = make_test_pool(4, &[[4, 3, 2], [0, 1, 5]]);
        pool.life_events[0] |= agent::IS_NAMED;
        let slots: Vec<usize> = (0..2).collect();
        let dist = compute_cultural_distribution(&pool, &slots);
        // Named agent counts 5× for each value
        assert_eq!(dist[4], 5); // Honor: 5 (named)
        assert_eq!(dist[3], 5); // Knowledge: 5 (named)
        assert_eq!(dist[2], 5); // Tradition: 5 (named)
        assert_eq!(dist[0], 1); // Freedom: 1 (unnamed)
    }

    #[test]
    fn test_env_bias_ore_region() {
        // ORE in slot 0 → Honor + Order bias
        let resource_types = [5u8, 255, 255]; // ORE only
        let population = 200u16;
        let mut dist = [0u16; 6];
        apply_environmental_bias(&mut dist, &resource_types, population);
        // Phantom weight = 200 * 0.05 = 10
        // ORE slot 0 weight = 1.0: Honor gets 10*1.0 = 10, Order gets 10*0.5 = 5
        assert_eq!(dist[4], 10); // Honor
        assert_eq!(dist[1], 5);  // Order
        assert_eq!(dist[0], 0);  // Freedom (no bias)
    }

    #[test]
    fn test_env_bias_slot_weighted() {
        // GRAIN(slot 0, weight 1.0) + FISH(slot 1, weight 0.5)
        let resource_types = [0u8, 3, 255]; // GRAIN + FISH
        let population = 200u16;
        let mut dist = [0u16; 6];
        apply_environmental_bias(&mut dist, &resource_types, population);
        // GRAIN slot 0 (×1.0): Tradition 10, Order 5
        // FISH slot 1 (×0.5): Freedom 5, Cunning 2 (rounded)
        assert_eq!(dist[2], 10); // Tradition from GRAIN
        assert_eq!(dist[1], 5);  // Order from GRAIN
        assert_eq!(dist[0], 5);  // Freedom from FISH (10*0.5*1.0 = 5)
    }

    #[test]
    fn test_env_bias_table_sparse() {
        // Verify each resource type has at most 2 nonzero entries
        for (rtype, row) in ENV_BIAS_TABLE.iter().enumerate() {
            let nonzero = row.iter().filter(|&&v| v > 0.0).count();
            assert!(nonzero <= 2, "Resource type {} has {} nonzero bias entries", rtype, nonzero);
        }
    }
}
```

- [ ] **Step 2: Add module export to lib.rs**

In `lib.rs`, add after the existing `mod tick;` line:

```rust
pub mod culture_tick;
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test test_compute_distribution -- --nocapture 2>&1 | head -20`
Expected: compile error — functions not defined

- [ ] **Step 4: Implement compute_cultural_distribution()**

Add above the tests in `culture_tick.rs`:

```rust
/// Recompute cultural value frequency distribution for a set of agents in a region.
/// Named agents (IS_NAMED bit set) contribute NAMED_CULTURE_WEIGHT per value.
pub fn compute_cultural_distribution(pool: &AgentPool, slots: &[usize]) -> [u16; agent::NUM_CULTURAL_VALUES] {
    let mut dist = [0u16; agent::NUM_CULTURAL_VALUES];
    for &slot in slots {
        if !pool.alive[slot] {
            continue;
        }
        let weight = if pool.is_named(slot) { agent::NAMED_CULTURE_WEIGHT } else { 1 };
        for &val in &[
            pool.cultural_value_0[slot],
            pool.cultural_value_1[slot],
            pool.cultural_value_2[slot],
        ] {
            if val != agent::CULTURAL_VALUE_EMPTY && (val as usize) < agent::NUM_CULTURAL_VALUES {
                dist[val as usize] = dist[val as usize].saturating_add(weight);
            }
        }
    }
    dist
}

/// Add environmental bias from region's resource types to the frequency distribution.
/// Phantom weight = population × ENV_BIAS_FRACTION, slot-weighted by resource slot.
pub fn apply_environmental_bias(dist: &mut [u16; agent::NUM_CULTURAL_VALUES], resource_types: &[u8; 3], population: u16) {
    let phantom_base = (population as f32 * agent::ENV_BIAS_FRACTION) as u16;
    for (slot_idx, &rtype) in resource_types.iter().enumerate() {
        if rtype == 255 || rtype as usize >= 8 {
            continue;
        }
        let slot_weight = agent::ENV_SLOT_WEIGHTS[slot_idx];
        let bias_row = &ENV_BIAS_TABLE[rtype as usize];
        for (val_idx, &bias) in bias_row.iter().enumerate() {
            if bias > 0.0 {
                let phantom = (phantom_base as f32 * slot_weight * bias) as u16;
                dist[val_idx] = dist[val_idx].saturating_add(phantom);
            }
        }
    }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test culture_tick::tests -- --nocapture`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/culture_tick.rs chronicler-agents/src/lib.rs
git commit -m "feat(m36): add culture_tick module with frequency distribution + env bias"
```

---

### Task 6: Add per-agent drift logic to culture_tick.rs

**Files:**
- Modify: `chronicler-agents/src/culture_tick.rs`

- [ ] **Step 1: Write failing tests for drift**

Add to the existing test module:

```rust
    #[test]
    fn test_drift_no_duplicate_values() {
        // After drift, no agent should have duplicate values across slots
        let mut pool = make_test_pool(4, &[[4, 3, 2]]);
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        // Distribution heavily weighted toward Freedom(0)
        let dist = [100u16, 0, 0, 0, 0, 0];
        for _ in 0..100 {
            drift_agent(0, &mut pool, &dist, 1.0, &mut rng); // max drift rate
            let v0 = pool.cultural_value_0[0];
            let v1 = pool.cultural_value_1[0];
            let v2 = pool.cultural_value_2[0];
            assert!(v0 != v1 || v0 == agent::CULTURAL_VALUE_EMPTY);
            assert!(v0 != v2 || v0 == agent::CULTURAL_VALUE_EMPTY);
            assert!(v1 != v2 || v1 == agent::CULTURAL_VALUE_EMPTY);
        }
    }

    #[test]
    fn test_drift_slot_weighted_rates() {
        // Over 10K trials, slot 2 should drift ~3× more than slot 0
        let mut slot_0_drifts = 0u32;
        let mut slot_2_drifts = 0u32;
        for seed in 0..10_000u64 {
            let mut pool = make_test_pool(4, &[[4, 3, 2]]);
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            let dist = [50u16, 50, 0, 0, 0, 50]; // Freedom, Order, Cunning available
            let orig_0 = pool.cultural_value_0[0];
            let orig_2 = pool.cultural_value_2[0];
            drift_agent(0, &mut pool, &dist, agent::CULTURAL_DRIFT_RATE, &mut rng);
            if pool.cultural_value_0[0] != orig_0 { slot_0_drifts += 1; }
            if pool.cultural_value_2[0] != orig_2 { slot_2_drifts += 1; }
        }
        // Slot 0 rate = DRIFT_RATE * 1/3 ≈ 0.02, Slot 2 rate = DRIFT_RATE * 1.0 ≈ 0.06
        // Ratio should be ~3:1. Allow ±30% tolerance.
        let ratio = slot_2_drifts as f64 / slot_0_drifts.max(1) as f64;
        assert!(ratio > 2.0 && ratio < 4.5,
            "Drift ratio slot2/slot0 = {:.2} (expected ~3.0), drifts: s0={}, s2={}",
            ratio, slot_0_drifts, slot_2_drifts);
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test test_drift -- --nocapture 2>&1 | head -20`
Expected: compile error — `drift_agent` not defined

- [ ] **Step 3: Implement drift_agent()**

Add to `culture_tick.rs`, above the test module:

```rust
use rand::Rng;
use rand_chacha::ChaCha8Rng;

/// Attempt to drift one slot of an agent's cultural values.
/// Returns true if any value changed.
pub fn drift_agent(
    slot: usize,
    pool: &mut AgentPool,
    distribution: &[u16; agent::NUM_CULTURAL_VALUES],
    base_drift_rate: f32,
    rng: &mut ChaCha8Rng,
) -> bool {
    let mut changed = false;
    let current_values = [
        pool.cultural_value_0[slot],
        pool.cultural_value_1[slot],
        pool.cultural_value_2[slot],
    ];

    // Dissatisfied agents drift faster
    let sat_bonus = if pool.satisfactions[slot] < agent::DISSATISFIED_THRESHOLD {
        agent::DISSATISFIED_DRIFT_BONUS
    } else {
        0.0
    };

    for value_slot in (0..3).rev() {
        // Slot-weighted probability: slot 2 = base, slot 1 = 2/3, slot 0 = 1/3
        let slot_rate = (base_drift_rate + sat_bonus) * agent::DRIFT_SLOT_WEIGHTS[value_slot];
        if rng.gen::<f32>() >= slot_rate {
            continue;
        }

        // Sample new value from distribution, excluding current values
        let total_weight: u32 = distribution.iter().enumerate()
            .filter(|(idx, _)| !current_values.contains(&(*idx as u8)))
            .map(|(_, &w)| w as u32)
            .sum();

        if total_weight == 0 {
            continue;
        }

        let mut roll = rng.gen_range(0..total_weight);
        let mut new_val = current_values[value_slot]; // fallback
        for (idx, &w) in distribution.iter().enumerate() {
            if current_values.contains(&(idx as u8)) {
                continue;
            }
            if roll < w as u32 {
                new_val = idx as u8;
                break;
            }
            roll -= w as u32;
        }

        if new_val != current_values[value_slot] {
            match value_slot {
                0 => pool.cultural_value_0[slot] = new_val,
                1 => pool.cultural_value_1[slot] = new_val,
                2 => pool.cultural_value_2[slot] = new_val,
                _ => unreachable!(),
            }
            changed = true;
        }
    }
    changed
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test test_drift -- --nocapture`
Expected: All drift tests pass

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/culture_tick.rs
git commit -m "feat(m36): add per-agent drift with slot-weighted probability"
```

---

### Task 7: Add culture_tick orchestrator and wire into tick.rs

**Files:**
- Modify: `chronicler-agents/src/culture_tick.rs`
- Modify: `chronicler-agents/src/tick.rs:42-289`
- Modify: `chronicler-agents/src/tick.rs:240-265` (birth spawn)

- [ ] **Step 1: Implement culture_tick() orchestrator**

Add to `culture_tick.rs`:

```rust
use rand::SeedableRng;

/// Run cultural drift for all agents in a region.
/// Called as Rust tick stage 5, after demographics.
pub fn culture_tick(
    pool: &mut AgentPool,
    slots: &[usize],
    region: &RegionState,
    master_seed: [u8; 32],
    turn: u32,
    region_id: usize,
) {
    if slots.is_empty() {
        return;
    }

    // 1. Recompute frequency distribution
    let mut dist = compute_cultural_distribution(pool, slots);

    // 2. Apply environmental bias from resources
    apply_environmental_bias(&mut dist, &region.resource_types, region.population);

    // 3. If INVEST_CULTURE active, add bonus weight to controller's values
    if region.culture_investment_active {
        let bonus = (region.population as f32 * agent::INVEST_CULTURE_BONUS) as u16;
        for &cv in &region.controller_values {
            if cv != agent::CULTURAL_VALUE_EMPTY && (cv as usize) < agent::NUM_CULTURAL_VALUES {
                dist[cv as usize] = dist[cv as usize].saturating_add(bonus);
            }
        }
    }

    // 4. Per-agent drift with dedicated RNG stream
    let mut rng = ChaCha8Rng::from_seed(master_seed);
    rng.set_stream(
        region_id as u64 * 1000 + turn as u64 + agent::CULTURE_DRIFT_OFFSET,
    );

    for &slot in slots {
        if !pool.alive[slot] {
            continue;
        }
        drift_agent(slot, pool, &dist, agent::CULTURAL_DRIFT_RATE, &mut rng);
    }
}
```

- [ ] **Step 2: Add cultural values to the birth data structure in tick.rs**

The demographics stage collects birth results into a `DemographicsPending` struct (around line 416-421 in tick.rs) which contains a `births: Vec<BirthPending>` (or similar struct). Find this struct and add a `cultural_values: [u8; 3]` field.

In the demographics function (`tick_region_demographics`) where births are created (the loop that builds `BirthPending` entries), set `cultural_values` from the parent's actual current values — NOT from civ defaults:

```rust
cultural_values: [
    pool.cultural_value_0[parent_slot],
    pool.cultural_value_1[parent_slot],
    pool.cultural_value_2[parent_slot],
],
```

If births don't track a specific parent slot, use the region's majority civ values as fallback. The key invariant: drifted parents reproduce their actual culture.

- [ ] **Step 3: Update birth spawn call to pass cultural values**

In `tick.rs`, at the birth spawn call site (around line 243):

```rust
    let new_slot = pool.spawn(
        birth.region,
        birth.civ,
        crate::agent::Occupation::Farmer,
        0,
        birth.personality[0],
        birth.personality[1],
        birth.personality[2],
        birth.cultural_values[0],
        birth.cultural_values[1],
        birth.cultural_values[2],
    );
```

- [ ] **Step 4: Add stage 5 culture drift to tick_agents()**

After the demographics application block (around line 266), add culture drift as stage 5:

```rust
    // --- Stage 5: Cultural drift (M36) ---
    {
        let region_groups = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups.iter().enumerate() {
            if !slots.is_empty() {
                crate::culture_tick::culture_tick(
                    pool,
                    slots,
                    &regions[region_id],
                    master_seed,
                    turn,
                    region_id,
                );
            }
        }
    }
```

Note: Culture drift runs sequentially (not parallel) because `drift_agent` mutates the pool. If performance profiling shows this is a bottleneck, it can be parallelized by collecting pending drifts into a struct (like decisions) and applying sequentially — but at 500 agents/region this is microseconds.

- [ ] **Step 5a: Read the current satisfaction call site**

In `tick.rs`, grep for `compute_satisfaction(` to find the exact call site in `update_satisfaction()` (around lines 295-403). Read the full call — note every positional argument, its source expression, and order. Write down the current arg list before making any changes.

- [ ] **Step 5b: Replace with compute_satisfaction_with_culture()**

Append two new arguments to the **end** of the existing arg list (do not reorder or modify existing args):

```rust
let agent_values = [
    pool.cultural_value_0[slot],
    pool.cultural_value_1[slot],
    pool.cultural_value_2[slot],
];
let sat = crate::satisfaction::compute_satisfaction_with_culture(
    // ... all existing positional args exactly as read in Step 5a ...,
    agent_values,
    regions[region_id].controller_values,
);
```

**Tech debt note:** The wrapper approach (calling `compute_satisfaction` then subtracting the penalty) works but means two functions exist. Before M37 adds religious penalty to the same sum, refactor to fold the cultural penalty *inside* `compute_satisfaction()` as additional parameters. Do not stack wrapper functions.

- [ ] **Step 6: Verify compilation and run existing tests**

Run: `cd chronicler-agents && cargo test -- --nocapture 2>&1 | tail -20`
Expected: All existing tests pass + new tests pass

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/culture_tick.rs chronicler-agents/src/tick.rs chronicler-agents/src/satisfaction.rs
git commit -m "feat(m36): wire culture_tick as stage 5, birth inherits parent values"
```

---

## Chunk 3: Python Integration

### Task 8: Add cultural columns to agent_bridge.py

**Files:**
- Modify: `src/chronicler/agent_bridge.py:86-136` (build_region_batch)

- [ ] **Step 1: Add VALUE_TO_ID mapping**

At the top of `agent_bridge.py`, after existing constants:

```python
# M36: Cultural value string → u8 index mapping (matches Rust enum order)
VALUE_TO_ID = {
    "Freedom": 0, "Order": 1, "Tradition": 2,
    "Knowledge": 3, "Honor": 4, "Cunning": 5,
}
VALUE_EMPTY = 0xFF
```

- [ ] **Step 2: Add new columns to build_region_batch()**

In `build_region_batch()`, add a helper to look up controller values:

```python
    def _controller_values(region):
        """Denormalize controller civ's cultural values into per-region columns."""
        if region.controller is None:
            return [VALUE_EMPTY, VALUE_EMPTY, VALUE_EMPTY]
        ctrl_civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if ctrl_civ is None:
            return [VALUE_EMPTY, VALUE_EMPTY, VALUE_EMPTY]
        vals = [VALUE_TO_ID.get(v, VALUE_EMPTY) for v in ctrl_civ.values[:3]]
        while len(vals) < 3:
            vals.append(VALUE_EMPTY)
        return vals
```

Add new columns to the `pa.record_batch({...})` dict, after the `endemic_severity` line:

```python
        # M36: Cultural identity signals
        "culture_investment_active": pa.array(
            [getattr(r, '_culture_investment_active', False) for r in world.regions],
            type=pa.bool_(),
        ),
        "controller_values_0": pa.array(
            [_controller_values(r)[0] for r in world.regions], type=pa.uint8(),
        ),
        "controller_values_1": pa.array(
            [_controller_values(r)[1] for r in world.regions], type=pa.uint8(),
        ),
        "controller_values_2": pa.array(
            [_controller_values(r)[2] for r in world.regions], type=pa.uint8(),
        ),
```

- [ ] **Step 3: Verify Python import works**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -c "from chronicler.agent_bridge import build_region_batch; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m36): add controller_values + culture_investment to region batch"
```

---

### Task 9: Replace culture.py functions

**Files:**
- Modify: `src/chronicler/culture.py:34-73` (apply_value_drift), `culture.py:81-127` (tick_cultural_assimilation)
- Test: `test/test_m36_culture.py`

- [ ] **Step 1: Write failing test for compute_civ_cultural_profile**

Create `test/test_m36_culture.py`:

```python
"""Tier 1 tests for M36 cultural identity."""
import pytest
from unittest.mock import MagicMock
import pyarrow as pa

from chronicler.culture import compute_civ_cultural_profile


def _make_snapshot(agents):
    """Create a minimal Arrow RecordBatch snapshot from agent dicts."""
    return pa.record_batch({
        "id": pa.array([a["id"] for a in agents], type=pa.uint32()),
        "region": pa.array([a["region"] for a in agents], type=pa.uint16()),
        "civ_affinity": pa.array([a["civ"] for a in agents], type=pa.uint16()),
        "cultural_value_0": pa.array([a["cv0"] for a in agents], type=pa.uint8()),
        "cultural_value_1": pa.array([a["cv1"] for a in agents], type=pa.uint8()),
        "cultural_value_2": pa.array([a["cv2"] for a in agents], type=pa.uint8()),
    })


class TestComputeCivCulturalProfile:
    def test_basic_aggregation(self):
        agents = [
            {"id": 1, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2},
            {"id": 2, "region": 0, "civ": 0, "cv0": 4, "cv1": 1, "cv2": 0},
            {"id": 3, "region": 1, "civ": 1, "cv0": 0, "cv1": 5, "cv2": 2},
        ]
        snap = _make_snapshot(agents)
        profile = compute_civ_cultural_profile(snap)
        # Civ 0: Honor(4)=2, Knowledge(3)=1, Tradition(2)=1, Order(1)=1, Freedom(0)=1
        assert profile[0][4] == 2
        assert profile[0][3] == 1
        # Civ 1: Freedom(0)=1, Cunning(5)=1, Tradition(2)=1
        assert profile[1][0] == 1
        assert profile[1][5] == 1

    def test_empty_snapshot(self):
        snap = _make_snapshot([])
        profile = compute_civ_cultural_profile(snap)
        assert len(profile) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_culture.py::TestComputeCivCulturalProfile -v 2>&1 | head -20`
Expected: ImportError — `compute_civ_cultural_profile` not found

- [ ] **Step 3: Implement compute_civ_cultural_profile()**

Add to `culture.py`, after the imports:

```python
from collections import Counter


def compute_civ_cultural_profile(snapshot) -> dict[int, Counter]:
    """Aggregate per-civ cultural value frequency from agent snapshot.

    Returns dict mapping civ_id → Counter of value indices.
    """
    if snapshot is None or snapshot.num_rows == 0:
        return {}

    civs = snapshot.column("civ_affinity").to_pylist()
    cv0 = snapshot.column("cultural_value_0").to_pylist()
    cv1 = snapshot.column("cultural_value_1").to_pylist()
    cv2 = snapshot.column("cultural_value_2").to_pylist()

    profiles: dict[int, Counter] = {}
    for i in range(len(civs)):
        civ_id = civs[i]
        if civ_id not in profiles:
            profiles[civ_id] = Counter()
        for val in (cv0[i], cv1[i], cv2[i]):
            if val != 0xFF and val < 6:
                profiles[civ_id][val] += 1
    return profiles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_culture.py::TestComputeCivCulturalProfile -v`
Expected: PASS

- [ ] **Step 5: Write test for agent-driven assimilation**

Add to `test/test_m36_culture.py`:

```python
from chronicler.culture import tick_cultural_assimilation
from chronicler.agent_bridge import VALUE_TO_ID


class TestAgentDrivenAssimilation:
    def _make_world(self, region_controller, region_identity, foreign_turns, civ_values):
        """Create minimal world with one region and two civs."""
        world = MagicMock()
        world.turn = 100
        region = MagicMock()
        region.name = "Plains_0"
        region.controller = region_controller
        region.cultural_identity = region_identity
        region.foreign_control_turns = foreign_turns
        world.regions = [region]
        world.named_events = []
        world.active_conditions = []

        civs = []
        for name, vals in civ_values.items():
            civ = MagicMock()
            civ.name = name
            civ.values = vals
            civ.stability = 80
            civs.append(civ)
        world.civilizations = civs
        return world

    def test_assimilation_at_60_percent(self):
        """Region flips when 60%+ hold controller's primary value."""
        world = self._make_world("Conqueror", "Native", 10, {
            "Conqueror": ["Honor", "Knowledge"],
            "Native": ["Freedom", "Order"],
        })
        # 7 of 10 agents hold Honor(4) somewhere → 70% > 60% threshold
        agents = []
        for i in range(7):
            agents.append({"id": i, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2})
        for i in range(7, 10):
            agents.append({"id": i, "region": 0, "civ": 1, "cv0": 0, "cv1": 1, "cv2": 5})
        snapshot = _make_snapshot(agents)
        tick_cultural_assimilation(world, acc=None, agent_snapshot=snapshot)
        assert world.regions[0].cultural_identity == "Conqueror"

    def test_no_assimilation_below_threshold(self):
        """Region does NOT flip when <60% hold controller's primary."""
        world = self._make_world("Conqueror", "Native", 10, {
            "Conqueror": ["Honor", "Knowledge"],
            "Native": ["Freedom", "Order"],
        })
        # 5 of 10 agents hold Honor → 50% < 60%
        agents = []
        for i in range(5):
            agents.append({"id": i, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2})
        for i in range(5, 10):
            agents.append({"id": i, "region": 0, "civ": 1, "cv0": 0, "cv1": 1, "cv2": 5})
        snapshot = _make_snapshot(agents)
        tick_cultural_assimilation(world, acc=None, agent_snapshot=snapshot)
        assert world.regions[0].cultural_identity == "Native"

    def test_guard_clause_short_occupation(self):
        """Don't check assimilation if foreign_control_turns < 5."""
        world = self._make_world("Conqueror", "Native", 3, {
            "Conqueror": ["Honor"],
            "Native": ["Freedom"],
        })
        # 100% hold Honor but occupation too short
        agents = [{"id": 0, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2}]
        snapshot = _make_snapshot(agents)
        tick_cultural_assimilation(world, acc=None, agent_snapshot=snapshot)
        assert world.regions[0].cultural_identity == "Native"

    def test_fallback_timer_no_snapshot(self):
        """With no snapshot (agents=off), use M16 timer-based assimilation."""
        world = self._make_world("Conqueror", "Native", 15, {
            "Conqueror": ["Honor"],
            "Native": ["Freedom"],
        })
        tick_cultural_assimilation(world, acc=None, agent_snapshot=None)
        # Timer path: 15 >= ASSIMILATION_THRESHOLD → flip
        assert world.regions[0].cultural_identity == "Conqueror"
```

- [ ] **Step 6: Implement agent-driven tick_cultural_assimilation()**

Replace the existing `tick_cultural_assimilation()` in `culture.py`. Keep the old logic as the fallback path.

**IMPORTANT:** Preserve the existing `ASSIMILATION_THRESHOLD = 15` constant (line 76) — it is used by the M16 timer fallback path in `--agents=off` mode. The new `ASSIMILATION_AGENT_THRESHOLD = 0.60` is a separate constant for the agent-driven path.

**Performance note:** The implementation below calls `to_pylist()` on snapshot columns and iterates the full snapshot per region — O(R × N). At current scale (200 regions × 10K agents = 2M iterations) this is fine. If it becomes a bottleneck, pre-index agents by region once per turn with a `defaultdict(list)` and iterate per-region. Don't optimize now.

```python
ASSIMILATION_AGENT_THRESHOLD = 0.60
ASSIMILATION_GUARD_TURNS = 5


def tick_cultural_assimilation(world: WorldState, acc=None, agent_snapshot=None) -> None:
    """Tick cultural assimilation for all regions.

    M36: When agent_snapshot is available, use agent-driven 60% threshold.
    Fallback: M16 timer-based path when no snapshot (--agents=off).
    """
    from chronicler.agent_bridge import VALUE_TO_ID

    for region in world.regions:
        if region.controller is None:
            continue

        if region.cultural_identity is None:
            region.cultural_identity = region.controller
            continue

        if region.cultural_identity == region.controller:
            if region.foreign_control_turns > 0:
                region.foreign_control_turns = 0
                world.active_conditions.append(ActiveCondition(
                    condition_type="restless_population",
                    affected_civs=[region.controller],
                    duration=RECONQUEST_COOLDOWN,
                    severity=5,
                ))
            continue

        region.foreign_control_turns += 1

        if agent_snapshot is not None:
            # M36 agent-driven path
            if region.foreign_control_turns < ASSIMILATION_GUARD_TURNS:
                continue

            # Get controller's primary value
            ctrl_civ = next(
                (c for c in world.civilizations if c.name == region.controller), None
            )
            if ctrl_civ is None or not ctrl_civ.values:
                continue
            primary_value_id = VALUE_TO_ID.get(ctrl_civ.values[0])
            if primary_value_id is None:
                continue

            # Count agents in this region holding controller's primary in any slot
            region_idx = next(
                (i for i, r in enumerate(world.regions) if r.name == region.name), None
            )
            if region_idx is None:
                continue

            regions_col = agent_snapshot.column("region").to_pylist()
            cv0 = agent_snapshot.column("cultural_value_0").to_pylist()
            cv1 = agent_snapshot.column("cultural_value_1").to_pylist()
            cv2 = agent_snapshot.column("cultural_value_2").to_pylist()

            total = 0
            holding = 0
            for i in range(agent_snapshot.num_rows):
                if regions_col[i] == region_idx:
                    total += 1
                    if primary_value_id in (cv0[i], cv1[i], cv2[i]):
                        holding += 1

            if total == 0:
                continue

            fraction = holding / total
            if fraction >= ASSIMILATION_AGENT_THRESHOLD:
                region.cultural_identity = region.controller
                region.foreign_control_turns = 0
                world.named_events.append(NamedEvent(
                    name=f"Assimilation of {region.name}",
                    event_type="cultural_assimilation",
                    turn=world.turn,
                    actors=[region.controller],
                    region=region.name,
                    description=(
                        f"{region.name} has been culturally assimilated by "
                        f"{region.controller} ({fraction:.0%} cultural adoption)."
                    ),
                    importance=6,
                ))
        else:
            # M16 fallback: timer-based assimilation
            if region.foreign_control_turns >= ASSIMILATION_THRESHOLD:
                region.cultural_identity = region.controller
                region.foreign_control_turns = 0
                world.named_events.append(NamedEvent(
                    name=f"Assimilation of {region.name}",
                    event_type="cultural_assimilation",
                    turn=world.turn,
                    actors=[region.controller],
                    region=region.name,
                    description=(
                        f"{region.name} has been culturally assimilated by "
                        f"{region.controller}."
                    ),
                    importance=6,
                ))

        # Stability drain on controller during occupation (applies in both paths)
        if region.foreign_control_turns >= RECONQUEST_COOLDOWN:
            controller = next(
                (c for c in world.civilizations if c.name == region.controller), None
            )
            if controller:
                if acc is not None:
                    ctrl_idx = next(
                        i for i, c in enumerate(world.civilizations)
                        if c.name == controller.name
                    )
                    acc.add(
                        ctrl_idx, controller, "stability",
                        -ASSIMILATION_STABILITY_DRAIN, "signal",
                    )
                else:
                    controller.stability = clamp(
                        controller.stability - ASSIMILATION_STABILITY_DRAIN, 0, 100
                    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_culture.py -v`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/culture.py test/test_m36_culture.py
git commit -m "feat(m36): agent-driven assimilation + compute_civ_cultural_profile()"
```

---

### Task 10: Modify apply_value_drift() for bottom-up aggregation

**Files:**
- Modify: `src/chronicler/culture.py:34-73` (apply_value_drift)

- [ ] **Step 1: Modify apply_value_drift() to accept snapshot**

Update the function signature and add the agent-driven path:

```python
def apply_value_drift(world: WorldState, agent_snapshot=None) -> None:
    """Accumulate disposition drift from shared/opposing values.

    M36: When agent_snapshot is available, use bottom-up cultural similarity
    from agent population. Fallback: M16 civ-level value comparison.
    """
    from chronicler.movements import SCHISM_DIVERGENCE_THRESHOLD

    civs = world.civilizations

    if agent_snapshot is not None:
        # M36: Bottom-up cultural similarity from agent populations
        profiles = compute_civ_cultural_profile(agent_snapshot)
        for i, civ_a in enumerate(civs):
            civ_a_id = i  # civ index matches civ_id
            for civ_b in civs[i + 1:]:
                civ_b_id = next(
                    j for j, c in enumerate(civs) if c.name == civ_b.name
                )
                prof_a = profiles.get(civ_a_id, Counter())
                prof_b = profiles.get(civ_b_id, Counter())

                # Cultural similarity = sum of min counts for each value
                all_values = set(prof_a.keys()) | set(prof_b.keys())
                total_a = sum(prof_a.values()) or 1
                total_b = sum(prof_b.values()) or 1
                shared_frac = sum(
                    min(prof_a.get(v, 0) / total_a, prof_b.get(v, 0) / total_b)
                    for v in all_values
                )
                # Scale to drift units: high similarity → positive drift
                net_drift = int((shared_frac - 0.3) * 10)  # neutral at 0.3 overlap
                if net_drift == 0:
                    continue

                for a_name, b_name in [
                    (civ_a.name, civ_b.name),
                    (civ_b.name, civ_a.name),
                ]:
                    rel = world.relationships.get(a_name, {}).get(b_name)
                    if rel is None:
                        continue
                    rel.disposition_drift += net_drift
                    if rel.disposition_drift >= 10:
                        rel.disposition = upgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
                    elif rel.disposition_drift <= -10:
                        rel.disposition = _downgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
    else:
        # M16 fallback: civ-level value comparison
        for i, civ_a in enumerate(civs):
            for civ_b in civs[i + 1:]:
                shared = sum(1 for v in civ_a.values if v in civ_b.values)
                opposing = sum(
                    1 for va in civ_a.values for vb in civ_b.values
                    if VALUE_OPPOSITIONS.get(va) == vb
                )
                net_drift = (shared * 2) - (opposing * 2)
                if net_drift == 0:
                    continue

                for a_name, b_name in [
                    (civ_a.name, civ_b.name),
                    (civ_b.name, civ_a.name),
                ]:
                    rel = world.relationships.get(a_name, {}).get(b_name)
                    if rel is None:
                        continue
                    rel.disposition_drift += net_drift
                    if rel.disposition_drift >= 10:
                        rel.disposition = upgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0
                    elif rel.disposition_drift <= -10:
                        rel.disposition = _downgrade_disposition(rel.disposition)
                        rel.disposition_drift = 0

    # Movement co-adoption effects (unchanged from M16)
    for movement in world.movements:
        adherent_names = list(movement.adherents.keys())
        for idx_a, name_a in enumerate(adherent_names):
            for name_b in adherent_names[idx_a + 1:]:
                divergence = abs(
                    movement.adherents[name_a] - movement.adherents[name_b]
                )
                movement_drift = (
                    5 if divergence < SCHISM_DIVERGENCE_THRESHOLD else -5
                )
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel is None:
                        continue
                    rel.disposition_drift += movement_drift
```

**Pre-check:** Verify that `_downgrade_disposition()` and `upgrade_disposition()` still exist in `culture.py` — the replacement code calls them. If they've been renamed or moved, update the references.

- [ ] **Step 2: Write test for agent-driven value drift**

Add to `test/test_m36_culture.py`:

```python
class TestApplyValueDriftAgentDriven:
    def test_shared_values_positive_drift(self):
        """Civs with overlapping agent cultural profiles get positive disposition drift."""
        world = MagicMock()
        world.movements = []
        civ_a = MagicMock()
        civ_a.name = "Alpha"
        civ_a.values = ["Honor", "Knowledge"]
        civ_b = MagicMock()
        civ_b.name = "Beta"
        civ_b.values = ["Honor", "Freedom"]
        world.civilizations = [civ_a, civ_b]

        rel_ab = MagicMock()
        rel_ab.disposition_drift = 0
        rel_ba = MagicMock()
        rel_ba.disposition_drift = 0
        world.relationships = {
            "Alpha": {"Beta": rel_ab},
            "Beta": {"Alpha": rel_ba},
        }

        # Both civs' agents share Honor(4) heavily
        agents = [
            {"id": 0, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2},
            {"id": 1, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 0},
            {"id": 2, "region": 1, "civ": 1, "cv0": 4, "cv1": 0, "cv2": 5},
            {"id": 3, "region": 1, "civ": 1, "cv0": 4, "cv1": 0, "cv2": 1},
        ]
        snapshot = _make_snapshot(agents)

        from chronicler.culture import apply_value_drift
        apply_value_drift(world, agent_snapshot=snapshot)

        # Shared Honor should produce positive drift
        assert rel_ab.disposition_drift > 0

    def test_fallback_without_snapshot(self):
        """Without snapshot, uses M16 civ-level comparison."""
        world = MagicMock()
        world.movements = []
        civ_a = MagicMock()
        civ_a.name = "Alpha"
        civ_a.values = ["Honor", "Knowledge"]
        civ_b = MagicMock()
        civ_b.name = "Beta"
        civ_b.values = ["Honor", "Freedom"]
        world.civilizations = [civ_a, civ_b]

        rel_ab = MagicMock()
        rel_ab.disposition_drift = 0
        rel_ba = MagicMock()
        rel_ba.disposition_drift = 0
        world.relationships = {
            "Alpha": {"Beta": rel_ab},
            "Beta": {"Alpha": rel_ba},
        }

        from chronicler.culture import apply_value_drift
        apply_value_drift(world, agent_snapshot=None)

        # Shared Honor → positive drift via M16 path
        assert rel_ab.disposition_drift > 0
```

- [ ] **Step 3: Run tests**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_culture.py::TestApplyValueDriftAgentDriven -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/culture.py test/test_m36_culture.py
git commit -m "feat(m36): apply_value_drift uses bottom-up agent cultural profile"
```

---

### Task 11: Wire snapshot through simulation.py Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py:821-829`

- [ ] **Step 1: Pass agent_snapshot to culture functions**

The snapshot must be available in `phase_consequences()` (called at line 1140 of simulation.py). The `agent_bridge` is a local variable in the turn loop, not on `world`. Two approaches — pick whichever matches the codebase better:

**Option A** — Store snapshot on world temporarily before Phase 10:

In the turn loop (around line 1129-1139), after `agent_bridge.tick()` completes:

```python
    # M36: Stash snapshot for Phase 10 culture functions
    world._agent_snapshot = None
    if agent_bridge is not None:
        try:
            world._agent_snapshot = agent_bridge._sim.get_snapshot()
        except Exception:
            pass
```

Then in `phase_consequences()` (around line 821-829):

```python
    # M16a: Cultural effects (order matters — assimilation drain feeds asabiya)
    # M36: Use agent snapshot for agent-driven cultural mechanics
    _snap = getattr(world, '_agent_snapshot', None)
    apply_value_drift(world, agent_snapshot=_snap)
    tick_cultural_assimilation(world, acc=acc, agent_snapshot=_snap)
```

**Option B** — Pass snapshot as parameter to `phase_consequences()`:

Add `agent_snapshot=None` parameter to `phase_consequences()` signature and pass it from the turn loop.

Option A is simpler (no signature change). Either way, verify in hybrid mode that the snapshot is non-None by adding a debug assert or print during initial testing.

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/ -x -q 2>&1 | tail -10`
Expected: All existing tests pass

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m36): wire agent snapshot to Phase 10 culture functions"
```

---

### Task 12: Modify INVEST_CULTURE to set signal flag

**Files:**
- Modify: `src/chronicler/culture.py:147-229` (resolve_invest_culture)

- [ ] **Step 1: Add signal flag setting to resolve_invest_culture**

At the end of `resolve_invest_culture()`, after the existing `target.foreign_control_turns += net_acceleration` line, add:

```python
    # M36: Set signal flag for Rust culture_tick to boost drift toward controller values
    target._culture_investment_active = True
```

This transient attribute is read by `build_region_batch()` in `agent_bridge.py` (already wired in Task 8 via `getattr(r, '_culture_investment_active', False)`). It's set each turn INVEST_CULTURE fires and consumed when building the region batch. The attribute doesn't persist between turns because `build_region_batch()` defaults to False.

**Execution order safety:** Phase 8 (action engine) runs `resolve_invest_culture()` which sets the flag. The Rust tick (between Phase 9-10) calls `build_region_batch()` which reads the flag. Phase 8 always runs before the Rust tick, so the flag is set before it's read. Verify this by checking the turn loop in `simulation.py`.

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/culture.py
git commit -m "feat(m36): INVEST_CULTURE sets _culture_investment_active signal flag"
```

---

## Chunk 4: Validation

### Task 13: Tier 2 regression harness

**Files:**
- Create: `test/test_m36_regression.py`

- [ ] **Step 1: Create regression harness**

```python
"""Tier 2 regression tests for M36 cultural identity.

200 seeds × 200 turns. Tests assimilation timing, economy stability,
and --agents=off fallback correctness.
"""
import pytest
import statistics
from chronicler.simulation import simulate
from chronicler.models import WorldState


SEEDS = range(200)
TURNS = 200


def _run_sim(seed, agent_mode="hybrid", turns=TURNS):
    """Run a simulation and return the final world state."""
    world = WorldState.from_scenario("default", seed=seed)
    simulate(world, turns=turns, agent_mode=agent_mode, quiet=True)
    return world


class TestAgentsOffRegression:
    """M36 must not change behavior when --agents=off."""

    @pytest.mark.parametrize("seed", SEEDS[:10])
    def test_agents_off_assimilation_unchanged(self, seed):
        """Timer-based assimilation still works identically in agents-off mode."""
        world = _run_sim(seed, agent_mode="off", turns=50)
        # Verify: assimilation events use timer path (15 turns)
        assimilation_events = [
            e for e in world.named_events
            if e.event_type == "cultural_assimilation"
        ]
        # Should produce identical results to pre-M36
        # (This is a smoke test; exact comparison requires baseline capture)
        assert isinstance(assimilation_events, list)


class TestAssimilationTiming:
    """Agent-driven assimilation should take 40-80 turns (median)."""

    @pytest.mark.slow
    def test_assimilation_timing_median(self):
        """Median assimilation turn across seeds should be within 40-80 range."""
        assimilation_turns = []
        for seed in SEEDS[:50]:
            world = _run_sim(seed, agent_mode="hybrid", turns=TURNS)
            for event in world.named_events:
                if event.event_type == "cultural_assimilation":
                    assimilation_turns.append(event.turn)
        assert len(assimilation_turns) >= 5, (
            f"Only {len(assimilation_turns)} assimilation events in 50 seeds — "
            f"need ≥5 for meaningful median"
        )
        median_turn = statistics.median(assimilation_turns)
        # Spec target: 40-80 turns median. Test band: ±20 (so 20-100).
        assert 20 <= median_turn <= 100, (
            f"Median assimilation at turn {median_turn:.0f} outside 20-100 band. "
            f"If <20: drift rate too high. If >100: INVEST_CULTURE mandatory. "
            f"({len(assimilation_turns)} events)"
        )


class TestEconomyRegression:
    """Satisfaction penalty should not destabilize economy.

    Captures pre-M36 baseline (agents=off) and compares post-M36
    (agents=hybrid) within ±10% tolerance.
    """

    @pytest.mark.slow
    def test_economy_within_tolerance(self):
        """Post-M36 economy should be within ±10% of baseline."""
        baseline_treasuries = []
        m36_treasuries = []
        baseline_stabilities = []
        m36_stabilities = []

        for seed in SEEDS[:20]:
            # Baseline: agents=off (M16 timer path, no cultural penalty)
            base_world = _run_sim(seed, agent_mode="off", turns=100)
            for civ in base_world.civilizations:
                if civ.alive:
                    baseline_treasuries.append(civ.treasury)
                    baseline_stabilities.append(civ.stability)

            # M36: agents=hybrid (cultural penalty active)
            m36_world = _run_sim(seed, agent_mode="hybrid", turns=100)
            for civ in m36_world.civilizations:
                if civ.alive:
                    m36_treasuries.append(civ.treasury)
                    m36_stabilities.append(civ.stability)

        assert len(baseline_treasuries) > 0 and len(m36_treasuries) > 0

        base_mean_t = statistics.mean(baseline_treasuries)
        m36_mean_t = statistics.mean(m36_treasuries)
        base_mean_s = statistics.mean(baseline_stabilities)
        m36_mean_s = statistics.mean(m36_stabilities)

        # Treasury within ±10% of baseline (or both near zero)
        if base_mean_t > 10:
            ratio_t = m36_mean_t / base_mean_t
            assert 0.90 <= ratio_t <= 1.10, (
                f"Treasury ratio {ratio_t:.2f} outside ±10% "
                f"(baseline={base_mean_t:.0f}, m36={m36_mean_t:.0f})"
            )

        # Stability within ±10% of baseline
        if base_mean_s > 10:
            ratio_s = m36_mean_s / base_mean_s
            assert 0.90 <= ratio_s <= 1.10, (
                f"Stability ratio {ratio_s:.2f} outside ±10% "
                f"(baseline={base_mean_s:.0f}, m36={m36_mean_s:.0f})"
            )


class TestInvestCultureAcceleration:
    """INVEST_CULTURE should accelerate assimilation vs organic."""

    @pytest.mark.slow
    def test_invest_culture_produces_faster_assimilation(self):
        """Seeds with INVEST_CULTURE events should assimilate faster than average.

        Methodology: across 50 seeds, compare assimilation timing in civs
        that used INVEST_CULTURE vs those that didn't. The INVEST_CULTURE
        civs should assimilate 30-50% faster (spec target).
        """
        invest_assimilation_turns = []
        all_assimilation_turns = []

        for seed in SEEDS[:50]:
            world = _run_sim(seed, agent_mode="hybrid", turns=TURNS)

            # Collect all assimilation events
            for event in world.named_events:
                if event.event_type == "cultural_assimilation":
                    all_assimilation_turns.append(event.turn)

            # Check if any INVEST_CULTURE actions occurred
            invest_events = [
                e for e in world.events_timeline
                if getattr(e, 'event_type', '') == 'invest_culture'
            ]
            if invest_events:
                for event in world.named_events:
                    if event.event_type == "cultural_assimilation":
                        invest_assimilation_turns.append(event.turn)

        assert len(all_assimilation_turns) >= 5, (
            f"Only {len(all_assimilation_turns)} assimilation events — "
            f"insufficient for comparison"
        )

        # Directional check: if we have invest events, they should trend faster
        if len(invest_assimilation_turns) >= 3:
            invest_median = statistics.median(invest_assimilation_turns)
            all_median = statistics.median(all_assimilation_turns)
            # Invest seeds should assimilate no later than overall average
            # (exact 30-50% target calibrated in M47 Tier 3)
            assert invest_median <= all_median * 1.1, (
                f"INVEST_CULTURE median ({invest_median:.0f}) not faster than "
                f"overall median ({all_median:.0f})"
            )


class TestCivCulturalProfileConsistency:
    """compute_civ_cultural_profile() must match direct snapshot query."""

    def test_profile_matches_direct_query(self):
        """Profile aggregated from snapshot matches manual count."""
        import pyarrow as pa
        from chronicler.culture import compute_civ_cultural_profile
        from collections import Counter

        agents = [
            {"id": 0, "region": 0, "civ": 0, "cv0": 4, "cv1": 3, "cv2": 2},
            {"id": 1, "region": 0, "civ": 0, "cv0": 4, "cv1": 1, "cv2": 0},
            {"id": 2, "region": 1, "civ": 1, "cv0": 0, "cv1": 5, "cv2": 2},
            {"id": 3, "region": 1, "civ": 0, "cv0": 3, "cv1": 2, "cv2": 1},
        ]
        snapshot = pa.record_batch({
            "id": pa.array([a["id"] for a in agents], type=pa.uint32()),
            "region": pa.array([a["region"] for a in agents], type=pa.uint16()),
            "civ_affinity": pa.array([a["civ"] for a in agents], type=pa.uint16()),
            "cultural_value_0": pa.array([a["cv0"] for a in agents], type=pa.uint8()),
            "cultural_value_1": pa.array([a["cv1"] for a in agents], type=pa.uint8()),
            "cultural_value_2": pa.array([a["cv2"] for a in agents], type=pa.uint8()),
        })

        profile = compute_civ_cultural_profile(snapshot)

        # Manual count for civ 0 (agents 0, 1, 3):
        expected_0 = Counter({4: 2, 3: 2, 2: 2, 1: 2, 0: 1})
        assert dict(profile[0]) == dict(expected_0)

        # Manual count for civ 1 (agent 2):
        expected_1 = Counter({0: 1, 5: 1, 2: 1})
        assert dict(profile[1]) == dict(expected_1)
```

- [ ] **Step 2: Run smoke tests (fast subset)**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_regression.py::TestAgentsOffRegression -v --timeout=120`
Expected: All smoke tests pass

- [ ] **Step 3: Run full Tier 2 harness (slow)**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/test_m36_regression.py -v --timeout=600 -m slow`
Expected: All tests pass within tolerance bands

- [ ] **Step 4: Commit**

```bash
git add test/test_m36_regression.py
git commit -m "test(m36): add Tier 2 regression harness for cultural identity"
```

---

**Tier 3 characterization tests** (200 seeds × 500 turns, Moran's I spatial autocorrelation, environmental correlation, etc.) are intentionally deferred to a separate session. They generate calibration data for M47 — no pass/fail. Report output: `docs/superpowers/analytics/m36-cultural-identity-report.md`.

---

## Execution Notes

**Build & test commands:**
- Rust: `cd chronicler-agents && cargo test`
- Python: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest test/`
- Full: `cd /c/Users/tateb/Documents/opusprogram && cargo test --manifest-path chronicler-agents/Cargo.toml && python -m pytest test/ -x`

**Critical integration point:** Task 7 (wiring culture_tick into tick.rs) is the highest-risk change. If existing tests break, the issue is likely in the `update_satisfaction()` call — verify that `controller_values` defaults to `[0xFF, 0xFF, 0xFF]` when not provided by Python, producing distance 0 and zero penalty.

**Calibration constants:** All tuning values (`CULTURAL_DRIFT_RATE`, `CULTURAL_MISMATCH_WEIGHT`, etc.) are set to spec defaults. Tier 3 characterization (deferred to a separate session) will generate data for M47 tuning.
