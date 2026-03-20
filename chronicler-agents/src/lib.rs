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

// Public re-exports for integration tests and benchmarks.
#[doc(hidden)]
pub use agent::Occupation;
#[doc(hidden)]
pub use agent::BELIEF_NONE;
#[doc(hidden)]
pub use pool::AgentPool;
#[doc(hidden)]
pub use region::RegionState;
#[doc(hidden)]
pub use tick::{tick_agents, AgentEvent};
#[doc(hidden)]
pub use named_characters::{CharacterRole, NamedCharacterRegistry};
#[doc(hidden)]
pub use social::{RelationshipType, SocialEdge, SocialGraph};
#[doc(hidden)]
pub use memory::{
    MemoryEventType, MemoryIntent, MEMORY_SLOTS,
    factor_from_half_life, half_life_from_factor, default_decay_factor,
    decay_memories, write_single_memory, write_all_memories,
    clear_memory_gates, compute_memory_satisfaction_score,
    GATE_BIT_BATTLE, GATE_BIT_PROSPERITY, GATE_BIT_FAMINE, GATE_BIT_PERSECUTION,
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
    Ok(())
}
