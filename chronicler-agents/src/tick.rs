//! Full tick orchestration: skill growth -> satisfaction -> decisions -> demographics.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;

use crate::agent::{
    DECISION_STREAM_OFFSET, PERSONALITY_STREAM_OFFSET,
    LIFE_EVENT_LOYALTY_FLIP, LIFE_EVENT_MIGRATION, LIFE_EVENT_OCC_SWITCH,
    LIFE_EVENT_REBELLION, LIFE_EVENT_WAR_SURVIVAL,
    OCCUPATION_COUNT, SKILL_NEWBORN, SKILL_RESET_ON_SWITCH,
};
use crate::behavior::{compute_region_stats, evaluate_region_decisions};
use crate::demographics;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::satisfaction;
use crate::signals::TickSignals;

// ---------------------------------------------------------------------------
// AgentEvent
// ---------------------------------------------------------------------------

/// Lightweight event emitted during tick processing for the Python layer to
/// consume. Event types: 0=death, 1=rebellion, 2=migration, 3=occ_switch,
/// 4=loyalty_flip, 5=birth.
pub struct AgentEvent {
    pub agent_id: u32,
    pub event_type: u8,
    pub region: u16,
    pub target_region: u16,
    pub civ_affinity: u8,
    pub occupation: u8,
    pub turn: u32,
}

// ---------------------------------------------------------------------------
// Public tick entry point
// ---------------------------------------------------------------------------

pub fn tick_agents(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    master_seed: [u8; 32],
    turn: u32,
    wealth_percentiles: &mut [f32],
) -> Vec<AgentEvent> {
    let num_regions = regions.len();
    let mut events: Vec<AgentEvent> = Vec::new();

    // -----------------------------------------------------------------------
    // M48: Collect alive slots and decay memories as FIRST operation
    // -----------------------------------------------------------------------
    let alive_slots: Vec<usize> = (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect();
    crate::memory::decay_memories(pool, &alive_slots);
    let mut memory_intents: Vec<crate::memory::MemoryIntent> = Vec::with_capacity(alive_slots.len());

    // -----------------------------------------------------------------------
    // 0. Skill growth — iterate all alive agents
    // -----------------------------------------------------------------------
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            pool.grow_skill(slot);
            // Update promotion progress for named character promotion
            let occ = pool.occupations[slot] as usize;
            let skill = pool.skills[slot * 5 + occ];
            if skill > crate::agent::PROMOTION_SKILL_THRESHOLD {
                pool.promotion_progress[slot] =
                    pool.promotion_progress[slot].saturating_add(1);
            } else {
                pool.promotion_progress[slot] = 0;
            }
        }
    }

    // -----------------------------------------------------------------------
    // 0.5 Wealth accumulation, decay, per-civ rank (M41)
    // -----------------------------------------------------------------------
    wealth_tick(pool, regions, signals, wealth_percentiles);

    // -----------------------------------------------------------------------
    // 1. Update satisfaction
    // -----------------------------------------------------------------------
    update_satisfaction(pool, regions, signals, wealth_percentiles);

    // -----------------------------------------------------------------------
    // M48: Famine + Prosperity intents (post-satisfaction, post-wealth)
    // -----------------------------------------------------------------------
    for &slot in &alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx < regions.len() {
            // Famine: food_sufficiency below threshold
            if regions[region_idx].food_sufficiency < crate::agent::FAMINE_MEMORY_THRESHOLD {
                memory_intents.push(crate::memory::MemoryIntent {
                    agent_slot: slot,
                    event_type: crate::memory::MemoryEventType::Famine as u8,
                    source_civ: pool.civ_affinities[slot],
                    intensity: crate::agent::FAMINE_DEFAULT_INTENSITY,
                });
            }
        }
        // Prosperity: wealth above threshold
        if pool.wealth[slot] > crate::agent::PROSPERITY_THRESHOLD {
            memory_intents.push(crate::memory::MemoryIntent {
                agent_slot: slot,
                event_type: crate::memory::MemoryEventType::Prosperity as u8,
                source_civ: pool.civ_affinities[slot],
                intensity: crate::agent::PROSPERITY_DEFAULT_INTENSITY,
            });
        }
    }

    // -----------------------------------------------------------------------
    // 2. Pre-compute region stats for decisions
    // -----------------------------------------------------------------------
    let stats = compute_region_stats(pool, regions, signals);

    // -----------------------------------------------------------------------
    // 3. Decisions — per-region parallel via rayon
    // -----------------------------------------------------------------------
    let region_groups = pool.partition_by_region(num_regions as u16);

    let pending_decisions: Vec<_> = {
        let pool_ref = &*pool;
        let stats_ref = &stats;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                let mut rng = ChaCha8Rng::from_seed(master_seed);
                rng.set_stream(
                    region_id as u64 * 1000 + turn as u64 + DECISION_STREAM_OFFSET,
                );
                evaluate_region_decisions(
                    pool_ref,
                    slots,
                    &regions[region_id],
                    stats_ref,
                    region_id,
                    &mut rng,
                )
            })
            .collect()
    };

    // -----------------------------------------------------------------------
    // 4. Apply decisions sequentially
    // -----------------------------------------------------------------------
    for pd in &pending_decisions {
        // Rebellions
        for &(slot, region) in &pd.rebellions {
            pool.life_events[slot] |= LIFE_EVENT_REBELLION;
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 1,
                region,
                target_region: 0,
                civ_affinity: pool.civ_affinity(slot),
                occupation: pool.occupation(slot),
                turn,
            });
        }

        // Migrations
        for &(slot, from, to) in &pd.migrations {
            pool.set_region(slot, to);
            pool.set_displacement_turns(slot, 3);
            pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 2,
                region: from,
                target_region: to,
                civ_affinity: pool.civ_affinity(slot),
                occupation: pool.occupation(slot),
                turn,
            });
        }

        // Occupation switches
        for &(slot, new_occ) in &pd.occupation_switches {
            let old_occ = pool.occupation(slot);
            pool.set_occupation(slot, new_occ);
            // Set skill floor for new occupation
            let skill_idx = slot * 5 + new_occ as usize;
            if pool.skills[skill_idx] < SKILL_RESET_ON_SWITCH {
                pool.skills[skill_idx] = SKILL_RESET_ON_SWITCH;
            }
            pool.life_events[slot] |= LIFE_EVENT_OCC_SWITCH;
            pool.promotion_progress[slot] = 0;
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 3,
                region: pool.region(slot),
                target_region: 0,
                civ_affinity: pool.civ_affinity(slot),
                occupation: pool.occupation(slot),
                turn,
            });
            let _ = old_occ; // suppress unused warning
        }

        // Loyalty flips
        for &(slot, new_civ) in &pd.loyalty_flips {
            pool.set_civ_affinity(slot, new_civ);
            pool.set_loyalty(slot, 0.5);
            pool.life_events[slot] |= LIFE_EVENT_LOYALTY_FLIP;
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 4,
                region: pool.region(slot),
                target_region: 0,
                civ_affinity: new_civ,
                occupation: pool.occupation(slot),
                turn,
            });
        }

        // Loyalty drifts
        for &(slot, delta) in &pd.loyalty_drifts {
            let new_loy = (pool.loyalty(slot) + delta).clamp(0.0, 1.0);
            pool.set_loyalty(slot, new_loy);
        }

        // M48: Migration intents
        for &(slot, _from, _to) in &pd.migrations {
            memory_intents.push(crate::memory::MemoryIntent {
                agent_slot: slot,
                event_type: crate::memory::MemoryEventType::Migration as u8,
                source_civ: pool.civ_affinities[slot],
                intensity: crate::agent::MIGRATION_DEFAULT_INTENSITY,
            });
        }
    }

    // -----------------------------------------------------------------------
    // M48: Battle + Victory intents (soldiers in contested regions)
    // -----------------------------------------------------------------------
    {
        let region_groups_battle = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups_battle.iter().enumerate() {
            let is_contested = region_id < signals.contested_regions.len()
                && signals.contested_regions[region_id];
            if !is_contested {
                continue;
            }
            for &slot in slots {
                if !pool.is_alive(slot) {
                    continue;
                }
                let is_soldier = pool.occupations[slot]
                    == crate::agent::Occupation::Soldier as u8;
                if is_soldier {
                    // Battle intent for soldiers in contested regions
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: slot,
                        event_type: crate::memory::MemoryEventType::Battle as u8,
                        source_civ: pool.civ_affinities[slot],
                        intensity: crate::agent::BATTLE_DEFAULT_INTENSITY,
                    });
                    // Victory intent if this region's war was won
                    if region_id < regions.len() && regions[region_id].war_won_this_turn {
                        memory_intents.push(crate::memory::MemoryIntent {
                            agent_slot: slot,
                            event_type: crate::memory::MemoryEventType::Victory as u8,
                            source_civ: pool.civ_affinities[slot],
                            intensity: crate::agent::VICTORY_DEFAULT_INTENSITY,
                        });
                    }
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // M48: Conquest + Secession intents (region-wide signals)
    // -----------------------------------------------------------------------
    {
        let region_groups_signal = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups_signal.iter().enumerate() {
            if region_id >= regions.len() {
                continue;
            }
            let region = &regions[region_id];
            if region.controller_changed_this_turn {
                for &slot in slots {
                    if pool.is_alive(slot) {
                        memory_intents.push(crate::memory::MemoryIntent {
                            agent_slot: slot,
                            event_type: crate::memory::MemoryEventType::Conquest as u8,
                            source_civ: pool.civ_affinities[slot],
                            intensity: crate::agent::CONQUEST_DEFAULT_INTENSITY,
                        });
                    }
                }
            }
            if region.seceded_this_turn {
                for &slot in slots {
                    if pool.is_alive(slot) {
                        memory_intents.push(crate::memory::MemoryIntent {
                            agent_slot: slot,
                            event_type: crate::memory::MemoryEventType::Secession as u8,
                            source_civ: pool.civ_affinities[slot],
                            intensity: crate::agent::SECESSION_DEFAULT_INTENSITY,
                        });
                    }
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // 5. Demographics — per-region parallel
    // -----------------------------------------------------------------------
    // Re-partition after migrations may have moved agents.
    let region_groups = pool.partition_by_region(num_regions as u16);

    let demo_results: Vec<DemographicsPending> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                let mut rng = ChaCha8Rng::from_seed(master_seed);
                rng.set_stream(
                    region_id as u64 * 1000 + turn as u64
                        + crate::agent::DEMOGRAPHICS_STREAM_OFFSET,
                );
                tick_region_demographics(
                    pool_ref,
                    slots,
                    &regions[region_id],
                    signals,
                    region_id,
                    &mut rng,
                    master_seed,
                    turn,
                )
            })
            .collect()
    };

    // -----------------------------------------------------------------------
    // M48: Build agent_id → slot reverse index for DeathOfKin lookups.
    // Must be built BEFORE deaths so we can find children of dying parents.
    // -----------------------------------------------------------------------
    let mut id_to_slot: std::collections::HashMap<u32, usize> =
        std::collections::HashMap::with_capacity(pool.alive_count());
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            id_to_slot.insert(pool.ids[slot], slot);
        }
    }

    // Build parent_id → Vec<child_slot> reverse index for DeathOfKin
    let mut parent_to_children: std::collections::HashMap<u32, Vec<usize>> =
        std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let parent_id = pool.parent_ids[slot];
            if parent_id != crate::agent::PARENT_NONE {
                parent_to_children.entry(parent_id).or_default().push(slot);
            }
        }
    }

    // Sequential apply: deaths, age increments, births
    for dr in &demo_results {
        // Deaths
        for &(slot, region) in &dr.deaths {
            events.push(AgentEvent {
                agent_id: pool.id(slot),
                event_type: 0,
                region,
                target_region: 0,
                civ_affinity: pool.civ_affinity(slot),
                occupation: pool.occupation(slot),
                turn,
            });

            // M48: DeathOfKin intent for each living child of the dying agent
            let dying_agent_id = pool.ids[slot];
            if let Some(children) = parent_to_children.get(&dying_agent_id) {
                for &child_slot in children {
                    // Only emit for children still alive at this point
                    if pool.is_alive(child_slot) {
                        memory_intents.push(crate::memory::MemoryIntent {
                            agent_slot: child_slot,
                            event_type: crate::memory::MemoryEventType::DeathOfKin as u8,
                            source_civ: pool.civ_affinities[child_slot],
                            intensity: crate::agent::DEATHOFKIN_DEFAULT_INTENSITY,
                        });
                    }
                }
            }

            pool.kill(slot);
        }

        // Age increments
        for &slot in &dr.aged {
            pool.increment_age(slot);
        }

        // Births
        for birth in &dr.births {
            let new_slot = pool.spawn(
                birth.region,
                birth.civ,
                crate::agent::Occupation::Farmer,
                0,
                birth.personality[0],
                birth.personality[1],
                birth.personality[2],
                birth.cultural_values[0],
                birth.cultural_values[1],
                birth.cultural_values[2],
                birth.belief,
            );
            pool.set_loyalty(new_slot, birth.parent_loyalty);
            pool.parent_ids[new_slot] = birth.parent_id;
            // Set all 5 skill slots to SKILL_NEWBORN
            for occ in 0..OCCUPATION_COUNT {
                pool.skills[new_slot * 5 + occ] = SKILL_NEWBORN;
            }
            events.push(AgentEvent {
                agent_id: pool.id(new_slot),
                event_type: 5,
                region: birth.region,
                target_region: 0,
                civ_affinity: birth.civ,
                occupation: crate::agent::Occupation::Farmer as u8,
                turn,
            });

            // M48: BirthOfKin intent for the parent
            if let Some(&parent_slot) = id_to_slot.get(&birth.parent_id) {
                if pool.is_alive(parent_slot) {
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: parent_slot,
                        event_type: crate::memory::MemoryEventType::BirthOfKin as u8,
                        source_civ: pool.civ_affinities[parent_slot],
                        intensity: crate::agent::BIRTHOFKIN_DEFAULT_INTENSITY,
                    });
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // 6. Cultural drift (M36)
    // -----------------------------------------------------------------------
    {
        let region_groups = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups.iter().enumerate() {
            if !slots.is_empty() {
                let drift_mult = signals.civs.iter()
                    .find(|c| c.civ_id == regions[region_id].controller_civ)
                    .map(|c| c.cultural_drift_multiplier)
                    .unwrap_or(1.0);
                crate::culture_tick::culture_tick(
                    pool, slots, &regions[region_id],
                    master_seed, turn, region_id, drift_mult,
                );
            }
        }
    }

    // -----------------------------------------------------------------------
    // Stage 7: Conversion (M37)
    // Note: reuses stage 6's partition pattern. No agents move between stages 6-7.
    // -----------------------------------------------------------------------
    // M48: Snapshot LIFE_EVENT_CONVERSION bits BEFORE conversion_tick runs,
    // so we can detect which agents are NEWLY converted this tick.
    let pre_conversion_bits: Vec<bool> = (0..pool.capacity())
        .map(|s| pool.life_events[s] & crate::agent::LIFE_EVENT_CONVERSION != 0)
        .collect();
    {
        let region_groups = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups.iter().enumerate() {
            if !slots.is_empty() {
                let religion_mult = signals.civs.iter()
                    .find(|c| c.civ_id == regions[region_id].controller_civ)
                    .map(|c| c.religion_intensity_multiplier)
                    .unwrap_or(1.0);
                crate::conversion_tick::conversion_tick(
                    pool, slots, &regions[region_id],
                    master_seed, turn, region_id, religion_mult,
                );
            }
        }
    }

    // -----------------------------------------------------------------------
    // M48: Conversion + Persecution intents (after conversion tick)
    // -----------------------------------------------------------------------
    {
        let region_groups_conv = pool.partition_by_region(num_regions as u16);
        for (region_id, slots) in region_groups_conv.iter().enumerate() {
            if region_id >= regions.len() {
                continue;
            }
            let region = &regions[region_id];
            for &slot in slots {
                if !pool.is_alive(slot) {
                    continue;
                }
                // Conversion: newly converted this tick (bit was OFF before, ON after)
                let newly_converted = slot < pre_conversion_bits.len()
                    && !pre_conversion_bits[slot]
                    && (pool.life_events[slot] & crate::agent::LIFE_EVENT_CONVERSION != 0);
                if newly_converted {
                    // Intensity: +50 voluntary, -50 if conquest conversion active
                    let intensity = if region.conquest_conversion_active {
                        -(crate::agent::CONVERSION_DEFAULT_INTENSITY.unsigned_abs() as i8)
                    } else {
                        crate::agent::CONVERSION_DEFAULT_INTENSITY
                    };
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: slot,
                        event_type: crate::memory::MemoryEventType::Conversion as u8,
                        source_civ: pool.civ_affinities[slot],
                        intensity,
                    });
                }
                // Persecution: minority belief + nonzero persecution intensity
                if region.persecution_intensity > 0.0
                    && pool.beliefs[slot] != region.majority_belief
                    && pool.beliefs[slot] != crate::agent::BELIEF_NONE
                {
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: slot,
                        event_type: crate::memory::MemoryEventType::Persecution as u8,
                        source_civ: pool.civ_affinities[slot],
                        intensity: crate::agent::PERSECUTION_DEFAULT_INTENSITY,
                    });
                }
            }
        }
    }

    // Mark war survival for agents in contested regions who survived
    for (region_id, slots) in region_groups.iter().enumerate() {
        if region_id < signals.contested_regions.len()
            && signals.contested_regions[region_id]
        {
            for &slot in slots {
                if pool.is_alive(slot) {
                    pool.life_events[slot] |= LIFE_EVENT_WAR_SURVIVAL;
                }
            }
        }
    }

    // Decrement displacement turns for all alive agents
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) && pool.displacement_turns(slot) > 0 {
            pool.set_displacement_turns(slot, pool.displacement_turns(slot) - 1);
        }
    }

    // -----------------------------------------------------------------------
    // M48: Gate clearing + consolidated memory write (LAST operation)
    // -----------------------------------------------------------------------
    {
        let post_alive: Vec<usize> = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s))
            .collect();
        crate::memory::clear_memory_gates(
            pool,
            &post_alive,
            regions,
            &signals.contested_regions,
        );
        crate::memory::write_all_memories(pool, &memory_intents, turn as u16);
    }

    events
}

// ---------------------------------------------------------------------------
// M41: Wealth tick — accumulation, decay, per-civ rank
// ---------------------------------------------------------------------------

/// Wealth accumulation, multiplicative decay, and per-civ percentile ranking.
/// Must run BEFORE update_satisfaction (which consumes wealth_percentiles).
pub fn wealth_tick(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    wealth_percentiles: &mut [f32],
) {
    // --- Step 1: Accumulation + Decay ---
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }

        let region_id = pool.regions[slot] as usize;
        if region_id >= regions.len() { continue; }
        let region = &regions[region_id];
        let occ = pool.occupations[slot];
        let civ = pool.civ_affinities[slot];

        // Note: O(n) lookup per agent. If benchmarks show this matters, pre-build
        // a [Option<&CivSignals>; 256] lookup array before the loop.
        let civ_sig = signals.civs.iter().find(|c| c.civ_id == civ);
        let at_war = civ_sig.map_or(false, |c| c.is_at_war);
        let conquered = civ_sig.map_or(false, |c| c.conquered_this_turn);

        let income = match occ {
            0 => {
                // Farmer — M42: market-derived modifier replaces is_extractive() dispatch
                let yield_val = region.resource_yields[0];
                crate::agent::BASE_FARMER_INCOME * region.farmer_income_modifier * yield_val
            }
            1 => {
                // Soldier — war bonus + conquest bonus
                crate::agent::SOLDIER_INCOME * (1.0 + crate::agent::AT_WAR_BONUS * at_war as i32 as f32)
                    + crate::agent::CONQUEST_BONUS * conquered as i32 as f32
            }
            2 => {
                // Merchant — M42: arbitrage-driven income from Python-side goods economy
                region.merchant_trade_income
            }
            3 => {
                // Scholar — flat
                crate::agent::SCHOLAR_INCOME
            }
            _ => {
                // Priest — M42: base income + per-priest tithe share
                crate::agent::PRIEST_INCOME
                    + civ_sig.map_or(0.0, |c| c.priest_tithe_share)
            }
        };

        pool.wealth[slot] += income;
        // Multiplicative decay
        pool.wealth[slot] *= 1.0 - crate::agent::WEALTH_DECAY;
        pool.wealth[slot] = pool.wealth[slot].clamp(0.0, crate::agent::MAX_WEALTH);
    }

    // --- Step 2: Per-civ percentile ranking ---
    // Note: HashMap allocates per tick. With <16 civs this is fast, but if
    // benchmarks show allocation pressure, refactor to a reusable [Vec; 256].
    let mut civ_groups: std::collections::HashMap<u8, Vec<(usize, f32)>> =
        std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        let civ = pool.civ_affinities[slot];
        civ_groups.entry(civ).or_default().push((slot, pool.wealth[slot]));
    }

    for (_civ, mut agents) in civ_groups {
        // Sort ascending by wealth — total_cmp: no panic on NaN
        agents.sort_by(|a, b| a.1.total_cmp(&b.1));
        let denom = (agents.len() as f32 - 1.0).max(1.0);
        for (rank, (slot, _)) in agents.iter().enumerate() {
            wealth_percentiles[*slot] = rank as f32 / denom;
        }
    }
}

// ---------------------------------------------------------------------------
// Satisfaction update
// ---------------------------------------------------------------------------

fn update_satisfaction(pool: &mut AgentPool, regions: &[RegionState], signals: &TickSignals, wealth_percentiles: &[f32]) {
    // Pre-compute region stats for demand/supply ratio
    let stats = compute_region_stats(pool, regions, signals);

    // Partition agents by region
    let num_regions = regions.len();
    let region_groups = pool.partition_by_region(num_regions as u16);

    // Compute satisfaction per-region in parallel.
    // Collect (slot, sat) pairs — avoids unsafe mutable aliasing on pool.satisfactions.
    let updates: Vec<Vec<(usize, f32)>> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                if region_id >= regions.len() {
                    return Vec::new();
                }
                let region = &regions[region_id];

                slots
                    .iter()
                    .map(|&slot| {
                        let occ = pool_ref.occupation(slot);
                        let civ = pool_ref.civ_affinity(slot) as usize;

                        let civ_sig = signals
                            .civs
                            .iter()
                            .find(|c| c.civ_id as usize == civ);

                        let civ_stability = civ_sig.map_or(50, |c| c.stability);
                        let civ_at_war = civ_sig.map_or(false, |c| c.is_at_war);
                        let region_contested = if region_id < signals.contested_regions.len() {
                            signals.contested_regions[region_id]
                        } else {
                            false
                        };

                        let occ_idx = occ as usize;
                        let supply = stats.occupation_supply[region_id][occ_idx] as f32;
                        let demand = stats.occupation_demand[region_id][occ_idx];
                        let ds_ratio = if supply > 0.0 {
                            (demand - supply) / supply
                        } else {
                            0.0
                        };

                        let pop = stats.occupation_supply[region_id]
                            .iter()
                            .sum::<usize>() as f32;
                        let cap = region.carrying_capacity as f32;
                        let pop_over_cap = if cap > 0.0 { pop / cap } else { 1.0 };

                        let occ_matches = match civ_sig {
                            Some(cs) => match cs.dominant_faction {
                                0 => occ == 1,  // military -> soldiers
                                1 => occ == 2,  // merchant -> merchants
                                2 => occ == 3,  // cultural -> scholars
                                3 => occ == 4,  // M38a: clergy -> priests
                                _ => false,
                            },
                            None => false,
                        };

                        let is_displaced = pool_ref.displacement_turns(slot) > 0;

                        let faction_influence = match civ_sig {
                            Some(cs) => match occ {
                                1 => cs.faction_military,
                                2 => cs.faction_merchant,
                                3 => cs.faction_cultural,
                                4 => cs.faction_clergy,   // M38a
                                _ => 0.0,
                            },
                            None => 0.0,
                        };

                        let shock = signals.shock_for_civ(pool_ref.civ_affinity(slot));
                        let gini = civ_sig.map_or(0.0, |c| c.gini_coefficient);
                        let wealth_pct = wealth_percentiles[slot];

                        let agent_values = [
                            pool_ref.cultural_value_0[slot],
                            pool_ref.cultural_value_1[slot],
                            pool_ref.cultural_value_2[slot],
                        ];

                        let sat = satisfaction::compute_satisfaction_with_culture(
                            &satisfaction::SatisfactionInputs {
                                occupation: occ,
                                soil: region.soil,
                                water: region.water,
                                civ_stability,
                                demand_supply_ratio: ds_ratio,
                                pop_over_capacity: pop_over_cap,
                                civ_at_war,
                                region_contested,
                                occ_matches_faction: occ_matches,
                                is_displaced,
                                trade_routes: region.trade_route_count,
                                faction_influence,
                                shock,
                                agent_values,
                                controller_values: region.controller_values,
                                agent_belief: pool_ref.beliefs[slot],
                                majority_belief: region.majority_belief,
                                has_temple: region.has_temple,
                                persecution_intensity: region.persecution_intensity,
                                gini_coefficient: gini,
                                wealth_percentile: wealth_pct,
                                food_sufficiency: region.food_sufficiency,
                                merchant_margin: region.merchant_margin,
                            },
                        );

                        (slot, sat)
                    })
                    .collect()
            })
            .collect()
    };

    // Apply collected satisfaction values sequentially
    for region_updates in &updates {
        for &(slot, sat) in region_updates {
            pool.set_satisfaction(slot, sat);
        }
    }
}

// ---------------------------------------------------------------------------
// Demographics (parallel per-region)
// ---------------------------------------------------------------------------

struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],
    cultural_values: [u8; 3],
    belief: u8,  // M37: inherited from parent
    parent_id: u32,  // M39: stable agent_id of biological parent
}

struct DemographicsPending {
    /// (slot, region_id)
    deaths: Vec<(usize, u16)>,
    aged: Vec<usize>,
    births: Vec<BirthInfo>,
}

fn tick_region_demographics(
    pool: &AgentPool,
    slots: &[usize],
    region: &RegionState,
    signals: &TickSignals,
    region_id: usize,
    rng: &mut ChaCha8Rng,
    master_seed: [u8; 32],
    turn: u32,
) -> DemographicsPending {
    let mut pending = DemographicsPending {
        deaths: Vec::new(),
        aged: Vec::new(),
        births: Vec::new(),
    };

    let eco_stress = demographics::ecological_stress(region);

    // Dedicated personality RNG (offset 700) decoupled from demographics RNG.
    // Prevents adding/removing mortality checks from changing personality assignments.
    let mut personality_rng = ChaCha8Rng::from_seed(master_seed);
    personality_rng.set_stream(
        region_id as u64 * 1000 + turn as u64 + PERSONALITY_STREAM_OFFSET,
    );

    for &slot in slots {
        let age = pool.age(slot);
        let occ = pool.occupation(slot);
        let civ = pool.civ_affinity(slot) as usize;
        let sat = pool.satisfaction(slot);

        // Is this a soldier at war?
        let civ_at_war = signals
            .civs
            .iter()
            .find(|c| c.civ_id as usize == civ)
            .map_or(false, |c| c.is_at_war);
        let is_soldier_at_war = occ == 1 && civ_at_war;

        let mort_rate = demographics::mortality_rate(age, eco_stress, is_soldier_at_war, region.endemic_severity);

        if rng.gen::<f32>() < mort_rate {
            pending.deaths.push((slot, region_id as u16));
        } else {
            pending.aged.push(slot);

            // Fertility check (only for survivors)
            let fert_rate = demographics::fertility_rate(age, sat, occ, region.soil);
            if fert_rate > 0.0 && rng.gen::<f32>() < fert_rate {
                let civ_id = pool.civ_affinity(slot);
                // M39: inherit personality from parent (tighter noise than civ-mean assignment)
                let parent_personality = [
                    pool.boldness[slot],
                    pool.ambition[slot],
                    pool.loyalty_trait[slot],
                ];
                let personality = crate::demographics::inherit_personality(
                    &mut personality_rng, parent_personality,
                );
                pending.births.push(BirthInfo {
                    region: region_id as u16,
                    civ: civ_id,
                    parent_loyalty: pool.loyalty(slot),
                    personality,
                    cultural_values: [
                        pool.cultural_value_0[slot],
                        pool.cultural_value_1[slot],
                        pool.cultural_value_2[slot],
                    ],
                    belief: pool.beliefs[slot],  // M37: read in parallel phase
                    parent_id: pool.ids[slot],  // M39: slot IS the parent in this loop
                });
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
    use crate::signals::CivSignals;

    fn make_healthy_region(id: u16) -> RegionState {
        RegionState {
            region_id: id,
            terrain: 0,
            carrying_capacity: 60,
            population: 60,
            soil: 0.8,
            water: 0.6,
            forest_cover: 0.3,
            adjacency_mask: 0,
            controller_civ: 255,
            trade_route_count: 0,
            resource_types: [255, 255, 255],
            resource_yields: [0.0, 0.0, 0.0],
            resource_reserves: [1.0, 1.0, 1.0],
            season: 0,
            season_id: 0,
            river_mask: 0,
            endemic_severity: 0.0,
            culture_investment_active: false,
            controller_values: [0xFF, 0xFF, 0xFF],
            conversion_rate: 0.0,
            conversion_target_belief: 0xFF,
            conquest_conversion_active: false,
            majority_belief: 0xFF,
            has_temple: false,
            persecution_intensity: 0.0,
            schism_convert_from: 0xFF,
            schism_convert_to: 0xFF,
            farmer_income_modifier: 1.0,
            food_sufficiency: 1.0,
            merchant_margin: 0.0,
            merchant_trade_income: 0.0,
            controller_changed_this_turn: false,
            war_won_this_turn: false,
            seceded_this_turn: false,
        }
    }

    fn make_default_signals(num_civs: usize, num_regions: usize) -> TickSignals {
        TickSignals {
            civs: (0..num_civs)
                .map(|i| CivSignals {
                    civ_id: i as u8,
                    stability: 50,
                    is_at_war: false,
                    dominant_faction: 0,
                    faction_military: 0.33,
                    faction_merchant: 0.33,
                    faction_cultural: 0.34,
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
                    faction_clergy: 0.0,
                    gini_coefficient: 0.0,
                    conquered_this_turn: false,
                    priest_tithe_share: 0.0,
                    cultural_drift_multiplier: 1.0,
                    religion_intensity_multiplier: 1.0,
                })
                .collect(),
            contested_regions: vec![false; num_regions],
        }
    }

    #[test]
    fn test_tick_agents_reduces_population() {
        let mut pool = AgentPool::new(0);
        let regions = vec![make_healthy_region(0)];
        let signals = make_default_signals(1, 1);
        // Spawn at elder age (60+) so MORTALITY_ELDER (0.05) * eco_stress (1.0)
        // = 0.05 per agent per tick -- guarantees deaths in 500 agents.
        for _ in 0..500 {
            pool.spawn(0, 0, Occupation::Farmer, 65, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        let mut seed = [0u8; 32];
        seed[0] = 42;
        let mut percentiles = vec![0.0f32; pool.capacity()];
        let events = tick_agents(&mut pool, &regions, &signals, seed, 0, &mut percentiles);
        assert!(pool.alive_count() < 500);
        assert!(pool.alive_count() > 0);
        // Should have death events
        assert!(events.iter().any(|e| e.event_type == 0));
    }

    #[test]
    fn test_tick_deterministic() {
        let regions = vec![make_healthy_region(0), make_healthy_region(1)];
        let signals = make_default_signals(2, 2);
        let mut seed = [0u8; 32];
        seed[0] = 99;
        let mut pool_a = AgentPool::new(0);
        let mut pool_b = AgentPool::new(0);
        for _ in 0..50 {
            pool_a.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(0, 0, Occupation::Farmer, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..50 {
            pool_a.spawn(1, 1, Occupation::Soldier, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(1, 1, Occupation::Soldier, 0, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        let mut pa: Vec<f32> = Vec::new();
        let mut pb: Vec<f32> = Vec::new();
        for turn in 0..10 {
            if pa.len() < pool_a.capacity() { pa.resize(pool_a.capacity(), 0.0); }
            if pb.len() < pool_b.capacity() { pb.resize(pool_b.capacity(), 0.0); }
            tick_agents(&mut pool_a, &regions, &signals, seed, turn, &mut pa);
            tick_agents(&mut pool_b, &regions, &signals, seed, turn, &mut pb);
        }
        assert_eq!(pool_a.alive_count(), pool_b.alive_count());
    }

    #[test]
    fn test_full_tick_deterministic() {
        // Two pools with identical setup, same seed/signals -> identical results
        let mut regions = vec![make_healthy_region(0), make_healthy_region(1)];
        regions[0].adjacency_mask = 0b10; // region 0 adjacent to region 1
        regions[1].adjacency_mask = 0b01; // region 1 adjacent to region 0
        let signals = make_default_signals(2, 2);
        let mut seed = [0u8; 32];
        seed[0] = 77;

        let mut pool_a = AgentPool::new(0);
        let mut pool_b = AgentPool::new(0);

        // Mix of occupations, civs, ages
        for _ in 0..30 {
            pool_a.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..20 {
            pool_a.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(0, 0, Occupation::Soldier, 30, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..20 {
            pool_a.spawn(1, 1, Occupation::Merchant, 22, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(1, 1, Occupation::Merchant, 22, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }
        for _ in 0..30 {
            pool_a.spawn(1, 1, Occupation::Scholar, 40, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            pool_b.spawn(1, 1, Occupation::Scholar, 40, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }

        let mut events_a_total = 0;
        let mut events_b_total = 0;
        let mut pa: Vec<f32> = Vec::new();
        let mut pb: Vec<f32> = Vec::new();
        for turn in 0..5 {
            if pa.len() < pool_a.capacity() { pa.resize(pool_a.capacity(), 0.0); }
            if pb.len() < pool_b.capacity() { pb.resize(pool_b.capacity(), 0.0); }
            let ea = tick_agents(&mut pool_a, &regions, &signals, seed, turn, &mut pa);
            let eb = tick_agents(&mut pool_b, &regions, &signals, seed, turn, &mut pb);
            events_a_total += ea.len();
            events_b_total += eb.len();
        }

        assert_eq!(pool_a.alive_count(), pool_b.alive_count());
        assert_eq!(events_a_total, events_b_total);

        // Verify satisfaction arrays are identical
        for slot in 0..pool_a.capacity() {
            if pool_a.is_alive(slot) {
                assert!(
                    (pool_a.satisfaction(slot) - pool_b.satisfaction(slot)).abs() < 1e-6,
                    "satisfaction mismatch at slot {}",
                    slot
                );
            }
        }
    }

    #[test]
    fn test_full_tick_produces_death_events() {
        // 500 elder agents -> tick produces death events (event_type=0)
        let mut pool = AgentPool::new(0);
        let regions = vec![make_healthy_region(0)];
        let signals = make_default_signals(1, 1);

        for _ in 0..500 {
            pool.spawn(0, 0, Occupation::Farmer, 65, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }

        let mut seed = [0u8; 32];
        seed[0] = 55;
        let mut percentiles = vec![0.0f32; pool.capacity()];
        let events = tick_agents(&mut pool, &regions, &signals, seed, 0, &mut percentiles);

        let death_events: Vec<_> = events.iter().filter(|e| e.event_type == 0).collect();
        assert!(
            !death_events.is_empty(),
            "expected at least one death event from 500 elders"
        );

        // Verify death count matches population reduction
        let deaths = death_events.len();
        assert_eq!(pool.alive_count(), 500 - deaths);

        // Verify all death events have correct fields
        for e in &death_events {
            assert_eq!(e.event_type, 0);
            assert_eq!(e.region, 0);
            assert_eq!(e.target_region, 0);
            assert_eq!(e.civ_affinity, 0);
            assert_eq!(e.turn, 0);
        }
    }

    #[test]
    fn test_skill_growth_happens() {
        use crate::agent::SKILL_GROWTH_PER_TURN;
        let mut pool = AgentPool::new(0);
        let regions = vec![make_healthy_region(0)];
        let signals = make_default_signals(1, 1);

        let slot = pool.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let initial_skill = pool.skill(slot, 1); // Soldier = occ 1
        assert!(initial_skill.abs() < 0.01);

        let mut seed = [0u8; 32];
        seed[0] = 1;
        let mut percentiles = vec![0.0f32; pool.capacity()];
        tick_agents(&mut pool, &regions, &signals, seed, 0, &mut percentiles);

        // After one tick, soldier skill should have grown (if agent survived)
        if pool.is_alive(slot) {
            assert!(
                (pool.skill(slot, 1) - SKILL_GROWTH_PER_TURN).abs() < 0.01,
                "expected skill growth after tick"
            );
        }
    }

    #[test]
    fn test_satisfaction_is_updated() {
        let mut pool = AgentPool::new(0);
        let regions = vec![make_healthy_region(0)];
        let signals = make_default_signals(1, 1);

        for _ in 0..10 {
            pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        }

        let mut seed = [0u8; 32];
        seed[0] = 3;
        let mut percentiles = vec![0.0f32; pool.capacity()];
        tick_agents(&mut pool, &regions, &signals, seed, 0, &mut percentiles);

        // After tick, satisfaction should differ from default 0.5
        // (healthy region with good soil/water should give decent satisfaction)
        let mut any_changed = false;
        for slot in 0..pool.capacity() {
            if pool.is_alive(slot) {
                let sat = pool.satisfaction(slot);
                if (sat - 0.5).abs() > 0.01 {
                    any_changed = true;
                    break;
                }
            }
        }
        assert!(any_changed, "satisfaction should be updated from default 0.5");
    }

    #[test]
    fn test_satisfaction_parallel_matches_sequential() {
        let mut regions = vec![
            make_healthy_region(0),
            make_healthy_region(1),
            make_healthy_region(2),
        ];
        regions[0].adjacency_mask = 0b110;
        regions[1].adjacency_mask = 0b101;
        regions[2].adjacency_mask = 0b011;
        regions[0].controller_civ = 0;
        regions[1].controller_civ = 1;
        regions[2].controller_civ = 0;

        let signals = make_default_signals(2, 3);

        let mut pool_a = AgentPool::new(0);
        let mut pool_b = AgentPool::new(0);
        let occupations = [
            Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
            Occupation::Scholar, Occupation::Priest,
        ];
        for r in 0..3u16 {
            for j in 0..100 {
                let occ = occupations[j % 5];
                let age = (j % 60) as u16;
                let civ = (r % 2) as u8;
                pool_a.spawn(r, civ, occ, age, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
                pool_b.spawn(r, civ, occ, age, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
            }
        }

        let cap_a = pool_a.capacity();
        let cap_b = pool_b.capacity();
        let wealth_pcts_a = vec![0.5f32; cap_a];
        let wealth_pcts_b = vec![0.5f32; cap_b];
        update_satisfaction(&mut pool_a, &regions, &signals, &wealth_pcts_a);
        update_satisfaction(&mut pool_b, &regions, &signals, &wealth_pcts_b);

        // Verify computation actually happened (not still at default 0.5)
        let any_changed = (0..pool_a.capacity())
            .filter(|&s| pool_a.is_alive(s))
            .any(|s| (pool_a.satisfaction(s) - 0.5).abs() > 0.01);
        assert!(any_changed, "satisfaction should differ from default 0.5 after update");

        // Verify all satisfaction values match between the two pools
        for slot in 0..pool_a.capacity() {
            if pool_a.is_alive(slot) {
                let diff = (pool_a.satisfaction(slot) - pool_b.satisfaction(slot)).abs();
                assert!(
                    diff < 1e-6,
                    "satisfaction mismatch at slot {}: {} vs {}",
                    slot,
                    pool_a.satisfaction(slot),
                    pool_b.satisfaction(slot),
                );
            }
        }
    }

    #[test]
    fn test_birth_parent_id_and_personality_inheritance() {
        use crate::agent::PARENT_NONE;

        let mut pool = AgentPool::new(8);
        let parent_slot = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 25,
            0.8, -0.5, 0.3,
            0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.parent_id(parent_slot), PARENT_NONE);

        let parent_agent_id = pool.id(parent_slot);
        assert_ne!(parent_agent_id, PARENT_NONE);
    }
}

// ---------------------------------------------------------------------------
// M41 tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod m41_tests {
    use super::*;
    use crate::agent::{self, STARTING_WEALTH, BASE_FARMER_INCOME,
        SOLDIER_INCOME, AT_WAR_BONUS, CONQUEST_BONUS,
        WEALTH_DECAY, MAX_WEALTH};
    use crate::region::RegionState;
    use crate::signals::{CivSignals, TickSignals};

    fn make_test_signals(at_war: bool, conquered: bool, gini: f32) -> TickSignals {
        TickSignals {
            civs: vec![CivSignals {
                civ_id: 0,
                stability: 50,
                is_at_war: at_war,
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
                gini_coefficient: gini,
                conquered_this_turn: conquered,
                priest_tithe_share: 0.0,
                cultural_drift_multiplier: 1.0,
                religion_intensity_multiplier: 1.0,
            }],
            contested_regions: vec![false],
        }
    }

    fn make_region_organic(yield_val: f32) -> RegionState {
        let mut r = RegionState::new(0);
        r.resource_types = [0, 255, 255]; // GRAIN
        r.resource_yields = [yield_val, 0.0, 0.0];
        r.soil = 0.5;
        r.water = 0.5;
        r.controller_values = [0, 1, 2];
        r.majority_belief = 0xFF;
        r
    }

    #[test]
    fn test_farmer_organic_wealth_accumulates() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let initial = pool.wealth[slot];
        assert!((initial - STARTING_WEALTH).abs() < 0.001);

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        // M42: farmer_income_modifier defaults to 1.0 in RegionState::new()
        let expected_income = BASE_FARMER_INCOME * 1.0 * 0.8;
        let after_income = initial + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001,
            "Got {}, expected {}", pool.wealth[slot], expected);
    }

    #[test]
    fn test_farmer_with_income_modifier() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let mut region = make_region_organic(0.8);
        region.farmer_income_modifier = 2.5; // M42: extractive/high-value modifier
        let regions = vec![region];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = BASE_FARMER_INCOME * 2.5 * 0.8;
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001);
    }

    #[test]
    fn test_soldier_war_bonus() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Soldier, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_organic(0.8)];
        let signals_peace = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals_peace, &mut percentiles);
        let wealth_peace = pool.wealth[slot];

        pool.wealth[slot] = STARTING_WEALTH;
        let signals_war = make_test_signals(true, false, 0.0);
        wealth_tick(&mut pool, &regions, &signals_war, &mut percentiles);
        let wealth_war = pool.wealth[slot];

        assert!(wealth_war > wealth_peace,
            "War income ({wealth_war}) should exceed peace income ({wealth_peace})");
    }

    #[test]
    fn test_soldier_conquest_bonus() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Soldier, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(true, true, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = SOLDIER_INCOME * (1.0 + AT_WAR_BONUS) + CONQUEST_BONUS;
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.01,
            "Got {}, expected {}", pool.wealth[slot], expected);
    }

    #[test]
    fn test_merchant_trade_income() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Merchant, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        let mut region = make_region_organic(0.8);
        region.merchant_trade_income = 0.35; // M42: from Python goods economy
        let regions = vec![region];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        let expected_income = 0.35; // merchant_trade_income directly
        let after_income = STARTING_WEALTH + expected_income;
        let expected = after_income * (1.0 - WEALTH_DECAY);
        assert!((pool.wealth[slot] - expected).abs() < 0.001);
    }

    #[test]
    fn test_wealth_clamped_to_max() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        pool.wealth[slot] = MAX_WEALTH + 10.0;

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.0);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        assert!(pool.wealth[slot] <= MAX_WEALTH,
            "Wealth {} should be clamped to {}", pool.wealth[slot], MAX_WEALTH);
    }

    #[test]
    fn test_percentile_ranking_three_agents() {
        let mut pool = AgentPool::new(4);
        let s0 = pool.spawn(0, 0, agent::Occupation::Farmer, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let s1 = pool.spawn(0, 0, agent::Occupation::Merchant, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);
        let s2 = pool.spawn(0, 0, agent::Occupation::Scholar, 20,
            0.5, 0.5, 0.5, 0, 1, 2, 0xFF);

        // Set wealth with large enough gaps that accumulation won't change ordering
        pool.wealth[s0] = 1.0;
        pool.wealth[s1] = 50.0;
        pool.wealth[s2] = 99.0;

        let regions = vec![make_region_organic(0.8)];
        let signals = make_test_signals(false, false, 0.5);
        let mut percentiles = vec![0.0f32; pool.capacity()];

        wealth_tick(&mut pool, &regions, &signals, &mut percentiles);

        // After accumulation+decay, relative ordering preserved with large gaps
        assert!((percentiles[s0] - 0.0).abs() < 0.001, "Poorest should be 0.0");
        assert!((percentiles[s1] - 0.5).abs() < 0.001, "Middle should be 0.5");
        assert!((percentiles[s2] - 1.0).abs() < 0.001, "Richest should be 1.0");
    }
}
