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
