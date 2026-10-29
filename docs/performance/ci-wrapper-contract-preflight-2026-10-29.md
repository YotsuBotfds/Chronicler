# Turn-wrapper contract preflight — 2026-10-29

This source-only change adds two existing contract checks to each full Python
job after locked dependency installation. The native job checks them before
building its release wheel; the no-Rust job checks them before its full suite.
The jobs still run independently, with no new prerequisite runner.

The concrete failure was standard CI source `b35ccd7d`: both full Python lanes
failed only `test_result_wrapper_preserves_signature_and_arguments`, after
hundreds of seconds of suite work. Its signature assertion caught a private
keyword added to `run_turn_result` but missing from `run_turn`. Corrected source
`9d5cb7e4` passed all six existing jobs in run
[40831049842](https://github.com/YotsuBotfds/Chronicler/actions/runs/40831049842).
The new ordering targets this already observed failure; no timing saving has
been measured for the proposed workflow.

Each preflight selects exactly these nodes in a separate pytest process:

- `tests/test_practice_growth_observer.py::test_turn_wrappers_share_signature_and_forward_only_explicit_trace`
- `tests/test_turn_artifact_lifecycle.py::test_result_wrapper_preserves_signature_and_arguments`

The observer node checks parameter names, kinds and defaults, plus unchanged
ten-argument forwarding for omitted/`None` trace and explicit forwarding for a
trace token. The original lifecycle assertion is unchanged. Its `sample_world`
fixture constructs a `WorldState` model; its patched result function does not
advance a turn. These are not simulation or native qualification cases.

Both invocations use the existing offline guard, plugin autoload disabled and
the unchanged 110-second hard pytest limit with pipeline failure propagation.
The guard must report exactly two passes, no skips or failures, active native
and I/O blocking, no native import attempts, and zero ecology/politics factory
calls. The native build and real-native full suite run in later processes, so
the preflight's process-local guard cannot replace their runtimes.

Each lane uploads only its guard JSON, pytest log and JUnit XML in a separate
14-day artifact, including on failure:

- `wrapper-contract-native-<source SHA>`
- `wrapper-contract-no-rust-<source SHA>`

Successful future producers therefore publish seven artifacts instead of the
previous five. Exact-set readers must register the two additional artifacts
for that future source and count these two-node receipts separately from the
full-suite results. Sources `95f73a74`, `b35ccd7d` and `9d5cb7e4` retain their
original five-artifact contract. A preflight refusal may leave later suite or
wheel artifacts absent; its own bounded evidence is still retained.

All existing full-suite commands, offline chunks and their 110-second limits,
compiled-class/installed-wheel verification, original result/wheel artifact
paths, job dependencies and summary behavior remain unchanged. No simulation,
native, dependency, threshold or scientific policy source is modified.

Local qualification ran only the existing 27 workflow/wheel contracts under
the offline guard: 27 passed in 0.19 seconds, no skips, native imports, factory
calls or blocked I/O. Unfiltered actionlint and diff checks passed. The new
two-node preflight was not executed locally, and this workflow has not been
pushed or activated. No local World, native build or new simulation ran.
