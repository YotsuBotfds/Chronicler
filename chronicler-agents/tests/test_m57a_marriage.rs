//! M57a Marriage Formation & Lineage: Integration tests.
//!
//! Tests verify determinism, exclusivity, age/distance gates, incest blocking,
//! scored greedy matching, cadence scheduling, dual-parent FFI round-trip,
//! and remarriage after spouse death.

use chronicler_agents::{
    AgentPool, Occupation, RegionState,
    CivSignals, TickSignals,
};
use chronicler_agents::formation::marriage_scan;
use chronicler_agents::relationships::{
    get_spouse_id, upsert_symmetric, BondType,
};

use arrow::array::UInt32Array;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Spawn an agent with full control over region, civ, occupation, age,
/// cultural values, and belief. Uses fixed boldness/loyalty_trait.
fn spawn(
    pool: &mut AgentPool,
    region: u16,
    civ: u8,
    occ: Occupation,
    age: u16,
    cv0: u8,
    cv1: u8,
    cv2: u8,
    belief: u8,
) -> usize {
    pool.spawn(region, civ, occ, age, 0.5, 0.5, 0.5, cv0, cv1, cv2, belief)
}

/// Build alive_slots list from pool.
fn alive_slots(pool: &AgentPool) -> Vec<usize> {
    (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect()
}

/// Build a minimal TickSignals with no wars.
fn peaceful_signals() -> TickSignals {
    TickSignals {
        civs: vec![],
        contested_regions: vec![],
    }
}

/// Build TickSignals with civ 0 at war.
fn war_signals() -> TickSignals {
    TickSignals {
        civs: vec![CivSignals {
            civ_id: 0,
            stability: 50,
            is_at_war: true,
            dominant_faction: 0,
            faction_military: 0.33,
            faction_merchant: 0.33,
            faction_cultural: 0.34,
            faction_clergy: 0.0,
            shock_stability: 0.0,
            shock_economy: 0.0,
            shock_military: 0.0,
            shock_culture: 0.0,
            demand_shift_farmer: 0.0,
            demand_shift_soldier: 0.0,
            demand_shift_merchant: 0.0,
            demand_shift_scholar: 0.0,
            demand_shift_priest: 0.0,
            mean_boldness: 0.0,
            mean_ambition: 0.0,
            mean_loyalty_trait: 0.0,
            gini_coefficient: 0.0,
            conquered_this_turn: false,
            priest_tithe_share: 0.0,
            cultural_drift_multiplier: 1.0,
            religion_intensity_multiplier: 1.0,
        }],
        contested_regions: vec![],
    }
}

/// Place two agents close together spatially (within MARRIAGE_RADIUS).
fn place_close(pool: &mut AgentPool, a: usize, b: usize) {
    pool.x[a] = 0.5;
    pool.y[a] = 0.5;
    pool.x[b] = 0.51;
    pool.y[b] = 0.51;
}

/// Place two agents far apart spatially (beyond MARRIAGE_RADIUS).
fn place_far(pool: &mut AgentPool, a: usize, b: usize) {
    pool.x[a] = 0.0;
    pool.y[a] = 0.0;
    pool.x[b] = 0.9;
    pool.y[b] = 0.9;
}

// ---------------------------------------------------------------------------
// Test 1: Determinism — identical pool state produces identical results
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_determinism() {
    fn run_scan() -> Vec<(u32, Option<u32>)> {
        let mut pool = AgentPool::new(16);
        let mut regions = vec![RegionState::new(0)];
        regions[0].controller_civ = 0;
        let signals = peaceful_signals();

        // Spawn 4 eligible agents, same region, close together
        let mut slots = Vec::new();
        for _ in 0..4 {
            let s = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
            slots.push(s);
        }
        // Place all close together
        for &s in &slots {
            pool.x[s] = 0.5;
            pool.y[s] = 0.5;
        }

        let alive = alive_slots(&pool);
        marriage_scan(&mut pool, &regions, &signals, 0, &alive);

        // Collect (agent_id, spouse_id) for all agents, sorted by agent_id
        let mut result: Vec<(u32, Option<u32>)> = slots.iter()
            .map(|&s| (pool.ids[s], get_spouse_id(&pool, s)))
            .collect();
        result.sort_by_key(|&(id, _)| id);
        result
    }

    let r1 = run_scan();
    let r2 = run_scan();
    assert_eq!(r1, r2, "identical inputs must produce identical marriage results");
    // At least some marriages should have formed
    assert!(r1.iter().any(|(_, spouse)| spouse.is_some()), "should form at least one marriage");
}

// ---------------------------------------------------------------------------
// Test 2: Exclusivity — no agent has two Marriage bonds; already-married
//         agents are not re-matched
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_exclusivity_no_double_marriage() {
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Spawn 6 agents, all eligible, all close
    let mut slots = Vec::new();
    for _ in 0..6 {
        let s = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
        pool.x[s] = 0.5;
        pool.y[s] = 0.5;
        slots.push(s);
    }

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);
    assert!(stats.marriages_formed >= 1, "should form at least 1 marriage");

    // Verify: no agent has more than one Marriage bond
    for &s in &slots {
        let count = pool.rel_count[s] as usize;
        let marriage_bonds: usize = (0..count)
            .filter(|&i| pool.rel_bond_types[s][i] == BondType::Marriage as u8)
            .count();
        assert!(marriage_bonds <= 1, "agent {} has {} Marriage bonds", pool.ids[s], marriage_bonds);
    }
}

#[test]
fn test_marriage_already_married_not_rematched() {
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Pre-marry agents a and b
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);
    pool.x[c] = 0.5;
    pool.y[c] = 0.5;

    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);

    let alive = alive_slots(&pool);
    marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    // a should still be married to b, not to c
    let spouse_a = get_spouse_id(&pool, a);
    assert_eq!(spouse_a, Some(pool.ids[b]), "a should remain married to b");

    // c should not be married to a (a was already married)
    let spouse_c = get_spouse_id(&pool, c);
    assert_ne!(spouse_c, Some(pool.ids[a]), "c should not marry already-married a");
}

// ---------------------------------------------------------------------------
// Test 3: Age gate — agents below MARRIAGE_MIN_AGE are not matched
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_age_gate() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // One agent is old enough (20), one is too young (10)
    let adult = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 10, 1, 2, 3, 5);
    place_close(&mut pool, adult, child);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 0, "underage agent should not be matched");
    assert!(get_spouse_id(&pool, adult).is_none());
    assert!(get_spouse_id(&pool, child).is_none());
}

#[test]
fn test_marriage_exactly_min_age() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Both at exactly MARRIAGE_MIN_AGE (16) should match
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 16, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 16, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1, "agents at exactly min age should match");
    assert!(get_spouse_id(&pool, a).is_some());
}

// ---------------------------------------------------------------------------
// Test 4: Distance gate — agents beyond MARRIAGE_RADIUS are not matched
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_distance_gate() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_far(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 0, "distant agents should not match");
    assert_eq!(stats.marriage_pairs_rejected_distance, 1, "should count distance rejection");
}

#[test]
fn test_marriage_close_agents_match() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1, "close agents should match");
    assert_eq!(stats.marriage_pairs_rejected_distance, 0);
}

// ---------------------------------------------------------------------------
// Test 5: Incest — parent-child blocked
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_parent_child_blocked() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let parent = spawn(&mut pool, 0, 0, Occupation::Farmer, 40, 1, 2, 3, 5);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, parent, child);

    // Set parent-child relationship
    let parent_id = pool.ids[parent];
    pool.parent_id_0[child] = parent_id;

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 0, "parent-child marriage should be blocked");
    assert_eq!(stats.marriage_pairs_rejected_incest, 1);
}

#[test]
fn test_marriage_parent_child_blocked_slot1() {
    // Same test but parent is in parent_id_1 slot
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let parent = spawn(&mut pool, 0, 0, Occupation::Farmer, 40, 1, 2, 3, 5);
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, parent, child);

    let parent_id = pool.ids[parent];
    pool.parent_id_1[child] = parent_id;

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 0, "parent-child via slot 1 should be blocked");
    assert_eq!(stats.marriage_pairs_rejected_incest, 1);
}

// ---------------------------------------------------------------------------
// Test 6: Incest — siblings (shared parent) blocked
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_siblings_blocked() {
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Create a "parent" (doesn't need to be alive, just an ID)
    let parent = spawn(&mut pool, 0, 0, Occupation::Farmer, 50, 1, 2, 3, 5);
    let parent_id = pool.ids[parent];

    // Two siblings sharing parent_id_0
    let sib_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let sib_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    pool.parent_id_0[sib_a] = parent_id;
    pool.parent_id_0[sib_b] = parent_id;
    place_close(&mut pool, sib_a, sib_b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    // Sibling pair should be rejected; parent-sib pairs may also be rejected
    assert!(
        get_spouse_id(&pool, sib_a).is_none() || get_spouse_id(&pool, sib_a) != Some(pool.ids[sib_b]),
        "siblings should not marry each other"
    );
    assert!(stats.marriage_pairs_rejected_incest >= 1, "at least one incest rejection expected");
}

#[test]
fn test_marriage_half_siblings_blocked() {
    // Half-siblings: share parent_id_1 but different parent_id_0
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let shared_parent = spawn(&mut pool, 0, 0, Occupation::Farmer, 50, 1, 2, 3, 5);
    let shared_parent_id = pool.ids[shared_parent];

    let sib_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let sib_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    // Different parent_id_0 (different mothers), same parent_id_1 (same father)
    pool.parent_id_0[sib_a] = 9990; // fake unique parent
    pool.parent_id_0[sib_b] = 9991; // fake unique parent
    pool.parent_id_1[sib_a] = shared_parent_id;
    pool.parent_id_1[sib_b] = shared_parent_id;
    place_close(&mut pool, sib_a, sib_b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    // The sibling pair should be blocked
    let spouse_a = get_spouse_id(&pool, sib_a);
    assert!(
        spouse_a.is_none() || spouse_a != Some(pool.ids[sib_b]),
        "half-siblings should not marry each other"
    );
    assert!(stats.marriage_pairs_rejected_incest >= 1);
}

#[test]
fn test_marriage_parent_none_not_treated_as_shared() {
    // Two agents both with PARENT_NONE — should NOT be treated as siblings
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    // Both have PARENT_NONE by default from spawn — shares_parent should skip PARENT_NONE
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1, "PARENT_NONE agents should not be treated as siblings");
    assert_eq!(stats.marriage_pairs_rejected_incest, 0);
}

// ---------------------------------------------------------------------------
// Test 7: Scored greedy — higher-scoring pair wins
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_scored_greedy() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Agent A: civ 0, belief 5, culture [1,2,3]
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    // Agent B: civ 0, belief 5, culture [1,2,3] — perfect match with A
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    // Agent C: civ 0, belief 7, culture [4,5,6] — poor match with A
    let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 4, 5, 6, 7);

    // All close together
    pool.x[a] = 0.5; pool.y[a] = 0.5;
    pool.x[b] = 0.5; pool.y[b] = 0.5;
    pool.x[c] = 0.5; pool.y[c] = 0.5;

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert!(stats.marriages_formed >= 1, "should form at least one marriage");

    // A should match B (higher score: same civ + same belief + same culture)
    // not C (different belief with penalty, different culture)
    let spouse_a = get_spouse_id(&pool, a);
    assert_eq!(
        spouse_a,
        Some(pool.ids[b]),
        "A should marry B (higher score), not C"
    );
}

// ---------------------------------------------------------------------------
// Test 8: Cadence — only regions where region_idx % CADENCE == turn % CADENCE
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_cadence_scheduling() {
    // MARRIAGE_CADENCE = 4. Region 0 scanned at turn 0,4,8. Region 1 at turn 1,5,9.
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_civ = 0;
    regions[1].controller_civ = 0;
    let signals = peaceful_signals();

    // Pair in region 0
    let a0 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b0 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a0, b0);

    // Pair in region 1
    let a1 = spawn(&mut pool, 1, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b1 = spawn(&mut pool, 1, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    pool.x[a1] = 0.5; pool.y[a1] = 0.5;
    pool.x[b1] = 0.51; pool.y[b1] = 0.51;

    // Turn 0: region 0 scanned (0 % 4 == 0), region 1 NOT (1 % 4 != 0)
    let alive = alive_slots(&pool);
    let stats0 = marriage_scan(&mut pool, &regions, &signals, 0, &alive);
    assert!(stats0.marriages_formed >= 1, "region 0 should form marriage on turn 0");
    assert!(get_spouse_id(&pool, a0).is_some(), "region 0 pair should be married after turn 0");
    assert!(get_spouse_id(&pool, a1).is_none(), "region 1 pair should NOT be married after turn 0");

    // Turn 1: region 1 scanned (1 % 4 == 1)
    let alive = alive_slots(&pool);
    let stats1 = marriage_scan(&mut pool, &regions, &signals, 1, &alive);
    assert!(stats1.marriages_formed >= 1, "region 1 should form marriage on turn 1");
    assert!(get_spouse_id(&pool, a1).is_some(), "region 1 pair should be married after turn 1");
}

#[test]
fn test_marriage_cadence_non_eligible_turn() {
    let mut pool = AgentPool::new(8);
    let regions = vec![RegionState::new(0)];
    let signals = peaceful_signals();

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    // Turn 2: region 0 should NOT be scanned (0 % 4 != 2)
    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 2, &alive);
    assert_eq!(stats.marriages_formed, 0, "region 0 should not be scanned on turn 2");
    assert_eq!(stats.marriage_pairs_evaluated, 0);
}

// ---------------------------------------------------------------------------
// Test 9: Two-parent FFI round-trip
// ---------------------------------------------------------------------------

#[test]
fn test_two_parent_ffi_round_trip() {
    let mut pool = AgentPool::new(8);

    // Spawn two parents
    let parent_a = spawn(&mut pool, 0, 0, Occupation::Farmer, 30, 1, 2, 3, 5);
    let parent_b = spawn(&mut pool, 0, 0, Occupation::Farmer, 28, 1, 2, 3, 5);
    let id_a = pool.ids[parent_a];
    let id_b = pool.ids[parent_b];

    // Spawn a child and manually set both parents
    let child = spawn(&mut pool, 0, 0, Occupation::Farmer, 0, 1, 2, 3, 5);
    pool.parent_id_0[child] = id_a;
    pool.parent_id_1[child] = id_b;

    // Verify in-memory state
    assert_eq!(pool.parent_id_0(child), id_a);
    assert_eq!(pool.parent_id_1(child), id_b);
    assert!(pool.has_parent(child, id_a));
    assert!(pool.has_parent(child, id_b));

    // Export to Arrow RecordBatch and verify columns exist with correct values
    let batch = pool.to_record_batch().expect("to_record_batch should succeed");

    // Find the child's row in the batch (search by agent id)
    let id_col = batch.column_by_name("id")
        .expect("id column should exist")
        .as_any().downcast_ref::<UInt32Array>()
        .expect("id column should be UInt32");
    let p0_col = batch.column_by_name("parent_id_0")
        .expect("parent_id_0 column should exist")
        .as_any().downcast_ref::<UInt32Array>()
        .expect("parent_id_0 column should be UInt32");
    let p1_col = batch.column_by_name("parent_id_1")
        .expect("parent_id_1 column should exist")
        .as_any().downcast_ref::<UInt32Array>()
        .expect("parent_id_1 column should be UInt32");

    let child_id = pool.ids[child];
    let mut found = false;
    for row in 0..batch.num_rows() {
        if id_col.value(row) == child_id {
            assert_eq!(p0_col.value(row), id_a, "parent_id_0 in Arrow should match");
            assert_eq!(p1_col.value(row), id_b, "parent_id_1 in Arrow should match");
            found = true;
            break;
        }
    }
    assert!(found, "child agent should appear in snapshot");

    // Also verify parents have PARENT_NONE in the snapshot
    for row in 0..batch.num_rows() {
        if id_col.value(row) == id_a || id_col.value(row) == id_b {
            assert_eq!(p0_col.value(row), 0, "spawned parent should have PARENT_NONE for parent_id_0");
            assert_eq!(p1_col.value(row), 0, "spawned parent should have PARENT_NONE for parent_id_1");
        }
    }
}

// ---------------------------------------------------------------------------
// Test 10: Remarriage — kill spouse, verify bond removed, re-scan → survivor
//          can rematch
// ---------------------------------------------------------------------------

#[test]
fn test_remarriage_after_spouse_death() {
    use chronicler_agents::death_cleanup_sweep;

    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Spawn 3 agents: a, b (will marry), c (potential new spouse)
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    for &s in &[a, b, c] {
        pool.x[s] = 0.5;
        pool.y[s] = 0.5;
    }

    // Marry a and b
    let id_b = pool.ids[b];
    upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1);
    assert_eq!(get_spouse_id(&pool, a), Some(id_b));

    // Kill b
    pool.kill(b);
    let mut dead_ids = std::collections::HashSet::new();
    dead_ids.insert(id_b);

    // Run death cleanup to remove dead bonds from survivors
    let alive = vec![a, c];
    death_cleanup_sweep(&mut pool, &alive, &dead_ids, 5);

    // Verify marriage bond is removed from a
    assert!(
        get_spouse_id(&pool, a).is_none(),
        "after spouse death + cleanup, survivor should have no spouse"
    );

    // Run marriage_scan again on the next cadence-eligible turn
    // Turn 4: region 0 scanned (0 % 4 == 0)
    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 4, &alive);

    assert!(stats.marriages_formed >= 1, "survivor should be able to remarry");
    let new_spouse = get_spouse_id(&pool, a);
    assert_eq!(
        new_spouse,
        Some(pool.ids[c]),
        "survivor should marry the remaining eligible agent"
    );
}

// ---------------------------------------------------------------------------
// Bonus tests: cross-civ wartime blocking
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_cross_civ_wartime_blocked() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = war_signals(); // civ 0 is at war

    // Agent from civ 0, agent from civ 1 — cross-civ during wartime
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 1, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 0, "cross-civ marriage during wartime should be blocked");
    assert_eq!(stats.marriage_pairs_rejected_hostile, 1);
}

#[test]
fn test_marriage_same_civ_wartime_allowed() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = war_signals(); // civ 0 is at war

    // Both agents from civ 0 — same-civ should be allowed even during war
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1, "same-civ marriage during wartime should be allowed");
}

// ---------------------------------------------------------------------------
// Bonus: empty pool and single-agent no-panic tests
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_empty_pool_no_panic() {
    let mut pool = AgentPool::new(4);
    let regions = vec![RegionState::new(0)];
    let signals = peaceful_signals();

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);
    assert_eq!(stats.marriages_formed, 0);
    assert_eq!(stats.marriage_pairs_evaluated, 0);
}

#[test]
fn test_marriage_single_agent_no_panic() {
    let mut pool = AgentPool::new(4);
    let regions = vec![RegionState::new(0)];
    let signals = peaceful_signals();

    let _a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);
    assert_eq!(stats.marriages_formed, 0);
}

// ---------------------------------------------------------------------------
// Bonus: marriage stats tracking (same_civ, cross_civ, faith)
// ---------------------------------------------------------------------------

#[test]
fn test_marriage_stats_same_civ_counted() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1);
    assert_eq!(stats.same_civ_marriages, 1);
    assert_eq!(stats.cross_civ_marriages, 0);
    assert_eq!(stats.same_faith_marriages, 1);
    assert_eq!(stats.cross_faith_marriages, 0);
}

#[test]
fn test_marriage_stats_cross_faith_counted() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;
    let signals = peaceful_signals();

    // Same civ, different beliefs
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 1, 2, 3, 7);
    place_close(&mut pool, a, b);

    let alive = alive_slots(&pool);
    let stats = marriage_scan(&mut pool, &regions, &signals, 0, &alive);

    assert_eq!(stats.marriages_formed, 1);
    assert_eq!(stats.same_civ_marriages, 1);
    assert_eq!(stats.cross_faith_marriages, 1);
    assert_eq!(stats.same_faith_marriages, 0);
}
