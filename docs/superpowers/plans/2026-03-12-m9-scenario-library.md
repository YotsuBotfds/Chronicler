# M9: Scenario Library Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add event flavor mapping, custom leader name pools, narrative style injection, and region controller assignment to the scenario system, then create three themed scenario YAMLs (Post-Collapse Minnesota, Sentient Vehicle World, Dead Miles).

**Architecture:** Extend four existing Pydantic models with optional fields, wire three leaf-level integration points (leader succession, narrative prompt construction, event display), convert `build_chronicle_prompt` from free function to `NarrativeEngine` method, then write three scenario YAML files validated by 20-turn smoke tests.

**Tech Stack:** Python 3.12, Pydantic, PyYAML, pytest

**Spec:** `docs/superpowers/specs/2026-03-12-m9-scenario-library-design.md`

---

## Chunk 1: Schema Extensions and Validation

### Task 1: Add EventFlavor model and ScenarioConfig fields

**Files:**
- Modify: `src/chronicler/scenario.py:8,26-30,33-47,56-69`
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Write failing tests for new schema fields**

Add to `tests/test_scenario.py` in class `TestScenarioModels`:

```python
def test_event_flavor_field(self):
    from chronicler.scenario import EventFlavor
    config = ScenarioConfig(
        name="Test",
        event_flavor={"drought": {"name": "Harsh Winter", "description": "Cold"}},
    )
    assert config.event_flavor["drought"].name == "Harsh Winter"

def test_event_flavor_none_by_default(self):
    config = ScenarioConfig(name="Test")
    assert config.event_flavor is None

def test_narrative_style_field(self):
    config = ScenarioConfig(name="Test", narrative_style="Terse and pragmatic.")
    assert config.narrative_style == "Terse and pragmatic."

def test_narrative_style_none_by_default(self):
    config = ScenarioConfig(name="Test")
    assert config.narrative_style is None

def test_leader_name_pool_on_civ_override(self):
    c = CivOverride(name="Test", leader_name_pool=["A", "B", "C", "D", "E"])
    assert c.leader_name_pool == ["A", "B", "C", "D", "E"]

def test_leader_name_pool_none_by_default(self):
    c = CivOverride(name="Test")
    assert c.leader_name_pool is None

def test_region_override_controller_field(self):
    r = RegionOverride(name="Test", controller="Civ A")
    assert r.controller == "Civ A"

def test_region_override_controller_none_by_default(self):
    r = RegionOverride(name="Test")
    assert r.controller is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scenario.py::TestScenarioModels -v`
Expected: FAIL — `EventFlavor` not importable, fields not defined

- [ ] **Step 3: Add EventFlavor model and new fields to scenario.py**

In `src/chronicler/scenario.py`, add after line 18:

```python
class EventFlavor(BaseModel):
    name: str
    description: str
```

Add to `RegionOverride` (after `resources` field):

```python
    controller: str | None = None
```

Add to `CivOverride` (after `leader` field):

```python
    leader_name_pool: list[str] | None = None
```

Add to `ScenarioConfig` (after `starting_conditions` field):

```python
    event_flavor: dict[str, EventFlavor] | None = None
    narrative_style: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scenario.py::TestScenarioModels -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_scenario.py
git commit -m "feat(m9): add EventFlavor model, leader_name_pool, narrative_style, controller fields"
```

### Task 2: Add leader_name_pool to Civilization model

**Files:**
- Modify: `src/chronicler/models.py:65-85`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_models.py`:

```python
def test_civilization_leader_name_pool_default_none():
    civ = Civilization(
        name="Test", population=5, military=5, economy=5, culture=5, stability=5,
        leader=Leader(name="Test Leader", trait="bold", reign_start=0),
    )
    assert civ.leader_name_pool is None

def test_civilization_leader_name_pool_set():
    civ = Civilization(
        name="Test", population=5, military=5, economy=5, culture=5, stability=5,
        leader=Leader(name="Test Leader", trait="bold", reign_start=0),
        leader_name_pool=["A", "B", "C"],
    )
    assert civ.leader_name_pool == ["A", "B", "C"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_civilization_leader_name_pool_default_none -v`
Expected: FAIL — `leader_name_pool` not a field

- [ ] **Step 3: Add field to Civilization model**

In `src/chronicler/models.py`, add after line 85 (`action_counts` field):

```python
    leader_name_pool: list[str] | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat(m9): add leader_name_pool field to Civilization model"
```

### Task 3: Validation rules for new fields

**Files:**
- Modify: `src/chronicler/scenario.py:72-145` (load_scenario function)
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Write failing tests for validation**

Add to `tests/test_scenario.py` in class `TestLoadScenario`:

```python
def test_load_invalid_event_flavor_key(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "event_flavor": {"tech_advancement": {"name": "X", "description": "Y"}},
    })
    with pytest.raises(ValueError, match="tech_advancement"):
        load_scenario(path)

def test_load_valid_event_flavor(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "event_flavor": {"drought": {"name": "Harsh Winter", "description": "Cold"}},
    })
    config = load_scenario(path)
    assert config.event_flavor["drought"].name == "Harsh Winter"

def test_load_leader_name_pool_too_few(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "civilizations": [{"name": "Civ A", "leader_name_pool": ["A", "B"]}],
    })
    with pytest.raises(ValueError, match="leader_name_pool"):
        load_scenario(path)

def test_load_leader_name_pool_empty_list(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "civilizations": [{"name": "Civ A", "leader_name_pool": []}],
    })
    with pytest.raises(ValueError, match="leader_name_pool"):
        load_scenario(path)

def test_load_leader_name_pool_valid(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "civilizations": [{"name": "Civ A", "leader_name_pool": ["A", "B", "C", "D", "E"]}],
    })
    config = load_scenario(path)
    assert config.civilizations[0].leader_name_pool == ["A", "B", "C", "D", "E"]

def test_load_cross_pool_duplicate_raises(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "civilizations": [
            {"name": "Civ A", "leader_name_pool": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]},
            {"name": "Civ B", "leader_name_pool": ["Alpha", "Zeta", "Eta", "Theta", "Iota"]},
        ],
    })
    with pytest.raises(ValueError, match="Alpha"):
        load_scenario(path)

def test_load_controller_invalid_civ_name(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "regions": [{"name": "R1", "controller": "Nonexistent Civ"}],
    })
    with pytest.raises(ValueError, match="controller"):
        load_scenario(path)

def test_load_controller_valid_civ_name(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "civilizations": [{"name": "Civ A"}],
        "regions": [{"name": "R1", "controller": "Civ A"}],
    })
    config = load_scenario(path)
    assert config.regions[0].controller == "Civ A"

def test_load_controller_none_accepted(self, tmp_path):
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "regions": [{"name": "R1"}],
    })
    config = load_scenario(path)
    assert config.regions[0].controller is None

def test_load_controller_none_string(self, tmp_path):
    """The literal string 'none' (quoted in YAML) means explicitly uncontrolled."""
    path = self._write_yaml(tmp_path, {
        "name": "Test",
        "regions": [{"name": "R1", "controller": "none"}],
    })
    config = load_scenario(path)
    assert config.regions[0].controller == "none"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scenario.py::TestLoadScenario::test_load_invalid_event_flavor_key tests/test_scenario.py::TestLoadScenario::test_load_leader_name_pool_too_few tests/test_scenario.py::TestLoadScenario::test_load_cross_pool_duplicate_raises tests/test_scenario.py::TestLoadScenario::test_load_controller_invalid_civ_name -v`
Expected: FAIL — validation not implemented

- [ ] **Step 3: Add validation to load_scenario**

In `src/chronicler/scenario.py`, add the following validation blocks to `load_scenario()` after the existing event_probability_overrides validation (after line 117):

```python
    # event_flavor keys must be valid event types
    if config.event_flavor:
        for key in config.event_flavor:
            if key not in VALID_EVENT_OVERRIDE_KEYS:
                raise ValueError(
                    f"Invalid event type '{key}' in event_flavor. "
                    f"Valid types: {sorted(VALID_EVENT_OVERRIDE_KEYS)}"
                )

    # leader_name_pool validation
    for civ in config.civilizations:
        if civ.leader_name_pool is not None:
            if len(civ.leader_name_pool) < 5:
                raise ValueError(
                    f"leader_name_pool for '{civ.name}' must have at least 5 names, "
                    f"got {len(civ.leader_name_pool)}"
                )

    # Cross-pool uniqueness
    all_pool_names: dict[str, str] = {}  # name -> civ that owns it
    for civ in config.civilizations:
        if civ.leader_name_pool:
            for name in civ.leader_name_pool:
                if name in all_pool_names:
                    raise ValueError(
                        f"Name '{name}' appears in leader_name_pool for both "
                        f"'{all_pool_names[name]}' and '{civ.name}'"
                    )
                all_pool_names[name] = civ.name

    # controller references must match defined civ names
    defined_civ_names = {c.name for c in config.civilizations}
    for region in config.regions:
        if region.controller is not None and region.controller != "none":
            if region.controller not in defined_civ_names:
                raise ValueError(
                    f"Region '{region.name}' controller '{region.controller}' "
                    f"not found in defined civilizations"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scenario.py::TestLoadScenario -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/scenario.py tests/test_scenario.py
git commit -m "feat(m9): add validation for event_flavor, leader_name_pool, controller"
```

### Task 4: apply_scenario wiring for leader_name_pool and controller

**Files:**
- Modify: `src/chronicler/scenario.py:148-265,267-336` (apply_scenario, _apply_civ_override)
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_scenario.py` in class `TestApplyScenario`:

```python
def test_leader_name_pool_copied_to_civ(self, generated_world):
    pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
    config = ScenarioConfig(
        name="Test",
        civilizations=[CivOverride(name="Pooled Civ", leader_name_pool=pool)],
    )
    apply_scenario(generated_world, config)
    assert generated_world.civilizations[0].leader_name_pool == pool

def test_leader_name_pool_none_when_not_set(self, generated_world):
    config = ScenarioConfig(
        name="Test",
        civilizations=[CivOverride(name="No Pool Civ")],
    )
    apply_scenario(generated_world, config)
    assert generated_world.civilizations[0].leader_name_pool is None

def test_controller_override_sets_region_controller(self, generated_world):
    civ_name = generated_world.civilizations[0].name
    # Inject a region with explicit controller
    config = ScenarioConfig(
        name="Test",
        civilizations=[CivOverride(name="Controller Civ")],
        regions=[RegionOverride(name="Controlled Region", controller="Controller Civ")],
    )
    apply_scenario(generated_world, config)
    region = next(r for r in generated_world.regions if r.name == "Controlled Region")
    assert region.controller == "Controller Civ"
    civ = next(c for c in generated_world.civilizations if c.name == "Controller Civ")
    assert "Controlled Region" in civ.regions

def test_controller_none_makes_region_uncontrolled(self, generated_world):
    # Find a civ that controls 2+ regions so removing one won't orphan it
    multi_region_civ = None
    for civ in generated_world.civilizations:
        if len(civ.regions) >= 2:
            multi_region_civ = civ
            break
    assert multi_region_civ is not None, "Need a civ with 2+ regions for this test"
    target_region_name = multi_region_civ.regions[0]
    config = ScenarioConfig(
        name="Test",
        regions=[RegionOverride(name="Neutral Zone", controller="none")],
    )
    # Override the first region (which belongs to multi_region_civ)
    apply_scenario(generated_world, config)
    region = next(r for r in generated_world.regions if r.name == "Neutral Zone")
    assert region.controller is None
    # The civ should still have its other region(s)
    assert len(multi_region_civ.regions) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scenario.py::TestApplyScenario::test_leader_name_pool_copied_to_civ tests/test_scenario.py::TestApplyScenario::test_controller_override_sets_region_controller -v`
Expected: FAIL

- [ ] **Step 3: Implement apply_scenario changes**

In `src/chronicler/scenario.py`, in `_apply_civ_override` function, add after the leader override block (after line 314):

```python
    # Leader name pool
    if override.leader_name_pool is not None:
        civ.leader_name_pool = override.leader_name_pool
```

In `apply_scenario`, add a new step after Step 1 (region injection), before Step 2 (civ injection). Insert after the region injection loop closes (after line 181). This handles controller overrides after all regions are injected:

```python
    # --- Step 1b: Region controller overrides ---
    for reg_override, target_idx in zip(config.regions, sorted(replaced_region_indices)):
        if reg_override.controller is not None:
            region = world.regions[target_idx]
            old_controller = region.controller

            # Remove this region from old controller's region list
            if old_controller:
                for civ in world.civilizations:
                    if civ.name == old_controller:
                        civ.regions = [r for r in civ.regions if r != region.name]

            if reg_override.controller == "none":
                region.controller = None
            else:
                region.controller = reg_override.controller
                # Add to new controller's region list (will be updated by civ rename if needed)
                for civ in world.civilizations:
                    if civ.name == reg_override.controller and region.name not in civ.regions:
                        civ.regions.append(region.name)
```

**Note:** The controller references use the civ names as they exist at the time of region injection. If civ injection renames a civ afterward, the existing `_apply_civ_override` rename logic (lines 321-335) will update `region.controller` to the new name. This means the controller field in the YAML should reference the **scenario civ names** (which are the names used in `CivOverride.name`), and the rename flow will handle the rest.

However, there's a subtlety: the controller override runs before civ injection. If the controller references a scenario civ name that doesn't exist yet (because the civ hasn't been injected/renamed), we need to defer controller assignment.

**Revised approach:** Instead of Step 1b, apply controller overrides **after** civ injection (after Step 2). Add after line 204:

```python
    # --- Step 2b: Region controller overrides ---
    for i, reg_override in enumerate(config.regions):
        if i >= len(world.regions):
            break
        target_idx = sorted(replaced_region_indices)[i] if i < len(replaced_region_indices) else None
        if target_idx is None:
            continue
        if reg_override.controller is not None:
            region = world.regions[target_idx]
            old_controller = region.controller

            # Remove region from old controller's list
            if old_controller:
                for civ in world.civilizations:
                    if civ.name == old_controller:
                        civ.regions = [r for r in civ.regions if r != region.name]

            if reg_override.controller == "none":
                region.controller = None
            else:
                region.controller = reg_override.controller
                for civ in world.civilizations:
                    if civ.name == reg_override.controller and region.name not in civ.regions:
                        civ.regions.append(region.name)
```

Actually, this is getting complex. Let me simplify. The cleanest approach: track the region overrides and their target indices during Step 1, then apply controller overrides in a new Step 2b after civ injection is complete. We need to store the mapping. Revise Step 1 to build a list of `(target_idx, reg_override)` pairs, then use that list in Step 2b.

**Simplified implementation:** Modify the region injection loop to store mappings, then add Step 2b:

Replace the region injection loop body to also store `region_override_map`:

At the start of `apply_scenario`, after `replaced_region_indices: set[int] = set()`, add:

```python
    region_override_map: list[tuple[int, RegionOverride]] = []
```

Inside the loop, after `replaced_region_indices.add(target_idx)`, add:

```python
        region_override_map.append((target_idx, reg_override))
```

After Step 2 (civ injection) closes, add:

```python
    # --- Step 2b: Region controller overrides ---
    for target_idx, reg_override in region_override_map:
        if reg_override.controller is None:
            continue
        region = world.regions[target_idx]
        old_controller = region.controller

        # Remove region from old controller's region list
        if old_controller:
            for civ in world.civilizations:
                if civ.name == old_controller:
                    civ.regions = [r for r in civ.regions if r != region.name]

        if reg_override.controller == "none":
            region.controller = None
        else:
            region.controller = reg_override.controller
            for civ in world.civilizations:
                if civ.name == reg_override.controller and region.name not in civ.regions:
                    civ.regions.append(region.name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scenario.py::TestApplyScenario -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS (post-apply validation for "every civ has regions" may need attention — the controller override could leave a civ with no regions if all its regions are reassigned. The test `test_controller_none_makes_region_uncontrolled` deliberately uncontrolls a region, which may orphan a civ. Adjust the test or add a region back to avoid triggering the post-apply check.)

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/scenario.py tests/test_scenario.py
git commit -m "feat(m9): wire leader_name_pool and controller into apply_scenario"
```

## Chunk 2: Integration Points

### Task 5: Custom leader name pool in _pick_name

**Files:**
- Modify: `src/chronicler/leaders.py:152-173`
- Test: `tests/test_leaders.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_leaders.py`:

```python
class TestCustomNamePool:
    def test_picks_from_custom_pool(self, leader_world):
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["CustomAlpha", "CustomBeta", "CustomGamma", "CustomDelta", "CustomEpsilon"]
        civ.leader.alive = False
        import random
        rng = random.Random(42)
        from chronicler.leaders import _pick_name
        name = _pick_name(civ, leader_world, rng)
        # Name should be "Title CustomX" format
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base in civ.leader_name_pool

    def test_custom_pool_uses_rng(self, leader_world):
        """Same seed produces same name — deterministic."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]
        import random
        name1 = _pick_name(civ, leader_world, random.Random(99))
        # Reset used names
        leader_world.used_leader_names = leader_world.used_leader_names[:-1]
        name2 = _pick_name(civ, leader_world, random.Random(99))
        assert name1 == name2

    def test_custom_pool_dedup_against_used_bases(self, leader_world):
        """A name already used (with title) should not be picked from custom pool."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["UsedName", "FreshName", "AnotherFresh", "MoreFresh", "YetMore"]
        leader_world.used_leader_names.append("Emperor UsedName")
        import random
        name = _pick_name(civ, leader_world, random.Random(42))
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base != "UsedName"

    def test_custom_pool_exhausted_falls_back(self, leader_world):
        """When custom pool is exhausted, falls back to cultural pool."""
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["OnlyName", "SecondName", "ThirdName", "FourthName", "FifthName"]
        # Mark all custom names as used
        for n in civ.leader_name_pool:
            leader_world.used_leader_names.append(f"Title {n}")
        import random
        name = _pick_name(civ, leader_world, random.Random(42))
        base = name.split(" ", 1)[-1] if " " in name else name
        assert base not in civ.leader_name_pool

    def test_custom_pool_adds_to_used_leader_names(self, leader_world):
        civ = leader_world.civilizations[0]
        civ.leader_name_pool = ["TrackMe", "Other", "Another", "More", "Extra"]
        import random
        count_before = len(leader_world.used_leader_names)
        _pick_name(civ, leader_world, random.Random(42))
        assert len(leader_world.used_leader_names) == count_before + 1
```

Add the import at the top of the new class:

```python
from chronicler.leaders import _pick_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_leaders.py::TestCustomNamePool -v`
Expected: FAIL — `_pick_name` doesn't check `leader_name_pool`

- [ ] **Step 3: Implement custom pool logic in _pick_name**

In `src/chronicler/leaders.py`, modify `_pick_name` (lines 152-173). Insert custom pool check after `used_bases` is built (after line 159), before the cultural pool lookup (line 160):

```python
    # Custom name pool (scenario-provided) takes priority
    if civ.leader_name_pool:
        custom_available = [n for n in civ.leader_name_pool if n not in used_bases]
        if custom_available:
            title = rng.choice(TITLES)
            base_name = rng.choice(custom_available)
            full_name = f"{title} {base_name}"
            world.used_leader_names.append(full_name)
            return full_name

    # Existing cultural pool logic (unchanged)
    available = [n for n in pool if n not in used_bases]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_leaders.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/leaders.py tests/test_leaders.py
git commit -m "feat(m9): custom leader name pool support in _pick_name"
```

### Task 6: Deterministic succession test

**Files:**
- Test: `tests/test_leaders.py`

- [ ] **Step 1: Write deterministic succession test**

Add to `tests/test_leaders.py` in class `TestCustomNamePool`:

```python
def test_deterministic_succession_with_custom_pool(self):
    """Two runs with same seed produce identical successor names."""
    from chronicler.leaders import generate_successor
    from chronicler.world_gen import generate_world

    def make_world():
        world = generate_world(seed=77, num_regions=4, num_civs=2)
        civ = world.civilizations[0]
        civ.leader_name_pool = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon",
                                "Zeta", "Eta", "Theta", "Iota", "Kappa"]
        world.event_probabilities["leader_death"] = 1.0
        return world

    # Run 1
    world1 = make_world()
    names1 = []
    for i in range(5):
        civ = world1.civilizations[0]
        new_leader = generate_successor(civ, world1, seed=77)
        names1.append(new_leader.name)
        civ.leader = new_leader
        world1.turn += 1

    # Run 2
    world2 = make_world()
    names2 = []
    for i in range(5):
        civ = world2.civilizations[0]
        new_leader = generate_successor(civ, world2, seed=77)
        names2.append(new_leader.name)
        civ.leader = new_leader
        world2.turn += 1

    assert names1 == names2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_leaders.py::TestCustomNamePool::test_deterministic_succession_with_custom_pool -v`
Expected: PASS (custom pool draws go through `rng`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_leaders.py
git commit -m "test(m9): deterministic succession test for custom name pools"
```

### Task 7: Convert build_chronicle_prompt to NarrativeEngine method, add event flavor and narrative style

**Files:**
- Modify: `src/chronicler/narrative.py:85-145,148-203`
- Modify: `src/chronicler/main.py:56`
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_narrative.py`:

```python
class TestEventFlavor:
    def test_event_flavor_substitutes_name(self, sample_world):
        from chronicler.scenario import EventFlavor
        sim_client = MagicMock()
        sim_client.complete.return_value = "DEVELOP"
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        flavor = {"drought": EventFlavor(name="Harsh Winter", description="Cold winds blow")}
        engine = NarrativeEngine(sim_client, narrative_client, event_flavor=flavor)
        events = [Event(turn=0, event_type="drought", actors=["Civ A"],
                       description="A drought struck.", importance=5)]
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "Harsh Winter" in call_args
        assert "Cold winds blow" in call_args

    def test_no_event_flavor_uses_original(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = [Event(turn=0, event_type="drought", actors=["Civ A"],
                       description="A drought struck.", importance=5)]
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "drought" in call_args.lower()


class TestNarrativeStyle:
    def test_narrative_style_in_prompt(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client,
                                narrative_style="Terse and pragmatic.")
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "NARRATIVE STYLE: Terse and pragmatic." in call_args

    def test_no_narrative_style_no_injection(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "NARRATIVE STYLE" not in call_args

    def test_neutral_historian_role(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "You are a historian chronicling" in call_args
        assert "mythic historian" not in call_args
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrative.py::TestEventFlavor tests/test_narrative.py::TestNarrativeStyle -v`
Expected: FAIL — `NarrativeEngine` doesn't accept `event_flavor`/`narrative_style` kwargs

- [ ] **Step 3: Implement changes to narrative.py**

**3a.** Update `NarrativeEngine.__init__` (line 156):

```python
def __init__(self, sim_client: LLMClient, narrative_client: LLMClient,
             event_flavor: dict | None = None,
             narrative_style: str | None = None):
    self.sim_client = sim_client
    self.narrative_client = narrative_client
    self.event_flavor = event_flavor
    self.narrative_style = narrative_style
```

**3b.** Replace the entire `build_chronicle_prompt` function body (lines 85-145) with a thin backward-compatible wrapper, and add `_build_chronicle_prompt_impl` as a new module-level function below it. Delete the old function body completely — the new impl function contains the updated logic with event flavor substitution, narrative style injection, and the neutral "historian" role line (replacing "mythic historian"):

```python
def build_chronicle_prompt(world: WorldState, events: list[Event]) -> str:
    """Backward-compatible wrapper — delegates to a no-flavor, no-style build."""
    return _build_chronicle_prompt_impl(world, events, event_flavor=None, narrative_style=None)


def _build_chronicle_prompt_impl(
    world: WorldState, events: list[Event],
    event_flavor: dict | None = None,
    narrative_style: str | None = None,
) -> str:
    """Build the prompt for LLM chronicle narration."""
    # Build civilization summaries
    civ_summaries = ""
    for civ in world.civilizations:
        civ_summaries += f"\n{civ.name} (domains: {', '.join(civ.domains)}):"
        civ_summaries += f" Pop {civ.population}, Mil {civ.military}, Econ {civ.economy},"
        civ_summaries += f" Culture {civ.culture}, Stability {civ.stability},"
        civ_summaries += f" Treasury {civ.treasury}, Asabiya {civ.asabiya}"
        civ_summaries += f"\n  Leader: {civ.leader.name} ({civ.leader.trait})"
        civ_summaries += f"\n  Regions: {', '.join(civ.regions)}"

    # Build event list with flavor substitution
    event_text = ""
    for e in events:
        display_type = e.event_type
        display_desc = e.description
        if event_flavor and e.event_type in event_flavor:
            display_type = event_flavor[e.event_type].name
            display_desc = event_flavor[e.event_type].description
        event_text += f"\n- [{display_type}] {display_desc} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)"

    # Named events context for historical callbacks
    named_context = ""
    if world.named_events:
        recent = world.named_events[-5:]
        named_context += "\n\nRecent historical landmarks:\n"
        for ne in recent:
            named_context += f"- {ne.name} (turn {ne.turn}): {ne.description}\n"

        best_named = max(world.named_events, key=lambda ne: ne.importance)
        if best_named not in recent:
            named_context += f"\nMost significant event in all history: {best_named.name} (turn {best_named.turn})\n"

        named_context += "\nReference these landmarks when relevant — weave callbacks to past events.\n"

    # Rivalry context
    rivalries = []
    for civ in world.civilizations:
        if civ.leader.rival_leader:
            rivalries.append(f"{civ.leader.name} of {civ.name} has a personal rivalry with {civ.leader.rival_leader} of {civ.leader.rival_civ}")
    rivalry_context = ""
    if rivalries:
        rivalry_context += "\n\nActive rivalries:\n"
        for r in rivalries:
            rivalry_context += f"- {r}\n"
        rivalry_context += "Weave these personal rivalries into the narrative when relevant.\n"

    # Role line and narrative style
    role_line = f"You are a historian chronicling the world of {world.name}."
    if narrative_style:
        role_line += f"\n\nNARRATIVE STYLE: {narrative_style}"

    return f"""{role_line}

TURN {world.turn}:

CIVILIZATIONS:{civ_summaries}

EVENTS THIS TURN:{event_text}{named_context}{rivalry_context}

Write a chronicle entry for this turn. Rules:
1. Write in the style of a history — evocative, literary, as if written by a scholar looking back on these events centuries later.
2. For each civilization mentioned, weave their cultural DOMAINS into the prose. A maritime culture's trade dispute involves harbors and currents; a mountain culture's crisis involves peaks and stone. This is critical for thematic coherence.
3. Focus on events with importance >= 5. Mention lower-importance events briefly or skip them.
4. Reference specific leader names, region names, and cultural values where relevant.
5. End with a sentence that hints at coming tension or change.
6. Do NOT include turn numbers or game mechanics in the prose.
7. Write 3-5 paragraphs.

Respond only with the chronicle prose. No preamble, no markdown formatting, no meta-commentary."""
```

**3c.** Update `generate_chronicle` method (line 188) to use the implementation:

```python
def generate_chronicle(self, world: WorldState, events: list[Event]) -> str:
    prompt = _build_chronicle_prompt_impl(world, events,
                                          event_flavor=self.event_flavor,
                                          narrative_style=self.narrative_style)
    try:
        return self.narrative_client.complete(prompt, max_tokens=1000)
    except Exception:
        summaries = "; ".join(e.description for e in events if e.description)
        return f"Turn {world.turn}: {summaries or 'Events unfolded.'}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrative.py -v`
Expected: All PASS (including existing tests via backward-compatible wrapper)

- [ ] **Step 5: Update main.py to pass event_flavor and narrative_style to NarrativeEngine**

In `src/chronicler/main.py`, modify line 56:

```python
    # Extract presentation-layer config for narrative engine
    event_flavor = scenario_config.event_flavor if scenario_config else None
    narrative_style = scenario_config.narrative_style if scenario_config else None
    engine = NarrativeEngine(
        sim_client=sim_client,
        narrative_client=narrative_client,
        event_flavor=event_flavor,
        narrative_style=narrative_style,
    )
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py src/chronicler/main.py tests/test_narrative.py
git commit -m "feat(m9): event flavor swap, narrative style injection, NarrativeEngine wiring"
```

## Chunk 3: Scenario YAML Files

### Task 8: Post-Collapse Minnesota scenario

**Files:**
- Create: `scenarios/post_collapse_minnesota.yaml`
- Test: `tests/test_scenario.py`

**IMPORTANT — Trait mapping:** The spec uses `trait: pragmatic` (Elder Johansson) and `trait: disciplined` (Colonel Voss), but neither exists in `ALL_TRAITS` in `leaders.py`. The valid traits are: ambitious, cautious, aggressive, calculating, zealous, opportunistic, stubborn, bold, shrewd, visionary. Invalid traits cause the action engine to fall through to default weights (all actions equally likely), defeating the personality system. Map in the YAML:
- `pragmatic` → `cautious` (same strategic behavior: risk-averse, stability-focused)
- `disciplined` → `calculating` (same strategic behavior: methodical, controlled)

- [ ] **Step 1: Write the scenario YAML**

Create `scenarios/post_collapse_minnesota.yaml` with the full content from the spec (Section: Scenario 1). All regions, civs, relationships, event_flavor, starting_conditions, and narrative_style as specified. **Use `cautious` instead of `pragmatic` for Elder Johansson and `calculating` instead of `disciplined` for Colonel Voss.**

- [ ] **Step 2: Write the smoke test**

Add to `tests/test_scenario.py` in class `TestTemplates`:

```python
def test_minnesota_loads(self):
    config = load_scenario(TEMPLATE_DIR / "post_collapse_minnesota.yaml")
    assert config.name == "Post-Collapse Minnesota"
    assert len(config.civilizations) == 6
    assert len(config.regions) == 10
    assert config.event_flavor is not None
    assert config.event_flavor["drought"].name == "Harsh Winter"
    assert config.narrative_style is not None
    assert config.civilizations[0].leader_name_pool is not None
    assert len(config.civilizations[0].leader_name_pool) >= 5

def test_minnesota_runs_20_turns(self):
    config = load_scenario(TEMPLATE_DIR / "post_collapse_minnesota.yaml")
    from chronicler.scenario import resolve_scenario_params
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                           num_civs=params["num_civs"])
    apply_scenario(world, config)
    # Verify key state
    civ_names = {c.name for c in world.civilizations}
    assert "Farmer Co-ops" in civ_names
    assert "Carleton Enclave" in civ_names
    carleton = next(c for c in world.civilizations if c.name == "Carleton Enclave")
    assert carleton.tech_era == TechEra.CLASSICAL
    # Run 20 turns
    for i in range(20):
        engine = ActionEngine(world)
        run_turn(
            world,
            action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
            narrator=lambda w, e: "Turn narrative.",
            seed=params["seed"] + i,
        )
    assert world.turn == 20
```

Add the `SimpleNamespace` import at the top of the file (it's already there from `TestResolveScenarioParams`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_scenario.py::TestTemplates::test_minnesota_loads -v`
Expected: FAIL — file not found

- [ ] **Step 4: Create the YAML file**

Write `scenarios/post_collapse_minnesota.yaml` per the spec. The full YAML file contents should match all fields in the design spec Section "Scenario 1: Post-Collapse Minnesota" — all 10 regions, 6 civs with full stats/pools, relationships, event_flavor, starting_conditions, and narrative_style.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scenario.py::TestTemplates::test_minnesota_loads tests/test_scenario.py::TestTemplates::test_minnesota_runs_20_turns -v`
Expected: PASS

- [ ] **Step 6: Run determinism check**

Add a determinism test:

```python
def test_minnesota_deterministic(self):
    config = load_scenario(TEMPLATE_DIR / "post_collapse_minnesota.yaml")
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)

    def run_5_turns():
        world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                               num_civs=params["num_civs"])
        apply_scenario(world, config)
        for i in range(5):
            engine = ActionEngine(world)
            run_turn(world,
                     action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                     narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
        return world

    w1 = run_5_turns()
    w2 = run_5_turns()
    assert w1.model_dump() == w2.model_dump()
```

Run: `pytest tests/test_scenario.py::TestTemplates::test_minnesota_deterministic -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scenarios/post_collapse_minnesota.yaml tests/test_scenario.py
git commit -m "feat(m9): add Post-Collapse Minnesota scenario"
```

### Task 9: Sentient Vehicle World scenario

**Files:**
- Create: `scenarios/sentient_vehicle_world.yaml`
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Write the scenario YAML**

Create `scenarios/sentient_vehicle_world.yaml` per the spec Section "Scenario 2: Sentient Vehicle World". All 10 regions, 5 civs with 20-name pools, relationships, event_flavor, and narrative_style.

- [ ] **Step 2: Write smoke tests**

Add to `tests/test_scenario.py` in class `TestTemplates`:

```python
def test_vehicle_world_loads(self):
    config = load_scenario(TEMPLATE_DIR / "sentient_vehicle_world.yaml")
    assert config.name == "Sentient Vehicle World"
    assert len(config.civilizations) == 5
    assert len(config.regions) == 10
    assert config.event_flavor["drought"].name == "Fuel Shortage"
    assert config.event_flavor["leader_death"].name == "Final Breakdown"
    # All pools should have 20 names
    for civ in config.civilizations:
        assert len(civ.leader_name_pool) == 20

def test_vehicle_world_runs_20_turns(self):
    config = load_scenario(TEMPLATE_DIR / "sentient_vehicle_world.yaml")
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                           num_civs=params["num_civs"])
    apply_scenario(world, config)
    assert world.relationships["Geargrinders"]["Rustborn"].disposition == Disposition.HOSTILE
    assert world.relationships["Chrome Council"]["Electrics"].disposition == Disposition.FRIENDLY
    for i in range(20):
        engine = ActionEngine(world)
        run_turn(world,
                 action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                 narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
    assert world.turn == 20

def test_vehicle_world_deterministic(self):
    config = load_scenario(TEMPLATE_DIR / "sentient_vehicle_world.yaml")
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    def run_5():
        world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                               num_civs=params["num_civs"])
        apply_scenario(world, config)
        for i in range(5):
            engine = ActionEngine(world)
            run_turn(world,
                     action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                     narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
        return world
    assert run_5().model_dump() == run_5().model_dump()
```

- [ ] **Step 3: Create the YAML and run tests**

Run: `pytest tests/test_scenario.py::TestTemplates::test_vehicle_world_loads tests/test_scenario.py::TestTemplates::test_vehicle_world_runs_20_turns tests/test_scenario.py::TestTemplates::test_vehicle_world_deterministic -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scenarios/sentient_vehicle_world.yaml tests/test_scenario.py
git commit -m "feat(m9): add Sentient Vehicle World scenario"
```

### Task 10: Dead Miles scenario

**Files:**
- Create: `scenarios/dead_miles.yaml`
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Write the scenario YAML**

Create `scenarios/dead_miles.yaml` per the spec Section "Scenario 3: Dead Miles / Port Junction". All 10 regions with explicit controller assignments, 5 civs, 6 relationship pairs, event_flavor, and narrative_style.

**IMPORTANT:** For uncontrolled regions (The Gulch, The Interchange), use quoted `controller: "none"` in the YAML. Unquoted `none` is parsed by `yaml.safe_load` as Python `None`, which would be treated as "controller not specified" (inheriting the default) rather than "explicitly uncontrolled." The quoted string `"none"` is handled by `apply_scenario` to set `region.controller = None`.

- [ ] **Step 2: Write smoke tests**

Add to `tests/test_scenario.py` in class `TestTemplates`:

```python
def test_dead_miles_loads(self):
    config = load_scenario(TEMPLATE_DIR / "dead_miles.yaml")
    assert config.name == "Dead Miles"
    assert len(config.civilizations) == 5
    assert len(config.regions) == 10
    assert config.event_flavor["rebellion"].name == "Dock Strike"
    # Check controller assignments
    gasoline = next(r for r in config.regions if r.name == "Gasoline Alley")
    assert gasoline.controller == "Geargrinders"
    gulch = next(r for r in config.regions if r.name == "The Gulch")
    assert gulch.controller == "none"

def test_dead_miles_runs_20_turns(self):
    config = load_scenario(TEMPLATE_DIR / "dead_miles.yaml")
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                           num_civs=params["num_civs"])
    apply_scenario(world, config)
    # Verify controller assignments
    gasoline = next(r for r in world.regions if r.name == "Gasoline Alley")
    assert gasoline.controller == "Geargrinders"
    gulch = next(r for r in world.regions if r.name == "The Gulch")
    assert gulch.controller is None
    # Verify relationships
    assert world.relationships["Geargrinders"]["Rustborn"].disposition == Disposition.HOSTILE
    assert world.relationships["Haulers Union"]["Chrome Council"].disposition == Disposition.FRIENDLY
    # All civs start at iron era
    for civ in world.civilizations:
        assert civ.tech_era == TechEra.IRON
    for i in range(20):
        engine = ActionEngine(world)
        run_turn(world,
                 action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                 narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
    assert world.turn == 20

def test_dead_miles_deterministic(self):
    config = load_scenario(TEMPLATE_DIR / "dead_miles.yaml")
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    def run_5():
        world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                               num_civs=params["num_civs"])
        apply_scenario(world, config)
        for i in range(5):
            engine = ActionEngine(world)
            run_turn(world,
                     action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                     narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
        return world
    assert run_5().model_dump() == run_5().model_dump()

def test_dead_miles_naming_consistency_with_vehicle_world(self):
    """Both scenarios share the same five faction names."""
    dm = load_scenario(TEMPLATE_DIR / "dead_miles.yaml")
    vw = load_scenario(TEMPLATE_DIR / "sentient_vehicle_world.yaml")
    dm_names = {c.name for c in dm.civilizations}
    vw_names = {c.name for c in vw.civilizations}
    assert dm_names == vw_names
```

- [ ] **Step 3: Create the YAML and run tests**

Run: `pytest tests/test_scenario.py::TestTemplates::test_dead_miles_loads tests/test_scenario.py::TestTemplates::test_dead_miles_runs_20_turns tests/test_scenario.py::TestTemplates::test_dead_miles_deterministic tests/test_scenario.py::TestTemplates::test_dead_miles_naming_consistency_with_vehicle_world -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add scenarios/dead_miles.yaml tests/test_scenario.py
git commit -m "feat(m9): add Dead Miles scenario"
```

### Task 11: Final integration test and full suite

**Files:**
- Test: `tests/test_scenario.py`

- [ ] **Step 1: Add run_chronicle integration test with scenario**

Add to `tests/test_scenario.py` in class `TestIntegration`:

```python
def test_minnesota_20_turns_with_conditions(self):
    """Minnesota scenario runs 20 turns with grid-down condition active throughout."""
    config = load_scenario(TEMPLATE_DIR / "post_collapse_minnesota.yaml")
    from chronicler.scenario import resolve_scenario_params
    args = SimpleNamespace(seed=None, turns=None, civs=None, regions=None,
                           reflection_interval=None, resume=None)
    params = resolve_scenario_params(config, args)
    world = generate_world(seed=params["seed"], num_regions=params["num_regions"],
                           num_civs=params["num_civs"])
    apply_scenario(world, config)
    # Grid-down should be active
    grid_down = [c for c in world.active_conditions if c.condition_type == "grid-down"]
    assert len(grid_down) == 1
    assert grid_down[0].severity == 4
    # Run 20 turns
    for i in range(20):
        engine = ActionEngine(world)
        run_turn(world,
                 action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
                 narrator=lambda w, e: "Turn narrative.", seed=params["seed"] + i)
    assert world.turn == 20
    # All civs should still exist (severity 4 shouldn't kill anyone in 20 turns)
    assert len(world.civilizations) >= 5
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario.py
git commit -m "test(m9): final integration tests for scenario library"
```

- [ ] **Step 4: Run full suite one final time and verify test count**

Run: `pytest tests/ -v --tb=short`
Expected: All PASS. Test count should be 262 (pre-M9) + ~30 new tests = ~292.
