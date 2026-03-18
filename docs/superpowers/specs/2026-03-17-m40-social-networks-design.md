# M40: Social Networks — Design Spec

> **Status:** Approved. Ready for implementation planning.
>
> **Depends on:** M30 (named characters), M38b (schisms — for co-religionist dissolution), M39 (family — shares `agent_id` lookup pattern)
>
> **Date:** 2026-03-17

---

## Goal

Named characters form peer-to-peer social relationships — mentor/apprentice, rivalry, marriage, exile bond, co-religionist — stored in a unified Rust-backed graph. Formation logic stays in Python (Phase 10). The graph is exposed via Arrow for narration and future tick-phase effects.

This milestone **unifies** the existing `character_relationships` system (rivalry, mentorship, marriage in `relationships.py`) with two new relationship types (exile bond, co-religionist) into a single Rust-resident store. The current Python-only `character_relationships` list on `WorldState` is removed.

**Hostages are excluded.** The hostage system (`capture_hostage()`, `release_hostage()`, hostage timers) stays in its current Python-only form. Hostages are an asymmetric diplomatic mechanic with civ-level effects and lifecycle timers — structurally different from peer-to-peer social bonds. Narration merges both sources into a single relationship view (see Section 4).

---

## Section 1: Rust Storage

### SocialEdge Struct

New `social.rs` module in `chronicler-agents/src/`:

```rust
#[repr(u8)]
pub enum RelationshipType {
    Mentor = 0,
    Rival = 1,
    Marriage = 2,
    ExileBond = 3,
    CoReligionist = 4,
}

pub struct SocialEdge {
    pub agent_a: u32,
    pub agent_b: u32,
    pub relationship: RelationshipType,
    pub formed_turn: u16,
}
```

~12 bytes per edge.

### Directionality

- **Mentor:** `agent_a` = mentor, `agent_b` = apprentice. Asymmetric — Rust needs to know which side is which for future tick-phase effects (e.g., apprentice satisfaction bonus).
- **Rival, Marriage, ExileBond, CoReligionist:** `agent_a < agent_b` by convention. Symmetric — Python formation logic enforces the ordering.

No canonical ordering constraint across all types. Dedup is handled by formation logic checking existing edges before adding — no structural enforcement needed.

### SocialGraph

Owned by `AgentSimulator`, not per-region — relationships cross region boundaries:

```rust
pub struct SocialGraph {
    edges: Vec<SocialEdge>,  // capacity hint: 512 (50 chars × ~10 edges)
}
```

~12 bytes × 512 = ~6KB max. Negligible.

### Arrow Exposure

Four columns in a `social_edges` RecordBatch:

| Column | Type |
|--------|------|
| `agent_a` | `UInt32` |
| `agent_b` | `UInt32` |
| `relationship` | `UInt8` |
| `formed_turn` | `UInt16` |

Read via existing Arrow FFI pattern.

### Write-Back

Single FFI function: `replace_social_edges(batch: RecordBatch)`. **Batch replace** — Python sends the full edge list each turn after Phase 10 formation/dissolution. No incremental add/remove API. At ~500 edges max, serializing the full list is trivial and eliminates delta-tracking bookkeeping.

### One-Turn Latency

Formation and dissolution run in Phase 10. Agent tick runs between Phase 9 and Phase 10. If a future milestone adds tick-phase relationship effects, Rust reads edges from the previous turn's Phase 10 output. Same pattern as M38b's schism one-turn delay — **intentional, not a bug.**

---

## Section 2: Formation Logic (Python)

### Where It Runs

Phase 10, in `simulation.py` where existing `check_rivalry_formation()` / `check_mentorship_formation()` / `check_marriage_formation()` calls already live (~lines 983-994).

### Coordinator Function

A new coordinator replaces the three individual formation calls:

```python
def form_and_sync_relationships(world, bridge):
    """Phase 10 relationship pass: detect new edges, dissolve stale ones, batch-replace to Rust."""
    # 1. Read current edges from Rust (Arrow batch)
    current_edges = bridge.read_social_edges()

    # 2. Run dissolution — returns both surviving and dissolved lists
    surviving, dissolved_this_turn = dissolve_edges(current_edges, world)

    # 3. Run all five formation checks, dedup against surviving
    new_rivals = check_rivalry_formation(world, surviving)
    new_mentors = check_mentorship_formation(world, surviving)
    new_marriages = check_marriage_formation(world, surviving)
    new_exile_bonds = check_exile_bond_formation(world, surviving)
    new_coreligionists = check_coreligionist_formation(world, surviving)

    # 4. Batch replace to Rust
    all_edges = surviving + new_rivals + new_mentors + new_marriages + new_exile_bonds + new_coreligionists
    bridge.replace_social_edges(all_edges)

    # 5. Return dissolved edges for narration pipeline (transient, not written to Rust)
    return dissolved_this_turn
```

### Migration of Existing Types

The three existing formation functions in `relationships.py` keep their detection logic unchanged. Only the write target changes — instead of appending to `world.character_relationships`, they return `SocialEdge`-compatible tuples. Dedup checks against the `surviving` edge list passed in.

| Type | Conditions (existing, unchanged) |
|------|----------------------------------|
| Rivalry | Same role, opposing sides in war |
| Mentorship | Great person + leader with compatible secondary trait |
| Marriage | Great persons from allied civs (disposition ALLIED, 10+ turns) |

### New Formation Rules

| Type | Conditions | Dedup |
|------|-----------|-------|
| Exile Bond | 2+ named characters share `origin_region`, both currently in the **same** region that is **not** their `origin_region` | One bond per pair per origin |
| Co-religionist | 2+ named characters share belief in a region where that belief is <30% of population (from agent snapshot) | One bond per pair per shared faith |

### `origin_region` Prerequisite

Neither `GreatPerson` (Python) nor `NamedCharacter` (Rust) currently has `origin_region`. M40 adds:

```python
# models.py — GreatPerson
origin_region: Optional[str] = None
```

Populated at promotion time from the agent's region in the snapshot (same `agent_id` lookup pattern as existing fields). `None` for pre-M40 great persons — formation logic guards with `if gp.origin_region is None: skip`. No false matches from shared default values.

---

## Section 3: Dissolution Logic

Single function `dissolve_edges()` runs at the start of the Phase 10 relationship pass (before formation). Returns both surviving and dissolved edge lists.

### Dissolution Table

| Type | Dissolves when | Detection |
|------|---------------|-----------|
| Mentor | Either party dead | `agent_id` not in active named characters |
| Rival | Either party dead | Same |
| Marriage | Either party dead | Same |
| Exile Bond | Either party dead (only) | Same |
| Co-religionist | Either party dead, **or** beliefs now differ | Death: same check. Belief divergence: compare current `belief_id` from agent snapshot. If beliefs differ now when they matched at formation, the bond dissolves — whether caused by conversion (M37) or schism (M38b). No need to distinguish the cause. |

### Design Notes

- **Implicit schism detection:** Comparing current beliefs avoids coupling to M38b's event system. A schism that splits a shared faith results in different `belief_id` values — dissolution logic sees diverged beliefs and dissolves the bond without knowing a schism occurred.
- **Dissolved edges are transient Python-side data.** They are returned from `dissolve_edges()` for narration but never written back to Rust. This keeps dissolution as silent bookkeeping while preserving relationship context for the narrator.
- **No dissolution events generated.** If a future milestone wants "the schism tore them apart" as a narrative event, it would be wired through the curator, not the dissolution function.

---

## Section 4: Narration Wiring

### Problem

Relationship data currently does not reach the narrator. `character_relationships` is stored on `WorldState` but never serialized into `NarrationContext`. Additionally, death dissolves edges before narration reads them — so when the narrator builds context for "Kiran fell in battle," the mentor-apprentice edge to Vesh is already gone.

### Solution

`build_agent_context_for_moment()` in `narrative.py` merges three sources into a single `relationships` list on `AgentContext`:

1. **Social edges from Rust** (current surviving edges)
2. **Dissolved edges from this turn** (transient Python-side data from `dissolve_edges()`)
3. **Hostage state from `GreatPerson` fields** (`is_hostage`, `captured_by`)

### AgentContext Addition

```python
relationships: list[dict] = Field(default_factory=list)
# Each dict:
# {"type": str, "character_a": str, "character_b": str,
#  "role_a": str | None, "role_b": str | None, "since_turn": int}
# role_a/role_b only populated for asymmetric types:
#   mentor/apprentice, captor/captive
```

### Narrator Prompt Format

```
## Character Relationships
- Vesh (apprentice of Kiran, since turn 210)
- Maren (rival of Vesh, since turn 245)
- Sera and Vesh (co-religionists in the polytheist minority, since turn 230)
- Kiran (hostage of the Arathi, turn 3 of captivity)
```

### Curator Integration

`compute_base_scores()` in `curator.py` already boosts events involving named characters. M40 adds a secondary boost when an event involves characters who share a relationship. Multiplicative: `RELATIONSHIP_SCORE_BONUS = 1.2`, applied once per event (capped at one application regardless of how many relationships are relevant, to avoid runaway scores).

### `--agents=off` Behavior

No social graph exists. `relationships` list is empty. Narration proceeds without relationship context. No special handling needed — formation logic never runs, Rust graph stays empty.

---

## Section 5: Migration Path & File Changes

### Migration Steps

1. **Add Rust infrastructure:** New `social.rs` module with `SocialGraph`, `SocialEdge`, `RelationshipType`. Wire into `AgentSimulator`. Add `replace_social_edges()` and `read_social_edges()` FFI functions in `ffi.rs`.

2. **Add `origin_region: Optional[str] = None` to `GreatPerson`:** Populated at promotion time from the agent's region in the snapshot.

3. **Migrate formation functions in `relationships.py`:** `check_rivalry_formation()`, `check_mentorship_formation()`, `check_marriage_formation()` return edge tuples instead of appending to `world.character_relationships`. Add `check_exile_bond_formation()` and `check_coreligionist_formation()`.

4. **New coordinator:** `form_and_sync_relationships()` in `relationships.py` — reads edges from Rust, runs dissolution (returning surviving + dissolved), runs all five formation checks, batch-replaces to Rust. Returns dissolved edges for narration.

5. **Wire into Phase 10:** Replace the three individual formation calls in `simulation.py` with a single `form_and_sync_relationships(world, bridge)` call.

6. **Wire narration:** Update `build_agent_context_for_moment()` to read social edges + dissolved edges + hostage state into `AgentContext.relationships`.

7. **Remove `character_relationships`:** Delete the field from `WorldState` once all consumers read from the Rust store. `dissolve_dead_relationships()` becomes `dissolve_edges()` in the new coordinator.

### File Changes

| File | Change |
|------|--------|
| `chronicler-agents/src/social.rs` | **New** — `SocialGraph`, `SocialEdge`, `RelationshipType` |
| `chronicler-agents/src/lib.rs` | Add `mod social` |
| `chronicler-agents/src/ffi.rs` | Add `replace_social_edges()`, `read_social_edges()` FFI functions |
| `src/chronicler/models.py` | Add `origin_region: Optional[str] = None` to `GreatPerson`; remove `character_relationships` from `WorldState` |
| `src/chronicler/relationships.py` | Migrate formation functions to return edge tuples; add exile bond + co-religionist formation; add `form_and_sync_relationships()` coordinator; add `dissolve_edges()` |
| `src/chronicler/agent_bridge.py` | Wire `replace_social_edges()` / `read_social_edges()` bridge methods; set `origin_region` at promotion time |
| `src/chronicler/simulation.py` | Replace three individual formation calls with single `form_and_sync_relationships(world, bridge)` call |
| `src/chronicler/narrative.py` | Read social edges + dissolved edges + hostage state into `AgentContext.relationships` |
| `src/chronicler/curator.py` | Add `RELATIONSHIP_SCORE_BONUS = 1.2` multiplicative boost for events involving related characters |

### Bundle Impact

`character_relationships` is not currently serialized to the bundle. The social graph is reconstructable from turn history. **No bundle format change.**

### Test Coverage

- Formation conditions (all five types, including co-location requirement for exile bonds)
- Dissolution (all triggers: death, conversion, schism-splits-co-religionist)
- Edge dedup (no duplicate edges from repeated formation checks)
- Narration context merging (social edges + dissolved edges + hostage state)
- `--agents=off` produces empty relationships
- Curator relationship boost scoring (capped at 1.2× per event)
