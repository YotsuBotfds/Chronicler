//! Benchmark: 6K agents x 1 tick. Target: < 0.5ms on 9950X.
use criterion::{black_box, criterion_group, criterion_main, Criterion, BatchSize};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_default_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: 50,
                is_at_war: false,
                dominant_faction: 0,
                faction_military: 0.33,
                faction_merchant: 0.33,
                faction_cultural: 0.34,
            })
            .collect(),
        contested_regions: vec![false; num_regions],
    }
}

fn setup_6k_pool() -> (AgentPool, Vec<RegionState>, TickSignals) {
    let regions: Vec<RegionState> = (0..24u16).map(|i| RegionState {
        region_id: i, terrain: 0, carrying_capacity: 250, population: 250,
        soil: 0.7, water: 0.5, forest_cover: 0.3,
        adjacency_mask: 0, controller_civ: 255, trade_route_count: 0,
    }).collect();
    let signals = make_default_signals(1, 24);
    let mut pool = AgentPool::new(6000);
    for r in &regions { for _ in 0..250 { pool.spawn(r.region_id, 0, Occupation::Farmer, 0); } }
    (pool, regions, signals)
}

fn bench_tick_6k(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;
    c.bench_function("tick_6k_agents", |b| {
        b.iter_batched(setup_6k_pool, |(mut pool, regions, signals)| {
            tick_agents(black_box(&mut pool), black_box(&regions), black_box(&signals), seed, 0);
        }, BatchSize::SmallInput)
    });
}

criterion_group!(benches, bench_tick_6k);
criterion_main!(benches);
