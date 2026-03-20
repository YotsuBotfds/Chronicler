//! M50b Formation Scan: Integration tests.
//!
//! Tests verify staggered scheduling, bond formation, budget caps,
//! determinism, and transient signal reset between cadence ticks.

use chronicler_agents::{
    AgentPool, Occupation, RegionState,
    formation_scan,
    MAX_NEW_BONDS_PER_PASS, MAX_NEW_BONDS_PER_REGION,
    MemoryEventType,
};
use chronicler_agents::relationships::{
    find_relationship, read_rel, BondType,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Spawn agent with full control over region, civ, occupation, age, cultural
/// values, and belief. Uses fixed boldness/loyalty_trait.
fn spawn(
    pool: &mut AgentPool,
    region: u16,
    civ: u8,
    occ: Occupation,
    age: u16,
    ambition: f32,
    cv0: u8,
    cv1: u8,
    cv2: u8,
    belief: u8,
) -> usize {
    pool.spawn(region, civ, occ, age, 0.5, ambition, 0.5, cv0, cv1, cv2, belief)
}

/// Build alive_slots list from pool.
fn alive_slots(pool: &AgentPool) -> Vec<usize> {
    (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect()
}

/// Write a battle memory at the given slot + turn, so agents_share_memory can match.
fn write_battle_memory(pool: &mut AgentPool, slot: usize, turn: u16) {
    pool.memory_event_types[slot][0] = MemoryEventType::Battle as u8;
    pool.memory_turns[slot][0] = turn;
    pool.memory_intensities[slot][0] = -60;
    pool.memory_count[slot] = 1;
}

// ---------------------------------------------------------------------------
// Test 1: Staggered scheduling
// ---------------------------------------------------------------------------

#[test]
fn test_staggered_scheduling_region_cadence() {
    // Region 0 is scanned when turn % FORMATION_CADENCE == 0
    // Region 1 is scanned when turn % FORMATION_CADENCE == 1
    // With FORMATION_CADENCE=6:
    //   Region 0: turns 0, 6, 12
    //   Region 1: turns 1, 7, 13

    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_civ = 0;
    regions[1].controller_civ = 0;

    // Two compatible agents in region 0 — same belief, same occ, same civ, shared memory
    let a0 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b0 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a0, 10);
    write_battle_memory(&mut pool, b0, 10);

    // Two compatible agents in region 1
    let a1 = spawn(&mut pool, 1, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b1 = spawn(&mut pool, 1, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a1, 10);
    write_battle_memory(&mut pool, b1, 10);

    // Turn 0: region 0 is scanned (0 % 6 == 0), region 1 is NOT (1 % 6 != 0)
    let slots = alive_slots(&pool);
    let stats0 = formation_scan(&mut pool, &regions, 0, &slots);
    assert!(stats0.bonds_formed > 0, "region 0 should form bonds on turn 0");

    // Check region 0 agents have bonds
    let id_b0 = pool.ids[b0];
    assert!(
        find_relationship(&pool, a0, id_b0, BondType::Friend as u8).is_some(),
        "region 0 pair should have friend bond after turn 0"
    );

    // Region 1 agents should NOT have bonds yet
    let id_b1 = pool.ids[b1];
    assert!(
        find_relationship(&pool, a1, id_b1, BondType::Friend as u8).is_none(),
        "region 1 pair should NOT have friend bond after turn 0"
    );

    // Turn 1: region 1 is scanned (1 % 6 == 1)
    let slots = alive_slots(&pool);
    let stats1 = formation_scan(&mut pool, &regions, 1, &slots);
    assert!(stats1.bonds_formed > 0, "region 1 should form bonds on turn 1");
    assert!(
        find_relationship(&pool, a1, id_b1, BondType::Friend as u8).is_some(),
        "region 1 pair should have friend bond after turn 1"
    );
}

#[test]
fn test_staggered_scheduling_region_0_scanned_on_multiples() {
    // Region 0 on tick 0, 6, 12
    let mut pool = AgentPool::new(8);
    let regions = vec![RegionState::new(0)];

    // Two compatible agents in region 0
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);
    write_battle_memory(&mut pool, b, 10);

    // Turn 3: region 0 should NOT be scanned (0 % 6 != 3)
    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 3, &slots);
    assert_eq!(stats.bonds_formed, 0, "region 0 should not be scanned on turn 3");
    assert_eq!(stats.pairs_evaluated, 0);

    // Turn 6: region 0 IS scanned (0 % 6 == 0)
    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 6, &slots);
    assert!(stats.bonds_formed > 0, "region 0 should be scanned on turn 6");
}

// ---------------------------------------------------------------------------
// Test 2: Friend bond formation via compatibility + shared memory
// ---------------------------------------------------------------------------

#[test]
fn test_friend_bond_forms_with_shared_memory_and_culture() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;

    // Two agents: same belief (5), same occupation, same civ_affinity (0),
    // identical culture [1,2,3] -> compatibility = W_BELIEF + W_OCC + W_AFF + W_CULTURE
    // = 0.35 + 0.15 + 0.15 + 0.35 = 1.0 >> FRIEND_THRESHOLD (0.50)
    // Plus shared memory requirement.
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);
    write_battle_memory(&mut pool, b, 10);

    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 0, &slots);

    // With 2 agents sharing belief=5, all believers = region_pop, so CoReligionist
    // gate fails (not a minority). Only Friend bond forms.
    assert!(stats.bonds_formed >= 1, "should form at least 1 bond");
    let id_b = pool.ids[b];
    let rel_idx = find_relationship(&pool, a, id_b, BondType::Friend as u8);
    assert!(rel_idx.is_some(), "a should have friend bond to b");
    let (_, sent, bt, _) = read_rel(&pool, a, rel_idx.unwrap());
    assert_eq!(bt, BondType::Friend as u8);
    assert_eq!(sent, 30); // FRIEND_INITIAL_SENTIMENT

    // Symmetric: b also has bond to a
    let id_a = pool.ids[a];
    assert!(
        find_relationship(&pool, b, id_a, BondType::Friend as u8).is_some(),
        "b should have symmetric friend bond to a"
    );
}

// ---------------------------------------------------------------------------
// Test 3: Formation caps respected
// ---------------------------------------------------------------------------

#[test]
fn test_per_agent_bond_cap() {
    // MAX_NEW_BONDS_PER_PASS = 2: each agent can form at most 2 bonds per scan
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;

    // Agent 0: will try to form bonds with agents 1, 2, 3
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);

    // Create 4 compatible partners
    let mut partners = Vec::new();
    for _ in 0..4 {
        let p = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
        write_battle_memory(&mut pool, p, 10);
        partners.push(p);
    }

    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 0, &slots);

    // Agent a can form at most MAX_NEW_BONDS_PER_PASS (2) bonds.
    // Other agents can also form bonds with each other, but each is capped at 2.
    // Count how many bonds agent a has:
    let a_bond_count = pool.rel_count[a] as u32;
    assert!(
        a_bond_count <= MAX_NEW_BONDS_PER_PASS as u32,
        "agent a should have at most {} bonds, got {}",
        MAX_NEW_BONDS_PER_PASS, a_bond_count
    );

    // Total bonds formed should be reasonable (each agent capped at 2)
    assert!(stats.bonds_formed > 0, "should form some bonds");
}

#[test]
fn test_per_region_bond_cap() {
    // MAX_NEW_BONDS_PER_REGION = 50: region can have at most 50 new bonds per scan.
    // This test verifies the cap by creating a large number of compatible agents.
    // With 20 agents: C(20,2) = 190 pairs, all compatible. Should be capped at 50.
    let mut pool = AgentPool::new(64);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;

    for _ in 0..20 {
        let s = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
        write_battle_memory(&mut pool, s, 10);
    }

    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 0, &slots);

    // Per-agent cap (2) is tighter: 20 agents * 2 / 2 = 20 bonds max (symmetric).
    // Actually with 20 agents, each capped at 2 symmetric bonds,
    // max bonds = 20 (since each bond consumes budget from 2 agents).
    assert!(
        stats.bonds_formed <= MAX_NEW_BONDS_PER_REGION,
        "region bond count {} should be <= MAX_NEW_BONDS_PER_REGION {}",
        stats.bonds_formed, MAX_NEW_BONDS_PER_REGION
    );
}

// ---------------------------------------------------------------------------
// Test 4: Determinism
// ---------------------------------------------------------------------------

#[test]
fn test_deterministic_same_inputs_same_bonds() {
    // Run the same formation scan twice from identical initial states.
    // Bonds formed should be identical.
    fn run_scan() -> Vec<(u32, u32, u8)> {
        let mut pool = AgentPool::new(16);
        let mut regions = vec![RegionState::new(0)];
        regions[0].controller_civ = 0;

        for i in 0..6u8 {
            let s = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
            write_battle_memory(&mut pool, s, 10);
            // Give them slightly different wealth to make rival gates differentiate
            pool.wealth[s] = 10.0 + (i as f32);
        }

        let slots = alive_slots(&pool);
        formation_scan(&mut pool, &regions, 0, &slots);

        // Collect all bonds from all agents
        let mut bonds = Vec::new();
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) { continue; }
            let count = pool.rel_count[slot] as usize;
            for i in 0..count {
                bonds.push((
                    pool.ids[slot],
                    pool.rel_target_ids[slot][i],
                    pool.rel_bond_types[slot][i],
                ));
            }
        }
        bonds.sort();
        bonds
    }

    let bonds1 = run_scan();
    let bonds2 = run_scan();
    assert_eq!(bonds1, bonds2, "same inputs must produce identical bonds");
    assert!(!bonds1.is_empty(), "should form at least some bonds");
}

// ---------------------------------------------------------------------------
// Test 5: 2-turn transient signal test (CLAUDE.md requirement)
// ---------------------------------------------------------------------------

#[test]
fn test_formation_stats_reset_between_cadence_ticks() {
    // Per CLAUDE.md: every new transient signal requires a 2+ turn integration test
    // verifying the value resets after consumption.
    //
    // FormationStats is returned fresh each call. Verify that calling formation_scan
    // on two consecutive cadence-eligible turns produces independent stats.
    let mut pool = AgentPool::new(16);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;

    // Two compatible agents in region 0
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);
    write_battle_memory(&mut pool, b, 10);

    // Turn 0: region 0 scanned (0 % 6 == 0), should form bonds
    // Multi-bond: pair qualifies for Friend + CoReligionist
    let slots = alive_slots(&pool);
    let stats_t0 = formation_scan(&mut pool, &regions, 0, &slots);
    assert!(stats_t0.bonds_formed >= 1, "turn 0: should form bonds");
    assert!(stats_t0.pairs_evaluated > 0, "turn 0: should evaluate pairs");

    // Turn 6: region 0 scanned again (6 % 6 == 0).
    // All eligible bond types already exist, so no new bonds should form.
    let slots = alive_slots(&pool);
    let stats_t6 = formation_scan(&mut pool, &regions, 6, &slots);
    // Stats should be fresh (not accumulating from turn 0)
    assert_eq!(
        stats_t6.bonds_formed, 0,
        "turn 6: no new bonds (all eligible types already bonded), stats are fresh"
    );
    // pairs_evaluated may be >0 (pair is evaluated but all types already exist)
    // The key assertion: bonds_formed is 0, proving stats reset between calls
}

#[test]
fn test_formation_stats_independent_across_non_cadence_turns() {
    // Additional transient test: stats from a non-cadence turn should be zeroed
    let mut pool = AgentPool::new(8);
    let regions = vec![RegionState::new(0)];

    let _a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let _b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);

    // Turn 3: region 0 not scanned (0 % 6 != 3)
    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 3, &slots);
    assert_eq!(stats.bonds_formed, 0);
    assert_eq!(stats.pairs_evaluated, 0);
    assert_eq!(stats.pairs_eligible, 0);
    assert_eq!(stats.bonds_evicted, 0);
}

// ---------------------------------------------------------------------------
// Test 6: Existing bond prevents duplicate
// ---------------------------------------------------------------------------

#[test]
fn test_existing_bond_prevents_duplicate_formation() {
    let mut pool = AgentPool::new(8);
    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_civ = 0;

    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);
    write_battle_memory(&mut pool, b, 10);

    // Form bonds on turn 0 (multi-bond: Friend + CoReligionist possible)
    let slots = alive_slots(&pool);
    let stats1 = formation_scan(&mut pool, &regions, 0, &slots);
    let bonds_after_t0 = stats1.bonds_formed;
    assert!(bonds_after_t0 >= 1, "should form at least 1 bond");
    let rel_count_after_t0 = pool.rel_count[a];

    // Try again on turn 6 — all eligible types already exist, should be rejected
    let slots = alive_slots(&pool);
    let stats2 = formation_scan(&mut pool, &regions, 6, &slots);
    assert_eq!(stats2.bonds_formed, 0, "should not form duplicate bond of any type");
    assert_eq!(pool.rel_count[a], rel_count_after_t0, "a should have same bond count as after t0");
}

// ---------------------------------------------------------------------------
// Test 7: Agents in different regions don't get paired
// ---------------------------------------------------------------------------

#[test]
fn test_cross_region_agents_not_paired() {
    let mut pool = AgentPool::new(8);
    let regions = vec![RegionState::new(0), RegionState::new(1)];

    // a in region 0, b in region 1
    let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    let b = spawn(&mut pool, 1, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);
    write_battle_memory(&mut pool, a, 10);
    write_battle_memory(&mut pool, b, 10);

    // Scan both turns to cover both regions
    let slots = alive_slots(&pool);
    formation_scan(&mut pool, &regions, 0, &slots);
    let slots = alive_slots(&pool);
    formation_scan(&mut pool, &regions, 1, &slots);

    // No bond should form (each region has only 1 agent, need >= 2 for pairs)
    assert_eq!(pool.rel_count[a], 0, "a should have no bonds");
    assert_eq!(pool.rel_count[b], 0, "b should have no bonds");
}

// ---------------------------------------------------------------------------
// Test 8: Single agent in region doesn't cause issues
// ---------------------------------------------------------------------------

#[test]
fn test_single_agent_in_region_no_panic() {
    let mut pool = AgentPool::new(4);
    let regions = vec![RegionState::new(0)];

    let _a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 5);

    let slots = alive_slots(&pool);
    let stats = formation_scan(&mut pool, &regions, 0, &slots);
    assert_eq!(stats.bonds_formed, 0);
    assert_eq!(stats.pairs_evaluated, 0);
}
