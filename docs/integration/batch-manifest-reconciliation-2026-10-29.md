# Batch cohort identity reconciliation — 2026-10-29

This isolated review branch starts from sidecar-inventory repair
`e984be2adc2e6fdf27b4442b852a9e6789b6617b`. That frozen source and its running
CI qualification remain unchanged. This follow-up corrects validation
admission only: simulation physics, exporters, scientific methods, thresholds
and default configuration are unchanged.

## Reproduced problem

The verifier formerly accepted `runs=[null]`, 200 declared seeds and a 500-turn
horizon with no bundles. Its report advertised `verified (200 runs x 500 turns)`.
It also accepted a hashed 20-turn bundle as a 500-turn run when the manifest's
recorded total was changed, and a cohort declared as seeds 7/8 whose actual
bundles both recorded seed 7. The comparator trusted the declared verified
cohort while oracle readers used the differing payload metadata.

Duplicate bundle entries were silently collapsed; declared seeds and run
directories were not reconciled. Extra file hashes could reference another
run, a parent path or an absolute path. Two bundle paths could alias the same
physical file and produce a tautological determinism PASS.

## Correction and compatibility

Structural preflight requires nonempty record rows, exact ordered seed facts,
nonnegative integer horizons with booleans excluded, unique canonical run and
bundle paths, and run-scoped validation-input inventories. Directory/bundle
paths must agree and remain inside the batch. Symlinked or physically aliased
bundles are refused. Hashes still bind every actual validation input, including
the sidecars covered by the preceding e984 repair.

Actual bundle metadata seed/total-turn facts must match each recorded run.
The terminal world turn, when present, must agree too. Direct public verifier
and manifest-check APIs perform complete verification; structural preflight
alone never emits a verified cohort.

Normal oracle paths carry a small immutable expectation map and observation
set through their existing per-bundle decode. Every expected payload must be
observed before the final verified summary. This adds no second large-bundle
parse to the normal oracle reader; standalone manifest verification reads
bundles one at a time. Empty oracle selections still inspect their payloads.
Malformed or duplicate-key JSON in manifested bundles becomes a validation
request error. Legacy standalone loading retains its existing behavior and
explicit `--legacy-batch` admission remains unchecked. A present malformed
manifest cannot use that flag as a bypass.

Repeated seeds remain supported in distinct genuine files: the established
determinism design registers `[42,42]` in separate directories. The correction
does not change statistical independence policy or scientific acceptance
rules. The facade's custom determinism-runner signature is preserved.

## Validation

All tests use synthetic files and pure reader paths; no worlds, native builds
or optional native imports ran. The 52 new cases run against frozen e984 give
**40 failures and 12 passes**. Those expected baseline failures remain saved.
The correction passes **231 guarded tests**, comprising the new cases, the
original sidecar-inventory regressions, validation CLI/oracles, turn-index and
split-import tests. The guard records no native import attempt, no blocked IO
and zero ecology/politics factory calls.

Coverage includes zero-world/invented cohorts, typed horizons and actual
payload identity, external/cross-run hashes, symlink/hardlink aliases, rejected
last payload before scientific-oracle invocation, empty selections, strict
JSON failures and version-6 decoding. A valid ordinary reader decodes each
bundle once. Genuine repeated-seed determinism passes with its original two
index reads plus two comparison reads. Valid cohort summaries retain their
exact values. The new pure file joins the existing bounded validation-tooling
chunk without changing its 110-second limit or guard permissions.

The original 22-probe audit tree was rechecked read-only: its valid control
still verifies and all 21 inconsistent fixtures are rejected. All 69 original
evidence files were rehashed before/after unchanged. The audit's first external
driver formatting error, corrected separate attempt, original accepted results
and raw fixtures remain retained. No original failure was overwritten.

External records are under `batch-structural-audit-20261029` and
`batch-reconciliation-validation-20261029`. Full combined offline/CI and source
review remain separate qualification steps. Main and the recovered producer
branch are unchanged; this record claims no simulation performance gain.
