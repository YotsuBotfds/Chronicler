# Native region ingress — source only, 2026-10-30

This child of `ef716e7f0d5ba0fa1e4c53774389201bcc23720d` corrects direct
AgentSimulator inputs that could disagree with the simulator's declared region
universe. It retains that parent's context-reader early completion and care
source binding. All compilation, tests, native execution and CI for this child
are UNRUN at source freeze. This is an input-correctness change, not a measured
optimization or a scientific qualification.

## The inconsistency and admission contract

The constructor stored a `usize` region count, while the first Arrow batch could
provide a different number of rows or sparse/reordered region IDs. Initialization
used the batch, but regional population export used the constructor count. A
constructor declaring one region could therefore ingest two populated rows and
silently omit the second region from that export. Tick partitions also narrow
region counts to uint16.

The Python constructor now rejects counts above 65535 before reserve allocation.
Zero remains legal: construction, empty getters/checkpoints and a typed empty
first batch retain their existing behavior. The existing Rust `new -> Self`
entry remains available, with a programmer-error assertion before allocation;
the fallible PyO3 constructor reports ValueError for an out-of-range count. The
upper boundary is checked without allocating a maximum-sized pool in tests.

On first ingestion, the row count must equal the declared count and the UInt16
region_id values must be non-null and exactly 0..count-1 in row order. This
matches the established identity rule: a region's ID is its index. Arrow column
order stays unrestricted because required columns are looked up by name.

The new shape/ID checks, existing required-column checks and fallible adjacency
decoding complete before any simulator mutation, including snapshot-cache
invalidation or contested-region assignment. The existing later row-count
refusal also moves before mutation. Later updates retain their existing
positional interpretation of region_id; this slice adds no later row-ID gate.
Other runtime failures, such as resource exhaustion during valid initialization,
are not claimed to be transactional.

## Compatibility audit and prospective tests

A source-only census hash-checked and parsed 624 current nonhistorical Python
files. It traced 55 direct constructors, 70 setters including ecology-only
calls, and indirect simulator factories. No legitimate partial, mismatched,
sparse or reordered first AgentSimulator batch was found. Production uses
len(world.regions) and the same dense builder. Existing column-reordering and
constructor-only getter/checkpoint calls remain supported. No existing zero
caller was found; absence of a caller was not used to remove that valid API.

Six Rust tests cover the admitted zero/exact-upper domain, rejected counts before
allocation, empty initialization, first shape/ID refusals with complete encoded
checkpoint and held-snapshot preservation, subsequent shape refusal, missing
required columns, and successful same-seed recovery after refusal. The existing
Rust constructor callers and care tests remain unchanged.

Six native Python functions add 22 prospective cases: zero/empty, oversized
constructors, six first-batch faults with cold/warm snapshot caches, valid dense
33-region input and neighbor 32 with either column order, later count failures,
and preserved later positional-ID behavior. Refusals compare complete native
checkpoint bytes/schema and cache state; recovery is compared with a fresh
same-seed simulator. These tests use existing owners and are excluded from the
offline selection as before. No World or tick is needed by the new cases.

The original constructor field initialization, native persistent field ledger,
checkpoint/schema getters, context kernels, RNG operations and all care phase
bodies stay exact. Only the current whole-FFI care-test SHA is deliberately
rebound; all other nine current witnesses, ten care marker blocks, codec,
mechanics and historical native09ec SOURCE_BINDINGS stay unchanged. The old
ef716/f2c517 source remains preserved in ancestry. Source review does not prove
compiled ABI or checkpoint identity; those remain fresh-native test gates.

## Scope and next ownership slice

No dependency, model coefficient, default, source owner, offline chunk, workflow,
population setting or scientific gate changes. Zero through 65535 is an input
representation domain, not a practical memory/population capacity claim.

The distinct 254-record civilization allocation gap is not fixed here. A later
slice must define admission before secession/restoration/new-polity mutation.
Staging should merge this child in place of a redundant ef716 donor. When also
merging the separate needs-decode child, retain both independently reviewed
current bridge and FFI witness hashes rather than replacing the whole care test
with one donor's copy.
