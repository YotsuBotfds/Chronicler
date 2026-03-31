//! Agent decision model — rebel, migrate, switch occupation, loyalty drift.
//!
//! Each tick, agents compute utility scores for rebel, migrate, switch, and
//! stay. Gumbel-argmax selects one action; loyalty drift runs as a background
//! process for all non-rebel agents.

use std::collections::HashMap;

use crate::agent::{
    BOLD_MIGRATE_WEIGHT, BOLD_REBEL_WEIGHT, AMBITION_SWITCH_WEIGHT, LOYALTY_TRAIT_WEIGHT,
    DECISION_TEMPERATURE, LOYALTY_DRIFT_RATE, LOYALTY_FLIP_THRESHOLD, LOYALTY_RECOVERY_RATE,
    MIGRATE_CAP, MIGRATE_HYSTERESIS, MIGRATE_SATISFACTION_THRESHOLD, OCCUPATION_COUNT,
    PERSECUTION_MIGRATE_BOOST, PERSECUTION_REBEL_BOOST,
    REBEL_CAP, REBEL_LOYALTY_THRESHOLD, REBEL_MIN_COHORT, REBEL_SATISFACTION_THRESHOLD,
    STAY_BASE, SWITCH_CAP, SWITCH_OVERSUPPLY_THRESH, SWITCH_UNDERSUPPLY_FACTOR,
    W_MIGRATE_OPP, W_MIGRATE_SAT, W_REBEL, W_SWITCH,
};
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::satisfaction::target_occupation_ratio;
use crate::signals::TickSignals;
use rand::Rng;
use rand_chacha::ChaCha8Rng;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// M35a: Migration attractiveness bonus for river-connected neighbors. [CALIBRATE]
const RIVER_MIGRATION_BONUS: f32 = 0.1;
/// Spare capacity makes a destination more attractive; overcrowding makes it worse.
const MIGRATION_HEADROOM_BONUS: f32 = 0.20;
const MIGRATION_OVERCROWDING_PENALTY: f32 = 0.80;
/// Do not flee into regions that are already meaningfully more crowded.
const MIGRATION_RELATIVE_CROWDING_GUARD: f32 = 0.05;
/// If a source region is already over capacity, only move when the destination
/// offers a meaningful crowding improvement instead of a sideways shuffle.
const MIGRATION_OVERCROWD_EXIT_DELTA: f32 = 0.20;
/// Agents in stable regions should not voluntarily pile into already-overfull targets.
const MIGRATION_TARGET_SOFT_CAP: f32 = 1.10;
/// Chronic food shortages should materially reduce a destination's attractiveness.
const MIGRATION_FOOD_SIGNAL_WEIGHT: f32 = 0.25;
/// Neutral by default; left as an explicit hook for future migration retuning.
const MIGRATION_SELF_RULE_BONUS: f32 = 0.0;
/// M57b tuning: pooled household wealth dampens migration pressure for wealthy pairs.
const HOUSEHOLD_MIGRATION_WEALTH_DAMP_EXPONENT: f32 = 1.20;
/// Flat risk-aversion factor for partnered households with pooled wealth.
const HOUSEHOLD_MIGRATION_MARRIED_FACTOR: f32 = 0.88;
/// M59b: Maximum penalty applied to adjacent migration target from a threat packet.
const MAX_THREAT_PENALTY: f32 = 0.20;

// ---------------------------------------------------------------------------
// Helpers — smoothstep, gumbel_argmax
// ---------------------------------------------------------------------------

fn smoothstep(x: usize, edge0: usize, edge1: usize) -> f32 {
    if x <= edge0 { return 0.0; }
    if x >= edge1 { return 1.0; }
    let t = (x - edge0) as f32 / (edge1 - edge0) as f32;
    t * t * (3.0 - 2.0 * t)
}

/// Maps a personality dimension [-1, +1] to a utility multiplier.
/// Output clamped to >= 0.0 to prevent sign flips at high weights.
#[inline]
pub fn personality_modifier(dimension: f32, weight: f32) -> f32 {
    (1.0 + dimension * weight).max(0.0)
}

fn gumbel_argmax(utilities: &[f32], rng: &mut ChaCha8Rng, temperature: f32) -> usize {
    if temperature <= 0.0 {
        return utilities.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i)
            .unwrap_or(0);
    }
    let mut best_idx = 0;
    let mut best_val = f32::NEG_INFINITY;
    for (i, &u) in utilities.iter().enumerate() {
        let uniform: f32 = rng.gen::<f32>().max(f32::EPSILON);
        let gumbel = -temperature * (-uniform.ln()).ln();
        let perturbed = u + gumbel;
        if perturbed > best_val {
            best_val = perturbed;
            best_idx = i;
        }
    }
    best_idx
}

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

fn rebel_utility(loyalty: f32, satisfaction: f32, rebel_eligible: usize) -> f32 {
    let raw = W_REBEL
        * ((REBEL_LOYALTY_THRESHOLD - loyalty).max(0.0)
            + (REBEL_SATISFACTION_THRESHOLD - satisfaction).max(0.0));
    raw.min(REBEL_CAP) * smoothstep(rebel_eligible, REBEL_MIN_COHORT - 2, REBEL_MIN_COHORT + 3)
}

fn migrate_utility(satisfaction: f32, migration_opportunity: f32) -> f32 {
    let raw = W_MIGRATE_SAT * (MIGRATE_SATISFACTION_THRESHOLD - satisfaction).max(0.0)
        + W_MIGRATE_OPP * (migration_opportunity - MIGRATE_HYSTERESIS).max(0.0);
    raw.min(MIGRATE_CAP)
}

fn migration_region_score(region: &RegionState, mean_satisfaction: f32, pop_count: usize) -> f32 {
    let cap = region.carrying_capacity.max(1) as f32;
    let pop_ratio = pop_count as f32 / cap;
    let headroom_bonus = (1.0 - pop_ratio).clamp(-1.0, 1.0) * MIGRATION_HEADROOM_BONUS;
    let overcrowding_penalty = (pop_ratio - 1.0).max(0.0) * MIGRATION_OVERCROWDING_PENALTY;
    let food_signal = (region.food_sufficiency - 1.0).clamp(-1.0, 0.5) * MIGRATION_FOOD_SIGNAL_WEIGHT;
    mean_satisfaction + headroom_bonus - overcrowding_penalty + food_signal
}

#[inline]
fn polity_alignment_score(
    source_region: &RegionState,
    destination_region: &RegionState,
    civ: u8,
) -> f32 {
    if source_region.controller_civ != civ && destination_region.controller_civ == civ {
        MIGRATION_SELF_RULE_BONUS
    } else {
        0.0
    }
}

fn region_population_count(stats: &RegionStats, region_id: usize) -> usize {
    stats.occupation_supply[region_id].iter().sum()
}

/// Returns (best_target, migration_opportunity, choices_changed_by_threat).
fn best_migration_target_for_agent(
    pool: &AgentPool,
    regions: &[RegionState],
    stats: &RegionStats,
    region_id: usize,
    slot: usize,
) -> (u16, f32, bool) {
    let civ = pool.civ_affinity(slot);
    let own_pop = region_population_count(stats, region_id);
    let own_cap = regions[region_id].carrying_capacity.max(1) as f32;
    let own_pop_ratio = own_pop as f32 / own_cap;
    let own_mean = stats.mean_satisfaction[region_id];
    let own_score = migration_region_score(&regions[region_id], own_mean, own_pop)
        + polity_alignment_score(&regions[region_id], &regions[region_id], civ);

    let mut best_adj_score = own_score;
    let mut best_adj_id = region_id as u16;
    let mut baseline_best_adj_id = region_id as u16;
    let mut baseline_best_adj_score = own_score;
    for bit in 0..32u32 {
        if regions[region_id].adjacency_mask & (1 << bit) == 0 {
            continue;
        }
        let adj = bit as usize;
        if adj >= regions.len() {
            continue;
        }

        let adj_pop = region_population_count(stats, adj);
        let adj_cap = regions[adj].carrying_capacity.max(1) as f32;
        let adj_pop_ratio = adj_pop as f32 / adj_cap;
        if own_pop_ratio <= 1.0 && adj_pop_ratio > MIGRATION_TARGET_SOFT_CAP {
            continue;
        }
        if own_pop_ratio > 1.0
            && adj_pop_ratio > 1.0
            && adj_pop_ratio > own_pop_ratio - MIGRATION_OVERCROWD_EXIT_DELTA
        {
            continue;
        }
        if adj_pop_ratio > own_pop_ratio + MIGRATION_RELATIVE_CROWDING_GUARD
            && adj_pop_ratio > 1.0
        {
            continue;
        }

        let adj_mean = stats.mean_satisfaction[adj];
        let mut adj_score = migration_region_score(&regions[adj], adj_mean, adj_pop)
            + polity_alignment_score(&regions[region_id], &regions[adj], civ);
        if regions[region_id].river_mask & regions[adj].river_mask != 0 {
            adj_score += RIVER_MIGRATION_BONUS;
        }

        // M59b: Track baseline (pre-penalty) best for diagnostic comparison.
        // Baseline includes ALL existing modifiers (region score, polity, river).
        if adj_score > baseline_best_adj_score {
            baseline_best_adj_score = adj_score;
            baseline_best_adj_id = adj as u16;
        }

        // M59b: Apply threat penalty from held packets (adjacent only, own-region excluded)
        let threat_strength = crate::knowledge::strongest_threat_for_region(
            pool, slot, adj as u16, region_id as u16,
        );
        if threat_strength > 0.0 {
            adj_score -= MAX_THREAT_PENALTY * threat_strength;
        }

        if adj_score > best_adj_score {
            best_adj_score = adj_score;
            best_adj_id = adj as u16;
        }
    }

    let threat_changed = best_adj_id != baseline_best_adj_id;
    (best_adj_id, (best_adj_score - own_score).max(0.0), threat_changed)
}

fn switch_utility(
    occ: usize,
    supply: &[usize; OCCUPATION_COUNT],
    demand: &[f32; OCCUPATION_COUNT],
) -> (f32, u8) {
    let own_supply = supply[occ] as f32;
    let own_demand = demand[occ].max(0.01);
    let oversupply = (own_supply / own_demand - SWITCH_OVERSUPPLY_THRESH).max(0.0);

    let mut best_alt: u8 = occ as u8;
    let mut best_gap: f32 = 0.0;
    for alt in 0..OCCUPATION_COUNT {
        if alt == occ { continue; }
        let alt_supply = supply[alt] as f32;
        let alt_demand = demand[alt];
        let gap = (alt_demand - alt_supply * SWITCH_UNDERSUPPLY_FACTOR).max(0.0);
        if gap > best_gap {
            best_gap = gap;
            best_alt = alt as u8;
        }
    }

    let utility = (W_SWITCH * oversupply * best_gap).min(SWITCH_CAP);
    (utility, best_alt)
}

// ---------------------------------------------------------------------------
// RegionStats — pre-computed per-region aggregates
// ---------------------------------------------------------------------------

/// Pre-computed per-region aggregates needed by decision evaluation.
pub struct RegionStats {
    /// Count of agents per region with loyalty < REBEL_LOYALTY_THRESHOLD
    /// AND satisfaction < REBEL_SATISFACTION_THRESHOLD.
    pub rebel_eligible: Vec<usize>,
    /// Mean satisfaction per region.
    pub mean_satisfaction: Vec<f32>,
    /// Per-region, per-occupation agent count.
    pub occupation_supply: Vec<[usize; OCCUPATION_COUNT]>,
    /// Per-region demand from target_occupation_ratio * pop.
    pub occupation_demand: Vec<[f32; OCCUPATION_COUNT]>,
    /// Per-region, per-civ agent count.
    pub civ_counts: Vec<Vec<(u8, usize)>>,
    /// Per-region, per-civ mean satisfaction.
    pub civ_mean_satisfaction: Vec<Vec<(u8, f32)>>,
    /// How much better the best adjacent region is (0 if none better).
    pub migration_opportunity: Vec<f32>,
    /// Region id of the best adjacent migration target (own id if none better).
    pub best_migration_target: Vec<u16>,
}

/// Single O(n) pass over alive agents to build all region stats.
pub fn compute_region_stats(pool: &AgentPool, regions: &[RegionState], signals: &TickSignals) -> RegionStats {
    let n = regions.len();

    let mut rebel_eligible = vec![0usize; n];
    let mut sat_sum = vec![0.0f32; n];
    let mut pop_count = vec![0usize; n];
    let mut occupation_supply = vec![[0usize; OCCUPATION_COUNT]; n];
    // Per-region civ data: HashMap<civ_id, (count, satisfaction_sum)>
    let mut civ_data: Vec<HashMap<u8, (usize, f32)>> =
        (0..n).map(|_| HashMap::new()).collect();

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) {
            continue;
        }
        let r = pool.region(slot) as usize;
        if r >= n {
            continue;
        }

        // M58a: Skip non-idle merchants from ALL region aggregates
        if pool.is_on_trip(slot) {
            continue;
        }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let occ = pool.occupation(slot) as usize;
        let civ = pool.civ_affinity(slot);

        // Rebel eligibility
        if loy < REBEL_LOYALTY_THRESHOLD && sat < REBEL_SATISFACTION_THRESHOLD {
            rebel_eligible[r] += 1;
        }

        // Satisfaction accumulator
        sat_sum[r] += sat;
        pop_count[r] += 1;

        // Occupation supply
        if occ < OCCUPATION_COUNT {
            occupation_supply[r][occ] += 1;
        }

        // Civ data
        let entry = civ_data[r].entry(civ).or_insert((0, 0.0));
        entry.0 += 1;
        entry.1 += sat;
    }

    // Finalize mean satisfaction
    let mean_satisfaction: Vec<f32> = (0..n)
        .map(|r| {
            if pop_count[r] > 0 {
                sat_sum[r] / pop_count[r] as f32
            } else {
                0.0
            }
        })
        .collect();

    // Finalize occupation demand
    let occupation_demand: Vec<[f32; OCCUPATION_COUNT]> = (0..n)
        .map(|r| {
            let demand_shifts = if regions[r].controller_civ != 255 {
                signals.demand_shifts_for_civ(regions[r].controller_civ)
            } else {
                [0.0; 5]
            };
            let ratios = target_occupation_ratio(
                regions[r].terrain,
                regions[r].soil,
                regions[r].water,
                regions[r].food_sufficiency,
                demand_shifts,
            );
            let pop = pop_count[r] as f32;
            let mut demand = [0.0f32; OCCUPATION_COUNT];
            for i in 0..OCCUPATION_COUNT {
                demand[i] = ratios[i] * pop;
            }
            demand
        })
        .collect();

    // Finalize civ counts and civ mean satisfaction
    let mut civ_counts: Vec<Vec<(u8, usize)>> = Vec::with_capacity(n);
    let mut civ_mean_satisfaction: Vec<Vec<(u8, f32)>> = Vec::with_capacity(n);

    for r in 0..n {
        let mut counts: Vec<(u8, usize)> = Vec::new();
        let mut means: Vec<(u8, f32)> = Vec::new();
        for (&civ, &(count, sat_total)) in &civ_data[r] {
            counts.push((civ, count));
            let mean = if count > 0 {
                sat_total / count as f32
            } else {
                0.0
            };
            means.push((civ, mean));
        }
        // Sort by civ_id for deterministic ordering
        counts.sort_by_key(|(c, _)| *c);
        means.sort_by_key(|(c, _)| *c);
        civ_counts.push(counts);
        civ_mean_satisfaction.push(means);
    }

    let mut migration_opportunity = vec![0.0f32; n];
    let mut best_migration_target = vec![0u16; n];
    for r in 0..n {
        let own_mean = mean_satisfaction[r];
        let own_cap = regions[r].carrying_capacity.max(1) as f32;
        let own_pop_ratio = pop_count[r] as f32 / own_cap;
        let own_score = migration_region_score(&regions[r], own_mean, pop_count[r]);
        let mut best_adj_score = own_score;
        let mut best_adj_id: u16 = r as u16;
        for bit in 0..32u32 {
            if regions[r].adjacency_mask & (1 << bit) != 0 {
                let adj = bit as usize;
                if adj < n {
                    let adj_cap = regions[adj].carrying_capacity.max(1) as f32;
                    let adj_pop_ratio = pop_count[adj] as f32 / adj_cap;
                    if own_pop_ratio <= 1.0 && adj_pop_ratio > MIGRATION_TARGET_SOFT_CAP {
                        continue;
                    }
                    if own_pop_ratio > 1.0
                        && adj_pop_ratio > 1.0
                        && adj_pop_ratio > own_pop_ratio - MIGRATION_OVERCROWD_EXIT_DELTA
                    {
                        continue;
                    }
                    if adj_pop_ratio > own_pop_ratio + MIGRATION_RELATIVE_CROWDING_GUARD
                        && adj_pop_ratio > 1.0
                    {
                        continue;
                    }

                    let adj_mean = mean_satisfaction[adj];
                    let mut adj_score =
                        migration_region_score(&regions[adj], adj_mean, pop_count[adj]);
                    // M35a: River-connected neighbors get a bonus
                    if regions[r].river_mask & regions[adj].river_mask != 0 {
                        adj_score += RIVER_MIGRATION_BONUS;
                    }
                    if adj_score > best_adj_score {
                        best_adj_score = adj_score;
                        best_adj_id = adj as u16;
                    }
                }
            }
        }
        migration_opportunity[r] = (best_adj_score - own_score).max(0.0);
        best_migration_target[r] = best_adj_id;
    }

    RegionStats {
        rebel_eligible,
        mean_satisfaction,
        occupation_supply,
        occupation_demand,
        civ_counts,
        civ_mean_satisfaction,
        migration_opportunity,
        best_migration_target,
    }
}

// ---------------------------------------------------------------------------
// PendingDecisions
// ---------------------------------------------------------------------------

/// Collected decisions from one region's evaluation pass.
pub struct PendingDecisions {
    /// (slot, region) — agent rebels.
    pub rebellions: Vec<(usize, u16)>,
    /// (slot, from, to) — agent migrates.
    pub migrations: Vec<(usize, u16, u16)>,
    /// (slot, new_occ) — agent switches occupation.
    pub occupation_switches: Vec<(usize, u8)>,
    /// (slot, new_civ) — agent flips civ allegiance.
    pub loyalty_flips: Vec<(usize, u8)>,
    /// (slot, delta) — positive = recovery, negative = drift.
    pub loyalty_drifts: Vec<(usize, f32)>,
}

impl PendingDecisions {
    pub fn new() -> Self {
        Self {
            rebellions: Vec::new(),
            migrations: Vec::new(),
            occupation_switches: Vec::new(),
            loyalty_flips: Vec::new(),
            loyalty_drifts: Vec::new(),
        }
    }
}

// ---------------------------------------------------------------------------
// evaluate_region_decisions — utility-based (M32)
// ---------------------------------------------------------------------------

/// Evaluate decisions for all alive agents in a region using utility selection.
///
/// Each agent computes utility scores for rebel, migrate, switch, and stay.
/// Gumbel-argmax selects one action. Loyalty drift runs as a background
/// process for all non-rebel agents afterward.
pub fn evaluate_region_decisions(
    pool: &AgentPool,
    slots: &[usize],
    regions: &[RegionState],
    region_state: &RegionState,
    stats: &RegionStats,
    region_id: usize,
    rng: &mut ChaCha8Rng,
    id_to_slot: &std::collections::HashMap<u32, usize>,  // M57b
) -> (PendingDecisions, u32) {
    let mut pending = PendingDecisions::new();
    let mut threat_changed_count: u32 = 0;

    for &slot in slots {
        if !pool.is_alive(slot) {
            continue;
        }

        // M58a: Skip non-idle merchants from decisions (on trip)
        if pool.is_on_trip(slot) {
            continue;
        }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let civ = pool.civ_affinity(slot);
        let occ = pool.occupation(slot) as usize;

        let bold = pool.boldness(slot);
        let ambi = pool.ambition(slot);
        let ltrait = pool.loyalty_trait(slot);
        let is_displaced = pool.displacement_turns(slot) > 0;
        let (best_migration_target, migration_opportunity, threat_changed) = if is_displaced {
            (region_id as u16, 0.0, false)
        } else {
            best_migration_target_for_agent(pool, regions, stats, region_id, slot)
        };
        if threat_changed {
            threat_changed_count += 1;
        }

        // Compute utilities: utility fn -> personality modifier -> NEG_INFINITY gate
        // Modifier MUST be applied BEFORE the gate. 0.0 * modifier = 0.0 -> gated to NEG_INFINITY.
        // If placed after, NEG_INFINITY * modifier produces garbage.
        let mut rebel_util = rebel_utility(loy, sat, stats.rebel_eligible[region_id])
            * personality_modifier(bold, BOLD_REBEL_WEIGHT);
        // Recently displaced agents must settle before moving again, or migration
        // devolves into high-frequency sloshing between adjacent regions.
        let mut migrate_util = if is_displaced {
            0.0
        } else {
            migrate_utility(sat, migration_opportunity)
                * personality_modifier(bold, BOLD_MIGRATE_WEIGHT)
        };

        // M38b: Persecution boosts for agents whose belief differs from the majority
        if pool.beliefs[slot] != region_state.majority_belief {
            rebel_util += PERSECUTION_REBEL_BOOST * region_state.persecution_intensity;
            if !is_displaced {
                migrate_util += PERSECUTION_MIGRATE_BOOST * region_state.persecution_intensity;
            }
        }

        // M48: Memory-driven utility modifiers — additive, applied before NEG_INFINITY gate
        let mem_mods = crate::memory::compute_memory_utility_modifiers(pool, slot);
        rebel_util += mem_mods.rebel;
        if !is_displaced {
            migrate_util += mem_mods.migrate;
        }

        // M49: Need-driven utility modifiers — additive, applied after memory, before gate
        let need_mods = crate::needs::compute_need_utility_modifiers(pool, slot);
        rebel_util += need_mods.rebel;
        if !is_displaced {
            migrate_util += need_mods.migrate;
        }

        // M57b: Household-effective wealth modulates migration threshold for married agents.
        // Wealthier households are less likely to migrate (higher opportunity cost).
        if !is_displaced {
            let eff_wealth = crate::household::household_effective_wealth(pool, slot, id_to_slot);
            let personal_wealth = pool.wealth[slot];
            if eff_wealth > personal_wealth {
                // Married with pooled wealth: dampen migration utility slightly
                // Ratio > 1.0 means spouse has wealth; damp migration by inverse power.
                let ratio = eff_wealth / personal_wealth.max(0.01);
                migrate_util *= HOUSEHOLD_MIGRATION_MARRIED_FACTOR
                    * (1.0 / ratio.powf(HOUSEHOLD_MIGRATION_WEALTH_DAMP_EXPONENT));
            }
        }

        let u_rebel = if rebel_util > 0.0 { rebel_util } else { f32::NEG_INFINITY };
        let u_migrate = if !is_displaced && migrate_util > 0.0 {
            migrate_util
        } else {
            f32::NEG_INFINITY
        };

        let (u_switch_base, switch_target) = switch_utility(
            occ,
            &stats.occupation_supply[region_id],
            &stats.occupation_demand[region_id],
        );
        let u_switch_raw = u_switch_base * personality_modifier(ambi, AMBITION_SWITCH_WEIGHT)
            + mem_mods.switch + need_mods.switch_occ;
        let u_switch = if u_switch_raw > 0.0 { u_switch_raw } else { f32::NEG_INFINITY };

        let u_stay = STAY_BASE + mem_mods.stay + need_mods.stay;

        let chosen = gumbel_argmax(
            &[u_rebel, u_migrate, u_switch, u_stay],
            rng,
            DECISION_TEMPERATURE,
        );

        match chosen {
            0 => {
                // Rebel
                pending.rebellions.push((slot, region_id as u16));
            }
            1 => {
                if best_migration_target != region_id as u16 {
                    pending
                        .migrations
                        .push((slot, region_id as u16, best_migration_target));
                }
            }
            2 => {
                // Switch occupation
                if switch_target != occ as u8 {
                    pending.occupation_switches.push((slot, switch_target));
                }
            }
            _ => {
                // Stay — no action
            }
        }

        // Loyalty drift as background process (skip only for rebels)
        if chosen != 0 && stats.civ_counts[region_id].len() > 1 {
            // Find own civ mean satisfaction
            let own_mean = stats
                .civ_mean_satisfaction[region_id]
                .iter()
                .find(|(c, _)| *c == civ)
                .map(|(_, m)| *m)
                .unwrap_or(0.0);

            // Find best other civ mean satisfaction and its civ_id
            let mut best_other_civ: Option<u8> = None;
            let mut best_other_mean: f32 = own_mean;

            for &(c, mean) in &stats.civ_mean_satisfaction[region_id] {
                if c != civ && mean > best_other_mean {
                    best_other_mean = mean;
                    best_other_civ = Some(c);
                }
            }

            if let Some(other_civ) = best_other_civ {
                // Other civ is happier — drift away
                // Personality-modified drift: steadfast (+1) drifts slower, mercenary (-1) faster
                // M49: Autonomy need accelerates negative loyalty drift
                let autonomy_deficit = (crate::agent::AUTONOMY_THRESHOLD
                    - pool.need_autonomy[slot]).max(0.0);
                let autonomy_factor = 1.0 + autonomy_deficit * crate::agent::AUTONOMY_DRIFT_WEIGHT;
                let effective_drift = LOYALTY_DRIFT_RATE
                    * personality_modifier(-ltrait, LOYALTY_TRAIT_WEIGHT)
                    * autonomy_factor;
                if loy - effective_drift < LOYALTY_FLIP_THRESHOLD {
                    // Would drop below flip threshold — flip civ
                    pending.loyalty_flips.push((slot, other_civ));
                } else {
                    pending.loyalty_drifts.push((slot, -effective_drift));
                }
            } else {
                // No happier civ — recover loyalty
                pending.loyalty_drifts.push((slot, LOYALTY_RECOVERY_RATE));
            }
        }
    }

    (pending, threat_changed_count)
}

// ---------------------------------------------------------------------------
// evaluate_region_decisions_v1 — Phase 5 short-circuit (preserved for regression)
// ---------------------------------------------------------------------------

/// Phase 5 short-circuit decision model. Preserved for regression comparison.
#[cfg(test)]
#[allow(dead_code)]
fn evaluate_region_decisions_v1(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    stats: &RegionStats,
    region_id: usize,
) -> PendingDecisions {
    let mut pending = PendingDecisions::new();

    for &slot in slots {
        if !pool.is_alive(slot) {
            continue;
        }

        let sat = pool.satisfaction(slot);
        let loy = pool.loyalty(slot);
        let civ = pool.civ_affinity(slot);
        let occ = pool.occupation(slot) as usize;

        // 1. Rebel?
        if loy < REBEL_LOYALTY_THRESHOLD
            && sat < REBEL_SATISFACTION_THRESHOLD
            && stats.rebel_eligible[region_id] >= REBEL_MIN_COHORT
        {
            pending.rebellions.push((slot, region_id as u16));
            continue;
        }

        // 2. Migrate?
        if sat < MIGRATE_SATISFACTION_THRESHOLD && region.adjacency_mask != 0 {
            let current_mean = stats.mean_satisfaction[region_id];
            let mut best_region: Option<u16> = None;
            let mut best_sat: f32 = current_mean + 0.05;

            for bit in 0..32u32 {
                if region.adjacency_mask & (1 << bit) != 0 {
                    let adj = bit as usize;
                    if adj < stats.mean_satisfaction.len()
                        && stats.mean_satisfaction[adj] > best_sat
                    {
                        best_sat = stats.mean_satisfaction[adj];
                        best_region = Some(adj as u16);
                    }
                }
            }

            if let Some(target) = best_region {
                pending.migrations.push((slot, region_id as u16, target));
                continue;
            }
        }

        // 3. Switch occupation?
        let supply = stats.occupation_supply[region_id][occ] as f32;
        let demand = stats.occupation_demand[region_id][occ];
        let oversupply_threshold = demand * (1.0 / crate::agent::OCCUPATION_SWITCH_OVERSUPPLY);

        let mut switched = false;
        if supply > oversupply_threshold {
            let mut best_occ: Option<u8> = None;
            let mut best_gap: f32 = 0.0;

            for alt in 0..OCCUPATION_COUNT {
                if alt == occ {
                    continue;
                }
                let alt_supply = stats.occupation_supply[region_id][alt] as f32;
                let alt_demand = stats.occupation_demand[region_id][alt];
                if alt_demand > alt_supply * crate::agent::OCCUPATION_SWITCH_UNDERSUPPLY {
                    let gap = alt_demand - alt_supply;
                    if gap > best_gap {
                        best_gap = gap;
                        best_occ = Some(alt as u8);
                    }
                }
            }

            if let Some(new_occ) = best_occ {
                pending.occupation_switches.push((slot, new_occ));
                switched = true;
            }
        }

        if switched {
            continue;
        }

        // 4. Loyalty drift (only when multiple civs present)
        if stats.civ_counts[region_id].len() > 1 {
            let own_mean = stats
                .civ_mean_satisfaction[region_id]
                .iter()
                .find(|(c, _)| *c == civ)
                .map(|(_, m)| *m)
                .unwrap_or(0.0);

            let mut best_other_civ: Option<u8> = None;
            let mut best_other_mean: f32 = own_mean;

            for &(c, mean) in &stats.civ_mean_satisfaction[region_id] {
                if c != civ && mean > best_other_mean {
                    best_other_mean = mean;
                    best_other_civ = Some(c);
                }
            }

            if let Some(other_civ) = best_other_civ {
                if loy - LOYALTY_DRIFT_RATE < LOYALTY_FLIP_THRESHOLD {
                    pending.loyalty_flips.push((slot, other_civ));
                } else {
                    pending.loyalty_drifts.push((slot, -LOYALTY_DRIFT_RATE));
                }
            } else {
                pending.loyalty_drifts.push((slot, LOYALTY_RECOVERY_RATE));
            }
        }
    }

    pending
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::pool::AgentPool;
    use crate::region::RegionState;
    use crate::signals::TickSignals;

    fn default_signals(num_regions: usize) -> TickSignals {
        TickSignals {
            civs: vec![],
            contested_regions: vec![false; num_regions],
        }
    }

    fn make_region(id: u16) -> RegionState {
        let mut r = RegionState::new(id);
        r.controller_civ = 0;
        r
    }

    fn eval_region_decisions(
        pool: &AgentPool,
        slots: &[usize],
        regions: &[RegionState],
        stats: &RegionStats,
        region_id: usize,
        rng: &mut rand_chacha::ChaCha8Rng,
    ) -> PendingDecisions {
        let (pd, _threat_count) = super::evaluate_region_decisions(
            pool,
            slots,
            regions,
            &regions[region_id],
            stats,
            region_id,
            rng,
            &std::collections::HashMap::new(),  // M57b: no household effect in unit tests
        );
        pd
    }

    #[test]
    fn test_rebel_fires_with_cohort() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let mut region = make_region(0);
        region.majority_belief = 2;
        region.persecution_intensity = 1.0;
        let regions = vec![region];
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.8, 0.0, 0.0, 0, 1, 2, 1);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
            pool.need_autonomy[slot] = 0.0;
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert!(pending.rebellions.len() >= 3,
            "expected most agents to rebel, got {}", pending.rebellions.len());
    }

    #[test]
    fn test_rebel_needs_cohort() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert_eq!(pending.rebellions.len(), 0);
    }

    #[test]
    fn test_migrate_to_better_region() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.05);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..5).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert!(pending.migrations.len() >= 3,
            "expected most agents to migrate, got {}", pending.migrations.len());
        for &(_, from, to) in &pending.migrations {
            assert_eq!(from, 0);
            assert_eq!(to, 1);
        }
    }

    #[test]
    fn test_displaced_agents_do_not_chain_migrate() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.05);
            pool.set_displacement_turns(slot, 2);
        }
        for _ in 0..6 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.80);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert!(
            pending.migrations.is_empty(),
            "displaced agents should settle before migrating again, got {} migrations",
            pending.migrations.len(),
        );
    }

    #[test]
    fn test_occupation_switch_oversupplied_to_undersupplied() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let regions = vec![make_region(0)];
        let mut pool = AgentPool::new(32);
        for _ in 0..20 {
            let slot = pool.spawn(0, 0, Occupation::Priest, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.5);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..20).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert!(pending.occupation_switches.len() > 0);
        for &(_, new_occ) in &pending.occupation_switches {
            assert_eq!(new_occ, Occupation::Farmer as u8);
        }
    }

    #[test]
    fn test_loyalty_drift_without_flip() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_flips.len(), 0);
        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - (-LOYALTY_DRIFT_RATE)).abs() < 0.001);
        }
    }

    #[test]
    fn test_loyalty_drift_flips_civ() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.228);
            pool.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.9);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_flips.len(), 3);
        for &(_, new_civ) in &pending.loyalty_flips {
            assert_eq!(new_civ, 1);
        }
        assert_eq!(pending.loyalty_drifts.len(), 0);
    }

    fn test_rebel_priority_over_migrate() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.9);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..6).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        let total_actions = pending.rebellions.len() + pending.migrations.len();
        assert!(total_actions >= 4,
            "expected most agents to rebel or migrate, got {} rebels + {} migrants",
            pending.rebellions.len(), pending.migrations.len());
    }

    #[test]
    fn test_compute_region_stats_empty_region() {
        let pool = AgentPool::new(8);
        let regions = vec![make_region(0), make_region(1)];
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(stats.rebel_eligible[0], 0);
        assert_eq!(stats.mean_satisfaction[0], 0.0);
        assert_eq!(stats.occupation_supply[0], [0; OCCUPATION_COUNT]);
        assert_eq!(stats.civ_counts[0].len(), 0);
        assert_eq!(stats.migration_opportunity[0], 0.0);
    }

    #[test]
    fn test_smoothstep_below_edge0() {
        assert_eq!(super::smoothstep(0, 3, 8), 0.0);
        assert_eq!(super::smoothstep(2, 3, 8), 0.0);
        assert_eq!(super::smoothstep(3, 3, 8), 0.0);
    }

    #[test]
    fn test_smoothstep_above_edge1() {
        assert_eq!(super::smoothstep(8, 3, 8), 1.0);
        assert_eq!(super::smoothstep(10, 3, 8), 1.0);
    }

    #[test]
    fn test_smoothstep_midpoint() {
        let mid_low = super::smoothstep(5, 3, 8);
        let mid_high = super::smoothstep(6, 3, 8);
        assert!(mid_low > 0.0 && mid_low < 1.0);
        assert!(mid_high > mid_low);
    }

    #[test]
    fn test_gumbel_argmax_deterministic_at_zero_temp() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let utilities = [0.3, 0.8, 0.1, 0.5];
        for _ in 0..10 {
            let chosen = super::gumbel_argmax(&utilities, &mut rng, 0.0);
            assert_eq!(chosen, 1);
        }
    }

    #[test]
    fn test_gumbel_argmax_respects_utility_ordering() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut wins = [0u32; 4];
        for seed_byte in 0..100u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;
            let mut rng = ChaCha8Rng::from_seed(seed);
            let utilities = [0.1, 1.5, 0.3, 0.5];
            let chosen = super::gumbel_argmax(&utilities, &mut rng, 0.01);
            wins[chosen] += 1;
        }
        assert!(wins[1] > 90, "expected index 1 to win >90 times, got {}", wins[1]);
    }

    #[test]
    fn test_gumbel_argmax_zero_draws_at_zero_temp() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut rng_a = ChaCha8Rng::from_seed([0u8; 32]);
        let mut rng_b = ChaCha8Rng::from_seed([0u8; 32]);
        let _ = super::gumbel_argmax(&[0.1, 0.5, 0.3, 0.2], &mut rng_a, 0.0);
        let val_a: f32 = rng_a.gen();
        let val_b: f32 = rng_b.gen();
        assert_eq!(val_a, val_b, "T=0 path should not consume RNG draws");
    }

    #[test]
    fn test_migration_opportunity_computed() {
        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.2);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert!(stats.migration_opportunity[0] > 0.0);
        assert_eq!(stats.best_migration_target[0], 1);
        assert_eq!(stats.migration_opportunity[1], 0.0);
    }

    #[test]
    fn test_migration_avoids_food_starved_target() {
        let mut pool = AgentPool::new(128);
        let mut regions = vec![make_region(0), make_region(1), make_region(2)];
        regions[0].adjacency_mask = 0b110;
        regions[1].adjacency_mask = 0b001;
        regions[2].adjacency_mask = 0b001;
        regions[1].food_sufficiency = 0.0;
        regions[2].food_sufficiency = 1.2;

        for _ in 0..10 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.20);
        }
        for _ in 0..10 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.80);
        }
        for _ in 0..10 {
            let slot = pool.spawn(2, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.70);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(stats.best_migration_target[0], 2);
    }

    #[test]
    fn test_agent_specific_migration_uses_region_score_without_alignment_bias() {
        let mut pool = AgentPool::new(64);
        let mut regions = vec![make_region(0), make_region(1), make_region(2)];
        regions[0].adjacency_mask = 0b110;
        regions[1].adjacency_mask = 0b001;
        regions[2].adjacency_mask = 0b001;
        regions[0].controller_civ = 0;
        regions[1].controller_civ = 0;
        regions[2].controller_civ = 1;

        for _ in 0..8 {
            let slot = pool.spawn(
                0,
                1,
                Occupation::Farmer,
                25,
                1.0,
                0.0,
                0.0,
                0,
                1,
                2,
                crate::agent::BELIEF_NONE,
            );
            pool.set_satisfaction(slot, 0.10);
            pool.set_loyalty(slot, 0.60);
        }
        for _ in 0..8 {
            let slot = pool.spawn(
                1,
                0,
                Occupation::Farmer,
                25,
                0.0,
                0.0,
                0.0,
                0,
                1,
                2,
                crate::agent::BELIEF_NONE,
            );
            pool.set_satisfaction(slot, 0.75);
            pool.set_loyalty(slot, 0.60);
        }
        for _ in 0..8 {
            let slot = pool.spawn(
                2,
                1,
                Occupation::Farmer,
                25,
                0.0,
                0.0,
                0.0,
                0,
                1,
                2,
                crate::agent::BELIEF_NONE,
            );
            pool.set_satisfaction(slot, 0.68);
            pool.set_loyalty(slot, 0.60);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(
            stats.best_migration_target[0],
            1,
            "region-level targeting should still favor the slightly happier foreign-ruled region",
        );

        let (target, opportunity, _threat_changed) =
            best_migration_target_for_agent(&pool, &regions, &stats, 0, 0);
        assert_eq!(
            target, 1,
            "without an alignment bonus, agent-specific targeting should match the region-level score",
        );
        assert!(opportunity > 0.0);
    }

    #[test]
    fn test_migration_prefers_under_capacity_target() {
        let mut pool = AgentPool::new(128);
        let mut regions = vec![make_region(0), make_region(1), make_region(2)];
        regions[0].adjacency_mask = 0b110;
        regions[1].adjacency_mask = 0b001;
        regions[2].adjacency_mask = 0b001;
        regions[0].carrying_capacity = 60;
        regions[1].carrying_capacity = 20;
        regions[2].carrying_capacity = 60;

        for _ in 0..10 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.10);
        }
        for _ in 0..60 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.60);
        }
        for _ in 0..20 {
            let slot = pool.spawn(2, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.50);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(
            stats.best_migration_target[0],
            2,
            "overcrowded targets should lose to under-capacity alternatives",
        );
        assert!(stats.migration_opportunity[0] > 0.0);
    }

    #[test]
    fn test_migration_rejects_sideways_overcrowding() {
        let mut pool = AgentPool::new(128);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;
        regions[0].carrying_capacity = 50;
        regions[1].carrying_capacity = 50;

        for _ in 0..100 {
            let slot = pool.spawn(
                0,
                0,
                Occupation::Farmer,
                25,
                0.0,
                0.0,
                0.0,
                0,
                1,
                2,
                crate::agent::BELIEF_NONE,
            );
            pool.set_satisfaction(slot, 0.20);
        }
        for _ in 0..95 {
            let slot = pool.spawn(
                1,
                0,
                Occupation::Farmer,
                25,
                0.0,
                0.0,
                0.0,
                0,
                1,
                2,
                crate::agent::BELIEF_NONE,
            );
            pool.set_satisfaction(slot, 0.85);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(
            stats.best_migration_target[0],
            0,
            "slightly less crowded but still-overfull targets should not trigger migration",
        );
        assert_eq!(stats.migration_opportunity[0], 0.0);
    }

    #[test]
    fn test_migration_opportunity_no_adjacent() {
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..5 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.2);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        assert_eq!(stats.migration_opportunity[0], 0.0);
    }

    #[test]
    fn test_rebel_utility_zero_above_both_thresholds() {
        let u = super::rebel_utility(0.5, 0.5, 10);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_rebel_utility_partial_one_dimension() {
        let u = super::rebel_utility(0.1, 0.5, 10);
        assert!(u > 0.0);
        let expected = crate::agent::W_REBEL * (crate::agent::REBEL_LOYALTY_THRESHOLD - 0.1);
        assert!((u - expected).abs() < 0.01, "expected ~{}, got {}", expected, u);
    }

    #[test]
    fn test_rebel_utility_saturates_at_cap() {
        use crate::agent::REBEL_CAP;
        let u = super::rebel_utility(-1.0, -1.0, 10);
        assert!((u - REBEL_CAP).abs() < 0.01);
    }

    #[test]
    fn test_rebel_utility_smoothstep_cohort_gate() {
        use crate::agent::{REBEL_CAP, REBEL_MIN_COHORT};
        let edge0 = REBEL_MIN_COHORT.saturating_sub(2);
        let edge1 = REBEL_MIN_COHORT + 3;

        let u_zero = super::rebel_utility(-1.0, -1.0, edge0.saturating_sub(1));
        assert_eq!(u_zero, 0.0);
        let u_full = super::rebel_utility(-1.0, -1.0, edge1);
        assert!((u_full - REBEL_CAP).abs() < 0.01);
        let u_mid = super::rebel_utility(-1.0, -1.0, REBEL_MIN_COHORT);
        assert!(u_mid > 0.0 && u_mid < REBEL_CAP);
    }

    #[test]
    fn test_migrate_utility_zero_above_threshold_no_opportunity() {
        let u = super::migrate_utility(0.5, 0.0);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_migrate_utility_satisfaction_below_threshold() {
        let u = super::migrate_utility(0.1, 0.0);
        let expected = crate::agent::W_MIGRATE_SAT
            * (crate::agent::MIGRATE_SATISFACTION_THRESHOLD - 0.1);
        assert!((u - expected).abs() < 0.01, "expected ~{}, got {}", expected, u);
    }

    #[test]
    fn test_migrate_utility_saturates_at_cap() {
        use crate::agent::MIGRATE_CAP;
        let u = super::migrate_utility(0.0, 1.0);
        assert!((u - MIGRATE_CAP).abs() < 0.01);
    }

    #[test]
    fn test_migrate_utility_opportunity_below_hysteresis() {
        let u = super::migrate_utility(0.5, 0.03);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_no_oversupply() {
        let supply = [5, 0, 0, 0, 0];
        let demand = [10.0, 10.0, 10.0, 10.0, 10.0];
        let (u, _) = super::switch_utility(0, &supply, &demand);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_oversupply_no_undersupply() {
        let supply = [20, 20, 20, 20, 20];
        let demand = [5.0, 20.0, 20.0, 20.0, 20.0];
        let (u, _) = super::switch_utility(0, &supply, &demand);
        assert_eq!(u, 0.0);
    }

    #[test]
    fn test_switch_utility_both_conditions() {
        use crate::agent::{W_SWITCH, SWITCH_CAP};
        let supply = [0, 5, 5, 5, 20];
        let demand = [12.0, 5.0, 5.0, 5.0, 1.0];
        let (u, best_alt) = super::switch_utility(4, &supply, &demand);
        let expected = (W_SWITCH * 18.0 * 12.0).min(SWITCH_CAP);
        assert!((u - expected).abs() < 0.01, "expected {}, got {}", expected, u);
        assert_eq!(best_alt, 0);
    }

    #[test]
    fn test_switch_utility_returns_best_alternative() {
        let supply = [3, 0, 5, 5, 20];
        let demand = [5.0, 10.0, 5.0, 5.0, 1.0];
        let (_, best_alt) = super::switch_utility(4, &supply, &demand);
        assert_eq!(best_alt, 1);
    }

    #[test]
    fn test_switch_utility_all_farmer_region_has_recovery_path() {
        // When births temporarily push a civ into an all-farmer state, switch
        // utility must stay positive so labor diversity can recover.
        let supply = [20, 0, 0, 0, 0];
        let demand = [12.0, 3.0, 2.0, 2.0, 1.0];
        let (u, best_alt) = super::switch_utility(0, &supply, &demand);
        assert!(u > 0.0, "all-farmer collapse should produce positive switch utility");
        assert_eq!(best_alt, 1, "largest unmet demand should pull farmers toward soldiers first");
    }

    #[test]
    fn test_loyalty_recovery_when_own_civ_happier() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        let mut pool = AgentPool::new(16);
        let regions = vec![make_region(0)];
        for _ in 0..3 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.8);
        }
        for _ in 0..3 {
            let slot = pool.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.6);
            pool.set_satisfaction(slot, 0.5);
        }
        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pending = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
        assert_eq!(pending.loyalty_drifts.len(), 3);
        for &(_, delta) in &pending.loyalty_drifts {
            assert!((delta - LOYALTY_RECOVERY_RATE).abs() < 0.001);
        }
    }

    /// Extreme regression: even under the softened calibration, a cohort with
    /// maximal grievance should still decisively prefer rebellion over staying.
    #[test]
    fn test_extreme_rebel_conditions_overwhelm_stay_utility() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let mut pool = AgentPool::new(16);
        let mut region = make_region(0);
        region.majority_belief = 2;
        region.persecution_intensity = 1.0;
        let regions = vec![region];

        for _ in 0..10 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.8, 0.0, 0.0, 0, 1, 2, 1);
            pool.set_loyalty(slot, -1.0);
            pool.set_satisfaction(slot, -1.0);
            pool.need_autonomy[slot] = 0.0;
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..10).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pd = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);

        assert_eq!(
            pd.rebellions.len(),
            10,
            "extreme grievance cohort should unanimously rebel, got {} rebels",
            pd.rebellions.len()
        );
    }

    // --- personality_modifier unit tests (M33) ---

    #[test]
    fn test_personality_modifier_neutral() {
        let m = super::personality_modifier(0.0, 0.3);
        assert!((m - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_positive() {
        let m = super::personality_modifier(1.0, 0.3);
        assert!((m - 1.3).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_negative() {
        let m = super::personality_modifier(-1.0, 0.3);
        assert!((m - 0.7).abs() < 1e-6);
    }

    #[test]
    fn test_personality_modifier_floor_at_zero() {
        let m = super::personality_modifier(-1.0, 1.5);
        assert_eq!(m, 0.0);
    }

    /// M33 neutral regression: personality [0,0,0] must produce identical
    /// decisions to M32 (modifier = 1.0 + 0.0 * weight = 1.0).
    #[test]
    fn test_m33_neutral_regression() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let mut pool = AgentPool::new(32);
        let mut regions = vec![make_region(0), make_region(1)];
        regions[0].adjacency_mask = 0b10;

        for _ in 0..6 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_loyalty(slot, 0.01);
            pool.set_satisfaction(slot, 0.01);
        }
        for _ in 0..4 {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.1);
            pool.set_loyalty(slot, 0.5);
        }
        for _ in 0..5 {
            let slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool.set_satisfaction(slot, 0.8);
            pool.set_loyalty(slot, 0.5);
        }

        let stats = compute_region_stats(&pool, &regions, &default_signals(regions.len()));
        let slots: Vec<usize> = (0..10).collect();

        let mut rng_a = ChaCha8Rng::from_seed([42u8; 32]);
        let mut rng_b = ChaCha8Rng::from_seed([42u8; 32]);
        let pd_a = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng_a);
        let pd_b = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng_b);

        assert_eq!(pd_a.rebellions.len(), pd_b.rebellions.len());
        assert_eq!(pd_a.migrations.len(), pd_b.migrations.len());
        assert_eq!(pd_a.occupation_switches.len(), pd_b.occupation_switches.len());
    }

    /// M33 Tier 2: Bold agents rebel more than cautious agents in marginal conditions.
    #[test]
    fn test_m33_bold_rebels_more_than_cautious() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let mut region = make_region(0);
        region.majority_belief = 2;
        region.persecution_intensity = 1.0;
        let regions = vec![region];
        let mut bold_rebels = 0u32;
        let mut cautious_rebels = 0u32;

        for seed_byte in 0..100u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;

            let mut pool = AgentPool::new(16);
            for _ in 0..6 {
                let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.8, 0.0, 0.0, 0, 1, 2, 1);
                pool.set_loyalty(slot, 0.05);
                pool.set_satisfaction(slot, 0.05);
                pool.need_autonomy[slot] = 0.0;
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..6).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
            bold_rebels += pd.rebellions.len() as u32;

            let mut pool = AgentPool::new(16);
            for _ in 0..6 {
                let slot = pool.spawn(0, 0, Occupation::Farmer, 25, -0.8, 0.0, 0.0, 0, 1, 2, 1);
                pool.set_loyalty(slot, 0.05);
                pool.set_satisfaction(slot, 0.05);
                pool.need_autonomy[slot] = 0.0;
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..6).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
            cautious_rebels += pd.rebellions.len() as u32;
        }

        assert!(bold_rebels > cautious_rebels,
            "bold agents should rebel more: bold={} cautious={}", bold_rebels, cautious_rebels);
        assert!(bold_rebels > cautious_rebels + 20,
            "margin too small: bold={} cautious={}", bold_rebels, cautious_rebels);
    }

    /// M33 Tier 2: Ambitious agents switch occupation more than content agents.
    #[test]
    fn test_m33_ambitious_switches_more_than_content() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;

        let regions = vec![make_region(0)];
        let mut ambitious_switches = 0u32;
        let mut content_switches = 0u32;

        for seed_byte in 0..100u8 {
            let mut seed = [0u8; 32];
            seed[0] = seed_byte;

            // Ambitious cohort: 20 oversupplied priests with ambition=+0.8
            let mut pool = AgentPool::new(32);
            for _ in 0..20 {
                let slot = pool.spawn(0, 0, Occupation::Priest, 25, 0.0, 0.8, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
                pool.set_satisfaction(slot, 0.5);
                pool.set_loyalty(slot, 0.5);
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..20).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
            ambitious_switches += pd.occupation_switches.len() as u32;

            // Content cohort: same setup with ambition=-0.8
            let mut pool = AgentPool::new(32);
            for _ in 0..20 {
                let slot = pool.spawn(0, 0, Occupation::Priest, 25, 0.0, -0.8, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
                pool.set_satisfaction(slot, 0.5);
                pool.set_loyalty(slot, 0.5);
            }
            let stats = compute_region_stats(&pool, &regions, &default_signals(1));
            let slots: Vec<usize> = (0..20).collect();
            let mut rng = ChaCha8Rng::from_seed(seed);
            let pd = eval_region_decisions(&pool, &slots, &regions, &stats, 0, &mut rng);
            content_switches += pd.occupation_switches.len() as u32;
        }

        assert!(ambitious_switches > content_switches,
            "ambitious agents should switch more: ambitious={} content={}",
            ambitious_switches, content_switches);
    }

    /// M33 Tier 2: Steadfast agents drift slower than mercenary agents.
    #[test]
    fn test_m33_steadfast_drifts_less_than_mercenary() {
        use rand::SeedableRng;
        use rand_chacha::ChaCha8Rng;
        use crate::agent::LOYALTY_DRIFT_RATE;

        let regions = vec![make_region(0)];

        // Two civs in one region — triggers loyalty drift
        let mut pool_steadfast = AgentPool::new(16);
        for _ in 0..3 {
            // Steadfast civ-0 agents (loyalty_trait=+0.8)
            let slot = pool_steadfast.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.8, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_steadfast.set_loyalty(slot, 0.6);
            pool_steadfast.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            // Happier civ-1 agents (triggers drift for civ-0)
            let slot = pool_steadfast.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_steadfast.set_loyalty(slot, 0.6);
            pool_steadfast.set_satisfaction(slot, 0.8);
        }
        let stats = compute_region_stats(&pool_steadfast, &regions, &default_signals(1));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pd_steadfast = eval_region_decisions(&pool_steadfast, &slots, &regions, &stats, 0, &mut rng);

        let mut pool_mercenary = AgentPool::new(16);
        for _ in 0..3 {
            // Mercenary civ-0 agents (loyalty_trait=-0.8)
            let slot = pool_mercenary.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, -0.8, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_mercenary.set_loyalty(slot, 0.6);
            pool_mercenary.set_satisfaction(slot, 0.5);
        }
        for _ in 0..3 {
            let slot = pool_mercenary.spawn(0, 1, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_mercenary.set_loyalty(slot, 0.6);
            pool_mercenary.set_satisfaction(slot, 0.8);
        }
        let stats = compute_region_stats(&pool_mercenary, &regions, &default_signals(1));
        let slots: Vec<usize> = (0..3).collect();
        let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
        let pd_mercenary = eval_region_decisions(&pool_mercenary, &slots, &regions, &stats, 0, &mut rng);

        // Both should have drifts (multi-civ region, other civ happier)
        assert!(!pd_steadfast.loyalty_drifts.is_empty(), "steadfast should still drift");
        assert!(!pd_mercenary.loyalty_drifts.is_empty(), "mercenary should drift");

        // Steadfast drift magnitude should be smaller than mercenary
        let steadfast_mag: f32 = pd_steadfast.loyalty_drifts.iter()
            .map(|(_, d)| d.abs()).sum();
        let mercenary_mag: f32 = pd_mercenary.loyalty_drifts.iter()
            .map(|(_, d)| d.abs()).sum();

        // Steadfast: DRIFT_RATE * (1.0 + (-0.8) * 0.3) = 0.02 * 0.76 = 0.0152 per agent
        // Mercenary: DRIFT_RATE * (1.0 + (0.8) * 0.3)  = 0.02 * 1.24 = 0.0248 per agent
        assert!(steadfast_mag < mercenary_mag,
            "steadfast drift {} should be less than mercenary drift {}",
            steadfast_mag, mercenary_mag);

        // Verify exact values for one drift
        // loyalty_trait = +0.8 (steadfast), modifier = (1.0 + (-0.8) * 0.3) = 0.76
        let expected_steadfast_drift = LOYALTY_DRIFT_RATE * 0.76;
        let expected_mercenary_drift = LOYALTY_DRIFT_RATE * 1.24;
        for &(_, d) in &pd_steadfast.loyalty_drifts {
            assert!((d.abs() - expected_steadfast_drift).abs() < 0.001,
                "steadfast drift {} != expected {}", d.abs(), expected_steadfast_drift);
        }
        for &(_, d) in &pd_mercenary.loyalty_drifts {
            assert!((d.abs() - expected_mercenary_drift).abs() < 0.001,
                "mercenary drift {} != expected {}", d.abs(), expected_mercenary_drift);
        }
    }
}

#[cfg(test)]
mod river_tests {
    use super::*;
    use crate::region::RegionState;
    use crate::pool::AgentPool;
    use crate::agent::Occupation;
    use crate::signals::TickSignals;

    #[test]
    fn test_river_migration_bonus() {
        let mut regions = vec![
            RegionState::new(0),
            RegionState::new(1),
            RegionState::new(2),
        ];
        // Region 0 adjacent to 1 and 2
        regions[0].adjacency_mask = 0b110;
        regions[1].adjacency_mask = 0b001;
        regions[2].adjacency_mask = 0b001;

        // River: regions 0 and 1 share river 0
        regions[0].river_mask = 1;
        regions[1].river_mask = 1;
        regions[2].river_mask = 0;

        for r in &mut regions {
            r.carrying_capacity = 60;
            r.population = 30;
            r.soil = 0.8;
            r.water = 0.6;
            r.forest_cover = 0.3;
            r.controller_civ = 0;
        }

        // Make region 2 slightly more attractive than region 1
        regions[2].water = 0.65;  // slightly better ecology

        let signals = TickSignals {
            civs: vec![],
            contested_regions: vec![false, false, false],
        };
        let mut pool = AgentPool::new(100);
        for _ in 0..10 {
            pool.spawn(0, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..10 {
            pool.spawn(1, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..10 {
            pool.spawn(2, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5, 0, 1, 2, crate::agent::BELIEF_NONE);
        }

        let stats = compute_region_stats(&pool, &regions, &signals);
        assert_eq!(stats.best_migration_target[0], 1,
            "River-connected region should be preferred migration target");
    }
}

