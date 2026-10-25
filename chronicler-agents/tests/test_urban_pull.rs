//! Urban pull (`--cities`) across ticks: rural people of the realm move to
//! the region whose city draws them, the draw stops when `city_pull` goes
//! back to 0, and without it the tick is unchanged.

use chronicler_agents::migration_drivers::{MigrationDriverStats, TERM_URBAN};
use chronicler_agents::signals::{CivSignals, TickSignals};
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

/// Hinterland (region 0, 30 of capacity 60: farmers, merchants, scholars)
/// next to the city's region (region 1, 20 of capacity 60), one realm, both
/// fed, the same land.
fn world() -> (AgentPool, Vec<RegionState>) {
    let mut pool = AgentPool::new(64);
    let mut regions: Vec<RegionState> = (0..2)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.controller_civ = 0;
            r.carrying_capacity = 60;
            r.food_sufficiency = 1.2;
            r.soil = 0.6;
            r.water = 0.6;
            r.resource_types[0] = 0;
            r.resource_base_yield[0] = 2.5;
            r.resource_yields[0] = 0.9;
            r.majority_belief = 0;
            r.has_temple = true;
            r
        })
        .collect();
    regions[0].adjacency = vec![1];
    regions[1].adjacency = vec![0];
    let occupations = [Occupation::Farmer, Occupation::Merchant, Occupation::Scholar];
    for i in 0..30u16 {
        pool.spawn(0, 0, occupations[(i % 3) as usize], 21 + i % 12, 0.0, 0.0, 0.0, 0, 1, 2, 0);
    }
    for i in 0..20u16 {
        pool.spawn(1, 0, occupations[(i % 3) as usize], 25 + i % 10, 0.0, 0.0, 0.0, 0, 1, 2, 0);
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

/// Run `turns` ticks with `city_pull(turn)` on region 1; per-turn moves
/// (0 -> 1, 1 -> 0) and the migration budget per turn.
fn run(turns: u32, city_pull: impl Fn(u32) -> f32) -> (Vec<(usize, usize)>, Vec<MigrationDriverStats>) {
    let (mut pool, mut regions) = world();
    let signals = peaceful_signals(2);
    let mut seed = [0u8; 32];
    seed[0] = 23;
    let mut percentiles: Vec<f32> = Vec::new();
    let mut flows = Vec::new();
    let mut budgets = Vec::new();
    for turn in 0..turns {
        sync_populations(&pool, &mut regions);
        regions[1].city_pull = city_pull(turn);
        percentiles.resize(pool.capacity().max(percentiles.len()), 0.0);
        let (events, _, _, _, household, _, _) = tick_agents(
            &mut pool, &regions, &signals, seed, turn, &mut percentiles,
            &mut Vec::new(), &[], &mut SpatialDiagnostics::default(), &[], None,
        );
        let out = events.iter().filter(|e| e.event_type == 2 && e.region == 0).count();
        let back = events.iter().filter(|e| e.event_type == 2 && e.region == 1).count();
        flows.push((out, back));
        budgets.push(household.migration_drivers.clone());
    }
    (flows, budgets)
}

#[test]
fn a_city_draws_rural_people_of_its_realm() {
    let (flows, budgets) = run(12, |_| 1.0);
    let drawn: usize = flows.iter().map(|f| f.0).sum();
    let urban: f64 = budgets.iter().map(|b| b.share[TERM_URBAN]).sum();
    assert!(drawn >= 3, "expected rural people to move to the city: {flows:?}");
    assert!(urban > 0.0, "urban decisions recorded");
    assert!(budgets.iter().map(|b| b.open[3]).sum::<u32>() > 0);
}

#[test]
fn the_draw_stops_when_city_pull_returns_to_zero() {
    // The city falls (or the switch is turned off) after turn 5: from then
    // on the region batch carries 0 and no urban decision is made.
    let (_, budgets) = run(14, |turn| if turn < 6 { 1.0 } else { 0.0 });
    let early: f64 = budgets[..6].iter().map(|b| b.share[TERM_URBAN]).sum();
    assert!(early > 0.0);
    for b in &budgets[6..] {
        assert_eq!(b.share[TERM_URBAN], 0.0);
        assert_eq!((b.gate[3], b.open[3]), (0, 0));
    }
}

#[test]
fn without_city_pull_no_urban_term_and_the_run_repeats() {
    let (a, ba) = run(10, |_| 0.0);
    let (b, bb) = run(10, |_| 0.0);
    assert_eq!(a, b);
    for (x, y) in ba.iter().zip(&bb) {
        assert_eq!(x.share[TERM_URBAN], 0.0);
        assert_eq!(x.decided, y.decided);
        assert_eq!(x.share, y.share);
    }
    let (c, _) = run(10, |_| 1.0);
    let (d, _) = run(10, |_| 1.0);
    assert_eq!(c, d, "deterministic with the pull");
}
