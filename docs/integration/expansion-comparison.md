# Compare expansion experiment evidence

```sh
python scripts/compare_system_expansion.py path/to/forecast-study path/to/gathering-study path/to/health-study --json reports/comparison.json --markdown reports/comparison.md
```

Inputs are explicit bundle files or directories searched for
`chronicle_bundle.json`. `compare_paths` in `chronicler.expansion_compare` is
the reusable API. It reads each bundle once, hashes those bytes, uses the shared
v6/legacy decoder, and reads only the adjacent `worker_identity.json` companion.
It never follows paths embedded in experiment receipts or loads native code,
checkpoints, simulation or an LLM. Report paths cannot overwrite any source
bundle/worker receipt, including aliases. Source directories and runtime state
remain untouched.

The catalog discloses exact source commit, Python-package digest, native binary
SHA, bundle SHA, worker-receipt SHA, checkpoint SHA/seed/turn/exactness, parent
feature flags, recorded environment, before/after controls, cohort, registration
SHA and intervention boundary. Machine-local source/module/checkpoint paths are
omitted. Worker before/after identities must match the bundle receipt. These are
recorded producer assertions, not cryptographic authentication of a producer.
Actual worker environments are captured at `before.environment` and
`after.environment` and must be stable; paired arms must match those measured
environments. The parent checkpoint environment is disclosed separately and
never fills an unrecorded worker environment. Parent orchestration settings may
legitimately differ. An optional declared runtime environment must agree with
the measured one. Optional external runner hashes are disclosed and matched
when present on both sides; a captured before/after runner hash must remain stable.
Both checkpoint-header and batch-worker environment formats are supported.
When the worker format records `PYTHONHASHSEED` only inside its captured thread
environment, that actual captured value supplies the normalized hash-seed field.
Public platform/CPU counts remain explicit. An executable path is represented
by a hash of its text, without following or exposing the path; this is not a
hash of the executable binary.

Supported systems are harvest assessments, local harvest gatherings,
temporary work impairment/care and [institutional science receipts](scientific-receipts-audit.md).
Unsupported features are catalogued with explicit blockers.
Canonical arm labels are checked against their recorded controls, so an
arm called `no_contact` with contact enabled cannot silently pass. Care contrasts
also require the injury rate, impairment, care allocation fraction and ordinary
recovery-work setting to match.

Every matched contrast requires one unambiguous baseline and alternative for
the same feature, experiment, cohort and seed. Baselines default to `normal`
for forecasts/gatherings/science and `care` for health (`--baseline` selects another
recorded arm). Pairs must agree on source/package/native identities, checkpoint,
flags, actual worker environments, registration, pre-intervention controls, end horizon and
canonical historical/event prefix before treatment. A fresh parent remains in
the catalog, but is not silently treated as an intervention arm.

Quantities come only from snapshots describing completed turns in
`[applied_before_turn, total_turns)`. Parent history remains excluded from
treatment totals. Every turn of that window must have a valid dated section for
the compared feature. The full recorded bundle is also checked by the
[expansion audit](expansion-audit.md). Invariant errors, scan truncation, missing
worker identity, mismatched provenance, ambiguous arm assignments or incomplete
windows block numerical differences. Warnings/unavailable checks remain visible.
An unknown metric stays `null`; it never becomes zero in a subtraction.

Health metrics are episode-turns, new onsets, episode retirement/censor counts
and work/care time, without clinical interpretation. Gathering metrics describe
actual recorded occurrence/attendance/cost/contact/bond-attempt receipts.
Forecast metrics distinguish reports observed during the window from new
issuances, actual deliveries, closures and scores **dated inside** the window.
Pre-existing reports remain visible as pre-existing. Preparation quantities are
the actual recorded purchases during warnings; a mean Brier score is descriptive
and discloses its score count. Different reported score cohorts are not treated
as matched individual forecasts or evidence of calibrated skill.

For a fork whose controls did not change, the tool can compare the final
exported Python world hash with its single fresh parent's hash. A true result is
limited to that serialized Python state. It does not establish native pool,
RNG-state or all-file identity. Missing state yields an unknown result.

The output is deliberately descriptive. Seed IDs and cohorts remain explicit;
turns, regions, attendees, reports and different contrasts from the same seed
are not independent replications. No p-values, efficacy promotion, clinical
benefits, avoided deaths, successful friendship formation or attributable excess
spending are inferred. Development cohorts cannot become confirmatory evidence
through this report. Registration hashes identify records; they do not assess
preregistration quality or prove a held-out cohort.

Default discovery is bounded at 64 runs (absolute cap 512). Each sequential
bundle read inherits the audit byte/snapshot/event/receipt limits; history is
bounded before delta expansion. Only compact catalog/metric records are retained
between inputs. Exceeding discovery bounds aborts rather than returning an
apparently complete subset. Per-bundle truncation is an explicit pairing blocker.
Both Markdown and JSON contain the provenance and coverage disclosures. Exit 0
means all discovered contrasts met the **recorded-window** prerequisites; it is
not scientific qualification. Exit 1 indicates blocked/unpaired evidence, and
exit 2 indicates an input/output error.

On the original two-seed, 40-turn development studies from source `527a9ff8`,
the initial draft read 24 actual bundles and found 12 candidate contrasts.
Review then found that those older worker receipts captured only source/native
identities, without independent before/after environment capture. The strict
comparison now reports that environment as **unrecorded**, rather than copying
the parent header or treating it as an observed mismatch. Numerical treatment
deltas remain blocked; descriptive post-fork metrics stay available. The
seed-43 shuffled forecast arm additionally carries its historical negative
target increment. All six recorded no-op forks matched their parents' final
exported Python worlds, within that limited equality scope. The catalog
contained only development seeds 42 and 43. These are development workflow
checks, not a powered study or a feature gate.

Final focused verification passed 32 tests under Python 3.13.5 with native
imports, network and subprocesses blocked (zero attempts). Re-reading the old
24 bundles with the completed guards preserved all post-fork catalogs and six
Python-world equalities, and blocked all 12 strict contrasts because actual
worker environments were unrecorded. The negative-target arm retained its
additional integrity blocker. Original artifacts were not modified.
At that tooling checkpoint, an actual schema-2 worker receipt from the later frozen-source natural study
was also read successfully: source/native, measured environments and runner
hashes were recognized, while its unsupported scientific-claims feature remained
blocked rather than being interpreted as one of the three then-supported systems.
The subsequent science extension checks all four science controls, including
the legacy-default versus explicit funded-context publication rule, and current
summary controls against the actual treatment receipt. It separates new
funding/counter changes from later resolution-attached historical costs and
never reconstructs an omitted receipt archive from final world state.
