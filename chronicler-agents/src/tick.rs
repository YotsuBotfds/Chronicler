//! Full tick orchestration: skill growth -> satisfaction -> decisions -> demographics.

use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;

use crate::agent::{OCCUPATION_COUNT, SKILL_NEWBORN, SKILL_RESET_ON_SWITCH};
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
) -> Vec<AgentEvent> {
    let num_regions = regions.len();
    let mut events: Vec<AgentEvent> = Vec::new();

    // -----------------------------------------------------------------------
    // 0. Skill growth — iterate all alive agents
    // -----------------------------------------------------------------------
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            pool.grow_skill(slot);
        }
    }

    // -----------------------------------------------------------------------
    // 1. Update satisfaction
    // -----------------------------------------------------------------------
    update_satisfaction(pool, regions, signals);

    // -----------------------------------------------------------------------
    // 2. Pre-compute region stats for decisions
    // -----------------------------------------------------------------------
    let stats = compute_region_stats(pool, regions);

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
                evaluate_region_decisions(
                    pool_ref,
                    slots,
                    &regions[region_id],
                    stats_ref,
                    region_id,
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
                rng.set_stream(region_id as u64 * 1000 + turn as u64);
                tick_region_demographics(
                    pool_ref,
                    slots,
                    &regions[region_id],
                    signals,
                    region_id,
                    &mut rng,
                )
            })
            .collect()
    };

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
            );
            pool.set_loyalty(new_slot, birth.parent_loyalty);
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
        }
    }

    // Decrement displacement turns for all alive agents
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) && pool.displacement_turns(slot) > 0 {
            pool.set_displacement_turns(slot, pool.displacement_turns(slot) - 1);
        }
    }

    events
}

// ---------------------------------------------------------------------------
// Satisfaction update
// ---------------------------------------------------------------------------

fn update_satisfaction(pool: &mut AgentPool, regions: &[RegionState], signals: &TickSignals) {
    // Pre-compute region stats for demand/supply ratio
    let stats = compute_region_stats(pool, regions);

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) {
            continue;
        }

        let r = pool.region(slot) as usize;
        if r >= regions.len() {
            continue;
        }

        let region = &regions[r];
        let occ = pool.occupation(slot);
        let civ = pool.civ_affinity(slot) as usize;

        // Look up civ signals (default to stable peacetime if civ not in signals)
        let civ_sig = signals
            .civs
            .iter()
            .find(|c| c.civ_id as usize == civ);

        let civ_stability = civ_sig.map_or(50, |c| c.stability);
        let civ_at_war = civ_sig.map_or(false, |c| c.is_at_war);
        let region_contested = if r < signals.contested_regions.len() {
            signals.contested_regions[r]
        } else {
            false
        };

        // Demand/supply ratio for this agent's occupation
        let occ_idx = occ as usize;
        let supply = stats.occupation_supply[r][occ_idx] as f32;
        let demand = stats.occupation_demand[r][occ_idx];
        let ds_ratio = if supply > 0.0 {
            (demand - supply) / supply
        } else {
            0.0
        };

        // Pop over capacity
        let pop = stats.occupation_supply[r].iter().sum::<usize>() as f32;
        let cap = region.carrying_capacity as f32;
        let pop_over_cap = if cap > 0.0 { pop / cap } else { 1.0 };

        // Occupation matches dominant faction?
        let occ_matches = match civ_sig {
            Some(cs) => match cs.dominant_faction {
                0 => occ == 1, // military -> Soldier
                1 => occ == 2, // merchant -> Merchant
                2 => occ == 3, // cultural -> Scholar
                _ => false,
            },
            None => false,
        };

        let is_displaced = pool.displacement_turns(slot) > 0;

        // Faction influence for this agent's occupation
        let faction_influence = match civ_sig {
            Some(cs) => match occ {
                1 => cs.faction_military,
                2 => cs.faction_merchant,
                3 => cs.faction_cultural,
                _ => 0.0,
            },
            None => 0.0,
        };

        let sat = satisfaction::compute_satisfaction(
            occ,
            region.soil,
            region.water,
            civ_stability,
            ds_ratio,
            pop_over_cap,
            civ_at_war,
            region_contested,
            occ_matches,
            is_displaced,
            region.trade_route_count,
            faction_influence,
        );

        pool.set_satisfaction(slot, sat);
    }
}

// ---------------------------------------------------------------------------
// Demographics (parallel per-region)
// ---------------------------------------------------------------------------

struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
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
) -> DemographicsPending {
    let mut pending = DemographicsPending {
        deaths: Vec::new(),
        aged: Vec::new(),
        births: Vec::new(),
    };

    let eco_stress = demographics::ecological_stress(region);

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

        let mort_rate = demographics::mortality_rate(age, eco_stress, is_soldier_at_war);

        if rng.gen::<f32>() < mort_rate {
            pending.deaths.push((slot, region_id as u16));
        } else {
            pending.aged.push(slot);

            // Fertility check (only for survivors)
            let fert_rate = demographics::fertility_rate(age, sat, occ, region.soil);
            if fert_rate > 0.0 && rng.gen::<f32>() < fert_rate {
                pending.births.push(BirthInfo {
                    region: region_id as u16,
                    civ: pool.civ_affinity(slot),
                    parent_loyalty: pool.loyalty(slot),
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
            pool.spawn(0, 0, Occupation::Farmer, 65);
        }
        let mut seed = [0u8; 32];
        seed[0] = 42;
        let events = tick_agents(&mut pool, &regions, &signals, seed, 0);
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
            pool_a.spawn(0, 0, Occupation::Farmer, 0);
            pool_b.spawn(0, 0, Occupation::Farmer, 0);
        }
        for _ in 0..50 {
            pool_a.spawn(1, 1, Occupation::Soldier, 0);
            pool_b.spawn(1, 1, Occupation::Soldier, 0);
        }
        for turn in 0..10 {
            tick_agents(&mut pool_a, &regions, &signals, seed, turn);
            tick_agents(&mut pool_b, &regions, &signals, seed, turn);
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
            pool_a.spawn(0, 0, Occupation::Farmer, 25);
            pool_b.spawn(0, 0, Occupation::Farmer, 25);
        }
        for _ in 0..20 {
            pool_a.spawn(0, 0, Occupation::Soldier, 30);
            pool_b.spawn(0, 0, Occupation::Soldier, 30);
        }
        for _ in 0..20 {
            pool_a.spawn(1, 1, Occupation::Merchant, 22);
            pool_b.spawn(1, 1, Occupation::Merchant, 22);
        }
        for _ in 0..30 {
            pool_a.spawn(1, 1, Occupation::Scholar, 40);
            pool_b.spawn(1, 1, Occupation::Scholar, 40);
        }

        let mut events_a_total = 0;
        let mut events_b_total = 0;
        for turn in 0..5 {
            let ea = tick_agents(&mut pool_a, &regions, &signals, seed, turn);
            let eb = tick_agents(&mut pool_b, &regions, &signals, seed, turn);
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
            pool.spawn(0, 0, Occupation::Farmer, 65);
        }

        let mut seed = [0u8; 32];
        seed[0] = 55;
        let events = tick_agents(&mut pool, &regions, &signals, seed, 0);

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

        let slot = pool.spawn(0, 0, Occupation::Soldier, 25);
        let initial_skill = pool.skill(slot, 1); // Soldier = occ 1
        assert!(initial_skill.abs() < 0.01);

        let mut seed = [0u8; 32];
        seed[0] = 1;
        tick_agents(&mut pool, &regions, &signals, seed, 0);

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
            pool.spawn(0, 0, Occupation::Farmer, 25);
        }

        let mut seed = [0u8; 32];
        seed[0] = 3;
        tick_agents(&mut pool, &regions, &signals, seed, 0);

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
}
