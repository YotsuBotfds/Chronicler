//! PoliticsSimulator — off-mode wrapper (no AgentPool).
//!
//! Lightweight politics-only simulator for `--agents=off` mode.
//! Executes the same 11-step Rust politics pass without any agent pool.

use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use crate::politics::PoliticsConfig;
use super::batch::tick_politics_impl;

#[pyclass]
pub struct PoliticsSimulator {
    politics_config: PoliticsConfig,
}

#[pymethods]
impl PoliticsSimulator {
    #[new]
    pub fn new() -> Self {
        Self {
            politics_config: PoliticsConfig::default(),
        }
    }

    /// Set politics configuration from individual field arguments.
    #[allow(clippy::too_many_arguments)]
    pub fn set_politics_config(
        &mut self,
        secession_stability_threshold: i32,
        secession_surveillance_threshold: i32,
        proxy_war_secession_bonus: f32,
        secession_stability_loss: i32,
        secession_likelihood_multiplier: f32,
        capital_loss_stability: i32,
        vassal_rebellion_base_prob: f32,
        vassal_rebellion_reduced_prob: f32,
        federation_allied_turns: i32,
        federation_exit_stability: i32,
        federation_remaining_stability: i32,
        restoration_base_prob: f32,
        restoration_recognition_bonus: f32,
        twilight_absorption_decline: i32,
        severity_stress_divisor: f32,
        severity_stress_scale: f32,
        severity_cap: f32,
        severity_multiplier: f32,
    ) {
        self.politics_config = PoliticsConfig {
            secession_stability_threshold,
            secession_surveillance_threshold,
            proxy_war_secession_bonus,
            secession_stability_loss,
            secession_likelihood_multiplier,
            capital_loss_stability,
            vassal_rebellion_base_prob,
            vassal_rebellion_reduced_prob,
            federation_allied_turns,
            federation_exit_stability,
            federation_remaining_stability,
            restoration_base_prob,
            restoration_recognition_bonus,
            twilight_absorption_decline,
            severity_stress_divisor,
            severity_stress_scale,
            severity_cap,
            severity_multiplier,
        };
    }

    /// Run the 11-step Phase 10 politics pass (off-mode, no pool).
    ///
    /// Same signature and return type as `AgentSimulator.tick_politics()`.
    #[allow(clippy::too_many_arguments, clippy::type_complexity)]
    pub fn tick_politics(
        &self,
        civ_batch: PyRecordBatch,
        region_batch: PyRecordBatch,
        relationship_batch: PyRecordBatch,
        vassal_batch: PyRecordBatch,
        federation_batch: PyRecordBatch,
        war_batch: PyRecordBatch,
        embargo_batch: PyRecordBatch,
        proxy_war_batch: PyRecordBatch,
        exile_batch: PyRecordBatch,
        turn: u32,
        seed: u64,
        hybrid_mode: bool,
    ) -> PyResult<(PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch,
                   PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch,
                   PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch)> {
        tick_politics_impl(
            civ_batch, region_batch, relationship_batch, vassal_batch,
            federation_batch, war_batch, embargo_batch, proxy_war_batch,
            exile_batch, turn, seed, hybrid_mode, &self.politics_config,
        )
    }
}

