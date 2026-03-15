# M23: Coupled Ecology Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single `fertility: float` on Region with a three-variable coupled ecology system (soil, water, forest_cover) that produces discrete threshold-crossing events for the narrator pipeline.

**Architecture:** New `ecology.py` module owns the entire system: `RegionEcology` terrain defaults/caps, `effective_capacity`, pressure-gated recovery, and the per-turn `tick_ecology` orchestrator. All callers of `terrain.effective_capacity` migrate to `ecology.effective_capacity`. Old `phase_fertility` in simulation.py is replaced by `tick_ecology`. M18 terrain succession migrates from fertility-keyed to forest-keyed triggers.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-15-m23-coupled-ecology-design.md`

### Implementation Notes (from plan review)

1. **Task 9 — Circular import risk.** `_check_famine` imports `_get_civ`, `clamp`, `STAT_FLOOR` from simulation.py and `get_severity_multiplier` from emergence.py. Since simulation.py imports ecology.py, this creates a circular dependency. **Fix before implementation:** Extract `_get_civ`, `clamp`, `STAT_FLOOR` into `utils.py` (they're generic helpers), then import from there. Or pass `_get_civ` as a parameter.
2. **Task 10 — climate_phase recomputation.** Check whether `climate_phase` is already computed earlier in the turn loop and available as a local variable. If so, pass that instead of recomputing via `get_climate_phase`.
3. **Task 12 — Disaster tests are formula validation only.** The Step 1 tests just validate Python arithmetic, not the actual disaster code migration. Real validation comes from the existing climate/emergence test suites in Step 4. Don't count these as meaningful migration test coverage.
4. **Task 13 — _apply_transition water.** Forest→plains sets soil=0.5 and forest_cover=0.1 but does NOT touch water (spec says "water unchanged"). Do not accidentally reset water when implementing.
5. **Task 15 — Blast radius.** Run `grep -r "\.fertility" tests/` first to get the full list of sites before starting edits. Expect 50+ sites across 9+ test files.

---

## Chunk 1: Data Model Foundation

### Task 1: RegionEcology model and Region field swap

**Files:**
- Modify: `src/chronicler/models.py:121-143` (Region), `src/chronicler/models.py:27-31` (RegionEcology — new class)
- Test: `tests/test_ecology.py` (new file)

- [ ] **Step 1: Write failing tests for RegionEcology model**

```python
# tests/test_ecology.py
import pytest
from chronicler.models import RegionEcology, Region


class TestRegionEcologyModel:
    def test_defaults(self):
        eco = RegionEcology()
        assert eco.soil == 0.8
        assert eco.water == 0.6
        assert eco.forest_cover == 0.3

    def test_custom_values(self):
        eco = RegionEcology(soil=0.5, water=0.4, forest_cover=0.9)
        assert eco.soil == 0.5

    def test_soil_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(soil=1.5)
        with pytest.raises(Exception):
            RegionEcology(soil=-0.1)

    def test_water_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(water=1.5)

    def test_forest_cover_clamped_to_01(self):
        with pytest.raises(Exception):
            RegionEcology(forest_cover=-0.1)


class TestRegionEcologyField:
    def test_region_has_ecology(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert isinstance(r.ecology, RegionEcology)
        assert r.ecology.soil == 0.8

    def test_region_has_low_forest_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert r.low_forest_turns == 0

    def test_region_has_forest_regrowth_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=60, resources="fertile")
        assert r.forest_regrowth_turns == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py -v`
Expected: FAIL — `RegionEcology` not importable, `Region` has no `ecology` field

- [ ] **Step 3: Add RegionEcology model and update Region**

In `src/chronicler/models.py`, add `RegionEcology` class before the `Region` class (after the infrastructure models around line 110):

```python
class RegionEcology(BaseModel):
    soil: float = Field(default=0.8, ge=0.0, le=1.0)
    water: float = Field(default=0.6, ge=0.0, le=1.0)
    forest_cover: float = Field(default=0.3, ge=0.0, le=1.0)
```

In the `Region` class, replace the `fertility` and `low_fertility_turns` fields:

```python
# REMOVE these two lines:
#   fertility: float = Field(default=0.8, ge=0.0, le=1.0)
#   low_fertility_turns: int = 0  # M18: consecutive turns with fertility < 0.3

# ADD:
ecology: RegionEcology = Field(default_factory=RegionEcology)
low_forest_turns: int = 0
forest_regrowth_turns: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_ecology.py
git commit -m "feat(m23): add RegionEcology model, swap fertility→ecology on Region"
```

---

### Task 2: TurnSnapshot and TerrainTransitionRule migration

**Files:**
- Modify: `src/chronicler/models.py:434-453` (TurnSnapshot), `src/chronicler/models.py:321-326` (TerrainTransitionRule), `src/chronicler/models.py:370-377` (WorldState defaults)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.models import TurnSnapshot, WorldState


class TestTurnSnapshotEcology:
    def test_snapshot_has_ecology_field(self):
        snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
        assert snap.ecology == {}

    def test_snapshot_ecology_accepts_dict(self):
        snap = TurnSnapshot(
            turn=0, civ_stats={}, region_control={}, relationships={},
            ecology={"Plains": {"soil": 0.9, "water": 0.6, "forest_cover": 0.2}},
        )
        assert snap.ecology["Plains"]["soil"] == 0.9


class TestTerrainTransitionDefaults:
    def test_deforestation_rule_uses_low_forest(self):
        w = WorldState(name="T", seed=42)
        deforest = w.terrain_transition_rules[0]
        assert deforest.from_terrain == "forest"
        assert deforest.to_terrain == "plains"
        assert deforest.condition == "low_forest"

    def test_rewilding_rule_uses_forest_regrowth(self):
        w = WorldState(name="T", seed=42)
        rewild = w.terrain_transition_rules[1]
        assert rewild.from_terrain == "plains"
        assert rewild.to_terrain == "forest"
        assert rewild.condition == "forest_regrowth"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTurnSnapshotEcology tests/test_ecology.py::TestTerrainTransitionDefaults -v`
Expected: FAIL — TurnSnapshot has `fertility` not `ecology`, default conditions are `low_fertility`/`depopulated`

- [ ] **Step 3: Update TurnSnapshot and WorldState defaults**

In `TurnSnapshot`, replace `fertility: dict[str, float]` with:
```python
ecology: dict[str, dict[str, float]] = Field(default_factory=dict)
```

In `WorldState.terrain_transition_rules` default factory, change:
```python
terrain_transition_rules: list[TerrainTransitionRule] = Field(
    default_factory=lambda: [
        TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                              condition="low_forest", threshold_turns=50),
        TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                              condition="forest_regrowth", threshold_turns=100),
    ]
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_ecology.py
git commit -m "feat(m23): migrate TurnSnapshot to ecology dict, update transition rule defaults"
```

---

### Task 3: Tuning keys migration

**Files:**
- Modify: `src/chronicler/tuning.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.tuning import KNOWN_OVERRIDES


class TestEcologyTuningKeys:
    def test_old_fertility_keys_removed(self):
        assert "fertility.degradation_rate" not in KNOWN_OVERRIDES
        assert "fertility.recovery_rate" not in KNOWN_OVERRIDES
        assert "fertility.famine_threshold" not in KNOWN_OVERRIDES

    def test_ecology_keys_registered(self):
        expected = [
            "ecology.soil_degradation_rate",
            "ecology.soil_recovery_rate",
            "ecology.mine_soil_degradation_rate",
            "ecology.water_drought_rate",
            "ecology.water_recovery_rate",
            "ecology.forest_clearing_rate",
            "ecology.forest_regrowth_rate",
            "ecology.cooling_forest_damage_rate",
            "ecology.irrigation_water_bonus",
            "ecology.irrigation_drought_multiplier",
            "ecology.agriculture_soil_bonus",
            "ecology.mechanization_mine_multiplier",
            "ecology.famine_water_threshold",
        ]
        for key in expected:
            assert key in KNOWN_OVERRIDES, f"Missing tuning key: {key}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestEcologyTuningKeys -v`
Expected: FAIL — old keys still present, new keys missing

- [ ] **Step 3: Update tuning.py**

Remove the three `K_FERTILITY_*` constants and their entries in `KNOWN_OVERRIDES`. Add the new ecology constants:

```python
# Replace the "# Fertility" section with:

# Ecology
K_SOIL_DEGRADATION = "ecology.soil_degradation_rate"
K_SOIL_RECOVERY = "ecology.soil_recovery_rate"
K_MINE_SOIL_DEGRADATION = "ecology.mine_soil_degradation_rate"
K_WATER_DROUGHT = "ecology.water_drought_rate"
K_WATER_RECOVERY = "ecology.water_recovery_rate"
K_FOREST_CLEARING = "ecology.forest_clearing_rate"
K_FOREST_REGROWTH = "ecology.forest_regrowth_rate"
K_COOLING_FOREST_DAMAGE = "ecology.cooling_forest_damage_rate"
K_IRRIGATION_WATER_BONUS = "ecology.irrigation_water_bonus"
K_IRRIGATION_DROUGHT_MULT = "ecology.irrigation_drought_multiplier"
K_AGRICULTURE_SOIL_BONUS = "ecology.agriculture_soil_bonus"
K_MECHANIZATION_MINE_MULT = "ecology.mechanization_mine_multiplier"
K_FAMINE_WATER_THRESHOLD = "ecology.famine_water_threshold"
```

Update `KNOWN_OVERRIDES` to remove the three old keys and add the 13 new ones.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tuning.py tests/test_ecology.py
git commit -m "feat(m23): replace fertility tuning keys with 13 ecology keys"
```

---

## Chunk 2: ecology.py Core Module

### Task 4: Terrain defaults, caps, and effective_capacity

**Files:**
- Create: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import effective_capacity, TERRAIN_ECOLOGY_DEFAULTS, TERRAIN_ECOLOGY_CAPS
from chronicler.models import RegionEcology


class TestTerrainDefaults:
    def test_plains_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["plains"]
        assert eco.soil == 0.9
        assert eco.water == 0.6
        assert eco.forest_cover == 0.2

    def test_forest_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["forest"]
        assert eco.forest_cover == 0.9

    def test_desert_defaults(self):
        eco = TERRAIN_ECOLOGY_DEFAULTS["desert"]
        assert eco.soil == 0.2
        assert eco.water == 0.1
        assert eco.forest_cover == 0.05

    def test_all_six_terrains_present(self):
        assert set(TERRAIN_ECOLOGY_DEFAULTS.keys()) == {"plains", "forest", "mountains", "coast", "desert", "tundra"}


class TestTerrainCaps:
    def test_desert_caps(self):
        caps = TERRAIN_ECOLOGY_CAPS["desert"]
        assert caps["soil"] == 0.30
        assert caps["water"] == 0.20
        assert caps["forest_cover"] == 0.10

    def test_all_six_terrains_present(self):
        assert set(TERRAIN_ECOLOGY_CAPS.keys()) == {"plains", "forest", "mountains", "coast", "desert", "tundra"}


class TestEffectiveCapacity:
    def _region(self, soil=0.8, water=0.6, forest_cover=0.3, capacity=100):
        return Region(
            name="T", terrain="plains", carrying_capacity=capacity,
            resources="fertile",
            ecology=RegionEcology(soil=soil, water=water, forest_cover=forest_cover),
        )

    def test_full_soil_full_water(self):
        r = self._region(soil=1.0, water=1.0)
        assert effective_capacity(r) == 100

    def test_half_soil_full_water(self):
        r = self._region(soil=0.5, water=1.0)
        assert effective_capacity(r) == 50

    def test_full_soil_water_at_threshold(self):
        # water=0.5 → water_factor = min(1.0, 0.5/0.5) = 1.0
        r = self._region(soil=1.0, water=0.5)
        assert effective_capacity(r) == 100

    def test_full_soil_water_below_threshold(self):
        # water=0.25 → water_factor = min(1.0, 0.25/0.5) = 0.5
        r = self._region(soil=1.0, water=0.25)
        assert effective_capacity(r) == 50

    def test_floor_of_one(self):
        r = self._region(soil=0.05, water=0.10, capacity=1)
        assert effective_capacity(r) >= 1

    def test_combined_soil_and_water(self):
        # soil=0.5, water=0.25 → 100 * 0.5 * 0.5 = 25
        r = self._region(soil=0.5, water=0.25)
        assert effective_capacity(r) == 25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTerrainDefaults tests/test_ecology.py::TestTerrainCaps tests/test_ecology.py::TestEffectiveCapacity -v`
Expected: FAIL — ecology module doesn't exist

- [ ] **Step 3: Create ecology.py with defaults, caps, and effective_capacity**

```python
# src/chronicler/ecology.py
"""Coupled ecology system — three-variable tick replacing single fertility.

Public API: tick_ecology(), effective_capacity()
No state. All functions operate on WorldState/Region passed in.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from chronicler.models import ClimatePhase, Event, InfrastructureType, RegionEcology
from chronicler.tuning import (
    K_SOIL_DEGRADATION, K_SOIL_RECOVERY, K_MINE_SOIL_DEGRADATION,
    K_WATER_DROUGHT, K_WATER_RECOVERY,
    K_FOREST_CLEARING, K_FOREST_REGROWTH, K_COOLING_FOREST_DAMAGE,
    K_IRRIGATION_WATER_BONUS, K_IRRIGATION_DROUGHT_MULT,
    K_AGRICULTURE_SOIL_BONUS, K_MECHANIZATION_MINE_MULT,
    K_FAMINE_WATER_THRESHOLD,
    get_override,
)

if TYPE_CHECKING:
    from chronicler.models import Region, WorldState

# --- Terrain ecology tables ---

TERRAIN_ECOLOGY_DEFAULTS: dict[str, RegionEcology] = {
    "plains":    RegionEcology(soil=0.90, water=0.60, forest_cover=0.20),
    "forest":    RegionEcology(soil=0.70, water=0.70, forest_cover=0.90),
    "mountains": RegionEcology(soil=0.40, water=0.80, forest_cover=0.30),
    "coast":     RegionEcology(soil=0.70, water=0.80, forest_cover=0.30),
    "desert":    RegionEcology(soil=0.20, water=0.10, forest_cover=0.05),
    "tundra":    RegionEcology(soil=0.15, water=0.50, forest_cover=0.10),
}

TERRAIN_ECOLOGY_CAPS: dict[str, dict[str, float]] = {
    "plains":    {"soil": 0.95, "water": 0.70, "forest_cover": 0.40},
    "forest":    {"soil": 0.80, "water": 0.80, "forest_cover": 0.95},
    "mountains": {"soil": 0.50, "water": 0.90, "forest_cover": 0.40},
    "coast":     {"soil": 0.80, "water": 0.90, "forest_cover": 0.40},
    "desert":    {"soil": 0.30, "water": 0.20, "forest_cover": 0.10},
    "tundra":    {"soil": 0.20, "water": 0.60, "forest_cover": 0.15},
}

# Floors: soil 0.05, water 0.10, forest_cover 0.00
_FLOOR_SOIL = 0.05
_FLOOR_WATER = 0.10
_FLOOR_FOREST = 0.00


def effective_capacity(region: Region) -> int:
    """Single source of truth for region carrying capacity.

    Capacity = carrying_capacity * soil * water_factor.
    Water factor uses threshold model: constrains only below 0.5.
    Floor of 1 prevents division-by-zero.
    """
    soil = region.ecology.soil
    water_factor = min(1.0, region.ecology.water / 0.5)
    return max(int(region.carrying_capacity * soil * water_factor), 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestTerrainDefaults tests/test_ecology.py::TestTerrainCaps tests/test_ecology.py::TestEffectiveCapacity -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): ecology.py with terrain defaults, caps, effective_capacity"
```

---

### Task 5: Soil tick (degradation + recovery + agriculture)

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import _tick_soil, _pressure_multiplier


class TestPressureMultiplier:
    def _region(self, pop, soil=0.8, water=0.6, capacity=100):
        return Region(
            name="T", terrain="plains", carrying_capacity=capacity,
            resources="fertile", population=pop,
            ecology=RegionEcology(soil=soil, water=water, forest_cover=0.3),
        )

    def test_at_capacity(self):
        r = self._region(pop=80)  # eff_cap ~80
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(0.1, abs=0.05)  # floor

    def test_half_capacity(self):
        r = self._region(pop=40)  # eff_cap ~80
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(0.5, abs=0.05)

    def test_abandoned(self):
        r = self._region(pop=0)
        mult = _pressure_multiplier(r)
        assert mult == pytest.approx(1.0)


class TestTickSoil:
    def _setup(self, pop=90, soil=0.8, focus=None, has_mine=False):
        from chronicler.models import Infrastructure, Leader, Civilization
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=soil, water=0.6, forest_cover=0.3),
        )
        if has_mine:
            r.infrastructure.append(Infrastructure(
                type=InfrastructureType.MINES, builder_civ="TestCiv",
                built_turn=0, active=True,
            ))
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        if focus:
            civ.active_focus = focus
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_overpop_degrades_soil(self):
        r, civ, w = self._setup(pop=90, soil=0.8)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil < old_soil

    def test_underpop_recovers_soil(self):
        r, civ, w = self._setup(pop=10, soil=0.4)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil > old_soil

    def test_agriculture_bonus_recovery(self):
        r_agri, civ_agri, w_agri = self._setup(pop=10, soil=0.4, focus="agriculture")
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.4)
        _tick_soil(r_agri, civ_agri, ClimatePhase.TEMPERATE, w_agri)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        assert r_agri.ecology.soil > r_none.ecology.soil

    def test_mine_degrades_soil(self):
        r, civ, w = self._setup(pop=10, soil=0.8, has_mine=True)
        old_soil = r.ecology.soil
        _tick_soil(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.soil < old_soil

    def test_metallurgy_halves_mine_degradation(self):
        r_met, civ_met, w_met = self._setup(pop=10, soil=0.8, focus="metallurgy", has_mine=True)
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.8, has_mine=True)
        _tick_soil(r_met, civ_met, ClimatePhase.TEMPERATE, w_met)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        # Metallurgy should degrade less
        assert r_met.ecology.soil > r_none.ecology.soil

    def test_mechanization_doubles_mine_degradation(self):
        r_mech, civ_mech, w_mech = self._setup(pop=10, soil=0.8, focus="mechanization", has_mine=True)
        r_none, civ_none, w_none = self._setup(pop=10, soil=0.8, has_mine=True)
        _tick_soil(r_mech, civ_mech, ClimatePhase.TEMPERATE, w_mech)
        _tick_soil(r_none, civ_none, ClimatePhase.TEMPERATE, w_none)
        assert r_mech.ecology.soil < r_none.ecology.soil
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestPressureMultiplier tests/test_ecology.py::TestTickSoil -v`
Expected: FAIL — `_tick_soil` and `_pressure_multiplier` not defined

- [ ] **Step 3: Implement _pressure_multiplier and _tick_soil**

Add to `src/chronicler/ecology.py`:

```python
def _pressure_multiplier(region: Region) -> float:
    """Recovery scaling: high at low pop, 0.1 floor at capacity."""
    eff = effective_capacity(region)
    if eff <= 0:
        return 1.0
    return max(0.1, 1.0 - region.population / eff)


def _tick_soil(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    """Soil degradation from overpop/mines, recovery pressure-gated + agriculture."""
    eff = effective_capacity(region)

    # Degradation: overpopulation
    if region.population > eff:
        rate = get_override(world, K_SOIL_DEGRADATION, 0.005)
        region.ecology.soil -= rate

    # Degradation: active mines
    has_mine = any(
        i.type == InfrastructureType.MINES and i.active for i in region.infrastructure
    )
    if has_mine:
        mine_rate = get_override(world, K_MINE_SOIL_DEGRADATION, 0.03)
        if civ and civ.active_focus == "metallurgy":
            mine_rate *= 0.5
            world.events_timeline.append(Event(
                turn=world.turn, event_type="capability_metallurgy",
                actors=[civ.name],
                description=f"{civ.name} metallurgy reduces mine degradation",
                importance=1,
            ))
        elif civ and civ.active_focus == "mechanization":
            mine_rate *= get_override(world, K_MECHANIZATION_MINE_MULT, 2.0)
        region.ecology.soil -= mine_rate

    # Recovery: pressure-gated
    if region.population < eff * 0.75:
        rate = get_override(world, K_SOIL_RECOVERY, 0.05)
        rate *= _pressure_multiplier(region)
        # Agriculture bonus
        if civ and civ.active_focus == "agriculture":
            rate += get_override(world, K_AGRICULTURE_SOIL_BONUS, 0.02)
        region.ecology.soil += rate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestPressureMultiplier tests/test_ecology.py::TestTickSoil -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): _tick_soil with mine degradation, pressure-gated recovery, agriculture bonus"
```

---

### Task 6: Water tick (drought + irrigation + temperate recovery)

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import _tick_water


class TestTickWater:
    def _setup(self, pop=50, water=0.6, has_irrigation=False, phase=ClimatePhase.TEMPERATE):
        from chronicler.models import Infrastructure, Leader, Civilization
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.8, water=water, forest_cover=0.3),
        )
        if has_irrigation:
            r.infrastructure.append(Infrastructure(
                type=InfrastructureType.IRRIGATION, builder_civ="TestCiv",
                built_turn=0, active=True,
            ))
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_drought_degrades_water(self):
        r, civ, w = self._setup(water=0.6)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.DROUGHT, w)
        assert r.ecology.water < old

    def test_irrigation_amplifies_drought(self):
        r_irr, civ_irr, w_irr = self._setup(water=0.6, has_irrigation=True)
        r_dry, civ_dry, w_dry = self._setup(water=0.6)
        _tick_water(r_irr, civ_irr, ClimatePhase.DROUGHT, w_irr)
        _tick_water(r_dry, civ_dry, ClimatePhase.DROUGHT, w_dry)
        assert r_irr.ecology.water < r_dry.ecology.water

    def test_temperate_recovers_water(self):
        r, civ, w = self._setup(water=0.4)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.water > old

    def test_irrigation_bonus_recovery(self):
        r_irr, civ_irr, w_irr = self._setup(water=0.4, has_irrigation=True)
        r_dry, civ_dry, w_dry = self._setup(water=0.4)
        _tick_water(r_irr, civ_irr, ClimatePhase.TEMPERATE, w_irr)
        _tick_water(r_dry, civ_dry, ClimatePhase.TEMPERATE, w_dry)
        assert r_irr.ecology.water > r_dry.ecology.water

    def test_cooling_degrades_water(self):
        r, civ, w = self._setup(water=0.6)
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.COOLING, w)
        assert r.ecology.water < old

    def test_warming_tundra_melt_bonus(self):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="tundra", carrying_capacity=20,
            resources="barren", population=5, controller="TestCiv",
            ecology=RegionEcology(soil=0.15, water=0.4, forest_cover=0.1),
        )
        civ = Civilization(
            name="TestCiv", population=5, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.WARMING, w)
        assert r.ecology.water > old  # tundra gets +0.05 melt

    def test_warming_non_tundra_no_effect(self):
        r, civ, w = self._setup(water=0.6)  # plains terrain
        old = r.ecology.water
        _tick_water(r, civ, ClimatePhase.WARMING, w)
        assert r.ecology.water == old  # no water effect on non-tundra
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTickWater -v`
Expected: FAIL — `_tick_water` not defined

- [ ] **Step 3: Implement _tick_water**

Add to `src/chronicler/ecology.py`:

```python
def _tick_water(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    """Water degradation from drought/cooling, recovery from temperate + irrigation."""
    has_irrigation = any(
        i.type == InfrastructureType.IRRIGATION and i.active for i in region.infrastructure
    )

    # Degradation / phase effects
    if climate_phase == ClimatePhase.DROUGHT:
        rate = get_override(world, K_WATER_DROUGHT, 0.04)
        if has_irrigation:
            rate *= get_override(world, K_IRRIGATION_DROUGHT_MULT, 1.5)
        region.ecology.water -= rate
    elif climate_phase == ClimatePhase.COOLING:
        region.ecology.water -= 0.02
    elif climate_phase == ClimatePhase.WARMING:
        # Tundra melt: water bonus from thawing permafrost
        if region.terrain == "tundra":
            region.ecology.water += 0.05

    # Recovery
    if climate_phase == ClimatePhase.TEMPERATE:
        rate = get_override(world, K_WATER_RECOVERY, 0.03)
        rate *= _pressure_multiplier(region)
        region.ecology.water += rate

    # Irrigation bonus (always, not just temperate)
    if has_irrigation and climate_phase != ClimatePhase.DROUGHT:
        bonus = get_override(world, K_IRRIGATION_WATER_BONUS, 0.03)
        bonus *= _pressure_multiplier(region)
        region.ecology.water += bonus
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestTickWater -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): _tick_water with drought, irrigation trap, temperate recovery"
```

---

### Task 7: Forest tick (clearing + regrowth + water gate)

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import _tick_forest


class TestTickForest:
    def _setup(self, pop=60, forest=0.5, water=0.6, capacity=100, phase=ClimatePhase.TEMPERATE):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="forest", carrying_capacity=capacity,
            resources="timber", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.7, water=water, forest_cover=forest),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        return r, civ, w

    def test_high_pop_clears_forest(self):
        # pop=60, capacity=100 → 60 > 50 → clearing
        r, civ, w = self._setup(pop=60, forest=0.5)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover < old

    def test_low_pop_regrows_forest(self):
        r, civ, w = self._setup(pop=10, forest=0.5)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover > old

    def test_low_water_blocks_regrowth(self):
        r, civ, w = self._setup(pop=10, forest=0.5, water=0.2)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.TEMPERATE, w)
        assert r.ecology.forest_cover == old  # no regrowth

    def test_cooling_damages_forest(self):
        r, civ, w = self._setup(pop=10, forest=0.5)
        old = r.ecology.forest_cover
        _tick_forest(r, civ, ClimatePhase.COOLING, w)
        # Cooling does frost damage, but also allows regrowth if pop low
        # Net effect depends on rates, but frost damage should reduce vs temperate
        r2, civ2, w2 = self._setup(pop=10, forest=0.5)
        _tick_forest(r2, civ2, ClimatePhase.TEMPERATE, w2)
        assert r.ecology.forest_cover < r2.ecology.forest_cover
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTickForest -v`
Expected: FAIL — `_tick_forest` not defined

- [ ] **Step 3: Implement _tick_forest**

Add to `src/chronicler/ecology.py`:

```python
def _tick_forest(region: Region, civ, climate_phase: ClimatePhase, world: WorldState) -> None:
    """Forest clearing from pop pressure, regrowth gated by water."""
    # Degradation: population clearing
    if region.population > region.carrying_capacity * 0.5:
        rate = get_override(world, K_FOREST_CLEARING, 0.02)
        region.ecology.forest_cover -= rate

    # Degradation: cooling frost damage (new behavior)
    if climate_phase == ClimatePhase.COOLING:
        region.ecology.forest_cover -= get_override(world, K_COOLING_FOREST_DAMAGE, 0.01)

    # Recovery: natural regrowth (gated by water and pop)
    if region.population < region.carrying_capacity * 0.5 and region.ecology.water >= 0.3:
        rate = get_override(world, K_FOREST_REGROWTH, 0.01)
        rate *= _pressure_multiplier(region)
        region.ecology.forest_cover += rate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestTickForest -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): _tick_forest with pop clearing, water gate, cooling frost"
```

---

### Task 8: Cross-effects and clamping

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import _apply_cross_effects, _clamp_ecology


class TestCrossEffects:
    def test_forest_provides_soil_bonus(self):
        r = Region(
            name="T", terrain="forest", carrying_capacity=100,
            resources="timber", population=0,
            ecology=RegionEcology(soil=0.5, water=0.6, forest_cover=0.6),
        )
        old_soil = r.ecology.soil
        _apply_cross_effects(r)
        assert r.ecology.soil > old_soil  # +0.01 bonus

    def test_low_forest_no_soil_bonus(self):
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=0,
            ecology=RegionEcology(soil=0.5, water=0.6, forest_cover=0.3),
        )
        old_soil = r.ecology.soil
        _apply_cross_effects(r)
        assert r.ecology.soil == old_soil  # no bonus below 0.5


class TestClampEcology:
    def test_soil_floor(self):
        r = Region(
            name="T", terrain="desert", carrying_capacity=30,
            resources="barren",
            ecology=RegionEcology(soil=0.01, water=0.10, forest_cover=0.0),
        )
        _clamp_ecology(r)
        assert r.ecology.soil == 0.05

    def test_water_floor(self):
        r = Region(
            name="T", terrain="desert", carrying_capacity=30,
            resources="barren",
            ecology=RegionEcology(soil=0.20, water=0.02, forest_cover=0.0),
        )
        _clamp_ecology(r)
        assert r.ecology.water == 0.10

    def test_forest_floor_is_zero(self):
        r = Region(
            name="T", terrain="desert", carrying_capacity=30,
            resources="barren",
            ecology=RegionEcology(soil=0.20, water=0.10, forest_cover=0.0),
        )
        _clamp_ecology(r)
        assert r.ecology.forest_cover == 0.0  # no floor for forest

    def test_terrain_caps_enforced(self):
        r = Region(
            name="T", terrain="desert", carrying_capacity=30,
            resources="barren",
            ecology=RegionEcology(soil=0.50, water=0.50, forest_cover=0.50),
        )
        _clamp_ecology(r)
        assert r.ecology.soil == 0.30  # desert cap
        assert r.ecology.water == 0.20
        assert r.ecology.forest_cover == 0.10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestCrossEffects tests/test_ecology.py::TestClampEcology -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement _apply_cross_effects and _clamp_ecology**

Add to `src/chronicler/ecology.py`:

```python
def _apply_cross_effects(region: Region) -> None:
    """Forest→soil bonus when forest > 0.5. Water→forest gate handled in _tick_forest."""
    if region.ecology.forest_cover > 0.5:
        region.ecology.soil += 0.01


def _clamp_ecology(region: Region) -> None:
    """Apply floors and terrain-specific caps."""
    caps = TERRAIN_ECOLOGY_CAPS.get(region.terrain, TERRAIN_ECOLOGY_CAPS["plains"])
    region.ecology.soil = max(_FLOOR_SOIL, min(caps["soil"], round(region.ecology.soil, 4)))
    region.ecology.water = max(_FLOOR_WATER, min(caps["water"], round(region.ecology.water, 4)))
    region.ecology.forest_cover = max(_FLOOR_FOREST, min(caps["forest_cover"], round(region.ecology.forest_cover, 4)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestCrossEffects tests/test_ecology.py::TestClampEcology -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): cross-effects (forest→soil) and ecology clamping"
```

---

### Task 9: tick_ecology orchestrator and famine check

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py
from chronicler.ecology import tick_ecology


class TestTickEcology:
    def _make_world(self, pop=50, soil=0.8, water=0.6, forest=0.3, terrain="plains"):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="TestRegion", terrain=terrain, carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=soil, water=water, forest_cover=forest),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["TestRegion"],
        )
        return WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

    def test_returns_event_list(self):
        w = self._make_world()
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        assert isinstance(events, list)

    def test_skips_uncontrolled_regions(self):
        w = self._make_world()
        w.regions[0].controller = None
        old = w.regions[0].ecology.soil
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].ecology.soil == old

    def test_ecology_clamped_after_tick(self):
        w = self._make_world(soil=0.01, terrain="desert")
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].ecology.soil >= 0.05  # floor

    def test_famine_cooldown_decremented(self):
        w = self._make_world()
        w.regions[0].famine_cooldown = 3
        tick_ecology(w, ClimatePhase.TEMPERATE)
        assert w.regions[0].famine_cooldown == 2


class TestFamineCheck:
    def _make_world(self, water=0.15, pop=50):
        from chronicler.models import Leader, Civilization
        r = Region(
            name="TestRegion", terrain="plains", carrying_capacity=100,
            resources="fertile", population=pop, controller="TestCiv",
            ecology=RegionEcology(soil=0.8, water=water, forest_cover=0.3),
        )
        civ = Civilization(
            name="TestCiv", population=pop, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["TestRegion"],
        )
        return WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

    def test_famine_fires_when_water_below_threshold(self):
        w = self._make_world(water=0.15)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 1
        assert "TestRegion" in famine_events[0].description

    def test_no_famine_when_water_above_threshold(self):
        w = self._make_world(water=0.5)
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 0

    def test_no_famine_during_cooldown(self):
        w = self._make_world(water=0.15)
        w.regions[0].famine_cooldown = 3
        events = tick_ecology(w, ClimatePhase.TEMPERATE)
        famine_events = [e for e in events if e.event_type == "famine"]
        assert len(famine_events) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTickEcology tests/test_ecology.py::TestFamineCheck -v`
Expected: FAIL — `tick_ecology` not defined

- [ ] **Step 3: Implement tick_ecology and _check_famine**

Add to `src/chronicler/ecology.py`:

```python
def _check_famine(world: WorldState) -> list[Event]:
    """Region-level famine check: water < threshold."""
    from chronicler.utils import drain_region_pop, sync_civ_population, add_region_pop
    from chronicler.simulation import _get_civ, clamp, STAT_FLOOR
    from chronicler.tuning import get_override as _get
    from chronicler.emergence import get_severity_multiplier

    events: list[Event] = []
    threshold = _get(world, K_FAMINE_WATER_THRESHOLD, 0.20)

    for region in world.regions:
        if region.controller is None or region.famine_cooldown > 0:
            continue
        if region.ecology.water >= threshold:
            continue
        if region.population <= 0:
            continue

        civ = _get_civ(world, region.controller)
        if civ is None:
            continue

        mult = get_severity_multiplier(civ)
        drain_region_pop(region, int(5 * mult))
        sync_civ_population(civ, world)
        drain = int(_get(world, "stability.drain.famine_immediate", 3))
        civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = _get_civ(world, adj.controller)
                if neighbor:
                    add_region_pop(adj, 5)
                    sync_civ_population(neighbor, world)
                    neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)

        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events


def _update_ecology_counters(world: WorldState) -> None:
    """Update low_forest_turns and forest_regrowth_turns for terrain succession."""
    for region in world.regions:
        # Deforestation counter
        if region.ecology.forest_cover < 0.2:
            region.low_forest_turns += 1
        else:
            region.low_forest_turns = 0
        # Regrowth counter
        if region.ecology.forest_cover > 0.7 and region.population < 5:
            region.forest_regrowth_turns += 1
        else:
            region.forest_regrowth_turns = 0


def tick_ecology(world: WorldState, climate_phase: ClimatePhase) -> list[Event]:
    """Phase 9 ecology tick. Replaces phase_fertility."""
    for region in world.regions:
        if region.controller is None:
            continue
        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        _tick_soil(region, civ, climate_phase, world)
        _tick_water(region, civ, climate_phase, world)
        _tick_forest(region, civ, climate_phase, world)
        _apply_cross_effects(region)
        _clamp_ecology(region)

        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1

    events = _check_famine(world)

    # Note: food_stockpiling tradition soil floor added in Task 14 after traditions migration

    # Update ecology counters for M18 terrain succession
    _update_ecology_counters(world)

    from chronicler.utils import sync_all_populations
    sync_all_populations(world)
    return events
```

**Note:** The traditions call (`apply_fertility_floor`) references `fertility` which won't exist yet. Implement `tick_ecology` without the traditions call in this task. Task 14 migrates traditions and adds the call back.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestTickEcology tests/test_ecology.py::TestFamineCheck -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): tick_ecology orchestrator with famine check and ecology counters"
```

---

## Chunk 3: Codebase Migration

### Task 10: Simulation phase 9 swap

**Files:**
- Modify: `src/chronicler/simulation.py:1032-1037`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write a failing integration test**

```python
# Append to tests/test_ecology.py

class TestSimulationPhase9Integration:
    def test_phase_fertility_replaced_by_tick_ecology(self):
        """Verify simulation.py no longer calls phase_fertility."""
        import ast
        from pathlib import Path
        src = Path("src/chronicler/simulation.py").read_text()
        tree = ast.parse(src)
        function_calls = [
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert "phase_fertility" not in function_calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ecology.py::TestSimulationPhase9Integration -v`
Expected: FAIL — `phase_fertility` still called

- [ ] **Step 3: Swap phase 9 in simulation.py**

In `src/chronicler/simulation.py`, around line 1032-1037, replace:

```python
# Phase 9: Fertility
turn_events.extend(phase_fertility(world))

# M18: Terrain succession (after phase_fertility updates low_fertility_turns)
from chronicler.emergence import tick_terrain_succession
turn_events.extend(tick_terrain_succession(world))
```

With:

```python
# Phase 9: Ecology (M23 — replaces phase_fertility)
from chronicler.ecology import tick_ecology
from chronicler.climate import get_climate_phase
climate_phase = get_climate_phase(world.turn, world.climate_config)
turn_events.extend(tick_ecology(world, climate_phase))

# M18: Terrain succession (uses low_forest_turns updated by tick_ecology)
from chronicler.emergence import tick_terrain_succession
turn_events.extend(tick_terrain_succession(world))
```

Also update the phase comment at the top of `simulation.py` (line 12):
```python
# 9. Ecology — soil/water/forest degradation, recovery, famine (M23)
```

Remove the `phase_fertility` function definition (lines 888-944) and the `_check_famine` function (lines 947-984). These are replaced by `ecology.py`.

Remove the now-unused imports of `K_FERTILITY_DEGRADATION`, `K_FERTILITY_RECOVERY`, `K_FAMINE_THRESHOLD` from simulation.py.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ecology.py::TestSimulationPhase9Integration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_ecology.py
git commit -m "feat(m23): swap phase_fertility for tick_ecology in simulation turn loop"
```

---

### Task 11: Effective capacity caller migration

**Files:**
- Modify: `src/chronicler/simulation.py`, `src/chronicler/climate.py`, `src/chronicler/politics.py`, `src/chronicler/factions.py`, `src/chronicler/utils.py`, `src/chronicler/world_gen.py`, `src/chronicler/scenario.py`
- Modify: `src/chronicler/terrain.py` (remove `effective_capacity` and `terrain_fertility_cap`)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_ecology.py

class TestEffectiveCapacityMigration:
    def test_terrain_py_no_longer_exports_effective_capacity(self):
        import chronicler.terrain as t
        assert not hasattr(t, "effective_capacity"), "effective_capacity should be removed from terrain.py"

    def test_ecology_exports_effective_capacity(self):
        from chronicler.ecology import effective_capacity
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile",
            ecology=RegionEcology(soil=0.8, water=0.6, forest_cover=0.3),
        )
        assert effective_capacity(r) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ecology.py::TestEffectiveCapacityMigration -v`
Expected: FAIL — `terrain.py` still exports `effective_capacity`

- [ ] **Step 3: Migrate all callers**

For each file, change `from chronicler.terrain import effective_capacity` to `from chronicler.ecology import effective_capacity`:

1. **`simulation.py`** — update remaining imports (lines ~374, ~591 area). Remove the import of `terrain_fertility_cap` if present.
2. **`climate.py`** — line ~168, migration cascade function. Change import.
3. **`politics.py`** — line ~14 (top-level import), line ~820 (local re-import). Change both.
4. **`factions.py`** — line ~437 area. Change import.
5. **`utils.py`** — line ~61 in `add_region_pop`. Change `from chronicler.terrain import effective_capacity` to `from chronicler.ecology import effective_capacity`.
6. **`world_gen.py`** — line ~22. Change import.
7. **`scenario.py`** — line ~425 area. Change import.

Then in **`terrain.py`**, remove the `effective_capacity` function (lines 76-83) and the `terrain_fertility_cap` function (lines 52-54). Keep `TerrainEffect.fertility_cap` field for scenario backward compat but it's no longer called.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestEffectiveCapacityMigration -v && pytest tests/ -x --timeout=30`
Expected: Migration test passes. Run the full suite to catch any broken imports — expect some failures from tests that reference `fertility` directly (will be fixed in subsequent tasks).

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/terrain.py src/chronicler/simulation.py src/chronicler/climate.py src/chronicler/politics.py src/chronicler/factions.py src/chronicler/utils.py src/chronicler/world_gen.py src/chronicler/scenario.py tests/test_ecology.py
git commit -m "feat(m23): migrate all effective_capacity callers from terrain→ecology"
```

---

### Task 12: Disaster fertility writes migration

**Files:**
- Modify: `src/chronicler/climate.py:116-161` (check_disasters)
- Modify: `src/chronicler/emergence.py:377` (_apply_supervolcano), `src/chronicler/emergence.py:486-505` (_apply_tech_accident)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py

class TestDisasterEcologyMigration:
    def test_earthquake_damages_soil(self):
        r = Region(name="T", terrain="mountains", carrying_capacity=40,
                   resources="mineral", ecology=RegionEcology(soil=0.8, water=0.8, forest_cover=0.3))
        old = r.ecology.soil
        # Simulate earthquake effect directly
        r.ecology.soil = max(0.05, r.ecology.soil - 0.2)
        assert r.ecology.soil < old

    def test_flood_raises_water(self):
        r = Region(name="T", terrain="coast", carrying_capacity=60,
                   resources="maritime", ecology=RegionEcology(soil=0.7, water=0.4, forest_cover=0.3))
        old = r.ecology.water
        r.ecology.water = min(1.0, r.ecology.water + 0.1)
        assert r.ecology.water > old

    def test_wildfire_burns_forest(self):
        r = Region(name="T", terrain="forest", carrying_capacity=50,
                   resources="timber", ecology=RegionEcology(soil=0.7, water=0.7, forest_cover=0.9))
        old = r.ecology.forest_cover
        r.ecology.forest_cover = max(0.0, r.ecology.forest_cover - 0.3)
        assert r.ecology.forest_cover < old
```

- [ ] **Step 2: Run tests to verify they pass (these are formula validation, not integration)**

Run: `pytest tests/test_ecology.py::TestDisasterEcologyMigration -v`
Expected: PASS (validates the formulas work on RegionEcology)

- [ ] **Step 3: Migrate disaster code**

In `src/chronicler/climate.py:check_disasters`:
- Line 117: `region.fertility = max(region.fertility - 0.2, 0.0)` → `region.ecology.soil = max(0.05, region.ecology.soil - 0.2)`
- Line 133: `region.fertility = max(region.fertility - 0.1, 0.0)` → `region.ecology.water = min(1.0, region.ecology.water + 0.1)`
- Line 145: `region.fertility = max(region.fertility - 0.15, 0.0)` → `region.ecology.forest_cover = max(0.0, region.ecology.forest_cover - 0.3)`

In `src/chronicler/emergence.py:_apply_supervolcano`:
- Line 377: `region.fertility = 0.1` → `region.ecology.soil = 0.1; region.ecology.forest_cover = 0.05`

In `src/chronicler/emergence.py:_apply_tech_accident`:
- Line 486: `target.fertility = max(0.0, round(target.fertility - 0.3, 4))` → `target.ecology.soil = max(0.05, round(target.ecology.soil - 0.3, 4))`
- Line 505: `region.fertility = max(0.0, round(region.fertility - 0.15, 4))` → `region.ecology.soil = max(0.05, round(region.ecology.soil - 0.15, 4))`

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_climate.py tests/test_emergence.py -v --timeout=30`
Expected: Some tests may reference `fertility` and need updating in Task 14. Core disaster tests should pass.

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/climate.py src/chronicler/emergence.py tests/test_ecology.py
git commit -m "feat(m23): migrate disaster fertility writes to ecology variables"
```

---

### Task 13: M18 terrain succession migration

**Files:**
- Modify: `src/chronicler/emergence.py:601-659` (update_low_fertility_counters, tick_terrain_succession, _apply_transition)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py

class TestTerrainSuccessionMigration:
    def test_deforestation_triggers_on_low_forest(self):
        from chronicler.emergence import tick_terrain_succession
        r = Region(
            name="T", terrain="forest", carrying_capacity=50,
            resources="timber", population=30, controller="TestCiv",
            ecology=RegionEcology(soil=0.7, water=0.7, forest_cover=0.1),
            low_forest_turns=50,
        )
        from chronicler.models import Leader, Civilization
        civ = Civilization(
            name="TestCiv", population=30, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        events = tick_terrain_succession(w)
        assert len(events) == 1
        assert r.terrain == "plains"

    def test_rewilding_triggers_on_forest_regrowth(self):
        from chronicler.emergence import tick_terrain_succession
        r = Region(
            name="T", terrain="plains", carrying_capacity=60,
            resources="fertile", population=3, controller=None,
            ecology=RegionEcology(soil=0.7, water=0.6, forest_cover=0.8),
            forest_regrowth_turns=100,
        )
        w = WorldState(name="T", seed=42, regions=[r])
        events = tick_terrain_succession(w)
        assert len(events) == 1
        assert r.terrain == "forest"

    def test_apply_transition_sets_ecology_forest_to_plains(self):
        from chronicler.emergence import _apply_transition
        from chronicler.models import TerrainTransitionRule
        r = Region(
            name="T", terrain="forest", carrying_capacity=50,
            resources="timber",
            ecology=RegionEcology(soil=0.7, water=0.7, forest_cover=0.1),
        )
        rule = TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                                     condition="low_forest", threshold_turns=50)
        _apply_transition(r, rule)
        assert r.ecology.soil == 0.5
        assert r.ecology.forest_cover == 0.1
        assert r.low_forest_turns == 0

    def test_apply_transition_sets_ecology_plains_to_forest(self):
        from chronicler.emergence import _apply_transition
        from chronicler.models import TerrainTransitionRule
        r = Region(
            name="T", terrain="plains", carrying_capacity=60,
            resources="fertile",
            ecology=RegionEcology(soil=0.7, water=0.6, forest_cover=0.8),
        )
        rule = TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                                     condition="forest_regrowth", threshold_turns=100)
        _apply_transition(r, rule)
        assert r.ecology.forest_cover == 0.7
        assert r.forest_regrowth_turns == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTerrainSuccessionMigration -v`
Expected: FAIL — emergence.py still checks `low_fertility` and `depopulated`

- [ ] **Step 3: Update emergence.py**

Replace `update_low_fertility_counters` (lines 601-607) — this function is now dead code since `tick_ecology` calls `_update_ecology_counters` internally. Remove it.

Update `tick_terrain_succession` (lines 610-645):
```python
def tick_terrain_succession(world: WorldState) -> list[Event]:
    """Check and apply terrain transitions. Called at end of Phase 9."""
    events: list[Event] = []

    for region in world.regions:
        for rule in world.terrain_transition_rules:
            if region.terrain != rule.from_terrain:
                continue

            if rule.condition == "low_forest":
                if region.low_forest_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[region.controller] if region.controller else [],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

            elif rule.condition == "forest_regrowth":
                if region.forest_regrowth_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

    return events
```

Update `_apply_transition` (lines 648-659):
```python
def _apply_transition(region: Region, rule) -> None:
    """Apply a terrain transition to a region."""
    if rule.from_terrain == "forest" and rule.to_terrain == "plains":
        region.terrain = "plains"
        region.carrying_capacity = min(100, region.carrying_capacity + 20)
        region.ecology.soil = 0.5
        region.ecology.forest_cover = 0.1
        region.low_forest_turns = 0
    elif rule.from_terrain == "plains" and rule.to_terrain == "forest":
        region.terrain = "forest"
        region.carrying_capacity = max(1, region.carrying_capacity - 10)
        region.ecology.forest_cover = 0.7
        region.forest_regrowth_turns = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py::TestTerrainSuccessionMigration -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_ecology.py
git commit -m "feat(m23): migrate M18 terrain succession to forest-keyed triggers"
```

---

## Chunk 4: Remaining Migrations and Test Suite Repair

### Task 14: Traditions, infrastructure, scenario, world_gen, snapshot migrations

**Files:**
- Modify: `src/chronicler/traditions.py:125-132`
- Modify: `src/chronicler/infrastructure.py:86-101` (remove mine degradation)
- Modify: `src/chronicler/scenario.py:49,266-267` (RegionOverride)
- Modify: `src/chronicler/world_gen.py` (terrain ecology defaults)
- Modify: `src/chronicler/main.py:218-279` (snapshot builder)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_ecology.py

class TestTraditionsMigration:
    def test_food_stockpiling_sets_soil_floor(self):
        from chronicler.traditions import apply_fertility_floor
        from chronicler.models import Leader, Civilization
        r = Region(name="T", terrain="plains", carrying_capacity=60,
                   resources="fertile", controller="TestCiv",
                   ecology=RegionEcology(soil=0.1, water=0.4, forest_cover=0.2))
        civ = Civilization(
            name="TestCiv", population=50, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"], traditions=["food_stockpiling"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        apply_fertility_floor(w)
        assert r.ecology.soil >= 0.2


class TestInfrastructureMigration:
    def test_tick_infrastructure_no_longer_degrades_fertility(self):
        """Mine degradation should not reference fertility."""
        from pathlib import Path
        src = Path("src/chronicler/infrastructure.py").read_text()
        assert "region.fertility" not in src


class TestWorldGenMigration:
    def test_world_gen_no_fertility_reference(self):
        from pathlib import Path
        src = Path("src/chronicler/world_gen.py").read_text()
        assert "fertility" not in src.lower() or "ecology" in src.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ecology.py::TestTraditionsMigration tests/test_ecology.py::TestInfrastructureMigration tests/test_ecology.py::TestWorldGenMigration -v`
Expected: FAIL

- [ ] **Step 3: Apply migrations**

**traditions.py** — Replace `apply_fertility_floor`:
```python
def apply_fertility_floor(world: WorldState) -> None:
    """Phase 9: Apply soil floor for civs with food_stockpiling tradition."""
    for region in world.regions:
        controller = next(
            (civ for civ in world.civilizations if region.name in civ.regions), None
        )
        if controller and "food_stockpiling" in controller.traditions:
            region.ecology.soil = max(region.ecology.soil, 0.2)
```

**infrastructure.py** — Remove the mine fertility degradation block (lines 86-101). Keep the rest of `tick_infrastructure` intact. The mine soil degradation and `capability_metallurgy` event emission are now in `ecology.py:_tick_soil` (added in Task 5).

**scenario.py** — In `RegionOverride` (line 49), replace `fertility: float | None = None` with `ecology: dict[str, float] | None = None`. In `apply_scenario_overrides` (lines 266-267), replace:
```python
if reg_override.fertility is not None:
    world.regions[target_idx].fertility = reg_override.fertility
```
With:
```python
if reg_override.ecology is not None:
    for key, value in reg_override.ecology.items():
        setattr(world.regions[target_idx].ecology, key, value)
```

**world_gen.py** — After region creation, apply terrain ecology defaults. In the region generation function, after creating each region, add:
```python
from chronicler.ecology import TERRAIN_ECOLOGY_DEFAULTS
defaults = TERRAIN_ECOLOGY_DEFAULTS.get(region.terrain)
if defaults:
    region.ecology = defaults.model_copy()
```

**main.py** — In the TurnSnapshot builder (line 218-279), add the ecology field:
```python
ecology={r.name: r.ecology.model_dump() for r in world.regions},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ecology.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/traditions.py src/chronicler/infrastructure.py src/chronicler/scenario.py src/chronicler/world_gen.py src/chronicler/main.py src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m23): migrate traditions, infrastructure, scenario, world_gen, snapshot to ecology"
```

---

### Task 15: Existing test suite repair

**Files:**
- Modify: Various test files that reference `fertility` or `low_fertility_turns`

- [ ] **Step 1: Find all broken test references**

Run: `pytest tests/ --timeout=30 2>&1 | head -100`

Identify tests that fail due to:
- `Region` no longer having `fertility` attribute
- `TurnSnapshot` no longer having `fertility` field
- `low_fertility_turns` renamed to `low_forest_turns`
- `terrain.effective_capacity` removed

- [ ] **Step 2: Fix each broken test file**

For each failing test, apply the migration:
- `region.fertility = X` → `region.ecology.soil = X` (or appropriate variable)
- `region.low_fertility_turns` → `region.low_forest_turns`
- `from chronicler.terrain import effective_capacity` → `from chronicler.ecology import effective_capacity`
- `TurnSnapshot(..., fertility={...})` → `TurnSnapshot(..., ecology={...})`

Common files likely affected:
- `tests/test_climate.py` — disaster tests reference fertility
- `tests/test_emergence.py` — succession tests reference low_fertility_turns
- `tests/test_models.py` — model field tests
- `tests/test_simulation.py` — phase_fertility tests
- `tests/test_terrain.py` — effective_capacity tests
- `tests/test_infrastructure.py` — mine degradation tests
- `tests/test_scenario.py` — scenario override tests
- `tests/test_traditions.py` — fertility floor tests
- `tests/test_e2e.py` — end-to-end tests

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ --timeout=60 -v`
Expected: All PASS (or known pre-existing failures unrelated to M23)

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "fix(m23): repair test suite for fertility→ecology migration"
```

---

### Task 16: Final integration smoke test

**Files:**
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write integration tests**

```python
# Append to tests/test_ecology.py

class TestFeedbackLoops:
    """Deterministic multi-turn tests validating feedback loop behavior."""

    def _run_turns(self, world, phase, n):
        from chronicler.ecology import tick_ecology
        all_events = []
        for _ in range(n):
            world.turn += 1
            events = tick_ecology(world, phase)
            all_events.extend(events)
        return all_events

    def test_deforestation_spiral_terminates(self):
        """High pop in forest → forest clears → soil degrades → pop drops → recovery."""
        from chronicler.models import Leader, Civilization
        r = Region(
            name="T", terrain="forest", carrying_capacity=80,
            resources="timber", population=70, controller="TestCiv",
            ecology=RegionEcology(soil=0.7, water=0.7, forest_cover=0.9),
        )
        civ = Civilization(
            name="TestCiv", population=70, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

        self._run_turns(w, ClimatePhase.TEMPERATE, 100)
        # After 100 turns of temperate climate, forest should be partially degraded
        # but system should not have all variables at floor
        assert r.ecology.soil > 0.05 or r.ecology.forest_cover > 0.0

    def test_irrigation_trap_drought_spike(self):
        """Irrigated region during drought loses water faster."""
        from chronicler.models import Leader, Civilization, Infrastructure
        r = Region(
            name="T", terrain="plains", carrying_capacity=100,
            resources="fertile", population=80, controller="TestCiv",
            ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        )
        r.infrastructure.append(Infrastructure(
            type=InfrastructureType.IRRIGATION, builder_civ="TestCiv",
            built_turn=0, active=True,
        ))
        civ = Civilization(
            name="TestCiv", population=80, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"],
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

        self._run_turns(w, ClimatePhase.DROUGHT, 10)
        # Water should drop significantly
        assert r.ecology.water < 0.3

    def test_mining_collapse_and_recovery(self):
        """Mine + mechanization degrades soil; depopulation enables recovery."""
        from chronicler.models import Leader, Civilization, Infrastructure
        r = Region(
            name="T", terrain="mountains", carrying_capacity=40,
            resources="mineral", population=30, controller="TestCiv",
            ecology=RegionEcology(soil=0.4, water=0.8, forest_cover=0.3),
        )
        r.infrastructure.append(Infrastructure(
            type=InfrastructureType.MINES, builder_civ="TestCiv",
            built_turn=0, active=True,
        ))
        civ = Civilization(
            name="TestCiv", population=30, military=30, economy=40,
            culture=30, stability=50, leader=Leader(name="L", trait="cautious", reign_start=0),
            regions=["T"], active_focus="mechanization",
        )
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])

        self._run_turns(w, ClimatePhase.TEMPERATE, 20)
        # Soil should hit floor from heavy mining
        assert r.ecology.soil <= 0.10
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_ecology.py::TestFeedbackLoops -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite one final time**

Run: `pytest tests/ --timeout=60`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_ecology.py
git commit -m "test(m23): feedback loop integration tests — deforestation, irrigation, mining"
```
