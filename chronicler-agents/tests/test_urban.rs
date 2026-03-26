//! M56b: Urban effects tests

use chronicler_agents::{AgentPool, Occupation, assign_settlement_ids, build_settlement_grids};

fn baseline_civ_signal() -> chronicler_agents::signals::CivSignals {
    chronicler_agents::signals::CivSignals {
        civ_id: 0,
        stability: 50,
        is_at_war: false,
        dominant_faction: 0,
        faction_military: 0.0,
        faction_merchant: 0.0,
        faction_cultural: 0.0,
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
    }
}

#[test]
fn test_grid_construction_basic() {
    let grids = build_settlement_grids(
        2,
        &[0, 0],
        &[1, 1],
        &[3, 4],
        &[7, 7],
    );
    assert_eq!(grids.len(), 2);
    assert_eq!(grids[0][7 * 10 + 3], 1);
    assert_eq!(grids[0][7 * 10 + 4], 1);
    assert_eq!(grids[0][0], 0);
    assert_eq!(grids[1][0], 0);
}

#[test]
fn test_grid_tiebreak_lowest_id_wins() {
    let grids = build_settlement_grids(
        1,
        &[0, 0],
        &[2, 5],
        &[3, 3],
        &[7, 7],
    );
    assert_eq!(grids[0][7 * 10 + 3], 2);
}

#[test]
fn test_assignment_basic() {
    let mut pool = AgentPool::new(4);
    let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let s1 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.x[s0] = 0.35;
    pool.y[s0] = 0.72;
    pool.x[s1] = 0.95;
    pool.y[s1] = 0.95;

    let grids = build_settlement_grids(1, &[0], &[1], &[3], &[7]);
    assign_settlement_ids(&mut pool, &grids);

    assert_eq!(pool.settlement_ids[s0], 1);
    assert_eq!(pool.settlement_ids[s1], 0);
}

#[test]
fn test_dual_pass_assignment() {
    let mut pool = AgentPool::new(4);
    let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool.x[s0] = 0.35;
    pool.y[s0] = 0.72;

    let grids = build_settlement_grids(1, &[0], &[1], &[3], &[7]);

    // Pass A: assign from current position
    assign_settlement_ids(&mut pool, &grids);
    assert_eq!(pool.settlement_ids[s0], 1, "Pass A should assign urban");

    // Simulate migration: move agent to (0.95, 0.95) → cell (9,9) which is rural
    pool.x[s0] = 0.95;
    pool.y[s0] = 0.95;

    // Pass B: reassign from new position
    assign_settlement_ids(&mut pool, &grids);
    assert_eq!(pool.settlement_ids[s0], 0, "Pass B should assign rural after move");
}

#[test]
fn test_urban_safety_restores_slower() {
    use chronicler_agents::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_urban.need_safety[su] = 0.3;
    pool_rural.need_safety[sr] = 0.3;
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    let regions = vec![RegionState::new(0)];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![baseline_civ_signal()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    chronicler_agents::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    chronicler_agents::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    assert!(pool_urban.need_safety[su] < pool_rural.need_safety[sr],
        "Urban safety {:.4} should be < rural {:.4}",
        pool_urban.need_safety[su], pool_rural.need_safety[sr]);
}

#[test]
fn test_urban_material_food_contribution_reduced() {
    use chronicler_agents::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_urban.need_material[su] = 0.3;
    pool_rural.need_material[sr] = 0.3;
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    let mut region = RegionState::new(0);
    region.food_sufficiency = 1.2;
    let regions = vec![region];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![baseline_civ_signal()],
        contested_regions: vec![false],
    };
    let wp = vec![0.0_f32]; // zero wealth -> only food term contributes

    chronicler_agents::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    chronicler_agents::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    assert!(pool_urban.need_material[su] < pool_rural.need_material[sr],
        "Urban material (food only) {:.4} should be < rural {:.4}",
        pool_urban.need_material[su], pool_rural.need_material[sr]);
}

#[test]
fn test_urban_social_restores_faster() {
    use chronicler_agents::RegionState;

    let mut pool_urban = AgentPool::new(2);
    let mut pool_rural = AgentPool::new(2);

    let su = pool_urban.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sr = pool_rural.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_urban.need_social[su] = 0.3;
    pool_rural.need_social[sr] = 0.3;
    pool_urban.settlement_ids[su] = 1;
    pool_rural.settlement_ids[sr] = 0;

    let mut region = RegionState::new(0);
    region.population = 30;
    region.carrying_capacity = 60;
    let regions = vec![region];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![baseline_civ_signal()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    chronicler_agents::needs::update_needs(&mut pool_urban, &regions, &signals, &wp);
    chronicler_agents::needs::update_needs(&mut pool_rural, &regions, &signals, &wp);

    assert!(pool_urban.need_social[su] > pool_rural.need_social[sr],
        "Urban social {:.4} should be > rural {:.4}",
        pool_urban.need_social[su], pool_rural.need_social[sr]);
}

#[test]
fn test_rural_agent_unchanged_from_baseline() {
    use chronicler_agents::RegionState;

    let mut pool_a = AgentPool::new(2);
    let mut pool_b = AgentPool::new(2);

    let sa = pool_a.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let sb = pool_b.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    pool_a.need_safety[sa] = 0.3;
    pool_a.need_material[sa] = 0.3;
    pool_a.need_social[sa] = 0.3;
    pool_b.need_safety[sb] = 0.3;
    pool_b.need_material[sb] = 0.3;
    pool_b.need_social[sb] = 0.3;

    // Both rural
    pool_a.settlement_ids[sa] = 0;
    pool_b.settlement_ids[sb] = 0;

    let regions = vec![RegionState::new(0)];
    let signals = chronicler_agents::signals::TickSignals {
        civs: vec![baseline_civ_signal()],
        contested_regions: vec![false],
    };
    let wp = vec![0.5_f32];

    chronicler_agents::needs::update_needs(&mut pool_a, &regions, &signals, &wp);
    chronicler_agents::needs::update_needs(&mut pool_b, &regions, &signals, &wp);

    assert!((pool_a.need_safety[sa] - pool_b.need_safety[sb]).abs() < 1e-6);
    assert!((pool_a.need_material[sa] - pool_b.need_material[sb]).abs() < 1e-6);
    assert!((pool_a.need_social[sa] - pool_b.need_social[sb]).abs() < 1e-6);
}

#[test]
fn test_urban_satisfaction_material_bonus() {
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};

    let mut base = SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.5, pop_over_capacity: 0.0,
        civ_at_war: false, region_contested: false,
        occ_matches_faction: false, is_displaced: false,
        trade_routes: 1, faction_influence: 0.0,
        shock: chronicler_agents::signals::CivShock::default(),
        agent_values: [0, 0, 0], controller_values: [0, 0, 0],
        agent_belief: 0, majority_belief: 0, has_temple: false,
        persecution_intensity: 0.0,
        gini_coefficient: 0.0, wealth_percentile: 0.5,
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
        is_urban: false,
    };
    let rural = compute_satisfaction_with_culture(&base);
    base.is_urban = true;
    let urban = compute_satisfaction_with_culture(&base);

    let diff = urban - rural;
    // Net: +0.02 (material bonus) - 0.04 (safety penalty) = -0.02
    assert!(diff > -0.03 && diff < -0.01,
        "Urban-rural diff {:.4} should be ~-0.02", diff);
}

#[test]
fn test_urban_safety_penalty_respects_cap() {
    use chronicler_agents::satisfaction::{SatisfactionInputs, compute_satisfaction_with_culture};

    let mut inp = SatisfactionInputs {
        occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
        demand_supply_ratio: 0.5, pop_over_capacity: 0.0,
        civ_at_war: false, region_contested: false,
        occ_matches_faction: false, is_displaced: false,
        trade_routes: 1, faction_influence: 0.0,
        shock: chronicler_agents::signals::CivShock::default(),
        agent_values: [4, 3, 2], controller_values: [0, 1, 5], // max cultural mismatch
        agent_belief: 1, majority_belief: 2,                     // religious mismatch
        has_temple: false,
        persecution_intensity: 1.0,                               // max persecution
        gini_coefficient: 1.0, wealth_percentile: 0.0,          // max class tension
        food_sufficiency: 1.0, merchant_margin: 0.0,
        memory_score: 0.0,
        is_urban: true,
    };
    let urban_sat = compute_satisfaction_with_culture(&inp);
    inp.is_urban = false;
    let rural_sat = compute_satisfaction_with_culture(&inp);

    // Both should hit the cap. Urban has material bonus but penalty is capped.
    // At cap: urban should be ~+0.02 higher (material bonus is outside cap)
    let diff = urban_sat - rural_sat;
    assert!(diff > 0.01 && diff < 0.03,
        "At cap, urban-rural diff {:.4} should be ~+0.02 (material bonus only)", diff);
}
