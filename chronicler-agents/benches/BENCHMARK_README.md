# Benchmark Reference

## Hardware

AMD Ryzen 9 9950X (16C/32T)
All targets and results in this project are for this machine.

## How to Run

### Criterion micro-benchmarks (matrix)

    cargo bench --bench tick_bench

### Macro regression gate (500-turn timed tests)

    cargo test --release --test regression -- --ignored --nocapture

### Flamegraph (requires cargo-flamegraph, run in WSL)

    cargo flamegraph --example flamegraph_run --root -- --agents 10000 --regions 24 --turns 500

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

## Results (M29 Phase A)

Measured on reference hardware (9950X), Windows, `--release` profile.

### Macro Regression Gate (500 turns, median of 3)

| Config   | Median   | Target  | Headroom |
|----------|----------|---------|----------|
| 6K / 24  | 0.109 s  | < 3.0 s | ~27x     |
| 10K / 24 | 0.126 s  | < 6.0 s | ~47x     |

### Arrow FFI Overhead

| Config             | Mean    | Target   |
|--------------------|---------|----------|
| `to_record_batch` 10K | 131 µs  | < 500 µs |

### Cache Efficiency (packed vs scattered)

| Config                        | Mean     | Delta  |
|-------------------------------|----------|--------|
| Packed 10K (contiguous)       | 870 µs   | —      |
| Scattered 10K in 15K (~33% dead) | 885 µs | +1.6%  |

Compaction not warranted — fragmentation penalty is negligible.

### Phase B Status

**Deferred.** All performance targets met with 27-47x headroom. SIMD satisfaction verification, decision short-circuit tuning, and compaction have no profiling justification at current scale. Flamegraphs can be run post-merge for documentation if desired.
