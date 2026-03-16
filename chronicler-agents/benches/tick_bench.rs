//! Benchmark: 6K agents x 1 tick. Target: < 0.5ms on 9950X.
use criterion::{black_box, criterion_group, criterion_main, Criterion, BatchSize};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};

fn setup_6k_pool() -> (AgentPool, Vec<RegionState>) {
    let regions: Vec<RegionState> = (0..24u16).map(|i| RegionState {
        region_id: i, terrain: 0, carrying_capacity: 250, population: 250,
        soil: 0.7, water: 0.5, forest_cover: 0.3,
    }).collect();
    let mut pool = AgentPool::new(6000);
    for r in &regions { for _ in 0..250 { pool.spawn(r.region_id, 0, Occupation::Farmer, 0); } }
    (pool, regions)
}

fn bench_tick_6k(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;
    c.bench_function("tick_6k_agents", |b| {
        b.iter_batched(setup_6k_pool, |(mut pool, regions)| {
            tick_agents(black_box(&mut pool), black_box(&regions), seed, 0);
        }, BatchSize::SmallInput)
    });
}

criterion_group!(benches, bench_tick_6k);
criterion_main!(benches);
