# Hostage Affinity Sync Design

> Date: 2026-04-03
> Scope: Python-only plumbing + existing `set_agent_civ()` FFI call
> Depends on: M40 (relationships substrate), M17 (great persons)
> Estimated size: ~30 lines changed across 3 files, 4 new test cases

## Problem

Hostage capture and release are the only named-character civ-transfer paths that do not sync Rust agent civ affinity. Every other transfer site (conquest, exile return, restoration, absorption, secession) already calls `set_agent_civ()` through the bridge. This creates a divergence: after a hostage lifecycle transition, Python says the GP belongs to civ X, but the Rust agent pool still thinks civ Y.

## Invariant

**After any hostage lifecycle transition, if the GP is agent-backed and a bridge exists, Rust civ affinity must match `gp.civilization` in Python.**

This applies to:
- Capture (GP moves from loser to winner)
- Normal release (GP moves from captor back to origin)
- Missing-or-extinct-origin release (origin civ not found or has no regions — GP stays with captor)

## Design Choice: Explicit Bridge Plumbing (Option A)

`capture_hostage()` already accepts `bridge=None`. Finish that pattern:

- Keep `capture_hostage(..., bridge=None)` — already exists
- Add `bridge=None` to `tick_hostages()`
- Add `bridge=None` to `release_hostage()`
- Callsites resolve the bridge and pass it explicitly

**Why not internal `world._agent_bridge` lookup?** Capture already exposes a `bridge` param. Switching to hidden lookup mid-pattern creates inconsistency. Explicit threading keeps bridge ownership visible at every seam and is easier to test.

## Caller Map

### 1. War resolution → `capture_hostage()`

Location: `action_engine.py`, two callsites in `_resolve_war_action()` (lines 417, 427).

Current:
```python
capture_hostage(civ, defender, world, contested_region=result.contested_region)
capture_hostage(defender, civ, world, contested_region=result.contested_region)
```

Change: resolve `bridge = getattr(world, "_agent_bridge", None)` in `_resolve_war_action()` before the capture calls, pass to both.

### 2. Phase 2 → `tick_hostages()`

Location: `simulation.py`, single callsite in Phase 2 automatic effects.

Current:
```python
tick_hostages(world, acc=acc)
```

Change: resolve `bridge = getattr(world, "_agent_bridge", None)`, pass as `bridge=bridge`.

### 3. `tick_hostages()` → `release_hostage()`

Location: `relationships.py`, internal forwarding.

Current:
```python
release_hostage(gp, civ, origin, world, acc=acc)
```

Change: forward `bridge` parameter.

## Function Signature Changes

```python
# capture_hostage — no change, bridge=None already present
def capture_hostage(loser, winner, world, contested_region=None, bridge=None): ...

# tick_hostages — add bridge parameter
def tick_hostages(world, acc=None, bridge=None): ...

# release_hostage — add bridge parameter
def release_hostage(gp, captor, origin, world, acc=None, bridge=None): ...
```

## Sync Logic

### Capture (already exists, currently dormant)

Lines 457-471 of `relationships.py` already contain the sync block. No logic change needed — it activates once callers pass the bridge.

### Normal release

After `gp.civilization = origin.name` and `origin.great_persons.append(gp)`:

```python
if bridge is not None and gp.agent_id is not None:
    origin_idx = next(
        (i for i, c in enumerate(world.civilizations) if c.name == origin.name),
        None,
    )
    if origin_idx is not None:
        try:
            bridge._sim.set_agent_civ(gp.agent_id, origin_idx)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to set GP civ during hostage release (agent_id=%s, civ_idx=%s)",
                gp.agent_id, origin_idx,
            )
```

### Missing-or-extinct-origin release

In `tick_hostages()`, when `origin is None` (civ not found) or `not origin.regions` (extinct), the GP stays with the captor and `gp.civilization = civ.name`. Add sync after that assignment:

```python
if bridge is not None and gp.agent_id is not None:
    captor_idx = next(
        (i for i, c in enumerate(world.civilizations) if c.name == civ.name),
        None,
    )
    if captor_idx is not None:
        try:
            bridge._sim.set_agent_civ(gp.agent_id, captor_idx)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to set GP civ during missing/extinct-origin hostage release (agent_id=%s, civ_idx=%s)",
                gp.agent_id, captor_idx,
            )
```

## Edge Cases

### Synthetic hostages (no agent_id)

`capture_hostage()` can synthesize a hostage when the loser has no candidate GP. Synthetic hostages have `agent_id=None`. All sync blocks gate on `gp.agent_id is not None` — no `set_agent_civ()` call for synthetics.

### No bridge (--agents=off, unit tests)

All sync blocks gate on `bridge is not None`. No behavioral change when bridge is absent. Existing unit tests that don't supply a bridge continue to pass unchanged.

### Civ lookup failure

If `next(...)` returns `None` (civ not found in `world.civilizations`), the sync is silently skipped. This mirrors the existing capture-path pattern and the broader `agent_bridge.py` convention.

## Test Strategy

Build on existing anchors in `tests/test_relationships.py`.

### New test cases

1. **Capture calls `set_agent_civ` when bridge is provided.** Create a mock bridge with a recording `_sim.set_agent_civ`. Call `capture_hostage()` with a GP that has `agent_id`. Assert `set_agent_civ` was called with `(agent_id, winner_civ_idx)`.

2. **Release calls `set_agent_civ` with origin civ index.** Call `release_hostage()` with a mock bridge. Assert `set_agent_civ` was called with `(agent_id, origin_civ_idx)`.

3. **Missing-or-extinct-origin release syncs to captor.** Two sub-cases:
   - Origin civ has no regions (extinct) — assert `set_agent_civ` called with `(agent_id, captor_civ_idx)`.
   - Origin civ not found in `world.civilizations` at all (missing) — assert same sync to captor. Existing regression anchor: `test_audit_batch_e.py:282`.

4. **No-op cases.** Verify no `set_agent_civ` call when:
   - `bridge` is `None`
   - `gp.agent_id` is `None` (synthetic hostage)

### Existing tests unaffected

All existing `test_relationships.py` tests call without `bridge` — they continue to work via the `bridge=None` default.

## Non-Goals

- No Rust schema changes
- No new FFI surface — uses existing `set_agent_civ()`
- No changes to hostage gameplay mechanics (capture probability, release timing, cultural conversion)
- No changes to `AgentBridge.apply_conquest_transitions()` or other bridge-owned transfer paths — those already sync correctly
