use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_test_regions() -> Vec<RegionState> {
    (0..5)
        .map(|i| RegionState {
            region_id: i,
            terrain: 0,
            carrying_capacity: 60,
            population: 60,
            soil: 0.5 + (i as f32) * 0.1,
            water: 0.4 + (i as f32) * 0.05,
            forest_cover: 0.3,
            adjacency_mask: 0,
            controller_civ: 255,
            trade_route_count: 0,
        })
        .collect()
}

fn make_default_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: if i == 2 { 20 } else { 55 },
                is_at_war: i == 1 || i == 3,
                dominant_faction: (i % 3) as u8,
                faction_military: if i == 1 { 0.60 } else { 0.25 },
                faction_merchant: if i == 1 { 0.20 } else { 0.40 },
                faction_cultural: if i == 1 { 0.20 } else { 0.35 },
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
            })
            .collect(),
        contested_regions: (0..num_regions).map(|i| i == 1 || i == 3).collect(),
    }
}

fn make_test_pool(regions: &[RegionState]) -> AgentPool {
    let mut pool = AgentPool::new(0);
    for r in regions {
        for _ in 0..r.carrying_capacity {
            pool.spawn(r.region_id, r.region_id as u8, Occupation::Farmer, 0, 0.0, 0.0, 0.0);
        }
    }
    pool
}

fn run_simulation(seed: [u8; 32], turns: u32) -> (usize, Vec<u16>) {
    let regions = make_test_regions();
    let signals = make_default_signals(5, 5);
    let mut pool = make_test_pool(&regions);
    for turn in 0..turns {
        tick_agents(&mut pool, &regions, &signals, seed, turn);
    }
    let batch = pool.to_record_batch().unwrap();
    let ages_col = batch
        .column(8)
        .as_any()
        .downcast_ref::<arrow::array::UInt16Array>()
        .unwrap();
    let ages: Vec<u16> = (0..ages_col.len()).map(|i| ages_col.value(i)).collect();
    (pool.alive_count(), ages)
}

#[test]
fn test_determinism_same_seed() {
    let mut seed = [0u8; 32];
    seed[0] = 42;
    let (a, ages_a) = run_simulation(seed, 20);
    let (b, ages_b) = run_simulation(seed, 20);
    assert_eq!(a, b);
    assert_eq!(ages_a, ages_b);
}

#[test]
fn test_determinism_different_seeds() {
    let mut sa = [0u8; 32];
    sa[0] = 42;
    let mut sb = [0u8; 32];
    sb[0] = 99;
    assert_ne!(run_simulation(sa, 20).0, run_simulation(sb, 20).0);
}

#[test]
fn test_determinism_across_thread_counts() {
    let mut seed = [0u8; 32];
    seed[0] = 77;
    let mut results = Vec::new();
    for threads in [1, 4, 16] {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        let result = pool.install(|| run_simulation(seed, 30));
        results.push(result);
    }
    for i in 1..results.len() {
        assert_eq!(results[0].0, results[i].0);
        assert_eq!(results[0].1, results[i].1);
    }
}
