# M54a Brainstorm Handoff

> Date: 2026-03-21
> Purpose: fast context pack for brainstorming the `M54a` milestone before a formal spec/plan exists.

## Status Snapshot

- There is no dedicated `M54a` spec or implementation plan in the repo yet.
- The canonical roadmap still defines `M54a` as **Rust Ecology Migration** and explicitly says it should establish the Arrow-batch-in / Arrow-batch-out pattern for later phase migrations.
- `M53` is still the formal gate before `M54a`. The current progress doc still lists `M53b` remaining work for full closure.

## What The Docs Currently Say

### Canonical roadmap meaning

Primary reference:
- `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

Current roadmap wording:
- `M54a` = ecology migration, estimated 8-11 days.
- It is described as the simplest of the Rust phase migrations because soil/water/forest coupling is local to each region.
- It is supposed to establish the shared FFI migration pattern for `M54b` and `M54c`.
- Its explicit merge gate is determinism at 1/4/8/16 threads.

### Dependency-shape tension

Secondary reference:
- `docs/superpowers/plans/2026-03-20-phase7-viability-adjustments.md`

That memo proposes a meaningful dependency change:
- move shared sort infrastructure into `M54a`
- let `M55` depend on `M54a` + sort infra, not all of `M54a/b/c`

This is not fully reflected in the roadmap yet, so any new `M54a` brainstorm should decide whether it is following:
- the current roadmap dependency graph, or
- the revised viability-adjustments graph

### Pre-M54a cleanup plan

Reference:
- `docs/superpowers/plans/2026-03-21-post-m51-refactor-waves.md`

Wave 2 is explicitly framed as pre-`M54a` seam work:
- `codex/refactor-world-indexes`
- `codex/refactor-turn-artifacts`
- `codex/refactor-ffi-contracts`
- `codex/refactor-run-orchestration`

These read as "make M54a easier and safer" rather than "hard blockers," but they are clearly intended to reduce the migration pain.

## Current Code Reality

### Python still owns the full ecology phase

Primary files:
- `src/chronicler/ecology.py`
- `src/chronicler/simulation.py`

`tick_ecology()` currently does all of this in Python:
- disease severity updates
- depletion feedback and streak tracking
- soil/water/forest mutation
- deforestation river cascade
- resource-yield computation
- famine detection and event emission
- soil-floor application
- terrain-succession counters
- `prev_turn_water` persistence for next-turn disease flares

`run_turn()` still calls Python ecology in Phase 9, then terrain succession, then the Rust agent tick.

### Rust already consumes ecology outputs

Primary files:
- `src/chronicler/agent_bridge.py`
- `chronicler-agents/src/ffi.rs`
- `chronicler-agents/src/region.rs`
- `chronicler-agents/src/demographics.rs`
- `chronicler-agents/src/satisfaction.rs`

Current flow:
1. Python Phase 9 mutates `world.regions`.
2. `build_region_batch()` sends region data into Rust.
3. Rust uses those values for satisfaction, wealth, behavior, and demographics.

Important consequence:
- Rust already depends on ecology-derived fields, but it does not own the ecology phase state machine yet.

### Current write-back path is incomplete for a Rust ecology owner

`AgentBridge._write_back()` currently writes back:
- region populations
- civ aggregate stats

It does not write back:
- soil / water / forest_cover
- resource reserves / yields
- disease state
- famine cooldown
- ecology counters

So if `M54a` makes Rust the source of truth for ecology, the write-back surface must expand or the source-of-truth split must be redesigned.

## Biggest Design Seam

The Python `Region` model currently holds ecology state that Rust `RegionState` does not yet represent.

Python `Region` has persistent ecology-adjacent fields such as:
- `low_forest_turns`
- `forest_regrowth_turns`
- `famine_cooldown`
- `disease_baseline`
- `soil_pressure_streak`
- `overextraction_streaks`
- `resource_effective_yields`
- `capacity_modifier`
- `prev_turn_water`

Rust `RegionState` currently has:
- current soil / water / forest values
- current resource yields / reserves
- current endemic severity
- some derived or transient phase signals

It does not currently have most of the long-lived ecology bookkeeping above.

Inference:
- a real `M54a` design probably needs an explicit decision about whether those fields move into Rust, stay Python-side as a mirror, or get split into "Rust-owned hot state" and "Python-owned narrative/event state."

## Scope Ambiguity To Resolve Early

The docs are slightly inconsistent about what `M54a` really covers.

Roadmap language says:
- ecology migration

But the enrichment map also attaches demographics modeling ideas to `M54a`, including:
- Siler mortality
- Gompertz-Makeham
- age-specific fertility
- demographic-transition modifiers

Important context:
- demographics is already Rust-side today in `chronicler-agents/src/demographics.rs`

My read:
- the safest interpretation is that `M54a` core scope is **Phase 9 ecology migration**, not "rethink demographics."
- those demographic ideas are better treated as optional enrichments or later calibration/design follow-ons unless the spec explicitly pulls them in.

## Likely Brainstorm Questions

1. What is the exact unit of migration?
- Minimal option: Rust computes ecology mutations and returns them; Python still emits events and terrain transitions.
- Larger option: Rust owns all of Phase 9 except Python orchestration.

2. Where is the source of truth after migration?
- Python `Region`
- Rust `RegionState`
- mirrored state with explicit write-back contract

3. What is the returned Rust payload?
- updated region batch only
- region batch plus ecology events
- region batch plus deterministic event structs plus yield cache output

4. How should `_last_region_yields` evolve?
- keep a Python cache fed by Rust output
- replace it with explicit region fields
- eliminate the cache and make consumers read from a returned batch/result object

5. Does `M54a` include the viability memo's shared sort infrastructure?
- if yes, the milestone becomes both ecology migration and part of the spatial branch unlock
- if no, the roadmap and viability memo still need reconciliation

6. What is the determinism test harness?
- same seed, same result at 1/4/8/16 threads
- likely compare region ecology state, emitted ecology events, and downstream agent outcomes after one or more turns

## Good "Do Not Lose" Details

- `tick_terrain_succession()` currently depends on `low_forest_turns` and `forest_regrowth_turns` being updated immediately after ecology.
- `climate.process_migration()` depends on `effective_capacity()`, which depends on ecology and `capacity_modifier`.
- `build_region_batch()` currently clears transient one-turn signals before returning. Any new ecology-side transient crossing the boundary should follow the same rule and keep the required multi-turn reset test.
- `tests/test_ecology.py` already has broad Python ecology coverage and is a good oracle source for parity planning.
- `tests/test_agent_bridge.py` already asserts expectations around the region batch and transient cleanup behavior.

## Suggested First Brainstorm Output

If the next agent wants a tight deliverable, I would aim for:
- a one-page scope statement for `M54a`
- a state-ownership table: Python field -> Rust field -> write-back rule
- a return-contract sketch for ecology results/events
- a determinism-test plan
- a short "core vs optional enrichments" section so the milestone does not balloon

