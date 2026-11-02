# Completed-comparison frame response, 2026-11-02

Memoizing the completed-comparison trajectory component prevents four unchanged
Recharts trees from rendering again when the endpoint selection changes. The
existing aligned point array and metric are the memo inputs. Loading either run
or choosing another financial metric still updates the affected chart. All
samples, extrema, null gaps, dots, axes, tooltips and exact endpoint tables keep
their existing calculations and markup. No aggregation or downsampling is used.

## Bottleneck and rejected work

Before implementing the candidate, a private production build at `9de396fb`
showed repeated Recharts dot/line prop processing and selectors among the largest
comparison CPU-profile costs. One diagnostic run measured endpoint script
61.8 ms, commit 66.0 ms and frame 69.9 ms (medians of twelve changes). Its
inspection rendering trace includes 402.8 ms of Layout and 590.1 ms of PrePaint
across history opening, twenty seeks, twelve metric choices, comparison loading
and twelve endpoints. Trace overhead makes these diagnostic figures separate
from acceptance below.

The [earlier history work](viewer-history-2026-11-02.md) retains its rejected
history-memo candidate and its accepted scripting-only optimization, which did
not improve frames. Neither is reclassified as a frame win. This slice targets
the measured completed-comparison chart rerenders and makes no history-scrub,
file-loading, whole-viewer or simulation speed claim.

## Same-source paired measurement

The integrated UI baseline is `27e199f9`, whose tree equals root `c1ed5d35`
(`9de396fb` plus frozen C14/C18 changes). Candidate differs only in the memo
boundary. Existing shared dependencies, Node 20.19.0 and headless system Chromium
154.0.8037.57 were used on Linux, with a 1920 × 1200 viewport and no CPU
throttling. Private static servers use allocated ports, separate from root QA.

The existing `viewer/scripts/perf-viewer.mjs` was reused through an external
inspection copy: MutationObserver script timing, forced-layout commit, and the
next frame followed by a MessageChannel task. CPU profiles run equally for both
builds; acceptance has no rendering trace. Three rounds alternate build order
(A/B, B/A, A/B), with twenty history seeks, twelve metric changes and twelve
comparison endpoints per sample. Other workers held CPU-heavy checks during
measurement; no otherwise-idle-host qualification is inferred.

Values are medians of three per-run medians, with their min–max ranges, in ms:

| Comparison endpoint | Baseline | Memo |
| --- | ---: | ---: |
| Legacy 200-turn world, script | 51.75 (48.30–68.10) | 4.00 (3.55–4.45) |
| Legacy 200-turn world, frame | 58.80 (55.20–75.25) | 25.60 (25.05–29.50) |
| Current 160-turn world, script | 61.30 (54.55–76.10) | 4.25 (4.20–6.00) |
| Current 160-turn world, frame | 68.95 (62.15–83.20) | 26.55 (26.35–32.95) |

All twelve browser runs recorded zero errors. History-scrub frame medians were
49.40 → 49.95 ms on the older world and 77.85 → 82.60 ms on the current world;
this change does not resolve that remaining path. The demonstrated endpoint
benefit requires no chart aggregation, so the exact representation is retained.

Inputs are read-only real simulate-only procedural worlds (seed 42, 32 regions):

- Older checkpoint-matrix world: 200 turns, 10 lifetime civilizations,
  10,848,941 bytes, SHA-256
  `1f6ee94b2ea6b1e6a5338669eb84197dc05d175d936bf633e758a8daf25b0ebd`.
  It lacks current regional-population observations.
- Current world: 160 turns, eight civilizations, 19,052,995 bytes, SHA-256
  `db4a33e351cb032d9426bcb2373ef9ccca944fa85432bd495e919a8b57c946cb`.
  Its producer source is `59d1de84`; exact 80→160 continuation qualification
  remains the separate long-run worker's evidence.

Private input identities, build hashes, raw timings, profiles, trace and reused
harness copies are under
`/workspace/shared/chronicler-multiwave-evidence/frame-performance/`.
`paired-memo.json` and its summary retain every acceptance sample. The source
change does not alter simulation, RNG, defaults, dependencies or native builds.

The root's four pending accessibility-wrapper changes were then applied
identically to both builds. One additional bounded round confirmed endpoint
frame 55.30 → 29.80 ms (older world) and 59.75 → 24.45 ms (current world), with
zero errors in four runs. `root-accessibility-wrappers.patch` and
`paired-wrappers.json` preserve that exact overlay and confirmation; it is not
substituted for the three-round acceptance series.

## Equivalence and checks

The reused rendered-DOM equivalence script was extended externally to capture
comparison endpoints and every additional trajectory choice. It found zero
differences and zero console messages on both real worlds and the older
unversioned `sample_bundle.json`: 104, 110 and 43 captures respectively (32,
34 and 12 states; 12.0, 13.9 and 1.3 MB of DOM per build). Exact tables, source
paths, unknown observations and chart SVG geometry were compared together.
The existing completed-run library tests retain gap/tail, duplicate-turn,
true-zero and older missing-value coverage; no metric reader changed.

Full viewer verification passed 101 test files / 1,097 tests, full lint and
TypeScript plus Vite production builds on Node 20.19.0. The existing large-chunk
build warning remains. Functional browser equivalence and tests ran after the
quiet timing window. These checks cover this viewer slice, not later recipe
contract fixes or broader scientific/native qualification.
