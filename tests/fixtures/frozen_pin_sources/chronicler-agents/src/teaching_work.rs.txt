//! One-turn, transient Scholar work reservation. No worker identities are
//! invented; the native Scholar's ordinary income competes with teaching.
use std::collections::HashSet;
use crate::{agent::{AGE_ADULT, Occupation}, pool::AgentPool};

pub const MAX_RECEIPTS: usize = 128;

#[derive(Clone, Debug)]
pub struct TeachingRow {
    pub slot: usize, pub agent_id: u32, pub region: u16,
    pub fraction: f32, pub delivered: f32,
}

#[derive(Clone, Debug)]
pub struct TeachingPlan {
    pub source_turn: u32,
    pub requested: Vec<f32>, pub available: Vec<f64>,
    pub rows: Vec<TeachingRow>, pub consumed: bool,
}

impl TeachingPlan {
    /// Region id, available, requested, reserved, actually consumed. The
    /// latter is zero until the wealth phase confirms each live identity.
    pub fn regions(&self) -> Vec<(u16, f64, f64, f64, f64)> {
        let mut reserved = vec![0.0f64; self.requested.len()];
        let mut consumed = vec![0.0f64; self.requested.len()];
        for row in &self.rows {
            reserved[row.region as usize] += row.fraction as f64;
            consumed[row.region as usize] += row.delivered as f64;
        }
        self.requested.iter().enumerate().map(|(i, &request)|
            (i as u16, self.available[i], request as f64, reserved[i], consumed[i])).collect()
    }

    /// Sample includes the reserved and actually consumed work fractions;
    /// dropped counts all reserved rows beyond the bounded sample.
    pub fn receipts(&self) -> (Vec<(u32, u16, f32, f32)>, usize) {
        (self.rows.iter().take(MAX_RECEIPTS).map(|r|
            (r.agent_id, r.region, r.fraction, r.delivered)).collect(),
         self.rows.len().saturating_sub(MAX_RECEIPTS))
    }
}

/// Build without mutation; caller installs only after all validation succeeds.
pub fn prepare(pool: &AgentPool, turn: u32, requested: &[f32], excluded: &[u32]) -> Result<Option<TeachingPlan>, &'static str> {
    if requested.iter().any(|v| !v.is_finite() || *v < 0.0) {
        return Err("teaching work requests must be finite and nonnegative");
    }
    if requested.iter().all(|v| *v == 0.0) { return Ok(None); }
    let excluded: HashSet<u32> = excluded.iter().copied().collect();
    let mut slots: Vec<usize> = (0..pool.capacity()).filter(|&slot| {
        pool.is_alive(slot) && pool.ages[slot] >= AGE_ADULT
            && pool.occupations[slot] == Occupation::Scholar as u8
            && !pool.is_on_trip(slot) && !excluded.contains(&pool.ids[slot])
            && (pool.regions[slot] as usize) < requested.len()
            && requested[pool.regions[slot] as usize] > 0.0
    }).collect();
    slots.sort_unstable_by_key(|&slot| pool.ids[slot]);
    let mut plan = TeachingPlan { source_turn: turn, requested: requested.to_vec(),
        available: vec![0.0; requested.len()], rows: Vec::new(), consumed: false };
    let mut remaining = requested.to_vec();
    for slot in slots {
        let region = pool.regions[slot] as usize;
        let health = pool.health_work_loss.get(slot)
            .filter(|&&(id, _)| id == pool.ids[slot]).map_or(0.0, |&(_, value)| value);
        if !health.is_finite() || !(0.0..=1.0).contains(&health) {
            return Err("invalid existing health work loss");
        }
        let capacity = 1.0 - health;
        plan.available[region] += capacity as f64;
        let amount = capacity.min(remaining[region]);
        if amount > 0.0 {
            plan.rows.push(TeachingRow { slot, agent_id: pool.ids[slot], region: region as u16,
                fraction: amount, delivered: 0.0 });
            remaining[region] = (remaining[region] - amount).max(0.0);
        }
    }
    Ok(Some(plan))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn scholar(pool: &mut AgentPool, region: u16, age: u16) -> usize {
        pool.spawn(region, 0, Occupation::Scholar, age, 0.0, 0.0, 0.0, 255, 255, 255, 255)
    }
    #[test]
    fn teaching_work_eligible_fractional_shared_budget() {
        let mut pool = AgentPool::new(10);
        let a = scholar(&mut pool, 0, 25); let b = scholar(&mut pool, 0, 26);
        let child = scholar(&mut pool, 0, AGE_ADULT-1);
        let trip = scholar(&mut pool, 0, 25); pool.trip_phase[trip] = crate::agent::TRIP_PHASE_TRANSIT;
        let excluded = scholar(&mut pool, 0, 25);
        let dead = scholar(&mut pool, 0, 25); pool.kill(dead);
        let other = scholar(&mut pool, 1, 25);
        pool.health_work_loss.resize(pool.capacity(), (0, 0.0));
        pool.health_work_loss[a] = (pool.ids[a], 0.25);
        let p = prepare(&pool, 5, &[1.25, 0.0], &[pool.ids[excluded]]).unwrap().unwrap();
        assert_eq!(p.regions()[0], (0, 1.75, 1.25, 1.25, 0.0));
        assert_eq!(p.rows.len(), 2);
        assert_eq!((p.rows[0].agent_id, p.rows[0].fraction), (pool.ids[a], 0.75));
        assert_eq!((p.rows[1].agent_id, p.rows[1].fraction), (pool.ids[b], 0.5));
        assert!(!p.rows.iter().any(|row| [pool.ids[child], pool.ids[trip], pool.ids[excluded], pool.ids[other]].contains(&row.agent_id)));
        assert_eq!(p.regions()[1], (1, 0.0, 0.0, 0.0, 0.0));
    }
    #[test]
    fn teaching_work_invalid_and_zero_do_not_create_plan() {
        let pool = AgentPool::new(1);
        assert!(prepare(&pool, 0, &[0.0], &[]).unwrap().is_none());
        for bad in [-1.0, f32::NAN, f32::INFINITY] {
            assert!(prepare(&pool, 0, &[bad], &[]).is_err());
        }
        assert!(pool.teaching_plan.is_none());
    }
    #[test]
    fn teaching_work_receipts_are_bounded_not_work_capped() {
        let mut pool = AgentPool::new(130);
        for _ in 0..130 { scholar(&mut pool, 0, 25); }
        let p = prepare(&pool, 0, &[130.0], &[]).unwrap().unwrap();
        assert_eq!(p.regions()[0].3, 130.0);
        assert_eq!(p.receipts().0.len(), MAX_RECEIPTS);
        assert_eq!(p.receipts().1, 2);
    }
}
