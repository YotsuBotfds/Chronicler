//! Branchless satisfaction formula — computes per-agent satisfaction from
//! ecology, civ state, and occupation context.

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

    (base + stability_bonus + ds_bonus - overcrowding - war_pen + faction_bonus - displacement_pen)
        .clamp(0.0, 1.0)
}

/// Target occupation ratios for a region based on terrain and ecology.
/// Returns [farmer, soldier, merchant, scholar, priest] ratios summing to ~1.0.
/// Cold path — called once per region per tick, not per agent.
pub fn target_occupation_ratio(terrain: u8, soil: f32, _water: f32) -> [f32; 5] {
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

    r
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_farmer_healthy_ecology_peacetime() {
        let sat = compute_satisfaction(
            0, 0.8, 0.7, 80, 0.0, 0.8, false, false, false, false, 0, 0.0,
        );
        // base = 0.78, stability = 0.40, total = 1.18 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_farmer_bad_ecology_wartime() {
        let sat = compute_satisfaction(
            0, 0.2, 0.1, 20, -0.5, 1.3, true, true, false, true, 0, 0.0,
        );
        // total ≈ 0.04
        assert!(sat > 0.0 && sat < 0.15);
    }

    #[test]
    fn test_soldier_with_faction_alignment() {
        let sat = compute_satisfaction(
            1, 0.5, 0.5, 60, 0.0, 0.9, false, false, true, false, 0, 0.6,
        );
        // total = 1.03 → clamped to 1.0
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_merchant_with_trade_routes() {
        let sat = compute_satisfaction(
            2, 0.5, 0.5, 50, 0.3, 0.7, false, false, true, false, 2, 0.4,
        );
        assert!(sat > 0.90 && sat <= 1.0);
    }

    #[test]
    fn test_scholar_with_faction() {
        let sat = compute_satisfaction(
            3, 0.5, 0.5, 50, 0.0, 0.8, false, false, true, false, 0, 0.5,
        );
        // base = 0.5 + 0.5*0.2 = 0.6, stability = 0.25, faction = 0.05 → 0.90
        assert!(sat > 0.85 && sat <= 1.0);
    }

    #[test]
    fn test_priest_unstable_civ() {
        let sat = compute_satisfaction(
            4, 0.5, 0.5, 15, 0.0, 0.8, false, false, false, false, 0, 0.0,
        );
        assert!(sat > 0.45 && sat < 0.60);
    }

    #[test]
    fn test_satisfaction_clamps_to_zero() {
        let sat = compute_satisfaction(
            0, 0.0, 0.0, 0, -1.0, 2.0, true, true, false, true, 0, 0.0,
        );
        assert!(sat >= 0.0);
    }

    #[test]
    fn test_target_occupation_ratio_plains() {
        let ratios = target_occupation_ratio(0, 0.8, 0.6);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.01);
        assert!(ratios[0] > 0.5);
    }

    #[test]
    fn test_target_occupation_ratio_coast() {
        let ratios = target_occupation_ratio(2, 0.5, 0.5);
        assert!(ratios[2] > 0.10);
    }

    #[test]
    fn test_target_occupation_ratio_desert_bad_soil() {
        let ratios = target_occupation_ratio(4, 0.2, 0.3);
        assert!(ratios[0] < 0.45);
        assert!((ratios.iter().sum::<f32>() - 1.0).abs() < 0.02);
    }
}
