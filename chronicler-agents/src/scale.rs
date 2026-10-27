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
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct TickOptions {
    pub scale_mode: AgentScaleMode,
    /// Profiling only: time the discarded Morton sort of the spatial step at
    /// or above `sort::SPATIAL_SORT_AGENT_THRESHOLD` agents
    /// (`SpatialDiagnostics::sort_time_us`). Off by default; it never
    /// changes simulation results.
    pub profile_spatial_sort: bool,
    /// Validation experiments only: decision terms switched off from a
    /// turn on (`DecisionAblation`). Off by default (mask 0): every tick
    /// decides exactly as before.
    pub ablation: DecisionAblation,
    /// Community anchoring (`--community-anchoring`, `crate::community`).
    /// Off by default: the anchor is never computed.
    pub community_anchoring: CommunityAnchoring,
}

/// The community anchoring switch and its strength (`crate::community`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CommunityAnchoring {
    pub enabled: bool,
    /// The anchor of an agent with `community::COMMUNITY_FULL_TIES` ties, in
    /// utility units (default `community::COMMUNITY_ANCHOR`).
    pub full_anchor: f32,
}

impl Default for CommunityAnchoring {
    fn default() -> Self {
        Self { enabled: false, full_anchor: crate::community::COMMUNITY_ANCHOR }
    }
}

// ---------------------------------------------------------------------------
// Decision ablations (validation experiments; docs/integration/ablation-oracles.md)
// ---------------------------------------------------------------------------

/// The need terms of the agent decision: `needs::compute_need_utility_modifiers`
/// is replaced by zeros (rebel, migrate, switch and stay utilities) and the
/// autonomy deficit no longer speeds loyalty drift. Needs still evolve.
pub const ABLATE_NEEDS: u8 = 1;
/// The relationship part of a migrant's roots (`migration_drivers::roots`):
/// marriage and positive bonds at home no longer hold back a voluntary pull.
/// The life-course (age) part stays, and home bonds still decide whether
/// chain migration pulls.
pub const ABLATE_KIN_ROOTS: u8 = 2;
/// A placebo: the decision draws come from another random stream
/// (`agent::DECISION_PLACEBO_STREAM_OFFSET`). No term changes; the arm
/// differs from the plain run only by chance.
pub const ABLATE_PLACEBO: u8 = 4;
/// The community anchor (`crate::community`, `--community-anchoring`):
/// community ties no longer hold back a move. Without community anchoring
/// there is no anchor to switch off.
pub const ABLATE_COMMUNITY_ANCHOR: u8 = 8;
/// Every known ablation bit.
pub const ABLATE_KNOWN: u8 = ABLATE_NEEDS | ABLATE_KIN_ROOTS | ABLATE_PLACEBO | ABLATE_COMMUNITY_ANCHOR;

/// Which decision terms are switched off, from which tick turn on.
///
/// A validation arm runs a seed as the plain run does, with the ablation
/// taking effect at `start_turn`: every tick before it is the plain tick, so
/// the two runs share their history up to the fork and differ afterwards
/// only through the ablated terms. The switch draws nothing and changes no
/// state of its own; with `mask` 0 (the default) it does nothing at all.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct DecisionAblation {
    /// Bits of `ABLATE_*`.
    pub mask: u8,
    /// First tick turn whose decisions are ablated.
    pub start_turn: u32,
}

impl DecisionAblation {
    /// The `ABLATE_*` bit of an ablation name.
    pub fn bit(name: &str) -> Option<u8> {
        match name {
            "needs" => Some(ABLATE_NEEDS),
            "kin_roots" => Some(ABLATE_KIN_ROOTS),
            "placebo" => Some(ABLATE_PLACEBO),
            "community_anchor" => Some(ABLATE_COMMUNITY_ANCHOR),
            _ => None,
        }
    }

    /// Names of the bits set in `mask`, in bit order.
    pub fn names(mask: u8) -> Vec<&'static str> {
        [
            (ABLATE_NEEDS, "needs"),
            (ABLATE_KIN_ROOTS, "kin_roots"),
            (ABLATE_PLACEBO, "placebo"),
            (ABLATE_COMMUNITY_ANCHOR, "community_anchor"),
        ]
            .iter()
            .filter(|(bit, _)| mask & bit != 0)
            .map(|&(_, name)| name)
            .collect()
    }

    /// The bits in force for a tick of `turn`: `mask` from `start_turn` on, else 0.
    #[inline]
    pub fn active(self, turn: u32) -> u8 {
        if self.mask != 0 && turn >= self.start_turn {
            self.mask
        } else {
            0
        }
    }
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
    scale_mode, profile_spatial_sort, ablation, community_anchoring,
});
crate::persist_struct!(DecisionAblation {
    mask, start_turn,
});
crate::persist_struct!(CommunityAnchoring {
    enabled, full_anchor,
});
crate::persist_enum!(AgentScaleMode {
    Exact = 0, Fast = 1,
});

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decision_ablation_is_off_by_default_and_from_its_start_turn_on() {
        assert_eq!(TickOptions::default().ablation, DecisionAblation { mask: 0, start_turn: 0 });
        assert_eq!(TickOptions::default().ablation.active(0), 0);
        assert_eq!(TickOptions::default().ablation.active(u32::MAX), 0);
        let a = DecisionAblation { mask: ABLATE_NEEDS, start_turn: 101 };
        assert_eq!(a.active(100), 0);
        assert_eq!(a.active(101), ABLATE_NEEDS);
        assert_eq!(a.active(500), ABLATE_NEEDS);
    }

    #[test]
    fn decision_ablation_names_round_trip() {
        for name in ["needs", "kin_roots", "placebo", "community_anchor"] {
            let bit = DecisionAblation::bit(name).unwrap();
            assert_eq!(bit & ABLATE_KNOWN, bit);
            assert_eq!(DecisionAblation::names(bit), vec![name]);
        }
        assert_eq!(DecisionAblation::bit("terms"), None);
        assert_eq!(DecisionAblation::names(0), Vec::<&str>::new());
        assert_eq!(
            DecisionAblation::names(ABLATE_KNOWN),
            vec!["needs", "kin_roots", "placebo", "community_anchor"]
        );
    }

    #[test]
    fn tick_options_persist_the_ablation_exactly() {
        let options = TickOptions {
            scale_mode: AgentScaleMode::Fast,
            profile_spatial_sort: true,
            ablation: DecisionAblation { mask: ABLATE_KIN_ROOTS, start_turn: 301 },
            community_anchoring: CommunityAnchoring { enabled: true, full_anchor: 0.25 },
        };
        let blob = crate::persist::encode(crate::persist::KIND_AGENT, &options);
        let back: TickOptions = crate::persist::decode(crate::persist::KIND_AGENT, &blob).unwrap();
        assert_eq!(back, options);
        let schema = crate::persist::schema_of::<TickOptions>();
        assert!(schema.contains("ablation:DecisionAblation{mask:u8,start_turn:u32,}"));
        assert!(schema.contains("community_anchoring:CommunityAnchoring{enabled:bool,full_anchor:f32,}"));
    }

    #[test]
    fn community_anchoring_is_off_by_default_at_the_calibrated_strength() {
        let options = TickOptions::default();
        assert!(!options.community_anchoring.enabled);
        assert_eq!(options.community_anchoring.full_anchor, crate::community::COMMUNITY_ANCHOR);
    }
}
