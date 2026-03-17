# Code Health Cleanup — Design Spec

> **Status:** Approved. Ready for implementation planning.
>
> **Scope:** Low-risk cleanup — centralize duplicated civ lookups, delete dead code. No architectural changes, no behavior changes.
>
> **Triggered by:** External code health review (2026-03-17). Claims verified, recommendations filtered for actual merit.

---

## Overview

An external review identified legitimate code duplication and dead code in the Chronicler Python codebase. This spec covers the three changes worth making now. Everything else was either misdiagnosed (test suite "broken" = wrong Python interpreter), architecturally intentional (accumulator branching), a forward placeholder (trade_route_count for M42), or premature (splitting politics.py at 1284 lines).

---

## Change 1: Centralize `civ_index()` and `get_civ()` in utils.py

### Problem

The pattern `next(i for i, c in enumerate(world.civilizations) if c.name == name)` appears **62 times** across 13 files. Additionally, an identical `_get_civ(world, name)` helper (returns the Civilization object, not the index) is duplicated in `action_engine.py:69` and `simulation.py:87`.

This is a verbosity problem, not a performance problem — the list has 4-12 civs. But 62 inline copies of the same 1-liner create noise that obscures the actual game logic.

### Design

Add two functions to `src/chronicler/utils.py`:

```python
def civ_index(world, name: str) -> int:
    """Return the index of the civilization with the given name.

    Raises StopIteration if not found (same behavior as the inline pattern).
    """
    return next(i for i, c in enumerate(world.civilizations) if c.name == name)


def get_civ(world, name: str):
    """Return the Civilization object with the given name, or None."""
    for c in world.civilizations:
        if c.name == name:
            return c
    return None
```

**Type annotations:** `world` is typed as a bare parameter (not `WorldState`) to avoid a circular import — `utils.py` is imported by `models.py`. This matches the existing `sync_civ_population(civ, world)` pattern already in utils.py.

**Error behavior:** `civ_index()` raises `StopIteration` on miss, exactly like the inline `next(...)` it replaces. `get_civ()` returns `None` on miss, exactly like the existing `_get_civ()` implementations.

### Affected Files

Replace 60 inline `civ_index` lookups across 13 files (62 total occurrences minus 2 inside `_check_famine_legacy` which is deleted in Change 2):

| File | Count |
|------|-------|
| politics.py | 21 |
| simulation.py | 9 |
| action_engine.py | 6 |
| ecology.py | 3 (6 total minus 3 inside `_check_famine_legacy`) |
| leaders.py | 4 |
| culture.py | 5 |
| emergence.py | 3 |
| exploration.py | 2 |
| succession.py | 2 |
| climate.py | 1 |
| factions.py | 1 |
| infrastructure.py | 1 |
| tech.py | 1 |

Replace 12 `_get_civ()` call sites:
- action_engine.py: 4 calls (delete local `_get_civ` definition at line 69)
- simulation.py: 8 calls (delete local `_get_civ` definition at line 87)

### What Doesn't Change

- Behavior — every replacement is semantically identical
- Performance — same O(N) scan, N is 4-12
- Accumulator pattern — untouched
- `_get_civ_resources` in tech.py — different function, different purpose, stays

---

## Change 2: Delete `_check_famine_legacy` from ecology.py

### Problem

`_check_famine_legacy()` at ecology.py:254 is ~50 lines of dead code. The docstring says "Preserved but no longer called." Line 633 confirms it was replaced by `_check_famine_yield()` (M34). No call sites reference it.

### Design

Delete the function definition (lines 254–309, approximately). No callers to update.

---

## Change 3: Roadmap Notes for Deferred Items

Add a "Code Health Notes" section to the Phase 6 roadmap documenting items that don't warrant immediate action but should be tracked:

1. **M42 — trade_route_count:** `build_region_batch()` in agent_bridge.py sends hardcoded zeros for `trade_route_count`. The Rust side reads this for merchant satisfaction (`satisfaction.rs` line 101: `0.4 + (trade_routes as f32 / 3.0).min(1.0) * 0.3`). When M42 implements trade routes, wire real per-region counts into the batch. Merchants currently get no trade-route satisfaction bonus.

2. **M47 — analytics.py size:** At 1500 lines, analytics.py is the largest file. Its functions are genuinely independent (per-metric extractors). If it grows further during Phase 6, consider splitting by metric category. Not urgent — the functions don't interact.

3. **M47 — civ_index caching:** If civ count exceeds ~20 (e.g. via M38b schism-spawned successor states), the O(N) `civ_index()` helper becomes worth caching. Add a `_civ_name_to_idx: dict[str, int]` on WorldState, invalidated on civ list mutation. Not needed at current N=4-12.

---

## Validation

- **Existing tests:** All 60 civ_index replacements and 12 get_civ replacements are covered by existing test paths. No new tests needed — the helpers are trivial wrappers.
- **Grep verification:** After replacement, `next(i for i, c in enumerate(world.civilizations) if c.name` should return 0 matches. `def _get_civ` should return 0 matches in action_engine.py and simulation.py.
- **`_check_famine_legacy` removal:** Grep for `_check_famine_legacy` should return 0 matches after deletion (currently 3: definition, comment in `_check_famine_yield`, and the line 633 comment — the latter two are informational references, not calls, and should be cleaned up).

---

## What Was Explicitly Rejected

| External Recommendation | Why Rejected |
|---|---|
| "Test suite is broken" | Reviewer ran wrong Python. 1205/1212 tests pass with `.venv`. |
| Abstract accumulator branching | Intentional design — the if/else IS the hybrid/aggregate mode seam |
| Split politics.py into 3 files | Creates cross-file coupling worse than 1284 lines of cohesive code |
| Dict-ify world.civilizations | Wrong tradeoff for N=4-12. Touches serialization, save/load, every iteration |
| Delete trade_route_count | Forward placeholder for M42 merchant satisfaction — Rust reads it |
