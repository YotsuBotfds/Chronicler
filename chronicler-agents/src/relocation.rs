//! Livelihoods L7 (default off): priced voluntary household relocation.
//!
//! A one-turn policy installed before the native tick turns the household
//! liquidity gate into a fare for an ordinary adjacency move:
//!
//! * [`gate`] runs after household consolidation, on the same household
//!   groups the liquid-reserve gate uses (a moving lead with the spouse and
//!   dependent children the consolidator actually linked, same origin and
//!   destination). A group is priced at `fare_milli` per person, children
//!   included. It passes when its adult movers' liquid wealth (whole
//!   milli-units, as the wealth transfer debits them) covers the fare, or,
//!   when short, covers it with the destination ruler's bounded assistance
//!   (`assist_milli` per person, never more than the fare, from that ruler's
//!   remaining budget, reserved in the gate's deterministic order: origin
//!   bucket, then (origin, destination, stable id)). A short group is
//!   blocked: its moves are removed before they are applied, so a blocked or
//!   cancelled move is never charged. Groups the fare does not price
//!   (unknown or non-adjacent route, a member on a merchant trip) pass
//!   unpriced, as the liquid-reserve gate lets them pass.
//! * [`finish`] runs after the moves are applied: a group counts as applied
//!   only when every member is alive in the destination (the apply phase is
//!   the only native relocation of ordinary agents). A passed group that was
//!   not applied releases its reserved assistance. The receipt (groups,
//!   per-region alive counts before the gate and after the moves, remaining
//!   budgets) is taken once by Python, which charges the fare through the
//!   wealth transfer and the assistance through the treasury.
//! * [`observe_rations`] (with an L2 food allocation this tick) records the
//!   previous turn's tracked arrivals' own rations against the other
//!   residents' in the region where each now lives.
//!
//! Merchant trips, refugees and conquest flows are not moves here. No RNG;
//! the policy and receipt are transient and never checkpointed.
use std::collections::{BTreeMap, HashSet};

use crate::agent::AGE_ADULT;
use crate::behavior::PendingDecisions;
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Gate reasons, extending the liquid-reserve gate's codes (append only):
/// 0 passed affordability; 1 insufficient; 2 (no local distress) is not
/// used here: every priced move pays; 3 unknown or non-adjacent route; 4 on
/// a trip; 5 passed with the destination's assistance.
pub const REASON_PASSED: u8 = 0;
pub const REASON_SHORT: u8 = 1;
pub const REASON_ROUTE: u8 = 3;
pub const REASON_TRIP: u8 = 4;
pub const REASON_ASSISTED: u8 = 5;
pub const MAX_TRACKED: usize = 256;
pub const MAX_MILLI: i64 = 1_000_000_000;

#[derive(Clone, Debug, PartialEq)]
pub struct Group {
    pub lead: u32,
    pub from: u16,
    pub to: u16,
    /// (stable id, slot at the gate) of every member, ascending id.
    pub members: Vec<(u32, usize)>,
    /// (stable id, liquid milli-units at the gate) of the adult movers.
    pub adults: Vec<(u32, i64)>,
    pub children: u32,
    pub liquid_milli: i64,
    pub reason: u8,
    /// Fare for the whole group, assistance granted, and the payer (-1 none).
    pub fare_milli: i64,
    pub grant_milli: i64,
    pub payer: i16,
    pub applied: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RelocationPolicy {
    pub turn: u32,
    pub fare_milli: i64,
    pub assist_milli: i64,
    /// Per region: the civilization index that assists arrivals (-1 none).
    pub region_payer: Vec<i16>,
    /// Per civilization: the assistance budget still unreserved.
    pub budget_milli: Vec<i64>,
    /// Last turn's arrivals whose rations this tick's allocation reports.
    pub track: Vec<u32>,
    pub groups: Vec<Group>,
    pub before: Vec<u32>,
    /// Per region: (region, arrivals, arrivals' ration sum, residents,
    /// residents' ration sum); None without an allocation this tick.
    pub rations: Option<Vec<(u16, u32, f64, u32, f64)>>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RelocationReceipt {
    pub turn: u32,
    pub groups: Vec<Group>,
    pub before: Vec<u32>,
    pub after: Vec<u32>,
    pub budget_milli: Vec<i64>,
    pub rations: Option<Vec<(u16, u32, f64, u32, f64)>>,
}

fn liquid_milli(wealth: f32) -> i64 {
    if wealth.is_finite() && wealth > 0.0 { (wealth as f64 * 1000.0).floor() as i64 } else { 0 }
}

/// Validate and install; refuses a pending policy.
#[allow(clippy::too_many_arguments)]
pub fn install(pool: &mut AgentPool, turn: u32, fare_milli: i64, assist_milli: i64, region_payer: Vec<i16>,
               budget_milli: Vec<i64>, track: Vec<u32>, num_regions: usize) -> Result<(), &'static str> {
    if pool.relocation_policy.is_some() {
        return Err("relocation policy already pending");
    }
    if !(0..=MAX_MILLI).contains(&fare_milli) || !(0..=MAX_MILLI).contains(&assist_milli) {
        return Err("fare and assistance must be in 0..=1e9 milli-units");
    }
    if region_payer.len() != num_regions {
        return Err("relocation payers must match the region count");
    }
    if region_payer.iter().any(|&p| p < -1 || (p >= 0 && p as usize >= budget_milli.len())) {
        return Err("relocation payer out of range");
    }
    if budget_milli.iter().any(|b| !(0..=MAX_MILLI * 1000).contains(b)) {
        return Err("assistance budgets must be nonnegative and bounded");
    }
    if track.len() > MAX_TRACKED || track.iter().collect::<HashSet<_>>().len() != track.len() {
        return Err("at most 256 distinct tracked arrivals");
    }
    pool.relocation_policy = Some(RelocationPolicy {
        turn, fare_milli, assist_milli, region_payer, budget_milli, track,
        groups: Vec::new(), before: Vec::new(), rations: None,
    });
    pool.relocation_receipt = None;
    Ok(())
}

/// The tick refuses a policy for another turn, or alongside the liquid-reserve gate.
pub fn check_tick(pool: &AgentPool, turn: u32, liquid_requirement: f32) -> Result<(), &'static str> {
    match &pool.relocation_policy {
        Some(p) if p.turn != turn => Err("relocation policy must be installed for this tick"),
        Some(_) if liquid_requirement > 0.0 => Err("relocation fares and the liquid-reserve gate cannot both run"),
        _ => Ok(()),
    }
}

/// After the L2 allocation: tracked arrivals' own rations against residents'.
pub fn observe_rations(pool: &mut AgentPool) {
    let Some(mut policy) = pool.relocation_policy.take() else { return };
    if !pool.food_access.is_empty() {
        let tracked: HashSet<u32> = policy.track.iter().copied().collect();
        let mut rows: BTreeMap<u16, (u32, f64, u32, f64)> = BTreeMap::new();
        let arrival_regions: HashSet<u16> = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s) && tracked.contains(&pool.ids[s])).map(|s| pool.regions[s]).collect();
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) || !arrival_regions.contains(&pool.regions[slot]) { continue; }
            let own = match (pool.food_access.get(slot), pool.food_access_ids.get(slot)) {
                (Some(&v), Some(&id)) if !v.is_nan() && id == pool.ids[slot] => v as f64,
                _ => continue,   // the regional signal: no own ration to compare
            };
            let row = rows.entry(pool.regions[slot]).or_insert((0, 0.0, 0, 0.0));
            if tracked.contains(&pool.ids[slot]) { row.0 += 1; row.1 += own; } else { row.2 += 1; row.3 += own; }
        }
        policy.rations = Some(rows.into_iter().map(|(r, (a, sa, n, sn))| (r, a, sa, n, sn)).collect());
    }
    pool.relocation_policy = Some(policy);
}

fn alive_by_region(pool: &AgentPool, n: usize) -> Vec<u32> {
    let mut counts = vec![0u32; n];
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) && (pool.regions[slot] as usize) < n {
            counts[pool.regions[slot] as usize] += 1;
        }
    }
    counts
}

/// Price the consolidated household moves; returns the blocked slots per bucket.
pub fn gate(pool: &AgentPool, pending: &mut [PendingDecisions], regions: &[RegionState],
            policy: &mut RelocationPolicy, follower_leaders: &[BTreeMap<usize, (usize, u16, u16)>])
    -> Vec<Vec<usize>> {
    policy.before = alive_by_region(pool, regions.len());
    let mut blocked_by_bucket = vec![Vec::new(); pending.len()];
    for (bucket_index, bucket) in pending.iter_mut().enumerate() {
        let mut moves = bucket.migrations.clone();
        moves.sort_unstable_by_key(|m| (m.1, m.2, pool.ids.get(m.0).copied().unwrap_or(u32::MAX)));
        moves.dedup_by_key(|m| m.0);
        let mut parent: Vec<usize> = (0..moves.len()).collect();
        fn root(parent: &[usize], mut i: usize) -> usize {
            while parent[i] != i { i = parent[i]; }
            i
        }
        let moving: BTreeMap<usize, usize> = moves.iter().enumerate().map(|(i, m)| (m.0, i)).collect();
        if let Some(links) = follower_leaders.get(bucket_index) {
            for (&follower, &(leader, from, to)) in links {
                if let (Some(&i), Some(&j)) = (moving.get(&follower), moving.get(&leader)) {
                    if moves[i].1 == from && moves[i].2 == to && moves[j].1 == from && moves[j].2 == to {
                        let x = root(&parent, i);
                        let y = root(&parent, j);
                        if x != y { parent[y] = x; }
                    }
                }
            }
        }
        let mut groups: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
        for i in 0..moves.len() { groups.entry(root(&parent, i)).or_default().push(i); }
        let mut blocked: HashSet<usize> = HashSet::new();
        for indices in groups.values() {
            let (_, from, to) = moves[indices[0]];
            let alive = |slot: usize| slot < pool.capacity() && pool.is_alive(slot);
            let valid = indices.iter().all(|&i| { let (s, f, _) = moves[i]; alive(s) && pool.regions[s] == f });
            let mut members: Vec<(u32, usize)> = indices.iter().map(|&i| moves[i].0)
                .filter(|&s| alive(s)).map(|s| (pool.ids[s], s)).collect();
            members.sort_unstable();
            let adults: Vec<(u32, i64)> = members.iter().filter(|&&(_, s)| pool.ages[s] >= AGE_ADULT)
                .map(|&(id, s)| (id, liquid_milli(pool.wealth[s]))).collect();
            let count = indices.len() as i64;
            let children = (members.len() - adults.len()) as u32;
            let liquid: i64 = adults.iter().map(|a| a.1).sum();
            let fare = policy.fare_milli.saturating_mul(count);
            let mut grant = 0i64;
            let mut payer = -1i16;
            let reason = if !valid || (to as usize) >= regions.len() || (from as usize) >= regions.len()
                || !regions[from as usize].adjacency.contains(&to) {
                REASON_ROUTE
            } else if indices.iter().any(|&i| pool.is_on_trip(moves[i].0)) {
                REASON_TRIP
            } else if liquid >= fare {
                REASON_PASSED
            } else {
                payer = policy.region_payer.get(to as usize).copied().unwrap_or(-1);
                let budget = if payer >= 0 { policy.budget_milli[payer as usize] } else { 0 };
                let offer = policy.assist_milli.min(policy.fare_milli).saturating_mul(count).min(budget);
                if offer > 0 && liquid + offer >= fare {
                    grant = offer;
                    policy.budget_milli[payer as usize] -= offer;
                    REASON_ASSISTED
                } else {
                    REASON_SHORT
                }
            };
            if reason == REASON_SHORT {
                blocked.extend(indices.iter().map(|&i| moves[i].0));
                blocked_by_bucket[bucket_index].extend(indices.iter().map(|&i| moves[i].0));
            }
            let priced = matches!(reason, REASON_PASSED | REASON_ASSISTED | REASON_SHORT);
            policy.groups.push(Group {
                lead: members.first().map_or(u32::MAX, |m| m.0), from, to, members, adults, children,
                liquid_milli: liquid, reason, fare_milli: if priced { fare } else { 0 }, grant_milli: grant,
                payer: if grant > 0 { payer } else { -1 }, applied: false,
            });
        }
        if !blocked.is_empty() {
            bucket.migrations.retain(|m| !blocked.contains(&m.0));
        }
    }
    blocked_by_bucket
}

/// After the moves are applied: mark applied groups, release unused
/// assistance and store the receipt for Python.
pub fn finish(pool: &mut AgentPool, regions: &[RegionState], mut policy: RelocationPolicy) {
    for group in &mut policy.groups {
        if group.reason == REASON_SHORT {
            continue;
        }
        group.applied = !group.members.is_empty() && group.members.iter().all(|&(id, s)|
            s < pool.capacity() && pool.is_alive(s) && pool.ids[s] == id && pool.regions[s] == group.to);
        if !group.applied && group.grant_milli > 0 {
            policy.budget_milli[group.payer as usize] += group.grant_milli;
        }
    }
    let after = alive_by_region(pool, regions.len());
    pool.relocation_receipt = Some(RelocationReceipt {
        turn: policy.turn, groups: policy.groups, before: policy.before, after,
        budget_milli: policy.budget_milli, rations: policy.rations,
    });
}

/// The receipt of `turn`, taken once.
pub fn take(pool: &mut AgentPool, turn: u32) -> Option<RelocationReceipt> {
    if pool.relocation_receipt.as_ref().is_some_and(|r| r.turn == turn) {
        pool.relocation_receipt.take()
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::behavior::PendingDecisions;

    fn person(pool: &mut AgentPool, region: u16, age: u16, wealth: f32) -> usize {
        let slot = pool.spawn(region, 0, Occupation::Farmer, age, 0.5, 0.5, 0.5, 0, 1, 2, 0);
        pool.wealth[slot] = wealth;
        slot
    }

    fn regions() -> Vec<RegionState> {
        let mut r = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
        r[0].adjacency = vec![1];
        r[1].adjacency = vec![0];
        r
    }

    fn policy(fare: i64, assist: i64, budget: i64) -> RelocationPolicy {
        RelocationPolicy { turn: 3, fare_milli: fare, assist_milli: assist, region_payer: vec![0, 0, -1],
            budget_milli: vec![budget], track: Vec::new(), groups: Vec::new(), before: Vec::new(), rations: None }
    }

    /// One household: two adults (wealth a, b) and a child, all moving 0 -> 1.
    fn household(pool: &mut AgentPool, a: f32, b: f32) -> (PendingDecisions, BTreeMap<usize, (usize, u16, u16)>, [usize; 3]) {
        let lead = person(pool, 0, 30, a);
        let spouse = person(pool, 0, 30, b);
        let child = person(pool, 0, 5, 0.0);
        let mut pd = PendingDecisions::new();
        pd.migrations = vec![(lead, 0, 1), (spouse, 0, 1), (child, 0, 1)];
        let links: BTreeMap<usize, (usize, u16, u16)> =
            [(spouse, (lead, 0, 1)), (child, (lead, 0, 1))].into_iter().collect();
        (pd, links, [lead, spouse, child])
    }

    #[test]
    fn a_household_pays_per_person_children_included_from_adult_liquidity() {
        let mut pool = AgentPool::new(8);
        let (pd, links, slots) = household(&mut pool, 2.0, 1.0);
        let regions = regions();
        let mut pending = vec![pd];
        let mut p = policy(1000, 0, 0);
        let blocked = gate(&pool, &mut pending, &regions, &mut p, &[links]);
        assert!(blocked[0].is_empty() && pending[0].migrations.len() == 3);
        let g = &p.groups[0];
        assert_eq!((g.reason, g.fare_milli, g.liquid_milli, g.children, g.adults.len()), (REASON_PASSED, 3000, 3000, 1, 2));
        assert_eq!(g.lead, pool.ids[slots[0]]);
        assert_eq!(p.before, vec![3, 0, 0]);
        for &s in &slots { pool.set_region(s, 1); }
        finish(&mut pool, &regions, p);
        let r = take(&mut pool, 3).unwrap();
        assert!(r.groups[0].applied && r.after == vec![0, 3, 0]);
        assert!(take(&mut pool, 3).is_none());
    }

    #[test]
    fn a_short_household_is_blocked_and_never_applied() {
        let mut pool = AgentPool::new(8);
        let (pd, links, _) = household(&mut pool, 1.0, 1.0);   // 2000 < 3000
        let regions = regions();
        let mut pending = vec![pd];
        let mut p = policy(1000, 0, 0);
        let blocked = gate(&pool, &mut pending, &regions, &mut p, &[links]);
        assert_eq!(blocked[0].len(), 3);
        assert!(pending[0].migrations.is_empty());
        assert_eq!(p.groups[0].reason, REASON_SHORT);
        finish(&mut pool, &regions, p);
        let r = take(&mut pool, 3).unwrap();
        assert!(!r.groups[0].applied && r.after == r.before);
    }

    #[test]
    fn identical_short_households_move_only_with_funded_assistance_in_gate_order() {
        let mut pool = AgentPool::new(16);
        let (mut a, la, _) = household(&mut pool, 1.0, 1.0);
        let (b, lb, _) = household(&mut pool, 1.0, 1.0);
        a.migrations.extend(b.migrations);
        let mut links = la;
        links.extend(lb);
        let regions = regions();
        // Liquidity alone: both blocked.
        let mut alone_pd = PendingDecisions::new();
        alone_pd.migrations = a.migrations.clone();
        let mut alone = vec![alone_pd];
        let mut p = policy(1000, 0, 0);
        gate(&pool, &mut alone, &regions, &mut p, &[links.clone()]);
        assert!(alone[0].migrations.is_empty());
        // Assistance of 500 per person, budget for one household (1500).
        let mut helped = vec![a];
        let mut p = policy(1000, 500, 1500);
        gate(&pool, &mut helped, &regions, &mut p, &[links]);
        let reasons: Vec<u8> = p.groups.iter().map(|g| g.reason).collect();
        assert_eq!(reasons, vec![REASON_ASSISTED, REASON_SHORT]);
        assert_eq!((p.groups[0].grant_milli, p.groups[0].payer, p.budget_milli[0]), (1500, 0, 0));
        assert_eq!(helped[0].migrations.len(), 3);
        // A passed assisted move that is not applied releases its assistance.
        finish(&mut pool, &regions, p);
        let r = take(&mut pool, 3).unwrap();
        assert!(!r.groups[0].applied && r.budget_milli == vec![1500]);
    }

    #[test]
    fn unpriced_routes_and_regions_without_a_payer() {
        let mut pool = AgentPool::new(8);
        let s = person(&mut pool, 0, 30, 0.0);
        let t = person(&mut pool, 1, 30, 0.0);
        let mut pd = PendingDecisions::new();
        pd.migrations = vec![(s, 0, 2), (t, 1, 0)];   // 0 -> 2 is not adjacent
        let mut pending = vec![pd];
        let mut p = policy(1000, 1000, 5000);
        p.region_payer = vec![-1, 0, -1];             // nobody assists arrivals in region 0
        let regions = regions();
        gate(&pool, &mut pending, &regions, &mut p, &[BTreeMap::new()]);
        let by_to: BTreeMap<u16, u8> = p.groups.iter().map(|g| (g.to, g.reason)).collect();
        assert_eq!(by_to[&2], REASON_ROUTE);
        assert_eq!(by_to[&0], REASON_SHORT);
        assert_eq!(pending[0].migrations, vec![(s, 0, 2)]);
        assert!(p.groups.iter().all(|g| g.reason != REASON_ROUTE || g.fare_milli == 0));
    }

    #[test]
    fn zero_fare_passes_everyone_and_install_validates() {
        let mut pool = AgentPool::new(8);
        let (pd, links, _) = household(&mut pool, 0.0, 0.0);
        let proposed = pd.migrations.clone();
        let mut pending = vec![pd];
        let mut p = policy(0, 0, 0);
        gate(&pool, &mut pending, &regions(), &mut p, &[links]);
        assert_eq!(pending[0].migrations, proposed);
        assert!(install(&mut pool, 1, -1, 0, vec![-1; 3], vec![], vec![], 3).is_err());
        assert!(install(&mut pool, 1, 1000, 0, vec![-1; 2], vec![], vec![], 3).is_err());
        assert!(install(&mut pool, 1, 1000, 0, vec![0, -1, -1], vec![], vec![], 3).is_err());
        assert!(install(&mut pool, 1, 1000, 0, vec![-1; 3], vec![], vec![7, 7], 3).is_err());
        assert!(pool.relocation_policy.is_none());
        install(&mut pool, 1, 1000, 500, vec![0, -1, -1], vec![10], vec![], 3).unwrap();
        assert!(install(&mut pool, 1, 1000, 0, vec![-1; 3], vec![], vec![], 3).is_err());
        assert!(check_tick(&pool, 2, 0.0).is_err() && check_tick(&pool, 1, 0.5).is_err());
        assert!(check_tick(&pool, 1, 0.0).is_ok());
    }

    #[test]
    fn tracked_arrivals_rations_are_compared_with_residents() {
        let mut pool = AgentPool::new(8);
        let arrival = person(&mut pool, 1, 30, 0.0);
        let resident = person(&mut pool, 1, 30, 0.0);
        let elsewhere = person(&mut pool, 0, 30, 0.0);
        let mut p = policy(0, 0, 0);
        p.track = vec![pool.ids[arrival]];
        pool.relocation_policy = Some(p);
        observe_rations(&mut pool);                       // no allocation this tick: unknown
        assert!(pool.relocation_policy.as_ref().unwrap().rations.is_none());
        pool.food_access = vec![0.5, 0.9, 1.0];
        pool.food_access_ids = (0..3).map(|s| pool.ids[s]).collect();
        observe_rations(&mut pool);
        let rows = pool.relocation_policy.as_ref().unwrap().rations.clone().unwrap();
        assert_eq!(rows.len(), 1);
        let (region, a, sa, n, sn) = rows[0];
        assert_eq!((region, a, n), (1, 1, 1));
        assert!((sa - 0.5).abs() < 1e-6 && (sn - 0.9).abs() < 1e-6);
        let _ = (resident, elsewhere);
    }
}
