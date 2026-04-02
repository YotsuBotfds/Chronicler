//! Centralized Arrow schema definitions for the FFI layer.
//!
//! Every schema used by the three simulators (Agent, Ecology, Politics)
//! lives here. Defined once, imported everywhere.

use std::sync::Arc;

use arrow::datatypes::{DataType, Field, Schema};

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
        Field::new("parent_id_0", DataType::UInt32, false),
        Field::new("parent_id_1", DataType::UInt32, false),
        Field::new("wealth", DataType::Float32, false),
        Field::new("x", DataType::Float32, false),
        Field::new("y", DataType::Float32, false),
        Field::new("settlement_id", DataType::UInt16, false),
    ])
}

/// Schema for `get_aggregates()` — per-civ stats.
pub fn aggregates_schema() -> Schema {
    Schema::new(vec![
        Field::new("civ_id", DataType::UInt8, false),
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
        Field::new("belief", DataType::UInt8, false),
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
        Field::new("parent_id_0", DataType::UInt32, false),
        Field::new("parent_id_1", DataType::UInt32, false),
        Field::new("civ_id", DataType::UInt8, false),
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

// ---------------------------------------------------------------------------
// Ecology return schemas
// ---------------------------------------------------------------------------

/// Canonical region-state batch for the ecology simulator.
///
/// This is the post-split replacement for the old monolithic region-state
/// schema naming that existed before the FFI schemas were separated.
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
// M54b: Economy schema helpers
// ---------------------------------------------------------------------------

pub fn economy_region_input_schema() -> Schema {
    let mut fields = vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("terrain", DataType::UInt8, false),
        Field::new("storage_population", DataType::UInt16, false),
        Field::new("resource_type_0", DataType::UInt8, false),
        Field::new("resource_effective_yield_0", DataType::Float32, false),
    ];
    for good in &["grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic"] {
        fields.push(Field::new(format!("stockpile_{good}"), DataType::Float32, false));
    }
    Schema::new(fields)
}

pub fn economy_trade_route_schema() -> Schema {
    Schema::new(vec![
        Field::new("origin_region_id", DataType::UInt16, false),
        Field::new("dest_region_id", DataType::UInt16, false),
        Field::new("is_river", DataType::Boolean, false),
    ])
}

pub fn economy_region_result_schema() -> Schema {
    let mut fields = vec![
        Field::new("region_id", DataType::UInt16, false),
    ];
    for good in &["grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic"] {
        fields.push(Field::new(format!("stockpile_{good}"), DataType::Float32, false));
    }
    fields.extend_from_slice(&[
        Field::new("farmer_income_modifier", DataType::Float32, false),
        Field::new("food_sufficiency", DataType::Float32, false),
        Field::new("merchant_margin", DataType::Float32, false),
        Field::new("merchant_trade_income", DataType::Float32, false),
        Field::new("trade_route_count", DataType::UInt16, false),
    ]);
    Schema::new(fields)
}

pub fn economy_civ_result_schema() -> Schema {
    Schema::new(vec![
        Field::new("civ_id", DataType::UInt8, false),
        Field::new("treasury_tax", DataType::Float32, false),
        Field::new("tithe_base", DataType::Float32, false),
        Field::new("priest_tithe_share", DataType::Float32, false),
    ])
}

pub fn economy_observability_schema() -> Schema {
    Schema::new(vec![
        Field::new("region_id", DataType::UInt16, false),
        Field::new("imports_food", DataType::Float32, false),
        Field::new("imports_raw_material", DataType::Float32, false),
        Field::new("imports_luxury", DataType::Float32, false),
        Field::new("stockpile_food", DataType::Float32, false),
        Field::new("stockpile_raw_material", DataType::Float32, false),
        Field::new("stockpile_luxury", DataType::Float32, false),
        Field::new("import_share", DataType::Float32, false),
        Field::new("trade_dependent", DataType::Boolean, false),
        // M58b: Oracle shadow columns (null/zero when oracle not active)
        Field::new("oracle_imports_food", DataType::Float32, true),
        Field::new("oracle_imports_raw_material", DataType::Float32, true),
        Field::new("oracle_imports_luxury", DataType::Float32, true),
        Field::new("oracle_margin", DataType::Float32, true),
        Field::new("oracle_food_sufficiency", DataType::Float32, true),
    ])
}

pub fn economy_upstream_sources_schema() -> Schema {
    Schema::new(vec![
        Field::new("dest_region_id", DataType::UInt16, false),
        Field::new("source_ordinal", DataType::UInt16, false),
        Field::new("source_region_id", DataType::UInt16, false),
    ])
}

pub fn economy_conservation_schema() -> Schema {
    Schema::new(vec![
        Field::new("production", DataType::Float64, false),
        Field::new("transit_loss", DataType::Float64, false),
        Field::new("consumption", DataType::Float64, false),
        Field::new("storage_loss", DataType::Float64, false),
        Field::new("cap_overflow", DataType::Float64, false),
        Field::new("clamp_floor_loss", DataType::Float64, false),
        Field::new("in_transit_delta", DataType::Float64, true), // M58b: nullable — None in abstract mode
    ])
}

// ---------------------------------------------------------------------------
// M54c: Politics output schemas
// ---------------------------------------------------------------------------

pub fn politics_civ_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("source_ref_kind", DataType::UInt8, false),
        Field::new("source_ref_id", DataType::UInt16, false),
        Field::new("target_ref_kind", DataType::UInt8, false),
        Field::new("target_ref_id", DataType::UInt16, false),
        Field::new(
            "region_indices",
            DataType::List(Arc::new(Field::new("item", DataType::UInt16, true))),
            false,
        ),
        // Stats for breakaway / restore
        Field::new("stat_military", DataType::Int32, false),
        Field::new("stat_economy", DataType::Int32, false),
        Field::new("stat_culture", DataType::Int32, false),
        Field::new("stat_stability", DataType::Int32, false),
        Field::new("stat_treasury", DataType::Int32, false),
        Field::new("stat_population", DataType::Int32, false),
        Field::new("stat_asabiya", DataType::Float32, false),
        Field::new("founded_turn", DataType::UInt32, false),
    ])
}

pub fn politics_region_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("controller_ref_kind", DataType::UInt8, false),
        Field::new("controller_ref_id", DataType::UInt16, false),
    ])
}

pub fn politics_relationship_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("civ_a_ref_kind", DataType::UInt8, false),
        Field::new("civ_a_ref_id", DataType::UInt16, false),
        Field::new("civ_b_ref_kind", DataType::UInt8, false),
        Field::new("civ_b_ref_id", DataType::UInt16, false),
        Field::new("disposition", DataType::UInt8, false),
    ])
}

pub fn politics_federation_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("federation_ref_kind", DataType::UInt8, false),
        Field::new("federation_ref_id", DataType::UInt16, false),
        Field::new("civ_ref_kind", DataType::UInt8, false),
        Field::new("civ_ref_id", DataType::UInt16, false),
        Field::new("member_count", DataType::UInt16, false),
        Field::new("member_0_ref_kind", DataType::UInt8, false),
        Field::new("member_0_ref_id", DataType::UInt16, false),
        Field::new("member_1_ref_kind", DataType::UInt8, false),
        Field::new("member_1_ref_id", DataType::UInt16, false),
        Field::new("context_seed", DataType::UInt64, false),
    ])
}

pub fn politics_vassal_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("vassal_ref_kind", DataType::UInt8, false),
        Field::new("vassal_ref_id", DataType::UInt16, false),
        Field::new("overlord_ref_kind", DataType::UInt8, false),
        Field::new("overlord_ref_id", DataType::UInt16, false),
    ])
}

pub fn politics_exile_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("original_civ_ref_kind", DataType::UInt8, false),
        Field::new("original_civ_ref_id", DataType::UInt16, false),
        Field::new("absorber_civ_ref_kind", DataType::UInt8, false),
        Field::new("absorber_civ_ref_id", DataType::UInt16, false),
        Field::new(
            "conquered_regions",
            DataType::List(Arc::new(Field::new("item", DataType::UInt16, true))),
            false,
        ),
        Field::new("turns_remaining", DataType::Int32, false),
    ])
}

pub fn politics_proxy_war_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("op_type", DataType::UInt8, false),
        Field::new("sponsor_ref_kind", DataType::UInt8, false),
        Field::new("sponsor_ref_id", DataType::UInt16, false),
        Field::new("target_civ_ref_kind", DataType::UInt8, false),
        Field::new("target_civ_ref_id", DataType::UInt16, false),
        Field::new("target_region", DataType::UInt16, false),
    ])
}

pub fn politics_civ_effect_ops_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("civ_ref_kind", DataType::UInt8, false),
        Field::new("civ_ref_id", DataType::UInt16, false),
        Field::new("field", DataType::Utf8, false),
        Field::new("delta", DataType::Float32, false),
        Field::new("routing", DataType::UInt8, false),
    ])
}

pub fn politics_bookkeeping_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("civ_ref_kind", DataType::UInt8, false),
        Field::new("civ_ref_id", DataType::UInt16, false),
        Field::new("bk_type", DataType::UInt8, false),
        Field::new("value", DataType::Int32, false),
        Field::new("event_key", DataType::Utf8, false),
    ])
}

pub fn politics_artifact_intent_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("losing_civ_ref_kind", DataType::UInt8, false),
        Field::new("losing_civ_ref_id", DataType::UInt16, false),
        Field::new("gaining_civ_ref_kind", DataType::UInt8, false),
        Field::new("gaining_civ_ref_id", DataType::UInt16, false),
        Field::new("region", DataType::UInt16, false),
        Field::new("is_capital", DataType::Boolean, false),
        Field::new("is_destructive", DataType::Boolean, false),
        Field::new("action", DataType::Utf8, false),
    ])
}

pub fn politics_bridge_transition_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("transition_type", DataType::UInt8, false),
        Field::new("source_ref_kind", DataType::UInt8, false),
        Field::new("source_ref_id", DataType::UInt16, false),
        Field::new("target_ref_kind", DataType::UInt8, false),
        Field::new("target_ref_id", DataType::UInt16, false),
        Field::new(
            "region_indices",
            DataType::List(Arc::new(Field::new("item", DataType::UInt16, true))),
            false,
        ),
    ])
}

pub fn politics_event_trigger_schema() -> Schema {
    Schema::new(vec![
        Field::new("step", DataType::UInt8, false),
        Field::new("seq", DataType::UInt16, false),
        Field::new("event_type", DataType::Utf8, false),
        Field::new("actor_count", DataType::UInt8, false),
        Field::new("actor_0_ref_kind", DataType::UInt8, false),
        Field::new("actor_0_ref_id", DataType::UInt16, false),
        Field::new("actor_1_ref_kind", DataType::UInt8, false),
        Field::new("actor_1_ref_id", DataType::UInt16, false),
        Field::new("importance", DataType::UInt8, false),
        Field::new("context_seed", DataType::UInt64, false),
    ])
}

