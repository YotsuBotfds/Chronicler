# Native and CI consolidation candidate — 2026-10-29

This candidate on `lead/native-ci-consolidation-20261029` composes the exact
native optimizations from `0900f3d2` with the exact standard CI sharding from
`ec09134b`. Its parent is documentation review `c900633d`. Main is unchanged.
Combined-head CI has not run; the source-scoped results below are prerequisites.

| Boundary | Exact source |
| --- | --- |
| Python simulation package and dependencies | CBF `cbf6e368` |
| Complete native crate tree | `0900f3d2` |
| Standard CI, shard controller/manifest and their tests/fixtures | `ec09134b` |
| Live narration integration test | `0900f3d2` (reviewed Event synchronization) |

No simulation expression, API, checkpoint schema, experiment default or RNG
rule is newly edited here. Four non-document paths come exactly from090 and
ten come exactly from ec; every other non-document entry remains CBF. Native
changes reuse ascending live slots and the satisfaction-region partition. The
live test awaits the actual spy invocation while preserving its assertions and
failure timeout. Sharding retains complete collection, exact-once ownership,
all six visible gates, Rust barriers and the offline110-second chunk limit.

Native090's independent full CI qualified1,121 Rust passes/two ignored,
8,351 native Python passes/six skips and8,018 no-Rust passes/325 skips, with
526 successful subtests separate. StandardEC's independent nine-job CI qualified
8,452 native passes/six skips and8,119 no-Rust passes/325 skips, with526 subtests.
The combined head needs its own complete nine-job result and binary provenance.
These historical counts are expectations to reconcile, not combined results.

The CBF-to090 default-export producer succeeded; its independent original-byte
audit is pending. Its actual wheel/native identities belong to that original
producer. A new combined-head CI build must record its own bytes; no binary or
output-parity claim is inherited merely from source composition. This candidate
has no whole-turn speedup, peak-memory, scientific-outcome or promotion result.

Wealth-floor physics and the marriage broadphase prototype remain separate.
The current [review](recovered-review-2026-10-29.md) preserves earlier source-scoped
claims and failed runs. [StandardCI evidence](native-module-shards-standard-ci-2026-10-29.md)
and [native partition design](../performance/native-region-partition-reuse-2026-10-29.md)
provide the component boundaries. No source-identical retry or main merge is
part of this candidate.
