# Narrative Context Wiring Pre-Spec Handoff

> Date: 2026-04-03
> Purpose: fast context pack for Spec A, covering the remaining pure-Python narration wiring gaps from the 2026-04-03 re-audit.

## Status Snapshot

- There is no dedicated spec or implementation plan for this work yet.
- This handoff covers the two original deferred items that belong together:
  - narrative agent-context wiring is disconnected
  - dynasty context never reaches narration
- The consumer side is mostly already built:
  - `build_agent_context_for_moment()` already accepts displacement, dynasty, social, dissolution, Gini, and economy inputs
  - `NarrativeEngine.narrate_batch()` already accepts most of the bridge-owned narration inputs
- The main remaining design seam is not "how should the prompt use this data?"
  - it is "which callers can supply which data, especially for in-process narration versus bundle replay?"

## Recommendation Context

My recommendation is:

- write one spec for both deferred items
- keep it scoped to Python plumbing plus safe fallbacks
- explicitly split the problem into:
  - **in-process narration**: live run or immediate post-run narration while `AgentBridge` still exists
  - **bundle-backed replay narration**: `_run_narrate()` and live `narrate_range`, which only have serialized data unless we widen persistence

Reason:

- the in-process path can ship immediately with no Rust or model changes
- the replay path does **not** have the same inputs available
- if the spec does not name that difference, it will accidentally over-promise "pure wiring" on paths that currently cannot reconstruct bridge-only state

## What The Docs Currently Say

Primary references:

- `docs/superpowers/specs/2026-03-16-m30-agent-narrative-design.md`
- `docs/superpowers/specs/2026-03-17-m39-parentage-dynasties-design.md`
- `docs/superpowers/specs/2026-03-17-m40-social-networks-design.md`
- `docs/superpowers/specs/2026-03-17-m41-wealth-class-stratification-design.md`
- `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`
- `docs/superpowers/progress/phase-6-progress.md`
- `docs/superpowers/plans/2026-04-03-reaudit-remediation-plan.md`

Important current-state notes:

- The re-audit remediation plan correctly records this as deferred design work.
- The progress doc contains some older wording around `_run_narrate()` being missing `great_persons`; that part is now stale.
- The live code today already passes:
  - `great_persons`
  - `world`
- The live code still does **not** pass:
  - `social_edges`
  - `dissolved_edges_by_turn`
  - `agent_name_map`
  - `gini_by_civ`
  - `economy_result`
  - `displacement_by_region`
  - `dynasty_registry`

Inference:

- the spec should treat some older progress notes as partially stale and rely on the live tree instead

## Current Code Reality

### The narrative consumer is already prepared for most of this data

`build_agent_context_for_moment()` in `src/chronicler/narrative.py` already accepts:

- `displacement_by_region`
- `dynasty_registry`
- `gp_by_agent_id`
- `social_edges`
- `dissolved_edges`
- `agent_name_map`
- `hostage_data`
- `civ_idx`
- `gini_by_civ`
- `economy_result`

Current usage points worth preserving:

- dynasty context is rendered only if both `dynasty_registry` and `gp_by_agent_id` are present
- wealth inequality context uses `gini_by_civ` keyed by civ index
- relationship context can come from either:
  - `gp.agent_bonds` + dissolved edges
  - legacy `social_edges` fallback
- M43b trade/shock narration still depends on `economy_result`

### The engine API is almost ready, but not fully

`NarrativeEngine.narrate_batch()` already accepts:

- `great_persons`
- `social_edges`
- `dissolved_edges_by_turn`
- `agent_name_map`
- `gini_by_civ`
- `economy_result`
- `world`
- `displacement_by_region`

What it does **not** accept yet:

- `dynasty_registry`

That omission propagates to `_prepare_narration_prompts()`, so dynasty context cannot reach narration even when the caller has it.

### Current callers still drop most of the data

#### 1. Post-loop API narration in `main.py`

The post-run narration path already builds:

- `all_great_persons`
- `world`

and still has `agent_bridge` alive at the callsite.

It currently does **not** pass any bridge-owned narrative context into `narrate_batch()`.

#### 2. `_run_narrate()` bundle replay in `main.py`

This path reconstructs:

- `world`
- `history`
- `events`
- `named_events`
- `all_great_persons`

But it does **not** have a live `AgentBridge`.

Important consequence:

- this path cannot supply bridge-owned transient state unless the spec explicitly allows reconstruction from serialized data or treats replay as best-effort

#### 3. Live `narrate_range` in `live.py`

This path currently reconstructs:

- events
- named events
- history
- named character names

and then calls `engine.narrate_batch(moments, all_history)` with no agent context at all.

It is also bundle/init-data based rather than bridge-based.

## Availability Matrix

This is the main contract seam the spec should lock down.

| Input | In-process run | Bundle replay | Notes |
|------|------|------|------|
| `great_persons` | yes | yes | already serialized on world state |
| `agent_name_map` | yes | yes | can be rebuilt from `great_persons` |
| `gini_by_civ` | yes | maybe | live bridge has `_gini_by_civ`; snapshots also carry per-civ `gini` |
| `displacement_by_region` | yes | no | bridge-owned transient today |
| `social_edges` | yes | no | available from `AgentBridge.read_social_edges()` only |
| `dissolved_edges_by_turn` | yes | no | transient on `WorldState`, excluded from bundle |
| `dynasty_registry` | yes | no | bridge-owned Python registry |
| `economy_result` | yes | no | bridge-owned transient, not serialized |

Inference:

- "pure wiring" is fully true for the in-process path
- it is only partly true for replay narration unless the spec explicitly adds graceful degradation rules

## Good Design Questions To Resolve Early

### 1. What is in scope for Spec A?

The cleanest scope options are:

- **Option A: in-process only**
  - post-run API narration and any path with a live `AgentBridge`
  - bundle replay remains best-effort
- **Option B: in-process plus replay fallback**
  - in-process gets full bridge context
  - replay gets whatever can be reconstructed cheaply from serialized data
- **Option C: full parity across all callers**
  - requires widening persistence for bridge-owned state
  - this no longer stays "pure wiring"

My recommendation:

- choose **Option B**
- keep the spec pure-Python by defining replay as degraded-but-safe rather than insisting on full parity now

### 2. Where should the bridge-to-narration wiring live?

Two possible patterns:

- callers explicitly gather inputs and pass them into `narrate_batch()`
- `NarrativeEngine` reaches into `world._agent_bridge` internally

My recommendation:

- keep it explicit at the callsite

Reason:

- `narrate_batch()` already uses explicit optional inputs
- explicit plumbing keeps bundle replay behavior obvious
- it avoids hiding bridge-private assumptions inside `narrative.py`

### 3. How should replay recover Gini?

There are two plausible sources:

- live `AgentBridge._gini_by_civ`
- `TurnSnapshot.civ_stats[*].gini`

My recommendation:

- spec explicit live-path threading from `AgentBridge._gini_by_civ`
- allow replay fallback to derive per-moment Gini from the current snapshot if bridge data is unavailable

This is still pure Python and avoids leaving replay with zeroed inequality context when snapshots already know the answer.

### 4. Is `social_edges` actually required when `gp.agent_bonds` exists?

Today `_prepare_narration_prompts()` builds `gp_by_agent_id` whenever `great_persons` exist, which means the modern path usually uses `gp.agent_bonds` plus dissolved edges.

But `social_edges` still matters because:

- it is the legacy fallback path
- it can still be the only relationship source when `gp.agent_bonds` is absent or incomplete

The spec should decide whether to:

- keep wiring `social_edges` as a compatibility path
- or deliberately declare bond-based narration the only supported source going forward

My recommendation:

- keep both in this pass
- avoid mixing a contract simplification into a plumbing fix

### 5. How should dynasty context behave on replay?

Because `dynasty_registry` is not serialized, replay cannot reconstruct true dynasty context without widening persistence.

The spec should explicitly choose one of:

- replay omits dynasty context
- replay gets a reduced fallback from `gp.dynasty_id` only
- widen bundle persistence in a later spec

My recommendation:

- replay omits dynasty context in this pass
- call it out as an accepted limitation of the no-model-change scope

## Current Test Anchors

Useful existing tests:

- `tests/test_narrative.py`
  - already covers agent-context building
  - already has a focused Gini plumbing test through `_prepare_narration_prompts()`
- `tests/test_agent_bridge.py`
  - already covers bridge snapshot metrics, `dynasty_registry`, and relationship-side data ownership

What new coverage will probably matter once the spec becomes a plan:

- post-loop narration path threads live bridge inputs into `narrate_batch()`
- dynasty context appears when a live registry is supplied
- replay narration degrades safely when bridge-only data is unavailable
- `agent_name_map` and dissolved-edge names remain stable for dead/retired characters

## Recommended Spec Shape

If the next agent wants a tight deliverable, I would aim for:

1. a short scope statement that distinguishes in-process narration from replay narration
2. a caller-by-caller wiring table:
   - `main.py` post-loop API narration
   - `main.py::_run_narrate()`
   - `live.py::narrate_range`
3. an input availability table like the one above
4. one explicit decision on replay behavior:
   - best-effort fallback, not full parity
5. a minimal test strategy section covering:
   - live bridge threading
   - dynasty context
   - replay fallback

## My Recommended End State

For this pass, the simplest durable contract is:

- add `dynasty_registry` to `narrate_batch()` and `_prepare_narration_prompts()`
- thread live bridge-owned narration inputs explicitly from callers that have a bridge
- build `agent_name_map` from `great_persons` when needed
- allow replay callers to pass only what they can reconstruct
- define replay degradation as acceptable for:
  - dynasty context
  - social/dissolution graph context
  - displacement context
  - M43b economy-result context
- optionally recover Gini from snapshots when live bridge data is unavailable

That keeps Spec A small, honest, and shippable without blocking on persistence work.
