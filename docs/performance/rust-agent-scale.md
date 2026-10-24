# Rust agent scale, October 2026

Branch `perf/rust-agent-scale`. Base: `eca9359`, the merge of
`feat/geography-2` (`47f1272`) into `integrate/wave-1` (`01f2502`). All
"base" numbers below come from an export of that tree with its own compiled
extension; "new" numbers come from this branch's final build.

The native agent tick was superlinear in agents per region. The work below
makes the default (**exact**) mode much faster while keeping every output
byte-identical, and adds an opt-in **fast** mode whose per-agent work no
longer grows with region density.

Summary (real pipeline, 12-region template world scaled up; details below):

| start agents | native tick: base | exact | fast | whole turn: base | exact | fast |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20,000 | 1.26 s | 0.19 s | 0.06 s | 1.54 s | 0.50 s | 0.33 s |
| 50,000 | 20.5 s | 1.10 s | 0.13 s | 21.2 s | 1.94 s | 0.83 s |
| 100,000 | 80.5 s | 4.29 s | 0.40 s | 81.9 s | 6.15 s | 2.02 s |

* **Exact mode** (default): byte-identical artifacts on every checked run
  (default, 64-region and 20K-agent worlds, demographics-only and hybrid,
  the subset gate's 2,113 files, synthetic digests up to 100K agents). The
  native tick is 6.7x faster at 20K agents, 18.6x at 50K, 18.7x at 100K.
* **Fast mode** (`--agent-scale-mode fast`): bounded work per agent; 200x
  faster than base at 100K. Bonds, marriages, marriage composition,
  relationship counts, survival and spatial clustering stay within
  seed-to-seed noise in the real pipeline (8 seeds); in a very uniform
  synthetic world it marries 0.23% fewer agents.
* **Practical scale** for at most 1 s per turn: native tick ~54K agents
  exact / ~150K fast in the 12-region world, ~140K exact / ~330K fast over
  150 regions; whole turns ~37K exact / ~67K fast, where Python (governance
  metrics, bridge post-processing) now dominates.

## Measuring

Two benchmarks, both new:

* `chronicler-agents/examples/scale_bench.rs`: the native tick alone on a
  synthetic world (uniform agents per region, spatial attractors, mixed ages,
  cultures and beliefs, no inter-region migration). `--hash` prints FNV
  digests of the whole pool and of every event, which is how exact-mode
  identity was checked at 50K-100K agents.

      cargo run --release --example scale_bench -- --agents 100000 --regions 12 \
          --turns 12 --warmup 4 --mode exact --hash

* `scripts/agent_scale_benchmark.py`: the real CLI pipeline
  (`execute_run`, `--simulate-only`, hybrid agents). In a child process it
  multiplies every region's carrying capacity and starting population so the
  pool starts at the target agent count; default worlds are not changed. It
  times `AgentSimulator.tick` (the native agent tick, all rayon threads) and
  the whole turn, wall and process CPU, and reports medians after warm-up.
  `--seeds` and `--social` add per-seed bond, marriage and spatial
  statistics; `--source-root`/`--native-root` run another tree.

      python scripts/agent_scale_benchmark.py --targets 1000,5000,20000,50000,100000 \
          --agent-scale-mode fast --out curve_fast.json
      python scripts/agent_scale_compare.py exact.json fast.json

The machine is a shared 4-core host; other agents kept it at load 3-6, so
wall times are noisy. Process CPU times are the steadier numbers. Default
rayon threads (4) throughout.

## Where the time went (base)

Per-phase timing of the base native tick (temporary instrumentation, not
committed), synthetic 20K agents over 12 regions:

| phase | turns 0-3 | later turns |
| --- | ---: | ---: |
| spatial drift | 400-550 ms | 300-350 ms |
| marriage scan | 230-400 ms | 1-2 ms |
| everything else | ~15 ms | ~15 ms |

* **Spatial drift** (`spatial.rs`): for every agent, `query_neighbors`
  allocated a vector of the 3 x 3 block of a fixed 10 x 10 grid, sorted it,
  copied positions into a second vector and computed every distance twice.
  Agents are placed at their occupation's attractor, so blocks hold most of a
  region: cost ~ agents x agents-per-region, single-threaded.
* **Marriage** (`formation.rs`): every pair of eligible (adult, unmarried)
  agents was scored, the within-radius candidates (most of them, since agents
  cluster) materialised and sorted, then accepted greedily. Each region's
  first scan (turns 0-3) has nearly everyone eligible: O(n^2) time and memory
  (at 8K agents per region, millions of candidates per scan).
* **Formation** rebuilt an alive-agent id map for every scanned region. The
  pair loop itself is cheap in practice (it stops at 50 bonds per region).

## Exact mode: output-identical changes

Exact mode is the default and is byte-identical to the base (proof below).
No RNG draw, candidate set, accumulation order or counter changed.

1. **Spatial drift, per-cell blocks.** All agents of one 10 x 10 cell share
   the same 3 x 3 block, so the block's slot-sorted list is merged once per
   cell (cells are filled in slot order; hand-built grids are sorted) instead
   of allocated and sorted per agent. The list is exactly what
   `query_neighbors` returned plus the agent itself, which gets an infinite
   distance so both force loops skip it as if absent. Each neighbour's
   distance is computed once (`agent - n` is the exact negation of
   `n - agent`, so both loops' distances are the same bits) and both loops add
   the same terms in the same order. Agents depend only on the old positions,
   so they are computed in parallel (cell chunks of 128) and written back
   afterwards. Attractor-occupancy diagnostics run per region in parallel
   (integer counts). `compute_drift_for_agent` is unchanged and is the oracle
   of a bit-identity unit test over clustered, duplicate, edge and boundary
   positions.
2. **Marriage, planned matching.** Each scanned region is planned in parallel
   from the unchanged pool and committed in region order. This is exact: a
   marriage writes only the two spouses' relationship slots, every planned
   spouse is distinct, and nothing a plan reads (age, spouse status, parents,
   civ, belief, culture, position, relationship capacity) changes during the
   scan. Whether a bond can be written depends only on the agent (a free or
   evictable slot), so failed upserts are agents removed from the graph. The
   reference greedy (score desc, hash asc, then insertion order) is a strict
   total order on pairs, and greedy matching under a strict order is the
   unique matching obtained by repeatedly accepting pairs that are each
   other's best remaining partner. The plan computes that with per-agent
   top-8 partner caches (rescanning only when a cache runs out), skips the
   hash when the score alone cannot enter a full cache, and never materialises
   or sorts the candidate list. Rejection counters are tallied over every
   pair as before. Non-finite positions (never seen; the reference comparator
   is then not a total order) fall back to the kept reference scan,
   `marriage_scan_reference`, which is also the oracle of the equivalence
   test.
3. **Formation:** the alive id -> slot map is built once per scan (ids and
   liveness do not change during it).

Rayon is used only where each work item is a pure function of state that no
other item writes (drift agents, marriage regions and agents, per-region
diagnostics) and results are merged in a fixed order; outputs do not depend on
the thread count (tested with 1, 3 and 4 threads).

Tried and dropped: evaluating 8 agents of a cell as SIMD lanes against their
shared block (bit-identical, but slower on this x86-64 baseline build because
every lane pays every division).

## Fast mode (`--agent-scale-mode fast`)

Opt-in, deterministic, and **not** output-identical. Per-agent work is
bounded independently of region density:

| phase | exact | fast |
| --- | --- | --- |
| spatial drift | every agent of the 3 x 3 block of a 10 x 10 grid | population-sized grid (10 x 10 to 20 x 20 cells, never narrower than the 0.05 repulsion radius), stride sample of at most 96 block entries offset by slot |
| marriage | every eligible pair; greedy matching | each eligible agent examines a stride sample of at most 256 agents around it in a population-sized grid and keeps its 24 best partners in the reference order; the same greedy matching runs on the union. Regions with at most 256 eligible agents use the exact scan |
| formation | each agent against every later agent in the shuffled order | against the next 64 |

Small regions are unchanged in fast mode (blocks of at most 96 agents,
regions of at most 256 eligible agents, at most 65 agents for formation).
Marriage counters in fast mode count the examinations made, not all pairs.

Switch: `AgentScaleMode`/`TickOptions` in `chronicler-agents/src/scale.rs`;
`try_tick_agents_with_options`; FFI `AgentSimulator.set_agent_scale_mode`
and the `agent_scale_mode` getter; `AgentBridge(..., agent_scale_mode=)`;
CLI `--agent-scale-mode {exact,fast}`, which requires an agent mode. Exact
makes no extra native call, so existing runs and old extensions behave as
before; fast with an old extension fails clearly. The mode is not stored in
`state.json` (that would change exact-mode bytes); pass it again on
`--resume`. Batch workers inherit it from the parsed arguments.

## Identity proof (exact mode)

Base tree export plus base extension against this branch's final build
(head `1db51da`, extension sha256 `d746298d...`; the default, 64-region and 20K-agent sets were re-run on it), every artifact in the run directory hashed
(`chronicle_bundle.json` without `metadata.generated_at`), CLI
`--simulate-only`, default rayon threads:

| Check | Result |
| --- | --- |
| Default world (8 regions, 4 civs), `--agents hybrid`, 200 turns, seeds 42 / 7 / 1234 | byte-identical (8 files each) |
| Default world, `--agents demographics-only`, 200 turns, seeds 42 / 7 / 1234 | byte-identical (7 files each) |
| Procedural 64 regions x 16 civs: hybrid 100 turns seeds 42 / 7, demographics-only 100 turns seed 1234 | byte-identical (20 / 20 / 19 files) |
| 12-region template world scaled to 20,000 starting agents (benchmark capacity scaling), 30 turns: hybrid seeds 42 / 7, demographics-only seed 1234 (marriage first scans of 7,700-agent regions included) | byte-identical (8 / 8 / 7 files) |
| `scale_bench --hash`, synthetic 12 regions: 1K / 5K / 20K / 50K agents x 16 turns, 100K x 8 turns | pool and event digests identical to the base build |
| Subset gate (`m53b_run_validation.py --profile subset --parallel 2`, 20 seeds x 200 turns, sidecars) both PASS; all 2,113 run files byte-identical (the reports differ only in their batch-directory paths); `validation_compare` against the base report: NO REGRESSION, every metric delta 0.0 |

The subset gate and the 50K/100K digests ran on the build before the last
commit (`ca552db`), which differs only in running drift for pools under 4,096
agents on one thread; that path is covered by the default-world set re-run on
the final build and the 1K-20K digests.

Unit and integration tests pin the pieces: the per-cell block path against
`query_neighbors` + `compute_drift_for_agent` bit for bit (clustered,
duplicate, corner and cell-boundary positions, 3-1,200 agents);
`marriage_scan` against `marriage_scan_reference` (10 seeds x 4 cadence
turns: counters and every relationship slot, with incest, hostile civs,
already-married and fully protected agents, duplicate positions); default
formation equal to the explicit exact mode; drift independent of the rayon
thread count (1 / 3 / 4); and an exact-mode CLI run equal to the default.

## Statistical equivalence (fast vs exact)

Fast mode is judged by whether its outcomes stay within seed-to-seed noise
of exact mode. `scripts/agent_scale_compare.py` prints means and standard
deviations over seeds and Welch's t for the difference (|t| < 2: within
noise).

**Real pipeline**, 12-region template world scaled to 20,000 starting agents
(about 30,000 alive on average, 7,700 in the largest region at the start),
hybrid, 40 turns from turn 0 (so every region's first marriage scan is
included), seeds 1-8 per mode
(`agent_scale_benchmark.py --targets 20000 --seeds 1,...,8 --warmup 0
--turns 40 --social`):

| metric | exact mean (sd) | fast mean (sd) | diff | Welch t |
| --- | ---: | ---: | ---: | ---: |
| bonds formed per 1,000 agent-turns | 2.468 (0.16) | 2.438 (0.18) | -0.030 | -0.36 |
| marriages per 1,000 agent-turns | 15.56 (0.39) | 15.62 (0.47) | +0.063 | +0.29 |
| same-civ share of marriages | 0.9837 (0.0036) | 0.9858 (0.0056) | +0.0021 | +0.91 |
| same-faith share of marriages (both have a faith) | 0.9695 (0.0083) | 0.9697 (0.010) | +0.0003 | +0.05 |
| mean relationships per agent, final turn | 2.761 (0.061) | 2.734 (0.069) | -0.027 | -0.82 |
| alive agents, final turn | 39,550 (2,100) | 38,890 (2,500) | -665 | -0.58 |
| spatial hotspot cells per tick (all regions) | 114.9 (10) | 112.5 (12) | -2.4 | -0.43 |
| max cell occupancy per tick (sum over regions) | 3,694 (330) | 3,684 (330) | -10 | -0.06 |

Over those 8 x 40 turns exact mode formed 151,244 marriages and 23,992
bonds, fast mode 151,285 and 23,651. Native tick medians: exact 268 ms
wall / 346 ms CPU, fast 134 / 136 ms; whole turn 924 vs 775 ms.

**Native tick, synthetic world**, 100,000 agents over 12 regions (8,300 per
region), 12 turns from turn 0, seeds 1-5 per mode (`scale_bench --warmup 0
--turns 12 --seed N`):

| metric | exact mean (sd) | fast mean (sd) | diff | Welch t |
| --- | ---: | ---: | ---: | ---: |
| bonds formed per 1,000 agent-turns | 0.8606 (0.0004) | 0.8606 (0.0004) | 0.0000 | -0.01 |
| marriages per 1,000 agent-turns | 33.93 (0.031) | 33.85 (0.032) | -0.078 (-0.23%) | -3.88 |
| married share of adults, final turn | 0.9659 (0.0005) | 0.9645 (0.0005) | -0.0015 | -4.62 |
| same-faith share of marriages | 0.9989 (0.0002) | 0.9995 (0.0001) | +0.0005 | +6.63 |
| mean relationships per agent, final | 1.625 (0.003) | 1.620 (0.003) | -0.006 (-0.3%) | -3.18 |
| alive agents, final | 129,400 (180) | 129,400 (180) | +0.4 | 0.00 |
| occupied 10 x 10 cells | 0.641 (0.033) | 0.639 (0.033) | -0.002 | -0.10 |
| spatial hotspot cells per tick | 169.7 (4.0) | 172.5 (4.2) | +2.8 | +1.07 |
| max cell occupancy per tick (sum) | 16,580 (810) | 16,100 (820) | -477 | -0.92 |

The synthetic world is so uniform that seed-to-seed spread is about 0.1%,
which makes even the small marriage differences detectable: fast mode marries
0.23% fewer agents per turn (an agent whose 24 kept partners are all taken
stays single that scan, where exact mode would reach its 25th), and its
spouses share a faith slightly more often. Bonds, survival and the spatial
distribution are within noise. In the real pipeline, where runs differ more
between seeds, every measured outcome is within noise.

## Scale curves

### Native tick alone (synthetic world)

`scale_bench`, uniform agents per region, median wall ms per tick after 4
warm-up turns (12 measured; 4 at 100K exact/base) and mean process CPU ms per
tick. Base and exact digests are identical at every size.

| agents (regions) | base wall / CPU | exact wall / CPU | fast wall / CPU |
| ---: | ---: | ---: | ---: |
| 1,000 (12) | 4.3 / 5.3 | 3.9 / 4.8 | 3.3 / 4.2 |
| 5,000 (12) | 31 / 31 | 12 / 18 | 10 / 14 |
| 20,000 (12) | 357 / 355 | 75 / 125 | 46 / 63 |
| 50,000 (12) | 2,136 / 2,160 | 382 / 666 | 132 / 174 |
| 100,000 (12) | 9,665 / 9,755 | 1,447 / 2,698 | 288 / 378 |
| 250,000 (48) | - | 1,777 / 4,358 | 739 / 1,005 |
| 500,000 (48) | - | - | 1,524 / 2,065 |
| 1,000,000 (96) | - | - | 2,941 / 4,467 |

(1K row: median of three interleaved base/exact pairs, 40 turns each; at
this size the difference is noise, so small worlds are not slowed down.)

### Real pipeline, 12-region template world

`agent_scale_benchmark.py`, seed 42, 4 civs, hybrid, region capacities and
starting populations scaled to the target (5 of the 12 regions start
populated, so the densest region holds ~39% of the agents). Medians over
the measured turns ("alive" is the median live pool). Base: 3 warm-up + 8
measured turns up to 20K, 1 + 3 at 50K/100K (a base turn takes 20-80 s
there). New: 3 + 8 up to 20K, 2 + 6 at 50K/100K; marriage first scans fall in
warm-up or in one measured turn.

Native agent tick (`AgentSimulator.tick`), wall / process CPU:

| start agents | alive (base / new) | base | exact | fast |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1,158 / 1,158 | 7.0 / 7.1 ms | 4.6 / 5.6 ms | 3.6 / 4.2 ms |
| 5,000 | 5,930 / 5,930 | 85 / 85 ms | 19 / 38 ms | 15 / 21 ms |
| 20,000 | 24,027 / 24,027 | 1,257 / 1,255 ms | 188 / 422 ms | 57 / 79 ms |
| 50,000 | 54,114 / 57,394 | 20.5 / 20.3 s | 1.10 / 2.65 s | 0.13 / 0.20 s |
| 100,000 | 108,079 / 114,786 | 80.5 / 79.8 s | 4.29 / 9.97 s | 0.40 / 0.59 s |

Whole turn, wall / process CPU:

| start agents | base | exact | fast |
| ---: | ---: | ---: | ---: |
| 1,000 | 42 / 40 ms | 38 / 38 ms | 33 / 33 ms |
| 5,000 | 170 / 170 ms | 94 / 113 ms | 101 / 105 ms |
| 20,000 | 1.54 / 1.55 s | 0.50 / 0.77 s | 0.33 / 0.36 s |
| 50,000 | 21.2 / 21.2 s | 1.94 / 3.59 s | 0.83 / 1.14 s |
| 100,000 | 81.9 / 81.3 s | 6.15 / 11.6 s | 2.02 / 2.37 s |

Identical alive counts up to 20K reflect exact mode's identical runs (the
50K/100K rows used different warm-up windows for base and new). At 100K the
densest region starts with 38,600 agents, where exact drift and the first
marriage scans are still heavy; fast mode is 200x faster than base there.
Outside the native tick a turn costs about 0.3 s at 24K agents and 1.6-1.9 s
at 115K, almost all in Python (see Gaps).

### Real pipeline, 150-region procedural world

Geography 2.0 world, `--regions 150 --civs 30`, seed 42, 45 regions start
populated; 2 warm-up + 5 measured turns.

| start agents | alive (exact / fast) | exact native tick | fast native tick | exact turn | fast turn |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20,000 | 22,163 / 22,226 | 53 / 73 ms | 46 / 67 ms | 0.58 / 0.60 s | 0.50 / 0.51 s |
| 100,000 | 113,821 / 113,901 | 0.69 / 1.13 s | 0.28 / 0.43 s | 2.74 / 3.34 s | 2.15 / 2.27 s |
| 250,000 | 285,729 / 285,837 | 3.07 / 5.50 s | 0.84 / 1.08 s | 8.83 / 11.3 s | 5.77 / 6.18 s |

(wall / process CPU). With agents spread over more regions (at most 11,400
in one region at 250K) exact mode stays near 0.7 s per native tick at 100K
agents; fast mode keeps 285K agents under 1 s. Whole turns are dominated by
Python here: 1.9 s of a 2.2 s turn at 114K agents and 4.9 s of 5.8 s at 286K
in fast mode.

Base was not run on these worlds; at 20K agents in the template world it
already needed 1.3 s per native tick.

## What is practical now

On this shared 4-core host, the largest population that stays at or below
1 s per turn (alive agents, interpolated on a power law between the two
nearest measurements):

| budget | base | exact (default) | fast |
| --- | --- | --- | --- |
| native agent tick, 12-region template world | ~21K (1.26 s at 24K) | ~54K (1.10 s at 57K) | ~150K, the u16 region cap (0.40 s at 115K) |
| native agent tick, 150-region world | - | ~140K (0.69 s at 114K) | ~330K (0.84 s at 286K) |
| native agent tick, synthetic uniform world | ~34K (2.1 s at 50K) | ~83K (1.45 s at 100K) | ~330K (0.74 s at 250K, 1.5 s at 500K, 2.9 s at 1M) |
| whole turn, 12-region template world | ~18K (1.54 s at 24K) | ~37K (0.50 s at 24K, 1.9 s at 57K) | ~67K (0.83 s at 58K, 2.0 s at 115K) |

The native tick is no longer what limits whole turns: above ~50K agents the
Python side (governance elite metrics and bridge post-processing) costs more
than the fast-mode tick. The roadmap's 500K-1M agents are feasible for the
native tick in fast mode at a few seconds per turn (synthetic: 1.5 s at 500K,
2.9 s at 1M over 48-96 regions), not yet for whole turns.

## Tests

* `python -m pytest -q -m "not slow" -n 2` with the native extension built
  from this branch: 5,277 passed, 3 skipped (the Geography 2.0 merge base
  reports 5,267 passed, 3 skipped; the difference is the 10 new tests).
* `cargo test --manifest-path chronicler-agents/Cargo.toml` (debug, no
  debuginfo, separate target directory): 874 passed, 0 failed, 2 ignored
  (the timed regression gate).
* `cargo test --release --test regression -- --ignored`: @@REGRESSION@@
* New Rust tests: `spatial::scale_equivalence_tests` (bit identity of the
  block path, sorting of hand-built cells, fast-grid bounds, fast-sample
  determinism) and `tests/test_agent_scale_mode.rs` (exact marriage against
  the reference scan, non-finite fallback, fast marriage determinism and
  coverage, default formation, drift thread-count independence, fast drift
  determinism, option parsing).
* New Python tests: `tests/test_agent_scale_mode.py` (CLI option, agent-pool
  requirement, bridge sends nothing in exact mode and `fast` once, unknown
  modes, old-extension error, native round trip, explicit exact equals the
  default run byte for byte, fast runs are deterministic).

## Gaps and next steps

* **Full-turn time above ~40K agents is Python.** cProfile of a 50K-agent
  fast-mode hybrid turn: the Phase 8 governance tick takes 58% (per-civ
  `governance_runtime._elite_metrics` / `elite_metrics.compute_elite_metrics`
  walk every agent in Python), the native agent tick 11%, and
  `AgentBridge._process_tick_results` 13% (mostly arro3 `to_pylist`). These
  are the next targets for whole-turn scale; they are outside this branch
  (governance and bridge semantics, float accumulation order).
* **Exact mode is still density-bound** by design: drift costs agents x
  block size and each region's first marriage scan costs (eligible)^2 pair
  checks (about 0.3-0.4 s per turn for turns 0-3 at 50K synthetic agents,
  down from 2-3 s, with no candidate list in memory). Only fast mode bounds
  them.
* **Fast mode is calibrated, not qualified.** Its constants are marked
  `[CALIBRATE M61b]`; equivalence was measured at 20K agents in the real
  pipeline (8 seeds x 40 turns) and at 100K synthetic agents, not over long
  runs or the 200-seed gate. Its marriage counters count examinations, not
  all pairs. Its mode is not saved in `state.json`.
* **Region population is `u16`** across the bridge (65,535 per region), so
  very large worlds need many regions; the benchmark refuses to scale a
  region past 60,000.
* Above 100K alive agents the drift diagnostics still run the M55a Morton
  sort of every alive agent whose result is discarded
  (`SPATIAL_SORT_AGENT_THRESHOLD`, kept as M61b profiling infrastructure;
  not measured separately here).
* Remaining O(N) sequential phases dominate a fast-mode tick at 250K+
  agents (demographic apply, relationship drift's per-tick `BTreeMap`,
  knowledge, SipHash maps): next candidates for exact speedups.
