//! Benchmark: tick performance across agent/region configurations. Target: < 0.5ms on 9950X.
use criterion::{black_box, criterion_group, criterion_main, Criterion, BatchSize};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_default_signals(num_civs: usize, num_regions: usize) -> TickSignals {
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
            })
            .collect(),
        contested_regions: (0..num_regions).map(|i| i % 5 == 0).collect(),
    }
}

fn setup_pool(num_agents: usize, num_regions: u16) -> (AgentPool, Vec<RegionState>, TickSignals) {
    let agents_per_region = num_agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|i| RegionState {
        region_id: i,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if i > 0 { 1u32 << (i - 1) } else { 0 })
                | (if i < num_regions - 1 { 1u32 << (i + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (i % 4) as u8,
        trade_route_count: 0,
    }).collect();
    let num_civs = (num_regions.min(8)) as usize;
    let signals = make_default_signals(num_civs, num_regions as usize);
    let mut pool = AgentPool::new(num_agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16);
        }
    }
    (pool, regions, signals)
}

fn setup_6k_pool() -> (AgentPool, Vec<RegionState>, TickSignals) {
    setup_pool(6000, 24)
}

fn bench_tick_matrix(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;

    let configs: &[(usize, u16, &str)] = &[
        (6_000,  24, "6k_24r"),
        (10_000, 24, "10k_24r"),
        (10_000, 40, "10k_40r"),
        (15_000, 40, "15k_40r"),
        (10_000, 10, "10k_10r_stress"),
    ];

    let mut group = c.benchmark_group("tick_matrix");
    for &(agents, regions, label) in configs {
        group.bench_function(label, |b| {
            b.iter_batched(
                || setup_pool(agents, regions),
                |(mut pool, regs, sigs)| {
                    tick_agents(
                        black_box(&mut pool),
                        black_box(&regs),
                        black_box(&sigs),
                        seed,
                        0,
                    );
                },
                BatchSize::SmallInput,
            )
        });
    }
    group.finish();
}

fn bench_arrow_ffi(c: &mut Criterion) {
    let (pool, _, _) = setup_pool(10_000, 24);
    c.bench_function("arrow_snapshot_10k", |b| {
        b.iter(|| {
            let _ = black_box(pool.to_record_batch().unwrap());
        })
    });
}

criterion_group!(benches, bench_tick_matrix, bench_arrow_ffi);
criterion_main!(benches);
