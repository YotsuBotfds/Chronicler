//! Arrow FFI layer: centralized schemas and the AgentSimulator PyO3 class.

use std::sync::Arc;

use arrow::array::{UInt8Builder, UInt16Builder, UInt32Builder, StringBuilder};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use rand::SeedableRng;
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
// AgentSimulator
// ---------------------------------------------------------------------------

/// Python-facing AgentSimulator. Manages an `AgentPool` and a list of
/// `RegionState`s; exchanges data with Python via Arrow PyCapsules.
#[pyclass]
pub struct AgentSimulator {
    pool: AgentPool,
    regions: Vec<RegionState>,
    contested_regions: Vec<bool>,
    master_seed: [u8; 32],
    num_regions: usize,
    turn: u32,
    registry: crate::named_characters::NamedCharacterRegistry,
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
            contested_regions: Vec::new(),
            master_seed,
            num_regions,
            turn: 0,
            registry: crate::named_characters::NamedCharacterRegistry::new(),
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
                })
                .collect();

            // Spawn agents proportional to carrying capacity.
            // Distribution: 60% farmer, 15% soldier, 10% merchant, 10% scholar, ~5% priest
            for i in 0..n {
                let cap = capacities.value(i) as usize;
                let region_id = region_ids.value(i);
                let civ = if self.regions[i].controller_civ != 255 {
                    self.regions[i].controller_civ
                } else {
                    (region_id % 256) as u8  // fallback for uncontrolled
                };

                let n_farmer = (cap * 60 + 50) / 100;
                let n_soldier = (cap * 15 + 50) / 100;
                let n_merchant = (cap * 10 + 50) / 100;
                let n_scholar = (cap * 10 + 50) / 100;
                let spawned = n_farmer + n_soldier + n_merchant + n_scholar;
                let n_priest = if cap > spawned { cap - spawned } else { 0 };

                // M33: personality assignment at initial spawn
                let mut personality_rng = ChaCha8Rng::from_seed(self.master_seed);
                personality_rng.set_stream(
                    region_id as u64 * 1000 + crate::agent::PERSONALITY_STREAM_OFFSET,
                );
                let civ_mean = [0.0f32; 3]; // Civ means not yet available at initial spawn

                for _ in 0..n_farmer {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Farmer, 0, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY);
                }
                for _ in 0..n_soldier {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Soldier, 0, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY);
                }
                for _ in 0..n_merchant {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Merchant, 0, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY);
                }
                for _ in 0..n_scholar {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Scholar, 0, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY);
                }
                for _ in 0..n_priest {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    self.pool.spawn(region_id, civ, Occupation::Priest, 0, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY);
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
        let events = crate::tick::tick_agents(
            &mut self.pool,
            &self.regions,
            &signals,
            self.master_seed,
            turn,
        );

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
}
