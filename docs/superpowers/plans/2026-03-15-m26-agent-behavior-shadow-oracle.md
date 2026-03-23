# M26: Agent Behavior + Shadow Oracle Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add agent decision-making (satisfaction, rebellion, migration, occupation switching, loyalty drift), satisfaction-gated fertility, updated ecological stress, and shadow mode with oracle comparison framework.

**Architecture:** Four new Rust modules (`satisfaction.rs`, `behavior.rs`, `demographics.rs`, `signals.rs`) plug into the existing `tick.rs` orchestrator. `pool.rs` gains setters for satisfaction/loyalty/occupation/skills. Python side adds `shadow.py` (Arrow IPC logger) and `shadow_oracle.py` (KS/AD comparison). Agent tick runs in shadow mode — outputs compared against aggregate model but discarded.

**Tech Stack:** Rust (stable), PyO3, pyo3-arrow, rand_chacha, rayon, maturin, Python 3.12, pyarrow, scipy, numpy, pytest, criterion

**Spec:** `docs/superpowers/specs/2026-03-15-m26-agent-behavior-shadow-oracle-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `chronicler-agents/src/agent.rs` | Fertility/decision/skill constants, MAX_CIVS assert | Modify |
| `chronicler-agents/src/region.rs` | Add adjacency_mask, controller_civ, trade_route_count | Modify |
| `chronicler-agents/src/satisfaction.rs` | Branchless satisfaction formula, demand/supply ratios | Create |
| `chronicler-agents/src/behavior.rs` | Decision model: rebel → migrate → switch → drift | Create |
| `chronicler-agents/src/demographics.rs` | Updated mortality (new eco stress) + fertility | Create |
| `chronicler-agents/src/signals.rs` | Parse civ-signals + extended region-state Arrow batches | Create |
| `chronicler-agents/src/tick.rs` | Orchestrate: skill growth → satisfaction → decisions → demographics | Modify |
| `chronicler-agents/src/pool.rs` | Add setters, skill growth, populated compute_aggregates | Modify |
| `chronicler-agents/src/ffi.rs` | Accept signals, return populated events, extended set_region_state | Modify |
| `chronicler-agents/src/lib.rs` | Re-export new modules | Modify |
| `src/chronicler/agent_bridge.py` | Add build_signals(), shadow mode support | Modify |
| `src/chronicler/shadow.py` | ShadowLogger: Arrow IPC per-turn comparison writer | Create |
| `src/chronicler/shadow_oracle.py` | KS/AD comparison framework, OracleReport | Create |
| `tests/test_agent_bridge.py` | Shadow mode integration tests, signal building tests | Modify |
| `tests/test_shadow_oracle.py` | Oracle framework tests with synthetic data | Create |

---

## Chunk 1: Ecological Stress + Satisfaction Module

### Task 1: Add M26 Constants to agent.rs

**Files:**
- Modify: `chronicler-agents/src/agent.rs`

- [ ] **Step 1: Write the test for MAX_CIVS compile-time assert**

This is a compile-time assert — if it fails, the crate won't compile. No runtime test needed. Just add the constants and assert.

- [ ] **Step 2: Add constants and compile-time assert**

```rust
// Add after existing constants in agent.rs:

pub const MAX_CIVS: usize = 255;
const _: () = assert!(MAX_CIVS <= u8::MAX as usize);

// Fertility
pub const FERTILITY_AGE_MIN: u16 = 16;
pub const FERTILITY_AGE_MAX: u16 = 45;
pub const FERTILITY_BASE_FARMER: f32 = 0.03;
pub const FERTILITY_BASE_OTHER: f32 = 0.015;
pub const FERTILITY_SATISFACTION_THRESHOLD: f32 = 0.4;

// Decision thresholds
pub const REBEL_LOYALTY_THRESHOLD: f32 = 0.2;
pub const REBEL_SATISFACTION_THRESHOLD: f32 = 0.2;
pub const REBEL_MIN_COHORT: usize = 5;
pub const MIGRATE_SATISFACTION_THRESHOLD: f32 = 0.3;
pub const OCCUPATION_SWITCH_UNDERSUPPLY: f32 = 1.5;
pub const OCCUPATION_SWITCH_OVERSUPPLY: f32 = 0.5;
pub const LOYALTY_DRIFT_RATE: f32 = 0.02;
pub const LOYALTY_RECOVERY_RATE: f32 = 0.01;
pub const LOYALTY_FLIP_THRESHOLD: f32 = 0.3;

// Skill
pub const SKILL_RESET_ON_SWITCH: f32 = 0.3;
pub const SKILL_GROWTH_PER_TURN: f32 = 0.05;
pub const SKILL_MAX: f32 = 1.0;
pub const SKILL_NEWBORN: f32 = 0.1;

// War
pub const WAR_CASUALTY_MULTIPLIER: f32 = 2.0;
```

- [ ] **Step 3: Verify it compiles**

Run: `cd chronicler-agents && cargo check`
Expected: compiles with no errors.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m26): add M26 constants — fertility, decisions, skills, war casualty"
```

---

### Task 2: Swap Ecological Stress Formula in tick.rs

**Files:**
- Modify: `chronicler-agents/src/tick.rs`

- [ ] **Step 1: Update the ecological stress tests to expect M26 formula**

In `tick.rs` `mod tests`, update:

```rust
#[test]
fn test_ecological_stress_healthy() {
    let r = make_healthy_region(0);
    // soil=0.8, water=0.6 → both above 0.5 → stress = 1.0
    assert!((ecological_stress(&r) - 1.0).abs() < 0.01);
}

#[test]
fn test_ecological_stress_collapsed() {
    let mut r = make_healthy_region(0);
    r.soil = 0.0;
    r.water = 0.0;
    // max(0, 0.5-0.0) + max(0, 0.5-0.0) = 0.5 + 0.5 = 1.0 → stress = 2.0
    assert!((ecological_stress(&r) - 2.0).abs() < 0.01);
}

#[test]
fn test_ecological_stress_partial() {
    let mut r = make_healthy_region(0);
    r.soil = 0.3;  // below 0.5
    r.water = 0.7; // above 0.5
    // max(0, 0.5-0.3) + max(0, 0.5-0.7) = 0.2 + 0.0 = 0.2 → stress = 1.2
    assert!((ecological_stress(&r) - 1.2).abs() < 0.01);
}
```

- [ ] **Step 2: Run tests to verify they fail (old formula)**

Run: `cd chronicler-agents && cargo test --lib tick::tests`
Expected: `test_ecological_stress_healthy` FAILS (old formula returns 1.6, new expects 1.0).

- [ ] **Step 3: Replace the ecological_stress function**

```rust
fn ecological_stress(region: &RegionState) -> f32 {
    // M26 per-variable formula (replaces M25 averaged formula).
    // Range: 1.0 (both soil/water >= 0.5) to 2.0 (both at 0.0).
    let soil_stress = (0.5 - region.soil) * ((0.5 - region.soil) > 0.0) as i32 as f32;
    let water_stress = (0.5 - region.water) * ((0.5 - region.water) > 0.0) as i32 as f32;
    1.0 + soil_stress + water_stress
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test --lib tick::tests`
Expected: all tick tests PASS. Note: `test_tick_agents_reduces_population` still passes because eco stress with soil=0.8, water=0.6 is now 1.0 (lower than old 1.6), but elder mortality at 0.05 × 1.0 = 5% per tick still guarantees deaths in 500 agents.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m26): swap ecological stress to per-variable formula (range 1.0-2.0)"
```

---

### Task 3: Add Pool Setters and Skill Growth

**Files:**
- Modify: `chronicler-agents/src/pool.rs`

- [ ] **Step 1: Write tests for new setters and skill growth**

Add to `pool.rs` `mod tests`:

```rust
#[test]
fn test_set_satisfaction() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    assert!((pool.satisfaction(slot) - 0.5).abs() < 0.01); // default
    pool.set_satisfaction(slot, 0.8);
    assert!((pool.satisfaction(slot) - 0.8).abs() < 0.01);
}

#[test]
fn test_set_loyalty() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Soldier, 30);
    pool.set_loyalty(slot, 0.2);
    assert!((pool.loyalty(slot) - 0.2).abs() < 0.01);
}

#[test]
fn test_set_occupation() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    pool.set_occupation(slot, Occupation::Merchant as u8);
    assert_eq!(pool.occupation(slot), Occupation::Merchant as u8);
}

#[test]
fn test_set_region() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    pool.set_region(slot, 3);
    assert_eq!(pool.region(slot), 3);
}

#[test]
fn test_set_civ_affinity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    pool.set_civ_affinity(slot, 5);
    assert_eq!(pool.civ_affinity(slot), 5);
}

#[test]
fn test_set_displacement_turns() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    pool.set_displacement_turns(slot, 3);
    assert_eq!(pool.displacement_turns[slot], 3);
}

#[test]
fn test_grow_skill() {
    use crate::agent::{SKILL_GROWTH_PER_TURN, SKILL_MAX};
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Soldier, 25); // occ=1
    // Initial skill for soldier slot (slot*5 + 1) = 0.0
    assert!((pool.skills[slot * 5 + 1]).abs() < 0.01);
    pool.grow_skill(slot);
    assert!((pool.skills[slot * 5 + 1] - SKILL_GROWTH_PER_TURN).abs() < 0.01);
    // Grow to max
    pool.skills[slot * 5 + 1] = SKILL_MAX - 0.01;
    pool.grow_skill(slot);
    assert!((pool.skills[slot * 5 + 1] - SKILL_MAX).abs() < 0.01);
}

#[test]
fn test_loyalty_accessor() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    assert!((pool.loyalty(slot) - 0.5).abs() < 0.01); // default
}

#[test]
fn test_origin_region_accessor() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(3, 0, Occupation::Farmer, 25);
    assert_eq!(pool.origin_region(slot), 3);
}

#[test]
fn test_displacement_turns_accessor() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
    assert_eq!(pool.displacement_turns(slot), 0); // default
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test --lib pool::tests`
Expected: FAIL — `set_satisfaction`, `set_loyalty`, `set_occupation`, `set_region`, `set_civ_affinity`, `set_displacement_turns`, `grow_skill`, `loyalty`, `origin_region`, `displacement_turns` methods don't exist.

- [ ] **Step 3: Implement setters, accessors, and skill growth**

Add to `pool.rs` impl block:

```rust
// --- Setters ---

#[inline]
pub fn set_satisfaction(&mut self, slot: usize, val: f32) {
    self.satisfactions[slot] = val;
}

#[inline]
pub fn set_loyalty(&mut self, slot: usize, val: f32) {
    self.loyalties[slot] = val;
}

#[inline]
pub fn set_occupation(&mut self, slot: usize, occ: u8) {
    self.occupations[slot] = occ;
}

#[inline]
pub fn set_region(&mut self, slot: usize, region: u16) {
    self.regions[slot] = region;
}

#[inline]
pub fn set_civ_affinity(&mut self, slot: usize, civ: u8) {
    self.civ_affinities[slot] = civ;
}

#[inline]
pub fn set_displacement_turns(&mut self, slot: usize, turns: u8) {
    self.displacement_turns[slot] = turns;
}

// --- Additional accessors ---

#[inline]
pub fn loyalty(&self, slot: usize) -> f32 {
    self.loyalties[slot]
}

#[inline]
pub fn origin_region(&self, slot: usize) -> u16 {
    self.origin_regions[slot]
}

#[inline]
pub fn displacement_turns(&self, slot: usize) -> u8 {
    self.displacement_turns[slot]
}

// --- Skill ---

/// Grow current occupation's skill by SKILL_GROWTH_PER_TURN, capped at SKILL_MAX.
pub fn grow_skill(&mut self, slot: usize) {
    use crate::agent::{SKILL_GROWTH_PER_TURN, SKILL_MAX};
    let occ = self.occupations[slot] as usize;
    let idx = slot * 5 + occ;
    self.skills[idx] = (self.skills[idx] + SKILL_GROWTH_PER_TURN).min(SKILL_MAX);
}

/// Get skill value for a specific occupation.
pub fn skill(&self, slot: usize, occ: usize) -> f32 {
    self.skills[slot * 5 + occ]
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test --lib pool::tests`
Expected: all pool tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "feat(m26): add pool setters, accessors, and skill growth"
```

---

### Task 4: Create satisfaction.rs — Branchless Satisfaction Formula

**Files:**
- Create: `chronicler-agents/src/satisfaction.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `pub mod satisfaction;`)

- [ ] **Step 1: Write tests for satisfaction computation**

Create `chronicler-agents/src/satisfaction.rs` with tests first:

```rust
//! Branchless satisfaction formula — computes per-agent satisfaction from
//! ecology, civ state, and occupation context.

/// Compute satisfaction for a single agent. All inputs pre-fetched.
/// Branchless: bool-as-f32 masks for auto-vectorization.
pub fn compute_satisfaction(
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
) -> f32 {
    todo!()
}

/// Target occupation ratios for a region based on terrain and ecology.
/// Returns [farmer, soldier, merchant, scholar, priest] ratios summing to ~1.0.
/// Cold path — called once per region per tick, not per agent.
pub fn target_occupation_ratio(terrain: u8, soil: f32, _water: f32) -> [f32; 5] {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_farmer_healthy_ecology_peacetime() {
        // Farmer in good ecology (soil=0.8, water=0.7), stable civ (80),
        // balanced supply, no war, no displacement
        let sat = compute_satisfaction(
            0, 0.8, 0.7, 80, 0.0, 0.8, false, false, false, false, 0, 0.0,
        );
        // base = 0.4 + 0.8*0.3 + 0.7*0.2 = 0.4 + 0.24 + 0.14 = 0.78
        // + stability_bonus = 80/200 = 0.40
        // + ds_bonus = 0.0
        // - overcrowding = 0.0 (0.8 < 1.0)
        // - war_pen = 0.0
        // + faction = 0.0
        // - displacement = 0.0
        // total = 1.18 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_farmer_bad_ecology_wartime() {
        // Farmer in bad ecology (soil=0.2, water=0.1), unstable civ (20),
        // oversupplied, at war + contested, displaced
        let sat = compute_satisfaction(
            0, 0.2, 0.1, 20, -0.5, 1.3, true, true, false, true, 0, 0.0,
        );
        // base = 0.4 + 0.2*0.3 + 0.1*0.2 = 0.4 + 0.06 + 0.02 = 0.48
        // + stability = 20/200 = 0.10
        // + ds_bonus = -0.5*0.2 = -0.10 (clamped to -0.10)
        // - overcrowding = (1.3-1.0)*0.3 = 0.09
        // - war_pen = 0.15 + 0.10 = 0.25
        // + faction = 0.0
        // - displacement = 0.10
        // total = 0.48 + 0.10 - 0.10 - 0.09 - 0.25 + 0.0 - 0.10 = 0.04
        assert!(sat > 0.0 && sat < 0.15);
    }

    #[test]
    fn test_soldier_with_faction_alignment() {
        // Soldier, military faction dominant (influence=0.6), faction matches
        let sat = compute_satisfaction(
            1, 0.5, 0.5, 60, 0.0, 0.9, false, false, true, false, 0, 0.6,
        );
        // base = 0.5 + 0.6*0.3 = 0.68
        // + stability = 60/200 = 0.30
        // + ds = 0.0
        // - overcrowding = 0.0
        // - war = 0.0
        // + faction = 0.05
        // - displacement = 0.0
        // total = 1.03 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_merchant_with_trade_routes() {
        // Merchant with 2 trade routes, merchant faction
        let sat = compute_satisfaction(
            2, 0.5, 0.5, 50, 0.3, 0.7, false, false, true, false, 2, 0.4,
        );
        // base = 0.4 + (2/3).min(1.0)*0.3 = 0.4 + 0.667*0.3 = 0.4 + 0.20 = 0.60
        // + stability = 50/200 = 0.25
        // + ds = 0.3*0.2 = 0.06
        // - overcrowding = 0.0
        // - war = 0.0
        // + faction = 0.05
        // - displacement = 0.0
        // total = 0.96
        assert!(sat > 0.90 && sat <= 1.0);
    }

    #[test]
    fn test_priest_unstable_civ() {
        // Priest in unstable civ (stability=15)
        let sat = compute_satisfaction(
            4, 0.5, 0.5, 15, 0.0, 0.8, false, false, false, false, 0, 0.0,
        );
        // base = 0.6 - (1.0 - 15/100)*0.2 = 0.6 - 0.85*0.2 = 0.6 - 0.17 = 0.43
        // + stability = 15/200 = 0.075
        // total ≈ 0.505
        assert!(sat > 0.45 && sat < 0.60);
    }

    #[test]
    fn test_satisfaction_clamps_to_zero() {
        // Extreme negatives shouldn't go below 0
        let sat = compute_satisfaction(
            0, 0.0, 0.0, 0, -1.0, 2.0, true, true, false, true, 0, 0.0,
        );
        assert!(sat >= 0.0);
    }

    #[test]
    fn test_target_occupation_ratio_plains() {
        let ratios = target_occupation_ratio(0, 0.8, 0.6); // Plains, good soil
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.01);
        assert!(ratios[0] > 0.5); // farmers dominant on plains
    }

    #[test]
    fn test_target_occupation_ratio_coast() {
        let ratios = target_occupation_ratio(2, 0.5, 0.5); // Coast
        assert!(ratios[2] > 0.10); // merchants boosted on coast
    }

    #[test]
    fn test_target_occupation_ratio_desert_bad_soil() {
        let ratios = target_occupation_ratio(4, 0.2, 0.3); // Desert, bad soil
        assert!(ratios[0] < 0.45); // farmers reduced
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.02);
    }
}
```

- [ ] **Step 2: Add module to lib.rs**

Add `pub mod satisfaction;` to `chronicler-agents/src/lib.rs`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test --lib satisfaction::tests`
Expected: FAIL — `todo!()` panics.

- [ ] **Step 4: Implement compute_satisfaction**

Replace `todo!()` in `compute_satisfaction`:

```rust
pub fn compute_satisfaction(
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
) -> f32 {
    let base = match occupation {
        0 => 0.4 + soil * 0.3 + water * 0.2,                      // Farmer
        1 => 0.5 + faction_influence * 0.3,                        // Soldier
        2 => 0.4 + (trade_routes as f32 / 3.0).min(1.0) * 0.3,   // Merchant
        3 => 0.5 + faction_influence * 0.2,                        // Scholar
        _ => 0.6 - (1.0 - civ_stability as f32 / 100.0) * 0.2,   // Priest
    };

    let stability_bonus = civ_stability as f32 / 200.0;

    let ds_raw = demand_supply_ratio * 0.2;
    let ds_bonus = ds_raw.clamp(-0.2, 0.2);

    let overcrowding_raw = (pop_over_capacity - 1.0) * 0.3;
    let overcrowding = overcrowding_raw * (overcrowding_raw > 0.0) as i32 as f32;

    let war_pen = 0.15 * civ_at_war as i32 as f32
                + 0.10 * region_contested as i32 as f32;

    let faction_bonus = 0.05 * occ_matches_faction as i32 as f32;

    let displacement_pen = 0.10 * is_displaced as i32 as f32;

    (base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen)
        .clamp(0.0, 1.0)
}
```

- [ ] **Step 5: Implement target_occupation_ratio**

Replace `todo!()` in `target_occupation_ratio`:

```rust
pub fn target_occupation_ratio(terrain: u8, soil: f32, _water: f32) -> [f32; 5] {
    // Base: farmer 0.60, soldier 0.15, merchant 0.10, scholar 0.10, priest 0.05
    let mut r = [0.60f32, 0.15, 0.10, 0.10, 0.05];

    // Terrain adjustments (cold path — runs once per region, not per agent)
    match terrain {
        1 => { r[1] += 0.05; r[0] -= 0.05; }  // Mountains: more soldiers
        2 => { r[2] += 0.05; r[0] -= 0.05; }  // Coast: more merchants
        3 => { r[0] += 0.05; r[2] -= 0.05; }  // Forest: more farmers
        4 => { r[1] += 0.05; r[0] -= 0.10; r[4] += 0.05; } // Desert
        _ => {}
    }

    // Ecology pressure
    if soil < 0.3 {
        r[0] -= 0.10;
        r[1] += 0.05;
        r[4] += 0.05;
    }

    r
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd chronicler-agents && cargo test --lib satisfaction::tests`
Expected: all 9 satisfaction tests PASS.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/lib.rs
git commit -m "feat(m26): add branchless satisfaction formula and occupation target ratios"
```

---

## Chunk 2: RegionState Extension + Demographics + Behavior Modules

### Task 5: Extend RegionState for M26 Fields

> **Moved before demographics** — `demographics.rs` test helper needs `adjacency_mask`, `controller_civ`, `trade_route_count` fields.

**Files:**
- Modify: `chronicler-agents/src/region.rs`

- [ ] **Step 1: Write test for new RegionState fields**

Add to `region.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_region_new_has_m26_defaults() {
        let r = RegionState::new(5);
        assert_eq!(r.adjacency_mask, 0);
        assert_eq!(r.controller_civ, 255); // uncontrolled
        assert_eq!(r.trade_route_count, 0);
    }

    #[test]
    fn test_adjacency_mask_check() {
        let mut r = RegionState::new(0);
        r.adjacency_mask = 0b1010; // adjacent to regions 1 and 3
        assert!(r.adjacency_mask & (1 << 1) != 0);
        assert!(r.adjacency_mask & (1 << 3) != 0);
        assert!(r.adjacency_mask & (1 << 2) == 0);
    }
}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd chronicler-agents && cargo test --lib region::tests`
Expected: FAIL — fields don't exist.

- [ ] **Step 3: Add fields to RegionState**

Update `RegionState` struct and `new()`:

```rust
#[derive(Clone, Debug)]
pub struct RegionState {
    pub region_id: u16,
    pub terrain: u8,
    pub carrying_capacity: u16,
    pub population: u16,
    pub soil: f32,
    pub water: f32,
    pub forest_cover: f32,
    // M26 additions
    pub adjacency_mask: u32,     // bitmask: bit i = adjacent to region i (≤32 regions)
    pub controller_civ: u8,      // civ_id controlling region (255 = uncontrolled)
    pub trade_route_count: u8,
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
            adjacency_mask: 0,
            controller_civ: 255,
            trade_route_count: 0,
        }
    }
}
```

- [ ] **Step 4: Fix all compilation errors from new fields**

Every `RegionState { ... }` literal in the codebase needs the three new fields. Grep for `RegionState {` and add defaults. Key locations:
- `tick.rs` test helper `make_healthy_region` → add `adjacency_mask: 0, controller_civ: 0, trade_route_count: 0`
- `ffi.rs` in `set_region_state` → add default values for new fields; also update the `else` branch (subsequent calls) to parse `controller_civ`, `adjacency_mask`, `trade_route_count` from the Arrow batch when present (default if column absent)
- `tests/determinism.rs` if it constructs RegionState directly

Run: `cd chronicler-agents && cargo test`
Expected: all existing tests PASS with new fields defaulted.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/determinism.rs
git commit -m "feat(m26): extend RegionState with adjacency_mask, controller_civ, trade_route_count"
```

---

### Task 6: Create demographics.rs — Updated Mortality + Fertility

**Files:**
- Create: `chronicler-agents/src/demographics.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `pub mod demographics;`)

- [ ] **Step 1: Write tests for ecological stress, mortality, and fertility**

Create `chronicler-agents/src/demographics.rs`:

```rust
//! Demographics: age-dependent mortality with M26 ecological stress + satisfaction-gated fertility.

use crate::agent::*;
use crate::region::RegionState;

pub fn ecological_stress(region: &RegionState) -> f32 {
    todo!()
}

/// War casualty multiplier applies to all soldier age brackets — intentional
/// divergence from roadmap draft which restricted to 20–60. Soldiers of any
/// age on an active front face elevated mortality.
pub fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool) -> f32 {
    todo!()
}

pub fn fertility_rate(age: u16, satisfaction: f32, occupation: u8, soil: f32) -> f32 {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(soil: f32, water: f32) -> RegionState {
        RegionState {
            region_id: 0, terrain: 0, carrying_capacity: 60, population: 40,
            soil, water, forest_cover: 0.3,
            adjacency_mask: 0, controller_civ: 0, trade_route_count: 0,
        }
    }

    // --- Ecological Stress ---

    #[test]
    fn test_eco_stress_healthy() {
        assert!((ecological_stress(&region(0.8, 0.7)) - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_both_low() {
        // soil=0.1, water=0.2 → 1.0 + 0.4 + 0.3 = 1.7
        assert!((ecological_stress(&region(0.1, 0.2)) - 1.7).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_collapsed() {
        assert!((ecological_stress(&region(0.0, 0.0)) - 2.0).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_one_bad() {
        // soil=0.3, water=0.6 → 1.0 + 0.2 + 0.0 = 1.2
        assert!((ecological_stress(&region(0.3, 0.6)) - 1.2).abs() < 0.01);
    }

    // --- Mortality ---

    #[test]
    fn test_mortality_young_peaceful() {
        let rate = mortality_rate(10, 1.0, false);
        assert!((rate - MORTALITY_YOUNG).abs() < 0.001);
    }

    #[test]
    fn test_mortality_adult_stressed() {
        let rate = mortality_rate(30, 1.5, false);
        assert!((rate - MORTALITY_ADULT * 1.5).abs() < 0.001);
    }

    #[test]
    fn test_mortality_soldier_at_war() {
        let rate = mortality_rate(30, 1.0, true);
        assert!((rate - MORTALITY_ADULT * WAR_CASUALTY_MULTIPLIER).abs() < 0.001);
    }

    #[test]
    fn test_mortality_elder_war_stressed() {
        let rate = mortality_rate(65, 1.5, true);
        let expected = MORTALITY_ELDER * 1.5 * WAR_CASUALTY_MULTIPLIER;
        assert!((rate - expected).abs() < 0.001);
    }

    // --- Fertility ---

    #[test]
    fn test_fertility_eligible_farmer() {
        let rate = fertility_rate(25, 0.6, 0, 0.8);
        // base=0.03, eco_mod=0.5+0.8*0.5=0.9, eligible=1.0
        let expected = 0.03 * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_eligible_soldier() {
        let rate = fertility_rate(25, 0.6, 1, 0.8);
        let expected = 0.015 * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_too_young() {
        assert!(fertility_rate(15, 0.8, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_too_old() {
        assert!(fertility_rate(46, 0.8, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_low_satisfaction() {
        // satisfaction=0.4 exactly → NOT eligible (strict >)
        assert!(fertility_rate(25, 0.4, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_bad_soil() {
        let rate = fertility_rate(25, 0.6, 0, 0.0);
        // eco_mod = 0.5 + 0.0*0.5 = 0.5
        let expected = 0.03 * 0.5;
        assert!((rate - expected).abs() < 0.001);
    }
}
```

- [ ] **Step 2: Add module to lib.rs, run tests to verify failure**

Add `pub mod demographics;` to `lib.rs`.

Run: `cd chronicler-agents && cargo test --lib demographics::tests`
Expected: FAIL — `todo!()` panics.

- [ ] **Step 3: Implement all three functions**

```rust
pub fn ecological_stress(region: &RegionState) -> f32 {
    let soil_stress = (0.5 - region.soil) * ((0.5 - region.soil) > 0.0) as i32 as f32;
    let water_stress = (0.5 - region.water) * ((0.5 - region.water) > 0.0) as i32 as f32;
    1.0 + soil_stress + water_stress
}

pub fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool) -> f32 {
    let base = match age {
        0..AGE_ADULT => MORTALITY_YOUNG,
        AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
        _ => MORTALITY_ELDER,
    };
    let war_mult = 1.0 + (WAR_CASUALTY_MULTIPLIER - 1.0) * is_soldier_at_war as i32 as f32;
    base * eco_stress * war_mult
}

pub fn fertility_rate(age: u16, satisfaction: f32, occupation: u8, soil: f32) -> f32 {
    let eligible = (age >= FERTILITY_AGE_MIN
        && age <= FERTILITY_AGE_MAX
        && satisfaction > FERTILITY_SATISFACTION_THRESHOLD) as i32 as f32;
    let base = if occupation == 0 { FERTILITY_BASE_FARMER } else { FERTILITY_BASE_OTHER };
    let ecology_mod = 0.5 + soil * 0.5;
    base * ecology_mod * eligible
}
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo test --lib demographics::tests`
Expected: all 12 demographics tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/demographics.rs chronicler-agents/src/lib.rs
git commit -m "feat(m26): add demographics module — eco stress, mortality, fertility"
```

---

### Task 7: Create behavior.rs — Decision Model

**Files:**
- Create: `chronicler-agents/src/behavior.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `pub mod behavior;`)

- [ ] **Step 1: Write RegionStats struct and compute function tests**

Create `chronicler-agents/src/behavior.rs` with the `RegionStats` struct that pre-computes per-region aggregates needed by decisions:

```rust
//! Agent decision model: rebel → migrate → switch occupation → loyalty drift.
//! Decisions evaluated in priority order; first triggered decision executes.

use crate::agent::*;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::satisfaction::target_occupation_ratio;

/// Pre-computed per-region stats for decision evaluation.
pub struct RegionStats {
    /// Count of agents per region with loyalty < REBEL_LOYALTY_THRESHOLD
    /// AND satisfaction < REBEL_SATISFACTION_THRESHOLD.
    pub rebel_eligible: Vec<usize>,
    /// Mean satisfaction per region (for migration target evaluation).
    pub mean_satisfaction: Vec<f32>,
    /// Per-region, per-occupation supply count.
    pub occupation_supply: Vec<[usize; OCCUPATION_COUNT]>,
    /// Per-region, per-occupation demand (target count based on terrain/ecology).
    pub occupation_demand: Vec<[f32; OCCUPATION_COUNT]>,
    /// Per-region, per-civ agent count (for loyalty drift — dominant civ).
    pub civ_counts: Vec<Vec<(u8, usize)>>,
    /// Per-region, per-civ mean satisfaction (for loyalty drift).
    pub civ_mean_satisfaction: Vec<Vec<(u8, f32)>>,
}

pub fn compute_region_stats(
    pool: &AgentPool,
    regions: &[RegionState],
) -> RegionStats {
    todo!()
}

/// Pending decisions collected during parallel evaluation, applied sequentially.
pub struct PendingDecisions {
    pub rebellions: Vec<(usize, u16)>,          // (slot, region)
    pub migrations: Vec<(usize, u16, u16)>,     // (slot, from, to)
    pub occupation_switches: Vec<(usize, u8)>,  // (slot, new_occ)
    pub loyalty_flips: Vec<(usize, u8)>,        // (slot, new_civ) — apply_decisions resets loyalty to 0.5
    pub loyalty_drifts: Vec<(usize, f32)>,      // (slot, delta) — positive = recovery, negative = drift
}

impl PendingDecisions {
    pub fn new() -> Self {
        Self {
            rebellions: Vec::new(),
            migrations: Vec::new(),
            occupation_switches: Vec::new(),
            loyalty_flips: Vec::new(),
            loyalty_drifts: Vec::new(),
        }
    }

    pub fn merge(&mut self, other: PendingDecisions) {
        self.rebellions.extend(other.rebellions);
        self.migrations.extend(other.migrations);
        self.occupation_switches.extend(other.occupation_switches);
        self.loyalty_flips.extend(other.loyalty_flips);
        self.loyalty_drifts.extend(other.loyalty_drifts);
    }
}

/// Evaluate decisions for all agents in a single region.
/// Returns pending decisions (not yet applied to pool).
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
) -> PendingDecisions {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_region(id: u16, adj: u32, civ: u8) -> RegionState {
        RegionState {
            region_id: id, terrain: 0, carrying_capacity: 60, population: 40,
            soil: 0.8, water: 0.6, forest_cover: 0.3,
            adjacency_mask: adj, controller_civ: civ, trade_route_count: 0,
        }
    }

    #[test]
    fn test_rebel_fires_with_cohort() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0, 0, 0)];
        // 6 agents with low loyalty AND low satisfaction (above REBEL_MIN_COHORT=5)
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.1);
            pool.set_satisfaction(slot, 0.1);
        }
        // 2 agents with normal stats (shouldn't rebel)
        for _ in 0..2 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.8);
            pool.set_satisfaction(slot, 0.7);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots: Vec<usize> = (0..8).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);
        // 6 agents should rebel
        assert_eq!(pending.rebellions.len(), 6);
        // Rebels should NOT also appear in migrations (short-circuit)
        assert_eq!(pending.migrations.len(), 0);
    }

    #[test]
    fn test_rebel_needs_cohort() {
        let mut pool = AgentPool::new(8);
        let regions = vec![make_region(0, 0, 0)];
        // Only 3 agents with low stats (below REBEL_MIN_COHORT=5)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.1);
            pool.set_satisfaction(slot, 0.1);
        }
        for _ in 0..5 {
            pool.spawn(0, 0, Occupation::Farmer, 25);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots: Vec<usize> = (0..8).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);
        // Not enough for rebellion — falls through to migrate check
        assert_eq!(pending.rebellions.len(), 0);
    }

    #[test]
    fn test_migrate_to_better_region() {
        let mut pool = AgentPool::new(16);
        let regions = vec![
            make_region(0, 0b10, 0),  // region 0 adjacent to region 1
            make_region(1, 0b01, 0),  // region 1 adjacent to region 0
        ];
        // Region 0: 4 dissatisfied agents
        for _ in 0..4 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_satisfaction(slot, 0.2); // below MIGRATE threshold
        }
        // Region 1: 4 happy agents (makes region 1 attractive)
        for _ in 0..4 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25);
            pool.set_satisfaction(slot, 0.8);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots_r0: Vec<usize> = (0..4).collect();
        let pending = evaluate_region_decisions(&pool, &slots_r0, &regions[0], &stats, 0);
        // Dissatisfied agents should want to migrate to region 1
        assert!(pending.migrations.len() > 0);
        for &(_, from, to) in &pending.migrations {
            assert_eq!(from, 0);
            assert_eq!(to, 1);
        }
    }

    #[test]
    fn test_occupation_switch_oversupplied_to_undersupplied() {
        let mut pool = AgentPool::new(32);
        let regions = vec![make_region(0, 0, 0)];
        // 20 farmers (oversupplied) in a region where demand targets ~60% of 25 = 15
        for _ in 0..20 {
            pool.spawn(0, 0, Occupation::Farmer, 25);
        }
        // 0 soldiers (undersupplied) — demand targets ~15% of 25 = 3.75
        // 5 merchants to round out the region
        for _ in 0..5 {
            pool.spawn(0, 0, Occupation::Merchant, 25);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots: Vec<usize> = (0..25).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);
        // Some farmers should switch to soldier (oversupply farmer, undersupply soldier)
        assert!(pending.occupation_switches.len() > 0);
        // Switched agents should target soldier (occ=1)
        assert!(pending.occupation_switches.iter().any(|(_, occ)| *occ == 1));
    }

    #[test]
    fn test_loyalty_drift_without_flip() {
        let mut pool = AgentPool::new(16);
        let regions = vec![
            make_region(0, 0b10, 0),
            make_region(1, 0b01, 1),
        ];
        // Civ 0 agents with moderate loyalty (above flip threshold)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6); // well above LOYALTY_FLIP_THRESHOLD=0.3
            pool.set_satisfaction(slot, 0.4);
        }
        // Civ 1 agents with higher satisfaction (drives drift)
        for _ in 0..5 {
            let slot = pool.spawn(0, 1, Occupation::Merchant, 30);
            pool.set_satisfaction(slot, 0.9);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots: Vec<usize> = (0..8).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);
        // Should have loyalty drift (negative delta) but NO flip (loyalty 0.6 - 0.02 = 0.58 > 0.3)
        assert!(pending.loyalty_drifts.iter().any(|(_, delta)| *delta < 0.0));
        assert_eq!(pending.loyalty_flips.len(), 0);
    }

    #[test]
    fn test_loyalty_drift_flips_civ() {
        let mut pool = AgentPool::new(16);
        // Region 0 controlled by civ 0, adjacent to region 1 (civ 1)
        let regions = vec![
            make_region(0, 0b10, 0),
            make_region(1, 0b01, 1),
        ];
        // Civ 0 agents in region 0 with low loyalty (near flip threshold)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.25); // just above LOYALTY_FLIP_THRESHOLD=0.3... wait, needs to drift below
            pool.set_satisfaction(slot, 0.4); // low satisfaction
        }
        // Civ 1 agents in region 0 with high satisfaction (drives loyalty drift)
        for _ in 0..5 {
            let slot = pool.spawn(0, 1, Occupation::Merchant, 30);
            pool.set_satisfaction(slot, 0.9);
        }

        let stats = compute_region_stats(&pool, &regions);
        let slots: Vec<usize> = (0..8).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);
        // Civ 0 agents should have loyalty drift (not necessarily flip in one tick)
        // The loyalty_flips list captures agents whose loyalty dropped below threshold
        // In this test, agents start at 0.25, drift -0.02 → 0.23, still above 0.3? No wait...
        // LOYALTY_FLIP_THRESHOLD is 0.3, agents at 0.25 are already below → should flip!
        assert!(pending.loyalty_flips.len() > 0);
    }
}
```

- [ ] **Step 2: Add module to lib.rs, run tests to verify failure**

Add `pub mod behavior;` to `lib.rs`.

Run: `cd chronicler-agents && cargo test --lib behavior::tests`
Expected: FAIL — `todo!()` panics.

- [ ] **Step 3: Implement compute_region_stats**

```rust
pub fn compute_region_stats(
    pool: &AgentPool,
    regions: &[RegionState],
) -> RegionStats {
    let n = regions.len();
    let mut rebel_eligible = vec![0usize; n];
    let mut sat_sum = vec![0.0f32; n];
    let mut sat_count = vec![0usize; n];
    let mut occ_supply = vec![[0usize; OCCUPATION_COUNT]; n];
    let mut occ_demand = vec![[0.0f32; OCCUPATION_COUNT]; n];
    // civ_id → (count, sat_sum) per region
    let mut civ_data: Vec<std::collections::HashMap<u8, (usize, f32)>> =
        (0..n).map(|_| std::collections::HashMap::new()).collect();

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        let r = pool.region(slot) as usize;
        if r >= n { continue; }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let occ = pool.occupation(slot) as usize;
        let civ = pool.civ_affinity(slot);

        if loy < REBEL_LOYALTY_THRESHOLD && sat < REBEL_SATISFACTION_THRESHOLD {
            rebel_eligible[r] += 1;
        }

        sat_sum[r] += sat;
        sat_count[r] += 1;

        if occ < OCCUPATION_COUNT {
            occ_supply[r][occ] += 1;
        }

        let entry = civ_data[r].entry(civ).or_insert((0, 0.0));
        entry.0 += 1;
        entry.1 += sat;
    }

    let mean_satisfaction: Vec<f32> = (0..n)
        .map(|r| if sat_count[r] > 0 { sat_sum[r] / sat_count[r] as f32 } else { 0.5 })
        .collect();

    for r in 0..n {
        let ratios = target_occupation_ratio(regions[r].terrain, regions[r].soil, regions[r].water);
        let pop = sat_count[r] as f32;
        for occ in 0..OCCUPATION_COUNT {
            occ_demand[r][occ] = ratios[occ] * pop;
        }
    }

    let civ_counts: Vec<Vec<(u8, usize)>> = civ_data.iter()
        .map(|m| m.iter().map(|(&civ, &(count, _))| (civ, count)).collect())
        .collect();

    let civ_mean_satisfaction: Vec<Vec<(u8, f32)>> = civ_data.iter()
        .map(|m| m.iter().map(|(&civ, &(count, sum))| {
            (civ, if count > 0 { sum / count as f32 } else { 0.5 })
        }).collect())
        .collect();

    RegionStats {
        rebel_eligible,
        mean_satisfaction,
        occupation_supply: occ_supply,
        occupation_demand: occ_demand,
        civ_counts,
        civ_mean_satisfaction,
    }
}
```

- [ ] **Step 4: Implement evaluate_region_decisions**

```rust
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
) -> PendingDecisions {
    let mut pending = PendingDecisions::new();
    let rebel_count = stats.rebel_eligible[region_id];

    for &slot in slots {
        if !pool.is_alive(slot) { continue; }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let occ = pool.occupation(slot) as usize;
        let civ = pool.civ_affinity(slot);

        // 1. Rebel?
        if loy < REBEL_LOYALTY_THRESHOLD
            && sat < REBEL_SATISFACTION_THRESHOLD
            && rebel_count >= REBEL_MIN_COHORT
        {
            pending.rebellions.push((slot, region.region_id));
            continue; // short-circuit
        }

        // 2. Migrate?
        if sat < MIGRATE_SATISFACTION_THRESHOLD && region.adjacency_mask != 0 {
            // Find best adjacent region
            let mut best_target: Option<u16> = None;
            let mut best_sat = sat + 0.05; // must exceed current by 0.05
            for adj_r in 0..32u16 {
                if region.adjacency_mask & (1 << adj_r) == 0 { continue; }
                let adj_idx = adj_r as usize;
                if adj_idx >= stats.mean_satisfaction.len() { continue; }
                if stats.mean_satisfaction[adj_idx] > best_sat {
                    best_sat = stats.mean_satisfaction[adj_idx];
                    best_target = Some(adj_r);
                }
            }
            if let Some(target) = best_target {
                pending.migrations.push((slot, region.region_id, target));
                continue; // short-circuit
            }
        }

        // 3. Switch occupation?
        if occ < OCCUPATION_COUNT {
            let supply = stats.occupation_supply[region_id][occ] as f32;
            let demand = stats.occupation_demand[region_id][occ];
            if supply > demand * (1.0 / OCCUPATION_SWITCH_OVERSUPPLY) {
                // Oversupplied — look for undersupplied alternative
                for alt_occ in 0..OCCUPATION_COUNT {
                    if alt_occ == occ { continue; }
                    let alt_supply = stats.occupation_supply[region_id][alt_occ] as f32;
                    let alt_demand = stats.occupation_demand[region_id][alt_occ];
                    if alt_demand > alt_supply * OCCUPATION_SWITCH_UNDERSUPPLY {
                        pending.occupation_switches.push((slot, alt_occ as u8));
                        break; // switch to first undersupplied
                    }
                }
                // Note: no continue here — if no switch found, fall through to loyalty drift
            }
        }

        // 4. Loyalty drift (only for agents in border regions)
        if region.adjacency_mask != 0 {
            // Check if any adjacent region has a different controller civ
            let mut borders_other_civ = false;
            for adj_r in 0..32u16 {
                if region.adjacency_mask & (1 << adj_r) == 0 { continue; }
                // We'd need the adjacent region's controller_civ. For now, check if
                // any other civ has agents in THIS region (simpler, same effect).
                break;
            }
            // Use civ_mean_satisfaction to determine drift direction
            let own_mean = stats.civ_mean_satisfaction[region_id].iter()
                .find(|(c, _)| *c == civ)
                .map(|(_, s)| *s)
                .unwrap_or(0.5);
            let other_mean = stats.civ_mean_satisfaction[region_id].iter()
                .filter(|(c, _)| *c != civ)
                .map(|(_, s)| *s)
                .max_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
                .unwrap_or(0.0);

            if stats.civ_counts[region_id].len() > 1 {
                if other_mean > own_mean {
                    // Drift toward other civ — loyalty erodes
                    let new_loyalty = loy - LOYALTY_DRIFT_RATE;
                    if new_loyalty < LOYALTY_FLIP_THRESHOLD {
                        // Flip to dominant civ in this region
                        let dominant = stats.civ_counts[region_id].iter()
                            .filter(|(c, _)| *c != civ)
                            .max_by_key(|(_, count)| *count)
                            .map(|(c, _)| *c)
                            .unwrap_or(civ);
                        if dominant != civ {
                            // loyalty_flips: apply_decisions sets loyalty=0.5 (reset after flip)
                            pending.loyalty_flips.push((slot, dominant));
                        }
                    }
                    pending.loyalty_drifts.push((slot, -LOYALTY_DRIFT_RATE));
                } else {
                    // Recovery — own civ doing better, loyalty recovers (slower than drift)
                    pending.loyalty_drifts.push((slot, LOYALTY_RECOVERY_RATE));
                }
            }
        }
    }

    pending
}
```

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo test --lib behavior::tests`
Expected: all 4 behavior tests PASS.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/behavior.rs chronicler-agents/src/lib.rs
git commit -m "feat(m26): add decision model — rebel, migrate, switch, loyalty drift"
```

---

### Task 8: Create signals.rs — Parse Arrow Signal Batches

**Files:**
- Create: `chronicler-agents/src/signals.rs`
- Modify: `chronicler-agents/src/lib.rs` (add `pub mod signals;`)

- [ ] **Step 1: Write struct definitions and parsing function signature**

Create `chronicler-agents/src/signals.rs`:

```rust
//! Parse per-tick signals from Python Arrow RecordBatches into typed Rust structs.

use arrow::array::{BooleanArray, Float32Array, UInt8Array};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

/// Per-civ signals from Python aggregate model.
#[derive(Clone, Debug)]
pub struct CivSignals {
    pub civ_id: u8,
    pub stability: u8,
    pub is_at_war: bool,
    pub dominant_faction: u8,   // 0=military, 1=merchant, 2=cultural
    pub faction_military: f32,
    pub faction_merchant: f32,
    pub faction_cultural: f32,
}

/// Parsed signals for one tick.
#[derive(Clone, Debug)]
pub struct TickSignals {
    pub civs: Vec<CivSignals>,
    pub contested_regions: Vec<bool>,
}

/// Parse a civ-signals Arrow RecordBatch into Vec<CivSignals>.
pub fn parse_civ_signals(batch: &RecordBatch) -> Result<Vec<CivSignals>, ArrowError> {
    todo!()
}

/// Build contested_regions from the extended region state batch.
/// Reads the `is_contested` Boolean column.
pub fn parse_contested_regions(batch: &RecordBatch, num_regions: usize) -> Vec<bool> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use arrow::array::{BooleanBuilder, Float32Builder, UInt8Builder};
    use arrow::datatypes::{DataType, Field, Schema};

    fn make_civ_batch() -> RecordBatch {
        let schema = Arc::new(Schema::new(vec![
            Field::new("civ_id", DataType::UInt8, false),
            Field::new("stability", DataType::UInt8, false),
            Field::new("is_at_war", DataType::Boolean, false),
            Field::new("dominant_faction", DataType::UInt8, false),
            Field::new("faction_military", DataType::Float32, false),
            Field::new("faction_merchant", DataType::Float32, false),
            Field::new("faction_cultural", DataType::Float32, false),
        ]));
        let mut civ_ids = UInt8Builder::new();
        let mut stabilities = UInt8Builder::new();
        let mut at_wars = BooleanBuilder::new();
        let mut dom_factions = UInt8Builder::new();
        let mut fac_mil = Float32Builder::new();
        let mut fac_mer = Float32Builder::new();
        let mut fac_cul = Float32Builder::new();

        // Civ 0: stable, at war, military dominant
        civ_ids.append_value(0); stabilities.append_value(70);
        at_wars.append_value(true); dom_factions.append_value(0);
        fac_mil.append_value(0.5); fac_mer.append_value(0.3); fac_cul.append_value(0.2);

        // Civ 1: unstable, at peace, merchant dominant
        civ_ids.append_value(1); stabilities.append_value(30);
        at_wars.append_value(false); dom_factions.append_value(1);
        fac_mil.append_value(0.2); fac_mer.append_value(0.5); fac_cul.append_value(0.3);

        RecordBatch::try_new(schema, vec![
            Arc::new(civ_ids.finish()), Arc::new(stabilities.finish()),
            Arc::new(at_wars.finish()), Arc::new(dom_factions.finish()),
            Arc::new(fac_mil.finish()), Arc::new(fac_mer.finish()),
            Arc::new(fac_cul.finish()),
        ]).unwrap()
    }

    #[test]
    fn test_parse_civ_signals() {
        let batch = make_civ_batch();
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs.len(), 2);
        assert_eq!(civs[0].civ_id, 0);
        assert_eq!(civs[0].stability, 70);
        assert!(civs[0].is_at_war);
        assert_eq!(civs[0].dominant_faction, 0);
        assert!((civs[0].faction_military - 0.5).abs() < 0.01);

        assert_eq!(civs[1].civ_id, 1);
        assert!(!civs[1].is_at_war);
        assert_eq!(civs[1].dominant_faction, 1);
    }

    #[test]
    fn test_parse_contested_regions() {
        // Simulate a region batch with is_contested column
        let schema = Arc::new(Schema::new(vec![
            Field::new("is_contested", DataType::Boolean, false),
        ]));
        let mut contested = BooleanBuilder::new();
        contested.append_value(false);
        contested.append_value(true);
        contested.append_value(false);
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(contested.finish()),
        ]).unwrap();

        let result = parse_contested_regions(&batch, 3);
        assert_eq!(result, vec![false, true, false]);
    }
}
```

- [ ] **Step 2: Add module to lib.rs, run tests to verify failure**

Run: `cd chronicler-agents && cargo test --lib signals::tests`
Expected: FAIL — `todo!()`.

- [ ] **Step 3: Implement parse functions**

```rust
pub fn parse_civ_signals(batch: &RecordBatch) -> Result<Vec<CivSignals>, ArrowError> {
    let civ_ids = batch.column_by_name("civ_id")
        .ok_or_else(|| ArrowError::SchemaError("missing civ_id".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("civ_id not UInt8".into()))?;
    let stabilities = batch.column_by_name("stability")
        .ok_or_else(|| ArrowError::SchemaError("missing stability".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("stability not UInt8".into()))?;
    let at_wars = batch.column_by_name("is_at_war")
        .ok_or_else(|| ArrowError::SchemaError("missing is_at_war".into()))?
        .as_any().downcast_ref::<BooleanArray>()
        .ok_or_else(|| ArrowError::CastError("is_at_war not Boolean".into()))?;
    let dom_factions = batch.column_by_name("dominant_faction")
        .ok_or_else(|| ArrowError::SchemaError("missing dominant_faction".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("dominant_faction not UInt8".into()))?;
    let fac_mil = batch.column_by_name("faction_military")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_military".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_military not Float32".into()))?;
    let fac_mer = batch.column_by_name("faction_merchant")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_merchant".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_merchant not Float32".into()))?;
    let fac_cul = batch.column_by_name("faction_cultural")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_cultural".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_cultural not Float32".into()))?;

    let mut result = Vec::with_capacity(batch.num_rows());
    for i in 0..batch.num_rows() {
        result.push(CivSignals {
            civ_id: civ_ids.value(i),
            stability: stabilities.value(i),
            is_at_war: at_wars.value(i),
            dominant_faction: dom_factions.value(i),
            faction_military: fac_mil.value(i),
            faction_merchant: fac_mer.value(i),
            faction_cultural: fac_cul.value(i),
        });
    }
    Ok(result)
}

pub fn parse_contested_regions(batch: &RecordBatch, num_regions: usize) -> Vec<bool> {
    let mut result = vec![false; num_regions];
    if let Some(col) = batch.column_by_name("is_contested") {
        if let Some(arr) = col.as_any().downcast_ref::<BooleanArray>() {
            for i in 0..arr.len().min(num_regions) {
                result[i] = arr.value(i);
            }
        }
    }
    result
}
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo test --lib signals::tests`
Expected: all 2 signal tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/signals.rs chronicler-agents/src/lib.rs
git commit -m "feat(m26): add signals module — parse civ and region Arrow batches"
```

---

## Chunk 3: Tick Orchestration + FFI + Aggregates + Python Shadow Mode

### Task 9: Update tick.rs — Full Orchestration

**Files:**
- Modify: `chronicler-agents/src/tick.rs`

- [ ] **Step 1: Write integration test for full tick with signals**

Add to `tick.rs` tests:

```rust
#[test]
fn test_full_tick_with_signals_deterministic() {
    use crate::signals::{CivSignals, TickSignals};

    let regions = vec![
        RegionState {
            region_id: 0, terrain: 0, carrying_capacity: 60, population: 40,
            soil: 0.8, water: 0.6, forest_cover: 0.3,
            adjacency_mask: 0b10, controller_civ: 0, trade_route_count: 0,
        },
        RegionState {
            region_id: 1, terrain: 0, carrying_capacity: 60, population: 40,
            soil: 0.7, water: 0.5, forest_cover: 0.4,
            adjacency_mask: 0b01, controller_civ: 0, trade_route_count: 1,
        },
    ];
    let signals = TickSignals {
        civs: vec![CivSignals {
            civ_id: 0, stability: 60, is_at_war: false,
            dominant_faction: 0, faction_military: 0.4,
            faction_merchant: 0.3, faction_cultural: 0.3,
        }],
        contested_regions: vec![false, false],
    };
    let mut seed = [0u8; 32];
    seed[0] = 42;

    let mut pool_a = AgentPool::new(128);
    let mut pool_b = AgentPool::new(128);
    for _ in 0..30 { pool_a.spawn(0, 0, Occupation::Farmer, 25); pool_b.spawn(0, 0, Occupation::Farmer, 25); }
    for _ in 0..20 { pool_a.spawn(1, 0, Occupation::Soldier, 30); pool_b.spawn(1, 0, Occupation::Soldier, 30); }

    let events_a = tick_agents(&mut pool_a, &regions, &signals, seed, 0);
    let events_b = tick_agents(&mut pool_b, &regions, &signals, seed, 0);

    assert_eq!(pool_a.alive_count(), pool_b.alive_count());
    assert_eq!(events_a.len(), events_b.len());
}

#[test]
fn test_full_tick_produces_events() {
    use crate::signals::{CivSignals, TickSignals};

    let regions = vec![RegionState {
        region_id: 0, terrain: 0, carrying_capacity: 60, population: 40,
        soil: 0.8, water: 0.6, forest_cover: 0.3,
        adjacency_mask: 0, controller_civ: 0, trade_route_count: 0,
    }];
    let signals = TickSignals {
        civs: vec![CivSignals {
            civ_id: 0, stability: 60, is_at_war: false,
            dominant_faction: 0, faction_military: 0.33,
            faction_merchant: 0.33, faction_cultural: 0.34,
        }],
        contested_regions: vec![false],
    };
    let mut seed = [0u8; 32];
    seed[0] = 99;

    let mut pool = AgentPool::new(600);
    // 500 elder agents — high mortality guarantees death events
    for _ in 0..500 {
        pool.spawn(0, 0, Occupation::Farmer, 65);
    }

    let events = tick_agents(&mut pool, &regions, &signals, seed, 0);
    // Should have death events (event_type=0)
    let deaths: Vec<_> = events.iter().filter(|e| e.event_type == 0).collect();
    assert!(!deaths.is_empty());
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test --lib tick::tests::test_full_tick`
Expected: FAIL — `tick_agents` doesn't accept signals.

- [ ] **Step 3: Rewrite tick_agents with full orchestration**

Replace the existing `tick_agents` function and supporting code in `tick.rs`:

```rust
//! Agent tick orchestration: skill growth → satisfaction → decisions → demographics.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;

use crate::agent::*;
use crate::behavior::{compute_region_stats, evaluate_region_decisions, PendingDecisions};
use crate::demographics;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::satisfaction;
use crate::signals::TickSignals;

/// An event emitted by the agent tick.
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,     // 0=death, 1=rebellion, 2=migration, 3=occ_switch, 4=loyalty_flip, 5=birth
    pub region: u16,
    pub target_region: u16,
    pub civ_affinity: u8,
    pub turn: u32,
}

pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
) -> Vec<AgentEvent> {
    // 0. Skill growth
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            pool.grow_skill(slot);
        }
    }

    // 1. Update satisfaction
    update_satisfaction(pool, regions, signals);

    // 2. Pre-compute region stats
    let region_stats = compute_region_stats(pool, regions);

    // 3. Decisions (per-region parallel)
    let region_groups = pool.partition_by_region(regions.len() as u16);
    let pending_decisions: Vec<PendingDecisions> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                evaluate_region_decisions(pool_ref, slots, &regions[region_id], &region_stats, region_id)
            })
            .collect()
    };

    // 4. Apply decisions sequentially
    let mut events = Vec::new();
    for pending in pending_decisions {
        for (slot, region) in &pending.rebellions {
            events.push(AgentEvent {
                agent_id: pool.id(*slot), event_type: 1, region: *region,
                target_region: 0, civ_affinity: pool.civ_affinity(*slot), turn,
            });
        }
        for &(slot, from, to) in &pending.migrations {
            let old_civ = pool.civ_affinity(slot);
            pool.set_region(slot, to);
            let new_controller = regions.get(to as usize).map(|r| r.controller_civ).unwrap_or(255);
            if new_controller != old_civ && new_controller != 255 {
                pool.set_displacement_turns(slot, 1);
            }
            events.push(AgentEvent {
                agent_id: pool.id(slot), event_type: 2, region: from,
                target_region: to, civ_affinity: old_civ, turn,
            });
        }
        for &(slot, new_occ) in &pending.occupation_switches {
            pool.set_occupation(slot, new_occ);
            // Set skill floor for new occupation
            let idx = slot * 5 + new_occ as usize;
            if pool.skills[idx] < SKILL_RESET_ON_SWITCH {
                pool.skills[idx] = SKILL_RESET_ON_SWITCH;
            }
            events.push(AgentEvent {
                agent_id: pool.id(slot), event_type: 3, region: pool.region(slot),
                target_region: 0, civ_affinity: pool.civ_affinity(slot), turn,
            });
        }
        for &(slot, new_civ) in &pending.loyalty_flips {
            pool.set_civ_affinity(slot, new_civ);
            pool.set_loyalty(slot, 0.5); // reset after flip (spec line 320)
            events.push(AgentEvent {
                agent_id: pool.id(slot), event_type: 4, region: pool.region(slot),
                target_region: 0, civ_affinity: new_civ, turn,
            });
        }
        // Apply loyalty drifts (agents not flipping — gradual drift or recovery)
        for &(slot, delta) in &pending.loyalty_drifts {
            let new_loy = (pool.loyalty(slot) + delta).clamp(0.0, 1.0);
            pool.set_loyalty(slot, new_loy);
        }
    }

    // 5. Demographics: mortality + fertility (per-region parallel)
    let region_groups = pool.partition_by_region(regions.len() as u16);
    let demo_results: Vec<(Vec<usize>, Vec<usize>, Vec<(u16, u8, f32)>)> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                let mut rng = ChaCha8Rng::from_seed(master_seed);
                rng.set_stream(region_id as u64 * 1000 + turn as u64);
                let region = &regions[region_id];
                let eco_stress = demographics::ecological_stress(region);

                let mut deaths = Vec::new();
                let mut aged = Vec::new();
                let mut births = Vec::new();

                for &slot in slots {
                    let age = pool_ref.age(slot);
                    let occ = pool_ref.occupation(slot);
                    let is_soldier_at_war = occ == Occupation::Soldier as u8
                        && signals.civs.get(pool_ref.civ_affinity(slot) as usize)
                            .map(|c| c.is_at_war)
                            .unwrap_or(false);

                    let mort = demographics::mortality_rate(age, eco_stress, is_soldier_at_war);
                    if rng.gen::<f32>() < mort {
                        deaths.push(slot);
                    } else {
                        aged.push(slot);

                        // Fertility check
                        let sat = pool_ref.satisfaction(slot);
                        let fert = demographics::fertility_rate(age, sat, occ, region.soil);
                        if rng.gen::<f32>() < fert {
                            births.push((
                                region.region_id,
                                pool_ref.civ_affinity(slot),
                                pool_ref.loyalty(slot),
                            ));
                        }
                    }
                }
                (deaths, aged, births)
            })
            .collect()
    };

    // Apply demographics sequentially
    for (deaths, aged, births) in demo_results {
        for slot in &deaths {
            events.push(AgentEvent {
                agent_id: pool.id(*slot), event_type: 0, region: pool.region(*slot),
                target_region: 0, civ_affinity: pool.civ_affinity(*slot), turn,
            });
            pool.kill(*slot);
        }
        for &slot in &aged {
            pool.increment_age(slot);
        }
        for (region_id, civ, parent_loyalty) in births {
            let slot = pool.spawn(region_id, civ, Occupation::Farmer, 0);
            pool.set_loyalty(slot, parent_loyalty);
            // Set all skills to SKILL_NEWBORN
            for occ_idx in 0..OCCUPATION_COUNT {
                pool.skills[slot * 5 + occ_idx] = SKILL_NEWBORN;
            }
            events.push(AgentEvent {
                agent_id: pool.id(slot), event_type: 5, region: region_id,
                target_region: 0, civ_affinity: civ, turn,
            });
        }
    }

    events
}

/// Update satisfaction for all alive agents based on current signals and region state.
fn update_satisfaction(pool: &mut AgentPool, regions: &[RegionState], signals: &TickSignals) {
    let region_stats = compute_region_stats(pool, regions);

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        let r = pool.region(slot) as usize;
        if r >= regions.len() { continue; }

        let region = &regions[r];
        let occ = pool.occupation(slot);
        let civ = pool.civ_affinity(slot);

        let civ_sig = signals.civs.get(civ as usize);
        let civ_stability = civ_sig.map(|c| c.stability).unwrap_or(50);
        let civ_at_war = civ_sig.map(|c| c.is_at_war).unwrap_or(false);
        let dom_faction = civ_sig.map(|c| c.dominant_faction).unwrap_or(0);
        let faction_influence = civ_sig.map(|c| match occ {
            1 => c.faction_military,
            2 => c.faction_merchant,
            3 => c.faction_cultural,
            _ => 0.0,
        }).unwrap_or(0.0);

        // Occupation-faction alignment
        let occ_matches = match occ {
            1 => dom_faction == 0,
            2 => dom_faction == 1,
            3 => dom_faction == 2,
            _ => false,
        };

        let supply = region_stats.occupation_supply[r][occ as usize] as f32;
        let demand = region_stats.occupation_demand[r][occ as usize];
        let ds_ratio = if supply > 0.0 { (demand - supply) / supply } else { 0.0 };

        let pop_over_cap = if region.carrying_capacity > 0 {
            region.population as f32 / region.carrying_capacity as f32
        } else { 1.0 };

        let contested = signals.contested_regions.get(r).copied().unwrap_or(false);
        let is_displaced = pool.displacement_turns(slot) > 0
            && pool.region(slot) != pool.origin_region(slot);

        let sat = satisfaction::compute_satisfaction(
            occ, region.soil, region.water, civ_stability, ds_ratio,
            pop_over_cap, civ_at_war, contested, occ_matches, is_displaced,
            region.trade_route_count, faction_influence,
        );
        pool.set_satisfaction(slot, sat);
    }
}
```

- [ ] **Step 4: Run all tests**

Run: `cd chronicler-agents && cargo test`
Expected: all tests PASS (including old M25 tests with updated signatures).

Note: The old M25 `tick_agents` tests need updating to pass signals. Update `test_tick_agents_reduces_population` and `test_tick_deterministic` to create dummy `TickSignals` with empty civs/contested_regions.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m26): full tick orchestration — satisfaction, decisions, demographics"
```

---

### Task 10: Populate compute_aggregates in pool.rs

**Files:**
- Modify: `chronicler-agents/src/pool.rs`

- [ ] **Step 1: Write test for populated aggregates**

Add to `pool.rs` tests:

```rust
#[test]
fn test_compute_aggregates_populated() {
    use arrow::array::{UInt16Array, UInt32Array};

    use crate::region::RegionState;

    // Region 0: capacity 60, controlled by civ 0
    let regions = vec![RegionState {
        region_id: 0, terrain: 0, carrying_capacity: 60, population: 40,
        soil: 0.8, water: 0.6, forest_cover: 0.3,
        adjacency_mask: 0, controller_civ: 0, trade_route_count: 0,
    }];

    let mut pool = AgentPool::new(16);
    // Civ 0: 2 soldiers (skill 0.8, 0.4), 1 merchant (skill 0.6)
    let s0 = pool.spawn(0, 0, Occupation::Soldier, 25);
    pool.skills[s0 * 5 + 1] = 0.8;
    let s1 = pool.spawn(0, 0, Occupation::Soldier, 30);
    pool.skills[s1 * 5 + 1] = 0.4;
    let s2 = pool.spawn(0, 0, Occupation::Merchant, 28);
    pool.skills[s2 * 5 + 2] = 0.6;
    // Set satisfaction and loyalty for stability calc
    pool.set_satisfaction(s0, 0.6);
    pool.set_satisfaction(s1, 0.4);
    pool.set_satisfaction(s2, 0.8);
    pool.set_loyalty(s0, 0.7);
    pool.set_loyalty(s1, 0.5);
    pool.set_loyalty(s2, 0.9);

    let batch = pool.compute_aggregates(&regions).unwrap();
    assert_eq!(batch.num_rows(), 1); // one civ

    let pop = batch.column(1).as_any().downcast_ref::<UInt32Array>().unwrap();
    assert_eq!(pop.value(0), 3);

    let mil = batch.column(2).as_any().downcast_ref::<UInt32Array>().unwrap();
    assert!(mil.value(0) > 0); // soldiers contribute to military

    let econ = batch.column(3).as_any().downcast_ref::<UInt32Array>().unwrap();
    assert!(econ.value(0) > 0); // merchant contributes to economy

    let stab = batch.column(5).as_any().downcast_ref::<UInt32Array>().unwrap();
    // stability = mean(sat) * mean(loy) * 100 = 0.6 * 0.7 * 100 = 42-ish
    assert!(stab.value(0) > 0 && stab.value(0) <= 100);
}
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd chronicler-agents && cargo test --lib pool::tests::test_compute_aggregates_populated`
Expected: FAIL — military/economy/stability still zeroed.

- [ ] **Step 3: Update compute_aggregates to populate all columns**

Replace the `compute_aggregates` method:

```rust
/// Compute per-civ aggregates. `regions` needed for carrying capacity normalization.
pub fn compute_aggregates(&self, regions: &[RegionState]) -> Result<RecordBatch, ArrowError> {
    use std::collections::HashMap;
    use std::collections::HashSet;

    struct CivAgg {
        population: u32,
        soldier_skill_sum: f32,
        merchant_skill_sum: f32,
        scholar_skill_sum: f32,
        priest_skill_sum: f32,
        satisfaction_sum: f32,
        loyalty_sum: f32,
        controlled_regions: HashSet<u16>,  // region_ids controlled by this civ
    }

    let mut aggs: HashMap<u8, CivAgg> = HashMap::new();

    // First pass: build civ → controlled regions from region state
    for r in regions {
        if r.controller_civ != 255 {
            aggs.entry(r.controller_civ).or_insert(CivAgg {
                population: 0, soldier_skill_sum: 0.0, merchant_skill_sum: 0.0,
                scholar_skill_sum: 0.0, priest_skill_sum: 0.0,
                satisfaction_sum: 0.0, loyalty_sum: 0.0,
                controlled_regions: HashSet::new(),
            }).controlled_regions.insert(r.region_id);
        }
    }

    // Second pass: aggregate agent stats per civ
    for slot in 0..self.capacity() {
        if !self.is_alive(slot) { continue; }
        let civ = self.civ_affinities[slot];
        let occ = self.occupations[slot] as usize;
        let occ_skill = self.skills[slot * 5 + occ];

        let entry = aggs.entry(civ).or_insert(CivAgg {
            population: 0, soldier_skill_sum: 0.0, merchant_skill_sum: 0.0,
            scholar_skill_sum: 0.0, priest_skill_sum: 0.0,
            satisfaction_sum: 0.0, loyalty_sum: 0.0,
            controlled_regions: HashSet::new(),
        });
        entry.population += 1;
        match occ {
            1 => entry.soldier_skill_sum += occ_skill,
            2 => entry.merchant_skill_sum += occ_skill,
            3 => entry.scholar_skill_sum += occ_skill,
            4 => entry.priest_skill_sum += occ_skill,
            _ => {}
        }
        entry.satisfaction_sum += self.satisfactions[slot];
        entry.loyalty_sum += self.loyalties[slot];
    }

    let mut sorted: Vec<(u8, CivAgg)> = aggs.into_iter().collect();
    sorted.sort_by_key(|(civ, _)| *civ);

    let n = sorted.len();
    let mut civ_ids = UInt16Builder::with_capacity(n);
    let mut populations = UInt32Builder::with_capacity(n);
    let mut military = UInt32Builder::with_capacity(n);
    let mut economy = UInt32Builder::with_capacity(n);
    let mut culture = UInt32Builder::with_capacity(n);
    let mut stability = UInt32Builder::with_capacity(n);

    for (civ, agg) in &sorted {
        civ_ids.append_value(*civ as u16);
        populations.append_value(agg.population);

        // Normalization denominator: civ carrying capacity (sum of controlled regions)
        let civ_capacity: f32 = agg.controlled_regions.iter()
            .filter_map(|&rid| regions.get(rid as usize))
            .map(|r| r.carrying_capacity as f32)
            .sum();
        let cap = if civ_capacity > 0.0 { civ_capacity } else { agg.population as f32 };
        let pop_f = agg.population as f32;

        // Normalization: raw / (civ_capacity * max_skill * occ_fraction) * 100
        // Spec worked example: 3.1 / (60 * 1.0 * 0.15) * 100 = 34
        let mil_norm = if cap > 0.0 { (agg.soldier_skill_sum / (cap * 0.15)).min(1.0) * 100.0 } else { 0.0 };
        let econ_norm = if cap > 0.0 { (agg.merchant_skill_sum / (cap * 0.10)).min(1.0) * 100.0 } else { 0.0 };
        let cult_raw = agg.scholar_skill_sum + agg.priest_skill_sum * 0.3;
        let cult_norm = if cap > 0.0 { (cult_raw / (cap * 0.13)).min(1.0) * 100.0 } else { 0.0 };
        let stab_val = if pop_f > 0.0 {
            let mean_sat = agg.satisfaction_sum / pop_f;
            let mean_loy = agg.loyalty_sum / pop_f;
            (mean_sat * mean_loy * 100.0).min(100.0)
        } else { 0.0 };

        military.append_value(mil_norm as u32);
        economy.append_value(econ_norm as u32);
        culture.append_value(cult_norm as u32);
        stability.append_value(stab_val as u32);
    }

    let schema = Arc::new(ffi::aggregates_schema());
    RecordBatch::try_new(
        schema,
        vec![
            Arc::new(civ_ids.finish()) as _,
            Arc::new(populations.finish()) as _,
            Arc::new(military.finish()) as _,
            Arc::new(economy.finish()) as _,
            Arc::new(culture.finish()) as _,
            Arc::new(stability.finish()) as _,
        ],
    )
}
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo test --lib pool::tests`
Expected: all pool tests PASS including the new populated aggregates test.

Note: the old `test_compute_aggregates_zeroes_non_population` test will now FAIL because military/economy/culture/stability are no longer zeroed. Update it to assert populated values or remove it in favor of the new test.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "feat(m26): populate compute_aggregates — military, economy, culture, stability"
```

---

### Task 11: Update FFI — Accept Signals, Return Populated Events

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Update tick() signature to accept signals**

Update the `tick` method in `AgentSimulator`:

Add `contested_regions: Vec<bool>` field to `AgentSimulator`:

```rust
#[pyclass]
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    contested_regions: Vec<bool>,  // M26: parsed from is_contested column in set_region_state
    master_seed: [u8; 32],
    num_regions: usize,
    turn: u32,
    initialized: bool,
}
```

In `set_region_state`, after parsing existing columns, parse `is_contested` (default `false` if absent):

```rust
// At end of set_region_state, both init and update paths:
self.contested_regions = crate::signals::parse_contested_regions(&rb, n);
```

Update `tick()`:

```rust
pub fn tick(&mut self, turn: u32, civ_signals: PyRecordBatch) -> PyResult<PyRecordBatch> {
    if !self.initialized {
        return Err(PyValueError::new_err("tick() called before set_region_state()"));
    }
    self.turn = turn;

    let sig_batch: RecordBatch = civ_signals.into_inner();
    let civs = crate::signals::parse_civ_signals(&sig_batch).map_err(arrow_err)?;
    let tick_signals = crate::signals::TickSignals {
        civs,
        contested_regions: self.contested_regions.clone(),
    };

    let events = crate::tick::tick_agents(
        &mut self.pool, &self.regions, &tick_signals, self.master_seed, turn,
    );

    Ok(PyRecordBatch::new(events_to_batch(&events, turn)?))
}
```

Update `get_aggregates()` to pass regions:

```rust
pub fn get_aggregates(&self) -> PyResult<PyRecordBatch> {
    let batch = self.pool.compute_aggregates(&self.regions).map_err(arrow_err)?;
    Ok(PyRecordBatch::new(batch))
}
```

- [ ] **Step 2: Add events_to_batch helper**

```rust
fn events_to_batch(events: &[crate::tick::AgentEvent], _turn: u32) -> Result<RecordBatch, ArrowError> {
    use arrow::array::{UInt8Builder, UInt16Builder, UInt32Builder};

    let n = events.len();
    let mut agent_ids = UInt32Builder::with_capacity(n);
    let mut event_types = UInt8Builder::with_capacity(n);
    let mut regions = UInt16Builder::with_capacity(n);
    let mut target_regions = UInt16Builder::with_capacity(n);
    let mut civ_affinities = UInt16Builder::with_capacity(n);
    let mut turns = UInt32Builder::with_capacity(n);

    for e in events {
        agent_ids.append_value(e.agent_id);
        event_types.append_value(e.event_type);
        regions.append_value(e.region);
        target_regions.append_value(e.target_region);
        civ_affinities.append_value(e.civ_affinity as u16);
        turns.append_value(e.turn);
    }

    let schema = Arc::new(events_schema());
    RecordBatch::try_new(schema, vec![
        Arc::new(agent_ids.finish()) as _,
        Arc::new(event_types.finish()) as _,
        Arc::new(regions.finish()) as _,
        Arc::new(target_regions.finish()) as _,
        Arc::new(civ_affinities.finish()) as _,
        Arc::new(turns.finish()) as _,
    ])
}
```

- [ ] **Step 3: Update set_region_state to parse extended columns**

Add parsing for `controller_civ`, `adjacency_mask`, `trade_route_count`, `is_contested` with backward-compatible defaults.

- [ ] **Step 4: Run all Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m26): update FFI — accept civ signals, return populated events, extended region state"
```

---

### Task 12: Python Shadow Mode — shadow.py + shadow_oracle.py

**Files:**
- Create: `src/chronicler/shadow.py`
- Create: `src/chronicler/shadow_oracle.py`

- [ ] **Step 1: Create shadow.py with ShadowLogger**

```python
"""Shadow mode: Arrow IPC logger for agent-vs-aggregate comparison."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import pyarrow as pa
import pyarrow.ipc as ipc

if TYPE_CHECKING:
    from chronicler.models import WorldState

SHADOW_SCHEMA = pa.schema([
    ("turn", pa.uint32()),
    ("civ_id", pa.uint16()),
    ("agent_population", pa.uint32()),
    ("agent_military", pa.uint32()),
    ("agent_economy", pa.uint32()),
    ("agent_culture", pa.uint32()),
    ("agent_stability", pa.uint32()),
    ("agg_population", pa.uint32()),
    ("agg_military", pa.uint32()),
    ("agg_economy", pa.uint32()),
    ("agg_culture", pa.uint32()),
    ("agg_stability", pa.uint32()),
])


class ShadowLogger:
    """Writes per-turn agent-vs-aggregate comparison data as Arrow IPC."""

    def __init__(self, output_path: Path):
        self._path = output_path
        self._writer: ipc.RecordBatchFileWriter | None = None

    def log_turn(self, turn: int, agent_aggs: pa.RecordBatch, world: WorldState) -> None:
        if self._writer is None:
            sink = pa.OSFile(str(self._path), "wb")
            self._writer = ipc.new_file(sink, SHADOW_SCHEMA)

        # Build civ_id → aggregate stats lookup from Python model
        civ_map = {i: c for i, c in enumerate(world.civilizations)}

        agent_civ_ids = agent_aggs.column("civ_id").to_pylist()
        agent_pops = agent_aggs.column("population").to_pylist()
        agent_mils = agent_aggs.column("military").to_pylist()
        agent_econs = agent_aggs.column("economy").to_pylist()
        agent_cults = agent_aggs.column("culture").to_pylist()
        agent_stabs = agent_aggs.column("stability").to_pylist()

        turns, civ_ids = [], []
        a_pop, a_mil, a_econ, a_cult, a_stab = [], [], [], [], []
        g_pop, g_mil, g_econ, g_cult, g_stab = [], [], [], [], []

        for idx in range(len(agent_civ_ids)):
            civ_id = agent_civ_ids[idx]
            civ = civ_map.get(civ_id)
            if civ is None:
                continue
            turns.append(turn)
            civ_ids.append(civ_id)
            a_pop.append(agent_pops[idx])
            a_mil.append(agent_mils[idx])
            a_econ.append(agent_econs[idx])
            a_cult.append(agent_cults[idx])
            a_stab.append(agent_stabs[idx])
            g_pop.append(civ.population)
            g_mil.append(civ.military)
            g_econ.append(civ.economy)
            g_cult.append(civ.culture)
            g_stab.append(civ.stability)

        batch = pa.record_batch({
            "turn": pa.array(turns, type=pa.uint32()),
            "civ_id": pa.array(civ_ids, type=pa.uint16()),
            "agent_population": pa.array(a_pop, type=pa.uint32()),
            "agent_military": pa.array(a_mil, type=pa.uint32()),
            "agent_economy": pa.array(a_econ, type=pa.uint32()),
            "agent_culture": pa.array(a_cult, type=pa.uint32()),
            "agent_stability": pa.array(a_stab, type=pa.uint32()),
            "agg_population": pa.array(g_pop, type=pa.uint32()),
            "agg_military": pa.array(g_mil, type=pa.uint32()),
            "agg_economy": pa.array(g_econ, type=pa.uint32()),
            "agg_culture": pa.array(g_cult, type=pa.uint32()),
            "agg_stability": pa.array(g_stab, type=pa.uint32()),
        }, schema=SHADOW_SCHEMA)
        self._writer.write_batch(batch)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
```

- [ ] **Step 2: Create shadow_oracle.py**

```python
"""Shadow oracle: KS + Anderson-Darling comparison of agent vs aggregate distributions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pyarrow.ipc as ipc
from scipy.stats import ks_2samp, anderson_ksamp


@dataclass
class OracleResult:
    metric: str
    turn: int
    ks_stat: float
    ks_p: float
    ad_p: float
    alpha: float

    @property
    def passed(self) -> bool:
        return self.ks_p > self.alpha and self.ad_p > self.alpha


@dataclass
class CorrelationResult:
    metric1: str
    metric2: str
    turn: int
    delta: float

    @property
    def passed(self) -> bool:
        return self.delta < 0.15


@dataclass
class OracleReport:
    results: list[OracleResult | CorrelationResult]

    @property
    def ks_pass_count(self) -> int:
        return sum(1 for r in self.results if isinstance(r, OracleResult) and r.passed)

    @property
    def ks_total(self) -> int:
        return sum(1 for r in self.results if isinstance(r, OracleResult))

    @property
    def correlation_passed(self) -> bool:
        return all(r.passed for r in self.results if isinstance(r, CorrelationResult))

    @property
    def passed(self) -> bool:
        return self.ks_pass_count >= 12 and self.correlation_passed


def load_shadow_data(paths: list[Path]) -> dict:
    """Load shadow IPC files into column-oriented dict."""
    columns: dict[str, list] = {}
    for path in paths:
        reader = ipc.open_file(str(path))
        for i in range(reader.num_record_batches):
            batch = reader.get_batch(i)
            for col_name in batch.schema.names:
                columns.setdefault(col_name, []).extend(batch.column(col_name).to_pylist())
    return columns


def extract_at_turn(data: dict, column: str, turn: int) -> np.ndarray:
    """Extract values for a specific column at a specific turn."""
    turns = np.array(data["turn"])
    values = np.array(data[column])
    mask = turns == turn
    return values[mask]


def shadow_oracle_report(shadow_ipc_paths: list[Path]) -> OracleReport:
    """Compare agent-derived and aggregate stat distributions at checkpoints."""
    checkpoints = [100, 250, 500]
    metrics = ["population", "military", "economy", "culture", "stability"]
    bonferroni_alpha = 0.05 / (len(metrics) * len(checkpoints))

    all_data = load_shadow_data(shadow_ipc_paths)
    results: list[OracleResult | CorrelationResult] = []

    for metric in metrics:
        for turn in checkpoints:
            agent_vals = extract_at_turn(all_data, f"agent_{metric}", turn)
            agg_vals = extract_at_turn(all_data, f"agg_{metric}", turn)
            if len(agent_vals) < 2 or len(agg_vals) < 2:
                continue
            ks_stat, ks_p = ks_2samp(agent_vals, agg_vals)
            ad_stat, _, ad_p = anderson_ksamp([agent_vals, agg_vals])
            results.append(OracleResult(metric, turn, ks_stat, ks_p, ad_p, bonferroni_alpha))

    correlation_checks = [("military", "economy"), ("culture", "stability")]
    for m1, m2 in correlation_checks:
        for turn in checkpoints:
            agent_m1 = extract_at_turn(all_data, f"agent_{m1}", turn)
            agent_m2 = extract_at_turn(all_data, f"agent_{m2}", turn)
            agg_m1 = extract_at_turn(all_data, f"agg_{m1}", turn)
            agg_m2 = extract_at_turn(all_data, f"agg_{m2}", turn)
            if len(agent_m1) < 3 or len(agg_m1) < 3:
                continue
            corr_delta = abs(
                np.corrcoef(agent_m1, agent_m2)[0, 1]
                - np.corrcoef(agg_m1, agg_m2)[0, 1]
            )
            results.append(CorrelationResult(m1, m2, turn, corr_delta))

    return OracleReport(results)
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/shadow.py src/chronicler/shadow_oracle.py
git commit -m "feat(m26): add shadow logger (Arrow IPC) and oracle comparison framework"
```

---

### Task 13: Update agent_bridge.py — Shadow Mode + build_signals

**Files:**
- Modify: `src/chronicler/agent_bridge.py`

- [ ] **Step 1: Add build_signals and update AgentBridge**

```python
"""Bridge between Python WorldState and Rust AgentSimulator."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import pyarrow as pa
from chronicler_agents import AgentSimulator
from chronicler.shadow import ShadowLogger

if TYPE_CHECKING:
    from chronicler.models import Event, WorldState

TERRAIN_MAP = {
    "plains": 0, "mountains": 1, "coast": 2,
    "forest": 3, "desert": 4, "tundra": 5,
}
FACTION_MAP = {"military": 0, "merchant": 1, "cultural": 2}


def build_region_batch(world: WorldState) -> pa.RecordBatch:
    """Build extended region state Arrow batch (M26: adds controller, adjacency, etc.)."""
    # Build civ name → id map
    civ_name_to_id = {c.name: i for i, c in enumerate(world.civilizations)}

    # Build adjacency masks
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}
    adj_masks = []
    for r in world.regions:
        mask = 0
        for adj_name in r.adjacencies:
            if adj_name in region_name_to_idx:
                mask |= 1 << region_name_to_idx[adj_name]
        adj_masks.append(mask)

    # Contested regions
    contested_regions_set = set()
    for attacker, defender in world.active_wars:
        # Simplified: regions of defender are contested
        for r in world.regions:
            if r.controller == defender:
                contested_regions_set.add(r.name)

    return pa.record_batch({
        "region_id": pa.array(range(len(world.regions)), type=pa.uint16()),
        "terrain": pa.array([TERRAIN_MAP[r.terrain] for r in world.regions], type=pa.uint8()),
        "carrying_capacity": pa.array([r.carrying_capacity for r in world.regions], type=pa.uint16()),
        "population": pa.array([r.population for r in world.regions], type=pa.uint16()),
        "soil": pa.array([r.ecology.soil for r in world.regions], type=pa.float32()),
        "water": pa.array([r.ecology.water for r in world.regions], type=pa.float32()),
        "forest_cover": pa.array([r.ecology.forest_cover for r in world.regions], type=pa.float32()),
        "controller_civ": pa.array(
            [civ_name_to_id.get(r.controller, 255) if r.controller else 255 for r in world.regions],
            type=pa.uint8(),
        ),
        "adjacency_mask": pa.array(adj_masks, type=pa.uint32()),
        "trade_route_count": pa.array([0 for _ in world.regions], type=pa.uint8()),  # TODO: derive from trade system
        "is_contested": pa.array([r.name in contested_regions_set for r in world.regions], type=pa.bool_()),
    })


def build_signals(world: WorldState) -> pa.RecordBatch:
    """Build civ-signals Arrow RecordBatch from current WorldState."""
    from chronicler.factions import get_dominant_faction
    from chronicler.models import FactionType

    war_civs = set()
    for attacker, defender in world.active_wars:
        war_civs.add(attacker)
        war_civs.add(defender)

    civ_ids, stabilities, at_wars = [], [], []
    dom_factions, fac_mil, fac_mer, fac_cul = [], [], [], []

    for i, civ in enumerate(world.civilizations):
        civ_ids.append(i)
        stabilities.append(min(civ.stability, 100))
        at_wars.append(civ.name in war_civs)
        dominant = get_dominant_faction(civ.factions)
        dom_factions.append(FACTION_MAP.get(dominant.value, 0))
        fac_mil.append(civ.factions.influence.get(FactionType.MILITARY, 0.33))
        fac_mer.append(civ.factions.influence.get(FactionType.MERCHANT, 0.33))
        fac_cul.append(civ.factions.influence.get(FactionType.CULTURAL, 0.34))

    return pa.record_batch({
        "civ_id": pa.array(civ_ids, type=pa.uint8()),
        "stability": pa.array(stabilities, type=pa.uint8()),
        "is_at_war": pa.array(at_wars, type=pa.bool_()),
        "dominant_faction": pa.array(dom_factions, type=pa.uint8()),
        "faction_military": pa.array(fac_mil, type=pa.float32()),
        "faction_merchant": pa.array(fac_mer, type=pa.float32()),
        "faction_cultural": pa.array(fac_cul, type=pa.float32()),
    })


class AgentBridge:
    def __init__(self, world: WorldState, mode: str = "demographics-only",
                 shadow_output: Path | None = None):
        self._sim = AgentSimulator(num_regions=len(world.regions), seed=world.seed)
        self._mode = mode
        self._shadow_logger: ShadowLogger | None = None
        if mode == "shadow" and shadow_output is not None:
            self._shadow_logger = ShadowLogger(shadow_output)

    def tick(self, world: WorldState) -> list[Event]:
        self._sim.set_region_state(build_region_batch(world))
        signals = build_signals(world)
        _agent_events = self._sim.tick(world.turn, signals)

        if self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            return []  # discard — aggregate model drives
        elif self._mode == "demographics-only":
            self._apply_demographics_clamp(world)
            return []
        return []

    def _apply_demographics_clamp(self, world: WorldState) -> None:
        region_pops = self._sim.get_region_populations()
        pop_map = dict(zip(
            region_pops.column("region_id").to_pylist(),
            region_pops.column("alive_count").to_pylist(),
        ))
        for i, region in enumerate(world.regions):
            if region.controller is not None:
                agent_pop = pop_map.get(i, 0)
                region.population = min(agent_pop, int(region.carrying_capacity * 1.2))

    def close(self) -> None:
        if self._shadow_logger:
            self._shadow_logger.close()

    def get_snapshot(self): return self._sim.get_snapshot()
    def get_aggregates(self): return self._sim.get_aggregates()
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m26): update agent_bridge — shadow mode, build_signals, extended region batch"
```

---

### Task 14: Python Tests — Shadow Mode + Signals

**Files:**
- Modify: `tests/test_agent_bridge.py`
- Create: `tests/test_shadow_oracle.py`

- [ ] **Step 0: Update existing M25 Python tests for new tick() signature**

The FFI `tick()` now requires a `civ_signals` RecordBatch. All existing `sim.tick(turn)` calls in `tests/test_agent_bridge.py` must be updated to `sim.tick(turn, _make_dummy_signals(...))`.

Add this helper to `tests/test_agent_bridge.py`:

```python
def _make_dummy_signals(num_civs=3):
    """Minimal civ-signals batch for tests that don't exercise signal logic."""
    return pa.record_batch({
        "civ_id": pa.array(range(num_civs), type=pa.uint8()),
        "stability": pa.array([50] * num_civs, type=pa.uint8()),
        "is_at_war": pa.array([False] * num_civs, type=pa.bool_()),
        "dominant_faction": pa.array([0] * num_civs, type=pa.uint8()),
        "faction_military": pa.array([0.33] * num_civs, type=pa.float32()),
        "faction_merchant": pa.array([0.33] * num_civs, type=pa.float32()),
        "faction_cultural": pa.array([0.34] * num_civs, type=pa.float32()),
    })
```

Update all `sim.tick(turn)` → `sim.tick(turn, _make_dummy_signals())` in:
- `TestPythonRoundTrip.test_set_region_state_initializes_agents`
- `TestTickBehavior.test_tick_reduces_population`
- `TestTickBehavior.test_ages_increment`
- `TestTickBehavior.test_region_populations_matches_snapshot`
- `TestPythonDeterminism.test_determinism_50_turns`
- `test_tick_before_set_region_state_errors` (pass dummy signals to verify error is about `set_region_state`, not arg count)

Also update `test_aggregates_population_matches_and_others_zeroed`: M26 populates military/economy/culture/stability, so remove the "others zeroed" assertion. Replace with a check that values are in range [0, 100].

Run: `python -m pytest tests/test_agent_bridge.py -v`
Expected: all existing M25 tests PASS with updated calls.

- [ ] **Step 1: Add signal building test to test_agent_bridge.py**

```python
class TestBuildSignals:
    def test_build_signals_schema(self, world_fixture):
        from chronicler.agent_bridge import build_signals
        batch = build_signals(world_fixture)
        assert batch.num_rows == len(world_fixture.civilizations)
        assert "civ_id" in batch.schema.names
        assert "stability" in batch.schema.names
        assert "is_at_war" in batch.schema.names
        assert "dominant_faction" in batch.schema.names

    def test_build_signals_war_state(self, world_fixture):
        from chronicler.agent_bridge import build_signals
        world_fixture.active_wars = [(world_fixture.civilizations[0].name,
                                      world_fixture.civilizations[1].name)]
        batch = build_signals(world_fixture)
        at_war = batch.column("is_at_war").to_pylist()
        assert at_war[0] is True
        assert at_war[1] is True
```

- [ ] **Step 2: Create test_shadow_oracle.py with synthetic data tests**

```python
"""Tests for shadow oracle comparison framework."""
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.ipc as ipc
import numpy as np
import pytest
from chronicler.shadow import SHADOW_SCHEMA
from chronicler.shadow_oracle import (
    shadow_oracle_report, load_shadow_data, extract_at_turn, OracleReport,
)


def write_synthetic_shadow(path: Path, turns: list[int], n_civs: int = 3,
                           diverge: bool = False) -> None:
    """Write synthetic shadow data for testing."""
    rng = np.random.default_rng(42)
    sink = pa.OSFile(str(path), "wb")
    writer = ipc.new_file(sink, SHADOW_SCHEMA)

    for turn in turns:
        for civ in range(n_civs):
            agent_pop = int(rng.normal(50, 5))
            agg_pop = int(rng.normal(50, 5)) if not diverge else int(rng.normal(80, 5))
            batch = pa.record_batch({
                "turn": pa.array([turn], type=pa.uint32()),
                "civ_id": pa.array([civ], type=pa.uint16()),
                "agent_population": pa.array([max(0, agent_pop)], type=pa.uint32()),
                "agent_military": pa.array([30], type=pa.uint32()),
                "agent_economy": pa.array([25], type=pa.uint32()),
                "agent_culture": pa.array([20], type=pa.uint32()),
                "agent_stability": pa.array([40], type=pa.uint32()),
                "agg_population": pa.array([max(0, agg_pop)], type=pa.uint32()),
                "agg_military": pa.array([30], type=pa.uint32()),
                "agg_economy": pa.array([25], type=pa.uint32()),
                "agg_culture": pa.array([20], type=pa.uint32()),
                "agg_stability": pa.array([40], type=pa.uint32()),
            }, schema=SHADOW_SCHEMA)
            writer.write_batch(batch)
    writer.close()


class TestShadowDataIO:
    def test_write_and_read(self):
        with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
            path = Path(f.name)
        write_synthetic_shadow(path, [100, 250, 500])
        data = load_shadow_data([path])
        assert "turn" in data
        assert len(data["turn"]) == 3 * 3 * 3  # 3 turns × 3 civs

    def test_extract_at_turn(self):
        with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
            path = Path(f.name)
        write_synthetic_shadow(path, [100, 250])
        data = load_shadow_data([path])
        vals = extract_at_turn(data, "agent_population", 100)
        assert len(vals) == 3  # 3 civs at turn 100


class TestOracleReport:
    def test_matching_distributions_pass(self):
        """When agent and aggregate use same distribution, oracle should pass."""
        paths = []
        for seed in range(50):
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
                path = Path(f.name)
            write_synthetic_shadow(path, [100, 250, 500], diverge=False)
            paths.append(path)
        report = shadow_oracle_report(paths)
        # With matching distributions, most tests should pass
        assert report.ks_pass_count >= 10  # relaxed for synthetic data

    def test_divergent_distributions_fail(self):
        """When distributions diverge, oracle should detect it."""
        paths = []
        for seed in range(50):
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as f:
                path = Path(f.name)
            write_synthetic_shadow(path, [100, 250, 500], diverge=True)
            paths.append(path)
        report = shadow_oracle_report(paths)
        # Population should fail (agent ~50, agg ~80)
        pop_results = [r for r in report.results
                       if hasattr(r, "metric") and r.metric == "population"]
        assert any(not r.passed for r in pop_results)
```

- [ ] **Step 3: Run Python tests**

Run: `cd /c/Users/tateb/Documents/opusprogram && python -m pytest tests/test_shadow_oracle.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_bridge.py tests/test_shadow_oracle.py
git commit -m "test(m26): add shadow oracle tests and signal building tests"
```

---

### Task 15: Determinism Test + Benchmark

**Files:**
- Modify: `chronicler-agents/tests/determinism.rs`
- Modify: `chronicler-agents/benches/tick_bench.rs`

- [ ] **Step 1: Update determinism test for M26 tick signature**

Update `determinism.rs` to pass `TickSignals` to `tick_agents` and verify determinism with full behavior model across 1, 4, 16 thread counts.

- [ ] **Step 2: Update benchmark for M26 tick**

Update `tick_bench.rs` to benchmark 6,000 agents with full decision model + demographics. Add signals with realistic values (2 civs, 24 regions).

Document in benchmark output: thread count, CPU load, jemalloc status.

- [ ] **Step 3: Run benchmark**

Run: `cd chronicler-agents && cargo bench`
Expected: < 3ms/tick for 6,000 agents.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/determinism.rs chronicler-agents/benches/tick_bench.rs
git commit -m "test(m26): update determinism test and benchmark for full behavior model"
```
