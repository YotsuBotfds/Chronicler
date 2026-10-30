# Culture assimilation counts — unrun source candidate

`tick_cultural_assimilation` currently counts all agent rows separately for
each eligible foreign-controlled region. `AgentRows` already shares successful
column decodes, but each region still builds a whole-population equality mask
and three cultural-value comparisons. This candidate reuses count results in
the coordinated Phase10 path, without changing assimilation policy.

For one exact `AgentRows` with four equal-length, one-dimensional integer NumPy
arrays, count all valid-region rows once. Lazily count holders of each requested
target0–5 once, using a boolean OR over the three slots. Duplicate values on one
agent count once;255 and all other cultural values still contribute to that
region's denominator. Filter region IDs in their original integer dtype into
`[0,len(world.regions))` before the `intp` cast and `bincount`; a hugeuint64 or
negative ID cannot determine allocation size. Region identity remains list index.

With A agent rows, R regions, F eligible regions and K distinct demanded values,
the counting work changes from O(F×A) to O((K+1)×(A+R)+F), K≤6. This is a structural
bound, **not a measured speedup**. Histograms retain at most(K+1)×R integer
counts, plus O(A) index/mask scratch. That additional integer-index storage is
not memory neutral. Small F may pay more NumPy setup/allocation than the old
scans; neither ordinary-world wall time nor peak memory has been measured.

Counts are initialized only after the existing foreign-rule, guard, investment
flag, controller, primary-value and column-demand gates. The ratio and tuning
threshold are evaluated at their old per-region point. An empty population
still reaches the original long-stop timer. No cache survives the call or is
placed on World, AgentRows, a checkpoint or global state. Snapshot `num_rows`
is not newly read: the original vector path uses actual column lengths.

The uncached path and old scalar/vector fallback bodies remain exact, including
column-access frequency, nulls, floating/bool columns, broadcast-compatible
malformed lengths, failing shapes and private effects before an error. An
unknown primary target still requests the original arrays before skipping
arithmetic. No new validation policy or experimental/default flag is added.

Fifteen new literal cases append to `tests/test_turn_artifact_views.py`, already
on native owner1 and in the existing offline core chunk. They cover duplicate
slots/255 denominators/per-region boundaries, signed and hugeuint64 IDs, all six
targets, actual numeric-column decode sharing, unsupported/null/malformed
fallbacks, lazy target demand, empty timer and call-local re-evaluation. The
old module prefix, `tests/test_culture.py`, runner selections/owners and caps
are unchanged. New and existing checks against this source are all UNRUN.

Root proposes the existing whole culture and whole view modules under the
ordinary offline guard,110 wall/30 CPU seconds,512MiB address space and one CPU,
after source review. Controlled complete-function timing/allocation and broader
default-output/World/checkpoint/RNG/scientific comparisons remain unrun. This
candidate neither changes nor replaces the original isolated701/5122 scientific
sources, their first before-subset failure, seeds, horizons, arms or thresholds.


## Demand-deferred child, 2026-10-30 — source only

The first complete benchmark of219 retained576 calls with state/input/RNG parity,
all positive wall intervals and a clean source guard. Its registered joint
wall+CPU protocol exited2: INVALID_NONPOSITIVE_CLOCK, with44 short CPU zeros.
That attempt is preserved at/tmp/chronicler-culture-phase-benchmark-run-20261030-ysurdksl;
root completion660fe6 recorded77.065s elapsed,76.955593s CPU and167,308KiB
maximum-child RSS. These are resource observations, not a performance PASS.
Descriptive wall data showed the one-query250,000-row histogram condition about
7.25times slower, while dense256-region/six-value conditions were about5–6times
faster. The first registered verdict is not promoted and no condition is dropped.
The219 branch's109 focused cases passed, followed by all nine first Tests jobs
in run41004377008; those results do not qualify this new child.

This child keeps the exact vector scan for the first eight valid cached-integer
requests for each target value. The ninth builds regional totals once and that
value's holder histogram; later requests reuse it. Every new target pays its own
eight-query rental window even after shared totals exist. Counts are phase-local,
capped at nine per target, and limited to the existing six integer targets.
No world lookahead, persistent cache, RNG call, schema, tuning knob or feature
activation is added. Unsupported/null/malformed/legacy paths and all original
guard, column demand, private signal, threshold, timer and event ordering remain.

Eight is fixed before any successor measurement. It protects one/two/eight-query
conditions from N-sized indexing scratch; it does not claim an empirical optimal
crossover. Ninth-request construction still costs O(N+R), long demand pays eight
prior O(N) scans per target, and medium-demand regressions must remain visible.
Worst-case scratch is still O(N) plus at most seven R-sized count arrays. New
activation fixtures place decisive values at requests nine/ten, cover signed and
huge uint64 IDs, exercise all six targets over60regions, and test independent
per-target deferral, original gates, state/private/RNG parity and decode sharing.
All new-candidate tests and performance measurements are UNRUN.

Root plans a distinct wall-primary method2 for this source: the same original12
fixtures plus six preregistered uniform crossover fixtures. The first joint
negative and all44 CPU zeros remain unchanged; no old harness rerun, adaptive
calibration, threshold retuning or performance claim is authorized by this note.
