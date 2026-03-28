//! M57b: Household helpers — derived households, inheritance, joint migration.
//!
//! All functions are pure (no state, no RNG). Households are derived from
//! marriage bonds + parent links, not stored as entities.

use std::collections::HashMap;

use crate::pool::AgentPool;
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
                    return (
                        vec![InheritanceEvent {
                            heir_slot: spouse_slot,
                            deceased_id: dying_id,
                            amount: actual,
                            overflow,
                            transfer_type: TransferType::SpouseInherit,
                        }],
                        intents,
                    );
                }
            }
        }
    }

    // No spouse — try children
    let heirs = find_child_heirs(pool, dying_id, full_dead_ids, id_to_slot, parent_to_children);
    if heirs.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let transfer_type = if heirs
        .iter()
        .any(|&s| pool.ages[s] < crate::agent::AGE_ADULT)
    {
        TransferType::OrphanSplit
    } else {
        TransferType::AdultChildSplit
    };

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

/// Return combined household wealth for a married agent, or personal wealth if unmarried.
/// Uses `id_to_slot` for O(1) spouse slot resolution — never falls back to linear scan.
pub fn household_effective_wealth(
    pool: &AgentPool,
    slot: usize,
    id_to_slot: &HashMap<u32, usize>,
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

/// Return sorted-by-slot list of dependent children for a household.
/// Dependents: alive, age < AGE_ADULT, listed in `dependent_index`, and NOT married.
/// `dependent_index` maps parent agent_id -> Vec<child_slot>, pre-filtered to age < AGE_ADULT.
pub fn resolve_dependents(
    pool: &AgentPool,
    lead_slot: usize,
    spouse_slot: usize,
    dependent_index: &HashMap<u32, Vec<usize>>,
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
