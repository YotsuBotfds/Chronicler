//! H-38: Integration tests for culture_tick and conversion_tick through
//! the public AgentSimulator / tick_agents API.
//!
//! Tests exercise cultural drift and belief conversion at the full-tick level
//! (not the internal per-region functions), verifying that the stages fire
//! correctly and produce deterministic outcomes.

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn make_test_regions(num: usize) -> Vec<RegionState> {
    (0..num)
        .map(|i| {
            let mut r = RegionState::new(i as u16);
            r.population = 60;
            r.soil = 0.7;
            r.water = 0.6;
            r.controller_civ = 0;
            r.carrying_capacity = 120;
            // Set resource types so culture_tick environmental bias fires
            r.resource_types = [5, 255, 255]; // ORE → Honor/Order bias
            r
        })
        .collect()
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

fn make_pool_with_uniform_culture(regions: &[RegionState], value: [u8; 3], belief: u8) -> AgentPool {
    let mut pool = AgentPool::new(0);
    for r in regions {
        for _ in 0..40 {
            pool.spawn(
                r.region_id, r.controller_civ, Occupation::Farmer,
                25, 0.5, 0.5, 0.5, value[0], value[1], value[2], belief,
            );
        }
    }
    pool
}

fn run_ticks(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    seed: [u8; 32],
    turns: u32,
) {
    let mut percentiles: Vec<f32> = Vec::new();
    for turn in 0..turns {
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
// Culture drift tests
// ---------------------------------------------------------------------------

/// Culture drift should produce measurable change over many turns.
/// Starting with all agents holding the same values, environmental bias from
/// ORE regions (Honor/Order) should cause some agents to adopt Honor or Order
/// as the ORE environment pushes those values.
#[test]
fn test_culture_drift_produces_change() {
    let regions = make_test_regions(2);
    let signals = make_signals(1, 2);
    let mut seed = [0u8; 32];
    seed[0] = 36;

    // Start with all agents having Freedom/Knowledge/Tradition (0, 3, 2)
    // ORE environment biases toward Honor(4) and Order(1)
    let mut pool = make_pool_with_uniform_culture(&regions, [0, 3, 2], chronicler_agents::BELIEF_NONE);

    let initial_count = pool.alive_count();
    assert!(initial_count > 0, "Must have agents to test culture drift");

    // Snapshot initial cultural values
    let initial_honor_count: usize = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .filter(|&s| {
            pool.cultural_value_0[s] == 4
                || pool.cultural_value_1[s] == 4
                || pool.cultural_value_2[s] == 4
        })
        .count();
    assert_eq!(initial_honor_count, 0, "No agents should start with Honor(4)");

    // Run many turns to allow drift
    run_ticks(&mut pool, &regions, &signals, seed, 50);

    // After 50 turns of ORE-biased drift, some agents should have adopted Honor(4)
    let final_honor_count: usize = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .filter(|&s| {
            pool.cultural_value_0[s] == 4
                || pool.cultural_value_1[s] == 4
                || pool.cultural_value_2[s] == 4
        })
        .count();

    assert!(
        final_honor_count > 0,
        "Expected some agents to drift toward Honor after 50 turns in ORE region, got 0"
    );
}

/// Culture drift is deterministic: same seed → same cultural outcomes.
#[test]
fn test_culture_drift_determinism() {
    let regions = make_test_regions(2);
    let signals = make_signals(1, 2);
    let mut seed = [0u8; 32];
    seed[0] = 37;

    fn collect_culture(pool: &AgentPool) -> Vec<(u8, u8, u8)> {
        let mut result: Vec<(u8, u8, u8)> = Vec::new();
        for s in 0..pool.capacity() {
            if pool.is_alive(s) {
                result.push((
                    pool.cultural_value_0[s],
                    pool.cultural_value_1[s],
                    pool.cultural_value_2[s],
                ));
            }
        }
        result
    }

    let mut pool_a = make_pool_with_uniform_culture(&regions, [0, 3, 2], chronicler_agents::BELIEF_NONE);
    run_ticks(&mut pool_a, &regions, &signals, seed, 30);
    let culture_a = collect_culture(&pool_a);

    let mut pool_b = make_pool_with_uniform_culture(&regions, [0, 3, 2], chronicler_agents::BELIEF_NONE);
    run_ticks(&mut pool_b, &regions, &signals, seed, 30);
    let culture_b = collect_culture(&pool_b);

    assert_eq!(culture_a.len(), culture_b.len(), "Alive count mismatch");
    assert_eq!(culture_a, culture_b, "Cultural values differ between runs with same seed");
}

/// Elevated cultural_drift_multiplier should accelerate drift.
#[test]
fn test_elevated_drift_multiplier_accelerates() {
    let regions = make_test_regions(1);
    let mut seed = [0u8; 32];
    seed[0] = 38;

    fn count_drifted(pool: &AgentPool) -> usize {
        (0..pool.capacity())
            .filter(|&s| pool.is_alive(s))
            .filter(|&s| {
                pool.cultural_value_0[s] != 0
                    || pool.cultural_value_1[s] != 3
                    || pool.cultural_value_2[s] != 2
            })
            .count()
    }

    // Run with 1.0 multiplier
    let signals_1x = make_signals(1, 1);
    let mut pool_1x = make_pool_with_uniform_culture(&regions, [0, 3, 2], chronicler_agents::BELIEF_NONE);
    run_ticks(&mut pool_1x, &regions, &signals_1x, seed, 20);
    let drifted_1x = count_drifted(&pool_1x);

    // Run with 3.0 multiplier
    let mut signals_3x = make_signals(1, 1);
    signals_3x.civs[0].cultural_drift_multiplier = 3.0;
    let mut pool_3x = make_pool_with_uniform_culture(&regions, [0, 3, 2], chronicler_agents::BELIEF_NONE);
    run_ticks(&mut pool_3x, &regions, &signals_3x, seed, 20);
    let drifted_3x = count_drifted(&pool_3x);

    assert!(
        drifted_3x > drifted_1x,
        "3x drift multiplier should produce more drifted agents ({}) than 1x ({})",
        drifted_3x, drifted_1x
    );
}

// ---------------------------------------------------------------------------
// Conversion tick tests
// ---------------------------------------------------------------------------

/// Conversion tick should convert agents when conversion_rate > 0.
#[test]
fn test_conversion_produces_belief_changes() {
    let mut regions = make_test_regions(1);
    regions[0].conversion_rate = 0.5;
    regions[0].conversion_target_belief = 5;

    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 39;

    // All agents start with belief 1
    let mut pool = make_pool_with_uniform_culture(&regions, [0, 3, 2], 1);
    let initial_count = pool.alive_count();
    assert!(initial_count > 0);

    run_ticks(&mut pool, &regions, &signals, seed, 5);

    let converted: usize = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.beliefs[s] == 5)
        .count();

    assert!(
        converted > 0,
        "Expected some agents to convert to belief 5 with rate=0.5 after 5 turns"
    );
}

/// Conversion tick is deterministic.
#[test]
fn test_conversion_determinism() {
    let mut regions = make_test_regions(1);
    regions[0].conversion_rate = 0.3;
    regions[0].conversion_target_belief = 7;

    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 40;

    fn collect_beliefs(pool: &AgentPool) -> Vec<u8> {
        (0..pool.capacity())
            .filter(|&s| pool.is_alive(s))
            .map(|s| pool.beliefs[s])
            .collect()
    }

    let mut pool_a = make_pool_with_uniform_culture(&regions, [0, 3, 2], 2);
    run_ticks(&mut pool_a, &regions, &signals, seed, 10);
    let beliefs_a = collect_beliefs(&pool_a);

    let mut pool_b = make_pool_with_uniform_culture(&regions, [0, 3, 2], 2);
    run_ticks(&mut pool_b, &regions, &signals, seed, 10);
    let beliefs_b = collect_beliefs(&pool_b);

    assert_eq!(beliefs_a.len(), beliefs_b.len(), "Alive count mismatch");
    assert_eq!(beliefs_a, beliefs_b, "Belief outcomes differ between runs with same seed");
}

/// No conversion should occur when rate=0 and conquest=false.
#[test]
fn test_no_conversion_with_zero_rate() {
    let regions = make_test_regions(1);
    // Default: conversion_rate=0.0, conquest_conversion_active=false
    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 41;

    let mut pool = make_pool_with_uniform_culture(&regions, [0, 3, 2], 3);
    run_ticks(&mut pool, &regions, &signals, seed, 10);

    let unconverted: usize = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.beliefs[s] == 3)
        .count();
    let alive = pool.alive_count();

    assert_eq!(
        unconverted, alive,
        "All agents should retain belief 3 when conversion rate is 0"
    );
}

/// Conquest conversion should fire at ~30% rate.
#[test]
fn test_conquest_conversion_statistical() {
    let mut regions = make_test_regions(1);
    regions[0].conquest_conversion_active = true;
    regions[0].conversion_target_belief = 9;
    regions[0].population = 200;
    regions[0].carrying_capacity = 300;

    let signals = make_signals(1, 1);
    let mut seed = [0u8; 32];
    seed[0] = 42;

    // Spawn many agents for statistical check
    let mut pool = AgentPool::new(0);
    for _ in 0..200 {
        pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 3, 2, 1);
    }

    // Run just 1 turn to see conquest conversion in action
    let mut percentiles: Vec<f32> = vec![0.0; pool.capacity()];
    tick_agents(
        &mut pool, &regions, &signals, seed, 0,
        &mut percentiles, &mut Vec::new(), &[], &mut SpatialDiagnostics::default(),
        &[], None,
    );

    let converted: usize = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.beliefs[s] == 9)
        .count();
    let alive = pool.alive_count();
    let rate = converted as f32 / alive as f32;

    assert!(
        (rate - 0.30).abs() < 0.10,
        "Conquest conversion rate {:.3} should be ~0.30 ±0.10 (converted={}, alive={})",
        rate, converted, alive
    );
}
