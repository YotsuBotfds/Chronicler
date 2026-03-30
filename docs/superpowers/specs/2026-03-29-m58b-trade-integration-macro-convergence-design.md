# M58b: Trade Integration & Macro Convergence — Design Spec

> **Date:** 2026-03-29
> **Status:** Draft
> **Depends on:** M58a (merged `1f48121`)
> **Prerequisite for:** M61a (Scale Harness & Determinism)
> **RNG offset:** None (no new RNG sources — reuses M58a's 1700 offset)

---

## Goal

Wire merchant mobility throughput into macro economy truth and validate convergence versus M42-M43 baselines. Agent-level trade replaces abstract trade allocation in hybrid mode; the abstract path becomes an oracle/comparison engine.

**Gate:** Price gradients, trade volumes, and food sufficiency stay within an acceptable comparison band versus the oracle (abstract trade model), measured over 200 paired seeds.

---

## Scope

### In-scope

- Three-stream delivery buffer (departure_debits, arrival_imports with provenance, return_credits)
- Macro stockpile write-back via Phase 2 economy ingress with one-turn lag
- Availability guard fix (replace `in_transit_out` with `departure_debits` in hybrid)
- Transit decay on arrival_imports (same `TRANSIT_DECAY` rates as abstract path)
- Oracle shadow: non-mutating abstract `allocate_trade_flow()` for convergence diagnostics
- Per-turn conservation diagnostics with enforcement tiers
- Sidecar extension for convergence gate data
- 200-seed convergence gate with staged execution (20-seed smoke first)

### Out-of-scope (deferred)

- Disruption/raid cargo losses (dormant `loss_by_reason` seam only)
- Dynamic route formation (gravity model, Urquhart graphs)
- Stale-price / information lag (M59 concern)
- Profitability-based mid-trip re-evaluation (disruption-only replan preserved from M58a)
- Snapshot/FFI column export of trip state

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Batch write-back with one-turn lag | Deliveries from tick T accumulate in drainable buffer; flushed atomically at Phase 2 ingress on turn T+1. Matches existing one-turn lag patterns (Gini). Preserves bridge contract (Rust computes/reports, Python-via-Rust-economy owns mutation). |
| D2 | Full return-to-origin for non-delivery events; transit decay active on arrivals | No disruption/raid sink terms. Unwind returns full cargo to origin. Material transit decay (`TRANSIT_DECAY[good_slot]`) applied to arrival_imports at Phase 2 ingress only — return_credits remain full-value. Keeps parity with oracle for downstream food/pricing signals. |
| D3 | Perfect-info price source, disruption-only replan | Merchants read current turn's RegionState signals at planning time. No mid-transit profitability re-evaluation. No stale-price fields — M59 owns information lag. Best comparability to abstract model for convergence gating. |
| D4 | Band convergence gate (3-layer) | Not KS-tight replication, not qualitative-only. Directional match + bounded numeric bands. Per-seed criteria, milestone pass rate, catastrophic tail guard. |
| D5 | Agent trade replaces abstract allocation in hybrid; abstract becomes oracle | Single ownership of goods movement. `tick_economy_core()` in Rust still computes production/demand/pricing; trade flow step replaced by delivery buffer in hybrid. Oracle shadow runs abstract allocation non-mutating for convergence diagnostics. `--agents=off` path preserved unchanged. |
| D6 | Hard assertion in tests, soft clamp in production, strict gate on diagnostics | Tests catch bugs (exact epsilon). Production runs are resilient (clamp + log). Gate fails on non-trivial drift even if runs complete. |

---

## Section 1: Delivery Buffer & Write-Back Contract

### Buffer structure

New `DeliveryBuffer` alongside existing `ShadowLedger` in `merchant.rs`. Three streams with distinct accounting roles:

| Stream | Schema | Macro effect | M43b role |
|--------|--------|-------------|-----------|
| `departure_debits` | `(origin_region_id: u16, good_slot: u8, qty: f32)` | Negative delta on origin stockpile | Not an import event |
| `arrival_imports` | `(source_region_id: u16, dest_region_id: u16, good_slot: u8, qty: f32)` | Positive delta on dest stockpile (post-decay) | Feeds `imports_by_region`, `import_share`, `trade_dependent`, `inbound_sources` |
| `return_credits` | `(origin_region_id: u16, good_slot: u8, qty: f32)` | Positive delta on origin stockpile (full value) | Not an import event — recovery, not trade |

### Monotonic counter preserved

The existing `ShadowLedger.pending_delivery` (monotonic, never cleared) is untouched. It remains the diagnostic accumulator for total throughput. The delivery buffer is a separate drainable structure.

### Dormant loss seam

`loss_by_reason: Vec<[f32; NUM_GOODS]>` per region, with reason discriminant. In M58b:
- `transit_decay`: active (computed at Phase 2 ingress, not in merchant movement)
- `raid`, `disruption`, `spoilage`: dormant (zeroed, plumbed but never written)

### FFI surface

**No separate drain method in hot path.** The delivery buffer is consumed internally by `tick_economy()` in hybrid mode. The buffer lives on `AgentSimulator` and is read/zeroed by the Rust economy kernel during the economy tick.

New PyO3 method for diagnostics/testing:

```
get_delivery_diagnostics() -> PyRecordBatch
```

Non-draining read of cumulative delivery counters (total departures, arrivals, returns by region and good). For post-tick inspection and test assertions. Does not affect buffer state.

**Counter lifetime:** Run-lifetime monotonic. Counters are initialized to zero at `AgentSimulator` construction and never reset. Per-turn deltas are derived by diffing consecutive reads (same pattern as `pending_delivery`). `AgentBridge.reset()` or new sim init creates a fresh `AgentSimulator`, which resets counters implicitly.

**`tick_economy()` return batches extended:** In hybrid mode, the existing return tuple gains additional columns for delivery-applied quantities (departure_debits_applied, arrival_imports_applied, return_credits_applied) alongside existing economy results. Python reconstructs these into `EconomyResult` conservation fields.

**Batch ordering:** All delivery-related data sorted deterministically:
- departure_debits: by `(origin_region_id, good_slot)`
- arrival_imports: by `(dest_region_id, source_region_id, good_slot)`
- return_credits: by `(origin_region_id, good_slot)`

Keyed by `u16` region engine ID (not name string).

### Drain timing and transactionality

The delivery buffer is consumed *inside* `tick_economy()`, not drained separately before it. This avoids the failure window where a separate drain-then-consume could lose goods if the economy tick fails after drain.

**Contract:** `tick_economy()` receives no separate delivery batches. Instead, the Rust economy kernel reads the delivery buffer directly from the `AgentSimulator`'s internal state and zeros it atomically as part of the economy computation. If `tick_economy()` fails (panic/exception), the buffer is NOT zeroed — goods remain available for the next attempt.

**Sequence:**
1. Python calls `tick_economy(region_input, trade_route, ...)` as today
2. Inside `tick_economy_core()`, hybrid mode reads `DeliveryBuffer` from the simulator state
3. Buffer contents are applied to the economy computation
4. Buffer is zeroed only after successful completion of the economy tick
5. Return batches include delivery diagnostics alongside existing economy results

No Python-side holding of buffer contents between turns. No separate `drain_delivery_buffer()` call in the hot path. The FFI surface gains a `get_delivery_diagnostics()` method for post-tick inspection (non-draining read of cumulative counters), but the drain itself is internal to the economy tick.

### Write-back lifecycle

1. **Pre-departure failure** (loading invalidation): cancel reservation only. No delivery buffer entry. No macro delta.
2. **Departure** (Loading → Transit): `departure_debits` entry recorded. `in_transit_out` incremented (conservation). `departure_debits` stays in buffer until Phase 2 drain.
3. **Arrival** (Transit → Idle via Arrived): `arrival_imports` entry recorded with source provenance. `in_transit_out` decremented.
4. **Post-departure failure** (disruption/conquest unwind): `return_credits` entry recorded for origin. `in_transit_out` decremented. Full cargo value (no decay on returns).
5. **Phase 2 ingress** (next turn): all three streams drained atomically, applied to stockpiles, transit decay applied to arrival_imports.

---

## Section 2: Economy Pipeline Integration

### Runtime owner

The production economy runtime is `tick_economy()` (Rust FFI, `ffi.rs:3497`) → `tick_economy_core()` (`economy.rs:368`). Python's `compute_economy()` is an oracle/test surface only. The delivery buffer is consumed internally by the Rust economy kernel from `AgentSimulator`'s own state — no additional Arrow batch is passed from Python. The Python call site for `tick_economy()` is unchanged.

### Hybrid pipeline

Steps in `tick_economy_core()` for hybrid mode:

1. **Production** — unchanged (per-region, per-good from terrain + population)
2. **Demand computation** — unchanged
3. **Pre-trade pricing** — unchanged (merchants need price signals)
4. **Consume delivery buffer** — replaces `allocate_trade_flow()`:
   - Compute `per_good_imports` from arrival_imports (post-decay) only (not returns)
   - Compute net mobility delta per region-slot: `arrival × (1 - decay) + returns - departures`
   - Track `transit_loss = sum(arrival_imports × TRANSIT_DECAY[good_slot])`
   - **Mobility deltas are NOT applied to stockpiles here** — they feed into step 6's single stockpile update
5. **Post-trade pricing** — uses agent-delivered volumes (post-decay) as realized trade flow
6. **Stockpile lifecycle (single application point)** — `stockpile += production + mobility_net_delta - consumption - storage_decay - cap_overflow`. Mobility deltas from step 4 are applied exactly once here, alongside all other terms. No separate pre-application.
7. **Signal derivation** — unchanged logic, inputs now reflect agent trade
8. **M43b observability** — derived from arrival_imports:
   - `imports_by_region[dest][category]` from arrival category rollups
   - `inbound_sources[dest]` from arrival source_region_ids (deduped, deterministic order)
   - `import_share`, `trade_dependent` from arrival-derived imports
9. **Oracle shadow** (new) — within `tick_economy_core()`, run the abstract trade allocation phase (Phase B) non-mutating and store results separately for convergence diagnostics. This is the same allocation math the abstract path uses, just not applied to stockpiles.

### Mode gating

The Rust economy kernel (`tick_economy()`) runs whenever `agent_bridge is not None` — this includes demographics-only, shadow, and hybrid modes. Only `--agents=off` skips it entirely.

M58b gates delivery buffer *application* by mode, not economy execution:

| Mode | Economy runs? | Trade flow source | Delivery buffer | Oracle shadow |
|------|--------------|------------------|-----------------|---------------|
| `--agents=off` | No | N/A | N/A | N/A |
| `demographics-only` | Yes | Abstract allocation (unchanged) | Populated (merchants tick), but ignored by economy — not applied to stockpiles | N/A |
| `shadow` | Yes | Abstract allocation (M58a behavior) | Populated (merchants tick), but ignored by economy — not applied to stockpiles | N/A |
| `hybrid` | Yes | Delivery buffer (M58b) | Active: consumed internally by economy tick, applied to stockpiles | Active: non-mutating |

`tick_agents()` runs in all agent modes and sets the merchant route graph unconditionally (`agent_bridge.py:806`). Merchants are spawned at init and move in demographics-only and shadow modes. The delivery buffer therefore accumulates in all agent modes. The distinction is at economy ingress: only hybrid mode consumes the buffer for stockpile truth. In demographics-only and shadow, the buffer accumulates (available for diagnostics via `get_delivery_diagnostics()`) but the economy kernel ignores it and uses abstract allocation.

**Buffer lifecycle in non-hybrid modes:** The buffer grows monotonically unless explicitly cleared. For M58b, non-hybrid modes clear the buffer at the same point hybrid would consume it (start of economy tick), discarding contents without applying. This prevents unbounded memory growth while keeping the diagnostic read available between tick and economy.

### Availability guard change

**Current** (`merchant.rs:33`): `available = stockpile - reserved - in_transit_out`

**M58b hybrid**: `available = stockpile - reserved - departure_debits[region][slot]`

Rationale: after Phase 2 drain, prior-turn departures are already debited from stockpile. `in_transit_out` tracks those same goods for conservation. Subtracting `in_transit_out` would double-count. `departure_debits` (un-drained portion) tracks only goods that departed since last drain — the correct exclusion set.

`is_overcommitted()` updated to match: `reserved + departure_debits > stockpile`.

### Merchant income coupling

In hybrid mode, `merchant_trade_income` is derived from realized arrival volumes aggregated by origin region. Merchants in region R earn income proportional to total goods delivered from R (post-decay). Feeds into Rust `wealth_tick` via existing RegionState FFI path.

---

## Section 3: Conservation Model & Diagnostics

### Per-region, per-good-slot stockpile invariant

```
stockpile[r][g]_{T+1} = stockpile[r][g]_T
    + production[r][g]
    - consumption[r][g]
    - storage_decay[r][g]
    + arrival_imports[r][g] * (1 - TRANSIT_DECAY[g])
    - departure_debits[r][g]
    + return_credits[r][g]
    - cap_overflow[r][g]
```

Category rollups computed from per-good totals for observability and convergence diagnostics.

### Global in-transit flow identity

```
in_transit_{T+1} = in_transit_T + departures_T - arrivals_T - returns_T
```

Validated by comparing Rust `sum(in_transit_out)` against cumulative stream deltas from the delivery buffer.

### Existing conservation fields preserved

M43a's `EconomyResult.conservation` structure is extended, not replaced:

| Field | Source | M58b change |
|-------|--------|-------------|
| `production` | Existing | Unchanged |
| `transit_loss` | Existing (material decay in transport) | Now includes agent transit decay: `sum(arrival_imports * TRANSIT_DECAY[g])` |
| `consumption` | Existing | Unchanged |
| `storage_loss` | Existing | Unchanged |
| `cap_overflow` | Existing | Unchanged |
| `clamp_floor_loss` | Existing | Unchanged |
| `in_transit_delta` | **New** | `departures - arrivals - returns` (in-flight inventory change per turn) |

`transit_loss` retains its M43a semantics (material decay). In hybrid mode, it's populated from agent arrival decay instead of abstract allocation decay.

### Enforcement tiers

| Context | Tolerance | Action |
|---------|-----------|--------|
| Unit/integration tests | <= 1e-6 per region-slot, <= 1e-5 global turn total | Hard assert failure |
| Production/sim runs | Any imbalance | Clamp negative stockpiles to 0, log repair event, continue |
| 200-seed gate | See thresholds below | Fail milestone even if all runs complete |

### Per-turn structured diagnostics

Appended to bundle metadata per turn:

- `conservation_error_abs_turn` — absolute imbalance this turn
- `conservation_error_abs_cumulative` — running sum across turns
- `conservation_repair_events` — count of negative-stockpile clamps this turn
- `max_region_slot_error_turn` — worst single region-slot imbalance this turn
- `in_transit_total` — total goods currently in flight
- `delivery_buffer_pending` — total un-drained departure_debits:
  - **Pre-Phase-2 check:** logged as diagnostic (expected non-zero if merchants departed)
  - **Post-Phase-2 check:** must be zero (non-zero = failed drain → `conservation_repair_events`)

---

## Section 4: Convergence Gate & Test Plan

### Gate structure

200 paired seeds, 500 turns, `--agents hybrid` with oracle shadow. Compare hybrid realized trade against oracle (abstract allocation run non-mutating in same run). Evaluate turns >= 100.

**NOT** hybrid vs `--agents=off` (off mode doesn't run the economy kernel).

### Staged execution

1. **20-seed smoke** (500 turns): all per-seed criteria must pass on >= 75% of seeds. Conservation thresholds must hold. Run first.
2. **200-seed full gate** (500 turns): full convergence criteria + conservation + tail guard. Only runs after smoke passes.

### Per-seed pass criteria

| Category | Metric | Criterion |
|----------|--------|-----------|
| Price gradient | Spearman rank correlation of per-region post-trade margin vector (realized vs oracle) | >= 0.80 median over sampled turns (every 10 turns, turns >= 100) |
| Price magnitude | Median relative error of post-trade margin | <= 30% |
| Trade volume | Median agent/oracle volume ratio per category | In [0.75, 1.25] |
| Trade volume (tail) | p90 agent/oracle volume ratio | In [0.60, 1.40] |
| Food sufficiency (mean) | Absolute delta of mean food_sufficiency (realized vs oracle) | <= 0.10 |
| Food sufficiency (crisis) | Delta of crisis rate (food_suff < 0.8) | <= 3 percentage points |

### Milestone pass criteria

- At least **75% of seeds** pass all three categories (price, volume, food)
- **Tail guard:** fewer than 5% of seeds violate food crisis delta by more than 8 percentage points

### Conservation gate thresholds

| Metric | Threshold |
|--------|-----------|
| Median cumulative conservation error (200 seeds) | <= 1e-4 |
| p95 cumulative conservation error | <= 1e-2 |
| Median repair events per seed | 0 |
| p95 repair events per seed | <= 2 |
| `delivery_buffer_pending` post-Phase-2 | 0 across all seeds |

### Sidecar extension

New economy section in `SidecarWriter`:
- `economy_turn_NNN.json` per sampled turn (every 10 turns after turn 100)
- Contains: `oracle_trade_volume_by_category`, `agent_trade_volume_by_category`, `post_trade_margin_by_region`, `food_sufficiency_by_region`, `imports_by_region_by_category`, `conservation_error_abs_turn`
- Consolidated into `validation_economy.arrow` at run end for gate evaluation

### Unit tests (hard assertion)

- Per-good conservation exact balance (epsilon <= 1e-6 per region-slot)
- Global turn conservation (epsilon <= 1e-5)
- Delivery buffer zeroed after successful economy tick (post-tick buffer = zero)
- `available()` formula correctness with `departure_debits`
- Three-stream accounting: `in_transit_delta = departures - arrivals - returns`
- Transit decay applied to arrivals only (returns full-value)
- Drain/apply transactionality: if economy tick fails after buffer read, buffer is NOT zeroed (goods preserved for retry)

### Integration tests

- Multi-turn delivery: merchant departs turn T, arrives turn T+N, stockpile truth updates at T+N+1 Phase 2
- Disruption return: mid-transit unwind → `return_credits` applied to origin stockpile (full value, no decay)
- `--agents=off` non-regression: no M58b code path touched, Phase 4 bit-identical output
- Determinism replay: same seed produces identical delivery buffer contents and stockpile outcomes
- Oracle shadow: abstract allocation runs alongside hybrid without mutation, produces comparable outputs
- Conservation multi-turn: 10+ turn run, verify `in_transit_delta` identity and stockpile invariant hold every turn

---

## File Map

| File | M58b changes |
|------|-------------|
| `chronicler-agents/src/merchant.rs` | DeliveryBuffer struct, departure_debits accumulation, availability guard change, non-hybrid clear method |
| `chronicler-agents/src/economy.rs` | Hybrid trade flow ingress (consume delivery buffer), oracle shadow path, transit_loss from agent decay |
| `chronicler-agents/src/ffi.rs` | `tick_economy()` extended to consume delivery buffer internally in hybrid mode; `get_delivery_diagnostics()` for testing; return batches extended with delivery-applied quantities |
| `chronicler-agents/src/tick.rs` | Wire delivery buffer population into merchant phase events (depart/arrive/unwind) |
| `src/chronicler/simulation.py` | Phase 2: `tick_economy()` call unchanged; economy result reconstruction extended for delivery diagnostics |
| `src/chronicler/agent_bridge.py` | Hybrid mode flag propagation, delivery diagnostics retrieval, economy result reconstruction for delivery fields |
| `src/chronicler/sidecar.py` | Economy sidecar section (per-turn + consolidated Arrow) |
| `src/chronicler/analytics.py` | Conservation diagnostics extraction |
| `chronicler-agents/tests/test_merchant.rs` | Delivery buffer unit tests, availability guard tests |
| `tests/test_merchant_mobility.py` | Integration tests (multi-turn delivery, conservation, oracle shadow) |
