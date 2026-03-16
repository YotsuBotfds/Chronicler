//! Branchless satisfaction formula — computes per-agent satisfaction from
//! ecology, civ state, and occupation context.

use crate::signals::CivShock;

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
