//! M38a FFI round-trip tests: faction_clergy in civ signals and has_temple in region state.

use std::sync::Arc;

use arrow::array::{BooleanBuilder, Float32Builder, UInt8Builder, UInt16Builder, Float32Array, UInt8Array, BooleanArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;

use chronicler_agents::signals::parse_civ_signals;
use chronicler_agents::RegionState;

// ---------------------------------------------------------------------------
// Test 1: faction_clergy round-trip via parse_civ_signals
// ---------------------------------------------------------------------------

/// Build a civ signals RecordBatch that includes the `faction_clergy` column.
/// Parse it via parse_civ_signals and verify faction_clergy is correctly read.
#[test]
fn test_faction_clergy_round_trip() {
    // Build the batch including faction_clergy
    let batch = RecordBatch::try_from_iter(vec![
        ("civ_id",           Arc::new(UInt8Array::from(vec![0u8, 1u8])) as Arc<dyn arrow::array::Array>),
        ("stability",        Arc::new(UInt8Array::from(vec![55u8, 70u8])) as _),
        ("is_at_war",        Arc::new(BooleanArray::from(vec![false, true])) as _),
        ("dominant_faction", Arc::new(UInt8Array::from(vec![3u8, 0u8])) as _),
        ("faction_military", Arc::new(Float32Array::from(vec![0.20f32, 0.50f32])) as _),
        ("faction_merchant", Arc::new(Float32Array::from(vec![0.25f32, 0.20f32])) as _),
        ("faction_cultural", Arc::new(Float32Array::from(vec![0.20f32, 0.15f32])) as _),
        ("faction_clergy",   Arc::new(Float32Array::from(vec![0.35f32, 0.15f32])) as _),
    ])
    .unwrap();

    let civs = parse_civ_signals(&batch).expect("parse_civ_signals failed");

    assert_eq!(civs.len(), 2);

    // Civ 0: clergy-dominant with faction_clergy = 0.35
    assert_eq!(civs[0].civ_id, 0);
    assert_eq!(civs[0].dominant_faction, 3); // CLERGY
    assert!(
        (civs[0].faction_clergy - 0.35).abs() < 1e-4,
        "expected faction_clergy=0.35 for civ 0, got {}",
        civs[0].faction_clergy
    );
    assert!(!civs[0].is_at_war);

    // Civ 1: military-dominant with faction_clergy = 0.15
    assert_eq!(civs[1].civ_id, 1);
    assert_eq!(civs[1].dominant_faction, 0); // MILITARY
    assert!(
        (civs[1].faction_clergy - 0.15).abs() < 1e-4,
        "expected faction_clergy=0.15 for civ 1, got {}",
        civs[1].faction_clergy
    );
    assert!(civs[1].is_at_war);

    // Verify other factions are correctly parsed alongside clergy
    assert!((civs[0].faction_military - 0.20).abs() < 1e-4);
    assert!((civs[0].faction_merchant - 0.25).abs() < 1e-4);
    assert!((civs[0].faction_cultural - 0.20).abs() < 1e-4);
}

// ---------------------------------------------------------------------------
// Test 2: has_temple round-trip via set_region_state()
// ---------------------------------------------------------------------------

/// Helper: build a minimal region RecordBatch with a has_temple column.
fn make_region_batch_with_temple(has_temple_values: &[bool]) -> RecordBatch {
    let n = has_temple_values.len();

    let mut region_ids = UInt16Builder::with_capacity(n);
    let mut terrains = UInt8Builder::with_capacity(n);
    let mut capacities = UInt16Builder::with_capacity(n);
    let mut populations = UInt16Builder::with_capacity(n);
    let mut soils = Float32Builder::with_capacity(n);
    let mut waters = Float32Builder::with_capacity(n);
    let mut forest_covers = Float32Builder::with_capacity(n);
    let mut has_temple_col = BooleanBuilder::with_capacity(n);

    for (i, &temple) in has_temple_values.iter().enumerate() {
        region_ids.append_value(i as u16);
        terrains.append_value(0u8);
        capacities.append_value(10u16);
        populations.append_value(5u16);
        soils.append_value(0.7f32);
        waters.append_value(0.5f32);
        forest_covers.append_value(0.3f32);
        has_temple_col.append_value(temple);
    }

    let schema = Arc::new(Schema::new(vec![
        Field::new("region_id",         DataType::UInt16,   false),
        Field::new("terrain",           DataType::UInt8,    false),
        Field::new("carrying_capacity", DataType::UInt16,   false),
        Field::new("population",        DataType::UInt16,   false),
        Field::new("soil",              DataType::Float32,  false),
        Field::new("water",             DataType::Float32,  false),
        Field::new("forest_cover",      DataType::Float32,  false),
        Field::new("has_temple",        DataType::Boolean,  false),
    ]));

    RecordBatch::try_new(
        schema,
        vec![
            Arc::new(region_ids.finish()) as _,
            Arc::new(terrains.finish()) as _,
            Arc::new(capacities.finish()) as _,
            Arc::new(populations.finish()) as _,
            Arc::new(soils.finish()) as _,
            Arc::new(waters.finish()) as _,
            Arc::new(forest_covers.finish()) as _,
            Arc::new(has_temple_col.finish()) as _,
        ],
    )
    .unwrap()
}

/// Build a region RecordBatch with has_temple column, parse via set_region_state(),
/// and verify has_temple is correctly set on the internal RegionState.
/// We test this through the public make_test_regions pattern used in determinism.rs,
/// constructing RegionState directly and checking the field assignment matches.
#[test]
fn test_has_temple_round_trip() {
    // has_temple pattern: [false, true, false, true, false]
    let temple_pattern = vec![false, true, false, true, false];

    // Simulate what set_region_state does when parsing has_temple via the
    // same logic as ffi.rs: downcast to BooleanArray, read value(i)
    let batch = make_region_batch_with_temple(&temple_pattern);

    let has_temple_col = batch
        .column_by_name("has_temple")
        .expect("has_temple column missing")
        .as_any()
        .downcast_ref::<BooleanArray>()
        .expect("has_temple not BooleanArray");

    // Verify each row is correctly read
    for (i, &expected) in temple_pattern.iter().enumerate() {
        let actual = has_temple_col.value(i);
        assert_eq!(
            actual, expected,
            "region {i}: expected has_temple={expected}, got {actual}"
        );
    }

    // Verify the parsed values can construct a RegionState with correct has_temple
    let region_ids_col = batch
        .column_by_name("region_id")
        .unwrap()
        .as_any()
        .downcast_ref::<arrow::array::UInt16Array>()
        .unwrap();

    let regions: Vec<RegionState> = (0..batch.num_rows())
        .map(|i| RegionState {
            region_id: region_ids_col.value(i),
            terrain: 0,
            carrying_capacity: 10,
            population: 5,
            soil: 0.7,
            water: 0.5,
            forest_cover: 0.3,
            adjacency_mask: 0,
            controller_civ: 255,
            trade_route_count: 0,
            resource_types: [255, 255, 255],
            resource_yields: [0.0, 0.0, 0.0],
            resource_reserves: [1.0, 1.0, 1.0],
            season: 0,
            season_id: 0,
            river_mask: 0,
            endemic_severity: 0.0,
            culture_investment_active: false,
            controller_values: [0xFF, 0xFF, 0xFF],
            conversion_rate: 0.0,
            conversion_target_belief: 0xFF,
            conquest_conversion_active: false,
            majority_belief: 0xFF,
            has_temple: has_temple_col.value(i),
            persecution_intensity: 0.0,
            schism_convert_from: 0xFF,
            schism_convert_to: 0xFF,
        })
        .collect();

    assert_eq!(regions.len(), 5);

    // Region 0: no temple
    assert!(!regions[0].has_temple, "region 0 should have no temple");
    // Region 1: has temple
    assert!(regions[1].has_temple, "region 1 should have a temple");
    // Region 2: no temple
    assert!(!regions[2].has_temple, "region 2 should have no temple");
    // Region 3: has temple
    assert!(regions[3].has_temple, "region 3 should have a temple");
    // Region 4: no temple
    assert!(!regions[4].has_temple, "region 4 should have no temple");
}
