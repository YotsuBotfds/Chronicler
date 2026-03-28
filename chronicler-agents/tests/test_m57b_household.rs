//! M57b Household: Integration tests for helpers, inheritance, and migration.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::relationships::{upsert_symmetric, BondType};
use chronicler_agents::household::{household_effective_wealth, resolve_dependents};
use chronicler_agents::{AGE_ADULT, PARENT_NONE};
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
