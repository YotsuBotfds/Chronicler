//! M57b: Household helpers — derived households, inheritance, joint migration.
//!
//! All functions are pure (no state, no RNG). Households are derived from
//! marriage bonds + parent links, not stored as entities.

use std::collections::HashMap;

use crate::behavior::PendingDecisions;
use crate::decision_delivery::{
    MoveObserver, NoDelivery, MOVE_REASON_CATASTROPHE, MOVE_REASON_REBELLION,
    MOVE_ROLE_DEPENDENT, MOVE_ROLE_SPOUSE,
};
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
    /// What moved this tick's migrants, as decided before the household
    /// consolidation that adds followers (diagnostic; exported separately by
    /// `get_migration_driver_stats`, not by `get_household_stats`).
    pub migration_drivers: crate::migration_drivers::MigrationDriverStats,
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
pub fn household_death_transfer<L: crate::pool::SlotLookup>(
    pool: &mut AgentPool,
    dying_slot: usize,
    full_dead_ids: &std::collections::HashSet<u32>,
    id_to_slot: &L,
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
            if let Some(spouse_slot) = id_to_slot.slot_of(spouse_id) {
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
fn find_child_heirs<L: crate::pool::SlotLookup>(
    pool: &AgentPool,
    dying_id: u32,
    full_dead_ids: &std::collections::HashSet<u32>,
    id_to_slot: &L,
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
                && id_to_slot.slot_of(pool.ids[slot]) == Some(slot) // stale-map defense
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
pub fn household_effective_wealth<L: crate::pool::SlotLookup>(
    pool: &AgentPool,
    slot: usize,
    id_to_slot: &L,
) -> f32 {
    let personal = pool.wealth[slot];
    if let Some(spouse_id) = relationships::get_spouse_id(pool, slot) {
        if let Some(spouse_slot) = id_to_slot.slot_of(spouse_id) {
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
pub fn consolidate_household_migrations<L: crate::pool::SlotLookup>(
    pool: &AgentPool,
    pending_decisions: &mut [PendingDecisions],
    regions: &[RegionState],
    contested_regions: &[bool],
    id_to_slot: &L,
    stats: &mut HouseholdStats,
) {
    consolidate_household_migrations_observed(
        pool, pending_decisions, regions, contested_regions, id_to_slot, stats, &mut NoDelivery,
    );
}

/// The same consolidation with observations of the actual edits. The ordinary
/// wrapper instantiates a zero-sized sink; disabled hooks read no pool fields.
pub(crate) fn consolidate_household_migrations_observed<
    L: crate::pool::SlotLookup,
    O: MoveObserver,
>(
    pool: &AgentPool,
    pending_decisions: &mut [PendingDecisions],
    regions: &[RegionState],
    contested_regions: &[bool],
    id_to_slot: &L,
    stats: &mut HouseholdStats,
    observer: &mut O,
) {
    // Build dependent index for this phase (pre-demographics, all alive)
    let dep_index = build_dependent_index_for_migration(pool);

    for bucket_idx in 0..pending_decisions.len() {
        let bucket = &pending_decisions[bucket_idx];

        // Collect married migrator pairs in this bucket
        let mut pairs: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();
        let migration_snapshot: Vec<(usize, u16, u16)> = bucket.migrations.clone();

        for &(slot, from, _to) in &migration_snapshot {
            // M58a: Skip non-idle merchants — trip state takes precedence
            if pool.is_on_trip(slot) {
                continue;
            }
            if let Some(spouse_id) = relationships::get_spouse_id(pool, slot) {
                if let Some(spouse_slot) = id_to_slot.slot_of(spouse_id) {
                    // M58a: Don't follow a spouse who is on a trade trip
                    if pool.is_on_trip(spouse_slot) {
                        continue;
                    }
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
                let mut trailing_removed = false;
                bucket.migrations.retain(|m| {
                    let keep = m.0 != lead_slot && m.0 != trailing_slot;
                    if O::ENABLED && !keep {
                        trailing_removed |= m.0 == trailing_slot;
                        observer.cancelled(pool, bucket_idx, *m, lead_slot, trailing_slot,
                            MOVE_REASON_REBELLION, lead_to);
                    }
                    keep
                });
                if O::ENABLED && !trailing_removed {
                    observer.blocked(pool, bucket_idx, trailing_slot, lead_from, lead_to,
                        lead_slot, trailing_slot, MOVE_ROLE_SPOUSE, MOVE_REASON_REBELLION);
                }
                for &dep in &dep_slots {
                    let mut removed = false;
                    bucket.migrations.retain(|m| {
                        let keep = m.0 != dep;
                        if O::ENABLED && !keep {
                            removed = true;
                            observer.cancelled(pool, bucket_idx, *m, lead_slot, trailing_slot,
                                MOVE_REASON_REBELLION, lead_to);
                        }
                        keep
                    });
                    if O::ENABLED && !removed {
                        observer.blocked(pool, bucket_idx, dep, lead_from, lead_to,
                            lead_slot, trailing_slot, MOVE_ROLE_DEPENDENT, MOVE_REASON_REBELLION);
                    }
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
                let mut trailing_removed = false;
                bucket.migrations.retain(|m| {
                    let keep = m.0 != lead_slot && m.0 != trailing_slot;
                    if O::ENABLED && !keep {
                        trailing_removed |= m.0 == trailing_slot;
                        observer.cancelled(pool, bucket_idx, *m, lead_slot, trailing_slot,
                            MOVE_REASON_CATASTROPHE, lead_to);
                    }
                    keep
                });
                if O::ENABLED && !trailing_removed {
                    observer.blocked(pool, bucket_idx, trailing_slot, lead_from, lead_to,
                        lead_slot, trailing_slot, MOVE_ROLE_SPOUSE, MOVE_REASON_CATASTROPHE);
                }
                for &dep in &dep_slots {
                    let mut removed = false;
                    bucket.migrations.retain(|m| {
                        let keep = m.0 != dep;
                        if O::ENABLED && !keep {
                            removed = true;
                            observer.cancelled(pool, bucket_idx, *m, lead_slot, trailing_slot,
                                MOVE_REASON_CATASTROPHE, lead_to);
                        }
                        keep
                    });
                    if O::ENABLED && !removed {
                        observer.blocked(pool, bucket_idx, dep, lead_from, lead_to,
                            lead_slot, trailing_slot, MOVE_ROLE_DEPENDENT, MOVE_REASON_CATASTROPHE);
                    }
                }
                continue;
            }

            // Migration budget: followers count under the lead's largest term
            // (`migration_dominant` is in slot order: the region's slots are).
            let lead_term = bucket
                .migration_dominant
                .binary_search_by_key(&lead_slot, |&(s, _)| s)
                .map_or(crate::migration_drivers::MIGRATION_TERMS as u8, |i| bucket.migration_dominant[i].1);

            // APPROVED: trailing spouse follows
            // Remove trailing's existing migration (if different destination)
            let mut removed_count = 0;
            let mut last_removed = None;
            bucket.migrations.retain(|m| {
                let keep = m.0 != trailing_slot;
                if O::ENABLED && !keep {
                    removed_count += 1;
                    last_removed = Some((m.1, m.2));
                    observer.replacement_removed(pool, bucket_idx, *m, lead_slot, MOVE_ROLE_SPOUSE);
                }
                keep
            });
            bucket.migrations.push((trailing_slot, lead_from, lead_to));
            if O::ENABLED {
                observer.follower_written(pool, bucket_idx, trailing_slot, lead_from, lead_to,
                    lead_slot, MOVE_ROLE_SPOUSE, removed_count, last_removed);
            }
            bucket.migration_followers.push((trailing_slot, lead_term));
            // Remove trailing from rebellion/switch (primary action replaced)
            bucket.rebellions.retain(|&(s, _)| s != trailing_slot);
            bucket.occupation_switches.retain(|&(s, _)| s != trailing_slot);
            stats.household_migrations_follow += 1;
            stats.migration_drivers.record_follower(lead_term);

            // APPROVED: dependents follow
            for &dep in &dep_slots {
                let mut removed_count = 0;
                let mut last_removed = None;
                bucket.migrations.retain(|m| {
                    let keep = m.0 != dep;
                    if O::ENABLED && !keep {
                        removed_count += 1;
                        last_removed = Some((m.1, m.2));
                        observer.replacement_removed(pool, bucket_idx, *m, lead_slot, MOVE_ROLE_DEPENDENT);
                    }
                    keep
                });
                bucket.migrations.push((dep, lead_from, lead_to));
                if O::ENABLED {
                    observer.follower_written(pool, bucket_idx, dep, lead_from, lead_to,
                        lead_slot, MOVE_ROLE_DEPENDENT, removed_count, last_removed);
                }
                bucket.migration_followers.push((dep, lead_term));
                bucket.rebellions.retain(|&(s, _)| s != dep);
                bucket.occupation_switches.retain(|&(s, _)| s != dep);
                stats.household_migrations_follow += 1;
                stats.household_dependent_overrides += 1;
                stats.migration_drivers.record_follower(lead_term);
            }
        }

        // Deduplicate by slot (keep last entry for each slot)
        let bucket = &mut pending_decisions[bucket_idx];
        let mut seen: std::collections::HashSet<usize> = std::collections::HashSet::new();
        let mut deduped: Vec<(usize, u16, u16)> = Vec::new();
        for &mig in bucket.migrations.iter().rev() {
            if seen.insert(mig.0) {
                deduped.push(mig);
            } else if O::ENABLED {
                observer.dedup_removed(pool, bucket_idx, mig);
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

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(HouseholdStats {
    inheritance_transfers_spouse, inheritance_transfers_child, inheritance_wealth_lost,
    household_migrations_follow, household_migrations_cancelled_rebellion,
    household_migrations_cancelled_catastrophe, household_dependent_overrides,
    births_married_parent, births_unmarried_parent, migration_drivers,
});

#[cfg(test)]
mod delivery_tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::relationships::{upsert_symmetric, BondType};

    #[derive(Debug, PartialEq, Eq)]
    enum Edit {
        Replacement {
            bucket: usize, migration: (u32, u16, u16), lead_id: u32, role: u8,
        },
        Follower {
            bucket: usize, migration: (u32, u16, u16), lead_id: u32, role: u8,
            removed_count: usize, last_removed: Option<(u16, u16)>,
        },
        Cancelled {
            bucket: usize, migration: (u32, u16, u16), lead_id: u32,
            trailing_id: u32, reason: u8, rejected_to: u16,
        },
        Blocked {
            bucket: usize, migration: (u32, u16, u16), lead_id: u32,
            trailing_id: u32, role: u8, reason: u8,
        },
        Dedup { bucket: usize, migration: (u32, u16, u16) },
    }

    fn stable_migration(pool: &AgentPool, migration: (usize, u16, u16)) -> (u32, u16, u16) {
        (pool.ids[migration.0], migration.1, migration.2)
    }

    #[derive(Default)]
    struct Recorder { edits: Vec<Edit> }

    impl MoveObserver for Recorder {
        const ENABLED: bool = true;

        fn replacement_removed(&mut self, pool: &AgentPool, bucket: usize,
            migration: (usize, u16, u16), lead_slot: usize, role: u8) {
            self.edits.push(Edit::Replacement {
                bucket, migration: stable_migration(pool, migration), lead_id: pool.ids[lead_slot], role,
            });
        }

        fn follower_written(&mut self, pool: &AgentPool, bucket: usize, slot: usize,
            from: u16, to: u16, lead_slot: usize, role: u8, removed_count: usize,
            last_removed: Option<(u16, u16)>) {
            self.edits.push(Edit::Follower {
                bucket, migration: stable_migration(pool, (slot, from, to)),
                lead_id: pool.ids[lead_slot], role, removed_count, last_removed,
            });
        }

        fn cancelled(&mut self, pool: &AgentPool, bucket: usize,
            migration: (usize, u16, u16), lead_slot: usize, trailing_slot: usize,
            reason: u8, rejected_to: u16) {
            self.edits.push(Edit::Cancelled {
                bucket, migration: stable_migration(pool, migration), lead_id: pool.ids[lead_slot],
                trailing_id: pool.ids[trailing_slot], reason, rejected_to,
            });
        }

        fn blocked(&mut self, pool: &AgentPool, bucket: usize, slot: usize,
            from: u16, to: u16, lead_slot: usize, trailing_slot: usize, role: u8, reason: u8) {
            self.edits.push(Edit::Blocked {
                bucket, migration: stable_migration(pool, (slot, from, to)), lead_id: pool.ids[lead_slot],
                trailing_id: pool.ids[trailing_slot], role, reason,
            });
        }

        fn dedup_removed(&mut self, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16)) {
            self.edits.push(Edit::Dedup { bucket, migration: stable_migration(pool, migration) });
        }
    }

    struct DisabledHooks;

    impl MoveObserver for DisabledHooks {
        fn replacement_removed(&mut self, _: &AgentPool, _: usize,
            _: (usize, u16, u16), _: usize, _: u8) { panic!("disabled replacement hook"); }
        fn follower_written(&mut self, _: &AgentPool, _: usize, _: usize,
            _: u16, _: u16, _: usize, _: u8, _: usize,
            _: Option<(u16, u16)>) { panic!("disabled follower hook"); }
        fn cancelled(&mut self, _: &AgentPool, _: usize,
            _: (usize, u16, u16), _: usize, _: usize, _: u8, _: u16) { panic!("disabled cancellation hook"); }
        fn blocked(&mut self, _: &AgentPool, _: usize, _: usize,
            _: u16, _: u16, _: usize, _: usize, _: u8, _: u8) { panic!("disabled blocked hook"); }
        fn dedup_removed(&mut self, _: &AgentPool, _: usize,
            _: (usize, u16, u16)) { panic!("disabled dedup hook"); }
    }

    fn spawn(pool: &mut AgentPool, age: u16) -> usize {
        pool.spawn(0, 0, Occupation::Farmer, age, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE)
    }

    fn marry(pool: &mut AgentPool, a: usize, b: usize) {
        upsert_symmetric(pool, a, b, BondType::Marriage as u8, 50, 1);
    }

    fn regions() -> Vec<RegionState> {
        (0..4).map(|id| {
            let mut region = RegionState::new(id);
            region.controller_civ = 0;
            region.food_sufficiency = 1.0;
            region
        }).collect()
    }

    fn copy_pending(buckets: &[PendingDecisions]) -> Vec<PendingDecisions> {
        buckets.iter().map(|p| PendingDecisions {
            rebellions: p.rebellions.clone(), migrations: p.migrations.clone(),
            occupation_switches: p.occupation_switches.clone(), loyalty_flips: p.loyalty_flips.clone(),
            loyalty_drifts: p.loyalty_drifts.clone(),
            migration_changed_by_religion: p.migration_changed_by_religion,
            loyalty_drifts_damped_by_rally: p.loyalty_drifts_damped_by_rally,
            migration_drivers: p.migration_drivers.clone(),
            migration_dominant: p.migration_dominant.clone(), migration_followers: p.migration_followers.clone(),
        }).collect()
    }

    fn assert_pending_equal(left: &[PendingDecisions], right: &[PendingDecisions]) {
        assert_eq!(left.len(), right.len());
        for (a, b) in left.iter().zip(right) {
            assert_eq!(a.rebellions, b.rebellions);
            assert_eq!(a.migrations, b.migrations);
            assert_eq!(a.occupation_switches, b.occupation_switches);
            assert_eq!(a.loyalty_flips, b.loyalty_flips);
            assert_eq!(a.loyalty_drifts, b.loyalty_drifts);
            assert_eq!(a.migration_changed_by_religion, b.migration_changed_by_religion);
            assert_eq!(a.loyalty_drifts_damped_by_rally, b.loyalty_drifts_damped_by_rally);
            assert_eq!(a.migration_dominant, b.migration_dominant);
            assert_eq!(a.migration_followers, b.migration_followers);
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &a.migration_drivers),
                crate::persist::encode(crate::persist::KIND_AGENT, &b.migration_drivers));
        }
    }

    fn consolidate_and_check(pool: &AgentPool, regions: &[RegionState], contested: &[bool],
        input: &[PendingDecisions]) -> (Vec<PendingDecisions>, Recorder, HouseholdStats) {
        let before = crate::persist::encode(crate::persist::KIND_AGENT, pool);
        let ids = pool.build_id_slots();
        let mut ordinary = copy_pending(input);
        let mut observed = copy_pending(input);
        let mut disabled = copy_pending(input);
        let mut ordinary_stats = HouseholdStats::default();
        let mut observed_stats = HouseholdStats::default();
        let mut disabled_stats = HouseholdStats::default();
        let mut recorder = Recorder::default();
        consolidate_household_migrations(pool, &mut ordinary, regions, contested, &ids, &mut ordinary_stats);
        consolidate_household_migrations_observed(pool, &mut observed, regions, contested,
            &ids, &mut observed_stats, &mut recorder);
        consolidate_household_migrations_observed(pool, &mut disabled, regions, contested,
            &ids, &mut disabled_stats, &mut DisabledHooks);
        assert_pending_equal(&ordinary, &observed);
        assert_pending_equal(&ordinary, &disabled);
        let stats_bytes = crate::persist::encode(crate::persist::KIND_AGENT, &ordinary_stats);
        assert_eq!(stats_bytes, crate::persist::encode(crate::persist::KIND_AGENT, &observed_stats));
        assert_eq!(stats_bytes, crate::persist::encode(crate::persist::KIND_AGENT, &disabled_stats));
        assert_eq!(before, crate::persist::encode(crate::persist::KIND_AGENT, pool));
        (observed, recorder, observed_stats)
    }

    #[test]
    fn household_delivery_lead_uses_reused_lower_slot_and_same_target_is_replaced() {
        let mut pool = AgentPool::new(4);
        let old = spawn(&mut pool, 25);
        let high = spawn(&mut pool, 25);
        pool.kill(old);
        let low = spawn(&mut pool, 25);
        assert_eq!(low, old);
        assert!(low < high && pool.ids[low] > pool.ids[high]);
        marry(&mut pool, low, high);
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(high, 0, 1), (low, 0, 1)];
        pending.migration_dominant = vec![(low, 14), (high, 7)];
        let (result, recorder, stats) = consolidate_and_check(&pool, &regions(), &[false; 4], &[pending]);
        assert_eq!(recorder.edits, vec![
            Edit::Replacement { bucket: 0, migration: (pool.ids[high], 0, 1),
                lead_id: pool.ids[low], role: MOVE_ROLE_SPOUSE },
            Edit::Follower { bucket: 0, migration: (pool.ids[high], 0, 1),
                lead_id: pool.ids[low], role: MOVE_ROLE_SPOUSE,
                removed_count: 1, last_removed: Some((0, 1)) },
        ]);
        assert_eq!(result[0].migrations, vec![(low, 0, 1), (high, 0, 1)]);
        assert_eq!(result[0].migration_driver_of(high), 14, "the term label remains separate from follower provenance");
        assert_eq!(stats.household_migrations_follow, 1);
    }

    #[test]
    fn household_delivery_records_every_replaced_proposal_and_last_target() {
        let mut pool = AgentPool::new(2);
        let lead = spawn(&mut pool, 25);
        let spouse = spawn(&mut pool, 25);
        marry(&mut pool, lead, spouse);
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(lead, 0, 1), (spouse, 0, 2), (spouse, 0, 3)];
        let (_, recorder, _) = consolidate_and_check(&pool, &regions(), &[false; 4], &[pending]);
        assert_eq!(recorder.edits, vec![
            Edit::Replacement { bucket: 0, migration: (pool.ids[spouse], 0, 2),
                lead_id: pool.ids[lead], role: MOVE_ROLE_SPOUSE },
            Edit::Replacement { bucket: 0, migration: (pool.ids[spouse], 0, 3),
                lead_id: pool.ids[lead], role: MOVE_ROLE_SPOUSE },
            Edit::Follower { bucket: 0, migration: (pool.ids[spouse], 0, 1),
                lead_id: pool.ids[lead], role: MOVE_ROLE_SPOUSE,
                removed_count: 2, last_removed: Some((0, 3)) },
        ]);
    }

    #[test]
    fn household_delivery_rebellion_precedes_catastrophe_and_distinguishes_blocked_followers() {
        let mut pool = AgentPool::new(4);
        let lead = spawn(&mut pool, 25);
        let spouse = spawn(&mut pool, 25);
        let proposing_child = spawn(&mut pool, 10);
        let blocked_child = spawn(&mut pool, 10);
        marry(&mut pool, lead, spouse);
        pool.parent_id_0[proposing_child] = pool.ids[lead];
        pool.parent_id_0[blocked_child] = pool.ids[lead];
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(lead, 0, 1), (proposing_child, 0, 2)];
        pending.rebellions.push((spouse, 0));
        let mut regions = regions();
        regions[1].food_sufficiency = 0.0;
        let (result, recorder, stats) = consolidate_and_check(&pool, &regions,
            &[false, true, false, false], &[pending]);
        assert!(result[0].migrations.is_empty());
        assert_eq!(result[0].rebellions, vec![(spouse, 0)]);
        assert_eq!(stats.household_migrations_cancelled_rebellion, 1);
        assert_eq!(stats.household_migrations_cancelled_catastrophe, 0);
        assert_eq!(recorder.edits, vec![
            Edit::Cancelled { bucket: 0, migration: (pool.ids[lead], 0, 1),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                reason: MOVE_REASON_REBELLION, rejected_to: 1 },
            Edit::Blocked { bucket: 0, migration: (pool.ids[spouse], 0, 1),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                role: MOVE_ROLE_SPOUSE, reason: MOVE_REASON_REBELLION },
            Edit::Cancelled { bucket: 0, migration: (pool.ids[proposing_child], 0, 2),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                reason: MOVE_REASON_REBELLION, rejected_to: 1 },
            Edit::Blocked { bucket: 0, migration: (pool.ids[blocked_child], 0, 1),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                role: MOVE_ROLE_DEPENDENT, reason: MOVE_REASON_REBELLION },
        ]);
    }

    #[test]
    fn household_delivery_catastrophe_cancels_actual_proposals_without_inventing_child_proposals() {
        let mut pool = AgentPool::new(3);
        let lead = spawn(&mut pool, 25);
        let spouse = spawn(&mut pool, 25);
        let child = spawn(&mut pool, 10);
        marry(&mut pool, lead, spouse);
        pool.parent_id_0[child] = pool.ids[lead];
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(lead, 0, 1), (spouse, 0, 2)];
        let mut regions = regions();
        regions[1].food_sufficiency = 0.0;
        let (result, recorder, stats) = consolidate_and_check(&pool, &regions,
            &[false, true, false, false], &[pending]);
        assert!(result[0].migrations.is_empty());
        assert_eq!(stats.household_migrations_cancelled_catastrophe, 1);
        assert_eq!(recorder.edits, vec![
            Edit::Cancelled { bucket: 0, migration: (pool.ids[lead], 0, 1),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                reason: MOVE_REASON_CATASTROPHE, rejected_to: 1 },
            Edit::Cancelled { bucket: 0, migration: (pool.ids[spouse], 0, 2),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                reason: MOVE_REASON_CATASTROPHE, rejected_to: 1 },
            Edit::Blocked { bucket: 0, migration: (pool.ids[child], 0, 1),
                lead_id: pool.ids[lead], trailing_id: pool.ids[spouse],
                role: MOVE_ROLE_DEPENDENT, reason: MOVE_REASON_CATASTROPHE },
        ]);
    }

    #[test]
    fn household_delivery_shared_dependent_records_successive_household_last_writes() {
        let mut pool = AgentPool::new(5);
        let first = spawn(&mut pool, 25);
        let first_spouse = spawn(&mut pool, 25);
        let second = spawn(&mut pool, 25);
        let second_spouse = spawn(&mut pool, 25);
        let child = spawn(&mut pool, 10);
        marry(&mut pool, first, first_spouse);
        marry(&mut pool, second, second_spouse);
        pool.parent_id_0[child] = pool.ids[first];
        pool.parent_id_1[child] = pool.ids[second];
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(first, 0, 1), (second, 0, 2)];
        pending.migration_dominant = vec![(first, 14), (second, 7)];
        let (result, recorder, stats) = consolidate_and_check(&pool, &regions(), &[false; 4], &[pending]);
        let child_edits: Vec<_> = recorder.edits.iter().filter(|edit| match edit {
            Edit::Replacement { migration, .. } | Edit::Follower { migration, .. } => migration.0 == pool.ids[child],
            _ => false,
        }).collect();
        assert_eq!(child_edits, vec![
            &Edit::Follower { bucket: 0, migration: (pool.ids[child], 0, 1),
                lead_id: pool.ids[first], role: MOVE_ROLE_DEPENDENT,
                removed_count: 0, last_removed: None },
            &Edit::Replacement { bucket: 0, migration: (pool.ids[child], 0, 1),
                lead_id: pool.ids[second], role: MOVE_ROLE_DEPENDENT },
            &Edit::Follower { bucket: 0, migration: (pool.ids[child], 0, 2),
                lead_id: pool.ids[second], role: MOVE_ROLE_DEPENDENT,
                removed_count: 1, last_removed: Some((0, 1)) },
        ]);
        assert_eq!(result[0].migrations.iter().filter(|m| m.0 == child).copied().collect::<Vec<_>>(), vec![(child, 0, 2)]);
        assert_eq!(result[0].migration_driver_of(child), 7);
        assert_eq!(stats.household_migrations_follow, 4, "writes include both proposals for the shared child");
        assert_eq!(stats.household_dependent_overrides, 2);
    }

    #[test]
    fn household_delivery_dedup_reports_only_discarded_earlier_tuple() {
        let mut pool = AgentPool::new(3);
        let lead = spawn(&mut pool, 25);
        let spouse = spawn(&mut pool, 25);
        let loner = spawn(&mut pool, 25);
        marry(&mut pool, lead, spouse);
        let mut pending = PendingDecisions::new();
        pending.migrations = vec![(lead, 0, 1), (loner, 0, 1), (loner, 0, 2)];
        let (result, recorder, _) = consolidate_and_check(&pool, &regions(), &[false; 4], &[pending]);
        let discarded: Vec<_> = recorder.edits.iter().filter(|edit| matches!(edit, Edit::Dedup { .. })).collect();
        assert_eq!(discarded, vec![&Edit::Dedup { bucket: 0, migration: (pool.ids[loner], 0, 1) }]);
        assert_eq!(result[0].migrations.iter().filter(|m| m.0 == loner).copied().collect::<Vec<_>>(), vec![(loner, 0, 2)]);
    }
}
