# Native and CI consolidation candidate — 2026-10-29

This candidate on `lead/native-ci-consolidation-20261029` composes the exact
native optimizations from `0900f3d2` with the qualified standard CI sharding from
`ec09134b`. Its parent is documentation review `c900633d`. Main is unchanged.
The exact combined code `c5c6b6d9` now has independently/root-qualified [nine-job CI](native-ci-consolidation-ci-2026-10-29.md), run `40880410392`. Documentation-only successors retain that code identity; no additional CI is claimed.

| Boundary | Exact source |
| --- | --- |
| Python simulation package and dependencies | CBF `cbf6e368` |
| Complete native crate tree | `0900f3d2` |
| Standard CI, shard controller/manifest and their tests/fixtures | `ec09134b` |
| Live narration integration test | `0900f3d2` (reviewed Event synchronization) |

No simulation expression, API, checkpoint schema, experiment default or RNG
rule is newly edited here. Four non-document paths come exactly from 090 and
ten come exactly from ec; every other non-document entry remains CBF. Native
changes reuse ascending live slots and the satisfaction-region partition. The
live test awaits the actual spy invocation while preserving its assertions and
failure timeout. Sharding retains complete collection, exact-once ownership,
all six visible gates, Rust barriers and the offline 110-second chunk limit.

Native 090's independent full CI qualified 1,121 Rust passes/two ignored,
8,351 native Python passes/six skips and 8,018 no-Rust passes/325 skips, with
526 successful subtests separate. Standard EC's independent nine-job CI qualified
8,452 native passes/six skips and 8,119 no-Rust passes/325 skips, with 526 subtests.
The c5 combined result records 8,452 native passes/six skips/526 subtests, 8,119 no-Rust passes/325 skips/526 subtests, 4,248 offline cases/65 skips, 1,121 Rust cases/two ignored and 743 Viewer tests with lint/build. The original component records remain separate; 2 + 2 preflights are not added to full counts.

The CBF-to-090 default-export producer succeeded; its independent original-byte
audit is pending. Its actual wheel/native identities belong to that original
producer. The new c5 build independently records native SHA `14a67f28…`, equal to 090, and whole-wheel SHA `507c5b96…`, distinct from the old wheel. No old/new output-parity claim follows from this byte identity or from CI. This candidate
has no whole-turn speedup, peak-memory, scientific-outcome or promotion result.

Wealth-floor physics, the marriage broadphase and the later native fusion source remain separate; this evidence grants no parity or performance result for them.
The current [review](recovered-review-2026-10-29.md) preserves earlier source-scoped
claims and failed runs. [Standard CI evidence](native-module-shards-standard-ci-2026-10-29.md)
and [native partition design](../performance/native-region-partition-reuse-2026-10-29.md)
provide the component boundaries. No source-identical retry or main merge is
part of this candidate.
