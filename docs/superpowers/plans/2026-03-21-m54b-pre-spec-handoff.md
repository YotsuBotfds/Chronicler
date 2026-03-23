# M54b Pre-Spec Handoff

> Date: 2026-03-21
> Purpose: fast context pack for brainstorming `M54b` before `M54a` lands and establishes the concrete migration contract.

## Status Snapshot

- There is no dedicated `M54b` spec or implementation plan in the repo yet.
- The canonical roadmap defines `M54b` as **Rust Economy Migration** with a 10-14 day estimate.
- The roadmap is explicit that `M54a` should establish the Arrow-batch-in / Arrow-batch-out migration pattern for later phase migrations.
- The roadmap gate for `M54b` is stronger than `M54a`: **determinism + conservation law verification**.
- The viability-adjustments memo does not materially change `M54b` scope. It mainly reshuffles dependencies around spatial work and `M54c`.

## Recommendation Context

My recommendation is:
- do a **pre-spec now**
- wait to do the **full implementation spec** until `M54a` proves the real Rust/Python contract

Reason:
- `M54b` is more coupled than `M54a`
- it mutates persistent world state, feeds same-turn Rust signals, updates cross-turn analytics state, and also powers later Python consumers like action weighting and narration
- if `M54a` changes the conventions for result batches, write-back, patch sync, config storage, or determinism harness shape, a full `M54b` spec written now will likely churn

What is stable enough to lock now:
- scope boundary
- non-goals
- invariants
- current state/consumer seams
- the big open design questions

What should wait for `M54a`:
- exact Arrow schemas
- exact FFI entry point signatures
- whether post-pass sync uses write-back only or write-back plus patch batches
- the exact return shape for fixed rows vs variable events/diagnostics
- shared helper abstractions in `ffi.rs` and `agent_bridge.py`

## What The Docs Currently Say

### Canonical roadmap meaning

Primary reference:
- `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

Current roadmap wording:
- `M54b` = economy migration
- hardest of the three phase migrations
- complexity comes from transport costs, perishability, stockpiles, conservation law tracking, shock detection, trade dependency classification, and the raider modifier
- trade flow has real cross-region dependencies, so this is not as embarrassingly parallel as ecology
- explicit migration note: `EconomyTracker` state must either live in Rust or round-trip through Python
- explicit roadmap caveat: `EconomyResult.conservation` may stay Python-side because it is validation infrastructure, not gameplay logic

### Dependency shape

Reference:
- `docs/superpowers/plans/2026-03-20-phase7-viability-adjustments.md`

Important point:
- the memo keeps `M54b` as its own standalone migration milestone
- unlike the spatial-sort question, there is no major docs conflict about what `M54b` is

Inference:
- `M54b` is a good target for a clean pre-spec now, but not for a deeply committed implementation contract yet

## Current Code Reality

### Economy runs early and fans out widely

Primary files:
- `src/chronicler/simulation.py`
- `src/chronicler/economy.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/narrative.py`

Current Phase 2 sequence in `run_turn()`:
1. `compute_economy()` runs before automatic effects and long before the Rust agent tick
2. it mutates `Region.stockpile.goods` in place
3. it returns `EconomyResult`
4. the bridge stores that result for same-turn signal wiring
5. `EconomyTracker` EMAs are updated from current stockpile/import state
6. `detect_supply_shocks()` emits Python `Event` objects
7. treasury tax is routed through the accumulator
8. later consumers read the result again in action selection and narration

Important consequence:
- `M54b` is not just "move one hot function"
- it is a migration of a shared Phase 2 state producer with multiple downstream consumers

### `compute_economy()` owns the heavy path today

Primary file:
- `src/chronicler/economy.py`

The Python economy path currently does all of this:
- snapshot extraction from Rust agent state arrays
- per-region production and demand computation
- pre-trade pricing
- boundary-pair trade-route decomposition
- transport-cost computation
- tatonnement price iteration
- trade flow allocation
- per-good transit decay
- stockpile accumulation
- food sufficiency from pre-consumption stockpile
- stockpile consumption
- storage decay with salt preservation
- stockpile caps
- trade dependency classification
- post-trade signal derivation
- civ-level treasury/tithe outputs in agent mode

This is the real hot-path candidate for Rust migration.

### The economy phase already has persistent material state

Primary files:
- `src/chronicler/models.py`
- `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md`
- `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`

Persistent state today:
- `Region.stockpile.goods` is durable world state
- `EconomyTracker` is durable run-state but explicitly **not** world state
- `world._economy_result` is a transient one-turn artifact for later consumers

Important difference from `M54a`:
- economy already has both durable simulation state and durable analytics state, and they live in different places

## Current Consumer Map

### Same-turn Rust bridge consumers

`AgentBridge.build_region_batch()` currently reads `EconomyResult` to populate:
- `trade_route_count`
- `farmer_income_modifier`
- `food_sufficiency`
- `merchant_margin`
- `merchant_trade_income`

`AgentBridge.build_signals()` currently reads `EconomyResult` to populate:
- `priest_tithe_share`

These are not optional side data. They feed the same-turn Rust agent tick.

### Same-turn Python consumers

`simulation.py` currently uses `EconomyResult` for:
- `EconomyTracker` updates
- `detect_supply_shocks()`
- treasury tax routing through `StatAccumulator`
- `world._economy_result` stash for later phases

`action_engine.py` uses `world._economy_result` for:
- the M43b raider WAR modifier

`narrative.py` / context builders use `EconomyResult` for:
- trade dependency context
- active supply shock context

Inference:
- a full `M54b` design must account for both Rust-facing signal delivery and Python-facing narrative/strategy consumers

## State Categories Worth Locking Now

### Persistent simulation state

These are the pieces that feel most like eventual Rust-owned state:
- `Region.stockpile.goods`
- any deterministic per-route / per-region trade bookkeeping needed to produce same-turn signals

### Persistent analytics state

These are cross-turn, but not core world state:
- `EconomyTracker.trailing_avg`
- `EconomyTracker.import_avg`

This is the cleanest open boundary in the milestone.

### Transient per-turn outputs

Today `EconomyResult` mixes several kinds of data:

Core same-turn signals:
- `farmer_income_modifiers`
- `food_sufficiency`
- `merchant_margins`
- `merchant_trade_incomes`
- `trade_route_counts`
- `priest_tithe_shares`
- `treasury_tax`
- `tithe_base`

Cross-region observability / shock inputs:
- `imports_by_region`
- `inbound_sources`
- `stockpile_levels`
- `import_share`
- `trade_dependent`

Diagnostics:
- `conservation`
- `region_goods`

This mixed result shape is one reason not to over-spec the FFI contract before `M54a`.

## Likely Migration Boundary

My current lean for the first `M54b` cut:

### Likely Rust-owned core

- production and demand extraction
- route decomposition and transport costs
- tatonnement loop
- trade flow allocation
- per-good transit decay
- stockpile accumulation / drawdown / decay / cap
- final same-turn region signals
- civ-level tithe / treasury outputs

### Likely Python-side post-pass or consumer layer

- `EconomyTracker` update
- `detect_supply_shocks()` event materialization
- `world._economy_result` or successor transient for action/narration consumers
- conservation-law assertion/reporting if it stays diagnostic-only

Reason for this lean:
- the hot compute is in the trade / stockpile / signal path
- `EconomyTracker` and shock-event narration are cross-turn analytics / storytelling infrastructure, not the main throughput win
- the roadmap already hints that `conservation` may not be worth migrating as full gameplay state

This is not a final design decision, but it is the cleanest current boundary.

## Biggest Design Questions

### 1. Where does `EconomyTracker` live after migration?

Options:
- Rust-owned persistent state on the simulator
- Python-owned tracker fed by Rust-returned observables
- mirrored state with round-trip each turn

My current lean:
- keep it Python-side for the first migration
- let Rust return the current-turn observables needed to update it deterministically

Why:
- it is not core world state
- it is not currently consumed by Rust
- keeping it Python-side avoids committing `M54b` to a cross-turn analytics ownership model before `M54a` even proves the basic phase-migration seam

### 2. What happens to `EconomyResult.conservation`?

Roadmap already calls this out as optional.

The real question:
- is conservation a Rust-owned result payload
- or a Python-side verification layer that recomputes/checks aggregates from Rust output

My current lean:
- keep it explicit and testable, but do not force it to become durable Rust-side state

### 3. What is the return shape?

This should wait for `M54a`, but the data naturally falls into at least three buckets:
- fixed one-row-per-region outputs
- fixed one-row-per-civ outputs
- variable diagnostic or trigger rows

Inference:
- `M54b` is likely to need more than a single flat result object
- but the exact batch breakdown should follow the `M54a` precedent, not invent a competing pattern now

### 4. How is trade flow parallelized without losing determinism?

This is the hardest technical part of the milestone.

Unlike ecology:
- route decomposition depends on cross-region adjacency
- price iteration and imports/exports are global per-pass structures
- route-order differences can change floating-point accumulation order

Any real design will need:
- a stable route ordering
- deterministic accumulation order
- phase barriers between tatonnement passes
- a clear story for per-origin parallel work vs synchronized reductions

### 5. What is authoritative mutable state after Rust returns?

At minimum the design has to answer:
- does Rust mutate stockpiles in-place and return the new per-region stockpile state for Python mirroring
- or does Python remain the authoritative stockpile owner and apply Rust deltas

This is the same ownership question as `M54a`, but with a more consequential persistent payload.

## Invariants The Agent Should Not Lose

- Conservation law is a real milestone gate, not a nice-to-have.
- `food_sufficiency` is still defined from **pre-consumption stockpile**, not single-turn production.
- `trade_dependent` is based on `food_imports / max(food_demand, 0.1)`, not stockpile depth.
- Raider logic uses the **max adjacent enemy food stockpile**, not the sum.
- Actor ordering for supply shocks is affected civ first, upstream civ second.
- `world._economy_result` is intentionally transient and overwritten each turn.
- Same-turn Rust consumers still need `food_sufficiency`, `merchant_margin`, `merchant_trade_income`, `trade_route_count`, and `priest_tithe_share`.
- `--agents=off` must remain behaviorally compatible.
- Any new transient crossing the Python/Rust boundary needs the usual multi-turn reset test.

## Good Oracle Sources

- `tests/test_economy.py`
- `tests/test_economy_m43a.py`
- `tests/test_economy_m43b.py`
- `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md`
- `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`

These already encode the important economics decisions:
- stockpile ordering
- salt preservation
- trade dependency definition
- EMA behavior
- shock actor ordering
- raider modifier semantics
- transient overwrite expectations

## Suggested Next Output

If the next agent wants a focused deliverable before `M54a` lands, I would aim for:
- a 1-2 page `M54b` pre-spec
- explicit scope / non-goals
- a state classification table: persistent world state vs persistent analytics state vs per-turn outputs
- a consumer map: Rust signals vs Python post-pass vs narration/strategy consumers
- a short section on "what waits for M54a"
- a short list of the 3-5 real open design questions

I would explicitly avoid, for now:
- freezing exact Arrow schemas
- freezing PyO3 method signatures
- committing to a specific write-back / patch contract
- fully speccing the determinism harness plumbing before `M54a` establishes the shared pattern
