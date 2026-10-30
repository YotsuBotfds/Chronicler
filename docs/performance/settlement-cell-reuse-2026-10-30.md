# Settlement cell reuse candidate — 2026-10-30

This source-only child starts from exact `701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d`.
It changes only `extract_clusters` in the live settlement detector. Detection is
called by `run_settlement_tick` every 15 turns and during forced finalization.
The historical profile in [python-scale](python-scale.md) sampled settlement
detection at roughly 6% of a large-world window containing a detection turn.
That observation is motivation, not a timing measurement of this source.

## Change and exactness boundary

The first classification pass stores a shared `[count, component_id]` record
for each occupied cell and one reference to that record for each input row.
The density helper receives the same ordinary cell-to-integer count mapping;
its all-row denominator and the connected-component helper are unchanged.
The centroid pass reuses each record's component ID. It retains the original
row order, `0.0` accumulators and `+= x`, `+= y`, `+= 1` statements. It does not
sum by cell, convert coordinates, filter rows, clip lower-negative coordinates,
change the detection interval, retain state across calls or consume RNG.
The public `assign_cell`, `build_density_grid`, density and BFS helpers remain
byte-exact. Simulation call sites, schemas, native source and imports are exact.

No input validation or dtype conversion is added. Prospective parity checks
cover ordinary stable Python numeric rows, including Python floats widened
from float32 snapshot coordinates, ints and bools. NaN/Inf classification errors,
finite accumulation overflow, signed zero, subnormal coordinates, upper clamping
and lower-negative cells retain the original operations. Negative cells can
join a component through adjacency to an in-range cell; isolated negative cells
are not BFS seeds. Classification still completes before centroid addition.
Arbitrary stateful numeric callbacks or a sequence mutating between passes are
not qualified by this candidate: deleting a second call to `assign_cell` changes
its callback count by design. There is no broader numerical equivalence claim.

The existing settlement test file remains an exact byte prefix. The appended
oracle is the parent's whole `extract_clusters` body with only four local
helper imports added. Thirty-nine prospective pytest cases compare 21 exact
outputs (including centroid type and IEEE-754 bits), five assignment traces and
13 exception types/messages. Cases include interleaved connected cells, separate
and row-major components, 166/167-row density threshold boundaries, float32 grid
edges and classification-before-addition failure ordering. These tests are
UNRUN; static source inspection is not a pytest result.

## Memory and performance risk

On a 64-bit interpreter, the row list needs at least eight bytes per row for
references, plus its header and allocation slack (commonly up to roughly 12.5%
for an append-grown CPython list). A two-slot cell record adds its list header
and two references per occupied cell. The count dictionary passed to the density
helper is also temporarily live beside those records. Existing input tuples
and coordinate objects are reused. No measured allocation sizes are claimed.

For normal nonnegative coordinates there are at most 100 occupied cells.
Negative inputs can create one distinct cell per row, so the general bound is
O(N + C) additional storage with C up to N. The original no-dense path already
makes only one classification pass: this candidate adds work and memory there
without saving assignments. A favorable clustered microbenchmark alone cannot
qualify this tradeoff. The original implementation remains the baseline and
this candidate must be rejected or revised if the registered comparison fails.

## Proposed bounded comparison, not executed

Freeze the candidate, original oracle, input generator, interpreter/environment
and harness before a separate execution decision. Do not tune workloads or
repeat a failed comparison on the same source. Use no World, agent runtime,
network, child process, persistent fixture or native simulation. Loading and
execution must follow the separately reviewed runner's exact source scope.

Use four position counts: 1,000, 10,000, 100,000 and 250,000. The last is a
single-region stress case, not a claimed typical per-region population. At each
size use the same deterministic ordinary-float rows for both algorithms:

- One compact hub occupying four adjacent cells, all above the density threshold.
- Two interleaved separated hubs, with adjacent cells inside each component.
- Balanced occupancy of all 100 cells, producing no dense cells at these sizes.

Register the formula and its exact generated-input digests before timing. Check
all result keys, populations, cell sets, centroid types and bits first. Warm up
once at 1,000 rows only. Retain three paired timings per workload, alternating
baseline/candidate order by a fixed schedule. Record raw wall and process-CPU
values and paired ratios, rather than only a best run. Keep input construction,
comparison and result serialization outside the timed calls. Use a separate
single-pass allocation measurement on the same maximum-size workloads, report
baseline/candidate peak traced allocation and actual list/record sizes, and
retain both measurement methods and their overhead limits.

Each separately authorized process keeps the existing 110-second wall,
30-second CPU, 512-MiB address-space and one-CPU limits; joint logs/results must
fit 2 MiB. A deadline or resource refusal is incomplete, never a pass. Do not
increase caps or repeat measurements to chase a threshold. The allocation pass
must not be used as a performance timing sample.

Proposed acceptance requires exact parity everywhere; at least 10% lower median
CPU and wall at both 100,000 and 250,000 rows for each clustered workload; no
more than 5% median CPU or wall regression for either large no-dense workload;
and an explained peak-memory increase consistent with the row-reference model.
Also report all small-workload regressions. These are prospective criteria,
not earned results. Broader guarded settlement tests and existing columnar-path
contracts remain separate correctness gates; no full-simulation speed, native,
scientific, CP, efficacy or production qualification follows from a microbenchmark.

The earlier allocator/intake idea was not integrated: current701 has no
production constructor caller for either ledger. Wiring the held care-study
roles into CI intake would duplicate its custody/debit path without serving a
live owner. That investigation produced no product change.
