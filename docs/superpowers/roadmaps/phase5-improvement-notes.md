# Phase 5 Roadmap — Improvement Notes

> Research-backed suggestions for the agent-based population model roadmap.
> These are observations and options, not prescriptions — some may not be worth the tradeoff.

---

## 1. RNG Strategy: ChaCha8Rng with Stream Splitting

**Current approach:** Per-agent RNG seeded from `world_seed ⊕ agent_id ⊕ turn`.

**Concern:** XOR-based seed derivation from a single master seed can produce correlated sequences with simple PRNGs. If two agents have IDs that differ by one bit, their seed-derived sequences may overlap or correlate, especially over hundreds of turns.

**Recommended alternative:** Use `ChaCha8Rng` with its native stream-splitting API. ChaCha's 256-bit seed + 64-bit stream counter is designed exactly for this — cryptographically independent streams without correlation artifacts.

```rust
use rand_chacha::ChaCha8Rng;
use rand::SeedableRng;

// Per-region RNG with guaranteed independence
let mut region_rng = ChaCha8Rng::from_seed(master_seed);
region_rng.set_stream(region_id as u64);

// Per-agent within region: advance counter or use nested stream
```

This also simplifies the determinism guarantee. Instead of proving that XOR-derived seeds don't collide, you get mathematical independence by construction. The `set_stream()` approach is what the Rust Rand Book explicitly recommends for parallel simulation.

**Cost:** Minimal. ChaCha8Rng is fast (faster than ChaCha20), and the API change is localized to the RNG initialization in `tick_agents`.

---

## 2. Agent Decision Model: Consider Utility-Based Selection

**Current approach:** Priority-ordered short-circuit (rebel → migrate → switch occupation → loyalty drift). First triggered action executes, rest skipped.

**Observation:** This creates rigid coupling between decision priority and behavior. A farmer with satisfaction 0.29 (just under migration threshold) who also has loyalty 0.19 (just under rebellion threshold) will always rebel and never migrate, even if migration would serve them better. The priority ordering becomes a hidden tuning parameter that's hard to reason about.

**Alternative: Weighted utility selection.** Each action computes a utility score; the agent picks the highest (with some noise for stochasticity):

```
utility_rebel    = max(0, rebellion_threshold - loyalty) × rebel_weight × group_factor
utility_migrate  = max(0, migration_threshold - satisfaction) × adjacent_region_pull
utility_switch   = max(0, demand_gap) × switch_weight
utility_stay     = base_inertia + satisfaction × stay_weight
```

Agent picks `argmax(utility + noise)`. This is cheaper to compute than BDI (no belief state maintenance), but more expressive than thresholds. It also makes tuning more transparent — each weight maps to a behavioral tendency.

**Full BDI is probably overkill** for this simulation. BDI shines when agents need complex multi-step plans. These agents make one decision per tick from a small action space. Utility scoring gives you the composability benefits without the architectural overhead.

**Cost:** Moderate. Requires reworking `behavior.rs` decision logic, but the number of lines is similar. Tuning shifts from "get the threshold ordering right" to "get the utility weights right" — arguably easier because weights are continuous and independently adjustable.

---

## 3. Validation: Beyond KS Tests

**Current approach:** KS two-sample tests at 3 checkpoints, pass if p > 0.05.

**Concerns:**

- **KS is weak on tails.** If the agent model produces realistic means but pathological extremes (e.g., occasional civilizations with 0 population that the aggregate model never produces), KS may not catch it. The **Anderson-Darling test** is more sensitive to tail behavior and is a drop-in replacement.

- **KS is univariate.** Testing each metric independently misses correlated failures. A simulation where military is high whenever economy is low (agent model) vs. independent (aggregate model) would pass 10/10 univariate KS tests but produce fundamentally different dynamics. Consider **Wasserstein distance** (earth mover's distance) for comparing multivariate distributions, or at minimum test key metric *ratios* (military/economy, culture/stability).

- **15 comparisons → multiple testing problem.** With 15 independent KS tests at α = 0.05, the probability of at least one false positive is `1 - 0.95^15 ≈ 54%`. Apply Bonferroni correction (α = 0.05/15 ≈ 0.003) or use Benjamini-Hochberg FDR control.

**Suggested additions for M26/M28:**

```python
from scipy.stats import anderson_ksamp, wasserstein_distance

# Tail-sensitive test
ad_stat, critical_values, p_value = anderson_ksamp([agent_vals, agg_vals])

# Distribution distance (interpretable magnitude, not just pass/fail)
wd = wasserstein_distance(agent_vals, agg_vals)

# Correlation structure validation
agent_corr = np.corrcoef(agent_military, agent_economy)[0, 1]
agg_corr = np.corrcoef(agg_military, agg_economy)[0, 1]
corr_delta = abs(agent_corr - agg_corr)  # should be < 0.15
```

**Metamodel validation** (building a surrogate model of the ABM and comparing response surfaces) is the state of the art in ABM validation literature, but it's a significant investment. Probably better suited for a post-M28 quality pass than baking into the initial oracle gate.

**Cost:** Low for Anderson-Darling + correlation checks (a few lines in `shadow_oracle.py`). Medium for Wasserstein on multivariate data.

---

## 4. Arrow FFI: Use pyo3-arrow Instead of Raw arrow-rs

**Current approach:** Manual `RecordBatch::to_pyarrow(py)` / `RecordBatch::from_pyarrow(py, &batch)` via arrow-rs + PyO3.

**Recommendation:** The `pyo3-arrow` crate (and its companion `arro3-core`) provides a cleaner abstraction over the Arrow PyCapsule Interface. Key benefits:

- **Zero-copy by default** via the PyCapsule protocol (avoids the IPC serialization path that raw arrow-rs sometimes falls into)
- **Schema negotiation** built in — catches type mismatches at the boundary instead of inside Rust code
- **Lighter Python dependency** — `arro3-core` is ~7MB vs PyArrow's ~100MB. You can still accept PyArrow RecordBatches from the Python side (PyCapsule is interoperable), but the Rust side doesn't need the full PyArrow build

**Gotcha:** Use owned types (`PyArray`, not `&PyArray`) in PyO3 function signatures. References don't trigger pyo3-arrow's zero-copy extraction.

This doesn't change the architecture — it's a library swap in `ffi.rs` and `Cargo.toml`. But it avoids a class of subtle bugs around IPC vs. zero-copy paths.

**Cost:** Low. Library swap, ~30 lines changed in FFI layer.

---

## 5. Performance: jemalloc + Compiler Settings

**Current approach:** Arena allocation with free-list (good), SoA layout (good), rayon (good). No mention of allocator choice or release profile tuning.

**Recommendations:**

```toml
# Cargo.toml
[dependencies]
tikv-jemallocator = "0.6"

# lib.rs
use tikv_jemallocator::Jemalloc;
#[global_allocator]
static GLOBAL: Jemalloc = Jemalloc;
```

```toml
# Cargo.toml
[profile.release]
codegen-units = 1   # better optimization, slower compile
lto = true          # link-time optimization across crates
opt-level = 3
```

jemalloc consistently outperforms the system allocator for long-running simulations with arena-style allocation patterns. The `codegen-units = 1` + LTO combination enables cross-function optimization that matters for tight inner loops like the satisfaction formula.

Benchmarks from similar workloads show 20-40% improvement from allocator + LTO alone, before any algorithmic changes.

**Cost:** Trivial. A few lines in `Cargo.toml` and `lib.rs`. Compile time increases ~30% in release mode.

---

## 6. M29 SIMD: Be Specific About Targets

**Current approach:** "auto-vectorization with `#[target_feature(enable = "avx2")]` where profitable."

**Observation:** Auto-vectorization is unreliable for complex control flow. The satisfaction formula has branches (`max`, clamping, conditional penalties) that often prevent auto-vectorization. Two concrete alternatives:

**Option A: Branchless satisfaction.** Rewrite the satisfaction formula to avoid conditionals. Replace `max(0, x)` with `x * (x > 0) as f32` and compute all bonuses/penalties unconditionally, zeroing irrelevant ones with masks. This lets LLVM auto-vectorize reliably.

**Option B: Explicit SIMD with `std::simd` (nightly) or `wide` crate.** Process 8 agents simultaneously (AVX2 = 8 × f32). This guarantees vectorization but ties you to a specific SIMD width.

**Recommendation:** Start with Option A (branchless formulas) in M26 when writing `satisfaction.rs`. It's free performance that doesn't require nightly Rust or explicit intrinsics. Add explicit SIMD in M29 only if profiling shows satisfaction is still the bottleneck after branchless rewrites.

**Cost:** Low for branchless. Medium for explicit SIMD.

---

## 7. Missing Concern: Agent Pool Compaction Strategy

**Current approach:** `compact_dead_slots()` runs every tick, returning dead agent indices to `free_slots`.

**Potential issue:** Over many turns, the alive agents become increasingly scattered across the pool as deaths and births interleave. The SoA arrays still have the same length (high-water mark), but alive agents are non-contiguous. This defeats cache prefetching — iterating "all alive agents in region 5" touches random cache lines.

**Options:**

- **Periodic full compaction** (every 50 turns): move all alive agents to front of arrays, rebuild indices. Cost: O(n) copy, amortized to O(n/50) per tick.
- **Generational arenas:** separate pools for young (high mortality) and established (low mortality) agents. Young pool compacts frequently; established pool rarely.
- **Bitmap filtering:** maintain a `BitVec` of alive flags. Use `count_ones()` / `select()` for fast alive-agent iteration without compaction.

The right choice depends on the death rate. If < 5% of agents die per tick, scattered dead slots are negligible. If famine/war produces 20%+ mortality spikes, compaction matters.

**Recommendation:** Add a compaction benchmark to M29's profiling checklist. Don't pre-optimize — measure first.

---

## 8. Shadow Mode Data Volume

**Current approach:** Shadow log captures per-turn, per-civ stats for the full 500-turn run across 50 seeds.

**Back-of-envelope:** 50 seeds × 500 turns × ~10 civs × ~30 fields × 8 bytes ≈ 60MB of shadow log data. That's fine for analysis but could slow down the shadow run itself if it's serializing to JSON each turn.

**Suggestion:** Use Arrow IPC for the shadow log too (you already have the Arrow infrastructure). Write shadow snapshots as Arrow IPC files — they compress well (~4:1 for numeric data) and load directly into pandas/polars for analysis without JSON parsing overhead.

```python
# Instead of shadow_log.append(dict(...))
writer.write_batch(pa.record_batch({...}))  # Arrow IPC, ~15MB compressed
```

**Cost:** Low. You're already using Arrow everywhere else.

---

## 9. Named Character Cap (M30)

**Current approach:** Max 50 named characters per run.

**Observation:** 50 is probably fine for narrative purposes, but the promotion criteria might produce uneven coverage. A long peaceful run could generate 50 high-skill characters from the same dominant civ, leaving no narrative representation for smaller civs.

**Suggestion:** Add a per-civ cap (e.g., max 10 per civ) or a diversity weighting that slightly favors promoting characters from underrepresented civs. This ensures the chronicle mentions characters from different perspectives without requiring a hard quota.

**Cost:** Trivial. A few lines in the promotion logic.

---

## 10. Missing: Graceful Degradation / Feature Flags

The roadmap has `--agents` as a single toggle. Consider breaking this into finer-grained flags for development and debugging:

- `--agents=shadow` (M26 shadow mode)
- `--agents=hybrid` (M27 full integration)
- `--agents=demographics-only` (M25 — agents age/die but don't decide)
- `--agent-narrative` (M30 named characters, independent of agent tick)

This helps isolate regressions. If a bug appears in hybrid mode, you can quickly check whether it reproduces in shadow mode (agent behavior bug) or only in hybrid mode (integration bug).

**Cost:** Low. It's a CLI flag and a few conditionals in `simulation.py`.

---

## Summary: Priority Ranking

| # | Improvement | Impact | Effort | When |
|---|-------------|--------|--------|------|
| 5 | jemalloc + release profile | High | Trivial | M25 |
| 1 | ChaCha8Rng stream splitting | Medium-High | Low | M25 |
| 4 | pyo3-arrow for FFI | Medium | Low | M25 |
| 3 | Validation beyond KS | Medium-High | Low-Med | M26 |
| 6 | Branchless satisfaction | Medium | Low | M26 |
| 10 | Feature flags | Medium | Low | M25-M27 |
| 2 | Utility-based decisions | Medium-High | Medium | M26 |
| 8 | Arrow IPC shadow log | Low-Med | Low | M26 |
| 9 | Named character diversity | Low | Trivial | M30 |
| 7 | Pool compaction analysis | Variable | Low | M29 |
