# A01 slice 3: runner cutover and persistence evidence

Base: `2ab3b4814abb665c7b3d5c255152cf5767bbf25a`, tree
`46f0e042302f33865b76bd71d5b1b2c3dcda1b4f`. Branch: `a01/slice3-runner`.
The exact reviewed A01 contract owns the interfaces and merge order.

`main.execute_run` calls `simulation.run_turn_result` with the existing arguments.
It checks the explicit opening source turn and completed turn, keeps text as a
plain string, and reads `observation.phase10_agents` at the old urban extraction
point. Required `civ_affinity`/`settlement_id` accesses and optional `region`
fallback preserve the original order, exceptions, coercions, and arithmetic.
Urban assignment combines the historical rows with current end-turn region
controllers. Snapshot schema, intelligence/perception code, narrator callbacks,
seed arithmetic, final settlement detection, and output save timing are unchanged.
The result, row view, and decoded column references are released before `on_turn`.

The internal injection seam is now `chronicler.main.run_turn_result`; the three
owned fixture seams return explicit `TurnResult`/`TurnObservation` values.
Public `simulation.run_turn(...) -> str` remains the coordinator slice's API.
This patch never implements or replaces that production wrapper.

Checkpoint guards retain every previous rejection and the existing source hash
algorithm. Comments make the dependency on agent mode, bridge and economy
explicit after the two snapshot/name aliases retire. Legacy aliases still fail
closed when supplied by old/staged callers. The guard tests include empty named
registries, absent aliases in every agent mode, and adding a source module to
change identity and reject a checkpoint. Native/hybrid continuation remains
unsupported. There is no serializer migration or new WorldState field.

## Staging and integration

Slices 1 and 2 are absent from this checkout. Production imports intentionally
require their reviewed APIs; do not deploy this isolated slice. No fallback is
installed by production code. The explicitly enabled `scripts/a01_test_doubles.py`
pytest plugin supplies only the missing contracts and wraps the existing
coordinator for standalone tests. It aborts if either real interface exists.
Its source hash and use are recorded by the capture harness. Doubles are
scaffolding, not proof about real AgentRows caching or the migrated coordinator.

Parent single-writer integration must apply reviewed slice 1, then slice 2, then
this slice; finally the coordinator owner removes `_agent_snapshot` and
`_named_agents` publication in its own file. Keep `_economy_result` at its old
publication point for the prior-turn Phase-5 gate and checkpoint rejection.
This slice edits no coordinator, bridge, settlement, scientific, native, runtime
protocol, seed registry, detached governance, or blocked G05/serialization code.
No ownership conflict was encountered. Dependencies are not an invitation to
silently edit another slice.

Standalone verification (test-only doubles are explicit):

```sh
PYTHONPATH=scripts:src /path/to/python3.13 -m pytest -p a01_test_doubles -q \
  tests/test_turn_artifact_runner.py tests/test_main.py \
  tests/test_integration_snapshot_lifecycle.py tests/test_performance_equivalence.py \
  tests/test_checkpoint_replay.py tests/test_models.py tests/test_simulation.py \
  tests/test_tech_focus.py tests/test_artifact_io.py tests/test_settlements.py \
  tests/test_culture.py tests/test_religion.py tests/test_great_persons.py
```

After integration use the same command **without** `-p a01_test_doubles`; use the
actual slice-1/2 lifecycle/view tests too. Frozen performance goldens are unchanged.
Their historical oracle source is still `423a67c`; they are relevant regression
coverage, not an A01 exact-head replay proof.

## Replay and artifact comparisons

Use the same `scripts/a01_acceptance.py` driver and interpreter in separate
processes. It accepts an existing saved Python input or a named existing
performance regression fixture (`single`, `standard`, `wide`). It introduces no
new study world or parameter/seed set. Native ecology/politics presence and
unsupported initial agent state are rejected, rather than silently disabled.
Reports preserve runtime/package identities, current and Git-object Python/native
source hashes, input hashes, driver hash, and explicit doubles use. Baseline must
be the clean exact `2ab3b48` with bytes matching its Git tree, including files
hidden by status flags.

```sh
PY=/path/to/python3.13
DRIVER=/path/to/slice3/scripts/a01_acceptance.py
$PY "$DRIVER" capture --source-root /path/to/exact-2ab3b48 \
  --fixture single --split 5 --report-dir /fresh/before-single
# Isolated slice only: add --test-doubles. Integrated candidate: omit it.
$PY "$DRIVER" capture --source-root /path/to/candidate \
  --fixture single --split 5 --report-dir /fresh/after-single
$PY "$DRIVER" compare --baseline /fresh/before-single --candidate /fresh/after-single
# Existing admitted Python saved input, unchanged and read-only:
$PY "$DRIVER" capture --source-root /path/to/candidate \
  --state /path/to/approved-python-input.json --turns 20 --split 5 \
  --report-dir /fresh/input-after
```

All output directories must be new. The harness stores complete per-turn
snapshot/text/ordered events/named events/world, deterministic narrator inputs,
ordered RNG seed/random/getrandbits traces, and complete artifacts recursively.
Only the pre-existing fixed `bundle.metadata.generated_at` convention is used.
Comparator revalidates artifact manifests against the actual files, including
extra nested files, and reports the first divergent record/field or byte encoding.
JSON diagnostics distinguish signed zero; byte hashes remain authoritative.
It compares split/uninterrupted checkpoint digests separately in each source,
then across sources; checkpoint envelopes themselves must differ in source
identity. Direct cross-source load must still fail with a runtime mismatch.
No golden regeneration is performed.

## Resource and native acceptance boundaries

Each capture warms the existing fixture, records three paired-compatible whole
run timing samples including artifact I/O and the span between coordinator return
and snapshot callback, and measures current/peak tracemalloc bytes separately.
It records peak process RSS (Linux KiB), callback/end live AgentRows counts, and
C-call diagnostics for Arrow `to_pylist`/native `get_snapshot`. The diagnostic
observer does not replace Arrow batches, native runtimes, seed construction, or
simulation methods. Decode records include caller/line/source-turn, and resolve
batch/column/schema/row-count from caller-local batches by buffer identity when
possible. Ambiguous/unavailable identities and stages remain explicit. Native
getter return batches are not observable through this C-call observer; exact
phase/getter-return evidence requires a compatible in-process native harness.
Zero calls in Python off mode cannot prove native call parity or allocation savings.

```sh
# Repeat final paired captures with --repetitions 3 (default); alternate process
# order across repetitions when collecting timing evidence for integration.
$PY "$DRIVER" capture --source-root /path/to/exact-2ab3b48 \
  --fixture standard --report-dir /fresh/before-standard --repetitions 3
$PY "$DRIVER" capture --source-root /path/to/integrated-candidate \
  --fixture standard --report-dir /fresh/after-standard --repetitions 3
```

Compatible reviewed native binary plus admitted **in-process** starting inputs
are unavailable here. Hybrid/shadow/demographics evidence is BLOCKED, including
getter order/phase distinction, per-batch decode reduction, real cache allocations,
and no retained-cache growth across turns. A raw WorldState JSON cannot reconstruct
native RNG/pool/merchant/memory state. The harness never sets full
`integrated_acceptance` true; its narrower `integrated_python_off_acceptance`
requires real interfaces and exact parity. Speed is diagnostic, not a correctness
gate; no speedup or native memory benefit is claimed.

## Rollback

Before parent integration record the integration checkout's existing HEAD. On
parity mismatch revert the consumer/result-path commits together (all three
slices plus coordinator alias cutover); do not revert only the runner against an
API-incompatible coordinator or keep a mixed set of aliases. A fresh checkout
of exact `2ab3b48` is the unambiguous rollback starting point. Artifacts never
serialize, so no persisted migration is needed. A failed turn has mutated its
world and is not retry-safe; restart only from an existing supported same-source
Python checkpoint or an approved native starting fixture. Old-source checkpoint
imports remain rejected.
