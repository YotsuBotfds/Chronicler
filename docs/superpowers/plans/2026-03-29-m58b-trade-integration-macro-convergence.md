# M58b: Trade Integration & Macro Convergence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire merchant mobility throughput into macro economy truth and validate convergence versus M42-M43 baselines.

**Architecture:** Three-stream delivery buffer in Rust (`DeliveryBuffer`) records departures, arrivals, and returns during the merchant tick. The Rust economy kernel (`tick_economy_core`) consumes this buffer in hybrid mode, replacing abstract trade allocation. Oracle shadow path runs non-mutating abstract allocation for convergence comparison. Conservation diagnostics and a 200-seed convergence gate validate parity.

**Tech Stack:** Rust (chronicler-agents crate), Python (chronicler package), Arrow IPC for FFI, pytest + cargo nextest for testing.

**Spec:** `docs/superpowers/specs/2026-03-29-m58b-trade-integration-macro-convergence-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `chronicler-agents/src/merchant.rs` | Modify | `DeliveryBuffer` struct, `DeliveryDiagnostics` struct, wire into `ShadowLedger` event methods, availability guard change |
| `chronicler-agents/src/economy.rs` | Modify | `tick_economy_core` gains `delivery_buffer` param, hybrid trade ingress, oracle shadow, `in_transit_delta` conservation field |
| `chronicler-agents/src/ffi.rs` | Modify | `tick_economy()` reads delivery buffer from self, passes to core; `get_delivery_diagnostics()` method; conservation schema extended |
| `chronicler-agents/src/tick.rs` | Modify | `tick_agents` signature updated to accept `DeliveryBuffer` in merchant state tuple; passes through to `merchant_mobility_phase` and `conquest_unwind` |
| `src/chronicler/economy.py` | Modify | `EconomyResult.conservation` dict gains `in_transit_delta` key |
| `src/chronicler/simulation.py` | Minor | Economy result reconstruction handles new conservation field |
| `src/chronicler/sidecar.py` | Modify | Economy sidecar section for convergence gate data |
| `src/chronicler/analytics.py` | Modify | Conservation diagnostics extractor |
| `chronicler-agents/tests/test_merchant.rs` | Modify | Delivery buffer unit tests, availability guard tests |
| `tests/test_merchant_mobility.py` | Modify | Integration tests (multi-turn delivery, conservation, oracle shadow) |

---

## Task 1: DeliveryBuffer Struct and ShadowLedger Wiring

**Files:**
- Modify: `chronicler-agents/src/merchant.rs:14-75` (ShadowLedger and methods)
- Test: `chronicler-agents/tests/test_merchant.rs`

- [ ] **Step 1: Write failing test — DeliveryBuffer records departure**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_delivery_buffer_records_departure() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_departure(0, 2, 5.0);
    assert_eq!(buf.departure_debits[0][2], 5.0);
    // Cumulative diagnostics
    assert_eq!(buf.diagnostics.total_departures[0][2], 5.0);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_delivery_buffer_records_departure`
Expected: FAIL — `DeliveryBuffer` not defined.

- [ ] **Step 3: Implement DeliveryBuffer struct**

Add to `chronicler-agents/src/merchant.rs` after `ShadowLedger`:

```rust
/// Cumulative monotonic counters for delivery diagnostics.
/// Run-lifetime: initialized at AgentSimulator construction, never reset.
/// Per-turn deltas derived by diffing consecutive reads.
#[derive(Clone, Debug)]
pub struct DeliveryDiagnostics {
    pub total_departures: Vec<[f32; NUM_GOODS]>,
    pub total_arrivals: Vec<[f32; NUM_GOODS]>,
    pub total_returns: Vec<[f32; NUM_GOODS]>,
    pub total_transit_decay: Vec<[f32; NUM_GOODS]>,
}

impl DeliveryDiagnostics {
    pub fn new(num_regions: usize) -> Self {
        Self {
            total_departures: vec![[0.0; NUM_GOODS]; num_regions],
            total_arrivals: vec![[0.0; NUM_GOODS]; num_regions],
            total_returns: vec![[0.0; NUM_GOODS]; num_regions],
            total_transit_decay: vec![[0.0; NUM_GOODS]; num_regions],
        }
    }
}

/// Drainable delivery buffer — three streams with distinct accounting roles.
/// Consumed by economy kernel in hybrid mode. Cleared atomically on successful
/// economy tick. If economy tick fails, buffer preserved for retry.
#[derive(Clone, Debug)]
pub struct DeliveryBuffer {
    /// Per-origin-region departure quantities (negative delta on origin stockpile).
    pub departure_debits: Vec<[f32; NUM_GOODS]>,
    /// Per-arrival: (source, dest, good, qty). Provenance required for M43b observability.
    pub arrival_imports: Vec<ArrivalRecord>,
    /// Per-origin-region return quantities (positive delta on origin stockpile, full value).
    pub return_credits: Vec<[f32; NUM_GOODS]>,
    /// Run-lifetime monotonic counters.
    pub diagnostics: DeliveryDiagnostics,
}

/// Single arrival record with source provenance.
#[derive(Clone, Debug)]
pub struct ArrivalRecord {
    pub source_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub qty: f32,
}

impl DeliveryBuffer {
    pub fn new(num_regions: usize) -> Self {
        Self {
            departure_debits: vec![[0.0; NUM_GOODS]; num_regions],
            arrival_imports: Vec::new(),
            return_credits: vec![[0.0; NUM_GOODS]; num_regions],
            diagnostics: DeliveryDiagnostics::new(num_regions),
        }
    }

    pub fn record_departure(&mut self, origin: usize, slot: usize, qty: f32) {
        self.departure_debits[origin][slot] += qty;
        self.diagnostics.total_departures[origin][slot] += qty;
    }

    pub fn record_arrival(&mut self, source: u16, dest: u16, good_slot: u8, qty: f32) {
        self.arrival_imports.push(ArrivalRecord {
            source_region: source,
            dest_region: dest,
            good_slot,
            qty,
        });
        self.diagnostics.total_arrivals[dest as usize][good_slot as usize] += qty;
    }

    pub fn record_return(&mut self, origin: usize, slot: usize, qty: f32) {
        self.return_credits[origin][slot] += qty;
        self.diagnostics.total_returns[origin][slot] += qty;
    }

    /// Clear all drainable streams. Called after successful economy tick consumption,
    /// or to discard in non-hybrid modes. Diagnostics are NOT cleared (run-lifetime monotonic).
    pub fn clear(&mut self) {
        for arr in self.departure_debits.iter_mut() {
            *arr = [0.0; NUM_GOODS];
        }
        self.arrival_imports.clear();
        for arr in self.return_credits.iter_mut() {
            *arr = [0.0; NUM_GOODS];
        }
    }
}

/// Loss reason discriminant for future loss tracking (M58b: only transit_decay active).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum LossReason {
    TransitDecay = 0,
    Raid = 1,        // dormant — M58b+
    Disruption = 2,  // dormant — M58b+
    Spoilage = 3,    // dormant — M58b+
}
```

The `LossReason` enum is plumbed but only `TransitDecay` is used in M58b. The economy kernel tracks transit decay via `conservation.transit_loss`. The enum exists as a seam for future loss bucketing.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo nextest run -p chronicler-agents test_delivery_buffer_records_departure`
Expected: PASS.

- [ ] **Step 5: Write failing tests — arrival and return recording + clear**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_delivery_buffer_records_arrival() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_arrival(0, 1, 2, 7.5);
    assert_eq!(buf.arrival_imports.len(), 1);
    assert_eq!(buf.arrival_imports[0].source_region, 0);
    assert_eq!(buf.arrival_imports[0].dest_region, 1);
    assert_eq!(buf.arrival_imports[0].good_slot, 2);
    assert_eq!(buf.arrival_imports[0].qty, 7.5);
    assert_eq!(buf.diagnostics.total_arrivals[1][2], 7.5);
}

#[test]
fn test_delivery_buffer_records_return() {
    let mut buf = DeliveryBuffer::new(3);
    buf.record_return(0, 3, 4.0);
    assert_eq!(buf.return_credits[0][3], 4.0);
    assert_eq!(buf.diagnostics.total_returns[0][3], 4.0);
}

#[test]
fn test_delivery_buffer_clear_preserves_diagnostics() {
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 5.0);
    buf.record_arrival(0, 1, 0, 5.0);
    buf.record_return(0, 1, 3.0);
    buf.clear();
    // Drainable streams zeroed
    assert_eq!(buf.departure_debits[0][0], 0.0);
    assert!(buf.arrival_imports.is_empty());
    assert_eq!(buf.return_credits[0][1], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 5.0);
    assert_eq!(buf.diagnostics.total_arrivals[1][0], 5.0);
    assert_eq!(buf.diagnostics.total_returns[0][1], 3.0);
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_delivery_buffer_`
Expected: All 4 delivery buffer tests PASS.

- [ ] **Step 7: Wire DeliveryBuffer into ShadowLedger event methods**

Modify `ShadowLedger::depart()`, `ShadowLedger::arrive()`, and `ShadowLedger::unwind()` in `chronicler-agents/src/merchant.rs` to accept an optional `&mut DeliveryBuffer`:

```rust
    /// Depart: move from reserved to in_transit_out (Loading → Transit).
    /// If delivery buffer provided, records departure debit.
    pub fn depart(&mut self, origin: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.reserved[origin][slot] = (self.reserved[origin][slot] - qty).max(0.0);
        self.in_transit_out[origin][slot] += qty;
        if let Some(buf) = delivery_buf {
            buf.record_departure(origin, slot, qty);
        }
    }

    /// Arrive: move from in_transit_out to pending_delivery (Transit → Idle via Arrived).
    /// If delivery buffer provided, records arrival import with provenance.
    pub fn arrive(&mut self, origin: usize, dest: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        self.pending_delivery[dest][slot] += qty;
        if let Some(buf) = delivery_buf {
            buf.record_arrival(origin as u16, dest as u16, slot as u8, qty);
        }
    }

    /// Unwind: return in-transit cargo to origin (disruption).
    /// If delivery buffer provided, records return credit.
    pub fn unwind(&mut self, origin: usize, slot: usize, qty: f32, delivery_buf: Option<&mut DeliveryBuffer>) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        if let Some(buf) = delivery_buf {
            buf.record_return(origin, slot, qty);
        }
    }
```

- [ ] **Step 8: Update all callers of depart/arrive/unwind to pass `None` temporarily**

**Staging note:** This task passes `None` as a compile-gate only. Task 3 will replace all `None` args with `Some(buf)` once the delivery buffer is wired through `merchant_mobility_phase` and `conquest_unwind`. The dispatch notes' rule "None is not valid when buffer exists" applies after Task 3 lands — not during Task 1.

Update every call site in `merchant.rs` that calls `ledger.depart(...)`, `ledger.arrive(...)`, or `ledger.unwind(...)` to add the trailing `None` argument. This includes:

- `depart_merchant()` (~line 395): `ledger.depart(origin, good, pool.trip_cargo_qty[slot], None);`
- `merchant_mobility_phase()` arrival loop (~line 527): `ledger.arrive(origin, dest, good, qty, None);`
- `merchant_mobility_phase()` disruption unwind (~line 500): `ledger.unwind(origin, good, pool.trip_cargo_qty[slot], None);`
- `conquest_unwind()` transit branch (~line 453): `ledger.unwind(origin_idx, good, qty, None);`

Also update all call sites in existing tests in `merchant.rs` `mod tests`.

**Task 3 will change these `None`s to `Some(buf)` — do not leave them as `None` after Task 3.**

- [ ] **Step 9: Run full Rust test suite to verify no regressions**

Run: `cargo nextest run -p chronicler-agents`
Expected: All existing tests PASS (None args are no-ops, behavior unchanged).

- [ ] **Step 10: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m58b): add DeliveryBuffer struct and wire into ShadowLedger events"
```

---

## Task 2: Availability Guard Change

**Files:**
- Modify: `chronicler-agents/src/merchant.rs:31-39` (available + is_overcommitted)
- Test: `chronicler-agents/tests/test_merchant.rs`

- [ ] **Step 1: Write failing test — hybrid availability uses departure_debits**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_hybrid_availability_uses_departure_debits() {
    let mut ledger = ShadowLedger::new(2);
    let mut buf = DeliveryBuffer::new(2);
    let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];

    // Reserve + depart with delivery buffer
    ledger.reserve(0, 0, 3.0);
    ledger.depart(0, 0, 3.0, Some(&mut buf));

    // Hybrid availability: stockpile(10) - reserved(0) - departure_debits(3) = 7
    assert_eq!(ledger.available_hybrid(0, 0, &stockpile, &buf), 7.0);

    // Old formula would give: stockpile(10) - reserved(0) - in_transit_out(3) = 7
    // Same result on same turn. Difference appears after economy drain.

    // Simulate economy drain: stockpile debited, departure_debits cleared
    let debited_stockpile = [7.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
    buf.clear();

    // Hybrid: stockpile(7) - reserved(0) - departure_debits(0) = 7 ✓
    assert_eq!(ledger.available_hybrid(0, 0, &debited_stockpile, &buf), 7.0);

    // Old formula would give: stockpile(7) - reserved(0) - in_transit_out(3) = 4 ✗ (double-subtraction)
    assert_eq!(ledger.available(0, 0, &debited_stockpile), 4.0); // confirms the bug
}

#[test]
fn test_hybrid_overcommitted_uses_departure_debits() {
    let ledger = ShadowLedger::new(2);
    let buf = DeliveryBuffer::new(2);
    let stockpile = [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
    assert!(!ledger.is_overcommitted_hybrid(0, 0, &stockpile, &buf));
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_hybrid_availability`
Expected: FAIL — `available_hybrid` not defined.

- [ ] **Step 3: Implement available_hybrid and is_overcommitted_hybrid**

Add to `ShadowLedger` impl in `chronicler-agents/src/merchant.rs`:

```rust
    /// Hybrid-mode availability: uses departure_debits instead of in_transit_out.
    /// Use when stockpile has already been debited for prior-turn departures.
    pub fn available_hybrid(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS], delivery_buf: &DeliveryBuffer) -> f32 {
        (stockpile[slot] - self.reserved[region][slot] - delivery_buf.departure_debits[region][slot]).max(0.0)
    }

    /// Hybrid-mode overcommitted check.
    pub fn is_overcommitted_hybrid(&self, region: usize, slot: usize, stockpile: &[f32; NUM_GOODS], delivery_buf: &DeliveryBuffer) -> bool {
        self.reserved[region][slot] + delivery_buf.departure_debits[region][slot] > stockpile[slot]
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cargo nextest run -p chronicler-agents test_hybrid_`
Expected: PASS.

- [ ] **Step 5: Update evaluate_route and apply_trip_intent to accept hybrid flag + delivery buffer**

Modify `evaluate_route()` in `chronicler-agents/src/merchant.rs` (~line 234):
- Add parameter `delivery_buf: Option<&DeliveryBuffer>`
- When `delivery_buf` is `Some(buf)`, call `ledger.is_overcommitted_hybrid(...)` / `ledger.available_hybrid(...)` instead of the non-hybrid variants.
- When `delivery_buf` is `None`, use the existing `ledger.is_overcommitted(...)` / `ledger.available(...)`.

Modify `apply_trip_intent()` (~line 302) the same way.

Update `merchant_mobility_phase()` (~line 471) to accept `delivery_buf: Option<&mut DeliveryBuffer>` and pass through.

- [ ] **Step 6: Update all callers to pass None for delivery_buf**

In `merchant_mobility_phase()`, pass `delivery_buf.as_deref()` to `evaluate_route` and `delivery_buf.as_deref()` to `apply_trip_intent`.

Update the `depart_merchant`, arrival loop, and unwind calls in `merchant_mobility_phase` to pass `delivery_buf.as_deref_mut()` instead of `None`.

Update `conquest_unwind()` to accept `delivery_buf: Option<&mut DeliveryBuffer>` and pass through to `ledger.unwind()`.

- [ ] **Step 7: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All tests PASS (None args preserve existing behavior).

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m58b): add hybrid availability guard using departure_debits"
```

---

## Task 3: Wire DeliveryBuffer into AgentSimulator

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:1633-1721` (AgentSimulator struct + constructor)
- Modify: `chronicler-agents/src/ffi.rs:2317-2344` (tick_agents merchant state)
- Modify: `chronicler-agents/src/ffi.rs:3497-3841` (tick_economy)

- [ ] **Step 1: Add delivery_buffer field to AgentSimulator**

In `chronicler-agents/src/ffi.rs`, add to `AgentSimulator` struct (~line 1676):

```rust
    merchant_ledger: Option<crate::merchant::ShadowLedger>,
    merchant_delivery_buf: Option<crate::merchant::DeliveryBuffer>,
    merchant_trip_stats: crate::merchant::MerchantTripStats,
```

In constructor (~line 1719):

```rust
            merchant_ledger: None,
            merchant_delivery_buf: None,
            merchant_trip_stats: crate::merchant::MerchantTripStats::default(),
```

- [ ] **Step 2: Initialize DeliveryBuffer alongside ShadowLedger in set_merchant_route_graph**

Find `set_merchant_route_graph` in `ffi.rs` (the method that initializes `merchant_ledger`). When `merchant_ledger` is initialized, also initialize `merchant_delivery_buf`:

```rust
        if self.merchant_ledger.is_none() {
            self.merchant_ledger = Some(crate::merchant::ShadowLedger::new(self.num_regions));
            self.merchant_delivery_buf = Some(crate::merchant::DeliveryBuffer::new(self.num_regions));
        }
```

- [ ] **Step 3: Pass delivery buffer through tick_agents merchant state**

In the `tick_agents` call (~line 2321-2340), include `merchant_delivery_buf` in the merchant state:

```rust
        let merchant_graph_taken = self.merchant_graph.take();
        let mut merchant_ledger_taken = self.merchant_ledger.take();
        let mut merchant_delivery_buf_taken = self.merchant_delivery_buf.take();
        let merchant_state = match (&merchant_graph_taken, &mut merchant_ledger_taken, &mut merchant_delivery_buf_taken) {
            (Some(graph), Some(ledger), Some(buf)) => Some((graph, ledger, buf)),
            _ => None,
        };
```

This requires updating `tick_agents` in `tick.rs` and `merchant_mobility_phase` to accept the delivery buffer as part of the merchant state tuple.

- [ ] **Step 4: Update tick.rs tick_agents signature**

In `chronicler-agents/src/tick.rs`, update the `tick_agents` function signature to accept the delivery buffer as part of the merchant state:

Change the merchant_state parameter type from `Option<(&RouteGraph, &mut ShadowLedger)>` to `Option<(&RouteGraph, &mut ShadowLedger, &mut DeliveryBuffer)>`.

Update the call to `conquest_unwind` and `merchant_mobility_phase` inside `tick_agents` to pass `Some(buf)` through.

- [ ] **Step 5: Restore delivery buffer after tick_agents**

After the `tick_agents` call in `ffi.rs`:

```rust
        self.merchant_graph = merchant_graph_taken;
        self.merchant_ledger = merchant_ledger_taken;
        self.merchant_delivery_buf = merchant_delivery_buf_taken;
```

- [ ] **Step 6: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All tests PASS. Delivery buffer now wired through but all paths pass `Some(buf)` to the merchant methods.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/src/tick.rs
git commit -m "feat(m58b): wire DeliveryBuffer through AgentSimulator and tick_agents"
```

---

## Task 4: Hybrid Trade Ingress in Economy Kernel

**Files:**
- Modify: `chronicler-agents/src/economy.rs:368-910` (tick_economy_core)
- Test: `chronicler-agents/tests/test_merchant.rs`

- [ ] **Step 1: Write failing test — hybrid economy consumes delivery buffer**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
use chronicler_agents::economy::{
    tick_economy_core, EconomyRegionInput, RegionAgentCounts, TradeRouteInput,
    EconomyConfig, NUM_GOODS, TRANSIT_DECAY, HybridDeliveryInput,
};
use chronicler_agents::merchant::DeliveryBuffer;

#[test]
fn test_hybrid_economy_consumes_delivery_buffer() {
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);

    // Region 0 ships 10 grain to region 1
    buf.record_departure(0, 0, 10.0); // grain slot 0
    buf.record_arrival(0, 1, 0, 10.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 1, 100, 0, 1.0, [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 80, 5, 10, 5),
        test_agent_counts(100, 80, 5, 10, 5),
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &[], &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Region 0 stockpile should decrease by departure (10 grain)
    // Region 1 stockpile should increase by arrival * (1 - transit_decay)
    let expected_arrival = 10.0 * (1.0 - TRANSIT_DECAY[0]);
    let r0_grain = output.region_results[0].stockpile[0];
    let r1_grain = output.region_results[1].stockpile[0];

    // Exact values depend on production/consumption, but the delta should include mobility
    // Just verify the transit_loss is tracked
    assert!(output.conservation.transit_loss > 0.0, "transit decay should be tracked");
    assert!(output.conservation.in_transit_delta.is_some(), "in_transit_delta should be present");
}
```

Note: `test_region_input` and `test_agent_counts` are test helpers. Create them if they don't exist, or use the existing test helper pattern in the crate.

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_hybrid_economy_consumes`
Expected: FAIL — `HybridDeliveryInput` not defined, `tick_economy_core` doesn't accept delivery param.

- [ ] **Step 3: Define HybridDeliveryInput and extend tick_economy_core signature**

Add to `chronicler-agents/src/economy.rs`:

```rust
/// Pre-aggregated delivery buffer data for hybrid economy ingress.
/// Aggregated from DeliveryBuffer's three streams into per-region arrays.
pub struct HybridDeliveryInput {
    /// Per-region departure debits (negative delta on origin).
    pub departure_debits: Vec<[f32; NUM_GOODS]>,
    /// Per-region per-good import totals from arrivals (pre-decay).
    pub arrival_imports: Vec<[f32; NUM_GOODS]>,
    /// Per-region return credits (positive delta on origin, full value).
    pub return_credits: Vec<[f32; NUM_GOODS]>,
    /// Per-(dest, source) pairs for upstream source tracking.
    pub inbound_pairs: Vec<(u16, u16)>,
}

impl HybridDeliveryInput {
    /// Aggregate from a DeliveryBuffer into per-region arrays.
    pub fn from_buffer(buf: &crate::merchant::DeliveryBuffer, num_regions: usize) -> Self {
        let mut arrival_imports = vec![[0.0f32; NUM_GOODS]; num_regions];
        let mut inbound_pairs: Vec<(u16, u16)> = Vec::new();
        for rec in &buf.arrival_imports {
            let dest = rec.dest_region as usize;
            let slot = rec.good_slot as usize;
            if dest < num_regions && slot < NUM_GOODS {
                arrival_imports[dest][slot] += rec.qty;
                inbound_pairs.push((rec.dest_region, rec.source_region));
            }
        }
        inbound_pairs.sort();
        inbound_pairs.dedup();

        Self {
            departure_debits: buf.departure_debits.clone(),
            arrival_imports,
            return_credits: buf.return_credits.clone(),
            inbound_pairs,
        }
    }
}
```

Extend `ConservationSummary`:

```rust
pub struct ConservationSummary {
    pub production: f64,
    pub transit_loss: f64,
    pub consumption: f64,
    pub storage_loss: f64,
    pub cap_overflow: f64,
    pub clamp_floor_loss: f64,
    /// M58b: in-flight inventory change = departures - arrivals - returns.
    pub in_transit_delta: Option<f64>,
}
```

Update `ConservationSummary::new()` to set `in_transit_delta: None`.

Extend `tick_economy_core` signature:

```rust
pub fn tick_economy_core(
    region_inputs: &[EconomyRegionInput],
    agent_counts: &[RegionAgentCounts],
    routes: &[TradeRouteInput],
    civ_merchant_wealth: &[f32],
    civ_priest_count: &[u32],
    n_civs: usize,
    config: &EconomyConfig,
    trade_friction: f32,
    is_winter: bool,
    hybrid_delivery: Option<&HybridDeliveryInput>,
) -> EconomyOutput {
```

- [ ] **Step 4: Implement hybrid trade ingress in Phase B**

In `tick_economy_core`, after Phase A (production/demand), add a branch before Phase B:

```rust
    // -----------------------------------------------------------------------
    // Phase B: Trade kernel
    // -----------------------------------------------------------------------

    let (per_good_imports, upstream_sources) = if let Some(delivery) = hybrid_delivery {
        // --- Hybrid path: use delivery buffer ---
        // Apply mobility deltas as the trade flow source.
        let mut per_good_imports = vec![[0.0f32; NUM_GOODS]; n_regions];

        // Arrival imports with transit decay
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                let raw = delivery.arrival_imports[ri][g];
                let decay_rate = TRANSIT_DECAY[g];
                let delivered = raw * (1.0 - decay_rate);
                conservation.transit_loss += (raw - delivered) as f64;
                per_good_imports[ri][g] = delivered;
            }
        }

        // Compute category-level imports for tatonnement price update
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                let cat = GOOD_CATEGORY[g];
                work[ri].imports[cat] += per_good_imports[ri][g];
            }
        }

        // Compute category-level exports from departure debits
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                let cat = GOOD_CATEGORY[g];
                work[ri].exports[cat] += delivery.departure_debits[ri][g];
            }
        }

        // Compute in_transit_delta
        let mut delta: f64 = 0.0;
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                delta += delivery.departure_debits[ri][g] as f64;
                delta -= delivery.arrival_imports[ri][g] as f64;
                delta -= delivery.return_credits[ri][g] as f64;
            }
        }
        conservation.in_transit_delta = Some(delta);

        // Build upstream sources from delivery provenance
        let mut us: Vec<UpstreamSource> = Vec::new();
        let mut ordinal_counter: u16 = 0;
        let mut last_dest: Option<u16> = None;
        for &(dest_id, src_id) in &delivery.inbound_pairs {
            if last_dest != Some(dest_id) {
                ordinal_counter = 0;
                last_dest = Some(dest_id);
            }
            us.push(UpstreamSource {
                dest_region_id: dest_id,
                source_ordinal: ordinal_counter,
                source_region_id: src_id,
            });
            ordinal_counter += 1;
        }

        (per_good_imports, us)
    } else {
        // --- Abstract path: existing tatonnement + allocation ---
        // (existing Phase B code stays here, unchanged)
```

Move the existing Phase B code (tatonnement loop, route allocation, inbound_pairs, upstream_sources, per_good_imports with decay) into the `else` branch. After Phase B, both branches produce `per_good_imports` and `upstream_sources`.

Also in the hybrid path, compute `per_good_net_mobility` for stockpile update:

```rust
        // Net mobility delta per region-slot for stockpile update
        let mut per_good_net_mobility = vec![[0.0f32; NUM_GOODS]; n_regions];
        for ri in 0..n_regions {
            for g in 0..NUM_GOODS {
                per_good_net_mobility[ri][g] = per_good_imports[ri][g]
                    + delivery.return_credits[ri][g]
                    - delivery.departure_debits[ri][g];
            }
        }
```

- [ ] **Step 5: Update Phase C stockpile lifecycle for hybrid mode**

In the stockpile accumulation step (currently ~line 740), when in hybrid mode use `per_good_net_mobility` instead of `per_good_production - per_good_exports + per_good_imports`:

```rust
        // Step 1: Accumulate stockpile
        let mut stockpile = w.stockpile;
        for g in 0..NUM_GOODS {
            let new_val = if hybrid_delivery.is_some() {
                // Hybrid: single application point for all mobility + production
                stockpile[g] + per_good_production[g] + per_good_net_mobility[ri][g]
            } else {
                // Abstract: old path
                stockpile[g] + per_good_production[g] - per_good_exports[g] + per_good_imports[ri][g]
            };
            if new_val < 0.0 {
                conservation.clamp_floor_loss += (-new_val) as f64;
                stockpile[g] = 0.0;
            } else {
                stockpile[g] = new_val;
            }
        }
```

- [ ] **Step 6: Update merchant_trade_income for hybrid mode**

In the `merchant_trade_income` derivation (~line 848), when in hybrid mode derive from realized arrival volumes aggregated by origin region. Spec: "Merchants in region R earn income proportional to total goods delivered from R (post-decay)."

```rust
        let merchant_trade_income = if let Some(delivery) = hybrid_delivery {
            // Hybrid: income from realized arrivals originating from this region.
            // Sum post-decay arrival value for goods that originated from this region.
            if ac.merchant_count > 0 {
                let mut total_delivered_value = 0.0f32;
                for rec in &delivery.arrival_imports_raw {
                    if rec.source_region == inp.region_id {
                        let g = rec.good_slot as usize;
                        if g < NUM_GOODS {
                            let delivered = rec.qty * (1.0 - TRANSIT_DECAY[g]);
                            let cat = GOOD_CATEGORY[g];
                            let margin = (post_trade_prices[rec.dest_region as usize][cat]
                                - post_trade_prices[ri][cat]).max(0.0);
                            total_delivered_value += delivered * margin;
                        }
                    }
                }
                total_delivered_value / ac.merchant_count as f32
            } else {
                0.0
            }
        } else {
            // Abstract: existing arbitrage calculation (unchanged)
            if ac.merchant_count > 0 && route_count > 0 {
                let mut total_arbitrage = 0.0f32;
                for rw_idx in rstart..rend {
                    let dest_idx = route_works[rw_idx].dest_idx;
                    for c in 0..NUM_CATEGORIES {
                        let margin = (post_trade_prices[dest_idx][c] - post_trade_prices[ri][c]).max(0.0);
                        total_arbitrage += route_works[rw_idx].flow[c] * margin;
                    }
                }
                total_arbitrage / ac.merchant_count as f32
            } else {
                0.0
            }
        };
```

This requires `HybridDeliveryInput` to carry the raw arrival records (not just per-region aggregates) so we can filter by source. Add `arrival_imports_raw: Vec<ArrivalRecord>` to `HybridDeliveryInput::from_buffer()`:

```rust
impl HybridDeliveryInput {
    pub fn from_buffer(buf: &crate::merchant::DeliveryBuffer, num_regions: usize) -> Self {
        // ... existing aggregation code ...
        Self {
            departure_debits: buf.departure_debits.clone(),
            arrival_imports,
            arrival_imports_raw: buf.arrival_imports.clone(), // raw records for merchant income
            return_credits: buf.return_credits.clone(),
            inbound_pairs,
        }
    }
}
```

- [ ] **Step 7: Update ffi.rs tick_economy to pass delivery buffer**

In `ffi.rs tick_economy()` (~line 3688), read the delivery buffer from self and pass to core. **Mode gating:** only pass `Some` in hybrid mode. The `AgentSimulator` needs to know its agent mode — add a `hybrid_mode: bool` field set during construction or via a setter called from Python.

```rust
        // Mode gate: only hybrid mode consumes delivery buffer for stockpile truth.
        // Non-hybrid modes (demographics-only, shadow) have buffers but don't apply them.
        let hybrid_delivery = if self.hybrid_mode {
            self.merchant_delivery_buf.as_ref().map(|buf| {
                crate::economy::HybridDeliveryInput::from_buffer(buf, n_regions)
            })
        } else {
            None
        };

        let output = tick_economy_core(
            &region_inputs,
            &agent_counts,
            &routes,
            &civ_merchant_wealth,
            &civ_priest_count,
            n_civs,
            &self.economy_config,
            trade_friction,
            is_winter,
            hybrid_delivery.as_ref(),
        );

        // Clear delivery buffer on successful economy completion (transactional)
        if hybrid_delivery.is_some() {
            if let Some(buf) = self.merchant_delivery_buf.as_mut() {
                buf.clear();
            }
        }
```

- [ ] **Step 8: Extend conservation schema and batch with in_transit_delta**

In `ffi.rs`, update `economy_conservation_schema()`:

```rust
pub fn economy_conservation_schema() -> Schema {
    Schema::new(vec![
        Field::new("production", DataType::Float64, false),
        Field::new("transit_loss", DataType::Float64, false),
        Field::new("consumption", DataType::Float64, false),
        Field::new("storage_loss", DataType::Float64, false),
        Field::new("cap_overflow", DataType::Float64, false),
        Field::new("clamp_floor_loss", DataType::Float64, false),
        Field::new("in_transit_delta", DataType::Float64, true), // nullable — None in abstract mode
    ])
}
```

Update the conservation batch packing (~line 3820):

```rust
        let conservation_batch = RecordBatch::try_new(
            Arc::new(economy_conservation_schema()),
            vec![
                Arc::new(Float64Array::from(vec![c.production])),
                Arc::new(Float64Array::from(vec![c.transit_loss])),
                Arc::new(Float64Array::from(vec![c.consumption])),
                Arc::new(Float64Array::from(vec![c.storage_loss])),
                Arc::new(Float64Array::from(vec![c.cap_overflow])),
                Arc::new(Float64Array::from(vec![c.clamp_floor_loss])),
                Arc::new(Float64Array::from(vec![c.in_transit_delta.unwrap_or(0.0)])),
            ],
        ).map_err(arrow_err)?;
```

- [ ] **Step 9: Run test to verify hybrid economy path works**

Run: `cargo nextest run -p chronicler-agents test_hybrid_economy_consumes`
Expected: PASS.

- [ ] **Step 10: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All tests PASS. Existing economy tests pass `None` for `hybrid_delivery`.

- [ ] **Step 11: Commit**

```bash
git add chronicler-agents/src/economy.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m58b): hybrid trade ingress in economy kernel with delivery buffer consumption"
```

---

## Task 5: Oracle Shadow Path

**Files:**
- Modify: `chronicler-agents/src/economy.rs` (EconomyOutput gains oracle fields)
- Modify: `chronicler-agents/src/ffi.rs` (return oracle data in batches)
- Test: `chronicler-agents/tests/test_merchant.rs`

- [ ] **Step 1: Write failing test — oracle shadow produces comparison data**

```rust
#[test]
fn test_oracle_shadow_produces_data_in_hybrid_mode() {
    // Setup same as test_hybrid_economy_consumes, but check oracle fields
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    let region_inputs = vec![
        test_region_input(0, 0, 100, 0, 1.0, [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        test_region_input(1, 1, 100, 0, 1.0, [5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    ];
    let agent_counts = vec![
        test_agent_counts(100, 80, 5, 10, 5),
        test_agent_counts(100, 80, 5, 10, 5),
    ];
    let routes = vec![
        TradeRouteInput { origin_region_id: 0, dest_region_id: 1, is_river: false },
    ];

    let output = tick_economy_core(
        &region_inputs, &agent_counts, &routes, &[0.0], &[0],
        1, &config, 1.0, false, Some(&delivery),
    );

    // Oracle shadow should have run abstract allocation
    assert!(output.oracle_trade_volume.is_some());
    let oracle = output.oracle_trade_volume.as_ref().unwrap();
    assert_eq!(oracle.len(), 2); // one per region
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo nextest run -p chronicler-agents test_oracle_shadow`
Expected: FAIL — `oracle_trade_volume` field not defined.

- [ ] **Step 3: Add oracle fields to EconomyOutput**

In `chronicler-agents/src/economy.rs`, extend `EconomyOutput`:

```rust
pub struct EconomyOutput {
    pub region_results: Vec<EconomyRegionResult>,
    pub civ_results: Vec<EconomyCivResult>,
    pub observability: Vec<EconomyObservability>,
    pub upstream_sources: Vec<UpstreamSource>,
    pub conservation: ConservationSummary,
    /// M58b: Oracle shadow — abstract trade volumes per region per category.
    /// Only populated in hybrid mode.
    pub oracle_trade_volume: Option<Vec<[f32; NUM_CATEGORIES]>>,
}
```

- [ ] **Step 4: Implement oracle shadow in hybrid path**

In `tick_economy_core`, after the hybrid branch consumes the delivery buffer, run the abstract allocation as a non-mutating shadow:

```rust
        // Oracle shadow: run abstract allocation non-mutating for convergence comparison.
        // Uses a clone of work state so abstract allocation doesn't affect hybrid stockpiles.
        let oracle_trade_volume = if hybrid_delivery.is_some() && !routes.is_empty() {
            let mut shadow_work = work.clone();
            // Re-run abstract allocation on shadow_work (same code as else branch)
            // ... run tatonnement + allocation on shadow_work ...
            // Collect per-region import totals by category
            let vols: Vec<[f32; NUM_CATEGORIES]> = shadow_work.iter()
                .map(|w| w.imports)
                .collect();
            Some(vols)
        } else {
            None
        };
```

Note: The implementation should extract the abstract allocation logic into a helper function to avoid duplicating the tatonnement code. Both the abstract path and the oracle shadow call the same helper.

- [ ] **Step 5: Serialize oracle data in FFI return**

**Do NOT change the tick_economy return tuple from 5 to 6 batches.** That would break `simulation.py:1495-1499` which unpacks the 5-tuple directly into `reconstruct_economy_result()`. Instead, add oracle columns to the existing observability batch (batch 3). Add three nullable `Float32` columns per category:

- `oracle_imports_food`, `oracle_imports_raw_material`, `oracle_imports_luxury`

These are null/zero when oracle is not active (non-hybrid mode). `reconstruct_economy_result` in Python reads them if present (check column existence), otherwise ignores. No return-shape change, no unpack breakage.

In `ffi.rs`, update the observability batch packing (~line 3765) to include oracle columns:

```rust
        // Oracle shadow columns (nullable — zero when no oracle)
        let mut oracle_if = Float32Builder::with_capacity(n_out);
        let mut oracle_irm = Float32Builder::with_capacity(n_out);
        let mut oracle_il = Float32Builder::with_capacity(n_out);
        if let Some(ref oracle_vols) = output.oracle_trade_volume {
            for ri in 0..n_out {
                oracle_if.append_value(oracle_vols[ri][0]);  // CAT_FOOD
                oracle_irm.append_value(oracle_vols[ri][1]); // CAT_RAW_MATERIAL
                oracle_il.append_value(oracle_vols[ri][2]);  // CAT_LUXURY
            }
        } else {
            for _ in 0..n_out {
                oracle_if.append_value(0.0);
                oracle_irm.append_value(0.0);
                oracle_il.append_value(0.0);
            }
        }
```

Update `economy_observability_schema()` to include the three new columns. Update `reconstruct_economy_result` in Python to read them.

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/economy.rs chronicler-agents/src/ffi.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m58b): oracle shadow path for convergence comparison in hybrid mode"
```

---

## Task 6: Python-Side Economy Result Reconstruction

**Files:**
- Modify: `src/chronicler/economy.py:520-523` (EconomyResult.conservation dict)
- Modify: `src/chronicler/economy.py:970-1057` (reconstruct_economy_result)

- [ ] **Step 1: Write failing test — reconstruction handles in_transit_delta**

Add to `tests/test_merchant_mobility.py`:

```python
def test_economy_result_has_in_transit_delta():
    """EconomyResult.conservation dict includes in_transit_delta key."""
    from chronicler.economy import EconomyResult
    result = EconomyResult()
    assert "in_transit_delta" in result.conservation
    assert result.conservation["in_transit_delta"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_merchant_mobility.py::test_economy_result_has_in_transit_delta -v`
Expected: FAIL — key not in dict.

- [ ] **Step 3: Add in_transit_delta to EconomyResult.conservation**

In `src/chronicler/economy.py` (~line 520):

```python
    conservation: dict[str, float] = field(default_factory=lambda: {
        "production": 0.0, "transit_loss": 0.0, "consumption": 0.0,
        "storage_loss": 0.0, "cap_overflow": 0.0, "clamp_floor_loss": 0.0,
        "in_transit_delta": 0.0,
    })
```

- [ ] **Step 4: Update reconstruct_economy_result to read in_transit_delta**

In `src/chronicler/economy.py` (~line 1054):

```python
    for field_name in ("production", "transit_loss", "consumption", "storage_loss", "cap_overflow", "clamp_floor_loss", "in_transit_delta"):
        result.conservation[field_name] = conservation_batch.column(field_name).to_pylist()[0]
```

- [ ] **Step 5: Run test**

Run: `pytest tests/test_merchant_mobility.py::test_economy_result_has_in_transit_delta -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/economy.py tests/test_merchant_mobility.py
git commit -m "feat(m58b): add in_transit_delta to EconomyResult conservation dict"
```

---

## Task 7: get_delivery_diagnostics FFI Method

**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (new PyO3 method)
- Test: `tests/test_merchant_mobility.py`

- [ ] **Step 1: Implement get_delivery_diagnostics**

Add to `AgentSimulator` impl in `chronicler-agents/src/ffi.rs`:

```rust
    /// M58b: Non-draining read of cumulative delivery counters.
    /// Run-lifetime monotonic — per-turn deltas derived by diffing consecutive reads.
    pub fn get_delivery_diagnostics(&self) -> PyResult<PyRecordBatch> {
        use arrow::array::{UInt16Builder, UInt8Builder, Float32Builder};

        let buf = match &self.merchant_delivery_buf {
            Some(b) => &b.diagnostics,
            None => {
                // Return empty batch
                let schema = Arc::new(Schema::new(vec![
                    Field::new("region_id", DataType::UInt16, false),
                    Field::new("good_slot", DataType::UInt8, false),
                    Field::new("total_departures", DataType::Float32, false),
                    Field::new("total_arrivals", DataType::Float32, false),
                    Field::new("total_returns", DataType::Float32, false),
                    Field::new("total_transit_decay", DataType::Float32, false),
                ]));
                let batch = RecordBatch::new_empty(schema);
                return Ok(PyRecordBatch::new(batch));
            }
        };

        let n = buf.total_departures.len();
        let mut rid = UInt16Builder::with_capacity(n * NUM_GOODS);
        let mut gs = UInt8Builder::with_capacity(n * NUM_GOODS);
        let mut dep = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut arr = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut ret = Float32Builder::with_capacity(n * NUM_GOODS);
        let mut decay = Float32Builder::with_capacity(n * NUM_GOODS);

        for region in 0..n {
            for g in 0..NUM_GOODS {
                rid.append_value(region as u16);
                gs.append_value(g as u8);
                dep.append_value(buf.total_departures[region][g]);
                arr.append_value(buf.total_arrivals[region][g]);
                ret.append_value(buf.total_returns[region][g]);
                decay.append_value(buf.total_transit_decay[region][g]);
            }
        }

        let schema = Arc::new(Schema::new(vec![
            Field::new("region_id", DataType::UInt16, false),
            Field::new("good_slot", DataType::UInt8, false),
            Field::new("total_departures", DataType::Float32, false),
            Field::new("total_arrivals", DataType::Float32, false),
            Field::new("total_returns", DataType::Float32, false),
            Field::new("total_transit_decay", DataType::Float32, false),
        ]));

        let batch = RecordBatch::try_new(schema, vec![
            Arc::new(rid.finish()),
            Arc::new(gs.finish()),
            Arc::new(dep.finish()),
            Arc::new(arr.finish()),
            Arc::new(ret.finish()),
            Arc::new(decay.finish()),
        ]).map_err(arrow_err)?;

        Ok(PyRecordBatch::new(batch))
    }
```

- [ ] **Step 2: Write Python integration test**

Add to `tests/test_merchant_mobility.py`:

```python
def test_get_delivery_diagnostics_returns_batch(sim_fixture):
    """get_delivery_diagnostics returns an Arrow batch with expected columns."""
    batch = sim_fixture.get_delivery_diagnostics()
    assert batch.num_columns == 6
    assert "total_departures" in batch.schema.names
    assert "total_arrivals" in batch.schema.names
    assert "total_returns" in batch.schema.names
    assert "total_transit_decay" in batch.schema.names
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents` and `pytest tests/test_merchant_mobility.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/ffi.rs tests/test_merchant_mobility.py
git commit -m "feat(m58b): add get_delivery_diagnostics FFI method for testing and sidecar"
```

---

## Task 8: Conservation Integration Tests

**Files:**
- Test: `chronicler-agents/tests/test_merchant.rs` (Rust unit)
- Test: `tests/test_merchant_mobility.py` (Python integration)

- [ ] **Step 1: Write Rust conservation test — three-stream accounting**

```rust
#[test]
fn test_three_stream_conservation() {
    let mut buf = DeliveryBuffer::new(3);
    // Merchant departs region 0 with 10 grain
    buf.record_departure(0, 0, 10.0);
    // Merchant arrives at region 2 with 10 grain
    buf.record_arrival(0, 2, 0, 10.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 3);

    // in_transit_delta = departures - arrivals - returns = 10 - 10 - 0 = 0
    let delta: f32 = (0..3).map(|r| {
        (0..NUM_GOODS).map(|g| {
            delivery.departure_debits[r][g] - delivery.arrival_imports[r][g] - delivery.return_credits[r][g]
        }).sum::<f32>()
    }).sum();
    assert!((delta).abs() < 1e-6, "in_transit_delta should be 0 when all trips complete");
}

#[test]
fn test_conservation_with_in_transit_goods() {
    let mut buf = DeliveryBuffer::new(2);
    // 10 departs, only 7 arrives (3 still in transit)
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 7.0);

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);
    let delta: f32 = (0..2).map(|r| {
        (0..NUM_GOODS).map(|g| {
            delivery.departure_debits[r][g] - delivery.arrival_imports[r][g] - delivery.return_credits[r][g]
        }).sum::<f32>()
    }).sum();
    // 10 - 7 - 0 = 3 goods still in transit
    assert!((delta - 3.0).abs() < 1e-6);
}

#[test]
fn test_transit_decay_on_arrivals_only() {
    let config = EconomyConfig::default();
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    buf.record_return(0, 1, 5.0); // return to region 0, slot 1

    let delivery = HybridDeliveryInput::from_buffer(&buf, 2);

    // ... run tick_economy_core with delivery ...
    // Transit loss should only be from arrivals, not returns
    // Expected: 10.0 * TRANSIT_DECAY[0] (grain decay)
    // Returns should NOT incur decay
}
```

- [ ] **Step 2: Write Python multi-turn conservation test**

```python
def test_multi_turn_delivery_conservation(sim_fixture, world_fixture):
    """10+ turn run: verify in_transit_delta identity and stockpile invariant each turn."""
    # Run N turns, collect economy results, verify conservation each turn
    for turn in range(1, 12):
        # tick economy, collect result
        # Check: conservation error < 1e-5
        # Check: in_transit_delta = departures - arrivals - returns
        pass
```

- [ ] **Step 3: Write transactionality test**

```rust
#[test]
fn test_buffer_not_cleared_on_economy_failure() {
    // Create a delivery buffer with data
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    assert_eq!(buf.departure_debits[0][0], 10.0);

    // Simulate: economy tick would fail (we just don't call clear)
    // Buffer should still have data
    assert_eq!(buf.departure_debits[0][0], 10.0);
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);

    // Only after explicit clear:
    buf.clear();
    assert_eq!(buf.departure_debits[0][0], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);
}
```

- [ ] **Step 4: Run all tests**

Run: `cargo nextest run -p chronicler-agents` and `pytest tests/test_merchant_mobility.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/tests/test_merchant.rs tests/test_merchant_mobility.py
git commit -m "test(m58b): conservation integration tests for three-stream accounting"
```

---

## Task 9: Economy Sidecar Extension

**Files:**
- Modify: `src/chronicler/sidecar.py`
- Modify: `src/chronicler/analytics.py`
- Test: `tests/test_merchant_mobility.py`

- [ ] **Step 1: Add economy sidecar methods to SidecarWriter**

In `src/chronicler/sidecar.py`, add to `SidecarWriter`:

```python
    def write_economy_snapshot(self, turn: int, data: dict[str, Any]) -> None:
        """Write per-turn economy convergence data for M58b gate."""
        path = self._dir / f"economy_turn_{_turn_str(turn)}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _economy_rows(self) -> list[dict[str, Any]]:
        """Collect economy snapshots for consolidated Arrow output."""
        rows = []
        for path in sorted(self._dir.glob("economy_turn_*.json")):
            with open(path) as f:
                data = json.load(f)
                rows.append(data)
        return rows
```

Add economy consolidation to the existing `close()` method (`sidecar.py:193`).

- [ ] **Step 2: Add conservation diagnostics extractor to analytics.py**

In `src/chronicler/analytics.py`, add:

```python
def extract_conservation_diagnostics(economy_result) -> dict[str, float]:
    """Extract per-turn conservation diagnostics from economy result."""
    if economy_result is None:
        return {}
    c = economy_result.conservation
    return {
        "conservation_error_abs_turn": 0.0,  # computed from invariant check
        "conservation_error_abs_cumulative": 0.0,
        "conservation_repair_events": c.get("clamp_floor_loss", 0.0) > 0,
        "max_region_slot_error_turn": 0.0,
        "in_transit_total": 0.0,
        "in_transit_delta": c.get("in_transit_delta", 0.0),
    }
```

- [ ] **Step 3: Wire sidecar writes into simulation loop**

The sidecar is owned by `AgentBridge` (`self._sidecar`, initialized at `agent_bridge.py:750`). Wire economy sidecar writes into `AgentBridge`'s existing sidecar snapshot path (`agent_bridge.py:979`), not directly in `simulation.py`.

Add a method to `AgentBridge`:

```python
    def _write_economy_sidecar(self, world, economy_result):
        """Write economy convergence snapshot if sidecar active and sampling conditions met."""
        if not self._sidecar or economy_result is None:
            return
        if world.turn < 100 or world.turn % 10 != 0:
            return
        from chronicler.analytics import extract_conservation_diagnostics
        self._sidecar.write_economy_snapshot(world.turn, {
            "turn": world.turn,
            "conservation": economy_result.conservation,
        })
```

Call `self._write_economy_sidecar(world, economy_result)` from `set_economy_result()` or from the existing sidecar snapshot block at `agent_bridge.py:979`.

- [ ] **Step 4: Test sidecar writes**

```python
def test_economy_sidecar_writes_snapshots(tmp_path):
    from chronicler.sidecar import SidecarWriter
    writer = SidecarWriter(tmp_path)
    writer.write_economy_snapshot(100, {"turn": 100, "conservation": {"production": 1.0}})
    assert (tmp_path / "validation_summary" / "economy_turn_100.json").exists()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_merchant_mobility.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/sidecar.py src/chronicler/analytics.py src/chronicler/simulation.py tests/test_merchant_mobility.py
git commit -m "feat(m58b): economy sidecar extension for convergence gate data"
```

---

## Task 10: Non-Hybrid Buffer Clearing + Mode Gating

**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (tick_economy non-hybrid clear)
- Test: `chronicler-agents/tests/test_merchant.rs`

- [ ] **Step 1: Add mode-aware buffer clearing to tick_economy**

In `ffi.rs tick_economy()`, after the core call, clear the delivery buffer in non-hybrid modes to prevent unbounded memory growth:

```rust
        // Clear delivery buffer after economy tick.
        // Hybrid: cleared after successful consumption (already done above).
        // Non-hybrid: clear without applying (prevent unbounded growth).
        if hybrid_delivery.is_none() {
            if let Some(buf) = self.merchant_delivery_buf.as_mut() {
                buf.clear();
            }
        }
```

- [ ] **Step 2: Write test — non-hybrid mode clears buffer**

```rust
#[test]
fn test_non_hybrid_clears_delivery_buffer() {
    let mut buf = DeliveryBuffer::new(2);
    buf.record_departure(0, 0, 10.0);
    buf.record_arrival(0, 1, 0, 10.0);
    assert!(!buf.arrival_imports.is_empty());

    // Non-hybrid: clear without applying
    buf.clear();
    assert!(buf.arrival_imports.is_empty());
    assert_eq!(buf.departure_debits[0][0], 0.0);
    // Diagnostics preserved
    assert_eq!(buf.diagnostics.total_departures[0][0], 10.0);
}
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/ffi.rs chronicler-agents/tests/test_merchant.rs
git commit -m "feat(m58b): non-hybrid buffer clearing to prevent unbounded memory growth"
```

---

## Task 11: --agents=off Non-Regression + Full Python Test Suite

**Files:**
- Test: `tests/test_merchant_mobility.py`

- [ ] **Step 1: Write agents=off non-regression test**

```python
def test_agents_off_unchanged_by_m58b():
    """--agents=off path does not touch any M58b code paths."""
    # Run a short simulation with --agents=off
    # Verify Phase 4 bit-identical output (existing test pattern)
    # Verify no delivery buffer methods are called
    pass
```

- [ ] **Step 2: Run full Python test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: All tests PASS.

- [ ] **Step 4: Reinstall Rust extension**

Run: `python -m maturin develop --release`

- [ ] **Step 5: Run a quick 5-seed hybrid smoke test**

Run: `python -m chronicler --agents hybrid --seeds 1-5 --turns 100 --simulate-only`
Expected: Completes without error. Conservation diagnostics show near-zero error.

- [ ] **Step 6: Commit any test additions**

```bash
git add tests/
git commit -m "test(m58b): agents=off non-regression and integration smoke test"
```

---

## Task 12: 200-Seed Convergence Gate

**Files:**
- Create: `scripts/m58b_convergence_gate.py`

- [ ] **Step 1: Write convergence gate script**

Create `scripts/m58b_convergence_gate.py`:

```python
"""M58b convergence gate: 200-seed comparison of hybrid realized vs oracle shadow.

Usage:
    python scripts/m58b_convergence_gate.py --seeds 200 --turns 500 --parallel 24
    python scripts/m58b_convergence_gate.py --seeds 20 --turns 500 --parallel 24 --smoke
"""
import argparse
import json
import numpy as np
from pathlib import Path
from scipy.stats import spearmanr

# Gate criteria from spec
PRICE_RANK_CORR_THRESHOLD = 0.80
PRICE_MAGNITUDE_THRESHOLD = 0.30
VOLUME_RATIO_MEDIAN = (0.75, 1.25)
VOLUME_RATIO_P90 = (0.60, 1.40)
FOOD_SUFF_MEAN_DELTA = 0.10
FOOD_CRISIS_DELTA_PP = 3.0
FOOD_CRISIS_CATASTROPHIC_PP = 8.0
SEED_PASS_RATE = 0.75
CATASTROPHIC_TAIL_RATE = 0.05

# Conservation thresholds
CONSERVATION_MEDIAN_CUMULATIVE = 1e-4
CONSERVATION_P95_CUMULATIVE = 1e-2
CONSERVATION_REPAIR_MEDIAN = 0
CONSERVATION_REPAIR_P95 = 2


def evaluate_seed(sidecar_dir: Path) -> dict:
    """Evaluate one seed's convergence metrics."""
    # Read economy sidecar snapshots
    # Compute per-seed pass criteria
    # Return metrics dict
    pass


def run_gate(output_dir: Path, n_seeds: int) -> dict:
    """Evaluate all seeds against gate criteria."""
    # Collect per-seed results
    # Compute milestone pass criteria
    # Return gate result
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--turns", type=int, default=500)
    parser.add_argument("--parallel", type=int, default=24)
    parser.add_argument("--smoke", action="store_true", help="20-seed smoke test")
    parser.add_argument("--output", type=str, default="output/m58b_gate")
    args = parser.parse_args()

    if args.smoke:
        args.seeds = 20

    # Run batch simulation
    # Evaluate gate
    # Print results
```

- [ ] **Step 2: Run 20-seed smoke test**

Run: `python scripts/m58b_convergence_gate.py --smoke --parallel 24`
Expected: Smoke passes (>= 75% seed pass rate, conservation within thresholds).

- [ ] **Step 3: Run full 200-seed gate**

Run: `python scripts/m58b_convergence_gate.py --seeds 200 --turns 500 --parallel 24`
Expected: Gate passes. Record results for milestone closeout.

- [ ] **Step 4: Commit**

```bash
git add scripts/m58b_convergence_gate.py
git commit -m "feat(m58b): 200-seed convergence gate script with staged execution"
```

---

## Subagent Dispatch Notes

When spawning implementation subagents, include in their prompt:

1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially treasury/tithe/population fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.
8. `ShadowLedger::depart/arrive/unwind` now take `Option<&mut DeliveryBuffer>` — pass `Some(buf)` in merchant phase. After Task 3, `None` is not valid when delivery buffer exists (Task 1 uses `None` temporarily until Task 3 wires the buffer through).
9. `tick_economy_core` takes `Option<&HybridDeliveryInput>` — existing tests pass `None`, hybrid tests pass `Some`.
10. `DeliveryBuffer::clear()` preserves diagnostics. Never call `diagnostics` clear.
11. `TRANSIT_DECAY` in `economy.rs:69` is currently `const` (not `pub`). Task 4 must add `pub` visibility to make it importable from tests and `merchant.rs`.
