# Corrected CWR1 AD enabled exact resume

Both development-world cases pass: **14 resumed branches and two checkpoint-writing
neutrality checks, 202 file comparisons, zero differences**. Each repeated straight
run also reproduces its saved pilot trajectory. All eighteen output Arrow
identities match their respective pilot. This is lifecycle/output identity
evidence, not qualification or a performance improvement claim.

Runtime is clean `8792be88dd36ba4d7c22e480de6a19dd64ea1300` at
`/workspace/cwr-final-runtime`, interpreter `/workspace/cwr-native/bin/python`,
imported compiled extension SHA256
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`.
Frozen [driver](driver.py.txt) SHA256:
`bb02ef4bac760bdc4068c443294a9b466169ca937b9ae9645debc88030bf0c2c`.
Official pilot source identity is `96f1efad…`; full source/import/native,
CLI and tracked runtime-input identities are in each plan. No production source,
comparator or native build changed for these runs.

| Development case, 120 turns | Selected completed checkpoints | Resumes | Files per check | Actual execution / fixed cap |
| --- | --- | ---: | ---: | ---: |
| procedural 19 | 1, 2, 3, 18, 19, 67 | 6 | 16 | 387.03 / 600 seconds |
| template 5 | 3, 4, 5, 6, 12, 13, 41, 61 | 8 | 10 | 174.53 / 350 seconds |

Receipts: [readback](completed-readback.json), [schedule/budgets](execution-schedule.json),
[procedural plan](plan-p19.json), [template plan](plan-t5.json),
[procedural report](completed/p19/report.json), [template report](completed/t5/report.json).
The exact [procedural](completed/p19/invocations.json) and
[template](completed/t5/invocations.json) commands, environments, exits, output
SHA/size inventories and selected checkpoint SHA/size metadata are retained.
All eighteen stdout logs and both comparison execution logs are under `completed/`.

## Corrected controls and actual lifecycle coverage

These are **AD**, rules 3, all personal channels, active health and explicit
`density_only`, using only the registered template-5/procedural-19 timing worlds.
The adapter validates actual seed/geography, all 120 completed snapshots and
dated A6/public-health choices, then invokes the real strict
`cw_rework_screen.extract(..., expected_turns=120)`. The historical CW6 FULL
public planner does not validate or select these new controls. Saved pilots
contain JSON/world state and untruncated Arrow; the adapter generates its own
new same-source private checkpoints.

Selection prioritizes the first actual D3 wound/release/evacuation/return
before/after boundaries, then maximizes uncovered observed lifecycle categories,
with earliest-turn ties and a twelve-point maximum per stratum. Full active-turn
lists, missing/unselected categories and example dates remain in the plans.
No world was edited or event forced.

The union covers every declared category: actual migration; recent residence
arrivals and complete twenty-turn arrival coverage; army demand and positive
requisition/seizure; moving timber with positive cargo and escrow; named paid
infrastructure work; actual epidemic care coverage and individual health
episodes; dated reports/paid guards; personal A6 memory; money transfers;
moving titled food and actual restitution. These are observed state predicates,
not proofs of motive, individual causal effect or a complete personal diary.

Procedural first wound/release occurs at source turn zero, so preceding
checkpoint zero is unavailable. Evacuation has before/after checkpoints 2/3
and return 18/19. Template supplies all four D3 before/after boundaries:
release/evacuation 3/4, wound 5/6 and return 12/13. Template has **no positive
care-coverage or moving-timber-escrow observation**; procedural covers both.
No active category is silently unselected. These cases do not cover every
possible pool-reset, birth, estate, training, transaction or campaign transition;
unit/native/compatibility and canonical cases remain separate evidence.

## Comparison, identities and retention

Unchanged `checkpoint_identity.run_case` creates a plain run, a straight run
writing checkpoints each turn, and selected continuations, with `jobs=1`, hash
seed zero and native/BLAS/OpenMP thread limits one. The adapter never unpickles
an old-source checkpoint. Before/after every subprocess it checks exact clean
source, native/interpreter paths and bytes, tracked runtime inputs and pilot
JSON/Arrow/source record. It also compares the repeated straight bundle to
the pilot used for selection.

Unchanged `cities_identity.compare` decodes the bundle, removes
`metadata.generated_at` and compares sorted-key JSON serialization: decoded
values, not raw JSON bytes or key order. Other outputs, including Arrow, compare
as bytes. Established exclusions are manifests, logs, checkpoints and absent
precheckpoint per-turn validation JSON. Checkpoint hashes document created
artifacts; checkpoint bytes themselves are not an identity target. Passing
temporary checkpoints/resumed directories follow existing cleanup; retained
straight outputs and matching hashes preserve the verified observations.

An external [collector](retain-logs.py.txt) held stdout descriptors through the
comparator's unlink of passing logs and copied complete bytes outside compared
directories. Both collector receipts and eighteen hashed logs are retained.
No simulated process or compared output was added. A read-only
[auditor](audit-completed.py.txt) rechecked report arithmetic, Arrow identities,
retained straight outputs, fourteen checkpoint hashes/sizes, eighteen logs and
current source/native/input hashes: [PASS](completed-readback.json). Independent
final review remains the lead's distinct gate.

## Budgets and preserved failure

The official 24-run timing pilot closed first. Procedural AD took 30.7 seconds;
six continuations span 610 remaining turns. Its fixed execution cap was 600
seconds. Template AD took 10.7 seconds; eight continuations span 815 turns.
The [pre-execution proposal](template-budget-proposal.json) used that rate,
historical checkpoint cost and conservatively transferred measured procedural
comparison/guard overhead: 234.10 seconds. The lead accepted 350 seconds before
template started. Execution includes inventories/comparisons/final guards;
initial planning/import/revalidation and later audit are outside that clock.
Template shared the host with one single-CPU held model process. These wall
times are not comparative performance benchmarks. No cap was raised or world
replaced; the offline 110-second chunk limit was unchanged.

The first procedural invocation refused **before simulation or output creation**:
the official source record appended its final `finished` line after planning.
The [failure](prestart-refusal.log) and [readback](prestart-refusal.json) show
that only the source-record hash changed; model/native/CLI/selection and pilot
JSON/Arrow were unchanged. Replanning against the closed record preserved the
frozen adapter and 600-second cap. Earlier planning remains in Git history.

Preparation [receipt](preparation.json) and [constructed checks](preparation-self-check.json)
retain the compiled-package identity and nonfinite-budget mistakes found and
corrected before execution. Runtime/scientific results were not changed to
rescue a run.

## Reproduction

Use matching published source/native, recreated official development pilots and
**new output paths**. Exact model subprocess commands are in the invocation
receipts. The procedural entry point was:

```sh
PYTHONPATH=/workspace/cwr-final-runtime/src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
/workspace/cwr-native/bin/python /workspace/evidence/cwr-resume/driver.py run \
  --source-root /workspace/cwr-final-runtime \
  --plan /workspace/evidence/cwr-resume/plan-p19-8792-bb02-closed.json \
  --output /workspace/evidence/cwr-resume/run-p19-8792-bb02-v2 \
  --max-wall-seconds 600
# Template: same environment, plan-t5-8792-bb02-closed.json,
# output run-t5-8792-bb02-v1 and --max-wall-seconds 350.
```

Driver `plan --help`, `run --help` and `self-check --help` are inert. Planning
requires source/native SHA, official pilot source, bundle, stratum/seed and a
new plan output; running requires exact driver hash, immutable inputs and a
finite predeclared budget. No paid calls, new held seeds, qualification or
default promotion were involved. Raw workspace lifetime is not promised;
exact refs, commands, identities and compact receipts support reconstruction.
