//! M58a: Merchant mobility integration tests.
//! Tests multi-turn travel, route disruption unwind, and default stats.

use chronicler_agents::merchant::{
    merchant_mobility_phase, DeliveryBuffer, MerchantTripStats, RouteGraph, ShadowLedger,
};
use chronicler_agents::{AgentPool, Occupation, RegionState};

/// Trip phase constants (mirrored from agent.rs which is crate-private).
const TRIP_PHASE_IDLE: u8 = 0;
const TRIP_PHASE_LOADING: u8 = 1;
const TRIP_PHASE_TRANSIT: u8 = 2;

/// Build a linear 4-region world where region 3 is the most attractive destination.
/// Low margin at region 0 and high margin at region 3 ensures a multi-hop trip.
fn setup_linear_world() -> (AgentPool, Vec<RegionState>, RouteGraph) {
    let mut pool = AgentPool::new(10);
    // Spawn a merchant at region 0
    pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions: Vec<RegionState> = (0..4)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
            r.controller_civ = 0;
            r
        })
        .collect();

    // Region 0: low margin (origin), region 3: high margin (destination).
    // This ensures the route evaluation picks region 3 over closer alternatives.
    regions[0].merchant_margin = 0.1;
    regions[1].merchant_margin = 0.0;
    regions[2].merchant_margin = 0.0;
    regions[3].merchant_margin = 0.8;

    // Linear bidirectional graph: 0 <-> 1 <-> 2 <-> 3
    let graph = RouteGraph::from_edges(
        &[0, 1, 1, 2, 2, 3],
        &[1, 0, 2, 1, 3, 2],
        &[false; 6],
        &[1.0; 6],
        4,
    );

    (pool, regions, graph)
}

#[test]
fn test_multi_turn_travel() {
    let (mut pool, regions, graph) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);

    // Turn 1: merchant evaluates routes, enters Loading with a multi-hop trip to region 3.
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(
        pool.trip_phase[0], TRIP_PHASE_LOADING,
        "After turn 1, merchant should be in Loading phase"
    );
    assert_eq!(
        pool.trip_dest_region[0], 3,
        "Merchant should target region 3 (highest margin sum)"
    );
    assert_eq!(
        pool.trip_path_len[0], 3,
        "Path from 0 to 3 should be 3 hops"
    );

    // Turn 2: Loading -> Transit, advance one hop (region 0 -> 1).
    // The path has 3 hops, so the merchant is still in transit after one advance.
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "After turn 2, merchant should be in Transit phase (2 more hops to go)"
    );
    assert_eq!(
        pool.regions[0], 1,
        "After one hop from region 0, merchant should be at region 1"
    );

    // Turn 3: advance one more hop (region 1 -> 2).
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "After turn 3, merchant should still be in Transit (1 more hop to go)"
    );
    assert_eq!(pool.regions[0], 2, "After two hops, merchant at region 2");

    // Turn 4: advance last hop (region 2 -> 3), arrive, trip completed.
    let stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(stats.completed_trips, 1, "Trip should complete on turn 4");
    // After arrival + reset, the merchant may immediately plan a new route (Loading)
    // or remain Idle if no profitable return route exists. Either is valid.
    assert_ne!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "After arrival, merchant should not remain in Transit"
    );
}

#[test]
fn test_disruption_unwind() {
    let (mut pool, regions, graph) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);

    // Turn 1: plan route (Idle -> Loading to region 3)
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(pool.trip_dest_region[0], 3);

    // Turn 2: depart and advance to region 1 (Loading -> Transit)
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(pool.trip_phase[0], TRIP_PHASE_TRANSIT);
    assert_eq!(pool.regions[0], 1);

    // Turn 3: break the graph — only keep 0 <-> 1, severing the route to region 3.
    let broken_graph = RouteGraph::from_edges(
        &[0, 1],
        &[1, 0],
        &[false; 2],
        &[1.0; 2],
        4,
    );
    let stats = merchant_mobility_phase(&mut pool, &regions, &broken_graph, &mut ledger, &[0u8; 32]);

    // The merchant was at region 1 heading to region 3 via 1->2->3.
    // With edge 1->2 gone, the path is broken. Replan to region 3 also fails (unreachable).
    // So the merchant should be unwound. Note: after unwind, phase f-g in the same turn
    // may immediately plan a new trip to region 0 (the only reachable destination),
    // so the final state may be Loading (new trip) rather than Idle.
    assert_ne!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "Disrupted merchant should not remain in Transit after unwind"
    );
    assert!(
        stats.unwind_count > 0,
        "Stats should record at least one unwind"
    );
    assert!(
        stats.stalled_trip_count > 0,
        "Stats should record at least one stalled trip"
    );
    // The original trip to region 3 should no longer be active
    assert_ne!(
        pool.trip_dest_region[0], 3,
        "Disrupted trip to region 3 should be cleared"
    );
}

#[test]
fn test_agents_off_default_stats() {
    // When no merchant mobility phase runs, default stats should be zero.
    let stats = MerchantTripStats::default();
    assert_eq!(stats.active_trips, 0);
    assert_eq!(stats.completed_trips, 0);
    assert_eq!(stats.unwind_count, 0);
    assert_eq!(stats.stalled_trip_count, 0);
    assert_eq!(stats.disruption_replans, 0);
    assert_eq!(stats.overcommit_count, 0);
    assert!((stats.avg_trip_duration - 0.0).abs() < f32::EPSILON);
    assert!((stats.total_in_transit_qty - 0.0).abs() < f32::EPSILON);
    assert!((stats.route_utilization - 0.0).abs() < f32::EPSILON);
}

#[test]
fn test_full_trip_lifecycle() {
    // Verify a merchant can complete a full 1-hop trip: Idle -> Loading -> Transit+Arrive -> Idle.
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Two-region world: 0 <-> 1 (one hop trip)
    let regions: Vec<RegionState> = (0..2)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.merchant_margin = 0.5;
            r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
            r.controller_civ = 0;
            r
        })
        .collect();
    let graph = RouteGraph::from_edges(
        &[0, 1],
        &[1, 0],
        &[false; 2],
        &[1.0; 2],
        2,
    );
    let mut ledger = ShadowLedger::new(2);

    // Turn 1: Idle -> Loading
    let stats1 = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(pool.trip_phase[0], TRIP_PHASE_LOADING);
    assert_eq!(stats1.completed_trips, 0);

    // Turn 2: Loading -> Transit -> Arrive (1 hop) -> Idle. Then Idle -> Loading (new route).
    let stats2 = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32]);
    assert_eq!(stats2.completed_trips, 1, "Should record one completed trip");
    // After arrival, the merchant immediately evaluates a return route and enters Loading.
    // trip_phase should be Loading (planning the return trip) or Idle (if no route found).
    assert_ne!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "Merchant should not remain in Transit after completing a 1-hop trip"
    );
}

#[test]
fn test_delivery_buffer_records_departure() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_departure(0, 2, 5.0);
    assert_eq!(buf.departure_debits[0][2], 5.0);
    // Cumulative diagnostics
    assert_eq!(buf.diagnostics.total_departures[0][2], 5.0);
}

#[test]
fn test_delivery_buffer_records_arrival() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_arrival(0, 1, 2, 7.5);
    assert_eq!(buf.arrival_imports.len(), 1);
    assert_eq!(buf.arrival_imports[0].source_region, 0);
    assert_eq!(buf.arrival_imports[0].dest_region, 1);
    assert_eq!(buf.arrival_imports[0].good_slot, 2);
    assert_eq!(buf.arrival_imports[0].qty, 7.5);
    assert_eq!(buf.diagnostics.total_arrivals[1][2], 7.5);
}

#[test]
fn test_delivery_buffer_records_return() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_return(0, 3, 4.0);
    assert_eq!(buf.return_credits[0][3], 4.0);
    assert_eq!(buf.diagnostics.total_returns[0][3], 4.0);
}

#[test]
fn test_delivery_buffer_clear_preserves_diagnostics() {
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 5.0);
    buf.record_arrival(0, 1, 0, 5.0);
    buf.record_return(0, 1, 3.0);
    buf.clear();
    // Drainable streams zeroed
    assert_eq!(buf.departure_debits[0][0], 0.0);
    assert!(buf.arrival_imports.is_empty());
    assert_eq!(buf.return_credits[0][1], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 5.0);
    assert_eq!(buf.diagnostics.total_arrivals[1][0], 5.0);
    assert_eq!(buf.diagnostics.total_returns[0][1], 3.0);
}

#[test]
fn test_thread_count_determinism() {
    let (mut pool1, regions1, graph1) = setup_linear_world();
    let (mut pool2, regions2, graph2) = setup_linear_world();
    let mut ledger1 = ShadowLedger::new(4);
    let mut ledger2 = ShadowLedger::new(4);

    let stats1 = merchant_mobility_phase(&mut pool1, &regions1, &graph1, &mut ledger1, &[0u8; 32]);
    let stats2 = merchant_mobility_phase(&mut pool2, &regions2, &graph2, &mut ledger2, &[0u8; 32]);

    assert_eq!(stats1.active_trips, stats2.active_trips);
    assert_eq!(stats1.completed_trips, stats2.completed_trips);
    assert_eq!(stats1.avg_trip_duration, stats2.avg_trip_duration);
    assert_eq!(stats1.total_in_transit_qty, stats2.total_in_transit_qty);
}
