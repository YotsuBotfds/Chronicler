# M59a: Information Packets & Diffusion — Design Spec

> Date: 2026-03-30
> Status: approved
> Depends on: M50a/b (relationships), M55a (spatial), M58a/b (merchant mobility)
> Downstream: M59b (behavior coupling), M60a (campaign awareness)

---

## Overview

M59a builds the agent-level perception-lag substrate: per-agent information packets that carry cross-region knowledge through the social graph with lag and decay. Agents observe their local region, produce packets, and share them over relationship bonds with probabilistic propagation. The result is a deterministic, inspectable diffusion layer where graph distance equals temporal lag.

M59a is the **substrate only**. It produces packet state and diagnostics. It does not change any agent decision — merchants, migrants, and loyalists continue using perfect-info signals until M59b wires behavior coupling.

---

## Design Decisions

| # | Decision | Resolution |
|---|----------|------------|
| 1 | Packet-only vs derived civ-region cache | Packet-only. Per-agent slots are the single authoritative state. Any civ-region summary is derived transiently for analytics, not persisted. |
| 2 | Merchant planning in M59a | Unchanged. Merchants are packet *producers* (emit on arrival), not *consumers*. Route planning reads `merchant_route_margin` from RegionState. Stale trade knowledge deferred to M59b. |
| 3 | Packet types | Three: `threat_warning`, `trade_opportunity`, `religious_signal`. `political_rumor` deferred until a concrete source and consumer contract exist. |
| 4 | Direct observation sources | Fully Rust-local. No new Python→Rust signals. Sources from existing RegionState fields, merchant trip state, and a new Rust-internal arrival flag. |
| 5 | Propagation model | Probabilistic with deterministic keyed rolls on RNG stream 1800. |
| 6 | Legacy system interaction | No changes to `exploration.py`, `intelligence.py`, or `politics.rs`. Civ-level fog/M24 perception coexists without gating or bridging. |
| 7 | Diagnostics surface | Bundle metadata time series (`knowledge_stats`), following existing `relationship_stats` pattern. No FFI getter or snapshot fields in M59a. |
| 8 | Slot replacement policy | Refresh if same identity and fresher → fill empty → evict-if-better → drop. Admission guard prevents stale packets from evicting fresher ones. |

---

## Data Model

### Packet Storage

4 fixed-width slots per agent on `AgentPool` (Rust SoA). Each slot is 6 bytes:

| Field | Type | Meaning |
|-------|------|---------|
| `type_and_hops` | `u8` | Upper 3 bits = `InfoType` (0-7), lower 5 bits = `hop_count` (0-31) |
| `source_region` | `u16` | Region where information originated |
| `source_turn` | `u16` | Turn of originating direct observation (unchanged by propagation) |
| `intensity` | `u8` | Signal strength (0-255), decays each turn |

Total: **24 bytes/agent** across 4 slots. Matches roadmap budget exactly.

**Canonical empty slot:** all-zero bytes (`type_and_hops = 0` encodes `InfoType::Empty` with `hop_count = 0`).

**Packet identity:** `(info_type, source_region)`. Two packets with the same identity are the same piece of knowledge at different freshness levels.

**`source_turn` semantics:** the turn of the originating direct observation. Propagation copies `source_turn` unchanged. Only direct re-observation from ground truth refreshes it. Staleness = `current_turn - source_turn`.

### InfoType Enum

Lives in a new `knowledge.rs` module:

```rust
#[repr(u8)]
pub enum InfoType {
    Empty           = 0,
    ThreatWarning   = 1,
    TradeOpportunity = 2,
    ReligiousSignal = 3,
    // 4-7 reserved for future types (e.g. political_rumor)
}
```

Extensible — adding variant 4+ requires no layout change.

### Retention Priority

Explicit priority table for eviction ranking (not enum ordinal):

```
ThreatWarning > TradeOpportunity > ReligiousSignal
```

### Arrival Transient

`arrived_this_turn: Vec<bool>` — pool-owned SoA field. Set by merchant mobility (phase 0.9) when a merchant completes arrival. Consumed and cleared by the knowledge phase (0.95). Rust-internal only — not a Python→Rust signal, no cross-boundary reset test needed.

---

## Lifecycle

### Tick Placement

Phase 0.95 in the agent tick, as a dedicated knowledge phase:

```
0.8   Relationship drift
0.9   Merchant mobility
0.95  Knowledge phase:
        1. Decay + expire
        2. Direct observation
        3. Propagation (buffered)
        4. Commit received packets
1.0   Satisfaction
```

### Step 1: Decay + Expire

All non-empty slots: decrement `intensity` by a per-type decay rate. Slots where `intensity` reaches 0: clear to all-zero (reclaim immediately, freeing slots before observation/propagation).

| Packet Type | Decay Rate | Max Lifetime at intensity 255 |
|-------------|-----------|-------------------------------|
| `threat_warning` | 15/turn | ~17 turns |
| `trade_opportunity` | 8/turn | ~32 turns |
| `religious_signal` | 5/turn | ~51 turns |

These are outer bounds — propagation loss and eviction shorten effective lifetimes.

### Step 2: Direct Observation

Agent observes their current region's RegionState and their own state. Creates/refreshes packets. All direct observations set `source_region = agent's current region`, `source_turn = current_turn`, `hop_count = 0`.

**Threat warning sources:**

| RegionState Field | Intensity |
|-------------------|-----------|
| `controller_changed_this_turn` | 200 |
| `war_won_this_turn` | 180 |
| `seceded_this_turn` | 150 |

If multiple threat triggers fire in the same region on the same turn: one packet per identity, use the max mapped intensity (not sum).

**Trade opportunity sources:**

| Source | Intensity Basis |
|--------|----------------|
| Merchant with `arrived_this_turn` flag AND `merchant_route_margin > 0.10` | `clamp(((merchant_route_margin - 0.10) / 0.90 × 230.0) as u8, 50, 230)` — margin threshold of 0.10 prevents zero/marginal arrivals from flooding the network; scale starts above the threshold |

Non-merchant local-market observation deferred from M59a. Merchants are the distinctive cross-region trade information source.

**Religious signal sources:**

| RegionState Field | Intensity |
|-------------------|-----------|
| `persecution_intensity > 0` | `clamp((persecution_intensity × 200.0) as u8, 40, 200)` |
| `conversion_rate` above threshold (> 0.05) | `clamp((conversion_rate × 300.0) as u8, 40, 180)` |
| Schism active (`schism_convert_from != schism_convert_to`) | 160 |

If multiple religious triggers fire in the same region on the same turn: one packet per identity, max intensity.

**Admission policy (applied per packet):**

1. Same identity `(info_type, source_region)` exists in agent's slots:
   - Incoming `source_turn` is newer → refresh in place: copy incoming `intensity`, `source_turn`, and `hop_count`. For direct re-observation this means `hop_count = 0`; for propagated packets this copies the sender's `hop_count + 1`.
   - Same `source_turn` → keep higher `intensity`; if intensity ties, keep lower `hop_count`
   - Incoming is older → drop
2. Empty slot available → insert
3. All slots full → compare incoming against the lowest-ranked incumbent:
   - Ranking: older `source_turn` = easier to evict, then lower retention priority, then higher `slot_index`
   - Incoming outranks lowest incumbent → evict and insert
   - Otherwise → drop incoming

### Step 3: Propagation (Buffered)

Propagation reads from the **post-observation, pre-propagation** snapshot. All transmitted packets go into a write buffer not visible to other propagation reads within the same turn. This enforces one-hop-per-turn.

For each agent with non-empty packets:

1. Read the agent's relationship slots
2. For each non-empty packet:
   a. Identify all relationships with eligible bond types for this packet's `info_type` (per channel filter table)
   b. For each unique receiver: select the bond producing the highest effective propagation chance (multi-bond resolution)
   c. Compute chance and roll

**Multi-bond resolution tie-break** (when two eligible bonds produce the same effective chance): higher `channel_weight` → higher positive `sentiment` → lower `bond_type` ordinal. Independent of relationship slot order.

**Propagation chance formula:**

```
sentiment_factor = max(sentiment, 0) as f32 / 127.0
chance = base_rate[info_type] × channel_weight[bond_type][info_type] × sentiment_factor
```

**RNG:** stream 1800, key = `(sender_id, receiver_id, info_type, source_region, source_turn, current_turn)`.

If roll passes: buffer a received packet for the receiver with `hop_count + 1` and `intensity = sender_intensity × 0.85` (per-hop attenuation, tunable).

**hop_count = 31 halts propagation.** Packets at max hops are not candidates for transmission.

### Step 4: Commit

**Intra-turn merge** (before admission): if multiple buffered transmissions produce the same `(info_type, source_region)` for one receiver in the same turn, dedupe: newest `source_turn` → highest `intensity` → lowest `hop_count`. After dedupe, sort buffered candidates canonically per receiver before admission for thread-stable outcomes.

Apply deduplicated buffered packets to each receiver using the admission policy (refresh/fill/evict-if-better/drop).

---

## Propagation Channels & Weighting

### Channel Filter Table

| Bond Type | threat_warning | trade_opportunity | religious_signal |
|-----------|:-:|:-:|:-:|
| Mentor (0) | yes | yes | - |
| Rival (1) | - | - | - |
| Marriage (2) | yes | yes | yes (secondary) |
| ExileBond (3) | yes | - | - |
| CoReligionist (4) | yes | - | yes (primary) |
| Kin (5) | yes | yes | yes (secondary) |
| Friend (6) | yes | yes | - |
| Grudge (7) | - | - | - |

### Per-Channel Weights

| Bond Type | threat | trade | religious |
|-----------|--------|-------|-----------|
| Mentor | 1.0 | 0.8 | - |
| Marriage | 1.0 | 0.9 | 0.6 |
| ExileBond | 0.8 | - | - |
| CoReligionist | 0.9 | - | 1.0 |
| Kin | 1.0 | 0.7 | 0.7 |
| Friend | 0.9 | 1.0 | - |

### Base Rates

| Packet Type | Base Rate |
|-------------|-----------|
| `threat_warning` | 0.7 |
| `trade_opportunity` | 0.4 |
| `religious_signal` | 0.25 |

Each packet type has a distinct social shape:
- **Threat warning:** broad and urgent — all positive-valence bonds, high base rate
- **Trade opportunity:** trust-and-commerce shaped — Friend/Mentor/Marriage/Kin only
- **Religious signal:** faith-and-family shaped — CoReligionist primary, Kin/Marriage secondary, slow base rate

---

## Diagnostics & Observability

### Surface

Bundle metadata time series (`knowledge_stats`), following the existing `relationship_stats` / `household_stats` / `merchant_trip_stats` pattern.

**Transport path:** Rust accumulates counters into a `KnowledgeStats` struct during the knowledge phase. `ffi.rs` exposes a `get_knowledge_stats() → KnowledgeStats` method on `AgentSimulator`. `agent_bridge.py` calls this after the tick, converts to a Python dict, and appends to the `knowledge_stats` history list. `main.py` writes that history into bundle metadata. `analytics.py` provides an extractor.

**"No FFI getter" means:** no per-agent packet inspection API (no `get_agent_packets(agent_id)` or similar). The aggregate `KnowledgeStats` struct does cross FFI — that is the intended and only transport path for diagnostics.

### Per-Turn Metrics

| Metric | Meaning |
|--------|---------|
| `packets_created` | New packets from direct observation this turn |
| `packets_refreshed` | Existing packets updated by fresher observation or transmission |
| `packets_transmitted` | Successful propagation rolls that produced a buffered receive candidate |
| `packets_expired` | Packets cleared by decay (intensity reached 0) |
| `packets_evicted` | Packets displaced by higher-priority incoming during admission |
| `packets_dropped` | Incoming packets that failed admission (incumbent was better) |
| `live_packet_count` | Total non-empty slots across all agents after commit |
| `agents_with_packets` | Count of agents holding at least one non-empty packet after commit |
| `created_by_type` | `{threat: N, trade: N, religious: N}` |
| `transmitted_by_type` | `{threat: N, trade: N, religious: N}` |
| `mean_age` | Mean `(current_turn - source_turn)` across all live packets (post-commit) |
| `max_age` | Max `(current_turn - source_turn)` across any live packet (post-commit) |
| `mean_hops` | Mean `hop_count` across all live packets (post-commit) |
| `max_hops` | Max `hop_count` across any live packet (post-commit) |

**Zero-fill rule:** when no live packets exist, emit 0/0.0 values rather than omitting fields. Append a zero-filled `knowledge_stats` entry every agent-backed turn so the series stays aligned.

### `--agents=off` Behavior

No knowledge phase runs. No `knowledge_stats` emitted. No bundle metadata pollution.

---

## Scope Boundaries

### In Scope (M59a)

- Packet slot data model and lifecycle (4 slots, 24 bytes/agent)
- Three packet types: `threat_warning`, `trade_opportunity`, `religious_signal`
- Direct observation from Rust-local state (RegionState + trip state + arrival flag)
- Relationship-driven propagation with channel filters, weights, and sentiment scaling
- Decay, staleness, hop tracking, intensity attenuation
- One-hop-per-turn enforcement via buffered writes
- Bundle metadata diagnostics (`knowledge_stats`)
- Merchant arrival flag (Rust-internal transient)

### Out of Scope (Deferred)

| Feature | Deferred To |
|---------|-------------|
| Merchants consuming stale packets for route planning | M59b |
| `political_rumor` packet type | M59b+ (needs concrete source/consumer) |
| Migration/loyalty behavior changes from packets | M59b |
| Campaign awareness / battle intelligence | M60a |
| Replacing civ-level fog / M24 perception | Future |
| Bundle v2 knowledge overlays / viewer | Phase 7.5 |
| New Python→Rust packet-source signals | M59b+ |
| Non-merchant local-market trade observation | M59b+ |
| Derived civ-region knowledge cache | Future (only if profiling shows packet-to-summary scans are a bottleneck) |

---

## Compatibility

- **`--agents=off`:** no knowledge phase, no `knowledge_stats`, no behavioral change. Phase 4 bit-identical.
- **Legacy systems untouched:** `exploration.py` (`known_regions`, `tick_trade_knowledge_sharing`), `intelligence.py`, `politics.rs` remain parallel civ-level systems with no synchronization or bridging in M59a.
- **Merchant planning unchanged:** route selection reads `merchant_route_margin` from RegionState. Merchant decision semantics remain unchanged until M59b.
- **Bundle format:** `knowledge_stats` is additive metadata. No existing bundle fields change.

---

## RNG

- Stream offset **1800** registered in `agent.rs` `STREAM_OFFSETS` block.
- Key: `(sender_id, receiver_id, info_type, source_region, source_turn, current_turn)`.
- No other RNG streams used by M59a.

---

## Testing Requirements

### Unit Tests (Rust)

- Packet refresh/merge/eviction semantics — all admission policy branches
- Decay rates per type — intensity reaching zero clears slot to all-zero
- Channel filtering by bond type — eligible, ineligible, multi-bond resolution with tie-breaks
- Deterministic propagation rolls and tie-breaks
- `hop_count = 31` halts propagation
- Intra-turn merge dedupe (newest `source_turn` → highest `intensity` → lowest `hop_count`)
- Arrival flag set by merchant mobility, consumed and cleared by knowledge phase
- `source_turn` unchanged through propagation, reset on direct re-observation

### Integration Tests (Rust + Python)

- Multi-turn chain diffusion across bonded agents (verify one-hop-per-turn)
- Direct observation from regional shock sources (controller change, war, secession)
- Direct observation from merchant arrival
- Diagnostics counters emitted and stable across turns
- Zero-fill diagnostics on turns with no live packets

### Determinism Tests

- Same-seed cross-process replay produces identical packet state
- Propagation ordering independent of relationship slot order

### Compatibility Tests

- `--agents=off` produces no `knowledge_stats` and no behavioral change
- Merchant planning unchanged (route selection reads same signals, produces same outcomes)

### Behavioral Inertia Regression

- Same seed in agent mode: merchant routing and all pre-existing decisions produce identical outcomes aside from additive `knowledge_stats` metadata. Verifies M59a is producer-only and RNG stream 1800 is fully isolated.

---

## File Touch Map

### New

| File | Role |
|------|------|
| `chronicler-agents/src/knowledge.rs` | InfoType enum, packet slot operations, knowledge phase orchestration, diagnostics struct |
| `tests/test_m59a_knowledge.py` | Python integration tests for M59a |

### Modified (Rust)

| File | Change |
|------|--------|
| `chronicler-agents/src/lib.rs` | Register `knowledge` module |
| `chronicler-agents/src/agent.rs` | Register stream offset 1800 in `STREAM_OFFSETS` |
| `chronicler-agents/src/pool.rs` | Add 4 packet SoA slot arrays + `arrived_this_turn` SoA field |
| `chronicler-agents/src/tick.rs` | Call knowledge phase at 0.95 |
| `chronicler-agents/src/ffi.rs` | Expose diagnostics struct to Python |
| `chronicler-agents/src/merchant.rs` | Set `arrived_this_turn` flag on merchant arrival |

### Modified (Python)

| File | Change |
|------|--------|
| `src/chronicler/agent_bridge.py` | Receive FFI diagnostics, build `knowledge_stats` dict |
| `src/chronicler/main.py` | Append `knowledge_stats` to bundle metadata history |
| `src/chronicler/analytics.py` | Extractor for `knowledge_stats` metadata family |

### Not Touched

`models.py`, `simulation.py`, `exploration.py`, `intelligence.py`, `economy.py`, `politics.rs`, `relationships.rs` (read-only access from knowledge phase)
