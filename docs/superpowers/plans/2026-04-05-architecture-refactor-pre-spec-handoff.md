# Architecture Refactor Pre-Spec Handoff

> Date: 2026-04-05
> Audience: spec-writing / question-gathering agent
> Purpose: lock an implementation-ready handoff for the current non-rewrite architecture follow-ups that are worth moving forward now.

## Status Snapshot

- This is a doc-only handoff pass, not an implementation plan.
- The recommendation below is based on a live-tree review of:
  - `src/chronicler/simulation.py`
  - `src/chronicler/models.py`
  - `src/chronicler/agent_bridge.py`
  - `src/chronicler/action_engine.py`
  - `src/chronicler/main.py`
  - `src/chronicler/politics_bridge.py`
  - `docs/superpowers/plans/2026-03-21-post-m51-refactor-waves.md`
  - `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`
  - `docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md`
  - `docs/superpowers/design/phase8-9-brainstorm-synthesis.md`
- The current code already shows the pressure points these refactors are trying to relieve:
  - `run_turn()` is still about a 400-line coordinator
  - `phase_consequences()` is another roughly 320-line mixed phase function
  - `AgentBridge` still owns about 1500 lines inside a ~2350-line module
  - turn-local and carry-over scratch state is split across `WorldState`, `AgentBridge`, and ad hoc private attributes
- All six items below are worth moving forward with.
- Phase 8/9 forward compatibility makes the first four items more valuable, not less.

## Recommendation Summary

Move forward with these six items:

1. typed `TurnArtifacts` / `TurnContext` for turn-local orchestration state
2. `run_turn()` coordinator split without behavior change
3. `agent_bridge.py` split by responsibility
4. authoritative bridge-contract module plus ratchet tests
5. gradual Pydantic peel-out for runtime-only structures
6. continued Phase 7.5 thin-client / query-oriented viewer direction

Adjacent follow-ons that should stay separate from this pass:

- pre-M63 modifier-composition refactor for action weights
- small rules-foundation follow-up for Phase 8 crisis and institution chains
- any large `WorldState` redesign
- any big-bang viewer rewrite before the M61b gate

## Cross-Cutting Guardrails

- Preserve runtime behavior unless a later spec explicitly chooses otherwise.
- Preserve the `--agents=off` aggregate baseline.
- Preserve the existing hybrid accumulator contract:
  - Phase 10 in hybrid still uses the accumulator watermark
  - bundle consumers remain agnostic to whether final stats came from aggregates or agents
- Preserve the repo's one-turn lag discipline for cross-system signals.
- Do not collapse three different categories into one abstraction:
  - turn-local artifacts
  - cross-turn carry state
  - hot-path caches
- Keep export-plane work separate from engine refactors unless a spec explicitly owns both.
- Favor additive seams over replacement.

## Phase 8/9 Forward-Compatibility Lens

The Phase 8/9 planning docs make three constraints especially important:

1. Cross-system signals should keep the N -> N+1 lag pattern.
2. Ownership of bridge payloads and signal families should be explicit.
3. Action-weight composition must stop growing as hidden local multiplication before institutions land.

Implication:

- `TurnArtifacts`, `run_turn()` decomposition, and bridge contracts help protect signal timing and ownership.
- `agent_bridge.py` splitting helps keep Phase 8 additions from concentrating even more logic in one file.
- runtime-only dataclasses help keep new Phase 8/9 structures out of the hottest mutable `BaseModel` paths.
- viewer work should keep additive typed extension points for M63-M73 layers, not reopen browser-side monolithic parsing.
- modifier composition is important for Phase 8, but should stay a separate spec instead of being folded into these six items.

## Recommended Ordering

If these are spec'd as separate implementation branches, the recommended order is:

1. `TurnArtifacts` / `TurnContext`
2. bridge-contract module plus ratchet tests
3. `run_turn()` coordinator split
4. `agent_bridge.py` responsibility split
5. runtime-only dataclass peel-out
6. Phase 7.5 viewer thin-client/query-oriented continuation after the existing gate

Reason:

- Items 1-4 reduce hidden coupling before new systems add more of it.
- Item 5 is easier once the explicit seams exist.
- Item 6 is directionally locked already, but remains gated on the existing Phase 7.5 entry conditions.

## 1. TurnArtifacts / TurnContext

### Why this should move forward

The live code is already using hidden turn scratch fields as a de facto turn-context object:

- `simulation.py` writes `_agent_snapshot`, `_named_agents`, `_economy_result`, `_conquered_this_turn`, and `_dead_agents_this_turn`
- `action_engine.py`, `main.py`, `settlements.py`, and `politics_bridge.py` read some of that state later
- `models.py` currently formalizes only part of the transient surface (`pending_shocks`, `agent_events_raw`, settlement candidates), while other state lives as undeclared private attributes on `world`

This is not just style debt. It makes phase ownership and same-turn data flow harder to reason about.

### Scope recommendation

Add a new `src/chronicler/turn_artifacts.py` module with one explicit turn-local container.

Recommended first-pass contents:

- agent snapshot for same-turn Phase 10 readers
- named agent map for narration / religion consumers
- economy result for same-turn consumers
- conquered civ ids for the bridge tick
- dead-agent records for martyrdom / religion consumers
- phase-local event buckets or checkpoints if helpful

Recommended API direction:

- `run_turn()` creates the artifact object at turn start
- helpers receive it explicitly when they need turn-local data
- `run_turn()` remains the owner of lifecycle and reset semantics

### Important gotcha

Do not put every private `world._...` value into `TurnArtifacts`.

These do not belong in the same bucket:

- `pending_shocks`: carry-over state consumed next turn
- `_prev_belief_distribution`: cross-turn comparative state
- `_prev_priest_counts`: cross-turn comparative state
- `_treasury_tax_carry`: cross-turn fractional carry state
- `_persecuted_regions`: persistent one-shot suppression memory
- `region_map` / `civ_map` / trade-route caches: caches, not phase artifacts

The spec should explicitly separate:

- turn-local artifacts
- turn-to-turn carry state
- caches

### Main targets

- `src/chronicler/simulation.py`
- `src/chronicler/models.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/main.py`
- `src/chronicler/settlements.py`
- `src/chronicler/politics_bridge.py`
- `src/chronicler/turn_artifacts.py` (new)

### Questions the spec should lock down

1. Which fields are truly turn-local versus cross-turn carry state?
2. Should `pending_shocks` remain on `WorldState` for now or move into a separate carry-state helper?
3. Should the artifact object be immutable after construction, or mutable but coordinator-owned?
4. How much of the artifact surface should be visible to Phase 10 helpers versus only to `run_turn()`?

### Minimum validation shape

- focused `run_turn()` tests proving same-turn consumers still see the right snapshot/economy data
- multi-turn tests proving no stale transient state leaks across turns
- parity coverage for `--agents=off`, shadow, demographics-only, and hybrid where relevant

## 2. run_turn() Coordinator Split

### Why this should move forward

`run_turn()` currently owns:

- turn-start cleanup
- pending injection draining
- economy orchestration
- Phase 1-9 execution
- bridge sync / bridge tick coordination
- transient-state stashing
- pre-Phase 10 timeline commit ordering
- Phase 10 accumulator watermark handling
- post-Phase 10 cleanup

That is too much coordination logic for one function, especially with Phase 8/9 adding more signal families and crisis/state interactions.

### Scope recommendation

Keep `run_turn()` as the public orchestration entrypoint, but split it into smaller coordinator helpers.

Suggested slice boundaries:

- `_prepare_turn_state(...)`
- `_run_pre_bridge_phases(...)`
- `_run_bridge_handoff(...)`
- `_prepare_phase10_inputs(...)`
- `_run_phase10_and_flush(...)`
- `_finalize_turn_state(...)`

The names do not matter much. The seam clarity does.

### Non-goals

- do not change the phase order
- do not change the bridge tick placement
- do not change the accumulator routing contract
- do not mix this with a large CLI or runner split

### Main targets

- `src/chronicler/simulation.py`

### Spec questions to resolve

1. Which helper boundaries reduce complexity without spraying a dozen new tiny functions?
2. Should `phase_consequences()` itself be split in the same pass, or only after `run_turn()` is decomposed?
3. Which helpers should accept `TurnArtifacts` explicitly versus reading from `world` for legacy compatibility?
4. Which same-turn ordering contracts need top-level assertions or comments because they are easy to break?

### Contracts the spec should name explicitly

- economy runs before automatic effects
- ecology write-back happens before the bridge tick
- conquered civ markers are cleared immediately before bridge consumption
- pre-Phase 10 events hit `events_timeline` before Great Person and faction consequences
- hybrid Phase 10 uses accumulator watermark plus second keep flush

### Minimum validation shape

- regression tests around event ordering and timeline visibility
- regression tests around pending-shock carry-over
- regression tests around off-mode Phase 10 behavior
- regression tests around settlement detection placement and bridge tick ordering

## 3. agent_bridge.py Responsibility Split

### Why this should move forward

The Rust FFI layer has already been split into focused modules. Python has not caught up.

Today `agent_bridge.py` mixes:

- Arrow batch builders
- signal builders and validation
- simulator configuration
- snapshot metrics and readback
- event conversion and named-character materialization
- write-back
- sidecar export
- stats history normalization

That concentration will get worse when new signal families and observability surfaces arrive.

### Scope recommendation

Keep `AgentBridge` as the public coordinator class, but move pure or mostly-pure responsibilities out into focused modules first.

Recommended split target:

- `src/chronicler/bridge_batches.py`
  - region batch builder
  - settlement batch builder
- `src/chronicler/bridge_signals.py`
  - civ-signal validation
  - signal RecordBatch construction
- `src/chronicler/bridge_snapshot.py`
  - snapshot readers
  - gini / wealth / displacement extraction
  - event batch decoding helpers
- `src/chronicler/bridge_sidecar.py`
  - sidecar export
  - economy sidecar export
  - per-tick stats normalization
- `src/chronicler/agent_bridge.py`
  - public `AgentBridge`
  - lifecycle orchestration
  - bridge reset / close

Module names can change. The important part is responsibility separation.

### Important sequencing note

Move the least entangled pieces first:

- batch builders
- signal builders
- snapshot readers

Leave lifecycle-heavy methods inside `AgentBridge` until the pure helpers are extracted.

### Main targets

- `src/chronicler/agent_bridge.py`
- possible new `src/chronicler/bridge_*.py` modules
- `tests/test_agent_bridge.py`
- narrow related tests in economy, ecology, politics, and sidecar surfaces

### Spec questions to resolve

1. Which helpers stay methods because they truly need mutable bridge state?
2. Which extracted modules should be considered public versus internal?
3. How do we avoid circular imports between builders, constants, models, and sidecar helpers?
4. Should write-back stay in `AgentBridge` for the first pass, or be split later with a dedicated handoff?

### Minimum validation shape

- existing bridge round-trip tests still pass unchanged at the public API level
- no regression in reset semantics
- no regression in sidecar emission timing
- no regression in hybrid, shadow, and demographics-only mode behavior

## 4. Authoritative Bridge Contract + Ratchet Tests

### Why this should move forward

Rust now centralizes FFI schemas in `chronicler-agents/src/ffi/schema.rs`, but Python still mirrors many of those contracts indirectly through local batch builders, local decode logic, and scattered tests.

The gap is not "there are no tests."
The gap is "the contract is not expressed once on the Python side and ratcheted as a coherent surface."

That becomes more expensive every time a new field crosses the boundary.

### Scope recommendation

Add one Python-side contract module that becomes the authoritative home for bridge payload-family expectations.

Recommended targets:

- `src/chronicler/bridge_contract.py` or `src/chronicler/agent_contracts.py`

Recommended contents:

- payload family names
- field-name tuples
- expected required/optional columns
- schema-version constants where needed
- decode helpers or lightweight DTO types
- reset / clear semantics documentation for transient signal families

Recommended payload families to cover first:

- snapshot
- tick events
- promotions
- aggregates
- region batch core columns
- civ signal batch
- economy return batches
- ecology return batches
- politics return batches

### Ratchet-test direction

Add one coherent contract test surface that checks:

- field names
- field counts
- required vs optional column expectations
- reset behavior for transient signals
- versioning expectations
- tolerances for backward-compatible column order or additive extension where intentionally allowed

### Important versioning note

Do not force one giant "bridge schema version" unless the repo truly wants lockstep behavior across every payload family.

Safer first-pass options:

- one per-family version constant
- one per-family "expected field set" plus changelog comment
- explicit compatibility policy for additive optional columns

### Main targets

- `src/chronicler/agent_bridge.py`
- new Python contract module
- `tests/test_agent_bridge.py`
- `tests/test_ecology_bridge.py`
- `tests/test_politics_bridge.py`
- economy bridge tests
- relevant Rust schema tests

### Spec questions to resolve

1. Which payload families need strict field-order ratchets versus name/type ratchets only?
2. Which columns are allowed to be optional for backward compatibility?
3. Should Python contract tests compare directly against Rust-exported schemas where possible?
4. How should transient reset expectations be encoded so they fail loudly when a new signal forgets to clear?

### Minimum validation shape

- contract tests for every bridge payload family touched by active development
- at least one multi-turn reset test for every transient cross-boundary signal family
- explicit failure on missing required columns or wrong types

## 5. Gradual Pydantic Peel-Out For Runtime-Only Structures

### Why this should move forward

The repo is heavily `BaseModel`-driven, but runtime mutation dominates the hot path and assignment validation is intentionally disabled in key places.

That means the best next step is not "replace Pydantic."
It is "stop introducing more runtime-only traffic through the serialized model layer when we do not need to."

### Scope recommendation

Start with runtime-only dataclasses and DTOs, not with `WorldState`, `Region`, or `Civilization`.

Good first targets:

- `TurnArtifacts` / `TurnContext`
- bridge decode DTOs
- snapshot-metrics containers
- sidecar row families
- other coordinator-only temporary structures

### Non-goals

- no full `WorldState` rewrite
- no attempt to replace persisted bundle/state models
- no broad model migration in one pass

### Main targets

- `src/chronicler/models.py`
- new small runtime modules near the coordinator and bridge seams
- any phase helper currently using ad hoc dicts or tuple unpacking for transient work

### Important gotcha

Do not create duplicate dataclass mirrors of the main serialized domain models unless there is a hard hot-path reason.

The goal is to peel runtime-only structures out of the hot path, not to create two parallel domain models for the same persistent entity.

### Spec questions to resolve

1. Which runtime-only containers have the highest clarity or perf payoff?
2. Which new dataclasses should be `slots=True` by default?
3. Which existing dict-based payloads are stable enough to convert immediately?
4. How much of this work should happen opportunistically inside other refactors versus in a dedicated branch?

### Minimum validation shape

- direct unit coverage for new DTO/dataclass constructors or helper transforms
- no serialization regressions for persisted bundle/state surfaces
- no public API drift unless explicitly chosen

## 6. Viewer Thin-Client / Query-Oriented Direction

### Why this should move forward

This is already the repo's stated Phase 7.5 direction:

- Tauri 2 as the canonical client
- Rust-side processing as the primary data plane
- browser fallback limited to live mode and legacy bundle browsing
- query-oriented IPC instead of giant browser-side bundle parsing

That direction also fits Phase 8/9 better because M63-M73 add more layers, overlays, and entity families.

### Scope recommendation

Treat this item as a planning lock plus handoff refinement, not as an active rewrite before the M61b gate.

Move forward with:

- contract/query boundary clarification
- additive typed layer namespaces
- stable ID expectations
- diagnostics vocabulary shared between browser and Tauri paths
- front-door workflow alignment for setup -> run -> inspect

Do not move forward yet with:

- a full Tauri data-plane implementation before the gate
- browser-side monolithic loader expansion
- a framework rewrite absent the benchmark gate

### Phase 8/9 compatibility angle

Phase 8/9 wants additive room for:

- institutions
- PSI metrics
- legitimacy / ambition panels
- cultural trait overlays
- patronage networks
- revolt cascade layers
- intelligence / belief-state views

That argues for:

- query-oriented access
- stable IDs
- additive layer families
- narrow typed diagnostics

not for richer browser-side global JSON hydration.

### Main targets once the gate opens

- `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md`
- `docs/superpowers/plans/2026-03-24-m62a-preactivation-prep.md`
- `docs/superpowers/plans/2026-03-30-m62b-preactivation-prep.md`
- `viewer/`
- future `src-tauri/` scaffold

### Spec questions to resolve later

1. What are the first stable query families?
2. Which Phase 8/9 entity and overlay families need reserved namespaces in Bundle v2?
3. Which viewer diagnostics are shared across browser and Tauri paths?
4. What is the narrowest browser fallback that still keeps live mode and legacy viewing healthy?

## What Not To Fold Into These Specs

Keep these separate unless the user explicitly asks to combine them:

- modifier-composition refactor for action weights
- rules-engine or condition/effect foundation
- CLI/application-runner split in `main.py`
- export-v2 implementation details
- full persistence redesign for bridge-owned transient state

They are all related, but they are not the same handoff.

## Recommended Progress-Doc Recording

Record this pass as:

- a docs-only architecture handoff pass
- six move-forward recommendations are now explicitly captured
- Phase 8/9 compatibility strengthens the case for the first four items
- modifier composition remains an adjacent pre-M63 guardrail, not part of this handoff batch

## Suggested Next Spec To Write First

If only one of these is taken to full spec next, the best first target is:

- `TurnArtifacts` / `TurnContext`

Reason:

- it removes the most hidden coupling across simulation, narrative, and bridge code
- it makes the later `run_turn()` split safer
- it gives the bridge-contract work a cleaner coordinator seam
