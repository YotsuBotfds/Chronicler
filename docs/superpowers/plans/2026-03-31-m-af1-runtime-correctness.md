# M-AF1: Runtime Correctness & Safety — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 17 runtime correctness and safety bugs identified by the 2026-03-31 dual-model audit, gated by 200-seed adjudicated comparison.

**Architecture:** Each task is an independent bug fix with its own regression test. No task depends on another except Tasks 9a/9b (martyrdom decay before filter). All fixes target Python simulation code except Tasks 11-12 (Python+Rust ecology/religion), Tasks 13-14 (Rust FFI + Python bridge), and Task 15 (Rust FFI safety).

**Tech Stack:** Python 3.13+, Rust (PyO3/Arrow FFI), pytest, cargo nextest

**Spec:** `docs/superpowers/specs/2026-03-31-m-af1-runtime-correctness-design.md`

**Subagent dispatch checklist (from CLAUDE.md):**
1. No Rust struct literals in tests — use constructor functions.
2. Verify all referenced file paths and function signatures exist via Read/Grep before editing.
3. Check float vs int types on all arithmetic, especially treasury/tithe/population fields.
4. After deleting or renaming any function, grep for all callers and test imports.
5. Run the relevant test suite after each task (`cargo nextest run` for Rust, `pytest` for Python). Fix before reporting done.
6. Check that Python-Rust bridge types match (column counts, field names in Arrow batches).
7. Do not create files outside the scope specified in the task.

---

## Task 1: Governing cost stability fix

**Spec item:** #6 — `int(0.5)` truncation
**Files:**
- Modify: `src/chronicler/politics.py:68`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing test**

In `tests/test_politics.py`, add:

```python
def test_governing_cost_stability_nonzero(make_world):
    """M-AF1 #6: governing cost stability should be nonzero for distant regions."""
    world = make_world(3)
    civ = world.civilizations[0]
    civ.regions = [r.name for r in world.regions]
    civ.capital_region = world.regions[0].name
    civ.stability = 80

    from chronicler.politics import apply_governing_costs
    apply_governing_costs(world)

    # With default K_GOVERNING_COST=0.5 and distance >= 1,
    # stability should decrease (not stay at 80)
    assert civ.stability < 80, (
        f"Governing cost stability should be nonzero but stability stayed at {civ.stability}"
    )
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_politics.py::test_governing_cost_stability_nonzero -v`
Expected: FAIL — stability stays at 80 because `int(0.5)` = 0.

- [ ] **Step 3: Fix the truncation**

In `src/chronicler/politics.py:68`, change:

```python
# BEFORE:
gov_cost_per_dist = int(get_override(world, K_GOVERNING_COST, 0.5))

# AFTER:
gov_cost_per_dist = get_override(world, K_GOVERNING_COST, 0.5)
```

Then on line 82, the `int()` cast is already applied to `stability_cost * mult`, which handles the float→int conversion after multiplication. Verify that `stability_cost += dist * gov_cost_per_dist` now accumulates a float, and `int(stability_cost * mult)` produces the final integer drain.

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_politics.py::test_governing_cost_stability_nonzero -v`
Expected: PASS

- [ ] **Step 5: Run full politics test suite**

Run: `pytest tests/test_politics.py -q`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "fix(m-af1): governing cost stability no longer truncated to zero (#6)"
```

---

## Task 2: Black market leakage — scan all regions

**Spec item:** #16 — only first region checked
**Files:**
- Modify: `src/chronicler/simulation.py:311`
- Test: `tests/test_simulation.py`

- [ ] **Step 1: Write failing test**

In `tests/test_simulation.py`, add:

```python
def test_black_market_checks_all_regions(make_world):
    """M-AF1 #16: black market should scan all controlled regions, not just first."""
    world = make_world(3)
    civ = world.civilizations[0]
    other = world.civilizations[1]
    # civ controls regions 0 and 1; other controls region 2
    world.regions[0].controller = civ.name
    world.regions[1].controller = civ.name
    world.regions[2].controller = other.name
    civ.regions = [world.regions[0].name, world.regions[1].name]
    other.regions = [world.regions[2].name]
    # Region 0 has no adjacency to region 2 (no smuggling route)
    world.regions[0].adjacencies = [world.regions[1].name]
    # Region 1 IS adjacent to region 2 (valid smuggling route)
    world.regions[1].adjacencies = [world.regions[0].name, world.regions[2].name]
    world.regions[2].adjacencies = [world.regions[1].name]
    # Set up embargo
    world.embargoes = [(civ.name, other.name)]
    civ.treasury = 50
    civ.stability = 50

    from chronicler.simulation import apply_automatic_effects
    apply_automatic_effects(world)  # Signature: (world, acc=None) — no seed param

    # Black market should fire via region 1's route to region 2
    assert civ.treasury == 51, f"Expected treasury 51 (black market +1), got {civ.treasury}"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_simulation.py::test_black_market_checks_all_regions -v`
Expected: FAIL — treasury stays at 50 (or only drops from war costs) because the break on line 311 exits after checking region 0.

- [ ] **Step 3: Remove the premature break**

In `src/chronicler/simulation.py:311`, remove the line:

```python
# REMOVE this line:
            break  # Only check first controlled region for simplicity
```

The inner `break` at line 310 (`break  # Only one black market route per civ per turn`) already ensures at most one payout per civ. The outer `break` was prematurely stopping the region scan.

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_simulation.py::test_black_market_checks_all_regions -v`
Expected: PASS

- [ ] **Step 5: Run related test suite**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "fix(m-af1): black market scans all controlled regions (#16)"
```

---

## Task 3: Clear `conquest_conversion_active` unconditionally

**Spec item:** #14 — stale flag in off-mode
**Files:**
- Modify: `src/chronicler/simulation.py` (turn-start clearing)
- Test: `tests/test_simulation.py`

- [ ] **Step 1: Write failing test**

```python
def test_conquest_conversion_clears_each_turn_off_mode(make_world):
    """M-AF1 #14: conquest_conversion_active must clear each turn regardless of mode."""
    world = make_world(2)
    world.agent_mode = "off"
    # Manually set the flag on a region
    world.regions[0].conquest_conversion_active = True

    from chronicler.simulation import run_turn
    # Run one turn in off-mode
    run_turn(world, action_selector=lambda c, w: __import__('chronicler.models', fromlist=['ActionType']).ActionType.DEVELOP,
             narrator=lambda *a, **kw: "narration", seed=42)

    assert not getattr(world.regions[0], 'conquest_conversion_active', False), \
        "conquest_conversion_active should be cleared after turn in off-mode"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_simulation.py::test_conquest_conversion_clears_each_turn_off_mode -v`
Expected: FAIL — flag persists.

- [ ] **Step 3: Add unconditional clearing at turn start**

In `src/chronicler/simulation.py`, in `run_turn()`, near the top of the function (before Phase 1), add:

```python
    # M-AF1 #14: Clear transient conquest conversion flags unconditionally
    for r in world.regions:
        r.conquest_conversion_active = False
```

Find the appropriate location — after the `_conquered_this_turn` initialization but before Phase 1 begins.

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_simulation.py::test_conquest_conversion_clears_each_turn_off_mode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "fix(m-af1): clear conquest_conversion_active unconditionally at turn start (#14)"
```

---

## Task 4: Severity multiplier gaps

**Spec item:** #9 — plague stability + war bankruptcy stability
**Files:**
- Modify: `src/chronicler/simulation.py:168,326`
- Test: `tests/test_severity.py`

- [ ] **Step 1: Write failing test for plague stability**

The buggy code is in `phase_environment()` at `simulation.py:168`, inside the `elif event.event_type == "plague"` branch. Severity uses `civ.civ_stress` (via `get_severity_multiplier(civ, world)` at line 160), not `world.stress_index`. The test must trigger a plague event through `phase_environment()` with a high-stress civ.

```python
def test_plague_stability_uses_severity_multiplier(make_world):
    """M-AF1 #9: plague stability drain must scale with severity."""
    world = make_world(2)
    civ = world.civilizations[0]
    civ.stability = 80
    # Set high civ_stress so severity multiplier > 1.0
    civ.civ_stress = 15

    from chronicler.emergence import get_severity_multiplier
    mult = get_severity_multiplier(civ, world)
    assert mult > 1.0, f"Test setup: severity multiplier should be > 1.0, got {mult}"

    raw_drain = 3  # default K_PLAGUE_STABILITY
    pre_stability = civ.stability

    # Force a plague event by setting event_probabilities to guarantee plague
    world.event_probabilities = {"plague": 1.0}

    from chronicler.simulation import phase_environment
    phase_environment(world, seed=42, acc=None)

    actual_drain = pre_stability - civ.stability
    expected_min_drain = int(raw_drain * mult)
    # Before fix: drain = int(3) = 3 regardless of stress
    # After fix: drain = int(3 * mult) > 3
    assert actual_drain >= expected_min_drain, \
        f"Plague drain should be >= {expected_min_drain} (raw {raw_drain} * mult {mult:.2f}), got {actual_drain}"
```

Note: If `phase_environment` doesn't roll plague on this seed, the test may need to try multiple seeds or mock `roll_for_event`. The implementor should verify the event fires before asserting the drain.

- [ ] **Step 2: Fix plague stability drain**

In `src/chronicler/simulation.py:168`, change:

```python
# BEFORE:
drain = int(get_override(world, K_PLAGUE_STABILITY, 3))

# AFTER:
drain = int(get_override(world, K_PLAGUE_STABILITY, 3) * mult)
```

The `mult` variable is already in scope from line 160.

- [ ] **Step 3: Write failing test for war-bankruptcy stability drain**

The bankruptcy drain is at `simulation.py:326` (acc path) and `:331` (direct path), inside `apply_automatic_effects()`. It fires when a civ's treasury goes to zero from war costs (-3/turn per active war).

```python
def test_war_bankruptcy_stability_uses_severity_multiplier(make_world):
    """M-AF1 #9: war bankruptcy stability drain must scale with severity."""
    world = make_world(2)
    civ = world.civilizations[0]
    other = world.civilizations[1]
    civ.stability = 80
    civ.treasury = 2  # Will go to -1 after -3 war cost → triggers bankruptcy drain
    # With civ_stress=15, formula is: 1.0 + (15/20)*0.5 = 1.375
    # int(2 * 1.375) = int(2.75) = 2, same as unfixed! Need higher stress.
    # With civ_stress=20, formula is: 1.0 + (20/20)*0.5 = 1.5
    # int(2 * 1.5) = int(3.0) = 3, which differs from raw 2.
    civ.civ_stress = 20  # Severity = 1.5 → int(2*1.5) = 3 ≠ 2
    world.active_wars = [(civ.name, other.name)]

    from chronicler.emergence import get_severity_multiplier
    mult = get_severity_multiplier(civ, world)
    assert mult >= 1.5, f"Test setup: severity multiplier should be >= 1.5, got {mult}"

    pre_stability = civ.stability
    raw_drain = 2  # default K_WAR_COST_STABILITY
    expected_drain = int(raw_drain * mult)
    assert expected_drain > raw_drain, f"Test setup: int({raw_drain} * {mult}) must exceed {raw_drain}"

    from chronicler.simulation import apply_automatic_effects
    apply_automatic_effects(world)

    actual_drain = pre_stability - civ.stability
    expected_min_drain = int(raw_drain * mult)
    assert actual_drain >= expected_min_drain, \
        f"War bankruptcy drain should be >= {expected_min_drain} (raw {raw_drain} * mult {mult:.2f}), got {actual_drain}"
```

- [ ] **Step 4: Fix war-bankruptcy stability drain**

In `src/chronicler/simulation.py:326` (acc path) and `:331` (direct path), add severity multiplier. Both lines currently read:

```python
drain = int(get_override(world, K_WAR_COST_STABILITY, 2))
```

Change both to:

```python
war_mult = get_severity_multiplier(c, world)
drain = int(get_override(world, K_WAR_COST_STABILITY, 2) * war_mult)
```

`get_severity_multiplier` is already imported in `simulation.py`. The variable `c` is the current civ in scope at both sites.

- [ ] **Step 5: Audit remaining negative stat drains**

Grep for patterns like `drain = int(get_override(` in `simulation.py` and verify each applies `* mult`. Document any additional gaps found and fix them.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_severity.py tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add src/chronicler/simulation.py tests/test_severity.py
git commit -m "fix(m-af1): apply severity multiplier to plague and war bankruptcy stability drains (#9)"
```

---

## Task 5: Resolved-action bookkeeping

**Spec item:** #3 — record resolved action, not selected action
**Files:**
- Modify: `src/chronicler/simulation.py:559-581`
- Modify: `src/chronicler/action_engine.py:294-296`
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test**

The real bug is in `phase_action()` (simulation.py:575-581), not in `resolve_action()`. The test must exercise the full `phase_action()` path to verify `action_history` and `action_counts` record the resolved action.

```python
def test_war_fallback_records_develop_in_history(make_world):
    """M-AF1 #3: WAR falling back to DEVELOP should record 'develop' in history and counts."""
    from chronicler.models import ActionType
    world = make_world(2)
    civ = world.civilizations[0]
    # No hostile/suspicious target — WAR will fall back to DEVELOP
    for name, rel in world.relationships.get(civ.name, {}).items():
        rel.disposition = "friendly"

    world.action_history[civ.name] = []
    civ.action_counts = {}

    # phase_action signature: (world, action_selector, acc=None) — no seed param
    from chronicler.simulation import phase_action
    phase_action(world, action_selector=lambda c, w: ActionType.WAR)

    # History and counts should record "develop", not "war"
    assert world.action_history[civ.name][-1] == "develop", \
        f"Expected 'develop' in history, got {world.action_history[civ.name][-1]}"
    assert civ.action_counts.get("develop", 0) > 0, "develop should be counted"
    assert civ.action_counts.get("war", 0) == 0, "war should NOT be counted when it fell back"
```

- [ ] **Step 2: Modify phase_action to record resolved action**

The key change is in `src/chronicler/simulation.py:574-581`. Currently:

```python
# Track action in history (for streak breaker)
history = world.action_history.setdefault(civ.name, [])
history.append(action.value)  # Records SELECTED action
# Track action counts (for trait evolution)
civ.action_counts[action.value] = civ.action_counts.get(action.value, 0) + 1
```

Change the bookkeeping to use the resolved action from the event:

```python
# M-AF1 #3: Record the resolved action, not the selected action
resolved_action = event.event_type if event.event_type in {a.value for a in ActionType} else action.value
history = world.action_history.setdefault(civ.name, [])
history.append(resolved_action)
civ.action_counts[resolved_action] = civ.action_counts.get(resolved_action, 0) + 1
```

Note: `event.event_type` for action results matches `ActionType.value` (e.g., "develop", "war", "trade"). Verify this mapping.

- [ ] **Step 3: Run test, verify it passes**

Run: `pytest tests/test_action_engine.py::test_war_fallback_records_develop_in_history -v`
Expected: PASS

- [ ] **Step 4: Run full action engine test suite**

Run: `pytest tests/test_action_engine.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add src/chronicler/simulation.py src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "fix(m-af1): record resolved action in history and counts, not selected action (#3)"
```

---

## Task 6: TRADE route existence check

**Spec item:** #2 — TRADE pays without active route
**Files:**
- Modify: `src/chronicler/action_engine.py:200-216`
- Test: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test**

```python
def test_trade_requires_active_route(make_world):
    """M-AF1 #2: TRADE should not pay out without an active trade route."""
    from chronicler.models import ActionType
    world = make_world(2)
    civ = world.civilizations[0]
    other = world.civilizations[1]
    # Make them friendly (disposition >= neutral) but with no adjacency
    if civ.name in world.relationships and other.name in world.relationships[civ.name]:
        world.relationships[civ.name][other.name].disposition = "friendly"
    # Remove all adjacencies so no trade route exists
    for r in world.regions:
        r.adjacencies = []

    pre_treasury = civ.treasury

    from chronicler.action_engine import resolve_action
    event = resolve_action(civ, ActionType.TRADE, world)

    # Without a route, trade should fall back — treasury should not increase
    assert event.event_type != "trade" or "no willing" in event.description or civ.treasury == pre_treasury, \
        f"TRADE paid out without an active route: treasury went from {pre_treasury} to {civ.treasury}"
```

- [ ] **Step 2: Add route existence check**

In `src/chronicler/action_engine.py`, in `_resolve_trade()`, before `resolve_trade()` is called, add a route check. `get_active_trade_routes()` in `resources.py:134` returns `list[tuple[str, str]]` where each tuple is a **sorted civ-name pair** (e.g., `("CivA", "CivB")`). The check is a simple membership test:

```python
    if best_partner and best_disp >= 2:  # At least neutral
        # M-AF1 #2: Verify an active trade route exists between these civs
        from chronicler.resources import get_active_trade_routes
        routes = get_active_trade_routes(world)
        civ_pair = tuple(sorted([civ.name, best_partner.name]))
        if civ_pair not in set(routes):
            # No route — fall back to actual develop resolution
            return _resolve_develop(civ, world, acc=acc)
        resolve_trade(civ, best_partner, world, acc=acc)
```

Note: The fallback calls `_resolve_develop()` so the civ gets real develop effects (treasury spend, economy/culture boost), not an empty event.

- [ ] **Step 3: Run test, verify it passes**

Run: `pytest tests/test_action_engine.py::test_trade_requires_active_route -v`
Expected: PASS

- [ ] **Step 4: Run full suite**

Run: `pytest tests/test_action_engine.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "fix(m-af1): TRADE requires active route, falls back to develop if none (#2)"
```

---

## Task 7: Populate `war_start_turns`

**Spec item:** #4 — congress ignores war duration
**Files:**
- Modify: `src/chronicler/action_engine.py:300-305`
- Modify: `src/chronicler/simulation.py` or `action_engine.py` (war end cleanup)
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing test**

```python
def test_war_start_turns_populated(make_world):
    """M-AF1 #4: normal wars should populate war_start_turns."""
    from chronicler.models import ActionType
    world = make_world(2)
    world.turn = 10
    civ = world.civilizations[0]
    other = world.civilizations[1]
    # Set up hostile relationship for WAR
    if civ.name in world.relationships:
        world.relationships[civ.name][other.name].disposition = "hostile"
    if other.name in world.relationships:
        world.relationships[other.name][civ.name].disposition = "hostile"
    civ.military = 80
    other.military = 30

    from chronicler.action_engine import resolve_action
    resolve_action(civ, ActionType.WAR, world)

    # war_start_turns should have an entry for this war
    assert len(world.war_start_turns) > 0, "war_start_turns should be populated after war resolution"
    key = next(iter(world.war_start_turns))
    assert world.war_start_turns[key] == 10, f"War start turn should be 10, got {world.war_start_turns[key]}"
```

- [ ] **Step 2: Add war_start_turns stamping**

In `src/chronicler/action_engine.py`, after the war is added to `world.active_wars` (around line 304-305), add:

```python
        # M-AF1 #4: Stamp war start turn
        war_key_str = war_key(civ.name, target_name)
        if war_key_str not in world.war_start_turns:
            world.war_start_turns[war_key_str] = world.turn
```

Import `war_key` from `politics.py` if not already imported. Verify the `war_key()` function signature — it likely returns a canonical string like `"CivA:CivB"`.

- [ ] **Step 3: Add cleanup on war end**

Find where wars are removed from `active_wars` (in `_resolve_diplomacy` when disposition reaches FRIENDLY, and in `prune_inactive_wars`). Add corresponding `war_start_turns.pop(key, None)` cleanup.

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_politics.py::test_war_start_turns_populated -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/chronicler/action_engine.py src/chronicler/politics.py tests/test_politics.py
git commit -m "fix(m-af1): populate and clean war_start_turns on normal war lifecycle (#4)"
```

---

## Task 8: Wire federation defense

**Spec item:** #5 — federations provide no mutual defense
**Files:**
- Modify: `src/chronicler/action_engine.py` (war resolution path)
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing test**

```python
def test_federation_defense_triggers(make_world):
    """M-AF1 #5: attacking a federation member should pull allies into war."""
    world = make_world(3)
    attacker = world.civilizations[0]
    defender = world.civilizations[1]
    ally = world.civilizations[2]
    # Set up federation between defender and ally
    from chronicler.models import Federation
    world.federations = [Federation(name="Alliance", members=[defender.name, ally.name], founded_turn=1)]
    # Set up hostile relationship for WAR
    if attacker.name in world.relationships:
        world.relationships[attacker.name][defender.name].disposition = "hostile"
    if defender.name in world.relationships:
        world.relationships[defender.name][attacker.name].disposition = "hostile"
    attacker.military = 80
    defender.military = 30
    ally.military = 40

    from chronicler.models import ActionType
    from chronicler.action_engine import resolve_action
    resolve_action(attacker, ActionType.WAR, world)

    # Ally should now be at war with attacker
    all_wars = [(a, b) for a, b in world.active_wars]
    ally_at_war = any(
        (attacker.name in pair and ally.name in pair)
        for pair in [(a, b) for a, b in world.active_wars]
    )
    assert ally_at_war, f"Federation ally should have entered war. Active wars: {world.active_wars}"
```

- [ ] **Step 2: Wire trigger_federation_defense**

In `src/chronicler/action_engine.py`, in `_resolve_war_action()`, after the war is added to `active_wars` (around line 304-305), add:

```python
        # M-AF1 #5: Federation mutual defense
        from chronicler.politics import trigger_federation_defense
        fed_events = trigger_federation_defense(civ.name, target_name, world)
        # Append federation defense events to the timeline so they appear in
        # narration and analytics (trigger_federation_defense returns list[Event])
        world.events_timeline.extend(fed_events)
```

`trigger_federation_defense(attacker: str, defender: str, world)` returns `list[Event]` containing `federation_defense` events. It also stamps `war_start_turns` for the new wars internally (politics.py:732).

- [ ] **Step 3: Run test, verify it passes**

Run: `pytest tests/test_politics.py::test_federation_defense_triggers -v`
Expected: PASS

- [ ] **Step 4: Run full suite**

Run: `pytest tests/test_politics.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add src/chronicler/action_engine.py tests/test_politics.py
git commit -m "fix(m-af1): wire federation mutual defense into war resolution (#5)"
```

---

## Task 9a: Martyrdom boost decay wiring

**Spec item:** #11 — decay never called
**Files:**
- Modify: `src/chronicler/simulation.py` (turn loop)
- Test: `tests/test_religion.py`

- [ ] **Step 1: Write failing test**

```python
def test_martyrdom_boost_decays(make_world):
    """M-AF1 #11: martyrdom boost should decay over turns."""
    world = make_world(2)
    # Set a martyrdom boost on a region
    world.regions[0].martyrdom_boost = 0.15
    world.regions[0].controller = world.civilizations[0].name

    from chronicler.religion import decay_martyrdom_boosts
    decay_martyrdom_boosts(world.regions)  # Takes list[Region], not world

    assert world.regions[0].martyrdom_boost < 0.15, \
        f"Martyrdom boost should have decayed, got {world.regions[0].martyrdom_boost}"
```

- [ ] **Step 2: Verify `decay_martyrdom_boosts()` exists and works**

Read `src/chronicler/religion.py:594` to confirm the function exists and performs decay. It should already be implemented — just never called.

- [ ] **Step 3: Wire into turn loop**

In `src/chronicler/simulation.py`, find where `compute_conversion_signals()` is called (around line 967). The current order is: `compute_conversion_signals()` → `compute_martyrdom_boosts()`. The decay must run BEFORE `compute_conversion_signals()` so that conversion signals consume the decayed (not fresh) boost, and new deaths only affect the NEXT turn's conversion.

Insert the decay call before `compute_conversion_signals()`:

```python
    # M-AF1 #11: Decay existing martyrdom boost before conversion signals consume it
    from chronicler.religion import decay_martyrdom_boosts
    decay_martyrdom_boosts(world.regions)
```

Note: `decay_martyrdom_boosts` takes `regions: list[Region]`, not `world`. The ordering is: decay → conversion signals (reads decayed boost) → new martyrdom inputs (from this turn's deaths, affect next turn).

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_religion.py::test_martyrdom_boost_decays -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add src/chronicler/simulation.py tests/test_religion.py
git commit -m "fix(m-af1): wire martyrdom boost decay into turn loop (#11)"
```

---

## Task 9b: Martyrdom boost death filtering

**Spec item:** #12 — applies to all deaths
**Files:**
- Modify: `src/chronicler/religion.py` (`compute_martyrdom_boosts`)
- Test: `tests/test_religion.py`

- [ ] **Step 1: Write failing test**

```python
def test_martyrdom_ignores_non_persecuted_deaths(make_world):
    """M-AF1 #12: deaths in non-persecuted regions should not boost martyrdom."""
    world = make_world(2)
    region = world.regions[0]
    region.controller = world.civilizations[0].name
    region.martyrdom_boost = 0.0
    # Region is NOT persecuted
    region.persecution_intensity = 0.0

    # Use region_idx (int index), not region name — compute_martyrdom_boosts
    # expects {"region_idx": int, "belief": int} per religion.py:573
    dead_agents = [{"region_idx": 0, "belief": 1}]  # Minority faith, region index 0

    from chronicler.religion import compute_martyrdom_boosts
    compute_martyrdom_boosts(world.regions, dead_agents)  # Takes list[Region], not world

    assert region.martyrdom_boost == 0.0, \
        f"Martyrdom should not increase in non-persecuted region, got {region.martyrdom_boost}"
```

- [ ] **Step 2: Add filtering to compute_martyrdom_boosts**

Read `src/chronicler/religion.py:560` to understand the current function signature and what data is available. Add filters:
1. Region must have `persecution_intensity > 0`
2. Dead agent's belief must mismatch the region's majority faith

```python
# Inside compute_martyrdom_boosts, filter deaths:
# Only count deaths where:
#   - region has active persecution (persecution_intensity > 0)
#   - dead agent's belief != region majority belief
```

Adapt to the actual function signature and available data fields.

- [ ] **Step 3: Run test, verify it passes**

Run: `pytest tests/test_religion.py::test_martyrdom_ignores_non_persecuted_deaths -v`
Expected: PASS

- [ ] **Step 4: Also test majority-faith deaths don't count**

Add a test where the dead agent's belief matches the majority in a persecuted region — martyrdom should still not increase.

- [ ] **Step 5: Commit**

```
git add src/chronicler/religion.py tests/test_religion.py
git commit -m "fix(m-af1): filter martyrdom to minority-faith deaths in persecuted regions (#12)"
```

---

## Task 10: Rewilding threshold fix

**Spec item:** #13 — forest_cover > 0.7 impossible on plains (cap 0.40)
**Files:**
- Modify: `src/chronicler/ecology.py:169`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing test**

```python
def test_rewilding_counter_increments_on_plains(make_world):
    """M-AF1 #13: plains rewilding counter should increment when conditions are met."""
    world = make_world(2)
    region = world.regions[0]
    region.terrain = "plains"
    region.ecology.forest_cover = 0.38  # Below plains cap of 0.40, above threshold
    region.population = 2  # Below threshold of 5
    region.forest_regrowth_turns = 0

    from chronicler.ecology import _update_ecology_counters
    _update_ecology_counters(world)

    assert region.forest_regrowth_turns > 0, \
        f"Rewilding counter should have incremented, got {region.forest_regrowth_turns}"
```

- [ ] **Step 2: Lower the threshold**

In `src/chronicler/ecology.py:169`, change the regrowth condition:

```python
# BEFORE:
if region.ecology.forest_cover > 0.7 and region.population < 5:

# AFTER:
if region.ecology.forest_cover > 0.35 and region.population < 5:
```

The value 0.35 is below the plains cap of 0.40, making rewilding structurally possible for plains. Verify this value against the terrain cap table in `ecology.rs:86` — plains forest cap should be 0.40. The threshold should be below the cap to allow the counter to increment.

- [ ] **Step 3: Run test, verify it passes**

Run: `pytest tests/test_ecology.py::test_rewilding_counter_increments_on_plains -v`
Expected: PASS

- [ ] **Step 4: Commit**

```
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "fix(m-af1): lower rewilding threshold to make plains-to-forest possible (#13)"
```

---

## Task 11: Schism conversion wiring

**Spec item:** #10 — conversion fields never consumed in Rust
**Files:**
- Modify: `chronicler-agents/src/conversion_tick.rs`
- Test: `chronicler-agents/tests/` (new or existing conversion test)
- Test: `tests/test_religion.py` (Python integration)

- [ ] **Step 1: Read the current conversion_tick.rs**

Read `chronicler-agents/src/conversion_tick.rs` fully to understand the conversion phase. Identify where `schism_convert_from` and `schism_convert_to` should be consumed. Read `chronicler-agents/src/region.rs` to verify these fields exist on `RegionState`.

- [ ] **Step 2: Write Rust test**

In a new or existing Rust test file, add a test that:
- Sets `schism_convert_from = X` and `schism_convert_to = Y` on a region
- Populates agents with belief = X
- Runs conversion tick
- Asserts some agents now have belief = Y

- [ ] **Step 3: Implement schism conversion consumption**

In `conversion_tick.rs`, add a branch that:
- Checks if `region.schism_convert_from != 0xFF` (non-empty)
- For agents in that region with `belief == schism_convert_from`
- Applies a conversion probability (suggest using existing `BASE_CONVERSION_RATE` or a dedicated constant)
- Converts matching agents to `schism_convert_to`

Use the existing RNG stream pattern. Register a new stream offset if needed.

- [ ] **Step 4: Run Rust tests**

Run: `cargo nextest run --test test_conversion_tick` (or relevant test file)
Expected: PASS

- [ ] **Step 5: Write Python integration test**

In `tests/test_religion.py`, add a test that sets schism conversion fields on a region, runs a turn in hybrid mode, and verifies agent belief changes in the snapshot.

- [ ] **Step 6: Run Python test**

Run: `pytest tests/test_religion.py -q`
Expected: All pass

- [ ] **Step 7: Commit**

```
git add chronicler-agents/src/conversion_tick.rs chronicler-agents/tests/ tests/test_religion.py
git commit -m "fix(m-af1): consume schism conversion fields in Rust conversion tick (#10)"
```

---

## Task 12: Zero-agent aggregate writeback

**Spec item:** #7 — stale civ stats when zero agents
**Files:**
- Modify: `chronicler-agents/src/pool.rs` (`compute_aggregates`)
- Modify: `src/chronicler/agent_bridge.py` (`_write_back`)
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Read current aggregate code**

Read `chronicler-agents/src/pool.rs:659-682` to understand `compute_aggregates`. Read `src/chronicler/agent_bridge.py:2055-2087` to understand `_write_back`.

- [ ] **Step 2: Write failing test**

```python
def test_writeback_zeroes_stats_for_zero_agent_civ(make_world):
    """M-AF1 #7: civ with regions but zero agents should get zeroed guard stats."""
    # This test requires hybrid mode with a Rust bridge.
    # Set up a civ that controls a region but has zero live agents.
    # After write-back, military/economy/culture/stability should be zeroed,
    # not carry stale values from the previous turn.
    pytest.importorskip("chronicler_agents")
    # ... setup with bridge, verify stale stats are zeroed
```

The exact test structure depends on whether you can construct a bridge with zero agents for one civ. Read the bridge init code to determine the simplest setup.

- [ ] **Step 3: Fix in Rust or Python**

Per the spec, use **deterministic synthetic zero-row semantics**: emit a zero-valued aggregate row for any `civ_id` that still controls regions but has no alive agents.

**Fix in Rust** (`pool.rs:compute_aggregates`): After computing aggregate rows for civs with alive agents, check which civ IDs from the region batch have controlled regions. For any such civ_id absent from the computed rows, append a synthetic zero-row (population=0, military=0, economy=0, culture=0, stability=0). This ensures Python's `_write_back` always receives a row for every region-holding civ and deterministically zeroes their stats.

Do NOT use a Python-side fallback — the spec requires the zero-row to come from the aggregate batch itself so write-back semantics are consistent.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent_bridge.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/pool.rs src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "fix(m-af1): zero guard stats for civs with regions but no agents (#7)"
```

---

## Task 13: Promotions civ identity

**Spec item:** #8 — civ reconstructed from region controller
**Files:**
- Modify: `chronicler-agents/src/ffi.rs` (promotions batch schema)
- Modify: `src/chronicler/agent_bridge.py:1418-1436` (`_process_promotions`)
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Read current promotions FFI**

Read `chronicler-agents/src/ffi.rs:2410-2451` to understand the current promotions Arrow schema. Read `chronicler-agents/src/named_characters.rs:145` to verify `civ_id` is available on the promotion record. Read `src/chronicler/agent_bridge.py:1418-1436` to see how Python reconstructs civ identity.

- [ ] **Step 2: Add `civ_id` column to promotions batch in Rust**

In `ffi.rs`, add a `UInt8` column named `"civ_id"` to the promotions RecordBatch, populated from the agent's current `civ` field in the pool.

- [ ] **Step 3: Update Python to read authoritative civ_id**

In `agent_bridge.py:_process_promotions`, replace the region-controller lookup:

```python
# BEFORE:
origin_region = ...
civilization = next(c for c in world.civilizations if origin_region in ...)

# AFTER:
civ_id = batch.column("civ_id").to_pylist()[i]
civilization = world.civilizations[civ_id]
```

Keep `origin_civilization` using existing logic (best-effort, per spec).

- [ ] **Step 4: Write test**

Test that a promoted agent whose `civ_id` differs from their region's controller gets the correct civilization attribution.

- [ ] **Step 5: Rebuild Rust extension and run tests**

Run: `maturin develop --release` in `chronicler-agents/`
Run: `cargo nextest run -q && pytest tests/test_agent_bridge.py -q`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add chronicler-agents/src/ffi.rs src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "fix(m-af1): carry authoritative civ_id in promotions FFI batch (#8)"
```

---

## Task 14: `replace_social_edges` safety

**Spec item:** #17 — positional unwrap panic
**Files:**
- Modify: `chronicler-agents/src/ffi.rs:2636-2639`
- Test: `chronicler-agents/tests/test_social_edges.rs` or Python test

- [ ] **Step 1: Read current code**

Read `chronicler-agents/src/ffi.rs:2636-2639` to see the positional `.column(N).unwrap()` calls.

- [ ] **Step 2: Replace with column_by_name**

```rust
// BEFORE:
let agent_a = batch.column(0).as_any().downcast_ref::<UInt32Array>().unwrap();

// AFTER:
let agent_a = batch
    .column_by_name("agent_a")
    .ok_or_else(|| PyValueError::new_err("missing column 'agent_a' in social edges batch"))?
    .as_any()
    .downcast_ref::<UInt32Array>()
    .ok_or_else(|| PyValueError::new_err("column 'agent_a' is not UInt32"))?;
```

Apply the same pattern to columns 1-3 (`agent_b`, `relationship`, `formed_turn`).

- [ ] **Step 3: Run Rust tests**

Run: `cargo nextest run --test test_social_edges -q`
Expected: PASS

- [ ] **Step 4: Rebuild and run Python tests**

Run: `maturin develop --release`
Run: `pytest tests/test_relationships.py tests/test_m50a_relationships.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```
git add chronicler-agents/src/ffi.rs
git commit -m "fix(m-af1): replace_social_edges uses column_by_name instead of positional unwrap (#17)"
```

---

## Task 15: Guard-shock semantic verification

**Spec item:** #1 — verify positive guard-shock behavior
**Files:**
- Read: `src/chronicler/accumulator.py:126`, `chronicler-agents/src/satisfaction.rs:596`
- Test: `tests/test_accumulator.py` or `tests/test_simulation.py`

- [ ] **Step 1: Trace the full path**

1. Read `accumulator.py:126` — verify positive deltas are preserved as positive in `to_shock_signals()`
2. Read `satisfaction.rs` — find `compute_shock_penalty` and trace what happens with a positive `economy_shock` value. Does it reduce the penalty (boost) or increase it?
3. Read `satisfaction.rs:596` — the test that asserts positive shock behavior.

- [ ] **Step 2: Document finding**

If the chain correctly treats positive shock as a boost: write a comment in `simulation.py` at the discovery/renaissance/religious_movement guard-shock sites explaining the semantics, and add a test.

If the chain inverts the sign (positive shock = more penalty): reroute the positive deltas to `"guard"` instead of `"guard-shock"`.

- [ ] **Step 3: Write verification test**

```python
def test_positive_guard_shock_does_not_worsen_satisfaction():
    """M-AF1 #1: positive guard-shock should not worsen agent satisfaction."""
    # Construct a StatAccumulator, add a positive economy delta as guard-shock,
    # convert to shock signals, verify the economy_shock field is positive,
    # then verify in Rust (or document) that positive economy_shock reduces
    # the shock penalty (i.e., is a boost).
```

- [ ] **Step 4: Commit**

```
git add src/chronicler/simulation.py tests/test_accumulator.py
git commit -m "fix(m-af1): verify and document guard-shock semantics for positive events (#1)"
```

---

## Task 16: Vassalization wiring

**Spec item:** #15 — dead-wired vassalization path
**Files:**
- Modify: `src/chronicler/action_engine.py` (war resolution)
- Read: `src/chronicler/politics.py:420-472` (existing vassalization code)
- Test: `tests/test_politics.py`

- [ ] **Step 1: Read existing vassalization code**

Read `src/chronicler/politics.py:420` (`choose_vassalize_or_absorb`) and `politics.py:439` (`resolve_vassalization`) to understand the existing decision criteria and resolution logic.

- [ ] **Step 2: Write failing test**

```python
def test_decisive_war_can_vassalize(make_world):
    """M-AF1 #15: decisive war should sometimes produce vassals via existing chooser."""
    world = make_world(2)
    # Set up conditions that the existing chooser uses to prefer vassalization
    # (read choose_vassalize_or_absorb to find these conditions)
    # Use a deterministic seed/fixture that forces the vassalization branch
    ...
    # After war resolution, check for VassalRelation
    assert any(v.overlord == attacker.name for v in world.vassal_relations), \
        "Decisive war should have produced a vassal relation"
    # M-AF1: vassalization must NOT leave the pair in active_wars
    war_pairs = [(a, b) for a, b in world.active_wars]
    assert not any(
        (attacker.name in pair and defender.name in pair) for pair in war_pairs
    ), f"Vassalized pair should not be in active_wars, got {world.active_wars}"
```

- [ ] **Step 3: Wire into war resolution**

In `src/chronicler/action_engine.py`, in `resolve_war()`, after a decisive victory where the winner takes a region, add:

`WarResult` is a `NamedTuple` with two fields: `outcome: str` and `contested_region: str | None`. Region transfer (absorption) happens **inside** `resolve_war()` at `action_engine.py:515-527` — NOT in `_resolve_war_action()`. By the time `WarResult` is returned at line 600, the contested region has already been transferred. The vassalization check must therefore go **inside `resolve_war()`**, before the region transfer block.

Insert at `action_engine.py:515`, replacing the `if att_power > def_power * decisive_ratio:` block's region-transfer path:

```python
    if att_power > def_power * decisive_ratio:
        # M-AF1 #15: Check vassalization before absorption
        from chronicler.politics import choose_vassalize_or_absorb, resolve_vassalization
        if choose_vassalize_or_absorb(attacker, defender, world):
            # Vassalize: create VassalRelation, skip region transfer entirely
            vassal_events = resolve_vassalization(attacker, defender, world)
            world.events_timeline.extend(vassal_events)
            # Still apply military losses and stability drain (lines 591-599)
            mult = get_severity_multiplier(defender, world)
            if acc is not None:
                acc.add(att_idx, attacker, "military", -winner_mil_loss, "guard-action")
                acc.add(def_idx, defender, "military", -loser_mil_loss, "guard-action")
                acc.add(def_idx, defender, "stability", -int(war_stab_loss * mult), "signal")
            else:
                attacker.military = clamp(attacker.military - winner_mil_loss, STAT_FLOOR["military"], 100)
                defender.military = clamp(defender.military - loser_mil_loss, STAT_FLOOR["military"], 100)
                defender.stability = clamp(defender.stability - int(war_stab_loss * mult), STAT_FLOOR["stability"], 100)
            return WarResult("attacker_wins", contested.name if contested else None)
        # Otherwise: existing absorption path (lines 516-599) runs unchanged
        if contested:
            contested.controller = attacker.name
            # ... (existing region transfer, stockpile destruction, agent realignment, etc.)
```

**Critical caller interaction:** `_resolve_war_action()` at lines 301-305 unconditionally adds the attacker/defender pair to `active_wars` after `resolve_war()` returns. But `resolve_vassalization()` at `politics.py:443` clears the war from `active_wars`. If you only fix `resolve_war()`, the caller will re-add the war immediately after vassalization clears it, leaving `war_start_turns` out of sync.

Fix: in `_resolve_war_action()`, guard the `active_wars.append` so it does NOT fire when vassalization occurred. Since the vassalization branch still returns `WarResult("attacker_wins", ...)` (so battle-name and hostage logic at lines 307 and 339 still fire), use a `vassal_relations` membership check to distinguish:

```python
    # After resolve_war returns, only add to active_wars if not vassalized
    if result.outcome == "attacker_wins":
        # Check if resolve_vassalization already ran (it clears the war)
        pair = (civ.name, target_name)
        pair_rev = (target_name, civ.name)
        # Only add if vassalization didn't already handle the war state
        if not any(v.overlord == civ.name and v.vassal == target_name for v in world.vassal_relations):
            if pair not in world.active_wars and pair_rev not in world.active_wars:
                world.active_wars.append(pair)
    elif result.outcome == "stalemate":
        ...
```

The implementor must verify the exact `_resolve_war_action()` flow at lines 300-340 and ensure vassalization and war-tracking do not conflict. The regression test should assert that after vassalization, `active_wars` does NOT contain the attacker/defender pair.

- [ ] **Step 4: Run test**

Run: `pytest tests/test_politics.py::test_decisive_war_can_vassalize -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest tests/test_politics.py tests/test_action_engine.py -q`
Expected: All pass

- [ ] **Step 6: Commit**

```
git add src/chronicler/action_engine.py tests/test_politics.py
git commit -m "fix(m-af1): wire existing vassalize-vs-absorb into war resolution (#15)"
```

---

## Task 17: 200-Seed Regression Gate

**Spec verification gate**
**Files:**
- Run: `scripts/run_oracle_gate.py` or equivalent
- Create: `docs/superpowers/audits/m-af1-behavior-shift-note.md`

- [ ] **Step 1: Record pre-gate test counts**

Run: `pytest tests/ -q` — record exact pass/skip/fail counts.
Run: `cargo nextest run` — record exact pass/skip counts.

- [ ] **Step 2: Run 200-seed comparison**

Run the 200-seed regression comparison against baseline `d9baf0a`:

```bash
# Absolute paths to avoid stale-extension/env mismatch (per CLAUDE.md operational note)
MAIN_VENV="C:/Users/tateb/Documents/opusprogram/.venv/Scripts/python.exe"
MAIN_OUTPUT="C:/Users/tateb/Documents/opusprogram/output"

# Use a worktree for the baseline build — do NOT stash/checkout in the main tree.
git worktree add .worktrees/m-af1-baseline d9baf0a
cd .worktrees/m-af1-baseline/chronicler-agents
# Build Rust extension using the MAIN tree's interpreter
$MAIN_VENV -m pip install maturin && maturin develop --release --interpreter $MAIN_VENV
cd ..
# Run baseline batch — output to main tree so artifacts persist after worktree removal
$MAIN_VENV -m chronicler --batch --seeds 1-200 --turns 500 --agents hybrid --output $MAIN_OUTPUT/m-af1-baseline --parallel 24 --simulate-only
cd ../..
git worktree remove .worktrees/m-af1-baseline

# Run post-fix comparison from the main tree (rebuild extension with pinned interpreter)
cd chronicler-agents && maturin develop --release --interpreter $MAIN_VENV && cd ..
$MAIN_VENV -m chronicler --batch --seeds 1-200 --turns 500 --agents hybrid --output output/m-af1-post --parallel 24 --simulate-only
```

Then run the comparison:

```bash
.venv/Scripts/python.exe scripts/run_oracle_gate.py --baseline output/m-af1-baseline --current output/m-af1-post --profile full
```

- [ ] **Step 3: Adjudicate results**

Apply the gate criteria from the spec:
- **Hard gate:** No crashes, no new invariant violations, no pathological outcomes
- **Adjudicated:** Expected directional shifts (see spec) are acceptable

- [ ] **Step 4: Write behavior shift note**

Create `docs/superpowers/audits/m-af1-behavior-shift-note.md` documenting:
- Observed macro changes
- Which changes map to which fixes
- Any unexpected shifts requiring investigation
- Final test counts at signoff

- [ ] **Step 5: Commit gate artifacts**

```
git add docs/superpowers/audits/m-af1-behavior-shift-note.md
git commit -m "docs(m-af1): 200-seed regression gate passed with adjudicated behavior shifts"
```

- [ ] **Step 6: Update progress doc**

Add M-AF1 to `docs/superpowers/progress/phase-6-progress.md` as merged, with final test counts and a link to the behavior shift note.

```
git add docs/superpowers/progress/phase-6-progress.md
git commit -m "docs(m-af1): mark M-AF1 merged in progress doc"
```
