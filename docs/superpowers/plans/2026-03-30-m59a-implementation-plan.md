# M59a: Information Packets & Diffusion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent-level information packet substrate — per-agent fixed-width packet slots with direct observation, relationship-driven propagation, decay, and diagnostics.

**Architecture:** 4 packet slots per agent (24 bytes) stored as SoA arrays in Rust `AgentPool`. A new `knowledge.rs` module owns the `InfoType` enum, packet operations, knowledge phase orchestration (decay → observation → buffered propagation → commit), and a `KnowledgeStats` diagnostics struct. The knowledge phase runs at tick phase 0.95 (after merchant mobility, before satisfaction). Python receives only aggregate diagnostics via `get_knowledge_stats()` FFI method.

**Tech Stack:** Rust (chronicler-agents crate), Python (agent_bridge.py, main.py, analytics.py), PyO3 FFI, `rand_chacha` for deterministic keyed rolls.

**Spec:** `docs/superpowers/specs/2026-03-30-m59a-information-packets-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/knowledge.rs` | InfoType enum, packet constants, KnowledgeStats struct, packet slot helpers (admit, decay, observe, propagate, commit), knowledge phase orchestrator |
| `chronicler-agents/tests/test_knowledge.rs` | Rust unit/integration tests for packet lifecycle, admission, propagation, determinism |
| `tests/test_m59a_knowledge.py` | Python integration tests for diagnostics bridge, `--agents=off` compat, behavioral inertia |

### Modified Files

| File | Change Summary |
|------|---------------|
| `chronicler-agents/src/lib.rs:8-31` | Add `pub mod knowledge;` |
| `chronicler-agents/src/agent.rs:89-114` | Register `KNOWLEDGE_STREAM_OFFSET = 1800` |
| `chronicler-agents/src/pool.rs:17-102` | Add 4 packet SoA slot arrays + `arrived_this_turn` field to struct, `new()`, `spawn()`, `kill()` |
| `chronicler-agents/src/tick.rs:107-133` | Insert knowledge phase call at 0.95 between merchant mobility and satisfaction |
| `chronicler-agents/src/merchant.rs:658-675` | Set `arrived_this_turn` flag on merchant arrival |
| `chronicler-agents/src/ffi.rs:2349-2374` | Store `KnowledgeStats`, add `get_knowledge_stats()` method |
| `src/chronicler/agent_bridge.py:850-870` | Collect knowledge_stats after tick |
| `src/chronicler/main.py:746-762` | Append knowledge_stats to bundle metadata |
| `src/chronicler/analytics.py:1952+` | Add `extract_knowledge_stats()` extractor |

---

## Task 1: Pool Storage — Packet SoA Arrays + Arrival Flag

**Files:**
- Modify: `chronicler-agents/src/agent.rs:89-116` — add stream offset constant
- Modify: `chronicler-agents/src/pool.rs:17-94` — add fields to struct
- Modify: `chronicler-agents/src/pool.rs:106-167` — add fields to `new()`
- Modify: `chronicler-agents/src/pool.rs:188-314` — add fields to `spawn()`
- Test: `chronicler-agents/tests/test_knowledge.rs` — new file

- [ ] **Step 1: Register RNG stream offset in agent.rs**

In `chronicler-agents/src/agent.rs`, after line 114 (`MERCHANT_ROUTE_STREAM_OFFSET`), add:

```rust
// M59a: Information packet propagation
pub const KNOWLEDGE_STREAM_OFFSET: u64 = 1800;
```

- [ ] **Step 2: Add packet constants to agent.rs**

In the same area of `chronicler-agents/src/agent.rs`, add:

```rust
// M59a: Packet slot constants
pub const PACKET_SLOTS: usize = 4;
pub const PACKET_TYPE_EMPTY: u8 = 0;
pub const MAX_HOP_COUNT: u8 = 31;
```

- [ ] **Step 3: Add packet SoA fields to AgentPool struct**

In `chronicler-agents/src/pool.rs`, after the trip state fields (line 92, `trip_path_cursor`) and before `alive` (line 94), add:

```rust
    // M59a: Information packet slots (4 per agent)
    pub pkt_type_and_hops: Vec<[u8; 4]>,
    pub pkt_source_region: Vec<[u16; 4]>,
    pub pkt_source_turn: Vec<[u16; 4]>,
    pub pkt_intensity: Vec<[u8; 4]>,
    // M59a: Merchant arrival transient (set by 0.9 merchant mobility, cleared by 0.95 knowledge phase)
    pub arrived_this_turn: Vec<bool>,
```

- [ ] **Step 4: Initialize packet fields in `AgentPool::new()`**

In `chronicler-agents/src/pool.rs`, in the `new()` method, after `trip_path_cursor` init (line 161) and before `alive` init (line 162), add:

```rust
            pkt_type_and_hops: Vec::with_capacity(capacity),
            pkt_source_region: Vec::with_capacity(capacity),
            pkt_source_turn: Vec::with_capacity(capacity),
            pkt_intensity: Vec::with_capacity(capacity),
            arrived_this_turn: Vec::with_capacity(capacity),
```

- [ ] **Step 5: Initialize packet fields in `spawn()` — reuse path (slot exists)**

In `chronicler-agents/src/pool.rs`, in the reuse branch of `spawn()`, after `trip_path_cursor[slot] = 0;` (line 247) and before `alive[slot] = true;` (line 248), add:

```rust
            self.pkt_type_and_hops[slot] = [0; 4];
            self.pkt_source_region[slot] = [0; 4];
            self.pkt_source_turn[slot] = [0; 4];
            self.pkt_intensity[slot] = [0; 4];
            self.arrived_this_turn[slot] = false;
```

- [ ] **Step 6: Initialize packet fields in `spawn()` — grow path (new slot)**

In `chronicler-agents/src/pool.rs`, in the grow branch of `spawn()`, after `trip_path_cursor.push(0);` (line 310) and before `alive.push(true);` (line 311), add:

```rust
            self.pkt_type_and_hops.push([0; 4]);
            self.pkt_source_region.push([0; 4]);
            self.pkt_source_turn.push([0; 4]);
            self.pkt_intensity.push([0; 4]);
            self.arrived_this_turn.push(false);
```

- [ ] **Step 7: Write failing test — pool spawns with empty packets**

Create `chronicler-agents/tests/test_knowledge.rs`:

```rust
//! M59a: Information packet substrate tests.

use chronicler_agents::{AgentPool, Occupation, RegionState};

#[test]
fn test_spawn_has_empty_packets() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    for i in 0..4 {
        assert_eq!(pool.pkt_type_and_hops[slot][i], 0, "slot {i} type_and_hops should be 0");
        assert_eq!(pool.pkt_source_region[slot][i], 0, "slot {i} source_region should be 0");
        assert_eq!(pool.pkt_source_turn[slot][i], 0, "slot {i} source_turn should be 0");
        assert_eq!(pool.pkt_intensity[slot][i], 0, "slot {i} intensity should be 0");
    }
    assert!(!pool.arrived_this_turn[slot], "arrived_this_turn should be false on spawn");
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge -E 'test(test_spawn_has_empty_packets)'`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/agent.rs chronicler-agents/src/pool.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): add packet SoA storage and arrival flag to AgentPool"
```

---

## Task 2: knowledge.rs — InfoType, Constants, and Packet Helpers

**Files:**
- Create: `chronicler-agents/src/knowledge.rs`
- Modify: `chronicler-agents/src/lib.rs:8-31` — register module
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Create knowledge.rs with InfoType enum and constants**

Create `chronicler-agents/src/knowledge.rs`:

```rust
//! M59a: Information packet substrate — types, helpers, knowledge phase.

use crate::agent;
use crate::pool::AgentPool;
use crate::region::RegionState;

// ---------------------------------------------------------------------------
// InfoType
// ---------------------------------------------------------------------------

#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InfoType {
    Empty           = 0,
    ThreatWarning   = 1,
    TradeOpportunity = 2,
    ReligiousSignal = 3,
}

impl InfoType {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0 => Some(Self::Empty),
            1 => Some(Self::ThreatWarning),
            2 => Some(Self::TradeOpportunity),
            3 => Some(Self::ReligiousSignal),
            _ => None,
        }
    }

    /// Retention priority for eviction ranking. Higher = harder to evict.
    pub fn retention_priority(self) -> u8 {
        match self {
            Self::Empty => 0,
            Self::ThreatWarning => 3,
            Self::TradeOpportunity => 2,
            Self::ReligiousSignal => 1,
        }
    }
}

// ---------------------------------------------------------------------------
// Packet field encoding
// ---------------------------------------------------------------------------

/// Pack info_type (upper 3 bits) and hop_count (lower 5 bits) into a u8.
#[inline]
pub fn pack_type_hops(info_type: u8, hop_count: u8) -> u8 {
    (info_type << 5) | (hop_count & 0x1F)
}

/// Extract info_type from packed type_and_hops byte.
#[inline]
pub fn unpack_type(type_and_hops: u8) -> u8 {
    type_and_hops >> 5
}

/// Extract hop_count from packed type_and_hops byte.
#[inline]
pub fn unpack_hops(type_and_hops: u8) -> u8 {
    type_and_hops & 0x1F
}

/// Check if a packet slot is empty.
#[inline]
pub fn is_empty_slot(type_and_hops: u8) -> bool {
    unpack_type(type_and_hops) == InfoType::Empty as u8
}

// ---------------------------------------------------------------------------
// Decay constants
// ---------------------------------------------------------------------------

pub const DECAY_THREAT: u8 = 15;
pub const DECAY_TRADE: u8 = 8;
pub const DECAY_RELIGIOUS: u8 = 5;

pub fn decay_rate(info_type: u8) -> u8 {
    match info_type {
        1 => DECAY_THREAT,
        2 => DECAY_TRADE,
        3 => DECAY_RELIGIOUS,
        _ => 0,
    }
}

// ---------------------------------------------------------------------------
// Propagation constants
// ---------------------------------------------------------------------------

pub const BASE_RATE_THREAT: f32 = 0.7;
pub const BASE_RATE_TRADE: f32 = 0.4;
pub const BASE_RATE_RELIGIOUS: f32 = 0.25;
pub const HOP_ATTENUATION: f32 = 0.85;

pub fn base_rate(info_type: u8) -> f32 {
    match info_type {
        1 => BASE_RATE_THREAT,
        2 => BASE_RATE_TRADE,
        3 => BASE_RATE_RELIGIOUS,
        _ => 0.0,
    }
}

// ---------------------------------------------------------------------------
// Direct observation intensity constants
// ---------------------------------------------------------------------------

pub const INTENSITY_CONTROLLER_CHANGED: u8 = 200;
pub const INTENSITY_WAR_WON: u8 = 180;
pub const INTENSITY_SECESSION: u8 = 150;
pub const INTENSITY_SCHISM: u8 = 160;

/// Minimum merchant_route_margin to emit a trade_opportunity packet.
pub const TRADE_MARGIN_THRESHOLD: f32 = 0.10;

/// Minimum conversion_rate to emit a religious_signal packet.
pub const CONVERSION_RATE_THRESHOLD: f32 = 0.05;

// ---------------------------------------------------------------------------
// Channel filter + weight tables
// ---------------------------------------------------------------------------

use crate::relationships::BondType;

/// Returns the channel weight for a (bond_type, info_type) pair, or None if
/// this bond does not carry this packet type.
pub fn channel_weight(bond_type: u8, info_type: u8) -> Option<f32> {
    match (bond_type, info_type) {
        // threat_warning (type 1): all positive-valence bonds
        (0, 1) => Some(1.0),  // Mentor
        (2, 1) => Some(1.0),  // Marriage
        (3, 1) => Some(0.8),  // ExileBond
        (4, 1) => Some(0.9),  // CoReligionist
        (5, 1) => Some(1.0),  // Kin
        (6, 1) => Some(0.9),  // Friend
        // trade_opportunity (type 2): Friend, Mentor, Marriage, Kin
        (0, 2) => Some(0.8),  // Mentor
        (2, 2) => Some(0.9),  // Marriage
        (5, 2) => Some(0.7),  // Kin
        (6, 2) => Some(1.0),  // Friend
        // religious_signal (type 3): CoReligionist primary, Kin + Marriage secondary
        (2, 3) => Some(0.6),  // Marriage
        (4, 3) => Some(1.0),  // CoReligionist
        (5, 3) => Some(0.7),  // Kin
        // Everything else: not eligible
        _ => None,
    }
}

// ---------------------------------------------------------------------------
// KnowledgeStats
// ---------------------------------------------------------------------------

/// Per-turn diagnostics accumulated during the knowledge phase.
#[derive(Clone, Debug, Default)]
pub struct KnowledgeStats {
    pub packets_created: u32,
    pub packets_refreshed: u32,
    pub packets_transmitted: u32,
    pub packets_expired: u32,
    pub packets_evicted: u32,
    pub packets_dropped: u32,
    pub live_packet_count: u32,
    pub agents_with_packets: u32,
    pub created_threat: u32,
    pub created_trade: u32,
    pub created_religious: u32,
    pub transmitted_threat: u32,
    pub transmitted_trade: u32,
    pub transmitted_religious: u32,
    pub mean_age: f32,
    pub max_age: u32,
    pub mean_hops: f32,
    pub max_hops: u32,
}
```

- [ ] **Step 2: Register module in lib.rs**

In `chronicler-agents/src/lib.rs`, after `pub mod merchant;` (line 31), add:

```rust
pub mod knowledge;
```

- [ ] **Step 3: Write failing test for pack/unpack helpers**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::{
    pack_type_hops, unpack_type, unpack_hops, is_empty_slot, InfoType,
    channel_weight, decay_rate, base_rate,
};

#[test]
fn test_pack_unpack_type_hops() {
    // ThreatWarning (1) with 5 hops
    let packed = pack_type_hops(1, 5);
    assert_eq!(unpack_type(packed), 1);
    assert_eq!(unpack_hops(packed), 5);

    // Empty (0) with 0 hops
    let packed = pack_type_hops(0, 0);
    assert_eq!(packed, 0);
    assert!(is_empty_slot(packed));

    // Max hop count (31)
    let packed = pack_type_hops(3, 31);
    assert_eq!(unpack_type(packed), 3);
    assert_eq!(unpack_hops(packed), 31);

    // Hop count overflow is masked to 5 bits
    let packed = pack_type_hops(1, 33); // 33 & 0x1F = 1
    assert_eq!(unpack_hops(packed), 1);
}

#[test]
fn test_retention_priority_order() {
    assert!(InfoType::ThreatWarning.retention_priority() > InfoType::TradeOpportunity.retention_priority());
    assert!(InfoType::TradeOpportunity.retention_priority() > InfoType::ReligiousSignal.retention_priority());
    assert!(InfoType::ReligiousSignal.retention_priority() > InfoType::Empty.retention_priority());
}

#[test]
fn test_channel_weight_filters() {
    // Threat: Mentor eligible, Rival not
    assert!(channel_weight(BondType::Mentor as u8, 1).is_some());
    assert!(channel_weight(BondType::Rival as u8, 1).is_none());
    assert!(channel_weight(BondType::Grudge as u8, 1).is_none());

    // Trade: Friend eligible, CoReligionist not
    assert!(channel_weight(BondType::Friend as u8, 2).is_some());
    assert!(channel_weight(BondType::CoReligionist as u8, 2).is_none());

    // Religious: CoReligionist eligible, Friend not
    assert!(channel_weight(BondType::CoReligionist as u8, 3).is_some());
    assert!(channel_weight(BondType::Friend as u8, 3).is_none());
}

#[test]
fn test_decay_rates() {
    assert_eq!(decay_rate(1), 15); // threat
    assert_eq!(decay_rate(2), 8);  // trade
    assert_eq!(decay_rate(3), 5);  // religious
    assert_eq!(decay_rate(0), 0);  // empty
}
```

- [ ] **Step 4: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/src/lib.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): add knowledge.rs with InfoType, constants, channel tables, KnowledgeStats"
```

---

## Task 3: Admission Policy

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Implement `admit_packet` in knowledge.rs**

Add to `chronicler-agents/src/knowledge.rs`:

```rust
// ---------------------------------------------------------------------------
// Admission policy
// ---------------------------------------------------------------------------

/// Incoming packet candidate for admission into an agent's slots.
#[derive(Clone, Debug)]
pub struct PacketCandidate {
    pub info_type: u8,
    pub source_region: u16,
    pub source_turn: u16,
    pub intensity: u8,
    pub hop_count: u8,
}

/// Result of an admission attempt.
#[derive(Debug, PartialEq, Eq)]
pub enum AdmitResult {
    Refreshed,
    Inserted,
    Evicted,
    Dropped,
}

/// Try to admit a packet into the agent's 4 slots.
/// Returns the admission outcome.
pub fn admit_packet(pool: &mut AgentPool, slot: usize, candidate: &PacketCandidate) -> AdmitResult {
    let info_type = candidate.info_type;
    let source_region = candidate.source_region;

    // Step 1: Check for same identity (info_type, source_region)
    for i in 0..agent::PACKET_SLOTS {
        let existing_type = unpack_type(pool.pkt_type_and_hops[slot][i]);
        if existing_type == info_type && pool.pkt_source_region[slot][i] == source_region {
            // Same identity — compare freshness
            let existing_turn = pool.pkt_source_turn[slot][i];
            if candidate.source_turn > existing_turn {
                // Incoming is newer — refresh in place
                pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
                pool.pkt_source_region[slot][i] = source_region;
                pool.pkt_source_turn[slot][i] = candidate.source_turn;
                pool.pkt_intensity[slot][i] = candidate.intensity;
                return AdmitResult::Refreshed;
            } else if candidate.source_turn == existing_turn {
                // Same turn — keep higher intensity; if tied, keep lower hop_count
                let existing_intensity = pool.pkt_intensity[slot][i];
                let existing_hops = unpack_hops(pool.pkt_type_and_hops[slot][i]);
                if candidate.intensity > existing_intensity
                    || (candidate.intensity == existing_intensity && candidate.hop_count < existing_hops)
                {
                    pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
                    pool.pkt_intensity[slot][i] = candidate.intensity;
                    return AdmitResult::Refreshed;
                }
            }
            // Incoming is older or weaker — drop
            return AdmitResult::Dropped;
        }
    }

    // Step 2: Check for empty slot
    for i in 0..agent::PACKET_SLOTS {
        if is_empty_slot(pool.pkt_type_and_hops[slot][i]) {
            pool.pkt_type_and_hops[slot][i] = pack_type_hops(info_type, candidate.hop_count);
            pool.pkt_source_region[slot][i] = source_region;
            pool.pkt_source_turn[slot][i] = candidate.source_turn;
            pool.pkt_intensity[slot][i] = candidate.intensity;
            return AdmitResult::Inserted;
        }
    }

    // Step 3: All slots full — find lowest-ranked incumbent
    let incoming_priority = InfoType::from_u8(info_type)
        .map(|t| t.retention_priority())
        .unwrap_or(0);

    let mut worst_idx: usize = 0;
    let mut worst_turn: u16 = pool.pkt_source_turn[slot][0];
    let mut worst_priority: u8 = InfoType::from_u8(unpack_type(pool.pkt_type_and_hops[slot][0]))
        .map(|t| t.retention_priority())
        .unwrap_or(0);

    for i in 1..agent::PACKET_SLOTS {
        let i_turn = pool.pkt_source_turn[slot][i];
        let i_priority = InfoType::from_u8(unpack_type(pool.pkt_type_and_hops[slot][i]))
            .map(|t| t.retention_priority())
            .unwrap_or(0);

        // Older source_turn = easier to evict
        // Lower retention priority = easier to evict
        // Higher slot_index = easier to evict (tie-break)
        if i_turn < worst_turn
            || (i_turn == worst_turn && i_priority < worst_priority)
            || (i_turn == worst_turn && i_priority == worst_priority && i > worst_idx)
        {
            worst_idx = i;
            worst_turn = i_turn;
            worst_priority = i_priority;
        }
    }

    // Admission guard: incoming must outrank the worst incumbent
    let incoming_outranks = candidate.source_turn > worst_turn
        || (candidate.source_turn == worst_turn && incoming_priority > worst_priority)
        || (candidate.source_turn == worst_turn && incoming_priority == worst_priority);

    if incoming_outranks {
        pool.pkt_type_and_hops[slot][worst_idx] = pack_type_hops(info_type, candidate.hop_count);
        pool.pkt_source_region[slot][worst_idx] = source_region;
        pool.pkt_source_turn[slot][worst_idx] = candidate.source_turn;
        pool.pkt_intensity[slot][worst_idx] = candidate.intensity;
        return AdmitResult::Evicted;
    }

    AdmitResult::Dropped
}
```

- [ ] **Step 2: Write admission tests**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::{admit_packet, AdmitResult, PacketCandidate};

#[test]
fn test_admit_into_empty_slots() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 200, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Inserted);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), 1);
    assert_eq!(pool.pkt_source_region[slot][0], 5);
    assert_eq!(pool.pkt_intensity[slot][0], 200);
}

#[test]
fn test_refresh_same_identity_newer_turn() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert initial
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 150, hop_count: 3,
    });
    // Refresh with newer turn
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 12, intensity: 180, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(pool.pkt_source_turn[slot][0], 12);
    assert_eq!(pool.pkt_intensity[slot][0], 180);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 0);
}

#[test]
fn test_drop_same_identity_older_turn() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 12, intensity: 200, hop_count: 0,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 5, source_turn: 10, intensity: 250, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Dropped);
    assert_eq!(pool.pkt_source_turn[slot][0], 12); // unchanged
}

#[test]
fn test_same_turn_keeps_higher_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 2,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 150, hop_count: 1,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(pool.pkt_intensity[slot][0], 150);
}

#[test]
fn test_same_turn_same_intensity_keeps_lower_hops() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 5,
    });
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 3, source_turn: 10, intensity: 100, hop_count: 2,
    });
    assert_eq!(result, AdmitResult::Refreshed);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 2);
}

#[test]
fn test_evict_stalest_when_full() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Fill all 4 slots with different identities
    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: 1, source_region: i, source_turn: 10 + i, intensity: 200, hop_count: 0,
        });
    }

    // New packet at turn 15 — should evict the stalest (region 0, turn 10)
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 99, source_turn: 15, intensity: 100, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Evicted);
    // Region 0 should be gone
    let has_region_0 = (0..4).any(|i| pool.pkt_source_region[slot][i] == 0);
    assert!(!has_region_0, "stalest packet (region 0) should have been evicted");
}

#[test]
fn test_admission_guard_drops_stale_incoming() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Fill with fresh packets at turn 20
    for i in 0..4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: 1, source_region: i, source_turn: 20, intensity: 200, hop_count: 0,
        });
    }

    // Stale incoming at turn 5 should be dropped
    let result = admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 3, source_region: 99, source_turn: 5, intensity: 250, hop_count: 0,
    });
    assert_eq!(result, AdmitResult::Dropped);
}
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): implement packet admission policy with refresh/fill/evict-if-better"
```

---

## Task 4: Decay Phase

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Implement `decay_packets` in knowledge.rs**

Add to `chronicler-agents/src/knowledge.rs`:

```rust
// ---------------------------------------------------------------------------
// Decay phase
// ---------------------------------------------------------------------------

/// Decay all non-empty packets. Returns the number of packets expired (cleared).
pub fn decay_packets(pool: &mut AgentPool, alive_slots: &[usize]) -> u32 {
    let mut expired = 0u32;
    for &slot in alive_slots {
        for i in 0..agent::PACKET_SLOTS {
            let th = pool.pkt_type_and_hops[slot][i];
            if is_empty_slot(th) {
                continue;
            }
            let info_type = unpack_type(th);
            let rate = decay_rate(info_type);
            let intensity = pool.pkt_intensity[slot][i];
            if intensity <= rate {
                // Expired — clear slot to all-zero
                pool.pkt_type_and_hops[slot][i] = 0;
                pool.pkt_source_region[slot][i] = 0;
                pool.pkt_source_turn[slot][i] = 0;
                pool.pkt_intensity[slot][i] = 0;
                expired += 1;
            } else {
                pool.pkt_intensity[slot][i] = intensity - rate;
            }
        }
    }
    expired
}
```

- [ ] **Step 2: Write decay tests**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::decay_packets;

#[test]
fn test_decay_reduces_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 200, hop_count: 0,
    });

    let expired = decay_packets(&mut pool, &[slot]);
    assert_eq!(expired, 0);
    assert_eq!(pool.pkt_intensity[slot][0], 200 - 15); // threat decay = 15
}

#[test]
fn test_decay_clears_expired_packet() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert with low intensity that will expire on first decay
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 10, hop_count: 0,
    });

    let expired = decay_packets(&mut pool, &[slot]);
    assert_eq!(expired, 1);
    assert!(is_empty_slot(pool.pkt_type_and_hops[slot][0]));
    assert_eq!(pool.pkt_intensity[slot][0], 0);
    assert_eq!(pool.pkt_source_region[slot][0], 0);
    assert_eq!(pool.pkt_source_turn[slot][0], 0);
}

#[test]
fn test_decay_rates_differ_by_type() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    // Insert one of each type
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 1, intensity: 100, hop_count: 0,
    });
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 2, source_region: 1, source_turn: 1, intensity: 100, hop_count: 0,
    });
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: 3, source_region: 2, source_turn: 1, intensity: 100, hop_count: 0,
    });

    decay_packets(&mut pool, &[slot]);

    assert_eq!(pool.pkt_intensity[slot][0], 85);  // 100 - 15 (threat)
    assert_eq!(pool.pkt_intensity[slot][1], 92);  // 100 - 8 (trade)
    assert_eq!(pool.pkt_intensity[slot][2], 95);  // 100 - 5 (religious)
}
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): implement packet decay phase"
```

---

## Task 5: Direct Observation Phase

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Implement `observe_packets` in knowledge.rs**

Add to `chronicler-agents/src/knowledge.rs`:

```rust
// ---------------------------------------------------------------------------
// Direct observation phase
// ---------------------------------------------------------------------------

/// Run direct observation for all alive agents. Each agent checks their
/// current region's state and their arrival flag to produce/refresh packets.
/// Returns (created_count, refreshed_count, created_threat, created_trade, created_religious).
pub fn observe_packets(
    pool: &mut AgentPool,
    regions: &[RegionState],
    alive_slots: &[usize],
    current_turn: u16,
) -> (u32, u32, u32, u32, u32) {
    let mut created = 0u32;
    let mut refreshed = 0u32;
    let mut created_threat = 0u32;
    let mut created_trade = 0u32;
    let mut created_religious = 0u32;

    for &slot in alive_slots {
        let region_idx = pool.regions[slot] as usize;
        if region_idx >= regions.len() {
            continue;
        }
        let region = &regions[region_idx];

        // --- Threat warning ---
        // Use max intensity across all threat triggers (one packet per identity)
        let mut threat_intensity: u8 = 0;
        if region.controller_changed_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_CONTROLLER_CHANGED);
        }
        if region.war_won_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_WAR_WON);
        }
        if region.seceded_this_turn {
            threat_intensity = threat_intensity.max(INTENSITY_SECESSION);
        }
        if threat_intensity > 0 {
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::ThreatWarning as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: threat_intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_threat += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }

        // --- Trade opportunity ---
        // Only merchants who arrived this turn with sufficient margin
        if pool.arrived_this_turn[slot] && region.merchant_route_margin > TRADE_MARGIN_THRESHOLD {
            let scaled = ((region.merchant_route_margin - TRADE_MARGIN_THRESHOLD) / 0.90 * 230.0) as u8;
            let intensity = scaled.max(50).min(230);
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::TradeOpportunity as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_trade += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }

        // --- Religious signal ---
        // Use max intensity across all religious triggers (one packet per identity)
        let mut religious_intensity: u8 = 0;
        if region.persecution_intensity > 0.0 {
            let scaled = (region.persecution_intensity * 200.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(200));
        }
        if region.conversion_rate > CONVERSION_RATE_THRESHOLD {
            let scaled = (region.conversion_rate * 300.0) as u8;
            religious_intensity = religious_intensity.max(scaled.max(40).min(180));
        }
        if region.schism_convert_from != region.schism_convert_to
            && region.schism_convert_from != 255
        {
            religious_intensity = religious_intensity.max(INTENSITY_SCHISM);
        }
        if religious_intensity > 0 {
            let result = admit_packet(pool, slot, &PacketCandidate {
                info_type: InfoType::ReligiousSignal as u8,
                source_region: region.region_id,
                source_turn: current_turn,
                intensity: religious_intensity,
                hop_count: 0,
            });
            match result {
                AdmitResult::Inserted => { created += 1; created_religious += 1; }
                AdmitResult::Refreshed => { refreshed += 1; }
                _ => {}
            }
        }
    }

    (created, refreshed, created_threat, created_trade, created_religious)
}
```

- [ ] **Step 2: Write observation tests**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::observe_packets;

#[test]
fn test_observe_threat_from_controller_change() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_changed_this_turn = true;

    let (created, _, created_threat, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_threat, 1);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), InfoType::ThreatWarning as u8);
    assert_eq!(pool.pkt_intensity[slot][0], 200);
    assert_eq!(pool.pkt_source_turn[slot][0], 5);
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[slot][0]), 0);
}

#[test]
fn test_observe_threat_uses_max_intensity() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].controller_changed_this_turn = true; // 200
    regions[0].war_won_this_turn = true;             // 180
    regions[0].seceded_this_turn = true;             // 150

    observe_packets(&mut pool, &regions, &[slot], 5);
    // Max of (200, 180, 150) = 200
    assert_eq!(pool.pkt_intensity[slot][0], 200);
}

#[test]
fn test_observe_trade_requires_arrival_and_margin() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.5;

    // No arrival flag — should not emit
    let (created, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);

    // Set arrival flag
    pool.arrived_this_turn[slot] = true;
    let (created, _, _, created_trade, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_trade, 1);
}

#[test]
fn test_observe_trade_below_margin_threshold_no_packet() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[slot] = true;

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.05; // below 0.10 threshold

    let (created, _, _, _, _) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 0);
}

#[test]
fn test_observe_religious_from_persecution() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions = vec![RegionState::new(0)];
    regions[0].persecution_intensity = 0.5;

    let (created, _, _, _, created_religious) = observe_packets(&mut pool, &regions, &[slot], 5);
    assert_eq!(created, 1);
    assert_eq!(created_religious, 1);
    assert_eq!(unpack_type(pool.pkt_type_and_hops[slot][0]), InfoType::ReligiousSignal as u8);
}
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): implement direct observation phase for threat/trade/religious packets"
```

---

## Task 6: Propagation Phase (Buffered)

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Implement propagation in knowledge.rs**

Add to `chronicler-agents/src/knowledge.rs` (add `use rand::Rng; use rand::SeedableRng; use rand_chacha::ChaCha8Rng;` at the top):

```rust
// ---------------------------------------------------------------------------
// Propagation phase (buffered)
// ---------------------------------------------------------------------------

/// A buffered packet received during propagation, pending commit.
#[derive(Clone, Debug)]
struct BufferedReceive {
    receiver_slot: usize,
    candidate: PacketCandidate,
}

/// Run propagation: each agent tries to share non-empty packets with bonded agents.
/// Uses the post-observation snapshot. Returns (transmitted_count, transmitted_by_type).
///
/// `slot_lookup` maps agent_id -> slot index for relationship target resolution.
pub fn propagate_packets(
    pool: &AgentPool,
    alive_slots: &[usize],
    master_seed: &[u8; 32],
    current_turn: u32,
    slot_lookup: &std::collections::HashMap<u32, usize>,
) -> (Vec<BufferedReceive>, u32, u32, u32, u32) {
    let mut buffer: Vec<BufferedReceive> = Vec::new();
    let mut transmitted = 0u32;
    let mut transmitted_threat = 0u32;
    let mut transmitted_trade = 0u32;
    let mut transmitted_religious = 0u32;

    for &sender_slot in alive_slots {
        let rel_count = pool.rel_count[sender_slot] as usize;
        if rel_count == 0 {
            continue;
        }

        for pkt_idx in 0..agent::PACKET_SLOTS {
            let th = pool.pkt_type_and_hops[sender_slot][pkt_idx];
            if is_empty_slot(th) {
                continue;
            }
            let info_type = unpack_type(th);
            let hop_count = unpack_hops(th);

            // hop_count = 31 halts propagation
            if hop_count >= agent::MAX_HOP_COUNT {
                continue;
            }

            let source_region = pool.pkt_source_region[sender_slot][pkt_idx];
            let source_turn = pool.pkt_source_turn[sender_slot][pkt_idx];
            let sender_intensity = pool.pkt_intensity[sender_slot][pkt_idx];

            // Collect unique receivers with their best eligible bond
            // Key: receiver_slot, Value: (effective_chance, channel_weight, sentiment, bond_type)
            let mut best_per_receiver: std::collections::HashMap<usize, (f32, f32, i8, u8)> =
                std::collections::HashMap::new();

            for rel_idx in 0..rel_count {
                let target_id = pool.rel_target_ids[sender_slot][rel_idx];
                let bond_type = pool.rel_bond_types[sender_slot][rel_idx];
                let sentiment = pool.rel_sentiments[sender_slot][rel_idx];

                if bond_type == crate::relationships::EMPTY_BOND_TYPE {
                    continue;
                }

                // Check channel eligibility
                let weight = match channel_weight(bond_type, info_type) {
                    Some(w) => w,
                    None => continue,
                };

                // Resolve receiver slot
                let receiver_slot = match slot_lookup.get(&target_id) {
                    Some(&s) if pool.is_alive(s) => s,
                    _ => continue,
                };

                let sentiment_factor = (sentiment.max(0) as f32) / 127.0;
                let chance = base_rate(info_type) * weight * sentiment_factor;

                // Multi-bond resolution: keep the bond with highest effective chance
                // Tie-break: higher channel_weight > higher positive sentiment > lower bond_type ordinal
                let entry = best_per_receiver.entry(receiver_slot).or_insert((0.0, 0.0, 0, 255));
                if chance > entry.0
                    || (chance == entry.0 && weight > entry.1)
                    || (chance == entry.0 && weight == entry.1 && sentiment > entry.2)
                    || (chance == entry.0 && weight == entry.1 && sentiment == entry.2 && bond_type < entry.3)
                {
                    *entry = (chance, weight, sentiment, bond_type);
                }
            }

            // Roll for each unique receiver
            for (&receiver_slot, &(chance, _, _, _)) in &best_per_receiver {
                if chance <= 0.0 {
                    continue;
                }

                let sender_id = pool.ids[sender_slot];
                let receiver_id = pool.ids[receiver_slot];

                // Deterministic keyed RNG on stream 1800
                let mut key_seed = *master_seed;
                // Mix the key components into the seed
                let key_hash = {
                    let mut h: u64 = sender_id as u64;
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(receiver_id as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(info_type as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_region as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(source_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(current_turn as u64);
                    h = h.wrapping_mul(6364136223846793005).wrapping_add(agent::KNOWLEDGE_STREAM_OFFSET);
                    h
                };
                // XOR the key hash into the first 8 bytes of the seed
                let hash_bytes = key_hash.to_le_bytes();
                for i in 0..8 {
                    key_seed[i] ^= hash_bytes[i];
                }
                let mut rng = ChaCha8Rng::from_seed(key_seed);
                let roll: f32 = rng.gen();

                if roll < chance {
                    let received_intensity = (sender_intensity as f32 * HOP_ATTENUATION) as u8;
                    if received_intensity == 0 {
                        continue;
                    }
                    buffer.push(BufferedReceive {
                        receiver_slot,
                        candidate: PacketCandidate {
                            info_type,
                            source_region,
                            source_turn,
                            intensity: received_intensity,
                            hop_count: hop_count + 1,
                        },
                    });
                    transmitted += 1;
                    match info_type {
                        1 => transmitted_threat += 1,
                        2 => transmitted_trade += 1,
                        3 => transmitted_religious += 1,
                        _ => {}
                    }
                }
            }
        }
    }

    (buffer, transmitted, transmitted_threat, transmitted_trade, transmitted_religious)
}

// ---------------------------------------------------------------------------
// Commit phase
// ---------------------------------------------------------------------------

/// Dedupe and commit buffered receives. Returns (refreshed, evicted, dropped).
pub fn commit_buffered(
    pool: &mut AgentPool,
    mut buffer: Vec<BufferedReceive>,
) -> (u32, u32, u32) {
    let mut refreshed = 0u32;
    let mut evicted = 0u32;
    let mut dropped = 0u32;

    if buffer.is_empty() {
        return (refreshed, evicted, dropped);
    }

    // Intra-turn merge: dedupe by (receiver_slot, info_type, source_region)
    // Keep: newest source_turn > highest intensity > lowest hop_count
    // Then sort canonically for thread-stable admission order.

    // Sort by (receiver_slot, info_type, source_region, source_turn DESC, intensity DESC, hop_count ASC)
    buffer.sort_by(|a, b| {
        a.receiver_slot.cmp(&b.receiver_slot)
            .then(a.candidate.info_type.cmp(&b.candidate.info_type))
            .then(a.candidate.source_region.cmp(&b.candidate.source_region))
            .then(b.candidate.source_turn.cmp(&a.candidate.source_turn))
            .then(b.candidate.intensity.cmp(&a.candidate.intensity))
            .then(a.candidate.hop_count.cmp(&b.candidate.hop_count))
    });

    // Dedupe: keep first in each (receiver_slot, info_type, source_region) group
    buffer.dedup_by(|b, a| {
        a.receiver_slot == b.receiver_slot
            && a.candidate.info_type == b.candidate.info_type
            && a.candidate.source_region == b.candidate.source_region
    });

    // Apply admission
    for receive in &buffer {
        let result = admit_packet(pool, receive.receiver_slot, &receive.candidate);
        match result {
            AdmitResult::Refreshed => refreshed += 1,
            AdmitResult::Evicted => evicted += 1,
            AdmitResult::Dropped => dropped += 1,
            AdmitResult::Inserted => {} // new slot fill from propagation — not a refresh or eviction
        }
    }

    (refreshed, evicted, dropped)
}
```

- [ ] **Step 2: Write propagation tests**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::{propagate_packets, commit_buffered};
use chronicler_agents::relationships;

/// Helper: set up a relationship bond between two agents.
fn set_bond(pool: &mut AgentPool, from_slot: usize, to_id: u32, bond_type: u8, sentiment: i8) {
    let idx = pool.rel_count[from_slot] as usize;
    pool.rel_target_ids[from_slot][idx] = to_id;
    pool.rel_bond_types[from_slot][idx] = bond_type;
    pool.rel_sentiments[from_slot][idx] = sentiment;
    pool.rel_formed_turns[from_slot][idx] = 0;
    pool.rel_count[from_slot] += 1;
}

#[test]
fn test_propagation_one_hop() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    // Give A a threat warning
    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    // A -> B: Kin bond with max sentiment (guarantees propagation)
    set_bond(&mut pool, a, b_id, 5, 127); // Kin

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (buffer, transmitted, t_threat, _, _) =
        propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);

    assert!(transmitted > 0, "should have transmitted at least one packet");
    assert!(t_threat > 0, "should have transmitted a threat packet");

    // Commit buffer
    commit_buffered(&mut pool, buffer);

    // B should now have the threat packet with hop_count = 1
    let b_has_threat = (0..4).any(|i| {
        unpack_type(pool.pkt_type_and_hops[b][i]) == 1
            && pool.pkt_source_region[b][i] == 0
            && unpack_hops(pool.pkt_type_and_hops[b][i]) == 1
    });
    assert!(b_has_threat, "B should have received threat packet with hop=1");
}

#[test]
fn test_propagation_one_hop_per_turn() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];
    let c_id = pool.ids[c];

    // Give A a threat warning
    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    // Chain: A -> B -> C (Kin bonds, max sentiment)
    set_bond(&mut pool, a, b_id, 5, 127);
    set_bond(&mut pool, b, c_id, 5, 127);

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b), (c_id, c)].into_iter().collect();

    // Turn 1: propagate from snapshot (B has no packet yet)
    let (buffer, _, _, _, _) = propagate_packets(&pool, &[a, b, c], &[0u8; 32], 6, &lookup);
    commit_buffered(&mut pool, buffer);

    // B should have the packet, but C should NOT (one-hop-per-turn)
    let b_has = (0..4).any(|i| unpack_type(pool.pkt_type_and_hops[b][i]) == 1);
    let c_has = (0..4).any(|i| unpack_type(pool.pkt_type_and_hops[c][i]) == 1);
    assert!(b_has, "B should have the packet after turn 1");
    assert!(!c_has, "C should NOT have the packet after turn 1 (one-hop-per-turn)");
}

#[test]
fn test_hop_count_31_halts_propagation() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    // Give A a packet at max hops
    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 31,
    });

    set_bond(&mut pool, a, b_id, 5, 127);

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (buffer, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);
    assert_eq!(transmitted, 0, "should not transmit at max hops");
    assert!(buffer.is_empty());
}

#[test]
fn test_propagation_channel_filtering() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];

    // Give A a religious signal
    admit_packet(&mut pool, a, &PacketCandidate {
        info_type: 3, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
    });

    // A -> B: Friend bond (not eligible for religious)
    set_bond(&mut pool, a, b_id, 6, 127); // Friend

    let lookup: std::collections::HashMap<u32, usize> =
        vec![(a_id, a), (b_id, b)].into_iter().collect();

    let (_, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &[0u8; 32], 6, &lookup);
    assert_eq!(transmitted, 0, "Friend bond should not carry religious signal");
}
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): implement buffered propagation and commit phases"
```

---

## Task 7: Knowledge Phase Orchestrator + Live Stats

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Implement `knowledge_phase` orchestrator**

Add to `chronicler-agents/src/knowledge.rs`:

```rust
// ---------------------------------------------------------------------------
// Knowledge phase orchestrator (tick phase 0.95)
// ---------------------------------------------------------------------------

/// Run the full knowledge phase: decay → observe → propagate → commit → stats.
/// Clears `arrived_this_turn` as the last operation.
pub fn knowledge_phase(
    pool: &mut AgentPool,
    regions: &[RegionState],
    master_seed: &[u8; 32],
    turn: u32,
) -> KnowledgeStats {
    let mut stats = KnowledgeStats::default();
    let current_turn = turn as u16;

    // Collect alive slots
    let alive_slots: Vec<usize> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .collect();

    if alive_slots.is_empty() {
        return stats;
    }

    // Step 1: Decay + expire
    stats.packets_expired = decay_packets(pool, &alive_slots);

    // Step 2: Direct observation
    let (created, refreshed_obs, ct, ctr, cr) =
        observe_packets(pool, regions, &alive_slots, current_turn);
    stats.packets_created = created;
    stats.packets_refreshed = refreshed_obs;
    stats.created_threat = ct;
    stats.created_trade = ctr;
    stats.created_religious = cr;

    // Step 3: Propagation (buffered, reads post-observation snapshot)
    // Build slot lookup for relationship target resolution
    let slot_lookup: std::collections::HashMap<u32, usize> = alive_slots
        .iter()
        .map(|&s| (pool.ids[s], s))
        .collect();

    let (buffer, transmitted, tt, ttr, tr) =
        propagate_packets(pool, &alive_slots, master_seed, turn, &slot_lookup);
    stats.packets_transmitted = transmitted;
    stats.transmitted_threat = tt;
    stats.transmitted_trade = ttr;
    stats.transmitted_religious = tr;

    // Step 4: Commit buffered receives
    let (commit_refreshed, evicted, dropped) = commit_buffered(pool, buffer);
    stats.packets_refreshed += commit_refreshed;
    stats.packets_evicted = evicted;
    stats.packets_dropped = dropped;

    // Step 5: Compute post-commit live stats
    let mut total_age: u64 = 0;
    let mut total_hops: u64 = 0;
    let mut max_age: u32 = 0;
    let mut max_hops: u32 = 0;
    let mut live_count: u32 = 0;
    let mut agents_with: u32 = 0;

    for &slot in &alive_slots {
        let mut has_packet = false;
        for i in 0..agent::PACKET_SLOTS {
            if !is_empty_slot(pool.pkt_type_and_hops[slot][i]) {
                has_packet = true;
                live_count += 1;
                let age = current_turn.saturating_sub(pool.pkt_source_turn[slot][i]) as u32;
                let hops = unpack_hops(pool.pkt_type_and_hops[slot][i]) as u32;
                total_age += age as u64;
                total_hops += hops as u64;
                if age > max_age { max_age = age; }
                if hops > max_hops { max_hops = hops; }
            }
        }
        if has_packet {
            agents_with += 1;
        }
    }

    stats.live_packet_count = live_count;
    stats.agents_with_packets = agents_with;
    stats.max_age = max_age;
    stats.max_hops = max_hops;
    if live_count > 0 {
        stats.mean_age = total_age as f32 / live_count as f32;
        stats.mean_hops = total_hops as f32 / live_count as f32;
    }

    // Clear arrival flags
    for &slot in &alive_slots {
        pool.arrived_this_turn[slot] = false;
    }

    stats
}
```

- [ ] **Step 2: Write orchestrator test**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::knowledge_phase;

#[test]
fn test_knowledge_phase_full_cycle() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let b_id = pool.ids[b];

    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_changed_this_turn = true;

    // A -> B: Kin bond
    set_bond(&mut pool, a, b_id, 5, 127);

    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert!(stats.packets_created > 0, "should have created packets");
    assert!(stats.live_packet_count > 0, "should have live packets");
    assert!(stats.agents_with_packets > 0, "should have agents with packets");
}

#[test]
fn test_knowledge_phase_clears_arrival_flag() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[a] = true;

    let regions = vec![RegionState::new(0)];
    knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert!(!pool.arrived_this_turn[a], "arrived_this_turn should be cleared after knowledge phase");
}

#[test]
fn test_knowledge_phase_zero_fill_no_packets() {
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let regions = vec![RegionState::new(0)];
    // No triggers — no packets
    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 5);

    assert_eq!(stats.live_packet_count, 0);
    assert_eq!(stats.agents_with_packets, 0);
    assert_eq!(stats.mean_age, 0.0);
    assert_eq!(stats.max_age, 0);
}
```

- [ ] **Step 3: Run tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59a): implement knowledge phase orchestrator with live stats"
```

---

## Task 8: Wire Into Tick + Merchant Arrival Flag

**Files:**
- Modify: `chronicler-agents/src/tick.rs:107-133`
- Modify: `chronicler-agents/src/merchant.rs:658-675`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Set `arrived_this_turn` in merchant arrival code**

In `chronicler-agents/src/merchant.rs`, in the `merchant_mobility_phase` function, in the arrivals loop (around line 665-674), after `ledger.arrive(...)` (line 670) and before `reset_trip_fields(pool, slot);` (line 674), add:

```rust
        pool.arrived_this_turn[slot] = true;
```

- [ ] **Step 2: Add KnowledgeStats to tick_agents return type**

In `chronicler-agents/src/tick.rs`, change the return type of `tick_agents` (line 56) from:

```rust
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug, crate::household::HouseholdStats, crate::merchant::MerchantTripStats) {
```

to:

```rust
) -> (Vec<AgentEvent>, u32, crate::formation::FormationStats, DemographicDebug, crate::household::HouseholdStats, crate::merchant::MerchantTripStats, crate::knowledge::KnowledgeStats) {
```

- [ ] **Step 3: Insert knowledge phase call at 0.95**

In `chronicler-agents/src/tick.rs`, after the merchant_stats line (line 128, `merchant_stats.unwind_count += conquest_unwind_count;`) and before the satisfaction section (line 130, `// 1. Update satisfaction`), add:

```rust
    // -----------------------------------------------------------------------
    // 0.95 Knowledge phase — packet decay, observation, propagation (M59a)
    // -----------------------------------------------------------------------
    let knowledge_stats = crate::knowledge::knowledge_phase(pool, regions, &master_seed, turn);
```

- [ ] **Step 4: Add knowledge_stats to the return tuple**

In `chronicler-agents/src/tick.rs`, at the return statement (line 920), change from:

```rust
    (events, kin_bond_failures, formation_stats, demo_debug, household_stats, merchant_stats)
```

to:

```rust
    (events, kin_bond_failures, formation_stats, demo_debug, household_stats, merchant_stats, knowledge_stats)
```

- [ ] **Step 5: Update ffi.rs to destructure the new return tuple**

In `chronicler-agents/src/ffi.rs`, at the `tick_agents` call site (line 2349), change from:

```rust
        let (events, kin_failures, formation_stats, demo_debug, household_stats, merchant_stats) = crate::tick::tick_agents(
```

to:

```rust
        let (events, kin_failures, formation_stats, demo_debug, household_stats, merchant_stats, knowledge_stats) = crate::tick::tick_agents(
```

And after `self.merchant_trip_stats = merchant_stats;` (line 2374), add:

```rust
        self.knowledge_stats = knowledge_stats;
```

- [ ] **Step 6: Add `knowledge_stats` field to `AgentSimulator` struct in ffi.rs**

Find the `AgentSimulator` struct fields (search for `merchant_trip_stats: crate::merchant::MerchantTripStats`). After it, add:

```rust
    knowledge_stats: crate::knowledge::KnowledgeStats,
```

And in the `AgentSimulator::new()` constructor, after `merchant_trip_stats: Default::default(),`, add:

```rust
            knowledge_stats: Default::default(),
```

- [ ] **Step 7: Update lib.rs re-exports**

In `chronicler-agents/src/lib.rs`, after the existing `tick_agents` re-export line (line 68), the return type references are already satisfied since `KnowledgeStats` is part of the tuple. No additional re-export needed unless integration tests reference `KnowledgeStats` directly. Add for test access:

```rust
#[doc(hidden)]
pub use knowledge::{InfoType, KnowledgeStats, knowledge_phase, pack_type_hops, unpack_type, unpack_hops, is_empty_slot};
#[doc(hidden)]
pub use knowledge::{channel_weight, decay_rate, base_rate, admit_packet, AdmitResult, PacketCandidate};
#[doc(hidden)]
pub use knowledge::{observe_packets, propagate_packets, commit_buffered, decay_packets};
```

- [ ] **Step 8: Run cargo check to verify compilation**

Run: `cd chronicler-agents && cargo check`
Expected: No errors

- [ ] **Step 9: Run all existing tests to verify no regressions**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All existing tests PASS (no regressions from return type change)

- [ ] **Step 10: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/merchant.rs chronicler-agents/src/ffi.rs chronicler-agents/src/lib.rs
git commit -m "feat(m59a): wire knowledge phase into tick at 0.95, set merchant arrival flag"
```

---

## Task 9: FFI Diagnostics — get_knowledge_stats()

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Add `get_knowledge_stats()` method to AgentSimulator**

In `chronicler-agents/src/ffi.rs`, in the `#[pymethods]` impl block, after the `get_merchant_trip_stats` method (find it by searching for `fn get_merchant_trip_stats`), add:

Note: the spec says `KnowledgeStats` struct crosses FFI. The Rust side stores it as a `KnowledgeStats` struct (Task 8). The PyO3 getter converts to `HashMap<String, f64>` for Python consumption, matching the established pattern used by `get_relationship_stats()`, `get_household_stats()`, and `get_merchant_trip_stats()`. This is the spec's intended "flat fixed-width struct through FFI → Python builds per-type dicts" transport path.

```rust
    /// M59a: Return knowledge stats from last tick as a flat HashMap.
    /// Rust-side KnowledgeStats struct converted to Python dict, matching
    /// the established pattern from relationship/household/merchant stats.
    #[pyo3(name = "get_knowledge_stats")]
    pub fn get_knowledge_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("packets_created".into(), self.knowledge_stats.packets_created as f64);
        stats.insert("packets_refreshed".into(), self.knowledge_stats.packets_refreshed as f64);
        stats.insert("packets_transmitted".into(), self.knowledge_stats.packets_transmitted as f64);
        stats.insert("packets_expired".into(), self.knowledge_stats.packets_expired as f64);
        stats.insert("packets_evicted".into(), self.knowledge_stats.packets_evicted as f64);
        stats.insert("packets_dropped".into(), self.knowledge_stats.packets_dropped as f64);
        stats.insert("live_packet_count".into(), self.knowledge_stats.live_packet_count as f64);
        stats.insert("agents_with_packets".into(), self.knowledge_stats.agents_with_packets as f64);
        stats.insert("created_threat".into(), self.knowledge_stats.created_threat as f64);
        stats.insert("created_trade".into(), self.knowledge_stats.created_trade as f64);
        stats.insert("created_religious".into(), self.knowledge_stats.created_religious as f64);
        stats.insert("transmitted_threat".into(), self.knowledge_stats.transmitted_threat as f64);
        stats.insert("transmitted_trade".into(), self.knowledge_stats.transmitted_trade as f64);
        stats.insert("transmitted_religious".into(), self.knowledge_stats.transmitted_religious as f64);
        stats.insert("mean_age".into(), self.knowledge_stats.mean_age as f64);
        stats.insert("max_age".into(), self.knowledge_stats.max_age as f64);
        stats.insert("mean_hops".into(), self.knowledge_stats.mean_hops as f64);
        stats.insert("max_hops".into(), self.knowledge_stats.max_hops as f64);
        Ok(stats)
    }
```

- [ ] **Step 2: Run cargo check**

Run: `cd chronicler-agents && cargo check`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m59a): expose get_knowledge_stats() via PyO3 FFI"
```

---

## Task 10: Python Bridge — Collect knowledge_stats

**Files:**
- Modify: `src/chronicler/agent_bridge.py:730-870`
- Test: `tests/test_m59a_knowledge.py`

- [ ] **Step 1: Add knowledge_stats collection to agent_bridge.py**

In `src/chronicler/agent_bridge.py`, in the `__init__` method, after `self._merchant_trip_stats_history: list = []` (line 775), add:

```python
        # M59a: Knowledge stats collection (always in agent modes)
        self._knowledge_stats_history: list = []
```

In the tick method, after the merchant trip stats collection block (after line 870), add:

```python
        # M59a: knowledge stats collection
        try:
            k_stats = self._sim.get_knowledge_stats()
            self._knowledge_stats_history.append(k_stats)
        except Exception:
            logger.exception("Failed to collect knowledge stats from Rust tick")
```

Add a property accessor, after `merchant_trip_stats` property (line 1042-1044):

```python
    @property
    def knowledge_stats(self) -> list:
        """M59a: Per-tick knowledge stats history."""
        return self._knowledge_stats_history
```

In the `reset` method (around line 2085-2086), add after `self._household_stats_history.clear()`:

```python
        self._knowledge_stats_history.clear()
```

- [ ] **Step 2: Write failing Python test**

Create `tests/test_m59a_knowledge.py`:

```python
"""M59a: Knowledge stats integration tests."""
import argparse
import json
import subprocess
import sys

import pytest


def test_knowledge_stats_property_exists():
    """Verify the knowledge_stats property exists on AgentBridge."""
    from chronicler.agent_bridge import AgentBridge
    assert hasattr(AgentBridge, "knowledge_stats"), "AgentBridge should have knowledge_stats property"
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_m59a_knowledge.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_m59a_knowledge.py
git commit -m "feat(m59a): collect knowledge_stats in agent_bridge after tick"
```

---

## Task 11: Python Bridge — Bundle Metadata + Analytics Extractor

**Files:**
- Modify: `src/chronicler/main.py:746-762`
- Modify: `src/chronicler/analytics.py`
- Test: `tests/test_m59a_knowledge.py`

- [ ] **Step 1: Append knowledge_stats to bundle metadata in main.py**

In `src/chronicler/main.py`, after the merchant trip stats metadata block (after line 762, `bundle["metadata"]["merchant_trip_stats"] = m_trip_stats`), add:

```python
    # M59a: knowledge stats metadata
    if agent_bridge is not None:
        k_stats = getattr(agent_bridge, "knowledge_stats", [])
        if not isinstance(k_stats, list):
            k_stats = []
        bundle["metadata"]["knowledge_stats"] = k_stats
```

- [ ] **Step 2: Add analytics extractor**

In `src/chronicler/analytics.py`, after the `extract_merchant_trip_stats` function (after line 1962), add:

```python
def extract_knowledge_stats(bundles: list[dict]) -> dict:
    """M59a: Per-seed knowledge stats time series.

    Returns ``{'by_seed': {seed: [per-turn-dict, ...]}}``.
    """
    by_seed: dict[int, list] = {}
    for b in bundles:
        seed = b.get("metadata", {}).get("seed", 0)
        stats = b.get("metadata", {}).get("knowledge_stats", [])
        by_seed[seed] = stats
    return {"by_seed": by_seed}
```

- [ ] **Step 3: Write test for metadata integration**

Append to `tests/test_m59a_knowledge.py`:

```python
def test_extract_knowledge_stats_empty():
    """Verify extractor handles bundles with no knowledge_stats."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{"metadata": {"seed": 42}}]
    result = extract_knowledge_stats(bundles)
    assert result == {"by_seed": {42: []}}


def test_extract_knowledge_stats_with_data():
    """Verify extractor routes per-turn stats by seed."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{
        "metadata": {
            "seed": 42,
            "knowledge_stats": [
                {"packets_created": 5, "live_packet_count": 3},
                {"packets_created": 2, "live_packet_count": 4},
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    assert len(result["by_seed"][42]) == 2
    assert result["by_seed"][42][0]["packets_created"] == 5
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_m59a_knowledge.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py src/chronicler/analytics.py tests/test_m59a_knowledge.py
git commit -m "feat(m59a): wire knowledge_stats into bundle metadata and analytics extractor"
```

---

## Task 12: Determinism + Compatibility Tests

**Files:**
- Test: `chronicler-agents/tests/test_knowledge.rs`
- Test: `tests/test_m59a_knowledge.py`

- [ ] **Step 1: Add same-process determinism test to Rust**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_knowledge_phase_deterministic_same_process() {
    // Run the same setup twice with the same seed — results must match
    let seed = [42u8; 32];

    let run = || {
        let mut pool = AgentPool::new(10);
        let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let b_id = pool.ids[b];
        let c_id = pool.ids[c];

        set_bond(&mut pool, a, b_id, 5, 100); // Kin
        set_bond(&mut pool, b, c_id, 6, 80);  // Friend

        let mut regions = vec![RegionState::new(0), RegionState::new(1), RegionState::new(2)];
        regions[0].controller_changed_this_turn = true;
        regions[0].persecution_intensity = 0.5;

        // Turn 1
        let stats1 = knowledge_phase(&mut pool, &regions, &seed, 1);
        // Turn 2
        regions[0].controller_changed_this_turn = false;
        let stats2 = knowledge_phase(&mut pool, &regions, &seed, 2);

        (stats1, stats2, pool.pkt_type_and_hops.clone(), pool.pkt_intensity.clone())
    };

    let (s1a, s2a, th_a, int_a) = run();
    let (s1b, s2b, th_b, int_b) = run();

    assert_eq!(s1a.packets_created, s1b.packets_created);
    assert_eq!(s1a.packets_transmitted, s1b.packets_transmitted);
    assert_eq!(s2a.packets_transmitted, s2b.packets_transmitted);
    assert_eq!(th_a, th_b, "packet state should be identical across runs");
    assert_eq!(int_a, int_b, "intensity state should be identical across runs");
}
```

- [ ] **Step 2: Add cross-process determinism test via Python**

Append to `tests/test_m59a_knowledge.py`:

```python
def test_knowledge_deterministic_cross_process(tmp_path):
    """Cross-process determinism: same seed in two separate processes must
    produce identical knowledge_stats.

    This catches process-local nondeterminism (uninitialized memory, HashMap
    iteration order, thread scheduling) that same-process reruns miss.
    """
    from chronicler.main import execute_run

    bundles = []
    for run_idx in range(2):
        run_dir = tmp_path / f"det_run_{run_idx}"
        run_dir.mkdir()
        # Run in a subprocess to get true process isolation
        script = (
            f"import argparse, json; "
            f"from chronicler.main import execute_run; "
            f"args = argparse.Namespace("
            f"  seed=77, turns=8, civs=2, regions=5,"
            f"  output=r'{run_dir / 'chronicle.md'}',"
            f"  state=r'{run_dir / 'state.json'}',"
            f"  resume=None, reflection_interval=10,"
            f"  llm_actions=False, scenario=None, pause_every=None,"
            f"  agents='hybrid', narrator='off', agent_narrative=False,"
            f"  relationship_stats=False, live=False,"
            f"  shadow_output=None, validation_sidecar=False,"
            f"); "
            f"execute_run(args)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, (
            f"Run {run_idx} failed: {result.stderr[-500:]}"
        )
        bundle_path = run_dir / "chronicle_bundle.json"
        assert bundle_path.exists(), f"Run {run_idx} produced no bundle"
        bundles.append(json.loads(bundle_path.read_text()))

    k0 = bundles[0].get("metadata", {}).get("knowledge_stats", [])
    k1 = bundles[1].get("metadata", {}).get("knowledge_stats", [])
    assert len(k0) > 0, "knowledge_stats should be non-empty in hybrid mode"
    assert k0 == k1, "knowledge_stats diverged across processes"
```

- [ ] **Step 2: Add slot-order independence test**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_propagation_independent_of_rel_slot_order() {
    // Agent A has two bonds to B: Kin at slot 0, Friend at slot 1.
    // Swap the slot order. Result should be the same (best bond wins).
    let seed = [99u8; 32];

    let run = |first_bond: u8, second_bond: u8| {
        let mut pool = AgentPool::new(10);
        let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let b_id = pool.ids[b];

        admit_packet(&mut pool, a, &PacketCandidate {
            info_type: 1, source_region: 0, source_turn: 5, intensity: 200, hop_count: 0,
        });

        set_bond(&mut pool, a, b_id, first_bond, 100);
        set_bond(&mut pool, a, b_id, second_bond, 100);

        let lookup: std::collections::HashMap<u32, usize> =
            vec![(pool.ids[a], a), (pool.ids[b], b)].into_iter().collect();

        let (buffer, transmitted, _, _, _) = propagate_packets(&pool, &[a, b], &seed, 6, &lookup);
        (transmitted, buffer.len())
    };

    let (t1, b1) = run(5, 6); // Kin first, Friend second
    let (t2, b2) = run(6, 5); // Friend first, Kin second
    assert_eq!(t1, t2, "transmitted count should be independent of slot order");
    assert_eq!(b1, b2, "buffer size should be independent of slot order");
}
```

- [ ] **Step 3: Run all Rust tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/test_knowledge.rs
git commit -m "test(m59a): add determinism and slot-order independence tests"
```

---

## Task 13: Rebuild Rust Extension + Full Test Suite

**Files:**
- No new files — validation only

- [ ] **Step 1: Rebuild the Rust extension**

Run: `cd chronicler-agents && maturin develop --release`
Expected: Build succeeds. Use `.venv\\Scripts\\python.exe` to verify the correct venv picks up the rebuilt extension.

- [ ] **Step 2: Run full Rust test suite**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All tests PASS (no regressions)

- [ ] **Step 3: Run full Python test suite**

Run: `pytest tests/ -q`
Expected: All tests PASS (no regressions)

- [ ] **Step 4: Commit if any fixups were needed**

Only if fixes were required. Otherwise skip.

---

## Task 14: Compatibility + Behavioral Inertia Regression Tests

**Files:**
- Test: `tests/test_m59a_knowledge.py`

- [ ] **Step 1: Write `--agents=off` compatibility test**

Append to `tests/test_m59a_knowledge.py`:

```python
def _make_args(tmp_path, seed=42, turns=5, agents="off"):
    """Build an args namespace matching execute_run's expected shape."""
    return argparse.Namespace(
        seed=seed,
        turns=turns,
        civs=2,
        regions=5,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None,
        reflection_interval=10,
        llm_actions=False,
        scenario=None,
        pause_every=None,
        agents=agents,
        narrator="off",
        agent_narrative=False,
        relationship_stats=False,
        live=False,
        shadow_output=None,
        validation_sidecar=False,
    )


def test_agents_off_no_knowledge_stats(tmp_path):
    """--agents=off should produce no knowledge_stats in bundle metadata."""
    from chronicler.main import execute_run

    args = _make_args(tmp_path, agents="off")
    execute_run(args)

    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists(), "execute_run should produce a bundle"
    bundle = json.loads(bundle_path.read_text())
    metadata = bundle.get("metadata", {})
    k_stats = metadata.get("knowledge_stats", [])
    assert k_stats == [] or "knowledge_stats" not in metadata
```

- [ ] **Step 2: Write behavioral inertia regression test (Rust level)**

The approved spec requires verifying that M59a is producer-only: the knowledge phase must not modify any non-packet pool fields. This is tested at the Rust level by snapshotting all decision-relevant fields before and after `knowledge_phase`, and asserting they are unchanged.

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_knowledge_phase_does_not_modify_non_packet_fields() {
    // Verify producer-only property: knowledge_phase must not touch any
    // pool field that feeds into existing systems (satisfaction, decisions,
    // demographics, merchant routing, relationships, needs, wealth, etc.)
    let seed = [42u8; 32];
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[b] = true; // will be cleared by knowledge phase

    let b_id = pool.ids[b];
    set_bond(&mut pool, a, b_id, 5, 100);

    // Set some non-default field values to ensure they survive
    pool.satisfactions[a] = 0.75;
    pool.loyalties[a] = 0.6;
    pool.wealth[a] = 50.0;
    pool.need_safety[a] = 0.8;

    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[0].controller_changed_this_turn = true;
    regions[0].persecution_intensity = 0.5;
    regions[1].merchant_route_margin = 0.5;

    // Snapshot all non-packet fields before knowledge_phase
    let sat_before = pool.satisfactions.clone();
    let loy_before = pool.loyalties.clone();
    let wealth_before = pool.wealth.clone();
    let occ_before = pool.occupations.clone();
    let regions_before = pool.regions.clone();
    let civ_before = pool.civ_affinities.clone();
    let ages_before = pool.ages.clone();
    let needs_before = (
        pool.need_safety.clone(), pool.need_material.clone(),
        pool.need_social.clone(), pool.need_spiritual.clone(),
        pool.need_autonomy.clone(), pool.need_purpose.clone(),
    );
    let rel_targets_before = pool.rel_target_ids.clone();
    let rel_sentiments_before = pool.rel_sentiments.clone();
    let rel_bonds_before = pool.rel_bond_types.clone();
    let trip_phase_before = pool.trip_phase.clone();
    let alive_before = pool.alive.clone();

    // Run knowledge phase (should create/propagate packets but touch nothing else)
    let stats = knowledge_phase(&mut pool, &regions, &seed, 5);

    // Verify packets were actually created (not a vacuous test)
    assert!(stats.packets_created > 0, "knowledge_phase should have created packets");

    // Verify ALL non-packet fields are unchanged
    assert_eq!(pool.satisfactions, sat_before, "satisfactions modified");
    assert_eq!(pool.loyalties, loy_before, "loyalties modified");
    assert_eq!(pool.wealth, wealth_before, "wealth modified");
    assert_eq!(pool.occupations, occ_before, "occupations modified");
    assert_eq!(pool.regions, regions_before, "regions modified");
    assert_eq!(pool.civ_affinities, civ_before, "civ_affinities modified");
    assert_eq!(pool.ages, ages_before, "ages modified");
    assert_eq!(pool.need_safety, needs_before.0, "need_safety modified");
    assert_eq!(pool.need_material, needs_before.1, "need_material modified");
    assert_eq!(pool.need_social, needs_before.2, "need_social modified");
    assert_eq!(pool.need_spiritual, needs_before.3, "need_spiritual modified");
    assert_eq!(pool.need_autonomy, needs_before.4, "need_autonomy modified");
    assert_eq!(pool.need_purpose, needs_before.5, "need_purpose modified");
    assert_eq!(pool.rel_target_ids, rel_targets_before, "rel_target_ids modified");
    assert_eq!(pool.rel_sentiments, rel_sentiments_before, "rel_sentiments modified");
    assert_eq!(pool.rel_bond_types, rel_bonds_before, "rel_bond_types modified");
    assert_eq!(pool.trip_phase, trip_phase_before, "trip_phase modified");
    assert_eq!(pool.alive, alive_before, "alive modified");

    // arrived_this_turn IS expected to change (consumed by knowledge phase)
    assert!(!pool.arrived_this_turn[b], "arrived_this_turn should be cleared");
}
```

- [ ] **Step 3: Write Python-level behavioral inertia test**

This complements the Rust test: runs two same-seed hybrid sims and verifies bundle-level determinism plus knowledge_stats presence.

Append to `tests/test_m59a_knowledge.py`:

```python
def test_hybrid_determinism_with_knowledge_stats(tmp_path):
    """Same seed in hybrid mode: two runs produce identical bundles.

    This is a determinism test, not a pre/post comparison. The Rust-level
    test_knowledge_phase_does_not_modify_non_packet_fields verifies the
    producer-only property directly.
    """
    from chronicler.main import execute_run

    results = []
    for run_idx in range(2):
        run_dir = tmp_path / f"run_{run_idx}"
        run_dir.mkdir()
        args = _make_args(run_dir, seed=42, turns=10, agents="hybrid")
        execute_run(args)
        bundle_path = run_dir / "chronicle_bundle.json"
        assert bundle_path.exists(), f"Run {run_idx} did not produce a bundle"
        results.append(json.loads(bundle_path.read_text()))

    b0, b1 = results
    assert b0["history"] == b1["history"], "history diverged"
    assert b0.get("events_timeline") == b1.get("events_timeline"), "events diverged"

    k0 = b0.get("metadata", {}).get("knowledge_stats", [])
    k1 = b1.get("metadata", {}).get("knowledge_stats", [])
    assert len(k0) == 10, f"Expected 10 turns of knowledge_stats, got {len(k0)}"
    assert k0 == k1, "knowledge_stats diverged between same-seed runs"
```

- [ ] **Step 3: Run Rust tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge -E 'test(test_knowledge_phase_does_not_modify_non_packet_fields)'`
Expected: PASS

- [ ] **Step 4: Run Python tests**

Run: `pytest tests/test_m59a_knowledge.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/tests/test_knowledge.rs tests/test_m59a_knowledge.py
git commit -m "test(m59a): add behavioral inertia, --agents=off compat, and hybrid determinism tests"
```

---

## Task 15: Multi-Turn Chain Diffusion Integration Test

**Files:**
- Test: `chronicler-agents/tests/test_knowledge.rs`

- [ ] **Step 1: Write multi-turn chain diffusion test**

Append to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_multi_turn_chain_diffusion() {
    // Chain: A -> B -> C -> D
    // Turn 1: A observes threat, propagates to B
    // Turn 2: B propagates to C (A's packet, hop=2)
    // Turn 3: C propagates to D (hop=3)
    // Verify hop counts increment and source_turn stays constant
    let seed = [7u8; 32];
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let b = pool.spawn(1, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let c = pool.spawn(2, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    let d = pool.spawn(3, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let a_id = pool.ids[a];
    let b_id = pool.ids[b];
    let c_id = pool.ids[c];
    let d_id = pool.ids[d];

    // Chain bonds: A->B, B->C, C->D (Kin, max sentiment)
    set_bond(&mut pool, a, b_id, 5, 127);
    set_bond(&mut pool, b, c_id, 5, 127);
    set_bond(&mut pool, c, d_id, 5, 127);

    let mut regions: Vec<RegionState> = (0..4).map(|i| RegionState::new(i)).collect();
    regions[0].controller_changed_this_turn = true;

    // Turn 1: A observes threat, propagation may reach B
    let _s1 = knowledge_phase(&mut pool, &regions, &seed, 1);
    regions[0].controller_changed_this_turn = false; // clear transient

    // A should have the packet at hop 0
    let a_pkt = (0..4).find(|&i| unpack_type(pool.pkt_type_and_hops[a][i]) == 1);
    assert!(a_pkt.is_some(), "A should have threat packet");
    assert_eq!(pool.pkt_source_turn[a][a_pkt.unwrap()], 1, "source_turn should be 1");
    assert_eq!(unpack_hops(pool.pkt_type_and_hops[a][a_pkt.unwrap()]), 0, "A's packet should be hop 0");

    // Turn 2
    let _s2 = knowledge_phase(&mut pool, &regions, &seed, 2);

    // Turn 3
    let _s3 = knowledge_phase(&mut pool, &regions, &seed, 3);

    // Turn 4
    let _s4 = knowledge_phase(&mut pool, &regions, &seed, 4);

    // By now, if propagation succeeded along the chain, D should have the packet.
    // The exact turn depends on RNG rolls, but source_turn should always be 1
    // and hop_count should be > 0 for any propagated copy.
    for agent_slot in [b, c, d] {
        for i in 0..4 {
            if unpack_type(pool.pkt_type_and_hops[agent_slot][i]) == 1 {
                assert_eq!(
                    pool.pkt_source_turn[agent_slot][i], 1,
                    "source_turn should be preserved through propagation"
                );
                assert!(
                    unpack_hops(pool.pkt_type_and_hops[agent_slot][i]) > 0,
                    "propagated packets should have hop_count > 0"
                );
            }
        }
    }
}

#[test]
fn test_arrival_flag_consumed_by_knowledge_phase() {
    let mut pool = AgentPool::new(10);
    let a = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.arrived_this_turn[a] = true;

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.5;

    // Turn 1: knowledge phase consumes arrival flag
    let stats = knowledge_phase(&mut pool, &regions, &[0u8; 32], 1);
    assert!(!pool.arrived_this_turn[a], "flag should be cleared");
    assert!(stats.packets_created > 0, "should have created trade packet");

    // Turn 2: no arrival flag, no new trade packet
    let stats2 = knowledge_phase(&mut pool, &regions, &[0u8; 32], 2);
    assert_eq!(stats2.created_trade, 0, "no arrival = no new trade packet");
}
```

- [ ] **Step 2: Run all knowledge tests**

Run: `cd chronicler-agents && cargo nextest run --test test_knowledge`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/test_knowledge.rs
git commit -m "test(m59a): add multi-turn chain diffusion and arrival flag lifecycle tests"
```

---

## Task 16: Final Validation

**Files:**
- No new files — validation only

- [ ] **Step 1: Rebuild Rust extension**

Run: `cd chronicler-agents && maturin develop --release`
Expected: Build succeeds

- [ ] **Step 2: Run full Rust test suite**

Run: `cd chronicler-agents && cargo nextest run`
Expected: All PASS

- [ ] **Step 3: Run full Python test suite**

Run: `pytest tests/ -q`
Expected: All PASS

- [ ] **Step 4: Run a short hybrid simulation to verify runtime integration**

Run: `.venv/Scripts/python.exe -m chronicler.main --seed 42 --turns 20 --agents hybrid --narrator off --output output/m59a_smoke`

Expected: Completes without error. Check that `output/m59a_smoke/chronicle_bundle.json` contains `knowledge_stats` in metadata with 20 entries (one per turn).

- [ ] **Step 5: Verify knowledge_stats content**

Run: `.venv/Scripts/python.exe -c "import json; b = json.load(open('output/m59a_smoke/chronicle_bundle.json')); ks = b['metadata']['knowledge_stats']; print(f'Turns: {len(ks)}'); print(f'Last: {ks[-1] if ks else \"empty\"}')"`

Expected: `Turns: 20` and the last entry should have non-zero `live_packet_count` and `agents_with_packets`.

- [ ] **Step 6: Final commit if any fixups were needed**

Only if fixes were required during validation.
