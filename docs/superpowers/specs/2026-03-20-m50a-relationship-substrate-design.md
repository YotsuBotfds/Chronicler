# M50a: Relationship Substrate — Design Spec

> **Status:** Draft
> **Date:** 2026-03-20
> **Depends on:** M48 (Agent Memory, merged), M40 (Social Networks, merged), M49 (Needs System, in-flight)
> **Feeds:** M50b (Relationship Emergence & Cohorts), M51 (Multi-Generational Memory), M57 (Marriage & Households)

---

## 1. Goal

Give every agent a Rust-owned, per-agent relationship store with directed sentiment drift and protected structural ties. M40's named-character social graph becomes a read-only projection over this store instead of a parallel truth source.

**Scope rule:** M50a owns persistence and deterministic thermodynamics. M50b owns interpretation (similarity-gated formation, triadic closure, synthesis-triggered reassessment, cohort emergence).

---

## 2. Storage Model

### 2.1 SoA Fields on AgentPool

Parallels the M48 memory layout (`Vec<[T; SLOTS]>` pattern):

```rust
rel_target_ids:   Vec<[u32; 8]>   // target agent_id per slot (0 = empty sentinel)
rel_sentiments:   Vec<[i8; 8]>    // -128 (hate) to +127 (love)
rel_bond_types:   Vec<[u8; 8]>    // BondType enum (255 = empty sentinel)
rel_formed_turns: Vec<[u16; 8]>   // turn of formation
rel_count:        Vec<u8>         // occupied slot count (0-8)
```

65 bytes/agent. At 50K agents = 3.25MB.

### 2.2 BondType Enum

Values 0-4 match M40's `RelationshipType` enum exactly, eliminating translation for overlapping types:

```rust
#[repr(u8)]
pub enum BondType {
    // --- Values 0-4 match M40 RelationshipType ---
    Mentor        = 0,   // asymmetric (src = mentor, dst = apprentice)
    Rival         = 1,
    Marriage      = 2,   // reserved, not used until M57
    ExileBond     = 3,
    CoReligionist = 4,
    // --- New types with no M40 equivalent ---
    Kin           = 5,
    Friend        = 6,
    Grudge        = 7,
}
```

**M40 compatibility:** For bond types 0-4, the raw `u8` is identical to M40's `RelationshipType`. The projection and shim need no translation for these values. Types 5-7 are new and excluded from the legacy projection.

### 2.3 Valence Classification

```rust
fn is_positive_valence(bond_type: u8) -> bool {
    matches!(bond_type, 0 | 2 | 3 | 4 | 5 | 6)
    // Mentor, Marriage, ExileBond, CoReligionist, Kin, Friend
}
// Rival (1) and Grudge (7) are negative-valence.
```

### 2.4 Asymmetry Classification

```rust
fn is_asymmetric(bond_type: u8) -> bool {
    matches!(bond_type, 0)  // Mentor only
}
// All other types are symmetric (stored as two directed entries with same bond_type).
// Mentor is stored as a single directed entry (src=mentor, dst=apprentice).
```

### 2.4 Occupancy Semantics

- **`rel_count` is the sole authoritative occupancy signal.** Slots `[0..rel_count)` are valid; `[rel_count..8)` are don't-care.
- **Packed-prefix invariant:** Occupied relationships always live in `[0..rel_count)`. Removal uses swap-remove from the last occupied slot (swap target with `[rel_count - 1]`, decrement `rel_count`). No holes.
- **Sentinel hygiene:** Spawn initializes `rel_bond_types` to `[255; 8]` (not zero — avoids false Kin at `bond_type=0`). After swap-remove, old tail slot is reset to sentinels (`target_id=0`, `bond_type=255`, `sentiment=0`, `formed_turn=0`).

### 2.5 Multiplicity

Same target can appear in multiple slots with different bond types. A parent can also be a mentor. A rival can also be a co-religionist. The logical key is `(target_id, bond_type)`.

- `Upsert` with an existing `(target_id, bond_type)` updates sentiment in place (does not allocate a new slot).
- Duplicate `(target_id, bond_type)` pairs are prevented by the upsert-in-place rule.

### 2.6 Self-Bond Prohibition

All upsert paths enforce `target_id != src_agent_id`. Ops violating this are rejected.

### 2.7 Helper Functions

New `relationships.rs` module:

| Function | Signature | Purpose |
|----------|-----------|---------|
| `find_relationship` | `(pool, slot, target_id, bond_type) -> Option<usize>` | Compound-key slot lookup |
| `read_rel` | `(pool, slot, rel_idx) -> (u32, i8, u8, u16)` | Read one slot |
| `write_rel` | `(pool, slot, rel_idx, target_id, sentiment, bond_type, formed_turn)` | Write one slot |
| `find_evictable` | `(pool, slot) -> Option<usize>` | Weakest non-protected slot; lowest index on ties |
| `is_protected` | `(bond_type) -> bool` | M50a: Kin (5) only |
| `is_positive_valence` | `(bond_type) -> bool` | Valence classification |
| `is_asymmetric` | `(bond_type) -> bool` | Mentor (0) only |
| `is_symmetric` | `(bond_type) -> bool` | All types except Mentor |

---

## 3. Protection and Eviction

### 3.1 Protection Rule

Protection is a property of the bond type, not a per-slot flag. Derived from `is_protected(bond_type)`:

- **M50a:** Only `Kin` is protected.
- **M57:** `Marriage` joins the protected set. No storage layout change needed.

### 3.2 Eviction Rules

1. Updates to an existing bond always succeed in place.
2. New non-protected bonds may evict only non-protected bonds.
3. `find_evictable()` returns the slot with weakest absolute sentiment among non-protected bonds. Deterministic tie-break: lowest slot index.
4. If all 8 slots are protected, new social bonds fail silently.
5. `UpsertSymmetric` creates fail atomically: if either side has no admissible slot, neither side is written. Each side can evict a different weak tie, but the pair write either fully commits or fully fails.

---

## 4. Op Interface and Batched Mutation

### 4.1 RelationshipOp Variants

```
UpsertDirected  { src, dst, bond_type, sentiment, formed_turn }
UpsertSymmetric { a, b, bond_type, sentiment, formed_turn }
RemoveDirected  { src, dst, bond_type }
RemoveSymmetric { a, b, bond_type }
```

### 4.2 Batch Delivery

One Arrow RecordBatch per turn. Schema:

| Column | Type | Notes |
|--------|------|-------|
| `op_type` | u8 | 0=UpsertDirected, 1=UpsertSymmetric, 2=RemoveDirected, 3=RemoveSymmetric |
| `agent_a` | u32 | src for directed, first agent for symmetric |
| `agent_b` | u32 | dst for directed, second agent for symmetric |
| `bond_type` | u8 | BondType enum value |
| `sentiment` | i8 | Initial sentiment (ignored for Remove ops) |
| `formed_turn` | u16 | Formation turn (ignored for Remove ops) |

### 4.3 FFI Method

`apply_relationship_ops(batch: RecordBatch)` on `AgentSimulator`. Processes ops sequentially in batch order (deterministic).

### 4.4 Upsert Semantics

- If `(src, dst, bond_type)` exists → update sentiment in place. **`formed_turn` is preserved** (not refreshed). This protects the narrator's "since turn X" behavior.
- If not → find empty slot (`rel_count < 8`) or `find_evictable()`. If no admissible slot, op fails silently (debug log).
- `UpsertSymmetric` → atomic: resolve both sides first, commit both or neither.

### 4.5 Remove Semantics

- Find `(src, dst, bond_type)` → swap-remove + clear tail sentinel. If not found, no-op.
- `RemoveSymmetric` → remove both directions independently (one missing doesn't block the other).

### 4.6 Invalid-Op Guards

Skip ops where:
- Either `agent_id` is dead or not found in pool.
- `bond_type` is unknown (>7 or 255).
- `UpsertSymmetric` used with an asymmetric type (Mentor). Kin uses two directed writes in Rust birth path, not `UpsertSymmetric`.
- `target_id == src_agent_id` (self-bond).

Debug log on all skips.

### 4.7 Batch Ordering

Batch order is authoritative. Same-batch conflicts resolve by order — last op wins. `Upsert→Remove` deletes; `Remove→Upsert` recreates.

### 4.8 agent_id → slot Resolution

No reverse index in M50a. Linear scan per op. The batch is small (M40 produces ~50-500 ops/turn for named characters). Acceptable at 50K agents. If M50b grows the batch, add a `HashMap<u32, usize>` — the interface doesn't change.

---

## 5. Kin Auto-Formation (Rust-Native)

### 5.1 Scope

Only direct parent-child kin bonds auto-form in Rust. No sibling inference. No other bond types. This is the only Rust-native formation path in M50a.

### 5.2 Mechanism

In `demographics.rs` birth handling, after setting `parent_id`:

```rust
relationships::form_kin_bond(pool, parent_slot, child_slot, turn);
```

Writes two directed entries:
- Parent → child: sentiment `KIN_INITIAL_PARENT` `[CALIBRATE]` (~+60)
- Child → parent: sentiment `KIN_INITIAL_CHILD` `[CALIBRATE]` (~+40)

Uses standard slot allocation with protection/eviction rules.

### 5.3 Failure Handling

If the parent has 8 protected slots (extreme edge case), the parent→child bond fails. Increments `kin_bond_failures: u32` counter on `AgentSimulator` — observable for diagnostics, operationally a no-op (does not panic or retry).

---

## 6. Sentiment Drift (Per-Tick)

### 6.1 Placement

Phase 0.8 in `tick.rs`, after needs update (0.75), before satisfaction (1.0). Newborn kin bonds (from demographics at phase 5.0) start drifting next tick.

### 6.2 Algorithm

For each agent, for each occupied slot `[0..rel_count)`:

```
1. Resolve target_id → target_slot via per-pass HashMap<u32, usize>
   (built once at start of drift, O(N) build, O(1) lookup per relationship)
2. co_located = pool.regions[agent_slot] == pool.regions[target_slot]
3. valence = is_positive_valence(bond_type)
4. Widen sentiment to i16 for arithmetic

if co_located:
    if valence:
        // positive bond, same region → strengthen toward +127
        drift = POSITIVE_COLOC_DRIFT
        if sentiment > STRONG_TIE_THRESHOLD: drift *= STRONG_TIE_DRIFT_FACTOR
        sentiment = min(sentiment + drift, 127)
    else:
        // negative bond, same region → deepen toward -128
        sentiment = max(sentiment - NEGATIVE_COLOC_DRIFT, -128)
else:
    // separated → decay toward 0
    if sentiment > 0:
        sentiment = max(sentiment - POSITIVE_SEPARATION_DECAY, 0)
    elif sentiment < 0:
        // negative decays 3-5x slower
        if turn % NEGATIVE_DECAY_CADENCE == 0:
            sentiment = min(sentiment + 1, 0)

5. Clamp back to i8 range [-128, 127]
```

### 6.3 Key Properties

- **Dead targets:** Target not found or `!alive` → sentiment decays under separation rules. Slot is NOT auto-removed — Python dissolution logic handles cleanup via `RemoveDirected` ops.
- **Protected bonds drift identically** to unprotected. Protection only affects eviction. You can resent your parent.
- **No RNG.** Drift is deterministic from state — no probability rolls in M50a.
- **All constants `[CALIBRATE]` for M53.**

### 6.4 Constants

| Constant | Domain | Initial | Notes |
|----------|--------|---------|-------|
| `KIN_INITIAL_PARENT` | Birth | +60 | Parent→child starting sentiment |
| `KIN_INITIAL_CHILD` | Birth | +40 | Child→parent starting sentiment |
| `POSITIVE_COLOC_DRIFT` | Drift | 1 | Per-tick positive co-located drift |
| `NEGATIVE_COLOC_DRIFT` | Drift | 1 | Per-tick negative co-located drift |
| `POSITIVE_SEPARATION_DECAY` | Drift | 1 | Per-tick positive separation decay |
| `NEGATIVE_DECAY_CADENCE` | Drift | 4 | Ticks between negative decay steps |
| `STRONG_TIE_THRESHOLD` | Drift | 100 | Diminishing returns threshold |
| `STRONG_TIE_DRIFT_FACTOR` | Drift | 0.5 | Drift multiplier above threshold |

8 constants. All `[CALIBRATE]` for M53.

---

## 7. M40 Compatibility Layer

### 7.1 Principle

M40's Python-side formation logic (`relationships.py`) and narration pipeline keep working. The Rust `SocialGraph` struct stops being authoritative immediately. One source of truth from day one.

### 7.2 `get_social_edges()` → Projection

Reimplemented to scan the per-agent store for named characters, derived internally from the simulator's named-character registry.

Returns Arrow RecordBatch with the **same schema as today**: `[agent_a: u32, agent_b: u32, relationship: u8, formed_turn: u16]`.

**Bond type mapping** (M50a BondType → M40 RelationshipType):

| M50a BondType | M40 RelationshipType | Projected? | Translation |
|---------------|---------------------|------------|-------------|
| Mentor (0) | Mentor (0) | Yes | Identity |
| Rival (1) | Rival (1) | Yes | Identity |
| Marriage (2) | Marriage (2) | Yes | Identity |
| ExileBond (3) | ExileBond (3) | Yes | Identity |
| CoReligionist (4) | CoReligionist (4) | Yes | Identity |
| Kin (5) | — | **No** (excluded) | N/A |
| Friend (6) | — | **No** (excluded) | N/A |
| Grudge (7) | — | **No** (excluded) | N/A |

**No enum translation needed.** Types 0-4 share identical `u8` values between BondType and RelationshipType. Types 5-7 are new and excluded from projection.

**Multi-bond pairs:** If agent A has both `(A→B, Rival)` and `(A→B, CoReligionist)`, both appear as separate rows.

**Directionality:** Mentor emits one row `(mentor_id, apprentice_id, 0, turn)`. Symmetric types emit one row per pair with `a < b` convention — only emit from the side where `src < dst` to avoid duplicates.

**`formed_turn`:** Read from the lower-id side (`src < dst`). `UpsertSymmetric` writes identical `formed_turn` to both sides at creation.

### 7.3 `replace_social_edges()` → Compatibility Shim

Temporarily survives as a translation layer:

1. Reads current projected state for named characters via `get_social_edges()`.
2. Diffs against incoming Arrow batch using compound key `(agent_a, agent_b, relationship_type)`.
3. Converts delta into `relationship_ops` using per-bond-type dispatch:

| M40 RelationshipType | Op for new edges | Op for removed edges |
|---------------------|------------------|---------------------|
| Mentor (0) | `UpsertDirected(mentor→apprentice)` | `RemoveDirected(mentor→apprentice)` |
| Rival (1) | `UpsertSymmetric` | `RemoveSymmetric` |
| Marriage (2) | `UpsertSymmetric` | `RemoveSymmetric` |
| ExileBond (3) | `UpsertSymmetric` | `RemoveSymmetric` |
| CoReligionist (4) | `UpsertSymmetric` | `RemoveSymmetric` |

4. Applies ops via `apply_relationship_ops()`.

**No enum translation needed for types 0-4.** BondType values 0-4 match M40 RelationshipType values exactly.

**Mentor is single-directed:** Only one entry exists in the new store (mentor→apprentice). The apprentice does NOT get a reciprocal slot. This matches M40's single-edge model. `get_agent_relationships()` for the apprentice will not show the mentor bond — consistent with M40 behavior where only `get_social_edges()` (scanning both sides) surfaces the relationship. `get_social_edges()` projection scans all named characters' slots, so it finds the Mentor bond on the mentor's side.

**Guard:** Rejects edges with `agent_ids` not in the named-character registry. Debug log on reject. Explicitly compatibility-only, named-character scope.

**Deprecation target:** Remove once `relationships.py` is migrated to emit ops directly (can happen within M50a or early M50b).

### 7.4 Old SocialGraph

`SocialGraph` struct in `social.rs` stops being authoritative immediately. It is deprecated but alive during the transitional period. Deleted once `replace_social_edges()` shim is removed.

### 7.5 Transitional Mode

Phase 1 (M50a) keeps `replace_social_edges()` alive at the Python layer. The new op interface is exercised only by kin auto-formation in Rust. This is an intentional transitional mode, not the end state.

---

## 8. New FFI Method: `get_agent_relationships()`

```rust
fn get_agent_relationships(&self, agent_id: u32) -> Option<Vec<(u32, i8, u8, u16)>>
```

Returns all occupied relationship slots for one agent as `(target_id, sentiment, bond_type, formed_turn)`. Same pattern as `get_agent_memories()` and `get_agent_needs()`. Linear scan for agent_id. Returns `None` if agent not found or dead.

Used by the per-GP sync loop in `agent_bridge.py` to populate `GreatPerson.agent_bonds` with **all** M50a bond types (including Kin, Friend, Grudge — not limited to legacy M40 types).

---

## 9. Python-Side Changes

### 9.1 agent_bridge.py

- New `apply_relationship_ops(ops: list[dict])` method wrapping `AgentSimulator.apply_relationship_ops()` FFI call.
- `read_social_edges()` still calls `get_social_edges()` — API unchanged, now backed by projection.
- **Relationship sync for active named characters:** In the existing per-GP sync loop (alongside memory and needs sync), call `get_agent_relationships(gp.agent_id)` and populate `gp.agent_bonds`.

### 9.2 simulation.py

No changes to Phase 10 wiring. `form_and_sync_relationships()` keeps calling `replace_social_edges()` through the compatibility shim.

### 9.3 models.py

`GreatPerson` gains:

```python
agent_bonds: Optional[list[dict]] = None
# M50a: synced from Rust via get_agent_relationships() FFI
# Each dict: {"target_id": int, "sentiment": int, "bond_type": int, "formed_turn": int}
# None in aggregate mode
# Named "agent_bonds" to avoid collision with TurnSnapshot.relationships (M40 edge data)
```

### 9.4 narrative.py

Existing relationship rendering works via `read_social_edges()` projection. **No changes.** New bond types (Kin, Friend, Grudge) are invisible to narration until M50b or later widens the renderer.

---

## 10. M49 Interaction — Keep the Proxy

The social need in `needs.rs` currently uses a population-ratio proxy (`region_pop / capacity`). **M50a does NOT swap this to real relationship data.**

**Rationale:** At M50a launch, only kin bonds exist in the new store from Rust-native formation. Social bonds (friend, co-religionist) won't populate until Python formation logic targets the new store or M50b adds Rust-native formation. Swapping the proxy to real relationship count would make social need effectively zero for non-kin agents, causing behavioral regression.

**M50b swap plan:** Once friend/co-religionist bonds populate reliably, blend `real_bond_count` with the population proxy: `social_restore = alpha * bond_factor + (1 - alpha) * pop_factor`, where alpha ramps from 0 → 1 over M50b calibration.

---

## 11. Scope Boundaries

### 11.1 In Scope

- Rust-owned per-agent SoA relationship storage (8 slots, 65 bytes/agent)
- BondType enum with protection derived from type
- Batched `RelationshipOp` Arrow interface (Upsert/Remove, Directed/Symmetric)
- Kin auto-formation in Rust birth path (direct parent-child only)
- Deterministic sentiment drift (bond-type-dependent valence, co-location/separation, asymmetric decay)
- `get_social_edges()` as M40 projection over new store
- `replace_social_edges()` as temporary compatibility shim
- `get_agent_relationships()` FFI for per-GP sync
- GreatPerson.agent_bonds field
- 8 `[CALIBRATE]` constants for M53

### 11.2 Not In Scope

- Region-wide pair scanning or formation intelligence (M50b)
- Shared-memory event boosts (M50b)
- Personality-modulated reactions (M50b)
- Synthesis-budget reassessment (M50b)
- Triadic closure (M50b)
- Diaspora tracking
- Sibling inference (kin = direct parent-child only)
- `replace_social_edges()` migration to direct ops (transitional shim stays)
- `SocialGraph` struct deletion (deprecated but alive)
- M49 social need swap to real relationship data
- Narration widening for new bond types (Kin, Friend, Grudge)

---

## 12. Testing Strategy

### 12.1 Rust Unit Tests (relationships.rs)

- Slot allocation: empty pool, partial fill, full pool
- Eviction: non-protected evicts weakest, protected slots skipped, deterministic tie-break (lowest index)
- Swap-remove compaction: packed-prefix maintained, sentinel hygiene on tail
- Self-bond rejection
- Compound key uniqueness: upsert in-place on duplicate `(target_id, bond_type)`
- `formed_turn` preservation: upsert existing bond does not refresh `formed_turn`
- `UpsertSymmetric` atomicity: one side blocked → neither written
- Multi-bond pairs: same target, different bond types, both persist
- Swap-remove followed by eviction: recently-moved relationship at lower index is evictable if weakest

### 12.2 Rust Unit Tests (drift in tick.rs or relationships.rs)

- Positive-valence co-located: sentiment increases toward +127
- Negative-valence co-located: sentiment deepens toward -128
- Positive separation: decays toward 0
- Negative separation: decays toward 0 at slower cadence
- Saturating math: no overflow at i8 boundaries
- Dead target: decays under separation rules, not auto-removed
- Protected bonds drift normally
- Diminishing returns above `STRONG_TIE_THRESHOLD`

### 12.3 Rust Integration Tests

- Kin auto-formation at birth: parent and child both have kin slot after demographics phase
- Multi-turn drift convergence: co-located kin bond strengthens over N turns
- Slot exhaustion: 8 protected kin bonds → new social bond fails, `kin_bond_failures` counter increments
- `apply_relationship_ops()` round-trip: batch of mixed ops produces expected store state

### 12.4 FFI Tests

- `apply_relationship_ops()` Arrow batch parsing and execution
- Invalid-op rejection: dead agents, unknown bond type, symmetric Mentor, self-bond
- Batch ordering: same-batch Upsert→Remove→Upsert produces correct final state
- `get_social_edges()` projection: only legacy bond types, only named characters, `a < b` convention
- `get_agent_relationships()`: returns all bond types for a single agent

### 12.5 Python Integration Tests

- M40 compatibility: formation → shim → store → projection round-trip produces same narration context as pre-M50a
- `formed_turn` preservation across repeated `replace_social_edges()` shim writes
- `GreatPerson.agent_bonds` sync: populated from `get_agent_relationships()`, includes kin bonds
- Determinism: same seed produces identical relationship state after N turns

### 12.6 Transient Signal Test

Verify relationship ops don't persist stale state across turns (2-turn test per CLAUDE.md rule).

---

## 13. Phase 6 Roadmap Cross-References

- **REVIEW B-2 Q1 (formation interface):** Resolved. Kin-only Rust-native; all other formation via Python-issued batched ops.
- **REVIEW B-2 Q2 (O(N^2) scaling):** Resolved. No region-wide pair scanning in M50a. Formation is Python-commanded for named characters only. M50b can use cadence-gated checks; M55 adds spatial hash.
- **REVIEW B-2 Q3 (M40 transition):** Resolved. Single truth source, `get_social_edges()` projection, `replace_social_edges()` shim, `SocialGraph` deprecated.
- **RNG stream offset:** 1100 reserved for M50 in the `STREAM_OFFSETS` registry. Not consumed in M50a (no RNG in drift). Available for M50b formation rolls. Must be registered in `agent.rs` `STREAM_OFFSETS` block and collision test even though unused.
- **Satisfaction cap:** No new satisfaction terms in M50a. Drift is behavioral only.
- **Transient signal rule:** `apply_relationship_ops()` batch is consumed once per turn. No transient state to clear — ops are applied and discarded.

---

## 14. CLAUDE.md Updates

Implementation must update CLAUDE.md with:

1. **Rust file table:** Add `relationships.rs` — "Per-agent relationship store, bond helpers, sentiment drift, eviction"
2. **Per-agent memory budget:** Add M50a row: `relationships (5 SoA arrays)` — 65 bytes, cumulative ~133 bytes (from M48's 68-byte baseline + M49's 24 bytes needs + 65 bytes relationships). Note: ~157 if M49 needs are counted in the baseline.
3. **RNG stream offset:** 1100 registered for M50 (not consumed in M50a).

---

## 15. Phoebe Review Resolution

**Review date:** 2026-03-20

### Blocking Issues — Resolved

- **B-1 (shim dispatch table + enum translation):** Added explicit per-bond-type dispatch table to Section 7.3. Mentor → `UpsertDirected`, all others → `UpsertSymmetric`. Documented Mentor single-directed storage (mentor→apprentice only, no reciprocal slot on apprentice).
- **B-2 (enum value mapping):** Reordered BondType enum (Section 2.2) so values 0-4 match M40 `RelationshipType` exactly. No translation needed for overlapping types. Types 5-7 (Kin, Friend, Grudge) are new with no M40 equivalent.

### Non-Blocking Observations — Dispositions

- **NB-1 (65 bytes arithmetic):** Verified correct.
- **NB-2 (`agents_share_memory()` exists):** Confirmed deferred to M50b.
- **NB-3 (RNG offset 1100 not registered):** Added to Section 13 — must register even though unused.
- **NB-4 (spawn init):** Covered by Section 2.4 sentinel hygiene. Implementation must init both spawn branches.
- **NB-5 (dead target drift):** Section 6.3 correctly handles — HashMap miss → separation rules, not skip.
- **NB-6 (`UpsertSymmetric` atomicity):** Implementation note: `resolve_slot()` both sides before `commit_both()`.
- **NB-7 (projection de-duplication):** Added `is_symmetric()` / `is_asymmetric()` helpers to Section 2.7.
- **NB-8 (field name collision):** Renamed to `GreatPerson.agent_bonds` (Section 9.3).
- **NB-9 (Mentor directionality):** Resolved: single directed entry (mentor→apprentice). Documented in Section 7.3.
- **NB-10 (swap-remove + eviction interaction):** Noted for unit test coverage (Section 12.1).
- **NB-11 (CLAUDE.md updates):** Added Section 14.
- **NB-12 (scope boundary clean):** Confirmed.
