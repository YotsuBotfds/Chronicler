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

## Fixed-parent lossless archive probe

After all 200 parents in each template source were complete, a separate
copy-only probe selected the original seed 42 from each. It compressed only
`state.json`, the historiography/language JSON and four top-level memory JSON
files. None was a manifest validation input. It verified the original batch's
required input hashes, created deterministic gzip copies, restored all fourteen
files to new real paths and checked their exact raw sizes and SHA-256 hashes.
Inventories of **every** original file in both parent directories and both
batch manifests matched before/after. No original, sidecar or checkpoint was
removed or rewritten; active gates kept their existing protocol.

| One completed seed-42 parent | Raw selected bytes | Gzip bytes | Actual restored files |
| --- | ---: | ---: | ---: |
| Baseline | 5,080,980 | 365,796 | 7, all exact |
| Candidate | 4,965,943 | 354,819 | 7, all exact |

These two fixtures demonstrate lossless restoration and compression opportunity,
not the compression ratio of all 400 parents, net disk recovery or a faster
simulation. The probe retained originals, gzip copies and restored copies, so
it recovered no space. Its external script and receipt remain under
`chronicler-next-evidence/probe_lossless_parent_archive.py` and
`chronicler-archive-probe-20261028/receipt.json`; receipt SHA-256 is
`c0e7122e1ebfc647b0f5dabd2aeec6ccc8ae008c5ece134b130646e59aec4b89`.

Any cohort-wide archival/removal still waits for complete fork execution and
official validation. It must retain every validation sidecar, including
unhashed resource/economy ledgers, and preserve a hash-linked restoration
index. The next procedural arm must be budgeted from the **actual** retained
result and peak requirements, not an extrapolation from these two parents.

## Completed qualification scratch cleanup

After all three b257 lanes passed and their children exited, their three pytest
basetemp directories were removed. These held temporary test fixtures, not the
long-gate parents, forks or checkpoints. Hash inventories verified that all
85 retained qualification records were unchanged, including logs, JUnit,
guards, requests, copied supervisors and source/runtime inventories. Live
current-user process references were checked; privileged system services and
verified exited zombies were explicitly outside that inspection scope.

The observed free-space delta was 989,130,752 bytes under concurrent gate
output. External preflight/result records remain in
`chronicler-next-evidence/passed-b257-scratch-cleanup/`; result SHA-256 is
`2c601fdc55a09a5c9d0b22ee084b219e7a27cbb0009d30c00bafb9ca2fa9f698`.
The archive probe's originals, compressed copies and restored copies remain.
