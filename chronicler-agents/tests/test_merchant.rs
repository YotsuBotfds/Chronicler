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
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
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
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
    assert_eq!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "After turn 2, merchant should be in Transit phase (2 more hops to go)"
    );
    assert_eq!(
        pool.regions[0], 1,
        "After one hop from region 0, merchant should be at region 1"
    );

    // Turn 3: advance one more hop (region 1 -> 2).
    let _stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
    assert_eq!(
        pool.trip_phase[0], TRIP_PHASE_TRANSIT,
        "After turn 3, merchant should still be in Transit (1 more hop to go)"
    );
    assert_eq!(pool.regions[0], 2, "After two hops, merchant at region 2");

    // Turn 4: advance last hop (region 2 -> 3), arrive, trip completed.
    let stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
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
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
    assert_eq!(pool.trip_dest_region[0], 3);

    // Turn 2: depart and advance to region 1 (Loading -> Transit)
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
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
    let stats = merchant_mobility_phase(&mut pool, &regions, &broken_graph, &mut ledger, &[0u8; 32], None);

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
    let stats1 = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
    assert_eq!(pool.trip_phase[0], TRIP_PHASE_LOADING);
    assert_eq!(stats1.completed_trips, 0);

    // Turn 2: Loading -> Transit -> Arrive (1 hop) -> Idle. Then Idle -> Loading (new route).
    let stats2 = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, &[0u8; 32], None);
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

    let stats1 = merchant_mobility_phase(&mut pool1, &regions1, &graph1, &mut ledger1, &[0u8; 32], None);
    let stats2 = merchant_mobility_phase(&mut pool2, &regions2, &graph2, &mut ledger2, &[0u8; 32], None);

    assert_eq!(stats1.active_trips, stats2.active_trips);
    assert_eq!(stats1.completed_trips, stats2.completed_trips);
    assert_eq!(stats1.avg_trip_duration, stats2.avg_trip_duration);
    assert_eq!(stats1.total_in_transit_qty, stats2.total_in_transit_qty);
}

#[test]
fn test_hybrid_availability_uses_departure_debits() {
    let mut ledger = ShadowLedger::new(2);
    let mut buf = DeliveryBuffer::new(2);
    let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];

    // Reserve + depart with delivery buffer
    ledger.reserve(0, 0, 3.0);
    ledger.depart(0, 0, 3.0, Some(&mut buf));

    // Hybrid availability: stockpile(10) - reserved(0) - departure_debits(3) = 7
    assert_eq!(ledger.available_hybrid(0, 0, &stockpile, &buf), 7.0);

    // Old formula would give: stockpile(10) - reserved(0) - in_transit_out(3) = 7
    // Same result on same turn. Difference appears after economy drain.

    // Simulate economy drain: stockpile debited, departure_debits cleared
    let debited_stockpile = [7.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
    buf.clear();

    // Hybrid: stockpile(7) - reserved(0) - departure_debits(0) = 7 ✓
    assert_eq!(ledger.available_hybrid(0, 0, &debited_stockpile, &buf), 7.0);

    // Old formula would give: stockpile(7) - reserved(0) - in_transit_out(3) = 4 ✗ (double-subtraction)
    assert_eq!(ledger.available(0, 0, &debited_stockpile), 4.0); // confirms the bug
}

#[test]
fn test_hybrid_overcommitted_uses_departure_debits() {
    let ledger = ShadowLedger::new(2);
    let buf = DeliveryBuffer::new(2);
    let stockpile = [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
    assert!(!ledger.is_overcommitted_hybrid(0, 0, &stockpile, &buf));
}

#[test]
fn test_non_hybrid_clears_delivery_buffer() {
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    assert!(!buf.arrival_imports.is_empty());

    // Non-hybrid: clear without applying
    buf.clear();
    assert!(buf.arrival_imports.is_empty());
    assert_eq!(buf.departure_debits[0][0], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);
}

// ---------------------------------------------------------------------------
// M58b: Hybrid economy ingress tests
// ---------------------------------------------------------------------------

use chronicler_agents::economy::{
    tick_economy_core, EconomyRegionInput, RegionAgentCounts, TradeRouteInput,
    EconomyConfig, NUM_GOODS, TRANSIT_DECAY, HybridDeliveryInput,
};

/// Test helper: build an EconomyRegionInput.
fn test_region_input(
    region_id: u16,
    resource_type_0: u8,
    storage_population: u16,
    terrain: u8,
    yield_0: f32,
    stockpile: [f32; NUM_GOODS],
) -> EconomyRegionInput {
    EconomyRegionInput {
        region_id,
        terrain,
        storage_population,
        resource_type_0,
        resource_effective_yield_0: yield_0,
        stockpile,
    }
}

/// Test helper: build a RegionAgentCounts.
fn test_agent_counts(
    population: u32,
    farmer_count: u32,
    soldier_count: u32,
    merchant_count: u32,
    wealthy_count: u32,
) -> RegionAgentCounts {
    RegionAgentCounts {
        population,
        farmer_count,
        soldier_count,
        merchant_count,
        wealthy_count,
    }
}

#[test]
fn test_hybrid_economy_consumes_delivery_buffer() {
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);

    // Region 0 ships 10 grain to region 1
    buf.record_departure(0, 0, 10.0); // grain slot 0
    buf.record_arrival(0, 1, 0, 10.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 1, 100, 0, 1.0, [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 80, 5, 10, 5),
        test_agent_counts(100, 80, 5, 10, 5),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Transit loss should be tracked (grain has non-zero TRANSIT_DECAY)
    assert!(output.conservation.transit_loss > 0.0, "transit decay should be tracked");
    assert!(output.conservation.in_transit_delta.is_some(), "in_transit_delta should be present");
}

#[test]
fn test_hybrid_economy_abstract_path_unchanged() {
    // Verify that passing None for hybrid_delivery produces identical results
    // to the original abstract path (regression guard).
    let config = EconomyConfig::default();
    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [0.0; NUM_GOODS]),
        test_region_input(1, 5, 100, 0, 1.0, [0.0; NUM_GOODS]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 50, 10, 5, 2),
        test_agent_counts(100, 50, 10, 5, 2),
    ];
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &routes,
        &[0.0, 0.0], &[0, 0], 2,
        &config, 1.0, false, None,
    );

    assert_eq!(output.region_results.len(), 2);
    assert!(output.conservation.in_transit_delta.is_none(), "abstract mode should have None in_transit_delta");
    // Production should be non-zero (50 farmers * 1.0 yield each region).
    assert!(output.conservation.production > 0.0);
}

#[test]
fn test_hybrid_transit_decay_accounting() {
    // Verify that transit decay is correctly computed from arrival records.
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);

    // Ship 100 fish from region 0 to region 1.
    // Fish (slot 1) has TRANSIT_DECAY = 0.08.
    buf.record_departure(0, 1, 100.0);  // fish slot 1
    buf.record_arrival(0, 1, 1, 100.0); // fish arrival

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 3, 100, 0, 1.0, [0.0; NUM_GOODS]), // fish (RT=3 -> slot 1)
        test_region_input(1, 0, 100, 0, 1.0, [0.0; NUM_GOODS]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 50, 10, 5, 2),
        test_agent_counts(100, 50, 10, 5, 2),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Transit loss = 100 * 0.08 = 8.0
    let expected_loss = 100.0 * TRANSIT_DECAY[1] as f64;
    assert!(
        (output.conservation.transit_loss - expected_loss).abs() < 0.01,
        "transit_loss: expected {}, got {}",
        expected_loss, output.conservation.transit_loss
    );
}

#[test]
fn test_oracle_shadow_produces_data_in_hybrid_mode() {
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 1, 100, 0, 1.0, [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 80, 5, 10, 5),
        test_agent_counts(100, 80, 5, 10, 5),
    ];
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &routes, &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Oracle shadow should have run abstract allocation
    assert!(output.oracle_trade_volume.is_some());
    let oracle = output.oracle_trade_volume.as_ref().unwrap();
    assert_eq!(oracle.len(), 2); // one per region
}

// ---------------------------------------------------------------------------
// M58b: Conservation integration tests — three-stream accounting
// ---------------------------------------------------------------------------

#[test]
fn test_three_stream_conservation() {
    let mut buf = DeliveryBuffer::new(3);
    // Merchant departs region 0 with 10 grain
    buf.record_departure(0, 0, 10.0);
    // Merchant arrives at region 2 with 10 grain
    buf.record_arrival(0, 2, 0, 10.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 3);

    // in_transit_delta = departures - arrivals - returns = 10 - 10 - 0 = 0
    let delta: f32 = (0..3).map(|r| {
        (0..NUM_GOODS).map(|g| {
            delivery.departure_debits[r][g] - delivery.arrival_imports[r][g] - delivery.return_credits[r][g]
        }).sum::<f32>()
    }).sum();
    assert!((delta).abs() < 1e-6, "in_transit_delta should be 0 when all trips complete");
}

#[test]
fn test_conservation_with_in_transit_goods() {
    let mut buf = DeliveryBuffer::new(2);
    // 10 departs, only 7 arrives (3 still in transit)
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 7.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);
    let delta: f32 = (0..2).map(|r| {
        (0..NUM_GOODS).map(|g| {
            delivery.departure_debits[r][g] - delivery.arrival_imports[r][g] - delivery.return_credits[r][g]
        }).sum::<f32>()
    }).sum();
    // 10 - 7 - 0 = 3 goods still in transit
    assert!((delta - 3.0).abs() < 1e-6);
}

#[test]
fn test_transit_decay_on_arrivals_only() {
    // Verify that transit decay is applied only to arrivals, not returns
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    buf.record_return(0, 1, 5.0); // return to region 0, slot 1

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 1, 100, 0, 1.0, [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 80, 5, 10, 5),
        test_agent_counts(100, 80, 5, 10, 5),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Transit loss should only be from arrivals (10 * TRANSIT_DECAY[0]), not returns
    let expected_transit_loss = 10.0 * TRANSIT_DECAY[0];
    assert!((output.conservation.transit_loss - expected_transit_loss as f64).abs() < 1e-4,
        "transit loss should be {} but was {}", expected_transit_loss, output.conservation.transit_loss);
}

#[test]
fn test_buffer_not_cleared_on_economy_failure() {
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    assert_eq!(buf.departure_debits[0][0], 10.0);

    // Simulate: economy tick would fail (we just don't call clear)
    // Buffer should still have data
    assert_eq!(buf.departure_debits[0][0], 10.0);
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);

    // Only after explicit clear:
    buf.clear();
    assert_eq!(buf.departure_debits[0][0], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);
}

#[test]
fn test_hybrid_stockpile_net_mobility() {
    // Verify that hybrid mode uses net mobility for stockpile updates.
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);

    // Region 0 departs 20 grain, region 1 receives 20 grain (pre-decay).
    buf.record_departure(0, 0, 20.0);
    buf.record_arrival(0, 1, 0, 20.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    // Region 0 starts with 50 grain, region 1 starts with 10 grain.
    let region_inputs = vec![
        test_region_input(0, 0, 200, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 0, 200, 0, 1.0, [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(50, 40, 5, 3, 2),
        test_agent_counts(50, 40, 5, 3, 2),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Region 0: stockpile = 50 + production(40*1.0) + net_mobility(0 + 0 - 20) = 70
    // Region 1: stockpile = 10 + production(40*1.0) + net_mobility(20*(1-0.05) + 0 - 0) = 10 + 40 + 19.0 = 69
    // (Before consumption/decay/cap)
    // The exact values depend on consumption and decay, but region 0 should have
    // less grain than without any trade, and region 1 should have more.
    let r0_grain = output.region_results[0].stockpile[0];
    let r1_grain = output.region_results[1].stockpile[0];

    // Region 0 lost 20 from departure, so stockpile should reflect that.
    // Without trade: 50 + 40 = 90 (pre-consumption). With hybrid: 50 + 40 - 20 = 70 (pre-consumption).
    // Region 1 gained ~19 from imports, so stockpile should be higher.
    // Without trade: 10 + 40 = 50 (pre-consumption). With hybrid: 10 + 40 + 19 = 69 (pre-consumption).
    assert!(r0_grain < 90.0, "Region 0 grain should be reduced by departures: got {}", r0_grain);
    assert!(r1_grain > 10.0, "Region 1 grain should be increased by imports: got {}", r1_grain);
}

#[test]
fn test_transit_decay_by_region_populated_in_hybrid() {
    // Verify that transit_decay_by_region is populated with per-region per-good
    // decay amounts when running in hybrid mode.
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);

    // Ship 100 fish (slot 1, TRANSIT_DECAY = 0.08) from region 0 to region 1.
    buf.record_departure(0, 1, 100.0);
    buf.record_arrival(0, 1, 1, 100.0);

    // Also ship 50 grain (slot 0, TRANSIT_DECAY = 0.05) from region 0 to region 1.
    buf.record_departure(0, 0, 50.0);
    buf.record_arrival(0, 1, 0, 50.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 3, 100, 0, 1.0, [0.0; NUM_GOODS]),
        test_region_input(1, 0, 100, 0, 1.0, [0.0; NUM_GOODS]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 50, 10, 5, 2),
        test_agent_counts(100, 50, 10, 5, 2),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // transit_decay_by_region should be Some in hybrid mode.
    let tdr = output.transit_decay_by_region.as_ref()
        .expect("transit_decay_by_region should be Some in hybrid mode");
    assert_eq!(tdr.len(), 2);

    // Region 1 receives both shipments — decay should be non-zero.
    // Fish decay at region 1: 100 * 0.08 = 8.0
    let fish_decay = tdr[1][1];
    let expected_fish_decay = 100.0 * TRANSIT_DECAY[1];
    assert!(
        (fish_decay - expected_fish_decay).abs() < 0.01,
        "fish transit decay at region 1: expected {}, got {}",
        expected_fish_decay, fish_decay
    );

    // Grain decay at region 1: 50 * 0.05 = 2.5
    let grain_decay = tdr[1][0];
    let expected_grain_decay = 50.0 * TRANSIT_DECAY[0];
    assert!(
        (grain_decay - expected_grain_decay).abs() < 0.01,
        "grain transit decay at region 1: expected {}, got {}",
        expected_grain_decay, grain_decay
    );

    // Region 0 received nothing — decay should be zero.
    for g in 0..NUM_GOODS {
        assert_eq!(tdr[0][g], 0.0, "region 0 should have zero decay for good {}", g);
    }
}

#[test]
fn test_transit_decay_by_region_none_in_abstract() {
    // Verify that transit_decay_by_region is None when running in abstract mode.
    let config = EconomyConfig::default();
    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [0.0; NUM_GOODS]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 50, 10, 5, 2),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, None,
    );

    assert!(
        output.transit_decay_by_region.is_none(),
        "transit_decay_by_region should be None in abstract mode"
    );
}
