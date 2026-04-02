//! Demographics: age-dependent mortality with ecology/crowding stress and
//! satisfaction-gated fertility.

use crate::agent::*;
use crate::region::RegionState;

const CROWDING_STRESS_WEIGHT: f32 = 0.30;
const CROWDING_STRESS_CAP: f32 = 0.60;
const FERTILITY_CROWDING_SOFT_START: f32 = 1.10;
const FERTILITY_CROWDING_ZERO: f32 = 2.50;
const FERTILITY_SATISFACTION_RAMP: f32 = 0.10;

#[inline]
pub fn population_pressure(region: &RegionState) -> f32 {
    if region.carrying_capacity == 0 {
        1.0
    } else {
        region.population as f32 / region.carrying_capacity as f32
    }
}

#[inline]
fn crowding_fertility_modifier(pop_over_capacity: f32) -> f32 {
    if pop_over_capacity <= FERTILITY_CROWDING_SOFT_START {
        1.0
    } else {
        (
            (FERTILITY_CROWDING_ZERO - pop_over_capacity)
                / (FERTILITY_CROWDING_ZERO - FERTILITY_CROWDING_SOFT_START)
        )
        .clamp(0.0, 1.0)
    }
}

/// M26 per-variable ecological stress. Healthy terrain starts at 1.0; severe
/// crowding adds extra pressure on top of soil/water stress.
pub fn ecological_stress(region: &RegionState) -> f32 {
    let pop_pressure = population_pressure(region);
    let soil_stress = (0.5 - region.soil) * ((0.5 - region.soil) > 0.0) as i32 as f32;
    let water_stress = (0.5 - region.water) * ((0.5 - region.water) > 0.0) as i32 as f32;
    let crowding_stress =
        ((pop_pressure - 1.0) * CROWDING_STRESS_WEIGHT).clamp(0.0, CROWDING_STRESS_CAP);
    1.0 + soil_stress + water_stress + crowding_stress
}

/// War casualty multiplier applies to all soldier age brackets — intentional
/// divergence from roadmap draft which restricted to 20–60. Soldiers of any
/// age on an active front face elevated mortality.
///
/// Disease is multiplicative (M53 fix): `base * eco * war * (1 + disease * SCALE)`.
/// Previous formula was additive (`base * eco * war + disease`), which caused
/// disease_severity at cap (0.15) to dominate mortality at 16%/turn, dwarfing
/// base rates and all fertility. Multiplicative keeps disease as an amplifier:
/// at cap (0.15), mortality is 2.5x base; at baseline (0.01), 1.1x.
pub fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool, disease_severity: f32) -> f32 {
    let base = match age {
        0..AGE_ADULT => MORTALITY_YOUNG,
        AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
        _ => MORTALITY_ELDER,
    };
    let war_mult = 1.0 + (WAR_CASUALTY_MULTIPLIER - 1.0) * is_soldier_at_war as i32 as f32;
    let disease_mult = 1.0 + disease_severity * DISEASE_MORTALITY_SCALE;
    base * eco_stress * war_mult * disease_mult
}

/// Fertility with age taper: full rate through midlife, then a gradual decline.
/// Replaces hard cutoff at FERTILITY_AGE_MAX which caused entire cohorts to drop out
/// of the breeding pool simultaneously, creating generational handoff failures.
pub fn fertility_rate(age: u16, satisfaction: f32, occupation: u8, soil: f32) -> f32 {
    fertility_rate_with_pressure(age, satisfaction, occupation, soil, 1.0)
}

/// Fertility rate adjusted for carrying-capacity pressure in the current region.
pub fn fertility_rate_with_pressure(
    age: u16,
    satisfaction: f32,
    occupation: u8,
    soil: f32,
    pop_over_capacity: f32,
) -> f32 {
    let age_mult = if age < FERTILITY_AGE_MIN {
        0.0
    } else if age <= FERTILITY_FULL_AGE_MAX {
        1.0
    } else if age <= FERTILITY_TAPER_AGE_MAX {
        1.0 - (age - FERTILITY_FULL_AGE_MAX) as f32
            / (FERTILITY_TAPER_AGE_MAX - FERTILITY_FULL_AGE_MAX) as f32
    } else {
        0.0
    };
    // Smooth the satisfaction gate so fertility does not cliff-drop at a
    // single threshold, which otherwise creates cohort spikes when satisfaction
    // oscillates around the tuning point.
    let sat_gate = ((satisfaction - (FERTILITY_SATISFACTION_THRESHOLD - FERTILITY_SATISFACTION_RAMP))
        / FERTILITY_SATISFACTION_RAMP)
        .clamp(0.0, 1.0);
    let base = if occupation == 0 { FERTILITY_BASE_FARMER } else { FERTILITY_BASE_OTHER };
    let ecology_mod = 0.5 + soil * 0.5;
    let crowding_mod = crowding_fertility_modifier(pop_over_capacity);
    base * ecology_mod * age_mult * sat_gate * crowding_mod
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
        let mut r = RegionState::new(0);
        r.population = 40;
        r.soil = soil;
        r.water = water;
        r.controller_civ = 0;
        r
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
    fn test_population_pressure_over_capacity() {
        let mut r = region(0.8, 0.7);
        r.carrying_capacity = 60;
        r.population = 150;
        assert!((population_pressure(&r) - 2.5).abs() < 0.01);
    }

    #[test]
    fn test_eco_stress_includes_crowding() {
        let mut r = region(0.8, 0.7);
        r.carrying_capacity = 60;
        r.population = 150;
        let expected = 1.0 + ((2.5 - 1.0) * CROWDING_STRESS_WEIGHT).min(CROWDING_STRESS_CAP);
        assert!((ecological_stress(&r) - expected).abs() < 0.01);
    }

    #[test]
    fn test_fertility_satisfaction_gate_ramps_smoothly() {
        let low = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD - 0.11, 0, 1.0, 1.0);
        let mid = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD - 0.05, 0, 1.0, 1.0);
        let high = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD + 0.01, 0, 1.0, 1.0);

        assert_eq!(low, 0.0);
        assert!(mid > 0.0 && mid < high);
        assert!(high > 0.0);
    }

    #[test]
    fn test_mortality_young_peaceful() {
        let rate = mortality_rate(10, 1.0, false, 0.0);
        assert!((rate - MORTALITY_YOUNG).abs() < 0.001);
    }

    #[test]
    fn test_mortality_adult_stressed() {
        let rate = mortality_rate(30, 1.5, false, 0.0);
        assert!((rate - MORTALITY_ADULT * 1.5).abs() < 0.001);
    }

    #[test]
    fn test_mortality_soldier_at_war() {
        let rate = mortality_rate(30, 1.0, true, 0.0);
        assert!((rate - MORTALITY_ADULT * WAR_CASUALTY_MULTIPLIER).abs() < 0.001);
    }

    #[test]
    fn test_mortality_elder_war_stressed() {
        let rate = mortality_rate(65, 1.5, true, 0.0);
        let expected = MORTALITY_ELDER * 1.5 * WAR_CASUALTY_MULTIPLIER;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_mortality_with_disease() {
        // M53: disease is multiplicative — (1 + 0.05 * DISEASE_MORTALITY_SCALE)
        let rate = mortality_rate(30, 1.0, false, 0.05);
        let expected = MORTALITY_ADULT * (1.0 + 0.05 * DISEASE_MORTALITY_SCALE);
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_mortality_disease_plus_war() {
        // M53: disease multiplicative with war
        let rate = mortality_rate(30, 1.0, true, 0.10);
        let expected = MORTALITY_ADULT * WAR_CASUALTY_MULTIPLIER * (1.0 + 0.10 * DISEASE_MORTALITY_SCALE);
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_mortality_no_disease() {
        let rate = mortality_rate(30, 1.0, false, 0.0);
        assert!((rate - MORTALITY_ADULT).abs() < 0.001);
    }

    #[test]
    fn test_mortality_disease_at_cap() {
        // At disease cap (0.15), mortality should rise meaningfully without
        // dominating the demographic loop.
        let rate = mortality_rate(30, 1.0, false, 0.15);
        let expected = MORTALITY_ADULT * (1.0 + 0.15 * DISEASE_MORTALITY_SCALE);
        assert!((rate - expected).abs() < 0.001);
        // Verify the multiplier stays close to 1.9x at SCALE=6.
        assert!((rate / MORTALITY_ADULT - 1.9).abs() < 0.01);
        // And crucially, the rate remains well below the old additive blow-up regime.
        assert!(rate < 0.02, "disease at cap should stay near 1.9x base, got {}", rate);
    }

    #[test]
    fn test_fertility_eligible_farmer() {
        let rate = fertility_rate(25, 0.6, 0, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;  // M53: use constant, not hardcoded
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_eligible_soldier() {
        let rate = fertility_rate(25, 0.6, 1, 0.8);
        let expected = FERTILITY_BASE_OTHER * 0.9;  // M53: use constant, not hardcoded
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_too_young() {
        assert!(fertility_rate(15, 0.8, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_too_old() {
        assert!(fertility_rate(81, 0.8, 0, 0.8) == 0.0);  // past FERTILITY_TAPER_AGE_MAX (80)
    }

    #[test]
    fn test_fertility_low_satisfaction() {
        let below_ramp = FERTILITY_SATISFACTION_THRESHOLD - FERTILITY_SATISFACTION_RAMP - 0.01;
        let mid_ramp = FERTILITY_SATISFACTION_THRESHOLD - FERTILITY_SATISFACTION_RAMP / 2.0;
        let gate = FERTILITY_SATISFACTION_THRESHOLD;
        assert_eq!(fertility_rate(25, below_ramp, 0, 0.8), 0.0);
        assert!(fertility_rate(25, mid_ramp, 0, 0.8) > 0.0);
        assert!(fertility_rate(25, gate, 0, 0.8) > fertility_rate(25, mid_ramp, 0, 0.8));
    }

    #[test]
    fn test_fertility_bad_soil() {
        let rate = fertility_rate(25, 0.6, 0, 0.0);
        let expected = FERTILITY_BASE_FARMER * 0.5;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_crowding_soft_start_preserves_baseline() {
        let crowded = fertility_rate_with_pressure(25, 0.6, 0, 0.8, 1.05);
        let baseline = fertility_rate(25, 0.6, 0, 0.8);
        assert!((crowded - baseline).abs() < 0.001);
    }

    #[test]
    fn test_fertility_crowding_strongly_suppresses_births() {
        let rate = fertility_rate_with_pressure(25, 0.6, 0, 0.8, 2.0);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let crowding_mult = (FERTILITY_CROWDING_ZERO - 2.0)
            / (FERTILITY_CROWDING_ZERO - FERTILITY_CROWDING_SOFT_START);
        assert!((rate - full * crowding_mult).abs() < 0.001);
    }

    #[test]
    fn test_fertility_crowding_zeroes_extreme_overflow() {
        assert!(fertility_rate_with_pressure(
            25,
            0.6,
            0,
            0.8,
            FERTILITY_CROWDING_ZERO,
        ) == 0.0);
    }

    #[test]
    fn test_fertility_boundary_age_min() {
        assert!(fertility_rate(16, 0.6, 0, 0.8) > 0.0);
    }

    #[test]
    fn test_fertility_full_at_55() {
        // Age 55 remains inside the full-rate fertility window.
        let rate = fertility_rate(55, 0.6, 0, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_full_at_60() {
        // Age 60 = last full-rate year after the handoff retune.
        let rate = fertility_rate(60, 0.6, 0, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_at_61() {
        // Age 61 = first taper year: 1.0 - 1/20
        let rate = fertility_rate(61, 0.6, 0, 0.8);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let taper = 1.0 - 1.0 / (FERTILITY_TAPER_AGE_MAX - FERTILITY_FULL_AGE_MAX) as f32;
        assert!((rate - full * taper).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_midpoint() {
        // Age 70 sits midway through the taper (60..80): 1.0 - 10/20
        let rate = fertility_rate(70, 0.6, 0, 0.8);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let taper = 1.0 - 10.0 / (FERTILITY_TAPER_AGE_MAX - FERTILITY_FULL_AGE_MAX) as f32;
        assert!((rate - full * taper).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_at_80() {
        // Age 80 = end of taper: 1.0 - 20/20 = 0.0
        assert!(fertility_rate(80, 0.6, 0, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_past_taper() {
        // Age 81 = past taper range
        assert!(fertility_rate(81, 0.6, 0, 0.8) == 0.0);
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
