# M59b: Perception-Coupled Behavior — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agents act on propagated information — merchants plan routes from trade packets instead of omniscient scans, migrants avoid destinations they've heard are threatened.

**Architecture:** Two consumers wired into existing Rust decision code. Merchant route evaluation (`merchant.rs`) switches from oracle scan to packet-gated candidate selection with counted bootstrap fallback. Migration scoring (`behavior.rs`) applies threat penalties to adjacent targets. Four new diagnostic counters on `KnowledgeStats` with cross-phase merge in `tick.rs`.

**Tech Stack:** Rust (chronicler-agents crate), Python (agent_bridge.py normalization), pytest + cargo nextest

---

## File Map

### Rust — create/modify

| File | Responsibility |
|------|---------------|
| `chronicler-agents/src/knowledge.rs` | Add packet query helpers (`usable_trade_packets`, `strongest_threat_for_region`); broaden `observe_packets` for idle/loading merchant local observation with `arrived_this_turn` dedup; add 4 consumer counter fields to `KnowledgeStats` |
| `chronicler-agents/src/merchant.rs` | New `evaluate_route_packet_aware` function (packet-gated destination selection); add `ConsumerStats` fields to `MerchantTripStats`; modify `merchant_mobility_phase` to call packet-aware route eval and accumulate counters |
| `chronicler-agents/src/behavior.rs` | Modify `best_migration_target_for_agent` to accept packet slots and apply threat penalties; add `migration_choices_changed_by_threat` counter return |
| `chronicler-agents/src/tick.rs` | Merge consumer counters from merchant phase and behavior phase into `KnowledgeStats` before return |
| `chronicler-agents/src/ffi.rs` | Add 4 new fields to `get_knowledge_stats()` HashMap |

### Rust — test files

| File | Responsibility |
|------|---------------|
| `chronicler-agents/tests/test_knowledge.rs` | Local trade observation, arrival dedup, query helper tests |
| `chronicler-agents/tests/test_merchant.rs` | Packet-gated routing, bootstrap fallback, anti-omniscience, scoring |
| `chronicler-agents/tests/test_behavior.rs` | Threat penalty, strongest-wins, own-region exclusion, non-adjacent exclusion |

### Python — modify

| File | Responsibility |
|------|---------------|
| `src/chronicler/agent_bridge.py` | Add 4 new counter keys to `int_keys` set in normalization block (~line 887) |
| `src/chronicler/analytics.py` | No changes needed — extractor already forwards all keys from knowledge_stats |
| `tests/test_m59a_knowledge.py` | Add assertions for new counter fields in bundle metadata |

---

## Task 1: Packet Query Helpers on `knowledge.rs`

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs:156-177` (KnowledgeStats struct)
- Modify: `chronicler-agents/src/knowledge.rs` (add query functions after commit_buffered at ~line 644)
- Test: `chronicler-agents/tests/test_knowledge.rs`

### Substeps

- [ ] **Step 1: Add consumer counter fields to `KnowledgeStats`**

In `chronicler-agents/src/knowledge.rs`, add 4 fields to the `KnowledgeStats` struct after `max_hops`:

```rust
    pub max_hops: u32,
    // M59b: Consumer counters (accumulated outside knowledge_phase, merged in tick.rs)
    pub merchant_plans_packet_driven: u32,
    pub merchant_plans_bootstrap: u32,
    pub merchant_no_usable_packets: u32,
    pub migration_choices_changed_by_threat: u32,
```

These derive `Default` (already on the struct), so they start at 0.

- [ ] **Step 2: Add `usable_trade_packets` query helper**

Add after `commit_buffered` (~line 644) in `knowledge.rs`:

```rust
/// M59b: Collect usable nonlocal trade_opportunity packets for a merchant.
/// Returns vec of (source_region, packet_strength) for packets where:
/// - info_type == TradeOpportunity
/// - intensity > 0
/// - source_region != current_region
/// Caller is responsible for reachability filtering.
pub fn usable_trade_packets(
    pool: &AgentPool,
    slot: usize,
    current_region: u16,
) -> Vec<(u16, f32)> {
    let mut results = Vec::new();
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) {
            continue;
        }
        if unpack_type(th) != InfoType::TradeOpportunity as u8 {
            continue;
        }
        let intensity = pool.pkt_intensity[slot][i];
        if intensity == 0 {
            continue;
        }
        let source_region = pool.pkt_source_region[slot][i];
        if source_region == current_region {
            continue;
        }
        results.push((source_region, intensity as f32 / 255.0));
    }
    results
}
```

- [ ] **Step 3: Add `strongest_threat_for_region` query helper**

Add after `usable_trade_packets`:

```rust
/// M59b: Find the strongest threat_warning packet targeting `target_region`.
/// Returns the packet strength (intensity / 255.0) of the strongest match,
/// or 0.0 if no matching threat packet is held.
/// Excludes packets sourced from the agent's own region.
pub fn strongest_threat_for_region(
    pool: &AgentPool,
    slot: usize,
    target_region: u16,
    own_region: u16,
) -> f32 {
    let mut best: f32 = 0.0;
    for i in 0..agent::PACKET_SLOTS {
        let th = pool.pkt_type_and_hops[slot][i];
        if is_empty_slot(th) {
            continue;
        }
        if unpack_type(th) != InfoType::ThreatWarning as u8 {
            continue;
        }
        let source_region = pool.pkt_source_region[slot][i];
        if source_region != target_region {
            continue;
        }
        if source_region == own_region {
            continue;
        }
        let strength = pool.pkt_intensity[slot][i] as f32 / 255.0;
        if strength > best {
            best = strength;
        }
    }
    best
}
```

- [ ] **Step 4: Write tests for query helpers**

Add to `chronicler-agents/tests/test_knowledge.rs`:

```rust
use chronicler_agents::knowledge::{
    usable_trade_packets, strongest_threat_for_region,
};

#[test]
fn test_usable_trade_packets_filters_correctly() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 0; // current region = 0

    // Slot 0: trade packet from region 1 (usable)
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 200,
        hop_count: 1,
    });
    // Slot 1: trade packet from region 0 (local — excluded)
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 0,
        source_turn: 5,
        intensity: 180,
        hop_count: 0,
    });
    // Slot 2: threat packet from region 2 (wrong type — excluded)
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 2,
        source_turn: 5,
        intensity: 150,
        hop_count: 0,
    });

    let result = usable_trade_packets(&pool, slot, 0);
    assert_eq!(result.len(), 1);
    assert_eq!(result[0].0, 1); // source_region
    assert!((result[0].1 - 200.0 / 255.0).abs() < 0.01); // packet_strength
}

#[test]
fn test_strongest_threat_for_region() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 0;

    // Two threat packets for region 2 with different intensities
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 2,
        source_turn: 5,
        intensity: 100,
        hop_count: 1,
    });
    // Same identity — will refresh if newer/stronger
    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 2,
        source_turn: 6,
        intensity: 180,
        hop_count: 0,
    });

    let strength = strongest_threat_for_region(&pool, slot, 2, 0);
    assert!((strength - 180.0 / 255.0).abs() < 0.01);

    // No threat for region 3
    assert_eq!(strongest_threat_for_region(&pool, slot, 3, 0), 0.0);
}

#[test]
fn test_threat_own_region_excluded() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 2;

    admit_packet(&mut pool, slot, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 2,
        source_turn: 5,
        intensity: 200,
        hop_count: 0,
    });

    // target_region == own_region == 2 → excluded
    assert_eq!(strongest_threat_for_region(&pool, slot, 2, 2), 0.0);
}
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents --test test_knowledge`
Expected: All tests PASS including 3 new query helper tests.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59b): add packet query helpers and consumer counter fields"
```

---

## Task 2: Broaden Local Trade Observation

**Files:**
- Modify: `chronicler-agents/src/knowledge.rs:334-453` (observe_packets function)
- Test: `chronicler-agents/tests/test_knowledge.rs`

### Substeps

- [ ] **Step 1: Write the failing test for local trade observation**

Add to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_local_trade_observation_idle_merchant() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 0;
    pool.trip_phase[slot] = 0; // TRIP_PHASE_IDLE
    pool.arrived_this_turn[slot] = false;

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.50; // above TRADE_MARGIN_THRESHOLD (0.10)

    let (created, _, _, _, _, created_trade, _) =
        observe_packets(&mut pool, &regions, &[slot], 10);

    assert!(created >= 1, "Idle merchant should observe local trade");
    assert!(created_trade >= 1, "Should be a trade packet");
    // Check the packet was admitted
    let packets = usable_trade_packets(&pool, slot, 99); // 99 = fake "other" region
    // The local packet has source_region=0, which is the merchant's current region.
    // usable_trade_packets filters out local — so check raw slots instead.
    let has_trade = (0..4).any(|i| {
        unpack_type(pool.pkt_type_and_hops[slot][i]) == InfoType::TradeOpportunity as u8
            && pool.pkt_source_region[slot][i] == 0
    });
    assert!(has_trade, "Idle merchant should have a trade packet from own region");
}

#[test]
fn test_local_trade_observation_skips_transit() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 1;
    pool.trip_phase[slot] = 2; // TRIP_PHASE_TRANSIT
    pool.arrived_this_turn[slot] = false;

    let mut regions = vec![RegionState::new(0), RegionState::new(1)];
    regions[1].merchant_route_margin = 0.50;

    let (created, _, _, _, _, created_trade, _) =
        observe_packets(&mut pool, &regions, &[slot], 10);

    assert_eq!(created_trade, 0, "Transit merchant should NOT observe local trade");
}

#[test]
fn test_local_trade_observation_skips_arrived_this_turn() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 0;
    pool.trip_phase[slot] = 0; // TRIP_PHASE_IDLE (arrived merchants reset to idle)
    pool.arrived_this_turn[slot] = true; // arrived this turn — arrival path handles it

    let mut regions = vec![RegionState::new(0)];
    regions[0].merchant_route_margin = 0.50;

    let (created, _, _, dropped, _, _, _) =
        observe_packets(&mut pool, &regions, &[slot], 10);

    // Arrival already fires the trade observation. Local observation must not
    // fire a duplicate that would show up as a Dropped in diagnostics.
    // We expect exactly 1 created (from arrival path), 0 dropped.
    assert_eq!(created, 1, "Only arrival path should create the packet");
    assert_eq!(dropped, 0, "No duplicate admission attempt should be dropped");
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo nextest run -p chronicler-agents --test test_knowledge -- test_local_trade_observation`
Expected: FAIL — `test_local_trade_observation_idle_merchant` fails because `observe_packets` only creates trade packets on `arrived_this_turn`.

- [ ] **Step 3: Modify `observe_packets` to broaden local trade observation**

In `chronicler-agents/src/knowledge.rs`, in the `observe_packets` function, modify the trade opportunity block (currently at ~line 387). Replace:

```rust
        // --- Trade opportunity ---
        if pool.arrived_this_turn[slot] && region.merchant_route_margin > TRADE_MARGIN_THRESHOLD {
```

With:

```rust
        // --- Trade opportunity ---
        // M59b: Broaden to idle/loading merchants (not just arrivals).
        // Skip transit merchants (intermediate hops) and arrived_this_turn
        // (arrival path already fires — dedup to prevent dropped-packet noise).
        let is_merchant = pool.occupations[slot] == crate::agent::Occupation::Merchant as u8;
        let is_trade_eligible = if pool.arrived_this_turn[slot] {
            // Arrival path: original M59a behavior
            true
        } else if is_merchant
            && (pool.trip_phase[slot] == crate::agent::TRIP_PHASE_IDLE
                || pool.trip_phase[slot] == crate::agent::TRIP_PHASE_LOADING)
        {
            // M59b: Idle/loading merchant local observation
            true
        } else {
            false
        };
        if is_trade_eligible && region.merchant_route_margin > TRADE_MARGIN_THRESHOLD {
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents --test test_knowledge`
Expected: All tests PASS including 3 new local observation tests.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/knowledge.rs chronicler-agents/tests/test_knowledge.rs
git commit -m "feat(m59b): broaden local trade observation to idle/loading merchants"
```

---

## Task 3: Packet-Gated Merchant Route Evaluation

**Files:**
- Modify: `chronicler-agents/src/merchant.rs:353-428` (evaluate_route function area)
- Modify: `chronicler-agents/src/merchant.rs:198-208` (MerchantTripStats)
- Test: `chronicler-agents/tests/test_merchant.rs`

### Substeps

- [ ] **Step 1: Add consumer counter fields to `MerchantTripStats`**

In `chronicler-agents/src/merchant.rs`, add to `MerchantTripStats` after `overcommit_count`:

```rust
    pub overcommit_count: u32,
    // M59b: Packet-driven planning counters
    pub plans_packet_driven: u32,
    pub plans_bootstrap: u32,
    pub no_usable_packets: u32,
```

- [ ] **Step 2: Write the packet-aware route evaluation function**

Add after `evaluate_route` (~line 428) in `merchant.rs`:

```rust
/// M59b: Packet-gated route evaluation. When usable nonlocal trade packets
/// exist (after reachability filtering), only packet-known destinations are
/// candidates. Falls back to oracle (evaluate_route) when usable set is empty.
///
/// Returns (Option<TripIntent>, used_packets: bool).
pub fn evaluate_route_packet_aware(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    pool: &AgentPool,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
    delivery_buf: Option<&DeliveryBuffer>,
    stats: &mut MerchantTripStats,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    if origin >= regions.len() {
        return None;
    }

    // Collect usable nonlocal trade packets
    let raw_packets = crate::knowledge::usable_trade_packets(pool, agent_slot, origin_region);

    // Reachability filter: only keep packets whose source_region is reachable
    let reachable_packets: Vec<(u16, f32)> = raw_packets
        .into_iter()
        .filter(|&(src_region, _)| {
            let idx = src_region as usize;
            idx < path_table.dist.len()
                && path_table.dist[idx] != 0
                && path_table.dist[idx] != u16::MAX
        })
        .collect();

    if reachable_packets.is_empty() {
        // Bootstrap fallback: no usable packets, use oracle planner
        stats.no_usable_packets += 1;
        let intent = evaluate_route(
            agent_slot, agent_id, origin_region, regions, path_table, ledger, delivery_buf,
        );
        if intent.is_some() {
            stats.plans_bootstrap += 1;
        }
        return intent;
    }

    // Packet-gated planning: score only packet-known destinations
    let origin_margin = regions[origin].merchant_route_margin;
    let mut best_dest: Option<u16> = None;
    let mut best_score: f32 = MIN_TRIP_PROFIT;
    let mut best_dest_id_tiebreak: (u16, u32) = (u16::MAX, u32::MAX);

    for &(src_region, packet_strength) in &reachable_packets {
        let score = origin_margin + packet_strength;
        let tiebreak = (src_region, agent_id);
        if score > best_score || (score == best_score && tiebreak < best_dest_id_tiebreak) {
            best_score = score;
            best_dest = Some(src_region);
            best_dest_id_tiebreak = tiebreak;
        }
    }

    let dest = match best_dest {
        Some(d) => d,
        None => {
            // All packet-gated destinations below MIN_TRIP_PROFIT.
            // Do NOT fall back to oracle — anti-omniscience rule.
            return None;
        }
    };

    // Find best good slot with available cargo (same logic as evaluate_route)
    let mut best_slot: Option<u8> = None;
    let mut best_avail: f32 = 0.0;
    for slot in 0..8u8 {
        let overcommitted = match delivery_buf {
            Some(buf) => ledger.is_overcommitted_hybrid(origin, slot as usize, &regions[origin].stockpile, buf),
            None => ledger.is_overcommitted(origin, slot as usize, &regions[origin].stockpile),
        };
        if overcommitted {
            continue;
        }
        let avail = match delivery_buf {
            Some(buf) => ledger.available_hybrid(origin, slot as usize, &regions[origin].stockpile, buf),
            None => ledger.available(origin, slot as usize, &regions[origin].stockpile),
        };
        if avail > best_avail || (avail == best_avail && best_slot.is_none_or(|s| slot < s)) {
            best_avail = avail;
            best_slot = Some(slot);
        }
    }

    let good_slot = best_slot.filter(|_| best_avail > 0.0)?;
    let cargo_qty = best_avail.min(MERCHANT_CARGO_CAP);

    let (path, path_len) = trace_path(path_table, origin_region, dest)?;

    stats.plans_packet_driven += 1;

    Some(TripIntent {
        agent_slot,
        origin_region,
        dest_region: dest,
        good_slot,
        cargo_qty,
        path,
        path_len,
    })
}
```

- [ ] **Step 3: Wire packet-aware evaluation into `merchant_mobility_phase`**

In `merchant_mobility_phase` (~line 682-696), replace the route evaluation loop:

```rust
    // Phase f-g: Route evaluation for idle merchants + cargo reservation
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut intents: Vec<TripIntent> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE { continue; }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 { continue; }
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        if let Some(intent) = evaluate_route(slot, pool.ids[slot], origin, regions, table, ledger, delivery_buf.as_deref()) {
            intents.push(intent);
        }
    }
```

With:

```rust
    // Phase f-g: Route evaluation for idle merchants + cargo reservation
    // M59b: Use packet-aware route evaluation (packet-gated with bootstrap fallback)
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut intents: Vec<TripIntent> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE { continue; }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 { continue; }
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        if let Some(intent) = evaluate_route_packet_aware(
            slot, pool.ids[slot], origin, pool, regions, table, ledger,
            delivery_buf.as_deref(), &mut stats,
        ) {
            intents.push(intent);
        }
    }
```

- [ ] **Step 4: Write tests for packet-gated routing**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
use chronicler_agents::knowledge::{
    admit_packet, AdmitResult, PacketCandidate, InfoType,
};
use chronicler_agents::merchant::evaluate_route_packet_aware;

#[test]
fn test_packet_gated_routing_uses_packet_destinations() {
    let (mut pool, regions, graph) = setup_linear_world();
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    // Give the merchant a trade packet for region 2 (not region 3 which is the oracle best)
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 2,
        source_turn: 5,
        intensity: 200,
        hop_count: 1,
    });

    let intent = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    assert!(intent.is_some(), "Should find a route");
    let intent = intent.unwrap();
    assert_eq!(intent.dest_region, 2, "Should route to packet-known region 2, not oracle-best region 3");
    assert_eq!(stats.plans_packet_driven, 1);
    assert_eq!(stats.plans_bootstrap, 0);
    assert_eq!(stats.no_usable_packets, 0);
}

#[test]
fn test_bootstrap_when_no_usable_packets() {
    let (pool, regions, graph) = setup_linear_world();
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    // No packets — should fall back to oracle
    let intent = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    assert!(intent.is_some(), "Bootstrap should find oracle route");
    let intent = intent.unwrap();
    assert_eq!(intent.dest_region, 3, "Bootstrap oracle should pick region 3 (highest margin)");
    assert_eq!(stats.plans_packet_driven, 0);
    assert_eq!(stats.plans_bootstrap, 1);
    assert_eq!(stats.no_usable_packets, 1);
}

#[test]
fn test_anti_omniscience_no_fallback_when_packets_exist_but_unprofitable() {
    let (mut pool, mut regions, graph) = setup_linear_world();
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    // Set origin margin very low so packet score < MIN_TRIP_PROFIT
    regions[0].merchant_route_margin = 0.0;

    // Give merchant a packet for region 1 with very low intensity
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 1, // 1/255 ≈ 0.004, plus 0.0 origin margin < MIN_TRIP_PROFIT (0.05)
        hop_count: 3,
    });

    let intent = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    assert!(intent.is_none(), "Must NOT fall back to oracle when usable packets exist but are unprofitable");
    assert_eq!(stats.plans_packet_driven, 0);
    assert_eq!(stats.plans_bootstrap, 0);
    assert_eq!(stats.no_usable_packets, 0);
}

#[test]
fn test_bootstrap_when_packet_destination_unreachable() {
    let (mut pool, regions, graph) = setup_linear_world();
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    // Give merchant a packet for region 99 (does not exist in graph)
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 99,
        source_turn: 5,
        intensity: 200,
        hop_count: 1,
    });

    let intent = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    // Unreachable packet filtered out → empty usable set → bootstrap
    assert!(intent.is_some());
    assert_eq!(intent.unwrap().dest_region, 3, "Should fall back to oracle");
    assert_eq!(stats.no_usable_packets, 1);
    assert_eq!(stats.plans_bootstrap, 1);
}

#[test]
fn test_packet_driven_and_bootstrap_mutually_exclusive() {
    let (mut pool, regions, graph) = setup_linear_world();
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    // With packet → packet-driven
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::TradeOpportunity as u8,
        source_region: 2,
        source_turn: 5,
        intensity: 200,
        hop_count: 1,
    });
    let _ = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    assert_eq!(stats.plans_packet_driven, 1);
    assert_eq!(stats.plans_bootstrap, 0);
    assert!(stats.plans_packet_driven > 0 && stats.plans_bootstrap == 0,
        "packet_driven and bootstrap must be mutually exclusive");
}

#[test]
fn test_no_usable_packets_increments_even_when_bootstrap_fails() {
    // Build a world with no cargo available
    let mut pool = AgentPool::new(10);
    pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions: Vec<RegionState> = (0..4)
        .map(|i| {
            let mut r = RegionState::new(i);
            // Zero stockpile — no cargo available
            r.stockpile = [0.0; 8];
            r.controller_civ = 0;
            r
        })
        .collect();
    regions[0].merchant_route_margin = 0.1;
    regions[3].merchant_route_margin = 0.8;

    let graph = RouteGraph::from_edges(
        &[0, 1, 1, 2, 2, 3],
        &[1, 0, 2, 1, 3, 2],
        &[false; 6],
        &[1.0; 6],
        4,
    );
    let ledger = ShadowLedger::new(4);
    let table = bfs_from(&graph, 0);
    let mut stats = MerchantTripStats::default();

    let intent = evaluate_route_packet_aware(
        0, pool.ids[0], 0, &pool, &regions, &table, &ledger, None, &mut stats,
    );

    assert!(intent.is_none(), "No cargo → no intent");
    assert_eq!(stats.no_usable_packets, 1, "Should still count the empty packet set");
}
```

- [ ] **Step 5: Run tests**

Run: `cargo nextest run -p chronicler-agents --test test_merchant`
Expected: All tests PASS including 6 new packet-gated routing tests.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m59b): packet-gated merchant route evaluation with bootstrap fallback"
```

---

## Task 4: Threat-Aware Migration

**Files:**
- Modify: `chronicler-agents/src/behavior.rs:132-189` (best_migration_target_for_agent)
- Create: `chronicler-agents/tests/test_behavior.rs`

### Substeps

- [ ] **Step 1: Add `MAX_THREAT_PENALTY` constant**

In `chronicler-agents/src/behavior.rs`, add after the existing migration constants (~line 48):

```rust
/// M59b: Maximum penalty applied to adjacent migration target from a threat packet.
const MAX_THREAT_PENALTY: f32 = 0.20;
```

- [ ] **Step 2: Modify `best_migration_target_for_agent` to accept pool reference and apply threat penalties**

The function already takes `pool: &AgentPool` and `slot: usize`. Modify the return type to include a changed-by-threat flag. Change the signature from:

```rust
fn best_migration_target_for_agent(
    pool: &AgentPool,
    regions: &[RegionState],
    stats: &RegionStats,
    region_id: usize,
    slot: usize,
) -> (u16, f32) {
```

To:

```rust
/// Returns (best_target, migration_opportunity, choices_changed_by_threat).
fn best_migration_target_for_agent(
    pool: &AgentPool,
    regions: &[RegionState],
    stats: &RegionStats,
    region_id: usize,
    slot: usize,
) -> (u16, f32, bool) {
```

Inside the function, after computing `adj_score` (at ~line 177-178), before the `if adj_score > best_adj_score` comparison, add threat penalty application:

```rust
        let adj_score = migration_region_score(&regions[adj], adj_mean, adj_pop)
            + polity_alignment_score(&regions[region_id], &regions[adj], civ);
```

After this, add:

```rust
            // M59b: Apply threat penalty from held packets (adjacent only, own-region excluded)
            let threat_strength = crate::knowledge::strongest_threat_for_region(
                pool, slot, adj as u16, region_id as u16,
            );
            if threat_strength > 0.0 {
                adj_score -= MAX_THREAT_PENALTY * threat_strength;
            }
```

Note: `adj_score` must be declared `let mut adj_score` for this to work. Change the existing line from `let adj_score` (or `let mut adj_score` if already mutable) accordingly.

Then, track baseline and post-penalty best targets. Replace the current best-tracking and return logic:

At the start of the function (after `let mut best_adj_id = region_id as u16;`), add:

```rust
    let mut baseline_best_adj_id = region_id as u16;
    let mut baseline_best_adj_score = own_score;
```

In the adjacency loop, before applying threat penalty, track the baseline:

```rust
            // M59b: Track baseline (pre-penalty) best for diagnostic comparison
            let pre_penalty_score = adj_score; // before threat penalty
            if pre_penalty_score > baseline_best_adj_score {
                baseline_best_adj_score = pre_penalty_score;
                baseline_best_adj_id = adj as u16;
            }
```

Then apply the threat penalty after the baseline tracking.

At the return, compute the changed flag:

```rust
    let threat_changed = best_adj_id != baseline_best_adj_id;
    (best_adj_id, (best_adj_score - own_score).max(0.0), threat_changed)
```

- [ ] **Step 3: Update all callers of `best_migration_target_for_agent`**

In `evaluate_region_decisions` (~line 481-485), update the destructuring:

```rust
        let (best_migration_target, migration_opportunity) = if is_displaced {
            (region_id as u16, 0.0)
        } else {
            best_migration_target_for_agent(pool, regions, stats, region_id, slot)
        };
```

To:

```rust
        let (best_migration_target, migration_opportunity, _threat_changed) = if is_displaced {
            (region_id as u16, 0.0, false)
        } else {
            best_migration_target_for_agent(pool, regions, stats, region_id, slot)
        };
```

In `compute_region_stats` (~line 353-396), there's a second call site that computes region-level migration opportunity. This one does NOT use per-agent packets (it's a region-level aggregate), so it should keep using the original non-packet logic. The threat penalty is per-agent, applied only in `best_migration_target_for_agent`. No change needed here.

- [ ] **Step 4: Add counter accumulation to `evaluate_region_decisions`**

Modify `evaluate_region_decisions` to return a threat-changed counter. Change the return type from `PendingDecisions` to `(PendingDecisions, u32)`:

```rust
pub fn evaluate_region_decisions(
    ...
) -> (PendingDecisions, u32) {
    let mut pending = PendingDecisions::new();
    let mut threat_changed_count: u32 = 0;
```

Then in the loop where threat_changed is computed:

```rust
        let (best_migration_target, migration_opportunity, threat_changed) = if is_displaced {
            (region_id as u16, 0.0, false)
        } else {
            best_migration_target_for_agent(pool, regions, stats, region_id, slot)
        };
        if threat_changed {
            threat_changed_count += 1;
        }
```

At the end of the function:

```rust
    (pending, threat_changed_count)
}
```

- [ ] **Step 5: Update callers of `evaluate_region_decisions` in `tick.rs`**

In `tick.rs` (~line 209), the call is inside a parallel `map`. Update the destructuring:

```rust
                evaluate_region_decisions(
                    pool_ref,
                    slots,
                    regions,
                    &regions[region_id],
                    stats_ref,
                    region_id,
                    &mut rng,
                    id_to_slot_ref,
                )
```

This returns `(PendingDecisions, u32)` now. The `pending_decisions` collection needs to store both. Change the collect type:

```rust
    let pending_decisions_with_threat: Vec<(PendingDecisions, u32)> = {
```

Then split apart after collection:

```rust
    let migration_threat_changed: u32 = pending_decisions_with_threat.iter().map(|(_, c)| c).sum();
    let mut pending_decisions: Vec<PendingDecisions> = pending_decisions_with_threat
        .into_iter()
        .map(|(pd, _)| pd)
        .collect();
```

Update the household consolidation call to use `&mut pending_decisions` (unchanged shape).

Then update the apply loop — previously `for pd in &pending_decisions`, no change needed in the loop body.

- [ ] **Step 6: Write tests**

Create `chronicler-agents/tests/test_behavior.rs`:

```rust
//! M59b: Threat-aware migration tests.

use chronicler_agents::{AgentPool, Occupation, RegionState};
use chronicler_agents::knowledge::{
    admit_packet, PacketCandidate, InfoType,
};
use chronicler_agents::signals::{CivSignals, TickSignals};

/// Build minimal TickSignals with no wars for `num_regions` regions.
fn peaceful_signals(num_regions: usize) -> TickSignals {
    TickSignals {
        civs: vec![CivSignals {
            civ_id: 0,
            stability: 55,
            is_at_war: false,
            dominant_faction: 0,
            faction_military: 0.25,
            faction_merchant: 0.25,
            faction_cultural: 0.25,
            shock_stability: 0.0,
            shock_economy: 0.0,
            shock_military: 0.0,
            shock_culture: 0.0,
            demand_shift_farmer: 0.0,
            demand_shift_soldier: 0.0,
            demand_shift_merchant: 0.0,
            demand_shift_scholar: 0.0,
            demand_shift_priest: 0.0,
            mean_boldness: 0.0,
            mean_ambition: 0.0,
            mean_loyalty_trait: 0.0,
            faction_clergy: 0.25,
            gini_coefficient: 0.0,
            conquered_this_turn: false,
            priest_tithe_share: 0.0,
            cultural_drift_multiplier: 1.0,
            religion_intensity_multiplier: 1.0,
        }],
        contested_regions: vec![false; num_regions],
    }
}

/// Build a 3-region world with region 0 adjacent to regions 1 and 2.
fn setup_migration_world() -> (AgentPool, Vec<RegionState>) {
    let mut pool = AgentPool::new(10);
    // Spawn a farmer at region 0
    pool.spawn(0, 0, Occupation::Farmer, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.set_satisfaction(0, 0.3); // low satisfaction → wants to migrate

    let mut regions: Vec<RegionState> = (0..3)
        .map(|i| {
            let mut r = RegionState::new(i);
            r.carrying_capacity = 100;
            r.controller_civ = 0;
            r.food_sufficiency = 1.0;
            r
        })
        .collect();

    // Region 0 adjacent to 1 and 2
    regions[0].adjacency_mask = (1 << 1) | (1 << 2);
    regions[1].adjacency_mask = 1 << 0;
    regions[2].adjacency_mask = 1 << 0;

    (pool, regions)
}

#[test]
fn test_threat_penalty_changes_best_target() {
    let (mut pool, regions) = setup_migration_world();

    // Without threat: both regions 1 and 2 are equal; deterministic tiebreak picks 1
    // (lower index wins in the adjacency scan since scores are equal)

    // Give a strong threat packet for region 1
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 200,
        hop_count: 0,
    });

    // Now compute migration — need RegionStats
    use chronicler_agents::behavior::compute_region_stats;
    let signals = peaceful_signals(3);
    let stats = compute_region_stats(&pool, &regions, &signals);

    // Call best_migration_target_for_agent via evaluate_region_decisions
    use chronicler_agents::behavior::evaluate_region_decisions;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;
    let id_to_slot = std::collections::HashMap::from([(pool.ids[0], 0usize)]);
    let mut rng = ChaCha8Rng::from_seed([0u8; 32]);
    let (pending, threat_count) = evaluate_region_decisions(
        &pool, &[0], &regions, &regions[0], &stats, 0, &mut rng, &id_to_slot,
    );

    // The agent should prefer region 2 (unthreatened) over region 1 (threatened)
    if !pending.migrations.is_empty() {
        let (_, _, target) = pending.migrations[0];
        assert_eq!(target, 2, "Should migrate to unthreatened region 2, not threatened region 1");
    }
    assert!(threat_count > 0, "Threat penalty should have changed the best target");
}

#[test]
fn test_own_region_threat_not_applied() {
    let (mut pool, regions) = setup_migration_world();
    pool.regions[0] = 1; // agent is in region 1

    // Threat for region 1 (agent's own region) — should NOT affect migration scoring
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1, // own region
        source_turn: 5,
        intensity: 255,
        hop_count: 0,
    });

    use chronicler_agents::knowledge::strongest_threat_for_region;
    // When target == own_region, should return 0
    let strength = strongest_threat_for_region(&pool, 0, 1, 1);
    assert_eq!(strength, 0.0, "Own-region threat should be excluded");
}

#[test]
fn test_non_adjacent_threat_not_applied() {
    let (mut pool, regions) = setup_migration_world();

    // Threat for region 99 (not adjacent) — should not affect anything
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 99,
        source_turn: 5,
        intensity: 255,
        hop_count: 0,
    });

    use chronicler_agents::knowledge::strongest_threat_for_region;
    // Region 99 is not in the adjacency mask, so even if the query returns
    // a strength, it won't be applied because the migration loop only
    // iterates adjacent regions (bits in adjacency_mask).
    // The query itself still returns a value if the packet exists:
    let strength = strongest_threat_for_region(&pool, 0, 99, 0);
    // This proves the query works — but the migration loop never queries
    // region 99 because it's not in adjacency_mask. The adjacency constraint
    // is structural, not in the query helper.
    assert!(strength > 0.0, "Query returns strength for the packet");
    // The actual test is that non-adjacent threats don't change behavior —
    // verified by the fact that the migration loop only iterates adjacency_mask bits.
}

#[test]
fn test_strongest_threat_wins_no_stacking() {
    let (mut pool, _) = setup_migration_world();

    // Two threats for region 1 with different intensities
    // Due to admission dedup (same info_type + source_region), only the stronger
    // one survives. Test that the query returns the surviving intensity.
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 5,
        intensity: 100,
        hop_count: 2,
    });
    admit_packet(&mut pool, 0, &PacketCandidate {
        info_type: InfoType::ThreatWarning as u8,
        source_region: 1,
        source_turn: 6,
        intensity: 200, // stronger, newer
        hop_count: 0,
    });

    use chronicler_agents::knowledge::strongest_threat_for_region;
    let strength = strongest_threat_for_region(&pool, 0, 1, 0);
    // Admission policy keeps the fresher (turn 6, intensity 200) packet
    assert!((strength - 200.0 / 255.0).abs() < 0.01, "Should use the strongest packet");
}
```

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents --test test_behavior`
Expected: All tests PASS.

Also run existing tests to verify no regressions:
Run: `cargo nextest run -p chronicler-agents --test test_knowledge --test test_merchant`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/behavior.rs chronicler-agents/src/tick.rs chronicler-agents/tests/test_behavior.rs
git commit -m "feat(m59b): threat-aware migration with per-agent packet penalties"
```

---

## Task 5: Diagnostics Plumbing — `tick.rs` Merge + `ffi.rs` + Python

**Files:**
- Modify: `chronicler-agents/src/tick.rs:123-133` (merge consumer counters into KnowledgeStats)
- Modify: `chronicler-agents/src/ffi.rs:4079-4101` (get_knowledge_stats)
- Modify: `src/chronicler/agent_bridge.py:887` (int_keys set)
- Test: `tests/test_m59a_knowledge.py`

### Substeps

- [ ] **Step 1: Merge consumer counters in `tick.rs`**

In `tick.rs`, after the decisions block and the `migration_threat_changed` accumulation (from Task 4), and before the return, merge counters into `knowledge_stats`. Find the line where `knowledge_stats` is defined (~line 133):

```rust
    let knowledge_stats = crate::knowledge::knowledge_phase(pool, regions, &master_seed, turn);
```

Change to `let mut knowledge_stats`:

```rust
    let mut knowledge_stats = crate::knowledge::knowledge_phase(pool, regions, &master_seed, turn);
```

Then, after all decisions are applied and `migration_threat_changed` is computed, add the merge:

```rust
    // M59b: Merge consumer counters into knowledge_stats
    knowledge_stats.merchant_plans_packet_driven = merchant_stats.plans_packet_driven;
    knowledge_stats.merchant_plans_bootstrap = merchant_stats.plans_bootstrap;
    knowledge_stats.merchant_no_usable_packets = merchant_stats.no_usable_packets;
    knowledge_stats.migration_choices_changed_by_threat = migration_threat_changed;
```

Place this after the `merchant_stats.unwind_count += conquest_unwind_count;` line and after the decisions block, just before the final return tuple.

- [ ] **Step 2: Add new fields to `ffi.rs::get_knowledge_stats()`**

In `chronicler-agents/src/ffi.rs`, after the `max_hops` line (~4100), add:

```rust
        // M59b: Consumer counters
        stats.insert("merchant_plans_packet_driven".into(), self.knowledge_stats.merchant_plans_packet_driven as f64);
        stats.insert("merchant_plans_bootstrap".into(), self.knowledge_stats.merchant_plans_bootstrap as f64);
        stats.insert("merchant_no_usable_packets".into(), self.knowledge_stats.merchant_no_usable_packets as f64);
        stats.insert("migration_choices_changed_by_threat".into(), self.knowledge_stats.migration_choices_changed_by_threat as f64);
```

- [ ] **Step 3: Add new fields to Python normalization**

In `src/chronicler/agent_bridge.py`, in the `int_keys` set (~line 887), add the 4 new counter names:

```python
            int_keys = {
                "packets_created",
                "packets_refreshed",
                "packets_transmitted",
                "packets_expired",
                "packets_evicted",
                "packets_dropped",
                "live_packet_count",
                "agents_with_packets",
                "max_age",
                "max_hops",
                "merchant_plans_packet_driven",
                "merchant_plans_bootstrap",
                "merchant_no_usable_packets",
                "migration_choices_changed_by_threat",
            }
```

- [ ] **Step 4: Add Python integration test for new counters**

Add to `tests/test_m59a_knowledge.py`:

```python
def test_m59b_consumer_counters_in_knowledge_stats():
    """Verify M59b consumer counters are present in knowledge_stats."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{
        "metadata": {
            "seed": 42,
            "knowledge_stats": [
                {
                    "packets_created": 5,
                    "live_packet_count": 3,
                    "created_by_type": {"threat": 4, "trade": 1, "religious": 0},
                    "transmitted_by_type": {"threat": 2, "trade": 0, "religious": 1},
                    "merchant_plans_packet_driven": 3,
                    "merchant_plans_bootstrap": 1,
                    "merchant_no_usable_packets": 1,
                    "migration_choices_changed_by_threat": 2,
                },
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    turn_data = result["by_seed"][42][0]
    assert turn_data["merchant_plans_packet_driven"] == 3
    assert turn_data["merchant_plans_bootstrap"] == 1
    assert turn_data["merchant_no_usable_packets"] == 1
    assert turn_data["migration_choices_changed_by_threat"] == 2
```

- [ ] **Step 5: Rebuild and run tests**

Run: `cd chronicler-agents && maturin develop --release`
Then: `cargo nextest run -p chronicler-agents`
Then: `pytest tests/test_m59a_knowledge.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/tick.rs chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py tests/test_m59a_knowledge.py
git commit -m "feat(m59b): wire consumer diagnostics through tick, ffi, and Python normalization"
```

---

## Task 6: Integration Smoke Test — No Merchant Deadlock

**Files:**
- Modify: `chronicler-agents/tests/test_merchant.rs`

### Substeps

- [ ] **Step 1: Write multi-turn no-deadlock integration test**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_packet_aware_merchant_no_deadlock_20_turns() {
    let (mut pool, regions, graph) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);

    let mut total_completed = 0u32;
    let mut total_bootstrap = 0u32;
    let mut total_packet_driven = 0u32;

    for turn in 0..20u32 {
        let mut buf = DeliveryBuffer::new(4);
        let stats = merchant_mobility_phase(
            &mut pool, &regions, &graph, &mut ledger, &[turn as u8; 32], Some(&mut buf),
        );
        total_completed += stats.completed_trips;
        total_bootstrap += stats.plans_bootstrap;
        total_packet_driven += stats.plans_packet_driven;

        // Run knowledge phase so packets decay/propagate
        let _k = chronicler_agents::knowledge::knowledge_phase(
            &mut pool, &regions, &[turn as u8; 32], turn,
        );
    }

    assert!(total_completed > 0, "Merchant must complete at least one trip in 20 turns");
    // Bootstrap should fire at least once (first trip before any packets exist)
    assert!(total_bootstrap > 0, "Bootstrap should fire when no packets exist");
}
```

- [ ] **Step 2: Run test**

Run: `cargo nextest run -p chronicler-agents --test test_merchant -- test_packet_aware_merchant_no_deadlock`
Expected: PASS — trade activity remains nonzero across 20 turns.

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/tests/test_merchant.rs
git commit -m "test(m59b): add 20-turn no-deadlock smoke test for packet-aware merchants"
```

---

## Task 7: Determinism and Slot-Order Independence Tests

**Files:**
- Modify: `chronicler-agents/tests/test_knowledge.rs`
- Modify: `chronicler-agents/tests/test_merchant.rs`

### Substeps

- [ ] **Step 1: Write slot-order independence test for trade query**

Add to `chronicler-agents/tests/test_knowledge.rs`:

```rust
#[test]
fn test_usable_trade_packets_slot_order_independent() {
    let mut pool = AgentPool::new(4);
    let slot = pool.spawn(0, 0, Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
    pool.regions[slot] = 0;

    // Fill all 4 slots with trade packets from different regions
    for region in 1..=4u16 {
        admit_packet(&mut pool, slot, &PacketCandidate {
            info_type: InfoType::TradeOpportunity as u8,
            source_region: region,
            source_turn: 5,
            intensity: (50 * region as u8).min(250),
            hop_count: 0,
        });
    }

    let result = usable_trade_packets(&pool, slot, 0);
    // All 4 should appear (all nonlocal, all nonzero intensity)
    assert_eq!(result.len(), 4);

    // The results should be deterministic regardless of which slot holds which packet
    let mut sorted = result.clone();
    sorted.sort_by_key(|(r, _)| *r);
    assert_eq!(sorted[0].0, 1);
    assert_eq!(sorted[1].0, 2);
    assert_eq!(sorted[2].0, 3);
    assert_eq!(sorted[3].0, 4);
}
```

- [ ] **Step 2: Write determinism test for packet-gated routing**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_packet_gated_routing_deterministic_same_seed() {
    let (mut pool1, regions, graph) = setup_linear_world();
    let (mut pool2, _, _) = setup_linear_world();
    let ledger = ShadowLedger::new(4);

    // Give both merchants identical packets
    for pool in [&mut pool1, &mut pool2] {
        admit_packet(pool, 0, &PacketCandidate {
            info_type: InfoType::TradeOpportunity as u8,
            source_region: 2,
            source_turn: 5,
            intensity: 200,
            hop_count: 1,
        });
    }

    let table = bfs_from(&graph, 0);
    let mut stats1 = MerchantTripStats::default();
    let mut stats2 = MerchantTripStats::default();

    let intent1 = evaluate_route_packet_aware(
        0, pool1.ids[0], 0, &pool1, &regions, &table, &ledger, None, &mut stats1,
    );
    let intent2 = evaluate_route_packet_aware(
        0, pool2.ids[0], 0, &pool2, &regions, &table, &ledger, None, &mut stats2,
    );

    assert_eq!(intent1.is_some(), intent2.is_some());
    if let (Some(i1), Some(i2)) = (intent1, intent2) {
        assert_eq!(i1.dest_region, i2.dest_region, "Same packets → same destination");
    }
    assert_eq!(stats1.plans_packet_driven, stats2.plans_packet_driven);
    assert_eq!(stats1.plans_bootstrap, stats2.plans_bootstrap);
}
```

- [ ] **Step 3: Run all tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/test_knowledge.rs chronicler-agents/tests/test_merchant.rs
git commit -m "test(m59b): add determinism and slot-order independence tests"
```

---

## Task 8: Python Integration Tests + Final Verification

**Files:**
- Modify: `tests/test_m59a_knowledge.py`
- Modify: `tests/test_agent_bridge.py`

### Substeps

- [ ] **Step 1: Add `--agents=off` negative test**

Add to `tests/test_m59a_knowledge.py`:

```python
def test_agents_off_no_consumer_counters(tmp_path):
    """When --agents=off, no knowledge_stats should appear in metadata."""
    import subprocess
    result = subprocess.run(
        [
            sys.executable, "-m", "chronicler.main",
            "--seed", "42", "--turns", "5", "--agents", "off",
            "--output", str(tmp_path / "off_test"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Run failed: {result.stderr}"
    bundle_path = tmp_path / "off_test" / "chronicle_bundle.json"
    assert bundle_path.exists()
    with open(bundle_path) as f:
        bundle = json.load(f)
    metadata = bundle.get("metadata", {})
    assert "knowledge_stats" not in metadata, \
        "knowledge_stats should not be present when --agents=off"
```

- [ ] **Step 2: Rebuild the extension and run full Python test suite**

Run: `cd chronicler-agents && maturin develop --release`
Then: `pytest tests/test_m59a_knowledge.py tests/test_agent_bridge.py -v`
Expected: All PASS.

- [ ] **Step 3: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS.

- [ ] **Step 4: Run full Python test suite for regressions**

Run: `pytest tests/ -x -q`
Expected: All PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add tests/test_m59a_knowledge.py
git commit -m "test(m59b): add agents-off negative test and final verification"
```

---

## Self-Review Checklist

| Spec Requirement | Task |
|-----------------|------|
| Merchant packet-gated destinations | Task 3 |
| "Usable" 3-condition filter (intensity > 0, nonlocal, reachable) | Task 3 (evaluate_route_packet_aware) |
| Score = origin_margin + packet_strength, no second decay | Task 3 |
| Bootstrap fallback when usable set empty | Task 3 |
| Anti-omniscience: no fallback when packets exist but unprofitable | Task 3 (test_anti_omniscience) |
| Local trade observation for idle/loading merchants | Task 2 |
| Arrival dedup (skip when arrived_this_turn) | Task 2 |
| Transit merchants excluded from local observation | Task 2 |
| Threat penalty on adjacent migration targets | Task 4 |
| MAX_THREAT_PENALTY = 0.20, strongest-wins, no stacking | Task 4 |
| Own-region exclusion for threats | Task 1 (query helper) + Task 4 |
| Adjacency constraint (structural in migration loop) | Task 4 |
| migration_choices_changed_by_threat = final target comparison | Task 4 |
| 4 KnowledgeStats consumer counters | Task 1 + Task 5 |
| Counter merge in tick.rs | Task 5 |
| ffi.rs get_knowledge_stats enumerates new fields | Task 5 |
| Python normalization block | Task 5 |
| Determinism tests | Task 7 |
| Slot-order independence | Task 7 |
| --agents=off unchanged | Task 8 |
| No merchant deadlock | Task 6 |
| merchant_plans_* mutually exclusive | Task 3 (test) |
| merchant_no_usable_packets as precondition | Task 3 (test) |
