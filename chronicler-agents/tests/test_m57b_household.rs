//! M57b Household: Integration tests for helpers, inheritance, and migration.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::relationships::{upsert_symmetric, BondType};
use chronicler_agents::household::{
    household_effective_wealth, resolve_dependents,
    household_death_transfer, HouseholdStats, TransferType,
};
use chronicler_agents::{AGE_ADULT, PARENT_NONE, MAX_WEALTH};
use std::collections::HashSet;
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

fn build_dependent_index(pool: &AgentPool) -> HashMap<u32, Vec<usize>> {
    let mut index: HashMap<u32, Vec<usize>> = HashMap::new();
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        if pool.ages[slot] >= AGE_ADULT { continue; }
        let pid0 = pool.parent_id_0[slot];
        if pid0 != PARENT_NONE {
            index.entry(pid0).or_default().push(slot);
        }
        let pid1 = pool.parent_id_1[slot];
        if pid1 != PARENT_NONE && pid1 != pid0 {
            index.entry(pid1).or_default().push(slot);
        }
    }
    index
}

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

// ─── Death Transfer (Inheritance) Tests ─────────────────────────────────────

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

    // A dies: both in dead_ids, so no spouse transfer -> children split
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
