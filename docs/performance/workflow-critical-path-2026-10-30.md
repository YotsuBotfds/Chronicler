# Standard CI wall-clock evidence and safe options — 2026-10-30

Fresh official run and job metadata identifies the native producer/shard chain
as the critical path in the three completed samples. There is no controlled
speedup experiment here. Source and runner variation can affect every duration;
the measurements do not establish a cache cause or a stable shard imbalance.
No workflow body, test selection, native source, cache flag or scientific gate
is changed by this analysis or the optional offline reporting helper.

## Parallel jobs and critical path

| Parallel role / stage | 701 run 40981650005 | 5122 run 40987709533 | ca8 run 40988805361 |
|---|---:|---:|---:|
| Wheel producer job | 129 s | 201 s | 199 s |
| Of that: combined wheel build/install step | 93 s | 166 s | 173 s |
| Native shard 0 job | 353 s | 268 s | 290 s |
| Native shard 1 job | 354 s | 346 s | 346 s |
| Collection + owned tests, shard 0 / shard 1 | 335 / 336 s | 255 / 329 s | 274 / 332 s |
| Aggregate job after producer and both shards | 21 s | 13 s | 17 s |
| Final native + Rust barrier job | 4 s | 3 s | 3 s |
| No-Rust job, parallel from run start | 339 s | 436 s | 420 s |
| Guarded offline job, parallel | 165 s | 214 s | 175 s |
| Rust job, parallel | 70 s | 73 s | 77 s |
| Viewer job, parallel | 116 s | 91 s | 89 s |
| Official run created→updated | 520 s | 574 s | 575 s |

The selected **Chronicler Tests V2 source profile** has independent producer,
Rust, offline, no-Rust and Viewer roots. Both native shards need the producer;
aggregate needs the producer **and both shards**, including the direct redundant
producer edge; the final native barrier needs aggregate and Rust. The profile
is an explicit assumption verified against the pinned workflow source, not a
DAG inferred from the jobs API or a rule for arbitrary repositories.

Observed job creation→start was only 1–3 seconds per job. Native child jobs did
not exist while the producer was running: that delay is dependency sequencing,
not measured runner-queue congestion. The producer→slower shard→aggregate→final
chain is critical in all three completed samples. Job wall durations are not CPU
time; sums across parallel jobs do not describe elapsed pipeline time or prove
available runner capacity. Python dependency-install steps on native shards
were only 3–8 seconds, so adding a cache/runner system is not justified by those
small costs alone.

## What the upper bounds do and do not justify

Equalizing just the observed shard test work, with all other job durations
fixed and no scheduling gaps, could lower the duration-only path bound by
**0.5 second in 701 versus 37 seconds in 5122**. The later ca8 sample has
58 seconds of test-step imbalance, but equalizing only that work saves 27
seconds after preserving its different per-shard overheads. The first pair was already almost
balanced; the next was not. A partition based on only the latter could move
work in the wrong direction on another runner. Historical module weights are
attribution, not current per-module timing measurements. Keep all 305 current
whole-module assignments until repeatable module-level evidence supports a move.

Even a hypothetical zero-cost wheel build/install step would save at most
**93 seconds in 701 and127 seconds in 5122** on the fixed-duration DAG bound.
The latter is less than its 166-second build step because the 436-second parallel
no-Rust job would become critical. These are optimistic arithmetic bounds,
not predicted improvements and never permission to skip build/admission gates.
A real build improvement must preserve the same current-source producer,
wheel/native/package verification and scientific tests. The ca8 zero-build-step
bound saves at most 145 seconds before its 420-second no-Rust lane limits it. The dormant native
cache remains disabled; metadata alone does not establish why build time varied.

Practical options, in order:

1. Use complete saved official metadata to track the native chain, scheduling
   gaps and the next bottleneck. This patch supplies a pure offline analyzer;
   it changes no CI scheduling and performs no network operation.
2. Attribute producer build cost more precisely in a separately reviewed change
   before trying a cache/toolchain optimization. The current combined step
   hides compilation versus wheel packaging/install time. No cause is inferred.
3. Use repeated per-module evidence before changing native assignment. A single
   run's 74-second test-step imbalance does not establish a stable heavy module.
4. Consider small aggregate/bootstrap reductions only with evidence: their
   combined overhead is far below the producer/shard work and a small fixed
   saving may merely expose the no-Rust lane sooner.

The retained workflow contracts compare complete native job bodies with the
qualified V2 fixture, apart from tightly pinned disabled-cache projections.
A workflow-only edit would fail that contract. Any future scheduling change
must deliberately preserve or review that contract; this patch edits neither
workflow nor fixture and does not weaken the barrier.

## Optional offline analyzer

`scripts/ci_critical_path.py` uses only the standard library and is opt-in:

```sh
python scripts/ci_critical_path.py --run saved-run.json --jobs saved-jobs.json --format markdown
```

Inputs are full saved official REST run/job objects, or the existing fetch
connector envelopes around those objects. Use the full jobs endpoint with
`per_page=100`; the step-summary wrapper omits required timestamps. The helper
makes no API call, executes no job body, reads no environment/secrets, and writes
only its JSON or Markdown report to stdout. Each supplied JSON file is bounded
to 2 MiB; duplicate keys, ambiguous/unknown roles, run/source/attempt/branch joins,
missing pages, inconsistent timestamps and invalid completed sets refuse.

The fixed profile is printed in every report, including the direct
producer→aggregate edge. Valid partial runs may omit not-yet-created known
roles or contain in-progress jobs. They produce **PARTIAL_METADATA**, with no
invented remaining durations, terminal CI result, or what-if completion claim.
A complete metadata report still supplies no artifact, test or scientific
qualification. Its what-if scenarios require a successful complete job set and
are optimistic duration-only bounds under unchanged other-job durations.

The nondefault `tests/ci_critical_path_contracts.py` selection checks these
behaviors using synthetic metadata, including bottleneck migration to no-Rust.
It adds no native/default owner, offline chunk, workflow registration or test
selection. All preexisting test bytes and coverage remain unchanged. Focused
execution under the existing offline guard is a separate root decision.

## Evidence scope

The completed official samples are attempt 1 for sources
`701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d`,
`5122fad852535f1f70a281c5b0fbfef06dfa8f69`, and
`ca8a0a51ab1630470db29bba1616f80001bc17ab`. The first ca8 snapshot was partial
and is preserved separately. A fresh metadata-only update found all nine jobs
successful at 2026-10-30T02:06:29Z; that is an official status observation, not
saved-byte artifact qualification or a controlled settlement speed comparison.
All raw metadata responses and calculation records remain outside Git. No
artifact/log body calls, workflow edits, reruns, builds, test execution or
network-driven job action were used to obtain this timing evidence.
