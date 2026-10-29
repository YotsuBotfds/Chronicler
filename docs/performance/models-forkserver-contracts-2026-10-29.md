# Models-only launch contracts, 2026-10-29

This isolated branch implements stage 1 of the
[reviewed integration plan](https://github.com/YotsuBotfds/Chronicler/blob/6dfa2515a3cecdf04a61033263f0a174a6763f13/docs/performance/models-forkserver-integration-plan-2026-10-29.md),
against producer `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`.
It does not implement or activate a forkserver. Main, the frozen producer,
existing qualification controls and the consolidated review branch are unchanged.

`run_ablation_arms` now accepts the keyword-only `launch_backend="fresh"`.
Omitted or explicit fresh selection uses the original launch body, arguments,
manifest schema, output validation and whole-cohort checkpoint retirement.
The fresh path does not import the new contract module. There is no new CLI
option, gate forwarding, simulation configuration key or checkpoint field.

Any other selection is handled before the existing source/native probes,
destination check, directory creation or batch read. Unknown selections fail.
The prospective models-only selection checks one worker, lean output, the
20-turn measured window, unique needs/kin-roots arms, Linux CPython 3.13 and
pidfd/wait4 primitives, then **always refuses as unavailable**. These host
checks are preliminary eligibility, not a proof for the requested interpreter,
checkpoint, model preload or native binary. No fallback launches fresh workers.

The stdlib-only contract module defines immutable primitive job/outcome records
with closed payload fields, bounded opaque IDs and byte-bounded unchanged argv.
One batch contains one to eight unique jobs. Terminal outcomes must cover
submitted IDs exactly once; reordered results are restored to submission order.
Success requires return code zero and confirmed owned cleanup. Failed, cancelled
and unattempted states remain failure; missing, duplicate or unknown results
raise rather than qualifying an incomplete batch. No contract function runs a
job, imports models, reads checkpoints or certifies an actual process identity.

## Validation

Python 3.13.5, genuine no-native environment, CPU 3, thread caps one:

- New contract tests plus existing ablation output tests: **66 passed**, 0.36 s.
  Offline guard PASS; zero native modules/import attempts, blocked I/O or
  ecology/politics oracle calls.
- Complete modified `validation-tooling` selection: **276 passed**, 8.99 s,
  below the unchanged 110-second lane limit. Offline guard PASS; zero native
  modules/import attempts or blocked I/O. Existing tests made 61 calls each
  to the guarded ecology and politics Python oracle factories.

The focused command was `python -B -m pytest -q -x --tb=short
tests/test_ablation_launch.py tests/test_ablation_output.py
-p python_oracle_guard -p no:cacheprovider`; the second command uses the exact
ten files in the updated `validation-tooling` selection. Both used
`PYTHONPATH=src:scripts/testing`, disabled third-party pytest plugin autoload,
`PYTHONHASHSEED=0`, and external temporary/guard-receipt directories.

Tests check the blocked backend-import probe on successful fresh orchestration,
unchanged manifest shape, refusal before source/path probes, unsupported
configuration/platform cases, payload/UTF-8 bounds, immutability, exact coverage
and every non-success terminal state. Existing successful full/lean mocked
fork orchestration and failure/checkpoint-preservation assertions also pass.
The root agent independently reviewed the API diff and full contract/test
module before publication. `git diff --check` passes.

These are pure/source foundation checks. No backend process, metadata fork,
prospective simulation study or native build ran. Full integration CI and
current-source checkpoint/native/full-window proof remain unrun on this branch.
Adding even a dormant package file changes the checkpoint package digest;
later runtime qualification needs newly generated matching-source parents.
The earlier timing experiment does not qualify this source or establish a
speedup here. Controller ownership/preload checks, real CLI execution, bounded
process cleanup, source binding, outcomes and timing remain later stages.
