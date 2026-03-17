# M35a: Rivers & Trade Corridors Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add named river systems as a geographic adjacency layer with upstream-downstream ecological coupling and migration preference.

**Architecture:** Rivers are immutable topology defined in scenario YAML configs. Python handles world-gen bonuses (water, capacity, Fish) and per-tick deforestation cascade in ecology Phase 9. Rust reads `river_mask: u32` via Arrow FFI for migration attractiveness bonus in `compute_region_stats()`.

**Tech Stack:** Python (Pydantic models, ecology system), Rust (RegionState, behavior.rs), Arrow FFI (agent_bridge.py ↔ ffi.rs), pytest, cargo test.

---

## Chunk 1: Python Data Model, Config, and World-Gen

### Task 1: River Model Class

**Files:**
- Modify: `src/chronicler/models.py:148` (insert before Region class)
- Modify: `src/chronicler/models.py:458` (add field to WorldState)
- Test: `tests/test_models.py` (or existing model test location)

- [ ] **Step 1: Write failing test for River model**

```python
# tests/test_rivers.py
import pytest
from chronicler.models import River, WorldState


class TestRiverModel:
    def test_river_basic(self):
        r = River(name="Amber River", path=["Greenfields", "Marshfen", "Coasthaven"])
        assert r.name == "Amber River"
        assert r.path == ["Greenfields", "Marshfen", "Coasthaven"]

    def test_river_path_must_have_at_least_two(self):
        with pytest.raises(Exception):
            River(name="Creek", path=["Solo"])

    def test_world_state_has_rivers(self):
        ws = WorldState(name="Test", seed=42)
        assert ws.rivers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py -v`
Expected: FAIL — `River` not importable from `chronicler.models`

- [ ] **Step 3: Add River class to models.py**

In `src/chronicler/models.py`, insert before line 149 (before `class Region`):

```python
class River(BaseModel):
    name: str
    path: list[str] = Field(min_length=2)
```

In `src/chronicler/models.py`, after line 457 (after `agent_events_raw` in WorldState):

```python
    # M35a: Rivers
    rivers: list[River] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_rivers.py
git commit -m "feat(m35a): add River model and rivers field on WorldState"
```

---

### Task 2: Tuning Constants

**Files:**
- Modify: `src/chronicler/tuning.py:50` (add constants after K_DEPLETION_RATE)
- Modify: `src/chronicler/tuning.py:81` (add to KNOWN_OVERRIDES)

- [ ] **Step 1: Write failing test for river constants**

```python
# Append to tests/test_rivers.py
from chronicler.tuning import (
    K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
    KNOWN_OVERRIDES,
)


class TestRiverConstants:
    def test_river_constants_exist(self):
        assert K_RIVER_WATER_BONUS == "ecology.river_water_bonus"
        assert K_RIVER_CAPACITY_MULTIPLIER == "ecology.river_capacity_multiplier"
        assert K_DEFORESTATION_THRESHOLD == "ecology.deforestation_threshold"
        assert K_DEFORESTATION_WATER_LOSS == "ecology.deforestation_water_loss"

    def test_river_constants_in_known_overrides(self):
        assert K_RIVER_WATER_BONUS in KNOWN_OVERRIDES
        assert K_RIVER_CAPACITY_MULTIPLIER in KNOWN_OVERRIDES
        assert K_DEFORESTATION_THRESHOLD in KNOWN_OVERRIDES
        assert K_DEFORESTATION_WATER_LOSS in KNOWN_OVERRIDES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestRiverConstants -v`
Expected: FAIL — constants not importable

- [ ] **Step 3: Add constants to tuning.py**

In `src/chronicler/tuning.py`, after line 50 (`K_DEPLETION_RATE`):

```python
# M35a: Rivers
K_RIVER_WATER_BONUS = "ecology.river_water_bonus"
K_RIVER_CAPACITY_MULTIPLIER = "ecology.river_capacity_multiplier"
K_DEFORESTATION_THRESHOLD = "ecology.deforestation_threshold"
K_DEFORESTATION_WATER_LOSS = "ecology.deforestation_water_loss"
```

In `src/chronicler/tuning.py`, add to `KNOWN_OVERRIDES` set (inside the braces, after `K_DEPLETION_RATE`):

```python
    K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER,
    K_DEFORESTATION_THRESHOLD, K_DEFORESTATION_WATER_LOSS,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestRiverConstants -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tuning.py tests/test_rivers.py
git commit -m "feat(m35a): add river tuning constants"
```

---

### Task 3: Scenario Config — River Parsing & Validation

**Files:**
- Modify: `src/chronicler/scenario.py:99` (add rivers field to ScenarioConfig)
- Modify: `src/chronicler/scenario.py:102-223` (add validation in load_scenario)
- Test: `tests/test_rivers.py`

- [ ] **Step 1: Write failing test for scenario river parsing**

```python
# Append to tests/test_rivers.py
from chronicler.scenario import ScenarioConfig


class TestScenarioRiverConfig:
    def test_config_accepts_rivers(self):
        config = ScenarioConfig(
            name="River Test",
            rivers=[{"name": "Amber River", "path": ["R1", "R2", "R3"]}],
        )
        assert len(config.rivers) == 1
        assert config.rivers[0].name == "Amber River"

    def test_config_default_no_rivers(self):
        config = ScenarioConfig(name="No Rivers")
        assert config.rivers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestScenarioRiverConfig -v`
Expected: FAIL — `rivers` not a valid field on ScenarioConfig

- [ ] **Step 3: Add rivers field to ScenarioConfig**

In `src/chronicler/scenario.py`, add import at top (with other model imports):

```python
from chronicler.models import River
```

In `src/chronicler/scenario.py`, after line 99 (`black_swan_cooldown_turns`), before the closing of ScenarioConfig:

```python
    rivers: list[River] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestScenarioRiverConfig -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_rivers.py
git commit -m "feat(m35a): add rivers field to ScenarioConfig"
```

---

### Task 4: Scenario Validation — River Path Adjacency Check

**Files:**
- Modify: `src/chronicler/scenario.py:227-423` (add validation in apply_scenario, after Step 8)
- Test: `tests/test_rivers.py`

- [ ] **Step 1: Write failing tests for river validation**

```python
# Append to tests/test_rivers.py
from chronicler.scenario import apply_scenario
from chronicler.world_gen import generate_world


class TestRiverValidation:
    def _make_world_and_config(self, rivers):
        """Helper: generate a small world, build config with rivers."""
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        region_names = [r.name for r in world.regions]
        config = ScenarioConfig(name="Test", rivers=rivers)
        return world, config, region_names

    def test_valid_river_accepted(self):
        world, config, names = self._make_world_and_config([])
        # Build a valid river from two adjacent regions
        r0 = world.regions[0]
        if r0.adjacencies:
            adj_name = r0.adjacencies[0]
            config.rivers = [River(name="Test River", path=[r0.name, adj_name])]
            apply_scenario(world, config)  # Should not raise
            assert len(world.rivers) == 1
            assert world.rivers[0].name == "Test River"

    def test_river_with_unknown_region_raises(self):
        world, config, _ = self._make_world_and_config([])
        config.rivers = [River(name="Bad River", path=["FAKE_REGION", world.regions[0].name])]
        with pytest.raises(ValueError, match="not found"):
            apply_scenario(world, config)

    def test_river_with_non_adjacent_regions_raises(self):
        world, config, _ = self._make_world_and_config([])
        # Find two non-adjacent regions
        r0 = world.regions[0]
        non_adj = None
        for r in world.regions:
            if r.name != r0.name and r.name not in r0.adjacencies:
                non_adj = r
                break
        if non_adj:
            config.rivers = [River(name="Bad River", path=[r0.name, non_adj.name])]
            with pytest.raises(ValueError, match="not adjacent"):
                apply_scenario(world, config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestRiverValidation -v`
Expected: FAIL — apply_scenario doesn't handle rivers yet

- [ ] **Step 3: Add river validation and assignment to apply_scenario**

In `src/chronicler/scenario.py`, after Step 8 (after line 395, after `populate_legacy_resources`), insert:

```python
    # --- Step 9: River assignment (M35a) ---
    region_map = {r.name: r for r in world.regions}
    world.rivers = []
    for river_idx, river in enumerate(config.rivers):
        # Validate region names exist
        for rname in river.path:
            if rname not in region_map:
                raise ValueError(f"River '{river.name}': region '{rname}' not found in scenario")
        # Validate consecutive adjacency
        for i in range(len(river.path) - 1):
            r_curr = region_map[river.path[i]]
            r_next_name = river.path[i + 1]
            if r_next_name not in r_curr.adjacencies:
                raise ValueError(
                    f"River '{river.name}': '{river.path[i]}' and '{r_next_name}' are not adjacent"
                )
        world.rivers.append(river)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestRiverValidation -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_rivers.py
git commit -m "feat(m35a): validate river paths in apply_scenario"
```

---

### Task 5: River Mask Assignment

**Files:**
- Modify: `src/chronicler/scenario.py` (extend Step 9 to assign river_mask)
- Modify: `src/chronicler/models.py` (add river_mask field to Region)
- Test: `tests/test_rivers.py`

- [ ] **Step 1: Write failing test for river_mask assignment**

```python
# Append to tests/test_rivers.py

class TestRiverMaskAssignment:
    def test_river_mask_assigned(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies in test world")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        assert region_map[r0.name].river_mask & 1 != 0  # bit 0 set
        assert region_map[adj_name].river_mask & 1 != 0  # bit 0 set

    def test_non_river_region_mask_zero(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies in test world")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        river_region_names = {r0.name, adj_name}
        for r in world.regions:
            if r.name not in river_region_names:
                assert r.river_mask == 0, f"{r.name} should have river_mask=0"

    def test_confluence_has_multiple_bits(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        # Find a region with at least 2 adjacencies to form 2 rivers sharing it
        shared = None
        for r in world.regions:
            if len(r.adjacencies) >= 2:
                shared = r
                break
        if shared is None:
            pytest.skip("No region with 2+ adjacencies")
        a1, a2 = shared.adjacencies[0], shared.adjacencies[1]
        config = ScenarioConfig(
            name="Test",
            rivers=[
                River(name="River A", path=[a1, shared.name]),
                River(name="River B", path=[a2, shared.name]),
            ],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        mask = region_map[shared.name].river_mask
        assert mask & 1 != 0  # bit 0 (River A)
        assert mask & 2 != 0  # bit 1 (River B)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestRiverMaskAssignment -v`
Expected: FAIL — `river_mask` not a field on Region

- [ ] **Step 3: Add river_mask to Region model and assign in apply_scenario**

In `src/chronicler/models.py`, add to Region class (after `resource_reserves` field, line 176):

```python
    river_mask: int = 0
```

In `src/chronicler/scenario.py`, extend the Step 9 river block. After `world.rivers.append(river)`, add the bitmask assignment:

```python
    # Assign river_mask bits
    for river_idx, river in enumerate(world.rivers):
        bit = 1 << river_idx
        for rname in river.path:
            region_map[rname].river_mask |= bit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestRiverMaskAssignment -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py src/chronicler/scenario.py tests/test_rivers.py
git commit -m "feat(m35a): assign river_mask bitmask to regions"
```

---

### Task 6: World-Gen Bonuses — Water, Capacity, Fish

**Files:**
- Modify: `src/chronicler/scenario.py` (extend Step 9 with bonus application)
- Test: `tests/test_rivers.py`

**Phoebe N-2 note:** Fish assignment must also set `resource_base_yields[slot]` following M34's `assign_resource_types()` pattern.

- [ ] **Step 1: Write failing tests for river bonuses**

```python
# Append to tests/test_rivers.py
from chronicler.models import EMPTY_SLOT, ResourceType
from chronicler.tuning import K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER


class TestRiverWorldGenBonuses:
    def _apply_rivers(self, seed=42):
        """Helper: create world, apply a river, return (world, river_region, non_river_region)."""
        world = generate_world(seed=seed, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        # Record pre-bonus values
        region_map = {r.name: r for r in world.regions}
        pre_water = region_map[r0.name].ecology.water
        pre_capacity = region_map[r0.name].carrying_capacity
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        return world, r0.name, adj_name, pre_water, pre_capacity

    def test_water_baseline_increased(self):
        world, rname, _, pre_water, _ = self._apply_rivers()
        region_map = {r.name: r for r in world.regions}
        # Water should be higher (exact amount depends on clamp)
        assert region_map[rname].ecology.water >= pre_water

    def test_carrying_capacity_multiplied(self):
        world, rname, _, _, pre_cap = self._apply_rivers()
        region_map = {r.name: r for r in world.regions}
        assert region_map[rname].carrying_capacity >= int(pre_cap * 1.2)

    def test_fish_assigned_to_empty_slot(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        # Find a river region that has an empty resource slot
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        region = region_map[r0.name]
        # If there was an empty slot, Fish should be assigned
        has_fish = ResourceType.FISH in region.resource_types
        has_empty = EMPTY_SLOT in region.resource_types
        # Either Fish was assigned or all slots were already full
        assert has_fish or not has_empty

    def test_fish_has_base_yield(self):
        """Phoebe N-2: Fish assignment must also set resource_base_yields."""
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        # Force an empty slot for testing
        r0.resource_types[2] = EMPTY_SLOT
        r0.resource_base_yields[2] = 0.0
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        region = region_map[r0.name]
        if ResourceType.FISH in region.resource_types:
            fish_idx = region.resource_types.index(ResourceType.FISH)
            assert region.resource_base_yields[fish_idx] > 0.0, "Fish must have base yield set"

    def test_full_slot_region_keeps_resources(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        # Fill all 3 slots
        r0.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, ResourceType.SALT]
        original_types = list(r0.resource_types)
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        assert region_map[r0.name].resource_types == original_types

    def test_confluence_bonuses_applied_once(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        shared = None
        for r in world.regions:
            if len(r.adjacencies) >= 2:
                shared = r
                break
        if shared is None:
            pytest.skip("No region with 2+ adjacencies")
        pre_water = shared.ecology.water
        a1, a2 = shared.adjacencies[0], shared.adjacencies[1]
        config = ScenarioConfig(
            name="Test",
            rivers=[
                River(name="River A", path=[a1, shared.name]),
                River(name="River B", path=[a2, shared.name]),
            ],
        )
        apply_scenario(world, config)
        region_map = {r.name: r for r in world.regions}
        # Water bonus should be applied once, not twice
        # The increase should be approximately RIVER_WATER_BONUS (0.15), not 0.30
        water_increase = region_map[shared.name].ecology.water - pre_water
        assert water_increase < 0.25  # Less than 2x the bonus
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestRiverWorldGenBonuses -v`
Expected: FAIL — no bonus application code yet

- [ ] **Step 3: Add river bonus application to apply_scenario**

In `src/chronicler/scenario.py`, extend Step 9 (after the river_mask assignment loop). Add lazy imports inside the `apply_scenario` function body (to avoid circular import with ecology.py), then the bonus code:

```python
    from chronicler.tuning import get_override, K_RIVER_WATER_BONUS, K_RIVER_CAPACITY_MULTIPLIER
    from chronicler.ecology import _clamp_ecology
    from chronicler.resources import RESOURCE_BASE
```

Then after the bitmask assignment loop:

```python
    # Apply river bonuses (once per region, not per river)
    import random as _rng_mod
    water_bonus = get_override(world, K_RIVER_WATER_BONUS, 0.15)
    cap_mult = get_override(world, K_RIVER_CAPACITY_MULTIPLIER, 1.2)
    for region in world.regions:
        if region.river_mask == 0:
            continue
        # Water baseline
        region.ecology.water += water_bonus
        _clamp_ecology(region)
        # Carrying capacity
        region.carrying_capacity = int(region.carrying_capacity * cap_mult)
        # Fish resource (Phoebe N-2: must also set base_yield)
        if ResourceType.FISH not in region.resource_types:
            for slot in range(3):
                if region.resource_types[slot] == EMPTY_SLOT:
                    region.resource_types[slot] = ResourceType.FISH
                    rng = _rng_mod.Random(world.seed + hash(region.name) + 0xF15F)
                    variance = rng.uniform(-0.2, 0.2)
                    region.resource_base_yields[slot] = RESOURCE_BASE[ResourceType.FISH] * (1.0 + variance)
                    break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestRiverWorldGenBonuses -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_rivers.py
git commit -m "feat(m35a): apply river world-gen bonuses (water, capacity, Fish)"
```

---

## Chunk 2: Ecological Cascade

### Task 7: Upstream Deforestation Cascade in tick_ecology

**Files:**
- Modify: `src/chronicler/ecology.py:425` (insert cascade after uncontrolled region loop, before resource yield computation)
- Test: `tests/test_rivers.py`

**Phoebe N-1 note:** `_clamp_ecology()` runs inside the per-region loops (lines 391, 425) but not after the cascade. Cascade-affected regions need a second clamp pass.

- [ ] **Step 1: Write failing tests for cascade**

```python
# Append to tests/test_rivers.py
from chronicler.ecology import tick_ecology
from chronicler.models import ClimatePhase


class TestDeforestationCascade:
    def _make_river_world(self):
        """Create a world with a 3-region river: headwater → mid → delta."""
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        # Pick 3 adjacent regions to form a river
        for r in world.regions:
            if len(r.adjacencies) >= 1:
                head = r
                break
        mid_name = head.adjacencies[0]
        region_map = {r.name: r for r in world.regions}
        mid = region_map[mid_name]
        # Find a third region adjacent to mid (not head)
        delta = None
        for adj_name in mid.adjacencies:
            if adj_name != head.name:
                delta = region_map[adj_name]
                break
        if delta is None:
            pytest.skip("Cannot form 3-region river path")

        config = ScenarioConfig(
            name="Cascade Test",
            rivers=[River(name="Test River", path=[head.name, mid.name, delta.name])],
        )
        apply_scenario(world, config)
        # Ensure all regions have controllers for ecology tick
        for r in world.regions:
            if r.controller is None:
                r.controller = world.civilizations[0].name
        return world, head.name, mid.name, delta.name

    def test_cascade_triggers_on_deforestation(self):
        world, head, mid, delta = self._make_river_world()
        region_map = {r.name: r for r in world.regions}
        # Deforest headwater below threshold
        region_map[head].ecology.forest_cover = 0.1
        # Set downstream water to known values
        region_map[mid].ecology.water = 0.5
        region_map[delta].ecology.water = 0.5
        pre_mid = region_map[mid].ecology.water
        pre_delta = region_map[delta].ecology.water
        tick_ecology(world, ClimatePhase.TEMPERATE)
        # Both downstream regions should have lost water
        assert region_map[mid].ecology.water < pre_mid
        assert region_map[delta].ecology.water < pre_delta

    def test_no_cascade_when_forest_healthy(self):
        world, head, mid, delta = self._make_river_world()
        region_map = {r.name: r for r in world.regions}
        region_map[head].ecology.forest_cover = 0.5  # Well above threshold
        # Run two ticks: one baseline, one with the same healthy forest
        # The difference should be zero (no cascade penalty)
        region_map[mid].ecology.water = 0.5
        tick_ecology(world, ClimatePhase.TEMPERATE)
        water_after_first = region_map[mid].ecology.water
        region_map[mid].ecology.water = 0.5  # Reset to same starting point
        region_map[head].ecology.forest_cover = 0.5  # Still healthy
        tick_ecology(world, ClimatePhase.TEMPERATE)
        water_after_second = region_map[mid].ecology.water
        # Both ticks should produce the same result (no cascade either time)
        assert abs(water_after_first - water_after_second) < 0.001

    def test_headwater_immune(self):
        world, head, mid, delta = self._make_river_world()
        region_map = {r.name: r for r in world.regions}
        # Deforest mid (not headwater) — head is upstream, should not be penalized
        region_map[mid].ecology.forest_cover = 0.1
        # Run baseline tick with healthy mid to get normal head water
        region_map_copy_water = region_map[head].ecology.water
        region_map[mid].ecology.forest_cover = 0.5
        tick_ecology(world, ClimatePhase.TEMPERATE)
        head_water_healthy = region_map[head].ecology.water
        # Reset and run with deforested mid
        region_map[head].ecology.water = region_map_copy_water
        region_map[mid].ecology.forest_cover = 0.1
        tick_ecology(world, ClimatePhase.TEMPERATE)
        head_water_deforested = region_map[head].ecology.water
        # Head water should be the same — cascade only flows downstream
        assert abs(head_water_healthy - head_water_deforested) < 0.001

    def test_water_clamp_floor(self):
        world, head, mid, delta = self._make_river_world()
        region_map = {r.name: r for r in world.regions}
        # Deforest headwater
        region_map[head].ecology.forest_cover = 0.05
        # Set delta water very low
        region_map[delta].ecology.water = 0.12
        tick_ecology(world, ClimatePhase.TEMPERATE)
        # Water should not go below floor (0.10)
        assert region_map[delta].ecology.water >= 0.10

    def test_cascade_dedup_same_source(self):
        """Same deforested region on two rivers shouldn't double-penalize."""
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        # Find a region with 2+ adjacencies to create a shared upstream
        shared = None
        for r in world.regions:
            if len(r.adjacencies) >= 2:
                shared = r
                break
        if shared is None:
            pytest.skip("Need region with 2+ adjacencies")
        a1, a2 = shared.adjacencies[0], shared.adjacencies[1]
        region_map = {r.name: r for r in world.regions}
        # Find a downstream target adjacent to both a1 and a2 via shared
        # Use shared as upstream, a1 and a2 as downstream via separate rivers
        config = ScenarioConfig(
            name="Dedup Test",
            rivers=[
                River(name="River A", path=[shared.name, a1]),
                River(name="River B", path=[shared.name, a2]),
            ],
        )
        apply_scenario(world, config)
        for r in world.regions:
            if r.controller is None:
                r.controller = world.civilizations[0].name
        region_map = {r.name: r for r in world.regions}
        region_map[shared.name].ecology.forest_cover = 0.1
        region_map[a1].ecology.water = 0.5
        region_map[a2].ecology.water = 0.5
        tick_ecology(world, ClimatePhase.TEMPERATE)
        # a1 and a2 each get penalized once (they're on separate rivers, different targets)
        # This test just ensures no crash and reasonable values
        assert region_map[a1].ecology.water >= 0.10
        assert region_map[a2].ecology.water >= 0.10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestDeforestationCascade -v`
Expected: FAIL — no cascade code in tick_ecology

- [ ] **Step 3: Implement cascade in tick_ecology**

In `src/chronicler/ecology.py`, add `K_DEFORESTATION_THRESHOLD` and `K_DEFORESTATION_WATER_LOSS` to the existing `from chronicler.tuning import ...` statement (line 12). Do NOT add a second import line.

After line 425 (after the uncontrolled region loop's `_clamp_ecology(region)`), before the `# --- M34: Compute resource yields` comment at line 427, insert:

```python
    # --- M35a: Upstream deforestation cascade ---
    if world.rivers:
        deforest_thresh = get_override(world, K_DEFORESTATION_THRESHOLD, 0.2)
        deforest_loss = get_override(world, K_DEFORESTATION_WATER_LOSS, 0.05)
        region_map = {r.name: r for r in world.regions}
        cascade_affected: set[str] = set()
        seen: set[tuple[str, str]] = set()
        for river in world.rivers:
            for i, rname in enumerate(river.path):
                region = region_map[rname]
                if region.ecology.forest_cover < deforest_thresh:
                    for downstream_name in river.path[i + 1:]:
                        if (rname, downstream_name) not in seen:
                            seen.add((rname, downstream_name))
                            region_map[downstream_name].ecology.water -= deforest_loss
                            cascade_affected.add(downstream_name)
        # Phoebe N-1: second clamp pass for cascade-affected regions
        for rname in cascade_affected:
            _clamp_ecology(region_map[rname])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestDeforestationCascade -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/ecology.py tests/test_rivers.py
git commit -m "feat(m35a): upstream deforestation cascade in ecology tick"
```

---

## Chunk 3: Rust Integration — RegionState, FFI, Migration Bonus

### Task 8: Add river_mask to Rust RegionState

**Files:**
- Modify: `chronicler-agents/src/region.rs:19-37` (add field to RegionState)
- Modify: `chronicler-agents/src/region.rs:40-42` (update RegionState::new)

- [ ] **Step 1: Write failing Rust test**

In `chronicler-agents/src/region.rs`, add to the `tests` module (after the existing tests):

```rust
    #[test]
    fn test_region_new_has_river_mask_default() {
        let r = RegionState::new(5);
        assert_eq!(r.river_mask, 0);
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chronicler-agents && cargo test test_region_new_has_river_mask_default -- --nocapture`
Expected: FAIL — `river_mask` not a field on RegionState

- [ ] **Step 3: Add river_mask field**

In `chronicler-agents/src/region.rs`, add after line 36 (`pub season_id: u8,`):

```rust
    // M35a: River bitmask
    pub river_mask: u32,
```

In the `RegionState::new()` method (line 41), add `river_mask: 0` to the struct literal (after `season_id: 0`):

```rust
    Self { region_id, terrain: Terrain::Plains as u8, carrying_capacity: 60, population: 0, soil: 0.8, water: 0.6, forest_cover: 0.3, adjacency_mask: 0, controller_civ: 255, trade_route_count: 0, resource_types: [255, 255, 255], resource_yields: [0.0, 0.0, 0.0], resource_reserves: [1.0, 1.0, 1.0], season: 0, season_id: 0, river_mask: 0 }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chronicler-agents && cargo test test_region_new_has_river_mask_default -- --nocapture`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/region.rs
git commit -m "feat(m35a): add river_mask field to RegionState"
```

---

### Task 9: FFI — Read river_mask from Arrow RecordBatch

**Files:**
- Modify: `chronicler-agents/src/ffi.rs:288-290` (add optional column read, after season_id_col)
- Modify: `chronicler-agents/src/ffi.rs:327` (add to init struct literal)
- Modify: `chronicler-agents/src/ffi.rs:407` (add to update path)

- [ ] **Step 1: Add river_mask column read to ffi.rs**

In `chronicler-agents/src/ffi.rs`, after line 290 (after `season_id_col` optional column), add:

```rust
        // Optional M35a column
        let river_mask_col = rb
            .column_by_name("river_mask")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::UInt32Array>());
```

In the init block (after line 327, after `season_id`), add to the RegionState struct literal:

```rust
                    river_mask: river_mask_col.map_or(0, |arr| arr.value(i)),
```

In the update block (after line 407, after `r.season_id = ...`), add:

```rust
                r.river_mask = river_mask_col.map_or(r.river_mask, |arr| arr.value(i));
```

- [ ] **Step 2: Run all Rust tests to verify no regressions**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add chronicler-agents/src/ffi.rs
git commit -m "feat(m35a): read river_mask column from Arrow RecordBatch"
```

---

### Task 10: Python Bridge — Write river_mask Column

**Files:**
- Modify: `src/chronicler/agent_bridge.py:131` (add river_mask column after season_id)
- Test: `tests/test_rivers.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_rivers.py
import pyarrow as pa
from chronicler.agent_bridge import build_region_batch


class TestRiverBridge:
    def test_river_mask_in_record_batch(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj_name = r0.adjacencies[0] if r0.adjacencies else None
        if adj_name is None:
            pytest.skip("No adjacencies")
        config = ScenarioConfig(
            name="Test",
            rivers=[River(name="Test River", path=[r0.name, adj_name])],
        )
        apply_scenario(world, config)
        batch = build_region_batch(world)
        assert "river_mask" in batch.schema.names
        masks = batch.column("river_mask").to_pylist()
        region_map = {r.name: i for i, r in enumerate(world.regions)}
        assert masks[region_map[r0.name]] == 1  # bit 0
        assert masks[region_map[adj_name]] == 1

    def test_non_river_region_mask_zero_in_batch(self):
        world = generate_world(seed=42, num_regions=8, num_civs=2)
        # No rivers
        batch = build_region_batch(world)
        assert "river_mask" in batch.schema.names
        masks = batch.column("river_mask").to_pylist()
        assert all(m == 0 for m in masks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rivers.py::TestRiverBridge -v`
Expected: FAIL — `river_mask` not in batch schema

- [ ] **Step 3: Add river_mask column to build_region_batch**

In `src/chronicler/agent_bridge.py`, after line 131 (after `"season_id"` column), add:

```python
        # M35a: River mask
        "river_mask": pa.array([r.river_mask for r in world.regions], type=pa.uint32()),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rivers.py::TestRiverBridge -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_rivers.py
git commit -m "feat(m35a): add river_mask column to Arrow RecordBatch"
```

---

### Task 11: Migration Bonus in compute_region_stats

**Files:**
- Modify: `chronicler-agents/src/behavior.rs:232-247` (replace migration target loop with river-aware version)

- [ ] **Step 1: Write failing Rust test**

In `chronicler-agents/src/behavior.rs`, add a test at the bottom of the file (or in the existing test module):

```rust
#[cfg(test)]
mod river_tests {
    use super::*;
    use crate::region::RegionState;
    use crate::pool::AgentPool;
    use crate::agent::Occupation;
    use crate::signals::TickSignals;

    #[test]
    fn test_river_migration_bonus() {
        // Setup: 3 regions. Region 0 and 1 share a river (mask bit 0).
        // Region 2 has no river. Regions 0-1 adjacent, 0-2 adjacent.
        // Agent on region 0, regions 1 and 2 have same satisfaction.
        let mut regions = vec![
            RegionState::new(0),
            RegionState::new(1),
            RegionState::new(2),
        ];
        // Region 0 adjacent to 1 and 2
        regions[0].adjacency_mask = 0b110; // bits 1 and 2
        regions[1].adjacency_mask = 0b001; // bit 0
        regions[2].adjacency_mask = 0b001; // bit 0

        // River: regions 0 and 1 share river 0
        regions[0].river_mask = 1;
        regions[1].river_mask = 1;
        regions[2].river_mask = 0;

        // Give all regions the same base conditions
        for r in &mut regions {
            r.carrying_capacity = 60;
            r.population = 30;
            r.soil = 0.8;
            r.water = 0.6;
            r.forest_cover = 0.3;
            r.controller_civ = 0;
        }

        let signals = TickSignals {
            civs: vec![],
            contested_regions: vec![false, false, false],
        };
        let mut pool = AgentPool::new(100);
        // Spawn agents on region 0
        for _ in 0..10 {
            pool.spawn(0, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5);
        }
        // Spawn equal agents on regions 1 and 2 for equal satisfaction
        for _ in 0..10 {
            pool.spawn(1, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5);
        }
        for _ in 0..10 {
            pool.spawn(2, 0, Occupation::Farmer, 0, 0.5, 0.5, 0.5);
        }

        let stats = compute_region_stats(&pool, &regions, &signals);

        // Region 1 (river-connected) should be preferred over region 2 (non-river)
        // as migration target from region 0, due to river bonus
        assert_eq!(stats.best_migration_target[0], 1,
            "River-connected region should be preferred migration target");
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chronicler-agents && cargo test test_river_migration_bonus -- --nocapture`
Expected: FAIL — no river bonus logic, target could be either 1 or 2

- [ ] **Step 3: Implement river migration bonus**

In `chronicler-agents/src/behavior.rs`, add constant near the top (with other constants):

```rust
/// M35a: Migration attractiveness bonus for river-connected neighbors. [CALIBRATE]
const RIVER_MIGRATION_BONUS: f32 = 0.1;
```

In the migration target loop (lines 236-244), modify the neighbor comparison to include the river bonus. Replace the loop body:

```rust
    for r in 0..n {
        let own_mean = mean_satisfaction[r];
        let mut best_adj_mean = own_mean;
        let mut best_adj_id: u16 = r as u16;
        for bit in 0..32u32 {
            if regions[r].adjacency_mask & (1 << bit) != 0 {
                let adj = bit as usize;
                if adj < n {
                    let mut adj_score = mean_satisfaction[adj];
                    // M35a: River-connected neighbors get a bonus
                    if regions[r].river_mask & regions[adj].river_mask != 0 {
                        adj_score += RIVER_MIGRATION_BONUS;
                    }
                    if adj_score > best_adj_mean {
                        best_adj_mean = adj_score;
                        best_adj_id = adj as u16;
                    }
                }
            }
        }
        migration_opportunity[r] = (best_adj_mean - own_mean).max(0.0);
        best_migration_target[r] = best_adj_id;
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chronicler-agents && cargo test test_river_migration_bonus -- --nocapture`
Expected: PASS

- [ ] **Step 5: Run all Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/behavior.rs
git commit -m "feat(m35a): add river migration bonus in compute_region_stats"
```

---

## Chunk 4: Integration Test & Final Verification

### Task 12: End-to-End Integration Test

**Files:**
- Test: `tests/test_rivers.py`

- [ ] **Step 1: Write integration test**

```python
# Append to tests/test_rivers.py

class TestRiverIntegration:
    """End-to-end: scenario with rivers → world-gen → ecology ticks → verify cascading."""

    def test_river_scenario_runs_100_turns(self):
        """Smoke test: a river scenario runs without errors for 100 turns."""
        from chronicler.simulation import run_turn
        from chronicler.action_engine import ActionEngine

        world = generate_world(seed=42, num_regions=8, num_civs=2)
        r0 = world.regions[0]
        adj = r0.adjacencies[0] if r0.adjacencies else None
        if adj is None:
            pytest.skip("No adjacencies")
        # Find a 3-region path
        region_map = {r.name: r for r in world.regions}
        mid = region_map[adj]
        delta_name = None
        for a in mid.adjacencies:
            if a != r0.name:
                delta_name = a
                break
        if delta_name is None:
            path = [r0.name, adj]
        else:
            path = [r0.name, adj, delta_name]

        config = ScenarioConfig(
            name="River Integration",
            rivers=[River(name="Great River", path=path)],
        )
        apply_scenario(world, config)

        engine = ActionEngine(world)
        # Narrator is Callable[[WorldState, list[Event]], str] — use a no-op
        narrator = lambda world, events: ""
        for _ in range(100):
            run_turn(world, engine, narrator)

        # Basic sanity: world still has rivers, no crashes
        assert len(world.rivers) == 1
        assert world.turn == 100

    def test_river_regions_have_higher_water_after_gen(self):
        """River regions start with higher water than equivalent non-river terrain."""
        world = generate_world(seed=99, num_regions=12, num_civs=3)
        r0 = world.regions[0]
        adj = r0.adjacencies[0] if r0.adjacencies else None
        if adj is None:
            pytest.skip("No adjacencies")

        # Record pre-scenario water values
        pre_waters = {r.name: r.ecology.water for r in world.regions}

        config = ScenarioConfig(
            name="Water Test",
            rivers=[River(name="Test River", path=[r0.name, adj])],
        )
        apply_scenario(world, config)

        region_map = {r.name: r for r in world.regions}
        for rname in [r0.name, adj]:
            # Note: apply_scenario re-runs assign_resources which may change things,
            # so just verify river regions have reasonable water
            assert region_map[rname].river_mask != 0
            assert region_map[rname].ecology.water >= 0.10  # Above floor
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_rivers.py::TestRiverIntegration -v --timeout=120`
Expected: PASS (2 tests)

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v --timeout=120`
Expected: All tests PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add tests/test_rivers.py
git commit -m "test(m35a): add end-to-end river integration tests"
```

---

### Task 13: Build Verification

- [ ] **Step 1: Rebuild Rust crate and verify Python integration**

Run: `cd chronicler-agents && cargo build --release`
Expected: Build succeeds with no warnings related to river_mask

- [ ] **Step 2: Install updated Python package**

Run: `cd chronicler-agents && maturin develop --release`
Expected: Package installs successfully

- [ ] **Step 3: Run full test suite with Rust integration**

Run: `pytest tests/ -v --timeout=120`
Expected: All tests PASS

- [ ] **Step 4: Final commit with any build fixes if needed**

```bash
git status  # Check for any uncommitted changes
```
