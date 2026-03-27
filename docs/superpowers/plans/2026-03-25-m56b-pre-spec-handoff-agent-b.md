# M56b Pre-Spec Handoff (Agent B)

> Date: 2026-03-26 (refresh after M56a landing)  
> Audience: Agent B (spec writer)  
> Purpose: lock an implementation-ready design spec for `M56b: Urban Effects`.

## Status Snapshot

- M56a is now implemented on `feat/m56a-settlement-detection` and provides the settlement detection/persistence contract.
- M56b has not started; no urban mechanics are wired yet.
- Hybrid smoke/regression is currently blocked by a pre-existing FFI mismatch (`set_economy_config` AttributeError). M56b spec should note this blocker for validation sequencing.

## Canonical Requirements (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: convert settlements into mechanical context across needs, production, culture, safety, and narration.
- Behavioral split to preserve:
  - Urban: higher material/social access, lower safety, faster cultural drift, stronger market/temple exposure.
  - Rural: higher food efficiency and safety, slower cultural drift, weaker material access.
- Runtime state requirement: Rust should consume lightweight per-agent signals; heavy settlement objects remain Python-side.
- Gate: effects are measurable and legible while unrelated economy/needs baselines remain stable.

## M56a Contract (Implemented, Use This)

From landed M56a code (`models.py`, `settlements.py`, `main.py`):

- `Settlement` fields available to M56b include:
  - `settlement_id`, `name`, `region_name`
  - `status` (`candidate`, `active`, `dissolving`, `dissolved`)
  - `founding_turn`, `last_seen_turn`, `dissolved_turn`
  - `population_estimate`, `peak_population`
  - `centroid_x`, `centroid_y`
  - `footprint_cells: list[tuple[int, int]]` (detection-grid cells)
- Storage surfaces:
  - `Region.settlements` (active and dissolving)
  - `WorldState.settlement_candidates`
  - `WorldState.dissolved_settlements`
  - `WorldState.next_settlement_id`, `WorldState.settlement_naming_counters`
- Runtime/diagnostic surfaces:
  - `world._settlement_diagnostics`
  - `world._settlement_source_turn`
  - `world._settlement_founded_this_turn`
  - `world._settlement_dissolved_this_turn`
- Snapshot surfaces:
  - `TurnSnapshot.settlement_source_turn`
  - `settlement_count`, `candidate_count`, `total_settlement_population`
  - `active_settlements`, `founded_this_turn`, `dissolved_this_turn`
- Detection is Python-side and deterministic; `--agents=off` is an explicit no-op.

## Current Code Reality (M56b Starting Point)

- Rust tick reads region-level signals from `RegionState` and civ-level signals from `TickSignals`.
- Needs/satisfaction/culture/conversion pathways exist (`needs.rs`, `satisfaction.rs`, `culture_tick.rs`, `conversion_tick.rs`).
- Python->Rust bridge does not yet send per-agent settlement assignment.
- No per-agent urban field exists in `AgentPool` yet.

## Hard Constraints To Preserve

- Keep `--agents=off` semantics intact (no synthetic urban fallback in aggregate mode).
- Preserve determinism (stable ordering, explicit tie-breakers).
- Preserve cap rules:
  - non-ecological satisfaction penalties remain capped at `-0.40`.
- Follow transient-signal discipline across Python/Rust boundary:
  - clear one-turn transients before builder return
  - add multi-turn reset tests for new transients.
- `compute_satisfaction_with_culture` uses `SatisfactionInputs`; add struct fields, do not append positional params.

## Scope Recommendation

In-scope for M56b:
- Define and wire per-agent urban classification signal using M56a settlements.
- Apply targeted urban/rural modifiers to existing needs/satisfaction/culture/religion/market pathways.
- Add narration/analytics exposure for urbanization legibility.
- Add bounded constants with explicit `[CALIBRATE M61b]` ownership.

Out-of-scope for M56b:
- Reworking core economy architecture.
- Viewer schema redesign.
- Broad retune of unrelated M53/M54/M55-calibrated constants.

## Recommended Wiring Strategy

1. Classification layer:
- Use M56a `footprint_cells` as primary geometry contract (not radius approximation).
- Match M56a grid semantics exactly for assignment:
  - grid size 10
  - cell mapping `min(int(x * 10), 9)`, `min(int(y * 10), 9)`
- Prefer `settlement_id` assignment (derive `is_urban` as `settlement_id != 0`).
- Define deterministic tie-break for overlapping footprints.

2. Behavioral layer:
- Needs: bounded urban/rural modifiers in restoration and/or utility terms.
- Satisfaction: extend `SatisfactionInputs` with urban context fields.
- Culture/conversion: modest multipliers for urban vs rural pace/exposure.
- Keep early constants conservative; no large global retune.

3. Narration/analytics layer:
- Surface urban/rural aggregates per civ/region for prompts and diagnostics.
- Reuse existing settlement event types (`settlement_founded`, `settlement_dissolved`) and enrich context rather than changing event schema.

## Candidate File Touch Map

- Python:
  - `src/chronicler/agent_bridge.py`
  - `src/chronicler/simulation.py`
  - `src/chronicler/settlements.py` (shared geometry helpers, if needed)
  - `src/chronicler/narrative.py`
  - `src/chronicler/analytics.py`
- Rust:
  - `chronicler-agents/src/ffi.rs`
  - `chronicler-agents/src/tick.rs`
  - `chronicler-agents/src/needs.rs`
  - `chronicler-agents/src/satisfaction.rs`
  - `chronicler-agents/src/culture_tick.rs`
  - `chronicler-agents/src/conversion_tick.rs`
  - `chronicler-agents/src/pool.rs` (only if per-agent field is persisted there)
- Tests:
  - `tests/test_agent_bridge.py`
  - `tests/test_narrative.py`
  - `tests/test_analytics.py`
  - `chronicler-agents/tests/*`

## Design Decisions Agent B Should Lock

1. Final signal shape on agent side: `settlement_id` only vs `settlement_id` + cached `is_urban`.
2. Classification cadence: every hybrid tick vs periodic recompute.
3. Deterministic overlap/tie-break rules for footprint membership.
4. Exact subsystem modifier map (needs/satisfaction/culture/conversion/market/temple).
5. Magnitude bounds and `[CALIBRATE M61b]` constants.
6. Snapshot/analytics additions for urbanization visibility in M56b.
7. Validation path while hybrid blocker exists (what can be merged before full hybrid smoke).

## Validation Plan Expectations

- Unit tests:
  - deterministic per-agent urban assignment
  - stable assignment under minor movement
  - correct fallback for agents outside all settlements (`settlement_id=0`)
- Behavior tests:
  - directional urban/rural deltas in needs/safety/culture/exposure
  - no breach of satisfaction cap logic
- Integration tests:
  - end-to-end run with M56a settlement data producing legible differences
  - no regressions to unrelated M54/M55 baselines
- Determinism tests:
  - same seed => same urban assignments and downstream outcomes.

## Expected Output From Agent B

- A single pre-implementation M56b spec with:
  - explicit use of the landed M56a contract above
  - Python->Rust signal path for per-agent settlement classification
  - subsystem modifier matrix with bounded constants
  - tests + merge gates + blocker-aware validation sequence
