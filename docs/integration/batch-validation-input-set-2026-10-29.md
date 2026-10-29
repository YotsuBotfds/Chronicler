# Verify added batch oracle inputs, 2026-10-29

The isolated branch `lead/batch-validation-input-set-20261029` closes a saved
batch verification gap. Previously, adding a sidecar after the manifest had
recorded a run could change the oracle inputs while the batch still reported
`verified`: the verifier checked recorded hashes but not newly present inputs.
For example, an unrecorded `validation_summary.json` was accepted and then
selected by the reader. The defect was reproduced without simulation.

Verification now enumerates validation inputs beside each actual bundle,
using the same input discovery function as the manifest writer. Every present
input must have a recorded hash for that run. Existing checks still require
the recorded bytes and reject missing inputs. Unrelated state, memories, prose
and diagnostic files can still be added or pruned. The manifest schema,
recording code, physics, RNG, output serializers, oracle policies and legacy
no-manifest behavior are unchanged. This checks the file set at verification
time; it does not establish a locked or immutable read session.

## Validation

The eleven new pure cases cover every fixed sidecar, recursive legacy JSON,
another seed's hash, exact recorded bytes and unrelated exports. Against the
unchanged producer, nine defect regressions fail and two compatibility cases
pass. Against the correction, the focused manifest files pass **35 tests**.
A real short-batch regression also requires rejection before Arrow decoding.
The complete modified offline `validation-tooling` chunk passes **237 tests**
in 6.58 seconds including startup, below the unchanged 110-second limit.
Both candidate guard receipts pass, with no native modules, native import
attempts or blocked I/O. Their existing aggregate simulation cases use the
guarded Python runtime factories.

The checks used Python 3.13.5, CPU0 and one-thread numerical settings.
External evidence is retained in
`/workspace/chronicler-recovered-evidence/batch-input-set-20261029`, including
commands, source hashes, decoded logs and guards. The first attempted baseline
run accidentally selected the candidate through pytest's configured `src`
path; its result remains recorded. The corrected baseline explicitly overrides
that setting and produces the nine expected failures. No simulation cohort,
native build or scientific gate was rerun to reproduce this defect.

An independent source review checked the actual reader's bundle-parent path,
per-run set difference, compatibility and test coverage and found no blocker.
Exact source `e984be2adc2e6fdf27b4442b852a9e6789b6617b` subsequently passed
all six CI jobs in run 40801509650. The
[source-scoped CI record](batch-verification-ci-2026-10-29.md) preserves its
counts, clocks and official publication metadata separately from the later
cohort reconciliation. Earlier CI at `1c5728b7` qualifies the preceding review
code. The frozen producer and active full-gate controls remain unchanged.
