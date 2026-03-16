//! Parse per-tick signals from Python Arrow RecordBatches into typed Rust structs.

use arrow::array::{BooleanArray, Float32Array, UInt8Array};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

/// Per-civ signals from Python aggregate model.
#[derive(Clone, Debug)]
pub struct CivSignals {
    pub civ_id: u8,
    pub stability: u8,
    pub is_at_war: bool,
    pub dominant_faction: u8,   // 0=military, 1=merchant, 2=cultural
    pub faction_military: f32,
    pub faction_merchant: f32,
    pub faction_cultural: f32,
}

/// Parsed signals for one tick.
#[derive(Clone, Debug)]
pub struct TickSignals {
    pub civs: Vec<CivSignals>,
    pub contested_regions: Vec<bool>,
}

/// Parse a civ-signals Arrow RecordBatch into Vec<CivSignals>.
pub fn parse_civ_signals(batch: &RecordBatch) -> Result<Vec<CivSignals>, ArrowError> {
    let civ_ids = batch.column_by_name("civ_id")
        .ok_or_else(|| ArrowError::SchemaError("missing civ_id".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("civ_id not UInt8".into()))?;
    let stabilities = batch.column_by_name("stability")
        .ok_or_else(|| ArrowError::SchemaError("missing stability".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("stability not UInt8".into()))?;
    let at_wars = batch.column_by_name("is_at_war")
        .ok_or_else(|| ArrowError::SchemaError("missing is_at_war".into()))?
        .as_any().downcast_ref::<BooleanArray>()
        .ok_or_else(|| ArrowError::CastError("is_at_war not Boolean".into()))?;
    let dom_factions = batch.column_by_name("dominant_faction")
        .ok_or_else(|| ArrowError::SchemaError("missing dominant_faction".into()))?
        .as_any().downcast_ref::<UInt8Array>()
        .ok_or_else(|| ArrowError::CastError("dominant_faction not UInt8".into()))?;
    let fac_mil = batch.column_by_name("faction_military")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_military".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_military not Float32".into()))?;
    let fac_mer = batch.column_by_name("faction_merchant")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_merchant".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_merchant not Float32".into()))?;
    let fac_cul = batch.column_by_name("faction_cultural")
        .ok_or_else(|| ArrowError::SchemaError("missing faction_cultural".into()))?
        .as_any().downcast_ref::<Float32Array>()
        .ok_or_else(|| ArrowError::CastError("faction_cultural not Float32".into()))?;

    let mut result = Vec::with_capacity(batch.num_rows());
    for i in 0..batch.num_rows() {
        result.push(CivSignals {
            civ_id: civ_ids.value(i),
            stability: stabilities.value(i),
            is_at_war: at_wars.value(i),
            dominant_faction: dom_factions.value(i),
            faction_military: fac_mil.value(i),
            faction_merchant: fac_mer.value(i),
            faction_cultural: fac_cul.value(i),
        });
    }
    Ok(result)
}

/// Build contested_regions from the extended region state batch.
/// Reads the `is_contested` Boolean column. Returns vec of false if column absent.
pub fn parse_contested_regions(batch: &RecordBatch, num_regions: usize) -> Vec<bool> {
    let mut result = vec![false; num_regions];
    if let Some(col) = batch.column_by_name("is_contested") {
        if let Some(arr) = col.as_any().downcast_ref::<BooleanArray>() {
            for i in 0..arr.len().min(num_regions) {
                result[i] = arr.value(i);
            }
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use arrow::array::{BooleanBuilder, Float32Builder, UInt8Builder};
    use arrow::datatypes::{DataType, Field, Schema};

    fn make_civ_batch() -> RecordBatch {
        let schema = Arc::new(Schema::new(vec![
            Field::new("civ_id", DataType::UInt8, false),
            Field::new("stability", DataType::UInt8, false),
            Field::new("is_at_war", DataType::Boolean, false),
            Field::new("dominant_faction", DataType::UInt8, false),
            Field::new("faction_military", DataType::Float32, false),
            Field::new("faction_merchant", DataType::Float32, false),
            Field::new("faction_cultural", DataType::Float32, false),
        ]));
        let mut civ_ids = UInt8Builder::new();
        let mut stabilities = UInt8Builder::new();
        let mut at_wars = BooleanBuilder::new();
        let mut dom_factions = UInt8Builder::new();
        let mut fac_mil = Float32Builder::new();
        let mut fac_mer = Float32Builder::new();
        let mut fac_cul = Float32Builder::new();

        civ_ids.append_value(0); stabilities.append_value(70);
        at_wars.append_value(true); dom_factions.append_value(0);
        fac_mil.append_value(0.5); fac_mer.append_value(0.3); fac_cul.append_value(0.2);

        civ_ids.append_value(1); stabilities.append_value(30);
        at_wars.append_value(false); dom_factions.append_value(1);
        fac_mil.append_value(0.2); fac_mer.append_value(0.5); fac_cul.append_value(0.3);

        RecordBatch::try_new(schema, vec![
            Arc::new(civ_ids.finish()), Arc::new(stabilities.finish()),
            Arc::new(at_wars.finish()), Arc::new(dom_factions.finish()),
            Arc::new(fac_mil.finish()), Arc::new(fac_mer.finish()),
            Arc::new(fac_cul.finish()),
        ]).unwrap()
    }

    #[test]
    fn test_parse_civ_signals() {
        let batch = make_civ_batch();
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs.len(), 2);
        assert_eq!(civs[0].civ_id, 0);
        assert_eq!(civs[0].stability, 70);
        assert!(civs[0].is_at_war);
        assert_eq!(civs[0].dominant_faction, 0);
        assert!((civs[0].faction_military - 0.5).abs() < 0.01);
        assert_eq!(civs[1].civ_id, 1);
        assert!(!civs[1].is_at_war);
        assert_eq!(civs[1].dominant_faction, 1);
    }

    #[test]
    fn test_parse_contested_regions() {
        let schema = Arc::new(Schema::new(vec![
            Field::new("is_contested", DataType::Boolean, false),
        ]));
        let mut contested = BooleanBuilder::new();
        contested.append_value(false);
        contested.append_value(true);
        contested.append_value(false);
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(contested.finish()),
        ]).unwrap();
        let result = parse_contested_regions(&batch, 3);
        assert_eq!(result, vec![false, true, false]);
    }

    #[test]
    fn test_parse_contested_regions_missing_column() {
        let schema = Arc::new(Schema::new(vec![
            Field::new("other_col", DataType::UInt8, false),
        ]));
        let mut other = UInt8Builder::new();
        other.append_value(0);
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(other.finish()),
        ]).unwrap();
        let result = parse_contested_regions(&batch, 3);
        assert_eq!(result, vec![false, false, false]);
    }
}
