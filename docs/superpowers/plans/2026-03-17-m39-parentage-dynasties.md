# M39: Parentage, Inheritance & Dynasties — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parent tracking to the agent pool, swap personality assignment to inheritance at birth, and build a Python-side dynasty detection/event/narrative system.

**Architecture:** Rust owns `parent_id` (new pool field, Arrow columns). Python owns dynasty logic (detection on promotion, extinction on death, split on secession, narrative enrichment). No new FFI functions — one new column on snapshot batch, one on promotions batch.

**Tech Stack:** Rust (chronicler-agents crate), Python (chronicler package), Arrow IPC, pytest, cargo test

**Spec:** `docs/superpowers/specs/2026-03-17-m39-parentage-dynasties-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `chronicler-agents/src/agent.rs` | Add `PARENT_NONE` constant |
| Modify | `chronicler-agents/src/pool.rs` | Add `parent_ids` field, sentinel fix (`next_id: 1`), spawn paths, accessor |
| Modify | `chronicler-agents/src/tick.rs` | Add `parent_id` to `BirthInfo`, personality swap, post-spawn assignment |
| Modify | `chronicler-agents/src/named_characters.rs` | Add `parent_id` to `NamedCharacter`, `register()` param |
| Modify | `chronicler-agents/src/ffi.rs` | Add `parent_id` to `snapshot_schema`, `promotions_schema`, `to_record_batch`, `get_promotions` |
| Modify | `chronicler-agents/src/demographics.rs` | No changes (already has `inherit_personality`) |
| Create | `src/chronicler/dynasties.py` | `Dynasty` dataclass, `DynastyRegistry` class |
| Modify | `src/chronicler/models.py` | Add `parent_id`, `dynasty_id` to `GreatPerson` |
| Modify | `src/chronicler/agent_bridge.py` | Add `gp_by_agent_id` dict, wire dynasty detection/extinction/split |
| Modify | `src/chronicler/narrative.py` | Dynasty context in `build_agent_context_for_moment` / `build_agent_context_block` |
| Modify | `tests/test_agent_bridge.py` | Update `test_snapshot_schema` expected columns |
| Create | `tests/test_dynasties.py` | Python unit tests for dynasty logic |

---

## Chunk 1: Rust Data Model & Sentinel Fix

### Task 1: Sentinel fix — `next_id` starts at 1

**Files:**
- Modify: `chronicler-agents/src/agent.rs:133` (add constant)
- Modify: `chronicler-agents/src/pool.rs:84` (sentinel fix)
- Modify: `chronicler-agents/src/pool.rs:569-579` (update test)

- [ ] **Step 1: Add `PARENT_NONE` constant to `agent.rs`**

After the M38b persecution constants block (after line 142), add a new section:

```rust
// M39: Parentage
pub const PARENT_NONE: u32 = 0;                 // sentinel for no parent
```

- [ ] **Step 2: Fix `next_id` initialization in `pool.rs`**

Change line 84 from:
```rust
            next_id: 0,
```
to:
```rust
            next_id: 1,
```

- [ ] **Step 3: Update `test_spawn_into_empty_pool` to verify sentinel**

In `pool.rs` test (line 569-579), add an assertion after the existing ones:

```rust
        assert_eq!(pool.id(slot), 1); // M39: first agent id must be 1, not 0 (PARENT_NONE sentinel)
```

- [ ] **Step 4: Ripple-effect audit**

Run:
```bash
cd chronicler-agents && grep -rn "agent_id.*=.*0\b\|id.*==.*0\b\|register(0" src/ --include="*.rs" | grep -v "//\|test_character_role"
```

Check each match. The `register()` calls in tests use small integers (0, 1, 2...) as agent IDs — these will now never collide with `PARENT_NONE = 0` because real IDs start at 1. No test fixes needed beyond step 3.

- [ ] **Step 5: Run Rust tests**

```bash
cd chronicler-agents && cargo test
```

Expected: all tests pass. `test_spawn_into_empty_pool` now asserts `id == 1`.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs
git commit -m "feat(m39): add PARENT_NONE sentinel, fix next_id to start at 1"
```

---

### Task 2: Add `parent_ids` field to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs:17-57` (struct), `pool.rs:62-87` (new()), `pool.rs:108-162` (spawn paths)

- [ ] **Step 1: Add field to `AgentPool` struct**

After `beliefs: Vec<u8>` (line 47), before `// Liveness` (line 48), add:

```rust
    // Parentage (M39) — stable agent_id of biological parent
    pub parent_ids: Vec<u32>,
```

- [ ] **Step 2: Initialize in `AgentPool::new()`**

After `beliefs: Vec::with_capacity(capacity),` (line 81), add:

```rust
            parent_ids: Vec::with_capacity(capacity),
```

- [ ] **Step 3: Handle in spawn() reuse path**

In the reuse path (after `self.beliefs[slot] = belief;` at line 131), add:

```rust
            self.parent_ids[slot] = crate::agent::PARENT_NONE;
```

- [ ] **Step 4: Handle in spawn() grow path**

In the grow path (after `self.beliefs.push(belief);` at line 158), add:

```rust
            self.parent_ids.push(crate::agent::PARENT_NONE);
```

- [ ] **Step 5: Add accessor**

After the `is_named` accessor (line 314), add:

```rust
    #[inline]
    pub fn parent_id(&self, slot: usize) -> u32 {
        self.parent_ids[slot]
    }
```

- [ ] **Step 6: Write test for parent_id initialization**

Add to `pool.rs` tests:

```rust
    #[test]
    fn test_parent_id_defaults_to_none() {
        let mut pool = AgentPool::new(4);
        let s0 = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.parent_id(s0), crate::agent::PARENT_NONE);

        // Kill and reuse slot — parent_id should reset to PARENT_NONE
        pool.kill(s0);
        let s1 = pool.spawn(0, 0, Occupation::Soldier, 25, 0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(s1, s0); // reused slot
        assert_eq!(pool.parent_id(s1), crate::agent::PARENT_NONE);
    }
```

- [ ] **Step 7: Run tests**

```bash
cd chronicler-agents && cargo test
```

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/pool.rs
git commit -m "feat(m39): add parent_ids field to AgentPool with PARENT_NONE default"
```

---

### Task 3: Add `parent_id` to `NamedCharacter` and `register()`

**Files:**
- Modify: `chronicler-agents/src/named_characters.rs:22-31` (struct), `142-163` (register)

- [ ] **Step 1: Add field to `NamedCharacter` struct**

After `promotion_trigger: u8,` (line 29), add:

```rust
    pub parent_id: u32,
```

- [ ] **Step 2: Add parameter to `register()`**

Change `register()` signature (line 143-151) to add `parent_id: u32` after `promotion_trigger`:

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
            born_turn,
            promotion_turn,
            promotion_trigger,
            parent_id,
            history: Vec::new(),
        });
    }
```

- [ ] **Step 3: Fix all `register()` call sites**

In `named_characters.rs` tests, every `register()` call needs a trailing `0` (PARENT_NONE) argument. Update:

- Line 220: `registry.register(i, CharacterRole::General, 0, 0, 0, 100, 0);` → `registry.register(i, CharacterRole::General, 0, 0, 0, 100, 0, 0);`
- Line 227: `registry.register(i, CharacterRole::Merchant, (i % 5) as u8 + 1, 0, 0, 100, 0);` → `registry.register(i, CharacterRole::Merchant, (i % 5) as u8 + 1, 0, 0, 100, 0, 0);`
- Line 249: `registry.register(pool.id(slot), CharacterRole::General, 0, 0, 0, 100, 0);` → `registry.register(pool.id(slot), CharacterRole::General, 0, 0, 0, 100, 0, 0);`

In `ffi.rs`, the `get_promotions()` `register()` call (line 607-615) — update in Task 5.

**NOTE:** After this step, `cargo test` will not compile because `ffi.rs` calls `register()` with the old 7-arg signature. Temporarily add `, 0` to the `self.registry.register(...)` call at ffi.rs line 607-615 to keep things compiling, or defer `cargo test` to after Task 5 completes the proper fix.

- [ ] **Step 4: Add test for parent_id on NamedCharacter**

```rust
    #[test]
    fn test_named_character_parent_id() {
        let mut registry = NamedCharacterRegistry::new();
        registry.register(42, CharacterRole::General, 0, 0, 0, 100, 0, 7);
        assert_eq!(registry.characters[0].parent_id, 7);

        // PARENT_NONE case
        registry.register(43, CharacterRole::Merchant, 1, 1, 0, 110, 0, crate::agent::PARENT_NONE);
        assert_eq!(registry.characters[1].parent_id, crate::agent::PARENT_NONE);
    }
```

- [ ] **Step 5: Run tests**

```bash
cd chronicler-agents && cargo test
```

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/named_characters.rs
git commit -m "feat(m39): add parent_id to NamedCharacter and register()"
```

---

## Chunk 2: Birth Path & FFI

### Task 4: Wire `parent_id` into birth path

**Files:**
- Modify: `chronicler-agents/src/tick.rs:458-465` (BirthInfo), `tick.rs:521-538` (parallel phase), `tick.rs:241-269` (sequential phase)

- [ ] **Step 1: Add `parent_id` to `BirthInfo`**

After `belief: u8,` (line 464), add:

```rust
    parent_id: u32,  // M39: stable agent_id of biological parent
```

- [ ] **Step 2: Capture `parent_id` in parallel phase**

In `tick_region_demographics`, inside the fertility branch (after line 538 `belief: pool.beliefs[slot],`), add:

```rust
                    parent_id: pool.ids[slot],  // M39: slot IS the parent in this loop
```

- [ ] **Step 3: Swap personality function in parallel phase**

Replace lines 523-527:
```rust
                let civ_id = pool.civ_affinity(slot);
                let civ_mean = signals.personality_mean_for_civ(civ_id);
                let personality = crate::demographics::assign_personality(
                    &mut personality_rng, civ_mean,
                );
```

With:
```rust
                let civ_id = pool.civ_affinity(slot);
                // M39: inherit personality from parent (tighter noise than civ-mean assignment)
                let parent_personality = [
                    pool.boldness[slot],
                    pool.ambition[slot],
                    pool.loyalty_trait[slot],
                ];
                let personality = crate::demographics::inherit_personality(
                    &mut personality_rng, parent_personality,
                );
```

- [ ] **Step 4: Set `parent_id` post-spawn in sequential phase**

After `pool.set_loyalty(new_slot, birth.parent_loyalty);` (line 255), add:

```rust
            pool.parent_ids[new_slot] = birth.parent_id;
```

- [ ] **Step 5: Add path divergence test to tick.rs**

Add to the `#[cfg(test)]` section at the bottom of tick.rs. This covers the spec's Tier 1 requirement for verifying the spawn vs. birth conditional dispatch fork:

```rust
    #[test]
    fn test_birth_parent_id_and_personality_inheritance() {
        // Spawned agents get PARENT_NONE and assign_personality (civ mean).
        // Born agents get parent's agent_id and inherit_personality (parent values).
        use crate::agent::PARENT_NONE;

        let mut pool = AgentPool::new(8);
        // Spawn an initial agent — should have PARENT_NONE
        let parent_slot = pool.spawn(0, 0, crate::agent::Occupation::Farmer, 25,
            0.8, -0.5, 0.3,  // distinctive personality
            0, 1, 2, crate::agent::BELIEF_NONE);
        assert_eq!(pool.parent_id(parent_slot), PARENT_NONE);

        // After a tick with a birth, the newborn should have parent's agent_id
        // and personality clustered near parent (not civ mean).
        // Full integration requires tick() — this is verified in Tier 2 regression.
        // Unit-level: verify BirthInfo stores parent's id, not slot.
        let parent_agent_id = pool.id(parent_slot);
        assert_ne!(parent_agent_id, PARENT_NONE); // sentinel fix: first id is 1
    }
```

- [ ] **Step 6: Run tests**

```bash
cd chronicler-agents && cargo test
```

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m39): wire parent_id into birth path, swap to inherit_personality"
```

---

### Task 5: Add `parent_id` to Arrow schemas and FFI

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:64-83` (snapshot_schema), `ffi.rs:119-131` (promotions_schema), `ffi.rs:354-426` (to_record_batch), `ffi.rs:565-636` (get_promotions)

- [ ] **Step 1: Add to `snapshot_schema()`**

After `Field::new("belief", DataType::UInt8, false),` (line 82), add:

```rust
        Field::new("parent_id", DataType::UInt32, false),
```

- [ ] **Step 2: Add to `promotions_schema()`**

After `Field::new("personality_label", DataType::Utf8, true),` (line 130), add:

```rust
        Field::new("parent_id", DataType::UInt32, false),
```

- [ ] **Step 3: Add to `to_record_batch()` loop**

Add a builder at the top of the function (after `belief_col`, around line 373):

```rust
        let mut parent_id_col = UInt32Builder::with_capacity(live);
```

Inside the loop (after `belief_col.append_value(self.beliefs[slot]);` at line 400):

```rust
            parent_id_col.append_value(self.parent_ids[slot]);
```

In the `RecordBatch::try_new` column list (after `belief_col` at line 423):

```rust
                Arc::new(parent_id_col.finish()) as _,
```

- [ ] **Step 4: Add to `get_promotions()` loop**

Add a builder (after `label_col`, around line 577):

```rust
        let mut parent_id_col = UInt32Builder::with_capacity(n);
```

Inside the loop (after the `label_col` append, around line 599):

```rust
            parent_id_col.append_value(self.pool.parent_ids[slot]);
```

Update the `register()` call (line 607-615) to pass `parent_id`:

```rust
            self.registry.register(
                agent_id,
                role,
                self.pool.civ_affinity(slot),
                self.pool.civ_affinity(slot),
                born,
                self.turn as u16,
                trigger,
                self.pool.parent_ids[slot],
            );
```

In the `RecordBatch::try_new` column list (after `label_col` at line 631):

```rust
                Arc::new(parent_id_col.finish()) as _,
```

- [ ] **Step 5: Run Rust tests**

```bash
cd chronicler-agents && cargo test
```

Some existing tests (like `test_snapshot_schema` / `test_to_record_batch_filters_dead`) check column counts or schema names — they may need column count adjustments if they assert exact counts.

- [ ] **Step 6: Fix any broken Arrow tests**

`test_to_record_batch_filters_dead` (pool.rs:644) checks schema field names. If it only checks the first few by index, it should still pass. If it checks total column count, update the expected count from 17 → 18.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/pool.rs
git commit -m "feat(m39): add parent_id to snapshot and promotions Arrow schemas"
```

---

### Task 6: Update Python snapshot schema test

**Files:**
- Modify: `tests/test_agent_bridge.py:46-52`

- [ ] **Step 1: Replace entire expected schema in `test_snapshot_schema`**

The test at line 50-52 only lists 10 columns but the Rust schema now has 18. **Replace the entire expected list** (not just append `parent_id`):

```python
        expected = ["id", "region", "origin_region", "civ_affinity", "occupation",
                    "loyalty", "satisfaction", "skill", "age", "displacement_turn",
                    "boldness", "ambition", "loyalty_trait",
                    "cultural_value_0", "cultural_value_1", "cultural_value_2",
                    "belief", "parent_id"]
        assert snap.schema.names == expected
```

The old list was stale from M33/M36/M37 additions. This replaces it with all 18 columns.

- [ ] **Step 2: Run Python test**

```bash
python -m pytest tests/test_agent_bridge.py::TestPythonRoundTrip::test_snapshot_schema -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_bridge.py
git commit -m "test(m39): update snapshot schema test for parent_id column"
```

---

## Chunk 3: Python Dynasty System

### Task 7: Add `parent_id` and `dynasty_id` to `GreatPerson`

**Files:**
- Modify: `src/chronicler/models.py:309-329`

- [ ] **Step 1: Add fields to `GreatPerson`**

After `agent_id: int | None = None` (line 329), add:

```python
    parent_id: int = 0
    dynasty_id: int | None = None
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m39): add parent_id and dynasty_id fields to GreatPerson"
```

---

### Task 8: Create `dynasties.py` — registry and detection

**Files:**
- Create: `src/chronicler/dynasties.py`
- Test: `tests/test_dynasties.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_dynasties.py`:

```python
"""Tests for dynasty detection, extinction, and split logic."""
from chronicler.dynasties import Dynasty, DynastyRegistry
from chronicler.models import GreatPerson


def _make_gp(agent_id: int, name: str, civ: str = "Ashara",
             parent_id: int = 0, alive: bool = True) -> GreatPerson:
    gp = GreatPerson(
        name=name, role="general", trait="bold",
        civilization=civ, origin_civilization=civ,
        born_turn=10, source="agent", agent_id=agent_id,
        parent_id=parent_id,
    )
    gp.alive = alive
    return gp


class TestDynastyDetection:
    def test_no_dynasty_when_parent_not_promoted(self):
        registry = DynastyRegistry()
        named_agents = {10: "Kiran"}
        gp_map = {10: _make_gp(10, "Kiran", parent_id=0)}
        # Child's parent_id=99 is not in named_agents
        child = _make_gp(20, "Tala", parent_id=99)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 0
        assert child.dynasty_id is None

    def test_dynasty_founded_on_parent_child_pair(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        child = _make_gp(20, "Tala", parent_id=10)
        events = registry.check_promotion(child, named_agents, gp_map)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_founded"
        assert events[0].importance == 7
        assert parent.dynasty_id is not None
        assert child.dynasty_id == parent.dynasty_id
        assert registry.dynasties[0].founder_name == "Kiran"

    def test_child_joins_existing_dynasty(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", parent_id=0)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent}
        # First child founds dynasty
        child1 = _make_gp(20, "Tala", parent_id=10)
        registry.check_promotion(child1, named_agents, gp_map)
        dynasty_id = child1.dynasty_id
        # Second child joins
        child2 = _make_gp(30, "Sera", parent_id=10)
        events = registry.check_promotion(child2, named_agents, gp_map)
        assert child2.dynasty_id == dynasty_id
        assert len(registry.dynasties) == 1  # no new dynasty
        assert 30 in registry.dynasties[0].members


class TestDynastyExtinction:
    def test_extinction_when_all_dead(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran")
        child = _make_gp(20, "Tala", parent_id=10)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        # Kill both
        parent.alive = False
        child.alive = False
        events = registry.check_extinctions(gp_map)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_extinct"
        assert registry.dynasties[0].extinct

    def test_no_extinction_while_member_alive(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran")
        child = _make_gp(20, "Tala", parent_id=10)
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        parent.alive = False  # only parent dead
        events = registry.check_extinctions(gp_map)
        assert len(events) == 0
        assert not registry.dynasties[0].extinct


class TestDynastySplit:
    def test_split_on_different_civs(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Verath")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        events = registry.check_splits(gp_map)
        assert len(events) == 1
        assert events[0].event_type == "dynasty_split"
        assert events[0].importance == 5
        assert registry.dynasties[0].split_detected

    def test_split_one_shot(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Verath")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        registry.check_splits(gp_map)  # first fire
        events = registry.check_splits(gp_map)  # second call
        assert len(events) == 0  # one-shot: no re-fire

    def test_no_split_when_same_civ(self):
        registry = DynastyRegistry()
        parent = _make_gp(10, "Kiran", civ="Ashara")
        child = _make_gp(20, "Tala", parent_id=10, civ="Ashara")
        named_agents = {10: "Kiran"}
        gp_map = {10: parent, 20: child}
        registry.check_promotion(child, named_agents, gp_map)
        events = registry.check_splits(gp_map)
        assert len(events) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_dynasties.py -v
```

Expected: `ModuleNotFoundError: No module named 'chronicler.dynasties'`

- [ ] **Step 3: Implement `dynasties.py`**

Create `src/chronicler/dynasties.py`:

```python
"""Dynasty detection, tracking, and event emission (M39).

Dynasties are detected when a promoted named character's parent is also
a promoted named character. Detection is O(1) per promotion via dict lookup.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from chronicler.models import Event, GreatPerson


@dataclass
class Dynasty:
    dynasty_id: int
    founder_id: int          # agent_id of the parent (earliest promoted ancestor)
    founder_name: str        # frozen at founding
    civ_id: str              # founding civ name (spec says int, but str matches GreatPerson.civilization for split comparison)
    members: list[int] = field(default_factory=list)  # agent_ids
    founded_turn: int = 0
    split_detected: bool = False
    extinct: bool = False


class DynastyRegistry:
    def __init__(self) -> None:
        self.dynasties: list[Dynasty] = []
        self._next_id: int = 1

    def check_promotion(
        self,
        child: GreatPerson,
        named_agents: dict[int, str],
        gp_map: dict[int, GreatPerson],
    ) -> list[Event]:
        """Check if a newly promoted character forms a dynasty with their parent."""
        events: list[Event] = []
        parent_id = child.parent_id
        if parent_id not in named_agents:
            return events

        parent = gp_map[parent_id]
        if parent.dynasty_id is not None:
            # Child joins existing dynasty
            dynasty = self._find(parent.dynasty_id)
            dynasty.members.append(child.agent_id)
            child.dynasty_id = parent.dynasty_id
        else:
            # New dynasty founded — parent is the founder
            dynasty = Dynasty(
                dynasty_id=self._next_id,
                founder_id=parent_id,
                founder_name=parent.name,
                civ_id=parent.civilization,
                members=[parent_id, child.agent_id],
                founded_turn=child.born_turn,
            )
            self.dynasties.append(dynasty)
            parent.dynasty_id = self._next_id
            child.dynasty_id = self._next_id
            self._next_id += 1

            events.append(Event(
                turn=child.born_turn,
                event_type="dynasty_founded",
                actors=[parent.name, child.name],
                description=(
                    f"The House of {parent.name} is established as {child.name}, "
                    f"child of the great {parent.role} {parent.name}, rises to prominence"
                ),
                importance=7,
                source="agent",
            ))
        return events

    def check_extinctions(self, gp_map: dict[int, GreatPerson]) -> list[Event]:
        """Post-death sweep: check if any dynasty has all members dead."""
        events: list[Event] = []
        for dynasty in self.dynasties:
            if dynasty.extinct:
                continue
            if all(not gp_map[mid].alive for mid in dynasty.members):
                dynasty.extinct = True
                events.append(Event(
                    turn=0,  # caller should set to current turn
                    event_type="dynasty_extinct",
                    actors=[dynasty.founder_name],
                    description=f"The House of {dynasty.founder_name} has ended — no heir remains",
                    importance=6,
                    source="agent",
                ))
        return events

    def check_splits(self, gp_map: dict[int, GreatPerson]) -> list[Event]:
        """Check if living dynasty members span different civilizations."""
        events: list[Event] = []
        for dynasty in self.dynasties:
            if dynasty.split_detected or dynasty.extinct:
                continue
            living_civs = {
                gp_map[mid].civilization
                for mid in dynasty.members
                if gp_map[mid].alive
            }
            if len(living_civs) > 1:
                dynasty.split_detected = True
                civs_str = " and ".join(sorted(living_civs))
                events.append(Event(
                    turn=0,  # caller should set to current turn
                    event_type="dynasty_split",
                    actors=[dynasty.founder_name],
                    description=(
                        f"The House of {dynasty.founder_name} is divided — "
                        f"members serve {civs_str}"
                    ),
                    importance=5,
                    source="agent",
                ))
        return events

    def get_dynasty_for(self, agent_id: int, gp_map: dict[int, GreatPerson]) -> Dynasty | None:
        """Look up dynasty for a given agent_id, if any."""
        gp = gp_map.get(agent_id)
        if gp is None or gp.dynasty_id is None:
            return None
        return self._find(gp.dynasty_id)

    def _find(self, dynasty_id: int) -> Dynasty:
        for d in self.dynasties:
            if d.dynasty_id == dynasty_id:
                return d
        raise ValueError(f"Dynasty {dynasty_id} not found")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_dynasties.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/dynasties.py tests/test_dynasties.py
git commit -m "feat(m39): add DynastyRegistry with detection, extinction, split logic"
```

---

### Task 9: Wire dynasty system into AgentBridge

**Files:**
- Modify: `src/chronicler/agent_bridge.py:320-322` (init), `agent_bridge.py:461-474` (_process_promotions), `agent_bridge.py:478-522` (_process_deaths), `agent_bridge.py:895-903` (reset)

- [ ] **Step 1: Add `gp_by_agent_id` and `DynastyRegistry` to `__init__`**

After `self.named_agents: dict[int, str] = {}` (line 322), add:

```python
        self.gp_by_agent_id: dict[int, GreatPerson] = {}  # M39: agent_id → GreatPerson
        from chronicler.dynasties import DynastyRegistry
        self.dynasty_registry = DynastyRegistry()
```

- [ ] **Step 2: Populate `gp_by_agent_id` in `_process_promotions()`**

After `self.named_agents[agent_id] = name` (line 473), add:

```python
            self.gp_by_agent_id[agent_id] = gp
```

- [ ] **Step 3: Read `parent_id` from batch and set on GreatPerson**

Inside the promotion loop, after `agent_id = batch.column("agent_id")[i].as_py()` (line 420), add:

```python
            parent_id = batch.column("parent_id")[i].as_py()
```

In the `GreatPerson(...)` constructor (line 461-470), add `parent_id=parent_id`:

```python
            gp = GreatPerson(
                name=name,
                role=role,
                trait=trait,
                civilization=civ.name,
                origin_civilization=civ.name,
                born_turn=world.turn,
                source="agent",
                agent_id=agent_id,
                parent_id=parent_id,
            )
```

- [ ] **Step 4: Add `_pending_dynasty_events` to `__init__`**

After the `DynastyRegistry` initialization (from step 1), add:

```python
        self._pending_dynasty_events: list = []
```

- [ ] **Step 5: Run dynasty detection in `_process_promotions()`**

After `self.gp_by_agent_id[agent_id] = gp` (from step 2), add:

```python
            dynasty_events = self.dynasty_registry.check_promotion(
                gp, self.named_agents, self.gp_by_agent_id,
            )
            for de in dynasty_events:
                de.turn = world.turn
                self._pending_dynasty_events.append(de)
```

Note: `_process_promotions` returns `list[GreatPerson]`, not `Event`. Dynasty events are accumulated on `self._pending_dynasty_events` and drained in the `tick()` caller (Step 7).

- [ ] **Step 6: Wire extinction check into `_process_deaths()`**

After the death processing loop in `_process_deaths` (after line 520, before `return death_events`), add:

```python
        # M39: post-loop extinction check
        extinction_events = self.dynasty_registry.check_extinctions(self.gp_by_agent_id)
        for ee in extinction_events:
            ee.turn = world.turn
        death_events.extend(extinction_events)
```

Also, populate `gp_by_agent_id` for dead characters — they're already in the dict from promotion time, and `_process_deaths` sets `.alive = False` on the same object reference. No additional code needed.

- [ ] **Step 7: Drain dynasty events in the `tick()` method**

The `tick()` method (agent_bridge.py, around line 335) calls `_process_promotions` and `_process_deaths` and combines results. Find the return statement (line ~372):

```python
            return summaries + char_events + death_events
```

Change to:
```python
            # M39: drain dynasty events and check splits
            dynasty_events = self._pending_dynasty_events
            self._pending_dynasty_events = []
            split_events = self.dynasty_registry.check_splits(self.gp_by_agent_id)
            for se in split_events:
                se.turn = world.turn
            dynasty_events.extend(split_events)

            return summaries + char_events + death_events + dynasty_events
```

- [ ] **Step 8: Clear registry on reset**

In the `reset()` method (around line 899-903), after `self.named_agents.clear()`, add:

```python
        self.gp_by_agent_id.clear()
        self.dynasty_registry = DynastyRegistry()
        self._pending_dynasty_events.clear()
```

- [ ] **Step 9: Run all tests**

```bash
python -m pytest tests/test_agent_bridge.py tests/test_dynasties.py -v
```

- [ ] **Step 10: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m39): wire dynasty detection, extinction, and split into AgentBridge"
```

---

## Chunk 4: Narrative Integration

### Task 10: Add dynasty context to narrative

**Files:**
- Modify: `src/chronicler/narrative.py:112-141` (build_agent_context_for_moment), `narrative.py:68-81` (build_agent_context_block)

- [ ] **Step 1: Pass dynasty registry to context builder**

`build_agent_context_for_moment` needs access to the `DynastyRegistry`. Add an optional parameter:

```python
def build_agent_context_for_moment(
    moment: NarrativeMoment,
    great_persons: list,
    displacement_by_region: dict[int, float],
    region_names: dict[int, str],
    dynasty_registry=None,       # M39: optional DynastyRegistry
    gp_by_agent_id: dict | None = None,  # M39: agent_id → GreatPerson
) -> AgentContext | None:
```

- [ ] **Step 2: Enrich character dicts with dynasty info**

Inside the character loop (after `chars.append(char)` at line 129), add dynasty context:

```python
        # M39: dynasty context
        if dynasty_registry is not None and gp_by_agent_id is not None and gp.agent_id:
            dynasty = dynasty_registry.get_dynasty_for(gp.agent_id, gp_by_agent_id)
            if dynasty is not None:
                living_count = sum(1 for m in dynasty.members if gp_by_agent_id[m].alive)
                char["dynasty"] = dynasty.founder_name
                char["dynasty_living"] = living_count
                char["dynasty_total"] = len(dynasty.members)
                if dynasty.split_detected:
                    char["dynasty_split"] = True
```

- [ ] **Step 3: Render dynasty info in `build_agent_context_block`**

In the character rendering loop (after the history lines, around line 80), add:

```python
            if char.get("dynasty"):
                dynasty_line = f"  House of {char['dynasty']}"
                if char.get("dynasty_living", 0) == 1:
                    dynasty_line += " (last of their line)"
                elif char.get("dynasty_split"):
                    dynasty_line += " (dynasty divided)"
                else:
                    dynasty_line += f" ({char['dynasty_living']}/{char['dynasty_total']} living)"
                lines.append(dynasty_line)
```

- [ ] **Step 4: Update the caller to pass dynasty_registry**

Find where `build_agent_context_for_moment` is called:

```bash
cd src && grep -rn "build_agent_context_for_moment" --include="*.py"
```

**Note:** This function may currently have zero callers (it may be defined but not yet wired in). If so, the new optional parameters are safe — no call sites to update. If callers exist, add `dynasty_registry=bridge.dynasty_registry, gp_by_agent_id=bridge.gp_by_agent_id` to each call.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/narrative.py src/chronicler/simulation.py
git commit -m "feat(m39): add dynasty context to narrative prompt"
```

---

### Task 11: Final integration test

**Files:**
- Modify: `tests/test_agent_bridge.py`

- [ ] **Step 1: Add `gp_by_agent_id` population test**

Add to `tests/test_agent_bridge.py`:

```python
class TestDynastyIntegration:
    def test_gp_by_agent_id_mirrors_named_agents(self):
        """Every named_agents entry must have a corresponding gp_by_agent_id entry."""
        # Use the same multi-turn fixture as other integration tests.
        # Run enough turns for at least one promotion.
        bridge = _make_bridge_with_turns(100)  # helper from existing fixtures
        for agent_id in bridge.named_agents:
            assert agent_id in bridge.gp_by_agent_id, (
                f"agent_id {agent_id} in named_agents but missing from gp_by_agent_id"
            )
            gp = bridge.gp_by_agent_id[agent_id]
            assert gp.name == bridge.named_agents[agent_id]
            assert gp.agent_id == agent_id
            assert gp.parent_id is not None  # should be 0 (PARENT_NONE) or a real id
```

If no `_make_bridge_with_turns` helper exists, create one following the existing integration test patterns in the file, or inline the setup. The key assertion is that every `named_agents` key also exists in `gp_by_agent_id` with matching data.

- [ ] **Step 2: Run full test suite**

```bash
cd chronicler-agents && cargo test
```

```bash
python -m pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_bridge.py
git commit -m "test(m39): add dynasty integration test skeleton"
```

---

## Chunk 5: Regression & Characterization (Tier 2/3)

### Task 12: `--agents=off` regression

- [ ] **Step 1: Run agents-off regression**

```bash
python -m chronicler --agents=off --seed=42 --turns=50
```

Verify output is identical to pre-M39 baseline. M39 only touches the birth path and promotion pipeline — `--agents=off` bypasses both.

- [ ] **Step 2: Run 200-turn seed sweep (if harness exists)**

```bash
python -m pytest tests/test_regression.py -k "agents" -v --timeout=300
```

Or manually:
```bash
for seed in $(seq 1 10); do python -m chronicler --seed=$seed --turns=200 2>&1 | grep -c "dynasty"; done
```

Verify at least some runs produce dynasty events across many seeds.

- [ ] **Step 3: Commit any test harness additions**

```bash
git add tests/
git commit -m "test(m39): add regression and characterization harness"
```
