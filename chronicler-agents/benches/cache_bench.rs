//! Cache efficiency benchmark: packed pool vs scattered pool.
//! Measures tick-time difference to isolate cache-miss impact from fragmentation.

use criterion::{black_box, criterion_group, criterion_main, Criterion, BatchSize};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: 55,
                is_at_war: false,
                dominant_faction: 0,
                faction_military: 0.33,
                faction_merchant: 0.33,
                faction_cultural: 0.34,
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
            })
            .collect(),
        contested_regions: vec![false; num_regions],
    }
}

/// Packed: 10K alive agents contiguous at slots 0..10_000.
fn setup_packed() -> (AgentPool, Vec<RegionState>, TickSignals) {
    let num_regions = 24u16;
    let agents_per_region = 10_000 / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r, terrain: 0, carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16, soil: 0.7, water: 0.5,
        forest_cover: 0.3, adjacency_mask: 0, controller_civ: (r % 4) as u8,
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
    }).collect();
    let signals = make_signals(4, num_regions as usize);
    let mut pool = AgentPool::new(10_000);
    let occs = [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
                Occupation::Scholar, Occupation::Priest];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occs[j % 5], (j % 60) as u16, 0.0, 0.0, 0.0, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        }
    }
    (pool, regions, signals)
}

/// Scattered: 10K alive agents across 15K slots (5K dead gaps).
/// Simulates post-mortality fragmentation (~33% dead).
fn setup_scattered() -> (AgentPool, Vec<RegionState>, TickSignals) {
    let num_regions = 24u16;
    let agents_per_region = 10_000 / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r, terrain: 0, carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16, soil: 0.7, water: 0.5,
        forest_cover: 0.3, adjacency_mask: 0, controller_civ: (r % 4) as u8,
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
    }).collect();
    let signals = make_signals(4, num_regions as usize);
    // Spawn 15K agents, then kill every 3rd to leave 10K alive across 15K slots
    let mut pool = AgentPool::new(15_000);
    let occs = [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
                Occupation::Scholar, Occupation::Priest];
    let total_per_region = 15_000 / num_regions as usize;
    for r in 0..num_regions {
        for j in 0..total_per_region {
            pool.spawn(r, (r % 4) as u8, occs[j % 5], (j % 60) as u16, 0.0, 0.0, 0.0, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        }
    }
    // Kill every 3rd slot to create scattered dead gaps
    for slot in (0..pool.capacity()).step_by(3) {
        if pool.is_alive(slot) {
            pool.kill(slot);
        }
    }
    (pool, regions, signals)
}

fn bench_cache_efficiency(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;
    let mut group = c.benchmark_group("cache_efficiency");

    group.bench_function("packed_10k", |b| {
        b.iter_batched(setup_packed, |(mut pool, regions, signals)| {
            tick_agents(black_box(&mut pool), black_box(&regions), black_box(&signals), seed, 0);
        }, BatchSize::SmallInput)
    });

    group.bench_function("scattered_10k_in_15k", |b| {
        b.iter_batched(setup_scattered, |(mut pool, regions, signals)| {
            tick_agents(black_box(&mut pool), black_box(&regions), black_box(&signals), seed, 0);
        }, BatchSize::SmallInput)
    });

    group.finish();
}

criterion_group!(benches, bench_cache_efficiency);
criterion_main!(benches);
