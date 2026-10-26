//! Learning pull (`--scholarship`) across ticks: scholars of the realm move
//! to the region whose seat of learning draws them, the draw stops when
//! `seat_pull` goes back to 0, a fallen seat's scholars cross a border while
//! `seat_flight` is set and stop when it is cleared, and without the columns
//! the tick is unchanged.

use chronicler_agents::migration_drivers::{MigrationDriverStats, TERM_LEARNING};
use chronicler_agents::signals::{CivSignals, TickSignals};
use chronicler_agents::spatial::SpatialDiagnostics;
use chronicler_agents::{tick_agents, AgentPool, Occupation, RegionState};

fn civ(civ_id: u8) -> CivSignals {
    CivSignals {
        civ_id,
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
    }
}

/// Home (region 0, 30 of capacity 60: farmers, merchants, scholars) next to
/// the seat's region (region 1, 20 of capacity 60), both fed, the same land;
/// region 1 ruled by `seat_ruler` (0: one realm).
fn world(seat_ruler: u8) -> (AgentPool, Vec<RegionState>) {
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
    regions[1].controller_civ = seat_ruler;
    regions[0].adjacency = vec![1];
    regions[1].adjacency = vec![0];
    let occupations = [Occupation::Farmer, Occupation::Merchant, Occupation::Scholar];
    for i in 0..30u16 {
        pool.spawn(0, 0, occupations[(i % 3) as usize], 21 + i % 12, 0.0, 0.0, 0.0, 0, 1, 2, 0);
    }
    for i in 0..20u16 {
        pool.spawn(1, seat_ruler, occupations[(i % 3) as usize], 25 + i % 10, 0.0, 0.0, 0.0, 0, 1, 2, 0);
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

/// Per turn: scholars moving 0 -> 1, others moving 0 -> 1, and the budget.
type Run = (Vec<(usize, usize)>, Vec<MigrationDriverStats>);

/// Run `turns` ticks with `seat_pull(turn)` on region 1 and
/// `flight(turn)` on region 0.
fn run(turns: u32, seat_ruler: u8, seat_pull: impl Fn(u32) -> f32, flight: impl Fn(u32) -> bool) -> Run {
    let (mut pool, mut regions) = world(seat_ruler);
    let mut signals = TickSignals { civs: vec![civ(0)], contested_regions: vec![false; 2] };
    if seat_ruler != 0 {
        signals.civs.push(civ(seat_ruler));
    }
    let mut seed = [0u8; 32];
    seed[0] = 29;
    let mut percentiles: Vec<f32> = Vec::new();
    let mut flows = Vec::new();
    let mut budgets = Vec::new();
    for turn in 0..turns {
        sync_populations(&pool, &mut regions);
        regions[1].seat_pull = seat_pull(turn);
        regions[0].seat_flight = flight(turn);
        percentiles.resize(pool.capacity().max(percentiles.len()), 0.0);
        let (events, _, _, _, household, _, _) = tick_agents(
            &mut pool, &regions, &signals, seed, turn, &mut percentiles,
            &mut Vec::new(), &[], &mut SpatialDiagnostics::default(), &[], None,
        );
        let moved = |scholar: bool| {
            events.iter()
                .filter(|e| e.event_type == 2 && e.region == 0 && e.target_region == 1)
                .filter(|e| (e.occupation == Occupation::Scholar as u8) == scholar)
                .count()
        };
        flows.push((moved(true), moved(false)));
        budgets.push(household.migration_drivers.clone());
    }
    (flows, budgets)
}

#[test]
fn a_seat_draws_the_scholars_of_its_realm() {
    let (flows, budgets) = run(12, 0, |_| 1.0, |_| false);
    let drawn: usize = flows.iter().map(|f| f.0).sum();
    let learning: f64 = budgets.iter().map(|b| b.share[TERM_LEARNING]).sum();
    assert!(drawn >= 2, "expected scholars to move to the seat: {flows:?}");
    assert!(learning > 0.0, "learning decisions recorded");
    assert!(budgets.iter().map(|b| b.open[4]).sum::<u32>() > 0);
}

#[test]
fn the_draw_stops_when_seat_pull_returns_to_zero() {
    let (_, budgets) = run(14, 0, |turn| if turn < 6 { 1.0 } else { 0.0 }, |_| false);
    let early: f64 = budgets[..6].iter().map(|b| b.share[TERM_LEARNING]).sum();
    assert!(early > 0.0);
    for b in &budgets[6..] {
        assert_eq!(b.share[TERM_LEARNING], 0.0);
        assert_eq!((b.gate[4], b.open[4]), (0, 0));
    }
}

#[test]
fn a_fallen_seats_scholars_cross_the_border_only_while_in_flight() {
    // The seat stands across the border (another realm): no draw without
    // flight; while home is in flight its scholars go; then it stops.
    let (_, still) = run(8, 1, |_| 1.0, |_| false);
    for b in &still {
        assert_eq!(b.share[TERM_LEARNING], 0.0, "no draw across a border");
        assert_eq!(b.gate[4], 0);
    }
    let (flows, budgets) = run(14, 1, |_| 1.0, |turn| turn < 6);
    let fled: usize = flows[..6].iter().map(|f| f.0).sum();
    assert!(fled >= 1, "scholars in flight cross the border: {flows:?}");
    assert!(budgets[..6].iter().map(|b| b.gate[4]).sum::<u32>() > 0);
    for b in &budgets[6..] {
        assert_eq!(b.share[TERM_LEARNING], 0.0);
        assert_eq!(b.gate[4], 0, "the flight is over");
    }
}

#[test]
fn without_seat_pull_no_learning_term_and_the_run_repeats() {
    let (a, ba) = run(10, 0, |_| 0.0, |_| false);
    let (b, bb) = run(10, 0, |_| 0.0, |_| false);
    assert_eq!(a, b);
    for (x, y) in ba.iter().zip(&bb) {
        assert_eq!(x.share[TERM_LEARNING], 0.0);
        assert_eq!(x.decided, y.decided);
        assert_eq!(x.share, y.share);
    }
    let (c, _) = run(10, 0, |_| 1.0, |_| false);
    let (d, _) = run(10, 0, |_| 1.0, |_| false);
    assert_eq!(c, d, "deterministic with the pull");
}
