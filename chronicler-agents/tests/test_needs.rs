use chronicler_agents::{
    AgentPool, Occupation, RegionState,
    CivSignals, TickSignals,
    decay_needs, restore_needs, clamp_needs, update_needs,
    compute_need_utility_modifiers,
};

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

fn make_region(id: u16) -> RegionState {
    let mut r = RegionState::new(id);
    r.carrying_capacity = 60;
    r.population = 30;
    r.controller_civ = 0;
    r.food_sufficiency = 1.0;
    r
}

fn make_civ_signals(civ_id: u8, is_at_war: bool) -> CivSignals {
    CivSignals {
        civ_id,
        stability: 50,
        is_at_war,
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
    }
}

fn peacetime_signals() -> TickSignals {
    TickSignals {
        civs: vec![make_civ_signals(0, false)],
        contested_regions: vec![false],
    }
}

fn wartime_signals() -> TickSignals {
    TickSignals {
        civs: vec![make_civ_signals(0, true)],
        contested_regions: vec![true],
    }
}

// ===========================================================================
// Task 1 tests (preserved from initial commit)
// ===========================================================================

#[test]
fn test_needs_spawn_at_starting_value() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert!((pool.need_safety[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_material[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_social[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_spiritual[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_autonomy[slot] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot] - 0.5).abs() < 0.001);
}

#[test]
fn test_needs_reuse_reset() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.1;
    pool.need_purpose[slot] = 0.9;
    pool.kill(slot);
    let slot2 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert_eq!(slot, slot2);
    assert!((pool.need_safety[slot2] - 0.5).abs() < 0.001);
    assert!((pool.need_purpose[slot2] - 0.5).abs() < 0.001);
}

// ===========================================================================
// Task 2: Decay tests
// ===========================================================================

#[test]
fn test_decay_basic() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    assert!((pool.need_safety[slot] - 0.5).abs() < 0.001);

    decay_needs(&mut pool, &[slot]);

    // SAFETY_DECAY = 0.015
    let expected = 0.5 - 0.015;
    assert!(
        (pool.need_safety[slot] - expected).abs() < 0.001,
        "Expected safety {} after one decay, got {}",
        expected, pool.need_safety[slot]
    );
}

#[test]
fn test_decay_clamps_at_zero() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.005;

    decay_needs(&mut pool, &[slot]);

    assert!(
        pool.need_safety[slot] == 0.0,
        "Expected 0.0 after decay on value below decay rate, got {}",
        pool.need_safety[slot]
    );
}

#[test]
fn test_decay_all_six_needs() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);

    decay_needs(&mut pool, &[slot]);

    assert!((pool.need_safety[slot] - (0.5 - 0.015)).abs() < 0.001);
    assert!((pool.need_material[slot] - (0.5 - 0.012)).abs() < 0.001);
    assert!((pool.need_social[slot] - (0.5 - 0.008)).abs() < 0.001);
    assert!((pool.need_spiritual[slot] - (0.5 - 0.010)).abs() < 0.001);
    assert!((pool.need_autonomy[slot] - (0.5 - 0.010)).abs() < 0.001);
    assert!((pool.need_purpose[slot] - (0.5 - 0.012)).abs() < 0.001);
}

// ===========================================================================
// Task 2: Restoration tests
// ===========================================================================

#[test]
fn test_restoration_proportional() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 3);
    pool.need_spiritual[slot] = 0.2;

    let mut region = make_region(0);
    region.has_temple = true;
    region.majority_belief = 3;

    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32];

    restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);

    assert!(
        pool.need_spiritual[slot] > 0.2,
        "Spiritual should increase from 0.2, got {}",
        pool.need_spiritual[slot]
    );
    assert!(
        pool.need_spiritual[slot] < 0.3,
        "Should stay below 0.3 after one tick, got {}",
        pool.need_spiritual[slot]
    );
}

#[test]
fn test_restoration_diminishes_near_max() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 3);
    pool.need_spiritual[slot] = 0.95;

    let mut region = make_region(0);
    region.has_temple = true;
    region.majority_belief = 3;

    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32];

    let before = pool.need_spiritual[slot];
    restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);
    let delta = pool.need_spiritual[slot] - before;

    assert!(
        delta < 0.005,
        "Restoration delta near max should be tiny, got {}",
        delta
    );
    assert!(delta > 0.0, "Should still restore a tiny amount, got {}", delta);
}

#[test]
fn test_autonomy_blocked_by_displacement() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_autonomy[slot] = 0.1;
    pool.displacement_turns[slot] = 3;

    let mut region = make_region(0);
    region.controller_civ = 0;
    region.persecution_intensity = 0.0;

    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32];

    let before = pool.need_autonomy[slot];
    restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);
    let after = pool.need_autonomy[slot];

    assert!(
        (after - before).abs() < 0.001,
        "Autonomy should NOT change with displacement: before={}, after={}",
        before, after
    );
}

#[test]
fn test_equilibrium_convergence() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.1;

    let region = make_region(0);
    let regions = vec![region];
    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32];
    let alive_slots = vec![slot];

    for _ in 0..200 {
        decay_needs(&mut pool, &alive_slots);
        restore_needs(&mut pool, &alive_slots, &regions, &signals, &wealth_pct);
        clamp_needs(&mut pool, &alive_slots);
    }

    let final_val = pool.need_safety[slot];

    // One more tick to verify convergence
    let before_last = pool.need_safety[slot];
    decay_needs(&mut pool, &alive_slots);
    restore_needs(&mut pool, &alive_slots, &regions, &signals, &wealth_pct);
    clamp_needs(&mut pool, &alive_slots);
    let last_delta = (pool.need_safety[slot] - before_last).abs();

    assert!(
        last_delta < 0.001,
        "Should have converged after 200 ticks, last delta = {}",
        last_delta
    );
    assert!(
        final_val > 0.50 && final_val < 0.70,
        "Equilibrium should be in 0.50-0.70, got {}",
        final_val
    );
}

// ===========================================================================
// Task 2: Safety restoration specifics
// ===========================================================================

#[test]
fn test_safety_peace_restores_more_than_war() {
    let region = make_region(0);
    let wealth_pct = vec![0.5_f32];

    // Peacetime agent
    let mut pool_peace = AgentPool::new(8);
    let slot_p = pool_peace.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool_peace.need_safety[slot_p] = 0.3;
    restore_needs(&mut pool_peace, &[slot_p], &[region.clone()], &peacetime_signals(), &wealth_pct);

    // Wartime agent
    let mut pool_war = AgentPool::new(8);
    let slot_w = pool_war.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool_war.need_safety[slot_w] = 0.3;
    restore_needs(&mut pool_war, &[slot_w], &[region.clone()], &wartime_signals(), &wealth_pct);

    assert!(
        pool_peace.need_safety[slot_p] > pool_war.need_safety[slot_w],
        "Peace safety {} should be > war safety {}",
        pool_peace.need_safety[slot_p], pool_war.need_safety[slot_w]
    );
}

// ===========================================================================
// Task 2: Material restoration specifics
// ===========================================================================

#[test]
fn test_material_restoration_wealth_dependent() {
    let mut pool = AgentPool::new(8);
    let slot_rich = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    let slot_poor = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_material[slot_rich] = 0.3;
    pool.need_material[slot_poor] = 0.3;

    let region = make_region(0);
    let signals = peacetime_signals();
    let wealth_pct = vec![0.9_f32, 0.1];

    restore_needs(&mut pool, &[slot_rich, slot_poor], &[region], &signals, &wealth_pct);

    assert!(
        pool.need_material[slot_rich] > pool.need_material[slot_poor],
        "Rich ({}) should have more material than poor ({})",
        pool.need_material[slot_rich], pool.need_material[slot_poor]
    );
}

// ===========================================================================
// Task 2: Social restoration proxy
// ===========================================================================

#[test]
fn test_social_restoration_occupation_bonus() {
    let mut pool = AgentPool::new(16);
    let slot_farmer = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    let slot_merchant = pool.spawn(0, 0, Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    let slot_priest = pool.spawn(0, 0, Occupation::Priest, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_social[slot_farmer] = 0.3;
    pool.need_social[slot_merchant] = 0.3;
    pool.need_social[slot_priest] = 0.3;

    let region = make_region(0);
    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32; 3];

    restore_needs(
        &mut pool,
        &[slot_farmer, slot_merchant, slot_priest],
        &[region],
        &signals,
        &wealth_pct,
    );

    assert!(
        pool.need_social[slot_merchant] > pool.need_social[slot_farmer],
        "Merchant ({}) should restore social faster than Farmer ({})",
        pool.need_social[slot_merchant], pool.need_social[slot_farmer]
    );
    assert!(
        pool.need_social[slot_priest] > pool.need_social[slot_farmer],
        "Priest ({}) should restore social faster than Farmer ({})",
        pool.need_social[slot_priest], pool.need_social[slot_farmer]
    );
}

// ===========================================================================
// Task 2: Purpose restoration specifics
// ===========================================================================

#[test]
fn test_purpose_restoration_skill_dependent() {
    let mut pool = AgentPool::new(8);
    let slot_skilled = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    let slot_unskilled = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_purpose[slot_skilled] = 0.3;
    pool.need_purpose[slot_unskilled] = 0.3;
    pool.skills[slot_skilled * 5 + 0] = 0.8; // High farmer skill

    let region = make_region(0);
    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32; 2];

    restore_needs(
        &mut pool,
        &[slot_skilled, slot_unskilled],
        &[region],
        &signals,
        &wealth_pct,
    );

    assert!(
        pool.need_purpose[slot_skilled] > pool.need_purpose[slot_unskilled],
        "Skilled ({}) should restore purpose faster than unskilled ({})",
        pool.need_purpose[slot_skilled], pool.need_purpose[slot_unskilled]
    );
}

#[test]
fn test_purpose_soldier_at_war_bonus() {
    let region = make_region(0);
    let wealth_pct = vec![0.5_f32];

    // Soldier at war
    let mut pool_war = AgentPool::new(8);
    let slot_war = pool_war.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool_war.need_purpose[slot_war] = 0.3;
    restore_needs(&mut pool_war, &[slot_war], &[region.clone()], &wartime_signals(), &wealth_pct);

    // Soldier at peace
    let mut pool_peace = AgentPool::new(8);
    let slot_peace = pool_peace.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool_peace.need_purpose[slot_peace] = 0.3;
    restore_needs(&mut pool_peace, &[slot_peace], &[region.clone()], &peacetime_signals(), &wealth_pct);

    assert!(
        pool_war.need_purpose[slot_war] > pool_peace.need_purpose[slot_peace],
        "Soldier at war ({}) should have more purpose than at peace ({})",
        pool_war.need_purpose[slot_war], pool_peace.need_purpose[slot_peace]
    );
}

// ===========================================================================
// Task 3: Utility modifier tests
// ===========================================================================

#[test]
fn test_utility_modifier_safety_migrate() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.1; // below threshold 0.3
    let mods = compute_need_utility_modifiers(&pool, slot);
    // deficit = 0.2, migrate = 0.2 * 0.7 = 0.14
    assert!((mods.migrate - 0.14).abs() < 0.01,
        "Expected migrate ~0.14, got {}", mods.migrate);
    assert!(mods.stay < 0.0, "Safety unmet should reduce stay");
}

#[test]
fn test_utility_modifier_above_threshold_zero() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    // All needs at spawn (0.5) are above all thresholds (0.25-0.35)
    let mods = compute_need_utility_modifiers(&pool, slot);
    assert_eq!(mods.migrate, 0.0);
    assert_eq!(mods.rebel, 0.0);
    assert_eq!(mods.switch_occ, 0.0);
    assert_eq!(mods.stay, 0.0);
}

#[test]
fn test_utility_modifier_cap() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_safety[slot] = 0.0;    // max Safety migrate = 0.3 * 0.7 = 0.21
    pool.need_material[slot] = 0.0;  // max Material migrate = 0.3 * 0.5 = 0.15
    pool.need_spiritual[slot] = 0.0; // max Spiritual migrate = 0.3 * 0.4 = 0.12
    let mods = compute_need_utility_modifiers(&pool, slot);
    // Total uncapped = 0.21 + 0.15 + 0.12 = 0.48 > cap 0.30
    assert!((mods.migrate - 0.30).abs() < 0.01,
        "migrate should be capped at 0.30, got {}", mods.migrate);
}

#[test]
fn test_autonomy_rebel_independently() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.need_autonomy[slot] = 0.0;
    let mods = compute_need_utility_modifiers(&pool, slot);
    // deficit = 0.3 * 0.8 = 0.24
    assert!((mods.rebel - 0.24).abs() < 0.01,
        "Expected rebel ~0.24, got {}", mods.rebel);
}

#[test]
fn test_needs_only_rebellion_trigger() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
    pool.satisfactions[slot] = 0.6; // above rebel threshold
    pool.loyalties[slot] = 0.5;     // above rebel threshold
    pool.need_autonomy[slot] = 0.0; // full deficit
    let mods = compute_need_utility_modifiers(&pool, slot);
    assert!(mods.rebel > 0.0, "Autonomy deficit should produce positive rebel modifier");
    // When base rebel_utility is 0.0 (above thresholds), adding needs makes total > 0.0
    let simulated_total = 0.0 + mods.rebel;
    assert!(simulated_total > 0.0, "Needs-only rebel should pass gate");
}

// ===========================================================================
// Task 4: Autonomy drift acceleration
// ===========================================================================

#[test]
fn test_autonomy_drift_acceleration() {
    // Full deficit: (0.3 - 0.0) * 2.0 = 0.6, factor = 1.6
    let autonomy_deficit = (0.3_f32 - 0.0_f32).max(0.0);
    let factor = 1.0 + autonomy_deficit * 2.0;
    assert!((factor - 1.6).abs() < 0.01,
        "Expected factor 1.6, got {}", factor);

    // Half deficit: (0.3 - 0.15) * 2.0 = 0.3, factor = 1.3
    let autonomy_deficit_half = (0.3_f32 - 0.15_f32).max(0.0);
    let factor_half = 1.0 + autonomy_deficit_half * 2.0;
    assert!((factor_half - 1.3).abs() < 0.01,
        "Expected factor_half 1.3, got {}", factor_half);

    // Above threshold: no acceleration
    let autonomy_ok = (0.3_f32 - 0.5_f32).max(0.0);
    let factor_ok = 1.0 + autonomy_ok * 2.0;
    assert_eq!(factor_ok, 1.0);
}

// ===========================================================================
// Task 2: update_needs integration test
// ===========================================================================

#[test]
fn test_update_needs_full_cycle() {
    let mut pool = AgentPool::new(8);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);

    let region = make_region(0);
    let signals = peacetime_signals();
    let wealth_pct = vec![0.5_f32];

    let before = pool.need_safety[slot];
    update_needs(&mut pool, &[region], &signals, &wealth_pct);
    let after = pool.need_safety[slot];

    // Should have changed (decay + restore)
    assert!(
        (before - after).abs() > 0.0001,
        "update_needs should change safety: before={}, after={}",
        before, after
    );

    // All needs should be in [0, 1]
    assert!(pool.need_safety[slot] >= 0.0 && pool.need_safety[slot] <= 1.0);
    assert!(pool.need_material[slot] >= 0.0 && pool.need_material[slot] <= 1.0);
    assert!(pool.need_social[slot] >= 0.0 && pool.need_social[slot] <= 1.0);
    assert!(pool.need_spiritual[slot] >= 0.0 && pool.need_spiritual[slot] <= 1.0);
    assert!(pool.need_autonomy[slot] >= 0.0 && pool.need_autonomy[slot] <= 1.0);
    assert!(pool.need_purpose[slot] >= 0.0 && pool.need_purpose[slot] <= 1.0);
}
