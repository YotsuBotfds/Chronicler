# M58b Pre-Spec Handoff: Merchant Mobility Macro Write-Back

## Scope Snapshot

- **Milestone:** M58b
- **Date:** 2026-03-29
- **Depends on:** M58a branch `feature/m58a-merchant-mobility`
- **Goal:** wire merchant mobility throughput into macro economy truth and validate convergence vs M42-M43 baselines.

M58a shipped the mobility substrate (route graph, pathfinding, trip state, shadow ledger, disruption handling, diagnostics) without mutating macro stockpiles. M58b should keep that substrate stable and add controlled macro integration.

## What M58a Already Implements

### Core mobility substrate

- Rust trip state on `AgentPool`:
  - `trip_phase`, `trip_dest_region`, `trip_origin_region`, `trip_good_slot`, `trip_cargo_qty`, `trip_turns_elapsed`, `trip_path`, `trip_path_len`, `trip_path_cursor`
- Merchant phase at tick **0.9** in `tick_agents`:
  - disruption check/replan/unwind
  - loading invalidation + departure
  - one-hop transit move per turn
  - arrival processing
  - route evaluation + reservation
  - per-turn diagnostics collection
- Shadow ledger (`reserved`, `in_transit_out`, `pending_delivery`) in Rust.

### Python/Rust bridge seams

- Python builds route graph each turn (`build_merchant_route_graph`) and sends edge-list batch to Rust.
- Rust consumes graph via `set_merchant_route_graph`.
- Merchant diagnostics exposed via `get_merchant_trip_stats` and appended to bundle metadata.

### Integration and exclusion rules landed

- `compute_region_stats` excludes `trip_phase != Idle`.
- Decision loop excludes `trip_phase != Idle`.
- Household consolidation skips on-trip spouses/agents.
- Spatial drift and spatial grid population skip `trip_phase != Idle`.
- Economy merchant count uses anchor rule for transit merchants (`trip_origin_region`).

### Market attractor activation

- Market attractor always allocated at init.
- Merchant affinity to market enabled.
- Dynamic EMA weight from `trade_route_count` + `merchant_margin`.

## M58a Behavior That Is Intentionally Non-Conservative

M58a is shadow-mode for completed deliveries:

- Loading/transit reservations are conserved in ledger.
- On arrival, cargo moves to `pending_delivery` (diagnostic accumulator).
- Macro stockpile is not decremented/credited by merchant delivery path in M58a.

Result: completed deliveries are visible as throughput but not yet coupled into stockpile truth. This is expected and is the primary M58b handoff seam.

## Patch Applied During Review (Important for M58b Assumptions)

- Fixed merchant route suspension gating in `build_merchant_route_graph`:
  - endpoint `"trade_route"` suspensions now block edges for both cross-civ and intra-civ traversal.
  - prior logic incorrectly keyed suspensions by adjacent region name and only in cross-civ branch.
- Added regression coverage:
  - `test_route_suspension_blocks_cross_civ_edges`
  - `test_route_suspension_blocks_intra_civ_edges`

## Operational Gotcha

- New PyO3 methods in M58a (`set_merchant_route_graph`, `get_merchant_trip_stats`) require rebuilding/reinstalling the Rust extension.
- If a stale `.pyd` is loaded, Python tests may fail with `AttributeError` even when source code is correct.

## M58b Must Own

### 1) Macro write-back from shadow delivery

Define the exact consumption/write-back contract for `pending_delivery`:

- when and where delivered goods become macro stockpile truth
- how to avoid double-counting vs origin reservation semantics
- whether write-back is immediate per turn or buffered by settlement/market mechanics

### 2) Conservation model and invariants

Upgrade from "in-flight conservation" to end-to-end macro conservation:

- conservation checks should include produced, transported, delivered, consumed, decayed
- failure mode should be bounded (diagnostic + clamp/block policy)

### 3) Route profitability semantics

M58a scores routes with a coarse bilateral margin proxy. M58b should decide:

- goods-specific destination demand signal
- transport-cost-aware ranking (if enabling weighted path choice)
- whether to introduce periodic economic re-evaluation in transit

### 4) Economic coupling blast radius

M58b should explicitly define and validate impacts on:

- stockpile trajectories
- price stabilization/volatility
- faction and satisfaction downstream signals that depend on economy outputs

### 5) Calibration and convergence gates

Add gate criteria for macro parity and stability:

- before/after comparisons against post-M57 baseline and M42-M43 expectations
- 200-seed drift checks for key economy metrics
- explicit acceptance bounds for variance increases

## Recommended M58b Spec Decisions (Lock Early)

1. **Write-back timing:** end-of-economy-turn batch application vs immediate per-arrival.
2. **Ledger lifecycle:** whether `pending_delivery` is drained fully each turn or partially by capacity.
3. **Failure policy:** if destination cannot absorb delivery (capacity/price shock), store, reroute, or decay.
4. **Price source:** keep perfect-info for M58b or begin staged stale-knowledge hooks.
5. **Replan trigger policy:** disruption-only remains, or add periodic profitability checks.
6. **Diagnostics expansion:** add macro-coupled counters (delivered_to_stockpile, dropped_delivery, backpressure events).

## Suggested Test Additions for M58b

- End-to-end conservation test with multi-turn delivery + macro write-back.
- Route-to-stockpile integration test (arrival actually changes destination stockpile truth).
- Backpressure/overflow test (delivery exceeds target absorption assumptions).
- Economy regression test comparing pre/post M58b distributions (not just spot values).
- Determinism replay for merchant diagnostics plus macro stockpile outputs.
- `--agents=off` unchanged baseline check.

## File Map for M58b Spec Writer

- Mobility core: `chronicler-agents/src/merchant.rs`
- Tick orchestration: `chronicler-agents/src/tick.rs`
- FFI + economy bridge points: `chronicler-agents/src/ffi.rs`
- Route graph builder: `src/chronicler/economy.py`
- Python bridge integration: `src/chronicler/agent_bridge.py`
- Bundle metadata hook: `src/chronicler/main.py`
- M58a integration tests: `chronicler-agents/tests/test_merchant.rs`, `tests/test_merchant_mobility.py`

## Bottom Line

M58a gives M58b a stable, deterministic transport substrate with diagnostics and enforced movement semantics. The remaining work is economic truth integration and convergence governance, not movement mechanics.
