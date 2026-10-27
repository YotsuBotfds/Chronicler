# Turn speed, October 2026 (second pass: the native tick)

Branch `perf/rust-turn-2`, from `main` `8142c48` (PR #51), merged without
rebase with `7bb2bd4` (PR #52, production ledger). Performance only: every
output byte is unchanged. The 9-case identity matrix of
`scripts/turn_speed_identity.py`, a 3-seed hybrid batch and a procedural
32-region world are byte-identical to `main` `7bb2bd4`'s (proof below), as
they were to `8142c48`'s before the merge. No RNG draw, candidate set or
floating-point evaluation order changed. Follows
[turn-speed-2026-10.md](turn-speed-2026-10.md) (PR #44), whose method,
workloads and identity checks it reuses.

## Summary

Process CPU per turn, median of five interleaved runs per side (min-max in
brackets), `main` `8142c48` against the branch before the merge,
uninstrumented; agents is the median alive over the measured turns.

| World | Agents | Base turn CPU | Head turn CPU | Speed-up | Turn wall, speed-up | Whole process CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 12 regions scaled, 18,800 start | 23,604 | 146.6 ms (138.7-153.0) | 106.7 ms (102.6-107.3) | **1.37x** | 147.5 -> 107.2 ms, 1.38x | 6.2 -> 4.5 s (1.36x) |
| 12 regions scaled, 43,700 start | 53,696 | 498.9 ms (484.8-519.5) | 298.1 ms (292.7-320.8) | **1.67x** | 501.5 -> 301.5 ms, 1.66x | 22.8 -> 14.6 s (1.56x) |
| 12 regions scaled, 92,000 start | 104,840 | 1,614.6 ms (1,564.5-1,662.0) | 822.1 ms (814.4-842.2) | **1.96x** | 1,634.6 -> 833.4 ms, 1.96x | 64.0 -> 38.5 s (1.66x) |
| procedural 48 x 10, 300 turns | 651 | 64.5 ms (63.3-65.2) | 64.6 ms (63.1-65.5) | 1.00x | 65.0 -> 65.0 ms | 24.9 -> 25.0 s |
| default (gate) world, 500 turns | 157 | 19.4 ms (19.3-19.8) | 19.3 ms (18.6-19.8) | 1.00x | 19.5 -> 19.5 ms | 12.6 -> 12.6 s |

"Whole process" is the child's user + sys CPU from start to exit (imports,
world generation, warm-up turns, saves, bundle). It gains less than the
measured turns in the scaled worlds because their first turns, when every
adult is unmarried, are dominated by the marriage scan (change 4 cuts
those by about 30%, not more). The small worlds are flat Python (governance,
checkpoints, politics marshalling, sidecars) and do not move; no clear
win was found there.

The external review's estimate was about 1.34x at 52k from halving drift
alone. Drift fell 2.2x and marriage and knowledge by a third each.

**After merging `main` `7bb2bd4`** (PR #52 changes the ecology and economy
paths, none of the code changed here): three more interleaved rounds per
side against a `7bb2bd4` build (load 2.5-8.2), turn CPU median (min-max):

| World | Base `7bb2bd4` | Head (merged) | Speed-up | Whole process CPU |
| --- | ---: | ---: | ---: | ---: |
| 22k | 139.8 ms (139.3-142.5) | 111.2 ms (104.8-111.3) | 1.26x | 6.1 -> 4.5 s (1.38x) |
| 52k | 501.6 ms (501.5-509.0) | 299.0 ms (298.7-302.4) | 1.68x | 22.9 -> 14.3 s (1.60x) |
| 100k | 1,602.6 ms (1,592.4-1,656.9) | 825.4 ms (823.8-838.0) | 1.94x | 63.6 -> 37.7 s (1.69x) |
| gate world, 500 turns | 19.5 ms (19.3-19.7) | 19.5 ms (19.4-19.6) | 1.00x | 12.6 -> 12.8 s |

At 22k the turn ratio is lower in this set (base 139.8 against 146.6 ms
in the first, on a host loaded up to 8); the whole-process ratio matches
the first set.

## Method

* **Machine.** 4 vCPU Intel Xeon @ 2.30 GHz (AVX-512F/BW/DQ/VL and FP16:
  a Sapphire Rapids class core), 15 GB RAM, Ubuntu 24.04, kernel 6.18,
  Python 3.13.17, rustc 1.97.0, maturin 1.15.0. Release extensions built
  with `maturin develop --release --locked` into separate virtualenvs
  (`venv-base` from an export of `main`, `venv-head` from the branch)
  with separate `CARGO_TARGET_DIR`s. First set: base `8142c48`
  (`83b76b41...5b87`, the bytes PR #51 recorded) against head
  `c4da6ddf...31f6`; second set: base `7bb2bd4` (`c8ef41f5...b6ff`, the
  bytes PR #52 recorded) against the merge (`ee58c01e...d8d4`). Every
  build was checked to resolve `chronicler_agents.chronicler_agents` to a
  compiled extension with real `AgentSimulator`, `EcologySimulator` and
  `PoliticsSimulator` classes.
* **Shared host.** Another agent ran validation gates throughout: the
  1-minute load average was 1.6-5.3 over the first set and 2.5-8.2 over
  the second. Base and head were interleaved (each round runs every world
  on both sides, the side that goes first alternating by round and
  world), five rounds in the first set and three in the second, and CPU
  times are reported first.
* **Settings.** `RAYON_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`,
  `OMP_NUM_THREADS=1`, `PYTHONHASHSEED=0` for every timed run.
* **Worlds.** PR #44's: the 12-region template world scaled to 18,800
  and 43,700 starting agents (20 warm-up and 8 measured turns), the
  procedural 48 x 10 world (300 turns) and the CLI default gate world
  (500 turns), both with validation sidecars; plus a 92,000-start world
  (104,840 alive; 8 warm-up and 6 measured turns) for change 1, above
  the 100,000-agent threshold of the discarded sort.
* **Tools.** `scripts/turn_phase_profile.py --no-instrument` per run (turn
  CPU and wall from its turn marks; whole-process CPU from `wait4`).
  `perf` 6.8 with the software `cpu-clock` event (the VM exposes no PMU,
  so no hardware counters), sliced to the measured turns. Native tick
  phases from temporary per-phase timers in a scratch copy of the crate
  (not committed). Drift alone from a scratch micro-benchmark that loads
  the drift step's exact inputs (positions, regions, occupations, trips,
  attractors) dumped from the real 52k and 22k worlds, and reports the
  FNV digest of the output bits.

## Profile before (`main` `8142c48`)

perf, 52k world, the measured turns only (shares of all process samples):

| Symbol | Share |
| --- | ---: |
| spatial drift (the drift step's work-item closure) | 56.9% |
| `try_tick_agents_with_movements` (inlined phases) | 5.4% |
| marriage (`classify_pair_dist`, the scan closure, `pair_score`) | 7.1% |
| `rand_chacha` `refill_wide` (per-pair transmission rolls) | 2.4% |
| decisions (rayon closure) | 1.7% |
| `sincosf` (zero-distance repulsion fallback) | 1.3% |

Native tick by phase (temporary timers, 1 rayon thread, mean of the 8
measured turns, one paired run):

| Tick phase | 52k base | 52k head | 22k base | 22k head |
| --- | ---: | ---: | ---: | ---: |
| spatial drift (grids, diagnostics, drift) | 319.9 | 142.5 | 60.4 | 30.7 |
| marriage | 31.6 | 20.4 | 7.3 | 4.7 |
| knowledge (propagation 20.0 -> 10.9 / 8.9 -> 4.9) | 23.6 | 14.7 | 10.5 | 6.6 |
| decisions | 12.4 | 12.9 | 5.9 | 5.3 |
| household consolidation | 6.9 | 7.0 | 1.8 | 2.1 |
| satisfaction | 3.5 | 4.4 | 1.8 | 1.8 |
| needs | 3.7 | 4.1 | 1.6 | 1.8 |
| demographics | 3.7 | 4.0 | 1.5 | 1.6 |
| everything else | 23.3 | 23.2 | 9.0 | 10.1 |
| **tick** | **428.8** | **233.2** | **99.7** | **64.7** |

Single runs with the timers on a loaded host: compare the summary for
speed; the unchanged rows show the noise (a few tenths of a ms).

Drift at 52k (dump of turn 27, 54,174 agents): 150.6 M agent-neighbour
pairs a tick (2,835 per agent), 13.5% of them within the repulsion
radius, 385,000 at the zero-distance fallback. The lane loop took 66% of
the drift closure and the per-lane repulsion lists 27%.

## Changes

| # | Commit | Change | Saving (where it matters most) |
| ---: | --- | --- | --- |
| 1 | `9fd11d4` | Morton sort timing only when profiling | 105k agents: 4.2-4.3 ms a tick |
| 2 | `671a71d` | Exact drift kernels, run-time dispatch | 52k drift dump: 295 -> 134 ms (AVX-512) |
| 3 | `e8a51e1` | One ChaCha8 block per transmission roll | 52k: propagation 20.0 -> 10.9 ms |
| 4 | `d1be4af` | Marriage visits only partners within the radius | 52k: marriage 31.6 -> 20.4 ms; first turns 1.82 -> 1.30 s each |

### 1. The discarded sort (`spatial.rs`, `scale.rs`, `ffi`)

At 100,000 agents or more the drift step ran
`sort::sorted_iteration_order` (a full Morton radix sort of the pool)
every tick and threw the result away; only its wall time reached
`SpatialDiagnostics::sort_time_us`, which nothing in the simulation or in
Python reads. It now runs only with `TickOptions::profile_spatial_sort`
(off by default; `AgentSimulator.set_spatial_sort_profiling(True)` from
Python), and `sort_time_us` stays 0 otherwise. With the switch on, the
head world at 104-105k agents spends 4.2-4.3 ms a tick on it (about 0.5%
of the 822 ms turn), so this is the smallest of the four. The sort reads
the pool and returns a list nobody used, so results cannot change.
`spatial_drift_step_with_options` takes the tick options;
`spatial_drift_step_with_mode` keeps its signature.

### 2. Exact drift kernels (`spatial.rs`)

PR #44 evaluated a cell's agents 8 at a time (`drift_lanes`): distance,
direction and density terms in lanes, then per lane a list of repulsion
neighbours summed by the reference code, which recomputed each of those
distances, both directions and the force. Now:

* **Repulsion inside the lane loop.** The reference repulsion direction
  `(agent - n) / dist` is the negated density direction `(n - agent) /
  dist` bit for bit: IEEE subtraction and division are symmetric under
  negation, equal coordinates give `+0.0` either way, and a `+0.0` /
  `-0.0` term leaves a sum that starts at `+0.0` (and so is never
  `-0.0`) unchanged; and `x + f * (-u)` is `x - f * u`. A lane therefore
  subtracts `force * u` with the reference force in block order, in the
  same loop, without a list and without recomputing anything but the force.
  The force division runs only for neighbours some lane repels from (18%
  of a 16-lane group's iterations at 52k); lanes outside the radius
  subtract `+0.0` (`x - 0.0` is `x` for every `x`). The mask is applied to
  the bits of the product: written as a per-lane `if`, LLVM turned the
  selects into a branch and a scalar division per lane, and drift got
  slower (517 ms portable, 418 ms AVX2).
* **Zero-distance fallback table.** The fallback direction depends on
  `(a ^ b) % 360` and the flip only, 720 values: `fallback_directions()`
  builds them once from the reference expressions, and a test compares
  each with joint and separate `cos`/`sin` calls. It was 7% of the new
  kernel's time (385,000 calls of `sincosf` a tick at 52k).
* **Compact lane groups.** Agents are grouped in Z order of position within
  their cell (a result depends only on the agent and its block, never on
  its group), so the union of the group's repulsion neighbourhoods halves
  (899 -> 464 block entries per 8-lane group at 52k).
* **Run-time dispatch.** `DriftKernel::detect()` picks AVX-512F (16 lanes),
  AVX2 (8) or the build baseline (8, SSE2 on x86-64) with
  `is_x86_feature_detected!`. The kernels are the same generic code in
  `#[target_feature]` wrappers: IEEE division and square root are
  correctly rounded at every width, Rust never contracts multiply-add,
  and no reciprocal or rsqrt approximation is used. 32 AVX-512 lanes
  gave the same time as 16 (167 vs 167 ms at that step); 16 is kept.
* **Bigger work items** (128 -> 1,024 agents: a dense cell's block is
  merged and copied once instead of once per 128 agents) and one packed
  `u64` key for the work sort.

Drift alone on the 52k dump (median of 7, one thread; every variant's
output digest equal to the base's):

| Step | Baseline kernel | AVX2 | AVX-512 |
| --- | ---: | ---: | ---: |
| `main` (8 lanes, SSE2) | 295 | | |
| repulsion in the lanes | 300 | 242 | 187 |
| + Z-order groups | 252 | 186 | 164 |
| + fallback table | 242 | 177 | 154 |
| + 1,024-agent items, packed key (head) | 215 | 157 | 134 |

The 52k dump of turn 20 goes 341 -> 154 ms and the 22k dump 61.7 -> 32.2
ms (AVX-512). With four rayon threads on the loaded host (best of 7, load
5-7) the 52k step goes 205 -> 81 ms. The new kernel is bound by the divider: per 16-lane iteration one
`vsqrtps` and two `vdivps` (and the force division in 18% of them),
about 34 cycles, close to the 2 cycles per agent-neighbour pair those
three instructions need.

The `avx512f` target feature is stable only from Rust 1.89, and the
crate's `rust-version` stays 1.85 (its dependencies' floor, pinned by
`tests/test_native_build_lanes.py` and the README): `build.rs` sets the
`chronicler_avx512` cfg on 1.89 or later, and only then is the AVX-512
kernel compiled and offered. An older compiler builds the AVX2 and
portable kernels (checked by forcing the cfg off: no warnings).

### 3. Transmission rolls (`knowledge.rs`)

Every (sender, receiver, packet) transmission roll built a `ChaCha8Rng`
on its own stream and drew one `f32`; the generator computes four
keystream blocks (256 bytes) for the first 4 bytes. `chacha8_first_f32`
computes only word 0 of block 0 (the constants, the seed's eight key
words, block counter 0 and the stream as nonce after four double rounds,
plus the initial word) and converts it as `rand`'s `Standard` `f32` does
(top 24 bits times 2^-24). A test checks it against the generator bit
for bit for 16 seeds and about 2,000 streams each, including the edge
streams and real knowledge stream hashes. Propagation 20.0 -> 10.9 ms at
52k, 8.9 -> 4.9 ms at 22k.

### 4. Marriage within the radius (`formation.rs`)

The exact marriage plan classified every pair of a region's eligible
agents from both sides (1.31 M visits a tick at 52k, each a square
root, a function call and an unpredictable branch); 64% of the pairs are
beyond `MARRIAGE_RADIUS`. Each scan now computes the squared distances to
every eligible agent in one vectorisable pass and visits only those
within the radius (0.47 M visits): `marriage_radius_sq()` is the largest
squared distance whose correctly rounded root is at most the radius;
the root is monotone, so `d2 <= marriage_radius_sq()` keeps exactly the
reference's pairs (a test checks the threshold, its neighbours and
coordinates a few ulps around the radius apart). Farther later agents
are counted as `Far` at once. `TopPartners` keeps the best entries of a
strict total order and the counters are sums, so the visit order does not
matter. The visit takes the precomputed squared distance (the same
expression) and inlines classification and score. A new test runs pairs
straddling the radius against the reference scan.

52k (the paired phase run): 31.6 -> 20.4 ms a tick in the measured turns,
and the first four ticks (every adult unmarried, 55.6 M pairs a tick)
1.82 -> 1.30 s each.

## Tried and not kept

* **Group far-filter.** Leave out block entries farther than
  `DENSITY_RADIUS + 0.0013` from a lane group's bounding box (exact by a
  rounding-margin argument; 15% of iterations for 16-lane Z groups). A
  scalar filter cost more than it saved (portable 252 -> 280 ms, AVX-512
  164 -> 183); an AVX-512 compress-store filter saved 5% of drift
  (136 -> 129 ms), not worth 80 lines of unsafe intrinsics.
* **Dense vectorised marriage classification.** Classifying and scoring
  every pair in 64-pair blocks with branch-free lanes (and a test that the
  branch-free score equals `marriage_score_from`): LLVM did not vectorise
  it (scalar `sqrtss`/`divss`, the closeness division turned into a
  branch), 18.9 -> 34.9 ms. The radius prefilter was kept.
* **Each pair's distance computed once for both agents** (the terms are
  antisymmetric): an agent's sums run over its 3 x 3 block in slot order,
  so the per-pair terms would have to be stored between cells (megabytes
  per dense cell pair); not built.
* **One division for both directions** (a reciprocal with a correction
  step): not exact in every case; excluded by the exact-mode rule.
* **Reuse of id -> slot tables across phases (review item 2).** Five
  `IdSlots` builds a tick (needs, relationship drift, knowledge,
  pre-decision, deaths) take 0.09-0.10 ms each at 52k: reuse could save
  at most 0.5 ms a tick (0.15% of the turn). Not implemented, so no
  generation counter was needed. The movement pass's SipHash map
  (0.27 ms with movements on) and the household dependent index (2.1 ms)
  are separate structures and were left too.
* **Small worlds (review item 5).** The gate and procedural profiles are
  flat (governance 9%, checkpoint 4%, region batches 3%, politics 3%,
  sidecars 3%, native tick 4%): no clear win, nothing changed.

## After

perf, 52k world, measured turns (head): drift kernel 33.5%, the drift
step's other work 2.2%, `try_tick_agents_with_movements` 8.9%, marriage
4.6%, decisions 2.6%; the extension 62.8% of samples (81.8% on `main`),
Python 21.3%. `rand_chacha` and `sincosf` no longer appear.

Remaining hotspots at 52k (head, shares of the native tick): drift 61%
(divider-bound, above), marriage 9% (the visits within the radius:
classification, score and partner cache), knowledge 6% (propagation's
remaining per-pair work), decisions 5.5%, household consolidation 3%
(an O(pairs x migrations) search per bucket and a SipHash index of
minors). Python around the tick is about 30% of the turn and flat
(governance 3.6%, snapshot exports 2.6%, snapshot metrics 2.0%, GC 2.6%).

## Identity

Final: base an export of `main` `7bb2bd4` with its own release extension
(`c8ef41f5...b6ff`, the bytes PR #52 recorded) in `venv-base`; head the
merge `7a62d9d` with `ee58c01e...d8d4` in `venv-head`.

* **9-case matrix** (`scripts/turn_speed_identity.py run`, all cases:
  `--agents off` 300 turns seeds 42 and 7, hybrid 200 turns 42 and 7 with
  sidecars and 1234, procedural 48 x 10 hybrid and off, scaled 22k with
  sidecars and 52k): 399 files (now with the resource ledger sidecars),
  0 differences (bundles decoded and as raw bytes with only
  `generated_at` blanked).
* **3-seed hybrid batch** (`--seed 42 --batch 3 --turns 200 --agents
  hybrid --validation-sidecar`): 335 files; 334 identical (every seed's
  state, sidecars, memory streams, events, chronicle and bundle, and
  `summary.md`). `batch_manifest.json` differs only in run identity:
  timestamps, interpreter path, the native file's path, size and SHA-256,
  the source revision and path, and the bundles' file SHA-256 (which cover
  `generated_at`); every other recorded file hash and run field is equal.
* **Procedural 32 regions x 10 civs** (`--worldgen procedural`, seed 42,
  200 turns, hybrid, sidecars): 117 files, 0 differences.
* **Before the merge**, against `main` `8142c48` (`83b76b41...5b87`, the
  bytes PR #51 recorded), the same three checks on the branch's pre-merge
  code, with the timed build `c4da6ddf...31f6` and again with
  `57d3807f...feae` (the final pre-merge tree, after the AVX-512 kernel
  was gated on the compiler): 395 files, 0 differences; batch 332 files,
  the manifest's run identity only; procedural 116 files, 0 differences.
* **Drift inputs** (52k turns 20 and 27, 22k turn 27): output digests of
  every kernel equal to `main`'s, and equal to the per-agent reference
  (`compute_drift_for_agent` over `query_neighbors`) for every agent.
* No full gate was run: identity is the qualification for this branch.

## Tests

On the merge `7a62d9d` with its extension (`ee58c01e...d8d4`):

* `CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 cargo test --locked
  --manifest-path chronicler-agents/Cargo.toml`: 1,044 passed, 0 failed,
  2 ignored (1,034 before the merge). New:
  `exact_drift_step_matches_reference_for_every_kernel` (whole step,
  parallel path, a cell split into items, fallback knots,
  dead and travelling agents; every available kernel and the detected
  one), `exact_lanes_are_bit_identical_to_reference` now runs every
  kernel, `fallback_directions_match_reference_expressions`,
  `spatial_sort_timing_is_opt_in`, `transmission_roll_matches_chacha8rng`,
  `marriage_radius_threshold_is_exact`,
  `exact_marriage_matches_reference_at_the_radius`.
* The equivalence tests in optimised code, where the kernels vectorise:
  `cargo test --release --locked --manifest-path chronicler-agents/Cargo.toml
  --lib --test test_agent_scale_mode --test test_spatial --test
  test_knowledge --test test_m57a_marriage`: 627 passed (this CPU runs all
  three kernels).
* `pytest -m "not slow" -n 2`: 6,571 passed, 3 skipped, 526 subtests
  (6,546 / 3 before the merge).
* `python scripts/run_python_oracle_checks.py`: PASS in 81.8 s, 2,587
  passed, 50 skipped, ten chunks.
* New `tests/test_rust_turn_speed.py`: the Python sort-profiling switch
  (off by default, round trip; native).

## Not done

* Not run on a CPU without AVX-512 or AVX2, nor on aarch64: there the
  AVX2 or portable kernel runs; both are covered by the equivalence tests
  here (forced through the test-only `spatial_drift_step_with_kernel`) but
  not timed on such hardware.
* Built and tested only with rustc 1.97: the build without the AVX-512
  kernel (what 1.85-1.88 compile) was checked by forcing its cfg off, not
  with an older toolchain.
* Decisions, household consolidation, the rest of knowledge propagation
  and the Python side were profiled but not changed (see After).

## Reproduce

    # identity (base: an export of main with its own release build in venv-base)
    venv-base/bin/python base-src/scripts/turn_speed_identity.py run id/base
    venv-head/bin/python scripts/turn_speed_identity.py run id/head
    venv-head/bin/python scripts/turn_speed_identity.py compare id/base id/head
    # one timed run per side and world (interleave them)
    RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONHASHSEED=0 \
        venv-head/bin/python scripts/turn_phase_profile.py --target 43700 --regions 12 --civs 4 \
        --warmup 20 --turns 8 --no-instrument
