//! Arrow FFI layer: centralized schemas and the AgentSimulator PyO3 class.

use std::sync::Arc;

use arrow::array::{Int8Builder, UInt8Builder, UInt16Builder, UInt32Builder, StringBuilder};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::agent::{Occupation, PERSONALITY_LABEL_THRESHOLD};
use crate::pool::AgentPool;
use crate::region::RegionState;

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------

/// Convert an Arrow error into a PyErr.
pub fn arrow_err(e: ArrowError) -> PyErr {
    PyValueError::new_err(e.to_string())
}

// ---------------------------------------------------------------------------
// Personality label helper
// ---------------------------------------------------------------------------

/// Derive a narrative label from the dominant personality dimension.
/// Returns None if all dimensions are below threshold (neutral personality).
pub fn personality_label(boldness: f32, ambition: f32, loyalty_trait: f32) -> Option<&'static str> {
    let dims: [(f32, f32, &str, &str); 3] = [
        (boldness.abs(),      boldness,      "the Bold",      "the Cautious"),
        (ambition.abs(),      ambition,      "the Ambitious",  "the Humble"),
        (loyalty_trait.abs(), loyalty_trait,  "the Steadfast",  "the Fickle"),
    ];

    let mut max_idx = 0;
    let mut max_abs = dims[0].0;
    for i in 1..3 {
        if dims[i].0 > max_abs {
            max_abs = dims[i].0;
            max_idx = i;
        }
    }

    if max_abs < PERSONALITY_LABEL_THRESHOLD {
        return None;
    }

    let (_, raw, pos, neg) = dims[max_idx];
    Some(if raw > 0.0 { pos } else { neg })
}

// ---------------------------------------------------------------------------
// Centralized schema definitions
// ---------------------------------------------------------------------------

/// Schema for `get_snapshot()` — alive agents only.
pub fn snapshot_schema() -> Schema {
    Schema::new(vec![
        Field::new("id", DataType::UInt32, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("origin_region", DataType::UInt16, false),
        Field::new("civ_affinity", DataType::UInt16, false),
        Field::new("occupation", DataType::UInt8, false),
        Field::new("loyalty", DataType::Float32, false),
        Field::new("satisfaction", DataType::Float32, false),
        Field::new("skill", DataType::Float32, false),
        Field::new("age", DataType::UInt16, false),
        Field::new("displacement_turn", DataType::UInt16, false),
        Field::new("boldness", DataType::Float32, false),
        Field::new("ambition", DataType::Float32, false),
        Field::new("loyalty_trait", DataType::Float32, false),
        Field::new("cultural_value_0", DataType::UInt8, false),
        Field::new("cultural_value_1", DataType::UInt8, false),
        Field::new("cultural_value_2", DataType::UInt8, false),
        Field::new("belief", DataType::UInt8, false),
        Field::new("parent_id", DataType::UInt32, false),
        Field::new("wealth", DataType::Float32, false),
    ])
}

/// Schema for `get_aggregates()` — per-civ stats.
pub fn aggregates_schema() -> Schema {
    Schema::new(vec![
        Field::new("civ_id", DataType::UInt16, false),
        Field::new("population", DataType::UInt32, false),
        Field::new("military", DataType::UInt32, false),
        Field::new("economy", DataType::UInt32, false),
        Field::new("culture", DataType::UInt32, false),
        Field::new("stability", DataType::UInt32, false),
    ])
}

/// Schema for `get_region_populations()` — per-region alive count.
pub fn region_populations_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("alive_count", DataType::UInt32, false),
    ])
}

/// Schema for events returned by `tick()`.
pub fn events_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_id", DataType::UInt32, false),
        Field::new("event_type", DataType::UInt8, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("target_region", DataType::UInt16, false),
        Field::new("civ_affinity", DataType::UInt16, false),
        Field::new("occupation", DataType::UInt8, false),
        Field::new("turn", DataType::UInt32, false),
    ])
}

pub fn promotions_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_id", DataType::UInt32, false),
        Field::new("role", DataType::UInt8, false),
        Field::new("trigger", DataType::UInt8, false),
        Field::new("skill", DataType::Float32, false),
        Field::new("life_events", DataType::UInt8, false),
        Field::new("origin_region", DataType::UInt16, false),
        Field::new("boldness", DataType::Float32, false),
        Field::new("ambition", DataType::Float32, false),
        Field::new("loyalty_trait", DataType::Float32, false),
        Field::new("personality_label", DataType::Utf8, true),
        Field::new("parent_id", DataType::UInt32, false),
    ])
}

pub fn social_edges_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_a", DataType::UInt32, false),
        Field::new("agent_b", DataType::UInt32, false),
        Field::new("relationship", DataType::UInt8, false),
        Field::new("formed_turn", DataType::UInt16, false),
    ])
}

/// Schema for `set_region_state()` input.
#[allow(dead_code)]
pub fn region_state_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("terrain", DataType::UInt8, false),
        Field::new("carrying_capacity", DataType::UInt16, false),
        Field::new("population", DataType::UInt16, false),
        Field::new("soil", DataType::Float32, false),
        Field::new("water", DataType::Float32, false),
        Field::new("forest_cover", DataType::Float32, false),
    ])
}

/// Schema for civ_signals input to `tick()`.
#[allow(dead_code)]
pub fn civ_signals_schema() -> Schema {
    Schema::new(vec![
        Field::new("civ_id", DataType::UInt8, false),
        Field::new("stability", DataType::UInt8, false),
        Field::new("is_at_war", DataType::Boolean, false),
        Field::new("dominant_faction", DataType::UInt8, false),
        Field::new("faction_military", DataType::Float32, false),
        Field::new("faction_merchant", DataType::Float32, false),
        Field::new("faction_cultural", DataType::Float32, false),
    ])
}

// ---------------------------------------------------------------------------
// Ecology return schemas
// ---------------------------------------------------------------------------

/// Schema for the region-state batch returned by `tick_ecology()`.
pub fn ecology_region_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("soil", DataType::Float32, false),
        Field::new("water", DataType::Float32, false),
        Field::new("forest_cover", DataType::Float32, false),
        Field::new("endemic_severity", DataType::Float32, false),
        Field::new("prev_turn_water", DataType::Float32, false),
        Field::new("soil_pressure_streak", DataType::Int32, false),
        Field::new("overextraction_streak_0", DataType::Int32, false),
        Field::new("overextraction_streak_1", DataType::Int32, false),
        Field::new("overextraction_streak_2", DataType::Int32, false),
        Field::new("resource_reserve_0", DataType::Float32, false),
        Field::new("resource_reserve_1", DataType::Float32, false),
        Field::new("resource_reserve_2", DataType::Float32, false),
        Field::new("resource_effective_yield_0", DataType::Float32, false),
        Field::new("resource_effective_yield_1", DataType::Float32, false),
        Field::new("resource_effective_yield_2", DataType::Float32, false),
        Field::new("current_turn_yield_0", DataType::Float32, false),
        Field::new("current_turn_yield_1", DataType::Float32, false),
        Field::new("current_turn_yield_2", DataType::Float32, false),
    ])
}

/// Schema for the ecology-event batch returned by `tick_ecology()`.
pub fn ecology_events_schema() -> Schema {
    Schema::new(vec![
        Field::new("event_type", DataType::UInt8, false),
        Field::new("region_id", DataType::UInt16, false),
        Field::new("slot", DataType::UInt8, false),
        Field::new("magnitude", DataType::Float32, false),
    ])
}

// ---------------------------------------------------------------------------
// Recompute context (shared between AgentSimulator and EcologySimulator)
// ---------------------------------------------------------------------------

/// Minimal context stored by `tick_ecology()` for use by `apply_region_postpass_patch()`.
/// Avoids widening the patch schema with season/climate columns.
#[derive(Clone, Debug, Default)]
struct RecomputeContext {
    turn: u32,
    climate_phase: u8,
    season_id: u8,
    valid: bool,
}

// ---------------------------------------------------------------------------
// Shared ecology helpers (used by both AgentSimulator and EcologySimulator)
// ---------------------------------------------------------------------------

/// Build region-state and ecology-event Arrow RecordBatches from ecology tick results.
fn build_ecology_batches(
    regions: &[RegionState],
    yields: &[[f32; 3]],
    events: &[crate::ecology::EcologyEvent],
) -> Result<(RecordBatch, RecordBatch), ArrowError> {
    let n = regions.len();

    // Region-state batch
    let mut region_ids = UInt16Builder::with_capacity(n);
    let mut soils = arrow::array::Float32Builder::with_capacity(n);
    let mut waters = arrow::array::Float32Builder::with_capacity(n);
    let mut forests = arrow::array::Float32Builder::with_capacity(n);
    let mut endemic_severities = arrow::array::Float32Builder::with_capacity(n);
    let mut prev_waters = arrow::array::Float32Builder::with_capacity(n);
    let mut soil_streaks = arrow::array::Int32Builder::with_capacity(n);
    let mut over_s0 = arrow::array::Int32Builder::with_capacity(n);
    let mut over_s1 = arrow::array::Int32Builder::with_capacity(n);
    let mut over_s2 = arrow::array::Int32Builder::with_capacity(n);
    let mut res0 = arrow::array::Float32Builder::with_capacity(n);
    let mut res1 = arrow::array::Float32Builder::with_capacity(n);
    let mut res2 = arrow::array::Float32Builder::with_capacity(n);
    let mut eff0 = arrow::array::Float32Builder::with_capacity(n);
    let mut eff1 = arrow::array::Float32Builder::with_capacity(n);
    let mut eff2 = arrow::array::Float32Builder::with_capacity(n);
    let mut y0 = arrow::array::Float32Builder::with_capacity(n);
    let mut y1 = arrow::array::Float32Builder::with_capacity(n);
    let mut y2 = arrow::array::Float32Builder::with_capacity(n);

    for i in 0..n {
        let r = &regions[i];
        let ys = &yields[i];
        region_ids.append_value(r.region_id);
        soils.append_value(r.soil);
        waters.append_value(r.water);
        forests.append_value(r.forest_cover);
        endemic_severities.append_value(r.endemic_severity);
        prev_waters.append_value(r.prev_turn_water);
        soil_streaks.append_value(r.soil_pressure_streak);
        over_s0.append_value(r.overextraction_streak[0]);
        over_s1.append_value(r.overextraction_streak[1]);
        over_s2.append_value(r.overextraction_streak[2]);
        res0.append_value(r.resource_reserves[0]);
        res1.append_value(r.resource_reserves[1]);
        res2.append_value(r.resource_reserves[2]);
        eff0.append_value(r.resource_effective_yield[0]);
        eff1.append_value(r.resource_effective_yield[1]);
        eff2.append_value(r.resource_effective_yield[2]);
        y0.append_value(ys[0]);
        y1.append_value(ys[1]);
        y2.append_value(ys[2]);
    }

    let region_batch = RecordBatch::try_new(
        Arc::new(ecology_region_schema()),
        vec![
            Arc::new(region_ids.finish()) as _,
            Arc::new(soils.finish()) as _,
            Arc::new(waters.finish()) as _,
            Arc::new(forests.finish()) as _,
            Arc::new(endemic_severities.finish()) as _,
            Arc::new(prev_waters.finish()) as _,
            Arc::new(soil_streaks.finish()) as _,
            Arc::new(over_s0.finish()) as _,
            Arc::new(over_s1.finish()) as _,
            Arc::new(over_s2.finish()) as _,
            Arc::new(res0.finish()) as _,
            Arc::new(res1.finish()) as _,
            Arc::new(res2.finish()) as _,
            Arc::new(eff0.finish()) as _,
            Arc::new(eff1.finish()) as _,
            Arc::new(eff2.finish()) as _,
            Arc::new(y0.finish()) as _,
            Arc::new(y1.finish()) as _,
            Arc::new(y2.finish()) as _,
        ],
    )?;

    // Ecology-event batch (already sorted by ecology.rs)
    let ne = events.len();
    let mut evt_types = UInt8Builder::with_capacity(ne);
    let mut evt_regions = UInt16Builder::with_capacity(ne);
    let mut evt_slots = UInt8Builder::with_capacity(ne);
    let mut evt_magnitudes = arrow::array::Float32Builder::with_capacity(ne);

    for ev in events {
        evt_types.append_value(ev.event_type);
        evt_regions.append_value(ev.region_id);
        evt_slots.append_value(ev.slot);
        evt_magnitudes.append_value(ev.magnitude);
    }

    let event_batch = RecordBatch::try_new(
        Arc::new(ecology_events_schema()),
        vec![
            Arc::new(evt_types.finish()) as _,
            Arc::new(evt_regions.finish()) as _,
            Arc::new(evt_slots.finish()) as _,
            Arc::new(evt_magnitudes.finish()) as _,
        ],
    )?;

    Ok((region_batch, event_batch))
}

/// Parse a post-pass patch batch and apply it to regions.
/// Returns the set of region indices that had ecology-affecting changes.
fn apply_patch_to_regions(
    regions: &mut [RegionState],
    batch: &RecordBatch,
) -> Result<Vec<usize>, PyErr> {
    let n = batch.num_rows();

    macro_rules! patch_col {
        ($name:expr, $ty:ty) => {
            batch
                .column_by_name($name)
                .ok_or_else(|| PyValueError::new_err(format!("patch missing column {}", $name)))?
                .as_any()
                .downcast_ref::<$ty>()
                .ok_or_else(|| PyValueError::new_err(format!("patch column {} wrong type", $name)))?
        };
    }

    let region_ids = patch_col!("region_id", arrow::array::UInt16Array);
    let populations = patch_col!("population", arrow::array::UInt16Array);
    let soils = patch_col!("soil", arrow::array::Float32Array);
    let waters = patch_col!("water", arrow::array::Float32Array);
    let forest_covers = patch_col!("forest_cover", arrow::array::Float32Array);
    let terrains = patch_col!("terrain", arrow::array::UInt8Array);
    let capacities = patch_col!("carrying_capacity", arrow::array::UInt16Array);

    let num_regions = regions.len();
    let mut recompute_indices = Vec::new();

    for i in 0..n {
        let rid = region_ids.value(i) as usize;
        if rid >= num_regions {
            continue;
        }
        let r = &mut regions[rid];

        let new_pop = populations.value(i);
        let new_soil = soils.value(i);
        let new_water = waters.value(i);
        let new_forest = forest_covers.value(i);
        let new_terrain = terrains.value(i);
        let new_cap = capacities.value(i);

        // Detect ecology-affecting changes
        let ecology_changed = (new_soil - r.soil).abs() > f32::EPSILON
            || (new_water - r.water).abs() > f32::EPSILON
            || (new_forest - r.forest_cover).abs() > f32::EPSILON
            || new_terrain != r.terrain
            || new_cap != r.carrying_capacity;

        // Apply all patch fields
        r.population = new_pop;
        r.soil = new_soil;
        r.water = new_water;
        r.forest_cover = new_forest;
        r.terrain = new_terrain;
        r.carrying_capacity = new_cap;

        if ecology_changed {
            recompute_indices.push(rid);
        }
    }

    Ok(recompute_indices)
}

/// Recompute yields for specific regions using stored context.
fn recompute_region_yields(
    regions: &mut [RegionState],
    indices: &[usize],
    ctx: &RecomputeContext,
    config: &crate::ecology::EcologyConfig,
) {
    for &idx in indices {
        if idx < regions.len() {
            crate::ecology::compute_yields(
                &mut regions[idx],
                config,
                ctx.season_id,
                ctx.climate_phase,
            );
        }
    }
}

// ---------------------------------------------------------------------------
// AgentSimulator
// ---------------------------------------------------------------------------

/// Python-facing AgentSimulator. Manages an `AgentPool` and a list of
/// `RegionState`s; exchanges data with Python via Arrow PyCapsules.
#[pyclass]
pub struct AgentSimulator {
    pub pool: AgentPool,
    regions: Vec<RegionState>,
    contested_regions: Vec<bool>,
    master_seed: [u8; 32],
    num_regions: usize,
    turn: u32,
    registry: crate::named_characters::NamedCharacterRegistry,
    social_graph: crate::social::SocialGraph,
    initialized: bool,
    wealth_percentiles: Vec<f32>,
    #[pyo3(get)]
    pub kin_bond_failures: u32,
    formation_stats: crate::formation::FormationStats,
    prev_kin_bond_failures: u32,
    // M53: per-tick demographic counters for debug reporting
    #[pyo3(get)]
    pub last_tick_deaths: u32,
    #[pyo3(get)]
    pub last_tick_births: u32,
    #[pyo3(get)]
    pub last_tick_alive: u32,
    // M53: expanded demographic debug (collected during tick)
    demographic_debug: crate::tick::DemographicDebug,
    // M54a: ecology state
    ecology_config: crate::ecology::EcologyConfig,
    river_topology: crate::ecology::RiverTopology,
    recompute_ctx: RecomputeContext,
}

#[pymethods]
impl AgentSimulator {
    /// Create a new simulator.
    ///
    /// `seed` is zero-extended to a 32-byte master seed.
    #[new]
    pub fn new(num_regions: usize, seed: u64) -> Self {
        let mut master_seed = [0u8; 32];
        master_seed[..8].copy_from_slice(&seed.to_le_bytes());
        Self {
            pool: AgentPool::new(num_regions * 60),
            regions: Vec::new(),
            contested_regions: Vec::new(),
            master_seed,
            num_regions,
            turn: 0,
            registry: crate::named_characters::NamedCharacterRegistry::new(),
            social_graph: crate::social::SocialGraph::new(),
            initialized: false,
            wealth_percentiles: Vec::new(),
            kin_bond_failures: 0,
            formation_stats: crate::formation::FormationStats::default(),
            prev_kin_bond_failures: 0,
            last_tick_deaths: 0,
            last_tick_births: 0,
            last_tick_alive: 0,
            demographic_debug: crate::tick::DemographicDebug::default(),
            ecology_config: crate::ecology::EcologyConfig::default(),
            river_topology: crate::ecology::RiverTopology::default(),
            recompute_ctx: RecomputeContext::default(),
        }
    }

    /// Ingest region state from Python as an Arrow RecordBatch.
    ///
    /// First call initialises the regions and spawns agents from the supplied
    /// population column (60% farmer, 15% soldier, 10% merchant, 10%
    /// scholar, ~5% priest). Subsequent calls update ecology fields only.
    pub fn set_region_state(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();

        // Helper macros to extract typed columns.
        macro_rules! col_u16 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt16", $name)))?
            }};
        }
        macro_rules! col_u8 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt8Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt8", $name)))?
            }};
        }
        macro_rules! col_f32 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::Float32Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not Float32", $name)))?
            }};
        }

        let region_ids = col_u16!("region_id");
        let terrains = col_u8!("terrain");
        let capacities = col_u16!("carrying_capacity");
        let populations = col_u16!("population");
        let soils = col_f32!("soil");
        let waters = col_f32!("water");
        let forest_covers = col_f32!("forest_cover");

        // Optional M26 columns — backward-compatible defaults.
        let controller_civs = rb
            .column_by_name("controller_civ")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let adjacency_masks = rb
            .column_by_name("adjacency_mask")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt32Array>());
        let trade_route_counts = rb
            .column_by_name("trade_route_count")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let is_contested_col = rb
            .column_by_name("is_contested")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());

        // Optional M34 columns — backward-compatible defaults.
        let resource_type_0 = rb
            .column_by_name("resource_type_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_type_1 = rb
            .column_by_name("resource_type_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_type_2 = rb
            .column_by_name("resource_type_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_yield_0 = rb
            .column_by_name("resource_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_yield_1 = rb
            .column_by_name("resource_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_yield_2 = rb
            .column_by_name("resource_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_reserve_0 = rb
            .column_by_name("resource_reserve_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_reserve_1 = rb
            .column_by_name("resource_reserve_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_reserve_2 = rb
            .column_by_name("resource_reserve_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let season_col = rb
            .column_by_name("season")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let season_id_col = rb
            .column_by_name("season_id")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // Optional M35a column
        let river_mask_col = rb
            .column_by_name("river_mask")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt32Array>());

        // Optional M35b column
        let endemic_severity_col = rb
            .column_by_name("endemic_severity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());

        // Optional M36 columns
        let culture_investment = rb
            .column_by_name("culture_investment_active")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let ctrl_val_0 = rb
            .column_by_name("controller_values_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let ctrl_val_1 = rb
            .column_by_name("controller_values_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let ctrl_val_2 = rb
            .column_by_name("controller_values_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // Optional M37 columns — conversion signals
        let conversion_rate_col = rb
            .column_by_name("conversion_rate")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let conversion_target_belief_col = rb
            .column_by_name("conversion_target_belief")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let conquest_conversion_active_col = rb
            .column_by_name("conquest_conversion_active")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let majority_belief_col = rb
            .column_by_name("majority_belief")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // Optional M38a columns — temples & clergy
        let has_temple_col = rb
            .column_by_name("has_temple")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());

        // Optional M38b columns — persecution & schism
        let persecution_intensity_col = rb
            .column_by_name("persecution_intensity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let schism_convert_from_col = rb
            .column_by_name("schism_convert_from")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let schism_convert_to_col = rb
            .column_by_name("schism_convert_to")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // M42: Goods economy signals
        let farmer_income_modifier_col = rb
            .column_by_name("farmer_income_modifier")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let food_sufficiency_col = rb
            .column_by_name("food_sufficiency")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let merchant_margin_col = rb
            .column_by_name("merchant_margin")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let merchant_trade_income_col = rb
            .column_by_name("merchant_trade_income")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());

        // M48: Per-region transient memory signals
        let controller_changed_col = rb
            .column_by_name("controller_changed_this_turn")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let war_won_col = rb
            .column_by_name("war_won_this_turn")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let seceded_col = rb
            .column_by_name("seceded_this_turn")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());

        // M55a: Spatial substrate columns
        let is_capital_col = rb
            .column_by_name("is_capital")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let temple_prestige_col = rb
            .column_by_name("temple_prestige")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());

        // M54a: Ecology schema columns
        let disease_baseline_col = rb
            .column_by_name("disease_baseline")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let capacity_modifier_col = rb
            .column_by_name("capacity_modifier")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_base_yield_0_col = rb
            .column_by_name("resource_base_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_base_yield_1_col = rb
            .column_by_name("resource_base_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_base_yield_2_col = rb
            .column_by_name("resource_base_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_0_col = rb
            .column_by_name("resource_effective_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_1_col = rb
            .column_by_name("resource_effective_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_2_col = rb
            .column_by_name("resource_effective_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_suspension_0_col = rb
            .column_by_name("resource_suspension_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let resource_suspension_1_col = rb
            .column_by_name("resource_suspension_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let resource_suspension_2_col = rb
            .column_by_name("resource_suspension_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let has_irrigation_col = rb
            .column_by_name("has_irrigation")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let has_mines_col = rb
            .column_by_name("has_mines")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let active_focus_col = rb
            .column_by_name("active_focus")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let prev_turn_water_col = rb
            .column_by_name("prev_turn_water")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let soil_pressure_streak_col = rb
            .column_by_name("soil_pressure_streak")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_0_col = rb
            .column_by_name("overextraction_streak_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_1_col = rb
            .column_by_name("overextraction_streak_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_2_col = rb
            .column_by_name("overextraction_streak_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());

        // M37: Initial belief for spawn (per-region, controller civ's faith_id)
        let initial_belief_col = rb
            .column_by_name("initial_belief")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // Store contested_regions.
        self.contested_regions = (0..n)
            .map(|i| is_contested_col.map_or(false, |arr| arr.value(i)))
            .collect();

        if !self.initialized {
            // First call: initialise regions and spawn agents.
            self.regions = (0..n)
                .map(|i| RegionState {
                    region_id: region_ids.value(i),
                    terrain: terrains.value(i),
                    carrying_capacity: capacities.value(i),
                    population: populations.value(i),
                    soil: soils.value(i),
                    water: waters.value(i),
                    forest_cover: forest_covers.value(i),
                    controller_civ: controller_civs.map_or(255, |arr| arr.value(i)),
                    adjacency_mask: adjacency_masks.map_or(0, |arr| arr.value(i)),
                    trade_route_count: trade_route_counts.map_or(0, |arr| arr.value(i)),
                    resource_types: [
                        resource_type_0.map_or(255, |arr| arr.value(i)),
                        resource_type_1.map_or(255, |arr| arr.value(i)),
                        resource_type_2.map_or(255, |arr| arr.value(i)),
                    ],
                    resource_yields: [
                        resource_yield_0.map_or(0.0, |arr| arr.value(i)),
                        resource_yield_1.map_or(0.0, |arr| arr.value(i)),
                        resource_yield_2.map_or(0.0, |arr| arr.value(i)),
                    ],
                    resource_reserves: [
                        resource_reserve_0.map_or(1.0, |arr| arr.value(i)),
                        resource_reserve_1.map_or(1.0, |arr| arr.value(i)),
                        resource_reserve_2.map_or(1.0, |arr| arr.value(i)),
                    ],
                    season: season_col.map_or(0, |arr| arr.value(i)),
                    season_id: season_id_col.map_or(0, |arr| arr.value(i)),
                    river_mask: river_mask_col.map_or(0, |arr| arr.value(i)),
                    endemic_severity: endemic_severity_col.map_or(0.0, |arr| arr.value(i)),
                    culture_investment_active: culture_investment.map_or(false, |arr| arr.value(i)),
                    controller_values: [
                        ctrl_val_0.map_or(0xFF, |arr| arr.value(i)),
                        ctrl_val_1.map_or(0xFF, |arr| arr.value(i)),
                        ctrl_val_2.map_or(0xFF, |arr| arr.value(i)),
                    ],
                    conversion_rate: conversion_rate_col.map_or(0.0, |arr| arr.value(i)),
                    conversion_target_belief: conversion_target_belief_col.map_or(0xFF, |arr| arr.value(i)),
                    conquest_conversion_active: conquest_conversion_active_col.map_or(false, |arr| arr.value(i)),
                    majority_belief: majority_belief_col.map_or(0xFF, |arr| arr.value(i)),
                    has_temple: has_temple_col.map_or(false, |c| c.value(i)),
                    persecution_intensity: persecution_intensity_col.map_or(0.0, |arr| arr.value(i)),
                    schism_convert_from: schism_convert_from_col.map_or(0xFF, |arr| arr.value(i)),
                    schism_convert_to: schism_convert_to_col.map_or(0xFF, |arr| arr.value(i)),
                    farmer_income_modifier: farmer_income_modifier_col.map_or(1.0, |arr| arr.value(i)),
                    food_sufficiency: food_sufficiency_col.map_or(1.0, |arr| arr.value(i)),
                    merchant_margin: merchant_margin_col.map_or(0.0, |arr| arr.value(i)),
                    merchant_trade_income: merchant_trade_income_col.map_or(0.0, |arr| arr.value(i)),
                    controller_changed_this_turn: controller_changed_col.map_or(false, |arr| arr.value(i)),
                    war_won_this_turn: war_won_col.map_or(false, |arr| arr.value(i)),
                    seceded_this_turn: seceded_col.map_or(false, |arr| arr.value(i)),
                    // M55a
                    is_capital: is_capital_col.map_or(false, |arr| arr.value(i)),
                    temple_prestige: temple_prestige_col.map_or(0.0, |arr| arr.value(i)),
                    // M54a ecology
                    disease_baseline: disease_baseline_col.map_or(0.0, |arr| arr.value(i)),
                    capacity_modifier: capacity_modifier_col.map_or(1.0, |arr| arr.value(i)),
                    resource_base_yield: [
                        resource_base_yield_0_col.map_or(0.0, |arr| arr.value(i)),
                        resource_base_yield_1_col.map_or(0.0, |arr| arr.value(i)),
                        resource_base_yield_2_col.map_or(0.0, |arr| arr.value(i)),
                    ],
                    resource_effective_yield: [
                        resource_effective_yield_0_col.map_or(0.0, |arr| arr.value(i)),
                        resource_effective_yield_1_col.map_or(0.0, |arr| arr.value(i)),
                        resource_effective_yield_2_col.map_or(0.0, |arr| arr.value(i)),
                    ],
                    resource_suspension: [
                        resource_suspension_0_col.map_or(false, |arr| arr.value(i)),
                        resource_suspension_1_col.map_or(false, |arr| arr.value(i)),
                        resource_suspension_2_col.map_or(false, |arr| arr.value(i)),
                    ],
                    has_irrigation: has_irrigation_col.map_or(false, |arr| arr.value(i)),
                    has_mines: has_mines_col.map_or(false, |arr| arr.value(i)),
                    active_focus: active_focus_col.map_or(0, |arr| arr.value(i)),
                    prev_turn_water: prev_turn_water_col.map_or(0.0, |arr| arr.value(i)),
                    soil_pressure_streak: soil_pressure_streak_col.map_or(0, |arr| arr.value(i)),
                    overextraction_streak: [
                        overextraction_streak_0_col.map_or(0, |arr| arr.value(i)),
                        overextraction_streak_1_col.map_or(0, |arr| arr.value(i)),
                        overextraction_streak_2_col.map_or(0, |arr| arr.value(i)),
                    ],
                })
                .collect();

            // Spawn agents from the incoming population column.
            // Distribution: 60% farmer, 15% soldier, 10% merchant, 10% scholar, ~5% priest
            for i in 0..n {
                let pop = populations.value(i) as usize;
                let region_id = region_ids.value(i);
                let civ = if self.regions[i].controller_civ != 255 {
                    self.regions[i].controller_civ
                } else {
                    (region_id % 256) as u8  // fallback for uncontrolled
                };

                let n_farmer = (pop * 60 + 50) / 100;
                let n_soldier = (pop * 15 + 50) / 100;
                let n_merchant = (pop * 10 + 50) / 100;
                let n_scholar = (pop * 10 + 50) / 100;
                let spawned = n_farmer + n_soldier + n_merchant + n_scholar;
                let n_priest = if pop > spawned { pop - spawned } else { 0 };

                // M33: personality assignment at initial spawn
                let mut personality_rng = ChaCha8Rng::from_seed(self.master_seed);
                personality_rng.set_stream(
                    region_id as u64 * 1000 + crate::agent::PERSONALITY_STREAM_OFFSET,
                );
                let civ_mean = [0.0f32; 3]; // Civ means not yet available at initial spawn

                // M53: mixed age distribution at initial spawn (was all age=0)
                let mut age_rng = ChaCha8Rng::from_seed(self.master_seed);
                age_rng.set_stream(
                    region_id as u64 * 1000 + crate::agent::INITIAL_AGE_STREAM_OFFSET,
                );

                // M37: use controller civ's faith_id as initial belief if provided
                let belief = if let Some(col) = &initial_belief_col {
                    col.value(i)
                } else {
                    crate::agent::BELIEF_NONE
                };

                // M53: younger-fertile skew for population mass retention.
                // Previous mix lost too many agents to elder mortality before
                // equilibrium. This skew keeps fertile base deeper into T80-150.
                //   20% ages 0-15 (young)
                //   55% ages 16-30 (prime fertile)
                //   20% ages 31-45 (late fertile/working)
                //    5% ages 46-60 (near-elder, no 60+ at spawn)
                let assign_age = |rng: &mut ChaCha8Rng| -> u16 {
                    let roll: f32 = rng.gen();
                    if roll < 0.20 {
                        (roll / 0.20 * 16.0) as u16
                    } else if roll < 0.75 {
                        16 + ((roll - 0.20) / 0.55 * 15.0) as u16
                    } else if roll < 0.95 {
                        31 + ((roll - 0.75) / 0.20 * 15.0) as u16
                    } else {
                        46 + ((roll - 0.95) / 0.05 * 15.0) as u16
                    }
                };

                for _ in 0..n_farmer {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.spawn(region_id, civ, Occupation::Farmer, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief);
                }
                for _ in 0..n_soldier {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.spawn(region_id, civ, Occupation::Soldier, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief);
                }
                for _ in 0..n_merchant {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.spawn(region_id, civ, Occupation::Merchant, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief);
                }
                for _ in 0..n_scholar {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.spawn(region_id, civ, Occupation::Scholar, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief);
                }
                for _ in 0..n_priest {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.spawn(region_id, civ, Occupation::Priest, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief);
                }
            }

            self.initialized = true;
        } else {
            // Subsequent calls: update all fields.
            if self.regions.len() != n {
                return Err(PyValueError::new_err(
                    "set_region_state: row count changed between calls",
                ));
            }
            for i in 0..n {
                let r = &mut self.regions[i];
                r.terrain = terrains.value(i);
                r.carrying_capacity = capacities.value(i);
                r.population = populations.value(i);
                r.soil = soils.value(i);
                r.water = waters.value(i);
                r.forest_cover = forest_covers.value(i);
                r.controller_civ = controller_civs.map_or(r.controller_civ, |arr| arr.value(i));
                r.adjacency_mask = adjacency_masks.map_or(r.adjacency_mask, |arr| arr.value(i));
                r.trade_route_count = trade_route_counts.map_or(r.trade_route_count, |arr| arr.value(i));
                r.resource_types[0] = resource_type_0.map_or(r.resource_types[0], |arr| arr.value(i));
                r.resource_types[1] = resource_type_1.map_or(r.resource_types[1], |arr| arr.value(i));
                r.resource_types[2] = resource_type_2.map_or(r.resource_types[2], |arr| arr.value(i));
                r.resource_yields[0] = resource_yield_0.map_or(r.resource_yields[0], |arr| arr.value(i));
                r.resource_yields[1] = resource_yield_1.map_or(r.resource_yields[1], |arr| arr.value(i));
                r.resource_yields[2] = resource_yield_2.map_or(r.resource_yields[2], |arr| arr.value(i));
                r.resource_reserves[0] = resource_reserve_0.map_or(r.resource_reserves[0], |arr| arr.value(i));
                r.resource_reserves[1] = resource_reserve_1.map_or(r.resource_reserves[1], |arr| arr.value(i));
                r.resource_reserves[2] = resource_reserve_2.map_or(r.resource_reserves[2], |arr| arr.value(i));
                r.season = season_col.map_or(r.season, |arr| arr.value(i));
                r.season_id = season_id_col.map_or(r.season_id, |arr| arr.value(i));
                r.river_mask = river_mask_col.map_or(r.river_mask, |arr| arr.value(i));
                r.endemic_severity = endemic_severity_col.map_or(r.endemic_severity, |arr| arr.value(i));
                r.culture_investment_active = culture_investment.map_or(false, |arr| arr.value(i));
                r.controller_values = [
                    ctrl_val_0.map_or(0xFF, |arr| arr.value(i)),
                    ctrl_val_1.map_or(0xFF, |arr| arr.value(i)),
                    ctrl_val_2.map_or(0xFF, |arr| arr.value(i)),
                ];
                r.conversion_rate = conversion_rate_col.map_or(r.conversion_rate, |arr| arr.value(i));
                r.conversion_target_belief = conversion_target_belief_col.map_or(r.conversion_target_belief, |arr| arr.value(i));
                r.conquest_conversion_active = conquest_conversion_active_col.map_or(r.conquest_conversion_active, |arr| arr.value(i));
                r.majority_belief = majority_belief_col.map_or(r.majority_belief, |arr| arr.value(i));
                r.has_temple = has_temple_col.map_or(false, |arr| arr.value(i));
                r.persecution_intensity = persecution_intensity_col.map_or(r.persecution_intensity, |arr| arr.value(i));
                r.schism_convert_from = schism_convert_from_col.map_or(0xFF, |arr| arr.value(i));
                r.schism_convert_to = schism_convert_to_col.map_or(0xFF, |arr| arr.value(i));
                if let Some(arr) = farmer_income_modifier_col { r.farmer_income_modifier = arr.value(i); }
                if let Some(arr) = food_sufficiency_col { r.food_sufficiency = arr.value(i); }
                if let Some(arr) = merchant_margin_col { r.merchant_margin = arr.value(i); }
                if let Some(arr) = merchant_trade_income_col { r.merchant_trade_income = arr.value(i); }
                r.controller_changed_this_turn = controller_changed_col.map_or(false, |arr| arr.value(i));
                r.war_won_this_turn = war_won_col.map_or(false, |arr| arr.value(i));
                r.seceded_this_turn = seceded_col.map_or(false, |arr| arr.value(i));
                r.is_capital = is_capital_col.map_or(false, |arr| arr.value(i));
                r.temple_prestige = temple_prestige_col.map_or(0.0, |arr| arr.value(i));
                // M54a ecology — read-only inputs
                if let Some(arr) = disease_baseline_col { r.disease_baseline = arr.value(i); }
                if let Some(arr) = capacity_modifier_col { r.capacity_modifier = arr.value(i); }
                if let Some(arr) = resource_base_yield_0_col { r.resource_base_yield[0] = arr.value(i); }
                if let Some(arr) = resource_base_yield_1_col { r.resource_base_yield[1] = arr.value(i); }
                if let Some(arr) = resource_base_yield_2_col { r.resource_base_yield[2] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_0_col { r.resource_effective_yield[0] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_1_col { r.resource_effective_yield[1] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_2_col { r.resource_effective_yield[2] = arr.value(i); }
                r.resource_suspension[0] = resource_suspension_0_col.map_or(false, |arr| arr.value(i));
                r.resource_suspension[1] = resource_suspension_1_col.map_or(false, |arr| arr.value(i));
                r.resource_suspension[2] = resource_suspension_2_col.map_or(false, |arr| arr.value(i));
                r.has_irrigation = has_irrigation_col.map_or(false, |arr| arr.value(i));
                r.has_mines = has_mines_col.map_or(false, |arr| arr.value(i));
                if let Some(arr) = active_focus_col { r.active_focus = arr.value(i); }
                // M54a ecology — persistent state (synced from Python during migration)
                if let Some(arr) = prev_turn_water_col { r.prev_turn_water = arr.value(i); }
                if let Some(arr) = soil_pressure_streak_col { r.soil_pressure_streak = arr.value(i); }
                if let Some(arr) = overextraction_streak_0_col { r.overextraction_streak[0] = arr.value(i); }
                if let Some(arr) = overextraction_streak_1_col { r.overextraction_streak[1] = arr.value(i); }
                if let Some(arr) = overextraction_streak_2_col { r.overextraction_streak[2] = arr.value(i); }
            }
        }
        Ok(())
    }

    /// Advance simulation by one turn. Returns an events RecordBatch.
    pub fn tick(&mut self, turn: u32, civ_signals: PyRecordBatch) -> PyResult<PyRecordBatch> {
        if !self.initialized {
            return Err(PyValueError::new_err(
                "tick() called before set_region_state()",
            ));
        }
        self.turn = turn;

        // Parse civ signals from the Arrow batch.
        let civ_rb: RecordBatch = civ_signals.into_inner();
        let civs = crate::signals::parse_civ_signals(&civ_rb).map_err(arrow_err)?;

        let signals = crate::signals::TickSignals {
            civs,
            contested_regions: self.contested_regions.clone(),
        };

        // Resize scratch vector if pool grew
        if self.wealth_percentiles.len() < self.pool.capacity() {
            self.wealth_percentiles.resize(self.pool.capacity(), 0.0);
        }

        let (events, kin_failures, formation_stats, demo_debug) = crate::tick::tick_agents(
            &mut self.pool,
            &self.regions,
            &signals,
            self.master_seed,
            turn,
            &mut self.wealth_percentiles,
        );
        self.prev_kin_bond_failures = self.kin_bond_failures;
        self.kin_bond_failures = self.kin_bond_failures.saturating_add(kin_failures);
        self.formation_stats = formation_stats;
        self.demographic_debug = demo_debug;

        // M53: demographic debug counters
        // event_type 0 = death, 5 = birth (from tick.rs AgentEvent)
        self.last_tick_deaths = events.iter().filter(|e| e.event_type == 0).count() as u32;
        self.last_tick_births = events.iter().filter(|e| e.event_type == 5).count() as u32;
        self.last_tick_alive = self.pool.alive.iter().filter(|&&a| a).count() as u32;

        let batch = events_to_batch(&events).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return an Arrow RecordBatch snapshot of all alive agents.
    pub fn get_snapshot(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.to_record_batch().map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return per-civ aggregate stats as an Arrow RecordBatch.
    pub fn get_aggregates(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.compute_aggregates(&self.regions).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return per-region alive counts as an Arrow RecordBatch.
    pub fn get_region_populations(&self) -> PyResult<PyRecordBatch> {
        let batch = self
            .pool
            .region_populations(self.num_regions)
            .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    pub fn get_promotions(&mut self) -> PyResult<PyRecordBatch> {
        let candidates = self.registry.find_candidates(&self.pool, self.turn);
        let n = candidates.len();
        let mut agent_ids = UInt32Builder::with_capacity(n);
        let mut roles = UInt8Builder::with_capacity(n);
        let mut triggers = UInt8Builder::with_capacity(n);
        let mut skills = arrow::array::Float32Builder::with_capacity(n);
        let mut life_events_col = UInt8Builder::with_capacity(n);
        let mut origin_regions = UInt16Builder::with_capacity(n);
        let mut boldness_col = arrow::array::Float32Builder::with_capacity(n);
        let mut ambition_col = arrow::array::Float32Builder::with_capacity(n);
        let mut loyalty_trait_col = arrow::array::Float32Builder::with_capacity(n);
        let mut label_col = StringBuilder::with_capacity(n, n * 16);
        let mut parent_id_col = UInt32Builder::with_capacity(n);

        for &(slot, role, trigger) in &candidates {
            let agent_id = self.pool.id(slot);
            let occ = self.pool.occupations[slot] as usize;
            let skill = self.pool.skills[slot * 5 + occ];

            agent_ids.append_value(agent_id);
            roles.append_value(role as u8);
            triggers.append_value(trigger);
            skills.append_value(skill);
            life_events_col.append_value(self.pool.life_events[slot]);
            origin_regions.append_value(self.pool.origin_regions[slot]);

            let b = self.pool.boldness[slot];
            let a = self.pool.ambition[slot];
            let lt = self.pool.loyalty_trait[slot];
            boldness_col.append_value(b);
            ambition_col.append_value(a);
            loyalty_trait_col.append_value(lt);
            match personality_label(b, a, lt) {
                Some(label) => label_col.append_value(label),
                None => label_col.append_null(),
            }
            parent_id_col.append_value(self.pool.parent_ids[slot]);

            // Register in the Rust-side registry.
            // origin_civ_id = current civ at promotion time (best available;
            // Python owns the richer GreatPerson.origin_civilization).
            // born_turn = turn - age (when the agent was spawned).
            let born = self.turn.saturating_sub(self.pool.age(slot) as u32) as u16;
            self.registry.register(
                agent_id,
                role,
                self.pool.civ_affinity(slot),
                self.pool.civ_affinity(slot),
                born,
                self.turn as u16,
                trigger,
                self.pool.parent_ids[slot],
            );
        }

        let schema = Arc::new(promotions_schema());
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(agent_ids.finish()) as _,
                Arc::new(roles.finish()) as _,
                Arc::new(triggers.finish()) as _,
                Arc::new(skills.finish()) as _,
                Arc::new(life_events_col.finish()) as _,
                Arc::new(origin_regions.finish()) as _,
                Arc::new(boldness_col.finish()) as _,
                Arc::new(ambition_col.finish()) as _,
                Arc::new(loyalty_trait_col.finish()) as _,
                Arc::new(label_col.finish()) as _,
                Arc::new(parent_id_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    pub fn set_agent_civ(&mut self, agent_id: u32, new_civ_id: u8) -> PyResult<()> {
        for slot in 0..self.pool.capacity() {
            if self.pool.is_alive(slot) && self.pool.id(slot) == agent_id {
                self.pool.set_civ_affinity(slot, new_civ_id);
                self.registry.set_character_civ(agent_id, new_civ_id);
                return Ok(());
            }
        }
        Err(PyValueError::new_err(format!("agent_id {} not found or dead", agent_id)))
    }

    /// Return current social graph edges as an Arrow RecordBatch.
    /// Projects from the per-agent SoA relationship store (M50a) instead of the
    /// old SocialGraph.  Same schema: [agent_a: u32, agent_b: u32, relationship: u8,
    /// formed_turn: u16].  Only named-character bonds with bond_type 0-4 (M40-compatible).
    pub fn get_social_edges(&self) -> PyResult<PyRecordBatch> {
        // Collect named character agent IDs for fast membership check
        let named_ids: std::collections::HashSet<u32> = self.registry.characters.iter()
            .map(|c| c.agent_id).collect();

        let mut agent_a_col = UInt32Builder::new();
        let mut agent_b_col = UInt32Builder::new();
        let mut rel_col = UInt8Builder::new();
        let mut formed_col = UInt16Builder::new();

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            if !named_ids.contains(&agent_id) { continue; }

            let count = self.pool.rel_count[slot] as usize;
            for i in 0..count {
                let bt = self.pool.rel_bond_types[slot][i];
                // Only project M40-compatible types (0-4)
                if bt > 4 { continue; }

                let target_id = self.pool.rel_target_ids[slot][i];

                if crate::relationships::is_asymmetric(bt) {
                    // Mentor: emit from mentor side (this slot = mentor, target = apprentice)
                    agent_a_col.append_value(agent_id);
                    agent_b_col.append_value(target_id);
                    rel_col.append_value(bt);
                    formed_col.append_value(self.pool.rel_formed_turns[slot][i]);
                } else {
                    // Symmetric: emit only from the lower-id side to avoid duplicates
                    if agent_id < target_id {
                        agent_a_col.append_value(agent_id);
                        agent_b_col.append_value(target_id);
                        rel_col.append_value(bt);
                        formed_col.append_value(self.pool.rel_formed_turns[slot][i]);
                    }
                }
            }
        }

        let batch = RecordBatch::try_new(
            Arc::new(social_edges_schema()),
            vec![
                Arc::new(agent_a_col.finish()) as _,
                Arc::new(agent_b_col.finish()) as _,
                Arc::new(rel_col.finish()) as _,
                Arc::new(formed_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// M48: Return memory slots for a specific agent.
    /// Returns Vec<(event_type, source_civ, turn, intensity, decay_factor, is_legacy)>.
    /// Empty vec if agent not found or dead.
    fn get_agent_memories(&self, agent_id: u32) -> Vec<(u8, u8, u16, i8, u8, bool)> {
        // O(N) scan for agent_id — acceptable for ~50 named character queries
        let pool = &self.pool;
        for slot in 0..pool.ids.len() {
            if pool.id(slot) == agent_id && pool.is_alive(slot) {
                let count = pool.memory_count[slot] as usize;
                let mut result = Vec::with_capacity(count);
                for i in 0..count {
                    result.push((
                        pool.memory_event_types[slot][i],
                        pool.memory_source_civs[slot][i],
                        pool.memory_turns[slot][i],
                        pool.memory_intensities[slot][i],
                        pool.memory_decay_factors[slot][i],
                        (pool.memory_is_legacy[slot] >> i) & 1 == 1,  // NEW: legacy flag
                    ));
                }
                return result;
            }
        }
        Vec::new()
    }

    /// M49: Return need values for a specific agent.
    /// Returns (safety, material, social, spiritual, autonomy, purpose).
    /// None if agent not found or dead.
    fn get_agent_needs(&self, agent_id: u32) -> Option<(f32, f32, f32, f32, f32, f32)> {
        let pool = &self.pool;
        for slot in 0..pool.ids.len() {
            if pool.id(slot) == agent_id && pool.is_alive(slot) {
                return Some((
                    pool.need_safety[slot],
                    pool.need_material[slot],
                    pool.need_social[slot],
                    pool.need_spiritual[slot],
                    pool.need_autonomy[slot],
                    pool.need_purpose[slot],
                ));
            }
        }
        None
    }

    /// M40 compatibility shim. Translates full-graph replacement into incremental ops.
    /// DEPRECATED — use apply_relationship_ops directly. Will be removed in M50b.
    pub fn replace_social_edges(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let batch = batch.into_inner();
        let named_ids: std::collections::HashSet<u32> = self.registry.characters.iter()
            .map(|c| c.agent_id).collect();

        // 1. Read current projected state (compound key = (a, b, relationship_type))
        let mut current: std::collections::HashSet<(u32, u32, u8)> = std::collections::HashSet::new();
        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            if !named_ids.contains(&agent_id) { continue; }
            let count = self.pool.rel_count[slot] as usize;
            for i in 0..count {
                let bt = self.pool.rel_bond_types[slot][i];
                if bt > 4 { continue; } // Only M40-compatible types
                let target_id = self.pool.rel_target_ids[slot][i];
                if crate::relationships::is_asymmetric(bt) {
                    current.insert((agent_id, target_id, bt));
                } else if agent_id < target_id {
                    current.insert((agent_id, target_id, bt));
                }
            }
        }

        // 2. Parse incoming batch
        let mut incoming: std::collections::HashSet<(u32, u32, u8)> = std::collections::HashSet::new();
        let mut incoming_turns: std::collections::HashMap<(u32, u32, u8), u16> = std::collections::HashMap::new();
        if batch.num_rows() > 0 {
            let a_col = batch.column(0).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
            let b_col = batch.column(1).as_any().downcast_ref::<arrow::array::UInt32Array>().unwrap();
            let r_col = batch.column(2).as_any().downcast_ref::<arrow::array::UInt8Array>().unwrap();
            let t_col = batch.column(3).as_any().downcast_ref::<arrow::array::UInt16Array>().unwrap();
            for i in 0..batch.num_rows() {
                let a = a_col.value(i);
                let b = b_col.value(i);
                let r = r_col.value(i);
                let t = t_col.value(i);
                // Guard: only named characters
                if !named_ids.contains(&a) || !named_ids.contains(&b) { continue; }
                let key = if crate::relationships::is_asymmetric(r) {
                    (a, b, r)
                } else {
                    (a.min(b), a.max(b), r)
                };
                incoming.insert(key);
                incoming_turns.insert(key, t);
            }
        }

        // 3. Diff: removals = current - incoming
        for &(a, b, bt) in current.difference(&incoming) {
            if crate::relationships::is_asymmetric(bt) {
                // Mentor: remove from mentor side only
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    crate::relationships::remove_directed(&mut self.pool, slot_a, b, bt);
                }
            } else {
                // Symmetric: remove whatever side still exists
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    if self.pool.alive[slot_a] {
                        crate::relationships::remove_directed(&mut self.pool, slot_a, b, bt);
                    }
                }
                if let Some(slot_b) = self.pool.find_slot_by_id(b) {
                    if self.pool.alive[slot_b] {
                        crate::relationships::remove_directed(&mut self.pool, slot_b, a, bt);
                    }
                }
            }
        }

        // 4. Additions = incoming - current
        for &(a, b, bt) in incoming.difference(&current) {
            let ft = incoming_turns.get(&(a, b, bt)).copied().unwrap_or(0);
            let sent: i8 = 50; // Default sentiment (M40 has no sentiment)
            if crate::relationships::is_asymmetric(bt) {
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    if self.pool.alive[slot_a] {
                        crate::relationships::upsert_directed(&mut self.pool, slot_a, b, bt, sent, ft);
                    }
                }
            } else {
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    if let Some(slot_b) = self.pool.find_slot_by_id(b) {
                        if self.pool.alive[slot_a] && self.pool.alive[slot_b] {
                            crate::relationships::upsert_symmetric(&mut self.pool, slot_a, slot_b, bt, sent, ft);
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// M50a: Apply batched relationship operations from an Arrow RecordBatch.
    /// Columns: op_type(u8), agent_a(u32), agent_b(u32), bond_type(u8), sentiment(i8), formed_turn(u16)
    /// op_type: 0=UpsertDirected, 1=UpsertSymmetric, 2=RemoveDirected, 3=RemoveSymmetric
    pub fn apply_relationship_ops(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();

        macro_rules! named_col {
            ($name:expr, $ty:ty) => {
                rb.column_by_name($name)
                    .and_then(|c| c.as_any().downcast_ref::<$ty>())
                    .ok_or_else(|| PyValueError::new_err(concat!("missing or wrong type: ", $name)))?
            };
        }

        let op_type_col = named_col!("op_type", arrow::array::UInt8Array);
        let agent_a_col = named_col!("agent_a", arrow::array::UInt32Array);
        let agent_b_col = named_col!("agent_b", arrow::array::UInt32Array);
        let bond_type_col = named_col!("bond_type", arrow::array::UInt8Array);
        let sentiment_col = named_col!("sentiment", arrow::array::Int8Array);
        let formed_turn_col = named_col!("formed_turn", arrow::array::UInt16Array);

        for i in 0..n {
            let op = op_type_col.value(i);
            let id_a = agent_a_col.value(i);
            let id_b = agent_b_col.value(i);
            let bt_raw = bond_type_col.value(i);
            let sentiment = sentiment_col.value(i);
            let formed_turn = formed_turn_col.value(i);

            let bt = match crate::relationships::BondType::from_u8(bt_raw) {
                Some(b) => b,
                None => continue, // skip unknown bond type
            };
            let _ = bt; // validate only; we pass bt_raw to the helpers

            match op {
                0 => {
                    // UpsertDirected: src and dst must be alive
                    let slot_a = match self.pool.find_slot_by_id(id_a) {
                        Some(s) => s,
                        None => continue,
                    };
                    if self.pool.find_slot_by_id(id_b).is_none() {
                        continue; // dst must be alive
                    }
                    crate::relationships::upsert_directed(
                        &mut self.pool, slot_a, id_b, bt_raw, sentiment, formed_turn,
                    );
                }
                1 => {
                    // UpsertSymmetric: both alive, reject asymmetric types AND Kin
                    // Kin bonds must go through Rust-native birth path (form_kin_bond)
                    if crate::relationships::is_asymmetric(bt_raw)
                        || bt_raw == crate::relationships::BondType::Kin as u8
                    {
                        continue;
                    }
                    let slot_a = match self.pool.find_slot_by_id(id_a) {
                        Some(s) => s,
                        None => continue,
                    };
                    let slot_b = match self.pool.find_slot_by_id(id_b) {
                        Some(s) => s,
                        None => continue,
                    };
                    crate::relationships::upsert_symmetric(
                        &mut self.pool, slot_a, slot_b, bt_raw, sentiment, formed_turn,
                    );
                }
                2 => {
                    // RemoveDirected: source must be alive, target may be dead
                    let slot_a = match self.pool.find_slot_by_id(id_a) {
                        Some(s) => s,
                        None => continue,
                    };
                    crate::relationships::remove_directed(&mut self.pool, slot_a, id_b, bt_raw);
                }
                3 => {
                    // RemoveSymmetric: remove whatever side still exists
                    if let Some(slot_a) = self.pool.find_slot_by_id(id_a) {
                        if self.pool.alive[slot_a] {
                            crate::relationships::remove_directed(&mut self.pool, slot_a, id_b, bt_raw);
                        }
                    }
                    if let Some(slot_b) = self.pool.find_slot_by_id(id_b) {
                        if self.pool.alive[slot_b] {
                            crate::relationships::remove_directed(&mut self.pool, slot_b, id_a, bt_raw);
                        }
                    }
                }
                _ => continue, // unknown op type
            }
        }
        Ok(())
    }

    /// M50a: Return all relationship slots for one agent.
    /// Returns Vec<(target_id, sentiment, bond_type, formed_turn)> or None if not found/dead.
    fn get_agent_relationships(&self, agent_id: u32) -> Option<Vec<(u32, i8, u8, u16)>> {
        let slot = self.pool.find_slot_by_id(agent_id)?;
        if !self.pool.alive[slot] { return None; }
        let count = self.pool.rel_count[slot] as usize;
        let mut result = Vec::with_capacity(count);
        for i in 0..count {
            result.push(crate::relationships::read_rel(&self.pool, slot, i));
        }
        Some(result)
    }

    /// M53: Return expanded demographic debug counters from the last tick.
    #[pyo3(name = "get_demographic_debug")]
    pub fn get_demographic_debug(&self) -> std::collections::HashMap<String, f64> {
        let d = &self.demographic_debug;
        let mut m = std::collections::HashMap::new();
        m.insert("deaths_young".into(), d.deaths_young as f64);
        m.insert("deaths_adult".into(), d.deaths_adult as f64);
        m.insert("deaths_elder".into(), d.deaths_elder as f64);
        m.insert("deaths_with_disease".into(), d.deaths_with_disease as f64);
        m.insert("deaths_soldier_at_war".into(), d.deaths_soldier_at_war as f64);
        m.insert("deaths_eco_stress_gt1".into(), d.deaths_eco_stress_gt1 as f64);
        m.insert("mean_endemic".into(), d.mean_endemic as f64);
        m.insert("max_endemic".into(), d.max_endemic as f64);
        m.insert("fertile_farmer".into(), d.fertile_by_occ[0] as f64);
        m.insert("fertile_soldier".into(), d.fertile_by_occ[1] as f64);
        m.insert("fertile_merchant".into(), d.fertile_by_occ[2] as f64);
        m.insert("fertile_scholar".into(), d.fertile_by_occ[3] as f64);
        m.insert("fertile_priest".into(), d.fertile_by_occ[4] as f64);
        m.insert("fertile_age_total".into(), d.fertile_age_total as f64);
        m.insert("expected_deaths".into(), d.expected_deaths as f64);
        m.insert("expected_births".into(), d.expected_births as f64);
        m.insert("sat_near_threshold".into(), d.sat_near_threshold as f64);
        m
    }

    /// M53: Return age distribution of alive agents.
    #[pyo3(name = "get_age_histogram")]
    pub fn get_age_histogram(&self) -> std::collections::HashMap<String, u32> {
        let mut m = std::collections::HashMap::new();
        let mut young: u32 = 0;
        let mut adult: u32 = 0;
        let mut elder: u32 = 0;
        let mut fertile_range: u32 = 0;
        let mut total: u32 = 0;
        for slot in 0..self.pool.capacity() {
            if !self.pool.is_alive(slot) { continue; }
            total += 1;
            let age = self.pool.ages[slot];
            match age {
                0..crate::agent::AGE_ADULT => young += 1,
                crate::agent::AGE_ADULT..crate::agent::AGE_ELDER => adult += 1,
                _ => elder += 1,
            }
            if age >= crate::agent::FERTILITY_AGE_MIN && age <= crate::agent::FERTILITY_TAPER_AGE_MAX {
                fertile_range += 1;
            }
        }
        m.insert("young_0_19".into(), young);
        m.insert("adult_20_59".into(), adult);
        m.insert("elder_60_plus".into(), elder);
        m.insert("fertile_range_16_60".into(), fertile_range);
        m.insert("total_alive".into(), total);
        m
    }

    /// M50b: Return formation stats + distribution metrics as a flat HashMap.
    /// Includes per-tick formation counters, kin_bond_failures delta, and
    /// distribution snapshots (mean rel count, sentiment, bond type counts,
    /// cross-civ fraction).
    #[pyo3(name = "get_relationship_stats")]
    pub fn get_relationship_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();

        // Formation stats from last tick
        stats.insert("bonds_formed".into(), self.formation_stats.bonds_formed as f64);
        stats.insert("bonds_dissolved_structural".into(), self.formation_stats.bonds_dissolved_structural as f64);
        stats.insert("bonds_dissolved_death".into(), self.formation_stats.bonds_dissolved_death as f64);
        stats.insert("bonds_evicted".into(), self.formation_stats.bonds_evicted as f64);
        stats.insert("pairs_evaluated".into(), self.formation_stats.pairs_evaluated as f64);
        stats.insert("pairs_eligible".into(), self.formation_stats.pairs_eligible as f64);

        // Kin bond failures delta (this tick vs last tick)
        let delta = self.kin_bond_failures.saturating_sub(self.prev_kin_bond_failures);
        stats.insert("kin_bond_failures_delta".into(), delta as f64);

        // Distribution snapshots: single pass over alive agents
        let mut alive_count: u64 = 0;
        let mut total_rel_count: u64 = 0;
        let mut positive_sentiment_sum: f64 = 0.0;
        let mut positive_sentiment_count: u64 = 0;
        let mut bond_type_counts = [0u64; 8];
        let mut cross_civ_bonds: u64 = 0;
        let mut total_directed_slots: u64 = 0;

        // Build id_to_slot map for cross-civ lookups
        let mut id_to_slot: std::collections::HashMap<u32, usize> =
            std::collections::HashMap::with_capacity(self.pool.alive_count());
        for slot in 0..self.pool.capacity() {
            if self.pool.alive[slot] {
                id_to_slot.insert(self.pool.ids[slot], slot);
            }
        }

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            alive_count += 1;
            let count = self.pool.rel_count[slot] as usize;
            total_rel_count += count as u64;

            let src_civ = self.pool.civ_affinities[slot];

            for i in 0..count {
                let bond_type = self.pool.rel_bond_types[slot][i];
                let sentiment = self.pool.rel_sentiments[slot][i];
                let target_id = self.pool.rel_target_ids[slot][i];

                // Bond type counts
                if (bond_type as usize) < 8 {
                    bond_type_counts[bond_type as usize] += 1;
                }

                // Positive sentiment for positive-valence bonds
                if crate::relationships::is_positive_valence(bond_type) && sentiment > 0 {
                    positive_sentiment_sum += sentiment as f64;
                    positive_sentiment_count += 1;
                }

                // Cross-civ check
                total_directed_slots += 1;
                if let Some(&target_slot) = id_to_slot.get(&target_id) {
                    if self.pool.civ_affinities[target_slot] != src_civ {
                        cross_civ_bonds += 1;
                    }
                }
                // If target not found (dead), don't count as cross-civ
            }
        }

        // Write distribution metrics
        let mean_rel = if alive_count > 0 { total_rel_count as f64 / alive_count as f64 } else { 0.0 };
        stats.insert("mean_rel_count".into(), mean_rel);

        let mean_pos_sent = if positive_sentiment_count > 0 {
            positive_sentiment_sum / positive_sentiment_count as f64
        } else { 0.0 };
        stats.insert("mean_positive_sentiment".into(), mean_pos_sent);

        for i in 0..8 {
            stats.insert(format!("bond_type_count_{}", i), bond_type_counts[i] as f64);
        }

        let cross_frac = if total_directed_slots > 0 {
            cross_civ_bonds as f64 / total_directed_slots as f64
        } else { 0.0 };
        stats.insert("cross_civ_bond_fraction".into(), cross_frac);

        Ok(stats)
    }

    /// M50b: Return ALL relationship edges as an Arrow RecordBatch.
    /// Schema: [agent_id: u32, target_id: u32, sentiment: i8, bond_type: u8, formed_turn: u16]
    /// One row per occupied relationship slot across all alive agents.
    #[pyo3(name = "get_all_relationships")]
    pub fn get_all_relationships(&self) -> PyResult<PyRecordBatch> {
        // Pre-count total edges for capacity hint
        let mut total_edges: usize = 0;
        for slot in 0..self.pool.capacity() {
            if self.pool.alive[slot] {
                total_edges += self.pool.rel_count[slot] as usize;
            }
        }

        let mut agent_id_col = UInt32Builder::with_capacity(total_edges);
        let mut target_id_col = UInt32Builder::with_capacity(total_edges);
        let mut sentiment_col = Int8Builder::with_capacity(total_edges);
        let mut bond_type_col = UInt8Builder::with_capacity(total_edges);
        let mut formed_turn_col = UInt16Builder::with_capacity(total_edges);

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            let count = self.pool.rel_count[slot] as usize;
            for i in 0..count {
                agent_id_col.append_value(agent_id);
                target_id_col.append_value(self.pool.rel_target_ids[slot][i]);
                sentiment_col.append_value(self.pool.rel_sentiments[slot][i]);
                bond_type_col.append_value(self.pool.rel_bond_types[slot][i]);
                formed_turn_col.append_value(self.pool.rel_formed_turns[slot][i]);
            }
        }

        let schema = Arc::new(Schema::new(vec![
            Field::new("agent_id", DataType::UInt32, false),
            Field::new("target_id", DataType::UInt32, false),
            Field::new("sentiment", DataType::Int8, false),
            Field::new("bond_type", DataType::UInt8, false),
            Field::new("formed_turn", DataType::UInt16, false),
        ]));

        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(agent_id_col.finish()) as _,
                Arc::new(target_id_col.finish()) as _,
                Arc::new(sentiment_col.finish()) as _,
                Arc::new(bond_type_col.finish()) as _,
                Arc::new(formed_turn_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// M53: Return ALL agent memories as an Arrow RecordBatch.
    /// Schema: [agent_id: u32, slot: u8, event_type: u8, turn: u16, intensity: i8,
    ///          is_legacy: u8, civ_affinity: u16, region: u16, occupation: u8]
    /// One row per occupied memory slot across all alive agents.
    #[pyo3(name = "get_all_memories")]
    pub fn get_all_memories(&self) -> PyResult<PyRecordBatch> {
        // Pre-count total memory rows for capacity hint
        let mut total_memories: usize = 0;
        for slot in 0..self.pool.capacity() {
            if self.pool.alive[slot] {
                total_memories += self.pool.memory_count[slot] as usize;
            }
        }

        let mut agent_id_col = UInt32Builder::with_capacity(total_memories);
        let mut slot_col = UInt8Builder::with_capacity(total_memories);
        let mut event_type_col = UInt8Builder::with_capacity(total_memories);
        let mut turn_col = UInt16Builder::with_capacity(total_memories);
        let mut intensity_col = Int8Builder::with_capacity(total_memories);
        let mut is_legacy_col = UInt8Builder::with_capacity(total_memories);
        let mut civ_affinity_col = UInt16Builder::with_capacity(total_memories);
        let mut region_col = UInt16Builder::with_capacity(total_memories);
        let mut occupation_col = UInt8Builder::with_capacity(total_memories);

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            let mem_count = self.pool.memory_count[slot] as usize;
            let civ_affinity = self.pool.civ_affinities[slot] as u16;
            let region = self.pool.regions[slot];
            let occupation = self.pool.occupations[slot];
            let legacy_mask = self.pool.memory_is_legacy[slot];
            for i in 0..mem_count {
                agent_id_col.append_value(agent_id);
                slot_col.append_value(i as u8);
                event_type_col.append_value(self.pool.memory_event_types[slot][i]);
                turn_col.append_value(self.pool.memory_turns[slot][i]);
                intensity_col.append_value(self.pool.memory_intensities[slot][i]);
                is_legacy_col.append_value((legacy_mask >> i) & 1);
                civ_affinity_col.append_value(civ_affinity);
                region_col.append_value(region);
                occupation_col.append_value(occupation);
            }
        }

        let schema = Arc::new(Schema::new(vec![
            Field::new("agent_id", DataType::UInt32, false),
            Field::new("slot", DataType::UInt8, false),
            Field::new("event_type", DataType::UInt8, false),
            Field::new("turn", DataType::UInt16, false),
            Field::new("intensity", DataType::Int8, false),
            Field::new("is_legacy", DataType::UInt8, false),
            Field::new("civ_affinity", DataType::UInt16, false),
            Field::new("region", DataType::UInt16, false),
            Field::new("occupation", DataType::UInt8, false),
        ]));

        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(agent_id_col.finish()) as _,
                Arc::new(slot_col.finish()) as _,
                Arc::new(event_type_col.finish()) as _,
                Arc::new(turn_col.finish()) as _,
                Arc::new(intensity_col.finish()) as _,
                Arc::new(is_legacy_col.finish()) as _,
                Arc::new(civ_affinity_col.finish()) as _,
                Arc::new(region_col.finish()) as _,
                Arc::new(occupation_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// M53: Return ALL agent needs as an Arrow RecordBatch.
    /// Schema: [agent_id: u32, safety: f32, autonomy: f32, social: f32, spiritual: f32,
    ///          material: f32, purpose: f32, civ_affinity: u16, region: u16,
    ///          occupation: u8, satisfaction: f32, boldness: f32, ambition: f32, loyalty_trait: f32]
    /// One row per alive agent.
    #[pyo3(name = "get_all_needs")]
    pub fn get_all_needs(&self) -> PyResult<PyRecordBatch> {
        let live = self.pool.alive_count();

        let mut agent_id_col = UInt32Builder::with_capacity(live);
        let mut safety_col = arrow::array::Float32Builder::with_capacity(live);
        let mut autonomy_col = arrow::array::Float32Builder::with_capacity(live);
        let mut social_col = arrow::array::Float32Builder::with_capacity(live);
        let mut spiritual_col = arrow::array::Float32Builder::with_capacity(live);
        let mut material_col = arrow::array::Float32Builder::with_capacity(live);
        let mut purpose_col = arrow::array::Float32Builder::with_capacity(live);
        let mut civ_affinity_col = UInt16Builder::with_capacity(live);
        let mut region_col = UInt16Builder::with_capacity(live);
        let mut occupation_col = UInt8Builder::with_capacity(live);
        let mut satisfaction_col = arrow::array::Float32Builder::with_capacity(live);
        let mut boldness_col = arrow::array::Float32Builder::with_capacity(live);
        let mut ambition_col = arrow::array::Float32Builder::with_capacity(live);
        let mut loyalty_trait_col = arrow::array::Float32Builder::with_capacity(live);

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            agent_id_col.append_value(self.pool.ids[slot]);
            safety_col.append_value(self.pool.need_safety[slot]);
            autonomy_col.append_value(self.pool.need_autonomy[slot]);
            social_col.append_value(self.pool.need_social[slot]);
            spiritual_col.append_value(self.pool.need_spiritual[slot]);
            material_col.append_value(self.pool.need_material[slot]);
            purpose_col.append_value(self.pool.need_purpose[slot]);
            civ_affinity_col.append_value(self.pool.civ_affinities[slot] as u16);
            region_col.append_value(self.pool.regions[slot]);
            occupation_col.append_value(self.pool.occupations[slot]);
            satisfaction_col.append_value(self.pool.satisfactions[slot]);
            boldness_col.append_value(self.pool.boldness[slot]);
            ambition_col.append_value(self.pool.ambition[slot]);
            loyalty_trait_col.append_value(self.pool.loyalty_trait[slot]);
        }

        let schema = Arc::new(Schema::new(vec![
            Field::new("agent_id",     DataType::UInt32,  false),
            Field::new("safety",       DataType::Float32, false),
            Field::new("autonomy",     DataType::Float32, false),
            Field::new("social",       DataType::Float32, false),
            Field::new("spiritual",    DataType::Float32, false),
            Field::new("material",     DataType::Float32, false),
            Field::new("purpose",      DataType::Float32, false),
            Field::new("civ_affinity", DataType::UInt16,  false),
            Field::new("region",       DataType::UInt16,  false),
            Field::new("occupation",   DataType::UInt8,   false),
            Field::new("satisfaction", DataType::Float32, false),
            Field::new("boldness",     DataType::Float32, false),
            Field::new("ambition",     DataType::Float32, false),
            Field::new("loyalty_trait",DataType::Float32, false),
        ]));

        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(agent_id_col.finish())    as _,
                Arc::new(safety_col.finish())       as _,
                Arc::new(autonomy_col.finish())     as _,
                Arc::new(social_col.finish())       as _,
                Arc::new(spiritual_col.finish())    as _,
                Arc::new(material_col.finish())     as _,
                Arc::new(purpose_col.finish())      as _,
                Arc::new(civ_affinity_col.finish()) as _,
                Arc::new(region_col.finish())       as _,
                Arc::new(occupation_col.finish())   as _,
                Arc::new(satisfaction_col.finish()) as _,
                Arc::new(boldness_col.finish())     as _,
                Arc::new(ambition_col.finish())     as _,
                Arc::new(loyalty_trait_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    // -----------------------------------------------------------------------
    // M54a: Ecology FFI surface
    // -----------------------------------------------------------------------

    /// Set ecology configuration from individual field arguments.
    #[allow(clippy::too_many_arguments)]
    pub fn set_ecology_config(
        &mut self,
        soil_degradation: f32,
        soil_recovery: f32,
        mine_soil_degradation: f32,
        soil_recovery_pop_ratio: f32,
        agriculture_soil_bonus: f32,
        metallurgy_mine_reduction: f32,
        mechanization_mine_mult: f32,
        soil_pressure_threshold: f32,
        soil_pressure_streak_limit: i32,
        soil_pressure_degradation_mult: f32,
        water_drought: f32,
        water_recovery: f32,
        irrigation_water_bonus: f32,
        irrigation_drought_mult: f32,
        cooling_water_loss: f32,
        warming_tundra_water_gain: f32,
        water_factor_denominator: f32,
        forest_clearing: f32,
        forest_regrowth: f32,
        cooling_forest_damage: f32,
        forest_pop_ratio: f32,
        forest_regrowth_water_gate: f32,
        cross_effect_forest_soil: f32,
        cross_effect_forest_threshold: f32,
        disease_severity_cap: f32,
        disease_decay_rate: f32,
        flare_overcrowding_threshold: f32,
        flare_overcrowding_spike: f32,
        flare_army_spike: f32,
        flare_water_spike: f32,
        flare_season_spike: f32,
        depletion_rate: f32,
        exhausted_trickle_fraction: f32,
        reserve_ramp_threshold: f32,
        resource_abundance_multiplier: f32,
        overextraction_streak_limit: i32,
        overextraction_yield_penalty: f32,
        workers_per_yield_unit: i32,
        deforestation_threshold: f32,
        deforestation_water_loss: f32,
    ) {
        self.ecology_config = crate::ecology::EcologyConfig {
            soil_degradation,
            soil_recovery,
            mine_soil_degradation,
            soil_recovery_pop_ratio,
            agriculture_soil_bonus,
            metallurgy_mine_reduction,
            mechanization_mine_mult,
            soil_pressure_threshold,
            soil_pressure_streak_limit,
            soil_pressure_degradation_mult,
            water_drought,
            water_recovery,
            irrigation_water_bonus,
            irrigation_drought_mult,
            cooling_water_loss,
            warming_tundra_water_gain,
            water_factor_denominator,
            forest_clearing,
            forest_regrowth,
            cooling_forest_damage,
            forest_pop_ratio,
            forest_regrowth_water_gate,
            cross_effect_forest_soil,
            cross_effect_forest_threshold,
            disease_severity_cap,
            disease_decay_rate,
            flare_overcrowding_threshold,
            flare_overcrowding_spike,
            flare_army_spike,
            flare_water_spike,
            flare_season_spike,
            depletion_rate,
            exhausted_trickle_fraction,
            reserve_ramp_threshold,
            resource_abundance_multiplier,
            overextraction_streak_limit,
            overextraction_yield_penalty,
            workers_per_yield_unit,
            deforestation_threshold,
            deforestation_water_loss,
        };
    }

    /// Set the river topology for ecology cascade computation.
    pub fn set_river_topology(&mut self, rivers: Vec<Vec<u16>>) {
        self.river_topology = crate::ecology::RiverTopology { rivers };
    }

    /// Run the ecology tick: mutates Rust region state, returns two Arrow batches.
    ///
    /// After this call, `regions[i].resource_yields` hold the post-ecology yields
    /// so the subsequent agent tick sees the correct values.
    pub fn tick_ecology(
        &mut self,
        turn: u32,
        climate_phase: u8,
        pandemic_mask: Vec<bool>,
        army_arrived_mask: Vec<bool>,
    ) -> PyResult<(PyRecordBatch, PyRecordBatch)> {
        if self.regions.is_empty() {
            return Err(PyValueError::new_err(
                "tick_ecology() called before set_region_state()",
            ));
        }

        let (yields, events) = crate::ecology::tick_ecology(
            &mut self.regions,
            &self.ecology_config,
            turn,
            climate_phase,
            &pandemic_mask,
            &army_arrived_mask,
            &self.river_topology,
        );

        // Write current_turn_yields into regions so the agent tick sees them.
        for (i, ys) in yields.iter().enumerate() {
            self.regions[i].resource_yields = *ys;
        }

        // Store recompute context for apply_region_postpass_patch.
        self.recompute_ctx = RecomputeContext {
            turn,
            climate_phase,
            season_id: crate::ecology::season_id_from_turn(turn),
            valid: true,
        };

        let (region_batch, event_batch) =
            build_ecology_batches(&self.regions, &yields, &events).map_err(arrow_err)?;

        Ok((PyRecordBatch::new(region_batch), PyRecordBatch::new(event_batch)))
    }

    /// Apply a narrow post-pass patch back to Rust region state.
    /// Recomputes resource_yields for regions whose ecology-affecting inputs changed.
    pub fn apply_region_postpass_patch(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let recompute_indices = apply_patch_to_regions(&mut self.regions, &rb)?;

        if !recompute_indices.is_empty() && self.recompute_ctx.valid {
            recompute_region_yields(
                &mut self.regions,
                &recompute_indices,
                &self.recompute_ctx,
                &self.ecology_config,
            );
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// EcologySimulator — off-mode wrapper (no AgentPool)
// ---------------------------------------------------------------------------

/// Lightweight ecology-only simulator for `--agents=off` mode.
/// Owns `Vec<RegionState>`, `EcologyConfig`, `RiverTopology`.
/// Does NOT create or manage an AgentPool.
/// Reuses the same ecology.rs core as AgentSimulator.
#[pyclass]
pub struct EcologySimulator {
    regions: Vec<RegionState>,
    ecology_config: crate::ecology::EcologyConfig,
    river_topology: crate::ecology::RiverTopology,
    recompute_ctx: RecomputeContext,
}

#[pymethods]
impl EcologySimulator {
    #[new]
    pub fn new() -> Self {
        Self {
            regions: Vec::new(),
            ecology_config: crate::ecology::EcologyConfig::default(),
            river_topology: crate::ecology::RiverTopology::default(),
            recompute_ctx: RecomputeContext::default(),
        }
    }

    /// Ingest region state from Python as an Arrow RecordBatch.
    /// First call initialises the regions. Subsequent calls update all fields.
    /// Does NOT spawn agents — this is the off-mode path.
    pub fn set_region_state(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();

        macro_rules! col_u16 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt16", $name)))?
            }};
        }
        macro_rules! col_u8 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt8Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt8", $name)))?
            }};
        }
        macro_rules! col_f32 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::Float32Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not Float32", $name)))?
            }};
        }

        let region_ids = col_u16!("region_id");
        let terrains = col_u8!("terrain");
        let capacities = col_u16!("carrying_capacity");
        let populations = col_u16!("population");
        let soils = col_f32!("soil");
        let waters = col_f32!("water");
        let forest_covers = col_f32!("forest_cover");

        // Optional columns with defaults
        let controller_civs = rb
            .column_by_name("controller_civ")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());

        // M54a ecology columns
        let disease_baseline_col = rb
            .column_by_name("disease_baseline")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let capacity_modifier_col = rb
            .column_by_name("capacity_modifier")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_type_0 = rb
            .column_by_name("resource_type_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_type_1 = rb
            .column_by_name("resource_type_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_type_2 = rb
            .column_by_name("resource_type_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let resource_base_yield_0_col = rb
            .column_by_name("resource_base_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_base_yield_1_col = rb
            .column_by_name("resource_base_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_base_yield_2_col = rb
            .column_by_name("resource_base_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_0_col = rb
            .column_by_name("resource_effective_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_1_col = rb
            .column_by_name("resource_effective_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_effective_yield_2_col = rb
            .column_by_name("resource_effective_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_suspension_0_col = rb
            .column_by_name("resource_suspension_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let resource_suspension_1_col = rb
            .column_by_name("resource_suspension_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let resource_suspension_2_col = rb
            .column_by_name("resource_suspension_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let has_irrigation_col = rb
            .column_by_name("has_irrigation")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let has_mines_col = rb
            .column_by_name("has_mines")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let active_focus_col = rb
            .column_by_name("active_focus")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let prev_turn_water_col = rb
            .column_by_name("prev_turn_water")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let soil_pressure_streak_col = rb
            .column_by_name("soil_pressure_streak")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_0_col = rb
            .column_by_name("overextraction_streak_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_1_col = rb
            .column_by_name("overextraction_streak_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let overextraction_streak_2_col = rb
            .column_by_name("overextraction_streak_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Int32Array>());
        let resource_reserve_0 = rb
            .column_by_name("resource_reserve_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_reserve_1 = rb
            .column_by_name("resource_reserve_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_reserve_2 = rb
            .column_by_name("resource_reserve_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_yield_0 = rb
            .column_by_name("resource_yield_0")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_yield_1 = rb
            .column_by_name("resource_yield_1")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let resource_yield_2 = rb
            .column_by_name("resource_yield_2")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let endemic_severity_col = rb
            .column_by_name("endemic_severity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());

        // M55a (optional, ecology doesn't use but must not reject)
        let is_capital_col = rb
            .column_by_name("is_capital")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let temple_prestige_col = rb
            .column_by_name("temple_prestige")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());

        if self.regions.is_empty() {
            // First call: initialize regions.
            self.regions = (0..n)
                .map(|i| {
                    let mut r = RegionState::new(region_ids.value(i));
                    r.terrain = terrains.value(i);
                    r.carrying_capacity = capacities.value(i);
                    r.population = populations.value(i);
                    r.soil = soils.value(i);
                    r.water = waters.value(i);
                    r.forest_cover = forest_covers.value(i);
                    r.controller_civ = controller_civs.map_or(255, |arr| arr.value(i));
                    // Ecology fields
                    r.disease_baseline = disease_baseline_col.map_or(0.0, |arr| arr.value(i));
                    r.capacity_modifier = capacity_modifier_col.map_or(1.0, |arr| arr.value(i));
                    r.resource_types = [
                        resource_type_0.map_or(255, |arr| arr.value(i)),
                        resource_type_1.map_or(255, |arr| arr.value(i)),
                        resource_type_2.map_or(255, |arr| arr.value(i)),
                    ];
                    r.resource_base_yield = [
                        resource_base_yield_0_col.map_or(0.0, |arr| arr.value(i)),
                        resource_base_yield_1_col.map_or(0.0, |arr| arr.value(i)),
                        resource_base_yield_2_col.map_or(0.0, |arr| arr.value(i)),
                    ];
                    r.resource_effective_yield = [
                        resource_effective_yield_0_col.map_or(0.0, |arr| arr.value(i)),
                        resource_effective_yield_1_col.map_or(0.0, |arr| arr.value(i)),
                        resource_effective_yield_2_col.map_or(0.0, |arr| arr.value(i)),
                    ];
                    r.resource_suspension = [
                        resource_suspension_0_col.map_or(false, |arr| arr.value(i)),
                        resource_suspension_1_col.map_or(false, |arr| arr.value(i)),
                        resource_suspension_2_col.map_or(false, |arr| arr.value(i)),
                    ];
                    r.has_irrigation = has_irrigation_col.map_or(false, |arr| arr.value(i));
                    r.has_mines = has_mines_col.map_or(false, |arr| arr.value(i));
                    r.active_focus = active_focus_col.map_or(0, |arr| arr.value(i));
                    r.prev_turn_water = prev_turn_water_col.map_or(0.0, |arr| arr.value(i));
                    r.soil_pressure_streak = soil_pressure_streak_col.map_or(0, |arr| arr.value(i));
                    r.overextraction_streak = [
                        overextraction_streak_0_col.map_or(0, |arr| arr.value(i)),
                        overextraction_streak_1_col.map_or(0, |arr| arr.value(i)),
                        overextraction_streak_2_col.map_or(0, |arr| arr.value(i)),
                    ];
                    r.resource_reserves = [
                        resource_reserve_0.map_or(1.0, |arr| arr.value(i)),
                        resource_reserve_1.map_or(1.0, |arr| arr.value(i)),
                        resource_reserve_2.map_or(1.0, |arr| arr.value(i)),
                    ];
                    r.resource_yields = [
                        resource_yield_0.map_or(0.0, |arr| arr.value(i)),
                        resource_yield_1.map_or(0.0, |arr| arr.value(i)),
                        resource_yield_2.map_or(0.0, |arr| arr.value(i)),
                    ];
                    r.endemic_severity = endemic_severity_col.map_or(0.0, |arr| arr.value(i));
                    r.is_capital = is_capital_col.map_or(false, |arr| arr.value(i));
                    r.temple_prestige = temple_prestige_col.map_or(0.0, |arr| arr.value(i));
                    r
                })
                .collect();
        } else {
            // Subsequent calls: update all fields.
            if self.regions.len() != n {
                return Err(PyValueError::new_err(
                    "set_region_state: row count changed between calls",
                ));
            }
            for i in 0..n {
                let r = &mut self.regions[i];
                r.terrain = terrains.value(i);
                r.carrying_capacity = capacities.value(i);
                r.population = populations.value(i);
                r.soil = soils.value(i);
                r.water = waters.value(i);
                r.forest_cover = forest_covers.value(i);
                r.controller_civ = controller_civs.map_or(r.controller_civ, |arr| arr.value(i));
                if let Some(arr) = disease_baseline_col { r.disease_baseline = arr.value(i); }
                if let Some(arr) = capacity_modifier_col { r.capacity_modifier = arr.value(i); }
                r.resource_types[0] = resource_type_0.map_or(r.resource_types[0], |arr| arr.value(i));
                r.resource_types[1] = resource_type_1.map_or(r.resource_types[1], |arr| arr.value(i));
                r.resource_types[2] = resource_type_2.map_or(r.resource_types[2], |arr| arr.value(i));
                if let Some(arr) = resource_base_yield_0_col { r.resource_base_yield[0] = arr.value(i); }
                if let Some(arr) = resource_base_yield_1_col { r.resource_base_yield[1] = arr.value(i); }
                if let Some(arr) = resource_base_yield_2_col { r.resource_base_yield[2] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_0_col { r.resource_effective_yield[0] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_1_col { r.resource_effective_yield[1] = arr.value(i); }
                if let Some(arr) = resource_effective_yield_2_col { r.resource_effective_yield[2] = arr.value(i); }
                r.resource_suspension[0] = resource_suspension_0_col.map_or(false, |arr| arr.value(i));
                r.resource_suspension[1] = resource_suspension_1_col.map_or(false, |arr| arr.value(i));
                r.resource_suspension[2] = resource_suspension_2_col.map_or(false, |arr| arr.value(i));
                r.has_irrigation = has_irrigation_col.map_or(false, |arr| arr.value(i));
                r.has_mines = has_mines_col.map_or(false, |arr| arr.value(i));
                if let Some(arr) = active_focus_col { r.active_focus = arr.value(i); }
                if let Some(arr) = prev_turn_water_col { r.prev_turn_water = arr.value(i); }
                if let Some(arr) = soil_pressure_streak_col { r.soil_pressure_streak = arr.value(i); }
                if let Some(arr) = overextraction_streak_0_col { r.overextraction_streak[0] = arr.value(i); }
                if let Some(arr) = overextraction_streak_1_col { r.overextraction_streak[1] = arr.value(i); }
                if let Some(arr) = overextraction_streak_2_col { r.overextraction_streak[2] = arr.value(i); }
                r.resource_reserves[0] = resource_reserve_0.map_or(r.resource_reserves[0], |arr| arr.value(i));
                r.resource_reserves[1] = resource_reserve_1.map_or(r.resource_reserves[1], |arr| arr.value(i));
                r.resource_reserves[2] = resource_reserve_2.map_or(r.resource_reserves[2], |arr| arr.value(i));
                r.resource_yields[0] = resource_yield_0.map_or(r.resource_yields[0], |arr| arr.value(i));
                r.resource_yields[1] = resource_yield_1.map_or(r.resource_yields[1], |arr| arr.value(i));
                r.resource_yields[2] = resource_yield_2.map_or(r.resource_yields[2], |arr| arr.value(i));
                r.endemic_severity = endemic_severity_col.map_or(r.endemic_severity, |arr| arr.value(i));
                r.is_capital = is_capital_col.map_or(false, |arr| arr.value(i));
                r.temple_prestige = temple_prestige_col.map_or(0.0, |arr| arr.value(i));
            }
        }
        Ok(())
    }

    /// Set ecology configuration.
    #[allow(clippy::too_many_arguments)]
    pub fn set_ecology_config(
        &mut self,
        soil_degradation: f32,
        soil_recovery: f32,
        mine_soil_degradation: f32,
        soil_recovery_pop_ratio: f32,
        agriculture_soil_bonus: f32,
        metallurgy_mine_reduction: f32,
        mechanization_mine_mult: f32,
        soil_pressure_threshold: f32,
        soil_pressure_streak_limit: i32,
        soil_pressure_degradation_mult: f32,
        water_drought: f32,
        water_recovery: f32,
        irrigation_water_bonus: f32,
        irrigation_drought_mult: f32,
        cooling_water_loss: f32,
        warming_tundra_water_gain: f32,
        water_factor_denominator: f32,
        forest_clearing: f32,
        forest_regrowth: f32,
        cooling_forest_damage: f32,
        forest_pop_ratio: f32,
        forest_regrowth_water_gate: f32,
        cross_effect_forest_soil: f32,
        cross_effect_forest_threshold: f32,
        disease_severity_cap: f32,
        disease_decay_rate: f32,
        flare_overcrowding_threshold: f32,
        flare_overcrowding_spike: f32,
        flare_army_spike: f32,
        flare_water_spike: f32,
        flare_season_spike: f32,
        depletion_rate: f32,
        exhausted_trickle_fraction: f32,
        reserve_ramp_threshold: f32,
        resource_abundance_multiplier: f32,
        overextraction_streak_limit: i32,
        overextraction_yield_penalty: f32,
        workers_per_yield_unit: i32,
        deforestation_threshold: f32,
        deforestation_water_loss: f32,
    ) {
        self.ecology_config = crate::ecology::EcologyConfig {
            soil_degradation,
            soil_recovery,
            mine_soil_degradation,
            soil_recovery_pop_ratio,
            agriculture_soil_bonus,
            metallurgy_mine_reduction,
            mechanization_mine_mult,
            soil_pressure_threshold,
            soil_pressure_streak_limit,
            soil_pressure_degradation_mult,
            water_drought,
            water_recovery,
            irrigation_water_bonus,
            irrigation_drought_mult,
            cooling_water_loss,
            warming_tundra_water_gain,
            water_factor_denominator,
            forest_clearing,
            forest_regrowth,
            cooling_forest_damage,
            forest_pop_ratio,
            forest_regrowth_water_gate,
            cross_effect_forest_soil,
            cross_effect_forest_threshold,
            disease_severity_cap,
            disease_decay_rate,
            flare_overcrowding_threshold,
            flare_overcrowding_spike,
            flare_army_spike,
            flare_water_spike,
            flare_season_spike,
            depletion_rate,
            exhausted_trickle_fraction,
            reserve_ramp_threshold,
            resource_abundance_multiplier,
            overextraction_streak_limit,
            overextraction_yield_penalty,
            workers_per_yield_unit,
            deforestation_threshold,
            deforestation_water_loss,
        };
    }

    /// Set the river topology.
    pub fn set_river_topology(&mut self, rivers: Vec<Vec<u16>>) {
        self.river_topology = crate::ecology::RiverTopology { rivers };
    }

    /// Run the ecology tick: mutates Rust region state, returns two Arrow batches.
    pub fn tick_ecology(
        &mut self,
        turn: u32,
        climate_phase: u8,
        pandemic_mask: Vec<bool>,
        army_arrived_mask: Vec<bool>,
    ) -> PyResult<(PyRecordBatch, PyRecordBatch)> {
        if self.regions.is_empty() {
            return Err(PyValueError::new_err(
                "tick_ecology() called before set_region_state()",
            ));
        }

        let (yields, events) = crate::ecology::tick_ecology(
            &mut self.regions,
            &self.ecology_config,
            turn,
            climate_phase,
            &pandemic_mask,
            &army_arrived_mask,
            &self.river_topology,
        );

        // Write current_turn_yields into regions.
        for (i, ys) in yields.iter().enumerate() {
            self.regions[i].resource_yields = *ys;
        }

        // Store recompute context.
        self.recompute_ctx = RecomputeContext {
            turn,
            climate_phase,
            season_id: crate::ecology::season_id_from_turn(turn),
            valid: true,
        };

        let (region_batch, event_batch) =
            build_ecology_batches(&self.regions, &yields, &events).map_err(arrow_err)?;

        Ok((PyRecordBatch::new(region_batch), PyRecordBatch::new(event_batch)))
    }

    /// Apply a narrow post-pass patch back to Rust region state.
    pub fn apply_region_postpass_patch(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let recompute_indices = apply_patch_to_regions(&mut self.regions, &rb)?;

        if !recompute_indices.is_empty() && self.recompute_ctx.valid {
            recompute_region_yields(
                &mut self.regions,
                &recompute_indices,
                &self.recompute_ctx,
                &self.ecology_config,
            );
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Event serialization
// ---------------------------------------------------------------------------

/// Convert a slice of AgentEvents into an Arrow RecordBatch using events_schema().
fn events_to_batch(events: &[crate::tick::AgentEvent]) -> Result<RecordBatch, ArrowError> {
    let n = events.len();
    let mut agent_ids = UInt32Builder::with_capacity(n);
    let mut event_types = UInt8Builder::with_capacity(n);
    let mut regions = UInt16Builder::with_capacity(n);
    let mut target_regions = UInt16Builder::with_capacity(n);
    let mut civ_affinities = UInt16Builder::with_capacity(n);
    let mut occupations = UInt8Builder::with_capacity(n);
    let mut turns = UInt32Builder::with_capacity(n);

    for e in events {
        agent_ids.append_value(e.agent_id);
        event_types.append_value(e.event_type);
        regions.append_value(e.region);
        target_regions.append_value(e.target_region);
        civ_affinities.append_value(e.civ_affinity as u16);
        occupations.append_value(e.occupation);
        turns.append_value(e.turn);
    }

    let schema = Arc::new(events_schema());
    RecordBatch::try_new(
        schema,
        vec![
            Arc::new(agent_ids.finish()) as _,
            Arc::new(event_types.finish()) as _,
            Arc::new(regions.finish()) as _,
            Arc::new(target_regions.finish()) as _,
            Arc::new(civ_affinities.finish()) as _,
            Arc::new(occupations.finish()) as _,
            Arc::new(turns.finish()) as _,
        ],
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow::array::{Int8Array, UInt8Array, UInt16Array, UInt32Array};
    use arrow::datatypes::{DataType, Field, Schema};
    use pyo3_arrow::PyRecordBatch;

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
}
