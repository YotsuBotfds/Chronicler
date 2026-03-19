//! Macro regression gate: 500-turn timed runs.
//! Run: cargo test --release -p chronicler-agents --test regression -- --ignored --nocapture
//! Targets (9950X): 6K/24 < 3s, 10K/24 < 6s. Report median of 3.

use std::time::Instant;

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: if i % 4 == 2 { 25 } else { 55 },
                is_at_war: i % 3 == 1,
                dominant_faction: (i % 3) as u8,
                faction_military: if i % 3 == 1 { 0.55 } else { 0.25 },
                faction_merchant: if i % 3 == 1 { 0.25 } else { 0.40 },
                faction_cultural: if i % 3 == 1 { 0.20 } else { 0.35 },
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
        contested_regions: (0..num_regions).map(|i| i % 5 == 0).collect(),
    }
}

fn setup_pool(num_agents: usize, num_regions: u16) -> (AgentPool, Vec<RegionState>, TickSignals) {
    let agents_per_region = num_agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if r > 0 { 1u32 << (r - 1) } else { 0 })
                | (if r < num_regions - 1 { 1u32 << (r + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (r % 4) as u8,
        trade_route_count: 0,
        resource_types: [255, 255, 255],
        resource_yields: [0.0, 0.0, 0.0],
        resource_reserves: [1.0, 1.0, 1.0],
        season: 0,
        season_id: 0,
        river_mask: 0,
        endemic_severity: 0.0,
        culture_investment_active: false,
        controller_values: [0xFF, 0xFF, 0xFF],
        conversion_rate: 0.0,
        conversion_target_belief: 0xFF,
        conquest_conversion_active: false,
        majority_belief: 0xFF,
        has_temple: false,
        persecution_intensity: 0.0,
        schism_convert_from: 0xFF,
        schism_convert_to: 0xFF,
        farmer_income_modifier: 1.0,
        food_sufficiency: 1.0,
        merchant_margin: 0.0,
        merchant_trade_income: 0.0,
    }).collect();
    let num_civs = (num_regions.min(8)) as usize;
    let signals = make_signals(num_civs, num_regions as usize);
    let mut pool = AgentPool::new(num_agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16, 0.0, 0.0, 0.0, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        }
    }
    (pool, regions, signals)
}

fn run_500_turns(num_agents: usize, num_regions: u16) -> f64 {
    let (mut pool, regions, signals) = setup_pool(num_agents, num_regions);
    let mut seed = [0u8; 32]; seed[0] = 42;
    let mut percentiles: Vec<f32> = Vec::new();
    let start = Instant::now();
    for turn in 0..500 {
        if percentiles.len() < pool.capacity() {
            percentiles.resize(pool.capacity(), 0.0);
        }
        tick_agents(&mut pool, &regions, &signals, seed, turn, &mut percentiles);
    }
    start.elapsed().as_secs_f64()
}

fn median_of_3(num_agents: usize, num_regions: u16) -> f64 {
    let mut times = [0.0f64; 3];
    for i in 0..3 {
        times[i] = run_500_turns(num_agents, num_regions);
        eprintln!("  run {}: {:.3}s", i + 1, times[i]);
    }
    times.sort_by(|a, b| a.partial_cmp(b).unwrap());
    times[1]
}

#[test]
#[ignore]
fn regression_6k_24r_under_3s() {
    eprintln!("=== 500 turns × 6K agents / 24 regions ===");
    let median = median_of_3(6_000, 24);
    eprintln!("  median: {:.3}s (target: < 3.0s)", median);
    assert!(median < 3.0, "6K/24 median {:.3}s exceeded 3.0s target", median);
}

#[test]
#[ignore]
fn regression_10k_24r_under_6s() {
    eprintln!("=== 500 turns × 10K agents / 24 regions ===");
    let median = median_of_3(10_000, 24);
    eprintln!("  median: {:.3}s (target: < 6.0s)", median);
    assert!(median < 6.0, "10K/24 median {:.3}s exceeded 6.0s target", median);
}
