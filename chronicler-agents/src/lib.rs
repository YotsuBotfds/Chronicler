//! Chronicler agent simulation core.
//!
//! Provides a Rust-backed agent-based population model with PyO3 bindings
//! and Arrow FFI for zero-copy data exchange with the Python orchestrator.

use pyo3::prelude::*;

mod agent;
mod ffi;
mod pool;
mod region;
pub mod satisfaction;
mod tick;

// Public re-exports for integration tests and benchmarks.
#[doc(hidden)]
pub use agent::Occupation;
#[doc(hidden)]
pub use pool::AgentPool;
#[doc(hidden)]
pub use region::RegionState;
#[doc(hidden)]
pub use tick::tick_agents;

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
