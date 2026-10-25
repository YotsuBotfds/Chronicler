//! Demographics: age-dependent mortality with ecology/crowding stress and
//! satisfaction-gated fertility.

use crate::agent::*;
use crate::region::RegionState;

const CROWDING_STRESS_WEIGHT: f32 = 0.30;
const CROWDING_STRESS_CAP: f32 = 0.60;
// Correction (2026-10): until the tick measured crowding from the live agent
// count (see tick_region_demographics) this brake never engaged, and these
// thresholds were never exercised in a hybrid run. Tapering from 1.1x to zero
// at 2.5x lets regions settle near 2x capacity, where the satisfaction
// overcrowding penalty saturates; births now taper from capacity and stop at
// 1.6x, so crowding binds before misery does.
//
// Correction (2026-10, food balance): the 1.0-1.6x band was chosen while the
// ecology still read a population that Python's aggregate overflow migration
// had clamped towards effective capacity, so its interaction with the soil
// model was invisible. The ecology degrades soil whenever a region holds more
// people than its undegraded (potential) capacity and lets it recover only
// below 0.75x (`soil_recovery_pop_ratio`). A brake that only starts at 1.0x
// parks every region in the degradation band; with real populations visible,
// grain plains fell to soil 0.65 within 200 turns and kept falling. Births now
// taper from the recovery ratio and stop at potential capacity, the band in
// which the land neither degrades nor needs to recover. Mortality crowding
// stress is unchanged (it starts at 1.0x).
const FERTILITY_CROWDING_SOFT_START: f32 = 0.75;
const FERTILITY_CROWDING_ZERO: f32 = 1.00;
const FERTILITY_SATISFACTION_RAMP: f32 = 0.10;

// ---------------------------------------------------------------------------
// Hunger (2026-10, docs/integration/hunger-mortality.md)
// ---------------------------------------------------------------------------
// A region's food sufficiency (pre-consumption food over demand) and the run
// of turns it has stayed below the famine severity threshold give two
// components in [0, 1]:
//
// * dearth: the shortfall across the dearth band, 0 when fed and 1 at or
//   below the severity threshold: `min(1, (1 - s) / (1 - 0.6))`;
// * famine: the depth below the threshold, `(0.6 - s) / 0.6`, ramped in over
//   the turns a famine takes to declare (`min(1, run / 3)`), so a single lean
//   month is not a famine.
//
// The thresholds are the food-crisis labels' (Python
// `ecology.FAMINE_SEVERE_SUFFICIENCY`, `FAMINE_SEVERE_TURNS`). Mortality
// gains `1 + vulnerability * (DEARTH * dearth + FAMINE * famine)`; fertility
// is scaled by `(1 - DEARTH * dearth) * (1 - FAMINE * famine)`. Magnitudes
// (high-price years: deaths up a few percent to 10-20%, births down 5-15%;
// famines: crude death rates two to four times normal, most among young
// children, the old and the poor, births down a quarter to a half) were first
// held at the low end because world-wide climate famines with constant returns
// to farm labour could not end. With diminishing returns and regional climate
// (2026-10, docs/integration/farmland-climate.md) they are raised part of the
// way to the middle: the mid-range famine terms (deaths 1.5, births 0.6)
// failed the needs subset gate.
pub const HUNGER_SEVERE_SUFFICIENCY: f32 = crate::agent::FAMINE_MEMORY_THRESHOLD;
pub const HUNGER_FAMINE_TURNS: u16 = 3;
/// Mortality multiplier at the edge of the dearth band (vulnerability 1).
pub const HUNGER_DEARTH_MORTALITY: f32 = 0.10;
/// Added mortality multiplier of a total, sustained famine (vulnerability 1).
pub const HUNGER_FAMINE_MORTALITY: f32 = 1.00;
/// Births withheld at the edge of the dearth band.
pub const HUNGER_DEARTH_FERTILITY: f32 = 0.15;
/// Further share of births withheld in a total, sustained famine.
pub const HUNGER_FAMINE_FERTILITY: f32 = 0.45;
/// Vulnerability by age band: young children and the old carry the full
/// hunger hazard, older children and working-age adults half of it.
pub const HUNGER_CHILD_AGE: u16 = 5;
pub const HUNGER_VULNERABLE_WEIGHT: f32 = 1.0;
pub const HUNGER_ROBUST_WEIGHT: f32 = 0.5;
/// Adults' vulnerability spread by civ wealth percentile: the poorest carry
/// `1 + W/2`, the richest `1 - W/2` (children's own wealth is not their
/// household's, so they carry the age weight alone).
pub const HUNGER_POVERTY_WEIGHT: f32 = 0.5;

/// (dearth, famine) hunger components of a region this turn. `prev_run` is
/// the severe-shortage run up to the previous turn; this turn extends it
/// while sufficiency stays below the threshold.
#[inline]
pub fn hunger_components(food_sufficiency: f32, prev_run: u16) -> (f32, f32) {
    let s = food_sufficiency;
    if !(s < 1.0) {
        return (0.0, 0.0);
    }
    let dearth = ((1.0 - s) / (1.0 - HUNGER_SEVERE_SUFFICIENCY)).clamp(0.0, 1.0);
    if !(s < HUNGER_SEVERE_SUFFICIENCY) {
        return (dearth, 0.0);
    }
    let run = prev_run.saturating_add(1);
    let ramp = (run as f32 / HUNGER_FAMINE_TURNS as f32).min(1.0);
    let depth = ((HUNGER_SEVERE_SUFFICIENCY - s) / HUNGER_SEVERE_SUFFICIENCY).clamp(0.0, 1.0);
    (dearth, depth * ramp)
}

/// Hunger vulnerability of an agent: its age band, and for adults its civ
/// wealth percentile (0 poorest, 1 richest).
#[inline]
pub fn hunger_vulnerability(age: u16, wealth_percentile: f32) -> f32 {
    if age < HUNGER_CHILD_AGE {
        HUNGER_VULNERABLE_WEIGHT
    } else if age < AGE_ADULT {
        HUNGER_ROBUST_WEIGHT
    } else {
        let base = if age < AGE_ELDER { HUNGER_ROBUST_WEIGHT } else { HUNGER_VULNERABLE_WEIGHT };
        let poverty = 1.0 + HUNGER_POVERTY_WEIGHT * (0.5 - wealth_percentile.clamp(0.0, 1.0));
        base * poverty
    }
}

/// Mortality multiplier from hunger (1 when fed).
#[inline]
pub fn hunger_mortality_multiplier(vulnerability: f32, dearth: f32, famine: f32) -> f32 {
    1.0 + vulnerability * (HUNGER_DEARTH_MORTALITY * dearth + HUNGER_FAMINE_MORTALITY * famine)
}

/// Fertility multiplier from hunger (1 when fed; never 0, so it withholds
/// births without removing their draws).
#[inline]
pub fn hunger_fertility_multiplier(dearth: f32, famine: f32) -> f32 {
    (1.0 - HUNGER_DEARTH_FERTILITY * dearth) * (1.0 - HUNGER_FAMINE_FERTILITY * famine)
}

#[inline]
pub fn population_pressure(region: &RegionState) -> f32 {
    population_pressure_for(region, region.population as usize)
}

/// Pressure for an explicit head count (the tick passes the live agent count).
#[inline]
pub fn population_pressure_for(region: &RegionState, population: usize) -> f32 {
    if region.carrying_capacity == 0 {
        1.0
    } else {
        population as f32 / region.carrying_capacity as f32
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
    ecological_stress_with_pressure(region, population_pressure(region))
}

/// Ecological stress for an explicit population pressure.
pub fn ecological_stress_with_pressure(region: &RegionState, pop_pressure: f32) -> f32 {
    let soil_stress = (0.5 - region.soil).max(0.0);
    let water_stress = (0.5 - region.water).max(0.0);
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
/// Uncrowded: no carrying-capacity pressure (the crowding brake starts below
/// capacity since the 2026-10 food-balance correction, so "at capacity" is no
/// longer the neutral pressure).
pub fn fertility_rate(age: u16, satisfaction: f32, occupation: u8, soil: f32, water: f32) -> f32 {
    fertility_rate_with_pressure(age, satisfaction, occupation, soil, water, 0.0)
}

/// Fertility rate adjusted for carrying-capacity pressure in the current region.
/// V5: Added `water` parameter — ecology_mod now incorporates both soil and water,
/// matching the ecology model where both are co-equal reproductive resources.
pub fn fertility_rate_with_pressure(
    age: u16,
    satisfaction: f32,
    occupation: u8,
    soil: f32,
    water: f32,
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
    let ecology_mod = 0.5 + (soil * 0.5 + water * 0.5) * 0.5;
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
        // Uncrowded (pressure 0.0): the crowding brake does not mask the gate.
        let low = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD - 0.11, 0, 1.0, 1.0, 0.0);
        let mid = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD - 0.05, 0, 1.0, 1.0, 0.0);
        let high = fertility_rate_with_pressure(30, FERTILITY_SATISFACTION_THRESHOLD + 0.01, 0, 1.0, 1.0, 0.0);

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
        // V5: soil=0.8, water=0.8 → ecology_mod = 0.5 + (0.4+0.4)*0.5 = 0.9
        let rate = fertility_rate(25, 0.6, 0, 0.8, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_eligible_soldier() {
        let rate = fertility_rate(25, 0.6, 1, 0.8, 0.8);
        let expected = FERTILITY_BASE_OTHER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_too_young() {
        assert!(fertility_rate(15, 0.8, 0, 0.8, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_too_old() {
        assert!(fertility_rate(81, 0.8, 0, 0.8, 0.8) == 0.0);  // past FERTILITY_TAPER_AGE_MAX (80)
    }

    #[test]
    fn test_fertility_low_satisfaction() {
        let below_ramp = FERTILITY_SATISFACTION_THRESHOLD - FERTILITY_SATISFACTION_RAMP - 0.01;
        let mid_ramp = FERTILITY_SATISFACTION_THRESHOLD - FERTILITY_SATISFACTION_RAMP / 2.0;
        let gate = FERTILITY_SATISFACTION_THRESHOLD;
        assert_eq!(fertility_rate(25, below_ramp, 0, 0.8, 0.8), 0.0);
        assert!(fertility_rate(25, mid_ramp, 0, 0.8, 0.8) > 0.0);
        assert!(fertility_rate(25, gate, 0, 0.8, 0.8) > fertility_rate(25, mid_ramp, 0, 0.8, 0.8));
    }

    #[test]
    fn test_fertility_bad_soil() {
        // V5: soil=0.0, water=0.0 → ecology_mod = 0.5 + (0+0)*0.5 = 0.5
        let rate = fertility_rate(25, 0.6, 0, 0.0, 0.0);
        let expected = FERTILITY_BASE_FARMER * 0.5;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_crowding_soft_start_preserves_baseline() {
        let crowded = fertility_rate_with_pressure(
            25, 0.6, 0, 0.8, 0.8, FERTILITY_CROWDING_SOFT_START - 0.05,
        );
        let baseline = fertility_rate(25, 0.6, 0, 0.8, 0.8);
        assert!((crowded - baseline).abs() < 0.001);
    }

    #[test]
    fn test_fertility_crowding_strongly_suppresses_births() {
        let rate = fertility_rate_with_pressure(25, 0.6, 0, 0.8, 0.8, 0.9);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let crowding_mult = (FERTILITY_CROWDING_ZERO - 0.9)
            / (FERTILITY_CROWDING_ZERO - FERTILITY_CROWDING_SOFT_START);
        assert!(crowding_mult > 0.0 && crowding_mult < 0.5);
        assert!((rate - full * crowding_mult).abs() < 0.001);
    }

    #[test]
    fn test_hunger_components_fed_dearth_famine() {
        assert_eq!(hunger_components(1.0, 0), (0.0, 0.0));
        assert_eq!(hunger_components(2.0, 7), (0.0, 0.0));
        assert_eq!(hunger_components(f32::NAN, 0), (0.0, 0.0));
        let (d, f) = hunger_components(0.8, 0);
        assert!((d - 0.5).abs() < 1e-6 && f == 0.0);
        let (d, f) = hunger_components(HUNGER_SEVERE_SUFFICIENCY, 9);
        assert!((d - 1.0).abs() < 1e-6 && f == 0.0);
        // Below the line: depth ramped over the run, this turn included.
        let depth = (HUNGER_SEVERE_SUFFICIENCY - 0.3) / HUNGER_SEVERE_SUFFICIENCY;
        for prev in 0..5u16 {
            let (d, f) = hunger_components(0.3, prev);
            let ramp = ((prev + 1) as f32 / HUNGER_FAMINE_TURNS as f32).min(1.0);
            assert_eq!(d, 1.0);
            assert!((f - depth * ramp).abs() < 1e-6, "prev {} f {}", prev, f);
        }
        assert_eq!(hunger_components(0.0, u16::MAX), (1.0, 1.0));
    }

    #[test]
    fn test_hunger_vulnerability_by_age_and_wealth() {
        let child = hunger_vulnerability(2, 0.9);
        let youth = hunger_vulnerability(12, 0.0);
        let poor_adult = hunger_vulnerability(30, 0.0);
        let rich_adult = hunger_vulnerability(30, 1.0);
        let poor_elder = hunger_vulnerability(70, 0.0);
        let rich_elder = hunger_vulnerability(70, 1.0);
        assert_eq!(child, HUNGER_VULNERABLE_WEIGHT);
        assert_eq!(youth, HUNGER_ROBUST_WEIGHT);
        assert!(poor_adult > rich_adult);
        assert!(poor_elder > rich_elder);
        assert!(rich_elder > poor_adult);
        // The middle of the wealth ranking carries the age weight alone.
        assert!((hunger_vulnerability(30, 0.5) - HUNGER_ROBUST_WEIGHT).abs() < 1e-6);
        assert!((hunger_vulnerability(70, 0.5) - HUNGER_VULNERABLE_WEIGHT).abs() < 1e-6);
    }

    #[test]
    fn test_hunger_multipliers() {
        assert_eq!(hunger_mortality_multiplier(1.0, 0.0, 0.0), 1.0);
        assert_eq!(hunger_fertility_multiplier(0.0, 0.0), 1.0);
        let dearth = hunger_mortality_multiplier(1.0, 1.0, 0.0);
        let famine = hunger_mortality_multiplier(1.0, 1.0, 1.0);
        assert!((dearth - (1.0 + HUNGER_DEARTH_MORTALITY)).abs() < 1e-6);
        assert!((famine - (1.0 + HUNGER_DEARTH_MORTALITY + HUNGER_FAMINE_MORTALITY)).abs() < 1e-6);
        assert!(hunger_mortality_multiplier(0.5, 1.0, 1.0) < famine);
        let worst = hunger_fertility_multiplier(1.0, 1.0);
        assert!(worst > 0.0 && worst < hunger_fertility_multiplier(1.0, 0.0));
    }

    #[test]
    fn test_population_pressure_for_uses_explicit_head_count() {
        // The tick passes the live agent count; region.population may be a
        // stale or clamped Python-side figure.
        let mut r = region(0.8, 0.6);
        r.carrying_capacity = 40;
        r.population = 20;
        assert!((population_pressure_for(&r, 80) - 2.0).abs() < 1e-6);
        assert!((population_pressure(&r) - 0.5).abs() < 1e-6);
        assert!(ecological_stress_with_pressure(&r, 2.0) > ecological_stress(&r));
    }

    #[test]
    fn test_fertility_crowding_zeroes_extreme_overflow() {
        assert!(fertility_rate_with_pressure(
            25,
            0.6,
            0,
            0.8,
            0.8,
            FERTILITY_CROWDING_ZERO,
        ) == 0.0);
    }

    #[test]
    fn test_fertility_boundary_age_min() {
        assert!(fertility_rate(16, 0.6, 0, 0.8, 0.8) > 0.0);
    }

    #[test]
    fn test_fertility_full_at_55() {
        // Age 55 remains inside the full-rate fertility window.
        let rate = fertility_rate(55, 0.6, 0, 0.8, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_full_at_60() {
        // Age 60 = last full-rate year after the handoff retune.
        let rate = fertility_rate(60, 0.6, 0, 0.8, 0.8);
        let expected = FERTILITY_BASE_FARMER * 0.9;
        assert!((rate - expected).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_at_61() {
        // Age 61 = first taper year: 1.0 - 1/20
        let rate = fertility_rate(61, 0.6, 0, 0.8, 0.8);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let taper = 1.0 - 1.0 / (FERTILITY_TAPER_AGE_MAX - FERTILITY_FULL_AGE_MAX) as f32;
        assert!((rate - full * taper).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_midpoint() {
        // Age 70 sits midway through the taper (60..80): 1.0 - 10/20
        let rate = fertility_rate(70, 0.6, 0, 0.8, 0.8);
        let full = FERTILITY_BASE_FARMER * 0.9;
        let taper = 1.0 - 10.0 / (FERTILITY_TAPER_AGE_MAX - FERTILITY_FULL_AGE_MAX) as f32;
        assert!((rate - full * taper).abs() < 0.001);
    }

    #[test]
    fn test_fertility_taper_at_80() {
        // Age 80 = end of taper: 1.0 - 20/20 = 0.0
        assert!(fertility_rate(80, 0.6, 0, 0.8, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_past_taper() {
        // Age 81 = past taper range
        assert!(fertility_rate(81, 0.6, 0, 0.8, 0.8) == 0.0);
    }

    #[test]
    fn test_fertility_water_aware() {
        // V5 regression: water contributes to ecology_mod alongside soil.
        // High water should produce higher fertility than low water, all else equal.
        let rate_high_water = fertility_rate(25, 0.6, 0, 0.8, 0.8);
        let rate_low_water = fertility_rate(25, 0.6, 0, 0.8, 0.0);
        assert!(rate_high_water > rate_low_water,
            "high water ({}) should produce higher fertility than low water ({})",
            rate_high_water, rate_low_water);
        // Verify exact values:
        // soil=0.8, water=0.8: ecology_mod = 0.5 + (0.4+0.4)*0.5 = 0.9
        // soil=0.8, water=0.0: ecology_mod = 0.5 + (0.4+0.0)*0.5 = 0.7
        let expected_high = FERTILITY_BASE_FARMER * 0.9;
        let expected_low = FERTILITY_BASE_FARMER * 0.7;
        assert!((rate_high_water - expected_high).abs() < 0.001);
        assert!((rate_low_water - expected_low).abs() < 0.001);
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
