//! M50a Relationship Substrate: Integration tests for apply_relationship_ops behaviours.
//!
//! AgentSimulator::apply_relationship_ops dispatches to the public `relationships`
//! module helpers (upsert_directed, upsert_symmetric, remove_directed).  Since the
//! AgentSimulator type itself is not publicly re-exported (cdylib constraint), these
//! tests verify the same invariants through the public `relationships` API directly.
//!
//! The ffi.rs #[cfg(test)] module contains matching unit tests using AgentSimulator
//! and PyRecordBatch that exercise the full FFI dispatch path; those run when Python
//! is available on the system PATH.

use chronicler_agents::{AgentPool, Occupation};
use chronicler_agents::relationships::{
    upsert_directed, upsert_symmetric, remove_directed,
    find_relationship, read_rel,
    BondType, REL_SLOTS, EMPTY_BOND_TYPE,
};

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

fn make_pool_with_agents(n: usize) -> (AgentPool, Vec<usize>) {
    let mut pool = AgentPool::new(n * 2);
    let mut slots = Vec::new();
    for i in 0..n {
        let slot = pool.spawn(
            i as u16, // region
            0,        // civ_affinity
            Occupation::Farmer,
            20,       // age
            0.0, 0.0, 0.0,
            0, 0, 0,
            chronicler_agents::BELIEF_NONE,
        );
        slots.push(slot);
    }
    (pool, slots)
}

// ---------------------------------------------------------------------------
// Test 1: UpsertDirected round-trip
// ---------------------------------------------------------------------------

#[test]
fn test_upsert_directed_round_trip() {
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let id_b = pool.ids[slots[1]];

    // Equivalent to op=0 UpsertDirected Friend(6) sentiment=50 formed_turn=10
    assert!(upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10));

    let rels_count = pool.rel_count[a] as usize;
    assert_eq!(rels_count, 1);
    let (target, sent, bt, ft) = read_rel(&pool, a, 0);
    assert_eq!(target, id_b);
    assert_eq!(sent, 50);
    assert_eq!(bt, BondType::Friend as u8);
    assert_eq!(ft, 10);
}

// ---------------------------------------------------------------------------
// Test 2: Batch ordering — Upsert → Remove → Upsert on same bond
// ---------------------------------------------------------------------------

#[test]
fn test_upsert_remove_upsert_ordering() {
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let id_b = pool.ids[slots[1]];

    // Step 1: upsert
    upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 30, 5);
    assert_eq!(pool.rel_count[a], 1);

    // Step 2: remove
    assert!(remove_directed(&mut pool, a, id_b, BondType::Friend as u8));
    assert_eq!(pool.rel_count[a], 0);
    assert_eq!(pool.rel_bond_types[a][0], EMPTY_BOND_TYPE);

    // Step 3: re-upsert — new bond, new formed_turn
    upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 70, 15);
    assert_eq!(pool.rel_count[a], 1);
    let (_, sent, _, ft) = read_rel(&pool, a, 0);
    assert_eq!(sent, 70);
    assert_eq!(ft, 15);
}

// ---------------------------------------------------------------------------
// Test 3: Unknown bond_type (>7) — BondType::from_u8 returns None → skip
// ---------------------------------------------------------------------------

#[test]
fn test_unknown_bond_type_not_stored() {
    // Simulates the apply_relationship_ops guard:
    // let bt = match BondType::from_u8(bt_raw) { Some(b) => b, None => continue };
    assert!(BondType::from_u8(99).is_none(), "bond_type 99 must be invalid");
    assert!(BondType::from_u8(8).is_none(),  "bond_type 8 must be invalid");
    assert!(BondType::from_u8(255).is_none(), "bond_type 255 must be invalid");

    // Directly verifying that no write happens for an unknown type
    // (applying the same guard logic manually):
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let id_b = pool.ids[slots[1]];
    let bt_raw: u8 = 99;
    if BondType::from_u8(bt_raw).is_some() {
        upsert_directed(&mut pool, a, id_b, bt_raw, 50, 10);
    }
    assert_eq!(pool.rel_count[a], 0, "unknown bond_type must not be stored");
}

// ---------------------------------------------------------------------------
// Test 4: RemoveDirected with dead target succeeds (source must be alive)
// ---------------------------------------------------------------------------

#[test]
fn test_remove_directed_dead_target() {
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let b = slots[1];
    let id_b = pool.ids[b];

    // Form bond a→b
    upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 40, 5);
    assert_eq!(pool.rel_count[a], 1);

    // Kill agent b
    pool.alive[b] = false;

    // RemoveDirected — source alive, target dead
    // The remove_directed function only needs the target_id (u32), not alive status.
    let removed = remove_directed(&mut pool, a, id_b, BondType::Friend as u8);
    assert!(removed, "bond must be removable even when target is dead");
    assert_eq!(pool.rel_count[a], 0);
}

// ---------------------------------------------------------------------------
// Test 5: RemoveSymmetric with one dead endpoint removes the live side
// ---------------------------------------------------------------------------

#[test]
fn test_remove_symmetric_one_dead_endpoint() {
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let b = slots[1];
    let id_a = pool.ids[a];
    let id_b = pool.ids[b];

    // Form symmetric Rival bond
    assert!(upsert_symmetric(&mut pool, a, b, BondType::Rival as u8, -30, 8));
    assert_eq!(pool.rel_count[a], 1);
    assert_eq!(pool.rel_count[b], 1);

    // Kill agent b
    pool.alive[b] = false;

    // Simulate RemoveSymmetric (op=3) logic from apply_relationship_ops:
    // Remove from live side (a); skip dead side (b already not alive).
    if pool.alive[a] {
        remove_directed(&mut pool, a, id_b, BondType::Rival as u8);
    }
    // Dead side: b is not alive, so we skip (matching the `if self.pool.alive[slot_b]` guard)

    assert_eq!(pool.rel_count[a], 0, "live side bond must be removed");
    // b is dead — its rel_count doesn't matter, but verify it was set when alive
    // (we can't call get_agent_relationships on dead agents meaningfully)
    assert!(!pool.alive[b], "b remains dead");

    // Also verify the id_a side: if we had tried to remove b's bond to id_a,
    // b is dead so we correctly skip. If we had done it anyway:
    // remove_directed on a dead slot is still safe (it just won't find the entry).
    // Let's verify that explicitly:
    let _ = remove_directed(&mut pool, b, id_a, BondType::Rival as u8); // no panic
}

// ---------------------------------------------------------------------------
// Test 6: get_agent_relationships returns all bond types
// ---------------------------------------------------------------------------

#[test]
fn test_all_bond_types_stored_and_readable() {
    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let id_b = pool.ids[slots[1]];

    // Directed bonds for all valid bond types (0-7)
    let bond_types = [
        BondType::Mentor as u8,       // 0, asymmetric
        BondType::Rival as u8,        // 1
        BondType::Marriage as u8,     // 2
        BondType::ExileBond as u8,    // 3
        BondType::CoReligionist as u8,// 4
        BondType::Kin as u8,          // 5
        BondType::Friend as u8,       // 6
        BondType::Grudge as u8,       // 7
    ];

    assert_eq!(bond_types.len(), REL_SLOTS, "8 bond types fill exactly 8 slots");

    for (i, &bt) in bond_types.iter().enumerate() {
        upsert_directed(&mut pool, a, id_b, bt, (i as i8) * 10, i as u16);
    }

    assert_eq!(pool.rel_count[a] as usize, REL_SLOTS, "all 8 slots must be filled");

    // Verify every bond type is findable
    for &bt in &bond_types {
        assert!(
            find_relationship(&pool, a, id_b, bt).is_some(),
            "bond_type {} must be present", bt
        );
    }
}

// ---------------------------------------------------------------------------
// Test 7: UpsertSymmetric rejected for asymmetric bond type (Mentor)
// ---------------------------------------------------------------------------

#[test]
fn test_upsert_symmetric_rejects_asymmetric_type() {
    use chronicler_agents::relationships::is_asymmetric;

    let (mut pool, slots) = make_pool_with_agents(2);
    let a = slots[0];
    let b = slots[1];

    // Simulate the apply_relationship_ops op=1 guard:
    // if is_asymmetric(bt_raw) { continue; }
    let bt_raw = BondType::Mentor as u8;
    if !is_asymmetric(bt_raw) {
        upsert_symmetric(&mut pool, a, b, bt_raw, 60, 1);
    }

    assert_eq!(pool.rel_count[a], 0, "Mentor (asymmetric) must not be upserted symmetrically");
    assert_eq!(pool.rel_count[b], 0, "neither side written");
}
