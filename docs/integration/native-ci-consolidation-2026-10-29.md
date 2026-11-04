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

The [CBF-to-090 original default-export audit](cbf-090-default-output-identity-result-2026-10-29.md)
is now independently/root-qualified: nine original cases, 399 file pairs and
zero differences. Its read-only audit created no Worlds and retained all 36
actual schema/native/runtime probes. The new c5 build independently records
native SHA `14a67f28…`, equal to 090, and whole-wheel SHA `507c5b96…`, distinct
from the old wheel. The matrix executed exact CBF-to-090; it did not run new
c5/0654 Worlds or qualify full global RNG, checkpoints, scientific efficacy,
whole-turn speed, peak RSS, feature activation or main merge.

The [detached exact-marriage screen](exact-marriage-screen-rejection-2026-10-29.md)
is **COMPLETE REJECTED**, with root and independent review: all 15 synthetic cases/150
samples are retained, 12 criteria pass and spread257/1024/4096 fail. There is
no tuning, retry, production wiring or adoption. Fewer distance evaluations
and the favorable boundary case do not override its registered all-case gate.
Wealth-floor physics and the later native fusion source remain separate; this
default audit grants no parity or performance result for them.
The current [review](recovered-review-2026-10-29.md) preserves earlier source-scoped
claims and failed runs. [Standard CI evidence](native-module-shards-standard-ci-2026-10-29.md)
and [native partition design](../performance/native-region-partition-reuse-2026-10-29.md)
provide the component boundaries. No source-identical retry or main merge is
part of this candidate.

The [registered original practice-byte audit](original-practice-byte-audit-2026-10-29.md)
now closes original RAW authentication and strict semantic/readout/Markdown replay
for source `2d3faa8c`, eight seeds and 24 executions. Remote reader `72704385` /
run `40901409086` passed 118 hosted guarded contracts; local consumers verified
its 15-member small publication, completion links and source snapshots. The large
RAW/wheel, derived rehash, full source-after comparison and owned quiescence keep
their source-qualified remote scope. No new World, full-global-RNG/uninterrupted
physics, efficacy or performance result is implied. The first `e625f6ce`
precollection failure remains preserved.

The [qualified checkpoint-header observations](wealth-floor-checkpoint-header-result-2026-10-29.md)
identify only the false current-civilization/initial-request equality in the
failed wealth cohort: template 5/4 and procedural 11/10. The other four old
shape operands match, while record-growth cause and decoded physical consistency
remain unassessed. The original cohort stays **INCOMPLETE_MECHANICS**; no physics
fix, parent/checkpoint reuse or scientific verdict follows. Unwired K2 metadata
source `78a5998c` does not supply those grants.

Optional retained-Kin care `23d4d246` remains a separate source whose new-source
CI/result qualification is pending in this review; no care code or default is
adopted here. This documentation update retains all 1,058 non-document entries
of `2f164203`, including exact 090 native code and qualified CI wiring. Earlier
CI, default-output and rejected-experiment records keep their original sources.
