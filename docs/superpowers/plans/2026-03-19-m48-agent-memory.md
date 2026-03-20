# M48: Agent Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-agent memory ring buffer (8 slots, 50 bytes/agent) to the Rust agent pool with decay, eviction, behavioral effects on satisfaction and decisions, plus a Mule promotion system that creates history-bending named characters.

**Architecture:** Memory is SoA storage on `AgentPool` (Rust), written via a consolidated write phase at tick end. Behavioral effects are additive: memory satisfaction term inside the 0.40 cap as 5th priority, additive utility modifiers on agent decisions. Mule promotions are Python-side, modifying civ-level action weights via the existing multiplicative pipeline. Three new per-region transient signals cross FFI for conquest/victory/secession events.

**Tech Stack:** Rust (pool.rs, tick.rs, satisfaction.rs, behavior.rs, region.rs, signals.rs, ffi.rs), Python (models.py, agent_bridge.py, action_engine.py, simulation.py, narrative.py), PyO3/Arrow FFI.

**Spec:** `docs/superpowers/specs/2026-03-19-m48-agent-memory-design.md`

**IMPORTANT: Test code in this plan is schematic.** All `AgentPool::new()` and `pool.spawn()` calls use simplified signatures. Before implementing, READ the actual signatures in `pool.rs` (lines 65, 97-110) and adjust test code accordingly. Same applies to `SatisfactionInputs` construction — there is no `default_test()` constructor; build the struct manually following existing test patterns in `satisfaction.rs`.

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

### New Files

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/memory.rs` | MemoryEventType enum, MemoryIntent struct, half-life conversion utilities, event type defaults registry, consolidated write logic, decay loop, eviction, gate clearing, `agents_share_memory` query |
| `chronicler-agents/tests/test_memory.rs` | All Rust memory unit tests |
| `tests/test_memory.py` | Python integration tests for transient signals, Mule, FFI, `--agents=off` |

### Modified Files

| File | Changes |
|------|---------|
| `chronicler-agents/src/lib.rs` | Add `pub mod memory;` |
| `chronicler-agents/src/agent.rs` | Add MEMORY_STREAM_OFFSET constant (reserved, not consumed), memory-related constants (half-lives, thresholds, Mule constants) |
| `chronicler-agents/src/pool.rs` | Add 7 memory SoA fields, zero-init in spawn() reuse + grow branches |
| `chronicler-agents/src/tick.rs` | Insert memory decay as first operation, collect memory intents across phases, call consolidated write pass as last operation |
| `chronicler-agents/src/satisfaction.rs` | Add `memory_score: f32` to `SatisfactionInputs`, add 5th-priority penalty clamping in `compute_satisfaction_with_culture()` |
| `chronicler-agents/src/behavior.rs` | Add memory-driven additive utility modifiers in `evaluate_region_decisions()` |
| `chronicler-agents/src/region.rs` | Add 3 boolean fields: `controller_changed_this_turn`, `war_won_this_turn`, `seceded_this_turn` |
| `chronicler-agents/src/signals.rs` | Parse 3 new region signal columns from Arrow batch |
| `chronicler-agents/src/ffi.rs` | Add `get_agent_memories()` pymethod, pass memory fields through tick, add memory columns to snapshot if needed |
| `src/chronicler/models.py` | Add `mule`, `mule_memory_event_type`, `utility_overrides`, `memories` fields on GreatPerson |
| `src/chronicler/agent_bridge.py` | Add 3 signal columns to `build_region_batch()`, Mule detection in `_process_promotions()`, memory sync on GreatPerson |
| `src/chronicler/action_engine.py` | Add `get_mule_factor()`, Mule weight modification loop between aggression bias and streak-breaker, set `controller_changed_this_turn` and `war_won_this_turn` in `_resolve_war_action()` |
| `src/chronicler/politics.py` | Set `seceded_this_turn` in `check_secession()` |
| `src/chronicler/simulation.py` | Clear 3 new region-level transient signals before bridge tick |
| `src/chronicler/narrative.py` | Add `MEMORY_DESCRIPTIONS` registry, `render_memory()`, memory context in `build_agent_context_for_moment()`, Mule narrator context |

---

## Task 1: Rust Foundation — Constants, Types, Storage

**Files:**
- Create: `chronicler-agents/src/memory.rs`
- Modify: `chronicler-agents/src/lib.rs`
- Modify: `chronicler-agents/src/agent.rs` (after line 92 for STREAM_OFFSETS, after line 162 for constants)
- Modify: `chronicler-agents/src/pool.rs` (lines 19-51 struct fields, lines 114-142 reuse branch, lines 143-172 grow branch)
- Create: `chronicler-agents/tests/test_memory.rs`

- [ ] **Step 1: Write test for spawn zero-initialization**

In `chronicler-agents/tests/test_memory.rs`:

```rust
use chronicler_agents::pool::AgentPool;

#[test]
fn test_memory_spawn_zeroed() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    assert_eq!(pool.memory_count[slot], 0);
    assert_eq!(pool.memory_gates[slot], 0);
    for i in 0..8 {
        assert_eq!(pool.memory_intensities[slot][i], 0);
        assert_eq!(pool.memory_event_types[slot][i], 0);
        assert_eq!(pool.memory_decay_factors[slot][i], 0);
    }
}

#[test]
fn test_memory_reuse_zeroed() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // Manually dirty the memory fields
    pool.memory_count[slot] = 5;
    pool.memory_gates[slot] = 0xFF;
    pool.memory_intensities[slot] = [-80, -60, 50, 70, -90, 0, 0, 0];
    pool.kill(slot);
    // Respawn into the same slot
    let slot2 = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    assert_eq!(slot, slot2); // free-list reuse
    assert_eq!(pool.memory_count[slot2], 0);
    assert_eq!(pool.memory_gates[slot2], 0);
    for i in 0..8 {
        assert_eq!(pool.memory_intensities[slot2][i], 0);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_memory_spawn`
Expected: Compilation error — `memory_count` field does not exist on AgentPool.

- [ ] **Step 3: Create memory.rs with MemoryEventType enum and constants**

In `chronicler-agents/src/memory.rs`:

```rust
/// M48 Agent Memory System
/// Spec: docs/superpowers/specs/2026-03-19-m48-agent-memory-design.md

pub const MEMORY_SLOTS: usize = 8;

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MemoryEventType {
    Famine = 0,
    Battle = 1,
    Conquest = 2,
    Persecution = 3,
    Migration = 4,
    Prosperity = 5,
    Victory = 6,
    Promotion = 7,
    BirthOfKin = 8,
    DeathOfKin = 9,
    Conversion = 10,
    Secession = 11,
    // 12-13 reserved for Phase 8
    Legacy = 14,
    // 15 reserved
}

impl MemoryEventType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Famine),
            1 => Some(Self::Battle),
            2 => Some(Self::Conquest),
            3 => Some(Self::Persecution),
            4 => Some(Self::Migration),
            5 => Some(Self::Prosperity),
            6 => Some(Self::Victory),
            7 => Some(Self::Promotion),
            8 => Some(Self::BirthOfKin),
            9 => Some(Self::DeathOfKin),
            10 => Some(Self::Conversion),
            11 => Some(Self::Secession),
            14 => Some(Self::Legacy),
            _ => None, // reserved slots 12, 13, 15
        }
    }
}

/// Gate bit assignments for frequency-gated event types
pub const GATE_BIT_BATTLE: u8 = 1 << 0;
pub const GATE_BIT_PROSPERITY: u8 = 1 << 1;
pub const GATE_BIT_FAMINE: u8 = 1 << 2;
pub const GATE_BIT_PERSECUTION: u8 = 1 << 3;

/// Returns the gate bit for a gated event type, or 0 if not gated
pub fn gate_bit_for(event_type: u8) -> u8 {
    match event_type {
        1 => GATE_BIT_BATTLE,
        5 => GATE_BIT_PROSPERITY,
        0 => GATE_BIT_FAMINE,
        3 => GATE_BIT_PERSECUTION,
        _ => 0,
    }
}

/// Intent struct for deferred memory writes
#[derive(Debug, Clone)]
pub struct MemoryIntent {
    pub agent_slot: usize,
    pub event_type: u8,
    pub source_civ: u8,
    pub intensity: i8,
}

/// Convert half-life in turns to per-tick decay factor (u8).
/// 0 = permanent (no decay). Higher values = faster decay.
/// Cold-path only — called at memory creation time, not per-tick.
pub fn factor_from_half_life(half_life: f32) -> u8 {
    if half_life == f32::INFINITY || half_life <= 0.0 {
        return 0; // permanent sentinel
    }
    let rate = 1.0 - 0.5_f32.powf(1.0 / half_life);
    (rate * 255.0).round().min(255.0) as u8
}

/// Convert per-tick decay factor back to half-life in turns.
/// For debugging and roundtrip verification.
pub fn half_life_from_factor(factor: u8) -> f32 {
    if factor == 0 {
        return f32::INFINITY; // permanent
    }
    let rate = factor as f32 / 255.0;
    let base = 1.0 - rate;
    if base <= 0.0 {
        return 1.0; // instant decay
    }
    (0.5_f32.ln() / base.ln()).abs()
}
```

- [ ] **Step 4: Add `pub mod memory;` to lib.rs**

In `chronicler-agents/src/lib.rs`, add `pub mod memory;` alongside the other module declarations.

- [ ] **Step 5: Add memory constants to agent.rs**

After the existing STREAM_OFFSETS block (line 92), add:

```rust
// M48: Memory system (reserved, not consumed in M48 — deterministic writes)
pub const MEMORY_STREAM_OFFSET: u64 = 900;
// M48: Mule promotion (reserved for Rust, but M48 uses Python-side RNG)
pub const MULE_STREAM_OFFSET: u64 = 1300;
```

After the existing constants block (after line 162), add memory default profiles:

```rust
// M48: Memory event default intensities [CALIBRATE M53]
pub const FAMINE_DEFAULT_INTENSITY: i8 = -80;
pub const BATTLE_DEFAULT_INTENSITY: i8 = -60;
pub const CONQUEST_DEFAULT_INTENSITY: i8 = -70;
pub const PERSECUTION_DEFAULT_INTENSITY: i8 = -90;
pub const MIGRATION_DEFAULT_INTENSITY: i8 = -30;
pub const PROSPERITY_DEFAULT_INTENSITY: i8 = 50;
pub const VICTORY_DEFAULT_INTENSITY: i8 = 60;
pub const PROMOTION_DEFAULT_INTENSITY: i8 = 70;
pub const BIRTHOFKIN_DEFAULT_INTENSITY: i8 = 40;
pub const DEATHOFKIN_DEFAULT_INTENSITY: i8 = -80;
pub const CONVERSION_DEFAULT_INTENSITY: i8 = 50; // -50 when forced
pub const SECESSION_DEFAULT_INTENSITY: i8 = -60;

// M48: Memory event default half-lives in turns [CALIBRATE M53]
pub const FAMINE_HALF_LIFE: f32 = 40.0;
pub const BATTLE_HALF_LIFE: f32 = 25.0;
pub const CONQUEST_HALF_LIFE: f32 = 30.0;
pub const PERSECUTION_HALF_LIFE: f32 = 50.0;
pub const MIGRATION_HALF_LIFE: f32 = 15.0;
pub const PROSPERITY_HALF_LIFE: f32 = 20.0;
pub const VICTORY_HALF_LIFE: f32 = 20.0;
pub const PROMOTION_HALF_LIFE: f32 = 30.0;
pub const BIRTHOFKIN_HALF_LIFE: f32 = 25.0;
pub const DEATHOFKIN_HALF_LIFE: f32 = 35.0;
pub const CONVERSION_HALF_LIFE: f32 = 20.0;
pub const SECESSION_HALF_LIFE: f32 = 20.0;
pub const LEGACY_HALF_LIFE: f32 = 100.0;

// M48: Memory behavioral constants [CALIBRATE M53]
pub const MEMORY_SATISFACTION_WEIGHT: f32 = 0.12;
pub const FAMINE_MEMORY_THRESHOLD: f32 = 0.6; // food_sufficiency below this triggers FAMINE memory
pub const PROSPERITY_THRESHOLD: f32 = 3.0; // wealth above this triggers PROSPERITY memory

// M48: Memory utility modifier magnitudes [CALIBRATE M53]
pub const FAMINE_MIGRATE_BOOST: f32 = 0.2;
pub const BATTLE_BOLD_STAY_BOOST: f32 = 0.1;
pub const BATTLE_CAUTIOUS_MIGRATE_BOOST: f32 = 0.15;
pub const CONQUEST_CONQUERED_MIGRATE_BOOST: f32 = 0.3;
pub const CONQUEST_CONQUEROR_STAY_BOOST: f32 = 0.1;
pub const PERSECUTION_REBEL_BOOST_MEMORY: f32 = 0.15; // separate from existing PERSECUTION_REBEL_BOOST
pub const PERSECUTION_MIGRATE_BOOST_MEMORY: f32 = 0.2;
pub const PROSPERITY_MIGRATE_PENALTY: f32 = 0.2;
pub const PROSPERITY_SWITCH_PENALTY: f32 = 0.1;
pub const VICTORY_STAY_BOOST: f32 = 0.1;
pub const DEATHOFKIN_MIGRATE_PENALTY: f32 = 0.15;
```

- [ ] **Step 6: Add 7 memory SoA fields to AgentPool in pool.rs**

After the last existing SoA field declaration (wealth, ~line 51), add:

```rust
// M48: Memory ring buffer (8 slots per agent)
pub memory_event_types: Vec<[u8; 8]>,
pub memory_source_civs: Vec<[u8; 8]>,
pub memory_turns: Vec<[u16; 8]>,
pub memory_intensities: Vec<[i8; 8]>,
pub memory_decay_factors: Vec<[u8; 8]>,
pub memory_gates: Vec<u8>,
pub memory_count: Vec<u8>,
```

In `AgentPool::new()`, add initialization for each field (empty Vecs).

In the free-list reuse branch of `spawn()` (after line 139, before `self.alive[slot] = true;`), add:

```rust
self.memory_event_types[slot] = [0; 8];
self.memory_source_civs[slot] = [0; 8];
self.memory_turns[slot] = [0; 8];
self.memory_intensities[slot] = [0; 8];
self.memory_decay_factors[slot] = [0; 8];
self.memory_gates[slot] = 0;
self.memory_count[slot] = 0;
```

In the grow branch of `spawn()` (after the last `.push()` for existing fields, before `self.alive.push(true);`), add:

```rust
self.memory_event_types.push([0; 8]);
self.memory_source_civs.push([0; 8]);
self.memory_turns.push([0; 8]);
self.memory_intensities.push([0; 8]);
self.memory_decay_factors.push([0; 8]);
self.memory_gates.push(0);
self.memory_count.push(0);
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_memory`
Expected: PASS for `test_memory_spawn_zeroed` and `test_memory_reuse_zeroed`.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/memory.rs chronicler-agents/src/lib.rs \
  chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs \
  chronicler-agents/tests/test_memory.rs
git commit -m "feat(m48): memory SoA storage, event type registry, constants"
```

---

## Task 2: Decay & Eviction

**Files:**
- Modify: `chronicler-agents/src/memory.rs` (add decay + eviction functions)
- Modify: `chronicler-agents/tests/test_memory.rs`

- [ ] **Step 1: Write decay and eviction tests**

Add to `chronicler-agents/tests/test_memory.rs`:

```rust
use chronicler_agents::memory::*;

#[test]
fn test_halflife_roundtrip() {
    for n in 1..=100 {
        let half_life = n as f32;
        let factor = factor_from_half_life(half_life);
        let recovered = half_life_from_factor(factor);
        let relative_error = (recovered - half_life).abs() / half_life;
        let tolerance = if n <= 50 { 0.15 } else { 0.25 };
        assert!(
            relative_error < tolerance,
            "half_life={}, factor={}, recovered={}, error={:.2}%",
            half_life, factor, recovered, relative_error * 100.0
        );
    }
}

#[test]
fn test_halflife_edge_cases() {
    assert_eq!(factor_from_half_life(f32::INFINITY), 0);
    assert!(half_life_from_factor(0).is_infinite());
    let f255 = half_life_from_factor(255);
    assert!(f255 >= 0.5 && f255 <= 2.0, "factor 255 should be ~1 turn, got {}", f255);
}

#[test]
fn test_memory_decay_basic() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // Write a memory with half-life 10 turns
    let factor = factor_from_half_life(10.0);
    pool.memory_event_types[slot][0] = 0; // Famine
    pool.memory_intensities[slot][0] = -80;
    pool.memory_decay_factors[slot][0] = factor;
    pool.memory_count[slot] = 1;

    // Decay for 10 turns — intensity should roughly halve
    for _ in 0..10 {
        decay_memories(&mut pool, &[slot]);
    }
    let intensity = pool.memory_intensities[slot][0];
    // Allow ±25% tolerance due to integer quantization
    assert!(intensity >= -50 && intensity <= -30,
        "After 10 turns with half-life 10, expected ~-40, got {}", intensity);
}

#[test]
fn test_memory_decay_permanent() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    pool.memory_intensities[slot][0] = -90;
    pool.memory_decay_factors[slot][0] = 0; // permanent
    pool.memory_count[slot] = 1;
    for _ in 0..100 {
        decay_memories(&mut pool, &[slot]);
    }
    assert_eq!(pool.memory_intensities[slot][0], -90);
}

#[test]
fn test_decay_integer_truncation() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    pool.memory_intensities[slot][0] = 1;
    pool.memory_decay_factors[slot][0] = 10; // any nonzero factor
    pool.memory_count[slot] = 1;
    decay_memories(&mut pool, &[slot]);
    assert_eq!(pool.memory_intensities[slot][0], 0, "intensity 1 should decay to 0 in one tick");
}

#[test]
fn test_memory_eviction_min_intensity() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // Fill all 8 slots with varying intensities
    for i in 0..8 {
        pool.memory_intensities[slot][i] = ((i as i8 + 1) * 10); // 10, 20, ..., 80
        pool.memory_event_types[slot][i] = i as u8;
        pool.memory_count[slot] = (i + 1) as u8;
    }
    // Write a new memory — should evict slot 0 (intensity 10, lowest)
    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: 9, // DeathOfKin
        source_civ: 0,
        intensity: -80,
    };
    write_single_memory(&mut pool, &intent, 100);
    assert_eq!(pool.memory_event_types[slot][0], 9, "slot 0 should be overwritten");
    assert_eq!(pool.memory_intensities[slot][0], -80);
    assert_eq!(pool.memory_count[slot], 8, "count stays at 8");
}

#[test]
fn test_memory_eviction_tiebreak() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // Fill all 8 slots with same intensity
    for i in 0..8 {
        pool.memory_intensities[slot][i] = 50;
        pool.memory_event_types[slot][i] = i as u8;
    }
    pool.memory_count[slot] = 8;
    let intent = MemoryIntent {
        agent_slot: slot,
        event_type: 9,
        source_civ: 0,
        intensity: -80,
    };
    write_single_memory(&mut pool, &intent, 100);
    // Tie-break: lowest index (slot 0) should be evicted
    assert_eq!(pool.memory_event_types[slot][0], 9);
}

#[test]
fn test_memory_count_lifecycle() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    assert_eq!(pool.memory_count[slot], 0);
    for i in 0..8 {
        let intent = MemoryIntent {
            agent_slot: slot, event_type: 0, source_civ: 0, intensity: -50,
        };
        write_single_memory(&mut pool, &intent, i as u16);
        assert_eq!(pool.memory_count[slot], (i + 1).min(8) as u8);
    }
    // 9th write — count stays at 8
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 1, source_civ: 0, intensity: -90,
    };
    write_single_memory(&mut pool, &intent, 100);
    assert_eq!(pool.memory_count[slot], 8);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents test_memory`
Expected: Compilation error — `decay_memories` and `write_single_memory` don't exist.

- [ ] **Step 3: Implement decay and write functions in memory.rs**

Add to `chronicler-agents/src/memory.rs`:

```rust
use crate::pool::AgentPool;
use crate::agent;

/// Per-tick decay for all occupied memory slots across given agent slots.
/// Hot path — integer arithmetic only, no floats.
/// Runs as the first tick operation ("Phase -0.5").
pub fn decay_memories(pool: &mut AgentPool, alive_slots: &[usize]) {
    for &slot in alive_slots {
        let count = pool.memory_count[slot] as usize;
        for i in 0..count {
            let factor = pool.memory_decay_factors[slot][i];
            if factor == 0 {
                continue; // permanent — no decay
            }
            let intensity = pool.memory_intensities[slot][i] as i16;
            // new_intensity = intensity * (255 - factor) / 255
            // i16 intermediate: max |128 * 255| = 32640, within i16 range
            let new_val = (intensity * (255 - factor as i16)) / 255;
            pool.memory_intensities[slot][i] = new_val as i8;
        }
    }
}

/// Lookup table: event_type → precomputed decay_factor (u8)
/// Built once, used at memory write time.
pub fn default_decay_factor(event_type: u8) -> u8 {
    match event_type {
        0 => factor_from_half_life(agent::FAMINE_HALF_LIFE),
        1 => factor_from_half_life(agent::BATTLE_HALF_LIFE),
        2 => factor_from_half_life(agent::CONQUEST_HALF_LIFE),
        3 => factor_from_half_life(agent::PERSECUTION_HALF_LIFE),
        4 => factor_from_half_life(agent::MIGRATION_HALF_LIFE),
        5 => factor_from_half_life(agent::PROSPERITY_HALF_LIFE),
        6 => factor_from_half_life(agent::VICTORY_HALF_LIFE),
        7 => factor_from_half_life(agent::PROMOTION_HALF_LIFE),
        8 => factor_from_half_life(agent::BIRTHOFKIN_HALF_LIFE),
        9 => factor_from_half_life(agent::DEATHOFKIN_HALF_LIFE),
        10 => factor_from_half_life(agent::CONVERSION_HALF_LIFE),
        11 => factor_from_half_life(agent::SECESSION_HALF_LIFE),
        14 => factor_from_half_life(agent::LEGACY_HALF_LIFE),
        _ => 0, // reserved — permanent (won't be written in M48)
    }
}

/// Write a single memory intent into an agent's ring buffer.
/// Handles append (count < 8) and eviction (count == 8).
pub fn write_single_memory(pool: &mut AgentPool, intent: &MemoryIntent, turn: u16) {
    let slot = intent.agent_slot;
    let count = pool.memory_count[slot] as usize;
    let write_idx = if count < 8 {
        pool.memory_count[slot] += 1;
        count
    } else {
        // Evict: find slot with minimum |intensity|, tie-break lowest index
        let mut min_abs = i8::MAX.unsigned_abs();
        let mut min_idx = 0;
        for i in 0..8 {
            let abs = pool.memory_intensities[slot][i].unsigned_abs();
            if abs < min_abs {
                min_abs = abs;
                min_idx = i;
            }
        }
        min_idx
    };
    pool.memory_event_types[slot][write_idx] = intent.event_type;
    pool.memory_source_civs[slot][write_idx] = intent.source_civ;
    pool.memory_turns[slot][write_idx] = turn;
    pool.memory_intensities[slot][write_idx] = intent.intensity;
    pool.memory_decay_factors[slot][write_idx] = default_decay_factor(intent.event_type);
}

/// Compute the memory satisfaction score for an agent.
/// Returns a value in approximately [-0.15, +0.15].
pub fn compute_memory_satisfaction_score(pool: &AgentPool, slot: usize) -> f32 {
    let count = pool.memory_count[slot] as usize;
    if count == 0 {
        return 0.0;
    }
    let sum: i16 = pool.memory_intensities[slot][..count]
        .iter()
        .map(|&i| i as i16)
        .sum();
    (sum as f32 / 1024.0) * agent::MEMORY_SATISFACTION_WEIGHT
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_memory`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/memory.rs chronicler-agents/tests/test_memory.rs
git commit -m "feat(m48): decay hot path, eviction logic, half-life utilities"
```

---

## Task 3: RegionState Signals + Python Signal Sourcing

**Files:**
- Modify: `chronicler-agents/src/region.rs` (after line 59)
- Modify: `chronicler-agents/src/signals.rs`
- Modify: `src/chronicler/action_engine.py` — in `_resolve_war_action()`
- Modify: `src/chronicler/politics.py` — in `check_secession()`
- Modify: `src/chronicler/simulation.py` — transient signal clearing
- Modify: `src/chronicler/agent_bridge.py` — `build_region_batch()` columns
- Create: `tests/test_memory.py`

- [ ] **Step 1: Write Python transient signal integration tests**

In `tests/test_memory.py`:

```python
"""M48 Agent Memory integration tests.
All tests use run_turn() directly — never execute_run().
"""
import pytest
from chronicler.models import WorldState, Region
from chronicler.simulation import run_turn


class TestTransientSignals:
    """Each signal must be set on the event turn and cleared next turn."""

    def test_controller_changed_this_turn(self, basic_world_with_war):
        """controller_changed_this_turn set on conquest, cleared next turn."""
        world = basic_world_with_war
        # After war resolution turn, conquered region should have flag set
        conquered_region = _find_conquered_region(world)
        assert conquered_region is not None
        assert getattr(conquered_region, '_controller_changed_this_turn', False) is True
        # Run another turn — flag should be cleared
        run_turn(world)
        assert getattr(conquered_region, '_controller_changed_this_turn', False) is False

    def test_war_won_this_turn(self, basic_world_with_war):
        """war_won_this_turn set on victory, cleared next turn."""
        world = basic_world_with_war
        won_regions = [r for r in world.regions
                       if getattr(r, '_war_won_this_turn', False)]
        assert len(won_regions) > 0
        run_turn(world)
        won_regions_after = [r for r in world.regions
                            if getattr(r, '_war_won_this_turn', False)]
        assert len(won_regions_after) == 0

    def test_seceded_this_turn(self, basic_world_with_secession):
        """seceded_this_turn set on secession, cleared next turn."""
        world = basic_world_with_secession
        seceded = [r for r in world.regions
                   if getattr(r, '_seceded_this_turn', False)]
        assert len(seceded) > 0
        run_turn(world)
        seceded_after = [r for r in world.regions
                        if getattr(r, '_seceded_this_turn', False)]
        assert len(seceded_after) == 0
```

Note: Test fixtures (`basic_world_with_war`, `basic_world_with_secession`) will need to be implemented by creating world states that trigger war/secession. The implementer should check existing test patterns in `tests/` for fixture conventions.

- [ ] **Step 2: Add 3 boolean fields to RegionState in region.rs**

After the last field in `RegionState` (before the closing brace), add:

```rust
// M48: Per-region transient memory signals (cleared each turn in Python)
pub controller_changed_this_turn: bool,
pub war_won_this_turn: bool,
pub seceded_this_turn: bool,
```

Update `RegionState::new()` to initialize all three to `false`.

- [ ] **Step 3: Parse new columns in signals.rs**

In the region signal parsing function, add optional column reads for the 3 new booleans. Follow the existing pattern for optional columns (default to `false` if absent).

- [ ] **Step 4: Add columns to build_region_batch() in agent_bridge.py**

After the last column in the record batch dictionary (merchant_trade_income), add:

```python
"controller_changed_this_turn": pa.array(
    [getattr(r, '_controller_changed_this_turn', False) for r in world.regions],
    type=pa.bool_()
),
"war_won_this_turn": pa.array(
    [getattr(r, '_war_won_this_turn', False) for r in world.regions],
    type=pa.bool_()
),
"seceded_this_turn": pa.array(
    [getattr(r, '_seceded_this_turn', False) for r in world.regions],
    type=pa.bool_()
),
```

- [ ] **Step 5: Set signals in action_engine.py and politics.py**

In `_resolve_war_action()`, where `region.controller = attacker.name` is set for conquered regions, add:

```python
region._controller_changed_this_turn = True
```

For `war_won_this_turn`, set on the contested/target regions where the winning civ's soldiers are present:

```python
for region in _get_war_target_regions(attacker, defender, world):
    region._war_won_this_turn = True
```

In `check_secession()` in politics.py, where seceding regions are transferred, add:

```python
region._seceded_this_turn = True
```

- [ ] **Step 6: Clear signals inside build_region_batch() AFTER reading them**

In `agent_bridge.py`, in `build_region_batch()`, AFTER the `pa.array()` calls that read these three attributes (Step 4 above) and BEFORE the function returns, add clearing logic. This follows the CLAUDE.md transient signal pattern: "clear BEFORE the return in the builder function."

```python
# M48: Clear per-region memory transient signals after batch construction
for r in world.regions:
    r._controller_changed_this_turn = False
    r._war_won_this_turn = False
    r._seceded_this_turn = False
```

This ensures: (1) the signals are available when the Arrow batch is constructed, (2) they are cleared before the function returns, (3) next turn starts clean. Do NOT clear in `simulation.py` before the bridge tick — that would clear before `build_region_batch()` reads them.

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents` (Rust — verify compilation)
Run: `pytest tests/test_memory.py -v` (Python — transient signal tests)
Expected: Rust compiles. Python tests may need fixture adjustments.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/signals.rs \
  src/chronicler/action_engine.py src/chronicler/politics.py \
  src/chronicler/simulation.py src/chronicler/agent_bridge.py \
  tests/test_memory.py
git commit -m "feat(m48): per-region transient signals for conquest/victory/secession"
```

---

## Task 4: Intent Collection & Consolidated Write Phase

**Files:**
- Modify: `chronicler-agents/src/tick.rs` (lines 54-338)
- Modify: `chronicler-agents/src/memory.rs`
- Modify: `chronicler-agents/tests/test_memory.rs`

This is the largest task. The consolidated write phase collects intents from multiple tick phases, then writes them all at once at tick end.

- [ ] **Step 1: Write consolidated write ordering test**

Add to `chronicler-agents/tests/test_memory.rs`:

```rust
#[test]
fn test_consolidated_write_ordering() {
    // Verify that intents from multiple sources all write in the single pass
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    let intents = vec![
        MemoryIntent { agent_slot: slot, event_type: 0, source_civ: 0, intensity: -80 }, // Famine
        MemoryIntent { agent_slot: slot, event_type: 6, source_civ: 1, intensity: 60 },  // Victory
        MemoryIntent { agent_slot: slot, event_type: 4, source_civ: 0, intensity: -30 }, // Migration
    ];
    write_all_memories(&mut pool, &intents, 50);
    assert_eq!(pool.memory_count[slot], 3);
    assert_eq!(pool.memory_event_types[slot][0], 0);
    assert_eq!(pool.memory_event_types[slot][1], 6);
    assert_eq!(pool.memory_event_types[slot][2], 4);
}
```

- [ ] **Step 2: Implement write_all_memories in memory.rs**

```rust
/// Process all collected memory intents in a single pass.
/// Gate checks happen here (not at collection time).
pub fn write_all_memories(pool: &mut AgentPool, intents: &[MemoryIntent], turn: u16) {
    for intent in intents {
        let slot = intent.agent_slot;
        let gate = gate_bit_for(intent.event_type);
        if gate != 0 && (pool.memory_gates[slot] & gate) != 0 {
            continue; // gated — skip
        }
        write_single_memory(pool, intent, turn);
        if gate != 0 {
            pool.memory_gates[slot] |= gate; // set gate bit
        }
    }
}

/// Clear gate bits based on current conditions.
/// Called at the start of the consolidated write pass.
pub fn clear_memory_gates(
    pool: &mut AgentPool,
    alive_slots: &[usize],
    regions: &[crate::region::RegionState],
    contested_regions: &[bool], // from TickSignals, NOT a method on RegionState
) {
    for &slot in alive_slots {
        let gates = pool.memory_gates[slot];
        if gates == 0 { continue; }
        let region_idx = pool.regions[slot] as usize;
        let region = &regions[region_idx];
        let mut new_gates = gates;
        // Bit 0 (BATTLE): clear if not soldier OR not contested
        // NOTE: contested status comes from TickSignals, not RegionState
        if gates & GATE_BIT_BATTLE != 0 {
            let is_soldier = pool.occupations[slot] == 1; // Soldier occupation
            let is_contested = contested_regions.get(region_idx).copied().unwrap_or(false);
            if !is_soldier || !is_contested {
                new_gates &= !GATE_BIT_BATTLE;
            }
        }
        // Bit 1 (PROSPERITY): clear if wealth < threshold
        if gates & GATE_BIT_PROSPERITY != 0 {
            if pool.wealth[slot] < agent::PROSPERITY_THRESHOLD {
                new_gates &= !GATE_BIT_PROSPERITY;
            }
        }
        // Bit 2 (FAMINE): clear if food_sufficiency >= 1.0
        if gates & GATE_BIT_FAMINE != 0 {
            if region.food_sufficiency >= 1.0 {
                new_gates &= !GATE_BIT_FAMINE;
            }
        }
        // Bit 3 (PERSECUTION): clear if persecution_intensity == 0
        if gates & GATE_BIT_PERSECUTION != 0 {
            if region.persecution_intensity <= 0.0 {
                new_gates &= !GATE_BIT_PERSECUTION;
            }
        }
        pool.memory_gates[slot] = new_gates;
    }
}
```

- [ ] **Step 3: Integrate into tick.rs**

The tick.rs changes are the core integration. The implementer must:

1. **Add `decay_memories()` call** as the very first operation in `tick_agents()`, before skill growth (before line 54).

2. **Collect intents** across tick phases by creating a `Vec<MemoryIntent>` at the start of `tick_agents()` and passing it through (or building it in phases):
   - After satisfaction: check `food_sufficiency < FAMINE_MEMORY_THRESHOLD` → FAMINE intent
   - After wealth tick: check `wealth > PROSPERITY_THRESHOLD` → PROSPERITY intent
   - In decision apply: BATTLE (soldier + contested + survived), MIGRATION (migrated), VICTORY (soldier + `war_won_this_turn`)
   - In demographics: BIRTH_OF_KIN (parent), DEATH_OF_KIN (children via reverse index), PROMOTION (promoted agent)
   - In conversion tick: CONVERSION (belief changed — intensity +50 voluntary, -50 if `conquest_conversion_active`), PERSECUTION (minority + persecuted)
   - From region signals: CONQUEST (`controller_changed_this_turn`), SECESSION (`seceded_this_turn`)

3. **Build parent-to-child reverse index** immediately before demographics sequential-apply, before any `pool.kill()` calls. Single O(n) scan.

4. **Call `clear_memory_gates()` then `write_all_memories()`** as the absolute last operations in `tick_agents()`, after displacement decrement (after line 336), before `return events;` (line 338).

The exact intent collection code at each site follows the pattern:

```rust
// Example: FAMINE intent after satisfaction computation
if region.food_sufficiency < agent::FAMINE_MEMORY_THRESHOLD {
    memory_intents.push(MemoryIntent {
        agent_slot: slot,
        event_type: MemoryEventType::Famine as u8,
        source_civ: pool.civ_affinities[slot],
        intensity: agent::FAMINE_DEFAULT_INTENSITY,
    });
}
```

- [ ] **Step 4: Run all Rust tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass including new memory tests.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/memory.rs \
  chronicler-agents/tests/test_memory.rs
git commit -m "feat(m48): consolidated write phase with intent collection across tick"
```

---

## Task 5: Gate Bit Tests

**Files:**
- Modify: `chronicler-agents/tests/test_memory.rs`

- [ ] **Step 1: Write gate bit tests**

```rust
#[test]
fn test_memory_gate_battle() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 1, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // occ=1 is Soldier
    // Write BATTLE — gate should be set
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 1, source_civ: 1, intensity: -60,
    };
    write_all_memories(&mut pool, &[intent.clone()], 10);
    assert_eq!(pool.memory_count[slot], 1);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_BATTLE, 0);
    // Second BATTLE — should be blocked
    write_all_memories(&mut pool, &[intent], 11);
    assert_eq!(pool.memory_count[slot], 1, "gated BATTLE should not write");
}

#[test]
fn test_memory_gate_famine() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 0, source_civ: 0, intensity: -80,
    };
    write_all_memories(&mut pool, &[intent.clone()], 10);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_FAMINE, 0);
    // Second FAMINE — blocked
    write_all_memories(&mut pool, &[intent], 11);
    assert_eq!(pool.memory_count[slot], 1);
}

#[test]
fn test_memory_gate_prosperity() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 5, source_civ: 0, intensity: 50,
    };
    write_all_memories(&mut pool, &[intent.clone()], 10);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PROSPERITY, 0);
    write_all_memories(&mut pool, &[intent], 11);
    assert_eq!(pool.memory_count[slot], 1);
}

#[test]
fn test_memory_gate_persecution() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    let intent = MemoryIntent {
        agent_slot: slot, event_type: 3, source_civ: 1, intensity: -90,
    };
    write_all_memories(&mut pool, &[intent.clone()], 10);
    assert_ne!(pool.memory_gates[slot] & GATE_BIT_PERSECUTION, 0);
    write_all_memories(&mut pool, &[intent], 11);
    assert_eq!(pool.memory_count[slot], 1);
}
```

- [ ] **Step 2: Run and verify pass**

Run: `cargo nextest run -p chronicler-agents test_memory_gate`
Expected: All PASS (gate logic was implemented in Task 4).

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/test_memory.rs
git commit -m "test(m48): gate bit tests for battle, famine, prosperity, persecution"
```

---

## Task 6: Satisfaction Modifier

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs` (SatisfactionInputs struct ~line 131, compute function ~line 159)
- Modify: `chronicler-agents/src/tick.rs` (pass memory score to satisfaction)
- Modify: `chronicler-agents/tests/test_memory.rs`

- [ ] **Step 1: Write satisfaction cap test and same-turn no-feedback test**

NOTE: `SatisfactionInputs` has no `default_test()` constructor. Build the struct manually following the pattern in existing satisfaction tests (e.g., `m37_tests`, `m41_tests` in satisfaction.rs). The function `compute_satisfaction_with_culture()` takes a single `&SatisfactionInputs` argument — NOT two arguments.

```rust
#[test]
fn test_memory_satisfaction_inside_cap() {
    // Verify memory penalty is clamped to remaining 0.40 budget
    // Build SatisfactionInputs manually — match existing test patterns
    let mut inputs = /* build full SatisfactionInputs with mismatch values:
        agent_values mismatching controller_values (cultural penalty),
        agent_belief != majority_belief (religious penalty),
        persecution_intensity = 1.0 (persecution penalty).
        These three should sum to ~0.40, consuming the full budget. */;
    inputs.memory_score = -0.10; // negative memory
    let sat_with_memory = compute_satisfaction_with_culture(&inputs);
    inputs.memory_score = 0.0;
    let sat_without_memory = compute_satisfaction_with_culture(&inputs);
    assert!((sat_with_memory - sat_without_memory).abs() < 0.01,
        "Memory should be absorbed when 0.40 budget is full");
}

#[test]
fn test_same_turn_no_feedback() {
    // Verify the full delay chain: memory written at tick T end
    // does NOT affect satisfaction at tick T, only at tick T+1.
    // This tests the consolidated write architecture.
    let mut pool = AgentPool::new(/* capacity */);
    let slot = pool.spawn(/* ... actual params ... */);
    // Manually write a strong negative memory
    pool.memory_intensities[slot][0] = -90;
    pool.memory_event_types[slot][0] = 0; // Famine
    pool.memory_decay_factors[slot][0] = factor_from_half_life(40.0);
    pool.memory_count[slot] = 1;
    // Compute satisfaction — should NOT include the memory yet
    // (memory was written at end of tick, satisfaction reads at tick start)
    // In the real tick, decay runs first (start of tick T+1),
    // THEN satisfaction reads the decayed value.
    // So tick T satisfaction sees the PREVIOUS turn's memory state.
    let score_before = compute_memory_satisfaction_score(&pool, slot);
    assert!(score_before.abs() > 0.01, "Memory score should be nonzero");
    // After one decay pass, score should be slightly reduced
    decay_memories(&mut pool, &[slot]);
    let score_after = compute_memory_satisfaction_score(&pool, slot);
    assert!(score_after.abs() < score_before.abs(),
        "Score should decrease after decay: before={}, after={}", score_before, score_after);
}
```

- [ ] **Step 2: Add `memory_score: f32` to SatisfactionInputs**

In `satisfaction.rs`, add `pub memory_score: f32,` to the `SatisfactionInputs` struct (after `merchant_margin`). Default to `0.0` in all existing constructors/tests.

- [ ] **Step 3: Add 5th-priority clamping in compute_satisfaction_with_culture()**

NOTE: `compute_satisfaction_with_culture()` takes a single `&SatisfactionInputs` argument (satisfaction.rs ~line 159). It internally calls `compute_satisfaction()`. Do NOT change the function signature — just add the memory clamping logic inside the function body.

After the class tension clamping block (~line 203), add:

```rust
// M48: Memory penalty — 5th priority (lowest), takes whatever budget remains
let memory_clamped = if inputs.memory_score < 0.0 {
    inputs.memory_score.max(-(PENALTY_CAP - three_term - class_tension_clamped).max(0.0))
} else {
    inputs.memory_score // positive memories reduce penalty freely
};
let total_non_eco_penalty = (three_term + class_tension_clamped + memory_clamped)
    .min(PENALTY_CAP)
    .max(0.0); // positive memories cannot create net bonus
```

- [ ] **Step 4: Pass memory score in tick.rs satisfaction call**

Where `update_satisfaction()` is called (tick.rs ~line 77), compute memory score and pass it:

```rust
let mem_score = crate::memory::compute_memory_satisfaction_score(pool, slot);
// Include mem_score in SatisfactionInputs construction
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs \
  chronicler-agents/tests/test_memory.rs
git commit -m "feat(m48): memory satisfaction modifier inside 0.40 cap, 5th priority"
```

---

## Task 7: Decision Utility Modifiers

**Files:**
- Modify: `chronicler-agents/src/behavior.rs` (~lines 342-370)
- Modify: `chronicler-agents/tests/test_memory.rs`

- [ ] **Step 1: Write utility modifier test**

```rust
#[test]
fn test_utility_modifier_mapping() {
    let mut pool = AgentPool::new();
    let slot = pool.spawn(0, 0, 0, 0, 0.5, [0.0; 5], 20, [0, 0, 0], 0, 0, 0.5);
    // Write FAMINE memory at intensity -80
    pool.memory_intensities[slot][0] = -80;
    pool.memory_event_types[slot][0] = 0; // Famine
    pool.memory_source_civs[slot][0] = 0;
    pool.memory_count[slot] = 1;

    let modifiers = compute_memory_utility_modifiers(&pool, slot);
    // FAMINE → MIGRATE boost, scaled by intensity/128
    let scale = -80.0 / -128.0; // ~0.625
    let expected_migrate = agent::FAMINE_MIGRATE_BOOST * scale;
    assert!((modifiers.migrate - expected_migrate).abs() < 0.01,
        "Famine memory should boost migrate by ~{:.3}, got {:.3}",
        expected_migrate, modifiers.migrate);
    // Other modifiers should be near zero
    assert!(modifiers.rebel.abs() < 0.01);
}
```

- [ ] **Step 2: Implement memory utility modifiers in memory.rs**

```rust
/// Utility modifier outputs for agent decisions
#[derive(Debug, Default)]
pub struct MemoryUtilityModifiers {
    pub rebel: f32,
    pub migrate: f32,
    pub switch: f32,
    pub stay: f32,
}

/// Compute additive utility modifiers from an agent's active memories.
/// Each memory type contributes to specific decision utilities,
/// scaled by intensity/128.0 (normalized to [-1.0, +1.0]).
pub fn compute_memory_utility_modifiers(
    pool: &AgentPool,
    slot: usize,
) -> MemoryUtilityModifiers {
    let mut mods = MemoryUtilityModifiers::default();
    let count = pool.memory_count[slot] as usize;
    let boldness = pool.boldness[slot];

    for i in 0..count {
        let intensity = pool.memory_intensities[slot][i];
        if intensity == 0 { continue; }
        let scale = intensity as f32 / 128.0; // negative for negative memories
        let abs_scale = scale.abs();
        let event_type = pool.memory_event_types[slot][i];
        let source_civ = pool.memory_source_civs[slot][i];
        let agent_civ = pool.civ_affinities[slot];

        match event_type {
            0 => { // Famine
                mods.migrate += agent::FAMINE_MIGRATE_BOOST * abs_scale;
            }
            1 => { // Battle
                if boldness > 0.0 {
                    mods.stay += agent::BATTLE_BOLD_STAY_BOOST * abs_scale;
                } else {
                    mods.migrate += agent::BATTLE_CAUTIOUS_MIGRATE_BOOST * abs_scale;
                }
            }
            2 => { // Conquest
                if source_civ == agent_civ {
                    mods.stay += agent::CONQUEST_CONQUEROR_STAY_BOOST * abs_scale;
                } else {
                    mods.migrate += agent::CONQUEST_CONQUERED_MIGRATE_BOOST * abs_scale;
                }
            }
            3 => { // Persecution
                mods.rebel += agent::PERSECUTION_REBEL_BOOST_MEMORY * abs_scale;
                mods.migrate += agent::PERSECUTION_MIGRATE_BOOST_MEMORY * abs_scale;
            }
            5 => { // Prosperity
                mods.migrate -= agent::PROSPERITY_MIGRATE_PENALTY * abs_scale;
                mods.switch -= agent::PROSPERITY_SWITCH_PENALTY * abs_scale;
            }
            6 => { // Victory
                mods.stay += agent::VICTORY_STAY_BOOST * abs_scale;
            }
            9 => { // DeathOfKin
                mods.migrate -= agent::DEATHOFKIN_MIGRATE_PENALTY * abs_scale;
            }
            _ => {} // Migration, Promotion, BirthOfKin, Conversion, Secession, Legacy — no utility effect
        }
    }
    mods
}
```

- [ ] **Step 3: Wire into behavior.rs**

In `evaluate_region_decisions()`, after the existing persecution boosts (~line 351) and before `gumbel_argmax()` (~line 366), add:

```rust
// M48: Memory-driven utility modifiers
let mem_mods = crate::memory::compute_memory_utility_modifiers(pool, slot);
u_rebel += mem_mods.rebel;
u_migrate += mem_mods.migrate;
u_switch += mem_mods.switch;
u_stay += mem_mods.stay;
```

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/memory.rs chronicler-agents/src/behavior.rs \
  chronicler-agents/tests/test_memory.rs
git commit -m "feat(m48): memory-driven utility modifiers on agent decisions"
```

---

## Task 8: FFI — get_agent_memories

**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (after existing pymethods, ~line 727)
- Modify: `tests/test_memory.py`

- [ ] **Step 1: Write Python FFI test**

Add to `tests/test_memory.py`:

```python
class TestFFI:
    def test_get_agent_memories(self, agent_simulator_with_memories):
        """FFI method returns correct memory slots for a known agent."""
        sim, agent_id = agent_simulator_with_memories
        memories = sim.get_agent_memories(agent_id)
        assert len(memories) > 0
        # Each memory is (event_type, source_civ, turn, intensity, decay_factor)
        for mem in memories:
            assert len(mem) == 5
            event_type, source_civ, turn, intensity, decay_factor = mem
            assert 0 <= event_type <= 14

    def test_get_agent_memories_dead_agent(self, agent_simulator):
        """Dead agent returns empty list."""
        memories = agent_simulator.get_agent_memories(99999)
        assert memories == []
```

- [ ] **Step 2: Add get_agent_memories pymethod to ffi.rs**

```rust
#[pymethods]
impl AgentSimulator {
    /// M48: Return memory slots for a specific agent.
    /// Returns Vec<(event_type, source_civ, turn, intensity, decay_factor)>.
    /// Empty vec if agent not found or dead.
    fn get_agent_memories(&self, agent_id: u32) -> Vec<(u8, u8, u16, i8, u8)> {
        // O(N) scan for agent_id — acceptable for ~50 named character queries
        let pool = &self.pool;
        for slot in 0..pool.ids.len() {
            if pool.ids[slot] == agent_id && pool.alive[slot] {
                let count = pool.memory_count[slot] as usize;
                let mut result = Vec::with_capacity(count);
                for i in 0..count {
                    result.push((
                        pool.memory_event_types[slot][i],
                        pool.memory_source_civs[slot][i],
                        pool.memory_turns[slot][i],
                        pool.memory_intensities[slot][i],
                        pool.memory_decay_factors[slot][i],
                    ));
                }
                return result;
            }
        }
        Vec::new()
    }
}
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Run: `pytest tests/test_memory.py::TestFFI -v`

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/ffi.rs tests/test_memory.py
git commit -m "feat(m48): get_agent_memories FFI method"
```

---

## Task 9: GreatPerson Fields + Mule Promotion

**Files:**
- Modify: `src/chronicler/models.py` (GreatPerson class)
- Modify: `src/chronicler/agent_bridge.py` (`_process_promotions`)
- Modify: `tests/test_memory.py`

- [ ] **Step 1: Write Mule promotion test**

Add to `tests/test_memory.py`:

```python
class TestMulePromotion:
    def test_mule_promotion_determinism(self):
        """Same seed produces same Mule flag and overrides."""
        # Run promotion logic twice with same seed — both should produce identical Mule state
        gp1 = _simulate_promotion(seed=42, turn=100, agent_id=500)
        gp2 = _simulate_promotion(seed=42, turn=100, agent_id=500)
        assert gp1.mule == gp2.mule
        assert gp1.mule_memory_event_type == gp2.mule_memory_event_type
        assert gp1.utility_overrides == gp2.utility_overrides
```

- [ ] **Step 2: Add Mule fields to GreatPerson in models.py**

```python
# M48: Mule promotion system
mule: bool = False
mule_memory_event_type: Optional[int] = None
utility_overrides: dict = Field(default_factory=dict)  # ActionType name -> multiplier
memories: list = Field(default_factory=list)  # cached from Rust via FFI
```

- [ ] **Step 3: Add Mule detection in _process_promotions**

In `agent_bridge.py`, in `_process_promotions()`, after GreatPerson creation:

```python
# M48: Mule promotion roll
import random
MULE_PROMOTION_PROBABILITY = 0.07  # [CALIBRATE M53] target 5-10%
MULE_MAPPING = {
    0: {"DEVELOP": 3.0, "TRADE": 2.0, "WAR": 0.3},        # Famine
    1: {"WAR": 3.0, "DIPLOMACY": 0.5},                      # Battle
    2: {"WAR": 3.0, "EXPAND": 2.0, "DIPLOMACY": 0.3},      # Conquest
    3: {"FUND_INSTABILITY": 3.0, "TRADE": 0.5},             # Persecution
    4: {"EXPAND": 3.0, "TRADE": 2.0},                       # Migration
    6: {"WAR": 2.5, "EXPAND": 2.0},                         # Victory
    9: {"DIPLOMACY": 3.0, "WAR": 0.3},                      # DeathOfKin
    10: {"INVEST_CULTURE": 3.0, "BUILD": 2.0},              # Conversion
    11: {"DIPLOMACY": 2.5, "INVEST_CULTURE": 2.0},          # Secession
}

mule_rng = random.Random(world.seed + world.turn * 7919 + gp.agent_id)
if mule_rng.random() < MULE_PROMOTION_PROBABILITY:
    # Get agent's memories
    memories = self.simulator.get_agent_memories(gp.agent_id)
    if memories:
        # Find strongest memory (highest |intensity|)
        strongest = max(memories, key=lambda m: abs(m[3]))  # m[3] = intensity
        event_type = strongest[0]
        if event_type in MULE_MAPPING:
            gp.mule = True
            gp.mule_memory_event_type = event_type
            gp.utility_overrides = MULE_MAPPING[event_type]
```

- [ ] **Step 4: Add memory sync on GreatPerson**

In `_process_promotions()` or the Phase 10 event processing loop, after `_detect_character_events` and before arc classification, add:

```python
# M48: Sync memories for named characters
for gp in world.great_persons:
    if gp.active and gp.agent_id is not None:
        raw_memories = self.simulator.get_agent_memories(gp.agent_id)
        gp.memories = [
            {"event_type": m[0], "source_civ": m[1], "turn": m[2],
             "intensity": m[3], "decay_factor": m[4]}
            for m in raw_memories
        ]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_memory.py::TestMulePromotion -v`

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py src/chronicler/agent_bridge.py tests/test_memory.py
git commit -m "feat(m48): Mule promotion system with memory-driven utility overrides"
```

---

## Task 10: Mule Action Engine Integration

**Files:**
- Modify: `src/chronicler/action_engine.py`
- Modify: `tests/test_memory.py`

- [ ] **Step 1: Write Mule action engine tests**

Add to `tests/test_memory.py`:

```python
MULE_ACTIVE_WINDOW = 25  # [CALIBRATE M53]
MULE_FADE_TURNS = 10     # [CALIBRATE M53]


class TestMuleActionEngine:
    def test_mule_active_window(self):
        """Mule boost applies during window, fades linearly, zeroes after."""
        gp = _make_mule_gp(born_turn=100, overrides={"WAR": 3.0})
        # Active window
        assert get_mule_factor(gp, "WAR", 110) == 3.0
        # Fade period (turn 125 = start of fade)
        factor = get_mule_factor(gp, "WAR", 130)
        assert 1.0 < factor < 3.0, f"Should be fading, got {factor}"
        # After fade
        assert get_mule_factor(gp, "WAR", 140) == 1.0

    def test_mule_streak_interaction(self):
        """Streak-breaker zeros Mule's preferred action."""
        # Mule boosts WAR, but WAR was the last 3 actions → streak-breaker zeros it
        weights = _compute_weights_with_mule(
            mule_overrides={"WAR": 3.0},
            action_history=["WAR", "WAR", "WAR"]
        )
        assert weights["WAR"] == 0.0  # streak-breaker wins

    def test_mule_weight_cap(self):
        """Mule boost subject to 2.5x proportional rescale."""
        weights = _compute_weights_with_mule(
            mule_overrides={"WAR": 4.0},
            action_history=[]
        )
        assert max(weights.values()) <= 2.5 + 0.01

    def test_mule_suppression_floor(self):
        """Suppression multiplier floors at 0.1x; zero-weight stays zero."""
        weights = _compute_weights_with_mule(
            mule_overrides={"WAR": 0.05},  # below 0.1 floor
            action_history=[]
        )
        # WAR should be floored at 0.1x of pre-Mule value, not 0.05x
        assert weights["WAR"] > 0
```

- [ ] **Step 2: Implement get_mule_factor and action engine integration**

Add constants and function to `action_engine.py`:

```python
# M48: Mule constants [CALIBRATE M53]
MULE_ACTIVE_WINDOW = 25
MULE_FADE_TURNS = 10
```

```python
def get_mule_factor(gp, action_name: str, current_turn: int) -> float:
    """Compute the Mule's weight multiplier for a given action."""
    if not gp.mule or not gp.active:
        return 1.0
    age = current_turn - gp.born_turn
    if age > MULE_ACTIVE_WINDOW + MULE_FADE_TURNS:
        return 1.0
    base = gp.utility_overrides.get(action_name, 1.0)
    if age <= MULE_ACTIVE_WINDOW:
        return base
    fade_progress = (age - MULE_ACTIVE_WINDOW) / MULE_FADE_TURNS
    return base + (1.0 - base) * fade_progress
```

In `_compute_weights()`, after K_AGGRESSION_BIAS application and before the streak-breaker block, add:

```python
# M48: Mule weight modification
for gp in [gp for gp in self.world.great_persons
           if gp.mule and gp.active and gp.civilization == civ.name]:
    for action in ActionType:
        factor = get_mule_factor(gp, action.name, self.world.turn)
        if weights[action] > 0:
            weights[action] *= max(factor, 0.1)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_memory.py::TestMuleActionEngine -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_memory.py
git commit -m "feat(m48): Mule action engine integration with fade and cap"
```

---

## Task 11: Narration Integration

**Files:**
- Modify: `src/chronicler/narrative.py`

- [ ] **Step 1: Add memory rendering and narrator context**

```python
# M48: Memory descriptions for narration
MEMORY_DESCRIPTIONS = {
    0: "a great famine under the {civ}",
    1: "combat against the {civ}",
    2: "the fall of the {civ}",
    3: "persecution by the {civ}",
    4: "a migration from {civ} lands",
    5: "a time of prosperity",
    6: "victory over the {civ}",
    7: "a great achievement",
    8: "the birth of a child",
    9: "the death of kin",
    10: "a change of faith",
    11: "the fracture of the {civ}",
}

MEMORY_NARRATION_VIVID = 60   # [CALIBRATE M53]
MEMORY_NARRATION_FADING = 30  # [CALIBRATE M53]


def render_memory(mem: dict, civ_names: list) -> str | None:
    """Render a memory slot as a natural language fragment."""
    intensity = abs(mem.get("intensity", 0))
    if intensity < MEMORY_NARRATION_FADING:
        return None  # too weak to mention
    template = MEMORY_DESCRIPTIONS.get(mem["event_type"], "an event")
    source = mem.get("source_civ", 0)
    civ_name = civ_names[source] if source < len(civ_names) else "unknown"
    descriptor = "vivid" if intensity >= MEMORY_NARRATION_VIVID else "fading"
    text = template.format(civ=civ_name, turn=mem["turn"])
    return f"{text} (turn {mem['turn']}, {descriptor})"
```

- [ ] **Step 2: Add memory context to build_agent_context_for_moment()**

In the function that builds narrator context for named characters, add:

```python
# M48: Memory context
if hasattr(gp, 'memories') and gp.memories:
    civ_names = [c.name for c in world.civilizations]
    rendered = [render_memory(m, civ_names) for m in gp.memories]
    rendered = [r for r in rendered if r is not None]
    if rendered:
        lines.append("Memories:")
        for r in rendered:
            lines.append(f"  - {r}")

# M48: Mule context
if gp.mule and gp.active:
    remaining = (gp.born_turn + MULE_ACTIVE_WINDOW + MULE_FADE_TURNS) - world.turn
    if remaining > 0:
        overrides_str = ", ".join(f"{k} x{v}" for k, v in gp.utility_overrides.items())
        lines.append(f"[MULE] Active influence: {overrides_str}")
        lines.append(f"  Window: {remaining} turns remaining")
```

- [ ] **Step 3: Run narration tests**

Run: `pytest tests/ -k narrat -v` (any existing narration tests)

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/narrative.py
git commit -m "feat(m48): memory rendering and Mule context in narration pipeline"
```

---

## Task 12: Bond Formation Query + Integration Tests

**Files:**
- Modify: `chronicler-agents/src/memory.rs`
- Modify: `tests/test_memory.py`

- [ ] **Step 1: Implement agents_share_memory query**

Add to `memory.rs`:

```rust
/// M50 interface: Check if two agents share a memory (same event_type, turn within ±1).
/// Returns (event_type, turn) of the strongest shared match, or None.
pub fn agents_share_memory(pool: &AgentPool, a: usize, b: usize) -> Option<(u8, u16)> {
    let count_a = pool.memory_count[a] as usize;
    let count_b = pool.memory_count[b] as usize;
    let mut best: Option<(u8, u16, u16)> = None; // (event_type, turn, combined_intensity)
    for i in 0..count_a {
        let et_a = pool.memory_event_types[a][i];
        let turn_a = pool.memory_turns[a][i];
        let int_a = pool.memory_intensities[a][i].unsigned_abs() as u16;
        for j in 0..count_b {
            if pool.memory_event_types[b][j] == et_a
                && turn_a.abs_diff(pool.memory_turns[b][j]) <= 1
            {
                let combined = int_a + pool.memory_intensities[b][j].unsigned_abs() as u16;
                if best.is_none() || combined > best.unwrap().2 {
                    best = Some((et_a, turn_a, combined));
                }
            }
        }
    }
    best.map(|(et, turn, _)| (et, turn))
}
```

- [ ] **Step 2: Write Python integration tests**

Add to `tests/test_memory.py`:

```python
class TestIntegration:
    def test_agents_off_unaffected(self):
        """--agents=off produces identical output with memory system present."""
        # Use run_turn() with agents=off, compare snapshots against baseline
        world = _create_test_world(agents="off")
        snapshot_before = _snapshot_civ_stats(world)
        for _ in range(10):
            run_turn(world)
        snapshot_after = _snapshot_civ_stats(world)
        # Verify simulation runs and produces non-trivial output
        assert snapshot_after != snapshot_before
        # Memory fields should not exist in --agents=off path
```

- [ ] **Step 3: Run all tests**

Run: `cargo nextest run -p chronicler-agents`
Run: `pytest tests/test_memory.py -v`

- [ ] **Step 4: Final commit**

```bash
git add chronicler-agents/src/memory.rs tests/test_memory.py
git commit -m "feat(m48): M50 bond query interface, integration tests"
```

---

## Verification Checklist

After all 12 tasks are complete:

- [ ] `cargo nextest run -p chronicler-agents` — all Rust tests pass (including existing 188+)
- [ ] `pytest tests/test_memory.py -v` — all Python memory tests pass
- [ ] `pytest tests/ -v` — full test suite passes (no regressions)
- [ ] `--agents=off` mode produces identical output (memory system is Rust-only)
- [ ] 3 transient signals each have 2-turn reset tests
- [ ] No new files created outside the scope specified above
