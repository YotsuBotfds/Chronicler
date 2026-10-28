//! Receipt capture is optional, bounded, and absent from every native payload.
use chronicler_agents::merchant::{merchant_mobility_phase_at, DeliveryBuffer, RouteGraph, ShadowLedger};
use chronicler_agents::persist::{decode, encode, schema_of, KIND_AGENT};
use chronicler_agents::transaction_receipts as R;
use chronicler_agents::{AgentPool, AgentSimulator, Occupation, RegionState};

fn setup(risk: Option<f32>) -> (AgentPool, Vec<RegionState>, RouteGraph, ShadowLedger, DeliveryBuffer) {
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let regions = (0..4).map(|i| {
        let mut r = RegionState::new(i);
        r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        r.controller_civ = if i == 3 { 1 } else { 0 };
        r.population = 20;
        r.food_sufficiency = if i == 3 { 0.4 } else { 1.0 };
        r.merchant_margin = if i == 3 { 0.8 } else { 0.0 };
        r.merchant_route_margin = r.merchant_margin;
        r
    }).collect::<Vec<_>>();
    let mut graph = RouteGraph::from_edges(&[0,1,1,2,2,3], &[1,0,2,1,3,2], &[false;6], &[1.0;6], 4);
    if let Some(risk) = risk { graph = graph.with_sea_lanes(&[1,2], &[2,1], &[risk,risk]); }
    graph.receipt_limit = R::DEFAULT_LIMIT;
    let mut buf = DeliveryBuffer::new(4);
    buf.physical_stock = true;
    (pool, regions, graph, ShadowLedger::new(4), buf)
}

#[test]
fn receipt_departure_and_arrival_are_gross_ledger_boundaries() {
    let (mut pool, regions, graph, mut ledger, mut buf) = setup(Some(0.0));
    let mut rows = Vec::new();
    for turn in 10..14 {
        let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], turn, Some(&mut buf));
        let frame = stats.receipts.unwrap();
        assert_eq!(frame.source_turn, turn);
        assert!(frame.mobility_executed && frame.dropped == 0);
        rows.extend(frame.rows);
    }
    let ops = rows.iter().map(|r| r.operation).collect::<Vec<_>>();
    assert_eq!(ops, vec![R::RESERVED,R::ACTIVE,R::DEPARTED,R::ACTIVE,R::SEA_CROSSING,R::ACTIVE,R::ARRIVED]);
    assert!(rows.iter().all(|r| r.merchant_id == pool.ids[0] && r.quantity > 0.0 && r.physical_stock));
    assert!(rows.iter().all(|r| r.origin_controller == 0 && r.dest_controller == 1));
    let quantity = rows[0].quantity;
    assert_eq!(buf.departure_debits[0][0], quantity);
    assert_eq!(buf.arrival_imports.len(), 1);
    assert_eq!(buf.arrival_imports[0].qty, quantity);
    // Recording did not prematurely debit/settle macro stocks.
    assert_eq!(regions[0].stockpile[0], 10.0);
}

#[test]
fn receipt_raid_uses_the_existing_draw_and_seizure_quantity() {
    let (mut pool, regions, graph, mut ledger, mut buf) = setup(Some(1.0));
    let mut loss = Vec::new();
    for turn in 1..=4 {
        let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], turn, Some(&mut buf));
        for row in stats.receipts.unwrap().rows {
            if row.loss_reason != R::NO_LOSS { loss.push(row); }
        }
    }
    assert_eq!(loss.len(), 1);
    assert_eq!(loss[0].operation, R::SEA_CROSSING);
    assert_eq!(loss[0].loss_reason, 1);
    assert_eq!((loss[0].from_region,loss[0].to_region), (1,2));
    assert_eq!(buf.departure_debits[0][0], loss[0].quantity);
    assert!(buf.arrival_imports.is_empty());
    assert!(ledger.in_transit_out.iter().flatten().all(|&q| q == 0.0));
}

#[test]
fn receipt_enabled_and_disabled_have_identical_native_payloads_each_tick() {
    let (mut a, regions, mut graph_a, mut ledger_a, mut buf_a) = setup(Some(0.4));
    let (mut b, _, graph_b, mut ledger_b, mut buf_b) = setup(Some(0.4));
    graph_a.receipt_limit = 0;
    assert_eq!(encode(KIND_AGENT,&graph_a), encode(KIND_AGENT,&graph_b));
    for turn in 1..=16 {
        let stats_a = merchant_mobility_phase_at(&mut a, &regions, &graph_a, &mut ledger_a, &[7;32], turn, Some(&mut buf_a));
        let stats_b = merchant_mobility_phase_at(&mut b, &regions, &graph_b, &mut ledger_b, &[7;32], turn, Some(&mut buf_b));
        assert!(stats_a.receipts.is_none());
        assert!(stats_b.receipts.is_some());
        assert_eq!(encode(KIND_AGENT,&a), encode(KIND_AGENT,&b));
        assert_eq!(encode(KIND_AGENT,&ledger_a), encode(KIND_AGENT,&ledger_b));
        assert_eq!(encode(KIND_AGENT,&buf_a), encode(KIND_AGENT,&buf_b));
        assert_eq!(encode(KIND_AGENT,&stats_a), encode(KIND_AGENT,&stats_b));
    }
}

#[test]
fn receipt_overflow_is_observable_and_does_not_change_simulation() {
    let (mut pool, regions, mut graph, mut ledger, mut buf) = setup(None);
    graph.receipt_limit = 1;
    let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 10, Some(&mut buf));
    let frame = stats.receipts.unwrap();
    assert_eq!(frame.rows.len(), 1);
    assert_eq!(frame.dropped, 1); // reservation observed, final active set truncated
    assert_eq!(pool.trip_phase[0], 1);
    assert!(ledger.reserved[0][0] > 0.0);
    assert_eq!(R::to_batch(Some(&frame)).unwrap().num_rows(), 1);
}

#[test]
fn receipt_departure_reports_revalidated_quantity_and_shadow_provenance() {
    let (mut pool, mut regions, graph, mut ledger, mut buf) = setup(None);
    merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 1, Some(&mut buf));
    regions[0].stockpile[0] = 1.0;
    let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 2, Some(&mut buf));
    let departure = stats.receipts.unwrap().rows.into_iter().find(|r|r.operation == R::DEPARTED).unwrap();
    assert_eq!(departure.quantity, 1.0);
    assert_eq!(buf.departure_debits[0][0], 1.0);
    let (mut pool, regions, graph, mut ledger, mut buf) = setup(None);
    buf.physical_stock = false;
    let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 1, Some(&mut buf));
    assert!(stats.receipts.unwrap().rows.iter().all(|r| !r.physical_stock));
}

#[test]
fn receipt_cancel_and_disruption_return_observe_before_field_reset() {
    let (mut pool, regions, mut graph, mut ledger, mut buf) = setup(None);
    merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 1, Some(&mut buf));
    graph.adj[0].clear();
    let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 2, Some(&mut buf));
    let frame = stats.receipts.unwrap();
    assert_eq!(frame.rows.len(), 1);
    assert_eq!(frame.rows[0].operation, R::CANCELLED);
    assert_eq!((frame.rows[0].origin_region, frame.rows[0].dest_region), (0,3));
    assert!(frame.rows[0].quantity > 0.0);
    let (mut pool, regions, mut graph, mut ledger, mut buf) = setup(None);
    for turn in 1..=2 { merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], turn, Some(&mut buf)); }
    graph.adj[1].clear();
    let stats = merchant_mobility_phase_at(&mut pool, &regions, &graph, &mut ledger, &[7;32], 3, Some(&mut buf));
    let row = stats.receipts.unwrap().rows.into_iter().find(|r|r.operation == R::RETURNED).unwrap();
    assert_eq!(buf.return_credits[0][0], row.quantity);
    assert_eq!((row.from_region, row.to_region), (1,0));
}

#[test]
fn receipt_configuration_and_buffers_are_truly_transient() {
    let mut sim = AgentSimulator::new(4, 7);
    let schema = AgentSimulator::checkpoint_schema();
    let before = encode(KIND_AGENT, &sim);
    sim.configure_transaction_receipts(true, 1).unwrap();
    assert_eq!(before, encode(KIND_AGENT, &sim));
    assert_eq!(schema, AgentSimulator::checkpoint_schema());
    assert!(!schema_of::<AgentSimulator>().contains("transaction_receipts"));
    assert!(!schema_of::<RouteGraph>().contains("receipt_limit"));
    let restored: AgentSimulator = decode(KIND_AGENT,&encode(KIND_AGENT,&sim)).unwrap();
    assert_eq!(before, encode(KIND_AGENT,&restored));
    assert!(sim.configure_transaction_receipts(true, 0).is_err());
    assert!(sim.configure_transaction_receipts(true, R::MAX_LIMIT + 1).is_err());
}
