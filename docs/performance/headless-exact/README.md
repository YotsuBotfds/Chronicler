# Exact headless snapshot optimization

This lane starts at public `edf72991cad58d6670b1f382c33d50d903a6054a`, including
PR13, on isolated branch `perf/headless-exact`. Private frozen `b665e198` is outside
the experiment. No science, fishery-stock, mutual-aid, fertility-memory, Rust,
credential, or security mechanisms changed. Drive remains paused. Nothing was
pushed, merged, or promoted to the default branch.

## Change and evidence

`execute_run` already computes intelligence accuracy for each observer/target
pair immediately after the turn. Its snapshot then recomputed that same value
for military, economy and stability perception. The optimization reuses the
existing exact value within that read-only construction interval. The private
helper contains the unchanged noise body; ordinary `get_perceived_stat` calls
still compute live accuracy. Gaussian draws, seed bytes, digest byte order,
float operation order, clipping and early returns remain unchanged.

Externally supplied worlds can contain duplicate civilization names. Their
name-keyed cache entries collide, and discarded intermediate dictionary entries
can still consume RNG. A uniqueness check retains the original per-stat reads
for such worlds. A frozen public-baseline fixture verifies this edge case.

The warmed standard profile identified 3,991 `compute_accuracy` calls consuming
0.070839 seconds cumulatively. The final candidate makes 1,036 calls, a 74.0%
reduction. The six-civ profile falls from 4,889 to 1,418 calls, a 71.0% reduction.
No cache crosses a turn, mutation phase, callback, or action boundary.

The original cold CLI profile was dominated by imports and bytecode compilation;
it is diagnostic only. World/state serialization and artifact I/O remain part
of the full-run cost. Crash-recovery save frequency was preserved.

## Measured results

All values below are medians of three small observations. They are local
diagnostics without a statistical confidence interval. Profiles, RNG tracing
and tracemalloc run separately from uninstrumented timings.

| Headless execute_run workload | Public baseline | Initial candidate | Final candidate |
| --- | ---: | ---: | ---: |
| seed 321; 20 turns; 1 civ; 3 regions | 0.028671 s | 0.035091 s | 0.022088 s |
| seed 42; 60 turns; 4 civs; 12 regions | 0.366223 s | 0.439454 s | 0.341075 s |
| seed 77; 40 turns; 6 civs; 12 regions | 0.303379 s | 0.302320 s | 0.300843 s |

The initial report predates the duplicate-name fallback; the final report hashes
the final production source. Initial slowdowns are retained, not discarded.
Single-civ execution has no cross-civ perception work, so its apparent speedup
cannot be attributed to this optimization.

The final alternating before/after check uses the standard workload:

| Boundary | Baseline | Candidate | Speed ratio |
| --- | ---: | ---: | ---: |
| Accuracy cache + perception errors, 80 repeats on a fixed final world | 0.095468 s | 0.074890 s | 1.275x |
| World generation + turn loop control | 0.119962 s | 0.128571 s | 0.933x |
| Warm execute_run with artifact I/O | 0.310155 s | 0.287682 s | 1.078x |
| Fresh CLI interpreter, filesystem/bytecode primed | 0.695610 s | 0.684635 s | 1.016x |

The focused perception check excludes the rest of `TurnSnapshot` construction.
Its common benchmark scaffolding performs the uniqueness scan on both sides;
the original production path lacked that scan, so this small shared overhead
also differs from the original isolated perception task.
It supports a narrow reduction in perception work (21.6% lower final median),
not a universal simulation speedup. The earlier focused check measured 1.538x,
while its execute_run check measured 0.979x. The unchanged kernel control is
slower in the final check. Whole-run timings therefore remain mixed; neither a
general end-to-end benefit nor a kernel benefit is established.

Final tracemalloc peak deltas are -118 bytes (single), +271 bytes (standard),
and -3,422 bytes (wide). These do not establish a meaningful memory saving.
Native hybrid/agents-backed runtimes were unavailable and were not measured.

## Exact regression evidence and independent review

- All complete output files match byte-for-byte through SHA-256 and lengths:
  chronicle, world state, viewer bundle, and civilization memory files. Only
  `bundle.metadata.generated_at` is fixed by the harness to the same timestamp
  before generation; no output fields are dropped or rounded.
- All 120 turn snapshot/event/narrative hashes and ordered RNG primitive traces
  match the frozen public baseline in all three workloads. Seeds and primitive
  `Random.random`/`getrandbits` values are traced in construction order, using
  exact float hexadecimal representation. The pure-Python off path has no
  relevant module-level bound RNG alias calls.
- The full non-slow Python suite passed: **2,813 passed, 121 skipped, 9
  deselected** in 70.24 seconds. This run includes the final production code.
- After adding the duplicate-name regression, the final dedicated suite passed:
  **60 passed** in 1.50 seconds. Earlier focused production tests passed:
  **161 passed** in 2.42 seconds.
- Fresh Tier 1 reviewed the profiling method and mutation boundary. Fresh Tier 2
  independently found the helper noise body AST-identical to the public baseline,
  passed 97 existing tests and 4,392 exact numerical comparisons, and reviewed
  the duplicate fallback. Fresh Tier 3 reviewed evidence claims and transfer
  provenance. All reviewers used the fixed Sol6.1/high configuration.

Returned `RunResult` aggregates are not independently compared by the harness;
they are derived from the matching complete world/memory state. Assertions cover
actual persisted outputs and per-turn callbacks. Baseline comparisons and tests
do not claim correctness of the private science branch or unmeasured modes.

## Reproduce

Use a clean public baseline checkout and a candidate checkout; run the same
checked-in benchmark scripts with one Python interpreter and identical packages.
The JSON reports record every source-module SHA-256, Python/platform and package
versions. `paired-final.json` also records the driver-script hash and both source
revisions. Recorded candidate revision is the pre-commit HEAD; source hashes
identify the measured dirty tree and match the committed production files.

Python 3.13.5 was available locally. The public lock file does not include NumPy,
SciPy, PyArrow or arro3-core despite their declarations in `pyproject.toml`.
Preserve that lock file; install the four missing packages into the isolated
virtual environment at the recorded versions. This lane did not change it.

```bash
UV_CACHE_DIR=/tmp/chronicler-uv-cache uv sync --frozen --python 3.13
UV_CACHE_DIR=/tmp/chronicler-uv-cache uv pip install --python .venv/bin/python \
  numpy==2.5.3 scipy==1.18.1 pyarrow==25.0.1 arro3-core==0.9.0

.venv/bin/python scripts/benchmark_headless.py \
  --source-root /path/to/public-baseline --report-dir output/perf-before
.venv/bin/python scripts/benchmark_headless.py \
  --source-root /path/to/candidate --report-dir output/perf-after \
  --reference output/perf-before/report.json
.venv/bin/python scripts/benchmark_perception.py \
  --baseline-root /path/to/public-baseline --candidate-root /path/to/candidate \
  --output output/perf-paired.json
.venv/bin/python -m pytest -q -m 'not slow'
```

Both harnesses reject active native off-mode ecology/politics runtimes so their
lane cannot silently change. New report destinations must not already exist.
`comparison-final.json`'s `passed` means exact equivalence and matched package
environment; it deliberately contains no performance threshold.

Full raw profiles, traces, and artifact bytes remain locally under
`output/performance/`; tracked JSON reports, fixtures, test logs and reviews
support transfer. Failed initial probes are retained there: an incorrect
`chronicler` module invocation and a requested 24-region workload rejected by the
public generator's 12-template limit. They are excluded from result tables.
