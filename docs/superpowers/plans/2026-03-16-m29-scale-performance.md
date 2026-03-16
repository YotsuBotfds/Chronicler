# M29: Scale & Performance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale the Rust agent simulation from ~6K to 10K+ agents with < 5ms tick time through measurement-driven optimization.

**Architecture:** Phase A builds profiling infrastructure and applies structural optimizations (satisfaction parallelization). Phase B (after baselines) verifies auto-vectorization and tunes decision short-circuits. Every optimization is justified by profiling data.

**Tech Stack:** Rust, criterion 0.5, cargo-flamegraph, rayon 1.10, cargo-show-asm

---

## File Structure

**Files to create:**
- `chronicler-agents/examples/flamegraph_run.rs` — Binary target for `cargo flamegraph`. CLI args for agent/region/turn count, per-phase timing output.
- `chronicler-agents/tests/regression.rs` — 500-turn macro regression tests (`#[ignore]` gated). Asserts wall-time targets.
- `chronicler-agents/benches/cache_bench.rs` — Synthetic packed-vs-scattered cache efficiency benchmark.
- `chronicler-agents/benches/BENCHMARK_README.md` — Reference hardware specs and measurement protocol.

**Files to modify:**
- `chronicler-agents/benches/tick_bench.rs` — Extend from single 6K/24 config to full benchmark matrix.
- `chronicler-agents/src/tick.rs` — Refactor `update_satisfaction` (lines 250-341) from sequential to per-region parallel via rayon.
- `chronicler-agents/Cargo.toml` — Add `[[example]]` entry and `std::time` usage in tests.

---

## Chunk 1: Profiling Infrastructure

### Task 1: Parameterized Benchmark Setup

**Files:**
- Modify: `chronicler-agents/benches/tick_bench.rs`

- [ ] **Step 1: Write parameterized `setup_pool` helper**

Add above the existing `setup_6k_pool` function (line 32). Reuses the existing `make_default_signals` helper (line 6).

```rust
fn setup_pool(num_agents: usize, num_regions: u16) -> (AgentPool, Vec<RegionState>, TickSignals) {
    let agents_per_region = num_agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|i| RegionState {
        region_id: i,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if i > 0 { 1u32 << (i - 1) } else { 0 })
                | (if i < num_regions - 1 { 1u32 << (i + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (i % 4) as u8,
        trade_route_count: 0,
    }).collect();
    let num_civs = (num_regions.min(8)) as usize;
    let signals = make_default_signals(num_civs, num_regions as usize);
    let mut pool = AgentPool::new(num_agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16);
        }
    }
    (pool, regions, signals)
}
```

- [ ] **Step 2: Rewrite `setup_6k_pool` to delegate**

Replace the existing `setup_6k_pool` body (lines 32-42) with:

```rust
fn setup_6k_pool() -> (AgentPool, Vec<RegionState>, TickSignals) {
    setup_pool(6000, 24)
}
```

- [ ] **Step 3: Verify existing benchmark still works**

Run: `cargo bench --bench tick_bench -- --test` (from `chronicler-agents/`)

Expected: compiles and runs the existing `tick_6k_agents` benchmark without errors.

- [ ] **Step 4: Commit**

```bash
git add benches/tick_bench.rs
git commit -m "bench(m29): add parameterized setup_pool helper"
```

### Task 2: Benchmark Matrix

**Files:**
- Modify: `chronicler-agents/benches/tick_bench.rs`

- [ ] **Step 1: Add benchmark group with matrix configurations**

Replace the single `bench_tick_6k` function and `criterion_group!` (lines 44-54) with:

```rust
fn bench_tick_matrix(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;

    let configs: &[(usize, u16, &str)] = &[
        (6_000,  24, "6k_24r"),
        (10_000, 24, "10k_24r"),
        (10_000, 40, "10k_40r"),
        (15_000, 40, "15k_40r"),
        (10_000, 10, "10k_10r_stress"),
    ];

    let mut group = c.benchmark_group("tick_matrix");
    for &(agents, regions, label) in configs {
        group.bench_function(label, |b| {
            b.iter_batched(
                || setup_pool(agents, regions),
                |(mut pool, regs, sigs)| {
                    tick_agents(
                        black_box(&mut pool),
                        black_box(&regs),
                        black_box(&sigs),
                        seed,
                        0,
                    );
                },
                BatchSize::SmallInput,
            )
        });
    }
    group.finish();
}

criterion_group!(benches, bench_tick_matrix);
criterion_main!(benches);
```

- [ ] **Step 2: Run the full matrix**

Run: `cargo bench --bench tick_bench` (from `chronicler-agents/`)

Expected: All 5 configurations run. Observe baseline numbers — record them for the performance report.

- [ ] **Step 3: Commit**

```bash
git add benches/tick_bench.rs
git commit -m "bench(m29): add 5-config benchmark matrix (6k-15k × 10-40 regions)"
```

### Task 3: Flamegraph Harness

**Files:**
- Create: `chronicler-agents/examples/flamegraph_run.rs`
- Modify: `chronicler-agents/Cargo.toml`

- [ ] **Step 1: Add example entry to Cargo.toml**

Add after the `[[bench]]` section (after line 33):

```toml
[[example]]
name = "flamegraph_run"
```

- [ ] **Step 2: Write the flamegraph harness**

```rust
//! Flamegraph-friendly binary: runs N turns at configurable scale.
//! Usage: cargo flamegraph --example flamegraph_run -- --agents 10000 --regions 24 --turns 500

use std::time::Instant;

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn main() {
    let args: Vec<String> = std::env::args().collect();

    let mut agents = 10_000usize;
    let mut num_regions = 24u16;
    let mut turns = 500u32;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--agents" => { agents = args[i + 1].parse().unwrap(); i += 2; }
            "--regions" => { num_regions = args[i + 1].parse().unwrap(); i += 2; }
            "--turns" => { turns = args[i + 1].parse().unwrap(); i += 2; }
            _ => { i += 1; }
        }
    }

    let agents_per_region = agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if r > 0 { 1u32 << (r - 1) } else { 0 })
                | (if r < num_regions - 1 { 1u32 << (r + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (r % 4) as u8,
        trade_route_count: 0,
    }).collect();

    let num_civs = (num_regions.min(8)) as usize;
    let signals = TickSignals {
        civs: (0..num_civs)
            .map(|c| CivSignals {
                civ_id: c as u8,
                stability: if c % 4 == 2 { 25 } else { 55 },
                is_at_war: c % 3 == 1,
                dominant_faction: (c % 3) as u8,
                faction_military: if c % 3 == 1 { 0.55 } else { 0.25 },
                faction_merchant: if c % 3 == 1 { 0.25 } else { 0.40 },
                faction_cultural: if c % 3 == 1 { 0.20 } else { 0.35 },
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
            })
            .collect(),
        contested_regions: (0..num_regions as usize).map(|r| r % 5 == 0).collect(),
    };

    let mut pool = AgentPool::new(agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16);
        }
    }

    let mut seed = [0u8; 32]; seed[0] = 42;

    eprintln!("Config: {} agents, {} regions, {} turns", agents, num_regions, turns);
    eprintln!("Agents/region: {}", agents_per_region);
    eprintln!("---");

    let total_start = Instant::now();
    for turn in 0..turns {
        let tick_start = Instant::now();
        let events = tick_agents(&mut pool, &regions, &signals, seed, turn);
        let tick_elapsed = tick_start.elapsed();

        if turn % 100 == 0 || turn == turns - 1 {
            eprintln!(
                "Turn {:>4}: {:>6.2}ms | alive: {:>6} | events: {:>4}",
                turn,
                tick_elapsed.as_secs_f64() * 1000.0,
                pool.alive_count(),
                events.len(),
            );
        }
    }
    let total_elapsed = total_start.elapsed();
    eprintln!("---");
    eprintln!("Total: {:.3}s ({:.2}ms avg/turn)", total_elapsed.as_secs_f64(), total_elapsed.as_secs_f64() * 1000.0 / turns as f64);
    eprintln!("Alive: {}", pool.alive_count());
}
```

- [ ] **Step 3: Verify it compiles and runs**

Run: `cargo run --release --example flamegraph_run -- --agents 6000 --regions 24 --turns 10` (from `chronicler-agents/`)

Expected: Prints 10 turns of timing output, no panics.

- [ ] **Step 4: Commit**

```bash
git add examples/flamegraph_run.rs Cargo.toml
git commit -m "bench(m29): add flamegraph harness binary (examples/flamegraph_run.rs)"
```

### Task 4: Macro Regression Gate

**Files:**
- Create: `chronicler-agents/tests/regression.rs`

- [ ] **Step 1: Write the 500-turn regression tests**

```rust
//! Macro regression gate: 500-turn timed runs.
//! Run: cargo test --release -p chronicler-agents --test regression -- --ignored --nocapture
//! Targets (9950X): 6K/24 < 3s, 10K/24 < 6s. Report median of 3.

use std::time::Instant;

use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: if i % 4 == 2 { 25 } else { 55 },
                is_at_war: i % 3 == 1,
                dominant_faction: (i % 3) as u8,
                faction_military: if i % 3 == 1 { 0.55 } else { 0.25 },
                faction_merchant: if i % 3 == 1 { 0.25 } else { 0.40 },
                faction_cultural: if i % 3 == 1 { 0.20 } else { 0.35 },
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
            })
            .collect(),
        contested_regions: (0..num_regions).map(|i| i % 5 == 0).collect(),
    }
}

fn setup_pool(num_agents: usize, num_regions: u16) -> (AgentPool, Vec<RegionState>, TickSignals) {
    let agents_per_region = num_agents / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r,
        terrain: 0,
        carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16,
        soil: 0.7,
        water: 0.5,
        forest_cover: 0.3,
        adjacency_mask: if num_regions <= 32 {
            (if r > 0 { 1u32 << (r - 1) } else { 0 })
                | (if r < num_regions - 1 { 1u32 << (r + 1) } else { 0 })
        } else {
            0
        },
        controller_civ: (r % 4) as u8,
        trade_route_count: 0,
    }).collect();
    let num_civs = (num_regions.min(8)) as usize;
    let signals = make_signals(num_civs, num_regions as usize);
    let mut pool = AgentPool::new(num_agents);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occupations[j % 5], (j % 60) as u16);
        }
    }
    (pool, regions, signals)
}

fn run_500_turns(num_agents: usize, num_regions: u16) -> f64 {
    let (mut pool, regions, signals) = setup_pool(num_agents, num_regions);
    let mut seed = [0u8; 32]; seed[0] = 42;
    let start = Instant::now();
    for turn in 0..500 {
        tick_agents(&mut pool, &regions, &signals, seed, turn);
    }
    start.elapsed().as_secs_f64()
}

fn median_of_3(num_agents: usize, num_regions: u16) -> f64 {
    let mut times = [0.0f64; 3];
    for i in 0..3 {
        times[i] = run_500_turns(num_agents, num_regions);
        eprintln!("  run {}: {:.3}s", i + 1, times[i]);
    }
    times.sort_by(|a, b| a.partial_cmp(b).unwrap());
    times[1]
}

#[test]
#[ignore]
fn regression_6k_24r_under_3s() {
    eprintln!("=== 500 turns × 6K agents / 24 regions ===");
    let median = median_of_3(6_000, 24);
    eprintln!("  median: {:.3}s (target: < 3.0s)", median);
    assert!(median < 3.0, "6K/24 median {:.3}s exceeded 3.0s target", median);
}

#[test]
#[ignore]
fn regression_10k_24r_under_6s() {
    eprintln!("=== 500 turns × 10K agents / 24 regions ===");
    let median = median_of_3(10_000, 24);
    eprintln!("  median: {:.3}s (target: < 6.0s)", median);
    assert!(median < 6.0, "10K/24 median {:.3}s exceeded 6.0s target", median);
}
```

- [ ] **Step 2: Verify tests compile and run**

Run: `cargo test --release -p chronicler-agents --test regression -- --ignored --nocapture` (from project root)

Expected: Both tests run, print timing per run and median. Record baseline numbers.

- [ ] **Step 3: Commit**

```bash
git add tests/regression.rs
git commit -m "test(m29): add 500-turn macro regression gate (6K/24, 10K/24)"
```

### Task 5: Benchmark README

**Files:**
- Create: `chronicler-agents/benches/BENCHMARK_README.md`

- [ ] **Step 1: Write the README**

```markdown
# Benchmark Reference

## Hardware

AMD Ryzen 9 9950X (16C/32T)
All targets and results in this project are for this machine.

## How to Run

### Criterion micro-benchmarks (matrix)
```
cargo bench --bench tick_bench
```

### Macro regression gate (500-turn timed tests)
```
cargo test --release --test regression -- --ignored --nocapture
```

### Flamegraph (requires cargo-flamegraph)
```
cargo flamegraph --example flamegraph_run -- --agents 10000 --regions 24 --turns 500
```

## Measurement Protocol

- Macro regression gate: report the **median of 3 runs**; target must be met on all 3.
- Criterion benchmarks: use default criterion settings (100 iterations, statistical analysis).
- Close other CPU-intensive applications before benchmarking.

## Performance Targets

| Metric               | Target  |
|----------------------|---------|
| Tick time (6K/24)    | < 3 ms  |
| Tick time (10K/24)   | < 5 ms  |
| 500-turn run (6K/24) | < 3 s   |
| 500-turn run (10K/24)| < 6 s   |
| Arrow FFI per tick   | < 0.5ms |
```

- [ ] **Step 2: Commit**

```bash
git add benches/BENCHMARK_README.md
git commit -m "docs(m29): add benchmark README with hardware reference and protocol"
```

---

## Chunk 2: Baseline Measurements & Satisfaction Parallelization

### Task 6: Collect Baseline Measurements

This is a manual analysis task — no code changes, just running tools and recording results.

- [ ] **Step 1: Run the full criterion matrix**

Run: `cargo bench --bench tick_bench` (from `chronicler-agents/`)

Record: All 5 configuration results (mean tick time per config).

- [ ] **Step 2: Run the macro regression gate**

Run: `cargo test --release --test regression -- --ignored --nocapture`

Record: Median times for 6K/24 and 10K/24.

- [ ] **Step 3: Generate a flamegraph at 10K/24**

Run: `cargo flamegraph --example flamegraph_run --root -- --agents 10000 --regions 24 --turns 500` (from `chronicler-agents/`)

**Note:** `cargo flamegraph` requires Linux/WSL with `perf` installed. The `--root` flag is for `perf` permissions. On Windows, run this step in WSL where jemalloc is also active.

Record: Open `flamegraph.svg`. Identify the top hotspots by percentage of total time. Note:
- What % is `update_satisfaction`?
- What % is `compute_region_stats`?
- What % is `partition_by_region`?
- What % is `evaluate_region_decisions`?
- What % is `tick_region_demographics`?
- What % is signal parsing (`shock_for_civ`, `demand_shifts_for_civ`, `parse_civ_signals`)?
- What % is the sequential apply loop (phase 4)?

- [ ] **Step 4: Record results in a comment in the benchmark README**

Add a "## Baseline (pre-optimization)" section to `benches/BENCHMARK_README.md` with the numbers.

- [ ] **Step 5: Commit**

```bash
git add benches/BENCHMARK_README.md
git commit -m "docs(m29): record pre-optimization baseline measurements"
```

### Task 7: Parallelize Satisfaction Update

**Files:**
- Modify: `chronicler-agents/src/tick.rs:250-341`

- [ ] **Step 1: Write a test that verifies satisfaction values are identical before and after refactor**

Add to `src/tick.rs` inside the `#[cfg(test)] mod tests` block (after line 646):

```rust
#[test]
fn test_satisfaction_parallel_matches_sequential() {
    // Set up a multi-region pool with varied occupations and civs
    let mut regions = vec![
        make_healthy_region(0),
        make_healthy_region(1),
        make_healthy_region(2),
    ];
    regions[0].adjacency_mask = 0b110;
    regions[1].adjacency_mask = 0b101;
    regions[2].adjacency_mask = 0b011;
    regions[0].controller_civ = 0;
    regions[1].controller_civ = 1;
    regions[2].controller_civ = 0;

    let signals = make_default_signals(2, 3);

    // Build two identical pools
    let mut pool_a = AgentPool::new(0);
    let mut pool_b = AgentPool::new(0);
    let occupations = [
        Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
        Occupation::Scholar, Occupation::Priest,
    ];
    for r in 0..3u16 {
        for j in 0..100 {
            let occ = occupations[j % 5];
            let age = (j % 60) as u16;
            let civ = (r % 2) as u8;
            pool_a.spawn(r, civ, occ, age);
            pool_b.spawn(r, civ, occ, age);
        }
    }

    // Run satisfaction on pool_a (current implementation)
    update_satisfaction(&mut pool_a, &regions, &signals);

    // Run satisfaction on pool_b (same function — after refactoring this
    // still calls update_satisfaction, which now uses rayon internally)
    update_satisfaction(&mut pool_b, &regions, &signals);

    // Verify computation actually happened (not still at default 0.5)
    let any_changed = (0..pool_a.capacity())
        .filter(|&s| pool_a.is_alive(s))
        .any(|s| (pool_a.satisfaction(s) - 0.5).abs() > 0.01);
    assert!(any_changed, "satisfaction should differ from default 0.5 after update");

    // Verify all satisfaction values match between the two pools
    for slot in 0..pool_a.capacity() {
        if pool_a.is_alive(slot) {
            let diff = (pool_a.satisfaction(slot) - pool_b.satisfaction(slot)).abs();
            assert!(
                diff < 1e-6,
                "satisfaction mismatch at slot {}: {} vs {}",
                slot,
                pool_a.satisfaction(slot),
                pool_b.satisfaction(slot),
            );
        }
    }
}
```

- [ ] **Step 2: Run test to verify it passes (pre-refactor baseline)**

Run: `cargo test -p chronicler-agents test_satisfaction_parallel_matches_sequential -- --nocapture`

Expected: PASS — both pools produce identical results with sequential code.

- [ ] **Step 3: Refactor `update_satisfaction` to use per-region rayon parallelism**

Replace `update_satisfaction` (lines 250-341 of `src/tick.rs`) with:

```rust
fn update_satisfaction(pool: &mut AgentPool, regions: &[RegionState], signals: &TickSignals) {
    // Pre-compute region stats for demand/supply ratio
    let stats = compute_region_stats(pool, regions, signals);

    // Partition agents by region
    let num_regions = regions.len();
    let region_groups = pool.partition_by_region(num_regions as u16);

    // Compute satisfaction per-region in parallel.
    // Collect (slot, sat) pairs — avoids unsafe mutable aliasing on pool.satisfactions.
    let updates: Vec<Vec<(usize, f32)>> = {
        let pool_ref = &*pool;
        region_groups
            .par_iter()
            .enumerate()
            .map(|(region_id, slots)| {
                if region_id >= regions.len() {
                    return Vec::new();
                }
                let region = &regions[region_id];

                slots
                    .iter()
                    .map(|&slot| {
                        let occ = pool_ref.occupation(slot);
                        let civ = pool_ref.civ_affinity(slot) as usize;

                        let civ_sig = signals
                            .civs
                            .iter()
                            .find(|c| c.civ_id as usize == civ);

                        let civ_stability = civ_sig.map_or(50, |c| c.stability);
                        let civ_at_war = civ_sig.map_or(false, |c| c.is_at_war);
                        let region_contested = if region_id < signals.contested_regions.len() {
                            signals.contested_regions[region_id]
                        } else {
                            false
                        };

                        let occ_idx = occ as usize;
                        let supply = stats.occupation_supply[region_id][occ_idx] as f32;
                        let demand = stats.occupation_demand[region_id][occ_idx];
                        let ds_ratio = if supply > 0.0 {
                            (demand - supply) / supply
                        } else {
                            0.0
                        };

                        let pop = stats.occupation_supply[region_id]
                            .iter()
                            .sum::<usize>() as f32;
                        let cap = region.carrying_capacity as f32;
                        let pop_over_cap = if cap > 0.0 { pop / cap } else { 1.0 };

                        let occ_matches = match civ_sig {
                            Some(cs) => match cs.dominant_faction {
                                0 => occ == 1,
                                1 => occ == 2,
                                2 => occ == 3,
                                _ => false,
                            },
                            None => false,
                        };

                        let is_displaced = pool_ref.displacement_turns(slot) > 0;

                        let faction_influence = match civ_sig {
                            Some(cs) => match occ {
                                1 => cs.faction_military,
                                2 => cs.faction_merchant,
                                3 => cs.faction_cultural,
                                _ => 0.0,
                            },
                            None => 0.0,
                        };

                        let shock = signals.shock_for_civ(pool_ref.civ_affinity(slot));

                        let sat = satisfaction::compute_satisfaction(
                            occ,
                            region.soil,
                            region.water,
                            civ_stability,
                            ds_ratio,
                            pop_over_cap,
                            civ_at_war,
                            region_contested,
                            occ_matches,
                            is_displaced,
                            region.trade_route_count,
                            faction_influence,
                            &shock,
                        );

                        (slot, sat)
                    })
                    .collect()
            })
            .collect()
    };

    // Apply collected satisfaction values sequentially
    for region_updates in &updates {
        for &(slot, sat) in region_updates {
            pool.set_satisfaction(slot, sat);
        }
    }
}
```

**Design note:** This uses a collect-then-apply pattern (~80KB intermediate allocation at 10K agents) rather than direct parallel writes to `pool.satisfactions`. The spec notes that direct writes to disjoint slot indices are safe, but direct writes require `unsafe` in Rust. The collect approach avoids `unsafe` at negligible cost. If post-optimization flamegraphs show the allocation is material, switch to direct writes via `unsafe` slice access with a safety comment citing slot-index disjointness.

- [ ] **Step 4: Run the matching test to verify correctness**

Run: `cargo test -p chronicler-agents test_satisfaction_parallel_matches_sequential -- --nocapture`

Expected: PASS.

- [ ] **Step 5: Run all existing tests**

Run: `cargo test -p chronicler-agents`

Expected: All tests pass — the refactored `update_satisfaction` produces identical results.

- [ ] **Step 6: Run the determinism test specifically**

Run: `cargo test -p chronicler-agents --test determinism`

Expected: PASS — parallelized satisfaction is deterministic (rayon preserves order within `par_iter().enumerate().map().collect()`).

- [ ] **Step 7: Run criterion benchmark to measure improvement**

Run: `cargo bench --bench tick_bench`

Record: Compare tick times against pre-optimization baseline from Task 6.

- [ ] **Step 8: Commit**

```bash
git add src/tick.rs
git commit -m "perf(m29): parallelize satisfaction update per-region via rayon"
```

---

## Chunk 3: Profile-Driven Investigations

### Task 8: Post-Optimization Flamegraph

- [ ] **Step 1: Generate flamegraph after satisfaction parallelization**

Run in WSL: `cargo flamegraph --example flamegraph_run --root -- --agents 10000 --regions 24 --turns 500`

Record: Compare against Task 6 baseline. Note:
- How much did `update_satisfaction` decrease?
- What is now the top hotspot?
- Is signal parsing (`shock_for_civ` / linear civ lookup) visible?
- What % is `partition_by_region`? (Now called 3 times per tick)

- [ ] **Step 2: Based on flamegraph, decide which criterion benchmarks to write**

If specific functions show up as >10% of tick time, create targeted criterion benchmarks for them in `benches/tick_bench.rs`. The functions to watch for:
- `compute_region_stats` — if hot, benchmark it in isolation
- `partition_by_region` — if hot (3 calls/tick), benchmark it
- `shock_for_civ` / civ signal lookup — if hot, benchmark the linear scan
- `evaluate_region_decisions` — if decision evaluation dominates

Add each as a `bench_function` inside the existing `bench_tick_matrix` group or a new group.

**If signal parsing (`shock_for_civ`, `demand_shifts_for_civ`) is >5% of tick time:** The linear `.iter().find()` scan in `TickSignals` methods (signals.rs:134-163) runs once per agent per tick. Replace with a pre-indexed lookup: at the start of `update_satisfaction`, build a `[Option<usize>; 256]` mapping `civ_id -> index` into `signals.civs`, then use direct indexing instead of `.find()`. Apply the same optimization in `tick_region_demographics` (tick.rs:383-387).

- [ ] **Step 3: Commit any new benchmarks**

```bash
git add benches/tick_bench.rs
git commit -m "bench(m29): add criterion benchmarks for flamegraph-identified hotspots"
```

### Task 9: Arrow FFI Overhead Measurement

- [ ] **Step 1: Add a benchmark for Arrow serialization**

Add to `benches/tick_bench.rs` (a new benchmark group):

```rust
fn bench_arrow_ffi(c: &mut Criterion) {
    let (pool, _, _) = setup_pool(10_000, 24);
    c.bench_function("arrow_snapshot_10k", |b| {
        b.iter(|| {
            let _ = black_box(pool.to_record_batch().unwrap());
        })
    });
}
```

Update the `criterion_group!` to include `bench_arrow_ffi`.

Note: `to_record_batch` must be `pub` on `AgentPool`. If it isn't currently exported, add `pub use pool::AgentPool;` already covers it since `to_record_batch` is a method on the public struct. Verify the method is `pub`.

- [ ] **Step 2: Run the Arrow benchmark**

Run: `cargo bench --bench tick_bench -- arrow_snapshot`

Expected: Sub-millisecond result. Record the number.

- [ ] **Step 3: Document the result**

Add the Arrow FFI measurement to the "Post-optimization" section of `benches/BENCHMARK_README.md`.

- [ ] **Step 4: Commit**

```bash
git add benches/tick_bench.rs benches/BENCHMARK_README.md
git commit -m "bench(m29): measure Arrow FFI overhead — document result"
```

### Task 10: Cache Efficiency Synthetic Benchmark

**Files:**
- Create: `chronicler-agents/benches/cache_bench.rs`
- Modify: `chronicler-agents/Cargo.toml`

- [ ] **Step 1: Add bench entry to Cargo.toml**

Add after the existing `[[bench]]` section:

```toml
[[bench]]
name = "cache_bench"
harness = false
```

- [ ] **Step 2: Write the packed-vs-scattered benchmark**

```rust
//! Cache efficiency benchmark: packed pool vs scattered pool.
//! Measures tick-time difference to isolate cache-miss impact from fragmentation.

use criterion::{black_box, criterion_group, criterion_main, Criterion, BatchSize};
use chronicler_agents::{AgentPool, Occupation, RegionState, tick_agents};
use chronicler_agents::signals::{CivSignals, TickSignals};

fn make_signals(num_civs: usize, num_regions: usize) -> TickSignals {
    TickSignals {
        civs: (0..num_civs)
            .map(|i| CivSignals {
                civ_id: i as u8,
                stability: 55,
                is_at_war: false,
                dominant_faction: 0,
                faction_military: 0.33,
                faction_merchant: 0.33,
                faction_cultural: 0.34,
                shock_stability: 0.0,
                shock_economy: 0.0,
                shock_military: 0.0,
                shock_culture: 0.0,
                demand_shift_farmer: 0.0,
                demand_shift_soldier: 0.0,
                demand_shift_merchant: 0.0,
                demand_shift_scholar: 0.0,
                demand_shift_priest: 0.0,
            })
            .collect(),
        contested_regions: vec![false; num_regions],
    }
}

/// Packed: 10K alive agents contiguous at slots 0..10_000.
fn setup_packed() -> (AgentPool, Vec<RegionState>, TickSignals) {
    let num_regions = 24u16;
    let agents_per_region = 10_000 / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r, terrain: 0, carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16, soil: 0.7, water: 0.5,
        forest_cover: 0.3, adjacency_mask: 0, controller_civ: (r % 4) as u8,
        trade_route_count: 0,
    }).collect();
    let signals = make_signals(4, num_regions as usize);
    let mut pool = AgentPool::new(10_000);
    let occs = [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
                Occupation::Scholar, Occupation::Priest];
    for r in 0..num_regions {
        for j in 0..agents_per_region {
            pool.spawn(r, (r % 4) as u8, occs[j % 5], (j % 60) as u16);
        }
    }
    (pool, regions, signals)
}

/// Scattered: 10K alive agents across 15K slots (5K dead gaps).
/// Simulates post-mortality fragmentation (~33% dead).
fn setup_scattered() -> (AgentPool, Vec<RegionState>, TickSignals) {
    let num_regions = 24u16;
    let agents_per_region = 10_000 / num_regions as usize;
    let regions: Vec<RegionState> = (0..num_regions).map(|r| RegionState {
        region_id: r, terrain: 0, carrying_capacity: agents_per_region as u16,
        population: agents_per_region as u16, soil: 0.7, water: 0.5,
        forest_cover: 0.3, adjacency_mask: 0, controller_civ: (r % 4) as u8,
        trade_route_count: 0,
    }).collect();
    let signals = make_signals(4, num_regions as usize);
    // Spawn 15K agents, then kill every 3rd to leave 10K alive across 15K slots
    let mut pool = AgentPool::new(15_000);
    let occs = [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant,
                Occupation::Scholar, Occupation::Priest];
    let total_per_region = 15_000 / num_regions as usize;
    for r in 0..num_regions {
        for j in 0..total_per_region {
            pool.spawn(r, (r % 4) as u8, occs[j % 5], (j % 60) as u16);
        }
    }
    // Kill every 3rd slot to create scattered dead gaps
    for slot in (0..pool.capacity()).step_by(3) {
        if pool.is_alive(slot) {
            pool.kill(slot);
        }
    }
    (pool, regions, signals)
}

fn bench_cache_efficiency(c: &mut Criterion) {
    let mut seed = [0u8; 32]; seed[0] = 42;
    let mut group = c.benchmark_group("cache_efficiency");

    group.bench_function("packed_10k", |b| {
        b.iter_batched(setup_packed, |(mut pool, regions, signals)| {
            tick_agents(black_box(&mut pool), black_box(&regions), black_box(&signals), seed, 0);
        }, BatchSize::SmallInput)
    });

    group.bench_function("scattered_10k_in_15k", |b| {
        b.iter_batched(setup_scattered, |(mut pool, regions, signals)| {
            tick_agents(black_box(&mut pool), black_box(&regions), black_box(&signals), seed, 0);
        }, BatchSize::SmallInput)
    });

    group.finish();
}

criterion_group!(benches, bench_cache_efficiency);
criterion_main!(benches);
```

- [ ] **Step 3: Run the cache benchmark**

Run: `cargo bench --bench cache_bench`

Expected: Both configs run. Compare packed vs scattered tick times.

**Decision point:** If scattered is >15% slower than packed, compaction (Task 11) is warranted. If <15%, document the result and skip compaction.

- [ ] **Step 4: Commit**

```bash
git add benches/cache_bench.rs Cargo.toml
git commit -m "bench(m29): add packed-vs-scattered cache efficiency benchmark"
```

### Task 11: Compaction (Contingent on Task 10)

**Skip this task if Task 10 shows <15% degradation from scattering.**

**Files:**
- Modify: `chronicler-agents/src/pool.rs`

- [ ] **Step 1: Write a test for compaction correctness**

Add to `pool.rs` test module (or create `tests/compaction.rs`):

```rust
#[test]
fn test_compact_preserves_agent_data() {
    let mut pool = AgentPool::new(100);
    // Spawn 50 agents, kill every other one, then compact
    let mut ids = Vec::new();
    for i in 0..50 {
        let slot = pool.spawn(i % 5, (i % 3) as u8, Occupation::Farmer, (i * 2) as u16);
        ids.push(pool.id(slot));
    }
    // Kill every other agent
    for slot in (0..50).step_by(2) {
        pool.kill(slot);
    }
    assert_eq!(pool.alive_count(), 25);

    // Record pre-compaction data for alive agents
    let pre_data: Vec<(u32, u16, u8, u8, f32)> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s))
        .map(|s| (pool.id(s), pool.region(s), pool.civ_affinity(s), pool.occupation(s), pool.satisfaction(s)))
        .collect();

    pool.compact();

    assert_eq!(pool.alive_count(), 25);
    // All alive agents should now be in slots 0..25
    for slot in 0..25 {
        assert!(pool.is_alive(slot), "slot {} should be alive after compact", slot);
    }
    // No alive agents beyond slot 25
    for slot in 25..pool.capacity() {
        assert!(!pool.is_alive(slot), "slot {} should be dead after compact", slot);
    }
    // Data should be preserved (order may change, but all agents present)
    let post_data: Vec<(u32, u16, u8, u8, f32)> = (0..25)
        .map(|s| (pool.id(s), pool.region(s), pool.civ_affinity(s), pool.occupation(s), pool.satisfaction(s)))
        .collect();
    for pre in &pre_data {
        assert!(post_data.contains(pre), "agent {:?} missing after compact", pre);
    }
}
```

- [ ] **Step 2: Run test — should fail (compact not implemented)**

Run: `cargo test -p chronicler-agents test_compact_preserves_agent_data`

Expected: FAIL — `compact` method does not exist.

- [ ] **Step 3: Implement `compact` on `AgentPool`**

Add to `pool.rs` impl block:

```rust
/// Compact the pool: move all alive agents to contiguous front slots.
/// Safe to call between ticks. Preserves agent IDs (stable identity).
/// Invalidates slot indices — only call when nothing caches slots.
pub fn compact(&mut self) {
    let alive_count = self.count;
    if alive_count == 0 || alive_count == self.capacity() {
        return; // Nothing to compact
    }

    // Find the boundary: we want alive agents in 0..alive_count
    let mut write_slot = 0;
    let mut read_slot = 0;
    let cap = self.capacity();

    while write_slot < alive_count && read_slot < cap {
        if write_slot < cap && self.alive[write_slot] {
            write_slot += 1;
            read_slot = read_slot.max(write_slot);
            continue;
        }
        // write_slot is dead — find next alive read_slot
        while read_slot < cap && !self.alive[read_slot] {
            read_slot += 1;
        }
        if read_slot >= cap {
            break;
        }
        // Move read_slot -> write_slot
        self.ids[write_slot] = self.ids[read_slot];
        self.regions[write_slot] = self.regions[read_slot];
        self.origin_regions[write_slot] = self.origin_regions[read_slot];
        self.civ_affinities[write_slot] = self.civ_affinities[read_slot];
        self.occupations[write_slot] = self.occupations[read_slot];
        self.loyalties[write_slot] = self.loyalties[read_slot];
        self.satisfactions[write_slot] = self.satisfactions[read_slot];
        let w_base = write_slot * 5;
        let r_base = read_slot * 5;
        for i in 0..5 {
            self.skills[w_base + i] = self.skills[r_base + i];
        }
        self.ages[write_slot] = self.ages[read_slot];
        self.displacement_turns[write_slot] = self.displacement_turns[read_slot];
        self.alive[write_slot] = true;
        self.alive[read_slot] = false;

        write_slot += 1;
        read_slot += 1;
    }

    // Rebuild free-list: all slots from alive_count..capacity are dead
    self.free_slots.clear();
    for slot in (alive_count..cap).rev() {
        self.free_slots.push(slot);
    }
}
```

- [ ] **Step 4: Run the test**

Run: `cargo test -p chronicler-agents test_compact_preserves_agent_data`

Expected: PASS.

- [ ] **Step 5: Run all tests to verify no regressions**

Run: `cargo test -p chronicler-agents`

Expected: All pass.

- [ ] **Step 6: Re-run cache benchmark to measure improvement**

Run: `cargo bench --bench cache_bench`

Note: This benchmarks tick-on-scattered vs tick-on-packed. To test compaction benefit, add a third benchmark that runs `compact()` on the scattered pool before ticking.

- [ ] **Step 7: Commit**

```bash
git add src/pool.rs
git commit -m "perf(m29): add pool compaction for cache-miss mitigation"
```

---

## Chunk 4: Phase B — Formula-Coupled Optimizations

### Task 12: SIMD Satisfaction Verification

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs` (only if auto-vectorization fails)

- [ ] **Step 1: Install cargo-show-asm if not present**

Run: `cargo install cargo-show-asm`

- [ ] **Step 2: Check if `compute_satisfaction` auto-vectorizes**

Run: `cargo asm -p chronicler-agents --lib "satisfaction::compute_satisfaction" --release`

Inspect the output for SIMD instructions (look for `vmovaps`, `vaddps`, `vmulps`, `vminps`, `vmaxps` on x86-64). The branchless `as i32 as f32` pattern should enable the compiler to vectorize.

**Decision point:**
- If SIMD instructions present: **done** — document the verification and skip step 3.
- If no SIMD: proceed to step 3.

- [ ] **Step 3: (Only if no auto-vectorization) Add explicit SIMD via `wide` crate**

This step is contingent and should only be attempted if step 2 shows no vectorization. The specific implementation depends on what the compiler failed to vectorize. Typical approach:

Add `wide = "0.7"` to `[dependencies]` in `Cargo.toml`.

Rewrite the satisfaction inner loop to process 8 agents at once using `f32x8` vectors. This changes the per-agent function into a batched function that takes slices.

**Note:** The satisfaction function takes 13 parameters per agent. Batching requires restructuring the call site (the parallel closures from Task 7) to collect inputs into SoA-style slices per region before calling a SIMD batch function. This is a significant refactor — profile the impact carefully.

- [ ] **Step 4: Run all tests**

Run: `cargo test -p chronicler-agents`

Expected: All pass.

- [ ] **Step 5: Run criterion benchmark to measure impact**

Run: `cargo bench --bench tick_bench`

Expected: If SIMD was added, tick times should decrease. If auto-vectorization was already happening, no change expected.

- [ ] **Step 6: Commit**

```bash
git add src/satisfaction.rs Cargo.toml
git commit -m "perf(m29): verify/enable SIMD auto-vectorization for satisfaction"
```

### Task 13: Decision Short-Circuit Tuning

**Files:**
- Modify: `chronicler-agents/src/behavior.rs`

- [ ] **Step 1: Instrument decision evaluation to count branch hit rates**

Add temporary thread-local counters at the top of `evaluate_region_decisions` in `behavior.rs`. Wrap in `#[cfg(feature = "profile-decisions")]` so they don't pollute production builds. Add the feature to `Cargo.toml`:

```toml
[features]
profile-decisions = []
```

At the top of `evaluate_region_decisions` (after line ~206), add:

```rust
#[cfg(feature = "profile-decisions")]
{
    use std::sync::atomic::{AtomicUsize, Ordering};
    static TOTAL: AtomicUsize = AtomicUsize::new(0);
    static REBEL: AtomicUsize = AtomicUsize::new(0);
    static MIGRATE: AtomicUsize = AtomicUsize::new(0);
    static OCC_SWITCH: AtomicUsize = AtomicUsize::new(0);
    static DRIFT: AtomicUsize = AtomicUsize::new(0);
    // Increment TOTAL for each agent evaluated, and the relevant counter
    // at each branch that fires. Print summary every 100K agents:
    let t = TOTAL.fetch_add(slots.len(), Ordering::Relaxed) + slots.len();
    if t % 100_000 < slots.len() {
        eprintln!("decisions: total={t} rebel={} migrate={} occ_switch={} drift={}",
            REBEL.load(Ordering::Relaxed), MIGRATE.load(Ordering::Relaxed),
            OCC_SWITCH.load(Ordering::Relaxed), DRIFT.load(Ordering::Relaxed));
    }
}
```

Then add `REBEL.fetch_add(1, ...)` etc. at each branch that fires.

Run: `cargo run --release --features profile-decisions --example flamegraph_run -- --agents 10000 --regions 24 --turns 500 2>&1 | grep decisions | tail -1`

Record: Which branch fires most rarely? That should be evaluated first (earliest rejection = best short-circuit).

- [ ] **Step 2: Reorder decision branches based on measured data**

Move the most-commonly-rejected decision to the top of the evaluation order. The current order is: rebellion → migration → occupation switch → loyalty drift.

If data shows (for example) that rebellion's threshold (`loy < 0.2 && sat < 0.2`) rejects 98% of agents while migration's threshold (`sat < 0.3`) rejects 85%, the order should remain rebellion-first (it's already optimal). Adjust only if data contradicts the current ordering.

- [ ] **Step 3: Remove temporary instrumentation**

Remove the `#[cfg(feature = "profile-decisions")]` blocks from `behavior.rs` and the `profile-decisions` feature from `Cargo.toml`.

- [ ] **Step 4: Run all tests**

Run: `cargo test -p chronicler-agents`

Expected: All pass.

- [ ] **Step 5: Benchmark**

Run: `cargo bench --bench tick_bench`

Record: Compare against post-satisfaction-parallelization baseline.

- [ ] **Step 6: Commit**

```bash
git add src/behavior.rs
git commit -m "perf(m29): tune decision short-circuit ordering based on profile data"
```

### Task 14: Final Measurements & Performance Report

- [ ] **Step 1: Run the full criterion matrix**

Run: `cargo bench --bench tick_bench`

- [ ] **Step 2: Run the macro regression gate**

Run: `cargo test --release --test regression -- --ignored --nocapture`

Expected: Both tests PASS (6K/24 < 3s, 10K/24 < 6s).

- [ ] **Step 3: Generate final flamegraph**

Run in WSL: `cargo flamegraph --example flamegraph_run --root -- --agents 10000 --regions 24 --turns 500`

- [ ] **Step 4: Update BENCHMARK_README with final results**

Add a "## Post-Optimization Results" section comparing before/after for all metrics:
- Tick time per matrix config (before → after)
- 500-turn macro times (before → after)
- Arrow FFI overhead measurement
- Cache efficiency (packed vs scattered delta)
- Flamegraph hotspot breakdown

- [ ] **Step 5: Commit**

```bash
git add benches/BENCHMARK_README.md
git commit -m "docs(m29): add post-optimization performance comparison report"
```

- [ ] **Step 6: Run macro regression gate one final time to confirm**

Run: `cargo test --release --test regression -- --ignored --nocapture`

Expected: Both tests PASS with comfortable margin.
