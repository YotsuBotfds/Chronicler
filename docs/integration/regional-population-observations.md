# Regional population observations

`TurnSnapshot.regional_population` is an additive, version-1 observation inside
existing version-6 bundles and the existing live transport. It records actual
regional simulation entities, separately labelled native alive-agent counts,
and the earlier food denominator. It does not divide civilization totals among
regions, change simulation decisions, tick a runtime, or consume RNG.

## Identity and epochs

Every array position is the region's index in `world.regions`; civilization
IDs are positions in `world.civilizations`. Names are display values, not IDs.
Region positions are stable across conquest, migration and political births.
The completed snapshot labelled `T` describes source turn `T-1`. The payload is:

```text
regional_population?: {
  schema_version: 1,
  mode: "off" | "hybrid" | "shadow" | "demographics-only",
  source_turn: N,
  completed_turn: N + 1,
  timing: "completed_turn",
  counts: nonnegative_integer[],
  sources: (
    "python_region_state" | "hybrid_region_state" |
    "demographics_clamped_region_state" | "uncontrolled_region_state"
  )[],
  agent_counts: nonnegative_integer[] | null,
  agent_source: "native_region_alive_count" | null,
  food_weights: {
    source: "phase2_agent_pool",
    source_turn: N,
    timing: "phase2_entry",
    counts: nonnegative_integer[],
    controller_ids: (civilization_index | null)[]
  } | null
}
```

Each present array has exactly `len(world.regions)` elements. Count and source
arrays contain no null entries. `agent_counts` and `agent_source` are either
both present or both null. `food_weights` is either complete or null; a null
controller means unowned, unknown or ambiguous name identity. Unknown modes,
invalid model populations and unavailable demographics provenance do not produce
a fabricated envelope. Missing or malformed native batches produce null native
counts, without replacing them with model population. Missing Phase 2 rows or
an economy that did not run produce null food weights. Old snapshots omit the
whole field and remain unknown; the final world's population is not their
historical population.

`counts` is copied from each completed `Region.population` after all turn
consequences. Its model lineage depends on the selected mode:

| Mode | Completed model population | Per-region source |
| --- | --- | --- |
| off, including saved `None` mode | Actual Python regional entities | `python_region_state` |
| shadow | Actual Python regional entities; the native pool runs alongside them | `python_region_state` |
| hybrid | Actual regional state after raw alive-count bridge writeback and subsequent consequences | `hybrid_region_state` |
| demographics-only, controlled at writeback | Actual regional state after `min(alive_count, floor(1.2 * carrying_capacity))` and subsequent consequences | `demographics_clamped_region_state` |
| demographics-only, uncontrolled at writeback | Retained regional model state and subsequent consequences | `uncontrolled_region_state` |

The demographics provenance is captured immediately after bridge writeback,
before Phase 10 politics can transfer control. A source label describes model
lineage; it does not attribute the cause of a population delta. Later legitimate
regional writes are reflected in completed `counts`.

In all three agent modes, `agent_counts` comes from the native
`get_region_populations()` reader at completed snapshot capture. That native
`&self` method counts alive agents by their physical region and returns dense,
ordered rows including empty and uncontrolled regions. These counts include
the tick's births, deaths and migrations. They can differ from the model's
population in shadow or demographics-only mode. Without an available pool,
they are null. Aggregate mode does not read a pool.

## Food weighting

`food_weights` copies the already-obtained Phase 2 input snapshot's alive rows
and the controller IDs at that same boundary, before the economy runs. It is a
detached immutable turn-local handoff, published only if the economy ran. It
adds no native snapshot query. The population and controllers at completion
must never stand in for these earlier values: agents can move, be born or die,
and regions can change hands later in the turn.

The native food demand is Phase 2 alive population times the common configured
per-capita food rate. Therefore a population-weighted mean of the recorded
regional food sufficiency can use these weights. Attribute a civilization's
food observation using the Phase 2 `controller_ids`, including regions it lost
later that turn. Do not use completed ownership. Any positive-weight region
with missing food sufficiency makes a complete weighted mean unavailable;
a zero total denominator is also unavailable. Unknown controllers cannot be
assigned to a civilization. The existing sufficiency is clipped to 0–2 and
rounded to two decimals for export, so its weighted mean is a mean of recorded
regional sufficiency, not an exact physical food inventory ratio. Existing
unweighted food metrics remain compatible and explicitly unweighted.

## Transport and historical compatibility

The model field defaults to `None` and is omitted while absent. Existing saved
history and pre-feature exact checkpoints remain readable without backfilling
observations. Newly completed turns receive the field. It is registered in
`transport_contract.json` so static bundles, Batch Lab, live turns, reconnect
and checkpoint-carried live history preserve it. Generic snapshot pruning and
version-6 delta encoding already preserve arbitrary registered fields; no
container codec or container/transport version change is required. The nested
`schema_version` versions this observation independently.

Newly generated bundle/history exports intentionally differ by this one field.
Exact checkpoints containing that exported history also differ in their body;
source/package identity metadata naturally identifies the changed Python source.
Simulation state, decisions, native persisted state, existing exported fields
and controlled RNG behavior are unchanged.

Strict test-only literal inverses in
`scripts/testing/regional_population_witness.py` recover the complete c04 parent
modules before applying existing care, canonical-default and shipment witnesses.
All historical hash literals and both prior shipment JSON witnesses remain
unchanged. Missing/changed insertion context and unrelated source mutations
fail; the new observation source is separately hashed. These source projections
are not native or scientific qualification.

## Verification, 2026-11-02

Source is the isolated `feat/codex-regional-observations-20261102` worktree based
on `c04b32adef05e54c46f597d9fece9568e719c7c7`. Python 3.13.5 uses the existing real
`32ac5879` native build, with unchanged Rust tree
`edb263686adb7ea5e23864146a5f7d0c5a163da4` and compiled binary SHA-256
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
No shared build or installer was invoked.

- Focused Python/native, model/epoch/transport, main/checkpoint/live and historical
  source-witness checks: **577 passed, 61 successful subtests, one existing
  weak-reference mock skip**. One existing deliberate malformed care-value
  serializer warning remains. New real-native observation tests pass in hybrid,
  shadow and demographics-only modes, preserving checkpoint bytes, snapshot-cache
  state, world, bridge members and global RNG.
- The new bounded offline `regional-population` chunk: **32 passed**, guard PASS,
  zero native loads or attempted imports, zero blocked IO, the existing 110-second
  cap retained. Existing chunks and their selections/caps are unchanged.
- Matched actual parent/current seed-42 runs, 16 turns, four civilizations and
  eight regions, in all four modes: **PASS**. Only `regional_population` was
  removed from decoded bundle history for comparison. All 9/10/11/9 remaining
  artifacts, every completed snapshot, full world, selected actions, primitive
  Python RNG trace and controlled global RNG match. Every native completed-turn
  checkpoint byte hash matches; callbacks also verify that main's observation
  did not change native bytes.
- Same-source exact turn-8 continuation to turn 16 in all four modes: **PASS**;
  all existing artifacts, full history including the new field, completed world
  and native final bytes match the uninterrupted run.

The focused command selected:

```sh
python -m pytest -q -rs tests/test_regional_population.py \
  tests/test_regional_population_native.py tests/test_historical_parity.py \
  tests/test_bundle_codec.py tests/test_turn_artifact_views.py \
  tests/test_turn_artifact_lifecycle.py tests/test_turn_artifact_runner.py \
  tests/test_practice_observer_runner.py tests/test_public_grain_shipments.py \
  tests/test_health_care_policy.py tests/test_main.py tests/test_run_checkpoint.py \
  tests/test_live_checkpoints.py tests/test_live.py tests/test_state_checkpoints.py
```

External evidence is retained under
`/workspace/shared/chronicler-regional-population-evidence-20261102`: focused and
guarded logs/receipt, immutable c04 source archive, parent/current drivers and
per-mode reports, and exact-resume reports/artifacts. The initial new-suite
failure was an incorrect test author's expansion of the abbreviated parent SHA;
the actual c04 SHA corrected the assertion before the reported passing checks.

Full fresh CI, all Rust tests, the full exact-checkpoint matrix and scientific
qualification were not run for this observation-only change. Native reuse is
qualified here by matching build inputs and binary identity, not a fresh build.
