// Test-only kernel frozen from 2dd47347; intentionally retains vector rescans.
// Eligibility helpers are unchanged and shared with the production kernel.
use super::*;

pub(super) fn consolidate_household_migrations_reference<L: crate::pool::SlotLookup>(
    pool: &AgentPool,
    pending_decisions: &mut [PendingDecisions],
    regions: &[RegionState],
    contested_regions: &[bool],
    id_to_slot: &L,
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

            // Migration budget: followers count under the lead's largest term
            // (`migration_dominant` is in slot order: the region's slots are).
            let lead_term = bucket
                .migration_dominant
                .binary_search_by_key(&lead_slot, |&(s, _)| s)
                .map_or(crate::migration_drivers::MIGRATION_TERMS as u8, |i| bucket.migration_dominant[i].1);

            // APPROVED: trailing spouse follows
            // Remove trailing's existing migration (if different destination)
            bucket.migrations.retain(|m| m.0 != trailing_slot);
            bucket.migrations.push((trailing_slot, lead_from, lead_to));
            bucket.migration_followers.push((trailing_slot, lead_term));
            // Remove trailing from rebellion/switch (primary action replaced)
            bucket.rebellions.retain(|&(s, _)| s != trailing_slot);
            bucket.occupation_switches.retain(|&(s, _)| s != trailing_slot);
            stats.household_migrations_follow += 1;
            stats.migration_drivers.record_follower(lead_term);

            // APPROVED: dependents follow
            for &dep in &dep_slots {
                bucket.migrations.retain(|m| m.0 != dep);
                bucket.migrations.push((dep, lead_from, lead_to));
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
            }
        }
        deduped.reverse();
        bucket.migrations = deduped;
    }
}
