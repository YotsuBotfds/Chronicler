# Code Health Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize 60 duplicated civ-index lookups into one helper, deduplicate `_get_civ()`, and delete dead famine legacy code.

**Architecture:** Add `civ_index()` and `get_civ()` to `utils.py`, then find-and-replace across 13 files. Pure refactor — zero behavior change. Delete `_check_famine_legacy` from `ecology.py` (dead code since M34).

**Tech Stack:** Python 3.13+, pytest. No Rust changes.

**Spec:** `docs/superpowers/specs/2026-03-17-code-health-cleanup-design.md`

### Implementation Notes (read before starting)

1. **`action_engine.py:115` is a special case.** It uses `next((i for i, c in enumerate(world.civilizations) if c.name == civ.name), 0)` — note the default value `0`. All other 62 sites use `next(i for ...)` without a default (raises `StopIteration` on miss). The `civ_index()` helper matches the no-default pattern. For line 115, use `civ_index(world, civ.name)` — the civ is always present in that context (it's iterating `world.civilizations` directly), so the default was defensive noise.

2. **Ecology lines 276, 283, 297 are inside `_check_famine_legacy`.** These get deleted with the function in Task 5 — don't replace them individually.

3. **Import pattern.** Every file that gains `civ_index` or `get_civ` already imports from `chronicler.utils` (check `from chronicler.utils import ...` and add to the existing import). If a file doesn't have a utils import yet, add one.

4. **Variable naming.** Most sites assign to `civ_idx`. A few use `target_idx`, `vassal_idx`, `absorber_idx`, etc. Preserve the local variable name — only replace the RHS expression.

---

### Task 1: Add `civ_index()` and `get_civ()` to utils.py

**Files:**
- Modify: `src/chronicler/utils.py`
- Create: `tests/test_utils_civ_helpers.py`

- [ ] **Step 1: Write tests for both helpers**

Create `tests/test_utils_civ_helpers.py`:

```python
"""Tests for civ_index() and get_civ() helpers in utils.py."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

import pytest
from chronicler.models import WorldState, Civilization, Leader, TechEra, Region


def _make_world(civ_names: list[str]) -> WorldState:
    """Create a minimal WorldState with named civs."""
    civs = []
    regions = []
    for name in civ_names:
        region = Region(name=f"{name}_region", terrain="plains", carrying_capacity=10, resources="fertile", controller=name)
        civ = Civilization(
            name=name, population=10, military=5, economy=5, culture=5, stability=50,
            tech_era=TechEra.IRON, treasury=10,
            leader=Leader(name=f"Leader of {name}", trait="cautious", reign_start=0),
            regions=[region.name], values=["Honor"], asabiya=0.5,
        )
        civs.append(civ)
        regions.append(region)
    return WorldState(name="Test", seed=42, turn=0, regions=regions, civilizations=civs, relationships={})


class TestCivIndex:
    def test_finds_existing_civ(self):
        from chronicler.utils import civ_index
        world = _make_world(["Alpha", "Beta", "Gamma"])
        assert civ_index(world, "Alpha") == 0
        assert civ_index(world, "Beta") == 1
        assert civ_index(world, "Gamma") == 2

    def test_raises_on_missing_civ(self):
        from chronicler.utils import civ_index
        world = _make_world(["Alpha"])
        with pytest.raises(StopIteration):
            civ_index(world, "NonExistent")


class TestGetCiv:
    def test_returns_civ_object(self):
        from chronicler.utils import get_civ
        world = _make_world(["Alpha", "Beta"])
        civ = get_civ(world, "Beta")
        assert civ is not None
        assert civ.name == "Beta"

    def test_returns_none_on_miss(self):
        from chronicler.utils import get_civ
        world = _make_world(["Alpha"])
        assert get_civ(world, "NonExistent") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_utils_civ_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name 'civ_index' from 'chronicler.utils'`

- [ ] **Step 3: Add both helpers to utils.py**

Add at end of `src/chronicler/utils.py`:

```python


def civ_index(world, name: str) -> int:
    """Return the index of the named civilization in world.civilizations.

    Raises StopIteration if not found.
    """
    return next(i for i, c in enumerate(world.civilizations) if c.name == name)


def get_civ(world, name: str):
    """Return the Civilization with the given name, or None."""
    for c in world.civilizations:
        if c.name == name:
            return c
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_utils_civ_helpers.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/utils.py tests/test_utils_civ_helpers.py
git commit -m "feat: add civ_index() and get_civ() helpers to utils.py"
```

---

### Task 2: Replace civ_index lookups in politics.py (21 sites)

**Files:**
- Modify: `src/chronicler/politics.py`

- [ ] **Step 1: Add import**

Add `civ_index` to the existing `from chronicler.utils import ...` line in `politics.py`. If no such import exists, add: `from chronicler.utils import civ_index`

- [ ] **Step 2: Replace all 21 occurrences**

Find every line matching `next(i for i, c in enumerate(world.civilizations) if c.name ==` and replace the RHS with `civ_index(world, <name_var>)`. Preserve the LHS variable name.

Lines to replace (preserving variable names):
- Line 50: `civ_idx = civ_index(world, civ.name)`
- Line 63: `civ_idx = civ_index(world, civ.name)`
- Line 236: `civ_idx = civ_index(world, civ.name)`
- Line 307: `civ_idx = civ_index(world, civ.name)`
- Line 410: `vassal_idx = civ_index(world, vassal.name)`
- Line 411: `overlord_idx = civ_index(world, overlord.name)`
- Line 457: `vassal_idx = civ_index(world, vassal.name)`
- Line 598: `civ_idx = civ_index(world, civ.name)`
- Line 609: `rc_idx = civ_index(world, rc.name)`
- Line 675: `sponsor_idx = civ_index(world, sponsor.name)`
- Line 676: `target_idx = civ_index(world, target.name)`
- Line 725: `target_idx = civ_index(world, target.name)`
- Line 850: `civ_idx = civ_index(world, civ.name)`
- Line 892: `absorber_idx = civ_index(world, absorber.name)`
- Line 1044: `civ_idx = civ_index(world, civ.name)`
- Line 1078: `civ_idx = civ_index(world, civ.name)`
- Line 1085: `civ_idx = civ_index(world, civ.name)`
- Line 1209: `civ_idx = civ_index(world, civ.name)`
- Line 1219: `richest_idx = civ_index(world, richest.name)`
- Line 1220: `poorest_idx = civ_index(world, poorest.name)`
- Line 1275: `civ_idx = civ_index(world, civ.name)`

- [ ] **Step 3: Run politics tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_politics.py -v`
Expected: All pass (no behavior change)

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/politics.py
git commit -m "refactor: use civ_index() helper in politics.py (21 sites)"
```

---

### Task 3: Replace civ_index lookups in simulation.py (9 sites) and action_engine.py (7 sites)

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/action_engine.py`

- [ ] **Step 1: Add imports to both files**

Add `civ_index` to each file's existing `from chronicler.utils import ...`.

- [ ] **Step 2: Replace 9 occurrences in simulation.py**

- Line 146: `civ_idx = civ_index(world, civ.name)`
- Line 163: `civ_idx = civ_index(world, civ.name)`
- Line 187: `civ_idx = civ_index(world, civ.name)`
- Line 229: `a_idx = civ_index(world, a.name)`
- Line 235: `b_idx = civ_index(world, b.name)`
- Line 641: `civ_idx = civ_index(world, civ.name)`
- Line 735: `civ_idx = civ_index(world, civ.name)`
- Line 805: `civ_idx = civ_index(world, civ.name)`
- Line 894: `civ_idx = civ_index(world, civ.name)`

- [ ] **Step 3: Replace 7 occurrences in action_engine.py**

- Line 82: `civ_idx = civ_index(world, civ.name)`
- Line 115: `civ_index_val = civ_index(world, civ.name)` (special case: previously had default `0`, but the civ is always present — iterating `world.civilizations` directly)
- Line 336: `target_idx = civ_index(world, target.name)`
- Line 448: `att_idx = civ_index(world, attacker.name)`
- Line 449: `def_idx = civ_index(world, defender.name)`
- Line 561: `civ1_idx = civ_index(world, civ1.name)`
- Line 562: `civ2_idx = civ_index(world, civ2.name)`

**Note on line 115:** Check that the variable name used downstream matches. If the original was `civ_index = next(...)`, rename the local variable to `civ_idx` to avoid shadowing the imported `civ_index` function.

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_simulation.py tests/test_action_engine.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/action_engine.py
git commit -m "refactor: use civ_index() helper in simulation.py and action_engine.py (16 sites)"
```

---

### Task 4: Replace civ_index lookups in remaining 9 files

**Files:**
- Modify: `src/chronicler/culture.py` (5 sites)
- Modify: `src/chronicler/ecology.py` (3 sites — lines 340, 347, 361 only; lines 276, 283, 297 are inside dead code deleted in Task 5)
- Modify: `src/chronicler/leaders.py` (4 sites)
- Modify: `src/chronicler/emergence.py` (3 sites)
- Modify: `src/chronicler/exploration.py` (2 sites)
- Modify: `src/chronicler/succession.py` (2 sites)
- Modify: `src/chronicler/climate.py` (1 site)
- Modify: `src/chronicler/factions.py` (1 site)
- Modify: `src/chronicler/infrastructure.py` (1 site)
- Modify: `src/chronicler/tech.py` (1 site)

- [ ] **Step 1: Add `civ_index` import to each file**

Add `civ_index` to each file's existing `from chronicler.utils import ...`. For files that don't import from utils yet, add a new import line.

- [ ] **Step 2: Replace all occurrences**

**culture.py:**
- Line 225: `ctrl_idx = civ_index(world, controller.name)`
- Line 242: `defender_idx = civ_index(world, defender.name)`
- Line 292: `civ_idx = civ_index(world, civ.name)`
- Line 378: `civ_idx = civ_index(world, civ.name)`
- Line 385: `civ_idx = civ_index(world, civ.name)`

**ecology.py** (only the 3 OUTSIDE `_check_famine_legacy`):
- Line 340: `civ_idx = civ_index(world, civ.name)`
- Line 347: `civ_idx = civ_index(world, civ.name)`
- Line 361: `neighbor_idx = civ_index(world, neighbor.name)`

**leaders.py:**
- Line 219: `civ_idx = civ_index(world, civ.name)`
- Line 227: `civ_idx = civ_index(world, civ.name)`
- Line 239: `civ_idx = civ_index(world, civ.name)`
- Line 296: `other_idx = civ_index(world, other_civ.name)`

**emergence.py:**
- Line 291: `civ_idx = civ_index(world, civ.name)`
- Line 396: `civ_idx = civ_index(world, civ.name)`
- Line 427: `civ_idx = civ_index(world, civ.name)`

**exploration.py:**
- Line 92: `civ_idx = civ_index(world, civ.name)`
- Line 195: `civ_idx = civ_index(world, civ.name)`

**succession.py:**
- Line 252: `origin_idx = civ_index(world, origin.name)`
- Line 257: `civ_idx = civ_index(world, civ.name)`

**climate.py:**
- Line 219: `recv_idx = civ_index(world, recv_civ.name)`

**factions.py:**
- Line 343: `civ_idx = civ_index(world, civ.name)`

**infrastructure.py:**
- Line 170: `civ_idx = civ_index(world, civ.name)`

**tech.py:**
- Line 110: `civ_idx = civ_index(world, civ.name)`

- [ ] **Step 3: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_agent_bridge.py --ignore=tests/test_e2e.py --ignore=tests/test_culture.py --ignore=tests/test_fork.py --ignore=tests/test_interactive.py --ignore=tests/test_batch_websocket.py --ignore=tests/test_m10_integration.py`

(Ignore tests that require the Rust FFI crate. If all other tests pass, the replacements are correct.)

Expected: All non-FFI tests pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/culture.py src/chronicler/ecology.py src/chronicler/leaders.py src/chronicler/emergence.py src/chronicler/exploration.py src/chronicler/succession.py src/chronicler/climate.py src/chronicler/factions.py src/chronicler/infrastructure.py src/chronicler/tech.py
git commit -m "refactor: use civ_index() helper in 10 remaining files (23 sites)"
```

---

### Task 5: Replace `_get_civ()` call sites, delete duplicate definitions

**Files:**
- Modify: `src/chronicler/action_engine.py` (delete definition at line 69, replace 4 call sites)
- Modify: `src/chronicler/simulation.py` (delete definition at line 87, replace 8 call sites)

- [ ] **Step 1: Add `get_civ` import to both files**

Add `get_civ` to each file's existing `from chronicler.utils import ...` (which now already includes `civ_index` from Task 3).

- [ ] **Step 2: Delete `_get_civ` definition from action_engine.py**

Delete lines 69-73 (the `def _get_civ(world, name)` function).

- [ ] **Step 3: Replace 4 call sites in action_engine.py**

Change `_get_civ(world, ...)` to `get_civ(world, ...)` at:
- Line 157: `best_partner = get_civ(world, other_name)`
- Line 229: `other_civ = get_civ(world, other_name)`
- Line 250: `defender = get_civ(world, target_name)`
- Line 323: `target = get_civ(world, target_name)`

- [ ] **Step 4: Delete `_get_civ` definition from simulation.py**

Delete lines 87-91 (the `def _get_civ(world, name)` function).

- [ ] **Step 5: Replace 8 call sites in simulation.py**

Change `_get_civ(world, ...)` to `get_civ(world, ...)` at:
- Line 225: `a = get_civ(world, civ_a)`
- Line 226: `b = get_civ(world, civ_b)`
- Line 240: `c = get_civ(world, civ_name)`
- Line 315: `c = get_civ(world, civ_name)`
- Line 364: `c = get_civ(world, civ_name)`
- Line 628: `affected_civ = get_civ(world, event.actors[0])`
- Line 731: `civ = get_civ(world, target_civ_name)`
- Line 803: `civ = get_civ(world, civ_name)`

- [ ] **Step 6: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_simulation.py tests/test_action_engine.py -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/simulation.py
git commit -m "refactor: deduplicate _get_civ() into utils.get_civ() (12 call sites)"
```

---

### Task 6: Delete `_check_famine_legacy` from ecology.py

**Files:**
- Modify: `src/chronicler/ecology.py`

- [ ] **Step 1: Delete the function**

Delete `_check_famine_legacy` (lines 254-307 approximately — from `def _check_famine_legacy` through the `return events` line and trailing blank lines).

- [ ] **Step 2: Clean up informational references**

Two comments in ecology.py reference the deleted function:
- Line ~337: `# --- Effects below are identical to _check_famine_legacy ---` — update to: `# --- Famine effects ---`
- Line ~633: `# M34: Yield-based famine (replaces water-sentinel _check_famine_legacy)` — update to: `# M34: Yield-based famine check`

- [ ] **Step 3: Run ecology tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ecology.py -v`
Expected: All pass (function was never called)

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/ecology.py
git commit -m "cleanup: delete dead _check_famine_legacy (replaced by _check_famine_yield in M34)"
```

---

### Task 7: Verification and final commit

- [ ] **Step 1: Verify no inline civ_index patterns remain**

Run: `grep -rn "next(i for i, c in enumerate(world.civilizations)" src/chronicler/`
Expected: **0 matches**

Also: `grep -rn "next((i for i, c in enumerate(world.civilizations)" src/chronicler/`
Expected: **0 matches**

- [ ] **Step 2: Verify no duplicate `_get_civ` definitions remain**

Run: `grep -rn "def _get_civ" src/chronicler/`
Expected: **0 matches**

- [ ] **Step 3: Verify `_check_famine_legacy` is fully removed**

Run: `grep -rn "_check_famine_legacy" src/chronicler/`
Expected: **0 matches**

- [ ] **Step 4: Run full test suite one last time**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_agent_bridge.py --ignore=tests/test_e2e.py --ignore=tests/test_culture.py --ignore=tests/test_fork.py --ignore=tests/test_interactive.py --ignore=tests/test_batch_websocket.py --ignore=tests/test_m10_integration.py`

Expected: All non-FFI tests pass

- [ ] **Step 5: Squash or leave as-is based on preference**

The 6 commits tell a clean story. Leave as-is unless user prefers squash.
