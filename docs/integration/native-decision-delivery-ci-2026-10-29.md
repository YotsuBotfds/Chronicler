# Native decision delivery CI — 2026-10-29

All six unchanged standard CI jobs passed at exact source
`e99c0fd52f3839ba89dc0c65bf217542e42acbc4`, isolated branch
`lead/decision-delivery-native-20261029`, [run 40813775699](https://github.com/YotsuBotfds/Chronicler/actions/runs/40813775699), attempt 1.
The final requirement completed at **03:52:26 UTC**. Workflow blob
`26afaa1f92c7f7a5f4fcf87571bfd8b022255c56` is unchanged from review `82b3699b`.
The [JSON companion](native-decision-delivery-ci-2026-10-29.json) retains both
complete runs, job/step clocks, counts, official artifact pins and receipt links.

| Completed lane | Passed | Skipped/ignored | Additional result |
| --- | ---: | ---: | --- |
| Native Python | 8,099 parent tests | 6 | 526 successful subtests |
| No-Rust Python | 7,780 parent tests | 311 | 526 successful subtests |
| Bounded offline | 3,996 tests / 32 chunks | 65 | all guards pass, unchanged 110-second bound |
| Rust | 1,102 tests | 2 | 562-case library suite passes |
| Viewer | 743 tests / 69 files | 0 | lint and production build pass |
| Combined native requirement | success | — | both native Python and Rust success |

Overlapping lanes are not summed as unique tests. JUnit totals reconcile to
parents + successful subtests + skips: native **8,631**, no-Rust **8,617**.

## New contracts and compiled identity

Fourteen new Rust cases cover actual needs arithmetic/cap shadowing, copied
roots/pull values, RNG/decision/pool parity, displacement, full-tick events and
legacy statistics, deterministic one-versus-two-worker quotas, validity and
checkpoint transience. They are source-linked to the complete unfiltered
library pass; quiet Cargo output provides no individual passing-name lines.
No separate targeted invocation was needed or launched.

Retained JUnit proves all **five real compiled API cases pass**: configuration
and recorded schema, events/payload/source-turn/ablation parity, candidate
capture and truncation/selection/disable, same-new-build checkpoint restore,
and stale-frame clearing after accepted-call signal parsing fails. The same
five explicitly skip with **native extension absent** in the no-Rust lane.
Fixtures use two direct Arrow regions and fresh tiny populations, without a
world generator. Candidate rows must be nonempty and reconcile with the
complete-capture header count.

The job freshly built and installed a CPython 3.13 release wheel, preloaded the
real compiled module/classes, and retained its identity. The verified identity
receipt reports CPython **3.13.17** and `.so` SHA-256
`1bc7159ab4b4ae4dba386ffd9dc061ef355c785f6ebd0d97aa0fc75d6b1eca8e`.
Original `dec95033` reports the same binary SHA after its separate build.
This is producer-reported binary identity inside independently rehashed ZIP
bytes; this audit did not download/recompute the binary or wheel hash.

The recorded old schema fingerprint **dcf0c34097c88451** and within-new-build
on/off checkpoint equality pass. No historical checkpoint was relabelled or
rebound into this native binary. Old/new default-output parity, large-agent
behavior and scientific efficacy are outside this qualification.

## Original failure and narrow correction

Original [run 40813417246](https://github.com/YotsuBotfds/Chronicler/actions/runs/40813417246)
at `dec950334e9d7fceb77e51b482b60931357ffbc5`, attempt 1, remains **failure**.
Compilation succeeded; the new direct two-tick Rust fixture failed at
`tick.rs:1455`, indexing slot 16 into a 16-entry percentile scratch array:
**561 library passes / one failure, 2.23 s**. Later Rust harnesses did not run.
Native Python independently passed all 8,099 parents and all five new API
contracts; no-Rust/offline/viewer passed. The combined native requirement
correctly failed with Python success and Rust failure.

First-tick births grow `AgentPool::capacity()` (allocated slot count). The
fixture missed the per-turn scratch resize already performed by production
FFI and existing multi-turn tests. Root and independent peer reviewed the
correction: **three test-only lines**, refreshing each scratch vector against
its own pool before the next tick. Births and all two-tick assertions remain.
Runtime, Python and workflow source are unchanged from `dec95033`. A new
commit/run was used; the original run was allowed to finish without cancel,
rerun, overwrite or reclassification.

## Observed clocks

These are single hosted-run observations, not controlled performance evidence
or CPU measurements. Job clocks include setup/reporting; test steps include
overhead absent from the framework's reported test clock.

| Corrected lane | Job seconds | Relevant step seconds | Reported test clock |
| --- | ---: | --- | --- |
| Native Python | 510 | wheel 113; tests 374 | pytest 368.60 s |
| No-Rust Python | 366 | tests 352 | pytest 347.80 s |
| Bounded offline | 187 | runner 172 | printed chunk sum 171.9 s; max 28.7/110 s |
| Rust | 61 | cargo 50 | summed harness clocks 6.10 s; library 2.26 s |
| Viewer | 114 | tests 72; lint 13; build 15 | Vitest 70.77 s |
| Combined native | 3 | requirement 0 | — |

Creation to final job completion was **518 seconds**. Original run clocks remain in JSON, including native pytest 525.05 s and no-Rust 413.66 s. Their difference is not a speed claim.

## Published evidence

All four corrected artifacts are nonexpired and expire on **2026-11-12**;
JSON preserves exact creation/expiry timestamps and full names. The two Python
ZIPs were independently rehashed in RAM and their retained JUnit/identity
members verified. Rust/offline rows are official current API publication
metadata, without an independent ZIP rehash. Original four artifact pins remain
separate in JSON. No raw logs or signed transport URLs are included here.

| Corrected evidence | Artifact ID | ZIP bytes | SHA-256 |
| --- | ---: | ---: | --- |
| python-native | 12872060517 | 138,169 | `ae71929341272a9cc54801a8f8262d089f6a68ce1bb187de6804075438d39363` |
| python-no-rust | 12871861535 | 141,053 | `ebf8b9c5c55e5fde7d6746c99f033d9081a9d988a1b01d85a3f6f4ee8e3216a1` |
| rust | 12871228496 | 716 | `81ce6252ed3c3f9d08bfd5412ae852b7907c9b58a83b49a823d762b92017a1d6` |
| python-offline | 12870944790 | 41,866 | `6172a09a73c78ad3039d24e9a055ad119ac51d04e45de7cebcb5a275b33ae050` |

## Scope

This qualifies native-only Stage 1 tooling and its standard exact-source CI.
It records actual decision/candidate values with explicit validity/truncation;
applied household provenance and counterfactual effects remain incomplete.
Python writers, CLI and experiment-harness integration are not implemented.
The original full population gates retain their frozen 2f9/d028/06db identities;
no new scientific cohort or coefficient/threshold change was run. All builds
and tests ran remotely. Local receipt inspection used only bounded stdlib
JSON/XML reads, with RAM admission and the 3 GiB disk floor preserved. Main and
the frozen producer/source refs remain unchanged.
