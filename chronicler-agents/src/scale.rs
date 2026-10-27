//! Agent-scale execution mode.
//!
//! `Exact` (the default) reproduces the reference algorithms bit for bit:
//! every RNG draw, candidate set and floating-point accumulation order is the
//! same as before the scale work, so runs are byte-identical.
//!
//! `Fast` swaps the density-dependent parts of the tick for bounded-work
//! approximations whose per-agent cost does not grow with region density:
//!
//! * spatial drift buckets each region into a population-sized grid
//!   (10 x 10 up to 20 x 20 cells, never narrower than the repulsion radius)
//!   and evaluates at most [`FAST_DRIFT_MAX_NEIGHBORS`] neighbours per agent,
//!   a deterministic stride sample of its 3 x 3 block;
//! * marriage lets each eligible agent examine a stride sample of at most
//!   [`FAST_MARRIAGE_SCAN`] agents around it and keep its
//!   [`FAST_MARRIAGE_CANDIDATES`] best partners in the reference greedy order;
//!   the same greedy matching then runs on the union of those lists. Regions
//!   with at most `FAST_MARRIAGE_SCAN` eligible agents keep the exact scan;
//! * relationship formation pairs each agent only with the next
//!   [`FAST_FORMATION_PARTNERS`] agents of the region's shuffled order.
//!
//! Fast mode changes candidate sets and therefore results; it is designed to
//! keep bonds and marriages per agent statistically equivalent (see
//! `docs/performance/rust-agent-scale.md`). It is opt-in.

/// How density-dependent tick phases choose their candidates.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AgentScaleMode {
    /// Reference algorithms; byte-identical outputs.
    #[default]
    Exact,
    /// Bounded-work approximations for large populations.
    Fast,
}

impl AgentScaleMode {
    pub fn parse(name: &str) -> Option<Self> {
        match name {
            "exact" => Some(Self::Exact),
            "fast" => Some(Self::Fast),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Exact => "exact",
            Self::Fast => "fast",
        }
    }
}

/// Per-tick options that do not belong to region or civ signals.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TickOptions {
    pub scale_mode: AgentScaleMode,
    /// Profiling only: time the discarded Morton sort of the spatial step at
    /// or above `sort::SPATIAL_SORT_AGENT_THRESHOLD` agents
    /// (`SpatialDiagnostics::sort_time_us`). Off by default; it never
    /// changes simulation results.
    pub profile_spatial_sort: bool,
}

/// Fast drift: target mean agents per neighbour-grid cell.
pub const FAST_DRIFT_TARGET_PER_CELL: usize = 8; // [CALIBRATE M61b]
/// Fast drift: the grid never gets coarser than the exact 10 x 10 grid.
pub const FAST_DRIFT_MIN_SIDE: usize = 10;
/// Fast drift: cells are never narrower than the repulsion radius (0.05), so
/// the 3 x 3 query block always contains every repelling neighbour.
pub const FAST_DRIFT_MAX_SIDE: usize = 20;
/// Fast drift: neighbours evaluated per agent (deterministic stride sample).
pub const FAST_DRIFT_MAX_NEIGHBORS: usize = 96; // [CALIBRATE M61b]
/// Fast marriage: agents examined per eligible agent (stride sample of the
/// surrounding block). Regions with at most this many eligible agents use the
/// exact all-pairs scan.
pub const FAST_MARRIAGE_SCAN: usize = 256; // [CALIBRATE M61b]
/// Fast marriage: best valid partners kept per agent for the matching.
pub const FAST_MARRIAGE_CANDIDATES: usize = 24; // [CALIBRATE M61b]
/// Fast formation: later partners examined per agent in the shuffled order.
pub const FAST_FORMATION_PARTNERS: usize = 64; // [CALIBRATE M61b]

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(TickOptions {
    scale_mode, profile_spatial_sort,
});
crate::persist_enum!(AgentScaleMode {
    Exact = 0, Fast = 1,
});
