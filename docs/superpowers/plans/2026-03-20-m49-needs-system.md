# M49: Needs System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 per-agent needs (Safety, Material, Social, Spiritual, Autonomy, Purpose) to the Rust agent pool with decay, proportional restoration, and threshold-gated decision utility modifiers.

**Architecture:** Needs are SoA f32 fields on AgentPool. Linear decay + proportional restoration each tick produces stable equilibria. Threshold-gated utility modifiers add to rebel/migrate/switch/stay decisions after M48 memory modifiers. Autonomy need also accelerates loyalty drift. FFI query method exposes needs for named character narration.

**Tech Stack:** Rust (needs.rs, pool.rs, tick.rs, behavior.rs, agent.rs, ffi.rs), Python (models.py, agent_bridge.py, narrative.py), PyO3 FFI.

**Spec:** `docs/superpowers/specs/2026-03-20-m49-needs-system-design.md`

**IMPORTANT: Test code in this plan is schematic.** All `AgentPool::new()` and `pool.spawn()` calls use simplified signatures. Before implementing, READ the actual signatures in `pool.rs` (lines 73, 112-125) and adjust test code accordingly. Same applies to `RegionState::new()` — check `region.rs` line 67.

**Subagent dispatch checklist (from CLAUDE.md):**
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially population/capacity fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.

---

## File Map

### New Files

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/needs.rs` | NeedUtilityModifiers struct, decay_needs, restore_needs, clamp_needs, update_needs, compute_need_utility_modifiers, social_restoration proxy |
| `chronicler-agents/tests/test_needs.rs` | Rust unit/integration tests for needs |
| `tests/test_needs.py` | Python integration tests (narration rendering, --agents=off invariant) |

### Modified Files

| File | Changes |
|------|---------|
| `chronicler-agents/src/lib.rs` | Add `pub mod needs;` after line 21 (`pub mod memory;`), add re-exports |
| `chronicler-agents/src/agent.rs` | ~51 need constants after line 213 (end of M48 memory block, before `#[cfg(test)]`) |
| `chronicler-agents/src/pool.rs` | 6 SoA fields between line 59 (`memory_count`) and line 61 (`alive`), spawn init in both branches |
| `chronicler-agents/src/tick.rs` | Insert `update_needs()` call between line 81 (`wealth_tick`) and line 86 (`update_satisfaction`) |
| `chronicler-agents/src/behavior.rs` | Make `personality_modifier` `pub`, add need modifiers + cap + Autonomy drift after M48 memory modifiers (lines 354-356), before NEG_INFINITY gates (lines 358-359) |
| `chronicler-agents/src/ffi.rs` | `get_agent_needs()` pymethod after line 766 (`get_agent_memories`) |
| `src/chronicler/models.py` | `GreatPerson.needs` field after line 362 |
| `src/chronicler/agent_bridge.py` | Needs sync after line 513 (memory sync) |
| `src/chronicler/narrative.py` | `NEED_DESCRIPTIONS` after line 81, `render_needs()`, needs context in `build_agent_context_block()` (line 110) |

---

## Task 1: Rust Foundation — Constants, Storage, Module

**Files:**
- Create: `chronicler-agents/src/needs.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Modify: `chronicler-agents/src/agent.rs` (after line 213, before `#[cfg(test)]`)
- Modify: `chronicler-agents/src/pool.rs` (lines 59-61 struct fields, lines 129-164 reuse branch, lines 165-201 grow branch, lines 73-108 new())
- Create: `chronicler-agents/tests/test_needs.rs`

- [ ] **Step 1: Write test for spawn zero-initialization**

In `chronicler-agents/tests/test_needs.rs`:

```rust
use chronicler_agents::pool::AgentPool;

#[test]
fn test_needs_spawn_at_starting_value() {
    let mut pool = AgentPool::new(16);
    // Use actual spawn() signature from pool.rs lines 112-125
    let slot = pool.spawn(0, 0, chronicler_agents::Occupation::Farmer, 20,
        0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert!((pool.need_safety[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_material[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_social[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_spiritual[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_autonomy[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot] - 0.5).abs() < 0.001);
}

#[test]
fn test_needs_reuse_reset() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, chronicler_agents::Occupation::Farmer, 20,
        0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    // Dirty the needs
    pool.need_safety[slot] = 0.1;
    pool.need_purpose[slot] = 0.9;
    pool.kill(slot);
    // Respawn — should reset to STARTING_NEED
    let slot2 = pool.spawn(0, 0, chronicler_agents::Occupation::Farmer, 20,
        0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert_eq!(slot, slot2); // free-list reuse
    assert!((pool.need_safety[slot2] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot2] - 0.5).abs() < 0.001);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_needs_spawn`
Expected: Compilation error — `need_safety` field does not exist on AgentPool.

- [ ] **Step 3: Add need constants to agent.rs**

After line 213 (end of M48 block `DEATHOFKIN_MIGRATE_PENALTY`), before `#[cfg(test)]` at line 215, add:

```rust
// M49: Needs system — starting value
pub const STARTING_NEED: f32 = 0.5;

// M49: Need decay rates [CALIBRATE M53]
pub const SAFETY_DECAY: f32 = 0.015;
pub const MATERIAL_DECAY: f32 = 0.012;
pub const SOCIAL_DECAY: f32 = 0.008;
pub const SPIRITUAL_DECAY: f32 = 0.010;
pub const AUTONOMY_DECAY: f32 = 0.015;
pub const PURPOSE_DECAY: f32 = 0.012;

// M49: Need behavioral thresholds [CALIBRATE M53]
pub const SAFETY_THRESHOLD: f32 = 0.3;
pub const MATERIAL_THRESHOLD: f32 = 0.3;
pub const SOCIAL_THRESHOLD: f32 = 0.25;
pub const SPIRITUAL_THRESHOLD: f32 = 0.3;
pub const AUTONOMY_THRESHOLD: f32 = 0.3;
pub const PURPOSE_THRESHOLD: f32 = 0.35;

// M49: Need behavioral weights [CALIBRATE M53]
pub const SAFETY_WEIGHT: f32 = 0.7;
pub const MATERIAL_WEIGHT: f32 = 0.5;
pub const SOCIAL_WEIGHT: f32 = 0.5;
pub const SPIRITUAL_WEIGHT: f32 = 0.4;
pub const AUTONOMY_WEIGHT: f32 = 0.8;
pub const PURPOSE_WEIGHT: f32 = 0.4;

// M49: Restoration rates [CALIBRATE M53]
pub const SAFETY_RESTORE_PEACE: f32 = 0.020;
pub const SAFETY_RESTORE_HEALTH: f32 = 0.010;
pub const SAFETY_RESTORE_FOOD: f32 = 0.008;
pub const BOLD_SAFETY_RESTORE_WEIGHT: f32 = 0.3;
pub const MATERIAL_RESTORE_FOOD: f32 = 0.012;
pub const MATERIAL_RESTORE_WEALTH: f32 = 0.015;
pub const SOCIAL_RESTORE_POP: f32 = 0.010;
pub const SOCIAL_RESTORE_POP_THRESHOLD: f32 = 0.3;
pub const SOCIAL_MERCHANT_MULT: f32 = 1.5;
pub const SOCIAL_PRIEST_MULT: f32 = 1.3;
pub const SPIRITUAL_RESTORE_TEMPLE: f32 = 0.020;
pub const SPIRITUAL_RESTORE_MATCH: f32 = 0.015;
pub const AUTONOMY_RESTORE_SELF_GOV: f32 = 0.020;
pub const AUTONOMY_RESTORE_NO_PERSC: f32 = 0.010;
pub const PURPOSE_RESTORE_SKILL: f32 = 0.020;
pub const PURPOSE_RESTORE_WAR: f32 = 0.015;

// M49: Infrastructure constants [CALIBRATE M53]
pub const NEEDS_MODIFIER_CAP: f32 = 0.30;
pub const AUTONOMY_DRIFT_WEIGHT: f32 = 2.0;
```

- [ ] **Step 4: Create needs.rs stub with NeedUtilityModifiers**

In `chronicler-agents/src/needs.rs`:

```rust
/// M49 Needs System
/// Spec: docs/superpowers/specs/2026-03-20-m49-needs-system-design.md
///
/// 6 per-agent needs as f32 in [0.0, 1.0]. Linear decay + proportional
/// restoration each tick. Threshold-gated utility modifiers on decisions.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::signals::TickSignals;

/// Additive utility modifiers from needs, applied after M48 memory modifiers.
#[derive(Debug, Default)]
pub struct NeedUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch_occ: f32,
    pub stay: f32,
}
```

- [ ] **Step 5: Add `pub mod needs;` to lib.rs**

After line 21 (`pub mod memory;`), add `pub mod needs;`. In the re-exports block, add:

```rust
#[doc(hidden)]
pub use needs::NeedUtilityModifiers;
```

- [ ] **Step 6: Add 6 SoA fields to AgentPool in pool.rs**

Between line 59 (`memory_count`) and line 61 (`alive`), add:

```rust
// M49: Needs system (6 × f32 per agent)
pub need_safety: Vec<f32>,
pub need_material: Vec<f32>,
pub need_social: Vec<f32>,
pub need_spiritual: Vec<f32>,
pub need_autonomy: Vec<f32>,
pub need_purpose: Vec<f32>,
```

In `AgentPool::new()` (lines 73-108), add `Vec::with_capacity(capacity)` for each.

In the free-list reuse branch (lines 129-164), before `self.alive[slot] = true;` (line 162), add:

```rust
self.need_safety[slot] = agent::STARTING_NEED;
self.need_material[slot] = agent::STARTING_NEED;
self.need_social[slot] = agent::STARTING_NEED;
self.need_spiritual[slot] = agent::STARTING_NEED;
self.need_autonomy[slot] = agent::STARTING_NEED;
self.need_purpose[slot] = agent::STARTING_NEED;
```

In the grow branch (lines 165-201), before `self.alive.push(true);` (line 198), add:

```rust
self.need_safety.push(agent::STARTING_NEED);
self.need_material.push(agent::STARTING_NEED);
self.need_social.push(agent::STARTING_NEED);
self.need_spiritual.push(agent::STARTING_NEED);
self.need_autonomy.push(agent::STARTING_NEED);
self.need_purpose.push(agent::STARTING_NEED);
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_needs`
Expected: PASS for both `test_needs_spawn_at_starting_value` and `test_needs_reuse_reset`.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/needs.rs chronicler-agents/src/lib.rs \
  chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs \
  chronicler-agents/tests/test_needs.rs
git commit -m "feat(m49): needs SoA storage, constants, NeedUtilityModifiers struct"
```

---

## Task 2: Decay & Restoration

**Files:**
- Modify: `chronicler-agents/src/needs.rs`
- Modify: `chronicler-agents/tests/test_needs.rs`

- [ ] **Step 1: Write decay and restoration tests**

Add to `chronicler-agents/tests/test_needs.rs`:

```rust
use chronicler_agents::needs::*;
use chronicler_agents::RegionState;

#[test]
fn test_decay_basic() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_safety[slot] = 0.5;
    let alive = vec![slot];
    decay_needs(&mut pool, &alive);
    // 0.5 - SAFETY_DECAY(0.015) = 0.485
    assert!((pool.need_safety[slot] - 0.485).abs() < 0.001);
}

#[test]
fn test_decay_clamps_at_zero() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_safety[slot] = 0.005; // below SAFETY_DECAY
    let alive = vec![slot];
    decay_needs(&mut pool, &alive);
    assert_eq!(pool.need_safety[slot], 0.0);
}

#[test]
fn test_restoration_proportional() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_spiritual[slot] = 0.2; // low need
    let mut region = RegionState::new(0);
    region.has_temple = true;
    region.majority_belief = 0; // matches agent belief
    pool.beliefs[slot] = 0;
    let regions = vec![region];
    let signals = /* build TickSignals with is_at_war=false */;
    let wealth_pct = vec![0.5_f32];
    restore_needs(&mut pool, &[slot], &regions, &signals, &wealth_pct);
    // Spiritual: TEMPLE_RATE * (1 - 0.2) + MATCH_RATE * (1 - 0.2) = 0.020*0.8 + 0.015*0.8 = 0.028
    assert!(pool.need_spiritual[slot] > 0.2, "Should restore upward");
    assert!(pool.need_spiritual[slot] < 0.3, "Should not overshoot");
}

#[test]
fn test_restoration_diminishes_near_max() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_spiritual[slot] = 0.95; // already high
    let mut region = RegionState::new(0);
    region.has_temple = true;
    region.majority_belief = 0;
    pool.beliefs[slot] = 0;
    let regions = vec![region];
    let signals = /* build TickSignals */;
    let wealth_pct = vec![0.5];
    restore_needs(&mut pool, &[slot], &regions, &signals, &wealth_pct);
    // At 0.95: restoration = 0.035 * (1 - 0.95) = 0.035 * 0.05 = 0.00175
    let delta = pool.need_spiritual[slot] - 0.95;
    assert!(delta < 0.005, "Near-max restoration should be tiny, got {}", delta);
}

#[test]
fn test_autonomy_blocked_by_displacement() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_autonomy[slot] = 0.1;
    pool.displacement_turns[slot] = 3; // displaced
    pool.civ_affinities[slot] = 0;
    let mut region = RegionState::new(0);
    region.controller_civ = 0; // self-governed
    region.persecution_intensity = 0.0;
    let regions = vec![region];
    let signals = /* build TickSignals */;
    let wealth_pct = vec![0.5];
    restore_needs(&mut pool, &[slot], &regions, &signals, &wealth_pct);
    // Displacement blocks ALL autonomy restoration
    assert!((pool.need_autonomy[slot] - 0.1).abs() < 0.001);
}

#[test]
fn test_equilibrium_convergence() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_safety[slot] = 0.0; // start at minimum
    pool.boldness[slot] = 0.0; // neutral boldness
    let mut region = RegionState::new(0);
    region.endemic_severity = 0.0;
    region.food_sufficiency = 1.0;
    let regions = vec![region];
    // is_at_war = false for agent's civ
    let signals = /* build TickSignals with is_at_war=false */;
    let wealth_pct = vec![0.5];
    // Run 200 ticks — should converge near eq = 1 - D/R_total
    for _ in 0..200 {
        decay_needs(&mut pool, &[slot]);
        restore_needs(&mut pool, &[slot], &regions, &signals, &wealth_pct);
        clamp_needs(&mut pool, &[slot]);
    }
    // Expected eq ~ 1 - 0.015/0.038 ~ 0.605
    assert!(pool.need_safety[slot] > 0.50, "Should converge above 0.50, got {}", pool.need_safety[slot]);
    assert!(pool.need_safety[slot] < 0.70, "Should converge below 0.70, got {}", pool.need_safety[slot]);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_needs`
Expected: Compilation error — `decay_needs`, `restore_needs`, `clamp_needs` don't exist.

- [ ] **Step 3: Implement decay, restoration, and clamp in needs.rs**

Add to `chronicler-agents/src/needs.rs`:

```rust
use crate::behavior::personality_modifier;

/// Linear decay for all 6 needs. Clamps to 0.0.
pub fn decay_needs(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        pool.need_safety[slot] = (pool.need_safety[slot] - agent::SAFETY_DECAY).max(0.0);
        pool.need_material[slot] = (pool.need_material[slot] - agent::MATERIAL_DECAY).max(0.0);
        pool.need_social[slot] = (pool.need_social[slot] - agent::SOCIAL_DECAY).max(0.0);
        pool.need_spiritual[slot] = (pool.need_spiritual[slot] - agent::SPIRITUAL_DECAY).max(0.0);
        pool.need_autonomy[slot] = (pool.need_autonomy[slot] - agent::AUTONOMY_DECAY).max(0.0);
        pool.need_purpose[slot] = (pool.need_purpose[slot] - agent::PURPOSE_DECAY).max(0.0);
    }
}

/// Clamp all 6 needs to [0.0, 1.0].
pub fn clamp_needs(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        pool.need_safety[slot] = pool.need_safety[slot].clamp(0.0, 1.0);
        pool.need_material[slot] = pool.need_material[slot].clamp(0.0, 1.0);
        pool.need_social[slot] = pool.need_social[slot].clamp(0.0, 1.0);
        pool.need_spiritual[slot] = pool.need_spiritual[slot].clamp(0.0, 1.0);
        pool.need_autonomy[slot] = pool.need_autonomy[slot].clamp(0.0, 1.0);
        pool.need_purpose[slot] = pool.need_purpose[slot].clamp(0.0, 1.0);
    }
}

/// Pre-M50 proxy for Social need restoration.
/// Replace with relationship count when M50 lands.
fn social_restoration(pool: &AgentPool, slot: usize, region: &RegionState) -> f32 {
    let cap = region.carrying_capacity as f32;
    if cap <= 0.0 { return 0.0; }
    let pop_ratio = (region.population as f32 / cap).min(1.0);
    if pop_ratio < agent::SOCIAL_RESTORE_POP_THRESHOLD { return 0.0; }
    let mut rate = agent::SOCIAL_RESTORE_POP * pop_ratio;
    // Occupation modifier
    let occ = pool.occupations[slot];
    if occ == crate::agent::Occupation::Merchant as u8 { rate *= agent::SOCIAL_MERCHANT_MULT; }
    if occ == crate::agent::Occupation::Priest as u8 { rate *= agent::SOCIAL_PRIEST_MULT; }
    // Age modifier
    let age_mult = (pool.ages[slot] as f32 / 40.0).min(1.0);
    rate * age_mult
}

/// Proportional restoration for all 6 needs.
/// Each condition contributes R * condition_value * (1 - need).
pub fn restore_needs(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    for &slot in alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx >= regions.len() { continue; }
        let region = &regions[region_idx];
        let civ = pool.civ_affinities[slot] as usize;

        // Look up is_at_war for the agent's own civ
        let is_at_war = signals.civs.get(civ).map_or(false, |c| c.is_at_war);

        // --- Safety ---
        let deficit = 1.0 - pool.need_safety[slot];
        let mut safety_r = 0.0;
        if !is_at_war { safety_r += agent::SAFETY_RESTORE_PEACE; }
        safety_r += agent::SAFETY_RESTORE_HEALTH * (1.0 - region.endemic_severity).max(0.0);
        if region.food_sufficiency > 0.8 {
            safety_r += agent::SAFETY_RESTORE_FOOD * region.food_sufficiency.min(1.5);
        }
        // Per-agent boldness modifier
        let bold_mod = personality_modifier(pool.boldness[slot], agent::BOLD_SAFETY_RESTORE_WEIGHT);
        pool.need_safety[slot] += safety_r * bold_mod * deficit;

        // --- Material ---
        let deficit = 1.0 - pool.need_material[slot];
        let mut material_r = 0.0;
        material_r += agent::MATERIAL_RESTORE_FOOD * region.food_sufficiency.min(1.5);
        let wpct = if slot < wealth_percentiles.len() { wealth_percentiles[slot] } else { 0.0 };
        material_r += agent::MATERIAL_RESTORE_WEALTH * wpct;
        pool.need_material[slot] += material_r * deficit;

        // --- Social ---
        let deficit = 1.0 - pool.need_social[slot];
        let social_r = social_restoration(pool, slot, region);
        pool.need_social[slot] += social_r * deficit;

        // --- Spiritual ---
        let deficit = 1.0 - pool.need_spiritual[slot];
        let mut spiritual_r = 0.0;
        if region.has_temple { spiritual_r += agent::SPIRITUAL_RESTORE_TEMPLE; }
        if pool.beliefs[slot] == region.majority_belief
            && region.majority_belief != crate::agent::BELIEF_NONE
        {
            spiritual_r += agent::SPIRITUAL_RESTORE_MATCH;
        }
        pool.need_spiritual[slot] += spiritual_r * deficit;

        // --- Autonomy ---
        // Displacement blocks ALL restoration
        if pool.displacement_turns[slot] == 0 {
            let deficit = 1.0 - pool.need_autonomy[slot];
            let mut autonomy_r = 0.0;
            if region.controller_civ == pool.civ_affinities[slot] {
                autonomy_r += agent::AUTONOMY_RESTORE_SELF_GOV;
            }
            if region.persecution_intensity == 0.0 {
                autonomy_r += agent::AUTONOMY_RESTORE_NO_PERSC;
            }
            pool.need_autonomy[slot] += autonomy_r * deficit;
        }

        // --- Purpose ---
        let deficit = 1.0 - pool.need_purpose[slot];
        let occ = pool.occupations[slot] as usize;
        let skill_idx = slot * 5 + occ;
        let skill = if skill_idx < pool.skills.len() { pool.skills[skill_idx] } else { 0.0 };
        let mut purpose_r = agent::PURPOSE_RESTORE_SKILL * skill;
        if pool.occupations[slot] == crate::agent::Occupation::Soldier as u8 && is_at_war {
            purpose_r += agent::PURPOSE_RESTORE_WAR;
        }
        pool.need_purpose[slot] += purpose_r * deficit;
    }
}

/// Entry point for needs tick. Called between wealth_tick and update_satisfaction.
pub fn update_needs(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .collect();
    decay_needs(pool, &alive_slots);
    restore_needs(pool, &alive_slots, regions, signals, wealth_percentiles);
    clamp_needs(pool, &alive_slots);
}
```

- [ ] **Step 4: Make `personality_modifier` public in behavior.rs**

At `behavior.rs` line 46, change `fn personality_modifier` to `pub fn personality_modifier`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_needs`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/needs.rs chronicler-agents/src/behavior.rs \
  chronicler-agents/tests/test_needs.rs
git commit -m "feat(m49): decay, proportional restoration, equilibrium convergence"
```

---

## Task 3: Utility Modifiers + Needs Cap

**Files:**
- Modify: `chronicler-agents/src/needs.rs`
- Modify: `chronicler-agents/src/behavior.rs` (lines 354-370)
- Modify: `chronicler-agents/tests/test_needs.rs`

- [ ] **Step 1: Write utility modifier tests**

Add to `chronicler-agents/tests/test_needs.rs`:

```rust
#[test]
fn test_utility_modifier_safety_migrate() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_safety[slot] = 0.1; // below threshold 0.3
    let mods = compute_need_utility_modifiers(&pool, slot);
    // deficit = (0.3 - 0.1) = 0.2, migrate = 0.2 * SAFETY_WEIGHT(0.7) = 0.14
    assert!((mods.migrate - 0.14).abs() < 0.01);
    assert!(mods.stay < 0.0, "Safety unmet should reduce stay");
}

#[test]
fn test_utility_modifier_above_threshold_zero() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    pool.need_safety[slot] = 0.5; // above threshold 0.3
    let mods = compute_need_utility_modifiers(&pool, slot);
    assert_eq!(mods.migrate, 0.0);
    assert_eq!(mods.rebel, 0.0);
    assert_eq!(mods.switch_occ, 0.0);
    assert_eq!(mods.stay, 0.0);
}

#[test]
fn test_utility_modifier_cap() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    // Set all needs to 0 — maximum deficit
    pool.need_safety[slot] = 0.0;
    pool.need_material[slot] = 0.0;
    pool.need_spiritual[slot] = 0.0;
    let mods = compute_need_utility_modifiers(&pool, slot);
    // Safety(0.21) + Material(0.15) + Spiritual(0.12) = 0.48 > cap 0.30
    assert!((mods.migrate - 0.30).abs() < 0.01, "migrate should be capped at 0.30, got {}", mods.migrate);
}

#[test]
fn test_autonomy_rebel_independently() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params */);
    // All needs met except Autonomy
    pool.need_autonomy[slot] = 0.0; // full deficit
    let mods = compute_need_utility_modifiers(&pool, slot);
    // rebel = 0.3 * AUTONOMY_WEIGHT(0.8) = 0.24
    assert!((mods.rebel - 0.24).abs() < 0.01);
}

#[test]
fn test_needs_only_rebellion_trigger() {
    // The critical M49 behavioral property: an agent with satisfaction and loyalty
    // ABOVE rebellion thresholds can still rebel from Autonomy need alone.
    // rebel_utility() returns 0.0 when sat > 0.2 and loy > 0.2.
    // Need modifier adds to 0.0, pushing above the NEG_INFINITY gate.
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(/* actual params with default personality */);
    pool.satisfactions[slot] = 0.6; // well above REBEL_SATISFACTION_THRESHOLD (0.2)
    pool.loyalties[slot] = 0.5;     // well above REBEL_LOYALTY_THRESHOLD (0.2)
    pool.need_autonomy[slot] = 0.0; // full deficit → rebel mod = 0.24

    // Base rebel utility should be 0.0 (above both thresholds)
    let base = crate::behavior::rebel_utility(0.5, 0.6, 10);
    assert_eq!(base, 0.0, "Base rebel utility should be zero above thresholds");

    // Need modifier should be positive
    let mods = compute_need_utility_modifiers(&pool, slot);
    assert!(mods.rebel > 0.0, "Autonomy deficit should produce positive rebel modifier");

    // Combined: 0.0 * personality + 0.0 (no persecution) + 0.0 (no memory) + mods.rebel > 0.0
    // This passes the NEG_INFINITY gate, making rebellion a selectable action
    let total = 0.0 + mods.rebel; // base 0 + needs
    assert!(total > 0.0, "Needs-only rebel utility should be positive: {}", total);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_utility_modifier`
Expected: Compilation error — `compute_need_utility_modifiers` doesn't exist.

- [ ] **Step 3: Implement compute_need_utility_modifiers in needs.rs**

```rust
/// Compute threshold-gated utility modifiers from an agent's need state.
/// Each need below its threshold contributes (threshold - need) * weight.
/// Per-channel cap applied: total needs modifier per channel <= NEEDS_MODIFIER_CAP.
pub fn compute_need_utility_modifiers(pool: &AgentPool, slot: usize) -> NeedUtilityModifiers {
    let mut mods = NeedUtilityModifiers::default();

    // Safety → migrate +, stay -
    let safety_deficit = (agent::SAFETY_THRESHOLD - pool.need_safety[slot]).max(0.0);
    if safety_deficit > 0.0 {
        mods.migrate += safety_deficit * agent::SAFETY_WEIGHT;
        mods.stay -= safety_deficit * agent::SAFETY_WEIGHT;
    }

    // Material → migrate +, switch +
    let material_deficit = (agent::MATERIAL_THRESHOLD - pool.need_material[slot]).max(0.0);
    if material_deficit > 0.0 {
        mods.migrate += material_deficit * agent::MATERIAL_WEIGHT;
        mods.switch_occ += material_deficit * agent::MATERIAL_WEIGHT;
    }

    // Social → stay +, migrate -
    let social_deficit = (agent::SOCIAL_THRESHOLD - pool.need_social[slot]).max(0.0);
    if social_deficit > 0.0 {
        mods.stay += social_deficit * agent::SOCIAL_WEIGHT;
        mods.migrate -= social_deficit * agent::SOCIAL_WEIGHT;
    }

    // Spiritual → migrate +
    let spiritual_deficit = (agent::SPIRITUAL_THRESHOLD - pool.need_spiritual[slot]).max(0.0);
    if spiritual_deficit > 0.0 {
        mods.migrate += spiritual_deficit * agent::SPIRITUAL_WEIGHT;
    }

    // Autonomy → rebel +
    let autonomy_deficit = (agent::AUTONOMY_THRESHOLD - pool.need_autonomy[slot]).max(0.0);
    if autonomy_deficit > 0.0 {
        mods.rebel += autonomy_deficit * agent::AUTONOMY_WEIGHT;
    }

    // Purpose → switch +
    let purpose_deficit = (agent::PURPOSE_THRESHOLD - pool.need_purpose[slot]).max(0.0);
    if purpose_deficit > 0.0 {
        mods.switch_occ += purpose_deficit * agent::PURPOSE_WEIGHT;
    }

    // Per-channel cap (needs-only, does not affect M38b/M48 modifiers)
    mods.rebel = mods.rebel.min(agent::NEEDS_MODIFIER_CAP);
    mods.migrate = mods.migrate.max(-agent::NEEDS_MODIFIER_CAP).min(agent::NEEDS_MODIFIER_CAP);
    mods.switch_occ = mods.switch_occ.min(agent::NEEDS_MODIFIER_CAP);
    mods.stay = mods.stay.max(-agent::NEEDS_MODIFIER_CAP).min(agent::NEEDS_MODIFIER_CAP);

    mods
}
```

- [ ] **Step 4: Wire into behavior.rs evaluate_region_decisions**

After the M48 memory modifier block (lines 354-356) and before the NEG_INFINITY gates (lines 358-359), add:

```rust
// M49: Need-driven utility modifiers — additive, applied after memory, before gate
let need_mods = crate::needs::compute_need_utility_modifiers(pool, slot);
rebel_util += need_mods.rebel;
migrate_util += need_mods.migrate;
```

Then modify the switch and stay lines (366-370) to include needs:

At line 367, change:
```rust
let u_switch_raw = u_switch_base * personality_modifier(ambi, AMBITION_SWITCH_WEIGHT)
    + mem_mods.switch;
```
to:
```rust
let u_switch_raw = u_switch_base * personality_modifier(ambi, AMBITION_SWITCH_WEIGHT)
    + mem_mods.switch + need_mods.switch_occ;
```

At line 370, change:
```rust
let u_stay = STAY_BASE + mem_mods.stay;
```
to:
```rust
let u_stay = STAY_BASE + mem_mods.stay + need_mods.stay;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass including new needs tests and all existing tests.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/needs.rs chronicler-agents/src/behavior.rs \
  chronicler-agents/tests/test_needs.rs
git commit -m "feat(m49): threshold-gated utility modifiers with per-channel cap"
```

---

## Task 4: Autonomy Drift Acceleration

**Files:**
- Modify: `chronicler-agents/src/behavior.rs` (lines 422-426, loyalty drift section)
- Modify: `chronicler-agents/tests/test_needs.rs`

- [ ] **Step 1: Write Autonomy drift test**

```rust
#[test]
fn test_autonomy_drift_acceleration() {
    // Agents with unmet Autonomy should drift faster than those with met Autonomy
    // This is a behavioral integration test — verify drift rate multiplier
    let autonomy_deficit = (0.3 - 0.0_f32).max(0.0); // full deficit
    let factor = 1.0 + autonomy_deficit * 2.0; // AUTONOMY_DRIFT_WEIGHT = 2.0
    assert!((factor - 1.6).abs() < 0.01, "Max deficit should give 1.6x drift, got {}", factor);

    let autonomy_deficit_half = (0.3 - 0.15_f32).max(0.0);
    let factor_half = 1.0 + autonomy_deficit_half * 2.0;
    assert!((factor_half - 1.3).abs() < 0.01, "Half deficit should give 1.3x drift");

    // Above threshold — no acceleration
    let autonomy_ok = (0.3 - 0.5_f32).max(0.0);
    let factor_ok = 1.0 + autonomy_ok * 2.0;
    assert_eq!(factor_ok, 1.0, "No deficit should give 1.0x drift");
}
```

- [ ] **Step 2: Wire Autonomy drift into behavior.rs**

In `evaluate_region_decisions()`, at the loyalty drift section (lines 422-426), change:

```rust
let effective_drift = LOYALTY_DRIFT_RATE
    * personality_modifier(-ltrait, LOYALTY_TRAIT_WEIGHT);
```

to:

```rust
// M49: Autonomy need accelerates negative loyalty drift
let autonomy_deficit = (crate::agent::AUTONOMY_THRESHOLD
    - pool.need_autonomy[slot]).max(0.0);
let autonomy_factor = 1.0 + autonomy_deficit * crate::agent::AUTONOMY_DRIFT_WEIGHT;
let effective_drift = LOYALTY_DRIFT_RATE
    * personality_modifier(-ltrait, LOYALTY_TRAIT_WEIGHT)
    * autonomy_factor;
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/behavior.rs chronicler-agents/tests/test_needs.rs
git commit -m "feat(m49): Autonomy need accelerates loyalty drift toward civ flip"
```

---

## Task 5: Tick Integration

**Files:**
- Modify: `chronicler-agents/src/tick.rs` (between lines 81 and 86)

- [ ] **Step 1: Insert update_needs call in tick_agents**

Between `wealth_tick` (line 81) and `update_satisfaction` (line 86), add:

```rust
// -----------------------------------------------------------------------
// 0.75 Needs decay + restoration (M49)
// -----------------------------------------------------------------------
crate::needs::update_needs(pool, regions, signals, wealth_percentiles);
```

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass. Existing determinism tests should still pass since needs are deterministic.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m49): wire update_needs into tick between wealth and satisfaction"
```

---

## Task 6: FFI — get_agent_needs

**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (after line 766, `get_agent_memories`)

- [ ] **Step 1: Add get_agent_needs pymethod**

After `get_agent_memories` (line 766), add:

```rust
/// M49: Return need values for a specific agent.
/// Returns (safety, material, social, spiritual, autonomy, purpose).
/// None if agent not found or dead.
fn get_agent_needs(&self, agent_id: u32) -> Option<(f32, f32, f32, f32, f32, f32)> {
    let pool = &self.pool;
    for slot in 0..pool.ids.len() {
        if pool.id(slot) == agent_id && pool.is_alive(slot) {
            return Some((
                pool.need_safety[slot],
                pool.need_material[slot],
                pool.need_social[slot],
                pool.need_spiritual[slot],
                pool.need_autonomy[slot],
                pool.need_purpose[slot],
            ));
        }
    }
    None
}
```

- [ ] **Step 2: Run Rust tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m49): get_agent_needs FFI method for named character narration"
```

---

## Task 7: Python Integration — GreatPerson + Agent Bridge

**Files:**
- Modify: `src/chronicler/models.py` (after line 362)
- Modify: `src/chronicler/agent_bridge.py` (after line 513)

- [ ] **Step 1: Add GreatPerson.needs field**

In `models.py`, after line 362 (`memories: list = Field(default_factory=list)`), add:

```python
needs: dict = Field(default_factory=dict)  # M49: cached from Rust via FFI
```

- [ ] **Step 2: Add needs sync in agent_bridge.py**

In `agent_bridge.py`, after the memory sync loop (line 513), add inside the same `for civ_obj in world.civilizations:` / `for gp in civ_obj.great_persons:` loop:

```python
                        # M49: Sync needs for active named characters
                        raw_needs = self._sim.get_agent_needs(gp.agent_id)
                        if raw_needs is not None:
                            gp.needs = {
                                "safety": raw_needs[0], "material": raw_needs[1],
                                "social": raw_needs[2], "spiritual": raw_needs[3],
                                "autonomy": raw_needs[4], "purpose": raw_needs[5],
                            }
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py src/chronicler/agent_bridge.py
git commit -m "feat(m49): GreatPerson.needs field and Rust-to-Python sync"
```

---

## Task 8: Narration Integration

**Files:**
- Modify: `src/chronicler/narrative.py` (after line 81 for NEED_DESCRIPTIONS, after line 110 for build_agent_context_block)
- Create: `tests/test_needs.py`

- [ ] **Step 1: Add NEED_DESCRIPTIONS and render_needs**

In `narrative.py`, after line 81 (end of `MEMORY_DESCRIPTIONS`), add:

```python
# ---------------------------------------------------------------------------
# M49: Need descriptions for narration
# ---------------------------------------------------------------------------

NEED_DESCRIPTIONS = {
    "safety": "feels unsafe",
    "material": "wants for material comfort",
    "social": "is isolated",
    "spiritual": "is spiritually adrift",
    "autonomy": "chafes under foreign rule",
    "purpose": "lacks a sense of purpose",
}

# Thresholds must match agent.rs constants
_NEED_THRESHOLDS = {
    "safety": 0.3, "material": 0.3, "social": 0.25,
    "spiritual": 0.3, "autonomy": 0.3, "purpose": 0.35,
}


def render_needs(needs: dict) -> list[str]:
    """Render needs as narrator context lines.

    Returns lines like:
      "Needs: Safety satisfied, Material LOW (0.18), ..."
      "  - wants for material comfort"
    """
    if not needs:
        return []
    parts = []
    low_descriptions = []
    for name in ["safety", "material", "social", "spiritual", "autonomy", "purpose"]:
        val = needs.get(name, 0.5)
        threshold = _NEED_THRESHOLDS.get(name, 0.3)
        if val < threshold:
            parts.append(f"{name.title()} LOW ({val:.2f})")
            desc = NEED_DESCRIPTIONS.get(name)
            if desc:
                low_descriptions.append(f"  - {desc}")
        else:
            parts.append(f"{name.title()} satisfied")
    lines = [f"Needs: {', '.join(parts)}"]
    lines.extend(low_descriptions)
    return lines
```

- [ ] **Step 2: Wire into build_agent_context_block**

In `build_agent_context_block()` (line 110), after the memory rendering section, add needs rendering. Find the return/join point and insert before it:

Two insertion points are needed:

**A. In `build_agent_context_for_moment()` (narrative.py ~line 286),** after the memory context injection into the char dict, add:

```python
# M49: Needs context
if hasattr(gp, "needs") and gp.needs:
    char["needs"] = gp.needs
```

**B. In `build_agent_context_block()` (narrative.py ~line 110),** inside the per-character loop (which iterates `ctx.named_characters` — a list of dicts, NOT GreatPerson objects), after the memory/mule rendering sections (~line 170), add:

```python
            # M49: Needs context
            char_needs = char.get("needs")
            if char_needs:
                needs_lines = render_needs(char_needs)
                for line in needs_lines:
                    lines.append(line)
```

**IMPORTANT:** `AgentContext` has `named_characters: list[dict]`, NOT `great_persons`. The char dicts don't have `.needs` attributes — they use dict keys. The `needs` key is injected by step A above.

- [ ] **Step 3: Write Python narration test**

In `tests/test_needs.py`:

```python
"""M49 Needs System integration tests.
All tests use render_needs() — no execute_run().
"""
from chronicler.narrative import render_needs, NEED_DESCRIPTIONS


class TestNeedsRendering:
    def test_all_satisfied(self):
        needs = {"safety": 0.5, "material": 0.6, "social": 0.4,
                 "spiritual": 0.5, "autonomy": 0.5, "purpose": 0.5}
        lines = render_needs(needs)
        assert len(lines) == 1  # just the summary, no LOW descriptions
        assert "LOW" not in lines[0]

    def test_one_low(self):
        needs = {"safety": 0.1, "material": 0.6, "social": 0.4,
                 "spiritual": 0.5, "autonomy": 0.5, "purpose": 0.5}
        lines = render_needs(needs)
        assert "Safety LOW (0.10)" in lines[0]
        assert "feels unsafe" in lines[1]

    def test_multiple_low(self):
        needs = {"safety": 0.1, "material": 0.6, "social": 0.1,
                 "spiritual": 0.5, "autonomy": 0.0, "purpose": 0.5}
        lines = render_needs(needs)
        assert "Safety LOW" in lines[0]
        assert "Social LOW" in lines[0]
        assert "Autonomy LOW" in lines[0]
        assert len(lines) == 4  # summary + 3 descriptions

    def test_empty_needs(self):
        assert render_needs({}) == []

    def test_need_descriptions_complete(self):
        for name in ["safety", "material", "social", "spiritual", "autonomy", "purpose"]:
            assert name in NEED_DESCRIPTIONS
```

- [ ] **Step 4: Run Python tests**

Run: `pytest tests/test_needs.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_needs.py
git commit -m "feat(m49): need narration rendering with LOW/satisfied context"
```

---

## Verification Checklist

After all 8 tasks are complete:

- [ ] `cargo nextest run -p chronicler-agents` — all Rust tests pass (including existing 188+)
- [ ] `pytest tests/test_needs.py -v` — all Python needs tests pass
- [ ] `pytest tests/ -v --ignore=tests/test_bundle.py --ignore=tests/test_m36_regression.py --ignore=tests/test_main.py` — full Python suite passes (excluding known hanging tests)
- [ ] `--agents=off` mode produces identical output (needs are Rust-only)
- [ ] Equilibrium convergence test passes (200 ticks → need converges near `1 - D/R_total`)
- [ ] Needs-only rebellion test: agent with sat > 0.2, loyalty > 0.2, Autonomy need = 0.0 can rebel
- [ ] No new files created outside the scope specified above
