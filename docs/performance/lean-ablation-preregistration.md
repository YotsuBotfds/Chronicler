# Lean ablation output: equivalence contract

Registered before production edits, against `ac38e80e`, 2026-10-28.
This is an exact output-policy experiment, not a change to simulation or causal
qualification. No performance gain is claimed before paired measurements.

## Candidate boundary

Add an explicit internal output profile for exact-checkpoint ablation workers.
The ordinary/default profile remains unchanged. The first implementation skips
unused **post-run** exports: full history bundles, final raw world state,
compiled prose and observational language/archive exports. It writes the same
small `fork.json` metadata that the existing cleanup derives from the bundle.
The complete agent event stream and its prefix remain available.

Retain the entire turn loop and its runtime data: world/events, inherited
history, snapshot construction, memory updates, reflections, historiography,
language observation, final-turn forced settlement detection, existing periodic
writers, checkpoints, per-turn callbacks, final native sidecar snapshot and
writer close. Do not trim history or archives, change ablation timing, reduce
the 20-turn causal window, or infer that a writer is harmless without proof.
More invasive retention/serialization changes are separate experiments.

The hidden CLI profile is output-only, explicitly overridable at exact resume.
Lean output requires a compatible exact checkpoint, simulation-only execution
and a recorded decision-ablation arm. Interactive/live/presentation paths are
outside its intended scope. Default calls do not acquire a lean receipt or
different artifact content. The ablation manifest retains its current schema,
identities, seed/fork/window rules and input hashes.

## Required equivalence

1. From the same checkpoint and compatible native binary, full and lean arms
   execute the same source turns through `fork_turn + window + 1`; completion
   labels and final settlement behavior are unchanged.
2. At every observed turn boundary, compare physical WorldState fields, native
   checkpoint bytes, pending signals and event order. Compare full final run
   state in a controlled verification hook. The profile cannot alter RNG state
   or the inputs consumed by another turn.
3. Before and after identical event compression, `agent_events.arrow` has the
   same schema, complete prefix and rows/bytes. `fork.json` has the same seed,
   total horizon, decision-ablation record and resume label.
4. Exercise actual `run_ablation_arms`, its output cleanup/manifests and the
   downstream needs/cohort ablation readers. All oracle results, diagnostics,
   exposed cohorts and window counts must match on the same retained inputs.
5. Wrong horizons, missing receipts/events, nonzero worker exits, malformed
   output and incomplete forks remain visible failures. Preserve failure logs
   and artifacts; do not overwrite an existing output root or delete required
   checkpoints after a failed study.
6. Default/full output retains existing file content (timestamps and source/
   build provenance have their normal identity rules). Existing full/no-Rust,
   checkpoint and manifest tests continue to exercise the ordinary path.

## Measurement plan

Freeze the candidate source before timing. Use the same identified release
extension and one-thread environment in both arms. First compare an early and
late checkpoint, then several arms/seeds through the actual orchestrator. Ask
the lead for a quiet benchmark window after the current gates and suites.

Alternate full/lean order across fresh processes and destinations, with at
least five paired repeats per retained checkpoint. Record whole-worker and
whole-orchestrator elapsed/CPU time where available, bytes produced before
cleanup and bytes retained, checkpoint/import/restore context, compression and
cleanup. Report raw pairs and noisy/inconclusive effects. A smaller export
boundary alone is not evidence of an end-to-end wall-clock speedup.

No seed count, horizon, oracle method/threshold, causal criterion or offline
110-second chunk limit changes. New tests must fit an existing chunk or receive
a separate bounded chunk. Native code is outside this candidate's edit scope.
