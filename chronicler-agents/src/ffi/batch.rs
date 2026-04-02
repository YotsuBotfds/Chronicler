//! RecordBatch building and parsing helpers for the FFI layer.
//!
//! Politics input parsing, result building, ecology batch construction,
//! event serialization, and shared utility types live here.

use std::sync::Arc;

use arrow::array::{UInt8Builder, UInt16Builder, UInt32Builder};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3_arrow::PyRecordBatch;

use crate::agent::PERSONALITY_LABEL_THRESHOLD;
use crate::region::RegionState;
use super::schema::*;

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
// M54c: Politics input parsing helpers
// ---------------------------------------------------------------------------

use crate::politics::{
    CivInput, RegionInput, PoliticsTopology, PoliticsConfig,
    RelationshipEntry, VassalEntry, FederationEntry, WarEntry,
    EmbargoEntry, ProxyWarEntry, ExileEntry,
    CivRef, FedRef, Disposition,
    PoliticsResult,
    CivOpType, RegionOpType, RelationshipOpType, FederationOpType,
    VassalOpType, ExileOpType, ProxyWarOpType,
    EffectRouting, BookkeepingType, BridgeTransitionType,
    CIV_NONE,
};

fn civref_to_pair(cr: &CivRef) -> (u8, u16) {
    match cr {
        CivRef::Existing(id) => (0, *id),
        CivRef::New(id) => (1, *id),
    }
}

fn fedref_to_pair(fr: &FedRef) -> (u8, u16) {
    match fr {
        FedRef::Existing(id) => (0, *id),
        FedRef::New(id) => (1, *id),
    }
}

fn disposition_to_u8(d: &Disposition) -> u8 {
    *d as u8
}

fn effect_routing_to_u8(r: &EffectRouting) -> u8 {
    match r {
        EffectRouting::Keep => 0,
        EffectRouting::Signal => 1,
        EffectRouting::GuardShock => 2,
        EffectRouting::DirectOnly => 3,
        EffectRouting::HybridShock => 4,
    }
}

fn bk_type_to_u8(t: &BookkeepingType) -> u8 {
    match t {
        BookkeepingType::AppendStatsHistory => 0,
        BookkeepingType::IncrementDecline => 1,
        BookkeepingType::ResetDecline => 2,
        BookkeepingType::IncrementEventCount => 3,
    }
}

fn bridge_type_to_u8(t: &BridgeTransitionType) -> u8 {
    match t {
        BridgeTransitionType::Secession => 0,
        BridgeTransitionType::Restoration => 1,
        BridgeTransitionType::Absorption => 2,
    }
}

fn civ_op_type_to_u8(t: &CivOpType) -> u8 {
    match t {
        CivOpType::CreateBreakaway => 0,
        CivOpType::Restore => 1,
        CivOpType::Absorb => 2,
        CivOpType::ReassignCapital => 3,
        CivOpType::StripToFirstRegion => 4,
    }
}

fn region_op_type_to_u8(t: &RegionOpType) -> u8 {
    match t {
        RegionOpType::SetController => 0,
        RegionOpType::NullifyController => 1,
        RegionOpType::SetSecededTransient => 2,
    }
}

fn rel_op_type_to_u8(t: &RelationshipOpType) -> u8 {
    match t {
        RelationshipOpType::InitPair => 0,
        RelationshipOpType::SetDisposition => 1,
        RelationshipOpType::ResetAlliedTurns => 2,
        RelationshipOpType::IncrementAlliedTurns => 3,
    }
}

fn fed_op_type_to_u8(t: &FederationOpType) -> u8 {
    match t {
        FederationOpType::Create => 0,
        FederationOpType::AppendMember => 1,
        FederationOpType::RemoveMember => 2,
        FederationOpType::Dissolve => 3,
    }
}

fn vassal_op_type_to_u8(t: &VassalOpType) -> u8 {
    match t {
        VassalOpType::Remove => 0,
    }
}

fn exile_op_type_to_u8(t: &ExileOpType) -> u8 {
    match t {
        ExileOpType::Append => 0,
        ExileOpType::Remove => 1,
    }
}

fn proxy_war_op_type_to_u8(t: &ProxyWarOpType) -> u8 {
    match t {
        ProxyWarOpType::SetDetected => 0,
    }
}

/// Parse civ input batch columns into `Vec<CivInput>`.
///
/// List columns (`stats_sum_history`, `regions_list`) are Arrow list<T> types.
pub(crate) fn parse_civ_input_batch(rb: &RecordBatch) -> Result<Vec<CivInput>, PyErr> {
    use arrow::array::{Array, UInt8Array, UInt16Array, Int32Array, Float32Array, ListArray, StringArray};

    let n = rb.num_rows();
    macro_rules! col {
        ($name:expr, $ty:ty) => {
            rb.column_by_name($name)
                .ok_or_else(|| PyValueError::new_err(format!("civ input missing column {}", $name)))?
                .as_any()
                .downcast_ref::<$ty>()
                .ok_or_else(|| PyValueError::new_err(format!("civ input column {} wrong type", $name)))?
        };
    }

    let civ_idx_col = col!("civ_idx", UInt16Array);
    let civ_name_col = col!("civ_name", StringArray);
    let stability_col = col!("stability", Int32Array);
    let military_col = col!("military", Int32Array);
    let economy_col = col!("economy", Int32Array);
    let culture_col = col!("culture", Int32Array);
    let treasury_col = col!("treasury", Int32Array);
    let asabiya_col = col!("asabiya", Float32Array);
    let population_col = col!("population", Int32Array);
    let decline_turns_col = col!("decline_turns", Int32Array);
    let founded_turn_col = col!("founded_turn", arrow::array::UInt32Array);
    let civ_stress_col = col!("civ_stress", Int32Array);
    let civ_majority_faith_col = col!("civ_majority_faith", UInt8Array);
    let active_focus_col = col!("active_focus", UInt8Array);
    let total_eff_cap_col = col!("total_effective_capacity", Int32Array);
    let capital_region_col = col!("capital_region", UInt16Array);
    let _num_regions_col = col!("num_regions", UInt16Array);
    let dominant_faction_col = col!("dominant_faction", UInt8Array);
    let secession_occurred_col = col!("secession_occurred_count", Int32Array);
    let capital_lost_col = col!("capital_lost_count", Int32Array);
    // List columns for packed data
    let ssh_list = col!("stats_sum_history", ListArray);
    let reg_list = col!("regions_list", ListArray);

    let mut civs = Vec::with_capacity(n);
    for i in 0..n {
        // Extract stats_sum_history list<int32>
        let ssh: Vec<i32> = if !ssh_list.is_null(i) {
            let arr = ssh_list.value(i);
            let int_arr = arr.as_any().downcast_ref::<Int32Array>()
                .ok_or_else(|| PyValueError::new_err("stats_sum_history inner not Int32"))?;
            (0..int_arr.len()).map(|j| int_arr.value(j)).collect()
        } else {
            Vec::new()
        };

        // Extract regions_list list<uint16>
        let regions: Vec<u16> = if !reg_list.is_null(i) {
            let arr = reg_list.value(i);
            let u16_arr = arr.as_any().downcast_ref::<UInt16Array>()
                .ok_or_else(|| PyValueError::new_err("regions_list inner not UInt16"))?;
            (0..u16_arr.len()).map(|j| u16_arr.value(j)).collect()
        } else {
            Vec::new()
        };

        let mut c = CivInput::new(civ_idx_col.value(i));
        c.name = civ_name_col.value(i).to_string();
        c.stability = stability_col.value(i);
        c.military = military_col.value(i);
        c.economy = economy_col.value(i);
        c.culture = culture_col.value(i);
        c.treasury = treasury_col.value(i);
        c.asabiya = asabiya_col.value(i);
        c.population = population_col.value(i);
        c.decline_turns = decline_turns_col.value(i);
        c.stats_sum_history = ssh;
        c.founded_turn = founded_turn_col.value(i);
        c.regions = regions;
        c.capital_region = capital_region_col.value(i);
        c.total_effective_capacity = total_eff_cap_col.value(i);
        c.active_focus = active_focus_col.value(i);
        c.civ_majority_faith = civ_majority_faith_col.value(i);
        c.civ_stress = civ_stress_col.value(i);
        c.dominant_faction = dominant_faction_col.value(i);
        c.secession_occurred_count = secession_occurred_col.value(i);
        c.capital_lost_count = capital_lost_col.value(i);
        civs.push(c);
    }
    Ok(civs)
}

/// Parse region input batch columns into `Vec<RegionInput>`.
///
/// Adjacency data uses Arrow list<uint16> column.
pub(crate) fn parse_region_input_batch(rb: &RecordBatch) -> Result<Vec<RegionInput>, PyErr> {
    use arrow::array::{Array, UInt8Array, UInt16Array, ListArray};

    let n = rb.num_rows();
    macro_rules! col {
        ($name:expr, $ty:ty) => {
            rb.column_by_name($name)
                .ok_or_else(|| PyValueError::new_err(format!("region input missing column {}", $name)))?
                .as_any()
                .downcast_ref::<$ty>()
                .ok_or_else(|| PyValueError::new_err(format!("region input column {} wrong type", $name)))?
        };
    }

    let region_idx_col = col!("region_idx", UInt16Array);
    let controller_col = col!("controller", UInt16Array);
    let capacity_col = col!("carrying_capacity", UInt16Array);
    let population_col = col!("population", UInt16Array);
    let majority_belief_col = col!("majority_belief", UInt8Array);
    let effective_capacity_col = col!("effective_capacity", UInt16Array);
    let adj_list = col!("adjacencies", ListArray);

    let mut regions = Vec::with_capacity(n);
    for i in 0..n {
        let adjs: Vec<u16> = if !adj_list.is_null(i) {
            let arr = adj_list.value(i);
            let u16_arr = arr.as_any().downcast_ref::<UInt16Array>()
                .ok_or_else(|| PyValueError::new_err("adjacencies inner not UInt16"))?;
            (0..u16_arr.len()).map(|j| u16_arr.value(j)).collect()
        } else {
            Vec::new()
        };

        let mut r = RegionInput::new(region_idx_col.value(i));
        r.controller = controller_col.value(i);
        r.adjacencies = adjs;
        r.carrying_capacity = capacity_col.value(i);
        r.population = population_col.value(i);
        r.majority_belief = majority_belief_col.value(i);
        r.effective_capacity = effective_capacity_col.value(i);
        regions.push(r);
    }
    Ok(regions)
}

/// Parse relationship, vassal, federation, war, embargo, proxy-war, exile batches
/// into a `PoliticsTopology`.
pub(crate) fn parse_topology_batches(
    rel_rb: &RecordBatch,
    vassal_rb: &RecordBatch,
    fed_rb: &RecordBatch,
    war_rb: &RecordBatch,
    embargo_rb: &RecordBatch,
    proxy_rb: &RecordBatch,
    exile_rb: &RecordBatch,
) -> Result<PoliticsTopology, PyErr> {
    use arrow::array::{Array, UInt8Array, UInt16Array, UInt32Array, Int32Array, BooleanArray, ListArray};

    macro_rules! col {
        ($rb:expr, $name:expr, $ty:ty) => {
            $rb.column_by_name($name)
                .ok_or_else(|| PyValueError::new_err(format!("topology missing column {}", $name)))?
                .as_any()
                .downcast_ref::<$ty>()
                .ok_or_else(|| PyValueError::new_err(format!("topology column {} wrong type", $name)))?
        };
    }

    // Relationships
    let mut relationships = Vec::with_capacity(rel_rb.num_rows());
    if rel_rb.num_rows() > 0 {
        let rel_a = col!(rel_rb, "civ_a", UInt16Array);
        let rel_b = col!(rel_rb, "civ_b", UInt16Array);
        let rel_disp = col!(rel_rb, "disposition", UInt8Array);
        let rel_allied = col!(rel_rb, "allied_turns", Int32Array);
        for i in 0..rel_rb.num_rows() {
            relationships.push(RelationshipEntry {
                civ_a: rel_a.value(i),
                civ_b: rel_b.value(i),
                disposition: Disposition::from_u8(rel_disp.value(i)).unwrap_or(Disposition::Neutral),
                allied_turns: rel_allied.value(i),
            });
        }
    }

    // Vassals
    let mut vassals = Vec::with_capacity(vassal_rb.num_rows());
    if vassal_rb.num_rows() > 0 {
        let v_vassal = col!(vassal_rb, "vassal", UInt16Array);
        let v_overlord = col!(vassal_rb, "overlord", UInt16Array);
        for i in 0..vassal_rb.num_rows() {
            vassals.push(VassalEntry {
                vassal: v_vassal.value(i),
                overlord: v_overlord.value(i),
            });
        }
    }

    // Federations — uses list<uint16> for members
    let mut federations = Vec::new();
    if fed_rb.num_rows() > 0 {
        let f_idx = col!(fed_rb, "federation_idx", UInt16Array);
        let f_turn = col!(fed_rb, "founded_turn", UInt32Array);
        let f_members = col!(fed_rb, "members", ListArray);
        for i in 0..fed_rb.num_rows() {
            let members: Vec<u16> = if !f_members.is_null(i) {
                let arr = f_members.value(i);
                let u16_arr = arr.as_any().downcast_ref::<UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err("federation members inner not UInt16"))?;
                (0..u16_arr.len()).map(|j| u16_arr.value(j)).collect()
            } else {
                Vec::new()
            };
            federations.push(FederationEntry {
                fed_idx: f_idx.value(i),
                members,
                founded_turn: f_turn.value(i),
            });
        }
    }

    // Wars
    let mut wars = Vec::with_capacity(war_rb.num_rows());
    if war_rb.num_rows() > 0 {
        let w_a = col!(war_rb, "civ_a", UInt16Array);
        let w_b = col!(war_rb, "civ_b", UInt16Array);
        for i in 0..war_rb.num_rows() {
            wars.push(WarEntry { civ_a: w_a.value(i), civ_b: w_b.value(i) });
        }
    }

    // Embargoes
    let mut embargoes = Vec::with_capacity(embargo_rb.num_rows());
    if embargo_rb.num_rows() > 0 {
        let e_a = col!(embargo_rb, "civ_a", UInt16Array);
        let e_b = col!(embargo_rb, "civ_b", UInt16Array);
        for i in 0..embargo_rb.num_rows() {
            embargoes.push(EmbargoEntry { civ_a: e_a.value(i), civ_b: e_b.value(i) });
        }
    }

    // Proxy wars
    let mut proxy_wars = Vec::with_capacity(proxy_rb.num_rows());
    if proxy_rb.num_rows() > 0 {
        let p_sponsor = col!(proxy_rb, "sponsor", UInt16Array);
        let p_target_civ = col!(proxy_rb, "target_civ", UInt16Array);
        let p_target_region = col!(proxy_rb, "target_region", UInt16Array);
        let p_detected = col!(proxy_rb, "detected", BooleanArray);
        for i in 0..proxy_rb.num_rows() {
            proxy_wars.push(ProxyWarEntry {
                sponsor: p_sponsor.value(i),
                target_civ: p_target_civ.value(i),
                target_region: p_target_region.value(i),
                detected: p_detected.value(i),
            });
        }
    }

    // Exiles — uses list<uint16> for conquered_regions and recognized_by
    let mut exiles = Vec::new();
    if exile_rb.num_rows() > 0 {
        let ex_orig = col!(exile_rb, "original_civ", UInt16Array);
        let ex_abs = col!(exile_rb, "absorber_civ", UInt16Array);
        let ex_turns = col!(exile_rb, "turns_remaining", Int32Array);
        let ex_regions = col!(exile_rb, "conquered_regions", ListArray);
        let ex_recognized = col!(exile_rb, "recognized_by", ListArray);
        for i in 0..exile_rb.num_rows() {
            let conquered: Vec<u16> = if !ex_regions.is_null(i) {
                let arr = ex_regions.value(i);
                let u16_arr = arr.as_any().downcast_ref::<UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err("exile regions inner not UInt16"))?;
                (0..u16_arr.len()).map(|j| u16_arr.value(j)).collect()
            } else { Vec::new() };

            let recognized: Vec<u16> = if !ex_recognized.is_null(i) {
                let arr = ex_recognized.value(i);
                let u16_arr = arr.as_any().downcast_ref::<UInt16Array>()
                    .ok_or_else(|| PyValueError::new_err("exile recognized inner not UInt16"))?;
                (0..u16_arr.len()).map(|j| u16_arr.value(j)).collect()
            } else { Vec::new() };

            exiles.push(ExileEntry {
                original_civ: ex_orig.value(i),
                absorber_civ: ex_abs.value(i),
                conquered_regions: conquered,
                turns_remaining: ex_turns.value(i),
                recognized_by: recognized,
            });
        }
    }

    Ok(PoliticsTopology { relationships, vassals, federations, wars, embargoes, proxy_wars, exiles })
}

/// Convert a `PoliticsResult` into the 12-tuple of Arrow RecordBatches.
#[allow(clippy::type_complexity)]
pub(crate) fn build_politics_result_batches(
    result: &PoliticsResult,
) -> Result<(RecordBatch, RecordBatch, RecordBatch, RecordBatch,
             RecordBatch, RecordBatch, RecordBatch, RecordBatch,
             RecordBatch, RecordBatch, RecordBatch, RecordBatch), ArrowError> {
    use arrow::array::{
        UInt8Builder, UInt16Builder, UInt32Builder, UInt64Builder,
        Int32Builder, Float32Builder, StringBuilder, BooleanBuilder, ListBuilder,
    };

    // 1. Civ ops
    let n = result.civ_ops.len();
    let mut co_step = UInt8Builder::with_capacity(n);
    let mut co_seq = UInt16Builder::with_capacity(n);
    let mut co_type = UInt8Builder::with_capacity(n);
    let mut co_src_kind = UInt8Builder::with_capacity(n);
    let mut co_src_id = UInt16Builder::with_capacity(n);
    let mut co_tgt_kind = UInt8Builder::with_capacity(n);
    let mut co_tgt_id = UInt16Builder::with_capacity(n);
    let mut co_regions = ListBuilder::new(UInt16Builder::new());
    let mut co_mil = Int32Builder::with_capacity(n);
    let mut co_eco = Int32Builder::with_capacity(n);
    let mut co_cul = Int32Builder::with_capacity(n);
    let mut co_stab = Int32Builder::with_capacity(n);
    let mut co_tre = Int32Builder::with_capacity(n);
    let mut co_pop = Int32Builder::with_capacity(n);
    let mut co_asa = Float32Builder::with_capacity(n);
    let mut co_ft = UInt32Builder::with_capacity(n);

    for op in &result.civ_ops {
        co_step.append_value(op.step);
        co_seq.append_value(op.seq);
        co_type.append_value(civ_op_type_to_u8(&op.op_type));
        let (sk, si) = civref_to_pair(&op.source_civ);
        co_src_kind.append_value(sk);
        co_src_id.append_value(si);
        let (tk, ti) = civref_to_pair(&op.target_civ);
        co_tgt_kind.append_value(tk);
        co_tgt_id.append_value(ti);
        for &region in &op.regions {
            co_regions.values().append_value(region);
        }
        co_regions.append(true);
        co_mil.append_value(op.stat_military);
        co_eco.append_value(op.stat_economy);
        co_cul.append_value(op.stat_culture);
        co_stab.append_value(op.stat_stability);
        co_tre.append_value(op.stat_treasury);
        co_pop.append_value(op.stat_population);
        co_asa.append_value(op.stat_asabiya);
        co_ft.append_value(op.founded_turn);
    }

    let civ_ops_batch = RecordBatch::try_new(
        Arc::new(politics_civ_ops_schema()),
        vec![
            Arc::new(co_step.finish()) as _, Arc::new(co_seq.finish()) as _,
            Arc::new(co_type.finish()) as _,
            Arc::new(co_src_kind.finish()) as _, Arc::new(co_src_id.finish()) as _,
            Arc::new(co_tgt_kind.finish()) as _, Arc::new(co_tgt_id.finish()) as _,
            Arc::new(co_regions.finish()) as _,
            Arc::new(co_mil.finish()) as _, Arc::new(co_eco.finish()) as _,
            Arc::new(co_cul.finish()) as _, Arc::new(co_stab.finish()) as _,
            Arc::new(co_tre.finish()) as _, Arc::new(co_pop.finish()) as _,
            Arc::new(co_asa.finish()) as _, Arc::new(co_ft.finish()) as _,
        ],
    )?;

    // 2. Region ops
    let n = result.region_ops.len();
    let mut ro_step = UInt8Builder::with_capacity(n);
    let mut ro_seq = UInt16Builder::with_capacity(n);
    let mut ro_type = UInt8Builder::with_capacity(n);
    let mut ro_region = UInt16Builder::with_capacity(n);
    let mut ro_ck = UInt8Builder::with_capacity(n);
    let mut ro_ci = UInt16Builder::with_capacity(n);

    for op in &result.region_ops {
        ro_step.append_value(op.step);
        ro_seq.append_value(op.seq);
        ro_type.append_value(region_op_type_to_u8(&op.op_type));
        ro_region.append_value(op.region);
        let (ck, ci) = civref_to_pair(&op.controller);
        ro_ck.append_value(ck);
        ro_ci.append_value(ci);
    }

    let region_ops_batch = RecordBatch::try_new(
        Arc::new(politics_region_ops_schema()),
        vec![
            Arc::new(ro_step.finish()) as _, Arc::new(ro_seq.finish()) as _,
            Arc::new(ro_type.finish()) as _,
            Arc::new(ro_region.finish()) as _,
            Arc::new(ro_ck.finish()) as _, Arc::new(ro_ci.finish()) as _,
        ],
    )?;

    // 3. Relationship ops
    let n = result.relationship_ops.len();
    let mut rl_step = UInt8Builder::with_capacity(n);
    let mut rl_seq = UInt16Builder::with_capacity(n);
    let mut rl_type = UInt8Builder::with_capacity(n);
    let mut rl_ak = UInt8Builder::with_capacity(n);
    let mut rl_ai = UInt16Builder::with_capacity(n);
    let mut rl_bk = UInt8Builder::with_capacity(n);
    let mut rl_bi = UInt16Builder::with_capacity(n);
    let mut rl_disp = UInt8Builder::with_capacity(n);

    for op in &result.relationship_ops {
        rl_step.append_value(op.step);
        rl_seq.append_value(op.seq);
        rl_type.append_value(rel_op_type_to_u8(&op.op_type));
        let (ak, ai) = civref_to_pair(&op.civ_a);
        rl_ak.append_value(ak);
        rl_ai.append_value(ai);
        let (bk, bi) = civref_to_pair(&op.civ_b);
        rl_bk.append_value(bk);
        rl_bi.append_value(bi);
        rl_disp.append_value(disposition_to_u8(&op.disposition));
    }

    let rel_ops_batch = RecordBatch::try_new(
        Arc::new(politics_relationship_ops_schema()),
        vec![
            Arc::new(rl_step.finish()) as _, Arc::new(rl_seq.finish()) as _,
            Arc::new(rl_type.finish()) as _,
            Arc::new(rl_ak.finish()) as _, Arc::new(rl_ai.finish()) as _,
            Arc::new(rl_bk.finish()) as _, Arc::new(rl_bi.finish()) as _,
            Arc::new(rl_disp.finish()) as _,
        ],
    )?;

    // 4. Federation ops
    let n = result.federation_ops.len();
    let mut fo_step = UInt8Builder::with_capacity(n);
    let mut fo_seq = UInt16Builder::with_capacity(n);
    let mut fo_type = UInt8Builder::with_capacity(n);
    let mut fo_fk = UInt8Builder::with_capacity(n);
    let mut fo_fi = UInt16Builder::with_capacity(n);
    let mut fo_ck = UInt8Builder::with_capacity(n);
    let mut fo_ci = UInt16Builder::with_capacity(n);
    let mut fo_mc = UInt16Builder::with_capacity(n);
    let mut fo_m0k = UInt8Builder::with_capacity(n);
    let mut fo_m0i = UInt16Builder::with_capacity(n);
    let mut fo_m1k = UInt8Builder::with_capacity(n);
    let mut fo_m1i = UInt16Builder::with_capacity(n);
    let mut fo_cs = UInt64Builder::with_capacity(n);

    for op in &result.federation_ops {
        fo_step.append_value(op.step);
        fo_seq.append_value(op.seq);
        fo_type.append_value(fed_op_type_to_u8(&op.op_type));
        let (fk, fi) = fedref_to_pair(&op.federation_ref);
        fo_fk.append_value(fk);
        fo_fi.append_value(fi);
        let (ck, ci) = civref_to_pair(&op.civ);
        fo_ck.append_value(ck);
        fo_ci.append_value(ci);
        fo_mc.append_value(op.members.len() as u16);
        let m0 = op.members.first().copied().unwrap_or(CivRef::Existing(CIV_NONE));
        let m1 = op.members.get(1).copied().unwrap_or(CivRef::Existing(CIV_NONE));
        let (m0k, m0i) = civref_to_pair(&m0);
        let (m1k, m1i) = civref_to_pair(&m1);
        fo_m0k.append_value(m0k);
        fo_m0i.append_value(m0i);
        fo_m1k.append_value(m1k);
        fo_m1i.append_value(m1i);
        fo_cs.append_value(op.context_seed);
    }

    let fed_ops_batch = RecordBatch::try_new(
        Arc::new(politics_federation_ops_schema()),
        vec![
            Arc::new(fo_step.finish()) as _, Arc::new(fo_seq.finish()) as _,
            Arc::new(fo_type.finish()) as _,
            Arc::new(fo_fk.finish()) as _, Arc::new(fo_fi.finish()) as _,
            Arc::new(fo_ck.finish()) as _, Arc::new(fo_ci.finish()) as _,
            Arc::new(fo_mc.finish()) as _,
            Arc::new(fo_m0k.finish()) as _, Arc::new(fo_m0i.finish()) as _,
            Arc::new(fo_m1k.finish()) as _, Arc::new(fo_m1i.finish()) as _,
            Arc::new(fo_cs.finish()) as _,
        ],
    )?;

    // 5. Vassal ops
    let n = result.vassal_ops.len();
    let mut vo_step = UInt8Builder::with_capacity(n);
    let mut vo_seq = UInt16Builder::with_capacity(n);
    let mut vo_type = UInt8Builder::with_capacity(n);
    let mut vo_vk = UInt8Builder::with_capacity(n);
    let mut vo_vi = UInt16Builder::with_capacity(n);
    let mut vo_ok = UInt8Builder::with_capacity(n);
    let mut vo_oi = UInt16Builder::with_capacity(n);

    for op in &result.vassal_ops {
        vo_step.append_value(op.step);
        vo_seq.append_value(op.seq);
        vo_type.append_value(vassal_op_type_to_u8(&op.op_type));
        let (vk, vi) = civref_to_pair(&op.vassal);
        vo_vk.append_value(vk);
        vo_vi.append_value(vi);
        let (ok, oi) = civref_to_pair(&op.overlord);
        vo_ok.append_value(ok);
        vo_oi.append_value(oi);
    }

    let vassal_ops_batch = RecordBatch::try_new(
        Arc::new(politics_vassal_ops_schema()),
        vec![
            Arc::new(vo_step.finish()) as _, Arc::new(vo_seq.finish()) as _,
            Arc::new(vo_type.finish()) as _,
            Arc::new(vo_vk.finish()) as _, Arc::new(vo_vi.finish()) as _,
            Arc::new(vo_ok.finish()) as _, Arc::new(vo_oi.finish()) as _,
        ],
    )?;

    // 6. Exile ops
    let n = result.exile_ops.len();
    let mut eo_step = UInt8Builder::with_capacity(n);
    let mut eo_seq = UInt16Builder::with_capacity(n);
    let mut eo_type = UInt8Builder::with_capacity(n);
    let mut eo_ok = UInt8Builder::with_capacity(n);
    let mut eo_oi = UInt16Builder::with_capacity(n);
    let mut eo_ak = UInt8Builder::with_capacity(n);
    let mut eo_ai = UInt16Builder::with_capacity(n);
    let mut eo_regions = ListBuilder::new(UInt16Builder::new());
    let mut eo_tr = Int32Builder::with_capacity(n);

    for op in &result.exile_ops {
        eo_step.append_value(op.step);
        eo_seq.append_value(op.seq);
        eo_type.append_value(exile_op_type_to_u8(&op.op_type));
        let (ok, oi) = civref_to_pair(&op.original_civ);
        eo_ok.append_value(ok);
        eo_oi.append_value(oi);
        let (ak, ai) = civref_to_pair(&op.absorber_civ);
        eo_ak.append_value(ak);
        eo_ai.append_value(ai);
        for &region in &op.conquered_regions {
            eo_regions.values().append_value(region);
        }
        eo_regions.append(true);
        eo_tr.append_value(op.turns_remaining);
    }

    let exile_ops_batch = RecordBatch::try_new(
        Arc::new(politics_exile_ops_schema()),
        vec![
            Arc::new(eo_step.finish()) as _, Arc::new(eo_seq.finish()) as _,
            Arc::new(eo_type.finish()) as _,
            Arc::new(eo_ok.finish()) as _, Arc::new(eo_oi.finish()) as _,
            Arc::new(eo_ak.finish()) as _, Arc::new(eo_ai.finish()) as _,
            Arc::new(eo_regions.finish()) as _,
            Arc::new(eo_tr.finish()) as _,
        ],
    )?;

    // 7. Proxy war ops
    let n = result.proxy_war_ops.len();
    let mut pw_step = UInt8Builder::with_capacity(n);
    let mut pw_seq = UInt16Builder::with_capacity(n);
    let mut pw_type = UInt8Builder::with_capacity(n);
    let mut pw_sk = UInt8Builder::with_capacity(n);
    let mut pw_si = UInt16Builder::with_capacity(n);
    let mut pw_tk = UInt8Builder::with_capacity(n);
    let mut pw_ti = UInt16Builder::with_capacity(n);
    let mut pw_tr = UInt16Builder::with_capacity(n);

    for op in &result.proxy_war_ops {
        pw_step.append_value(op.step);
        pw_seq.append_value(op.seq);
        pw_type.append_value(proxy_war_op_type_to_u8(&op.op_type));
        let (sk, si) = civref_to_pair(&op.sponsor);
        pw_sk.append_value(sk);
        pw_si.append_value(si);
        let (tk, ti) = civref_to_pair(&op.target_civ);
        pw_tk.append_value(tk);
        pw_ti.append_value(ti);
        pw_tr.append_value(op.target_region);
    }

    let proxy_ops_batch = RecordBatch::try_new(
        Arc::new(politics_proxy_war_ops_schema()),
        vec![
            Arc::new(pw_step.finish()) as _, Arc::new(pw_seq.finish()) as _,
            Arc::new(pw_type.finish()) as _,
            Arc::new(pw_sk.finish()) as _, Arc::new(pw_si.finish()) as _,
            Arc::new(pw_tk.finish()) as _, Arc::new(pw_ti.finish()) as _,
            Arc::new(pw_tr.finish()) as _,
        ],
    )?;

    // 8. Civ effect ops
    let n = result.civ_effects.len();
    let mut ce_step = UInt8Builder::with_capacity(n);
    let mut ce_seq = UInt16Builder::with_capacity(n);
    let mut ce_ck = UInt8Builder::with_capacity(n);
    let mut ce_ci = UInt16Builder::with_capacity(n);
    let mut ce_field = StringBuilder::with_capacity(n, n * 12);
    let mut ce_delta = Float32Builder::with_capacity(n);
    let mut ce_routing = UInt8Builder::with_capacity(n);

    for op in &result.civ_effects {
        ce_step.append_value(op.step);
        ce_seq.append_value(op.seq);
        let (ck, ci) = civref_to_pair(&op.civ);
        ce_ck.append_value(ck);
        ce_ci.append_value(ci);
        ce_field.append_value(op.field);
        // Use delta_f if non-zero, else delta_i as float
        let delta = if op.delta_f.abs() > f32::EPSILON { op.delta_f } else { op.delta_i as f32 };
        ce_delta.append_value(delta);
        ce_routing.append_value(effect_routing_to_u8(&op.routing));
    }

    let civ_effect_batch = RecordBatch::try_new(
        Arc::new(politics_civ_effect_ops_schema()),
        vec![
            Arc::new(ce_step.finish()) as _, Arc::new(ce_seq.finish()) as _,
            Arc::new(ce_ck.finish()) as _, Arc::new(ce_ci.finish()) as _,
            Arc::new(ce_field.finish()) as _,
            Arc::new(ce_delta.finish()) as _,
            Arc::new(ce_routing.finish()) as _,
        ],
    )?;

    // 9. Bookkeeping
    let n = result.bookkeeping.len();
    let mut bk_step = UInt8Builder::with_capacity(n);
    let mut bk_seq = UInt16Builder::with_capacity(n);
    let mut bk_ck = UInt8Builder::with_capacity(n);
    let mut bk_ci = UInt16Builder::with_capacity(n);
    let mut bk_type = UInt8Builder::with_capacity(n);
    let mut bk_value = Int32Builder::with_capacity(n);
    let mut bk_key = StringBuilder::with_capacity(n, n * 20);

    for op in &result.bookkeeping {
        bk_step.append_value(op.step);
        bk_seq.append_value(op.seq);
        let (ck, ci) = civref_to_pair(&op.civ);
        bk_ck.append_value(ck);
        bk_ci.append_value(ci);
        bk_type.append_value(bk_type_to_u8(&op.bk_type));
        bk_value.append_value(op.value_i);
        bk_key.append_value(op.field);
    }

    let bookkeeping_batch = RecordBatch::try_new(
        Arc::new(politics_bookkeeping_schema()),
        vec![
            Arc::new(bk_step.finish()) as _, Arc::new(bk_seq.finish()) as _,
            Arc::new(bk_ck.finish()) as _, Arc::new(bk_ci.finish()) as _,
            Arc::new(bk_type.finish()) as _,
            Arc::new(bk_value.finish()) as _,
            Arc::new(bk_key.finish()) as _,
        ],
    )?;

    // 10. Artifact intents
    let n = result.artifact_intents.len();
    let mut ai_step = UInt8Builder::with_capacity(n);
    let mut ai_seq = UInt16Builder::with_capacity(n);
    let mut ai_lk = UInt8Builder::with_capacity(n);
    let mut ai_li = UInt16Builder::with_capacity(n);
    let mut ai_gk = UInt8Builder::with_capacity(n);
    let mut ai_gi = UInt16Builder::with_capacity(n);
    let mut ai_region = UInt16Builder::with_capacity(n);
    let mut ai_cap = BooleanBuilder::with_capacity(n);
    let mut ai_dest = BooleanBuilder::with_capacity(n);
    let mut ai_action = StringBuilder::with_capacity(n, n * 24);

    for op in &result.artifact_intents {
        ai_step.append_value(op.step);
        ai_seq.append_value(op.seq);
        let (lk, li) = civref_to_pair(&op.losing_civ);
        ai_lk.append_value(lk);
        ai_li.append_value(li);
        let (gk, gi) = civref_to_pair(&op.gaining_civ);
        ai_gk.append_value(gk);
        ai_gi.append_value(gi);
        ai_region.append_value(op.region);
        ai_cap.append_value(op.is_capital);
        ai_dest.append_value(op.is_destructive);
        ai_action.append_value(op.action);
    }

    let artifact_batch = RecordBatch::try_new(
        Arc::new(politics_artifact_intent_schema()),
        vec![
            Arc::new(ai_step.finish()) as _, Arc::new(ai_seq.finish()) as _,
            Arc::new(ai_lk.finish()) as _, Arc::new(ai_li.finish()) as _,
            Arc::new(ai_gk.finish()) as _, Arc::new(ai_gi.finish()) as _,
            Arc::new(ai_region.finish()) as _,
            Arc::new(ai_cap.finish()) as _, Arc::new(ai_dest.finish()) as _,
            Arc::new(ai_action.finish()) as _,
        ],
    )?;

    // 11. Bridge transitions
    let n = result.bridge_transitions.len();
    let mut bt_step = UInt8Builder::with_capacity(n);
    let mut bt_seq = UInt16Builder::with_capacity(n);
    let mut bt_type = UInt8Builder::with_capacity(n);
    let mut bt_sk = UInt8Builder::with_capacity(n);
    let mut bt_si = UInt16Builder::with_capacity(n);
    let mut bt_tk = UInt8Builder::with_capacity(n);
    let mut bt_ti = UInt16Builder::with_capacity(n);
    let mut bt_regions = ListBuilder::new(UInt16Builder::new());

    for op in &result.bridge_transitions {
        bt_step.append_value(op.step);
        bt_seq.append_value(op.seq);
        bt_type.append_value(bridge_type_to_u8(&op.transition_type));
        let (sk, si) = civref_to_pair(&op.source_civ);
        bt_sk.append_value(sk);
        bt_si.append_value(si);
        let (tk, ti) = civref_to_pair(&op.target_civ);
        bt_tk.append_value(tk);
        bt_ti.append_value(ti);
        for &region in &op.regions {
            bt_regions.values().append_value(region);
        }
        bt_regions.append(true);
    }

    let bridge_batch = RecordBatch::try_new(
        Arc::new(politics_bridge_transition_schema()),
        vec![
            Arc::new(bt_step.finish()) as _, Arc::new(bt_seq.finish()) as _,
            Arc::new(bt_type.finish()) as _,
            Arc::new(bt_sk.finish()) as _, Arc::new(bt_si.finish()) as _,
            Arc::new(bt_tk.finish()) as _, Arc::new(bt_ti.finish()) as _,
            Arc::new(bt_regions.finish()) as _,
        ],
    )?;

    // 12. Event triggers
    let n = result.events.len();
    let mut et_step = UInt8Builder::with_capacity(n);
    let mut et_seq = UInt16Builder::with_capacity(n);
    let mut et_type = StringBuilder::with_capacity(n, n * 24);
    let mut et_ac = UInt8Builder::with_capacity(n);
    let mut et_a0k = UInt8Builder::with_capacity(n);
    let mut et_a0i = UInt16Builder::with_capacity(n);
    let mut et_a1k = UInt8Builder::with_capacity(n);
    let mut et_a1i = UInt16Builder::with_capacity(n);
    let mut et_imp = UInt8Builder::with_capacity(n);
    let mut et_cs = UInt64Builder::with_capacity(n);

    for ev in &result.events {
        et_step.append_value(ev.step);
        et_seq.append_value(ev.seq);
        et_type.append_value(ev.event_type);
        et_ac.append_value(ev.actors.len() as u8);
        if let Some(a0) = ev.actors.first() {
            let (k, i) = civref_to_pair(a0);
            et_a0k.append_value(k);
            et_a0i.append_value(i);
        } else {
            et_a0k.append_value(0);
            et_a0i.append_value(CIV_NONE);
        }
        if let Some(a1) = ev.actors.get(1) {
            let (k, i) = civref_to_pair(a1);
            et_a1k.append_value(k);
            et_a1i.append_value(i);
        } else {
            et_a1k.append_value(0);
            et_a1i.append_value(CIV_NONE);
        }
        et_imp.append_value(ev.importance);
        et_cs.append_value(ev.context_seed);
    }

    let event_batch = RecordBatch::try_new(
        Arc::new(politics_event_trigger_schema()),
        vec![
            Arc::new(et_step.finish()) as _, Arc::new(et_seq.finish()) as _,
            Arc::new(et_type.finish()) as _,
            Arc::new(et_ac.finish()) as _,
            Arc::new(et_a0k.finish()) as _, Arc::new(et_a0i.finish()) as _,
            Arc::new(et_a1k.finish()) as _, Arc::new(et_a1i.finish()) as _,
            Arc::new(et_imp.finish()) as _,
            Arc::new(et_cs.finish()) as _,
        ],
    )?;

    Ok((civ_ops_batch, region_ops_batch, rel_ops_batch, fed_ops_batch,
        vassal_ops_batch, exile_ops_batch, proxy_ops_batch, civ_effect_batch,
        bookkeeping_batch, artifact_batch, bridge_batch, event_batch))
}

/// Shared implementation of tick_politics for both AgentSimulator and PoliticsSimulator.
#[allow(clippy::type_complexity)]
pub(crate) fn tick_politics_impl(
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
    config: &PoliticsConfig,
) -> PyResult<(PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch,
               PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch,
               PyRecordBatch, PyRecordBatch, PyRecordBatch, PyRecordBatch)> {
    let civ_rb: RecordBatch = civ_batch.into_inner();
    let region_rb: RecordBatch = region_batch.into_inner();
    let rel_rb: RecordBatch = relationship_batch.into_inner();
    let vas_rb: RecordBatch = vassal_batch.into_inner();
    let fed_rb: RecordBatch = federation_batch.into_inner();
    let war_rb: RecordBatch = war_batch.into_inner();
    let emb_rb: RecordBatch = embargo_batch.into_inner();
    let prx_rb: RecordBatch = proxy_war_batch.into_inner();
    let exl_rb: RecordBatch = exile_batch.into_inner();

    let civs = parse_civ_input_batch(&civ_rb)?;
    let regions = parse_region_input_batch(&region_rb)?;
    let topology = parse_topology_batches(&rel_rb, &vas_rb, &fed_rb, &war_rb, &emb_rb, &prx_rb, &exl_rb)?;

    let result = crate::politics::run_politics_pass(&civs, &regions, &topology, config, turn, seed, hybrid_mode);

    let (b0, b1, b2, b3, b4, b5, b6, b7, b8, b9, b10, b11) =
        build_politics_result_batches(&result).map_err(arrow_err)?;

    Ok((
        PyRecordBatch::new(b0), PyRecordBatch::new(b1), PyRecordBatch::new(b2),
        PyRecordBatch::new(b3), PyRecordBatch::new(b4), PyRecordBatch::new(b5),
        PyRecordBatch::new(b6), PyRecordBatch::new(b7), PyRecordBatch::new(b8),
        PyRecordBatch::new(b9), PyRecordBatch::new(b10), PyRecordBatch::new(b11),
    ))
}
// ---------------------------------------------------------------------------
// Recompute context (shared between AgentSimulator and EcologySimulator)
// ---------------------------------------------------------------------------

/// Minimal context stored by `tick_ecology()` for use by `apply_region_postpass_patch()`.
/// Avoids widening the patch schema with season/climate columns.
#[derive(Clone, Debug, Default)]
pub(crate) struct RecomputeContext {
    pub(crate) turn: u32,
    pub(crate) climate_phase: u8,
    pub(crate) season_id: u8,
    pub(crate) valid: bool,
}

// ---------------------------------------------------------------------------
// Shared ecology helpers (used by both AgentSimulator and EcologySimulator)
// ---------------------------------------------------------------------------

/// Build region-state and ecology-event Arrow RecordBatches from ecology tick results.
pub(crate) fn build_ecology_batches(
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
pub(crate) fn apply_patch_to_regions(
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
pub(crate) fn recompute_region_yields(
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
// Event serialization
// ---------------------------------------------------------------------------

/// Convert a slice of AgentEvents into an Arrow RecordBatch using events_schema().
pub(crate) fn events_to_batch(events: &[crate::tick::AgentEvent]) -> Result<RecordBatch, ArrowError> {
    let n = events.len();
    let mut agent_ids = UInt32Builder::with_capacity(n);
    let mut event_types = UInt8Builder::with_capacity(n);
    let mut regions = UInt16Builder::with_capacity(n);
    let mut target_regions = UInt16Builder::with_capacity(n);
    let mut civ_affinities = UInt16Builder::with_capacity(n);
    let mut occupations = UInt8Builder::with_capacity(n);
    let mut beliefs = UInt8Builder::with_capacity(n);
    let mut turns = UInt32Builder::with_capacity(n);

    for e in events {
        agent_ids.append_value(e.agent_id);
        event_types.append_value(e.event_type);
        regions.append_value(e.region);
        target_regions.append_value(e.target_region);
        civ_affinities.append_value(e.civ_affinity as u16);
        occupations.append_value(e.occupation);
        beliefs.append_value(e.belief);
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
            Arc::new(beliefs.finish()) as _,
            Arc::new(turns.finish()) as _,
        ],
    )
}
