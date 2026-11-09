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
//!
//! Livelihoods L6b household retail ([`retail`], option R, default off)
//! extends the same step in its pilot regions: people eat free food, their
//! households' own titled food and food bought from owners by stable id, in
//! a fair-share round to `min(1, sufficiency)` and an open round to one
//! ration; payments are settled in the tick
//! (`wealth_transfer::settle_food_purchases`). Its install, frame and the
//! farm income replacement it pairs with are one-tick transients.
use std::collections::BTreeMap;

use crate::agent::AGE_ADULT;
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Total order on `f64` keys that agrees with `partial_cmp` on every non-NaN
/// pair: adding `+0.0` maps `-0.0` to `+0.0`, so the two zeros stay `Equal`
/// and a tie-break key still applies; NaN gets a fixed place instead of a
/// panic or an inconsistent sort.
fn cmp_f64(a: f64, b: f64) -> std::cmp::Ordering {
    (a + 0.0).total_cmp(&(b + 0.0))
}

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
    if let Some(food) = pool.army_food(slot) { return food; }
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

/// The living of each region, ascending id, with their derived household
/// keys (see the module docs). Shared by L2 and household retail.
fn people_by_region(pool: &AgentPool, n_regions: usize) -> Vec<Vec<Person>> {
    let n_slots = pool.ids.len();
    let id_slots = pool.build_id_slots();
    let alive_in = |id: u32, region: u16| -> Option<usize> {
        id_slots.get(id).filter(|&s| pool.is_alive(s) && !pool.enlisted(s) && pool.regions[s] == region)
    };
    // Adults' household keys first (spouse pairing), then children.
    let mut key = vec![u32::MAX; n_slots];
    for slot in 0..n_slots {
        if !pool.is_alive(slot) || pool.enlisted(slot) || pool.ages[slot] < AGE_ADULT {
            continue;
        }
        let id = pool.ids[slot];
        key[slot] = match crate::relationships::get_spouse_id(pool, slot)
            .and_then(|sid| alive_in(sid, pool.regions[slot]).map(|_| sid)) {
            Some(spouse) => id.min(spouse),
            None => id,
        };
    }
    let mut by_region: Vec<Vec<Person>> = (0..n_regions).map(|_| Vec::new()).collect();
    for slot in 0..n_slots {
        if !pool.is_alive(slot) || pool.enlisted(slot) {
            continue;
        }
        let r = pool.regions[slot];
        if r as usize >= n_regions {
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
    for people in by_region.iter_mut() {
        people.sort_unstable_by_key(|p| p.id);
    }
    by_region
}

/// Compute this tick's rations. Returns (ration by slot, NaN where the
/// regional signal applies), the matching stable ids, and the receipts.
pub fn allocate(pool: &AgentPool, regions: &[RegionState], cfg: &ProvisionConfig)
    -> (Vec<f32>, Vec<u32>, ProvisionFrame) {
    let n_slots = pool.ids.len();
    let mut access = vec![f32::NAN; n_slots];
    let mut access_ids = vec![0u32; n_slots];
    let mut by_region = people_by_region(pool, regions.len());
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
        order.sort_by(|a, b| cmp_f64(per_capita(*a), per_capita(*b)).then(a.cmp(b)));
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

// ---------------------------------------------------------------------------
// Livelihoods L6b: household food retail (option R), default off.
// ---------------------------------------------------------------------------

pub const RETAIL_MODE_RETAIL: u8 = 0;
pub const RETAIL_MODE_NO_RELIEF: u8 = 1;
pub const RETAIL_MODE_FREE_EXCHANGE: u8 = 2;
/// Person sample statuses, in declaration order (append only).
pub const RETAIL_STATUS_FED: u8 = 0;
pub const RETAIL_STATUS_PRICED_OUT: u8 = 1;
pub const RETAIL_STATUS_OFFER_SHORT: u8 = 2;
/// Below the fair share with cash in hand while a dead owner's claim was
/// withheld in the region (the one source of an unreachable fair share once
/// sufficiency counts exactly the food offered).
pub const RETAIL_STATUS_WITHHELD_DEAD: u8 = 3;

/// Within one milli-food of a full ration (the fed tolerance): a full ration.
#[inline]
fn full_ration(ration: f64, milli_food_per_ration: f64) -> bool {
    (1.0 - ration) * milli_food_per_ration < 1.0 + 1e-6
}
/// Most milli-units one ration may cost, milli-food one claim may hold, and
/// claims one install may carry.
pub const RETAIL_MAX_PRICE_MILLI: i64 = 1_000_000_000;
pub const RETAIL_MAX_CLAIM_MILLI: i64 = 1_000_000_000_000;
pub const RETAIL_MAX_CLAIMS: usize = 1 << 20;
pub const RETAIL_MAX_FREE_RATIONS: f64 = 1e9;

/// One pilot region's offer: price in milli-units per ration and free
/// rations (the commons draw-down and the granary release, for the Phase 2
/// population).
#[derive(Clone, Debug, PartialEq)]
pub struct RetailOffer {
    pub region: u16,
    pub price_milli: i64,
    pub free_rations: f64,
}

/// A one-tick household retail install, taken at phase 0.7 right after the
/// L2 allocation it extends.
#[derive(Clone, Debug, PartialEq)]
pub struct RetailConfig {
    pub source_turn: u32,
    pub mode: u8,
    /// Milli-food in one ration: the economy's per-capita food demand x 1000
    /// (500 at the default 0.5: 1000 milli-food = one food unit = two rations).
    pub milli_food_per_ration: i64,
    /// Pilot regions, ascending, at most one offer each.
    pub regions: Vec<RetailOffer>,
    /// (owner stable id, pilot region, milli-food), one per (owner, region).
    pub claims: Vec<(u32, u16, i64)>,
}

impl RetailConfig {
    /// Validate an install completely before anything changes.
    pub fn new(source_turn: u32, mode: u8, milli_food_per_ration: i64, regions: Vec<(u16, i64, f64)>,
               claims: Vec<(u32, u16, i64)>, num_regions: usize) -> Result<Self, &'static str> {
        if mode > RETAIL_MODE_FREE_EXCHANGE {
            return Err("unknown household retail mode");
        }
        if milli_food_per_ration < 1 {
            return Err("household retail needs a positive per-capita food ration");
        }
        let mut pilot = vec![false; num_regions];
        for &(region, price, free) in &regions {
            let Some(seen) = pilot.get_mut(region as usize) else { return Err("household retail region out of range") };
            if *seen {
                return Err("duplicate household retail region");
            }
            *seen = true;
            if !(0..=RETAIL_MAX_PRICE_MILLI).contains(&price) {
                return Err("household retail price out of range");
            }
            if !(free.is_finite() && (0.0..=RETAIL_MAX_FREE_RATIONS).contains(&free)) {
                return Err("household retail free rations must be finite and nonnegative");
            }
        }
        if claims.len() > RETAIL_MAX_CLAIMS {
            return Err("too many household retail claims");
        }
        let mut keys = std::collections::HashSet::with_capacity(claims.len());
        for &(owner, region, milli) in &claims {
            if owner == 0 {
                return Err("household retail claim names no agent");
            }
            if !pilot.get(region as usize).copied().unwrap_or(false) {
                return Err("household retail claim outside the pilot regions");
            }
            if !(0..=RETAIL_MAX_CLAIM_MILLI).contains(&milli) {
                return Err("household retail claim out of range");
            }
            if !keys.insert((owner, region)) {
                return Err("duplicate household retail claim");
            }
        }
        let mut regions: Vec<RetailOffer> = regions.into_iter()
            .map(|(region, price_milli, free_rations)| RetailOffer { region, price_milli, free_rations }).collect();
        regions.sort_unstable_by_key(|o| o.region);
        Ok(Self { source_turn, mode, milli_food_per_ration, regions, claims })
    }
}

/// One pilot region's receipt row; [`RETAIL_REGION_COLUMNS`] names
/// [`RetailRegionRow::row`]. Food in milli-food, money in milli-units,
/// rations as fractions of one ration.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct RetailRegionRow {
    pub region: u16,
    pub mode: u8,
    pub phase2_alive: u32,
    pub persons: u32,
    pub households: u32,
    pub children: u32,
    pub sufficiency: f32,
    pub fair_share: f64,
    pub price_quoted_milli: i64,
    pub price_milli: i64,
    pub milli_food_per_ration: i64,
    pub free_rations: f64,
    pub free_living: f64,
    pub free_given: f64,
    pub free_unallocated: f64,
    pub free_to_priority: f64,
    pub priority_households: u32,
    pub claims: u32,
    pub present_claims: u32,
    /// Claims (and their milli-food) whose owner was not alive at phase 0.7:
    /// neither offered nor eaten, left whole for the owner's heirs.
    pub withheld_dead_claims: u32,
    pub offered_milli: i64,
    pub withheld_dead_milli: i64,
    pub own_eaten_fair_milli: i64,
    pub own_eaten_open_milli: i64,
    pub sold_fair_milli: i64,
    pub sold_open_milli: i64,
    pub unsold_milli: i64,
    pub demand_fair_milli: i64,
    pub demand_open_milli: i64,
    pub buying_households: u32,
    pub sellers: u32,
    pub paid_milli: i64,
    pub credited_milli: i64,
    pub refunded_milli: i64,
    pub refused_ceiling_milli: i64,
    pub rations: f64,
    pub fed_fair: u32,
    pub full_ration: u32,
    pub min_ration: f64,
    pub max_ration: f64,
    pub deficit: f64,
    pub priced_out_households: u32,
    pub priced_out_persons: u32,
    pub priced_out_children: u32,
    pub priced_out_deficit: f64,
    pub offer_short_households: u32,
    pub offer_short_persons: u32,
    pub offer_short_children: u32,
    pub offer_short_deficit: f64,
    pub withheld_dead_households: u32,
    pub withheld_dead_persons: u32,
    pub withheld_dead_children: u32,
    pub withheld_dead_deficit: f64,
}

/// Column names of [`RetailRegionRow::row`], in order: food in milli-food,
/// money in milli-units (`_milli`), rations as fractions of one ration.
/// `own_eaten_milli` and `sold_milli` are the two rounds together.
pub const RETAIL_REGION_COLUMNS: [&str; 55] = [
    "region", "mode", "phase2_alive", "persons", "households", "children", "sufficiency", "fair_share",
    "price_quoted_milli", "price_milli", "milli_food_per_ration", "free_rations", "free_living", "free_given",
    "free_unallocated", "free_to_priority", "priority_households", "claims", "present_claims",
    "withheld_dead_claims", "offered_milli", "withheld_dead_milli", "own_eaten_milli", "own_eaten_fair_milli", "own_eaten_open_milli", "sold_milli", "sold_fair_milli",
    "sold_open_milli", "unsold_milli", "demand_fair_milli", "demand_open_milli", "buying_households", "sellers",
    "paid_milli", "credited_milli", "refunded_milli", "refused_ceiling_milli", "rations", "fed_fair", "full_ration", "min_ration", "max_ration", "deficit", "priced_out_households",
    "priced_out_persons", "priced_out_children", "priced_out_deficit", "offer_short_households",
    "offer_short_persons", "offer_short_children", "offer_short_deficit", "withheld_dead_households",
    "withheld_dead_persons", "withheld_dead_children", "withheld_dead_deficit",
];

impl RetailRegionRow {
    pub fn row(&self) -> Vec<f64> {
        vec![
            self.region as f64, self.mode as f64, self.phase2_alive as f64, self.persons as f64,
            self.households as f64, self.children as f64, self.sufficiency as f64, self.fair_share,
            self.price_quoted_milli as f64, self.price_milli as f64, self.milli_food_per_ration as f64,
            self.free_rations, self.free_living, self.free_given, self.free_unallocated, self.free_to_priority,
            self.priority_households as f64, self.claims as f64, self.present_claims as f64,
            self.withheld_dead_claims as f64, self.offered_milli as f64, self.withheld_dead_milli as f64,
            (self.own_eaten_fair_milli + self.own_eaten_open_milli) as f64,
            self.own_eaten_fair_milli as f64, self.own_eaten_open_milli as f64,
            (self.sold_fair_milli + self.sold_open_milli) as f64, self.sold_fair_milli as f64,
            self.sold_open_milli as f64, self.unsold_milli as f64, self.demand_fair_milli as f64,
            self.demand_open_milli as f64, self.buying_households as f64, self.sellers as f64,
            self.paid_milli as f64, self.credited_milli as f64, self.refunded_milli as f64,
            self.refused_ceiling_milli as f64, self.rations,
            self.fed_fair as f64, self.full_ration as f64, self.min_ration, self.max_ration, self.deficit,
            self.priced_out_households as f64, self.priced_out_persons as f64, self.priced_out_children as f64,
            self.priced_out_deficit, self.offer_short_households as f64, self.offer_short_persons as f64,
            self.offer_short_children as f64, self.offer_short_deficit, self.withheld_dead_households as f64,
            self.withheld_dead_persons as f64, self.withheld_dead_children as f64, self.withheld_dead_deficit,
        ]
    }
}

/// The tick's household retail receipts, taken once by Python.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct RetailFrame {
    pub source_turn: u32,
    pub mode: u8,
    pub regions: Vec<RetailRegionRow>,
    /// (owner, region, own-eaten milli-food, sold milli-food) for every
    /// installed claim, by (region, owner).
    pub claims: Vec<(u32, u16, i64, i64)>,
    /// (stable id, paid, credited, refunded) milli-units, ascending id.
    pub money: Vec<(u32, i64, i64, i64)>,
    /// (id, region, household key, ration, fair share, status), people not
    /// fed to their fair share first, then the fed, each by (region, id).
    pub sample: Vec<(u32, u16, u32, f32, f32, u8)>,
    pub sample_dropped: usize,
}

/// One household of a pilot region.
struct RetailHousehold {
    key: u32,
    /// Person indices: children (ascending id), then adults (ascending id).
    members: Vec<usize>,
    /// (stable id, wealth in whole milli): its adults, or with no adult its members.
    payers: Vec<(u32, i64)>,
    /// Milli-food the payers' cash buys at the price (`i64::MAX` when free).
    afford: i64,
    /// Indices of claims whose owner is present in the household.
    claims: Vec<usize>,
    bought: i64,
    /// Whether its fair-share purchases were limited by cash (priced out).
    cash_limited: bool,
}

/// What one pilot region's rounds decided before the money is settled.
struct RetailRegionWork {
    row: RetailRegionRow,
    purchase: crate::wealth_transfer::FoodPurchases,
    /// (slot, id, household key, child, ration, status)
    people: Vec<(usize, u32, u32, bool, f64, u8)>,
}

/// Eat the household's present claims, children first, up to `cap` per
/// member (milli-food, counting what each already ate or bought); the claims
/// are debited pro rata to what is left of them (largest remainder, ties by
/// owner id). Returns what was eaten.
fn eat_own(h: &RetailHousehold, cap: &[i64], own: &mut [i64], bought: &[i64], claims: &[(u32, u16, i64)],
           left: &mut [i64], eaten: &mut [i64]) -> i64 {
    let have: i64 = h.claims.iter().map(|&c| left[c]).sum();
    let mut give = have.min(h.members.iter().map(|&m| (cap[m] - own[m] - bought[m]).max(0)).sum());
    let eat = give;
    for &m in &h.members {
        let take = (cap[m] - own[m] - bought[m]).max(0).min(give);
        own[m] += take;
        give -= take;
    }
    let weights: Vec<(u64, i64)> = h.claims.iter().map(|&c| (claims[c].0 as u64, left[c])).collect();
    for (&c, share) in h.claims.iter().zip(crate::wealth_transfer::split_largest_remainder(eat, &weights)) {
        left[c] -= share;
        eaten[c] += share;
    }
    eat
}

/// One purchase round up to `cap` per member: each household's demand is
/// its members' gap, limited by what its cash still buys; a short offer is
/// split pro rata to demand (largest remainder, ties by household key),
/// otherwise the sellers sell pro rata to their remaining claims (ties by
/// owner id). Bought food goes to children first. Returns (demand, sold).
#[allow(clippy::too_many_arguments)]
fn buy_round(hhs: &mut [RetailHousehold], cap: &[i64], own: &[i64], bought: &mut [i64], region_claims: &[usize],
             claims: &[(u32, u16, i64)], left: &mut [i64], sold: &mut [i64], fair: bool) -> (i64, i64) {
    let demand: Vec<i64> = hhs.iter_mut().map(|h| {
        let need: i64 = h.members.iter().map(|&m| (cap[m] - own[m] - bought[m]).max(0)).sum();
        let can = (h.afford - h.bought).max(0);
        if fair && need > can { h.cash_limited = true; }
        need.min(can)
    }).collect();
    let total: i64 = demand.iter().sum();
    let offer: i64 = region_claims.iter().map(|&c| left[c]).sum();
    if total == 0 || offer == 0 {
        return (total, 0);
    }
    let got = if total <= offer {
        demand
    } else {
        let weights: Vec<(u64, i64)> = hhs.iter().zip(&demand).map(|(h, &d)| (h.key as u64, d)).collect();
        crate::wealth_transfer::split_largest_remainder(offer, &weights)
    };
    let sold_now: i64 = got.iter().sum();
    let weights: Vec<(u64, i64)> = region_claims.iter().map(|&c| (claims[c].0 as u64, left[c])).collect();
    for (&c, share) in region_claims.iter().zip(crate::wealth_transfer::split_largest_remainder(sold_now, &weights)) {
        left[c] -= share;
        sold[c] += share;
    }
    for (h, &q) in hhs.iter_mut().zip(&got) {
        let mut give = q;
        for &m in &h.members {
            let take = (cap[m] - own[m] - bought[m]).max(0).min(give);
            bought[m] += take;
            give -= take;
        }
        h.bought += q;
    }
    (total, sold_now)
}

/// Checks the tick makes on the pending retail installs before anything
/// changes: purchases are settled once per turn (the turn's `food_purchase`
/// key must be unused unless the mode pays nothing), and the farm income
/// replacement covers only pilot regions of the retail install (no region
/// without one), except under `free_exchange`.
pub fn check_retail_tick(pool: &AgentPool, turn: u32) -> Result<(), &'static str> {
    if let Some(cfg) = &pool.retail_config {
        if cfg.mode != RETAIL_MODE_FREE_EXCHANGE && pool.wealth_transfer_log.iter()
            .any(|&(t, p, b)| p == crate::wealth_transfer::PURPOSE_FOOD_PURCHASE && b == 0 && t >= turn) {
            return Err("household food purchases already settled for this turn");
        }
    }
    if let Some(income) = &pool.retail_income {
        let free_exchange = pool.retail_config.as_ref().is_some_and(|c| c.mode == RETAIL_MODE_FREE_EXCHANGE);
        let pilot = |r: usize| pool.retail_config.as_ref()
            .is_some_and(|c| c.regions.iter().any(|o| o.region as usize == r));
        if !free_exchange && income.regions.iter().enumerate().any(|(r, &on)| on && !pilot(r)) {
            return Err("retail income regions must be pilot regions of the retail install");
        }
    }
    Ok(())
}

/// Household retail at phase 0.7, right after the L2 allocation `l2` it
/// extends: in each pilot region of `cfg` it allocates the free pool, runs
/// the fair-share round (own food, then purchases) and the open round to one
/// ration, writes every pilot person's ration into `food_access` and
/// settles the purchases (`wealth_transfer::settle_food_purchases`). People
/// outside the pilot regions keep L2's rations. Returns the frame.
///
/// Per pilot region (households as L2 derives them, people by id; `cf =
/// min(1, regional sufficiency)`; rations in milli-food, a ration being
/// `milli_food_per_ration`):
///
/// 1. The free pool: the living's share of the free rations (the share of
///    people who died after Phase 2 is unallocated, as in L2). Mode 0
///    (`retail`) and 2 (`free_exchange`, price 0): first to the members of
///    means-tested households, those whose gap to `cf` after their own food
///    (children first) exceeds what their cash buys at the price, each up to
///    `cf` counting that own food; the rest water-filled to `cf` the same
///    way, then to one ration. Mode 1 (`no_relief`): L2's regime on the free
///    pool, no means test.
/// 2. Fair-share round, own food: each household eats its present members'
///    claims, children first, up to `cf` per member.
/// 3. Fair-share round, purchases (see [`buy_round`]), limited by cash over
///    price; at price 0 nothing limits them.
/// 4. Open round: own food, then purchases, up to one ration.
/// 5. Rations: free plus own plus bought. A person within one milli-food of a
///    full ration (the fed tolerance) has a full ration and reads the regional
///    signal where the region is not short (abundance kept), 1.0 otherwise;
///    anyone below reads their ration. Status: fed within one milli-food of
///    `cf`; else priced out when the household's fair-share purchases were
///    cash-limited; else withheld_dead when a dead owner's claim was withheld
///    in the region; else offer short.
///
/// Phase 2 counts in sufficiency exactly the owned food offered here (the
/// carried stock decays and is capped before sufficiency; this turn's title
/// whole), so with nothing withheld the free and offered food together cover
/// `cf` for everyone alive.
///
/// A dead buyer is not among the people. A claim whose owner is no longer
/// alive (died after Phase 2; a reused slot is another person by the stable-id
/// guard) is withheld: neither offered nor eaten, left whole for Python to
/// pass to the heirs, and counted in `withheld_dead_milli` (part of
/// `unsold_milli`). A living owner's claim away from home is only for sale. Each household
/// pays `ceil(bought x price / ration)` milli-units, which its cash covers.
/// Refused, with nothing changed, when this turn's purchases were already
/// settled (the `food_purchase` key of the turn is consumed).
pub fn retail(pool: &mut AgentPool, regions: &[RegionState], l2: &ProvisionConfig, cfg: &RetailConfig,
              turn: u32) -> Result<RetailFrame, &'static str> {
    let rf = cfg.milli_food_per_ration as f64;
    let n_claims = cfg.claims.len();
    let mut left: Vec<i64> = cfg.claims.iter().map(|c| c.2).collect();
    let mut eaten = vec![0i64; n_claims];
    let mut sold = vec![0i64; n_claims];
    let mut by_claim_region: BTreeMap<u16, Vec<usize>> = BTreeMap::new();
    for (i, c) in cfg.claims.iter().enumerate() {
        by_claim_region.entry(c.1).or_default().push(i);
    }
    for list in by_claim_region.values_mut() {
        list.sort_unstable_by_key(|&i| cfg.claims[i].0);
    }
    let mut works: Vec<RetailRegionWork> = Vec::with_capacity(cfg.regions.len());
    {
        let by_region = people_by_region(pool, regions.len());
        let id_slots = pool.build_id_slots();
        for offer in &cfg.regions {
            let r = offer.region as usize;
            let people = &by_region[r];
            let region_claims: &[usize] = by_claim_region.get(&offer.region).map_or(&[], |v| v.as_slice());
            let n = people.len();
            let fs = regions[r].food_sufficiency;
            let cf = if fs.is_finite() { (fs as f64).clamp(0.0, 1.0) } else { 0.0 };
            let price = if cfg.mode == RETAIL_MODE_FREE_EXCHANGE { 0 } else { offer.price_milli };
            let n2 = l2.phase2_alive.get(r).copied().unwrap_or(0);
            let living = (n as u32).min(n2) as f64;
            let free_living = if n2 > 0 { offer.free_rations * living / n2 as f64 } else { 0.0 };
            let mut row = RetailRegionRow {
                region: offer.region, mode: cfg.mode, phase2_alive: n2, persons: n as u32,
                children: people.iter().filter(|p| p.child).count() as u32, sufficiency: fs, fair_share: cf,
                price_quoted_milli: offer.price_milli, price_milli: price, milli_food_per_ration: cfg.milli_food_per_ration,
                free_rations: offer.free_rations, free_living, claims: region_claims.len() as u32,
                offered_milli: region_claims.iter().map(|&c| left[c]).sum(), ..Default::default()
            };
            // Households, children first within each, and their payers' cash.
            let index: std::collections::HashMap<usize, usize> =
                people.iter().enumerate().map(|(i, p)| (p.slot, i)).collect();
            // Households in key order (the tie order of a short offer).
            let mut key_index: BTreeMap<u32, usize> = people.iter().map(|p| (p.household, 0)).collect();
            for (i, v) in key_index.values_mut().enumerate() { *v = i; }
            let hh_of: Vec<usize> = people.iter().map(|p| key_index[&p.household]).collect();
            let mut hhs: Vec<RetailHousehold> = key_index.keys().map(|&key| RetailHousehold {
                key, members: Vec::new(), payers: Vec::new(), afford: 0, claims: Vec::new(), bought: 0,
                cash_limited: false }).collect();
            for pass_children in [true, false] {
                for (i, p) in people.iter().enumerate() {
                    if p.child == pass_children { hhs[hh_of[i]].members.push(i); }
                }
            }
            for h in hhs.iter_mut() {
                let adults: Vec<usize> = h.members.iter().copied().filter(|&m| !people[m].child).collect();
                let payers = if adults.is_empty() { h.members.clone() } else { adults };
                let mut payers: Vec<(u32, i64)> = payers.iter()
                    .map(|&m| (people[m].id, crate::wealth_transfer::floor_millis(pool.wealth[people[m].slot]))).collect();
                payers.sort_unstable_by_key(|p| p.0);
                let cash: i64 = payers.iter().map(|p| p.1).sum();
                h.afford = if price == 0 { i64::MAX } else {
                    ((cash as i128 * cfg.milli_food_per_ration as i128) / price as i128).min(i64::MAX as i128 / 4) as i64
                };
                h.payers = payers;
            }
            // A claim whose owner is no longer alive (died after Phase 2, or a
            // reused slot: stable-id guard) is withheld whole for the heirs.
            let mut on_sale: Vec<usize> = Vec::with_capacity(region_claims.len());
            for &c in region_claims {
                let owner = cfg.claims[c].0;
                let Some(slot) = id_slots.get(owner).filter(|&s| pool.is_alive(s) && pool.ids[s] == owner) else {
                    row.withheld_dead_claims += 1;
                    row.withheld_dead_milli += left[c];
                    continue;
                };
                on_sale.push(c);
                if pool.regions[slot] == offer.region {
                    if let Some(&i) = index.get(&slot) {
                        hhs[hh_of[i]].claims.push(c);
                        row.present_claims += 1;
                    }
                }
            }
            let region_claims_all = region_claims;
            let region_claims: &[usize] = &on_sale;
            row.households = hhs.len() as u32;
            // 1. The free pool.
            let ones = vec![1.0f64; n];
            let fair_cap = ((cf * rf) + 1e-6).floor() as i64;
            let mut free = vec![0.0f64; n];
            // What the pool could not place is unallocated with the dead's share.
            let _unplaced = if n == 0 {
                free_living
            } else if cfg.mode == RETAIL_MODE_NO_RELIEF {
                let caps = vec![1.0f64; n];
                let per_capita = |h: &RetailHousehold| {
                    let w: f64 = h.members.iter().filter(|&&m| !people[m].child)
                        .map(|&m| pool.wealth[people[m].slot].max(0.0) as f64).sum();
                    w / h.members.len().max(1) as f64
                };
                match l2.regime {
                    REGIME_FLOOR_MEANS => {
                        let floor = (l2.floor as f64).min(free_living / n as f64);
                        let weights: Vec<f64> = (0..n).map(|i| per_capita(&hhs[hh_of[i]]) + MEANS_BASE_WEIGHT).collect();
                        let rest: Vec<f64> = caps.iter().map(|c| c - floor).collect();
                        let (extra, unplaced) = fill(free_living - floor * n as f64, &weights, &rest);
                        for i in 0..n { free[i] = floor + extra[i]; }
                        unplaced
                    }
                    REGIME_TARGETED_RELIEF => {
                        let pre = l2.pre_release.get(r).copied().unwrap_or(f32::NAN);
                        let relief = if pre.is_nan() { 0.0 } else {
                            (((fs - pre).max(0.0) as f64) * living).min(free_living)
                        };
                        let (base, left_market) = fill((free_living - relief).max(0.0), &ones, &caps);
                        let mut order: Vec<usize> = (0..hhs.len()).collect();
                        order.sort_by(|&a, &b| cmp_f64(per_capita(&hhs[a]), per_capita(&hhs[b]))
                            .then(hhs[a].key.cmp(&hhs[b].key)));
                        let targeted_n = ((order.len() as f64) * l2.target_share as f64).ceil() as usize;
                        let targeted: std::collections::HashSet<usize> = order.iter().take(targeted_n).copied().collect();
                        let room: Vec<f64> = (0..n).map(|i| if targeted.contains(&hh_of[i]) { caps[i] - base[i] } else { 0.0 }).collect();
                        let (to_targeted, left_relief) = fill(relief, &ones, &room);
                        let room2: Vec<f64> = (0..n).map(|i| caps[i] - base[i] - to_targeted[i]).collect();
                        let (to_rest, left_rest) = fill(left_relief, &ones, &room2);
                        for i in 0..n { free[i] = base[i] + to_targeted[i] + to_rest[i]; }
                        left_market + left_rest
                    }
                    _ => {
                        let (given, unplaced) = fill(free_living, &ones, &caps);
                        free = given;
                        unplaced
                    }
                }
            } else {
                // Means test on the household's own food at the fair share.
                let mut own_proj = vec![0i64; n];
                let mut priority = vec![false; hhs.len()];
                for (h, hh) in hhs.iter().enumerate() {
                    let mut have: i64 = hh.claims.iter().map(|&c| left[c]).sum();
                    for &m in &hh.members {
                        own_proj[m] = have.min(fair_cap);
                        have -= own_proj[m];
                    }
                    let gap: i64 = hh.members.iter().map(|&m| fair_cap - own_proj[m]).sum();
                    priority[h] = gap > hh.afford;
                }
                row.priority_households = priority.iter().filter(|&&p| p).count() as u32;
                let proj = |i: usize| own_proj[i] as f64 / rf;
                let caps_a: Vec<f64> = (0..n).map(|i| if priority[hh_of[i]] { (cf - proj(i)).max(0.0) } else { 0.0 }).collect();
                let (a, rest) = fill(free_living, &ones, &caps_a);
                let caps_b: Vec<f64> = (0..n).map(|i| (cf - proj(i) - a[i]).max(0.0)).collect();
                let (b, rest) = fill(rest, &ones, &caps_b);
                let caps_c: Vec<f64> = (0..n).map(|i| (1.0 - proj(i) - a[i] - b[i]).max(0.0)).collect();
                let (c, rest) = fill(rest, &ones, &caps_c);
                row.free_to_priority = a.iter().sum();
                for i in 0..n { free[i] = a[i] + b[i] + c[i]; }
                rest
            };
            row.free_given = free.iter().sum();
            row.free_unallocated = offer.free_rations - row.free_given;
            // 2-4. The fair-share round and the open round.
            let cap_fair: Vec<i64> = free.iter().map(|&f| (((cf - f) * rf) + 1e-6).floor().max(0.0) as i64).collect();
            let cap_open: Vec<i64> = free.iter().map(|&f| (((1.0 - f) * rf) + 1e-6).floor().max(0.0) as i64).collect();
            let mut own = vec![0i64; n];
            let mut bought = vec![0i64; n];
            for h in &hhs {
                row.own_eaten_fair_milli += eat_own(h, &cap_fair, &mut own, &bought, &cfg.claims, &mut left, &mut eaten);
            }
            let (demand, got) = buy_round(&mut hhs, &cap_fair, &own, &mut bought, region_claims, &cfg.claims,
                                          &mut left, &mut sold, true);
            row.demand_fair_milli = demand;
            row.sold_fair_milli = got;
            for h in &hhs {
                row.own_eaten_open_milli += eat_own(h, &cap_open, &mut own, &bought, &cfg.claims, &mut left, &mut eaten);
            }
            let (demand, got) = buy_round(&mut hhs, &cap_open, &own, &mut bought, region_claims, &cfg.claims,
                                          &mut left, &mut sold, false);
            row.demand_open_milli = demand;
            row.sold_open_milli = got;
            row.unsold_milli = region_claims_all.iter().map(|&c| left[c]).sum();
            row.sellers = region_claims.iter().filter(|&&c| sold[c] > 0).count() as u32;
            row.buying_households = hhs.iter().filter(|h| h.bought > 0).count() as u32;
            // Payments (settled after every region is decided).
            let mut purchase = crate::wealth_transfer::FoodPurchases::default();
            if price > 0 {
                for h in &hhs {
                    if h.bought > 0 {
                        let amount = ((h.bought as i128 * price as i128 + cfg.milli_food_per_ration as i128 - 1)
                            / cfg.milli_food_per_ration as i128) as i64;
                        purchase.households.push((h.payers.clone(), amount));
                    }
                }
                purchase.sales = region_claims.iter().filter(|&&c| sold[c] > 0)
                    .map(|&c| (cfg.claims[c].0, sold[c])).collect();
            }
            // 5. Rations and statuses.
            let mut out = Vec::with_capacity(n);
            row.min_ration = if n > 0 { f64::INFINITY } else { 0.0 };
            let mut priced_out_hh = std::collections::BTreeSet::new();
            let mut offer_short_hh = std::collections::BTreeSet::new();
            let mut withheld_hh = std::collections::BTreeSet::new();
            for (i, p) in people.iter().enumerate() {
                let ration = (free[i] + (own[i] + bought[i]) as f64 / rf).clamp(0.0, 1.0);
                let short = (cf - ration).max(0.0);
                let h = &hhs[hh_of[i]];
                let status = if short * rf < 1.0 + 1e-6 {
                    RETAIL_STATUS_FED
                } else if h.cash_limited {
                    RETAIL_STATUS_PRICED_OUT
                } else if row.withheld_dead_milli > 0 {
                    RETAIL_STATUS_WITHHELD_DEAD
                } else {
                    RETAIL_STATUS_OFFER_SHORT
                };
                row.rations += ration;
                row.min_ration = row.min_ration.min(ration);
                row.max_ration = row.max_ration.max(ration);
                if full_ration(ration, rf) { row.full_ration += 1; }
                match status {
                    RETAIL_STATUS_FED => row.fed_fair += 1,
                    RETAIL_STATUS_PRICED_OUT => {
                        row.priced_out_persons += 1;
                        row.priced_out_children += p.child as u32;
                        row.priced_out_deficit += short;
                        priced_out_hh.insert(h.key);
                    }
                    RETAIL_STATUS_WITHHELD_DEAD => {
                        row.withheld_dead_persons += 1;
                        row.withheld_dead_children += p.child as u32;
                        row.withheld_dead_deficit += short;
                        withheld_hh.insert(h.key);
                    }
                    _ => {
                        row.offer_short_persons += 1;
                        row.offer_short_children += p.child as u32;
                        row.offer_short_deficit += short;
                        offer_short_hh.insert(h.key);
                    }
                }
                out.push((p.slot, p.id, p.household, p.child, ration, status));
            }
            row.priced_out_households = priced_out_hh.len() as u32;
            row.offer_short_households = offer_short_hh.len() as u32;
            row.withheld_dead_households = withheld_hh.len() as u32;
            row.deficit = row.priced_out_deficit + row.offer_short_deficit + row.withheld_dead_deficit;
            works.push(RetailRegionWork { row, purchase, people: out });
        }
    }
    // Settle every pilot region's purchases once (not in free exchange).
    let mut frame = RetailFrame { source_turn: cfg.source_turn, mode: cfg.mode, ..Default::default() };
    if cfg.mode != RETAIL_MODE_FREE_EXCHANGE {
        let purchases: Vec<crate::wealth_transfer::FoodPurchases> = works.iter().map(|w| w.purchase.clone()).collect();
        let (money, book) = crate::wealth_transfer::settle_food_purchases(pool, turn, &purchases)?;
        for (w, m) in works.iter_mut().zip(money) {
            w.row.paid_milli = m.paid;
            w.row.credited_milli = m.credited;
            w.row.refunded_milli = m.refunded;
            w.row.refused_ceiling_milli = m.refused_ceiling;
        }
        frame.money = book;
    }
    // Rations into food_access (L2 sized the vectors and wrote the ids).
    let mut unfed = Vec::new();
    let mut fed = Vec::new();
    for w in &works {
        let abundant = w.row.sufficiency >= 1.0;
        for &(slot, id, household, _child, ration, status) in &w.people {
            if slot < pool.food_access.len() {
                pool.food_access[slot] = if full_ration(ration, rf) {
                    if abundant { f32::NAN } else { 1.0 }
                } else {
                    ration as f32
                };
                pool.food_access_ids[slot] = id;
            }
            let record = (id, w.row.region, household, ration as f32, w.row.fair_share as f32, status);
            if status == RETAIL_STATUS_FED { fed.push(record) } else { unfed.push(record) }
        }
    }
    for record in unfed.into_iter().chain(fed) {
        if frame.sample.len() < MAX_SAMPLE { frame.sample.push(record) } else { frame.sample_dropped += 1 }
    }
    frame.claims = by_claim_region.values().flatten()
        .map(|&c| (cfg.claims[c].0, cfg.claims[c].1, eaten[c], sold[c])).collect();
    frame.regions = works.into_iter().map(|w| w.row).collect();
    Ok(frame)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    #[test]
    fn cmp_f64_is_total_and_keeps_the_zeros_equal() {
        use std::cmp::Ordering;
        assert_eq!(cmp_f64(-0.0, 0.0), Ordering::Equal);
        assert_eq!(cmp_f64(0.0, -0.0), Ordering::Equal);
        assert_ne!(cmp_f64(f64::NAN, 1.0), Ordering::Equal);
        assert_ne!(cmp_f64(1.0, f64::NAN), Ordering::Equal);
        // A finite list with both zeros and ties sorts as `partial_cmp` sorted it,
        // so the tie-break key still decides between -0.0 and 0.0.
        let keys: [f64; 10] = [3.5, -0.0, 1.0, 0.0, -2.25, 1.0, f64::INFINITY, -0.0, f64::NEG_INFINITY, 7.0];
        let mut before: Vec<usize> = (0..keys.len()).collect();
        before.sort_by(|&a, &b| keys[a].partial_cmp(&keys[b]).unwrap().then(a.cmp(&b)));
        let mut after: Vec<usize> = (0..keys.len()).collect();
        after.sort_by(|&a, &b| cmp_f64(keys[a], keys[b]).then(a.cmp(&b)));
        assert_eq!(after, before);
        let mut descending: Vec<usize> = (0..keys.len()).collect();
        descending.sort_by(|&a, &b| cmp_f64(keys[b], keys[a]));
        let mut descending_before: Vec<usize> = (0..keys.len()).collect();
        descending_before.sort_by(|&a, &b| keys[b].partial_cmp(&keys[a]).unwrap());
        assert_eq!(descending, descending_before);
        // NaN keys sort without a panic.
        let mut with_nan: Vec<f64> = vec![1.0, f64::NAN, -0.0, 0.0, -f64::NAN, 2.0];
        with_nan.sort_by(|a, b| cmp_f64(*a, *b));
        assert_eq!(with_nan.iter().filter(|x| x.is_nan()).count(), 2);
    }

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

    fn install(pool: &mut AgentPool, regions: &[RegionState], c: &ProvisionConfig) -> ProvisionFrame {
        // As the tick does at phase 0.7.
        let (access, ids, frame) = allocate(pool, regions, c);
        pool.food_access_regions = pool.regions.clone();
        pool.food_access = access;
        pool.food_access_ids = ids;
        frame
    }

    #[test]
    fn marriage_merges_households_and_death_or_remarriage_splits_them() {
        use crate::relationships::{remove_symmetric, upsert_symmetric, BondType};
        let marriage = BondType::Marriage as u8;
        let (mut pool, regions) = world(&[(0, 30, 100.0), (0, 30, 0.0), (0, 30, 0.0)], &[0.6]);
        assert!(upsert_symmetric(&mut pool, 0, 1, marriage, 50, 1));
        let f = allocate(&pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.6], vec![3])).2;
        assert_eq!(f.regions[0].households, 2);
        let (a, _, _) = allocate(&pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.6], vec![3]));
        // The couple shares one household's means; the single poor adult gets less.
        assert!((a[0] - a[1]).abs() < 1e-6 && a[0] > a[2]);
        // Remarriage: B leaves A and marries C; A's means no longer reach B.
        remove_symmetric(&mut pool, 0, 1, marriage);
        assert!(upsert_symmetric(&mut pool, 1, 2, marriage, 50, 2));
        let (a, _, f) = allocate(&pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.6], vec![3]));
        assert_eq!(f.regions[0].households, 2);
        assert!((a[1] - a[2]).abs() < 1e-6 && a[0] > a[1]);
        // Death of a spouse leaves a household of one; nobody eats for the dead.
        pool.kill(2);
        let (a, _, f) = allocate(&pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.6], vec![3]));
        assert_eq!((f.regions[0].alive, f.regions[0].households), (2, 2));
        assert!(a[2].is_nan());
        assert!((f.regions[0].allocated + f.regions[0].unallocated - f.regions[0].rations_available).abs() < 1e-9);
    }

    #[test]
    fn migrants_newborns_and_reused_slots_read_the_regional_signal() {
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 50.0), (1, 30, 0.0)], &[0.4, 0.9]);
        let frame = install(&mut pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.4, 0.9], vec![2, 1]));
        assert_eq!(frame.regions.len(), 2);
        let own = food_for(&pool, 0, 0.4);
        assert!(!own.is_nan() && own <= 1.0);
        // A migrant after the allocation reads the region it is now in.
        pool.regions[0] = 1;
        assert_eq!(food_for(&pool, 0, 0.9), 0.9);
        // A newborn in a reused slot is a different person: regional signal.
        pool.kill(1);
        let born = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 0, 0.5, 0.5, 0.5, 0, 1, 2, 0);
        assert_eq!(born, 1);
        assert_eq!(food_for(&pool, born, 0.4), 0.4);
        // With no allocation installed every consumer reads the region.
        pool.food_access.clear();
        assert_eq!(food_for(&pool, 2, 0.9), 0.9);
    }

    #[test]
    fn empty_and_zero_food_regions_are_handled() {
        let (pool, regions) = world(&[(1, 30, 0.0), (1, 5, 0.0)], &[0.3, 0.0]);
        let (access, _, frame) = allocate(&pool, &regions, &cfg(REGIME_TARGETED_RELIEF, vec![f32::NAN, 0.0], vec![0, 2]));
        let empty = &frame.regions[0];
        assert_eq!((empty.alive, empty.households, empty.scarce), (0, 0, false));
        assert_eq!((empty.allocated, empty.unallocated, empty.shortfall), (0.0, 0.0, 0.0));
        let starving = &frame.regions[1];
        assert!(starving.scarce && starving.allocated == 0.0 && (starving.shortfall - 2.0).abs() < 1e-9);
        assert!(access[0] == 0.0 && access[1] == 0.0);
        assert_eq!(starving.children, 1);
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

    // --- L6b household retail ---------------------------------------------

    const R: i64 = 500; // milli-food per ration at the default per-capita food

    fn l2_equal(n2: Vec<u32>) -> ProvisionConfig {
        cfg(REGIME_EQUAL, vec![f32::NAN; n2.len()], n2)
    }

    fn offer(mode: u8, regions: Vec<(u16, i64, f64)>, claims: Vec<(u32, u16, i64)>, n: usize) -> RetailConfig {
        RetailConfig::new(3, mode, R, regions, claims, n).unwrap()
    }

    /// As the tick does at phase 0.7: L2 first, then retail.
    fn sell(pool: &mut AgentPool, regions: &[RegionState], l2: &ProvisionConfig, rc: &RetailConfig) -> RetailFrame {
        install(pool, regions, l2);
        let frame = retail(pool, regions, l2, rc, 3).expect("retail settles");
        assert_closes(&frame, rc);
        frame
    }

    fn milli(pool: &AgentPool, slot: usize) -> i64 { (pool.wealth[slot] as f64 * 1000.0).round() as i64 }

    fn access(pool: &AgentPool, slot: usize) -> f32 { pool.food_access[slot] }

    fn col(row: &RetailRegionRow, name: &str) -> f64 {
        row.row()[RETAIL_REGION_COLUMNS.iter().position(|c| *c == name).unwrap()]
    }

    /// Every identity of the frame: free, food, rations and money.
    fn assert_closes(frame: &RetailFrame, rc: &RetailConfig) {
        assert_eq!(RETAIL_REGION_COLUMNS.len(), frame.regions.first().map_or(50, |r| r.row().len()));
        for row in &frame.regions {
            assert!((row.free_given + row.free_unallocated - row.free_rations).abs() < 1e-9);
            assert!(row.free_given <= row.free_living + 1e-9);
            assert_eq!(row.own_eaten_fair_milli + row.own_eaten_open_milli + row.sold_fair_milli + row.sold_open_milli + row.unsold_milli, row.offered_milli);
            let food = (row.own_eaten_fair_milli + row.own_eaten_open_milli + row.sold_fair_milli + row.sold_open_milli) as f64 / R as f64;
            assert!((row.rations - row.free_given - food).abs() < 1e-6, "{row:?}");
            assert_eq!(col(row, "own_eaten_milli") as i64, row.own_eaten_fair_milli + row.own_eaten_open_milli);
            assert_eq!(col(row, "sold_milli") as i64, row.sold_fair_milli + row.sold_open_milli);
            assert_eq!(row.paid_milli, row.credited_milli + row.refunded_milli);
            assert_eq!(row.refunded_milli, row.refused_ceiling_milli);
            assert!(row.withheld_dead_milli <= row.unsold_milli && row.withheld_dead_claims <= row.claims);
            assert!(row.min_ration >= 0.0 && row.max_ration <= 1.0);
            assert!((row.deficit - row.priced_out_deficit - row.offer_short_deficit - row.withheld_dead_deficit).abs() < 1e-12);
            assert_eq!(row.fed_fair + row.priced_out_persons + row.offer_short_persons + row.withheld_dead_persons,
                       row.persons);
            // A shortfall is withheld_dead only where a dead owner's claim was withheld.
            assert!(row.withheld_dead_persons == 0 || row.withheld_dead_milli > 0);
            let claims: Vec<_> = frame.claims.iter().filter(|c| c.1 == row.region).collect();
            assert_eq!(claims.len() as u32, row.claims);
            assert_eq!(claims.iter().map(|c| c.2).sum::<i64>(), row.own_eaten_fair_milli + row.own_eaten_open_milli);
            assert_eq!(claims.iter().map(|c| c.3).sum::<i64>(), row.sold_fair_milli + row.sold_open_milli);
            if row.mode == RETAIL_MODE_FREE_EXCHANGE { assert_eq!((row.price_milli, row.paid_milli), (0, 0)); }
        }
        // Each claim moves at most what it held.
        for &(owner, region, eaten, sold) in &frame.claims {
            let held = rc.claims.iter().find(|c| c.0 == owner && c.1 == region).unwrap().2;
            assert!(eaten >= 0 && sold >= 0 && eaten + sold <= held);
        }
        let money = |f: fn(&(u32, i64, i64, i64)) -> i64| frame.money.iter().map(f).sum::<i64>();
        assert_eq!(money(|m| m.1), frame.regions.iter().map(|r| r.paid_milli).sum::<i64>());
        assert_eq!(money(|m| m.2), frame.regions.iter().map(|r| r.credited_milli).sum::<i64>());
        assert_eq!(money(|m| m.3), frame.regions.iter().map(|r| r.refunded_milli).sum::<i64>());
        assert!(frame.money.windows(2).all(|w| w[0].0 < w[1].0));
    }

    #[test]
    fn fair_share_round_comes_before_the_open_round() {
        // A owns 700 milli-food; B has cash. cf = 0.6 (300 milli-food each).
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0)], &[0.6]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(a, 0, 700)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        let row = &f.regions[0];
        // A eats its fair share, B buys its fair share, then A eats the rest:
        // owners never eat beyond the fair share while a paying neighbour is below it.
        assert_eq!((row.own_eaten_fair_milli, row.sold_fair_milli, row.own_eaten_open_milli, row.sold_open_milli, row.unsold_milli), (300, 300, 100, 0, 0));
        assert!((access(&pool, 0) - 0.8).abs() < 1e-6);
        assert!((access(&pool, 1) - 0.6).abs() < 1e-6);
        assert_eq!(f.claims, vec![(a, 0, 400, 300)]);
        // 0.6 rations at 250 milli each: 150 milli from B to A.
        assert_eq!(f.money, vec![(a, 0, 150, 0), (b, 150, 0, 0)]);
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), (150, 9850));
        assert_eq!((row.fed_fair, row.priced_out_persons, row.offer_short_persons), (2, 0, 0));
        assert_eq!(f.sample.iter().map(|s| s.5).collect::<Vec<_>>(), vec![RETAIL_STATUS_FED; 2]);
        // With more food both reach a full ration in the open round.
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0)], &[0.6]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(a, 0, 1000)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        assert_eq!((f.regions[0].sold_fair_milli, f.regions[0].sold_open_milli, f.regions[0].unsold_milli), (300, 200, 0));
        assert_eq!((access(&pool, 0), access(&pool, 1)), (1.0, 1.0)); // short region: 1.0, not the signal
    }

    #[test]
    fn own_food_first_children_first_and_adults_pay() {
        // P (adult, 0.2 wealth) and child C (owns 100 milli-food, wealth 5);
        // owner O elsewhere in the region with 2000. cf = 0.8 (400 each).
        let (mut pool, regions) = world(&[(0, 30, 0.2), (0, 5, 5.0), (0, 30, 0.0)], &[0.8]);
        let (p, c, o) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        pool.parent_id_0[1] = p;
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 500, 0.0)], vec![(c, 0, 100), (o, 0, 2000)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![3]), &rc);
        let row = &f.regions[0];
        assert_eq!(row.households, 2);
        // C eats its own 100; the household's 200 milli buys 200 milli-food,
        // which goes to the child first: C 300, P 0. Only the adult pays.
        assert!((access(&pool, 1) - 0.6).abs() < 1e-6);
        assert_eq!(access(&pool, 0), 0.0);
        assert_eq!(access(&pool, 2), 1.0);
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), (0, 5000));
        assert_eq!(f.money, vec![(p, 200, 0, 0), (o, 0, 200, 0)]);
        assert_eq!((row.priced_out_households, row.priced_out_persons, row.priced_out_children), (1, 2, 1));
        assert!((row.priced_out_deficit - (0.8 + 0.2)).abs() < 1e-6);
        assert_eq!(row.priority_households, 1);
        assert_eq!(f.claims, vec![(c, 0, 100, 0), (o, 0, 500, 200)]);
        // Priced-out people lead the sample.
        assert_eq!(f.sample[0].5, RETAIL_STATUS_PRICED_OUT);
        assert_eq!(f.sample.last().unwrap().5, RETAIL_STATUS_FED);
    }

    #[test]
    fn a_household_without_an_adult_pays_from_its_own_wealth() {
        // An orphan (wealth 0.3) and an owner; cf = 0.6.
        let (mut pool, regions) = world(&[(0, 10, 0.3), (0, 30, 0.0)], &[0.6]);
        let (k, o) = (pool.ids[0], pool.ids[1]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(o, 0, 1000)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        // The child buys a full ration over the two rounds: 500 milli-food, 250 milli.
        assert_eq!(access(&pool, 0), 1.0);
        assert_eq!(f.money, vec![(k, 250, 0, 0), (o, 0, 250, 0)]);
        assert_eq!(milli(&pool, 0), 50);
        // Without the child's own wealth it would be priced out.
        let (mut pool, regions) = world(&[(0, 10, 0.0), (0, 30, 0.0)], &[0.6]);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        assert_eq!(access(&pool, 0), 0.0);
        assert_eq!((f.regions[0].priced_out_children, f.regions[0].paid_milli), (1, 0));
    }

    #[test]
    fn a_short_offer_is_split_pro_rata_by_largest_remainder() {
        // B1, B2 want 300 each; B3 eats its own 150 and wants 150; an absent
        // owner O (region 1) offers 301. cf = 0.6.
        let (mut pool, regions) = world(&[(0, 30, 10.0), (0, 30, 10.0), (0, 30, 10.0), (1, 30, 0.0)], &[0.6, 1.0]);
        let ids: Vec<u32> = pool.ids[..4].to_vec();
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(ids[2], 0, 150), (ids[3], 0, 301)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![3, 1]), &rc);
        let row = &f.regions[0];
        assert_eq!((row.demand_fair_milli, row.sold_fair_milli, row.unsold_milli), (750, 301, 0));
        // 120.4, 120.4, 60.2: the leftover milli-food goes to the smaller key.
        let got = |s: usize| (access(&pool, s) as f64 * R as f64).round() as i64;
        assert_eq!((got(0), got(1), got(2)), (121, 120, 150 + 60));
        assert_eq!((row.offer_short_households, row.offer_short_persons, row.priced_out_persons), (3, 3, 0));
        assert!(f.sample.iter().take(3).all(|s| s.5 == RETAIL_STATUS_OFFER_SHORT));
        // Payments round up per household: 61 + 60 + 30.
        assert_eq!(f.money, vec![(ids[0], 61, 0, 0), (ids[1], 60, 0, 0), (ids[2], 30, 0, 0), (ids[3], 0, 151, 0)]);
        assert!(access(&pool, 3).is_nan()); // region 1 is not a pilot: L2 abundance
        // An ample offer: three sellers sell pro rata to their claims, ties by id.
        let (mut pool, regions) = world(&[(0, 30, 10.0), (1, 30, 0.0), (1, 30, 0.0), (1, 30, 0.0)], &[0.4, 1.0]);
        let ids: Vec<u32> = pool.ids[..4].to_vec();
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)],
            vec![(ids[3], 0, 100), (ids[1], 0, 100), (ids[2], 0, 100)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![1, 3]), &rc);
        // 200 in the fair round (66.7 each), then 100 more in the open round.
        assert_eq!(f.claims, vec![(ids[1], 0, 0, 100), (ids[2], 0, 0, 100), (ids[3], 0, 0, 100)]);
        assert_eq!((f.regions[0].sold_fair_milli, f.regions[0].sold_open_milli), (200, 100));
        let (mut pool, regions) = world(&[(0, 30, 10.0), (1, 30, 0.0), (1, 30, 0.0), (1, 30, 0.0)], &[0.4, 1.0]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)],
            vec![(ids[3], 0, 100), (ids[1], 0, 100), (ids[2], 0, 1000)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![1, 3]), &rc);
        // Fair round 200 of 1200: 16.7, 166.7, 16.7 -> 17, 167, 16 (equal
        // remainders, smaller id first); open round 300 of 83, 833, 84 ->
        // 24.9, 249.9, 25.2 -> 25, 250, 25.
        assert_eq!(f.claims, vec![(ids[1], 0, 0, 42), (ids[2], 0, 0, 417), (ids[3], 0, 0, 41)]);
    }

    #[test]
    fn wealth_never_goes_negative_and_the_ceiling_refunds_the_buyers() {
        // B has 125 milli: at 250 a ration it affords 250 milli-food; the
        // seller S is near the wealth ceiling.
        let (mut pool, regions) = world(&[(0, 30, 0.125), (1, 30, 99.99)], &[0.6, 1.0]);
        let (b, s) = (pool.ids[0], pool.ids[1]);
        let room = crate::wealth_transfer::floor_millis(crate::agent::MAX_WEALTH - pool.wealth[1]);
        assert!(room < 125);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(s, 0, 1000)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![1, 1]), &rc);
        let row = &f.regions[0];
        assert_eq!((row.sold_fair_milli, row.sold_open_milli), (250, 0));
        assert_eq!((row.paid_milli, row.credited_milli, row.refused_ceiling_milli, row.refunded_milli), (125, room, 125 - room, 125 - room));
        assert_eq!(f.money, vec![(b, 125, 0, 125 - room), (s, 0, room, 0)]);
        assert_eq!(milli(&pool, 0), 125 - room);
        assert!(pool.wealth[0] >= 0.0 && pool.wealth[1] <= crate::agent::MAX_WEALTH);
        // The food is still delivered; B is priced out of the rest.
        assert!((access(&pool, 0) - 0.5).abs() < 1e-6);
        assert_eq!(row.priced_out_persons, 1);
    }

    #[test]
    fn an_owner_dead_after_phase2_keeps_the_claim_whole_and_a_dead_buyer_is_skipped() {
        // O owns 400 and dies after Phase 2, as D does; B has cash; a living
        // owner L elsewhere in the region holds 100.
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0), (0, 30, 10.0), (0, 30, 0.0)], &[0.6]);
        let (o, b, d, l) = (pool.ids[0], pool.ids[1], pool.ids[2], pool.ids[3]);
        pool.kill(0);
        pool.kill(2);
        // Four were fed at Phase 2; the free rations of the two dead stay unallocated.
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.4)], vec![(o, 0, 400), (l, 0, 100)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![4]), &rc);
        let row = &f.regions[0];
        assert_eq!((row.persons, row.present_claims), (2, 1));
        assert!((row.free_living - 0.2).abs() < 1e-12 && (row.free_unallocated - 0.2).abs() < 1e-9);
        // The dead owner's claim is neither offered nor eaten: it stays whole
        // for the heirs. Only L's 100 is food: L eats it and B finds no offer.
        assert_eq!((row.withheld_dead_claims, row.withheld_dead_milli, row.offered_milli), (1, 400, 500));
        assert_eq!((row.own_eaten_fair_milli + row.own_eaten_open_milli, row.sold_fair_milli + row.sold_open_milli,
                    row.unsold_milli), (100, 0, 400));
        assert_eq!(f.claims, vec![(o, 0, 0, 0), (l, 0, 100, 0)]);
        assert_eq!((row.paid_milli, row.credited_milli, row.refunded_milli), (0, 0, 0));
        assert!(f.money.is_empty());
        assert_eq!(milli(&pool, 1), 10_000);
        // L, means-tested, takes the free 0.2 and eats its own 100 (0.4, priced
        // out of the rest); B, with cash, finds nothing on offer because the
        // dead owner's food was withheld: classified withheld_dead, never
        // offer_short.
        assert_eq!(access(&pool, 1), 0.0);
        assert!((access(&pool, 3) - 0.4).abs() < 1e-6);
        assert_eq!((row.offer_short_persons, row.priced_out_persons, row.withheld_dead_persons), (0, 1, 1));
        assert_eq!((row.withheld_dead_households, row.withheld_dead_children), (1, 0));
        assert!((row.withheld_dead_deficit - 0.6).abs() < 1e-6);
        assert_eq!(f.sample.iter().find(|s| s.0 == b).unwrap().5, RETAIL_STATUS_WITHHELD_DEAD);
        assert!(f.sample.iter().all(|s| s.0 == b || s.0 == l) && f.sample.iter().all(|s| s.0 != d));
    }

    #[test]
    fn a_reused_slot_is_not_the_owner() {
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0)], &[0.6]);
        let (o, b) = (pool.ids[0], pool.ids[1]);
        pool.kill(0);
        let born = pool.spawn(0, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5, 0, 1, 2, 0);
        assert_eq!(born, 0);
        assert_ne!(pool.ids[0], o);
        pool.wealth[born] = 0.0;
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(o, 0, 400)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        let row = &f.regions[0];
        // The newborn in the dead owner's slot does not eat the claim, and
        // nobody buys it: it is withheld whole.
        assert_eq!((row.present_claims, row.withheld_dead_milli, row.unsold_milli), (0, 400, 400));
        assert_eq!((access(&pool, 0), access(&pool, 1)), (0.0, 0.0));
        assert_eq!((row.paid_milli, milli(&pool, 0), milli(&pool, 1)), (0, 0, 10_000));
        assert_eq!(f.claims, vec![(o, 0, 0, 0)]);
        let _ = b;
    }

    #[test]
    fn non_pilot_regions_keep_l2_exactly() {
        let people = [(0, 30, 1.0), (0, 30, 9.0), (0, 5, 0.0), (1, 30, 2.0), (1, 30, 0.0), (1, 8, 4.0)];
        let fs = [0.5, 0.45];
        for regime in [REGIME_EQUAL, REGIME_FLOOR_MEANS, REGIME_TARGETED_RELIEF] {
            let l2 = cfg(regime, vec![0.3, 0.3], vec![3, 3]);
            let (mut alone, regions) = world(&people, &fs);
            alone.parent_id_0[2] = alone.ids[0];
            let (mut both, _) = world(&people, &fs);
            both.parent_id_0[2] = both.ids[0];
            install(&mut alone, &regions, &l2);
            let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 300, 0.4)], vec![(both.ids[1], 0, 600)], 2);
            let f = sell(&mut both, &regions, &l2, &rc);
            assert_eq!(f.regions.len(), 1);
            for slot in 3..6 {
                assert_eq!(both.food_access[slot].to_bits(), alone.food_access[slot].to_bits());
                assert_eq!(both.wealth[slot].to_bits(), alone.wealth[slot].to_bits());
            }
            assert_eq!(both.food_access_ids, alone.food_access_ids);
            // L2's own receipt is untouched by retail.
            assert_eq!(both.provision_frame, alone.provision_frame);
        }
    }

    #[test]
    fn the_free_pool_is_means_tested_except_in_no_relief() {
        // P (no cash) and R (cash); an absent owner offers 1000. Free: 0.6 rations.
        let people = [(0, 30, 0.0), (0, 30, 10.0), (1, 30, 0.0)];
        let fs = [0.6, 1.0];
        let claims = |pool: &AgentPool| vec![(pool.ids[2], 0, 1000)];
        let (mut pool, regions) = world(&people, &fs);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.6)], claims(&pool), 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2, 1]), &rc);
        // P is means-tested and gets the whole free pool; R buys its fair share.
        assert!((access(&pool, 0) - 0.6).abs() < 1e-6 && (access(&pool, 1) - 1.0).abs() < 1e-6);
        assert_eq!((f.regions[0].priority_households, f.regions[0].priced_out_persons), (1, 0));
        assert!((f.regions[0].free_to_priority - 0.6).abs() < 1e-9);
        // No relief: L2's equal regime shares the pool; P is priced out.
        let (mut pool, regions) = world(&people, &fs);
        let rc = offer(RETAIL_MODE_NO_RELIEF, vec![(0, 250, 0.6)], claims(&pool), 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2, 1]), &rc);
        assert!((access(&pool, 0) - 0.3).abs() < 1e-6 && (access(&pool, 1) - 1.0).abs() < 1e-6);
        assert_eq!((f.regions[0].priority_households, f.regions[0].priced_out_persons), (0, 1));
        // No relief under floor_means: L2's floor (0.5), then by means: of
        // 1.6 free rations R takes a full ration and P 0.6.
        let (mut pool, regions) = world(&people, &fs);
        let rc = offer(RETAIL_MODE_NO_RELIEF, vec![(0, 250, 1.6)], claims(&pool), 2);
        let f = sell(&mut pool, &regions, &cfg(REGIME_FLOOR_MEANS, vec![f32::NAN; 2], vec![2, 1]), &rc);
        assert!((access(&pool, 0) - 0.6).abs() < 1e-6 && access(&pool, 1) == 1.0);
        assert_eq!((f.regions[0].paid_milli, f.regions[0].sold_fair_milli + f.regions[0].sold_open_milli), (0, 0));
        // Means test, own food counted: an owner with enough food is not tested.
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 0.0)], &[0.6]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.6)], vec![(pool.ids[0], 0, 300)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2]), &rc);
        assert_eq!(f.regions[0].priority_households, 1);
        assert!((access(&pool, 0) - 0.6).abs() < 1e-6 && (access(&pool, 1) - 0.6).abs() < 1e-6);
        assert_eq!(f.regions[0].own_eaten_fair_milli, 300);
    }

    #[test]
    fn free_exchange_runs_the_rounds_at_price_zero_without_payment() {
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0), (0, 30, 0.0)], &[0.6]);
        let a = pool.ids[0];
        let rc = offer(RETAIL_MODE_FREE_EXCHANGE, vec![(0, 250, 0.0)], vec![(a, 0, 1000)], 1);
        let before: Vec<i64> = (0..3).map(|s| milli(&pool, s)).collect();
        let f = sell(&mut pool, &regions, &l2_equal(vec![3]), &rc);
        let row = &f.regions[0];
        assert_eq!((row.price_quoted_milli, row.price_milli, row.paid_milli), (250, 0, 0));
        assert!(f.money.is_empty());
        assert_eq!((0..3).map(|s| milli(&pool, s)).collect::<Vec<_>>(), before);
        assert!(pool.wealth_transfer_log.is_empty());
        // The penniless buy at price 0: everyone reaches the fair share first.
        assert_eq!((row.own_eaten_fair_milli, row.sold_fair_milli), (300, 600));
        assert!((0..3).all(|s| access(&pool, s) >= 0.6 - 1e-6));
    }

    #[test]
    fn an_abundant_region_keeps_its_signal_for_the_fed() {
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0), (0, 30, 0.0)], &[1.4]);
        let o = pool.ids[0];
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 400, 0.0)], vec![(o, 0, 1000)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![3]), &rc);
        assert!(access(&pool, 0).is_nan() && access(&pool, 1).is_nan());
        assert_eq!(access(&pool, 2), 0.0);
        assert_eq!(food_for(&pool, 0, 1.4), 1.4);
        assert_eq!(food_for(&pool, 2, 1.4), 0.0);
        assert_eq!((f.regions[0].full_ration, f.regions[0].priced_out_persons), (2, 1));
        assert_eq!(pool.wealth_transfer_log, vec![(3, crate::wealth_transfer::PURPOSE_FOOD_PURCHASE, 0)]);
    }

    #[test]
    fn receipts_close_in_a_mixed_world() {
        use crate::relationships::{upsert_symmetric, BondType};
        // Two pilot regions and a third: couples, children, owners present,
        // absent and dead, a free pool and short markets.
        let build = || {
            let people: Vec<(u16, u16, f32)> = (0..30).map(|i| {
                let age = if i % 4 == 3 { 6 } else { 25 + i as u16 };
                ((i % 3) as u16, age, (i as f32 * 0.37) % 2.1)
            }).collect();
            let (mut pool, regions) = world(&people, &[0.55, 0.8, 0.7]);
            for (a, b) in [(0, 6), (1, 4), (2, 5), (12, 18)] {
                assert!(upsert_symmetric(&mut pool, a, b, BondType::Marriage as u8, 50, 1));
            }
            for child in (3..30).step_by(4) {
                pool.parent_id_0[child] = pool.ids[child - 3];
            }
            pool.kill(9);
            (pool, regions)
        };
        let (pool, regions) = build();
        let ids: Vec<u32> = pool.ids[..30].to_vec();
        let claims = vec![(ids[0], 0, 900), (ids[1], 0, 333), (ids[9], 0, 250), (ids[4], 1, 1200),
                          (ids[7], 1, 41), (ids[3], 0, 77), (ids[2], 1, 500), (ids[13], 1, 10)];
        for mode in [RETAIL_MODE_RETAIL, RETAIL_MODE_NO_RELIEF, RETAIL_MODE_FREE_EXCHANGE] {
            let (mut p, _) = build();
            let rc = offer(mode, vec![(1, 375, 0.9), (0, 280, 1.7)], claims.clone(), 3);
            let f = sell(&mut p, &regions, &cfg(REGIME_FLOOR_MEANS, vec![0.4, 0.5, 0.6], vec![10, 10, 10]), &rc);
            assert_eq!(f.regions.iter().map(|r| r.region).collect::<Vec<_>>(), vec![0, 1]);
            assert_eq!((f.source_turn, f.mode), (3, mode));
            assert_eq!(f.claims.len(), claims.len());
            assert_eq!(f.sample.len() + f.sample_dropped, 19);
            assert!(f.regions.iter().all(|r| col(r, "mode") == mode as f64 && r.households > 0));
            // Money: nothing created or destroyed, no payer below zero or
            // refunded above what they paid.
            let total = |q: &AgentPool| (0..30).map(|s| q.wealth[s] as f64).sum::<f64>();
            assert!((total(&pool) - total(&p)).abs() < 1e-3);
            for &(id, paid, _, refunded) in &f.money {
                let slot = (0..30).find(|&s| pool.ids[s] == id).unwrap();
                assert!(paid <= crate::wealth_transfer::floor_millis(pool.wealth[slot]) && refunded <= paid);
            }
            assert!((0..30).all(|s| p.wealth[s] >= 0.0));
            assert_eq!(f.regions[0].withheld_dead_milli, 250);
            assert!(f.claims.contains(&(ids[9], 0, 0, 0)));
            if mode != RETAIL_MODE_FREE_EXCHANGE {
                assert!(f.regions.iter().map(|r| r.paid_milli).sum::<i64>() > 0);
                assert!(f.regions.iter().map(|r| r.paid_milli).sum::<i64>() > 0);
            }
        }
    }

    #[test]
    fn invalid_retail_installs_are_refused() {
        let ok = || RetailConfig::new(1, 0, R, vec![(0, 250, 1.0), (2, 0, 0.0)], vec![(5, 0, 10), (5, 2, 10)], 3);
        assert!(ok().is_ok());
        let bad: Vec<Result<RetailConfig, &str>> = vec![
            RetailConfig::new(1, 3, R, vec![], vec![], 3),
            RetailConfig::new(1, 0, 0, vec![], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(3, 250, 1.0)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, 1.0), (0, 250, 1.0)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, -1, 1.0)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, RETAIL_MAX_PRICE_MILLI + 1, 1.0)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, f64::NAN)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, -0.5)], vec![], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, 1.0)], vec![(5, 1, 10)], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, 1.0)], vec![(5, 0, 10), (5, 0, 3)], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, 1.0)], vec![(5, 0, -1)], 3),
            RetailConfig::new(1, 0, R, vec![(0, 250, 1.0)], vec![(0, 0, 1)], 3),
        ];
        assert!(bad.iter().all(Result::is_err));
        // Offers are kept by region.
        assert_eq!(ok().unwrap().regions.iter().map(|o| o.region).collect::<Vec<_>>(), vec![0, 2]);
    }

    // --- review D -----------------------------------------------------------

    #[test]
    fn a_fractional_free_share_in_an_abundant_region_still_reads_the_signal() {
        // Reviewer D's case: owner O with plenty, three buyers with cash,
        // regional sufficiency 1.4, one free ration for N2 = 4. The free third
        // leaves each buyer 0.9993 of a ration after whole milli-food purchases;
        // within one milli-food that is a full ration and reads the signal.
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0), (0, 30, 10.0), (0, 30, 10.0)], &[1.4]);
        let o = pool.ids[0];
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 400, 1.0)], vec![(o, 0, 5000)], 1);
        let f = sell(&mut pool, &regions, &l2_equal(vec![4]), &rc);
        let row = &f.regions[0];
        for slot in 0..4 {
            assert!(access(&pool, slot).is_nan(), "slot {slot} reads {}", access(&pool, slot));
            assert_eq!(food_for(&pool, slot, 1.4), 1.4);
        }
        assert_eq!((row.full_ration, row.fed_fair), (4, 4));
        assert!(row.min_ration < 1.0 && row.min_ration > 1.0 - 1.0 / R as f64);
        // In a short region a nearly full ration reads 1.0.
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0), (0, 30, 10.0), (0, 30, 10.0)], &[0.999]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 400, 1.0)], vec![(pool.ids[0], 0, 5000)], 1);
        sell(&mut pool, &regions, &l2_equal(vec![4]), &rc);
        assert!((1..4).all(|slot| access(&pool, slot) == 1.0));
    }

    #[test]
    fn a_household_sells_in_the_fair_round_and_buys_in_the_open_round() {
        // A (cash) owns 400 at cf = 0.6: eats its 300 and offers 100; B wants
        // 300; C, absent, offers 600.
        let (mut pool, regions) = world(&[(0, 30, 10.0), (0, 30, 10.0), (1, 30, 0.0)], &[0.6, 1.0]);
        let (a, b, c) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(a, 0, 400), (c, 0, 600)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2, 1]), &rc);
        // Fair round: B's 300 from A's 100 and C's 600 pro rata: 43 and 257.
        // Open round: A eats its last 57, then buys 143; B buys 200; C sells 343.
        assert_eq!(f.claims, vec![(a, 0, 357, 43), (c, 0, 0, 600)]);
        assert_eq!((access(&pool, 0), access(&pool, 1)), (1.0, 1.0));
        // A pays 72 for its 143 and is credited 22 of the 322 paid for its 43.
        assert_eq!(f.money, vec![(a, 72, 22, 0), (b, 250, 0, 0), (c, 0, 300, 0)]);
        assert_eq!(milli(&pool, 0), 10_000 - 72 + 22);
    }

    #[test]
    fn cash_and_a_short_offer_binding_together_classify_as_priced_out() {
        // B1 can afford 100 milli-food, B2 plenty; C, absent, offers 200 at cf = 0.6.
        let (mut pool, regions) = world(&[(0, 30, 0.05), (0, 30, 10.0), (1, 30, 0.0)], &[0.6, 1.0]);
        let c = pool.ids[2];
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(c, 0, 200)], 2);
        let f = sell(&mut pool, &regions, &l2_equal(vec![2, 1]), &rc);
        let row = &f.regions[0];
        // Demand 100 + 300 > 200: split 50 and 150. B1 is limited by both and
        // reads priced out; B2 by the offer only.
        assert_eq!((row.demand_fair_milli, row.sold_fair_milli), (400, 200));
        assert!((access(&pool, 0) - 0.1).abs() < 1e-6 && (access(&pool, 1) - 0.3).abs() < 1e-6);
        let status = |id: u32| f.sample.iter().find(|s| s.0 == id).unwrap().5;
        assert_eq!(status(pool.ids[0]), RETAIL_STATUS_PRICED_OUT);
        assert_eq!(status(pool.ids[1]), RETAIL_STATUS_OFFER_SHORT);
        assert_eq!((row.priced_out_persons, row.offer_short_persons, row.withheld_dead_persons), (1, 1, 0));
    }

    #[test]
    fn retail_is_refused_unchanged_when_the_turns_purchases_were_settled() {
        let (mut pool, regions) = world(&[(0, 30, 0.0), (0, 30, 10.0)], &[0.6]);
        let a = pool.ids[0];
        let rc = offer(RETAIL_MODE_RETAIL, vec![(0, 250, 0.0)], vec![(a, 0, 700)], 1);
        let l2 = l2_equal(vec![2]);
        sell(&mut pool, &regions, &l2, &rc);
        let wealth = (milli(&pool, 0), milli(&pool, 1));
        let access_before = pool.food_access.clone();
        install(&mut pool, &regions, &l2);
        let installed = pool.food_access.clone();
        assert!(retail(&mut pool, &regions, &l2, &rc, 3).is_err());
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), wealth);
        assert_eq!(pool.food_access, installed);
        assert_ne!(access_before, installed);
        // free_exchange moves no money and needs no key.
        let free = offer(RETAIL_MODE_FREE_EXCHANGE, vec![(0, 250, 0.0)], vec![(a, 0, 700)], 1);
        assert!(retail(&mut pool, &regions, &l2, &free, 3).is_ok());
    }

    #[test]
    fn the_tick_checks_the_purchase_key_and_the_income_regions() {
        let (mut pool, _) = world(&[(0, 30, 1.0), (1, 30, 1.0)], &[0.6, 0.6]);
        assert!(check_retail_tick(&pool, 4).is_ok());
        // Income for a region without a retail install, or outside its regions.
        crate::wealth_transfer::install_retail_income(&mut pool, 4, &[1], 2).unwrap();
        assert!(check_retail_tick(&pool, 4).is_err());
        pool.retail_config = Some(RetailConfig::new(4, RETAIL_MODE_RETAIL, R, vec![(0, 250, 0.0)], vec![], 2).unwrap());
        assert!(check_retail_tick(&pool, 4).is_err());
        pool.retail_config = Some(RetailConfig::new(4, RETAIL_MODE_RETAIL, R, vec![(0, 250, 0.0), (1, 250, 0.0)],
                                                    vec![], 2).unwrap());
        assert!(check_retail_tick(&pool, 4).is_ok());
        pool.retail_config = Some(RetailConfig::new(4, RETAIL_MODE_FREE_EXCHANGE, R, vec![(0, 250, 0.0)], vec![], 2).unwrap());
        assert!(check_retail_tick(&pool, 4).is_ok());          // not checked under free_exchange
        pool.retail_income = None;
        crate::wealth_transfer::install_retail_income(&mut pool, 4, &[], 2).unwrap();
        pool.retail_config = None;
        assert!(check_retail_tick(&pool, 4).is_ok());          // an empty install needs no pilot
        // The purchase key of the turn (or a later one) already consumed.
        pool.retail_income = None;
        pool.retail_config = Some(RetailConfig::new(4, RETAIL_MODE_NO_RELIEF, R, vec![(0, 250, 0.0)], vec![], 2).unwrap());
        pool.wealth_transfer_log.push((4, crate::wealth_transfer::PURPOSE_FOOD_PURCHASE, 0));
        assert!(check_retail_tick(&pool, 4).is_err());
        assert!(check_retail_tick(&pool, 5).is_ok());
        pool.wealth_transfer_log = vec![(4, crate::wealth_transfer::PURPOSE_FOOD_PURCHASE, 1)];
        assert!(check_retail_tick(&pool, 4).is_ok());          // another batch
        pool.wealth_transfer_log = vec![(4, crate::wealth_transfer::PURPOSE_FOOD_PURCHASE, 0)];
        pool.retail_config = Some(RetailConfig::new(4, RETAIL_MODE_FREE_EXCHANGE, R, vec![(0, 250, 0.0)], vec![], 2).unwrap());
        assert!(check_retail_tick(&pool, 4).is_ok());
    }
}
