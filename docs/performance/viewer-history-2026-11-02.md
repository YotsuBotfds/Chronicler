# Measured history interaction work, 2026-11-02

The retained change reuses one `Intl.NumberFormat` for What changed table
cells and caches event selection-key counts in the existing array-identity
`bundleIndex`. Repeated history interactions no longer build the same collision
map or initialize the same locale formatter for each cell. Duplicate selection
keys remain ambiguous, including legacy fallback keys. The existing index
contract is unchanged: new event arrays get a new index; an in-place length
change invalidates it; old arrays and their maps can be collected.

This is a narrow reduction in measured script work. It is not evidence of a
faster whole viewer, faster file loading, faster completed-run comparison or
faster native simulation. The more visible remaining cost is chart rendering
and layout. No chart, snapshot, calculation, ordering, event clock, source
contract or missing-value behavior changed.

## Real input and source

The input is the preserved native simulate-only checkpoint-matrix run
`proc32_hybrid_s42_recycling/straight/chronicle_bundle.json` under
`/workspace/shared/chronicler-lead-evidence/checkpoint-matrix-final`:

- 10,848,941 bytes; bundle 6; seed 42; 200 recorded turns; 32 regions;
  10 lifetime civilization records; 12,450 exported events.
- SHA-256 `1f6ee94b2ea6b1e6a5338669eb84197dc05d175d936bf633e758a8daf25b0ebd`.
- The producing environment receipt records source
  `32ac587908b28167e45ff105f62ace988fbb8e12` and native binary SHA-256
  `f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
  This older real bundle lacks the new regional-population observation. It
  measures historical-bundle behavior, not a large current-observation run.
- UI parent: `cb4c9f5cb108aa0b1f6e0cbf53035efb61d332e0`.
- Final integrated acceptance baseline:
  `02545111324dfa757e91ebca6fcba6ec29ee2f25`; candidate is that exact tree plus
  the four-file retained performance patch. It was built in a separate detached
  worktree, without rebuilding or editing the shared root checkout.

External evidence is under
`/workspace/shared/chronicler-world-lab-evidence/viewer/performance/`.
`inputs.json`, `receipt.json`, `candidate-indexed.patch`, the build asset SHA-256
manifests and the final source-file hashes retain the input and build identities.
The implementation commit identity is recorded there after committing.

## Method and environment

Node 20.19.0; existing shared dependencies (Playwright 1.64.1, Vite 7.3.7);
headless system Chromium 154.0.8037.57 on Linux x86_64, Intel Xeon Platinum
8573C, five visible logical CPUs, four-CPU cgroup quota and 16 GiB memory limit.
No CPU throttling was applied. The browser viewport was 1920 × 1200.
No dependencies, lockfiles or simulation outputs were changed or generated.

The existing `viewer/scripts/perf-viewer.mjs` and
`viewer/scripts/viewer-equivalence.mjs` were used through external copies.
Both copies select `input[aria-label="Open saved world file"]`; the historical
`accept=".json"` selector now addresses the separate resume-state input. Both
copies explicitly launch `/usr/bin/chromium` with `--no-sandbox`. An initial
wrong-selector attempt was stopped before producing a measurement receipt.

The performance copy extends the existing sample with history opening, twenty
consecutive timeline seeks while history is open (turns 81–100), twelve
alternating soil/water metric selections, completed-run comparison opening and
file loading, and twelve alternating comparison endpoints. It uses the same
MutationObserver, forced-layout and next-frame timing method as the existing
scrub tool, with CDP CPU profiles for inspection. This external instrumentation
is not a new product profiling subsystem. `perf-viewer-inspection.mjs` and raw
profiles are retained with the evidence.

A separate initial baseline used thirty consecutive and thirty random overview
seeks, plus ten of each campaign and pinned-event pattern. Three fresh-context
loads had median 587.4 ms to the overview frame and 10 ms main-thread blocking;
overview consecutive script median was 8.95 ms. There were no browser errors.
The worker's existing decoding behavior was preserved.

The final integrated comparison used three rounds, alternating build order:
root/candidate, candidate/root, root/candidate. Browser samples ran serially,
without concurrent checks in this final lane. Initial profiling found repeated
event-key counting and number formatting among the leading named history
application costs; chart/layout work was larger overall.

## Final integrated measurements

Values are the median of the three per-run medians; parentheses give the range
of those medians, in milliseconds. Each inspector-scrub run has twenty steps;
each metric/comparison-endpoint run has twelve. Raw samples, profiles and
console messages are in `paired-root.json`; `root-summary.json` preserves each
run separately. Every one of the six browser runs had zero recorded errors.

| Interaction / measure | Root | Candidate |
| --- | ---: | ---: |
| Inspector-open timeline, script | 22.15 (18.90–23.60) | 16.60 (15.20–22.75) |
| Inspector-open timeline, frame | 52.60 (50.95–61.10) | 52.95 (52.45–68.55) |
| Region metric selection, script | 27.15 (25.70–28.50) | 25.70 (22.80–29.05) |
| Region metric selection, frame | 31.55 (30.15–33.40) | 30.35 (26.65–33.35) |
| Completed-comparison endpoint, script | 51.75 (45.30–62.25) | 60.95 (48.70–61.15) |
| Completed-comparison file load, frame | 298.60 (288.80–301.20) | 380.80 (292.10–435.80) |
| Saved-world overview load, frame | 549.80 (511.90–577.60) | 621.70 (558.70–622.80) |

The targeted history script median was about 25% lower, with overlapping ranges
and no frame-time gain. Other paths were variable and several candidate
measurements were slower. The retained code does not alter those decoding or
completed-comparison paths; these samples establish no improvement there and
must not be reported as a general performance win. The accepted scope is the
smaller repeated history script work only.

A first candidate extracting memo boundaries around the plot and turn
comparison showed no improvement (script medians 15.1 → 22.6 ms for history
scrubbing, 24.6 → 24.55 ms for metric changes). It was fully discarded. Its
external `paired-history.json` negative is retained. A preliminary indexed
candidate showed a larger benefit, but its first round overlapped focused
checks, so only the clean integrated lane above is acceptance evidence.

## Equivalence and checks

The existing rendered-DOM equivalence tool compared the retained optimization
against its UI parent on the same real bundle and the older, unversioned
`sample_bundle.json`. It compared 99 captures in 30 states (9.4 MB of DOM per
build) for the real run and 34 captures in nine states (0.7 MB) for the older
file: zero differences, zero console messages. States include overview,
systems, layers, event pinning, region selections, other surfaces and region
history. Worker decoding occurred for the real file; the older small file
used the main-thread path in both builds. This equivalence result is separate
from the later root integration's broader UI changes.

Affected checks passed: the existing five-file lane (189 tests), followed by
the index lane including the new ambiguity/append/replacement regression
(169 tests; 190 distinct affected tests across both runs), TypeScript, changed
file lint and production builds. `git diff --check` passed. Root owns the final
combined full viewer and UI checks; this lane supplies no Python/native or
scientific qualification.

The root shell recreates its event-selection callback on render. The retained
optimization does not rely on callback identity or a memoized inspector. Live
updates still replace event arrays and invalidate indexes; no live-session
speedup is claimed from this saved-run measurement.
