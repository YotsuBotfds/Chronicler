//! conversion_tick: per-agent religious conversion logic.
//!
//! Runs as Rust tick stage 7 (after M36 culture_drift at stage 6).
//! Beliefs are stable by default; this module fires only when Python
//! pre-computes non-zero conversion pressure for a region.
//!
//! Python sets per-region fields on `RegionState`:
//!   - `conversion_rate`            — base probability per agent per turn
//!   - `conversion_target_belief`   — the faith agents are pushed toward
//!   - `conquest_conversion_active` — forced 30% flip (holy-war mode)
//!
//! Agents with `satisfaction < SUSCEPTIBILITY_THRESHOLD` convert at 2×.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;
use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;

/// Run conversion logic for all agents in a region.
/// Called as Rust tick stage 7, after culture_drift.
pub fn conversion_tick(
    pool: &mut AgentPool,
    slots: &[usize],
    region: &RegionState,
    master_seed: [u8; 32],
    turn: u32,
    region_id: usize,
    religion_multiplier: f32,
) {
    // Early exit: no conversion pressure at all.
    if region.conversion_rate <= 0.0 && !region.conquest_conversion_active {
        return;
    }

    // Early exit: no agents to process.
    if slots.is_empty() {
        return;
    }

    let target = region.conversion_target_belief;

    let mut rng = ChaCha8Rng::from_seed(master_seed);
    rng.set_stream(region_id as u64 * 1000 + turn as u64 + agent::CONVERSION_STREAM_OFFSET);

    for &slot in slots {
        if !pool.alive[slot] {
            continue;
        }

        let current_belief = pool.beliefs[slot];

        // Skip agents that are already the target faith.
        if current_belief == target {
            continue;
        }

        // Skip agents with no belief assigned (sentinel 0xFF).
        if current_belief == agent::BELIEF_NONE {
            continue;
        }

        // Determine conversion probability.
        let prob = if region.conquest_conversion_active {
            (agent::CONQUEST_CONVERSION_RATE * religion_multiplier).min(1.0)
        } else {
            let base = region.conversion_rate * religion_multiplier;
            if pool.satisfactions[slot] < agent::SUSCEPTIBILITY_THRESHOLD {
                (base * agent::SUSCEPTIBILITY_MULTIPLIER).min(1.0)
            } else {
                base.min(1.0)
            }
        };

        // Roll and apply.
        let roll: f32 = rng.gen();
        if roll < prob {
            pool.beliefs[slot] = target;
            pool.life_events[slot] |= agent::LIFE_EVENT_CONVERSION;
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;

    /// Convenience: spawn a basic agent with controllable belief and satisfaction.
    fn spawn_agent(pool: &mut AgentPool, belief: u8, satisfaction: f32) -> usize {
        let slot = pool.spawn(0, 0, Occupation::Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, belief);
        pool.satisfactions[slot] = satisfaction;
        slot
    }

    /// Build a RegionState with conversion fields set.
    fn make_region(
        rate: f32,
        target: u8,
        conquest: bool,
    ) -> RegionState {
        let mut r = RegionState::new(0);
        r.conversion_rate = rate;
        r.conversion_target_belief = target;
        r.conquest_conversion_active = conquest;
        r
    }

    const SEED: [u8; 32] = [42u8; 32];

    // ------------------------------------------------------------------
    // Test 1: zero rate and no conquest → no conversions.
    // ------------------------------------------------------------------
    #[test]
    fn test_zero_rate_no_conversion() {
        let mut pool = AgentPool::new(8);
        let s0 = spawn_agent(&mut pool, 1, 0.5);
        let s1 = spawn_agent(&mut pool, 2, 0.1); // low satisfaction
        let slots = vec![s0, s1];

        let region = make_region(0.0, 3, false);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        assert_eq!(pool.beliefs[s0], 1, "belief should be unchanged");
        assert_eq!(pool.beliefs[s1], 2, "belief should be unchanged");
        assert_eq!(pool.life_events[s0] & agent::LIFE_EVENT_CONVERSION, 0);
        assert_eq!(pool.life_events[s1] & agent::LIFE_EVENT_CONVERSION, 0);
    }

    // ------------------------------------------------------------------
    // Test 2: rate = 1.0 → every eligible agent converts.
    // ------------------------------------------------------------------
    #[test]
    fn test_full_rate_all_convert() {
        let mut pool = AgentPool::new(16);
        let target_belief: u8 = 5;
        let mut slots = Vec::new();
        for _ in 0..10 {
            slots.push(spawn_agent(&mut pool, 1, 0.6)); // normal satisfaction
        }

        let region = make_region(1.0, target_belief, false);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        for &slot in &slots {
            assert_eq!(
                pool.beliefs[slot], target_belief,
                "agent should have converted to target belief"
            );
            assert_ne!(
                pool.life_events[slot] & agent::LIFE_EVENT_CONVERSION, 0,
                "LIFE_EVENT_CONVERSION bit should be set"
            );
        }
    }

    // ------------------------------------------------------------------
    // Test 3: agents already holding the target belief are not touched.
    // ------------------------------------------------------------------
    #[test]
    fn test_skip_already_target_belief() {
        let mut pool = AgentPool::new(8);
        let target: u8 = 3;
        let already = spawn_agent(&mut pool, target, 0.5);
        let other = spawn_agent(&mut pool, 1, 0.5);
        let slots = vec![already, other];

        let region = make_region(1.0, target, false);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        // `already` must remain unchanged (life_event bit must stay clear).
        assert_eq!(pool.life_events[already] & agent::LIFE_EVENT_CONVERSION, 0,
            "already-at-target agent must not fire LIFE_EVENT_CONVERSION");
        // `other` should convert.
        assert_eq!(pool.beliefs[other], target);
    }

    // ------------------------------------------------------------------
    // Test 4: conquest mode → ~30% convert (statistical, ±5%).
    // ------------------------------------------------------------------
    #[test]
    fn test_conquest_conversion_rate() {
        let n = 2000usize;
        let mut pool = AgentPool::new(n);
        let target: u8 = 7;
        let mut slots = Vec::with_capacity(n);
        for _ in 0..n {
            slots.push(spawn_agent(&mut pool, 1, 0.6)); // normal satisfaction
        }

        let region = make_region(0.0, target, true); // conquest, base rate irrelevant
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        let converted = slots.iter().filter(|&&s| pool.beliefs[s] == target).count();
        let rate = converted as f32 / n as f32;
        assert!(
            (rate - 0.30).abs() < 0.05,
            "conquest conversion rate {:.3} should be ~0.30 ±0.05",
            rate
        );
    }

    // ------------------------------------------------------------------
    // Test 5: susceptibility doubles effective rate for low-sat agents.
    // ------------------------------------------------------------------
    #[test]
    fn test_susceptibility_doubles_rate() {
        let n = 2000usize;
        let base_rate = 0.20f32;
        let target: u8 = 9;

        // High-satisfaction cohort.
        let mut pool_high = AgentPool::new(n);
        let mut slots_high = Vec::with_capacity(n);
        for _ in 0..n {
            slots_high.push(spawn_agent(&mut pool_high, 1, 0.8)); // above threshold
        }
        let region = make_region(base_rate, target, false);
        conversion_tick(&mut pool_high, &slots_high, &region, SEED, 1, 0, 1.0);
        let converted_high = slots_high.iter().filter(|&&s| pool_high.beliefs[s] == target).count();

        // Low-satisfaction cohort.
        let mut pool_low = AgentPool::new(n);
        let mut slots_low = Vec::with_capacity(n);
        for _ in 0..n {
            slots_low.push(spawn_agent(&mut pool_low, 1, 0.1)); // below threshold
        }
        conversion_tick(&mut pool_low, &slots_low, &region, SEED, 1, 0, 1.0);
        let converted_low = slots_low.iter().filter(|&&s| pool_low.beliefs[s] == target).count();

        // Low-sat should convert at approximately 2× the high-sat rate.
        let ratio = converted_low as f32 / (converted_high as f32 + 1.0);
        assert!(
            ratio > 1.5,
            "low-sat converts {}, high-sat converts {} — ratio {:.2} should be > 1.5",
            converted_low, converted_high, ratio
        );
    }

    // ------------------------------------------------------------------
    // Test 6: converted agents have LIFE_EVENT_CONVERSION bit (bit 6) set.
    // ------------------------------------------------------------------
    #[test]
    fn test_life_event_conversion_bit_set() {
        let mut pool = AgentPool::new(8);
        let target: u8 = 4;
        let slots: Vec<usize> = (0..5)
            .map(|_| spawn_agent(&mut pool, 0, 0.6))
            .collect();

        let region = make_region(1.0, target, false);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        for &slot in &slots {
            assert_ne!(
                pool.life_events[slot] & agent::LIFE_EVENT_CONVERSION, 0,
                "slot {} should have LIFE_EVENT_CONVERSION (bit 6) set", slot
            );
            // Verify it is indeed bit 6.
            assert_eq!(agent::LIFE_EVENT_CONVERSION, 1 << 6);
        }
    }
}
