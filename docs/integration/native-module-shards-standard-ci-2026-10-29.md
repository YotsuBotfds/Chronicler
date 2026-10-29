# Standard Tests native shards — qualified source

All nine jobs passed at **`ec09134b`**, run [40869065907](https://github.com/YotsuBotfds/Chronicler/actions/runs/40869065907),
attempt 1. This qualifies the standard CI graph on that separate source branch:
one fresh builder, two module consumers and a blocking aggregate, while retaining
the six original visible gates. Main/default-branch adoption is separate.

| Lane | Passed parents/tests | Skipped/ignored | Successful subtests |
| --- | ---: | ---: | ---: |
| Native shard 0 | 4,362 | 4 skipped | 407 |
| Native shard 1 | 4,090 | 2 skipped | 119 |
| Native total | 8,452 | 6 skipped | 526 |
| No-Rust | 8,119 | 325 skipped | 526 |
| Offline guard reports | 4,248 | 65 skipped | separate reports |
| Rust | 1,118 | 2 ignored | — |
| Viewer | 743 / 69 files | — | lint/build PASS |

Both native consumers collected the same ordered **8,458 parents / 300 modules**.
Their selections are disjoint and complete. All **25,374 parent phase reports**,
526 successful subtests and six registered skip identities reconcile. Repeated
reports remain distinct, including 28 repeated display labels. The four new
standard-workflow contracts are separate from the 97 shard contracts.

The wrapper preflights pass **2 + 2** cases with zero skips or forbidden calls;
these early passes are separate from full counts. Both practice cases and both
execute_run cases pass in each full environment. Seven compiled adapter cases
pass native and skip explicitly without the extension.

Offline retains 35 chunks with the unchanged 110s limit: 189.5833s observed total,
slowest 30.1986s. All 325 hashes match ec; only two workflow-test hashes differ
from CBF. Its 313 blocked availability imports and 168 calls each to replaced
None factories are retained, with no native module loaded or blocked I/O.

All nine original ZIPs / 90 members pass whole-file and streamed size/CRC/SHA
verification; the wheel's six inner members also verify. Fresh wheel SHA starts
`45aea506`; actual installed native SHA starts `3ee06a53`. Full hashes, artifact
identities/expiry and authority pins are in the JSON. Builder/transfers/receipts/
aggregate agree, and 788 source hashes independently match. Post-suite identity
checks are producer assertions, not external process attestations.

Runtime/native/dependencies remain exact CBF. The four independent job bodies
and standard trigger header are unchanged. Existing closed qualification
workflows remain disjoint; ordinary pushes do not start a duplicate workflow.
The aggregate requires both shards and builder; the native summary also requires
Rust. Unknown/missing modules and partial evidence fail closed.

New modules need explicit assignment; intentional skip/subtest changes need
reviewed registration. Context labels are bounded lossy diagnostics. The nine-
artifact layout must be read as a whole; neither shard is a complete CI result.

The first local 127-pass/1-fail expectation error is preserved; only its historical
manual-dispatch expectation changed before the 128-pass source qualification.
The original `847f164c` publication failure remains failed; isolated `7dcb2402`
qualification is separately pinned. No failed producer was retried unchanged.

Observed wall seconds: builder 141, shards 344/348, no-Rust 451, aggregate 15,
summary 2; created-to-last-job 515. These are uncontrolled observations, not a
speedup, CPU-saving or simulation-capacity result.

Root qualification `56c1355b` and independent peer `5b472808` reconcile this
source-scoped result. This Markdown/JSON is a **curated projection**, not a byte
copy of the producing readout or a claim for a later documentation commit.
It grants no main/default feature promotion, old/new World or RNG/checkpoint
parity, scientific outcome, historical reuse or performance qualification.
