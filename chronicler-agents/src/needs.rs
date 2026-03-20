/// M49 Needs System
/// Spec: docs/superpowers/specs/2026-03-20-m49-needs-system-design.md

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::signals::TickSignals;

/// Additive utility modifiers from needs, applied after M48 memory modifiers.
#[derive(Debug, Default)]
pub struct NeedUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch_occ: f32,
    pub stay: f32,
}
