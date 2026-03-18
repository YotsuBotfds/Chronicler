# M41: Wealth & Class Stratification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-agent wealth accumulation and class tension to the Rust agent pool, producing emergent economic stratification that feeds into the existing satisfaction → loyalty → rebellion pipeline.

**Architecture:** One new `f32` SoA field (`wealth`) in the Rust agent pool. Wealth accumulates per-tick based on occupation and resource type (organic vs extractive dispatch). Python computes per-civ Gini coefficient from snapshot, sends it back as a signal. Rust uses Gini + per-agent wealth rank to compute a class tension satisfaction penalty (priority-clamped under the existing 0.40 cap). No treasury or market effects — those belong to M42.

**Tech Stack:** Rust (chronicler-agents crate), Python 3.12, PyO3/Arrow FFI, numpy

**Spec:** `docs/superpowers/specs/2026-03-17-m41-wealth-class-stratification-design.md`

---

## Chunk 1: Rust Foundation (Tasks 1–4)

### Task 1: Constants & Resource Dispatch

**Files:**
- Modify: `chronicler-agents/src/agent.rs:139-150`
- Test: `chronicler-agents/src/agent.rs` (inline tests)

- [ ] **Step 1: Add wealth constants to agent.rs**

After the M39 constants block (line 145), add:

```rust
// M41: Wealth & Class Stratification
pub const STARTING_WEALTH: f32 = 0.5;       // [CALIBRATE] initial wealth for all agents
pub const MAX_WEALTH: f32 = 100.0;          // [CALIBRATE] wealth ceiling
pub const WEALTH_DECAY: f32 = 0.02;         // [CALIBRATE] multiplicative decay per tick
pub const FARMER_INCOME: f32 = 0.30;        // [CALIBRATE] equilibrium ~15 at full yield
pub const MINER_INCOME: f32 = 0.80;         // [CALIBRATE] equilibrium ~40, yield-dependent
pub const SOLDIER_INCOME: f32 = 0.15;       // [CALIBRATE] low peacetime base
pub const AT_WAR_BONUS: f32 = 1.0;          // [CALIBRATE] doubles soldier income at war
pub const CONQUEST_BONUS: f32 = 3.0;        // [CALIBRATE] one-shot wealth spike on conquest
pub const MERCHANT_INCOME: f32 = 0.50;      // [CALIBRATE] with baseline → equilibrium ~12.5
pub const MERCHANT_BASELINE: f32 = 0.5;     // [CALIBRATE] temporary; M42 replaces with market income
pub const SCHOLAR_INCOME: f32 = 0.20;       // [CALIBRATE] equilibrium ~10
pub const PRIEST_INCOME: f32 = 0.20;        // [CALIBRATE] equilibrium ~10; M42 adds tithe
pub const CLASS_TENSION_WEIGHT: f32 = 0.15; // [CALIBRATE] max penalty for poorest at Gini=1.0
```

- [ ] **Step 2: Add is_extractive helper**

In `agent.rs`, after the constants block:

```rust
/// ORE=5, PRECIOUS=6 are extractive; all others are organic.
#[inline]
pub fn is_extractive(resource_type: u8) -> bool {
    resource_type == 5 || resource_type == 6
}
```

- [ ] **Step 3: Write tests for constants and dispatch**

Add to the existing `mod tests` in `agent.rs`:

```rust
#[test]
fn test_is_extractive_ore() {
    assert!(is_extractive(5)); // ORE
}

#[test]
fn test_is_extractive_precious() {
    assert!(is_extractive(6)); // PRECIOUS
}

#[test]
fn test_is_extractive_organic() {
    assert!(!is_extractive(0)); // GRAIN
    assert!(!is_extractive(1)); // TIMBER
    assert!(!is_extractive(2)); // BOTANICALS
    assert!(!is_extractive(3)); // FISH
    assert!(!is_extractive(4)); // SALT
    assert!(!is_extractive(7)); // EXOTIC
}

#[test]
fn test_wealth_equilibrium_farmer() {
    // At yield=1.0: equilibrium = FARMER_INCOME / WEALTH_DECAY
    let eq = FARMER_INCOME / WEALTH_DECAY;
    assert!(eq > 5.0 && eq < 50.0, "Farmer equilibrium {eq} out of range");
}

#[test]
fn test_wealth_equilibrium_miner() {
    let eq = MINER_INCOME / WEALTH_DECAY;
    assert!(eq > FARMER_INCOME / WEALTH_DECAY, "Miner should earn more than farmer");
}
```

- [ ] **Step 4: Run tests**

Run: `cargo test -p chronicler-agents -- agent::tests::test_is_extractive`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "M41: add wealth constants and is_extractive() resource dispatch"
```

---

### Task 2: Pool Storage — wealth Vec

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-59` (struct), `:94-168` (spawn), `:363-437` (to_record_batch)
- Modify: `chronicler-agents/src/ffi.rs:64-85` (snapshot_schema)

- [ ] **Step 1: Add `wealth` field to AgentPool struct**

In `pool.rs`, after `parent_ids` (line 49), before `alive` (line 51):

```rust
    // Wealth (M41) — personal economic accumulation
    pub wealth: Vec<f32>,
```

- [ ] **Step 2: Initialize wealth in `with_capacity`**

In `pool.rs`, find the `with_capacity` method. Add after `parent_ids`:

```rust
            wealth: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Initialize wealth in `spawn` — free slot path**

In `pool.rs` `spawn()`, after `self.parent_ids[slot] = ...` (line 135), before `self.alive[slot] = true`:

```rust
            self.wealth[slot] = crate::agent::STARTING_WEALTH;
```

- [ ] **Step 4: Initialize wealth in `spawn` — growth path**

In `pool.rs` `spawn()`, after `self.parent_ids.push(...)` (line 163), before `self.alive.push(true)`:

```rust
            self.wealth.push(crate::agent::STARTING_WEALTH);
```

- [ ] **Step 5: Add wealth to snapshot schema**

In `ffi.rs` `snapshot_schema()`, after the `parent_id` field (line 83):

```rust
        Field::new("wealth", DataType::Float32, false),
```

- [ ] **Step 6: Add wealth to `to_record_batch`**

In `pool.rs` `to_record_batch()`:

1. Add builder initialization (after the `parent_id_col` builder):
```rust
        let mut wealth_col = Float32Builder::new();
```

2. In the per-slot loop, after appending `parent_id`:
```rust
                wealth_col.append_value(self.wealth[slot]);
```

3. In the RecordBatch construction vec, after the `parent_id` column:
```rust
                Arc::new(wealth_col.finish()),
```

- [ ] **Step 7: Run tests to verify pool compiles**

Run: `cargo test -p chronicler-agents -- pool`
Expected: existing pool tests PASS (no behavioral change yet)

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/ffi.rs
git commit -m "M41: add wealth field to AgentPool and snapshot schema"
```

---

### Task 3: Signals — gini_coefficient & conquered_this_turn

**Files:**
- Modify: `chronicler-agents/src/signals.rs:8-32` (CivSignals struct), `:42-129` (parse)

- [ ] **Step 1: Write failing test for new signal fields**

Add to `signals.rs` `mod tests`:

```rust
#[test]
fn test_parse_m41_signals() {
    let batch = RecordBatch::try_from_iter(vec![
        ("civ_id", Arc::new(UInt8Array::from(vec![0u8])) as _),
        ("stability", Arc::new(UInt8Array::from(vec![50u8])) as _),
        ("is_at_war", Arc::new(BooleanArray::from(vec![false])) as _),
        ("dominant_faction", Arc::new(UInt8Array::from(vec![0u8])) as _),
        ("faction_military", Arc::new(Float32Array::from(vec![0.33f32])) as _),
        ("faction_merchant", Arc::new(Float32Array::from(vec![0.33f32])) as _),
        ("faction_cultural", Arc::new(Float32Array::from(vec![0.34f32])) as _),
        ("gini_coefficient", Arc::new(Float32Array::from(vec![0.45f32])) as _),
        ("conquered_this_turn", Arc::new(BooleanArray::from(vec![true])) as _),
    ]).unwrap();
    let civs = parse_civ_signals(&batch).unwrap();
    assert_eq!(civs.len(), 1);
    assert!((civs[0].gini_coefficient - 0.45).abs() < 0.001);
    assert!(civs[0].conquered_this_turn);
}

#[test]
fn test_m41_signals_default_when_absent() {
    let batch = make_civ_batch(); // existing helper — no M41 columns
    let civs = parse_civ_signals(&batch).unwrap();
    assert_eq!(civs[0].gini_coefficient, 0.0);
    assert!(!civs[0].conquered_this_turn);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p chronicler-agents -- signals::tests::test_parse_m41`
Expected: FAIL — `gini_coefficient` field doesn't exist on CivSignals

- [ ] **Step 3: Add fields to CivSignals struct**

In `signals.rs`, after `mean_loyalty_trait` (line 31):

```rust
    // M41: Wealth & Class Stratification
    pub gini_coefficient: f32,
    pub conquered_this_turn: bool,
```

- [ ] **Step 4: Add signal parsing**

In `parse_civ_signals()`, after `mean_loyalty_trait_col` (line 101):

```rust
    let gini_coefficient_col = batch.column_by_name("gini_coefficient")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let conquered_this_turn_col = batch.column_by_name("conquered_this_turn")
        .and_then(|c| c.as_any().downcast_ref::<BooleanArray>());
```

In the `result.push(CivSignals { ... })` block, after `mean_loyalty_trait`:

```rust
            gini_coefficient: gini_coefficient_col.map(|a| a.value(i)).unwrap_or(0.0),
            conquered_this_turn: conquered_this_turn_col.map(|a| a.value(i)).unwrap_or(false),
```

- [ ] **Step 5: Update ALL CivSignals struct literal construction sites**

Every file that constructs `CivSignals` via struct literal must add the two new fields. Add `gini_coefficient: 0.0, conquered_this_turn: false,` to each:

- `chronicler-agents/src/tick.rs:600` — `make_default_signals` test helper
- `chronicler-agents/tests/determinism.rs:41` — test signals construction
- `chronicler-agents/tests/regression.rs:13` — test signals construction
- `chronicler-agents/benches/tick_bench.rs:9` — benchmark signals
- `chronicler-agents/benches/cache_bench.rs:11` — benchmark signals
- `chronicler-agents/examples/flamegraph_run.rs:65` — example signals

**Pre-existing fix:** The bench/test files (`tick_bench.rs`, `cache_bench.rs`, `regression.rs`) are also missing `faction_clergy: 0.0` from M38a. Add it at the same time alongside the M41 fields to avoid confusing compilation errors. (`flamegraph_run.rs` already has it.)

- [ ] **Step 6: Run tests**

Run: `cargo test -p chronicler-agents -- signals::tests`
Expected: all signal tests PASS (including new M41 tests and backward compat)

Run: `cargo test -p chronicler-agents`
Expected: full crate PASS (all struct literal sites updated)

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/signals.rs chronicler-agents/src/tick.rs chronicler-agents/tests/determinism.rs chronicler-agents/tests/regression.rs chronicler-agents/benches/tick_bench.rs chronicler-agents/benches/cache_bench.rs chronicler-agents/examples/flamegraph_run.rs
git commit -m "M41: add gini_coefficient and conquered_this_turn to CivSignals"
```

---

### Task 4: Wealth Tick — Accumulation, Decay, Rank

**Files:**
- Modify: `chronicler-agents/src/tick.rs:42-73` (insert wealth phases before satisfaction)
- Test: `chronicler-agents/src/tick.rs` (inline tests) or new test file

- [ ] **Step 1: Write failing test for wealth accumulation**

Add a new `mod m41_tests` at the bottom of `tick.rs`:

```rust
#[cfg(test)]
mod m41_tests {
    use super::*;
    use crate::agent::{self, STARTING_WEALTH, FARMER_INCOME, MINER_INCOME,
        SOLDIER_INCOME, AT_WAR_BONUS, CONQUEST_BONUS, MERCHANT_INCOME,
        MERCHANT_BASELINE, SCHOLAR_INCOME, PRIEST_INCOME, WEALTH_DECAY, MAX_WEALTH};
    use crate::region::RegionState;
    use crate::signals::{CivSignals, TickSignals};

    fn make_test_signals(at_war: bool, conquered: bool, gini: f32) -> TickSignals {
        TickSignals {
            civs: vec![CivSignals {
                civ_id: 0,
                stability: 50,
                is_at_war: at_war,
                dominant_faction: 0,
                faction_military: 0.33,
                faction_merchant: 0.33,
                faction_cultural: 0.34,
                faction_clergy: 0.0,
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
                mean_boldness: 0.0,
                mean_ambition: 0.0,
                mean_loyalty_trait: 0.0,
                gini_coefficient: gini,
                conquered_this_turn: conquered,
            }],
            contested_regions: vec![false],
        }
    }

    fn make_region_organic(yield_val: f32) -> RegionState {
        let mut r = RegionState::new(0);
        r.resource_types = [0, 255, 255]; // GRAIN
        r.resource_yields = [yield_val, 0.0, 0.0];
        r.soil = 0.5;
        r.water = 0.5;
        r.controller_values = [0, 1, 2];
        r.majority_belief = 0xFF;
        r
    }

    fn make_region_extractive(yield_val: f32) -> RegionState {
        let mut r = RegionState::new(0);
        r.resource_types = [5, 255, 255]; // ORE
        r.resource_yields = [yield_val, 0.0, 0.0];
        r.soil = 0.5;
        r.water = 0.5;
        r.controller_values = [0, 1, 2];
        r.majority_belief = 0xFF;
        r
    }

    #[test]
    fn test_farmer_organic_wealth_accumulates() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let initial = pool.wealth[slot];
        assert!((initial - STARTING_WEALTH).abs() < 0.001);

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        // income = FARMER_INCOME * 0.8, then decay
        let expected_income = FARMER_INCOME * 0.8;
        let after_income = initial + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001,
            "Got {}, expected {}", pool.wealth[slot], expected);
    }

    #[test]
    fn test_farmer_extractive_uses_miner_rate() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_extractive(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = MINER_INCOME * 0.8;
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001);
    }

    #[test]
    fn test_soldier_war_bonus() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Soldier, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_organic(0.8)];
        let signals_peace = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals_peace, &mut percentiles);
        let wealth_peace = pool.wealth[slot];

        // Reset
        pool.wealth[slot] = STARTING_WEALTH;
        let signals_war = make_test_signals(true, false, 0.0);
        wealth_tick(&mut pool, &regions, &signals_war, &mut percentiles);
        let wealth_war = pool.wealth[slot];

        assert!(wealth_war > wealth_peace,
            "War income ({wealth_war}) should exceed peace income ({wealth_peace})");
    }

    #[test]
    fn test_soldier_conquest_bonus() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Soldier, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(true, true, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = SOLDIER_INCOME * (1.0 + AT_WAR_BONUS) + CONQUEST_BONUS;
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.01,
            "Got {}, expected {}", pool.wealth[slot], expected);
    }

    #[test]
    fn test_merchant_baseline_income() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Merchant, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = MERCHANT_INCOME * MERCHANT_BASELINE;
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001);
    }

    #[test]
    fn test_wealth_clamped_to_max() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        pool.wealth[slot] = MAX_WEALTH + 10.0; // artificially above max

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        assert!(pool.wealth[slot] <= MAX_WEALTH,
            "Wealth {} should be clamped to {}", pool.wealth[slot], MAX_WEALTH);
    }

    #[test]
    fn test_percentile_ranking_three_agents() {
        let mut pool = AgentPool::new(4);
        // Three agents in same civ (0), same region (0)
        let s0 = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let s1 = pool.spawn(0, 0, agent::Occupation::Merchant, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let s2 = pool.spawn(0, 0, agent::Occupation::Scholar, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        pool.wealth[s0] = 1.0;  // poorest
        pool.wealth[s1] = 5.0;  // middle
        pool.wealth[s2] = 10.0; // richest

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.5);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        // After accumulation+decay, relative ordering should be preserved.
        // Check percentiles: poorest=0.0, middle=0.5, richest=1.0
        assert!((percentiles[s0] - 0.0).abs() < 0.001, "Poorest should be 0.0");
        assert!((percentiles[s1] - 0.5).abs() < 0.001, "Middle should be 0.5");
        assert!((percentiles[s2] - 1.0).abs() < 0.001, "Richest should be 1.0");
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p chronicler-agents -- m41_tests`
Expected: FAIL — `wealth_tick` function doesn't exist

- [ ] **Step 3: Implement wealth_tick function**

Add to `tick.rs`, before the `update_satisfaction` function:

```rust
// ---------------------------------------------------------------------------
// M41: Wealth tick — accumulation, decay, per-civ rank
// ---------------------------------------------------------------------------

/// Wealth accumulation, multiplicative decay, and per-civ percentile ranking.
/// Must run BEFORE update_satisfaction (which consumes wealth_percentiles).
pub fn wealth_tick(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &mut [f32],
) {
    // --- Step 1: Accumulation + Decay ---
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }

        let region_id = pool.regions[slot] as usize;
        if region_id >= regions.len() { continue; }
        let region = &regions[region_id];
        let occ = pool.occupations[slot];
        let civ = pool.civ_affinities[slot];

        // Note: O(n) lookup per agent. If benchmarks show this matters, pre-build
        // a [Option<&CivSignals>; 256] lookup array before the loop.
        let civ_sig = signals.civs.iter().find(|c| c.civ_id == civ);
        let at_war = civ_sig.map_or(false, |c| c.is_at_war);
        let conquered = civ_sig.map_or(false, |c| c.conquered_this_turn);

        let income = match occ {
            0 => {
                // Farmer — dispatch on primary resource type
                let rtype = region.resource_types[0];
                let yield_val = region.resource_yields[0];
                if crate::agent::is_extractive(rtype) {
                    crate::agent::MINER_INCOME * yield_val
                } else {
                    crate::agent::FARMER_INCOME * yield_val
                }
            }
            1 => {
                // Soldier — war bonus + conquest bonus
                crate::agent::SOLDIER_INCOME * (1.0 + crate::agent::AT_WAR_BONUS * at_war as i32 as f32)
                    + crate::agent::CONQUEST_BONUS * conquered as i32 as f32
            }
            2 => {
                // Merchant — temporary baseline (Decision 17)
                crate::agent::MERCHANT_INCOME * crate::agent::MERCHANT_BASELINE
            }
            3 => {
                // Scholar — flat
                crate::agent::SCHOLAR_INCOME
            }
            _ => {
                // Priest — flat (tithe deferred to M42)
                crate::agent::PRIEST_INCOME
            }
        };

        pool.wealth[slot] += income;
        // Multiplicative decay
        pool.wealth[slot] *= 1.0 - crate::agent::WEALTH_DECAY;
        pool.wealth[slot] = pool.wealth[slot].clamp(0.0, crate::agent::MAX_WEALTH);
    }

    // --- Step 2: Per-civ percentile ranking ---
    // Collect (slot, wealth, civ) for alive agents, group by civ.
    // Note: HashMap allocates per tick. With <16 civs this is fast, but if
    // benchmarks show allocation pressure, refactor to a reusable [Vec; 256].
    let mut civ_groups: std::collections::HashMap<u8, Vec<(usize, f32)>> =
        std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        let civ = pool.civ_affinities[slot];
        civ_groups.entry(civ).or_default().push((slot, pool.wealth[slot]));
    }

    for (_civ, mut agents) in civ_groups {
        // Sort ascending by wealth — total_cmp: no panic on NaN
        agents.sort_by(|a, b| a.1.total_cmp(&b.1));
        let denom = (agents.len() as f32 - 1.0).max(1.0);
        for (rank, (slot, _)) in agents.iter().enumerate() {
            wealth_percentiles[*slot] = rank as f32 / denom;
        }
    }
}
```

- [ ] **Step 4: Add wealth_percentiles scratch vector to AgentSimulator**

In `ffi.rs`, add a field to `AgentSimulator` (after existing fields, around line 185):

```rust
    wealth_percentiles: Vec<f32>,
```

In `AgentSimulator::new()`, initialize it:

```rust
    wealth_percentiles: Vec::new(),
```

In `AgentSimulator::tick()`, resize if needed and pass to `tick_agents`:

```rust
    // Resize scratch vector if pool grew
    if self.wealth_percentiles.len() < self.pool.capacity() {
        self.wealth_percentiles.resize(self.pool.capacity(), 0.0);
    }
```

- [ ] **Step 5: Wire wealth_tick into tick_agents**

Update `tick_agents` signature to accept `wealth_percentiles`:

```rust
pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
    wealth_percentiles: &mut [f32],
) -> Vec<AgentEvent> {
```

After the skill growth loop (line 68), before the satisfaction update (line 73), insert:

```rust
    // -----------------------------------------------------------------------
    // 0.5 Wealth accumulation, decay, per-civ rank (M41)
    // -----------------------------------------------------------------------
    wealth_tick(pool, regions, signals, wealth_percentiles);
```

Update ALL callers of `tick_agents` — each needs a scratch buffer (`vec![0.0f32; pool.capacity()]`) and `&mut percentiles` passed as the new parameter:

- `chronicler-agents/src/ffi.rs` — `AgentSimulator::tick()` (pass `&mut self.wealth_percentiles`)
- `chronicler-agents/benches/tick_bench.rs` — benchmark entry point
- `chronicler-agents/benches/cache_bench.rs` — benchmark entry point
- `chronicler-agents/tests/regression.rs` — integration test
- `chronicler-agents/examples/flamegraph_run.rs` — example runner

This is the same file list as Task 3 Step 5 (CivSignals updates).

- [ ] **Step 6: Run tests**

Run: `cargo test -p chronicler-agents -- m41_tests`
Expected: all 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/benches/tick_bench.rs chronicler-agents/benches/cache_bench.rs chronicler-agents/tests/regression.rs chronicler-agents/examples/flamegraph_run.rs
git commit -m "M41: implement wealth_tick — accumulation, decay, per-civ rank"
```

---

## Chunk 2: Satisfaction Integration (Task 5)

### Task 5: Class Tension Penalty in Satisfaction

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs:128-187` (add params, priority clamping)
- Modify: `chronicler-agents/src/tick.rs:331-450` (pass wealth_percentiles + gini to update_satisfaction)

- [ ] **Step 1: Write failing test for class tension penalty**

Add to `satisfaction.rs` at the end of file:

```rust
#[cfg(test)]
mod m41_tests {
    use super::*;
    use crate::signals::CivShock;

    #[test]
    fn test_class_tension_poor_agent_penalized() {
        let shock = CivShock::default();
        let sat_rich = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock, [0, 1, 2], [0, 1, 2], 0xFF, 0xFF, false, 0.0,
            0.6, // gini
            1.0, // wealth_percentile = richest → zero penalty
        );
        let sat_poor = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock, [0, 1, 2], [0, 1, 2], 0xFF, 0xFF, false, 0.0,
            0.6, // gini
            0.0, // wealth_percentile = poorest → full penalty
        );
        let expected_diff = 0.6 * 1.0 * crate::agent::CLASS_TENSION_WEIGHT;
        assert!((sat_rich - sat_poor - expected_diff).abs() < 0.01,
            "Rich-poor diff {}, expected {}", sat_rich - sat_poor, expected_diff);
    }

    #[test]
    fn test_class_tension_zero_gini_no_penalty() {
        let shock = CivShock::default();
        let sat_base = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock, [0, 1, 2], [0, 1, 2], 0xFF, 0xFF, false, 0.0,
            0.0, // gini = 0 → no class tension
            0.0, // poorest
        );
        let sat_no_wealth = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock, [0, 1, 2], [0, 1, 2], 0xFF, 0xFF, false, 0.0,
            0.0, // gini = 0
            0.5, // middle
        );
        assert!((sat_base - sat_no_wealth).abs() < 0.001,
            "Zero Gini should produce no class tension penalty");
    }

    #[test]
    fn test_class_tension_priority_clamping() {
        let shock = CivShock::default();
        // Max cultural mismatch (0.15) + religious mismatch (0.10) + persecution (0.15) = 0.40
        // Class tension should be fully eaten by priority clamping
        let sat = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock,
            [4, 3, 2], [0, 1, 5], // full cultural mismatch (distance 3 → 0.15)
            3, 5,                  // religious mismatch (0.10)
            false,
            1.0,                   // max persecution (0.15)
            1.0,                   // max gini
            0.0,                   // poorest agent → would be 0.15 class tension
        );
        // Three core terms = 0.40 = cap. Class tension should be zeroed out.
        // Same result with or without class tension at cap:
        let sat_no_class = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &shock,
            [4, 3, 2], [0, 1, 5],
            3, 5,
            false,
            1.0,
            0.0, // zero gini → zero class tension
            0.0,
        );
        assert!((sat - sat_no_class).abs() < 0.001,
            "Class tension should be zero when three core terms hit cap");
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p chronicler-agents -- satisfaction::m41_tests`
Expected: FAIL — `compute_satisfaction_with_culture` doesn't accept gini/percentile params

- [ ] **Step 3: Add gini_coefficient and wealth_percentile parameters**

In `satisfaction.rs`, add two parameters to `compute_satisfaction_with_culture` signature, after `persecution_intensity: f32` (line 147):

```rust
    gini_coefficient: f32,
    wealth_percentile: f32,
```

- [ ] **Step 4: Implement priority clamping**

Replace the penalty cap logic (around line 185) with:

```rust
    // M41: class tension penalty — poor agents in unequal civs
    let class_tension_pen = gini_coefficient
        * (1.0 - wealth_percentile)
        * crate::agent::CLASS_TENSION_WEIGHT;

    // Priority clamping (Decision 3): core identity/persecution terms first,
    // class tension takes whatever budget remains under the 0.40 cap.
    let three_term = cultural_pen + religious_pen + penalty;
    let class_tension_clamped = class_tension_pen.min((crate::agent::PENALTY_CAP - three_term).max(0.0));
    let total_non_eco_penalty = (three_term + class_tension_clamped).min(crate::agent::PENALTY_CAP);
    (base_sat - total_non_eco_penalty + temple_bonus).clamp(0.0, 1.0)
```

(This replaces the old `let total_non_eco_penalty = apply_penalty_cap(cultural_pen + religious_pen + penalty);` and the `(base_sat - total_non_eco_penalty + temple_bonus).clamp(0.0, 1.0)` return line.)

- [ ] **Step 5: Update ALL call sites of compute_satisfaction_with_culture**

**Existing test calls that must be updated** — append `, 0.0, 0.5` (zero gini, middle percentile) to each:

- `chronicler-agents/src/satisfaction.rs` — 5 existing calls in `m36_tests` (line 281) and `m37_tests` (lines 300, 308, 321, 329)
- `chronicler-agents/tests/satisfaction_m38a.rs` — 4 calls (lines 44, 54, 75, 85)

**Production call site:**

In `tick.rs` `update_satisfaction()`, update the call at line 418 to pass the new params. Change the function signature to accept `wealth_percentiles: &[f32]`:

```rust
fn update_satisfaction(pool: &mut AgentPool, regions: &[RegionState], signals: &TickSignals, wealth_percentiles: &[f32]) {
```

In the closure, after `let shock = ...` (line 410), add:

```rust
                        let gini = civ_sig.map_or(0.0, |c| c.gini_coefficient);
                        let wealth_pct = wealth_percentiles[slot];
```

Update the `compute_satisfaction_with_culture` call (line 418) to add the two new arguments at the end:

```rust
                        let sat = satisfaction::compute_satisfaction_with_culture(
                            occ,
                            region.soil,
                            region.water,
                            civ_stability,
                            ds_ratio,
                            pop_over_cap,
                            civ_at_war,
                            region_contested,
                            occ_matches,
                            is_displaced,
                            region.trade_route_count,
                            faction_influence,
                            &shock,
                            agent_values,
                            region.controller_values,
                            pool_ref.beliefs[slot],
                            region.majority_belief,
                            region.has_temple,
                            region.persecution_intensity,
                            gini,
                            wealth_pct,
                        );
```

Update the call site in `tick_agents()` where `update_satisfaction` is called (line 73):

```rust
    update_satisfaction(pool, regions, signals, &wealth_percentiles);
```

- [ ] **Step 6: Run all satisfaction tests**

Run: `cargo test -p chronicler-agents -- satisfaction`
Expected: all tests PASS (existing + new M41 tests)

- [ ] **Step 7: Run all tick tests**

Run: `cargo test -p chronicler-agents`
Expected: full crate PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/satisfaction_m38a.rs
git commit -m "M41: class tension penalty with priority clamping in satisfaction"
```

---

## Chunk 3: Python Integration (Tasks 6–8)

### Task 6: Conquest Signal — Python Side

**Files:**
- Modify: `src/chronicler/action_engine.py:116-117,451-454` (set conquest flag on world)
- Modify: `src/chronicler/simulation.py:1211-1251` (clear transient, pass to bridge)
- Modify: `src/chronicler/agent_bridge.py:236-317` (read from world, add to signals batch)

**Approach:** Use a transient attribute `world._conquered_this_turn: set[int]` populated inside `resolve_war` only (WAR path), read and cleared in `simulation.py` before the agent tick. EXPAND claims unclaimed territory (settlement, no defender, no plunder) and does NOT set the conquest flag — `CONQUEST_BONUS` is narratively a looting spike from defeating an enemy, not planting a flag on empty land.

- [ ] **Step 1: Track conquests in action_engine — WAR path only**

In `action_engine.py`, at the WAR resolution (line 451, after `contested.controller = attacker.name`):

```python
            if not hasattr(world, '_conquered_this_turn'):
                world._conquered_this_turn = set()
            world._conquered_this_turn.add(world.civilizations.index(attacker))
```

**Note:** EXPAND (line 116) is intentionally excluded — settlement of unclaimed land is not conquest.

- [ ] **Step 2: Read and clear conquest set in simulation.py**

In `simulation.py`, after `phase_action` returns (line 1212), read and clear the transient:

```python
        conquered_civs = getattr(world, '_conquered_this_turn', set())
        world._conquered_this_turn = set()  # clear BEFORE passing to bridge (transient signal rule)
        conquered_dict = {i: True for i in conquered_civs}
```

Pass `conquered=conquered_dict` to the agent bridge tick (both hybrid and non-hybrid call sites, lines 1246 and 1251).

- [ ] **Step 3: Add conquered_this_turn to build_signals**

In `agent_bridge.py`, update `build_signals` signature:

```python
def build_signals(world: WorldState, shocks: list | None = None,
                  demands: dict | None = None,
                  conquered: dict[int, bool] | None = None) -> pa.RecordBatch:
```

Add `conquered_flags = []` after the existing builder lists (line 261).

In the per-civ loop, after `mean_ltrait.append(pm[2])` (line 294):

```python
        conquered_flags.append((conquered or {}).get(i, False))
```

In the return dict (line 296), after `mean_loyalty_trait`:

```python
        "conquered_this_turn": pa.array(conquered_flags, type=pa.bool_()),
```

- [ ] **Step 4: Update AgentBridge.tick to forward conquered**

```python
    def tick(self, world: WorldState, shocks=None, demands=None, conquered=None) -> list:
        self._sim.set_region_state(build_region_batch(world))
        signals = build_signals(world, shocks=shocks, demands=demands, conquered=conquered)
```

Update `simulation.py` call sites to pass `conquered=conquered_dict`.

- [ ] **Step 5: Run existing Python tests to verify no breakage**

Run: `python -m pytest tests/ -x -q --timeout=60`
Expected: existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/simulation.py src/chronicler/agent_bridge.py
git commit -m "M41: wire conquered_this_turn signal from action engine through FFI"
```

---

### Task 7: Gini Computation — Python Side

**Files:**
- Modify: `src/chronicler/agent_bridge.py:339-400` (compute Gini from snapshot, add to signals)
- Test: `tests/test_agent_bridge.py` (or existing test file)

- [ ] **Step 1: Write failing test for compute_gini**

Create or add to `tests/test_wealth.py`:

```python
import numpy as np


def test_compute_gini_uniform():
    """All agents same wealth → Gini = 0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([5.0, 5.0, 5.0, 5.0])
    assert abs(compute_gini(arr)) < 0.001


def test_compute_gini_maximal():
    """One agent has everything → Gini near 1.0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([0.0, 0.0, 0.0, 100.0])
    assert compute_gini(arr) > 0.7


def test_compute_gini_moderate():
    """Mixed distribution → Gini in 0.2-0.6 range."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([1.0, 2.0, 5.0, 10.0, 50.0])
    g = compute_gini(arr)
    assert 0.2 < g < 0.7, f"Expected moderate Gini, got {g}"


def test_compute_gini_empty():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([])
    assert compute_gini(arr) == 0.0


def test_compute_gini_single():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([10.0])
    assert compute_gini(arr) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_wealth.py -v`
Expected: FAIL — `compute_gini` doesn't exist

- [ ] **Step 3: Implement compute_gini**

In `agent_bridge.py`, add near the top (after imports):

```python
import numpy as np


def compute_gini(wealth_array: np.ndarray) -> float:
    """Gini coefficient from a 1D array of non-negative values."""
    sorted_w = np.sort(wealth_array)
    n = len(sorted_w)
    if n == 0 or sorted_w.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2.0 * (index * sorted_w).sum() / (n * sorted_w.sum())) - (n + 1) / n)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_wealth.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Wire Gini computation into AgentBridge.tick**

In `agent_bridge.py` `AgentBridge.tick()`, after the snapshot is read (around line 352), add Gini computation. Store it on the bridge instance so it's available for the *next* turn's signals (one-turn lag, Decision 15):

Add an instance variable in `__init__`:

```python
        self._gini_by_civ: dict[int, float] = {}  # M41: per-civ Gini from last tick
```

In the `tick()` method, after `self.displacement_by_region` computation (around line 365), in hybrid mode. **Note:** Gini is only computed in hybrid mode because the agent pool (and thus wealth snapshot) does not exist in `--agents=off` mode.

```python
            # M41: compute per-civ Gini from wealth snapshot (hybrid mode only)
            if "wealth" in snap.schema.names:
                wealth_col = snap.column("wealth").to_numpy()
                civ_col = snap.column("civ_affinity").to_numpy()
                new_gini: dict[int, float] = {}
                for civ_id in np.unique(civ_col):
                    mask = civ_col == civ_id
                    civ_wealth = wealth_col[mask]
                    new_gini[int(civ_id)] = compute_gini(civ_wealth)
                self._gini_by_civ = new_gini
```

Then update `build_signals` to also accept and include `gini_by_civ`:

```python
def build_signals(world: WorldState, shocks: list | None = None,
                  demands: dict | None = None,
                  conquered: dict[int, bool] | None = None,
                  gini_by_civ: dict[int, float] | None = None) -> pa.RecordBatch:
```

Add `gini_vals = []` alongside the other builder lists (near line 261).

In the per-civ loop:

```python
        gini_vals.append((gini_by_civ or {}).get(i, 0.0))
```

In the return dict:

```python
        "gini_coefficient": pa.array(gini_vals, type=pa.float32()),
```

Update the `tick()` method to pass `gini_by_civ=self._gini_by_civ` to `build_signals`. This implements the one-turn lag (Decision 15) — Gini computed from turn N's snapshot feeds turn N+1's signals.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -x -q --timeout=60`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_wealth.py
git commit -m "M41: compute per-civ Gini from wealth snapshot, wire into signals"
```

---

### Task 8: Conquest Signal — Transient Signal Tests

**Files:**
- Test: `tests/test_wealth.py`

Per CLAUDE.md: "Every new transient signal requires a 2+ turn integration test verifying the value resets after consumption."

- [ ] **Step 1: Write unit test for build_signals transient behavior**

Add to `tests/test_wealth.py`:

```python
def test_conquered_this_turn_build_signals():
    """build_signals produces correct conquered_this_turn per call."""
    import pyarrow as pa
    from chronicler.agent_bridge import build_signals
    from tests.conftest import make_test_world  # use existing fixture

    world = make_test_world()

    # With conquest
    batch1 = build_signals(world, conquered={0: True})
    assert batch1.column("conquered_this_turn").to_pylist()[0] is True

    # Without conquest — fresh call, no persistence
    batch2 = build_signals(world, conquered=None)
    assert batch2.column("conquered_this_turn").to_pylist()[0] is False
```

- [ ] **Step 2: Write 2+ turn integration test for full transient lifecycle**

This test verifies the end-to-end path: `world._conquered_this_turn` is populated by `phase_action`, read and cleared in `simulation.py`, and does not persist to the next turn.

```python
def test_conquered_this_turn_transient_two_turns():
    """conquered_this_turn resets after one turn (CLAUDE.md transient signal rule).

    Verifies the full path: action_engine sets world._conquered_this_turn,
    simulation.py reads and clears it before passing to agent bridge.
    """
    from chronicler.models import WorldState

    world = make_test_world()

    # Simulate conquest on turn 1
    world._conquered_this_turn = {0}

    # simulation.py's clearing pattern
    conquered_civs = getattr(world, '_conquered_this_turn', set())
    world._conquered_this_turn = set()
    assert 0 in conquered_civs, "Turn 1: conquest should be detected"

    # Turn 2: no action engine ran, attribute should be empty
    conquered_civs_2 = getattr(world, '_conquered_this_turn', set())
    assert len(conquered_civs_2) == 0, "Turn 2: conquest should NOT persist"
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_wealth.py -v -k conquered`
Expected: both tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_wealth.py
git commit -m "M41: add transient signal tests for conquered_this_turn (unit + integration)"
```

---

## Chunk 4: Analytics, Narration & Final Verification (Tasks 9–11)

### Task 9: Analytics — Live Wealth Stats

**Files:**
- Modify: `src/chronicler/agent_bridge.py` (compute wealth stats during tick, store on bridge)
- Modify: `src/chronicler/analytics.py` (add `extract_wealth` that reads from bridge)

**Note:** The existing analytics pipeline (`generate_report`) operates on serialized bundles, not live simulation state. M41 wealth stats are computed from live agent snapshots during simulation and stored on the bridge for the bundle assembly step to include. Full bundle integration (serializing wealth stats into `chronicle_bundle.json`) is a follow-up if needed — M41 makes the data available; bundle format changes are deferred.

- [ ] **Step 1: Store wealth stats on AgentBridge during tick**

In `agent_bridge.py` `__init__`, add:

```python
        self._wealth_stats: dict[int, dict] = {}  # M41: per-civ wealth stats from last tick
```

In the hybrid `tick()` method, alongside the Gini computation (added in Task 7), compute additional stats:

```python
            # M41: wealth analytics (computed alongside Gini)
            # numpy already imported at module level (Task 7)
            if "wealth" in snap.schema.names:
                wealth_col = snap.column("wealth").to_numpy()
                civ_col = snap.column("civ_affinity").to_numpy()
                occ_col = snap.column("occupation").to_numpy()
                occ_names = ["farmer", "soldier", "merchant", "scholar", "priest"]
                stats: dict[int, dict] = {}
                for civ_id in np.unique(civ_col):
                    mask = civ_col == civ_id
                    civ_wealth = wealth_col[mask]
                    civ_occ = occ_col[mask]
                    wealth_by_occ = {}
                    for occ_idx, name in enumerate(occ_names):
                        occ_mask = civ_occ == occ_idx
                        if occ_mask.any():
                            wealth_by_occ[name] = float(np.mean(civ_wealth[occ_mask]))
                    stats[int(civ_id)] = {
                        "gini": self._gini_by_civ.get(int(civ_id), 0.0),
                        "mean": float(np.mean(civ_wealth)),
                        "median": float(np.median(civ_wealth)),
                        "std": float(np.std(civ_wealth)),
                        "by_occupation": wealth_by_occ,
                    }
                self._wealth_stats = stats
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "M41: compute and store per-civ wealth stats during agent tick"
```

---

### Task 10: Narration Context

**Files:**
- Modify: `src/chronicler/models.py:662-668` (AgentContext is defined here, NOT in narrative.py)
- Modify: `src/chronicler/narrative.py:124-210` (build_agent_context_for_moment — add gini_by_civ param)

- [ ] **Step 1: Add gini_coefficient to AgentContext model**

In `models.py`, add to the `AgentContext` class (after `displacement_fraction`):

```python
    gini_coefficient: float = 0.0
```

- [ ] **Step 2: Add gini_by_civ parameter to build_agent_context_for_moment**

In `narrative.py`, update `build_agent_context_for_moment()` signature to accept `gini_by_civ: dict[int, float] | None = None`.

In the function body, compute the gini value for the relevant civ:

```python
    gini = (gini_by_civ or {}).get(civ_idx, 0.0)
```

Pass `gini_coefficient=gini` when constructing the `AgentContext` (around line 205).

- [ ] **Step 3: Update all callers of build_agent_context_for_moment**

Find all call sites (grep for `build_agent_context_for_moment`) and pass `gini_by_civ=agent_bridge._gini_by_civ` where the bridge is available, or `gini_by_civ=None` where it isn't.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py src/chronicler/narrative.py
git commit -m "M41: add gini_coefficient to AgentContext for narration"
```

---

### Task 11: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -x -q --timeout=120`
Expected: all tests PASS

Run: `cargo test -p chronicler-agents`
Expected: all Rust tests PASS

- [ ] **Step 2: Run 200-seed Tier 2 regression**

```bash
python scripts/p4_validate.py --seeds 200 --turns 300 --agents hybrid
```

Compare before/after: satisfaction distribution, loyalty, rebellion rate, Gini spread.

- [ ] **Step 3: Verify --agents=off bit-identical**

```bash
python -m chronicler --seed 42 --turns 100 --agents=off > before.json
# (after M41 changes)
python -m chronicler --seed 42 --turns 100 --agents=off > after.json
diff before.json after.json
```

Expected: identical output

- [ ] **Step 4: Final commit with integration test results**

```bash
git add tests/test_wealth.py
git commit -m "M41: Wealth & Class Stratification — integration test results"
```
