//! Parse per-tick signals from Python Arrow RecordBatches into typed Rust structs.

use arrow::array::{BooleanArray, Float32Array, UInt8Array};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

#[inline]
fn read_optional_f32_unit_signal(
    column: Option<&Float32Array>,
    field_name: &str,
    row_idx: usize,
) -> Result<f32, ArrowError> {
    let value = column.map(|c| c.value(row_idx)).unwrap_or(0.0);
    if !value.is_finite() {
        return Err(ArrowError::InvalidArgumentError(format!(
            "{field_name} row {row_idx} must be finite, got {value}"
        )));
    }
    if !(-1.0..=1.0).contains(&value) {
        return Err(ArrowError::InvalidArgumentError(format!(
            "{field_name} row {row_idx} must be in [-1.0, 1.0], got {value}"
        )));
    }
    Ok(value)
}

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
    pub faction_clergy: f32,
    // M27 additions:
    pub shock_stability: f32,
    pub shock_economy: f32,
    pub shock_military: f32,
    pub shock_culture: f32,
    pub demand_shift_farmer: f32,
    pub demand_shift_soldier: f32,
    pub demand_shift_merchant: f32,
    pub demand_shift_scholar: f32,
    pub demand_shift_priest: f32,
    // M33 personality means (immutable per-civ):
    pub mean_boldness: f32,
    pub mean_ambition: f32,
    pub mean_loyalty_trait: f32,
    // M41: Wealth & Class Stratification
    pub gini_coefficient: f32,
    pub conquered_this_turn: bool,
    // M42: Priest tithe share
    pub priest_tithe_share: f32,
    // M47: Tuning multipliers
    pub cultural_drift_multiplier: f32,
    pub religion_intensity_multiplier: f32,
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

    // M38a optional column — default to 0.0 if absent
    let faction_clergy_col = batch
        .column_by_name("faction_clergy")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());

    // M27 optional columns — default to 0.0 if absent
    let shock_stability_col = batch.column_by_name("shock_stability")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let shock_economy_col = batch.column_by_name("shock_economy")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let shock_military_col = batch.column_by_name("shock_military")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let shock_culture_col = batch.column_by_name("shock_culture")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let demand_farmer_col = batch.column_by_name("demand_shift_farmer")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let demand_soldier_col = batch.column_by_name("demand_shift_soldier")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let demand_merchant_col = batch.column_by_name("demand_shift_merchant")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let demand_scholar_col = batch.column_by_name("demand_shift_scholar")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let demand_priest_col = batch.column_by_name("demand_shift_priest")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let mean_boldness_col = batch.column_by_name("mean_boldness")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let mean_ambition_col = batch.column_by_name("mean_ambition")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let mean_loyalty_trait_col = batch.column_by_name("mean_loyalty_trait")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let gini_coefficient_col = batch.column_by_name("gini_coefficient")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let conquered_this_turn_col = batch.column_by_name("conquered_this_turn")
        .and_then(|c| c.as_any().downcast_ref::<BooleanArray>());
    let priest_tithe_share_col = batch.column_by_name("priest_tithe_share")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let cultural_drift_multiplier_col = batch.column_by_name("cultural_drift_multiplier")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
    let religion_intensity_multiplier_col = batch.column_by_name("religion_intensity_multiplier")
        .and_then(|c| c.as_any().downcast_ref::<Float32Array>());

    let mut result = Vec::with_capacity(batch.num_rows());
    for i in 0..batch.num_rows() {
        let shock_stability = read_optional_f32_unit_signal(shock_stability_col, "shock_stability", i)?;
        let shock_economy = read_optional_f32_unit_signal(shock_economy_col, "shock_economy", i)?;
        let shock_military = read_optional_f32_unit_signal(shock_military_col, "shock_military", i)?;
        let shock_culture = read_optional_f32_unit_signal(shock_culture_col, "shock_culture", i)?;
        result.push(CivSignals {
            civ_id: civ_ids.value(i),
            stability: stabilities.value(i),
            is_at_war: at_wars.value(i),
            dominant_faction: dom_factions.value(i),
            faction_military: fac_mil.value(i),
            faction_merchant: fac_mer.value(i),
            faction_cultural: fac_cul.value(i),
            faction_clergy: faction_clergy_col.map_or(0.0, |c| c.value(i)),
            shock_stability,
            shock_economy,
            shock_military,
            shock_culture,
            demand_shift_farmer: demand_farmer_col.map(|a| a.value(i)).unwrap_or(0.0),
            demand_shift_soldier: demand_soldier_col.map(|a| a.value(i)).unwrap_or(0.0),
            demand_shift_merchant: demand_merchant_col.map(|a| a.value(i)).unwrap_or(0.0),
            demand_shift_scholar: demand_scholar_col.map(|a| a.value(i)).unwrap_or(0.0),
            demand_shift_priest: demand_priest_col.map(|a| a.value(i)).unwrap_or(0.0),
            mean_boldness: mean_boldness_col.map(|a| a.value(i)).unwrap_or(0.0),
            mean_ambition: mean_ambition_col.map(|a| a.value(i)).unwrap_or(0.0),
            mean_loyalty_trait: mean_loyalty_trait_col.map(|a| a.value(i)).unwrap_or(0.0),
            gini_coefficient: gini_coefficient_col.map(|a| a.value(i)).unwrap_or(0.0),
            conquered_this_turn: conquered_this_turn_col.map(|a| a.value(i)).unwrap_or(false),
            priest_tithe_share: priest_tithe_share_col.map(|a| a.value(i)).unwrap_or(0.0),
            cultural_drift_multiplier: cultural_drift_multiplier_col.map(|a| a.value(i)).unwrap_or(1.0),
            religion_intensity_multiplier: religion_intensity_multiplier_col.map(|a| a.value(i)).unwrap_or(1.0),
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

/// Aggregated shock values for a single civilization.
///
/// Sign contract across the Python/Rust boundary:
///   - negative values are harmful shocks that reduce satisfaction
///   - positive values are beneficial shocks that increase satisfaction
/// Each component is normalized to the closed range `[-1.0, 1.0]`.
#[derive(Clone, Debug, Default)]
pub struct CivShock {
    pub stability: f32,
    pub economy: f32,
    pub military: f32,
    pub culture: f32,
}

/// O(1) civ_id-to-index lookup table built once per tick (H-29 audit).
/// Maps civ_id (u8) to index in TickSignals.civs. None = civ not present.
pub struct CivSignalsIndex {
    table: [Option<usize>; 256],
}

impl CivSignalsIndex {
    /// Build from a TickSignals reference. O(n) where n = number of civs.
    pub fn build(signals: &TickSignals) -> Self {
        let mut table = [None; 256];
        for (idx, cs) in signals.civs.iter().enumerate() {
            table[cs.civ_id as usize] = Some(idx);
        }
        CivSignalsIndex { table }
    }

    /// O(1) lookup of CivSignals by civ_id.
    #[inline]
    pub fn get<'a>(&self, signals: &'a TickSignals, civ_id: u8) -> Option<&'a CivSignals> {
        self.table[civ_id as usize].map(|idx| &signals.civs[idx])
    }
}

impl TickSignals {
    /// Build an O(1) index for civ_id lookups. Call once per tick, then use
    /// `index.get(signals, civ_id)` in hot loops instead of linear scan.
    pub fn build_index(&self) -> CivSignalsIndex {
        CivSignalsIndex::build(self)
    }

    /// Look up the shock components for the given civ, defaulting to zeros.
    pub fn shock_for_civ(&self, civ_id: u8) -> CivShock {
        self.civs
            .iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| CivShock {
                stability: c.shock_stability,
                economy: c.shock_economy,
                military: c.shock_military,
                culture: c.shock_culture,
            })
            .unwrap_or_default()
    }

    /// O(1) shock lookup using pre-built index.
    pub fn shock_for_civ_indexed(&self, civ_id: u8, idx: &CivSignalsIndex) -> CivShock {
        idx.get(self, civ_id)
            .map(|c| CivShock {
                stability: c.shock_stability,
                economy: c.shock_economy,
                military: c.shock_military,
                culture: c.shock_culture,
            })
            .unwrap_or_default()
    }

    /// Demand-shift array [farmer, soldier, merchant, scholar, priest] for the
    /// given civ, defaulting to zeros.
    pub fn demand_shifts_for_civ(&self, civ_id: u8) -> [f32; 5] {
        self.civs
            .iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| [
                c.demand_shift_farmer,
                c.demand_shift_soldier,
                c.demand_shift_merchant,
                c.demand_shift_scholar,
                c.demand_shift_priest,
            ])
            .unwrap_or([0.0; 5])
    }

    /// Personality mean [boldness, ambition, loyalty_trait] for the given civ.
    pub fn personality_mean_for_civ(&self, civ_id: u8) -> [f32; 3] {
        self.civs
            .iter()
            .find(|c| c.civ_id == civ_id)
            .map(|c| [c.mean_boldness, c.mean_ambition, c.mean_loyalty_trait])
            .unwrap_or([0.0; 3])
    }
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

    fn make_full_civ_signals_batch() -> RecordBatch {
        RecordBatch::try_from_iter(vec![
            ("civ_id", Arc::new(UInt8Array::from(vec![0u8])) as _),
            ("stability", Arc::new(UInt8Array::from(vec![75u8])) as _),
            ("is_at_war", Arc::new(BooleanArray::from(vec![true])) as _),
            ("dominant_faction", Arc::new(UInt8Array::from(vec![1u8])) as _),
            ("faction_military", Arc::new(Float32Array::from(vec![0.5f32])) as _),
            ("faction_merchant", Arc::new(Float32Array::from(vec![0.3f32])) as _),
            ("faction_cultural", Arc::new(Float32Array::from(vec![0.2f32])) as _),
            ("shock_stability", Arc::new(Float32Array::from(vec![-0.25f32])) as _),
            ("shock_economy", Arc::new(Float32Array::from(vec![-0.1f32])) as _),
            ("shock_military", Arc::new(Float32Array::from(vec![0.0f32])) as _),
            ("shock_culture", Arc::new(Float32Array::from(vec![0.15f32])) as _),
            ("demand_shift_farmer", Arc::new(Float32Array::from(vec![0.0f32])) as _),
            ("demand_shift_soldier", Arc::new(Float32Array::from(vec![0.17f32])) as _),
            ("demand_shift_merchant", Arc::new(Float32Array::from(vec![0.0f32])) as _),
            ("demand_shift_scholar", Arc::new(Float32Array::from(vec![0.0f32])) as _),
            ("demand_shift_priest", Arc::new(Float32Array::from(vec![0.0f32])) as _),
        ]).unwrap()
    }

    #[test]
    fn test_parse_extended_civ_signals() {
        let batch = make_full_civ_signals_batch();
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs.len(), 1);
        assert_eq!(civs[0].civ_id, 0);
        assert_eq!(civs[0].stability, 75);
        assert!(civs[0].is_at_war);
        assert_eq!(civs[0].dominant_faction, 1);
        assert!((civs[0].faction_military - 0.5).abs() < 0.01);
        assert!((civs[0].faction_merchant - 0.3).abs() < 0.01);
        assert!((civs[0].faction_cultural - 0.2).abs() < 0.01);
        // M27 shock fields
        assert!((civs[0].shock_stability - (-0.25)).abs() < 0.01);
        assert!((civs[0].shock_economy - (-0.1)).abs() < 0.01);
        assert!((civs[0].shock_military - 0.0).abs() < 0.01);
        assert!((civs[0].shock_culture - 0.15).abs() < 0.01);
        // M27 demand shift fields
        assert!((civs[0].demand_shift_farmer - 0.0).abs() < 0.01);
        assert!((civs[0].demand_shift_soldier - 0.17).abs() < 0.01);
        assert!((civs[0].demand_shift_merchant - 0.0).abs() < 0.01);
        assert!((civs[0].demand_shift_scholar - 0.0).abs() < 0.01);
        assert!((civs[0].demand_shift_priest - 0.0).abs() < 0.01);

        // Test accessors via TickSignals
        let ts = TickSignals { civs, contested_regions: vec![] };
        let shock = ts.shock_for_civ(0);
        assert!((shock.stability - (-0.25)).abs() < 0.01);
        assert!((shock.economy - (-0.1)).abs() < 0.01);
        assert!((shock.military - 0.0).abs() < 0.01);
        assert!((shock.culture - 0.15).abs() < 0.01);

        let demand = ts.demand_shifts_for_civ(0);
        assert!((demand[0] - 0.0).abs() < 0.01);
        assert!((demand[1] - 0.17).abs() < 0.01);
        assert!((demand[2] - 0.0).abs() < 0.01);
        assert!((demand[3] - 0.0).abs() < 0.01);
        assert!((demand[4] - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_parse_m41_signals() {
        let batch = RecordBatch::try_from_iter(vec![
            ("civ_id", Arc::new(UInt8Array::from(vec![0u8])) as _),
            ("stability", Arc::new(UInt8Array::from(vec![50u8])) as _),
            ("is_at_war", Arc::new(BooleanArray::from(vec![false])) as _),
            ("dominant_faction", Arc::new(UInt8Array::from(vec![0u8])) as _),
            ("faction_military", Arc::new(Float32Array::from(vec![0.33f32])) as _),
            ("faction_merchant", Arc::new(Float32Array::from(vec![0.33f32])) as _),
            ("faction_cultural", Arc::new(Float32Array::from(vec![0.34f32])) as _),
            ("gini_coefficient", Arc::new(Float32Array::from(vec![0.45f32])) as _),
            ("conquered_this_turn", Arc::new(BooleanArray::from(vec![true])) as _),
        ]).unwrap();
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs.len(), 1);
        assert!((civs[0].gini_coefficient - 0.45).abs() < 0.001);
        assert!(civs[0].conquered_this_turn);
    }

    #[test]
    fn test_m41_signals_default_when_absent() {
        let batch = make_civ_batch(); // existing helper — no M41 columns
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs[0].gini_coefficient, 0.0);
        assert!(!civs[0].conquered_this_turn);
    }

    #[test]
    fn test_backward_compatible_without_m27_columns() {
        // Use the original M26 batch (no shock/demand columns)
        let batch = make_civ_batch();
        let civs = parse_civ_signals(&batch).unwrap();
        assert_eq!(civs.len(), 2);
        // All M27 fields should default to 0.0
        for c in &civs {
            assert_eq!(c.shock_stability, 0.0);
            assert_eq!(c.shock_economy, 0.0);
            assert_eq!(c.shock_military, 0.0);
            assert_eq!(c.shock_culture, 0.0);
            assert_eq!(c.demand_shift_farmer, 0.0);
            assert_eq!(c.demand_shift_soldier, 0.0);
            assert_eq!(c.demand_shift_merchant, 0.0);
            assert_eq!(c.demand_shift_scholar, 0.0);
            assert_eq!(c.demand_shift_priest, 0.0);
        }

        // Accessors on missing civ should also return zeros
        let ts = TickSignals { civs, contested_regions: vec![] };
        let shock = ts.shock_for_civ(99);
        assert_eq!(shock.stability, 0.0);
        assert_eq!(shock.economy, 0.0);
        let demand = ts.demand_shifts_for_civ(99);
        assert_eq!(demand, [0.0; 5]);
    }

    // H-29 regression: CivSignalsIndex O(1) lookup produces same results as linear scan
    #[test]
    fn test_civ_signals_index_parity() {
        let batch = make_civ_batch();
        let civs = parse_civ_signals(&batch).unwrap();
        let ts = TickSignals { civs, contested_regions: vec![] };
        let idx = ts.build_index();

        // Existing civs: indexed lookup matches linear scan
        for civ_id in [0u8, 1] {
            let linear = ts.shock_for_civ(civ_id);
            let indexed = ts.shock_for_civ_indexed(civ_id, &idx);
            assert_eq!(linear.stability, indexed.stability);
            assert_eq!(linear.economy, indexed.economy);

            let linear_sig = ts.civs.iter().find(|c| c.civ_id == civ_id);
            let indexed_sig = idx.get(&ts, civ_id);
            assert_eq!(linear_sig.map(|c| c.stability), indexed_sig.map(|c| c.stability));
            assert_eq!(linear_sig.map(|c| c.is_at_war), indexed_sig.map(|c| c.is_at_war));
        }

        // Missing civ: indexed lookup returns None / default
        assert!(idx.get(&ts, 99).is_none());
        let missing_shock = ts.shock_for_civ_indexed(99, &idx);
        assert_eq!(missing_shock.stability, 0.0);
    }

    #[test]
    fn test_parse_civ_signals_rejects_out_of_range_shocks() {
        let batch = RecordBatch::try_from_iter(vec![
            ("civ_id", Arc::new(UInt8Array::from(vec![0u8])) as _),
            ("stability", Arc::new(UInt8Array::from(vec![50u8])) as _),
            ("is_at_war", Arc::new(BooleanArray::from(vec![false])) as _),
            ("dominant_faction", Arc::new(UInt8Array::from(vec![0u8])) as _),
            ("faction_military", Arc::new(Float32Array::from(vec![0.33f32])) as _),
            ("faction_merchant", Arc::new(Float32Array::from(vec![0.33f32])) as _),
            ("faction_cultural", Arc::new(Float32Array::from(vec![0.34f32])) as _),
            ("shock_stability", Arc::new(Float32Array::from(vec![1.25f32])) as _),
        ])
        .unwrap();

        let err = parse_civ_signals(&batch).unwrap_err();
        assert!(
            err.to_string().contains("shock_stability"),
            "unexpected error: {err}"
        );
    }
}
