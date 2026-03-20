# M50a: Relationship Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Rust-owned per-agent relationship store with directed sentiment drift and protected kin bonds, making M40's named-character social graph a projection over the new store.

**Architecture:** New `relationships.rs` module owns SoA storage (8 slots/agent, 65 bytes), BondType enum (values 0-4 matching M40 for zero-translation), helpers (find/read/write/evict), upsert/remove with atomicity, and sentiment drift. Kin bonds auto-form at birth in `tick.rs`. M40 compatibility via projection (`get_social_edges`) and shim (`replace_social_edges`). Python-side changes are minimal — existing formation logic works through the shim.

**Tech Stack:** Rust (SoA on AgentPool, PyO3 Arrow FFI), Python (agent_bridge, models)

**Spec:** `docs/superpowers/specs/2026-03-20-m50a-relationship-substrate-design.md`

**Subagent dispatch checklist (from CLAUDE.md):**
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially sentiment i8/i16 widening.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.
8. Post-implementation self-review: read every modified file end-to-end, verify all cross-file data flow.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `chronicler-agents/src/relationships.rs` | **Create** | BondType enum, classification helpers, slot ops, upsert/remove, eviction, kin formation, drift |
| `chronicler-agents/src/pool.rs` | Modify (lines 52-66, 142-226) | Add 5 SoA relationship fields, init in both spawn branches |
| `chronicler-agents/src/agent.rs` | Modify (lines 82-96, 215-262) | Constants block, RNG stream offset 1100 |
| `chronicler-agents/src/tick.rs` | Modify (lines 83-91, 417-432) | Drift phase 0.8 call, kin formation in birth loop |
| `chronicler-agents/src/ffi.rs` | Modify (lines 716-822) | `apply_relationship_ops`, `get_agent_relationships`, reimplement `get_social_edges`, `replace_social_edges` shim |
| `chronicler-agents/src/lib.rs` | Modify (line 22) | Add `pub mod relationships;` |
| `chronicler-agents/src/social.rs` | Modify (lines 4-42) | Deprecation comment on `SocialGraph` |
| `chronicler-agents/tests/test_relationships.rs` | **Create** | Rust integration tests |
| `src/chronicler/models.py` | Modify (GreatPerson class) | Add `agent_bonds` field |
| `src/chronicler/agent_bridge.py` | Modify (lines 504-521, 1120-1152) | `apply_relationship_ops` wrapper, `agent_bonds` sync |
| `tests/test_m50a_relationships.py` | **Create** | Python integration tests |

---

### Task 1: BondType Enum, Classification Helpers, and Module Skeleton

**Files:**
- Create: `chronicler-agents/src/relationships.rs`
- Modify: `chronicler-agents/src/lib.rs:22`

- [ ] **Step 1: Create `relationships.rs` with BondType enum and helpers**

```rust
// chronicler-agents/src/relationships.rs

use crate::pool::AgentPool;

/// Bond types. Values 0-4 match M40 RelationshipType for zero-translation compatibility.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BondType {
    Mentor        = 0,
    Rival         = 1,
    Marriage      = 2,
    ExileBond     = 3,
    CoReligionist = 4,
    Kin           = 5,
    Friend        = 6,
    Grudge        = 7,
}

impl BondType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Mentor),
            1 => Some(Self::Rival),
            2 => Some(Self::Marriage),
            3 => Some(Self::ExileBond),
            4 => Some(Self::CoReligionist),
            5 => Some(Self::Kin),
            6 => Some(Self::Friend),
            7 => Some(Self::Grudge),
            _ => None,
        }
    }
}

pub const REL_SLOTS: usize = 8;
pub const EMPTY_TARGET: u32 = 0;
pub const EMPTY_BOND_TYPE: u8 = 255;

/// Kin bonds are eviction-protected. Marriage joins in M57.
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8
}

/// Positive-valence bonds strengthen when co-located.
/// Negative-valence bonds (Rival, Grudge) deepen when co-located.
pub fn is_positive_valence(bond_type: u8) -> bool {
    matches!(bond_type, 0 | 2 | 3 | 4 | 5 | 6)
}

/// Only Mentor is asymmetric (single directed entry, src=mentor dst=apprentice).
pub fn is_asymmetric(bond_type: u8) -> bool {
    bond_type == BondType::Mentor as u8
}

pub fn is_symmetric(bond_type: u8) -> bool {
    !is_asymmetric(bond_type)
}
```

- [ ] **Step 2: Register module in lib.rs**

Add `pub mod relationships;` after `pub mod needs;` (line 22) in `chronicler-agents/src/lib.rs`.

- [ ] **Step 3: Write unit tests for classification helpers**

At the bottom of `relationships.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bond_type_from_u8() {
        assert_eq!(BondType::from_u8(0), Some(BondType::Mentor));
        assert_eq!(BondType::from_u8(5), Some(BondType::Kin));
        assert_eq!(BondType::from_u8(7), Some(BondType::Grudge));
        assert_eq!(BondType::from_u8(8), None);
        assert_eq!(BondType::from_u8(255), None);
    }

    #[test]
    fn test_is_protected() {
        assert!(is_protected(BondType::Kin as u8));
        assert!(!is_protected(BondType::Mentor as u8));
        assert!(!is_protected(BondType::Rival as u8));
        assert!(!is_protected(BondType::Friend as u8));
    }

    #[test]
    fn test_valence() {
        // Positive-valence
        assert!(is_positive_valence(BondType::Kin as u8));
        assert!(is_positive_valence(BondType::Mentor as u8));
        assert!(is_positive_valence(BondType::Friend as u8));
        assert!(is_positive_valence(BondType::CoReligionist as u8));
        assert!(is_positive_valence(BondType::Marriage as u8));
        assert!(is_positive_valence(BondType::ExileBond as u8));
        // Negative-valence
        assert!(!is_positive_valence(BondType::Rival as u8));
        assert!(!is_positive_valence(BondType::Grudge as u8));
    }

    #[test]
    fn test_asymmetry() {
        assert!(is_asymmetric(BondType::Mentor as u8));
        assert!(!is_asymmetric(BondType::Kin as u8));
        assert!(!is_asymmetric(BondType::Rival as u8));
        assert!(is_symmetric(BondType::Kin as u8));
        assert!(is_symmetric(BondType::Rival as u8));
    }

    #[test]
    fn test_m40_value_compatibility() {
        // Values 0-4 must match M40 RelationshipType exactly
        assert_eq!(BondType::Mentor as u8, 0);
        assert_eq!(BondType::Rival as u8, 1);
        assert_eq!(BondType::Marriage as u8, 2);
        assert_eq!(BondType::ExileBond as u8, 3);
        assert_eq!(BondType::CoReligionist as u8, 4);
    }
}
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo nextest run relationships`
Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/relationships.rs chronicler-agents/src/lib.rs
git commit -m "feat(m50a): BondType enum, classification helpers, module skeleton"
```

---

### Task 2: SoA Storage Fields on AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs:52-66` (field declarations)
- Modify: `chronicler-agents/src/pool.rs:142-183` (spawn free-list branch)
- Modify: `chronicler-agents/src/pool.rs:184-226` (spawn grow branch)

- [ ] **Step 1: Add SoA field declarations**

After the M49 needs fields (line 66), add:

```rust
    // M50a: Per-agent relationship store (8 slots)
    pub rel_target_ids:   Vec<[u32; 8]>,
    pub rel_sentiments:   Vec<[i8; 8]>,
    pub rel_bond_types:   Vec<[u8; 8]>,
    pub rel_formed_turns: Vec<[u16; 8]>,
    pub rel_count:        Vec<u8>,
```

- [ ] **Step 2: Initialize in the `new()` constructor**

In `AgentPool::new()`, add to the field initialization list (after needs fields). Use `with_capacity` to match the existing pattern:

```rust
            rel_target_ids: Vec::with_capacity(capacity),
            rel_sentiments: Vec::with_capacity(capacity),
            rel_bond_types: Vec::with_capacity(capacity),
            rel_formed_turns: Vec::with_capacity(capacity),
            rel_count: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Initialize in spawn — free-list reuse branch**

In the free-list reuse branch (after needs init ~line 180), add:

```rust
            // M50a relationship init
            self.rel_target_ids[slot] = [0u32; 8];
            self.rel_sentiments[slot] = [0i8; 8];
            self.rel_bond_types[slot] = [255u8; 8]; // 255 = empty sentinel (not 0, since Kin=5)
            self.rel_formed_turns[slot] = [0u16; 8];
            self.rel_count[slot] = 0;
```

- [ ] **Step 4: Initialize in spawn — vector grow branch**

In the vector grow branch (after needs init ~line 222), add:

```rust
            // M50a relationship init
            self.rel_target_ids.push([0u32; 8]);
            self.rel_sentiments.push([0i8; 8]);
            self.rel_bond_types.push([255u8; 8]);
            self.rel_formed_turns.push([0u16; 8]);
            self.rel_count.push(0);
```

- [ ] **Step 5: Add `find_slot_by_id` helper on AgentPool**

Add after the existing pool methods:

```rust
    /// Linear scan to find the slot index for a given agent_id.
    /// Returns None if not found or not alive.
    pub fn find_slot_by_id(&self, agent_id: u32) -> Option<usize> {
        if agent_id == 0 { return None; } // PARENT_NONE sentinel
        for slot in 0..self.capacity() {
            if self.alive[slot] && self.ids[slot] == agent_id {
                return Some(slot);
            }
        }
        None
    }
```

- [ ] **Step 6: Run full Rust test suite**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All existing tests pass (no behavioral change, just new empty fields).

- [ ] **Step 7: Commit**

```
git add chronicler-agents/src/pool.rs
git commit -m "feat(m50a): SoA relationship fields on AgentPool with spawn init"
```

---

### Task 3: Slot Helpers and Eviction Logic

**Files:**
- Modify: `chronicler-agents/src/relationships.rs`

- [ ] **Step 1: Add slot helper functions**

```rust
/// Find a relationship slot by compound key (target_id, bond_type).
/// Searches slots [0..rel_count) for the given agent.
pub fn find_relationship(pool: &AgentPool, slot: usize, target_id: u32, bond_type: u8) -> Option<usize> {
    let count = pool.rel_count[slot] as usize;
    for i in 0..count {
        if pool.rel_target_ids[slot][i] == target_id && pool.rel_bond_types[slot][i] == bond_type {
            return Some(i);
        }
    }
    None
}

/// Read one relationship slot. Returns (target_id, sentiment, bond_type, formed_turn).
pub fn read_rel(pool: &AgentPool, slot: usize, rel_idx: usize) -> (u32, i8, u8, u16) {
    (
        pool.rel_target_ids[slot][rel_idx],
        pool.rel_sentiments[slot][rel_idx],
        pool.rel_bond_types[slot][rel_idx],
        pool.rel_formed_turns[slot][rel_idx],
    )
}

/// Write one relationship slot.
pub fn write_rel(
    pool: &mut AgentPool, slot: usize, rel_idx: usize,
    target_id: u32, sentiment: i8, bond_type: u8, formed_turn: u16,
) {
    pool.rel_target_ids[slot][rel_idx] = target_id;
    pool.rel_sentiments[slot][rel_idx] = sentiment;
    pool.rel_bond_types[slot][rel_idx] = bond_type;
    pool.rel_formed_turns[slot][rel_idx] = formed_turn;
}

/// Clear a slot to sentinel values.
fn clear_slot(pool: &mut AgentPool, slot: usize, rel_idx: usize) {
    pool.rel_target_ids[slot][rel_idx] = EMPTY_TARGET;
    pool.rel_sentiments[slot][rel_idx] = 0;
    pool.rel_bond_types[slot][rel_idx] = EMPTY_BOND_TYPE;
    pool.rel_formed_turns[slot][rel_idx] = 0;
}

/// Swap-remove: move last occupied slot into the removed position, clear tail, decrement count.
pub fn swap_remove_rel(pool: &mut AgentPool, slot: usize, rel_idx: usize) {
    let count = pool.rel_count[slot] as usize;
    debug_assert!(rel_idx < count);
    let last = count - 1;
    if rel_idx != last {
        // Copy last slot into the removed position
        pool.rel_target_ids[slot][rel_idx] = pool.rel_target_ids[slot][last];
        pool.rel_sentiments[slot][rel_idx] = pool.rel_sentiments[slot][last];
        pool.rel_bond_types[slot][rel_idx] = pool.rel_bond_types[slot][last];
        pool.rel_formed_turns[slot][rel_idx] = pool.rel_formed_turns[slot][last];
    }
    // Clear the old tail slot for hygiene
    clear_slot(pool, slot, last);
    pool.rel_count[slot] -= 1;
}

/// Find the weakest non-protected slot for eviction.
/// Returns None if all occupied slots are protected.
/// Tie-break: lowest slot index among equal-sentiment candidates.
pub fn find_evictable(pool: &AgentPool, slot: usize) -> Option<usize> {
    let count = pool.rel_count[slot] as usize;
    let mut best: Option<(usize, u8)> = None; // (rel_idx, abs_sentiment as u8)
    for i in 0..count {
        let bt = pool.rel_bond_types[slot][i];
        if is_protected(bt) {
            continue;
        }
        let abs_sent = pool.rel_sentiments[slot][i].unsigned_abs(); // u8
        match best {
            None => best = Some((i, abs_sent)),
            Some((_, best_abs)) if abs_sent < best_abs => {
                best = Some((i, abs_sent));
            }
            _ => {} // tie-break: keep lower index (already stored)
        }
    }
    best.map(|(idx, _)| idx)
}
```

Note: `find_evictable` uses `unsigned_abs()` → `u8`, then compares. The lowest `u8` value wins. On ties, the lowest slot index wins (because we only replace on strict `<`).

- [ ] **Step 2: Write unit tests for slot helpers**

```rust
    #[test]
    fn test_find_relationship() {
        let mut pool = create_test_pool(1); // helper from existing test utils
        let slot = spawn_test_agent(&mut pool, 0, 0);
        // Write a bond manually
        pool.rel_target_ids[slot][0] = 42;
        pool.rel_bond_types[slot][0] = BondType::Friend as u8;
        pool.rel_sentiments[slot][0] = 50;
        pool.rel_formed_turns[slot][0] = 10;
        pool.rel_count[slot] = 1;

        assert_eq!(find_relationship(&pool, slot, 42, BondType::Friend as u8), Some(0));
        assert_eq!(find_relationship(&pool, slot, 42, BondType::Rival as u8), None);
        assert_eq!(find_relationship(&pool, slot, 99, BondType::Friend as u8), None);
    }

    #[test]
    fn test_swap_remove_compaction() {
        let mut pool = create_test_pool(1);
        let slot = spawn_test_agent(&mut pool, 0, 0);
        // Write 3 bonds
        for i in 0..3u32 {
            write_rel(&mut pool, slot, i as usize, 10 + i, (i as i8) * 10, BondType::Friend as u8, 1);
        }
        pool.rel_count[slot] = 3;

        // Remove middle bond (idx 1)
        swap_remove_rel(&mut pool, slot, 1);

        assert_eq!(pool.rel_count[slot], 2);
        // Last bond (target_id=12) moved to idx 1
        assert_eq!(pool.rel_target_ids[slot][1], 12);
        // Old tail (idx 2) cleared to sentinel
        assert_eq!(pool.rel_bond_types[slot][2], EMPTY_BOND_TYPE);
        assert_eq!(pool.rel_target_ids[slot][2], EMPTY_TARGET);
    }

    #[test]
    fn test_find_evictable_skips_protected() {
        let mut pool = create_test_pool(1);
        let slot = spawn_test_agent(&mut pool, 0, 0);
        // Slot 0: Kin (protected), sentiment 10
        write_rel(&mut pool, slot, 0, 100, 10, BondType::Kin as u8, 1);
        // Slot 1: Friend (unprotected), sentiment 50
        write_rel(&mut pool, slot, 1, 101, 50, BondType::Friend as u8, 1);
        // Slot 2: Rival (unprotected), sentiment -30
        write_rel(&mut pool, slot, 2, 102, -30, BondType::Rival as u8, 1);
        pool.rel_count[slot] = 3;

        // Should evict Rival (abs 30 < abs 50), skipping Kin
        assert_eq!(find_evictable(&pool, slot), Some(2));
    }

    #[test]
    fn test_find_evictable_all_protected() {
        let mut pool = create_test_pool(1);
        let slot = spawn_test_agent(&mut pool, 0, 0);
        for i in 0..8 {
            write_rel(&mut pool, slot, i, (100 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[slot] = 8;

        assert_eq!(find_evictable(&pool, slot), None);
    }

    #[test]
    fn test_find_evictable_tiebreak_lowest_index() {
        let mut pool = create_test_pool(1);
        let slot = spawn_test_agent(&mut pool, 0, 0);
        // Two friends with identical sentiment
        write_rel(&mut pool, slot, 0, 100, 20, BondType::Friend as u8, 1);
        write_rel(&mut pool, slot, 1, 101, 20, BondType::Friend as u8, 1);
        pool.rel_count[slot] = 2;

        assert_eq!(find_evictable(&pool, slot), Some(0)); // lowest index wins
    }
```

Note: The tests above reference `create_test_pool` and `spawn_test_agent` — these are existing test helpers in the Rust crate. **Before writing tests, verify these helpers exist** by grepping `chronicler-agents/tests/` and `chronicler-agents/src/` for `create_test_pool` or the equivalent constructor pattern. If they don't exist as standalone helpers, create minimal versions or use the pool directly. **Do not use struct literals for RegionState** — use the existing constructor functions.

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run relationships`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```
git add chronicler-agents/src/relationships.rs
git commit -m "feat(m50a): slot helpers (find/read/write/evict) with swap-remove compaction"
```

---

### Task 4: Upsert and Remove Operations

**Files:**
- Modify: `chronicler-agents/src/relationships.rs`

- [ ] **Step 1: Implement `upsert_directed`**

```rust
/// Result of a slot resolution attempt.
enum SlotResolution {
    ExistingSlot(usize),        // bond already exists at this index
    EmptySlot(usize),           // empty slot available at this index
    EvictSlot(usize),           // non-protected slot to evict at this index
    NoSlot,                     // all 8 protected, cannot admit
}

fn resolve_slot(pool: &AgentPool, agent_slot: usize, target_id: u32, bond_type: u8) -> SlotResolution {
    // Check for existing bond
    if let Some(idx) = find_relationship(pool, agent_slot, target_id, bond_type) {
        return SlotResolution::ExistingSlot(idx);
    }
    // Check for empty slot
    let count = pool.rel_count[agent_slot] as usize;
    if count < REL_SLOTS {
        return SlotResolution::EmptySlot(count);
    }
    // Check for evictable slot
    if let Some(idx) = find_evictable(pool, agent_slot) {
        return SlotResolution::EvictSlot(idx);
    }
    SlotResolution::NoSlot
}

/// Insert or update a directed bond from src_slot to target_id.
/// Returns true if the bond was written, false if rejected.
pub fn upsert_directed(
    pool: &mut AgentPool, src_slot: usize,
    target_id: u32, bond_type: u8, sentiment: i8, formed_turn: u16,
) -> bool {
    // Self-bond check
    if pool.ids[src_slot] == target_id { return false; }

    match resolve_slot(pool, src_slot, target_id, bond_type) {
        SlotResolution::ExistingSlot(idx) => {
            // Update sentiment only; preserve formed_turn
            pool.rel_sentiments[src_slot][idx] = sentiment;
            true
        }
        SlotResolution::EmptySlot(idx) => {
            write_rel(pool, src_slot, idx, target_id, sentiment, bond_type, formed_turn);
            pool.rel_count[src_slot] += 1;
            true
        }
        SlotResolution::EvictSlot(idx) => {
            // find_evictable guarantees the candidate is non-protected
            write_rel(pool, src_slot, idx, target_id, sentiment, bond_type, formed_turn);
            true
        }
        SlotResolution::NoSlot => false,
    }
}

/// Atomically insert a symmetric bond (both directions).
/// Returns true if both sides were written, false if either failed.
pub fn upsert_symmetric(
    pool: &mut AgentPool, slot_a: usize, slot_b: usize,
    bond_type: u8, sentiment: i8, formed_turn: u16,
) -> bool {
    let id_a = pool.ids[slot_a];
    let id_b = pool.ids[slot_b];
    if id_a == id_b { return false; }

    // Resolve both sides BEFORE committing either
    let res_a = resolve_slot(pool, slot_a, id_b, bond_type);
    let res_b = resolve_slot(pool, slot_b, id_a, bond_type);

    // Check both sides can admit
    let can_a = !matches!(res_a, SlotResolution::NoSlot);
    let can_b = !matches!(res_b, SlotResolution::NoSlot);
    if !can_a || !can_b { return false; }

    // Commit both
    commit_resolved(pool, slot_a, id_b, bond_type, sentiment, formed_turn, res_a);
    commit_resolved(pool, slot_b, id_a, bond_type, sentiment, formed_turn, res_b);
    true
}

fn commit_resolved(
    pool: &mut AgentPool, slot: usize,
    target_id: u32, bond_type: u8, sentiment: i8, formed_turn: u16,
    resolution: SlotResolution,
) {
    match resolution {
        SlotResolution::ExistingSlot(idx) => {
            pool.rel_sentiments[slot][idx] = sentiment;
        }
        SlotResolution::EmptySlot(idx) => {
            write_rel(pool, slot, idx, target_id, sentiment, bond_type, formed_turn);
            pool.rel_count[slot] += 1;
        }
        SlotResolution::EvictSlot(idx) => {
            write_rel(pool, slot, idx, target_id, sentiment, bond_type, formed_turn);
        }
        SlotResolution::NoSlot => unreachable!("checked before commit"),
    }
}

/// Remove a directed bond. Returns true if found and removed.
pub fn remove_directed(pool: &mut AgentPool, src_slot: usize, target_id: u32, bond_type: u8) -> bool {
    if let Some(idx) = find_relationship(pool, src_slot, target_id, bond_type) {
        swap_remove_rel(pool, src_slot, idx);
        true
    } else {
        false
    }
}

/// Remove a symmetric bond (both directions independently).
pub fn remove_symmetric(pool: &mut AgentPool, slot_a: usize, slot_b: usize, bond_type: u8) {
    let id_a = pool.ids[slot_a];
    let id_b = pool.ids[slot_b];
    remove_directed(pool, slot_a, id_b, bond_type);
    remove_directed(pool, slot_b, id_a, bond_type);
}
```

- [ ] **Step 2: Write tests for upsert/remove operations**

```rust
    #[test]
    fn test_upsert_directed_new_bond() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        assert!(upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10));
        assert_eq!(pool.rel_count[a], 1);
        let (tid, sent, bt, ft) = read_rel(&pool, a, 0);
        assert_eq!(tid, id_b);
        assert_eq!(sent, 50);
        assert_eq!(bt, BondType::Friend as u8);
        assert_eq!(ft, 10);
    }

    #[test]
    fn test_upsert_directed_preserves_formed_turn() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10);
        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 80, 99);
        // Sentiment updated, formed_turn preserved
        assert_eq!(pool.rel_sentiments[a][0], 80);
        assert_eq!(pool.rel_formed_turns[a][0], 10); // NOT 99
    }

    #[test]
    fn test_upsert_directed_self_bond_rejected() {
        let mut pool = create_test_pool(1);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let id_a = pool.ids[a];

        assert!(!upsert_directed(&mut pool, a, id_a, BondType::Friend as u8, 50, 10));
        assert_eq!(pool.rel_count[a], 0);
    }

    #[test]
    fn test_upsert_symmetric_atomic_failure() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        // Fill agent a with 8 protected kin bonds
        for i in 0..8 {
            write_rel(&mut pool, a, i, (100 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[a] = 8;

        // Symmetric upsert should fail — a has no admissible slot
        assert!(!upsert_symmetric(&mut pool, a, b, BondType::Friend as u8, 50, 10));
        // Neither side should have the bond
        assert_eq!(pool.rel_count[b], 0);
    }

    #[test]
    fn test_remove_directed() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 10);
        assert!(remove_directed(&mut pool, a, id_b, BondType::Friend as u8));
        assert_eq!(pool.rel_count[a], 0);
        // Sentinel hygiene
        assert_eq!(pool.rel_bond_types[a][0], EMPTY_BOND_TYPE);
    }

    #[test]
    fn test_multi_bond_pairs() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Rival as u8, -30, 5);
        upsert_directed(&mut pool, a, id_b, BondType::CoReligionist as u8, 40, 8);
        assert_eq!(pool.rel_count[a], 2);
        // Both bonds coexist
        assert!(find_relationship(&pool, a, id_b, BondType::Rival as u8).is_some());
        assert!(find_relationship(&pool, a, id_b, BondType::CoReligionist as u8).is_some());
    }
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run relationships`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```
git add chronicler-agents/src/relationships.rs
git commit -m "feat(m50a): upsert/remove operations with atomicity and eviction"
```

---

### Task 5: Constants and RNG Stream Offset

**Files:**
- Modify: `chronicler-agents/src/agent.rs:82-96` (STREAM_OFFSETS)
- Modify: `chronicler-agents/src/agent.rs` (new constants block after M49)

- [ ] **Step 1: Register RNG stream offset 1100**

In the `STREAM_OFFSETS` block in `agent.rs` (after the M48/M49 entries), add:

```rust
    // M50 — Relationship formation / dissolution (not consumed in M50a)
    pub const RELATIONSHIP_STREAM_OFFSET: u64 = 1100;
```

- [ ] **Step 2: Add M50a constants block**

After the M49 needs constants section (~line 262), add:

```rust
// ── M50a: Relationship Substrate ──────────────────────────────────────────────
// Kin auto-formation initial sentiments
pub const KIN_INITIAL_PARENT: i8 = 60;   // [CALIBRATE M53] parent→child
pub const KIN_INITIAL_CHILD: i8 = 40;    // [CALIBRATE M53] child→parent

// Sentiment drift — co-located bonds
pub const POSITIVE_COLOC_DRIFT: i16 = 1;           // [CALIBRATE M53] per-tick positive drift
pub const NEGATIVE_COLOC_DRIFT: i16 = 1;           // [CALIBRATE M53] per-tick negative deepening
pub const STRONG_TIE_THRESHOLD: i16 = 100;         // [CALIBRATE M53] cadence kicks in above this
pub const STRONG_TIE_CADENCE: u16 = 2;             // [CALIBRATE M53] drift every N ticks above threshold

// Sentiment drift — separation decay
pub const POSITIVE_SEPARATION_DECAY: i16 = 1;      // [CALIBRATE M53] per-tick positive decay
pub const NEGATIVE_DECAY_CADENCE: u16 = 4;         // [CALIBRATE M53] ticks between negative decay steps
```

- [ ] **Step 3: Add offset to the collision test**

Find the existing STREAM_OFFSETS collision test in `agent.rs` or the test files and add `RELATIONSHIP_STREAM_OFFSET` to the checked list.

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass (including collision test).

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/agent.rs
git commit -m "feat(m50a): relationship constants and RNG stream offset 1100"
```

---

### Task 6: Kin Auto-Formation at Birth

**Files:**
- Modify: `chronicler-agents/src/relationships.rs` (add `form_kin_bond`)
- Modify: `chronicler-agents/src/tick.rs:417-432` (birth loop)

- [ ] **Step 1: Add `form_kin_bond` function**

In `relationships.rs`:

```rust
/// Form a kin bond between parent and child at birth.
/// Atomic pair-write: both succeed or neither.
/// Returns true if both bonds were written.
pub fn form_kin_bond(pool: &mut AgentPool, parent_slot: usize, child_slot: usize, turn: u16) -> bool {
    let parent_id = pool.ids[parent_slot];
    let child_id = pool.ids[child_slot];
    if parent_id == child_id { return false; }

    let bond_type = BondType::Kin as u8;

    // Resolve both sides before committing
    let res_parent = resolve_slot(pool, parent_slot, child_id, bond_type);
    let res_child = resolve_slot(pool, child_slot, parent_id, bond_type);

    let can_parent = !matches!(res_parent, SlotResolution::NoSlot);
    let can_child = !matches!(res_child, SlotResolution::NoSlot);
    if !can_parent || !can_child { return false; }

    commit_resolved(pool, parent_slot, child_id, bond_type,
                    crate::agent::KIN_INITIAL_PARENT, turn, res_parent);
    commit_resolved(pool, child_slot, parent_id, bond_type,
                    crate::agent::KIN_INITIAL_CHILD, turn, res_child);
    true
}
```

- [ ] **Step 2: Wire into birth loop in tick.rs**

In `tick.rs`, after `pool.parent_ids[new_slot] = birth.parent_id;` (line ~432), add:

```rust
            // M50a: auto-form kin bond between parent and child
            if birth.parent_id != crate::agent::PARENT_NONE {
                if let Some(parent_slot) = pool.find_slot_by_id(birth.parent_id) {
                    if !crate::relationships::form_kin_bond(pool, parent_slot, new_slot, turn) {
                        kin_bond_failures += 1;
                    }
                }
            }
```

Also add `let mut kin_bond_failures: u32 = 0;` at the start of the demographics section. After the birth loop, log failures: `if kin_bond_failures > 0 { log::debug!("M50a: {} kin bond formations failed (slot exhaustion)", kin_bond_failures); }`. This is diagnostic-only — no need to persist or return the counter.

- [ ] **Step 3: Write test for kin auto-formation**

```rust
    #[test]
    fn test_form_kin_bond() {
        let mut pool = create_test_pool(2);
        let parent = spawn_test_agent(&mut pool, 0, 0);
        let child = spawn_test_agent(&mut pool, 0, 0);

        assert!(form_kin_bond(&mut pool, parent, child, 50));

        // Parent has kin bond to child
        assert_eq!(pool.rel_count[parent], 1);
        let (tid, sent, bt, _) = read_rel(&pool, parent, 0);
        assert_eq!(tid, pool.ids[child]);
        assert_eq!(sent, crate::agent::KIN_INITIAL_PARENT);
        assert_eq!(bt, BondType::Kin as u8);

        // Child has kin bond to parent
        assert_eq!(pool.rel_count[child], 1);
        let (tid, sent, bt, _) = read_rel(&pool, child, 0);
        assert_eq!(tid, pool.ids[parent]);
        assert_eq!(sent, crate::agent::KIN_INITIAL_CHILD);
        assert_eq!(bt, BondType::Kin as u8);
    }

    #[test]
    fn test_form_kin_bond_atomic_failure() {
        let mut pool = create_test_pool(2);
        let parent = spawn_test_agent(&mut pool, 0, 0);
        let child = spawn_test_agent(&mut pool, 0, 0);

        // Fill parent with 8 kin bonds
        for i in 0..8 {
            write_rel(&mut pool, parent, i, (200 + i) as u32, 50, BondType::Kin as u8, 1);
        }
        pool.rel_count[parent] = 8;

        // Should fail atomically — child should NOT get a bond either
        assert!(!form_kin_bond(&mut pool, parent, child, 50));
        assert_eq!(pool.rel_count[child], 0);
    }
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/relationships.rs chronicler-agents/src/tick.rs
git commit -m "feat(m50a): kin auto-formation at birth with atomic pair-write"
```

---

### Task 7: Sentiment Drift

**Files:**
- Modify: `chronicler-agents/src/relationships.rs` (add `drift_relationships`)
- Modify: `chronicler-agents/src/tick.rs:83-91` (phase 0.8 call site)

- [ ] **Step 1: Implement drift function**

In `relationships.rs`:

```rust
use std::collections::HashMap;

/// Per-tick sentiment drift for all agents.
/// Phase 0.8: after needs (0.75), before satisfaction (1.0).
pub fn drift_relationships(pool: &mut AgentPool, turn: u16) {
    // Build id→slot lookup (alive agents only)
    let mut id_to_slot: HashMap<u32, usize> = HashMap::with_capacity(pool.capacity());
    for slot in 0..pool.capacity() {
        if pool.alive[slot] {
            id_to_slot.insert(pool.ids[slot], slot);
        }
    }

    for agent_slot in 0..pool.capacity() {
        if !pool.alive[agent_slot] { continue; }
        let count = pool.rel_count[agent_slot] as usize;
        let agent_region = pool.regions[agent_slot];

        for i in 0..count {
            let target_id = pool.rel_target_ids[agent_slot][i];
            let bond_type = pool.rel_bond_types[agent_slot][i];
            let mut sent = pool.rel_sentiments[agent_slot][i] as i16;

            // Determine co-location (dead/missing targets → not co-located)
            let co_located = id_to_slot.get(&target_id)
                .map(|&ts| pool.alive[ts] && pool.regions[ts] == agent_region)
                .unwrap_or(false);

            let valence = is_positive_valence(bond_type);

            if co_located {
                if valence {
                    // Positive: strengthen toward +127, cadence-gated above threshold
                    if sent <= crate::agent::STRONG_TIE_THRESHOLD
                        || turn % crate::agent::STRONG_TIE_CADENCE == 0
                    {
                        sent = (sent + crate::agent::POSITIVE_COLOC_DRIFT).min(127);
                    }
                } else {
                    // Negative: deepen toward -128
                    sent = (sent - crate::agent::NEGATIVE_COLOC_DRIFT).max(-128);
                }
            } else {
                // Separated: decay toward 0
                if sent > 0 {
                    sent = (sent - crate::agent::POSITIVE_SEPARATION_DECAY).max(0);
                } else if sent < 0 {
                    // Negative decays slower (cadence-gated)
                    if turn % crate::agent::NEGATIVE_DECAY_CADENCE == 0 {
                        sent = (sent + 1).min(0);
                    }
                }
            }

            pool.rel_sentiments[agent_slot][i] = sent as i8;
        }
    }
}
```

- [ ] **Step 2: Wire into tick.rs**

Between the needs update (0.75) and satisfaction (1.0) calls, add:

```rust
    // 0.8 Relationship sentiment drift (M50a)
    crate::relationships::drift_relationships(pool, turn);
```

- [ ] **Step 3: Write drift tests**

```rust
    #[test]
    fn test_drift_positive_colocation_strengthens() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0); // region 0
        let b = spawn_test_agent(&mut pool, 0, 0); // same region
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 51); // 50 + 1
    }

    #[test]
    fn test_drift_negative_colocation_deepens() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Rival as u8, -50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], -51); // -50 - 1
    }

    #[test]
    fn test_drift_separation_positive_decays() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0); // region 0
        let b = spawn_test_agent(&mut pool, 1, 0); // different region
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 49); // 50 - 1
    }

    #[test]
    fn test_drift_separation_negative_slow_decay() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 1, 0); // different region
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Grudge as u8, -50, 1);
        // Turn 1: not on cadence (NEGATIVE_DECAY_CADENCE=4)
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], -50); // no change
        // Turn 4: on cadence
        drift_relationships(&mut pool, 4);
        assert_eq!(pool.rel_sentiments[a][0], -49); // -50 + 1
    }

    #[test]
    fn test_drift_dead_target_uses_separation_rules() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 50, 1);
        // Kill target
        pool.alive[b] = false;
        drift_relationships(&mut pool, 1);
        // Should decay under separation rules (not skip)
        assert_eq!(pool.rel_sentiments[a][0], 49);
    }

    #[test]
    fn test_drift_strong_tie_cadence() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        // Above STRONG_TIE_THRESHOLD (100)
        upsert_directed(&mut pool, a, id_b, BondType::Kin as u8, 105, 1);
        // Turn 1: not on cadence (STRONG_TIE_CADENCE=2)
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 105); // no drift
        // Turn 2: on cadence
        drift_relationships(&mut pool, 2);
        assert_eq!(pool.rel_sentiments[a][0], 106); // drifts
    }

    #[test]
    fn test_drift_saturating_math() {
        let mut pool = create_test_pool(2);
        let a = spawn_test_agent(&mut pool, 0, 0);
        let b = spawn_test_agent(&mut pool, 0, 0);
        let id_b = pool.ids[b];

        upsert_directed(&mut pool, a, id_b, BondType::Friend as u8, 127, 1);
        drift_relationships(&mut pool, 1);
        assert_eq!(pool.rel_sentiments[a][0], 127); // clamped, not overflow
    }
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo nextest run relationships`
Expected: All drift tests pass.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/relationships.rs chronicler-agents/src/tick.rs
git commit -m "feat(m50a): sentiment drift with valence-dependent co-location and cadence-gated slowing"
```

---

### Task 8: apply_relationship_ops FFI

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Add `apply_relationship_ops` pymethod**

After `replace_social_edges()` (~line 822), add:

```rust
    /// M50a: Apply batched relationship operations.
    /// Arrow schema: [op_type: u8, agent_a: u32, agent_b: u32, bond_type: u8, sentiment: i8, formed_turn: u16]
    fn apply_relationship_ops(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let batch = batch.into_inner();
        let len = batch.num_rows();
        if len == 0 { return Ok(()); }

        let op_types = batch.column(0).as_any().downcast_ref::<UInt8Array>().unwrap();
        let agent_as = batch.column(1).as_any().downcast_ref::<UInt32Array>().unwrap();
        let agent_bs = batch.column(2).as_any().downcast_ref::<UInt32Array>().unwrap();
        let bond_types = batch.column(3).as_any().downcast_ref::<UInt8Array>().unwrap();
        let sentiments = batch.column(4).as_any().downcast_ref::<Int8Array>().unwrap();
        let formed_turns = batch.column(5).as_any().downcast_ref::<UInt16Array>().unwrap();

        for i in 0..len {
            let op = op_types.value(i);
            let id_a = agent_as.value(i);
            let id_b = agent_bs.value(i);
            let bt = bond_types.value(i);
            let sent = sentiments.value(i);
            let ft = formed_turns.value(i);

            // Validate bond_type
            if crate::relationships::BondType::from_u8(bt).is_none() {
                log::debug!("apply_relationship_ops: unknown bond_type {} at row {}", bt, i);
                continue;
            }

            match op {
                0 => { // UpsertDirected
                    let Some(slot_a) = self.pool.find_slot_by_id(id_a) else {
                        log::debug!("apply_relationship_ops: src {} not found at row {}", id_a, i);
                        continue;
                    };
                    if !self.pool.alive[slot_a] { continue; }
                    // Target must be alive for upsert
                    if self.pool.find_slot_by_id(id_b).map_or(true, |s| !self.pool.alive[s]) {
                        log::debug!("apply_relationship_ops: dst {} dead/missing at row {}", id_b, i);
                        continue;
                    }
                    // Guard: no UpsertSymmetric with asymmetric types handled below
                    crate::relationships::upsert_directed(&mut self.pool, slot_a, id_b, bt, sent, ft);
                }
                1 => { // UpsertSymmetric
                    if crate::relationships::is_asymmetric(bt) {
                        log::debug!("apply_relationship_ops: UpsertSymmetric with asymmetric type {} at row {}", bt, i);
                        continue;
                    }
                    let Some(slot_a) = self.pool.find_slot_by_id(id_a) else { continue; };
                    let Some(slot_b) = self.pool.find_slot_by_id(id_b) else { continue; };
                    if !self.pool.alive[slot_a] || !self.pool.alive[slot_b] { continue; }
                    crate::relationships::upsert_symmetric(&mut self.pool, slot_a, slot_b, bt, sent, ft);
                }
                2 => { // RemoveDirected
                    // Source must exist; target may be dead (dead-target cleanup)
                    let Some(slot_a) = self.pool.find_slot_by_id(id_a) else { continue; };
                    if !self.pool.alive[slot_a] { continue; }
                    crate::relationships::remove_directed(&mut self.pool, slot_a, id_b, bt);
                }
                3 => { // RemoveSymmetric
                    let Some(slot_a) = self.pool.find_slot_by_id(id_a) else { continue; };
                    let Some(slot_b) = self.pool.find_slot_by_id(id_b) else { continue; };
                    // Both sources must be alive (own their slots)
                    if self.pool.alive[slot_a] && self.pool.alive[slot_b] {
                        crate::relationships::remove_symmetric(&mut self.pool, slot_a, slot_b, bt);
                    }
                }
                _ => {
                    log::debug!("apply_relationship_ops: unknown op_type {} at row {}", op, i);
                }
            }
        }
        Ok(())
    }
```

- [ ] **Step 2: Add `get_agent_relationships` pymethod**

```rust
    /// M50a: Get all relationship slots for one agent.
    /// Returns list of (target_id, sentiment, bond_type, formed_turn) tuples.
    fn get_agent_relationships(&self, agent_id: u32) -> Option<Vec<(u32, i8, u8, u16)>> {
        let slot = self.pool.find_slot_by_id(agent_id)?;
        if !self.pool.alive[slot] { return None; }
        let count = self.pool.rel_count[slot] as usize;
        let mut result = Vec::with_capacity(count);
        for i in 0..count {
            result.push(crate::relationships::read_rel(&self.pool, slot, i));
        }
        Some(result)
    }
```

- [ ] **Step 3: Verify Arrow imports**

Check that `Int8Array` is imported in `ffi.rs`. If not, add it to the existing `use arrow::array::` import line. Also verify `UInt8Array`, `UInt16Array`, `UInt32Array` are present.

- [ ] **Step 4: Run Rust tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: Compiles and all tests pass.

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m50a): apply_relationship_ops and get_agent_relationships FFI methods"
```

---

### Task 9: Reimplement get_social_edges as Projection

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:716-741`

- [ ] **Step 1: Rewrite `get_social_edges` to project from per-agent store**

Replace the existing implementation that reads from `self.social_graph` with a projection over the per-agent relationship store. The method signature and return type stay identical.

```rust
    fn get_social_edges(&self) -> PyResult<PyRecordBatch> {
        // Collect named character agent IDs
        let named_ids: std::collections::HashSet<u32> = self.registry.characters.iter().map(|c| c.agent_id).collect();

        let mut agent_a_vals: Vec<u32> = Vec::new();
        let mut agent_b_vals: Vec<u32> = Vec::new();
        let mut rel_type_vals: Vec<u8> = Vec::new();
        let mut formed_turn_vals: Vec<u16> = Vec::new();

        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            if !named_ids.contains(&agent_id) { continue; }

            let count = self.pool.rel_count[slot] as usize;
            for i in 0..count {
                let bt = self.pool.rel_bond_types[slot][i];
                // Only project M40-compatible types (0-4)
                if bt > 4 { continue; }

                let target_id = self.pool.rel_target_ids[slot][i];

                if crate::relationships::is_asymmetric(bt) {
                    // Mentor: emit from mentor side (agent_a=mentor, agent_b=apprentice)
                    agent_a_vals.push(agent_id);
                    agent_b_vals.push(target_id);
                    rel_type_vals.push(bt);
                    formed_turn_vals.push(self.pool.rel_formed_turns[slot][i]);
                } else {
                    // Symmetric: emit only from the lower-id side to avoid duplicates
                    if agent_id < target_id {
                        agent_a_vals.push(agent_id);
                        agent_b_vals.push(target_id);
                        rel_type_vals.push(bt);
                        formed_turn_vals.push(self.pool.rel_formed_turns[slot][i]);
                    }
                }
            }
        }

        // Build Arrow RecordBatch with same schema as before
        let schema = Arc::new(Schema::new(vec![
            Field::new("agent_a", DataType::UInt32, false),
            Field::new("agent_b", DataType::UInt32, false),
            Field::new("relationship", DataType::UInt8, false),
            Field::new("formed_turn", DataType::UInt16, false),
        ]));
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(UInt32Array::from(agent_a_vals)),
                Arc::new(UInt32Array::from(agent_b_vals)),
                Arc::new(UInt8Array::from(rel_type_vals)),
                Arc::new(UInt16Array::from(formed_turn_vals)),
            ],
        ).map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;

        Ok(PyRecordBatch::new(batch))
    }
```

- [ ] **Step 2: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All pass. The new projection produces the same output shape.

- [ ] **Step 3: Commit**

```
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m50a): get_social_edges reimplemented as projection over per-agent store"
```

---

### Task 10: replace_social_edges Compatibility Shim

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:789-822`
- Modify: `chronicler-agents/src/social.rs` (deprecation comment)

- [ ] **Step 1: Rewrite `replace_social_edges` as a shim**

Replace the existing implementation that writes to `self.social_graph` with a shim that diffs incoming edges against current state and applies ops:

```rust
    /// M40 compatibility shim. Translates full-graph replacement into incremental ops.
    /// DEPRECATED — use apply_relationship_ops directly. Will be removed in M50b.
    fn replace_social_edges(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let batch = batch.into_inner();
        let named_ids: std::collections::HashSet<u32> = self.registry.characters.iter().map(|c| c.agent_id).collect();

        // 1. Read current projected state
        let mut current: std::collections::HashSet<(u32, u32, u8)> = std::collections::HashSet::new();
        for slot in 0..self.pool.capacity() {
            if !self.pool.alive[slot] { continue; }
            let agent_id = self.pool.ids[slot];
            if !named_ids.contains(&agent_id) { continue; }
            let count = self.pool.rel_count[slot] as usize;
            for i in 0..count {
                let bt = self.pool.rel_bond_types[slot][i];
                if bt > 4 { continue; } // Only M40-compatible
                let target_id = self.pool.rel_target_ids[slot][i];
                if crate::relationships::is_asymmetric(bt) {
                    current.insert((agent_id, target_id, bt));
                } else if agent_id < target_id {
                    current.insert((agent_id, target_id, bt));
                }
            }
        }

        // 2. Parse incoming batch
        let mut incoming: std::collections::HashSet<(u32, u32, u8)> = std::collections::HashSet::new();
        let mut incoming_turns: std::collections::HashMap<(u32, u32, u8), u16> = std::collections::HashMap::new();
        let mut incoming_sents: std::collections::HashMap<(u32, u32, u8), i8> = std::collections::HashMap::new();
        if batch.num_rows() > 0 {
            let a_col = batch.column(0).as_any().downcast_ref::<UInt32Array>().unwrap();
            let b_col = batch.column(1).as_any().downcast_ref::<UInt32Array>().unwrap();
            let r_col = batch.column(2).as_any().downcast_ref::<UInt8Array>().unwrap();
            let t_col = batch.column(3).as_any().downcast_ref::<UInt16Array>().unwrap();
            for i in 0..batch.num_rows() {
                let a = a_col.value(i);
                let b = b_col.value(i);
                let r = r_col.value(i);
                let t = t_col.value(i);
                // Guard: only named characters
                if !named_ids.contains(&a) || !named_ids.contains(&b) { continue; }
                let key = if crate::relationships::is_asymmetric(r) { (a, b, r) }
                          else { (a.min(b), a.max(b), r) };
                incoming.insert(key);
                incoming_turns.insert(key, t);
                // Default sentiment for new bonds from M40 (no sentiment in legacy format)
                incoming_sents.insert(key, 50);
            }
        }

        // 3. Diff: removals = current - incoming, additions = incoming - current
        for &(a, b, bt) in current.difference(&incoming) {
            if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                if crate::relationships::is_asymmetric(bt) {
                    crate::relationships::remove_directed(&mut self.pool, slot_a, b, bt);
                } else if let Some(slot_b) = self.pool.find_slot_by_id(b) {
                    crate::relationships::remove_symmetric(&mut self.pool, slot_a, slot_b, bt);
                }
            }
        }
        for &(a, b, bt) in incoming.difference(&current) {
            let ft = incoming_turns.get(&(a, b, bt)).copied().unwrap_or(0);
            let sent = incoming_sents.get(&(a, b, bt)).copied().unwrap_or(50);
            if crate::relationships::is_asymmetric(bt) {
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    crate::relationships::upsert_directed(&mut self.pool, slot_a, b, bt, sent, ft);
                }
            } else {
                if let Some(slot_a) = self.pool.find_slot_by_id(a) {
                    if let Some(slot_b) = self.pool.find_slot_by_id(b) {
                        crate::relationships::upsert_symmetric(&mut self.pool, slot_a, slot_b, bt, sent, ft);
                    }
                }
            }
        }

        Ok(())
    }
```

- [ ] **Step 2: Add deprecation comment to SocialGraph**

In `social.rs`, add at the top:

```rust
// DEPRECATED (M50a): SocialGraph is no longer authoritative.
// Relationships are stored per-agent in pool.rs SoA fields.
// This struct will be deleted once replace_social_edges() shim is removed.
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All pass.

- [ ] **Step 4: Commit**

```
git add chronicler-agents/src/ffi.rs chronicler-agents/src/social.rs
git commit -m "feat(m50a): replace_social_edges compatibility shim with diff-based translation"
```

---

### Task 11: Python-Side Integration

**Files:**
- Modify: `src/chronicler/models.py` (GreatPerson class)
- Modify: `src/chronicler/agent_bridge.py:504-521` (sync loop)
- Modify: `src/chronicler/agent_bridge.py:1120-1152` (social edge methods)

- [ ] **Step 1: Add `agent_bonds` field to GreatPerson**

In `models.py`, in the GreatPerson class (after the `needs` field), add:

```python
    agent_bonds: Optional[list] = None  # M50a: synced from Rust per-agent store
```

- [ ] **Step 2: Add `apply_relationship_ops` wrapper to AgentBridge**

In `agent_bridge.py`, near the existing `replace_social_edges` method:

```python
    def apply_relationship_ops(self, ops: list[dict]) -> None:
        """Apply batched relationship ops to the Rust store.
        Each op: {"op_type": int, "agent_a": int, "agent_b": int,
                  "bond_type": int, "sentiment": int, "formed_turn": int}
        """
        if not ops:
            return
        import pyarrow as pa
        arrays = [
            pa.array([o["op_type"] for o in ops], type=pa.uint8()),
            pa.array([o["agent_a"] for o in ops], type=pa.uint32()),
            pa.array([o["agent_b"] for o in ops], type=pa.uint32()),
            pa.array([o["bond_type"] for o in ops], type=pa.uint8()),
            pa.array([o.get("sentiment", 0) for o in ops], type=pa.int8()),
            pa.array([o.get("formed_turn", 0) for o in ops], type=pa.uint16()),
        ]
        batch = pa.RecordBatch.from_arrays(arrays, names=[
            "op_type", "agent_a", "agent_b", "bond_type", "sentiment", "formed_turn"
        ])
        self._sim.apply_relationship_ops(batch)
```

- [ ] **Step 3: Add `agent_bonds` sync to per-GP loop**

In the existing per-GP sync loop (after needs sync, ~line 521), add:

```python
            # M50a: relationship sync
            raw_bonds = self._sim.get_agent_relationships(gp.agent_id)
            if raw_bonds is not None:
                gp.agent_bonds = [
                    {"target_id": b[0], "sentiment": b[1], "bond_type": b[2], "formed_turn": b[3]}
                    for b in raw_bonds
                ]
```

- [ ] **Step 4: Run Python tests**

Run: `pytest tests/ -x -q`
Expected: All existing tests pass (no behavioral change — the shim preserves M40 behavior).

- [ ] **Step 5: Commit**

```
git add src/chronicler/models.py src/chronicler/agent_bridge.py
git commit -m "feat(m50a): Python integration — agent_bonds field, apply_relationship_ops, sync loop"
```

---

### Task 12: Rust Integration Tests

**Files:**
- Create: `chronicler-agents/tests/test_relationships.rs`

- [ ] **Step 1: Write integration tests**

Create `chronicler-agents/tests/test_relationships.rs`:

```rust
//! M50a relationship substrate integration tests.
//!
//! Tests end-to-end behavior: kin formation at birth → drift over multiple turns →
//! eviction under slot pressure → projection compatibility.

// Import patterns vary by test file convention in this crate.
// Check existing integration test files (e.g., test_memory.rs) for the correct
// import pattern and constructor usage before writing.

// Tests to implement:
// 1. Kin bond formed after simulated birth, visible via get_agent_relationships
// 2. Multi-turn drift: co-located kin bond sentiment increases each tick
// 3. Slot exhaustion: 8 kin bonds → social upsert fails
// 4. apply_relationship_ops round-trip: build Arrow batch, apply, verify store state
// 5. get_social_edges projection: only types 0-4, only named characters, a<b convention
// 6. Batch ordering: Upsert→Remove→Upsert in one batch produces correct final state
// 7. Invalid ops: dead agent, unknown bond type, symmetric Mentor → all skipped
// 8. Remove with dead target: succeeds (source alive, target dead)
// 9. Determinism: same operations in same order produce identical store state
```

**Important:** Before writing test bodies, read an existing integration test file (e.g., `chronicler-agents/tests/test_memory.rs` or `chronicler-agents/tests/test_needs.rs`) to understand:
- How to construct `AgentSimulator` in tests
- How to build Arrow `RecordBatch` in tests
- How `RegionState` is constructed (use constructor functions, NOT struct literals)
- How to call FFI methods from integration tests

Mirror that pattern exactly. Each test should be self-contained with its own pool setup.

- [ ] **Step 2: Run integration tests**

Run: `cd chronicler-agents && cargo nextest run test_relationships`
Expected: All pass.

- [ ] **Step 3: Commit**

```
git add chronicler-agents/tests/test_relationships.rs
git commit -m "test(m50a): Rust integration tests for relationship substrate"
```

---

### Task 13: Python Integration Tests and Determinism

**Files:**
- Create: `tests/test_m50a_relationships.py`

- [ ] **Step 1: Write Python integration tests**

```python
"""M50a relationship substrate integration tests.

Tests M40 compatibility, GreatPerson sync, and determinism.
"""

# Tests to implement:
# 1. M40 round-trip: form_and_sync_relationships() → replace_social_edges() shim →
#    read_social_edges() projection → same narration context as pre-M50a
# 2. formed_turn preservation: repeated replace_social_edges() calls don't overwrite
#    original formation turns
# 3. GreatPerson.agent_bonds populated with kin bonds after simulation tick
# 4. Determinism: two runs with same seed produce identical relationship state
# 5. Transient signal: relationship ops applied in turn N don't leak into turn N+1
#    (ops are consumed and discarded)
```

**Important:** Before writing test bodies, read existing test files (e.g., `tests/test_m48_memory.py` or `tests/test_needs.py`) for the project's test patterns:
- How to set up `WorldState` and `AgentBridge`
- How to run simulation turns for testing
- Assertion patterns

- [ ] **Step 2: Run Python tests**

Run: `pytest tests/test_m50a_relationships.py -v`
Expected: All pass.

- [ ] **Step 3: Commit**

```
git add tests/test_m50a_relationships.py
git commit -m "test(m50a): Python integration tests for M40 compatibility and determinism"
```

---

### Task 14: CLAUDE.md Updates and Final Verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Rust file table**

Add to the Rust crate file table:

```
| `relationships.rs` | Per-agent relationship store, bond helpers, sentiment drift, eviction |
```

- [ ] **Step 2: Run full test suite**

Run: `cd chronicler-agents && cargo nextest run` and `pytest tests/ -x -q`
Expected: All Rust and Python tests pass.

- [ ] **Step 3: Commit**

```
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with M50a relationships.rs module"
```
