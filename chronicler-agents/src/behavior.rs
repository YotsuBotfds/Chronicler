//! Agent decision model — rebel, migrate, switch occupation, loyalty drift.
//!
//! Each tick, agents evaluate decisions in priority order. First triggered
//! decision executes; rest skipped (short-circuit).

use std::collections::HashMap;

use crate::agent::{
    LOYALTY_DRIFT_RATE, LOYALTY_FLIP_THRESHOLD, LOYALTY_RECOVERY_RATE,
    MIGRATE_CAP, MIGRATE_HYSTERESIS, MIGRATE_SATISFACTION_THRESHOLD, OCCUPATION_COUNT,
    OCCUPATION_SWITCH_OVERSUPPLY, OCCUPATION_SWITCH_UNDERSUPPLY, REBEL_CAP,
    REBEL_LOYALTY_THRESHOLD, REBEL_MIN_COHORT, REBEL_SATISFACTION_THRESHOLD,
    SWITCH_CAP, SWITCH_OVERSUPPLY_THRESH, SWITCH_UNDERSUPPLY_FACTOR,
    W_MIGRATE_OPP, W_MIGRATE_SAT, W_REBEL, W_SWITCH,
};
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::satisfaction::target_occupation_ratio;
use crate::signals::TickSignals;
use rand::Rng;
use rand_chacha::ChaCha8Rng;

// ---------------------------------------------------------------------------
// Helpers — smoothstep, gumbel_argmax
// ---------------------------------------------------------------------------

fn smoothstep(x: usize, edge0: usize, edge1: usize) -> f32 {
    if x <= edge0 { return 0.0; }
    if x >= edge1 { return 1.0; }
    let t = (x - edge0) as f32 / (edge1 - edge0) as f32;
    t * t * (3.0 - 2.0 * t)
}

fn gumbel_argmax(utilities: &[f32], rng: &mut ChaCha8Rng, temperature: f32) -> usize {
    if temperature <= 0.0 {
        return utilities.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0);
    }
    let mut best_idx = 0;
    let mut best_val = f32::NEG_INFINITY;
    for (i, &u) in utilities.iter().enumerate() {
        let uniform: f32 = rng.gen::<f32>().max(f32::EPSILON);
        let gumbel = -temperature * (-uniform.ln()).ln();
        let perturbed = u + gumbel;
        if perturbed > best_val {
            best_val = perturbed;
            best_idx = i;
        }
    }
    best_idx
}

// ---------------------------------------------------------------------------
// RegionStats — pre-computed per-region aggregates
// ---------------------------------------------------------------------------

/// Pre-computed per-region aggregates needed by decision evaluation.
pub struct RegionStats {
    /// Count of agents per region with loyalty < REBEL_LOYALTY_THRESHOLD
    /// AND satisfaction < REBEL_SATISFACTION_THRESHOLD.
    pub rebel_eligible: Vec<usize>,
    /// Mean satisfaction per region.
    pub mean_satisfaction: Vec<f32>,
    /// Per-region, per-occupation agent count.
    pub occupation_supply: Vec<[usize; OCCUPATION_COUNT]>,
    /// Per-region demand from target_occupation_ratio * pop.
    pub occupation_demand: Vec<[f32; OCCUPATION_COUNT]>,
    /// Per-region, per-civ agent count.
    pub civ_counts: Vec<Vec<(u8, usize)>>,
    /// Per-region, per-civ mean satisfaction.
    pub civ_mean_satisfaction: Vec<Vec<(u8, f32)>>,
}

/// Single O(n) pass over alive agents to build all region stats.
pub fn compute_region_stats(pool: &AgentPool, regions: &[RegionState], signals: &TickSignals) -> RegionStats {
    let n = regions.len();

    let mut rebel_eligible = vec![0usize; n];
    let mut sat_sum = vec![0.0f32; n];
    let mut pop_count = vec![0usize; n];
    let mut occupation_supply = vec![[0usize; OCCUPATION_COUNT]; n];

    // Per-region civ data: HashMap<civ_id, (count, satisfaction_sum)>
    let mut civ_data: Vec<HashMap<u8, (usize, f32)>> =
        (0..n).map(|_| HashMap::new()).collect();

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) {
            continue;
        }
        let r = pool.region(slot) as usize;
        if r >= n {
            continue;
        }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let occ = pool.occupation(slot) as usize;
        let civ = pool.civ_affinity(slot);

        // Rebel eligibility
        if loy < REBEL_LOYALTY_THRESHOLD && sat < REBEL_SATISFACTION_THRESHOLD {
            rebel_eligible[r] += 1;
        }

        // Satisfaction accumulator
        sat_sum[r] += sat;
        pop_count[r] += 1;

        // Occupation supply
        if occ < OCCUPATION_COUNT {
            occupation_supply[r][occ] += 1;
        }

        // Civ data
        let entry = civ_data[r].entry(civ).or_insert((0, 0.0));
        entry.0 += 1;
        entry.1 += sat;
    }

    // Finalize mean satisfaction
    let mean_satisfaction: Vec<f32> = (0..n)
        .map(|r| {
            if pop_count[r] > 0 {
                sat_sum[r] / pop_count[r] as f32
            } else {
                0.0
            }
        })
        .collect();

    // Finalize occupation demand
    let occupation_demand: Vec<[f32; OCCUPATION_COUNT]> = (0..n)
        .map(|r| {
            let demand_shifts = if regions[r].controller_civ != 255 {
                signals.demand_shifts_for_civ(regions[r].controller_civ)
            } else {
                [0.0; 5]
            };
            let ratios = target_occupation_ratio(regions[r].terrain, regions[r].soil, regions[r].water, demand_shifts);
            let pop = pop_count[r] as f32;
            let mut demand = [0.0f32; OCCUPATION_COUNT];
            for i in 0..OCCUPATION_COUNT {
                demand[i] = ratios[i] * pop;
            }
            demand
        })
        .collect();

    // Finalize civ counts and civ mean satisfaction
    let mut civ_counts: Vec<Vec<(u8, usize)>> = Vec::with_capacity(n);
    let mut civ_mean_satisfaction: Vec<Vec<(u8, f32)>> = Vec::with_capacity(n);

    for r in 0..n {
        let mut counts: Vec<(u8, usize)> = Vec::new();
        let mut means: Vec<(u8, f32)> = Vec::new();
        for (&civ, &(count, sat_total)) in &civ_data[r] {
            counts.push((civ, count));
            let mean = if count > 0 {
                sat_total / count as f32
            } else {
                0.0
            };
            means.push((civ, mean));
        }
        // Sort by civ_id for deterministic ordering
        counts.sort_by_key(|(c, _)| *c);
        means.sort_by_key(|(c, _)| *c);
        civ_counts.push(counts);
        civ_mean_satisfaction.push(means);
    }

    RegionStats {
        rebel_eligible,
        mean_satisfaction,
        occupation_supply,
        occupation_demand,
        civ_counts,
        civ_mean_satisfaction,
    }
}

// ---------------------------------------------------------------------------
// PendingDecisions
// ---------------------------------------------------------------------------

/// Collected decisions from one region's evaluation pass.
pub struct PendingDecisions {
    /// (slot, region) — agent rebels.
    pub rebellions: Vec<(usize, u16)>,
    /// (slot, from, to) — agent migrates.
    pub migrations: Vec<(usize, u16, u16)>,
    /// (slot, new_occ) — agent switches occupation.
    pub occupation_switches: Vec<(usize, u8)>,
    /// (slot, new_civ) — agent flips civ allegiance.
    pub loyalty_flips: Vec<(usize, u8)>,
    /// (slot, delta) — positive = recovery, negative = drift.
    pub loyalty_drifts: Vec<(usize, f32)>,
}

impl PendingDecisions {
    fn new() -> Self {
        Self {
            rebellions: Vec::new(),
            migrations: Vec::new(),
            occupation_switches: Vec::new(),
            loyalty_flips: Vec::new(),
            loyalty_drifts: Vec::new(),
        }
    }
}

// ---------------------------------------------------------------------------
// evaluate_region_decisions
// ---------------------------------------------------------------------------

/// Evaluate decisions for all alive agents in a region.
///
/// Short-circuit: first triggered decision executes, rest skipped.
/// Priority: rebel > migrate > switch occupation > loyalty drift/recovery.
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
) -> PendingDecisions {
    let mut pending = PendingDecisions::new();

    for &slot in slots {
        if !pool.is_alive(slot) {
            continue;
        }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let civ = pool.civ_affinity(slot);
        let occ = pool.occupation(slot) as usize;

        // 1. Rebel?
        if loy < REBEL_LOYALTY_THRESHOLD
            && sat < REBEL_SATISFACTION_THRESHOLD
            && stats.rebel_eligible[region_id] >= REBEL_MIN_COHORT
        {
            pending.rebellions.push((slot, region_id as u16));
            continue;
        }

        // 2. Migrate?
        if sat < MIGRATE_SATISFACTION_THRESHOLD && region.adjacency_mask != 0 {
            let current_mean = stats.mean_satisfaction[region_id];
            let mut best_region: Option<u16> = None;
            let mut best_sat: f32 = current_mean + 0.05;

            for bit in 0..32u32 {
                if region.adjacency_mask & (1 << bit) != 0 {
                    let adj = bit as usize;
                    if adj < stats.mean_satisfaction.len()
                        && stats.mean_satisfaction[adj] > best_sat
                    {
                        best_sat = stats.mean_satisfaction[adj];
                        best_region = Some(adj as u16);
                    }
                }
            }

            if let Some(target) = best_region {
                pending.migrations.push((slot, region_id as u16, target));
                continue;
            }
        }

        // 3. Switch occupation?
        // Oversupply check: supply > demand * (1.0 / OCCUPATION_SWITCH_OVERSUPPLY) = demand * 2.0
        let supply = stats.occupation_supply[region_id][occ] as f32;
        let demand = stats.occupation_demand[region_id][occ];
        let oversupply_threshold = demand * (1.0 / OCCUPATION_SWITCH_OVERSUPPLY);

        let mut switched = false;
        if supply > oversupply_threshold {
            // Find alternative with undersupply: demand > supply * UNDERSUPPLY
            let mut best_occ: Option<u8> = None;
            let mut best_gap: f32 = 0.0;

            for alt in 0..OCCUPATION_COUNT {
                if alt == occ {
                    continue;
                }
                let alt_supply = stats.occupation_supply[region_id][alt] as f32;
                let alt_demand = stats.occupation_demand[region_id][alt];
                if alt_demand > alt_supply * OCCUPATION_SWITCH_UNDERSUPPLY {
                    let gap = alt_demand - alt_supply;
                    if gap > best_gap {
                        best_gap = gap;
                        best_occ = Some(alt as u8);
                    }
                }
            }

            if let Some(new_occ) = best_occ {
                pending.occupation_switches.push((slot, new_occ));
                switched = true;
            }
        }

        if switched {
            continue;
        }

        // 4. Loyalty drift (only when multiple civs present)
        if stats.civ_counts[region_id].len() > 1 {
            // Find own civ mean satisfaction
            let own_mean = stats
                .civ_mean_satisfaction[region_id]
                .iter()
                .find(|(c, _)| *c == civ)
                .map(|(_, m)| *m)
                .unwrap_or(0.0);

            // Find best other civ mean satisfaction and its civ_id
            let mut best_other_civ: Option<u8> = None;
            let mut best_other_mean: f32 = own_mean;

            for &(c, mean) in &stats.civ_mean_satisfaction[region_id] {
                if c != civ && mean > best_other_mean {
                    best_other_mean = mean;
                    best_other_civ = Some(c);
                }
            }

            if let Some(other_civ) = best_other_civ {
                // Other civ is happier — drift away
                if loy - LOYALTY_DRIFT_RATE < LOYALTY_FLIP_THRESHOLD {
                    // Would drop below flip threshold — flip civ
                    pending.loyalty_flips.push((slot, other_civ));
                } else {
                    pending.loyalty_drifts.push((slot, -LOYALTY_DRIFT_RATE));
                }
            } else {
                // No happier civ — recover loyalty
                pending.loyalty_drifts.push((slot, LOYALTY_RECOVERY_RATE));
            }
        }
    }

    pending
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::pool::AgentPool;
    use crate::region::RegionState;
    use crate::signals::TickSignals;

    fn default_signals(num_regions: usize) -> TickSignals {
        TickSignals {
            civs: vec![],
            contested_regions: vec![false; num_regions],
        }
    }

    fn make_region(id: u16) -> RegionState {
        RegionState {
            region_id: id,
            terrain: 0,
            carrying_capacity: 60,
            population: 0,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
            adjacency_mask: 0,
            controller_civ: 0,
            trade_route_count: 0,
        }
    }

    #[test]
    fn test_rebel_fires_with_cohort() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // 6 agents below both thresholds
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.1);
            pool.set_satisfaction(slot, 0.1);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        assert_eq!(pending.rebellions.len(), 6);
        // No other decisions should fire (short-circuit)
        assert_eq!(pending.migrations.len(), 0);
        assert_eq!(pending.occupation_switches.len(), 0);
    }

    #[test]
    fn test_rebel_needs_cohort() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // Only 3 below thresholds — not enough for REBEL_MIN_COHORT (5)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.1);
            pool.set_satisfaction(slot, 0.1);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        assert_eq!(pending.rebellions.len(), 0);
    }

    #[test]
    fn test_migrate_to_better_region() {
        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];

        // Region 0 is adjacent to region 1
        regions[0].adjacency_mask = 0b10; // bit 1

        // 5 dissatisfied agents in region 0
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_satisfaction(slot, 0.2);
            pool.set_loyalty(slot, 0.5); // loyalty high enough to avoid rebel
        }

        // 5 happy agents in region 1
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        // Verify mean satisfaction: region 0 = 0.2, region 1 = 0.8
        assert!((stats.mean_satisfaction[0] - 0.2).abs() < 0.01);
        assert!((stats.mean_satisfaction[1] - 0.8).abs() < 0.01);

        let slots: Vec<usize> = (0..5).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        // All 5 should want to migrate to region 1
        assert_eq!(pending.migrations.len(), 5);
        for &(_, from, to) in &pending.migrations {
            assert_eq!(from, 0);
            assert_eq!(to, 1);
        }
    }

    #[test]
    fn test_occupation_switch_oversupplied_to_undersupplied() {
        let regions = vec![make_region(0)];

        // Use priests: ratio = 0.05. With 20 priests, demand = 0.05 * 20 = 1.0
        // Oversupply threshold = 1.0 * 2.0 = 2.0, supply(20) > 2.0 → oversupplied
        // Farmer demand = 0.60 * 20 = 12.0, supply = 0
        // 12.0 > 0 * 1.5 = 0 → undersupplied → switch to farmer
        let mut pool = AgentPool::new(32);
        for _ in 0..20 {
            let slot = pool.spawn(0, 0, Occupation::Priest, 25);
            pool.set_satisfaction(slot, 0.5); // above migrate threshold
            pool.set_loyalty(slot, 0.5);      // above rebel threshold
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        let slots: Vec<usize> = (0..20).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        assert!(pending.occupation_switches.len() > 0);
        // Should switch to farmer (occupation 0) since it has highest gap
        for &(_, new_occ) in &pending.occupation_switches {
            assert_eq!(new_occ, Occupation::Farmer as u8);
        }
    }

    #[test]
    fn test_loyalty_drift_without_flip() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // Civ 0: 3 agents at 0.6 loyalty, satisfaction 0.3
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.3);
        }
        // Civ 1: 3 agents, satisfaction 0.8 (happier)
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        // Verify multiple civs present
        assert!(stats.civ_counts[0].len() > 1);

        // Evaluate civ 0 agents (slots 0..3)
        let slots: Vec<usize> = (0..3).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        // Should drift negatively (other civ is happier) but NOT flip
        // loyalty 0.6 - 0.02 = 0.58, which is above LOYALTY_FLIP_THRESHOLD (0.3)
        assert_eq!(pending.loyalty_flips.len(), 0);
        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - (-LOYALTY_DRIFT_RATE)).abs() < 0.001);
        }
    }

    #[test]
    fn test_loyalty_drift_flips_civ() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // Civ 0: 3 agents at 0.25 loyalty (below flip threshold after drift)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.25);
            pool.set_satisfaction(slot, 0.4); // above migrate threshold
        }
        // Civ 1: 3 agents, satisfaction 0.9 (happier)
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.9);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        let slots: Vec<usize> = (0..3).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        // loyalty 0.25 - 0.02 = 0.23, which is below LOYALTY_FLIP_THRESHOLD (0.3)
        // → should flip to civ 1
        assert_eq!(pending.loyalty_flips.len(), 3);
        for &(_, new_civ) in &pending.loyalty_flips {
            assert_eq!(new_civ, 1);
        }
        assert_eq!(pending.loyalty_drifts.len(), 0);
    }

    #[test]
    fn test_compute_region_stats_empty_region() {
        let pool = AgentPool::new(8);
        let regions = vec![make_region(0), make_region(1)];
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        assert_eq!(stats.rebel_eligible[0], 0);
        assert_eq!(stats.mean_satisfaction[0], 0.0);
        assert_eq!(stats.occupation_supply[0], [0; OCCUPATION_COUNT]);
        assert_eq!(stats.civ_counts[0].len(), 0);
    }

    #[test]
    fn test_short_circuit_rebel_blocks_migrate() {
        // An agent eligible for both rebel and migrate should only rebel.
        let mut pool = AgentPool::new(16);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10; // adjacent to region 1

        // 6 rebel-eligible agents with low satisfaction (also eligible for migration)
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.1);
            pool.set_satisfaction(slot, 0.1);
        }
        // Some happy agents in region 1 to make migration attractive
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25);
            pool.set_satisfaction(slot, 0.9);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        // All rebel, none migrate
        assert_eq!(pending.rebellions.len(), 6);
        assert_eq!(pending.migrations.len(), 0);
    }

    #[test]
    fn test_smoothstep_below_edge0() {
        assert_eq!(super::smoothstep(0, 3, 8), 0.0);
        assert_eq!(super::smoothstep(2, 3, 8), 0.0);
        assert_eq!(super::smoothstep(3, 3, 8), 0.0);
    }

    #[test]
    fn test_smoothstep_above_edge1() {
        assert_eq!(super::smoothstep(8, 3, 8), 1.0);
        assert_eq!(super::smoothstep(10, 3, 8), 1.0);
    }

    #[test]
    fn test_smoothstep_midpoint() {
        let mid_low = super::smoothstep(5, 3, 8);
        let mid_high = super::smoothstep(6, 3, 8);
        assert!(mid_low > 0.0 && mid_low < 1.0);
        assert!(mid_high > mid_low);
    }

    #[test]
    fn test_gumbel_argmax_deterministic_at_zero_temp() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let utilities = [0.3, 0.8, 0.1, 0.5];
        for _ in 0..10 {
            let chosen = super::gumbel_argmax(&utilities, &mut rng, 0.0);
            assert_eq!(chosen, 1);
        }
    }

    #[test]
    fn test_gumbel_argmax_respects_utility_ordering() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut wins = [0u32; 4];
        for seed_byte in 0..100u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let utilities = [0.1, 1.5, 0.3, 0.5];
            let chosen = super::gumbel_argmax(&utilities, &mut rng, 0.01);
            wins[chosen] += 1;
        }
        assert!(wins[1] > 90, "expected index 1 to win >90 times, got {}", wins[1]);
    }

    #[test]
    fn test_gumbel_argmax_zero_draws_at_zero_temp() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng_a = ChaCha8Rng::from_seed([0u8; 32]);
        let mut rng_b = ChaCha8Rng::from_seed([0u8; 32]);
        let _ = super::gumbel_argmax(&[0.1, 0.5, 0.3, 0.2], &mut rng_a, 0.0);
        let val_a: f32 = rng_a.gen();
        let val_b: f32 = rng_b.gen();
        assert_eq!(val_a, val_b, "T=0 path should not consume RNG draws");
    }

    #[test]
    fn test_loyalty_recovery_when_own_civ_happier() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // Civ 0: 3 agents, satisfaction 0.8 (happier)
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }
        // Civ 1: 3 agents, satisfaction 0.3 (less happy)
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.3);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));

        // Evaluate civ 0 agents — own civ is happier, should recover
        let slots: Vec<usize> = (0..3).collect();
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0);

        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - LOYALTY_RECOVERY_RATE).abs() < 0.001);
        }
    }
}
