//! Adversarial physical-migration invariants; imported only by tick's cfg(test).
//! Reason codes remain honest diagnostics and never change physical application.
use super::*;
use crate::agent::{BELIEF_NONE, Occupation};
use crate::behavior::PendingDecisions;
use crate::decision_delivery::NoDelivery;
use crate::household::{consolidate_household_migrations, HouseholdStats};
use crate::migration_drivers::TERM_MATERIAL_NEED;
use crate::relationships::{upsert_symmetric, BondType};

fn spawn(pool: &mut AgentPool, age: u16) -> usize {
    pool.spawn(0, 0, Occupation::Farmer, age, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE)
}

fn copy_pool(pool: &AgentPool) -> AgentPool {
    crate::persist::decode(crate::persist::KIND_AGENT,
        &crate::persist::encode(crate::persist::KIND_AGENT, pool)).unwrap()
}

fn physical_move(pool: &mut AgentPool, slot: usize, from: u16, to: u16,
                 turn: u32, driver: u8) -> Vec<AgentEvent> {
    let mut pending = PendingDecisions::new();
    pending.migrations.push((slot, from, to));
    pending.migration_dominant.push((slot, driver));
    let mut events = Vec::new();
    apply_migrations_observed(pool, &pending, turn, 0, &mut events, &mut NoDelivery);
    events
}

#[test]
fn reason_known_or_unknown_does_not_change_physical_move_return_or_checkpoint_state() {
    let mut known = AgentPool::new(2);
    let slot = spawn(&mut known, 30);
    let mut unknown = copy_pool(&known);
    for (turn, from, to) in [(2, 0, 1), (3, 1, 2), (4, 2, 0)] {
        let a = physical_move(&mut known, slot, from, to, turn, TERM_MATERIAL_NEED as u8);
        let b = physical_move(&mut unknown, slot, from, to, turn, NO_MIGRATION_DRIVER);
        assert_eq!(a.len(), 1);
        assert_eq!(b.len(), 1);
        assert_eq!((a[0].agent_id, a[0].region, a[0].target_region, a[0].turn),
                   (b[0].agent_id, b[0].region, b[0].target_region, b[0].turn));
        assert_eq!(a[0].migration_driver, TERM_MATERIAL_NEED as u8);
        assert_eq!(b[0].migration_driver, NO_MIGRATION_DRIVER);
        assert_eq!(known.regions[slot], to);
        assert_eq!(known.displacement_turns[slot], 5);
        // All authoritative persisted native state is equal. The intentionally
        // distinct event annotation must not alter even unrelated pool fields.
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &known),
                   crate::persist::encode(crate::persist::KIND_AGENT, &unknown));
        known = copy_pool(&known);
        unknown = copy_pool(&unknown);
    }
}

#[test]
fn household_followers_retain_unknown_reason_without_losing_physical_move() {
    let mut pool = AgentPool::new(3);
    let lead = spawn(&mut pool, 30);
    let spouse = spawn(&mut pool, 29);
    let child = spawn(&mut pool, 8);
    assert!(upsert_symmetric(&mut pool, lead, spouse, BondType::Marriage as u8, 50, 1));
    pool.parent_id_0[child] = pool.ids[lead];
    pool.parent_id_1[child] = pool.ids[spouse];
    let mut pending = PendingDecisions::new();
    pending.migrations.push((lead, 0, 1));
    pending.migration_dominant.push((lead, NO_MIGRATION_DRIVER));
    let mut buckets = vec![pending];
    let mut regions: Vec<RegionState> = (0..2).map(RegionState::new).collect();
    for region in &mut regions {
        region.controller_civ = 0;
        region.food_sufficiency = 1.0;
    }
    let lookup = pool.build_id_slots();
    let mut stats = HouseholdStats::default();
    consolidate_household_migrations(&pool, &mut buckets, &regions, &[false; 2], &lookup, &mut stats);
    assert_eq!(buckets[0].migrations.len(), 3);
    assert_eq!(stats.household_migrations_follow, 2);
    let mut events = Vec::new();
    apply_migrations_observed(&mut pool, &buckets[0], 2, 0, &mut events, &mut NoDelivery);
    let ids: std::collections::HashSet<_> = events.iter().map(|e| e.agent_id).collect();
    assert_eq!(ids.len(), 3);
    for slot in [lead, spouse, child] {
        assert_eq!(pool.regions[slot], 1);
        assert_eq!(pool.displacement_turns[slot], 5);
        assert!(events.iter().any(|e| e.agent_id == pool.ids[slot] && e.migration_driver == NO_MIGRATION_DRIVER));
    }
}

#[test]
fn death_and_slot_reuse_clear_physical_recent_mover_state_and_change_identity() {
    let mut pool = AgentPool::new(1);
    let old = spawn(&mut pool, 30);
    let old_id = pool.ids[old];
    physical_move(&mut pool, old, 0, 1, 2, NO_MIGRATION_DRIVER);
    assert_eq!(pool.displacement_turns[old], 5);
    pool.kill(old);
    assert!(!pool.is_alive(old));
    assert_eq!(pool.displacement_turns[old], 0);
    let fresh = spawn(&mut pool, 0);
    assert_eq!(fresh, old);
    assert_ne!(pool.ids[fresh], old_id);
    assert_eq!(pool.regions[fresh], 0);
    assert_eq!(pool.displacement_turns[fresh], 0);
    assert_eq!(pool.life_events[fresh], 0);
    let restored = copy_pool(&pool);
    assert_eq!(restored.ids[fresh], pool.ids[fresh]);
    assert_eq!(restored.displacement_turns[fresh], 0);
}
