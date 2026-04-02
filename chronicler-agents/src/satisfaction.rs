//! Branchless satisfaction formula — computes per-agent satisfaction from
//! ecology, civ state, and occupation context.

use crate::region::RegionState;
use crate::signals::CivShock;

const FAMINE_YIELD_THRESHOLD: f32 = 0.12;
const PEAK_YIELD: f32 = 1.0;
const FOOD_SHORTAGE_WEIGHT: f32 = 0.07;  // [CALIBRATE] Multiplies `(1.0 - food_sufficiency)` when food_sufficiency < 1.0, so the added penalty range is [0.0, 0.07].
const MERCHANT_MARGIN_WEIGHT: f32 = 0.3;  // [CALIBRATE] Multiplies `merchant_margin` in [0.0, 1.0], so the merchant-only base uplift range is [0.0, 0.3].
const FOOD_SCARCITY_FARMER_BONUS: f32 = 0.36;  // [CALIBRATE] Added to farmer demand weight when food_sufficiency is critically low; larger values accelerate labor reallocation toward farming.

// M-2 audit: Named constants for satisfaction formula terms
const WAR_PENALTY_CIV: f32 = 0.08;        // [CALIBRATE] M47c: 0.15->0.08 (whole-civ at-war penalty)
const WAR_PENALTY_CONTESTED: f32 = 0.05;  // [CALIBRATE] M47c: 0.10->0.05 (region contested penalty)
const FACTION_ALIGNMENT_BONUS: f32 = 0.05; // bonus when occupation matches dominant faction
const DISPLACEMENT_PENALTY: f32 = 0.10;    // penalty for displaced agents
const MEMORY_POSITIVE_CAP_FRACTION: f32 = 0.50; // good memories can reduce at most 50% of accumulated penalty

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
    debug_assert!(overlap <= 3, "cultural overlap exceeded available value slots: {overlap}");
    3u8.saturating_sub(overlap)
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
    _trade_routes: u8,
    faction_influence: f32,
    shock: &CivShock,
    merchant_margin: f32,  // M42: replaces trade_routes for merchant satisfaction
) -> f32 {
    let base = match occupation {
        0 => 0.4 + soil * 0.3 + water * 0.2,                      // Farmer
        1 => 0.5 + faction_influence * 0.3,                        // Soldier
        2 => 0.4 + merchant_margin * MERCHANT_MARGIN_WEIGHT,       // Merchant — M42: margin replaces trade_routes
        3 => 0.5 + faction_influence * 0.2,                        // Scholar
        _ => 0.6 - (1.0 - civ_stability as f32 / 100.0) * 0.2,   // Priest
    };

    let stability_bonus = civ_stability as f32 / 200.0;  // [CALIBRATE] M57 tuning: stronger civic-stability upside to recover regression-floor satisfaction under stricter rebel containment.

    let ds_raw = demand_supply_ratio * 0.2;
    let ds_bonus = ds_raw.clamp(-0.2, 0.2);

    let overcrowding_raw = (pop_over_capacity - 1.0) * crate::agent::OVERCROWDING_WEIGHT;
    let overcrowding = overcrowding_raw.clamp(0.0, crate::agent::OVERCROWDING_PENALTY_CAP);

    let war_pen = WAR_PENALTY_CIV * civ_at_war as i32 as f32
                + WAR_PENALTY_CONTESTED * region_contested as i32 as f32;

    let faction_bonus = FACTION_ALIGNMENT_BONUS * occ_matches_faction as i32 as f32;

    let displacement_pen = DISPLACEMENT_PENALTY * is_displaced as i32 as f32;

    // shock_effect can be positive (good shock) or negative (bad shock) — not strictly a penalty
    let shock_effect = compute_shock_penalty(occupation, shock);

    // Shock effects live in base satisfaction, not the capped non-ecological
    // social-penalty bucket. They can be positive or negative, and they are
    // intentionally excluded from the 0.40 cap budget above.

    (base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen + shock_effect)
        .clamp(0.0, 1.0)
}

/// All inputs needed for the full satisfaction calculation (base + cultural/religious/class).
pub struct SatisfactionInputs {
    pub occupation: u8,
    pub soil: f32,
    pub water: f32,
    pub civ_stability: u8,
    pub demand_supply_ratio: f32,
    pub pop_over_capacity: f32,
    pub civ_at_war: bool,
    pub region_contested: bool,
    pub occ_matches_faction: bool,
    pub is_displaced: bool,
    pub trade_routes: u8,
    pub faction_influence: f32,
    pub shock: CivShock,
    pub agent_values: [u8; 3],
    pub controller_values: [u8; 3],
    pub agent_belief: u8,
    pub majority_belief: u8,
    pub has_temple: bool,
    pub persecution_intensity: f32,
    pub gini_coefficient: f32,
    pub wealth_percentile: f32,
    // M42: Goods economy
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
    // M48: Memory satisfaction score
    pub memory_score: f32,
    // M56b: Urban context
    pub is_urban: bool,
}

/// Wraps compute_satisfaction(), subtracting the cultural and religious mismatch penalties (capped).
pub fn compute_satisfaction_with_culture(inp: &SatisfactionInputs) -> f32 {
    let base_sat = compute_satisfaction(
        inp.occupation,
        inp.soil,
        inp.water,
        inp.civ_stability,
        inp.demand_supply_ratio,
        inp.pop_over_capacity,
        inp.civ_at_war,
        inp.region_contested,
        inp.occ_matches_faction,
        inp.is_displaced,
        inp.trade_routes,
        inp.faction_influence,
        &inp.shock,
        inp.merchant_margin,
    );
    let cultural_pen = compute_cultural_penalty(inp.agent_values, inp.controller_values);
    // M37: religious mismatch — binary (match or not)
    let religious_pen = if inp.agent_belief != inp.majority_belief
        && inp.agent_belief != crate::agent::BELIEF_NONE
        && inp.majority_belief != crate::agent::BELIEF_NONE
    {
        crate::agent::RELIGIOUS_MISMATCH_WEIGHT
    } else {
        0.0
    };
    // M38b: Persecution penalty — skip for BELIEF_NONE agents (no faith to persecute)
    let mut penalty = 0.0f32;
    if inp.agent_belief != crate::agent::BELIEF_NONE
        && inp.agent_belief != inp.majority_belief
    {
        penalty += crate::agent::PERSECUTION_SAT_WEIGHT * inp.persecution_intensity;
    }
    // M38a: temple priest bonus — faith-blind (Decision 6)
    let temple_bonus = if inp.occupation == 4 && inp.has_temple {
        0.10  // TEMPLE_PRIEST_BONUS [CALIBRATE]
    } else {
        0.0
    };
    // M41: class tension penalty — poor agents in unequal civs
    let class_tension_pen = inp.gini_coefficient
        * (1.0 - inp.wealth_percentile)
        * crate::agent::CLASS_TENSION_WEIGHT;

    // Priority clamping (Decision 3): core identity/persecution terms first.
    // Clamp this subtotal before downstream budget math so later priorities
    // never observe more than the social-penalty cap allows.
    let three_term = (cultural_pen + religious_pen + penalty).min(crate::agent::PENALTY_CAP);
    // M56b: Urban safety penalty — priority 2 (after three_term, before class tension)
    let urban_safety_pen = if inp.is_urban {
        crate::agent::URBAN_SAFETY_SATISFACTION_PENALTY
    } else {
        0.0
    };
    let urban_safety_clamped = urban_safety_pen
        .min((crate::agent::PENALTY_CAP - three_term).max(0.0));
    let class_tension_clamped = class_tension_pen.min((crate::agent::PENALTY_CAP - three_term - urban_safety_clamped).max(0.0));
    // M48: Memory penalty — 5th priority (lowest), takes whatever budget remains.
    // memory_score is in satisfaction-space (positive=good, negative=bad).
    // Convert to penalty-space by negation: bad memories → positive penalty addition.
    let accumulated_penalty = three_term + urban_safety_clamped + class_tension_clamped;
    let memory_penalty = if inp.memory_score < 0.0 {
        // Bad memories: add penalty, clamped to remaining budget
        (-inp.memory_score).min((crate::agent::PENALTY_CAP - accumulated_penalty).max(0.0))
    } else {
        // Good memories: reduce penalty, but cap at 50% of accumulated penalty
        // so memories cannot fully erase persecution/cultural/class penalties (M-6 audit)
        let max_reduction = accumulated_penalty * MEMORY_POSITIVE_CAP_FRACTION;
        -(inp.memory_score.min(max_reduction))
    };
    let total_non_eco_penalty = (accumulated_penalty + memory_penalty)
        .min(crate::agent::PENALTY_CAP)
        .max(0.0); // positive memories cannot create net bonus
    // M42: Food sufficiency penalty — material condition, outside social penalty cap
    let food_penalty = if inp.food_sufficiency < 1.0 {
        (1.0 - inp.food_sufficiency) * FOOD_SHORTAGE_WEIGHT
    } else {
        0.0
    };
    // M56b: Urban material bonus (positive, outside penalty cap)
    let urban_material_bonus = if inp.is_urban {
        crate::agent::URBAN_MATERIAL_SATISFACTION_BONUS
    } else {
        0.0
    };
    (base_sat + urban_material_bonus - total_non_eco_penalty + temple_bonus - food_penalty).clamp(0.0, 1.0)
}

/// Target occupation ratios for a region based on terrain and ecology.
/// Returns [farmer, soldier, merchant, scholar, priest] ratios summing to ~1.0.
/// Cold path — called once per region per tick, not per agent.
pub fn target_occupation_ratio(
    terrain: u8,
    soil: f32,
    _water: f32,
    food_sufficiency: f32,
    demand_shifts: [f32; 5],
) -> [f32; 5] {
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

    // Food scarcity should pull labor back toward farming before regions fall
    // into a multi-turn zero-stockpile trap.
    let food_pressure = (0.85 - food_sufficiency).max(0.0) / 0.85;
    if food_pressure > 0.0 {
        let farmer_bonus = FOOD_SCARCITY_FARMER_BONUS * food_pressure;
        r[0] += farmer_bonus;
        r[1] -= farmer_bonus * 0.30;
        r[2] -= farmer_bonus * 0.30;
        r[3] -= farmer_bonus * 0.20;
        r[4] -= farmer_bonus * 0.20;
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
        let shock = crate::signals::CivShock::default();
        let base = compute_satisfaction(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0, &shock, 0.0,
        );
        let with_culture = compute_satisfaction_with_culture(&SatisfactionInputs {
            occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
            demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
            civ_at_war: false, region_contested: false, occ_matches_faction: false,
            is_displaced: false, trade_routes: 0, faction_influence: 0.0,
            shock,
            agent_values: [4, 3, 2], controller_values: [4, 3, 2],
            agent_belief: 0xFF, majority_belief: 0xFF,
            has_temple: false, persecution_intensity: 0.0,
            gini_coefficient: 0.0, wealth_percentile: 0.5,
            food_sufficiency: 1.0, merchant_margin: 0.0,
            memory_score: 0.0,
            is_urban: false,
        });
        assert!((base - with_culture).abs() < 0.001);
    }
}

#[cfg(test)]
mod m37_tests {
    use super::*;
    use crate::signals::CivShock;

    fn m37_base_inputs() -> SatisfactionInputs {
        SatisfactionInputs {
            occupation: 0, soil: 0.8, water: 0.6, civ_stability: 50,
            demand_supply_ratio: 1.0, pop_over_capacity: 0.5,
            civ_at_war: false, region_contested: false, occ_matches_faction: false,
            is_displaced: false, trade_routes: 0, faction_influence: 0.0,
            shock: CivShock::default(),
            agent_values: [0, 1, 2], controller_values: [0, 1, 2],
            agent_belief: 0xFF, majority_belief: 0xFF,
            has_temple: false, persecution_intensity: 0.0,
            gini_coefficient: 0.0, wealth_percentile: 0.5,
            food_sufficiency: 1.0, merchant_margin: 0.0,
            memory_score: 0.0,
            is_urban: false,
        }
    }

    #[test]
    fn test_religious_penalty_match_is_zero() {
        // Same belief → no penalty vs BELIEF_NONE baseline
        let sat_match = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 3, majority_belief: 3,
            ..m37_base_inputs()
        });
        let sat_none = compute_satisfaction_with_culture(&m37_base_inputs());
        assert!((sat_match - sat_none).abs() < 0.001);
    }

    #[test]
    fn test_religious_penalty_mismatch() {
        let sat_match = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 3, majority_belief: 3,
            ..m37_base_inputs()
        });
        let sat_mismatch = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 3, majority_belief: 5,
            ..m37_base_inputs()
        });
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

    /// C-7 regression: BELIEF_NONE agents must not receive persecution penalties.
    #[test]
    fn test_belief_none_no_persecution_penalty() {
        // Agent with BELIEF_NONE and a real majority belief — should get NO persecution penalty
        let sat_none_belief = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: crate::agent::BELIEF_NONE,
            majority_belief: 3,
            persecution_intensity: 1.0,  // max persecution
            ..m37_base_inputs()
        });
        // Agent with matching belief (also no persecution)
        let sat_matching = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 3,
            majority_belief: 3,
            persecution_intensity: 1.0,
            ..m37_base_inputs()
        });
        // Both should have the same satisfaction (no persecution penalty)
        assert!((sat_none_belief - sat_matching).abs() < 0.001,
            "BELIEF_NONE agent should not receive persecution penalty; \
             sat_none={}, sat_match={}", sat_none_belief, sat_matching);
    }

    /// C-7 regression: real minority belief DOES receive persecution penalty.
    #[test]
    fn test_real_minority_belief_gets_persecution_penalty() {
        let sat_minority = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 5,
            majority_belief: 3,
            persecution_intensity: 1.0,
            ..m37_base_inputs()
        });
        let sat_majority = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_belief: 3,
            majority_belief: 3,
            persecution_intensity: 1.0,
            ..m37_base_inputs()
        });
        let expected_diff = crate::agent::PERSECUTION_SAT_WEIGHT * 1.0
            + crate::agent::RELIGIOUS_MISMATCH_WEIGHT;
        assert!((sat_majority - sat_minority - expected_diff).abs() < 0.001,
            "Real minority belief should receive both persecution and religious mismatch penalties; \
             diff={}, expected={}", sat_majority - sat_minority, expected_diff);
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
            &CivShock::default(), 0.0,
        );
        // base = 0.4 + 0.8*0.3 + 0.7*0.2 = 0.78, stability = 80/200 = 0.40,
        // total = 1.18 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_farmer_bad_ecology_wartime() {
        let sat = compute_satisfaction(
            0, 0.2, 0.1, 20, -0.5, 1.3, true, true, false, true, 0, 0.0,
            &CivShock::default(), 0.0,
        );
        // Harsh conditions should remain low but non-zero under current tuning.
        assert!(sat > 0.0 && sat < 0.25);
    }

    #[test]
    fn test_soldier_with_faction_alignment() {
        let sat = compute_satisfaction(
            1, 0.5, 0.5, 60, 0.0, 0.9, false, false, true, false, 0, 0.6,
            &CivShock::default(), 0.0,
        );
        // base = 0.5 + 0.6*0.3 = 0.68, stability = 60/200 = 0.30, faction = 0.05 → 1.03 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_merchant_with_margin() {
        // M42: merchant satisfaction uses merchant_margin instead of trade_routes
        let sat = compute_satisfaction(
            2, 0.5, 0.5, 50, 0.3, 0.7, false, false, true, false, 2, 0.4,
            &CivShock::default(), 1.0,  // merchant_margin=1.0 → base=0.4+0.3=0.7
        );
        assert!(sat > 0.90 && sat <= 1.0);
    }

    #[test]
    fn test_scholar_with_faction() {
        let sat = compute_satisfaction(
            3, 0.5, 0.5, 50, 0.0, 0.8, false, false, true, false, 0, 0.5,
            &CivShock::default(), 0.0,
        );
        // base = 0.5 + 0.5*0.2 = 0.60, stability = 50/200 = 0.25, faction = 0.05 → 0.90
        assert!((sat - 0.90).abs() < 0.02);
    }

    #[test]
    fn test_priest_unstable_civ() {
        let sat = compute_satisfaction(
            4, 0.5, 0.5, 15, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &CivShock::default(), 0.0,
        );
        assert!(sat > 0.45 && sat < 0.60);
    }

    #[test]
    fn test_satisfaction_clamps_to_zero() {
        let sat = compute_satisfaction(
            0, 0.0, 0.0, 0, -1.0, 2.0, true, true, false, true, 0, 0.0,
            &CivShock::default(), 0.0,
        );
        assert!(sat >= 0.0);
    }

    #[test]
    fn test_target_occupation_ratio_plains() {
        let ratios = target_occupation_ratio(0, 0.8, 0.6, 1.0, [0.0; 5]);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.01);
        assert!(ratios[0] > 0.5);
    }

    #[test]
    fn test_target_occupation_ratio_coast() {
        let ratios = target_occupation_ratio(2, 0.5, 0.5, 1.0, [0.0; 5]);
        assert!(ratios[2] > 0.10);
    }

    #[test]
    fn test_target_occupation_ratio_desert_bad_soil() {
        let ratios = target_occupation_ratio(4, 0.2, 0.3, 1.0, [0.0; 5]);
        assert!(ratios[0] < 0.45);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.02);
    }

    #[test]
    fn test_target_occupation_ratio_food_shortage_boosts_farmers() {
        let base = target_occupation_ratio(0, 0.5, 0.5, 1.0, [0.0; 5]);
        let starving = target_occupation_ratio(0, 0.5, 0.5, 0.2, [0.0; 5]);
        assert!(starving[0] > base[0]);
        assert!((starving.iter().sum::<f32>() - 1.0).abs() < 0.001);
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
        let base = target_occupation_ratio(0, 0.5, 0.5, 1.0, [0.0; 5]);
        let shifted = target_occupation_ratio(0, 0.5, 0.5, 1.0, [0.0, 0.17, 0.0, 0.0, 0.0]);
        assert!(shifted[1] > base[1], "Soldier ratio should increase with demand shift");
        let sum: f32 = shifted.iter().sum();
        assert!((sum - 1.0).abs() < 0.001, "Ratios must sum to 1.0");
        assert!(shifted.iter().all(|&r| r >= 0.01), "All ratios above 1% floor");
    }

    #[test]
    fn test_demand_shift_zero_is_noop() {
        let base = target_occupation_ratio(0, 0.5, 0.5, 1.0, [0.0; 5]);
        let same = target_occupation_ratio(0, 0.5, 0.5, 1.0, [0.0; 5]);
        for i in 0..5 {
            assert!((base[i] - same[i]).abs() < 0.001);
        }
    }
}

#[cfg(test)]
mod m41_tests {
    use super::*;
    use crate::signals::CivShock;

    fn m41_base_inputs() -> SatisfactionInputs {
        SatisfactionInputs {
            occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
            demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
            civ_at_war: false, region_contested: false, occ_matches_faction: false,
            is_displaced: false, trade_routes: 0, faction_influence: 0.0,
            shock: CivShock::default(),
            agent_values: [0, 1, 2], controller_values: [0, 1, 2],
            agent_belief: 0xFF, majority_belief: 0xFF,
            has_temple: false, persecution_intensity: 0.0,
            gini_coefficient: 0.0, wealth_percentile: 0.5,
            food_sufficiency: 1.0, merchant_margin: 0.0,
            memory_score: 0.0,
            is_urban: false,
        }
    }

    #[test]
    fn test_class_tension_poor_agent_penalized() {
        let sat_rich = compute_satisfaction_with_culture(&SatisfactionInputs {
            gini_coefficient: 0.6, wealth_percentile: 1.0,
            ..m41_base_inputs()
        });
        let sat_poor = compute_satisfaction_with_culture(&SatisfactionInputs {
            gini_coefficient: 0.6, wealth_percentile: 0.0,
            ..m41_base_inputs()
        });
        let expected_diff = 0.6 * 1.0 * crate::agent::CLASS_TENSION_WEIGHT;
        assert!((sat_rich - sat_poor - expected_diff).abs() < 0.01,
            "Rich-poor diff {}, expected {}", sat_rich - sat_poor, expected_diff);
    }

    #[test]
    fn test_class_tension_zero_gini_no_penalty() {
        let sat_base = compute_satisfaction_with_culture(&SatisfactionInputs {
            gini_coefficient: 0.0, wealth_percentile: 0.0,
            ..m41_base_inputs()
        });
        let sat_no_wealth = compute_satisfaction_with_culture(&SatisfactionInputs {
            gini_coefficient: 0.0, wealth_percentile: 0.5,
            ..m41_base_inputs()
        });
        assert!((sat_base - sat_no_wealth).abs() < 0.001,
            "Zero Gini should produce no class tension penalty");
    }

    #[test]
    fn test_class_tension_priority_clamping() {
        // Max cultural mismatch (0.15) + religious mismatch (0.05) + persecution (0.15) = 0.35
        // Leaves 0.05 budget for class tension under the 0.40 cap
        let sat = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2], controller_values: [0, 1, 5],
            agent_belief: 3, majority_belief: 5,
            persecution_intensity: 1.0,
            gini_coefficient: 1.0, wealth_percentile: 0.0,
            ..m41_base_inputs()
        });
        let sat_no_class = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2], controller_values: [0, 1, 5],
            agent_belief: 3, majority_belief: 5,
            persecution_intensity: 1.0,
            gini_coefficient: 0.0, wealth_percentile: 0.0,
            ..m41_base_inputs()
        });
        // Raw class tension = 1.0 * 1.0 * CLASS_TENSION_WEIGHT(0.15) = 0.15
        // Clamped to remaining budget: 0.40 - 0.35 = 0.05
        let remaining_budget = crate::agent::PENALTY_CAP
            - (0.15 + crate::agent::RELIGIOUS_MISMATCH_WEIGHT + crate::agent::PERSECUTION_SAT_WEIGHT * 1.0);
        assert!((sat_no_class - sat - remaining_budget).abs() < 0.001,
            "Class tension should equal remaining budget ({}) under cap", remaining_budget);
    }
}

#[cfg(test)]
mod audit_tests {
    use super::*;
    use crate::signals::CivShock;

    fn audit_base_inputs() -> SatisfactionInputs {
        SatisfactionInputs {
            occupation: 0, soil: 0.5, water: 0.5, civ_stability: 50,
            demand_supply_ratio: 0.0, pop_over_capacity: 0.8,
            civ_at_war: false, region_contested: false, occ_matches_faction: false,
            is_displaced: false, trade_routes: 0, faction_influence: 0.0,
            shock: CivShock::default(),
            agent_values: [0, 1, 2], controller_values: [0, 1, 2],
            agent_belief: 0xFF, majority_belief: 0xFF,
            has_temple: false, persecution_intensity: 0.0,
            gini_coefficient: 0.0, wealth_percentile: 0.5,
            food_sufficiency: 1.0, merchant_margin: 0.0,
            memory_score: 0.0,
            is_urban: false,
        }
    }

    // M-6: Good memories can reduce but not fully eliminate penalties
    #[test]
    fn test_positive_memory_capped_at_half_penalty() {
        // Cultural distance = 2 (two mismatches) -> penalty = 0.10
        let sat_no_memory = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2], controller_values: [4, 0, 1],
            memory_score: 0.0,
            ..audit_base_inputs()
        });
        let sat_big_memory = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2], controller_values: [4, 0, 1],
            memory_score: 1.0,  // huge positive memory
            ..audit_base_inputs()
        });
        let sat_no_penalty = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [0, 1, 2], controller_values: [0, 1, 2],
            memory_score: 0.0,
            ..audit_base_inputs()
        });
        // With 50% cap: memory reduces 0.10 penalty by at most 0.05
        // So sat_big_memory should be 0.05 below sat_no_penalty
        let residual = sat_no_penalty - sat_big_memory;
        assert!(residual > 0.04 && residual < 0.06,
            "Positive memory should leave ~50%% of cultural penalty: residual={}", residual);
        // And better than no memory
        assert!(sat_big_memory > sat_no_memory,
            "Positive memory should still improve satisfaction: big={}, none={}",
            sat_big_memory, sat_no_memory);
    }

    // Civ shock effects remain part of base satisfaction, even when the
    // social penalty budget is already exhausted.
    #[test]
    fn test_shock_effects_apply_outside_social_penalty_cap() {
        let capped = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2],
            controller_values: [0, 1, 5],
            agent_belief: 3,
            majority_belief: 5,
            soil: 0.0,
            water: 0.0,
            civ_stability: 0,
            persecution_intensity: 1.0,
            gini_coefficient: 1.0,
            wealth_percentile: 0.0,
            shock: CivShock {
                stability: 0.0,
                economy: 0.0,
                military: 0.0,
                culture: 0.0,
            },
            ..audit_base_inputs()
        });
        let shocked = compute_satisfaction_with_culture(&SatisfactionInputs {
            agent_values: [4, 3, 2],
            controller_values: [0, 1, 5],
            agent_belief: 3,
            majority_belief: 5,
            soil: 0.0,
            water: 0.0,
            civ_stability: 0,
            persecution_intensity: 1.0,
            gini_coefficient: 1.0,
            wealth_percentile: 0.0,
            shock: CivShock {
                stability: 1.0,
                economy: 0.0,
                military: 0.0,
                culture: 0.0,
            },
            ..audit_base_inputs()
        });

        assert!(shocked > capped, "Shock effects should move base satisfaction even at the social-penalty cap");
        assert!((shocked - capped - 0.15).abs() < 0.001,
            "Stability shock should contribute its base 0.15 effect, got {}", shocked - capped);
    }

    // M-6: Zero penalty means positive memory has no penalty-reduction effect
    #[test]
    fn test_positive_memory_no_bonus_without_penalty() {
        let sat_base = compute_satisfaction_with_culture(&SatisfactionInputs {
            memory_score: 0.0,
            ..audit_base_inputs()
        });
        let sat_pos = compute_satisfaction_with_culture(&SatisfactionInputs {
            memory_score: 0.5,
            ..audit_base_inputs()
        });
        // No penalty to reduce -> positive memory does nothing
        assert!((sat_base - sat_pos).abs() < 0.001,
            "Positive memory with no penalty should not grant bonus: base={}, pos={}",
            sat_base, sat_pos);
    }

    // M-1: shock_effect can be positive (good shock)
    #[test]
    fn test_positive_shock_improves_satisfaction() {
        let sat_no_shock = compute_satisfaction(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &CivShock::default(), 0.0,
        );
        let sat_good_shock = compute_satisfaction(
            0, 0.5, 0.5, 50, 0.0, 0.8, false, false, false, false, 0, 0.0,
            &CivShock { stability: 0.5, economy: 0.5, military: 0.0, culture: 0.0 }, 0.0,
        );
        assert!(sat_good_shock > sat_no_shock,
            "Positive shock should improve satisfaction: good={}, none={}",
            sat_good_shock, sat_no_shock);
    }

    // M-2: Named constants produce same values as old magic numbers
    #[test]
    fn test_named_constants_match_original_values() {
        assert_eq!(WAR_PENALTY_CIV, 0.08);
        assert_eq!(WAR_PENALTY_CONTESTED, 0.05);
        assert_eq!(FACTION_ALIGNMENT_BONUS, 0.05);
        assert_eq!(DISPLACEMENT_PENALTY, 0.10);
    }
}
