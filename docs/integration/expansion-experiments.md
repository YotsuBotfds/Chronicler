# Running controlled expansion studies

`scripts/run_expansion_experiment.py` writes reproducible experiment evidence
for harvest forecasts, harvest gatherings and health/care. It does not issue a
scientific gate verdict or promote a feature. The default cohort is not guessed:
`--cohort development` or `--cohort confirmatory` is required. Confirmatory runs
also require a registration file, whose digest is retained; the label and hash
do not by themselves establish adequate power or adherence to the protocol.

## Shared parent, explicit intervention

For each seed, the harness calls the real `execute_run` with no supplied world.
Normal fresh-world configuration therefore applies all existing defaults before
the selected experiment's controls are changed. It enables only the requested
new feature and its prerequisites; the other new features stay off.

The parent runs to the final requested horizon and retains an earlier exact
checkpoint. Every arm restores that same checkpoint, then applies a typed,
source-owned control request before the next turn. Running the parent only to
the fork would force final-turn settlement detection there and change the
ordinary prefix. The full parent avoids that distortion and supplies the
uninterrupted reference. A no-op arm's final `state.json` must match its parent
byte for byte; metadata still correctly labels that arm as an experiment fork.

Resumed control requests require `fork=True`, the parent checkpoint's actual
path/SHA-256 and a matching seed/turn. They are labelled intervention forks,
not exact continuations of unchanged behavior. Ordinary exact resumes without
a new request keep the saved controls and experiment receipt. Neither the
helper nor the runner silently enables an unavailable system or rewrites its
episodes, reports, schedules, native inputs or clock.

The optional `execute_run(..., expansion_experiment=REQUEST)` seam invokes
`chronicler.expansion_experiment.apply_expansion_experiment` after normal
configuration/restore. Only the following controls are accepted and validated
by the system's own state schema:

| Feature | Registered arms | Other shared controls |
| --- | --- | --- |
| `harvest_forecasts` | `normal`, `withheld`, `shuffled` | None; arm names fix `policy` |
| `ritual_gatherings` | `normal`, `no_contact`, `no_bonds`, `cost_only` | None; arms fix the two channel switches |
| `health_care` | `care`, `no_care` | `injury_rate`, `impairment`, `care_fraction`, `recovery_work` |

The receipt stores **all** resolved control parameters before and after the
intervention, rather than only overrides. State progress stays intact. An
already-delivered report is not retroactively withheld by a later policy
change. Choose the fork boundary accordingly and register it before running.
The default boundary is completion turn 4, before assessment publication at
source turn 5 and the first gathering at source turn 8.

## Invocation

Run with an interpreter containing the identified native build. An external
copy of the runner can target a frozen simulation checkout with `--source-root`;
source selection occurs before Chronicler imports, and mixing already-imported
checkouts is rejected. The runner file's SHA-256 is recorded separately from
the simulation package digest.

```sh
python scripts/run_expansion_experiment.py \
    --source-root /path/to/frozen-checkout \
    --feature harvest_forecasts --cohort development --name forecast-probe \
    --seeds 42-43 --turns 40 --fork-turn 4 --workers 1 \
    --output-root /path/to/new/forecast-evidence

python scripts/run_expansion_experiment.py \
    --source-root /path/to/frozen-checkout \
    --feature ritual_gatherings --cohort development --name gathering-probe \
    --seeds 42-43 --turns 40 --workers 1 \
    --output-root /path/to/new/gathering-evidence
```

`--arms` selects comma-separated registered arms. `--controls FILE.json`
provides shared source-owned parameters, with arm-defining fields rejected.
`--registration FILE.md` records a frozen protocol file. `--worldgen procedural`
defaults to 32 regions/10 civs; templates default to the ordinary 8/4.
`--regions` and `--civs` are explicit workload overrides. Seeds are nonnegative
integers or inclusive comma-separated ranges; duplicates are rejected rather
than counted as independent replicates.

`--workers` defaults to one and bounds concurrent seeds. Arms within a seed run
sequentially. Each simulation runs in a fresh subprocess with one-thread native
and numerical-library settings and a fixed Python hash seed. These settings
apply to children, not unrelated processes. Coordinate larger worker counts
with native builds, other gates and available memory; extra agents do not
increase the host's CPU quota.

## Evidence and failures

`expansion_experiment_manifest.json` records the cohort, world, seeds, horizon,
fork boundary, requested arm controls, registration digest, simulation source/
package/native identities, interpreter/environment, worker thread settings,
external runner hash, exact worker commands, simulation arguments, actual
control receipts, parent checkpoint identities and per-file output hashes.
Each run retains `job.json`, `worker.log`, `worker_identity.json`, its bundle,
state and sidecars. The parent checkpoint is retained. No output is pruned or
overwritten by the harness; a used destination is refused.

Source/native identities are checked before and after each worker and against
the experiment's identity. The external runner hash is checked again at the
end. A worker error, missing/mismatched receipt, incomplete horizon, changed
source/binary or failed no-op state identity makes the evidence manifest fail.
Failed seeds remain visible; they are not dropped from the cohort. An intact
manifest marked `complete` means its declared executions completed under the
recorded identities, not that their effects passed a statistical threshold.

The small development examples above test execution, exposure and accounting.
They cannot establish population benefit. Health cohorts must be selected at
the common fork and censored at death; future injury or survival cannot select
the analysis sample. Forecast production/demand scores include policy feedback;
climate-vector exogeneity and preparation losses are separate diagnostics.
Gatherings need actual attendance/contact/accepted bond evidence, not merely
an enabled flag. Preserve empty exposures and inconclusive results. See the
[qualification plan](expansion-qualification.md) and each system's registered
mechanism criteria before assigning confirmatory seeds or making claims.

## Checks

The helper tests reject unknown/nonfinite/invalid control values atomically,
preserve state progress, require explicit fork lineage and verify parent and
registration hashes. Harness tests check normal fresh-world entrypoint usage,
common parents, failed-parent containment, output preservation, truncated-run
failure, source drift and binary identity independent of import-path labels.
These tests replace subprocess outcomes only in their deliberate unit fixtures;
the production runner always executes the real simulator and reads its outputs.

## First actual development studies, 2026-10-28

The commands above were executed for all three features, seeds 42–43, completion
horizon 40, common fork boundary 4, one worker. The health study used the same
arguments with `--feature health_care`. Simulation source was frozen at
`527a9ff804a157a1278f86fbf1b4ac3065f195a9`, package digest
`e1d0aee1c2a64aa86f4235e1dcc3ef679044b139c18426afa5d8492f71465263`.
The fresh native extension SHA-256 was
`e7ec77283075cb9b817ad47490fc98a3e77685451bbcd4ce8f5b8bcad9db5867`.
External runner source was commit `e7b2add9`, file SHA-256
`f8c628415f6fb71898eaa491822133a73a6c51da5b4deb120661c8efb48d1799`.

All **24 actual executions** completed their declared horizons with stable
source/native/runner identities: eight forecast, ten gathering and six health
runs, including the full parents. All six no-op control forks had final state
bytes identical to their uninterrupted parents. These are development execution
and continuation results, not full gates or estimates of population benefit.

- Forecast normal arms delivered 17/21 reports for seeds 42/43 and recorded
  89.60/112.39 received grain with 15/19 treasury paid while warnings were
  active. Withheld arms delivered no reports and recorded no warning-associated
  purchases; ordinary granary purchases are a separate quantity. Shuffled arms
  also ran. These receipts do not identify causal excess purchases.
- Gathering normal arms held 4/10 occurrences, cancelled 20/14, recorded
  102/281 attendances, consumed 5.10/14.05 grain and spent 12/30 treasury.
  They attempted 25/54 bond updates and added 0/15 gathering contact units.
  Disabled channels recorded zero respective activity. Seed 42 supplies no
  gathering-contact exposure and cannot establish an effect of that channel.
- In source turns 4–39, health care arms recorded 2.0/3.0 worker-turns of care
  over 10/15 recipient-turns. No-care arms recorded zero care. New injury counts
  and later worlds diverged, so their aggregate recovery totals are not a fixed
  patient-cohort causal estimate. The controlled mechanism tests remain distinct.

The complete evidence, worker logs and artifacts are retained outside Git.
Manifest SHA-256 values identify the records independently of local paths:

| Study | Manifest SHA-256 |
| --- | --- |
| Forecasts | `8ea7c17ac5360ac6b2b71a50ceacdd5941c95ee5c70a1c836441963a5f9b9fbf` |
| Gatherings | `d18a6193611b443b2be2fb4d3700c813050b0dcead310b0f3f6f323d2003c29b` |
| Health/care | `4a688490f0b331b9f538b7607cb6907bc37e64fc27e8f006eea19f18b4d060ce` |
