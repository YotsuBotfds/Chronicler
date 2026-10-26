/// M49 Needs System
/// Spec: docs/superpowers/specs/2026-03-20-m49-needs-system-design.md
/// Calibration (2026-10): docs/integration/needs-calibration.md

use std::collections::HashMap;

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
    /// The positive parts of `migrate` before the cap (safety, material,
    /// spiritual, social). Diagnostic only, for the migration budget.
    pub migrate_push: [f32; 4],
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
        mods.migrate_push[0] = safety_deficit * agent::SAFETY_WEIGHT;
        mods.stay -= safety_deficit * agent::SAFETY_WEIGHT;
    }

    // Material → migrate +, switch + (not for farmers). Needs calibration
    // (2026-10): want sends people to other work, in a food shortage mostly
    // to the fields (satisfaction::target_occupation_ratio); a farmer's want
    // is the harvest's, and leaving the fields would deepen it (and farmers
    // bear more children: demographics' FERTILITY_BASE_FARMER).
    let material_deficit = (agent::MATERIAL_THRESHOLD - pool.need_material[slot]).max(0.0);
    if material_deficit > 0.0 {
        mods.migrate += material_deficit * agent::MATERIAL_WEIGHT;
        mods.migrate_push[1] = material_deficit * agent::MATERIAL_WEIGHT;
        if pool.occupations[slot] != Occupation::Farmer as u8 {
            mods.switch_occ += material_deficit * agent::MATERIAL_WEIGHT;
        }
    }

    // Social → migrate +. Needs calibration (2026-10): an isolated agent,
    // with no bonds where it lives, has nothing holding it there and moves
    // more; bonded agents are held by the migration drivers' roots
    // (`migration_drivers`) and pulled toward emigrated kin by chain
    // migration. The old term (deficit → stay +, migrate -) made isolation
    // anchor agents, the reverse of its own rationale.
    let social_deficit = (agent::SOCIAL_THRESHOLD - pool.need_social[slot]).max(0.0);
    if social_deficit > 0.0 {
        mods.migrate += social_deficit * agent::SOCIAL_WEIGHT;
        mods.migrate_push[3] = social_deficit * agent::SOCIAL_WEIGHT;
    }

    // Spiritual → migrate +
    let spiritual_deficit = (agent::SPIRITUAL_THRESHOLD - pool.need_spiritual[slot]).max(0.0);
    if spiritual_deficit > 0.0 {
        mods.migrate += spiritual_deficit * agent::SPIRITUAL_WEIGHT;
        mods.migrate_push[2] = spiritual_deficit * agent::SPIRITUAL_WEIGHT;
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
// Social restoration
// ---------------------------------------------------------------------------

/// Community proxy: population/capacity ratio, occupation and age.
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

/// Positive-valence bonds with positive sentiment whose holder is alive and
/// lives in the agent's region. Bonds to people elsewhere (left behind by a
/// migration) or to the dead give no company.
pub fn co_resident_bonds(pool: &AgentPool, slot: usize, id_to_slot: &HashMap<u32, usize>) -> u32 {
    let region = pool.regions[slot];
    let mut count = 0u32;
    for i in 0..(pool.rel_count[slot] as usize).min(crate::relationships::REL_SLOTS) {
        if !crate::relationships::is_positive_valence(pool.rel_bond_types[slot][i])
            || pool.rel_sentiments[slot][i] <= 0
        {
            continue;
        }
        let target_id = pool.rel_target_ids[slot][i];
        if let Some(&t) = id_to_slot.get(&target_id) {
            if t < pool.capacity()
                && pool.is_alive(t)
                && pool.ids[t] == target_id
                && pool.regions[t] == region
            {
                count += 1;
            }
        }
    }
    count
}

/// Social restoration: co-resident bonds plus the community proxy.
fn social_restoration(pool: &AgentPool, slot: usize, region: &RegionState, co_resident: u32) -> f32 {
    let proxy = social_restoration_proxy(pool, slot, region);
    let deficit = 1.0 - pool.need_social[slot];
    let bond_factor = agent::SOCIAL_RESTORE_BOND
        * (co_resident as f32 / agent::SOCIAL_BOND_TARGET).min(1.0)
        * deficit;
    proxy + bond_factor
}

/// The strongest remembered conquest of the agent's region by a civ other
/// than its own (|intensity| / 127, decayed with the memory). A conquest by
/// the agent's own civ, or by one it has since joined, does not count.
fn conquest_grievance(pool: &AgentPool, slot: usize) -> f32 {
    let civ = pool.civ_affinities[slot];
    let mut best = 0.0f32;
    for i in 0..(pool.memory_count[slot] as usize).min(crate::memory::MEMORY_SLOTS) {
        if pool.memory_event_types[slot][i] == crate::memory::MemoryEventType::Conquest as u8
            && pool.memory_source_civs[slot][i] != civ
        {
            let v = (pool.memory_intensities[slot][i] as f32).abs() / 127.0;
            best = best.max(v);
        }
    }
    best.min(1.0)
}

// ---------------------------------------------------------------------------
// Restore — proportional restoration and condition pressure for all 6 needs
// ---------------------------------------------------------------------------

/// Co-resident bond counts (`co_resident_bonds`) of the given slots,
/// indexed by slot.
pub fn co_resident_counts(pool: &AgentPool, alive_slots: &[usize]) -> Vec<u32> {
    let id_to_slot = pool.build_id_to_slot();
    let mut co_resident = vec![0u32; pool.capacity()];
    for &slot in alive_slots {
        co_resident[slot] = co_resident_bonds(pool, slot, &id_to_slot);
    }
    co_resident
}

/// Apply proportional restoration to all 6 needs for alive agents, and the
/// condition pressures and shocks of safety, material and autonomy.
/// Each need has per-agent restoration conditions that create behavioral
/// diversity between agents in the same region.
pub fn restore_needs(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
) {
    let co_resident = co_resident_counts(pool, alive_slots);
    restore_needs_with_bonds(pool, alive_slots, regions, signals, wealth_percentiles, &co_resident);
}

/// [`restore_needs`] with the co-resident bond counts given (indexed by
/// slot; a missing slot counts none).
pub fn restore_needs_with_bonds(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &[f32],
    co_resident: &[u32],
) {
    for &slot in alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx >= regions.len() {
            continue;
        }
        let region = &regions[region_idx];
        let civ = pool.civ_affinities[slot];
        let is_urban = pool.settlement_ids[slot] != 0;

        // Look up civ signals (guard for out-of-bounds)
        let civ_signals = signals.civs.get(civ as usize);
        let is_at_war = civ_signals.map_or(false, |c| c.is_at_war);
        let contested = signals.contested_regions.get(region_idx).copied().unwrap_or(false);
        // A war zone: armies, battles or occupation in a region whose ruler
        // or whose people's civ is at war (armies alone, in peace, are not).
        let ruler_at_war = signals
            .civs
            .get(region.controller_civ as usize)
            .map_or(false, |c| c.is_at_war);
        let war_zone = contested && (is_at_war || ruler_at_war);

        // ----- Safety -----
        {
            let deficit = 1.0 - pool.need_safety[slot];
            let mut delta = 0.0_f32;

            // NOT at war
            if !is_at_war {
                delta += agent::SAFETY_RESTORE_PEACE * deficit;
            }

            // No armies, battles or occupation in the region
            if !contested {
                delta += agent::SAFETY_RESTORE_SECURE * deficit;
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

            // M56b: Urban safety restoration penalty
            if is_urban {
                delta *= agent::URBAN_SAFETY_RESTORATION_MULT;
            }

            // Pressure and shocks: a war zone; a conquest or a raid this
            // turn. (Epidemic deaths act through the health term, not as
            // violence.)
            if war_zone {
                delta -= agent::SAFETY_WAR_ZONE_PRESSURE;
            }
            if region.controller_changed_this_turn {
                delta -= agent::SAFETY_CONQUEST_SHOCK;
            }
            if region.raided_this_turn {
                delta -= agent::SAFETY_RAID_SHOCK;
            }

            pool.need_safety[slot] += delta;
        }

        // ----- Material -----
        {
            let deficit = 1.0 - pool.need_material[slot];
            let mut delta = 0.0_f32;

            // Food sufficiency (per-term urban modifier)
            let mut food_contribution = agent::MATERIAL_RESTORE_FOOD
                * region.food_sufficiency.min(1.5) * deficit;
            if is_urban {
                food_contribution *= agent::URBAN_FOOD_SUFFICIENCY_MULT;
            }
            delta += food_contribution;

            // Per-agent wealth percentile (per-term urban modifier)
            let wp = if slot < wealth_percentiles.len() {
                wealth_percentiles[slot]
            } else {
                0.0
            };
            let shortfall = (1.0 - region.food_sufficiency).clamp(0.0, 1.0);
            let mut wealth_contribution = (agent::MATERIAL_RESTORE_WEALTH
                + agent::MATERIAL_RESTORE_WEALTH_SHORTAGE * shortfall)
                * wp * deficit;
            if is_urban {
                wealth_contribution *= agent::URBAN_WEALTH_RESTORATION_MULT;
            }
            delta += wealth_contribution;

            // Crafts (2026-10): wares in use (tools, cloth, pots), up to the
            // people's demand; 0 without a wares market.
            if region.craft_sufficiency > 0.0 {
                delta += agent::MATERIAL_RESTORE_CRAFTS * region.craft_sufficiency.min(1.0) * deficit;
            }

            // Pressure: dearth and famine, graded as the hunger mortality
            // bands grade them (the severe run includes this turn).
            let (dearth, famine) = crate::demographics::hunger_components(
                region.food_sufficiency,
                region.food_severe_turns,
            );
            delta -= agent::MATERIAL_DEARTH_PRESSURE * dearth
                + agent::MATERIAL_FAMINE_PRESSURE * famine;

            pool.need_material[slot] += delta;
        }

        // ----- Social -----
        {
            let bonds = co_resident.get(slot).copied().unwrap_or(0);
            let mut delta = social_restoration(pool, slot, region, bonds);
            // M56b: Urban social restoration bonus
            if is_urban {
                delta *= agent::URBAN_SOCIAL_RESTORATION_MULT;
            }
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
            let persecuted = region.persecutes(pool.beliefs[slot]);
            let mut delta = 0.0_f32;
            // A move does not oppress: every move is the agent's or its
            // household's own decision. The displacement turns after a move
            // still bar another move (behavior.rs) and cost satisfaction; they
            // no longer block autonomy restoration (needs follow-ups, 2026-10).
            let deficit = 1.0 - pool.need_autonomy[slot];

            // Self-governance: controller matches civ affinity
            if region.controller_civ == civ {
                delta += agent::AUTONOMY_RESTORE_SELF_GOV * deficit;
            }

            // Not persecuted: the agent's faith is not the one targeted
            if !persecuted {
                delta += agent::AUTONOMY_RESTORE_NO_PERSC * deficit;
            }

            // Pressure: persecution of the agent's faith, harsh rule, and a
            // remembered conquest by another civ.
            if persecuted {
                delta -= agent::AUTONOMY_PERSECUTION_PRESSURE
                    * region.persecution_intensity.clamp(0.0, 1.0);
            }
            if region.harsh_rule > 0.0 {
                delta -= agent::AUTONOMY_HARSH_RULE_PRESSURE * region.harsh_rule.min(1.0);
            }
            delta -= agent::AUTONOMY_CONQUEST_PRESSURE * conquest_grievance(pool, slot);

            pool.need_autonomy[slot] += delta;
            // A conquest strips the conquered of their say at once.
            if region.controller_changed_this_turn && region.controller_civ != civ {
                pool.need_autonomy[slot] = pool.need_autonomy[slot].min(agent::AUTONOMY_CONQUEST_CAP);
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
// Newborns
// ---------------------------------------------------------------------------

/// The needs a newborn takes from its birth parent: safety, material,
/// social, spiritual and autonomy, in that order. They follow conditions the
/// child is born into (region, war, food, faith, rule). Purpose follows the
/// agent's own skill at its work, and a newborn's starts at STARTING_NEED.
pub fn inherited_needs(pool: &AgentPool, parent: usize) -> [f32; 5] {
    [
        pool.need_safety[parent],
        pool.need_material[parent],
        pool.need_social[parent],
        pool.need_spiritual[parent],
        pool.need_autonomy[parent],
    ]
}

/// Start a newborn from its birth parent's needs ([`inherited_needs`],
/// read before the tick's deaths) instead of STARTING_NEED for all six, so
/// that a need does not mark a young agent (needs follow-ups, 2026-10).
pub fn set_newborn_needs(pool: &mut AgentPool, child: usize, inherited: [f32; 5]) {
    pool.need_safety[child] = inherited[0];
    pool.need_material[child] = inherited[1];
    pool.need_social[child] = inherited[2];
    pool.need_spiritual[child] = inherited[3];
    pool.need_autonomy[child] = inherited[4];
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

    // Decay → Restore → Clamp. Co-resident bonds are counted inside
    // restore_needs; decay moves no one.
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

        restore_needs_with_bonds(&mut pool, &[slot], &[region], &signals, &wealth_pct, &[0]);

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
    fn test_wares_in_use_restore_the_material_need() {
        let signals = peacetime_signals();
        let material_after = |craft_sufficiency: f32| {
            let mut pool = AgentPool::new(8);
            let slot = pool.spawn(0, 0, Occupation::Merchant, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
            pool.need_material[slot] = 0.2;
            let mut region = make_region(0);
            region.craft_sufficiency = craft_sufficiency;
            restore_needs(&mut pool, &[slot], &[region], &signals, &[0.5]);
            pool.need_material[slot]
        };
        let (none, full, glut) = (material_after(0.0), material_after(1.0), material_after(2.0));
        // deficit 0.8: full supply adds MATERIAL_RESTORE_CRAFTS x 0.8; a glut no more.
        assert!((full - none - agent::MATERIAL_RESTORE_CRAFTS * 0.8).abs() < 1e-6, "{none} {full}");
        assert_eq!(glut, full);
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
        restore_needs_with_bonds(&mut pool, &[slot], &[region], &signals, &wealth_pct, &[0]);
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
    fn test_autonomy_restores_after_a_move() {
        // A displaced agent (just moved) restores autonomy as a settled one does.
        let region = make_region(0);
        let signals = peacetime_signals();
        let wealth_pct = vec![0.5_f32];
        let after = |displacement: u8| {
            let mut pool = AgentPool::new(8);
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
            pool.need_autonomy[slot] = 0.1;
            pool.displacement_turns[slot] = displacement;
            restore_needs_with_bonds(&mut pool, &[slot], &[region.clone()], &signals, &wealth_pct, &[0]);
            pool.need_autonomy[slot]
        };
        // self-rule and no persecution: (0.031 + 0.060) x deficit 0.9
        assert!((after(0) - (0.1 + 0.091 * 0.9)).abs() < 1e-5, "{}", after(0));
        assert_eq!(after(3), after(0));
    }

    #[test]
    fn test_social_restoration_co_resident_bonds_improve() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_social[slot] = 0.3;

        let region = make_region(0);

        let result_no_bonds = social_restoration(&pool, slot, &region, 0);
        let result_one = social_restoration(&pool, slot, &region, 1);
        let result_two = social_restoration(&pool, slot, &region, 2);
        let result_three = social_restoration(&pool, slot, &region, 3);

        assert!(result_no_bonds > 0.0, "the community proxy alone restores a little");
        assert!(result_one > result_no_bonds);
        // Saturates at SOCIAL_BOND_TARGET (one) co-resident bond
        assert!((result_two - result_one).abs() < 1e-7);
        assert!((result_three - result_one).abs() < 1e-7);
        // bond part at the target = 0.054 * deficit 0.7 = 0.0378
        assert!((result_one - result_no_bonds - 0.0378).abs() < 1e-5);
    }

    #[test]
    fn test_co_resident_bonds_count_only_living_neighbours() {
        use crate::relationships::BondType;
        let mut pool = AgentPool::new(8);
        let a = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let here = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let away = pool.spawn(1, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let dead = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let rival = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let faded = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let bonds = [
            (here, BondType::Kin, 60i8),
            (away, BondType::Kin, 60),
            (dead, BondType::Friend, 40),
            (rival, BondType::Rival, -20),
            (faded, BondType::Friend, 0),
        ];
        for (i, (t, bt, sent)) in bonds.iter().enumerate() {
            pool.rel_target_ids[a][i] = pool.ids[*t];
            pool.rel_bond_types[a][i] = *bt as u8;
            pool.rel_sentiments[a][i] = *sent;
        }
        pool.rel_count[a] = bonds.len() as u8;
        pool.kill(dead);
        let map = pool.build_id_to_slot();
        assert_eq!(co_resident_bonds(&pool, a, &map), 1);
        // The bonded neighbour leaves: no company left.
        pool.regions[here] = 1;
        assert_eq!(co_resident_bonds(&pool, a, &map), 0);
    }

    #[test]
    fn test_isolation_binds_and_bonds_hold() {
        let mut pool = AgentPool::new(8);
        let alone = pool.spawn(0, 0, Occupation::Farmer, 40, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let bonded = pool.spawn(0, 0, Occupation::Farmer, 40, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let mut region = make_region(0);
        region.population = 60;
        let regions = vec![region];
        let signals = peacetime_signals();
        let wp = vec![0.5_f32; 2];
        let slots = vec![alone, bonded];
        let mut co = vec![0u32; 2];
        co[bonded] = 1;
        let mut bound_at = None;
        for t in 0..40 {
            decay_needs(&mut pool, &slots);
            restore_needs_with_bonds(&mut pool, &slots, &regions, &signals, &wp, &co);
            clamp_needs(&mut pool, &slots);
            if bound_at.is_none() && pool.need_social[alone] < agent::SOCIAL_THRESHOLD {
                bound_at = Some(t + 1);
            }
        }
        let t = bound_at.expect("an isolated agent's social need binds");
        assert!(t <= 15, "binds within 15 turns, took {}", t);
        assert!((pool.need_social[bonded] - 0.615).abs() < 0.02, "bonded {}", pool.need_social[bonded]);
    }

    #[test]
    fn test_material_want_moves_non_farmers_to_other_work_not_farmers() {
        let mut pool = AgentPool::new(8);
        let farmer = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let smith = pool.spawn(0, 0, Occupation::Merchant, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        for &s in &[farmer, smith] {
            pool.need_safety[s] = 0.9;
            pool.need_social[s] = 0.9;
            pool.need_spiritual[s] = 0.9;
            pool.need_autonomy[s] = 0.9;
            pool.need_purpose[s] = 0.9;
            pool.need_material[s] = 0.1;
        }
        let expected = 0.2 * agent::MATERIAL_WEIGHT;
        let f = compute_need_utility_modifiers(&pool, farmer);
        let m = compute_need_utility_modifiers(&pool, smith);
        assert!((f.migrate - expected).abs() < 1e-6 && (m.migrate - expected).abs() < 1e-6);
        assert_eq!(f.switch_occ, 0.0);
        assert!((m.switch_occ - expected).abs() < 1e-6);
    }

    #[test]
    fn test_social_deficit_pushes_migration_not_staying() {
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_safety[slot] = 0.9;
        pool.need_material[slot] = 0.9;
        pool.need_spiritual[slot] = 0.9;
        pool.need_autonomy[slot] = 0.9;
        pool.need_purpose[slot] = 0.9;
        pool.need_social[slot] = 0.05;
        let mods = compute_need_utility_modifiers(&pool, slot);
        let expected = (agent::SOCIAL_THRESHOLD - 0.05) * agent::SOCIAL_WEIGHT;
        assert!((mods.migrate - expected).abs() < 1e-6, "migrate {}", mods.migrate);
        assert!((mods.migrate_push[3] - expected).abs() < 1e-6);
        assert_eq!(mods.stay, 0.0);
        assert_eq!((mods.rebel, mods.switch_occ), (0.0, 0.0));
    }

    fn run_turns(pool: &mut AgentPool, slots: &[usize], regions: &[RegionState],
                 signals: &TickSignals, wp: &[f32], turns: usize) {
        let co = vec![2u32; pool.capacity()];
        for _ in 0..turns {
            decay_needs(pool, slots);
            restore_needs_with_bonds(pool, slots, regions, signals, wp, &co);
            clamp_needs(pool, slots);
        }
    }

    #[test]
    fn test_material_binds_in_famine_by_wealth() {
        // Poor, median and rich agents; a fed region, then a famine at 0.4.
        let mut pool = AgentPool::new(8);
        let poor = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let mid = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let rich = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let slots = vec![poor, mid, rich];
        let wp = vec![0.1_f32, 0.5, 0.9];
        let signals = peacetime_signals();
        let fed = vec![make_region(0)];
        run_turns(&mut pool, &slots, &fed, &signals, &wp, 60);
        for &s in &slots {
            assert!(pool.need_material[s] > agent::MATERIAL_THRESHOLD + 0.1,
                "fed agents stay well above the threshold: {}", pool.need_material[s]);
        }
        assert!((pool.need_material[mid] - 0.62).abs() < 0.02, "fed median {}", pool.need_material[mid]);

        let mut famine = make_region(0);
        famine.food_sufficiency = 0.4;
        famine.food_severe_turns = 5;
        let famine = vec![famine];
        run_turns(&mut pool, &slots, &famine, &signals, &wp, 6);
        assert!(pool.need_material[poor] < agent::MATERIAL_THRESHOLD, "poor bind within 6 turns");
        run_turns(&mut pool, &slots, &famine, &signals, &wp, 14);
        assert!(pool.need_material[mid] < agent::MATERIAL_THRESHOLD, "median binds within 20 turns");
        assert!(pool.need_material[rich] > agent::MATERIAL_THRESHOLD,
            "the rich do not: {}", pool.need_material[rich]);
    }

    #[test]
    fn test_material_dearth_binds_the_poor_only() {
        let mut pool = AgentPool::new(8);
        let poor = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let mid = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let slots = vec![poor, mid];
        let wp = vec![0.1_f32, 0.5];
        let mut dearth = make_region(0);
        dearth.food_sufficiency = 0.8;
        run_turns(&mut pool, &slots, &[dearth], &peacetime_signals(), &wp, 60);
        assert!(pool.need_material[poor] < agent::MATERIAL_THRESHOLD);
        assert!(pool.need_material[mid] > agent::MATERIAL_THRESHOLD + 0.1);
    }

    #[test]
    fn test_safety_binds_in_a_war_zone_not_at_home() {
        let mut pool = AgentPool::new(8);
        let front = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let home = pool.spawn(1, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let slots = vec![front, home];
        let wp = vec![0.5_f32; 2];
        let mut calm = make_region(0);
        calm.endemic_severity = 0.0;
        let mut calm1 = make_region(1);
        calm1.endemic_severity = 0.0;
        let regions = vec![calm, calm1];
        let mut peace = peacetime_signals();
        peace.contested_regions = vec![false, false];
        run_turns(&mut pool, &slots, &regions, &peace, &wp, 60);
        assert!((pool.need_safety[front] - 0.667).abs() < 0.02, "peace {}", pool.need_safety[front]);
        // Armies in the region of a civ at peace: no war zone.
        let mut armies = peacetime_signals();
        armies.contested_regions = vec![true, false];
        run_turns(&mut pool, &slots, &regions, &armies, &wp, 60);
        assert!(pool.need_safety[front] > agent::SAFETY_THRESHOLD + 0.15, "armies in peace {}", pool.need_safety[front]);
        let mut war = peacetime_signals();
        war.civs[0].is_at_war = true;
        war.contested_regions = vec![true, false];
        run_turns(&mut pool, &slots, &regions, &war, &wp, 6);
        assert!(pool.need_safety[front] < agent::SAFETY_THRESHOLD, "front {}", pool.need_safety[front]);
        run_turns(&mut pool, &slots, &regions, &war, &wp, 48);
        assert!(pool.need_safety[home] > agent::SAFETY_THRESHOLD + 0.15, "home front {}", pool.need_safety[home]);
    }

    #[test]
    fn test_safety_shocks_from_conquest_and_raids() {
        let mut calm = make_region(0);
        calm.endemic_severity = 0.0;
        let signals = peacetime_signals();
        let wp = vec![0.5_f32];
        let mut base = AgentPool::new(8);
        let s0 = base.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        base.need_safety[s0] = 0.6;
        restore_needs_with_bonds(&mut base, &[s0], &[calm.clone()], &signals, &wp, &[0]);
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_safety[slot] = 0.6;
        let mut hit = calm.clone();
        hit.controller_changed_this_turn = true;
        hit.raided_this_turn = true;
        hit.catastrophe_deaths_this_turn = 3; // epidemic or war deaths: no shock of their own
        restore_needs_with_bonds(&mut pool, &[slot], &[hit], &signals, &wp, &[0]);
        let drop = base.need_safety[s0] - pool.need_safety[slot];
        let expected = agent::SAFETY_CONQUEST_SHOCK + agent::SAFETY_RAID_SHOCK;
        assert!((drop - expected).abs() < 1e-5, "drop {} expected {}", drop, expected);
    }

    #[test]
    fn test_autonomy_persecution_targets_the_faith_not_the_region() {
        let mut pool = AgentPool::new(8);
        // Belief 3 is persecuted by a ruler enforcing belief 1.
        let target = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 3);
        let faithful = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 1);
        let slots = vec![target, faithful];
        let mut region = make_region(0);
        region.persecution_intensity = 0.5;
        region.persecuting_faith = 1;
        region.majority_belief = 1;
        let wp = vec![0.5_f32; 2];
        run_turns(&mut pool, &slots, &[region], &peacetime_signals(), &wp, 40);
        assert!(pool.need_autonomy[target] < agent::AUTONOMY_THRESHOLD,
            "persecuted {}", pool.need_autonomy[target]);
        assert!((pool.need_autonomy[faithful] - 0.75).abs() < 0.02,
            "the ruler's faith {}", pool.need_autonomy[faithful]);
    }

    #[test]
    fn test_autonomy_conquest_memory_and_harsh_rule_press_the_conquered() {
        let mut pool = AgentPool::new(8);
        let conquered = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        let settler = pool.spawn(0, 1, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        for &s in &[conquered, settler] {
            pool.need_autonomy[s] = 0.5;
            pool.memory_event_types[s][0] = crate::memory::MemoryEventType::Conquest as u8;
            pool.memory_source_civs[s][0] = 1; // conquered by civ 1
            pool.memory_intensities[s][0] = -127;
            pool.memory_count[s] = 1;
        }
        let mut region = make_region(0);
        region.controller_civ = 1;
        let wp = vec![0.5_f32; 2];
        let mut signals = peacetime_signals();
        signals.civs.push(signals.civs[0].clone());
        signals.civs[1].civ_id = 1;
        restore_needs_with_bonds(&mut pool, &[conquered, settler], &[region.clone()], &signals, &wp, &[0, 0]);
        // conquered: foreign rule (no self-government), not persecuted, full grievance
        let exp_c = 0.5 + agent::AUTONOMY_RESTORE_NO_PERSC * 0.5 - agent::AUTONOMY_CONQUEST_PRESSURE;
        let exp_s = 0.5 + (agent::AUTONOMY_RESTORE_SELF_GOV + agent::AUTONOMY_RESTORE_NO_PERSC) * 0.5;
        assert!((pool.need_autonomy[conquered] - exp_c).abs() < 1e-5);
        assert!((pool.need_autonomy[settler] - exp_s).abs() < 1e-5, "the conqueror's own people are free");
        // Martial law weighs on everyone in the region; it binds the
        // conquered, not the ruler's own people.
        region.harsh_rule = 1.0;
        let slots = [conquered, settler];
        pool.memory_count[conquered] = 0;
        pool.memory_count[settler] = 0;
        run_turns(&mut pool, &slots, &[region.clone()], &signals, &wp, 80);
        assert!(pool.need_autonomy[conquered] < agent::AUTONOMY_THRESHOLD);
        assert!((pool.need_autonomy[settler] - 0.42).abs() < 0.02, "settler {}", pool.need_autonomy[settler]);
        // The turn of a conquest caps the conquered's autonomy, not the conqueror's.
        region.harsh_rule = 0.0;
        region.controller_changed_this_turn = true;
        pool.need_autonomy[conquered] = 0.8;
        pool.need_autonomy[settler] = 0.8;
        restore_needs_with_bonds(&mut pool, &slots, &[region], &signals, &wp, &[0, 0]);
        assert_eq!(pool.need_autonomy[conquered], agent::AUTONOMY_CONQUEST_CAP);
        assert!(pool.need_autonomy[settler] > 0.75);
    }

    #[test]
    fn test_social_restoration_proxy_matches_original() {
        // Verify social_restoration_proxy produces the expected value
        let mut pool = AgentPool::new(8);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 40, 0.0, 0.0, 0.0, 0, 0, 0, 0xFF);
        pool.need_social[slot] = 0.4;

        let region = make_region(0);

        let result = social_restoration_proxy(&pool, slot, &region);

        // pop_ratio = 30/60 = 0.5, base_rate = 0.019 * 0.5 = 0.0095
        // occ_mult = 1.0 (Farmer), age_mult = min(40/40, 1.0) = 1.0
        // deficit = 1.0 - 0.4 = 0.6
        // expected = 0.0095 * 1.0 * 1.0 * 0.6 = 0.0057
        let expected = 0.0057;
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

        let result = social_restoration(&pool, slot, &region, 0);
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

        for _ in 0..200 {
            decay_needs(&mut pool, &alive_slots);
            restore_needs_with_bonds(&mut pool, &alive_slots, &regions, &signals, &wealth_pct, &[0]);
            clamp_needs(&mut pool, &alive_slots);
        }

        let final_val = pool.need_safety[slot];

        // Should have converged (last delta tiny)
        // Run one more tick and check delta is very small
        let before_last = pool.need_safety[slot];
        decay_needs(&mut pool, &alive_slots);
        restore_needs_with_bonds(&mut pool, &alive_slots, &regions, &signals, &wealth_pct, &[0]);
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
