//! Demographics: age-dependent mortality with M26 ecological stress + satisfaction-gated fertility.

use crate::agent::*;
use crate::region::RegionState;

/// M26 per-variable ecological stress. Range: 1.0 (healthy) to 2.0 (collapsed).
pub fn ecological_stress(region: &RegionState) -> f32 {
    let soil_stress = (0.5 - region.soil) * ((0.5 - region.soil) > 0.0) as i32 as f32;
    let water_stress = (0.5 - region.water) * ((0.5 - region.water) > 0.0) as i32 as f32;
    1.0 + soil_stress + water_stress
}

/// War casualty multiplier applies to all soldier age brackets — intentional
/// divergence from roadmap draft which restricted to 20–60. Soldiers of any
/// age on an active front face elevated mortality.
pub fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool) -> f32 {
    let base = match age {
        0..AGE_ADULT => MORTALITY_YOUNG,
        AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
        _ => MORTALITY_ELDER,
    };
    let war_mult = 1.0 + (WAR_CASUALTY_MULTIPLIER - 1.0) * is_soldier_at_war as i32 as f32;
    base * eco_stress * war_mult
}

pub fn fertility_rate(age: u16, satisfaction: f32, occupation: u8, soil: f32) -> f32 {
    let eligible = (age >= FERTILITY_AGE_MIN
        && age <= FERTILITY_AGE_MAX
        && satisfaction > FERTILITY_SATISFACTION_THRESHOLD) as i32 as f32;
    let base = if occupation == 0 { FERTILITY_BASE_FARMER } else { FERTILITY_BASE_OTHER };
    let ecology_mod = 0.5 + soil * 0.5;
    base * ecology_mod * eligible
}

use rand::prelude::*;
use rand_chacha::ChaCha8Rng;
use rand_distr::StandardNormal;

/// Assign personality from civ mean + Gaussian noise. Immutable after spawn.
pub fn assign_personality(rng: &mut ChaCha8Rng, civ_mean: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise: f32 = rng.sample(StandardNormal);
        p[i] = (civ_mean[i] + noise * SPAWN_PERSONALITY_NOISE).clamp(-1.0, 1.0);
    }
    p
}

/// Inherit personality from parent + tighter Gaussian noise. For M39 wiring.
pub fn inherit_personality(rng: &mut ChaCha8Rng, parent: [f32; 3]) -> [f32; 3] {
    let mut p = [0.0f32; 3];
    for i in 0..3 {
        let noise: f32 = rng.sample(StandardNormal);
        p[i] = (parent[i] + noise * BIRTH_PERSONALITY_NOISE).clamp(-1.0, 1.0);
    }
    p
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(soil: f32, water: f32) -> RegionState {
        RegionState {
            region_id: 0, terrain: 0, carrying_capacity: 60, population: 40,
            soil, water, forest_cover: 0.3,
            adjacency_mask: 0, controller_civ: 0, trade_route_count: 0,
        }
    }

    #[test]
    fn test_eco_stress_healthy() {
        assert!((ecological_stress(&region(0.8, 0.7)) - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_both_low() {
        assert!((ecological_stress(&region(0.1, 0.2)) - 1.7).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_collapsed() {
        assert!((ecological_stress(&region(0.0, 0.0)) - 2.0).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_one_bad() {
        assert!((ecological_stress(&region(0.3, 0.6)) - 1.2).abs() < 0.01);
    }

    #[test]
    fn test_mortality_young_peaceful() {
        let rate = mortality_rate(10, 1.0, false);
        assert!((rate - MORTALITY_YOUNG).abs() < 0.001);
    }

    #[test]
    fn test_mortality_adult_stressed() {
        let rate = mortality_rate(30, 1.5, false);
        assert!((rate - MORTALITY_ADULT * 1.5).abs() < 0.001);
    }

    #[test]
    fn test_mortality_soldier_at_war() {
        let rate = mortality_rate(30, 1.0, true);
        assert!((rate - MORTALITY_ADULT * WAR_CASUALTY_MULTIPLIER).abs() < 0.001);
    }

    #[test]
    fn test_mortality_elder_war_stressed() {
        let rate = mortality_rate(65, 1.5, true);
        let expected = MORTALITY_ELDER * 1.5 * WAR_CASUALTY_MULTIPLIER;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_eligible_farmer() {
        let rate = fertility_rate(25, 0.6, 0, 0.8);
        let expected = 0.03 * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_eligible_soldier() {
        let rate = fertility_rate(25, 0.6, 1, 0.8);
        let expected = 0.015 * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_too_young() {
        assert!(fertility_rate(15, 0.8, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_too_old() {
        assert!(fertility_rate(46, 0.8, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_low_satisfaction() {
        assert!(fertility_rate(25, 0.4, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_bad_soil() {
        let rate = fertility_rate(25, 0.6, 0, 0.0);
        let expected = 0.03 * 0.5;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_boundary_age_min() {
        assert!(fertility_rate(16, 0.6, 0, 0.8) > 0.0);
    }

    #[test]
    fn test_fertility_boundary_age_max() {
        assert!(fertility_rate(45, 0.6, 0, 0.8) > 0.0);
    }

    #[test]
    fn test_assign_personality_neutral_mean() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let p = super::assign_personality(&mut rng, [0.0, 0.0, 0.0]);
        for &v in &p {
            assert!(v >= -1.0 && v <= 1.0, "personality out of range: {}", v);
        }
    }

    #[test]
    fn test_assign_personality_clamped() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        for seed_byte in 0..50u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let p = super::assign_personality(&mut rng, [0.3, -0.3, 0.3]);
            for &v in &p {
                assert!(v >= -1.0 && v <= 1.0, "personality out of range: {}", v);
            }
        }
    }

    #[test]
    fn test_inherit_personality_tighter_noise() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut sum = [0.0f64; 3];
        let n = 1000;
        for seed_byte in 0..n {
            let mut seed = [0u8; 32];
            seed[0] = (seed_byte % 256) as u8;
            seed[1] = (seed_byte / 256) as u8;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let p = super::inherit_personality(&mut rng, [0.5, 0.5, 0.5]);
            for i in 0..3 { sum[i] += p[i] as f64; }
        }
        for i in 0..3 {
            let mean = sum[i] / n as f64;
            assert!((mean - 0.5).abs() < 0.05,
                "dimension {} mean {} too far from parent 0.5", i, mean);
        }
    }
}
