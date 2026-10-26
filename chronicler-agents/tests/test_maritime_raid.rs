//! Maritime: merchant sea-lane crossing log and `LossReason::Raid`.
//!
//! The route graph carries sea lanes only when Python sends the optional
//! `sea_raid_risk` column (the maritime layer is on). Without it the mobility
//! phase is unchanged; with it every hop across a sea lane is logged and may be
//! seized by raiders with the lane's probability.

use chronicler_agents::merchant::{
    merchant_mobility_phase, merchant_mobility_phase_at, raid_roll, LossReason, MerchantTripStats,
    RouteGraph, ShadowLedger,
};
use chronicler_agents::{AgentPool, Occupation, RegionState};

const TRIP_PHASE_TRANSIT: u8 = 2;

/// A linear 4-region world (0 <-> 1 <-> 2 <-> 3) whose merchant at region 0
/// plans a 3-hop food trip to region 3, the populated region short of food.
fn setup_linear_world() -> (AgentPool, Vec<RegionState>, RouteGraph) {
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let mut regions: Vec<RegionState> = (0..4)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
            r.controller_civ = 0;
            r.population = 20;
            r
        })
        .collect();
    regions[3].food_sufficiency = 0.4;
    for (i, margin) in [0.1, 0.0, 0.0, 0.8].into_iter().enumerate() {
        regions[i].merchant_margin = margin;
        regions[i].merchant_route_margin = margin;
    }
    let graph = RouteGraph::from_edges(
        &[0, 1, 1, 2, 2, 3],
        &[1, 0, 2, 1, 3, 2],
        &[false; 6],
        &[1.0; 6],
        4,
    );
    (pool, regions, graph)
}

/// The linear world with the 1 <-> 2 edge marked as a sea lane at `risk`.
fn sea_graph(risk: f32) -> RouteGraph {
    let (_, _, graph) = setup_linear_world();
    graph.with_sea_lanes(
        &[0, 1, 1, 2, 2, 3],
        &[1, 0, 2, 1, 3, 2],
        &[-1.0, -1.0, risk, risk, -1.0, -1.0],
    )
}

fn run_ticks(
    pool: &mut AgentPool,
    regions: &[RegionState],
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
    turns: u32,
) -> Vec<MerchantTripStats> {
    (1..=turns)
        .map(|turn| merchant_mobility_phase_at(pool, regions, graph, ledger, &[7u8; 32], turn, None))
        .collect()
}

#[test]
fn test_graph_without_sea_lanes_is_unchanged() {
    // No `sea_raid_risk` column: no log, no draws, the trip runs as before.
    let (mut pool, regions, graph) = setup_linear_world();
    let (mut pool2, _, _) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);
    let mut ledger2 = ShadowLedger::new(4);
    let stats = run_ticks(&mut pool, &regions, &graph, &mut ledger, 4);
    for _ in 0..4 {
        merchant_mobility_phase(&mut pool2, &regions, &graph, &mut ledger2, &[7u8; 32], None);
    }
    assert!(graph.sea_lanes.is_empty());
    assert!(stats.iter().all(|s| s.sea_log.is_empty() && s.raided_trips == 0));
    assert_eq!(stats[3].completed_trips, 1);
    assert_eq!(pool.regions, pool2.regions);
    assert_eq!(pool.trip_phase, pool2.trip_phase);
    assert_eq!(ledger.pending_delivery, ledger2.pending_delivery);
}

#[test]
fn test_negative_risks_mark_land_edges() {
    let graph = sea_graph(0.25);
    assert_eq!(graph.sea_lanes.len(), 2);
    assert_eq!(graph.sea_lanes.get(&(1, 2)), Some(&0.25));
    assert_eq!(graph.sea_lanes.get(&(0, 1)), None);
}

#[test]
fn test_safe_sea_lane_logs_crossing_and_delivers() {
    let (mut pool, regions, _) = setup_linear_world();
    let graph = sea_graph(0.0);
    let mut ledger = ShadowLedger::new(4);
    let stats = run_ticks(&mut pool, &regions, &graph, &mut ledger, 4);
    let crossings: Vec<_> = stats.iter().flat_map(|s| s.sea_log.iter()).collect();
    assert_eq!(crossings.len(), 1);
    let c = crossings[0];
    assert_eq!((c.from_region, c.to_region, c.origin_region, c.dest_region), (1, 2, 0, 3));
    assert!(c.qty > 0.0);
    assert_eq!(c.loss, None);
    assert_eq!(stats[3].completed_trips, 1, "an unraided cargo still arrives");
    assert!(ledger.pending_delivery[3].iter().sum::<f32>() > 0.0);
}

#[test]
fn test_raided_cargo_is_seized_and_never_arrives() {
    let (mut pool, regions, _) = setup_linear_world();
    let graph = sea_graph(1.0);
    let mut ledger = ShadowLedger::new(4);
    let stats = run_ticks(&mut pool, &regions, &graph, &mut ledger, 3);
    let raid = &stats[2].sea_log;
    assert_eq!(raid.len(), 1);
    assert_eq!(raid[0].loss, Some(LossReason::Raid));
    assert_eq!(stats[2].raided_trips, 1);
    // Seized: the trip is over, the cargo is off the origin's in-transit book
    // and nothing was delivered anywhere.
    assert_ne!(pool.trip_phase[0], TRIP_PHASE_TRANSIT);
    assert!(ledger.in_transit_out[0].iter().all(|&q| q == 0.0));
    assert!(ledger.pending_delivery.iter().all(|r| r.iter().all(|&q| q == 0.0)));
    assert_eq!(stats.iter().map(|s| s.completed_trips).sum::<u32>(), 0);
    // Like a delivering merchant, the robbed one heads home (the tick sends it
    // there after the knowledge phase) instead of planning from mid-route.
    assert_eq!(pool.trip_home_region[0], 0);
    assert_eq!(pool.regions[0], 1);
    chronicler_agents::merchant::return_delivering_merchants_home(&mut pool, &[7u8; 32]);
    assert_eq!(pool.regions[0], 0);
}

#[test]
fn test_raid_rolls_are_deterministic_and_keyed() {
    let seed = [3u8; 32];
    let a = raid_roll(&seed, 10, 42, 1, 2);
    assert_eq!(a, raid_roll(&seed, 10, 42, 1, 2));
    assert!((0.0..1.0).contains(&a));
    let others = [
        raid_roll(&seed, 11, 42, 1, 2),
        raid_roll(&seed, 10, 43, 1, 2),
        raid_roll(&seed, 10, 42, 2, 1),
    ];
    assert!(others.iter().all(|&x| x != a));
    let run = || {
        let (mut pool, regions, _) = setup_linear_world();
        let graph = sea_graph(0.5);
        let mut ledger = ShadowLedger::new(4);
        let stats = run_ticks(&mut pool, &regions, &graph, &mut ledger, 12);
        (
            stats.iter().map(|s| s.sea_log.clone()).collect::<Vec<_>>(),
            pool.regions.clone(),
            ledger.pending_delivery.clone(),
        )
    };
    assert_eq!(run(), run());
}

#[test]
fn test_sea_log_is_rebuilt_every_tick() {
    // The log is a per-tick output: the tick after a crossing reports none.
    let (mut pool, regions, _) = setup_linear_world();
    let graph = sea_graph(0.0);
    let mut ledger = ShadowLedger::new(4);
    let stats = run_ticks(&mut pool, &regions, &graph, &mut ledger, 4);
    assert_eq!(stats[2].sea_log.len(), 1);
    assert!(stats[3].sea_log.is_empty(), "the turn-3 crossing must not be reported again");
}
