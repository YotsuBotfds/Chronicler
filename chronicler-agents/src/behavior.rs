//! Agent decision model — rebel, migrate, switch occupation, loyalty drift.
//!
//! Each tick, agents compute utility scores for rebel, migrate, switch, and
//! stay. Gumbel-argmax selects one action; loyalty drift runs as a background
//! process for all non-rebel agents.

use std::collections::HashMap;

use crate::agent::{
    DECISION_TEMPERATURE, LOYALTY_DRIFT_RATE, LOYALTY_FLIP_THRESHOLD, LOYALTY_RECOVERY_RATE,
    MIGRATE_CAP, MIGRATE_HYSTERESIS, MIGRATE_SATISFACTION_THRESHOLD, OCCUPATION_COUNT,
    REBEL_CAP, REBEL_LOYALTY_THRESHOLD, REBEL_MIN_COHORT, REBEL_SATISFACTION_THRESHOLD,
    STAY_BASE, SWITCH_CAP, SWITCH_OVERSUPPLY_THRESH, SWITCH_UNDERSUPPLY_FACTOR,
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
// Utility functions
// ---------------------------------------------------------------------------

fn rebel_utility(loyalty: f32, satisfaction: f32, rebel_eligible: usize) -> f32 {
    let raw = W_REBEL
        * ((REBEL_LOYALTY_THRESHOLD - loyalty).max(0.0)
            + (REBEL_SATISFACTION_THRESHOLD - satisfaction).max(0.0));
    raw.min(REBEL_CAP) * smoothstep(rebel_eligible, REBEL_MIN_COHORT - 2, REBEL_MIN_COHORT + 3)
}

fn migrate_utility(satisfaction: f32, migration_opportunity: f32) -> f32 {
    let raw = W_MIGRATE_SAT * (MIGRATE_SATISFACTION_THRESHOLD - satisfaction).max(0.0)
        + W_MIGRATE_OPP * (migration_opportunity - MIGRATE_HYSTERESIS).max(0.0);
    raw.min(MIGRATE_CAP)
}

fn switch_utility(
    occ: usize,
    supply: &[usize; OCCUPATION_COUNT],
    demand: &[f32; OCCUPATION_COUNT],
) -> (f32, u8) {
    let own_supply = supply[occ] as f32;
    let own_demand = demand[occ].max(0.01);
    let oversupply = (own_supply / own_demand - SWITCH_OVERSUPPLY_THRESH).max(0.0);

    let mut best_alt: u8 = occ as u8;
    let mut best_gap: f32 = 0.0;
    for alt in 0..OCCUPATION_COUNT {
        if alt == occ { continue; }
        let alt_supply = supply[alt] as f32;
        let alt_demand = demand[alt];
        let gap = (alt_demand - alt_supply * SWITCH_UNDERSUPPLY_FACTOR).max(0.0);
        if gap > best_gap {
            best_gap = gap;
            best_alt = alt as u8;
        }
    }

    let utility = (W_SWITCH * oversupply * best_gap).min(SWITCH_CAP);
    (utility, best_alt)
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
    /// How much better the best adjacent region is (0 if none better).
    pub migration_opportunity: Vec<f32>,
    /// Region id of the best adjacent migration target (own id if none better).
    pub best_migration_target: Vec<u16>,
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

    let mut migration_opportunity = vec![0.0f32; n];
    let mut best_migration_target = vec![0u16; n];
    for r in 0..n {
        let own_mean = mean_satisfaction[r];
        let mut best_adj_mean = own_mean;
        let mut best_adj_id: u16 = r as u16;
        for bit in 0..32u32 {
            if regions[r].adjacency_mask & (1 << bit) != 0 {
                let adj = bit as usize;
                if adj < n && mean_satisfaction[adj] > best_adj_mean {
                    best_adj_mean = mean_satisfaction[adj];
                    best_adj_id = adj as u16;
                }
            }
        }
        migration_opportunity[r] = (best_adj_mean - own_mean).max(0.0);
        best_migration_target[r] = best_adj_id;
    }

    RegionStats {
        rebel_eligible,
        mean_satisfaction,
        occupation_supply,
        occupation_demand,
        civ_counts,
        civ_mean_satisfaction,
        migration_opportunity,
        best_migration_target,
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
// evaluate_region_decisions — utility-based (M32)
// ---------------------------------------------------------------------------

/// Evaluate decisions for all alive agents in a region using utility selection.
///
/// Each agent computes utility scores for rebel, migrate, switch, and stay.
/// Gumbel-argmax selects one action. Loyalty drift runs as a background
/// process for all non-rebel agents afterward.
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    _region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
    rng: &mut ChaCha8Rng,
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

        // Compute utilities for all 4 actions.
        // Zero-utility actions are gated to NEG_INFINITY so gumbel noise
        // cannot select an action whose prerequisites are not met.
        let u_rebel_raw = rebel_utility(loy, sat, stats.rebel_eligible[region_id]);
        let u_rebel = if u_rebel_raw > 0.0 { u_rebel_raw } else { f32::NEG_INFINITY };
        let u_migrate_raw = migrate_utility(sat, stats.migration_opportunity[region_id]);
        let u_migrate = if u_migrate_raw > 0.0 { u_migrate_raw } else { f32::NEG_INFINITY };
        let (u_switch_raw, switch_target) = switch_utility(
            occ,
            &stats.occupation_supply[region_id],
            &stats.occupation_demand[region_id],
        );
        let u_switch = if u_switch_raw > 0.0 { u_switch_raw } else { f32::NEG_INFINITY };
        let u_stay = STAY_BASE;

        let chosen = gumbel_argmax(
            &[u_rebel, u_migrate, u_switch, u_stay],
            rng,
            DECISION_TEMPERATURE,
        );

        match chosen {
            0 => {
                // Rebel
                pending.rebellions.push((slot, region_id as u16));
            }
            1 => {
                // Migrate — use pre-computed best target
                let target = stats.best_migration_target[region_id];
                if target != region_id as u16 {
                    pending.migrations.push((slot, region_id as u16, target));
                }
            }
            2 => {
                // Switch occupation
                if switch_target != occ as u8 {
                    pending.occupation_switches.push((slot, switch_target));
                }
            }
            _ => {
                // Stay — no action
            }
        }

        // Loyalty drift as background process (skip only for rebels)
        if chosen != 0 && stats.civ_counts[region_id].len() > 1 {
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
// evaluate_region_decisions_v1 — Phase 5 short-circuit (preserved for regression)
// ---------------------------------------------------------------------------

/// Phase 5 short-circuit decision model. Preserved for regression comparison.
#[cfg(test)]
#[allow(dead_code)]
fn evaluate_region_decisions_v1(
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
        let supply = stats.occupation_supply[region_id][occ] as f32;
        let demand = stats.occupation_demand[region_id][occ];
        let oversupply_threshold = demand * (1.0 / crate::agent::OCCUPATION_SWITCH_OVERSUPPLY);

        let mut switched = false;
        if supply > oversupply_threshold {
            let mut best_occ: Option<u8> = None;
            let mut best_gap: f32 = 0.0;

            for alt in 0..OCCUPATION_COUNT {
                if alt == occ {
                    continue;
                }
                let alt_supply = stats.occupation_supply[region_id][alt] as f32;
                let alt_demand = stats.occupation_demand[region_id][alt];
                if alt_demand > alt_supply * crate::agent::OCCUPATION_SWITCH_UNDERSUPPLY {
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
            let own_mean = stats
                .civ_mean_satisfaction[region_id]
                .iter()
                .find(|(c, _)| *c == civ)
                .map(|(_, m)| *m)
                .unwrap_or(0.0);

            let mut best_other_civ: Option<u8> = None;
            let mut best_other_mean: f32 = own_mean;

            for &(c, mean) in &stats.civ_mean_satisfaction[region_id] {
                if c != civ && mean > best_other_mean {
                    best_other_mean = mean;
                    best_other_civ = Some(c);
                }
            }

            if let Some(other_civ) = best_other_civ {
                if loy - LOYALTY_DRIFT_RATE < LOYALTY_FLIP_THRESHOLD {
                    pending.loyalty_flips.push((slot, other_civ));
                } else {
                    pending.loyalty_drifts.push((slot, -LOYALTY_DRIFT_RATE));
                }
            } else {
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
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert!(pending.rebellions.len() >= 3,
            "expected most agents to rebel, got {}", pending.rebellions.len());
    }

    #[test]
    fn test_rebel_needs_cohort() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert_eq!(pending.rebellions.len(), 0);
    }

    #[test]
    fn test_migrate_to_better_region() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.05);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..5).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert!(pending.migrations.len() >= 3,
            "expected most agents to migrate, got {}", pending.migrations.len());
        for &(_, from, to) in &pending.migrations {
            assert_eq!(from, 0);
            assert_eq!(to, 1);
        }
    }

    #[test]
    fn test_occupation_switch_oversupplied_to_undersupplied() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let regions = vec![make_region(0)];
        let mut pool = AgentPool::new(32);
        for _ in 0..20 {
            let slot = pool.spawn(0, 0, Occupation::Priest, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.5);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..20).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert!(pending.occupation_switches.len() > 0);
        for &(_, new_occ) in &pending.occupation_switches {
            assert_eq!(new_occ, Occupation::Farmer as u8);
        }
    }

    #[test]
    fn test_loyalty_drift_without_flip() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_flips.len(), 0);
        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - (-LOYALTY_DRIFT_RATE)).abs() < 0.001);
        }
    }

    #[test]
    fn test_loyalty_drift_flips_civ() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.25);
            pool.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.9);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_flips.len(), 3);
        for &(_, new_civ) in &pending.loyalty_flips {
            assert_eq!(new_civ, 1);
        }
        assert_eq!(pending.loyalty_drifts.len(), 0);
    }

    #[test]
    fn test_rebel_priority_over_migrate() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.9);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        let total_actions = pending.rebellions.len() + pending.migrations.len();
        assert!(total_actions >= 4,
            "expected most agents to rebel or migrate, got {} rebels + {} migrants",
            pending.rebellions.len(), pending.migrations.len());
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
        assert_eq!(stats.migration_opportunity[0], 0.0);
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
    fn test_migration_opportunity_computed() {
        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.2);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert!(stats.migration_opportunity[0] > 0.0);
        assert_eq!(stats.best_migration_target[0], 1);
        assert_eq!(stats.migration_opportunity[1], 0.0);
    }

    #[test]
    fn test_migration_opportunity_no_adjacent() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_satisfaction(slot, 0.2);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(stats.migration_opportunity[0], 0.0);
    }

    #[test]
    fn test_rebel_utility_zero_above_both_thresholds() {
        let u = super::rebel_utility(0.5, 0.5, 10);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_rebel_utility_partial_one_dimension() {
        let u = super::rebel_utility(0.1, 0.5, 10);
        assert!(u > 0.0);
        let expected = 0.375_f32; // W_REBEL * (0.2 - 0.1) * smoothstep(10,3,8)=1.0
        assert!((u - expected).abs() < 0.01, "expected ~{}, got {}", expected, u);
    }

    #[test]
    fn test_rebel_utility_saturates_at_cap() {
        use crate::agent::REBEL_CAP;
        let u = super::rebel_utility(0.0, 0.0, 10);
        assert!((u - REBEL_CAP).abs() < 0.01);
    }

    #[test]
    fn test_rebel_utility_smoothstep_cohort_gate() {
        use crate::agent::REBEL_CAP;
        let u_zero = super::rebel_utility(0.0, 0.0, 3);
        assert_eq!(u_zero, 0.0);
        let u_full = super::rebel_utility(0.0, 0.0, 8);
        assert!((u_full - REBEL_CAP).abs() < 0.01);
        let u_mid = super::rebel_utility(0.0, 0.0, 5);
        assert!(u_mid > 0.0 && u_mid < REBEL_CAP);
    }

    #[test]
    fn test_migrate_utility_zero_above_threshold_no_opportunity() {
        let u = super::migrate_utility(0.5, 0.0);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_migrate_utility_satisfaction_below_threshold() {
        let u = super::migrate_utility(0.1, 0.0);
        assert!((u - 0.334).abs() < 0.01, "expected ~0.334, got {}", u);
    }

    #[test]
    fn test_migrate_utility_saturates_at_cap() {
        use crate::agent::MIGRATE_CAP;
        let u = super::migrate_utility(0.0, 1.0);
        assert!((u - MIGRATE_CAP).abs() < 0.01);
    }

    #[test]
    fn test_migrate_utility_opportunity_below_hysteresis() {
        let u = super::migrate_utility(0.5, 0.03);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_no_oversupply() {
        let supply = [5, 0, 0, 0, 0];
        let demand = [10.0, 10.0, 10.0, 10.0, 10.0];
        let (u, _) = super::switch_utility(0, &supply, &demand);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_oversupply_no_undersupply() {
        let supply = [20, 20, 20, 20, 20];
        let demand = [5.0, 20.0, 20.0, 20.0, 20.0];
        let (u, _) = super::switch_utility(0, &supply, &demand);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_both_conditions() {
        use crate::agent::{W_SWITCH, SWITCH_CAP};
        let supply = [0, 5, 5, 5, 20];
        let demand = [12.0, 5.0, 5.0, 5.0, 1.0];
        let (u, best_alt) = super::switch_utility(4, &supply, &demand);
        let expected = (W_SWITCH * 18.0 * 12.0).min(SWITCH_CAP);
        assert!((u - expected).abs() < 0.01, "expected {}, got {}", expected, u);
        assert_eq!(best_alt, 0);
    }

    #[test]
    fn test_switch_utility_returns_best_alternative() {
        let supply = [3, 0, 5, 5, 20];
        let demand = [5.0, 10.0, 5.0, 5.0, 1.0];
        let (_, best_alt) = super::switch_utility(4, &supply, &demand);
        assert_eq!(best_alt, 1);
    }

    #[test]
    fn test_loyalty_recovery_when_own_civ_happier() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - LOYALTY_RECOVERY_RATE).abs() < 0.001);
        }
    }

    /// Structural regression: verify utility model with extreme conditions matches
    /// Phase 5 short-circuit for a deeply-below-threshold rebel scenario.
    /// Uses 10 agents at loyalty=0.0, sat=0.0 so rebel_utility = 1.5 (cap)
    /// with smoothstep(10, 3, 8) = 1.0. Gap of 1.0 over STAY_BASE makes
    /// Gumbel noise at T=0.3 negligible (~0.04% flip probability per agent).
    #[test]
    fn test_structural_regression_rebel_v1_vs_v2() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];

        // 10 agents at absolute minimum (maximizes rebel utility to cap)
        for _ in 0..10 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0);
            pool.set_loyalty(slot, 0.0);
            pool.set_satisfaction(slot, 0.0);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..10).collect();

        // V1: Phase 5 short-circuit — all 10 rebel
        let pd_v1 = evaluate_region_decisions_v1(&pool, &slots, &regions[0], &stats, 0);
        assert_eq!(pd_v1.rebellions.len(), 10);

        // V2: utility model — rebel_utility = 1.5, STAY_BASE = 0.5
        // Gap of 1.0 with T=0.3 makes noise flip astronomically unlikely
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pd_v2 = evaluate_region_decisions(&pool, &slots, &regions[0], &stats, 0, &mut rng);

        assert_eq!(pd_v2.rebellions.len(), pd_v1.rebellions.len(),
            "structural regression: v2 rebels={} vs v1 rebels={}",
            pd_v2.rebellions.len(), pd_v1.rebellions.len());
    }
}
