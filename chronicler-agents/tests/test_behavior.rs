//! M59b and Sprint 5 migration-behavior integration tests.

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents, BELIEF_NONE};
use chronicler_agents::knowledge::{admit_packet, PacketCandidate, InfoType};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;

fn peaceful_signals(num_regions: usize) -> TickSignals {
    TickSignals {
        civs: vec![CivSignals {
            civ_id: 0,
            stability: 55,
            is_at_war: false,
            dominant_faction: 0,
            faction_military: 0.25,
            faction_merchant: 0.25,
            faction_cultural: 0.25,
            faction_clergy: 0.25,
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
        contested_regions: vec![false; num_regions],
    }
}

fn setup_migration_world() -> (AgentPool, Vec<RegionState>) {
    let mut pool = AgentPool::new(20);
    // Slot 0: the test subject in region 0 with low satisfaction (wants to migrate)
    pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(0, 0.3);
    // Slots 1-2: agents in region 1 with high satisfaction (making region 1 attractive)
    let s1 = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(s1, 0.8);
    let s1b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(s1b, 0.8);
    // Slots 3-4: agents in region 2 with high satisfaction (making region 2 attractive)
    let s2 = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(s2, 0.8);
    let s2b = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(s2b, 0.8);
    let mut regions: Vec<RegionState> = (0..3).map(|i| {
        let mut r = RegionState::new(i);
        r.carrying_capacity = 100;
        r.controller_civ = 0;
        r.food_sufficiency = 1.0;
        r
    }).collect();
    regions[0].adjacency_mask = (1 << 1) | (1 << 2);
    regions[1].adjacency_mask = 1 << 0;
    regions[2].adjacency_mask = 1 << 0;
    (pool, regions)
}

fn sync_region_populations(pool: &AgentPool, regions: &mut [RegionState]) {
    for region in regions.iter_mut() {
        let pop = (0..pool.capacity())
            .filter(|&slot| pool.is_alive(slot) && pool.regions[slot] == region.region_id)
            .count() as u16;
        region.population = pop;
    }
}

#[test]
fn test_threat_penalty_changes_best_target() {
    let (mut pool, regions) = setup_migration_world();
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 200,
        hop_count: 0,
    });

    use chronicler_agents::behavior::{compute_region_stats, evaluate_region_decisions};
    let signals = peaceful_signals(3);
    let stats = compute_region_stats(&pool, &regions, &signals);

    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;
    let id_to_slot = std::collections::HashMap::from([(pool.ids[0], 0usize)]);
    let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
    let (pending, threat_count) = evaluate_region_decisions(
        &pool, &[0], &regions, &regions[0], &stats, 0, &mut rng, &id_to_slot,
    );

    // With a threat on region 1, if the agent migrates it should prefer region 2.
    if !pending.migrations.is_empty() {
        let (_, _, target) = pending.migrations[0];
        assert_eq!(target, 2, "Should migrate to unthreatened region 2, not threatened region 1");
    }
    assert!(threat_count > 0, "Threat penalty should have changed the best target");
}

#[test]
fn test_own_region_threat_not_applied() {
    let (mut pool, _regions) = setup_migration_world();
    pool.regions[0] = 1;
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 255,
        hop_count: 0,
    });

    use chronicler_agents::knowledge::strongest_threat_for_region;
    let strength = strongest_threat_for_region(&pool, 0, 1, 1);
    assert_eq!(strength, 0.0, "Own-region threat should be excluded");
}

#[test]
fn test_non_adjacent_threat_not_applied() {
    let (mut pool, regions) = setup_migration_world();

    use chronicler_agents::behavior::{compute_region_stats, evaluate_region_decisions};
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    let signals = peaceful_signals(3);
    let stats = compute_region_stats(&pool, &regions, &signals);
    let id_to_slot = std::collections::HashMap::from([(pool.ids[0], 0usize)]);

    // Baseline: no threat packets
    let mut rng_base = ChaCha8Rng::from_seed([0u8; 32]);
    let (pending_base, threat_base) = evaluate_region_decisions(
        &pool, &[0], &regions, &regions[0], &stats, 0, &mut rng_base, &id_to_slot,
    );

    // Add a threat for a non-adjacent region (99 is not adjacent to region 0)
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 99,
        source_turn: 5,
        intensity: 255,
        hop_count: 0,
    });

    let mut rng_test = ChaCha8Rng::from_seed([0u8; 32]);
    let (pending_test, threat_test) = evaluate_region_decisions(
        &pool, &[0], &regions, &regions[0], &stats, 0, &mut rng_test, &id_to_slot,
    );

    assert_eq!(threat_test, 0, "Non-adjacent threat must not change migration target");
    assert_eq!(threat_base, threat_test, "Threat counter unchanged");
    assert_eq!(
        pending_base.migrations.len(),
        pending_test.migrations.len(),
        "Same number of migrations",
    );
    if !pending_base.migrations.is_empty() {
        assert_eq!(
            pending_base.migrations[0].2,
            pending_test.migrations[0].2,
            "Migration target must be identical with or without non-adjacent threat",
        );
    }
}

#[test]
fn test_strongest_threat_wins_no_stacking() {
    let (mut pool, _) = setup_migration_world();
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 100,
        hop_count: 2,
    });
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 6,
        intensity: 200,
        hop_count: 0,
    });

    use chronicler_agents::knowledge::strongest_threat_for_region;
    let strength = strongest_threat_for_region(&pool, 0, 1, 0);
    assert!(
        (strength - 200.0 / 255.0).abs() < 0.01,
        "Should use the strongest packet, got {strength}",
    );
}

#[test]
fn test_economy_satisfaction_behavior_chain_can_trigger_migration() {
    let mut pool = AgentPool::new(0);
    let mut regions: Vec<RegionState> = (0..2).map(|i| {
        let mut r = RegionState::new(i);
        r.carrying_capacity = if i == 0 { 40 } else { 80 };
        r.controller_civ = 0;
        r.food_sufficiency = if i == 0 { 0.15 } else { 1.25 };
        r.farmer_income_modifier = if i == 0 { 0.25 } else { 1.5 };
        r
    }).collect();
    regions[0].adjacency_mask = 0b10;
    regions[1].adjacency_mask = 0b01;

    let source_slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, BELIEF_NONE);
    let target_slot = pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, BELIEF_NONE);
    let mut source_ids = vec![pool.ids[source_slot]];
    for _ in 0..17 {
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, BELIEF_NONE);
        source_ids.push(pool.ids[slot]);
    }
    for _ in 0..3 {
        pool.spawn(1, 0, Occupation::Farmer, 25, 0.0, 0.0, 0.0, 0, 0, 0, BELIEF_NONE);
    }

    let signals = peaceful_signals(2);
    let mut seed = [0u8; 32];
    seed[0] = 19;
    let mut percentiles: Vec<f32> = Vec::new();

    for turn in 0..8u32 {
        sync_region_populations(&pool, &mut regions);
        if percentiles.len() < pool.capacity() {
            percentiles.resize(pool.capacity(), 0.0);
        }
        tick_agents(
            &mut pool,
            &regions,
            &signals,
            seed,
            turn,
            &mut percentiles,
            &mut Vec::new(),
            &[],
            &mut SpatialDiagnostics::default(),
            &[],
            None,
        );
        if turn == 0 {
            assert!(
                pool.satisfaction(source_slot) < pool.satisfaction(target_slot),
                "source region should produce lower satisfaction before migration pressure resolves",
            );
        }
    }

    let migrated = source_ids
        .iter()
        .filter(|&&agent_id| {
            (0..pool.capacity()).any(|slot| {
                pool.is_alive(slot) && pool.ids[slot] == agent_id && pool.regions[slot] == 1
            })
        })
        .count();
    assert!(
        migrated > 0,
        "expected at least one low-food, low-income farmer to migrate to the healthier adjacent region",
    );
}
