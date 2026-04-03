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

#[inline]
fn conversion_stream(region_id: usize, turn: u32, stream_offset: u64) -> u64 {
    // Pack region, turn, and stream offset into disjoint bit ranges so the
    // natural and schism passes cannot collide with each other or with future
    // turn/region combinations in the supported range.
    debug_assert!(region_id <= u16::MAX as usize, "region_id exceeds packed RNG stream range");
    debug_assert!(stream_offset <= u16::MAX as u64, "stream_offset exceeds packed RNG stream range");
    ((region_id as u64) << 48) | ((turn as u64) << 16) | stream_offset
}

/// Run conversion logic for all agents in a region.
/// Called as Rust tick stage 7, after culture_drift.
///
/// Two independent conversion passes:
///   1. Natural/conquest conversion: pushes agents toward `conversion_target_belief`.
///   2. Schism conversion: pushes agents with `schism_convert_from` belief toward
///      `schism_convert_to` (set by Python `fire_schism()`, one-turn transient).
///
/// Each pass uses its own RNG stream to avoid coupling.
pub fn conversion_tick(
    pool: &mut AgentPool,
    slots: &[usize],
    region: &RegionState,
    master_seed: [u8; 32],
    turn: u32,
    region_id: usize,
    religion_multiplier: f32,
) {
    let has_natural = region.conversion_rate > 0.0 || region.conquest_conversion_active;
    let has_schism = region.schism_convert_from != agent::BELIEF_NONE
        && region.schism_convert_to != agent::BELIEF_NONE;

    // Early exit: no conversion pressure at all.
    if !has_natural && !has_schism {
        return;
    }

    // Early exit: no agents to process.
    if slots.is_empty() {
        return;
    }

    // --- Pass 1: natural / conquest conversion ---
    if has_natural {
        let target = region.conversion_target_belief;

        // Guard: if Python sent conversion_rate > 0 but left the target at the
        // 0xFF sentinel (no faith assigned), skip pass 1 entirely.  Without this,
        // agents would have their belief overwritten to BELIEF_NONE.
        if target == agent::BELIEF_NONE {
            // Fall through to pass 2 (schism) which has its own guards.
        } else {

        let mut rng = ChaCha8Rng::from_seed(master_seed);
        rng.set_stream(conversion_stream(region_id, turn, agent::CONVERSION_STREAM_OFFSET));

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
            let urban_mult = if pool.settlement_ids[slot] != 0 {
                agent::URBAN_CONVERSION_MULT
            } else {
                1.0
            };
            let prob = if region.conquest_conversion_active {
                (agent::CONQUEST_CONVERSION_RATE * religion_multiplier * urban_mult).min(1.0)
            } else {
                let base = region.conversion_rate * religion_multiplier * urban_mult;
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

        } // end if target != BELIEF_NONE
    }

    // --- Pass 2: schism conversion ---
    if has_schism {
        let from_belief = region.schism_convert_from;
        let to_belief = region.schism_convert_to;

        let mut rng = ChaCha8Rng::from_seed(master_seed);
        rng.set_stream(conversion_stream(region_id, turn, agent::SCHISM_CONVERSION_STREAM_OFFSET));

        for &slot in slots {
            if !pool.alive[slot] {
                continue;
            }

            // Only agents currently holding the source faith are eligible.
            if pool.beliefs[slot] != from_belief {
                continue;
            }

            // Susceptibility: low-satisfaction agents convert at 2x.
            let base = agent::SCHISM_CONVERSION_RATE * religion_multiplier;
            let prob = if pool.satisfactions[slot] < agent::SUSCEPTIBILITY_THRESHOLD {
                (base * agent::SUSCEPTIBILITY_MULTIPLIER).min(1.0)
            } else {
                base.min(1.0)
            };

            let roll: f32 = rng.gen();
            if roll < prob {
                pool.beliefs[slot] = to_belief;
                pool.life_events[slot] |= agent::LIFE_EVENT_CONVERSION;
            }
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

    /// Build a RegionState with schism conversion fields set.
    fn make_schism_region(from_belief: u8, to_belief: u8) -> RegionState {
        let mut r = RegionState::new(0);
        r.schism_convert_from = from_belief;
        r.schism_convert_to = to_belief;
        r
    }

    const SEED: [u8; 32] = [42u8; 32];

    #[test]
    fn test_conversion_stream_packing_is_distinct() {
        let a = conversion_stream(1, 7, agent::CONVERSION_STREAM_OFFSET);
        let b = conversion_stream(2, 7, agent::CONVERSION_STREAM_OFFSET);
        let c = conversion_stream(1, 8, agent::CONVERSION_STREAM_OFFSET);
        let d = conversion_stream(1, 7, agent::SCHISM_CONVERSION_STREAM_OFFSET);

        assert_ne!(a, b);
        assert_ne!(a, c);
        assert_ne!(a, d);
    }

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

    // ------------------------------------------------------------------
    // Test 7: schism conversion — agents with from_belief convert to to_belief.
    // ------------------------------------------------------------------
    #[test]
    fn test_schism_converts_matching_agents() {
        let n = 2000usize;
        let from_belief: u8 = 3;
        let to_belief: u8 = 7;

        let mut pool = AgentPool::new(n);
        let mut slots = Vec::with_capacity(n);
        for _ in 0..n {
            slots.push(spawn_agent(&mut pool, from_belief, 0.6));
        }

        let region = make_schism_region(from_belief, to_belief);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        let converted = slots.iter().filter(|&&s| pool.beliefs[s] == to_belief).count();
        let rate = converted as f32 / n as f32;
        // SCHISM_CONVERSION_RATE = 0.25, expect ~25% ± 5%
        assert!(
            (rate - 0.25).abs() < 0.05,
            "schism conversion rate {:.3} should be ~0.25 ±0.05",
            rate
        );
        // Converted agents should have LIFE_EVENT_CONVERSION set
        for &slot in &slots {
            if pool.beliefs[slot] == to_belief {
                assert_ne!(
                    pool.life_events[slot] & agent::LIFE_EVENT_CONVERSION, 0,
                    "schism-converted agent should have LIFE_EVENT_CONVERSION set"
                );
            }
        }
    }

    // ------------------------------------------------------------------
    // Test 8: schism does not affect agents with a different belief.
    // ------------------------------------------------------------------
    #[test]
    fn test_schism_skips_non_matching_agents() {
        let mut pool = AgentPool::new(16);
        let from_belief: u8 = 3;
        let to_belief: u8 = 7;
        let other_belief: u8 = 5;

        // 5 agents with from_belief, 5 with other_belief
        let mut from_slots = Vec::new();
        let mut other_slots = Vec::new();
        for _ in 0..5 {
            from_slots.push(spawn_agent(&mut pool, from_belief, 0.6));
        }
        for _ in 0..5 {
            other_slots.push(spawn_agent(&mut pool, other_belief, 0.6));
        }

        let all_slots: Vec<usize> = from_slots.iter().chain(other_slots.iter()).copied().collect();

        // Use rate=1.0 equivalent by setting religion_multiplier high enough
        // that SCHISM_CONVERSION_RATE * multiplier >= 1.0
        let region = make_schism_region(from_belief, to_belief);
        conversion_tick(&mut pool, &all_slots, &region, SEED, 1, 0, 4.0);

        // All from_belief agents should have converted
        for &slot in &from_slots {
            assert_eq!(
                pool.beliefs[slot], to_belief,
                "from_belief agent should convert to to_belief"
            );
        }
        // All other_belief agents should be untouched
        for &slot in &other_slots {
            assert_eq!(
                pool.beliefs[slot], other_belief,
                "other_belief agent should not be affected by schism"
            );
            assert_eq!(
                pool.life_events[slot] & agent::LIFE_EVENT_CONVERSION, 0,
                "non-schism agent should not have LIFE_EVENT_CONVERSION set"
            );
        }
    }

    // ------------------------------------------------------------------
    // Test 9: schism with sentinel 0xFF (no schism) has no effect.
    // ------------------------------------------------------------------
    #[test]
    fn test_schism_sentinel_no_effect() {
        let mut pool = AgentPool::new(8);
        let s0 = spawn_agent(&mut pool, 1, 0.5);
        let s1 = spawn_agent(&mut pool, 2, 0.5);
        let slots = vec![s0, s1];

        // Default region: schism_convert_from = 0xFF, schism_convert_to = 0xFF
        let region = RegionState::new(0);
        conversion_tick(&mut pool, &slots, &region, SEED, 1, 0, 1.0);

        assert_eq!(pool.beliefs[s0], 1, "belief should be unchanged");
        assert_eq!(pool.beliefs[s1], 2, "belief should be unchanged");
    }

    // ------------------------------------------------------------------
    // Test 10: schism and natural conversion run independently.
    // ------------------------------------------------------------------
    #[test]
    fn test_schism_and_natural_both_fire() {
        let mut pool = AgentPool::new(32);
        let from_belief: u8 = 3;
        let to_belief: u8 = 7;
        let natural_target: u8 = 9;
        let bystander: u8 = 5;

        // Agents with from_belief (eligible for schism)
        let mut schism_slots = Vec::new();
        for _ in 0..10 {
            schism_slots.push(spawn_agent(&mut pool, from_belief, 0.6));
        }
        // Agents with bystander belief (eligible for natural conversion only)
        let mut natural_slots = Vec::new();
        for _ in 0..10 {
            natural_slots.push(spawn_agent(&mut pool, bystander, 0.6));
        }

        let all_slots: Vec<usize> = schism_slots.iter().chain(natural_slots.iter()).copied().collect();

        // Set both natural conversion and schism active
        let mut region = RegionState::new(0);
        region.conversion_rate = 1.0;
        region.conversion_target_belief = natural_target;
        region.schism_convert_from = from_belief;
        region.schism_convert_to = to_belief;

        conversion_tick(&mut pool, &all_slots, &region, SEED, 1, 0, 1.0);

        // Natural conversion pass runs first — from_belief agents may convert
        // to natural_target. Then schism pass converts remaining from_belief
        // agents to to_belief. Bystander agents get natural conversion only.

        // All bystander agents should have converted to natural_target (rate=1.0)
        for &slot in &natural_slots {
            assert_eq!(
                pool.beliefs[slot], natural_target,
                "bystander agent should convert to natural_target"
            );
        }

        // Schism slots: after natural pass (rate=1.0), they convert to natural_target.
        // Then schism pass won't touch them (they no longer hold from_belief).
        // So they should all be natural_target.
        for &slot in &schism_slots {
            assert_eq!(
                pool.beliefs[slot], natural_target,
                "schism agents should have been converted by natural pass first (rate=1.0)"
            );
        }
    }

    // ------------------------------------------------------------------
    // Test 11: schism susceptibility — low satisfaction doubles rate.
    // ------------------------------------------------------------------
    #[test]
    fn test_schism_susceptibility() {
        let n = 2000usize;
        let from_belief: u8 = 3;
        let to_belief: u8 = 7;

        // High-satisfaction cohort
        let mut pool_high = AgentPool::new(n);
        let mut slots_high = Vec::with_capacity(n);
        for _ in 0..n {
            slots_high.push(spawn_agent(&mut pool_high, from_belief, 0.8));
        }
        let region = make_schism_region(from_belief, to_belief);
        conversion_tick(&mut pool_high, &slots_high, &region, SEED, 1, 0, 1.0);
        let converted_high = slots_high.iter().filter(|&&s| pool_high.beliefs[s] == to_belief).count();

        // Low-satisfaction cohort
        let mut pool_low = AgentPool::new(n);
        let mut slots_low = Vec::with_capacity(n);
        for _ in 0..n {
            slots_low.push(spawn_agent(&mut pool_low, from_belief, 0.1));
        }
        conversion_tick(&mut pool_low, &slots_low, &region, SEED, 1, 0, 1.0);
        let converted_low = slots_low.iter().filter(|&&s| pool_low.beliefs[s] == to_belief).count();

        let ratio = converted_low as f32 / (converted_high as f32 + 1.0);
        assert!(
            ratio > 1.5,
            "low-sat schism converts {}, high-sat converts {} — ratio {:.2} should be > 1.5",
            converted_low, converted_high, ratio
        );
    }
}
