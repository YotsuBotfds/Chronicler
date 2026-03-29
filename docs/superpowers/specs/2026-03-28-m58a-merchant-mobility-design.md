# M58a: Merchant Mobility — Design Spec

> **Date:** 2026-03-28
> **Status:** Approved
> **Depends on:** M54b (spatial drift), M55a (spatial attractors), M42-M43 (goods economy + stockpiles)
> **Prerequisite for:** M58b (Trade Integration & Macro Convergence)
> **Estimate:** 3-4 days
> **RNG offset:** 1700 (registered, not consumed in M58a)

---

## Goal

Make merchants physically move goods through space. This milestone implements route choice, cargo reservation/loading, multi-turn transit state, and one-region-per-turn travel — without altering macro economy truth.

**Gate:** Merchants move coherently through the world and transit state is inspectable before their effects are used as the new macro trade truth.

---

## Scope

### In-scope

- Merchant route candidate evaluation and deterministic selection
- Multi-hop pathfinding over allowed adjacency graph
- Cargo reservation/loading via shadow ledger
- Multi-turn transit state with one-region-per-turn movement
- Disruption replan/unwind on edge invalidation (embargo, war, suspension)
- Market attractor activation (merchant-only, idle-only)
- Diagnostics metadata surface (9 metrics)
- Transit-agent exclusion from behavior/stats/spatial systems; economy counts transit merchants by anchor region

### Out-of-scope (deferred to M58b+)

- Macro stockpile mutation / write-back of delivered goods
- Macro convergence validation against M42-M43 baseline
- Profitability-based mid-trip re-evaluation (upgrade seam present)
- Dynamic route formation (gravity model, Urquhart graphs)
- Stale-price / information lag (M59 concern)
- Snapshot/FFI column export of trip state

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Shadow ledger — no macro stockpile mutation in M58a | Preserves M58a/M58b boundary and D6 baseline stability. Debugging stays focused on mobility state transitions. |
| D2 | Existing adjacency topology first, dynamic routes deferred | Avoids coupling route-formation correctness with mobility correctness. Extension seam via route-provider contract. |
| D3 | Replan on disruption only, no economic re-evaluation mid-trip | Keeps M58a focused on mobility/transit correctness. Generic replan trigger plumbing present for M58b upgrade to periodic profitability checks. |
| D4 | Full decision suppression during transit (including rebellion) | Prevents split-brain state transitions. Cargo ownership and unwind semantics stay unambiguous. Disruption path owns all in-transit exception handling. |
| D5 | Market attractor: preallocated, dynamic weight, merchant-only, idle-only | Avoids late attractor creation for regions inactive at init. Weight driven by stable signals with EMA smoothing. |
| D6 | Diagnostics: metadata time series only, no snapshot columns | Follows existing `household_stats` pattern. Internal Rust fields present but not FFI-exposed. |
| D7 | Stale prices deferred entirely — no placeholders | Route evaluation reads prices through parameterizable interface; M59 swaps the source, not the mobility logic. |
| D8 | Approach C: Hybrid (Python graph → Rust pathfinding + mobility) | Single-direction data flow. All per-agent state and pathfinding in Rust for 50K merchant performance. Route-provider seam at Arrow edge-list boundary. |

---

## Section 1: Merchant Trip State Machine

### Persistent States (pool fields)

- **Idle** (0) — no active trip. Merchant participates in normal spatial drift, market attractor pull, and is counted in region stats.
- **Loading** (1) — cargo reserved from shadow ledger, departs next tick. Behavior decisions suppressed. Excluded from behavior stats and spatial grid. Economy: counted by current region (still stationary).
- **Transit** (2) — moving one hop per turn along path. Behavior decisions suppressed. Excluded from behavior stats and spatial grid. Economy: counted by `trip_origin_region` (anchor counting).

### Ephemeral States (within-tick logic, not persisted)

- **Planning** — evaluate routes, select path, transition to Loading or stay Idle.
- **Arrived** — deliver cargo to shadow ledger, record diagnostics, transition to Idle.

### Transition Rules

```
Idle → Loading:    profitable route found, path valid, cargo available
Idle → Idle:       no profitable route or no available cargo
Loading → Transit: next tick, if next hop still valid
Loading → Idle:    next hop invalidated before departure (reservation cancelled)
Transit → Transit: advance one hop, path still valid
Transit → Idle:    destination reached (Arrived ephemeral), or disruption unwind
```

### Per-Agent SoA Fields (Rust pool)

| Field | Type | Description |
|-------|------|-------------|
| `trip_phase` | `Vec<u8>` | Idle=0, Loading=1, Transit=2 |
| `trip_dest_region` | `Vec<u16>` | Final destination region index |
| `trip_origin_region` | `Vec<u16>` | Departure region (unwind cargo return target) |
| `trip_good_slot` | `Vec<u8>` | Good slot ID (0..7), 255 = none. Aligned with stockpile goods / economy kernel. |
| `trip_cargo_qty` | `Vec<f32>` | Quantity of goods carried |
| `trip_turns_elapsed` | `Vec<u16>` | Turns since departure (diagnostics) |
| `trip_path` | `Vec<[u16; MAX_PATH_LEN]>` | Full path; cursor advances, no shifting |
| `trip_path_len` | `Vec<u8>` | Total valid hops in path |
| `trip_path_cursor` | `Vec<u8>` | Current position (next hop = `path[cursor]`) |

`MAX_PATH_LEN = 16`. Paths longer than 16 hops rejected at planning. Sufficient for typical world sizes (10-30 regions).

**Storage cost:** 46 bytes/agent. Pool goes from ~68 to ~114 bytes/agent. At 50K agents = 5.7MB total.

---

## Section 2: Route Graph and Pathfinding

### Python-Side Route Graph Construction (per turn)

Build a full traversable movement graph from region adjacency:

1. **Base graph:** All `region.adjacencies` pairs. Merchants traverse own-civ territory freely.
2. **Cross-civ edge gates (all must pass):**
   - Active trade route permission (disposition neutral+, same logic as `get_active_trade_routes()`)
   - No active war between civs (explicit `world.active_wars` check — hard gate, not just disposition). **War pairs normalized as sorted civ-name tuples** before filtering, matching embargo pattern.
   - No embargo between civs
   - No active `route_suspensions` on either endpoint region
3. **Edge attributes:** `is_river` (from region pair data), `transport_cost` (M43a terrain factors + river/coastal discounts). Transport cost available for M58b; M58a path selection uses hop count.

**Output:** Arrow edge-list batch: `[from_region: u16, to_region: u16, is_river: bool, transport_cost: f32]`. Passed to Rust once per turn before the merchant tick.

**Route-provider seam:** The Arrow edge-list batch is the contract. Python owns graph construction; Rust owns pathfinding and movement. Swapping the Python builder (gravity model, dynamic routes) doesn't touch Rust.

### Rust-Side Pathfinding — Precomputed Per-Origin Tables

Instead of BFS per merchant, precompute once per occupied origin region:

1. Build adjacency structure from edge-list batch.
2. For each region with idle merchants: BFS producing predecessor table and distance map for all reachable regions within `MAX_PATH_LEN` hops.
3. Cache tables for the turn — all merchants at the same origin share reachable sets and path traceback.

At ~30 regions, this is ~30 BFS runs max per turn. Negligible cost.

### Route Selection (per idle merchant)

1. Look up precomputed reachable destinations from merchant's current region.
2. Score: `origin_margin + destination_margin` as bilateral market-activity proxy. **Documented caveat:** `merchant_margin` is origin-side outgoing price delta, not goods-specific demand. This is an activity proxy only; M58b refines scoring with goods-level price differentials.
3. Tie-break: `(score, destination_region_id, agent_id)` — fully deterministic, no RNG consumed.
4. Trace path from predecessor table.
5. Below `MIN_TRIP_PROFIT [CALIBRATE]` → stay Idle.

### Disruption Handling (strict ordering per tick)

1. **Invalidate:** Check `path[cursor]` edge against current-turn edge list.
2. **Replan/unwind:** If invalid, attempt replan from current position using precomputed tables. If unreachable → unwind (cargo to origin shadow ledger, transition to Idle, increment `unwind_count`; increment `stalled_trip_count` if no valid next hop existed at all).
3. **Move:** Advance one hop along valid path.

Ordering is invariant — never "move then discover invalid." Civ/region affiliation changes processed through disruption path before movement step.

---

## Section 3: Shadow Ledger and Cargo Semantics

### New FFI Requirement

Add `stockpile: [f32; 8]` (per-good slot) to `RegionState`. Populated from `RegionStockpile.goods` during `build_region_batch()`. +32 bytes/region, negligible.

### Shadow Ledger (Rust-side, persistent across turns)

```rust
pub struct ShadowLedger {
    /// Committed to Loading merchants, not yet departed
    pub reserved: Vec<[f32; NUM_GOODS]>,
    /// Departed, in flight
    pub in_transit_out: Vec<[f32; NUM_GOODS]>,
    /// Arrived — cumulative monotonic counter, never decremented or reset
    pub pending_delivery: Vec<[f32; NUM_GOODS]>,
}
```

`pending_delivery` is **cumulative monotonic** — only incremented. Per-turn delta derivable from consecutive snapshots for analytics. No interval resets.

### Availability Formula

```
available(region, slot) = max(0, stockpile[region][slot] - reserved[region][slot] - in_transit_out[region][slot])
```

### Reservation Guard

If `reserved[r][s] + in_transit_out[r][s] > stockpile[r][s]`, **block** new reservations from `(r, s)` and increment `overcommit_count`. Prevents runaway overcommit in long runs where macro stockpile drops independently.

### Cargo Lifecycle — Explicit Two-Sided Accounting

| Transition | Decrements | Increments |
|---|---|---|
| Planning → Loading | — | `reserved[origin][slot]` |
| Loading → Transit | `reserved[origin][slot]` | `in_transit_out[origin][slot]` |
| Transit → Arrived → Idle | `in_transit_out[origin][slot]` | `pending_delivery[dest][slot]` |
| Transit → Idle (unwind) | `in_transit_out[origin][slot]` | — (cargo returned to origin conceptually) |

### Good Slot Selection

Merchant picks slot with highest `available(origin, slot)`. Tie-break by slot index. No RNG. Reserve amount = `min(available, MERCHANT_CARGO_CAP [CALIBRATE])`.

### Loading-State Invalidation

At Loading → Transit transition, re-validate next hop against current-turn edge list. If invalid: cancel reservation (decrement `reserved[origin][slot]`), transition to Idle. No cargo enters `in_transit_out` for a trip that never departs.

### Conquest / Controller-Change Handling (strict order)

1. **Identify:** Scan all non-Idle merchants (Loading AND Transit) — collect those with `origin == conquered_region` or `dest == conquered_region` or current position `== conquered_region`.
2. **Unwind:** For each impacted merchant:
   - If Loading: cancel reservation (decrement `reserved[origin][slot]`), zero agent cargo fields, transition to Idle.
   - If Transit: execute unwind transition (decrement `in_transit_out[origin][slot]`), zero agent cargo, transition to Idle.
3. **Clear residuals:** Zero any orphaned `reserved` or `in_transit_out` entries for the conquered region (safety sweep after all trips resolved).

### Shadow-Mode Conservation Caveat

M58a operates under **"in-flight conservation only."** Once cargo arrives (`in_transit_out` decremented, `pending_delivery` incremented), the origin's macro stockpile is unchanged, so the same goods become reservable again. This is a known double-counting at the macro level — acceptable because M58a does not claim physical conservation of completed deliveries. `pending_delivery` is a diagnostic counter showing trade throughput. M58b resolves this by wiring delivery into stockpile consumption.

---

## Section 4: Tick Integration and Exclusion Rules

### Tick Placement: Step 0.9 (before satisfaction and decisions)

```
0.5   Wealth tick
0.6   Settlement assignment (Pass A)
0.75  Needs decay
0.8   Relationship drift
0.9   MERCHANT MOBILITY (new):
      a. Disruption check: validate all Transit merchants' next hops
      b. Replan/unwind disrupted merchants
      c. Loading invalidation + departure (Loading → Transit)
      d. Advance Transit merchants one hop
      e. Process arrivals (Transit → Idle)
      f. Route evaluation for Idle merchants (Planning)
      g. Cargo reservation for new trips (→ Loading)
      h. Update shadow ledger + collect diagnostics
1.    Satisfaction
2.    Behavior decisions — skip trip_phase != Idle
3.    Household consolidation — skip trip_phase != Idle
4.    Apply decisions
4.5   Spatial drift — skip trip_phase != Idle (UNCHANGED position)
5.    Demographics
5+    Settlement assignment (Pass B — post-movement correction)
```

**No reordering of existing phases.** Spatial drift stays at its current position (step 4.5, after apply decisions, before demographics — `tick.rs:330`). M58a only inserts the new merchant mobility phase at 0.9 and adds exclusion guards to existing phases. This avoids behavioral risk from reordering drift relative to demographics.

**Why 0.9:** Mobility runs before decisions queue, eliminating decision-queue conflict. Wealth at 0.5 already ran, so agents entering Loading received normal income — **documented one-turn lag by design** (merchant earned stationary income, then begins trip). Satisfaction at 1.0 reads post-mobility state.

**Settlement staleness:** Transit merchants entering a new region at 0.9 have stale `settlement_id` until Pass B. Since satisfaction runs at 1.0 (between Pass A and Pass B), `is_urban` may be stale for moved merchants. This is a **known one-turn lag, identical to existing migration behavior.** No fix needed.

### Exclusion Rules by Trip Phase

**Loading** merchants are stationary (still in origin region) but committed to a trip. **Transit** merchants are physically moving.

| System | Loading | Transit |
|---|---|---|
| `compute_region_stats` | Excluded from all aggregates | Excluded from all aggregates |
| Behavior decisions | Skip `decide_for_agent()` | Skip `decide_for_agent()` |
| Household consolidation | Skip in `consolidate_household_migrations()` | Skip in `consolidate_household_migrations()` |
| Spatial drift | Skip drift + grid population | Skip drift + grid population |
| Economy merchant count | Counted by current region (still stationary) | Counted by `trip_origin_region` (anchor) |

Both Loading and Transit suppress behavior decisions and spatial participation. The only difference is economy counting: Loading merchants haven't moved yet so they count at their current (origin) region; Transit merchants count by anchor to prevent location leak.

Implementation: `ffi.rs` merchant tally reads `trip_origin_region` when `trip_phase == Transit`, otherwise reads current `region` (covers both Idle and Loading).

### Transit Merchant Spatial Position

On hop advance, set `(x, y)` via new `pub fn transit_entry_position(seed, region_id, from_region_id) -> (f32, f32)` in `spatial.rs`. Uses from-region direction to pick appropriate edge entry point. New public helper — does not reuse private `edge_position()`.

---

## Section 5: Market Attractor Activation

### Changes to `spatial.rs`

**`init_attractors()` (line 220):** Always push Market as active candidate. Position: `interior_position()`. Remove `// Market: never active (reserved)` comment and `unreachable!()` position arm.

**`update_attractor_weights()` (line 375):** Market weight uses EMA over previous weight (already available as `attractors.weights[i]`, no extra state):

```rust
AttractorType::Market => {
    let raw = (region.trade_route_count as f32 * 0.3
               + region.merchant_margin * 0.7)
               .clamp(0.0, 1.0);
    let prev = attractors.weights[i];
    prev + MARKET_WEIGHT_ALPHA * (raw - prev)  // EMA
}
```

`MARKET_WEIGHT_ALPHA [CALIBRATE] = 0.3`.

**`OCCUPATION_AFFINITY` table (line 117):** All 5 rows, Market column activated for Merchant only:

```rust
// River, Coast, Res0, Res1, Res2, Temple, Capital, Market
[0.4, 0.1, 0.8, 0.8, 0.8, 0.05, 0.1, 0.0],    // Farmer
[0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.7, 0.0],    // Soldier
[0.2, 0.3, 0.3, 0.3, 0.3, 0.05, 0.5, 0.4],    // Merchant
[0.1, 0.1, 0.1, 0.1, 0.1, 0.5,  0.5, 0.0],    // Scholar
[0.1, 0.05, 0.05, 0.05, 0.05, 0.8, 0.3, 0.0], // Priest
```

**`migration_reset_position()` guard (line 643):** If `best_score <= 0.0` after scanning all attractors, fall back to `(0.5, 0.5)` center position instead of selecting a zero-scored attractor. Prevents Market (always active) from pulling zero-affinity occupations.

**Transit agent grid exclusion:** Transit agents excluded from `SpatialGrid` population entirely — they don't appear as neighbors for density/repulsion calculations.

---

## Section 6: Diagnostics Contract

### Metrics (9 total, metadata time series)

```rust
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

### Metric Definitions

| Metric | Definition |
|--------|------------|
| `active_trips` | Count of `trip_phase == Transit` at end of mobility phase |
| `completed_trips` | Arrivals processed this turn |
| `avg_trip_duration` | Mean `trip_turns_elapsed` over completed trips this turn only |
| `total_in_transit_qty` | Sum of `trip_cargo_qty` for Transit merchants (raw quantity, goods units) |
| `route_utilization` | `completed_trips / max(1, available_directed_routes)` this turn |
| `disruption_replans` | Replans that succeeded (merchant continues with new path) |
| `unwind_count` | Replans that failed (merchant aborted, cargo returned) |
| `stalled_trip_count` | Event-based: incremented when disruption finds no valid next hop, before unwind transition |
| `overcommit_count` | Blocked reservation attempts due to shadow ledger guard |

### API Shape

Getter pattern matching existing `household_stats`:

- `self.merchant_trip_stats: MerchantTripStats` stored on `AgentSimulator`
- `get_merchant_trip_stats() -> HashMap<String, f64>` exposed via PyO3
- Python bridge appends to per-turn metadata series in `agent_bridge.py`
- Bundle surface: `merchant_trip_stats` key in `bundle["metadata"]`, written in `main.py` (same pattern as `relationship_stats` at `main.py:748` and `household_stats` at `main.py:752`)

---

## Section 7: RNG, Determinism, and Validation

### RNG

Register `MERCHANT_ROUTE_STREAM_OFFSET: u64 = 1700` in `agent.rs` `STREAM_OFFSETS` block. Add to collision-check array. **Not consumed in M58a** — all selection is deterministic. Reserved for M58b.

### Determinism Guarantees

- **Route graph:** Deterministic from world state (adjacency, embargo, war, suspensions).
- **Pathfinding:** BFS with lowest-region-ID tie-break. Same edge list → same predecessor tables.
- **Route selection:** Highest `origin_margin + destination_margin`, tie-break `(destination_region_id, agent_id)`. No noise.
- **Cargo reservation:** Highest available slot, tie-break by slot index. No noise.
- **Shadow ledger:** All operations are deterministic arithmetic.

### Two-Phase Apply Model

Route evaluation runs in parallel (read-only against precomputed path tables). Shadow-ledger mutations (reserve/depart/unwind) collected as intents, applied in a single deterministic pass: **regions in sorted order, agents within each region in ID order.** No concurrent mutation of shared ledger state.

**Reservation re-check at apply time:** Each reservation intent re-checks availability against the shadow ledger at the moment of commit, not at the moment of evaluation. If multiple merchants from the same region evaluated the same good slot in parallel, the first (by deterministic ordering) commits; subsequent intents that would exceed availability are rejected and the merchant stays Idle. `overcommit_count` increments for each rejected intent.

Float reductions (e.g., `total_in_transit_qty`) use deterministic ordered summation, not parallel reduction with non-deterministic accumulation order.

### `--agents=off` Compatibility

Merchant mobility is entirely within the agent tick. `--agents=off` skips the agent tick, so M58a has zero impact on aggregate mode.

### Validation Requirements

**Unit tests:**
- Deterministic route selection: same seed → same routes across runs
- Tie-break ordering: `(region_id, agent_id)` key produces stable selection
- State machine transitions: all valid transitions produce correct field updates
- Shadow ledger accounting: reserve/depart/arrive/unwind each produce correct two-sided updates
- Reservation guard: overcommit blocked when `reserved + in_transit_out > stockpile`
- Loading invalidation: route broken before departure → reservation cancelled

**Integration tests:**
- Multi-turn travel: merchant departs, transits N hops, arrives — verify region updates each turn
- Disruption replan: embargo mid-trip → merchant replans or unwinds correctly
- Conquest unwind: region changes controller → impacted merchants unwound in correct order (identify → unwind → clear)
- Transit exclusion: transit merchants not counted in occupation supply, behavior decisions, spatial grid
- Economy anchor counting: transit merchants counted by origin in `tick_economy` merchant tally
- Household skip: in-transit merchant not force-migrated by spouse

**Transient signal tests:**
- Any new signal crossing FFI boundary resets after consumption

**Determinism tests:**
- Cross-process replay: two runs with same seed produce identical `MerchantTripStats` series
- Thread-count determinism: same seed with `RAYON_NUM_THREADS=1` and `RAYON_NUM_THREADS=4` produce identical results
- `--agents=off` output unchanged (bit-identical to pre-M58a baseline)

### Calibration Constants

| Constant | Description | Default |
|----------|-------------|---------|
| `MIN_TRIP_PROFIT` | Minimum margin threshold for route selection | `[CALIBRATE]` |
| `MERCHANT_CARGO_CAP` | Max cargo quantity per trip | `[CALIBRATE]` |
| `MARKET_WEIGHT_ALPHA` | EMA smoothing for market attractor weight | 0.3 |
| `MAX_PATH_LEN` | Max hops per trip path | 16 |
| Merchant Market affinity | `OCCUPATION_AFFINITY[Merchant][Market]` | 0.4 |

---

## Integration Constraints (from seam audit)

These constraints were identified during design review and are binding on the implementation:

1. **Macro leak via merchant location:** In-transit merchants excluded from `tick_economy` merchant-count by current region. Counted by `trip_origin_region` instead (`ffi.rs` merchant tally).

2. **Macro leak via occupation supply:** In-transit merchants excluded from `compute_region_stats` — all aggregates, not just occupation supply.

3. **Household collision:** `consolidate_household_migrations()` skips agents with active trip state. Spouse-follow cannot force-move a transit merchant.

4. **Multi-hop uses trade-allowed edges, not raw adjacency:** Merchant path graph built from adjacency + cross-civ gates (trade permission, embargo, war, suspension), not unrestricted neighbor links.

5. **Disruption ordering:** Invalidate → replan/unwind → move. Never "move then realize invalid."

6. **Market attractor preallocated:** Always present, weight-driven. Never rely on late creation.

7. **Route suspensions binding:** `route_suspensions` (from `climate.py`) consumed by merchant route provider. Currently not consumed by `economy.py` — this is a new integration.

8. **RNG offset registered:** 1700 added to `agent.rs` `STREAM_OFFSETS` block and collision-check array before implementation begins.

---

## M58a / M58b Handoff Contract

M58a delivers to M58b:

- **Working mobility state machine** with per-agent trip state in Rust pool
- **Shadow ledger** with `pending_delivery` as cumulative delivery counter
- **Route-provider seam** (Arrow edge-list batch) — Python builder swappable
- **Precomputed path tables** — BFS replaceable with weighted Dijkstra
- **Replan trigger plumbing** — generic `replan_reason` field, only disruption enabled
- **Transit exclusion infrastructure** — all systems check `trip_phase`
- **9 diagnostics metrics** via metadata time series

M58b adds:

- `pending_delivery` consumption → stockpile write-back
- Macro convergence validation against M42-M43
- Profitability-based replan triggers (upgrade from disruption-only)
- Goods-level scoring (replace activity proxy with price differentials)
- Optional: `total_in_transit_value` metric (requires per-good value table)

---

## File Touch Map

**Rust:**
| File | Changes |
|------|---------|
| `agent.rs` | Register `MERCHANT_ROUTE_STREAM_OFFSET = 1700`, add to collision-check array |
| `pool.rs` | 9 new SoA fields for trip state |
| `tick.rs` | Step 0.9 merchant mobility phase, exclusion guards in steps 2/3/4.5 |
| `behavior.rs` | `compute_region_stats` excludes transit agents from all aggregates |
| `economy.rs` | No changes (shadow ledger is separate) |
| `ffi.rs` | Stockpile feed to `RegionState`, edge-list batch parsing, anchor-region merchant count, `get_merchant_trip_stats()` getter |
| `region.rs` | Add `stockpile: [f32; 8]` to `RegionState` |
| `spatial.rs` | Market attractor always-active, `update_attractor_weights` EMA, `transit_entry_position()` pub helper, `migration_reset_position()` zero-score guard, transit grid exclusion |
| New: `merchant.rs` | Shadow ledger struct, route evaluation, cargo lifecycle, disruption handling |

**Python:**
| File | Changes |
|------|---------|
| `agent_bridge.py` | Build edge-list batch, stockpile feed in `build_region_batch()`, `get_merchant_trip_stats()` collection |
| `simulation.py` | Pass edge-list batch to agent tick |
| `models.py` | No changes (shadow ledger is Rust-only) |
| `economy.py` | Route graph builder incorporating `route_suspensions` |
| `main.py` | Write `merchant_trip_stats` into `bundle["metadata"]` (same pattern as `relationship_stats` line 748, `household_stats` line 752) |
| `analytics.py` | `extract_merchant_trip_stats()` extractor |
| `bundle.py` | No changes (metadata written in `main.py`) |

**Tests:**
| File | Scope |
|------|-------|
| Rust unit tests | State machine, shadow ledger, BFS pathfinding, tie-breaks, reservation guard |
| Rust integration tests | Multi-turn travel, disruption, conquest unwind, transit exclusion, anchor counting, household skip, thread-count determinism |
| Python integration tests | Edge-list batch construction, stockpile feed, diagnostics collection, `--agents=off` compatibility |
| Transient signal tests | Any new cross-boundary signal resets after consumption |
