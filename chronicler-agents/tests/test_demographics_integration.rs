//! H-39: Integration tests for demographics (age-dependent mortality,
//! ecology-sensitive fertility) through the public tick_agents API.
//!
//! Verifies that:
//! - Fertility produces population growth under good conditions
//! - Mortality reduces population (especially elderly agents)
//! - Ecology affects fertility rates
//! - Determinism: same seed → same demographic outcomes

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn make_region(id: u16, soil: f32, water: f32, capacity: u16) -> RegionState {
    let mut r = RegionState::new(id);
    r.soil = soil;
    r.water = water;
    r.carrying_capacity = capacity;
    r.population = 0; // Will be set after spawning
    r.controller_civ = 0;
    r
}

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: 55,
                is_at_war: false,
                dominant_faction: 0,
                faction_military: 0.25,
                faction_merchant: 0.25,
                faction_cultural: 0.25,
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
                faction_clergy: 0.0,
                gini_coefficient: 0.0,
                conquered_this_turn: false,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            })
            .collect(),
        contested_regions: vec![false; num_regions],
    }
}

fn run_ticks(
    pool: &mut AgentPool,
    regions: &mut [RegionState],
    signals: &TickSignals,
    seed: [u8; 32],
    turns: u32,
) {
    let mut percentiles: Vec<f32> = Vec::new();
    for turn in 0..turns {
        // Sync population count into regions
        for r in regions.iter_mut() {
            let pop: u16 = (0..pool.capacity())
                .filter(|&s| pool.is_alive(s) && pool.regions[s] == r.region_id)
                .count() as u16;
            r.population = pop;
        }
        if percentiles.len() < pool.capacity() {
            percentiles.resize(pool.capacity(), 0.0);
        }
        tick_agents(
            pool, regions, signals, seed, turn,
            &mut percentiles, &mut Vec::new(), &[], &mut SpatialDiagnostics::default(),
            &[], None,
        );
    }
}

// ---------------------------------------------------------------------------
// Fertility tests
// ---------------------------------------------------------------------------

/// Young adults with good satisfaction and healthy ecology should reproduce.
#[test]
fn test_fertility_produces_growth() {
    let mut regions = vec![make_region(0, 0.8, 0.7, 200)];
    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 50;

    // Spawn fertile-age farmers with good satisfaction
    let mut pool = AgentPool::new(0);
    for _ in 0..30 {
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        pool.satisfactions[slot] = 0.7; // Above fertility threshold
    }
    regions[0].population = 30;

    let initial_alive = pool.alive_count();
    run_ticks(&mut pool, &mut regions, &signals, seed, 20);
    let final_alive = pool.alive_count();

    assert!(
        final_alive > initial_alive,
        "Expected population growth: started at {}, ended at {} after 20 turns",
        initial_alive, final_alive
    );
}

/// Elderly agents should die at a higher rate than young agents.
/// Compare two cohorts under identical conditions — elderly should have
/// fewer original survivors (tracking by agent ID, ignoring births).
#[test]
fn test_elderly_mortality() {
    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 51;

    // Elderly cohort: age 70 — collect their IDs
    let mut regions_old = vec![make_region(0, 0.8, 0.7, 200)];
    let mut pool_old = AgentPool::new(0);
    let mut old_ids: Vec<u32> = Vec::new();
    for _ in 0..50 {
        let slot = pool_old.spawn(0, 0, Occupation::Farmer, 70, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        old_ids.push(pool_old.ids[slot]);
    }
    regions_old[0].population = 50;
    run_ticks(&mut pool_old, &mut regions_old, &signals, seed, 10);
    // Count how many of the original elderly survived
    let old_survivors: usize = (0..pool_old.capacity())
        .filter(|&s| pool_old.is_alive(s) && old_ids.contains(&pool_old.ids[s]))
        .count();

    // Young cohort: age 20 — collect their IDs
    let mut regions_young = vec![make_region(0, 0.8, 0.7, 200)];
    let mut pool_young = AgentPool::new(0);
    let mut young_ids: Vec<u32> = Vec::new();
    for _ in 0..50 {
        let slot = pool_young.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        young_ids.push(pool_young.ids[slot]);
    }
    regions_young[0].population = 50;
    run_ticks(&mut pool_young, &mut regions_young, &signals, seed, 10);
    let young_survivors: usize = (0..pool_young.capacity())
        .filter(|&s| pool_young.is_alive(s) && young_ids.contains(&pool_young.ids[s]))
        .count();

    assert!(
        old_survivors < young_survivors,
        "Elderly should have fewer original survivors ({}) than young ({}) after 10 turns",
        old_survivors, young_survivors
    );
}

/// Young agents should survive at a much higher rate than elderly.
#[test]
fn test_age_dependent_mortality_differential() {
    let signals = make_signals(1, 2);
    let mut seed = [0u8; 32];
    seed[0] = 52;

    // Young cohort
    let mut regions_young = vec![make_region(0, 0.8, 0.7, 200)];
    let mut pool_young = AgentPool::new(0);
    for _ in 0..50 {
        pool_young.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
    }
    regions_young[0].population = 50;
    run_ticks(&mut pool_young, &mut regions_young, &signals, seed, 15);
    let young_survivors = pool_young.alive_count();

    // Elderly cohort
    let mut regions_elder = vec![make_region(0, 0.8, 0.7, 200)];
    let mut pool_elder = AgentPool::new(0);
    for _ in 0..50 {
        pool_elder.spawn(0, 0, Occupation::Farmer, 65, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
    }
    regions_elder[0].population = 50;
    run_ticks(&mut pool_elder, &mut regions_elder, &signals, seed, 15);
    let elder_survivors = pool_elder.alive_count();

    assert!(
        young_survivors > elder_survivors,
        "Young agents ({} survived) should survive better than elderly ({} survived)",
        young_survivors, elder_survivors
    );
}

// ---------------------------------------------------------------------------
// Ecology effect on fertility
// ---------------------------------------------------------------------------

/// Poor soil should suppress fertility compared to good soil.
#[test]
fn test_ecology_affects_fertility() {
    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 53;

    // Good soil cohort
    let mut regions_good = vec![make_region(0, 0.9, 0.8, 200)];
    let mut pool_good = AgentPool::new(0);
    for _ in 0..30 {
        let slot = pool_good.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        pool_good.satisfactions[slot] = 0.7;
    }
    regions_good[0].population = 30;
    run_ticks(&mut pool_good, &mut regions_good, &signals, seed, 25);
    let pop_good_soil = pool_good.alive_count();

    // Poor soil cohort
    let mut regions_poor = vec![make_region(0, 0.1, 0.1, 200)];
    let mut pool_poor = AgentPool::new(0);
    for _ in 0..30 {
        let slot = pool_poor.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        pool_poor.satisfactions[slot] = 0.7;
    }
    regions_poor[0].population = 30;
    run_ticks(&mut pool_poor, &mut regions_poor, &signals, seed, 25);
    let pop_poor_soil = pool_poor.alive_count();

    assert!(
        pop_good_soil > pop_poor_soil,
        "Good soil ({}) should produce more population than poor soil ({})",
        pop_good_soil, pop_poor_soil
    );
}

// ---------------------------------------------------------------------------
// Determinism
// ---------------------------------------------------------------------------

/// Same seed, same initial state → identical demographic outcomes.
#[test]
fn test_demographics_determinism() {
    let _signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 54;

    fn run_demo(seed: [u8; 32]) -> (usize, Vec<u16>) {
        let mut regions = vec![make_region(0, 0.7, 0.6, 150)];
        let signals = make_signals(1, 1);
        let mut pool = AgentPool::new(0);
        for _ in 0..40 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
            pool.satisfactions[slot] = 0.65;
        }
        regions[0].population = 40;

        let mut percentiles: Vec<f32> = Vec::new();
        for turn in 0..20u32 {
            // Sync population
            regions[0].population = (0..pool.capacity())
                .filter(|&s| pool.is_alive(s) && pool.regions[s] == 0)
                .count() as u16;
            if percentiles.len() < pool.capacity() {
                percentiles.resize(pool.capacity(), 0.0);
            }
            tick_agents(
                &mut pool, &regions, &signals, seed, turn,
                &mut percentiles, &mut Vec::new(), &[], &mut SpatialDiagnostics::default(),
                &[], None,
            );
        }

        // Collect ages of alive agents sorted by id
        let mut ages: Vec<(u32, u16)> = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s))
            .map(|s| (pool.ids[s], pool.ages[s]))
            .collect();
        ages.sort_by_key(|a| a.0);
        let alive = pool.alive_count();
        let age_vec: Vec<u16> = ages.iter().map(|a| a.1).collect();
        (alive, age_vec)
    }

    let (alive_a, ages_a) = run_demo(seed);
    let (alive_b, ages_b) = run_demo(seed);

    assert_eq!(alive_a, alive_b, "Alive count mismatch");
    assert_eq!(ages_a, ages_b, "Age distributions differ between runs");
}

/// War mortality should be elevated for soldiers.
/// Compare soldiers at war vs soldiers at peace (same seed), tracking original
/// agent survival by ID to isolate mortality from births.
/// Uses large sample (500 agents) and long simulation (40 turns) since
/// MORTALITY_ADULT is 0.0025 and WAR_CASUALTY_MULTIPLIER is 2.0x.
#[test]
fn test_war_mortality_soldiers() {
    let mut seed = [0u8; 32];
    seed[0] = 55;
    let n = 500;
    let turns = 40;

    // At-war cohort
    let mut regions_war = vec![make_region(0, 0.8, 0.7, 2000)];
    let mut signals_war = make_signals(1, 1);
    signals_war.civs[0].is_at_war = true;
    signals_war.contested_regions[0] = true;

    let mut pool_war = AgentPool::new(0);
    let mut war_ids: Vec<u32> = Vec::new();
    for _ in 0..n {
        let slot = pool_war.spawn(0, 0, Occupation::Soldier, 30, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        war_ids.push(pool_war.ids[slot]);
    }
    regions_war[0].population = n as u16;
    run_ticks(&mut pool_war, &mut regions_war, &signals_war, seed, turns);
    let war_survivors: usize = (0..pool_war.capacity())
        .filter(|&s| pool_war.is_alive(s) && war_ids.contains(&pool_war.ids[s]))
        .count();

    // At-peace cohort
    let mut regions_peace = vec![make_region(0, 0.8, 0.7, 2000)];
    let signals_peace = make_signals(1, 1); // is_at_war=false by default

    let mut pool_peace = AgentPool::new(0);
    let mut peace_ids: Vec<u32> = Vec::new();
    for _ in 0..n {
        let slot = pool_peace.spawn(0, 0, Occupation::Soldier, 30, 0.5, 0.5, 0.5, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        peace_ids.push(pool_peace.ids[slot]);
    }
    regions_peace[0].population = n as u16;
    run_ticks(&mut pool_peace, &mut regions_peace, &signals_peace, seed, turns);
    let peace_survivors: usize = (0..pool_peace.capacity())
        .filter(|&s| pool_peace.is_alive(s) && peace_ids.contains(&pool_peace.ids[s]))
        .count();

    assert!(
        war_survivors < peace_survivors,
        "Soldiers at war should have fewer survivors ({}) than at peace ({}) after {} turns with {} agents",
        war_survivors, peace_survivors, turns, n
    );
}
