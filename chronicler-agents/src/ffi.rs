//! Arrow FFI layer: centralized schemas and the AgentSimulator PyO3 class.

use std::sync::Arc;

use arrow::datatypes::{DataType, Field, Schema};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use crate::agent::Occupation;
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
        Field::new("turn", DataType::UInt32, false),
    ])
}

/// Schema for `set_region_state()` input.
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

// ---------------------------------------------------------------------------
// AgentSimulator
// ---------------------------------------------------------------------------

/// Python-facing AgentSimulator. Manages an `AgentPool` and a list of
/// `RegionState`s; exchanges data with Python via Arrow PyCapsules.
#[pyclass]
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    master_seed: [u8; 32],
    num_regions: usize,
    turn: u32,
    initialized: bool,
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
            master_seed,
            num_regions,
            turn: 0,
            initialized: false,
        }
    }

    /// Ingest region state from Python as an Arrow RecordBatch.
    ///
    /// First call initialises the regions and spawns agents proportional to
    /// carrying capacity (60% farmer, 15% soldier, 10% merchant, 10%
    /// scholar, ~5% priest).  Subsequent calls update ecology fields only.
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
                    adjacency_mask: 0,
                    controller_civ: 255,
                    trade_route_count: 0,
                })
                .collect();

            // Spawn agents proportional to carrying capacity.
            // Distribution: 60% farmer, 15% soldier, 10% merchant, 10% scholar, ~5% priest
            for i in 0..n {
                let cap = capacities.value(i) as usize;
                let region_id = region_ids.value(i);
                // Use civ_affinity = region_id as u8 (placeholder; M26 will assign proper civs)
                let civ = (region_id % 256) as u8;

                let n_farmer = (cap * 60 + 50) / 100;
                let n_soldier = (cap * 15 + 50) / 100;
                let n_merchant = (cap * 10 + 50) / 100;
                let n_scholar = (cap * 10 + 50) / 100;
                let spawned = n_farmer + n_soldier + n_merchant + n_scholar;
                let n_priest = if cap > spawned { cap - spawned } else { 0 };

                for _ in 0..n_farmer {
                    self.pool.spawn(region_id, civ, Occupation::Farmer, 0);
                }
                for _ in 0..n_soldier {
                    self.pool.spawn(region_id, civ, Occupation::Soldier, 0);
                }
                for _ in 0..n_merchant {
                    self.pool.spawn(region_id, civ, Occupation::Merchant, 0);
                }
                for _ in 0..n_scholar {
                    self.pool.spawn(region_id, civ, Occupation::Scholar, 0);
                }
                for _ in 0..n_priest {
                    self.pool.spawn(region_id, civ, Occupation::Priest, 0);
                }
            }

            self.initialized = true;
        } else {
            // Subsequent calls: update ecology fields only.
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
            }
        }
        Ok(())
    }

    /// Advance simulation by one turn. Returns an events RecordBatch.
    pub fn tick(&mut self, turn: u32) -> PyResult<PyRecordBatch> {
        if !self.initialized {
            return Err(PyValueError::new_err(
                "tick() called before set_region_state()",
            ));
        }
        self.turn = turn;

        // Build default signals when none provided via FFI (M26 Task 11 will add proper signal ingestion).
        let signals = crate::signals::TickSignals {
            civs: Vec::new(),
            contested_regions: vec![false; self.regions.len()],
        };
        let _events = crate::tick::tick_agents(
            &mut self.pool,
            &self.regions,
            &signals,
            self.master_seed,
            turn,
        );

        // Return an empty events RecordBatch with the full schema.
        // M26 Task 11 will serialize _events into this batch.
        let schema = Arc::new(events_schema());
        let batch = RecordBatch::new_empty(schema);
        Ok(PyRecordBatch::new(batch))
    }

    /// Return an Arrow RecordBatch snapshot of all alive agents.
    pub fn get_snapshot(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.to_record_batch().map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return per-civ aggregate stats as an Arrow RecordBatch.
    pub fn get_aggregates(&self) -> PyResult<PyRecordBatch> {
        let batch = self.pool.compute_aggregates().map_err(arrow_err)?;
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
}
