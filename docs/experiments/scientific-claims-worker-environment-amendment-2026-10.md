# Prospective worker-observation metadata amendment

This observer-only amendment is recorded before the first natural-world
science executions. The simulation remains frozen at `d051d7c0` in its own
checkout. The [registered development cohort](scientific-claims-development-2026-10.md)
keeps seeds 42–43, template 8/4, horizon 60, completion-turn-1 parent forks,
all four complete information arms and one worker. No trial, horizon, control,
eligibility rule, checkpoint requirement or output oracle changes here.

The external runner now emits worker-identity schema 2. Each actual worker
records `before.environment` before checkpoint restoration/configuration and
`after.environment` in its completion/failure cleanup using the source-owned
`environment_identity()`. These observations include interpreter, platform,
CPU/affinity metadata, relevant package versions, hash-seed and thread
environment. They accompany the existing source/native identities and an
external runner SHA-256 before/after. A measured environment or runner change
makes the worker fail, alongside the existing source/native guard.

The parent runner verifies the worker's actual hashed sidecar before calling
an execution complete. It recomputes stability and checks that source/native
identity matches the simulation receipt; stability booleans alone are
insufficient. Failed workers retain their observed receipts and original
error. The study manifest records the worker identity schema and separately
hashes the external runner. Its worker executes the same frozen simulation
source through `--source-root`; changing this external metadata collector
does not rewrite the simulation checkout.

The orchestration parent's environment and checkpoint header remain separate
observations. Their thread settings can intentionally differ from a worker,
so the actual child environment is not inferred from them. Paired-arm
comparisons must read the hashed actual worker observations. Existing 24-run
evidence is preserved without rewriting files or inventing missing historical
worker environment values. This amendment adds evidence about execution; it
does not qualify benefit, performance or independence.

The focused helper/runner selection passed 48 tests under the offline guard
in 2.30 seconds before the first natural science execution. Those deliberate
unit fixtures check actual metadata capture, runtime/package/thread/affinity
drift, failed-worker cleanup, forged stability flags, missing receipts and
source/native/external-runner mismatches. The guard loaded no native modules
and observed no network or child-process attempts. These fixtures do not
substitute for the actual ten registered executions.
