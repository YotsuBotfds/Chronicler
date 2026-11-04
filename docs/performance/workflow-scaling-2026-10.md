# Workflow and wall-clock scaling, 2026-10-28

The first priority is to stop spending the same scarce CPU budget on repeated
builds and competing qualification jobs. Then profile the simulation by the
size dimension that is actually growing. A faster dense-agent tick does not
by itself make long histories, many civilizations or multi-seed gates cheap.

This audit starts from integration `23f6136f`, with native build evidence for
base `cb9fe70c`. It adds the automatic worker-budget change described below.
Everything else is a proposal: no CI coverage, gate criteria, scientific sample
size, checkpoint identity requirement or cache acceptance rule changes here.

## Evidence and limits

| Classification | Observation | Implication |
| --- | --- | --- |
| Measured in this session | Linux cgroup `cpu.max` is `400000 100000`: four CPU equivalents. `os.cpu_count()`, `os.process_cpu_count()` and affinity each expose five CPUs. Memory quota is 16 GiB. | CPU visibility alone overestimates sustained CPU capacity. |
| Measured in this session | `base-source.json` records Python 3.13.5, Rust/Cargo 1.99.1, `build_jobs=2`, exact Rust source hashes and base `cb9fe70c`. `base-release-build.log` reports **7m 07s** for the release compile. | A cold optimized build is material. This is one observed build under shared load, not a stable build-time benchmark. |
| Measured in this session | The built wheel has SHA-256 `6cfa32ee...7b5cfc`; installed extension `43243cb0...a6afd5`. `base-extension.json` verifies the compiled module and all three native simulator classes. | There is an actual source-to-binary receipt; a successful import alone would be weaker evidence. |
| Observed failure | The first Cargo test attempt ended with `unable to find library -lpython3.13`, retained as `base-cargo-test-first-link-failure.log`. | Extension loading and executable-test linkage need separate preflights. An isolated tooling library-path fix subsequently let the unchanged source pass all 1,076 Rust tests (2 ignored); no repository or system-library changes were needed. |
| Observed cache sizes during that attempt | Release target about 382 MiB, partially built debug target about 1.3 GiB, wheel directory about 3.7 MiB. | Transferring the wheel is much smaller than transferring all intermediates. Cache upload/restore time has not been measured. |
| Source inspection | CI has separate no-Rust, native and viewer jobs. The native job runs release build, the whole native Python suite, then debug Cargo tests. Cargo and Python dependency caches are absent; viewer already has npm caching. | Optimize the existing critical path before adding more matrices. |
| Historical, not remeasured | [Turn speed](turn-speed-2026-10.md) reports large-agent drift at 51% of the turn after PR #44; [Rust scale](rust-agent-scale.md) distinguishes exact and opt-in fast behavior. | These identify profiling candidates, not the current head's measured bottlenecks. |
| Historical, not remeasured | [Checkpoint costs](../integration/checkpoint-continuation.md#7-cost) include roughly 0.42 s write / 0.45 s read at its 52k case; serialization and compression dominate the write. | Very frequent checkpoints can consume a meaningful fraction of a turn budget. Do not extrapolate these timings to the current head without measuring. |

The local native evidence lives outside Git under
`/workspace/chronicler-dev-evidence/native`. Logs are not copied into this
document as permanent fixtures. Subsequent repaired builds/tests need their
own completion receipts; the failed attempt above is not their result.

## Implemented: automatic worker counts follow the available budget

Previously a bare batch `--parallel` used visible CPU count minus one, and
the gate runner's omitted `--parallel` meant **12 workers** regardless of host.
The shared `chronicler.cpu_budget.automatic_workers` now takes the tightest
available bound from visible/process CPUs, process affinity and conventional
Linux cgroup v2/v1 CPU quotas, including ancestors named by `/proc/self/cgroup`.
It rounds fractional quotas down, reserves one CPU when more than one is
available, and always permits at least one worker. Missing, unreadable,
unsupported or malformed probes leave the remaining valid limits in force;
with no usable limits the fallback is one worker. Nonstandard cgroup mount
locations are not discovered dynamically.

Both a bare batch `--parallel` (and Batch Lab's automatic mode) and an omitted
gate-runner `--parallel` use it. On the observed host the automatic count is
**three**. Explicit positive counts remain exact, including `--parallel 1`
and `--parallel 12`; ordinary batches without `--parallel` remain sequential.
The helper changes no thread environment, seed, simulation or validation rule.
The optional `batch.parallel_workers(..., cpu_count=N)` caller-supplied budget
override is retained for compatibility.

One reserve CPU is a useful default, not admission control: independent builds,
pytest processes, viewers and other agents can still oversubscribe the host.
An explicit count also does not promise that the host can sustain it.

## First workstream: build once, identify it, use it repeatedly

1. **Preflight Python linkage before cold builds.** Check the selected
   interpreter's development/linker configuration for executable Cargo tests,
   not just extension loading. A tiny PyO3-linked executable/test built with
   the same interpreter selectors catches the observed missing-libpython
   problem early. This preflight should not install guessed headers or change
   Python midway through a qualification run.
2. **Keep dependency artifacts warm across development iterations.** Preserve
   Cargo registry/git caches and profile-specific target artifacts. Release
   and debug test builds differ in profile, dev dependencies and PyO3 features:
   maturin enables `pyo3/extension-module`, ordinary Cargo tests do not. A
   release wheel is not a debug test cache or a substitute for Cargo tests.
3. **Make the reusable wheel a named output of one build.** Retain wheel hash,
   installed-module hash and path, native source/build digest, compiler,
   Python ABI, target, maturin version, features and flags. Install that same
   identified wheel into baseline/head Python environments when their Rust
   input trees match. A Python-only or documentation-only change does not
   require recompiling unchanged Rust; record the new tested repository head
   separately from the native build's source identity.
4. **Always ask Cargo/maturin to validate a restored cache.** A cache key should
   include OS/architecture, toolchain, Python ABI, lockfile, features and
   relevant flags; dependency restore keys may be broader, but the normal
   locked build must still run. Source/binary receipts, not a cache hit or
   repository SHA alone, establish what was tested. Measure restore/save cost
   before caching the entire multi-gigabyte target tree. Consider `sccache`
   only after measuring real hit rates on this LTO/PyO3 workload.

The release profile currently uses `opt-level=3`, `codegen-units=1`, LTO.
Keep that qualified profile for performance and final native evidence. A
separate developer profile with cheaper codegen is an experiment that may
shorten edits; it must not silently supply a benchmark or scientific gate's
binary. First time cold builds, warm no-op builds and a one-file Rust edit
under both profiles. There is no measured speedup for such a profile here.

Locally, serialize writes to a shared target directory or isolate targets by
profile/toolchain and immutable source snapshot. Multiple agents invoking Cargo
against the same target can wait on its lock and still compete elsewhere;
copying entire caches into every worktree can instead repeat expensive work.

## Second workstream: schedule qualification along its dependencies

The existing CI wall path has the form, ignoring setup overhead:

```text
max(no-Rust tests,
    release build + native Python tests + debug build + Rust tests,
    viewer install + tests + lint + build)
```

The three existing jobs already overlap on separate CI runners. On the local
four-CPU host they share one quota, so extra jobs do not create extra cores.
For local development, use one agreed CPU budget: a three-worker seed batch
with one-thread native workers leaves little room for a two-job build and a
second whole pytest suite. Run focused feedback during a build; avoid starting
two scientific batches or a cold debug build just to keep every agent busy.

Proposed sequence for each candidate:

| Stage | Work | Evidence boundary |
| --- | --- | --- |
| Edit feedback | A reproducer and the affected subsystem tests; cheap Python/viewer checks can overlap build work within the shared budget. | Fails early; does not qualify the whole candidate. |
| Integration candidate | Freeze source snapshot; identify/reuse or build its correct native binary; run complete required Python/native/Rust/viewer lanes once for that head. | Changes after this snapshot invalidate affected lanes. Retain receipts for completed independent lanes. |
| Behavior qualification | Run the required template/procedural before/after cohort, determinism and applicable ablations against the frozen candidate. | Focused tests or matching selected outputs cannot replace this gate. |
| Publication check | Confirm no source movement, exact head status and retained evidence. | Documentation-only follow-up may retain binary provenance while updating tested-head bookkeeping. |

A proposal for CI is to split standalone Rust tests from native Python tests.
With independent runners and cached dependencies the mathematical path becomes
approximately `max(no-Rust, release+native Python, debug+Rust, viewer)`, plus
setup/artifact overhead. This is a scheduling opportunity, not a measured
reduction; costs and available runner capacity must be measured first. Another
option is one identified release-wheel build feeding native test shards.
Partition coverage explicitly, merge complete results, and verify the module
hash in every shard; repeated release builds per shard defeat the purpose.
No matrix, path-based skipping or coverage change is implemented here.

The bounded offline runner has **18 chunks**, each with a **110-second** limit,
fresh pytest process and guard receipt. Keep that limit and all guard checks.
Use its receipt's per-chunk seconds to rebalance or add chunks with headroom;
do not increase the limit when a shared host is overloaded. A missing or timed
out receipt remains incomplete evidence. Parallel chunk execution is only a
proposal and needs independent guard/temp directories and sufficient CPU/RAM;
the bounded selection also remains distinct from the complete CI suites.

## Third workstream: reuse simulation evidence without mixing cohorts

There are three separate reuse problems:

- **Re-score a complete immutable batch.** Existing `chronicler.validate` can
  read its manifest-verified inputs again without rerunning simulation. This
  is useful after validator/report changes. Record both producing simulation
  identity and scoring-tool identity/method versions; comparing old and new
  method versions may require a rebaseline, not a claim of unchanged behavior.
- **Resume an interrupted run of the same source.** Existing exact checkpoints
  verify source/package digest, native bytes/state layouts, interpreter,
  packages, thread environment and section digests. Use those checks. A raw
  `state.json` or `--resume-allow-mismatch` is not exact evidence, and a
  checkpoint from before a simulation-code edit cannot qualify the edit's
  unexecuted prefix. A changed whole-package digest intentionally refuses it.
- **Reuse completed seeds of an interrupted batch.** This needs new tooling.
  Today a batch directory must be new/empty and a non-complete manifest is
  rejected. Do not bypass those protections or concatenate seed directories
  by hand. A future resume command should lock a fresh destination, verify
  each completed seed's producing identity/config/horizon/input hashes, run
  only missing or invalid seeds, and atomically publish a new complete
  manifest with explicit lineage. Requested and effective feature defaults
  both need resolving before cross-head cache acceptance; `None` is not proof
  of the same default in two source trees.

For ablations, the present manifest ties arms to the exact plain manifest,
fork design, seed cohort and kept files. Checkpoints are deleted after a seed's
forks succeed. A resumable-arm design should retain/release checkpoints only
after verified per-fork completion receipts are durable, and recheck the exact
arm/window/start/source identity before skipping a fork. It must preserve the
pre-registered sampling design. It is not implemented here.

For storage, keep manifests, required bundles, Arrow validation inputs, decision
reports and binary/source receipts together. `batch_manifest.VALIDATION_INPUT_FILES`
defines what the validator reads; state JSON and memory streams may be pruned
only when those outputs are no longer needed for replay, forensics or byte
identity. Retain failures and a small inspection cohort. Historical procedural
disk/ablation costs are documented in [Development](../DEVELOPMENT.md) and
[procedural gates](../integration/procedural-gates.md); measure the current
configuration before choosing compression or retention. Compression before
hashing/publishing is different from mutating a manifest-covered file later.

## Simulation scaling: distinguish agents, regions, turns and seeds

Let `A` be agents, `R` regions, `T` turns and `S` seeds. Civilization count and
social/spatial concentration are additional inputs, not constants hidden by
`A`. A useful work model is `sum(seed,turn) CPU(A,R,civs,history)` plus generation,
serialization, validation and I/O. Batch wall time is bounded below by total
CPU work divided by available CPUs, and by its longest dependency chain. That
is a lower bound, not a prediction of linear scaling.

| Axis | What to measure | Optimization direction and constraint |
| --- | --- | --- |
| More agents in the same regions | Exact-mode neighborhood comparisons, candidates for marriage, knowledge/relationship work, bridge exports; count occupancy and the densest cells, not only mean agents. | Reprofile drift first using the existing scale/phase tools. Runtime SIMD dispatch or fewer repeated exports are candidates; preserve floating-point order, candidate sets and native state/event hashes for exact mode. |
| More regions at fixed agents | Empty-region scans, topology/routes, per-region bridge construction, governance and civ-pair work; record civ count separately. | Sparse active-region data or safely invalidated topology caches may help. More regions can lower pair density while increasing Python/graph overhead; it is not automatically slower or faster. |
| More turns | History/event growth, checkpoint encode/read, bundle assembly, RSS, sidecar bytes and final validator load. | Profile early/middle/late turns. Incremental storage and bounded views may beat another tick micro-optimization. Preserve old history and checkpoint continuation; do not prune evidence needed by readers. |
| More seeds | Seeds/hour, sum of process CPU, worker utilization, memory peak, artifact throughput and slow-tail seeds. | Parallelize independent seeds before increasing per-seed Rayon threads at small worlds. Choose worker count by both CPU and measured peak memory. More seeds multiply validation and artifact work as well as turns. |
| More civilizations | Diplomatic/intelligence pair counts, polity records including dead ones, city/war systems and native ID headroom. | All-pairs work and persistent identities need separate measurement. Native caps (254 civilization records, uint16 region IDs) are contracts, not performance targets. |

The opt-in `--agent-scale-mode fast` already bounds several dense-agent scans,
but can change outcomes; it is a separate configuration to qualify rather
than an exact optimization or silent gate setting. Increasing region count
to dilute density also changes geography and behavior. Prefer published scale
profiles so those tradeoffs are explicit.

For a benchmark matrix, start with: fixed 12-region agent-density sweeps;
fixed-agent region sweeps; a fixed world at 50/200/500 turns; then the same
seed cohort at one, two and three workers. Vary one dimension first. Record
wall time, process CPU, peak RSS, output/checkpoint bytes, late-turn latency,
compiler/native identity and thread settings, with alternating paired runs
on a quiet host. Existing `agent_scale_benchmark.py`, `turn_phase_profile.py`,
`checkpoint_cost.py` and identity scripts provide most of the machinery.

Batch initialization already defaults Rayon to one per worker, but inherits
an explicit user choice and does not globally cap BLAS. For repeatable scaling
experiments, set thread counts deliberately before import and record them;
changing them after writing exact checkpoints can make continuation fail its
identity check. Automatic process budgeting intentionally does not override
those settings.

## Order of delivery and acceptance

1. **Now:** the automatic worker helper; collect failed-build/preflight and
   existing lane receipts in one candidate manifest. Stop duplicate builds
   of matching native input trees. This is low cost and preserves coverage.
2. **Next:** benchmark cold/warm Cargo builds and cache transfer; add a
   documented release-wheel receipt/cache workflow and evaluate CI separation
   of Rust/native Python work. Require measured queue-to-result wall time and
   unchanged coverage before adopting it.
3. **Then:** add manifest-verified seed/fork resumption and independent scorer
   identity. Prove rejection of changed source/config, missing/altered inputs,
   duplicate seeds, incomplete horizons and changed ablation design.
4. **Performance work:** run the scale matrix and pick the largest measured
   cost per product workload. Exact changes need appropriate byte/RNG/pool
   identity checks; intentional approximations need their own scientific and
   narrative acceptance criteria. No numerical speedup is promised here.

## Verification of the worker change

The focused batch/gate/procedural/Batch Lab suites cover explicit counts,
automatic forwarding, quota versus affinity, fractional limits, v1/v2 parent
limits and malformed/unreadable/unsupported fallbacks. They do not execute a
scientific full gate. The helper tests are in the already-selected batch test
file, so the offline runner gains no new chunk or longer timeout.

A separate actual-process comparison runs two 30-turn aggregate seeds, 42 and
43, sequentially and through a bare `--parallel`. Both child processes use a
three-CPU affinity and the same explicit thread/hash environment; the new
budget therefore launches two workers. **19 files matched with zero output
differences**, excluding only the bundle generation timestamp. Raw bundle
hashes in the manifests consequently differ and remain recorded as written.
The execution manifest intentionally records different parallel requests,
timestamps and native import bookkeeping; source changes also change source
digests. Matching simulation output does not mean these provenance records
should be erased or called byte-identical.

The focused command passed **95 tests**:

```sh
PYTHONPATH=src python -m pytest -q tests/test_batch.py tests/test_m53b_run_validation.py tests/test_procedural_gates.py tests/test_batch_websocket.py
```

The batch selection also passed separately under the existing offline guard:
**28 tests**, guard **PASS**, no native modules loaded, no blocked I/O attempts.
This took 5.52 seconds locally; it is a focused guard check, not a complete
18-chunk oracle-lane run or a wall-time improvement measurement.
