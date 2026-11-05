//! Livelihoods sprint L1A: payer-independent workshop crew eligibility.
//!
//! A read-only planner over the live pool. For each selected workshop site
//! (one city settlement in one region) it resolves the named adult urban
//! farmers whose already-diverted farming time is available to the site:
//! living, age >= `AGE_ADULT`, `Occupation::Farmer`, resident in that
//! settlement and region, not on a merchant trip, not enlisted in an army
//! (identities supplied by the caller from the war state) and not already
//! reserved by another work consumer (`health_work_loss`, a pending teaching
//! plan, or an earlier site of the same plan). Selection is deterministic:
//! ascending stable agent id, at most `max_workers` per site. No RNG, no
//! pool mutation and no slot index leaves this module as an identity.
//!
//! The planner allocates only the diverted fraction `d = 1 - urban farm
//! factor` the caller supplies per site; it never subtracts farm time again
//! (the economy's `farm_labor_factor` already removed it). Health care is
//! rural-only and teaching is Scholar-only, so in the current model those
//! consumers are disjoint by predicate; the explicit exclusion keeps one
//! authority if that changes.
use std::collections::{HashMap, HashSet};

use crate::agent::{Occupation, AGE_ADULT};
use crate::pool::AgentPool;

pub const MAX_SITES: usize = 4;
pub const MAX_WORKERS_PER_SITE: usize = 8;

#[derive(Clone, Debug, PartialEq)]
pub struct SiteRequest {
    pub site: u16,
    pub region: u16,
    pub settlement_id: u16,
    pub diverted_fraction: f32,
    pub max_workers: u8,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct SiteCrew {
    pub site: u16,
    pub region: u16,
    pub settlement_id: u16,
    /// Living adult farmers resident in the settlement and region.
    pub resident_adult_farmers: u32,
    pub excluded_trip: u32,
    pub excluded_army: u32,
    pub excluded_assigned: u32,
    /// Eligible after every exclusion, before the per-site cap.
    pub eligible: u32,
    /// Selected stable ids (ascending), at most `max_workers`.
    pub crew: Vec<u32>,
    pub crew_ages: Vec<u16>,
    /// Sum of the crew's available diverted fractions.
    pub work_available: f32,
}

pub fn validate(sites: &[SiteRequest]) -> Result<(), &'static str> {
    if sites.len() > MAX_SITES {
        return Err("at most four workshop sites");
    }
    let mut regions = HashSet::new();
    let mut settlements = HashSet::new();
    let mut ids = HashSet::new();
    for s in sites {
        if s.settlement_id == 0 {
            return Err("workshop site needs a city settlement id");
        }
        if !(s.diverted_fraction > 0.0 && s.diverted_fraction <= 1.0) {
            return Err("diverted fraction must be in (0, 1]");
        }
        if s.max_workers == 0 || s.max_workers as usize > MAX_WORKERS_PER_SITE {
            return Err("max workers must be 1..=8");
        }
        if !regions.insert(s.region) || !settlements.insert(s.settlement_id) || !ids.insert(s.site) {
            return Err("workshop sites need distinct ids, regions and settlements");
        }
    }
    Ok(())
}

/// Resolve crews in one pass over the pool; returns rows in request order.
pub fn plan_crews(pool: &AgentPool, sites: &[SiteRequest], enlisted: &HashSet<u32>)
    -> Result<Vec<SiteCrew>, &'static str> {
    validate(sites)?;
    let mut assigned: HashSet<u32> = pool.health_work_loss.iter().map(|(id, _)| *id).collect();
    if let Some(plan) = pool.teaching_plan.as_ref() {
        assigned.extend(plan.rows.iter().map(|row| row.agent_id));
    }
    let by_settlement: HashMap<u16, usize> =
        sites.iter().enumerate().map(|(i, s)| (s.settlement_id, i)).collect();
    let mut rows: Vec<SiteCrew> = sites.iter().map(|s| SiteCrew {
        site: s.site, region: s.region, settlement_id: s.settlement_id, ..Default::default()
    }).collect();
    let mut candidates: Vec<Vec<(u32, u16)>> = vec![Vec::new(); sites.len()];
    let farmer = Occupation::Farmer as u8;
    for slot in 0..pool.ids.len() {
        if !pool.is_alive(slot) || pool.occupations[slot] != farmer || pool.ages[slot] < AGE_ADULT {
            continue;
        }
        let Some(&i) = by_settlement.get(&pool.settlement_ids[slot]) else { continue };
        if pool.regions[slot] != sites[i].region {
            continue;
        }
        let row = &mut rows[i];
        row.resident_adult_farmers += 1;
        let id = pool.ids[slot];
        if pool.is_on_trip(slot) {
            row.excluded_trip += 1;
        } else if enlisted.contains(&id) {
            row.excluded_army += 1;
        } else if assigned.contains(&id) {
            row.excluded_assigned += 1;
        } else {
            candidates[i].push((id, pool.ages[slot]));
        }
    }
    for (i, site) in sites.iter().enumerate() {
        let mut list = std::mem::take(&mut candidates[i]);
        list.sort_unstable_by_key(|(id, _)| *id);
        let row = &mut rows[i];
        row.eligible = list.len() as u32;
        for (id, age) in list.into_iter().take(site.max_workers as usize) {
            // Distinct settlements make a second claim impossible; keep the
            // shared authority explicit anyway.
            if assigned.insert(id) {
                row.crew.push(id);
                row.crew_ages.push(age);
            }
        }
        row.work_available = row.crew.len() as f32 * site.diverted_fraction;
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    fn pool_with(rows: &[(u16, u16, Occupation, u16)]) -> AgentPool {
        // (region, settlement, occupation, age)
        let mut pool = AgentPool::new(rows.len());
        for &(region, settlement, occ, age) in rows {
            let slot = pool.spawn(region, 0, occ, age, 0.5, 0.5, 0.5, 0, 1, 2, 0);
            pool.settlement_ids[slot] = settlement;
        }
        pool
    }

    fn site(site: u16, region: u16, settlement: u16) -> SiteRequest {
        SiteRequest { site, region, settlement_id: settlement, diverted_fraction: 0.2, max_workers: 8 }
    }

    #[test]
    fn eligibility_excludes_children_other_occupations_rural_and_other_cities() {
        let pool = pool_with(&[
            (0, 5, Occupation::Farmer, 30), (0, 5, Occupation::Farmer, 19),
            (0, 5, Occupation::Merchant, 30), (0, 5, Occupation::Scholar, 30),
            (0, 0, Occupation::Farmer, 30), (0, 6, Occupation::Farmer, 30),
            (1, 5, Occupation::Farmer, 30),
        ]);
        let rows = plan_crews(&pool, &[site(0, 0, 5)], &HashSet::new()).unwrap();
        assert_eq!(rows[0].resident_adult_farmers, 1);
        assert_eq!(rows[0].crew, vec![pool.ids[0]]);
        assert!((rows[0].work_available - 0.2).abs() < 1e-6);
    }

    #[test]
    fn army_trip_and_existing_assignments_are_excluded_and_counted() {
        let mut pool = pool_with(&[(0, 5, Occupation::Farmer, 30); 4]);
        pool.health_work_loss.push((pool.ids[2], 0.5));
        pool.trip_phase[3] = 1;
        let enlisted: HashSet<u32> = [pool.ids[1]].into_iter().collect();
        let rows = plan_crews(&pool, &[site(0, 0, 5)], &enlisted).unwrap();
        let r = &rows[0];
        assert_eq!((r.resident_adult_farmers, r.excluded_army, r.excluded_assigned, r.excluded_trip, r.eligible),
                   (4, 1, 1, 1, 1));
        assert_eq!(r.crew, vec![pool.ids[0]]);
    }

    #[test]
    fn cap_is_eight_by_ascending_id_and_dead_are_skipped() {
        let mut pool = pool_with(&[(0, 5, Occupation::Farmer, 40); 11]);
        pool.kill(0);
        let rows = plan_crews(&pool, &[site(0, 0, 5)], &HashSet::new()).unwrap();
        assert_eq!(rows[0].eligible, 10);
        assert_eq!(rows[0].crew.len(), 8);
        let mut expected: Vec<u32> = (1..11).map(|s| pool.ids[s]).collect();
        expected.sort_unstable();
        assert_eq!(rows[0].crew, expected[..8].to_vec());
        assert!((rows[0].work_available - 1.6).abs() < 1e-5);
    }

    #[test]
    fn invalid_requests_are_refused_without_a_plan() {
        let pool = pool_with(&[]);
        let mut bad = site(0, 0, 5);
        bad.max_workers = 9;
        assert!(plan_crews(&pool, &[bad], &HashSet::new()).is_err());
        assert!(plan_crews(&pool, &[site(0, 0, 5), site(1, 0, 6)], &HashSet::new()).is_err());
        assert!(plan_crews(&pool, &[site(0, 0, 0)], &HashSet::new()).is_err());
        let five: Vec<SiteRequest> = (0..5).map(|i| site(i, i, i + 1)).collect();
        assert!(plan_crews(&pool, &five, &HashSet::new()).is_err());
    }
}
