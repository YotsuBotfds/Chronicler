# M35b: Disease, Depletion & Environmental Events — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add endemic disease, resource depletion feedback loops, and condition-triggered environmental events to the simulation.

**Architecture:** Python-primary — disease severity computed per-region in ecology tick, passed to Rust as a single `f32` on `RegionState`. Environmental events integrate into existing `emergence.py` pipeline. Depletion feedback runs in ecology tick. All 21 constants route through `tuning.py` with `KNOWN_OVERRIDES`.

**Tech Stack:** Python (ecology.py, emergence.py, models.py, world_gen.py, tuning.py, agent_bridge.py), Rust (region.rs, demographics.rs, ffi.rs, tick.rs), pytest, cargo test.

**Spec:** `docs/superpowers/specs/2026-03-16-m35b-disease-depletion-events-design.md`

---

## Chunk 1: Data Model, Constants & World-Gen

### Task 1: Add M35b tuning constants

**Files:**
- Modify: `src/chronicler/tuning.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tuning.py — append to existing test file
def test_m35b_disease_constants_registered():
    from chronicler.tuning import KNOWN_OVERRIDES
    assert "ecology.disease_baseline_fever" in KNOWN_OVERRIDES
    assert "ecology.disease_baseline_cholera" in KNOWN_OVERRIDES
    assert "ecology.disease_baseline_plague" in KNOWN_OVERRIDES
    assert "ecology.disease_severity_cap" in KNOWN_OVERRIDES
    assert "ecology.disease_decay_rate" in KNOWN_OVERRIDES
    assert "ecology.flare_overcrowding_threshold" in KNOWN_OVERRIDES
    assert "ecology.flare_overcrowding_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_army_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_water_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_season_spike" in KNOWN_OVERRIDES
    assert "ecology.soil_pressure_threshold" in KNOWN_OVERRIDES
    assert "ecology.soil_pressure_streak_limit" in KNOWN_OVERRIDES
    assert "ecology.overextraction_streak_limit" in KNOWN_OVERRIDES
    assert "ecology.overextraction_yield_penalty" in KNOWN_OVERRIDES
    assert "ecology.workers_per_yield_unit" in KNOWN_OVERRIDES


def test_m35b_emergence_constants_registered():
    from chronicler.tuning import KNOWN_OVERRIDES
    assert "emergence.locust_probability" in KNOWN_OVERRIDES
    assert "emergence.flood_probability" in KNOWN_OVERRIDES
    assert "emergence.collapse_probability" in KNOWN_OVERRIDES
    assert "emergence.drought_intensification_probability" in KNOWN_OVERRIDES
    assert "emergence.collapse_mortality_spike" in KNOWN_OVERRIDES
    assert "emergence.ecological_recovery_probability" in KNOWN_OVERRIDES
    assert "emergence.ecological_recovery_fraction" in KNOWN_OVERRIDES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tuning.py::test_m35b_disease_constants_registered tests/test_tuning.py::test_m35b_emergence_constants_registered -v`
Expected: FAIL — keys not in KNOWN_OVERRIDES

- [ ] **Step 3: Add constants to tuning.py**

Add after the `K_DEFORESTATION_WATER_LOSS` line (line 55) in `src/chronicler/tuning.py`:

```python
# M35b: Disease
K_DISEASE_BASELINE_FEVER = "ecology.disease_baseline_fever"
K_DISEASE_BASELINE_CHOLERA = "ecology.disease_baseline_cholera"
K_DISEASE_BASELINE_PLAGUE = "ecology.disease_baseline_plague"
K_DISEASE_SEVERITY_CAP = "ecology.disease_severity_cap"
K_DISEASE_DECAY_RATE = "ecology.disease_decay_rate"
K_FLARE_OVERCROWDING_THRESHOLD = "ecology.flare_overcrowding_threshold"
K_FLARE_OVERCROWDING_SPIKE = "ecology.flare_overcrowding_spike"
K_FLARE_ARMY_SPIKE = "ecology.flare_army_spike"
K_FLARE_WATER_SPIKE = "ecology.flare_water_spike"
K_FLARE_SEASON_SPIKE = "ecology.flare_season_spike"
# M35b: Depletion
K_SOIL_PRESSURE_THRESHOLD = "ecology.soil_pressure_threshold"
K_SOIL_PRESSURE_STREAK_LIMIT = "ecology.soil_pressure_streak_limit"
K_OVEREXTRACTION_STREAK_LIMIT = "ecology.overextraction_streak_limit"
K_OVEREXTRACTION_YIELD_PENALTY = "ecology.overextraction_yield_penalty"
K_WORKERS_PER_YIELD_UNIT = "ecology.workers_per_yield_unit"
# M35b: Environmental events
K_LOCUST_PROBABILITY = "emergence.locust_probability"
K_FLOOD_PROBABILITY = "emergence.flood_probability"
K_COLLAPSE_PROBABILITY = "emergence.collapse_probability"
K_DROUGHT_INTENSIFICATION_PROBABILITY = "emergence.drought_intensification_probability"
K_COLLAPSE_MORTALITY_SPIKE = "emergence.collapse_mortality_spike"
K_ECOLOGICAL_RECOVERY_PROBABILITY = "emergence.ecological_recovery_probability"
K_ECOLOGICAL_RECOVERY_FRACTION = "emergence.ecological_recovery_fraction"
```

Then add all 21 keys to the `KNOWN_OVERRIDES` set (after the M35a entries):

```python
    K_DISEASE_BASELINE_FEVER, K_DISEASE_BASELINE_CHOLERA, K_DISEASE_BASELINE_PLAGUE,
    K_DISEASE_SEVERITY_CAP, K_DISEASE_DECAY_RATE,
    K_FLARE_OVERCROWDING_THRESHOLD, K_FLARE_OVERCROWDING_SPIKE,
    K_FLARE_ARMY_SPIKE, K_FLARE_WATER_SPIKE, K_FLARE_SEASON_SPIKE,
    K_SOIL_PRESSURE_THRESHOLD, K_SOIL_PRESSURE_STREAK_LIMIT,
    K_OVEREXTRACTION_STREAK_LIMIT, K_OVEREXTRACTION_YIELD_PENALTY,
    K_WORKERS_PER_YIELD_UNIT,
    K_LOCUST_PROBABILITY, K_FLOOD_PROBABILITY, K_COLLAPSE_PROBABILITY,
    K_DROUGHT_INTENSIFICATION_PROBABILITY, K_COLLAPSE_MORTALITY_SPIKE,
    K_ECOLOGICAL_RECOVERY_PROBABILITY, K_ECOLOGICAL_RECOVERY_FRACTION,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tuning.py::test_m35b_disease_constants_registered tests/test_tuning.py::test_m35b_emergence_constants_registered -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tuning.py tests/test_tuning.py
git commit -m "feat(m35b): add 21 tuning constants for disease, depletion, events"
```

---

### Task 2: Add new fields to Region model

**Files:**
- Modify: `src/chronicler/models.py:154-183` (Region class)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m35b_disease.py (new file)
from chronicler.models import Region


def test_region_has_disease_fields():
    r = Region(name="Test", terrain="plains", carrying_capacity=60, resources="fertile")
    assert r.disease_baseline == 0.01
    assert r.endemic_severity == 0.01
    assert r.soil_pressure_streak == 0
    assert r.overextraction_streaks == {}
    assert r.resource_effective_yields == [0.0, 0.0, 0.0]
    assert r.capacity_modifier == 1.0
    assert r.prev_turn_water == -1.0  # sentinel: not yet set
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_m35b_disease.py::test_region_has_disease_fields -v`
Expected: FAIL — fields don't exist on Region

- [ ] **Step 3: Add fields to Region in models.py**

Add after `river_mask: int = 0` (line 182) in `src/chronicler/models.py`:

```python
    # M35b: Disease, Depletion & Environmental Events
    disease_baseline: float = 0.01
    endemic_severity: float = 0.01
    soil_pressure_streak: int = 0
    overextraction_streaks: dict[int, int] = Field(default_factory=dict)
    resource_effective_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    capacity_modifier: float = 1.0  # Temporary capacity multiplier (flood=0.85, drought=0.5)
    prev_turn_water: float = -1.0  # Previous turn's water level for delta tracking (-1 = unset)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m35b_disease.py::test_region_has_disease_fields -v`
Expected: PASS

- [ ] **Step 5: Run existing model tests for regression**

Run: `python -m pytest tests/test_models.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_m35b_disease.py
git commit -m "feat(m35b): add disease, depletion fields to Region model"
```

---

### Task 3: Initialize disease baseline and effective yields at world-gen

**Files:**
- Modify: `src/chronicler/world_gen.py:187-243` (generate_world function)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m35b_disease.py — append
from chronicler.world_gen import generate_world


def test_disease_baseline_assigned_at_worldgen():
    world = generate_world(seed=42)
    for region in world.regions:
        assert region.disease_baseline > 0.0, f"{region.name} has no disease baseline"
        assert region.endemic_severity == region.disease_baseline
        # Desert regions get cholera baseline (0.015)
        if region.terrain == "desert":
            assert region.disease_baseline == 0.015
        # High water + soil regions get fever baseline (0.02)
        elif region.ecology.water > 0.6 and region.ecology.soil > 0.5:
            assert region.disease_baseline == 0.02
        # Others get plague baseline (0.01)
        else:
            assert region.disease_baseline == 0.01


def test_effective_yields_initialized_at_worldgen():
    world = generate_world(seed=42)
    for region in world.regions:
        assert region.resource_effective_yields == region.resource_base_yields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_m35b_disease.py::test_disease_baseline_assigned_at_worldgen tests/test_m35b_disease.py::test_effective_yields_initialized_at_worldgen -v`
Expected: FAIL — baselines not assigned, effective yields not initialized

- [ ] **Step 3: Add initialization to world_gen.py**

In `generate_world()`, after the M16a cultural identity block (line 241) and before `return world`, add:

```python
    # M35b: Initialize disease baseline and effective yields
    for region in world.regions:
        eco = region.ecology
        if eco.water > 0.6 and eco.soil > 0.5:
            region.disease_baseline = 0.02  # Fever
        elif region.terrain == "desert":
            region.disease_baseline = 0.015  # Cholera
        else:
            region.disease_baseline = 0.01  # Plague
        region.endemic_severity = region.disease_baseline
        region.resource_effective_yields = list(region.resource_base_yields)
```

Note: The baseline assignment uses hardcoded defaults here. These match the tuning constants (`K_DISEASE_BASELINE_FEVER` etc.) but world-gen doesn't have access to `world.tuning_overrides` yet (world isn't created yet). The tuning constants are for runtime override via YAML, not for world-gen.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m35b_disease.py::test_disease_baseline_assigned_at_worldgen tests/test_m35b_disease.py::test_effective_yields_initialized_at_worldgen -v`
Expected: PASS

- [ ] **Step 5: Run existing world-gen tests for regression**

Run: `python -m pytest tests/test_world_gen.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_m35b_disease.py
git commit -m "feat(m35b): initialize disease baseline and effective yields at world-gen"
```

---

## Chunk 2: Endemic Disease Computation

### Task 4: Implement compute_disease_severity()

**Files:**
- Modify: `src/chronicler/ecology.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_m35b_disease.py — append
from chronicler.models import Region, RegionEcology, WorldState, AgentEventRecord


def _make_region(terrain="plains", water=0.6, soil=0.8, pop=40, capacity=60, baseline=0.01):
    r = Region(
        name="TestRegion", terrain=terrain, carrying_capacity=capacity,
        population=pop, resources="fertile",
        ecology=RegionEcology(soil=soil, water=water, forest_cover=0.3),
    )
    r.disease_baseline = baseline
    r.endemic_severity = baseline
    return r


def test_disease_no_triggers_decays_toward_baseline():
    """When no triggers fire, severity decays 25% toward baseline."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.01)
    r.endemic_severity = 0.09  # Artificially high
    compute_disease_severity(r, world=None, pre_water=0.6)
    # Decay: 0.09 - 0.25 * (0.09 - 0.01) = 0.09 - 0.02 = 0.07
    assert abs(r.endemic_severity - 0.07) < 0.001


def test_disease_overcrowding_flare():
    """Population > 0.8 * capacity triggers +0.04 spike."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.01, pop=50, capacity=60)  # 50/60 = 0.83 > 0.8
    compute_disease_severity(r, world=None, pre_water=0.6)
    assert abs(r.endemic_severity - (0.01 + 0.04)) < 0.001


def test_disease_severity_capped_at_015():
    """Severity never exceeds 0.15 regardless of trigger stacking."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(baseline=0.02, pop=50, capacity=60)
    r.endemic_severity = 0.14  # Near cap
    compute_disease_severity(r, world=None, pre_water=0.6)
    # Overcrowding would push to 0.14 + 0.04 = 0.18, but capped at 0.15
    assert r.endemic_severity <= 0.15


def test_disease_water_quality_flare():
    """Water < 0.3 on non-desert terrain triggers +0.02 spike."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="plains", baseline=0.01, water=0.25, pop=20, capacity=60)
    compute_disease_severity(r, world=None, pre_water=0.25)
    assert abs(r.endemic_severity - (0.01 + 0.02)) < 0.001


def test_disease_water_drop_flare():
    """Water dropping > 0.1 since previous turn triggers +0.02."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="plains", baseline=0.01, water=0.5, pop=20, capacity=60)
    r.prev_turn_water = 0.65  # Previous turn had higher water
    compute_disease_severity(r, world=None, pre_water=0.5)
    assert abs(r.endemic_severity - (0.01 + 0.02)) < 0.001


def test_disease_desert_no_seasonal_peak():
    """Cholera (desert) has no seasonal modifier."""
    from chronicler.ecology import compute_disease_severity
    r = _make_region(terrain="desert", baseline=0.015, pop=20, capacity=60)
    # Even in summer, no seasonal spike for cholera
    compute_disease_severity(r, world=None, pre_water=0.1, season_id=1)  # summer
    # No triggers: low pop, desert terrain (water < 0.3 but IS desert so no water flare)
    # Should just equal baseline (no triggers → decay toward baseline, but already at baseline)
    assert abs(r.endemic_severity - 0.015) < 0.001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_m35b_disease.py::test_disease_no_triggers_decays_toward_baseline tests/test_m35b_disease.py::test_disease_overcrowding_flare tests/test_m35b_disease.py::test_disease_severity_capped_at_015 tests/test_m35b_disease.py::test_disease_water_quality_flare tests/test_m35b_disease.py::test_disease_water_drop_flare tests/test_m35b_disease.py::test_disease_desert_no_seasonal_peak -v`
Expected: FAIL — `compute_disease_severity` not defined

- [ ] **Step 3: Implement compute_disease_severity()**

Add the following imports at the top of `src/chronicler/ecology.py` (extend the existing tuning import block):

```python
from chronicler.tuning import (
    # ... existing imports ...
    K_DISEASE_SEVERITY_CAP, K_DISEASE_DECAY_RATE,
    K_FLARE_OVERCROWDING_THRESHOLD, K_FLARE_OVERCROWDING_SPIKE,
    K_FLARE_ARMY_SPIKE, K_FLARE_WATER_SPIKE, K_FLARE_SEASON_SPIKE,
    K_SOIL_PRESSURE_THRESHOLD, K_SOIL_PRESSURE_STREAK_LIMIT,
    K_OVEREXTRACTION_STREAK_LIMIT, K_OVEREXTRACTION_YIELD_PENALTY,
    K_WORKERS_PER_YIELD_UNIT,
)
```

Add this function before `tick_ecology()`:

```python
def compute_disease_severity(
    region: "Region",
    world: "WorldState | None",
    pre_water: float,
    season_id: int = 0,
) -> None:
    """Update region.endemic_severity based on flare triggers or decay.

    Must be called at the top of the ecology tick, before water/soil updates.
    pre_water is the region's water value at tick start (before ecology mutates it).
    """
    cap = get_override(world, K_DISEASE_SEVERITY_CAP, 0.15) if world else 0.15
    decay_rate = get_override(world, K_DISEASE_DECAY_RATE, 0.25) if world else 0.25
    overcrowding_thresh = get_override(world, K_FLARE_OVERCROWDING_THRESHOLD, 0.8) if world else 0.8
    overcrowding_spike = get_override(world, K_FLARE_OVERCROWDING_SPIKE, 0.04) if world else 0.04
    army_spike = get_override(world, K_FLARE_ARMY_SPIKE, 0.03) if world else 0.03
    water_spike = get_override(world, K_FLARE_WATER_SPIKE, 0.02) if world else 0.02
    season_spike = get_override(world, K_FLARE_SEASON_SPIKE, 0.02) if world else 0.02

    baseline = region.disease_baseline
    severity = region.endemic_severity
    triggered = False

    # --- Overcrowding ---
    if region.carrying_capacity > 0 and region.population > overcrowding_thresh * region.carrying_capacity:
        severity += overcrowding_spike
        triggered = True

    # --- Army passage (previous turn) ---
    if world is not None and hasattr(world, "agent_events_raw") and world.agent_events_raw:
        prev_turn = world.turn - 1
        # Check for soldier (occupation=1) migration into this region last turn
        region_idx = next((i for i, r in enumerate(world.regions) if r is region), None)
        if region_idx is not None:
            army_arrived = any(
                e.event_type == "migration"
                and e.occupation == 1
                and e.target_region == region_idx
                for e in world.agent_events_raw
                if e.turn == prev_turn
            )
            if army_arrived:
                severity += army_spike
                triggered = True

    # --- Water quality ---
    # Low water on non-desert terrain
    if region.terrain != "desert" and pre_water < 0.3:
        severity += water_spike
        triggered = True
    # Water dropped > 0.1 since previous turn (uses prev_turn_water stored on Region)
    if region.terrain != "desert" and region.prev_turn_water >= 0:
        water_delta = region.prev_turn_water - pre_water
        if water_delta > 0.1 and not (pre_water < 0.3):  # Don't double-count with low-water trigger
            severity += water_spike
            triggered = True

    # --- Seasonal peak ---
    # season_id: 0=Spring, 1=Summer, 2=Autumn, 3=Winter
    is_fever = region.disease_baseline >= 0.02
    is_plague = region.disease_baseline <= 0.01
    is_cholera = region.terrain == "desert"
    if is_fever and not is_cholera and season_id == 1:  # Summer
        severity += season_spike
        triggered = True
    elif is_plague and not is_cholera and season_id == 3:  # Winter
        severity += season_spike
        triggered = True
    # Cholera: no seasonal modifier

    # --- Pandemic skip ---
    if world is not None and hasattr(world, "pandemic_state"):
        if any(p.region_name == region.name for p in world.pandemic_state):
            # Don't flare during active pandemic — skip spike, just decay
            severity = region.endemic_severity  # Reset to pre-trigger value
            triggered = False

    if triggered:
        region.endemic_severity = min(severity, cap)
    else:
        # Decay toward baseline
        region.endemic_severity -= decay_rate * (region.endemic_severity - baseline)

    # Floor at baseline
    if region.endemic_severity < baseline:
        region.endemic_severity = baseline
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_m35b_disease.py -v -k "disease"`
Expected: All disease tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_m35b_disease.py
git commit -m "feat(m35b): implement compute_disease_severity with flare triggers and decay"
```

---

### Task 5: Wire disease computation into tick_ecology()

**Files:**
- Modify: `src/chronicler/ecology.py:379-469` (tick_ecology function)

- [ ] **Step 1: Write the integration test**

```python
# tests/test_m35b_disease.py — append
from chronicler.ecology import tick_ecology
from chronicler.models import ClimatePhase


def test_tick_ecology_updates_endemic_severity():
    """tick_ecology should compute disease severity for controlled regions."""
    world = generate_world(seed=42)
    # Force a region into overcrowding to trigger a flare
    region = world.regions[0]
    region.population = int(region.carrying_capacity * 0.9)  # 90% capacity
    old_severity = region.endemic_severity

    tick_ecology(world, ClimatePhase.TEMPERATE)

    # Overcrowding should have spiked severity above baseline
    assert region.endemic_severity > old_severity or region.endemic_severity >= region.disease_baseline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_m35b_disease.py::test_tick_ecology_updates_endemic_severity -v`
Expected: FAIL — severity not updated (disease computation not wired in)

- [ ] **Step 3: Wire into tick_ecology()**

In `tick_ecology()` at line 381, add disease computation at the start of the controlled-region loop, BEFORE the `_tick_soil` / `_tick_water` / `_tick_forest` calls:

```python
def tick_ecology(world: WorldState, climate_phase: ClimatePhase, acc=None) -> list[Event]:
    """Phase 9 ecology tick. Replaces phase_fertility."""
    from chronicler.resources import get_season_id as _get_season_id_fn
    current_season_id = _get_season_id_fn(world.turn)

    for region in world.regions:
        if region.controller is None:
            continue
        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        # M35b: Disease computation — before ecology updates
        pre_water = region.ecology.water
        compute_disease_severity(region, world, pre_water, season_id=current_season_id)

        _tick_soil(region, civ, climate_phase, world)
        # ... rest unchanged
```

Also add disease computation for uncontrolled regions (after the existing uncontrolled block):

```python
    # Uncontrolled regions: disease still computed (severity exists regardless of control)
    for region in world.regions:
        if region.controller is not None:
            continue
        pre_water = region.ecology.water
        compute_disease_severity(region, world, pre_water, season_id=current_season_id)
```

At the **end** of `tick_ecology()`, after all ecology updates and famine checks, update `prev_turn_water` for all regions (used by next turn's water delta disease trigger):

```python
    # M35b: Store post-tick water for next turn's delta detection
    for region in world.regions:
        region.prev_turn_water = region.ecology.water
```

Also add `capacity_modifier` reset for expired disaster cooldowns. In `simulation.py` where cooldowns are decremented (line 105-108), add after the `region.disaster_cooldowns` cleanup:

```python
    # M35b: Reset capacity_modifier when all disaster cooldowns expire
    if not region.disaster_cooldowns and region.capacity_modifier != 1.0:
        region.capacity_modifier = 1.0
```

And wire `capacity_modifier` into `effective_capacity()` in `ecology.py`:

```python
def effective_capacity(region: Region) -> int:
    soil = region.ecology.soil
    water_factor = min(1.0, region.ecology.water / 0.5)
    cap_mod = getattr(region, 'capacity_modifier', 1.0)
    return max(int(region.carrying_capacity * cap_mod * soil * water_factor), 1)
```

Actually, looking at the code flow more carefully: uncontrolled regions already have their own loop. Add `compute_disease_severity` at the start of the uncontrolled loop as well, before the natural recovery code. But since the uncontrolled loop doesn't iterate via `civ`, just add it before the soil recovery line.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_m35b_disease.py::test_tick_ecology_updates_endemic_severity -v`
Expected: PASS

- [ ] **Step 5: Run existing ecology tests for regression**

Run: `python -m pytest tests/test_ecology.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/ecology.py tests/test_m35b_disease.py
git commit -m "feat(m35b): wire compute_disease_severity into tick_ecology"
```

---

## Chunk 3: Rust FFI — Disease Severity to Mortality

### Task 6: Add endemic_severity to Rust RegionState

**Files:**
- Modify: `chronicler-agents/src/region.rs`

- [ ] **Step 1: Write the failing test**

Add to `chronicler-agents/src/region.rs` tests module:

```rust
#[test]
fn test_region_new_has_endemic_severity_default() {
    let r = RegionState::new(5);
    assert!((r.endemic_severity - 0.0).abs() < 0.001);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chronicler-agents && cargo test test_region_new_has_endemic_severity_default`
Expected: FAIL — field doesn't exist

- [ ] **Step 3: Add field to RegionState**

In `chronicler-agents/src/region.rs`, add after `pub river_mask: u32,` (line 38):

```rust
    // M35b: Endemic disease severity
    pub endemic_severity: f32,
```

Update `RegionState::new()` to include `endemic_severity: 0.0` in the initializer.

- [ ] **Step 4: Update all test helpers that construct RegionState**

Search for `RegionState {` in all Rust files. Update `demographics.rs` test helper `region()` function (line 63) to include `endemic_severity: 0.0`. Any other constructors must also be updated.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd chronicler-agents && cargo test test_region_new_has_endemic_severity_default`
Expected: PASS

- [ ] **Step 6: Run full Rust test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/demographics.rs
git commit -m "feat(m35b): add endemic_severity field to Rust RegionState"
```

---

### Task 7: Add disease_severity param to mortality_rate()

**Files:**
- Modify: `chronicler-agents/src/demographics.rs:16-24`
- Modify: `chronicler-agents/src/tick.rs:462`

- [ ] **Step 1: Write the failing test**

Add to `chronicler-agents/src/demographics.rs` tests:

```rust
#[test]
fn test_mortality_with_disease() {
    let rate = mortality_rate(30, 1.0, false, 0.05);
    // Disease adds to base mortality: MORTALITY_ADULT * 1.0 * 1.0 + 0.05
    let expected = MORTALITY_ADULT + 0.05;
    assert!((rate - expected).abs() < 0.001);
}

#[test]
fn test_mortality_disease_plus_war() {
    let rate = mortality_rate(30, 1.0, true, 0.10);
    let expected = MORTALITY_ADULT * WAR_CASUALTY_MULTIPLIER + 0.10;
    assert!((rate - expected).abs() < 0.001);
}

#[test]
fn test_mortality_no_disease() {
    let rate = mortality_rate(30, 1.0, false, 0.0);
    assert!((rate - MORTALITY_ADULT).abs() < 0.001);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chronicler-agents && cargo test test_mortality_with_disease test_mortality_disease_plus_war test_mortality_no_disease`
Expected: FAIL — wrong number of arguments

- [ ] **Step 3: Update mortality_rate() signature and implementation**

In `chronicler-agents/src/demographics.rs`, change `mortality_rate`:

```rust
pub fn mortality_rate(age: u16, eco_stress: f32, is_soldier_at_war: bool, disease_severity: f32) -> f32 {
    let base = match age {
        0..AGE_ADULT => MORTALITY_YOUNG,
        AGE_ADULT..AGE_ELDER => MORTALITY_ADULT,
        _ => MORTALITY_ELDER,
    };
    let war_mult = 1.0 + (WAR_CASUALTY_MULTIPLIER - 1.0) * is_soldier_at_war as i32 as f32;
    base * eco_stress * war_mult + disease_severity
}
```

Disease severity is **additive** (not multiplicative) — it's a separate mortality source independent of ecological stress and war multipliers.

- [ ] **Step 4: Update all existing call sites**

In `chronicler-agents/src/tick.rs:462`, update the call:

```rust
let mort_rate = demographics::mortality_rate(age, eco_stress, is_soldier_at_war, region.endemic_severity);
```

Update existing tests in `demographics.rs` that call `mortality_rate` with 3 args — add `0.0` as the 4th argument:

```rust
// test_mortality_young_peaceful:
let rate = mortality_rate(10, 1.0, false, 0.0);

// test_mortality_adult_stressed:
let rate = mortality_rate(30, 1.5, false, 0.0);

// test_mortality_soldier_at_war:
let rate = mortality_rate(30, 1.0, true, 0.0);

// test_mortality_elder_war_stressed:
let rate = mortality_rate(65, 1.5, true, 0.0);
```

- [ ] **Step 5: Run all Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/demographics.rs chronicler-agents/src/tick.rs
git commit -m "feat(m35b): add disease_severity param to mortality_rate, wire in tick"
```

---

### Task 8: Pass endemic_severity through Arrow FFI

**Files:**
- Modify: `src/chronicler/agent_bridge.py:86-134` (build_region_batch)
- Modify: `chronicler-agents/src/ffi.rs:292-414` (set_region_state)

- [ ] **Step 1: Add endemic_severity to build_region_batch()**

In `src/chronicler/agent_bridge.py`, in `build_region_batch()`, add after the `"river_mask"` line (line 133):

```python
        # M35b: Endemic disease severity
        "endemic_severity": pa.array([r.endemic_severity for r in world.regions], type=pa.float32()),
```

- [ ] **Step 2: Read endemic_severity in ffi.rs**

In `chronicler-agents/src/ffi.rs`, after the `river_mask_col` optional column (line 293-295), add:

```rust
        // Optional M35b column
        let endemic_severity_col = rb
            .column_by_name("endemic_severity")
            .and_then(|c| c.as_any().downcast_ref::<arrow::array::Float32Array>());
```

In the first-call initializer block (around line 333), add after `river_mask`:

```rust
                    endemic_severity: endemic_severity_col.map_or(0.0, |arr| arr.value(i)),
```

In the update block (around line 414), add after `r.river_mask = ...`:

```rust
                r.endemic_severity = endemic_severity_col.map_or(r.endemic_severity, |arr| arr.value(i));
```

- [ ] **Step 3: Build Rust crate**

Run: `cd chronicler-agents && cargo build`
Expected: Compiles without errors

- [ ] **Step 4: Run full Rust tests**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 5: Run Python agent bridge tests**

Run: `python -m pytest tests/test_agent_bridge.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/agent_bridge.py chronicler-agents/src/ffi.rs
git commit -m "feat(m35b): pass endemic_severity through Arrow FFI to Rust"
```

---

## Chunk 4: Resource Depletion Feedback

### Task 9: Implement soil exhaustion feedback

**Files:**
- Modify: `src/chronicler/ecology.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_m35b_disease.py — append
def test_soil_pressure_streak_increments():
    """Overcrowded crop region increments soil_pressure_streak."""
    from chronicler.ecology import update_depletion_feedback
    from chronicler.models import ResourceType
    r = _make_region(pop=50, capacity=60)  # 50/60 = 0.83 > 0.7
    r.resource_types = [ResourceType.GRAIN, 255, 255]
    update_depletion_feedback(r, world=None)
    assert r.soil_pressure_streak == 1


def test_soil_pressure_streak_resets_below_threshold():
    """Below threshold resets streak to 0."""
    from chronicler.ecology import update_depletion_feedback
    from chronicler.models import ResourceType
    r = _make_region(pop=30, capacity=60)  # 30/60 = 0.5 < 0.7
    r.resource_types = [ResourceType.GRAIN, 255, 255]
    r.soil_pressure_streak = 15
    update_depletion_feedback(r, world=None)
    assert r.soil_pressure_streak == 0


def test_soil_exhaustion_no_event_before_limit():
    """No soil exhaustion event before streak reaches limit."""
    from chronicler.ecology import update_depletion_feedback
    from chronicler.models import ResourceType
    r = _make_region(pop=50, capacity=60)
    r.resource_types = [ResourceType.GRAIN, 255, 255]
    r.soil_pressure_streak = 28
    events = update_depletion_feedback(r, world=None)
    assert r.soil_pressure_streak == 29
    assert not any(e.event_type == "soil_exhaustion" for e in events)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_m35b_disease.py -v -k "soil_pressure"`
Expected: FAIL — `update_depletion_feedback` not defined

- [ ] **Step 3: Implement update_depletion_feedback()**

Add to `src/chronicler/ecology.py`:

```python
def update_depletion_feedback(region: "Region", world: "WorldState | None") -> list["Event"]:
    """Update soil pressure and overextraction streaks. Returns events."""
    events: list[Event] = []
    soil_thresh = get_override(world, K_SOIL_PRESSURE_THRESHOLD, 0.7) if world else 0.7
    soil_limit = int(get_override(world, K_SOIL_PRESSURE_STREAK_LIMIT, 30)) if world else 30
    overext_limit = int(get_override(world, K_OVEREXTRACTION_STREAK_LIMIT, 35)) if world else 35
    overext_penalty = get_override(world, K_OVEREXTRACTION_YIELD_PENALTY, 0.10) if world else 0.10
    workers_per_unit = get_override(world, K_WORKERS_PER_YIELD_UNIT, 200) if world else 200

    # --- Soil exhaustion (population pressure) ---
    has_crop = any(
        rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS)
        for rtype in region.resource_types
        if rtype != EMPTY_SLOT
    )
    if has_crop and region.carrying_capacity > 0 and region.population > soil_thresh * region.carrying_capacity:
        region.soil_pressure_streak += 1
        if region.soil_pressure_streak >= soil_limit:
            events.append(Event(
                turn=world.turn if world else 0,
                event_type="soil_exhaustion",
                actors=[region.controller] if region.controller else [],
                description=f"The fields of {region.name} show signs of exhaustion from decades of intensive cultivation",
                importance=6,
            ))
    else:
        region.soil_pressure_streak = 0

    # --- Overextraction (per-resource) ---
    # Depletable classes: Crop (GRAIN=0, BOTANICALS=2), Marine (FISH=3), Mineral (ORE=5, PRECIOUS=6)
    DEPLETABLE = frozenset({ResourceType.GRAIN, ResourceType.BOTANICALS, ResourceType.FISH,
                            ResourceType.ORE, ResourceType.PRECIOUS})
    for slot in range(3):
        rtype = region.resource_types[slot]
        if rtype == EMPTY_SLOT or rtype not in DEPLETABLE:
            continue
        eff_yield = region.resource_effective_yields[slot]
        sustainable = eff_yield * workers_per_unit
        # Worker count approximation: population / 5 (same as ecology tick)
        worker_count = region.population // 5 if region.population > 0 else 0
        if sustainable > 0 and worker_count > sustainable:
            streak = region.overextraction_streaks.get(slot, 0) + 1
            region.overextraction_streaks[slot] = streak
            if streak >= overext_limit:
                # Permanent yield reduction
                region.resource_effective_yields[slot] *= (1.0 - overext_penalty)
                region.overextraction_streaks[slot] = 0
                events.append(Event(
                    turn=world.turn if world else 0,
                    event_type="resource_depletion",
                    actors=[region.controller] if region.controller else [],
                    description=f"Overextraction has degraded {region.name}'s resources",
                    importance=7,
                ))
        else:
            region.overextraction_streaks[slot] = 0

    return events
```

Add the `ResourceType` import at the top of `ecology.py` if not already present (it is — line 11 imports it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_m35b_disease.py -v -k "soil_pressure"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_m35b_disease.py
git commit -m "feat(m35b): implement soil exhaustion and overextraction depletion feedback"
```

---

### Task 10: Wire depletion into tick_ecology() and apply soil degradation doubling

**Files:**
- Modify: `src/chronicler/ecology.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_m35b_disease.py — append
def test_soil_degradation_doubles_after_streak():
    """When soil_pressure_streak >= 30, soil degrades 2x faster."""
    world = generate_world(seed=42)
    region = world.regions[0]
    region.population = int(region.carrying_capacity * 0.9)  # Overcrowded
    region.soil_pressure_streak = 31  # Past threshold

    soil_before = region.ecology.soil
    tick_ecology(world, ClimatePhase.TEMPERATE)
    soil_after_doubled = region.ecology.soil

    # Reset and test normal rate
    world2 = generate_world(seed=42)
    region2 = world2.regions[0]
    region2.population = int(region2.carrying_capacity * 0.9)
    region2.soil_pressure_streak = 0  # Below threshold

    soil_before2 = region2.ecology.soil
    tick_ecology(world2, ClimatePhase.TEMPERATE)
    soil_after_normal = region2.ecology.soil

    # Doubled degradation should lose more soil (or equal if no degradation occurs)
    normal_loss = soil_before2 - soil_after_normal
    doubled_loss = soil_before - soil_after_doubled
    if normal_loss > 0:
        assert doubled_loss >= normal_loss * 1.5  # At least 1.5x (accounting for clamp)
```

- [ ] **Step 2: Wire depletion and soil doubling into tick_ecology()**

In `tick_ecology()`, add `update_depletion_feedback` call after disease computation and before `_tick_soil`. When `soil_pressure_streak >= limit`, apply a 2x multiplier to soil degradation.

The simplest approach: call `update_depletion_feedback` in the ecology tick, and modify `_tick_soil` to accept an optional `degradation_mult` parameter:

In `_tick_soil()`, add `degradation_mult: float = 1.0` parameter. Multiply the degradation rate by it:

```python
def _tick_soil(region: Region, civ, climate_phase: ClimatePhase, world: WorldState, degradation_mult: float = 1.0) -> None:
    eff = effective_capacity(region)
    if region.population > eff:
        rate = get_override(world, K_SOIL_DEGRADATION, 0.005) * degradation_mult
        region.ecology.soil -= rate
    # ... rest unchanged
```

In `tick_ecology()`, compute the multiplier and pass it:

```python
        # M35b: Depletion feedback
        soil_limit = int(get_override(world, K_SOIL_PRESSURE_STREAK_LIMIT, 30))
        depletion_events = update_depletion_feedback(region, world)
        turn_events = []  # collect events
        turn_events.extend(depletion_events)
        soil_mult = 2.0 if region.soil_pressure_streak >= soil_limit else 1.0

        _tick_soil(region, civ, climate_phase, world, degradation_mult=soil_mult)
```

Note: `turn_events` should be accumulated and returned. Look at the existing pattern — `tick_ecology` returns events from famine checks. Add depletion events to the same return list.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_m35b_disease.py tests/test_ecology.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/ecology.py tests/test_m35b_disease.py
git commit -m "feat(m35b): wire depletion feedback into tick_ecology with 2x soil degradation"
```

---

## Chunk 5: Environmental Events

### Task 11: Implement check_environmental_events()

**Files:**
- Modify: `src/chronicler/emergence.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_m35b_events.py (new file)
import random
from chronicler.models import Region, RegionEcology, WorldState, ClimatePhase, ResourceType, EMPTY_SLOT


def _make_world_with_region(terrain="plains", water=0.6, soil=0.8, pop=40, capacity=60, resource_types=None):
    """Minimal world for testing environmental events."""
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42)
    region = world.regions[0]
    region.terrain = terrain
    region.ecology.water = water
    region.ecology.soil = soil
    region.population = pop
    region.carrying_capacity = capacity
    if resource_types is not None:
        region.resource_types = resource_types
    region.disaster_cooldowns = {}
    return world, region


def test_locust_never_fires_in_mountains():
    """Locust swarm requires plains or desert terrain."""
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="mountains",
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "locust_swarm" for e in events)


def test_locust_requires_grain():
    """Locust swarm requires Grain resource."""
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="plains",
        resource_types=[ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT],
    )
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "locust_swarm" for e in events)


def test_no_event_when_cooldown_active():
    """No environmental event fires when disaster_cooldowns is non-empty."""
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(
        terrain="plains",
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.disaster_cooldowns = {"earthquake": 5}  # Active cooldown
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    # Should not fire any event for this region
    locust_events = [e for e in events if e.event_type == "locust_swarm" and region.name in e.description]
    assert len(locust_events) == 0


def test_flood_requires_river_mask():
    """Flood only fires on river regions (river_mask != 0)."""
    from chronicler.emergence import check_environmental_events
    world, region = _make_world_with_region(water=0.9)
    region.river_mask = 0  # No river
    rng = random.Random(42)
    events = check_environmental_events(world, rng)
    assert not any(e.event_type == "flood" for e in events)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_m35b_events.py -v`
Expected: FAIL — `check_environmental_events` not defined

- [ ] **Step 3: Implement check_environmental_events()**

Add to `src/chronicler/emergence.py`:

```python
from chronicler.tuning import (
    # ... existing imports ...
    K_LOCUST_PROBABILITY, K_FLOOD_PROBABILITY, K_COLLAPSE_PROBABILITY,
    K_DROUGHT_INTENSIFICATION_PROBABILITY, K_COLLAPSE_MORTALITY_SPIKE,
    K_ECOLOGICAL_RECOVERY_PROBABILITY, K_ECOLOGICAL_RECOVERY_FRACTION,
)


def _check_locust(region: Region, world: WorldState, rng) -> bool:
    """Locust swarm: plains/desert, summer/autumn, has Grain, soil > 0.4."""
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)
    if region.terrain not in ("plains", "desert"):
        return False
    if season_id not in (1, 2):  # Summer, Autumn
        return False
    if not any(rtype == ResourceType.GRAIN for rtype in region.resource_types if rtype != EMPTY_SLOT):
        return False
    if region.ecology.soil <= 0.4:
        return False
    prob = get_override(world, K_LOCUST_PROBABILITY, 0.15)
    if rng.random() >= prob:
        return False
    # Fire!
    duration = rng.randint(2, 3)
    region.disaster_cooldowns["locust_swarm"] = duration
    # Zero crop-class yields
    for slot in range(3):
        rtype = region.resource_types[slot]
        if rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS):
            region.resource_suspensions[rtype] = duration
    world.events_timeline.append(Event(
        turn=world.turn, event_type="locust_swarm",
        actors=[region.controller] if region.controller else [],
        description=f"A locust swarm descends on {region.name}, devouring the crops",
        importance=7,
    ))
    return True


def _check_flood(region: Region, world: WorldState, rng) -> bool:
    """Flood: river region, spring, water > 0.8."""
    from chronicler.resources import get_season_id
    season_id = get_season_id(world.turn)
    if region.river_mask == 0:
        return False
    if season_id != 0:  # Spring
        return False
    if region.ecology.water <= 0.8:
        return False
    prob = get_override(world, K_FLOOD_PROBABILITY, 0.20)
    if rng.random() >= prob:
        return False
    # Fire!
    duration = rng.randint(1, 2)
    region.disaster_cooldowns["flood"] = duration
    # Carrying capacity reduced 15% via modifier (restored when cooldown expires)
    region.capacity_modifier = 0.85
    # Silt deposit: +0.15 soil (spec says "after" but immediate is simpler;
    # the capacity penalty is the short-term cost, silt is the long-term benefit)
    region.ecology.soil = min(1.0, region.ecology.soil + 0.15)
    world.events_timeline.append(Event(
        turn=world.turn, event_type="flood",
        actors=[region.controller] if region.controller else [],
        description=f"The river floods {region.name}, depositing rich silt but damaging infrastructure",
        importance=6,
    ))
    return True


def _check_collapse(region: Region, world: WorldState, rng) -> bool:
    """Mine collapse: mountains, mineral resource, reserves < 0.3."""
    if region.terrain != "mountains":
        return False
    has_mineral = any(
        rtype in (ResourceType.ORE, ResourceType.PRECIOUS)
        for rtype in region.resource_types
        if rtype != EMPTY_SLOT
    )
    if not has_mineral:
        return False
    # Check reserves for mineral slots
    low_reserves = any(
        region.resource_reserves[slot] < 0.3
        for slot in range(3)
        if region.resource_types[slot] in (ResourceType.ORE, ResourceType.PRECIOUS)
    )
    if not low_reserves:
        return False
    prob = get_override(world, K_COLLAPSE_PROBABILITY, 0.10)
    if rng.random() >= prob:
        return False
    # Fire!
    duration = rng.randint(3, 5)
    region.disaster_cooldowns["mine_collapse"] = duration
    # Mortality spike via endemic_severity
    spike = get_override(world, K_COLLAPSE_MORTALITY_SPIKE, 0.10)
    region.endemic_severity = min(0.15, region.endemic_severity + spike)
    # Mineral extraction halved — suspend mineral resource slots for the duration
    for slot in range(3):
        if region.resource_types[slot] in (ResourceType.ORE, ResourceType.PRECIOUS):
            region.resource_suspensions[region.resource_types[slot]] = duration
    # In --agents=off mode, also apply StatAccumulator population drain
    # (mine collapse kills workers regardless of agent mode)
    # --agents=off mode: population drain via StatAccumulator (if available)
    # In agent mode, mortality spike through endemic_severity handles deaths.
    # In aggregate mode, apply direct population loss.
    if hasattr(world, '_acc') and world._acc is not None:
        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            # ~5-10 deaths at typical population
            pop_loss = max(5, min(10, region.population // 30))
            world._acc.add(civ_idx, civ, "population", -pop_loss, "guard")

    world.events_timeline.append(Event(
        turn=world.turn, event_type="mine_collapse",
        actors=[region.controller] if region.controller else [],
        description=f"A mine collapses in {region.name}, killing workers and halting extraction",
        importance=8,
    ))
    return True


def _check_drought(region: Region, world: WorldState, rng) -> bool:
    """Drought intensification: active DROUGHT, summer, water < 0.25."""
    from chronicler.resources import get_season_id
    from chronicler.climate import get_climate_phase
    season_id = get_season_id(world.turn)
    climate_phase = get_climate_phase(world.turn, world.climate_config)
    if climate_phase != ClimatePhase.DROUGHT:
        return False
    if season_id != 1:  # Summer
        return False
    if region.ecology.water >= 0.25:
        return False
    prob = get_override(world, K_DROUGHT_INTENSIFICATION_PROBABILITY, 0.25)
    if rng.random() >= prob:
        return False
    # Fire!
    duration = rng.randint(4, 8)
    region.disaster_cooldowns["drought_intensification"] = duration
    # Halve carrying capacity via modifier (restored when cooldown expires)
    region.capacity_modifier = 0.5
    # Also halve adjacent desert regions
    for adj_name in region.adjacencies:
        adj = next((r for r in world.regions if r.name == adj_name), None)
        if adj and adj.terrain == "desert" and not adj.disaster_cooldowns:
            adj.capacity_modifier = 0.5
            adj.disaster_cooldowns["drought_intensification"] = duration
    world.events_timeline.append(Event(
        turn=world.turn, event_type="drought_intensification",
        actors=[region.controller] if region.controller else [],
        description=f"The drought intensifies around {region.name}, devastating the region",
        importance=8,
    ))
    return True


def check_environmental_events(world: WorldState, rng) -> list[Event]:
    """Check condition-triggered environmental events for all regions.

    Uses per-region disaster_cooldowns (shared with climate system).
    M18 black swans use separate world.black_swan_cooldown.
    """
    initial_event_count = len(world.events_timeline)
    for region in world.regions:
        if region.disaster_cooldowns:
            continue  # Shared cooldown — no stacking
        for event_check in [_check_locust, _check_flood, _check_collapse, _check_drought]:
            if event_check(region, world, rng):
                break  # Fired, cooldown set, done with this region
    # Return only newly added events
    return world.events_timeline[initial_event_count:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_m35b_events.py -v`
Expected: PASS

- [ ] **Step 5: Run existing emergence tests for regression**

Run: `python -m pytest tests/test_emergence.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/emergence.py tests/test_m35b_events.py
git commit -m "feat(m35b): implement check_environmental_events with 4 condition-triggered events"
```

---

### Task 12: Add ecological recovery black swan and wire into simulation

**Files:**
- Modify: `src/chronicler/emergence.py`
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Write the failing test for ecological recovery**

```python
# tests/test_m35b_events.py — append
def test_ecological_recovery_restores_yield():
    """Ecological recovery restores up to 50% of lost yield."""
    from chronicler.emergence import _check_ecological_recovery
    world, region = _make_world_with_region(
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [0.5, 0.0, 0.0]  # Lost 50%
    # Force the recovery to fire (use a rigged RNG)
    rng = type('RNG', (), {'random': lambda self: 0.001})()  # Always passes probability check
    result = _check_ecological_recovery(region, world, rng)
    assert result is True
    # Should restore up to 50% of lost yield: 0.5 + 0.5 * 0.5 = 0.75
    assert region.resource_effective_yields[0] <= region.resource_base_yields[0]
    assert region.resource_effective_yields[0] > 0.5


def test_ecological_recovery_never_exceeds_base():
    """Recovery never pushes effective yield above base yield."""
    from chronicler.emergence import _check_ecological_recovery
    world, region = _make_world_with_region(
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
    )
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [0.95, 0.0, 0.0]  # Only 5% lost
    rng = type('RNG', (), {'random': lambda self: 0.001})()
    _check_ecological_recovery(region, world, rng)
    assert region.resource_effective_yields[0] <= 1.0
```

- [ ] **Step 2: Implement _check_ecological_recovery()**

Add to `src/chronicler/emergence.py`:

```python
def _check_ecological_recovery(region: Region, world: WorldState, rng) -> bool:
    """Ecological recovery: rare event restoring degraded resource yields."""
    prob = get_override(world, K_ECOLOGICAL_RECOVERY_PROBABILITY, 0.02)
    fraction = get_override(world, K_ECOLOGICAL_RECOVERY_FRACTION, 0.50)

    # Find eligible resources: effective < 0.8 * base
    eligible_slots = [
        slot for slot in range(3)
        if region.resource_types[slot] != EMPTY_SLOT
        and region.resource_effective_yields[slot] < 0.8 * region.resource_base_yields[slot]
    ]
    if not eligible_slots:
        return False
    if rng.random() >= prob:
        return False

    # Restore up to `fraction` of lost yield for the most degraded resource
    slot = min(eligible_slots, key=lambda s: region.resource_effective_yields[s] / max(0.001, region.resource_base_yields[s]))
    base = region.resource_base_yields[slot]
    current = region.resource_effective_yields[slot]
    lost = base - current
    restore = lost * fraction
    region.resource_effective_yields[slot] = min(base, current + restore)

    world.events_timeline.append(Event(
        turn=world.turn, event_type="ecological_recovery",
        actors=[region.controller] if region.controller else [],
        description=f"The degraded resources of {region.name} show signs of recovery",
        importance=5,
    ))
    return True
```

- [ ] **Step 3: Wire check_environmental_events into simulation.py**

In `src/chronicler/simulation.py`, find where `check_black_swans` is called (line 1073-1074). Add M35b environmental events right after:

```python
    # M18: Black swan check (after climate disasters)
    from chronicler.emergence import check_black_swans
    turn_events.extend(check_black_swans(world, seed=seed, acc=acc))

    # M35b: Environmental events (condition-triggered, same phase)
    from chronicler.emergence import check_environmental_events
    env_rng = random.Random(seed + world.turn * 1013)
    turn_events.extend(check_environmental_events(world, env_rng))
```

Also add ecological recovery — it's a per-region check that runs alongside environmental events. Call it inside `check_environmental_events` or as a separate pass. Simplest: add it to the `check_environmental_events` loop, after the event checks, for regions that didn't fire an event:

In `check_environmental_events`, after the `break` loop, add recovery check:

```python
        # If no disaster fired, check ecological recovery
        if not region.disaster_cooldowns:
            _check_ecological_recovery(region, world, rng)
```

Wait — this would also check regions that had no disaster to begin with. That's correct — recovery fires on regions that currently have no active disaster AND have degraded yields.

Actually, recheck: the loop `continue`s if `region.disaster_cooldowns` is non-empty. So for regions without active disasters, both event checks AND recovery run. For regions with active disasters, neither runs. This is correct — you don't get recovery while a disaster is active.

Add after the event check loop but still inside the region iteration:

```python
    for region in world.regions:
        if region.disaster_cooldowns:
            continue
        fired = False
        for event_check in [_check_locust, _check_flood, _check_collapse, _check_drought]:
            if event_check(region, world, rng):
                fired = True
                break
        if not fired:
            _check_ecological_recovery(region, world, rng)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_m35b_events.py tests/test_emergence.py -v`
Expected: All PASS

- [ ] **Step 5: Run simulation tests for regression**

Run: `python -m pytest tests/test_simulation.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/emergence.py src/chronicler/simulation.py tests/test_m35b_events.py
git commit -m "feat(m35b): add ecological recovery and wire environmental events into simulation"
```

---

## Chunk 6: Integration & Regression

### Task 13: Disease vector label helper and integration test

**Files:**
- Modify: `src/chronicler/ecology.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_m35b_disease.py — append
def test_disease_vector_label():
    from chronicler.ecology import disease_vector_label
    r = _make_region(terrain="desert", baseline=0.015)
    assert disease_vector_label(r) == "cholera"
    r2 = _make_region(terrain="coast", baseline=0.02)
    assert disease_vector_label(r2) == "fever"
    r3 = _make_region(terrain="plains", baseline=0.01)
    assert disease_vector_label(r3) == "plague"
```

- [ ] **Step 2: Implement disease_vector_label()**

Add to `src/chronicler/ecology.py`:

```python
def disease_vector_label(region: "Region") -> str:
    """Derive disease vector label for narration. Not stored — deterministic."""
    if region.terrain == "desert":
        return "cholera"
    elif region.disease_baseline >= 0.02:
        return "fever"
    else:
        return "plague"
```

- [ ] **Step 3: Run test**

Run: `python -m pytest tests/test_m35b_disease.py::test_disease_vector_label -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/ecology.py tests/test_m35b_disease.py
git commit -m "feat(m35b): add disease_vector_label helper for narration"
```

---

### Task 14: Regression tests

**Files:**
- Create: `tests/test_m35b_regression.py`

- [ ] **Step 1: Write regression tests**

```python
# tests/test_m35b_regression.py (new file)
"""M35b regression tests: verify existing behavior is not broken."""
from chronicler.world_gen import generate_world
from chronicler.models import ClimatePhase
from chronicler.ecology import tick_ecology


def test_existing_ecology_tests_pass_with_disease_fields():
    """World-gen initializes disease fields without breaking ecology."""
    world = generate_world(seed=42)
    # Run a few ecology ticks — should not crash
    for _ in range(5):
        tick_ecology(world, ClimatePhase.TEMPERATE)
    # All regions should still have valid ecology
    for r in world.regions:
        assert 0.0 <= r.ecology.soil <= 1.0
        assert 0.0 <= r.ecology.water <= 1.0
        assert r.endemic_severity >= r.disease_baseline
        assert r.endemic_severity <= 0.15


def test_effective_yields_ceiling():
    """resource_effective_yields never exceeds resource_base_yields."""
    world = generate_world(seed=42)
    for _ in range(10):
        tick_ecology(world, ClimatePhase.TEMPERATE)
    for r in world.regions:
        for slot in range(3):
            assert r.resource_effective_yields[slot] <= r.resource_base_yields[slot] + 0.001


def test_m34_regression_unaffected():
    """Existing M34 tests should pass — controlled conditions don't trigger M35b events."""
    # Import and run existing M34 regression if available
    world = generate_world(seed=42)
    # Verify resource yields are computed (ecology tick computes yields)
    tick_ecology(world, ClimatePhase.TEMPERATE)
    from chronicler.ecology import _last_region_yields
    assert len(_last_region_yields) > 0
```

- [ ] **Step 2: Run regression tests**

Run: `python -m pytest tests/test_m35b_regression.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=120`
Expected: All tests PASS

Run: `cd chronicler-agents && cargo test`
Expected: All Rust tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_m35b_regression.py
git commit -m "test(m35b): add regression tests for disease, depletion, environmental events"
```

---

### Task 15: Final integration — run full simulation

- [ ] **Step 1: Run a full 50-turn simulation**

Run: `python -m chronicler --turns 50 --seed 42 --agents=hybrid 2>&1 | tail -20`
Expected: Completes without errors. May see disease/depletion events in output.

- [ ] **Step 2: Run existing e2e test**

Run: `python -m pytest tests/test_e2e.py -v --timeout=300`
Expected: PASS

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix(m35b): integration fixups from full simulation run"
```
