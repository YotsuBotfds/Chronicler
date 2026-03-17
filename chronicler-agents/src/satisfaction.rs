//! Branchless satisfaction formula — computes per-agent satisfaction from
//! ecology, civ state, and occupation context.

use crate::region::RegionState;
use crate::signals::CivShock;

const FAMINE_YIELD_THRESHOLD: f32 = 0.12;
const PEAK_YIELD: f32 = 1.0;

/// Food types: GRAIN=0, BOTANICALS=2, FISH=3, EXOTIC=7
fn is_food(rtype: u8) -> bool {
    matches!(rtype, 0 | 2 | 3 | 7)
}

pub fn resource_satisfaction(region: &RegionState) -> f32 {
    let primary_yield = region.resource_yields[0];
    let sat = (primary_yield - FAMINE_YIELD_THRESHOLD)
            / (PEAK_YIELD - FAMINE_YIELD_THRESHOLD);
    sat.clamp(0.0, 1.0)
}

pub fn trade_satisfaction(region: &RegionState) -> f32 {
    let mut trade_score: f32 = 0.0;
    for i in 0..3 {
        let rtype = region.resource_types[i];
        let yield_val = region.resource_yields[i];
        if rtype != 255 && yield_val > 0.0 {
            let weight = if is_food(rtype) { 0.15 } else { 0.35 };
            trade_score += weight;
        }
    }
    trade_score.clamp(0.1, 1.0)
}

/// Compute per-occupation shock penalty using general + specific pattern.
/// All occupations get baseline sensitivity to all shocks,
/// plus stronger reaction to their domain shock.
pub fn compute_shock_penalty(occupation: u8, shock: &CivShock) -> f32 {
    let general = shock.stability * 0.15
                + shock.economy * 0.05
                + shock.military * 0.05
                + shock.culture * 0.05;

    let specific = match occupation {
        0 => shock.economy * 0.20,    // Farmer: economy-sensitive
        1 => shock.military * 0.20,   // Soldier: military-sensitive
        2 => shock.economy * 0.30,    // Merchant: strongly economy-sensitive
        3 => shock.culture * 0.20,    // Scholar: culture-sensitive
        _ => shock.stability * 0.20,  // Priest: stability-sensitive
    };

    general + specific
}

/// Count overlap between two sets of 3 cultural values (0xFF = empty/ignored).
/// Returns distance = 3 - overlap_count.
#[inline]
pub fn cultural_distance(agent_values: [u8; 3], controller_values: [u8; 3]) -> u8 {
    let mut overlap: u8 = 0;
    for &av in &agent_values {
        if av == crate::agent::CULTURAL_VALUE_EMPTY { continue; }
        for &cv in &controller_values {
            if cv == crate::agent::CULTURAL_VALUE_EMPTY { continue; }
            if av == cv { overlap += 1; break; }
        }
    }
    3 - overlap
}

#[inline]
pub fn compute_cultural_penalty(agent_values: [u8; 3], controller_values: [u8; 3]) -> f32 {
    let dist = cultural_distance(agent_values, controller_values);
    dist as f32 * crate::agent::CULTURAL_MISMATCH_WEIGHT
}

#[inline]
pub fn apply_penalty_cap(total_penalty: f32) -> f32 {
    total_penalty.min(crate::agent::PENALTY_CAP)
}

/// Compute satisfaction for a single agent. All inputs pre-fetched.
/// Branchless: bool-as-f32 masks for auto-vectorization.
pub fn compute_satisfaction(
    occupation: u8,
    soil: f32,
    water: f32,
    civ_stability: u8,
    demand_supply_ratio: f32,
    pop_over_capacity: f32,
    civ_at_war: bool,
    region_contested: bool,
    occ_matches_faction: bool,
    is_displaced: bool,
    trade_routes: u8,
    faction_influence: f32,
    shock: &CivShock,
) -> f32 {
    let base = match occupation {
        0 => 0.4 + soil * 0.3 + water * 0.2,                      // Farmer
        1 => 0.5 + faction_influence * 0.3,                        // Soldier
        2 => 0.4 + (trade_routes as f32 / 3.0).min(1.0) * 0.3,   // Merchant
        3 => 0.5 + faction_influence * 0.2,                        // Scholar
        _ => 0.6 - (1.0 - civ_stability as f32 / 100.0) * 0.2,   // Priest
    };

    let stability_bonus = civ_stability as f32 / 200.0;

    let ds_raw = demand_supply_ratio * 0.2;
    let ds_bonus = ds_raw.clamp(-0.2, 0.2);

    let overcrowding_raw = (pop_over_capacity - 1.0) * 0.3;
    let overcrowding = overcrowding_raw * (overcrowding_raw > 0.0) as i32 as f32;

    let war_pen = 0.15 * civ_at_war as i32 as f32
                + 0.10 * region_contested as i32 as f32;

    let faction_bonus = 0.05 * occ_matches_faction as i32 as f32;

    let displacement_pen = 0.10 * is_displaced as i32 as f32;

    let shock_pen = compute_shock_penalty(occupation, shock);

    (base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen + shock_pen)
        .clamp(0.0, 1.0)
}

/// Wraps compute_satisfaction(), subtracting the cultural and religious mismatch penalties (capped).
pub fn compute_satisfaction_with_culture(
    occupation: u8,
    soil: f32,
    water: f32,
    civ_stability: u8,
    demand_supply_ratio: f32,
    pop_over_capacity: f32,
    civ_at_war: bool,
    region_contested: bool,
    occ_matches_faction: bool,
    is_displaced: bool,
    trade_routes: u8,
    faction_influence: f32,
    shock: &CivShock,
    agent_values: [u8; 3],
    controller_values: [u8; 3],
    agent_belief: u8,
    majority_belief: u8,
    has_temple: bool,
    persecution_intensity: f32,
) -> f32 {
    let base_sat = compute_satisfaction(
        occupation,
        soil,
        water,
        civ_stability,
        demand_supply_ratio,
        pop_over_capacity,
        civ_at_war,
        region_contested,
        occ_matches_faction,
        is_displaced,
        trade_routes,
        faction_influence,
        shock,
    );
    let cultural_pen = compute_cultural_penalty(agent_values, controller_values);
    // M37: religious mismatch — binary (match or not)
    let religious_pen = if agent_belief != majority_belief
        && agent_belief != crate::agent::BELIEF_NONE
        && majority_belief != crate::agent::BELIEF_NONE
    {
        crate::agent::RELIGIOUS_MISMATCH_WEIGHT
    } else {
        0.0
    };
    // M38b: Persecution penalty
    let mut penalty = 0.0f32;
    if agent_belief != majority_belief {
        penalty += crate::agent::PERSECUTION_SAT_WEIGHT * persecution_intensity;
    }
    // M38a: temple priest bonus — faith-blind (Decision 6)
    let temple_bonus = if occupation == 4 && has_temple {
        0.10  // TEMPLE_PRIEST_BONUS [CALIBRATE]
    } else {
        0.0
    };
    let total_non_eco_penalty = apply_penalty_cap(cultural_pen + religious_pen + penalty);
    (base_sat - total_non_eco_penalty + temple_bonus).clamp(0.0, 1.0)
}

/// Target occupation ratios for a region based on terrain and ecology.
/// Returns [farmer, soldier, merchant, scholar, priest] ratios summing to ~1.0.
/// Cold path — called once per region per tick, not per agent.
pub fn target_occupation_ratio(terrain: u8, soil: f32, _water: f32, demand_shifts: [f32; 5]) -> [f32; 5] {
    let mut r = [0.60f32, 0.15, 0.10, 0.10, 0.05];

    match terrain {
        1 => { r[1] += 0.05; r[0] -= 0.05; }  // Mountains: more soldiers
        2 => { r[2] += 0.05; r[0] -= 0.05; }  // Coast: more merchants
        3 => { r[0] += 0.05; r[2] -= 0.05; }  // Forest: more farmers
        4 => { r[1] += 0.05; r[0] -= 0.10; r[4] += 0.05; } // Desert
        _ => {}
    }

    if soil < 0.3 {
        r[0] -= 0.10;
        r[1] += 0.05;
        r[4] += 0.05;
    }

    // Apply demand shifts with 1% floor — never zero demand
    for i in 0..5 {
        r[i] = (r[i] + demand_shifts[i]).max(0.01);
    }
    let sum: f32 = r.iter().sum();
    for v in &mut r { *v /= sum; }

    r
}

#[cfg(test)]
mod m36_tests {
    use super::*;

    #[test]
    fn test_cultural_distance_full_overlap() {
        assert_eq!(cultural_distance([4, 3, 2], [4, 3, 2]), 0);
    }

    #[test]
    fn test_cultural_distance_partial_overlap() {
        assert_eq!(cultural_distance([4, 3, 2], [3, 2, 0]), 1);
    }

    #[test]
    fn test_cultural_distance_no_overlap() {
        assert_eq!(cultural_distance([4, 3, 2], [0, 1, 5]), 3);
    }

    #[test]
    fn test_cultural_distance_order_independent() {
        assert_eq!(cultural_distance([4, 3, 2], [2, 4, 3]), 0);
        assert_eq!(cultural_distance([4, 3, 2], [0, 3, 4]), 1);
    }

    #[test]
    fn test_cultural_distance_with_empty_slots() {
        // 0xFF sentinel should not self-match
        assert_eq!(cultural_distance([4, 3, 0xFF], [4, 3, 0xFF]), 1);
    }

    #[test]
    fn test_cultural_penalty_zero_distance() {
        let pen = compute_cultural_penalty([4, 3, 2], [4, 3, 2]);
        assert_eq!(pen, 0.0);
    }

    #[test]
    fn test_cultural_penalty_max_distance() {
        let pen = compute_cultural_penalty([4, 3, 2], [0, 1, 5]);
        assert!((pen - 0.15).abs() < 0.001);
    }

    #[test]
    fn test_penalty_cap_clamps() {
        let total = apply_penalty_cap(0.45);
        assert!((total - 0.40).abs() < 0.001);
    }

    #[test]
    fn test_penalty_cap_no_clamp_when_under() {
        let total = apply_penalty_cap(0.10);
        assert!((total - 0.10).abs() < 0.001);
    }

    #[test]
    fn test_zero_penalty_neutral_satisfaction() {
        // Matching cultural values → zero penalty → satisfaction unchanged
        let shock = &crate::signals::CivShock::default();
        let base = compute_satisfaction(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0, shock,
        );
        let with_culture = compute_satisfaction_with_culture(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0, shock,
            [4, 3, 2], [4, 3, 2],
            0xFF, 0xFF,
            false,
            0.0,
        );
        assert!((base - with_culture).abs() < 0.001);
    }
}

#[cfg(test)]
mod m37_tests {
    use super::*;
    use crate::signals::CivShock;

    #[test]
    fn test_religious_penalty_match_is_zero() {
        // Same belief → no penalty vs BELIEF_NONE baseline
        let sat_match = compute_satisfaction_with_culture(
            0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
            &CivShock::default(),
            [0, 1, 2], [0, 1, 2],
            3, 3,  // belief matches majority
            false,
            0.0,
        );
        let sat_none = compute_satisfaction_with_culture(
            0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
            &CivShock::default(),
            [0, 1, 2], [0, 1, 2],
            0xFF, 0xFF,  // BELIEF_NONE
            false,
            0.0,
        );
        assert!((sat_match - sat_none).abs() < 0.001);
    }

    #[test]
    fn test_religious_penalty_mismatch() {
        let sat_match = compute_satisfaction_with_culture(
            0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
            &CivShock::default(),
            [0, 1, 2], [0, 1, 2],
            3, 3,
            false,
            0.0,
        );
        let sat_mismatch = compute_satisfaction_with_culture(
            0, 0.8, 0.6, 50, 1.0, 0.5, false, false, false, false, 0, 0.0,
            &CivShock::default(),
            [0, 1, 2], [0, 1, 2],
            3, 5,  // different belief
            false,
            0.0,
        );
        let expected_diff = crate::agent::RELIGIOUS_MISMATCH_WEIGHT;
        assert!((sat_match - sat_mismatch - expected_diff).abs() < 0.001);
    }

    #[test]
    fn test_penalty_cap_with_religion() {
        let pen = apply_penalty_cap(0.15 + 0.10);
        assert!((pen - 0.25).abs() < 0.001);
        let pen_capped = apply_penalty_cap(0.15 + 0.10 + 0.20);
        assert!((pen_capped - 0.40).abs() < 0.001);
    }
}

#[cfg(test)]
mod m34_tests {
    use super::*;
    use crate::region::RegionState;

    fn make_region_with_resources(types: [u8; 3], yields: [f32; 3]) -> RegionState {
        let mut r = RegionState::new(0);
        r.resource_types = types;
        r.resource_yields = yields;
        r
    }

    #[test]
    fn test_resource_satisfaction_at_peak() {
        let r = make_region_with_resources([0, 255, 255], [1.0, 0.0, 0.0]);
        let sat = resource_satisfaction(&r);
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_resource_satisfaction_at_threshold() {
        let r = make_region_with_resources([0, 255, 255], [0.12, 0.0, 0.0]);
        let sat = resource_satisfaction(&r);
        assert!(sat.abs() < 0.01);
    }

    #[test]
    fn test_trade_satisfaction_mountains() {
        // Ore(5) + Precious(6) = 0.35 + 0.35 = 0.7
        let r = make_region_with_resources([5, 6, 255], [0.9, 0.5, 0.0]);
        let sat = trade_satisfaction(&r);
        assert!((sat - 0.7).abs() < 0.01);
    }

    #[test]
    fn test_trade_satisfaction_tundra_exotic_only() {
        // Exotic(7) is food → weight 0.15
        let r = make_region_with_resources([7, 255, 255], [0.5, 0.0, 0.0]);
        let sat = trade_satisfaction(&r);
        assert!((sat - 0.15).abs() < 0.01);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_farmer_healthy_ecology_peacetime() {
        let sat = compute_satisfaction(
            0, 0.8, 0.7, 80, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &CivShock::default(),
        );
        // base = 0.78, stability = 0.40, total = 1.18 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_farmer_bad_ecology_wartime() {
        let sat = compute_satisfaction(
            0, 0.2, 0.1, 20, -0.5, 1.3, true, true, false, true, 0, 0.0,
            &CivShock::default(),
        );
        // total ~= 0.04
        assert!(sat > 0.0 && sat < 0.15);
    }

    #[test]
    fn test_soldier_with_faction_alignment() {
        let sat = compute_satisfaction(
            1, 0.5, 0.5, 60, 0.0, 0.9, false, false, true, false, 0, 0.6,
            &CivShock::default(),
        );
        // total = 1.03 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_merchant_with_trade_routes() {
        let sat = compute_satisfaction(
            2, 0.5, 0.5, 50, 0.3, 0.7, false, false, true, false, 2, 0.4,
            &CivShock::default(),
        );
        assert!(sat > 0.90 && sat <= 1.0);
    }

    #[test]
    fn test_scholar_with_faction() {
        let sat = compute_satisfaction(
            3, 0.5, 0.5, 50, 0.0, 0.8, false, false, true, false, 0, 0.5,
            &CivShock::default(),
        );
        // base = 0.5 + 0.5*0.2 = 0.6, stability = 0.25, faction = 0.05 → 0.90
        assert!(sat > 0.85 && sat <= 1.0);
    }

    #[test]
    fn test_priest_unstable_civ() {
        let sat = compute_satisfaction(
            4, 0.5, 0.5, 15, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &CivShock::default(),
        );
        assert!(sat > 0.45 && sat < 0.60);
    }

    #[test]
    fn test_satisfaction_clamps_to_zero() {
        let sat = compute_satisfaction(
            0, 0.0, 0.0, 0, -1.0, 2.0, true, true, false, true, 0, 0.0,
            &CivShock::default(),
        );
        assert!(sat >= 0.0);
    }

    #[test]
    fn test_target_occupation_ratio_plains() {
        let ratios = target_occupation_ratio(0, 0.8, 0.6, [0.0; 5]);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.01);
        assert!(ratios[0] > 0.5);
    }

    #[test]
    fn test_target_occupation_ratio_coast() {
        let ratios = target_occupation_ratio(2, 0.5, 0.5, [0.0; 5]);
        assert!(ratios[2] > 0.10);
    }

    #[test]
    fn test_target_occupation_ratio_desert_bad_soil() {
        let ratios = target_occupation_ratio(4, 0.2, 0.3, [0.0; 5]);
        assert!(ratios[0] < 0.45);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.02);
    }

    // --- M27 shock penalty tests ---

    #[test]
    fn test_shock_penalty_farmer_economy_shock() {
        let shock = CivShock { stability: 0.0, economy: -0.5, military: 0.0, culture: 0.0 };
        let penalty = compute_shock_penalty(0, &shock);
        // general: 0.15*0 + 0.05*(-0.5) + 0.05*0 + 0.05*0 = -0.025
        // specific: (-0.5) * 0.20 = -0.10
        // total: -0.125
        assert!((penalty - (-0.125)).abs() < 0.001);
    }

    #[test]
    fn test_shock_penalty_all_occupations_nonzero() {
        let shock = CivShock { stability: -0.3, economy: -0.2, military: -0.4, culture: -0.1 };
        for occ in 0..5 {
            let pen = compute_shock_penalty(occ, &shock);
            assert!(pen < 0.0, "Occupation {occ} should have negative penalty with all-negative shocks");
        }
    }

    #[test]
    fn test_shock_penalty_positive_shock() {
        let shock = CivShock { stability: 0.1, economy: 0.0, military: 0.0, culture: 0.0 };
        let pen = compute_shock_penalty(4, &shock); // Priest: stability-sensitive
        assert!(pen > 0.0, "Positive stability shock should boost priest satisfaction");
    }

    // --- M27 demand shift tests ---

    #[test]
    fn test_demand_shift_increases_soldier() {
        let base = target_occupation_ratio(0, 0.5, 0.5, [0.0; 5]);
        let shifted = target_occupation_ratio(0, 0.5, 0.5, [0.0, 0.17, 0.0, 0.0, 0.0]);
        assert!(shifted[1] > base[1], "Soldier ratio should increase with demand shift");
        let sum: f32 = shifted.iter().sum();
        assert!((sum - 1.0).abs() < 0.001, "Ratios must sum to 1.0");
        assert!(shifted.iter().all(|&r| r >= 0.01), "All ratios above 1% floor");
    }

    #[test]
    fn test_demand_shift_zero_is_noop() {
        let base = target_occupation_ratio(0, 0.5, 0.5, [0.0; 5]);
        let same = target_occupation_ratio(0, 0.5, 0.5, [0.0; 5]);
        for i in 0..5 {
            assert!((base[i] - same[i]).abs() < 0.001);
        }
    }
}
