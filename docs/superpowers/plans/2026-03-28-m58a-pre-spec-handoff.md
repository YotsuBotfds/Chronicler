# M58a Pre-Spec Handoff

> Date: 2026-03-28  
> Audience: spec-writing / question-gathering agent  
> Purpose: lock an implementation-ready spec for `M58a: Merchant Mobility`, and surface the smallest set of user decisions that materially affect architecture before spec freeze.

## Status Snapshot

- There is no dedicated `M58a` spec or implementation plan in the repo yet.
- Canonical roadmap: `M58a` is a Phase 7 scale-track milestone, estimate `3-4` days, depending on `M54b`, `M55a`, and `M42-M43`.
- Live baseline has already landed the prerequisites that matter most for `M58a`:
  - `M54a`, `M54b`, `M54c`
  - `M55a`, `M55b`
  - `M56a`, `M56b`
  - `M57a`, `M57b`
- `M58a` is explicitly the substrate half only:
  - merchant route choice
  - cargo reservation/loading
  - transit state over multiple turns
  - one-region-per-turn travel
  - diagnostics surface for movement/profitability
- `M58b` still owns:
  - macro write-back as the new trade truth
  - economy-level convergence against `M42-M43` baseline
  - final stale-vs-current price integration for macro calibration

## Canonical Requirements (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: merchants physically move goods through space.
- Mechanism:
  - evaluate candidate destinations from visible price differentials
  - choose route
  - reserve/load goods
  - travel one region per turn with spatial updates
  - keep transit state inspectable
- Compute profile: at ~50K merchants and ~5-10 candidate routes each, this is already a large parallel workload.
- Required diagnostics:
  - route choice distributions
  - in-transit goods
  - merchant trip duration
  - route profitability counters
- Gate: movement and transit state are coherent and inspectable before macro trade truth changes.

Additional roadmap context that matters:
- `M42-M43` remains the macro specification (decision `D6`) and regression baseline.
- `M58b` is where delivery/write-back and macro convergence are validated.
- Risk register already flags likely `M58` enrichment scope creep (dynamic routes/gravity model). Build extension seams, but do not let enrichment block a first-cut `M58a` substrate.

## Current Code Reality (Live Baseline)

### Economy/trade is currently aggregate and immediate

- `src/chronicler/simulation.py` routes Phase 2 economy through Rust `tick_economy(...)` when agent mode is active.
- `chronicler-agents/src/economy.rs` allocates region-level flows and applies exports/imports in the same turn (with transit decay), then derives `merchant_margin` and `merchant_trade_income`.
- `chronicler-agents/src/tick.rs` wealth update consumes `region.merchant_trade_income`; there is no per-agent cargo/trip ledger.

### Route input exists, but only as aggregate topology

- `src/chronicler/resources.py::get_active_trade_routes()` yields civ-pair routes based on adjacency/relations/embargo.
- `src/chronicler/economy.py::build_economy_trade_route_batch()` decomposes those into boundary region pairs + `is_river`.
- Merchants do not currently choose or persist explicit route plans.

### Spatial seam is ready, including a reserved market attractor slot

- `chronicler-agents/src/spatial.rs` already defines `AttractorType::Market` as reserved/inactive.
- Merchant affinity currently has no market pull (market column effectively zeroed until `M58a` activation).
- Pool/snapshot already expose per-agent `x`, `y`, `region`, `occupation`, and `settlement_id`.

### Merchant mobility state does not exist yet

- `chronicler-agents/src/pool.rs` has no per-agent trade-trip fields (`destination`, `cargo`, `turns_remaining`, `trip_phase`, etc.).
- `chronicler-agents/src/ffi.rs::snapshot_schema()` exports no merchant-trip or cargo columns.
- `src/chronicler/models.py::RegionStockpile` has only `goods`; no reservation ledger.

### Diagnostics are currently macro-level only

- Existing outputs: route counts, import shares, stockpile levels, merchant margin/income.
- Missing outputs requested by roadmap: route choice distribution, in-transit inventory, trip duration, per-trip profitability.
- Existing metadata pattern (`relationship_stats`, `household_stats`) is a practical first surface for `M58a` diagnostics without immediate heavy schema churn.

## Non-Negotiables To Preserve

- `D6` macro contract:
  - `M42-M43` abstract model remains the macro specification and baseline through `M58a`.
  - `--agents=off` must remain behaviorally stable.
- Determinism rules still apply:
  - no iteration-order randomness
  - explicit tie-break keys
  - canonical ordering before decisions/FFI/serialization
- RNG stream discipline:
  - roadmap reserves `1700` for merchant route selection
  - `agent.rs` does not yet define an `M58` offset, so the `M58a` spec should lock this explicitly.
- Any new transient Python->Rust signal must:
  - clear before return in the emitting builder
  - include a multi-turn reset integration test.
- Bundle consumers should stay agnostic to whether outcomes come from aggregate or agent-backed internals.
- Scope guard:
  - `M58a` should not absorb `M58b` macro-convergence responsibility.

## Recommended Architecture Lean

### 1. Rust-owned merchant mobility state machine

- Keep movement/travel state in Rust near the existing agent tick.
- Use explicit phases (idle/load/transit/arrive/unwind) with deterministic transitions.
- Keep one-region-per-turn travel in this milestone even if later milestones add richer path costs.

### 2. Explicit reservation + edge-resident transit state

- Use a reserve -> transport -> settle/unwind protocol.
- Represent in-transit goods as edge/trip records with `turns_remaining`.
- Include unwind paths for route invalidation, agent death, or destination invalidation.

### 3. Start with existing route topology, but keep extension seams

- First cut can use the already available boundary-pair/adjacency topology.
- Keep interfaces open for later dynamic route formation enrichments (gravity/Urquhart) without forcing them into `M58a`.
- Support per-turn route re-evaluation when profitability or route availability changes.

### 4. Ship instrumentation in the same milestone

- Emit route-choice/trip-duration/transit/profit counters as part of `M58a`, not deferred to `M61`.
- Prefer metadata-series surfaces first; add heavier snapshot schema fields only when replay/debug needs demand it.

## Scope Recommendation

In-scope for `M58a`:
- Merchant route candidate evaluation and deterministic selection.
- Cargo reservation/loading semantics.
- Multi-turn transit state and one-region-per-turn movement.
- Basic replanning/unwind behavior on disruption.
- Diagnostics required by the roadmap gate.

Out-of-scope for `M58a`:
- Replacing macro trade truth with merchant outcomes.
- Full macro convergence validation against `M42-M43`.
- Complex route optimization (full VRP solvers).
- Endogenous route-formation enrichments as required scope.
- Full stale-information economy coupling (core of `M59`/`M58b` integration).

## Likely File Touch Map

Python:
- `src/chronicler/simulation.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/economy.py`
- `src/chronicler/models.py`
- `src/chronicler/main.py`
- `src/chronicler/analytics.py`
- `src/chronicler/bundle.py` (if diagnostics schema/metadata contracts expand)

Rust:
- `chronicler-agents/src/agent.rs`
- `chronicler-agents/src/pool.rs`
- `chronicler-agents/src/tick.rs`
- `chronicler-agents/src/behavior.rs`
- `chronicler-agents/src/economy.rs`
- `chronicler-agents/src/ffi.rs`
- `chronicler-agents/src/spatial.rs` (market attractor activation details)
- `chronicler-agents/src/region.rs` (if regional reservation/transit counters are surfaced)

Tests:
- Python bridge/economy integration tests (`tests/test_agent_bridge.py`, economy/simulation coverage)
- New focused `M58a` integration tests (multi-turn travel, reserve/unwind, diagnostics)
- Rust tick/economy/ffi tests for route selection, transit lifecycle, determinism
- Explicit transient reset test for any new cross-boundary transient signal

## Design Decisions Agent Should Lock In The Spec

1. Where merchant mobility executes in the tick timeline and how it composes with existing migration logic.
2. Route candidate generation policy:
   - existing boundary-pair graph only
   - region adjacency expansion
   - optional early support for richer topology.
3. Replan cadence and trigger conditions (always per turn vs event-triggered only).
4. Cargo reservation substrate:
   - `RegionStockpile` extension
   - dedicated Rust ledger
   - hybrid/shadow path for `M58a` vs macro write-back in `M58b`.
5. Transit representation:
   - per-agent cargo fields
   - edge-resident trip records
   - or mixed model.
6. Disruption behavior:
   - embargo, war route invalidation, civ collapse, merchant death.
7. Relationship between trade travel and ordinary dissatisfaction-driven migration for merchants.
8. Market attractor activation policy (merchant-only vs broader occupations).
9. Diagnostics contract shape (bundle metadata vs per-turn snapshot fields vs both).
10. RNG usage for route tie-breaks and explicit stream offset registration.
11. Minimum viable performance strategy for 50K merchants (batching/partitioning expectations).
12. Exact `M58a`/`M58b` handoff contract so macro integration can plug in without redesign.

## High-Value Questions To Bring Back

These are the user decisions most worth asking explicitly. Recommended defaults are included so the spec can keep moving if answers are sparse.

1. Should `M58a` mutate macro stockpile truth immediately, or run a shadow reservation/transit ledger with diagnostics first and defer macro write-back to `M58b`?
   Recommended: shadow ledger in `M58a`, macro write-back in `M58b`.

2. Should first-cut route candidates stay on existing boundary-pair/adjacency topology, or pull dynamic route formation into `M58a` scope?
   Recommended: existing topology first, design an extension seam for dynamic routes.

3. Should merchants re-evaluate routes every transit turn or only at departure?
   Recommended: re-evaluate each transit turn with a profitability threshold gate.

4. Should merchant trade trips suppress ordinary migration decisions while trip state is active?
   Recommended: yes, trip state should take precedence to avoid conflicting movement semantics.

5. Should `Market` attractor be activated in `M58a` for merchants?
   Recommended: yes, merchant-only activation in `M58a` with conservative default weights.

6. Where should route/trip diagnostics live first?
   Recommended: bundle metadata time series first, add snapshot schema only where replay tooling requires it.

7. Should we include stale-price knowledge state in `M58a`, or defer to `M59` and only store placeholders now?
   Recommended: defer full stale-price behavior to `M59`, keep optional placeholders only if needed for clean interface continuity.

## Validation Expectations

- Unit tests:
  - deterministic route selection and tie-break behavior
  - reservation/unwind invariants (no double counting)
  - transit lifecycle state transitions
- Integration tests:
  - multi-turn merchant travel with one-region-per-turn movement
  - disruption paths (embargo/war/death) unwind correctly
  - diagnostics counters are emitted and stable
- Determinism tests:
  - cross-process same-seed replay
  - cross-thread replay if merchant evaluation is parallelized
- Compatibility tests:
  - `--agents=off` unchanged
  - `M42-M43` macro baseline still valid during `M58a`
- Transient tests:
  - any new transient cross-boundary signal must prove reset on subsequent turns.

## Expected Output From The Next Agent

- A single `M58a` implementation spec that:
  - uses current Rust-owned simulation seams and spatial substrate
  - defines merchant mobility + reservation/transit lifecycle clearly
  - codifies determinism/RNG/test requirements
  - draws a crisp boundary between `M58a` substrate and `M58b` macro convergence
- A short user-facing question set based on the 7 questions above, with recommended defaults and rationale.
