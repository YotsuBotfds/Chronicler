//! Demographic tick — age + die with rayon parallelism.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;

use crate::agent::{AGE_ADULT, AGE_ELDER, MORTALITY_ADULT, MORTALITY_ELDER, MORTALITY_YOUNG};
use crate::pool::AgentPool;
use crate::region::RegionState;

struct PendingEvents {
    deaths: Vec<usize>,
    aged: Vec<usize>,
}

impl PendingEvents {
    fn new() -> Self {
        Self {
            deaths: Vec::new(),
            aged: Vec::new(),
        }
    }
}

pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: [u8; 32],
    turn: u32,
) {
    let region_groups = pool.partition_by_region(regions.len() as u16);

    // Scoped reborrow: pool_ref is &AgentPool for the parallel closure.
    // Scope ends before sequential apply, so pool reverts to &mut.
    let pending: Vec<PendingEvents> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                let mut rng = ChaCha8Rng::from_seed(master_seed);
                rng.set_stream(region_id as u64 * 1000 + turn as u64);
                tick_region_demographics(pool_ref, slots, &regions[region_id], &mut rng)
            })
            .collect()
    };

    // Sequential apply
    for p in pending {
        for slot in &p.deaths {
            pool.kill(*slot);
        }
        for &slot in &p.aged {
            pool.increment_age(slot);
        }
    }
}

fn tick_region_demographics(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    rng: &mut ChaCha8Rng,
) -> PendingEvents {
    let mut pending = PendingEvents::new();
    let eco_stress = ecological_stress(region);
    for &slot in slots {
        let age = pool.age(slot);
        let base_rate = match age {
            0..AGE_ADULT => MORTALITY_YOUNG,
            AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
            _ => MORTALITY_ELDER,
        };
        if rng.gen::<f32>() < base_rate * eco_stress {
            pending.deaths.push(slot);
        } else {
            pending.aged.push(slot);
        }
    }
    pending
}

fn ecological_stress(region: &RegionState) -> f32 {
    let eco_health = (region.soil + region.water) / 2.0;
    1.0 + 2.0 * (1.0 - eco_health)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn make_healthy_region(id: u16) -> RegionState {
        RegionState {
            region_id: id,
            terrain: 0,
            carrying_capacity: 60,
            population: 60,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
        }
    }

    #[test]
    fn test_ecological_stress_healthy() {
        let r = make_healthy_region(0);
        assert!((ecological_stress(&r) - 1.6).abs() < 0.01);
    }

    #[test]
    fn test_ecological_stress_collapsed() {
        let mut r = make_healthy_region(0);
        r.soil = 0.0;
        r.water = 0.0;
        assert!((ecological_stress(&r) - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_tick_agents_reduces_population() {
        let mut pool = AgentPool::new(0);
        let regions = vec![make_healthy_region(0)];
        // Spawn at elder age (60+) so MORTALITY_ELDER (0.05) * eco_stress (1.6)
        // = 0.08 per agent per tick — guarantees deaths in 500 agents.
        for _ in 0..500 {
            pool.spawn(0, 0, Occupation::Farmer, 65);
        }
        let mut seed = [0u8; 32];
        seed[0] = 42;
        tick_agents(&mut pool, &regions, seed, 0);
        assert!(pool.alive_count() < 500);
        assert!(pool.alive_count() > 0);
    }

    #[test]
    fn test_tick_deterministic() {
        let regions = vec![make_healthy_region(0), make_healthy_region(1)];
        let mut seed = [0u8; 32];
        seed[0] = 99;
        let mut pool_a = AgentPool::new(0);
        let mut pool_b = AgentPool::new(0);
        for _ in 0..50 {
            pool_a.spawn(0, 0, Occupation::Farmer, 0);
            pool_b.spawn(0, 0, Occupation::Farmer, 0);
        }
        for _ in 0..50 {
            pool_a.spawn(1, 1, Occupation::Soldier, 0);
            pool_b.spawn(1, 1, Occupation::Soldier, 0);
        }
        for turn in 0..10 {
            tick_agents(&mut pool_a, &regions, seed, turn);
            tick_agents(&mut pool_b, &regions, seed, turn);
        }
        assert_eq!(pool_a.alive_count(), pool_b.alive_count());
    }
}
