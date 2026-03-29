# M57a: Marriage Matching & Lineage Schema — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Rust-native marriage formation and migrate from single-parent to two-parent lineage across the full Rust/Python stack.

**Architecture:** Separate `marriage_scan()` in `formation.rs` runs before `formation_scan()` with scored greedy matching. Pool storage splits `parent_ids` into `parent_id_0`/`parent_id_1`. The migration propagates through FFI schemas, `named_characters.rs`, Python `GreatPerson`, dynasty/succession logic, kin bonds, and legacy memory inheritance.

**Tech Stack:** Rust (chronicler-agents crate), Python (src/chronicler), Arrow IPC for FFI.

**Spec:** `docs/superpowers/specs/2026-03-26-m57a-marriage-lineage-design.md`

**Subagent dispatch checklist (from CLAUDE.md):**
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially treasury/tithe/population fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.

---

## File Map

### Rust — Modify

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/agent.rs` | New constants: `MARRIAGE_CADENCE`, `MARRIAGE_RADIUS`, `MARRIAGE_STREAM_OFFSET`, `MARRIAGE_MIN_AGE`, compatibility weights. Add offset to collision test. |
| `chronicler-agents/src/pool.rs` | Split `parent_ids` → `parent_id_0` + `parent_id_1`. Update `spawn()`, `kill()` (no-op — free-list), `to_record_batch()`, accessors. |
| `chronicler-agents/src/relationships.rs` | `is_protected()` adds Marriage. New `get_spouse_id()` helper. |
| `chronicler-agents/src/formation.rs` | New `marriage_scan()`, `MarriageCandidate`, `marriage_pair_hash()`. Reuse existing hashing helpers without widening visibility unless needed. Add marriage diagnostics fields to `FormationStats`. |
| `chronicler-agents/src/tick.rs` | `BirthInfo` dual-parent. Kin bond widening. Reverse-index widening. BirthOfKin for both parents. Wire `marriage_scan()` before `formation_scan()` using `signals` and post-demographics alive slots. |
| `chronicler-agents/src/ffi.rs` | `snapshot_schema()`: `parent_id` → `parent_id_0` + `parent_id_1`. `promotions_schema()`: same. `get_promotions()`: export both parents. `get_relationship_stats()`: add marriage keys. |
| `chronicler-agents/src/named_characters.rs` | `NamedCharacter.parent_id` → `parent_id_0` + `parent_id_1`. `register()` signature. |
| `chronicler-agents/src/memory.rs` | `MemoryIntent` + `expected_agent_id`. `write_all_memories()` identity check. |

### Rust — Create

| File | Responsibility |
|------|---------------|
| `chronicler-agents/tests/test_m57a_marriage.rs` | Marriage formation, exclusivity, eligibility, lineage FFI round-trip tests. |

### Python — Modify

| File | Responsibility |
|------|---------------|
| `src/chronicler/models.py` | `GreatPerson`: `parent_id` → `parent_id_0` + `parent_id_1`, add `lineage_house`, `parent_ids()` helper. |
| `src/chronicler/agent_bridge.py` | `_process_promotions()`: read `parent_id_0`/`parent_id_1` columns. Snapshot column reads. Stats passthrough. Carry lineage metadata through the promotion/materialization seam. |
| `src/chronicler/dynasties.py` | `check_promotion()`: dual-parent dynasty resolution. `compute_dynasty_legitimacy()`: either-parent direct-heir check. |
| `src/chronicler/factions.py` | Succession candidate dict: `parent_id` → `parent_id_0` + `parent_id_1`. |
| `src/chronicler/simulation.py` | `marriage_formed` named-character event wiring. |
| `src/chronicler/narrative.py` | Consume resolved lineage-house context in narrator text; do not instantiate a dynasty registry here. |
| `src/chronicler/relationships.py` | Deprecation comment on `check_marriage_formation()`. |

---

## Task 1: Rust Constants & Stream Offset

**Files:**
- Modify: `chronicler-agents/src/agent.rs:89-113` (STREAM_OFFSETS block), `chronicler-agents/src/agent.rs:414-428` (collision test)

- [ ] **Step 1: Add marriage constants to `agent.rs`**

After the `SPATIAL_DRIFT_STREAM_OFFSET` line (line 112), add:

```rust
// M57a: Marriage formation
pub const MARRIAGE_STREAM_OFFSET: u64 = 1600;  // reserved, not consumed in v1
pub const MARRIAGE_CADENCE: u32 = 4;            // marriage scan runs every 4th turn per region
pub const MARRIAGE_RADIUS: f32 = 0.25;          // spatial proximity threshold (unit square)
pub const MARRIAGE_MIN_AGE: u16 = 16;           // matches FERTILITY_AGE_MIN
// Marriage compatibility weights
pub const MARRIAGE_SAME_CIV_BONUS: f32 = 0.30;
pub const MARRIAGE_SAME_BELIEF_BONUS: f32 = 0.20;
pub const MARRIAGE_CULTURE_MATCH_BONUS: f32 = 0.15;  // per matching cultural value (max 3)
pub const MARRIAGE_CLOSENESS_CAP: f32 = 0.20;        // max spatial proximity bonus
pub const MARRIAGE_CROSS_FAITH_PENALTY: f32 = 0.10;
```

- [ ] **Step 2: Add `MARRIAGE_STREAM_OFFSET` to the collision test**

In the `test_stream_offsets_no_collision` test (around line 415), add `MARRIAGE_STREAM_OFFSET` to the offsets array:

```rust
SPATIAL_DRIFT_STREAM_OFFSET,     // 2001
MARRIAGE_STREAM_OFFSET,          // 1600
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents test_stream_offsets_no_collision`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m57a): add marriage constants and stream offset reservation"
```

---

## Task 2: Pool Storage Migration — `parent_ids` → `parent_id_0` + `parent_id_1`

**Files:**
- Modify: `chronicler-agents/src/pool.rs:49` (field), `:96-145` (new()), `:167-273` (spawn()), `:427-428` (accessor), `:478-544` (to_record_batch())

- [ ] **Step 1: Replace `parent_ids` field with two parallel arrays**

In the `AgentPool` struct (pool.rs:48-49), replace:
```rust
    // Parentage (M39) — stable agent_id of biological parent
    pub parent_ids: Vec<u32>,
```
with:
```rust
    // Parentage (M39/M57a) — stable agent_ids of biological parents
    pub parent_id_0: Vec<u32>,  // birth parent
    pub parent_id_1: Vec<u32>,  // other parent (spouse at birth time), PARENT_NONE if unknown
```

- [ ] **Step 2: Update `new()` — replace `parent_ids` with_capacity**

In `new()` (pool.rs:116), replace:
```rust
            parent_ids: Vec::with_capacity(capacity),
```
with:
```rust
            parent_id_0: Vec::with_capacity(capacity),
            parent_id_1: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Update `spawn()` — dead-slot reuse path**

In `spawn()` dead-slot reuse (pool.rs:191), replace:
```rust
            self.parent_ids[slot] = crate::agent::PARENT_NONE;
```
with:
```rust
            self.parent_id_0[slot] = crate::agent::PARENT_NONE;
            self.parent_id_1[slot] = crate::agent::PARENT_NONE;
```

- [ ] **Step 4: Update `spawn()` — grow-vecs path**

In `spawn()` grow path (pool.rs:244), replace:
```rust
            self.parent_ids.push(crate::agent::PARENT_NONE);
```
with:
```rust
            self.parent_id_0.push(crate::agent::PARENT_NONE);
            self.parent_id_1.push(crate::agent::PARENT_NONE);
```

- [ ] **Step 5: Replace the `parent_id()` accessor with dual-parent accessors**

Replace the existing accessor (pool.rs:426-429):
```rust
    #[inline]
    pub fn parent_id(&self, slot: usize) -> u32 {
        self.parent_ids[slot]
    }
```
with:
```rust
    #[inline]
    pub fn parent_id_0(&self, slot: usize) -> u32 {
        self.parent_id_0[slot]
    }
    #[inline]
    pub fn parent_id_1(&self, slot: usize) -> u32 {
        self.parent_id_1[slot]
    }
    #[inline]
    pub fn parent_ids(&self, slot: usize) -> [u32; 2] {
        [self.parent_id_0[slot], self.parent_id_1[slot]]
    }
    /// Check if `agent_id` is either parent of the agent at `slot`.
    #[inline]
    pub fn has_parent(&self, slot: usize, agent_id: u32) -> bool {
        agent_id != crate::agent::PARENT_NONE
            && (self.parent_id_0[slot] == agent_id || self.parent_id_1[slot] == agent_id)
    }
```

- [ ] **Step 6: Update `to_record_batch()` — builder and append**

In `to_record_batch()` (pool.rs:501), replace the single parent_id builder:
```rust
        let mut parent_id_col = UInt32Builder::with_capacity(live);
```
with:
```rust
        let mut parent_id_0_col = UInt32Builder::with_capacity(live);
        let mut parent_id_1_col = UInt32Builder::with_capacity(live);
```

In the loop (pool.rs:533), replace:
```rust
            parent_id_col.append_value(self.parent_ids[slot]);
```
with:
```rust
            parent_id_0_col.append_value(self.parent_id_0[slot]);
            parent_id_1_col.append_value(self.parent_id_1[slot]);
```

In the RecordBatch column vec (pool.rs:561), replace:
```rust
                Arc::new(parent_id_col.finish()) as _,
```
with:
```rust
                Arc::new(parent_id_0_col.finish()) as _,
                Arc::new(parent_id_1_col.finish()) as _,
```

- [ ] **Step 7: Fix all callers of `pool.parent_ids[slot]` and `pool.parent_id(slot)`**

Run: `cargo check -p chronicler-agents 2>&1` — this will surface every compilation error from the removed field/accessor. Fix each caller:
- `tick.rs`: `pool.parent_ids[slot]` → `pool.parent_id_0[slot]` (birth path assigns parent_id_0; reverse index reads both — addressed in Task 6)
- `ffi.rs`: `pool.parent_ids[slot]` → `pool.parent_id_0[slot]` (promotions — addressed in Task 3)
- Any test that uses `pool.parent_id(slot)` → `pool.parent_id_0(slot)`

For now, make it compile by pointing single-parent callers at `parent_id_0`. The full dual-parent wiring happens in later tasks.

- [ ] **Step 8: Run compile check**

Run: `cargo check -p chronicler-agents`
Expected: PASS. Full Rust test coverage resumes after Tasks 3-4 complete the FFI and named-character migration.

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m57a): split parent_ids into parent_id_0 + parent_id_1 in AgentPool"
```

---

## Task 3: FFI Schema Migration — Snapshot & Promotions

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:64-89` (snapshot_schema), `:124-138` (promotions_schema), `:2343-2417` (get_promotions), `:2829-2839` (get_relationship_stats)

- [ ] **Step 1: Update `snapshot_schema()`**

In `snapshot_schema()` (ffi.rs:83), replace:
```rust
        Field::new("parent_id", DataType::UInt32, false),
```
with:
```rust
        Field::new("parent_id_0", DataType::UInt32, false),
        Field::new("parent_id_1", DataType::UInt32, false),
```

- [ ] **Step 2: Update `promotions_schema()`**

In `promotions_schema()` (ffi.rs:136), replace:
```rust
        Field::new("parent_id", DataType::UInt32, false),
```
with:
```rust
        Field::new("parent_id_0", DataType::UInt32, false),
        Field::new("parent_id_1", DataType::UInt32, false),
```

- [ ] **Step 3: Update `get_promotions()` — builders and append**

In `get_promotions()` (ffi.rs:2356), replace:
```rust
        let mut parent_id_col = UInt32Builder::with_capacity(n);
```
with:
```rust
        let mut parent_id_0_col = UInt32Builder::with_capacity(n);
        let mut parent_id_1_col = UInt32Builder::with_capacity(n);
```

In the loop (ffi.rs:2380), replace:
```rust
            parent_id_col.append_value(self.pool.parent_ids[slot]);
```
with:
```rust
            parent_id_0_col.append_value(self.pool.parent_id_0[slot]);
            parent_id_1_col.append_value(self.pool.parent_id_1[slot]);
```

In the register call (ffi.rs:2395), replace:
```rust
                self.pool.parent_ids[slot],
```
with:
```rust
                self.pool.parent_id_0[slot],
                self.pool.parent_id_1[slot],
```

In the RecordBatch column vec (ffi.rs:2413), replace:
```rust
                Arc::new(parent_id_col.finish()) as _,
```
with:
```rust
                Arc::new(parent_id_0_col.finish()) as _,
                Arc::new(parent_id_1_col.finish()) as _,
```

- [ ] **Step 4: Run `cargo check`**

Run: `cargo check -p chronicler-agents`
Expected: Compile error in `named_characters.rs` register() — that's Task 4. If only that error, proceed.

- [ ] **Step 5: Commit** (after Task 4 compiles)

Deferred to after Task 4.

---

## Task 4: Named Character Registry — Dual-Parent

**Files:**
- Modify: `chronicler-agents/src/named_characters.rs:22-32` (NamedCharacter struct), `:143-165` (register())

- [ ] **Step 1: Update `NamedCharacter` struct**

In the struct (named_characters.rs:30), replace:
```rust
    pub parent_id: u32,
```
with:
```rust
    pub parent_id_0: u32,
    pub parent_id_1: u32,
```

- [ ] **Step 2: Update `register()` signature and body**

Replace the register method signature (named_characters.rs:143-154):
```rust
    pub fn register(
        &mut self,
        agent_id: u32,
        role: CharacterRole,
        civ_id: u8,
        origin_civ_id: u8,
        born_turn: u16,
        promotion_turn: u16,
        promotion_trigger: u8,
        parent_id: u32,
    ) {
        self.characters.push(NamedCharacter {
            agent_id,
            role,
            civ_id,
            origin_civ_id,
```
with:
```rust
    pub fn register(
        &mut self,
        agent_id: u32,
        role: CharacterRole,
        civ_id: u8,
        origin_civ_id: u8,
        born_turn: u16,
        promotion_turn: u16,
        promotion_trigger: u8,
        parent_id_0: u32,
        parent_id_1: u32,
    ) {
        self.characters.push(NamedCharacter {
            agent_id,
            role,
            civ_id,
            origin_civ_id,
```

And in the struct literal body, replace:
```rust
            parent_id,
```
with:
```rust
            parent_id_0,
            parent_id_1,
```

- [ ] **Step 3: Run `cargo check` and fix remaining callers**

Run: `cargo check -p chronicler-agents`
Fix any remaining callers of the old `register()` signature or `NamedCharacter.parent_id`.

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 5: Commit Tasks 3 + 4 together**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/named_characters.rs
git commit -m "feat(m57a): dual-parent FFI schemas and named character registry"
```

---

## Task 5: Relationship Helpers — `is_protected()` + `get_spouse_id()`

**Files:**
- Modify: `chronicler-agents/src/relationships.rs:42-45` (is_protected), add `get_spouse_id()`

- [ ] **Step 1: Write tests first**

Add to the existing test module in `relationships.rs` (after the `test_is_protected` test):

```rust
    #[test]
    fn test_marriage_is_protected() {
        assert!(is_protected(BondType::Marriage as u8));
        assert!(is_protected(BondType::Kin as u8));
        assert!(!is_protected(BondType::Friend as u8));
        assert!(!is_protected(BondType::Rival as u8));
    }

    #[test]
    fn test_get_spouse_id_none() {
        let (pool, slots) = setup_pool(1);
        assert_eq!(get_spouse_id(&pool, slots[0]), None);
    }

    #[test]
    fn test_get_spouse_id_found() {
        let (mut pool, slots) = setup_pool(2);
        let a = slots[0];
        let id_b = pool.ids[slots[1]];
        upsert_symmetric(&mut pool, a, slots[1], BondType::Marriage as u8, 50, 10);
        assert_eq!(get_spouse_id(&pool, a), Some(id_b));
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_marriage_is_protected test_get_spouse_id`
Expected: FAIL — `test_marriage_is_protected` fails, `get_spouse_id` not found.

- [ ] **Step 3: Update `is_protected()`**

Replace (relationships.rs:43-45):
```rust
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8
}
```
with:
```rust
pub fn is_protected(bond_type: u8) -> bool {
    bond_type == BondType::Kin as u8 || bond_type == BondType::Marriage as u8
}
```

- [ ] **Step 4: Add `get_spouse_id()`**

Add after `is_symmetric()` (around relationships.rs:60):
```rust
/// Find the target ID of an agent's Marriage bond.
/// Returns None if the agent has no active Marriage bond.
/// In debug builds, asserts at most one Marriage bond exists.
pub fn get_spouse_id(pool: &AgentPool, slot: usize) -> Option<u32> {
    let count = pool.rel_count[slot] as usize;
    let mut found: Option<u32> = None;
    for i in 0..count {
        if pool.rel_bond_types[slot][i] == BondType::Marriage as u8 {
            let target = pool.rel_target_ids[slot][i];
            debug_assert!(found.is_none(), "agent has multiple Marriage bonds (slot={})", slot);
            if found.is_some() {
                // Release fallback: return first found
                return found;
            }
            found = Some(target);
        }
    }
    found
}
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents test_marriage_is_protected test_get_spouse_id`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/relationships.rs
git commit -m "feat(m57a): marriage eviction protection and get_spouse_id helper"
```

---

## Task 6: Tick Birth Path — Dual-Parent Wiring + Kin Bond Widening

**Files:**
- Modify: `chronicler-agents/src/tick.rs:1017-1025` (BirthInfo), `:1157-1180` (birth generation), `:456-466` (reverse index), `:552-619` (birth resolution + kin bonds + BirthOfKin)

- [ ] **Step 1: Update `BirthInfo` struct**

Replace (tick.rs:1017-1025):
```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],
    cultural_values: [u8; 3],
    belief: u8,  // M37: inherited from parent
    parent_id: u32,  // M39: stable agent_id of biological parent
}
```
with:
```rust
struct BirthInfo {
    region: u16,
    civ: u8,
    parent_loyalty: f32,
    personality: [f32; 3],
    cultural_values: [u8; 3],
    belief: u8,
    birth_parent_id: u32,   // M39: stable agent_id of biological parent
    other_parent_id: u32,   // M57a: spouse of birth parent at birth time, or PARENT_NONE
}
```

- [ ] **Step 2: Update birth generation — capture both parents**

In `tick_region_demographics()` (tick.rs:1168-1180), replace the BirthInfo construction:
```rust
                pending.births.push(BirthInfo {
                    region: region_id as u16,
                    civ: civ_id,
                    parent_loyalty: pool.loyalty(slot),
                    personality,
                    cultural_values: [
                        pool.cultural_value_0[slot],
                        pool.cultural_value_1[slot],
                        pool.cultural_value_2[slot],
                    ],
                    belief: pool.beliefs[slot],  // M37: read in parallel phase
                    parent_id: pool.ids[slot],  // M39: slot IS the parent in this loop
                });
```
with:
```rust
                // M57a: Capture spouse at birth-generation time.
                // Spouse may die later in the same tick — child should still record that parent.
                let birth_parent_id = pool.ids[slot];
                let other_parent_id = crate::relationships::get_spouse_id(pool, slot)
                    .unwrap_or(crate::agent::PARENT_NONE);
                pending.births.push(BirthInfo {
                    region: region_id as u16,
                    civ: civ_id,
                    parent_loyalty: pool.loyalty(slot),
                    personality,
                    cultural_values: [
                        pool.cultural_value_0[slot],
                        pool.cultural_value_1[slot],
                        pool.cultural_value_2[slot],
                    ],
                    belief: pool.beliefs[slot],
                    birth_parent_id,
                    other_parent_id,
                });
```

- [ ] **Step 3: Widen the reverse index to both parent slots**

Replace the reverse index construction (tick.rs:456-466):
```rust
    // Build parent_id → Vec<child_slot> reverse index for DeathOfKin
    let mut parent_to_children: std::collections::HashMap<u32, Vec<usize>> =
        std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let parent_id = pool.parent_ids[slot];
            if parent_id != crate::agent::PARENT_NONE {
                parent_to_children.entry(parent_id).or_default().push(slot);
            }
        }
    }
```
with:
```rust
    // Build parent_id → Vec<child_slot> reverse index for DeathOfKin
    // M57a: index under BOTH parent slots for dual-parent inheritance
    let mut parent_to_children: std::collections::HashMap<u32, Vec<usize>> =
        std::collections::HashMap::new();
    for slot in 0..pool.capacity() {
        if pool.is_alive(slot) {
            let p0 = pool.parent_id_0[slot];
            if p0 != crate::agent::PARENT_NONE {
                parent_to_children.entry(p0).or_default().push(slot);
            }
            let p1 = pool.parent_id_1[slot];
            if p1 != crate::agent::PARENT_NONE && p1 != p0 {
                parent_to_children.entry(p1).or_default().push(slot);
            }
        }
    }
```

- [ ] **Step 4: Update parent_pos snapshot to use `birth_parent_id`**

In the parent_pos block (tick.rs:474-486), replace all `birth.parent_id` with `birth.birth_parent_id`.

- [ ] **Step 5: Update birth resolution — set both parent fields + dual kin bonds**

In the births loop (tick.rs:552-619), replace the parent assignment and kin bond section:

Replace `pool.parent_ids[new_slot] = birth.parent_id;` with:
```rust
            pool.parent_id_0[new_slot] = birth.birth_parent_id;
            pool.parent_id_1[new_slot] = birth.other_parent_id;
```

Replace the kin bond block:
```rust
            // M50a: auto-form kin bond between parent and child
            if birth.parent_id != crate::agent::PARENT_NONE {
                if let Some(&parent_slot) = id_to_slot.get(&birth.parent_id) {
                    // Guard: parent may have died and slot reused by earlier birth in same batch.
                    // Check both alive AND id match to detect stale HashMap entries.
                    if pool.alive[parent_slot] && pool.ids[parent_slot] == birth.parent_id {
                        if !crate::relationships::form_kin_bond(pool, parent_slot, new_slot, turn) {
                            kin_bond_failures += 1;
                        }
                    }
                }
            }
```
with:
```rust
            // M50a/M57a: auto-form kin bonds to both parents
            if birth.birth_parent_id != crate::agent::PARENT_NONE {
                if let Some(&parent_slot) = id_to_slot.get(&birth.birth_parent_id) {
                    if pool.alive[parent_slot] && pool.ids[parent_slot] == birth.birth_parent_id {
                        if !crate::relationships::form_kin_bond(pool, parent_slot, new_slot, turn) {
                            kin_bond_failures += 1;
                        }
                    }
                }
            }
            if birth.other_parent_id != crate::agent::PARENT_NONE
                && birth.other_parent_id != birth.birth_parent_id
            {
                if let Some(&parent_slot) = id_to_slot.get(&birth.other_parent_id) {
                    if pool.alive[parent_slot] && pool.ids[parent_slot] == birth.other_parent_id {
                        if !crate::relationships::form_kin_bond(pool, parent_slot, new_slot, turn) {
                            kin_bond_failures += 1;
                        }
                    }
                }
            }
```

Update the spatial placement line:
```rust
                let base = parent_pos.get(&birth.parent_id).copied().unwrap_or((0.5, 0.5));
```
to:
```rust
                let base = parent_pos.get(&birth.birth_parent_id).copied().unwrap_or((0.5, 0.5));
```

- [ ] **Step 6: Update BirthOfKin intent — emit for both parents**

Replace the BirthOfKin block (tick.rs:607-619):
```rust
            // M48: BirthOfKin intent for the parent
            if let Some(&parent_slot) = id_to_slot.get(&birth.parent_id) {
                if pool.alive[parent_slot] && pool.ids[parent_slot] == birth.parent_id {
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: parent_slot,
                        event_type: crate::memory::MemoryEventType::BirthOfKin as u8,
                        source_civ: pool.civ_affinities[parent_slot],
                        intensity: crate::agent::BIRTHOFKIN_DEFAULT_INTENSITY,
                        is_legacy: false,
                        decay_factor_override: None,
                    });
                }
            }
```
with:
```rust
            // M48/M57a: BirthOfKin intent for both parents
            // Duplicate defense: if both slots hold the same parent, emit once (skip second iteration)
            let parents_for_intent: [u32; 2] = [birth.birth_parent_id, birth.other_parent_id];
            for (idx, &pid) in parents_for_intent.iter().enumerate() {
                if pid == crate::agent::PARENT_NONE {
                    continue;
                }
                if idx == 1 && pid == parents_for_intent[0] {
                    continue; // same parent in both slots — already emitted
                }
                if let Some(&parent_slot) = id_to_slot.get(&pid) {
                    if pool.alive[parent_slot] && pool.ids[parent_slot] == pid {
                        memory_intents.push(crate::memory::MemoryIntent {
                            agent_slot: parent_slot,
                            event_type: crate::memory::MemoryEventType::BirthOfKin as u8,
                            source_civ: pool.civ_affinities[parent_slot],
                            intensity: crate::agent::BIRTHOFKIN_DEFAULT_INTENSITY,
                            is_legacy: false,
                            decay_factor_override: None,
                        });
                    }
                }
            }
```

- [ ] **Step 7: Fix any remaining `birth.parent_id` references in tick.rs**

Grep for `birth.parent_id` in tick.rs. Every occurrence must become either `birth.birth_parent_id` or `birth.other_parent_id`.

- [ ] **Step 8: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m57a): dual-parent birth path, kin bond widening, reverse index widening"
```

---

## Task 7: MemoryIntent Identity Validation

**Files:**
- Modify: `chronicler-agents/src/memory.rs:72-79` (MemoryIntent), `:182-194` (write_all_memories)
- Modify: `chronicler-agents/src/tick.rs` (all MemoryIntent construction sites)

- [ ] **Step 1: Add `expected_agent_id` to `MemoryIntent`**

Replace (memory.rs:72-79):
```rust
pub struct MemoryIntent {
    pub agent_slot: usize,
    pub event_type: u8,
    pub source_civ: u8,
    pub intensity: i8,
    pub is_legacy: bool,
    pub decay_factor_override: Option<u8>,
}
```
with:
```rust
pub struct MemoryIntent {
    pub agent_slot: usize,
    pub expected_agent_id: u32,  // M57a: identity validation — must match pool.ids[slot] at write time
    pub event_type: u8,
    pub source_civ: u8,
    pub intensity: i8,
    pub is_legacy: bool,
    pub decay_factor_override: Option<u8>,
}
```

- [ ] **Step 2: Add identity check in `write_all_memories()`**

In `write_all_memories()` (memory.rs:182-194), add an identity check after the slot assignment:
```rust
pub fn write_all_memories(pool: &mut AgentPool, intents: &[MemoryIntent], turn: u16) {
    for intent in intents {
        let slot = intent.agent_slot;
        // M57a: Validate target identity — slot may have been reused by a newborn
        if !pool.is_alive(slot) || pool.ids[slot] != intent.expected_agent_id {
            continue;
        }
        let gate = gate_bit_for(intent.event_type);
        if gate != 0 && (pool.memory_gates[slot] & gate) != 0 {
            continue; // gated — skip
        }
        write_single_memory(pool, intent, turn);
        if gate != 0 {
            pool.memory_gates[slot] |= gate;
        }
    }
}
```

- [ ] **Step 3: Fix all MemoryIntent construction sites in tick.rs**

Every `MemoryIntent { agent_slot: ..., ... }` in tick.rs must now include `expected_agent_id`. Search for `MemoryIntent {` and add the field. The value is `pool.ids[slot]` where `slot` is the `agent_slot`.

For the BirthOfKin intents added in Task 6, add:
```rust
expected_agent_id: pool.ids[parent_slot],
```

For DeathOfKin intents, add `expected_agent_id: pool.ids[child_slot]`.
For all other memory intents (Battle, Famine, etc.), add `expected_agent_id: pool.ids[slot]`.

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/memory.rs chronicler-agents/src/tick.rs
git commit -m "fix(m57a): MemoryIntent identity validation prevents stale-slot memory delivery"
```

---

## Task 8: Marriage Formation — `marriage_scan()`

**Files:**
- Modify: `chronicler-agents/src/formation.rs` (add marriage types, `marriage_pair_hash()`, `marriage_scan()`, stats fields on `FormationStats`)
- Modify: `chronicler-agents/src/tick.rs` (wire `marriage_scan()` before `formation_scan()`)

- [ ] **Step 1: Reuse existing hashing helpers without widening visibility unless needed**

If `marriage_scan()` lives in the same module as `mix_hash()`, keep `mix_hash()` private. Only widen its visibility if another module actually needs it for deterministic ordering.

- [ ] **Step 2: Add marriage stats fields to `FormationStats`**

In the `FormationStats` struct (formation.rs:357), add after the existing fields:
```rust
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
```

- [ ] **Step 3: Add `MarriageCandidate` struct and `marriage_pair_hash()`**

Add before `marriage_scan()`:
```rust
// ---------------------------------------------------------------------------
// M57a: Marriage formation
// ---------------------------------------------------------------------------

/// A scored candidate pair for marriage matching.
struct MarriageCandidate {
    slot_a: usize,
    slot_b: usize,
    score: f32,
    hash: u64,  // deterministic tie-break
}

/// Deterministic pair hash for marriage tie-breaking.
/// Uses both agent IDs in canonical order (min, max) so (a,b) == (b,a).
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

/// Check if two agents share a parent (sibling/half-sibling incest gate).
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

/// Check if one agent is the parent of the other (direct parent-child incest gate).
fn is_parent_child(pool: &AgentPool, a: usize, b: usize) -> bool {
    let id_a = pool.ids[a];
    let id_b = pool.ids[b];
    pool.has_parent(a, id_b) || pool.has_parent(b, id_a)
}

/// Compute marriage compatibility score between two agents.
fn marriage_score(pool: &AgentPool, a: usize, b: usize) -> f32 {
    use crate::agent::*;
    let mut score: f32 = 0.0;

    // Same civ bonus
    if pool.civ_affinities[a] == pool.civ_affinities[b] {
        score += MARRIAGE_SAME_CIV_BONUS;
    }

    // Same belief bonus / cross-faith penalty
    let ba = pool.beliefs[a];
    let bb = pool.beliefs[b];
    if ba == bb && ba != BELIEF_NONE {
        score += MARRIAGE_SAME_BELIEF_BONUS;
    } else if ba != BELIEF_NONE && bb != BELIEF_NONE && ba != bb {
        score -= MARRIAGE_CROSS_FAITH_PENALTY;
    }

    // Cultural value proximity: bonus per matching value (max 3 slots)
    let cv_a = [pool.cultural_value_0[a], pool.cultural_value_1[a], pool.cultural_value_2[a]];
    let cv_b = [pool.cultural_value_0[b], pool.cultural_value_1[b], pool.cultural_value_2[b]];
    for i in 0..3 {
        if cv_a[i] == cv_b[i] && cv_a[i] != CULTURAL_VALUE_EMPTY {
            score += MARRIAGE_CULTURE_MATCH_BONUS;
        }
    }

    // Spatial closeness bonus (inverse distance, capped)
    let dx = pool.x[a] - pool.x[b];
    let dy = pool.y[a] - pool.y[b];
    let dist = (dx * dx + dy * dy).sqrt();
    if dist > 0.001 {
        let closeness = (1.0 / (1.0 + dist * 4.0)).min(MARRIAGE_CLOSENESS_CAP);
        score += closeness;
    } else {
        score += MARRIAGE_CLOSENESS_CAP;
    }

    score
}
```

- [ ] **Step 4: Implement `marriage_scan()`**

Implement `marriage_scan()` as a separate pass in `formation.rs` with this shape:

```rust
pub fn marriage_scan(
    pool: &mut AgentPool,
    regions: &[RegionState],
    signals: &TickSignals,
    turn: u32,
    alive_slots: &[usize],
) -> FormationStats
```

Implementation checklist:

1. Bucket the provided `alive_slots` by region, following the same region cadence rule as the spec:
   `region_idx % MARRIAGE_CADENCE == turn % MARRIAGE_CADENCE`.
2. Treat `alive_slots` here as the post-demographics alive list from `tick_agents()`, not the tick-start snapshot.
3. Filter eligible agents to:
   - `pool.ages[slot] >= MARRIAGE_MIN_AGE`
   - no existing `Marriage` bond via `get_spouse_id(pool, slot).is_none()`
4. Enumerate local pairs inside each on-cadence region bucket.
5. Reject pairs by:
   - distance (`MARRIAGE_RADIUS`)
   - incest (`is_parent_child()` or `shares_parent()` using both parent slots)
   - cross-civ war/hostility proxy: for `civ_a != civ_b`, reject if either civ's `CivSignals.is_at_war` is true
6. Score remaining pairs with:
   - same-civ bonus
   - same-belief bonus only when both beliefs are non-`BELIEF_NONE`
   - cross-faith penalty only when both beliefs are non-`BELIEF_NONE` and differ
   - cultural-value match bonuses
   - capped spatial closeness bonus
7. Create `MarriageCandidate { slot_a, slot_b, score, hash }` using `marriage_pair_hash()` as the deterministic tie-break.
8. Sort by descending score, then ascending pair hash.
9. Greedily accept only disjoint pairs, committing via `upsert_symmetric(... BondType::Marriage ...)`.
10. Populate only the marriage-related fields on `FormationStats`; the general formation counters remain at their default values in this pass.
11. For `same_faith_marriages` / `cross_faith_marriages`, only count marriages where both beliefs are non-`BELIEF_NONE`.

Implementation notes:

- Do **not** reference a nonexistent `RegionState.hostile_pairs`.
- Use `signals: &TickSignals` to read `CivSignals.is_at_war`.
- Keep the pass deterministic without consuming `MARRIAGE_STREAM_OFFSET`; the offset stays reserved in `agent.rs` for future use.

- [ ] **Step 5: Wire `marriage_scan()` in `tick_agents()`**

In `tick_agents()` (tick.rs), find where `formation_scan()` is called. Before that call, add:

```rust
    // M57a: Marriage scan runs BEFORE general formation
    let marriage_stats = crate::formation::marriage_scan(pool, regions, signals, turn, &post_alive);
```

After `formation_scan()` returns, merge the marriage stats:
```rust
    formation_stats.marriages_formed = marriage_stats.marriages_formed;
    formation_stats.marriage_pairs_evaluated = marriage_stats.marriage_pairs_evaluated;
    formation_stats.marriage_pairs_rejected_hostile = marriage_stats.marriage_pairs_rejected_hostile;
    formation_stats.marriage_pairs_rejected_incest = marriage_stats.marriage_pairs_rejected_incest;
    formation_stats.marriage_pairs_rejected_distance = marriage_stats.marriage_pairs_rejected_distance;
    formation_stats.cross_civ_marriages = marriage_stats.cross_civ_marriages;
    formation_stats.same_civ_marriages = marriage_stats.same_civ_marriages;
    formation_stats.cross_faith_marriages = marriage_stats.cross_faith_marriages;
    formation_stats.same_faith_marriages = marriage_stats.same_faith_marriages;
```

- [ ] **Step 6: Add marriage stats to `get_relationship_stats()`**

In `ffi.rs get_relationship_stats()` (around line 2839), after the existing formation stats inserts, add:

```rust
        // M57a: Marriage formation stats
        stats.insert("marriages_formed".into(), self.formation_stats.marriages_formed as f64);
        stats.insert("marriage_pairs_evaluated".into(), self.formation_stats.marriage_pairs_evaluated as f64);
        stats.insert("marriage_pairs_rejected_hostile".into(), self.formation_stats.marriage_pairs_rejected_hostile as f64);
        stats.insert("marriage_pairs_rejected_incest".into(), self.formation_stats.marriage_pairs_rejected_incest as f64);
        stats.insert("marriage_pairs_rejected_distance".into(), self.formation_stats.marriage_pairs_rejected_distance as f64);
        stats.insert("cross_civ_marriages".into(), self.formation_stats.cross_civ_marriages as f64);
        stats.insert("same_civ_marriages".into(), self.formation_stats.same_civ_marriages as f64);
        stats.insert("cross_faith_marriages".into(), self.formation_stats.cross_faith_marriages as f64);
        stats.insert("same_faith_marriages".into(), self.formation_stats.same_faith_marriages as f64);
```

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/formation.rs chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m57a): marriage_scan with scored greedy matching and diagnostics"
```

---

## Task 9: Rust Integration Tests — `test_m57a_marriage.rs`

**Files:**
- Create: `chronicler-agents/tests/test_m57a_marriage.rs`

- [ ] **Step 1: Write the integration test file**

Create `chronicler-agents/tests/test_m57a_marriage.rs`. The implementation agent should write tests covering:

1. **Determinism:** Run `marriage_scan()` twice with identical pool state → identical results.
2. **Exclusivity:** After `marriage_scan()`, no agent has two Marriage bonds. Agents with existing Marriage bonds are not re-matched.
3. **Age gate:** Agents below `MARRIAGE_MIN_AGE` are not matched.
4. **Distance gate:** Agents beyond `MARRIAGE_RADIUS` are not matched.
5. **Incest — parent-child:** If agent A is in agent B's `parent_id_0` or `parent_id_1`, they are not matched.
6. **Incest — siblings:** If agents share any non-`PARENT_NONE` parent across either slot, they are not matched.
7. **Scored greedy:** Given 3 agents A, B, C in range where A-B scores higher than A-C, A matches B (not C).
8. **Cadence:** Only regions where `region_idx % MARRIAGE_CADENCE == turn % MARRIAGE_CADENCE` are processed.
9. **Two-parent FFI round-trip:** Spawn parent agents, form marriage, run birth → child has both `parent_id_0` and `parent_id_1` set → snapshot exports both columns.
10. **Remarriage:** Kill spouse, verify bond removed, run another `marriage_scan()` → survivor can rematch.

Use the existing pool construction pattern from `test_m50b_formation.rs`. Each test should set up a small pool (2-8 agents), run `marriage_scan()`, and assert bond state.

- [ ] **Step 2: Run tests**

Run: `cargo nextest run -p chronicler-agents --test test_m57a_marriage`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/test_m57a_marriage.rs
git commit -m "test(m57a): Rust integration tests for marriage formation and lineage"
```

---

## Task 10: Python Models — `GreatPerson` Schema Migration

**Files:**
- Modify: `src/chronicler/models.py:467` (GreatPerson.parent_id)

- [ ] **Step 1: Update `GreatPerson` model**

In `models.py`, replace:
```python
    parent_id: int = 0
```
with:
```python
    parent_id_0: int = 0
    parent_id_1: int = 0  # M57a: other parent (spouse at birth), 0 = unknown
    lineage_house: int = 0  # M57a: secondary dynasty id for narration, 0 = none
```

Add a helper method to the class:
```python
    def parent_ids(self) -> tuple[int, int]:
        """Return both parent IDs as a tuple."""
        return (self.parent_id_0, self.parent_id_1)
```

- [ ] **Step 2: Grep for all remaining `parent_id` references on GreatPerson**

Run `grep -rn "\.parent_id\b" src/chronicler/ tests/` and fix all references to `.parent_id` that refer to GreatPerson instances. Map each to `.parent_id_0` unless the code explicitly needs both parents.

Key sites:
- `agent_bridge.py:1275` → `parent_id_0=..., parent_id_1=...`
- `dynasties.py:37` → dual-parent logic (Task 12)
- `factions.py:458` → dual-parent dict (Task 13)

For now, just update the model. Other files are handled in their own tasks.

- [ ] **Step 3: Run Python tests to see what breaks**

Run: `pytest tests/ -x --tb=short`
Expected: Some failures from column name changes and GreatPerson field rename. Note them for subsequent tasks.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m57a): GreatPerson dual-parent fields and lineage_house"
```

---

## Task 11: Agent Bridge — Promotions & Snapshot Column Migration

**Files:**
- Modify: `src/chronicler/agent_bridge.py:1209-1290` (_process_promotions), snapshot column reads

- [ ] **Step 1: Update `_process_promotions()`**

In `_process_promotions()` (agent_bridge.py:1225), replace:
```python
            parent_id = batch.column("parent_id")[i].as_py()
```
with:
```python
            parent_id_0 = batch.column("parent_id_0")[i].as_py()
            parent_id_1 = batch.column("parent_id_1")[i].as_py()
```

In the GreatPerson construction (agent_bridge.py:1275), replace:
```python
                parent_id=parent_id,
```
with:
```python
                parent_id_0=parent_id_0,
                parent_id_1=parent_id_1,
```

- [ ] **Step 2: Update any snapshot column reads that reference `parent_id`**

Grep `agent_bridge.py` for `column("parent_id")`. Each occurrence becomes `column("parent_id_0")` or needs a second read for `parent_id_1`.

- [ ] **Step 3: Update stats history passthrough**

In `agent_bridge.py`, find where `get_relationship_stats()` results are stored. The new marriage keys will flow through automatically since they're added to the existing HashMap in Rust.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent_bridge.py -x --tb=short`
Expected: PASS (or note remaining failures for later tasks)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m57a): agent bridge dual-parent column migration"
```

---

## Task 12: Dynasty & Succession — Dual-Parent Resolution

**Files:**
- Modify: `src/chronicler/dynasties.py:30-71` (check_promotion), `:137-160` (compute_dynasty_legitimacy)

- [ ] **Step 1: Update `check_promotion()` for dual-parent dynasty resolution**

Replace `check_promotion()` (dynasties.py:30-71):

```python
    def check_promotion(
        self,
        child: GreatPerson,
        named_agents: dict[int, str],
        gp_map: dict[int, GreatPerson],
    ) -> list[Event]:
        events: list[Event] = []

        # M57a: Resolve dynasty from both parents
        parent_0 = gp_map.get(child.parent_id_0) if child.parent_id_0 in named_agents else None
        parent_1 = gp_map.get(child.parent_id_1) if child.parent_id_1 in named_agents else None

        dynasty_0 = parent_0.dynasty_id if parent_0 else None
        dynasty_1 = parent_1.dynasty_id if parent_1 else None

        # Resolution rule (spec Section 3):
        # 1. Exactly one parent has a dynasty → child takes it
        # 2. Both share the same dynasty → child takes it
        # 3. Both have different dynasties → birth parent's; lineage_house records other
        # 4. Neither → founder logic (if parent is named but no dynasty yet)
        chosen_dynasty = None
        lineage_house = 0

        if dynasty_0 is not None and dynasty_1 is not None:
            if dynasty_0 == dynasty_1:
                chosen_dynasty = dynasty_0
            else:
                chosen_dynasty = dynasty_0  # birth parent's dynasty
                lineage_house = dynasty_1
        elif dynasty_0 is not None:
            chosen_dynasty = dynasty_0
        elif dynasty_1 is not None:
            chosen_dynasty = dynasty_1

        if chosen_dynasty is not None:
            dynasty = self._find(chosen_dynasty)
            dynasty.members.append(child.agent_id)
            child.dynasty_id = chosen_dynasty
            child.lineage_house = lineage_house
            return events

        # Rule 4: Neither parent has a dynasty — found a new one from first named parent
        founder_parent = parent_0 or parent_1
        if founder_parent is None:
            return events

        dynasty = Dynasty(
            dynasty_id=self._next_id,
            founder_id=founder_parent.agent_id,
            founder_name=founder_parent.name,
            civ_id=founder_parent.civilization,
            members=[founder_parent.agent_id, child.agent_id],
            founded_turn=child.born_turn,
        )
        self.dynasties.append(dynasty)
        founder_parent.dynasty_id = self._next_id
        child.dynasty_id = self._next_id
        self._next_id += 1

        events.append(Event(
            turn=child.born_turn,
            event_type="dynasty_founded",
            actors=[founder_parent.name, child.name],
            description=(
                f"The House of {founder_parent.name} is established as {child.name}, "
                f"child of the great {founder_parent.role} {founder_parent.name}, rises to prominence"
            ),
            importance=7,
            source="agent",
        ))
        return events
```

- [ ] **Step 2: Update `compute_dynasty_legitimacy()` for either-parent check**

Replace the direct-heir check (dynasties.py:150-160):
```python
    cand_parent_id = candidate.get("parent_id", 0)
    cand_dynasty_id = candidate.get("dynasty_id")

    # Direct heir: candidate's parent is the current ruler
    if (
        ruler_agent_id is not None
        and ruler_agent_id != 0
        and cand_parent_id != 0
        and cand_parent_id == ruler_agent_id
    ):
        return LEGITIMACY_DIRECT_HEIR
```
with:
```python
    cand_parent_ids = (candidate.get("parent_id_0", 0), candidate.get("parent_id_1", 0))
    cand_dynasty_id = candidate.get("dynasty_id")

    # M57a: Direct heir — ruler is EITHER parent
    if ruler_agent_id is not None and ruler_agent_id != 0:
        if ruler_agent_id in cand_parent_ids and ruler_agent_id != 0:
            return LEGITIMACY_DIRECT_HEIR
```

- [ ] **Step 3: Run dynasty tests**

Run: `pytest tests/test_dynasties.py -x -v`
Expected: Some failures from field rename. Fix test fixtures to use `parent_id_0`/`parent_id_1`.

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/dynasties.py
git commit -m "feat(m57a): dual-parent dynasty resolution and either-parent legitimacy"
```

---

## Task 13: Factions — Succession Candidate Dual-Parent

**Files:**
- Modify: `src/chronicler/factions.py:455-461` (candidate dict)

- [ ] **Step 1: Update succession candidate dict**

Replace (factions.py:458):
```python
        "parent_id": gp.parent_id,
```
with:
```python
        "parent_id_0": gp.parent_id_0,
        "parent_id_1": gp.parent_id_1,
```

- [ ] **Step 2: Grep for other `parent_id` references in factions.py**

Run: `grep -n "parent_id" src/chronicler/factions.py`
Fix any remaining singular references.

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -x --tb=short`
Expected: Closer to PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/factions.py
git commit -m "feat(m57a): succession candidate dict dual-parent fields"
```

---

## Task 14: Narrative & Events — Marriage Formed + Lineage Context

**Files:**
- Modify: `src/chronicler/agent_bridge.py` (promotion/materialization seam for lineage-house display context, if needed)
- Modify: `src/chronicler/simulation.py:1631-1645` (rivalry_formed block)
- Modify: `src/chronicler/narrative.py` (lineage house context)
- Modify: `src/chronicler/relationships.py` (deprecation comment)

- [ ] **Step 1: Add `marriage_formed` event wiring in `simulation.py`**

Find the `rivalry_formed` block (simulation.py:1631-1645). After it, add an analogous block for marriage:

```python
        # M57a: Marriage formation events for named characters
        REL_MARRIAGE = 2
        for edge in new_edges:
            if edge[2] == REL_MARRIAGE and edge[3] == world.turn:
                gp_a = gp_by_id.get(edge[0])
                gp_b = gp_by_id.get(edge[1])
                if gp_a and gp_b:
                    turn_events.append(Event(
                        turn=world.turn, event_type="marriage_formed",
                        actors=[gp_a.name, gp_b.name],
                        description=f"A marriage is forged between {gp_a.name} and {gp_b.name}.",
                        importance=6,
                        source="agent",
                    ))
```

Mirror the `rivalry_formed` plumbing, but keep the event character-centered: use great-person names as actors, and preserve whatever edge deduping rule the existing new-edge path already relies on for symmetric bonds.

- [ ] **Step 2: Add lineage house resolution at the promotion/materialization seam, then surface it in narrative context**

Do **not** instantiate or import a fresh `DynastyRegistry` inside `narrative.py`.

Instead:

1. At a seam that already has access to the live dynasty registry (prefer `AgentBridge._process_promotions()` and/or the simulation-side context assembly that already uses `agent_bridge.dynasty_registry`), resolve `gp.lineage_house` to a dynasty/house display name.
2. Pass that resolved context into the narrator-facing GreatPerson context.
3. In `narrative.py`, only consume the resolved lineage text/name and append phrasing like:
   - `"with lineage ties to the House of X"`

Keep the language parent-neutral. Do not introduce `mother` / `father` wording, because the model tracks parent slots, not gendered parent roles.

- [ ] **Step 3: Add deprecation comment on `check_marriage_formation()` in relationships.py**

In `relationships.py`, find `check_marriage_formation()` (around line 162). Add a deprecation comment:

```python
def check_marriage_formation(...):
    """DEPRECATED (M57a): Marriage formation is now Rust-native via marriage_scan()
    in formation.rs. This Python-side helper is frozen — do not extend.
    Retained for test compatibility only."""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -x --tb=short`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py src/chronicler/simulation.py src/chronicler/narrative.py src/chronicler/relationships.py
git commit -m "feat(m57a): marriage_formed events, lineage narration, legacy code freeze"
```

---

## Task 15: Python Tests — Dynasty, Legitimacy, Schema

**Files:**
- Modify: `tests/test_dynasties.py`, `tests/test_m51_regnal.py`, `tests/test_agent_bridge.py`, `tests/test_relationships.py` (or the existing `--agents=off` smoke-test file if that is a better fit)

- [ ] **Step 1: Update `test_dynasties.py` for dual-parent resolution**

Add tests covering the four dynasty resolution rules:
1. Single parent with dynasty → child inherits it
2. Two parents, same dynasty → child inherits it, `lineage_house` = 0
3. Two parents, different dynasties → child gets birth parent's, `lineage_house` = other's
4. Neither parent in dynasty → founder logic

The implementation agent should read the existing test patterns in `test_dynasties.py` and add analogous tests using `parent_id_0`/`parent_id_1` on `GreatPerson` fixtures.

- [ ] **Step 2: Update `test_m51_regnal.py` for either-parent legitimacy**

Add tests:
1. Ruler as `parent_id_0` → `LEGITIMACY_DIRECT_HEIR` returned
2. Ruler as `parent_id_1` → `LEGITIMACY_DIRECT_HEIR` returned
3. Ruler in neither slot → no direct-heir bonus

Use the existing `compute_dynasty_legitimacy()` test pattern.

- [ ] **Step 3: Add `--agents=off` smoke test**

Prefer extending the existing aggregate-mode / empty-relationships coverage in `tests/test_relationships.py` (or whichever current `--agents=off` smoke-test file is the closest fit). Add a test that runs a short simulation with `--agents=off` and verifies:
- No `marriage_formed` events emitted
- No marriage-derived relationship surface appears in aggregate mode
- Any emitted/promoted records keep `parent_id_1 == 0`
- Any emitted/promoted records keep `lineage_house == 0`

- [ ] **Step 4: Fix any broken test fixtures**

All tests that construct `GreatPerson(parent_id=X)` must become `GreatPerson(parent_id_0=X)`. Grep `tests/` for `parent_id=` and update.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test(m57a): dual-parent dynasty, legitimacy, and schema migration tests"
```

---

## Task 16: Full Integration Verification + Determinism

**Files:**
- Extend: `chronicler-agents/tests/determinism.rs`

- [ ] **Step 1: Add marriage determinism test**

In `determinism.rs`, add a test that runs a multi-turn simulation twice with identical seed and verifies:
- Same marriages formed
- Same `parent_id_0`/`parent_id_1` assignments

Follow the existing determinism test pattern in that file, including a thread-count variant if that file already checks multi-thread determinism. Dynasty assignment remains Python-owned and should be covered by the Python test suite, not the Rust determinism test.

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 3: Run full Python test suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Run a short smoke-test simulation**

Run: `python -m chronicler.main --seed 42 --turns 50 --agents hybrid`
Expected: Runs to completion without errors. Check output for marriage-related stats.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/tests/determinism.rs
git commit -m "test(m57a): determinism verification for marriage formation"
```

---

## Task 17: Progress Doc Update

**Files:**
- Modify: `docs/superpowers/progress/phase-6-progress.md`

- [ ] **Step 1: Update progress doc**

Add M57a status to the progress doc:
- Mark as implemented
- Note any gotchas discovered during implementation
- Note that 200-seed regression is pending

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m57a): update progress doc with implementation status"
```

---

## Summary

| Task | Description | Est. Complexity |
|------|------------|-----------------|
| 1 | Rust constants + stream offset | Low |
| 2 | Pool storage migration | Medium |
| 3 | FFI schema migration | Medium |
| 4 | Named character registry | Low |
| 5 | Relationship helpers | Low |
| 6 | Tick birth path + kin widening | High |
| 7 | MemoryIntent identity validation | Medium |
| 8 | Marriage formation scan | High |
| 9 | Rust integration tests | Medium |
| 10 | Python GreatPerson model | Low |
| 11 | Agent bridge column migration | Medium |
| 12 | Dynasty dual-parent resolution | Medium |
| 13 | Factions succession candidate | Low |
| 14 | Narrative + events + deprecation | Medium |
| 15 | Python tests | Medium |
| 16 | Full integration + determinism | Medium |
| 17 | Progress doc update | Low |

**Dependencies:** Tasks 1-4 must land first (they establish the storage foundation). Task 5 before Task 8 (marriage_scan needs get_spouse_id). Task 6 before Task 9 (birth path needed for FFI round-trip tests). Tasks 10-13 can proceed in parallel once the Rust side compiles. Task 14-15 after model changes land. Task 16-17 last.
