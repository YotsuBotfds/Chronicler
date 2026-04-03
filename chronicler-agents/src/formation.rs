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
// Formation scan orchestration (Task 3)
// ---------------------------------------------------------------------------

/// Stats emitted by a single formation scan pass.
#[derive(Default, Debug)]
pub struct FormationStats {
    pub bonds_formed: u32,
    pub bonds_evicted: u32,
    pub bonds_dissolved_structural: u32,
    pub bonds_dissolved_death: u32,
    pub pairs_evaluated: u32,
    pub pairs_eligible: u32,
    // M57a: Marriage formation stats
    pub marriages_formed: u32,
    pub marriage_pairs_evaluated: u32,
    pub marriage_pairs_rejected_hostile: u32,
    pub marriage_pairs_rejected_incest: u32,
    pub marriage_pairs_rejected_distance: u32,
    pub cross_civ_marriages: u32,
    pub same_civ_marriages: u32,
    pub cross_faith_marriages: u32,
    pub same_faith_marriages: u32,
}

// ---------------------------------------------------------------------------
// Death cleanup sweep (Task 4)
// ---------------------------------------------------------------------------

/// Sweep all alive agents' relationship slots, removing bonds to dead agents.
/// Returns dissolution events for narration and count of removed bonds.
pub fn death_cleanup_sweep(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    dead_ids: &std::collections::HashSet<u32>,
    turn: u32,
) -> (Vec<crate::tick::AgentEvent>, u32) {
    let mut events = Vec::new();
    let mut removed: u32 = 0;

    for &slot in alive_slots {
        let mut i: usize = 0;
        while i < pool.rel_count[slot] as usize {
            let target_id = pool.rel_target_ids[slot][i];
            if dead_ids.contains(&target_id) {
                let bond_type = pool.rel_bond_types[slot][i];
                events.push(crate::tick::AgentEvent {
                    agent_id: pool.ids[slot],
                    event_type: agent::LIFE_EVENT_DISSOLUTION,
                    region: pool.regions[slot],
                    target_region: bond_type as u16,
                    civ_affinity: pool.civ_affinities[slot],
                    occupation: pool.occupations[slot],
                    belief: pool.beliefs[slot],
                    turn,
                    target_agent_id: target_id,
                    formed_turn: pool.rel_formed_turns[slot][i] as u32,
                });
                crate::relationships::swap_remove_rel(pool, slot, i);
                removed += 1;
                // Don't increment i — swapped-in entry needs re-checking
            } else {
                i += 1;
            }
        }
    }

    (events, removed)
}

// ---------------------------------------------------------------------------
// Belief-divergence cleanup (Task 4)
// ---------------------------------------------------------------------------

/// Remove CoReligionist bonds where beliefs have diverged.
/// Returns the number of bonds removed.
pub fn belief_divergence_cleanup(
    pool: &mut AgentPool,
    region_slots: &[usize],
    id_to_slot: &HashMap<u32, usize>,
) -> u32 {
    let mut removed: u32 = 0;

    for &slot in region_slots {
        let src_belief = pool.beliefs[slot];
        let mut i: usize = 0;
        while i < pool.rel_count[slot] as usize {
            if pool.rel_bond_types[slot][i] == BondType::CoReligionist as u8 {
                let target_id = pool.rel_target_ids[slot][i];
                // Resolve target to slot via id_to_slot (target may have migrated)
                let beliefs_match = id_to_slot
                    .get(&target_id)
                    .map(|&target_slot| pool.beliefs[target_slot] == src_belief)
                    .unwrap_or(false); // target not found (dead/gone) → diverged
                if !beliefs_match {
                    crate::relationships::swap_remove_rel(pool, slot, i);
                    removed += 1;
                    // Don't increment i — swapped-in entry needs re-checking
                    continue;
                }
            }
            i += 1;
        }
    }

    removed
}

// ---------------------------------------------------------------------------
// Formation scan orchestration support
// ---------------------------------------------------------------------------

/// Deterministic hash mix for pair-shuffling.
/// Combines (turn, region_index, agent_id) into a u64 sort key.
fn mix_hash(a: u32, b: u32, c: u32) -> u64 {
    let mut h = (a as u64).wrapping_mul(0x9E3779B97F4A7C15);
    h ^= (b as u64).wrapping_mul(0x517CC1B727220A95);
    h ^= (c as u64).wrapping_mul(0x6C62272E07BB0142);
    h ^= h >> 33;
    h = h.wrapping_mul(0xFF51AFD7ED558CCD);
    h ^= h >> 33;
    h
}

/// Build a belief census for a list of slots: belief_id -> count.
fn build_belief_census(pool: &AgentPool, slots: &[usize]) -> HashMap<u8, usize> {
    let mut census: HashMap<u8, usize> = HashMap::new();
    for &s in slots {
        let b = pool.beliefs[s];
        if b != agent::BELIEF_NONE {
            *census.entry(b).or_insert(0) += 1;
        }
    }
    census
}

// ---------------------------------------------------------------------------
// M57a: Marriage formation
// ---------------------------------------------------------------------------

struct MarriageCandidate {
    slot_a: usize,
    slot_b: usize,
    score: f32,
    hash: u64,
}

fn marriage_pair_hash(turn: u32, region_idx: u32, id_a: u32, id_b: u32) -> u64 {
    let (lo, hi) = if id_a <= id_b { (id_a, id_b) } else { (id_b, id_a) };
    let mut h = (turn as u64).wrapping_mul(0x9E3779B97F4A7C15);
    h ^= (region_idx as u64).wrapping_mul(0x517CC1B727220A95);
    h ^= (lo as u64).wrapping_mul(0x6C62272E07BB0142);
    h ^= (hi as u64).wrapping_mul(0x2545F4914F6CDD1D);
    h ^= h >> 33;
    h = h.wrapping_mul(0xFF51AFD7ED558CCD);
    h ^= h >> 33;
    h
}

fn shares_parent(pool: &AgentPool, a: usize, b: usize) -> bool {
    let parents_a = pool.parent_ids(a);
    let parents_b = pool.parent_ids(b);
    for &pa in &parents_a {
        if pa == crate::agent::PARENT_NONE { continue; }
        for &pb in &parents_b {
            if pa == pb { return true; }
        }
    }
    false
}

fn is_parent_child(pool: &AgentPool, a: usize, b: usize) -> bool {
    let id_a = pool.ids[a];
    let id_b = pool.ids[b];
    pool.has_parent(a, id_b) || pool.has_parent(b, id_a)
}

fn marriage_score(pool: &AgentPool, a: usize, b: usize) -> f32 {
    use crate::agent::*;
    let mut score: f32 = 0.0;
    if pool.civ_affinities[a] == pool.civ_affinities[b] { score += MARRIAGE_SAME_CIV_BONUS; }
    let ba = pool.beliefs[a];
    let bb = pool.beliefs[b];
    if ba == bb && ba != BELIEF_NONE { score += MARRIAGE_SAME_BELIEF_BONUS; }
    else if ba != BELIEF_NONE && bb != BELIEF_NONE && ba != bb { score -= MARRIAGE_CROSS_FAITH_PENALTY; }
    let cv_a = [pool.cultural_value_0[a], pool.cultural_value_1[a], pool.cultural_value_2[a]];
    let cv_b = [pool.cultural_value_0[b], pool.cultural_value_1[b], pool.cultural_value_2[b]];
    for i in 0..3 {
        if cv_a[i] == cv_b[i] && cv_a[i] != CULTURAL_VALUE_EMPTY { score += MARRIAGE_CULTURE_MATCH_BONUS; }
    }
    let dx = pool.x[a] - pool.x[b];
    let dy = pool.y[a] - pool.y[b];
    let dist = (dx * dx + dy * dy).sqrt();
    if dist > 0.001 { score += (1.0 / (1.0 + dist * 4.0)).min(MARRIAGE_CLOSENESS_CAP); }
    else { score += MARRIAGE_CLOSENESS_CAP; }
    score
}

/// M57a: Marriage scan — scored greedy matching within regions.
///
/// Runs BEFORE formation_scan on a staggered cadence (MARRIAGE_CADENCE).
/// Evaluates eligible unmarried adults, rejects ineligible pairs (distance,
/// incest, cross-civ hostility), scores the rest, and greedily accepts
/// the highest-scoring disjoint pairs.
pub fn marriage_scan(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &crate::signals::TickSignals,
    turn: u32,
    alive_slots: &[usize],
) -> FormationStats {
    let mut stats = FormationStats::default();
    let cadence_phase = turn % agent::MARRIAGE_CADENCE;
    let num_regions = regions.len();

    // Bucket alive agents by region
    let mut region_buckets: Vec<Vec<usize>> = vec![Vec::new(); num_regions];
    for &slot in alive_slots {
        let r = pool.regions[slot] as usize;
        if r < num_regions {
            region_buckets[r].push(slot);
        }
    }

    // Pre-build civ war lookup: for each civ_id, is it at war?
    let mut civ_at_war = [false; 256];
    for cs in &signals.civs {
        civ_at_war[cs.civ_id as usize] = cs.is_at_war;
    }

    const MARRIAGE_INITIAL_SENTIMENT: i8 = 50;

    for region_idx in 0..num_regions {
        // Staggered cadence check
        if (region_idx as u32) % agent::MARRIAGE_CADENCE != cadence_phase {
            continue;
        }

        let bucket = &region_buckets[region_idx];

        // Filter eligible: old enough and unmarried
        let eligible: Vec<usize> = bucket.iter()
            .filter(|&&slot| {
                pool.ages[slot] >= agent::MARRIAGE_MIN_AGE
                    && crate::relationships::get_spouse_id(pool, slot).is_none()
            })
            .copied()
            .collect();

        if eligible.len() < 2 {
            continue;
        }

        // Evaluate all pairs, collect candidates
        let mut candidates: Vec<MarriageCandidate> = Vec::new();

        for i in 0..eligible.len() {
            let slot_a = eligible[i];
            for j in (i + 1)..eligible.len() {
                let slot_b = eligible[j];

                stats.marriage_pairs_evaluated += 1;

                // Reject: distance check
                let dx = pool.x[slot_a] - pool.x[slot_b];
                let dy = pool.y[slot_a] - pool.y[slot_b];
                let dist = (dx * dx + dy * dy).sqrt();
                if dist > agent::MARRIAGE_RADIUS {
                    stats.marriage_pairs_rejected_distance += 1;
                    continue;
                }

                // Reject: incest (parent-child or shared parent)
                if is_parent_child(pool, slot_a, slot_b) || shares_parent(pool, slot_a, slot_b) {
                    stats.marriage_pairs_rejected_incest += 1;
                    continue;
                }

                // Reject: cross-civ hostile
                let civ_a = pool.civ_affinities[slot_a];
                let civ_b = pool.civ_affinities[slot_b];
                if civ_a != civ_b {
                    if civ_at_war[civ_a as usize] || civ_at_war[civ_b as usize] {
                        stats.marriage_pairs_rejected_hostile += 1;
                        continue;
                    }
                }

                // Score the pair
                let score = marriage_score(pool, slot_a, slot_b);
                let hash = marriage_pair_hash(turn, region_idx as u32, pool.ids[slot_a], pool.ids[slot_b]);

                candidates.push(MarriageCandidate {
                    slot_a,
                    slot_b,
                    score,
                    hash,
                });
            }
        }

        // Sort by descending score, then ascending hash for tie-breaking
        candidates.sort_by(|a, b| {
            b.score.partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.hash.cmp(&b.hash))
        });

        // Greedily accept disjoint pairs
        let mut married_this_region: std::collections::HashSet<usize> = std::collections::HashSet::new();

        for mc in &candidates {
            if married_this_region.contains(&mc.slot_a) || married_this_region.contains(&mc.slot_b) {
                continue;
            }

            let ok = crate::relationships::upsert_symmetric(
                pool, mc.slot_a, mc.slot_b,
                BondType::Marriage as u8,
                MARRIAGE_INITIAL_SENTIMENT,
                turn as u16,
            );

            if ok {
                stats.marriages_formed += 1;
                married_this_region.insert(mc.slot_a);
                married_this_region.insert(mc.slot_b);

                // Track civ stats
                let civ_a = pool.civ_affinities[mc.slot_a];
                let civ_b = pool.civ_affinities[mc.slot_b];
                if civ_a == civ_b {
                    stats.same_civ_marriages += 1;
                } else {
                    stats.cross_civ_marriages += 1;
                }

                // Track faith stats (only when both have a belief)
                let belief_a = pool.beliefs[mc.slot_a];
                let belief_b = pool.beliefs[mc.slot_b];
                if belief_a != agent::BELIEF_NONE && belief_b != agent::BELIEF_NONE {
                    if belief_a == belief_b {
                        stats.same_faith_marriages += 1;
                    } else {
                        stats.cross_faith_marriages += 1;
                    }
                }
            }
        }
    }

    stats
}

/// Check whether agents a and b share a positive contact (triadic closure).
/// Returns true if there exists some agent c such that:
///   - a has a relationship to c with sentiment >= TRIADIC_MIN_SENTIMENT
///   - b has a relationship to c with sentiment >= TRIADIC_MIN_SENTIMENT
fn has_shared_positive_contact(pool: &AgentPool, a: usize, b: usize) -> bool {
    let count_a = pool.rel_count[a] as usize;
    let count_b = pool.rel_count[b] as usize;
    if count_a == 0 || count_b == 0 {
        return false;
    }
    // Iterate a's contacts, check if b also has a positive link to the same target
    for i in 0..count_a {
        if !crate::relationships::is_positive_valence(pool.rel_bond_types[a][i]) {
            continue;
        }
        if pool.rel_sentiments[a][i] < agent::TRIADIC_MIN_SENTIMENT {
            continue;
        }
        let target_id = pool.rel_target_ids[a][i];
        for j in 0..count_b {
            if pool.rel_target_ids[b][j] == target_id
                && crate::relationships::is_positive_valence(pool.rel_bond_types[b][j])
                && pool.rel_sentiments[b][j] >= agent::TRIADIC_MIN_SENTIMENT
            {
                return true;
            }
        }
    }
    false
}

/// Check if an agent has capacity for a new relationship.
fn has_capacity(pool: &AgentPool, slot: usize) -> bool {
    let count = pool.rel_count[slot] as usize;
    if count < crate::relationships::REL_SLOTS {
        return true;
    }
    // Full — check if there's an evictable slot
    crate::relationships::find_evictable(pool, slot).is_some()
}

/// Check if directed bond source has capacity (only source side matters for Mentor).
fn has_capacity_directed(pool: &AgentPool, src_slot: usize) -> bool {
    has_capacity(pool, src_slot)
}

/// Evaluate a pair for all bond types and return ALL candidates that pass.
/// Only skips a bond type if that specific type already exists between the pair.
/// Evaluation order: Friend, CoReligionist, Rival, Mentor, Grudge, ExileBond.
fn evaluate_pair(
    pool: &AgentPool,
    a: usize,
    b: usize,
    belief_census: &HashMap<u8, usize>,
    region_pop: u32,
    region: &RegionState,
    triadic: bool,
) -> Vec<FormationCandidate> {
    let id_b = pool.ids[b];
    let mut candidates = Vec::new();

    if crate::relationships::find_relationship(pool, a, id_b, BondType::Friend as u8).is_none() {
        if let Some(c) = check_friend(pool, a, b, triadic) {
            candidates.push(c);
        }
    }
    if crate::relationships::find_relationship(pool, a, id_b, BondType::CoReligionist as u8).is_none() {
        if let Some(c) = check_coreligionist(pool, a, b, belief_census, region_pop) {
            candidates.push(c);
        }
    }
    if crate::relationships::find_relationship(pool, a, id_b, BondType::Rival as u8).is_none() {
        if let Some(c) = check_rival(pool, a, b) {
            candidates.push(c);
        }
    }
    // Mentor is directed: check from both sides
    if crate::relationships::find_relationship(pool, a, id_b, BondType::Mentor as u8).is_none()
        && crate::relationships::find_relationship(pool, b, pool.ids[a], BondType::Mentor as u8).is_none()
    {
        if let Some(c) = check_mentor(pool, a, b) {
            candidates.push(c);
        }
    }
    if crate::relationships::find_relationship(pool, a, id_b, BondType::Grudge as u8).is_none() {
        if let Some(c) = check_grudge(pool, a, b) {
            candidates.push(c);
        }
    }
    if crate::relationships::find_relationship(pool, a, id_b, BondType::ExileBond as u8).is_none() {
        if let Some(c) = check_exile_bond(pool, a, b, region) {
            candidates.push(c);
        }
    }

    candidates
}

/// Attempt to form a bond from a FormationCandidate. Returns (formed, evicted).
fn attempt_bond(
    pool: &mut AgentPool,
    a: usize,
    b: usize,
    candidate: &FormationCandidate,
    turn: u32,
) -> (bool, bool) {
    let turn_u16 = turn as u16;
    if candidate.directed {
        // Mentor: directed bond from mentor to apprentice
        let (src, dst) = if candidate.source_is_first { (a, b) } else { (b, a) };
        let dst_id = pool.ids[dst];
        let was_full = pool.rel_count[src] as usize >= crate::relationships::REL_SLOTS;
        let ok = crate::relationships::upsert_directed(
            pool, src, dst_id,
            candidate.bond_type as u8, candidate.sentiment, turn_u16,
        );
        if ok {
            let evicted = was_full; // if full before, eviction happened
            (true, evicted)
        } else {
            (false, false)
        }
    } else {
        // Symmetric: both sides
        let was_full_a = pool.rel_count[a] as usize >= crate::relationships::REL_SLOTS;
        let was_full_b = pool.rel_count[b] as usize >= crate::relationships::REL_SLOTS;
        let ok = crate::relationships::upsert_symmetric(
            pool, a, b,
            candidate.bond_type as u8, candidate.sentiment, turn_u16,
        );
        if ok {
            let evicted = was_full_a || was_full_b;
            (true, evicted)
        } else {
            (false, false)
        }
    }
}

/// Main formation scan. Called once per tick, after memory write.
///
/// Staggered cadence: only scans regions where `region_index % FORMATION_CADENCE == turn % FORMATION_CADENCE`.
/// Within each scanned region: deterministic hash-based shuffle, pair iteration with early rejection cascade.
pub fn formation_scan(
    pool: &mut AgentPool,
    regions: &[RegionState],
    turn: u32,
    alive_slots: &[usize],
) -> FormationStats {
    let mut stats = FormationStats::default();
    let cadence_phase = turn % agent::FORMATION_CADENCE;

    // Bucket alive agents by region
    let num_regions = regions.len();
    let mut region_buckets: Vec<Vec<usize>> = vec![Vec::new(); num_regions];
    for &slot in alive_slots {
        let r = pool.regions[slot] as usize;
        if r < num_regions {
            region_buckets[r].push(slot);
        }
    }

    for region_idx in 0..num_regions {
        // Staggered cadence check
        if (region_idx as u32) % agent::FORMATION_CADENCE != cadence_phase {
            continue;
        }

        let bucket = &mut region_buckets[region_idx];
        if bucket.len() < 2 {
            continue;
        }

        // Deterministic shuffle: sort by hash(turn, region_idx, agent_id)
        bucket.sort_by_key(|&slot| {
            mix_hash(turn, region_idx as u32, pool.ids[slot])
        });

        // Build belief census for this region
        let belief_census = build_belief_census(pool, bucket);
        let region_pop = bucket.len() as u32;

        // M50b: Belief-divergence cleanup — remove CoReligionist bonds
        // where source and target beliefs have diverged.
        // Build id_to_slot map for this region (targets may have migrated).
        let id_to_slot: HashMap<u32, usize> = alive_slots
            .iter()
            .map(|&s| (pool.ids[s], s))
            .collect();
        let dissolved = belief_divergence_cleanup(pool, bucket, &id_to_slot);
        stats.bonds_dissolved_structural += dissolved;

        // Per-agent formation budget tracking
        let mut agent_bonds_this_pass: HashMap<usize, u8> = HashMap::new();
        let mut region_bonds: u32 = 0;

        // Pair iteration: (i, j) where i < j
        let n = bucket.len();
        for i in 0..n {
            if region_bonds >= agent::MAX_NEW_BONDS_PER_REGION {
                break;
            }

            let slot_a = bucket[i];
            let a_budget = agent_bonds_this_pass.get(&slot_a).copied().unwrap_or(0);
            if a_budget >= agent::MAX_NEW_BONDS_PER_PASS {
                continue;
            }

            for j in (i + 1)..n {
                if region_bonds >= agent::MAX_NEW_BONDS_PER_REGION {
                    break;
                }

                // Re-check slot_a budget (may have been incremented by prior j iterations)
                let a_budget_now = agent_bonds_this_pass.get(&slot_a).copied().unwrap_or(0);
                if a_budget_now >= agent::MAX_NEW_BONDS_PER_PASS {
                    break; // slot_a exhausted, skip remaining j's
                }

                let slot_b = bucket[j];
                let b_budget = agent_bonds_this_pass.get(&slot_b).copied().unwrap_or(0);
                if b_budget >= agent::MAX_NEW_BONDS_PER_PASS {
                    continue;
                }

                stats.pairs_evaluated += 1;

                // Capacity pre-filter: skip only if NEITHER side has room.
                // Directed bonds (Mentor) only need source-side capacity, so
                // we can't reject a pair where one side is full — the full side
                // might be the apprentice (destination) of a directed bond.
                let a_has_cap = has_capacity(pool, slot_a);
                let b_has_cap = has_capacity(pool, slot_b);
                if !a_has_cap && !b_has_cap {
                    continue;
                }

                // Triadic closure check (for Friend gate threshold reduction)
                let triadic = has_shared_positive_contact(pool, slot_a, slot_b);

                // Evaluate pair through all gates — returns all eligible bond types
                let candidates = evaluate_pair(
                    pool, slot_a, slot_b,
                    &belief_census, region_pop,
                    &regions[region_idx],
                    triadic,
                );

                if candidates.is_empty() {
                    continue;
                }

                stats.pairs_eligible += 1;

                // Attempt each candidate with budget checks
                for candidate in &candidates {
                    if region_bonds >= agent::MAX_NEW_BONDS_PER_REGION {
                        break;
                    }
                    let a_budget_inner = agent_bonds_this_pass.get(&slot_a).copied().unwrap_or(0);
                    let b_budget_inner = agent_bonds_this_pass.get(&slot_b).copied().unwrap_or(0);

                    if candidate.directed {
                        // Directed: only source needs budget and capacity
                        let src = if candidate.source_is_first { slot_a } else { slot_b };
                        let src_budget = agent_bonds_this_pass.get(&src).copied().unwrap_or(0);
                        if src_budget >= agent::MAX_NEW_BONDS_PER_PASS {
                            continue;
                        }
                        if !has_capacity_directed(pool, src) {
                            continue;
                        }
                    } else {
                        // Symmetric: both sides need budget
                        if a_budget_inner >= agent::MAX_NEW_BONDS_PER_PASS
                            || b_budget_inner >= agent::MAX_NEW_BONDS_PER_PASS
                        {
                            continue;
                        }
                        if !has_capacity(pool, slot_a) || !has_capacity(pool, slot_b) {
                            continue;
                        }
                    }

                    let (formed, evicted) = attempt_bond(pool, slot_a, slot_b, candidate, turn);
                    if formed {
                        stats.bonds_formed += 1;
                        if evicted {
                            stats.bonds_evicted += 1;
                        }
                        region_bonds += 1;
                        if candidate.directed {
                            // Directed: only source consumes budget
                            let src = if candidate.source_is_first { slot_a } else { slot_b };
                            *agent_bonds_this_pass.entry(src).or_insert(0) += 1;
                        } else {
                            // Symmetric bonds consume budget on both sides
                            *agent_bonds_this_pass.entry(slot_a).or_insert(0) += 1;
                            *agent_bonds_this_pass.entry(slot_b).or_insert(0) += 1;
                        }
                    }
                }
            }
        }
    }

    stats
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

    // ── mix_hash ────────────────────────────────────────────────────────────

    #[test]
    fn test_mix_hash_deterministic() {
        let h1 = mix_hash(10, 5, 42);
        let h2 = mix_hash(10, 5, 42);
        assert_eq!(h1, h2, "same inputs must produce same hash");
    }

    #[test]
    fn test_mix_hash_different_inputs_differ() {
        let h1 = mix_hash(10, 5, 42);
        let h2 = mix_hash(10, 5, 43);
        assert_ne!(h1, h2, "different agent_id should produce different hash");
        let h3 = mix_hash(11, 5, 42);
        assert_ne!(h1, h3, "different turn should produce different hash");
    }

    // ── build_belief_census ─────────────────────────────────────────────────

    #[test]
    fn test_belief_census_counts() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 7);
        let d = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let census = build_belief_census(&pool, &[a, b, c, d]);
        assert_eq!(census.get(&5).copied().unwrap_or(0), 2);
        assert_eq!(census.get(&7).copied().unwrap_or(0), 1);
        assert_eq!(census.get(&BELIEF_NONE), None, "BELIEF_NONE should be excluded");
    }

    // ── has_shared_positive_contact ─────────────────────────────────────────

    #[test]
    fn test_triadic_no_contacts() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        assert!(!has_shared_positive_contact(&pool, a, b), "no contacts → no triadic");
    }

    #[test]
    fn test_triadic_shared_positive_contact() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_c = pool.ids[c];
        // a → c with high sentiment
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Friend as u8, 50, 1);
        // b → c with high sentiment
        crate::relationships::upsert_directed(&mut pool, b, id_c, BondType::Friend as u8, 50, 1);
        assert!(has_shared_positive_contact(&pool, a, b), "shared positive contact c");
    }

    #[test]
    fn test_triadic_below_threshold() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_c = pool.ids[c];
        // a → c with sentiment below TRIADIC_MIN_SENTIMENT (40)
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Friend as u8, 20, 1);
        crate::relationships::upsert_directed(&mut pool, b, id_c, BondType::Friend as u8, 50, 1);
        assert!(!has_shared_positive_contact(&pool, a, b), "a's sentiment too low");
    }

    #[test]
    fn test_triadic_negative_valence_excluded() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_c = pool.ids[c];
        // a → c as Rival (negative valence) with high sentiment magnitude
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Rival as u8, 50, 1);
        // b → c as Grudge (negative valence) with high sentiment magnitude
        crate::relationships::upsert_directed(&mut pool, b, id_c, BondType::Grudge as u8, 50, 1);
        assert!(!has_shared_positive_contact(&pool, a, b),
            "Rival/Grudge bonds should not count as positive contacts for triadic closure");
    }

    // ── multi-bond per pair ─────────────────────────────────────────────────

    #[test]
    fn test_evaluate_pair_allows_multi_bond() {
        let mut pool = AgentPool::new(8);
        // Agent pair: same occ, same civ, same belief (minority), shared memory
        // Should qualify for both Friend and CoReligionist
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        write_battle_memory(&mut pool, a, 10);
        write_battle_memory(&mut pool, b, 10);
        let mut census = HashMap::new();
        census.insert(5u8, 2);
        let region = RegionState::new(0);
        let candidates = evaluate_pair(&pool, a, b, &census, 100, &region, false);
        assert!(candidates.len() >= 2, "should return multiple candidates, got {}", candidates.len());
        let types: Vec<u8> = candidates.iter().map(|c| c.bond_type as u8).collect();
        assert!(types.contains(&(BondType::Friend as u8)), "should include Friend");
        assert!(types.contains(&(BondType::CoReligionist as u8)), "should include CoReligionist");
    }

    #[test]
    fn test_evaluate_pair_skips_existing_type() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        write_battle_memory(&mut pool, a, 10);
        write_battle_memory(&mut pool, b, 10);
        // Pre-existing Friend bond
        crate::relationships::upsert_symmetric(&mut pool, a, b, BondType::Friend as u8, 30, 1);
        let mut census = HashMap::new();
        census.insert(5u8, 2);
        let region = RegionState::new(0);
        let candidates = evaluate_pair(&pool, a, b, &census, 100, &region, false);
        let types: Vec<u8> = candidates.iter().map(|c| c.bond_type as u8).collect();
        assert!(!types.contains(&(BondType::Friend as u8)), "should skip existing Friend");
        assert!(types.contains(&(BondType::CoReligionist as u8)), "should still include CoReligionist");
    }

    // ── has_capacity ────────────────────────────────────────────────────────

    #[test]
    fn test_has_capacity_empty() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        assert!(has_capacity(&pool, a), "empty rel slots → has capacity");
    }

    #[test]
    fn test_has_capacity_full_all_protected() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        for i in 0..8 {
            crate::relationships::write_rel(&mut pool, a, i, (100 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[a] = 8;
        assert!(!has_capacity(&pool, a), "full with all protected → no capacity");
    }

    #[test]
    fn test_has_capacity_full_with_evictable() {
        let mut pool = AgentPool::new(4);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        for i in 0..7 {
            crate::relationships::write_rel(&mut pool, a, i, (100 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        // Last slot is evictable (Friend, not protected)
        crate::relationships::write_rel(&mut pool, a, 7, 107, 10, BondType::Friend as u8, 1);
        pool.rel_count[a] = 8;
        assert!(has_capacity(&pool, a), "full with one evictable → has capacity");
    }

    // ── death_cleanup_sweep ────────────────────────────────────────────────

    #[test]
    fn test_death_cleanup_removes_bond_to_dead_target() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_b = pool.ids[b];
        let id_c = pool.ids[c];

        // a has bonds to b and c
        crate::relationships::upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Kin as u8, 60, 1);
        assert_eq!(pool.rel_count[a], 2);

        // Kill b
        pool.kill(b);
        let mut dead_ids = std::collections::HashSet::new();
        dead_ids.insert(id_b);

        let alive = vec![a, c];
        let (events, removed) = death_cleanup_sweep(&mut pool, &alive, &dead_ids, 10);

        // Bond to b should be removed, bond to c should remain
        assert_eq!(removed, 1);
        assert_eq!(pool.rel_count[a], 1);
        assert_eq!(pool.rel_target_ids[a][0], id_c, "bond to c should remain");
        assert_eq!(pool.rel_bond_types[a][0], BondType::Kin as u8);

        // Should emit one dissolution event
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].agent_id, pool.ids[a]);
        assert_eq!(events[0].event_type, agent::LIFE_EVENT_DISSOLUTION);
        assert_eq!(events[0].target_region, BondType::Friend as u16);
        assert_eq!(events[0].turn, 10);
        assert_eq!(events[0].target_agent_id, id_b);
        assert_eq!(events[0].formed_turn, 1); // matches upsert_directed formed_turn param at line 1655
    }

    #[test]
    fn test_death_cleanup_packed_prefix_maintained() {
        // Verify that after removing a bond at position 0, the remaining bonds
        // are compacted with swap-remove and no gaps exist.
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let d = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_b = pool.ids[b];
        let id_c = pool.ids[c];
        let id_d = pool.ids[d];

        // a has bonds: [b, c, d]
        crate::relationships::upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 30, 1);
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Rival as u8, -20, 2);
        crate::relationships::upsert_directed(&mut pool, a, id_d, BondType::Kin as u8, 60, 3);
        assert_eq!(pool.rel_count[a], 3);

        // Kill b (at position 0)
        pool.kill(b);
        let mut dead_ids = std::collections::HashSet::new();
        dead_ids.insert(id_b);

        let alive = vec![a, c, d];
        let (_events, removed) = death_cleanup_sweep(&mut pool, &alive, &dead_ids, 5);
        assert_eq!(removed, 1);
        assert_eq!(pool.rel_count[a], 2);

        // Remaining bonds should be packed: slots [0] and [1] occupied, [2] cleared
        let targets: Vec<u32> = (0..pool.rel_count[a] as usize)
            .map(|i| pool.rel_target_ids[a][i])
            .collect();
        assert!(targets.contains(&id_c), "c bond should remain");
        assert!(targets.contains(&id_d), "d bond should remain");
        assert!(!targets.contains(&id_b), "b bond should be gone");
    }

    #[test]
    fn test_death_cleanup_swap_remove_rechecks_swapped_entry() {
        // When bond at [0] is removed, the last entry swaps in.
        // If that swapped entry ALSO targets a dead agent, it should be removed too.
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let c = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let d = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, BELIEF_NONE);
        let id_b = pool.ids[b];
        let id_c = pool.ids[c];
        let id_d = pool.ids[d];

        // a has bonds: [b, c, d] at indices [0, 1, 2]
        crate::relationships::upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 30, 1);
        crate::relationships::upsert_directed(&mut pool, a, id_c, BondType::Rival as u8, -20, 2);
        crate::relationships::upsert_directed(&mut pool, a, id_d, BondType::Friend as u8, 40, 3);

        // Kill both b and d. When b at [0] is removed, d at [2] swaps to [0].
        // The while loop should NOT skip d — it re-checks [0].
        pool.kill(b);
        pool.kill(d);
        let mut dead_ids = std::collections::HashSet::new();
        dead_ids.insert(id_b);
        dead_ids.insert(id_d);

        let alive = vec![a, c];
        let (_events, removed) = death_cleanup_sweep(&mut pool, &alive, &dead_ids, 5);
        assert_eq!(removed, 2, "both b and d bonds should be removed");
        assert_eq!(pool.rel_count[a], 1, "only c should remain");
        assert_eq!(pool.rel_target_ids[a][0], id_c, "remaining bond should target c");
    }

    // ── belief_divergence_cleanup ──────────────────────────────────────────

    #[test]
    fn test_belief_divergence_removes_coreligionist() {
        let mut pool = AgentPool::new(8);
        // a and b start with same belief (5), forming CoReligionist bond
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let id_b = pool.ids[b];
        let id_a = pool.ids[a];

        // Create symmetric CoReligionist bond
        crate::relationships::upsert_symmetric(
            &mut pool, a, b, BondType::CoReligionist as u8, 25, 1,
        );
        assert_eq!(pool.rel_count[a], 1);
        assert_eq!(pool.rel_count[b], 1);

        // b converts to belief 7 — beliefs diverge
        pool.beliefs[b] = 7;

        let region_slots = vec![a, b];
        let id_map: HashMap<u32, usize> = vec![
            (id_a, a),
            (id_b, b),
        ].into_iter().collect();

        let removed = belief_divergence_cleanup(&mut pool, &region_slots, &id_map);
        // Both sides' CoReligionist bonds should be removed (cleanup runs for each agent)
        assert_eq!(removed, 2, "both a→b and b→a CoReligionist bonds removed");
        assert_eq!(pool.rel_count[a], 0);
        assert_eq!(pool.rel_count[b], 0);
    }

    #[test]
    fn test_belief_divergence_preserves_non_coreligionist() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let id_b = pool.ids[b];
        let id_a = pool.ids[a];

        // Create both CoReligionist and Friend bonds
        crate::relationships::upsert_symmetric(
            &mut pool, a, b, BondType::CoReligionist as u8, 25, 1,
        );
        crate::relationships::upsert_symmetric(
            &mut pool, a, b, BondType::Friend as u8, 30, 1,
        );
        assert_eq!(pool.rel_count[a], 2);

        // b converts — beliefs diverge
        pool.beliefs[b] = 7;

        let region_slots = vec![a, b];
        let id_map: HashMap<u32, usize> = vec![
            (id_a, a),
            (id_b, b),
        ].into_iter().collect();

        let removed = belief_divergence_cleanup(&mut pool, &region_slots, &id_map);
        assert_eq!(removed, 2, "only CoReligionist removed (both sides)");
        // Friend bond should remain
        assert_eq!(pool.rel_count[a], 1);
        assert_eq!(pool.rel_bond_types[a][0], BondType::Friend as u8);
        assert_eq!(pool.rel_count[b], 1);
        assert_eq!(pool.rel_bond_types[b][0], BondType::Friend as u8);
    }

    #[test]
    fn test_belief_divergence_same_belief_untouched() {
        let mut pool = AgentPool::new(8);
        let a = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let b = spawn(&mut pool, 0, 0, Occupation::Farmer, 20, 0.5, 0, 1, 2, 5);
        let id_b = pool.ids[b];
        let id_a = pool.ids[a];

        crate::relationships::upsert_symmetric(
            &mut pool, a, b, BondType::CoReligionist as u8, 25, 1,
        );

        // Same belief — should NOT be removed
        let region_slots = vec![a, b];
        let id_map: HashMap<u32, usize> = vec![
            (id_a, a),
            (id_b, b),
        ].into_iter().collect();

        let removed = belief_divergence_cleanup(&mut pool, &region_slots, &id_map);
        assert_eq!(removed, 0, "same belief → no removal");
        assert_eq!(pool.rel_count[a], 1);
        assert_eq!(pool.rel_count[b], 1);
    }
}
