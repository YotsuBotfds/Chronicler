# M50b: Relationship Emergence & Cohorts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give all agents Rust-native relationship formation, active dissolution, and cohort-facing instrumentation, replacing the Python-side M40 formation coordinator in agent modes.

**Architecture:** A Rust formation engine runs as the last phase inside `tick_agents()` at staggered cadence, scanning co-located agent pairs for bond eligibility using deterministic bounded-confidence gates. Death cleanup runs every tick after demographics. Python's `form_and_sync_relationships()` is gated off in agent modes. Social-need blend plumbing ships at `alpha=0.0` (M53 ramps).

**Tech Stack:** Rust (chronicler-agents crate), PyO3/Arrow FFI, Python (src/chronicler/)

**Prerequisite:** M50a (Relationship Substrate) must be merged to `main` before implementation begins. Verify the post-M50a reconciliation checklist in the spec (Section 2) before starting any task.

**Spec:** `docs/superpowers/specs/2026-03-20-m50b-relationship-emergence-cohorts-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/formation.rs` | Formation engine: scan scheduling, similarity gates, per-type rules, triadic closure, budgeting, dissolution |
| `chronicler-agents/tests/test_m50b_formation.rs` | Rust integration tests for formation + dissolution |
| `tests/test_m50b_formation.py` | Python integration tests for bridge, narration, social-need blend |

### Modified Files
| File | Changes |
|------|---------|
| `chronicler-agents/src/agent.rs` | ~27 formation constants, 1 new `AgentEvent` type |
| `chronicler-agents/src/pool.rs` | `synthesis_budget: Vec<u8>` dormant field |
| `chronicler-agents/src/memory.rs` | `agents_share_memory_with_valence()` helper |
| `chronicler-agents/src/needs.rs` | Social-need blend in `social_restoration()` |
| `chronicler-agents/src/tick.rs` | Death cleanup at phase 5.1, formation scan at phase 8 |
| `chronicler-agents/src/ffi.rs` | `get_relationship_stats()`, `get_all_relationships()` FFI methods, dissolution event emission |
| `chronicler-agents/src/lib.rs` | Re-export `formation` module and new public symbols |
| `src/chronicler/agent_bridge.py` | `rust_owns_formation` flag, dissolved-edge event collection |
| `src/chronicler/simulation.py` | Gate off `form_and_sync_relationships()` in agent modes |
| `src/chronicler/narrative.py` | Widen renderer for Kin/Friend/Grudge, source swap to `agent_bonds`, filter tightening |
| `src/chronicler/analytics.py` | `extract_relationship_metrics()` extractor |
| `src/chronicler/main.py` | `--relationship-stats` CLI flag |

---

## Task 1: Constants, Dormant Fields & Memory Helper

**Files:**
- Modify: `chronicler-agents/src/agent.rs` (after line ~279, existing M50a constants)
- Modify: `chronicler-agents/src/pool.rs` (after `rel_count` field, ~line 72)
- Modify: `chronicler-agents/src/memory.rs` (after `agents_share_memory()`, ~line 332)
- Modify: `chronicler-agents/src/lib.rs` (add re-export)
- Test: `chronicler-agents/src/memory.rs` (inline unit tests)

**Context for workers:**
- `agent.rs` already has M50a relationship constants (KIN_INITIAL_PARENT etc.) starting around line 266. Add M50b constants in a clearly labeled block after them.
- `pool.rs` AgentPool struct has M50a relationship SoA fields at lines 68-72. Add `synthesis_budget` after `rel_count`.
- `memory.rs` has `agents_share_memory()` at line 312 which returns `Option<(u8, u16)>`. The new variant returns signed intensities.
- Both `spawn()` branches in `pool.rs` must initialize `synthesis_budget` to `SYNTHESIS_BUDGET_MAX`.

- [ ] **Step 1: Add formation constants to agent.rs**

Add after the existing M50a relationship constants block:

```rust
// ---------------------------------------------------------------------------
// M50b: Formation constants [CALIBRATE M53]
// ---------------------------------------------------------------------------

// Scan scheduling
pub const FORMATION_CADENCE: u32 = 6;

// Similarity gate weights
pub const W_CULTURE: f32 = 0.35;
pub const W_BELIEF: f32 = 0.35;
pub const W_OCCUPATION: f32 = 0.15;
pub const W_AFFINITY: f32 = 0.15;
pub const SAME_RANK_WEIGHT: f32 = 1.0;
pub const CROSS_RANK_WEIGHT: f32 = 0.5;

// Friend
pub const FRIEND_THRESHOLD: f32 = 0.50;
pub const FRIEND_INITIAL_SENTIMENT: i8 = 30;

// CoReligionist
pub const MINORITY_THRESHOLD: f32 = 0.40;
pub const CORELIGIONIST_INITIAL_SENTIMENT: i8 = 25;

// Rival
pub const RIVAL_WEALTH_PROXIMITY: f32 = 50.0;
pub const RIVAL_SIMILARITY_FLOOR: f32 = 0.30;
pub const RIVAL_MIN_AMBITION: f32 = 0.50;
pub const RIVAL_INITIAL_SENTIMENT: i8 = -20;

// Mentor
pub const MENTOR_AGE_GAP: u16 = 15;
pub const MENTOR_INITIAL_SENTIMENT: i8 = 35;

// Grudge
pub const GRUDGE_INITIAL_SENTIMENT: i8 = -30;

// ExileBond
pub const EXILE_INITIAL_SENTIMENT: i8 = 35;

// Triadic closure
pub const TRIADIC_MIN_SENTIMENT: i8 = 40;
pub const TRIADIC_THRESHOLD_REDUCTION: f32 = 0.15;

// Formation budgeting
pub const MAX_NEW_BONDS_PER_PASS: u8 = 2;
pub const MAX_NEW_BONDS_PER_REGION: u32 = 50;

// Social-need blend
pub const SOCIAL_BLEND_ALPHA: f32 = 0.0;
pub const SOCIAL_RESTORE_BOND: f32 = 0.010;
pub const SOCIAL_BOND_TARGET: f32 = 4.0;

// Synthesis budget (dormant)
pub const SYNTHESIS_BUDGET_MAX: u8 = 100;

// AgentEvent type for dissolution
pub const LIFE_EVENT_DISSOLUTION: u8 = 6;
```

- [ ] **Step 2: Add synthesis_budget to AgentPool**

In `pool.rs`, add field after `rel_count`:

```rust
    // M50b: Synthesis budget (dormant — not decremented until M53)
    pub synthesis_budget: Vec<u8>,
```

Initialize in both `spawn()` branches to `agent::SYNTHESIS_BUDGET_MAX`. Initialize in pool `new()` / `with_capacity()` as empty Vec matching other fields.

- [ ] **Step 3: Write failing test for agents_share_memory_with_valence**

In `memory.rs` inline tests (after existing `test_agents_share_memory` tests):

```rust
#[test]
fn test_agents_share_memory_with_valence_returns_intensities() {
    let mut pool = test_pool(2);
    // Agent 0: Battle memory, turn 10, intensity +50
    pool.memory_event_types[0][0] = MemoryEventType::Battle as u8;
    pool.memory_turns[0][0] = 10;
    pool.memory_intensities[0][0] = 50;
    pool.memory_count[0] = 1;
    // Agent 1: Battle memory, turn 10, intensity -30
    pool.memory_event_types[1][0] = MemoryEventType::Battle as u8;
    pool.memory_turns[1][0] = 10;
    pool.memory_intensities[1][0] = -30;
    pool.memory_count[1] = 1;

    let result = agents_share_memory_with_valence(&pool, 0, 1);
    assert!(result.is_some());
    let (et, turn, int_a, int_b) = result.unwrap();
    assert_eq!(et, MemoryEventType::Battle as u8);
    assert_eq!(turn, 10);
    assert_eq!(int_a, 50);
    assert_eq!(int_b, -30);
}

#[test]
fn test_agents_share_memory_with_valence_no_match() {
    let mut pool = test_pool(2);
    pool.memory_event_types[0][0] = MemoryEventType::Famine as u8;
    pool.memory_turns[0][0] = 10;
    pool.memory_intensities[0][0] = -40;
    pool.memory_count[0] = 1;
    pool.memory_event_types[1][0] = MemoryEventType::Battle as u8;
    pool.memory_turns[1][0] = 10;
    pool.memory_intensities[1][0] = -30;
    pool.memory_count[1] = 1;

    assert!(agents_share_memory_with_valence(&pool, 0, 1).is_none());
}
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_agents_share_memory_with_valence`
Expected: FAIL — function not defined

- [ ] **Step 5: Implement agents_share_memory_with_valence**

In `memory.rs`, after `agents_share_memory()`:

```rust
/// M50b: Like agents_share_memory but returns per-agent signed intensities.
/// Returns (event_type, turn, intensity_a, intensity_b) of strongest shared match.
pub fn agents_share_memory_with_valence(
    pool: &AgentPool, a: usize, b: usize,
) -> Option<(u8, u16, i8, i8)> {
    let count_a = pool.memory_count[a] as usize;
    let count_b = pool.memory_count[b] as usize;
    let mut best: Option<(u8, u16, i8, i8, u16)> = None; // (et, turn, int_a, int_b, combined)
    for i in 0..count_a {
        let et_a = pool.memory_event_types[a][i];
        let turn_a = pool.memory_turns[a][i];
        let int_a = pool.memory_intensities[a][i];
        for j in 0..count_b {
            if pool.memory_event_types[b][j] == et_a
                && turn_a.abs_diff(pool.memory_turns[b][j]) <= 1
            {
                let int_b = pool.memory_intensities[b][j];
                let combined = int_a.unsigned_abs() as u16 + int_b.unsigned_abs() as u16;
                if best.is_none() || combined > best.unwrap().4 {
                    best = Some((et_a, turn_a, int_a, int_b, combined));
                }
            }
        }
    }
    best.map(|(et, turn, int_a, int_b, _)| (et, turn, int_a, int_b))
}
```

- [ ] **Step 6: Add re-export in lib.rs**

Add `agents_share_memory_with_valence` to the existing memory re-export line.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_agents_share_memory_with_valence`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs chronicler-agents/src/memory.rs chronicler-agents/src/lib.rs
git commit -m "feat(m50b): formation constants, synthesis_budget field, memory valence helper"
```

---

## Task 2: Formation Engine Core — Similarity & Per-Type Gates

**Files:**
- Create: `chronicler-agents/src/formation.rs`
- Modify: `chronicler-agents/src/lib.rs` (add module declaration)

**Context for workers:**
- This task creates the formation module with pure functions — no tick integration yet.
- All formation gates are deterministic. No RNG consumed.
- The similarity gate uses weighted cross-rank cultural overlap from `pool.cultural_value_0/1/2`.
- Bond types use the M50a `BondType` enum from `relationships.rs`. Verify ordinals match: Mentor=0, Rival=1, Marriage=2, ExileBond=3, CoReligionist=4, Kin=5, Friend=6, Grudge=7.
- `agents_share_memory()` and `agents_share_memory_with_valence()` take slot indices, not agent IDs.
- ExileBond gate must check `controller_civ != 255` (uncontrolled sentinel) before the affinity mismatch check.
- Mentor is `UpsertDirected` (asymmetric) — evaluate both orientations `(A older, C older)` per pair.

- [ ] **Step 1: Create formation.rs with module structure and cultural_similarity**

```rust
//! M50b: Formation engine — bond eligibility gates, scan orchestration, dissolution.

use crate::agent;
use crate::memory;
use crate::pool::AgentPool;
use crate::region::RegionState;
use crate::relationships::BondType;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Cultural similarity (weighted cross-rank overlap)
// ---------------------------------------------------------------------------

/// Compute weighted cultural similarity between two agents.
/// Uses greedy best-match: same-rank match wins over cross-rank.
/// Returns [0.0, 1.0].
pub fn cultural_similarity(pool: &AgentPool, a: usize, b: usize) -> f32 {
    let a_vals = [
        pool.cultural_value_0[a],
        pool.cultural_value_1[a],
        pool.cultural_value_2[a],
    ];
    let b_vals = [
        pool.cultural_value_0[b],
        pool.cultural_value_1[b],
        pool.cultural_value_2[b],
    ];
    let mut score = 0.0_f32;
    let mut b_used = [false; 3];

    // Pass 1: same-rank matches (highest weight)
    for i in 0..3 {
        if a_vals[i] == b_vals[i] {
            score += agent::SAME_RANK_WEIGHT;
            b_used[i] = true;
        }
    }

    // Pass 2: cross-rank matches (lower weight, unused slots only)
    for i in 0..3 {
        // Skip if this A-slot already matched same-rank
        if a_vals[i] == b_vals[i] {
            continue;
        }
        for j in 0..3 {
            if !b_used[j] && a_vals[i] == b_vals[j] {
                score += agent::CROSS_RANK_WEIGHT;
                b_used[j] = true;
                break;
            }
        }
    }

    score / 3.0
}

/// Compute weighted compatibility score between two agents.
/// Combines cultural similarity, belief match, occupation match, affinity match.
pub fn compatibility_score(pool: &AgentPool, a: usize, b: usize) -> f32 {
    let cult = cultural_similarity(pool, a, b);
    let belief = if pool.beliefs[a] == pool.beliefs[b] { 1.0 } else { 0.0 };
    let occ = if pool.occupations[a] == pool.occupations[b] { 1.0 } else { 0.0 };
    let aff = if pool.civ_affinities[a] == pool.civ_affinities[b] { 1.0 } else { 0.0 };

    agent::W_CULTURE * cult
        + agent::W_BELIEF * belief
        + agent::W_OCCUPATION * occ
        + agent::W_AFFINITY * aff
}
```

- [ ] **Step 2: Write failing tests for similarity functions**

In `formation.rs` inline tests:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use crate::pool::AgentPool;

    /// Create a test pool with `n` alive agents using the standard spawn path.
    /// Caller must set cultural values, beliefs, etc. after construction.
    fn test_pool_with_culture(n: usize) -> AgentPool {
        let mut pool = AgentPool::new(n);
        for i in 0..n {
            // Use the existing pool.spawn() with required params — check M50a's
            // test helpers in tests/test_m50a_relationships.rs for the canonical pattern.
            // All cultural/belief/occupation fields default to 0 after spawn.
            pool.spawn(i as u16, i as u8, 0, 25, 0.5, 0.5, 0.5);
        }
        pool
    }

    #[test]
    fn test_cultural_similarity_identical() {
        let mut pool = test_pool_with_culture(2);
        pool.cultural_value_0[0] = 1; pool.cultural_value_1[0] = 2; pool.cultural_value_2[0] = 3;
        pool.cultural_value_0[1] = 1; pool.cultural_value_1[1] = 2; pool.cultural_value_2[1] = 3;
        assert!((cultural_similarity(&pool, 0, 1) - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_cultural_similarity_same_values_different_order() {
        let mut pool = test_pool_with_culture(2);
        pool.cultural_value_0[0] = 1; pool.cultural_value_1[0] = 2; pool.cultural_value_2[0] = 3;
        pool.cultural_value_0[1] = 3; pool.cultural_value_1[1] = 1; pool.cultural_value_2[1] = 2;
        let sim = cultural_similarity(&pool, 0, 1);
        // 3 cross-rank matches: 3 * 0.5 / 3.0 = 0.5
        assert!((sim - 0.5).abs() < 0.001);
    }

    #[test]
    fn test_cultural_similarity_no_overlap() {
        let mut pool = test_pool_with_culture(2);
        pool.cultural_value_0[0] = 1; pool.cultural_value_1[0] = 2; pool.cultural_value_2[0] = 3;
        pool.cultural_value_0[1] = 4; pool.cultural_value_1[1] = 5; pool.cultural_value_2[1] = 6;
        assert!((cultural_similarity(&pool, 0, 1)).abs() < 0.001);
    }

    #[test]
    fn test_cultural_similarity_partial_same_rank() {
        let mut pool = test_pool_with_culture(2);
        pool.cultural_value_0[0] = 1; pool.cultural_value_1[0] = 2; pool.cultural_value_2[0] = 3;
        pool.cultural_value_0[1] = 1; pool.cultural_value_1[1] = 5; pool.cultural_value_2[1] = 3;
        let sim = cultural_similarity(&pool, 0, 1);
        // 2 same-rank matches: 2 * 1.0 / 3.0 = 0.667
        assert!((sim - 2.0 / 3.0).abs() < 0.001);
    }

    #[test]
    fn test_cultural_similarity_no_double_count() {
        let mut pool = test_pool_with_culture(2);
        // A: [1, 1, 2], B: [1, 2, 2] — value 1 matches at rank 0, value 2 matches at rank 2
        pool.cultural_value_0[0] = 1; pool.cultural_value_1[0] = 1; pool.cultural_value_2[0] = 2;
        pool.cultural_value_0[1] = 1; pool.cultural_value_1[1] = 2; pool.cultural_value_2[1] = 2;
        let sim = cultural_similarity(&pool, 0, 1);
        // Rank 0: 1==1 same-rank (1.0). Rank 1: 1!=2, cross-check: 1 in B? B[0]=1 already used → no.
        // Rank 2: 2==2 same-rank (1.0). Total: 2.0/3.0 = 0.667
        assert!((sim - 2.0 / 3.0).abs() < 0.001);
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents formation::tests`
Expected: FAIL — module not found

- [ ] **Step 4: Add module declaration to lib.rs**

```rust
pub mod formation;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents formation::tests`
Expected: PASS

- [ ] **Step 6: Add per-type gate functions**

Add to `formation.rs` after the similarity functions. Each gate is a pure function returning `Option<BondType>` and initial sentiment:

```rust
// ---------------------------------------------------------------------------
// Per-type formation gates
// ---------------------------------------------------------------------------

/// Result of a formation eligibility check.
pub struct FormationCandidate {
    pub bond_type: BondType,
    pub sentiment: i8,
    pub directed: bool,        // true = UpsertDirected (Mentor only)
    pub source_is_first: bool, // for Mentor: true = first agent is mentor
}

/// Check Friend eligibility. Requires shared memory + compatibility threshold.
/// `triadic_boost`: true if pair shares a positive contact (reduces threshold).
pub fn check_friend(
    pool: &AgentPool, a: usize, b: usize, triadic_boost: bool,
) -> Option<FormationCandidate> {
    // Shared memory prerequisite
    if memory::agents_share_memory(pool, a, b).is_none() {
        return None;
    }
    let threshold = if triadic_boost {
        agent::FRIEND_THRESHOLD - agent::TRIADIC_THRESHOLD_REDUCTION
    } else {
        agent::FRIEND_THRESHOLD
    };
    if compatibility_score(pool, a, b) < threshold {
        return None;
    }
    Some(FormationCandidate {
        bond_type: BondType::Friend,
        sentiment: agent::FRIEND_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// Check CoReligionist eligibility. Requires belief match + minority context.
/// `belief_census`: pre-computed HashMap<u8, usize> of belief counts in region.
pub fn check_coreligionist(
    pool: &AgentPool, a: usize, b: usize,
    belief_census: &HashMap<u8, usize>, region_pop: u32,
) -> Option<FormationCandidate> {
    let belief_a = pool.beliefs[a];
    let belief_b = pool.beliefs[b];
    if belief_a != belief_b || belief_a == 0xFF {
        return None;
    }
    // Minority context check
    let count = *belief_census.get(&belief_a).unwrap_or(&0) as f32;
    if count >= region_pop as f32 * agent::MINORITY_THRESHOLD {
        return None; // Not a minority
    }
    Some(FormationCandidate {
        bond_type: BondType::CoReligionist,
        sentiment: agent::CORELIGIONIST_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// Check Rival eligibility. Same occupation + wealth proximity + ambition gate.
pub fn check_rival(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.occupations[a] != pool.occupations[b] {
        return None;
    }
    if (pool.wealth[a] - pool.wealth[b]).abs() >= agent::RIVAL_WEALTH_PROXIMITY {
        return None;
    }
    if pool.ambition[a] < agent::RIVAL_MIN_AMBITION
        && pool.ambition[b] < agent::RIVAL_MIN_AMBITION
    {
        return None;
    }
    if compatibility_score(pool, a, b) < agent::RIVAL_SIMILARITY_FLOOR {
        return None;
    }
    Some(FormationCandidate {
        bond_type: BondType::Rival,
        sentiment: agent::RIVAL_INITIAL_SENTIMENT,
        directed: false,
        source_is_first: false,
    })
}

/// Check Mentor eligibility. Same occupation + age gap. Evaluates both orientations.
/// Returns at most one candidate (the valid direction).
pub fn check_mentor(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.occupations[a] != pool.occupations[b] {
        return None;
    }
    let age_a = pool.ages[a];
    let age_b = pool.ages[b];
    if age_a >= age_b + agent::MENTOR_AGE_GAP {
        // A is mentor, B is apprentice
        Some(FormationCandidate {
            bond_type: BondType::Mentor,
            sentiment: agent::MENTOR_INITIAL_SENTIMENT,
            directed: true,
            source_is_first: true,
        })
    } else if age_b >= age_a + agent::MENTOR_AGE_GAP {
        // B is mentor, A is apprentice
        Some(FormationCandidate {
            bond_type: BondType::Mentor,
            sentiment: agent::MENTOR_INITIAL_SENTIMENT,
            directed: true,
            source_is_first: false,
        })
    } else {
        None // Peers — no mentorship
    }
}

/// Check Grudge eligibility. Shared negative-valence memory + different civ_affinity.
pub fn check_grudge(pool: &AgentPool, a: usize, b: usize) -> Option<FormationCandidate> {
    if pool.civ_affinities[a] == pool.civ_affinities[b] {
        return None;
    }
    if let Some((_, _, int_a, int_b)) = memory::agents_share_memory_with_valence(pool, a, b) {
        if int_a < 0 || int_b < 0 {
            return Some(FormationCandidate {
                bond_type: BondType::Grudge,
                sentiment: agent::GRUDGE_INITIAL_SENTIMENT,
                directed: false,
                source_is_first: false,
            });
        }
    }
    None
}

/// Check ExileBond eligibility. Both away from origin + foreign rule.
pub fn check_exile_bond(
    pool: &AgentPool, a: usize, b: usize, region: &RegionState,
) -> Option<FormationCandidate> {
    // Neutral region — no "foreign rule" concept
    if region.controller_civ == 255 {
        return None;
    }
    // Both must be away from birth region
    let reg = pool.regions[a]; // Same region (co-located scan)
    if pool.origin_regions[a] == reg || pool.origin_regions[b] == reg {
        return None;
    }
    // Both must be under foreign rule
    if region.controller_civ == pool.civ_affinities[a]
        || region.controller_civ == pool.civ_affinities[b]
    {
        return None;
    }
    let base = agent::EXILE_INITIAL_SENTIMENT;
    // Optional boost for shared origin
    let sentiment = if pool.origin_regions[a] == pool.origin_regions[b] {
        base.saturating_add(5) // Small shared-homeland bonus
    } else {
        base
    };
    Some(FormationCandidate {
        bond_type: BondType::ExileBond,
        sentiment,
        directed: false,
        source_is_first: false,
    })
}
```

- [ ] **Step 7: Write unit tests for each gate function**

Add tests to the `tests` module in `formation.rs`. Test each gate with passing and failing inputs. Key cases:
- Friend: shared memory + above threshold → passes. No shared memory → fails. Below threshold → fails.
- CoReligionist: same belief in minority → passes. Same belief in majority → fails. Different belief → fails. BELIEF_NONE → fails.
- Rival: same occ + close wealth + ambitious → passes. Different occ → fails. Wealth gap too large → fails. Neither ambitious → fails.
- Mentor: age gap A>B → A is mentor. Age gap B>A → B is mentor. Peers → fails. Different occ → fails.
- Grudge: negative shared memory + different affinity → passes. Positive memory → fails. Same affinity → fails.
- ExileBond: both away + foreign rule → passes. Controller=255 → fails. One at origin → fails. One matches controller → fails.

- [ ] **Step 8: Run all formation tests**

Run: `cargo nextest run -p chronicler-agents formation`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/formation.rs chronicler-agents/src/lib.rs
git commit -m "feat(m50b): formation engine core — similarity gates and per-type rules"
```

---

## Task 3: Formation Scan Orchestration

**Files:**
- Modify: `chronicler-agents/src/formation.rs` (add scan logic)
- Modify: `chronicler-agents/src/tick.rs` (wire scan at phase 8)

**Context for workers:**
- The formation scan runs as the LAST operation in `tick_agents()` before return (~line 607).
- Region bucketing: `region_index % FORMATION_CADENCE == turn % FORMATION_CADENCE`.
- Agent list per region: collect alive slots, deterministic shuffle via hash-based sort key.
- Hash function: simple multiply + xor-shift mix of `(turn, region_index, agent_id)`. Do NOT use Rust `HashMap` default hasher.
- Pair iteration: `(i, j)` where `i < j` over shuffled list.
- Early rejection cascade order: existing bond → capacity → budget → type gate → expensive checks.
- For symmetric bonds: both sides need capacity. For Mentor (directed): only source side.
- The shuffled list contains slot indices. Use `pool.ids[slot]` for agent IDs in relationship store ops.
- Build per-region `HashMap<u8, usize>` belief census at scan start for CoReligionist minority check.
- Triadic closure: for Friend-eligible pairs, check `shared_positive_contacts(A, C)` — intersect positive-valence, high-sentiment slots. Cap at 1 bonus.
- Formation budgeting: per-agent `MAX_NEW_BONDS_PER_PASS`, per-region `MAX_NEW_BONDS_PER_REGION`.

- [ ] **Step 1: Add deterministic hash mix function**

```rust
/// Deterministic integer hash for scan rotation. Platform-independent.
fn mix_hash(a: u32, b: u32, c: u32) -> u64 {
    let mut h = (a as u64).wrapping_mul(0x9E3779B97F4A7C15);
    h ^= (b as u64).wrapping_mul(0x517CC1B727220A95);
    h ^= (c as u64).wrapping_mul(0x6C62272E07BB0142);
    h ^= h >> 33;
    h = h.wrapping_mul(0xFF51AFD7ED558CCD);
    h ^= h >> 33;
    h
}
```

- [ ] **Step 2: Add triadic closure check**

```rust
/// Check if pair (a, b) shares a positive contact above TRIADIC_MIN_SENTIMENT.
/// Returns true if at least one shared positive contact exists.
fn has_shared_positive_contact(pool: &AgentPool, a: usize, b: usize) -> bool {
    let count_a = pool.rel_count[a] as usize;
    let count_b = pool.rel_count[b] as usize;
    for i in 0..count_a {
        let target_a = pool.rel_target_ids[a][i];
        let bond_a = pool.rel_bond_types[a][i];
        let sent_a = pool.rel_sentiments[a][i];
        if !crate::relationships::is_positive_valence(bond_a) || sent_a < agent::TRIADIC_MIN_SENTIMENT {
            continue;
        }
        for j in 0..count_b {
            if pool.rel_target_ids[b][j] == target_a
                && crate::relationships::is_positive_valence(pool.rel_bond_types[b][j])
                && pool.rel_sentiments[b][j] >= agent::TRIADIC_MIN_SENTIMENT
            {
                return true;
            }
        }
    }
    false
}
```

- [ ] **Step 3: Add belief census builder**

```rust
/// Build per-region belief count map for minority context checks.
fn build_belief_census(pool: &AgentPool, slots: &[usize]) -> HashMap<u8, usize> {
    let mut census = HashMap::new();
    for &slot in slots {
        let b = pool.beliefs[slot];
        if b != 0xFF {
            *census.entry(b).or_insert(0) += 1;
        }
    }
    census
}
```

- [ ] **Step 4: Implement the main formation scan function**

```rust
/// Counters tracking formation activity for a single tick.
#[derive(Default)]
pub struct FormationStats {
    pub bonds_formed: u32,
    pub bonds_evicted: u32,
    pub pairs_evaluated: u32,
    pub pairs_eligible: u32,
}

/// Run the staggered formation scan for one tick.
/// Returns formation stats and a list of (no dissolution events yet — Task 5 adds those).
pub fn formation_scan(
    pool: &mut AgentPool,
    regions: &[RegionState],
    turn: u32,
    alive_slots: &[usize],
) -> FormationStats {
    let mut stats = FormationStats::default();

    // Build alive-slot-by-region index
    let mut region_slots: HashMap<u16, Vec<usize>> = HashMap::new();
    for &slot in alive_slots {
        region_slots.entry(pool.regions[slot]).or_default().push(slot);
    }

    // Pool-wide id→slot map for dissolution checks (belief-divergence needs this)
    let id_to_slot: HashMap<u32, usize> = alive_slots.iter().map(|&s| (pool.ids[s], s)).collect();

    for (region_idx, slots) in &region_slots {
        // Staggered cadence: only scan this region's bucket this tick
        if (*region_idx as u32) % agent::FORMATION_CADENCE != turn % agent::FORMATION_CADENCE {
            continue;
        }

        let region = &regions[*region_idx as usize];
        let belief_census = build_belief_census(pool, slots);
        let region_pop = slots.len() as u32;

        // Deterministic shuffle: sort by hash key
        let mut shuffled: Vec<usize> = slots.clone();
        shuffled.sort_by_key(|&s| mix_hash(turn, *region_idx as u32, pool.ids[s]));

        let mut region_bond_count: u32 = 0;
        let mut agent_bond_count: HashMap<usize, u8> = HashMap::new();

        let n = shuffled.len();
        for i in 0..n {
            if region_bond_count >= agent::MAX_NEW_BONDS_PER_REGION {
                break;
            }
            let a = shuffled[i];
            for j in (i + 1)..n {
                if region_bond_count >= agent::MAX_NEW_BONDS_PER_REGION {
                    break;
                }
                let b = shuffled[j];
                stats.pairs_evaluated += 1;

                // Try each bond type via early rejection cascade
                let candidates = evaluate_pair(pool, a, b, &belief_census, region_pop, region);
                for candidate in candidates {
                    // Budget check
                    let a_count = *agent_bond_count.get(&a).unwrap_or(&0);
                    let b_count = *agent_bond_count.get(&b).unwrap_or(&0);
                    if a_count >= agent::MAX_NEW_BONDS_PER_PASS {
                        continue;
                    }
                    if !candidate.directed && b_count >= agent::MAX_NEW_BONDS_PER_PASS {
                        continue;
                    }

                    stats.pairs_eligible += 1;

                    // Attempt to write the bond using M50a's existing upsert functions
                    let formed = if candidate.directed {
                        let (src, dst) = if candidate.source_is_first { (a, b) } else { (b, a) };
                        crate::relationships::upsert_directed(
                            pool, src, pool.ids[dst],
                            candidate.bond_type as u8, candidate.sentiment, turn as u16,
                        )
                    } else {
                        crate::relationships::upsert_symmetric(
                            pool, a, b,
                            candidate.bond_type as u8, candidate.sentiment, turn as u16,
                        )
                    };

                    if formed {
                        stats.bonds_formed += 1;
                        region_bond_count += 1;
                        *agent_bond_count.entry(a).or_insert(0) += 1;
                        if !candidate.directed {
                            *agent_bond_count.entry(b).or_insert(0) += 1;
                        }
                    }
                }
            }
        }
    }

    stats
}

/// Evaluate a pair for all bond types. Returns eligible candidates.
fn evaluate_pair(
    pool: &AgentPool, a: usize, b: usize,
    belief_census: &HashMap<u8, usize>, region_pop: u32,
    region: &RegionState,
) -> Vec<FormationCandidate> {
    let mut candidates = Vec::new();
    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    // Check each bond type — skip if already exists
    let triadic = has_shared_positive_contact(pool, a, b);

    if crate::relationships::find_relationship(pool, a, b_id, BondType::Friend as u8).is_none() {
        if let Some(c) = check_friend(pool, a, b, triadic) {
            if has_capacity(pool, a, b, false) {
                candidates.push(c);
            }
        }
    }

    if crate::relationships::find_relationship(pool, a, b_id, BondType::CoReligionist as u8).is_none() {
        if let Some(c) = check_coreligionist(pool, a, b, belief_census, region_pop) {
            if has_capacity(pool, a, b, false) {
                candidates.push(c);
            }
        }
    }

    if crate::relationships::find_relationship(pool, a, b_id, BondType::Rival as u8).is_none() {
        if let Some(c) = check_rival(pool, a, b) {
            if has_capacity(pool, a, b, false) {
                candidates.push(c);
            }
        }
    }

    // Mentor: check both orientations
    if crate::relationships::find_relationship(pool, a, b_id, BondType::Mentor as u8).is_none()
        && crate::relationships::find_relationship(pool, b, a_id, BondType::Mentor as u8).is_none()
    {
        if let Some(c) = check_mentor(pool, a, b) {
            let src = if c.source_is_first { a } else { b };
            if has_capacity_directed(pool, src) {
                candidates.push(c);
            }
        }
    }

    if crate::relationships::find_relationship(pool, a, b_id, BondType::Grudge as u8).is_none() {
        if let Some(c) = check_grudge(pool, a, b) {
            if has_capacity(pool, a, b, false) {
                candidates.push(c);
            }
        }
    }

    if crate::relationships::find_relationship(pool, a, b_id, BondType::ExileBond as u8).is_none() {
        if let Some(c) = check_exile_bond(pool, a, b, region) {
            if has_capacity(pool, a, b, false) {
                candidates.push(c);
            }
        }
    }

    candidates
}

/// Check if both agents have capacity for a symmetric bond.
fn has_capacity(pool: &AgentPool, a: usize, b: usize, _directed: bool) -> bool {
    let a_ok = (pool.rel_count[a] as usize) < 8
        || crate::relationships::find_evictable(pool, a).is_some();
    let b_ok = (pool.rel_count[b] as usize) < 8
        || crate::relationships::find_evictable(pool, b).is_some();
    a_ok && b_ok
}

/// Check if source agent has capacity for a directed bond.
fn has_capacity_directed(pool: &AgentPool, src: usize) -> bool {
    (pool.rel_count[src] as usize) < 8
        || crate::relationships::find_evictable(pool, src).is_some()
}

// Bond writing uses M50a's existing functions:
// - crate::relationships::upsert_directed(pool, src, dst_id, bond_type, sentiment, turn) -> bool
// - crate::relationships::upsert_symmetric(pool, a, b, bond_type, sentiment, turn) -> bool
// These handle slot resolution, eviction, atomicity, count management, and formed_turn preservation.
// Do NOT reimplement this logic — use the M50a API directly.
```

- [ ] **Step 5: Wire formation scan into tick.rs**

After the consolidated memory write (~line 605), before the return:

```rust
    // -----------------------------------------------------------------------
    // 8. M50b: Formation scan (staggered cadence)
    // -----------------------------------------------------------------------
    let _formation_stats = crate::formation::formation_scan(pool, regions, turn, &alive_slots);
```

Update the function to accumulate `formation_stats` into the returned counters (or store on a passed-in stats struct).

- [ ] **Step 6: Write integration tests for scan orchestration**

Tests in `chronicler-agents/tests/test_m50b_formation.rs`:
- Staggered scheduling: region 0 scanned on tick 0, 6, 12. Region 1 on tick 1, 7, 13.
- Friend bond forms when agents share memory + culture.
- Formation caps respected: per-agent and per-region.
- Deterministic: same seed → same bonds after N ticks.

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents formation && cargo nextest run -p chronicler-agents test_m50b`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/formation.rs chronicler-agents/src/tick.rs chronicler-agents/tests/test_m50b_formation.rs
git commit -m "feat(m50b): formation scan orchestration with staggered cadence and budgeting"
```

---

## Task 4: Death Cleanup & Belief-Divergence Dissolution

**Files:**
- Modify: `chronicler-agents/src/formation.rs` (add dissolution functions)
- Modify: `chronicler-agents/src/tick.rs` (wire death cleanup at phase 5.1)
- Modify: `chronicler-agents/src/ffi.rs` (dissolution event emission)

**Context for workers:**
- Death cleanup runs EVERY tick, after `pool.kill()` calls (~line 414) and before cultural drift (~line 480).
- Belief-divergence cleanup runs inside the formation scan, before pair evaluation for each region.
- Both use `while i < rel_count` loop (not `for`) due to swap-remove.
- Belief-divergence needs a pool-wide `id_to_slot: HashMap<u32, usize>` to resolve targets (they may have migrated).
- Death cleanup emits dissolution `AgentEvent` (event_type=6) for narration feed.
- Dead agent's own slots don't need cleanup — their row is dead.

- [ ] **Step 1: Add death cleanup function to formation.rs**

```rust
use crate::tick::AgentEvent;

/// Sweep all alive agents' relationship slots, removing bonds to dead agents.
/// Returns dissolution events for narration and count of removed bonds.
pub fn death_cleanup_sweep(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    dead_ids: &std::collections::HashSet<u32>,
    turn: u32,
) -> (Vec<AgentEvent>, u32) {
    let mut events = Vec::new();
    let mut removed = 0u32;

    for &slot in alive_slots {
        let mut i = 0usize;
        while i < pool.rel_count[slot] as usize {
            let target_id = pool.rel_target_ids[slot][i];
            if dead_ids.contains(&target_id) {
                let bond_type = pool.rel_bond_types[slot][i];
                // Emit dissolution event for narration
                events.push(AgentEvent {
                    agent_id: pool.ids[slot],
                    event_type: agent::LIFE_EVENT_DISSOLUTION,
                    region: pool.regions[slot],
                    target_region: bond_type as u16, // Repurpose for bond_type
                    civ_affinity: pool.civ_affinities[slot],
                    occupation: pool.occupations[slot],
                    turn,
                });
                // Use M50a's existing swap-remove helper
                crate::relationships::swap_remove_rel(pool, slot, i);
                removed += 1;
                // Don't increment i — re-check swapped entry
            } else {
                i += 1;
            }
        }
    }

    (events, removed)
}
```

- [ ] **Step 2: Add belief-divergence cleanup to formation scan**

```rust
/// Remove CoReligionist bonds where beliefs have diverged.
/// Called per-region at the start of the formation scan.
pub fn belief_divergence_cleanup(
    pool: &mut AgentPool,
    region_slots: &[usize],
    id_to_slot: &HashMap<u32, usize>,
) -> u32 {
    let mut removed = 0u32;
    for &slot in region_slots {
        let mut i = 0usize;
        while i < pool.rel_count[slot] as usize {
            if pool.rel_bond_types[slot][i] == BondType::CoReligionist as u8 {
                let target_id = pool.rel_target_ids[slot][i];
                if let Some(&target_slot) = id_to_slot.get(&target_id) {
                    if pool.beliefs[slot] != pool.beliefs[target_slot] {
                        crate::relationships::swap_remove_rel(pool, slot, i);
                        removed += 1;
                        continue; // Re-check swapped entry
                    }
                }
            }
            i += 1;
        }
    }
    removed
}
```

- [ ] **Step 3: Wire death cleanup into tick.rs at phase 5.1**

After the demographics sequential-apply block (after births, before cultural drift):

```rust
    // -----------------------------------------------------------------------
    // 5.1 M50b: Death cleanup sweep — remove bonds to this tick's dead agents
    // -----------------------------------------------------------------------
    let dead_ids: std::collections::HashSet<u32> = events.iter()
        .filter(|e| e.event_type == 0) // event_type 0 = death
        .map(|e| e.agent_id)
        .collect();
    if !dead_ids.is_empty() {
        // Rebuild alive_slots after deaths
        let alive_slots_post_demo: Vec<usize> = (0..pool.capacity())
            .filter(|&s| pool.is_alive(s))
            .collect();
        let (dissolution_events, _removed) =
            crate::formation::death_cleanup_sweep(pool, &alive_slots_post_demo, &dead_ids, turn);
        events.extend(dissolution_events);
    }
```

- [ ] **Step 4: Integrate belief-divergence into formation_scan**

In `formation_scan()`, after building `region_slots` and `id_to_slot`, add a call to `belief_divergence_cleanup()` for each region before the pair loop:

```rust
    // Run belief-divergence cleanup before pair evaluation
    let structural_removed = belief_divergence_cleanup(pool, slots, &id_to_slot);
    stats.bonds_dissolved_structural += structural_removed;
```

Update `FormationStats` to include dissolution counters:
```rust
pub struct FormationStats {
    pub bonds_formed: u32,
    pub bonds_evicted: u32,
    pub bonds_dissolved_death: u32,
    pub bonds_dissolved_structural: u32,
    pub pairs_evaluated: u32,
    pub pairs_eligible: u32,
}
```

- [ ] **Step 5: Write unit tests for dissolution**

- Death cleanup: bond to dead target removed, packed-prefix maintained.
- Belief divergence: CoReligionist removed when beliefs differ. Non-CoReligionist unaffected.
- Swap-remove correctness: swapped-in entry re-checked, no entries skipped.

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents formation`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/formation.rs chronicler-agents/src/tick.rs
git commit -m "feat(m50b): death cleanup sweep and belief-divergence dissolution"
```

---

## Task 5: Social-Need Blend

**Files:**
- Modify: `chronicler-agents/src/needs.rs` (~line 115, `social_restoration()`)
- Test: `chronicler-agents/src/needs.rs` (inline tests)

**Context for workers:**
- Current `social_restoration()` is at lines 115-145 in `needs.rs`. It uses population ratio, occupation multiplier, age multiplier.
- M50b adds a blend: `(1 - alpha) * pop_proxy + alpha * bond_factor`.
- Default `SOCIAL_BLEND_ALPHA = 0.0` means zero behavioral change at launch.
- When `alpha == 0.0`, skip the bond scan entirely (early return to existing logic).
- `positive_bond_count` = count of occupied slots with `is_positive_valence(bond_type)` AND `sentiment > 0`.
- `bond_factor = SOCIAL_RESTORE_BOND * (positive_bond_count / SOCIAL_BOND_TARGET).min(1.0) * deficit`

- [ ] **Step 1: Write failing test for blend at alpha=0.0**

```rust
#[test]
fn test_social_restoration_alpha_zero_unchanged() {
    // At alpha=0.0, result should be identical to the existing proxy
    let mut pool = test_pool(1); // helper that creates a pool with one alive agent
    // Set up agent state that produces non-zero proxy value
    pool.occupations[0] = Occupation::Merchant as u8;
    pool.ages[0] = 30;
    pool.need_social[0] = 0.5; // deficit = 0.5
    // Add some relationship slots (should be ignored at alpha=0)
    pool.rel_count[0] = 3;
    pool.rel_bond_types[0][0] = BondType::Friend as u8;
    pool.rel_sentiments[0][0] = 50;
    pool.rel_bond_types[0][1] = BondType::Kin as u8;
    pool.rel_sentiments[0][1] = 60;
    pool.rel_bond_types[0][2] = BondType::Rival as u8; // negative valence
    pool.rel_sentiments[0][2] = -20;

    let mut region = RegionState::new(0);
    region.population = 100;
    region.carrying_capacity = 200;
    let result_with_bonds = social_restoration(&pool, 0, &region);

    // Zero out bonds, compute again
    pool.rel_count[0] = 0;
    let result_without_bonds = social_restoration(&pool, 0, &region);

    // At alpha=0, bonds should not affect the result
    assert!((result_with_bonds - result_without_bonds).abs() < 0.0001);
}
```

- [ ] **Step 2: Run test to verify it passes with current code**

Run: `cargo nextest run -p chronicler-agents test_social_restoration_alpha_zero`
Expected: PASS (existing code ignores bonds)

- [ ] **Step 3: Modify social_restoration() to add blend**

Replace the function body:

```rust
fn social_restoration(pool: &AgentPool, slot: usize, region: &RegionState) -> f32 {
    let alpha = agent::SOCIAL_BLEND_ALPHA;

    // Fast path: alpha == 0 → pure proxy, skip bond scan
    if alpha == 0.0 {
        return social_restoration_proxy(pool, slot, region);
    }

    let proxy = social_restoration_proxy(pool, slot, region);

    // Bond factor: count positive-valence bonds with positive sentiment
    let mut positive_count = 0u32;
    for i in 0..pool.rel_count[slot] as usize {
        if crate::relationships::is_positive_valence(pool.rel_bond_types[slot][i])
            && pool.rel_sentiments[slot][i] > 0
        {
            positive_count += 1;
        }
    }
    let deficit = 1.0 - pool.need_social[slot];
    let bond_factor = agent::SOCIAL_RESTORE_BOND
        * (positive_count as f32 / agent::SOCIAL_BOND_TARGET).min(1.0)
        * deficit;

    (1.0 - alpha) * proxy + alpha * bond_factor
}

/// Original population-ratio proxy (extracted for blend).
fn social_restoration_proxy(pool: &AgentPool, slot: usize, region: &RegionState) -> f32 {
    let pop_ratio = if region.carrying_capacity > 0 {
        (region.population as f32 / region.carrying_capacity as f32).min(1.0)
    } else {
        0.0
    };
    if pop_ratio <= agent::SOCIAL_RESTORE_POP_THRESHOLD {
        return 0.0;
    }
    let base_rate = agent::SOCIAL_RESTORE_POP * pop_ratio;
    let occ = pool.occupations[slot];
    let occ_mult = if occ == Occupation::Merchant as u8 {
        agent::SOCIAL_MERCHANT_MULT
    } else if occ == Occupation::Priest as u8 {
        agent::SOCIAL_PRIEST_MULT
    } else {
        1.0
    };
    let age = pool.ages[slot];
    let age_mult = (age as f32 / 40.0).min(1.0);
    let deficit = 1.0 - pool.need_social[slot];
    base_rate * occ_mult * age_mult * deficit
}
```

- [ ] **Step 4: Run all needs tests**

Run: `cargo nextest run -p chronicler-agents needs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/needs.rs
git commit -m "feat(m50b): social-need blend with alpha=0.0 default"
```

---

## Task 6: Instrumentation & FFI

**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (add `get_relationship_stats()`, `get_all_relationships()`)
- Modify: `chronicler-agents/src/formation.rs` (expose stats)

**Context for workers:**
- `get_relationship_stats()` returns a Python dict with per-tick counters + optional distribution snapshots.
- `get_all_relationships()` returns an Arrow RecordBatch with schema `[agent_id: u32, target_id: u32, sentiment: i8, bond_type: u8, formed_turn: u16]`.
- Counters reset per tick. `kin_bond_failures` is cumulative on `AgentSimulator` — expose the delta.
- Distribution snapshots (mean_rel_count, bond_type_counts, etc.) are computed only when requested.
- Add `formation_stats` field to `AgentSimulator` to store the latest tick's formation stats.
- All metrics use directed-slot semantics.

- [ ] **Step 1: Add formation stats storage to AgentSimulator**

In `ffi.rs` struct:
```rust
    formation_stats: crate::formation::FormationStats,
    prev_kin_bond_failures: u32, // For delta computation
```

- [ ] **Step 2: Wire stats into tick call**

In the tick wrapper method, after calling `tick_agents()`, capture formation stats and update delta tracking.

- [ ] **Step 3: Implement get_relationship_stats()**

```rust
#[pyo3(name = "get_relationship_stats")]
pub fn get_relationship_stats(&self) -> PyResult<HashMap<String, f64>> {
    let mut stats = HashMap::new();
    stats.insert("bonds_formed".into(), self.formation_stats.bonds_formed as f64);
    stats.insert("bonds_dissolved_death".into(), self.formation_stats.bonds_dissolved_death as f64);
    stats.insert("bonds_dissolved_structural".into(), self.formation_stats.bonds_dissolved_structural as f64);
    stats.insert("bonds_evicted".into(), self.formation_stats.bonds_evicted as f64);
    stats.insert("pairs_evaluated".into(), self.formation_stats.pairs_evaluated as f64);
    stats.insert("pairs_eligible".into(), self.formation_stats.pairs_eligible as f64);
    let delta = self.kin_bond_failures.saturating_sub(self.prev_kin_bond_failures);
    stats.insert("kin_bond_failures_delta".into(), delta as f64);
    Ok(stats)
}
```

- [ ] **Step 4: Implement get_all_relationships()**

```rust
#[pyo3(name = "get_all_relationships")]
pub fn get_all_relationships(&self) -> PyResult<PyRecordBatch> {
    let pool = &self.pool;
    let mut agent_ids = UInt32Builder::new();
    let mut target_ids = UInt32Builder::new();
    let mut sentiments = Int8Builder::new();
    let mut bond_types = UInt8Builder::new();
    let mut formed_turns = UInt16Builder::new();

    for slot in 0..pool.capacity() {
        if !pool.is_alive(slot) { continue; }
        let count = pool.rel_count[slot] as usize;
        for i in 0..count {
            agent_ids.append_value(pool.ids[slot]);
            target_ids.append_value(pool.rel_target_ids[slot][i]);
            sentiments.append_value(pool.rel_sentiments[slot][i]);
            bond_types.append_value(pool.rel_bond_types[slot][i]);
            formed_turns.append_value(pool.rel_formed_turns[slot][i]);
        }
    }

    let batch = RecordBatch::try_new(
        Arc::new(arrow::datatypes::Schema::new(vec![
            arrow::datatypes::Field::new("agent_id", arrow::datatypes::DataType::UInt32, false),
            arrow::datatypes::Field::new("target_id", arrow::datatypes::DataType::UInt32, false),
            arrow::datatypes::Field::new("sentiment", arrow::datatypes::DataType::Int8, false),
            arrow::datatypes::Field::new("bond_type", arrow::datatypes::DataType::UInt8, false),
            arrow::datatypes::Field::new("formed_turn", arrow::datatypes::DataType::UInt16, false),
        ])),
        vec![
            Arc::new(agent_ids.finish()),
            Arc::new(target_ids.finish()),
            Arc::new(sentiments.finish()),
            Arc::new(bond_types.finish()),
            Arc::new(formed_turns.finish()),
        ],
    ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

    Ok(PyRecordBatch::new(batch))
}
```

- [ ] **Step 5: Write tests for both FFI methods**

- `get_relationship_stats()` returns expected counters after a tick with formation activity.
- `get_all_relationships()` returns correct schema and row count matching store state.

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents ffi`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/formation.rs
git commit -m "feat(m50b): get_relationship_stats() and get_all_relationships() FFI methods"
```

---

## Task 7: Python Bridge & Simulation Changes

**Files:**
- Modify: `src/chronicler/agent_bridge.py` (~line 402, AgentBridge class)
- Modify: `src/chronicler/simulation.py` (~line 1419, Phase 10 gate)
- Modify: `src/chronicler/main.py` (add `--relationship-stats` flag)
- Test: `tests/test_m50b_formation.py`

**Context for workers:**
- `AgentBridge` class is at line 402 in `agent_bridge.py`. Add `rust_owns_formation: bool` attribute.
- `form_and_sync_relationships()` is called at simulation.py line 1419. Gate with `not agent_bridge.rust_owns_formation`.
- Dissolution events (event_type=6) need to be collected and fed into `world.dissolved_edges_by_turn`.
- `agent_bonds` sync already happens in the per-GP loop alongside memory and needs.
- `--relationship-stats` flag enables per-tick distribution snapshots in `get_relationship_stats()`.

- [ ] **Step 1: Add rust_owns_formation flag to AgentBridge**

In `agent_bridge.py`, in `__init__`:
```python
self.rust_owns_formation = True  # M50b: Rust owns formation in agent modes
```

- [ ] **Step 2: Gate off form_and_sync_relationships in simulation.py**

At ~line 1400:
```python
    if agent_bridge is not None and not agent_bridge.rust_owns_formation:
        from chronicler.relationships import form_and_sync_relationships, compute_belief_data, REL_RIVAL
        # ... existing M40 formation code ...
```

- [ ] **Step 3: Collect dissolution events from tick**

In the tick event processing loop in `agent_bridge.py`, add handling for event_type=6:
```python
elif event_type == 6:  # Dissolution
    # target_region field repurposed as bond_type
    bond_type = event.target_region
    dissolved_key = world.turn
    if dissolved_key not in world.dissolved_edges_by_turn:
        world.dissolved_edges_by_turn[dissolved_key] = []
    world.dissolved_edges_by_turn[dissolved_key].append(
        (event.agent_id, 0, bond_type, world.turn)  # 0 = unknown target (one-sided event)
    )
```

- [ ] **Step 4: Add --relationship-stats CLI flag**

In `main.py` argument parser:
```python
parser.add_argument("--relationship-stats", action="store_true",
                    help="Enable per-tick relationship distribution snapshots")
```

- [ ] **Step 5: Write Python integration tests**

In `tests/test_m50b_formation.py`:
- Test that `rust_owns_formation=True` gates off `form_and_sync_relationships()`.
- Test that `rust_owns_formation=False` allows legacy path.
- Test dissolution event collection populates `dissolved_edges_by_turn`.
- Test `get_relationship_stats()` returns expected keys.
- Test determinism: same seed → identical relationship store.

- [ ] **Step 6: Run Python tests**

Run: `pytest tests/test_m50b_formation.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/simulation.py src/chronicler/main.py tests/test_m50b_formation.py
git commit -m "feat(m50b): rust_owns_formation gate, dissolution events, --relationship-stats flag"
```

---

## Task 8: Narration & Analytics

**Files:**
- Modify: `src/chronicler/narrative.py` (~line 361, context assembly)
- Modify: `src/chronicler/analytics.py` (add extractor)
- Test: `tests/test_m50b_formation.py` (additional tests)

**Context for workers:**
- `build_agent_context_for_moment()` at ~line 270 assembles `AgentContext.relationships` from `social_edges`.
- `rel_type_names` at ~line 361 maps M40 type IDs → names. Add Kin=5, Friend=6, Grudge=7.
- When `rust_owns_formation` is true, source relationships from `gp.agent_bonds` instead of `social_edges`.
- Filter: only narrate bonds where `name_map.get(target_id)` returns a name. Skip unnamed targets entirely.
- Add sentiment descriptors: "deep" (>80), "strong" (>40), "mild" (>0), "fading" (==0).
- `extract_relationship_metrics()` follows the same pattern as `extract_stockpiles()` in `analytics.py`.

- [ ] **Step 1: Widen rel_type_names in narrative.py**

At ~line 361:
```python
    rel_type_names = {
        0: "mentor", 1: "rival", 2: "marriage", 3: "exile_bond", 4: "co_religionist",
        5: "kin", 6: "friend", 7: "grudge",
    }
```

- [ ] **Step 2: Add source swap and filter tightening**

In the context assembly section, replace the `social_edges` source with `gp.agent_bonds` when available:

```python
    # M50b: Source swap — prefer agent_bonds from Rust store when available
    if hasattr(chars[0], 'agent_bonds') if chars else False:
        # Build relationships from all named characters' agent_bonds
        for c in chars:
            gp = gp_map.get(c["name"]) if gp_map else None
            if gp and gp.agent_bonds:
                for bond in gp.agent_bonds:
                    target_name = name_map.get(bond["target_id"])
                    if target_name is None:
                        continue  # Skip unnamed targets
                    sentiment = bond.get("sentiment", 0)
                    sent_desc = (
                        "deep" if abs(sentiment) > 80 else
                        "strong" if abs(sentiment) > 40 else
                        "mild" if abs(sentiment) > 0 else
                        "fading"
                    )
                    relationships.append({
                        "type": rel_type_names.get(bond["bond_type"], "unknown"),
                        "character_a": c["name"],
                        "character_b": target_name,
                        "sentiment": sent_desc,
                        "formed_turn": bond.get("formed_turn", 0),
                    })
    else:
        # Legacy M40 path
        all_edges = list(social_edges or []) + list(dissolved_edges or [])
        # ... existing code ...
```

- [ ] **Step 3: Add extract_relationship_metrics() to analytics.py**

```python
def extract_relationship_metrics(bundles: list[dict], checkpoints=None) -> dict:
    """Extract per-turn relationship formation/dissolution metrics."""
    metrics = {
        "bonds_formed_per_turn": [],
        "bonds_dissolved_per_turn": [],
        "mean_rel_count_per_turn": [],
    }
    for bundle in bundles:
        metadata = bundle.get("metadata", {})
        # Relationship stats are stored per-turn in metadata if --relationship-stats was enabled
        rel_stats = metadata.get("relationship_stats", [])
        for turn_stats in rel_stats:
            metrics["bonds_formed_per_turn"].append(turn_stats.get("bonds_formed", 0))
            metrics["bonds_dissolved_per_turn"].append(
                turn_stats.get("bonds_dissolved_death", 0)
                + turn_stats.get("bonds_dissolved_structural", 0)
            )
            metrics["mean_rel_count_per_turn"].append(turn_stats.get("mean_rel_count", 0))
    return metrics
```

- [ ] **Step 4: Write tests for narration and analytics**

- Test narration context includes Kin/Friend/Grudge types for named characters.
- Test unnamed targets are filtered out.
- Test sentiment descriptors render correctly.
- Test analytics extractor produces expected structure.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_m50b_formation.py tests/test_narrative.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/narrative.py src/chronicler/analytics.py tests/test_m50b_formation.py
git commit -m "feat(m50b): narration widening for new bond types, sentiment descriptors, analytics extractor"
```

---

## Verification Checklist

After all tasks complete:

- [ ] `cargo nextest run -p chronicler-agents` — all Rust tests pass
- [ ] `pytest tests/` — all Python tests pass
- [ ] `--agents=off` mode: no behavioral change (no agent bridge, no formation)
- [ ] `--agents=hybrid` mode: Rust formation active, Python `form_and_sync_relationships()` gated off
- [ ] Same seed determinism: two runs with identical seed produce identical relationship stores
- [ ] `get_all_relationships()` returns valid Arrow batch with correct schema
- [ ] `get_relationship_stats()` returns all expected counters
- [ ] Narration includes Kin/Friend/Grudge for named-character pairs
- [ ] Dissolved-edge events populate `world.dissolved_edges_by_turn`
- [ ] Social-need blend at alpha=0.0: behavior identical to pre-M50b

---

## Task Dependencies

```
Task 1 (constants, helpers)
  ├── Task 2 (formation gates) ── Task 3 (scan orchestration) ── Task 4 (dissolution)
  ├── Task 5 (social blend) [parallel with Task 2-4]
  └── Task 6 (instrumentation) [after Task 3-4]
       ├── Task 7 (Python bridge) [after Task 6]
       └── Task 8 (narration + analytics) [after Task 7]
```

Tasks 2-4 are sequential (each builds on the prior). Task 5 is independent and can run in parallel with Tasks 2-4. Tasks 6-8 are sequential after the Rust core is complete.

---

## Known Plan Issues (Fix During Implementation)

These wiring issues were identified during review. Implementers must fix them against the actual codebase rather than following the plan's code literally.

1. **Formation scan uses stale alive_slots.** Task 3 passes the tick-start `alive_slots` to `formation_scan()`. Must use `alive_slots_post_demo` (rebuilt after demographics) so the scan skips dead agents and includes newborns.

2. **Dissolved-edge events missing target_id.** Task 4's death cleanup emits `AgentEvent` with target=0 (unknown). The narration pipeline needs both endpoint IDs. Fix: add `target_agent_id: u32` field to `AgentEvent`, populate with the dead agent's ID during death cleanup. Python collects both endpoints for `dissolved_edges_by_turn`.

3. **Narration source swap references wrong scope.** Task 8 Step 2 checks `hasattr(chars[0], 'agent_bonds')` but `chars` is a list of dicts, not GreatPerson objects. The correct seam is `_prepare_narration_prompts()` where `gp_by_agent_id` is available, or thread `gp_by_agent_id` into `build_agent_context_for_moment()`.

4. **`AgentPool::spawn()` signature varies across milestones.** Task 1/2 test helpers guess the spawn signature. Before writing tests, read the actual M50a `pool.rs` `spawn()` signature and copy the test helper pattern from `tests/test_m50a_relationships.py`.

5. **Distribution snapshots not implemented.** Task 6's `get_relationship_stats()` returns flat counters but does not compute the 4 distribution metrics from spec Section 8.2 (`mean_rel_count`, `mean_positive_sentiment`, `bond_type_counts`, `cross_civ_bond_fraction`). Add a second code path gated by a `compute_distributions: bool` parameter, scanning alive agents' relationship slots.

6. **Transient signal test missing.** CLAUDE.md requires 2+ turn integration tests verifying per-scan counters reset between cadence ticks. Add to Task 3 integration tests.
