# CWR1 exact-resume evidence adapter: prepared, execution pending

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
exact imported native artifact SHA256, recorded pilot source identity and
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
and pilot input bytes. A fixed elapsed budget bounds subsequent subprocess
starts and times out an overrun; it does not alter the offline chunk limit.
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
