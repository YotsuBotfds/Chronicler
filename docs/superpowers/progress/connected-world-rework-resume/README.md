# CWR1 exact-resume evidence adapter: planning, execution pending

This is an evidence-only adapter for the final **AD**, rules 3, all personal
channels, active health and explicit `density_only` timing pilots: template 5
and procedural 19, 120 turns each. It does not claim that the historical CW6
FULL planner selects or validates these new controls. The existing
`checkpoint_identity.run_case` and `cities_identity.compare` remain the
execution/comparison authorities. No production source or comparator is edited.

The [driver](driver.py.txt), [preparation receipt](preparation.json) and
[pure constructed checks](preparation-self-check.json) are reviewable before
the final source/pilots exist. **No simulation or exact-resume execution has
started in this packet.** The lead must supply the final source/native freeze,
actual final pilot files, CPU slot and a predeclared wall budget first.
Preparation imports no simulation or native module and spends no held seed.

## Plan and execution contracts

Planning requires a clean, exact source commit, intended source import path,
exact imported compiled native artifact SHA256 (never the package initializer),
recorded pilot source identity and
unchanged raw JSON/Arrow inputs. It validates all 120 completed turns, actual
seed/geography and explicit per-turn A6/health modes, then invokes the real
strict `cw_rework_screen.extract(..., expected_turns=120)` for AD. Old CW6
control extraction is not substituted. The plan retains all CLI arguments,
interpreter/source/native paths and hashes, tracked runtime input hashes,
pilot source/JSON/Arrow hashes, the selection and comparison semantics.

The selector gives priority to checkpoints immediately before and after the
first actual D3 wounded, released, evacuated and returned events. It then
chooses the completed-turn checkpoint covering the most still-uncovered
observed lifecycle categories, with earliest-turn ties, up to twelve points
per stratum. Categories include applied migration, recent residence arrivals,
a complete twenty-turn arrival window, army demand/requisition, actual seizure,
escrowed moving timber, named paid works, epidemic coverage, individual health
episodes, dated reports/paid guards, personal A6 memory, money transactions,
moving titled food and actual restitution. These are recorded state predicates,
not invented activation or asserted personal causal effects. The full active
turn lists, absent/unselected categories and unavailable checkpoint zero are
retained. No final-only checkpoint is called resumable.

Execution uses one subprocess at a time (`jobs=1`), hash seed zero and one
native/BLAS/OpenMP thread. It creates fresh same-source checkpoints, compares
plain versus checkpoint-writing runs, and resumes each selected checkpoint.
The adapter never unpickles an old-source checkpoint. Before and after every
subprocess it rechecks exact source/native/interpreter, tracked input hashes
and pilot input bytes. A finite positive fixed elapsed budget bounds subsequent subprocess
starts and times out an overrun; final pass also requires the complete execution
(including inventories/comparisons/final guards) to fit. Its clock starts after
strict plan revalidation, excluding import/planning. It does not alter the offline
chunk limit.
New output paths and at least 3 GiB available disk are required.

The existing comparator decodes the bundle and removes only
`metadata.generated_at`; ordinary outputs, including the untruncated Arrow
sidecar, compare as bytes. Its established exclusions are manifests, logs,
checkpoint files and absent precheckpoint per-turn validation JSON. The driver
additionally records every command, environment, exit, output SHA/size and
selected checkpoint SHA/size before successful temporary runs are removed.
It checks every raw Arrow SHA against the planned pilot and compares the
repeated straight bundle to that pilot using the same decoded timestamp-only
comparison. A pass therefore cannot silently select states from one trajectory
and test a different declaration. Original pilots are never modified.

## Reproduction after the execution gate

The same interpreter/native environment must be used for planning and running.
Use new output paths. The commands below are templates, not an execution record.

```sh
python docs/superpowers/progress/connected-world-rework-resume/driver.py.txt \
  self-check --output NEW/self-check.json

PYTHONPATH=SOURCE/src NATIVE/bin/python \
  docs/superpowers/progress/connected-world-rework-resume/driver.py.txt plan \
  --source-root SOURCE --expected-source FULL_COMMIT \
  --expected-native-sha256 NATIVE_SHA256 --pilot-source PILOT/source.txt \
  --bundle PILOT/runs/AD-t5/chronicle_bundle.json \
  --stratum template --seed 5 --output NEW/template-plan.json

# Only after the lead schedules the CPU slot and declares its timing budget:
PYTHONPATH=SOURCE/src NATIVE/bin/python \
  docs/superpowers/progress/connected-world-rework-resume/driver.py.txt run \
  --source-root SOURCE --plan NEW/template-plan.json --output NEW/template-run \
  --max-wall-seconds DECLARED_BUDGET
```

Repeat with procedural 19 and its actual `AD-p19` pilot. A changed driver must
produce a new plan; driver SHA is part of the execution guard. Missing active
categories remain limitations rather than a reason to alter the world or use
held worlds. Final compact reports and independent readback must be added after
actual execution; the preparation checks do not establish model or native
checkpoint correctness, scientific qualification or final CI.

Lead review found the initial package-initializer hash mistake and missing
NaN/infinity budget refusal before any execution. Both are corrected; the
retained preparation checks exercise those exact refusals and a positive
compiled-artifact hash fixture. Constructed bytes are never imported as native
code. Earlier preparation remains in Git history; no simulation result changed.

## Actual procedural pilot selection

The final corrected procedural-19 AD pilot passed the real strict extractor
and the source/import/native/pilot-byte guards. Its [exact plan](plan-p19.json)
is bound to clean runtime `8792be88dd36ba4d7c22e480de6a19dd64ea1300`, compiled
native artifact `b1d3ea5a…`, official CWR1 pilot identity `96f1efad…` and
adapter SHA256 `f68f71f7…`. Raw JSON SHA256 is `b9d42be3…`; Arrow is
`db300e20…`. Full values, input hashes and exact AD CLI are retained in the plan.

Selected completed checkpoints are **1, 2, 3, 18, 19, 67**. Every declared
lifecycle category is observed and covered, including complete recent-arrival
coverage, actual positive epidemic care, individual health episodes, paid
works, moving escrow, actual seizure and restitution. D3 wound/release first
occur at source turn zero; checkpoint zero cannot be resumed and those two
before boundaries remain explicitly unavailable. Actual evacuation has
before/after checkpoints 2/3 and return 18/19. This is a saved-state selection,
**not an executed exact-resume pass**. Template selection and all simulation
execution still await their separate gates.

This parse-only command exited zero, with no source, registry, pilot or
simulation changes:

```sh
PYTHONPATH=/workspace/cwr-final-runtime/src RAYON_NUM_THREADS=1 \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/workspace/cwr-native/bin/python /workspace/evidence/cwr-resume/driver.py plan \
  --source-root /workspace/cwr-final-runtime \
  --expected-source 8792be88dd36ba4d7c22e480de6a19dd64ea1300 \
  --expected-native-sha256 b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd \
  --pilot-source /workspace/evidence/cwr-evaluation/pilot-8792be88-v1/source.txt \
  --bundle /workspace/evidence/cwr-evaluation/pilot-8792be88-v1/runs/AD-p19/chronicle_bundle.json \
  --stratum procedural --seed 19 \
  --output /workspace/evidence/cwr-resume/plan-p19-8792-f68f.json
```
