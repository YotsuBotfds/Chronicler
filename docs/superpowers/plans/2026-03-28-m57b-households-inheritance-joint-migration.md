# M57b: Households, Inheritance & Joint Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add derived household mechanics: spouse-first inheritance on death, joint migration with catastrophe gating, and household-effective wealth for migration decisions.

**Architecture:** Inline integration into existing tick phases via a new `household.rs` helper module. No new entity types — households are derived from marriage bonds + parent links. Two `id_to_slot` maps (pre-decision and pre-death) serve different phases. Household stats flow through the existing `_process_tick_results` pipeline.

**Tech Stack:** Rust (chronicler-agents crate), Python (chronicler package), PyO3 FFI, Arrow

**Spec:** `docs/superpowers/specs/2026-03-28-m57b-households-inheritance-joint-migration-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `chronicler-agents/src/household.rs` | CREATE | Pure helpers: `household_effective_wealth`, `resolve_dependents`, `household_death_transfer`, `consolidate_household_migrations`, `HouseholdStats` struct |
| `chronicler-agents/src/agent.rs` | MODIFY | `CATASTROPHE_FOOD_THRESHOLD` constant |
| `chronicler-agents/src/lib.rs` | MODIFY | `pub mod household;` + re-exports |
| `chronicler-agents/src/tick.rs` | MODIFY | Pre-decision `id_to_slot`, `full_dead_ids` precompute, death-transfer call, migration consolidation call, birth marital counting, household stats accumulation |
| `chronicler-agents/src/behavior.rs` | MODIFY | Pass `id_to_slot` to `evaluate_region_decisions`, wire `household_effective_wealth` into `migrate_utility` |
| `chronicler-agents/src/ffi.rs` | MODIFY | `HouseholdStats` storage on `AgentSimulator`, `get_household_stats()` PyO3 method |
| `chronicler-agents/tests/test_m57b_household.rs` | CREATE | Rust integration tests |
| `src/chronicler/agent_bridge.py` | MODIFY | `_household_stats_history`, `get_household_stats()` call in `_process_tick_results`, Python parity helper |
| `src/chronicler/analytics.py` | MODIFY | `extract_household_stats()` extractor |
| `src/chronicler/main.py` | MODIFY | Wire household stats into bundle metadata |
| `tests/test_m57b_household.py` | CREATE | Python integration tests |

---

### Task 1: Household Stats Struct & Constants

**Files:**
- Modify: `chronicler-agents/src/agent.rs`
- Create: `chronicler-agents/src/household.rs`
- Modify: `chronicler-agents/src/lib.rs`

- [ ] **Step 1: Add constant to `agent.rs`**

In `chronicler-agents/src/agent.rs`, after the existing marriage constants block (around line 125), add:

```rust
// M57b: Household constants
pub const CATASTROPHE_FOOD_THRESHOLD: f32 = 0.30; // [CALIBRATE M47]
```

- [ ] **Step 2: Create `household.rs` with `HouseholdStats` and `InheritanceEvent`**

Create `chronicler-agents/src/household.rs`:

```rust
//! M57b: Household helpers — derived households, inheritance, joint migration.
//!
//! All functions are pure (no state, no RNG). Households are derived from
//! marriage bonds + parent links, not stored as entities.

use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::relationships;

/// Per-tick household counters. Reset each tick, exported via FFI.
#[derive(Debug, Default, Clone)]
pub struct HouseholdStats {
    pub inheritance_transfers_spouse: u32,
    pub inheritance_transfers_child: u32,
    pub inheritance_wealth_lost: f32,
    pub household_migrations_follow: u32,
    pub household_migrations_cancelled_rebellion: u32,
    pub household_migrations_cancelled_catastrophe: u32,
    pub household_dependent_overrides: u32,
    pub births_married_parent: u32,
    pub births_unmarried_parent: u32,
}

/// Transfer type for inheritance events.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TransferType {
    SpouseInherit,
    OrphanSplit,
    AdultChildSplit,
}

/// Record of a single inheritance transfer.
#[derive(Debug, Clone)]
pub struct InheritanceEvent {
    pub heir_slot: usize,
    pub deceased_id: u32,
    pub amount: f32,
    pub overflow: f32,
    pub transfer_type: TransferType,
}
```

- [ ] **Step 3: Register module in `lib.rs`**

In `chronicler-agents/src/lib.rs`, after `pub mod formation;` (line 24), add:

```rust
pub mod household;
```

And in the re-exports section (after the formation re-export at line 90), add:

```rust
#[doc(hidden)]
pub use household::{HouseholdStats, InheritanceEvent, TransferType};
```

- [ ] **Step 4: Verify compilation**

Run: `cargo check -p chronicler-agents`
Expected: compiles with no errors.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/household.rs chronicler-agents/src/lib.rs
git commit -m "feat(m57b): add HouseholdStats struct, InheritanceEvent, and CATASTROPHE_FOOD_THRESHOLD constant"
```

---

### Task 2: Household Helper Functions + Unit Tests

**Files:**
- Modify: `chronicler-agents/src/household.rs`
- Create: `chronicler-agents/tests/test_m57b_household.rs`

- [ ] **Step 1: Write failing tests for `household_effective_wealth`**

Create `chronicler-agents/tests/test_m57b_household.rs`:

```rust
//! M57b Household: Integration tests for helpers, inheritance, and migration.

use chronicler_agents::{
    AgentPool, Occupation, RegionState,
    CivSignals, TickSignals,
};
use chronicler_agents::relationships::{get_spouse_id, upsert_symmetric, BondType};
use chronicler_agents::household::{household_effective_wealth, resolve_dependents};
use std::collections::HashMap;

fn spawn(pool: &mut AgentPool, region: u16, civ: u8, occ: Occupation, age: u16) -> usize {
    pool.spawn(region, civ, occ, age, 0.5, 0.5, 0.5, 0, 0, 0, 0xFF)
}

fn build_id_to_slot(pool: &AgentPool) -> HashMap<u32, usize> {
    let mut map = HashMap::new();
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            map.insert(pool.ids[slot], slot);
        }
    }
    map
}

#[test]
fn test_effective_wealth_unmarried() {
    let mut pool = AgentPool::new(10);
    let slot = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    pool.wealth[slot] = 100.0;
    let id_to_slot = build_id_to_slot(&pool);
    let ew = household_effective_wealth(&pool, slot, &id_to_slot);
    assert!((ew - 100.0).abs() < 0.01, "unmarried: personal wealth only, got {}", ew);
}

#[test]
fn test_effective_wealth_married() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Merchant, 25);
    pool.wealth[a] = 80.0;
    pool.wealth[b] = 120.0;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let ew_a = household_effective_wealth(&pool, a, &id_to_slot);
    let ew_b = household_effective_wealth(&pool, b, &id_to_slot);
    assert!((ew_a - 200.0).abs() < 0.01, "married A: combined, got {}", ew_a);
    assert!((ew_b - 200.0).abs() < 0.01, "married B: combined, got {}", ew_b);
}

#[test]
fn test_effective_wealth_widowed_after_kill() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    pool.wealth[a] = 50.0;
    pool.wealth[b] = 70.0;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    // Kill b and remove bonds (simulating death_cleanup_sweep)
    pool.kill(b);
    chronicler_agents::relationships::swap_remove_rel(&mut pool, a, 0);
    let id_to_slot = build_id_to_slot(&pool);
    let ew = household_effective_wealth(&pool, a, &id_to_slot);
    assert!((ew - 50.0).abs() < 0.01, "widowed: personal only, got {}", ew);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household`
Expected: FAIL — `household_effective_wealth` not found.

- [ ] **Step 3: Implement `household_effective_wealth`**

Add to `chronicler-agents/src/household.rs`:

```rust
/// Return combined household wealth for a married agent, or personal wealth if unmarried.
/// Uses `id_to_slot` for O(1) spouse slot resolution — never falls back to linear scan.
pub fn household_effective_wealth(
    pool: &AgentPool,
    slot: usize,
    id_to_slot: &std::collections::HashMap<u32, usize>,
) -> f32 {
    let personal = pool.wealth[slot];
    if let Some(spouse_id) = relationships::get_spouse_id(pool, slot) {
        if let Some(&spouse_slot) = id_to_slot.get(&spouse_id) {
            if pool.is_alive(spouse_slot) && pool.ids[spouse_slot] == spouse_id {
                return personal + pool.wealth[spouse_slot];
            }
        }
    }
    personal
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household`
Expected: all 3 tests PASS.

- [ ] **Step 5: Write failing test for `resolve_dependents`**

Add to `chronicler-agents/tests/test_m57b_household.rs`:

```rust
use chronicler_agents::agent::AGE_ADULT;

#[test]
fn test_resolve_dependents_basic() {
    let mut pool = AgentPool::new(20);
    let parent_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30);
    let parent_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28);
    upsert_symmetric(&mut pool, parent_a, parent_b, BondType::Marriage as u8, 50, 1);
    // Child of both parents, under AGE_ADULT, same region
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 10);
    pool.parent_id_0[child] = pool.ids[parent_a];
    pool.parent_id_1[child] = pool.ids[parent_b];
    // Adult child — should NOT be included
    let adult_child = spawn(&mut pool, 0, 0, Occupation::Soldier, AGE_ADULT);
    pool.parent_id_0[adult_child] = pool.ids[parent_a];
    pool.parent_id_1[adult_child] = pool.ids[parent_b];

    let dep_index = build_dependent_index(&pool);
    let deps = resolve_dependents(&pool, parent_a, parent_b, &dep_index);
    assert_eq!(deps.len(), 1, "only under-AGE_ADULT child");
    assert_eq!(deps[0], child);
}

#[test]
fn test_resolve_dependents_excludes_married_minor() {
    let mut pool = AgentPool::new(20);
    let parent_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 35);
    let parent_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 33);
    upsert_symmetric(&mut pool, parent_a, parent_b, BondType::Marriage as u8, 50, 1);
    // Minor child who is married (age 17, MARRIAGE_MIN_AGE=16)
    let married_minor = spawn(&mut pool, 0, 0, Occupation::Farmer, 17);
    pool.parent_id_0[married_minor] = pool.ids[parent_a];
    pool.parent_id_1[married_minor] = pool.ids[parent_b];
    let spouse_of_minor = spawn(&mut pool, 0, 0, Occupation::Farmer, 18);
    upsert_symmetric(&mut pool, married_minor, spouse_of_minor, BondType::Marriage as u8, 50, 1);

    let dep_index = build_dependent_index(&pool);
    let deps = resolve_dependents(&pool, parent_a, parent_b, &dep_index);
    assert_eq!(deps.len(), 0, "married minor is independent household");
}

fn build_dependent_index(pool: &AgentPool) -> HashMap<u32, Vec<usize>> {
    let mut index: HashMap<u32, Vec<usize>> = HashMap::new();
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        if pool.ages[slot] >= AGE_ADULT { continue; }
        let pid0 = pool.parent_id_0[slot];
        if pid0 != chronicler_agents::agent::PARENT_NONE {
            index.entry(pid0).or_default().push(slot);
        }
        let pid1 = pool.parent_id_1[slot];
        if pid1 != chronicler_agents::agent::PARENT_NONE && pid1 != pid0 {
            index.entry(pid1).or_default().push(slot);
        }
    }
    index
}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household -- resolve_dependents`
Expected: FAIL — `resolve_dependents` not found.

- [ ] **Step 7: Implement `resolve_dependents`**

Add to `chronicler-agents/src/household.rs`:

```rust
/// Return sorted-by-slot list of dependent children for a household.
/// Dependents: alive, age < AGE_ADULT, listed in `dependent_index`, and NOT married.
/// `dependent_index` maps parent agent_id → Vec<child_slot>, pre-filtered to age < AGE_ADULT.
pub fn resolve_dependents(
    pool: &AgentPool,
    lead_slot: usize,
    spouse_slot: usize,
    dependent_index: &std::collections::HashMap<u32, Vec<usize>>,
) -> Vec<usize> {
    let lead_id = pool.ids[lead_slot];
    let spouse_id = pool.ids[spouse_slot];
    let mut deps: Vec<usize> = Vec::new();

    for &parent_id in &[lead_id, spouse_id] {
        if let Some(children) = dependent_index.get(&parent_id) {
            for &child_slot in children {
                if !pool.is_alive(child_slot) { continue; }
                // Marriage precedence: married minors form their own household
                if relationships::get_spouse_id(pool, child_slot).is_some() { continue; }
                deps.push(child_slot);
            }
        }
    }

    deps.sort_unstable();
    deps.dedup();
    deps
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household`
Expected: all 5 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/household.rs chronicler-agents/tests/test_m57b_household.rs
git commit -m "feat(m57b): household_effective_wealth and resolve_dependents helpers with tests"
```

---

### Task 3: Death Transfer (Inheritance)

**Files:**
- Modify: `chronicler-agents/src/household.rs`
- Modify: `chronicler-agents/tests/test_m57b_household.rs`

- [ ] **Step 1: Write failing tests for inheritance**

Add to `chronicler-agents/tests/test_m57b_household.rs`:

```rust
use chronicler_agents::household::{
    household_death_transfer, HouseholdStats, InheritanceEvent, TransferType,
};
use chronicler_agents::agent::{MAX_WEALTH, PARENT_NONE};
use std::collections::HashSet;

#[test]
fn test_spouse_first_transfer() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28);
    pool.wealth[a] = 50.0;
    pool.wealth[b] = 30.0;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a]].into_iter().collect();
    let parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    let mut stats = HouseholdStats::default();

    let (events, intents) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert_eq!(events.len(), 1);
    assert_eq!(events[0].transfer_type, TransferType::SpouseInherit);
    assert!((events[0].amount - 50.0).abs() < 0.01);
    assert!((pool.wealth[b] - 80.0).abs() < 0.01, "spouse got estate");
    assert_eq!(stats.inheritance_transfers_spouse, 1);
    // Spec: spouse DeathOfKin memory intent emitted
    assert_eq!(intents.len(), 1, "spouse gets DeathOfKin intent");
    assert_eq!(intents[0].agent_slot, b);
}

#[test]
fn test_double_death_goes_to_children() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 40);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 38);
    pool.wealth[a] = 100.0;
    pool.wealth[b] = 60.0;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let child1 = spawn(&mut pool, 0, 0, Occupation::Farmer, 10);
    pool.parent_id_0[child1] = pool.ids[a];
    pool.parent_id_1[child1] = pool.ids[b];
    pool.wealth[child1] = 5.0;
    let child2 = spawn(&mut pool, 0, 0, Occupation::Farmer, 8);
    pool.parent_id_0[child2] = pool.ids[a];
    pool.parent_id_1[child2] = pool.ids[b];
    pool.wealth[child2] = 5.0;

    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a], pool.ids[b]].into_iter().collect();
    let mut parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    parent_to_children.entry(pool.ids[a]).or_default().push(child1);
    parent_to_children.entry(pool.ids[a]).or_default().push(child2);
    parent_to_children.entry(pool.ids[b]).or_default().push(child1);
    parent_to_children.entry(pool.ids[b]).or_default().push(child2);
    let mut stats = HouseholdStats::default();

    // A dies: both in dead_ids, so no spouse transfer → children split
    let (events_a, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert_eq!(events_a.len(), 2, "split between 2 children");
    for e in &events_a {
        assert_eq!(e.transfer_type, TransferType::OrphanSplit);
        assert!((e.amount - 50.0).abs() < 0.01, "100 / 2 = 50 each");
    }
    assert_eq!(stats.inheritance_transfers_child, 2);
}

#[test]
fn test_no_heirs_wealth_lost() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 50);
    pool.wealth[a] = 200.0;
    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a]].into_iter().collect();
    let parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    let mut stats = HouseholdStats::default();

    let (events, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert!(events.is_empty(), "no heirs: wealth lost");
}

#[test]
fn test_max_wealth_clamp_overflow_tracked() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28);
    pool.wealth[a] = MAX_WEALTH;
    pool.wealth[b] = MAX_WEALTH - 10.0;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a]].into_iter().collect();
    let parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    let mut stats = HouseholdStats::default();

    let (events, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert_eq!(events.len(), 1);
    assert!((pool.wealth[b] - MAX_WEALTH).abs() < 0.01, "clamped to MAX_WEALTH");
    assert!(events[0].overflow > 0.0, "overflow tracked");
    assert!(stats.inheritance_wealth_lost > 0.0, "stat recorded");
}

#[test]
fn test_adult_child_fallback() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 50);
    pool.wealth[a] = 90.0;
    let adult_child = spawn(&mut pool, 0, 0, Occupation::Soldier, AGE_ADULT + 5);
    pool.parent_id_0[adult_child] = pool.ids[a];
    pool.wealth[adult_child] = 10.0;

    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a]].into_iter().collect();
    let mut parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    parent_to_children.entry(pool.ids[a]).or_default().push(adult_child);
    let mut stats = HouseholdStats::default();

    let (events, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert_eq!(events.len(), 1);
    assert_eq!(events[0].transfer_type, TransferType::AdultChildSplit);
    assert!((pool.wealth[adult_child] - 100.0).abs() < 0.01);
}

#[test]
fn test_heir_eligibility_triple_check() {
    let mut pool = AgentPool::new(10);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 50);
    pool.wealth[a] = 100.0;
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 10);
    pool.parent_id_0[child] = pool.ids[a];
    // Child is also dying this tick
    let dead_ids: HashSet<u32> = [pool.ids[a], pool.ids[child]].into_iter().collect();
    let id_to_slot = build_id_to_slot(&pool);
    let mut parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    parent_to_children.entry(pool.ids[a]).or_default().push(child);
    let mut stats = HouseholdStats::default();

    let (events, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );
    assert!(events.is_empty(), "child in dead_ids: not eligible");
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household -- test_spouse_first`
Expected: FAIL — `household_death_transfer` not found.

- [ ] **Step 3: Implement `household_death_transfer`**

Add to `chronicler-agents/src/household.rs`:

```rust
/// Process inheritance for a single dying agent. Called inside the death-apply loop,
/// BEFORE pool.kill() and BEFORE death_cleanup_sweep.
///
/// Returns (Vec<InheritanceEvent>, Vec<MemoryIntent>). Mutates pool.wealth for heirs.
/// Updates `stats` counters for diagnostics. Memory intents must be appended to the
/// tick-level `memory_intents` vec by the caller.
pub fn household_death_transfer(
    pool: &mut AgentPool,
    dying_slot: usize,
    full_dead_ids: &std::collections::HashSet<u32>,
    id_to_slot: &std::collections::HashMap<u32, usize>,
    parent_to_children: &std::collections::HashMap<u32, Vec<usize>>,
    stats: &mut HouseholdStats,
) -> (Vec<InheritanceEvent>, Vec<crate::memory::MemoryIntent>) {
    let estate = pool.wealth[dying_slot];
    if estate <= 0.0 {
        return (Vec::new(), Vec::new());
    }
    let dying_id = pool.ids[dying_slot];
    let mut intents: Vec<crate::memory::MemoryIntent> = Vec::new();

    // Try spouse-first
    if let Some(spouse_id) = relationships::get_spouse_id(pool, dying_slot) {
        if !full_dead_ids.contains(&spouse_id) {
            if let Some(&spouse_slot) = id_to_slot.get(&spouse_id) {
                if pool.is_alive(spouse_slot) && pool.ids[spouse_slot] == spouse_id {
                    let before = pool.wealth[spouse_slot];
                    pool.wealth[spouse_slot] = (before + estate).min(crate::agent::MAX_WEALTH);
                    let actual = pool.wealth[spouse_slot] - before;
                    let overflow = estate - actual;
                    stats.inheritance_transfers_spouse += 1;
                    stats.inheritance_wealth_lost += overflow;
                    // Spec-required: spouse DeathOfKin memory intent
                    intents.push(crate::memory::MemoryIntent {
                        agent_slot: spouse_slot,
                        expected_agent_id: pool.ids[spouse_slot],
                        event_type: crate::memory::MemoryEventType::DeathOfKin as u8,
                        source_civ: pool.civ_affinities[spouse_slot],
                        intensity: crate::agent::DEATHOFKIN_DEFAULT_INTENSITY,
                        is_legacy: false,
                        decay_factor_override: None,
                    });
                    return (vec![InheritanceEvent {
                        heir_slot: spouse_slot,
                        deceased_id: dying_id,
                        amount: actual,
                        overflow,
                        transfer_type: TransferType::SpouseInherit,
                    }], intents);
                }
            }
        }
    }

    // No spouse — try children
    let heirs = find_child_heirs(pool, dying_id, full_dead_ids, id_to_slot, parent_to_children);
    if heirs.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let (transfer_type, is_dependent) = if heirs.iter().any(|&s| pool.ages[s] < crate::agent::AGE_ADULT) {
        (TransferType::OrphanSplit, true)
    } else {
        (TransferType::AdultChildSplit, false)
    };
    let _ = is_dependent; // used only for type selection

    let share = estate / heirs.len() as f32;
    let mut events = Vec::with_capacity(heirs.len());
    for &heir_slot in &heirs {
        let before = pool.wealth[heir_slot];
        pool.wealth[heir_slot] = (before + share).min(crate::agent::MAX_WEALTH);
        let actual = pool.wealth[heir_slot] - before;
        let overflow = share - actual;
        stats.inheritance_transfers_child += 1;
        stats.inheritance_wealth_lost += overflow;
        events.push(InheritanceEvent {
            heir_slot,
            deceased_id: dying_id,
            amount: actual,
            overflow,
            transfer_type,
        });
    }
    (events, intents)
}

/// Find eligible child heirs. First pass: dependent children (age < AGE_ADULT).
/// If empty, second pass: all living children (any age). Sorted by slot for determinism.
fn find_child_heirs(
    pool: &AgentPool,
    dying_id: u32,
    full_dead_ids: &std::collections::HashSet<u32>,
    id_to_slot: &std::collections::HashMap<u32, usize>,
    parent_to_children: &std::collections::HashMap<u32, Vec<usize>>,
) -> Vec<usize> {
    let children_slots: Vec<usize> = parent_to_children
        .get(&dying_id)
        .map(|v| v.as_slice())
        .unwrap_or(&[])
        .iter()
        .copied()
        .filter(|&slot| {
            pool.is_alive(slot)
                && !full_dead_ids.contains(&pool.ids[slot])
                && id_to_slot.get(&pool.ids[slot]).copied() == Some(slot) // stale-map defense
        })
        .collect();

    // First pass: dependents only
    let mut dependents: Vec<usize> = children_slots
        .iter()
        .copied()
        .filter(|&s| pool.ages[s] < crate::agent::AGE_ADULT)
        .collect();
    if !dependents.is_empty() {
        dependents.sort_unstable();
        return dependents;
    }

    // Second pass: all children (adult fallback)
    let mut all: Vec<usize> = children_slots;
    all.sort_unstable();
    all
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household`
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/household.rs chronicler-agents/tests/test_m57b_household.rs
git commit -m "feat(m57b): household_death_transfer with spouse-first, orphan split, and adult-child fallback"
```

---

### Task 4: Wire Death Transfer into Tick

**Files:**
- Modify: `chronicler-agents/src/tick.rs`
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Add `HouseholdStats` to `tick_agents` return type**

In `chronicler-agents/src/tick.rs`, change the return type at line 55 from:

```rust
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug) {
```

to:

```rust
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug, crate::household::HouseholdStats) {
```

Add `let mut household_stats = crate::household::HouseholdStats::default();` after the `memory_intents` declaration (around line 64).

Change the return statement at the end of `tick_agents` to include `household_stats` as the 5th tuple element.

- [ ] **Step 2: Precompute `full_dead_ids` before death-apply loop**

In `tick.rs`, before the `for (dr, _) in &demo_results` loop (around line 501), add:

```rust
    // M57b: Precompute full dead set for inheritance eligibility.
    // Reused later by death_cleanup_sweep.
    let full_dead_ids: std::collections::HashSet<u32> = demo_results
        .iter()
        .flat_map(|(dr, _)| dr.deaths.iter().map(|&(slot, _)| pool.ids[slot]))
        .collect();
```

- [ ] **Step 3: Insert `household_death_transfer` call in death-apply loop**

In the death-apply loop, BEFORE the existing DeathOfKin memory intents (line 514), add:

```rust
            // M57b: Inheritance transfer — MUST run before DeathOfKin and pool.kill
            let (_inheritance_events, spouse_intents) = crate::household::household_death_transfer(
                pool, slot, &full_dead_ids, &id_to_slot, &parent_to_children,
                &mut household_stats,
            );
            memory_intents.extend(spouse_intents);
```

- [ ] **Step 4: Count `births_by_marital_status` in birth-apply loop**

In the births section of the death-apply loop (around line 565), after `pool.spawn(...)` and parent setup, add:

```rust
            // M57b: Count births by marital status
            if birth.other_parent_id != crate::agent::PARENT_NONE {
                household_stats.births_married_parent += 1;
            } else {
                household_stats.births_unmarried_parent += 1;
            }
```

- [ ] **Step 5: Reuse `full_dead_ids` for `death_cleanup_sweep`**

Replace the existing `dead_ids` construction at line 659 with a reference to `full_dead_ids`:

Change:
```rust
    let dead_ids: std::collections::HashSet<u32> = events.iter()
        .filter(|e| e.event_type == 0)
        .map(|e| e.agent_id)
        .collect();
```

To:
```rust
    // M57b: Reuse precomputed full_dead_ids (same set, built before death-apply loop)
    let dead_ids = &full_dead_ids;
```

And update the `if !dead_ids.is_empty()` and the `death_cleanup_sweep` call to use a reference.

- [ ] **Step 6: Update `ffi.rs` to accept 5-tuple return**

In `chronicler-agents/src/ffi.rs`, find the `tick_agents` call site (around line 2296). Update destructuring:

```rust
        let (events, kin_failures, formation_stats, demo_debug, household_stats) = crate::tick::tick_agents(
```

Add a field to `AgentSimulator`:

```rust
    household_stats: crate::household::HouseholdStats,
```

Initialize in `new()`:

```rust
            household_stats: crate::household::HouseholdStats::default(),
```

Store after tick:

```rust
        self.household_stats = household_stats;
```

- [ ] **Step 7: Add `get_household_stats` PyO3 method to `AgentSimulator`**

In `ffi.rs`, after `get_relationship_stats` (around line 2900), add:

```rust
    /// M57b: Return household stats from last tick as a flat HashMap.
    #[pyo3(name = "get_household_stats")]
    pub fn get_household_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("inheritance_transfers_spouse".into(), self.household_stats.inheritance_transfers_spouse as f64);
        stats.insert("inheritance_transfers_child".into(), self.household_stats.inheritance_transfers_child as f64);
        stats.insert("inheritance_wealth_lost".into(), self.household_stats.inheritance_wealth_lost as f64);
        stats.insert("household_migrations_follow".into(), self.household_stats.household_migrations_follow as f64);
        stats.insert("household_migrations_cancelled_rebellion".into(), self.household_stats.household_migrations_cancelled_rebellion as f64);
        stats.insert("household_migrations_cancelled_catastrophe".into(), self.household_stats.household_migrations_cancelled_catastrophe as f64);
        stats.insert("household_dependent_overrides".into(), self.household_stats.household_dependent_overrides as f64);
        stats.insert("births_married_parent".into(), self.household_stats.births_married_parent as f64);
        stats.insert("births_unmarried_parent".into(), self.household_stats.births_unmarried_parent as f64);
        Ok(stats)
    }
```

- [ ] **Step 8: Update internal tick test destructuring**

In `chronicler-agents/src/tick.rs`, update the two existing `tick_agents` call sites in tests that destructure the 4-tuple:

Line ~1366: change `let (events, _, _, _) = tick_agents(...)` to `let (events, _, _, _, _) = tick_agents(...)`

Line ~1473: change `let (events, _, _, _) = tick_agents(...)` to `let (events, _, _, _, _) = tick_agents(...)`

Search for any other `tick_agents(` call sites in the crate and update their destructuring to 5-tuple.

- [ ] **Step 9: Verify compilation**

Run: `cargo check -p chronicler-agents`
Expected: compiles with no errors.

- [ ] **Step 10: Run full test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: all existing tests + M57b tests pass. No regressions.

- [ ] **Step 11: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m57b): wire death transfer and birth counting into tick, add get_household_stats FFI"
```

---

### Task 5: Joint Migration Consolidation

**Files:**
- Modify: `chronicler-agents/src/behavior.rs`
- Modify: `chronicler-agents/src/household.rs`
- Modify: `chronicler-agents/tests/test_m57b_household.rs`

- [ ] **Step 0: Make `PendingDecisions::new()` public**

In `chronicler-agents/src/behavior.rs`, line 421, change:

```rust
    fn new() -> Self {
```

to:

```rust
    pub fn new() -> Self {
```

This is needed by `consolidate_household_migrations` tests (integration tests can't call private methods).

- [ ] **Step 1: Write failing tests for migration consolidation**

Add to `chronicler-agents/tests/test_m57b_household.rs`:

```rust
use chronicler_agents::behavior::PendingDecisions;
use chronicler_agents::household::consolidate_household_migrations;

#[test]
fn test_spouse_follows_lead_migration() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 23);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1)); // A migrates 0 → 1
    // B stays (no action)

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    // B should now also migrate 0 → 1
    assert!(pds[0].migrations.iter().any(|&(s, _, t)| s == b && t == 1),
        "trailing spouse should follow");
    assert_eq!(stats.household_migrations_follow, 1);
}

#[test]
fn test_spouse_rebellion_cancels_migration() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 23);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1));
    pds[0].rebellions.push((b, 0)); // B rebels

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    assert!(!pds[0].migrations.iter().any(|&(s, _, _)| s == a),
        "lead migration removed");
    assert!(pds[0].rebellions.iter().any(|&(s, _)| s == b),
        "rebellion preserved");
    assert_eq!(stats.household_migrations_cancelled_rebellion, 1);
}

#[test]
fn test_catastrophe_gate_cancels_household() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 23);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[1].food_sufficiency = 0.1; // below CATASTROPHE_FOOD_THRESHOLD
    let contested = vec![false, true]; // region 1 contested

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1));

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    assert!(pds[0].migrations.is_empty(), "catastrophe cancelled all migrations");
    assert_eq!(stats.household_migrations_cancelled_catastrophe, 1);
}

#[test]
fn test_dependent_follows_household() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 10);
    pool.parent_id_0[child] = pool.ids[a];
    pool.parent_id_1[child] = pool.ids[b];
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1));

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    assert!(pds[0].migrations.iter().any(|&(s, _, t)| s == child && t == 1),
        "dependent child follows");
}

#[test]
fn test_married_minor_excluded_from_dependents() {
    let mut pool = AgentPool::new(20);
    let parent_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 35);
    let parent_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 33);
    upsert_symmetric(&mut pool, parent_a, parent_b, BondType::Marriage as u8, 50, 1);
    let married_minor = spawn(&mut pool, 0, 0, Occupation::Farmer, 17);
    pool.parent_id_0[married_minor] = pool.ids[parent_a];
    pool.parent_id_1[married_minor] = pool.ids[parent_b];
    let minor_spouse = spawn(&mut pool, 0, 0, Occupation::Farmer, 18);
    upsert_symmetric(&mut pool, married_minor, minor_spouse, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((parent_a, 0, 1));

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    assert!(!pds[0].migrations.iter().any(|&(s, _, _)| s == married_minor),
        "married minor not dragged as dependent");
}

#[test]
fn test_both_spouses_migrate_lower_slot_leads() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 23);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![
        RegionState::new(0),
        RegionState::new(1),
        RegionState::new(2),
    ];
    let contested = vec![false, false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1)); // A wants region 1
    pds[0].migrations.push((b, 0, 2)); // B wants region 2
    // Lower slot (a) should lead — both go to region 1

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    let a_dest: Vec<u16> = pds[0].migrations.iter().filter(|m| m.0 == a).map(|m| m.2).collect();
    let b_dest: Vec<u16> = pds[0].migrations.iter().filter(|m| m.0 == b).map(|m| m.2).collect();
    assert_eq!(a_dest, vec![1], "lead keeps destination");
    assert_eq!(b_dest, vec![1], "trailing follows lead destination");
}

#[test]
fn test_primary_action_invariant_after_consolidation() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 23);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 12);
    pool.parent_id_0[child] = pool.ids[a];
    pool.parent_id_1[child] = pool.ids[b];
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1));
    pds[0].occupation_switches.push((b, 3)); // B was switching
    pds[0].rebellions.push((child, 0)); // child was rebelling

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    // Check no slot appears in more than one primary action list
    let mut seen: std::collections::HashSet<usize> = std::collections::HashSet::new();
    for &(s, _, _) in &pds[0].migrations { assert!(seen.insert(s), "slot {} in multiple", s); }
    for &(s, _) in &pds[0].rebellions { assert!(seen.insert(s), "slot {} in multiple", s); }
    for &(s, _) in &pds[0].occupation_switches { assert!(seen.insert(s), "slot {} in multiple", s); }
}

#[test]
fn test_cancel_removes_dependent_independent_migration() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28);
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 12);
    pool.parent_id_0[child] = pool.ids[a];
    pool.parent_id_1[child] = pool.ids[b];
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
    let contested = vec![false, false, false];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1)); // A migrates
    pds[0].rebellions.push((b, 0)); // B rebels → cancel
    pds[0].migrations.push((child, 0, 2)); // child independently migrating

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    // All household migrations should be removed
    assert!(!pds[0].migrations.iter().any(|&(s, _, _)| s == a), "lead removed");
    assert!(!pds[0].migrations.iter().any(|&(s, _, _)| s == child), "dependent migration removed on cancel");
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household -- consolidate`
Expected: FAIL — `consolidate_household_migrations` not found.

- [ ] **Step 3: Implement `consolidate_household_migrations`**

Add to `chronicler-agents/src/household.rs`:

```rust
use crate::behavior::PendingDecisions;

/// Consolidate household migrations in place. Runs post-decision, pre-apply.
/// Only touches migrations, rebellions, and occupation_switches.
/// Never touches loyalty_flips or loyalty_drifts (background operations).
pub fn consolidate_household_migrations(
    pool: &AgentPool,
    pending_decisions: &mut [PendingDecisions],
    regions: &[RegionState],
    contested_regions: &[bool],
    id_to_slot: &std::collections::HashMap<u32, usize>,
    stats: &mut HouseholdStats,
) {
    // Build dependent index for this phase (pre-demographics, all alive)
    let dep_index = build_dependent_index_for_migration(pool);

    for bucket_idx in 0..pending_decisions.len() {
        let bucket = &pending_decisions[bucket_idx];

        // Collect married migrator pairs in this bucket
        let mut pairs: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();
        let migration_snapshot: Vec<(usize, u16, u16)> = bucket.migrations.clone();

        for &(slot, from, _to) in &migration_snapshot {
            if let Some(spouse_id) = relationships::get_spouse_id(pool, slot) {
                if let Some(&spouse_slot) = id_to_slot.get(&spouse_id) {
                    if pool.is_alive(spouse_slot)
                        && pool.ids[spouse_slot] == spouse_id
                        && pool.regions[spouse_slot] == from // co-located
                    {
                        let canonical = (slot.min(spouse_slot), slot.max(spouse_slot));
                        pairs.insert(canonical);
                    }
                }
            }
        }

        if pairs.is_empty() { continue; }

        // Sort for deterministic processing
        let mut sorted_pairs: Vec<(usize, usize)> = pairs.into_iter().collect();
        sorted_pairs.sort_unstable();

        let bucket = &mut pending_decisions[bucket_idx];

        for (low_slot, high_slot) in sorted_pairs {
            // Determine lead: the one who is migrating. If both, lower slot leads.
            let low_mig = bucket.migrations.iter().find(|m| m.0 == low_slot).copied();
            let high_mig = bucket.migrations.iter().find(|m| m.0 == high_slot).copied();

            let (lead_slot, lead_from, lead_to, trailing_slot) = match (low_mig, high_mig) {
                (Some(lm), _) => (lm.0, lm.1, lm.2, high_slot), // lower leads
                (None, Some(hm)) => (hm.0, hm.1, hm.2, low_slot),
                (None, None) => continue, // neither migrating anymore (edited by earlier proposal)
            };

            // Pre-apply recheck: lead still has migration?
            if !bucket.migrations.iter().any(|m| m.0 == lead_slot) {
                continue;
            }

            // Find dependents for this household
            let dep_slots = collect_dependents_for_consolidation(
                pool, lead_slot, trailing_slot, lead_from, &dep_index,
            );

            // Check trailing spouse rebellion → CANCEL (short-circuit precedence)
            let spouse_rebelling = bucket.rebellions.iter().any(|&(s, _)| s == trailing_slot);
            if spouse_rebelling {
                stats.household_migrations_cancelled_rebellion += 1;
                // CANCEL: remove all household migrations
                bucket.migrations.retain(|m| m.0 != lead_slot && m.0 != trailing_slot);
                for &dep in &dep_slots {
                    bucket.migrations.retain(|m| m.0 != dep);
                }
                continue;
            }

            // Catastrophe gate
            let is_catastrophic = (lead_to as usize) < regions.len()
                && (lead_to as usize) < contested_regions.len()
                && contested_regions[lead_to as usize]
                && regions[lead_to as usize].food_sufficiency < crate::agent::CATASTROPHE_FOOD_THRESHOLD;

            if is_catastrophic {
                stats.household_migrations_cancelled_catastrophe += 1;
                // CANCEL: remove all household migrations
                bucket.migrations.retain(|m| m.0 != lead_slot && m.0 != trailing_slot);
                for &dep in &dep_slots {
                    bucket.migrations.retain(|m| m.0 != dep);
                }
                continue;
            }

            // APPROVED: trailing spouse follows
            // Remove trailing's existing migration (if different destination)
            bucket.migrations.retain(|m| m.0 != trailing_slot);
            bucket.migrations.push((trailing_slot, lead_from, lead_to));
            // Remove trailing from rebellion/switch (primary action replaced)
            bucket.rebellions.retain(|&(s, _)| s != trailing_slot);
            bucket.occupation_switches.retain(|&(s, _)| s != trailing_slot);
            stats.household_migrations_follow += 1;

            // APPROVED: dependents follow
            for &dep in &dep_slots {
                bucket.migrations.retain(|m| m.0 != dep);
                bucket.migrations.push((dep, lead_from, lead_to));
                bucket.rebellions.retain(|&(s, _)| s != dep);
                bucket.occupation_switches.retain(|&(s, _)| s != dep);
                stats.household_migrations_follow += 1;
                stats.household_dependent_overrides += 1;
            }
        }

        // Deduplicate by slot (keep last entry for each slot)
        let bucket = &mut pending_decisions[bucket_idx];
        let mut seen: std::collections::HashSet<usize> = std::collections::HashSet::new();
        let mut deduped: Vec<(usize, u16, u16)> = Vec::new();
        for &mig in bucket.migrations.iter().rev() {
            if seen.insert(mig.0) {
                deduped.push(mig);
            }
        }
        deduped.reverse();
        bucket.migrations = deduped;
    }
}

fn build_dependent_index_for_migration(pool: &AgentPool) -> std::collections::HashMap<u32, Vec<usize>> {
    let mut index: std::collections::HashMap<u32, Vec<usize>> = std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        if pool.ages[slot] >= crate::agent::AGE_ADULT { continue; }
        let pid0 = pool.parent_id_0[slot];
        if pid0 != crate::agent::PARENT_NONE {
            index.entry(pid0).or_default().push(slot);
        }
        let pid1 = pool.parent_id_1[slot];
        if pid1 != crate::agent::PARENT_NONE && pid1 != pid0 {
            index.entry(pid1).or_default().push(slot);
        }
    }
    index
}

fn collect_dependents_for_consolidation(
    pool: &AgentPool,
    lead_slot: usize,
    spouse_slot: usize,
    from_region: u16,
    dep_index: &std::collections::HashMap<u32, Vec<usize>>,
) -> Vec<usize> {
    let lead_id = pool.ids[lead_slot];
    let spouse_id = pool.ids[spouse_slot];
    let mut deps: Vec<usize> = Vec::new();
    for &parent_id in &[lead_id, spouse_id] {
        if let Some(children) = dep_index.get(&parent_id) {
            for &child_slot in children {
                if !pool.is_alive(child_slot) { continue; }
                if pool.regions[child_slot] != from_region { continue; } // co-located check
                if relationships::get_spouse_id(pool, child_slot).is_some() { continue; } // marriage precedence
                deps.push(child_slot);
            }
        }
    }
    deps.sort_unstable();
    deps.dedup();
    deps
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household`
Expected: all tests PASS (19 total).

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/household.rs chronicler-agents/tests/test_m57b_household.rs
git commit -m "feat(m57b): consolidate_household_migrations with spouse follow, catastrophe gate, and dependent handling"
```

---

### Task 6: Wire Migration Consolidation into Tick + Pre-decision `id_to_slot`

**Files:**
- Modify: `chronicler-agents/src/tick.rs`

- [ ] **Step 1: Build pre-decision `id_to_slot` map**

In `tick.rs`, after `compute_region_stats` (around line 145) and before the decisions rayon block (line 150), add:

```rust
    // M57b: Pre-decision id_to_slot map for household_effective_wealth and consolidation.
    // Distinct from demographics-phase map (tick.rs:455) — this one uses pre-decision alive set.
    let pre_decision_id_to_slot: std::collections::HashMap<u32, usize> = {
        let mut map = std::collections::HashMap::with_capacity(pool.alive_count());
        for slot in 0..pool.capacity() {
            if pool.is_alive(slot) {
                map.insert(pool.ids[slot], slot);
            }
        }
        map
    };
```

- [ ] **Step 2: Insert consolidation call between decisions and apply**

After the `pending_decisions` collection (around line 174) and before the apply loop (line 179), add:

```rust
    // M57b: Household migration consolidation (post-decision, pre-apply)
    let mut pending_decisions = pending_decisions; // make mutable
    crate::household::consolidate_household_migrations(
        pool,
        &mut pending_decisions,
        regions,
        &signals.contested_regions,
        &pre_decision_id_to_slot,
        &mut household_stats,
    );
```

Note: the existing `pending_decisions` is collected as `Vec<_>` from rayon. You may need to adjust the variable binding. The `pending_decisions` from rayon `.collect()` is already owned, so `let mut pending_decisions = pending_decisions;` works or just shadow-bind.

- [ ] **Step 3: Verify compilation and run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: all tests pass. No regressions.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m57b): wire pre-decision id_to_slot and migration consolidation into tick"
```

---

### Task 7: Household-Effective Wealth in Migration Utility

**Files:**
- Modify: `chronicler-agents/src/behavior.rs`
- Modify: `chronicler-agents/src/tick.rs`

- [ ] **Step 1: Add `id_to_slot` parameter to `evaluate_region_decisions`**

In `chronicler-agents/src/behavior.rs`, change the signature at line 441:

```rust
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    regions: &[RegionState],
    region_state: &RegionState,
    stats: &RegionStats,
    region_id: usize,
    rng: &mut ChaCha8Rng,
    id_to_slot: &std::collections::HashMap<u32, usize>,  // M57b
) -> PendingDecisions {
```

- [ ] **Step 2: Wire household wealth into `migrate_utility` calculation**

In `evaluate_region_decisions`, after computing `migrate_util` (around line 482), add household wealth modulation for married agents:

```rust
        // M57b: Household-effective wealth modulates migration threshold for married agents.
        // Wealthier households are less likely to migrate (higher opportunity cost).
        if !is_displaced {
            let eff_wealth = crate::household::household_effective_wealth(pool, slot, id_to_slot);
            let personal_wealth = pool.wealth[slot];
            if eff_wealth > personal_wealth {
                // Married with pooled wealth: dampen migration utility slightly
                // Ratio > 1.0 means spouse has wealth; diminish by inverse sqrt of ratio
                let ratio = eff_wealth / personal_wealth.max(0.01);
                migrate_util *= 1.0 / ratio.sqrt();
            }
        }
```

- [ ] **Step 3: Update all call sites of `evaluate_region_decisions`**

In `tick.rs`, update the rayon call (around line 163):

```rust
                evaluate_region_decisions(
                    pool_ref,
                    slots,
                    regions,
                    &regions[region_id],
                    stats_ref,
                    region_id,
                    &mut rng,
                    &pre_decision_id_to_slot,  // M57b
                )
```

Check for any other call sites in `behavior.rs` tests — update them to pass an empty `HashMap` or a test-appropriate map.

- [ ] **Step 4: Update `evaluate_region_decisions` test helpers**

In `behavior.rs` tests, update calls to pass `&HashMap::new()` for the new parameter. Search for all test functions that call `evaluate_region_decisions` and add the parameter.

- [ ] **Step 5: Verify compilation and run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/behavior.rs chronicler-agents/src/tick.rs
git commit -m "feat(m57b): wire household_effective_wealth into migration utility via evaluate_region_decisions"
```

---

### Task 8: Python Stats Pipeline

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `src/chronicler/analytics.py`
- Modify: `src/chronicler/main.py`
- Create: `tests/test_m57b_household.py`

- [ ] **Step 1: Add household stats collection to `agent_bridge.py`**

In `src/chronicler/agent_bridge.py`, add to `__init__` (after `self._relationship_stats_history` around line 751):

```python
        self._household_stats_history: list = []
```

In `_process_tick_results()` (after the relationship stats block around line 821), add:

```python
        # M57b: household stats collection (always in agent modes)
        try:
            h_stats = self._sim.get_household_stats()
            self._household_stats_history.append(h_stats)
        except Exception:
            pass
```

Add a property (after `relationship_stats` property around line 973):

```python
    @property
    def household_stats(self) -> list:
        """M57b: Per-tick household stats history."""
        return self._household_stats_history
```

- [ ] **Step 2: Add Python parity helper**

Add to `agent_bridge.py` (as a module-level function or method):

```python
def household_effective_wealth_py(snapshot_df, relationships_df):
    """M57b: Python parity helper for household effective wealth.
    Uses get_all_relationships() for spouse lookup + snapshot for wealth.
    Diagnostics/analytics only — Rust is canonical."""
    import pyarrow as pa
    ids = snapshot_df.column("id").to_pylist()
    wealth = snapshot_df.column("wealth").to_pylist()
    id_to_wealth = dict(zip(ids, wealth))

    # Find marriage bonds from relationships
    spouse_map = {}
    if relationships_df is not None and relationships_df.num_rows > 0:
        agent_ids = relationships_df.column("agent_id").to_pylist()
        target_ids = relationships_df.column("target_id").to_pylist()
        bond_types = relationships_df.column("bond_type").to_pylist()
        MARRIAGE_BOND = 2  # BondType::Marriage
        for aid, tid, bt in zip(agent_ids, target_ids, bond_types):
            if bt == MARRIAGE_BOND:
                spouse_map[aid] = tid

    result = {}
    for aid, w in zip(ids, wealth):
        spouse_id = spouse_map.get(aid)
        if spouse_id is not None and spouse_id in id_to_wealth:
            result[aid] = w + id_to_wealth[spouse_id]
        else:
            result[aid] = w
    return result
```

- [ ] **Step 3: Wire household stats into bundle metadata in `main.py`**

In `src/chronicler/main.py`, find where relationship stats are written to bundle metadata (search for `relationship_stats`). Add alongside:

```python
        if agent_bridge is not None and hasattr(agent_bridge, 'household_stats'):
            metadata["household_stats"] = agent_bridge.household_stats
```

- [ ] **Step 4: Add `extract_household_stats` extractor in `analytics.py`**

In `src/chronicler/analytics.py`, after `extract_bond_health` (around line 1705), add:

```python
def extract_household_stats(bundles: list[dict]) -> dict:
    """M57b: Extract per-turn household stats from bundle metadata."""
    result = {"per_turn": [], "summary": {}}
    for bundle in bundles:
        metadata = bundle.get("metadata", {})
        h_stats = metadata.get("household_stats", [])
        result["per_turn"].extend(h_stats)

    if result["per_turn"]:
        keys = result["per_turn"][0].keys()
        for key in keys:
            vals = [t.get(key, 0) for t in result["per_turn"]]
            result["summary"][f"{key}_total"] = sum(vals)
            result["summary"][f"{key}_mean"] = sum(vals) / len(vals)
    return result
```

- [ ] **Step 5: Write Python tests**

Create `tests/test_m57b_household.py`:

```python
"""M57b: Household stats pipeline tests."""
import pytest
from chronicler.analytics import extract_household_stats


def test_extract_household_stats_empty():
    result = extract_household_stats([{"metadata": {}}])
    assert result["per_turn"] == []
    assert result["summary"] == {}


def test_extract_household_stats_round_trip():
    stats = [
        {"inheritance_transfers_spouse": 2.0, "births_married_parent": 5.0},
        {"inheritance_transfers_spouse": 1.0, "births_married_parent": 3.0},
    ]
    bundle = {"metadata": {"household_stats": stats}}
    result = extract_household_stats([bundle])
    assert len(result["per_turn"]) == 2
    assert result["summary"]["inheritance_transfers_spouse_total"] == 3.0
    assert result["summary"]["births_married_parent_mean"] == 4.0


def test_household_stats_reset_each_tick():
    """M57b: Verify household counters reset each tick (not accumulated).
    Two-tick assertion: counters from tick 1 must not bleed into tick 2."""
    from chronicler.main import execute_run
    from chronicler.world_gen import generate_world

    world = generate_world(seed=99, num_civs=4, num_regions=8)
    execute_run(world, turns=5, agents="hybrid", narrator="local",
                narrate=False, quiet=True)
    bridge = world._agent_bridge
    if bridge is None:
        pytest.skip("no agent bridge in this run")
    stats_history = bridge.household_stats
    if len(stats_history) < 2:
        pytest.skip("not enough ticks for reset test")
    # Each entry is an independent tick snapshot, not cumulative.
    # If counters were accumulated, later ticks would have >= earlier values for ALL keys.
    # With reset, it's normal for some ticks to have 0 while others have >0.
    has_zero_in_later_tick = False
    for key in stats_history[0]:
        vals = [s.get(key, 0) for s in stats_history]
        if any(v > 0 for v in vals) and any(v == 0 for v in vals[1:]):
            has_zero_in_later_tick = True
            break
    # If every counter monotonically increases, reset is broken.
    # This test passes as long as at least one counter resets to 0 in a later tick.
    assert has_zero_in_later_tick or all(
        s.get("inheritance_transfers_spouse", 0) == 0 for s in stats_history
    ), "counters should reset each tick, not accumulate"
```

- [ ] **Step 6: Run Python tests**

Run: `pytest tests/test_m57b_household.py -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/analytics.py src/chronicler/main.py tests/test_m57b_household.py
git commit -m "feat(m57b): Python household stats pipeline — collection, extraction, and parity helper"
```

---

### Task 9: Agents-Off Smoke Test & Cross-Civ Affinity Invariant

**Files:**
- Modify: `chronicler-agents/tests/test_m57b_household.rs`
- Modify: `tests/test_m57b_household.py`

- [ ] **Step 1: Add cross-civ affinity invariant test (Rust)**

Add to `chronicler-agents/tests/test_m57b_household.rs`:

```rust
#[test]
fn test_cross_civ_marriage_preserves_affinity() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 25); // civ 0
    pool.civ_affinities[a] = 0;
    let b = spawn(&mut pool, 0, 1, Occupation::Farmer, 23); // civ 1
    pool.civ_affinities[b] = 1;
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    let id_to_slot = build_id_to_slot(&pool);
    let regions = vec![RegionState::new(0), RegionState::new(1)];
    let contested = vec![false, false];

    let civ_a_before = pool.civ_affinities[a];
    let civ_b_before = pool.civ_affinities[b];

    let mut pds = vec![PendingDecisions::new(), PendingDecisions::new()];
    pds[0].migrations.push((a, 0, 1));

    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut pds, &regions, &contested, &id_to_slot, &mut stats);

    assert_eq!(pool.civ_affinities[a], civ_a_before, "migration must not change civ_affinity");
    assert_eq!(pool.civ_affinities[b], civ_b_before, "follow must not change civ_affinity");
}
```

- [ ] **Step 2: Add `--agents=off` smoke test (Python)**

Add to `tests/test_m57b_household.py`:

```python
def test_agents_off_smoke():
    """M57b: --agents=off must not execute any household code paths."""
    from chronicler.main import execute_run
    from chronicler.models import WorldState
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_civs=4, num_regions=8)
    # Run 10 turns with agents=off
    execute_run(world, turns=10, agents="off", narrator="local",
                narrate=False, quiet=True)
    # If we get here without error, the smoke test passes.
    # Household helpers should never have been called.
    assert len(world.civilizations) > 0, "simulation completed"
```

- [ ] **Step 3: Run all tests**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household && pytest tests/test_m57b_household.py -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/test_m57b_household.rs tests/test_m57b_household.py
git commit -m "test(m57b): cross-civ affinity invariant and --agents=off smoke test"
```

---

### Task 10: Integration Test — Wealth Conservation

**Files:**
- Modify: `chronicler-agents/tests/test_m57b_household.rs`

- [ ] **Step 1: Write phase-local wealth conservation test**

Add to `chronicler-agents/tests/test_m57b_household.rs`:

```rust
#[test]
fn test_wealth_conservation_in_death_phase() {
    let mut pool = AgentPool::new(20);
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 50);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 48);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 10);
    pool.wealth[a] = 100.0;
    pool.wealth[b] = 80.0;
    pool.wealth[child] = 5.0;
    pool.parent_id_0[child] = pool.ids[a];
    pool.parent_id_1[child] = pool.ids[b];
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);

    let total_before = pool.wealth[a] + pool.wealth[b] + pool.wealth[child];

    // A dies, spouse B survives
    let id_to_slot = build_id_to_slot(&pool);
    let dead_ids: HashSet<u32> = [pool.ids[a]].into_iter().collect();
    let mut parent_to_children: HashMap<u32, Vec<usize>> = HashMap::new();
    parent_to_children.entry(pool.ids[a]).or_default().push(child);
    parent_to_children.entry(pool.ids[b]).or_default().push(child);
    let mut stats = HouseholdStats::default();

    let (events, _) = household_death_transfer(
        &mut pool, a, &dead_ids, &id_to_slot, &parent_to_children, &mut stats,
    );

    // Conservation: total wealth should equal sum of all living agents + overflow
    let total_overflow: f32 = events.iter().map(|e| e.overflow).sum();
    let total_after = pool.wealth[a] + pool.wealth[b] + pool.wealth[child]; // a's wealth is still readable pre-kill
    assert!(
        (total_before - (total_after + total_overflow)).abs() < 0.01,
        "wealth conservation: before={}, after={}, overflow={}",
        total_before, total_after, total_overflow,
    );
}
```

- [ ] **Step 2: Run test**

Run: `cargo nextest run -p chronicler-agents --test test_m57b_household -- conservation`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/test_m57b_household.rs
git commit -m "test(m57b): phase-local wealth conservation invariant test"
```

---

### Task 11: Rebuild Rust Extension & Full Validation

**Files:** No new files — validation only.

- [ ] **Step 1: Rebuild the Python extension**

Run: `pip install -e chronicler-agents/ --force-reinstall`

(On Windows, if the .pyd is locked: close any running Python processes first.)

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: all tests pass, no regressions.

- [ ] **Step 3: Run full Python test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass, no regressions.

- [ ] **Step 4: Run a quick smoke simulation**

Run: `python -m chronicler.main --seed 42 --turns 50 --agents hybrid --quiet`
Expected: completes without error. Check output for `marriage_formed` events and household stats in bundle.

- [ ] **Step 5: Commit any final fixes**

If any fixes were needed, commit them with descriptive messages.

---

### Task 12: Progress Doc Update

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Add M57b entry to progress doc**

Add a new section under Merged Milestones (or In-Progress depending on regression status):

```markdown
### M57b: Households, Inheritance & Joint Migration — implemented on `m57a-marriage-lineage`

- N commits on `m57a-marriage-lineage`. X Rust household tests, Y Python tests. Z total Rust tests, W Python tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-28-m57b-households-inheritance-joint-migration-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-28-m57b-households-inheritance-joint-migration.md`
- **Rust:**
  - `household.rs` (new): `household_effective_wealth`, `resolve_dependents`, `household_death_transfer`, `consolidate_household_migrations`, `HouseholdStats`, `InheritanceEvent`.
  - `tick.rs`: pre-decision `id_to_slot`, `full_dead_ids` precompute, death-transfer in death-apply loop, birth marital counting, household stats accumulation.
  - `behavior.rs`: `evaluate_region_decisions` gains `id_to_slot` param, `migrate_utility` modulated by household-effective wealth.
  - `ffi.rs`: `get_household_stats()` PyO3 method.
  - `agent.rs`: `CATASTROPHE_FOOD_THRESHOLD` constant.
- **Python:**
  - `agent_bridge.py`: `_household_stats_history`, collection in `_process_tick_results()`, `household_effective_wealth_py` parity helper.
  - `analytics.py`: `extract_household_stats()` extractor.
  - `main.py`: household stats in bundle metadata.
- **Regression:** 200-seed regression pending.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m57b): update progress doc with implementation status"
```
