//! Chronicler agent simulation core.
//!
//! Provides a Rust-backed agent-based population model with PyO3 bindings
//! and Arrow FFI for zero-copy data exchange with the Python orchestrator.

use pyo3::prelude::*;

mod agent;
mod region;

// jemalloc: cfg-gated to non-Windows. Windows dev uses system allocator.
// Performance benchmarks run on WSL/Linux where jemalloc is active.
#[cfg(not(target_os = "windows"))]
use tikv_jemallocator::Jemalloc;

#[cfg(not(target_os = "windows"))]
#[global_allocator]
static GLOBAL: Jemalloc = Jemalloc;

/// Python module entry point.
#[pymodule]
fn chronicler_agents(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    // AgentSimulator will be registered here in Task 7
    Ok(())
}
