//! M57b: Household helpers — derived households, inheritance, joint migration.
//!
//! All functions are pure (no state, no RNG). Households are derived from
//! marriage bonds + parent links, not stored as entities.

use std::collections::HashMap;

use crate::behavior::PendingDecisions;
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

// ─── Joint Migration Consolidation ─────────────────────────────────────────

/// Consolidate household migrations in place. Runs post-decision, pre-apply.
/// Only touches migrations, rebellions, and occupation_switches.
/// Never touches loyalty_flips or loyalty_drifts (background operations).
pub fn consolidate_household_migrations(
    pool: &AgentPool,
    pending_decisions: &mut [PendingDecisions],
    regions: &[RegionState],
    contested_regions: &[bool],
    id_to_slot: &HashMap<u32, usize>,
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

            // Check trailing spouse rebellion -> CANCEL (short-circuit precedence)
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

fn build_dependent_index_for_migration(pool: &AgentPool) -> HashMap<u32, Vec<usize>> {
    let mut index: HashMap<u32, Vec<usize>> = HashMap::new();
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
    dep_index: &HashMap<u32, Vec<usize>>,
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
