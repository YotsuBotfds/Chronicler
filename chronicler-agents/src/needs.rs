/// M49 Needs System
/// Spec: docs/superpowers/specs/2026-03-20-m49-needs-system-design.md

use crate::agent;
use crate::agent::Occupation;
use crate::behavior::personality_modifier;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::signals::TickSignals;

/// Additive utility modifiers from needs, applied after M48 memory modifiers.
#[derive(Debug, Default)]
pub struct NeedUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch_occ: f32,
    pub stay: f32,
}

// ---------------------------------------------------------------------------
// Utility modifiers
// ---------------------------------------------------------------------------

/// Compute threshold-gated utility modifiers from an agent's need state.
pub fn compute_need_utility_modifiers(pool: &AgentPool, slot: usize) -> NeedUtilityModifiers {
    let mut mods = NeedUtilityModifiers::default();

    // Safety → migrate +, stay -
    let safety_deficit = (agent::SAFETY_THRESHOLD - pool.need_safety[slot]).max(0.0);
    if safety_deficit > 0.0 {
        mods.migrate += safety_deficit * agent::SAFETY_WEIGHT;
        mods.stay -= safety_deficit * agent::SAFETY_WEIGHT;
    }

    // Material → migrate +, switch +
    let material_deficit = (agent::MATERIAL_THRESHOLD - pool.need_material[slot]).max(0.0);
    if material_deficit > 0.0 {
        mods.migrate += material_deficit * agent::MATERIAL_WEIGHT;
        mods.switch_occ += material_deficit * agent::MATERIAL_WEIGHT;
    }

    // Social → stay +, migrate -
    let social_deficit = (agent::SOCIAL_THRESHOLD - pool.need_social[slot]).max(0.0);
    if social_deficit > 0.0 {
        mods.stay += social_deficit * agent::SOCIAL_WEIGHT;
        mods.migrate -= social_deficit * agent::SOCIAL_WEIGHT;
    }

    // Spiritual → migrate +
    let spiritual_deficit = (agent::SPIRITUAL_THRESHOLD - pool.need_spiritual[slot]).max(0.0);
    if spiritual_deficit > 0.0 {
        mods.migrate += spiritual_deficit * agent::SPIRITUAL_WEIGHT;
    }

    // Autonomy → rebel +
    let autonomy_deficit = (agent::AUTONOMY_THRESHOLD - pool.need_autonomy[slot]).max(0.0);
    if autonomy_deficit > 0.0 {
        mods.rebel += autonomy_deficit * agent::AUTONOMY_WEIGHT;
    }

    // Purpose → switch +
    let purpose_deficit = (agent::PURPOSE_THRESHOLD - pool.need_purpose[slot]).max(0.0);
    if purpose_deficit > 0.0 {
        mods.switch_occ += purpose_deficit * agent::PURPOSE_WEIGHT;
    }

    // Per-channel cap (needs-only — does not affect M38b/M48 modifiers)
    mods.rebel = mods.rebel.min(agent::NEEDS_MODIFIER_CAP);
    mods.migrate = mods.migrate.max(-agent::NEEDS_MODIFIER_CAP).min(agent::NEEDS_MODIFIER_CAP);
    mods.switch_occ = mods.switch_occ.min(agent::NEEDS_MODIFIER_CAP);
    mods.stay = mods.stay.max(-agent::NEEDS_MODIFIER_CAP).min(agent::NEEDS_MODIFIER_CAP);

    mods
}

// ---------------------------------------------------------------------------
// Decay — linear subtraction per need, clamp to 0.0
// ---------------------------------------------------------------------------

/// Apply linear decay to all 6 needs for alive agents.
/// Each need decreases by its decay rate constant, clamped at 0.0.
pub fn decay_needs(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        pool.need_safety[slot] = (pool.need_safety[slot] - agent::SAFETY_DECAY).max(0.0);
        pool.need_material[slot] = (pool.need_material[slot] - agent::MATERIAL_DECAY).max(0.0);
        pool.need_social[slot] = (pool.need_social[slot] - agent::SOCIAL_DECAY).max(0.0);
        pool.need_spiritual[slot] = (pool.need_spiritual[slot] - agent::SPIRITUAL_DECAY).max(0.0);
        pool.need_autonomy[slot] = (pool.need_autonomy[slot] - agent::AUTONOMY_DECAY).max(0.0);
        pool.need_purpose[slot] = (pool.need_purpose[slot] - agent::PURPOSE_DECAY).max(0.0);
    }
}

// ---------------------------------------------------------------------------
// Clamp — ensure all 6 needs stay in [0.0, 1.0]
// ---------------------------------------------------------------------------

/// Clamp all 6 needs to [0.0, 1.0] for alive agents.
pub fn clamp_needs(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        pool.need_safety[slot] = pool.need_safety[slot].clamp(0.0, 1.0);
        pool.need_material[slot] = pool.need_material[slot].clamp(0.0, 1.0);
        pool.need_social[slot] = pool.need_social[slot].clamp(0.0, 1.0);
        pool.need_spiritual[slot] = pool.need_spiritual[slot].clamp(0.0, 1.0);
        pool.need_autonomy[slot] = pool.need_autonomy[slot].clamp(0.0, 1.0);
        pool.need_purpose[slot] = pool.need_purpose[slot].clamp(0.0, 1.0);
    }
}

// ---------------------------------------------------------------------------
// Social restoration proxy
// ---------------------------------------------------------------------------

/// Population-based social restoration proxy (pre-M50 baseline).
/// Uses population/capacity ratio, occupation modifier, and age modifier.
fn social_restoration_proxy(pool: &AgentPool, slot: usize, region: &RegionState) -> f32 {
    // Population ratio — guard for capacity == 0
    let pop_ratio = if region.carrying_capacity > 0 {
        (region.population as f32 / region.carrying_capacity as f32).min(1.0)
    } else {
        0.0
    };

    if pop_ratio <= agent::SOCIAL_RESTORE_POP_THRESHOLD {
        return 0.0;
    }

    let base_rate = agent::SOCIAL_RESTORE_POP * pop_ratio;

    // Occupation multiplier
    let occ = pool.occupations[slot];
    let occ_mult = if occ == Occupation::Merchant as u8 {
        agent::SOCIAL_MERCHANT_MULT
    } else if occ == Occupation::Priest as u8 {
        agent::SOCIAL_PRIEST_MULT
    } else {
        1.0
    };

    // Age multiplier: older agents have more social connections
    let age = pool.ages[slot];
    let age_mult = (age as f32 / 40.0).min(1.0);

    let deficit = 1.0 - pool.need_social[slot];
    base_rate * occ_mult * age_mult * deficit
}

/// Social restoration with M50b blend: pop proxy + bond factor.
/// At alpha=0.0 (default), this is a pure proxy — bond scan skipped entirely.
fn social_restoration(pool: &AgentPool, slot: usize, region: &RegionState) -> f32 {
    let alpha = agent::SOCIAL_BLEND_ALPHA;

    // Fast path: alpha == 0 → pure proxy, skip bond scan
    if alpha == 0.0 {
        return social_restoration_proxy(pool, slot, region);
    }

    let proxy = social_restoration_proxy(pool, slot, region);

    // Bond factor: count positive-valence bonds with positive sentiment
    let mut positive_count = 0u32;
    for i in 0..pool.rel_count[slot] as usize {
        if crate::relationships::is_positive_valence(pool.rel_bond_types[slot][i])
            && pool.rel_sentiments[slot][i] > 0
        {
            positive_count += 1;
        }
    }
    let deficit = 1.0 - pool.need_social[slot];
    let bond_factor = agent::SOCIAL_RESTORE_BOND
        * (positive_count as f32 / agent::SOCIAL_BOND_TARGET).min(1.0)
        * deficit;

    (1.0 - alpha) * proxy + alpha * bond_factor
}

// ---------------------------------------------------------------------------
// Restore — proportional restoration for all 6 needs
// ---------------------------------------------------------------------------

/// Apply proportional restoration to all 6 needs for alive agents.
/// Each need has per-agent restoration conditions that create behavioral
/// diversity between agents in the same region.
pub fn restore_needs(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    for &slot in alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx >= regions.len() {
            continue;
        }
        let region = &regions[region_idx];
        let civ = pool.civ_affinities[slot];

        // Look up civ signals (guard for out-of-bounds)
        let civ_signals = signals.civs.get(civ as usize);
        let is_at_war = civ_signals.map_or(false, |c| c.is_at_war);

        // ----- Safety -----
        {
            let deficit = 1.0 - pool.need_safety[slot];
            let mut delta = 0.0_f32;

            // NOT at war
            if !is_at_war {
                delta += agent::SAFETY_RESTORE_PEACE * deficit;
            }

            // Low disease
            let health_factor = (1.0 - region.endemic_severity).max(0.0);
            delta += agent::SAFETY_RESTORE_HEALTH * health_factor * deficit;

            // Food > 0.8
            if region.food_sufficiency > 0.8 {
                delta += agent::SAFETY_RESTORE_FOOD * region.food_sufficiency.min(1.5) * deficit;
            }

            // Per-agent: boldness modifier on ALL Safety restoration
            let bold_mod = personality_modifier(pool.boldness[slot], agent::BOLD_SAFETY_RESTORE_WEIGHT);
            delta *= bold_mod;

            pool.need_safety[slot] += delta;
        }

        // ----- Material -----
        {
            let deficit = 1.0 - pool.need_material[slot];
            let mut delta = 0.0_f32;

            // Food sufficiency
            delta += agent::MATERIAL_RESTORE_FOOD * region.food_sufficiency.min(1.5) * deficit;

            // Per-agent wealth percentile
            let wp = if slot < wealth_percentiles.len() {
                wealth_percentiles[slot]
            } else {
                0.0
            };
            delta += agent::MATERIAL_RESTORE_WEALTH * wp * deficit;

            pool.need_material[slot] += delta;
        }

        // ----- Social (pre-M50 proxy) -----
        {
            let delta = social_restoration(pool, slot, region);
            pool.need_social[slot] += delta;
        }

        // ----- Spiritual -----
        {
            let deficit = 1.0 - pool.need_spiritual[slot];
            let mut delta = 0.0_f32;

            // has_temple
            if region.has_temple {
                delta += agent::SPIRITUAL_RESTORE_TEMPLE * deficit;
            }

            // Per-agent: belief matches majority AND majority != BELIEF_NONE
            if region.majority_belief != agent::BELIEF_NONE
                && pool.beliefs[slot] == region.majority_belief
            {
                delta += agent::SPIRITUAL_RESTORE_MATCH * deficit;
            }

            pool.need_spiritual[slot] += delta;
        }

        // ----- Autonomy -----
        {
            // GATE: if displacement_turns > 0, ALL autonomy restoration blocked
            if pool.displacement_turns[slot] == 0 {
                let deficit = 1.0 - pool.need_autonomy[slot];
                let mut delta = 0.0_f32;

                // Self-governance: controller matches civ affinity
                if region.controller_civ == civ {
                    delta += agent::AUTONOMY_RESTORE_SELF_GOV * deficit;
                }

                // No persecution
                if region.persecution_intensity == 0.0 {
                    delta += agent::AUTONOMY_RESTORE_NO_PERSC * deficit;
                }

                pool.need_autonomy[slot] += delta;
            }
        }

        // ----- Purpose -----
        {
            let deficit = 1.0 - pool.need_purpose[slot];
            let mut delta = 0.0_f32;
            let occ = pool.occupations[slot] as usize;

            // Per-agent skill at current occupation
            if occ < 5 {
                let skill_level = pool.skills[slot * 5 + occ];
                delta += agent::PURPOSE_RESTORE_SKILL * skill_level * deficit;
            }

            // Per-agent soldier at war
            if pool.occupations[slot] == Occupation::Soldier as u8 && is_at_war {
                delta += agent::PURPOSE_RESTORE_WAR * deficit;
            }

            pool.need_purpose[slot] += delta;
        }
    }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/// Entry point for the needs tick: collect alive slots, decay, restore, clamp.
pub fn update_needs(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    // Collect alive slots
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&slot| pool.is_alive(slot))
        .collect();

    // Decay → Restore → Clamp
    decay_needs(pool, &alive_slots);
    restore_needs(pool, &alive_slots, regions, signals, wealth_percentiles);
    clamp_needs(pool, &alive_slots);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_region(id: u16) -> RegionState {
        let mut r = RegionState::new(id);
        r.carrying_capacity = 60;
        r.population = 30;
        r.controller_civ = 0;
        r.food_sufficiency = 1.0;
        r
    }

    fn default_signals() -> TickSignals {
        TickSignals {
            civs: vec![],
            contested_regions: vec![false],
        }
    }

    fn peacetime_signals() -> TickSignals {
        use crate::signals::CivSignals;
        TickSignals {
            civs: vec![CivSignals {
                civ_id: 0,
                stability: 50,
                is_at_war: false,
                dominant_faction: 0,
                faction_military: 0.33,
                faction_merchant: 0.33,
                faction_cultural: 0.34,
                faction_clergy: 0.0,
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
                mean_boldness: 0.0,
                mean_ambition: 0.0,
                mean_loyalty_trait: 0.0,
                gini_coefficient: 0.0,
                conquered_this_turn: false,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            }],
            contested_regions: vec![false],
        }
    }

    #[test]
    fn test_decay_basic() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        // Need starts at STARTING_NEED (0.5)
        assert!((pool.need_safety[slot] - 0.5).abs() < 0.001);

        decay_needs(&mut pool, &[slot]);

        let expected = 0.5 - agent::SAFETY_DECAY;
        assert!(
            (pool.need_safety[slot] - expected).abs() < 0.001,
            "Expected safety {} after one decay, got {}",
            expected, pool.need_safety[slot]
        );
    }

    #[test]
    fn test_decay_clamps_at_zero() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        // Set need below the decay rate
        pool.need_safety[slot] = 0.005;

        decay_needs(&mut pool, &[slot]);

        assert!(
            pool.need_safety[slot] == 0.0,
            "Expected 0.0 after decay on value below decay rate, got {}",
            pool.need_safety[slot]
        );
    }

    #[test]
    fn test_restoration_proportional() {
        // Spiritual: temple + matching belief
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 3);
        pool.need_spiritual[slot] = 0.2;

        let mut region = make_region(0);
        region.has_temple = true;
        region.majority_belief = 3; // matches agent's belief

        let signals = peacetime_signals();
        let wealth_pct = vec![0.5_f32];

        restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);

        // deficit = 0.8, temple = 0.020 * 0.8 = 0.016, match = 0.015 * 0.8 = 0.012
        // total delta = 0.028
        let expected = 0.2 + 0.028;
        assert!(
            pool.need_spiritual[slot] > 0.2,
            "Spiritual should increase from 0.2, got {}",
            pool.need_spiritual[slot]
        );
        assert!(
            (pool.need_spiritual[slot] - expected).abs() < 0.005,
            "Expected ~{}, got {}",
            expected, pool.need_spiritual[slot]
        );
        assert!(
            pool.need_spiritual[slot] < 0.3,
            "Should stay below 0.3, got {}",
            pool.need_spiritual[slot]
        );
    }

    #[test]
    fn test_restoration_diminishes_near_max() {
        // When need is 0.95, restoration delta should be tiny (<0.005)
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 3);
        pool.need_spiritual[slot] = 0.95;

        let mut region = make_region(0);
        region.has_temple = true;
        region.majority_belief = 3;

        let signals = peacetime_signals();
        let wealth_pct = vec![0.5_f32];

        let before = pool.need_spiritual[slot];
        restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);
        let delta = pool.need_spiritual[slot] - before;

        // deficit = 0.05, temple = 0.020 * 0.05 = 0.001, match = 0.015 * 0.05 = 0.00075
        // total = 0.00175
        assert!(
            delta < 0.005,
            "Restoration delta near max should be tiny, got {}",
            delta
        );
        assert!(
            delta > 0.0,
            "Should still restore a tiny amount, got {}",
            delta
        );
    }

    #[test]
    fn test_autonomy_blocked_by_displacement() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_autonomy[slot] = 0.1;
        pool.displacement_turns[slot] = 3; // displaced

        let mut region = make_region(0);
        region.controller_civ = 0; // self-gov would normally restore
        region.persecution_intensity = 0.0; // no persecution would normally restore

        let signals = peacetime_signals();
        let wealth_pct = vec![0.5_f32];

        let before = pool.need_autonomy[slot];
        restore_needs(&mut pool, &[slot], &[region], &signals, &wealth_pct);
        let after = pool.need_autonomy[slot];

        assert!(
            (after - before).abs() < 0.001,
            "Autonomy should NOT change with displacement: before={}, after={}",
            before, after
        );
    }

    #[test]
    fn test_social_restoration_blend_bonds_improve() {
        // At alpha=0.3, bonds should increase restoration vs no-bonds
        use crate::relationships::BondType;

        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_social[slot] = 0.3;

        let region = make_region(0);

        // Compute without bonds
        let result_no_bonds = social_restoration(&pool, slot, &region);

        // Add 3 positive bonds with positive sentiment
        pool.rel_bond_types[slot][0] = BondType::Friend as u8;
        pool.rel_sentiments[slot][0] = 50;
        pool.rel_bond_types[slot][1] = BondType::Kin as u8;
        pool.rel_sentiments[slot][1] = 80;
        pool.rel_bond_types[slot][2] = BondType::Mentor as u8;
        pool.rel_sentiments[slot][2] = 30;
        pool.rel_count[slot] = 3;

        // Compute with bonds — should be higher due to bond restoration
        let result_with_bonds = social_restoration(&pool, slot, &region);

        assert!(
            result_with_bonds > result_no_bonds,
            "Bonds should increase restoration: no_bonds={}, with_bonds={}",
            result_no_bonds, result_with_bonds
        );
        // Both should be positive
        assert!(
            result_no_bonds > 0.0,
            "Expected positive restoration without bonds, got {}",
            result_no_bonds
        );
    }

    #[test]
    fn test_social_restoration_proxy_matches_original() {
        // Verify social_restoration_proxy produces the expected value
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 40, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_social[slot] = 0.4;

        let region = make_region(0);

        let result = social_restoration_proxy(&pool, slot, &region);

        // pop_ratio = 30/60 = 0.5, base_rate = 0.010 * 0.5 = 0.005
        // occ_mult = 1.0 (Farmer), age_mult = min(40/40, 1.0) = 1.0
        // deficit = 1.0 - 0.4 = 0.6
        // expected = 0.005 * 1.0 * 1.0 * 0.6 = 0.003
        let expected = 0.003;
        assert!(
            (result - expected).abs() < 0.0001,
            "Expected ~{}, got {}",
            expected, result
        );
    }

    #[test]
    fn test_social_restoration_below_pop_threshold() {
        // Below population threshold → 0.0
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_social[slot] = 0.3;

        let mut region = make_region(0);
        region.population = 10;
        region.carrying_capacity = 100;
        // pop_ratio = 10/100 = 0.1, below SOCIAL_RESTORE_POP_THRESHOLD (0.3)

        let result = social_restoration(&pool, slot, &region);
        assert!(
            result == 0.0,
            "Below pop threshold should return 0.0, got {}",
            result
        );
    }

    #[test]
    fn test_equilibrium_convergence() {
        // Run 200 ticks with Safety in peacetime conditions.
        // Should converge to a stable equilibrium near 0.50-0.70.
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        // Start from a low value to see convergence
        pool.need_safety[slot] = 0.1;

        let mut region = make_region(0);
        region.food_sufficiency = 1.0;
        region.endemic_severity = 0.0;
        let regions = vec![region];

        let signals = peacetime_signals();
        let wealth_pct = vec![0.5_f32];
        let alive_slots = vec![slot];

        let mut prev = pool.need_safety[slot];
        for _ in 0..200 {
            decay_needs(&mut pool, &alive_slots);
            restore_needs(&mut pool, &alive_slots, &regions, &signals, &wealth_pct);
            clamp_needs(&mut pool, &alive_slots);
        }

        let final_val = pool.need_safety[slot];

        // Should have converged (last delta tiny)
        // Run one more tick and check delta is very small
        let before_last = pool.need_safety[slot];
        decay_needs(&mut pool, &alive_slots);
        restore_needs(&mut pool, &alive_slots, &regions, &signals, &wealth_pct);
        clamp_needs(&mut pool, &alive_slots);
        let last_delta = (pool.need_safety[slot] - before_last).abs();

        assert!(
            last_delta < 0.001,
            "Should have converged after 200 ticks, last delta = {}",
            last_delta
        );
        assert!(
            final_val > 0.50 && final_val < 0.70,
            "Equilibrium should be in 0.50-0.70, got {}",
            final_val
        );
    }
}
