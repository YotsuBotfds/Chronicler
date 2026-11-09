use super::*;
use arrow::array::{Int8Array, UInt8Array, UInt16Array, UInt32Array};
use arrow::datatypes::{DataType, Field, Schema};
use pyo3_arrow::PyRecordBatch;

fn region_ingress_batch(ids: Vec<Option<u16>>) -> PyRecordBatch {
    let n = ids.len();
    let columns: Vec<arrow::array::ArrayRef> = vec![
        Arc::new(UInt16Array::from(ids)),
        Arc::new(UInt8Array::from(vec![0; n])),
        Arc::new(UInt16Array::from(vec![80; n])),
        Arc::new(UInt16Array::from(vec![2; n])),
        Arc::new(arrow::array::Float32Array::from(vec![0.8; n])),
        Arc::new(arrow::array::Float32Array::from(vec![0.6; n])),
        Arc::new(arrow::array::Float32Array::from(vec![0.3; n])),
    ];
    let schema = Arc::new(Schema::new(vec![
        Field::new("region_id", DataType::UInt16, true),
        Field::new("terrain", DataType::UInt8, false),
        Field::new("carrying_capacity", DataType::UInt16, false),
        Field::new("population", DataType::UInt16, false),
        Field::new("soil", DataType::Float32, false),
        Field::new("water", DataType::Float32, false),
        Field::new("forest_cover", DataType::Float32, false),
    ]));
    PyRecordBatch::new(RecordBatch::try_new(schema, columns).unwrap())
}

fn granary_work_input(request: Option<arrow::array::ArrayRef>, yield_value: f32) -> PyRecordBatch {
    use arrow::array::{Float32Array, ArrayRef};
    let mut fields: Vec<Field> = economy_region_input_schema().fields().iter()
        .map(|f| f.as_ref().clone()).collect();
    let mut cols: Vec<ArrayRef> = vec![
        Arc::new(UInt16Array::from(vec![0])), Arc::new(UInt8Array::from(vec![0])),
        Arc::new(UInt16Array::from(vec![80])), Arc::new(UInt8Array::from(vec![0])),
        Arc::new(UInt8Array::from(vec![255])), Arc::new(UInt8Array::from(vec![255])),
        Arc::new(Float32Array::from(vec![yield_value])),
        Arc::new(Float32Array::from(vec![0.0])), Arc::new(Float32Array::from(vec![0.0])),
    ];
    for _ in 0..8 { cols.push(Arc::new(Float32Array::from(vec![0.0]))); }
    fields.push(Field::new("farm_labor_factor", DataType::Float32, false));
    cols.push(Arc::new(Float32Array::from(vec![0.5])));
    if let Some(value) = request {
        fields.push(Field::new("granary_work_requested", value.data_type().clone(), true));
        cols.push(value);
    }
    PyRecordBatch::new(RecordBatch::try_new(Arc::new(Schema::new(fields)), cols).unwrap())
}

fn granary_work_routes() -> PyRecordBatch {
    PyRecordBatch::new(RecordBatch::new_empty(Arc::new(economy_trade_route_schema())))
}

fn granary_work_sim() -> AgentSimulator {
    let mut sim = AgentSimulator::new(1, 42);
    sim.set_region_state(region_ingress_batch(vec![Some(0)])).unwrap();
    sim.pool = AgentPool::new(10);
    for _ in 0..10 {
        sim.pool.spawn(0, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 255, 255, 255, 255);
    }
    sim.health_work = Some(crate::health_care::HealthWork {
        losses: vec![1.0], worked: vec![false], ..Default::default()
    });
    sim
}

#[test]
fn market_price_ffi_exports_actual_native_post_trade_prices() {
    use arrow::array::{ArrayRef, Float32Array};
    let mut sim = granary_work_sim();
    sim.economy_config.base_price = 2.0;
    let input = granary_work_input(None, 1.0).into_inner();
    let mut fields: Vec<Field> = input.schema().fields().iter().map(|f| f.as_ref().clone()).collect();
    let mut columns: Vec<ArrayRef> = input.columns().to_vec();
    fields.push(Field::new("craft_demand", DataType::Float32, false));
    columns.push(Arc::new(Float32Array::from(vec![1.0])));
    fields.push(Field::new("stockpile_crafts", DataType::Float32, false));
    columns.push(Arc::new(Float32Array::from(vec![2.0])));
    let batch = PyRecordBatch::new(RecordBatch::try_new(Arc::new(Schema::new(fields)), columns).unwrap());
    let output = sim.tick_economy(batch, granary_work_routes(), 0, false, 1.0).unwrap().0.into_inner();
    let val = |name| output.column_by_name(name).unwrap().as_any().downcast_ref::<Float32Array>().unwrap().value(0);
    assert_eq!(val("market_demand_craft"), 1.0);
    assert_eq!(val("market_supply_craft"), 2.0);
    assert_eq!(val("market_price_craft"), 1.0);
    assert_eq!(val("market_price_food"), 2.5);
    assert_eq!(val("market_price_luxury"), 0.0);
    assert_eq!(val("stockpile_crafts"), 0.99); // lifecycle after price
    let names = output.schema().fields().iter().map(|f| f.name().clone()).collect::<Vec<_>>();
    assert_eq!(&names[names.len()-4..], &["market_price_food", "market_price_raw_material", "market_price_luxury", "market_price_craft"]);
}

#[test]
fn granary_work_ffi_after_health_and_city_and_work_injury_proxy() {
    use arrow::array::Float32Array;
    let mut sim = granary_work_sim();
    let batch = sim.tick_economy(granary_work_input(Some(Arc::new(Float32Array::from(vec![3.0]))), 1.0),
        granary_work_routes(), 0, false, 1.0).unwrap().0.into_inner();
    let val = |name| batch.column_by_name(name).unwrap().as_any().downcast_ref::<Float32Array>().unwrap().value(0);
    assert_eq!(val("granary_work_delivered"), 3.0);
    assert_eq!(val("slot_output_0"), 1.0);
    assert_eq!(val("market_demand_food"), 5.0);
    assert!(sim.health_work.as_ref().unwrap().worked[0]);
    let barren = sim.tick_economy(granary_work_input(Some(Arc::new(Float32Array::from(vec![8.0]))), 0.0),
        granary_work_routes(), 0, false, 1.0).unwrap().0.into_inner();
    let delivered = barren.column_by_name("granary_work_delivered").unwrap().as_any()
        .downcast_ref::<Float32Array>().unwrap().value(0);
    assert_eq!(delivered, 4.0);
    assert!(sim.health_work.as_ref().unwrap().worked[0]);
    let zero = sim.tick_economy(granary_work_input(None, 0.0), granary_work_routes(), 0, false, 1.0).unwrap();
    assert!(!sim.health_work.as_ref().unwrap().worked[0]);
    assert_eq!(zero.0.into_inner().column_by_name("granary_work_delivered").unwrap().as_any()
        .downcast_ref::<Float32Array>().unwrap().value(0), 0.0);
}

#[test]
fn granary_work_ffi_absent_and_zero_keep_existing_outputs_and_state() {
    use arrow::array::Float32Array;
    let mut absent = granary_work_sim();
    let mut zero = granary_work_sim();
    let a = absent.tick_economy(granary_work_input(None, 1.0), granary_work_routes(), 0, false, 1.0).unwrap();
    let b = zero.tick_economy(granary_work_input(Some(Arc::new(Float32Array::from(vec![0.0]))), 1.0),
        granary_work_routes(), 0, false, 1.0).unwrap();
    let a = [a.0, a.1, a.2, a.3, a.4];
    let b = [b.0, b.1, b.2, b.3, b.4];
    for (left, right) in a.into_iter().zip(b) {
        assert_eq!(left.into_inner(), right.into_inner());
    }
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &absent),
               crate::persist::encode(crate::persist::KIND_AGENT, &zero));
    assert_eq!(absent.health_work.as_ref().unwrap().worked, zero.health_work.as_ref().unwrap().worked);
}

#[test]
fn granary_work_ffi_invalid_inputs_preserve_delivery_and_checkpoint() {
    use arrow::array::{ArrayRef, Float32Array, Float64Array};
    let inputs: Vec<ArrayRef> = vec![Arc::new(Float32Array::from(vec![-1.0])),
        Arc::new(Float32Array::from(vec![f32::NAN])), Arc::new(Float32Array::from(vec![f32::INFINITY])),
        Arc::new(Float32Array::from(vec![None::<f32>])), Arc::new(Float64Array::from(vec![1.0]))];
    for input in inputs {
        let mut sim = granary_work_sim();
        sim.set_hybrid_economy_mode(true);
        let mut buffer = crate::merchant::DeliveryBuffer::new(1);
        buffer.record_arrival(0, 0, 0, 1.0);
        sim.merchant_delivery_buf = Some(buffer);
        let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert!(sim.tick_economy(granary_work_input(Some(input), 1.0), granary_work_routes(),
                                 0, false, 1.0).is_err());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
        assert_eq!(sim.merchant_delivery_buf.as_ref().unwrap().arrival_imports.len(), 1);
        assert_eq!(sim.health_work.as_ref().unwrap().losses, vec![1.0]);
        assert!(!sim.health_work.as_ref().unwrap().worked[0]);
    }
}

/// PL1: the granary test region with a timber slot (yield 2) and the
/// optional woodcut columns.
fn woodcut_input(columns: Vec<(&str, arrow::array::ArrayRef)>, timber: bool) -> PyRecordBatch {
    use arrow::array::{ArrayRef, Float32Array};
    let input = granary_work_input(None, 1.0).into_inner();
    let mut fields: Vec<Field> = input.schema().fields().iter().map(|f| f.as_ref().clone()).collect();
    let mut cols: Vec<ArrayRef> = input.columns().to_vec();
    if timber {
        let i = fields.iter().position(|f| f.name() == "resource_type_1").unwrap();
        cols[i] = Arc::new(UInt8Array::from(vec![1]));
        let i = fields.iter().position(|f| f.name() == "resource_yield_1").unwrap();
        cols[i] = Arc::new(Float32Array::from(vec![2.0]));
    }
    for (name, column) in columns {
        fields.push(Field::new(name, column.data_type().clone(), true));
        cols.push(column);
    }
    PyRecordBatch::new(RecordBatch::try_new(Arc::new(Schema::new(fields)), cols).unwrap())
}

fn f32_column(value: Option<f32>) -> arrow::array::ArrayRef {
    Arc::new(arrow::array::Float32Array::from(vec![value]))
}

#[test]
fn woodcut_ffi_absent_and_zero_columns_keep_outputs_and_state() {
    use arrow::array::{Float32Array, Float64Array};
    let mut absent = granary_work_sim();
    let mut zero = granary_work_sim();
    let a = absent.tick_economy(woodcut_input(vec![], true), granary_work_routes(), 0, false, 1.0).unwrap();
    let b = zero.tick_economy(woodcut_input(vec![("woodcut_labor_away", f32_column(Some(0.0))),
                                               ("woodcut_labor", f32_column(Some(0.0)))], true),
                              granary_work_routes(), 0, false, 1.0).unwrap();
    let (ra, rb) = (a.0.into_inner(), b.0.into_inner());
    // The appended result columns are the only difference, and they are zero.
    let names: Vec<String> = rb.schema().fields().iter().map(|f| f.name().clone()).collect();
    assert_eq!(&names[names.len() - 2..], &["woodcut_labor_away_delivered", "woodcut_output"]);
    assert_eq!(rb.project(&(0..ra.num_columns()).collect::<Vec<_>>()).unwrap(), ra);
    for name in ["woodcut_labor_away_delivered", "woodcut_output"] {
        assert_eq!(rb.column_by_name(name).unwrap().as_any().downcast_ref::<Float32Array>().unwrap().value(0), 0.0);
    }
    assert!(ra.column_by_name("woodcut_output").is_none());
    assert_eq!(a.1.into_inner(), b.1.into_inner());
    assert_eq!(a.2.into_inner(), b.2.into_inner());
    assert_eq!(a.3.into_inner(), b.3.into_inner());
    let (ca, cb) = (a.4.into_inner(), b.4.into_inner());
    assert_eq!(cb.project(&(0..ca.num_columns()).collect::<Vec<_>>()).unwrap(), ca);
    assert_eq!(cb.column_by_name("woodcut_outflow").unwrap().as_any().downcast_ref::<Float64Array>().unwrap()
               .value(0), 0.0);
    assert!(ca.column_by_name("woodcut_outflow").is_none());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &absent),
               crate::persist::encode(crate::persist::KIND_AGENT, &zero));
}

#[test]
fn woodcut_ffi_reports_the_crew_and_keeps_the_stock() {
    use arrow::array::{Float32Array, Float64Array};
    let mut plain = granary_work_sim();
    let mut crews = granary_work_sim();
    let a = plain.tick_economy(woodcut_input(vec![], true), granary_work_routes(), 0, false, 1.0).unwrap();
    let b = crews.tick_economy(woodcut_input(vec![("woodcut_labor_away", f32_column(Some(1.0))),
                                                ("woodcut_labor", f32_column(Some(2.0)))], true),
                               granary_work_routes(), 0, false, 1.0).unwrap();
    let (ra, rb) = (a.0.into_inner(), b.0.into_inner());
    let val = |batch: &RecordBatch, name: &str| batch.column_by_name(name).unwrap().as_any()
        .downcast_ref::<Float32Array>().unwrap().value(0);
    // 10 farmers at half time, less one care loss: 4 headcount; one away.
    assert_eq!(val(&rb, "woodcut_labor_away_delivered"), 1.0);
    let cut = val(&rb, "woodcut_output");
    assert!(cut > 0.0);
    // Without slot curves the crew of two adds 2 x yield 2 on the slot.
    assert!((cut - 4.0).abs() < 1e-5, "{cut}");
    assert!(val(&rb, "slot_output_1") >= cut);
    let cons = b.4.into_inner();
    let outflow = cons.column_by_name("woodcut_outflow").unwrap().as_any()
        .downcast_ref::<Float64Array>().unwrap().value(0);
    assert_eq!(outflow, cut as f64);
    // The harvest left with the crew: the timber stock is the residents'.
    let resident_a = val(&ra, "slot_output_1");
    let resident_b = val(&rb, "slot_output_1") - cut;
    assert!(resident_b < resident_a);   // one farmer fewer at home
    assert!((val(&rb, "stockpile_timber") - resident_b * (1.0 - 0.005)).abs() < 1e-5);
}

#[test]
fn woodcut_ffi_invalid_inputs_preserve_state() {
    let cases: Vec<(Vec<(&str, arrow::array::ArrayRef)>, bool)> = vec![
        (vec![("woodcut_labor_away", f32_column(Some(1.0)))], true),
        (vec![("woodcut_labor", f32_column(Some(1.0)))], true),
        (vec![("woodcut_labor_away", f32_column(Some(0.0))), ("woodcut_labor", f32_column(Some(1.0)))], false),
        (vec![("woodcut_labor_away", f32_column(Some(-1.0))), ("woodcut_labor", f32_column(Some(0.0)))], true),
        (vec![("woodcut_labor_away", f32_column(Some(0.0))), ("woodcut_labor", f32_column(Some(f32::NAN)))], true),
        (vec![("woodcut_labor_away", f32_column(None)), ("woodcut_labor", f32_column(Some(0.0)))], true),
        (vec![("woodcut_labor_away", Arc::new(arrow::array::Float64Array::from(vec![0.0]))),
              ("woodcut_labor", f32_column(Some(0.0)))], true),
    ];
    for (columns, timber) in cases {
        let mut sim = granary_work_sim();
        sim.set_hybrid_economy_mode(true);
        let mut buffer = crate::merchant::DeliveryBuffer::new(1);
        buffer.record_arrival(0, 0, 0, 1.0);
        sim.merchant_delivery_buf = Some(buffer);
        let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert!(sim.tick_economy(woodcut_input(columns, timber), granary_work_routes(), 0, false, 1.0).is_err());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
        assert_eq!(sim.merchant_delivery_buf.as_ref().unwrap().arrival_imports.len(), 1);
        assert!(!sim.health_work.as_ref().unwrap().worked[0]);
    }
}

fn mobility_gate_signals() -> PyRecordBatch {
    let schema = Schema::new(vec![
        Field::new("civ_id", DataType::UInt8, false), Field::new("stability", DataType::UInt8, false),
        Field::new("is_at_war", DataType::Boolean, false), Field::new("dominant_faction", DataType::UInt8, false),
        Field::new("faction_military", DataType::Float32, false), Field::new("faction_merchant", DataType::Float32, false),
        Field::new("faction_cultural", DataType::Float32, false),
    ]);
    PyRecordBatch::new(RecordBatch::new_empty(Arc::new(schema)))
}

#[test]
fn mobility_gate_ffi_zero_and_invalid_are_nonmutating_or_old_path() {
    Python::initialize();
    Python::attach(|py| {
        let mut a = AgentSimulator::new(1, 42);
        let mut b = AgentSimulator::new(1, 42);
        a.set_region_state(region_ingress_batch(vec![Some(0)])).unwrap();
        b.set_region_state(region_ingress_batch(vec![Some(0)])).unwrap();
        let before = crate::persist::encode(crate::persist::KIND_AGENT, &a);
        for invalid in [-1.0, f32::NAN, f32::INFINITY] {
            assert!(a.tick(py, 0, mobility_gate_signals(), invalid).is_err());
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &a), before);
        }
        for turn in 0..3 {
            let ea = a.tick(py, turn, mobility_gate_signals(), 0.0).unwrap().into_inner();
            let eb = b.tick(py, turn, mobility_gate_signals(), 0.0).unwrap().into_inner();
            assert_eq!(ea, eb);
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &a),
                       crate::persist::encode(crate::persist::KIND_AGENT, &b));
            assert!(a.mobility_gate_frame.is_none());
        }
        a.tick(py, 3, mobility_gate_signals(), 1.0).unwrap();
        let before_read = crate::persist::encode(crate::persist::KIND_AGENT, &a);
        let first = a.get_mobility_gate_frame().unwrap();
        assert_eq!(first.0.0, 3);
        assert_eq!(a.get_mobility_gate_frame().unwrap(), first);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &a), before_read);
        assert!(!crate::persist::schema_of::<AgentSimulator>().contains("mobility_gate_frame"));
        a.tick(py, 4, mobility_gate_signals(), 0.0).unwrap();
        assert!(a.get_mobility_gate_frame().is_none());
    });
}

fn teaching_work_sim() -> (AgentSimulator, usize) {
    let mut sim = AgentSimulator::new(1, 42);
    sim.set_region_state(region_ingress_batch(vec![Some(0)])).unwrap();
    sim.pool = AgentPool::new(4);
    let scholar = sim.pool.spawn(0, 0, Occupation::Scholar, 30,
        0.5, 0.5, 0.5, 255, 255, 255, 255);
    (sim, scholar)
}

#[test]
fn teaching_work_ffi_cancel_validation_and_noop_preserve_existing_state() {
    let (mut sim, slot) = teaching_work_sim();
    let id = sim.pool.ids[slot];
    sim.pool.health_work_loss = vec![(id, 0.25)];
    let saved = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    assert!(sim.prepare_teaching_work(0, vec![0.0], vec![]).unwrap().is_none());
    assert!(!sim.has_pending_teaching_work());
    for bad in [vec![], vec![-1.0], vec![f32::NAN], vec![f32::INFINITY]] {
        assert!(sim.prepare_teaching_work(0, bad, vec![]).is_err());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), saved);
        assert_eq!(sim.pool.health_work_loss, vec![(id, 0.25)]);
    }
    let before = sim.prepare_teaching_work(0, vec![0.5], vec![]).unwrap().unwrap();
    assert_eq!(before.1[0], (0, 0.75, 0.5, 0.5, 0.0));
    assert_eq!(before.2, vec![(id, 0, 0.5, 0.0)]);
    assert!(sim.has_pending_teaching_work());
    assert!(sim.prepare_teaching_work(0, vec![0.5], vec![]).is_err());
    assert!(sim.cancel_teaching_work(1).is_err());
    assert!(sim.cancel_teaching_work(0).unwrap());
    assert!(!sim.cancel_teaching_work(0).unwrap());
    assert_eq!(sim.pool.health_work_loss, vec![(id, 0.25)]);
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), saved);
    assert!(!crate::persist::schema_of::<AgentSimulator>().contains("teaching_result"));
    assert!(!crate::persist::schema_of::<AgentSimulator>().contains("teaching_plan"));
}

#[test]
fn teaching_work_ffi_charges_actual_income_once_and_receipt_is_read_only() {
    Python::initialize();
    Python::attach(|py| {
        let (mut sim, slot) = teaching_work_sim();
        let id = sim.pool.ids[slot];
        sim.pool.health_work_loss = vec![(id, 0.25)];
        sim.prepare_teaching_work(0, vec![0.5], vec![]).unwrap();
        let saved = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert!(sim.tick(py, 1, mobility_gate_signals(), 0.0).is_err());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), saved);
        assert!(sim.has_pending_teaching_work());
        sim.tick(py, 0, mobility_gate_signals(), 0.0).unwrap();
        assert!(!sim.has_pending_teaching_work());
        let result = sim.get_teaching_work_result().unwrap();
        assert_eq!(result.0, 0);
        assert_eq!(result.1[0], (0, 0.75, 0.5, 0.5, 0.5));
        assert_eq!(result.2, vec![(id, 0, 0.5, 0.5)]);
        let expected = (crate::agent::STARTING_WEALTH + crate::agent::SCHOLAR_INCOME * 0.25)
            * (1.0 - crate::agent::WEALTH_DECAY);
        assert!((sim.pool.wealth[slot] - expected).abs() < 1e-6);
        let after = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert_eq!(sim.get_teaching_work_result().unwrap(), result);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), after);
        assert!(sim.prepare_teaching_work(0, vec![0.1], vec![]).is_err());
        sim.tick(py, 1, mobility_gate_signals(), 0.0).unwrap();
        assert!(sim.get_teaching_work_result().is_none());
    });
}

#[test]
fn teaching_work_ffi_does_not_double_charge_actual_farmer_care() {
    Python::initialize();
    Python::attach(|py| {
        let build = || {
            let (mut sim, scholar) = teaching_work_sim();
            let farmer = sim.pool.spawn(0, 0, Occupation::Farmer, 30,
                0.5, 0.5, 0.5, 255, 255, 255, 255);
            sim.pool.health_work_loss = vec![(0, 0.0), (sim.pool.ids[farmer], 0.5)];
            (sim, scholar, farmer)
        };
        let (mut a, _, farmer_a) = build(); let (mut b, _, farmer_b) = build();
        b.prepare_teaching_work(0, vec![0.5], vec![]).unwrap();
        a.tick(py, 0, mobility_gate_signals(), 0.0).unwrap();
        b.tick(py, 0, mobility_gate_signals(), 0.0).unwrap();
        assert_eq!(a.pool.wealth[farmer_a].to_bits(), b.pool.wealth[farmer_b].to_bits());
        assert_eq!(b.get_teaching_work_result().unwrap().1[0].4, 0.5);
    });
}

#[test]
fn teaching_work_ffi_reused_slot_cannot_receive_or_deliver_other_id_work() {
    Python::initialize();
    Python::attach(|py| {
        let (mut sim, slot) = teaching_work_sim();
        let original = sim.pool.ids[slot];
        sim.prepare_teaching_work(0, vec![1.0], vec![]).unwrap();
        sim.pool.kill(slot);
        let fresh = sim.pool.spawn(0, 0, Occupation::Scholar, 30,
            0.5, 0.5, 0.5, 255, 255, 255, 255);
        assert_eq!(fresh, slot); assert_ne!(sim.pool.ids[fresh], original);
        sim.tick(py, 0, mobility_gate_signals(), 0.0).unwrap();
        let result = sim.get_teaching_work_result().unwrap();
        assert_eq!(result.2, vec![(original, 0, 1.0, 0.0)]);
        let expected = (crate::agent::STARTING_WEALTH + crate::agent::SCHOLAR_INCOME)
            * (1.0 - crate::agent::WEALTH_DECAY);
        assert!((sim.pool.wealth[fresh] - expected).abs() < 1e-6);
    });
}

#[test]
fn teaching_work_ffi_death_before_wealth_does_not_deliver() {
    Python::initialize();
    Python::attach(|py| {
        let (mut sim, slot) = teaching_work_sim();
        let id = sim.pool.ids[slot];
        sim.prepare_teaching_work(0, vec![1.0], vec![]).unwrap();
        sim.queue_targeted_deaths(vec![id]);
        sim.tick(py, 0, mobility_gate_signals(), 0.0).unwrap();
        let result = sim.get_teaching_work_result().unwrap();
        assert_eq!(result.1[0], (0, 1.0, 1.0, 1.0, 0.0));
        assert_eq!(result.2, vec![(id, 0, 1.0, 0.0)]);
    });
}

#[test]
fn teaching_work_ffi_zero_is_bitwise_old_path() {
    Python::initialize();
    Python::attach(|py| {
        let (mut a, _) = teaching_work_sim(); let (mut b, _) = teaching_work_sim();
        assert!(b.prepare_teaching_work(0, vec![0.0], vec![]).unwrap().is_none());
        let ea = a.tick(py, 0, mobility_gate_signals(), 0.0).unwrap().into_inner();
        let eb = b.tick(py, 0, mobility_gate_signals(), 0.0).unwrap().into_inner();
        assert_eq!(ea, eb);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &a),
                   crate::persist::encode(crate::persist::KIND_AGENT, &b));
        assert!(a.get_teaching_work_result().is_none() && b.get_teaching_work_result().is_none());
    });
}

#[test]
fn native_region_count_admission_keeps_empty_and_exact_upper_boundary() {
    // The maximum is admitted without allocating millions of reserve slots.
    for n in [0, 1, 33, 65535] {
        assert!(validate_native_region_count(n).is_ok());
    }
    for n in [65536, usize::MAX] {
        assert!(validate_native_region_count(n).is_err());
        assert!(AgentSimulator::py_new(n, 42).is_err());
    }
}

#[test]
#[should_panic(expected = "invalid native region count")]
fn rust_region_constructor_refuses_before_reserve_size_multiplication() {
    let _ = AgentSimulator::new(usize::MAX, 42);
}

#[test]
fn native_zero_region_constructor_and_empty_initialization_stay_valid() {
    let mut sim = AgentSimulator::py_new(0, 42).unwrap();
    assert_eq!(sim.get_snapshot().unwrap().into_inner().num_rows(), 0);
    assert!(sim.snapshot_is_cached());
    sim.set_region_state(region_ingress_batch(vec![])).unwrap();
    assert!(sim.initialized);
    assert!(sim.regions.is_empty());
    assert_eq!(sim.get_region_populations().unwrap().into_inner().num_rows(), 0);
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    sim.set_region_state(region_ingress_batch(vec![])).unwrap();
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
}

#[test]
fn native_first_region_refusals_preserve_checkpoint_and_held_snapshot() {
    let invalid = [
        vec![Some(0)],
        vec![Some(0), Some(1), Some(2)],
        vec![Some(0), Some(2)],
        vec![Some(1), Some(0)],
        vec![Some(0), Some(0)],
        vec![Some(0), None],
    ];
    for ids in invalid {
        let mut sim = AgentSimulator::new(2, 42);
        sim.get_snapshot().unwrap();
        let held = sim.snapshot_cache.as_ref().unwrap().clone();
        let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert!(sim.set_region_state(region_ingress_batch(ids)).is_err());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
        assert!(sim.snapshot_is_cached());
        assert!(Arc::ptr_eq(held.column(0), sim.snapshot_cache.as_ref().unwrap().column(0)));
        assert!(!sim.initialized);
        // Rejection draws nothing and does not poison later valid initialization.
        sim.set_region_state(region_ingress_batch(vec![Some(0), Some(1)])).unwrap();
        let mut fresh = AgentSimulator::new(2, 42);
        fresh.set_region_state(region_ingress_batch(vec![Some(0), Some(1)])).unwrap();
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim),
            crate::persist::encode(crate::persist::KIND_AGENT, &fresh));
    }
}

#[test]
fn native_later_region_shape_refusal_precedes_state_and_cache_changes() {
    let mut sim = AgentSimulator::new(2, 42);
    sim.set_region_state(region_ingress_batch(vec![Some(0), Some(1)])).unwrap();
    sim.get_snapshot().unwrap();
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let held = sim.snapshot_cache.as_ref().unwrap().clone();
    assert!(sim.set_region_state(region_ingress_batch(vec![Some(0)])).is_err());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    assert!(Arc::ptr_eq(held.column(0), sim.snapshot_cache.as_ref().unwrap().column(0)));
    let counts = sim.get_region_populations().unwrap().into_inner();
    let alive = counts.column_by_name("alive_count").unwrap().as_any()
        .downcast_ref::<UInt32Array>().unwrap();
    assert_eq!(alive.values().as_ref(), &[2, 2]);
}

#[test]
fn native_missing_column_refusal_keeps_existing_state_and_snapshot() {
    let mut sim = AgentSimulator::new(2, 42);
    sim.get_snapshot().unwrap();
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let mut batch = region_ingress_batch(vec![Some(0), Some(1)]).into_inner();
    batch.remove_column(4); // soil
    assert!(sim.set_region_state(PyRecordBatch::new(batch)).is_err());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    assert!(sim.snapshot_is_cached());
}

#[test]
fn decision_delivery_configuration_and_frame_are_checkpoint_transient() {
    let mut sim = AgentSimulator::new(2, 42);
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let schema = AgentSimulator::checkpoint_schema();
    assert_eq!(schema.1, "dcf0c34097c88451", "a470/06db persisted schema must remain unchanged");
    assert!(!schema.2.contains("decision_delivery"));
    sim.configure_decision_delivery(true, 8, 16, Some(vec![0, 1]), 16).unwrap();
    sim.decision_delivery_frame = Some(crate::decision_delivery::DeliveryFrame::new(101, 1));
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    assert_eq!(AgentSimulator::checkpoint_schema(), schema);
    let restored: AgentSimulator = crate::persist::decode(crate::persist::KIND_AGENT, &before).unwrap();
    assert!(restored.decision_delivery_config.is_none());
    assert!(restored.decision_delivery_frame.is_none());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &restored), before);
}

#[test]
fn decision_delivery_reads_are_non_draining_and_disabling_clears_the_frame() {
    let mut sim = AgentSimulator::new(1, 42);
    sim.configure_decision_delivery(true, 8, 16, None, 16).unwrap();
    sim.decision_delivery_frame = Some(crate::decision_delivery::DeliveryFrame::new(17, 0));
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let (h1, d1, c1) = sim.get_decision_delivery_frame().unwrap();
    let (h2, d2, c2) = sim.get_decision_delivery_frame().unwrap();
    assert_eq!(h1.into_inner(), h2.into_inner());
    assert_eq!(d1.into_inner(), d2.into_inner());
    assert_eq!(c1.into_inner(), c2.into_inner());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    sim.configure_decision_delivery(false, 0, 0, None, 0).unwrap();
    assert!(sim.decision_delivery_config.is_none());
    assert!(sim.decision_delivery_frame.is_none());
    let (header, decisions, candidates) = sim.get_decision_delivery_frame().unwrap();
    let header = header.into_inner();
    let enabled = header.column_by_name("enabled").unwrap().as_any().downcast_ref::<arrow::array::BooleanArray>().unwrap();
    assert!(!enabled.value(0));
    assert_eq!(decisions.into_inner().num_rows(), 0);
    assert_eq!(candidates.into_inner().num_rows(), 0);
}

#[test]
fn test_postpass_recompute_refreshes_yields_without_second_mineral_extraction() {
    use arrow::array::Float32Array;
    let mut sim = AgentSimulator::new(1, 42);
    let mut region = RegionState::new(0);
    region.terrain = 0;
    region.soil = 0.8;
    region.water = 0.6;
    region.forest_cover = 0.2;
    region.carrying_capacity = 60;
    region.population = 30;
    region.controller_civ = 0;
    region.capacity_modifier = 1.0;
    region.resource_types = [0, 5, 255]; // grain + ore
    region.resource_base_yield = [1.0, 0.8, 0.0];
    region.resource_effective_yield = [1.0, 0.8, 0.0];
    region.resource_reserves = [1.0, 0.2, 0.0];
    sim.regions = vec![region];
    sim.tick_ecology(0, 0, vec![false], vec![false]).unwrap();
    let after_tick = sim.regions[0].resource_reserves;
    let ticked_yields = sim.regions[0].resource_yields;
    assert!(after_tick[1] < 0.2, "the ecology tick itself extracts ore once");

    // Python post-pass changed soil (e.g. a tradition soil floor), forcing
    // a native yield recompute for this region.
    let r = &sim.regions[0];
    let patch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![
            Field::new("region_id", DataType::UInt16, false),
            Field::new("population", DataType::UInt16, false),
            Field::new("soil", DataType::Float32, false),
            Field::new("water", DataType::Float32, false),
            Field::new("forest_cover", DataType::Float32, false),
            Field::new("terrain", DataType::UInt8, false),
            Field::new("carrying_capacity", DataType::UInt16, false),
        ])),
        vec![
            Arc::new(UInt16Array::from(vec![0u16])),
            Arc::new(UInt16Array::from(vec![r.population])),
            Arc::new(Float32Array::from(vec![r.soil * 0.5])),
            Arc::new(Float32Array::from(vec![r.water])),
            Arc::new(Float32Array::from(vec![r.forest_cover])),
            Arc::new(UInt8Array::from(vec![r.terrain])),
            Arc::new(UInt16Array::from(vec![r.carrying_capacity])),
        ],
    ).unwrap();
    sim.apply_region_postpass_patch(PyRecordBatch::new(patch)).unwrap();
    assert_eq!(sim.regions[0].resource_reserves, after_tick, "post-pass must not extract again");
    assert!(sim.regions[0].resource_yields[0] < ticked_yields[0], "crop yield follows patched soil");
    assert_eq!(sim.regions[0].resource_yields[1], ticked_yields[1]);
}

#[test]
fn test_stockpile_commitments_read_only_and_hybrid_scoped() {
    use arrow::array::Float32Array;
    use crate::merchant::{DeliveryBuffer, ShadowLedger};
    let mut sim = AgentSimulator::new(2, 42);
    let mut ledger = ShadowLedger::new(2);
    ledger.reserved[0][0] = 7.0;
    ledger.in_transit_out[0][0] = 99.0; // older cargo not debited twice
    ledger.pending_delivery[1][0] = 123.0; // cumulative, not spendable stocks
    let mut buffer = DeliveryBuffer::new(2);
    buffer.record_departure(0, 1, 5.0);
    buffer.record_arrival(0, 1, 0, 9.0);
    buffer.record_return(0, 0, 3.0);
    sim.merchant_ledger = Some(ledger);
    sim.merchant_delivery_buf = Some(buffer);
    let read = |sim: &AgentSimulator, column: &str| -> Vec<f32> {
        let batch = sim.get_stockpile_commitments().unwrap().into_inner();
        assert_eq!(batch.num_rows(), 2 * crate::economy::NUM_GOODS);
        batch.column_by_name(column).unwrap().as_any()
            .downcast_ref::<Float32Array>().unwrap().values().to_vec()
    };
    assert_eq!(read(&sim, "reserved"), vec![0.0; 2 * crate::economy::NUM_GOODS]);
    assert_eq!(read(&sim, "pending_departure"), vec![0.0; 2 * crate::economy::NUM_GOODS]);
    sim.set_hybrid_economy_mode(true);
    let res = read(&sim, "reserved");
    let dep = read(&sim, "pending_departure");
    assert_eq!(res[0], 7.0);
    assert_eq!(res.iter().sum::<f32>(), 7.0);
    assert_eq!(dep[1], 5.0);
    assert_eq!(dep.iter().sum::<f32>(), 5.0);
    assert_eq!(read(&sim, "reserved"), res);
    assert_eq!(read(&sim, "pending_departure"), dep);
    let buffer = sim.merchant_delivery_buf.as_ref().unwrap();
    assert_eq!(buffer.arrival_imports.len(), 1);
    assert_eq!(buffer.return_credits[0][0], 3.0);
    assert_eq!(buffer.diagnostics.total_departures[0][1], 5.0);
    assert_eq!(sim.merchant_ledger.as_ref().unwrap().in_transit_out[0][0], 99.0);
}

#[test]
fn test_pending_arrivals_read_only() {
    use arrow::array::Float32Array;
    use crate::merchant::DeliveryBuffer;
    let mut sim = AgentSimulator::new(3, 42);
    // No buffer yet: empty batch with the full schema.
    let empty = sim.get_pending_arrivals().unwrap().into_inner();
    assert_eq!(empty.num_rows(), 0);
    assert!(empty.column_by_name("qty").is_some());
    let mut buffer = DeliveryBuffer::new(3);
    buffer.record_arrival(0, 2, 1, 0.75);
    buffer.record_arrival(2, 1, 0, 1.0);
    sim.merchant_delivery_buf = Some(buffer);
    let read = |sim: &AgentSimulator| {
        let batch = sim.get_pending_arrivals().unwrap().into_inner();
        let src = batch.column_by_name("source_region").unwrap().as_any()
            .downcast_ref::<UInt16Array>().unwrap().values().to_vec();
        let dst = batch.column_by_name("dest_region").unwrap().as_any()
            .downcast_ref::<UInt16Array>().unwrap().values().to_vec();
        let slot = batch.column_by_name("good_slot").unwrap().as_any()
            .downcast_ref::<UInt8Array>().unwrap().values().to_vec();
        let qty = batch.column_by_name("qty").unwrap().as_any()
            .downcast_ref::<Float32Array>().unwrap().values().to_vec();
        (src, dst, slot, qty)
    };
    let first = read(&sim);
    assert_eq!(first, (vec![0, 2], vec![2, 1], vec![1, 0], vec![0.75, 1.0]));
    // Non-draining: a second read sees the same records and the buffer is intact.
    assert_eq!(read(&sim), first);
    assert_eq!(sim.merchant_delivery_buf.as_ref().unwrap().arrival_imports.len(), 2);
}

#[test]
fn test_promotion_memory_queued_then_written_once_next_tick() {
    use crate::memory::MemoryEventType;
    let mut sim = AgentSimulator::new(1, 42);
    let slot = sim.pool.spawn(
        0, 3, crate::agent::Occupation::Soldier, 30,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    let bystander = sim.pool.spawn(
        0, 3, crate::agent::Occupation::Farmer, 30,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    sim.pool.life_events[slot] = crate::agent::LIFE_EVENT_REBELLION; // bypass trigger
    sim.turn = 7;

    let promoted = sim.get_promotions().unwrap().into_inner();
    assert_eq!(promoted.num_rows(), 1);
    // Not written during get_promotions: the same-turn Python Mule roll
    // must see only the agent's pre-promotion memories.
    assert_eq!(sim.pool.memory_count[slot], 0);
    assert_eq!(sim.pending_promotion_memories.len(), 1);

    sim.turn = 8;
    sim.flush_pending_promotion_memories();
    assert!(sim.pending_promotion_memories.is_empty());
    assert_eq!(sim.pool.memory_count[slot], 1);
    assert_eq!(sim.pool.memory_event_types[slot][0], MemoryEventType::Promotion as u8);
    assert_eq!(sim.pool.memory_intensities[slot][0], crate::agent::PROMOTION_DEFAULT_INTENSITY);
    assert_eq!(sim.pool.memory_turns[slot][0], 7);
    assert_eq!(sim.pool.memory_source_civs[slot][0], 3);
    assert_eq!(sim.pool.memory_count[bystander], 0);

    // Already-registered characters are not re-promoted, and the drained
    // queue does not write the memory a second time.
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 0);
    sim.flush_pending_promotion_memories();
    assert_eq!(sim.pool.memory_count[slot], 1);
}

#[test]
fn test_movement_leaders_are_promoted_once_from_the_queue() {
    let mut sim = AgentSimulator::new(1, 42);
    // No life events and no skill: the regular gates promote no one.
    let leader = sim.pool.spawn(
        0, 2, crate::agent::Occupation::Farmer, 30,
        0.5, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    let other = sim.pool.spawn(
        0, 2, crate::agent::Occupation::Farmer, 30,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    sim.turn = 9;
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 0);
    assert!(sim.queue_movement_leaders(vec![1], vec![2]).is_err()); // a scientist is no leader role
    assert!(sim.queue_movement_leaders(vec![1], vec![4]).is_err()); // nor an exile
    let id = sim.pool.ids[leader];
    sim.queue_movement_leaders(vec![id, 999_999], vec![3, 0]).unwrap();
    let batch = sim.get_promotions().unwrap().into_inner();
    assert_eq!(batch.num_rows(), 1); // the unknown id is skipped
    let col = |name: &str| batch.column_by_name(name).unwrap().as_any()
        .downcast_ref::<UInt8Array>().unwrap().value(0);
    assert_eq!(col("role"), crate::named_characters::CharacterRole::Prophet as u8);
    assert_eq!(col("trigger"), crate::named_characters::TRIGGER_MOVEMENT_LEADER);
    assert_eq!(col("civ_id"), 2);
    assert!(sim.pending_movement_leaders.is_empty());
    // The queue is drained and the leader registered: not promoted again,
    // even when queued again.
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 0);
    sim.queue_movement_leaders(vec![id], vec![3]).unwrap();
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 0);
    assert_eq!(sim.pool.movement_ids[other], 0);
    // A registry full of the dead still admits a leader (living caps).
    for k in 0..60u32 {
        sim.registry.register(1_000_000 + k, crate::named_characters::CharacterRole::General,
                              2, 2, 0, 1, 0, 0, 0);
    }
    assert_eq!(sim.registry.living_named(&sim.pool).per_civ[2], 1); // the leader alone
    sim.queue_movement_leaders(vec![sim.pool.ids[other]], vec![0]).unwrap();
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 1);
}

#[test]
fn test_promotion_memory_skipped_if_agent_died_before_flush() {
    let mut sim = AgentSimulator::new(1, 42);
    let slot = sim.pool.spawn(
        0, 0, crate::agent::Occupation::Soldier, 30,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    sim.pool.life_events[slot] = crate::agent::LIFE_EVENT_REBELLION;
    assert_eq!(sim.get_promotions().unwrap().into_inner().num_rows(), 1);
    sim.pool.kill(slot);
    let reused = sim.pool.spawn(
        0, 0, crate::agent::Occupation::Farmer, 0,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    assert_eq!(reused, slot, "test assumes the freed slot is reused");
    sim.flush_pending_promotion_memories();
    assert_eq!(sim.pool.memory_count[reused], 0);
    assert!(sim.pending_promotion_memories.is_empty());
}

#[test]
fn test_personality_label_bold() {
    assert_eq!(personality_label(0.8, 0.1, 0.2), Some("the Bold"));
}

#[test]
fn test_personality_label_neutral() {
    assert_eq!(personality_label(0.2, 0.1, -0.3), None);
}

#[test]
fn test_personality_label_fickle() {
    assert_eq!(personality_label(0.1, 0.2, -0.7), Some("the Fickle"));
}

#[test]
fn test_personality_label_ambitious() {
    assert_eq!(personality_label(0.1, 0.9, 0.3), Some("the Ambitious"));
}

#[test]
fn test_personality_label_steadfast() {
    assert_eq!(personality_label(0.1, 0.2, 0.8), Some("the Steadfast"));
}

// ---------------------------------------------------------------------------
// M50a relationship FFI tests
// ---------------------------------------------------------------------------

/// Build an ops RecordBatch. Each tuple: (op_type, agent_a, agent_b, bond_type, sentiment, formed_turn)
fn make_ops_batch(ops: &[(u8, u32, u32, u8, i8, u16)]) -> PyRecordBatch {
    let schema = Arc::new(Schema::new(vec![
        Field::new("op_type",     DataType::UInt8,  false),
        Field::new("agent_a",     DataType::UInt32, false),
        Field::new("agent_b",     DataType::UInt32, false),
        Field::new("bond_type",   DataType::UInt8,  false),
        Field::new("sentiment",   DataType::Int8,   false),
        Field::new("formed_turn", DataType::UInt16, false),
    ]));
    let rb = RecordBatch::try_new(
        schema,
        vec![
            Arc::new(UInt8Array::from(ops.iter().map(|o| o.0).collect::<Vec<_>>()))  as _,
            Arc::new(UInt32Array::from(ops.iter().map(|o| o.1).collect::<Vec<_>>())) as _,
            Arc::new(UInt32Array::from(ops.iter().map(|o| o.2).collect::<Vec<_>>())) as _,
            Arc::new(UInt8Array::from(ops.iter().map(|o| o.3).collect::<Vec<_>>()))  as _,
            Arc::new(Int8Array::from(ops.iter().map(|o| o.4).collect::<Vec<_>>()))   as _,
            Arc::new(UInt16Array::from(ops.iter().map(|o| o.5).collect::<Vec<_>>())) as _,
        ],
    ).unwrap();
    PyRecordBatch::new(rb)
}

/// Create a minimal simulator with two spawned agents. Returns (simulator, id_a, id_b).
fn make_sim_with_two_agents() -> (AgentSimulator, u32, u32) {
    let mut sim = AgentSimulator::new(1, 42);
    // Manually spawn two agents directly into the pool (bypassing set_region_state).
    let slot_a = sim.pool.spawn(
        0, 0, crate::agent::Occupation::Farmer, 20,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    let slot_b = sim.pool.spawn(
        0, 0, crate::agent::Occupation::Farmer, 20,
        0.0, 0.0, 0.0, 0, 0, 0, crate::agent::BELIEF_NONE,
    );
    let id_a = sim.pool.ids[slot_a];
    let id_b = sim.pool.ids[slot_b];
    (sim, id_a, id_b)
}

// Test 1: UpsertDirected round-trip — apply op and read back via get_agent_relationships
#[test]
fn test_apply_ops_upsert_directed_round_trip() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // op=0 UpsertDirected, bond_type=6 (Friend), sentiment=50, formed_turn=10
    let batch = make_ops_batch(&[(0, id_a, id_b, 6, 50, 10)]);
    sim.apply_relationship_ops(batch).unwrap();

    let rels = sim.get_agent_relationships(id_a).expect("agent_a must exist");
    assert_eq!(rels.len(), 1);
    let (target, sent, bt, ft) = rels[0];
    assert_eq!(target, id_b);
    assert_eq!(sent, 50);
    assert_eq!(bt, 6); // Friend
    assert_eq!(ft, 10);
}

// Test 2: Batch ordering — Upsert then Remove then Upsert on same bond
#[test]
fn test_apply_ops_batch_ordering_upsert_remove_upsert() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // Three ops in one batch: upsert Friend, remove Friend, upsert Friend again
    let batch = make_ops_batch(&[
        (0, id_a, id_b, 6, 30, 5),   // UpsertDirected Friend
        (2, id_a, id_b, 6, 0, 0),    // RemoveDirected Friend (sentiment/ft fields ignored for remove)
        (0, id_a, id_b, 6, 70, 15),  // UpsertDirected Friend again
    ]);
    sim.apply_relationship_ops(batch).unwrap();

    let rels = sim.get_agent_relationships(id_a).expect("agent_a must exist");
    assert_eq!(rels.len(), 1, "should end up with one bond after remove+re-upsert");
    let (target, sent, _bt, ft) = rels[0];
    assert_eq!(target, id_b);
    assert_eq!(sent, 70);
    assert_eq!(ft, 15); // new formed_turn since this is a fresh insert
}

// Test 3: Unknown bond_type (>7) is silently skipped — no panic, no bond written
#[test]
fn test_apply_ops_unknown_bond_type_skipped() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // bond_type=99 is not a valid BondType
    let batch = make_ops_batch(&[(0, id_a, id_b, 99, 50, 10)]);
    sim.apply_relationship_ops(batch).unwrap(); // must not panic

    let rels = sim.get_agent_relationships(id_a).expect("agent_a must exist");
    assert_eq!(rels.len(), 0, "invalid bond_type must be silently skipped");
}

// Test 4: RemoveDirected with dead/missing target succeeds (source must be alive)
#[test]
fn test_apply_ops_remove_directed_dead_target() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // First, form a directed bond from a to b
    let upsert = make_ops_batch(&[(0, id_a, id_b, 6, 40, 5)]);
    sim.apply_relationship_ops(upsert).unwrap();

    // Kill agent_b in the pool
    if let Some(slot_b) = sim.pool.find_slot_by_id(id_b) {
        sim.pool.alive[slot_b] = false;
    }

    // RemoveDirected — source (id_a) is alive, target (id_b) is dead
    // The op should succeed and remove the bond from id_a's side
    let remove = make_ops_batch(&[(2, id_a, id_b, 6, 0, 0)]);
    sim.apply_relationship_ops(remove).unwrap(); // must not panic

    let rels = sim.get_agent_relationships(id_a).expect("agent_a must still be alive");
    assert_eq!(rels.len(), 0, "bond must be removed even when target is dead");
}

// Test 5: RemoveSymmetric with one dead endpoint — still removes the live side
#[test]
fn test_apply_ops_remove_symmetric_one_dead_endpoint() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // UpsertSymmetric Rival (bond_type=1, symmetric)
    let upsert = make_ops_batch(&[(1, id_a, id_b, 1, -30, 8)]);
    sim.apply_relationship_ops(upsert).unwrap();

    // Verify both sides exist before the remove
    let rels_a = sim.get_agent_relationships(id_a).unwrap();
    let rels_b = sim.get_agent_relationships(id_b).unwrap();
    assert_eq!(rels_a.len(), 1);
    assert_eq!(rels_b.len(), 1);

    // Kill id_b
    if let Some(slot_b) = sim.pool.find_slot_by_id(id_b) {
        sim.pool.alive[slot_b] = false;
    }

    // RemoveSymmetric — id_b is dead, id_a is alive
    let remove = make_ops_batch(&[(3, id_a, id_b, 1, 0, 0)]);
    sim.apply_relationship_ops(remove).unwrap(); // must not panic

    let rels_a = sim.get_agent_relationships(id_a).expect("id_a still alive");
    assert_eq!(rels_a.len(), 0, "live side bond removed by RemoveSymmetric with dead partner");
    // id_b is dead — get_agent_relationships should return None for it
    assert!(sim.get_agent_relationships(id_b).is_none(), "dead agent returns None");
}

// Test 6: get_agent_relationships returns all bond types
#[test]
fn test_get_agent_relationships_all_bond_types() {
    let (mut sim, id_a, id_b) = make_sim_with_two_agents();

    // Mentor (asymmetric, 0), Rival (1), ExileBond (3), CoReligionist (4), Kin (5)
    // We add four directed bonds from id_a to id_b with distinct bond types
    let batch = make_ops_batch(&[
        (0, id_a, id_b, 0, 60, 1),  // UpsertDirected Mentor
        (0, id_a, id_b, 1, -20, 2), // UpsertDirected Rival
        (0, id_a, id_b, 3, 40, 3),  // UpsertDirected ExileBond
        (0, id_a, id_b, 4, 50, 4),  // UpsertDirected CoReligionist
    ]);
    sim.apply_relationship_ops(batch).unwrap();

    let rels = sim.get_agent_relationships(id_a).expect("agent must exist");
    assert_eq!(rels.len(), 4, "all four bond types must be stored");

    let bond_types: std::collections::HashSet<u8> = rels.iter().map(|r| r.2).collect();
    assert!(bond_types.contains(&0), "Mentor bond must be present");
    assert!(bond_types.contains(&1), "Rival bond must be present");
    assert!(bond_types.contains(&3), "ExileBond must be present");
    assert!(bond_types.contains(&4), "CoReligionist must be present");
}

// ---------------------------------------------------------------------------
// V9: Initial spawn packed stream regression tests
// ---------------------------------------------------------------------------

#[test]
fn test_spawn_stream_packing_distinct_per_region() {
    // V9: Verify that packed stream IDs for personality and age RNG
    // produce distinct values for different regions (turn=0 at initial spawn).
    let personality_r0 = ((0u64) << 48) | crate::agent::PERSONALITY_STREAM_OFFSET;
    let personality_r1 = ((1u64) << 48) | crate::agent::PERSONALITY_STREAM_OFFSET;
    let personality_r2 = ((2u64) << 48) | crate::agent::PERSONALITY_STREAM_OFFSET;
    let age_r0 = ((0u64) << 48) | crate::agent::INITIAL_AGE_STREAM_OFFSET;
    let age_r1 = ((1u64) << 48) | crate::agent::INITIAL_AGE_STREAM_OFFSET;

    // Different regions produce different stream IDs
    assert_ne!(personality_r0, personality_r1);
    assert_ne!(personality_r1, personality_r2);
    assert_ne!(age_r0, age_r1);

    // Personality and age streams don't collide in the same region
    assert_ne!(personality_r0, age_r0);
    assert_ne!(personality_r1, age_r1);
}

#[test]
fn test_spawn_stream_packing_deterministic_rng() {
    // V9: Verify that initial spawn RNG with packed streams produces
    // deterministic, region-differentiated results.
    use rand::SeedableRng;
    use rand::Rng;
    use rand_chacha::ChaCha8Rng;

    let seed = [42u8; 32];

    let gen_personality = |region_id: u64| -> [f32; 3] {
        let mut rng = ChaCha8Rng::from_seed(seed);
        rng.set_stream((region_id << 48) | crate::agent::PERSONALITY_STREAM_OFFSET);
        [rng.gen::<f32>(), rng.gen::<f32>(), rng.gen::<f32>()]
    };

    // Same region, same seed → same result (deterministic)
    assert_eq!(gen_personality(0), gen_personality(0));
    assert_eq!(gen_personality(5), gen_personality(5));

    // Different regions → different results
    assert_ne!(gen_personality(0), gen_personality(1));
    assert_ne!(gen_personality(1), gen_personality(2));
}
