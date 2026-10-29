# Models-only forkserver workflow timing — 2026-10-29

The fixed guarded study passed its registered acceptance: median paired
forkserver/fresh cost was **0.882025 CPU and 0.884913 wall**, or **11.80% less CPU
and 11.51% less wall time**. All five pairs remain in the result. This is a
measured workflow result on one small frozen continuation fixture, with strict
state/output checks and process cleanup included. Production launch methods and
the fresh-process default are unchanged.

This documentation branch starts at `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`
so the result and its proposed follow-up are available beside the current source.
It changes documentation only. **The timing did not run c76**: its runtime was
the separately frozen source below. The experimental controller remains separate.

## Inputs and workload

| Input | Exact identity or scope |
| --- | --- |
| Experimental source | `811f5153524080229c071e4f300a8dfca2b32525` |
| Simulation source | `d051d7c06b1a490841d148b8906bde22f2f5d0f0` |
| Native module SHA-256 | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Original checkpoint SHA-256 | `6d85be5c158b2bca4c8635bd8748c992ca0860c695e8a200f7dd40dd8bc3034d` |
| Host/runtime | Linux x86-64, Xeon Platinum 8573C, Python 3.13.5; one worker pinned to CPU 0; hash seed 0 and recorded one-thread settings |
| World | Eight regions, four civilization records; 239 native agents at recorded turn 30 |
| Arms/endpoints | Needs and kin-roots ablations; source ticks 30–51, actual World 52; 206 and 209 agents respectively at 52 |
| Active native checkpoint state | `native.agent.0` only; three available native classes do not mean three active pools |

The original exact loader restored every world anew. The models-only server held
no WorldState or native runtime instance and never imported main, Arrow or the
native module. Every actual server fork checked its real one-task state, permitted
modules, pristine model/template content and global RNG state. Children had
separate owned sessions before runtime imports; no mutated worker was reused.

The registered sequence was:

1. Two metadata-only forks, zero worlds/restores: a private first-child mutation
   and a pristine second child, with actual wait4 and cleanup evidence.
2. Four new unseeded adapter worlds: needs/fresh, needs/server, kin/server,
   kin/fresh. They established fresh arm references at the same logical path.
3. Five paired fresh/server batch comparisons in F/S, S/F, F/S, S/F, F/S order.
   Every batch had eight new worlds in ABBA+BAAB order, four per arm. Each server
   batch started a new server and stopped it after those eight children.

That is **84 worlds, 1,848 actual physics ticks and 252 strict boundaries**.
The 80 timed worlds are separate from the four prerequisites. The earlier
18-world correctness proof and its failed attempts remain separate evidence.

## Results and accounting

Primary acceptance required the median of five paired server/fresh ratios to be
at most 0.95 for both whole-batch CPU and wall cost. Per-arm median allocated
ratios also had to be at most 1.03. Startup/cleanup shared costs were split
50/50 between arms before data; actual unallocated job costs remain retained.

| Pair | Backend order | CPU S/F | Wall S/F |
| --- | --- | ---: | ---: |
| 0 | Fresh, server | 0.840966 | 0.842626 |
| 1 | Server, fresh | 0.799807 | 0.801772 |
| 2 | Fresh, server | 0.882025 | 0.884913 |
| 3 | Server, fresh | 0.907107 | 0.911203 |
| 4 | Fresh, server | 0.965856 | 0.971170 |
| Median paired ratio | All five | **0.882025** | **0.884913** |

The fifth pair, with only 2.88% lower wall cost, is retained. Individual wall
reductions ranged from 2.88% to 19.82%; the criterion was a median benefit,
not a 5% benefit in every pair. These are medians of paired ratios, not ratios
of marginal medians.

| Arm | Median allocated CPU S/F | Median allocated wall S/F |
| --- | ---: | ---: |
| Needs | 0.866675 | 0.862949 |
| Kin roots | 0.882753 | 0.884671 |

Whole-batch wall spans controller launch through exit/reaping. CPU includes exact
wait4 process-tree CPU plus the supervising launcher's CPU. Guards, source/env
checks, imports, restore, physics, witnesses, output/reference checks, compression,
archival and cleanup are included. Logical and physical Linux I/O counters are
retained separately; no conversion from block counts invents byte totals.

Metadata, prerequisites, timing and recorded study-runner overhead together used
**274.033834 CPU / 275.700391 active wall seconds**, below the unchanged 600/900
caps. Human review waits were outside the prospectively defined active interval.
All eleven world-controller receipts report successful cleanup and final input
identity; all helpers were reaped. The 3 GiB running free-space guard did not
refuse execution; completion had 3,860,221,952 free bytes. No raw proof was pruned.

## Strict comparison and independent reinspection

Each world retained loaded30, completed52 and postexports52 carriers, including
complete typed/aliased Python state, raw MemoryStream/cache bytes and identities,
every active native blob, snapshot-cache status and call order. Actual
checkpoint52 sections matched completed52. Completed and post-export carriers
remain separate; they were not forced to agree. Periodic `state.json` correctly
remained at World 50 under unchanged write cadence; it is not the endpoint proof.

The only carried-state normalization was the preregistered exact integer object
binding `world._war_roster_sim`, validated against the actual restored
`agent_bridge._sim`, represented by one persistent token. Raw Python/checkpoint
bytes are retained too. No other carried field or production output was
normalized, and a common logical output path avoided path rewriting.

Python/NumPy singleton initial entropy was recorded as launch provenance rather
than equated across processes. No common singleton RNG seed/reset was imposed. Each job had
to preserve its singleton bytes from before exact load through physics and
exports. No such field was removed from the carried checkpoint state.

Independent reinspection verified **5,265 files / 1,685,438,440 bytes**, eleven
controllers, 84 worlds, 252 boundaries, 2,772 production-file instances (33 per
world), 1,764 witness blobs and 84 checkpoint52 envelopes. It reconstructed all
five ratios, arm allocations and the budget from retained records. Its separate
exact-type audit checked clocks, booleans, counts, descriptors and section
offsets. It launched no worlds, unpickled no state, loaded no native module and
did not decode Arrow. Live object-binding evidence therefore remains the pinned
producer observer and its exact one-token descriptors. Recorded parent overhead
was reconciled from ledger charges, not remeasured from past processes.

| Record outside Git | SHA-256 |
| --- | --- |
| Producer `timing-result-001.json` | `550737afd8f6eace69c9a661eea16a0ea289d331265fc4bf1a90739b2fa8190b` |
| Final study ledger | `0ad8c7296b2490226314d0156585f110f7316f4b37dbd0ac6364033520d90c77` |
| Qualified fresh arm references | `f6ccb50429da372dcd42ad52598826cc025208e2f27b30d2656f4b329524dc79` |
| Independent `verification.json` | `4b260c09f59df9064be8f0cdaa936770ae6822a68e9a227c1291c7f43db2620a` |
| Independent seal | `1059b1efcdefabe91ecf8635640019c3989fac0dbcd602d86a86ba9423b8c232` |
| Supplementary exact-type audit | `20226408aad8cba9c9c3160b7e55c5677ee791a8ff4ac4f3527065c3d6f88705` |

The [small machine-readable result](models-forkserver-timing-results-2026-10-29.json)
records the scope, criteria and pins without copying private logs or raw runs.
Raw evidence remains outside Git under the models-forkserver timing evidence and
reinspection directories; source, native binaries and environments are preserved.

## Readiness boundary

This result supports an opt-in integration experiment. It does not qualify c76,
many-agent worlds, multiple active native runtime kinds, parallel children,
memory savings or production full-gate throughput. It does not promote a default
or establish scientific efficacy. Server lifetime beyond eight jobs is untested.
The frozen prospective README/protocol retain their pre-exposure standing;
the result and independently sealed receipts record completed execution.

The next concrete work is the [bounded integration plan](models-forkserver-integration-plan-2026-10-29.md):
preserve the fresh default, use a dedicated supervisor and a fresh child per job,
then requalify current-source checkpoints, complete production windows and actual
production job order before any rollout. No runtime implementation is included.
