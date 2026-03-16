# M29: Scale & Performance — Design Spec

## Overview

M29 is a measurement-driven optimization milestone. No new simulation features — the goal is to scale the existing Rust agent model from ~6,000 to 10,000+ agents while meeting strict tick-time budgets, using profiling data to guide every optimization decision.

## Scope & Phasing

M29 is split into two phases with a hard gate between them.

### Phase A — Pre-M28 (start now)

Safe to implement before oracle gate validation because none of this work depends on finalized formula coefficients or decision thresholds.

1. **Profiling infrastructure** — Extend `tick_bench.rs` with a benchmark matrix, add flamegraph harness, add 500-turn timed integration test as macro regression gate.
2. **Phase 1 parallelization** — Parallelize satisfaction computation per-region via rayon. Phase 0 (skill growth) left sequential unless profiling justifies it.
3. **Profile-driven investigations** — Arrow FFI overhead, cache efficiency after mortality spikes, compaction if warranted.

### Phase B — Post-M28 Gate

Gated on M28 oracle gate passing. The satisfaction formula, decision thresholds, and coefficient values must be finalized before this work begins.

4a. **SIMD satisfaction verification** — Check whether the existing branchless formula auto-vectorizes; explicit SIMD only if it doesn't.
4b. **Decision short-circuit tuning** — Optimize branch ordering based on finalized formula.
4c. **Deferred Phase A findings** — Implement any optimizations flagged but deferred during Phase A (Arrow zero-copy, etc.).

### What M29 Does NOT Do

- No new simulation features (agents and behavior are M25–M27)
- No constant tuning (covered by M27)
- No algorithmic changes to decision logic (covered by M26)
- No narrative enrichment (that's M30)
- No new agent fields or pool structure changes (compaction rearranges existing slots but does not change the pool's field set or SoA layout)

## Benchmark Matrix & Profiling Infrastructure

### Starting Point

Extend the existing `tick_bench.rs` (currently benchmarks a single 6K/24-region configuration). Do not build from scratch.

### Benchmark Matrix

Criterion micro-benchmarks at these configurations, respecting the ~500 agents/region cap:

| Agents  | Regions | Category     | Agents/Region |
|---------|---------|--------------|---------------|
| 6,000   | 24      | realistic    | 250           |
| 10,000  | 24      | realistic    | 417           |
| 10,000  | 40      | realistic    | 250           |
| 15,000  | 40      | realistic    | 375           |
| 10,000  | 10      | stress test  | 1,000         |

15K included as headroom — shows where the next scaling wall is.

### Which Functions to Benchmark

The flamegraph runs first. Criterion benchmarks are then written targeting whatever the flamegraph identifies as hotspots — not a predetermined list. The four benchmarks in the Phase 5 roadmap (`tick_region_agents`, `compute_satisfaction`, `apply_migrations`, `compute_aggregates`) are hypotheses, not commitments.

### Macro Regression Gate

A 500-turn timed integration test (not criterion) at 6K/24 and 10K/24. Purely Rust-side: 500 ticks plus partition/event overhead, no Python orchestration. Run via `cargo test --release` with a `#[ignore]` gate so it doesn't slow CI. Report the median of 3 runs; target must be met on all 3. The headroom between tick targets (e.g., 500 × 3ms = 1.5s) and macro targets (3s) accounts for per-turn overhead (partition, event allocation, region stats) which is measured but not independently targeted.

### Flamegraph Harness

A binary target (e.g., `examples/flamegraph_run.rs`) that runs 500 turns at a configurable agent/region count, suitable for `cargo flamegraph`. Outputs tick-time breakdown per phase.

### Reference Hardware

AMD Ryzen 9 9950X. All performance targets and benchmark results are for this machine. Document specs in a benchmark README.

## Phase 1 Parallelization

### Target

Phase 1 (satisfaction) currently iterates all alive agents sequentially. It reads multiple SoA arrays per agent (loyalty, skill, occupation, region stats) and writes to the satisfaction array. This is the primary structural optimization candidate.

### Approach

Partition agents by region (same pattern as Phases 2-4), run satisfaction computation per-region in parallel via rayon. Each region's agents only read their own region's stats, so there are no cross-region data dependencies during computation.

### What Changes

- `tick.rs` Phase 1 block: refactored from a single loop over all agents to a `par_iter` over region partitions.
- Region stats (needed as read-only input): pre-computed once before the parallel pass. The tick's region-stats step already does this — reuse that infrastructure.
- Parallel writes to `pool.satisfactions` are safe without synchronization: each region's partition writes to disjoint slot indices, so no two threads touch the same element. This differs from the decisions phase (which collects results for sequential application) because satisfaction is a pure per-agent write with no cross-agent dependencies.
- No changes to the satisfaction formula itself.

### Phase 0 (Skill Growth)

Left sequential unless the flamegraph shows it's material. At 10K agents it's a ~40KB linear pass over one `f32` vec — likely faster than rayon dispatch overhead.

### Validation

Before/after flamegraph comparison. The 500-turn macro test confirms the overall tick time improved.

## Profile-Driven Investigations (Phase A)

Three investigations, all triggered by profiling data, not pre-committed.

### 3a. Arrow FFI Overhead

Measure the copy cost in `ffi.rs` (SoA vecs → Arrow builders). At 10K agents the serialization touches ~420KB of SoA data across ~10 column builders — expected to be sub-millisecond.

- **If sub-millisecond:** Document the measurement and move on.
- **If unexpectedly slow:** Refactor Rust side to wrap `Vec` buffers directly via pyo3-arrow's zero-copy path. Python side stays unchanged.

Expected outcome: non-issue.

### 3b. Cache Efficiency After Mortality Spikes

After high-mortality turns, dead slots scatter across SoA arrays. Measure whether this causes measurable cache-miss degradation.

**Measurement method:** Synthetically create two identical pools at 10K agents:
- **Packed:** All alive agents contiguous at the front of the SoA arrays.
- **Scattered:** Alive agents distributed across 15K slots with dead gaps (simulates peak pool size after a high-birth era followed by ~33% mortality).

Benchmark the same tick on both pools. This isolates the cache effect from gameplay noise (decision paths, migration counts, birth rates all vary per-turn and would confound a live comparison).

### 3c. Compaction (Contingent on 3b)

If 3b shows a real cache-miss problem: implement periodic full compaction every N turns (N=50 as starting point). O(n) copy, one tick's cost amortized over 50.

**Compaction is safe between ticks.** The `ids` array provides stable agent identity. `AgentEvent` uses `agent_id` (the monotonic ID from `pool.ids`), not slot index. Snapshots export via `get_snapshot()` which iterates alive slots and reads `ids[slot]`. Nothing caches slot indices between ticks. Compaction between ticks can freely rearrange slots without breaking any external references.

## Phase B — Post-M28 Formula-Coupled Optimizations

### Gate

M28 oracle gate passes. Satisfaction formula, decision thresholds, and coefficient values are finalized.

### 4a. SIMD Satisfaction Verification

The satisfaction formula is already branchless (M26 implemented `as f32` boolean casts for auto-vectorization). The work here is:

1. Check with `cargo asm` whether the existing branchless code auto-vectorizes.
2. If yes: done, no work needed.
3. If no: try explicit SIMD via the `wide` crate.

This is verification and a potential small fix, not a rewrite.

### 4b. Decision Short-Circuit Tuning

The decision evaluation loop in `behavior.rs` evaluates decisions per-agent with early exits. Optimize the branch ordering based on the finalized formula — put the most-common rejection case first.

### 4c. Deferred Phase A Findings

If Arrow FFI or compaction were flagged as issues in Phase A but deferred, implement them here.

### Scope Boundary

Phase B does not introduce new simulation features, new agent fields, or changes to the pool structure. Strictly optimizing the math and control flow of the finalized model.

## Performance Targets

| Metric                  | Target   | Notes                              |
|-------------------------|----------|------------------------------------|
| Tick time (6K/24)       | < 3 ms   | Reference hardware (9950X)         |
| Tick time (10K/24)      | < 5 ms   | Primary scaling target             |
| Memory per agent        | ~42 bytes| Already met; monitor, don't reduce |
| 500-turn run (6K/24)    | < 3 s    | Macro regression gate              |
| 500-turn run (10K/24)   | < 6 s    | Scaling gate                       |
| Arrow FFI per tick      | < 0.5 ms | Expected to be well under          |

## Dependencies

- **M25–M26:** Landed.
- **M27 (System Integration):** In progress. Phase A does not depend on M27 landing.
- **M28 (Oracle Gate):** Phase A runs in parallel with M28. Phase B is gated on M28 passing. Profiling infrastructure from Phase A also serves M28 (tick-time breakdowns help interpret oracle divergences).
- **M30 (Narrative):** No dependency in either direction. M29 and M30 are independent.

## Deliverables

- Flamegraph analysis of 500-turn × 10K/24 run (before and after optimization)
- Criterion benchmarks targeting flamegraph-identified hotspots across the benchmark matrix
- 500-turn timed integration test (macro regression gate) at 6K/24 and 10K/24
- Flamegraph harness binary (`examples/flamegraph_run.rs`)
- Benchmark README documenting reference hardware specs and measurement protocol
- Arrow FFI overhead measurement (documented even if result is "non-issue")
- Cache-efficiency synthetic benchmark (packed vs. scattered pools)
- Before/after performance comparison report
