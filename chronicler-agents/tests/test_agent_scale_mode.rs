//! Agent-scale mode: exact mode must reproduce the reference algorithms bit
//! for bit; fast mode must stay deterministic and form comparable bonds.

use chronicler_agents::formation::{
    formation_scan, formation_scan_with_mode, marriage_scan, marriage_scan_reference,
    marriage_scan_with_mode,
};
use chronicler_agents::relationships::{get_spouse_id, upsert_symmetric, BondType};
use chronicler_agents::scale::{AgentScaleMode, TickOptions};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::{
    init_attractors, rebuild_spatial_grids, spatial_drift_step, spatial_drift_step_with_mode,
    update_attractor_weights, RegionAttractors, SpatialDiagnostics, SpatialGrid,
};
use chronicler_agents::{AgentPool, Occupation, RegionState};

struct Mix(u64);
impl Mix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
    fn unit(&mut self) -> f32 {
        ((self.next() >> 40) as f32) / ((1u64 << 24) as f32)
    }
}

fn civ_signals(num_civs: u8, at_war: &[u8]) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|c| CivSignals {
                civ_id: c,
                stability: 50,
                is_at_war: at_war.contains(&c),
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
            })
            .collect(),
        contested_regions: vec![],
    }
}

/// A pool built deterministically from `seed`: clustered and duplicate
/// positions, siblings and parent-child pairs, several civs and faiths, some
/// agents already married and some whose relationship slots are all
/// protected (cannot take a marriage bond).
fn build_pool(seed: u64, per_region: usize, regions: u16) -> AgentPool {
    let mut rng = Mix(seed);
    let mut pool = AgentPool::new(per_region * regions as usize);
    let occs = [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
                Occupation::Scholar, Occupation::Priest];
    for r in 0..regions {
        let centres = [(rng.unit(), rng.unit()), (0.5, 0.5), (rng.unit(), rng.unit())];
        for i in 0..per_region {
            let civ = rng.below(4) as u8;
            let belief = if rng.below(5) == 0 { 0xFF } else { rng.below(3) as u8 };
            let cv0 = rng.below(4) as u8;
            let cv1 = 4 + rng.below(2) as u8;
            let cv2 = if rng.below(3) == 0 { 0xFF } else { 6 + rng.below(2) as u8 };
            let age = 10 + rng.below(50) as u16;
            let s = pool.spawn(r, civ, occs[i % 5], age, 0.0, 0.0, 0.0, cv0, cv1, cv2, belief);
            let (x, y) = match i % 6 {
                0 => (rng.unit(), rng.unit()),
                1 if i > 1 => (pool.x[s - 1], pool.y[s - 1]), // exact duplicate
                _ => {
                    let c = centres[rng.below(3) as usize];
                    (
                        (c.0 + 0.15 * (rng.unit() - 0.5)).clamp(0.0, 0.999),
                        (c.1 + 0.15 * (rng.unit() - 0.5)).clamp(0.0, 0.999),
                    )
                }
            };
            pool.x[s] = x;
            pool.y[s] = y;
        }
    }
    let n = pool.capacity();
    // Parents: siblings share a parent; some agents are a parent of another.
    for s in 0..n {
        match rng.below(6) {
            0 => pool.parent_id_0[s] = pool.ids[rng.below(n as u64) as usize],
            1 => {
                pool.parent_id_0[s] = 9_000_000 + rng.below(20) as u32;
                pool.parent_id_1[s] = 9_100_000 + rng.below(20) as u32;
            }
            _ => {}
        }
    }
    // Existing marriages and fully protected agents.
    for s in 0..n {
        match rng.below(12) {
            0 => {
                let t = rng.below(n as u64) as usize;
                if t != s && pool.regions[t] == pool.regions[s]
                    && get_spouse_id(&pool, s).is_none() && get_spouse_id(&pool, t).is_none()
                {
                    upsert_symmetric(&mut pool, s, t, BondType::Marriage as u8, 40, 0);
                }
            }
            1 => {
                for k in 0..8u32 {
                    let i = pool.rel_count[s] as usize;
                    if i >= 8 {
                        break;
                    }
                    pool.rel_target_ids[s][i] = 8_000_000 + k;
                    pool.rel_bond_types[s][i] = BondType::Kin as u8;
                    pool.rel_sentiments[s][i] = 30;
                    pool.rel_count[s] += 1;
                }
            }
            _ => {}
        }
    }
    pool
}

fn alive(pool: &AgentPool) -> Vec<usize> {
    (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect()
}

fn rel_state(pool: &AgentPool) -> Vec<(u32, u8, [u32; 8], [i8; 8], [u8; 8], [u16; 8])> {
    (0..pool.capacity())
        .map(|s| (pool.ids[s], pool.rel_count[s], pool.rel_target_ids[s], pool.rel_sentiments[s],
                  pool.rel_bond_types[s], pool.rel_formed_turns[s]))
        .collect()
}

#[test]
fn exact_marriage_matches_reference_scan() {
    for seed in 0..10u64 {
        let per_region = [6usize, 30, 120, 300][(seed % 4) as usize];
        let regions: Vec<RegionState> = (0..5).map(RegionState::new).collect();
        let signals = civ_signals(4, if seed % 2 == 0 { &[1] } else { &[0, 2] });
        for turn in 0..4u32 {
            let mut reference = build_pool(seed, per_region, 5);
            let mut planned = build_pool(seed, per_region, 5);
            let al = alive(&reference);
            let ref_stats = marriage_scan_reference(&mut reference, &regions, &signals, turn, &al);
            let new_stats = marriage_scan(&mut planned, &regions, &signals, turn, &al);
            assert_eq!(format!("{ref_stats:?}"), format!("{new_stats:?}"), "seed {seed} turn {turn}");
            assert!(rel_state(&reference) == rel_state(&planned), "seed {seed} turn {turn}: spouses differ");
            assert!(ref_stats.marriage_pairs_evaluated > 0);
        }
    }
}

/// Pairs straddling the marriage radius: the radius prefilter of the exact
/// scan keeps exactly the pairs the reference keeps (counters and spouses).
#[test]
fn exact_marriage_matches_reference_at_the_radius() {
    let regions: Vec<RegionState> = (0..3).map(RegionState::new).collect();
    let signals = civ_signals(4, &[2]);
    for seed in 0..6u64 {
        let mut reference = build_pool(seed + 40, 160, 3);
        let mut rng = Mix(seed);
        // Rows of agents spaced the radius apart, give or take a few ulps,
        // so many pairs sit on either side of the radius test.
        for s in 0..reference.capacity() {
            let col = (s % 4) as f32;
            let row = ((s / 4) % 8) as f32 * 0.11;
            let x = 0.05 + col * 0.25; // MARRIAGE_RADIUS
            let jitter = rng.below(9) as i32 - 4;
            reference.x[s] = f32::from_bits((x.to_bits() as i32 + jitter) as u32).clamp(0.0, 0.999);
            reference.y[s] = if s % 3 == 0 { 0.2 + row } else { reference.y[s] };
        }
        let mut planned = build_pool(seed + 40, 160, 3);
        planned.x.copy_from_slice(&reference.x);
        planned.y.copy_from_slice(&reference.y);
        for turn in 0..4u32 {
            let al = alive(&reference);
            let a = marriage_scan_reference(&mut reference, &regions, &signals, turn, &al);
            let b = marriage_scan(&mut planned, &regions, &signals, turn, &al);
            assert_eq!(format!("{a:?}"), format!("{b:?}"), "seed {seed} turn {turn}");
            assert!(rel_state(&reference) == rel_state(&planned), "seed {seed} turn {turn}: spouses differ");
        }
    }
}

#[test]
fn exact_marriage_with_non_finite_position_uses_reference() {
    let regions: Vec<RegionState> = (0..2).map(RegionState::new).collect();
    let signals = civ_signals(4, &[]);
    let mut reference = build_pool(5, 40, 2);
    let mut planned = build_pool(5, 40, 2);
    for pool in [&mut reference, &mut planned] {
        pool.x[3] = f32::NAN;
    }
    let al = alive(&reference);
    let a = marriage_scan_reference(&mut reference, &regions, &signals, 0, &al);
    let b = marriage_scan(&mut planned, &regions, &signals, 0, &al);
    assert_eq!(format!("{a:?}"), format!("{b:?}"));
    assert!(rel_state(&reference) == rel_state(&planned));
}

#[test]
fn fast_marriage_is_deterministic_and_marries_most_eligible() {
    let regions: Vec<RegionState> = (0..4).map(RegionState::new).collect();
    let signals = civ_signals(4, &[]);
    let run = |mode| {
        let mut pool = build_pool(11, 400, 4);
        let mut total = 0;
        for turn in 0..4 {
            let al = alive(&pool);
            let st = marriage_scan_with_mode(&mut pool, &regions, &signals, turn, &al, mode);
            total += st.marriages_formed;
        }
        (total, rel_state(&pool))
    };
    let (exact, _) = run(AgentScaleMode::Exact);
    let (fast_a, state_a) = run(AgentScaleMode::Fast);
    let (fast_b, state_b) = run(AgentScaleMode::Fast);
    assert_eq!(fast_a, fast_b);
    assert!(state_a == state_b);
    // Bounded candidates still pair up nearly everyone who can marry.
    assert!(fast_a as f64 >= 0.9 * exact as f64, "fast {fast_a} vs exact {exact}");
}

#[test]
fn exact_formation_is_the_default_scan() {
    let regions: Vec<RegionState> = (0..6).map(RegionState::new).collect();
    for turn in 0..6u32 {
        let mut a = build_pool(3, 200, 6);
        let mut b = build_pool(3, 200, 6);
        let al = alive(&a);
        let sa = formation_scan(&mut a, &regions, turn, &al);
        let sb = formation_scan_with_mode(&mut b, &regions, turn, &al, AgentScaleMode::Exact);
        assert_eq!(format!("{sa:?}"), format!("{sb:?}"));
        assert!(rel_state(&a) == rel_state(&b));
    }
}

fn spatial_world(seed: u64, n: usize) -> (AgentPool, Vec<RegionAttractors>) {
    let mut rng = Mix(seed);
    let mut pool = AgentPool::new(n);
    let mut attractors = Vec::new();
    for r in 0..3u16 {
        let mut region = RegionState::new(r);
        region.is_capital = r == 0;
        region.has_temple = r == 1;
        region.resource_effective_yield = [0.6, 0.3, 0.0];
        let mut att = init_attractors(seed, r, &region);
        update_attractor_weights(&mut att, &region);
        attractors.push(att);
    }
    for i in 0..n {
        let r = (i % 3) as u16;
        let s = pool.spawn(r, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, 0xFF);
        let c = attractors[r as usize].positions[0];
        pool.x[s] = (c.0 + 0.08 * (rng.unit() - 0.5)).clamp(0.0, 0.999);
        pool.y[s] = (c.1 + 0.08 * (rng.unit() - 0.5)).clamp(0.0, 0.999);
    }
    (pool, attractors)
}

#[test]
fn exact_drift_is_independent_of_thread_count() {
    let run = |threads: usize| {
        let (mut pool, attractors) = spatial_world(9, 6000); // above the parallel threshold
        let tp = rayon::ThreadPoolBuilder::new().num_threads(threads).build().unwrap();
        tp.install(|| {
            let mut grids: Vec<SpatialGrid> = Vec::new();
            let mut diag = SpatialDiagnostics::default();
            for _ in 0..5 {
                rebuild_spatial_grids(&pool, &mut grids, 3);
                spatial_drift_step(&mut pool, &grids, &attractors, &mut diag);
            }
            let xs: Vec<u32> = pool.x.iter().map(|v| v.to_bits()).collect();
            let ys: Vec<u32> = pool.y.iter().map(|v| v.to_bits()).collect();
            (xs, ys, format!("{diag:?}"))
        })
    };
    let one = run(1);
    assert_eq!(one, run(3));
    assert_eq!(one, run(4));
}

#[test]
fn fast_drift_is_deterministic_and_bounded() {
    let run = |threads: usize| {
        let (mut pool, attractors) = spatial_world(4, 6000);
        let tp = rayon::ThreadPoolBuilder::new().num_threads(threads).build().unwrap();
        tp.install(|| {
            let mut grids: Vec<SpatialGrid> = Vec::new();
            let mut diag = SpatialDiagnostics::default();
            for _ in 0..3 {
                rebuild_spatial_grids(&pool, &mut grids, 3);
                spatial_drift_step_with_mode(&mut pool, &grids, &attractors, &mut diag, AgentScaleMode::Fast);
            }
            pool.x.iter().chain(pool.y.iter()).map(|v| v.to_bits()).collect::<Vec<u32>>()
        })
    };
    let a = run(1);
    assert_eq!(a, run(4));
    assert!(a.iter().all(|&b| f32::from_bits(b) >= 0.0 && f32::from_bits(b) < 1.0));
}

#[test]
fn tick_options_default_is_exact() {
    assert_eq!(TickOptions::default().scale_mode, AgentScaleMode::Exact);
    assert_eq!(AgentScaleMode::parse("exact"), Some(AgentScaleMode::Exact));
    assert_eq!(AgentScaleMode::parse("fast"), Some(AgentScaleMode::Fast));
    assert_eq!(AgentScaleMode::parse("approximate"), None);
    assert_eq!(AgentScaleMode::Fast.as_str(), "fast");
}
