//! Healthy-world migration drivers and the migration budget.
//!
//! The rest of the migrate utility (`behavior.rs`) answers distress: low
//! satisfaction, a destination that scores 0.18 better than home, live
//! persecution, memories of famine, war and persecution, deprivation needs.
//! This module adds three pulls that move people in a living world, each
//! behind its own gate, and one life-course threshold they must clear:
//!
//! - **Frontier settlement.** A farmer whose home is near capacity, next to
//!   a markedly emptier region of the same realm whose land would feed
//!   settlers: the draw is land, not stored food.
//! - **Wage gap.** A farmer or merchant whose adult occupational peers next
//!   door are markedly better off (mean wealth, the income they accumulated).
//!   Only these two occupations earn by location: farmers by yield and
//!   price, merchants by regional arbitrage; soldier, scholar and priest pay
//!   is flat or set per civ.
//! - **Chain migration.** Bonds to people who emigrated from the agent's
//!   region and settled in a neighbouring region of the same realm, when they
//!   outweigh the bonds the agent keeps at home.
//! - **Urban pull** (`--cities`, default off). A rural adult who is not a
//!   soldier, next to a region of the same realm whose city draws markedly
//!   more than home's (Python's `city_pull`, from the city's rank, unrest
//!   and food), when that region is fed and has room. Without the switch
//!   every region's `city_pull` is 0 and the gate never opens.
//! - **Roots (life course).** The pulls count only beyond a threshold that
//!   is zero for unattached adults up to 35 and grows with age, marriage and
//!   bonds at home. A pull opens at `PULL_AT_GATE` of its full size, so a
//!   gate that opens is a real draw, not a marginal one. Dependants (under
//!   20) take no voluntary moves; married agents' households move with them
//!   (`household.rs`).
//!
//! All four are internal migration: source and destination are ruled by
//! the same civ. Moving does not change an agent's civ affinity; crossing a
//! border makes it a minority under a foreign ruler and counts as a
//! cross-border move in the hybrid civ migration hazard. Unclaimed land has
//! no controller values, which the cultural penalty reads as a full
//! mismatch. Distress moves keep crossing borders as before.
//!
//! A pull counts only toward a region the agent would not leave again at
//! once: seen from there, home must score less than the 0.18 hysteresis
//! better (`behavior.rs`), or the opportunity term would carry it back.
//!
//! The pulls are deterministic functions of the tick's region stats and the
//! agent's own fields: no new random draws, and the decision keeps its four
//! Gumbel draws per agent. An agent whose roots outweigh every pull (or who
//! is not eligible) decides exactly as before.
//!
//! The migration budget (`MigrationDriverStats`) records every migration
//! `evaluate_region_decisions` decides, before household consolidation adds
//! spouses and dependants. Each decision counts as one unit, split across
//! the positive utility terms in proportion to their size. Dampers
//! (prosperity and death-of-kin memories, the social need, roots) are not
//! attributed. The tally is a diagnostic: nothing in the simulation reads it.

use crate::agent::{AGE_ADULT, Occupation};
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::relationships::{is_positive_valence, BondType, REL_SLOTS};

/// `RegionState::controller_civ` of a region nobody rules.
pub const UNCONTROLLED: u8 = 255;

// ---------------------------------------------------------------------------
// Constants [CALIBRATE M53 HARD] — justification in
// docs/integration/healthy-migration.md
// ---------------------------------------------------------------------------

/// Voluntary pulls apply from adulthood; dependants move with their household.
pub const MOBILITY_MIN_AGE: u16 = AGE_ADULT;
/// Roots carry no age term through this age (peak mobility).
pub const ROOTS_FREE_AGE: u16 = 35;
/// Roots per year of age beyond `ROOTS_FREE_AGE` (0.15 at 60).
pub const ROOTS_PER_YEAR: f32 = 0.006;
/// Roots of a married agent, who moves the whole household.
pub const ROOTS_MARRIED: f32 = 0.02;
/// Roots per unit of positive bond strength kept at home (sentiment / 127),
/// counted up to `ROOTS_HOME_BOND_CAP` units. The spouse is not counted: the
/// spouse moves with the household.
pub const ROOTS_PER_HOME_BOND: f32 = 0.02;
pub const ROOTS_HOME_BOND_CAP: f32 = 2.0;
/// Positive bonds below this sentiment neither anchor nor pull.
pub const BOND_MIN_SENTIMENT: i8 = 20;

/// Frontier: home at or above this share of carrying capacity ...
pub const FRONTIER_SOURCE_MIN_RATIO: f32 = 0.80;
/// ... and the destination at least this much emptier (share of capacity);
/// the pull grows to `FRONTIER_PULL` at `FRONTIER_FULL_GAP`.
pub const FRONTIER_MIN_GAP: f32 = 0.25;
pub const FRONTIER_FULL_GAP: f32 = 0.65;
/// Settlers go only where a farmer's year of food (`food_potential`) at
/// least feeds the farmer: 0.5, the economy's per-capita food. Stored food
/// would not do: an under-filled region's stores reflect how few farmers
/// work there now, not what settlers could grow.
pub const FRONTIER_MIN_FOOD_POTENTIAL: f32 = 0.5;
pub const FRONTIER_PULL: f32 = 0.6;

/// Wage gap: adult peers' mean wealth there over their mean wealth here (the
/// denominator floored at `WAGE_WEALTH_FLOOR`), from `WAGE_MIN_RATIO`, full
/// at `WAGE_FULL_RATIO`, with at least `WAGE_MIN_PEERS` peers there and room
/// there: below `WAGE_MAX_TARGET_RATIO` of capacity, the share at which the
/// frontier gate counts a region as full, so the wage gap does not refill a
/// region that frontier settlement is leaving.
pub const WAGE_MIN_RATIO: f32 = 1.25;
pub const WAGE_FULL_RATIO: f32 = 3.0;
pub const WAGE_WEALTH_FLOOR: f32 = 1.0;
pub const WAGE_MIN_PEERS: u16 = 5;
pub const WAGE_MAX_TARGET_RATIO: f32 = FRONTIER_SOURCE_MIN_RATIO;
pub const WAGE_PULL: f32 = 0.55;

/// Chain: pull per unit of bond strength toward settled emigrants, capped.
pub const CHAIN_PULL_PER_BOND: f32 = 0.30;
pub const CHAIN_PULL_CAP: f32 = 0.45;

/// Urban pull (`--cities`): the destination's `city_pull` over home's, from
/// `URBAN_MIN_GAP` (a town next to land without one: rank weight 0.4 at
/// low unrest), full at `URBAN_FULL_GAP`; the destination fed (food
/// sufficiency at least `URBAN_MIN_FOOD_SUFFICIENCY`) and below
/// `URBAN_MAX_TARGET_RATIO` of capacity (farmers: below the frontier gate's
/// 0.80, so the pull does not refill a region frontier settlement is
/// leaving). Rural adults only (`settlement_id` 0); soldiers stay posted.
/// [CALIBRATE cities] (see docs/integration/cities.md)
pub const URBAN_MIN_GAP: f32 = 0.25;
pub const URBAN_FULL_GAP: f32 = 0.75;
pub const URBAN_MIN_FOOD_SUFFICIENCY: f32 = 1.0;
pub const URBAN_MAX_TARGET_RATIO: f32 = 1.0;
pub const URBAN_FARMER_MAX_TARGET_RATIO: f32 = FRONTIER_SOURCE_MIN_RATIO;
pub const URBAN_PULL: f32 = 0.5;

const _: () = assert!(URBAN_FULL_GAP > URBAN_MIN_GAP);
const _: () = assert!(FRONTIER_FULL_GAP > FRONTIER_MIN_GAP);
const _: () = assert!(WAGE_FULL_RATIO > WAGE_MIN_RATIO);
const _: () = assert!(WAGE_MIN_RATIO > 1.0);

/// Occupations whose income depends on where they work, as an index into
/// the per-region peer wealth stats: farmer 0, merchant 1.
pub const WAGE_OCCUPATIONS: usize = 2;

#[inline]
pub fn wage_index(occupation: u8) -> Option<usize> {
    if occupation == Occupation::Farmer as u8 {
        Some(0)
    } else if occupation == Occupation::Merchant as u8 {
        Some(1)
    } else {
        None
    }
}

/// What a farmer there would harvest in food over a year as the land stands:
/// the best food slot's `ecology::annual_yield_potential` (food as the goods
/// economy counts it). Region-level; computed once per tick.
pub fn food_potential(region: &RegionState) -> f32 {
    let mut best = 0.0f32;
    for slot in 0..3 {
        if crate::economy::is_food_resource(region.resource_types[slot]) {
            best = best.max(crate::ecology::annual_yield_potential(region, slot));
        }
    }
    best
}

/// Voluntary drivers, in the order of the budget's `open` and `gate` tallies.
pub const VOLUNTARY_DRIVERS: usize = 4;
pub const VOLUNTARY_DRIVER_NAMES: [&str; VOLUNTARY_DRIVERS] = ["frontier", "wage", "chain", "urban"];

/// Voluntary pull toward one destination, by driver.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct VoluntaryPull {
    pub frontier: f32,
    pub wage: f32,
    pub chain: f32,
    pub urban: f32,
}

impl VoluntaryPull {
    /// Sum of the pulls. The urban pull is added last, so with it at 0 the
    /// sum has the bits it had without the driver.
    #[inline]
    pub fn total(&self) -> f32 {
        self.frontier + self.wage + self.chain + self.urban
    }

    /// What remains of the pull beyond the agent's roots, split across the
    /// drivers in proportion. Zero when the roots hold.
    #[inline]
    pub fn net_of_roots(self, roots: f32) -> VoluntaryPull {
        let gross = self.total();
        if gross <= roots || gross <= 0.0 {
            return VoluntaryPull::default();
        }
        let k = (gross - roots) / gross;
        VoluntaryPull {
            frontier: self.frontier * k,
            wage: self.wage * k,
            chain: self.chain * k,
            urban: self.urban * k,
        }
    }

    /// Which drivers carry a positive pull, in `VOLUNTARY_DRIVER_NAMES` order.
    #[inline]
    pub fn open(&self) -> [bool; VOLUNTARY_DRIVERS] {
        [self.frontier > 0.0, self.wage > 0.0, self.chain > 0.0, self.urban > 0.0]
    }
}

/// Share of a driver's full pull that an open gate gives at its threshold;
/// the rest grows with the gap. A gate marks a real opportunity: a pull
/// that started from zero would be held by any roots, so in effect the gate
/// would sit wherever an agent's roots put it.
pub const PULL_AT_GATE: f32 = 0.75;

/// From `PULL_AT_GATE` at `lo` to 1 at `hi` (the caller has checked x >= lo).
#[inline]
fn ramp(x: f32, lo: f32, hi: f32) -> f32 {
    PULL_AT_GATE + (1.0 - PULL_AT_GATE) * ((x - lo) / (hi - lo)).clamp(0.0, 1.0)
}

/// Roots: the share of a pull an agent does not act on.
#[inline]
pub fn roots(age: u16, married: bool, home_bonds: f32) -> f32 {
    ROOTS_PER_YEAR * age.saturating_sub(ROOTS_FREE_AGE) as f32
        + if married { ROOTS_MARRIED } else { 0.0 }
        + ROOTS_PER_HOME_BOND * home_bonds.min(ROOTS_HOME_BOND_CAP)
}

/// What one agent brings to the voluntary decision. Built once per decision
/// on the stack (bond pass over at most `REL_SLOTS` bonds, no allocation).
#[derive(Clone, Copy, Debug)]
pub struct Mobility {
    pub roots: f32,
    /// Positive bond strength at home, spouse excluded.
    pub home_bonds: f32,
    occupation: u8,
    /// Outside every settlement footprint (`settlement_id` 0).
    rural: bool,
    chain_regions: [u16; REL_SLOTS],
    chain_strength: [f32; REL_SLOTS],
    chain_len: usize,
}

impl Mobility {
    /// `None` when no voluntary pull can apply: a dependant, an agent whose
    /// region has no ruler, or no neighbouring region of the same realm.
    pub fn for_agent<L: crate::pool::SlotLookup>(
        pool: &AgentPool,
        slot: usize,
        regions: &[RegionState],
        region_id: usize,
        has_internal_neighbour: bool,
        id_to_slot: &L,
    ) -> Option<Mobility> {
        let age = pool.ages[slot];
        if age < MOBILITY_MIN_AGE || !has_internal_neighbour {
            return None;
        }
        let src = &regions[region_id];
        if src.controller_civ == UNCONTROLLED {
            return None;
        }
        let mut m = Mobility {
            roots: 0.0,
            home_bonds: 0.0,
            occupation: pool.occupations[slot],
            rural: pool.settlement_ids[slot] == 0,
            chain_regions: [0; REL_SLOTS],
            chain_strength: [0.0; REL_SLOTS],
            chain_len: 0,
        };
        let mut married = false;
        let count = (pool.rel_count[slot] as usize).min(REL_SLOTS);
        for i in 0..count {
            let bond_type = pool.rel_bond_types[slot][i];
            let is_spouse = bond_type == BondType::Marriage as u8;
            married |= is_spouse;
            let sentiment = pool.rel_sentiments[slot][i];
            if !is_positive_valence(bond_type) || sentiment < BOND_MIN_SENTIMENT {
                continue;
            }
            let target_id = pool.rel_target_ids[slot][i];
            let t = match id_to_slot.slot_of(target_id) {
                Some(t) if t < pool.capacity() && pool.is_alive(t) && pool.ids[t] == target_id => t,
                _ => continue,
            };
            if pool.is_on_trip(t) {
                continue;
            }
            let strength = sentiment as f32 / 127.0;
            let there = pool.regions[t];
            if there as usize == region_id {
                if !is_spouse {
                    m.home_bonds += strength;
                }
                continue;
            }
            // Chain: an emigrant from here, settled (not displaced) in a
            // neighbouring region of this realm.
            if pool.origin_regions[t] as usize != region_id || pool.displacement_turns[t] > 0 {
                continue;
            }
            let tr = there as usize;
            if tr >= regions.len()
                || regions[tr].controller_civ != src.controller_civ
                || src.adjacency.binary_search(&there).is_err()
            {
                continue;
            }
            match m.chain_regions[..m.chain_len].iter().position(|&r| r == there) {
                Some(j) => m.chain_strength[j] += strength,
                None => {
                    m.chain_regions[m.chain_len] = there;
                    m.chain_strength[m.chain_len] = strength;
                    m.chain_len += 1;
                }
            }
        }
        m.roots = roots(age, married, m.home_bonds);
        Some(m)
    }

    /// Bond strength toward settled emigrants in `region`.
    #[inline]
    pub fn chain_strength_toward(&self, region: u16) -> f32 {
        self.chain_regions[..self.chain_len]
            .iter()
            .position(|&r| r == region)
            .map_or(0.0, |j| self.chain_strength[j])
    }
}

/// Region inputs of the voluntary pulls, from `RegionStats`.
pub struct PullInputs<'a> {
    pub own_ratio: f32,
    /// Index of the destination in `regions`.
    pub adj_id: u16,
    pub adj_ratio: f32,
    /// The destination's `food_potential`.
    pub adj_food_potential: f32,
    /// Peer mean wealth and peer count, per wage occupation, here and there.
    pub own_peer_wealth: &'a [f32; WAGE_OCCUPATIONS],
    pub adj_peer_wealth: &'a [f32; WAGE_OCCUPATIONS],
    pub adj_peer_count: &'a [u16; WAGE_OCCUPATIONS],
}

/// Gross voluntary pull from `src` toward the neighbouring `dst`, before
/// roots. Zero unless both are ruled by the same civ.
pub fn pull_toward(
    m: &Mobility,
    src: &RegionState,
    dst: &RegionState,
    inputs: &PullInputs,
) -> VoluntaryPull {
    let mut pull = VoluntaryPull::default();
    if dst.controller_civ != src.controller_civ || src.controller_civ == UNCONTROLLED {
        return pull;
    }
    // Frontier settlement: farmers, for land.
    let gap = inputs.own_ratio - inputs.adj_ratio;
    if m.occupation == Occupation::Farmer as u8
        && inputs.own_ratio >= FRONTIER_SOURCE_MIN_RATIO
        && gap >= FRONTIER_MIN_GAP
        && inputs.adj_food_potential >= FRONTIER_MIN_FOOD_POTENTIAL
    {
        pull.frontier = FRONTIER_PULL * ramp(gap, FRONTIER_MIN_GAP, FRONTIER_FULL_GAP);
    }
    // Wage gap.
    if let Some(k) = wage_index(m.occupation) {
        if inputs.adj_ratio < WAGE_MAX_TARGET_RATIO && inputs.adj_peer_count[k] >= WAGE_MIN_PEERS {
            let ratio = inputs.adj_peer_wealth[k] / inputs.own_peer_wealth[k].max(WAGE_WEALTH_FLOOR);
            if ratio >= WAGE_MIN_RATIO {
                pull.wage = WAGE_PULL * ramp(ratio, WAGE_MIN_RATIO, WAGE_FULL_RATIO);
            }
        }
    }
    // Chain migration.
    let chain = m.chain_strength_toward(inputs.adj_id);
    if chain > m.home_bonds {
        pull.chain = (CHAIN_PULL_PER_BOND * chain).min(CHAIN_PULL_CAP);
    }
    // Urban pull: rural people drawn to the city of a neighbouring region.
    let urban_gap = dst.city_pull - src.city_pull;
    if m.rural
        && m.occupation != Occupation::Soldier as u8
        && urban_gap >= URBAN_MIN_GAP
        && dst.food_sufficiency >= URBAN_MIN_FOOD_SUFFICIENCY
        && inputs.adj_ratio
            < if m.occupation == Occupation::Farmer as u8 {
                URBAN_FARMER_MAX_TARGET_RATIO
            } else {
                URBAN_MAX_TARGET_RATIO
            }
    {
        pull.urban = URBAN_PULL * ramp(urban_gap, URBAN_MIN_GAP, URBAN_FULL_GAP);
    }
    pull
}

// ---------------------------------------------------------------------------
// Migration budget
// ---------------------------------------------------------------------------

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
pub const TERM_URBAN: usize = 17;
/// Needs calibration (2026-10): the social need's push (appended, so the
/// earlier codes of saved migration events keep their meaning).
pub const TERM_SOCIAL_NEED: usize = 18;
pub const MIGRATION_TERMS: usize = 19;

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
    "urban",
    "social_need",
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
    /// Evaluated agents whose best target carries a voluntary pull beyond
    /// their roots, by driver (`VOLUNTARY_DRIVER_NAMES`), whatever the agent
    /// then chooses.
    pub open: [u32; VOLUNTARY_DRIVERS],
    /// Evaluated agents for whom some neighbour opens the driver's gate,
    /// before roots: `gate - open` is what the roots hold back.
    pub gate: [u32; VOLUNTARY_DRIVERS],
    /// Household followers (spouses, dependants) by the largest term of the
    /// decision they follow.
    pub followers: [u32; MIGRATION_TERMS],
    /// Decided migrations by the decider's age band (`AGE_BANDS`), all and
    /// those whose largest term is a voluntary driver.
    pub decided_by_age: [u32; AGE_BANDS],
    pub voluntary_by_age: [u32; AGE_BANDS],
}

/// Age bands of the budget: under 20, 20-34, 35-49, 50-64, 65 and over.
pub const AGE_BANDS: usize = 5;

#[inline]
pub fn age_band(age: u16) -> usize {
    match age {
        0..=19 => 0,
        20..=34 => 1,
        35..=49 => 2,
        50..=64 => 3,
        _ => 4,
    }
}

/// The largest positive term of a decision (`MIGRATION_TERMS` if none).
pub fn dominant_term(terms: &[f32; MIGRATION_TERMS]) -> u8 {
    let mut best = MIGRATION_TERMS;
    let mut best_value = 0.0f32;
    for (i, &t) in terms.iter().enumerate() {
        if t > best_value {
            best_value = t;
            best = i;
        }
    }
    best as u8
}

impl MigrationDriverStats {
    pub fn count_open_pulls(&mut self, pull: &VoluntaryPull, gate_open: &[bool; VOLUNTARY_DRIVERS]) {
        let open = pull.open();
        for i in 0..VOLUNTARY_DRIVERS {
            self.open[i] += open[i] as u32;
            self.gate[i] += gate_open[i] as u32;
        }
    }

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
        for i in 0..VOLUNTARY_DRIVERS {
            self.open[i] += other.open[i];
            self.gate[i] += other.gate[i];
        }
        for i in 0..MIGRATION_TERMS {
            self.followers[i] += other.followers[i];
        }
        for i in 0..AGE_BANDS {
            self.decided_by_age[i] += other.decided_by_age[i];
            self.voluntary_by_age[i] += other.voluntary_by_age[i];
        }
    }

    /// Count one decided migration in its decider's age band.
    pub fn record_age(&mut self, age: u16, dominant: u8) {
        let band = age_band(age);
        self.decided_by_age[band] += 1;
        let d = dominant as usize;
        if d == TERM_FRONTIER || d == TERM_WAGE || d == TERM_CHAIN || d == TERM_URBAN {
            self.voluntary_by_age[band] += 1;
        }
    }

    /// Count one household follower of a decision whose largest term is
    /// `term` (from `dominant_term`).
    pub fn record_follower(&mut self, term: u8) {
        if (term as usize) < MIGRATION_TERMS {
            self.followers[term as usize] += 1;
        }
    }
}

#[cfg(test)]
mod driver_tests {
    use super::*;
    use std::collections::HashMap;

    /// Region 0 and 1 adjacent, both ruled by civ 0 unless a test changes it.
    fn realm() -> Vec<RegionState> {
        let mut regions: Vec<RegionState> = (0..2).map(RegionState::new).collect();
        for r in regions.iter_mut() {
            r.controller_civ = 0;
            r.food_sufficiency = 1.0;
        }
        regions[0].adjacency = vec![1];
        regions[1].adjacency = vec![0];
        regions
    }

    fn agent(pool: &mut AgentPool, region: u16, occupation: Occupation, age: u16) -> usize {
        pool.spawn(region, 0, occupation, age, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE)
    }

    fn bond(pool: &mut AgentPool, from: usize, to: usize, bond_type: BondType, sentiment: i8) {
        let i = pool.rel_count[from] as usize;
        pool.rel_target_ids[from][i] = pool.ids[to];
        pool.rel_sentiments[from][i] = sentiment;
        pool.rel_bond_types[from][i] = bond_type as u8;
        pool.rel_count[from] += 1;
    }

    fn index(pool: &AgentPool) -> HashMap<u32, usize> {
        (0..pool.capacity()).filter(|&s| pool.is_alive(s)).map(|s| (pool.ids[s], s)).collect()
    }

    fn mobility(pool: &AgentPool, slot: usize, regions: &[RegionState]) -> Option<Mobility> {
        let region = pool.regions[slot] as usize;
        Mobility::for_agent(pool, slot, regions, region, true, &index(pool))
    }

    fn inputs<'a>(own: f32, adj: f32, wealth: &'a [[f32; 2]; 2], count: &'a [u16; 2]) -> PullInputs<'a> {
        PullInputs {
            own_ratio: own,
            adj_id: 1,
            adj_ratio: adj,
            adj_food_potential: 1.0,
            own_peer_wealth: &wealth[0],
            adj_peer_wealth: &wealth[1],
            adj_peer_count: count,
        }
    }

    const EVEN: [[f32; 2]; 2] = [[10.0, 10.0], [10.0, 10.0]];
    const PEERS: [u16; 2] = [WAGE_MIN_PEERS; 2];

    #[test]
    fn roots_are_zero_for_young_adults_and_grow_with_age_marriage_and_home_bonds() {
        assert_eq!(roots(20, false, 0.0), 0.0);
        assert_eq!(roots(ROOTS_FREE_AGE, false, 0.0), 0.0);
        let ten_years = roots(ROOTS_FREE_AGE + 10, false, 0.0);
        assert!((ten_years - 10.0 * ROOTS_PER_YEAR).abs() < 1e-6);
        assert!(roots(ROOTS_FREE_AGE + 30, false, 0.0) > ten_years);
        assert!((roots(25, true, 0.0) - ROOTS_MARRIED).abs() < 1e-6);
        assert!((roots(25, false, 1.0) - ROOTS_PER_HOME_BOND).abs() < 1e-6);
        // Home bonds count up to the cap.
        assert_eq!(roots(25, false, 9.0), roots(25, false, ROOTS_HOME_BOND_CAP));
    }

    #[test]
    fn net_of_roots_drops_pulls_the_roots_hold_and_scales_the_rest() {
        let pull = VoluntaryPull { frontier: 0.2, wage: 0.1, chain: 0.0, urban: 0.0 };
        assert_eq!(pull.net_of_roots(0.3), VoluntaryPull::default());
        assert_eq!(pull.net_of_roots(0.5), VoluntaryPull::default());
        let net = pull.net_of_roots(0.15);
        assert!((net.total() - 0.15).abs() < 1e-6);
        assert!((net.frontier - 0.10).abs() < 1e-6 && (net.wage - 0.05).abs() < 1e-6);
        assert_eq!(pull.net_of_roots(0.0), pull);
    }

    #[test]
    fn dependants_and_regions_without_a_realm_get_no_mobility() {
        let mut regions = realm();
        let mut pool = AgentPool::new(4);
        let child = agent(&mut pool, 0, Occupation::Farmer, MOBILITY_MIN_AGE - 1);
        let adult = agent(&mut pool, 0, Occupation::Farmer, MOBILITY_MIN_AGE);
        assert!(mobility(&pool, child, &regions).is_none());
        assert!(mobility(&pool, adult, &regions).is_some());
        assert!(Mobility::for_agent(&pool, adult, &regions, 0, false, &index(&pool)).is_none());
        regions[0].controller_civ = UNCONTROLLED;
        assert!(mobility(&pool, adult, &regions).is_none());
    }

    #[test]
    fn frontier_draws_farmers_from_a_crowded_home_to_emptier_land_of_the_realm() {
        let mut regions = realm();
        let mut pool = AgentPool::new(2);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 25);
        let scholar = agent(&mut pool, 0, Occupation::Scholar, 25);
        let m = mobility(&pool, farmer, &regions).unwrap();
        let pull = |regions: &[RegionState], own: f32, adj: f32, land: f32| {
            let mut i = inputs(own, adj, &EVEN, &PEERS);
            i.adj_food_potential = land;
            pull_toward(&m, &regions[0], &regions[1], &i).frontier
        };
        // Full pull at the full gap, ramping from the minimum gap.
        assert!((pull(&regions, 1.0, 0.3, 1.0) - FRONTIER_PULL).abs() < 1e-6);
        let mid = pull(&regions, 1.0, 0.5, 1.0);
        assert!(mid > 0.0 && mid < FRONTIER_PULL);
        assert_eq!(pull(&regions, 1.0, 1.0 - FRONTIER_MIN_GAP + 0.01, 1.0), 0.0, "gap too small");
        assert_eq!(pull(&regions, FRONTIER_SOURCE_MIN_RATIO - 0.01, 0.0, 1.0), 0.0, "home not crowded");
        // Land, not stores: an empty region with no food in store but good
        // land draws settlers; poor land does not.
        regions[1].food_sufficiency = 0.0;
        assert!(pull(&regions, 1.0, 0.0, FRONTIER_MIN_FOOD_POTENTIAL) > 0.0);
        assert_eq!(pull(&regions, 1.0, 0.0, FRONTIER_MIN_FOOD_POTENTIAL - 0.01), 0.0, "poor land");
        // Farmers settle land; a scholar is not drawn.
        let s = mobility(&pool, scholar, &regions).unwrap();
        assert_eq!(pull_toward(&s, &regions[0], &regions[1], &inputs(1.0, 0.2, &EVEN, &PEERS)).frontier, 0.0);
        regions[1].controller_civ = 1;
        assert_eq!(pull(&regions, 1.0, 0.2, 1.0), 0.0, "another realm");
        regions[1].controller_civ = UNCONTROLLED;
        assert_eq!(pull(&regions, 1.0, 0.2, 1.0), 0.0, "unclaimed land");
    }

    #[test]
    fn food_potential_is_a_years_harvest_of_the_best_food_slot_as_the_land_stands() {
        let mut r = RegionState::new(0);
        r.resource_types = [1, 0, 255]; // timber, grain, empty
        r.resource_base_yield = [2.0, 1.0, 0.0];
        r.soil = 0.8;
        r.water = 0.5;
        // Grain: mean season 0.95 x soil x water; timber is not food.
        assert!((food_potential(&r) - 0.95 * 0.8 * 0.5).abs() < 1e-6);
        r.resource_types[2] = 3; // fish: no soil or water term
        r.resource_base_yield[2] = 1.0;
        assert!((food_potential(&r) - 0.85).abs() < 1e-6);
        r.resource_suspension[2] = true;
        assert!((food_potential(&r) - 0.95 * 0.8 * 0.5).abs() < 1e-6, "a suspended slot yields nothing");
        // Independent of season, climate and stores.
        r.season_id = 3;
        r.food_sufficiency = 0.0;
        assert!((food_potential(&r) - 0.95 * 0.8 * 0.5).abs() < 1e-6);
    }

    #[test]
    fn wage_gap_pulls_farmers_and_merchants_toward_better_off_peers_with_room() {
        let regions = realm();
        let mut pool = AgentPool::new(4);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 25);
        let merchant = agent(&mut pool, 0, Occupation::Merchant, 25);
        let priest = agent(&mut pool, 0, Occupation::Priest, 25);
        let rich_there = [[4.0, 4.0], [12.0, 8.0]];
        let wage = |slot: usize, wealth: &[[f32; 2]; 2], count: &[u16; 2], adj_ratio: f32| {
            let m = mobility(&pool, slot, &regions).unwrap();
            pull_toward(&m, &regions[0], &regions[1], &inputs(0.5, adj_ratio, wealth, count)).wage
        };
        assert!((wage(farmer, &rich_there, &PEERS, 0.5) - WAGE_PULL).abs() < 1e-6, "3x: full pull");
        let m = wage(merchant, &rich_there, &PEERS, 0.5);
        assert!(m > 0.0 && m < WAGE_PULL, "2x: part of the pull");
        assert_eq!(wage(priest, &rich_there, &PEERS, 0.5), 0.0, "priest pay is set per civ");
        assert_eq!(wage(farmer, &EVEN, &PEERS, 0.5), 0.0, "no gap");
        assert_eq!(wage(farmer, &rich_there, &[WAGE_MIN_PEERS - 1; 2], 0.5), 0.0, "too few peers to go by");
        assert_eq!(wage(farmer, &rich_there, &PEERS, WAGE_MAX_TARGET_RATIO), 0.0, "no room there");
        // A poor home is floored, so a small absolute gap is not a large ratio.
        let below = WAGE_WEALTH_FLOOR * (WAGE_MIN_RATIO - 0.05);
        let poor = [[0.1, 0.1], [below, below]];
        assert_eq!(wage(farmer, &poor, &PEERS, 0.5), 0.0);
        // At the gate an open gate gives PULL_AT_GATE of the full pull.
        let at_gate = WAGE_MIN_RATIO * 4.0;
        let at = wage(farmer, &[[4.0, 4.0], [at_gate, at_gate]], &PEERS, 0.5);
        assert!((at - WAGE_PULL * PULL_AT_GATE).abs() < 1e-5);
    }

    #[test]
    fn chain_pulls_toward_settled_emigrants_when_they_outweigh_home() {
        let regions = realm();
        let mut pool = AgentPool::new(8);
        let a = agent(&mut pool, 0, Occupation::Farmer, 25);
        let emigrant = agent(&mut pool, 1, Occupation::Farmer, 25);
        pool.origin_regions[emigrant] = 0; // born in region 0, settled in 1
        bond(&mut pool, a, emigrant, BondType::Kin, 64);
        let chain = |pool: &AgentPool| {
            let m = mobility(pool, a, &regions).unwrap();
            (pull_toward(&m, &regions[0], &regions[1], &inputs(0.5, 0.5, &EVEN, &PEERS)).chain, m)
        };
        let (pull, m) = chain(&pool);
        assert!((pull - CHAIN_PULL_PER_BOND * 64.0 / 127.0).abs() < 1e-6);
        assert_eq!(m.roots, 0.0);

        // Not yet settled: no letters home.
        pool.displacement_turns[emigrant] = 3;
        assert_eq!(chain(&pool).0, 0.0);
        pool.displacement_turns[emigrant] = 0;

        // A native of region 1 is not an emigrant from here.
        pool.origin_regions[emigrant] = 1;
        assert_eq!(chain(&pool).0, 0.0);
        pool.origin_regions[emigrant] = 0;

        // A spouse at home moves with the household: it adds roots, not an anchor.
        let spouse = agent(&mut pool, 0, Occupation::Farmer, 25);
        bond(&mut pool, a, spouse, BondType::Marriage, 100);
        let (pull, m) = chain(&pool);
        assert!(pull > 0.0);
        assert_eq!(m.home_bonds, 0.0);
        assert!((m.roots - ROOTS_MARRIED).abs() < 1e-6);

        // Kin and friends at home outweigh one emigrant: no pull, more roots.
        let friend = agent(&mut pool, 0, Occupation::Farmer, 25);
        bond(&mut pool, a, friend, BondType::Friend, 70);
        let (pull, m) = chain(&pool);
        assert_eq!(pull, 0.0);
        assert!(m.home_bonds > 0.5);
    }

    #[test]
    fn chain_ignores_weak_and_negative_bonds_and_other_realms() {
        let mut regions = realm();
        let mut pool = AgentPool::new(4);
        let a = agent(&mut pool, 0, Occupation::Farmer, 25);
        let rival = agent(&mut pool, 1, Occupation::Farmer, 25);
        let weak = agent(&mut pool, 1, Occupation::Farmer, 25);
        pool.origin_regions[rival] = 0;
        pool.origin_regions[weak] = 0;
        bond(&mut pool, a, rival, BondType::Rival, 90);
        bond(&mut pool, a, weak, BondType::Friend, BOND_MIN_SENTIMENT - 1);
        let m = mobility(&pool, a, &regions).unwrap();
        assert_eq!(m.chain_strength_toward(1), 0.0);
        bond(&mut pool, a, weak, BondType::Kin, 80);
        regions[1].controller_civ = 1;
        let m = mobility(&pool, a, &regions).unwrap();
        assert_eq!(m.chain_strength_toward(1), 0.0, "a bond across the border does not pull");
    }

    #[test]
    fn urban_pull_draws_rural_adults_to_a_fed_city_of_the_realm_with_room() {
        let mut regions = realm();
        regions[1].city_pull = 1.0; // a great city next door, no city at home
        let mut pool = AgentPool::new(8);
        let scholar = agent(&mut pool, 0, Occupation::Scholar, 25);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 25);
        let soldier = agent(&mut pool, 0, Occupation::Soldier, 25);
        let townsman = agent(&mut pool, 0, Occupation::Merchant, 25);
        pool.settlement_ids[townsman] = 3; // lives in a settlement already
        let urban = |regions: &[RegionState], slot: usize, adj_ratio: f32| {
            let m = mobility(&pool, slot, regions).unwrap();
            pull_toward(&m, &regions[0], &regions[1], &inputs(0.5, adj_ratio, &EVEN, &PEERS)).urban
        };
        assert!((urban(&regions, scholar, 0.5) - URBAN_PULL).abs() < 1e-6, "gap 1.0: full pull");
        assert!((urban(&regions, farmer, 0.5) - URBAN_PULL).abs() < 1e-6);
        assert_eq!(urban(&regions, soldier, 0.5), 0.0, "soldiers stay posted");
        assert_eq!(urban(&regions, townsman, 0.5), 0.0, "already urban");
        // Room: farmers only below the frontier gate's threshold, others below capacity.
        assert_eq!(urban(&regions, farmer, URBAN_FARMER_MAX_TARGET_RATIO), 0.0);
        assert!(urban(&regions, scholar, URBAN_FARMER_MAX_TARGET_RATIO) > 0.0);
        assert_eq!(urban(&regions, scholar, URBAN_MAX_TARGET_RATIO), 0.0, "no room");
        // A hungry city does not draw.
        regions[1].food_sufficiency = URBAN_MIN_FOOD_SUFFICIENCY - 0.01;
        assert_eq!(urban(&regions, scholar, 0.5), 0.0, "not fed");
        regions[1].food_sufficiency = 1.0;
        // The gap, not the level: a city at home draws less, and a small gap none.
        regions[0].city_pull = 1.0 - URBAN_MIN_GAP;
        let at_gate = urban(&regions, scholar, 0.5);
        assert!((at_gate - URBAN_PULL * PULL_AT_GATE).abs() < 1e-5, "{at_gate}");
        regions[0].city_pull = 1.0 - URBAN_MIN_GAP + 0.01;
        assert_eq!(urban(&regions, scholar, 0.5), 0.0, "gap too small");
        regions[0].city_pull = 0.0;
        // Internal only.
        regions[1].controller_civ = 1;
        assert_eq!(urban(&regions, scholar, 0.5), 0.0, "another realm");
    }

    #[test]
    fn without_city_pull_the_urban_driver_adds_nothing_and_the_sum_keeps_its_bits() {
        let regions = realm(); // city_pull 0 everywhere: the switch off
        let mut pool = AgentPool::new(2);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 25);
        let m = mobility(&pool, farmer, &regions).unwrap();
        let mut i = inputs(1.0, 0.3, &[[4.0, 4.0], [12.0, 8.0]], &PEERS);
        i.adj_ratio = 0.3;
        let pull = pull_toward(&m, &regions[0], &regions[1], &i);
        assert_eq!(pull.urban, 0.0);
        assert!(pull.frontier > 0.0 && pull.wage > 0.0);
        assert_eq!(pull.total().to_bits(), (pull.frontier + pull.wage + pull.chain).to_bits());
        assert_eq!(pull.open(), [true, true, false, false]);
        let net = pull.net_of_roots(0.1);
        assert_eq!(net.urban, 0.0);
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
    fn social_need_is_appended_after_urban_and_urban_counts_as_voluntary_by_age() {
        assert_eq!(MIGRATION_TERM_NAMES[TERM_URBAN], "urban");
        assert_eq!(MIGRATION_TERM_NAMES[TERM_SOCIAL_NEED], "social_need");
        assert_eq!(TERM_SOCIAL_NEED, MIGRATION_TERMS - 1);
        assert_eq!(VOLUNTARY_DRIVER_NAMES, ["frontier", "wage", "chain", "urban"]);
        let mut stats = MigrationDriverStats::default();
        stats.record_age(25, TERM_URBAN as u8);
        assert_eq!((stats.decided_by_age[1], stats.voluntary_by_age[1]), (1, 1));
        let pull = VoluntaryPull { urban: 0.3, ..Default::default() };
        stats.count_open_pulls(&pull, &[false, false, false, true]);
        assert_eq!((stats.open[3], stats.gate[3]), (1, 1));
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
