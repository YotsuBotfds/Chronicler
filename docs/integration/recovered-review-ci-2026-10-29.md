# Consolidated review CI qualification — 2026-10-29

All six standard CI jobs passed for exact code and workflow source
`1c5728b74c9a050d817269152a8c92eeda7630dc` on
`lead/recovered-review-20261029`:
[run 40799038789](https://github.com/YotsuBotfds/Chronicler/actions/runs/40799038789),
attempt 1. The last job completed at 2026-10-29 01:25:29 UTC.

The production Python package and Rust crate are byte-identical to qualified
producer `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`. Later review work fixes live
test completion/cleanup, shares validated immutable M36 cohort observations,
and includes pure proof/stat-order contracts in the bounded offline selection.
The original producer branch, checkout and checkpoint identity remain frozen.

The [JSON companion](recovered-review-ci-2026-10-29.json) retains exact run/job
identities, all job/step timestamps, printed chunk summaries, decoded-log
digests and official artifact metadata. Counts come from completed logs;
publication metadata and timestamps come from GitHub Actions. The decoded
logs and metadata are preserved externally. This record introduces no new
test execution, native build or simulation run.

## Completed checks

| Lane | Passed | Skipped or ignored | Additional result |
| --- | ---: | ---: | --- |
| Native Python | 8,027 parent tests | 6 skipped | 526 successful subtests |
| No-Rust Python | 7,713 parent tests | 306 skipped | 526 successful subtests |
| Bounded offline Python | 3,929 tests in 32 chunks | 65 skipped | all guards passed; unchanged 110-second chunk limit |
| Rust | 1,088 tests | 2 ignored | no failures |
| Viewer | 743 tests across 69 files | 0 | lint and production build passed |
| Combined native requirement | success | — | required both native Python and Rust success |

Overlapping lanes are not summed as unique tests. Successful subtests are
kept separate from parent-test passes, and skipped or ignored cases remain
explicit. The native job built a fresh extension wheel with CPython 3.13.17
and checked compiled-module/class availability before pytest. Its native
identity receipt is retained in the published artifact; that receipt was not
separately downloaded for this readout.

## Observed clocks

| Lane | Complete job seconds | Relevant step seconds | Reported test clock |
| --- | ---: | --- | --- |
| Native Python | 744 | wheel build 167; native tests 556 | pytest 552.02 s |
| No-Rust Python | 281 | tests 269 | pytest 266.11 s |
| Bounded offline | 222 | guarded runner 174 | printed chunks sum to 173.4 s |
| Rust | 72 | tests 60 | individual suite summaries retained in log |
| Viewer | 104 | tests 65; lint 13; build 14 | — |
| Combined native requirement | 3 | requirement check below one whole second | — |

The first jobs started two seconds after run creation. Creation to the final
requirement's completion was 752 seconds. Job clocks include setup/reporting;
test-step clocks include overhead absent from pytest's own clock. Chunk
seconds are rounded values printed by the runner, so their sum need not
equal the enclosing step. The slowest was `systems-2`, **29.2/110 seconds**.
These are single hosted-run observations, not a controlled speed comparison
or aggregate CPU measurements.

## Published evidence

The four nonexpired artifacts below are bound to this exact run/source.
Digests are **GitHub-reported ZIP digests**; this readout did not download or
independently rehash their archive payloads. They expire on 2026-11-12, with
exact timestamps and complete names retained in JSON.

| Evidence | Artifact ID | ZIP bytes | GitHub SHA-256 |
| --- | ---: | ---: | --- |
| Native Python | [12864854064](https://github.com/YotsuBotfds/Chronicler/actions/runs/40799038789/artifacts/12864854064) | 138,139 | `5de364070461860e7d3e90313d2694ee91ac5c19fec4ad0bd7d68d36ba62cba4` |
| No-Rust Python | [12865735546](https://github.com/YotsuBotfds/Chronicler/actions/runs/40799038789/artifacts/12865735546) | 139,164 | `ea1844c00394f631f1dca96930e1e08b6f6094471fa2f12f57db8cd1e1b329b3` |
| Bounded offline | [12864788954](https://github.com/YotsuBotfds/Chronicler/actions/runs/40799038789/artifacts/12864788954) | 41,709 | `e98059dfd883e69ea8f8c06d3e173d2310097d515cc627e5063ef435b066a570` |
| Rust | [12864858196](https://github.com/YotsuBotfds/Chronicler/actions/runs/40799038789/artifacts/12864858196) | 521 | `0ec4c14b6bcdda3a6372ea185b7c5eda3b08c6a4f775487fb1ada808a76e6440` |

## Scope

This qualifies the consolidated test/workflow source in the standard CI
matrix. The linked [live lifecycle](../performance/live-roundtrip-lifecycle-2026-10.md)
and [M36 observation-reuse](../performance/m36-cohort-observation-reuse-2026-10.md)
records preserve their separate focused/exhaustive validation and original
observer failures. Later documentation-only commits do not create another
runtime qualification.

The [earlier CI/arc pack](ci-arc-qualification-2026-10-29.md) retains its four
different exact sources. Export identity, native composition, scientific
full-gate comparison and forkserver timing retain their own source boundaries.
No browser-session QA, natural optional-system efficacy, full population-gate
result or default activation is established here. Main is unchanged.
