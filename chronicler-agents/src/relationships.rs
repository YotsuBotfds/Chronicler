/// M50a Relationship Substrate
/// Per-agent relationship store: BondType enum and classification helpers.

use std::collections::HashMap;

/// Bond types. Values 0-4 match M40 RelationshipType for zero-translation compatibility.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BondType {
    // --- Values 0-4 match M40 RelationshipType ---
    Mentor        = 0,   // asymmetric (src = mentor, dst = apprentice)
    Rival         = 1,
    Marriage      = 2,   // reserved, not used until M57
    ExileBond     = 3,
    CoReligionist = 4,
    // --- New types with no M40 equivalent ---
    Kin           = 5,
    Friend        = 6,
    Grudge        = 7,
}

impl BondType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Mentor),
            1 => Some(Self::Rival),
            2 => Some(Self::Marriage),
            3 => Some(Self::ExileBond),
            4 => Some(Self::CoReligionist),
            5 => Some(Self::Kin),
            6 => Some(Self::Friend),
            7 => Some(Self::Grudge),
            _ => None,
        }
    }
}

pub const REL_SLOTS: usize = 8;
pub const EMPTY_TARGET: u32 = 0;
pub const EMPTY_BOND_TYPE: u8 = 255;

/// Kin bonds are eviction-protected. Marriage joins in M57.
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8 || bond_type == BondType::Marriage as u8
}

/// Positive-valence bonds strengthen when co-located.
/// Negative-valence bonds (Rival, Grudge) deepen when co-located.
pub fn is_positive_valence(bond_type: u8) -> bool {
    matches!(bond_type, 0 | 2 | 3 | 4 | 5 | 6)
}

/// Only Mentor is asymmetric (single directed entry, src=mentor dst=apprentice).
pub fn is_asymmetric(bond_type: u8) -> bool {
    bond_type == BondType::Mentor as u8
}

pub fn is_symmetric(bond_type: u8) -> bool {
    !is_asymmetric(bond_type)
}

/// Find the target ID of an agent's Marriage bond.
/// Returns None if the agent has no active Marriage bond.
/// In debug builds, asserts at most one Marriage bond exists.
pub fn get_spouse_id(pool: &AgentPool, slot: usize) -> Option<u32> {
    let count = pool.rel_count[slot] as usize;
    let mut found: Option<u32> = None;
    for i in 0..count {
        if pool.rel_bond_types[slot][i] == BondType::Marriage as u8 {
            let target = pool.rel_target_ids[slot][i];
            debug_assert!(found.is_none(), "agent has multiple Marriage bonds (slot={})", slot);
            if found.is_some() {
                // Release fallback: return first found
                return found;
            }
            found = Some(target);
        }
    }
    found
}

// ---------------------------------------------------------------------------
// Task 3: Slot helpers
// ---------------------------------------------------------------------------

use crate::pool::AgentPool;

/// Find a relationship slot by compound key (target_id, bond_type).
pub fn find_relationship(pool: &AgentPool, slot: usize, target_id: u32, bond_type: u8) -> Option<usize> {
    let count = pool.rel_count[slot] as usize;
    for i in 0..count {
        if pool.rel_target_ids[slot][i] == target_id && pool.rel_bond_types[slot][i] == bond_type {
            return Some(i);
        }
    }
    None
}

/// Read one relationship slot. Returns (target_id, sentiment, bond_type, formed_turn).
pub fn read_rel(pool: &AgentPool, slot: usize, rel_idx: usize) -> (u32, i8, u8, u16) {
    (
        pool.rel_target_ids[slot][rel_idx],
        pool.rel_sentiments[slot][rel_idx],
        pool.rel_bond_types[slot][rel_idx],
        pool.rel_formed_turns[slot][rel_idx],
    )
}

/// Write one relationship slot.
pub fn write_rel(
    pool: &mut AgentPool, slot: usize, rel_idx: usize,
    target_id: u32, sentiment: i8, bond_type: u8, formed_turn: u16,
) {
    pool.rel_target_ids[slot][rel_idx] = target_id;
    pool.rel_sentiments[slot][rel_idx] = sentiment;
    pool.rel_bond_types[slot][rel_idx] = bond_type;
    pool.rel_formed_turns[slot][rel_idx] = formed_turn;
}

fn clear_slot(pool: &mut AgentPool, slot: usize, rel_idx: usize) {
    pool.rel_target_ids[slot][rel_idx] = EMPTY_TARGET;
    pool.rel_sentiments[slot][rel_idx] = 0;
    pool.rel_bond_types[slot][rel_idx] = EMPTY_BOND_TYPE;
    pool.rel_formed_turns[slot][rel_idx] = 0;
}

/// Swap-remove: move last occupied slot into the removed position, clear tail, decrement count.
pub fn swap_remove_rel(pool: &mut AgentPool, slot: usize, rel_idx: usize) {
    let count = pool.rel_count[slot] as usize;
    debug_assert!(rel_idx < count);
    let last = count - 1;
    if rel_idx != last {
        pool.rel_target_ids[slot][rel_idx] = pool.rel_target_ids[slot][last];
        pool.rel_sentiments[slot][rel_idx] = pool.rel_sentiments[slot][last];
        pool.rel_bond_types[slot][rel_idx] = pool.rel_bond_types[slot][last];
        pool.rel_formed_turns[slot][rel_idx] = pool.rel_formed_turns[slot][last];
    }
    clear_slot(pool, slot, last);
    pool.rel_count[slot] -= 1;
}

/// Find the weakest non-protected slot for eviction.
/// Tie-break: lowest slot index among equal-sentiment candidates.
pub fn find_evictable(pool: &AgentPool, slot: usize) -> Option<usize> {
    let count = pool.rel_count[slot] as usize;
    let mut best: Option<(usize, u8)> = None; // (rel_idx, abs_sentiment as u8)
    for i in 0..count {
        let bt = pool.rel_bond_types[slot][i];
        if is_protected(bt) {
            continue;
        }
        let abs_sent = pool.rel_sentiments[slot][i].unsigned_abs(); // u8
        match best {
            None => best = Some((i, abs_sent)),
            Some((_, best_abs)) if abs_sent < best_abs => {
                best = Some((i, abs_sent));
            }
            _ => {} // tie-break: keep lower index (already stored)
        }
    }
    best.map(|(idx, _)| idx)
}

// ---------------------------------------------------------------------------
// Task 4: Upsert and remove operations
// ---------------------------------------------------------------------------

enum SlotResolution {
    ExistingSlot(usize),
    EmptySlot(usize),
    EvictSlot(usize),
    NoSlot,
}

fn resolve_slot(pool: &AgentPool, agent_slot: usize, target_id: u32, bond_type: u8) -> SlotResolution {
    if let Some(idx) = find_relationship(pool, agent_slot, target_id, bond_type) {
        return SlotResolution::ExistingSlot(idx);
    }
    let count = pool.rel_count[agent_slot] as usize;
    if count < REL_SLOTS {
        return SlotResolution::EmptySlot(count);
    }
    if let Some(idx) = find_evictable(pool, agent_slot) {
        return SlotResolution::EvictSlot(idx);
    }
    SlotResolution::NoSlot
}

/// Insert or update a directed bond. Returns true if written.
pub fn upsert_directed(
    pool: &mut AgentPool, src_slot: usize,
    target_id: u32, bond_type: u8, sentiment: i8, formed_turn: u16,
) -> bool {
    if pool.ids[src_slot] == target_id { return false; } // self-bond

    match resolve_slot(pool, src_slot, target_id, bond_type) {
        SlotResolution::ExistingSlot(idx) => {
            // Update sentiment only; preserve formed_turn
            pool.rel_sentiments[src_slot][idx] = sentiment;
            true
        }
        SlotResolution::EmptySlot(idx) => {
            write_rel(pool, src_slot, idx, target_id, sentiment, bond_type, formed_turn);
            pool.rel_count[src_slot] += 1;
            true
        }
        SlotResolution::EvictSlot(idx) => {
            // find_evictable guarantees the candidate is non-protected
            write_rel(pool, src_slot, idx, target_id, sentiment, bond_type, formed_turn);
            true
        }
        SlotResolution::NoSlot => false,
    }
}

/// Atomically insert a symmetric bond (both directions). Both succeed or neither.
pub fn upsert_symmetric(
    pool: &mut AgentPool, slot_a: usize, slot_b: usize,
    bond_type: u8, sentiment: i8, formed_turn: u16,
) -> bool {
    let id_a = pool.ids[slot_a];
    let id_b = pool.ids[slot_b];
    if id_a == id_b { return false; }

    let res_a = resolve_slot(pool, slot_a, id_b, bond_type);
    let res_b = resolve_slot(pool, slot_b, id_a, bond_type);

    let can_a = !matches!(res_a, SlotResolution::NoSlot);
    let can_b = !matches!(res_b, SlotResolution::NoSlot);
    if !can_a || !can_b { return false; }

    commit_resolved(pool, slot_a, id_b, bond_type, sentiment, formed_turn, res_a);
    commit_resolved(pool, slot_b, id_a, bond_type, sentiment, formed_turn, res_b);
    true
}

fn commit_resolved(
    pool: &mut AgentPool, slot: usize,
    target_id: u32, bond_type: u8, sentiment: i8, formed_turn: u16,
    resolution: SlotResolution,
) {
    match resolution {
        SlotResolution::ExistingSlot(idx) => {
            pool.rel_sentiments[slot][idx] = sentiment;
        }
        SlotResolution::EmptySlot(idx) => {
            write_rel(pool, slot, idx, target_id, sentiment, bond_type, formed_turn);
            pool.rel_count[slot] += 1;
        }
        SlotResolution::EvictSlot(idx) => {
            write_rel(pool, slot, idx, target_id, sentiment, bond_type, formed_turn);
        }
        SlotResolution::NoSlot => unreachable!("checked before commit"),
    }
}

/// Remove a directed bond. Returns true if found and removed.
pub fn remove_directed(pool: &mut AgentPool, src_slot: usize, target_id: u32, bond_type: u8) -> bool {
    if let Some(idx) = find_relationship(pool, src_slot, target_id, bond_type) {
        swap_remove_rel(pool, src_slot, idx);
        true
    } else {
        false
    }
}

/// Remove a symmetric bond (both directions independently).
pub fn remove_symmetric(pool: &mut AgentPool, slot_a: usize, slot_b: usize, bond_type: u8) {
    let id_a = pool.ids[slot_a];
    let id_b = pool.ids[slot_b];
    remove_directed(pool, slot_a, id_b, bond_type);
    remove_directed(pool, slot_b, id_a, bond_type);
}

// ---------------------------------------------------------------------------
// Task 7: Sentiment drift
// ---------------------------------------------------------------------------

/// Per-tick sentiment drift for all agents.
/// Phase 0.8: after needs (0.75), before satisfaction (1.0).
pub fn drift_relationships(pool: &mut AgentPool, turn: u32) {
    let turn_u16 = turn as u16;

    // Build id→slot lookup (alive agents only)
    let mut id_to_slot: HashMap<u32, usize> = HashMap::with_capacity(pool.capacity());
    for slot in 0..pool.capacity() {
        if pool.alive[slot] {
            id_to_slot.insert(pool.ids[slot], slot);
        }
    }

    for agent_slot in 0..pool.capacity() {
        if !pool.alive[agent_slot] { continue; }
        let count = pool.rel_count[agent_slot] as usize;
        let agent_region = pool.regions[agent_slot];

        for i in 0..count {
            let target_id = pool.rel_target_ids[agent_slot][i];
            let bond_type = pool.rel_bond_types[agent_slot][i];
            let mut sent = pool.rel_sentiments[agent_slot][i] as i16;

            // Dead/missing targets → not co-located (separation rules)
            let co_located = id_to_slot.get(&target_id)
                .map(|&ts| pool.alive[ts] && pool.regions[ts] == agent_region)
                .unwrap_or(false);

            let valence = is_positive_valence(bond_type);

            if co_located {
                if valence {
                    // Positive: strengthen toward +127, cadence-gated above threshold
                    if sent <= crate::agent::STRONG_TIE_THRESHOLD
                        || turn_u16 % crate::agent::STRONG_TIE_CADENCE == 0
                    {
                        sent = (sent + crate::agent::POSITIVE_COLOC_DRIFT).min(127);
                    }
                } else {
                    // Negative: deepen toward -128
                    sent = (sent - crate::agent::NEGATIVE_COLOC_DRIFT).max(-128);
                }
            } else {
                // Separated: decay toward 0
                if sent > 0 {
                    sent = (sent - crate::agent::POSITIVE_SEPARATION_DECAY).max(0);
                } else if sent < 0 {
                    // Negative decays slower (cadence-gated)
                    if turn_u16 % crate::agent::NEGATIVE_DECAY_CADENCE == 0 {
                        sent = (sent + 1).min(0);
                    }
                }
            }

            pool.rel_sentiments[agent_slot][i] = sent as i8;
        }
    }
}

/// Form a kin bond between parent and child at birth.
/// Atomic pair-write: both succeed or neither.
/// `turn` is u32 from the tick entrypoint; truncated to u16 for storage.
pub fn form_kin_bond(pool: &mut AgentPool, parent_slot: usize, child_slot: usize, turn: u32) -> bool {
    let turn = turn as u16;
    let parent_id = pool.ids[parent_slot];
    let child_id = pool.ids[child_slot];
    if parent_id == child_id { return false; }

    let bond_type = BondType::Kin as u8;

    // Resolve both sides before committing (atomic)
    let res_parent = resolve_slot(pool, parent_slot, child_id, bond_type);
    let res_child = resolve_slot(pool, child_slot, parent_id, bond_type);

    let can_parent = !matches!(res_parent, SlotResolution::NoSlot);
    let can_child = !matches!(res_child, SlotResolution::NoSlot);
    if !can_parent || !can_child { return false; }

    commit_resolved(pool, parent_slot, child_id, bond_type,
                    crate::agent::KIN_INITIAL_PARENT, turn, res_parent);
    commit_resolved(pool, child_slot, parent_id, bond_type,
                    crate::agent::KIN_INITIAL_CHILD, turn, res_child);
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::pool::AgentPool;

    // Helper to create a pool and spawn agents for testing
    fn setup_pool(n: usize) -> (AgentPool, Vec<usize>) {
        let mut pool = AgentPool::new(n * 2);
        let mut slots = Vec::new();
        for i in 0..n {
            let slot = pool.spawn(
                i as u16,  // region
                0,         // civ_affinity
                Occupation::Farmer,
                20,        // age
                0.0, 0.0, 0.0,  // boldness, ambition, loyalty_trait
                0, 0, 0,   // cultural_value_0, cultural_value_1, cultural_value_2
                0,          // belief
            );
            slots.push(slot);
        }
        (pool, slots)
    }

    #[test]
    fn test_bond_type_from_u8() {
        assert_eq!(BondType::from_u8(0), Some(BondType::Mentor));
        assert_eq!(BondType::from_u8(5), Some(BondType::Kin));
        assert_eq!(BondType::from_u8(7), Some(BondType::Grudge));
        assert_eq!(BondType::from_u8(8), None);
        assert_eq!(BondType::from_u8(255), None);
    }

    #[test]
    fn test_is_protected() {
        assert!(is_protected(BondType::Kin as u8));
        assert!(!is_protected(BondType::Mentor as u8));
        assert!(!is_protected(BondType::Rival as u8));
        assert!(!is_protected(BondType::Friend as u8));
    }

    #[test]
    fn test_valence() {
        assert!(is_positive_valence(BondType::Kin as u8));
        assert!(is_positive_valence(BondType::Mentor as u8));
        assert!(is_positive_valence(BondType::Friend as u8));
        assert!(is_positive_valence(BondType::CoReligionist as u8));
        assert!(is_positive_valence(BondType::Marriage as u8));
        assert!(is_positive_valence(BondType::ExileBond as u8));
        assert!(!is_positive_valence(BondType::Rival as u8));
        assert!(!is_positive_valence(BondType::Grudge as u8));
    }

    #[test]
    fn test_asymmetry() {
        assert!(is_asymmetric(BondType::Mentor as u8));
        assert!(!is_asymmetric(BondType::Kin as u8));
        assert!(!is_asymmetric(BondType::Rival as u8));
        assert!(is_symmetric(BondType::Kin as u8));
        assert!(is_symmetric(BondType::Rival as u8));
    }

    #[test]
    fn test_m40_value_compatibility() {
        assert_eq!(BondType::Mentor as u8, 0);
        assert_eq!(BondType::Rival as u8, 1);
        assert_eq!(BondType::Marriage as u8, 2);
        assert_eq!(BondType::ExileBond as u8, 3);
        assert_eq!(BondType::CoReligionist as u8, 4);
    }

    #[test]
    fn test_find_relationship() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        write_rel(&mut pool, a, 0, id_b, 50, BondType::Friend as u8, 10);
        pool.rel_count[a] = 1;
        assert_eq!(find_relationship(&pool, a, id_b, BondType::Friend as u8), Some(0));
        assert_eq!(find_relationship(&pool, a, id_b, BondType::Rival as u8), None);
        assert_eq!(find_relationship(&pool, a, 99, BondType::Friend as u8), None);
    }

    #[test]
    fn test_swap_remove_compaction() {
        let (mut pool, slots) = setup_pool(1);
        let a = slots[0];
        for i in 0..3u32 {
            write_rel(&mut pool, a, i as usize, 10 + i, (i as i8) * 10, BondType::Friend as u8, 1);
        }
        pool.rel_count[a] = 3;
        swap_remove_rel(&mut pool, a, 1);
        assert_eq!(pool.rel_count[a], 2);
        assert_eq!(pool.rel_target_ids[a][1], 12); // last moved to 1
        assert_eq!(pool.rel_bond_types[a][2], EMPTY_BOND_TYPE); // tail cleared
    }

    #[test]
    fn test_find_evictable_skips_protected() {
        let (mut pool, slots) = setup_pool(1);
        let a = slots[0];
        write_rel(&mut pool, a, 0, 100, 10, BondType::Kin as u8, 1);
        write_rel(&mut pool, a, 1, 101, 50, BondType::Friend as u8, 1);
        write_rel(&mut pool, a, 2, 102, -30, BondType::Rival as u8, 1);
        pool.rel_count[a] = 3;
        assert_eq!(find_evictable(&pool, a), Some(2)); // Rival abs(30) < Friend abs(50)
    }

    #[test]
    fn test_find_evictable_all_protected() {
        let (mut pool, slots) = setup_pool(1);
        let a = slots[0];
        for i in 0..8 {
            write_rel(&mut pool, a, i, (100 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[a] = 8;
        assert_eq!(find_evictable(&pool, a), None);
    }

    #[test]
    fn test_find_evictable_tiebreak_lowest_index() {
        let (mut pool, slots) = setup_pool(1);
        let a = slots[0];
        write_rel(&mut pool, a, 0, 100, 20, BondType::Friend as u8, 1);
        write_rel(&mut pool, a, 1, 101, 20, BondType::Friend as u8, 1);
        pool.rel_count[a] = 2;
        assert_eq!(find_evictable(&pool, a), Some(0));
    }

    #[test]
    fn test_upsert_directed_new_bond() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        assert!(upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10));
        assert_eq!(pool.rel_count[a], 1);
        let (tid, sent, bt, ft) = read_rel(&pool, a, 0);
        assert_eq!((tid, sent, bt, ft), (id_b, 50, BondType::Friend as u8, 10));
    }

    #[test]
    fn test_upsert_directed_preserves_formed_turn() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10);
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 80, 99);
        assert_eq!(pool.rel_sentiments[a][0], 80);
        assert_eq!(pool.rel_formed_turns[a][0], 10); // NOT 99
    }

    #[test]
    fn test_upsert_directed_self_bond_rejected() {
        let (mut pool, slots) = setup_pool(1);
        let a = slots[0];
        let id_a = pool.ids[a];
        assert!(!upsert_directed(&mut pool, a, id_a, BondType::Friend as u8, 50, 10));
        assert_eq!(pool.rel_count[a], 0);
    }

    #[test]
    fn test_upsert_symmetric_atomic_failure() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        for i in 0..8 {
            write_rel(&mut pool, a, i, (200 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[a] = 8;
        assert!(!upsert_symmetric(&mut pool, a, b, BondType::Friend as u8, 50, 10));
        assert_eq!(pool.rel_count[b], 0); // b not written either
    }

    #[test]
    fn test_remove_directed() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10);
        assert!(remove_directed(&mut pool, a, id_b, BondType::Friend as u8));
        assert_eq!(pool.rel_count[a], 0);
        assert_eq!(pool.rel_bond_types[a][0], EMPTY_BOND_TYPE);
    }

    #[test]
    fn test_multi_bond_pairs() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        upsert_directed(&mut pool, a, id_b, BondType::Rival as u8, -30, 5);
        upsert_directed(&mut pool, a, id_b, BondType::CoReligionist as u8, 40, 8);
        assert_eq!(pool.rel_count[a], 2);
        assert!(find_relationship(&pool, a, id_b, BondType::Rival as u8).is_some());
        assert!(find_relationship(&pool, a, id_b, BondType::CoReligionist as u8).is_some());
    }

    #[test]
    fn test_form_kin_bond() {
        let (mut pool, slots) = setup_pool(2);
        let parent = slots[0];
        let child = slots[1];
        assert!(form_kin_bond(&mut pool, parent, child, 50));
        // Parent has kin bond to child
        assert_eq!(pool.rel_count[parent], 1);
        let (tid, sent, bt, _) = read_rel(&pool, parent, 0);
        assert_eq!(tid, pool.ids[child]);
        assert_eq!(sent, crate::agent::KIN_INITIAL_PARENT);
        assert_eq!(bt, BondType::Kin as u8);
        // Child has kin bond to parent
        assert_eq!(pool.rel_count[child], 1);
        let (tid, sent, bt, _) = read_rel(&pool, child, 0);
        assert_eq!(tid, pool.ids[parent]);
        assert_eq!(sent, crate::agent::KIN_INITIAL_CHILD);
        assert_eq!(bt, BondType::Kin as u8);
    }

    #[test]
    fn test_form_kin_bond_atomic_failure() {
        let (mut pool, slots) = setup_pool(2);
        let parent = slots[0];
        let child = slots[1];
        // Fill parent with 8 kin bonds
        for i in 0..8 {
            write_rel(&mut pool, parent, i, (200 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[parent] = 8;
        assert!(!form_kin_bond(&mut pool, parent, child, 50));
        assert_eq!(pool.rel_count[child], 0); // child not written either
    }

    #[test]
    fn test_swap_remove_then_evict() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let _id_b = pool.ids[slots[1]];
        // Fill 8 non-protected bonds with varying sentiments
        for i in 0..8u32 {
            write_rel(&mut pool, a, i as usize, 100 + i, (10 + i) as i8, BondType::Friend as u8, 1);
        }
        pool.rel_count[a] = 8;
        // Remove slot 0 (sentiment 10). Last slot (7, sentiment 17) moves to 0.
        swap_remove_rel(&mut pool, a, 0);
        // Now slot 0 has sentiment 17, slots 1-6 have 11-16
        // Evict should pick slot 1 (sentiment 11, the new weakest at lowest index)
        assert_eq!(find_evictable(&pool, a), Some(1));
    }

    #[test]
    fn test_drift_positive_colocation_strengthens() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        // Put both in region 0
        pool.regions[b] = 0;
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 51);
    }

    #[test]
    fn test_drift_negative_colocation_deepens() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        pool.regions[b] = 0; // same region as a
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Rival as u8, -50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], -51);
    }

    #[test]
    fn test_drift_separation_positive_decays() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        // setup_pool assigns different regions (0 and 1)
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 49);
    }

    #[test]
    fn test_drift_separation_negative_slow_decay() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Grudge as u8, -50, 1);
        // Turn 1: not on cadence (NEGATIVE_DECAY_CADENCE=4)
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], -50);
        // Turn 4: on cadence (4 % 4 == 0)
        drift_relationships(&mut pool, 4);
        assert_eq!(pool.rel_sentiments[a][0], -49);
    }

    #[test]
    fn test_drift_dead_target_uses_separation_rules() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        pool.regions[b] = 0; // same region initially
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        pool.alive[b] = false; // kill target
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 49); // separation decay, not co-located
    }

    #[test]
    fn test_drift_strong_tie_cadence() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        pool.regions[b] = 0; // same region
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Kin as u8, 105, 1);
        // Turn 1: above threshold (100), not on cadence (STRONG_TIE_CADENCE=2, 1%2!=0)
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 105); // no drift
        // Turn 2: on cadence (2%2==0)
        drift_relationships(&mut pool, 2);
        assert_eq!(pool.rel_sentiments[a][0], 106);
    }

    #[test]
    fn test_marriage_is_protected() {
        assert!(is_protected(BondType::Marriage as u8));
        assert!(is_protected(BondType::Kin as u8));
        assert!(!is_protected(BondType::Friend as u8));
        assert!(!is_protected(BondType::Rival as u8));
    }

    #[test]
    fn test_get_spouse_id_none() {
        let (pool, slots) = setup_pool(1);
        assert_eq!(get_spouse_id(&pool, slots[0]), None);
    }

    #[test]
    fn test_get_spouse_id_found() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        upsert_symmetric(&mut pool, a, slots[1], BondType::Marriage as u8, 50, 10);
        assert_eq!(get_spouse_id(&pool, a), Some(id_b));
    }

    #[test]
    fn test_drift_saturating_math() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let b = slots[1];
        pool.regions[b] = 0;
        let id_b = pool.ids[b];
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 127, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 127); // clamped, not overflow
    }
}
