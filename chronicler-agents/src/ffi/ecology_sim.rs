//! EcologySimulator — off-mode wrapper (no AgentPool).
//!
//! Lightweight ecology-only simulator for `--agents=off` mode.
//! Owns `Vec<RegionState>`, `EcologyConfig`, `RiverTopology`.
//! Does NOT create or manage an AgentPool.
//! Reuses the same ecology.rs core as AgentSimulator.

use std::sync::Arc;

use arrow::array::{UInt8Builder, UInt16Builder};
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use crate::region::RegionState;
use super::batch::{arrow_err, build_ecology_batches, apply_patch_to_regions, recompute_region_yields, RecomputeContext};
use super::schema::ecology_region_schema;

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

