//! Domestic credit (`--domestic-credit`, Python `chronicler.domestic_credit`):
//! merchant agents as lenders to their lord.
//!
//! Python decides every loan, payment and write-off on its own books; this
//! module only reads and moves the wealth of merchant agents. A region's
//! merchants are the merchant agents whose home is the region: the region
//! they stand in, or for a merchant on a trip the region the trip started
//! from (as the economy and the occupational balance count them).
//!
//! * [`merchant_wealth_by_region`] reads their wealth (what they can lend).
//! * [`apply_merchant_transfers`] adds or takes the amount Python sends for
//!   each region (principal lent leaves, interest and repayments come back)
//!   and returns, per region, exactly what it changed. A debit is taken pro
//!   rata to wealth, never below zero; a credit is given pro rata to wealth
//!   (equal shares where nobody holds any), never above `MAX_WEALTH`, the
//!   rest pro rata to the room left. What could not be applied (no
//!   merchants, every one at the ceiling) is Python's to carry.
//!
//! Neither keeps any state: a call moves wealth once and reports it, so
//! nothing here is carried between ticks or checkpointed. No random draws.

use crate::agent::{Occupation, MAX_WEALTH};
use crate::pool::AgentPool;

/// A merchant's home region: where a trip started, else where it stands.
#[inline]
pub fn home_region(pool: &AgentPool, slot: usize) -> usize {
    if pool.is_on_trip(slot) {
        pool.trip_origin_region[slot] as usize
    } else {
        pool.regions[slot] as usize
    }
}

/// Merchant slots by home region (slot order within a region).
fn merchants_by_region(pool: &AgentPool, n_regions: usize) -> Vec<Vec<usize>> {
    let mut out = vec![Vec::new(); n_regions];
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) || pool.occupations[slot] != Occupation::Merchant as u8 {
            continue;
        }
        let r = home_region(pool, slot);
        if r < n_regions {
            out[r].push(slot);
        }
    }
    out
}

/// Total merchant wealth and the number of merchants per home region.
pub fn merchant_wealth_by_region(pool: &AgentPool, n_regions: usize) -> (Vec<f64>, Vec<u32>) {
    let groups = merchants_by_region(pool, n_regions);
    let wealth = groups.iter()
        .map(|slots| slots.iter().map(|&s| pool.wealth[s] as f64).sum())
        .collect();
    let counts = groups.iter().map(|slots| slots.len() as u32).collect();
    (wealth, counts)
}

/// Move `amount` (negative: take) through the wealth of `slots`; returns the
/// exact change made, the sum of each agent's new minus old wealth.
fn transfer(pool: &mut AgentPool, slots: &[usize], amount: f64) -> f64 {
    if slots.is_empty() || amount == 0.0 || !amount.is_finite() {
        return 0.0;
    }
    let before: Vec<f64> = slots.iter().map(|&s| pool.wealth[s] as f64).collect();
    let total: f64 = before.iter().sum();
    let mut target = before.clone();
    if amount < 0.0 {
        if total <= 0.0 {
            return 0.0;
        }
        let keep = (1.0 - (-amount).min(total) / total).max(0.0);
        for t in target.iter_mut() {
            *t *= keep;
        }
    } else {
        let max = MAX_WEALTH as f64;
        let room: Vec<f64> = before.iter().map(|w| (max - w).max(0.0)).collect();
        let weights: Vec<f64> = if total > 0.0 { before.clone() } else { vec![1.0; slots.len()] };
        let weight_sum: f64 = weights.iter().sum();
        let mut given = vec![0.0f64; slots.len()];
        for i in 0..slots.len() {
            given[i] = (amount * weights[i] / weight_sum).min(room[i]);
        }
        let left = amount - given.iter().sum::<f64>();
        if left > 0.0 {
            let spare: Vec<f64> = (0..slots.len()).map(|i| room[i] - given[i]).collect();
            let spare_sum: f64 = spare.iter().sum();
            if spare_sum > 0.0 {
                let share = (left / spare_sum).min(1.0);
                for i in 0..slots.len() {
                    given[i] += spare[i] * share;
                }
            }
        }
        for i in 0..slots.len() {
            target[i] = (before[i] + given[i]).min(max);
        }
    }
    let mut applied = 0.0f64;
    for (i, &s) in slots.iter().enumerate() {
        let new = (target[i] as f32).clamp(0.0, MAX_WEALTH);
        pool.wealth[s] = new;
        applied += new as f64 - before[i];
    }
    applied
}

/// Apply per-region transfers to the merchants of each region; returns the
/// change actually made for each entry, in the order given. Region ids at or
/// beyond `n_regions` change nothing.
pub fn apply_merchant_transfers(pool: &mut AgentPool, n_regions: usize,
                                region_ids: &[u16], amounts: &[f64]) -> Vec<f64> {
    let groups = merchants_by_region(pool, n_regions);
    region_ids.iter().zip(amounts.iter())
        .map(|(&r, &amount)| {
            let r = r as usize;
            if r >= n_regions { 0.0 } else { transfer(pool, &groups[r], amount) }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::BELIEF_NONE;

    fn agent(pool: &mut AgentPool, region: u16, occupation: Occupation, wealth: f32) -> usize {
        let slot = pool.spawn(region, 0, occupation, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
        pool.wealth[slot] = wealth;
        slot
    }

    fn total(pool: &AgentPool) -> f64 {
        (0..pool.capacity()).filter(|&s| pool.is_alive(s)).map(|s| pool.wealth[s] as f64).sum()
    }

    #[test]
    fn wealth_is_read_by_home_region_for_merchants_only() {
        let mut pool = AgentPool::new(8);
        agent(&mut pool, 0, Occupation::Merchant, 10.0);
        agent(&mut pool, 0, Occupation::Farmer, 50.0);
        let away = agent(&mut pool, 1, Occupation::Merchant, 4.0);
        pool.trip_phase[away] = crate::agent::TRIP_PHASE_TRANSIT;
        pool.trip_origin_region[away] = 0;
        agent(&mut pool, 1, Occupation::Merchant, 6.0);
        let (wealth, counts) = merchant_wealth_by_region(&pool, 3);
        assert_eq!(wealth, vec![14.0, 6.0, 0.0]);
        assert_eq!(counts, vec![2, 1, 0]);
    }

    #[test]
    fn a_debit_is_taken_pro_rata_and_reported_exactly() {
        let mut pool = AgentPool::new(8);
        let a = agent(&mut pool, 0, Occupation::Merchant, 30.0);
        let b = agent(&mut pool, 0, Occupation::Merchant, 10.0);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 20.0);
        let before = total(&pool);
        let applied = apply_merchant_transfers(&mut pool, 1, &[0], &[-20.0]);
        assert!((applied[0] + 20.0).abs() < 1e-5, "{applied:?}");
        assert!((total(&pool) - before - applied[0]).abs() < 1e-9);
        assert!((pool.wealth[a] - 15.0).abs() < 1e-5 && (pool.wealth[b] - 5.0).abs() < 1e-5);
        assert_eq!(pool.wealth[farmer], 20.0);
        // Never below zero: a debit beyond their wealth takes what there is.
        let applied = apply_merchant_transfers(&mut pool, 1, &[0], &[-1000.0]);
        assert!((applied[0] + 20.0).abs() < 1e-5);
        assert_eq!(pool.wealth[a], 0.0);
        assert_eq!(pool.wealth[b], 0.0);
    }

    #[test]
    fn a_credit_is_given_pro_rata_up_to_the_ceiling_and_the_rest_reported() {
        let mut pool = AgentPool::new(8);
        let rich = agent(&mut pool, 0, Occupation::Merchant, 90.0);
        let poor = agent(&mut pool, 0, Occupation::Merchant, 10.0);
        let before = total(&pool);
        // 50 pro rata to wealth would give 45 / 5; the rich one has room for 10.
        let applied = apply_merchant_transfers(&mut pool, 1, &[0], &[50.0]);
        assert!((applied[0] - 50.0).abs() < 1e-4, "{applied:?}");
        assert_eq!(pool.wealth[rich], MAX_WEALTH);
        assert!((pool.wealth[poor] - 50.0).abs() < 1e-4);
        assert!((total(&pool) - before - applied[0]).abs() < 1e-9);
        // Everyone at the ceiling: nothing more can be applied.
        apply_merchant_transfers(&mut pool, 1, &[0], &[50.0]);
        let applied = apply_merchant_transfers(&mut pool, 1, &[0], &[5.0]);
        assert_eq!(applied, vec![0.0]);
    }

    #[test]
    fn credits_without_merchants_or_wealth() {
        let mut pool = AgentPool::new(8);
        agent(&mut pool, 0, Occupation::Farmer, 5.0);
        assert_eq!(apply_merchant_transfers(&mut pool, 2, &[0, 1, 7], &[3.0, 3.0, 3.0]), vec![0.0, 0.0, 0.0]);
        let a = agent(&mut pool, 1, Occupation::Merchant, 0.0);
        let b = agent(&mut pool, 1, Occupation::Merchant, 0.0);
        let applied = apply_merchant_transfers(&mut pool, 2, &[1], &[3.0]);
        assert!((applied[0] - 3.0).abs() < 1e-6);
        assert_eq!(pool.wealth[a], 1.5);
        assert_eq!(pool.wealth[b], 1.5);
        // A debit from merchants holding nothing changes nothing.
        let mut empty = AgentPool::new(4);
        agent(&mut empty, 0, Occupation::Merchant, 0.0);
        assert_eq!(apply_merchant_transfers(&mut empty, 1, &[0], &[-2.0]), vec![0.0]);
    }

    #[test]
    fn a_call_moves_wealth_once_and_keeps_no_state() {
        let mut pool = AgentPool::new(8);
        agent(&mut pool, 0, Occupation::Merchant, 40.0);
        let first = apply_merchant_transfers(&mut pool, 1, &[0], &[-10.0]);
        let after_first = total(&pool);
        // An empty call afterwards changes nothing (nothing is held over).
        assert!(apply_merchant_transfers(&mut pool, 1, &[], &[]).is_empty());
        assert_eq!(total(&pool), after_first);
        assert!((first[0] + 10.0).abs() < 1e-6);
    }
}
