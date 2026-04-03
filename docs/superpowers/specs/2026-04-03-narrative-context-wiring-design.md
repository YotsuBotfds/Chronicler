# Narrative Context Wiring Design

> Date: 2026-04-03
> Status: Draft
> Scope: Pure Python plumbing — no Rust, no model changes, no bundle persistence expansion

## Problem

Seven bridge-owned narrative inputs are accepted by `build_agent_context_for_moment()` and declared on `narrate_batch()` / `_prepare_narration_prompts()`, but no caller actually passes them. The consumer API is ready; the wiring is disconnected.

Missing inputs: `social_edges`, `dissolved_edges_by_turn`, `agent_name_map`, `gini_by_civ`, `economy_result`, `displacement_by_region`, `dynasty_registry`.

## Scope

**In-process narration** (post-loop in `main.py`, any path with a live `AgentBridge`): pass all 7 inputs end-to-end.

**Replay narration** (`_run_narrate()` bundle replay, `live.py` bundle-loaded `narrate_range`): derive only cheap, durable context already present in bundle state. Pass `None` deliberately for everything else — no pseudo-reconstructed guesses.

**Running-live narration** (`live.py` `narrate_range` during an active simulation): `_init_data["world_state"]` is frozen at init and never refreshed with current great persons. Great persons and agent name map will be stale or empty. Narration degrades gracefully — same as replay with no GP data. A live-state refresh for GP data is out of scope for this spec.

**Out of scope:**
- Bundle persistence expansion (separate spec if full replay parity is wanted later)
- `NarrationContext` dataclass consolidation (follow-up refactor, not this change)
- Any Rust or data model changes

## Design Decisions

### Wiring pattern: explicit kwargs at the callsite

Callers extract what they have (from bridge or bundle) and pass explicitly to `narrate_batch()`. The engine does not reach into `world._agent_bridge` internally.

Rationale:
- Matches the existing explicit-input style across `narrative.py`
- Keeps replay vs. live data availability obvious at each callsite
- Avoids hiding a bridge dependency inside `NarrativeEngine`

### Replay contract: degraded but safe

Replay callers derive inputs from bundle state:
- `great_persons`: full deserialized active + retired list, unfiltered (dead-character context matters for narration)
- `agent_name_map`: built from `great_persons`, filtered to `agent_id is not None` (the filter applies to the map only, not the GP list)
- `gini_by_civ`: resolved internally via snapshot fallback (see Gini Fallback Rule below)

Replay callers pass `None` for:
- `social_edges`
- `dissolved_edges_by_turn`
- `displacement_by_region`
- `dynasty_registry`
- `economy_result`

Narration still works on replay — it produces less character-rich output, which is the honest contract given the data available.

## Input Availability Matrix

| Input | In-process | Bundle replay | Source |
|-------|-----------|---------------|--------|
| `great_persons` | yes | yes | already serialized on world state |
| `agent_name_map` | yes (bridge `named_agents`) | yes | derive from bundled `great_persons` |
| `gini_by_civ` | yes (bridge `_gini_by_civ`) | fallback | snapshot `civ_stats[name].gini` |
| `social_edges` | yes (bridge `read_social_edges()`) | no | bridge-only transient |
| `dissolved_edges_by_turn` | yes (`world.dissolved_edges_by_turn`) | no | transient on `WorldState`, not bundled |
| `displacement_by_region` | yes (bridge `displacement_by_region`) | no | bridge-only transient |
| `dynasty_registry` | yes (bridge `dynasty_registry`) | no | bridge-only Python registry |
| `economy_result` | yes (bridge `_economy_result`) | no | bridge-only transient |

## Caller-by-Caller Wiring

### 1. Post-loop API narration (`main.py` ~line 627)

Bridge is alive. Extract and pass all inputs:

```
social_edges         = agent_bridge.read_social_edges()
dissolved_edges      = world.dissolved_edges_by_turn
agent_name_map       = agent_bridge.named_agents
gini_by_civ          = agent_bridge._gini_by_civ
economy_result       = agent_bridge._economy_result
displacement         = agent_bridge.displacement_by_region
dynasty_registry     = agent_bridge.dynasty_registry
```

All passed explicitly to `narrate_batch()`.

### 2. Bundle replay (`_run_narrate()` ~line 1005)

No bridge. Derive durable context from bundle:

```
great_persons        = all_great_persons  (full active + retired list, unfiltered — dead-character context matters)
agent_name_map       = {gp.agent_id: gp.name for gp in all_great_persons if gp.agent_id is not None}
gini_by_civ          = None  (snapshot fallback in build_agent_context_for_moment)
social_edges         = None
dissolved_edges      = None
displacement         = None
dynasty_registry     = None
economy_result       = None
```

### 3. Live narrate_range (`live.py` ~line 628)

Bundle-backed, no bridge. Reconstruct what `_init_data["world_state"]` provides:

```
great_persons        = [reconstructed from _init_data["world_state"], full active + retired list]
agent_name_map       = {gp.agent_id: gp.name for gp in great_persons if gp.agent_id is not None}
gini_by_civ          = None  (snapshot fallback)
everything else      = None
```

`live.py` currently passes neither `great_persons` nor any agent context kwargs. This spec adds both.

**Caveat for running-live sessions:** `_init_data["world_state"]` is captured once at simulation init (line ~1091) and never refreshed with current GP state. Turn updates only append history, events, named events, and current turn. During an active simulation, `great_persons` reconstructed from this frozen state will be stale or empty. Narration degrades gracefully — no error, just less character context. A live-state GP refresh is out of scope.

## Public Signature Changes

### `narrate_batch()` (`narrative.py` ~line 911)

Add one kwarg: `dynasty_registry=None`.

All other agent-context kwargs (`social_edges`, `dissolved_edges_by_turn`, `agent_name_map`, `gini_by_civ`, `economy_result`, `displacement_by_region`) already exist in the signature but are never passed by callers today.

### `_prepare_narration_prompts()` (`narrative.py` ~line 958)

Add one kwarg: `dynasty_registry=None`.

Same situation — other kwargs already present, never wired through.

### `build_agent_context_for_moment()` (`narrative.py` ~line 298)

No public signature change. Already accepts `dynasty_registry` and all other inputs.

One internal behavior change: Gini fallback rule (below).

No other public call signatures change. Internal helper locals and prompt-prep wiring may be touched to thread `dynasty_registry` through.

## Gini Fallback Rule

**Location:** `build_agent_context_for_moment()` in `narrative.py`.

**Rule:**
1. If `gini_by_civ` is provided and contains the focal civ's index: use it (current behavior, live path).
2. If `gini_by_civ` is None or missing the focal civ: check `current_snapshot.civ_stats[focal_civ_name].gini`. If that field exists and is not None: use it.
3. If neither source yields a value: keep the existing no-signal default (`gini_coefficient` stays at its model default of `0.0`).

**Why this placement:** The function already resolves `focal_civ_name` from the moment, already receives `current_snapshot`, and is where Gini gets consumed. The fallback stays local to consumption — no synthetic map-building in callers or prompt prep.

**Live path is unaffected:** Step 1 fires. The fallback at step 2 only activates when callers pass `gini_by_civ=None`, which only happens on replay.

## Test Strategy

Tests target the production wiring seams, not helper abstractions.

### 1. Live bridge threading

**Home:** `tests/test_main.py` (existing caller-level test area ~line 913).

Verify that post-loop narration passes all 7 bridge-owned inputs through to `narrate_batch()`. Monkeypatch or spy on `NarrativeEngine.narrate_batch` and assert the kwargs arrive non-None when an `AgentBridge` is present.

### 2. Dynasty context propagation

**Home:** `tests/test_narrative.py` (existing agent-context test area).

When `dynasty_registry` is provided with matching `great_persons`: verify dynasty lineage text appears in the `AgentContext` output from `build_agent_context_for_moment()`.

When `dynasty_registry` is None: verify no dynasty text and no error.

### 3. Replay Gini fallback

**Home:** `tests/test_narrative.py` (precedent at ~line 545 for Gini plumbing through `_prepare_narration_prompts()`).

Call with `gini_by_civ=None` and `history` containing snapshots with `civ_stats[name].gini` populated. Assert on `agent_ctx.gini_coefficient` matching the snapshot value — not on prompt text.

Call with all bridge-owned inputs as None and no snapshot Gini: verify `gini_coefficient` stays at default, no errors.

### 4. Replay/live caller reconstruction

**Home:** `tests/test_main.py` for `_run_narrate()`, `tests/test_live_integration.py` (~line 529) for `narrate_range`.

Monkeypatch `NarrativeEngine.narrate_batch` and assert that:
- `great_persons` is passed (not None)
- `agent_name_map` is passed with the correct filtered active+retired mapping
- Bridge-only inputs are explicitly None

## Accepted Limitations

- Replay narration omits dynasty lineage, social/dissolution graph context, displacement context, and economy/trade-dependency context. This is the honest contract given bundle state today.
- The live path uses a single batch-level `gini_by_civ` from the bridge's final tick for all moments. This means early moments in a post-loop batch get the end-of-run Gini rather than their contemporary value. Not addressed in this spec — a per-moment live Gini would require accumulating Gini history during the simulation loop.
- `social_edges` and `gp.agent_bonds` remain dual paths for relationship context. This spec does not consolidate them — that is a separate contract simplification.
- Running-live `narrate_range` gets stale or empty GP state because `_init_data["world_state"]` is frozen at simulation init. A live-state GP refresh would fix this but is out of scope — it changes live.py's update protocol, not narration wiring.
