# Native tick index reuse: exact-source CI result

The unchanged standard **Tests** workflow passed all six jobs on its first
dispatch/attempt at `e2b7c940a86911a5ae57a74e0b4df3db6dbd3717`.
[Run 40817210999](https://github.com/YotsuBotfds/Chronicler/actions/runs/40817210999)
was dispatched at 2026-10-29 04:20:38 UTC; its last job completed at 04:34:18 UTC.
No workflow rerun, source fix, local native build/import or local world occurred.
The reviewed commits remain separate: partition `c60fde977d0865fbe651c3f716067d2de5c1a548`,
then dense lookup `e2b7c940a86911a5ae57a74e0b4df3db6dbd3717`.

| Job | Official job ID | Result |
| --- | --- | --- |
| Rust | 123260984801 | 1,092 passed; 2 ignored; 0 failed/filtered |
| Python native execution | 123260985252 | 8,094 passed; 6 skipped; 526 successful subtests |
| Python no-Rust | 123260985085 | 7,780 passed; 306 skipped; 526 successful subtests |
| Python bounded offline | 123260985102 | 3,996 passed; 65 skipped; all 32 chunks passed |
| Viewer | 123260985260 | 743 tests / 69 files passed; lint and build passed |
| Python native aggregate | 123265092037 | Required both native Python and Rust success |

The full unfiltered Rust command produced 37 successful target summaries,
including the 552-test unit target. The four new ordinary, unignored pool/tick
tests are included by exact-source selection. Quiet logs report aggregate
success rather than individual passing names. This is a CI inclusion claim,
not an independent name-by-name execution trace.

Native Python used the freshly built CPython 3.13 extension at the compiled
`.so` path recorded in `native-identity.json`. The unchanged workflow verified
the compiled submodule suffix and all three real class exports before pytest.
Its recorded native SHA-256 is
`2759587e5c67cfd5a1ec5a817b56a31b6b87957509215bed3173ae86ba49ef93`;
the identity names the exact tested source and CPython 3.13.17. The binary
was not downloaded, imported or independently rehashed locally.

`reconcile.py` checked official run/job/artifact source linkage, all four raw
ZIP byte hashes against official digests, and every original ZIP member's CRC
and payload hash. It reconciled native/no-Rust log counts with JUnit parent
elements, skip counts and subtest totals. For offline execution it checked all
32 original guard receipts against the embedded receipt, kept the 110-second
limit unchanged, and compared all 316 recorded source hashes with immutable
Git blobs at the tested commit. Metadata-only reconciliation passed.

Offline guards all report PASS and no loaded native modules. They record a
blocked `chronicler_agents` availability path and 168 ecology plus 168 politics
calls to the explicitly replaced Python-oracle factories; no blocked I/O was
recorded. The chunk maximum was 32.682 seconds; total receipt time was 196.517
seconds. These clocks describe this CI execution, not a controlled benchmark.

The [JSON companion](native-tick-index-reuse-ci-2026-10-29.json) preserves
the reconciled result, complete job clocks, counts and archive/member hashes.
The original source pins, final metadata, four small raw artifacts, decoded
logs, reconciler and evidence manifest remain outside Git under
`/workspace/chronicler-recovered-evidence/native-tick-index-reuse-ci-20261029`.
Candidate and frozen C76 checkout postflight status is recorded there. The
workflow blob is unchanged from the branch base. The original evidence-manifest
SHA-256 is `c47fca7d86c14bb3a8ad97987e3763085f71da1a3023b4709cf44ea009d5fa40`.
A separate lead read of all four retained archives and all 69 member payloads
also reconciles their hashes, CRCs, native identity, JUnit parents and guards;
its receipt is `a427f271dac7e85bc93f4d265ed49e82bc6fa208c431387e540d985ec2042401`.

This result does not establish original/candidate whole-world/default-output
parity, scientific before/after gate qualification or a performance benefit.
Those gates and runtime adoption remain held; no merge is included. Dense
lookup lifetime now spans intermediate phases, so fewer allocations and zero
fills do **not** establish lower peak RSS. A future controlled larger-world
benchmark must measure peak RSS together with CPU and wall time. No CPU,
wall-time or peak-RSS improvement is claimed here.
