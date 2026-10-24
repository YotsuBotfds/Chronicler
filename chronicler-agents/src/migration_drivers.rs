//! Migration budget: which terms of the decision moved each migrant.
//!
//! `evaluate_region_decisions` records every migration it decides (before
//! household consolidation adds spouses and dependents). Each decision
//! counts as one unit, split across the positive utility terms in proportion
//! to their size, the rule the probe tooling used. Dampers (prosperity and
//! death-of-kin memories, the social need) are not attributed. The tally is
//! a diagnostic: nothing in the simulation reads it.

/// Index of each attributable term in [`MigrationDriverStats::share`].
pub const TERM_LOW_SATISFACTION: usize = 0;
pub const TERM_OPP_SATISFACTION: usize = 1;
pub const TERM_OPP_CAPACITY: usize = 2;
pub const TERM_OPP_FOOD: usize = 3;
pub const TERM_OPP_RIVER: usize = 4;
pub const TERM_OPP_NEWS: usize = 5;
pub const TERM_PERSECUTION: usize = 6;
pub const TERM_FAMINE_MEMORY: usize = 7;
pub const TERM_BATTLE_MEMORY: usize = 8;
pub const TERM_CONQUEST_MEMORY: usize = 9;
pub const TERM_PERSECUTION_MEMORY: usize = 10;
pub const TERM_SAFETY_NEED: usize = 11;
pub const TERM_MATERIAL_NEED: usize = 12;
pub const TERM_SPIRITUAL_NEED: usize = 13;
pub const TERM_FRONTIER: usize = 14;
pub const TERM_WAGE: usize = 15;
pub const TERM_CHAIN: usize = 16;
pub const MIGRATION_TERMS: usize = 17;

/// Names exported by `AgentSimulator.get_migration_driver_stats`.
pub const MIGRATION_TERM_NAMES: [&str; MIGRATION_TERMS] = [
    "low_satisfaction",
    "opp_satisfaction",
    "opp_capacity",
    "opp_food",
    "opp_river",
    "opp_news",
    "persecution",
    "famine_memory",
    "battle_memory",
    "conquest_memory",
    "persecution_memory",
    "safety_need",
    "material_need",
    "spiritual_need",
    "frontier",
    "wage",
    "chain",
];

/// Per-tick migration decision tally.
#[derive(Debug, Default, Clone)]
pub struct MigrationDriverStats {
    /// Agents that weighed a move (alive, idle, not displaced).
    pub evaluated: u32,
    /// Migrations decided, before household consolidation.
    pub decided: u32,
    /// Decided migrations with no positive term (cannot happen while the
    /// migrate gate requires positive utility; kept as a check).
    pub unexplained: u32,
    /// Summed shares: each decided migration adds 1.0 across the terms.
    pub share: [f64; MIGRATION_TERMS],
    /// Decided migrations in which the term was positive.
    pub present: [u32; MIGRATION_TERMS],
}

impl MigrationDriverStats {
    /// Record one decided migration from its positive utility terms.
    pub fn record(&mut self, terms: &[f32; MIGRATION_TERMS]) {
        self.decided += 1;
        let mut total = 0.0f64;
        for &t in terms {
            if t > 0.0 {
                total += t as f64;
            }
        }
        if total <= 0.0 {
            self.unexplained += 1;
            return;
        }
        for (i, &t) in terms.iter().enumerate() {
            if t > 0.0 {
                self.share[i] += t as f64 / total;
                self.present[i] += 1;
            }
        }
    }

    pub fn merge(&mut self, other: &MigrationDriverStats) {
        self.evaluated += other.evaluated;
        self.decided += other.decided;
        self.unexplained += other.unexplained;
        for i in 0..MIGRATION_TERMS {
            self.share[i] += other.share[i];
            self.present[i] += other.present[i];
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn record_splits_one_unit_across_positive_terms() {
        let mut stats = MigrationDriverStats::default();
        let mut terms = [0.0f32; MIGRATION_TERMS];
        terms[TERM_FAMINE_MEMORY] = 0.3;
        terms[TERM_FRONTIER] = 0.1;
        terms[TERM_OPP_FOOD] = -0.2; // a negative component is not attributed
        stats.record(&terms);
        assert_eq!(stats.decided, 1);
        assert!((stats.share[TERM_FAMINE_MEMORY] - 0.75).abs() < 1e-6);
        assert!((stats.share[TERM_FRONTIER] - 0.25).abs() < 1e-6);
        assert_eq!(stats.share[TERM_OPP_FOOD], 0.0);
        assert_eq!(stats.present[TERM_FAMINE_MEMORY], 1);
        assert_eq!(stats.present[TERM_OPP_FOOD], 0);
        let total: f64 = stats.share.iter().sum();
        assert!((total - 1.0).abs() < 1e-9);
    }

    #[test]
    fn record_counts_a_migration_without_positive_terms_as_unexplained() {
        let mut stats = MigrationDriverStats::default();
        stats.record(&[0.0; MIGRATION_TERMS]);
        assert_eq!((stats.decided, stats.unexplained), (1, 1));
        assert_eq!(stats.share.iter().sum::<f64>(), 0.0);
    }

    #[test]
    fn merge_adds_counts_and_shares() {
        let mut a = MigrationDriverStats::default();
        let mut b = MigrationDriverStats::default();
        let mut terms = [0.0f32; MIGRATION_TERMS];
        terms[TERM_CHAIN] = 1.0;
        a.record(&terms);
        b.record(&terms);
        b.evaluated = 7;
        a.merge(&b);
        assert_eq!((a.decided, a.evaluated), (2, 7));
        assert!((a.share[TERM_CHAIN] - 2.0).abs() < 1e-9);
    }
}
