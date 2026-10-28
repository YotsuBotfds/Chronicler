//! The merchant tax (`economy::EconomyConfig::tax_rate`): what a treasury
//! collects from its merchant agents.
//!
//! The economy tick assesses every living civ (one that controls a region)
//! at `tax_rate` times the wealth of the living merchant agents of its
//! affinity (`EconomyCivResult::treasury_tax`), and Python pays the tax into
//! the civ's treasury. Until 2026-10 nobody paid it: the treasury was
//! credited and the merchants kept their wealth, so the same wealth was taxed
//! again every turn it lasted (docs/integration/money-credit.md, "The
//! merchant tax").
//!
//! [`plan_merchant_tax`] works out who pays what: each of those merchants
//! pays `tax_rate` of its own wealth (the same agents and the same wealth as
//! the assessment). It returns the new wealth of every paying agent and, per
//! civ, exactly what was taken (the sum of each agent's old minus new
//! wealth, in f64): what the treasury receives. [`apply_merchant_tax`]
//! writes the new wealth. The two steps let `tick_economy` report the tax
//! and change the pool only after its result batches are packed.
//!
//! Nothing here keeps state between calls: a call taxes once and reports
//! it. No random draws; slots are visited in order.

use crate::agent::Occupation;
use crate::pool::AgentPool;

/// The tax of one economy tick: the paying agents' new wealth, in slot
/// order, and what each civ collected.
#[derive(Debug, Default)]
pub struct MerchantTax {
    pub payments: Vec<(usize, f32)>,
    pub collected: Vec<f64>,
}

/// Who pays the merchant tax and how much: every living merchant whose civ
/// affinity `c` has `taxed[c]` pays `tax_rate` (clamped to 0..1) of its
/// wealth. `collected[c]` is the sum of `old - new` over civ `c`'s payers,
/// each term computed from the two f32 values in f64, so it equals the
/// change of their wealth. A rate of 0 (or below, or not finite) takes
/// nothing.
pub fn plan_merchant_tax(pool: &AgentPool, taxed: &[bool], tax_rate: f32) -> MerchantTax {
    let mut tax = MerchantTax { payments: Vec::new(), collected: vec![0.0; taxed.len()] };
    if !tax_rate.is_finite() || tax_rate <= 0.0 {
        return tax;
    }
    let keep = 1.0 - tax_rate.min(1.0);
    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) || pool.occupation(slot) != Occupation::Merchant as u8 {
            continue;
        }
        let civ = pool.civ_affinity(slot) as usize;
        if civ >= taxed.len() || !taxed[civ] {
            continue;
        }
        let old = pool.wealth[slot];
        let new = (old * keep).max(0.0);
        if new == old {
            continue;
        }
        tax.collected[civ] += old as f64 - new as f64;
        tax.payments.push((slot, new));
    }
    tax
}

/// Write the paying agents' new wealth (the plan of the same pool).
pub fn apply_merchant_tax(pool: &mut AgentPool, tax: &MerchantTax) {
    for &(slot, new) in &tax.payments {
        pool.wealth[slot] = new;
    }
}

/// Total wealth of the living merchant agents by civ affinity (index =
/// affinity, 256 entries), in f64. Reads only; the resource ledger's check
/// of the tax (`CHRONICLER_CHECK_RESOURCES=1`).
pub fn merchant_wealth_by_civ(pool: &AgentPool) -> Vec<f64> {
    let mut out = vec![0.0f64; 256];
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) && pool.occupation(slot) == Occupation::Merchant as u8 {
            out[pool.civ_affinity(slot) as usize] += pool.wealth[slot] as f64;
        }
    }
    out
}

/// Number of terms in each civ's merchant-wealth assessment. The resource
/// ledger uses this to bound the rounding error of its f32 accumulation.
pub fn merchant_count_by_civ(pool: &AgentPool) -> Vec<usize> {
    let mut out = vec![0usize; 256];
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) && pool.occupation(slot) == Occupation::Merchant as u8 {
            out[pool.civ_affinity(slot) as usize] += 1;
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::BELIEF_NONE;

    fn agent(pool: &mut AgentPool, civ: u8, occupation: Occupation, wealth: f32) -> usize {
        let slot = pool.spawn(0, civ, occupation, 30, 0.0, 0.0, 0.0, 0, 1, 2, BELIEF_NONE);
        pool.wealth[slot] = wealth;
        slot
    }

    fn wealth_of(pool: &AgentPool, civ: u8) -> f64 {
        merchant_wealth_by_civ(pool)[civ as usize]
    }

    #[test]
    fn each_merchant_of_a_taxed_civ_pays_the_rate_of_its_wealth() {
        let mut pool = AgentPool::new(8);
        let a = agent(&mut pool, 0, Occupation::Merchant, 40.0);
        let b = agent(&mut pool, 0, Occupation::Merchant, 10.0);
        let farmer = agent(&mut pool, 0, Occupation::Farmer, 50.0);
        let other = agent(&mut pool, 1, Occupation::Merchant, 20.0);
        let before = wealth_of(&pool, 0);
        let tax = plan_merchant_tax(&pool, &[true, false], 0.05);
        apply_merchant_tax(&mut pool, &tax);
        assert_eq!(pool.wealth[a], 40.0 * 0.95);
        assert_eq!(pool.wealth[b], 10.0 * 0.95);
        assert_eq!(pool.wealth[farmer], 50.0, "other occupations do not pay");
        assert_eq!(pool.wealth[other], 20.0, "an untaxed civ's merchants do not pay");
        assert!((tax.collected[0] - 2.5).abs() < 1e-5);
        assert_eq!(tax.collected[1], 0.0);
        // What was collected is exactly what the merchants lost.
        assert_eq!(before - wealth_of(&pool, 0), tax.collected[0]);
    }

    #[test]
    fn affinities_beyond_the_taxed_civs_and_dead_agents_do_not_pay() {
        let mut pool = AgentPool::new(4);
        let far = agent(&mut pool, 7, Occupation::Merchant, 30.0);
        let dead = agent(&mut pool, 0, Occupation::Merchant, 30.0);
        pool.kill(dead);
        let tax = plan_merchant_tax(&pool, &[true, true], 0.05);
        assert!(tax.payments.is_empty());
        assert_eq!(tax.collected, vec![0.0, 0.0]);
        apply_merchant_tax(&mut pool, &tax);
        assert_eq!(pool.wealth[far], 30.0);
    }

    #[test]
    fn no_rate_takes_nothing_and_a_full_rate_takes_everything() {
        let mut pool = AgentPool::new(4);
        let m = agent(&mut pool, 0, Occupation::Merchant, 12.5);
        for rate in [0.0, -0.1, f32::NAN] {
            let tax = plan_merchant_tax(&pool, &[true], rate);
            assert!(tax.payments.is_empty());
            assert_eq!(tax.collected, vec![0.0]);
        }
        let tax = plan_merchant_tax(&pool, &[true], 2.0);
        apply_merchant_tax(&mut pool, &tax);
        assert_eq!(pool.wealth[m], 0.0);
        assert_eq!(tax.collected[0], 12.5);
    }

    #[test]
    fn a_plan_changes_nothing_until_applied_and_keeps_no_state() {
        let mut pool = AgentPool::new(4);
        let m = agent(&mut pool, 0, Occupation::Merchant, 64.0);
        let tax = plan_merchant_tax(&pool, &[true], 0.05);
        assert_eq!(pool.wealth[m], 64.0, "planning reads only");
        apply_merchant_tax(&mut pool, &tax);
        let first = pool.wealth[m];
        // A second tick taxes again what is left, once.
        let again = plan_merchant_tax(&pool, &[true], 0.05);
        apply_merchant_tax(&mut pool, &again);
        assert_eq!(first, 64.0 * 0.95);
        assert_eq!(pool.wealth[m], first * 0.95);
        assert_eq!(again.collected[0], first as f64 - pool.wealth[m] as f64);
    }

    #[test]
    fn collected_equals_the_pool_change_across_many_wealth_levels() {
        let mut pool = AgentPool::new(512);
        let mut w = 0.000_37f32;
        for i in 0..400 {
            agent(&mut pool, (i % 3) as u8, Occupation::Merchant, w);
            w = (w * 1.031 + 0.013).min(100.0);
        }
        let before = merchant_wealth_by_civ(&pool);
        let tax = plan_merchant_tax(&pool, &[true, true, false], 0.05);
        apply_merchant_tax(&mut pool, &tax);
        let after = merchant_wealth_by_civ(&pool);
        for civ in 0..2 {
            let moved = before[civ] - after[civ];
            assert!((moved - tax.collected[civ]).abs() <= 1e-9 * before[civ].max(1.0),
                    "civ {civ}: moved {moved}, collected {}", tax.collected[civ]);
            assert!((tax.collected[civ] - 0.05 * before[civ]).abs() <= 1e-5 * before[civ]);
        }
        assert_eq!(before[2], after[2]);
    }

    #[test]
    fn assessment_counts_include_only_living_merchants_of_each_affinity() {
        for n in [1000, 10000] {
            let mut pool = AgentPool::new(n + 4);
            for _ in 0..n {
                agent(&mut pool, 0, Occupation::Merchant, 0.1);
            }
            agent(&mut pool, 1, Occupation::Merchant, 1.0);
            agent(&mut pool, 0, Occupation::Farmer, 2.0);
            let dead = agent(&mut pool, 0, Occupation::Merchant, 3.0);
            pool.kill(dead);
            let counts = merchant_count_by_civ(&pool);
            assert_eq!(counts[0], n);
            assert_eq!(counts[1], 1);
            assert_eq!(counts.iter().sum::<usize>(), n + 1);
        }
    }
}
