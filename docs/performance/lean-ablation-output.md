# Lean exact-checkpoint ablation output

The internal `--ablation-output` profile omits only post-run presentation
exports that the ablation orchestrator immediately deletes: the compiled
chronicle, final raw world save, viewer bundle and observational language and
historiography exports. Ordinary execution defaults to the existing full
profile. This implements the boundary registered in
[lean-ablation-preregistration.md](lean-ablation-preregistration.md).

The profile requires a compatible exact checkpoint, a decision-ablation arm,
`--simulate-only` and the local narrator. It is output-only and may override the
parent checkpoint's ordinary output profile. It changes no simulation settings.
`run_ablation_arms` uses it by default; `lean_output=False` or the orchestrator's
`--full-output` retains the full worker path for comparison.

Every turn, snapshot, event, inherited history record, memory update, reflection,
periodic writer and checkpoint still runs. Final-turn forced settlement
identification, the final native validation snapshot and writer close remain
in the same order. The lean path calls the existing event Arrow writer directly
and writes the existing four-field `fork.json` receipt. The full path continues
to obtain the event file through `write_bundle`. Compression and retained files
are identical. This first slice deliberately leaves periodic state/memory
serialization in place; further changes need their own equivalence proof.

Before compressing or deleting any output, the orchestrator checks the actual
receipt's seed, completed horizon and exact arm/start/fork turn. Missing or
malformed receipts, event serialization errors, worker launch errors and nonzero
exits produce a failed manifest and preserve that fork's artifacts and logs.
Plain checkpoints are deleted only after the whole study succeeds, so a later
seed's failure cannot erase an earlier seed's retry inputs. Existing output
roots remain protected against overwrite. Manifest schema, identities, seed and
fork rules, 20-turn windows, input hashes and causal criteria are unchanged.

## Focused correctness evidence, 2026-10-28

Source base `ac38e80e`; candidate worktree `lead/lean-ablation`; no native edits.
The preregistration was committed as `c79dcea2` before production edits.
The qualified extension SHA-256 was
`e7ec77283075cb9b817ad47490fc98a3e77685451bbcd4ce8f5b8bcad9db5867`.
Both candidate and qualified source have Rust tree
`adbe580cbeda6843b77d335e73e1ae10f7be6a9f`.

- **55 tests passed in 4.10 s:** profile restrictions and resume classification,
  ordinary decision-ablation/manifest checks, both orchestrator output paths,
  wrong horizon/seed/arm, missing receipts/events, launch failures, worker exits,
  failed manifests, retained checkpoints and no-overwrite destinations.
- **2 real native tests passed in 27.09 s:** one shared 9-turn checkpoint forked
  to completion 18, comparing every completed boundary and final state. All
  persisted world fields, entire native checkpoint bytes (including queues and
  RNG), memories, inherited history, chronicle entries, reflections, pending
  injections, turn seeds and forced-settlement calls match. Language and
  historiography systems were enabled. Raw and compressed event bytes and
  `fork.json` bytes match.
- The second native fixture executes actual `run_ablation_arms` subprocesses
  from a 101-turn checkpoint through completion 122, for `needs` and `kin_roots`,
  full and lean. Manifest input hashes, complete event prefixes, fork receipts,
  needs/cohort results, diagnostic counts and 20-turn windows match through the
  actual downstream loaders. It uses one seed for equivalence, not scientific
  qualification or an effect estimate.

Initial fixture failures were corrected before the passing result: the carried
memory object is not a Pydantic model; parent/child thread environments must
match; the explicit local narrator belongs in a programmatic checkpoint's
output settings. The first real test also caught the required event writer
being coupled to bundle output; the lean path now invokes that unchanged writer.

Commands used one-thread environments and the qualified interpreter, with this
worktree's `src` first on `PYTHONPATH`:

```sh
python -m pytest -q tests/test_ablation_output.py tests/test_decision_ablation.py tests/test_batch_manifest.py
python -m pytest -q tests/test_ablation_output_native.py
```

These correctness runs were under concurrent host load. They establish no
wall-clock improvement. Whole-worker and whole-orchestrator paired measurements
remain required on immutable source in a reserved quiet window; report output
bytes before cleanup and after retention separately. No full milestone gate is
claimed by this output-policy fixture.
