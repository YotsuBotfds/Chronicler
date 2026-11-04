# Harvest target correction: development registration

Registered on 2026-10-28 before launching this rerun. This is a development
verification of an already observed correction, using the known seeds 42 and
43. Earlier outcomes and the negative-target failure have been inspected.
These seeds are not a fresh confirmatory sample. No efficacy, population-wide
benefit, or feature-promotion claim is planned.

## Frozen inputs

| Input | Identity |
| --- | --- |
| Simulation commit | `d051d7c06b1a490841d148b8906bde22f2f5d0f0` |
| Python package digest | `c14bc2f0178139b58d778926e1f803597ee0856958b02da67882b851845c8129` |
| Native extension SHA-256 | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Correction ancestor | `8e3fc817960fc22d84a3ad78eed5cd72f10517ce` |
| Harvest implementation SHA-256 | `1a329c669060544c9a27a9052e86eb10d87fcdba51c84b26e9b41b227e84d80a` |
| External runner commit | `0885c4503d063e9d30a705c0bcb152b0a8687c27` |
| External runner SHA-256 | `b2f691f6ce1b9b7dfc4245d9e1951104e09de68aabafee19a2e1e81c94abee61` |

The corrected target is the recorded baseline plus a nonnegative warning
increment. A baseline already above the warning cap must not be reduced by a
negative increment. The earlier seed-43 shuffled report `harvest:2:0:6` at
source turn 32 recorded baseline `4.126938305182808`, increment
`-1.126938305182808`, and target `3.0`; its source bundle SHA-256 is
`2f98dd603b57f85dd710202c17badcaf13ca7e4861b41e1da65ac94016cc8415`.
That original evidence and the other 23 original study bundles remain intact.
The new source and binary include additional changes, so differences from those
older trajectories cannot be attributed solely to this correction.

## Fixed execution plan

- Seeds: 42 and 43, template worlds with 8 regions and 4 civilizations.
- Horizon: 40 completed turns; hybrid agents; simulation only, with validation
  sidecars and no LLM calls.
- Features: harvest forecasts, grain reserves and the contact ledger. Other
  fresh-world options retain the frozen source defaults.
- Per seed: one full-horizon parent retaining its exact checkpoint at turn 4,
  then normal, withheld and shuffled continuations from that same checkpoint.
  This is eight executions: two parents and six 36-turn continuations, or 296
  simulated turns if all complete. Parents run to 40 to preserve ordinary final
  settlement behavior; their histories are not eight independent worlds.
- No numeric control overrides, seed substitution, adaptive arm selection,
  outcome-based stopping, or tuning. Preserve failures. Any retry uses a new
  evidence directory and discloses its reason.
- One worker. Set Python hash seed to 0 and Rayon, OpenMP and BLAS thread caps
  to 1. Enable `CHRONICLER_CHECK_RESOURCES=1` and
  `CHRONICLER_CHECK_POPULATION=1` consistently; these checks have their existing
  implementation scope and do not prove all native accounting properties.

Commit this registration before launch, copy its exact bytes into the new
external evidence directory, and pass that file as `--registration`. Retain
its hash, the doc commit, UTC launch/completion receipts, the exact command,
stdout/stderr and exit status under a durable supervisor. Keep generated data
outside Git. The actual worker environment must be captured before and after
each execution by the frozen schema-2 runner; a parent environment is not a
substitute for worker evidence.

With `SOURCE_ROOT`, `EVIDENCE_ROOT` and the frozen interpreter selected outside
the repository, the runner arguments are fixed as follows:

```sh
python "$EVIDENCE_ROOT/run_expansion_experiment.py" \
  --source-root "$SOURCE_ROOT" \
  --feature harvest_forecasts --cohort development \
  --name harvest-target-correction-development \
  --seeds 42-43 --turns 40 --fork-turn 4 \
  --arms normal,withheld,shuffled --worldgen template --regions 8 --civs 4 \
  --workers 1 --registration "$EVIDENCE_ROOT/preregistration.md" \
  --output-root "$EVIDENCE_ROOT/runs"
```

## Mechanical acceptance and descriptive readout

Check all eight completion statuses and horizons, unchanged source/package/
native/runner identities, stable actual before/after worker environments, and
equal actual environments across matched arms. Verify both normal no-op
continuations have the same exported final Python world as their parent. This
identity does not certify every native pool or every output file.

Run the bounded read-only expansion audit on every bundle. For every recorded
preparation require finite, nonnegative `extra_target`; where a corresponding
granary target is recorded, require `target >= base_target` and
`target = base_target + extra_target` within relative tolerance `1e-8` and
absolute tolerance `1e-7`. Report incomplete coverage and unavailable facts.
If the earlier opportunity does not recur, say that no recurrence was observed;
do not claim the exact historical failure condition was exercised.

Run the strict comparator for normal versus withheld and normal versus shuffled
within each seed: four candidate pairs. Require common checkpoint, source,
binary, flags, registration, prefix, actual schema-2 environment and post-fork
window. Comparisons cover completed turns 4 through 39, not the shared prefix.
Any identity, coverage, audit or control mismatch remains a blocker; do not
relax matching after inspecting outcomes.

Report issued/delivered/closed/scored forecasts, Brier arithmetic with its
denominator, recorded preparation opportunities, positive payments, grain
purchases and funds spent. Preserve empty eligibility and missing exposure.
Purchases during a warning are not measured causal excess spending. Harvest
shortfalls depend on production, demand and policy, so forecast scores do not
establish an exogenous hazard or economic benefit. Two repeated seeds, shared
forks and repeated receipt snapshots do not establish independent sample size.
No significance test, clinical claim, avoided-death claim, confirmatory efficacy
claim or full milestone qualification is planned.

Results and deviations will be written separately without rewriting this
registration.
