# Hostage Affinity Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync Rust agent civ affinity on hostage capture and release so the invariant "Rust affinity matches Python `gp.civilization` after any hostage lifecycle transition" holds.

**Architecture:** Finish the explicit `bridge=None` parameter pattern that `capture_hostage()` already started. Thread `bridge` through war callsites and Phase 2, add sync blocks in `release_hostage()` and the missing/extinct-origin path in `tick_hostages()`. All sync blocks gate on `bridge is not None and gp.agent_id is not None` for safe no-op in non-hybrid modes.

**Tech Stack:** Python only — uses existing `set_agent_civ()` FFI call, no Rust changes.

**Spec:** `docs/superpowers/specs/2026-04-03-hostage-affinity-sync-design.md`

---

### Task 1: Capture path — test and wire

**Files:**
- Modify: `tests/test_relationships.py:361` (insert before M40 section)
- Modify: `tests/test_action_engine.py:337` (add to `TestWarResolution` class)
- Modify: `src/chronicler/action_engine.py:407-427`

- [ ] **Step 1: Write the unit test for capture sync**

Insert after `test_origin_extinction_release_clears_hostage_state` (line 361), before the `# --- M40: Social Networks ---` comment:

```python
# --- Hostage affinity sync ---

class _MockSim:
    """Records set_agent_civ calls for bridge sync tests."""
    def __init__(self):
        self.calls = []
    def set_agent_civ(self, agent_id, civ_id):
        self.calls.append((agent_id, civ_id))

class _MockBridge:
    def __init__(self):
        self._sim = _MockSim()


def test_capture_hostage_syncs_rust_affinity(make_world):
    """capture_hostage() calls set_agent_civ when bridge is provided."""
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp = GreatPerson(
        name="Agent GP", role="general", trait="bold",
        civilization=loser.name, origin_civilization=loser.name,
        born_turn=5, agent_id=100,
    )
    loser.great_persons = [gp]
    bridge = _MockBridge()
    winner_idx = 1  # world.civilizations index for winner
    capture_hostage(loser, winner, world, contested_region="Battlefield", bridge=bridge)
    assert bridge._sim.calls == [(100, winner_idx)]
```

- [ ] **Step 2: Run unit test to validate mock pattern**

Run: `pytest tests/test_relationships.py::test_capture_hostage_syncs_rust_affinity -v`
Expected: PASS (the sync logic in `capture_hostage` already exists at lines 457-471 — calling directly with `bridge=` activates it). This validates the mock works but does NOT protect the war callsite seam.

- [ ] **Step 3: Wire bridge through war callsites in action_engine.py**

In `src/chronicler/action_engine.py`, at line 407 (the `# Hostage capture on decisive outcomes` comment), add a bridge lookup before the two capture calls. Replace lines 407-434:

```python
        # Hostage capture on decisive outcomes
        bridge = getattr(world, "_agent_bridge", None)
        if result.outcome == "defender_wins":
            # M24: Check for intelligence failure (uses post-combat military —
            # intentional: the revealed truth is what defender had after battle)
            perceived_mil = get_perceived_stat(civ, defender, "military", world)
            if perceived_mil is not None and perceived_mil <= 0.7 * defender.military:
                world.events_timeline.append(emit_intelligence_failure(
                    civ, defender, perceived_mil, defender.military, world,
                ))
            from chronicler.relationships import capture_hostage
            hostage = capture_hostage(civ, defender, world, contested_region=result.contested_region, bridge=bridge)
            if hostage:
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="hostage_taken",
                    actors=[defender.name, civ.name],
                    description=f"{defender.name} takes {hostage.name} hostage from {civ.name}.",
                    importance=6,
                ))
        elif result.outcome == "attacker_wins":
            from chronicler.relationships import capture_hostage
            hostage = capture_hostage(defender, civ, world, contested_region=result.contested_region, bridge=bridge)
            if hostage:
                world.events_timeline.append(Event(
                    turn=world.turn, event_type="hostage_taken",
                    actors=[civ.name, defender.name],
                    description=f"{civ.name} takes {hostage.name} hostage from {defender.name}.",
                    importance=6,
                ))
```

- [ ] **Step 4: Write the action_engine callsite regression test**

Add `GreatPerson` to the imports at the top of `tests/test_action_engine.py` (line 2):

```python
from chronicler.models import (
    ActionType, Belief, Civilization, Disposition, GreatPerson, InfrastructureType, Leader, PendingBuild, Region, Relationship, TechEra, WorldState,
)
```

Add this test inside the `TestWarResolution` class (after `test_hybrid_conquest_realigns_conquered_region_agents`):

```python
    @pytest.mark.parametrize("outcome,loser_idx,winner_idx", [
        ("attacker_wins", 1, 0),   # loser=defender(1), winner=attacker(0)
        ("defender_wins", 0, 1),   # loser=attacker(0), winner=defender(1)
    ])
    def test_war_capture_passes_bridge_to_capture_hostage(
        self, engine_world, monkeypatch, outcome, loser_idx, winner_idx,
    ):
        """_resolve_war_action passes world._agent_bridge on both war outcomes."""
        class _FakeSim:
            def __init__(self):
                self.calls = []
            def set_agent_civ(self, agent_id, civ_id):
                self.calls.append((agent_id, civ_id))

        class _FakeBridge:
            def __init__(self):
                self._sim = _FakeSim()

        # Give the loser a GP with agent_id so capture_hostage has a candidate
        loser = engine_world.civilizations[loser_idx]
        gp = GreatPerson(
            name="Capturable", role="general", trait="bold",
            civilization=loser.name, origin_civilization=loser.name,
            born_turn=5, agent_id=99,
        )
        loser.great_persons = [gp]

        monkeypatch.setattr("chronicler.action_engine.resolve_war",
            lambda attacker, defender, world, seed=0, acc=None: WarResult(outcome, "Region C"))
        monkeypatch.setattr("chronicler.action_engine.get_perceived_stat",
            lambda *args, **kwargs: 50)

        bridge = _FakeBridge()
        engine_world._agent_bridge = bridge

        _resolve_war_action(engine_world.civilizations[0], engine_world)

        # GP synced to the winner's civ index
        assert bridge._sim.calls == [(99, winner_idx)]
```

- [ ] **Step 5: Run callsite regressions to verify they pass**

Run: `pytest tests/test_action_engine.py::TestWarResolution::test_war_capture_passes_bridge_to_capture_hostage -v`
Expected: Both parametrized cases PASS. If either fails, step 3's wiring is broken.

- [ ] **Step 6: Run all hostage and war tests for regression**

Run: `pytest tests/test_relationships.py -v -k hostage && pytest tests/test_action_engine.py::TestWarResolution -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_relationships.py tests/test_action_engine.py src/chronicler/action_engine.py
git commit -m "feat: wire bridge through war callsites for hostage capture sync"
```

---

### Task 2: Normal release sync — test and implement

**Files:**
- Modify: `tests/test_relationships.py` (add test after Task 1's test)
- Modify: `src/chronicler/relationships.py:499-519`

- [ ] **Step 1: Write the failing test for release sync**

Insert after `test_capture_hostage_syncs_rust_affinity`:

```python
def test_release_hostage_syncs_rust_affinity(make_world):
    """release_hostage() calls set_agent_civ with origin civ index."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Agent Captive", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=11,
        captured_by=captor.name, pre_hostage_role="merchant",
        agent_id=200,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    origin_idx = 1  # world.civilizations index for origin
    release_hostage(hostage, captor, origin, world, bridge=bridge)
    assert bridge._sim.calls == [(200, origin_idx)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_relationships.py::test_release_hostage_syncs_rust_affinity -v`
Expected: FAIL — `release_hostage()` does not accept `bridge` parameter yet.

- [ ] **Step 3: Add bridge parameter and sync block to release_hostage**

In `src/chronicler/relationships.py`, replace the `release_hostage` function (lines 499-519):

```python
def release_hostage(
    gp: GreatPerson,
    captor: "Civilization",
    origin: "Civilization",
    world: WorldState,
    acc=None,
    bridge=None,
) -> None:
    """Release a hostage back to their origin civilization."""
    if gp in captor.great_persons:
        captor.great_persons.remove(gp)
    _clear_hostage_state(gp, origin)
    gp.civilization = origin.name
    gp.region = origin.capital_region or (origin.regions[0] if origin.regions else None)
    origin.great_persons.append(gp)
    # Sync Rust-side civ affinity (mirrors capture_hostage sync block)
    if bridge is not None and gp.agent_id is not None:
        origin_idx = next(
            (i for i, c in enumerate(world.civilizations) if c.name == origin.name),
            None,
        )
        if origin_idx is not None:
            try:
                bridge._sim.set_agent_civ(gp.agent_id, origin_idx)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to set GP civ during hostage release (agent_id=%s, civ_idx=%s)",
                    gp.agent_id, origin_idx,
                )
    if origin.treasury >= 10:
        if acc is not None:
            from chronicler.utils import civ_index
            origin_idx = civ_index(world, origin.name)
            acc.add(origin_idx, origin, "treasury", -10, "keep")
        else:
            origin.treasury -= 10
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_relationships.py::test_release_hostage_syncs_rust_affinity -v`
Expected: PASS

- [ ] **Step 5: Run all hostage tests for regression**

Run: `pytest tests/test_relationships.py -v -k hostage`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_relationships.py src/chronicler/relationships.py
git commit -m "feat: add bridge sync to release_hostage for Rust civ affinity"
```

---

### Task 3: Missing/extinct-origin sync — test and implement

**Files:**
- Modify: `tests/test_relationships.py` (add two tests)
- Modify: `src/chronicler/relationships.py:476-496`

- [ ] **Step 1: Write the failing test for extinct-origin sync**

Insert after `test_release_hostage_syncs_rust_affinity`:

```python
def test_extinct_origin_release_syncs_rust_affinity(make_world):
    """tick_hostages() syncs to captor when origin has no regions."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    origin.regions = []  # extinct
    hostage = GreatPerson(
        name="Stranded GP", role="hostage", trait="cautious",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=5,
        captured_by=captor.name, pre_hostage_role="scientist",
        agent_id=300,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    captor_idx = 0  # world.civilizations index for captor
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(300, captor_idx)]
```

- [ ] **Step 2: Write the failing test for missing-origin sync**

Insert after the extinct-origin test:

```python
def test_missing_origin_release_syncs_rust_affinity():
    """tick_hostages() syncs to captor when origin civ not found at all."""
    from chronicler.models import (
        Civilization, Leader, Region, TechEra, WorldState, Relationship,
    )
    captor = Civilization(
        name="Captor", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="Leader of Captor", trait="cautious", reign_start=0),
        regions=["R1"], asabiya=0.5,
    )
    hostage = GreatPerson(
        name="Orphan GP", role="hostage", trait="bold",
        civilization="Captor", origin_civilization="NonExistent",
        born_turn=0, is_hostage=True, hostage_turns=3,
        captured_by="Captor", pre_hostage_role="general",
        agent_id=400,
    )
    captor.great_persons = [hostage]
    r1 = Region(name="R1", terrain="plains", carrying_capacity=60,
                resources="fertile", controller="Captor")
    world = WorldState(
        name="TestWorld", seed=42, turn=10,
        regions=[r1], civilizations=[captor], relationships={},
    )
    bridge = _MockBridge()
    captor_idx = 0
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(400, captor_idx)]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_relationships.py::test_extinct_origin_release_syncs_rust_affinity tests/test_relationships.py::test_missing_origin_release_syncs_rust_affinity -v`
Expected: FAIL — `tick_hostages()` does not accept `bridge` parameter yet.

- [ ] **Step 4: Add bridge parameter and sync block to tick_hostages**

In `src/chronicler/relationships.py`, replace `tick_hostages` (lines 476-496):

```python
def tick_hostages(world: WorldState, acc=None, bridge=None) -> list[GreatPerson]:
    """Advance hostage turns, apply cultural conversion at 10, auto-release at 15."""
    released = []
    for civ in world.civilizations:
        for gp in list(civ.great_persons):
            if not gp.is_hostage:
                continue
            gp.hostage_turns += 1
            if gp.hostage_turns >= 10 and gp.cultural_identity != civ.name:
                gp.cultural_identity = civ.name
            # Free hostage if origin civ is missing or extinct — retire in place
            origin = next((c for c in world.civilizations if c.name == gp.origin_civilization), None)
            if origin is None or not origin.regions:
                _clear_hostage_state(gp, origin or civ)
                gp.civilization = civ.name
                # Sync Rust-side civ affinity to captor
                if bridge is not None and gp.agent_id is not None:
                    captor_idx = next(
                        (i for i, c in enumerate(world.civilizations) if c.name == civ.name),
                        None,
                    )
                    if captor_idx is not None:
                        try:
                            bridge._sim.set_agent_civ(gp.agent_id, captor_idx)
                        except Exception:
                            import logging
                            logging.getLogger(__name__).exception(
                                "Failed to set GP civ during missing/extinct-origin hostage release (agent_id=%s, civ_idx=%s)",
                                gp.agent_id, captor_idx,
                            )
                released.append(gp)
                continue
            if gp.hostage_turns >= 15:
                release_hostage(gp, civ, origin, world, acc=acc, bridge=bridge)
                released.append(gp)
    return released
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_relationships.py::test_extinct_origin_release_syncs_rust_affinity tests/test_relationships.py::test_missing_origin_release_syncs_rust_affinity -v`
Expected: PASS

- [ ] **Step 6: Write the normal-release integration test through tick_hostages**

This locks down the `tick_hostages → release_hostage` bridge forwarding for the normal auto-release path (hostage_turns >= 15). Without this, Task 2's direct `release_hostage()` test passes even if `tick_hostages` never forwards `bridge=bridge`.

Insert after `test_missing_origin_release_syncs_rust_affinity`:

```python
def test_tick_hostages_normal_release_forwards_bridge(make_world):
    """tick_hostages() forwards bridge to release_hostage on normal auto-release."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Auto Release GP", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=14,
        captured_by=captor.name, pre_hostage_role="general",
        agent_id=350,
    )
    captor.great_persons = [hostage]
    bridge = _MockBridge()
    origin_idx = 1  # world.civilizations index for origin
    tick_hostages(world, bridge=bridge)
    assert bridge._sim.calls == [(350, origin_idx)]
```

- [ ] **Step 7: Run integration test to verify it passes**

Run: `pytest tests/test_relationships.py::test_tick_hostages_normal_release_forwards_bridge -v`
Expected: PASS (Task 3's `tick_hostages` rewrite forwards `bridge=bridge` to `release_hostage`).

- [ ] **Step 8: Run all hostage tests for regression**

Run: `pytest tests/test_relationships.py -v -k hostage`
Expected: All PASS (existing tests call `tick_hostages(world)` without `bridge`, so default `bridge=None` keeps behavior unchanged).

- [ ] **Step 9: Commit**

```bash
git add tests/test_relationships.py src/chronicler/relationships.py
git commit -m "feat: add bridge sync for missing/extinct-origin hostage release"
```

---

### Task 4: No-op safety tests, Phase 2 wiring, and simulation regression

**Files:**
- Modify: `tests/test_relationships.py` (add no-op tests)
- Modify: `tests/test_simulation.py` (add Phase 2 bridge-passing regression)
- Modify: `src/chronicler/simulation.py:479-481`

- [ ] **Step 1: Write no-op tests**

Insert after the missing-origin test:

```python
def test_capture_hostage_noop_without_bridge(make_world):
    """capture_hostage() does not error when bridge is None."""
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    gp = GreatPerson(
        name="No Bridge GP", role="general", trait="bold",
        civilization=loser.name, origin_civilization=loser.name,
        born_turn=5, agent_id=500,
    )
    loser.great_persons = [gp]
    captured = capture_hostage(loser, winner, world, contested_region="Battlefield")
    assert captured is not None
    assert captured.is_hostage is True


def test_capture_hostage_noop_without_agent_id(make_world):
    """capture_hostage() skips sync for synthetic hostages (no agent_id)."""
    world = make_world(num_civs=2, seed=42)
    loser = world.civilizations[0]
    winner = world.civilizations[1]
    loser.great_persons = []  # forces synthetic hostage creation
    bridge = _MockBridge()
    captured = capture_hostage(loser, winner, world, contested_region="Plains", bridge=bridge)
    assert captured is not None
    assert bridge._sim.calls == []  # no sync for synthetic (agent_id is None)


def test_release_hostage_noop_without_bridge(make_world):
    """release_hostage() works without bridge (--agents=off path)."""
    world = make_world(num_civs=2, seed=42)
    captor = world.civilizations[0]
    origin = world.civilizations[1]
    hostage = GreatPerson(
        name="Offline GP", role="hostage", trait="bold",
        civilization=captor.name, origin_civilization=origin.name,
        born_turn=0, is_hostage=True, hostage_turns=11,
        captured_by=captor.name, pre_hostage_role="merchant",
        agent_id=600,
    )
    captor.great_persons = [hostage]
    release_hostage(hostage, captor, origin, world)
    assert hostage.civilization == origin.name
    assert hostage in origin.great_persons
```

- [ ] **Step 2: Run no-op tests to verify they pass**

Run: `pytest tests/test_relationships.py -v -k noop`
Expected: All 3 PASS (no-op paths don't touch bridge, existing logic is unchanged).

- [ ] **Step 3: Wire bridge through Phase 2 callsite in simulation.py**

In `src/chronicler/simulation.py`, replace lines 479-481:

```python
    # M17c: Hostage turn ticking
    from chronicler.relationships import tick_hostages
    bridge = getattr(world, "_agent_bridge", None)
    tick_hostages(world, acc=acc, bridge=bridge)
```

- [ ] **Step 4: Write the simulation-level regression test**

This locks down the Phase 2 `apply_automatic_effects → tick_hostages` bridge wiring. Without it, step 3 could be omitted and all other tests would still pass.

Add this test to `tests/test_simulation.py` (after the existing Phase 2 tests, near line 200):

```python
def test_phase2_passes_bridge_to_tick_hostages(sample_world, monkeypatch):
    """apply_automatic_effects passes world._agent_bridge to tick_hostages."""
    received_kwargs = []

    def recording_tick_hostages(world, acc=None, bridge=None):
        received_kwargs.append({"bridge": bridge})
        return []

    monkeypatch.setattr("chronicler.relationships.tick_hostages", recording_tick_hostages)

    class _Sentinel:
        """Marker object to verify identity, not just truthiness."""
        pass

    sentinel_bridge = _Sentinel()
    sample_world._agent_bridge = sentinel_bridge

    apply_automatic_effects(sample_world)

    assert len(received_kwargs) == 1
    assert received_kwargs[0]["bridge"] is sentinel_bridge
```

- [ ] **Step 5: Run simulation regression to verify it passes**

Run: `pytest tests/test_simulation.py::test_phase2_passes_bridge_to_tick_hostages -v`
Expected: PASS (step 3 wired the bridge).

- [ ] **Step 6: Run full test suite for regressions**

Run: `pytest tests/test_relationships.py tests/test_audit_batch_e.py tests/test_action_engine.py::TestWarResolution tests/test_simulation.py::test_phase2_passes_bridge_to_tick_hostages -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_relationships.py tests/test_simulation.py src/chronicler/simulation.py
git commit -m "feat: wire bridge through Phase 2 tick_hostages + add no-op and simulation regression tests"
```
