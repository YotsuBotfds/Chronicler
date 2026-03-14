# M18: Emergence and Chaos — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rare, high-impact cross-system events (black swans, cascade failures, tech regression, ecological succession) that make long simulations genuinely surprising.

**Architecture:** Single `emergence.py` module containing all M18 logic, called from existing turn phases via distributed hooks. No new turn phases. Cross-system interactions centralized for readability. `remove_era_bonus()` and `_prev_era()` added to `tech.py` alongside their existing inverses.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-14-m18-emergence-chaos-design.md`

**Test command:** `.venv/bin/python -m pytest tests/ -v`

**Existing test count:** 801 tests (must not regress)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/chronicler/models.py` | Modify | Add `PandemicRegion`, `TerrainTransitionRule` models; extend `Region`, `Civilization`, `WorldState`, `ClimateConfig`, `CivSnapshot`, `TurnSnapshot` |
| `src/chronicler/scenario.py` | Modify | Add `chaos_multiplier`, `black_swan_cooldown_turns` to `ScenarioConfig`; wire `terrain_transition_rules` override in `apply_scenario` |
| `src/chronicler/tech.py` | Modify | Add `_prev_era()`, `remove_era_bonus()` |
| `src/chronicler/climate.py` | Modify | Wire `phase_offset` into `get_climate_phase()` |
| `src/chronicler/emergence.py` | Create | All M18 logic: black swans, pandemic tick, stress, regression, terrain succession |
| `src/chronicler/simulation.py` | Modify | Wire M18 hooks into `run_turn()`, `apply_automatic_effects()`, `phase_fertility()` |
| `tests/test_emergence.py` | Create | All M18 unit and integration tests |
| `tests/test_tech.py` | Modify | Tests for `_prev_era()`, `remove_era_bonus()` |
| `tests/test_climate.py` | Modify | Tests for `phase_offset` in `get_climate_phase()` |

---

## Chunk M18a: Data Model & Foundation (Tasks 1-6)

### Task 1: Add new Pydantic models (PandemicRegion, TerrainTransitionRule)

**Files:**
- Modify: `src/chronicler/models.py:257-285` (before `WorldState` class)
- Test: `tests/test_emergence.py` (create)

- [ ] **Step 1: Write failing tests for new models**

Create `tests/test_emergence.py`:

```python
"""Tests for M18 Emergence and Chaos systems."""
import pytest
from chronicler.models import PandemicRegion, TerrainTransitionRule


class TestPandemicRegion:
    def test_create(self):
        pr = PandemicRegion(region_name="Verdant Plains", severity=2, turns_remaining=5)
        assert pr.region_name == "Verdant Plains"
        assert pr.severity == 2
        assert pr.turns_remaining == 5

    def test_serialization_roundtrip(self):
        pr = PandemicRegion(region_name="Iron Peaks", severity=1, turns_remaining=4)
        data = pr.model_dump()
        pr2 = PandemicRegion(**data)
        assert pr2 == pr


class TestTerrainTransitionRule:
    def test_create(self):
        rule = TerrainTransitionRule(
            from_terrain="forest", to_terrain="plains",
            condition="low_fertility", threshold_turns=50,
        )
        assert rule.from_terrain == "forest"
        assert rule.threshold_turns == 50

    def test_serialization_roundtrip(self):
        rule = TerrainTransitionRule(
            from_terrain="plains", to_terrain="forest",
            condition="depopulated", threshold_turns=100,
        )
        data = rule.model_dump()
        rule2 = TerrainTransitionRule(**data)
        assert rule2 == rule
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py -v`
Expected: FAIL — `ImportError: cannot import name 'PandemicRegion' from 'chronicler.models'`

- [ ] **Step 3: Implement the models**

In `src/chronicler/models.py`, add after the `Movement` class (around line 277) and before `WorldState`:

```python
class PandemicRegion(BaseModel):
    """Tracks pandemic spread per-region. Part of M18 emergence system."""
    region_name: str
    severity: int  # 1-3, keyed off active infrastructure count
    turns_remaining: int  # 4-6, decrements each turn


class TerrainTransitionRule(BaseModel):
    """Configurable terrain transformation rule for ecological succession."""
    from_terrain: str
    to_terrain: str
    condition: str  # "low_fertility" or "depopulated"
    threshold_turns: int  # Consecutive turns before transform triggers
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_emergence.py
git commit -m "feat(m18): add PandemicRegion and TerrainTransitionRule models"
```

---

### Task 2: Extend Region, Civilization, WorldState, ClimateConfig with M18 fields

**Files:**
- Modify: `src/chronicler/models.py` — `Region` (line 102), `Civilization` (line 138), `WorldState` (line 286), `ClimateConfig` (line 94)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
from chronicler.models import (
    Region, Civilization, WorldState, ClimateConfig, Leader,
    PandemicRegion, TerrainTransitionRule,
)


class TestM18ModelExtensions:
    def test_region_has_low_fertility_turns(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80, resources="fertile")
        assert r.low_fertility_turns == 0

    def test_civilization_has_stress_fields(self):
        c = Civilization(
            name="T", population=50, military=50, economy=50,
            culture=50, stability=50, leader=Leader(name="L", trait="bold", reign_start=0),
        )
        assert c.civ_stress == 0
        assert c.regions_start_of_turn == 0
        assert c.was_in_twilight is False
        assert c.capital_start_of_turn is None

    def test_world_has_emergence_fields(self):
        w = WorldState(name="T", seed=42)
        assert w.stress_index == 0
        assert w.black_swan_cooldown == 0
        assert w.pandemic_state == []
        assert len(w.terrain_transition_rules) == 2
        assert w.terrain_transition_rules[0].from_terrain == "forest"
        assert w.terrain_transition_rules[1].from_terrain == "plains"
        assert w.chaos_multiplier == 1.0
        assert w.black_swan_cooldown_turns == 30

    def test_climate_config_has_phase_offset(self):
        cfg = ClimateConfig()
        assert cfg.phase_offset == 0

    def test_world_state_serialization_with_m18_fields(self):
        w = WorldState(name="T", seed=42)
        w.stress_index = 5
        w.black_swan_cooldown = 10
        w.pandemic_state.append(PandemicRegion(region_name="X", severity=2, turns_remaining=3))
        data = w.model_dump()
        w2 = WorldState(**data)
        assert w2.stress_index == 5
        assert w2.black_swan_cooldown == 10
        assert len(w2.pandemic_state) == 1
        assert w2.pandemic_state[0].region_name == "X"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestM18ModelExtensions -v`
Expected: FAIL — various `AttributeError` or `ValidationError`

- [ ] **Step 3: Add the fields**

In `src/chronicler/models.py`:

**Region** (after `ruin_quality` field, ~line 122):
```python
    low_fertility_turns: int = 0  # M18: consecutive turns with fertility < 0.3
```

**Civilization** (after `succession_candidates` field, ~line 175):
```python
    civ_stress: int = 0  # M18: per-civ stress, recomputed each turn
    regions_start_of_turn: int = 0  # M18: snapshot for regression detection
    was_in_twilight: bool = False  # M18: snapshot for regression detection
    capital_start_of_turn: str | None = None  # M18: snapshot for regression detection
```

**ClimateConfig** (after `start_phase` field, ~line 97):
```python
    phase_offset: int = 0  # M18: supervolcano advances climate by incrementing this
```

**WorldState** (after `great_person_cooldowns` field, ~line 317 — after all M17 fields):
```python
    # M18: Emergence and Chaos
    stress_index: int = 0  # Global stress aggregate (max across civs)
    black_swan_cooldown: int = 0  # Turns until next black swan eligible
    chaos_multiplier: float = 1.0  # Scalar on black swan probability (from ScenarioConfig)
    black_swan_cooldown_turns: int = 30  # Configurable cooldown length (from ScenarioConfig)
    pandemic_state: list[PandemicRegion] = Field(default_factory=list)
    pandemic_recovered: list[str] = Field(default_factory=list)  # Regions already hit; prevents re-infection
    terrain_transition_rules: list[TerrainTransitionRule] = Field(
        default_factory=lambda: [
            TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                                  condition="low_fertility", threshold_turns=50),
            TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                                  condition="depopulated", threshold_turns=100),
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: 801+ tests pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_emergence.py
git commit -m "feat(m18): extend Region, Civilization, WorldState, ClimateConfig with M18 fields"
```

---

### Task 3: Add ScenarioConfig M18 fields and apply_scenario wiring

**Files:**
- Modify: `src/chronicler/scenario.py:76-95` (`ScenarioConfig` class), `src/chronicler/scenario.py:223` (`apply_scenario`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
from chronicler.scenario import ScenarioConfig


class TestScenarioM18:
    def test_scenario_has_chaos_multiplier(self):
        cfg = ScenarioConfig(name="test")
        assert cfg.chaos_multiplier == 1.0

    def test_scenario_has_cooldown_turns(self):
        cfg = ScenarioConfig(name="test")
        assert cfg.black_swan_cooldown_turns == 30

    def test_scenario_terrain_rules_override(self):
        """Verify that scenario can override terrain transition rules."""
        from chronicler.world_gen import generate_world
        from chronicler.scenario import apply_scenario
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        assert len(world.terrain_transition_rules) == 2
        cfg = ScenarioConfig(name="test", terrain_transition_rules=[])
        apply_scenario(world, cfg)
        assert world.terrain_transition_rules == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestScenarioM18 -v`
Expected: FAIL

- [ ] **Step 3: Implement**

In `src/chronicler/scenario.py`, add `TerrainTransitionRule` to the existing top-level import from `chronicler.models` (line 10-12). Then add to `ScenarioConfig` class (after `fog_of_war`, ~line 95):
```python
    chaos_multiplier: float = Field(default=1.0, ge=0.0)
    black_swan_cooldown_turns: int = Field(default=30, ge=0)
    terrain_transition_rules: list[TerrainTransitionRule] | None = None  # None = use WorldState defaults
```

In `apply_scenario()`, add after the fog_of_war block (~line 363):
```python
    # --- Step 7c: M18 emergence config ---
    world.chaos_multiplier = config.chaos_multiplier
    world.black_swan_cooldown_turns = config.black_swan_cooldown_turns
    if config.terrain_transition_rules is not None:
        world.terrain_transition_rules = list(config.terrain_transition_rules)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestScenarioM18 -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/scenario.py tests/test_emergence.py
git commit -m "feat(m18): add chaos_multiplier and terrain_transition_rules to ScenarioConfig"
```

---

### Task 4: Add `_prev_era()` and `remove_era_bonus()` to tech.py

**Files:**
- Modify: `src/chronicler/tech.py:16` (after `_next_era`), `src/chronicler/tech.py:101` (after `apply_era_bonus`)
- Test: `tests/test_tech.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tech.py`:

```python
from chronicler.models import Civilization, Leader, TechEra
from chronicler.tech import _prev_era, remove_era_bonus, apply_era_bonus, ERA_BONUSES
from chronicler.utils import STAT_FLOOR


class TestPrevEra:
    def test_tribal_returns_none(self):
        assert _prev_era(TechEra.TRIBAL) is None

    def test_bronze_returns_tribal(self):
        assert _prev_era(TechEra.BRONZE) == TechEra.TRIBAL

    def test_information_returns_industrial(self):
        assert _prev_era(TechEra.INFORMATION) == TechEra.INDUSTRIAL

    def test_all_eras_except_tribal_have_prev(self):
        from chronicler.tech import _ERA_ORDER
        for era in _ERA_ORDER[1:]:
            assert _prev_era(era) is not None


class TestRemoveEraBonus:
    def _make_civ(self, **overrides):
        defaults = dict(
            name="T", population=50, military=50, economy=50,
            culture=50, stability=50,
            leader=Leader(name="L", trait="bold", reign_start=0),
        )
        defaults.update(overrides)
        return Civilization(**defaults)

    def test_remove_iron_reverses_apply(self):
        civ = self._make_civ(military=50, economy=50)
        apply_era_bonus(civ, TechEra.IRON)
        mil_after_apply = civ.military
        eco_after_apply = civ.economy
        remove_era_bonus(civ, TechEra.IRON)
        # IRON gives economy +10. military_multiplier is non-int, so only economy changes.
        assert civ.economy == eco_after_apply - 10

    def test_remove_industrial_reverses_apply(self):
        civ = self._make_civ(military=50, economy=50)
        apply_era_bonus(civ, TechEra.INDUSTRIAL)
        remove_era_bonus(civ, TechEra.INDUSTRIAL)
        assert civ.military == 50
        assert civ.economy == 50

    def test_remove_clamps_to_floor(self):
        civ = self._make_civ(economy=5)
        # RENAISSANCE gives economy +20; removing when at 5 should clamp to floor
        remove_era_bonus(civ, TechEra.RENAISSANCE)
        assert civ.economy >= STAT_FLOOR.get("economy", 0)

    def test_remove_era_with_no_bonuses(self):
        """TRIBAL has no bonuses. remove_era_bonus should be a no-op."""
        civ = self._make_civ()
        old_mil = civ.military
        remove_era_bonus(civ, TechEra.TRIBAL)
        assert civ.military == old_mil
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tech.py::TestPrevEra tests/test_tech.py::TestRemoveEraBonus -v`
Expected: FAIL — `ImportError: cannot import name '_prev_era'`

- [ ] **Step 3: Implement**

In `src/chronicler/tech.py`, after `_next_era` (~line 20):

```python
def _prev_era(era: TechEra) -> TechEra | None:
    """Return the previous era, or None for TRIBAL."""
    idx = _era_index(era)
    if idx > 0:
        return _ERA_ORDER[idx - 1]
    return None
```

After `apply_era_bonus` (~line 107):

```python
def remove_era_bonus(civ: Civilization, era: TechEra) -> None:
    """Reverse of apply_era_bonus — subtract integer stat bonuses for an era."""
    bonuses = ERA_BONUSES.get(era, {})
    for stat, amount in bonuses.items():
        if isinstance(amount, int) and hasattr(civ, stat):
            current = getattr(civ, stat)
            setattr(civ, stat, clamp(current - amount, STAT_FLOOR.get(stat, 0), 100))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tech.py::TestPrevEra tests/test_tech.py::TestRemoveEraBonus -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech.py tests/test_tech.py
git commit -m "feat(m18): add _prev_era() and remove_era_bonus() to tech.py"
```

---

### Task 5: Wire phase_offset into get_climate_phase()

**Depends on:** Task 2 (adds `ClimateConfig.phase_offset` field)

**Files:**
- Modify: `src/chronicler/climate.py:27-34` (`get_climate_phase`)
- Test: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_climate.py`:

```python
class TestPhaseOffset:
    def test_offset_zero_unchanged(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75, phase_offset=0)
        assert get_climate_phase(0, cfg) == ClimatePhase.TEMPERATE

    def test_offset_one_advances_one_phase(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=100, phase_offset=1)
        # offset=1 shifts by 25 turns (period//4). Turn 0 with offset=1
        # is equivalent to turn 25 without offset, which should be WARMING.
        assert get_climate_phase(0, cfg) == ClimatePhase.WARMING

    def test_offset_wraps_around(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=100, phase_offset=4)
        # offset=4 shifts by 100 turns = full cycle, back to same phase
        assert get_climate_phase(0, cfg) == get_climate_phase(0, ClimateConfig(period=100))

    def test_offset_two_advances_two_phases(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=100, phase_offset=2)
        # offset=2 shifts by 50 turns. Turn 0 with offset=2 => DROUGHT
        assert get_climate_phase(0, cfg) == ClimatePhase.DROUGHT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_climate.py::TestPhaseOffset -v`
Expected: FAIL (phase_offset field doesn't exist yet on ClimateConfig — added in Task 2 — or formula doesn't use it)

- [ ] **Step 3: Implement**

In `src/chronicler/climate.py`, modify `get_climate_phase` (line 29):

Change:
```python
    position = (turn % config.period) / config.period
```
To:
```python
    shifted_turn = turn + config.phase_offset * (config.period // 4)
    position = (shifted_turn % config.period) / config.period
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_climate.py -v`
Expected: All climate tests pass including new ones

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/climate.py tests/test_climate.py
git commit -m "feat(m18): wire phase_offset into get_climate_phase for volcanic winter"
```

---

### Task 6: Extend CivSnapshot and TurnSnapshot for viewer

**Files:**
- Modify: `src/chronicler/models.py:334` (`CivSnapshot`), `src/chronicler/models.py:367` (`TurnSnapshot`)
- Modify: `src/chronicler/main.py` (snapshot creation — find `CivSnapshot(` construction)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
from chronicler.models import CivSnapshot, TurnSnapshot


class TestSnapshotExtensions:
    def test_civ_snapshot_has_stress(self):
        snap = CivSnapshot(
            population=50, military=50, economy=50, culture=50,
            stability=50, treasury=100, asabiya=0.5, tech_era="tribal",
            trait="bold", regions=["R1"], leader_name="L", alive=True,
        )
        assert snap.civ_stress == 0

    def test_turn_snapshot_has_stress_index(self):
        snap = TurnSnapshot(turn=0, civ_stats={}, region_control={}, relationships={})
        assert snap.stress_index == 0
        assert snap.pandemic_regions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestSnapshotExtensions -v`
Expected: FAIL

- [ ] **Step 3: Implement**

In `CivSnapshot` (after `capital_region`, ~line 356):
```python
    civ_stress: int = 0
```

In `TurnSnapshot` (after `movements_summary`, ~line 385):
```python
    stress_index: int = 0
    pandemic_regions: list[str] = Field(default_factory=list)
```

In `src/chronicler/main.py`, find where `CivSnapshot` is constructed and add:
```python
    civ_stress=civ.civ_stress,
```

Find where `TurnSnapshot` is constructed and add:
```python
    stress_index=world.stress_index,
    pandemic_regions=[p.region_name for p in world.pandemic_state],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestSnapshotExtensions -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py src/chronicler/main.py tests/test_emergence.py
git commit -m "feat(m18): add stress and pandemic fields to viewer snapshots"
```

---

## Chunk M18b: Stress Index & Cascade Severity (Tasks 7-9)

### Task 7: Implement compute_civ_stress and compute_all_stress

**Files:**
- Create: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
from chronicler.models import (
    ActiveCondition, PandemicRegion, WorldState, Region, Civilization,
    Leader, Relationship, Disposition,
)


def _make_world(**overrides) -> WorldState:
    """Create a minimal WorldState for testing."""
    defaults = dict(name="Test", seed=42)
    defaults.update(overrides)
    return WorldState(**defaults)


def _make_civ(name="TestCiv", **overrides) -> Civilization:
    defaults = dict(
        name=name, population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="bold", reign_start=0),
    )
    defaults.update(overrides)
    return Civilization(**defaults)


def _make_region(name="R1", **overrides) -> Region:
    defaults = dict(name=name, terrain="plains", carrying_capacity=80, resources="fertile")
    defaults.update(overrides)
    return Region(**defaults)


class TestComputeCivStress:
    def test_zero_stress_baseline(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        assert compute_civ_stress(civ, world) == 0

    def test_war_adds_3(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_wars = [("TestCiv", "EnemyCiv")]
        assert compute_civ_stress(civ, world) == 3

    def test_two_wars_adds_6(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_wars = [("TestCiv", "A"), ("B", "TestCiv")]
        assert compute_civ_stress(civ, world) == 6

    def test_famine_region_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r = _make_region(controller="TestCiv", famine_cooldown=3)
        world.regions = [r]
        assert compute_civ_stress(civ, world) == 2

    def test_secession_risk_adds_4(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(stability=15, regions=["R1", "R2", "R3"])
        assert compute_civ_stress(civ, world) == 4

    def test_pandemic_adds_2_per_region(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r1 = _make_region(name="R1", controller="TestCiv")
        r2 = _make_region(name="R2", controller="TestCiv")
        world.regions = [r1, r2]
        world.pandemic_state = [
            PandemicRegion(region_name="R1", severity=2, turns_remaining=3),
            PandemicRegion(region_name="R2", severity=1, turns_remaining=2),
        ]
        assert compute_civ_stress(civ, world) == 4

    def test_turbulent_succession_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 10
        leader = Leader(name="L", trait="bold", reign_start=8, succession_type="usurper")
        civ = _make_civ(leader=leader)
        assert compute_civ_stress(civ, world) == 2

    def test_old_succession_no_stress(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 100
        leader = Leader(name="L", trait="bold", reign_start=10, succession_type="usurper")
        civ = _make_civ(leader=leader)
        assert compute_civ_stress(civ, world) == 0

    def test_twilight_adds_3(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(decline_turns=5)
        assert compute_civ_stress(civ, world) == 3

    def test_disaster_condition_adds_2(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_conditions = [
            ActiveCondition(condition_type="drought", affected_civs=["TestCiv"], duration=3, severity=50),
        ]
        assert compute_civ_stress(civ, world) == 2

    def test_volcanic_winter_counts(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        world.active_conditions = [
            ActiveCondition(condition_type="volcanic_winter", affected_civs=["TestCiv"], duration=3, severity=40),
        ]
        assert compute_civ_stress(civ, world) == 2

    def test_overextension_adds_per_region_beyond_6(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ(regions=[f"R{i}" for i in range(8)])
        assert compute_civ_stress(civ, world) == 2  # 8 - 6 = 2

    def test_stress_caps_at_20(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        world.turn = 1
        # Stack everything: 2 wars (6) + secession (4) + twilight (3) + drought (2) +
        # turbulent succession (2) + 16 regions overextension (10) = 27 -> capped at 20
        leader = Leader(name="L", trait="bold", reign_start=0, succession_type="general")
        civ = _make_civ(
            stability=15, decline_turns=5, leader=leader,
            regions=[f"R{i}" for i in range(16)],  # 16 regions = +10 overextension
        )
        world.active_wars = [("TestCiv", "A"), ("TestCiv", "B")]
        world.active_conditions = [
            ActiveCondition(condition_type="drought", affected_civs=["TestCiv"], duration=3, severity=50),
        ]
        assert compute_civ_stress(civ, world) == 20

    def test_multiple_factors_stack(self):
        from chronicler.emergence import compute_civ_stress
        world = _make_world()
        civ = _make_civ()
        r = _make_region(controller="TestCiv", famine_cooldown=3)
        world.regions = [r]
        world.active_wars = [("TestCiv", "Enemy")]
        # War (3) + famine (2) = 5
        assert compute_civ_stress(civ, world) == 5


class TestComputeAllStress:
    def test_updates_all_civs_and_global(self):
        from chronicler.emergence import compute_all_stress
        world = _make_world()
        civ_a = _make_civ(name="A", decline_turns=5)  # twilight = 3 stress
        civ_b = _make_civ(name="B")  # 0 stress
        world.civilizations = [civ_a, civ_b]
        compute_all_stress(world)
        assert civ_a.civ_stress == 3
        assert civ_b.civ_stress == 0
        assert world.stress_index == 3  # max(3, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestComputeCivStress tests/test_emergence.py::TestComputeAllStress -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chronicler.emergence'`

- [ ] **Step 3: Implement**

Create `src/chronicler/emergence.py`:

```python
"""M18 Emergence and Chaos — black swans, stress, regression, ecological succession.

All cross-system emergence logic centralized in one module. Called from
existing turn phases via distributed hooks in simulation.py.
"""
from __future__ import annotations

from chronicler.models import Civilization, WorldState
from chronicler.utils import clamp, STAT_FLOOR


# ---------------------------------------------------------------------------
# Stress Index & Cascade Severity
# ---------------------------------------------------------------------------

def compute_civ_stress(civ: Civilization, world: WorldState) -> int:
    """Compute per-civ stress from current world state. Returns 0-20."""
    stress = 0

    # Active wars: 3 per war (active_wars is list[tuple[str, str]])
    stress += sum(1 for w in world.active_wars if civ.name in w) * 3

    # Famine in controlled regions: 2 per famine region
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.famine_cooldown > 0
    ) * 2

    # Active secession risk: 4 if stability < 20 with 3+ regions
    if civ.stability < 20 and len(civ.regions) >= 3:
        stress += 4

    # Active pandemic in controlled regions: 2 per infected region
    infected_region_names = {p.region_name for p in world.pandemic_state}
    stress += sum(
        1 for r in world.regions
        if r.controller == civ.name and r.name in infected_region_names
    ) * 2

    # Recent turbulent succession: 2 if general/usurper within last 5 turns
    if (civ.leader.succession_type in ("general", "usurper")
            and world.turn - civ.leader.reign_start <= 5):
        stress += 2

    # In twilight: 3
    if civ.decline_turns > 0:
        stress += 3

    # Active disaster conditions: 2 per qualifying condition
    stress += sum(
        1 for c in world.active_conditions
        if civ.name in c.affected_civs
        and c.condition_type in ("drought", "volcanic_winter")
    ) * 2

    # Overextension: 1 per region beyond 6
    stress += max(0, len(civ.regions) - 6)

    return min(stress, 20)


def compute_all_stress(world: WorldState) -> None:
    """Recompute stress for all civs and set global aggregate."""
    for civ in world.civilizations:
        civ.civ_stress = compute_civ_stress(civ, world)
    if world.civilizations:
        world.stress_index = max(c.civ_stress for c in world.civilizations)
    else:
        world.stress_index = 0


def get_severity_multiplier(civ: Civilization) -> float:
    """Return cascade severity multiplier based on civ stress. Range: 1.0-1.5."""
    return 1.0 + (civ.civ_stress / 20) * 0.5
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestComputeCivStress tests/test_emergence.py::TestComputeAllStress -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement stress index and compute_all_stress"
```

---

### Task 8: Implement get_severity_multiplier and verify

**Files:**
- Modify: `src/chronicler/emergence.py` (already has `get_severity_multiplier`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_emergence.py`:

```python
class TestGetSeverityMultiplier:
    def test_zero_stress(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=0)
        assert get_severity_multiplier(civ) == 1.0

    def test_stress_10(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=10)
        assert get_severity_multiplier(civ) == pytest.approx(1.25)

    def test_stress_20_cap(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=20)
        assert get_severity_multiplier(civ) == pytest.approx(1.5)

    def test_stress_5(self):
        from chronicler.emergence import get_severity_multiplier
        civ = _make_civ(civ_stress=5)
        assert get_severity_multiplier(civ) == pytest.approx(1.125)
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestGetSeverityMultiplier -v`
Expected: PASS (4 tests — implementation already exists from Task 7)

- [ ] **Step 3: Commit** (tests only, no code change)

```bash
git add tests/test_emergence.py
git commit -m "test(m18): add severity multiplier tests"
```

---

### Task 9: Wire stress computation into simulation.py

**Files:**
- Modify: `src/chronicler/simulation.py:820` (`run_turn`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_emergence.py`:

```python
class TestStressIntegration:
    def test_stress_computed_after_turn(self):
        """After running a turn, stress should be recomputed."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Give one civ twilight to generate stress
        world.civilizations[0].decline_turns = 5
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # After turn, stress should be computed
        assert world.civilizations[0].civ_stress >= 3  # twilight = 3
        assert world.stress_index >= 3

    def test_snapshots_set_at_turn_start(self):
        """Start-of-turn snapshots should reflect pre-turn state."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        civ = world.civilizations[0]
        initial_regions = len(civ.regions)
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # Snapshot should have captured the pre-turn region count
        assert civ.regions_start_of_turn == initial_regions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestStressIntegration -v`
Expected: FAIL — stress not computed, snapshots not set

- [ ] **Step 3: Wire into run_turn**

In `src/chronicler/simulation.py`, modify `run_turn` (line 820+):

At the top of `run_turn`, before `# Phase 1: Environment`, add:
```python
    # --- M18: Start-of-turn snapshots ---
    for civ in world.civilizations:
        civ.regions_start_of_turn = len(civ.regions)
        civ.was_in_twilight = civ.decline_turns > 0
        civ.capital_start_of_turn = civ.capital_region
```

At the bottom of `run_turn`, after the Phase 10 consequences call and before `# Record events`, add:
```python
    # --- M18: Stress computation (feeds next turn) ---
    from chronicler.emergence import compute_all_stress
    compute_all_stress(world)

    # --- M18: Decrement black swan cooldown ---
    if world.black_swan_cooldown > 0:
        world.black_swan_cooldown -= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestStressIntegration -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass (801+ tests)

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_emergence.py
git commit -m "feat(m18): wire stress computation and snapshots into run_turn"
```

---

## Chunk M18c: Black Swan Events & Pandemic (Tasks 10-17)

### Task 10: Implement black swan probability roll and eligibility framework

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestBlackSwanEligibility:
    def test_no_event_when_cooldown_active(self):
        from chronicler.emergence import check_black_swans
        world = _make_world()
        world.black_swan_cooldown = 10
        world.civilizations = [_make_civ()]
        events = check_black_swans(world, seed=42)
        assert events == []

    def test_no_event_on_failed_roll(self):
        """With chaos_multiplier=0.0, no black swan should ever fire."""
        from chronicler.emergence import check_black_swans
        world = _make_world()
        world.civilizations = [_make_civ()]
        # Use chaos_multiplier=0 to guarantee no roll success
        events = check_black_swans(world, seed=42, chaos_multiplier=0.0)
        assert events == []

    def test_cooldown_set_when_event_fires(self):
        """When a black swan fires, cooldown should be set."""
        from chronicler.emergence import check_black_swans
        world = _make_world()
        # Need at least one eligible type. Resource discovery needs a region with 0 resources.
        r = _make_region(name="Barren", specialized_resources=[])
        world.regions = [r]
        world.civilizations = [_make_civ()]
        # Force the roll to succeed with chaos_multiplier very high
        events = check_black_swans(world, seed=42, chaos_multiplier=1000.0)
        if events:  # If an event fired
            assert world.black_swan_cooldown == 30

    def test_no_eligible_types_no_event(self):
        """If roll succeeds but no types are eligible, no event and no cooldown."""
        from chronicler.emergence import check_black_swans
        world = _make_world()
        # No regions, no civs — nothing is eligible
        events = check_black_swans(world, seed=42, chaos_multiplier=1000.0)
        assert events == []
        assert world.black_swan_cooldown == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestBlackSwanEligibility -v`
Expected: FAIL

- [ ] **Step 3: Implement the framework**

Add to `src/chronicler/emergence.py`:

```python
import random

from chronicler.models import (
    ActiveCondition, Civilization, Event, PandemicRegion, Region,
    Resource, TechEra, WorldState,
)
from chronicler.resources import get_active_trade_routes


# ---------------------------------------------------------------------------
# Black Swan Events
# ---------------------------------------------------------------------------

_BLACK_SWAN_BASE_PROB = 0.005  # 0.5% per turn
_DEFAULT_COOLDOWN = 30

# Event type names (shared constant for detection in simulation.py)
BLACK_SWAN_EVENT_TYPES = frozenset({"pandemic", "supervolcano", "resource_discovery", "tech_accident"})

# Weights for event type selection
_EVENT_WEIGHTS = {
    "pandemic": 3,
    "supervolcano": 2,
    "resource_discovery": 2,
    "tech_accident": 1,
}


def _count_trade_partners(civ_name: str, world: WorldState) -> int:
    """Count distinct trading partners for a civ."""
    routes = get_active_trade_routes(world)
    partners = set()
    for a, b in routes:
        if a == civ_name:
            partners.add(b)
        elif b == civ_name:
            partners.add(a)
    # M17: merchant great person adds +1 to partner count
    for civ in world.civilizations:
        if civ.name == civ_name:
            for gp in civ.great_persons:
                if gp.role == "merchant" and gp.active:
                    return len(partners) + 1
            break
    return len(partners)


def _find_volcano_triples(world: WorldState) -> list[tuple[Region, Region, Region]]:
    """Find all region triples where each pair is adjacent and at least one is controlled."""
    regions = world.regions
    triples = []
    for i, a in enumerate(regions):
        for j, b in enumerate(regions):
            if j <= i:
                continue
            if b.name not in a.adjacencies:
                continue
            for k, c in enumerate(regions):
                if k <= j:
                    continue
                if c.name not in a.adjacencies or c.name not in b.adjacencies:
                    continue
                if a.controller or b.controller or c.controller:
                    triples.append((a, b, c))
    return triples


def _get_eligible_types(world: WorldState) -> dict[str, int]:
    """Return eligible black swan types with their weights."""
    eligible = {}

    # Pandemic: any civ has 3+ distinct trading partners
    for civ in world.civilizations:
        if _count_trade_partners(civ.name, world) >= 3:
            eligible["pandemic"] = _EVENT_WEIGHTS["pandemic"]
            break

    # Supervolcano: any cluster of 3 mutually adjacent regions with at least one controlled
    if _find_volcano_triples(world):
        eligible["supervolcano"] = _EVENT_WEIGHTS["supervolcano"]

    # Resource discovery: any region with 0 specialized resources
    if any(len(r.specialized_resources) == 0 for r in world.regions):
        eligible["resource_discovery"] = _EVENT_WEIGHTS["resource_discovery"]

    # Tech accident: any civ at INDUSTRIAL+
    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    if any(c.tech_era in industrial_plus for c in world.civilizations):
        eligible["tech_accident"] = _EVENT_WEIGHTS["tech_accident"]

    return eligible


def check_black_swans(
    world: WorldState, seed: int, chaos_multiplier: float | None = None,
) -> list[Event]:
    """Roll for black swan event. Called after Phase 1 (Environment).
    chaos_multiplier defaults to world.chaos_multiplier if not provided."""
    if world.black_swan_cooldown > 0:
        return []

    cm = chaos_multiplier if chaos_multiplier is not None else world.chaos_multiplier
    rng = random.Random(seed + world.turn * 997)
    prob = _BLACK_SWAN_BASE_PROB * cm
    if rng.random() >= prob:
        return []

    # Roll succeeded — check eligibility
    eligible = _get_eligible_types(world)
    if not eligible:
        return []  # No eligible types, roll wasted, no cooldown set

    # Weighted selection
    types = list(eligible.keys())
    weights = [eligible[t] for t in types]
    chosen = rng.choices(types, weights=weights, k=1)[0]

    # Set cooldown
    world.black_swan_cooldown = world.black_swan_cooldown_turns

    # Dispatch to specific handler
    handlers = {
        "pandemic": _apply_pandemic_origin,
        "supervolcano": _apply_supervolcano,
        "resource_discovery": _apply_resource_discovery,
        "tech_accident": _apply_tech_accident,
    }
    return handlers[chosen](world, seed)


def _apply_pandemic_origin(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 12."""
    return []


def _apply_supervolcano(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 14."""
    return []


def _apply_resource_discovery(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 15."""
    return []


def _apply_tech_accident(world: WorldState, seed: int) -> list[Event]:
    """Placeholder — implemented in Task 16."""
    return []
```

Update the existing imports at the top of `emergence.py` to include all needed types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestBlackSwanEligibility -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement black swan probability roll and eligibility framework"
```

---

### Task 11: Implement eligibility helper tests

**Files:**
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write tests for each eligibility condition**

Append to `tests/test_emergence.py`:

```python
from chronicler.models import Resource, TechEra, Infrastructure, InfrastructureType


class TestEligibilityHelpers:
    def test_pandemic_eligible_with_3_trade_partners(self):
        from chronicler.emergence import _get_eligible_types
        world = _make_world()
        # Set up 4 civs with trade routes so one has 3 partners
        civs = [_make_civ(name=n, regions=[n]) for n in ["A", "B", "C", "D"]]
        world.civilizations = civs
        regions = [_make_region(name=n, controller=n) for n in ["A", "B", "C", "D"]]
        # Make A adjacent to B, C, D
        regions[0].adjacencies = ["B", "C", "D"]
        regions[1].adjacencies = ["A"]
        regions[2].adjacencies = ["A"]
        regions[3].adjacencies = ["A"]
        world.regions = regions
        # Set up relationships with trade treaties
        from chronicler.models import Relationship, Disposition
        world.relationships = {}
        for c in civs:
            world.relationships[c.name] = {}
            for other in civs:
                if other.name != c.name:
                    world.relationships[c.name][other.name] = Relationship(
                        disposition=Disposition.FRIENDLY,
                        treaties=["trade"],
                    )
        eligible = _get_eligible_types(world)
        assert "pandemic" in eligible

    def test_pandemic_not_eligible_without_trade(self):
        from chronicler.emergence import _get_eligible_types
        world = _make_world()
        world.civilizations = [_make_civ()]
        world.regions = [_make_region(controller="TestCiv")]
        eligible = _get_eligible_types(world)
        assert "pandemic" not in eligible

    def test_supervolcano_eligible_with_triple(self):
        from chronicler.emergence import _get_eligible_types, _find_volcano_triples
        world = _make_world()
        r1 = _make_region(name="A", controller="Civ1")
        r2 = _make_region(name="B")
        r3 = _make_region(name="C")
        r1.adjacencies = ["B", "C"]
        r2.adjacencies = ["A", "C"]
        r3.adjacencies = ["A", "B"]
        world.regions = [r1, r2, r3]
        world.civilizations = [_make_civ(name="Civ1")]
        triples = _find_volcano_triples(world)
        assert len(triples) == 1
        eligible = _get_eligible_types(world)
        assert "supervolcano" in eligible

    def test_supervolcano_not_eligible_no_controller(self):
        from chronicler.emergence import _find_volcano_triples
        world = _make_world()
        r1 = _make_region(name="A")  # No controller
        r2 = _make_region(name="B")
        r3 = _make_region(name="C")
        r1.adjacencies = ["B", "C"]
        r2.adjacencies = ["A", "C"]
        r3.adjacencies = ["A", "B"]
        world.regions = [r1, r2, r3]
        triples = _find_volcano_triples(world)
        assert len(triples) == 0

    def test_resource_discovery_eligible(self):
        from chronicler.emergence import _get_eligible_types
        world = _make_world()
        world.regions = [_make_region(specialized_resources=[])]
        world.civilizations = [_make_civ()]
        eligible = _get_eligible_types(world)
        assert "resource_discovery" in eligible

    def test_tech_accident_eligible_at_industrial(self):
        from chronicler.emergence import _get_eligible_types
        world = _make_world()
        world.civilizations = [_make_civ(tech_era=TechEra.INDUSTRIAL)]
        eligible = _get_eligible_types(world)
        assert "tech_accident" in eligible

    def test_tech_accident_not_eligible_at_medieval(self):
        from chronicler.emergence import _get_eligible_types
        world = _make_world()
        world.civilizations = [_make_civ(tech_era=TechEra.MEDIEVAL)]
        eligible = _get_eligible_types(world)
        assert "tech_accident" not in eligible
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestEligibilityHelpers -v`
Expected: PASS (implementation from Task 10 should handle these)

- [ ] **Step 3: Commit**

```bash
git add tests/test_emergence.py
git commit -m "test(m18): add eligibility helper tests for all black swan types"
```

---

### Task 12: Implement pandemic origin and spread

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestPandemic:
    def _setup_trade_world(self):
        """Create a world with trade routes for pandemic testing."""
        world = _make_world()
        civs = [_make_civ(name=n, regions=[n]) for n in ["A", "B", "C", "D"]]
        regions = [_make_region(name=n, controller=n) for n in ["A", "B", "C", "D"]]
        # A-B-C chain, D isolated
        regions[0].adjacencies = ["B"]
        regions[1].adjacencies = ["A", "C"]
        regions[2].adjacencies = ["B"]
        regions[3].adjacencies = []
        world.regions = regions
        world.civilizations = civs
        # A-B and B-C trade routes
        from chronicler.models import Relationship, Disposition
        world.relationships = {}
        for c in civs:
            world.relationships[c.name] = {}
            for o in civs:
                if o.name != c.name:
                    treaties = ["trade"] if {c.name, o.name} in [{"A", "B"}, {"B", "C"}] else []
                    world.relationships[c.name][o.name] = Relationship(
                        disposition=Disposition.FRIENDLY, treaties=treaties,
                    )
        return world

    def test_pandemic_origin_selects_most_connected(self):
        from chronicler.emergence import _apply_pandemic_origin
        world = self._setup_trade_world()
        events = _apply_pandemic_origin(world, seed=42)
        assert len(events) >= 1
        # B has 2 partners (A and C), most connected
        assert len(world.pandemic_state) >= 1
        # Origin should be in B's region
        origin = world.pandemic_state[0]
        assert origin.region_name == "B"

    def test_pandemic_severity_from_infrastructure(self):
        from chronicler.emergence import _apply_pandemic_origin
        world = self._setup_trade_world()
        # Add infrastructure to region B
        from chronicler.models import Infrastructure, InfrastructureType
        world.regions[1].infrastructure = [
            Infrastructure(type=InfrastructureType.ROADS, builder_civ="B", built_turn=0),
            Infrastructure(type=InfrastructureType.PORTS, builder_civ="B", built_turn=0),
        ]
        _apply_pandemic_origin(world, seed=42)
        origin = world.pandemic_state[0]
        assert origin.severity == 2  # 1 + 2//2 = 2

    def test_tick_pandemic_applies_damage(self):
        from chronicler.emergence import tick_pandemic
        world = _make_world()
        civ = _make_civ(population=80, economy=70)
        world.civilizations = [civ]
        r = _make_region(name="R1", controller="TestCiv")
        world.regions = [r]
        world.pandemic_state = [PandemicRegion(region_name="R1", severity=2, turns_remaining=4)]
        events = tick_pandemic(world)
        assert civ.population < 80  # Should have decreased
        assert civ.economy < 70
        assert world.pandemic_state[0].turns_remaining == 3

    def test_tick_pandemic_removes_expired(self):
        from chronicler.emergence import tick_pandemic
        world = _make_world()
        civ = _make_civ()
        world.civilizations = [civ]
        r = _make_region(name="R1", controller="TestCiv")
        world.regions = [r]
        world.pandemic_state = [PandemicRegion(region_name="R1", severity=1, turns_remaining=1)]
        tick_pandemic(world)
        assert len(world.pandemic_state) == 0  # Removed after last tick

    def test_pandemic_per_civ_damage_cap(self):
        """Damage is per-civ, not per-region. Multiple infected regions don't multiply damage."""
        from chronicler.emergence import tick_pandemic
        world = _make_world()
        civ = _make_civ(population=80, economy=70)
        world.civilizations = [civ]
        r1 = _make_region(name="R1", controller="TestCiv")
        r2 = _make_region(name="R2", controller="TestCiv")
        world.regions = [r1, r2]
        world.pandemic_state = [
            PandemicRegion(region_name="R1", severity=3, turns_remaining=4),
            PandemicRegion(region_name="R2", severity=2, turns_remaining=4),
        ]
        tick_pandemic(world)
        # Max severity is 3. pop -= min(3*3, 12) = 9, eco -= min(3*2, 8) = 6
        assert civ.population == 80 - 9
        assert civ.economy == 70 - 6

    def test_isolated_civ_not_infected(self):
        """D has no trade routes — pandemic should not spread to D."""
        from chronicler.emergence import tick_pandemic
        world = self._setup_trade_world()
        world.pandemic_state = [PandemicRegion(region_name="B", severity=1, turns_remaining=4)]
        tick_pandemic(world)
        infected_names = {p.region_name for p in world.pandemic_state}
        assert "D" not in infected_names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestPandemic -v`
Expected: FAIL (placeholder returns empty list)

- [ ] **Step 3: Implement**

Replace the placeholder `_apply_pandemic_origin` and add `tick_pandemic` in `emergence.py`:

```python
def _apply_pandemic_origin(world: WorldState, seed: int) -> list[Event]:
    """Initialize a pandemic originating from the most trade-connected civ."""
    rng = random.Random(seed + world.turn * 1009)

    # Find most connected civ
    best_civ = None
    best_count = 0
    for civ in world.civilizations:
        count = _count_trade_partners(civ.name, world)
        if count > best_count:
            best_count = count
            best_civ = civ

    if best_civ is None:
        return []

    # Select origin region (random among best_civ's controlled regions)
    controlled = [r for r in world.regions if r.controller == best_civ.name]
    if not controlled:
        return []
    origin_region = rng.choice(controlled)

    # Compute severity from active infrastructure
    active_infra = len([i for i in origin_region.infrastructure if i.active])
    severity = min(3, 1 + active_infra // 2)

    # Duration: 4-6, reduced by 1 if scientist great person present
    duration = rng.randint(4, 6)
    has_scientist = any(
        gp.role == "scientist" and gp.active
        for gp in best_civ.great_persons
    )
    if has_scientist:
        duration = max(1, duration - 1)

    world.pandemic_state.append(PandemicRegion(
        region_name=origin_region.name,
        severity=severity,
        turns_remaining=duration,
    ))

    return [Event(
        turn=world.turn,
        event_type="pandemic",
        actors=[best_civ.name],
        description=f"A devastating plague erupts in {origin_region.name}, spreading through {best_civ.name}'s trade network",
        importance=9,
    )]


def tick_pandemic(world: WorldState) -> list[Event]:
    """Per-turn pandemic tick: apply damage, spread, decrement timers. Phase 2."""
    if not world.pandemic_state:
        return []

    events: list[Event] = []
    infected_names = {p.region_name for p in world.pandemic_state}
    # Use persistent recovered set to prevent re-infection across turns
    already_infected_or_recovered = set(infected_names) | set(world.pandemic_recovered)

    # --- Apply per-civ damage (aggregate, not per-region) ---
    civ_max_severity: dict[str, int] = {}
    for p in world.pandemic_state:
        for r in world.regions:
            if r.name == p.region_name and r.controller:
                current = civ_max_severity.get(r.controller, 0)
                civ_max_severity[r.controller] = max(current, p.severity)

    for civ_name, severity in civ_max_severity.items():
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ is None:
            continue
        pop_loss = min(severity * 3, 12)
        eco_loss = min(severity * 2, 8)
        civ.population = clamp(civ.population - pop_loss, STAT_FLOOR.get("population", 1), 100)
        civ.economy = clamp(civ.economy - eco_loss, STAT_FLOOR.get("economy", 0), 100)

        # Leader kill check: 5% per infected civ
        rng = random.Random(world.seed + world.turn * 1013 + hash(civ_name))
        if rng.random() < 0.05:
            from chronicler.succession import trigger_crisis
            old_leader = civ.leader
            old_leader.alive = False
            trigger_crisis(civ, world)
            events.append(Event(
                turn=world.turn, event_type="pandemic_leader_death",
                actors=[civ_name],
                description=f"{old_leader.name} of {civ_name} succumbs to the plague",
                importance=8,
            ))

    # --- Spread to adjacent trade-connected regions ---
    routes = get_active_trade_routes(world)
    trade_pairs = set()
    for a, b in routes:
        trade_pairs.add((a, b))
        trade_pairs.add((b, a))

    # Collect ALL controllers of currently infected regions
    infected_controllers = set()
    for p in world.pandemic_state:
        for r in world.regions:
            if r.name == p.region_name and r.controller:
                infected_controllers.add(r.controller)

    new_infections: list[PandemicRegion] = []
    rng_spread = random.Random(world.seed + world.turn * 1019)
    for p in world.pandemic_state:
        source_region = next((r for r in world.regions if r.name == p.region_name), None)
        if source_region is None:
            continue
        for adj_name in source_region.adjacencies:
            if adj_name in already_infected_or_recovered:
                continue
            adj_region = next((r for r in world.regions if r.name == adj_name), None)
            if adj_region is None or adj_region.controller is None:
                continue
            # Check if adj controller trades with ANY infected controller
            adj_ctrl = adj_region.controller
            if any((ctrl, adj_ctrl) in trade_pairs for ctrl in infected_controllers):
                active_infra = len([i for i in adj_region.infrastructure if i.active])
                severity = min(3, 1 + active_infra // 2)
                duration = rng_spread.randint(4, 6)
                # Scientist reduction for target civ
                target_civ = next((c for c in world.civilizations if c.name == adj_ctrl), None)
                if target_civ and any(gp.role == "scientist" and gp.active for gp in target_civ.great_persons):
                    duration = max(1, duration - 1)
                new_infections.append(PandemicRegion(
                    region_name=adj_name, severity=severity, turns_remaining=duration,
                ))
                already_infected_or_recovered.add(adj_name)

    # --- Decrement timers and remove expired (BEFORE extending with new infections) ---
    # New infections should not be decremented on the turn they spread —
    # they haven't taken damage yet. Decrement only pre-existing entries.
    for p in world.pandemic_state:
        p.turns_remaining -= 1
    # Track recovered regions before removing them
    for p in world.pandemic_state:
        if p.turns_remaining <= 0:
            world.pandemic_recovered.append(p.region_name)
    world.pandemic_state = [p for p in world.pandemic_state if p.turns_remaining > 0]

    # Now add newly spread regions (they'll take damage and decrement next turn)
    world.pandemic_state.extend(new_infections)

    # Clear recovered list when the entire pandemic ends
    if not world.pandemic_state:
        world.pandemic_recovered = []

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestPandemic -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement pandemic origin, spread, and tick_pandemic"
```

---

### Task 13: Wire pandemic tick into simulation.py Phase 2

**Files:**
- Modify: `src/chronicler/simulation.py:150` (`apply_automatic_effects`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_emergence.py`:

```python
class TestPandemicIntegration:
    def test_pandemic_ticks_during_turn(self):
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Inject a pandemic
        world.pandemic_state = [PandemicRegion(
            region_name=world.regions[0].name, severity=1, turns_remaining=3,
        )]
        world.regions[0].controller = world.civilizations[0].name
        initial_pop = world.civilizations[0].population
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # Pandemic should have ticked (damage applied, timer decremented)
        assert world.civilizations[0].population < initial_pop
        assert world.pandemic_state[0].turns_remaining == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestPandemicIntegration -v`
Expected: FAIL — tick_pandemic not called during turn

- [ ] **Step 3: Wire tick_pandemic into apply_automatic_effects**

In `src/chronicler/simulation.py`, at the end of `apply_automatic_effects` (before `return events`, ~line 311):

```python
    # M18: Pandemic tick
    from chronicler.emergence import tick_pandemic
    events.extend(tick_pandemic(world))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestPandemicIntegration -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_emergence.py
git commit -m "feat(m18): wire tick_pandemic into Phase 2 automatic effects"
```

---

### Task 14: Implement supervolcano

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestSupervolcano:
    def _setup_volcano_world(self):
        world = _make_world()
        r1 = _make_region(name="Peak", terrain="mountains", controller="Civ1")
        r2 = _make_region(name="Valley", terrain="plains", controller="Civ1")
        r3 = _make_region(name="Coast", terrain="coast", controller="Civ2")
        r1.adjacencies = ["Valley", "Coast"]
        r2.adjacencies = ["Peak", "Coast"]
        r3.adjacencies = ["Peak", "Valley"]
        r1.infrastructure = [
            Infrastructure(type=InfrastructureType.FORTIFICATIONS, builder_civ="Civ1", built_turn=0),
        ]
        r1.fertility = 0.8
        r2.fertility = 0.8
        r3.fertility = 0.6
        world.regions = [r1, r2, r3]
        world.civilizations = [
            _make_civ(name="Civ1", population=80, stability=60, regions=["Peak", "Valley"]),
            _make_civ(name="Civ2", population=70, stability=50, regions=["Coast"]),
        ]
        return world

    def test_supervolcano_devastates_fertility(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        events = _apply_supervolcano(world, seed=42)
        assert len(events) >= 1
        for r in world.regions:
            assert r.fertility == pytest.approx(0.1)

    def test_supervolcano_destroys_infrastructure(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        _apply_supervolcano(world, seed=42)
        for r in world.regions:
            assert r.infrastructure == []
            assert r.pending_build is None

    def test_supervolcano_penalizes_controlling_civs(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        _apply_supervolcano(world, seed=42)
        # Civ1 controls 2 blast regions: pop -40, stability -30
        civ1 = world.civilizations[0]
        assert civ1.population <= 80 - 20  # At least -20 for one region
        assert civ1.stability <= 60 - 15

    def test_supervolcano_advances_climate(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        assert world.climate_config.phase_offset == 0
        _apply_supervolcano(world, seed=42)
        assert world.climate_config.phase_offset == 1

    def test_supervolcano_creates_volcanic_winter(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        _apply_supervolcano(world, seed=42)
        volcanic = [c for c in world.active_conditions if c.condition_type == "volcanic_winter"]
        assert len(volcanic) == 1
        assert volcanic[0].duration == 5
        assert volcanic[0].severity == 40

    def test_supervolcano_skips_uncontrolled_region_penalties(self):
        from chronicler.emergence import _apply_supervolcano
        world = self._setup_volcano_world()
        # Make one region uncontrolled
        world.regions[2].controller = None
        world.civilizations[1].regions = []
        _apply_supervolcano(world, seed=42)
        # Uncontrolled region still gets fertility devastated
        assert world.regions[2].fertility == pytest.approx(0.1)
        # But Civ2 should not be penalized (no controlled regions in blast)
        assert world.civilizations[1].population == 70  # Unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestSupervolcano -v`
Expected: FAIL (placeholder returns empty list)

- [ ] **Step 3: Implement**

Replace `_apply_supervolcano` in `emergence.py`:

```python
def _apply_supervolcano(world: WorldState, seed: int) -> list[Event]:
    """Supervolcano: devastate a cluster of 3 adjacent regions."""
    rng = random.Random(seed + world.turn * 1021)

    triples = _find_volcano_triples(world)
    if not triples:
        return []

    # Prefer triples containing mountains
    mountain_triples = [t for t in triples if any(r.terrain == "mountains" for r in t)]
    candidates = mountain_triples if mountain_triples else triples
    cluster = rng.choice(candidates)

    events: list[Event] = []
    affected_civs: set[str] = set()

    # Immediate effects on all regions in cluster
    for region in cluster:
        region.fertility = 0.1
        region.infrastructure = []
        region.pending_build = None

        if region.controller:
            affected_civs.add(region.controller)
            civ = next((c for c in world.civilizations if c.name == region.controller), None)
            if civ:
                civ.population = clamp(civ.population - 20, STAT_FLOOR.get("population", 1), 100)
                civ.stability = clamp(civ.stability - 15, STAT_FLOOR.get("stability", 0), 100)

    # Climate advancement
    world.climate_config.phase_offset += 1

    # Volcanic winter condition — affects civs adjacent to blast zone
    blast_names = {r.name for r in cluster}
    adjacent_civs: set[str] = set()
    for region in cluster:
        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.name not in blast_names:
                adjacent_civs.add(adj.controller)
    all_affected = affected_civs | adjacent_civs
    if all_affected:
        world.active_conditions.append(ActiveCondition(
            condition_type="volcanic_winter",
            affected_civs=list(all_affected),
            duration=5,
            severity=40,
        ))

    # M17: Folk hero asabiya bonus
    for civ_name in affected_civs:
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ and civ.folk_heroes:
            civ.asabiya = min(1.0, civ.asabiya + 0.05)

    region_names = [r.name for r in cluster]
    events.append(Event(
        turn=world.turn,
        event_type="supervolcano",
        actors=list(affected_civs),
        description=f"A supervolcano erupts, devastating {', '.join(region_names)}",
        importance=10,
    ))

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestSupervolcano -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement supervolcano black swan event"
```

---

### Task 15: Implement resource discovery

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestResourceDiscovery:
    def test_adds_resources_to_barren_region(self):
        from chronicler.emergence import _apply_resource_discovery
        world = _make_world()
        r = _make_region(name="Barren", specialized_resources=[], controller="Civ1")
        world.regions = [r]
        world.civilizations = [_make_civ(name="Civ1", regions=["Barren"])]
        _apply_resource_discovery(world, seed=42)
        assert len(r.specialized_resources) >= 1
        assert all(res in (Resource.FUEL, Resource.RARE_MINERALS) for res in r.specialized_resources)

    def test_diplomatic_drift_on_adjacent_civs(self):
        from chronicler.emergence import _apply_resource_discovery
        world = _make_world()
        r1 = _make_region(name="Barren", specialized_resources=[], controller="Civ1")
        r2 = _make_region(name="Neighbor", controller="Civ2")
        r1.adjacencies = ["Neighbor"]
        r2.adjacencies = ["Barren"]
        world.regions = [r1, r2]
        world.civilizations = [
            _make_civ(name="Civ1", regions=["Barren"]),
            _make_civ(name="Civ2", regions=["Neighbor"]),
        ]
        from chronicler.models import Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship()},
            "Civ2": {"Civ1": Relationship()},
        }
        _apply_resource_discovery(world, seed=42)
        assert world.relationships["Civ2"]["Civ1"].disposition_drift <= -5

    def test_discovery_returns_event(self):
        from chronicler.emergence import _apply_resource_discovery
        world = _make_world()
        r = _make_region(name="Barren", specialized_resources=[])
        world.regions = [r]
        world.civilizations = [_make_civ()]
        events = _apply_resource_discovery(world, seed=42)
        assert len(events) == 1
        assert events[0].event_type == "resource_discovery"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestResourceDiscovery -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Replace `_apply_resource_discovery` in `emergence.py`:

```python
def _apply_resource_discovery(world: WorldState, seed: int) -> list[Event]:
    """Add strategic resources to a barren region."""
    rng = random.Random(seed + world.turn * 1031)

    barren = [r for r in world.regions if len(r.specialized_resources) == 0]
    if not barren:
        return []

    region = rng.choice(barren)
    count = rng.randint(1, 2)
    new_resources = rng.sample([Resource.FUEL, Resource.RARE_MINERALS], k=count)
    region.specialized_resources.extend(new_resources)

    # Diplomatic consequence
    controller = region.controller
    for adj_name in region.adjacencies:
        adj = next((r for r in world.regions if r.name == adj_name), None)
        if adj is None or adj.controller is None:
            continue
        adj_ctrl = adj.controller
        if controller and adj_ctrl != controller:
            # Jealousy toward controller
            if adj_ctrl in world.relationships and controller in world.relationships[adj_ctrl]:
                world.relationships[adj_ctrl][controller].disposition_drift -= 5
        elif controller is None:
            # Competition for unclaimed wealth — drift between adjacent controllers
            for other_adj_name in region.adjacencies:
                other_adj = next((r for r in world.regions if r.name == other_adj_name), None)
                if other_adj and other_adj.controller and other_adj.controller != adj_ctrl:
                    if adj_ctrl in world.relationships and other_adj.controller in world.relationships[adj_ctrl]:
                        world.relationships[adj_ctrl][other_adj.controller].disposition_drift -= 5

    resource_names = ", ".join(r.value for r in new_resources)
    return [Event(
        turn=world.turn,
        event_type="resource_discovery",
        actors=[controller] if controller else [],
        description=f"Deposits of {resource_names} discovered in {region.name}!",
        importance=8,
    )]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestResourceDiscovery -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement resource discovery black swan event"
```

---

### Task 16: Implement technological accident

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestTechAccident:
    def _setup_industrial_world(self):
        world = _make_world()
        r1 = _make_region(name="Factory", controller="Civ1", fertility=0.8)
        r2 = _make_region(name="Neighbor1", controller="Civ2", fertility=0.7)
        r3 = _make_region(name="Neighbor2", controller="Civ2", fertility=0.6)
        r1.adjacencies = ["Neighbor1"]
        r2.adjacencies = ["Factory", "Neighbor2"]
        r3.adjacencies = ["Neighbor1"]
        r1.infrastructure = [
            Infrastructure(type=InfrastructureType.MINES, builder_civ="Civ1", built_turn=0),
        ]
        world.regions = [r1, r2, r3]
        world.civilizations = [
            _make_civ(name="Civ1", tech_era=TechEra.INDUSTRIAL, regions=["Factory"]),
            _make_civ(name="Civ2", regions=["Neighbor1", "Neighbor2"]),
        ]
        from chronicler.models import Relationship
        world.relationships = {
            "Civ1": {"Civ2": Relationship()},
            "Civ2": {"Civ1": Relationship()},
        }
        return world

    def test_target_region_fertility_drops(self):
        from chronicler.emergence import _apply_tech_accident
        world = self._setup_industrial_world()
        _apply_tech_accident(world, seed=42)
        assert world.regions[0].fertility == pytest.approx(0.5)  # 0.8 - 0.3

    def test_adjacent_regions_fertility_drops(self):
        from chronicler.emergence import _apply_tech_accident
        world = self._setup_industrial_world()
        _apply_tech_accident(world, seed=42)
        # Neighbor1 is 1 hop: fertility -= 0.15
        assert world.regions[1].fertility == pytest.approx(0.55)  # 0.7 - 0.15

    def test_two_hop_regions_affected(self):
        from chronicler.emergence import _apply_tech_accident
        world = self._setup_industrial_world()
        _apply_tech_accident(world, seed=42)
        # Neighbor2 is 2 hops: fertility -= 0.15
        assert world.regions[2].fertility == pytest.approx(0.45)  # 0.6 - 0.15

    def test_diplomatic_fallout(self):
        from chronicler.emergence import _apply_tech_accident
        world = self._setup_industrial_world()
        _apply_tech_accident(world, seed=42)
        assert world.relationships["Civ2"]["Civ1"].disposition_drift <= -8

    def test_scientist_reduces_radius(self):
        from chronicler.emergence import _apply_tech_accident
        from chronicler.models import GreatPerson
        world = self._setup_industrial_world()
        # Add scientist to Civ1
        scientist = GreatPerson(
            name="Dr. Test", role="scientist", trait="visionary",
            civilization="Civ1", origin_civilization="Civ1", born_turn=0,
        )
        world.civilizations[0].great_persons = [scientist]
        _apply_tech_accident(world, seed=42)
        # With scientist, radius is 1 hop instead of 2. Neighbor2 (2 hops) unaffected.
        assert world.regions[2].fertility == pytest.approx(0.6)  # Unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestTechAccident -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Replace `_apply_tech_accident` in `emergence.py`:

```python
def _apply_tech_accident(world: WorldState, seed: int) -> list[Event]:
    """Industrial+ era ecological disaster."""
    rng = random.Random(seed + world.turn * 1033)

    industrial_plus = {TechEra.INDUSTRIAL, TechEra.INFORMATION}
    industrial_civs = [c for c in world.civilizations if c.tech_era in industrial_plus]
    if not industrial_civs:
        return []

    civ = rng.choice(industrial_civs)

    # Prefer regions with mines
    controlled = [r for r in world.regions if r.controller == civ.name]
    if not controlled:
        return []
    from chronicler.models import InfrastructureType
    mine_regions = [r for r in controlled
                    if any(i.type == InfrastructureType.MINES and i.active for i in r.infrastructure)]
    target = rng.choice(mine_regions if mine_regions else controlled)

    # Scientist reduces radius from 2 to 1
    has_scientist = any(gp.role == "scientist" and gp.active for gp in civ.great_persons)
    max_hops = 1 if has_scientist else 2

    # Target region
    target.fertility = max(0.0, round(target.fertility - 0.3, 4))

    # BFS for regions within max_hops
    affected_neighbors: set[str] = set()
    frontier = {target.name}
    for hop in range(max_hops):
        next_frontier: set[str] = set()
        for rname in frontier:
            region = next((r for r in world.regions if r.name == rname), None)
            if region:
                for adj in region.adjacencies:
                    if adj != target.name and adj not in affected_neighbors:
                        next_frontier.add(adj)
                        affected_neighbors.add(adj)
        frontier = next_frontier

    # Apply fertility reduction to neighbors
    polluter_name = civ.name
    for rname in affected_neighbors:
        region = next((r for r in world.regions if r.name == rname), None)
        if region:
            region.fertility = max(0.0, round(region.fertility - 0.15, 4))
            # Diplomatic fallout
            if region.controller and region.controller != polluter_name:
                if region.controller in world.relationships and polluter_name in world.relationships[region.controller]:
                    world.relationships[region.controller][polluter_name].disposition_drift -= 8

    return [Event(
        turn=world.turn,
        event_type="tech_accident",
        actors=[civ.name],
        description=f"Industrial disaster in {target.name} poisons the surrounding lands",
        importance=8,
    )]
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestTechAccident -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement technological accident black swan event"
```

---

### Task 17: Wire check_black_swans into simulation.py Phase 1

**Files:**
- Modify: `src/chronicler/simulation.py:820` (`run_turn`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_emergence.py`:

```python
class TestBlackSwanIntegration:
    def test_black_swan_check_runs_during_turn(self):
        """Verify check_black_swans is called during run_turn."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Set cooldown to verify it decrements
        world.black_swan_cooldown = 5
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        assert world.black_swan_cooldown == 4  # Decremented by 1
```

- [ ] **Step 2: Run test — should already pass if Task 9 wired the cooldown decrement**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestBlackSwanIntegration -v`
Expected: PASS (cooldown decrement was wired in Task 9)

If it fails, add the `check_black_swans` call in `run_turn` after Phase 1:

```python
    # Phase 1: Environment
    turn_events.extend(phase_environment(world, seed=seed))

    # M18: Black swan check (after climate disasters)
    from chronicler.emergence import check_black_swans
    turn_events.extend(check_black_swans(world, seed=seed))
```

`chaos_multiplier` and `black_swan_cooldown_turns` are stored on `WorldState` (wired from `ScenarioConfig` via `apply_scenario` in Task 3).

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_emergence.py
git commit -m "feat(m18): wire check_black_swans into run_turn Phase 1"
```

---

## Chunk M18d: Tech Regression & Ecological Succession (Tasks 18-22)

### Task 18: Implement tech regression triggers and application

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestTechRegression:
    def test_no_regression_without_triggers(self):
        from chronicler.emergence import check_tech_regression
        world = _make_world()
        civ = _make_civ(tech_era=TechEra.INDUSTRIAL)
        world.civilizations = [civ]
        events = check_tech_regression(world, black_swan_fired=False)
        assert events == []

    def test_capital_loss_trigger(self):
        from chronicler.emergence import check_tech_regression
        world = _make_world()
        civ = _make_civ(
            tech_era=TechEra.INDUSTRIAL,
            regions=["R1"],
            regions_start_of_turn=4,  # Had 4 regions
            capital_start_of_turn="Capital",
            capital_region="R1",  # Capital changed
        )
        world.civilizations = [civ]
        # Run 100 times to verify probability (~30%)
        regressions = 0
        for i in range(100):
            test_world = _make_world()
            test_civ = _make_civ(
                tech_era=TechEra.INDUSTRIAL,
                regions=["R1"],
                regions_start_of_turn=4,
                capital_start_of_turn="Capital",
                capital_region="R1",
            )
            test_world.civilizations = [test_civ]
            test_world.seed = i
            test_world.turn = i
            events = check_tech_regression(test_world, black_swan_fired=False)
            if events:
                regressions += 1
        assert 15 <= regressions <= 45  # ~30% ± wide margin

    def test_twilight_trigger(self):
        from chronicler.emergence import check_tech_regression
        world = _make_world()
        civ = _make_civ(
            tech_era=TechEra.IRON,
            decline_turns=1,
            was_in_twilight=False,  # Transitioned this turn
        )
        world.civilizations = [civ]
        regressions = 0
        for i in range(100):
            test_world = _make_world()
            test_civ = _make_civ(
                tech_era=TechEra.IRON,
                decline_turns=1,
                was_in_twilight=False,
            )
            test_world.civilizations = [test_civ]
            test_world.seed = i
            test_world.turn = i
            events = check_tech_regression(test_world, black_swan_fired=False)
            if events:
                regressions += 1
        assert 35 <= regressions <= 65  # ~50% ± wide margin

    def test_regression_drops_one_era(self):
        from chronicler.emergence import check_tech_regression
        # Use twilight trigger (50%) — guaranteed to fire with enough seeds
        for i in range(100):
            world = _make_world()
            civ = _make_civ(
                tech_era=TechEra.IRON, decline_turns=1, was_in_twilight=False,
                military=60, economy=60,
            )
            world.civilizations = [civ]
            world.seed = i
            world.turn = i
            events = check_tech_regression(world, black_swan_fired=False)
            if events:
                assert civ.tech_era == TechEra.BRONZE
                return
        pytest.fail("Regression never fired in 100 attempts")

    def test_tribal_floor(self):
        from chronicler.emergence import check_tech_regression
        world = _make_world()
        civ = _make_civ(
            tech_era=TechEra.TRIBAL, decline_turns=1, was_in_twilight=False,
        )
        world.civilizations = [civ]
        events = check_tech_regression(world, black_swan_fired=False)
        assert events == []
        assert civ.tech_era == TechEra.TRIBAL

    def test_highest_probability_used(self):
        """When both capital loss (30%) and twilight (50%) match, use 50%."""
        from chronicler.emergence import check_tech_regression
        regressions = 0
        for i in range(200):
            world = _make_world()
            civ = _make_civ(
                tech_era=TechEra.IRON,
                regions=["R1"],
                regions_start_of_turn=4,
                capital_start_of_turn="Capital",
                capital_region="R1",
                decline_turns=1,
                was_in_twilight=False,
            )
            world.civilizations = [civ]
            world.seed = i
            world.turn = i
            events = check_tech_regression(world, black_swan_fired=False)
            if events:
                regressions += 1
        # Should be ~50% (twilight trigger), not ~30% (capital trigger)
        assert regressions >= 70  # At least 35% (50% - wide margin)

    def test_removes_era_bonuses(self):
        from chronicler.emergence import check_tech_regression
        from chronicler.tech import ERA_BONUSES
        # IRON gives economy +10
        for i in range(100):
            world = _make_world()
            civ = _make_civ(
                tech_era=TechEra.IRON, economy=70,
                decline_turns=1, was_in_twilight=False,
            )
            world.civilizations = [civ]
            world.seed = i
            world.turn = i
            events = check_tech_regression(world, black_swan_fired=False)
            if events:
                assert civ.economy == 60  # 70 - 10 (IRON economy bonus)
                return
        pytest.fail("Regression never fired")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestTechRegression -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Add to `emergence.py`:

```python
from chronicler.tech import _prev_era, remove_era_bonus


# ---------------------------------------------------------------------------
# Technological Regression
# ---------------------------------------------------------------------------

# Trigger probabilities (flat, not chaos-multiplied)
_REGRESSION_TRIGGERS = {
    "capital_collapse": 0.30,
    "entered_twilight": 0.50,
    "black_swan_stressed": 0.20,
}


def check_tech_regression(world: WorldState, black_swan_fired: bool = False) -> list[Event]:
    """Check regression triggers for all civs. Phase 10, after consequences."""
    events: list[Event] = []

    for civ in world.civilizations:
        # Floor: can't regress below TRIBAL
        if _prev_era(civ.tech_era) is None:
            continue

        # Find matching triggers and their probabilities
        matching_probs: list[float] = []

        # Trigger 1: Capital loss + territorial collapse
        if (civ.capital_start_of_turn is not None
                and civ.capital_region != civ.capital_start_of_turn
                and civ.regions_start_of_turn > 0
                and len(civ.regions) / civ.regions_start_of_turn < 0.5):
            matching_probs.append(_REGRESSION_TRIGGERS["capital_collapse"])

        # Trigger 2: Entered twilight this turn
        if civ.decline_turns > 0 and not civ.was_in_twilight:
            matching_probs.append(_REGRESSION_TRIGGERS["entered_twilight"])

        # Trigger 3: Black swan while critically stressed
        if black_swan_fired and civ.civ_stress >= 15:
            matching_probs.append(_REGRESSION_TRIGGERS["black_swan_stressed"])

        if not matching_probs:
            continue

        # Use highest probability among matching triggers
        best_prob = max(matching_probs)
        rng = random.Random(world.seed + world.turn * 1037 + hash(civ.name))
        if rng.random() >= best_prob:
            continue

        # Apply regression
        old_era = civ.tech_era
        new_era = _prev_era(old_era)
        assert new_era is not None  # Guarded by floor check above
        remove_era_bonus(civ, old_era)
        civ.tech_era = new_era

        events.append(Event(
            turn=world.turn,
            event_type="tech_regression",
            actors=[civ.name],
            description=f"{civ.name} loses the knowledge of the {old_era.value} era, falling back to {new_era.value}",
            importance=9,
        ))

    return events
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestTechRegression -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement technological regression triggers and era reversal"
```

---

### Task 19: Wire tech regression into simulation.py Phase 10

**Files:**
- Modify: `src/chronicler/simulation.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_emergence.py`:

```python
class TestRegressionIntegration:
    def test_regression_wired_into_turn(self):
        """Verify snapshots are set and regression hook runs during turn."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        civ = world.civilizations[0]
        initial_regions = len(civ.regions)
        run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                 narrator=lambda w, e: "", seed=1)
        # Verify start-of-turn snapshot was set (proves wiring works)
        assert civ.regions_start_of_turn == initial_regions
        assert civ.capital_start_of_turn is not None
```

- [ ] **Step 2: Wire into run_turn**

In `src/chronicler/simulation.py`, in the M18 section at the end of `run_turn`, add before `compute_all_stress`:

```python
    # --- M18: Tech regression (after consequences, before stress) ---
    from chronicler.emergence import check_tech_regression
    from chronicler.emergence import BLACK_SWAN_EVENT_TYPES
    black_swan_this_turn = any(e.event_type in BLACK_SWAN_EVENT_TYPES for e in turn_events)
    turn_events.extend(check_tech_regression(world, black_swan_fired=black_swan_this_turn))
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestRegressionIntegration -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_emergence.py
git commit -m "feat(m18): wire tech regression into run_turn Phase 10"
```

---

### Task 20: Implement ecological succession (deforestation + rewilding)

**Files:**
- Modify: `src/chronicler/emergence.py`
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_emergence.py`:

```python
class TestEcologicalSuccession:
    def test_deforestation_after_threshold(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        r = _make_region(name="Forest", terrain="forest", carrying_capacity=50,
                         fertility=0.2)
        r.low_fertility_turns = 50
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert len(events) == 1
        assert r.terrain == "plains"
        assert r.carrying_capacity == 70  # 50 + 20
        assert r.fertility == pytest.approx(0.5)
        assert r.low_fertility_turns == 0

    def test_deforestation_below_threshold_no_change(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        r = _make_region(name="Forest", terrain="forest", carrying_capacity=50,
                         fertility=0.2)
        r.low_fertility_turns = 49
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert events == []
        assert r.terrain == "forest"

    def test_rewilding_after_threshold(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        world.turn = 200
        r = _make_region(name="Plains", terrain="plains", carrying_capacity=80)
        r.depopulated_since = 99  # 200 - 99 = 101 turns > 100 threshold
        r.controller = None
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert len(events) == 1
        assert r.terrain == "forest"
        assert r.carrying_capacity == 70  # 80 - 10
        assert r.fertility == pytest.approx(0.7)
        assert r.depopulated_since is None

    def test_rewilding_skips_controlled_region(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        world.turn = 200
        r = _make_region(name="Plains", terrain="plains")
        r.depopulated_since = 50  # Would be 150 turns, but has controller
        r.controller = "Civ1"
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert events == []
        assert r.terrain == "plains"

    def test_rewilding_skips_none_depopulated_since(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        world.turn = 200
        r = _make_region(name="Plains", terrain="plains")
        r.depopulated_since = None  # Never controlled
        r.controller = None
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert events == []

    def test_empty_rules_disables_succession(self):
        from chronicler.emergence import tick_terrain_succession
        world = _make_world()
        world.terrain_transition_rules = []
        r = _make_region(name="Forest", terrain="forest", fertility=0.1)
        r.low_fertility_turns = 100
        world.regions = [r]
        events = tick_terrain_succession(world)
        assert events == []
        assert r.terrain == "forest"

    def test_low_fertility_counter_increments(self):
        from chronicler.emergence import update_low_fertility_counters
        world = _make_world()
        r = _make_region(name="R", fertility=0.2)  # Below 0.3
        world.regions = [r]
        update_low_fertility_counters(world)
        assert r.low_fertility_turns == 1

    def test_low_fertility_counter_resets(self):
        from chronicler.emergence import update_low_fertility_counters
        world = _make_world()
        r = _make_region(name="R", fertility=0.5)  # Above 0.3
        r.low_fertility_turns = 10
        world.regions = [r]
        update_low_fertility_counters(world)
        assert r.low_fertility_turns == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestEcologicalSuccession -v`
Expected: FAIL

- [ ] **Step 3: Implement**

Add to `emergence.py`:

```python
# ---------------------------------------------------------------------------
# Ecological Succession
# ---------------------------------------------------------------------------

def update_low_fertility_counters(world: WorldState) -> None:
    """Increment or reset low_fertility_turns for all regions. Called in Phase 9."""
    for region in world.regions:
        if region.fertility < 0.3:
            region.low_fertility_turns += 1
        else:
            region.low_fertility_turns = 0


def tick_terrain_succession(world: WorldState) -> list[Event]:
    """Check and apply terrain transitions. Called at end of Phase 9."""
    events: list[Event] = []

    for region in world.regions:
        for rule in world.terrain_transition_rules:
            if region.terrain != rule.from_terrain:
                continue

            if rule.condition == "low_fertility":
                if region.low_fertility_turns >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[region.controller] if region.controller else [],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

            elif rule.condition == "depopulated":
                # Guards: skip if controlled or never depopulated
                if region.controller is not None:
                    continue
                if region.depopulated_since is None:
                    continue
                if world.turn - region.depopulated_since >= rule.threshold_turns:
                    _apply_transition(region, rule)
                    events.append(Event(
                        turn=world.turn,
                        event_type="terrain_transition",
                        actors=[],
                        description=f"{region.name} transforms from {rule.from_terrain} to {rule.to_terrain}",
                        importance=6,
                    ))

    return events


def _apply_transition(region: Region, rule) -> None:
    """Apply a terrain transition to a region."""
    if rule.from_terrain == "forest" and rule.to_terrain == "plains":
        region.terrain = "plains"
        # Cleared forest = arable land, supports larger agricultural populations
        region.carrying_capacity = min(100, region.carrying_capacity + 20)
        region.fertility = 0.5
        region.low_fertility_turns = 0
    elif rule.from_terrain == "plains" and rule.to_terrain == "forest":
        region.terrain = "forest"
        region.carrying_capacity = max(1, region.carrying_capacity - 10)
        region.fertility = 0.7
        region.depopulated_since = None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestEcologicalSuccession -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_emergence.py
git commit -m "feat(m18): implement ecological succession (deforestation + rewilding)"
```

---

### Task 21: Wire ecological succession into Phase 9

**Files:**
- Modify: `src/chronicler/simulation.py:739` (`phase_fertility`)
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_emergence.py`:

```python
class TestSuccessionIntegration:
    def test_low_fertility_counter_updates_during_turn(self):
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        # Set a forest region to very low fertility
        forest_regions = [r for r in world.regions if r.terrain == "forest"]
        if forest_regions:
            forest_regions[0].fertility = 0.1
            run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                     narrator=lambda w, e: "", seed=1)
            assert forest_regions[0].low_fertility_turns >= 1
```

- [ ] **Step 2: Wire into phase_fertility**

In `src/chronicler/simulation.py`, at the end of `phase_fertility` (before `return _check_famine(world)`, ~line 788):

```python
    # M18: Update low fertility counters and check terrain succession
    from chronicler.emergence import update_low_fertility_counters, tick_terrain_succession
    update_low_fertility_counters(world)
```

And in `run_turn`, after the `phase_fertility` call, add:

```python
    # M18: Terrain succession (after fertility phase updates counters)
    from chronicler.emergence import tick_terrain_succession
    turn_events.extend(tick_terrain_succession(world))
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestSuccessionIntegration -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_emergence.py
git commit -m "feat(m18): wire ecological succession into Phase 9 fertility"
```

---

### Task 22: End-to-end integration test

**Files:**
- Test: `tests/test_emergence.py`

- [ ] **Step 1: Write integration smoke test**

Append to `tests/test_emergence.py`:

```python
class TestM18EndToEnd:
    def test_5_turn_smoke_test(self):
        """Run 5 turns with all M18 systems active. No crashes."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        for turn in range(5):
            run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                     narrator=lambda w, e: "", seed=turn)
        # Verify state consistency
        assert world.turn == 5
        assert world.stress_index >= 0
        assert world.black_swan_cooldown >= 0
        for civ in world.civilizations:
            assert 0 <= civ.civ_stress <= 20
            assert civ.population >= 1
            assert civ.economy >= 0

    def test_50_turn_extended_run(self):
        """Run 50 turns to verify stability over longer periods."""
        from chronicler.simulation import run_turn
        from chronicler.world_gen import generate_world
        from chronicler.models import ActionType
        world = generate_world(seed=99, num_regions=8, num_civs=4)
        for turn in range(50):
            run_turn(world, action_selector=lambda c, w: ActionType.DEVELOP,
                     narrator=lambda w, e: "", seed=turn)
        assert world.turn == 50
        # No crash = success for long runs

    def test_all_existing_tests_still_pass(self):
        """Placeholder reminder: run full test suite to verify no regressions."""
        # This test exists as a reminder — the actual verification is:
        # .venv/bin/python -m pytest tests/ -x -q
        pass
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/python -m pytest tests/test_emergence.py::TestM18EndToEnd -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All 801+ original tests pass plus ~60+ new M18 tests

- [ ] **Step 4: Commit**

```bash
git add tests/test_emergence.py
git commit -m "test(m18): add end-to-end integration smoke tests"
```
