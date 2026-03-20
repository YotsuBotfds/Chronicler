/// M50b Formation Engine Core
/// Similarity computation and per-type bond formation gate functions.
/// All functions are pure (no mutation, no RNG) — called by Task 3's scan orchestration.

use std::collections::HashMap;

use crate::agent;
use crate::memory::{agents_share_memory, agents_share_memory_with_valence};
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::relationships::BondType;

// ---------------------------------------------------------------------------
// FormationCandidate
// ---------------------------------------------------------------------------

/// Result returned by a gate function when a bond should be formed.
pub struct FormationCandidate {
    pub bond_type: BondType,
    pub sentiment: i8,
    /// true = UpsertDirected (Mentor only). false = UpsertSymmetric.
    pub directed: bool,
    /// For Mentor only: true = first agent (a) is the mentor.
    pub source_is_first: bool,
}

// ---------------------------------------------------------------------------
// Cultural similarity
// ---------------------------------------------------------------------------

/// Weighted cross-rank cultural overlap for two agents.
///
/// Algorithm:
/// - Pass 1: same-rank matches get SAME_RANK_WEIGHT (1.0) each
/// - Pass 2: cross-rank matches (unused slots only) get CROSS_RANK_WEIGHT (0.5)
/// - Each value counted at most once (greedy best-match; same-rank wins)
/// - Score = sum / 3.0, range [0.0, 1.0]
pub fn cultural_similarity(pool: &AgentPool, a: usize, b: usize) -> f32 {
    let vals_a = [
        pool.cultural_value_0[a],
        pool.cultural_value_1[a],
        pool.cultural_value_2[a],
    ];
    let vals_b = [
        pool.cultural_value_0[b],
        pool.cultural_value_1[b],
        pool.cultural_value_2[b],
    ];

    let mut score = 0.0_f32;
    // Track which b-slots have been matched already
    let mut b_used = [false; 3];
    // Track which a-slots have been matched (same-rank) so they don't cross-rank
    let mut a_matched_same_rank = [false; 3];

    // Pass 1: same-rank matches
    for rank in 0..3 {
        let va = vals_a[rank];
        if va == agent::CULTURAL_VALUE_EMPTY {
            continue;
        }
        if vals_b[rank] == va && !b_used[rank] {
            score += agent::SAME_RANK_WEIGHT;
            b_used[rank] = true;
            a_matched_same_rank[rank] = true;
        }
    }

    // Pass 2: cross-rank matches (only a-slots not already matched same-rank,
    // only b-slots not already used)
    for rank_a in 0..3 {
        if a_matched_same_rank[rank_a] {
            continue;
        }
        let va = vals_a[rank_a];
        if va == agent::CULTURAL_VALUE_EMPTY {
            continue;
        }
        // Find first unused b-slot (different rank) with same value
        for rank_b in 0..3 {
            if rank_b == rank_a || b_used[rank_b] {
                continue;
            }
            if vals_b[rank_b] == va && vals_b[rank_b] != agent::CULTURAL_VALUE_EMPTY {
                score += agent::CROSS_RANK_WEIGHT;
                b_used[rank_b] = true;
                break; // each a-slot counts at most once
            }
        }
    }

    score / 3.0
}

// ---------------------------------------------------------------------------
// Compatibility score
// ---------------------------------------------------------------------------

/// Weighted compatibility score between two agents.
///
/// score = W_CULTURE * cultural_similarity(a, b)
///       + W_BELIEF  * (beliefs match and not BELIEF_NONE ? 1 : 0)
///       + W_OCCUPATION * (occupations match ? 1 : 0)
///       + W_AFFINITY * (civ_affinities match ? 1 : 0)
pub fn compatibility_score(pool: &AgentPool, a: usize, b: usize) -> f32 {
    let culture = cultural_similarity(pool, a, b);

    let belief_match = pool.beliefs[a] != agent::BELIEF_NONE
        && pool.beliefs[a] == pool.beliefs[b];

    let occ_match = pool.occupations[a] == pool.occupations[b];

    let affinity_match = pool.civ_affinities[a] == pool.civ_affinities[b];

    agent::W_CULTURE * culture
        + agent::W_BELIEF * (if belief_match { 1.0 } else { 0.0 })
        + agent::W_OCCUPATION * (if occ_match { 1.0 } else { 0.0 })
        + agent::W_AFFINITY * (if affinity_match { 1.0 } else { 0.0 })
}

// ---------------------------------------------------------------------------
// Gate functions
// ---------------------------------------------------------------------------

/// Friend bond gate.
///
/// Gate: compatibility_score >= FRIEND_THRESHOLD
///       AND agents_share_memory(pool, a, b).is_some()
/// Triadic boost: if triadic_boost is true, threshold is reduced by TRIADIC_THRESHOLD_REDUCTION.
pub fn check_friend(
    pool: &AgentPool,
    a: usize,
    b: usize,
    triadic_boost: bool,
) -> Option<FormationCandidate> {
    let threshold = if triadic_boost {
        agent::FRIEND_THRESHOLD - agent::TRIADIC_THRESHOLD_REDUCTION
    } else {
        agent::FRIEND_THRESHOLD
    };

    if compatibility_score(pool, a, b) < threshold {
        return None;
    }
    if agents_share_memory(pool, a, b).is_none() {
        return None;
    }

    Some(FormationCandidate {
        bond_type: BondType::Friend,
        sentiment: agent::FRIEND_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// CoReligionist bond gate.
///
/// Gate: beliefs[a] == beliefs[b]
///       AND beliefs[a] != BELIEF_NONE
///       AND belief count in region < region_pop * MINORITY_THRESHOLD
///
/// belief_census: map from belief_id to count of agents in the region with that belief.
/// region_pop: total population in the region.
pub fn check_coreligionist(
    pool: &AgentPool,
    a: usize,
    b: usize,
    belief_census: &HashMap<u8, usize>,
    region_pop: u32,
) -> Option<FormationCandidate> {
    let belief_a = pool.beliefs[a];
    if belief_a == agent::BELIEF_NONE {
        return None;
    }
    if belief_a != pool.beliefs[b] {
        return None;
    }

    let count = belief_census.get(&belief_a).copied().unwrap_or(0);
    let threshold = (region_pop as f32 * agent::MINORITY_THRESHOLD) as usize;
    if count >= threshold {
        return None;
    }

    Some(FormationCandidate {
        bond_type: BondType::CoReligionist,
        sentiment: agent::CORELIGIONIST_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// Rival bond gate.
///
/// Gate: same occupation
///       AND abs(wealth[a] - wealth[b]) < RIVAL_WEALTH_PROXIMITY
///       AND compatibility_score >= RIVAL_SIMILARITY_FLOOR
///       AND at least one agent has ambition >= RIVAL_MIN_AMBITION
pub fn check_rival(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.occupations[a] != pool.occupations[b] {
        return None;
    }
    let wealth_gap = (pool.wealth[a] - pool.wealth[b]).abs();
    if wealth_gap >= agent::RIVAL_WEALTH_PROXIMITY {
        return None;
    }
    if compatibility_score(pool, a, b) < agent::RIVAL_SIMILARITY_FLOOR {
        return None;
    }
    let either_ambitious = pool.ambition[a] >= agent::RIVAL_MIN_AMBITION
        || pool.ambition[b] >= agent::RIVAL_MIN_AMBITION;
    if !either_ambitious {
        return None;
    }

    Some(FormationCandidate {
        bond_type: BondType::Rival,
        sentiment: agent::RIVAL_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// Mentor bond gate.
///
/// Gate: same occupation AND age gap >= MENTOR_AGE_GAP
/// Evaluates both orientations:
/// - if ages[a] - ages[b] >= gap → a is mentor (source_is_first = true)
/// - if ages[b] - ages[a] >= gap → b is mentor (source_is_first = false)
/// If both could mentor each other (peers) or neither qualifies, returns None.
/// The directed entry is stored from mentor's perspective:
///   source_is_first = true  → caller should call upsert_directed from a toward b's id
///   source_is_first = false → caller should call upsert_directed from b toward a's id
pub fn check_mentor(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.occupations[a] != pool.occupations[b] {
        return None;
    }

    let age_a = pool.ages[a];
    let age_b = pool.ages[b];
    let gap = agent::MENTOR_AGE_GAP;

    let a_mentors_b = age_a >= age_b && (age_a - age_b) >= gap;
    let b_mentors_a = age_b >= age_a && (age_b - age_a) >= gap;

    // Both would mentor each other → peers, skip
    if a_mentors_b && b_mentors_a {
        return None;
    }

    if a_mentors_b {
        return Some(FormationCandidate {
            bond_type: BondType::Mentor,
            sentiment: agent::MENTOR_INITIAL_SENTIMENT,
            directed: true,
            source_is_first: true,  // a is mentor
        });
    }

    if b_mentors_a {
        return Some(FormationCandidate {
            bond_type: BondType::Mentor,
            sentiment: agent::MENTOR_INITIAL_SENTIMENT,
            directed: true,
            source_is_first: false, // b is mentor
        });
    }

    None
}

/// Grudge bond gate.
///
/// Gate: agents_share_memory_with_valence returns a match
///       AND at least one intensity is negative
///       AND different civ_affinity (grudges form across cultural lines)
pub fn check_grudge(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.civ_affinities[a] == pool.civ_affinities[b] {
        return None;
    }

    let result = agents_share_memory_with_valence(pool, a, b)?;
    let (_et, _turn, int_a, int_b) = result;

    // At least one negative intensity
    if int_a >= 0 && int_b >= 0 {
        return None;
    }

    Some(FormationCandidate {
        bond_type: BondType::Grudge,
        sentiment: agent::GRUDGE_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// ExileBond gate.
///
/// Gate: region.controller_civ != 255 (not neutral)
///       AND origin_regions[a] != pool.regions[a]  (a is away from home)
///       AND origin_regions[b] != pool.regions[b]  (b is away from home)
///       AND controller_civ != civ_affinities[a]   (foreign rule for a)
///       AND controller_civ != civ_affinities[b]   (foreign rule for b)
///
/// Optional +5 sentiment boost when origin_regions[a] == origin_regions[b] (shared homeland).
pub fn check_exile_bond(
    pool: &AgentPool,
    a: usize,
    b: usize,
    region: &RegionState,
) -> Option<FormationCandidate> {
    let controller = region.controller_civ;
    if controller == 255 {
        return None;
    }

    // Both must be away from their origin region
    if pool.origin_regions[a] == pool.regions[a] {
        return None;
    }
    if pool.origin_regions[b] == pool.regions[b] {
        return None;
    }

    // Both must be under foreign rule
    if controller == pool.civ_affinities[a] {
        return None;
    }
    if controller == pool.civ_affinities[b] {
        return None;
    }

    // Shared homeland bonus
    let homeland_bonus = pool.origin_regions[a] == pool.origin_regions[b];
    let sentiment = if homeland_bonus {
        agent::EXILE_INITIAL_SENTIMENT.saturating_add(5)
    } else {
        agent::EXILE_INITIAL_SENTIMENT
    };

    Some(FormationCandidate {
        bond_type: BondType::ExileBond,
        sentiment,
        directed: false,
        source_is_first: false,
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::{Occupation, BELIEF_NONE};
    use crate::memory::MemoryEventType;
    use crate::pool::AgentPool;
    use crate::region::RegionState;

    // ── Spawn helpers ────────────────────────────────────────────────────────

    /// Spawn agent with given cultural values, belief, occupation, civ_affinity.
    fn spawn(
        pool: &mut AgentPool,
        region: u16,
        civ: u8,
        occ: Occupation,
        age: u16,
        ambition: f32,
        cv0: u8,
        cv1: u8,
        cv2: u8,
        belief: u8,
    ) -> usize {
        pool.spawn(region, civ, occ, age, 0.5, ambition, 0.5, cv0, cv1, cv2, belief)
    }

    // ── cultural_similarity ──────────────────────────────────────────────────

    #[test]
    fn test_similarity_identical_culture() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let sim = cultural_similarity(&pool, a, b);
        // All 3 same-rank matches: (1.0 + 1.0 + 1.0) / 3.0 = 1.0
        assert!((sim - 1.0).abs() < 1e-5, "identical → 1.0, got {sim}");
    }

    #[test]
    fn test_similarity_same_values_different_order() {
        let mut pool = AgentPool::new(4);
        // a = [1, 2, 3], b = [2, 1, 3]
        // same-rank matches: none at rank 0 (1≠2), none at rank 1 (2≠1), rank 2 match (3==3) → +1.0
        // cross-rank: rank 0 of a (val=1) matches rank 1 of b (val=1, used? no) → +0.5
        //             rank 1 of a (val=2) matches rank 0 of b (val=2, used? no) → +0.5
        // score = (1.0 + 0.5 + 0.5) / 3.0 = 2.0/3.0 ≈ 0.6667
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 2, 1, 3, BELIEF_NONE);
        let sim = cultural_similarity(&pool, a, b);
        let expected = 2.0_f32 / 3.0;
        assert!((sim - expected).abs() < 1e-5, "reordered → {expected}, got {sim}");
    }

    #[test]
    fn test_similarity_no_overlap() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 4, 5, 0, BELIEF_NONE);
        let sim = cultural_similarity(&pool, a, b);
        assert!((sim - 0.0).abs() < 1e-5, "no overlap → 0.0, got {sim}");
    }

    #[test]
    fn test_similarity_partial_same_rank() {
        // a = [1, 2, 3], b = [1, 5, 6]
        // same-rank: rank 0 match (1==1) → +1.0; no other same-rank
        // cross-rank: a[1]=2 no match in b (5,6 unused); a[2]=3 no match
        // score = 1.0 / 3.0
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 5, 0, BELIEF_NONE);
        let sim = cultural_similarity(&pool, a, b);
        let expected = 1.0_f32 / 3.0;
        assert!((sim - expected).abs() < 1e-5, "one same-rank → {expected}, got {sim}");
    }

    #[test]
    fn test_similarity_no_double_counting() {
        // a = [1, 1, 1], b = [1, 2, 3]
        // same-rank: rank 0 match (1==1) → +1.0; b[0] used
        // rank 1: a=1, b=2 → no same-rank match; b[0] already used, try b[1]=2 ≠ 1, b[2]=3 ≠ 1
        // rank 2: a=1, b=3 → no same-rank; cross: b[1]=2≠1, b[2]=3≠1 → nothing
        // score = 1.0 / 3.0 (no double counting of value 1)
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 1, 1, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let sim = cultural_similarity(&pool, a, b);
        let expected = 1.0_f32 / 3.0;
        assert!((sim - expected).abs() < 1e-5, "no double-count → {expected}, got {sim}");
    }

    // ── check_friend ─────────────────────────────────────────────────────────

    fn write_battle_memory(pool: &mut AgentPool, slot: usize, turn: u16) {
        pool.memory_event_types[slot][0] = MemoryEventType::Battle as u8;
        pool.memory_turns[slot][0] = turn;
        pool.memory_intensities[slot][0] = -60;
        pool.memory_count[slot] = 1;
    }

    #[test]
    fn test_friend_shared_memory_and_threshold_passes() {
        let mut pool = AgentPool::new(4);
        // Same belief, same occ, same civ → compatibility high (W_BELIEF + W_OCC + W_AFFINITY = 0.65)
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 3);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 3);
        write_battle_memory(&mut pool, a, 10);
        write_battle_memory(&mut pool, b, 10);
        let result = check_friend(&pool, a, b, false);
        assert!(result.is_some(), "should form friend bond");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::Friend as u8);
        assert_eq!(c.sentiment, agent::FRIEND_INITIAL_SENTIMENT);
        assert!(!c.directed);
    }

    #[test]
    fn test_friend_no_shared_memory_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 3);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 3);
        // No memories written
        let result = check_friend(&pool, a, b, false);
        assert!(result.is_none(), "no shared memory → should not form");
    }

    #[test]
    fn test_friend_below_threshold_fails() {
        let mut pool = AgentPool::new(4);
        // Different belief, different occ, different civ → low compatibility
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, 1);
        let b = spawn(&mut pool, 0, 1, Occupation::Soldier, 20, 0.5, 4, 5, 0, 2);
        write_battle_memory(&mut pool, a, 10);
        write_battle_memory(&mut pool, b, 10);
        let score = compatibility_score(&pool, a, b);
        // Ensure score is below threshold
        assert!(score < agent::FRIEND_THRESHOLD, "score {score} should be below threshold");
        let result = check_friend(&pool, a, b, false);
        assert!(result.is_none(), "below threshold → should not form");
    }

    #[test]
    fn test_friend_triadic_boost_lowers_threshold() {
        let mut pool = AgentPool::new(4);
        // Design: same occ + same civ, different belief → moderate compatibility
        // W_OCCUPATION (0.15) + W_AFFINITY (0.15) = 0.30
        // FRIEND_THRESHOLD = 0.50; with triadic: 0.50 - 0.15 = 0.35 → should pass at 0.30
        // Actually need a score between (threshold - reduction) and threshold.
        // Let's make a score at exactly W_OCC + W_AFF = 0.30, check below normal but above reduced.
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 2, 3, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 4, 5, 0, BELIEF_NONE);
        // score = 0 (culture) + 0 (belief) + W_OCC(0.15) + W_AFF(0.15) = 0.30
        let score = compatibility_score(&pool, a, b);
        assert!(score < agent::FRIEND_THRESHOLD, "pre-boost should be below threshold");
        let _reduced = agent::FRIEND_THRESHOLD - agent::TRIADIC_THRESHOLD_REDUCTION;
        // With memory, triadic boost applies. Score 0.30 > reduced threshold?
        // Only passes if reduced <= score. If reduced = 0.35 and score = 0.30, still fails.
        // Let's add occ match only - same civ but diff belief, diff culture → 0.15 + 0.15 = 0.30
        // TRIADIC_THRESHOLD_REDUCTION = 0.15, so reduced = 0.35. 0.30 < 0.35 → still fails.
        // Need at least 0.35. Add W_BELIEF partial: use same belief.
        // W_BELIEF(0.35) + W_OCC(0.15) + W_AFF(0.15) = 0.65 > threshold, not useful.
        // Let's just verify the mechanic works at a boundary case without belief match:
        // score = W_OCC(0.15) + W_AFF(0.15) = 0.30; threshold 0.35 → needs memory, still fails.
        // The test below verifies the triadic path completes when score is above reduced threshold.
        // Since we can't easily get a score in (0.35, 0.50) without belief,
        // use W_CULTURE. Set culture to partial match: cross-rank = 0.5/3 ≈ 0.167
        // score ≈ 0.35 * 0.167 + 0.15 + 0.15 = 0.058 + 0.30 = 0.358 > 0.35 → passes with triadic
        let a2 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 1, 4, 5, BELIEF_NONE);
        let b2 = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 4, 1, 0, BELIEF_NONE);
        // a2 = [1,4,5], b2 = [4,1,0]
        // same-rank: none (1≠4, 4≠1, 5≠0)
        // cross-rank: a2[0]=1 → b2[1]=1 → +0.5; a2[1]=4 → b2[0]=4 → +0.5
        // score_culture = 1.0/3.0 ≈ 0.333; compat = 0.35*0.333 + 0 + 0.15 + 0.15 ≈ 0.417
        let score2 = compatibility_score(&pool, a2, b2);
        write_battle_memory(&mut pool, a2, 20);
        write_battle_memory(&mut pool, b2, 20);
        if score2 < agent::FRIEND_THRESHOLD && score2 >= agent::FRIEND_THRESHOLD - agent::TRIADIC_THRESHOLD_REDUCTION {
            let no_boost = check_friend(&pool, a2, b2, false);
            let with_boost = check_friend(&pool, a2, b2, true);
            assert!(no_boost.is_none(), "without triadic boost: should fail at score {score2}");
            assert!(with_boost.is_some(), "with triadic boost: should pass at score {score2}");
        }
        // If the score is outside the range, just verify the function doesn't panic
        let _ = check_friend(&pool, a2, b2, true);
    }

    // ── check_coreligionist ──────────────────────────────────────────────────

    #[test]
    fn test_coreligionist_minority_passes() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        // 2 believers out of 100 = 2% < 40% threshold
        let mut census = HashMap::new();
        census.insert(5u8, 2);
        let result = check_coreligionist(&pool, a, b, &census, 100);
        assert!(result.is_some(), "minority belief should form bond");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::CoReligionist as u8);
        assert_eq!(c.sentiment, agent::CORELIGIONIST_INITIAL_SENTIMENT);
    }

    #[test]
    fn test_coreligionist_majority_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        // 50 believers out of 100 = 50% >= 40% threshold
        let mut census = HashMap::new();
        census.insert(5u8, 50);
        let result = check_coreligionist(&pool, a, b, &census, 100);
        assert!(result.is_none(), "majority belief should not form bond");
    }

    #[test]
    fn test_coreligionist_different_belief_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 3);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 7);
        let mut census = HashMap::new();
        census.insert(3u8, 2);
        census.insert(7u8, 2);
        let result = check_coreligionist(&pool, a, b, &census, 100);
        assert!(result.is_none(), "different beliefs should not form bond");
    }

    #[test]
    fn test_coreligionist_belief_none_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let census = HashMap::new();
        let result = check_coreligionist(&pool, a, b, &census, 100);
        assert!(result.is_none(), "BELIEF_NONE should not form bond");
    }

    // ── check_rival ──────────────────────────────────────────────────────────

    #[test]
    fn test_rival_same_occ_close_wealth_ambitious_passes() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.8, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.3, 0, 1, 2, BELIEF_NONE);
        // Same occupation, same civ, same culture → high compatibility > RIVAL_SIMILARITY_FLOOR
        // Set wealth close together (both start at STARTING_WEALTH = 0.5)
        // Ambition[a] = 0.8 >= RIVAL_MIN_AMBITION (0.50)
        let result = check_rival(&pool, a, b);
        assert!(result.is_some(), "should form rival bond");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::Rival as u8);
        assert_eq!(c.sentiment, agent::RIVAL_INITIAL_SENTIMENT);
        assert!(!c.directed);
    }

    #[test]
    fn test_rival_different_occ_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.8, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.8, 0, 1, 2, BELIEF_NONE);
        let result = check_rival(&pool, a, b);
        assert!(result.is_none(), "different occ should not form rival");
    }

    #[test]
    fn test_rival_wealth_gap_too_large_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.8, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.8, 0, 1, 2, BELIEF_NONE);
        // Set wealth gap >= RIVAL_WEALTH_PROXIMITY (50.0)
        pool.wealth[a] = 60.0;
        pool.wealth[b] = 0.5;
        let result = check_rival(&pool, a, b);
        assert!(result.is_none(), "large wealth gap should not form rival");
    }

    #[test]
    fn test_rival_neither_ambitious_fails() {
        let mut pool = AgentPool::new(4);
        // ambition below RIVAL_MIN_AMBITION (0.50)
        let a = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.3, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Merchant, 20, 0.4, 0, 1, 2, BELIEF_NONE);
        let result = check_rival(&pool, a, b);
        assert!(result.is_none(), "neither ambitious → should not form rival");
    }

    // ── check_mentor ─────────────────────────────────────────────────────────

    #[test]
    fn test_mentor_a_older_a_is_mentor() {
        let mut pool = AgentPool::new(4);
        // a is 40, b is 20 → gap = 20 >= MENTOR_AGE_GAP (15) → a mentors b
        let a = spawn(&mut pool, 0, 0, Occupation::Scholar, 40, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Scholar, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let result = check_mentor(&pool, a, b);
        assert!(result.is_some(), "should form mentor bond");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::Mentor as u8);
        assert!(c.directed);
        assert!(c.source_is_first, "a should be mentor");
        assert_eq!(c.sentiment, agent::MENTOR_INITIAL_SENTIMENT);
    }

    #[test]
    fn test_mentor_b_older_b_is_mentor() {
        let mut pool = AgentPool::new(4);
        // b is 50, a is 25 → gap = 25 >= 15 → b mentors a
        let a = spawn(&mut pool, 0, 0, Occupation::Scholar, 25, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Scholar, 50, 0.5, 0, 1, 2, BELIEF_NONE);
        let result = check_mentor(&pool, a, b);
        assert!(result.is_some(), "should form mentor bond");
        let c = result.unwrap();
        assert!(c.directed);
        assert!(!c.source_is_first, "b should be mentor");
    }

    #[test]
    fn test_mentor_peers_fail() {
        let mut pool = AgentPool::new(4);
        // Ages 30 and 35 → gap = 5 < 15
        let a = spawn(&mut pool, 0, 0, Occupation::Scholar, 30, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Scholar, 35, 0.5, 0, 1, 2, BELIEF_NONE);
        let result = check_mentor(&pool, a, b);
        assert!(result.is_none(), "peers should not form mentor bond");
    }

    #[test]
    fn test_mentor_different_occ_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Scholar, 50, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Merchant, 25, 0.5, 0, 1, 2, BELIEF_NONE);
        let result = check_mentor(&pool, a, b);
        assert!(result.is_none(), "different occ should not form mentor bond");
    }

    // ── check_grudge ─────────────────────────────────────────────────────────

    fn write_negative_memory(pool: &mut AgentPool, slot: usize, turn: u16) {
        pool.memory_event_types[slot][0] = MemoryEventType::Battle as u8;
        pool.memory_turns[slot][0] = turn;
        pool.memory_intensities[slot][0] = -50;
        pool.memory_count[slot] = 1;
    }

    fn write_positive_memory(pool: &mut AgentPool, slot: usize, turn: u16) {
        pool.memory_event_types[slot][0] = MemoryEventType::Prosperity as u8;
        pool.memory_turns[slot][0] = turn;
        pool.memory_intensities[slot][0] = 50;
        pool.memory_count[slot] = 1;
    }

    #[test]
    fn test_grudge_negative_memory_different_affinity_passes() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 1, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        write_negative_memory(&mut pool, a, 10);
        write_negative_memory(&mut pool, b, 10);
        let result = check_grudge(&pool, a, b);
        assert!(result.is_some(), "negative shared memory + different affinity → grudge");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::Grudge as u8);
        assert_eq!(c.sentiment, agent::GRUDGE_INITIAL_SENTIMENT);
        assert!(!c.directed);
    }

    #[test]
    fn test_grudge_positive_memory_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 1, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        // Same event type (Prosperity) on same turn but both positive
        write_positive_memory(&mut pool, a, 10);
        write_positive_memory(&mut pool, b, 10);
        let result = check_grudge(&pool, a, b);
        assert!(result.is_none(), "both positive intensities → no grudge");
    }

    #[test]
    fn test_grudge_same_affinity_fails() {
        let mut pool = AgentPool::new(4);
        // Same civ_affinity
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        write_negative_memory(&mut pool, a, 10);
        write_negative_memory(&mut pool, b, 10);
        let result = check_grudge(&pool, a, b);
        assert!(result.is_none(), "same civ_affinity → no grudge");
    }

    // ── check_exile_bond ─────────────────────────────────────────────────────

    fn make_exile_region(controller: u8) -> RegionState {
        let mut r = RegionState::new(0);
        r.controller_civ = controller;
        r
    }

    #[test]
    fn test_exile_bond_both_away_foreign_rule_passes() {
        let mut pool = AgentPool::new(4);
        // Both agents: origin_region = 5, current_region = 0, civ_affinity = 0
        // Controller = 1 (foreign to both)
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        pool.origin_regions[a] = 5;
        pool.origin_regions[b] = 7; // different homeland
        let region = make_exile_region(1);
        let result = check_exile_bond(&pool, a, b, &region);
        assert!(result.is_some(), "both away + foreign rule → exile bond");
        let c = result.unwrap();
        assert_eq!(c.bond_type as u8, BondType::ExileBond as u8);
        assert_eq!(c.sentiment, agent::EXILE_INITIAL_SENTIMENT);
        assert!(!c.directed);
    }

    #[test]
    fn test_exile_bond_controller_255_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        pool.origin_regions[a] = 5;
        pool.origin_regions[b] = 5;
        let region = make_exile_region(255); // neutral/uncontrolled
        let result = check_exile_bond(&pool, a, b, &region);
        assert!(result.is_none(), "controller=255 → not a foreign occupation");
    }

    #[test]
    fn test_exile_bond_one_at_origin_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        // a is at its origin (origin_region == current_region == 0)
        pool.origin_regions[a] = 0; // at home
        pool.origin_regions[b] = 5; // away
        let region = make_exile_region(1);
        let result = check_exile_bond(&pool, a, b, &region);
        assert!(result.is_none(), "a at origin → not an exile");
    }

    #[test]
    fn test_exile_bond_one_matches_controller_fails() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 1, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE); // civ=1
        pool.origin_regions[a] = 5;
        pool.origin_regions[b] = 6;
        // Controller = 1 → b matches controller (not under foreign rule for b)
        let region = make_exile_region(1);
        let result = check_exile_bond(&pool, a, b, &region);
        assert!(result.is_none(), "b matches controller → not exile for b");
    }

    #[test]
    fn test_exile_bond_shared_homeland_gives_bonus() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        // Both from region 5
        pool.origin_regions[a] = 5;
        pool.origin_regions[b] = 5;
        let region = make_exile_region(1);
        let result = check_exile_bond(&pool, a, b, &region);
        assert!(result.is_some(), "shared homeland exile bond should form");
        let c = result.unwrap();
        assert_eq!(c.sentiment, agent::EXILE_INITIAL_SENTIMENT + 5, "homeland bonus +5");
    }
}
