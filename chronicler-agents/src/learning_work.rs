//! Livelihoods L5 (default off): named learners' academy attendance.
//!
//! Python owns cohorts (stable ids, progress, completion). This module owns
//! the native facts around one tick, keyed by stable agent ids:
//!
//! 1. [`plan`] (read-only): for each academy cohort, the availability of its
//!    enrolled members and, for a forming cohort, eligible recruits: living
//!    adults who are not Scholars (Scholars teach), resident in the academy's
//!    region, not on a merchant trip, not on an army roster (ids supplied by
//!    the caller), not already holding work this turn (the shared registry,
//!    positive rural health work or a pending teaching plan) and with room to
//!    learn (skill in their current occupation at most `max_skill`). Recruits
//!    are ordered by ascending current skill, then stable id.
//! 2. [`reserve`]: commit the attending learners in the shared work registry
//!    (category learning) and install a one-turn attendance plan.
//! 3. The wealth phase ([`begin`], [`charge`], [`end`]): a learner is seated
//!    only while this turn's actual teaching delivers seats in that region;
//!    each delivered Scholar work unit seats `learners_per_teacher` learners,
//!    as academy services serves learner-equivalents. A seated learner's
//!    ordinary occupational income is reduced by the attended fraction (the
//!    actual cost of study). Unseated learners keep their income.
//!
//! [`grant`] raises a graduate's skill in the learned occupation by a gain
//! (never above `SKILL_MAX`), or reads it when the gain is zero (the
//! no-learning control). No randomness; the plan is never checkpointed.
use std::collections::HashSet;

use crate::agent::{Occupation, AGE_ADULT, SKILL_MAX};
use crate::pool::AgentPool;
use crate::teaching_work::TeachingPlan;
use crate::workshop_work::{holders, reserve as reserve_work, CATEGORY_LEARNING};

pub const MAX_COHORTS: usize = 8;
pub const MAX_MEMBERS: usize = 8;
pub const MAX_ATTENDANCE: usize = MAX_COHORTS * MAX_MEMBERS;

/// Member availability codes, in declaration order (append only).
pub const STATUS_AVAILABLE: u8 = 0;
pub const STATUS_DEAD: u8 = 1;
pub const STATUS_ELSEWHERE: u8 = 2;
pub const STATUS_TRIP: u8 = 3;
pub const STATUS_ARMY: u8 = 4;
pub const STATUS_ASSIGNED: u8 = 5;
pub const STATUS_NOT_ELIGIBLE: u8 = 6;

/// Attendance outcomes, in declaration order (append only).
pub const OUTCOME_PENDING: u8 = 0;
pub const OUTCOME_ATTENDED: u8 = 1;
pub const OUTCOME_NO_SEAT: u8 = 2;
pub const OUTCOME_ABSENT: u8 = 3;

#[derive(Clone, Debug, PartialEq)]
pub struct CohortRequest {
    pub region: u16,
    /// Enrolled, still active member ids.
    pub members: Vec<u32>,
    /// Recruits wanted (0 for a formed cohort: cohorts are finite).
    pub recruit: u8,
    pub max_skill: f32,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct CohortPlan {
    /// (id, status, current occupation, current-occupation skill); the last
    /// two are 0 for a dead or unknown id.
    pub members: Vec<(u32, u8, u8, f32)>,
    /// (id, occupation, current-occupation skill, age), at most `recruit`.
    pub recruits: Vec<(u32, u8, f32, u16)>,
    /// Living resident adults, then exclusions in rule order, then eligible.
    pub resident_adults: u32,
    pub excluded_scholar: u32,
    pub excluded_member: u32,
    pub excluded_trip: u32,
    pub excluded_army: u32,
    pub excluded_assigned: u32,
    pub excluded_skilled: u32,
    pub eligible: u32,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttendanceRow {
    pub agent_id: u32,
    pub region: u16,
    pub fraction: f32,
    pub outcome: u8,
    /// Ordinary income before the deduction, and the amount withheld.
    pub income: f32,
    pub charged: f32,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttendancePlan {
    pub turn: u32,
    pub learners_per_teacher: f32,
    pub rows: Vec<AttendanceRow>,
    /// Per region: delivered Scholar work and the seats it made (filled at
    /// the wealth phase; empty before).
    pub delivered: Vec<f64>,
    pub seats: Vec<u32>,
    pub consumed: bool,
}

/// The wealth phase's working copy (taken out of the pool for the loop).
pub struct Attendance {
    plan: AttendancePlan,
    by_slot: Vec<Option<usize>>,
}

fn valid_skill_bound(v: f32) -> bool {
    v.is_finite() && (0.0..=SKILL_MAX).contains(&v)
}

/// Read-only availability and recruitment; requests have distinct regions.
pub fn plan(pool: &AgentPool, turn: u32, requests: &[CohortRequest], enlisted: &HashSet<u32>,
            num_regions: usize) -> Result<Vec<CohortPlan>, &'static str> {
    if requests.len() > MAX_COHORTS {
        return Err("at most eight learning cohorts");
    }
    let mut regions = HashSet::new();
    let mut members: HashSet<u32> = HashSet::new();
    for r in requests {
        if r.region as usize >= num_regions {
            return Err("learning cohort region out of range");
        }
        if !regions.insert(r.region) {
            return Err("learning cohorts need distinct regions");
        }
        if r.members.len() + r.recruit as usize > MAX_MEMBERS {
            return Err("at most eight learners per cohort");
        }
        if !valid_skill_bound(r.max_skill) {
            return Err("learning skill bound must be finite in 0..=1");
        }
        for &id in &r.members {
            if !members.insert(id) {
                return Err("a learner belongs to one cohort");
            }
        }
    }
    let held: HashSet<u32> = holders(pool, turn).into_iter().map(|(id, _)| id).collect();
    let ids = pool.build_id_slots();
    let mut out: Vec<CohortPlan> = Vec::with_capacity(requests.len());
    let scholar = Occupation::Scholar as u8;
    for r in requests {
        let mut row = CohortPlan::default();
        for &id in &r.members {
            let Some(slot) = ids.get(id) else {
                row.members.push((id, STATUS_DEAD, 0, 0.0));
                continue;
            };
            let occ = pool.occupations[slot];
            let skill = pool.skills[slot * 5 + occ as usize];
            let status = if pool.regions[slot] != r.region {
                STATUS_ELSEWHERE
            } else if occ == scholar || pool.ages[slot] < AGE_ADULT {
                STATUS_NOT_ELIGIBLE
            } else if pool.is_on_trip(slot) {
                STATUS_TRIP
            } else if enlisted.contains(&id) {
                STATUS_ARMY
            } else if held.contains(&id) {
                STATUS_ASSIGNED
            } else {
                STATUS_AVAILABLE
            };
            row.members.push((id, status, occ, skill));
        }
        out.push(row);
    }
    // One pass over the pool for every forming cohort.
    let forming: Vec<usize> = (0..requests.len()).filter(|&i| requests[i].recruit > 0).collect();
    if !forming.is_empty() {
        let mut candidates: Vec<Vec<(f32, u32, u8, u16)>> = vec![Vec::new(); requests.len()];
        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) || pool.ages[slot] < AGE_ADULT {
                continue;
            }
            let Some(&i) = forming.iter().find(|&&i| requests[i].region == pool.regions[slot]) else { continue };
            let row = &mut out[i];
            row.resident_adults += 1;
            let id = pool.ids[slot];
            let occ = pool.occupations[slot];
            let skill = pool.skills[slot * 5 + occ as usize];
            if occ == scholar {
                row.excluded_scholar += 1;
            } else if members.contains(&id) {
                row.excluded_member += 1;
            } else if pool.is_on_trip(slot) {
                row.excluded_trip += 1;
            } else if enlisted.contains(&id) {
                row.excluded_army += 1;
            } else if held.contains(&id) {
                row.excluded_assigned += 1;
            } else if !(skill <= requests[i].max_skill) {
                row.excluded_skilled += 1;
            } else {
                candidates[i].push((skill, id, occ, pool.ages[slot]));
            }
        }
        for &i in &forming {
            let mut list = std::mem::take(&mut candidates[i]);
            list.sort_unstable_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
            out[i].eligible = list.len() as u32;
            out[i].recruits = list.into_iter().take(requests[i].recruit as usize)
                .map(|(skill, id, occ, age)| (id, occ, skill, age)).collect();
        }
    }
    Ok(out)
}

/// Validate, reserve in the shared registry, then install; all or none.
pub fn reserve(pool: &mut AgentPool, turn: u32, learners_per_teacher: f32, rows: &[(u32, u16, f32)],
               num_regions: usize) -> Result<(), &'static str> {
    if pool.learning_attendance.as_ref().is_some_and(|p| !p.consumed) {
        return Err("learning attendance already pending");
    }
    if !(learners_per_teacher.is_finite() && learners_per_teacher > 0.0 && learners_per_teacher <= 64.0) {
        return Err("learners per teacher must be finite in (0, 64]");
    }
    if rows.is_empty() || rows.len() > MAX_ATTENDANCE {
        return Err("learning attendance needs 1..=64 learners");
    }
    let ids = pool.build_id_slots();
    for &(id, region, fraction) in rows {
        if region as usize >= num_regions {
            return Err("learning attendance region out of range");
        }
        if !(fraction > 0.0 && fraction <= 1.0) {
            return Err("attendance fraction must be in (0, 1]");
        }
        match ids.get(id) {
            Some(slot) if pool.regions[slot] == region && pool.ages[slot] >= AGE_ADULT
                && pool.occupations[slot] != Occupation::Scholar as u8 => {}
            _ => return Err("a learner must be a living adult non-Scholar in the academy's region"),
        }
    }
    let pairs: Vec<(u32, f32)> = rows.iter().map(|&(id, _, fraction)| (id, fraction)).collect();
    reserve_work(pool, turn, CATEGORY_LEARNING, &pairs)?;
    pool.learning_attendance = Some(AttendancePlan {
        turn, learners_per_teacher,
        rows: rows.iter().map(|&(agent_id, region, fraction)| AttendanceRow {
            agent_id, region, fraction, outcome: OUTCOME_PENDING, income: 0.0, charged: 0.0 }).collect(),
        delivered: Vec::new(), seats: Vec::new(), consumed: false,
    });
    Ok(())
}

/// The tick refuses an unconsumed plan prepared for another turn.
pub fn check_tick(pool: &AgentPool, turn: u32) -> Result<(), &'static str> {
    match &pool.learning_attendance {
        Some(plan) if !plan.consumed && plan.turn != turn =>
            Err("learning attendance must be prepared for this tick"),
        _ => Ok(()),
    }
}

/// Drop an unconsumed plan for `turn` and its registry rows.
pub fn cancel(pool: &mut AgentPool, turn: u32) -> bool {
    match &pool.learning_attendance {
        Some(plan) if !plan.consumed && plan.turn == turn => {
            pool.learning_attendance = None;
            pool.work_reservations.retain(|r| !(r.turn == turn && r.category == CATEGORY_LEARNING));
            true
        }
        _ => false,
    }
}

/// The consumed plan of `turn`, taken once.
pub fn take(pool: &mut AgentPool, turn: u32) -> Option<AttendancePlan> {
    if pool.learning_attendance.as_ref().is_some_and(|p| p.consumed && p.turn == turn) {
        pool.learning_attendance.take()
    } else {
        None
    }
}

/// Wealth phase start: seat learners from this turn's actual teaching.
///
/// Delivered teaching per region is computed exactly as the wealth loop
/// delivers it (live Scholar, same id and region, capped by existing health
/// work loss); nothing the loop reads for it changes during the loop.
pub fn begin(pool: &mut AgentPool, teaching: Option<&TeachingPlan>, health_loss: &[(u32, f32)])
    -> Option<Attendance> {
    let mut plan = pool.learning_attendance.take().filter(|p| !p.consumed)?;
    let regions = teaching.map_or(0, |t| t.requested.len());
    let mut delivered = vec![0.0f64; regions];
    if let Some(teaching) = teaching {
        for row in &teaching.rows {
            let slot = row.slot;
            if slot < pool.capacity() && pool.is_alive(slot)
                && pool.occupations[slot] == Occupation::Scholar as u8
                && pool.ids[slot] == row.agent_id && pool.regions[slot] == row.region
                && (row.region as usize) < regions {
                let loss = health_loss.get(slot).filter(|&&(id, _)| id == row.agent_id)
                    .map_or(0.0, |&(_, value)| value.clamp(0.0, 1.0));
                delivered[row.region as usize] += row.fraction.min((1.0 - loss).max(0.0)) as f64;
            }
        }
    }
    let mut seats: Vec<u32> = delivered.iter()
        .map(|&d| (d * plan.learners_per_teacher as f64 + 1e-6).floor().clamp(0.0, MAX_ATTENDANCE as f64) as u32)
        .collect();
    plan.delivered = delivered;
    plan.seats = seats.clone();
    let ids = pool.build_id_slots();
    let mut by_slot = vec![None; pool.capacity()];
    for (i, row) in plan.rows.iter_mut().enumerate() {
        match ids.get(row.agent_id) {
            Some(slot) if pool.regions[slot] == row.region && pool.ages[slot] >= AGE_ADULT
                && pool.occupations[slot] != Occupation::Scholar as u8 => {
                let r = row.region as usize;
                if r < seats.len() && seats[r] > 0 {
                    seats[r] -= 1;
                    by_slot[slot] = Some(i);
                } else {
                    row.outcome = OUTCOME_NO_SEAT;
                }
            }
            _ => row.outcome = OUTCOME_ABSENT,
        }
    }
    Some(Attendance { plan, by_slot })
}

/// In the wealth loop, after teaching: withhold a seated learner's share.
#[inline]
pub fn charge(attendance: &mut Option<Attendance>, slot: usize, id: u32, income: f32) -> f32 {
    let Some(a) = attendance else { return income };
    let Some(i) = a.by_slot.get(slot).copied().flatten() else { return income };
    let row = &mut a.plan.rows[i];
    if row.agent_id != id || row.outcome != OUTCOME_PENDING {
        return income;
    }
    let kept = income * (1.0 - row.fraction);
    row.income = income;
    row.charged = income - kept;
    row.outcome = OUTCOME_ATTENDED;
    kept
}

/// Wealth phase end: a seat the loop never charged is an absence.
pub fn end(pool: &mut AgentPool, attendance: Option<Attendance>) {
    let Some(Attendance { mut plan, .. }) = attendance else { return };
    for row in &mut plan.rows {
        if row.outcome == OUTCOME_PENDING {
            row.outcome = OUTCOME_ABSENT;
        }
    }
    plan.consumed = true;
    pool.learning_attendance = Some(plan);
}

/// Raise (gain > 0) or read (gain == 0) each living graduate's skill in the
/// learned occupation. Returns (id, occupation, alive, before, after).
pub fn grant(pool: &mut AgentPool, rows: &[(u32, u8, f32)]) -> Result<Vec<(u32, u8, bool, f32, f32)>, &'static str> {
    if rows.len() > MAX_ATTENDANCE {
        return Err("at most 64 skill grants at once");
    }
    let mut seen = HashSet::new();
    for &(id, occ, gain) in rows {
        if occ as usize >= 5 || !gain.is_finite() || !(0.0..=SKILL_MAX).contains(&gain) || !seen.insert(id) {
            return Err("skill grants need distinct ids, an occupation code and a gain in 0..=1");
        }
    }
    let ids = pool.build_id_slots();
    Ok(rows.iter().map(|&(id, occ, gain)| match ids.get(id) {
        Some(slot) => {
            let index = slot * 5 + occ as usize;
            let before = pool.skills[index];
            if gain > 0.0 {
                pool.skills[index] = (before + gain).min(SKILL_MAX);
            }
            (id, occ, true, before, pool.skills[index])
        }
        None => (id, occ, false, 0.0, 0.0),
    }).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::teaching_work;

    fn spawn(pool: &mut AgentPool, region: u16, occ: Occupation, age: u16) -> usize {
        pool.spawn(region, 0, occ, age, 0.5, 0.5, 0.5, 0, 1, 2, 0)
    }

    fn request(region: u16, members: Vec<u32>, recruit: u8) -> CohortRequest {
        CohortRequest { region, members, recruit, max_skill: 0.75 }
    }

    #[test]
    fn recruits_are_present_unassigned_adults_with_room_to_learn() {
        let mut pool = AgentPool::new(16);
        let a = spawn(&mut pool, 0, Occupation::Farmer, 30);
        let b = spawn(&mut pool, 0, Occupation::Merchant, 30);
        let child = spawn(&mut pool, 0, Occupation::Farmer, AGE_ADULT - 1);
        let teacher = spawn(&mut pool, 0, Occupation::Scholar, 30);
        let trip = spawn(&mut pool, 0, Occupation::Farmer, 30);
        pool.trip_phase[trip] = crate::agent::TRIP_PHASE_TRANSIT;
        let army = spawn(&mut pool, 0, Occupation::Soldier, 30);
        let carer = spawn(&mut pool, 0, Occupation::Farmer, 30);
        let skilled = spawn(&mut pool, 0, Occupation::Priest, 30);
        let other = spawn(&mut pool, 1, Occupation::Farmer, 30);
        let dead = spawn(&mut pool, 0, Occupation::Farmer, 30);
        pool.kill(dead);
        pool.health_work_loss = vec![(0, 0.0); pool.capacity()];
        pool.health_work_loss[carer] = (pool.ids[carer], 0.5);
        pool.skills[skilled * 5 + 4] = 0.8;
        pool.skills[a * 5] = 0.4;
        pool.skills[b * 5 + 2] = 0.1;
        let enlisted: HashSet<u32> = [pool.ids[army]].into_iter().collect();
        let rows = plan(&pool, 3, &[request(0, vec![], 8)], &enlisted, 2).unwrap();
        let r = &rows[0];
        assert_eq!((r.resident_adults, r.excluded_scholar, r.excluded_trip, r.excluded_army,
                    r.excluded_assigned, r.excluded_skilled, r.eligible), (7, 1, 1, 1, 1, 1, 2));
        // Lowest current skill first, then stable id.
        assert_eq!(r.recruits.iter().map(|x| x.0).collect::<Vec<_>>(), vec![pool.ids[b], pool.ids[a]]);
        assert!(!r.recruits.iter().any(|x| [pool.ids[child], pool.ids[teacher], pool.ids[other]].contains(&x.0)));
    }

    #[test]
    fn member_status_reports_death_departure_and_unavailability() {
        let mut pool = AgentPool::new(8);
        let s: Vec<usize> = (0..6).map(|_| spawn(&mut pool, 0, Occupation::Farmer, 30)).collect();
        let ids: Vec<u32> = s.iter().map(|&x| pool.ids[x]).collect();
        pool.kill(s[1]);
        pool.set_region(s[2], 1);
        pool.trip_phase[s[3]] = crate::agent::TRIP_PHASE_TRANSIT;
        reserve_work(&mut pool, 4, crate::workshop_work::CATEGORY_WORKSHOP, &[(ids[5], 0.2)]).unwrap();
        let enlisted: HashSet<u32> = [ids[4]].into_iter().collect();
        let rows = plan(&pool, 4, &[request(0, ids.clone(), 0)], &enlisted, 2).unwrap();
        let statuses: Vec<u8> = rows[0].members.iter().map(|m| m.1).collect();
        assert_eq!(statuses, vec![STATUS_AVAILABLE, STATUS_DEAD, STATUS_ELSEWHERE, STATUS_TRIP,
                                  STATUS_ARMY, STATUS_ASSIGNED]);
        assert!(rows[0].recruits.is_empty() && rows[0].resident_adults == 0);
    }

    #[test]
    fn invalid_requests_are_refused() {
        let pool = AgentPool::new(1);
        let none = HashSet::new();
        assert!(plan(&pool, 0, &[request(0, vec![], 8), request(0, vec![], 1)], &none, 2).is_err());
        assert!(plan(&pool, 0, &[request(2, vec![], 1)], &none, 2).is_err());
        assert!(plan(&pool, 0, &[request(0, vec![1, 2], 7)], &none, 2).is_err());
        assert!(plan(&pool, 0, &[request(0, vec![1], 0), request(1, vec![1], 0)], &none, 2).is_err());
        let mut bad = request(0, vec![], 1);
        bad.max_skill = f32::NAN;
        assert!(plan(&pool, 0, &[bad], &none, 2).is_err());
    }

    fn teaching(pool: &AgentPool, region: u16, amount: f32) -> TeachingPlan {
        let mut req = vec![0.0; 2];
        req[region as usize] = amount;
        teaching_work::prepare(pool, 5, &req, &[]).unwrap().unwrap()
    }

    #[test]
    fn seats_come_only_from_delivered_teaching_and_cost_the_attended_share() {
        let mut pool = AgentPool::new(16);
        let _teacher = spawn(&mut pool, 0, Occupation::Scholar, 30);
        let learners: Vec<usize> = (0..6).map(|_| spawn(&mut pool, 0, Occupation::Farmer, 30)).collect();
        let rows: Vec<(u32, u16, f32)> = learners.iter().map(|&s| (pool.ids[s], 0u16, 0.5f32)).collect();
        reserve(&mut pool, 5, 8.0, &rows, 2).unwrap();
        assert!(reserve(&mut pool, 5, 8.0, &rows, 2).is_err());          // already pending
        assert!(check_tick(&pool, 6).is_err() && check_tick(&pool, 5).is_ok());
        assert_eq!(pool.work_reservations.len(), 6);
        // A half Scholar-day seats four learners; the rest have no seat.
        let plan_t = teaching(&pool, 0, 0.5);
        let mut active = begin(&mut pool, Some(&plan_t), &[]);
        assert!(pool.learning_attendance.is_none());
        for &slot in &learners {
            let kept = charge(&mut active, slot, pool.ids[slot], 2.0);
            assert!(kept == 1.0 || kept == 2.0);
        }
        end(&mut pool, active);
        let result = take(&mut pool, 5).unwrap();
        assert_eq!(result.seats, vec![4, 0]);
        let outcomes: Vec<u8> = result.rows.iter().map(|r| r.outcome).collect();
        assert_eq!(outcomes, vec![1, 1, 1, 1, 2, 2]);
        assert!(result.rows[..4].iter().all(|r| r.income == 2.0 && r.charged == 1.0));
        assert!(result.rows[4..].iter().all(|r| r.charged == 0.0));
        assert!(take(&mut pool, 5).is_none());
    }

    #[test]
    fn no_teaching_means_no_seat_and_no_cost() {
        let mut pool = AgentPool::new(4);
        let learner = spawn(&mut pool, 0, Occupation::Merchant, 30);
        let id = pool.ids[learner];
        reserve(&mut pool, 2, 8.0, &[(id, 0, 0.5)], 1).unwrap();
        let mut active = begin(&mut pool, None, &[]);
        assert_eq!(charge(&mut active, learner, id, 3.0), 3.0);
        end(&mut pool, active);
        let result = take(&mut pool, 2).unwrap();
        assert_eq!((result.rows[0].outcome, result.rows[0].charged), (OUTCOME_NO_SEAT, 0.0));
    }

    #[test]
    fn a_dead_learner_is_absent_and_cancel_releases_the_registry() {
        let mut pool = AgentPool::new(8);
        let _teacher = spawn(&mut pool, 0, Occupation::Scholar, 30);
        let a = spawn(&mut pool, 0, Occupation::Farmer, 30);
        let b = spawn(&mut pool, 0, Occupation::Farmer, 30);
        let (ia, ib) = (pool.ids[a], pool.ids[b]);
        reserve(&mut pool, 1, 8.0, &[(ia, 0, 0.5), (ib, 0, 0.5)], 1).unwrap();
        pool.kill(a);
        let plan_t = {
            let mut req = vec![0.0; 1];
            req[0] = 1.0;
            teaching_work::prepare(&pool, 1, &req, &[]).unwrap().unwrap()
        };
        let mut active = begin(&mut pool, Some(&plan_t), &[]);
        charge(&mut active, b, ib, 1.0);
        end(&mut pool, active);
        let result = take(&mut pool, 1).unwrap();
        assert_eq!(result.rows.iter().map(|r| r.outcome).collect::<Vec<_>>(), vec![OUTCOME_ABSENT, OUTCOME_ATTENDED]);
        let c = spawn(&mut pool, 0, Occupation::Farmer, 30);
        let ic = pool.ids[c];
        reserve(&mut pool, 2, 8.0, &[(ic, 0, 0.5)], 1).unwrap();
        assert!(!cancel(&mut pool, 3));
        assert!(cancel(&mut pool, 2));
        assert!(pool.learning_attendance.is_none() && pool.work_reservations.is_empty());
        // Invalid rows leave nothing behind.
        assert!(reserve(&mut pool, 2, 8.0, &[(ic, 1, 0.5)], 1).is_err());
        assert!(reserve(&mut pool, 2, f32::NAN, &[(ic, 0, 0.5)], 1).is_err());
        assert!(reserve(&mut pool, 2, 8.0, &[(ic, 0, 0.0)], 1).is_err());
        assert!(pool.learning_attendance.is_none() && pool.work_reservations.is_empty());
    }

    #[test]
    fn grant_is_capped_travels_with_the_agent_and_reads_when_zero() {
        let mut pool = AgentPool::new(4);
        let s = spawn(&mut pool, 0, Occupation::Soldier, 30);
        let id = pool.ids[s];
        pool.skills[s * 5 + 1] = 0.3;
        assert_eq!(grant(&mut pool, &[(id, 1, 0.0)]).unwrap(), vec![(id, 1, true, 0.3, 0.3)]);
        let got = grant(&mut pool, &[(id, 1, 0.25)]).unwrap()[0];
        assert!((got.4 - 0.55).abs() < 1e-6);
        pool.skills[s * 5 + 1] = 0.9;
        assert_eq!(grant(&mut pool, &[(id, 1, 0.25)]).unwrap()[0].4, SKILL_MAX);
        // The learned capability is the agent's: a move keeps it.
        pool.set_region(s, 1);
        assert_eq!(pool.skills[s * 5 + 1], SKILL_MAX);
        pool.kill(s);
        assert_eq!(grant(&mut pool, &[(id, 1, 0.25)]).unwrap(), vec![(id, 1, false, 0.0, 0.0)]);
        assert!(grant(&mut pool, &[(id, 5, 0.1)]).is_err());
        assert!(grant(&mut pool, &[(id, 1, -0.1)]).is_err());
        assert!(grant(&mut pool, &[(id, 1, 0.1), (id, 2, 0.1)]).is_err());
    }
}
