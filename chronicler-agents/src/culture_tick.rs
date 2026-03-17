//! culture_tick: region-level cultural frequency distribution and environmental bias.
//!
//! `compute_cultural_distribution` counts how many agents in a region hold each
//! of the 6 cultural values, with named agents contributing NAMED_CULTURE_WEIGHT×.
//!
//! `apply_environmental_bias` adds phantom weight derived from the region's M34
//! resource types using the ENV_BIAS_TABLE.

use crate::agent;
use crate::pool::AgentPool;

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_test_pool(n: usize, values: &[[u8; 3]]) -> AgentPool {
        let mut pool = AgentPool::new(n);
        for v in values {
            pool.spawn(0, 0, Occupation::Farmer, 20, 0.5, 0.5, 0.5, v[0], v[1], v[2]);
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
}
