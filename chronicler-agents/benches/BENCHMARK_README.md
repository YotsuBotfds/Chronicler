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
