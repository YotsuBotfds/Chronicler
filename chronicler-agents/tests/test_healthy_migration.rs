//! Healthy-world migration drivers across ticks: frontier settlement fills an
//! under-filled region of the realm and stops, without moving anyone back.

use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::migration_drivers::{MigrationDriverStats, TERM_FRONTIER};
use chronicler_agents::spatial::SpatialDiagnostics;
use chronicler_agents::{tick_agents, AgentPool, Occupation, RegionState};

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

/// Region 0 at capacity (40 farmers, capacity 40), region 1 under-filled
/// (8 farmers, capacity 80); one realm, fed, identical grain land (a year's
/// harvest per farmer 2.5 x 0.95 x 0.6 x 0.6 = 0.86).
fn frontier_world(second_ruler: u8) -> (AgentPool, Vec<RegionState>) {
    let mut pool = AgentPool::new(64);
    let mut regions: Vec<RegionState> = (0..2)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.controller_civ = 0;
            r.food_sufficiency = 1.2;
            r.soil = 0.6;
            r.water = 0.6;
            r.resource_types[0] = 0;
            r.resource_base_yield[0] = 2.5;
            // One faith with a temple keeps the spiritual need met, so no
            // deprivation push muddies the test.
            r.majority_belief = 0;
            r.has_temple = true;
            r
        })
        .collect();
    regions[0].carrying_capacity = 40;
    regions[1].carrying_capacity = 80;
    regions[1].controller_civ = second_ruler;
    regions[0].adjacency = vec![1];
    regions[1].adjacency = vec![0];
    for i in 0..40u16 {
        pool.spawn(0, 0, Occupation::Farmer, 21 + i % 40, 0.0, 0.0, 0.0, 0, 1, 2, 0);
    }
    for i in 0..8u16 {
        pool.spawn(1, 0, Occupation::Farmer, 25 + i, 0.0, 0.0, 0.0, 0, 1, 2, 0);
    }
    (pool, regions)
}

fn sync_populations(pool: &AgentPool, regions: &mut [RegionState]) {
    for region in regions.iter_mut() {
        region.population = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s) && pool.regions[s] == region.region_id)
            .count() as u16;
    }
}

/// Run `turns` ticks; returns per-turn (moves 0->1, moves 1->0), the
/// migration budget summed over the run, and the final pool.
fn run(second_ruler: u8, turns: u32) -> (Vec<(usize, usize)>, MigrationDriverStats, AgentPool) {
    let (mut pool, mut regions) = frontier_world(second_ruler);
    let signals = peaceful_signals(2);
    let mut seed = [0u8; 32];
    seed[0] = 11;
    let mut percentiles: Vec<f32> = Vec::new();
    let mut flows = Vec::new();
    let mut budget = MigrationDriverStats::default();
    for turn in 0..turns {
        sync_populations(&pool, &mut regions);
        percentiles.resize(pool.capacity().max(percentiles.len()), 0.0);
        let (events, _, _, _, household, _, _) = tick_agents(
            &mut pool, &regions, &signals, seed, turn, &mut percentiles,
            &mut Vec::new(), &[], &mut SpatialDiagnostics::default(), &[], None,
        );
        let out = events.iter().filter(|e| e.event_type == 2 && e.region == 0).count();
        let back = events.iter().filter(|e| e.event_type == 2 && e.region == 1).count();
        flows.push((out, back));
        budget.merge(&household.migration_drivers);
    }
    (flows, budget, pool)
}

fn in_region(pool: &AgentPool, region: u16) -> usize {
    (0..pool.capacity()).filter(|&s| pool.is_alive(s) && pool.regions[s] == region).count()
}

#[test]
fn frontier_settlement_fills_the_emptier_region_and_stops() {
    let turns = 40;
    let (flows, budget, pool) = run(0, turns);
    let settled: usize = flows.iter().map(|f| f.0).sum();
    let returned: usize = flows.iter().map(|f| f.1).sum();
    assert!(settled >= 8, "expected a settlement wave, got {settled} moves ({flows:?})");
    assert_eq!(returned, 0, "no one moves back: {flows:?}");
    // Every decision was a frontier move (household followers come along).
    assert!(budget.decided > 0);
    assert!((budget.share[TERM_FRONTIER] - budget.decided as f64).abs() < 1e-6, "{budget:?}");
    // The wave stops once home falls below the crowding gate.
    let late: usize = flows[turns as usize - 10..].iter().map(|f| f.0).sum();
    assert_eq!(late, 0, "settlement should stop: {flows:?}");
    let ratio0 = in_region(&pool, 0) as f32 / 40.0;
    let ratio1 = in_region(&pool, 1) as f32 / 80.0;
    assert!(ratio0 - ratio1 < 0.6, "gap should close: {ratio0:.2} vs {ratio1:.2}");
}

#[test]
fn frontier_settlement_does_not_cross_into_another_realm() {
    let (internal, internal_budget, _) = run(0, 20);
    let (foreign, foreign_budget, _) = run(1, 20);
    let internal_out: usize = internal.iter().map(|f| f.0).sum();
    let foreign_out: usize = foreign.iter().map(|f| f.0).sum();
    assert!(internal_budget.share[TERM_FRONTIER] > 0.0);
    assert_eq!(foreign_budget.share[TERM_FRONTIER], 0.0);
    assert_eq!(foreign_budget.open[0], 0, "the gate never opens toward a foreign region");
    // What still crosses is the overcrowding opportunity every agent had before.
    assert!(foreign_out < internal_out, "{foreign_out} vs {internal_out}");
}

#[test]
fn frontier_settlement_is_deterministic() {
    let (a, budget_a, pa) = run(0, 25);
    let (b, budget_b, pb) = run(0, 25);
    assert_eq!(a, b);
    assert_eq!(budget_a.share, budget_b.share);
    let regions_a: Vec<u16> = (0..pa.capacity()).filter(|&s| pa.is_alive(s)).map(|s| pa.regions[s]).collect();
    let regions_b: Vec<u16> = (0..pb.capacity()).filter(|&s| pb.is_alive(s)).map(|s| pb.regions[s]).collect();
    assert_eq!(regions_a, regions_b);
}

/// Two half-full regions of one realm (no frontier gradient); region 1 holds
/// settled emigrants from region 0. Their kin in region 0 follow them, and
/// nobody is pulled back.
#[test]
fn chain_migration_follows_settled_emigrants_and_stays() {
    use chronicler_agents::migration_drivers::TERM_CHAIN;
    use chronicler_agents::relationships::BondType;
    let (_, mut regions) = frontier_world(0);
    regions[0].carrying_capacity = 60;
    regions[1].carrying_capacity = 60;
    let mut pool = AgentPool::new(64);
    let mut stay = Vec::new();
    let mut emigrants = Vec::new();
    for i in 0..20u16 {
        stay.push(pool.spawn(0, 0, Occupation::Scholar, 22 + i % 8, 0.0, 0.0, 0.0, 0, 1, 2, 0));
        let e = pool.spawn(1, 0, Occupation::Scholar, 30 + i % 8, 0.0, 0.0, 0.0, 0, 1, 2, 0);
        pool.origin_regions[e] = 0;
        emigrants.push(e);
    }
    // The first eight stay-at-homes each have two kin among the emigrants:
    // more bond strength than the friendships they form at home (formation
    // runs on turn 0, and every 6 turns).
    for k in 0..16 {
        let home = stay[k % 8];
        for (from, to) in [(home, emigrants[k]), (emigrants[k], home)] {
            let i = pool.rel_count[from] as usize;
            pool.rel_target_ids[from][i] = pool.ids[to];
            pool.rel_sentiments[from][i] = 80;
            pool.rel_bond_types[from][i] = BondType::Kin as u8;
            pool.rel_count[from] += 1;
        }
    }
    let kin_ids: Vec<u32> = stay[..8].iter().map(|&s| pool.ids[s]).collect();
    let signals = peaceful_signals(2);
    let mut seed = [0u8; 32];
    seed[0] = 5;
    let mut percentiles: Vec<f32> = Vec::new();
    let mut budget = MigrationDriverStats::default();
    let mut back = 0;
    for turn in 0..20u32 {
        sync_populations(&pool, &mut regions);
        percentiles.resize(pool.capacity().max(percentiles.len()), 0.0);
        let (events, _, _, _, household, _, _) = tick_agents(
            &mut pool, &regions, &signals, seed, turn, &mut percentiles,
            &mut Vec::new(), &[], &mut SpatialDiagnostics::default(), &[], None,
        );
        back += events.iter().filter(|e| e.event_type == 2 && e.region == 1).count();
        budget.merge(&household.migration_drivers);
    }
    let followed = kin_ids
        .iter()
        .filter(|&&id| (0..pool.capacity()).any(|s| pool.is_alive(s) && pool.ids[s] == id && pool.regions[s] == 1))
        .count();
    assert!(followed >= 4, "kin should follow the emigrants: {followed} of 8 ({budget:?})");
    assert!(budget.share[TERM_CHAIN] > 0.0);
    assert_eq!(back, 0, "no one is pulled back");
}
