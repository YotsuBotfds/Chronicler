# Receipt-policy compatibility: qualified standard CI at 469

The stock runner now accepts the closed, source-owned optional care/forecast
receipt shapes while preserving legacy receipts, parent binding and the separate
science-policy contract. Exact code `46967ce6c70561e0bb7baa8dec1f1bd895ff0cd9`
has independently and root-qualified all-nine-job standard CI in
[run 40932674679](https://github.com/YotsuBotfds/Chronicler/actions/runs/40932674679),
attempt 1, on the persistent development-review branch. Main is unchanged.

| Job | Actual result |
| --- | --- |
| Viewer | 743 tests in 69 files; lint and build pass |
| Python bounded offline | 4,562 passed, 65 skipped, 97 subtests; 38 chunks |
| Python no-Rust | 8,336 passed, 325 skipped, 623 subtests |
| Build one current-source native wheel | Fresh wheel and 800 source-file identity verified |
| Rust | 1,140 passed, 2 ignored; 599 library tests |
| Python native module shard 0 | 4,412 passed, 4 skipped, 407 subtests |
| Python native module shard 1 | 4,257 passed, 2 skipped, 216 subtests |
| Python native execution | Exact-once aggregate and fresh build/transfer identity pass |
| Python native | Final native gate passes |

Together the native shards pass **8,669 parents with 6 skips and 623 successful
subtests**. Both collect the same ordered 8,675 parents across 303 modules; their
selected modules form a disjoint exact-once union. All 26,025 parent phase reports,
six exact skip IDs, subtest order/multiplicity and repeated labels reconcile.
The 2 + 2 turn-wrapper preflights are separate from the full-lane totals.

All **71 added receipt-policy cases** pass in both full Python lanes and the
existing whole-module offline selection. These are pure/fake metadata contracts;
they do not execute genuine experiment workers. The 38 care model/fake parents
and 97 subtests, 22 forecast model cases, 58 K2 dictionary cases and 125 metadata
cases keep their own scopes. All 38 offline chunks retain the 110-second limit
and 329 source pins; the metadata module runs in its dedicated standard chunk.

The complete 181-file package digest is
`074ac7565820d4d1145cc9efa8d16985e1543b57c4dffbf6db2b3ba9d116006d`.
The fresh current-source wheel SHA-256 is
`3a8859827e64303e1d127732ae6ca5655b2da0ce37fee9bfce098a67ae2dfddd`;
its native member is
`38dddb970b7e832ccaacced1a51df860cb7d7bbd73c137a3936ecd91a65d56a5`.
The 800-file source identity, nine original ZIPs, 96 outer members and six inner
wheel members reconcile. Prior matching native bytes do not replace the current
build/transfer receipts. Rust quiet output links the successful unfiltered target
to its source tests; it is not a named installed-wheel API/schema observation.

The builder actually restored all three previously resident branch keys: exact
uv/Cargo-download hits and a release restore key from `94b308e6`. It then saved
the current release key. The builder job took 120 seconds, its wheel-build step
95 seconds, Cargo reported 93 seconds, and creation to last job took 497 seconds.
These are naturally changed-source observations, not a controlled speedup or
simulator throughput/capacity result. Cache IDs were associated by exact old
inventory keys; no future hit or reservation is promised.

The primary reader's first module-level JUnit address join failed because it
added a class separator without a class. Its frozen reader and transcript stay
preserved. A one-line successor corrected only that separator and passed against
the same original ZIPs; no count, ordering or skip rule changed. Metadata-only
connector/formatter attempts are also retained. There was no producer/test/build
retry. Root seal `b6bef07c…` binds the independently reviewed core `1c7e7626…`;
the final peer wrapper `f8eb598a…` additionally binds cache/step review `83fd84b2…`.
The [curated JSON](policy-receipt-compatibility-ci-2026-10-29.json) carries full
paths, hashes, original artifact identities and source joins.

## Separate work remains held

The first actual 090 profiler run `40927885410` is finally authenticated as
**incomplete**, under root seal `d44f8ab3…`. Role 0 refused the frozen checkpoint
fingerprint traversal cap; no role/comparison completed and failed-role physics
ticks remain unknown. Later retention refusal and terminal `KeyError` remain
negative evidence. Source proves deliberate link fixtures conflict with the
whole-root inventory rules; it does not identify the actual first offending path.
Overall cleanup is uncertified, without an observed-leak finding. There is no
accepted profile result or actual retry.

Forecast study controller `99143193` separately reports **183 pure/fake passes**
after four reader acceptance repairs. Successor independent/root clearance and
durable original-RAW retention are still held; it is not grafted here and has no
actual World/checkpoint study or current full-CI binding. The bounded care
transient recorder is in source implementation, without a new native build,
recording-neutrality proof or enabled World. Both tracks need their own reviewed
source and runtime gates.

This CI qualifies receipt compatibility and current standard tests. Genuine
enabled care/forecast Worlds, checkpoint trajectories, actual schema/new-method
measurements, default-output/global-RNG identity, K2 decoded-state reuse,
scientific efficacy, performance, adoption and main promotion remain separate.
Earlier [94/3a reviews](current-development-cross-examination-2026-10-29.md) and
their JSON retain their original source and historical facts.
