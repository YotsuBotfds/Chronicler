# Exact household decision journal: prospective experiment

Registered before implementation/timing on source `2dd47347`, native crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` (2026-10-28). This is an exact
implementation experiment. No behavior, population balance or default feature
change is proposed. Merchant-tax work remains separate.

## Mechanism and prior evidence

[`consolidate_household_migrations`](../../chronicler-agents/src/household.rs)
currently searches and retains whole decision vectors for each sorted spouse
pair and each dependent. For an approved pair it removes and appends the
trailing spouse/dependents, so later pairs must see earlier edits. An index of
the original list alone would be wrong. Rebellions and occupation switches
only lose entries in this phase.

The historical [PR #53 profile](turn-speed-2026-10b.md) measured approximately
7 ms for this phase at 52k agents, about 3% of its native tick. This is not a
current profile or a promise of a material ordinary-run gain. The target is
the quadratic decision-list work under concentrated migration, which can grow
while the population-wide dependent-index scan remains linear. A simple bucket
with P independent migrating leads and P non-migrating spouses performs
4P-squared migration-slot comparisons in its find/any/retain operations, before
final deduplication. This is an operation count, not a measured CPU timing.

The recent small-world Python profile is unsuitable for attributing native
household cost. It also does not support optimizing finance projections or
required model/Arrow imports. The existing exact drift SIMD/division kernel
and previously rejected cross-phase ID-map reuse are outside this experiment.

## Exact contract

Use a bucket-local append-only migration journal and a sparse slot lookup of
the first and last currently active entry. Removal invalidates that slot's
entries; a subsequent append establishes a new first/last entry. At the end,
emit only each slot's active last entry in journal order. Initial duplicates
therefore retain first-match behavior during processing and last-match
behavior at final deduplication. No unordered-map iteration emits decisions.

Track original rebellion membership and slots whose primary actions were
suppressed. Apply the two stable retain operations once at the end. Rebellion
checks in later households must observe earlier suppression immediately.

Preserve every spouse-pair/dependent order, lead choice, cancellation precedence,
mutable edit visible to later pairs, follower append (including repeats),
driver attribution, counter increment and untouched vector. Do not add a
persistent field, cache lifetime, RNG call, FP operation, enum, FFI method,
schema entry, compiler option or dependency. Retain the old consolidation
kernel explicitly as a test-only differential reference. Pool/ID/dependent
eligibility helpers stay unchanged in this first slice.

## Staged measurement and acceptance

1. Before timing, compare complete pending-decision vectors and all household
   counters against the reference. Include ordered/duplicate/conflicting
   migrations, rebellion/catastrophe cancellations, shared dependents, married
   minors, travelling/dead/recycled slots, stale ID maps, empty buckets and
   multi-bucket inputs. A repeated call is compared to a repeated reference
   call; consolidation itself is not assumed idempotent.
2. A bounded Rust phase replay measures both implementations with the same
   immutable pool/decisions. Start at 1k and 20k agents, then 100k only if useful.
   Use normal 1% and shock 25% migrating leads, spread and concentrated buckets,
   one and multiple dependents, and cancellation-heavy variants. Report initial
   and resulting vector lengths, spouse pairs, occupied regions, maximum bucket
   size, complete equality digest, phase CPU/wall and peak scratch allocation.
   Sparse-index build and final materialization belong inside the timed phase.
3. Once a fresh matching release wheel is available, measure uninstrumented
   full production runs at near 1k/20k/50k/100k agents and the unchanged default
   template/procedural cases. Fixed seeds are 42, 7 and 1234. Retain normal and
   documented migration-shock worlds; record realized migration counts and
   occupancy rather than inferring a shock from a label. Use five sequential
   interleaved base/head pairs, alternating which side runs first; one Rayon,
   OpenBLAS, OMP and MKL thread, fixed PYTHONHASHSEED. Profile separately.
4. Target a repeatable >=2x phase gain for large shock buckets and >=5% whole
   workload gain in at least one predeclared exposed workload. Ordinary cases
   must have no repeatable regression above 3%. Retain every pair and report
   variability; failing these thresholds rejects or narrows the optimization,
   rather than authorizing parameter/workload tuning. No ordinary-run speedup
   is implied by a shock-only win.
5. Run the full nine-case artifact identity matrix with independently frozen
   source/binary arms and the established timestamp normalization only. Add a
   migration-heavy exact continuation case comparing full native pool/event
   and checkpoint state. Relevant Rust reference tests must pass in optimized
   code as well as the normal build before a speed claim.
6. Only after 100k establishes time and memory budgets, consider 1M agents
   spread over at least 20 regions, with no region above 50k. Retain population,
   density and active-decision distributions. This is a separate admission
   step, not an authorized timing run on the currently shared host. The sparse
   journal must scale with bucket decisions/edits, not global pool capacity.

No new timing or fresh-build claim is made by this preregistration. Root
coordinates compiler/benchmark windows and freezes source, interpreter,
extension digest, crate tree, Cargo lock and CPU/thread environment for each
receipt. Frozen environments and shared target caches are never silently
replaced.

## Prospective full-boundary pilot fixture

Before its first exposure run, `scripts/household_shock_benchmark.py` freezes
the seed42,20k-target,12-template-region/4-civilization pilot,20 warm-up and
8 measured turns. It pairs actual native adults aged at least20 in ascending
ID order within ascending region order, inserts symmetric Marriage bonds
through the existing FFI, and records every chosen pair. Initial populations
follow the existing scaling harness and must stay below50k per region.

The origin is the largest initial population region, ties by region index;
its actual adjacent regions, in region-index order, are the neighbors. From
turn20 onward only native `SyncRegion.food_sufficiency` inputs are overridden:
origin0.05, neighbors1.5; other fields and regions stay as built. This is a
forced-condition performance fixture, not physical food spending, and does
not establish a balanced intervention. The cohort-control arm keeps the
same marriages without a food-input override. Default production runs and
the nine-case identity matrix remain unwrapped.

Keep both binary arms, chosen pairs, complete per-turn exposure records,
cancellations/zero exposures and the initial/realized population distribution.
The existing complete-turn timer includes the same lightweight exposure
collection in both arms; imports, warm-up and final exports are separately
available through process/run timings. The first pilot retains actual run
files for artifact comparison. Do not change seed, origin,food values, exposure
thresholds or the candidate after seeing its result without a new prospective
amendment. The >=5% exposed-whole-workload and <=3% ordinary-whole-workload
regression rules remain decisive; a fast isolated phase is insufficient.
