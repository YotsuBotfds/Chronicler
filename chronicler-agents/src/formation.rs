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
                    migration_driver: crate::tick::NO_MIGRATION_DRIVER,
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
    let dx = pool.x[a] - pool.x[b];
    let dy = pool.y[a] - pool.y[b];
    let dist = (dx * dx + dy * dy).sqrt();
    marriage_score_from(
        pool.civ_affinities[a], pool.civ_affinities[b],
        pool.beliefs[a], pool.beliefs[b],
        [pool.cultural_value_0[a], pool.cultural_value_1[a], pool.cultural_value_2[a]],
        [pool.cultural_value_0[b], pool.cultural_value_1[b], pool.cultural_value_2[b]],
        dist,
    )
}

/// Marriage score from the pair's attributes and distance (one shared
/// definition, so the planned and reference scans add the same terms in the
/// same order).
#[inline]
fn marriage_score_from(
    civ_a: u8, civ_b: u8, ba: u8, bb: u8, cv_a: [u8; 3], cv_b: [u8; 3], dist: f32,
) -> f32 {
    use crate::agent::*;
    let mut score: f32 = 0.0;
    if civ_a == civ_b { score += MARRIAGE_SAME_CIV_BONUS; }
    if ba == bb && ba != BELIEF_NONE { score += MARRIAGE_SAME_BELIEF_BONUS; }
    else if ba != BELIEF_NONE && bb != BELIEF_NONE && ba != bb { score -= MARRIAGE_CROSS_FAITH_PENALTY; }
    for i in 0..3 {
        if cv_a[i] == cv_b[i] && cv_a[i] != CULTURAL_VALUE_EMPTY { score += MARRIAGE_CULTURE_MATCH_BONUS; }
    }
    if dist > 0.001 { score += (1.0 / (1.0 + dist * 4.0)).min(MARRIAGE_CLOSENESS_CAP); }
    else { score += MARRIAGE_CLOSENESS_CAP; }
    score
}

/// M57a: Marriage scan — scored greedy matching within regions (exact mode).
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
    marriage_scan_with_mode(
        pool, regions, signals, turn, alive_slots, crate::scale::AgentScaleMode::Exact,
    )
}

const MARRIAGE_INITIAL_SENTIMENT: i8 = 50;

/// Marriage scan with an explicit scale mode.
///
/// Both modes plan each scanned region independently (in parallel) from the
/// unchanged pool and then commit the planned marriages region by region.
/// This is exact: a marriage only writes the two spouses' relationship
/// slots, every planned spouse is distinct, and nothing a plan reads (age,
/// spouse status, parents, civ, belief, culture, position, free relationship
/// capacity) is changed by another region's or another pair's marriage.
///
/// Exact mode reproduces the reference all-pairs scan of
/// [`marriage_scan_reference`] (same counters, same spouses). Fast mode
/// examines a bounded spatial sample of partners per agent; see
/// [`crate::scale`].
pub fn marriage_scan_with_mode(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &crate::signals::TickSignals,
    turn: u32,
    alive_slots: &[usize],
    mode: crate::scale::AgentScaleMode,
) -> FormationStats {
    use rayon::prelude::*;

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

    // Regions on this turn's cadence with at least two eligible agents.
    let scanned: Vec<(usize, Vec<usize>)> = (0..num_regions)
        .filter(|&r| (r as u32) % agent::MARRIAGE_CADENCE == cadence_phase)
        .filter_map(|r| {
            let eligible: Vec<usize> = region_buckets[r]
                .iter()
                .filter(|&&slot| {
                    pool.ages[slot] >= agent::MARRIAGE_MIN_AGE
                        && crate::relationships::get_spouse_id(pool, slot).is_none()
                })
                .copied()
                .collect();
            (eligible.len() >= 2).then_some((r, eligible))
        })
        .collect();

    let plans: Vec<Option<MarriagePlan>> = {
        let pool_ref = &*pool;
        let war = &civ_at_war;
        scanned
            .par_iter()
            .map(|(r, eligible)| plan_region_marriages(pool_ref, eligible, *r as u32, turn, war, mode))
            .collect()
    };

    for ((region_idx, eligible), plan) in scanned.iter().zip(plans) {
        match plan {
            Some(plan) => {
                stats.marriage_pairs_evaluated += plan.evaluated;
                stats.marriage_pairs_rejected_distance += plan.rejected_distance;
                stats.marriage_pairs_rejected_incest += plan.rejected_incest;
                stats.marriage_pairs_rejected_hostile += plan.rejected_hostile;
                for &(slot_a, slot_b) in &plan.pairs {
                    let ok = crate::relationships::upsert_symmetric(
                        pool, slot_a, slot_b,
                        BondType::Marriage as u8,
                        MARRIAGE_INITIAL_SENTIMENT,
                        turn as u16,
                    );
                    debug_assert!(ok, "planned marriage must have free relationship capacity");
                    if ok {
                        record_marriage(pool, slot_a, slot_b, &mut stats);
                    }
                }
            }
            // Non-finite positions: keep the reference sort semantics.
            None => marriage_region_reference(
                pool, *region_idx, eligible, turn, &civ_at_war, &mut stats,
            ),
        }
    }

    stats
}

/// Reference all-pairs marriage scan (the pre-scale implementation). Kept for
/// the non-finite-position fallback and as the oracle in equivalence tests.
pub fn marriage_scan_reference(
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
        marriage_region_reference(pool, region_idx, &eligible, turn, &civ_at_war, &mut stats);
    }

    stats
}

/// One region of the reference scan: all pairs, stable sort, greedy accept.
fn marriage_region_reference(
    pool: &mut AgentPool,
    region_idx: usize,
    eligible: &[usize],
    turn: u32,
    civ_at_war: &[bool; 256],
    stats: &mut FormationStats,
) {
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
            married_this_region.insert(mc.slot_a);
            married_this_region.insert(mc.slot_b);
            record_marriage(pool, mc.slot_a, mc.slot_b, stats);
        }
    }
}

/// Marriage counters for an accepted pair (after the bond is written).
fn record_marriage(pool: &AgentPool, slot_a: usize, slot_b: usize, stats: &mut FormationStats) {
    stats.marriages_formed += 1;

    // Track civ stats
    let civ_a = pool.civ_affinities[slot_a];
    let civ_b = pool.civ_affinities[slot_b];
    if civ_a == civ_b {
        stats.same_civ_marriages += 1;
    } else {
        stats.cross_civ_marriages += 1;
    }

    // Track faith stats (only when both have a belief)
    let belief_a = pool.beliefs[slot_a];
    let belief_b = pool.beliefs[slot_b];
    if belief_a != agent::BELIEF_NONE && belief_b != agent::BELIEF_NONE {
        if belief_a == belief_b {
            stats.same_faith_marriages += 1;
        } else {
            stats.cross_faith_marriages += 1;
        }
    }
}

// ---------------------------------------------------------------------------
// Planned marriage matching (exact and fast modes)
// ---------------------------------------------------------------------------

/// Marriages planned for one region from the unchanged pool.
struct MarriagePlan {
    evaluated: u32,
    rejected_distance: u32,
    rejected_incest: u32,
    rejected_hostile: u32,
    /// (slot_a, slot_b) in the order the reference greedy accepts them;
    /// slot_a precedes slot_b in the eligible list.
    pairs: Vec<(usize, usize)>,
}

/// Region-local copy of the eligible agents' marriage inputs.
struct Eligible {
    slot: Vec<usize>,
    x: Vec<f32>,
    y: Vec<f32>,
    id: Vec<u32>,
    civ: Vec<u8>,
    belief: Vec<u8>,
    cv: Vec<[u8; 3]>,
    parents: Vec<[u32; 2]>,
    /// A marriage bond can be written (free or evictable relationship slot).
    can_wed: Vec<bool>,
}

impl Eligible {
    fn new(pool: &AgentPool, eligible: &[usize]) -> Self {
        let n = eligible.len();
        let mut e = Eligible {
            slot: eligible.to_vec(),
            x: Vec::with_capacity(n),
            y: Vec::with_capacity(n),
            id: Vec::with_capacity(n),
            civ: Vec::with_capacity(n),
            belief: Vec::with_capacity(n),
            cv: Vec::with_capacity(n),
            parents: Vec::with_capacity(n),
            can_wed: Vec::with_capacity(n),
        };
        for &s in eligible {
            e.x.push(pool.x[s]);
            e.y.push(pool.y[s]);
            e.id.push(pool.ids[s]);
            e.civ.push(pool.civ_affinities[s]);
            e.belief.push(pool.beliefs[s]);
            e.cv.push([pool.cultural_value_0[s], pool.cultural_value_1[s], pool.cultural_value_2[s]]);
            e.parents.push(pool.parent_ids(s));
            // Mirrors upsert_symmetric's slot resolution for an unmarried
            // agent: no existing Marriage bond, so it needs a free slot or an
            // evictable (non-protected) one. Depends only on this agent.
            e.can_wed.push(
                (pool.rel_count[s] as usize) < crate::relationships::REL_SLOTS
                    || crate::relationships::find_evictable(pool, s).is_some(),
            );
        }
        e
    }

    fn len(&self) -> usize {
        self.slot.len()
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum PairClass {
    Far,
    Incest,
    Hostile,
    Valid,
}

/// Reference rejection cascade for an eligible pair (symmetric in a, b),
/// plus the pair distance. The distance is symmetric bit for bit
/// (`x_a - x_b` is the exact negation of `x_b - x_a`), so it equals the one
/// the reference computes for its score.
#[inline]
fn classify_pair_dist(e: &Eligible, a: usize, b: usize, civ_at_war: &[bool; 256]) -> (PairClass, f32) {
    let dist = pair_d2(e, a, b).sqrt();
    (classify_with_dist(e, a, b, dist, civ_at_war), dist)
}

/// Squared distance of an eligible pair, the value `classify_pair_dist`
/// takes the root of.
#[inline(always)]
fn pair_d2(e: &Eligible, a: usize, b: usize) -> f32 {
    let dx = e.x[a] - e.x[b];
    let dy = e.y[a] - e.y[b];
    dx * dx + dy * dy
}

#[inline(always)]
fn classify_with_dist(e: &Eligible, a: usize, b: usize, dist: f32, civ_at_war: &[bool; 256]) -> PairClass {
    if dist > agent::MARRIAGE_RADIUS {
        return PairClass::Far;
    }
    let has_parent = |child: usize, pid: u32| {
        pid != agent::PARENT_NONE && (e.parents[child][0] == pid || e.parents[child][1] == pid)
    };
    let parent_child = has_parent(a, e.id[b]) || has_parent(b, e.id[a]);
    let shared = e.parents[a]
        .iter()
        .any(|&pa| pa != agent::PARENT_NONE && e.parents[b].contains(&pa));
    if parent_child || shared {
        return PairClass::Incest;
    }
    let (civ_a, civ_b) = (e.civ[a], e.civ[b]);
    if civ_a != civ_b && (civ_at_war[civ_a as usize] || civ_at_war[civ_b as usize]) {
        return PairClass::Hostile;
    }
    PairClass::Valid
}

/// Squared distances at or below this are exactly the pairs the reference
/// keeps within `MARRIAGE_RADIUS`: the largest `d2` with
/// `d2.sqrt() <= MARRIAGE_RADIUS`. The correctly rounded square root is
/// monotone, so `!(d2.sqrt() > MARRIAGE_RADIUS)` holds exactly for
/// `d2 <= marriage_radius_sq()` (`marriage_radius_threshold_is_exact`).
fn marriage_radius_sq() -> f32 {
    let r = agent::MARRIAGE_RADIUS;
    let next = |v: f32| f32::from_bits(v.to_bits() + 1);
    let prev = |v: f32| f32::from_bits(v.to_bits() - 1);
    let mut t = r * r;
    while t.sqrt() > r {
        t = prev(t);
    }
    while next(t).sqrt() <= r {
        t = next(t);
    }
    t
}

/// Per-thread buffers of the exact marriage scan.
#[derive(Default)]
struct MarriageScratch {
    /// Squared distance from the scanning agent to each eligible agent.
    d2: Vec<f32>,
    /// Eligible agents within the radius of the scanning agent (ascending).
    near: Vec<u32>,
}

/// The eligible agents within `MARRIAGE_RADIUS` of `a` (`a` included), in
/// ascending order, into `buf.near`. The squared distance is the expression
/// `classify_pair_dist` takes the root of, computed for all agents in one
/// vectorisable pass and compared with `max_sq` (`marriage_radius_sq`).
fn near_eligible(e: &Eligible, a: usize, max_sq: f32, buf: &mut MarriageScratch) {
    let n = e.len();
    let (xa, ya) = (e.x[a], e.y[a]);
    buf.d2.clear();
    buf.d2.extend(e.x.iter().zip(&e.y).map(|(&x, &y)| {
        let dx = xa - x;
        let dy = ya - y;
        dx * dx + dy * dy
    }));
    buf.near.clear();
    buf.near.resize(n, 0);
    let mut m = 0;
    for (b, &d2) in buf.d2.iter().enumerate() {
        // Written before the length moves, so kept entries stay in order.
        buf.near[m] = b as u32;
        m += (d2 <= max_sq) as usize;
    }
    buf.near.truncate(m);
}

/// Greedy order of a candidate pair: higher score first, then lower hash,
/// then the reference's insertion order (lower eligible indices), which is
/// what its stable sort falls back to.
#[derive(Clone, Copy, Debug)]
struct PairKey {
    score: f32,
    hash: u64,
    lo: u32,
    hi: u32,
}

impl PairKey {
    /// True when `self` is accepted before `other` by the reference greedy.
    /// Scores are finite here (non-finite positions use the reference path).
    #[inline]
    fn before(&self, other: &PairKey) -> bool {
        match self.score.partial_cmp(&other.score) {
            Some(std::cmp::Ordering::Greater) => true,
            Some(std::cmp::Ordering::Less) => false,
            _ => (self.hash, self.lo, self.hi) < (other.hash, other.lo, other.hi),
        }
    }
}

/// Score of an eligible pair from its distance (as the reference
/// `marriage_score(pool, lo, hi)` computes it).
#[inline(always)]
fn pair_score(e: &Eligible, a: usize, b: usize, dist: f32) -> f32 {
    let (lo, hi) = if a < b { (a, b) } else { (b, a) };
    marriage_score_from(e.civ[lo], e.civ[hi], e.belief[lo], e.belief[hi], e.cv[lo], e.cv[hi], dist)
}

#[inline]
fn pair_key_scored(e: &Eligible, a: usize, b: usize, score: f32, turn: u32, region_idx: u32) -> PairKey {
    let (lo, hi) = if a < b { (a, b) } else { (b, a) };
    PairKey {
        score,
        hash: marriage_pair_hash(turn, region_idx, e.id[lo], e.id[hi]),
        lo: lo as u32,
        hi: hi as u32,
    }
}

/// Best few partners of one agent among those still unmatched at its last
/// scan, best first. When `complete`, it held every partner then available.
const MARRIAGE_TOP_K: usize = 8;

#[derive(Clone)]
struct TopPartners {
    entries: Vec<(PairKey, u32)>,
    complete: bool,
}

impl TopPartners {
    fn new() -> Self {
        Self { entries: Vec::with_capacity(MARRIAGE_TOP_K + 1), complete: true }
    }

    /// Offer a partner given only its score when that already decides: a
    /// pair scoring below a full cache's worst entry cannot enter it (the
    /// score is the first key), so its hash need not be computed. Returns
    /// false when the caller must build the full key and `offer` it.
    #[inline]
    fn rejects_score(&mut self, score: f32) -> bool {
        if self.entries.len() == MARRIAGE_TOP_K && score < self.entries[MARRIAGE_TOP_K - 1].0.score {
            self.complete = false;
            return true;
        }
        false
    }

    #[inline]
    fn offer(&mut self, key: PairKey, partner: u32) {
        if self.entries.len() == MARRIAGE_TOP_K {
            self.complete = false;
            if !key.before(&self.entries[MARRIAGE_TOP_K - 1].0) {
                return;
            }
            self.entries.pop();
        }
        let pos = self.entries.iter().position(|(k, _)| key.before(k)).unwrap_or(self.entries.len());
        self.entries.insert(pos, (key, partner));
    }
}

/// Plan one region's marriages. `None` when a position is not finite (the
/// caller then runs the reference scan, whose comparator is then not a total
/// order and cannot be reproduced by any other algorithm).
fn plan_region_marriages(
    pool: &AgentPool,
    eligible: &[usize],
    region_idx: u32,
    turn: u32,
    civ_at_war: &[bool; 256],
    mode: crate::scale::AgentScaleMode,
) -> Option<MarriagePlan> {
    use rayon::prelude::*;

    let e = Eligible::new(pool, eligible);
    if !e.x.iter().chain(e.y.iter()).all(|v| v.is_finite()) {
        return None;
    }
    let n = e.len();

    // Fast mode: a bounded candidate adjacency (CSR) and the rejection
    // counters over the examinations it made. Small regions keep the exact
    // all-pairs scan, so fast mode only differs where it saves work.
    let fast = match mode {
        crate::scale::AgentScaleMode::Fast if n > crate::scale::FAST_MARRIAGE_SCAN => {
            Some(fast_marriage_candidates(&e, civ_at_war, turn, region_idx))
        }
        _ => None,
    };

    // Offer every valid, writable, unmatched partner of `a`. In exact mode
    // the initial scan (`count`) also tallies the reference rejection
    // counters over the pairs (a, b > a), so every pair is classified once
    // for the counters, exactly as in the reference loop.
    //
    // Exact mode visits only the agents within the radius (`near_eligible`):
    // a farther one is never a candidate, and every farther later agent is
    // a `Far` pair for the counters, so they are counted at once. The cache
    // and counters do not depend on the order of the visits (`TopPartners`
    // keeps the best entries of a strict total order).
    let radius_sq = marriage_radius_sq();
    let scan = |buf: &mut MarriageScratch, a: usize, matched: &[bool], count: bool| -> (TopPartners, [u32; 3]) {
        let mut top = TopPartners::new();
        let mut c = [0u32; 3];
        let wed_a = e.can_wed[a];
        // `d2` is the pair's squared distance (`pair_d2`).
        let mut visit = |b: usize, d2: f32| {
            if b == a {
                return;
            }
            let tally = count && b > a;
            if !tally && (!wed_a || matched[b] || !e.can_wed[b]) {
                return;
            }
            let dist = d2.sqrt();
            let class = classify_with_dist(&e, a, b, dist, civ_at_war);
            if tally {
                match class {
                    PairClass::Far => c[0] = c[0].wrapping_add(1),
                    PairClass::Incest => c[1] = c[1].wrapping_add(1),
                    PairClass::Hostile => c[2] = c[2].wrapping_add(1),
                    PairClass::Valid => {}
                }
            }
            if class == PairClass::Valid && wed_a && !matched[b] && e.can_wed[b] {
                let score = pair_score(&e, a, b, dist);
                if !top.rejects_score(score) {
                    top.offer(pair_key_scored(&e, a, b, score, turn, region_idx), b as u32);
                }
            }
        };
        match &fast {
            None => {
                if !count && !wed_a {
                    // No visit would classify or offer anything.
                    return (top, c);
                }
                near_eligible(&e, a, radius_sq, buf);
                let mut near_later = 0u32;
                for &b in &buf.near {
                    let b = b as usize;
                    near_later += (b > a) as u32;
                    visit(b, buf.d2[b]);
                }
                if count {
                    let later = (n - 1 - a) as u32;
                    c[0] = c[0].wrapping_add(later - near_later);
                }
            }
            Some(((starts, partners), _, _)) => {
                for &b in &partners[starts[a] as usize..starts[a + 1] as usize] {
                    let b = b as usize;
                    visit(b, pair_d2(&e, a, b));
                }
            }
        }
        (top, c)
    };

    // Locally dominant matching. With a strict total order on pairs, the
    // greedy matching (accept pairs best-first when both are free) is the
    // unique matching built by repeatedly accepting pairs that are each
    // other's best remaining partner, so this reproduces the reference
    // greedy without materialising and sorting every candidate pair.
    let mut matched = vec![false; n];
    let initial: Vec<(TopPartners, [u32; 3])> = {
        let m = &matched;
        let count = fast.is_none();
        (0..n)
            .into_par_iter()
            .map_init(MarriageScratch::default, |buf, a| scan(buf, a, m, count))
            .collect()
    };
    let (evaluated, counts) = match &fast {
        None => {
            let pairs = (n as u64) * (n as u64).saturating_sub(1) / 2;
            let counts = initial.iter().fold([0u32; 3], |x, (_, c)| {
                [x[0].wrapping_add(c[0]), x[1].wrapping_add(c[1]), x[2].wrapping_add(c[2])]
            });
            // The reference counts pairs in a u32 (wrapping in release).
            (pairs as u32, counts)
        }
        Some((_, evaluated, counts)) => (*evaluated, *counts),
    };
    let mut top: Vec<TopPartners> = initial.into_iter().map(|(t, _)| t).collect();
    let mut accepted: Vec<(PairKey, usize, usize)> = Vec::new();
    loop {
        let mut newly: Vec<(PairKey, usize, usize)> = Vec::new();
        for a in 0..n {
            if matched[a] {
                continue;
            }
            if let Some(&(key, b)) = top[a].entries.first() {
                let b = b as usize;
                if a < b && top[b].entries.first().map(|&(_, c)| c as usize) == Some(a) {
                    newly.push((key, a, b));
                }
            }
        }
        if newly.is_empty() {
            break;
        }
        for &(_, a, b) in &newly {
            matched[a] = true;
            matched[b] = true;
        }
        accepted.extend(newly);
        // Agents whose best partner was just taken advance to their next
        // cached partner, or rescan when the cache ran out.
        let dirty: Vec<usize> = (0..n)
            .filter(|&a| {
                !matched[a]
                    && top[a].entries.first().map_or(false, |&(_, b)| matched[b as usize])
            })
            .collect();
        let refreshed: Vec<(usize, TopPartners)> = {
            let m = &matched;
            let t = &top;
            dirty
                .par_iter()
                .map_init(MarriageScratch::default, |buf, &a| {
                    let mut cur = t[a].clone();
                    cur.entries.retain(|&(_, b)| !m[b as usize]);
                    if cur.entries.is_empty() && !cur.complete {
                        cur = scan(buf, a, m, false).0;
                    }
                    (a, cur)
                })
                .collect()
        };
        for (a, cur) in refreshed {
            top[a] = cur;
        }
    }
    accepted.sort_by(|x, y| {
        if x.0.before(&y.0) {
            std::cmp::Ordering::Less
        } else {
            std::cmp::Ordering::Greater
        }
    });

    Some(MarriagePlan {
        evaluated,
        rejected_distance: counts[0],
        rejected_incest: counts[1],
        rejected_hostile: counts[2],
        pairs: accepted.into_iter().map(|(_, a, b)| (e.slot[a], e.slot[b])).collect(),
    })
}

/// Fast mode: each eligible agent examines a deterministic stride sample of
/// at most `FAST_MARRIAGE_SCAN` agents from the 3 x 3 block of a
/// population-sized grid around it and keeps its `FAST_MARRIAGE_CANDIDATES`
/// best valid partners in the reference greedy order, so the bounded graph
/// keeps the high-scoring (same civ / faith / culture) pairs the exact greedy
/// would pick first. Returns the union of those lists as a CSR adjacency, the
/// number of (agent, partner) examinations and their rejection counters.
fn fast_marriage_candidates(
    e: &Eligible,
    civ_at_war: &[bool; 256],
    turn: u32,
    region_idx: u32,
) -> ((Vec<u32>, Vec<u32>), u32, [u32; 3]) {
    use rayon::prelude::*;

    let n = e.len();
    let scan = crate::scale::FAST_MARRIAGE_SCAN.max(1);
    let keep = crate::scale::FAST_MARRIAGE_CANDIDATES.max(1);
    // Cells sized so a 3 x 3 block holds about `scan` agents on average.
    let side = (((9 * n) as f64 / scan as f64).sqrt().ceil() as usize).clamp(1, 256);
    let cell_of = |i: usize| {
        let cx = ((e.x[i] * side as f32) as usize).min(side - 1);
        let cy = ((e.y[i] * side as f32) as usize).min(side - 1);
        cy * side + cx
    };
    let mut starts = vec![0u32; side * side + 1];
    for i in 0..n {
        starts[cell_of(i) + 1] += 1;
    }
    for c in 0..side * side {
        starts[c + 1] += starts[c];
    }
    let mut fill = starts[..side * side].to_vec();
    let mut members = vec![0u32; n];
    for i in 0..n {
        let c = cell_of(i);
        members[fill[c] as usize] = i as u32;
        fill[c] += 1;
    }

    let per_agent: Vec<(Vec<u32>, u32, [u32; 3])> = (0..n)
        .into_par_iter()
        .map_init(Vec::new, |block: &mut Vec<u32>, a| {
            let c = cell_of(a);
            let (cx, cy) = (c % side, c / side);
            block.clear();
            for row in cy.saturating_sub(1)..=(cy + 1).min(side - 1) {
                let first = row * side + cx.saturating_sub(1);
                let last = row * side + (cx + 1).min(side - 1);
                block.extend_from_slice(&members[starts[first] as usize..starts[last + 1] as usize]);
            }
            let stride = if block.len() > scan { (block.len() + scan - 1) / scan } else { 1 };
            let mut best: Vec<(PairKey, u32)> = Vec::with_capacity(keep + 1);
            let mut examined = 0u32;
            let mut counts = [0u32; 3];
            let mut idx = a % stride;
            while idx < block.len() {
                let b = block[idx] as usize;
                idx += stride;
                if b == a {
                    continue;
                }
                examined += 1;
                let (class, dist) = classify_pair_dist(e, a, b, civ_at_war);
                match class {
                    PairClass::Far => counts[0] += 1,
                    PairClass::Incest => counts[1] += 1,
                    PairClass::Hostile => counts[2] += 1,
                    PairClass::Valid => {
                        if !e.can_wed[a] || !e.can_wed[b] {
                            continue;
                        }
                        let score = pair_score(e, a, b, dist);
                        if best.len() == keep && score < best[keep - 1].0.score {
                            continue;
                        }
                        let key = pair_key_scored(e, a, b, score, turn, region_idx);
                        if best.len() == keep && !key.before(&best[keep - 1].0) {
                            continue;
                        }
                        let pos = best.iter().position(|(k, _)| key.before(k)).unwrap_or(best.len());
                        best.insert(pos, (key, b as u32));
                        best.truncate(keep);
                    }
                }
            }
            (best.into_iter().map(|(_, b)| b).collect(), examined, counts)
        })
        .collect();

    let mut examined = 0u32;
    let mut counts = [0u32; 3];
    let mut pairs: Vec<(u32, u32)> = Vec::new();
    for (a, (partners, ex, c)) in per_agent.iter().enumerate() {
        examined = examined.wrapping_add(*ex);
        for k in 0..3 {
            counts[k] = counts[k].wrapping_add(c[k]);
        }
        for &b in partners {
            let a = a as u32;
            pairs.push(if a < b { (a, b) } else { (b, a) });
        }
    }
    pairs.sort_unstable();
    pairs.dedup();

    let mut degree = vec![0u32; n + 1];
    for &(a, b) in &pairs {
        degree[a as usize + 1] += 1;
        degree[b as usize + 1] += 1;
    }
    for i in 0..n {
        degree[i + 1] += degree[i];
    }
    let mut fill = degree[..n].to_vec();
    let mut partners = vec![0u32; pairs.len() * 2];
    for &(a, b) in &pairs {
        partners[fill[a as usize] as usize] = b;
        fill[a as usize] += 1;
        partners[fill[b as usize] as usize] = a;
        fill[b as usize] += 1;
    }
    ((degree, partners), examined, counts)
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
    formation_scan_with_mode(pool, regions, turn, alive_slots, crate::scale::AgentScaleMode::Exact)
}

/// Formation scan with an explicit scale mode. Exact mode is the reference
/// scan. Fast mode pairs each agent only with the next
/// `FAST_FORMATION_PARTNERS` agents in the region's shuffled order, which
/// bounds the work per agent when few pairs pass the gates.
pub fn formation_scan_with_mode(
    pool: &mut AgentPool,
    regions: &[RegionState],
    turn: u32,
    alive_slots: &[usize],
    mode: crate::scale::AgentScaleMode,
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

    // Alive id -> slot lookup for belief-divergence cleanup (targets may have
    // migrated). Ids and liveness do not change during the scan, so one map
    // serves every region; it used to be rebuilt per scanned region.
    let mut id_to_slot: Option<HashMap<u32, usize>> = None;

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
        let id_to_slot = id_to_slot.get_or_insert_with(|| {
            alive_slots.iter().map(|&s| (pool.ids[s], s)).collect()
        });
        let dissolved = belief_divergence_cleanup(pool, bucket, id_to_slot);
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

            let j_end = match mode {
                crate::scale::AgentScaleMode::Exact => n,
                crate::scale::AgentScaleMode::Fast => {
                    (i + 1).saturating_add(crate::scale::FAST_FORMATION_PARTNERS).min(n)
                }
            };
            for j in (i + 1)..j_end {
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

    /// `d2 <= marriage_radius_sq()` is exactly the reference's
    /// `!(d2.sqrt() > MARRIAGE_RADIUS)`: at the threshold, at its neighbours
    /// and at the squared distances of coordinates a few ulps around the
    /// radius apart.
    #[test]
    fn marriage_radius_threshold_is_exact() {
        let r = agent::MARRIAGE_RADIUS;
        let t = marriage_radius_sq();
        let up = |v: f32| f32::from_bits(v.to_bits() + 1);
        assert!(!(t.sqrt() > r));
        assert!(up(t).sqrt() > r);
        let mut d2s: Vec<f32> = Vec::new();
        let mut v = f32::from_bits(t.to_bits() - 64);
        for _ in 0..128 {
            d2s.push(v);
            v = up(v);
        }
        for base in [0.0f32, 0.1, 0.37, 0.5, 0.74] {
            for k in -40i32..=40 {
                let other = f32::from_bits((base + r).to_bits().wrapping_add(k as u32));
                for dy in [0.0f32, 1e-7, 1e-4] {
                    let dx = other - base;
                    d2s.push(dx * dx + dy * dy);
                }
            }
        }
        for d2 in d2s {
            assert_eq!(d2 <= t, !(d2.sqrt() > r), "d2 {d2:e}");
        }
    }

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

// ---------------------------------------------------------------------------
// Exact checkpoint state (`crate::persist`): every field, in declaration order.
// ---------------------------------------------------------------------------

crate::persist_struct!(FormationStats {
    bonds_formed, bonds_evicted, bonds_dissolved_structural, bonds_dissolved_death,
    pairs_evaluated, pairs_eligible, marriages_formed, marriage_pairs_evaluated,
    marriage_pairs_rejected_hostile, marriage_pairs_rejected_incest,
    marriage_pairs_rejected_distance, cross_civ_marriages, same_civ_marriages,
    cross_faith_marriages, same_faith_marriages,
});

// Inactive enumerator experiment: production planners and Fast mode never call it.
#[cfg(test)]
mod exact_near_broadphase_experiment {
    use super::*;
    use std::hint::black_box;
    use std::time::Instant;

    const CROSSOVER: usize = 256;
    const CELLS: usize = 16;
    const SCREEN_SECONDS: u64 = 60;
    const SCREEN_RSS_KIB: u64 = 512 * 1024;
    const PAIRS: usize = 5;

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    enum Route { ReferenceNonFinite, LinearSmall, LinearOutOfDomain, LinearAll, Grid }

    struct BroadPhase {
        route: Route,
        words: usize,
        unions: Vec<u64>,
        neighbor_counts: [usize; CELLS],
        peak_index_bytes: usize,
    }

    #[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
    struct Work {
        queries: u64,
        words: u64,
        distances: u64,
        gathered: u64,
        later_far: u64,
        incest: u64,
        hostile: u64,
        valid: u64,
    }

    // Exactly representable binary boundaries, deliberately wider than 0.25.
    // A two-cell separation is >= 5/16 even before f32 rounding; it cannot
    // satisfy the original correctly rounded distance test at radius 1/4.
    fn axis_cell(value: f32) -> usize {
        if value < 5.0 / 16.0 { 0 }
        else if value < 10.0 / 16.0 { 1 }
        else if value < 15.0 / 16.0 { 2 }
        else { 3 }
    }

    fn cell(e: &Eligible, a: usize) -> usize { 4 * axis_cell(e.y[a]) + axis_cell(e.x[a]) }

    fn baseline_route(e: &Eligible) -> Route {
        if e.x.iter().chain(&e.y).all(|v| v.is_finite()) { Route::LinearAll }
        else { Route::ReferenceNonFinite }
    }

    impl BroadPhase {
        fn new(e: &Eligible) -> Self {
            let mut result = Self { route: Route::LinearSmall, words: 0, unions: Vec::new(),
                neighbor_counts: [0; CELLS], peak_index_bytes: 0 };
            if baseline_route(e) == Route::ReferenceNonFinite {
                result.route = Route::ReferenceNonFinite;
                return result;
            }
            if e.len() <= CROSSOVER { return result; }
            if e.x.iter().chain(&e.y).any(|&v| !(0.0..=1.0).contains(&v)) {
                result.route = Route::LinearOutOfDomain;
                return result;
            }
            let mut counts = [0usize; CELLS];
            for a in 0..e.len() { counts[cell(e, a)] += 1; }
            for c in 0..CELLS {
                let (x, y) = (c % 4, c / 4);
                for yy in y.saturating_sub(1)..=(y + 1).min(3) {
                    for xx in x.saturating_sub(1)..=(x + 1).min(3) {
                        result.neighbor_counts[c] += counts[yy * 4 + xx];
                    }
                }
            }
            // No query can exclude anything: preserve the original SIMD scan.
            if (0..CELLS).all(|c| counts[c] == 0 || result.neighbor_counts[c] == e.len()) {
                result.route = Route::LinearAll;
                return result;
            }
            result.words = e.len().checked_add(63).expect("eligible count overflow") / 64;
            let length = CELLS.checked_mul(result.words).expect("index size overflow");
            let mut membership = vec![0u64; length];
            result.unions = vec![0u64; length];
            for a in 0..e.len() {
                membership[cell(e, a) * result.words + a / 64] |= 1u64 << (a % 64);
            }
            for c in 0..CELLS {
                let (x, y) = (c % 4, c / 4);
                for yy in y.saturating_sub(1)..=(y + 1).min(3) {
                    for xx in x.saturating_sub(1)..=(x + 1).min(3) {
                        let other = yy * 4 + xx;
                        for w in 0..result.words {
                            result.unions[c * result.words + w] |= membership[other * result.words + w];
                        }
                    }
                }
            }
            result.peak_index_bytes = (membership.capacity() + result.unions.capacity()) * std::mem::size_of::<u64>();
            result.route = Route::Grid;
            result
        }

        fn query(&self, e: &Eligible, a: usize, max_sq: f32, buf: &mut MarriageScratch, work: &mut Work) {
            assert_ne!(self.route, Route::ReferenceNonFinite, "keep the existing reference-planner fallback");
            work.queries += 1;
            let c = if self.route == Route::Grid { cell(e, a) } else { 0 };
            if self.route != Route::Grid || self.neighbor_counts[c] == e.len() {
                near_eligible(e, a, max_sq, buf);
                work.distances += e.len() as u64;
            } else {
                // Reuse initialized scratch; do not zero n values per query.
                buf.d2.resize(e.len(), 0.0);
                buf.near.clear();
                work.words += self.words as u64;
                work.distances += self.neighbor_counts[c] as u64;
                let (xa, ya) = (e.x[a], e.y[a]);
                for w in 0..self.words {
                    let mut bits = self.unions[c * self.words + w];
                    while bits != 0 {
                        let bit = bits.trailing_zeros() as usize;
                        bits &= bits - 1;
                        let b = w * 64 + bit;
                        debug_assert!(b < e.len());
                        // Preserve the reference direction and f32 expression.
                        let dx = xa - e.x[b];
                        let dy = ya - e.y[b];
                        let d2 = dx * dx + dy * dy;
                        buf.d2[b] = d2;
                        if d2 <= max_sq { buf.near.push(b as u32); }
                    }
                }
            }
            work.gathered += buf.near.len() as u64;
        }
    }

    fn eligible(points: &[(f32, f32)]) -> Eligible {
        let n = points.len();
        Eligible { slot: (0..n).map(|a| 2 * a + 1).collect(),
            x: points.iter().map(|p| p.0).collect(), y: points.iter().map(|p| p.1).collect(),
            id: (0..n).map(|a| (a / 2) as u32).collect(), // include duplicate IDs and zero
            civ: (0..n).map(|a| (a % 4) as u8).collect(),
            belief: (0..n).map(|a| (a % 7) as u8).collect(),
            cv: (0..n).map(|a| [(a % 6) as u8, ((a + 1) % 6) as u8, 255]).collect(),
            parents: (0..n).map(|a| if a % 9 == 0 { [11, agent::PARENT_NONE] }
                else { [agent::PARENT_NONE; 2] }).collect(),
            can_wed: (0..n).map(|a| a % 11 != 0).collect() }
    }

    fn spread(n: usize) -> Vec<(f32, f32)> {
        let mut side = 1usize;
        while side * side < n { side += 1; }
        (0..n).map(|a| (((a % side) as f32 + 0.5) / side as f32,
                       ((a / side) as f32 + 0.5) / side as f32)).collect()
    }

    fn classify_counts(e: &Eligible, a: usize, buf: &MarriageScratch, work: &mut Work) {
        let mut war = [false; 256]; war[1] = true;
        let mut near_later = 0usize;
        for &b in &buf.near {
            let b = b as usize;
            if b <= a { continue; }
            near_later += 1;
            match classify_with_dist(e, a, b, buf.d2[b].sqrt(), &war) {
                PairClass::Far => panic!("radius prefilter admitted a far pair"),
                PairClass::Incest => work.incest += 1,
                PairClass::Hostile => work.hostile += 1,
                PairClass::Valid => work.valid += 1,
            }
        }
        work.later_far += (e.len() - 1 - a - near_later) as u64;
    }

    fn hash_word(hash: &mut u64, value: u64) {
        for byte in value.to_le_bytes() { *hash ^= byte as u64; *hash = hash.wrapping_mul(0x100000001b3); }
    }

    fn differential(points: &[(f32, f32)]) -> (Route, u64, Work, Work) {
        differential_eligible(&eligible(points))
    }

    fn differential_eligible(e: &Eligible) -> (Route, u64, Work, Work) {
        let broad = BroadPhase::new(e);
        if baseline_route(e) == Route::ReferenceNonFinite {
            assert_eq!(broad.route, Route::ReferenceNonFinite);
            return (broad.route, 0, Work::default(), Work::default());
        }
        let (mut old, mut new) = (MarriageScratch::default(), MarriageScratch::default());
        let (mut old_work, mut new_work) = (Work::default(), Work::default());
        let mut hash = 0xcbf29ce484222325u64;
        let max_sq = marriage_radius_sq();
        for a in 0..e.len() {
            near_eligible(e, a, max_sq, &mut old);
            old_work.queries += 1; old_work.distances += e.len() as u64;
            old_work.gathered += old.near.len() as u64;
            broad.query(e, a, max_sq, &mut new, &mut new_work);
            assert_eq!(old.near, new.near, "ordered near indices, query {a}");
            hash_word(&mut hash, a as u64); hash_word(&mut hash, old.near.len() as u64);
            for &b in &old.near {
                assert_eq!(old.d2[b as usize].to_bits(), new.d2[b as usize].to_bits(), "d2 bits, query {a}, partner {b}");
                hash_word(&mut hash, b as u64); hash_word(&mut hash, old.d2[b as usize].to_bits() as u64);
            }
            classify_counts(e, a, &old, &mut old_work);
            classify_counts(e, a, &new, &mut new_work);
        }
        assert_eq!((old_work.queries, old_work.gathered, old_work.later_far, old_work.incest, old_work.hostile, old_work.valid),
                   (new_work.queries, new_work.gathered, new_work.later_far, new_work.incest, new_work.hostile, new_work.valid));
        assert!(new_work.distances <= old_work.distances);
        (broad.route, hash, old_work, new_work)
    }

    #[test]
    fn exact_near_fixed_crossover_and_density_fallbacks() {
        for n in [0, 1, 16, 255, 256, 257, 1024] {
            let (route, _, old, new) = differential(&spread(n));
            assert_eq!(route, if n <= CROSSOVER { Route::LinearSmall } else { Route::Grid });
            if n > CROSSOVER { assert!(new.distances < old.distances); }
        }
        assert_eq!(differential(&vec![(0.125, 0.125); 257]).0, Route::LinearAll);
    }

    #[test]
    fn exact_near_all_cells_boundaries_zero_and_subnormals() {
        let mut axis = vec![0.0, -0.0, f32::from_bits(1), f32::from_bits(0x8000_0001), 1.0];
        for boundary in [0.25f32, 5.0 / 16.0, 0.5, 10.0 / 16.0, 15.0 / 16.0] {
            for offset in -2i32..=2 { axis.push(f32::from_bits((boundary.to_bits() as i32 + offset) as u32)); }
        }
        let points: Vec<_> = axis.iter().flat_map(|&x| axis.iter().map(move |&y| (x, y))).collect();
        // The negative subnormal is finite and outside the domain: keep linear.
        assert_eq!(differential(&points).0, Route::LinearOutOfDomain);
        let bounded: Vec<_> = points.into_iter().filter(|&(x, y)| x >= 0.0 && y >= 0.0).collect();
        assert_eq!(differential(&bounded).0, Route::Grid);
        assert_eq!(axis_cell(0.0), axis_cell(-0.0));
        for x in 0..4 { for y in 0..4 {
            let p = if x == 3 { 0.96875 } else { (x as f32 + 0.5) * 0.3125 };
            let q = if y == 3 { 0.96875 } else { (y as f32 + 0.5) * 0.3125 };
            assert_eq!(axis_cell(p), x); assert_eq!(axis_cell(q), y);
        }}
    }

    #[test]
    fn exact_near_tight_grid_radius_rounding_counterexample() {
        let a = f32::from_bits(0.25f32.to_bits() - 1);
        let b = 0.5f32;
        assert_eq!((b - a).to_bits(), 0.25f32.to_bits());
        assert_eq!((a * 4.0) as usize, 0); assert_eq!((b * 4.0) as usize, 2);
        let mut points = spread(257); points[0] = (a, 0.0); points[1] = (b, -0.0);
        let e = eligible(&points); let mut old = MarriageScratch::default();
        near_eligible(&e, 0, marriage_radius_sq(), &mut old);
        assert!(old.near.contains(&1));
        assert_eq!(differential(&points).0, Route::Grid);
    }

    #[test]
    fn exact_near_preserves_nonfinite_and_out_of_domain_routes() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
            let mut points = spread(257); points[3].0 = value;
            assert_eq!(differential(&points).0, Route::ReferenceNonFinite);
        }
        for value in [-1.0, f32::MAX, -f32::MAX, f32::from_bits(1.0f32.to_bits() + 1)] {
            let mut points = spread(257); points[3] = (value, -value);
            assert_eq!(differential(&points).0, Route::LinearOutOfDomain);
        }
    }

    #[test]
    fn exact_near_does_not_read_identity_or_mutate_eligible_inputs() {
        let points = spread(257); let mut e = eligible(&points);
        let original_x: Vec<_> = e.x.iter().map(|x| x.to_bits()).collect();
        let original_y: Vec<_> = e.y.iter().map(|x| x.to_bits()).collect();
        e.slot.reverse(); e.id.fill(0); e.can_wed.fill(false); e.parents.fill([99, 99]);
        let broad = BroadPhase::new(&e);
        let (mut old, mut new) = (MarriageScratch::default(), MarriageScratch::default());
        for a in 0..e.len() {
            near_eligible(&e, a, marriage_radius_sq(), &mut old);
            broad.query(&e, a, marriage_radius_sq(), &mut new, &mut Work::default());
            assert_eq!(old.near, new.near);
        }
        assert_eq!(original_x, e.x.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        assert_eq!(original_y, e.y.iter().map(|x| x.to_bits()).collect::<Vec<_>>());
        // The same owned scratch can cross region sizes and fallback routes.
        for points in [spread(512), vec![(0.125, 0.125); 257], spread(0), spread(16), spread(257)] {
            let next = eligible(&points); let index = BroadPhase::new(&next);
            for a in 0..next.len() {
                near_eligible(&next, a, marriage_radius_sq(), &mut old);
                index.query(&next, a, marriage_radius_sq(), &mut new, &mut Work::default());
                assert_eq!(old.near, new.near);
                for &b in &old.near { assert_eq!(old.d2[b as usize].to_bits(), new.d2[b as usize].to_bits()); }
            }
        }
    }

    #[test]
    fn exact_near_uses_current_eligible_slots_with_dead_holes() {
        let mut pool = AgentPool::new(280);
        let points = spread(280);
        let mut spawned = Vec::new();
        for (a, &(x, y)) in points.iter().enumerate() {
            let slot = pool.spawn(0, (a % 4) as u8, agent::Occupation::Farmer,
                30, 0.5, 0.0, 0.5, 0, 1, 2, agent::BELIEF_NONE);
            pool.x[slot] = x; pool.y[slot] = y;
            spawned.push(slot);
        }
        for (a, &slot) in spawned.iter().enumerate() { if a % 19 == 0 { pool.kill(slot); } }
        let replacement = pool.spawn(0, 0, agent::Occupation::Farmer,
            30, 0.5, 0.0, 0.5, 0, 1, 2, agent::BELIEF_NONE);
        pool.x[replacement] = 0.5; pool.y[replacement] = 0.5;
        let live: Vec<_> = (0..pool.capacity()).filter(|&s| pool.is_alive(s)).collect();
        assert!(live.windows(2).any(|w| w[1] != w[0] + 1), "required dead holes");
        let e = Eligible::new(&pool, &live);
        assert_eq!(differential_eligible(&e).0, Route::Grid);
        let mut nonfinite = pool.x.clone(); nonfinite[live[0]] = f32::NAN;
        pool.x = nonfinite;
        assert!(plan_region_marriages(&pool, &live, 0, 0, &[false; 256], crate::scale::AgentScaleMode::Exact).is_none());
        assert_eq!(BroadPhase::new(&Eligible::new(&pool, &live)).route, Route::ReferenceNonFinite);
    }

    fn process_cpu_ticks() -> u64 {
        let stat = std::fs::read_to_string("/proc/self/stat").expect("Linux process CPU accounting required");
        let fields: Vec<_> = stat[stat.rfind(')').expect("process stat name") + 2..].split_whitespace().collect();
        fields[11].parse::<u64>().unwrap() + fields[12].parse::<u64>().unwrap()
    }

    fn peak_rss_kib() -> u64 {
        let status = std::fs::read_to_string("/proc/self/status").expect("Linux RSS accounting required");
        status.lines().find(|line| line.starts_with("VmHWM:"))
            .and_then(|line| line.split_whitespace().nth(1)).unwrap().parse().unwrap()
    }

    fn screen_guard(start: Instant, cpu0: u64) {
        assert!(start.elapsed().as_secs() < SCREEN_SECONDS, "fixed screen wall budget exhausted");
        // Linux hosted runner convention is independently recorded by getconf.
        let hz: u64 = std::env::var("CHRONICLER_SCREEN_CLK_TCK").expect("explicit CLK_TCK required").parse().unwrap();
        assert!(hz > 0 && process_cpu_ticks() - cpu0 <= SCREEN_SECONDS * hz, "fixed screen CPU budget exhausted");
        assert!(peak_rss_kib() <= SCREEN_RSS_KIB, "fixed screen RSS budget exhausted");
    }

    struct Sample { total_ns: u128, setup_ns: u128, query_ns: u128, work: Work, index_live_bytes: usize,
        index_peak_bytes: usize, scratch_bytes: usize, route: Route }

    fn sample(points: &[(f32, f32)], candidate: bool) -> Sample {
        let total = Instant::now();
        let e = eligible(black_box(points));
        let broad = candidate.then(|| BroadPhase::new(&e));
        let selected = broad.as_ref().map_or_else(|| baseline_route(&e), |b| b.route);
        let setup_ns = total.elapsed().as_nanos();
        let mut buf = MarriageScratch::default(); let mut work = Work::default();
        let query = Instant::now(); let max_sq = marriage_radius_sq();
        if selected != Route::ReferenceNonFinite {
            for a in 0..e.len() {
                if let Some(b) = &broad { b.query(&e, a, max_sq, &mut buf, &mut work); }
                else {
                    near_eligible(&e, a, max_sq, &mut buf);
                    work.queries += 1; work.distances += e.len() as u64; work.gathered += buf.near.len() as u64;
                }
                black_box(&buf.near); black_box(&buf.d2);
            }
        }
        let query_ns = query.elapsed().as_nanos();
        let index_live_bytes = broad.as_ref().map_or(0, |b| b.unions.capacity() * 8);
        let index_peak_bytes = broad.as_ref().map_or(0, |b| b.peak_index_bytes);
        let scratch_bytes = buf.d2.capacity() * 4 + buf.near.capacity() * 4;
        // Total includes fixture/index setup, query work and all owned drops.
        drop(buf); drop(broad); drop(e);
        Sample { total_ns: total.elapsed().as_nanos(), setup_ns, query_ns, work, index_live_bytes,
            index_peak_bytes, scratch_bytes, route: selected }
    }

    #[test]
    #[ignore = "remote-only fixed synthetic enumerator screen; separate root activation required"]
    fn exact_near_broadphase_fixed_screen() {
        assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"), "remote-only experiment");
        assert_eq!(std::env::var("CHRONICLER_EXACT_NEAR_SCREEN").as_deref(), Ok("fixed-synthetic-v1"));
        for name in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT"] {
            assert_eq!(std::env::var(name).as_deref(), Ok("1"), "thread cap {name}");
        }
        assert_eq!(std::env::var("PYTHONHASHSEED").as_deref(), Ok("0"));
        let status = std::fs::read_to_string("/proc/self/status").unwrap();
        let affinity = status.lines().find(|s| s.starts_with("Cpus_allowed_list:"))
            .and_then(|s| s.split_whitespace().nth(1)).unwrap();
        assert!(affinity.parse::<usize>().is_ok(), "one actual affinity CPU required");
        let start = Instant::now(); let cpu0 = process_cpu_ticks();
        let mut boundary = spread(1024);
        for (a, point) in boundary.iter_mut().enumerate() {
            let v = [0.0f32, 0.25, 0.3125, 0.5, 0.625, 0.9375, 1.0][a % 7];
            *point = (v, if a % 2 == 0 { 0.3125 } else { 0.9375 });
        }
        let mut outside = spread(1024); outside[0] = (-1.0, f32::MAX);
        let mut nan = spread(1024); nan[0].0 = f32::NAN;
        let mut inf = spread(1024); inf[0].1 = f32::INFINITY;
        let cases = vec![
            ("empty0", spread(0)), ("singleton1", spread(1)), ("small16", spread(16)),
            ("spread255", spread(255)), ("spread256", spread(256)), ("spread257", spread(257)),
            ("spread1024", spread(1024)), ("spread4096", spread(4096)),
            ("dense1024", vec![(0.125, 0.125); 1024]), ("dense4096", vec![(0.96875, 0.96875); 4096]),
            ("boundaries1024", boundary), ("outside1024", outside), ("nan1024", nan), ("infinity1024", inf),
            ("zeros1024", (0..1024).map(|a| if a % 2 == 0 { (-0.0, 0.0) } else { (f32::from_bits(1), -0.0) }).collect()),
        ];
        println!("EXACT_NEAR {{\"kind\":\"header\",\"version\":1,\"synthetic_only\":true,\"cases\":15,\"pairs\":5,\"crossover\":256,\"wall_seconds_cap\":60,\"cpu_seconds_cap\":60,\"rss_kib_cap\":524288}}");
        let mut accepted = true;
        for (name, points) in &cases {
            screen_guard(start, cpu0);
            let (route, hash, old_work, new_work) = differential(points);
            println!("EXACT_NEAR {{\"kind\":\"parity\",\"case\":\"{}\",\"route\":\"{:?}\",\"ordered_near_d2_fnv\":\"{:016x}\",\"old_distances\":{},\"new_distances\":{},\"new_words\":{},\"near_results\":{},\"later_far\":{},\"incest\":{},\"hostile\":{},\"valid\":{}}}",
                name, route, hash, old_work.distances, new_work.distances, new_work.words, old_work.gathered,
                old_work.later_far, old_work.incest, old_work.hostile, old_work.valid);
            let (mut old_times, mut new_times) = (Vec::new(), Vec::new());
            for pair in 0..PAIRS {
                for candidate in if pair % 2 == 0 { [false, true] } else { [true, false] } {
                    screen_guard(start, cpu0);
                    let before_cpu = process_cpu_ticks(); let row = sample(points, candidate);
                    screen_guard(start, cpu0);
                    let ticks = process_cpu_ticks() - before_cpu;
                    if candidate { new_times.push(row.total_ns); } else { old_times.push(row.total_ns); }
                    println!("EXACT_NEAR {{\"kind\":\"sample\",\"case\":\"{}\",\"pair\":{},\"arm\":\"{}\",\"route\":\"{:?}\",\"setup_ns\":{},\"query_ns\":{},\"total_ns_with_drop\":{},\"cpu_ticks\":{},\"peak_process_rss_kib\":{},\"index_live_bytes\":{},\"index_peak_bytes\":{},\"scratch_capacity_bytes\":{},\"words\":{},\"distances\":{},\"gathered\":{}}}",
                        name, pair, if candidate { "candidate" } else { "old" }, row.route, row.setup_ns, row.query_ns,
                        row.total_ns, ticks, peak_rss_kib(), row.index_live_bytes, row.index_peak_bytes, row.scratch_bytes,
                        row.work.words, row.work.distances, row.work.gathered);
                }
            }
            old_times.sort_unstable(); new_times.sort_unstable();
            let (old, new) = (old_times[PAIRS / 2], new_times[PAIRS / 2]);
            let limit = if *name == "spread1024" || *name == "spread4096" { old * 90 / 100 }
                else if points.len() <= CROSSOVER || route == Route::ReferenceNonFinite { old * 105 / 100 + 5_000 }
                else { old * 105 / 100 };
            let pass = new <= limit;
            accepted &= pass;
            println!("EXACT_NEAR {{\"kind\":\"decision\",\"case\":\"{}\",\"old_median_ns\":{},\"candidate_median_ns\":{},\"limit_ns\":{},\"pass\":{}}}", name, old, new, limit, pass);
        }
        screen_guard(start, cpu0);
        println!("EXACT_NEAR {{\"kind\":\"final\",\"complete_cases\":15,\"samples\":150,\"accepted_for_later_planner_work\":{},\"production_promoted\":false,\"worlds\":0}}", accepted);
        assert!(accepted, "fixed synthetic screen rejected; preserve result and do not tune/retry");
    }
}
