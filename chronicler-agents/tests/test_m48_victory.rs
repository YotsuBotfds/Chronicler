//! M48 deferred-backlog: Victory memories are civ-filtered.
//!
//! `war_won_this_turn` is a per-region boolean. Before the fix every soldier in
//! the contested region received a Victory memory, including the losing side.
//! Victory now goes only to soldiers of the civ that holds the region after the
//! turn's decisive battle, never to agents in a region that changed hands.

use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;
use chronicler_agents::{tick_agents, AgentPool, MemoryEventType, Occupation, RegionState, BELIEF_NONE};

fn make_signals(num_civs: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: 55,
                is_at_war: true,
                dominant_faction: 0,
                faction_military: 0.25,
                faction_merchant: 0.25,
                faction_cultural: 0.25,
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
        contested_regions: vec![true],
    }
}

fn make_region(controller: u8) -> RegionState {
    let mut r = RegionState::new(0);
    r.soil = 0.8;
    r.water = 0.7;
    r.carrying_capacity = 200;
    r.controller_civ = controller;
    r
}

/// Spawn `n` soldiers of each civ in region 0; returns (civ, slot) pairs.
fn spawn_soldiers(pool: &mut AgentPool, civs: &[u8], n: usize) -> Vec<(u8, usize)> {
    let mut out = Vec::new();
    for &civ in civs {
        for _ in 0..n {
            let slot = pool.spawn(0, civ, Occupation::Soldier, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE);
            pool.satisfactions[slot] = 0.7;
            pool.loyalties[slot] = 1.0;
            out.push((civ, slot));
        }
    }
    out
}

fn count_type(pool: &AgentPool, slot: usize, event_type: MemoryEventType) -> usize {
    let n = pool.memory_count[slot] as usize;
    pool.memory_event_types[slot][..n]
        .iter()
        .filter(|&&t| t == event_type as u8)
        .count()
}

fn tick(pool: &mut AgentPool, regions: &mut [RegionState], signals: &TickSignals, turn: u32) {
    regions[0].population = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.regions[s] == 0)
        .count() as u16;
    let mut percentiles = vec![0.0; pool.capacity()];
    tick_agents(
        pool, regions, signals, [7u8; 32], turn,
        &mut percentiles, &mut Vec::new(), &[], &mut SpatialDiagnostics::default(),
        &[], None,
    );
}

/// Agents still alive, in region 0 and still soldiers after the tick. Deaths,
/// migration and occupation switches (a farmer-less region pulls soldiers into
/// farming before intents are collected) are seed-dependent.
fn survivors(pool: &AgentPool, soldiers: &[(u8, usize)], civ: u8) -> Vec<usize> {
    soldiers
        .iter()
        .filter(|&&(c, s)| {
            c == civ
                && pool.is_alive(s)
                && pool.regions[s] == 0
                && pool.occupations[s] == Occupation::Soldier as u8
        })
        .map(|&(_, s)| s)
        .collect()
}

#[test]
fn victory_only_for_soldiers_of_the_civ_holding_the_region() {
    let mut pool = AgentPool::new(0);
    let soldiers = spawn_soldiers(&mut pool, &[0, 1], 6);
    let mut regions = vec![make_region(0)];
    regions[0].war_won_this_turn = true; // civ 0 defended the region
    let signals = make_signals(2);
    tick(&mut pool, &mut regions, &signals, 1);

    let winners = survivors(&pool, &soldiers, 0);
    let losers = survivors(&pool, &soldiers, 1);
    assert!(!winners.is_empty() && !losers.is_empty(), "need survivors on both sides");
    for &s in &winners {
        assert_eq!(count_type(&pool, s, MemoryEventType::Victory), 1, "winner slot {s}");
        assert_eq!(count_type(&pool, s, MemoryEventType::Battle), 1);
    }
    for &s in &losers {
        assert_eq!(count_type(&pool, s, MemoryEventType::Victory), 0, "loser slot {s}");
        assert_eq!(count_type(&pool, s, MemoryEventType::Battle), 1, "losers still remember the battle");
    }
}

#[test]
fn no_victory_in_a_region_that_changed_hands() {
    // A conquered region holds the defeated defenders, realigned by Python to
    // the conqueror before the tick; they get Conquest, not Victory.
    let mut pool = AgentPool::new(0);
    let soldiers = spawn_soldiers(&mut pool, &[0], 6);
    let mut regions = vec![make_region(0)];
    regions[0].war_won_this_turn = true;
    regions[0].controller_changed_this_turn = true;
    let signals = make_signals(1);
    tick(&mut pool, &mut regions, &signals, 1);

    let present = survivors(&pool, &soldiers, 0);
    assert!(!present.is_empty());
    for &s in &present {
        assert_eq!(count_type(&pool, s, MemoryEventType::Victory), 0);
        assert_eq!(count_type(&pool, s, MemoryEventType::Conquest), 1);
    }
}

#[test]
fn no_victory_without_a_controlling_civ() {
    let mut pool = AgentPool::new(0);
    let soldiers = spawn_soldiers(&mut pool, &[0], 4);
    let mut regions = vec![make_region(255)];
    regions[0].war_won_this_turn = true;
    let signals = make_signals(1);
    tick(&mut pool, &mut regions, &signals, 1);
    for &s in &survivors(&pool, &soldiers, 0) {
        assert_eq!(count_type(&pool, s, MemoryEventType::Victory), 0);
    }
}

#[test]
fn victory_signal_is_one_shot_across_turns() {
    let mut pool = AgentPool::new(0);
    let soldiers = spawn_soldiers(&mut pool, &[0], 6);
    let mut regions = vec![make_region(0)];
    let signals = make_signals(1);

    regions[0].war_won_this_turn = true;
    tick(&mut pool, &mut regions, &signals, 1);
    let after_win: Vec<usize> = soldiers
        .iter()
        .map(|&(_, s)| count_type(&pool, s, MemoryEventType::Victory))
        .collect();
    assert!(after_win.iter().any(|&n| n == 1), "turn 1 must write Victory");

    // Python clears the transient flag before the next region batch.
    regions[0].war_won_this_turn = false;
    tick(&mut pool, &mut regions, &signals, 2);
    let after_quiet: Vec<usize> = soldiers
        .iter()
        .map(|&(_, s)| if pool.is_alive(s) { count_type(&pool, s, MemoryEventType::Victory) } else { 0 })
        .collect();
    for (i, &(_, s)) in soldiers.iter().enumerate() {
        if pool.is_alive(s) {
            assert_eq!(after_quiet[i], after_win[i], "turn 2 wrote Victory for slot {s}");
        }
    }
}
