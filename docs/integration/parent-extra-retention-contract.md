# Prospective parent-extra retention and restoration contract

Design only, from integration `2f9d618b70f3304c02dcaeef12996b4a99e074c0`
on 2026-10-28. No retirement/deletion API, original-path restore API, cohort
archive, or storage cleanup is implemented or executed by this document.
The existing [copy-only archive tool](parent-extra-archive.md) remains unchanged:
its actual restore copies and source originals both occupy storage.

## Eligibility begins after both official gates finish

For the recovered scholarship template comparison, both arms must finish their
unchanged complete 200-seed / 500-turn protocol, all 1,600 needs/kin forks per
source, strict validation and final source/native checks. A scientific gate failure
is retained as a failure and may still be eligible for byte-preserving storage
work. An interrupted/unknown execution does not meet this completion contract.

The admission packet must retain and hash these original artifacts:

| Artifact | Required evidence |
| --- | --- |
| Candidate `candidate-template/status.json` | `stage=complete`; `status=complete_pass` or `complete_gate_fail`; completion time; final identity; original gate decision |
| Baseline `baseline-template/continuation-001/status.json` | Same terminal requirements; retain the previous disk-guard stop and continuation linkage unchanged |
| Each `full_gate/batch_42/batch_manifest.json` | Complete schema; exact seeds 42–241; all 200 finalized runs at 500 turns; source/native/configuration identities and required input maps |
| Each `full_gate/ablation_42/ablation_manifest.json` | Complete, 1,600 unique exact expected records; arms `needs`, `kin_roots`; turns 100/200/300/400; window 20; final horizons T+22; every recorded pair hash and original plain-manifest hash |
| Each batch's `validate_report_full.json`, `gate_decision_full.json`, `gate_summary_full.md` | Final parseable originals; supervisor decision equals the decision file; full source-qualified result, including failure details, remains unchanged |
| Launch, scripts, control history, recovery maps and logs | Exact original bytes, source/interpreter/native linkage, recovered/fresh seed distinction and pause history |
| Fork observer journals and closure | Hash-chain verification, original checkpoint links, observed gaps/issues and bounded-observation limits retained separately from official acceptance |

In these exact old supervisors, `complete_pass` declares exit code 0 and
`complete_gate_fail` declares exit code 2. Status is written before process exit;
record it as the supervisor's declared code until an actual wait/exit observation
exists. Never fabricate an OS exit receipt after a PID disappears. If a zombie's
wait status is observed, record its boot/creation identity and raw wait status;
otherwise retain the explicit distinction between terminal application evidence
and observed process death.

A parent manifest's earlier `complete` status, an observer's 1,600 file pairs,
a paused supervisor, or a log ending in progress is insufficient. In particular,
`failed_or_interrupted`, missing/corrupt receipts, source drift, incomplete forks
or inconsistent final artifacts block this contract. Preserve them for separate
review instead of converting them into storage admission or a scientific pass.

Official old-source decisions used `require_causal_oracles=None`. Retain their
observational/strict and causal component statuses separately. Any later
causal-required adjudication or baseline comparison is a new read-only,
hash-linked result; it cannot overwrite or redefine the original gate decision.

Keep these science-source identities distinct from the later storage-tool source:

| Recovered source | Exact source SHA | Package digest |
| --- | --- | --- |
| Baseline | `cb9fe70c81658fb65c6f511b821447f1d7b55b54` | `5e54205216430f75ca2a6d13890f3a641b0dfdbd4f1cbf7eff3c087b27501fbc` |
| Candidate | `5b5252eded6d45957347af744f01847d2f735ef3` | `0fc95cb7d40fb9f65f0e9f775367a418081b59caf4ae667d0035e81b6a67b3b6` |

Both used original native SHA-256
`43243cb026c6a6a141d15a5df743c96f8aca05c6bdc7c5ce1adbda8e31a6afd5`
and the recorded Python 3.13.5 interpreter/package/thread identities. Preserve
those frozen environments and source checkouts. Admission must compare original
manifest, terminal before/after identities, final ablation records and the
retained file/header evidence against these expected values. Recheck clean source
SHA/package bytes and native binary bytes read-only before a storage mutation;
do not rebuild, reinstall or rerun science under the storage tool's later source.

## Quiescence and worker ownership

Before even a copy-only cohort archive, obtain a controller lease covering both
cohorts and prevent new simulation, validation, forensic or replay consumers from
starting against them. A new advisory lock cannot retroactively constrain the
old runners; their verified termination is a separate prerequisite.

Check the exact original commands, source cwd, boot ID and creation ticks from
the immutable launch/observer evidence for both supervisors and all tracked
children. Require the owned processes absent or terminal with matching birth
identity, zero live descendants, and the observer closed with its final records
preserved. PID disappearance/reuse is not authority to signal a new process.
A stopped `T` worker is still alive. Do not signal, resume or modify the old
gate/controller/observer as part of retention.

Scan accessible local process cwd/exe/fd/maps references to both cohort trees,
selected raw files, archive destinations and restore scratch before starting and
again at mutation boundaries. Record namespace/UID scope, exclusions and any
unreadable observations. Unknown relevant ownership or a live consumer blocks
mutation; a bounded local scan cannot prove that no future or remote consumer
exists. The scheduling lease and final per-file rechecks remain necessary.

Any future storage worker must have its own immutable typed request, tool hash,
operation ID, explicit approved cohort roots and output locations, owned
PID/creation/boot identity, one-thread environment and durable journal. No generic
shell executor, recursive delete, glob-expanded mutation or stop-the-world kill
is authorized. Work is one parent at a time; pauses acknowledge only between
completed per-file transactions.

## Protected bytes and exact selection

Only the direct parent files `state.json`, `state.historiography.json`,
`state.languages.json` and top-level `memories_*.json` may become archived raw
duplicates. Every selected name must be canonical, regular, unaliased, present
in the trusted archive index and absent from every manifest-required input map.
Reject symlinks, hardlinks, special files, traversal, separator aliases and
unrecorded additions. Do not broaden selection based on size or suffix alone.

All other parent files remain raw and at their original paths: every
`validation_*` file and legacy sidecar directory, currently unhashed economy/
resource ledgers, bundles, event streams, exact checkpoints, chronicles and
unknown outputs. Keep all ablation pairs, manifests, reports, decisions, logs,
source/native/environment evidence, original interrupted corpora, recovery maps
and observer records. Hashing only the manifest-required list is insufficient;
retain the stronger whole-parent inventory and unchanged nonselected map too.

The current archive index's raw hashes and whole-parent inventory anchor the
pre-retirement representation. Retention adds a separate path-to-archive storage
overlay and records intentional missing raw duplicates. It never edits the old
inventory, manifest, restore receipt or scientific report to conceal that change.

## Future per-parent transaction

The following is a proposed state machine, not a callable operation:

1. **Admitted.** Validate the completed-gate packet and quiescence lease. Save
   a fresh external request and full selected/nonselected inventories. Verify
   manifest, source/native anchors, archive tool/index hashes and disk budget.
2. **Copied and restored.** Use the existing bounded tool in fresh external
   directories. Verify every gzip/raw hash, an actual filesystem restore of
   every selected file, immutable completion/restore receipts, and unchanged
   whole parent and manifest. Record allocated bytes, not only logical lengths.
3. **Retirement intent durable.** Hash the archive/index/receipts again. Persist
   and fsync an immutable per-file intent containing the exact original path,
   inode/device/change-time/size/hash, archived member and proof references.
   Recheck the consumer lease and protected file inventory. No raw file may be
   removed on the strength of an incomplete archive or only a decoded hash.
4. **Derived scratch reduced.** Remove only byte-verified restored JSON copies
   named by that exact restore receipt and archive index. Retain the original
   `restore-receipt.json` and `status.json` in their original directory, plus a
   new external cleanup record. Each scratch unlink needs its own durable intent,
   identity/hash check, parent fsync and committed record too. Keeping those small
   evidence files preserves
   historical hash/path links; do not recursively remove the scratch directory.
5. **Raw duplicate retired.** Immediately revalidate each eligible original's
   full identity and raw hash, the exact indexed compressed bytes and the
   absence of aliases. Remove only that verified duplicate, fsync its parent,
   and commit a per-file journal record. Preserve the archive and immutable
   index. If any precondition changes, stop without selecting another file.
6. **Parent complete.** Confirm the expected selected paths are archived/absent,
   all nonselected parent paths and hashes unchanged, every required validation
   input raw/in place, and original manifest/ablation/report/decision hashes
   unchanged. Publish the typed retention receipt and measured net allocation.

Crash recovery reads immutable intents and records; it never treats a missing
raw file as proof of successful retirement. An uncertain unlink/receipt boundary
is `unknown` until exact archived bytes and original-path state are independently
reconciled. Already retired files need not be rewritten merely to repair a log,
but no automatic partial cohort/gate acceptance is introduced. Archives remain
mandatory throughout. Any new recovery/resume API needs its own tests and review.

## Original-path restoration must be a separate future contract

The current tool deliberately refuses restoration inside the original batch.
Do not weaken that guard. A future typed operation may restore only names in
the trusted immutable index and retention overlay, into their exact recorded
parent after reacquiring the quiescence lease and verifying the same manifest
and protected files. An existing target, even if apparently equal, is not
permission to overwrite it. Refuse unknown targets, aliases and protected names.

Create each missing allowed target exclusively (`O_CREAT|O_EXCL`, with no-follow
protection where supported), decode with compressed/raw byte caps, flush/fsync,
then independently hash the actual original-path file before its commit receipt.
Keep consumers excluded until the parent is complete. Exclusive creation alone
does not make an interrupted file complete: partial/uncertain targets remain
pending, block normal reuse, and require a separately reviewed operation-owned
recovery decision. Never truncate, replace or silently adopt a partial target.

The final restore receipt must prove all selected raw bytes at their original
paths for the requested parent, unchanged protected files/manifests/scientific decisions, and retained
archives. It does not promise restoration of inode, ctime, ownership, ACLs,
filesystem allocation or cross-platform metadata. Exact original bytes and
paths are the restoration contract; historical metadata remains recorded.
Budget enough free space for this future restoration before admitting new work.
The admission packet must name its restoration scope and reserved byte budget.
On-demand one-parent restoration reserves the largest indexed parent's full raw
allocation plus metadata/write headroom, above the floor; it does not promise
simultaneous residency of all retired raw parents. If full-cohort restoration
must remain immediately available, reserve the entire retired raw allocation
instead. That stronger reserve consumes nearly the raw-retirement gain and
must not be silently counted as procedural-work capacity too.

## Capacity is measured separately from scientific acceptance

The closed-parent metadata inventory at 21:07:30 UTC records:

| Eligible original state/memory JSON | Logical bytes | Allocated bytes |
| --- | ---: | ---: |
| Baseline, 200 parents | 1,183,844,397 | 1,186,787,328 |
| Candidate, 200 parents | 1,183,570,604 | 1,186,455,552 |
| Total possible raw-duplicate retirement | 2,367,415,001 | 2,373,242,880 |

The allocated total is **2.21 GiB before subtracting archives, indexes and
retained receipts**. Copy-only archive plus retained actual restores frees zero
source bytes and consumes additional capacity. Removing just restored scratch
copies returns their added space; it does not reclaim the source originals.
The two seed-42 probe parents are not a cohort-wide measured compression ratio.

At 21:54:56 UTC, free disk was 6,889,586,688 bytes (6.42 GiB). Even the impossible
best case of zero-size archives and complete eligible raw retirement gives only
9,262,829,568 bytes (8.63 GiB) free, or 6,041,604,096 bytes (5.63 GiB) above the
unchanged 3 GiB floor, before remaining forks, indexes, concurrent work and
temporary peaks. Both proposed procedural arms (~10 GB of historical parent
storage before their retained fork/checkpoint costs) therefore lack a disk
admission budget. One arm is not admitted by this arithmetic either: it needs
a measured conservative full retained-output and transient bound first.

The audited old `5b5252ed` and current `2f9d618b` sources both use ablation
design 2. For procedural 300-turn parents, `fork_every=20` and
`T + window < total_turns` give nine fork turns (100, 120, ..., 260), hence
**900 parent checkpoints and 1,800 needs/kin forks per 100-seed source**.
Checkpoint headers are at T+1 and fork horizons at T+22. The normal runner
finishes the entire parent batch before entering its fork stage, so its peak
includes all those parent checkpoints even if its existing later checkpoint
cleanup is retained. The historical ~5 GB parent figure does not bound this
complete modern protocol. Freeze the actual source, arms, output profile and
checkpoint retention policy before measuring/admitting it; additional arms add
work, and this retention proposal never prunes the recovered template checkpoints.

The historical procedural **2.5 GB validation peak is RSS memory**, as described
in [the procedural cost table](procedural-gates.md#cost-and-the-full-profiles-size).
It is not an extra measured disk allocation. Keep RAM and disk budgets separate;
the older external storage proposal's generic validation allowance must not be
read as a 2.5 GB disk measurement. New-source memory/disk peaks remain unmeasured.

After both template gates finish, measure actual final allocations, per-parent
archive/index/receipt sizes, largest parent restore need and net reclaimed bytes.
For each proposed procedural stage require:

`current free - remaining output/transient budget - reserved restoration bytes
 >= 3 GiB + explicitly reserved concurrent growth`

Apply the inequality independently to every filesystem involved. Bound initial
copy/archive/restore headroom before any reclaim, then schedule one complete
procedural arm at a time only if its full fixed protocol fits. Re-measure and
review retention after the first finished arm before admitting the second.
Do not assume compression, discard validation inputs, shorten horizons or
sample fewer seeds to force admission. Extra capacity or another separately
reviewed preservation plan may still be necessary.

## Required future implementation evidence

Before a retirement/original-path restore operation can be authorized, review
tests must demonstrate protected/unhashed paths never mutate, exact original-path
restoration, nonoverwriting collision/alias refusal, source/index drift handling,
disk exhaustion before each write, and actual interruptions at every durable
intent/unlink/write/receipt boundary. Unknown worker ownership must refuse action.
Use synthetic fixtures and a copy-only real-parent rehearsal first; retain all
negative evidence. No implementation or experiment is implied by this checklist.

External source anchors: complete-parent inventory SHA-256
`f6b15ed506c838d20d0b3513f136ebcdfb874049a2d1226bbf25297cfc352956`;
two-parent copy/actual-restore probe receipt
`c0e7122e1ebfc647b0f5dabd2aeec6ccc8ae008c5ece134b130646e59aec4b89`.
These preserve their original observation dates and do not attest terminal gates.
