//! culture_tick: region-level cultural frequency distribution and environmental bias.
//!
//! `compute_cultural_distribution` counts how many agents in a region hold each
//! of the 6 cultural values, with named agents contributing NAMED_CULTURE_WEIGHT×.
//!
//! `apply_environmental_bias` adds phantom weight derived from the region's M34
//! resource types using the ENV_BIAS_TABLE.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// Environmental bias table: resource_type (0-7) → value bias weights (6 values).
/// Sparse: most entries are 0.0. Primary bias = 1.0, secondary = 0.5.
const ENV_BIAS_TABLE: [[f32; 6]; 8] = [
    // Freedom, Order, Tradition, Knowledge, Honor, Cunning
    [0.0, 0.5, 1.0, 0.0, 0.0, 0.0], // GRAIN(0):      Tradition(primary), Order(secondary)
    [0.0, 0.0, 1.0, 0.0, 0.0, 0.0], // TIMBER(1):     Tradition(primary)
    [0.0, 0.0, 0.0, 1.0, 0.0, 0.5], // BOTANICALS(2): Knowledge(primary), Cunning(secondary)
    [1.0, 0.0, 0.0, 0.0, 0.0, 0.5], // FISH(3):       Freedom(primary), Cunning(secondary)
    [0.5, 0.0, 0.0, 0.0, 0.0, 1.0], // SALT(4):       Cunning(primary), Freedom(secondary)
    [0.0, 0.5, 0.0, 0.0, 1.0, 0.0], // ORE(5):        Honor(primary), Order(secondary)
    [0.0, 0.0, 0.0, 0.5, 0.0, 1.0], // PRECIOUS(6):   Cunning(primary), Knowledge(secondary)
    [1.0, 0.0, 0.0, 0.5, 0.0, 0.0], // EXOTIC(7):     Freedom(primary), Knowledge(secondary)
];

/// Run cultural drift for all agents in a region.
/// Called as Rust tick stage 6, after demographics.
pub fn culture_tick(
    pool: &mut AgentPool,
    slots: &[usize],
    region: &RegionState,
    master_seed: [u8; 32],
    turn: u32,
    region_id: usize,
) {
    if slots.is_empty() { return; }

    // 1. Recompute frequency distribution
    let mut dist = compute_cultural_distribution(pool, slots);

    // 2. Apply environmental bias from resources
    apply_environmental_bias(&mut dist, &region.resource_types, region.population);

    // 3. If INVEST_CULTURE active, add bonus weight to controller's values
    if region.culture_investment_active {
        let bonus = (region.population as f32 * agent::INVEST_CULTURE_BONUS) as u16;
        for &cv in &region.controller_values {
            if cv != agent::CULTURAL_VALUE_EMPTY && (cv as usize) < agent::NUM_CULTURAL_VALUES {
                dist[cv as usize] = dist[cv as usize].saturating_add(bonus);
            }
        }
    }

    // 4. Per-agent drift with dedicated RNG stream
    let mut rng = ChaCha8Rng::from_seed(master_seed);
    rng.set_stream(region_id as u64 * 1000 + turn as u64 + agent::CULTURE_DRIFT_OFFSET);

    for &slot in slots {
        if !pool.alive[slot] { continue; }
        drift_agent(slot, pool, &dist, agent::CULTURAL_DRIFT_RATE, &mut rng);
    }
}

/// Count how many agents in `slots` hold each cultural value.
/// Named agents (IS_NAMED bit set) contribute NAMED_CULTURE_WEIGHT instead of 1.
/// Slots for dead agents and CULTURAL_VALUE_EMPTY sentinels are skipped.
pub fn compute_cultural_distribution(
    pool: &AgentPool,
    slots: &[usize],
) -> [u16; agent::NUM_CULTURAL_VALUES] {
    let mut dist = [0u16; agent::NUM_CULTURAL_VALUES];
    for &slot in slots {
        if !pool.alive[slot] {
            continue;
        }
        let weight = if pool.is_named(slot) {
            agent::NAMED_CULTURE_WEIGHT
        } else {
            1
        };
        for &val in &[
            pool.cultural_value_0[slot],
            pool.cultural_value_1[slot],
            pool.cultural_value_2[slot],
        ] {
            if val != agent::CULTURAL_VALUE_EMPTY && (val as usize) < agent::NUM_CULTURAL_VALUES {
                dist[val as usize] = dist[val as usize].saturating_add(weight);
            }
        }
    }
    dist
}

/// Add phantom cultural weight from the region's resource environment.
///
/// For each of the 3 resource slots (slot_weight = ENV_SLOT_WEIGHTS[i]):
///   phantom_votes = floor(population × ENV_BIAS_FRACTION × slot_weight × bias)
///
/// resource_types entries of 255 or ≥ 8 are treated as empty slots and skipped.
pub fn apply_environmental_bias(
    dist: &mut [u16; agent::NUM_CULTURAL_VALUES],
    resource_types: &[u8; 3],
    population: u16,
) {
    let phantom_base = (population as f32 * agent::ENV_BIAS_FRACTION) as u16;
    for (slot_idx, &rtype) in resource_types.iter().enumerate() {
        if rtype == 255 || rtype as usize >= 8 {
            continue;
        }
        let slot_weight = agent::ENV_SLOT_WEIGHTS[slot_idx];
        let bias_row = &ENV_BIAS_TABLE[rtype as usize];
        for (val_idx, &bias) in bias_row.iter().enumerate() {
            if bias > 0.0 {
                let phantom = (phantom_base as f32 * slot_weight * bias) as u16;
                dist[val_idx] = dist[val_idx].saturating_add(phantom);
            }
        }
    }
}

/// Attempt to drift each of an agent's cultural value slots.
/// Returns true if any value changed.
///
/// Slots are processed tertiary-first (index 2 → 0). For each slot, a probability
/// roll is made against `base_drift_rate * DRIFT_SLOT_WEIGHTS[value_slot]` plus an
/// optional dissatisfaction bonus. If the roll passes, a new value is sampled from
/// `distribution` excluding all three of the agent's current values (re-read each
/// iteration to avoid intra-tick duplicates).
pub fn drift_agent(
    slot: usize,
    pool: &mut AgentPool,
    distribution: &[u16; agent::NUM_CULTURAL_VALUES],
    base_drift_rate: f32,
    rng: &mut ChaCha8Rng,
) -> bool {
    let mut changed = false;

    let sat_bonus = if pool.satisfactions[slot] < agent::DISSATISFIED_THRESHOLD {
        agent::DISSATISFIED_DRIFT_BONUS
    } else {
        0.0
    };

    for value_slot in (0..3).rev() {  // Tertiary first, primary last
        // Re-read current values each iteration to prevent intra-tick duplicates.
        let current_values = [
            pool.cultural_value_0[slot],
            pool.cultural_value_1[slot],
            pool.cultural_value_2[slot],
        ];

        let slot_rate = (base_drift_rate + sat_bonus) * agent::DRIFT_SLOT_WEIGHTS[value_slot];
        if rng.gen::<f32>() >= slot_rate { continue; }

        // Sample new value from distribution, excluding current values.
        let total_weight: u32 = distribution.iter().enumerate()
            .filter(|(idx, _)| !current_values.contains(&(*idx as u8)))
            .map(|(_, &w)| w as u32)
            .sum();

        if total_weight == 0 { continue; }

        let mut roll = rng.gen_range(0..total_weight);
        let mut new_val = current_values[value_slot];
        for (idx, &w) in distribution.iter().enumerate() {
            if current_values.contains(&(idx as u8)) { continue; }
            if roll < w as u32 { new_val = idx as u8; break; }
            roll -= w as u32;
        }

        if new_val != current_values[value_slot] {
            match value_slot {
                0 => pool.cultural_value_0[slot] = new_val,
                1 => pool.cultural_value_1[slot] = new_val,
                2 => pool.cultural_value_2[slot] = new_val,
                _ => unreachable!(),
            }
            changed = true;
        }
    }
    changed
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_test_pool(n: usize, values: &[[u8; 3]]) -> AgentPool {
        let mut pool = AgentPool::new(n);
        for v in values {
            pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, v[0], v[1], v[2], crate::agent::BELIEF_NONE);
        }
        pool
    }

    #[test]
    fn test_compute_distribution_basic() {
        let pool = make_test_pool(4, &[[4, 3, 2], [4, 1, 0], [4, 5, 2]]);
        let slots: Vec<usize> = (0..3).collect();
        let dist = compute_cultural_distribution(&pool, &slots);
        assert_eq!(dist[4], 3); // Honor: all 3
        assert_eq!(dist[3], 1); // Knowledge: 1
        assert_eq!(dist[2], 2); // Tradition: 2
        assert_eq!(dist[1], 1); // Order: 1
        assert_eq!(dist[0], 1); // Freedom: 1
        assert_eq!(dist[5], 1); // Cunning: 1
    }

    #[test]
    fn test_compute_distribution_named_agent_weight() {
        let mut pool = make_test_pool(4, &[[4, 3, 2], [0, 1, 5]]);
        pool.life_events[0] |= agent::IS_NAMED;
        let slots: Vec<usize> = (0..2).collect();
        let dist = compute_cultural_distribution(&pool, &slots);
        assert_eq!(dist[4], 5); // Honor: 5× named
        assert_eq!(dist[3], 5); // Knowledge: 5× named
        assert_eq!(dist[2], 5); // Tradition: 5× named
        assert_eq!(dist[0], 1); // Freedom: 1 unnamed
    }

    #[test]
    fn test_env_bias_ore_region() {
        let resource_types = [5u8, 255, 255]; // ORE only
        let population = 200u16;
        let mut dist = [0u16; 6];
        apply_environmental_bias(&mut dist, &resource_types, population);
        assert_eq!(dist[4], 10); // Honor: 200*0.05*1.0*1.0 = 10
        assert_eq!(dist[1], 5);  // Order: 200*0.05*1.0*0.5 = 5
    }

    #[test]
    fn test_env_bias_slot_weighted() {
        let resource_types = [0u8, 3, 255]; // GRAIN + FISH
        let population = 200u16;
        let mut dist = [0u16; 6];
        apply_environmental_bias(&mut dist, &resource_types, population);
        assert_eq!(dist[2], 10); // Tradition from GRAIN slot 0 (×1.0)
        assert_eq!(dist[1], 5);  // Order from GRAIN slot 0
        assert_eq!(dist[0], 5);  // Freedom from FISH slot 1 (×0.5): 10*0.5*1.0 = 5
    }

    #[test]
    fn test_env_bias_table_sparse() {
        for (rtype, row) in ENV_BIAS_TABLE.iter().enumerate() {
            let nonzero = row.iter().filter(|&&v| v > 0.0).count();
            assert!(nonzero <= 2, "Resource {} has {} nonzero entries", rtype, nonzero);
        }
    }

    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn test_drift_no_duplicate_values() {
        let mut pool = make_test_pool(4, &[[4, 3, 2]]);
        let mut rng = ChaCha8Rng::seed_from_u64(42);
        let dist = [100u16, 0, 0, 0, 0, 0]; // Heavy Freedom bias
        for _ in 0..100 {
            drift_agent(0, &mut pool, &dist, 1.0, &mut rng);
            let v0 = pool.cultural_value_0[0];
            let v1 = pool.cultural_value_1[0];
            let v2 = pool.cultural_value_2[0];
            assert!(v0 != v1 || v0 == agent::CULTURAL_VALUE_EMPTY);
            assert!(v0 != v2 || v0 == agent::CULTURAL_VALUE_EMPTY);
            assert!(v1 != v2 || v1 == agent::CULTURAL_VALUE_EMPTY);
        }
    }

    #[test]
    fn test_drift_slot_weighted_rates() {
        let mut slot_0_drifts = 0u32;
        let mut slot_2_drifts = 0u32;
        for seed in 0..10_000u64 {
            let mut pool = make_test_pool(4, &[[4, 3, 2]]);
            let mut rng = ChaCha8Rng::seed_from_u64(seed);
            let dist = [50u16, 50, 0, 0, 0, 50];
            let orig_0 = pool.cultural_value_0[0];
            let orig_2 = pool.cultural_value_2[0];
            drift_agent(0, &mut pool, &dist, agent::CULTURAL_DRIFT_RATE, &mut rng);
            if pool.cultural_value_0[0] != orig_0 { slot_0_drifts += 1; }
            if pool.cultural_value_2[0] != orig_2 { slot_2_drifts += 1; }
        }
        let ratio = slot_2_drifts as f64 / slot_0_drifts.max(1) as f64;
        assert!(ratio > 2.0 && ratio < 4.5,
            "Drift ratio slot2/slot0 = {:.2} (expected ~3.0), s0={}, s2={}",
            ratio, slot_0_drifts, slot_2_drifts);
    }
}
