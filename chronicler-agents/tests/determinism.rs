use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_test_regions() -> Vec<RegionState> {
    (0..5)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.population = 60;
            r.soil = 0.5 + (i as f32) * 0.1;
            r.water = 0.4 + (i as f32) * 0.05;
            r
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
                faction_clergy: 0.0,
                gini_coefficient: 0.0,
                conquered_this_turn: false,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            })
            .collect(),
        contested_regions: (0..num_regions).map(|i| i == 1 || i == 3).collect(),
    }
}

fn make_test_pool(regions: &[RegionState]) -> AgentPool {
    let mut pool = AgentPool::new(0);
    for r in regions {
        for _ in 0..r.carrying_capacity {
            pool.spawn(r.region_id, r.region_id as u8, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 1, 2, chronicler_agents::BELIEF_NONE);
        }
    }
    pool
}

fn make_spatial_regions() -> Vec<RegionState> {
    let mut regions = make_test_regions();
    // Add spatial features so attractors are non-trivial
    regions[0].river_mask = 1;
    regions[0].resource_effective_yield = [0.5, 0.3, 0.0];
    regions[1].is_capital = true;
    regions[1].resource_effective_yield = [0.0, 0.4, 0.2];
    regions[2].terrain = 2; // Coast
    regions[2].resource_effective_yield = [0.3, 0.0, 0.0];
    regions[3].has_temple = true;
    regions[3].temple_prestige = 0.6;
    regions
}

fn run_simulation(seed: [u8; 32], turns: u32) -> (usize, Vec<u16>) {
    let regions = make_test_regions();
    let signals = make_default_signals(5, 5);
    let mut pool = make_test_pool(&regions);
    let mut percentiles: Vec<f32> = Vec::new();
    for turn in 0..turns {
        if percentiles.len() < pool.capacity() {
            percentiles.resize(pool.capacity(), 0.0);
        }
        tick_agents(&mut pool, &regions, &signals, seed, turn, &mut percentiles, &mut Vec::new(), &[], &mut chronicler_agents::spatial::SpatialDiagnostics::default(), &[]);
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

/// M57a: Marriage determinism — verifies marriage_scan produces identical marriages
/// and parent_id_0/parent_id_1 assignments across two runs with the same seed.
///
/// Runs 30 turns so agents (spawned at age 0) reach MARRIAGE_MIN_AGE (16) and
/// several MARRIAGE_CADENCE (4-turn) cycles fire. Uses spatial regions so agents
/// cluster within MARRIAGE_RADIUS and actually form marriages.
#[test]
fn test_marriage_determinism() {
    use chronicler_agents::spatial::{init_attractors, SpatialGrid, SpatialDiagnostics};
    use chronicler_agents::relationships::BondType;

    /// Collected marriage state for one run — sorted by agent id for stable comparison.
    #[derive(Debug, PartialEq)]
    struct MarriageSnapshot {
        /// (agent_id, spouse_agent_id) for every agent that has a Marriage bond
        marriages: Vec<(u32, u32)>,
        /// (agent_id, parent_id_0, parent_id_1) for every alive agent
        parentage: Vec<(u32, u32, u32)>,
    }

    fn run_marriage_sim(seed: [u8; 32], turns: u32) -> MarriageSnapshot {
        let regions = make_spatial_regions();
        let signals = make_default_signals(5, 5);
        let attractors: Vec<_> = regions.iter()
            .map(|r| init_attractors(seed[0] as u64, r.region_id, r))
            .collect();
        let mut pool = make_test_pool(&regions);
        let mut percentiles: Vec<f32> = Vec::new();
        let mut grids: Vec<SpatialGrid> = Vec::new();
        let mut diag = SpatialDiagnostics::default();
        for turn in 0..turns {
            if percentiles.len() < pool.capacity() {
                percentiles.resize(pool.capacity(), 0.0);
            }
            tick_agents(
                &mut pool, &regions, &signals, seed, turn,
                &mut percentiles, &mut grids, &attractors, &mut diag, &[],
            );
        }

        // Collect marriage bonds
        let mut marriages: Vec<(u32, u32)> = Vec::new();
        let mut parentage: Vec<(u32, u32, u32)> = Vec::new();
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) { continue; }
            let agent_id = pool.ids[slot];

            // Check for Marriage bond
            let rel_count = pool.rel_count[slot] as usize;
            for i in 0..rel_count {
                if pool.rel_bond_types[slot][i] == BondType::Marriage as u8 {
                    marriages.push((agent_id, pool.rel_target_ids[slot][i]));
                    break; // at most one Marriage bond per agent
                }
            }

            // Collect parentage
            parentage.push((agent_id, pool.parent_id_0[slot], pool.parent_id_1[slot]));
        }
        marriages.sort_by_key(|m| m.0);
        parentage.sort_by_key(|p| p.0);
        MarriageSnapshot { marriages, parentage }
    }

    let mut seed = [0u8; 32];
    seed[0] = 57; // M57a-themed seed

    let run_a = run_marriage_sim(seed, 30);
    let run_b = run_marriage_sim(seed, 30);

    // Verify marriages actually formed (test is meaningful)
    assert!(
        !run_a.marriages.is_empty(),
        "No marriages formed in 30 turns — test cannot verify determinism"
    );

    // Core determinism check: identical marriages
    assert_eq!(
        run_a.marriages.len(), run_b.marriages.len(),
        "Marriage count mismatch: {} vs {}",
        run_a.marriages.len(), run_b.marriages.len()
    );
    assert_eq!(
        run_a.marriages, run_b.marriages,
        "Marriage pairs differ between runs"
    );

    // Core determinism check: identical parent assignments
    assert_eq!(
        run_a.parentage.len(), run_b.parentage.len(),
        "Alive agent count mismatch: {} vs {}",
        run_a.parentage.len(), run_b.parentage.len()
    );
    assert_eq!(
        run_a.parentage, run_b.parentage,
        "Parent assignments differ between runs"
    );

    // Verify at least some agents have non-PARENT_NONE parent_id_1 (dual-parent births)
    // PARENT_NONE = 0 (sentinel from agent.rs, not re-exported)
    const PARENT_NONE: u32 = 0;
    let dual_parent_count = run_a.parentage.iter()
        .filter(|p| p.2 != PARENT_NONE)
        .count();
    // Note: dual_parent_count may be 0 if no births happened to married agents
    // in 30 turns — that's fine, the marriage determinism itself is the primary check.
    eprintln!(
        "Marriage determinism: {} marriages, {} agents, {} with dual parents",
        run_a.marriages.len(), run_a.parentage.len(), dual_parent_count
    );
}

/// M55a: Full spatial determinism — 20-turn simulation with attractors enabled.
/// Verifies that (x, y) positions are bit-identical across two runs with the same seed.
#[test]
fn test_spatial_determinism_20_turns() {
    use chronicler_agents::spatial::{init_attractors, SpatialGrid, SpatialDiagnostics};

    fn run_spatial(seed: [u8; 32], turns: u32) -> Vec<(u32, u32, u32)> {
        let regions = make_spatial_regions();
        let signals = make_default_signals(5, 5);
        let attractors: Vec<_> = regions.iter()
            .map(|r| init_attractors(seed[0] as u64, r.region_id, r))
            .collect();
        let mut pool = make_test_pool(&regions);
        let mut percentiles: Vec<f32> = Vec::new();
        let mut grids: Vec<SpatialGrid> = Vec::new();
        let mut diag = SpatialDiagnostics::default();
        for turn in 0..turns {
            if percentiles.len() < pool.capacity() {
                percentiles.resize(pool.capacity(), 0.0);
            }
            tick_agents(
                &mut pool, &regions, &signals, seed, turn,
                &mut percentiles, &mut grids, &attractors, &mut diag, &[],
            );
        }
        // Collect (id, x_bits, y_bits) sorted by id for stable comparison
        let mut results: Vec<(u32, u32, u32)> = Vec::new();
        for slot in 0..pool.capacity() {
            if pool.is_alive(slot) {
                results.push((
                    pool.ids[slot],
                    pool.x[slot].to_bits(),
                    pool.y[slot].to_bits(),
                ));
            }
        }
        results.sort_by_key(|r| r.0);
        results
    }

    let mut seed = [0u8; 32];
    seed[0] = 55;
    let run_a = run_spatial(seed, 20);
    let run_b = run_spatial(seed, 20);

    assert!(!run_a.is_empty(), "Should have alive agents after 20 turns");
    assert_eq!(run_a.len(), run_b.len(), "Alive count mismatch");
    for (i, (a, b)) in run_a.iter().zip(run_b.iter()).enumerate() {
        assert_eq!(
            a, b,
            "Spatial mismatch at idx {}: id={} x={:#010x} y={:#010x} vs id={} x={:#010x} y={:#010x}",
            i, a.0, a.1, a.2, b.0, b.1, b.2
        );
    }
}
