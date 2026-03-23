# Post-M51 Refactor Waves

> **Status:** Proposal
> **Date:** 2026-03-21
> **Context:** Follow-on execution plan after `M51` lands and stabilizes.

---

## Goal

Preserve the current simulation direction while paying down the specific architectural debt that Phase 7, Phase 7.5, and the Phase 8-9 horizon already imply.

This is intentionally a staged refactor plan, not a rewrite plan.

## Immediate Follow-On

Before these waves, land the immediate post-M51 / post-M52 work:

- short `codex/m51-stabilize` pass
- `M52`
- `M53`
- `codex/refactor-identity-substrate`

The adjusted `M52` design intentionally avoids depending on the identity substrate. That means `codex/refactor-identity-substrate` is no longer treated as a blocker in front of `M52`; it becomes the key bridge from the depth-feature stretch into Wave 2 and later export-plane work.

The identity substrate branch is still the key prerequisite for the later waves. It gives long-lived entities stable internal identity without forcing an early bundle or viewer contract rewrite.

---

## Recommended Order

1. `M51`
2. short `codex/m51-stabilize` pass
3. `M52`
4. `M53`
5. `codex/refactor-identity-substrate`
6. Wave 2 branches
7. `M54a` and onward
8. Wave 3 branch before `M62a`
9. Wave 4 branches before `M63` / major Phase 8 institutional work

---

## Post-M52 Landing

Once `M52` lands, the next steps should be:

1. Run `M53` while the `M48`-`M52` interaction surface is still fresh:
   - calibrate the new artifact constants and event density
   - validate artifact narration, capture/loss rates, and Mule artifact frequency
2. Land `codex/refactor-identity-substrate` after `M53`, before Wave 2:
   - stable internal identity for long-lived entities
   - cleaner base for later export-plane and viewer-contract work
3. Start Wave 2 only after the identity substrate branch is in:
   - `codex/refactor-world-indexes`
   - `codex/refactor-turn-artifacts`
   - `codex/refactor-ffi-contracts`
   - `codex/refactor-run-orchestration`

Default rule: do not hold `M52` for the identity substrate branch unless implementation uncovers a concrete identity-coupling problem that the adjusted `M52` design failed to avoid.

---

## Wave 2: Pre-M54a Engine Seams

**Intent:** Make the simulation core easier to scale without changing the external product shape.

### Branch 1: `codex/refactor-world-indexes`

**Why**

The codebase still rebuilds local maps and performs repeated name-based scans in hot paths. This is manageable now, but it will get more expensive as the Phase 7 scale track migrates more systems and increases output size.

**Main Targets**

- `src/chronicler/models.py`
- `src/chronicler/simulation.py`
- `src/chronicler/economy.py`
- `src/chronicler/politics.py`
- `src/chronicler/factions.py`
- `src/chronicler/agent_bridge.py`

**Work**

- Add cached lookup helpers or a small `world_indexes.py` module.
- Support at least:
  - `civ_by_id`
  - `civ_by_name`
  - `region_by_id`
  - `region_by_name`
- Invalidate caches on relevant world mutations.
- Replace the hottest repeated scans first instead of trying to convert every lookup in one branch.

**Exit Criteria**

- Turn execution no longer rebuilds `region_map` ad hoc in multiple places.
- The main civ/region lookup paths are centralized and testable.

### Branch 2: `codex/refactor-turn-artifacts`

**Why**

`run_turn()` currently passes transient state through hidden `WorldState` scratch fields. That makes the phase pipeline harder to reason about and increases coupling between simulation, narrative, and Rust bridge code.

**Main Targets**

- `src/chronicler/simulation.py`
- `src/chronicler/narrative.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/turn_artifacts.py` (new)

**Work**

- Add a typed `TurnArtifacts` or `TurnContext` object.
- Move transient scratch state such as:
  - `_agent_snapshot`
  - `_named_agents`
  - `_economy_result`
  - `_conquered_this_turn`
- Pass turn-local outputs explicitly through orchestration.

**Exit Criteria**

- Transient per-turn outputs are explicit inputs/outputs instead of hidden `WorldState` fields.
- Phase boundaries become easier to test independently.

### Branch 3: `codex/refactor-ffi-contracts`

**Why**

The Python/Rust seam still relies on ad hoc tuple and Arrow decoding at several call sites. As the scale track grows, that becomes a drag on safety and iteration speed.

**Main Targets**

- `src/chronicler/agent_bridge.py`
- `src/chronicler/narrative.py`
- `src/chronicler/analytics.py`
- `src/chronicler/live.py`
- `src/chronicler/agent_contracts.py` (new)

**Work**

- Create typed Python-side DTOs for:
  - memories
  - needs
  - relationships
  - raw agent events
  - relationship stats
- Decode each payload family once in a central contract layer.
- Route downstream consumers through that layer.

**Exit Criteria**

- Rust payloads are decoded in one place per payload family.
- New FFI fields stop requiring repeated tuple-index edits across multiple files.

### Branch 4: `codex/refactor-run-orchestration`

**Why**

`main.py` is still functioning as both CLI shell and application orchestrator. That is survivable today, but it will become more brittle as validation, export modes, and live/viewer workflows expand.

**Main Targets**

- `src/chronicler/main.py`
- `src/chronicler/cli.py` (new)
- `src/chronicler/run_single.py` (new)
- `src/chronicler/run_batch.py` (new)
- `src/chronicler/run_live.py` (new)
- `src/chronicler/run_narrate.py` (new)

**Work**

- Split argument parsing from execution services.
- Keep the public CLI behavior stable.
- Leave the core simulation entrypoint intact or move it into a smaller runner module.

**Exit Criteria**

- `main.py` becomes a thin entrypoint.
- Mode-specific logic is isolated enough to evolve independently.

**Wave 2 Non-Goals**

- No Bundle v2 rewrite.
- No viewer type migration.
- No `WorldState` redesign.

---

## Wave 3: Pre-M62a Export Plane Foundation

**Intent:** Prepare the simulation output contract for Phase 7.5 without prematurely freezing it during core Phase 7 feature work.

### Branch: `codex/export-v2-foundation`

**Why**

Phase 7.5 is explicitly about export contracts, stable IDs, scalable loading, and viewer data-plane work. That should start only after the simulation output is stable enough to target.

**Main Targets**

- `src/chronicler/bundle.py`
- `viewer/src/types.ts`
- `viewer/src/hooks/useBundle.ts`
- `viewer/src/hooks/useLiveConnection.ts`

**Work**

- Introduce Bundle v2 as an additive path.
- Add:
  - schema version
  - manifest object
  - summary/detail split
  - stable IDs in exported entities
  - layer-friendly layout for later chunking
- Keep legacy monolithic bundle write/read support during transition.
- Add compatibility tests that compare legacy and v2 exports for the same run.

**Exit Criteria**

- Export code can produce a stable v2 foundation without breaking the current viewer.
- Viewer code can tolerate both legacy and v2 bundles during migration.

**Wave 3 Non-Goals**

- No full viewer redesign yet.
- No mandatory chunked transport implementation in the first export-v2 branch.

---

## Wave 4: Pre-M63 / Phase 8 Complexity Guardrails

**Intent:** Put structure under the next layer of systemic complexity before institutions, PSI, legitimacy shock propagation, and richer crisis logic start stacking.

### Branch 1: `codex/refactor-modifier-composition`

**Why**

The Phase 8-9 horizon already calls out the action-weight cap problem once institutions stack on top of traditions, tech focus, factions, and Mule effects.

**Main Targets**

- `src/chronicler/action_engine.py`
- `src/chronicler/factions.py`
- tech focus modules
- Mule-related logic

**Work**

- Add a central modifier-composition layer for action weights.
- Make contribution sources explicit.
- Make the cap policy explicit and testable.
- Route existing modifier sources through the shared composition path.

**Exit Criteria**

- Action-weight math is inspectable and testable.
- New systems can add modifiers without multiplying hidden local logic.

### Branch 2: `codex/refactor-rules-foundation`

**Why**

If Phase 8 keeps its current ambition, more crisis and institution behavior will otherwise accumulate as one-off branches in existing simulation modules.

**Main Targets**

- `src/chronicler/emergence.py`
- `src/chronicler/rules_engine.py` (new)
- related condition/effect call sites

**Work**

- Introduce a small condition/effect engine for cross-system triggers.
- Start by extracting the most repeated trigger/consequence patterns.
- Keep the first version deliberately small and simulation-owned.

**Exit Criteria**

- Institutions, PSI, legitimacy shocks, and crisis chains can be added through rules plus handlers instead of only through more branching in core files.

**Wave 4 Non-Goals**

- No attempt to data-drive the whole simulation.
- No generic enterprise rules DSL.

---

## Design Guardrails

- Prefer additive seams before replacement.
- Keep branch scopes narrow enough to test and merge independently.
- Preserve deterministic behavior at every wave.
- Do not couple export-plane changes to core simulation refactors unless a branch explicitly owns both.
- If only one refactor can happen between the depth-feature stretch and Wave 2, prioritize `codex/refactor-identity-substrate`.

---

## Roadmap Alignment

This plan is intended to stay consistent with:

- `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`
- `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`
- `docs/superpowers/roadmaps/chronicler-phase8-9-horizon.md`

In short:

- Wave 2 supports the pre-scale cleanup needed before `M54a`.
- Wave 3 creates the export/data-contract base for Phase 7.5 and `M62a`.
- Wave 4 reduces the systemic complexity risk already identified for `M63` and Phase 8.
