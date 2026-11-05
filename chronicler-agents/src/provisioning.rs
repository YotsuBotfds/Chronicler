//! Livelihoods L2: explicit allocation of a region's available food to people.
//!
//! Off by default. Python installs a one-tick [`ProvisionConfig`] before the
//! agent tick; the tick takes it at phase 0.7, after this turn's catastrophe
//! and targeted deaths and before needs, and writes one ration per living
//! agent (`AgentPool::food_access`, keyed by stable id). Needs, satisfaction
//! and hunger mortality/fertility read [`food_for`], which returns the
//! regional signal unchanged whenever no allocation is installed, so a
//! disabled world computes exactly what it did before.
//!
//! Units are rations: 1.0 is the economy's per-capita food demand. The
//! regional withdrawal is the Phase 2 economy's: `fs * N2` rations, where
//! `fs` is the region's food sufficiency after public release and `N2` the
//! Phase 2 native alive count that the demand was computed for. When
//! `fs >= 1` nobody is short and every person keeps the regional signal
//! (abundance included). When `fs < 1` the living's share `T = fs * N`
//! (N living, at most N2) is allocated, each person at most one ration,
//! under one explicit rule; the share of people who died after Phase 2 is
//! recorded as unallocated:
//!
//! * equal: `min(1, T / N) = fs` each: exactly the regional signal, so it is
//!   the identity control of the mechanism.
//! * floor_means: an equal floor `min(floor, T / N)`, then the scarce
//!   remainder by household means (per-capita adult wealth plus a declared
//!   base weight), water-filled up to a full ration. A market-access rule,
//!   stated, not a hidden wealth-to-food formula.
//! * targeted_relief: market food (`pre_release * N2`) equally; the public
//!   release (`(fs - pre_release) * N2`) to the poorest `target_share` of
//!   households first, then to everyone else; anything left is unallocated.
//!
//! Households are derived, not stored: a married adult's household is keyed
//! by the smaller of the couple's ids when the spouse is alive in the same
//! region; a child (age < AGE_ADULT) joins a living parent's household in the
//! same region; anyone else is a household of one. Rations left over because
//! people died after Phase 2 are recorded as unallocated, never invented.
//! The severe-hunger run (`food_severe_turns`) remains regional.
use std::collections::BTreeMap;

use crate::agent::AGE_ADULT;
use crate::pool::AgentPool;
use crate::region::RegionState;

pub const REGIME_EQUAL: u8 = 0;
pub const REGIME_FLOOR_MEANS: u8 = 1;
pub const REGIME_TARGETED_RELIEF: u8 = 2;
/// Bounded per-person receipts (stable sample: ascending id within region order).
pub const MAX_SAMPLE: usize = 256;
/// Base weight added to per-capita household wealth in floor_means [declared].
pub const MEANS_BASE_WEIGHT: f64 = 1.0;
const EPS: f64 = 1e-9;

#[derive(Clone, Debug, PartialEq)]
pub struct ProvisionConfig {
    pub source_turn: u32,
    pub regime: u8,
    pub floor: f32,
    pub target_share: f32,
    /// Per region: food sufficiency before public release (NaN: unknown).
    pub pre_release: Vec<f32>,
    /// Per region: Phase 2 native alive count.
    pub phase2_alive: Vec<u32>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct RegionProvision {
    pub region: u16,
    pub scarce: bool,
    pub phase2_alive: u32,
    pub alive: u32,
    pub households: u32,
    pub sufficiency: f32,
    pub rations_available: f64,
    pub relief_available: f64,
    pub allocated: f64,
    pub unallocated: f64,
    pub relief_to_targeted: f64,
    pub shortfall: f64,
    pub below_floor: u32,
    pub fully_fed: u32,
    pub min_ration: f32,
    pub max_ration: f32,
    pub people_poorer_half: u32,
    pub shortfall_poorer_half: f64,
    pub people_richer_half: u32,
    pub shortfall_richer_half: f64,
    pub children: u32,
    pub shortfall_children: f64,
}

/// Column names of [`RegionProvision::row`], in order.
pub const REGION_COLUMNS: [&str; 22] = [
    "region", "scarce", "phase2_alive", "alive", "households", "sufficiency",
    "rations_available", "relief_available", "allocated", "unallocated",
    "relief_to_targeted", "shortfall", "below_floor", "fully_fed", "min_ration",
    "max_ration", "people_poorer_half", "shortfall_poorer_half", "people_richer_half",
    "shortfall_richer_half", "children", "shortfall_children",
];

impl RegionProvision {
    pub fn row(&self) -> Vec<f64> {
        vec![
            self.region as f64, self.scarce as u8 as f64, self.phase2_alive as f64, self.alive as f64,
            self.households as f64, self.sufficiency as f64, self.rations_available, self.relief_available,
            self.allocated, self.unallocated, self.relief_to_targeted, self.shortfall,
            self.below_floor as f64, self.fully_fed as f64, self.min_ration as f64, self.max_ration as f64,
            self.people_poorer_half as f64, self.shortfall_poorer_half, self.people_richer_half as f64,
            self.shortfall_richer_half, self.children as f64, self.shortfall_children,
        ]
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct ProvisionFrame {
    pub source_turn: u32,
    pub regime: u8,
    pub regions: Vec<RegionProvision>,
    /// (agent id, region, household key, ration, targeted)
    pub sample: Vec<(u32, u16, u32, f32, bool)>,
    pub sample_dropped: usize,
}

pub fn validate(cfg: &ProvisionConfig, num_regions: usize) -> Result<(), &'static str> {
    if cfg.regime > REGIME_TARGETED_RELIEF {
        return Err("unknown food allocation regime");
    }
    if !(cfg.floor > 0.0 && cfg.floor <= 1.0) || !(cfg.target_share > 0.0 && cfg.target_share <= 1.0) {
        return Err("food allocation floor and target share must be in (0, 1]");
    }
    if cfg.pre_release.len() != num_regions || cfg.phase2_alive.len() != num_regions {
        return Err("food allocation rows must match the region count");
    }
    if cfg.pre_release.iter().any(|v| !(v.is_nan() || (v.is_finite() && *v >= 0.0))) {
        return Err("pre-release food sufficiency must be finite and nonnegative (NaN: unknown)");
    }
    Ok(())
}

/// The food signal one agent's consumers read this tick: the person's own
/// ration while they are still the same person in the region it was
/// allocated in; otherwise (no allocation, abundant region, a merchant trip
/// or migration since phase 0.7, a reused slot) the current region's signal,
/// exactly as without the allocation.
#[inline]
pub fn food_for(pool: &AgentPool, slot: usize, regional: f32) -> f32 {
    match (pool.food_access.get(slot), pool.food_access_ids.get(slot), pool.food_access_regions.get(slot)) {
        (Some(&v), Some(&id), Some(&region))
            if !v.is_nan() && id == pool.ids[slot] && region == pool.regions[slot] => v,
        _ => regional,
    }
}

/// Water-fill `amount` over people with per-person caps, proportionally to
/// weights. Returns the amounts given and what could not be placed.
fn fill(amount: f64, weights: &[f64], caps: &[f64]) -> (Vec<f64>, f64) {
    let n = weights.len();
    let mut given = vec![0.0f64; n];
    let mut active: Vec<usize> = (0..n).filter(|&i| caps[i] > EPS).collect();
    let mut left = amount.max(0.0);
    let all_zero = active.iter().all(|&i| weights[i] <= 0.0);
    let w = |i: usize| if all_zero { 1.0 } else { weights[i].max(0.0) };
    while left > EPS && !active.is_empty() {
        let total: f64 = active.iter().map(|&i| w(i)).sum();
        if total <= 0.0 {
            break;
        }
        let mut saturated = Vec::new();
        for &i in &active {
            if left * w(i) / total >= caps[i] - given[i] - EPS {
                saturated.push(i);
            }
        }
        if saturated.is_empty() {
            for &i in &active {
                given[i] += left * w(i) / total;
            }
            left = 0.0;
            break;
        }
        for &i in &saturated {
            let room = caps[i] - given[i];
            given[i] = caps[i];
            left -= room;
        }
        active.retain(|i| !saturated.contains(i));
    }
    (given, left.max(0.0))
}

struct Person { slot: usize, id: u32, household: u32, child: bool }

/// Compute this tick's rations. Returns (ration by slot, NaN where the
/// regional signal applies), the matching stable ids, and the receipts.
pub fn allocate(pool: &AgentPool, regions: &[RegionState], cfg: &ProvisionConfig)
    -> (Vec<f32>, Vec<u32>, ProvisionFrame) {
    let n_slots = pool.ids.len();
    let mut access = vec![f32::NAN; n_slots];
    let mut access_ids = vec![0u32; n_slots];
    let id_slots = pool.build_id_slots();
    let alive_in = |id: u32, region: u16| -> Option<usize> {
        id_slots.get(id).filter(|&s| pool.is_alive(s) && pool.regions[s] == region)
    };
    // Adults' household keys first (spouse pairing), then children.
    let mut key = vec![u32::MAX; n_slots];
    for slot in 0..n_slots {
        if !pool.is_alive(slot) || pool.ages[slot] < AGE_ADULT {
            continue;
        }
        let id = pool.ids[slot];
        key[slot] = match crate::relationships::get_spouse_id(pool, slot)
            .and_then(|sid| alive_in(sid, pool.regions[slot]).map(|_| sid)) {
            Some(spouse) => id.min(spouse),
            None => id,
        };
    }
    let mut by_region: Vec<Vec<Person>> = (0..regions.len()).map(|_| Vec::new()).collect();
    for slot in 0..n_slots {
        if !pool.is_alive(slot) {
            continue;
        }
        let r = pool.regions[slot];
        if r as usize >= regions.len() {
            continue;
        }
        let child = pool.ages[slot] < AGE_ADULT;
        let household = if child {
            [pool.parent_id_0[slot], pool.parent_id_1[slot]].into_iter()
                .filter_map(|pid| alive_in(pid, r))
                .find(|&ps| pool.ages[ps] >= AGE_ADULT)
                .map(|ps| key[ps]).unwrap_or(pool.ids[slot])
        } else {
            key[slot]
        };
        by_region[r as usize].push(Person { slot, id: pool.ids[slot], household, child });
    }
    let mut frame = ProvisionFrame { source_turn: cfg.source_turn, regime: cfg.regime, ..Default::default() };
    for (r, people) in by_region.iter_mut().enumerate() {
        people.sort_unstable_by_key(|p| p.id);
        let fs = regions[r].food_sufficiency;
        let n2 = cfg.phase2_alive[r];
        let mut row = RegionProvision { region: r as u16, phase2_alive: n2, alive: people.len() as u32,
                                        sufficiency: fs, ..Default::default() };
        // Households and their per-capita adult wealth.
        let mut hh: BTreeMap<u32, (f64, u32)> = BTreeMap::new();
        for p in people.iter() {
            let e = hh.entry(p.household).or_insert((0.0, 0));
            if !p.child {
                e.0 += pool.wealth[p.slot].max(0.0) as f64;
            }
            e.1 += 1;
        }
        row.households = hh.len() as u32;
        let per_capita = |h: u32| { let (w, n) = hh[&h]; w / n.max(1) as f64 };
        // Households by means, poorest first (ties by key).
        let mut order: Vec<u32> = hh.keys().copied().collect();
        order.sort_by(|a, b| per_capita(*a).partial_cmp(&per_capita(*b)).unwrap().then(a.cmp(b)));
        let poorer: std::collections::HashSet<u32> = order.iter().take(order.len() / 2).copied().collect();
        let targeted_n = ((order.len() as f64) * cfg.target_share as f64).ceil() as usize;
        let targeted: std::collections::HashSet<u32> = order.iter().take(targeted_n).copied().collect();
        let n = people.len();
        let mut rations = vec![1.0f64; n];
        let mut is_targeted = vec![false; n];
        if fs < 1.0 && n > 0 {
            row.scarce = true;
            // The withdrawal fed N2 people; the share of anyone who died before
            // eating is recorded unallocated, never shared out or invented.
            let living = (n as u32).min(n2) as f64;
            row.rations_available = (fs.max(0.0) as f64) * n2 as f64;
            let total = (fs.max(0.0) as f64) * living;
            let pre = cfg.pre_release[r];
            let relief = if pre.is_nan() { 0.0 } else { ((fs - pre).max(0.0) as f64) * living };
            row.relief_available = relief;
            let caps = vec![1.0f64; n];
            let (given, left) = match cfg.regime {
                REGIME_FLOOR_MEANS => {
                    let floor = (cfg.floor as f64).min(total / n as f64);
                    let base = vec![floor; n];
                    let weights: Vec<f64> = people.iter().map(|p| per_capita(p.household) + MEANS_BASE_WEIGHT).collect();
                    let rest: Vec<f64> = caps.iter().map(|c| c - floor).collect();
                    let (extra, left) = fill(total - floor * n as f64, &weights, &rest);
                    (base.iter().zip(extra).map(|(b, e)| b + e).collect(), left)
                }
                REGIME_TARGETED_RELIEF => {
                    let market = (total - relief).max(0.0);
                    let (base, left_market) = fill(market, &vec![1.0; n], &caps);
                    for (i, p) in people.iter().enumerate() {
                        is_targeted[i] = targeted.contains(&p.household);
                    }
                    let room: Vec<f64> = (0..n).map(|i| if is_targeted[i] { caps[i] - base[i] } else { 0.0 }).collect();
                    let (to_targeted, left_relief) = fill(relief, &vec![1.0; n], &room);
                    row.relief_to_targeted = to_targeted.iter().sum();
                    let room2: Vec<f64> = (0..n).map(|i| caps[i] - base[i] - to_targeted[i]).collect();
                    let (to_rest, left_rest) = fill(left_relief, &vec![1.0; n], &room2);
                    ((0..n).map(|i| base[i] + to_targeted[i] + to_rest[i]).collect(), left_market + left_rest)
                }
                _ => fill(total, &vec![1.0; n], &caps),
            };
            rations = given;
            row.unallocated = left + (row.rations_available - total);
        } else if n > 0 {
            // No scarcity: everyone keeps the regional signal and a full ration.
            row.rations_available = n2 as f64;
            row.unallocated = (n2 as f64 - n as f64).max(0.0);
        }
        row.min_ration = if n > 0 { f32::INFINITY } else { 0.0 };
        for (i, p) in people.iter().enumerate() {
            let ration = rations[i].clamp(0.0, 1.0);
            row.allocated += ration;
            let short = 1.0 - ration;
            row.shortfall += short;
            if row.scarce && ration < cfg.floor as f64 - 1e-6 { row.below_floor += 1; }
            if ration >= 1.0 - 1e-6 { row.fully_fed += 1; }
            row.min_ration = row.min_ration.min(ration as f32);
            row.max_ration = row.max_ration.max(ration as f32);
            if poorer.contains(&p.household) {
                row.people_poorer_half += 1; row.shortfall_poorer_half += short;
            } else {
                row.people_richer_half += 1; row.shortfall_richer_half += short;
            }
            if p.child { row.children += 1; row.shortfall_children += short; }
            if row.scarce {
                access[p.slot] = ration as f32;
            }
            access_ids[p.slot] = p.id;
            if frame.sample.len() < MAX_SAMPLE {
                frame.sample.push((p.id, r as u16, p.household, ration as f32, is_targeted[i]));
            } else {
                frame.sample_dropped += 1;
            }
        }
        frame.regions.push(row);
    }
    (access, access_ids, frame)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn world(people: &[(u16, u16, f32)], fs: &[f32]) -> (AgentPool, Vec<RegionState>) {
        // (region, age, wealth)
        let mut pool = AgentPool::new(people.len());
        for &(region, age, wealth) in people {
            let slot = pool.spawn(region, 0, Occupation::Farmer, age, 0.5, 0.5, 0.5, 0, 1, 2, 0);
            pool.wealth[slot] = wealth;
        }
        let regions = fs.iter().enumerate().map(|(i, &f)| {
            let mut r = RegionState::new(i as u16);
            r.food_sufficiency = f;
            r
        }).collect();
        (pool, regions)
    }

    fn cfg(regime: u8, pre: Vec<f32>, n2: Vec<u32>) -> ProvisionConfig {
        ProvisionConfig { source_turn: 3, regime, floor: 0.5, target_share: 0.5, pre_release: pre, phase2_alive: n2 }
    }

    #[test]
    fn equal_reproduces_the_regional_signal_and_closes() {
        let (pool, regions) = world(&[(0, 30, 1.0), (0, 30, 9.0), (0, 30, 0.0), (1, 30, 0.0)], &[0.6, 1.4]);
        let (access, ids, frame) = allocate(&pool, &regions, &cfg(REGIME_EQUAL, vec![0.6, 1.4], vec![3, 1]));
        for slot in 0..3 {
            assert!((access[slot] - 0.6).abs() < 1e-6);
            assert_eq!(ids[slot], pool.ids[slot]);
            assert!((food_for_test(&access, &ids, &pool, slot, 0.6) - 0.6).abs() < 1e-6);
        }
        assert!(access[3].is_nan());   // abundant region keeps the regional signal
        let r = &frame.regions[0];
        assert!((r.allocated + r.unallocated - r.rations_available).abs() < 1e-9);
        assert!((r.shortfall - 1.2).abs() < 1e-6);
    }

    fn food_for_test(access: &[f32], ids: &[u32], pool: &AgentPool, slot: usize, regional: f32) -> f32 {
        if !access[slot].is_nan() && ids[slot] == pool.ids[slot] { access[slot] } else { regional }
    }

    #[test]
    fn floor_means_floors_everyone_and_favours_means_without_exceeding_a_ration() {
        let (pool, regions) = world(&[(0, 30, 0.0), (0, 30, 0.0), (0, 30, 100.0), (0, 30, 100.0)], &[0.7]);
        let (access, _, frame) = allocate(&pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.7], vec![4]));
        assert!(access.iter().all(|&a| a >= 0.5 - 1e-6 && a <= 1.0 + 1e-6));
        assert!(access[2] > access[0] && (access[2] - access[3]).abs() < 1e-6);
        let r = &frame.regions[0];
        assert!((r.allocated - 2.8).abs() < 1e-6 && r.unallocated.abs() < 1e-9);
        assert!(r.shortfall_poorer_half > r.shortfall_richer_half);
    }

    #[test]
    fn targeted_relief_reaches_the_poorest_first_and_conserves() {
        let (pool, regions) = world(&[(0, 30, 0.0), (0, 30, 0.0), (0, 30, 50.0), (0, 30, 50.0)], &[0.75]);
        // Market 0.5 rations each (pre 0.5), relief 0.25 * 4 = 1.0 ration.
        let (access, _, frame) = allocate(&pool, &regions, &cfg(REGIME_TARGETED_RELIEF, vec![0.5], vec![4]));
        assert!((access[0] - 1.0).abs() < 1e-6 && (access[1] - 1.0).abs() < 1e-6);
        assert!((access[2] - 0.5).abs() < 1e-6 && (access[3] - 0.5).abs() < 1e-6);
        let r = &frame.regions[0];
        assert!((r.relief_to_targeted - 1.0).abs() < 1e-6);
        assert!((r.allocated + r.unallocated - 3.0).abs() < 1e-9);
    }

    #[test]
    fn deaths_after_phase2_leave_rations_unallocated_and_children_join_parents() {
        let (mut pool, regions) = world(&[(0, 30, 10.0), (0, 5, 0.0), (0, 30, 0.0)], &[0.5]);
        pool.parent_id_0[1] = pool.ids[0];
        pool.kill(2);
        let (access, _, frame) = allocate(&pool, &regions, &cfg(REGIME_EQUAL, vec![0.5], vec![3]));
        let r = &frame.regions[0];
        assert_eq!((r.alive, r.households, r.children), (2, 1, 1));
        // The survivors eat the regional ration; the dead's share is unallocated.
        assert!((access[0] - 0.5).abs() < 1e-6 && (access[1] - 0.5).abs() < 1e-6);
        assert!((r.unallocated - 0.5).abs() < 1e-9 && (r.allocated - 1.0).abs() < 1e-6);
        assert!((r.allocated + r.unallocated - r.rations_available).abs() < 1e-9);
    }

    #[test]
    fn invalid_configs_are_refused() {
        let mut c = cfg(REGIME_EQUAL, vec![0.5], vec![1]);
        assert!(validate(&c, 1).is_ok());
        c.regime = 9; assert!(validate(&c, 1).is_err());
        c = cfg(REGIME_EQUAL, vec![0.5], vec![1]); c.floor = 0.0; assert!(validate(&c, 1).is_err());
        c = cfg(REGIME_EQUAL, vec![-1.0], vec![1]); assert!(validate(&c, 1).is_err());
        c = cfg(REGIME_EQUAL, vec![0.5], vec![1]); assert!(validate(&c, 2).is_err());
    }
}
