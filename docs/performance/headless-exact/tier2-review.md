# Tier 2 independent regression review

Reviewed public baseline `edf72991cad58d6670b1f382c33d50d903a6054a` against the candidate working tree on 2026-10-05. The private `b665e198` branch was outside this review. No implementation files were edited and no performance workload was run concurrently with the primary benchmark.

## Recommendation

Approve the narrow optimization for regression safety. No blocking semantic or precision regression was found in the supported, single-threaded snapshot path. Keep the performance conclusion scoped: the initial complete benchmark proves exact equivalence and fewer repeated accuracy computations, but does **not** establish an overall wall-clock improvement. The primary agent's paired timing follow-up remains separate evidence to assess.

## Exact arithmetic and RNG audit

- `src/chronicler/intelligence.py:119` keeps the public wrapper's signature and recomputes `compute_accuracy` on every call. Its newly extracted helper does not store or round accuracy.
- The helper's executable noise body is AST-identical to the baseline body after its accuracy assignment. Floating-point accumulation remains in the unchanged `compute_accuracy`; the helper retains `int((1.0 - accuracy) * 20)`, division by two, Gaussian draw, integer truncation, clipping, and bounds in their original order. Exact knowledge still returns the raw stat before bounds, preserving the prior behavior.
- SHA-256 seed input, digest slicing, byte order, and `random.Random(seed_int)` construction are unchanged. The snapshot comprehensions preserve observer/target/stat iteration and their positive-accuracy filter. Removing accuracy recomputation removes no RNG calls: its relationship/faction/person/grudge reads are deterministic.
- Independent diagnostic: **4,392 exact baseline/helper comparisons** over **61 float values**, including neighboring `math.nextafter` values around all 0.05 accuracy boundaries and attainable bonus sums; three seed/turn combinations; four stat names; zero, near-bound, and high actual values; and default/custom upper bounds. All matched; the module global RNG state was unchanged. The original addition order intentionally produces values such as `0.7999999999999999`; comparisons retained those exact values.

## Cache lifetime and mutation audit

`src/chronicler/main.py:350` computes the existing local pair cache immediately after `run_turn`. `main.py:437` consumes it while constructing the same `TurnSnapshot`. The intervening expressions copy/read model fields, dump models, and call the pure climate-phase function. Neither snapshot model has a mutation validator. Turn callbacks and subsequent simulation work happen after construction. No ordinary accuracy input can change between these two sites in this path.

The trade-route read can populate an existing transient route cache during the first accuracy computation; repeated reads return the same graph. This side effect already occurred in the baseline's initial pair-cache construction. The optimization neither changes route invalidation nor extends an accuracy cache into actions, injection processing, later turns, narration, or callbacks.

An independent live-wrapper diagnostic changed actual world war, dominant faction, federation, and vassal inputs between reads. Accuracy advanced through `0.0`, `0.3`, `0.4`, `0.7999999999999999`, and `1.0`; every wrapper read recomputed and matched the baseline implementation. Future callers of the private helper must respect its documented read-only boundary. Moving it into mutation-heavy simulation code would require a fresh audit.

## Executed checks and benchmark evidence

Executed `.venv/bin/python -m pytest tests/test_intelligence.py tests/test_main.py -q`: **97 passed in 1.28 s**.

Independently read `before-complete/report.json`, `after/report.json`, and `after/comparison.json`. The baseline revision is the public commit above; source hashes differ only for `main.py` and `intelligence.py`; recorded interpreter/dependency environments match. All output artifact hashes/lengths, all **120** turn snapshot/event/narrative hashes, and ordered primitive RNG traces match for:

| Workload | Configuration | Baseline median | Candidate median |
| --- | --- | ---: | ---: |
| single | seed 321, 20 turns, 1 civ, 3 regions | 0.028671 s | 0.035091 s |
| standard | seed 42, 60 turns, 4 civs, 12 regions | 0.366223 s | 0.439454 s |
| wide | seed 77, 40 turns, 6 civs, 12 regions | 0.303379 s | 0.302320 s |

Profile totals improve for standard (0.776993 to 0.694885 s) and wide (0.637149 to 0.589350 s), but profile instrumentation is separate from wall-clock measurements. Peak tracemalloc deltas are only -118, -4,331, and -236 bytes; no meaningful memory reduction is established.

## Coverage limits and nonblocking observations

- `benchmark_headless.py:164` defines comparison `passed` as environment/output/RNG equivalence. It has no speed threshold. Treat this as an equivalence pass, not a performance acceptance result.
- Measurements cover pure-Python agents-off execution, warmed imports, world generation, snapshots, and artifact I/O. They exclude paid narration, native runtimes, interactive/live mode, resume/injection scenarios, and CLI startup. No speed or mode-wide claim for those paths follows from these reports.
- Ordered tracing covers `Random.seed`, `random`, and `getrandbits` and preserves the class's existing `_randbelow` selection; hexadecimal float recording preserves primitive results. Module-level bound RNG aliases are not independently intercepted. The only module-level draw found in source is in the excluded live mode; the changed code uses explicit `Random` instances.
- The pre-existing `TestSnapshotPopulation` reconstructs snapshot dictionaries rather than invoking the modified production construction. The complete benchmark's actual `execute_run` equivalence covers this gap for the three workloads. Newly added `tests/test_performance_equivalence.py` also exercises actual execution, baseline fixtures, arithmetic boundaries, and fresh wrapper reads; those new tests were inspected, but their execution is left to the primary agent's validation.
- Three unpaired repetitions are too little evidence to attribute the initial standard/single slowdown to the implementation. Conversely, fewer accuracy calls or improved instrumented profile totals alone cannot justify an end-to-end speed claim. Preserve the observed medians and assess the paired follow-up separately.

No remaining blocker for the scoped regression-safety recommendation.

## Follow-up: duplicate-name compatibility correction

The primary agent subsequently identified an edge case outside the original generated-world workloads: externally supplied `WorldState` objects can contain multiple civilizations with the same name. The existing name-keyed `_acc_cache` then holds only the last observer's accuracy for that name. The original snapshot still performed live per-stat reads for each observer, including computations subsequently discarded when duplicate dictionary keys were overwritten. Reusing the collided cache could change those discarded reads and their local RNG construction/draw order even when final serialized dictionaries matched.

A concrete case is two observers named `A`, one with military-dominant factions and no contact accuracy, another with merchant-dominant factions and positive accuracy toward `B`. When the latter occurs last, the shared cache entry is positive. Both observers pass the existing snapshot filter, but the baseline first observer returns `None` without constructing a noise RNG. The initial optimization would have applied the latter observer's accuracy to both and introduced extra RNG calls.

Reviewed the correction against `edf7299`: `main.py` now computes `_unique_civ_names` once per snapshot and, when names collide, calls the unchanged `compute_accuracy(obs, tgt, world)` separately for each original per-stat read before invoking the identical noise helper. The existing pair-cache construction, positive-accuracy filter, and observer/target/stat iteration order remain unchanged. This restores even discarded computations' RNG behavior without changing the baseline's duplicate-key output semantics. With distinct names, the fast path still consumes the existing exact cache. The uniqueness set itself reads model string names and makes no RNG calls or world mutations.

**Static verdict:** the fallback addresses the identified duplicate-name regression, and regression-safety approval applies to the revised implementation. This is a compatibility correction, not a claim that name collisions were impossible. The original benchmark tables above describe the earlier candidate. A frozen public-baseline duplicate-world fixture, complete suite execution, and refreshed candidate benchmark are being handled by the primary agent; no tests or workloads were run by this reviewer during that work. Final acceptance should use those refreshed results, including the slight uniqueness-check overhead in valid worlds.
