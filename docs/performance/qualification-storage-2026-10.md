# Qualification storage decisions, 2026-10-28

The shared workspace has a 32 GB filesystem. Qualification competes for disk
as well as its four-CPU budget: completed simulation parents retain exact
fork checkpoints while Rust integration tests link separate executables.
An earlier 8.3 GiB copied debug target reached the live gate's disk guard.
Its completed-target cleanup and retained evidence are documented in the
[Rust qualification](../integration/rust-qualification-d051-2026-10.md).

After those tests and all old-build checks finished, two additional unused
Cargo caches, `chronicler-build-base` and `chronicler-build-health`, were
removed. They contained no wheels. A process-reference preflight checked
commands, executable/cwd links, descriptors and mapped files; the active
`chronicler-build-receipts` target was excluded. The separate baseline/health
release wheels were hashed and retained, along with all installed environments,
source, qualification logs and receipts. Observed free-space recovery was
**3,975,774,208 bytes**. Concurrent parent growth makes this a workspace free
delta, not a precise accounting of only removed file bytes.

The external cleanup receipt is
`chronicler-next-evidence/unused-cargo-cache-cleanup-20261028.json`, SHA-256
`f6d16c7f0136472cd9cbd7fce2049978b91580c5cde5f7dc30f88db189a807df`.
The first preflight safely stopped because its own launcher quoted the cache
paths. The corrected scan excluded only those launcher command strings and
still checked their filesystem references. No removal preceded that correction.

The later [debug-info experiment](rust-debug-info-experiment-2026-10.md) passed
the complete unchanged 1,088-test crate with a fresh 1.03 GiB target and
verified assertions/overflow checks. That target is retained warm. The old
and new target artifact histories differ; no controlled percentage reduction
or compilation speedup follows from their sizes. The independently qualified
setting now applies to the standalone Rust CI test job.

The recovered template gates' live parent/fork data was not pruned or compressed.
A read-only inventory identified final state/archive/language and memory JSON
outside required manifest inputs as candidates for later lossless archival.
Such archival would need raw/compressed hashes, decoded verification and a
real restoration check before removing duplicate raw files. All validation
sidecars, including extra ledgers, would remain. No such archival has occurred.

Run a complete procedural arm only after measuring available capacity, then
budget the next arm from actual retained size and peak checkpoint/fork/
validation requirements plus the disk floor. Nominal cohort-size estimates
alone do not establish that both procedural arms fit. A guarded stop remains
an interrupted run, never a pass.
