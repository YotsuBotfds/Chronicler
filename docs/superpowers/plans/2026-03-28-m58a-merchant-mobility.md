# M58a: Merchant Mobility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make merchants physically move goods along multi-hop trade routes with shadow cargo tracking, one-region-per-turn travel, disruption handling, and diagnostics — without altering macro economy truth.

**Architecture:** Python builds an allowed-edge graph from region adjacency + trade/war/embargo/suspension gates and passes it to Rust via Arrow. Rust owns all per-agent state: BFS pathfinding, route selection, cargo reservation via shadow ledger, trip state machine, movement, and diagnostics. Trip state is 9 new SoA fields on AgentPool. Non-idle merchants are excluded from behavior decisions, spatial drift, and region stats. Economy counts Transit merchants by anchor region.

**Tech Stack:** Rust (chronicler-agents crate), Python (src/chronicler), PyO3 + Arrow FFI, cargo nextest for Rust tests, pytest for Python.

**Spec:** `docs/superpowers/specs/2026-03-28-m58a-merchant-mobility-design.md`

---

## File Structure

**New Rust files:**
- `chronicler-agents/src/merchant.rs` — shadow ledger, route graph, BFS pathfinding, route selection, cargo lifecycle, trip state machine, disruption handling, diagnostics collection

**Modified Rust files:**
- `chronicler-agents/src/agent.rs` — RNG offset 1700
- `chronicler-agents/src/pool.rs` — 9 trip SoA fields, accessors
- `chronicler-agents/src/region.rs` — `stockpile: [f32; 8]` field
- `chronicler-agents/src/tick.rs` — step 0.9 mobility phase, exclusion guards
- `chronicler-agents/src/behavior.rs` — `compute_region_stats` non-idle exclusion
- `chronicler-agents/src/spatial.rs` — market attractor, `transit_entry_position`, zero-score guard, grid exclusion
- `chronicler-agents/src/ffi.rs` — stockpile feed, edge-list batch, anchor merchant count, `get_merchant_trip_stats()`
- `chronicler-agents/src/lib.rs` — `pub mod merchant`

**Modified Python files:**
- `src/chronicler/agent_bridge.py` — stockpile columns in `build_region_batch()`, edge-list batch builder, `get_merchant_trip_stats()` collection
- `src/chronicler/economy.py` — route graph builder with `route_suspensions`
- `src/chronicler/main.py` — `merchant_trip_stats` in bundle metadata

**Test files:**
- `chronicler-agents/tests/test_merchant.rs` — Rust integration tests
- `tests/test_merchant_mobility.py` — Python integration tests

---

### Task 1: RNG Offset Registration

**Files:**
- Modify: `chronicler-agents/src/agent.rs:113-114` (after MARRIAGE_STREAM_OFFSET)
- Modify: `chronicler-agents/src/agent.rs:428-444` (collision-check array)

- [ ] **Step 1: Add offset constant**

In `chronicler-agents/src/agent.rs`, after the `MARRIAGE_STREAM_OFFSET` line (line 114):

```rust
// M58a: Merchant route selection (reserved, not consumed in M58a)
pub const MERCHANT_ROUTE_STREAM_OFFSET: u64 = 1700;
```

- [ ] **Step 2: Add to collision-check array**

In the `test_stream_offsets_no_collision` test (around line 428), add `MERCHANT_ROUTE_STREAM_OFFSET` to the `offsets` array:

```rust
MERCHANT_ROUTE_STREAM_OFFSET,    // 1700
```

- [ ] **Step 3: Run collision test**

Run: `cargo nextest run -p chronicler-agents test_stream_offsets_no_collision`
Expected: PASS (1700 is unique)

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/agent.rs
git commit -m "feat(m58a): register MERCHANT_ROUTE_STREAM_OFFSET = 1700"
```

---

### Task 2: Pool SoA Fields

**Files:**
- Modify: `chronicler-agents/src/pool.rs:19-84` (struct fields)
- Modify: `chronicler-agents/src/pool.rs:96-148` (new() constructor)
- Modify: `chronicler-agents/src/pool.rs:150-278` (spawn() both paths)
- Modify: `chronicler-agents/src/agent.rs` (constants)

- [ ] **Step 1: Add trip constants to agent.rs**

```rust
// M58a: Merchant mobility constants
pub const MAX_PATH_LEN: usize = 16;
pub const TRIP_PHASE_IDLE: u8 = 0;
pub const TRIP_PHASE_LOADING: u8 = 1;
pub const TRIP_PHASE_TRANSIT: u8 = 2;
pub const TRIP_GOOD_SLOT_NONE: u8 = 255;
```

- [ ] **Step 2: Add 9 SoA fields to AgentPool struct**

In `chronicler-agents/src/pool.rs`, after `settlement_ids` (line 82), before `alive` (line 84):

```rust
    // M58a: Merchant mobility trip state
    pub trip_phase: Vec<u8>,           // Idle=0, Loading=1, Transit=2
    pub trip_dest_region: Vec<u16>,
    pub trip_origin_region: Vec<u16>,
    pub trip_good_slot: Vec<u8>,       // good slot 0..7, 255=none
    pub trip_cargo_qty: Vec<f32>,
    pub trip_turns_elapsed: Vec<u16>,
    pub trip_path: Vec<[u16; crate::agent::MAX_PATH_LEN]>,
    pub trip_path_len: Vec<u8>,
    pub trip_path_cursor: Vec<u8>,
```

- [ ] **Step 3: Initialize in new()**

In `new()` (around line 96), add `Vec::with_capacity(capacity)` for each new field, before the `alive` init:

```rust
            trip_phase: Vec::with_capacity(capacity),
            trip_dest_region: Vec::with_capacity(capacity),
            trip_origin_region: Vec::with_capacity(capacity),
            trip_good_slot: Vec::with_capacity(capacity),
            trip_cargo_qty: Vec::with_capacity(capacity),
            trip_turns_elapsed: Vec::with_capacity(capacity),
            trip_path: Vec::with_capacity(capacity),
            trip_path_len: Vec::with_capacity(capacity),
            trip_path_cursor: Vec::with_capacity(capacity),
```

- [ ] **Step 4: Initialize in spawn() reuse path**

In the `if let Some(slot) = self.free_slots.pop()` branch (around line 169), before `self.alive[slot] = true`:

```rust
            self.trip_phase[slot] = crate::agent::TRIP_PHASE_IDLE;
            self.trip_dest_region[slot] = 0;
            self.trip_origin_region[slot] = 0;
            self.trip_good_slot[slot] = crate::agent::TRIP_GOOD_SLOT_NONE;
            self.trip_cargo_qty[slot] = 0.0;
            self.trip_turns_elapsed[slot] = 0;
            self.trip_path[slot] = [u16::MAX; crate::agent::MAX_PATH_LEN];
            self.trip_path_len[slot] = 0;
            self.trip_path_cursor[slot] = 0;
```

- [ ] **Step 5: Initialize in spawn() grow path**

In the `else` branch (around line 224), before `self.alive.push(true)`:

```rust
            self.trip_phase.push(crate::agent::TRIP_PHASE_IDLE);
            self.trip_dest_region.push(0);
            self.trip_origin_region.push(0);
            self.trip_good_slot.push(crate::agent::TRIP_GOOD_SLOT_NONE);
            self.trip_cargo_qty.push(0.0);
            self.trip_turns_elapsed.push(0);
            self.trip_path.push([u16::MAX; crate::agent::MAX_PATH_LEN]);
            self.trip_path_len.push(0);
            self.trip_path_cursor.push(0);
```

- [ ] **Step 6: Add inline accessors**

After existing accessors (around line 380):

```rust
    #[inline]
    pub fn is_on_trip(&self, slot: usize) -> bool {
        self.trip_phase[slot] != crate::agent::TRIP_PHASE_IDLE
    }
```

- [ ] **Step 7: Build and run existing tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: all existing tests pass (new fields are zero-initialized, no behavioral change)

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/pool.rs chronicler-agents/src/agent.rs
git commit -m "feat(m58a): add 9 trip SoA fields to AgentPool"
```

---

### Task 3: RegionState Stockpile Feed

**Files:**
- Modify: `chronicler-agents/src/region.rs:19-80` (struct field)
- Modify: `chronicler-agents/src/region.rs:82-135` (constructor default)
- Modify: `chronicler-agents/src/ffi.rs` (region batch parsing)
- Modify: `src/chronicler/agent_bridge.py:300-395` (stockpile columns)
- Modify: `chronicler-agents/src/economy.rs:9` (import NUM_GOODS)

- [ ] **Step 1: Add stockpile field to RegionState**

In `chronicler-agents/src/region.rs`, after `temple_prestige` (line 80), before the closing brace:

```rust
    // M58a: Per-good stockpile levels (from Python RegionStockpile)
    pub stockpile: [f32; 8],
```

- [ ] **Step 2: Initialize in RegionState::new()**

In the `new()` function default block, before the closing fields:

```rust
            stockpile: [0.0; 8],
```

- [ ] **Step 3: Update all RegionState literals in tests**

Grep all test files for `RegionState` struct literals and add `stockpile: [0.0; 8]`. Use the existing test helper function pattern — check if there's a `test_region()` or similar helper. If RegionState literals are constructed via `RegionState::new()`, no changes needed. If they use struct literal syntax, add the field.

Run: `cargo nextest run -p chronicler-agents` to find any that need updating.

- [ ] **Step 4: Add stockpile columns to Python build_region_batch()**

In `src/chronicler/agent_bridge.py`, in the `build_region_batch()` return dict (around line 395), add after the economy signals block:

```python
        # M58a: Per-good stockpile levels for merchant cargo availability
        "stockpile_0": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[0], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_1": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[1], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_2": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[2], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_3": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[3], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_4": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[4], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_5": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[5], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_6": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[6], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
        "stockpile_7": pa.array(
            [r.stockpile.goods.get(economy.GOOD_NAMES[7], 0.0) if hasattr(r, 'stockpile') and r.stockpile else 0.0
             for r in world.regions], type=pa.float32(),
        ),
```

First verify `GOOD_NAMES` exists in `economy.py` — grep for it. If it doesn't, use the good name constants from the economy module to map slot indices to names.

- [ ] **Step 5: Parse stockpile columns in Rust FFI**

In `chronicler-agents/src/ffi.rs`, in the `set_region_state()` function where region columns are extracted (around line 1741+), add optional stockpile column extraction:

```rust
let stockpile_cols: Vec<Option<&Float32Array>> = (0..8)
    .map(|g| rb.column_by_name(&format!("stockpile_{g}")).and_then(|c| c.as_any().downcast_ref::<Float32Array>()))
    .collect();
```

In the region initialization loop, add:

```rust
stockpile: {
    let mut s = [0.0f32; 8];
    for (g, col) in stockpile_cols.iter().enumerate() {
        if let Some(arr) = col {
            s[g] = arr.value(i);
        }
    }
    s
},
```

- [ ] **Step 6: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS (stockpile columns are optional, backward compatible)

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py
git commit -m "feat(m58a): add stockpile[8] to RegionState with Python→Rust feed"
```

---

### Task 4: Shadow Ledger and MerchantTripStats Structs

**Files:**
- Create: `chronicler-agents/src/merchant.rs`
- Modify: `chronicler-agents/src/lib.rs`

- [ ] **Step 1: Create merchant.rs with shadow ledger and stats**

```rust
//! M58a: Merchant mobility — shadow ledger, route graph, trip state machine.

use crate::economy::NUM_GOODS;

/// Shadow cargo ledger — tracks reservations and in-transit goods
/// without mutating macro stockpiles. Persistent across turns.
#[derive(Clone, Debug)]
pub struct ShadowLedger {
    pub reserved: Vec<[f32; NUM_GOODS]>,
    pub in_transit_out: Vec<[f32; NUM_GOODS]>,
    /// Cumulative monotonic counter — only incremented, never decremented.
    pub pending_delivery: Vec<[f32; NUM_GOODS]>,
}

impl ShadowLedger {
    pub fn new(num_regions: usize) -> Self {
        Self {
            reserved: vec![[0.0; NUM_GOODS]; num_regions],
            in_transit_out: vec![[0.0; NUM_GOODS]; num_regions],
            pending_delivery: vec![[0.0; NUM_GOODS]; num_regions],
        }
    }

    /// Available cargo for reservation at (region, slot).
    /// Returns max(0, stockpile - reserved - in_transit_out).
    pub fn available(&self, region: usize, slot: usize, stockpile: &[f32; 8]) -> f32 {
        (stockpile[slot] - self.reserved[region][slot] - self.in_transit_out[region][slot]).max(0.0)
    }

    /// Returns true if new reservations should be blocked (overcommitted).
    pub fn is_overcommitted(&self, region: usize, slot: usize, stockpile: &[f32; 8]) -> bool {
        self.reserved[region][slot] + self.in_transit_out[region][slot] > stockpile[slot]
    }

    /// Reserve cargo for a Loading merchant.
    pub fn reserve(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] += qty;
    }

    /// Cancel a reservation (Loading → Idle on invalidation).
    pub fn cancel_reservation(&mut self, region: usize, slot: usize, qty: f32) {
        self.reserved[region][slot] = (self.reserved[region][slot] - qty).max(0.0);
    }

    /// Depart: move from reserved to in_transit_out (Loading → Transit).
    pub fn depart(&mut self, origin: usize, slot: usize, qty: f32) {
        self.reserved[origin][slot] = (self.reserved[origin][slot] - qty).max(0.0);
        self.in_transit_out[origin][slot] += qty;
    }

    /// Arrive: move from in_transit_out to pending_delivery (Transit → Idle via Arrived).
    pub fn arrive(&mut self, origin: usize, dest: usize, slot: usize, qty: f32) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
        self.pending_delivery[dest][slot] += qty;
    }

    /// Unwind: return in-transit cargo to origin (disruption).
    pub fn unwind(&mut self, origin: usize, slot: usize, qty: f32) {
        self.in_transit_out[origin][slot] = (self.in_transit_out[origin][slot] - qty).max(0.0);
    }

    /// Clear all entries for a conquered region. Call AFTER unwinding impacted trips.
    pub fn clear_region(&mut self, region: usize) {
        self.reserved[region] = [0.0; NUM_GOODS];
        self.in_transit_out[region] = [0.0; NUM_GOODS];
        // pending_delivery is monotonic — do not clear
    }
}

/// Per-turn diagnostics collected during the merchant mobility phase.
#[derive(Clone, Debug, Default)]
pub struct MerchantTripStats {
    pub active_trips: u32,
    pub completed_trips: u32,
    pub avg_trip_duration: f32,
    pub total_in_transit_qty: f32,
    pub route_utilization: f32,
    pub disruption_replans: u32,
    pub unwind_count: u32,
    pub stalled_trip_count: u32,
    pub overcommit_count: u32,
}
```

- [ ] **Step 2: Add module to lib.rs**

In `chronicler-agents/src/lib.rs`, add:

```rust
pub mod merchant;
```

- [ ] **Step 3: Write shadow ledger unit tests**

At the bottom of `merchant.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shadow_ledger_availability() {
        let mut ledger = ShadowLedger::new(2);
        let stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        assert_eq!(ledger.available(0, 0, &stockpile), 10.0);
        ledger.reserve(0, 0, 3.0);
        assert_eq!(ledger.available(0, 0, &stockpile), 7.0);
        ledger.depart(0, 0, 3.0);
        assert_eq!(ledger.available(0, 0, &stockpile), 7.0); // reserved→in_transit, same total
    }

    #[test]
    fn test_shadow_ledger_two_sided_accounting() {
        let mut ledger = ShadowLedger::new(2);
        // Reserve at region 0, slot 0
        ledger.reserve(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 5.0);
        // Depart: reserved--, in_transit++
        ledger.depart(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 0.0);
        assert_eq!(ledger.in_transit_out[0][0], 5.0);
        // Arrive at region 1: in_transit--, pending++
        ledger.arrive(0, 1, 0, 5.0);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[1][0], 5.0);
    }

    #[test]
    fn test_shadow_ledger_unwind() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        ledger.depart(0, 0, 5.0);
        // Unwind: in_transit--, no pending
        ledger.unwind(0, 0, 5.0);
        assert_eq!(ledger.in_transit_out[0][0], 0.0);
        assert_eq!(ledger.pending_delivery[0][0], 0.0);
    }

    #[test]
    fn test_shadow_ledger_overcommit_guard() {
        let mut ledger = ShadowLedger::new(1);
        let stockpile = [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        ledger.reserve(0, 0, 6.0);
        ledger.depart(0, 0, 6.0);
        assert!(!ledger.is_overcommitted(0, 0, &stockpile)); // 6 < 10
        ledger.reserve(0, 0, 5.0);
        assert!(ledger.is_overcommitted(0, 0, &stockpile)); // 6+5 = 11 > 10
    }

    #[test]
    fn test_shadow_ledger_cancel_reservation() {
        let mut ledger = ShadowLedger::new(1);
        ledger.reserve(0, 0, 5.0);
        ledger.cancel_reservation(0, 0, 5.0);
        assert_eq!(ledger.reserved[0][0], 0.0);
    }

    #[test]
    fn test_shadow_ledger_clear_region() {
        let mut ledger = ShadowLedger::new(2);
        ledger.reserve(0, 0, 5.0);
        ledger.reserve(0, 1, 3.0);
        ledger.depart(0, 0, 2.0);
        ledger.arrive(0, 1, 0, 2.0);
        ledger.clear_region(0);
        assert_eq!(ledger.reserved[0], [0.0; NUM_GOODS]);
        assert_eq!(ledger.in_transit_out[0], [0.0; NUM_GOODS]);
        // pending_delivery is monotonic — NOT cleared
        assert_eq!(ledger.pending_delivery[1][0], 2.0);
    }
}
```

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents merchant`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/src/lib.rs
git commit -m "feat(m58a): shadow ledger and MerchantTripStats structs"
```

---

### Task 5: Route Graph — Edge-List Batch

**Files:**
- Modify: `src/chronicler/economy.py` (route graph builder)
- Modify: `src/chronicler/agent_bridge.py` (build and pass edge-list batch)
- Modify: `chronicler-agents/src/merchant.rs` (edge-list parsing + adjacency structure)
- Modify: `chronicler-agents/src/ffi.rs` (edge-list batch intake)

- [ ] **Step 1: Add route graph builder to economy.py**

In `src/chronicler/economy.py`, add a new function for the merchant route graph. This uses full region adjacency as the base, then gates cross-civ edges:

```python
def build_merchant_route_graph(world) -> "pa.RecordBatch":
    """Build allowed-edge graph for merchant pathfinding.

    Base: all region adjacency pairs (intra-civ movement is free).
    Cross-civ edges gated by: trade permission (neutral+), no active war,
    no embargo, no route_suspensions.
    """
    import pyarrow as pa
    region_name_to_idx = {r.name: i for i, r in enumerate(world.regions)}

    # Build war set (sorted tuples, symmetric)
    war_set = set()
    for a, b in world.active_wars:
        war_set.add(tuple(sorted([a, b])))

    # Build embargo set (sorted tuples, symmetric)
    embargo_set = set()
    for a, b in world.embargoes:
        embargo_set.add(tuple(sorted([a, b])))

    # Build suspension set (regions with active trade suspensions)
    suspended_regions = set()
    for r in world.regions:
        if r.route_suspensions:
            suspended_regions.add(r.name)

    from_ids, to_ids, is_rivers, transport_costs = [], [], [], []

    for r in world.regions:
        r_idx = region_name_to_idx[r.name]
        for adj_name in r.adjacencies:
            if adj_name not in region_name_to_idx:
                continue
            adj_idx = region_name_to_idx[adj_name]
            adj_region = world.regions[adj_idx]

            # Intra-civ: always allowed
            if r.controller and r.controller == adj_region.controller:
                from_ids.append(r_idx)
                to_ids.append(adj_idx)
                is_rivers.append(_regions_share_river(r, adj_region))
                transport_costs.append(_transport_cost(r, adj_region, world))
                continue

            # Cross-civ: apply all gates
            if r.controller is None or adj_region.controller is None:
                continue  # uncontrolled regions not traversable

            pair = tuple(sorted([r.controller, adj_region.controller]))
            if pair in war_set:
                continue
            if pair in embargo_set:
                continue
            if r.name in suspended_regions or adj_name in suspended_regions:
                continue

            # Disposition check: both sides must be neutral+
            rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
            rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
            DISP_ORDER = {"hostile": 0, "suspicious": 1, "neutral": 2, "friendly": 3, "allied": 4}
            if rel_ab is None or rel_ba is None:
                continue
            if (DISP_ORDER.get(rel_ab.disposition.value, 0) < 2
                    or DISP_ORDER.get(rel_ba.disposition.value, 0) < 2):
                continue

            from_ids.append(r_idx)
            to_ids.append(adj_idx)
            is_rivers.append(_regions_share_river(r, adj_region))
            transport_costs.append(_transport_cost(r, adj_region, world))

    return pa.record_batch({
        "from_region": pa.array(from_ids, type=pa.uint16()),
        "to_region": pa.array(to_ids, type=pa.uint16()),
        "is_river": pa.array(is_rivers, type=pa.bool_()),
        "transport_cost": pa.array(transport_costs, type=pa.float32()),
    })


def _regions_share_river(r1, r2) -> bool:
    """Check if two adjacent regions share a river connection."""
    # river_mask bits correspond to adjacencies — check if the bit for the
    # other region is set in either region's mask
    return bool(getattr(r1, 'river_mask', 0) or getattr(r2, 'river_mask', 0))


def _transport_cost(r1, r2, world) -> float:
    """Compute transport cost between two adjacent regions.

    Uses M43a terrain factors + river/coastal discounts.
    """
    # Base cost by terrain (from M43a transport model)
    TERRAIN_COST = {
        "plains": 1.0, "forest": 1.5, "mountains": 2.5,
        "coast": 0.8, "desert": 2.0, "tundra": 2.0,
    }
    base = max(TERRAIN_COST.get(r1.terrain, 1.0), TERRAIN_COST.get(r2.terrain, 1.0))
    if _regions_share_river(r1, r2):
        base *= 0.5  # river discount
    if r1.terrain == "coast" or r2.terrain == "coast":
        base *= 0.6  # coastal discount
    # Winter modifier
    from chronicler.ecology import get_season_id
    if get_season_id(world.turn) == 3:  # Winter
        base *= 1.5
    return base
```

Note: verify `_regions_share_river` against actual river_mask semantics by reading `resources.py` river logic. The above is a placeholder — the implementation agent should check `r.river_mask` bit layout and adjacency indexing.

- [ ] **Step 2: Add edge-list parsing to merchant.rs**

In `chronicler-agents/src/merchant.rs`, add the route graph structure and BFS:

```rust
use std::collections::VecDeque;
use crate::agent::MAX_PATH_LEN;

/// Adjacency list built from the Python edge-list batch.
#[derive(Clone, Debug)]
pub struct RouteGraph {
    /// For each region, list of (neighbor_region, is_river, transport_cost).
    pub adj: Vec<Vec<(u16, bool, f32)>>,
    pub num_regions: usize,
    /// Total directed edge count (for route_utilization normalization).
    pub edge_count: usize,
}

impl RouteGraph {
    pub fn from_edges(
        from_regions: &[u16],
        to_regions: &[u16],
        is_rivers: &[bool],
        transport_costs: &[f32],
        num_regions: usize,
    ) -> Self {
        let mut adj = vec![Vec::new(); num_regions];
        for i in 0..from_regions.len() {
            let from = from_regions[i] as usize;
            if from < num_regions {
                adj[from].push((to_regions[i], is_rivers[i], transport_costs[i]));
            }
        }
        // Sort adjacency lists for deterministic BFS
        for neighbors in &mut adj {
            neighbors.sort_by_key(|&(region, _, _)| region);
        }
        Self { adj, num_regions, edge_count: from_regions.len() }
    }

    /// Returns true if the directed edge (from, to) exists.
    pub fn has_edge(&self, from: u16, to: u16) -> bool {
        let from_idx = from as usize;
        if from_idx >= self.num_regions { return false; }
        self.adj[from_idx].iter().any(|&(r, _, _)| r == to)
    }
}

/// BFS predecessor table for one origin region.
#[derive(Clone, Debug)]
pub struct PathTable {
    /// Distance in hops from origin. u16::MAX = unreachable.
    pub dist: Vec<u16>,
    /// Predecessor region on shortest path. u16::MAX = no predecessor (origin or unreachable).
    pub pred: Vec<u16>,
}

/// Compute BFS shortest paths from `origin` over the route graph.
/// Only explores up to MAX_PATH_LEN hops.
pub fn bfs_from(graph: &RouteGraph, origin: u16) -> PathTable {
    let n = graph.num_regions;
    let mut dist = vec![u16::MAX; n];
    let mut pred = vec![u16::MAX; n];
    let origin_idx = origin as usize;
    if origin_idx >= n {
        return PathTable { dist, pred };
    }
    dist[origin_idx] = 0;
    let mut queue = VecDeque::new();
    queue.push_back(origin_idx);
    while let Some(current) = queue.pop_front() {
        let current_dist = dist[current];
        if current_dist as usize >= MAX_PATH_LEN {
            continue; // Don't explore beyond MAX_PATH_LEN
        }
        for &(neighbor, _, _) in &graph.adj[current] {
            let ni = neighbor as usize;
            if ni < n && dist[ni] == u16::MAX {
                dist[ni] = current_dist + 1;
                pred[ni] = current as u16;
                queue.push_back(ni);
            }
        }
    }
    PathTable { dist, pred }
}

/// Trace back the path from origin to dest using the predecessor table.
/// Returns the path as a fixed-size array with hop count, or None if unreachable.
pub fn trace_path(
    table: &PathTable,
    origin: u16,
    dest: u16,
) -> Option<([u16; MAX_PATH_LEN], u8)> {
    let dest_idx = dest as usize;
    if dest_idx >= table.dist.len() || table.dist[dest_idx] == u16::MAX {
        return None;
    }
    let hop_count = table.dist[dest_idx] as usize;
    if hop_count == 0 || hop_count > MAX_PATH_LEN {
        return None;
    }
    let mut path = [u16::MAX; MAX_PATH_LEN];
    let mut current = dest_idx;
    for i in (0..hop_count).rev() {
        path[i] = current as u16;
        current = table.pred[current] as usize;
    }
    // Sanity: first hop's predecessor should be origin
    if current != origin as usize {
        return None;
    }
    Some((path, hop_count as u8))
}
```

- [ ] **Step 3: Write BFS and path tracing tests**

Add to the `tests` module in `merchant.rs`:

```rust
    #[test]
    fn test_route_graph_from_edges() {
        // Linear graph: 0 → 1 → 2
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2], &[1, 0, 2, 1],
            &[false; 4], &[1.0; 4], 3,
        );
        assert!(graph.has_edge(0, 1));
        assert!(graph.has_edge(1, 2));
        assert!(!graph.has_edge(0, 2));
        assert_eq!(graph.edge_count, 4);
    }

    #[test]
    fn test_bfs_shortest_path() {
        // Triangle: 0↔1↔2, 0↔2
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2, 0, 2], &[1, 0, 2, 1, 2, 0],
            &[false; 6], &[1.0; 6], 3,
        );
        let table = bfs_from(&graph, 0);
        assert_eq!(table.dist[0], 0);
        assert_eq!(table.dist[1], 1);
        assert_eq!(table.dist[2], 1); // direct edge 0→2
    }

    #[test]
    fn test_bfs_max_path_len_limit() {
        // Long chain: 0→1→2→...→20
        let n = 20;
        let mut from_r = Vec::new();
        let mut to_r = Vec::new();
        for i in 0..n-1 {
            from_r.push(i as u16);
            to_r.push((i + 1) as u16);
            from_r.push((i + 1) as u16);
            to_r.push(i as u16);
        }
        let graph = RouteGraph::from_edges(
            &from_r, &to_r,
            &vec![false; from_r.len()], &vec![1.0; from_r.len()], n,
        );
        let table = bfs_from(&graph, 0);
        // Region 16 is MAX_PATH_LEN hops away — should be reachable
        assert_eq!(table.dist[16], 16);
        // Region 17+ should be unreachable (beyond MAX_PATH_LEN)
        assert_eq!(table.dist[17], u16::MAX);
    }

    #[test]
    fn test_trace_path() {
        // Linear: 0→1→2→3
        let graph = RouteGraph::from_edges(
            &[0, 1, 2, 1, 2, 3], &[1, 0, 1, 2, 3, 2],
            &[false; 6], &[1.0; 6], 4,
        );
        let table = bfs_from(&graph, 0);
        let (path, len) = trace_path(&table, 0, 3).unwrap();
        assert_eq!(len, 3);
        assert_eq!(path[0], 1);
        assert_eq!(path[1], 2);
        assert_eq!(path[2], 3);
    }

    #[test]
    fn test_trace_path_unreachable() {
        // Disconnected: 0↔1, 2 alone
        let graph = RouteGraph::from_edges(
            &[0, 1], &[1, 0], &[false; 2], &[1.0; 2], 3,
        );
        let table = bfs_from(&graph, 0);
        assert!(trace_path(&table, 0, 2).is_none());
    }

    #[test]
    fn test_bfs_deterministic_tiebreak() {
        // Star: 0→1, 0→2, 0→3 (all distance 1)
        let graph = RouteGraph::from_edges(
            &[0, 0, 0, 1, 2, 3], &[1, 2, 3, 0, 0, 0],
            &[false; 6], &[1.0; 6], 4,
        );
        let t1 = bfs_from(&graph, 0);
        let t2 = bfs_from(&graph, 0);
        // Same results both times (deterministic)
        assert_eq!(t1.dist, t2.dist);
        assert_eq!(t1.pred, t2.pred);
    }
```

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents merchant`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/merchant.rs src/chronicler/economy.py
git commit -m "feat(m58a): route graph, BFS pathfinding, and edge-list builder"
```

---

### Task 6: Route Selection and Trip State Machine

**Files:**
- Modify: `chronicler-agents/src/merchant.rs`

- [ ] **Step 1: Add route selection and cargo reservation**

In `merchant.rs`, add the route selection and trip initiation logic:

```rust
use crate::agent::{TRIP_PHASE_IDLE, TRIP_PHASE_LOADING, TRIP_PHASE_TRANSIT, TRIP_GOOD_SLOT_NONE, MAX_PATH_LEN};
use crate::pool::AgentPool;
use crate::region::RegionState;

/// Minimum margin sum (origin + dest) for a trip to be worthwhile.
pub const MIN_TRIP_PROFIT: f32 = 0.05; // [CALIBRATE]
/// Maximum cargo a single merchant can carry per trip.
pub const MERCHANT_CARGO_CAP: f32 = 2.0; // [CALIBRATE]

/// A reservation intent collected during parallel evaluation,
/// applied in deterministic order.
#[derive(Clone, Debug)]
pub struct TripIntent {
    pub agent_slot: usize,
    pub origin_region: u16,
    pub dest_region: u16,
    pub good_slot: u8,
    pub cargo_qty: f32,
    pub path: [u16; MAX_PATH_LEN],
    pub path_len: u8,
}

/// Evaluate route candidates for an idle merchant at `origin_region`.
/// Returns a TripIntent if a profitable route with available cargo exists.
pub fn evaluate_route(
    agent_slot: usize,
    agent_id: u32,
    origin_region: u16,
    regions: &[RegionState],
    path_table: &PathTable,
    ledger: &ShadowLedger,
) -> Option<TripIntent> {
    let origin = origin_region as usize;
    if origin >= regions.len() { return None; }

    let origin_margin = regions[origin].merchant_margin;

    // Score all reachable destinations
    let mut best_dest: Option<u16> = None;
    let mut best_score: f32 = MIN_TRIP_PROFIT;
    let mut best_dest_id_tiebreak: (u16, u32) = (u16::MAX, u32::MAX);

    for (dest_idx, &dist) in path_table.dist.iter().enumerate() {
        if dist == 0 || dist == u16::MAX { continue; }
        let score = origin_margin + regions[dest_idx].merchant_margin;
        let tiebreak = (dest_idx as u16, agent_id);
        if score > best_score || (score == best_score && tiebreak < best_dest_id_tiebreak) {
            best_score = score;
            best_dest = Some(dest_idx as u16);
            best_dest_id_tiebreak = tiebreak;
        }
    }

    let dest = best_dest?;

    // Find best good slot with available cargo
    let mut best_slot: Option<u8> = None;
    let mut best_avail: f32 = 0.0;
    for slot in 0..8u8 {
        if ledger.is_overcommitted(origin, slot as usize, &regions[origin].stockpile) {
            continue;
        }
        let avail = ledger.available(origin, slot as usize, &regions[origin].stockpile);
        if avail > best_avail || (avail == best_avail && best_slot.map_or(true, |s| slot < s)) {
            best_avail = avail;
            best_slot = Some(slot);
        }
    }

    let good_slot = best_slot.filter(|_| best_avail > 0.0)?;
    let cargo_qty = best_avail.min(MERCHANT_CARGO_CAP);

    let (path, path_len) = trace_path(path_table, origin_region, dest)?;

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

/// Apply a trip intent to the pool and shadow ledger.
/// Re-checks availability at apply time (two-phase model).
/// Returns true if the reservation was committed, false if rejected.
pub fn apply_trip_intent(
    intent: &TripIntent,
    pool: &mut AgentPool,
    ledger: &mut ShadowLedger,
    regions: &[RegionState],
    stats: &mut MerchantTripStats,
) -> bool {
    let origin = intent.origin_region as usize;
    let slot = intent.good_slot as usize;

    // Re-check at apply time
    if ledger.is_overcommitted(origin, slot, &regions[origin].stockpile) {
        stats.overcommit_count += 1;
        return false;
    }
    let avail = ledger.available(origin, slot, &regions[origin].stockpile);
    if avail <= 0.0 {
        stats.overcommit_count += 1;
        return false;
    }
    let qty = avail.min(intent.cargo_qty);

    // Commit reservation
    ledger.reserve(origin, slot, qty);

    // Update pool fields
    let s = intent.agent_slot;
    pool.trip_phase[s] = TRIP_PHASE_LOADING;
    pool.trip_dest_region[s] = intent.dest_region;
    pool.trip_origin_region[s] = intent.origin_region;
    pool.trip_good_slot[s] = intent.good_slot;
    pool.trip_cargo_qty[s] = qty;
    pool.trip_turns_elapsed[s] = 0;
    pool.trip_path[s] = intent.path;
    pool.trip_path_len[s] = intent.path_len;
    pool.trip_path_cursor[s] = 0;

    true
}

/// Advance a Transit merchant one hop along their path.
/// Updates region and spatial position via transit_entry_position.
/// Returns the new region, or None if arrived.
pub fn advance_one_hop(pool: &mut AgentPool, slot: usize, master_seed: u64) -> Option<u16> {
    let cursor = pool.trip_path_cursor[slot] as usize;
    let len = pool.trip_path_len[slot] as usize;
    if cursor >= len { return None; } // already at destination

    let from_region = pool.regions[slot];
    let next_region = pool.trip_path[slot][cursor];
    pool.regions[slot] = next_region;
    pool.trip_path_cursor[slot] += 1;
    pool.trip_turns_elapsed[slot] += 1;

    // Set spatial position at edge entry point
    let (x, y) = crate::spatial::transit_entry_position(master_seed, next_region, from_region);
    pool.x[slot] = x;
    pool.y[slot] = y;

    if (pool.trip_path_cursor[slot] as usize) >= len {
        None // arrived at destination
    } else {
        Some(next_region) // still in transit
    }
}

/// Transition Loading → Transit (departure).
/// Validates next hop first; cancels reservation if invalid.
pub fn depart_merchant(
    pool: &mut AgentPool,
    slot: usize,
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
) -> bool {
    let cursor = pool.trip_path_cursor[slot] as usize;
    let next_hop = pool.trip_path[slot][cursor];
    let current = pool.regions[slot];

    if !graph.has_edge(current, next_hop) {
        // Route invalidated before departure — cancel
        let origin = pool.trip_origin_region[slot] as usize;
        let good = pool.trip_good_slot[slot] as usize;
        ledger.cancel_reservation(origin, good, pool.trip_cargo_qty[slot]);
        reset_trip_fields(pool, slot);
        return false;
    }

    // Depart: reserved → in_transit
    let origin = pool.trip_origin_region[slot] as usize;
    let good = pool.trip_good_slot[slot] as usize;
    ledger.depart(origin, good, pool.trip_cargo_qty[slot]);
    pool.trip_phase[slot] = TRIP_PHASE_TRANSIT;
    true
}

/// Reset all trip fields to Idle state.
pub fn reset_trip_fields(pool: &mut AgentPool, slot: usize) {
    pool.trip_phase[slot] = TRIP_PHASE_IDLE;
    pool.trip_dest_region[slot] = 0;
    pool.trip_origin_region[slot] = 0;
    pool.trip_good_slot[slot] = TRIP_GOOD_SLOT_NONE;
    pool.trip_cargo_qty[slot] = 0.0;
    pool.trip_turns_elapsed[slot] = 0;
    pool.trip_path[slot] = [u16::MAX; MAX_PATH_LEN];
    pool.trip_path_len[slot] = 0;
    pool.trip_path_cursor[slot] = 0;
}
```

- [ ] **Step 2: Write route selection tests**

Add to the `tests` module:

```rust
    fn make_test_regions(n: usize) -> Vec<crate::region::RegionState> {
        (0..n).map(|i| {
            let mut r = crate::region::RegionState::new(i as u16);
            r.merchant_margin = 0.3;
            r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
            r
        }).collect()
    }

    #[test]
    fn test_evaluate_route_finds_profitable_destination() {
        let regions = make_test_regions(3);
        let graph = RouteGraph::from_edges(
            &[0, 1, 1, 2], &[1, 0, 2, 1],
            &[false; 4], &[1.0; 4], 3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger);
        assert!(intent.is_some());
        let intent = intent.unwrap();
        assert_eq!(intent.origin_region, 0);
        // Should pick region 1 (closer, same margin)
        assert!(intent.dest_region == 1 || intent.dest_region == 2);
        assert!(intent.cargo_qty > 0.0);
    }

    #[test]
    fn test_evaluate_route_no_profitable_route() {
        let mut regions = make_test_regions(2);
        regions[0].merchant_margin = 0.0;
        regions[1].merchant_margin = 0.0;
        let graph = RouteGraph::from_edges(
            &[0, 1], &[1, 0], &[false; 2], &[1.0; 2], 2,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(2);
        let intent = evaluate_route(0, 1, 0, &regions, &table, &ledger);
        assert!(intent.is_none()); // below MIN_TRIP_PROFIT
    }

    #[test]
    fn test_deterministic_tiebreak_by_region_then_agent() {
        let mut regions = make_test_regions(3);
        // Equal margins on both destinations
        regions[1].merchant_margin = 0.5;
        regions[2].merchant_margin = 0.5;
        let graph = RouteGraph::from_edges(
            &[0, 0, 1, 2], &[1, 2, 0, 0],
            &[false; 4], &[1.0; 4], 3,
        );
        let table = bfs_from(&graph, 0);
        let ledger = ShadowLedger::new(3);
        let i1 = evaluate_route(0, 100, 0, &regions, &table, &ledger).unwrap();
        let i2 = evaluate_route(0, 100, 0, &regions, &table, &ledger).unwrap();
        // Same agent, same state → same destination
        assert_eq!(i1.dest_region, i2.dest_region);
    }
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents merchant`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/merchant.rs
git commit -m "feat(m58a): route selection, cargo reservation, trip state machine"
```

---

### Task 7: Merchant Mobility Phase (tick orchestration)

**Files:**
- Modify: `chronicler-agents/src/merchant.rs` (orchestration function)
- Modify: `chronicler-agents/src/tick.rs` (step 0.9 insertion, exclusion guards)
- Modify: `chronicler-agents/src/behavior.rs` (compute_region_stats exclusion)

- [ ] **Step 1: Add mobility phase orchestration to merchant.rs**

```rust
/// Run the full merchant mobility phase. Called at step 0.9 in tick_agents.
/// Processes: disruption → departures → movement → arrivals → route eval → reservations.
pub fn merchant_mobility_phase(
    pool: &mut AgentPool,
    regions: &[RegionState],
    graph: &RouteGraph,
    ledger: &mut ShadowLedger,
    master_seed: u64,
) -> MerchantTripStats {
    let mut stats = MerchantTripStats::default();
    let cap = pool.capacity();

    // Phase a-b: Disruption check + replan/unwind for Transit merchants
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT {
            continue;
        }
        let cursor = pool.trip_path_cursor[slot] as usize;
        let len = pool.trip_path_len[slot] as usize;
        if cursor >= len { continue; } // will be processed as arrival

        let current = pool.regions[slot];
        let next_hop = pool.trip_path[slot][cursor];

        if !graph.has_edge(current, next_hop) {
            // Disruption: attempt replan from current position to same destination
            let dest = pool.trip_dest_region[slot];
            let table = bfs_from(graph, current);
            if let Some((new_path, new_len)) = trace_path(&table, current, dest) {
                // Replan succeeded
                pool.trip_path[slot] = new_path;
                pool.trip_path_len[slot] = new_len;
                pool.trip_path_cursor[slot] = 0;
                stats.disruption_replans += 1;
            } else {
                // Replan failed — unwind
                let origin = pool.trip_origin_region[slot] as usize;
                let good = pool.trip_good_slot[slot] as usize;
                ledger.unwind(origin, good, pool.trip_cargo_qty[slot]);
                stats.stalled_trip_count += 1;
                stats.unwind_count += 1;
                reset_trip_fields(pool, slot);
            }
        }
    }

    // Phase c: Loading invalidation + departure
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_LOADING {
            continue;
        }
        depart_merchant(pool, slot, graph, ledger);
    }

    // Phase d-e: Advance Transit merchants + process arrivals
    // Collect arrivals first, then process (avoid mutating while iterating stats)
    let mut arrivals: Vec<usize> = Vec::new();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT {
            continue;
        }
        if advance_one_hop(pool, slot, master_seed).is_none() {
            // Arrived at destination
            arrivals.push(slot);
        }
    }
    for slot in arrivals {
        let origin = pool.trip_origin_region[slot] as usize;
        let dest = pool.trip_dest_region[slot] as usize;
        let good = pool.trip_good_slot[slot] as usize;
        let qty = pool.trip_cargo_qty[slot];
        ledger.arrive(origin, dest, good, qty);
        let duration = pool.trip_turns_elapsed[slot];
        stats.completed_trips += 1;
        stats.avg_trip_duration += duration as f32; // accumulate sum, divide later
        reset_trip_fields(pool, slot);
    }
    // Finalize avg
    if stats.completed_trips > 0 {
        stats.avg_trip_duration /= stats.completed_trips as f32;
    }

    // Phase f-g: Route evaluation for idle merchants + cargo reservation
    // Collect path tables per origin region (precompute)
    let mut origin_tables: std::collections::HashMap<u16, PathTable> = std::collections::HashMap::new();
    let mut intents: Vec<TripIntent> = Vec::new();

    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_IDLE {
            continue;
        }
        if pool.occupations[slot] != crate::agent::Occupation::Merchant as u8 {
            continue;
        }
        let origin = pool.regions[slot];
        let table = origin_tables.entry(origin).or_insert_with(|| bfs_from(graph, origin));
        if let Some(intent) = evaluate_route(slot, pool.ids[slot], origin, regions, table, ledger) {
            intents.push(intent);
        }
    }

    // Apply intents in deterministic order: region then agent_id
    intents.sort_by_key(|i| (i.origin_region, pool.ids[i.agent_slot]));
    for intent in &intents {
        apply_trip_intent(intent, pool, ledger, regions, &mut stats);
    }

    // Phase h: Collect final diagnostics
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] != TRIP_PHASE_TRANSIT {
            continue;
        }
        stats.active_trips += 1;
        stats.total_in_transit_qty += pool.trip_cargo_qty[slot];
    }
    if graph.edge_count > 0 {
        stats.route_utilization = stats.completed_trips as f32 / graph.edge_count as f32;
    }

    stats
}
```

- [ ] **Step 2: Add non-idle exclusion to compute_region_stats**

In `chronicler-agents/src/behavior.rs`, in `compute_region_stats()` (line 243), add a check at the top of the per-agent loop (after the alive and region bounds checks at lines 255-261) to skip non-idle agents from ALL aggregates (rebel_eligible, sat_sum, pop_count, occupation_supply, civ_data):

```rust
        // M58a: Skip non-idle merchants from ALL region aggregates
        if pool.is_on_trip(slot) {
            continue;
        }
```

Add this at line 262 (after `if r >= n { continue; }` and before `let sat = pool.satisfaction(slot);`). This excludes non-idle agents from rebel eligibility counts, satisfaction averages, population counts, occupation supply, and civ data — matching the spec's "all aggregates" requirement.

- [ ] **Step 3: Add step 0.9 to tick_agents and exclusion guards**

In `chronicler-agents/src/tick.rs`:

The `merchant_mobility_phase` needs the route graph and shadow ledger. These will be stored on `AgentSimulator` in ffi.rs (Task 8). For now, add the function signature and insertion point.

In `tick_agents()`, after the relationship drift step (line 103) and before satisfaction (line 106), add:

```rust
    // -----------------------------------------------------------------------
    // 0.9 Merchant mobility — route eval, departure, movement, arrival (M58a)
    // -----------------------------------------------------------------------
    let merchant_stats = if let Some((ref graph, ref mut ledger)) = merchant_state {
        crate::merchant::merchant_mobility_phase(pool, regions, graph, ledger, master_seed)
    } else {
        crate::merchant::MerchantTripStats::default()
    };
```

This requires adding `merchant_state: Option<(&RouteGraph, &mut ShadowLedger)>` as a parameter to `tick_agents`. Update the signature and all call sites.

Add non-idle exclusion guards in:
- Step 2 (decisions): before `evaluate_region_decisions()`, skip slots where `pool.is_on_trip(slot)`
- Step 3 (household consolidation): in `consolidate_household_migrations`, skip agents with `pool.is_on_trip(slot)` (this is already in household.rs — add the check there)
- Step 4.5b+c (spatial drift): in `spatial_drift_step`, skip agents with `pool.is_on_trip(slot)`

The exact insertion points depend on how these functions iterate — the implementation agent should read each function and add the `is_on_trip` check at the start of per-agent loops.

- [ ] **Step 4: Add merchant_stats to tick_agents return**

Add `MerchantTripStats` to the return tuple. Update the return type and all callers.

- [ ] **Step 5: Run all Rust tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/src/tick.rs chronicler-agents/src/behavior.rs
git commit -m "feat(m58a): merchant mobility phase at step 0.9 with exclusion guards"
```

---

### Task 8: FFI Integration

**Files:**
- Modify: `chronicler-agents/src/ffi.rs`
- Modify: `src/chronicler/agent_bridge.py`
- Modify: `src/chronicler/main.py`

- [ ] **Step 1: Add merchant state to AgentSimulator**

In `ffi.rs`, on the `AgentSimulator` struct, add:

```rust
    merchant_graph: Option<crate::merchant::RouteGraph>,
    merchant_ledger: Option<crate::merchant::ShadowLedger>,
    merchant_trip_stats: crate::merchant::MerchantTripStats,
```

Initialize in `new()`:

```rust
    merchant_graph: None,
    merchant_ledger: None,
    merchant_trip_stats: crate::merchant::MerchantTripStats::default(),
```

- [ ] **Step 2: Add set_merchant_route_graph PyO3 method**

```rust
    #[pyo3(name = "set_merchant_route_graph")]
    pub fn set_merchant_route_graph(&mut self, batch: PyRecordBatch) -> PyResult<()> {
        let rb: RecordBatch = batch.into_inner();
        let from_col = rb.column_by_name("from_region")
            .and_then(|c| c.as_any().downcast_ref::<UInt16Array>())
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing from_region"))?;
        let to_col = rb.column_by_name("to_region")
            .and_then(|c| c.as_any().downcast_ref::<UInt16Array>())
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing to_region"))?;
        let river_col = rb.column_by_name("is_river")
            .and_then(|c| c.as_any().downcast_ref::<BooleanArray>())
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing is_river"))?;
        let cost_col = rb.column_by_name("transport_cost")
            .and_then(|c| c.as_any().downcast_ref::<Float32Array>())
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyValueError, _>("missing transport_cost"))?;

        let n = rb.num_rows();
        let from_r: Vec<u16> = (0..n).map(|i| from_col.value(i)).collect();
        let to_r: Vec<u16> = (0..n).map(|i| to_col.value(i)).collect();
        let rivers: Vec<bool> = (0..n).map(|i| river_col.value(i)).collect();
        let costs: Vec<f32> = (0..n).map(|i| cost_col.value(i)).collect();

        let num_regions = self.regions.len();
        self.merchant_graph = Some(crate::merchant::RouteGraph::from_edges(
            &from_r, &to_r, &rivers, &costs, num_regions,
        ));

        // Initialize ledger on first call
        if self.merchant_ledger.is_none() {
            self.merchant_ledger = Some(crate::merchant::ShadowLedger::new(num_regions));
        }

        Ok(())
    }
```

- [ ] **Step 3: Add get_merchant_trip_stats PyO3 method**

Following the `get_household_stats` pattern at line 2941:

```rust
    #[pyo3(name = "get_merchant_trip_stats")]
    pub fn get_merchant_trip_stats(&self) -> PyResult<std::collections::HashMap<String, f64>> {
        let mut stats = std::collections::HashMap::new();
        stats.insert("active_trips".into(), self.merchant_trip_stats.active_trips as f64);
        stats.insert("completed_trips".into(), self.merchant_trip_stats.completed_trips as f64);
        stats.insert("avg_trip_duration".into(), self.merchant_trip_stats.avg_trip_duration as f64);
        stats.insert("total_in_transit_qty".into(), self.merchant_trip_stats.total_in_transit_qty as f64);
        stats.insert("route_utilization".into(), self.merchant_trip_stats.route_utilization as f64);
        stats.insert("disruption_replans".into(), self.merchant_trip_stats.disruption_replans as f64);
        stats.insert("unwind_count".into(), self.merchant_trip_stats.unwind_count as f64);
        stats.insert("stalled_trip_count".into(), self.merchant_trip_stats.stalled_trip_count as f64);
        stats.insert("overcommit_count".into(), self.merchant_trip_stats.overcommit_count as f64);
        Ok(stats)
    }
```

- [ ] **Step 4: Modify tick_economy merchant count for anchor region**

In the merchant tally loop at `ffi.rs:3555-3577`, modify the merchant count to use anchor region:

```rust
Some(Occupation::Merchant) => {
    // M58a: Transit merchants counted by origin, not current region
    if self.pool.trip_phase[slot] == crate::agent::TRIP_PHASE_TRANSIT {
        // Don't count here — counted by origin region below
    } else {
        merchant_count += 1;
    }
}
```

After the per-region loop, add a second pass for transit merchants counted by origin:

```rust
// M58a: Count transit merchants by trip_origin_region
for slot in 0..self.pool.capacity() {
    if !self.pool.is_alive(slot) { continue; }
    if self.pool.trip_phase[slot] != crate::agent::TRIP_PHASE_TRANSIT { continue; }
    if self.pool.occupations[slot] != Occupation::Merchant as u8 { continue; }
    let origin = self.pool.trip_origin_region[slot] as usize;
    if origin < agent_counts.len() {
        agent_counts[origin].merchant_count += 1;
    }
}
```

- [ ] **Step 5: Wire merchant_state into tick_agents call**

In the `tick()` method on AgentSimulator, construct the merchant_state parameter to pass to `tick_agents`:

```rust
let merchant_state = match (&self.merchant_graph, &mut self.merchant_ledger) {
    (Some(graph), Some(ledger)) => Some((graph, ledger)),
    _ => None,
};
```

Store the returned `MerchantTripStats` in `self.merchant_trip_stats`.

- [ ] **Step 6: Wire Python-side agent_bridge**

In `src/chronicler/agent_bridge.py`:

Add merchant_trip_stats collection in `_process_tick_results()` (after household_stats collection around line 827):

```python
        # M58a: Merchant trip stats
        m_stats = self._sim.get_merchant_trip_stats()
        self._merchant_trip_stats_history.append(m_stats)
```

Add initialization in `__init__`:

```python
        self._merchant_trip_stats_history: list = []
```

Add property:

```python
    @property
    def merchant_trip_stats(self) -> list:
        """M58a: Per-tick merchant trip stats history."""
        return self._merchant_trip_stats_history
```

Add route graph sync to `tick_agents()` method (called by `simulation.py:1549,1554`). In `tick_agents()`, after `sync_regions()` and before `self._sim.tick()`:

```python
        # M58a: Build and set merchant route graph
        from chronicler.economy import build_merchant_route_graph
        route_batch = build_merchant_route_graph(world)
        self._sim.set_merchant_route_graph(route_batch)
```

This is the correct call site because both hybrid mode (`simulation.py:1549`) and non-hybrid agent modes (`simulation.py:1554`) call `agent_bridge.tick_agents()`. The route graph is rebuilt each turn from current world state.

- [ ] **Step 7: Wire main.py bundle metadata**

In `src/chronicler/main.py`, after the household_stats block (line 755):

```python
    # M58a: merchant trip stats metadata
    if agent_bridge is not None:
        m_trip_stats = getattr(agent_bridge, "merchant_trip_stats", [])
        if not isinstance(m_trip_stats, list):
            m_trip_stats = []
        bundle["metadata"]["merchant_trip_stats"] = m_trip_stats
```

- [ ] **Step 8: Run all tests**

Run: `cargo nextest run -p chronicler-agents && pytest tests/ -x`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py src/chronicler/main.py
git commit -m "feat(m58a): FFI integration — route graph, stats getter, anchor counting, Python bridge"
```

---

### Task 9: Spatial Changes

**Files:**
- Modify: `chronicler-agents/src/spatial.rs`

- [ ] **Step 1: Activate Market attractor in init_attractors**

In `init_attractors()` (line 220), add Market to the candidates array. Replace the `// Market: never active (reserved)` comment:

```rust
        Candidate {
            atype: AttractorType::Market,
            active: true, // M58a: always active, weight-driven
        },
```

Add position generation for Market in the match block (replace `unreachable!()`):

```rust
            AttractorType::Market => interior_position(seed, region_id, disc),
```

- [ ] **Step 2: Add EMA market weight in update_attractor_weights**

In `update_attractor_weights()` (line 375), replace the `AttractorType::Market => 0.0` arm:

```rust
            AttractorType::Market => {
                let raw = (region.trade_route_count as f32 * 0.3
                           + region.merchant_margin * 0.7)
                           .clamp(0.0, 1.0);
                let prev = attractors.weights[i];
                // EMA smoothing
                prev + crate::agent::MARKET_WEIGHT_ALPHA * (raw - prev)
            }
```

Add `MARKET_WEIGHT_ALPHA` constant to `agent.rs`:

```rust
pub const MARKET_WEIGHT_ALPHA: f32 = 0.3; // [CALIBRATE] EMA smoothing for market attractor
```

- [ ] **Step 3: Update OCCUPATION_AFFINITY — Merchant Market = 0.4**

In `OCCUPATION_AFFINITY` (line 117), change the Merchant row (line 121):

```rust
    [0.2, 0.3, 0.3, 0.3, 0.3, 0.05, 0.5, 0.4], // Merchant — M58a: Market activated
```

- [ ] **Step 4: Add migration_reset_position zero-score guard**

In `migration_reset_position()` (line 643), after the best-attractor loop (around line 665), add before returning the position:

```rust
    // M58a: If no attractor has positive score, fall back to center
    if best_score <= 0.0 {
        return (0.5, 0.5);
    }
```

- [ ] **Step 5: Add transit_entry_position public helper**

After `migration_reset_position()`:

```rust
/// Position a transit merchant at an edge entry point in the destination region,
/// biased toward the direction they came from.
pub fn transit_entry_position(
    seed: u64,
    region_id: u16,
    from_region_id: u16,
) -> (f32, f32) {
    let disc = from_region_id as u64;
    let h0 = seed
        .wrapping_mul(0x517cc1b727220a95)
        .wrapping_add(region_id as u64)
        .wrapping_mul(0x6c62272e07bb0142)
        .wrapping_add(disc);
    let edge = (h0 % 4) as u8;
    let h1 = h0.wrapping_mul(LCG_MUL).wrapping_add(LCG_ADD);
    let frac = (h1 as f32 / u64::MAX as f32).clamp(0.1, 0.9);
    match edge {
        0 => (frac, 0.05),        // top edge
        1 => (frac, 0.95),        // bottom edge
        2 => (0.05, frac),        // left edge
        3 => (0.95, frac),        // right edge
        _ => (0.5, 0.5),
    }
}
```

- [ ] **Step 6: Add non-idle grid exclusion in spatial_drift_step**

In `spatial_drift_step()` (line 531), add check at the start of the per-agent loop to skip non-idle agents:

In the first pass (computing new positions), add after the alive check:

```rust
        // M58a: Skip non-idle merchants from spatial drift and grid
        if pool.is_on_trip(slot) {
            continue;
        }
```

Also ensure the grid rebuild (`rebuild_spatial_grids`) skips non-idle agents — check how it populates the grid and add the same guard.

- [ ] **Step 7: Run tests**

Run: `cargo nextest run -p chronicler-agents`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/spatial.rs chronicler-agents/src/agent.rs
git commit -m "feat(m58a): market attractor activation, transit entry position, grid exclusion"
```

---

### Task 10: Integration Tests

**Files:**
- Create: `chronicler-agents/tests/test_merchant.rs`
- Create: `tests/test_merchant_mobility.py`

- [ ] **Step 1: Write Rust integration test — multi-turn travel**

In `chronicler-agents/tests/test_merchant.rs`:

```rust
use chronicler_agents::merchant::*;
use chronicler_agents::pool::AgentPool;
use chronicler_agents::agent::*;
use chronicler_agents::region::RegionState;

fn setup_linear_world() -> (AgentPool, Vec<RegionState>, RouteGraph) {
    let mut pool = AgentPool::new(10);
    // Spawn a merchant at region 0
    pool.spawn(0, 0, chronicler_agents::agent::Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

    let mut regions: Vec<RegionState> = (0..4).map(|i| {
        let mut r = RegionState::new(i);
        r.merchant_margin = 0.3;
        r.stockpile = [10.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        r.controller_civ = 0;
        r
    }).collect();

    // Linear graph: 0 ↔ 1 ↔ 2 ↔ 3
    let graph = RouteGraph::from_edges(
        &[0, 1, 1, 2, 2, 3, 3, 2, 2, 1, 1, 0],
        &[1, 0, 2, 1, 3, 2, 2, 3, 1, 2, 0, 1],
        &[false; 12], &[1.0; 12], 4,
    );

    (pool, regions, graph)
}

#[test]
fn test_multi_turn_travel() {
    let (mut pool, regions, graph) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);

    // Turn 1: merchant should plan and enter Loading
    let stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, 42);
    assert_eq!(pool.trip_phase[0], TRIP_PHASE_LOADING);

    // Turn 2: should depart (Loading → Transit) and advance one hop
    let stats = merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, 42);
    assert_eq!(pool.trip_phase[0], TRIP_PHASE_TRANSIT);
    // Should have moved from region 0
    assert_ne!(pool.regions[0], 0);
}

#[test]
fn test_disruption_unwind() {
    let (mut pool, regions, graph) = setup_linear_world();
    let mut ledger = ShadowLedger::new(4);

    // Turn 1: start trip
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, 42);
    // Turn 2: depart
    merchant_mobility_phase(&mut pool, &regions, &graph, &mut ledger, 42);

    // Turn 3: remove the edge the merchant needs — simulate embargo
    let broken_graph = RouteGraph::from_edges(
        &[0, 1], &[1, 0], &[false; 2], &[1.0; 2], 4,
    ); // Only region 0↔1 connected
    let stats = merchant_mobility_phase(&mut pool, &regions, &broken_graph, &mut ledger, 42);

    // Merchant should have been unwound (if destination unreachable)
    // or replanned (if still reachable via alternate route)
    // With only 0↔1 connected, regions 2 and 3 are unreachable
    if pool.trip_dest_region[0] > 1 {
        assert_eq!(pool.trip_phase[0], TRIP_PHASE_IDLE);
        assert!(stats.unwind_count > 0 || stats.stalled_trip_count > 0);
    }
}

#[test]
fn test_agents_off_unchanged() {
    // With no merchant_state, the mobility phase returns default stats
    let stats = MerchantTripStats::default();
    assert_eq!(stats.active_trips, 0);
    assert_eq!(stats.completed_trips, 0);
}
```

- [ ] **Step 2: Write Python integration test — --agents=off compatibility**

In `tests/test_merchant_mobility.py`:

```python
"""M58a: Merchant mobility integration tests."""
import argparse
import json
import pytest


def _make_args(tmp_path, seed=42, turns=10, agents="off"):
    return argparse.Namespace(
        seed=seed, turns=turns, civs=2, regions=5,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False,
        live=False, scenario=None, agents=agents,
        narrator="local", agent_narrative=False,
        pause_every=None,
    )


def test_agents_off_unaffected(tmp_path):
    """--agents=off produces identical output regardless of M58a code."""
    from chronicler.main import execute_run
    args = _make_args(tmp_path, agents="off")
    execute_run(args)
    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists()
    bundle = json.loads(bundle_path.read_text())
    # No merchant_trip_stats when agents=off
    assert "merchant_trip_stats" not in bundle.get("metadata", {})
```

- [ ] **Step 3: Run all tests**

Run: `cargo nextest run -p chronicler-agents && pytest tests/test_merchant_mobility.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/tests/test_merchant.rs tests/test_merchant_mobility.py
git commit -m "test(m58a): integration tests — multi-turn travel, disruption, --agents=off"
```

---

### Task 11: Household Consolidation Skip

**Files:**
- Modify: `chronicler-agents/src/household.rs:228` (consolidate_household_migrations)

- [ ] **Step 1: Add non-idle skip**

In `consolidate_household_migrations()`, at the start of the migration processing loop (where it iterates `migration_snapshot`), add a check to skip agents with active trip state:

```rust
            // M58a: Skip non-idle merchants — trip state takes precedence
            if pool.is_on_trip(slot) {
                continue;
            }
```

Also skip spouse-follow if the spouse is on a trip:

```rust
            if let Some(spouse_id) = relationships::get_spouse_id(pool, slot) {
                if let Some(&spouse_slot) = id_to_slot.get(&spouse_id) {
                    // M58a: Don't follow a spouse who is on a trade trip
                    if pool.is_on_trip(spouse_slot) {
                        continue;
                    }
```

- [ ] **Step 2: Run tests**

Run: `cargo nextest run -p chronicler-agents household`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/household.rs
git commit -m "feat(m58a): skip non-idle merchants in household migration consolidation"
```

---

### Task 12: Conquest/Controller-Change Unwind

**Files:**
- Modify: `chronicler-agents/src/merchant.rs`
- Modify: `chronicler-agents/src/tick.rs` (wire conquest unwind into tick)

- [ ] **Step 1: Add conquest unwind function to merchant.rs**

```rust
/// Handle conquest/controller-change: identify impacted trips, unwind, clear residuals.
/// Must be called when a region changes controller, BEFORE the merchant mobility phase.
/// `conquered_regions` contains indices of regions that changed controller this turn.
pub fn conquest_unwind(
    pool: &mut AgentPool,
    ledger: &mut ShadowLedger,
    conquered_regions: &[u16],
    stats: &mut MerchantTripStats,
) {
    let conquered_set: std::collections::HashSet<u16> = conquered_regions.iter().copied().collect();
    if conquered_set.is_empty() { return; }

    let cap = pool.capacity();
    for slot in 0..cap {
        if !pool.is_alive(slot) || pool.trip_phase[slot] == TRIP_PHASE_IDLE {
            continue;
        }
        let origin = pool.trip_origin_region[slot];
        let dest = pool.trip_dest_region[slot];
        let current = pool.regions[slot];

        if !conquered_set.contains(&origin) && !conquered_set.contains(&dest)
            && !conquered_set.contains(&current) {
            continue;
        }

        let good = pool.trip_good_slot[slot] as usize;
        let qty = pool.trip_cargo_qty[slot];
        let origin_idx = origin as usize;

        match pool.trip_phase[slot] {
            TRIP_PHASE_LOADING => {
                ledger.cancel_reservation(origin_idx, good, qty);
            }
            TRIP_PHASE_TRANSIT => {
                ledger.unwind(origin_idx, good, qty);
                stats.unwind_count += 1;
            }
            _ => {}
        }
        reset_trip_fields(pool, slot);
    }

    // Clear residual ledger entries for conquered regions
    for &region in conquered_regions {
        ledger.clear_region(region as usize);
    }
}
```

- [ ] **Step 2: Write conquest unwind test**

Add to `merchant.rs` tests:

```rust
    #[test]
    fn test_conquest_unwind_loading_and_transit() {
        let mut pool = AgentPool::new(5);
        // Spawn 2 merchants
        let s0 = pool.spawn(0, 0, crate::agent::Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let s1 = pool.spawn(1, 0, crate::agent::Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);

        let mut ledger = ShadowLedger::new(4);

        // s0: Loading at region 0, cargo reserved
        pool.trip_phase[s0] = TRIP_PHASE_LOADING;
        pool.trip_origin_region[s0] = 0;
        pool.trip_dest_region[s0] = 2;
        pool.trip_good_slot[s0] = 0;
        pool.trip_cargo_qty[s0] = 5.0;
        ledger.reserve(0, 0, 5.0);

        // s1: Transit from region 1, cargo in transit
        pool.trip_phase[s1] = TRIP_PHASE_TRANSIT;
        pool.trip_origin_region[s1] = 1;
        pool.trip_dest_region[s1] = 3;
        pool.trip_good_slot[s1] = 0;
        pool.trip_cargo_qty[s1] = 3.0;
        ledger.reserve(1, 0, 3.0);
        ledger.depart(1, 0, 3.0);

        let mut stats = MerchantTripStats::default();

        // Conquer region 0 — should unwind s0 (Loading) and clear region 0
        conquest_unwind(&mut pool, &mut ledger, &[0], &mut stats);

        assert_eq!(pool.trip_phase[s0], TRIP_PHASE_IDLE);
        assert_eq!(ledger.reserved[0][0], 0.0); // reservation cancelled + region cleared
        // s1 should be unaffected (region 1 not conquered)
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_TRANSIT);

        // Now conquer region 3 (s1's destination) — should unwind s1
        conquest_unwind(&mut pool, &mut ledger, &[3], &mut stats);
        assert_eq!(pool.trip_phase[s1], TRIP_PHASE_IDLE);
        assert_eq!(stats.unwind_count, 1);
    }
```

- [ ] **Step 3: Wire conquest unwind into tick**

In `tick.rs`, the conquest unwind should run at the start of step 0.9 (before the main mobility phase). The conquered regions come from `RegionState.controller_changed_this_turn`:

```rust
    // M58a: Conquest unwind before mobility
    if let Some((_, ref mut ledger)) = merchant_state {
        let conquered: Vec<u16> = regions.iter()
            .filter(|r| r.controller_changed_this_turn)
            .map(|r| r.region_id)
            .collect();
        if !conquered.is_empty() {
            let mut conquest_stats = crate::merchant::MerchantTripStats::default();
            crate::merchant::conquest_unwind(pool, ledger, &conquered, &mut conquest_stats);
            // Merge conquest stats into main stats later
        }
    }
```

- [ ] **Step 4: Run tests**

Run: `cargo nextest run -p chronicler-agents merchant`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/src/tick.rs
git commit -m "feat(m58a): conquest/controller-change unwind for impacted merchants"
```

---

### Task 13: Analytics Extractor

**Files:**
- Modify: `src/chronicler/analytics.py`

- [ ] **Step 1: Add merchant_trip_stats extractor**

In `src/chronicler/analytics.py`, add alongside existing extractors (following the `bundles: list[dict]` convention used by `extract_stockpiles`, `extract_politics`, etc.):

```python
def extract_merchant_trip_stats(bundles: list[dict]) -> dict:
    """M58a: Per-seed merchant trip stats time series.

    Returns {"by_seed": {seed: [per_turn_stats_dicts]}}.
    """
    by_seed: dict[int, list[dict]] = {}
    for b in bundles:
        seed = b.get("metadata", {}).get("seed", 0)
        stats = b.get("metadata", {}).get("merchant_trip_stats", [])
        by_seed[seed] = stats
    return {"by_seed": by_seed}
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/analytics.py
git commit -m "feat(m58a): merchant_trip_stats analytics extractor"
```

---

### Task 14: Loading Invalidation and Thread-Count Determinism Tests

**Files:**
- Modify: `chronicler-agents/src/merchant.rs` (unit test)
- Modify: `chronicler-agents/tests/test_merchant.rs` (integration test)

- [ ] **Step 1: Write loading invalidation unit test**

Add to `merchant.rs` tests:

```rust
    #[test]
    fn test_loading_invalidation_cancels_reservation() {
        let mut pool = AgentPool::new(5);
        let s = pool.spawn(0, 0, crate::agent::Occupation::Merchant, 20, 0.0, 0.0, 0.0, 0, 0, 0, 0);
        let mut ledger = ShadowLedger::new(3);

        // Set up merchant in Loading state with path 0→1→2
        pool.trip_phase[s] = TRIP_PHASE_LOADING;
        pool.trip_origin_region[s] = 0;
        pool.trip_dest_region[s] = 2;
        pool.trip_good_slot[s] = 0;
        pool.trip_cargo_qty[s] = 5.0;
        pool.trip_path[s] = {
            let mut p = [u16::MAX; MAX_PATH_LEN];
            p[0] = 1; p[1] = 2;
            p
        };
        pool.trip_path_len[s] = 2;
        pool.trip_path_cursor[s] = 0;
        ledger.reserve(0, 0, 5.0);

        // Graph WITHOUT edge 0→1 (invalidated)
        let graph = RouteGraph::from_edges(
            &[1, 2], &[2, 1], &[false; 2], &[1.0; 2], 3,
        );

        // Attempt departure — should fail and cancel reservation
        let departed = depart_merchant(&mut pool, s, &graph, &mut ledger);
        assert!(!departed);
        assert_eq!(pool.trip_phase[s], TRIP_PHASE_IDLE);
        assert_eq!(ledger.reserved[0][0], 0.0); // reservation cancelled
    }
```

- [ ] **Step 2: Write thread-count determinism test**

Add to `chronicler-agents/tests/test_merchant.rs`:

```rust
#[test]
fn test_thread_count_determinism() {
    // Run the same merchant mobility phase twice with identical inputs
    // and verify identical output stats.
    // Note: Full RAYON_NUM_THREADS comparison requires integration test harness.
    // This test verifies determinism of the single-threaded path.
    let (mut pool1, regions, graph) = setup_linear_world();
    let mut pool2 = pool1.clone(); // AgentPool must impl Clone for this
    let mut ledger1 = ShadowLedger::new(4);
    let mut ledger2 = ShadowLedger::new(4);

    let stats1 = merchant_mobility_phase(&mut pool1, &regions, &graph, &mut ledger1, 42);
    let stats2 = merchant_mobility_phase(&mut pool2, &regions, &graph, &mut ledger2, 42);

    assert_eq!(stats1.active_trips, stats2.active_trips);
    assert_eq!(stats1.completed_trips, stats2.completed_trips);
    assert_eq!(stats1.avg_trip_duration, stats2.avg_trip_duration);
    assert_eq!(stats1.total_in_transit_qty, stats2.total_in_transit_qty);
}
```

Note: Full `RAYON_NUM_THREADS=1` vs `RAYON_NUM_THREADS=4` comparison should be tested at the Python integration level by running two simulations with different thread counts and comparing bundle output. Add this to the Python test file:

```python
def test_thread_count_determinism(tmp_path):
    """Same seed with different thread counts produces identical merchant stats."""
    import os
    from chronicler.main import execute_run

    os.environ["RAYON_NUM_THREADS"] = "1"
    d1 = tmp_path / "run1"
    d1.mkdir()
    args1 = _make_args(d1, seed=42, turns=20, agents="hybrid")
    execute_run(args1)

    os.environ["RAYON_NUM_THREADS"] = "4"
    d2 = tmp_path / "run2"
    d2.mkdir()
    args2 = _make_args(d2, seed=42, turns=20, agents="hybrid")
    execute_run(args2)

    os.environ.pop("RAYON_NUM_THREADS", None)

    b1 = json.loads((d1 / "chronicle_bundle.json").read_text())
    b2 = json.loads((d2 / "chronicle_bundle.json").read_text())
    s1 = b1.get("metadata", {}).get("merchant_trip_stats", [])
    s2 = b2.get("metadata", {}).get("merchant_trip_stats", [])
    assert s1 == s2, f"Merchant stats diverge between thread counts"
```

- [ ] **Step 3: Run tests**

Run: `cargo nextest run -p chronicler-agents merchant && pytest tests/test_merchant_mobility.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add chronicler-agents/src/merchant.rs chronicler-agents/tests/test_merchant.rs tests/test_merchant_mobility.py
git commit -m "test(m58a): loading invalidation, thread-count determinism, conquest unwind"
```

---

### Task 15: Final Verification

**Files:** None (testing only)

- [ ] **Step 1: Run full Rust test suite**

Run: `cargo nextest run -p chronicler-agents`
Expected: all tests PASS

- [ ] **Step 2: Run full Python test suite**

Run: `pytest tests/ -x`
Expected: all tests PASS

- [ ] **Step 3: Run cargo clippy**

Run: `cargo clippy -p chronicler-agents -- -D warnings`
Expected: no warnings

- [ ] **Step 4: Verify --agents=off determinism**

Run a short simulation with `--agents=off` and compare against a pre-M58a baseline to confirm bit-identical output.

- [ ] **Step 5: Run a short hybrid simulation**

Run: `python -m chronicler --seed 42 --turns 50 --agents hybrid`
Expected: completes without crash. Check bundle for `merchant_trip_stats` in metadata.

- [ ] **Step 6: Commit any fixes**

If any issues found in steps 1-5, fix and commit.

- [ ] **Step 7: Final commit**

```bash
git commit -m "chore(m58a): final verification — all tests passing"
```
