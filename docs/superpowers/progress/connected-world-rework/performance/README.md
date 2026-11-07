# Connected World rework: runtime performance diagnosis and admission

This packet diagnoses the retained implementation before optimization. It does
not claim a speedup, corrected-model efficacy, qualification or default
promotion. The physical attribution/crowding correction belongs to the lead's
separate correctness work. A corrected **unoptimized** source must be frozen
before admitting any optimization using the matched plan below.

## Reproduced diagnostic and identities

The serial diagnostic ran the existing declared `proc32_s19-full` case unchanged:
seed 19, 32 regions, ten initial civilizations, **200 turns**, all FULL flags,
real validation Arrow sidecars and checkpoints at 50/100/150/199. The source was
clean main `2726bf449d0e4d581a72034000ee0861a58ee439`; CPython 3.13.5 imported
this lane's `src` and the actual release native extension
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
The source snapshot covers 344 inputs with digest
`2bdb18caf812208ac82b034a8951bc2144f91f51b2fece0cdafa05e3ff41ab5d`.
`RAYON_NUM_THREADS=1`, `PYTHONHASHSEED=0`; no simulator proxy or paid narration.

The [measurement wrapper](diagnostic-wrapper.py) surrounds only `execute_run`
with cProfile, using process CPU time. It retains the original scale profiler's
source/native checks and exact checkpoint reads. Instrumentation is expensive:
300.38 profiled CPU seconds and 301.56 measured run CPU seconds, versus the
historical uninstrumented 95.15 seconds. These are **not** a before/after
optimization comparison. Use the diagnostic to rank costs, not infer absolute
speed or a hardware-independent fraction.

The [compact call profile](main2726-proc19-calls.json) reports 264,263,575 calls
(246,749,115 primitive) and 6,610 functions. Cumulative times overlap:

| Measured scope | Calls | Diagnostic cumulative CPU seconds |
| --- | ---: | ---: |
| All simulation turns | 200 | 216.83 |
| Timber order planning | 200 | 59.63 |
| Timber dispatch | 46,007 | 30.51 |
| Full population conversion, `titled_trade._people` | 41,557 | 21.26 |
| Shortest paths, `titled_trade._bfs` | 85,887 | 20.31 |
| Dated timber price lookup | 83,376 | 7.39 |
| History encoding | 1 | 41.75 |
| All Python deep copies | 3,966,407 | 16.10 |
| Arrow arrays converted to Python lists | 222,254 | 9.26 |

Timber planning accounts for 27.5% of instrumented simulation CPU in this world.
Many rejected A6 market candidates independently rebuild the entire population,
the same origin paths and the same previous prices. This is avoidable work;
wallets, treasury, escrow, cargo, bookings and physical stock remain live.

The [diagnostic metrics](main2726-proc19-metrics.json) retain all turns, actual
population and checkpoint timings. Peak native population was 1,026; bundle
size 71,441,011 bytes; run peak RSS 1,993,892 KiB. Strict integrated extraction
reported zero problems. The wrapper did not change the run: [transparency](profiling-transparency.json)
and [whole-file comparison](profiling-output-file-comparison.json) show all 117
other simulation outputs, including every Arrow file, are byte-identical to
the retained `eaa4a5d3` case. The complete encoded bundle is identical in JSON
types, values, order and signed zero after normalizing only `generated_at`.

## Storage attribution and separate format proposal

The [exact encoded component analysis](bundle-components.json) attributes
63,721,665 value bytes to `history_delta`; livelihood fields account for
54,996,239 bytes, about 77.0% of the complete file. Largest package values are
public health 9,615,697; household retail 8,657,649; wealth accounting 7,635,354;
adaptive livelihoods 3,983,928; titled trade 3,634,384; and local budgets
3,285,807 bytes. These counts exclude surrounding key/separator overhead;
they do not justify deleting evidence, nulls or authoritative histories.

A [static lossless gzip experiment](gzip-feasibility.json) retains every input
byte: level 1 yields 17,441,926 bytes in 0.59 CPU seconds and decompresses in
0.277 seconds; level 6 yields 13,908,635 bytes in 2.19 seconds and decompresses
in 0.216 seconds. These single observations establish feasibility only.
No production codec or wire format changes in this lane. An explicit compressed
artifact option would need the lead's format/default-off decision, old-reader
compatibility, strict provenance binding and real browser verification.

## Conservative timber optimization

The candidate memoizes only paths and dated prices within one synchronous
planning call, and uses only native id/region/occupation/age to avoid repeated
population scans before a known-market refusal. Standalone dispatch keeps fresh
reads. An accepted planned candidate refreshes native eligibility and wealth
before quantity, stock, quote or payment decisions. Enlistment/trips, active
orders, capacity, free timber, envelope, treasury and settlement remain live.
Nothing caches a wallet, persists planning facts or changes candidate/settlement
order or floating-point arithmetic. Each later turn rebuilds the facts.

The [old-source cost regression](timber-old-regression.txt) uses an archived
`2726bf44` source with 100 ineligible-market candidates. All 100 refusals, wallet
balances, stock and treasury observations are correct, but the old code performs
101 full-population conversions; the fixed path performs one. The regression
fails on the old `101 <= 2` cost bound. This is a computational regression,
not evidence that the old economic outcomes were wrong.

Focused checks: 32 timber tests, the real compiled-native lifecycle test, and
the unchanged official `connected-world-completion` guarded chunk: **206 pass**,
guard PASS, 3.77 seconds under the unchanged 110-second limit. The
[receipt](timber-guarded-receipt.json) covers the exact source/test hashes.
Tests retain same-turn freight credits, depleted wallets, changed native
eligibility, competing destinations and stock, carrier reuse exclusion, and
later-turn route/price changes. Full source-level review and matched corrected
whole-run admission remain separate required gates.

## Frozen corrected before/after plan

Use [profile-rework.py](profile-rework.py) with a clean corrected source and
its verified native environment, then the optimized source using the **same
native artifact, interpreter and explicit physical flags**. FULL is the CWR
`AD` configuration: rules 3, all decision channels, `density_only` crowding.
The tool takes CWR's actual BASE/AD flags, not the old CW6 rules-2 defaults;
OFF strips the new parameters and keeps the prior chain/control.

| Fixed world | Turns | Declared regions/civilizations | Population treatment | Checkpoint turns |
| --- | ---: | --- | --- | --- |
| Template seed 5 | 200 | 8/4 | unchanged generated population | 50,100,150,199 |
| Procedural seed 19 | 200 | 32/10 | unchanged generated population | 50,100,150,199 |
| Historical scaled22k seed 42 | 30 | 12/4 | original target 18,800; actual initialized count recorded | 10,20,29 |
| Historical scaled52k seed 7 | 20 | 12/4 | original target 43,700; actual initialized count recorded | 5,10,15,19 |
| Procedural seed 42 | 150 | 48/10 | unchanged generated population | 50,100,149 |

Each source runs both OFF and FULL: ten runs per source, twenty total, with
72 exact same-source checkpoint reads. No new held seed or qualification gate
is used. The lead requested a separate cheap admission pair before the matrix,
so the actual timing pilot was **template seed 5 FULL, 200 turns**, capped at
450 process CPU seconds per source. It replaces the originally proposed proc19
pilot. [The budget amendment](matrix-budget-amendment.json) records the change,
projection and uncertainty before reporting any matrix results. The frozen
paired-suite ceiling is 2,700 process CPU seconds (0.75 core-hours), split into
1,350 per source; stop and retain failures if it is exhausted. This is separate from the offline
110-second chunk limit, which remains unchanged. Each child also receives a kernel
process-CPU ceiling equal to the remaining suite budget rounded up to a whole
second; its plan records the rounding. Schedule one profiling process
at a time after the lead releases the native-build/storage-benchmark slot.

The tool records complete per-turn and stage CSVs, CPU and wall time separately,
actual native counts, RSS, file bytes/SHA256, Arrow identities and checkpoint
read/write stages. High-frequency helpers are counted without individual
timers; their timing is **null**, not an invented zero. Outer planning and
serialization stages are timed; nested timings are cumulative, not additive.
No speedup claim uses the expensive cProfile diagnostic as its baseline.

[compare-profiles.py](compare-profiles.py) refuses changed flags/scale/horizon,
native artifact, interpreter, population trajectory, missing/changed outputs,
incomplete CSVs, failed extraction or changed decoded histories. It normalizes
only `metadata.generated_at`. Exact checkpoint exports bind each artifact and
compare native bytes, decoded world/history and every persisted livelihood
component, including JSON-excluded X1 person rows. Source identities in the
envelopes legitimately differ; no mismatched-source checkpoint is restored.
The [tool controls](measurement-tools-controls.json) pass 15 synthetic positive
and negative checks, including unknown-to-zero, identity, signed-zero, private
X1 state, artifact binding, flags, native identity and truncated CSV rejection.
These controls are not simulation evidence or a qualification claim.

The [actual template pilot comparison](template200-pilot-comparison.json) passes
all 117 non-bundle outputs, every Arrow file, the complete decoded bundle and
four native/private-state checkpoint comparisons. Corrected unoptimized source
`09403c15070ddab4977ae8b2e65c336238468447` and its timber-only optimization
`a1fcb482f4d971e1c20e99075f2e256f9838a359` share native artifact
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`.
Whole-run CPU is **22.3021 → 22.3118 seconds**, a null +0.04% observation in
single runs. Timber planning falls from 0.7992 to 0.2876 seconds; complete-child
CPU including checkpoint reads, validation and evidence is 33.26/33.53 seconds.
The matrix will freshly repeat this case alongside the other fixed scales.

```sh
TOOL=docs/superpowers/progress/connected-world-rework/performance/profile-rework.py
PYTHONPATH=FROZEN/src NATIVE/bin/python "$TOOL" run PILOT \
  --source-root FROZEN --expect-commit CORRECTED_REF --native-sha256 NATIVE_SHA \
  --python NATIVE/bin/python --case template_s5-full --cpu-budget-seconds 450
# After the measured budget and clean immutable refs are reviewed:
PYTHONPATH=BEFORE/src NATIVE/bin/python "$TOOL" run BEFORE_OUT \
  --source-root BEFORE --expect-commit BEFORE_REF --native-sha256 NATIVE_SHA \
  --python NATIVE/bin/python --cpu-budget-seconds 1350
PYTHONPATH=AFTER/src NATIVE/bin/python "$TOOL" run AFTER_OUT \
  --source-root AFTER --expect-commit AFTER_REF --native-sha256 NATIVE_SHA \
  --python NATIVE/bin/python --cpu-budget-seconds 1350
PYTHONPATH=AFTER/src NATIVE/bin/python \
  docs/superpowers/progress/connected-world-rework/performance/compare-profiles.py \
  BEFORE_OUT AFTER_OUT --out NEW_COMPARISON.json
```

Process CPU is the primary timing measure; shared-host wall time and single-run
variation remain explicit. The timing pilot can justify repeats within the
reviewed budget when a gain is borderline. Raw diagnostic runs, native builds
and checkpoints remain outside Git; compact source/measurement receipts and
commands are retained here. Workspace lifetime is not promised.
