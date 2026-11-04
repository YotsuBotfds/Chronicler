//! Bounded, transient observations at the decision boundary.
//!
//! Stage 1 describes pre-household decisions and admissible destinations, not
//! final applied moves or counterfactual winners. Floating-point observations
//! are exported as their original f32 bits. No simulation reads this module.

use std::{collections::BTreeMap, sync::Arc};
use arrow::array::{ArrayRef, BooleanArray, UInt8Array, UInt16Array, UInt32Array, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use crate::{migration_drivers::{Mobility, VoluntaryPull}, needs::NeedUtilityTrace, pool::AgentPool};

pub const DEFAULT_AGENT_LIMIT: usize = 4096;
pub const DEFAULT_CANDIDATE_LIMIT: usize = 16384;
pub const DEFAULT_MOVE_LIMIT: usize = 16384;
pub const MAX_LIMIT: usize = 65536;
pub const SCHEMA_VERSION: u16 = 1;
pub const STATUS_TRIP: u8 = 1;
pub const STATUS_EVALUATED: u8 = 2;

#[derive(Clone, Debug)]
pub struct DeliveryConfig {
    pub agent_limit: usize,
    pub candidate_limit: usize,
    pub move_limit: usize,
    /// None selects all alive agents; explicit IDs must be sorted and unique.
    pub selected_ids: Option<Vec<u32>>,
}

impl DeliveryConfig {
    pub fn new(agent_limit: usize, candidate_limit: usize, selected_ids: Option<Vec<u32>>) -> Result<Self, &'static str> {
        if !(1..=MAX_LIMIT).contains(&agent_limit) || !(1..=MAX_LIMIT).contains(&candidate_limit) {
            return Err("decision delivery row limits must be 1..65536");
        }
        if let Some(ids) = &selected_ids {
            if ids.len() > MAX_LIMIT || ids.windows(2).any(|w| w[0] >= w[1]) {
                return Err("decision delivery IDs must be sorted, unique and bounded");
            }
        }
        Ok(Self { agent_limit, candidate_limit, move_limit: DEFAULT_MOVE_LIMIT, selected_ids })
    }

    pub fn with_move_limit(mut self, move_limit: usize) -> Result<Self, &'static str> {
        if !(1..=MAX_LIMIT).contains(&move_limit) { return Err("decision delivery move row limit must be 1..65536"); }
        self.move_limit = move_limit;
        Ok(self)
    }

    #[inline]
    fn selected(&self, id: u32) -> bool {
        self.selected_ids.as_ref().map_or(true, |ids| ids.binary_search(&id).is_ok())
    }
}

/// A fixed region quota avoids locks and scheduling-dependent truncation.
pub fn region_quota(limit: usize, region: usize, regions: usize) -> usize {
    if regions == 0 { return 0; }
    limit / regions + usize::from(region < limit % regions)
}

#[derive(Clone, Debug, Default)]
pub struct DeliveryCounts {
    pub alive_all: u64,
    pub selected_alive: u64,
    pub trips_all: u64,
    pub evaluated_all: u64,
    pub displaced_all: u64,
    pub mobility_all: u64,
    pub admissible_candidates_all: u64,
    pub dropped_agents: u64,
    pub dropped_candidates: u64,
}

impl DeliveryCounts {
    fn merge(&mut self, other: &Self) {
        self.alive_all += other.alive_all;
        self.selected_alive += other.selected_alive;
        self.trips_all += other.trips_all;
        self.evaluated_all += other.evaluated_all;
        self.displaced_all += other.displaced_all;
        self.mobility_all += other.mobility_all;
        self.admissible_candidates_all += other.admissible_candidates_all;
        self.dropped_agents += other.dropped_agents;
        self.dropped_candidates += other.dropped_candidates;
    }
}

#[derive(Clone, Debug)]
pub struct DecisionRow {
    pub agent_id: u32,
    pub region: u16,
    pub civ: u8,
    pub occupation: u8,
    pub age: u16,
    pub displacement: u16,
    pub status: u8,
    pub mobility_eligible: bool,
    pub needs_computed: bool,
    pub needs_migration_applied: bool,
    pub wealth_computed: bool,
    pub wealth_multiplier_applied: bool,
    pub community_anchor_computed: bool,
    pub final_utilities_valid: bool,
    pub loyalty_drift_observed: bool,
    pub selected_target: u16,
    pub chosen_action: u8,
    pub needs: [f32; 6],
    /// rebel, migrate, switch occupation, stay; actual values around the cap.
    pub raw_need: [f32; 4],
    pub capped_need: [f32; 4],
    /// safety, material, social, spiritual; copied products, never a raw sum.
    pub need_migration_channels: [f32; 4],
    /// base, pre-needs, post-needs, post-pull, post-wealth, final migration.
    pub migration_stages: [f32; 6],
    pub utilities: [f32; 4],
    pub roots: f32,
    pub home_bonds: f32,
    pub opportunity: f32,
    pub voluntary_pull: f32,
    pub personal_wealth: f32,
    pub effective_wealth: f32,
    pub wealth_factor: f32,
    pub community_anchor: f32,
    pub autonomy_deficit: f32,
    pub autonomy_factor: f32,
    pub effective_drift: f32,
}

impl DecisionRow {
    fn new(pool: &AgentPool, slot: usize, region: usize) -> Self {
        Self {
            agent_id: pool.ids[slot], region: region as u16,
            civ: pool.civ_affinities[slot], occupation: pool.occupations[slot],
            age: pool.ages[slot], displacement: pool.displacement_turns[slot] as u16,
            status: 0, mobility_eligible: false, needs_computed: false,
            needs_migration_applied: false, wealth_computed: false,
            wealth_multiplier_applied: false, community_anchor_computed: false,
            final_utilities_valid: false, loyalty_drift_observed: false,
            selected_target: region as u16, chosen_action: u8::MAX,
            needs: [pool.need_safety[slot], pool.need_material[slot], pool.need_social[slot],
                pool.need_spiritual[slot], pool.need_autonomy[slot], pool.need_purpose[slot]],
            raw_need: [0.0; 4], capped_need: [0.0; 4], need_migration_channels: [0.0; 4],
            migration_stages: [0.0; 6], utilities: [0.0; 4], roots: 0.0,
            home_bonds: 0.0, opportunity: 0.0, voluntary_pull: 0.0,
            personal_wealth: pool.wealth[slot], effective_wealth: 0.0, wealth_factor: 1.0,
            community_anchor: 0.0, autonomy_deficit: 0.0, autonomy_factor: 1.0,
            effective_drift: 0.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct CandidateRow {
    pub agent_id: u32,
    pub region: u16,
    pub target: u16,
    pub mobility_eligible: bool,
    pub hysteresis_kept: bool,
    /// True at this iteration, not necessarily the final selected target.
    pub became_best: bool,
    pub own_score: f32,
    pub own_ratio: f32,
    pub target_ratio: f32,
    pub roots: f32,
    pub gross: [f32; 5],
    pub net: [f32; 5],
    pub post_roots_pull: f32,
    pub applied_pull: f32,
    pub target_base_score: f32,
    pub river: f32,
    pub pre_news_score: f32,
}

fn pull_fields(p: &VoluntaryPull) -> [f32; 5] {
    [p.frontier, p.wage, p.chain, p.urban, p.learning]
}

/// The ordinary decision path uses this zero-sized monomorphized sink.
pub struct NoDelivery;

pub(crate) trait DecisionObserver {
    const ENABLED: bool = false;
    #[inline(always)] fn begin_agent(&mut self, _pool: &AgentPool, _slot: usize, _region: usize) {}
    #[inline(always)] fn trip(&mut self) {}
    #[inline(always)] fn evaluated(&mut self, _displaced: bool) {}
    #[inline(always)] fn mobility(&mut self, _mobility: Option<&Mobility>) {}
    #[inline(always)] fn need(&mut self, _trace: &NeedUtilityTrace, _migration_applied: bool) {}
    #[inline(always)] fn stage(&mut self, _stage: usize, _value: f32) {}
    #[inline(always)] fn wealth(&mut self, _personal: f32, _effective: f32, _factor: f32, _applied: bool) {}
    #[inline(always)] fn anchor(&mut self, _value: f32) {}
    #[inline(always)] fn final_decision(&mut self, _target: u16, _opportunity: f32, _pull: f32, _utilities: [f32; 4], _chosen: u8) {}
    #[inline(always)] fn autonomy(&mut self, _deficit: f32, _factor: f32, _drift: f32) {}
    #[inline(always)] fn begin_candidate(&mut self, _target: u16, _score: f32, _own_ratio: f32, _target_ratio: f32) {}
    #[inline(always)] fn candidate_pull(&mut self, _gross: &VoluntaryPull, _roots: f32, _net: &VoluntaryPull) {}
    #[inline(always)] fn candidate_before_hysteresis(&mut self, _pull: f32) {}
    #[inline(always)] fn candidate_hysteresis(&mut self, _kept: bool) {}
    #[inline(always)] fn end_candidate(&mut self, _pull: f32, _base: f32, _river: f32, _news: f32, _became_best: bool) {}
}
impl DecisionObserver for NoDelivery {}

pub(crate) struct RegionDelivery<'a> {
    config: &'a DeliveryConfig,
    agent_quota: usize,
    candidate_quota: usize,
    selected: bool,
    current_agent: Option<usize>,
    current_candidate: Option<usize>,
    pub counts: DeliveryCounts,
    pub decisions: Vec<DecisionRow>,
    pub candidates: Vec<CandidateRow>,
}

impl<'a> RegionDelivery<'a> {
    pub fn new(config: &'a DeliveryConfig, region: usize, regions: usize) -> Self {
        let agent_quota = region_quota(config.agent_limit, region, regions);
        let candidate_quota = region_quota(config.candidate_limit, region, regions);
        Self { config, agent_quota, candidate_quota, selected: false,
            current_agent: None, current_candidate: None, counts: DeliveryCounts::default(),
            decisions: Vec::with_capacity(agent_quota.min(128)),
            candidates: Vec::with_capacity(candidate_quota.min(128)) }
    }
    fn agent(&mut self) -> Option<&mut DecisionRow> { self.decisions.get_mut(self.current_agent?) }
    fn candidate(&mut self) -> Option<&mut CandidateRow> { self.candidates.get_mut(self.current_candidate?) }
}

impl DecisionObserver for RegionDelivery<'_> {
    const ENABLED: bool = true;
    fn begin_agent(&mut self, pool: &AgentPool, slot: usize, region: usize) {
        self.counts.alive_all += 1;
        self.selected = self.config.selected(pool.ids[slot]);
        self.current_agent = None; self.current_candidate = None;
        if !self.selected { return; }
        self.counts.selected_alive += 1;
        if self.decisions.len() == self.agent_quota { self.counts.dropped_agents += 1; return; }
        self.current_agent = Some(self.decisions.len());
        self.decisions.push(DecisionRow::new(pool, slot, region));
    }
    fn trip(&mut self) { self.counts.trips_all += 1; if let Some(r) = self.agent() { r.status = STATUS_TRIP; } }
    fn evaluated(&mut self, displaced: bool) {
        self.counts.evaluated_all += 1; self.counts.displaced_all += u64::from(displaced);
        if let Some(r) = self.agent() { r.status = STATUS_EVALUATED; }
    }
    fn mobility(&mut self, mobility: Option<&Mobility>) {
        self.counts.mobility_all += u64::from(mobility.is_some());
        if let Some(r) = self.agent() { if let Some(m) = mobility {
            r.mobility_eligible = true; r.roots = m.roots; r.home_bonds = m.home_bonds;
        } }
    }
    fn need(&mut self, trace: &NeedUtilityTrace, migration_applied: bool) {
        if let Some(r) = self.agent() {
            r.needs = trace.inputs; r.raw_need = trace.raw; r.capped_need = trace.capped;
            r.need_migration_channels = trace.migrate_channels; r.needs_computed = true;
            r.needs_migration_applied = migration_applied;
        }
    }
    fn stage(&mut self, stage: usize, value: f32) { if let Some(r) = self.agent() { r.migration_stages[stage] = value; } }
    fn wealth(&mut self, personal: f32, effective: f32, factor: f32, applied: bool) { if let Some(r) = self.agent() {
        r.personal_wealth = personal; r.effective_wealth = effective; r.wealth_factor = factor; r.wealth_computed = true;
        r.wealth_multiplier_applied = applied;
    } }
    fn anchor(&mut self, value: f32) { if let Some(r) = self.agent() { r.community_anchor = value; r.community_anchor_computed = true; } }
    fn final_decision(&mut self, target: u16, opportunity: f32, pull: f32, utilities: [f32; 4], chosen: u8) { if let Some(r) = self.agent() {
        r.selected_target = target; r.opportunity = opportunity; r.voluntary_pull = pull;
        r.utilities = utilities; r.chosen_action = chosen; r.final_utilities_valid = true;
    } }
    fn autonomy(&mut self, deficit: f32, factor: f32, drift: f32) { if let Some(r) = self.agent() {
        r.autonomy_deficit = deficit; r.autonomy_factor = factor; r.effective_drift = drift; r.loyalty_drift_observed = true;
    } }
    fn begin_candidate(&mut self, target: u16, score: f32, own_ratio: f32, target_ratio: f32) {
        self.counts.admissible_candidates_all += 1; self.current_candidate = None;
        if !self.selected { return; }
        if self.candidates.len() == self.candidate_quota { self.counts.dropped_candidates += 1; return; }
        let Some(agent) = self.current_agent else { self.counts.dropped_candidates += 1; return; };
        let r = &self.decisions[agent]; self.current_candidate = Some(self.candidates.len());
        self.candidates.push(CandidateRow { agent_id: r.agent_id, region: r.region, target,
            mobility_eligible: r.mobility_eligible, hysteresis_kept: false, became_best: false,
            own_score: score, own_ratio, target_ratio, roots: r.roots,
            gross: [0.0; 5], net: [0.0; 5], post_roots_pull: 0.0, applied_pull: 0.0,
            target_base_score: 0.0, river: 0.0, pre_news_score: 0.0 });
    }
    fn candidate_pull(&mut self, gross: &VoluntaryPull, roots: f32, net: &VoluntaryPull) { if let Some(r) = self.candidate() {
        r.gross = pull_fields(gross); r.net = pull_fields(net); r.roots = roots;
    } }
    fn candidate_before_hysteresis(&mut self, pull: f32) { if let Some(r) = self.candidate() { r.post_roots_pull = pull; } }
    fn candidate_hysteresis(&mut self, kept: bool) { if let Some(r) = self.candidate() { r.hysteresis_kept = kept; } }
    fn end_candidate(&mut self, pull: f32, base: f32, river: f32, news: f32, became_best: bool) { if let Some(r) = self.candidate() {
        r.applied_pull = pull;
        r.target_base_score = base; r.river = river; r.pre_news_score = news; r.became_best = became_best;
    } }
}

#[derive(Clone, Debug)]
pub struct DeliveryFrame {
    pub source_turn: u32,
    pub ablation: u8,
    pub counts: DeliveryCounts,
    pub decisions: Vec<DecisionRow>,
    pub candidates: Vec<CandidateRow>,
    pub moves: MoveFrame,
}
impl DeliveryFrame {
    pub fn new(source_turn: u32, ablation: u8) -> Self {
        Self { source_turn, ablation, counts: DeliveryCounts::default(), decisions: Vec::new(), candidates: Vec::new(), moves: MoveFrame::default() }
    }
    pub(crate) fn merge_region(&mut self, mut region: RegionDelivery<'_>) {
        self.counts.merge(&region.counts);
        self.decisions.append(&mut region.decisions); self.candidates.append(&mut region.candidates);
    }
    pub fn stage_complete(&self) -> bool { self.counts.dropped_agents == 0 && self.counts.dropped_candidates == 0 }
}

pub const MOVE_ROLE_OWN: u8 = 0;
pub const MOVE_ROLE_SPOUSE: u8 = 1;
pub const MOVE_ROLE_DEPENDENT: u8 = 2;
pub const MOVE_ROLE_UNKNOWN: u8 = u8::MAX;
pub const MOVE_REASON_NONE: u8 = 0;
pub const MOVE_REASON_REBELLION: u8 = 1;
pub const MOVE_REASON_CATASTROPHE: u8 = 2;
pub const MOVE_OWN_PROPOSAL: u8 = 1;
pub const MOVE_REPLACEMENT_REMOVED: u8 = 2;
pub const MOVE_FOLLOWER_WRITTEN: u8 = 3;
pub const MOVE_CANCELLED: u8 = 4;
pub const MOVE_BLOCKED: u8 = 5;
pub const MOVE_DEDUP_REMOVED: u8 = 6;
pub const MOVE_APPLIED: u8 = 7;

/// Observation hooks share the physical operation's order. The default path
/// monomorphizes this zero-sized sink without a proposal scan or tracking map.
#[allow(clippy::too_many_arguments)]
pub(crate) trait MoveObserver {
    const ENABLED: bool = false;
    #[inline(always)] fn begin(&mut self, _pool: &AgentPool, _pending: &[crate::behavior::PendingDecisions]) {}
    #[inline(always)] fn replacement_removed(&mut self, _pool: &AgentPool, _bucket: usize, _migration: (usize, u16, u16), _lead_slot: usize, _role: u8) {}
    #[inline(always)] fn follower_written(&mut self, _pool: &AgentPool, _bucket: usize, _slot: usize, _from: u16, _to: u16, _lead_slot: usize, _role: u8, _removed_count: usize, _last_removed: Option<(u16, u16)>) {}
    #[inline(always)] fn cancelled(&mut self, _pool: &AgentPool, _bucket: usize, _migration: (usize, u16, u16), _lead_slot: usize, _trailing_slot: usize, _reason: u8, _rejected_to: u16) {}
    #[inline(always)] fn blocked(&mut self, _pool: &AgentPool, _bucket: usize, _slot: usize, _from: u16, _to: u16, _lead_slot: usize, _trailing_slot: usize, _role: u8, _reason: u8) {}
    #[inline(always)] fn dedup_removed(&mut self, _pool: &AgentPool, _bucket: usize, _migration: (usize, u16, u16)) {}
    #[inline(always)] fn applied(&mut self, _pool: &AgentPool, _bucket: usize, _migration: (usize, u16, u16), _event_ordinal: usize, _driver: u8) {}
}
impl MoveObserver for NoDelivery {}

#[derive(Clone, Debug, Default)]
pub struct MoveCounts {
    pub operations_all: u64,
    pub operations_selected: u64,
    pub dropped_rows: u64,
    pub tracking_dropped: u64,
    pub tracked_peak: usize,
    pub own_proposals_all: u64,
    pub replacement_removals_all: u64,
    pub follower_writes_all: u64,
    pub cancelled_existing_all: u64,
    pub blocked_nonproposers_all: u64,
    pub dedup_drops_all: u64,
    pub applied_all: u64,
    pub applied_selected: u64,
    pub missing_applied_origins: u64,
}

#[derive(Clone, Debug)]
pub struct MoveRow {
    /// Ordinal of this observed native operation, including unselected visits.
    pub operation_ordinal: u64,
    pub operation: u8,
    pub bucket: u16,
    pub agent_id: u32,
    pub from: u16,
    pub to: u16,
    pub role: u8,
    pub lead_id: Option<u32>,
    pub trigger_agent_id: Option<u32>,
    pub reason: u8,
    pub rejected_to: Option<u16>,
    /// Current proposal immediately before this operation, from the actual
    /// retain scan. This is not a claim about an unobserved initial decision.
    pub prior_count_valid: bool,
    pub prior_count: u64,
    pub prior_from: Option<u16>,
    pub prior_to: Option<u16>,
    pub origin_valid: bool,
    pub origin_operation_ordinal: Option<u64>,
    /// Index in the unchanged full native event batch, never a world event ID.
    pub native_event_ordinal: Option<u64>,
    /// Existing positive-term attribution, separate from household provenance.
    pub migration_driver: Option<u8>,
}

impl MoveRow {
    fn new(operation: u8, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16)) -> Self {
        Self { operation_ordinal: 0, operation, bucket: bucket as u16,
            agent_id: pool.ids[migration.0], from: migration.1, to: migration.2,
            role: MOVE_ROLE_UNKNOWN, lead_id: None, trigger_agent_id: None,
            reason: MOVE_REASON_NONE, rejected_to: None, prior_count_valid: false,
            prior_count: 0, prior_from: None, prior_to: None, origin_valid: false,
            origin_operation_ordinal: None, native_event_ordinal: None, migration_driver: None }
    }
}

#[derive(Clone, Debug, Default)]
pub struct MoveFrame {
    pub counts: MoveCounts,
    pub rows: Vec<MoveRow>,
    pub finished: bool,
}
impl MoveFrame {
    pub fn complete(&self) -> bool {
        self.finished && self.counts.dropped_rows == 0 && self.counts.tracking_dropped == 0
            && self.counts.missing_applied_origins == 0
    }
}

#[derive(Clone, Copy)]
struct MoveOrigin {
    role: u8,
    lead_id: Option<u32>,
    from: u16,
    to: u16,
    operation_ordinal: u64,
    valid: bool,
}

pub(crate) struct MoveDelivery<'a> {
    config: &'a DeliveryConfig,
    frame: MoveFrame,
    // A bounded deterministic map avoids constructing RandomState, which can
    // change seeds used by later production HashMaps on this same thread.
    origins: BTreeMap<(usize, u32), MoveOrigin>,
}

impl<'a> MoveDelivery<'a> {
    pub fn new(config: &'a DeliveryConfig) -> Self {
        Self { config, frame: MoveFrame { rows: Vec::with_capacity(config.move_limit.min(128)), ..Default::default() }, origins: BTreeMap::new() }
    }
    fn record(&mut self, mut row: MoveRow) -> (u64, bool) {
        let ordinal = self.frame.counts.operations_all;
        row.operation_ordinal = ordinal;
        let c = &mut self.frame.counts;
        c.operations_all += 1;
        match row.operation {
            MOVE_OWN_PROPOSAL => c.own_proposals_all += 1,
            MOVE_REPLACEMENT_REMOVED => c.replacement_removals_all += 1,
            MOVE_FOLLOWER_WRITTEN => c.follower_writes_all += 1,
            MOVE_CANCELLED => c.cancelled_existing_all += 1,
            MOVE_BLOCKED => c.blocked_nonproposers_all += 1,
            MOVE_DEDUP_REMOVED => c.dedup_drops_all += 1,
            MOVE_APPLIED => c.applied_all += 1,
            _ => unreachable!("native move observation kind"),
        }
        let selected = self.config.selected(row.agent_id);
        if !selected { return (ordinal, false); }
        c.operations_selected += 1;
        if row.operation == MOVE_APPLIED { c.applied_selected += 1; }
        if self.frame.rows.len() == self.config.move_limit { c.dropped_rows += 1; }
        else { self.frame.rows.push(row); }
        (ordinal, true)
    }
    fn track(&mut self, key: (usize, u32), mut origin: MoveOrigin, initial: bool) {
        if let Some(previous) = self.origins.get_mut(&key) {
            // Duplicate initial proposals have no unique operation origin.
            // A later actual follower write resolves that ambiguity.
            if initial { origin.valid = false; }
            *previous = origin;
        } else if self.origins.len() < self.config.move_limit {
            self.origins.insert(key, origin);
            self.frame.counts.tracked_peak = self.frame.counts.tracked_peak.max(self.origins.len());
        } else { self.frame.counts.tracking_dropped += 1; }
    }
    pub fn finish(mut self) -> MoveFrame { self.frame.finished = true; self.frame }
}

impl MoveObserver for MoveDelivery<'_> {
    const ENABLED: bool = true;
    fn begin(&mut self, pool: &AgentPool, pending: &[crate::behavior::PendingDecisions]) {
        for (bucket, decisions) in pending.iter().enumerate() { for &migration in &decisions.migrations {
            let mut row = MoveRow::new(MOVE_OWN_PROPOSAL, pool, bucket, migration);
            row.role = MOVE_ROLE_OWN; row.origin_valid = true;
            let (ordinal, selected) = self.record(row);
            if selected { self.track((bucket, pool.ids[migration.0]), MoveOrigin {
                role: MOVE_ROLE_OWN, lead_id: None, from: migration.1, to: migration.2,
                operation_ordinal: ordinal, valid: true,
            }, true); }
        } }
    }
    fn replacement_removed(&mut self, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16), lead_slot: usize, role: u8) {
        let mut row = MoveRow::new(MOVE_REPLACEMENT_REMOVED, pool, bucket, migration);
        row.role = role; row.lead_id = Some(pool.ids[lead_slot]);
        row.prior_count_valid = true; row.prior_count = 1;
        row.prior_from = Some(migration.1); row.prior_to = Some(migration.2);
        self.record(row);
    }
    fn follower_written(&mut self, pool: &AgentPool, bucket: usize, slot: usize, from: u16, to: u16, lead_slot: usize, role: u8, removed_count: usize, last_removed: Option<(u16, u16)>) {
        let mut row = MoveRow::new(MOVE_FOLLOWER_WRITTEN, pool, bucket, (slot, from, to));
        row.role = role; row.lead_id = Some(pool.ids[lead_slot]); row.origin_valid = true;
        row.prior_count_valid = true; row.prior_count = removed_count as u64;
        row.prior_from = last_removed.map(|m| m.0); row.prior_to = last_removed.map(|m| m.1);
        let (ordinal, selected) = self.record(row);
        if selected { self.track((bucket, pool.ids[slot]), MoveOrigin {
            role, lead_id: Some(pool.ids[lead_slot]), from, to, operation_ordinal: ordinal, valid: true,
        }, false); }
    }
    fn cancelled(&mut self, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16), lead_slot: usize, trailing_slot: usize, reason: u8, rejected_to: u16) {
        let mut row = MoveRow::new(MOVE_CANCELLED, pool, bucket, migration);
        row.role = if migration.0 == lead_slot { MOVE_ROLE_OWN } else if migration.0 == trailing_slot { MOVE_ROLE_SPOUSE } else { MOVE_ROLE_DEPENDENT };
        row.lead_id = Some(pool.ids[lead_slot]); row.reason = reason; row.rejected_to = Some(rejected_to);
        if reason == MOVE_REASON_REBELLION { row.trigger_agent_id = Some(pool.ids[trailing_slot]); }
        row.prior_count_valid = true; row.prior_count = 1;
        row.prior_from = Some(migration.1); row.prior_to = Some(migration.2);
        let (_, selected) = self.record(row);
        if selected { self.origins.remove(&(bucket, pool.ids[migration.0])); }
    }
    fn blocked(&mut self, pool: &AgentPool, bucket: usize, slot: usize, from: u16, to: u16, lead_slot: usize, trailing_slot: usize, role: u8, reason: u8) {
        let mut row = MoveRow::new(MOVE_BLOCKED, pool, bucket, (slot, from, to));
        row.role = role; row.lead_id = Some(pool.ids[lead_slot]); row.reason = reason;
        row.rejected_to = Some(to); row.prior_count_valid = true;
        if reason == MOVE_REASON_REBELLION { row.trigger_agent_id = Some(pool.ids[trailing_slot]); }
        self.record(row);
    }
    fn dedup_removed(&mut self, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16)) {
        // This is an older tuple discarded by the reverse scan. The surviving
        // last-write origin must remain untouched.
        self.record(MoveRow::new(MOVE_DEDUP_REMOVED, pool, bucket, migration));
    }
    fn applied(&mut self, pool: &AgentPool, bucket: usize, migration: (usize, u16, u16), event_ordinal: usize, driver: u8) {
        let mut row = MoveRow::new(MOVE_APPLIED, pool, bucket, migration);
        row.native_event_ordinal = Some(event_ordinal as u64); row.migration_driver = Some(driver);
        if let Some(origin) = self.origins.get(&(bucket, row.agent_id)).filter(|o| o.valid && o.from == migration.1 && o.to == migration.2) {
            row.role = origin.role; row.lead_id = origin.lead_id;
            row.origin_valid = true; row.origin_operation_ordinal = Some(origin.operation_ordinal);
        } else if self.config.selected(row.agent_id) { self.frame.counts.missing_applied_origins += 1; }
        self.record(row);
    }
}

fn batch(columns: Vec<(Field, ArrayRef)>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let (fields, arrays): (Vec<_>, Vec<_>) = columns.into_iter().unzip();
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
}

/// Separate new API; existing event/statistics/snapshot schemas are untouched.
pub fn header_batch(config: Option<&DeliveryConfig>, frame: Option<&DeliveryFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let empty = DeliveryCounts::default(); let c = frame.map_or(&empty, |f| &f.counts);
    macro_rules! count { ($name:literal, $value:expr) => { (Field::new($name, DataType::UInt64, false), Arc::new(UInt64Array::from(vec![$value as u64])) as ArrayRef) }; }
    batch(vec![
        (Field::new("schema_version", DataType::UInt16, false), Arc::new(UInt16Array::from(vec![SCHEMA_VERSION]))),
        (Field::new("enabled", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![config.is_some()]))),
        (Field::new("source_turn", DataType::UInt32, true), Arc::new(UInt32Array::from(vec![frame.map(|f| f.source_turn)]))),
        (Field::new("active_ablation", DataType::UInt8, false), Arc::new(UInt8Array::from(vec![frame.map_or(0, |f| f.ablation)]))),
        (Field::new("decision_capture_complete", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![frame.is_some_and(DeliveryFrame::stage_complete)]))),
        (Field::new("applied_move_provenance_complete", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![false]))),
        (Field::new("counterfactual_marginals_computed", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![false]))),
        (Field::new("selection_is_explicit", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![config.is_some_and(|c| c.selected_ids.is_some())]))),
        count!("agent_limit", config.map_or(0, |c| c.agent_limit)), count!("candidate_limit", config.map_or(0, |c| c.candidate_limit)),
        count!("selected_ids_requested", config.and_then(|c| c.selected_ids.as_ref()).map_or(0, Vec::len)),
        count!("alive_seen_all", c.alive_all), count!("selected_alive_seen", c.selected_alive),
        count!("trip_skipped_all", c.trips_all), count!("evaluated_all", c.evaluated_all),
        count!("displaced_all", c.displaced_all), count!("mobility_eligible_all", c.mobility_all),
        count!("admissible_candidates_all", c.admissible_candidates_all),
        count!("dropped_agent_rows", c.dropped_agents), count!("dropped_candidate_rows", c.dropped_candidates),
    ])
}

pub fn decisions_batch(frame: Option<&DeliveryFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let rows = frame.map_or(&[][..], |f| f.decisions.as_slice()); let mut columns = Vec::new();
    macro_rules! col { ($name:expr, $dtype:ident, $array:ident, $value:expr) => { columns.push((Field::new($name, DataType::$dtype, false), Arc::new($array::from(rows.iter().map($value).collect::<Vec<_>>())) as ArrayRef)); }; }
    col!("agent_id", UInt32, UInt32Array, |r: &DecisionRow| r.agent_id); col!("region", UInt16, UInt16Array, |r: &DecisionRow| r.region);
    col!("civ", UInt8, UInt8Array, |r: &DecisionRow| r.civ); col!("occupation", UInt8, UInt8Array, |r: &DecisionRow| r.occupation);
    col!("age", UInt16, UInt16Array, |r: &DecisionRow| r.age); col!("displacement", UInt16, UInt16Array, |r: &DecisionRow| r.displacement);
    col!("status", UInt8, UInt8Array, |r: &DecisionRow| r.status); col!("selected_target", UInt16, UInt16Array, |r: &DecisionRow| r.selected_target);
    col!("chosen_action", UInt8, UInt8Array, |r: &DecisionRow| r.chosen_action);
    macro_rules! boolean { ($field:ident) => { col!(stringify!($field), Boolean, BooleanArray, |r: &DecisionRow| r.$field); }; }
    boolean!(mobility_eligible); boolean!(needs_computed); boolean!(needs_migration_applied); boolean!(wealth_computed); boolean!(wealth_multiplier_applied); boolean!(community_anchor_computed); boolean!(final_utilities_valid); boolean!(loyalty_drift_observed);
    for (i, name) in ["safety", "material", "social", "spiritual", "autonomy", "purpose"].iter().enumerate() { col!(&format!("need_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.needs[i].to_bits()); }
    for (i, name) in ["rebel", "migrate", "switch", "stay"].iter().enumerate() {
        col!(&format!("need_raw_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.raw_need[i].to_bits());
        col!(&format!("need_capped_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.capped_need[i].to_bits());
        col!(&format!("utility_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.utilities[i].to_bits());
    }
    for (i, name) in ["safety", "material", "social", "spiritual"].iter().enumerate() { col!(&format!("migration_need_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.need_migration_channels[i].to_bits()); }
    for (i, name) in ["base", "pre_needs", "post_needs", "post_pull", "post_wealth", "final"].iter().enumerate() { col!(&format!("migration_{name}_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.migration_stages[i].to_bits()); }
    macro_rules! bits { ($field:ident) => { col!(concat!(stringify!($field), "_bits"), UInt32, UInt32Array, |r: &DecisionRow| r.$field.to_bits()); }; }
    bits!(roots); bits!(home_bonds); bits!(opportunity); bits!(voluntary_pull); bits!(personal_wealth); bits!(effective_wealth); bits!(wealth_factor); bits!(community_anchor); bits!(autonomy_deficit); bits!(autonomy_factor); bits!(effective_drift);
    batch(columns)
}

pub fn candidates_batch(frame: Option<&DeliveryFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let rows = frame.map_or(&[][..], |f| f.candidates.as_slice()); let mut columns = Vec::new();
    macro_rules! col { ($name:expr, $dtype:ident, $array:ident, $value:expr) => { columns.push((Field::new($name, DataType::$dtype, false), Arc::new($array::from(rows.iter().map($value).collect::<Vec<_>>())) as ArrayRef)); }; }
    col!("agent_id", UInt32, UInt32Array, |r: &CandidateRow| r.agent_id); col!("region", UInt16, UInt16Array, |r: &CandidateRow| r.region); col!("target", UInt16, UInt16Array, |r: &CandidateRow| r.target);
    col!("mobility_eligible", Boolean, BooleanArray, |r: &CandidateRow| r.mobility_eligible); col!("hysteresis_kept", Boolean, BooleanArray, |r: &CandidateRow| r.hysteresis_kept); col!("became_best_at_iteration", Boolean, BooleanArray, |r: &CandidateRow| r.became_best);
    macro_rules! bits { ($field:ident) => { col!(concat!(stringify!($field), "_bits"), UInt32, UInt32Array, |r: &CandidateRow| r.$field.to_bits()); }; }
    bits!(own_score); bits!(own_ratio); bits!(target_ratio); bits!(roots); bits!(post_roots_pull); bits!(applied_pull); bits!(target_base_score); bits!(river); bits!(pre_news_score);
    for (i, name) in ["frontier", "wage", "chain", "urban", "learning"].iter().enumerate() {
        col!(&format!("gross_{name}_bits"), UInt32, UInt32Array, |r: &CandidateRow| r.gross[i].to_bits());
        col!(&format!("net_{name}_bits"), UInt32, UInt32Array, |r: &CandidateRow| r.net[i].to_bits());
    }
    batch(columns)
}

/// Stage 2 has a separate versioned header. Stage 1's three batches and
/// header schema remain unchanged, including its incomplete provenance flag.
pub fn move_header_batch(config: Option<&DeliveryConfig>, frame: Option<&DeliveryFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let empty = MoveFrame::default(); let moves = frame.map_or(&empty, |f| &f.moves); let c = &moves.counts;
    macro_rules! count { ($name:literal, $value:expr) => { (Field::new($name, DataType::UInt64, false), Arc::new(UInt64Array::from(vec![$value as u64])) as ArrayRef) }; }
    batch(vec![
        (Field::new("schema_version", DataType::UInt16, false), Arc::new(UInt16Array::from(vec![2u16]))),
        (Field::new("enabled", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![config.is_some()]))),
        (Field::new("source_turn", DataType::UInt32, true), Arc::new(UInt32Array::from(vec![frame.map(|f| f.source_turn)]))),
        (Field::new("active_ablation", DataType::UInt8, false), Arc::new(UInt8Array::from(vec![frame.map_or(0, |f| f.ablation)]))),
        (Field::new("selection_is_explicit", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![config.is_some_and(|c| c.selected_ids.is_some())]))),
        (Field::new("capture_finished", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![moves.finished]))),
        (Field::new("applied_move_provenance_complete", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![moves.complete()]))),
        (Field::new("counterfactual_marginals_computed", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![false]))),
        (Field::new("native_event_ordinals_are_zero_based", DataType::Boolean, false), Arc::new(BooleanArray::from(vec![true]))),
        count!("move_limit", config.map_or(0, |c| c.move_limit)),
        count!("selected_ids_requested", config.and_then(|c| c.selected_ids.as_ref()).map_or(0, Vec::len)),
        count!("operations_seen_all", c.operations_all), count!("operations_selected", c.operations_selected),
        count!("dropped_move_rows", c.dropped_rows), count!("tracking_admission_dropped", c.tracking_dropped),
        count!("tracked_origins_peak", c.tracked_peak), count!("missing_applied_origins", c.missing_applied_origins),
        count!("own_proposals_all", c.own_proposals_all), count!("replacement_removals_all", c.replacement_removals_all),
        count!("follower_writes_all", c.follower_writes_all), count!("cancelled_existing_all", c.cancelled_existing_all),
        count!("blocked_nonproposers_all", c.blocked_nonproposers_all), count!("dedup_drops_all", c.dedup_drops_all),
        count!("applied_all", c.applied_all), count!("applied_selected", c.applied_selected),
    ])
}

pub fn moves_batch(frame: Option<&DeliveryFrame>) -> Result<RecordBatch, arrow::error::ArrowError> {
    let rows = frame.map_or(&[][..], |f| f.moves.rows.as_slice()); let mut columns = Vec::new();
    macro_rules! col { ($name:expr, $dtype:ident, $array:ident, $nullable:expr, $value:expr) => { columns.push((Field::new($name, DataType::$dtype, $nullable), Arc::new($array::from(rows.iter().map($value).collect::<Vec<_>>())) as ArrayRef)); }; }
    col!("operation_ordinal", UInt64, UInt64Array, false, |r: &MoveRow| r.operation_ordinal);
    col!("operation", UInt8, UInt8Array, false, |r: &MoveRow| r.operation);
    col!("applied", Boolean, BooleanArray, false, |r: &MoveRow| r.operation == MOVE_APPLIED);
    col!("bucket", UInt16, UInt16Array, false, |r: &MoveRow| r.bucket);
    col!("agent_id", UInt32, UInt32Array, false, |r: &MoveRow| r.agent_id);
    col!("from_region", UInt16, UInt16Array, false, |r: &MoveRow| r.from);
    col!("to_region", UInt16, UInt16Array, false, |r: &MoveRow| r.to);
    col!("role", UInt8, UInt8Array, false, |r: &MoveRow| r.role);
    col!("lead_agent_id", UInt32, UInt32Array, true, |r: &MoveRow| r.lead_id);
    col!("trigger_agent_id", UInt32, UInt32Array, true, |r: &MoveRow| r.trigger_agent_id);
    col!("reason", UInt8, UInt8Array, false, |r: &MoveRow| r.reason);
    col!("rejected_to_region", UInt16, UInt16Array, true, |r: &MoveRow| r.rejected_to);
    col!("prior_count_valid", Boolean, BooleanArray, false, |r: &MoveRow| r.prior_count_valid);
    col!("prior_proposal_count", UInt64, UInt64Array, false, |r: &MoveRow| r.prior_count);
    col!("prior_from_region", UInt16, UInt16Array, true, |r: &MoveRow| r.prior_from);
    col!("prior_to_region", UInt16, UInt16Array, true, |r: &MoveRow| r.prior_to);
    col!("origin_valid", Boolean, BooleanArray, false, |r: &MoveRow| r.origin_valid);
    col!("origin_operation_ordinal", UInt64, UInt64Array, true, |r: &MoveRow| r.origin_operation_ordinal);
    col!("native_event_ordinal", UInt64, UInt64Array, true, |r: &MoveRow| r.native_event_ordinal);
    col!("migration_driver", UInt8, UInt8Array, true, |r: &MoveRow| r.migration_driver);
    batch(columns)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn decision_delivery_quotas_bound_the_combined_rows() {
        for regions in [1, 2, 3, 8, 32, 100] { for limit in [1, 2, 17, 4096, MAX_LIMIT] {
            assert_eq!((0..regions).map(|r| region_quota(limit, r, regions)).sum::<usize>(), limit);
        } }
    }
    #[test]
    fn decision_delivery_configuration_rejects_aliases_and_unbounded_inputs() {
        assert!(DeliveryConfig::new(0, 1, None).is_err());
        assert!(DeliveryConfig::new(1, MAX_LIMIT + 1, None).is_err());
        assert!(DeliveryConfig::new(1, 1, Some(vec![2, 1])).is_err());
        assert!(DeliveryConfig::new(1, 1, Some(vec![1, 1])).is_err());
        assert!(DeliveryConfig::new(1, 1, Some(vec![0, 1])).is_ok());
        assert_eq!(std::mem::size_of::<NoDelivery>(), 0);
    }
    #[test]
    fn decision_delivery_empty_frame_is_stamped_and_truncation_is_explicit() {
        let mut frame = DeliveryFrame::new(101, crate::scale::ABLATE_NEEDS);
        assert!(frame.stage_complete()); assert_eq!(frame.source_turn, 101);
        assert_eq!(decisions_batch(Some(&frame)).unwrap().num_rows(), 0);
        assert_eq!(candidates_batch(Some(&frame)).unwrap().num_rows(), 0);
        frame.counts.dropped_candidates = 1; assert!(!frame.stage_complete());
    }

    #[test]
    fn decision_delivery_computed_zero_anchor_is_distinct_from_absence() {
        let mut pool = AgentPool::new(1);
        let slot = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 25,
            0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        let config = DeliveryConfig::new(1, 1, None).unwrap();
        let mut observer = RegionDelivery::new(&config, 0, 1);
        observer.begin_agent(&pool, slot, 0);
        assert!(!observer.decisions[0].community_anchor_computed);
        observer.anchor(0.0);
        assert!(observer.decisions[0].community_anchor_computed);
        assert_eq!(observer.decisions[0].community_anchor.to_bits(), 0.0f32.to_bits());
    }

    fn move_pool() -> AgentPool {
        let mut pool = AgentPool::new(4);
        for _ in 0..3 { pool.spawn(0, 0, crate::agent::Occupation::Farmer, 25,
            0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE); }
        pool
    }

    #[test]
    fn decision_delivery_move_tracking_and_rows_are_bounded_independently() {
        let pool = move_pool();
        let config = DeliveryConfig::new(1, 1, None).unwrap().with_move_limit(1).unwrap();
        let mut decisions = crate::behavior::PendingDecisions::new();
        decisions.migrations = vec![(0, 0, 1), (1, 0, 1), (2, 0, 1)];
        let mut observer = MoveDelivery::new(&config);
        observer.begin(&pool, &[decisions]);
        assert_eq!(observer.origins.len(), 1);
        observer.applied(&pool, 0, (2, 0, 1), 7, 0);
        let frame = observer.finish();
        assert_eq!(frame.rows.len(), 1);
        assert_eq!(frame.counts.tracked_peak, 1);
        assert_eq!(frame.counts.tracking_dropped, 2);
        assert_eq!(frame.counts.dropped_rows, 3);
        assert_eq!(frame.counts.missing_applied_origins, 1);
        assert!(!frame.complete());
    }

    #[test]
    fn decision_delivery_move_missing_origin_never_invents_an_own_proposal() {
        let pool = move_pool();
        let config = DeliveryConfig::new(1, 1, None).unwrap();
        let mut observer = MoveDelivery::new(&config);
        observer.applied(&pool, 0, (0, 0, 1), 9, 2);
        let frame = observer.finish();
        let row = &frame.rows[0];
        assert_eq!(row.role, MOVE_ROLE_UNKNOWN);
        assert!(!row.origin_valid);
        assert_eq!(row.origin_operation_ordinal, None);
        assert_eq!(row.native_event_ordinal, Some(9));
        assert!(!frame.complete());
    }

    #[test]
    fn decision_delivery_move_empty_selection_and_dedup_keep_last_writer() {
        let pool = move_pool();
        let empty = DeliveryConfig::new(1, 1, Some(vec![])).unwrap();
        let mut observer = MoveDelivery::new(&empty);
        let mut decisions = crate::behavior::PendingDecisions::new();
        decisions.migrations.push((0, 0, 1));
        observer.begin(&pool, &[decisions]);
        observer.applied(&pool, 0, (0, 0, 1), 0, 0);
        let empty_frame = observer.finish();
        assert!(empty_frame.complete()); assert!(empty_frame.rows.is_empty());
        assert_eq!(empty_frame.counts.applied_all, 1);
        assert_eq!(empty_frame.counts.applied_selected, 0);

        let config = DeliveryConfig::new(1, 1, None).unwrap();
        let mut observer = MoveDelivery::new(&config);
        observer.follower_written(&pool, 0, 2, 0, 1, 0, MOVE_ROLE_DEPENDENT, 0, None);
        observer.follower_written(&pool, 0, 2, 0, 2, 1, MOVE_ROLE_DEPENDENT, 1, Some((0, 1)));
        observer.dedup_removed(&pool, 0, (2, 0, 1));
        observer.applied(&pool, 0, (2, 0, 2), 3, 1);
        let frame = observer.finish();
        let applied = frame.rows.last().unwrap();
        assert!(frame.complete() && applied.origin_valid);
        assert_eq!(applied.lead_id, Some(pool.ids[1]));
        assert_eq!(applied.origin_operation_ordinal, Some(1));
    }
}
