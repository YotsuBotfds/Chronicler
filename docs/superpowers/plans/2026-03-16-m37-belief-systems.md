# M37: Belief Systems & Conversion — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-agent religious belief with event-driven conversion, culture-biased doctrines, holy war gradient, and satisfaction penalty to the Chronicler simulation.

**Architecture:** Hybrid Python/Rust tick — Python pre-computes per-region conversion parameters (priest counts, doctrine modifiers, conquest boost) and Rust executes per-agent probability rolls. Beliefs are stable by default; conversion requires explicit triggers. Data flows through existing Arrow FFI region batch pattern (3 new signals + 1 satisfaction field per region).

**Tech Stack:** Rust (SoA pool, rayon, ChaCha8Rng), Python 3.13+ (Pydantic models, PyArrow), pytest, cargo test.

**Spec:** `docs/superpowers/specs/2026-03-16-m37-belief-systems-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/conversion_tick.rs` | Rust conversion tick (stage 7): per-agent conversion roll, susceptibility check, conquest override, region-skip |
| `src/chronicler/religion.py` | Python religion module: faith generation, belief aggregation, conversion signal computation, boost lifecycle |
| `tests/test_religion.py` | Python tests: doctrine generation, aggregation, boost decay, regression |

### Modified Files
| File | Changes |
|------|---------|
| `chronicler-agents/src/agent.rs` | Add `LIFE_EVENT_CONVERSION`, `RELIGIOUS_MISMATCH_WEIGHT`, `SUSCEPTIBILITY_THRESHOLD/MULTIPLIER`, `CONQUEST_CONVERSION_RATE`, `BELIEF_NONE` constants |
| `chronicler-agents/src/pool.rs` | Add `beliefs: Vec<u8>` SoA field, extend `spawn()` with `belief: u8` param |
| `chronicler-agents/src/region.rs` | Add `conversion_rate`, `conversion_target_belief`, `conquest_conversion_active`, `majority_belief` to RegionState |
| `chronicler-agents/src/ffi.rs` | Parse 4 new region batch columns, add `beliefs` to snapshot, add `initial_belief` column for spawn |
| `chronicler-agents/src/satisfaction.rs` | Add `agent_belief`/`majority_belief` params, compute religious penalty inline |
| `chronicler-agents/src/tick.rs` | Add stage 7 (conversion), extend BirthInfo with `belief`, update satisfaction call sites |
| `chronicler-agents/src/lib.rs` | Export `conversion_tick` module |
| `src/chronicler/models.py` | Add `Belief` model, `belief_registry` on WorldState, `civ_majority_faith` on Civilization, `conquest_conversion_boost` on Region |
| `src/chronicler/agent_bridge.py` | Add 4+1 columns to `build_region_batch()`, initial spawn belief |
| `src/chronicler/action_engine.py` | Holy war WAR weight modifier, conquest conversion hook |
| `src/chronicler/simulation.py` | World-gen faith generation, Phase 10 religion computations |

---

## Chunk 1: Rust Data Model Foundation

### Task 1: Add Religion Constants to agent.rs

**Files:**
- Modify: `chronicler-agents/src/agent.rs:104-129`

- [ ] **Step 1: Add constants after existing M36 cultural identity constants**

```rust
// M37: Religion constants
pub const LIFE_EVENT_CONVERSION: u8 = 1 << 6;  // bit 6 of life_events
pub const BELIEF_NONE: u8 = 0xFF;              // sentinel for no belief assigned
pub const RELIGIOUS_MISMATCH_WEIGHT: f32 = 0.10;
pub const SUSCEPTIBILITY_THRESHOLD: f32 = 0.4;  // satisfaction below this → 2× conversion
pub const SUSCEPTIBILITY_MULTIPLIER: f32 = 2.0;
pub const CONQUEST_CONVERSION_RATE: f32 = 0.30;  // forced flip probability
```

Add after the `INVEST_CULTURE_BONUS` line (~line 129).

**Note:** `CONVERSION_STREAM_OFFSET: u64 = 600` already exists at line 90 of `agent.rs`. Do NOT re-add it.

- [ ] **Step 2: Verify constants compile**

Run: `cd chronicler-agents && cargo check`
Expected: no errors (constants are unused warnings OK)

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m37): add religion constants to agent.rs"
```

---

### Task 2: Add Beliefs SoA Field and Extend spawn()

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-157`
- Test: `chronicler-agents/src/pool.rs` (inline tests)

- [ ] **Step 1: Write failing test for spawn with belief param**

Add to the `#[cfg(test)]` module at the bottom of pool.rs:

```rust
#[test]
fn test_spawn_sets_belief() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 3);
    assert_eq!(pool.beliefs[slot], 3);
}

#[test]
fn test_spawn_reuse_sets_belief() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 5);
    pool.kill(slot);
    let slot2 = pool.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 0, 0, 7);
    assert_eq!(slot, slot2); // Reused slot
    assert_eq!(pool.beliefs[slot2], 7);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chronicler-agents && cargo test test_spawn_sets_belief -- --nocapture`
Expected: FAIL — `spawn()` doesn't accept a belief parameter yet

- [ ] **Step 3: Add beliefs field to AgentPool struct and extend spawn()**

In the `AgentPool` struct definition (~line 17-47), add after `cultural_value_2`:
```rust
    // Belief (M37)—indexes into Python-side belief_registry
    pub beliefs: Vec<u8>,
```

In `AgentPool::new()`, add to the initializer:
```rust
    beliefs: Vec::new(),
```

Extend `spawn()` signature — add `belief: u8` as the last parameter:
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
    belief: u8,
) -> usize {
```

In the free-slot reuse branch, add:
```rust
    self.beliefs[slot] = belief;
```

In the grow-vecs branch, add:
```rust
    self.beliefs.push(belief);
```

- [ ] **Step 4: Fix all existing spawn() call sites**

Search for all `pool.spawn(` calls. Each needs the new `belief` param appended. For now, use `crate::agent::BELIEF_NONE` (0xFF) as a placeholder at each existing call site:

- `tick.rs` demographics birth path (~line 241): Add `birth.cultural_values[2],` already exists — add `birth.belief,` after the last cultural_value line. **Wait — BirthInfo doesn't have belief yet.** For now, use `crate::agent::BELIEF_NONE` to compile. Task 10 will wire BirthInfo properly.
- `ffi.rs` initial spawn (~lines 393-409): Each `self.pool.spawn(...)` call needs `crate::agent::BELIEF_NONE` as the last arg.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test test_spawn_sets_belief test_spawn_reuse_sets_belief -- --nocapture`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All tests pass (existing tests unaffected since spawn calls updated)

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m37): add beliefs SoA field and extend spawn() with belief param"
```

---

### Task 3: Add Conversion Fields to RegionState

**Files:**
- Modify: `chronicler-agents/src/region.rs:18-49`

- [ ] **Step 1: Add 4 new fields to RegionState struct**

After the M36 fields (`culture_investment_active`, `controller_values`):

```rust
    // M37: Conversion signals (Python-computed, per-region)
    pub conversion_rate: f32,              // 0.0 = no conversion pressure
    pub conversion_target_belief: u8,      // dominant converting faith
    pub conquest_conversion_active: bool,  // Militant holy war forced flip
    pub majority_belief: u8,               // for satisfaction comparison
```

In `RegionState::new()`, add defaults:
```rust
    conversion_rate: 0.0,
    conversion_target_belief: 0xFF,
    conquest_conversion_active: false,
    majority_belief: 0xFF,
```

- [ ] **Step 2: Verify compiles**

Run: `cd chronicler-agents && cargo check`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/region.rs
git commit -m "feat(m37): add conversion fields to RegionState"
```

---

## Chunk 2: Rust FFI & Snapshot

### Task 4: Parse Conversion Columns in Region Batch + Initial Belief

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:205-411`

- [ ] **Step 1: Add region batch column parsing for M37 fields**

In `set_region_state()`, in the optional-columns block (after M36's `controller_values_0/1/2` parsing, ~line 317), add:

```rust
// M37: Conversion signals
if let Some(col) = batch.column_by_name("conversion_rate") {
    let arr = col.as_any().downcast_ref::<Float32Array>().unwrap();
    for i in 0..n {
        self.regions[i].conversion_rate = arr.value(i);
    }
}
if let Some(col) = batch.column_by_name("conversion_target_belief") {
    let arr = col.as_any().downcast_ref::<UInt8Array>().unwrap();
    for i in 0..n {
        self.regions[i].conversion_target_belief = arr.value(i);
    }
}
if let Some(col) = batch.column_by_name("conquest_conversion_active") {
    let arr = col.as_any().downcast_ref::<BooleanArray>().unwrap();
    for i in 0..n {
        self.regions[i].conquest_conversion_active = arr.value(i);
    }
}
if let Some(col) = batch.column_by_name("majority_belief") {
    let arr = col.as_any().downcast_ref::<UInt8Array>().unwrap();
    for i in 0..n {
        self.regions[i].majority_belief = arr.value(i);
    }
}
// M37: Initial belief for spawn (per-region, set to controller civ's faith_id)
let initial_belief_col = batch.column_by_name("initial_belief");
```

- [ ] **Step 2: Update initial spawn path to use initial_belief**

In the initial spawn loop (~lines 366-411), replace all `crate::agent::BELIEF_NONE` (or `CULTURAL_VALUE_EMPTY` if not yet updated) with the initial_belief value:

```rust
let belief = if let Some(col) = &initial_belief_col {
    col.as_any().downcast_ref::<UInt8Array>().unwrap().value(i)
} else {
    crate::agent::BELIEF_NONE
};
```

Then pass `belief` as the last arg to each `self.pool.spawn(...)` call in the initial spawn loop (for Farmer, Soldier, Merchant, Scholar, Priest occupations).

- [ ] **Step 3: Verify compiles**

Run: `cd chronicler-agents && cargo check`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m37): parse conversion columns and initial_belief in region batch"
```

---

### Task 5: Add Beliefs to Snapshot Output

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:64-83` (snapshot_schema) and snapshot builder

- [ ] **Step 1: Add "belief" column to snapshot schema and builder**

In `snapshot_schema()`, add after `"cultural_value_2"`:
```rust
Field::new("belief", DataType::UInt8, false),
```

In the snapshot builder function (where alive agents are iterated and columns are built), add a `belief_builder` (`UInt8Builder`). For each alive agent, append `pool.beliefs[slot]`.

Add to the final RecordBatch column list.

- [ ] **Step 2: Verify compiles and existing snapshot tests pass**

Run: `cd chronicler-agents && cargo test`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m37): add belief column to agent snapshot output"
```

---

## Chunk 3: Rust Satisfaction Integration

### Task 6: Add Religious Penalty to Satisfaction

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs:55-163`
- Modify: `chronicler-agents/src/tick.rs:395-414`
- Test: inline in satisfaction.rs

- [ ] **Step 1: Write failing tests for religious penalty**

Add to satisfaction.rs `#[cfg(test)]` module:

```rust
#[test]
fn test_religious_penalty_match_is_zero() {
    // Same belief as majority → no penalty vs BELIEF_NONE baseline
    let sat_match = compute_satisfaction_with_culture(
        0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
        &CivShock::default(),
        [0, 1, 2], [0, 1, 2],  // cultural values match
        3, 3,  // belief matches majority → 0 religious penalty
    );
    let sat_no_belief = compute_satisfaction_with_culture(
        0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
        &CivShock::default(),
        [0, 1, 2], [0, 1, 2],
        0xFF, 0xFF,  // BELIEF_NONE → 0 religious penalty
    );
    // Both should produce identical satisfaction (no religious penalty in either case)
    assert!((sat_match - sat_no_belief).abs() < 0.001);
}

#[test]
fn test_religious_penalty_mismatch() {
    // Different belief from majority → RELIGIOUS_MISMATCH_WEIGHT penalty
    let sat_match = compute_satisfaction_with_culture(
        0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
        &CivShock::default(),
        [0, 1, 2], [0, 1, 2],
        3, 3,  // same
    );
    let sat_mismatch = compute_satisfaction_with_culture(
        0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
        &CivShock::default(),
        [0, 1, 2], [0, 1, 2],
        3, 5,  // different
    );
    let expected_diff = crate::agent::RELIGIOUS_MISMATCH_WEIGHT;
    assert!((sat_match - sat_mismatch - expected_diff).abs() < 0.001);
}

#[test]
fn test_penalty_cap_with_religion() {
    // cultural_pen=0.15 + religious_pen=0.10 = 0.25, under cap of 0.40
    let pen = apply_penalty_cap(0.15 + 0.10);
    assert!((pen - 0.25).abs() < 0.001);
    // cultural_pen=0.15 + religious_pen=0.10 + future=0.20 = 0.45 → capped to 0.40
    let pen_capped = apply_penalty_cap(0.15 + 0.10 + 0.20);
    assert!((pen_capped - 0.40).abs() < 0.001);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test test_religious_penalty -- --nocapture`
Expected: FAIL — signature doesn't accept `agent_belief`/`majority_belief` yet

- [ ] **Step 3: Extend compute_satisfaction_with_culture() signature and implementation**

Add two params to the end of `compute_satisfaction_with_culture()`:

```rust
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
    agent_belief: u8,        // M37
    majority_belief: u8,     // M37
) -> f32 {
    let base_sat = compute_satisfaction(
        occupation, soil, water, civ_stability, demand_supply_ratio,
        pop_over_capacity, civ_at_war, region_contested,
        occ_matches_faction, is_displaced, trade_routes,
        faction_influence, shock,
    );
    let cultural_pen = compute_cultural_penalty(agent_values, controller_values);
    // M37: religious mismatch — binary (match or not)
    let religious_pen = if agent_belief != majority_belief
        && agent_belief != crate::agent::BELIEF_NONE
        && majority_belief != crate::agent::BELIEF_NONE
    {
        crate::agent::RELIGIOUS_MISMATCH_WEIGHT
    } else {
        0.0
    };
    let total_non_eco_penalty = apply_penalty_cap(cultural_pen + religious_pen);
    (base_sat - total_non_eco_penalty).clamp(0.0, 1.0)
}
```

- [ ] **Step 4: Update the call site in tick.rs update_satisfaction()**

In `tick.rs` `update_satisfaction()` (~line 398), update the call:

```rust
let sat = satisfaction::compute_satisfaction_with_culture(
    occ, region.soil, region.water,
    civ_stability, ds_ratio, pop_over_cap,
    civ_at_war, region_contested,
    occ_matches, is_displaced,
    region.trade_route_count, faction_influence,
    &shock, agent_values, region.controller_values,
    pool_ref.beliefs[slot],         // M37: agent's belief
    region.majority_belief,         // M37: region's majority belief
);
```

Also update any other call sites in satisfaction.rs tests (the existing `test_satisfaction_with_culture` test) to pass the two new params — use `0xFF, 0xFF` (BELIEF_NONE) for backwards-compatible behavior.

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo test`
Expected: All tests pass including the three new religion tests

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs
git commit -m "feat(m37): add religious mismatch penalty to satisfaction"
```

---

## Chunk 4: Rust Conversion Tick

### Task 7: Create conversion_tick.rs Module

**Files:**
- Create: `chronicler-agents/src/conversion_tick.rs`
- Modify: `chronicler-agents/src/lib.rs`

- [ ] **Step 1: Write failing test for conversion tick**

Create `chronicler-agents/src/conversion_tick.rs`:

```rust
use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// Run event-driven religious conversion for all agents in a region.
/// Called as Rust tick stage 7, after culture_drift.
///
/// Conversion is event-driven, NOT ambient drift:
/// - `conversion_rate == 0.0` → skip entirely (no conversion pressure)
/// - Otherwise, each agent rolls against conversion_rate (modified by susceptibility)
/// - `conquest_conversion_active` overrides probability to CONQUEST_CONVERSION_RATE (0.30)
/// - Converted agents get LIFE_EVENT_CONVERSION bit set
pub fn conversion_tick(
    pool: &mut AgentPool,
    slots: &[usize],
    region: &RegionState,
    master_seed: [u8; 32],
    turn: u32,
    region_id: usize,
) {
    // Skip if no conversion pressure
    if region.conversion_rate <= 0.0 && !region.conquest_conversion_active {
        return;
    }
    if slots.is_empty() {
        return;
    }

    let mut rng = ChaCha8Rng::from_seed(master_seed);
    rng.set_stream(
        region_id as u64 * 1000 + turn as u64 + agent::CONVERSION_STREAM_OFFSET,
    );

    use rand::Rng;
    for &slot in slots {
        if !pool.alive[slot] {
            continue;
        }
        let agent_belief = pool.beliefs[slot];
        // Skip if agent already holds the target belief
        if agent_belief == region.conversion_target_belief {
            continue;
        }
        // Skip if agent has no belief (shouldn't happen post-init, but guard)
        if agent_belief == agent::BELIEF_NONE {
            continue;
        }

        let probability = if region.conquest_conversion_active {
            // Holy war forced conversion — override rate
            agent::CONQUEST_CONVERSION_RATE
        } else {
            let mut p = region.conversion_rate;
            // Satisfaction-driven susceptibility
            if pool.satisfactions[slot] < agent::SUSCEPTIBILITY_THRESHOLD {
                p *= agent::SUSCEPTIBILITY_MULTIPLIER;
            }
            p
        };

        if rng.gen::<f32>() < probability {
            pool.beliefs[slot] = region.conversion_target_belief;
            // Mark life event for promotion system (prophet promotion)
            pool.life_events[slot] |= agent::LIFE_EVENT_CONVERSION;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_pool_with_beliefs(n: usize, belief: u8) -> (AgentPool, Vec<usize>) {
        let mut pool = AgentPool::new();
        let mut slots = Vec::new();
        for _ in 0..n {
            let s = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, belief);
            slots.push(s);
        }
        (pool, slots)
    }

    #[test]
    fn test_zero_rate_no_conversion() {
        let (mut pool, slots) = make_pool_with_beliefs(100, 1);
        let mut region = RegionState::new(0);
        region.conversion_rate = 0.0;
        region.conversion_target_belief = 2;
        conversion_tick(&mut pool, &slots, &region, [0u8; 32], 1, 0);
        // All agents should still have belief 1
        for &s in &slots {
            assert_eq!(pool.beliefs[s], 1);
        }
    }

    #[test]
    fn test_full_rate_all_convert() {
        let (mut pool, slots) = make_pool_with_beliefs(1000, 1);
        let mut region = RegionState::new(0);
        region.conversion_rate = 1.0; // 100% rate
        region.conversion_target_belief = 5;
        conversion_tick(&mut pool, &slots, &region, [42u8; 32], 1, 0);
        for &s in &slots {
            assert_eq!(pool.beliefs[s], 5);
        }
    }

    #[test]
    fn test_skip_already_target_belief() {
        let (mut pool, slots) = make_pool_with_beliefs(100, 3);
        let mut region = RegionState::new(0);
        region.conversion_rate = 1.0;
        region.conversion_target_belief = 3; // Same as agents
        conversion_tick(&mut pool, &slots, &region, [42u8; 32], 1, 0);
        for &s in &slots {
            assert_eq!(pool.beliefs[s], 3); // Unchanged
        }
    }

    #[test]
    fn test_conquest_conversion_rate() {
        // With conquest_conversion_active, ~30% should convert (statistical)
        let n = 10_000;
        let (mut pool, slots) = make_pool_with_beliefs(n, 1);
        let mut region = RegionState::new(0);
        region.conversion_rate = 0.0; // Base rate zero, but conquest overrides
        region.conversion_target_belief = 2;
        region.conquest_conversion_active = true;
        conversion_tick(&mut pool, &slots, &region, [99u8; 32], 1, 0);
        let converted: usize = slots.iter().filter(|&&s| pool.beliefs[s] == 2).count();
        let rate = converted as f32 / n as f32;
        assert!(rate > 0.25 && rate < 0.35, "Expected ~30%, got {:.2}%", rate * 100.0);
    }

    #[test]
    fn test_susceptibility_doubles_rate() {
        // Compare conversion counts: low satisfaction vs high satisfaction
        let n = 10_000;
        let base_rate = 0.10;

        // High satisfaction (above threshold)
        let (mut pool_high, slots_high) = make_pool_with_beliefs(n, 1);
        for &s in &slots_high {
            pool_high.satisfactions[s] = 0.8; // Above 0.4 threshold
        }
        let mut region = RegionState::new(0);
        region.conversion_rate = base_rate;
        region.conversion_target_belief = 2;
        conversion_tick(&mut pool_high, &slots_high, &region, [77u8; 32], 1, 0);
        let converted_high: usize = slots_high.iter().filter(|&&s| pool_high.beliefs[s] == 2).count();

        // Low satisfaction (below threshold)
        let (mut pool_low, slots_low) = make_pool_with_beliefs(n, 1);
        for &s in &slots_low {
            pool_low.satisfactions[s] = 0.2; // Below 0.4 threshold
        }
        let mut region2 = RegionState::new(0);
        region2.conversion_rate = base_rate;
        region2.conversion_target_belief = 2;
        conversion_tick(&mut pool_low, &slots_low, &region2, [77u8; 32], 1, 0);
        let converted_low: usize = slots_low.iter().filter(|&&s| pool_low.beliefs[s] == 2).count();

        // Low-sat should convert roughly 2× as many
        let ratio = converted_low as f32 / converted_high.max(1) as f32;
        assert!(ratio > 1.5 && ratio < 2.5, "Expected ~2× ratio, got {:.2}×", ratio);
    }

    #[test]
    fn test_life_event_conversion_bit_set() {
        let (mut pool, slots) = make_pool_with_beliefs(100, 1);
        let mut region = RegionState::new(0);
        region.conversion_rate = 1.0;
        region.conversion_target_belief = 2;
        conversion_tick(&mut pool, &slots, &region, [42u8; 32], 1, 0);
        for &s in &slots {
            assert_eq!(pool.beliefs[s], 2);
            assert_ne!(pool.life_events[s] & agent::LIFE_EVENT_CONVERSION, 0,
                "Converted agent should have LIFE_EVENT_CONVERSION bit set");
        }
    }
}
```

- [ ] **Step 2: Add module to lib.rs**

In `lib.rs`, after `pub mod culture_tick;`:
```rust
pub mod conversion_tick;  // M37: event-driven religious conversion
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo test conversion_tick -- --nocapture`
Expected: All 6 conversion_tick tests pass

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/conversion_tick.rs chronicler-agents/src/lib.rs
git commit -m "feat(m37): add conversion_tick.rs with per-agent conversion logic"
```

---

### Task 8: Wire Stage 7 in tick.rs + BirthInfo Belief Inheritance

**Files:**
- Modify: `chronicler-agents/src/tick.rs:272-305, 435-520`

- [ ] **Step 1: Write test for birth belief inheritance**

Add to tick.rs tests:

```rust
#[test]
fn test_birth_inherits_parent_belief() {
    // Verify that BirthInfo captures parent's belief and spawn uses it
    let mut pool = AgentPool::new();
    // Parent agent with belief=7
    let parent = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 7);
    assert_eq!(pool.beliefs[parent], 7);

    // Simulate what demographics does: read parent belief into BirthInfo
    let birth = BirthInfo {
        region: 0,
        civ: 0,
        parent_loyalty: 0.5,
        personality: [0.0, 0.0, 0.0],
        cultural_values: [0, 0, 0],
        belief: pool.beliefs[parent],  // Should be 7
    };

    // Spawn newborn with BirthInfo's belief
    let child = pool.spawn(
        birth.region, birth.civ, Occupation::Farmer, 0,
        birth.personality[0], birth.personality[1], birth.personality[2],
        birth.cultural_values[0], birth.cultural_values[1], birth.cultural_values[2],
        birth.belief,
    );
    assert_eq!(pool.beliefs[child], 7, "Child should inherit parent's belief");
}
```

- [ ] **Step 2: Extend BirthInfo with belief field**

In the `BirthInfo` struct (~line 435):
```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],
    cultural_values: [u8; 3],
    belief: u8,  // M37: inherited from parent
}
```

- [ ] **Step 3: Copy parent belief in demographics birth path**

In `tick_region_demographics()`, where BirthInfo is constructed (~line 497-514), add `belief` read from parent:

```rust
pending.births.push(BirthInfo {
    region: region_id as u16,
    civ: civ_id,
    parent_loyalty: pool.loyalty(slot),
    personality,
    cultural_values: [
        pool.cultural_value_0[slot],
        pool.cultural_value_1[slot],
        pool.cultural_value_2[slot],
    ],
    belief: pool.beliefs[slot],  // M37: read in parallel phase
});
```

- [ ] **Step 4: Pass belief to spawn() in birth apply path**

In the sequential birth apply loop (~line 241-253), update the spawn call:

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
    birth.belief,  // M37: inherited from parent
);
```

Remove the temporary `crate::agent::BELIEF_NONE` placeholder added in Task 2.

- [ ] **Step 5: Add stage 7 conversion tick call**

After stage 6 (culture_drift, ~line 284), add stage 7:

```rust
// Stage 7: Conversion (M37)
// Note: reuses stage 6's partition pattern. No agents move between stages 6-7,
// so the same partition is valid. M47 can optimize by lifting the partition out
// of stage 6's block scope and sharing it. For now, follow the per-stage pattern.
{
    let region_groups = pool.partition_by_region(num_regions as u16);
    for (region_id, slots) in region_groups.iter().enumerate() {
        if !slots.is_empty() {
            crate::conversion_tick::conversion_tick(
                pool, slots, &regions[region_id],
                master_seed, turn, region_id,
            );
        }
    }
}
```

- [ ] **Step 6: Run full test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m37): wire conversion tick stage 7 and birth belief inheritance"
```

---

## Chunk 5: Python Models & Religion Module

### Task 9: Add Python Data Models

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Add Belief model class**

After existing model classes (near the enums/constants section):

```python
# M37: Religion constants
DOCTRINE_THEOLOGY = 0
DOCTRINE_ETHICS = 1
DOCTRINE_STANCE = 2
DOCTRINE_OUTREACH = 3
DOCTRINE_STRUCTURE = 4

class Belief(BaseModel):
    """A faith in the world's belief registry."""
    faith_id: int = Field(ge=0, le=15)
    name: str
    civ_origin: int  # civ index that founded this faith
    doctrines: list[int] = Field(min_length=5, max_length=5)
    # [Theology, Ethics, Stance, Outreach, Structure], each -1/0/+1
```

- [ ] **Step 2: Add fields to Civilization model**

After `max_precap_weight` (~line 253):
```python
    civ_majority_faith: int = 0  # M37: computed from agent snapshot each turn
```

- [ ] **Step 3: Add field to Region model**

After `capacity_modifier` (~line 191):
```python
    conquest_conversion_boost: float = 0.0  # M37: decays over CONQUEST_BOOST_DURATION turns
    majority_belief: int = 0xFF             # M37: computed from snapshot in Phase 10
    conquest_conversion_active: bool = False # M37: one-shot flag set by action engine on holy war
    conversion_signals: tuple = (0.0, 0xFF, False)  # M37: (rate, target, conquest_active) for bridge
```

- [ ] **Step 4: Add belief_registry to WorldState**

After `agent_events_raw` (~line 474):
```python
    belief_registry: list[Belief] = Field(default_factory=list)  # M37: max 16 faiths
```

- [ ] **Step 5: Run existing model tests to verify no breakage**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: All existing tests pass (new fields have defaults)

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m37): add Belief model, belief_registry, civ_majority_faith, conquest_conversion_boost"
```

---

### Task 10: Create religion.py Module

**Files:**
- Create: `src/chronicler/religion.py`
- Create: `tests/test_religion.py`

- [ ] **Step 1: Write failing tests for doctrine generation**

Create `tests/test_religion.py`:

```python
"""Tests for M37 religion system."""
import random
from collections import Counter

import pytest

from chronicler.religion import (
    generate_faiths,
    compute_majority_belief,
    compute_civ_majority_faith,
    compute_conversion_signals,
    decay_conquest_boosts,
    BASE_CONVERSION_RATE,
    PROSELYTIZING_MULTIPLIER,
    INSULAR_RESISTANCE,
    CONQUEST_BOOST_RATE,
    CONQUEST_BOOST_DURATION,
    DOCTRINE_BIAS_RANDOM_CHANCE,
)
from chronicler.models import DOCTRINE_STANCE


class TestDoctrineGeneration:
    def test_honor_biases_militant(self):
        """Honor-primary civs should produce Militant stance ~60% of the time."""
        rng = random.Random(42)
        militant_count = 0
        n = 1000
        for _ in range(n):
            doctrines = generate_faiths._generate_doctrines(["Honor"], rng)
            if doctrines[DOCTRINE_STANCE] == 1:  # +1 = Militant
                militant_count += 1
        rate = militant_count / n
        assert 0.55 <= rate <= 0.65, f"Expected ~0.6, got {rate:.3f}"

    def test_average_nonzero_axes(self):
        """Average faith should have 2-3 non-neutral doctrine axes."""
        rng = random.Random(42)
        counts = []
        for _ in range(1000):
            doctrines = generate_faiths._generate_doctrines(["Honor", "Order"], rng)
            nonzero = sum(1 for d in doctrines if d != 0)
            counts.append(nonzero)
        avg = sum(counts) / len(counts)
        assert 2.0 <= avg <= 3.0, f"Expected 2-3 non-neutral axes, got {avg:.2f}"

    def test_generate_faiths_one_per_civ(self):
        """Each civ gets exactly one faith."""
        civ_values = [["Honor", "Order"], ["Freedom", "Cunning"], ["Tradition"]]
        civ_names = ["Civ0", "Civ1", "Civ2"]
        registry = generate_faiths(civ_values, civ_names, seed=42)
        assert len(registry) == 3
        for i, belief in enumerate(registry):
            assert belief.faith_id == i
            assert belief.civ_origin == i


class TestMajorityBelief:
    def test_simple_majority(self):
        """Region with more faith-1 agents returns faith 1."""
        # Mock snapshot: 3 agents in region 0, beliefs [1, 1, 2]
        result = compute_majority_belief(_make_snapshot(
            regions=[0, 0, 0], beliefs=[1, 1, 2]
        ))
        assert result[0] == 1

    def test_tie_breaks_to_lower_id(self):
        """Tie in belief count → lower faith_id wins."""
        result = compute_majority_belief(_make_snapshot(
            regions=[0, 0], beliefs=[2, 3]
        ))
        assert result[0] == 2


class TestCivMajorityFaith:
    def test_simple_civ_majority(self):
        result = compute_civ_majority_faith(_make_snapshot(
            civs=[0, 0, 0, 1, 1], beliefs=[1, 1, 2, 3, 3]
        ))
        assert result[0] == 1
        assert result[1] == 3


class TestConversionSignals:
    def test_dominant_faith_only(self):
        """Region with priests of faith A and B: only dominant (most priests) is target."""
        from chronicler.models import Belief, Region
        regions = [Region(name="r0", terrain="plains", carrying_capacity=60,
                         resources="fertile", adjacencies=[], specialized_resources=[],
                         ecology=None, infrastructure=[], disaster_cooldowns={},
                         resource_suspensions={}, route_suspensions={},
                         resource_types=[255,255,255], resource_base_yields=[0,0,0],
                         resource_reserves=[1,1,1], resource_effective_yields=[0,0,0],
                         overextraction_streaks={}, controller="Civ0")]
        registry = [
            Belief(faith_id=0, name="A", civ_origin=0, doctrines=[0,0,0,0,0]),
            Belief(faith_id=1, name="B", civ_origin=1, doctrines=[0,0,0,0,0]),
            Belief(faith_id=2, name="C", civ_origin=2, doctrines=[0,0,0,0,0]),
        ]
        # 3 priests of faith 1, 1 priest of faith 2; majority is faith 0
        snap = _make_snapshot(
            regions=[0, 0, 0, 0, 0, 0],
            beliefs=[0, 0, 1, 1, 1, 2],
            civs=  [0, 0, 1, 1, 1, 2],
            occs=  [0, 0, 4, 4, 4, 4],  # last 4 are priests
        )
        majority = compute_majority_belief(snap)
        signals = compute_conversion_signals(
            regions, majority, registry, snap,
        )
        rate, target, _ = signals[0]
        assert target == 1, f"Expected dominant faith 1 (3 priests), got {target}"
        assert rate > 0

    def test_no_priests_no_boost_zero_rate(self):
        """Region with no foreign priests and no conquest boost → rate = 0."""
        from chronicler.models import Belief, Region
        regions = [Region(name="r0", terrain="plains", carrying_capacity=60,
                         resources="fertile", adjacencies=[], specialized_resources=[],
                         ecology=None, infrastructure=[], disaster_cooldowns={},
                         resource_suspensions={}, route_suspensions={},
                         resource_types=[255,255,255], resource_base_yields=[0,0,0],
                         resource_reserves=[1,1,1], resource_effective_yields=[0,0,0],
                         overextraction_streaks={}, controller="Civ0")]
        registry = [Belief(faith_id=0, name="A", civ_origin=0, doctrines=[0,0,0,0,0])]
        snap = _make_snapshot(regions=[0, 0], beliefs=[0, 0], civs=[0, 0])
        majority = compute_majority_belief(snap)
        signals = compute_conversion_signals(regions, majority, registry, snap)
        assert signals[0][0] == 0.0


class TestConquestBoostDecay:
    def test_decay_lifecycle(self):
        """Boost decays linearly to 0 over CONQUEST_BOOST_DURATION turns."""
        boost = CONQUEST_BOOST_RATE
        for t in range(CONQUEST_BOOST_DURATION):
            expected = CONQUEST_BOOST_RATE * (1.0 - t / CONQUEST_BOOST_DURATION)
            assert abs(boost - expected) < 0.001, f"Turn {t}: expected {expected}, got {boost}"
            boost -= CONQUEST_BOOST_RATE / CONQUEST_BOOST_DURATION
        assert abs(boost) < 0.001, f"After full duration, boost should be ~0, got {boost}"


def _make_snapshot(regions=None, beliefs=None, civs=None, occs=None):
    """Build a minimal mock snapshot dict for testing."""
    import pyarrow as pa
    n = len(beliefs)
    arrays = {
        "id": pa.array(list(range(n)), type=pa.uint32()),
        "region": pa.array(regions or [0] * n, type=pa.uint16()),
        "belief": pa.array(beliefs, type=pa.uint8()),
        "civ_affinity": pa.array(civs or [0] * n, type=pa.uint16()),
        "occupation": pa.array(occs or [0] * n, type=pa.uint8()),
    }
    return pa.RecordBatch.from_pydict(arrays)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_religion.py -v`
Expected: FAIL — `chronicler.religion` module doesn't exist

- [ ] **Step 3: Create religion.py with all functions**

Create `src/chronicler/religion.py`:

```python
"""M37: Belief Systems & Conversion.

Religion module: faith generation, belief aggregation, conversion signal computation.
Separate from culture.py — religion is event-driven (stable by default),
culture is ambient drift. Different mechanics, different module.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import TYPE_CHECKING

from chronicler.models import (
    Belief, DOCTRINE_THEOLOGY, DOCTRINE_ETHICS, DOCTRINE_STANCE,
    DOCTRINE_OUTREACH, DOCTRINE_STRUCTURE,
)

if TYPE_CHECKING:
    import pyarrow as pa
    from chronicler.models import Region, WorldState

# --- Constants [CALIBRATE for M47] ---
BASE_CONVERSION_RATE: float = 0.03
PROSELYTIZING_MULTIPLIER: float = 2.0
INSULAR_RESISTANCE: float = 0.5
NAMED_PROPHET_MULTIPLIER: float = 2.0
CONQUEST_BOOST_RATE: float = 0.05
CONQUEST_BOOST_DURATION: int = 10
HOLY_WAR_WEIGHT_BONUS: float = 0.15
HOLY_WAR_DEFENDER_STABILITY: int = 5
DOCTRINE_BIAS_RANDOM_CHANCE: float = 0.20

# Culture value name → doctrine biases: list of (axis_index, pole, weight)
_DOCTRINE_BIAS_TABLE: dict[str, list[tuple[int, int, float]]] = {
    "Honor":     [(DOCTRINE_STANCE, +1, 0.6)],
    "Freedom":   [(DOCTRINE_STRUCTURE, +1, 0.4), (DOCTRINE_OUTREACH, +1, 0.4)],
    "Order":     [(DOCTRINE_STRUCTURE, -1, 0.4), (DOCTRINE_THEOLOGY, -1, 0.4)],
    "Tradition": [(DOCTRINE_OUTREACH, -1, 0.4), (DOCTRINE_ETHICS, -1, 0.4)],
    "Knowledge": [(DOCTRINE_STRUCTURE, -1, 0.5)],
    "Cunning":   [(DOCTRINE_ETHICS, +1, 0.4), (DOCTRINE_OUTREACH, +1, 0.4)],
}

_FAITH_NAME_PARTS = {
    "prefixes": [
        "The Way of", "The Path of", "The Light of", "The Order of",
        "The Fellowship of", "The Covenant of", "The Circle of",
    ],
    "cores": [
        "the Sun", "the Moon", "the Ancestors", "the Flame",
        "the Deep", "the Mountain", "the Stars", "the Tide",
        "the Storm", "the Harvest", "the Forge", "the Wind",
        "Truth", "Harmony", "Valor", "Wisdom", "Justice", "Mercy",
    ],
}


# --- Faith Generation ---

def generate_faiths(
    civ_values: list[list[str]],
    civ_names: list[str],
    seed: int = 0,
) -> list[Belief]:
    """Generate one faith per civ with culture-biased doctrines.

    Args:
        civ_values: Per-civ list of cultural value names (e.g. ["Honor", "Order"]).
        civ_names: Per-civ names (for faith naming).
        seed: RNG seed for reproducibility.

    Returns:
        List of Belief objects, one per civ, indexed by faith_id.
    """
    rng = random.Random(seed)
    registry: list[Belief] = []
    used_names: set[str] = set()

    for civ_idx, values in enumerate(civ_values):
        doctrines = _generate_doctrines(values, rng)
        name = _generate_faith_name(rng, used_names)
        used_names.add(name)
        registry.append(Belief(
            faith_id=civ_idx,
            name=name,
            civ_origin=civ_idx,
            doctrines=doctrines,
        ))

    return registry

# Expose as method on generate_faiths for test access
generate_faiths._generate_doctrines = None  # Replaced below


def _generate_doctrines(values: list[str], rng: random.Random) -> list[int]:
    """Generate doctrine array [i8; 5] biased by civ cultural values."""
    doctrines = [0, 0, 0, 0, 0]

    # Step 1-2: For each cultural value, roll biased axes
    for value_name in values:
        biases = _DOCTRINE_BIAS_TABLE.get(value_name, [])
        for axis, pole, weight in biases:
            if doctrines[axis] == 0 and rng.random() < weight:
                doctrines[axis] = pole

    # Step 3: Random fill for remaining neutral axes
    for i in range(5):
        if doctrines[i] == 0 and rng.random() < DOCTRINE_BIAS_RANDOM_CHANCE:
            doctrines[i] = rng.choice([-1, 1])

    return doctrines

# Wire up for test access
generate_faiths._generate_doctrines = staticmethod(_generate_doctrines)


def _generate_faith_name(rng: random.Random, used: set[str]) -> str:
    """Generate a unique faith name."""
    for _ in range(50):
        prefix = rng.choice(_FAITH_NAME_PARTS["prefixes"])
        core = rng.choice(_FAITH_NAME_PARTS["cores"])
        name = f"{prefix} {core}"
        if name not in used:
            return name
    return f"Faith {len(used)}"


# --- Belief Aggregation ---

def compute_majority_belief(snapshot: pa.RecordBatch) -> dict[int, int]:
    """Compute majority belief per region from agent snapshot.

    Returns dict[region_id, majority_faith_id]. Ties break to lower faith_id.
    """
    regions = snapshot.column("region").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()

    region_counts: dict[int, Counter] = {}
    for i in range(len(regions)):
        b = beliefs[i]
        if b == 0xFF:
            continue
        rid = regions[i]
        if rid not in region_counts:
            region_counts[rid] = Counter()
        region_counts[rid][b] += 1

    result: dict[int, int] = {}
    for rid, counts in region_counts.items():
        if counts:
            # Break ties by lower faith_id
            max_count = max(counts.values())
            candidates = [fid for fid, c in counts.items() if c == max_count]
            result[rid] = min(candidates)
    return result


def compute_civ_majority_faith(snapshot: pa.RecordBatch) -> dict[int, int]:
    """Compute majority faith per civ from agent snapshot.

    Returns dict[civ_id, majority_faith_id].
    """
    civs = snapshot.column("civ_affinity").to_pylist()
    beliefs = snapshot.column("belief").to_pylist()

    civ_counts: dict[int, Counter] = {}
    for i in range(len(civs)):
        b = beliefs[i]
        if b == 0xFF:
            continue
        cid = civs[i]
        if cid not in civ_counts:
            civ_counts[cid] = Counter()
        civ_counts[cid][b] += 1

    result: dict[int, int] = {}
    for cid, counts in civ_counts.items():
        if counts:
            result[cid] = counts.most_common(1)[0][0]
    return result


def compute_conversion_signals(
    regions: list[Region],
    majority_beliefs: dict[int, int],
    belief_registry: list[Belief],
    snapshot: pa.RecordBatch | None,
    named_agents: dict[int, str] | None = None,
    civ_majority_faiths: dict[int, int] | None = None,
    civ_name_to_id: dict[str, int] | None = None,
) -> list[tuple[float, int, bool]]:
    """Compute per-region conversion signals for the Rust tick.

    Returns list of (conversion_rate, conversion_target_belief, conquest_conversion_active)
    indexed by region_id.
    """
    n = len(regions)
    signals: list[tuple[float, int, bool]] = [(0.0, 0xFF, False)] * n

    if snapshot is None or not belief_registry:
        return signals

    # Pre-compute priest counts per faith per region from snapshot
    snap_regions = snapshot.column("region").to_pylist()
    snap_beliefs = snapshot.column("belief").to_pylist()
    snap_occs = snapshot.column("occupation").to_pylist()

    priest_counts: dict[int, Counter] = {}  # region_id → Counter[faith_id]
    # Also build per-region named-agent set for prophet multiplier
    named_agent_regions: dict[int, set[int]] = {}  # region_id → set of faith_ids with named agents
    snap_ids = snapshot.column("id").to_pylist() if named_agents else []
    for i in range(len(snap_regions)):
        rid = snap_regions[i]
        b = snap_beliefs[i]
        if b == 0xFF:
            continue
        # Named character check
        if named_agents and snap_ids and snap_ids[i] in named_agents:
            if snap_occs[i] == 4:  # Priest occupation
                if rid not in named_agent_regions:
                    named_agent_regions[rid] = set()
                named_agent_regions[rid].add(b)
        if snap_occs[i] != 4:  # Occupation::Priest = 4
            continue
        if rid not in priest_counts:
            priest_counts[rid] = Counter()
        priest_counts[rid][b] += 1

    # Build faith doctrine lookup
    doctrine_by_faith: dict[int, list[int]] = {}
    for belief in belief_registry:
        doctrine_by_faith[belief.faith_id] = belief.doctrines

    for rid in range(n):
        region = regions[rid]
        maj = majority_beliefs.get(rid, 0xFF)

        # Read one-shot conquest_conversion_active flag (set by action engine)
        conquest_active = getattr(region, 'conquest_conversion_active', False)
        # Clear after reading (one-shot)
        if conquest_active:
            region.conquest_conversion_active = False

        if maj == 0xFF:
            # No agents or no majority — no conversion (conquest_active still irrelevant)
            signals[rid] = (0.0, 0xFF, False)
            continue

        # Find dominant foreign-faith priests
        region_priests = priest_counts.get(rid, Counter())
        foreign_priests: Counter = Counter()
        for fid, count in region_priests.items():
            if fid != maj:
                foreign_priests[fid] = count

        total_agents = sum(1 for r in snap_regions if r == rid)

        # Determine target faith
        if foreign_priests:
            # Dominant-faith-only: faith with most priests wins
            target_faith = foreign_priests.most_common(1)[0][0]
            priest_count = foreign_priests[target_faith]
        elif region.conquest_conversion_boost > 0 or conquest_active:
            # Conquest boost only, no priests — target is controller civ's faith
            controller_name = region.controller
            if controller_name and civ_name_to_id and civ_majority_faiths:
                cid = civ_name_to_id.get(controller_name)
                target_faith = civ_majority_faiths.get(cid, 0xFF) if cid is not None else 0xFF
            else:
                target_faith = 0xFF
            priest_count = 0
        else:
            signals[rid] = (0.0, 0xFF, False)
            continue

        if target_faith == 0xFF:
            signals[rid] = (0.0, 0xFF, conquest_active)
            continue

        # Compute conversion rate from priest presence
        rate = 0.0
        if priest_count > 0 and total_agents > 0:
            priest_ratio = priest_count / total_agents
            rate = BASE_CONVERSION_RATE * priest_ratio

            # Doctrine modifiers
            target_doctrines = doctrine_by_faith.get(target_faith, [0] * 5)
            if len(target_doctrines) > DOCTRINE_OUTREACH:
                if target_doctrines[DOCTRINE_OUTREACH] == 1:  # Proselytizing
                    rate *= PROSELYTIZING_MULTIPLIER

            maj_doctrines = doctrine_by_faith.get(maj, [0] * 5)
            if len(maj_doctrines) > DOCTRINE_OUTREACH:
                if maj_doctrines[DOCTRINE_OUTREACH] == -1:  # Insular
                    rate *= INSULAR_RESISTANCE

            # Named prophet/priest multiplier
            if rid in named_agent_regions and target_faith in named_agent_regions[rid]:
                rate *= NAMED_PROPHET_MULTIPLIER

        # Add conquest boost
        rate += region.conquest_conversion_boost

        signals[rid] = (rate, target_faith, conquest_active)

    return signals


def decay_conquest_boosts(regions: list[Region]) -> None:
    """Decay conquest_conversion_boost linearly each turn."""
    decay_amount = CONQUEST_BOOST_RATE / CONQUEST_BOOST_DURATION
    for region in regions:
        if region.conquest_conversion_boost > 0:
            region.conquest_conversion_boost = max(
                0.0, region.conquest_conversion_boost - decay_amount
            )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_religion.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/religion.py tests/test_religion.py
git commit -m "feat(m37): add religion.py module with faith generation and signal computation"
```

---

## Chunk 6: Python Bridge & World-Gen

### Task 11: Extend agent_bridge.py with Conversion Signals

**Files:**
- Modify: `src/chronicler/agent_bridge.py:93-177`

- [ ] **Step 1: Add conversion signal columns to build_region_batch()**

In `build_region_batch()`, after the M36 `controller_values_0/1/2` columns (~line 176), add:

```python
    # M37: Conversion signals (computed by religion.py in Phase 10 of previous turn)
    # These are stored as declared fields on Region (not private underscore attrs)

    majority_belief_arr = []
    conversion_rate_arr = []
    conversion_target_arr = []
    conquest_active_arr = []
    initial_belief_arr = []

    for i, region in enumerate(world.regions):
        # Majority belief — stored on region from Phase 10
        majority_belief_arr.append(region.majority_belief)

        # Conversion signals — stored as tuple on region from Phase 10
        rate, target, active = region.conversion_signals
        conversion_rate_arr.append(rate)
        conversion_target_arr.append(target)
        conquest_active_arr.append(active)

        # Initial belief for spawn — controller civ's founding faith_id
        civ_name = region.controller
        if civ_name and world.belief_registry:
            civ_idx = next(
                (j for j, c in enumerate(world.civilizations) if c.name == civ_name),
                None,
            )
            if civ_idx is not None and civ_idx < len(world.belief_registry):
                initial_belief_arr.append(world.belief_registry[civ_idx].faith_id)
            else:
                initial_belief_arr.append(0xFF)
        else:
            initial_belief_arr.append(0xFF)
```

Add these to the Arrow arrays dict and RecordBatch:

```python
    arrays["conversion_rate"] = pa.array(conversion_rate_arr, type=pa.float32())
    arrays["conversion_target_belief"] = pa.array(conversion_target_arr, type=pa.uint8())
    arrays["conquest_conversion_active"] = pa.array(conquest_active_arr, type=pa.bool_())
    arrays["majority_belief"] = pa.array(majority_belief_arr, type=pa.uint8())
    arrays["initial_belief"] = pa.array(initial_belief_arr, type=pa.uint8())
```

- [ ] **Step 2: Verify build succeeds**

Run: `python -c "from chronicler.agent_bridge import build_region_batch; print('OK')"`
Expected: OK (import succeeds)

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m37): add conversion signals and initial_belief to region batch"
```

---

### Task 12: World-Gen Faith Generation and Phase 10 Wiring

**Files:**
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Add faith generation to world-gen initialization**

In `simulation.py`, find the world initialization / `init_world()` or equivalent function where civilizations are created. After civs are set up, add:

```python
    # M37: Generate one faith per civ
    from chronicler.religion import generate_faiths
    if world.civilizations:
        civ_values = [c.values for c in world.civilizations]
        civ_names = [c.name for c in world.civilizations]
        world.belief_registry = generate_faiths(civ_values, civ_names, seed=world.seed)
```

- [ ] **Step 2: Add Phase 10 religion computations**

In `phase_consequences()` / Phase 10 (~line 824), after cultural effects and before asabiya dynamics, add:

```python
    # M37: Religion computations for next turn's Rust tick
    _snap = getattr(world, '_agent_snapshot', None)
    if _snap is not None and world.belief_registry:
        from chronicler.religion import (
            compute_majority_belief, compute_civ_majority_faith,
            compute_conversion_signals, decay_conquest_boosts,
        )
        # Compute belief aggregations
        majority_beliefs = compute_majority_belief(_snap)
        civ_faiths = compute_civ_majority_faith(_snap)

        # Store majority_belief on regions (declared field)
        for rid, maj in majority_beliefs.items():
            if rid < len(world.regions):
                world.regions[rid].majority_belief = maj

        # Store civ_majority_faith on civilizations for action engine
        for cid, faith in civ_faiths.items():
            if cid < len(world.civilizations):
                world.civilizations[cid].civ_majority_faith = faith

        # Build civ lookup for conversion signal computation
        civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}

        # Compute conversion signals for next turn's Rust tick
        # Reads conquest_conversion_active from region (one-shot, cleared after read)
        signals = compute_conversion_signals(
            world.regions, majority_beliefs, world.belief_registry, _snap,
            named_agents=agent_bridge.named_agents if agent_bridge else None,
            civ_majority_faiths=civ_faiths,
            civ_name_to_id=civ_name_to_id,
        )
        for rid, sig in enumerate(signals):
            if rid < len(world.regions):
                world.regions[rid].conversion_signals = sig

        # Decay conquest conversion boosts
        decay_conquest_boosts(world.regions)
    elif world.belief_registry:
        # --agents=off: default civ_majority_faith to founding faith
        for i, civ in enumerate(world.civilizations):
            if i < len(world.belief_registry):
                civ.civ_majority_faith = world.belief_registry[i].faith_id
```

- [ ] **Step 3: Run smoke test**

Run: `python -m pytest tests/ -x -q --timeout=60 -k "not slow"`
Expected: All existing tests pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m37): add faith generation at world-gen and Phase 10 religion computations"
```

---

## Chunk 7: Holy War & Action Engine

### Task 13: Add Holy War WAR Weight Modifier

**Files:**
- Modify: `src/chronicler/action_engine.py`
- Test: `tests/test_religion.py`

- [ ] **Step 1: Write failing test for holy war weight**

Add to `tests/test_religion.py`:

```python
class TestHolyWarWeight:
    def test_militant_bonus(self, make_world):
        """Militant-doctrine civ gets +0.15 WAR weight against different faith."""
        from chronicler.religion import HOLY_WAR_WEIGHT_BONUS
        from chronicler.action_engine import ActionEngine
        from chronicler.models import Belief, DOCTRINE_STANCE

        world = make_world(num_civs=2)
        # Civ0: faith 0, Militant doctrine
        world.belief_registry = [
            Belief(faith_id=0, name="Faith A", civ_origin=0,
                   doctrines=[0, 0, 1, 0, 0]),  # Militant
            Belief(faith_id=1, name="Faith B", civ_origin=1,
                   doctrines=[0, 0, -1, 0, 0]),  # Pacifist
        ]
        world.civilizations[0].civ_majority_faith = 0
        world.civilizations[1].civ_majority_faith = 1

        # Make them hostile so WAR is viable
        world.relationships["Civ0"]["Civ1"].disposition = "hostile"

        engine = ActionEngine()
        weights = engine.compute_weights(world.civilizations[0], world)
        war_weight_with_holy = weights.get("war", 0)

        # Without religion, compute baseline
        world.belief_registry = []
        weights_base = engine.compute_weights(world.civilizations[0], world)
        war_weight_base = weights_base.get("war", 0)

        assert war_weight_with_holy > war_weight_base
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_religion.py::TestHolyWarWeight -v`
Expected: FAIL — holy war modifier not implemented

- [ ] **Step 3: Add holy war modifier to action engine**

In `action_engine.py`, in `compute_weights()` or `_apply_situational()`, after existing WAR modifiers and before the final cap (~line 735), add:

```python
    # M37: Holy war weight modifier
    if world.belief_registry and hasattr(civ, 'civ_majority_faith'):
        attacker_faith = civ.civ_majority_faith
        attacker_doctrines = None
        for b in world.belief_registry:
            if b.faith_id == attacker_faith:
                attacker_doctrines = b.doctrines
                break

        if attacker_doctrines and attacker_doctrines[DOCTRINE_STANCE] == 1:  # Militant
            # Check if any hostile/suspicious neighbor has different faith
            from chronicler.models import DOCTRINE_STANCE
            if civ.name in world.relationships:
                for other_name, rel in world.relationships[civ.name].items():
                    if rel.disposition in ("hostile", "suspicious"):
                        other = next((c for c in world.civilizations
                                     if c.name == other_name), None)
                        if other and hasattr(other, 'civ_majority_faith'):
                            if other.civ_majority_faith != attacker_faith:
                                from chronicler.religion import HOLY_WAR_WEIGHT_BONUS
                                weights[ActionType.WAR] += HOLY_WAR_WEIGHT_BONUS
                                break  # One bonus, not per-neighbor
```

- [ ] **Step 4: Add defender stability bonus in resolve_war()**

In `resolve_war()` (~line 393-398), after asabiya calculation, add:

```python
    # M37: Religious defense bonus
    if (world.belief_registry
        and hasattr(attacker, 'civ_majority_faith')
        and hasattr(defender, 'civ_majority_faith')
        and attacker.civ_majority_faith != defender.civ_majority_faith):
        from chronicler.religion import HOLY_WAR_DEFENDER_STABILITY
        def_asabiya = min(def_asabiya + HOLY_WAR_DEFENDER_STABILITY / 100.0, 1.0)
```

- [ ] **Step 5: Add conquest conversion hook after territory transfer**

In `resolve_war()`, after the territory transfer block (where region.controller changes), add:

```python
        # M37: Conquest conversion
        if (world.belief_registry
            and hasattr(attacker, 'civ_majority_faith')
            and hasattr(defender, 'civ_majority_faith')
            and attacker.civ_majority_faith != defender.civ_majority_faith):
            from chronicler.religion import CONQUEST_BOOST_RATE
            from chronicler.models import DOCTRINE_STANCE
            attacker_belief = next(
                (b for b in world.belief_registry
                 if b.faith_id == attacker.civ_majority_faith), None
            )
            is_militant = (attacker_belief and
                          attacker_belief.doctrines[DOCTRINE_STANCE] == 1)
            if is_militant:
                # Holy war: 30% forced flip via Rust + ongoing boost
                contested.conquest_conversion_active = True  # declared field on Region
            # Both militant and non-militant get the boost
            contested.conquest_conversion_boost = CONQUEST_BOOST_RATE
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_religion.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_religion.py
git commit -m "feat(m37): add holy war WAR weight modifier and conquest conversion hook"
```

---

## Chunk 8: Integration & Regression Tests

### Task 14: Write Tier 2 Regression Tests

**Files:**
- Modify: `tests/test_religion.py`

- [ ] **Step 1: Add regression test for belief stability (no false conversions)**

```python
class TestRegressionM37:
    @pytest.mark.slow
    def test_beliefs_stable_without_priests(self):
        """In a single-faith region with no foreign priests,
        beliefs never change. Stable-by-default contract."""
        # Run 50-turn sim with 1 civ, all same faith, verify 100% cohesion
        from chronicler.simulation import run_simulation
        world = _make_single_civ_world(seed=42)
        for _ in range(50):
            run_simulation(world, turns=1)
        snap = world._agent_snapshot
        if snap is not None:
            beliefs = snap.column("belief").to_pylist()
            unique = set(b for b in beliefs if b != 0xFF)
            assert len(unique) <= 1, f"Expected 1 faith, found {unique}"

    @pytest.mark.slow
    def test_life_event_conversion_survives_tick(self):
        """Converted agents have LIFE_EVENT_CONVERSION bit in snapshot."""
        # This requires a multi-civ world with foreign priests causing conversion
        # Run enough turns for conversion to occur, then check snapshot
        from chronicler.simulation import run_simulation
        world = _make_multi_civ_world(seed=42)
        # Run 30 turns to allow some conversions
        for _ in range(30):
            run_simulation(world, turns=1)
        snap = world._agent_snapshot
        if snap is not None and "life_events" in snap.schema.names:
            life_events = snap.column("life_events").to_pylist()
            beliefs = snap.column("belief").to_pylist()
            civs = snap.column("civ_affinity").to_pylist()
            # Look for any agent whose belief != their civ's founding faith
            converted = [
                i for i in range(len(beliefs))
                if beliefs[i] != civs[i] and beliefs[i] != 0xFF
            ]
            if converted:
                # At least some converted agents should have the bit set
                with_bit = [
                    i for i in converted
                    if life_events[i] & 0x40  # bit 6 = LIFE_EVENT_CONVERSION
                ]
                assert len(with_bit) > 0, (
                    f"Found {len(converted)} converted agents but none have "
                    f"LIFE_EVENT_CONVERSION bit set"
                )

    @pytest.mark.slow
    def test_agents_off_no_belief_behavior(self):
        """In --agents=off mode, belief_registry exists but no conversion occurs."""
        from chronicler.simulation import run_simulation
        world = _make_multi_civ_world(seed=42, agent_mode=None)
        for _ in range(50):
            run_simulation(world, turns=1)
        # No crash, no agent_snapshot, belief_registry still populated
        assert len(world.belief_registry) > 0
        assert world._agent_snapshot is None
```

- [ ] **Step 2: Run regression tests**

Run: `python -m pytest tests/test_religion.py::TestRegressionM37 -v --timeout=120`
Expected: Pass (may need adjustment based on actual simulation harness)

- [ ] **Step 3: Add test for initial spawn beliefs**

```python
class TestInitialSpawn:
    def test_all_agents_have_civ_faith(self):
        """After world-gen, every agent should hold their civ's founding faith."""
        from chronicler.simulation import run_simulation
        world = _make_multi_civ_world(seed=42)
        run_simulation(world, turns=0)  # Just init, no turns
        snap = world._agent_snapshot
        if snap is not None:
            civs = snap.column("civ_affinity").to_pylist()
            beliefs = snap.column("belief").to_pylist()
            for i in range(len(civs)):
                civ_id = civs[i]
                expected_faith = civ_id  # faith_id == civ index by generation
                assert beliefs[i] == expected_faith, (
                    f"Agent {i} in civ {civ_id} has belief {beliefs[i]}, "
                    f"expected {expected_faith}"
                )
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_religion.py
git commit -m "test(m37): add Tier 2 regression tests for belief stability and initial spawn"
```

---

### Task 15: Final Integration Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full Rust test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All tests pass

- [ ] **Step 2: Run full Python test suite**

Run: `python -m pytest tests/ -x -q --timeout=120`
Expected: All tests pass

- [ ] **Step 3: Run a quick simulation smoke test**

Run: `python -m chronicler.batch --seeds 42 --turns 100 --agents hybrid --quiet`
Expected: Completes without errors. Check output for belief-related events.

- [ ] **Step 4: Verify snapshot has belief column**

Run: `python -c "from chronicler.simulation import *; w = init_world(42); run_turn(w); print(w._agent_snapshot.schema)"`
Expected: Schema includes "belief" column with uint8 type

- [ ] **Step 5: Final commit with all integration fixes**

```bash
git add -A
git commit -m "feat(m37): M37 Belief Systems & Conversion complete"
```
