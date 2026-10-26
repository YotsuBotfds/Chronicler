# Validation integrity (2026-10)

Branch `fix/validation-integrity` from `main` `fc01d6e` (PR #44), merged
without rebase with `b8f0243` (PR #45, historical parity) at `c1ce58a`.
Validation tooling only: the needs oracle, batch directories and their manifests, the
report comparator, two small fixes, the lockfile and CI. Simulation output
is byte-identical to `main` ([Identity](#6-identity)); the only new file in a
batch directory is `batch_manifest.json`.

An external review reported four groups of defects. Each was reproduced on
`fc01d6e` before it was fixed:

| Finding | Reproduced on `fc01d6e` |
| --- | --- |
| 1. The needs oracle counts actions of the snapshot turn | Yes: two seeds whose only actions fall on the snapshot turn PASS the full profile (pooled bound +1.0, binding bound +1.0); without them FAIL |
| 2. A reused batch directory mixes runs | Yes: seeds 42-44, then seed 42 alone into the same `--output`: the validator loads 42, 43 and 44 |
| 3. The comparator does not check cohorts | Yes: a 200 x 500 report against a 20 x 200 report: NO REGRESSION |
| 4a. `--seed 0` runs seed 42 | Yes: `batch_42/seed_42` |
| 4b. `uv lock --check` fails | Yes: the lock lacked numpy, scipy, pyarrow, arro3-core and the `gemini` extra |
| 4c. No viewer CI job | Yes |

## 1. Needs oracle method 4

### The defect

The sidecar snapshot of turn t is written at the end of turn t's agent
processing (`agent_bridge.py`, after `tick` and the event conversion). In
the native tick (`tick.rs`) needs are updated (step 0.75) before the
decisions, and the apply step then moves migrants (`set_region`), switches
occupations and adds 0.10 to a rebel's autonomy. So the turn-t snapshot
observes the matching cell (region, occupation, civ affinity) and, for
rebels, the need after turn t's actions. Methods 2 and 3 counted outcomes on
turns t .. t+19, so a turn-t migrant was matched in its new region and its
migration counted as an outcome of a reading taken after it.

### The fix

Method 4 (`NEEDS_ORACLE_METHOD_VERSION = 4`) keeps method 3's matching,
pairs, criteria and profiles and counts outcomes strictly after the
snapshot: turns t+1 .. t+20. A run of N turns ticks turns 0 .. N-1 (events
of turns 0 .. N-1, a post-loop snapshot at N), so a snapshot is eligible
when t + 20 < N: 0 .. 470 of a 500-turn run (method 3: 0 .. 480), 0 .. 170
of a 200-turn run.

Capturing the predictors before the decisions would change the sidecar
writer inside the native tick and the bundle; counting after the snapshot
needs only the oracle and keeps every sidecar and report readable.

**Prior rebels.** The autonomy pairing already left out agents whose first
rebellion falls on or before the snapshot turn, so a turn-t rebel (whose
autonomy carries the +0.10) is a prior rebel under both methods. Method 4
makes the other pairings consistent with it: an action of turn t precedes
the reading. A first rebellion on turn t+1 is an outcome
(`test_needs_oracle_same_turn_rebels_are_prior_rebels`).

**Results and compatibility.** Method 4 results have `method_version: 4`
and `outcome_window_start_offset: 1`; method 2 and 3 results keep their
bytes. `run_needs_oracle(..., method_version=3)` re-scores method 3 exactly
(the re-score of the template subset below equals the turn-speed report's
method 3 result field for field), `method_version=2` or
`require_binding=False` method 2. The comparator reads the method version
and reports a 3 against 4 change as `rebaseline_required`, never as a new
or resolved failure. The binding component is required in the full profile
only (`validation_gate.NEEDS_BINDING_REQUIRED_PROFILES`, unchanged). No
threshold changed.

**Not changed.** The cohort oracle has the same convention (its window
starts at the graph and needs snapshot turn, `run_cohort_oracle`); it was
not part of the review and is left as is.

### Method 3 against method 4 on the retained sidecars

Every retained needs sidecar set on this machine was re-scored with both
methods (oracle code only, no new runs): 48 sets, the needs-followups full
gate's 200 x 500 sidecars, its 33 subsets and the needs-oracle-power
branch's 14 sets (its five `final-*` sets repeat their namesakes exactly).
A `perf` batch whose events end at turn 164 (interrupted, no bundles) was
left out. Columns: pooled net concordance
(one-sided 95% lower bound), seeds with C > D of 20 (or 200); the binding
pairs' net (lower bound), informative pairs; the gate's needs verdict for
the subset profile and with full-profile rules.

The full gate's sidecars (needs-followups head `d44cf4f`, 200 x 500):

| Method | Pooled | Binding | Subset | Full |
| --- | --- | --- | --- | --- |
| 3 | +0.222 (+0.204), 176 / 200, 9,902 informative | +0.192 (+0.168), 5,060 | PASS | PASS |
| 4 | +0.209 (+0.190), 175 / 200, 9,605 informative | +0.185 (+0.160), 4,892 | PASS | PASS |

Per pairing (method 3 -> 4, pooled): material +0.285 -> +0.255, social
+0.150 -> +0.165, autonomy +0.346 -> +0.343, purpose +0.051 -> +0.054,
safety +0.119 -> +0.098. Material falls most: its turn-t migrations, matched
in the region the mover had just entered, were on balance concordant.

Verdicts that change between the methods, of 48 sets:

| Set (20 x 200) | Pooled 3 -> 4 | Binding 3 -> 4 | Verdict 3 -> 4 |
| --- | --- | --- | --- |
| needs-followups `needsoff-base-42` (terms zeroed) | +0.097 (+0.021), 11 -> +0.101 (+0.022), 13 | -0.026 (-0.126) -> +0.005 (-0.092) | subset FAIL -> **PASS** |
| `needsoff-base2-42` (main `2ef3097`, terms zeroed) | +0.096 (-0.000), 14 -> +0.103 (+0.003), 12 | +0.029 (-0.086) -> +0.082 (-0.024) | subset FAIL -> **PASS** |
| `hunger-mid-42` (not shipped) | +0.144 (+0.046), 13 -> +0.147 (+0.037), 11 | +0.122 (-0.026) -> +0.146 (-0.002) | subset PASS -> FAIL |
| `base-82` (`f5425dc`) | +0.193 (+0.107), 16 -> +0.181 (+0.089), 15 | +0.164 (+0.041) -> +0.117 (-0.006) | full rules PASS -> FAIL |
| `head-82` (`89f3d67`) | +0.154 (+0.036), 14 -> +0.128 (+0.021), 14 | +0.174 (+0.015) -> +0.148 (-0.005) | full rules PASS -> FAIL |
| `needsoff-head-62` (terms zeroed) | +0.203 (+0.125), 15 -> +0.208 (+0.130), 14 | +0.156 (-0.015) -> +0.171 (+0.021) | full rules FAIL -> **PASS** |

Every other set keeps both verdicts. Over the 48 sets the median change is
-0.0002 in the pooled net and -0.016 in the binding net. Every set is in
the [appendix](#appendix-every-re-scored-set).

So method 4 passes the retained full gate as method 3 did, with margins a
little smaller. At subset scale it moves sets that sat at a bound in both
directions; two terms-zeroed subsets now pass the subset profile (method 2's
pooled criteria, which never separated the terms at subset scale:
`needs-followups.md` §1), and one terms-zeroed subset passes full-profile
rules (its binding bound +0.021). Counted over the sets:

| Sets (20 x 200) | Full-profile rules PASS, method 3 -> 4 | Subset profile PASS, method 3 -> 4 |
| --- | --- | --- |
| 18 with the need terms zeroed (needs-followups 15, needs-oracle-power 3) | 2 -> 3 | 15 -> 17 |
| 15 with the terms on (needs-followups main and head trees) | 14 -> 12 | 15 -> 15 |
| 10 with the terms on (needs-oracle-power, older code; 5 repeat 5) | 6 -> 6 | 10 -> 10 |
| 3 hunger mid range (not shipped) | 2 -> 2 | 3 -> 2 |

The subset-scale separation of terms on and off by the binding component,
already marginal under method 3, is a little weaker under method 4. No
threshold was retuned.

## 2. Batch directories and manifests

### Fresh destinations

`run_batch` writes `batch_<first seed>` next to `--output` and now refuses a
directory that already holds anything (`BatchDestinationError`; the CLI
prints it and exits 1). Refusing keeps every caller's paths: the gate
runner computes `<output-root>/oracle_subset/batch_<seed>` itself and now
checks it before it starts (an argument error), Batch Lab already writes
`output/batch_gui_<timestamp>`, and the tests use temporary directories.
An empty existing directory is accepted. The batch claims the directory by
creating an empty `batch_manifest.json` exclusively, so of two batches
started into one directory at once only one proceeds. The H-24 guard
(`--parallel` without `--simulate-only`) runs before the claim.

### The manifest

`batch_manifest.json` (`chronicler.batch_manifest`) is written before the
first run with status `running` and rewritten after the last as `complete`
or `cancelled`:

- `seeds`, `turns`, and per run its directory, bundle path, final turn and
  the SHA-256 of every file the validator reads (the bundle, the arrow
  sidecars, `validation_summary*.json`, `validation_summary/`). `state.json`,
  memory streams and chronicle text are not hashed and may be pruned.
- `simulation`: the requested simulation arguments (world, turns, agent
  mode, every feature switch, tuning file, preset, knobs) as given, None for
  a CLI default, and the tuning overrides in effect. Every parser argument
  is classified as simulation, output or neither; a test fails when a new
  one is not.
- `source`: the Git revision of the checkout holding the running package,
  read from the Git files (no child process), and a SHA-256 digest of the
  package's Python files, which also identifies a dirty or Git-less tree.
- `native`: the `chronicler_agents` extension file and its SHA-256, found on
  the import path without importing it.
- `environment`: Python, platform, CPU counts (Python's, which follows
  `PYTHON_CPU_COUNT`, and the affinity count native pools size by), the
  BLAS/OpenMP/rayon thread variables and `PYTHONHASHSEED`, and the versions
  of numpy, scipy, pyarrow, pydantic, arro3-core and the extension.

The gate runner writes a manifest for a determinism pair too (seed 42 in
`seed_42_a` and `seed_42_b`). Its own `run_manifest.json` (the gate
summary) keeps its name and adds the batch manifest's path and status.

### Validation consumes it

`python -m chronicler.validate` (and `run_oracles`) first checks the batch
directory (`check_batch_manifest`) and stops with an error when the batch
is not complete, a bundle is not in the manifest, a manifest run has no
bundle, a run is shorter than the requested turns, or a hashed validation
input changed. A directory without a manifest, or a single bundle, is
refused unless `--legacy-batch` (`legacy_batch=True`), which validates it
unchecked; a manifest that is present is always checked. Reports add
`batch_manifest` (`verified` with the seeds, turns, simulation
configuration and identity, or `unchecked`) and `profile`; older reports
load and compare as before. Gate summaries show a **Batch manifest** line.

## 3. Comparable cohorts

`compare_validation_reports` builds each report's cohort: seeds (with
repeats), turns, worlds, simulation configuration and gate profile, from a
verified manifest, else from the regression oracle's per-seed population
rows (seed, final turn) and the needs result's profile. Reports that differ
in any field both record are refused (`ValidationGateInputError`) unless
`exploratory=True` (`--exploratory`; the runner's `--exploratory-comparison`).
An exploratory result is labelled EXPLORATORY in its title and status and
says it is not regression evidence. Fields only one report records are
listed as not checked: an old baseline report gives seeds and turns but not
the simulation configuration. Different worlds keep their old message.

The status reads NO REGRESSION or REGRESSION as before, with the meaning in
the summary and the JSON (`status_meaning`): no required gate newly fails
(and no strict-regression downgrade where regression is required), not
unchanged distributions.

**Evidence by category.** A comparison lists each report's status per
category: execution (the batch's manifest check and the report),
determinism (`determinism`), balance (`regression`, `artifacts`, `arcs`) and
mechanism (`needs`, `community`, `cohort`, `era`). A category passes only
when its oracles pass; informational non-PASS statuses stay visible ("NOT
PASSED (informational only)" for a subset's balance oracles, "NOT CHECKED"
for a report without a manifest). The reports do not measure conservation,
performance or rendering, and the summary says so.

## 4. Small fixes

- `run_batch`: `--seed 0` runs seed 0 (`args.seed is None` gives 42). The
  `--parallel` worker count is unchanged (`fix/procedural-open-items`).
- `uv.lock` regenerated with `uv lock` (numpy 2.5.4, scipy 1.18.1, pyarrow
  26.0.0 and arro3-core 0.9.1 added; existing pins kept, so pydantic stays
  2.12.5, the floor's series; recent evidence here used 2.14.1). CI checks
  the lock (`uv lock --check`) and installs from it (`uv sync --frozen`) in
  the no-Rust, native and validation-gate jobs; the native jobs build with
  `maturin build --release --locked`.
- A viewer job: `npm ci`, `npm test -- --maxWorkers=2`, `npm run lint`,
  `npm run build` on Node 22.

## 5. Gates with method 4

The merged branch at `c1ce58a` (the simulation of `fc01d6e` and
`b8f0243`; PR #45 changes no simulation or Rust source), Linux, Python
3.13.17, `PYTHONHASHSEED=0`, subsets `--parallel 2`, extension built fresh
from `fc01d6e` (`maturin develop --release --locked`, SHA-256
`a6d0de13...6d31`, the turn-speed build's; compiled `AgentSimulator`,
`EcologySimulator`, `PoliticsSimulator` checked). The same two subsets at
`39d7e35`, before the merge, gave identical reports.

- **Template subset** (`--profile subset`, 42-61 x 200): PASS, batch
  manifest verified. Needs method 4 +0.191 (+0.101), 14 of 20 seeds (12
  required), binding +0.253 (+0.134), 190 informative. Against the
  turn-speed head's report (method 3, the same simulation): NO REGRESSION,
  needs method 3 -> 4 flagged for re-baselining, every other oracle result
  identical; method 3 re-scored on this batch equals that report's needs
  result exactly (+0.210 (+0.116), 17 seeds; binding +0.268 (+0.156), 213).
- **Procedural subset** (`--worldgen procedural`, 32 regions, 10 civs,
  42-61 x 200): PASS, batch manifest verified. Needs method 4 +0.177
  (+0.132), 18 of 20 seeds, binding +0.206 (+0.117), 393 informative.
  Against the procedural-gates merged head's report (method 3): NO
  REGRESSION, needs flagged for re-baselining, every other oracle result
  identical; method 3 re-scored here equals that report's needs result
  (+0.165 (+0.119), 17 seeds; binding +0.180 (+0.103), 405).
- **Full template gate** (200 x 500): not run with method 4. The machine's
  one full-gate slot was held by other branches' gates throughout. The
  full-scale evidence for method 4 is the re-score of the retained
  needs-followups full gate sidecars (§1: PASS, pooled +0.209 (+0.190),
  175 of 200 seeds; binding +0.185 (+0.160)), which are from `d44cf4f`,
  not from this branch's simulation.

## 6. Identity

Same venv and extension, `main`'s exported `src` against the branch,
twice: `fc01d6e` against `39d7e35`, and `b8f0243` against the merged
`c1ce58a`. Each time `scripts/turn_speed_identity.py` cases `off_s42`,
`hybrid_s42`, `hybrid_s7` and `proc48_hybrid_s42`: 320 files, 0
differences (bundles decoded without `generated_at` and raw with it
blanked); and a batch, `--seed-range 42-44 --turns 200 --agents hybrid
--validation-sidecar --parallel 2`: 331 files, 0 differences,
`batch_manifest.json` only in the branch's batch. Golden fixtures are
unchanged.

## 7. Tests

Linux, Python 3.13.17, the venv synced from the new lock (`uv sync
--frozen`) plus the fresh extension, at the merged `c1ce58a`:

- Focused (`test_batch_manifest`, `test_batch*`, `test_main`,
  `test_validate`, `test_validation_*`, `test_m53b_run_validation`,
  `test_procedural_gates`, `test_snapshot_pruning`, `test_bundle_codec`,
  `test_audit_batch_d`, `test_m10_integration`, `test_m19_integration`): 512
  passed. New: `tests/test_batch_manifest.py` (reuse refused, the claim,
  seed 0, manifest contents, argument classification, cancellation, every
  validation refusal, the legacy flag, source and extension identity
  without child processes or imports), method 4 tests in `test_validate.py`,
  cohort, exploratory, wording and category tests in
  `test_validation_compare.py`, runner tests in
  `test_m53b_run_validation.py`, workflow tests in
  `test_native_build_lanes.py`.
- `python scripts/run_python_oracle_checks.py`: PASS in 103.5 s, 2,460
  passed, 36 skipped (at `39d7e35`: PASS in 138.2 s, 2,423 passed); a new
  `validation-tooling` chunk (the manifest, batch, gate and comparator
  tests: 96 passed in 4.2 s).
- `pytest -m "not slow" -n 2`: 6,409 passed, 3 skipped, 9 failed. The 9 are
  pytest-xdist failing to serialize `unittest` subTest parameters
  (`execnet` `DumpError`) in five session and preview suites; the same 9
  fail on `fc01d6e` with `-n 2`, and the five files pass in one process
  (146 passed).
- Viewer (Node 22.22.0): `npm ci`, `npm test -- --maxWorkers=2` (44 files,
  352 tests), `npm run lint`, `npm run build` pass.
- `uv lock --check` passes.

## 8. Not run, open

- Not run: `cargo test` (no Rust change), `pytest -m slow`, the procedural
  full gate, a determinism profile, a native CI run of the new workflows
  (checked locally only: the lock, the venv sync, the viewer steps), and a
  terms-zeroed or shuffled sensitivity run under method 4 beyond the
  re-scored sidecars.
- The cohort oracle counts its window from the snapshot turn as methods 2
  and 3 did; not changed here.
- Method 4 weakens the binding component's separation of terms on and off
  at subset scale a little (subset rules never relied on it; the full
  profile does).
- The manifest records the requested configuration, so a CLI default that
  changes between code versions is not a cohort difference (comparing code
  versions is the point); explicit and default values of the same setting
  are. The Git revision does not show uncommitted changes; the package
  digest does. The validation profile is recorded in the report and the
  runner's `run_manifest.json`, not in the batch manifest.
- Comparisons against reports written before this branch can check seeds
  and turns only; their simulation configuration is listed as not checked.
- pydantic stays locked at 2.12.5 (`uv lock` keeps existing pins); this
  machine's earlier evidence used 2.14.1. `uv lock --upgrade-package
  pydantic` would move it.

## Appendix: every re-scored set

Pooled: net concordance (lower bound), seeds with C > D. Binding: net
(lower bound), informative pairs. Verdicts: the gate's needs status for the
subset profile and with full-profile rules, method 3 -> method 4. Sets of
`fix/needs-followups` (`main0`: its early head `b5d41af`; `base` and
`head`: main `f5425dc` and the head `89f3d67`; `base3` and `head2`: main
`2ef3097` and the head `d44cf4f`; `needsoff-*`: the same trees with the
need terms zeroed; `hunger-mid`: the unshipped hunger variant; `full-head`:
the 200 x 500 full gate at `d44cf4f`) and of `fix/needs-oracle-power`
(`power-*`, `main` `48b72be` and its variants).

| Set | Seeds x turns | Pooled, method 3 | Pooled, method 4 | Binding, method 3 | Binding, method 4 | Subset | Full rules |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `full-head` | 200 x 500 | +0.222 (+0.204), 176 | +0.209 (+0.190), 175 | +0.192 (+0.168), 5060 | +0.185 (+0.160), 4892 | PASS -> PASS | PASS -> PASS |
| `main0-42` | 20 x 200 | +0.228 (+0.170), 18 | +0.211 (+0.144), 17 | +0.284 (+0.195), 268 | +0.259 (+0.154), 259 | PASS -> PASS | PASS -> PASS |
| `main0-62` | 20 x 200 | +0.155 (+0.097), 14 | +0.162 (+0.105), 17 | +0.167 (+0.074), 240 | +0.157 (+0.064), 230 | PASS -> PASS | PASS -> PASS |
| `main0-82` | 20 x 200 | +0.234 (+0.160), 17 | +0.219 (+0.135), 18 | +0.252 (+0.179), 206 | +0.248 (+0.163), 210 | PASS -> PASS | PASS -> PASS |
| `needsoff-main0-42` | 20 x 200 | +0.123 (+0.047), 14 | +0.135 (+0.052), 13 | +0.062 (-0.004), 241 | +0.035 (-0.059), 226 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-main0-62` | 20 x 200 | +0.184 (+0.096), 15 | +0.169 (+0.089), 15 | +0.189 (+0.069), 244 | +0.172 (+0.047), 232 | PASS -> PASS | PASS -> PASS |
| `needsoff-main0-82` | 20 x 200 | +0.155 (+0.075), 15 | +0.163 (+0.072), 14 | -0.025 (-0.145), 240 | -0.068 (-0.205), 236 | PASS -> PASS | FAIL -> FAIL |
| `base-42` | 20 x 200 | +0.151 (+0.075), 15 | +0.135 (+0.059), 14 | +0.279 (+0.184), 258 | +0.195 (+0.105), 241 | PASS -> PASS | PASS -> PASS |
| `base-62` | 20 x 200 | +0.178 (+0.110), 15 | +0.193 (+0.128), 17 | +0.170 (+0.069), 265 | +0.140 (+0.039), 258 | PASS -> PASS | PASS -> PASS |
| `base-82` | 20 x 200 | +0.193 (+0.107), 16 | +0.181 (+0.089), 15 | +0.164 (+0.041), 225 | +0.117 (-0.006), 213 | PASS -> PASS | PASS -> FAIL |
| `needsoff-base-42` | 20 x 200 | +0.097 (+0.021), 11 | +0.101 (+0.022), 13 | -0.026 (-0.126), 230 | +0.005 (-0.092), 213 | FAIL -> PASS | FAIL -> FAIL |
| `needsoff-base-62` | 20 x 200 | +0.155 (+0.078), 13 | +0.155 (+0.080), 15 | +0.041 (-0.105), 219 | +0.024 (-0.118), 207 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-base-82` | 20 x 200 | +0.141 (+0.067), 14 | +0.159 (+0.094), 16 | -0.013 (-0.113), 235 | -0.004 (-0.111), 221 | PASS -> PASS | FAIL -> FAIL |
| `head-42` | 20 x 200 | +0.185 (+0.080), 16 | +0.168 (+0.056), 16 | +0.280 (+0.157), 214 | +0.280 (+0.147), 200 | PASS -> PASS | PASS -> PASS |
| `head-62` | 20 x 200 | +0.127 (+0.060), 14 | +0.105 (+0.043), 15 | +0.197 (+0.099), 229 | +0.164 (+0.062), 208 | PASS -> PASS | PASS -> PASS |
| `head-82` | 20 x 200 | +0.154 (+0.036), 14 | +0.128 (+0.021), 14 | +0.174 (+0.015), 172 | +0.148 (-0.005), 162 | PASS -> PASS | PASS -> FAIL |
| `needsoff-head-42` | 20 x 200 | +0.162 (+0.081), 17 | +0.184 (+0.093), 17 | +0.125 (+0.021), 208 | +0.178 (+0.055), 197 | PASS -> PASS | PASS -> PASS |
| `needsoff-head-62` | 20 x 200 | +0.203 (+0.125), 15 | +0.208 (+0.130), 14 | +0.156 (-0.015), 173 | +0.171 (+0.021), 176 | PASS -> PASS | FAIL -> PASS |
| `needsoff-head-82` | 20 x 200 | +0.161 (+0.061), 14 | +0.167 (+0.064), 14 | +0.060 (-0.051), 200 | +0.079 (-0.029), 178 | PASS -> PASS | FAIL -> FAIL |
| `base3-42` | 20 x 200 | +0.163 (+0.081), 14 | +0.147 (+0.063), 14 | +0.297 (+0.173), 222 | +0.282 (+0.152), 220 | PASS -> PASS | PASS -> PASS |
| `base3-62` | 20 x 200 | +0.152 (+0.090), 17 | +0.156 (+0.086), 17 | +0.167 (+0.072), 252 | +0.177 (+0.082), 243 | PASS -> PASS | PASS -> PASS |
| `base3-82` | 20 x 200 | +0.153 (+0.064), 16 | +0.133 (+0.056), 13 | +0.151 (+0.006), 259 | +0.165 (+0.035), 249 | PASS -> PASS | PASS -> PASS |
| `needsoff-base2-42` | 20 x 200 | +0.096 (-0.000), 14 | +0.103 (+0.003), 12 | +0.029 (-0.086), 237 | +0.082 (-0.024), 231 | FAIL -> PASS | FAIL -> FAIL |
| `needsoff-base2-62` | 20 x 200 | +0.132 (+0.075), 15 | +0.135 (+0.064), 15 | +0.078 (-0.046), 219 | +0.039 (-0.077), 206 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-base2-82` | 20 x 200 | +0.090 (+0.011), 12 | +0.114 (+0.035), 13 | -0.072 (-0.183), 250 | -0.033 (-0.155), 240 | PASS -> PASS | FAIL -> FAIL |
| `head2-42` | 20 x 200 | +0.145 (+0.057), 14 | +0.173 (+0.073), 15 | +0.172 (+0.111), 215 | +0.192 (+0.113), 198 | PASS -> PASS | PASS -> PASS |
| `head2-62` | 20 x 200 | +0.232 (+0.105), 15 | +0.207 (+0.078), 13 | +0.358 (+0.252), 212 | +0.371 (+0.263), 197 | PASS -> PASS | PASS -> PASS |
| `head2-82` | 20 x 200 | +0.193 (+0.119), 18 | +0.141 (+0.049), 14 | +0.103 (-0.028), 185 | +0.085 (-0.042), 188 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-head2-42` | 20 x 200 | +0.127 (+0.022), 13 | +0.127 (+0.026), 14 | +0.078 (-0.056), 193 | +0.086 (-0.070), 186 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-head2-62` | 20 x 200 | +0.141 (+0.061), 16 | +0.092 (+0.003), 13 | +0.098 (-0.021), 184 | +0.077 (-0.059), 169 | PASS -> PASS | FAIL -> FAIL |
| `needsoff-head2-82` | 20 x 200 | +0.136 (+0.027), 14 | +0.180 (+0.085), 16 | +0.030 (-0.074), 202 | +0.094 (-0.023), 192 | PASS -> PASS | FAIL -> FAIL |
| `hunger-mid-42` | 20 x 200 | +0.144 (+0.046), 13 | +0.147 (+0.037), 11 | +0.122 (-0.026), 196 | +0.146 (-0.002), 185 | PASS -> FAIL | FAIL -> FAIL |
| `hunger-mid-62` | 20 x 200 | +0.183 (+0.077), 14 | +0.127 (+0.015), 12 | +0.242 (+0.113), 182 | +0.189 (+0.057), 175 | PASS -> PASS | PASS -> PASS |
| `hunger-mid-82` | 20 x 200 | +0.247 (+0.159), 15 | +0.183 (+0.097), 14 | +0.253 (+0.110), 174 | +0.205 (+0.037), 161 | PASS -> PASS | PASS -> PASS |
| `power-main-42` | 20 x 200 | +0.179 (+0.101), 15 | +0.210 (+0.116), 17 | +0.208 (+0.065), 96 | +0.244 (+0.109), 90 | PASS -> PASS | PASS -> PASS |
| `power-main-62` | 20 x 200 | +0.199 (+0.098), 15 | +0.190 (+0.096), 16 | +0.333 (+0.181), 90 | +0.309 (+0.130), 84 | PASS -> PASS | PASS -> PASS |
| `power-main-82` | 20 x 200 | +0.330 (+0.245), 18 | +0.326 (+0.239), 16 | +0.258 (-0.091), 62 | +0.206 (-0.147), 63 | PASS -> PASS | FAIL -> FAIL |
| `power-needsoff-42` | 20 x 200 | +0.089 (-0.019), 10 | +0.106 (+0.004), 11 | +0.000 (-0.194), 80 | -0.013 (-0.237), 79 | FAIL -> FAIL | FAIL -> FAIL |
| `power-needsoff-62` | 20 x 200 | +0.158 (+0.065), 14 | +0.197 (+0.090), 15 | -0.062 (-0.300), 64 | -0.169 (-0.413), 65 | PASS -> PASS | FAIL -> FAIL |
| `power-needsoff-82` | 20 x 200 | +0.178 (+0.104), 14 | +0.167 (+0.093), 14 | -0.077 (-0.243), 78 | -0.195 (-0.371), 77 | PASS -> PASS | FAIL -> FAIL |
| `power-movements-42` | 20 x 200 | +0.138 (+0.049), 17 | +0.146 (+0.041), 14 | +0.216 (+0.092), 74 | +0.211 (+0.107), 71 | PASS -> PASS | PASS -> PASS |
| `power-nocities-62` | 20 x 200 | +0.184 (+0.099), 13 | +0.164 (+0.067), 15 | +0.013 (-0.199), 79 | -0.025 (-0.247), 80 | PASS -> PASS | FAIL -> FAIL |
| `power-final-main-42` | 20 x 200 | +0.179 (+0.101), 15 | +0.210 (+0.116), 17 | +0.208 (+0.065), 96 | +0.244 (+0.109), 90 | PASS -> PASS | PASS -> PASS |
| `power-final-main-62` | 20 x 200 | +0.199 (+0.098), 15 | +0.190 (+0.096), 16 | +0.333 (+0.181), 90 | +0.309 (+0.130), 84 | PASS -> PASS | PASS -> PASS |
| `power-final-main-82` | 20 x 200 | +0.330 (+0.245), 18 | +0.326 (+0.239), 16 | +0.258 (-0.091), 62 | +0.206 (-0.147), 63 | PASS -> PASS | FAIL -> FAIL |
| `power-final-movements-42` | 20 x 200 | +0.138 (+0.049), 17 | +0.146 (+0.041), 14 | +0.216 (+0.092), 74 | +0.211 (+0.107), 71 | PASS -> PASS | PASS -> PASS |
| `power-final-nocities-62` | 20 x 200 | +0.184 (+0.099), 13 | +0.164 (+0.067), 15 | +0.013 (-0.199), 79 | -0.025 (-0.247), 80 | PASS -> PASS | FAIL -> FAIL |
| `power-probe500-142` | 20 x 500 | +0.166 (+0.121), 17 | +0.182 (+0.137), 17 | +0.058 (-0.083), 223 | +0.035 (-0.108), 226 | PASS -> PASS | FAIL -> FAIL |
