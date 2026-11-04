# Settlement cell reuse: measured kernel result — 2026-10-30

Candidate `8aeea77a33a09be0cb06a2ca8a73f26de03d0424`, a child of exact
`701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d`, passed 95 focused settlement
module tests and the separately registered extracted-kernel benchmark002.
The large clustered workloads met their CPU and wall gates. Small no-dense
workloads regressed, and all three 250,000-row workloads used about 2 MB more
peak traced Python allocation. This documentation child changes no product or
test bytes. Its first standard CI remains a separate publication gate.

The historical profile in [python-scale](python-scale.md) sampled settlement
detection at roughly 6% of a large-world window containing a detection turn.
That observation motivated this work; it does not establish this candidate's
share of runtime or a full-simulation speedup.

## Change and correctness boundary

Only `extract_clusters` changes in the detector. It is called by
`run_settlement_tick` every 15 turns and during forced finalization. The first
classification pass stores a shared `[count, component_id]` record for each
occupied cell and a reference to that record for each input row. Density still
receives the same ordinary cell-to-integer count mapping. The all-row denominator
and connected-component helper are unchanged. The centroid pass reuses the
record's component ID while retaining original row order, `0.0` accumulators and
`+= x`, `+= y`, `+= 1`. It does not sum by cell, convert coordinates, filter rows,
clip lower-negative coordinates, change the detection interval, retain state
across calls or consume RNG. Public classification, density and BFS helper
bodies, call sites, schemas, native source, dependencies and imports stay exact.

No input validation or dtype conversion is added. The 39 new cases cover stable
ordinary Python numeric rows, including Python floats widened from float32
snapshot coordinates, ints and bools. They compare 21 exact outputs, including
centroid types and IEEE-754 bits, five assignment traces and 13 exception
cases. Cases include interleaved cells, separate and row-major components,
166/167-row density thresholds, float32 grid edges, signed zero, subnormals,
upper clamping, lower-negative cells, NaN/Inf classification errors, finite
accumulation overflow and classification-before-addition ordering. Negative
cells can join an in-range component through adjacency; isolated negative cells
are not BFS seeds. Classification still completes before centroid addition.

The test file retains its entire original 56-case prefix. Its appended oracle
preserves the parent's whole algorithm with only local imports of four unchanged
helpers. One actual focused run imported the real candidate module under the
existing `python_oracle_guard`: **95 passed (56 old + 39 new)**, guard PASS,
zero native modules, zero runtime-factory calls and zero blocked I/O. Pytest
reported 0.31 seconds; this is not an external process-wall measurement. The
result is a focused module gate, not whole-suite or simulation qualification.

Arbitrary stateful numeric callbacks or a sequence mutating between passes are
outside this equivalence boundary: removing a second call to `assign_cell`
changes callback counts by design. No universal numerical equivalence is claimed.

## Registered measurement and preserved first incomplete attempt

Benchmark001 exited 1 at its first nonpositive-clock precondition. It saved
zero timing samples and zero complete pairs; the raw interval was not saved,
so which clock and the cause remain **UNKNOWN**. It reached all 12 untimed
parity checks and three warmup pairs before that point, but produced no
performance verdict. Its harness, evidence and root POST remain preserved;
it was not rerun. Advertised 1-ns clock resolution does not explain the failure.

Benchmark002 is a distinct, preregistered fixed-batch protocol on the same
source, oracle, 12 input digests, workload formulas, acceptance thresholds and
resource caps. Its one actual process exited 0. Root reconciled every saved raw
clock endpoint/delta/per-call value, chronological pair order, all 12 medians
and paired ratios, and all three allocation models without replaying kernels.

The loader extracts exactly five unchanged-or-reviewed function bodies
(`assign_cell`, `build_density_grid`, `find_dense_cells`,
`find_connected_components`, `extract_clusters`), three constants and the
original annotations future flag from each pinned full source file. This is
**extracted Python kernel timing and allocation**, not an ordinary module-load,
World, native, scientific or simulation-throughput benchmark.

The three deterministic built-in-float distributions are a compact four-cell
hub, two interleaved separated hubs, and balanced occupancy of all 100 cells
with no dense cells. Sizes are 1,000, 10,000, 100,000 and 250,000 positions;
250,000 is a single-region stress case, not an asserted typical population.
Input formulas and binary64 digests were registered before timing. All 12
untimed exact-parity checks and three extra 1,000-row warmup pairs precede the
measurements. Normal GC settings are recorded. Construction, input hashes,
final-output comparison and serialization remain outside timers.

There are three fixed alternating pairs per dataset: **36 pairs, 72 validated
samples and 2,016 timed kernel calls**, with 18 pairs in either order. Fixed
batches are 100 calls at 1,000 rows, 10 at 10,000, and one direct call at both
large sizes. Small per-call measurements include loop/range, lookup, assignment
and intermediate result-release overhead; there is no calibrated subtraction.
Prior-sample result release is outside timers. All four raw clock readings,
batch totals and per-call values are flushed before positivity/parity checks.
Raw rows alone qualify nothing. Both algorithms use identical schedules; no
adaptive calibration, retry, threshold tuning or best-run selection occurred.

## Large-workload results

Ratios are candidate median divided by legacy median; lower is faster. These
six rows use direct single calls, with three measurements per role. Registered
acceptance required CPU **and** wall ratios <=0.90 for each clustered large
workload and <=1.05 for each large no-dense workload. All six met both gates.

| Workload | Positions | CPU ratio | Wall ratio |
|---|---:|---:|---:|
| Compact four-cell hub | 100,000 | 0.691397 | 0.626605 |
| Compact four-cell hub | 250,000 | 0.639421 | 0.658000 |
| Two interleaved hubs | 100,000 | 0.600000 | 0.643837 |
| Two interleaved hubs | 250,000 | 0.799570 | 0.805373 |
| Balanced, no dense cells | 100,000 | 0.833368 | 0.948601 |
| Balanced, no dense cells | 250,000 | 0.868730 | 0.894348 |

All small-case regressions are explicit: balanced/no-dense at 1,000 rows had
CPU ratio **1.000320 (+0.032036%)** and wall ratio **1.094455 (+9.445527%)**;
at 10,000 rows its wall ratio was **1.047349 (+4.734864%)**, while CPU ratio
was 0.999994 (a 0.000629% decrease). No other small CPU or wall ratio exceeded
1. Small cases were reportable costs, not independent rejection gates.

## Allocation cost and general storage risk

One separate call to each unmodified kernel on each maximum-size
workload measured Python allocations using `tracemalloc` depth 1. These six
allocation calls were not timing samples. At 250,000 rows:

| Workload | Additional peak traced Python bytes | Registered model upper bound |
|---|---:|---:|
| Compact four-cell hub | 2,054,672 | 2,122,008 |
| Two interleaved hubs | 2,056,816 | 2,122,680 |
| Balanced, no dense cells | 2,059,548 | 2,142,312 |

All three deltas fit the unchanged conservative model: append-shaped row-list
bytes + two-slot-record-list bytes + three cell-dictionary sizes +65,536 bytes.
Equivalent-container `sizeof` samples explain shape; they are not observations
of live candidate locals. Existing input tuples/coordinates are reused. These
are incremental **traced Python allocation peaks, not RSS**, native allocation
or process-wide memory. The result does not establish a memory benefit.

The row-reference list adds O(N) storage and cell records add O(C). Ordinary
nonnegative coordinates occupy at most 100 cells; arbitrary negative inputs
can make C approach N, so the general additional-storage bound is O(N+C).
The legacy no-dense path already classifies only once. The candidate adds work
and memory there without avoiding a second classification pass; the measured
small regressions remain relevant even though the large gates passed.

## Limits and evidence

The one benchmark process used CPython 3.13.5 and one CPU, with unchanged
110-second outer wall/internal remaining-wall alarm, 30-second CPU,
512-MiB address-space, no-core and 2-MiB joint-output caps. Saved elapsed wall
**before result writing** was 10.576361548 seconds. External total wall,
process CPU and RSS are unknown. A single fixed synthetic comparison is not a
confidence interval, broad workload census or guarantee on other interpreters.
The harness checked full output signatures before timing and after final
results; those signatures were not retained in the numerical report. The
separate 95-test actual-module result supplies additional correctness evidence.

Evidence remains outside Git; only this relevant summary is committed:

- Focused95 root POST: SHA256 `5b2f211beb56bc14814935ecf0f8943ab93dfbf71e8840182346c0b5fb874268`.
- First incomplete001 root POST: SHA256 `d01321fdb4f84d21171dba75a8967c228f492efb6c8bcf6676696dc088a89004`.
- Benchmark002 result: SHA256 `0d28efa41cfae1f3182c2be4df4e1742f3996224f5e7a5e47fd98d514872ecd8`.
- Root numerical qualification: SHA256 `c7d84c3dcff9cda570609e62c0b33b6bd44d70b797a710525b63683add47b918`.

No whole-module throughput, World, full simulation, native behavior, global RNG,
scientific validity, CP, efficacy or production qualification follows from this
kernel result. Standard CI on the published branch remains a separate gate.
The allocator/intake idea was not integrated: current701 had no production
constructor caller for either ledger, so it produced no extra dormant layer.
