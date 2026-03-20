# M51: Multi-Generational Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When agents die, their strongest memories transfer to children as legacy memories, and dynasty lineage feeds a bounded succession scoring system with per-civ royal numbering.

**Architecture:** Two tracks — Track A extends the existing Rust memory ring buffer with a legacy bitmask and death-path intent collection. Track B adds Python-side Leader lineage fields, a per-civ regnal name registry, and an additive dynasty legitimacy score on GP succession candidates. Both tracks share the M39 parent_id lineage contract.

**Tech Stack:** Rust (chronicler-agents crate), Python (src/chronicler/), pytest, cargo nextest

**Spec:** `docs/superpowers/specs/2026-03-20-m51-multi-generational-memory-design.md`

---

## File Structure

### Rust (Track A)

| File | Change | Responsibility |
|------|--------|---------------|
| `chronicler-agents/src/pool.rs` | Modify | Add `memory_is_legacy: Vec<u8>` SoA field — in `new()` constructor, both spawn branches |
| `chronicler-agents/src/memory.rs` | Modify | Extend `MemoryIntent` with `is_legacy` + `decay_factor_override`, modify `write_single_memory()` for override/bitmask, add `extract_legacy_memories()` helper |
| `chronicler-agents/src/tick.rs` | Modify | Add legacy intent collection in death processing block |
| `chronicler-agents/src/agent.rs` | Modify | Add `LEGACY_MIN_INTENSITY` and `LEGACY_MAX_MEMORIES` constants |
| `chronicler-agents/src/ffi.rs` | Modify | Extend `get_agent_memories()` return type to 6-tuple |

### Python (Track B)

| File | Change | Responsibility |
|------|--------|---------------|
| `src/chronicler/models.py` | Modify | Add `Leader` fields (`agent_id`, `dynasty_id`, `throne_name`, `regnal_ordinal`), add `Civilization.regnal_name_counts` |
| `src/chronicler/leaders.py` | Modify | Add `_pick_regnal_name()`, `to_roman()`, `strip_title()` helpers |
| `src/chronicler/factions.py` | Modify | Extend GP candidate dict, wire legitimacy scoring, lineage bridge in GP winner block |
| `src/chronicler/dynasties.py` | Modify | Add `compute_dynasty_legitimacy()` function |
| `src/chronicler/agent_bridge.py` | Modify | Update memory sync dict for 6-tuple |
| `src/chronicler/narrative.py` | Modify | Legacy memory rendering, succession legitimacy phrasing |
| `src/chronicler/world_gen.py` | Modify | Seed regnal metadata on founding leaders |
| `src/chronicler/politics.py` | Modify | Seed regnal metadata on secession + restored civ leaders |
| `src/chronicler/succession.py` | Modify | Seed regnal metadata on exile restoration leaders |
| `src/chronicler/scenario.py` | Modify | Seed regnal metadata on scenario overrides |

### Tests

| File | New/Modify | Covers |
|------|------------|--------|
| `chronicler-agents/tests/test_legacy_memory.rs` | Create | Rust unit + integration tests for Track A |
| `tests/test_m51_regnal.py` | Create | Python tests for Track B (regnal naming, legitimacy scoring) |
| `tests/test_m51_legacy_integration.py` | Create | Python FFI + narration integration tests |

---

## Task 1: SoA Field + MemoryIntent Extension

**Files:**
- Modify: `chronicler-agents/src/pool.rs:52-59` (SoA memory fields), `:182-186` (reuse spawn), `:231-237` (grow spawn)
- Modify: `chronicler-agents/src/memory.rs:72-77` (MemoryIntent struct)
- Test: `chronicler-agents/tests/test_legacy_memory.rs` (new file)

- [ ] **Step 1: Write failing test — MemoryIntent with legacy fields**

In `chronicler-agents/tests/test_legacy_memory.rs`:

```rust
use chronicler_agents::memory::MemoryIntent;

#[test]
fn test_memory_intent_legacy_fields() {
    let intent = MemoryIntent {
        agent_slot: 0,
        event_type: 0, // Famine
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(7), // ~100 turn half-life
    };
    assert!(intent.is_legacy);
    assert_eq!(intent.decay_factor_override, Some(7));
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_memory_intent_legacy_fields`
Expected: FAIL — `is_legacy` and `decay_factor_override` fields don't exist

- [ ] **Step 3: Extend MemoryIntent struct**

In `chronicler-agents/src/memory.rs`, replace the struct at line 72:

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

Update ALL existing MemoryIntent construction sites in `tick.rs` to include `is_legacy: false, decay_factor_override: None`. There are 11 intent collection sites — search for `MemoryIntent {` in tick.rs and add the two new fields to each.

- [ ] **Step 4: Add `memory_is_legacy` SoA field to AgentPool**

In `chronicler-agents/src/pool.rs`, add after the existing memory SoA fields (~line 59):

```rust
pub memory_is_legacy: Vec<u8>,  // per-agent bitmask, bit N = slot N is legacy
```

In the `new()` constructor (line 88-134), add to the `Self { ... }` initializer alongside other memory fields:

```rust
memory_is_legacy: Vec::with_capacity(capacity),
```

In the reuse spawn branch (~line 186), add after `memory_count` zeroing:

```rust
self.memory_is_legacy[slot] = 0;
```

In the grow spawn branch (~line 237), add after `memory_count` push:

```rust
self.memory_is_legacy.push(0);
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cargo nextest run -p chronicler-agents test_memory_intent_legacy_fields`
Expected: PASS

- [ ] **Step 6: Commit**

```
git add chronicler-agents/src/pool.rs chronicler-agents/src/memory.rs chronicler-agents/src/tick.rs chronicler-agents/tests/test_legacy_memory.rs
git commit -m "feat(m51): memory_is_legacy SoA field + MemoryIntent extension"
```

---

## Task 2: write_single_memory — Decay Override + Legacy Bitmask

**Files:**
- Modify: `chronicler-agents/src/memory.rs:143-167` (write_single_memory)
- Test: `chronicler-agents/tests/test_legacy_memory.rs`

- [ ] **Step 1: Write failing test — legacy memory gets overridden decay factor**

```rust
use chronicler_agents::pool::AgentPool;
use chronicler_agents::memory::{MemoryIntent, write_single_memory, factor_from_half_life};
use chronicler_agents::agent::LEGACY_HALF_LIFE;

#[test]
fn test_write_legacy_memory_decay_override() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);
    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: 0, // Famine — would normally get famine decay
        source_civ: 1,
        intensity: -45,
        is_legacy: true,
        decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 100);

    // Decay factor should be legacy rate, not famine rate
    assert_eq!(pool.memory_decay_factors[slot][0], legacy_factor);
    // Legacy bitmask should have bit 0 set
    assert_eq!(pool.memory_is_legacy[slot] & 1, 1);
    // Event type preserved as Famine (0), not Legacy (14)
    assert_eq!(pool.memory_event_types[slot][0], 0);
}
```

- [ ] **Step 2: Write failing test — legacy bit cleared on eviction**

```rust
#[test]
fn test_legacy_bit_cleared_on_eviction() {
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Fill all 8 slots — first one is legacy at intensity 10
    let legacy_intent = MemoryIntent {
        agent_slot: slot, event_type: 0, source_civ: 1, intensity: -10,
        is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &legacy_intent, 100);

    for i in 1..8 {
        let intent = MemoryIntent {
            agent_slot: slot, event_type: 1, source_civ: 1, intensity: -50,
            is_legacy: false, decay_factor_override: None,
        };
        write_single_memory(&mut pool, &intent, 100 + i as u16);
    }

    // Slot 0 should still be legacy
    assert_eq!(pool.memory_is_legacy[slot] & 1, 1);

    // Write a 9th memory — should evict slot 0 (weakest at |-10|)
    let strong_intent = MemoryIntent {
        agent_slot: slot, event_type: 2, source_civ: 1, intensity: -80,
        is_legacy: false, decay_factor_override: None,
    };
    write_single_memory(&mut pool, &strong_intent, 200);

    // Legacy bit for the evicted slot should be cleared
    // (the evicted slot index may have changed due to swap, so check
    // that total legacy count is 0)
    assert_eq!(pool.memory_is_legacy[slot], 0);
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_write_legacy_memory test_legacy_bit_cleared`
Expected: FAIL — decay override not applied, legacy bit not set

- [ ] **Step 4: Modify write_single_memory**

In `chronicler-agents/src/memory.rs` at `write_single_memory()` (line 143), make three changes:

1. Replace line 166 (`pool.memory_decay_factors[slot][write_idx] = default_decay_factor(intent.event_type);`) with:
```rust
pool.memory_decay_factors[slot][write_idx] = intent
    .decay_factor_override
    .unwrap_or_else(|| default_decay_factor(intent.event_type));
```

2. After setting decay_factor, add legacy bit management:
```rust
if intent.is_legacy {
    pool.memory_is_legacy[slot] |= 1 << write_idx;
} else {
    pool.memory_is_legacy[slot] &= !(1 << write_idx);
}
```

3. In the eviction branch (where `count == 8` and `min_idx` is selected), BEFORE overwriting the slot data, clear the legacy bit:
```rust
// Clear legacy bit for evicted slot
pool.memory_is_legacy[slot] &= !(1 << min_idx);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_write_legacy_memory test_legacy_bit_cleared`
Expected: PASS

- [ ] **Step 6: Commit**

```
git add chronicler-agents/src/memory.rs chronicler-agents/tests/test_legacy_memory.rs
git commit -m "feat(m51): write_single_memory decay override + legacy bitmask"
```

---

## Task 3: Legacy Extraction + Intent Emission in Death Path

**Files:**
- Modify: `chronicler-agents/src/memory.rs` (add `extract_legacy_memories()`)
- Modify: `chronicler-agents/src/agent.rs:197` (add constants)
- Modify: `chronicler-agents/src/tick.rs:387-414` (death processing block)
- Test: `chronicler-agents/tests/test_legacy_memory.rs`

- [ ] **Step 1: Add constants to agent.rs**

After `LEGACY_HALF_LIFE` at line 197:

```rust
pub const LEGACY_MIN_INTENSITY: i8 = 10;   // [CALIBRATE M53] post-halving threshold
pub const LEGACY_MAX_MEMORIES: usize = 2;  // [CALIBRATE M53] top-N extracted on death
```

- [ ] **Step 2: Write failing test — extract_legacy_memories returns top 2 by |intensity|**

```rust
use chronicler_agents::memory::{MemoryIntent, write_single_memory, extract_legacy_memories};

#[test]
fn test_extract_legacy_memories_top_2() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 30,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Write 4 memories with varying intensities
    for (i, intensity) in [(-30i8), (-90), (50), (-10)].iter().enumerate() {
        let intent = MemoryIntent {
            agent_slot: slot, event_type: i as u8, source_civ: 1,
            intensity: *intensity, is_legacy: false, decay_factor_override: None,
        };
        write_single_memory(&mut pool, &intent, 10 + i as u16);
    }

    let legacies = extract_legacy_memories(&pool, slot);
    assert_eq!(legacies.len(), 2);
    // Top 2 by |intensity|: -90 (type 1) and 50 (type 2)
    assert_eq!(legacies[0].0, 1);  // event_type of -90
    assert_eq!(legacies[0].2, -45); // halved: -90 / 2
    assert_eq!(legacies[1].0, 2);  // event_type of 50
    assert_eq!(legacies[1].2, 25); // halved: 50 / 2
}

#[test]
fn test_extract_legacy_memories_filters_below_threshold() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 30,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Write a memory that will be below threshold after halving
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 0, source_civ: 1,
        intensity: 15, // halved to 7, below LEGACY_MIN_INTENSITY (10)
        is_legacy: false, decay_factor_override: None,
    };
    write_single_memory(&mut pool, &intent, 10);

    let legacies = extract_legacy_memories(&pool, slot);
    assert!(legacies.is_empty());
}

#[test]
fn test_extract_legacy_memories_empty_buffer() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 30,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);

    let legacies = extract_legacy_memories(&pool, slot);
    assert!(legacies.is_empty());
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_extract_legacy`
Expected: FAIL — `extract_legacy_memories` not found

- [ ] **Step 4: Implement extract_legacy_memories**

In `chronicler-agents/src/memory.rs`, add:

```rust
/// Extract top LEGACY_MAX_MEMORIES memories by |intensity| for legacy transfer.
/// Returns Vec of (event_type, source_civ, halved_intensity) tuples.
/// Filters out memories where |halved_intensity| < LEGACY_MIN_INTENSITY.
/// Tiebreak: lowest slot index wins.
pub fn extract_legacy_memories(
    pool: &AgentPool,
    slot: usize,
) -> Vec<(u8, u8, i8)> {
    use crate::agent::{LEGACY_MAX_MEMORIES, LEGACY_MIN_INTENSITY};

    let count = pool.memory_count[slot] as usize;
    if count == 0 {
        return Vec::new();
    }

    // Collect (|intensity|, slot_index) pairs, sort descending by |intensity|, tiebreak ascending by index
    let mut ranked: Vec<(i8, usize)> = (0..count)
        .map(|i| (pool.memory_intensities[slot][i], i))
        .collect();
    ranked.sort_by(|a, b| {
        let abs_cmp = (b.0 as i16).abs().cmp(&(a.0 as i16).abs());
        if abs_cmp == std::cmp::Ordering::Equal {
            a.1.cmp(&b.1) // lower index wins tie
        } else {
            abs_cmp
        }
    });

    ranked
        .into_iter()
        .take(LEGACY_MAX_MEMORIES)
        .filter_map(|(intensity, idx)| {
            let halved = intensity / 2; // integer division truncating toward zero
            if (halved as i16).abs() < LEGACY_MIN_INTENSITY as i16 {
                return None;
            }
            Some((
                pool.memory_event_types[slot][idx],
                pool.memory_source_civs[slot][idx],
                halved,
            ))
        })
        .collect()
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_extract_legacy`
Expected: PASS

- [ ] **Step 6: Wire legacy intent emission into death path in tick.rs**

In `chronicler-agents/src/tick.rs`, in the death processing block (after the DeathOfKin intent emission at ~line 410, before `pool.kill(slot)` at line 414):

```rust
// M51: Legacy memory transfer — extract top memories from dying agent
let legacy_memories = crate::memory::extract_legacy_memories(pool, slot);
if !legacy_memories.is_empty() {
    let legacy_decay = crate::memory::factor_from_half_life(crate::agent::LEGACY_HALF_LIFE);
    if let Some(children) = parent_to_children.get(&dying_agent_id) {
        for &child_slot in children {
            if pool.is_alive(child_slot) && pool.ids[child_slot] != 0 {
                for &(event_type, source_civ, halved_intensity) in &legacy_memories {
                    memory_intents.push(crate::memory::MemoryIntent {
                        agent_slot: child_slot,
                        event_type,
                        source_civ,
                        intensity: halved_intensity,
                        is_legacy: true,
                        decay_factor_override: Some(legacy_decay),
                    });
                }
            }
        }
    }
}
```

- [ ] **Step 7: Write semantic preservation tests**

```rust
#[test]
fn test_legacy_utility_preservation() {
    // A legacy Famine memory should produce the same utility modifiers
    // as a direct Famine memory (at lower intensity)
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 0, // Famine
        source_civ: 1, intensity: -45,
        is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 100);
    let mods = compute_memory_utility_modifiers(&pool, slot);
    // Famine memory should boost migrate utility (positive value)
    assert!(mods.migrate > 0.0);
}

#[test]
fn test_legacy_satisfaction_preservation() {
    // Legacy memory contributes to satisfaction score at inherited intensity
    let mut pool = AgentPool::new(16);
    let slot = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 20,
                          0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 3, // Persecution
        source_civ: 1, intensity: -45,
        is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent, 100);
    let score = compute_memory_satisfaction_score(&pool, slot);
    // Negative persecution memory should produce negative satisfaction score
    assert!(score < 0.0);
}

#[test]
fn test_legacy_shared_memory_matching() {
    // Two siblings with legacy Battle from same parent should match
    let mut pool = AgentPool::new(16);
    let slot_a = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 5,
                            0.0, 0.0, 0.0, 0, 0, 0, 0);
    let slot_b = pool.spawn(0, 0, chronicler_agents::agent::Occupation::Farmer, 5,
                            0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);
    // Same event_type, same turn (as if inherited from same parent death)
    for slot in [slot_a, slot_b] {
        let intent = MemoryIntent {
            agent_slot: slot, event_type: 1, // Battle
            source_civ: 1, intensity: -30,
            is_legacy: true, decay_factor_override: Some(legacy_factor),
        };
        write_single_memory(&mut pool, &intent, 100);
    }
    let shared = agents_share_memory(&pool, slot_a, slot_b);
    assert!(shared.is_some());
}
```

- [ ] **Step 8: Run full test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All tests pass (existing + new)

- [ ] **Step 9: Commit**

```
git add chronicler-agents/src/memory.rs chronicler-agents/src/agent.rs chronicler-agents/src/tick.rs chronicler-agents/tests/test_legacy_memory.rs
git commit -m "feat(m51): legacy memory extraction + death-path intent emission"
```

---

## Task 4: FFI Extension — 6-Tuple Return

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:786` (get_agent_memories)
- Test: `chronicler-agents/tests/test_legacy_memory.rs`

- [ ] **Step 1: Write failing test — FFI returns legacy flag**

```rust
#[test]
fn test_ffi_get_agent_memories_includes_legacy_flag() {
    // Setup: create agent, write a legacy memory via intent, then
    // call get_agent_memories and verify 6th element is true
    // (Use AgentSimulator if needed for FFI access)
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_ffi_get_agent_memories_includes_legacy`
Expected: FAIL — return type mismatch

- [ ] **Step 3: Extend get_agent_memories return type**

In `chronicler-agents/src/ffi.rs` at `get_agent_memories()` (line 786), change the return type from `Vec<(u8, u8, u16, i8, u8)>` to `Vec<(u8, u8, u16, i8, u8, bool)>`.

In the tuple construction inside the function, add the 6th element:

```rust
(
    pool.memory_event_types[slot][i],
    pool.memory_source_civs[slot][i],
    pool.memory_turns[slot][i],
    pool.memory_intensities[slot][i],
    pool.memory_decay_factors[slot][i],
    (pool.memory_is_legacy[slot] >> i) & 1 == 1,  // NEW: legacy flag
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_legacy_memory.rs
git commit -m "feat(m51): get_agent_memories FFI returns 6-tuple with legacy flag"
```

---

## Task 5: Python Memory Sync Update

**Files:**
- Modify: `src/chronicler/agent_bridge.py:508` (memory sync dict)
- Test: `tests/test_m51_legacy_integration.py` (new file)

- [ ] **Step 1: Write failing test — memory sync includes is_legacy**

In `tests/test_m51_legacy_integration.py`:

```python
def test_memory_sync_includes_legacy_flag():
    """Memory sync dict should include is_legacy from 6-tuple."""
    # Mock the 6-tuple return from get_agent_memories
    raw = [(0, 1, 100, -45, 7, True)]  # Famine, legacy
    # Simulate the dict construction
    mem = {
        "event_type": raw[0][0],
        "source_civ": raw[0][1],
        "turn": raw[0][2],
        "intensity": raw[0][3],
        "decay_factor": raw[0][4],
        "is_legacy": raw[0][5],
    }
    assert mem["is_legacy"] is True
    assert mem["event_type"] == 0  # Famine preserved
```

- [ ] **Step 2: Update memory sync in agent_bridge.py**

At the memory sync loop (~line 508), where the 5-tuple is unpacked into a dict, add `"is_legacy": m[5]` to the dict comprehension. The exact code depends on the current dict construction pattern — read the file and add the 6th field.

- [ ] **Step 3: Run test**

Run: `pytest tests/test_m51_legacy_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```
git add src/chronicler/agent_bridge.py tests/test_m51_legacy_integration.py
git commit -m "feat(m51): memory sync includes is_legacy from FFI 6-tuple"
```

---

## Task 6: Legacy Narrative Rendering

**Files:**
- Modify: `src/chronicler/narrative.py:68` (MEMORY_DESCRIPTIONS), `:132` (render_memory), `:270` (build_agent_context_for_moment)
- Test: `tests/test_m51_legacy_integration.py`

- [ ] **Step 1: Write failing test — legacy memory renders with ancestral prefix**

```python
from chronicler.narrative import render_memory

def test_render_legacy_memory():
    mem = {"event_type": 0, "source_civ": 1, "turn": 50,
           "intensity": -45, "decay_factor": 7, "is_legacy": True}
    result = render_memory(mem, civ_names=["Aram", "Kethani"])
    assert "ancestral" in result.lower() or "inherited" in result.lower()
    # Should still mention the event type (famine), not generic "legacy"
    assert "famine" in result.lower()

def test_render_normal_memory_no_ancestral():
    mem = {"event_type": 0, "source_civ": 1, "turn": 50,
           "intensity": -80, "decay_factor": 20, "is_legacy": False}
    result = render_memory(mem, civ_names=["Aram", "Kethani"])
    assert "ancestral" not in result.lower()
    assert "inherited" not in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_m51_legacy_integration.py::test_render_legacy_memory -v`
Expected: FAIL — render_memory doesn't check is_legacy

- [ ] **Step 3: Modify render_memory to handle legacy flag**

In `src/chronicler/narrative.py` at `render_memory()` (line 132), add a check near the top:

```python
is_legacy = mem.get("is_legacy", False)
```

After composing the base description from `MEMORY_DESCRIPTIONS`, prefix it if legacy:

```python
if is_legacy:
    description = f"an ancestral memory of {description}"
```

- [ ] **Step 4: Add legacy memory block to build_agent_context_for_moment**

In the character context assembly section (~lines 337-340), after rendering normal memories, add a separate block for legacy memories:

```python
legacy_memories = [m for m in (gp.memories or []) if m.get("is_legacy")]
if legacy_memories:
    legacy_lines = []
    for m in legacy_memories:
        rendered = render_memory(m, civ_names=civ_names)
        if rendered:
            legacy_lines.append(rendered)
    if legacy_lines:
        char_dict["ancestral_memories"] = legacy_lines
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_m51_legacy_integration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```
git add src/chronicler/narrative.py tests/test_m51_legacy_integration.py
git commit -m "feat(m51): legacy memory narrative rendering with ancestral prefix"
```

---

## Task 7: Leader Model + Regnal Registry (Track B Foundation)

**Files:**
- Modify: `src/chronicler/models.py:271-282` (Leader class), `:284+` (Civilization class)
- Test: `tests/test_m51_regnal.py` (new file)

- [ ] **Step 1: Write failing test — Leader has new fields**

In `tests/test_m51_regnal.py`:

```python
from chronicler.models import Leader, Civilization

def test_leader_has_regnal_fields():
    leader = Leader(name="King Kiran", trait="bold", reign_start=0)
    assert leader.agent_id is None
    assert leader.dynasty_id is None
    assert leader.throne_name is None
    assert leader.regnal_ordinal == 0

def test_leader_with_regnal_data():
    leader = Leader(name="King Kiran II", trait="bold", reign_start=100,
                    agent_id=42, dynasty_id=1, throne_name="Kiran", regnal_ordinal=2)
    assert leader.throne_name == "Kiran"
    assert leader.regnal_ordinal == 2

def test_civilization_has_regnal_name_counts():
    civ = Civilization(name="Aram")
    assert civ.regnal_name_counts == {}
    civ.regnal_name_counts["Kiran"] = 1
    assert civ.regnal_name_counts["Kiran"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: FAIL — fields don't exist

- [ ] **Step 3: Add fields to Leader and Civilization**

In `src/chronicler/models.py`, add to `Leader` (after line 282):

```python
    agent_id: int | None = None
    dynasty_id: int | None = None
    throne_name: str | None = None
    regnal_ordinal: int = 0
```

Add to `Civilization` (near other dict fields, after `legacy_counts` if it exists, or after other Field-default fields):

```python
    regnal_name_counts: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/chronicler/models.py tests/test_m51_regnal.py
git commit -m "feat(m51): Leader regnal fields + Civilization.regnal_name_counts"
```

---

## Task 8: _pick_regnal_name + to_roman + strip_title

**Files:**
- Modify: `src/chronicler/leaders.py` (add 3 new functions)
- Test: `tests/test_m51_regnal.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.leaders import to_roman, strip_title, _pick_regnal_name
from chronicler.models import Civilization, WorldState, Leader

def test_to_roman():
    assert to_roman(2) == "II"
    assert to_roman(3) == "III"
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(14) == "XIV"
    assert to_roman(20) == "XX"

def test_strip_title_single_word():
    assert strip_title("Emperor Kiran") == "Kiran"
    assert strip_title("King Vesh") == "Vesh"

def test_strip_title_multi_word():
    assert strip_title("High Priestess Mira") == "Mira"

def test_strip_title_no_title():
    assert strip_title("Kiran") == "Kiran"

def test_strip_title_fallback_with_numeral():
    # Old crude numbering — strip trailing I-sequences
    assert strip_title("Kiran III") == "Kiran"

def test_pick_regnal_name_first_ruler():
    """First ruler with a name gets ordinal 0 (no numeral)."""
    civ = Civilization(name="Aram")
    # Minimal world state for the function
    world = _make_world_with_civs([civ])
    import random
    rng = random.Random(42)
    title, throne_name, ordinal = _pick_regnal_name(civ, world, rng)
    assert title in TITLES  # from leaders.py
    assert isinstance(throne_name, str)
    assert ordinal == 0
    assert civ.regnal_name_counts[throne_name] == 1

def test_pick_regnal_name_second_ruler_gets_ordinal_2():
    """Second ruler with same throne name gets ordinal 2 ('II')."""
    civ = Civilization(name="Aram")
    civ.regnal_name_counts["Kiran"] = 1
    world = _make_world_with_civs([civ])
    import random
    rng = random.Random(42)
    # Force selection of "Kiran" — may need to mock pool or iterate
    # For the test, directly test the ordinal logic:
    count = civ.regnal_name_counts.get("Kiran", 0)
    ordinal = count + 1 if count > 0 else 0
    assert ordinal == 2
```

Note: `_make_world_with_civs` is a test helper — construct a minimal `WorldState` with the given civs. Check existing test files for patterns.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_m51_regnal.py::test_to_roman -v`
Expected: FAIL — function not found

- [ ] **Step 3: Implement to_roman**

In `src/chronicler/leaders.py`, add:

```python
def to_roman(n: int) -> str:
    """Convert integer 1-20 to Roman numeral string."""
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    result = ""
    for value, numeral in vals:
        while n >= value:
            result += numeral
            n -= value
    return result
```

- [ ] **Step 4: Implement strip_title**

```python
def strip_title(display_name: str) -> str:
    """Extract base name from a display name by stripping known title prefixes
    and trailing crude Roman numeral sequences."""
    import re
    for title in sorted(TITLES, key=len, reverse=True):  # longest first
        prefix = title + " "
        if display_name.startswith(prefix):
            display_name = display_name[len(prefix):]
            break
    # Strip trailing crude 'I' sequences (old numbering fallback)
    display_name = re.sub(r'\s+I{2,}$', '', display_name)
    # Strip trailing proper Roman numerals
    display_name = re.sub(r'\s+(?:XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II)$', '', display_name)
    return display_name.strip()
```

- [ ] **Step 5: Implement _pick_regnal_name**

```python
def _pick_regnal_name(
    civ: Civilization, world: WorldState, rng: random.Random
) -> tuple[str, str, int]:
    """Pick a regnal name for a ruler. Returns (title, throne_name, ordinal).

    Independent of _pick_name() and world.used_leader_names.
    Uses per-civ regnal_name_counts for ordinal tracking.
    """
    archetype = get_archetype_for_domains(civ.domains)
    pool = CULTURAL_NAME_POOLS[archetype]

    # Avoid cross-civ collision with current rulers only
    current_throne_names = set()
    for other in world.civilizations:
        if other.name != civ.name and other.leader and other.leader.throne_name:
            current_throne_names.add(other.leader.throne_name)

    available = [n for n in pool if n not in current_throne_names]
    if not available:
        available = [n for n in CULTURAL_NAME_POOLS["default"] if n not in current_throne_names]
    if not available:
        available = list(pool)  # allow collision as last resort

    title = rng.choice(TITLES)
    throne_name = rng.choice(available)

    count = civ.regnal_name_counts.get(throne_name, 0)
    ordinal = count + 1 if count > 0 else 0
    civ.regnal_name_counts[throne_name] = count + 1

    return title, throne_name, ordinal
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```
git add src/chronicler/leaders.py tests/test_m51_regnal.py
git commit -m "feat(m51): _pick_regnal_name, to_roman, strip_title helpers"
```

---

## Task 9: Wire Regnal Naming Into All 7 Ruler Creation Sites

**Files:**
- Modify: `src/chronicler/leaders.py:189` (generate_successor)
- Modify: `src/chronicler/world_gen.py:143` (founding leaders)
- Modify: `src/chronicler/politics.py:241` (secession), `:1001` (restored civ)
- Modify: `src/chronicler/succession.py:298` (exile restoration)
- Modify: `src/chronicler/scenario.py:535` (scenario overrides)
- Test: `tests/test_m51_regnal.py`

- [ ] **Step 1: Write failing test — generate_successor produces regnal metadata**

```python
def test_generate_successor_has_regnal_metadata():
    """generate_successor should produce a leader with throne_name and ordinal."""
    civ = _make_civ("Aram")
    world = _make_world_with_civs([civ])
    from chronicler.leaders import generate_successor
    leader = generate_successor(civ, world, seed=42)
    assert leader.throne_name is not None
    assert leader.regnal_ordinal >= 0
    assert leader.throne_name in civ.regnal_name_counts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_m51_regnal.py::test_generate_successor_has_regnal_metadata -v`
Expected: FAIL — throne_name is None

- [ ] **Step 3: Modify generate_successor to use _pick_regnal_name**

In `src/chronicler/leaders.py` at `generate_successor()` (line 189), replace the `_pick_name()` call at line 211:

```python
# OLD: name = _pick_name(civ, world, rng)
title, throne_name, ordinal = _pick_regnal_name(civ, world, rng)
if ordinal == 0:
    name = f"{title} {throne_name}"
else:
    name = f"{title} {throne_name} {to_roman(ordinal)}"
```

Then after constructing the `Leader` object at line 212, set the regnal fields:

```python
new_leader.throne_name = throne_name
new_leader.regnal_ordinal = ordinal
```

- [ ] **Step 4: Wire remaining 6 sites**

For each site, apply the same pattern: use `_pick_regnal_name()` to get `(title, throne_name, ordinal)`, compose the display name, set `throne_name` and `regnal_ordinal` on the Leader, and seed `civ.regnal_name_counts`.

**world_gen.py (~lines 131-150):** The current code constructs `leader_name` at line 131 BEFORE the `Civilization` is created at line 134. Since `_pick_regnal_name()` requires a `Civilization` object, restructure: (1) construct the `Civilization` first without `leader=`, (2) call `_pick_regnal_name(civ, world, rng)`, (3) set `civ.leader = Leader(name=..., throne_name=..., regnal_ordinal=...)`. Alternatively, compute the regnal name components (title, base name, ordinal) independently of the civ object — `_pick_regnal_name` only uses `civ.domains`, `civ.regnal_name_counts`, and `world.civilizations` for cross-civ collision avoidance. The simplest approach: construct the Civilization with a placeholder Leader, then immediately replace it via `_pick_regnal_name()`.

**politics.py (~line 241, secession):** The secession path constructs `Leader(name=leader_name, ...)` directly. Replace `leader_name` derivation with `_pick_regnal_name(breakaway_civ, world, rng)`. Set regnal fields. Seed `breakaway_civ.regnal_name_counts`.

**politics.py (~line 1001, restored civ):** Same pattern — replace name derivation with `_pick_regnal_name()`.

**succession.py (~line 298, exile restoration):** This uses `gp.name` for the returning exile. Unlike normal succession, exile restoration should keep the GP's personal name as throne name (they are returning to power, not adopting a new name). Use `strip_title(gp.name)` to extract the base name, compute ordinal from `civ.regnal_name_counts`, compose display name, set `throne_name` and `regnal_ordinal`. Do NOT call `_pick_regnal_name()` here — it would generate a random new name.

**scenario.py (~line 535):** Scenario overrides that mutate `used_leader_names` should also seed `civ.regnal_name_counts` for the overridden leader's throne_name.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 6: Run full Python test suite to check for regressions**

Run: `pytest tests/ -v --timeout=30`
Expected: No regressions in existing tests

- [ ] **Step 7: Commit**

```
git add src/chronicler/leaders.py src/chronicler/world_gen.py src/chronicler/politics.py src/chronicler/succession.py src/chronicler/scenario.py tests/test_m51_regnal.py
git commit -m "feat(m51): wire _pick_regnal_name into all 7 ruler creation sites"
```

---

## Task 10: GP Title Stripping + Ascension Regnal Names

**Files:**
- Modify: `src/chronicler/factions.py:596-609` (GP winner block)
- Test: `tests/test_m51_regnal.py`

- [ ] **Step 1: Write failing test — GP ascension produces regnal name**

```python
def test_gp_ascension_produces_regnal_name():
    """When a GP wins succession, their base name becomes the throne name."""
    from chronicler.leaders import strip_title
    gp_name = "High Priestess Mira"
    base = strip_title(gp_name)
    assert base == "Mira"
    # In resolve_crisis_with_factions, the GP winner block should:
    # 1. Strip title from gp_name
    # 2. Use base as throne_name
    # 3. Compute ordinal from civ.regnal_name_counts
    # 4. Compose display name with new title
```

- [ ] **Step 2: Modify the GP winner block in resolve_crisis_with_factions**

In `src/chronicler/factions.py` at lines 596-609, replace the `gp_name` copy with regnal processing:

```python
if winner and winner.get("source") == "great_person":
    gp_name = winner.get("gp_name")
    gp_trait = winner.get("gp_trait")

    if gp_name:
        from chronicler.leaders import strip_title, to_roman, TITLES
        import random as _random
        _rng = _random.Random(world.seed + world.turn + hash(civ.name) + 1)

        # Undo the phantom regnal counter increment from generate_successor,
        # which already called _pick_regnal_name and incremented for a name
        # that won't be used (GP name replaces it).
        if new_leader.throne_name and new_leader.throne_name in civ.regnal_name_counts:
            civ.regnal_name_counts[new_leader.throne_name] -= 1
            if civ.regnal_name_counts[new_leader.throne_name] <= 0:
                del civ.regnal_name_counts[new_leader.throne_name]

        throne_name = strip_title(gp_name)
        title = _rng.choice(TITLES)
        count = civ.regnal_name_counts.get(throne_name, 0)
        ordinal = count + 1 if count > 0 else 0
        civ.regnal_name_counts[throne_name] = count + 1

        if ordinal == 0:
            new_leader.name = f"{title} {throne_name}"
        else:
            new_leader.name = f"{title} {throne_name} {to_roman(ordinal)}"
        new_leader.throne_name = throne_name
        new_leader.regnal_ordinal = ordinal

    if gp_trait:
        new_leader.trait = gp_trait

    # Lineage bridge
    new_leader.agent_id = winner.get("agent_id")
    new_leader.dynasty_id = winner.get("dynasty_id")

    # Mark the GP dead (existing code)
    for gp in civ.great_persons:
        if gp.name == winner.get("gp_name") and gp.active:
            gp.active = False
            gp.alive = False
            gp.fate = "ascended_to_leadership"
            break
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```
git add src/chronicler/factions.py tests/test_m51_regnal.py
git commit -m "feat(m51): GP ascension uses strip_title + regnal naming"
```

---

## Task 11: Succession Scoring — compute_dynasty_legitimacy

**Files:**
- Modify: `src/chronicler/dynasties.py` (add function)
- Modify: `src/chronicler/factions.py:477-495` (wire into GP candidates)
- Test: `tests/test_m51_regnal.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.dynasties import compute_dynasty_legitimacy
from chronicler.models import Leader, Civilization

def test_legitimacy_direct_heir():
    """GP whose parent_id matches ruler's agent_id gets full bonus."""
    civ = Civilization(name="Aram")
    civ.leader = Leader(name="King Kiran", trait="bold", reign_start=0,
                        agent_id=100, dynasty_id=1)
    candidate = {"parent_id": 100, "dynasty_id": 1, "agent_id": 200}
    score = compute_dynasty_legitimacy(candidate, civ)
    assert score == 0.15  # LEGITIMACY_DIRECT_HEIR

def test_legitimacy_same_dynasty():
    """GP with matching dynasty_id but different parent gets lesser bonus."""
    civ = Civilization(name="Aram")
    civ.leader = Leader(name="King Kiran", trait="bold", reign_start=0,
                        agent_id=100, dynasty_id=1)
    candidate = {"parent_id": 50, "dynasty_id": 1, "agent_id": 200}
    score = compute_dynasty_legitimacy(candidate, civ)
    assert score == 0.08  # LEGITIMACY_SAME_DYNASTY

def test_legitimacy_no_match():
    """GP from unrelated dynasty gets 0."""
    civ = Civilization(name="Aram")
    civ.leader = Leader(name="King Kiran", trait="bold", reign_start=0,
                        agent_id=100, dynasty_id=1)
    candidate = {"parent_id": 50, "dynasty_id": 2, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0

def test_legitimacy_no_ruler_lineage():
    """When ruler has no agent_id (non-GP), all candidates get 0."""
    civ = Civilization(name="Aram")
    civ.leader = Leader(name="King Kiran", trait="bold", reign_start=0)
    candidate = {"parent_id": 100, "dynasty_id": 1, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0

def test_legitimacy_parent_none_sentinel():
    """parent_id=0 (PARENT_NONE) should not match any ruler."""
    civ = Civilization(name="Aram")
    civ.leader = Leader(name="King Kiran", trait="bold", reign_start=0,
                        agent_id=0)  # edge case: ruler agent_id is 0
    candidate = {"parent_id": 0, "dynasty_id": None, "agent_id": 200}
    assert compute_dynasty_legitimacy(candidate, civ) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_m51_regnal.py::test_legitimacy -v`
Expected: FAIL — function not found

- [ ] **Step 3: Implement compute_dynasty_legitimacy**

In `src/chronicler/dynasties.py`, add:

```python
LEGITIMACY_DIRECT_HEIR = 0.15   # [CALIBRATE M53]
LEGITIMACY_SAME_DYNASTY = 0.08  # [CALIBRATE M53]


def compute_dynasty_legitimacy(candidate: dict, civ) -> float:
    """Compute additive legitimacy bonus for a succession candidate.

    Scoped to the incumbent ruling line — only the current ruler's lineage
    matters, not any living dynasty.
    """
    ruler = civ.leader
    if ruler is None:
        return 0.0

    ruler_agent_id = getattr(ruler, "agent_id", None)
    ruler_dynasty_id = getattr(ruler, "dynasty_id", None)

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

    # Same dynasty
    if (
        ruler_dynasty_id is not None
        and cand_dynasty_id is not None
        and ruler_dynasty_id == cand_dynasty_id
    ):
        return LEGITIMACY_SAME_DYNASTY

    return 0.0
```

- [ ] **Step 4: Wire into generate_faction_candidates**

In `src/chronicler/factions.py` at `generate_faction_candidates()`, in the GP candidate loop (lines 488-495):

1. Add `agent_id`, `parent_id`, `dynasty_id` to the candidate dict:

```python
candidates.append({
    "faction": gp_faction.value,
    "type": GP_SUCCESSION_TYPE[gp.role],
    "source": "great_person",
    "gp_name": gp.name,
    "gp_trait": gp.trait,
    "weight": weight,
    "agent_id": gp.agent_id,
    "parent_id": gp.parent_id,
    "dynasty_id": gp.dynasty_id,
})
```

2. After appending the candidate, add legitimacy bonus:

```python
from chronicler.dynasties import compute_dynasty_legitimacy
legitimacy = compute_dynasty_legitimacy(candidates[-1], civ)
candidates[-1]["weight"] += legitimacy
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```
git add src/chronicler/dynasties.py src/chronicler/factions.py tests/test_m51_regnal.py
git commit -m "feat(m51): dynasty legitimacy scoring + GP candidate lineage fields"
```

---

## Task 12: Succession Event Legitimacy Phrasing

**Files:**
- Modify: `src/chronicler/factions.py:626-636` (event description)
- Test: `tests/test_m51_regnal.py`

- [ ] **Step 1: Write failing test — succession event includes legitimacy phrase**

```python
def test_succession_event_direct_heir_phrasing():
    """Direct heir succession should include 'by right of blood'."""
    # This requires an integration-level test of resolve_crisis_with_factions
    # with a GP winner whose parent_id matches the ruler's agent_id.
    # Verify the event description contains the legitimacy phrase.
```

- [ ] **Step 2: Modify event description in resolve_crisis_with_factions**

In `src/chronicler/factions.py` at the event creation block (~line 626), compute legitimacy context:

```python
# Legitimacy phrasing
legitimacy_phrase = ""
if winner and winner.get("source") == "great_person":
    from chronicler.dynasties import compute_dynasty_legitimacy
    leg = compute_dynasty_legitimacy(winner, civ)
    if leg >= 0.15:
        legitimacy_phrase = ", by right of blood,"
    elif leg >= 0.08:
        legitimacy_phrase = ", of the ruling house,"

events.append(Event(
    turn=world.turn,
    event_type="succession_crisis_resolved",
    actors=[civ.name],
    description=(
        f"The succession crisis in {civ.name} ends: "
        f"{new_leader.name}{legitimacy_phrase} rises to power after the fall of {old_leader.name}."
    ),
    importance=8,
))
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_m51_regnal.py -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: No regressions

- [ ] **Step 5: Commit**

```
git add src/chronicler/factions.py tests/test_m51_regnal.py
git commit -m "feat(m51): succession event legitimacy phrasing"
```

---

## Task 13: Multi-Generational Integration Test

**Files:**
- Test: `chronicler-agents/tests/test_legacy_memory.rs` (Rust multi-gen test)
- Test: `tests/test_m51_legacy_integration.py` (Python integration)

- [ ] **Step 1: Rust multi-generational decay test**

Test the full 4-generation chain using `extract_legacy_memories` + `write_single_memory` directly (not through the full tick — avoids needing the entire simulation harness):

```rust
#[test]
fn test_multi_generational_legacy_decay() {
    let mut pool = AgentPool::new(16);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Gen 1: parent with Persecution at -90
    let parent = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let orig = MemoryIntent {
        agent_slot: parent, event_type: 3, source_civ: 1, intensity: -90,
        is_legacy: false, decay_factor_override: None,
    };
    write_single_memory(&mut pool, &orig, 10);

    // Gen 2: child inherits
    let child = pool.spawn(0, 0, Occupation::Farmer, 5, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacies = extract_legacy_memories(&pool, parent);
    assert_eq!(legacies.len(), 1);
    assert_eq!(legacies[0].2, -45); // -90 / 2
    let intent2 = MemoryIntent {
        agent_slot: child, event_type: legacies[0].0, source_civ: legacies[0].1,
        intensity: legacies[0].2, is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent2, 50);
    assert_eq!(pool.memory_intensities[child][0], -45);

    // Gen 3: grandchild inherits from child
    let grandchild = pool.spawn(0, 0, Occupation::Farmer, 5, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacies2 = extract_legacy_memories(&pool, child);
    assert_eq!(legacies2.len(), 1);
    assert_eq!(legacies2[0].2, -22); // -45 / 2
    let intent3 = MemoryIntent {
        agent_slot: grandchild, event_type: legacies2[0].0, source_civ: legacies2[0].1,
        intensity: legacies2[0].2, is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent3, 100);
    assert_eq!(pool.memory_intensities[grandchild][0], -22);

    // Gen 4: great-grandchild inherits -11
    let great = pool.spawn(0, 0, Occupation::Farmer, 5, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let legacies3 = extract_legacy_memories(&pool, grandchild);
    assert_eq!(legacies3.len(), 1);
    assert_eq!(legacies3[0].2, -11);

    // Gen 5: -11 / 2 = -5, below LEGACY_MIN_INTENSITY (10) → filtered
    let intent4 = MemoryIntent {
        agent_slot: great, event_type: legacies3[0].0, source_civ: legacies3[0].1,
        intensity: legacies3[0].2, is_legacy: true, decay_factor_override: Some(legacy_factor),
    };
    write_single_memory(&mut pool, &intent4, 150);
    let legacies4 = extract_legacy_memories(&pool, great);
    assert!(legacies4.is_empty()); // -11 / 2 = -5, below threshold
}
```

- [ ] **Step 2: Rust DeathOfKin + legacy same-tick test**

Test that DeathOfKin and legacy intents coexist in the same `memory_intents` Vec without conflict:

```rust
#[test]
fn test_death_of_kin_and_legacy_same_consolidated_write() {
    let mut pool = AgentPool::new(16);
    let legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE);

    // Parent with a strong Battle memory
    let parent = pool.spawn(0, 0, Occupation::Farmer, 30, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let battle = MemoryIntent {
        agent_slot: parent, event_type: 1, source_civ: 1, intensity: -60,
        is_legacy: false, decay_factor_override: None,
    };
    write_single_memory(&mut pool, &battle, 10);

    // Child starts empty
    let child = pool.spawn(0, 0, Occupation::Farmer, 5, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Simulate same-tick: collect both DeathOfKin and legacy intents
    let mut intents = Vec::new();

    // DeathOfKin intent
    intents.push(MemoryIntent {
        agent_slot: child, event_type: 9, // DeathOfKin
        source_civ: pool.civ_affinities[child], intensity: -80,
        is_legacy: false, decay_factor_override: None,
    });

    // Legacy intent
    let legacies = extract_legacy_memories(&pool, parent);
    for (et, sc, halved) in &legacies {
        intents.push(MemoryIntent {
            agent_slot: child, event_type: *et, source_civ: *sc,
            intensity: *halved, is_legacy: true, decay_factor_override: Some(legacy_factor),
        });
    }

    // Consolidated write — all intents land
    write_all_memories(&mut pool, &intents, 50);

    // Child should have 2 memories: DeathOfKin + legacy Battle
    assert_eq!(pool.memory_count[child], 2);
    // One should be legacy (bitmask non-zero)
    assert_ne!(pool.memory_is_legacy[child], 0);
}
```

- [ ] **Step 3: Python determinism test**

Pattern from `tests/test_main.py` — run two identical simulations and compare memory state. Use a short run (5 turns) with agents enabled:

```python
def test_legacy_determinism():
    """Same seed produces identical results across runs."""
    from chronicler.main import execute_run
    # Run twice with same seed, compare bundle memory data
    # (specific implementation depends on execute_run interface —
    #  follow patterns in tests/test_main.py or tests/test_bundle.py)
```

- [ ] **Step 3b: Rust 2-turn transient signal test (per CLAUDE.md rule)**

Verify legacy intents fire only on the death tick, not on subsequent ticks:

```rust
#[test]
fn test_legacy_does_not_leak_across_ticks() {
    // This test verifies the CLAUDE.md transient signal rule.
    // Legacy extraction happens inside the death loop — it's not a
    // persistent flag that re-fires. The test pattern: run two
    // consecutive ticks, verify legacy intents only appear on the
    // tick where death occurs. (Implementation depends on tick
    // test infrastructure — pattern from existing 2-turn tests.)
}
```

- [ ] **Step 4: Run all tests**

Run: `cargo nextest run -p chronicler-agents` and `pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 5: Commit**

```
git add chronicler-agents/tests/test_legacy_memory.rs tests/test_m51_legacy_integration.py
git commit -m "test(m51): multi-generational decay + same-tick + determinism tests"
```

---

## Task 14: Final Cleanup + Full Regression

- [ ] **Step 1: Add comment noting MemoryEventType::Legacy (14) is vestigial**

In `chronicler-agents/src/memory.rs` at the `default_decay_factor` match arm for event_type 14:

```rust
14 => factor_from_half_life(agent::LEGACY_HALF_LIFE), // Vestigial: M51 legacy memories use original event_type + decay_factor_override
```

- [ ] **Step 2: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS

- [ ] **Step 3: Run full Python test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: All PASS (may have 2 pre-existing failures from M47, per progress doc)

- [ ] **Step 4: Final commit**

```
git add -A
git commit -m "chore(m51): cleanup — vestigial Legacy match arm comment"
```
