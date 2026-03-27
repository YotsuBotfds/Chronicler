# M56a Pre-Spec Handoff (Agent A)

> Date: 2026-03-25  
> Audience: Agent A (spec writer)  
> Purpose: lock an implementation-ready design spec for `M56a: Settlement Detection`.

## Status Snapshot

- `M54a`, `M54b`, `M54c`, `M55a`, and `M55b` are landed and treated as the accepted baseline line in `main`.
- `M56` is the next target on the scale track; `M56a` should be spec'd as detection/persistence only.
- Progress doc instruction for this phase: start M56 work from clean `main` and preserve accepted M54 controls + final M55 gate artifacts for comparison.

## Canonical Requirements (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: detect and persist settlement structure produced by M55a clustering pressure.
- Key framing: detection, not creation.
- Mechanism requirements:
  - run density-based clustering every `SETTLEMENT_DETECTION_INTERVAL`
  - thresholded clusters become candidates
  - candidates that persist become named settlements with stable IDs and `founding_turn`
- Inertia requirement: anti-flicker persistence based on population and age.
- Storage requirement: Python-side per-region settlement list (artifact-like, low-volume, narrative-friendly).
- Gate: plausible form/persist/dissolve behavior, stable IDs, and usable diagnostics before M56b consumes mechanics.

## Current Code Reality (What Exists Today)

- Spatial substrate is present in Rust (`x`, `y` on agents, spatial grids, attractors, drift) via M55a.
- Region-level spatial inputs are already passed from Python to Rust (`is_capital`, `temple_prestige` in `build_region_batch()`).
- Rust exports per-tick spatial diagnostics via `AgentSimulator.get_spatial_diagnostics()`, but Python mainline flow does not currently consume/store them.
- The turn loop stores a post-tick snapshot in `world._agent_snapshot` before Phase 10; snapshot includes per-agent `id`, `region`, `x`, `y`.
- No settlement model or storage exists yet in Python `Region`/`WorldState`.
- No urban/settlement signal exists in Rust `RegionState`/`AgentPool`.

## Non-Negotiables To Preserve

- Determinism guardrails from the Phase 7 roadmap apply to M56a:
  - no hash-order dependent tie-breaks
  - canonical sorting for clustering/matching
  - explicit stable secondary keys
- If M56a uses RNG noise, reserve a unique stream offset and wire it through the established stream-offset pattern.
- `--agents=off` baseline behavior must remain valid.
- Bundle consumers should remain agnostic to aggregate-vs-agent stat origin.
- If you add any transient Python->Rust signal, clear it before returning from the builder and add a multi-turn reset test.

## Scope Recommendation

In-scope for M56a:
- Settlement detection cadence + clustering pass.
- Candidate persistence and anti-flicker inertia.
- Stable settlement identity lifecycle: found, persist, dissolve.
- Python-side data model + storage.
- Diagnostics surfaces needed by M56b spec and validation.

Out-of-scope for M56a:
- Need/satisfaction/culture/economy behavior changes from "urban vs rural."
- New per-agent Rust behavior modifiers.
- Large bundle/viewer contract changes beyond minimal settlement observability needed for validation.

## Suggested Integration Seam

Recommended placement:
- Run settlement detection in Python after post-tick snapshot is available and before turn snapshot/bundle capture.

Practical seam options:
- Option A: invoke from `run_turn()` after `_agent_snapshot` is set and before `phase_consequences()`.
- Option B: invoke inside `phase_consequences()` early, using `world._agent_snapshot`.

Preferred lean:
- Keep M56a as a standalone Python module (`src/chronicler/settlements.py`) called from `run_turn()` to avoid overloading Phase 10 politics/culture logic.

## Suggested Data Contract (For Spec Drafting)

Settlement object fields to lock:
- `settlement_id` (stable integer ID)
- `name`
- `region_name`
- `founding_turn`
- `last_seen_turn`
- `age_turns`
- `population_estimate`
- `centroid_x`, `centroid_y`
- `inertia`
- `status` (`candidate`/`active`/`dissolving` if you keep candidates persisted)

World/region storage lean:
- `Region.settlements: list[Settlement]` for narrative-facing storage.
- `WorldState.next_settlement_id` monotonic allocator for stable IDs.
- Private transient maps for matching/candidate bookkeeping if needed.

## Core Design Decisions Agent A Should Lock

1. Detection cadence and phase placement.
2. Clustering algorithm and deterministic tie-break rules.
3. Minimum density / size thresholds for candidate promotion.
4. Matching policy from new clusters to existing settlements (stable IDs).
5. Inertia update and dissolution policy.
6. Naming policy for newly activated settlements.
7. Diagnostics schema and where diagnostics are persisted.
8. Behavior in `--agents=off` (recommended: no-op or deterministic fallback, explicitly documented).

## File Touch Map (Likely)

- `src/chronicler/models.py`
- `src/chronicler/simulation.py`
- `src/chronicler/main.py` (if turn snapshots need settlement summaries)
- `src/chronicler/analytics.py`
- `src/chronicler/settlements.py` (new)
- `tests/test_settlements.py` (new)
- `tests/test_main.py` / `tests/test_bundle.py` (if snapshot/bundle shape changes)

## Validation Plan Expectations

- Unit tests:
  - deterministic clustering and matching
  - stable ID retention under mild position drift
  - inertia absorbing temporary dips
  - dissolution after sustained disappearance
- Integration tests:
  - multi-turn lifecycle (form -> persist -> dissolve)
  - no settlement-state corruption across save/load
  - no regressions in off-mode or existing M55 tests
- Determinism tests:
  - repeated same-seed runs produce identical settlement IDs and transitions.

## Open Questions To Route Back (If Needed)

1. Should M56a emit narrative `Event`s for settlement founding/dissolution now, or leave event emission to M56b?
2. Should settlement summaries be added to `TurnSnapshot` in M56a, or only stored in `WorldState` until M56b?
3. If no agent snapshot exists (`--agents=off`), do we require a fallback detector, or explicitly disable settlement detection?
4. Do we want settlement IDs globally unique across all regions forever (recommended), or region-local IDs?
5. Should dissolved settlements keep tombstone records for narrative continuity?

## Expected Output From Agent A

- A single pre-implementation design spec for M56a with:
  - data model
  - algorithm details
  - deterministic matching/inertia rules
  - call sequence in turn loop
  - diagnostics contract
  - explicit tests and gate criteria
