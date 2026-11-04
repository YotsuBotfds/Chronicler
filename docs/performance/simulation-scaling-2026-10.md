# Simulation scaling: next experiments, October 2026

Read-only research against integration `23f6136f02d7a30975a964715892ea9f93adc8b4`
(2026-10-28), after PR #67 and the historical-forensics, capacity-aware
refugee routing and granary-view integration. No new timings were collected:
native compilation, identity checks and full tests were sharing this host.
The measurements below belong to their cited source, build and workload;
the proposed gains are hypotheses, not benchmark results.

The next useful work is a validation turn index, lean ablation-fork outputs,
and a fresh production workload matrix. For one crowded simulation, household
decision indexing is a smaller exact candidate. For long runs, avoid repeatedly
serializing an ever-growing prefix. More SIMD alone will not address these
different limits. PR #53 already optimized the native drift kernel and rejected
cross-phase `IdSlots` reuse as too small to justify the complexity.

## What has actually been measured

| Evidence | Measured result | Source and practical limit |
| --- | --- | --- |
| PR #53 native second pass | At 23,604 / 53,696 / 104,840 median alive agents, 106.7 / 298.1 / 822.1 ms process CPU per measured turn; 12 template regions. Procedural 48 x 10 and default gate worlds stayed approximately flat at 64.6 and 19.3 ms. | [turn-speed-2026-10b.md](turn-speed-2026-10b.md), `8142c48` vs its pre-merge candidate, five interleaved runs; also a separate comparison against merged `7bb2bd4`. 4 vCPU Xeon 2.30 GHz, AVX-512, 15 GB RAM, Ubuntu 24.04, Python 3.13.17, rustc 1.97; shared-host load 1.6–5.3, one Rayon/OpenBLAS/OMP thread. These are not current-integration throughput numbers. |
| PR #53 remaining profile | At 52k, drift kernel 33.5% plus other drift work 2.2% of process samples; marriage 4.6%. Native-tick shares were drift 61%, marriage 9%, knowledge 6%, decisions 5.5%, household consolidation 3%. | Same report, “After”. Sampling shares and separately instrumented phase shares have different denominators; do not add or multiply them into a new precise profile. |
| Exact checkpoint qualification | 52k-labelled world at turn 20: 44,725 alive, 5.40 MB checkpoint, 0.42 s write / 0.45 s read. Write stages: native 13 ms, pickle 184 ms, zlib 203 ms, header 1 ms, atomic write/fsync 13 ms. | [checkpoint-continuation.md, §7](../integration/checkpoint-continuation.md#7-cost), source `db5eff4` vs checkpoint branch through `1d9eca5`, native build `99c1e1d5...e12f`; Linux x86-64, four shared vCPU, Python 3.13.17, one Rayon thread, load 7–10. Wall-clock medians, not uncontended CPU latency. |
| Bundle v6 | No-Rust size-guard bundle 22.67 → 8.61 MiB; procedural 48 x 10 hybrid 33.23 → 14.72 MiB. Size-guard history encoding approximately 0.8 s, decoding 0.6 s. | [bundle-v6.md](bundle-v6.md), base `ea08126`, native build from `84bfb44` where used; Linux/Python 3.13.17. That document does not identify a CPU for these codec timings. Compression in the file does not imply equally small decoded RAM. |
| Procedural causal validation, design 2 | Plain batch 1,045 s; three arms, 2,700 forks, 4,094 s; validation 637 s; 1 h 36 min overall. Two default arms about 45 minutes. | [community-anchoring.md, §6](../integration/community-anchoring.md), frozen tree `e67c083`, native digest `8497d374...`; its cost section does not restate CPU/host details, so this is experiment-specific cost evidence, not a current or portable timing. It uses nine fork points per seed, not the older two-fork design. |

Older [Python scale](python-scale.md) and [Rust agent scale](rust-agent-scale.md)
reports explain how previous bottlenecks were removed. Their per-agent Python
elite walks, element-wise Arrow decoding, discarded production Morton sort,
old marriage scan and unoptimized drift must not be presented as unaddressed
current problems. PR #53 includes AVX-512/AVX2/portable runtime dispatch,
repulsion inside lanes, the zero-distance table, larger work items, the
marriage radius prefilter and one-block knowledge transmission rolls.
Its unkept far-filter and vectorized marriage experiments are recorded too.

## Four independent scaling axes

Let `A` be alive agents, `R` regions, `C` relevant civilizations, `H` completed
turns, `S` seeds, `F` fork points per seed, and `Q` ablation arms. Keep the
starting values and realized distributions separate: secession increases
civilization records and migration concentrates agents.

| Axis | Cost to watch | What a benchmark must record |
| --- | --- | --- |
| Agent count and density | Exact drift visits agents times entries in their cell's fixed 3 x 3 block. Eligible marriage scans still test distances against the eligible set. Concentration can dominate total `A`. | Alive agents, maximum region population, occupied cells/block sizes, eligible singles, pair counters and trips. Compare concentrated and spread maps. |
| Regions and civilizations | Pairwise intelligence/perception, diplomacy and relationships; per-region systems and Arrow marshalling; political graph/path work. `C²` tables can grow while population declines. | Living civs **and** total historical civ records, contact pairs, owned regions, roads/trade edges and active optional systems. |
| Horizon | In-memory snapshots, accumulated agent events/accounts/names, final assembly/codec, and full-prefix saves. | Early/middle/late turn windows, finalization separately, raw/packed checkpoint sections, RSS and bytes written. |
| Ensemble and forks | `S` independent runs, plus roughly `S × F × Q × 22` fork turns under the present 20-turn-window design; checkpoint restore, imports, discarded output and validation also cost time. | Completed seeds per minute, arm jobs per minute, CPU-seconds, peak RAM/disk, I/O and slow-tail latency, not just milliseconds per tick. |

The PR #53 count ratios are 2.27x and 1.95x, while the corresponding measured
turn CPU ratios are 2.79x and 2.76x. Descriptive log-slopes are about 1.25 and
1.52. These three points do not identify a universal complexity law: they
change density and alive population, use short early-run windows, and do not
hold every component constant. They do justify measuring occupancy rather
than advertising a single “agents per second” number.

Native region population and carrying capacity are still `u16`
([region.rs](../../chronicler-agents/src/region.rs)); the agent-scale harness
rejects scaled regions above 60,000. A million-agent plan therefore needs
enough regions and an explicit density distribution. It is not valid to
multiply one dense 12-region result by ten or silently overflow the bridge.

### Amdahl bounds, not promised gains

For a component occupying fraction `p` of elapsed work, improving it by `g`
gives `1 / ((1-p) + p/g)` for the whole workload under that decomposition.
Using only PR #53's historical **process-sample** shares as an illustration,
halving the 35.7% drift work would suggest about 1.22x, and removing it
entirely a 1.56x ceiling. Halving its 4.6% marriage share suggests 1.024x.
These are arithmetic scenarios, not predictions of wall-clock speed on this
integration. A component's share moves when the workload or another component
changes. `IdSlots` reuse's previously measured <0.15% whole-turn ceiling
remains a reason to leave it alone until a new profile disproves that bound.

## Experiment queue

The candidates below are ranked by clarity of mechanism and bounded proof
cost, not by an invented speedup. Measure the relevant boundary first; reject
a change if its whole-workload benefit is lost in run-to-run variability or
its complexity outweighs that benefit.

### 1. Index validation columns by turn

**Observed in current source:**
[`validation_io._columns_for_turn`, `_graph_snapshot_from_columns`,
`_iter_graph_snapshots`, `_iter_needs_snapshots`](../../src/chronicler/validation_io.py)
scan complete `turn` columns for each sampled turn. Cohort joint-turn
selection also constructs snapshot lists, and other oracles ask for the
same views. With `J` sampled turns and `A` agent rows per sample, scanning
the accumulated table `J` times can inspect order `A × J²` rows rather than
`A × J`. That expression describes the filtering step, not the whole oracle.

**Exact candidate:** build a separate, immutable `turn -> row ranges/indices`
index once per input table and reuse the same ordered rows. Use contiguous
ranges only after checking monotonic turns; preserve an index-list fallback
for shuffled/legacy input. Do not insert cache keys into schema dictionaries
whose consumers iterate every column. Do not cache across changed files or
change sampled turns, matching order, death censoring or pooling arithmetic.

**Cheap discriminator:** on one retained seed, count row-turn comparisons and
time only turn filtering before and after an index. Then re-score its retained
batch, requiring every oracle result and diagnostic to be identical. Keep the
current no-data, unaligned-table, duplicate-id and old-method cases. No new
simulation or 200-seed rerun is needed merely to re-score unchanged inputs.

### 2. Avoid manufacturing ablation outputs that are immediately deleted

**Observed in current source:**
[`ablation_arms._fork_command`, `_keep_fork_outputs`](../../src/chronicler/ablation_arms.py)
launch a fresh CLI process per fork, retain compressed `agent_events.arrow`
and a small `fork.json`, then delete other outputs. Each resumed run carries
its prefix history and can serialize full state/bundle/memory files just to
discard them. Re-reading a late checkpoint and finalizing a long prefix can
matter more than the fork's 22 new turns. There is no new timing for the split.

**Trajectory-preserving, output-policy candidate:** an explicit internal
events-and-fork-metadata output policy for ablation jobs. Keep the complete
event stream needed for the validator's **prefix equality** check and window
counts; preserve final forced settlement detection and turn boundaries.
Skip only unused exports and prose work after establishing what is read.
The default CLI output must remain unchanged. Report metadata and source/
checkpoint identities must be built from the same run, not copied guesses.

**Cheap discriminator:** compare one early and one late fork on the same
checkpoint, recording imports/restore, 22-turn compute, each export, compression
and cleanup separately. Require equality of retained event rows/schema,
fork metadata, window counts and final simulation state in a verification
run. Then trial several arms/seeds with the unchanged validator. A worker
that handles multiple forks could additionally amortize imports, but needs
explicit resetting of module/private/native caches; it is a second experiment,
not a prerequisite for eliminating unused exports.

### 3. Reduce household decision-list rescans

**Observed in current source:**
[`household::consolidate_household_migrations`](../../chronicler-agents/src/household.rs)
does `find`, `any` and repeated `retain` over a bucket's migrations and other
decisions for each sorted spouse pair and dependent. PR #53 left this path
unchanged; it reported 7.0 ms in one instrumented 52k run, approximately 3%
of the native tick. It may matter more under mass displacement; it is not a
reason to promise a large ordinary-run win.

**Exact candidate:** a bucket-local slot lookup plus explicit active/position
tracking. Preserve the sorted-pair sequence, mutations visible to later
households, first-match lookup, last-entry deduplication, follower insertion
order, stats and event order. A lookup over the original immutable snapshot
alone is incorrect because earlier households edit these lists.

**Cheap discriminator:** replay real pending-decision buckets from a normal
turn and a migration shock against the kept reference; compare the complete
decision vectors, counters and native output hashes. Measure lookup/update
work as migration count changes. A general cross-phase id-map cache was
already rejected; this is a different index over mutable pending decisions.

### 4. Bound all-pairs work within a read-only construction interval

**Observed in current source:** [`main.execute_run`](../../src/chronicler/main.py)
already builds borders once and caches accuracy per pair for snapshot stat
reads. Procedural snapshots already restrict these pairs to living civs;
templates deliberately preserve all historical civ records. In
[`intelligence.compute_accuracy`](../../src/chronicler/intelligence.py), trade,
federation, vassal, war and character/grudge membership still contribute work
inside pair loops; perceived-stat noise still constructs a seeded Python RNG.

**Exact candidate:** precompute membership facts within the **same unchanged
snapshot boundary**, retaining the existing arithmetic and pair order. Count
the existing cost at `C=4,10,30,60` before choosing a cache. Preserve duplicate
name fallback behavior. Broad caching across action resolution, wars,
secession, conquest or callback boundaries is unsafe. RNG replacement is a
separate, much harder exactness project; a hash-only noise substitute changes
the model's realized trajectory.

**Cheap discriminator:** profile fixed late-world snapshots with growing
living and historical civ sets, and report cache-build time too. Compare
every pair's accuracy and errors, including duplicates and zero contact,
before a full-run identity comparison. A faster synthetic all-pairs loop
does not establish a production run improvement.

### 5. Long-horizon save and finalization paths

**Observed in current source:** [`bundle.assemble_bundle`](../../src/chronicler/bundle.py)
materializes snapshot/world/event dictionaries before
[`bundle_codec`](../../src/chronicler/bundle_codec.py) generates deltas and a
complete JSON string. World timeline dictionaries and the top-level event
list can coexist in memory even though v6 removes their duplication **on
disk**. `_diff_list` serializes both candidate patch and replacement to choose
the shorter representation. The decoder reconstructs independent snapshot
trees; compressed input is not a bound on validation RSS.

**First exact experiment:** separate `model_dump`, pruning, delta comparison,
delta-size decisions, JSON encoding and physical write. Investigate skipping
the world's duplicated timeline **during assembly**, rather than creating
and discarding it later, while preserving `assemble_bundle`'s public decoded
layout. A serialized event representation reused in two places, or a writer
specific path, may avoid duplicate conversion. Prove number types, key order,
signed zero and byte output. A different JSON serializer is not automatically
compatible with the existing encoder.

**Save-cadence sizing:** if a full growing prefix costs `b × t` bytes or work
at turn `t`, saving every `K` turns totals approximately `b × H² / (2K)`.
This is conditional algebra, not a measured scaling fit: population, event
rates and field sizes vary. The existing JSON state/memory cadence and an
opt-in exact-checkpoint cadence are different costs. Current memory entry
JSON is already cached, but joining/writing the complete growing file still
costs its length. Exact checkpoints retain histories and validation/event
buffers, not merely the live native pool.

[`run_checkpoint.write_checkpoint`](../../src/chronicler/run_checkpoint.py)
already uses pickle protocol 5, optimized event/column reducers and **zlib
level 1**. Do not recommend those as new work. The documented native raw state
was about 310–330 bytes per living agent, free slots included, on that
workload: one million such agents would be roughly 310–330 MB for that
section alone, before Python history/events and runtime overhead. This is a
byte-size extrapolation, not a memory or time measurement. Writing also holds
raw sections, compressed sections and a joined output blob concurrently.

**Later format project:** segmented history/event journals plus periodic
full checkpoints could avoid rewriting complete prefixes. This preserves
simulation behavior only if replay restores private signals, aliases,
free-slot order, native queues and output history exactly. It changes the
checkpoint/storage contract and needs a versioned decoder, crash recovery,
atomic commit semantics and identity tests. Reducing cadence trades recovery
distance for time; disabling fsync silently is not an optimization with the
same durability contract. Parallel compression of independent sections is
another hypothesis for a single run on spare cores; it competes with seeds
for the same cores and can increase peak RAM, so it need not improve ensemble
throughput.

### 6. Validation input loading and peak memory

[`validate.run_oracles`](../../src/chronicler/validate.py) already loads seed
data once for its selected oracle set, and `validation_io.iter_bundles`
already parses bundles one at a time. Do not replace these with a cache of
all decoded bundles. Still worth testing:

- `_load_agent_events` and `_load_agent_deaths` each read the same Arrow
  event file. A shared table/projection can derive both while preserving
  row order, earliest-death semantics and the uncounted-event sentinel.
- `_compact_column` builds a Python list before packing null-free numeric
  values into `array('q')`/`array('d')`. A direct Arrow/NumPy-to-packed-array
  path could avoid the temporary boxed list. Test overflow, nulls, booleans,
  endian handling, NaNs and signed zero; keep fallback behavior.
- `load_seed_runs(selected_oracles=...)` still attempts graph/memory/needs
  reads in its body. An input plan can omit genuinely unused tables for
  focused development re-scoring. A full gate requiring all tables gains
  nothing from that omission.

Measure manifest hashing, JSON decode/restore, Arrow reads/conversion and
oracle compute separately. Preserve file verification and compare complete
reports, not just PASS. Changing the oracle method, sampling cadence, seed
count or required threshold is a scientific change, not a performance patch.

## Behavior-changing scale options

Existing `--agent-scale-mode fast` bounds candidate work and is deterministic
within its own mode. It is not byte-identical to exact mode; its old short
equivalence study is not qualification of the current systems at long
horizons. Re-run outcome, contact/kin structure and causal-oracle evaluations
before recommending it for a new use case. Current exact checkpoints persist
native options; the older scale report's legacy `state.json` limitation must
not be confused with exact checkpoint support.

Coarser spatial dynamics, sampled social contacts, less frequent decisions,
agent aggregation, changed update order, approximate reductions and GPU
mixed precision are model variants. They can change scaling more than a
micro-optimization, but must be explicit modes with scientific evidence.
An “improved” spatial index that returns every neighbor within radius 0.15
is **not automatically exact**: the current reference first restricts the
candidate set to a fixed 10 x 10 grid's 3 x 3 block. Both that support and
slot-ordered accumulation are part of its realized behavior.

The Python phases also intentionally publish signals with one-turn latency
and apply accumulators at specific barriers
([simulation.py](../../src/chronicler/simulation.py),
[turn_artifacts.py](../../src/chronicler/turn_artifacts.py)). Run independent
read-only work in parallel only where inputs are frozen and merge order is
fixed. Moving governance, economy, ecology, agent decisions or Phase 10 across
barriers can change the simulation even if every individual function is
unchanged.

## Reproducible measurement protocol

1. Reserve a quiet host period. Record CPU model/features, available cores,
   memory, OS, Python/packages, source tree/package digest, native extension
   digest/layout, build flags, all feature flags and output/checkpoint cadence.
   Separate AVX-512, AVX2/portable and aarch64 results; PR #53 did not time
   the other hardware. Exclude compilation and other gates from timing runs.
2. Use a current production-default profile, plus explicit feature-on profiles
   for scholarship, grain reserves and domestic credit. Test capacity-aware
   refugees in aggregate/shadow modes where applicable. Keep output and
   validation-sidecar settings fixed within each comparison. Do not turn
   systems off to make a candidate look faster.
3. Separate four measurements: cold process start-to-exit; warmed full run
   including final outputs; early/middle/late completed-turn intervals; and
   standalone save/load/validation. `turn_phase_profile`'s measured window
   ends at `on_turn`: final save/bundle work is outside it. First-turn marks
   include startup/setup when warm-up is zero; use them only as a cold-start
   diagnostic, not a pure first-tick number. Instrumented profiles have
   overhead, so uninstrumented paired results decide speed.
4. Start with fixed seeds 42, 7 and 1234; use the same source-specific worlds
   and starting populations in both arms. Suggested staged matrix: template
   8 x 4, procedural 48 x 10, and a wider 150 x 30 profile; agent targets near
   1k/20k/50k/100k subject to the per-region cap; horizons 100/300/1000. First
   screen one seed at modest scale, then expand only promising candidates.
   Record realized living/total civs, occupied regions and agent concentration.
   Holding the target alone fixed does not hold density fixed.
5. For isolated latency, one seed worker; sweep Rayon threads only on fresh
   runs. For ensemble throughput, sweep seed workers with one Rayon thread
   per worker, then a small two-dimensional worker/thread grid on a larger
   host. Pin OpenBLAS/OMP/MKL counts explicitly. `--parallel 1` now means one
   worker (`batch.parallel_workers`); the earlier bug is fixed. Checkpoint
   thread-identity checks mean changing thread settings on an existing exact
   resume is not a valid comparison.
6. Interleave base/head sequentially in alternating order for at least five
   pairs after warm-up; report each pair, median, spread and a paired ratio
   interval when enough runs exist. Do not run base/head simultaneously and
   call the resulting wall time an isolated latency measurement. Record
   process CPU (all threads), wall, peak RSS and file bytes. Use separate
   profiling runs for stacks/allocation counters; a speed claim needs a
   repeatable full-boundary benefit beyond observed noise.
7. Exact implementation candidates must pass the relevant reference tests
   and `turn_speed_identity` matrix, comparing every artifact with only the
   established generated timestamps normalized. Add a workload exposing the
   claimed axis (late horizon, crowded region, large living/historical civ
   set, fork or legacy Arrow table). Storage-format/output-policy projects
   separately prove restored state/retained rows and declare changed artifact
   bytes. Behavior-changing modes need the appropriate before/after gates
   and causal checks; deterministic output alone is insufficient.

### Existing tools and commands

`scripts/benchmark_headless.py` remains a useful frozen exactness benchmark,
but explicitly disables native agents and most modern systems. It cannot
stand in for current production throughput. Use
[`turn_phase_profile.py`](../../scripts/turn_phase_profile.py),
[`agent_scale_benchmark.py`](../../scripts/agent_scale_benchmark.py),
[`checkpoint_cost.py`](../../scripts/checkpoint_cost.py) and
[`checkpoint_identity.py`](../../scripts/checkpoint_identity.py) for the
boundaries they actually cover. None currently provides the whole matrix
and admission-control workflow above.

Commands to run **after** the host is available, with a matching fresh release
extension in the selected interpreter; paths below are new local outputs:

```sh
RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0 \
  python scripts/turn_phase_profile.py --target 43700 --regions 12 --civs 4 --seed 7 \
  --warmup 20 --turns 8 --no-instrument --out /tmp/scaling-52k-uninstrumented.json

RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0 \
  python scripts/turn_phase_profile.py --regions 48 --civs 10 --worldgen procedural \
  --seed 42 --warmup 200 --turns 100 --cli-arg=--validation-sidecar \
  --out /tmp/scaling-procedural-late-profile.json

RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0 \
  python scripts/checkpoint_cost.py --target 43700 --seed 7 --warmup 20 --repeat 5 \
  --out /tmp/scaling-checkpoint-52k.json
```

Repeat the same late-window case with `--no-instrument` for a timing result.
Use external process timing for imports/start-to-exit, not merely the profiler's
in-process `run_wall`. `checkpoint_cost.py` repeats writes/reads and additional
compression probes: its overall run time is not normal checkpoint cadence
overhead. The scaled harnesses change carrying capacities and starting
populations only for benchmarking; they do not qualify those worlds' balance.

No new instrumentation helper is proposed for this first pass. If the existing
tools cannot separate finalization or row-turn comparisons, add a small
benchmark-only probe after agreeing its boundary and receipt fields; keep
timers/counters out of simulation state, RNG paths and persisted outputs.

## Development workflow that makes the results useful

Maintain distinct quick correctness, current-default performance and full
scientific lanes. A focused reader-only optimization should re-score retained,
manifest-verified data; an exact tick optimization should use identity before
spending time on statistical gates. Keep full native release builds and
large validation gates out of performance measurement windows. Immutable
worktrees and source/native digests prevent stale extensions from answering
the wrong experiment.

On a small host, one gate/benchmark coordinator should admit jobs against CPU,
peak RAM and scratch-disk budgets. Independent seeds are the simplest parallel
unit; a sequential world turn has real causal barriers. More workers can
increase throughput until memory, I/O or scheduler contention reverses it.
Do not infer the optimum from core count alone. Existing workers already use
a default one-thread Rayon pool; BLAS caps and fresh checkpoint identities
must still be made explicit.

Retain per-stage receipts, individual timings, changed/unchanged artifact
hashes, failed experiments and peak-resource measurements outside commits.
Commit concise source-qualified reports. A small aggregate performance result
should name exactly which profile improved and what cost moved elsewhere;
one seed's median, a profiler's self time or a smaller output file is not an
end-to-end scaling claim.
