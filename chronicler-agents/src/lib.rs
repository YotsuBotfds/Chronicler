//! Chronicler agent simulation core.
//!
//! Provides a Rust-backed agent-based population model with PyO3 bindings
//! and Arrow FFI for zero-copy data exchange with the Python orchestrator.

use pyo3::prelude::*;

mod agent;
mod ffi;
mod pool;
mod region;
pub mod behavior;
pub mod demographics;
pub mod satisfaction;
pub mod signals;
mod tick;
pub mod named_characters;
pub mod culture_tick;
pub mod conversion_tick;
pub mod social;
pub mod memory;
pub mod needs;
pub mod relationships;
pub mod formation;
pub mod ecology;
pub mod spatial;

// Public re-exports for integration tests and benchmarks.
#[doc(hidden)]
pub use ffi::AgentSimulator;
#[doc(hidden)]
pub use ffi::EcologySimulator;

/// Re-exported FFI schemas for integration tests.
pub mod ffi_schemas {
    pub use crate::ffi::{ecology_region_schema, ecology_events_schema};
}
#[doc(hidden)]
pub use agent::Occupation;
#[doc(hidden)]
pub use agent::BELIEF_NONE;
#[doc(hidden)]
pub use pool::AgentPool;
#[doc(hidden)]
pub use region::RegionState;
#[doc(hidden)]
pub use tick::{tick_agents, AgentEvent, DemographicDebug};
#[doc(hidden)]
pub use named_characters::{CharacterRole, NamedCharacterRegistry};
#[doc(hidden)]
pub use social::{RelationshipType, SocialEdge, SocialGraph};
#[doc(hidden)]
pub use memory::{
    MemoryEventType, MemoryIntent, MemoryUtilityModifiers, MEMORY_SLOTS,
    factor_from_half_life, half_life_from_factor, default_decay_factor,
    decay_memories, write_single_memory, write_all_memories,
    clear_memory_gates, compute_memory_satisfaction_score,
    compute_memory_utility_modifiers, agents_share_memory, agents_share_memory_with_valence,
    extract_legacy_memories,
    GATE_BIT_BATTLE, GATE_BIT_PROSPERITY, GATE_BIT_FAMINE, GATE_BIT_PERSECUTION,
};
#[doc(hidden)]
pub use needs::NeedUtilityModifiers;
#[doc(hidden)]
pub use needs::{decay_needs, restore_needs, clamp_needs, update_needs, compute_need_utility_modifiers};
#[doc(hidden)]
pub use signals::{CivSignals, TickSignals};
#[doc(hidden)]
pub use formation::{formation_scan, FormationStats, death_cleanup_sweep, belief_divergence_cleanup};
#[doc(hidden)]
pub use agent::{FORMATION_CADENCE, MAX_NEW_BONDS_PER_PASS, MAX_NEW_BONDS_PER_REGION, LIFE_EVENT_DISSOLUTION};
#[doc(hidden)]
pub use agent::{LEGACY_HALF_LIFE, LEGACY_MIN_INTENSITY, LEGACY_MAX_MEMORIES};
#[doc(hidden)]
pub use agent::{
    SAFETY_DECAY, MATERIAL_DECAY, SOCIAL_DECAY, SPIRITUAL_DECAY, AUTONOMY_DECAY, PURPOSE_DECAY,
};

// jemalloc: cfg-gated to non-Windows. Windows dev uses system allocator.
// Performance benchmarks run on WSL/Linux where jemalloc is active.
#[cfg(not(target_os = "windows"))]
use tikv_jemallocator::Jemalloc;

#[cfg(not(target_os = "windows"))]
#[global_allocator]
static GLOBAL: Jemalloc = Jemalloc;

/// Python module entry point.
#[pymodule]
fn chronicler_agents(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ffi::AgentSimulator>()?;
    m.add_class::<ffi::EcologySimulator>()?;
    Ok(())
}
