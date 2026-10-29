//! Bounded, transient observations at the decision boundary.
//!
//! Stage 1 describes pre-household decisions and admissible destinations, not
//! final applied moves or counterfactual winners. Floating-point observations
//! are exported as their original f32 bits. No simulation reads this module.

use std::sync::Arc;
use arrow::array::{ArrayRef, BooleanArray, UInt8Array, UInt16Array, UInt32Array, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use crate::{migration_drivers::{Mobility, VoluntaryPull}, needs::NeedUtilityTrace, pool::AgentPool};

pub const DEFAULT_AGENT_LIMIT: usize = 4096;
pub const DEFAULT_CANDIDATE_LIMIT: usize = 16384;
pub const MAX_LIMIT: usize = 65536;
pub const SCHEMA_VERSION: u16 = 1;
pub const STATUS_TRIP: u8 = 1;
pub const STATUS_EVALUATED: u8 = 2;

#[derive(Clone, Debug)]
pub struct DeliveryConfig {
    pub agent_limit: usize,
    pub candidate_limit: usize,
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
        Ok(Self { agent_limit, candidate_limit, selected_ids })
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
}
impl DeliveryFrame {
    pub fn new(source_turn: u32, ablation: u8) -> Self {
        Self { source_turn, ablation, counts: DeliveryCounts::default(), decisions: Vec::new(), candidates: Vec::new() }
    }
    pub(crate) fn merge_region(&mut self, mut region: RegionDelivery<'_>) {
        self.counts.merge(&region.counts);
        self.decisions.append(&mut region.decisions); self.candidates.append(&mut region.candidates);
    }
    pub fn stage_complete(&self) -> bool { self.counts.dropped_agents == 0 && self.counts.dropped_candidates == 0 }
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
}
