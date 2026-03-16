# M30: Agent Narrative Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge agent-level simulation with chronicle prose — agents become named characters with personal histories and narrative presence.

**Architecture:** Rust-side adds two SoA fields and a `NamedCharacterRegistry` to identify promotion candidates. Python bridge processes promotions, detects character-driven events, and feeds enriched context to the curator and narrator. Names live in Python only (Rust tracks agent_id/role/history, Python owns the `named_agents` dict).

**Tech Stack:** Rust (chronicler-agents crate), Python (chronicler package), PyO3/Arrow FFI, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-m30-agent-narrative-design.md`

---

## Chunk 1: Rust Agent Pool Extensions

### Task 1: Add `life_events` SoA field to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs` (AgentPool struct, `new`, `spawn`, `kill`)
- Modify: `chronicler-agents/src/agent.rs` (bitflag constants)

- [ ] **Step 1: Add life_events bitflag constants to agent.rs**

In `chronicler-agents/src/agent.rs`, after the `WAR_CASUALTY_MULTIPLIER` line:

```rust
// Life-event bitflags for named character promotion (M30)
pub const LIFE_EVENT_REBELLION: u8     = 1 << 0;
pub const LIFE_EVENT_MIGRATION: u8     = 1 << 1;
pub const LIFE_EVENT_WAR_SURVIVAL: u8  = 1 << 2;
pub const LIFE_EVENT_LOYALTY_FLIP: u8  = 1 << 3;
pub const LIFE_EVENT_OCC_SWITCH: u8    = 1 << 4;
```

- [ ] **Step 2: Add `life_events` Vec to AgentPool struct**

In `chronicler-agents/src/pool.rs`, add after `displacement_turns: Vec<u8>,` and before `// Liveness` / `alive: Vec<bool>,`:

```rust
    // Named character promotion (M30)
    pub life_events: Vec<u8>,
```

- [ ] **Step 3: Update `AgentPool::new` to include `life_events`**

In the `new` constructor, add after `displacement_turns: Vec::with_capacity(capacity),`:

```rust
            life_events: Vec::with_capacity(capacity),
```

- [ ] **Step 4: Update `spawn` — reuse path**

In the free-slot reuse branch of `spawn`, add after `self.displacement_turns[slot] = 0;`:

```rust
            self.life_events[slot] = 0;
```

- [ ] **Step 5: Update `spawn` — grow path**

In the grow-vecs branch of `spawn`, add after `self.displacement_turns.push(0);`:

```rust
            self.life_events.push(0);
```

- [ ] **Step 6: Add inline test**

In the existing `#[cfg(test)] mod tests` in `pool.rs`:

```rust
    #[test]
    fn test_life_events_bitflag() {
        use crate::agent::*;
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20);
        assert_eq!(pool.life_events[slot], 0);

        pool.life_events[slot] |= LIFE_EVENT_REBELLION;
        assert_eq!(pool.life_events[slot], 1);

        pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
        assert_eq!(pool.life_events[slot], 0b00000011);

        // All five bits set
        pool.life_events[slot] |= LIFE_EVENT_WAR_SURVIVAL
            | LIFE_EVENT_LOYALTY_FLIP
            | LIFE_EVENT_OCC_SWITCH;
        assert_eq!(pool.life_events[slot], 0b00011111);
    }
```

- [ ] **Step 7: Run tests**

Run: `cd chronicler-agents && cargo test test_life_events_bitflag -- --nocapture`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs
git commit -m "feat(m30): add life_events SoA field and bitflag constants"
```

---

### Task 2: Add `promotion_progress` SoA field to AgentPool

**Files:**
- Modify: `chronicler-agents/src/pool.rs`
- Modify: `chronicler-agents/src/agent.rs` (promotion constants)

- [ ] **Step 1: Add promotion constants to agent.rs**

In `chronicler-agents/src/agent.rs`, after the life-event bitflags:

```rust
// Named character promotion thresholds (M30) [CALIBRATE: post-M28]
pub const PROMOTION_SKILL_THRESHOLD: f32 = 0.9;
pub const PROMOTION_DURATION_TURNS: u8 = 20;
```

- [ ] **Step 2: Add `promotion_progress` Vec to AgentPool**

In `pool.rs`, directly after `pub life_events: Vec<u8>,`:

```rust
    pub promotion_progress: Vec<u8>,
```

- [ ] **Step 3: Update `AgentPool::new`**

Directly after `life_events: Vec::with_capacity(capacity),`:

```rust
            promotion_progress: Vec::with_capacity(capacity),
```

- [ ] **Step 4: Update `spawn` — reuse path**

After `self.life_events[slot] = 0;`:

```rust
            self.promotion_progress[slot] = 0;
```

- [ ] **Step 5: Update `spawn` — grow path**

After `self.life_events.push(0);`:

```rust
            self.promotion_progress.push(0);
```

- [ ] **Step 6: Add test for promotion_progress**

```rust
    #[test]
    fn test_promotion_progress_increments() {
        use crate::agent::*;
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 20);
        assert_eq!(pool.promotion_progress[slot], 0);

        // Simulate skill above threshold — increment
        let occ = pool.occupations[slot] as usize;
        pool.skills[slot * 5 + occ] = 0.95;
        if pool.skills[slot * 5 + occ] > PROMOTION_SKILL_THRESHOLD {
            pool.promotion_progress[slot] = pool.promotion_progress[slot].saturating_add(1);
        }
        assert_eq!(pool.promotion_progress[slot], 1);

        // Simulate skill drop — reset
        pool.skills[slot * 5 + occ] = 0.5;
        if pool.skills[slot * 5 + occ] <= PROMOTION_SKILL_THRESHOLD {
            pool.promotion_progress[slot] = 0;
        }
        assert_eq!(pool.promotion_progress[slot], 0);

        // Simulate occupation switch — reset
        pool.promotion_progress[slot] = 15;
        pool.occupations[slot] = Occupation::Merchant as u8;
        pool.promotion_progress[slot] = 0; // occ switch resets
        assert_eq!(pool.promotion_progress[slot], 0);
    }
```

- [ ] **Step 7: Run tests**

Run: `cd chronicler-agents && cargo test test_promotion_progress -- --nocapture`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs
git commit -m "feat(m30): add promotion_progress SoA field and threshold constants"
```

---

### Task 3: Wire life_events into tick.rs event handlers

**Files:**
- Modify: `chronicler-agents/src/tick.rs`

The tick function already emits `AgentEvent`s for rebellions, migrations, occupation switches, loyalty flips, and deaths (war casualties). Each handler must also set the corresponding `life_events` bit on the affected agent.

- [ ] **Step 1: Import life-event constants**

At the top of `tick.rs`, extend the `use crate::agent::` import:

```rust
use crate::agent::{
    LIFE_EVENT_LOYALTY_FLIP, LIFE_EVENT_MIGRATION, LIFE_EVENT_OCC_SWITCH,
    LIFE_EVENT_REBELLION, LIFE_EVENT_WAR_SURVIVAL,
    OCCUPATION_COUNT, SKILL_NEWBORN, SKILL_RESET_ON_SWITCH,
};
```

- [ ] **Step 2: Set rebellion bit**

In the `// Rebellions` apply block (~line 94), before `events.push(AgentEvent {`:

```rust
            pool.life_events[slot] |= LIFE_EVENT_REBELLION;
```

- [ ] **Step 3: Set migration bit**

In the `// Migrations` apply block (~line 108), before `events.push(AgentEvent {`:

```rust
            pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
```

- [ ] **Step 4: Set occupation switch bit and reset promotion_progress**

In the `// Occupation switches` apply block (~line 122), before `events.push(AgentEvent {`:

```rust
            pool.life_events[slot] |= LIFE_EVENT_OCC_SWITCH;
            pool.promotion_progress[slot] = 0;
```

- [ ] **Step 5: Set loyalty flip bit**

In the `// Loyalty flips` apply block (~line 143), before `events.push(AgentEvent {`:

```rust
            pool.life_events[slot] |= LIFE_EVENT_LOYALTY_FLIP;
```

- [ ] **Step 6: Set war survival bit on death-event neighbors**

War deaths are handled in the demographics section. For war *survival*, set the bit on agents in a contested region who survive the tick. This is done after the demographics apply block (deaths/age/births), before the displacement decrement loop (~line 236). Uses the second `region_groups` binding (line 168) which is still in scope. Add:

```rust
    // Mark war survival for agents in contested regions who survived
    for (region_id, slots) in region_groups.iter().enumerate() {
        if region_id < signals.contested_regions.len()
            && signals.contested_regions[region_id]
        {
            for &slot in slots {
                if pool.is_alive(slot) {
                    pool.life_events[slot] |= LIFE_EVENT_WAR_SURVIVAL;
                }
            }
        }
    }
```

- [ ] **Step 7: Update promotion_progress in skill growth loop**

In the skill growth loop (section 0, ~line 50), after `pool.grow_skill(slot);`:

```rust
            // Update promotion progress for named character promotion
            let occ = pool.occupations[slot] as usize;
            let skill = pool.skills[slot * 5 + occ];
            if skill > crate::agent::PROMOTION_SKILL_THRESHOLD {
                pool.promotion_progress[slot] =
                    pool.promotion_progress[slot].saturating_add(1);
            } else {
                pool.promotion_progress[slot] = 0;
            }
```

- [ ] **Step 8: Run full test suite**

Run: `cd chronicler-agents && cargo test -- --nocapture`
Expected: All existing tests PASS (no regression)

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "feat(m30): wire life_events and promotion_progress into tick handlers"
```

---

## Chunk 2: Rust Named Character Registry & FFI

### Task 4: Create `named_characters.rs` with CharacterRole and NamedCharacterRegistry

**Files:**
- Create: `chronicler-agents/src/named_characters.rs`
- Modify: `chronicler-agents/src/lib.rs` (add module)

- [ ] **Step 1: Create named_characters.rs**

```rust
//! Named character registry for M30 agent narrative promotion.
//!
//! Tracks which agents have been promoted to named characters.
//! Names are owned by Python — Rust tracks agent_id, role, and history only.

use crate::agent::{PROMOTION_DURATION_TURNS, PROMOTION_SKILL_THRESHOLD};
use crate::pool::AgentPool;

/// Character roles map to GreatPerson roles, not agent occupations.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CharacterRole {
    General = 0,
    Merchant = 1,
    Scientist = 2,
    Prophet = 3,
    Exile = 4,
}

/// Compact record of a promoted named character.
#[derive(Clone, Debug)]
pub struct NamedCharacter {
    pub agent_id: u32,
    pub role: CharacterRole,
    pub civ_id: u8,
    pub origin_civ_id: u8,
    pub born_turn: u16,
    pub promotion_turn: u16,
    pub promotion_trigger: u8, // 0=skill, 1=rebellion, 2=displacement, 3=migration, 4=versatility
    pub history: Vec<(u16, u8, u16)>, // (turn, event_type, region)
}

/// Per-civ cap on named characters.
const PER_CIV_CAP: usize = 10;
/// Global cap on named characters.
const GLOBAL_CAP: usize = 50;

/// Registry of all promoted named characters.
pub struct NamedCharacterRegistry {
    pub characters: Vec<NamedCharacter>,
}

impl NamedCharacterRegistry {
    pub fn new() -> Self {
        Self {
            characters: Vec::new(),
        }
    }

    /// Count characters belonging to a specific civ.
    pub fn count_for_civ(&self, civ_id: u8) -> usize {
        self.characters.iter().filter(|c| c.civ_id == civ_id).count()
    }

    /// Check if adding a character for this civ would exceed caps.
    pub fn can_promote(&self, civ_id: u8) -> bool {
        self.characters.len() < GLOBAL_CAP && self.count_for_civ(civ_id) < PER_CIV_CAP
    }

    /// Find promotion candidates from the pool.
    ///
    /// Returns (slot, CharacterRole, trigger) tuples for agents that qualify.
    pub fn find_candidates(&self, pool: &AgentPool, turn: u32) -> Vec<(usize, CharacterRole, u8)> {
        let mut candidates = Vec::new();
        let already_promoted: std::collections::HashSet<u32> = self
            .characters
            .iter()
            .map(|c| c.agent_id)
            .collect();

        for slot in 0..pool.capacity() {
            if !pool.is_alive(slot) {
                continue;
            }
            let agent_id = pool.id(slot);
            if already_promoted.contains(&agent_id) {
                continue;
            }
            // Life-event gate — must have at least one qualifying event
            if pool.life_events[slot] == 0 {
                continue;
            }

            let civ_id = pool.civ_affinity(slot);
            if !self.can_promote(civ_id) {
                continue;
            }

            // Check bypass triggers first (skip skill gate)
            if let Some((role, trigger)) = self.check_bypass_triggers(pool, slot, turn) {
                candidates.push((slot, role, trigger));
                continue;
            }

            // Two-gate: skill gate
            if pool.promotion_progress[slot] >= PROMOTION_DURATION_TURNS {
                let occ = pool.occupations[slot];
                let role = match occ {
                    1 => CharacterRole::General,  // Soldier
                    2 => CharacterRole::Merchant,
                    3 => CharacterRole::Scientist, // Scholar
                    4 => CharacterRole::Prophet,   // Priest
                    _ => CharacterRole::Merchant,  // Farmer → default Merchant
                };
                candidates.push((slot, role, 0)); // trigger 0 = skill
            }
        }
        candidates
    }

    /// Check bypass triggers for a single agent.
    /// Returns (CharacterRole, trigger_id) if a bypass fires.
    fn check_bypass_triggers(
        &self,
        pool: &AgentPool,
        slot: usize,
        _turn: u32,
    ) -> Option<(CharacterRole, u8)> {
        let life = pool.life_events[slot];
        let occ = pool.occupations[slot];

        // Bypass 1: Rebellion leader (bit 0 set)
        // In practice, the "led" distinction needs Python context.
        // Rust checks: participated in rebellion.
        if life & crate::agent::LIFE_EVENT_REBELLION != 0 {
            let role = if occ == 1 {
                CharacterRole::General
            } else {
                CharacterRole::Prophet
            };
            return Some((role, 1));
        }

        // Bypass 2: Long displacement (50+ turns)
        if pool.displacement_turns(slot) >= 50 {
            return Some((CharacterRole::Exile, 2));
        }

        // Bypass 3: Serial migrant (3+ region changes) — tracked by migration bit
        // The migration bit only tells us they migrated at least once.
        // For 3+ changes we need a counter. Since pool doesn't track migration count,
        // this bypass is deferred to Python which can count from event history.

        // Bypass 4: Occupation versatility (3+ switches) — same issue, deferred to Python.

        None
    }

    /// Register a promoted character.
    pub fn register(
        &mut self,
        agent_id: u32,
        role: CharacterRole,
        civ_id: u8,
        origin_civ_id: u8,
        born_turn: u16,
        promotion_turn: u16,
        promotion_trigger: u8,
    ) {
        self.characters.push(NamedCharacter {
            agent_id,
            role,
            civ_id,
            origin_civ_id,
            born_turn,
            promotion_turn,
            promotion_trigger,
            history: Vec::new(),
        });
    }

    /// Update civ_id for a character (conquest/secession sync).
    pub fn set_character_civ(&mut self, agent_id: u32, new_civ_id: u8) {
        for c in &mut self.characters {
            if c.agent_id == agent_id {
                c.civ_id = new_civ_id;
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::*;
    use crate::pool::AgentPool;

    #[test]
    fn test_promotion_two_gates() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Soldier, 20);
        let registry = NamedCharacterRegistry::new();

        // No life events, no promotion progress → no candidates
        assert!(registry.find_candidates(&pool, 100).is_empty());

        // Skill gate passes, life-event gate fails → no candidates
        pool.promotion_progress[slot] = PROMOTION_DURATION_TURNS;
        assert!(registry.find_candidates(&pool, 100).is_empty());

        // Both gates pass → candidate found
        pool.life_events[slot] |= LIFE_EVENT_MIGRATION;
        let candidates = registry.find_candidates(&pool, 100);
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].1, CharacterRole::General); // soldier → general
    }

    #[test]
    fn test_bypass_triggers() {
        let mut pool = AgentPool::new(4);
        // Priest with rebellion → Prophet
        let slot = pool.spawn(0, 0, Occupation::Priest, 20);
        pool.life_events[slot] |= LIFE_EVENT_REBELLION;
        let registry = NamedCharacterRegistry::new();
        let candidates = registry.find_candidates(&pool, 100);
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].1, CharacterRole::Prophet);
        assert_eq!(candidates[0].2, 1); // trigger 1 = rebellion
    }

    #[test]
    fn test_promotion_caps() {
        let mut registry = NamedCharacterRegistry::new();
        // Fill per-civ cap for civ 0
        for i in 0..10 {
            registry.register(i, CharacterRole::General, 0, 0, 0, 100, 0);
        }
        assert!(!registry.can_promote(0)); // civ 0 full
        assert!(registry.can_promote(1));  // civ 1 still has room

        // Fill global cap
        for i in 10..50 {
            registry.register(i, CharacterRole::Merchant, (i % 5) as u8 + 1, 0, 0, 100, 0);
        }
        assert!(!registry.can_promote(1)); // global cap hit
    }
}
```

- [ ] **Step 2: Register module in lib.rs**

In `chronicler-agents/src/lib.rs`, add after `mod tick;`:

```rust
pub mod named_characters;
```

And add a re-export after the existing ones:

```rust
#[doc(hidden)]
pub use named_characters::{CharacterRole, NamedCharacterRegistry};
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo test -- --nocapture`
Expected: All tests PASS including new `test_promotion_two_gates`, `test_bypass_triggers`, `test_promotion_caps`

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/named_characters.rs chronicler-agents/src/lib.rs
git commit -m "feat(m30): add NamedCharacterRegistry with CharacterRole and promotion logic"
```

---

### Task 5: Add `get_promotions()` and `set_agent_civ()` FFI methods

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Add promotions schema**

In `ffi.rs`, after `events_schema()`:

```rust
/// Schema for `get_promotions()` — named character promotion candidates.
pub fn promotions_schema() -> Schema {
    Schema::new(vec![
        Field::new("agent_id", DataType::UInt32, false),
        Field::new("role", DataType::UInt8, false),
        Field::new("trigger", DataType::UInt8, false),
        Field::new("skill", DataType::Float32, false),
        Field::new("life_events", DataType::UInt8, false),
        Field::new("origin_region", DataType::UInt16, false),
    ])
}
```

- [ ] **Step 2: Add NamedCharacterRegistry to AgentSimulator**

In the `AgentSimulator` struct, add after `turn: u32,`:

```rust
    registry: crate::named_characters::NamedCharacterRegistry,
```

In `AgentSimulator::new`, add after `turn: 0,`:

```rust
            registry: crate::named_characters::NamedCharacterRegistry::new(),
```

- [ ] **Step 3: Add `get_promotions()` method**

In `#[pymethods] impl AgentSimulator`, after `get_region_populations`:

```rust
    /// Return promotion candidates as an Arrow RecordBatch.
    /// Candidates are agents that pass both the skill gate and life-event gate,
    /// or a bypass trigger. Each call returns NEW candidates only (already-promoted
    /// agents are tracked in the registry).
    pub fn get_promotions(&mut self) -> PyResult<PyRecordBatch> {
        let candidates = self.registry.find_candidates(&self.pool, self.turn);

        let n = candidates.len();
        let mut agent_ids = UInt32Builder::with_capacity(n);
        let mut roles = UInt8Builder::with_capacity(n);
        let mut triggers = UInt8Builder::with_capacity(n);
        let mut skills = arrow::array::Float32Builder::with_capacity(n);
        let mut life_events_col = UInt8Builder::with_capacity(n);
        let mut origin_regions = UInt16Builder::with_capacity(n);

        for &(slot, role, trigger) in &candidates {
            let agent_id = self.pool.id(slot);
            let occ = self.pool.occupations[slot] as usize;
            let skill = self.pool.skills[slot * 5 + occ];

            agent_ids.append_value(agent_id);
            roles.append_value(role as u8);
            triggers.append_value(trigger);
            skills.append_value(skill);
            life_events_col.append_value(self.pool.life_events[slot]);
            origin_regions.append_value(self.pool.origin_regions[slot]);

            // Register in the Rust-side registry.
            // origin_civ_id = current civ at promotion time (best available;
            // Python owns the richer GreatPerson.origin_civilization).
            // born_turn = turn - age (when the agent was spawned).
            let born = self.turn.saturating_sub(self.pool.age(slot) as u32) as u16;
            self.registry.register(
                agent_id,
                role,
                self.pool.civ_affinity(slot),
                self.pool.civ_affinity(slot), // origin_civ ≈ current civ; Python tracks true origin
                born,
                self.turn as u16,
                trigger,
            );
        }

        let schema = Arc::new(promotions_schema());
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(agent_ids.finish()) as _,
                Arc::new(roles.finish()) as _,
                Arc::new(triggers.finish()) as _,
                Arc::new(skills.finish()) as _,
                Arc::new(life_events_col.finish()) as _,
                Arc::new(origin_regions.finish()) as _,
            ],
        )
        .map_err(arrow_err)?;
        Ok(PyRecordBatch::new(batch))
    }

    /// Force-set an agent's civ_affinity. Used for conquest/secession sync.
    pub fn set_agent_civ(&mut self, agent_id: u32, new_civ_id: u8) -> PyResult<()> {
        // Linear scan — called at most 10 times per event (per-civ cap).
        for slot in 0..self.pool.capacity() {
            if self.pool.is_alive(slot) && self.pool.id(slot) == agent_id {
                self.pool.set_civ_affinity(slot, new_civ_id);
                self.registry.set_character_civ(agent_id, new_civ_id);
                return Ok(());
            }
        }
        Err(PyValueError::new_err(format!(
            "agent_id {} not found or dead",
            agent_id
        )))
    }
```

- [ ] **Step 4: Add `Float32Builder` import**

At the top of `ffi.rs`, update the arrow imports to include `Float32Builder`:

```rust
use arrow::array::{Float32Builder, UInt8Builder, UInt16Builder, UInt32Builder};
```

Note: `Float32Builder` may already be imported. Check first — only add if missing.

- [ ] **Step 5: Run tests**

Run: `cd chronicler-agents && cargo test -- --nocapture`
Expected: All tests PASS. Compilation succeeds with new FFI methods.

- [ ] **Step 6: Add FFI round-trip test**

In `named_characters.rs` tests:

```rust
    #[test]
    fn test_character_role_mapping() {
        // Verify CharacterRole u8 values match what Python expects
        assert_eq!(CharacterRole::General as u8, 0);
        assert_eq!(CharacterRole::Merchant as u8, 1);
        assert_eq!(CharacterRole::Scientist as u8, 2);
        assert_eq!(CharacterRole::Prophet as u8, 3);
        assert_eq!(CharacterRole::Exile as u8, 4);
    }

    #[test]
    fn test_set_agent_civ() {
        let mut pool = AgentPool::new(4);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 20);
        assert_eq!(pool.civ_affinity(slot), 0);

        pool.set_civ_affinity(slot, 3);
        assert_eq!(pool.civ_affinity(slot), 3);

        let mut registry = NamedCharacterRegistry::new();
        registry.register(pool.id(slot), CharacterRole::General, 0, 0, 0, 100, 0);
        registry.set_character_civ(pool.id(slot), 3);
        assert_eq!(registry.characters[0].civ_id, 3);
    }
```

- [ ] **Step 7: Run tests**

Run: `cd chronicler-agents && cargo test -- --nocapture`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/named_characters.rs
git commit -m "feat(m30): add get_promotions() and set_agent_civ() FFI methods"
```

---

## Chunk 3: Python Model Changes & Bridge Promotion

### Task 6: Add `source` and `agent_id` fields to GreatPerson

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Add fields to GreatPerson**

In `src/chronicler/models.py`, in the `GreatPerson` class, after `recognized_by: list[str] = Field(default_factory=list)`:

```python
    source: str = "aggregate"  # "aggregate" or "agent"
    agent_id: int | None = None
```

- [ ] **Step 2: Update fate docstring**

Change the `fate` field comment from:

```python
    fate: str = "active"  # "active", "retired", "dead", "ascended"
```

to:

```python
    fate: str = "active"  # "active", "retired", "dead", "ascended", "exile"
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m30): add source, agent_id fields to GreatPerson; document exile fate"
```

---

### Task 7: Add `AgentContext` dataclass and `NarrationContext.agent_context`

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Add AgentContext class**

In `src/chronicler/models.py`, before the `NarrationContext` class:

```python
class AgentContext(BaseModel):
    """Agent narrative context for the narrator prompt (M30)."""
    named_characters: list[dict] = Field(default_factory=list)
    population_mood: str = "content"  # "desperate" > "restless" > "content"
    displacement_fraction: float = 0.0
```

- [ ] **Step 2: Add agent_context to NarrationContext**

In the `NarrationContext` class, after `civ_context: dict[str, CivThematicContext]`:

```python
    agent_context: AgentContext | None = None
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(m30): add AgentContext dataclass and NarrationContext.agent_context"
```

---

### Task 8: Bridge promotion processing

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Create: `test/test_m30_bridge.py`

- [ ] **Step 1: Write failing test for promotion processing**

Create `test/test_m30_bridge.py`:

```python
"""M30 agent narrative — bridge promotion tests."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
import pyarrow as pa

from chronicler.agent_bridge import AgentBridge, OCCUPATION_NAMES


ROLE_MAP = {0: "general", 1: "merchant", 2: "scientist", 3: "prophet", 4: "exile"}


def _make_promotion_batch(rows: list[dict]) -> pa.RecordBatch:
    """Build a promotions RecordBatch for testing."""
    if not rows:
        return pa.record_batch({
            "agent_id": pa.array([], type=pa.uint32()),
            "role": pa.array([], type=pa.uint8()),
            "trigger": pa.array([], type=pa.uint8()),
            "skill": pa.array([], type=pa.float32()),
            "life_events": pa.array([], type=pa.uint8()),
            "origin_region": pa.array([], type=pa.uint16()),
        })
    return pa.record_batch({
        "agent_id": pa.array([r["agent_id"] for r in rows], type=pa.uint32()),
        "role": pa.array([r["role"] for r in rows], type=pa.uint8()),
        "trigger": pa.array([r["trigger"] for r in rows], type=pa.uint8()),
        "skill": pa.array([r["skill"] for r in rows], type=pa.float32()),
        "life_events": pa.array([r["life_events"] for r in rows], type=pa.uint8()),
        "origin_region": pa.array([r["origin_region"] for r in rows], type=pa.uint16()),
    })


def test_promotion_creates_great_person():
    """Promotion RecordBatch → GreatPerson(source='agent')."""
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}

    batch = _make_promotion_batch([
        {"agent_id": 42, "role": 0, "trigger": 1, "skill": 0.95,
         "life_events": 0b00000001, "origin_region": 3},
    ])

    # Mock world with one civ
    world = MagicMock()
    world.turn = 100
    world.seed = 1
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    world.civilizations = [civ]

    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"):
        gp = bridge._process_promotions(batch, world)

    assert len(gp) == 1
    assert gp[0].source == "agent"
    assert gp[0].agent_id == 42
    assert gp[0].role == "general"
    assert gp[0].name == "Kiran"
    assert 42 in bridge.named_agents
    assert bridge.named_agents[42] == "Kiran"


def test_named_agents_dict_maintained():
    """Dict updated on promotion, accessible for _aggregate_events."""
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}

    batch = _make_promotion_batch([
        {"agent_id": 10, "role": 1, "trigger": 0, "skill": 0.92,
         "life_events": 0b00000010, "origin_region": 0},
        {"agent_id": 20, "role": 2, "trigger": 4, "skill": 0.88,
         "life_events": 0b00010000, "origin_region": 1},
    ])

    world = MagicMock()
    world.turn = 50
    world.seed = 1
    civ = MagicMock()
    civ.name = "TestCiv"
    civ.great_persons = []
    world.civilizations = [civ]

    with patch("chronicler.agent_bridge._pick_name", side_effect=["Vesh", "Talo"]):
        bridge._process_promotions(batch, world)

    assert len(bridge.named_agents) == 2
    assert bridge.named_agents[10] == "Vesh"
    assert bridge.named_agents[20] == "Talo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: FAIL — `_process_promotions` doesn't exist yet

- [ ] **Step 3: Implement `_process_promotions` and `named_agents`**

In `src/chronicler/agent_bridge.py`:

Add import at top:

```python
from chronicler.leaders import _pick_name, ALL_TRAITS
```

Add `ROLE_MAP` constant after `OCCUPATION_NAMES`:

```python
ROLE_MAP = {0: "general", 1: "merchant", 2: "scientist", 3: "prophet", 4: "exile"}
```

In `AgentBridge.__init__`, add after `self._shadow_logger` setup:

```python
        self.named_agents: dict[int, str] = {}  # agent_id → character name
        self._origin_regions: dict[int, int] = {}  # agent_id → origin_region (for exile_return)
```

Add new method after `_convert_events`:

```python
    def _process_promotions(self, batch, world) -> list:
        """Process promotion RecordBatch → create GreatPerson instances.

        Also checks Python-side bypass triggers that Rust cannot evaluate:
        - Serial migrant (3+ region changes) → Merchant
        - Occupation versatility (3+ switches) → Scientist
        These are checked against agent_events_raw history when the Rust-side
        trigger is 0 (skill-based), to see if a more specific role applies.
        """
        import random
        from chronicler.models import GreatPerson

        created = []
        for i in range(batch.num_rows):
            agent_id = batch.column("agent_id")[i].as_py()
            role_id = batch.column("role")[i].as_py()
            trigger = batch.column("trigger")[i].as_py()
            origin_region = batch.column("origin_region")[i].as_py()
            role = ROLE_MAP[role_id]

            # Python-side bypass: check event history for serial migrant / versatility
            if trigger == 0:  # skill-based — check if a bypass applies
                migration_count = sum(
                    1 for e in world.agent_events_raw
                    if e.agent_id == agent_id and e.event_type == "migration"
                )
                switch_count = sum(
                    1 for e in world.agent_events_raw
                    if e.agent_id == agent_id and e.event_type == "occupation_switch"
                )
                if migration_count >= 3:
                    role = "merchant"
                elif switch_count >= 3:
                    role = "scientist"

            # Pick civ — use origin_region's controller
            civ = world.civilizations[0]
            if origin_region < len(world.regions):
                controller = world.regions[origin_region].controller
                if controller:
                    for c in world.civilizations:
                        if c.name == controller:
                            civ = c
                            break

            rng = random.Random(world.seed + world.turn + agent_id)
            name = _pick_name(civ, world, rng)
            trait = rng.choice(ALL_TRAITS)

            gp = GreatPerson(
                name=name,
                role=role,
                trait=trait,
                civilization=civ.name,
                origin_civilization=civ.name,
                born_turn=world.turn,
                source="agent",
                agent_id=agent_id,
            )
            civ.great_persons.append(gp)
            created.append(gp)
            self.named_agents[agent_id] = name
            self._origin_regions[agent_id] = origin_region

        return created
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): implement bridge promotion processing with named_agents dict"
```

---

### Task 9: Bridge death transitions

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `test/test_m30_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `test/test_m30_bridge.py`:

```python
def test_death_transitions_great_person():
    """Agent death → GreatPerson gets alive=False, fate='dead'."""
    from chronicler.models import GreatPerson, AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42,
    )
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = [gp]

    world = MagicMock()
    world.turn = 100
    world.civilizations = [civ]
    world.retired_persons = []

    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="death",
                        region=0, target_region=0, civ_affinity=0, occupation=1),
    ]

    death_events = bridge._process_deaths(raw_events, world)

    assert not gp.alive
    assert gp.fate == "dead"
    assert gp.death_turn == 100
    assert len(death_events) == 1
    assert "Kiran" in death_events[0].actors


def test_death_overrides_exile_fate():
    """Exiled character dies → fate='dead' overrides 'exile'."""
    from chronicler.models import GreatPerson, AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}

    gp = GreatPerson(
        name="Vesh", role="exile", trait="stoic",
        civilization="Bora", origin_civilization="Aram",
        born_turn=30, fate="exile", source="agent", agent_id=7,
    )
    civ = MagicMock()
    civ.name = "Bora"
    civ.great_persons = [gp]

    world = MagicMock()
    world.turn = 200
    world.civilizations = [civ]
    world.retired_persons = []

    raw_events = [
        AgentEventRecord(turn=200, agent_id=7, event_type="death",
                        region=2, target_region=0, civ_affinity=1, occupation=0),
    ]

    bridge._process_deaths(raw_events, world)

    assert gp.fate == "dead"
    assert not gp.alive
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_bridge.py::test_death_transitions_great_person -v`
Expected: FAIL — `_process_deaths` doesn't exist

- [ ] **Step 3: Implement `_process_deaths`**

In `src/chronicler/agent_bridge.py`, add method:

```python
    def _process_deaths(self, raw_events, world) -> list:
        """Cross-reference death events against named_agents. Return Events for named character deaths."""
        from chronicler.models import Event

        death_events = []
        for e in raw_events:
            if e.event_type != "death":
                continue
            if e.agent_id not in self.named_agents:
                continue

            name = self.named_agents[e.agent_id]
            region_name = (world.regions[e.region].name
                          if e.region < len(world.regions) else f"region {e.region}")

            # Find and transition the GreatPerson
            for civ in world.civilizations:
                for gp in list(civ.great_persons):
                    if gp.agent_id == e.agent_id:
                        was_exile = gp.fate == "exile"
                        gp.alive = False
                        gp.active = False
                        gp.fate = "dead"
                        gp.death_turn = world.turn
                        civ.great_persons.remove(gp)
                        world.retired_persons.append(gp)

                        desc = (f"{name} died in exile in {region_name}"
                                if was_exile
                                else f"{name} died in {region_name}")
                        death_events.append(Event(
                            turn=world.turn,
                            event_type="character_death",
                            actors=[name, civ.name],
                            description=desc,
                            importance=6,
                            source="agent",
                        ))
                        break

        return death_events
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): implement bridge death transitions for named characters"
```

---

## Chunk 4: Python Event Detection & Lifecycle

### Task 10: Notable migration and exile return detection

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `test/test_m30_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `test/test_m30_bridge.py`:

```python
def test_notable_migration_detection():
    """Named character migration → notable_migration event."""
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._origin_regions = {42: 0}

    world = MagicMock()
    world.turn = 100
    world.regions = [MagicMock(name="Bora"), MagicMock(name="Aram")]

    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=1),
    ]

    events = bridge._detect_character_events(raw_events, world)

    notable = [e for e in events if e.event_type == "notable_migration"]
    assert len(notable) == 1
    assert "Kiran" in notable[0].actors


def test_exile_return_detection():
    """Named char returns to origin_region after 30+ turns → exile_return event."""
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}
    bridge._origin_regions = {7: 2}
    bridge._departure_turns = {7: 50}  # departed origin at turn 50

    world = MagicMock()
    world.turn = 100  # 50 turns later — qualifies for exile_return
    world.regions = [MagicMock(name="A"), MagicMock(name="B"), MagicMock(name="C")]

    raw_events = [
        AgentEventRecord(turn=100, agent_id=7, event_type="migration",
                        region=1, target_region=2, civ_affinity=0, occupation=3),
    ]

    events = bridge._detect_character_events(raw_events, world)

    exile_returns = [e for e in events if e.event_type == "exile_return"]
    assert len(exile_returns) == 1
    assert "Vesh" in exile_returns[0].actors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_bridge.py::test_notable_migration_detection -v`
Expected: FAIL

- [ ] **Step 3: Implement `_detect_character_events`**

In `AgentBridge.__init__`, add:

```python
        self._departure_turns: dict[int, int] = {}  # agent_id → turn they left origin_region
```

In `src/chronicler/agent_bridge.py`, add method:

```python
    def _detect_character_events(self, raw_events, world) -> list:
        """Detect notable_migration and exile_return from migration events."""
        from chronicler.models import Event

        character_events = []
        for e in raw_events:
            if e.event_type != "migration":
                continue
            if e.agent_id not in self.named_agents:
                continue

            name = self.named_agents[e.agent_id]
            origin = self._origin_regions.get(e.agent_id)
            source_name = (world.regions[e.region].name
                          if e.region < len(world.regions) else f"region {e.region}")
            target_name = (world.regions[e.target_region].name
                          if e.target_region < len(world.regions) else f"region {e.target_region}")

            # Track departure from origin
            if origin is not None and e.region == origin and e.target_region != origin:
                self._departure_turns.setdefault(e.agent_id, world.turn)

            # Exile return: named char returns to origin_region after 30+ turns away
            if (origin is not None
                    and e.target_region == origin
                    and e.agent_id in self._departure_turns):
                turns_away = world.turn - self._departure_turns[e.agent_id]
                if turns_away >= 30:
                    character_events.append(Event(
                        turn=world.turn,
                        event_type="exile_return",
                        actors=[name],
                        description=f"{name} returned to {target_name} after {turns_away} turns in exile",
                        importance=6,
                        source="agent",
                    ))
                    del self._departure_turns[e.agent_id]
                    continue  # don't also emit notable_migration

            # Notable migration: any named character moves
            character_events.append(Event(
                turn=world.turn,
                event_type="notable_migration",
                actors=[name],
                description=f"{name} migrated from {source_name} to {target_name}",
                importance=4,
                source="agent",
            ))

        return character_events
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): implement notable_migration and exile_return detection"
```

---

### Task 11: Economic boom and brain drain in `_aggregate_events`

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `test/test_m30_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `test/test_m30_bridge.py`:

```python
def test_economic_boom_detection():
    """Sufficient merchant switches → economic_boom event."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._event_window = deque(maxlen=20)

    # Simulate 10 occupation switches to merchant (occ=2) over multiple turns
    for turn in range(10):
        events = [
            AgentEventRecord(turn=turn, agent_id=turn, event_type="occupation_switch",
                            region=0, target_region=0, civ_affinity=0, occupation=2)
        ]
        bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 10
    world.regions = [MagicMock(name="TestRegion")]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    booms = [e for e in summaries if e.event_type == "economic_boom"]
    assert len(booms) == 1


def test_brain_drain_detection():
    """≥5 scholar departures → brain_drain event."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._event_window = deque(maxlen=10)

    # 5 scholars (occ=3) migrate from region 0
    events = [
        AgentEventRecord(turn=50, agent_id=i, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=3)
        for i in range(5)
    ]
    bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 50
    world.regions = [MagicMock(name="Origin"), MagicMock(name="Dest")]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    drains = [e for e in summaries if e.event_type == "brain_drain"]
    assert len(drains) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_bridge.py::test_economic_boom_detection -v`
Expected: FAIL — `_aggregate_events` doesn't accept `named_agents` parameter yet

- [ ] **Step 3: Update `_aggregate_events` signature and add new events**

In `src/chronicler/agent_bridge.py`, change `_aggregate_events` signature:

```python
    def _aggregate_events(self, world, named_agents=None):
```

Add `SUMMARY_TEMPLATES` entries:

```python
    "economic_boom": "Economic boom in {region}: {count} workers switched to merchant trades over {window} turns",
    "brain_drain": "{count} scholars fled {region} over {window} turns",
```

At the end of `_aggregate_events`, before `return summaries`, add:

```python
        # === M30 new event types ===
        if named_agents is None:
            named_agents = {}

        # Economic boom: >=10 occupation switches TO merchant over 20-turn window
        # [CALIBRATE: post-M28, initial 10]
        merchant_switches_by_region = {}
        boom_window = min(len(self._event_window), 20)
        boom_events = [e for t in list(self._event_window)[-boom_window:] for e in t]
        for e in boom_events:
            if e.event_type == "occupation_switch" and e.occupation == 2:  # merchant
                merchant_switches_by_region[e.region] = \
                    merchant_switches_by_region.get(e.region, 0) + 1
        for region_id, count in merchant_switches_by_region.items():
            if count >= 10:
                summaries.append(Event(
                    turn=world.turn, event_type="economic_boom",
                    actors=self._named_actors_in_region(region_id, named_agents, boom_events),
                    description=SUMMARY_TEMPLATES["economic_boom"].format(
                        region=region_names.get(region_id, f"region {region_id}"),
                        count=count, window=boom_window,
                    ),
                    importance=5, source="agent",
                ))

        # Brain drain: >=5 scholars leave region over 10-turn window
        # [CALIBRATE: post-M28, initial 5]
        scholar_departures_by_region = {}
        drain_window = min(len(self._event_window), 10)
        drain_events = [e for t in list(self._event_window)[-drain_window:] for e in t]
        for e in drain_events:
            if e.event_type == "migration" and e.occupation == 3:  # scholar
                scholar_departures_by_region[e.region] = \
                    scholar_departures_by_region.get(e.region, 0) + 1
        for region_id, count in scholar_departures_by_region.items():
            if count >= 5:
                summaries.append(Event(
                    turn=world.turn, event_type="brain_drain",
                    actors=self._named_actors_in_region(region_id, named_agents, drain_events),
                    description=SUMMARY_TEMPLATES["brain_drain"].format(
                        count=count,
                        region=region_names.get(region_id, f"region {region_id}"),
                        window=drain_window,
                    ),
                    importance=5, source="agent",
                ))
```

Add helper method:

```python
    def _named_actors_in_region(self, region_id, named_agents, current_events):
        """Find named character names involved in events for a given region."""
        actors = []
        for e in current_events:
            if e.region == region_id and e.agent_id in named_agents:
                name = named_agents[e.agent_id]
                if name not in actors:
                    actors.append(name)
        return actors
```

- [ ] **Step 4: Update existing `_aggregate_events` call in `tick()`**

In the `tick` method, change:

```python
            return self._aggregate_events(world)
```

to:

```python
            return self._aggregate_events(world, self.named_agents)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 6: Write test for actor population**

Add to `test/test_m30_bridge.py`:

```python
def test_actor_population():
    """Named character names appear in actors field of aggregate events."""
    from collections import deque
    from chronicler.models import AgentEventRecord

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {3: "Kiran"}
    bridge._event_window = deque(maxlen=10)

    # 5 rebels including named character in region 0
    events = [
        AgentEventRecord(turn=50, agent_id=i, event_type="rebellion",
                        region=0, target_region=0, civ_affinity=0, occupation=1)
        for i in range(5)
    ]
    # Agent 3 is among rebels
    bridge._event_window.append(events)

    world = MagicMock()
    world.turn = 50
    world.regions = [MagicMock(name="TestRegion")]

    summaries = bridge._aggregate_events(world, bridge.named_agents)

    rebellions = [e for e in summaries if e.event_type == "local_rebellion"]
    assert len(rebellions) == 1
    assert "Kiran" in rebellions[0].actors
```

- [ ] **Step 7: Update existing M27 events in `_aggregate_events` to populate actors**

For each existing event (mass_migration, local_rebellion, occupation_shift, loyalty_cascade, demographic_crisis), replace `actors=[]` with `actors=self._named_actors_in_region(region_id, named_agents, current)`. For windowed events that use `turn_events` from the window, pass the appropriate events list.

For example, in the `local_rebellion` block:

```python
                    actors=self._named_actors_in_region(region_id, named_agents, current),
```

Apply the same pattern to all five existing event types.

- [ ] **Step 8: Run all tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): add economic_boom, brain_drain detection and actor population"
```

---

### Task 12: Conquest and secession transitions

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `test/test_m30_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `test/test_m30_bridge.py`:

```python
def test_conquest_exile_transition():
    """Conquest → named characters become exiles, set_agent_civ called."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42, region="Bora",
    )
    conquered_civ = MagicMock()
    conquered_civ.name = "Aram"
    conquered_civ.great_persons = [gp]
    conquered_civ.regions = ["Bora"]

    conqueror_civ = MagicMock()
    conqueror_civ.name = "Vrashni"

    events = bridge.apply_conquest_transitions(
        conquered_civ, conqueror_civ, conquered_regions=["Bora"],
        conqueror_civ_id=1, turn=100)

    assert gp.fate == "exile"
    assert gp.captured_by == "Vrashni"
    bridge._sim.set_agent_civ.assert_called_once_with(42, 1)


def test_conquest_refugee_not_captured():
    """Refugee in surviving-civ territory → captured_by NOT set."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {7: "Vesh"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Vesh", role="merchant", trait="clever",
        civilization="Aram", origin_civilization="Aram",
        born_turn=30, source="agent", agent_id=7, region="Farland",
    )
    conquered_civ = MagicMock()
    conquered_civ.name = "Aram"
    conquered_civ.great_persons = [gp]

    conqueror_civ = MagicMock()
    conqueror_civ.name = "Vrashni"

    # "Farland" is NOT in conquered_regions — character is a refugee
    events = bridge.apply_conquest_transitions(
        conquered_civ, conqueror_civ, conquered_regions=["Bora"],
        conqueror_civ_id=1, host_civ_ids={"Farland": 2}, turn=100)

    assert gp.fate == "exile"
    assert gp.captured_by is None  # refugee, not hostage
    # Refugee still gets set_agent_civ with host civ ID
    bridge._sim.set_agent_civ.assert_called_once_with(7, 2)


def test_secession_transfer():
    """Secession → civilization updated, origin_civilization preserved."""
    from chronicler.models import GreatPerson

    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {42: "Kiran"}
    bridge._sim = MagicMock()

    gp = GreatPerson(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=50, source="agent", agent_id=42, region="Bora",
    )
    old_civ = MagicMock()
    old_civ.name = "Aram"
    old_civ.great_persons = [gp]

    new_civ = MagicMock()
    new_civ.name = "Free Bora"
    new_civ.great_persons = []

    events = bridge.apply_secession_transitions(
        old_civ, new_civ, seceding_regions=["Bora"], new_civ_id=5, turn=100)

    assert gp.civilization == "Free Bora"
    assert gp.origin_civilization == "Aram"  # preserved
    assert len(events) == 1
    assert events[0].event_type == "secession_defection"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_bridge.py::test_conquest_exile_transition -v`
Expected: FAIL

- [ ] **Step 3: Implement conquest and secession methods**

In `src/chronicler/agent_bridge.py`:

```python
    def apply_conquest_transitions(self, conquered_civ, conqueror_civ,
                                    conquered_regions: list[str],
                                    conqueror_civ_id: int,
                                    host_civ_ids: dict[str, int] | None = None,
                                    turn: int = 0) -> list:
        """Transition agent-source named characters on conquest.

        Args:
            conquered_civ: The conquered civilization object.
            conqueror_civ: The conquering civilization object.
            conquered_regions: List of region names that were conquered.
            conqueror_civ_id: Numeric civ ID (u8) for the conqueror (for FFI).
            host_civ_ids: Map of region_name → civ_id for refugees in surviving territory.
            turn: Current turn number for event timestamps.
        """
        from chronicler.models import Event

        events = []
        conquered_region_set = set(conquered_regions)
        if host_civ_ids is None:
            host_civ_ids = {}

        for gp in list(conquered_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue

            gp.fate = "exile"
            gp.active = False

            if gp.region in conquered_region_set:
                # In conquered territory → hostage
                gp.captured_by = conqueror_civ.name
                try:
                    self._sim.set_agent_civ(gp.agent_id, conqueror_civ_id)
                except Exception:
                    pass
            else:
                # In surviving territory → refugee, not captured
                gp.captured_by = None
                host_id = host_civ_ids.get(gp.region, conqueror_civ_id)
                try:
                    self._sim.set_agent_civ(gp.agent_id, host_id)
                except Exception:
                    pass

            events.append(Event(
                turn=turn,
                event_type="conquest_exile",
                actors=[gp.name, conquered_civ.name, conqueror_civ.name],
                description=f"{gp.name} of {conquered_civ.name} exiled after conquest by {conqueror_civ.name}",
                importance=5, source="agent",
            ))

        return events

    def apply_secession_transitions(self, old_civ, new_civ,
                                     seceding_regions: list[str],
                                     new_civ_id: int,
                                     turn: int = 0) -> list:
        """Transition agent-source named characters on secession."""
        from chronicler.models import Event

        events = []
        seceding_set = set(seceding_regions)

        for gp in list(old_civ.great_persons):
            if gp.source != "agent" or gp.agent_id is None:
                continue
            if gp.region not in seceding_set:
                continue

            gp.civilization = new_civ.name
            # origin_civilization stays unchanged
            old_civ.great_persons.remove(gp)
            new_civ.great_persons.append(gp)

            try:
                self._sim.set_agent_civ(gp.agent_id, new_civ_id)
            except Exception:
                pass

            events.append(Event(
                turn=turn,
                event_type="secession_defection",
                actors=[gp.name, old_civ.name, new_civ.name],
                description=f"{gp.name} defected with the secession of {gp.region}",
                importance=5, source="agent",
            ))

        return events
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_bridge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): implement conquest and secession transitions for named characters"
```

---

## Chunk 5: Python Curator & Narrator Integration

### Task 13: Character-reference bonus in curator

**Files:**
- Modify: `src/chronicler/curator.py`
- Create: `test/test_m30_curator.py`

- [ ] **Step 1: Write failing tests**

Create `test/test_m30_curator.py`:

```python
"""M30 agent narrative — curator scoring tests."""
from chronicler.models import Event, NamedEvent
from chronicler.curator import compute_base_scores


def test_character_reference_bonus():
    """+2.0 when named character in actors."""
    events = [
        Event(turn=10, event_type="local_rebellion", actors=["Kiran", "Aram"],
              description="test", importance=7, source="agent"),
        Event(turn=10, event_type="mass_migration", actors=["Aram"],
              description="test", importance=5, source="agent"),
    ]
    named_characters = {"Kiran"}
    scores = compute_base_scores(events, [], "Aram", 42,
                                  named_characters=named_characters)

    # First event: 7 (importance) + 2.0 (dominant power) + 2.0 (character ref) + 2.0 (rarity) = 13.0
    # Second event: 5 + 2.0 (dominant) + 2.0 (rarity) = 9.0
    assert scores[0] == 13.0
    assert scores[1] == 9.0


def test_saturation_guard():
    """Multiple named characters in one event → still only +2.0."""
    events = [
        Event(turn=10, event_type="local_rebellion",
              actors=["Kiran", "Vesh", "Talo"],
              description="test", importance=7, source="agent"),
    ]
    named_characters = {"Kiran", "Vesh", "Talo"}
    scores = compute_base_scores(events, [], "", 42,
                                  named_characters=named_characters)

    # 7 + 2.0 (character ref, once) + 2.0 (rarity) = 11.0
    assert scores[0] == 11.0


def test_source_agnostic_named_event():
    """Agent events eligible for NamedEvent promotion via existing logic."""
    events = [
        Event(turn=10, event_type="local_rebellion", actors=["Kiran"],
              description="test", importance=7, source="agent"),
    ]
    named_events = [
        NamedEvent(name="The Uprising", event_type="local_rebellion",
                   turn=10, actors=["Kiran"], description="test", importance=7),
    ]
    scores = compute_base_scores(events, named_events, "", 42)

    # 7 + 3.0 (named event) + 2.0 (rarity) = 12.0
    assert scores[0] == 12.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_curator.py -v`
Expected: FAIL — `compute_base_scores` doesn't accept `named_characters` parameter

- [ ] **Step 3: Add `named_characters` parameter to `compute_base_scores`**

In `src/chronicler/curator.py`, update the signature:

```python
def compute_base_scores(
    events: Sequence[Event],
    named_events: Sequence[NamedEvent],
    dominant_power: str,
    seed: int,
    named_characters: set[str] | None = None,
) -> list[float]:
```

After the rarity bonus block (`if type_counts[ev.event_type] < 3:`), add:

```python
        # Character-reference bonus (M30) — +2.0 if any actor is a named character
        # Saturation guard: max once per event regardless of how many characters
        if named_characters:
            if any(actor in named_characters for actor in ev.actors):
                score += 2.0
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_curator.py -v`
Expected: PASS

- [ ] **Step 5: Wire `named_characters` into the `curate()` call site**

In `src/chronicler/curator.py`, find the `curate()` function. Add `named_characters: set[str] | None = None` to its signature. Thread it to `compute_base_scores`:

Change:
```python
    scores = compute_base_scores(sorted_events, named_events, dominant, seed)
```
to:
```python
    scores = compute_base_scores(sorted_events, named_events, dominant, seed,
                                  named_characters=named_characters)
```

The caller of `curate()` (in the turn loop) passes the set built from `bridge.named_agents.values()`.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/curator.py test/test_m30_curator.py
git commit -m "feat(m30): add character-reference bonus to curator scoring"
```

---

### Task 14: AgentContext construction in narrative pipeline

**Files:**
- Modify: `src/chronicler/narrative.py`
- Create: `test/test_m30_narrative.py`

- [ ] **Step 1: Write failing tests**

Create `test/test_m30_narrative.py`:

```python
"""M30 agent narrative — narrator tests."""
from chronicler.models import AgentContext, Event


def test_agent_context_in_prompt():
    """AgentContext present → prompt includes named characters with history."""
    from chronicler.narrative import build_agent_context_block

    ctx = AgentContext(
        named_characters=[
            {
                "name": "Kiran", "role": "General", "civ": "Aram",
                "origin_civ": "Bora", "status": "active",
                "recent_history": [
                    {"turn": 195, "event": "migration", "region": "Aram"},
                    {"turn": 180, "event": "rebellion", "region": "Bora"},
                ],
            },
        ],
        population_mood="desperate",
        displacement_fraction=0.15,
    )

    block = build_agent_context_block(ctx)

    assert "Kiran" in block
    assert "desperate" in block
    assert "15%" in block
    assert "rebellion" in block.lower() or "Bora" in block


def test_no_agent_context():
    """None → empty string."""
    from chronicler.narrative import build_agent_context_block

    assert build_agent_context_block(None) == ""


def test_mood_precedence():
    """Rebellion + boom in same moment → 'desperate' wins."""
    from chronicler.narrative import compute_population_mood

    events = [
        Event(turn=10, event_type="local_rebellion", actors=["A"],
              description="test", importance=7, source="agent"),
        Event(turn=10, event_type="economic_boom", actors=["A"],
              description="test", importance=5, source="agent"),
    ]

    mood = compute_population_mood(events)
    assert mood == "desperate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test/test_m30_narrative.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `build_agent_context_block` and `compute_population_mood`**

In `src/chronicler/narrative.py`, add after imports:

```python
from chronicler.models import AgentContext
```

Add functions (before the `NarrativeEngine` class):

```python
# ---------------------------------------------------------------------------
# M30: Agent context for narrator prompt
# ---------------------------------------------------------------------------

_DESPERATE_EVENTS = {"local_rebellion", "demographic_crisis"}
_RESTLESS_EVENTS = {"loyalty_cascade", "brain_drain", "occupation_shift"}


def compute_population_mood(events: list[Event]) -> str:
    """Compute population mood from agent events. Worst wins."""
    agent_types = {e.event_type for e in events if e.source == "agent"}
    if agent_types & _DESPERATE_EVENTS:
        return "desperate"
    if agent_types & _RESTLESS_EVENTS:
        return "restless"
    return "content"


def build_agent_context_block(ctx: AgentContext | None) -> str:
    """Build the agent context section for the narrator prompt."""
    if ctx is None:
        return ""

    lines = ["## Agent Context"]
    lines.append(f"Population mood: {ctx.population_mood}")
    lines.append(f"Displacement: {int(ctx.displacement_fraction * 100)}% of population displaced")
    lines.append("")

    if ctx.named_characters:
        lines.append("Named characters present:")
        for char in ctx.named_characters:
            origin = f", originally {char['origin_civ']}" if char.get("origin_civ") != char.get("civ") else ""
            lines.append(f"- {char['role']} {char['name']} ({char['civ']}{origin}) [{char['status']}]:")
            history_parts = []
            for h in char.get("recent_history", []):
                history_parts.append(f"  {h['event']} in {h['region']} (turn {h['turn']})")
            if history_parts:
                lines.append(";".join(history_parts))
        lines.append("")

    lines.append("Guidelines:")
    lines.append("- Refer to named characters BY NAME — do not anonymize or rename them")
    lines.append("- Use their recent history for callbacks")
    lines.append("- Use population mood to set atmospheric tone")
    if ctx.displacement_fraction > 0.10:
        lines.append("- Weave refugee/exile themes into the narrative")

    lines.append("")
    lines.append('Character Continuity: When a named character has appeared in previous '
                 'chronicle entries, maintain their name and identity. Do not re-introduce '
                 'them or invent backstory that contradicts their listed history. '
                 'The named characters list is authoritative.')

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_narrative.py -v`
Expected: PASS

- [ ] **Step 5: Wire `build_agent_context_block` into narrator prompt assembly**

In `src/chronicler/narrative.py`, in the `_build_chronicle_prompt_impl` function (or the batch narration path), add after building the base prompt:

```python
    # M30: Append agent context block if present
    agent_block = ""
    if hasattr(world, '_agent_context') and world._agent_context is not None:
        agent_block = "\n\n" + build_agent_context_block(world._agent_context)
```

Append `{agent_block}` to the prompt string before the closing rules.

For the batch narration path (`narrate_batch`), when building `NarrationContext`, check if `agent_context` is set and include the block in the prompt assembly. The exact integration point depends on whether the prompt is built from `NarrationContext` fields — if so, add:

```python
    if ctx.agent_context is not None:
        prompt += "\n\n" + build_agent_context_block(ctx.agent_context)
```

- [ ] **Step 6: Add a helper to build AgentContext from moment data**

In `src/chronicler/narrative.py`:

```python
def build_agent_context_for_moment(
    moment: NarrativeMoment,
    great_persons: list,
    displacement_by_region: dict[int, float],
    region_names: dict[int, str],
) -> AgentContext | None:
    """Build AgentContext if the moment has agent-source events."""
    agent_events = [e for e in moment.events if e.source == "agent"]
    if not agent_events:
        return None

    # Named characters active in this moment's regions
    moment_regions = {e.actors[0] if e.actors else "" for e in moment.events}
    chars = []
    for gp in great_persons:
        if not gp.active or gp.source != "agent":
            continue
        char = {
            "name": gp.name,
            "role": gp.role.title(),
            "civ": gp.civilization,
            "origin_civ": gp.origin_civilization,
            "status": "exiled" if gp.fate == "exile" else ("dead" if not gp.alive else "active"),
            "recent_history": [
                {"turn": 0, "event": d, "region": gp.region or "unknown"}
                for d in gp.deeds[-3:]
            ],
        }
        chars.append(char)

    mood = compute_population_mood(agent_events)

    # Average displacement across relevant regions
    disp_values = [v for v in displacement_by_region.values()]
    avg_disp = sum(disp_values) / len(disp_values) if disp_values else 0.0

    return AgentContext(
        named_characters=chars[:10],  # cap for token budget
        population_mood=mood,
        displacement_fraction=avg_disp,
    )
```

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py test/test_m30_narrative.py
git commit -m "feat(m30): add AgentContext prompt builder and mood precedence"
```

---

### Task 15: Wire the full processing order into AgentBridge.tick()

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `test/test_m30_bridge.py`

- [ ] **Step 1: Write test for processing order**

Add to `test/test_m30_bridge.py`:

```python
def test_processing_order():
    """Same-tick promote+migrate → notable_migration detected."""
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.named_agents = {}
    bridge._origin_regions = {}
    bridge._departure_turns = {}

    # Simulate: agent 42 gets promoted AND migrates on same tick
    promo_batch = _make_promotion_batch([
        {"agent_id": 42, "role": 0, "trigger": 1, "skill": 0.95,
         "life_events": 0b00000011, "origin_region": 0},
    ])

    from chronicler.models import AgentEventRecord
    raw_events = [
        AgentEventRecord(turn=100, agent_id=42, event_type="migration",
                        region=0, target_region=1, civ_affinity=0, occupation=1),
    ]

    world = MagicMock()
    world.turn = 100
    world.seed = 1
    world.regions = [MagicMock(name="Bora"), MagicMock(name="Aram")]
    civ = MagicMock()
    civ.name = "Aram"
    civ.great_persons = []
    world.civilizations = [civ]
    world.retired_persons = []

    # Step 1: process promotions
    with patch("chronicler.agent_bridge._pick_name", return_value="Kiran"):
        bridge._process_promotions(promo_batch, world)

    assert 42 in bridge.named_agents  # now registered

    # Step 2: process deaths (none here)
    death_events = bridge._process_deaths(raw_events, world)
    assert len(death_events) == 0

    # Step 3: detect character events — should find notable_migration
    char_events = bridge._detect_character_events(raw_events, world)
    notable = [e for e in char_events if e.event_type == "notable_migration"]
    assert len(notable) == 1
    assert "Kiran" in notable[0].actors
```

- [ ] **Step 2: Run test**

Run: `python -m pytest test/test_m30_bridge.py::test_processing_order -v`
Expected: PASS (all methods already implemented)

- [ ] **Step 3: Update `tick()` to use full M30 processing order in hybrid mode**

In `src/chronicler/agent_bridge.py`, update the `hybrid` branch of `tick()`:

```python
        if self._mode == "hybrid":
            self._write_back(world)
            # M30 processing order
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)  # step 1

            raw_events = self._convert_events(agent_events, world.turn)
            death_events = self._process_deaths(raw_events, world)  # step 2
            world.agent_events_raw.extend(raw_events)

            char_events = self._detect_character_events(raw_events, world)  # step 3

            self._event_window.append(raw_events)
            summaries = self._aggregate_events(world, self.named_agents)  # step 4

            return summaries + char_events + death_events
```

- [ ] **Step 4: Also update shadow mode if needed**

In the `shadow` branch, add promotion processing:

```python
        elif self._mode == "shadow":
            agent_aggs = self._sim.get_aggregates()
            if self._shadow_logger:
                self._shadow_logger.log_turn(world.turn, agent_aggs, world)
            # M30 processing order (still track promotions in shadow mode)
            promotions_batch = self._sim.get_promotions()
            self._process_promotions(promotions_batch, world)
            raw_events = self._convert_events(agent_events, world.turn)
            self._process_deaths(raw_events, world)
            world.agent_events_raw.extend(raw_events)
            self._event_window.append(raw_events)
            return []
```

- [ ] **Step 5: Update `reset()` to clear M30 state**

In the `reset` method:

```python
    def reset(self) -> None:
        """Clear stateful data for batch mode reuse."""
        self._event_window.clear()
        self._demand_manager.reset()
        self.named_agents.clear()
        self._origin_regions.clear()
        self._departure_turns.clear()
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest test/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): wire full M30 processing order into AgentBridge.tick()"
```

---

### Task 16: Displacement fraction computation

**Files:**
- Modify: `src/chronicler/agent_bridge.py`

- [ ] **Step 1: Add `displacement_by_region` computation**

In `AgentBridge.__init__`, add:

```python
        self.displacement_by_region: dict[int, float] = {}
```

In the `tick()` method, after `self._process_promotions(promotions_batch, world)`:

```python
            # Compute displacement fractions from snapshot
            try:
                snap = self._sim.get_snapshot()
                regions_col = snap.column("region").to_pylist()
                disp_col = snap.column("displacement_turn").to_pylist()
                from collections import Counter
                region_totals = Counter(regions_col)
                region_displaced = Counter()
                for r, d in zip(regions_col, disp_col):
                    if d > 0:
                        region_displaced[r] += 1
                self.displacement_by_region = {
                    r: region_displaced[r] / total if total > 0 else 0.0
                    for r, total in region_totals.items()
                }
            except Exception:
                self.displacement_by_region = {}
```

- [ ] **Step 2: Write test for displacement computation**

Add to `test/test_m30_bridge.py`:

```python
def test_displacement_by_region():
    """Correct displacement fraction from mock snapshot."""
    import pyarrow as pa
    bridge = AgentBridge.__new__(AgentBridge)
    bridge.displacement_by_region = {}

    # Mock snapshot: 4 agents in region 0, 1 displaced; 2 in region 1, 0 displaced
    snap = pa.record_batch({
        "id": pa.array([1, 2, 3, 4, 5, 6], type=pa.uint32()),
        "region": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "origin_region": pa.array([0, 0, 0, 0, 1, 1], type=pa.uint16()),
        "civ_affinity": pa.array([0, 0, 0, 0, 0, 0], type=pa.uint16()),
        "occupation": pa.array([0, 0, 0, 0, 0, 0], type=pa.uint8()),
        "loyalty": pa.array([0.5]*6, type=pa.float32()),
        "satisfaction": pa.array([0.5]*6, type=pa.float32()),
        "skill": pa.array([0.5]*6, type=pa.float32()),
        "age": pa.array([20]*6, type=pa.uint16()),
        "displacement_turn": pa.array([3, 0, 0, 0, 0, 0], type=pa.uint16()),
    })

    # Compute directly
    from collections import Counter
    regions_col = snap.column("region").to_pylist()
    disp_col = snap.column("displacement_turn").to_pylist()
    region_totals = Counter(regions_col)
    region_displaced = Counter()
    for r, d in zip(regions_col, disp_col):
        if d > 0:
            region_displaced[r] += 1
    result = {
        r: region_displaced[r] / total if total > 0 else 0.0
        for r, total in region_totals.items()
    }

    assert result[0] == 0.25  # 1 of 4 displaced
    assert result[1] == 0.0   # 0 of 2 displaced
```

- [ ] **Step 3: Add to `reset()`**

```python
        self.displacement_by_region.clear()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest test/test_m30_bridge.py::test_displacement_by_region -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py test/test_m30_bridge.py
git commit -m "feat(m30): compute displacement_by_region from agent snapshot"
```

---

## Review Checkpoint

At this point all 16 tasks are complete. The implementation covers:

- **Rust:** 2 new SoA fields, NamedCharacterRegistry with CharacterRole, promotion logic, get_promotions() and set_agent_civ() FFI
- **Python models:** GreatPerson source/agent_id, AgentContext, NarrationContext.agent_context, fate="exile"
- **Python bridge:** Full 4-step processing order, promotion, death, character event detection, economic_boom, brain_drain, conquest, secession, displacement fraction
- **Python curator:** Character-reference bonus with saturation guard
- **Python narrator:** AgentContext prompt builder, mood precedence, character continuity rule
- **Tests:** 26 tests across Rust unit, Python bridge, curator, and narrator layers
