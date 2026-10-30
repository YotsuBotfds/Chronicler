//! Arrow FFI layer: schemas, batch helpers, and PyO3 simulator classes.
//!
//! Split into focused modules (audit batch I, 2026-04-01):
//!   - `schema.rs`       — Arrow schema definitions
//!   - `batch.rs`        — RecordBatch building/parsing + shared helpers
//!   - `ecology_sim.rs`  — EcologySimulator (off-mode ecology)
//!   - `politics_sim.rs` — PoliticsSimulator (off-mode politics)
//!   - `mod.rs`          — AgentSimulator + re-exports

pub mod schema;
pub mod batch;
mod ecology_sim;
mod politics_sim;

// Re-export everything that was public from the old monolithic ffi.rs
pub use schema::*;
pub use batch::{arrow_err, personality_label};
pub(crate) use batch::RecomputeContext;
pub use ecology_sim::EcologySimulator;
pub use politics_sim::PoliticsSimulator;

// Import batch internals needed by AgentSimulator in this module
use batch::{
    build_ecology_batches, apply_patch_to_regions, recompute_region_yields,
    events_to_batch, tick_politics_impl,
};

use std::sync::Arc;

use arrow::array::{Int8Builder, UInt8Builder, UInt16Builder, UInt32Builder, StringBuilder};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;

use crate::agent::Occupation;
use crate::pool::AgentPool;
use crate::region::{mask_to_ids, normalize_ids, RegionState};
use crate::politics::PoliticsConfig;

// Match the Python bridge's count limit; region id 65535 remains a sentinel.
const MAX_NATIVE_REGIONS: usize = u16::MAX as usize;

fn validate_native_region_count(num_regions: usize) -> Result<(), &'static str> {
    if num_regions > MAX_NATIVE_REGIONS {
        Err("AgentSimulator supports at most 65535 regions")
    } else {
        Ok(())
    }
}

/// Geography 2.0: read one sorted region/river id list per row.
///
/// Prefers the `List<UInt16>` column `list_name`; falls back to the legacy
/// u32 bitmask column `mask_name` (decoded in ascending bit order, exactly the
/// order the former bitmask walks used). Returns `None` when neither column is
/// present so callers keep their previous value / default.
pub(crate) fn read_region_id_lists(
    rb: &RecordBatch,
    list_name: &str,
    mask_name: &str,
) -> PyResult<Option<Vec<Vec<u16>>>> {
    use arrow::array::Array;
    if let Some(col) = rb.column_by_name(list_name) {
        let list = col
            .as_any()
            .downcast_ref::<arrow::array::ListArray>()
            .ok_or_else(|| PyValueError::new_err(format!("column {list_name} not List<UInt16>")))?;
        let mut out = Vec::with_capacity(list.len());
        for i in 0..list.len() {
            let mut ids: Vec<u16> = if list.is_null(i) {
                Vec::new()
            } else {
                let inner = list.value(i);
                let values = inner
                    .as_any()
                    .downcast_ref::<arrow::array::UInt16Array>()
                    .ok_or_else(|| {
                        PyValueError::new_err(format!("column {list_name} inner not UInt16"))
                    })?;
                values.values().to_vec()
            };
            normalize_ids(&mut ids);
            out.push(ids);
        }
        return Ok(Some(out));
    }
    Ok(rb
        .column_by_name(mask_name)
        .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt32Array>())
        .map(|masks| (0..masks.len()).map(|i| mask_to_ids(masks.value(i))).collect()))
}

// ---------------------------------------------------------------------------
// AgentSimulator
// ---------------------------------------------------------------------------

/// One memory entry in a batched agent context, in the scalar getter's order.
pub type AgentContextMemory = (u8, u8, u16, i8, u8, bool);
/// Safety, material, social, spiritual, autonomy and purpose, without arithmetic.
pub type AgentContextNeeds = (f32, f32, f32, f32, f32, f32);
/// Target id, sentiment, bond type and formation turn, in native store order.
pub type AgentContextRelationship = (u32, i8, u8, u16);
/// Requested id and the complete results of the three scalar context getters.
pub type AgentContextRow = (
    u32,
    Vec<AgentContextMemory>,
    Option<AgentContextNeeds>,
    Option<Vec<AgentContextRelationship>>,
);

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
    // M55a: Spatial substrate state
    spatial_grids: Vec<crate::spatial::SpatialGrid>,
    attractors: Vec<crate::spatial::RegionAttractors>,
    spatial_initialized: bool,
    last_spatial_diag: crate::spatial::SpatialDiagnostics,
    // M54b: economy state
    economy_config: crate::economy::EconomyConfig,
    // M54c: politics state
    politics_config: PoliticsConfig,
    // M56b: Per-region settlement lookup grids
    settlement_grids: Vec<[u16; 100]>,
    // M57b: household stats from last tick
    household_stats: crate::household::HouseholdStats,
    // M58a: merchant mobility state
    merchant_graph: Option<crate::merchant::RouteGraph>,
    /// Bulk trade: cargo per trip by mode of travel, applied to every graph.
    merchant_cargo: crate::merchant::CargoConfig,
    merchant_ledger: Option<crate::merchant::ShadowLedger>,
    merchant_delivery_buf: Option<crate::merchant::DeliveryBuffer>,
    merchant_trip_stats: crate::merchant::MerchantTripStats,
    knowledge_stats: crate::knowledge::KnowledgeStats,
    /// M58b: when true, economy tick consumes delivery buffer instead of tatonnement.
    hybrid_economy_mode: bool,
    /// M60b: stable agent ids queued by Python war casualties; drained by the next tick.
    pending_targeted_deaths: Vec<u32>,
    /// Agent movements: the table Python sends each tick (enabled by the
    /// first `set_movement_table`), re-seeding requests and the last stats.
    movements: crate::movements::MovementRuntime,
    /// Agent movements: (agent id, role) queued by `queue_movement_leaders`
    /// for the next `get_promotions()`, which drains it.
    pending_movement_leaders: Vec<(u32, u8)>,
    /// M48: Promotion memories queued by `get_promotions()` as (promotion
    /// turn, intent). Written at the start of the next `tick()` so the
    /// same-turn Python Mule roll still sees only pre-promotion memories.
    pending_promotion_memories: Vec<(u16, crate::memory::MemoryIntent)>,
    /// Agent-scale mode and other per-tick options (default: exact).
    tick_options: crate::scale::TickOptions,
    /// The last `get_snapshot()` batch while the pool is unchanged. Every
    /// `&mut self` Python method drops it first, except the three that only
    /// read the pool (`get_promotions`, `queue_targeted_deaths`,
    /// `tick_economy`); `to_record_batch` is a pure function of the pool, so
    /// a held batch equals a fresh export. Arrow arrays are shared, so
    /// handing it out again copies nothing.
    snapshot_cache: Option<arrow::record_batch::RecordBatch>,
    /// Rebuilt from Python episodes before economy; consumed after tick.
    health_work: Option<crate::health_care::HealthWork>,
    /// Optional recorder configuration, restored by Python before each tick.
    transaction_receipts_limit: Option<usize>,
    /// Detached decision observations; neither configuration nor frame persists.
    decision_delivery_config: Option<crate::decision_delivery::DeliveryConfig>,
    decision_delivery_frame: Option<crate::decision_delivery::DeliveryFrame>,
}

impl AgentSimulator {
    /// Create a new simulator through the existing Rust API.
    ///
    /// `seed` is zero-extended to a 32-byte master seed.
    pub fn new(num_regions: usize, seed: u64) -> Self {
        validate_native_region_count(num_regions).expect("invalid native region count");
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
            spatial_grids: Vec::new(),
            attractors: Vec::new(),
            spatial_initialized: false,
            last_spatial_diag: crate::spatial::SpatialDiagnostics::default(),
            economy_config: crate::economy::EconomyConfig::default(),
            politics_config: PoliticsConfig::default(),
            settlement_grids: Vec::new(),
            household_stats: crate::household::HouseholdStats::default(),
            merchant_graph: None,
            merchant_cargo: crate::merchant::CargoConfig::default(),
            merchant_ledger: None,
            merchant_delivery_buf: None,
            merchant_trip_stats: crate::merchant::MerchantTripStats::default(),
            knowledge_stats: crate::knowledge::KnowledgeStats::default(),
            hybrid_economy_mode: false,
            pending_targeted_deaths: Vec::new(),
            movements: crate::movements::MovementRuntime::default(),
            pending_movement_leaders: Vec::new(),
            pending_promotion_memories: Vec::new(),
            tick_options: crate::scale::TickOptions::default(),
            snapshot_cache: None,
            health_work: None,
            transaction_receipts_limit: None,
            decision_delivery_config: None,
            decision_delivery_frame: None,
        }
    }
}

#[pymethods]
impl AgentSimulator {
    /// Create a simulator, preserving zero-region/empty getter support.
    #[new]
    fn py_new(num_regions: usize, seed: u64) -> PyResult<Self> {
        validate_native_region_count(num_regions).map_err(PyValueError::new_err)?;
        Ok(Self::new(num_regions, seed))
    }

    // CAREOBS_SOURCE_BEGIN: configure and immutable export
    /// Configure before the first observed whole turn. Allocation failure means
    /// unavailable evidence and returns false; physics never allocates buffers.
    #[pyo3(signature = (start_turn, manifest_sha256, *, turns = 32))]
    pub fn configure_health_care_observation(&mut self, start_turn: u32,
        manifest_sha256: &[u8], turns: u32) -> PyResult<bool> {
        if manifest_sha256.len() != 32 || turns == 0 || turns > 32
            || start_turn.checked_add(turns - 1).is_none() || self.num_regions > 4096 {
            return Err(PyValueError::new_err("invalid bounded care observation configuration"));
        }
        if self.health_work.is_some() || self.pool.health_care_observation.is_some() {
            return Err(PyValueError::new_err("care observation must be configured before preparation"));
        }
        let mut manifest = [0u8; 32];
        manifest.copy_from_slice(manifest_sha256);
        self.pool.health_care_observation = crate::health_care_observation::CareObservation::configure(
            start_turn, turns, self.num_regions, manifest);
        Ok(self.pool.health_care_observation.is_some())
    }

    /// Saved provisional prefix only: no drain, reset, hash, native read or cache.
    pub fn get_health_care_observation<'py>(&self, py: Python<'py>)
        -> Option<Bound<'py, pyo3::types::PyBytes>> {
        self.pool.health_care_observation.as_ref().and_then(|frame| frame.saved_bytes())
            .and_then(|bytes| pyo3::types::PyBytes::new_with(py, bytes.len(), |output| {
                output.copy_from_slice(bytes);
                Ok(())
            }).ok())
    }
    // CAREOBS_SOURCE_END: configure and immutable export
    #[pyo3(signature = (ids, excluded, urban, impairment, care_fraction, *, care_policy = "spouse"))]
    pub fn prepare_health_work(&mut self, ids: Vec<u32>, excluded: Vec<u32>, urban: Vec<u16>,
        impairment: f32, care_fraction: f32, care_policy: &str) -> PyResult<Vec<(u32, u16, u32, f32)>> {
        let policy = crate::health_care::CarePolicy::from_name(care_policy)
            .ok_or_else(|| PyValueError::new_err("health care policy must be spouse or retained_kin"))?;
        if !impairment.is_finite() || !(0.0..=1.0).contains(&impairment)
            || !care_fraction.is_finite() || !(0.0..=1.0).contains(&care_fraction) {
            return Err(PyValueError::new_err("health work fractions must be finite in 0..1"));
        }
        let work = if policy == crate::health_care::CarePolicy::Spouse {
            crate::health_care::prepare(&mut self.pool, &ids, &excluded, &urban,
                self.num_regions, impairment, care_fraction)
        } else {
            crate::health_care::prepare_with_policy(&mut self.pool, &ids, &excluded, &urban,
                self.num_regions, impairment, care_fraction, crate::health_care::CarePolicy::RetainedKin)
        };
        // CAREOBS_SOURCE_BEGIN: actual preparation copies
        if let Some(mut observation) = self.pool.health_care_observation.take() {
            observation.prepare(&self.pool, &work, &ids, &excluded, &urban,
                self.num_regions, impairment, care_fraction, policy);
            self.pool.health_care_observation = Some(observation);
        }
        // CAREOBS_SOURCE_END: actual preparation copies
        let rows = work.rows.clone();
        self.health_work = Some(work);
        Ok(rows)
    }

    pub fn finish_health_work(&mut self, turn: u32, rate: f32)
        -> PyResult<(Vec<(u32, u16)>, Vec<(u32, u16, u16)>, Vec<(u16, f64, f64, u32)>)> {
        if !rate.is_finite() || !(0.0..=1.0).contains(&rate) {
            return Err(PyValueError::new_err("health injury rate must be finite in 0..1"));
        }
        self.pool.health_work_loss.clear();
        // CAREOBS_SOURCE_BEGIN: missing preparation finish
        if self.health_work.is_none() {
            if let Some(observation) = &mut self.pool.health_care_observation {
                observation.missing_finish(turn);
            }
        }
        // CAREOBS_SOURCE_END: missing preparation finish
        let Some(work) = self.health_work.take() else { return Ok((Vec::new(), Vec::new(), Vec::new())) };
        // CAREOBS_FINISH_BEGIN
        let result = crate::health_care::finish(work, &self.pool, self.master_seed, turn, rate);
        if let Some(mut observation) = self.pool.health_care_observation.take() {
            observation.finish(&self.pool, turn, rate, &result);
            self.pool.health_care_observation = Some(observation);
        }
        Ok(result)
        // CAREOBS_FINISH_END
    }

    /// Exact checkpoint: every field this simulator carries between ticks,
    /// as a versioned binary blob (`crate::persist`). Reads only: taking a
    /// checkpoint never changes the simulation.
    pub fn checkpoint_state<'py>(&self, py: Python<'py>) -> Bound<'py, pyo3::types::PyBytes> {
        crate::persist::py::to_bytes(py, crate::persist::KIND_AGENT, self)
    }

    /// A simulator rebuilt from `checkpoint_state()` bytes. Refuses blobs of
    /// another simulator, state version or field layout.
    #[staticmethod]
    pub fn from_checkpoint_state(data: &[u8]) -> PyResult<Self> {
        crate::persist::py::from_bytes(crate::persist::KIND_AGENT, data)
    }

    /// (state version, layout fingerprint, schema) of this build's checkpoint state.
    #[staticmethod]
    pub fn checkpoint_schema() -> (u32, String, String) {
        crate::persist::py::describe::<Self>()
    }

    /// M60b: queue stable agent ids to die at the start of the next tick
    /// (war casualties). The queue is consumed and cleared by `tick()`.
    pub fn queue_targeted_deaths(&mut self, ids: Vec<u32>) {
        self.pending_targeted_deaths.extend(ids);
    }

    /// Agent movements: replace the movement table (one row per living
    /// movement; see `movements::parse_movement_table`). The first call
    /// enables the movement pass for every later tick.
    pub fn set_movement_table(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let rb: RecordBatch = batch.into_inner();
        self.movements.rows = crate::movements::parse_movement_table(&rb).map_err(arrow_err)?;
        self.movements.enabled = true;
        Ok(())
    }

    /// Agent movements: replace the lasting reforms in force (creed u8, civ
    /// u8, region u16, faith u8; see `movements::parse_reform_table`). Sent
    /// with every table; the agents they cover read their creed need with
    /// `movements::REFORM_NEED_CREDIT`.
    pub fn set_movement_reforms(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        self.movements.reforms = crate::movements::parse_reform_table(&rb).map_err(arrow_err)?;
        Ok(())
    }

    /// Agent movements: agents (stable ids) to promote as movement leaders
    /// with the next `get_promotions()`, with their role (0 general, 3
    /// prophet). Consumed and cleared by that call; an agent that died, is
    /// already named, or whose civ is at the caps on living named characters
    /// is skipped.
    pub fn queue_movement_leaders(&mut self, ids: Vec<u32>, roles: Vec<u8>) -> PyResult<()> {
        if ids.len() != roles.len() {
            return Err(pyo3::exceptions::PyValueError::new_err("ids and roles differ in length"));
        }
        for (id, role) in ids.into_iter().zip(roles) {
            if crate::named_characters::CharacterRole::from_leader_u8(role).is_none() {
                return Err(pyo3::exceptions::PyValueError::new_err(format!("bad leader role {role}")));
            }
            self.pending_movement_leaders.push((id, role));
        }
        Ok(())
    }

    /// Agent movements: members to re-seed per region on the next tick
    /// (movement_id u16, region u16, count u32), after a resume rebuilt the
    /// pool from region populations.
    pub fn seed_movement_members(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let rb: RecordBatch = batch.into_inner();
        self.movements.seeds.extend(crate::movements::parse_movement_seeds(&rb).map_err(arrow_err)?);
        Ok(())
    }

    /// Agent movements: enrol a new movement's founders now. Python founds
    /// it in Phase 10, after this turn's tick; enrolling then keeps a living
    /// movement from standing without members until the next tick (see
    /// `movements::seed_founding`; draws nothing). Returns (regions, counts)
    /// of the members enrolled; nothing before the first movement table.
    pub fn found_movement(
        &mut self,
        movement_id: u16,
        creed: u8,
        target_civ: u8,
        region: u16,
        founder_id: u32,
        settlement: u16,
    ) -> PyResult<(Vec<u16>, Vec<u32>)> {
        if creed > crate::movements::CREED_GUILD {
            return Err(pyo3::exceptions::PyValueError::new_err(format!("bad creed {creed}")));
        }
        if !self.movements.enabled || region as usize >= self.num_regions {
            return Ok((Vec::new(), Vec::new()));
        }
        self.snapshot_cache = None; // pool changes: drop the cached snapshot
        let mut row = crate::movements::MovementRow::new(
            movement_id, creed, crate::movements::STAGE_GATHERING, target_civ);
        row.settlement = settlement;
        let enrolled = crate::movements::seed_founding(
            &mut self.pool, &self.movements, &row, region, founder_id);
        Ok(enrolled.into_iter().unzip())
    }

    /// Agent movements: the last pass's stats, (per region, per movement).
    pub fn get_movement_stats(&self) -> PyResult<(PyRecordBatch, PyRecordBatch)> {
        let (regions, movements) =
            crate::movements::movement_stats_batches(&self.movements.stats).map_err(arrow_err)?;
        Ok((PyRecordBatch::new(regions), PyRecordBatch::new(movements)))
    }

    /// Whether the movement pass is enabled (a table was set).
    pub fn movements_enabled(&self) -> bool {
        self.movements.enabled
    }

    /// M60b: number of queued targeted deaths not yet consumed by a tick.
    pub fn pending_targeted_death_count(&self) -> usize {
        self.pending_targeted_deaths.len()
    }

    /// Agent-scale mode for later ticks: `"exact"` (default; byte-identical
    /// reference algorithms) or `"fast"` (bounded-work candidate sampling
    /// for spatial drift, marriage and formation; changes results).
    pub fn set_agent_scale_mode(&mut self, mode: &str) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let parsed = crate::scale::AgentScaleMode::parse(mode).ok_or_else(|| {
            PyValueError::new_err(format!(
                "agent scale mode must be 'exact' or 'fast', got {mode:?}"
            ))
        })?;
        self.tick_options.scale_mode = parsed;
        Ok(())
    }

    /// Current agent-scale mode (`"exact"` or `"fast"`).
    #[getter]
    pub fn agent_scale_mode(&self) -> &'static str {
        self.tick_options.scale_mode.as_str()
    }

    /// Validation experiments only: switch decision terms off for every tick
    /// of turn `start_turn` or later (`scale::DecisionAblation`). `names`
    /// lists `"needs"` (the need terms of the decision and the autonomy
    /// factor of loyalty drift), `"kin_roots"` (marriage and home bonds in a
    /// migrant's roots), `"placebo"` (decision draws from another random
    /// stream, no term changed) or `"community_anchor"` (the community
    /// anchor of `set_community_anchoring`); an empty list switches nothing
    /// off. Never called by a plain run: the default ablates nothing.
    pub fn set_decision_ablation(&mut self, names: Vec<String>, start_turn: u32) -> PyResult<()> {
        let mut mask = 0u8;
        for name in &names {
            mask |= crate::scale::DecisionAblation::bit(name).ok_or_else(|| {
                PyValueError::new_err(format!(
                    "decision ablation must be 'needs', 'kin_roots', 'placebo' or 'community_anchor', got {name:?}"
                ))
            })?;
        }
        self.snapshot_cache = None; // later ticks change: drop the cached snapshot
        self.tick_options.ablation = crate::scale::DecisionAblation {
            mask,
            start_turn: if mask == 0 { 0 } else { start_turn },
        };
        Ok(())
    }

    /// The decision ablation in force: (names, start turn); ([], 0) when none.
    #[getter]
    pub fn decision_ablation(&self) -> (Vec<&'static str>, u32) {
        let a = self.tick_options.ablation;
        (crate::scale::DecisionAblation::names(a.mask), a.start_turn)
    }

    /// Community anchoring (`--community-anchoring`, `community.rs`) for
    /// later ticks: community ties at home hold an agent back from acting on
    /// a reason to move. `full_anchor` is the anchor of an agent with
    /// `COMMUNITY_FULL_TIES` ties, in utility units (default and None: the
    /// calibrated `COMMUNITY_ANCHOR`; it must be finite and not negative).
    /// Never called by a run without the switch.
    #[pyo3(signature = (enabled, full_anchor=None))]
    pub fn set_community_anchoring(&mut self, enabled: bool, full_anchor: Option<f32>) -> PyResult<()> {
        let full_anchor = full_anchor.unwrap_or(crate::community::COMMUNITY_ANCHOR);
        if !full_anchor.is_finite() || full_anchor < 0.0 {
            return Err(PyValueError::new_err(format!(
                "community anchor must be finite and not negative, got {full_anchor}"
            )));
        }
        self.snapshot_cache = None; // later ticks change: drop the cached snapshot
        self.tick_options.community_anchoring = crate::scale::CommunityAnchoring { enabled, full_anchor };
        Ok(())
    }

    /// Community anchoring in force: (enabled, full anchor).
    #[getter]
    pub fn community_anchoring(&self) -> (bool, f32) {
        let c = self.tick_options.community_anchoring;
        (c.enabled, c.full_anchor)
    }

    /// Domestic credit (`--domestic-credit`): the merchant agents' wealth by
    /// home region (a merchant on a trip counts at the region its trip
    /// started from), as (total wealth, merchants) per region index. Reads
    /// only. Never called by a run without the switch.
    pub fn merchant_wealth_by_region(&self) -> (Vec<f64>, Vec<u32>) {
        crate::credit::merchant_wealth_by_region(&self.pool, self.regions.len())
    }

    /// Domestic credit: add (positive) or take (negative) `amounts[i]` from
    /// the wealth of the merchants of region `region_ids[i]` (principal
    /// lent, interest and repayments; `credit::apply_merchant_transfers`).
    /// Returns the change actually made for each entry; nothing is kept for
    /// a later call. Never called by a run without the switch.
    pub fn apply_merchant_transfers(&mut self, region_ids: Vec<u16>, amounts: Vec<f64>) -> PyResult<Vec<f64>> {
        if region_ids.len() != amounts.len() {
            return Err(PyValueError::new_err(format!(
                "apply_merchant_transfers: {} region ids for {} amounts", region_ids.len(), amounts.len()
            )));
        }
        if let Some(bad) = amounts.iter().find(|a| !a.is_finite()) {
            return Err(PyValueError::new_err(format!("apply_merchant_transfers: amount {bad} is not finite")));
        }
        self.snapshot_cache = None; // the pool changes: drop the cached snapshot
        Ok(crate::credit::apply_merchant_transfers(&mut self.pool, self.regions.len(), &region_ids, &amounts))
    }

    /// Profiling only: when on, later ticks at 100,000 agents or more also
    /// time the (unused) Morton sort of the spatial step and report it as
    /// `get_spatial_diagnostics()["sort_time_us"]`. Off by default (the
    /// report is then 0); results are the same either way.
    pub fn set_spatial_sort_profiling(&mut self, enabled: bool) {
        self.tick_options.profile_spatial_sort = enabled;
    }

    /// Whether the spatial sort timing is on (`set_spatial_sort_profiling`).
    #[getter]
    pub fn spatial_sort_profiling(&self) -> bool {
        self.tick_options.profile_spatial_sort
    }

    /// Ingest region state from Python as an Arrow RecordBatch.
    ///
    /// First call initialises the regions and spawns agents from the supplied
    /// population column (60% farmer, 15% soldier, 10% merchant, 10%
    /// scholar, ~5% priest). Subsequent calls update ecology fields only.
    pub fn set_region_state(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();

        // Refuse shape changes before invalidating caches or changing any state.
        if !self.initialized {
            validate_native_region_count(self.num_regions).map_err(PyValueError::new_err)?;
            if n != self.num_regions {
                return Err(PyValueError::new_err(format!(
                    "set_region_state: expected {} initial region rows (at most 65535), got {n}",
                    self.num_regions,
                )));
            }
        } else if self.regions.len() != n {
            return Err(PyValueError::new_err(
                "set_region_state: row count changed between calls",
            ));
        }

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
        if !self.initialized && region_ids.iter().enumerate().any(|(i, id)| id != Some(i as u16)) {
            return Err(PyValueError::new_err(
                "set_region_state: initial region_id values must be non-null and ordered 0..num_regions",
            ));
        }
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
        // Geography 2.0: `adjacency` list column (legacy `adjacency_mask`).
        let mut adjacency_lists = read_region_id_lists(&rb, "adjacency", "adjacency_mask")?;
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

        // Optional M35a column. Geography 2.0: `rivers` list (legacy `river_mask`).
        let mut river_lists = read_region_id_lists(&rb, "rivers", "river_mask")?;

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
        // The militant ruler's faith that persecution_intensity was measured
        // against (255 = none); absent in older batches.
        let persecuting_faith_col = rb
            .column_by_name("persecuting_faith")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
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
        let farm_productivity_col = rb
            .column_by_name("farm_productivity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let merchant_margin_col = rb
            .column_by_name("merchant_margin")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let merchant_route_margin_col = rb
            .column_by_name("merchant_route_margin")
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
        let catastrophe_deaths_col = rb
            .column_by_name("catastrophe_deaths_this_turn")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt16Array>());

        // M55a: Spatial substrate columns
        let is_capital_col = rb
            .column_by_name("is_capital")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        let temple_prestige_col = rb
            .column_by_name("temple_prestige")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        // Geography 2.0: latitude climate exposure (absent on template worlds = 1.0)
        // Cities: per-region urban pull (absent when the switch is off = 0.0)
        let city_pull_col = rb
            .column_by_name("city_pull")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        // Seats of learning: per-region scholar pull and flight (absent when
        // the switch is off = no pull, no flight).
        let seat_pull_col = rb
            .column_by_name("seat_pull")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let seat_flight_col = rb
            .column_by_name("seat_flight")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        // Guilds: news of last turn's movement event per region (absent when
        // the switch is off = no news).
        let movement_news_col = rb
            .column_by_name("movement_news")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        let movement_news_intensity_col = rb
            .column_by_name("movement_news_intensity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt8Array>());
        // Domestic credit: merchants' grievance toward a defaulting lord
        // (absent when the switch is off = 0, no penalty).
        let creditor_grievance_col = rb
            .column_by_name("creditor_grievance")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        if let Some(arr) = creditor_grievance_col {
            for i in 0..arrow::array::Array::len(arr) {
                let v = arr.value(i);
                if !v.is_finite() || !(0.0..=1.0).contains(&v) {
                    return Err(PyValueError::new_err(format!(
                        "creditor_grievance row {i} must be in [0, 1], got {v}"
                    )));
                }
            }
        }
        // Merchant routing: the economy's demand and post-trade supply per
        // goods category (absent = 0: no non-food market, no food tally).
        const NC: usize = crate::economy::NUM_CATEGORIES;
        let market_cols = |prefix: &str| -> [Option<&arrow::array::Float32Array>; NC] {
            crate::ffi::schema::CATEGORY_NAMES.map(|cat| {
                rb.column_by_name(&format!("{prefix}_{cat}"))
                    .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>())
            })
        };
        let market_demand_cols = market_cols("market_demand");
        let market_supply_cols = market_cols("market_supply");
        let market_row = |cols: &[Option<&arrow::array::Float32Array>; NC], i: usize| -> [f32; NC] {
            std::array::from_fn(|c| cols[c].map_or(0.0, |arr| arr.value(i)))
        };
        // Crafts: wares on hand over demand at the last economy tick (absent = 0).
        let craft_sufficiency_col = rb
            .column_by_name("craft_sufficiency")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        // Hunger: the severe-shortage run up to the previous turn (absent = 0)
        let food_severe_turns_col = rb
            .column_by_name("food_severe_turns")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt16Array>());
        // Needs calibration: a raid this turn (absent = false)
        let raided_col = rb
            .column_by_name("raided_this_turn")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::BooleanArray>());
        // Needs calibration: the controller's harsh rule (absent = 0)
        let harsh_rule_col = rb
            .column_by_name("harsh_rule")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let climate_exposure_col = rb
            .column_by_name("climate_exposure")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
        let harvest_shock_col = rb
            .column_by_name("harvest_shock")
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

        // M58a: Per-good stockpile columns (optional, backward compatible)
        let stockpile_cols: Vec<Option<&arrow::array::Float32Array>> = (0..crate::economy::NUM_GOODS)
            .map(|g| {
                rb.column_by_name(&format!("stockpile_{g}"))
                    .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>())
            })
            .collect();

        // All fallible input validation above completes before persistent mutation.
        self.snapshot_cache = None; // a valid update may change the pool
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
                    adjacency: adjacency_lists
                        .as_mut()
                        .map_or_else(Vec::new, |lists| std::mem::take(&mut lists[i])),
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
                    realized_extraction: None,
                    season: season_col.map_or(0, |arr| arr.value(i)),
                    season_id: season_id_col.map_or(0, |arr| arr.value(i)),
                    rivers: river_lists
                        .as_mut()
                        .map_or_else(Vec::new, |lists| std::mem::take(&mut lists[i])),
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
                    persecuting_faith: persecuting_faith_col.map_or(0xFF, |arr| arr.value(i)),
                    schism_convert_from: schism_convert_from_col.map_or(0xFF, |arr| arr.value(i)),
                    schism_convert_to: schism_convert_to_col.map_or(0xFF, |arr| arr.value(i)),
                    farmer_income_modifier: farmer_income_modifier_col.map_or(1.0, |arr| arr.value(i)),
                    food_sufficiency: food_sufficiency_col.map_or(1.0, |arr| arr.value(i)),
                    farm_productivity: farm_productivity_col.map_or(1.0, |arr| arr.value(i)),
                    merchant_margin: merchant_margin_col.map_or(0.0, |arr| arr.value(i)),
                    merchant_route_margin: merchant_route_margin_col.map_or(
                        merchant_margin_col.map_or(0.0, |arr| arr.value(i)),
                        |arr| arr.value(i),
                    ),
                    merchant_trade_income: merchant_trade_income_col.map_or(0.0, |arr| arr.value(i)),
                    controller_changed_this_turn: controller_changed_col.map_or(false, |arr| arr.value(i)),
                    war_won_this_turn: war_won_col.map_or(false, |arr| arr.value(i)),
                    seceded_this_turn: seceded_col.map_or(false, |arr| arr.value(i)),
                    catastrophe_deaths_this_turn: catastrophe_deaths_col.map_or(0, |arr| arr.value(i)),
                    // M55a
                    is_capital: is_capital_col.map_or(false, |arr| arr.value(i)),
                    temple_prestige: temple_prestige_col.map_or(0.0, |arr| arr.value(i)),
                    climate_exposure: climate_exposure_col.map_or(1.0, |arr| arr.value(i)),
                    harvest_shock: harvest_shock_col.map_or(0.0, |arr| arr.value(i)),
                    city_pull: city_pull_col.map_or(0.0, |arr| arr.value(i)),
                    seat_pull: seat_pull_col.map_or(0.0, |arr| arr.value(i)),
                    seat_flight: seat_flight_col.map_or(false, |arr| arr.value(i)),
                    movement_news: movement_news_col.map_or(crate::knowledge::NO_NEWS, |arr| arr.value(i)),
                    movement_news_intensity: movement_news_intensity_col.map_or(0, |arr| arr.value(i)),
                    market_demand: market_row(&market_demand_cols, i),
                    market_supply: market_row(&market_supply_cols, i),
                    craft_sufficiency: craft_sufficiency_col.map_or(0.0, |arr| arr.value(i)),
                    food_severe_turns: food_severe_turns_col.map_or(0, |arr| arr.value(i)),
                    harsh_rule: harsh_rule_col.map_or(0.0, |arr| arr.value(i)),
                    raided_this_turn: raided_col.map_or(false, |arr| arr.value(i)),
                    creditor_grievance: creditor_grievance_col.map_or(0.0, |arr| arr.value(i)),
                    // M58a: Per-good stockpile
                    stockpile: {
                        let mut s = [0.0f32; crate::economy::NUM_GOODS];
                        for (g, col) in stockpile_cols.iter().enumerate() {
                            if let Some(arr) = col {
                                s[g] = arr.value(i);
                            }
                        }
                        s
                    },
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

                // Shares from a conserved budget: exactly `pop` agents
                // (correction 2026-10, see `initial_occupation_counts`).
                let [n_farmer, n_soldier, n_merchant, n_scholar, n_priest] =
                    crate::demographics::initial_occupation_counts(pop);

                // M33: personality assignment at initial spawn
                // V9: use packed stream scheme (region << 48 | turn << 16 | offset)
                // Initial spawn happens at turn 0, so turn component is 0.
                let mut personality_rng = ChaCha8Rng::from_seed(self.master_seed);
                personality_rng.set_stream(
                    ((region_id as u64) << 48) | crate::agent::PERSONALITY_STREAM_OFFSET,
                );
                let civ_mean = [0.0f32; 3]; // Civ means not yet available at initial spawn

                // M53: mixed age distribution at initial spawn (was all age=0)
                // V9: use packed stream scheme (turn=0 at initial spawn)
                let mut age_rng = ChaCha8Rng::from_seed(self.master_seed);
                age_rng.set_stream(
                    ((region_id as u64) << 48) | crate::agent::INITIAL_AGE_STREAM_OFFSET,
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
                    self.pool.try_spawn(region_id, civ, Occupation::Farmer, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief)
                        .map_err(PyRuntimeError::new_err)?;
                }
                for _ in 0..n_soldier {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.try_spawn(region_id, civ, Occupation::Soldier, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief)
                        .map_err(PyRuntimeError::new_err)?;
                }
                for _ in 0..n_merchant {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.try_spawn(region_id, civ, Occupation::Merchant, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief)
                        .map_err(PyRuntimeError::new_err)?;
                }
                for _ in 0..n_scholar {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.try_spawn(region_id, civ, Occupation::Scholar, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief)
                        .map_err(PyRuntimeError::new_err)?;
                }
                for _ in 0..n_priest {
                    let p = crate::demographics::assign_personality(&mut personality_rng, civ_mean);
                    let age = assign_age(&mut age_rng);
                    self.pool.try_spawn(region_id, civ, Occupation::Priest, age, p[0], p[1], p[2], crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, crate::agent::CULTURAL_VALUE_EMPTY, belief)
                        .map_err(PyRuntimeError::new_err)?;
                }
            }

            self.initialized = true;
        } else {
            // Subsequent calls: update all fields.
            for i in 0..n {
                let r = &mut self.regions[i];
                r.terrain = terrains.value(i);
                r.carrying_capacity = capacities.value(i);
                r.population = populations.value(i);
                r.soil = soils.value(i);
                r.water = waters.value(i);
                r.forest_cover = forest_covers.value(i);
                r.controller_civ = controller_civs.map_or(r.controller_civ, |arr| arr.value(i));
                if let Some(lists) = adjacency_lists.as_mut() {
                    r.adjacency = std::mem::take(&mut lists[i]);
                }
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
                if let Some(lists) = river_lists.as_mut() {
                    r.rivers = std::mem::take(&mut lists[i]);
                }
                r.endemic_severity = endemic_severity_col.map_or(r.endemic_severity, |arr| arr.value(i));
                r.culture_investment_active = culture_investment.map_or(r.culture_investment_active, |arr| arr.value(i));
                r.controller_values = [
                    ctrl_val_0.map_or(0xFF, |arr| arr.value(i)),
                    ctrl_val_1.map_or(0xFF, |arr| arr.value(i)),
                    ctrl_val_2.map_or(0xFF, |arr| arr.value(i)),
                ];
                r.conversion_rate = conversion_rate_col.map_or(r.conversion_rate, |arr| arr.value(i));
                r.conversion_target_belief = conversion_target_belief_col.map_or(r.conversion_target_belief, |arr| arr.value(i));
                r.conquest_conversion_active = conquest_conversion_active_col.map_or(r.conquest_conversion_active, |arr| arr.value(i));
                r.majority_belief = majority_belief_col.map_or(r.majority_belief, |arr| arr.value(i));
                r.has_temple = has_temple_col.map_or(r.has_temple, |arr| arr.value(i));
                r.persecution_intensity = persecution_intensity_col.map_or(r.persecution_intensity, |arr| arr.value(i));
                // Paired with the intensity: both keep their value only when
                // the batch carries neither column.
                r.persecuting_faith = match (persecuting_faith_col, persecution_intensity_col) {
                    (Some(arr), _) => arr.value(i),
                    (None, Some(_)) => 0xFF,
                    (None, None) => r.persecuting_faith,
                };
                r.schism_convert_from = schism_convert_from_col.map_or(0xFF, |arr| arr.value(i));
                r.schism_convert_to = schism_convert_to_col.map_or(0xFF, |arr| arr.value(i));
                if let Some(arr) = farmer_income_modifier_col { r.farmer_income_modifier = arr.value(i); }
                if let Some(arr) = food_sufficiency_col { r.food_sufficiency = arr.value(i); }
                r.farm_productivity = farm_productivity_col.map_or(1.0, |arr| arr.value(i));
                if let Some(arr) = merchant_margin_col { r.merchant_margin = arr.value(i); }
                r.merchant_route_margin = merchant_route_margin_col.map_or(r.merchant_margin, |arr| arr.value(i));
                if let Some(arr) = merchant_trade_income_col { r.merchant_trade_income = arr.value(i); }
                r.controller_changed_this_turn = controller_changed_col.map_or(false, |arr| arr.value(i));
                r.war_won_this_turn = war_won_col.map_or(false, |arr| arr.value(i));
                r.seceded_this_turn = seceded_col.map_or(false, |arr| arr.value(i));
                r.catastrophe_deaths_this_turn = catastrophe_deaths_col.map_or(0, |arr| arr.value(i));
                r.is_capital = is_capital_col.map_or(false, |arr| arr.value(i));
                r.temple_prestige = temple_prestige_col.map_or(0.0, |arr| arr.value(i));
                r.climate_exposure = climate_exposure_col.map_or(1.0, |arr| arr.value(i));
                r.harvest_shock = harvest_shock_col.map_or(0.0, |arr| arr.value(i));
                r.city_pull = city_pull_col.map_or(0.0, |arr| arr.value(i));
                r.seat_pull = seat_pull_col.map_or(0.0, |arr| arr.value(i));
                r.seat_flight = seat_flight_col.map_or(false, |arr| arr.value(i));
                r.movement_news = movement_news_col.map_or(crate::knowledge::NO_NEWS, |arr| arr.value(i));
                r.movement_news_intensity = movement_news_intensity_col.map_or(0, |arr| arr.value(i));
                r.market_demand = market_row(&market_demand_cols, i);
                r.market_supply = market_row(&market_supply_cols, i);
                r.craft_sufficiency = craft_sufficiency_col.map_or(0.0, |arr| arr.value(i));
                r.food_severe_turns = food_severe_turns_col.map_or(0, |arr| arr.value(i));
                r.harsh_rule = harsh_rule_col.map_or(0.0, |arr| arr.value(i));
                r.raided_this_turn = raided_col.map_or(false, |arr| arr.value(i));
                r.creditor_grievance = creditor_grievance_col.map_or(0.0, |arr| arr.value(i));
                // M58a: Per-good stockpile
                for (g, col) in stockpile_cols.iter().enumerate() {
                    if let Some(arr) = col {
                        r.stockpile[g] = arr.value(i);
                    } else {
                        r.stockpile[g] = 0.0;
                    }
                }
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
        // M55a: Spatial attractor init (once) + weight update (every call)
        if !self.spatial_initialized && self.initialized {
            let world_seed = u64::from_le_bytes(
                self.master_seed[0..8].try_into()
                    .map_err(|e| PyValueError::new_err(format!("Invalid master_seed slice: {e}")))?
            );
            self.attractors = (0..self.regions.len())
                .map(|i| crate::spatial::init_attractors(world_seed, i as u16, &self.regions[i]))
                .collect();
            // Initialize attractor weights before initial placement so spawn positions
            // respect occupation affinities on turn 0.
            for (i, region) in self.regions.iter().enumerate() {
                if i < self.attractors.len() {
                    crate::spatial::update_attractor_weights(&mut self.attractors[i], region);
                }
            }
            // Initialize agent positions near occupation-appropriate attractors
            for slot in 0..self.pool.capacity() {
                if self.pool.is_alive(slot) {
                    let r = self.pool.regions[slot] as usize;
                    if r < self.attractors.len() {
                        let (x, y) = crate::spatial::migration_reset_position(
                            self.pool.ids[slot],
                            self.pool.occupations[slot],
                            &self.attractors[r],
                            &self.master_seed,
                            r as u16,
                            0, // turn 0 for initial placement
                        );
                        self.pool.x[slot] = x;
                        self.pool.y[slot] = y;
                    }
                }
            }
            self.spatial_initialized = true;
        }
        // Always update attractor weights from current region state
        for (i, region) in self.regions.iter().enumerate() {
            if i < self.attractors.len() {
                crate::spatial::update_attractor_weights(&mut self.attractors[i], region);
            }
        }
        Ok(())
    }

    /// Advance simulation by one turn. Returns an events RecordBatch.
    pub fn tick(&mut self, py: Python<'_>, turn: u32, civ_signals: PyRecordBatch) -> PyResult<PyRecordBatch> {
        // A failed tick must never expose a previous turn's observation.
        self.decision_delivery_frame = None;
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        if !self.initialized {
            return Err(PyValueError::new_err(
                "tick() called before set_region_state()",
            ));
        }
        self.turn = turn;

        self.flush_pending_promotion_memories();

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

        let mut spatial_diag = crate::spatial::SpatialDiagnostics::default();

        // M58a: Build merchant_state from graph + ledger + delivery buffer if all present
        // Use take/put pattern to satisfy borrow checker (need &RouteGraph + &mut ShadowLedger + &mut DeliveryBuffer)
        if let Some(graph) = &mut self.merchant_graph {
            graph.receipt_limit = self.transaction_receipts_limit.unwrap_or(0);
        }
        let merchant_graph_taken = self.merchant_graph.take();
        let mut merchant_ledger_taken = self.merchant_ledger.take();
        let mut merchant_delivery_buf_taken = self.merchant_delivery_buf.take();
        let merchant_state = match (&merchant_graph_taken, &mut merchant_ledger_taken, &mut merchant_delivery_buf_taken) {
            (Some(graph), Some(ledger), Some(buf)) => Some((graph, ledger, buf)),
            _ => None,
        };

        let targeted_deaths = std::mem::take(&mut self.pending_targeted_deaths);
        let tick_options = self.tick_options;
        let delivery_config = self.decision_delivery_config.as_ref();
        let mut delivery_frame = delivery_config.map(|_| {
            crate::decision_delivery::DeliveryFrame::new(turn, tick_options.ablation.active(turn))
        });
        let (events, kin_failures, formation_stats, demo_debug, household_stats, merchant_stats, knowledge_stats) =
            py.detach(|| {
                if let (Some(config), Some(frame)) = (delivery_config, delivery_frame.as_mut()) {
                    crate::tick::try_tick_agents_with_delivery(
                        &mut self.pool, &self.regions, &signals, self.master_seed, turn,
                        &mut self.wealth_percentiles, &mut self.spatial_grids, &self.attractors,
                        &mut spatial_diag, &self.settlement_grids, merchant_state,
                        &targeted_deaths, tick_options, &mut self.movements, config, frame,
                    )
                } else {
                    crate::tick::try_tick_agents_with_movements(
                        &mut self.pool,
                        &self.regions,
                        &signals,
                        self.master_seed,
                        turn,
                        &mut self.wealth_percentiles,
                        &mut self.spatial_grids,
                        &self.attractors,
                        &mut spatial_diag,
                        &self.settlement_grids,  // M56b
                        merchant_state,
                        &targeted_deaths,
                        tick_options,
                        &mut self.movements,
                    )
                }
            }).map_err(PyRuntimeError::new_err)?;

        // Restore graph, ledger, and delivery buffer
        self.merchant_graph = merchant_graph_taken;
        self.merchant_ledger = merchant_ledger_taken;
        self.merchant_delivery_buf = merchant_delivery_buf_taken;

        self.last_spatial_diag = spatial_diag;
        self.prev_kin_bond_failures = self.kin_bond_failures;
        self.kin_bond_failures = self.kin_bond_failures.saturating_add(kin_failures);
        self.formation_stats = formation_stats;
        self.demographic_debug = demo_debug;
        self.household_stats = household_stats;
        self.merchant_trip_stats = merchant_stats;
        if let Some(limit) = self.transaction_receipts_limit {
            // A successful tick without merchant state did not observe mobility.
            self.merchant_trip_stats.receipts.get_or_insert_with(|| {
                let mut frame = crate::transaction_receipts::ReceiptFrame::new(turn, limit);
                frame.mobility_executed = false;
                frame
            });
        }
        self.knowledge_stats = knowledge_stats;

        // M53: demographic debug counters
        // event_type 0 = death, 5 = birth (from tick.rs AgentEvent)
        self.last_tick_deaths = events.iter().filter(|e| e.event_type == 0).count() as u32;
        self.last_tick_births = events.iter().filter(|e| e.event_type == 5).count() as u32;
        self.last_tick_alive = self.pool.alive.iter().filter(|&&a| a).count() as u32;

        let batch = events_to_batch(&events).map_err(arrow_err)?;
        // Publish only after successful native execution and event packing.
        self.decision_delivery_frame = delivery_frame;
        Ok(PyRecordBatch::new(batch))
    }

    /// Return an Arrow RecordBatch snapshot of all alive agents.
    ///
    /// Repeated calls without a pool-changing call in between return the
    /// same batch (see `snapshot_cache`) instead of exporting the pool again.
    pub fn get_snapshot(&mut self) -> PyResult<PyRecordBatch> {
        if let Some(batch) = &self.snapshot_cache {
            return Ok(PyRecordBatch::new(batch.clone()));
        }
        let batch = self.pool.to_record_batch().map_err(arrow_err)?;
        self.snapshot_cache = Some(batch.clone());
        Ok(PyRecordBatch::new(batch))
    }

    /// Whether the next `get_snapshot()` reuses a held batch (diagnostics/tests).
    pub fn snapshot_is_cached(&self) -> bool {
        self.snapshot_cache.is_some()
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
        let mut candidates = Vec::new();
        // Living named characters, counted once and raised as candidates are
        // accepted: the caps hold within this batch too.
        let mut living = self.registry.living_named(&self.pool);
        let mut leader_ids: std::collections::HashSet<u32> = std::collections::HashSet::new();
        if !self.pending_movement_leaders.is_empty() {
            // Movement leaders first (trigger TRIGGER_MOVEMENT_LEADER): alive,
            // not yet named, their civ under the living caps.
            let leaders = std::mem::take(&mut self.pending_movement_leaders);
            let mut taken: std::collections::HashSet<u32> =
                self.registry.characters.iter().map(|c| c.agent_id).collect();
            for (id, role) in leaders {
                let (Some(slot), Some(role)) = (
                    self.pool.find_slot_by_id(id),
                    crate::named_characters::CharacterRole::from_leader_u8(role),
                ) else {
                    continue;
                };
                let civ = self.pool.civ_affinity(slot);
                if !self.pool.is_alive(slot) || !living.admits_leader(civ) || !taken.insert(id) {
                    continue;
                }
                living.add(civ);
                leader_ids.insert(id);
                candidates.push((slot, role, crate::named_characters::TRIGGER_MOVEMENT_LEADER));
            }
        }
        candidates.extend(self.registry.find_candidates_with(&self.pool, self.turn, &mut living, &leader_ids));
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
        let mut parent_id_0_col = UInt32Builder::with_capacity(n);
        let mut parent_id_1_col = UInt32Builder::with_capacity(n);
        let mut civ_id_col = UInt8Builder::with_capacity(n);

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
            parent_id_0_col.append_value(self.pool.parent_id_0[slot]);
            parent_id_1_col.append_value(self.pool.parent_id_1[slot]);
            civ_id_col.append_value(self.pool.civ_affinity(slot));

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
                self.pool.parent_id_0[slot],
                self.pool.parent_id_1[slot],
            );
            // M48: queue the Promotion memory for the next tick (see field doc).
            self.pending_promotion_memories.push((
                self.turn as u16,
                crate::memory::MemoryIntent {
                    agent_slot: slot,
                    expected_agent_id: agent_id,
                    event_type: crate::memory::MemoryEventType::Promotion as u8,
                    source_civ: self.pool.civ_affinity(slot),
                    intensity: crate::agent::PROMOTION_DEFAULT_INTENSITY,
                    is_legacy: false,
                    decay_factor_override: None,
                },
            ));
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
                Arc::new(parent_id_0_col.finish()) as _,
                Arc::new(parent_id_1_col.finish()) as _,
                Arc::new(civ_id_col.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    pub fn set_agent_civ(&mut self, agent_id: u32, new_civ_id: u8) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
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
    /// Projects from the per-agent SoA relationship store (M50a).
    /// Schema: [agent_a: u32, agent_b: u32, relationship: u8, formed_turn: u16].
    /// Only named-character bonds with bond_type 0-4 (M40-compatible).
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

    /// Read memories, needs and relationships for each requested agent id.
    ///
    /// Rows keep input order and duplicates. A missing/dead id returns
    /// `(id, [], None, None)`; a live id with empty stores has `[]` memories
    /// and `Some([])` relationships. As in the scalar methods, first live
    /// duplicate pool ids win, and id zero can supply memories/needs but
    /// never relationships. The sorted query vector is local to this call:
    /// no id-sized table, randomized map, Arrow object or lasting cache.
    /// Existing scalar getters and production Python callers are unchanged.
    pub fn get_agent_context_batch(&self, agent_ids: Vec<u32>) -> Vec<AgentContextRow> {
        if agent_ids.is_empty() {
            return Vec::new();
        }
        let mut requested = agent_ids.clone();
        requested.sort_unstable();
        requested.dedup();
        let mut slots = vec![None; requested.len()];
        let mut remaining = requested.len();
        let pool = &self.pool;
        for slot in 0..pool.capacity() {
            if !pool.alive[slot] {
                continue;
            }
            if let Ok(index) = requested.binary_search(&pool.ids[slot]) {
                if slots[index].is_none() {
                    slots[index] = Some(slot);
                    remaining -= 1;
                    if remaining == 0 {
                        break;
                    }
                }
            }
        }
        agent_ids.into_iter().map(|agent_id| {
            let index = requested.binary_search(&agent_id).expect("requested id retained");
            let Some(slot) = slots[index] else {
                return (agent_id, Vec::new(), None, None);
            };
            let memories = (0..pool.memory_count[slot] as usize).map(|i| (
                pool.memory_event_types[slot][i],
                pool.memory_source_civs[slot][i],
                pool.memory_turns[slot][i],
                pool.memory_intensities[slot][i],
                pool.memory_decay_factors[slot][i],
                (pool.memory_is_legacy[slot] >> i) & 1 == 1,
            )).collect();
            let needs = Some((
                pool.need_safety[slot],
                pool.need_material[slot],
                pool.need_social[slot],
                pool.need_spiritual[slot],
                pool.need_autonomy[slot],
                pool.need_purpose[slot],
            ));
            let relationships = (agent_id != 0).then(|| {
                (0..pool.rel_count[slot] as usize)
                    .map(|i| crate::relationships::read_rel(pool, slot, i))
                    .collect()
            });
            (agent_id, memories, needs, relationships)
        }).collect()
    }

    /// M50a: Apply batched relationship operations from an Arrow RecordBatch.
    /// Columns: op_type(u8), agent_a(u32), agent_b(u32), bond_type(u8), sentiment(i8), formed_turn(u16)
    /// op_type: 0=UpsertDirected, 1=UpsertSymmetric, 2=RemoveDirected, 3=RemoveSymmetric
    pub fn apply_relationship_ops(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();
        let id_to_slot = self.pool.build_id_to_slot();

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
                    let slot_a = match id_to_slot.get(&id_a).copied() {
                        Some(s) => s,
                        None => continue,
                    };
                    if !id_to_slot.contains_key(&id_b) {
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
                    let slot_a = match id_to_slot.get(&id_a).copied() {
                        Some(s) => s,
                        None => continue,
                    };
                    let slot_b = match id_to_slot.get(&id_b).copied() {
                        Some(s) => s,
                        None => continue,
                    };
                    crate::relationships::upsert_symmetric(
                        &mut self.pool, slot_a, slot_b, bt_raw, sentiment, formed_turn,
                    );
                }
                2 => {
                    // RemoveDirected: source must be alive, target may be dead
                    let slot_a = match id_to_slot.get(&id_a).copied() {
                        Some(s) => s,
                        None => continue,
                    };
                    crate::relationships::remove_directed(&mut self.pool, slot_a, id_b, bt_raw);
                }
                3 => {
                    // RemoveSymmetric: remove whatever side still exists
                    if let Some(slot_a) = id_to_slot.get(&id_a).copied() {
                        if self.pool.alive[slot_a] {
                            crate::relationships::remove_directed(&mut self.pool, slot_a, id_b, bt_raw);
                        }
                    }
                    if let Some(slot_b) = id_to_slot.get(&id_b).copied() {
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
        m.insert("expected_hunger_deaths".into(), d.expected_hunger_deaths as f64);
        m.insert("hunger_births_withheld".into(), d.hunger_births_withheld as f64);
        m.insert("sat_near_threshold".into(), d.sat_near_threshold as f64);
        m
    }

    /// M55a: Return spatial diagnostics from the last tick.
    #[pyo3(name = "get_spatial_diagnostics")]
    pub fn get_spatial_diagnostics(&self) -> std::collections::HashMap<String, Vec<f64>> {
        let mut m = std::collections::HashMap::new();
        m.insert(
            "hotspot_count_by_region".into(),
            self.last_spatial_diag.hotspot_count_by_region.iter().map(|&v| v as f64).collect(),
        );
        m.insert(
            "hash_max_cell_occupancy".into(),
            self.last_spatial_diag.hash_max_cell_occupancy.iter().map(|&v| v as f64).collect(),
        );
        m.insert(
            "sort_time_us".into(),
            vec![self.last_spatial_diag.sort_time_us as f64],
        );
        // Flatten attractor_occupancy: concatenate all regions' arrays
        // Format: for each region, MAX_ATTRACTORS f64 values
        let mut occ_flat: Vec<f64> = Vec::new();
        for arr in &self.last_spatial_diag.attractor_occupancy {
            for &v in arr {
                occ_flat.push(v as f64);
            }
        }
        m.insert("attractor_occupancy_flat".into(), occ_flat);
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

        // M57a: Marriage formation stats
        stats.insert("marriages_formed".into(), self.formation_stats.marriages_formed as f64);
        stats.insert("marriage_pairs_evaluated".into(), self.formation_stats.marriage_pairs_evaluated as f64);
        stats.insert("marriage_pairs_rejected_hostile".into(), self.formation_stats.marriage_pairs_rejected_hostile as f64);
        stats.insert("marriage_pairs_rejected_incest".into(), self.formation_stats.marriage_pairs_rejected_incest as f64);
        stats.insert("marriage_pairs_rejected_distance".into(), self.formation_stats.marriage_pairs_rejected_distance as f64);
        stats.insert("cross_civ_marriages".into(), self.formation_stats.cross_civ_marriages as f64);
        stats.insert("same_civ_marriages".into(), self.formation_stats.same_civ_marriages as f64);
        stats.insert("cross_faith_marriages".into(), self.formation_stats.cross_faith_marriages as f64);
        stats.insert("same_faith_marriages".into(), self.formation_stats.same_faith_marriages as f64);

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

    /// M57b: Return household stats from last tick as a flat HashMap.
    #[pyo3(name = "get_household_stats")]
    pub fn get_household_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("inheritance_transfers_spouse".into(), self.household_stats.inheritance_transfers_spouse as f64);
        stats.insert("inheritance_transfers_child".into(), self.household_stats.inheritance_transfers_child as f64);
        stats.insert("inheritance_wealth_lost".into(), self.household_stats.inheritance_wealth_lost as f64);
        stats.insert("household_migrations_follow".into(), self.household_stats.household_migrations_follow as f64);
        stats.insert("household_migrations_cancelled_rebellion".into(), self.household_stats.household_migrations_cancelled_rebellion as f64);
        stats.insert("household_migrations_cancelled_catastrophe".into(), self.household_stats.household_migrations_cancelled_catastrophe as f64);
        stats.insert("household_dependent_overrides".into(), self.household_stats.household_dependent_overrides as f64);
        stats.insert("births_married_parent".into(), self.household_stats.births_married_parent as f64);
        stats.insert("births_unmarried_parent".into(), self.household_stats.births_unmarried_parent as f64);
        Ok(stats)
    }

    /// Migration budget of the last tick: agents that weighed a move, the
    /// migrations decided before household consolidation, and for each
    /// utility term its summed share (`share_<term>`) and the decisions in
    /// which it was positive (`present_<term>`). Per voluntary driver
    /// (frontier, wage, chain): `gate_<driver>`, agents for whom some
    /// neighbour opens the gate, and `open_<driver>`, agents whose chosen
    /// target carries that pull beyond their roots. `decided_age_<band>` and
    /// `voluntary_age_<band>` count decisions by the decider's age band (all,
    /// and those led by a voluntary driver). `follow_<term>` counts
    /// household followers by the largest term of the decision they follow
    /// (their total is `household_migrations_follow` in
    /// `get_household_stats`). Diagnostic only; production Python does not
    /// read it.
    #[pyo3(name = "get_migration_driver_stats")]
    pub fn get_migration_driver_stats(&self) -> std::collections::HashMap<String, f64> {
        let d = &self.household_stats.migration_drivers;
        let mut m = std::collections::HashMap::new();
        m.insert("evaluated".into(), d.evaluated as f64);
        m.insert("decided".into(), d.decided as f64);
        m.insert("unexplained".into(), d.unexplained as f64);
        for (i, name) in crate::migration_drivers::MIGRATION_TERM_NAMES.iter().enumerate() {
            m.insert(format!("share_{name}"), d.share[i]);
            m.insert(format!("present_{name}"), d.present[i] as f64);
            m.insert(format!("follow_{name}"), d.followers[i] as f64);
        }
        for (i, name) in crate::migration_drivers::VOLUNTARY_DRIVER_NAMES.iter().enumerate() {
            m.insert(format!("open_{name}"), d.open[i] as f64);
            m.insert(format!("gate_{name}"), d.gate[i] as f64);
        }
        for (i, band) in ["under20", "20_34", "35_49", "50_64", "65plus"].iter().enumerate() {
            m.insert(format!("decided_age_{band}"), d.decided_by_age[i] as f64);
            m.insert(format!("voluntary_age_{band}"), d.voluntary_by_age[i] as f64);
        }
        for (i, count) in d.community_ties.iter().enumerate() {
            m.insert(format!("community_ties_{i}"), *count as f64);
        }
        m
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
        let mut civ_affinity_col = UInt8Builder::with_capacity(total_memories);
        let mut region_col = UInt16Builder::with_capacity(total_memories);
        let mut occupation_col = UInt8Builder::with_capacity(total_memories);

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            let mem_count = self.pool.memory_count[slot] as usize;
            let civ_affinity = self.pool.civ_affinities[slot];
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
            Field::new("civ_affinity", DataType::UInt8, false),
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

    /// Community anchoring: every living agent's community ties as the
    /// decision counts them now (`community::community_ties`), as
    /// [agent_id: u32, ties: u8, non_kin: u8, counted: u8]. Read-only; the
    /// validator recomputes the same ties from the sidecars, and tests check
    /// the two agree.
    pub fn get_community_ties(&self) -> PyResult<PyRecordBatch> {
        let ids = self.pool.build_id_slots();
        let alive: Vec<usize> = (0..self.pool.capacity()).filter(|&s| self.pool.alive[s]).collect();
        let mut id_col = UInt32Builder::with_capacity(alive.len());
        let mut ties_col = UInt8Builder::with_capacity(alive.len());
        let mut non_kin_col = UInt8Builder::with_capacity(alive.len());
        let mut counted_col = UInt8Builder::with_capacity(alive.len());
        for slot in alive {
            let ties = crate::community::community_ties(&self.pool, slot, self.pool.regions[slot] as usize, &ids);
            id_col.append_value(self.pool.ids[slot]);
            ties_col.append_value(ties.ties);
            non_kin_col.append_value(ties.non_kin);
            counted_col.append_value(ties.counted());
        }
        let schema = Arc::new(Schema::new(vec![
            Field::new("agent_id", DataType::UInt32, false),
            Field::new("ties", DataType::UInt8, false),
            Field::new("non_kin", DataType::UInt8, false),
            Field::new("counted", DataType::UInt8, false),
        ]));
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(id_col.finish()) as _,
                Arc::new(ties_col.finish()) as _,
                Arc::new(non_kin_col.finish()) as _,
                Arc::new(counted_col.finish()) as _,
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
        let mut civ_affinity_col = UInt8Builder::with_capacity(live);
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
            civ_affinity_col.append_value(self.pool.civ_affinities[slot]);
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
            Field::new("civ_affinity", DataType::UInt8,   false),
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
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
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
            // Kept: set by `set_climate_config`.
            climate_trend_share: self.ecology_config.climate_trend_share,
            harvest_shock_water_loss: self.ecology_config.harvest_shock_water_loss,
            // Kept: set by `set_extraction_config`.
            overextraction_realized: self.ecology_config.overextraction_realized,
            mine_soil_realized: self.ecology_config.mine_soil_realized,
            yield_penalty_reaches_goods: self.ecology_config.yield_penalty_reaches_goods,
        };
    }

    /// Regional climate (2026-10): the global phase's share of the crop and
    /// water effects and the water a unit of harvest shock takes per turn
    /// (Python `climate.climate_trend_share`, `harvest_shock_water_loss`).
    /// Never called: 1.0 and 0.0, the global schedule alone.
    pub fn set_climate_config(&mut self, trend_share: f32, harvest_shock_water_loss: f32) -> PyResult<()> {
        if !trend_share.is_finite() || !(0.0..=1.0).contains(&trend_share)
            || !harvest_shock_water_loss.is_finite() || harvest_shock_water_loss < 0.0
        {
            return Err(PyValueError::new_err("invalid climate config"));
        }
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        self.ecology_config.climate_trend_share = trend_share;
        self.ecology_config.harvest_shock_water_loss = harvest_shock_water_loss;
        Ok(())
    }

    /// Set the river topology for ecology cascade computation.
    pub fn set_river_topology(&mut self, rivers: Vec<Vec<u16>>) {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
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
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        if self.regions.is_empty() {
            return Err(PyValueError::new_err(
                "tick_ecology() called before set_region_state()",
            ));
        }

        // Minerals are depleted by what this turn's economy tick produced
        // (`realized_extraction`); a tick without one keeps the labour proxy.
        // The ledger (what the tick took) goes out with the region batch.
        let (yields, events, ledgers) = crate::ecology::tick_ecology_with_ledger(
            &mut self.regions,
            &self.ecology_config,
            turn,
            climate_phase,
            &pandemic_mask,
            &army_arrived_mask,
            &self.river_topology,
        );
        // Consumed: never applied to a later tick.
        for region in self.regions.iter_mut() {
            region.realized_extraction = None;
        }

        // Write current_turn_yields into regions so the agent tick sees them.
        for (i, ys) in yields.iter().enumerate() {
            self.regions[i].resource_yields = *ys;
        }

        // Store recompute context for apply_region_postpass_patch.
        self.recompute_ctx = RecomputeContext {
            climate_phase,
            season_id: crate::ecology::season_id_from_turn(turn),
            valid: true,
        };

        let (region_batch, event_batch) =
            build_ecology_batches(&self.regions, &yields, &events, &ledgers).map_err(arrow_err)?;

        Ok((PyRecordBatch::new(region_batch), PyRecordBatch::new(event_batch)))
    }

    /// Production ledger (2026-10): the extraction rules (see
    /// `ecology::EcologyConfig`). `true` everywhere is the default; `false`
    /// restores the earlier rule (overextraction streak on population / 5
    /// workers, the flat per-mine soil charge, yields without the
    /// overextraction penalty). Sent only when a tuning key overrides one.
    pub fn set_extraction_config(
        &mut self,
        overextraction_realized: bool,
        mine_soil_realized: bool,
        yield_penalty_reaches_goods: bool,
    ) {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        self.ecology_config.overextraction_realized = overextraction_realized;
        self.ecology_config.mine_soil_realized = mine_soil_realized;
        self.ecology_config.yield_penalty_reaches_goods = yield_penalty_reaches_goods;
    }

    /// Apply a narrow post-pass patch back to Rust region state.
    /// Recomputes resource_yields for regions whose ecology-affecting inputs changed.
    pub fn apply_region_postpass_patch(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
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

    // -----------------------------------------------------------------------
    // M54c: Politics FFI surface
    // -----------------------------------------------------------------------

    /// Optional default-off ecology experiment: patch actual fish catch only.
    pub fn apply_fishery_yield_patch(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        batch::apply_fishery_yield_patch(&mut self.regions, &batch.into_inner())
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
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
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

    /// Run the 11-step Phase 10 politics pass.
    ///
    /// Returns a 12-tuple of Arrow RecordBatches (one per op family).
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

    // -----------------------------------------------------------------------
    // M54b: Economy FFI surface
    // -----------------------------------------------------------------------

    /// Set economy configuration from individual field arguments.
    #[allow(clippy::too_many_arguments)]
    pub fn set_economy_config(
        &mut self,
        base_price: f32,
        per_capita_food: f32,
        raw_material_per_soldier: f32,
        luxury_per_wealthy_agent: f32,
        luxury_demand_threshold: f32,
        carry_per_merchant: f32,
        farmer_income_modifier_floor: f32,
        farmer_income_modifier_cap: f32,
        merchant_margin_normalizer: f32,
        tax_rate: f32,
        trade_dependency_threshold: f32,
        per_good_cap_factor: f32,
        salt_preservation_factor: f32,
        max_preservation: f32,
        tatonnement_max_passes: u32,
        tatonnement_damping: f32,
        tatonnement_convergence: f32,
        tatonnement_price_clamp_lo: f32,
        tatonnement_price_clamp_hi: f32,
    ) {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        self.economy_config = crate::economy::EconomyConfig {
            base_price,
            per_capita_food,
            raw_material_per_soldier,
            luxury_per_wealthy_agent,
            luxury_demand_threshold,
            carry_per_merchant,
            farmer_income_modifier_floor,
            farmer_income_modifier_cap,
            merchant_margin_normalizer,
            tax_rate,
            trade_dependency_threshold,
            per_good_cap_factor,
            salt_preservation_factor,
            max_preservation,
            tatonnement_max_passes,
            tatonnement_damping,
            tatonnement_convergence,
            tatonnement_price_clamp_lo,
            tatonnement_price_clamp_hi,
        };
    }

    /// M58b: Enable/disable hybrid economy mode.
    /// When enabled, `tick_economy` consumes the merchant delivery buffer
    /// instead of running abstract tatonnement trade allocation.
    pub fn set_hybrid_economy_mode(&mut self, enabled: bool) {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        self.hybrid_economy_mode = enabled;
        if let Some(buf) = self.merchant_delivery_buf.as_mut() {
            buf.physical_stock = enabled;
        }
    }

    /// Bulk trade: loads per merchant trip overland, by river and by sea,
    /// and whether trips are planned in bulk, filled against the tick's
    /// committed deliveries (docs/integration/bulk-trade-crafts.md).
    /// (1, 1, 1, false) is the one-load trade before it. Applies to the
    /// current and later graphs.
    pub fn set_merchant_cargo_config(&mut self, land: f32, river: f32, sea: f32, fill: bool) -> PyResult<()> {
        for (name, v) in [("land", land), ("river", river), ("sea", sea)] {
            if !v.is_finite() || v <= 0.0 {
                return Err(PyValueError::new_err(format!("invalid {name} cargo capacity")));
            }
        }
        self.merchant_cargo = crate::merchant::CargoConfig { land, river, sea, fill };
        if let Some(graph) = self.merchant_graph.as_mut() {
            graph.cargo = self.merchant_cargo;
        }
        Ok(())
    }

    /// Run the economy tick: returns five Arrow batches.
    ///
    /// Python calls this with dedicated economy input batches (NOT build_region_batch).
    /// Rust derives agent counts from the live pool.
    pub fn tick_economy(
        &mut self,
        region_input_batch: PyRecordBatch,
        trade_route_batch: PyRecordBatch,
        season_id: u8,
        is_winter: bool,
        trade_friction: f32,
    ) -> PyResult<(PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch)> {
        use arrow::array::{
            Float32Array, Float64Array, UInt8Array, UInt16Array, BooleanArray,
            Float32Builder, UInt8Builder, UInt16Builder, BooleanBuilder,
        };
        use crate::economy::{
            EconomyRegionInput, RegionAgentCounts, TradeRouteInput, tick_economy_core,
        };

        let _ = season_id; // reserved for future seasonal modifiers

        let ri_rb: RecordBatch = region_input_batch.into_inner();
        let tr_rb: RecordBatch = trade_route_batch.into_inner();
        let n_regions = ri_rb.num_rows();
        let n_routes = tr_rb.num_rows();

        // --- Unpack region inputs ---
        // Helper macros for column extraction
        macro_rules! col_u8 {
            ($rb:expr, $name:expr) => {
                $rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any().downcast_ref::<UInt8Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt8", $name)))?
            };
        }
        macro_rules! col_u16 {
            ($rb:expr, $name:expr) => {
                $rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any().downcast_ref::<UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt16", $name)))?
            };
        }
        macro_rules! col_f32 {
            ($rb:expr, $name:expr) => {
                $rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any().downcast_ref::<Float32Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not Float32", $name)))?
            };
        }
        macro_rules! col_bool {
            ($rb:expr, $name:expr) => {
                $rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column {}", $name)))?
                    .as_any().downcast_ref::<BooleanArray>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not Boolean", $name)))?
            };
        }

        let ri_region_ids = col_u16!(&ri_rb, "region_id");
        let ri_terrain = col_u8!(&ri_rb, "terrain");
        let ri_storage_pop = col_u16!(&ri_rb, "storage_population");
        let ri_rt0 = col_u8!(&ri_rb, "resource_type_0");
        let ri_rt1 = col_u8!(&ri_rb, "resource_type_1");
        let ri_rt2 = col_u8!(&ri_rb, "resource_type_2");
        let ri_y0 = col_f32!(&ri_rb, "resource_yield_0");
        let ri_y1 = col_f32!(&ri_rb, "resource_yield_1");
        let ri_y2 = col_f32!(&ri_rb, "resource_yield_2");

        // Fixed good slot columns (crafts optional: absent, no wares in stock).
        use crate::ffi::schema::GOOD_NAMES;
        let mut ri_stockpile_cols: Vec<Option<&Float32Array>> = Vec::with_capacity(GOOD_NAMES.len());
        for (g, good) in GOOD_NAMES.iter().enumerate() {
            let name = format!("stockpile_{good}");
            if g == crate::economy::SLOT_CRAFTS {
                ri_stockpile_cols.push(ri_rb.column_by_name(&name).and_then(|c| c.as_any().downcast_ref::<Float32Array>()));
            } else {
                ri_stockpile_cols.push(Some(col_f32!(&ri_rb, &name)));
            }
        }

        let mut region_inputs: Vec<EconomyRegionInput> = Vec::with_capacity(n_regions);
        for i in 0..n_regions {
            let mut stockpile = [0.0f32; crate::economy::NUM_GOODS];
            for (g, col) in ri_stockpile_cols.iter().enumerate() {
                if let Some(col) = col {
                    stockpile[g] = col.value(i);
                }
            }
            region_inputs.push(EconomyRegionInput {
                region_id: ri_region_ids.value(i),
                terrain: ri_terrain.value(i),
                storage_population: ri_storage_pop.value(i),
                resource_types: [ri_rt0.value(i), ri_rt1.value(i), ri_rt2.value(i)],
                resource_yields: [ri_y0.value(i), ri_y1.value(i), ri_y2.value(i)],
                production_caps: [None; 3],
                stockpile,
                subsistence_yield: 0.0,
                farm_labor_factor: 1.0,
                craft_raw_demand: 0.0,
                craft_demand: 0.0,
                farm_labor_ref: 0.0,
                farm_labor_half: 0.0,
                slot_curves: false,
                slot_labor_ref: [0.0; 3],
                slot_labor_half: [0.0; 3],
            });
        }

        // Optional: goods per farmer from foraging when no food slot yields
        // (M34 subsistence baseline; see economy::allocate_farm_labor). An
        // absent column means no foraging, the pre-2026-10 behavior.
        if let Some(column) = ri_rb.column_by_name("subsistence_yield") {
            let values = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err("subsistence_yield must be Float32"))?;
            for i in 0..n_regions {
                let v = values.value(i);
                if !v.is_finite() || v < 0.0 {
                    return Err(PyValueError::new_err("invalid subsistence_yield"));
                }
                region_inputs[i].subsistence_yield = v;
            }
        }

        // Optional (--cities): city farmers' labor share and city crafts'
        // raw-material demand (Python `cities.economy_columns`). Absent
        // columns leave every region at 1.0 and 0.0.
        if let Some(column) = ri_rb.column_by_name("farm_labor_factor") {
            let values = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err("farm_labor_factor must be Float32"))?;
            for i in 0..n_regions {
                let v = values.value(i);
                if !v.is_finite() || !(0.0..=1.0).contains(&v) {
                    return Err(PyValueError::new_err("invalid farm_labor_factor"));
                }
                region_inputs[i].farm_labor_factor = v;
            }
        }
        if let Some(column) = ri_rb.column_by_name("craft_raw_demand") {
            let values = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err("craft_raw_demand must be Float32"))?;
            for i in 0..n_regions {
                let v = values.value(i);
                if !v.is_finite() || v < 0.0 {
                    return Err(PyValueError::new_err("invalid craft_raw_demand"));
                }
                region_inputs[i].craft_raw_demand = v;
            }
        }
        // Optional (--cities, 2026-10 crafts): wares the people want.
        if let Some(column) = ri_rb.column_by_name("craft_demand") {
            let values = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err("craft_demand must be Float32"))?;
            for i in 0..n_regions {
                let v = values.value(i);
                if !v.is_finite() || v < 0.0 {
                    return Err(PyValueError::new_err("invalid craft_demand"));
                }
                region_inputs[i].craft_demand = v;
            }
        }

        // Optional: diminishing returns to farm labour (Python
        // `economy.farm_labor_curve`). Absent columns keep constant returns.
        for (name, half) in [("farm_labor_ref", false), ("farm_labor_half", true)] {
            let Some(column) = ri_rb.column_by_name(name) else { continue };
            let values = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err(format!("{name} must be Float32")))?;
            for i in 0..n_regions {
                let v = values.value(i);
                if !v.is_finite() || v < 0.0 {
                    return Err(PyValueError::new_err(format!("invalid {name}")));
                }
                if half {
                    region_inputs[i].farm_labor_half = v;
                } else {
                    region_inputs[i].farm_labor_ref = v;
                }
            }
        }

        // Optional: mines and forests have their own curves (Python
        // `economy.slot_labor_curves`): with all six columns the farm curve
        // applies to the food labour only and each non-food slot's labour has
        // its own. Absent columns keep the farm curve on all farm labour.
        let slot_cols: Vec<Option<&Float32Array>> = ["ref", "half"].iter()
            .flat_map(|kind| (0..3).map(move |slot| format!("slot_labor_{kind}_{slot}")))
            .map(|name| ri_rb.column_by_name(&name).and_then(|c| c.as_any().downcast_ref::<Float32Array>()))
            .collect();
        if slot_cols.iter().all(Option::is_some) {
            for i in 0..n_regions {
                region_inputs[i].slot_curves = true;
                for slot in 0..3 {
                    let r = slot_cols[slot].unwrap().value(i);
                    let h = slot_cols[3 + slot].unwrap().value(i);
                    if !r.is_finite() || r < 0.0 || !h.is_finite() || h < 0.0 {
                        return Err(PyValueError::new_err("invalid slot labor curve"));
                    }
                    region_inputs[i].slot_labor_ref[slot] = r;
                    region_inputs[i].slot_labor_half[slot] = h;
                }
            }
        } else if slot_cols.iter().any(Option::is_some) {
            return Err(PyValueError::new_err("slot labor curves need all six slot_labor_* Float32 columns"));
        }

        // Optional default-off experiment: a fish slot's goods production may
        // not exceed the previous ecology tick's catch. The kernel applies the
        // cap after splitting farmer labor across occupied slots, so permanent
        // effective yields and other slots are untouched.
        for slot in 0..3 {
            let name = format!("fishery_catch_budget_{slot}");
            let Some(column) = ri_rb.column_by_name(&name) else { continue };
            use arrow::array::Array;
            let budgets = column.as_any().downcast_ref::<Float32Array>()
                .ok_or_else(|| PyValueError::new_err(format!("{name} must be Float32")))?;
            for i in 0..n_regions {
                if budgets.is_null(i) { continue; }
                let budget = budgets.value(i);
                if !budget.is_finite() || budget < 0.0 || region_inputs[i].resource_types[slot] != 3 {
                    return Err(PyValueError::new_err("invalid fishery catch budget"));
                }
                region_inputs[i].production_caps[slot] = Some(budget);
            }
        }

        // --- Derive agent counts from live pool ---
        // Partition by region for efficient iteration
        let partitioned = self.pool.partition_by_region(n_regions as u16);
        let mut agent_counts: Vec<RegionAgentCounts> = Vec::with_capacity(n_regions);
        for rid in 0..n_regions {
            let slots = &partitioned[rid];
            let mut population = 0u32;
            let mut farmer_count = 0u32;
            let mut soldier_count = 0u32;
            let mut merchant_count = 0u32;
            let mut wealthy_count = 0u32;
            for &slot in slots {
                population += 1;
                match Occupation::from_u8(self.pool.occupation(slot)) {
                    Some(Occupation::Farmer) => farmer_count += 1,
                    Some(Occupation::Soldier) => soldier_count += 1,
                    Some(Occupation::Merchant) => {
                        // M58a: Transit merchants counted by origin region in second pass
                        if self.pool.trip_phase[slot] == crate::agent::TRIP_PHASE_TRANSIT {
                            // Don't count here — counted by origin region below
                        } else {
                            merchant_count += 1;
                        }
                    }
                    _ => {}
                }
                if self.pool.wealth[slot] > self.economy_config.luxury_demand_threshold {
                    wealthy_count += 1;
                }
            }
            agent_counts.push(RegionAgentCounts {
                population,
                farmer_count,
                soldier_count,
                merchant_count,
                wealthy_count,
            });
        }

        // M58a: Second pass — count transit merchants by their origin region (anchor counting)
        for slot in 0..self.pool.capacity() {
            if !self.pool.is_alive(slot) { continue; }
            if self.pool.trip_phase[slot] != crate::agent::TRIP_PHASE_TRANSIT { continue; }
            if self.pool.occupations[slot] != Occupation::Merchant as u8 { continue; }
            let origin = self.pool.trip_origin_region[slot] as usize;
            if origin < agent_counts.len() {
                agent_counts[origin].merchant_count += 1;
            }
        }

        // --- Derive per-civ merchant wealth and priest count ---
        // Match Python's "living civ" semantics: fiscal outputs are keyed to civs
        // that currently control at least one region, not every affinity present
        // in the live pool. This keeps zero-agent controller civs explicit at 0.0
        // and prevents Phase 10 from falling back to stale trade_income values.
        let mut active_civ_flags = [false; 256];
        let mut active_civ_ids: Vec<u8> = Vec::new();
        let mut max_active_civ: Option<u8> = None;
        for region in &self.regions {
            let civ = region.controller_civ;
            if civ == 255 || active_civ_flags[civ as usize] {
                continue;
            }
            active_civ_flags[civ as usize] = true;
            active_civ_ids.push(civ);
            max_active_civ = Some(max_active_civ.map_or(civ, |prev| prev.max(civ)));
        }
        active_civ_ids.sort_unstable();

        let n_civs = max_active_civ.map_or(0, |max_civ| max_civ as usize + 1);

        let mut civ_merchant_wealth = vec![0.0f32; n_civs];
        let mut civ_priest_count = vec![0u32; n_civs];
        for slot in 0..self.pool.capacity() {
            if !self.pool.is_alive(slot) { continue; }
            let ca = self.pool.civ_affinity(slot) as usize;
            if ca >= n_civs || !active_civ_flags[ca] { continue; }
            match Occupation::from_u8(self.pool.occupation(slot)) {
                Some(Occupation::Merchant) => {
                    civ_merchant_wealth[ca] += self.pool.wealth[slot];
                }
                Some(Occupation::Priest) => {
                    civ_priest_count[ca] += 1;
                }
                _ => {}
            }
        }

        // Rural impairment/care removes productive work, not people or demand.
        // City craft allocation is already reflected in farm_labor_factor;
        // only non-city workers can contribute these additive deductions.
        // CAREOBS_SOURCE_BEGIN: economy stage
        if let Some(observation) = &mut self.pool.health_care_observation {
            observation.economy_begin(region_inputs.len());
        }
        // CAREOBS_SOURCE_END: economy stage
        if let Some(work) = &self.health_work {
            for (r, inp) in region_inputs.iter_mut().enumerate() {
                let farmers = agent_counts[r].farmer_count as f32;
                // CAREOBS_SOURCE_BEGIN: actual economy operands
                if let Some(observation) = &mut self.pool.health_care_observation {
                    observation.economy_before(r, agent_counts[r].farmer_count,
                        inp.farm_labor_factor, work.losses.get(r).copied());
                }
                // CAREOBS_SOURCE_END: actual economy operands
                if farmers > 0.0 && work.losses[r] > 0.0 {
                    inp.farm_labor_factor = (farmers * inp.farm_labor_factor - work.losses[r]).max(0.0) / farmers;
                    // CAREOBS_SOURCE_BEGIN: actual adjusted factor
                    if let Some(observation) = &mut self.pool.health_care_observation {
                        observation.economy_adjusted(inp.farm_labor_factor);
                    }
                    // CAREOBS_SOURCE_END: actual adjusted factor
                }
            }
        }

        // --- Unpack trade routes ---
        let mut routes: Vec<TradeRouteInput> = Vec::with_capacity(n_routes);
        if n_routes > 0 {
            let tr_origin = col_u16!(&tr_rb, "origin_region_id");
            let tr_dest = col_u16!(&tr_rb, "dest_region_id");
            let tr_river = col_bool!(&tr_rb, "is_river");
            for i in 0..n_routes {
                routes.push(TradeRouteInput {
                    origin_region_id: tr_origin.value(i),
                    dest_region_id: tr_dest.value(i),
                    is_river: tr_river.value(i),
                });
            }
        }

        // --- M58b: Build hybrid delivery input if in hybrid economy mode ---
        // The route graph and persistent buffer may not exist before the first
        // merchant tick. Hybrid cold-start still means zero realized deliveries;
        // passing None would accidentally execute instantaneous abstract trade.
        let hybrid_delivery = if self.hybrid_economy_mode {
            let empty_buffer;
            let buf = match self.merchant_delivery_buf.as_ref() {
                Some(buf) => buf,
                None => {
                    empty_buffer = crate::merchant::DeliveryBuffer::new(n_regions);
                    &empty_buffer
                }
            };
            Some(crate::economy::HybridDeliveryInput::from_buffer(buf, n_regions))
        } else {
            None
        };

        // --- Build region→civ owner mapping for tithe food gate ---
        let region_civ_owner: Vec<u8> = (0..n_regions)
            .map(|i| self.regions[i].controller_civ)
            .collect();

        // --- Call the core ---
        let output = tick_economy_core(
            &region_inputs,
            &agent_counts,
            &routes,
            &civ_merchant_wealth,
            &civ_priest_count,
            n_civs,
            &region_civ_owner,
            &self.economy_config,
            trade_friction,
            is_winter,
            hybrid_delivery.as_ref(),
        );

        // M58b: Write transit decay diagnostics back to delivery buffer before clearing.
        if let Some(ref tdr) = output.transit_decay_by_region {
            if let Some(buf) = self.merchant_delivery_buf.as_mut() {
                for (region, decay_per_good) in tdr.iter().enumerate() {
                    if region < buf.diagnostics.total_transit_decay.len() {
                        for g in 0..decay_per_good.len() {
                            buf.diagnostics.total_transit_decay[region][g] += decay_per_good[g];
                        }
                    }
                }
            }
        }

        // NOTE: Delivery buffer clearing is deferred until after Arrow packing succeeds.
        // If packing fails, the buffer is preserved for retry (transactional guarantee).

        // --- Pack results into Arrow batches ---
        // 1. Region result batch
        let n_out = output.region_results.len();
        // CAREOBS_SOURCE_BEGIN: actual output count
        if let Some(observation) = &mut self.pool.health_care_observation {
            observation.economy_outputs_begin(n_out);
        }
        // CAREOBS_SOURCE_END: actual output count
        let mut rr_region_id = UInt16Builder::with_capacity(n_out);
        let mut rr_fim = Float32Builder::with_capacity(n_out);
        let mut rr_fs = Float32Builder::with_capacity(n_out);
        let mut rr_mm = Float32Builder::with_capacity(n_out);
        let mut rr_mti = Float32Builder::with_capacity(n_out);
        let mut rr_trc = UInt16Builder::with_capacity(n_out);
        let mut rr_stockpile: Vec<Float32Builder> =
            (0..crate::economy::NUM_GOODS).map(|_| Float32Builder::with_capacity(n_out)).collect();
        // market_demand_<category> for every category, then market_supply_*.
        const NC: usize = crate::economy::NUM_CATEGORIES;
        let mut rr_market: Vec<Float32Builder> = (0..2 * NC).map(|_| Float32Builder::with_capacity(n_out)).collect();
        let mut rr_fp = Float32Builder::with_capacity(n_out);
        let mut rr_craft_out = Float32Builder::with_capacity(n_out);
        let mut rr_craft_suff = Float32Builder::with_capacity(n_out);
        let mut rr_slot_out: Vec<Float32Builder> = (0..3).map(|_| Float32Builder::with_capacity(n_out)).collect();
        let mut rr_forage = Float32Builder::with_capacity(n_out);

        for rr in &output.region_results {
            if let Some(work) = &mut self.health_work {
                let r = rr.region_id as usize;
                if r < work.worked.len() { work.worked[r] = rr.slot_output.iter().any(|&x| x > 0.0) || rr.forage_output > 0.0; }
            }
            // CAREOBS_SOURCE_BEGIN: actual economy work result
            if let Some(observation) = &mut self.pool.health_care_observation {
                observation.economy_output(rr.region_id, rr.slot_output, rr.forage_output,
                    self.health_work.as_ref().and_then(|work| work.worked.get(rr.region_id as usize).copied()));
            }
            // CAREOBS_SOURCE_END: actual economy work result
            for (slot, builder) in rr_slot_out.iter_mut().enumerate() {
                builder.append_value(rr.slot_output[slot]);
            }
            rr_forage.append_value(rr.forage_output);
            for c in 0..NC {
                rr_market[c].append_value(rr.market_demand[c]);
                rr_market[NC + c].append_value(rr.market_supply[c]);
            }
            rr_fp.append_value(rr.farm_productivity);
            rr_craft_out.append_value(rr.craft_output);
            rr_craft_suff.append_value(rr.craft_sufficiency);
            rr_region_id.append_value(rr.region_id);
            rr_fim.append_value(rr.farmer_income_modifier);
            rr_fs.append_value(rr.food_sufficiency);
            rr_mm.append_value(rr.merchant_margin);
            rr_mti.append_value(rr.merchant_trade_income);
            rr_trc.append_value(rr.trade_route_count);
            for (g, builder) in rr_stockpile.iter_mut().enumerate() {
                builder.append_value(rr.stockpile[g]);
            }
        }

        let mut rr_columns: Vec<Arc<dyn arrow::array::Array>> = vec![
            Arc::new(rr_region_id.finish()),
        ];
        for builder in rr_stockpile.iter_mut() {
            rr_columns.push(Arc::new(builder.finish()));
        }
        rr_columns.extend([
            Arc::new(rr_fim.finish()) as Arc<dyn arrow::array::Array>,
            Arc::new(rr_fs.finish()),
            Arc::new(rr_mm.finish()),
            Arc::new(rr_mti.finish()),
            Arc::new(rr_trc.finish()),
        ]);
        for builder in rr_market.iter_mut() {
            rr_columns.push(Arc::new(builder.finish()));
        }
        rr_columns.push(Arc::new(rr_fp.finish()));
        rr_columns.push(Arc::new(rr_craft_out.finish()));
        rr_columns.push(Arc::new(rr_craft_suff.finish()));
        for builder in rr_slot_out.iter_mut() {
            rr_columns.push(Arc::new(builder.finish()));
        }
        rr_columns.push(Arc::new(rr_forage.finish()));

        let region_result_batch = RecordBatch::try_new(
            Arc::new(economy_region_result_schema()),
            rr_columns,
        ).map_err(arrow_err)?;

        // 2. Civ result batch
        let n_civ_out = active_civ_ids.len();
        let mut cr_cid = UInt8Builder::with_capacity(n_civ_out);
        let mut cr_tax = Float32Builder::with_capacity(n_civ_out);
        let mut cr_tb = Float32Builder::with_capacity(n_civ_out);
        let mut cr_pts = Float32Builder::with_capacity(n_civ_out);
        for &civ_id in &active_civ_ids {
            let cr = &output.civ_results[civ_id as usize];
            cr_cid.append_value(civ_id);
            cr_tax.append_value(cr.treasury_tax);
            cr_tb.append_value(cr.tithe_base);
            cr_pts.append_value(cr.priest_tithe_share);
        }
        let civ_result_batch = RecordBatch::try_new(
            Arc::new(economy_civ_result_schema()),
            vec![
                Arc::new(cr_cid.finish()),
                Arc::new(cr_tax.finish()),
                Arc::new(cr_tb.finish()),
                Arc::new(cr_pts.finish()),
            ],
        ).map_err(arrow_err)?;

        // 3. Observability batch
        let mut obs_rid = UInt16Builder::with_capacity(n_out);
        let mut obs_if = Float32Builder::with_capacity(n_out);
        let mut obs_irm = Float32Builder::with_capacity(n_out);
        let mut obs_il = Float32Builder::with_capacity(n_out);
        let mut obs_ic = Float32Builder::with_capacity(n_out);
        let mut obs_sf = Float32Builder::with_capacity(n_out);
        let mut obs_srm = Float32Builder::with_capacity(n_out);
        let mut obs_sl = Float32Builder::with_capacity(n_out);
        let mut obs_sc = Float32Builder::with_capacity(n_out);
        let mut obs_is = Float32Builder::with_capacity(n_out);
        let mut obs_td = BooleanBuilder::with_capacity(n_out);
        // M58b: Oracle shadow columns
        let mut oracle_if = Float32Builder::with_capacity(n_out);
        let mut oracle_irm = Float32Builder::with_capacity(n_out);
        let mut oracle_il = Float32Builder::with_capacity(n_out);
        let mut oracle_margin = Float32Builder::with_capacity(n_out);
        let mut oracle_food_suff = Float32Builder::with_capacity(n_out);
        for obs in &output.observability {
            obs_rid.append_value(obs.region_id);
            obs_if.append_value(obs.imports_food);
            obs_irm.append_value(obs.imports_raw_material);
            obs_il.append_value(obs.imports_luxury);
            obs_ic.append_value(obs.imports_craft);
            obs_sf.append_value(obs.stockpile_food);
            obs_srm.append_value(obs.stockpile_raw_material);
            obs_sl.append_value(obs.stockpile_luxury);
            obs_sc.append_value(obs.stockpile_craft);
            obs_is.append_value(obs.import_share);
            obs_td.append_value(obs.trade_dependent);
        }
        if let Some(ref oracle_vols) = output.oracle_trade_volume {
            for ri in 0..n_out {
                oracle_if.append_value(oracle_vols[ri][0]);  // CAT_FOOD
                oracle_irm.append_value(oracle_vols[ri][1]); // CAT_RAW_MATERIAL
                oracle_il.append_value(oracle_vols[ri][2]);  // CAT_LUXURY
            }
        } else {
            for _ in 0..n_out {
                oracle_if.append_value(0.0);
                oracle_irm.append_value(0.0);
                oracle_il.append_value(0.0);
            }
        }
        if let Some(ref om) = output.oracle_margins {
            for ri in 0..n_out {
                oracle_margin.append_value(om[ri]);
            }
        } else {
            for _ in 0..n_out {
                oracle_margin.append_value(0.0);
            }
        }
        if let Some(ref ofs) = output.oracle_food_sufficiency {
            for ri in 0..n_out {
                oracle_food_suff.append_value(ofs[ri]);
            }
        } else {
            for _ in 0..n_out {
                oracle_food_suff.append_value(0.0);
            }
        }
        let observability_batch = RecordBatch::try_new(
            Arc::new(economy_observability_schema()),
            vec![
                Arc::new(obs_rid.finish()),
                Arc::new(obs_if.finish()),
                Arc::new(obs_irm.finish()),
                Arc::new(obs_il.finish()),
                Arc::new(obs_ic.finish()),
                Arc::new(obs_sf.finish()),
                Arc::new(obs_srm.finish()),
                Arc::new(obs_sl.finish()),
                Arc::new(obs_sc.finish()),
                Arc::new(obs_is.finish()),
                Arc::new(obs_td.finish()),
                Arc::new(oracle_if.finish()),
                Arc::new(oracle_irm.finish()),
                Arc::new(oracle_il.finish()),
                Arc::new(oracle_margin.finish()),
                Arc::new(oracle_food_suff.finish()),
            ],
        ).map_err(arrow_err)?;

        // 4. Upstream sources batch
        let n_us = output.upstream_sources.len();
        let mut us_dest = UInt16Builder::with_capacity(n_us);
        let mut us_ord = UInt16Builder::with_capacity(n_us);
        let mut us_src = UInt16Builder::with_capacity(n_us);
        for us in &output.upstream_sources {
            us_dest.append_value(us.dest_region_id);
            us_ord.append_value(us.source_ordinal);
            us_src.append_value(us.source_region_id);
        }
        let upstream_sources_batch = RecordBatch::try_new(
            Arc::new(economy_upstream_sources_schema()),
            vec![
                Arc::new(us_dest.finish()),
                Arc::new(us_ord.finish()),
                Arc::new(us_src.finish()),
            ],
        ).map_err(arrow_err)?;

        // 5. Conservation batch
        let c = &output.conservation;
        // M58b: in_transit_delta is nullable — use Option encoding.
        let in_transit_delta_arr: Arc<dyn arrow::array::Array> = match c.in_transit_delta {
            Some(v) => Arc::new(Float64Array::from(vec![Some(v)])),
            None => Arc::new(Float64Array::from(vec![None::<f64>])),
        };
        let conservation_batch = RecordBatch::try_new(
            Arc::new(economy_conservation_schema()),
            vec![
                Arc::new(Float64Array::from(vec![c.production])),
                Arc::new(Float64Array::from(vec![c.transit_loss])),
                Arc::new(Float64Array::from(vec![c.consumption])),
                Arc::new(Float64Array::from(vec![c.storage_loss])),
                Arc::new(Float64Array::from(vec![c.cap_overflow])),
                Arc::new(Float64Array::from(vec![c.clamp_floor_loss])),
                in_transit_delta_arr,
            ],
        ).map_err(arrow_err)?;

        // M58b: Clear delivery buffer AFTER Arrow packing succeeds (transactional guarantee).
        // If any batch packing above failed via `?`, we exit early and the buffer is preserved.
        if let Some(buf) = self.merchant_delivery_buf.as_mut() {
            buf.clear();
        }

        // What each slot produced is what the Phase 9 ecology tick depletes
        // mineral reserves by (consumed and cleared there; see
        // `ecology::mineral_extraction`).
        for rr in &output.region_results {
            if let Some(region) = self.regions.get_mut(rr.region_id as usize) {
                if region.region_id == rr.region_id {
                    region.realized_extraction = Some(rr.slot_output);
                }
            }
        }

        Ok((
            PyRecordBatch::new(region_result_batch),
            PyRecordBatch::new(civ_result_batch),
            PyRecordBatch::new(observability_batch),
            PyRecordBatch::new(upstream_sources_batch),
            PyRecordBatch::new(conservation_batch),
        ))
    }

    /// M56b: Ingest settlement footprint batch and build per-region grids.
    pub fn set_settlement_footprints(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let rb: RecordBatch = batch.into_inner();
        if rb.num_rows() == 0 {
            self.settlement_grids = vec![[0u16; 100]; self.num_regions];
            return Ok(());
        }

        macro_rules! col_u16 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column: {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt16", $name)))?
            }};
        }
        macro_rules! col_u8 {
            ($name:expr) => {{
                rb.column_by_name($name)
                    .ok_or_else(|| PyValueError::new_err(format!("missing column: {}", $name)))?
                    .as_any()
                    .downcast_ref::<arrow::array::UInt8Array>()
                    .ok_or_else(|| PyValueError::new_err(format!("column {} not UInt8", $name)))?
            }};
        }

        let region_ids = col_u16!("region_id");
        let settlement_ids = col_u16!("settlement_id");
        let cell_xs = col_u8!("cell_x");
        let cell_ys = col_u8!("cell_y");

        self.settlement_grids = crate::tick::build_settlement_grids(
            self.num_regions,
            region_ids.values(),
            settlement_ids.values(),
            cell_xs.values(),
            cell_ys.values(),
        );
        Ok(())
    }

    /// M58a: Ingest merchant route graph from Python as an Arrow RecordBatch.
    /// Schema: from_region (uint16), to_region (uint16), is_river (bool), transport_cost (float32).
    #[pyo3(name = "set_merchant_route_graph")]
    pub fn set_merchant_route_graph(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        self.snapshot_cache = None; // pool may change: drop the cached snapshot
        let rb: RecordBatch = batch.into_inner();
        let n = rb.num_rows();
        if n == 0 {
            // Empty graph — clear merchant state
            self.merchant_graph = Some(crate::merchant::RouteGraph::from_edges(
                &[], &[], &[], &[], self.regions.len(),
            ).with_cargo(self.merchant_cargo));
            if self.merchant_ledger.is_none() {
                self.merchant_ledger = Some(crate::merchant::ShadowLedger::new(self.regions.len()));
                self.merchant_delivery_buf = Some(crate::merchant::DeliveryBuffer::new(self.regions.len()));
                self.merchant_delivery_buf.as_mut().unwrap().physical_stock = self.hybrid_economy_mode;
            }
            return Ok(());
        }

        let from_region = rb.column_by_name("from_region")
            .ok_or_else(|| PyValueError::new_err("missing column: from_region"))?
            .as_any()
            .downcast_ref::<arrow::array::UInt16Array>()
            .ok_or_else(|| PyValueError::new_err("column from_region not UInt16"))?;
        let to_region = rb.column_by_name("to_region")
            .ok_or_else(|| PyValueError::new_err("missing column: to_region"))?
            .as_any()
            .downcast_ref::<arrow::array::UInt16Array>()
            .ok_or_else(|| PyValueError::new_err("column to_region not UInt16"))?;
        let is_river = rb.column_by_name("is_river")
            .ok_or_else(|| PyValueError::new_err("missing column: is_river"))?
            .as_any()
            .downcast_ref::<arrow::array::BooleanArray>()
            .ok_or_else(|| PyValueError::new_err("column is_river not Boolean"))?;
        let transport_cost = rb.column_by_name("transport_cost")
            .ok_or_else(|| PyValueError::new_err("missing column: transport_cost"))?
            .as_any()
            .downcast_ref::<arrow::array::Float32Array>()
            .ok_or_else(|| PyValueError::new_err("column transport_cost not Float32"))?;

        // Extract bool values from BooleanArray (bit-packed)
        let mut is_river_vec = Vec::with_capacity(n);
        for i in 0..n {
            is_river_vec.push(is_river.value(i));
        }

        let num_regions = self.regions.len();
        let mut graph = crate::merchant::RouteGraph::from_edges(
            from_region.values(),
            to_region.values(),
            &is_river_vec,
            transport_cost.values(),
            num_regions,
        );
        // Maritime (optional): per-edge sea-lane raid risk, -1 on land edges.
        // Absent unless the maritime layer is on, leaving the graph unchanged.
        if let Some(col) = rb.column_by_name("sea_raid_risk") {
            let risk = col
                .as_any()
                .downcast_ref::<arrow::array::Float32Array>()
                .ok_or_else(|| PyValueError::new_err("column sea_raid_risk not Float32"))?;
            graph = graph.with_sea_lanes(from_region.values(), to_region.values(), risk.values());
        }
        self.merchant_graph = Some(graph.with_cargo(self.merchant_cargo));

        // Initialize ledger and delivery buffer on first call
        if self.merchant_ledger.is_none() {
            self.merchant_ledger = Some(crate::merchant::ShadowLedger::new(num_regions));
            self.merchant_delivery_buf = Some(crate::merchant::DeliveryBuffer::new(num_regions));
            self.merchant_delivery_buf.as_mut().unwrap().physical_stock = self.hybrid_economy_mode;
        }
        Ok(())
    }

    /// M58a: Return merchant trip stats from last tick as a flat HashMap.
    #[pyo3(name = "get_merchant_trip_stats")]
    pub fn get_merchant_trip_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("active_trips".into(), self.merchant_trip_stats.active_trips as f64);
        stats.insert("completed_trips".into(), self.merchant_trip_stats.completed_trips as f64);
        stats.insert("avg_trip_duration".into(), self.merchant_trip_stats.avg_trip_duration as f64);
        stats.insert("total_in_transit_qty".into(), self.merchant_trip_stats.total_in_transit_qty as f64);
        stats.insert("route_utilization".into(), self.merchant_trip_stats.route_utilization as f64);
        stats.insert("disruption_replans".into(), self.merchant_trip_stats.disruption_replans as f64);
        stats.insert("unwind_count".into(), self.merchant_trip_stats.unwind_count as f64);
        stats.insert("stalled_trip_count".into(), self.merchant_trip_stats.stalled_trip_count as f64);
        stats.insert("overcommit_count".into(), self.merchant_trip_stats.overcommit_count as f64);
        Ok(stats)
    }

    /// Enable bounded read-only observations; configuration and frames are transient.
    #[pyo3(signature = (enabled, max_rows = 4096))]
    pub fn configure_transaction_receipts(&mut self, enabled: bool, max_rows: usize) -> PyResult<()> {
        if enabled && !(1..=crate::transaction_receipts::MAX_LIMIT).contains(&max_rows) {
            return Err(PyValueError::new_err("transaction receipt max_rows must be 1..65536"));
        }
        self.transaction_receipts_limit = enabled.then_some(max_rows);
        if let Some(graph) = &mut self.merchant_graph {
            graph.receipt_limit = self.transaction_receipts_limit.unwrap_or(0);
        }
        if !enabled { self.merchant_trip_stats.receipts = None; }
        Ok(())
    }

    /// (source turn, cap, dropped rows, mobility executed, rows); reads never drain.
    /// None/0/0 means disabled or no successful recorded tick yet. Enabled empty
    /// frames have an explicit source turn. Active rows are mobility-end only.
    pub fn get_transaction_receipt_frame(&self) -> PyResult<(Option<u32>, usize, u64, bool, PyRecordBatch)> {
        let frame = self.merchant_trip_stats.receipts.as_ref();
        let batch = crate::transaction_receipts::to_batch(frame).map_err(arrow_err)?;
        Ok((frame.map(|f| f.source_turn), frame.map_or(0, |f| f.limit),
            frame.map_or(0, |f| f.dropped), frame.is_some_and(|f| f.mobility_executed),
            PyRecordBatch::new(batch)))
    }

    /// Enable a bounded pre-household decision observer. Explicit IDs are a
    /// selection, not a random sample; truncated prefixes never establish rates.
    #[pyo3(signature = (enabled, max_agent_rows = 4096, max_candidate_rows = 16384, selected_agent_ids = None, *, max_move_rows = 16384))]
    pub fn configure_decision_delivery(&mut self, enabled: bool, max_agent_rows: usize,
        max_candidate_rows: usize, selected_agent_ids: Option<Vec<u32>>, max_move_rows: usize) -> PyResult<()> {
        let config = if enabled {
            Some(crate::decision_delivery::DeliveryConfig::new(max_agent_rows,
                max_candidate_rows, selected_agent_ids).and_then(|c| c.with_move_limit(max_move_rows)).map_err(PyValueError::new_err)?)
        } else { None };
        self.decision_delivery_config = config;
        self.decision_delivery_frame = None;
        Ok(())
    }

    /// (header, decision rows, candidate rows). Reads never drain or change the
    /// pool. f32 observations are UInt32 bits; validity columns distinguish
    /// skipped computation from an observed zero. Stage 1 does not trace final
    /// household follower/cancellation provenance or counterfactual winners.
    pub fn get_decision_delivery_frame(&self) -> PyResult<(PyRecordBatch, PyRecordBatch, PyRecordBatch)> {
        let frame = self.decision_delivery_frame.as_ref();
        let header = crate::decision_delivery::header_batch(self.decision_delivery_config.as_ref(), frame).map_err(arrow_err)?;
        let decisions = crate::decision_delivery::decisions_batch(frame).map_err(arrow_err)?;
        let candidates = crate::decision_delivery::candidates_batch(frame).map_err(arrow_err)?;
        Ok((PyRecordBatch::new(header), PyRecordBatch::new(decisions), PyRecordBatch::new(candidates)))
    }

    /// Separate version-2 move header and operation rows. Native event
    /// ordinals are zero-based positions in tick()'s full unchanged native
    /// event batch, not world-event IDs. Reads are non-draining. The bounded
    /// operation prefix is independent of Stage 1 row caps and is not a sample.
    pub fn get_decision_delivery_move_frame(&self) -> PyResult<(PyRecordBatch, PyRecordBatch)> {
        let frame = self.decision_delivery_frame.as_ref();
        let header = crate::decision_delivery::move_header_batch(self.decision_delivery_config.as_ref(), frame).map_err(arrow_err)?;
        let rows = crate::decision_delivery::moves_batch(frame).map_err(arrow_err)?;
        Ok((PyRecordBatch::new(header), PyRecordBatch::new(rows)))
    }

    /// Maritime: the last tick's merchant sea-lane crossings, one row per hop
    /// across a sea lane (in slot order), with `raided` set where raiders
    /// seized the cargo (`LossReason::Raid`). Empty unless the merchant route
    /// graph carried `sea_raid_risk`. Read-only; rebuilt every tick.
    /// Columns: from_region, to_region, origin_region, dest_region (u16),
    /// good_slot (u8), qty (f32), raided (bool).
    #[pyo3(name = "get_sea_trade_log")]
    pub fn get_sea_trade_log(&self) -> PyResult<PyRecordBatch> {
        use arrow::array::{BooleanBuilder, Float32Builder};
        let log = &self.merchant_trip_stats.sea_log;
        let n = log.len();
        let mut from = UInt16Builder::with_capacity(n);
        let mut to = UInt16Builder::with_capacity(n);
        let mut origin = UInt16Builder::with_capacity(n);
        let mut dest = UInt16Builder::with_capacity(n);
        let mut slot = UInt8Builder::with_capacity(n);
        let mut qty = Float32Builder::with_capacity(n);
        let mut raided = BooleanBuilder::with_capacity(n);
        for rec in log {
            from.append_value(rec.from_region);
            to.append_value(rec.to_region);
            origin.append_value(rec.origin_region);
            dest.append_value(rec.dest_region);
            slot.append_value(rec.good_slot);
            qty.append_value(rec.qty);
            raided.append_value(rec.loss == Some(crate::merchant::LossReason::Raid));
        }
        let schema = Arc::new(Schema::new(vec![
            Field::new("from_region", DataType::UInt16, false),
            Field::new("to_region", DataType::UInt16, false),
            Field::new("origin_region", DataType::UInt16, false),
            Field::new("dest_region", DataType::UInt16, false),
            Field::new("good_slot", DataType::UInt8, false),
            Field::new("qty", DataType::Float32, false),
            Field::new("raided", DataType::Boolean, false),
        ]));
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(from.finish()), Arc::new(to.finish()), Arc::new(origin.finish()),
            Arc::new(dest.finish()), Arc::new(slot.finish()), Arc::new(qty.finish()),
            Arc::new(raided.finish()),
        ]).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// M59a: Return knowledge stats from last tick as a flat HashMap.
    #[pyo3(name = "get_knowledge_stats")]
    pub fn get_knowledge_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("packets_created".into(), self.knowledge_stats.packets_created as f64);
        stats.insert("packets_refreshed".into(), self.knowledge_stats.packets_refreshed as f64);
        stats.insert("packets_transmitted".into(), self.knowledge_stats.packets_transmitted as f64);
        stats.insert("packets_expired".into(), self.knowledge_stats.packets_expired as f64);
        stats.insert("packets_evicted".into(), self.knowledge_stats.packets_evicted as f64);
        stats.insert("packets_dropped".into(), self.knowledge_stats.packets_dropped as f64);
        stats.insert("live_packet_count".into(), self.knowledge_stats.live_packet_count as f64);
        stats.insert("agents_with_packets".into(), self.knowledge_stats.agents_with_packets as f64);
        stats.insert("created_threat".into(), self.knowledge_stats.created_threat as f64);
        stats.insert("created_trade".into(), self.knowledge_stats.created_trade as f64);
        stats.insert("created_religious".into(), self.knowledge_stats.created_religious as f64);
        stats.insert("transmitted_threat".into(), self.knowledge_stats.transmitted_threat as f64);
        stats.insert("transmitted_trade".into(), self.knowledge_stats.transmitted_trade as f64);
        stats.insert("transmitted_religious".into(), self.knowledge_stats.transmitted_religious as f64);
        // Guilds: movement news (only when there was any, so the stats of a
        // run without news keep their keys).
        if self.knowledge_stats.created_news > 0 || self.knowledge_stats.transmitted_news > 0 {
            stats.insert("created_news".into(), self.knowledge_stats.created_news as f64);
            stats.insert("transmitted_news".into(), self.knowledge_stats.transmitted_news as f64);
        }
        stats.insert("mean_age".into(), self.knowledge_stats.mean_age as f64);
        stats.insert("max_age".into(), self.knowledge_stats.max_age as f64);
        stats.insert("mean_hops".into(), self.knowledge_stats.mean_hops as f64);
        stats.insert("max_hops".into(), self.knowledge_stats.max_hops as f64);
        // M59b: Consumer counters
        stats.insert("merchant_plans_packet_driven".into(), self.knowledge_stats.merchant_plans_packet_driven as f64);
        stats.insert("merchant_plans_bootstrap".into(), self.knowledge_stats.merchant_plans_bootstrap as f64);
        stats.insert("merchant_no_usable_packets".into(), self.knowledge_stats.merchant_no_usable_packets as f64);
        stats.insert("migration_choices_changed_by_threat".into(), self.knowledge_stats.migration_choices_changed_by_threat as f64);
        // Deferred-backlog consumers (religious signals, loyalty rally)
        stats.insert("migration_choices_changed_by_religion".into(), self.knowledge_stats.migration_choices_changed_by_religion as f64);
        stats.insert("loyalty_drifts_damped_by_rally".into(), self.knowledge_stats.loyalty_drifts_damped_by_rally as f64);
        Ok(stats)
    }

    /// Read-only physical stock commitments for external redistribution.
    /// Hybrid stocks still include Loading reservations and departures awaiting
    /// the next economy tick. Arrivals/returns are not yet spendable; older
    /// in-transit cargo has already been debited and must not be subtracted again.
    /// Abstract economy modes expose zero commitments (shadow cargo is virtual).
    pub fn get_stockpile_commitments(&self) -> PyResult<PyRecordBatch> {
        use arrow::array::Float32Builder;
        use crate::economy::NUM_GOODS;

        let n = self.num_regions;
        let mut rid = UInt16Builder::with_capacity(n * NUM_GOODS);
        let mut slot = UInt8Builder::with_capacity(n * NUM_GOODS);
        let mut reserved = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut departure = Float32Builder::with_capacity(n * NUM_GOODS);
        for region in 0..n {
            for good in 0..NUM_GOODS {
                rid.append_value(region as u16);
                slot.append_value(good as u8);
                let (res, dep) = if self.hybrid_economy_mode {
                    let res = self.merchant_ledger.as_ref()
                        .and_then(|ledger| ledger.reserved.get(region))
                        .map_or(0.0, |goods| goods[good]);
                    let dep = self.merchant_delivery_buf.as_ref()
                        .and_then(|buf| buf.departure_debits.get(region))
                        .map_or(0.0, |goods| goods[good]);
                    (res, dep)
                } else { (0.0, 0.0) };
                reserved.append_value(res);
                departure.append_value(dep);
            }
        }
        let schema = Arc::new(Schema::new(vec![
            Field::new("region_id", DataType::UInt16, false),
            Field::new("good_slot", DataType::UInt8, false),
            Field::new("reserved", DataType::Float32, false),
            Field::new("pending_departure", DataType::Float32, false),
        ]));
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(rid.finish()), Arc::new(slot.finish()),
            Arc::new(reserved.finish()), Arc::new(departure.finish()),
        ]).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Contact ledger: non-draining read of the merchant arrival records that
    /// the next `tick_economy` call will consume (one row per completed
    /// delivery, in recording order). Read-only; never mutates the buffer, so
    /// calling it does not change any simulation result.
    /// Columns: source_region (u16), dest_region (u16), good_slot (u8), qty (f32).
    #[pyo3(name = "get_pending_arrivals")]
    pub fn get_pending_arrivals(&self) -> PyResult<PyRecordBatch> {
        use arrow::array::Float32Builder;

        let records: &[crate::merchant::ArrivalRecord] = match &self.merchant_delivery_buf {
            Some(buf) => &buf.arrival_imports,
            None => &[],
        };
        let n = records.len();
        let mut src = UInt16Builder::with_capacity(n);
        let mut dst = UInt16Builder::with_capacity(n);
        let mut slot = UInt8Builder::with_capacity(n);
        let mut qty = Float32Builder::with_capacity(n);
        for rec in records {
            src.append_value(rec.source_region);
            dst.append_value(rec.dest_region);
            slot.append_value(rec.good_slot);
            qty.append_value(rec.qty);
        }
        let schema = Arc::new(Schema::new(vec![
            Field::new("source_region", DataType::UInt16, false),
            Field::new("dest_region", DataType::UInt16, false),
            Field::new("good_slot", DataType::UInt8, false),
            Field::new("qty", DataType::Float32, false),
        ]));
        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(src.finish()), Arc::new(dst.finish()),
            Arc::new(slot.finish()), Arc::new(qty.finish()),
        ]).map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// M58b: Non-draining read of cumulative delivery counters.
    /// Run-lifetime monotonic — per-turn deltas derived by diffing consecutive reads.
    #[pyo3(name = "get_delivery_diagnostics")]
    pub fn get_delivery_diagnostics(&self) -> PyResult<PyRecordBatch> {
        use arrow::array::{UInt16Builder, UInt8Builder, Float32Builder};
        use crate::economy::NUM_GOODS;

        let buf = match &self.merchant_delivery_buf {
            Some(b) => &b.diagnostics,
            None => {
                // Return empty batch
                let schema = Arc::new(Schema::new(vec![
                    Field::new("region_id", DataType::UInt16, false),
                    Field::new("good_slot", DataType::UInt8, false),
                    Field::new("total_departures", DataType::Float32, false),
                    Field::new("total_arrivals", DataType::Float32, false),
                    Field::new("total_returns", DataType::Float32, false),
                    Field::new("total_transit_decay", DataType::Float32, false),
                ]));
                let batch = RecordBatch::new_empty(schema);
                return Ok(PyRecordBatch::new(batch));
            }
        };

        let n = buf.total_departures.len();
        let mut rid = UInt16Builder::with_capacity(n * NUM_GOODS);
        let mut gs = UInt8Builder::with_capacity(n * NUM_GOODS);
        let mut dep = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut arr = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut ret = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut decay = Float32Builder::with_capacity(n * NUM_GOODS);

        for region in 0..n {
            for g in 0..NUM_GOODS {
                rid.append_value(region as u16);
                gs.append_value(g as u8);
                dep.append_value(buf.total_departures[region][g]);
                arr.append_value(buf.total_arrivals[region][g]);
                ret.append_value(buf.total_returns[region][g]);
                decay.append_value(buf.total_transit_decay[region][g]);
            }
        }

        let schema = Arc::new(Schema::new(vec![
            Field::new("region_id", DataType::UInt16, false),
            Field::new("good_slot", DataType::UInt8, false),
            Field::new("total_departures", DataType::Float32, false),
            Field::new("total_arrivals", DataType::Float32, false),
            Field::new("total_returns", DataType::Float32, false),
            Field::new("total_transit_decay", DataType::Float32, false),
        ]));

        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(rid.finish()),
            Arc::new(gs.finish()),
            Arc::new(dep.finish()),
            Arc::new(arr.finish()),
            Arc::new(ret.finish()),
            Arc::new(decay.finish()),
        ]).map_err(arrow_err)?;

        Ok(PyRecordBatch::new(batch))
    }
}

impl AgentSimulator {
    /// M48: Write Promotion memories queued by the previous `get_promotions()`
    /// call, stamped with their promotion turn. Draining clears the queue
    /// (one-shot); `write_all_memories` skips slots reused since promotion.
    fn flush_pending_promotion_memories(&mut self) {
        for (promotion_turn, intent) in std::mem::take(&mut self.pending_promotion_memories) {
            crate::memory::write_all_memories(
                &mut self.pool, std::slice::from_ref(&intent), promotion_turn,
            );
        }
    }
}

// ---------------------------------------------------------------------------
#[cfg(test)]
mod agent_context_tests;
// CAREOBS_SOURCE_BEGIN: PyO3 contracts
#[cfg(test)]
mod health_care_observation_tests;
// CAREOBS_SOURCE_END: PyO3 contracts

#[cfg(test)]
mod tests {
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

}

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(AgentSimulator {
    pool, regions, contested_regions, master_seed, num_regions, turn, registry, initialized,
    wealth_percentiles, kin_bond_failures, formation_stats, prev_kin_bond_failures,
    last_tick_deaths, last_tick_births, last_tick_alive, demographic_debug, ecology_config,
    river_topology, recompute_ctx, spatial_grids, attractors, spatial_initialized,
    last_spatial_diag, economy_config, politics_config, settlement_grids, household_stats,
    merchant_graph, merchant_cargo, merchant_ledger, merchant_delivery_buf,
    merchant_trip_stats, knowledge_stats, hybrid_economy_mode, pending_targeted_deaths,
    movements, pending_movement_leaders, pending_promotion_memories, tick_options,
} skip { snapshot_cache } transient {
    health_work, transaction_receipts_limit, decision_delivery_config, decision_delivery_frame
});

#[cfg(test)]
mod health_care_policy_tests {
    use super::*;

    #[test]
    fn health_policy_ffi_validates_before_mutation_and_preserves_native_payload() {
        let mut sim = AgentSimulator::new(1, 42);
        let patient = sim.pool.spawn(0, 0, crate::Occupation::Farmer, 30,
            0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let donor = sim.pool.spawn(0, 0, crate::Occupation::Farmer, 30,
            0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        for (a, b) in [(patient, donor), (donor, patient)] {
            sim.pool.rel_count[a] = 1;
            sim.pool.rel_target_ids[a][0] = sim.pool.ids[b];
            sim.pool.rel_bond_types[a][0] = crate::relationships::BondType::Kin as u8;
        }
        let id = sim.pool.ids[patient];
        let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
        assert_eq!(sim.prepare_health_work(vec![id], vec![], vec![], 0.5, 0.2, "spouse").unwrap(),
            vec![(id, 0, 0, 0.0)]);
        let rows = sim.health_work.as_ref().unwrap().rows.clone();
        let losses = sim.pool.health_work_loss.clone();
        assert!(sim.prepare_health_work(vec![id], vec![], vec![], 0.5, 0.2, "kin").is_err());
        assert_eq!(sim.health_work.as_ref().unwrap().rows, rows);
        assert_eq!(sim.pool.health_work_loss, losses);
        assert_eq!(sim.prepare_health_work(vec![id], vec![], vec![], 0.5, 0.2, "retained_kin").unwrap(),
            vec![(id, 0, sim.pool.ids[donor], 0.2)]);
        assert_eq!(before, crate::persist::encode(crate::persist::KIND_AGENT, &sim));
        assert!(!crate::persist::schema_of::<AgentSimulator>().contains("health_work"));
    }
}
