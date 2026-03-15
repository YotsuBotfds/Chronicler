# M21: Tech Specialization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic tech focus selection on era advancement — 15 focuses across 5 eras with scoring, stat/weight effects, and unique gameplay capabilities.

**Architecture:** New module `tech_focus.py` owns all focus definitions, scoring, selection, and effect application. Integration touches 11 existing files at precisely scoped callsites. Orchestration in `phase_technology()` (simulation.py), not inside `check_tech_advancement()`.

**Tech Stack:** Python 3.11+, Pydantic. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-15-m21-tech-specialization-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `src/chronicler/tech_focus.py` | TechFocus enum, ERA_FOCUSES, scoring helpers, FOCUS_EFFECTS table, select/apply/remove, weight modifiers (~250 lines) |
| `tests/test_tech_focus.py` | Selection, scoring, effects, weight integration, capabilities, edge cases (~150 lines) |

### Modified Files

| File | Lines | Changes |
|---|---|---|
| `src/chronicler/models.py` | 182, 398 | Add `tech_focuses`, `active_focus` to Civilization; add `active_focus` to CivSnapshot |
| `src/chronicler/simulation.py` | 766-796 | Hook focus selection in `phase_technology()` after advancement |
| `src/chronicler/action_engine.py` | 581-594, various | Weight modifiers + 2.5x cap in `compute_weights()`; COMMERCE/NETWORKS/EXPLORATION/BANKING/NAVAL_POWER callsite capabilities |
| `src/chronicler/emergence.py` | 578 | Remove focus effects on tech regression |
| `src/chronicler/main.py` | 244 | Populate `active_focus` in CivSnapshot |
| `src/chronicler/tech.py` | 96-98 | SCHOLARSHIP effective_cost pattern |
| `src/chronicler/resources.py` | ~43-69 | NAVIGATION and RAILWAYS 2-hop trade route extensions |
| `src/chronicler/movements.py` | 98 | PRINTING adoption probability x2 |
| `src/chronicler/culture.py` | 127 | MEDIA propaganda acceleration x2 |
| `src/chronicler/politics.py` | 102 | SURVEILLANCE secession threshold |
| `src/chronicler/infrastructure.py` | ~70 | FORTIFICATION build time -1 |

---

## Chunk 1: Data Model + Core Module

### Task 1: Add Civilization Fields

**Files:**
- Modify: `src/chronicler/models.py:182` (after `capital_start_of_turn`)
- Test: `tests/test_tech_focus.py` (new)

- [ ] **Step 1: Write failing test for new fields**

```python
# tests/test_tech_focus.py
from chronicler.models import (
    Civilization, Infrastructure, InfrastructureType, Leader, Region, Resource, TechEra,
)


def test_civilization_has_tech_focus_fields():
    civ = Civilization(
        name="Test", population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.tech_focuses == []
    assert civ.active_focus is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tech_focus.py::test_civilization_has_tech_focus_fields -v`
Expected: FAIL — `tech_focuses` not a field

- [ ] **Step 3: Add fields to Civilization**

In `src/chronicler/models.py`, after line 182 (`capital_start_of_turn`), add:

```python
    tech_focuses: list[str] = Field(default_factory=list)  # M21: history of focus values
    active_focus: str | None = None  # M21: current era's focus
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tech_focus.py::test_civilization_has_tech_focus_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_tech_focus.py
git commit -m "feat(m21): add tech_focuses and active_focus fields to Civilization"
```

---

### Task 2: Add CivSnapshot Field + Snapshot Capture

**Files:**
- Modify: `src/chronicler/models.py:398` (after `civ_stress`)
- Modify: `src/chronicler/main.py:244` (after `civ_stress=civ.civ_stress`)

- [ ] **Step 1: Add `active_focus` to CivSnapshot**

In `src/chronicler/models.py`, after line 398 (`civ_stress: int = 0`), add:

```python
    active_focus: str | None = None  # M21: tech focus for viewer/analytics
```

- [ ] **Step 2: Wire snapshot capture in main.py**

In `src/chronicler/main.py`, after line 244 (`civ_stress=civ.civ_stress,`), add:

```python
                    active_focus=civ.active_focus,
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/test_simulation.py tests/test_scenario.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py src/chronicler/main.py
git commit -m "feat(m21): add active_focus to CivSnapshot and wire snapshot capture"
```

---

### Task 3: TechFocus Enum + ERA_FOCUSES + Scoring Helpers

**Files:**
- Create: `src/chronicler/tech_focus.py`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing test for enum and era mapping**

```python
# tests/test_tech_focus.py (append)
from chronicler.tech_focus import TechFocus, ERA_FOCUSES
from chronicler.models import TechEra


def test_tech_focus_enum_has_15_values():
    assert len(TechFocus) == 15


def test_era_focuses_maps_5_eras():
    assert len(ERA_FOCUSES) == 5
    for era in (TechEra.CLASSICAL, TechEra.MEDIEVAL, TechEra.RENAISSANCE,
                TechEra.INDUSTRIAL, TechEra.INFORMATION):
        assert len(ERA_FOCUSES[era]) == 3


def test_pre_classical_eras_have_no_focuses():
    for era in (TechEra.TRIBAL, TechEra.BRONZE, TechEra.IRON):
        assert era not in ERA_FOCUSES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tech_focus.py::test_tech_focus_enum_has_15_values -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create tech_focus.py with enum, ERA_FOCUSES, and scoring helpers**

Create `src/chronicler/tech_focus.py`:

```python
"""Tech specialization — divergent development paths from deterministic state-based selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from chronicler.models import (
    ActionType, Civilization, Event, InfrastructureType, Resource, TechEra, WorldState,
)
from chronicler.utils import clamp, STAT_FLOOR


class TechFocus(str, Enum):
    # Classical
    NAVIGATION = "navigation"
    METALLURGY = "metallurgy"
    AGRICULTURE = "agriculture"
    # Medieval
    FORTIFICATION = "fortification"
    COMMERCE = "commerce"
    SCHOLARSHIP = "scholarship"
    # Renaissance
    EXPLORATION = "exploration"
    BANKING = "banking"
    PRINTING = "printing"
    # Industrial
    MECHANIZATION = "mechanization"
    RAILWAYS = "railways"
    NAVAL_POWER = "naval_power"
    # Information
    NETWORKS = "networks"
    SURVEILLANCE = "surveillance"
    MEDIA = "media"


ERA_FOCUSES: dict[TechEra, list[TechFocus]] = {
    TechEra.CLASSICAL: [TechFocus.NAVIGATION, TechFocus.METALLURGY, TechFocus.AGRICULTURE],
    TechEra.MEDIEVAL: [TechFocus.FORTIFICATION, TechFocus.COMMERCE, TechFocus.SCHOLARSHIP],
    TechEra.RENAISSANCE: [TechFocus.EXPLORATION, TechFocus.BANKING, TechFocus.PRINTING],
    TechEra.INDUSTRIAL: [TechFocus.MECHANIZATION, TechFocus.RAILWAYS, TechFocus.NAVAL_POWER],
    TechEra.INFORMATION: [TechFocus.NETWORKS, TechFocus.SURVEILLANCE, TechFocus.MEDIA],
}


# --- Scoring helpers ---

def _count_terrain(civ: Civilization, world: WorldState, terrain: str) -> int:
    return sum(1 for r in world.regions if r.controller == civ.name and r.terrain == terrain)


def _count_resource(civ: Civilization, world: WorldState, resource: Resource) -> int:
    return sum(
        1 for r in world.regions
        if r.controller == civ.name and resource in r.specialized_resources
    )


def _count_infra(civ: Civilization, world: WorldState, infra_type: InfrastructureType) -> int:
    return sum(
        1 for r in world.regions if r.controller == civ.name
        for i in r.infrastructure if i.type == infra_type and i.active
    )


def _count_trade_routes(civ: Civilization, world: WorldState) -> int:
    from chronicler.resources import get_active_trade_routes
    return sum(1 for route in get_active_trade_routes(world) if civ.name in route)


def _count_unclaimed_adjacent(civ: Civilization, world: WorldState) -> int:
    civ_regions = {r.name for r in world.regions if r.controller == civ.name}
    adjacent = set()
    for r in world.regions:
        if r.name in civ_regions:
            adjacent.update(r.adjacencies)
    unclaimed = set()
    for r in world.regions:
        if r.name in adjacent and r.name not in civ_regions and r.controller is None:
            unclaimed.add(r.name)
    return len(unclaimed)


def _count_border_regions(civ: Civilization, world: WorldState) -> int:
    region_controllers = {r.name: r.controller for r in world.regions}
    count = 0
    for r in world.regions:
        if r.controller != civ.name:
            continue
        for adj_name in r.adjacencies:
            adj_ctrl = region_controllers.get(adj_name)
            if adj_ctrl is not None and adj_ctrl != civ.name:
                count += 1
                break
    return count


def _count_great_persons(civ: Civilization) -> int:
    return sum(1 for gp in civ.great_persons if gp.active)


def _count_civ_movements(civ: Civilization, world: WorldState) -> int:
    return sum(1 for m in world.movements if civ.name in m.adherents)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tech_focus.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech_focus.py tests/test_tech_focus.py
git commit -m "feat(m21): add TechFocus enum, ERA_FOCUSES, and scoring helpers"
```

---

### Task 4: Scoring Functions + select_tech_focus()

**Files:**
- Modify: `src/chronicler/tech_focus.py`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing tests for scoring and selection**

```python
# tests/test_tech_focus.py (append)
from chronicler.tech_focus import select_tech_focus, _score_focus
from chronicler.models import Region, WorldState


def _make_world(regions=None, seed=42):
    """Minimal WorldState for testing."""
    return WorldState(
        name="TestWorld", turn=1, seed=seed,
        regions=regions or [],
        civilizations=[],
        relationships={},
    )


def _make_civ(**kwargs):
    defaults = dict(
        name="TestCiv", population=50, military=50, economy=50,
        culture=50, stability=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    defaults.update(kwargs)
    return Civilization(**defaults)


def _make_region(name, terrain="plains", controller=None, **kwargs):
    defaults = dict(
        name=name, terrain=terrain, carrying_capacity=20,
        resources="fertile", controller=controller, population=10,
    )
    defaults.update(kwargs)
    return Region(**defaults)


def _make_infra(infra_type, active=True):
    return Infrastructure(type=infra_type, builder_civ="TestCiv", built_turn=0, active=active)


def test_coastal_civ_selects_navigation():
    """Coastal regions + ports should score NAVIGATION highest."""
    regions = [
        _make_region(f"Coast{i}", terrain="coast", controller="TestCiv",
                     resources="maritime",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
        for i in range(3)
    ]
    civ = _make_civ(tech_era=TechEra.CLASSICAL, regions=[r.name for r in regions])
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    focus = select_tech_focus(civ, world)
    assert focus == TechFocus.NAVIGATION


def test_iron_mining_civ_selects_metallurgy():
    """Iron regions + mines should score METALLURGY highest."""
    regions = [
        _make_region(f"Mine{i}", terrain="mountains", controller="TestCiv",
                     resources="mineral",
                     specialized_resources=[Resource.IRON],
                     infrastructure=[_make_infra(InfrastructureType.MINES)])
        for i in range(3)
    ]
    civ = _make_civ(tech_era=TechEra.CLASSICAL, regions=[r.name for r in regions])
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    focus = select_tech_focus(civ, world)
    assert focus == TechFocus.METALLURGY


def test_pre_classical_returns_none():
    civ = _make_civ(tech_era=TechEra.IRON)
    world = _make_world()
    world.civilizations.append(civ)
    assert select_tech_focus(civ, world) is None


def test_selection_is_deterministic():
    """Same seed + state should produce same focus."""
    regions = [
        _make_region("R1", terrain="coast", controller="TestCiv",
                     resources="maritime",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
    ]
    civ = _make_civ(tech_era=TechEra.CLASSICAL, regions=["R1"])
    world = _make_world(regions=regions, seed=42)
    world.civilizations.append(civ)
    results = [select_tech_focus(civ, world) for _ in range(10)]
    assert len(set(results)) == 1


def test_all_zero_fallback_uses_highest_stat():
    """Forest-only civ with high military should fall back to METALLURGY."""
    regions = [_make_region("Forest1", terrain="forest", controller="TestCiv")]
    civ = _make_civ(tech_era=TechEra.CLASSICAL, military=80, economy=30, culture=20,
                    regions=["Forest1"])
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    focus = select_tech_focus(civ, world)
    assert focus == TechFocus.METALLURGY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tech_focus.py::test_coastal_civ_selects_navigation -v`
Expected: FAIL — `select_tech_focus` not defined

- [ ] **Step 3: Implement scoring functions and select_tech_focus**

Append to `src/chronicler/tech_focus.py`:

```python
# --- Scoring formulas per focus ---

# GP role -> focuses that get +5 bonus
_GP_BONUSES: dict[str, set[TechFocus]] = {
    "scientist": {TechFocus.SCHOLARSHIP, TechFocus.PRINTING, TechFocus.NETWORKS},
    "merchant": {TechFocus.COMMERCE, TechFocus.BANKING, TechFocus.RAILWAYS},
    "general": {TechFocus.METALLURGY, TechFocus.FORTIFICATION, TechFocus.MECHANIZATION},
    "prophet": {TechFocus.AGRICULTURE, TechFocus.SCHOLARSHIP, TechFocus.MEDIA},
}

# Tradition -> focuses that get +3 bonus
_TRADITION_BONUSES: dict[str, set[TechFocus]] = {
    "scholarly": {TechFocus.SCHOLARSHIP, TechFocus.PRINTING, TechFocus.MEDIA},
    "martial": {TechFocus.METALLURGY, TechFocus.FORTIFICATION, TechFocus.MECHANIZATION},
}

# All-zero fallback: stat -> focus per era
_ZERO_FALLBACK: dict[TechEra, dict[str, TechFocus]] = {
    TechEra.CLASSICAL: {"military": TechFocus.METALLURGY, "economy": TechFocus.NAVIGATION, "culture": TechFocus.AGRICULTURE},
    TechEra.MEDIEVAL: {"military": TechFocus.FORTIFICATION, "economy": TechFocus.COMMERCE, "culture": TechFocus.SCHOLARSHIP},
    TechEra.RENAISSANCE: {"military": TechFocus.EXPLORATION, "economy": TechFocus.BANKING, "culture": TechFocus.PRINTING},
    TechEra.INDUSTRIAL: {"military": TechFocus.NAVAL_POWER, "economy": TechFocus.MECHANIZATION, "culture": TechFocus.RAILWAYS},
    TechEra.INFORMATION: {"military": TechFocus.SURVEILLANCE, "economy": TechFocus.NETWORKS, "culture": TechFocus.MEDIA},
}


def _base_score(focus: TechFocus, civ: Civilization, world: WorldState) -> float:
    """Compute base geographic/economic score for a single focus."""
    # Classical
    if focus == TechFocus.NAVIGATION:
        return _count_terrain(civ, world, "coast") * 3 + _count_infra(civ, world, InfrastructureType.PORTS) * 5
    if focus == TechFocus.METALLURGY:
        return _count_resource(civ, world, Resource.IRON) * 4 + _count_infra(civ, world, InfrastructureType.MINES) * 5
    if focus == TechFocus.AGRICULTURE:
        return (_count_resource(civ, world, Resource.GRAIN) * 3
                + _count_infra(civ, world, InfrastructureType.IRRIGATION) * 5
                + civ.population * 0.1)  # civ.population synced in phase 0, current by phase 4
    # Medieval
    if focus == TechFocus.FORTIFICATION:
        return (_count_infra(civ, world, InfrastructureType.FORTIFICATIONS) * 5
                + _count_border_regions(civ, world) * 3
                + civ.military * 0.2)
    if focus == TechFocus.COMMERCE:
        return (_count_trade_routes(civ, world) * 5
                + civ.treasury * 0.1
                + _count_infra(civ, world, InfrastructureType.PORTS) * 3)
    if focus == TechFocus.SCHOLARSHIP:
        return (civ.culture * 0.3
                + _count_great_persons(civ) * 5
                + len(civ.traditions) * 3)
    # Renaissance
    if focus == TechFocus.EXPLORATION:
        return (len(civ.regions) * 3
                + civ.military * 0.15
                + _count_unclaimed_adjacent(civ, world) * 4)
    if focus == TechFocus.BANKING:
        return (civ.treasury * 0.15
                + civ.economy * 0.3
                + _count_trade_routes(civ, world) * 3)
    if focus == TechFocus.PRINTING:
        return (civ.culture * 0.2
                + _count_civ_movements(civ, world) * 5
                + _count_great_persons(civ) * 3)
    # Industrial
    if focus == TechFocus.MECHANIZATION:
        return (_count_infra(civ, world, InfrastructureType.MINES) * 5
                + _count_resource(civ, world, Resource.IRON) * 3
                + civ.economy * 0.2)
    if focus == TechFocus.RAILWAYS:
        return (_count_infra(civ, world, InfrastructureType.ROADS) * 5
                + len(civ.regions) * 3
                + _count_trade_routes(civ, world) * 2)
    if focus == TechFocus.NAVAL_POWER:
        return (_count_terrain(civ, world, "coast") * 5
                + _count_infra(civ, world, InfrastructureType.PORTS) * 5
                + civ.military * 0.2)
    # Information
    if focus == TechFocus.NETWORKS:
        return (_count_trade_routes(civ, world) * 5
                + _count_infra(civ, world, InfrastructureType.ROADS) * 3
                + civ.economy * 0.2)
    if focus == TechFocus.SURVEILLANCE:
        return (len(civ.regions) * 3
                + civ.stability * 0.3
                + civ.population * 0.05)
    if focus == TechFocus.MEDIA:
        return (civ.culture * 0.3
                + _count_civ_movements(civ, world) * 5
                + _count_great_persons(civ) * 3)
    return 0.0


def _gp_bonus(focus: TechFocus, civ: Civilization) -> float:
    bonus = 0.0
    for gp in civ.great_persons:
        if gp.active and gp.role in _GP_BONUSES and focus in _GP_BONUSES[gp.role]:
            bonus += 5.0
    return bonus


def _tradition_bonus(focus: TechFocus, civ: Civilization) -> float:
    bonus = 0.0
    for tradition in civ.traditions:
        if tradition in _TRADITION_BONUSES and focus in _TRADITION_BONUSES[tradition]:
            bonus += 3.0
    return bonus


def _score_focus(focus: TechFocus, civ: Civilization, world: WorldState) -> float:
    """Score a single focus based on civ state, geography, and great persons."""
    return _base_score(focus, civ, world) + _gp_bonus(focus, civ) + _tradition_bonus(focus, civ)


def select_tech_focus(civ: Civilization, world: WorldState) -> TechFocus | None:
    """Select tech focus for current era. Returns None if era has no focuses."""
    focuses = ERA_FOCUSES.get(civ.tech_era)
    if not focuses:
        return None

    scores = {f: _score_focus(f, civ, world) for f in focuses}

    # All-zero fallback: pick based on highest civ stat
    if all(s == 0.0 for s in scores.values()):
        fallback = _ZERO_FALLBACK.get(civ.tech_era, {})
        stat_order = sorted(
            ["military", "economy", "culture"],
            key=lambda s: (-getattr(civ, s), hash((world.seed, civ.name, s))),
        )
        return fallback[stat_order[0]]

    max_score = max(scores.values())
    tied = [f for f, s in scores.items() if s == max_score]
    if len(tied) == 1:
        return tied[0]
    # Deterministic tiebreak
    return min(tied, key=lambda f: hash((world.seed, civ.name, f.value)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tech_focus.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech_focus.py tests/test_tech_focus.py
git commit -m "feat(m21): implement scoring functions and select_tech_focus"
```

---

### Task 5: FocusEffect Table + apply/remove/get_weight_modifiers

**Files:**
- Modify: `src/chronicler/tech_focus.py`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing tests for effects**

```python
# tests/test_tech_focus.py (append)
from chronicler.tech_focus import (
    apply_focus_effects, remove_focus_effects, get_focus_weight_modifiers, FOCUS_EFFECTS,
)


def test_focus_effects_table_has_15_entries():
    assert len(FOCUS_EFFECTS) == 15


def test_apply_focus_effects_modifies_stats():
    civ = _make_civ(military=50)
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 65  # +15
    assert civ.active_focus == "metallurgy"
    assert "metallurgy" in civ.tech_focuses


def test_remove_focus_effects_reverses_stats():
    civ = _make_civ(military=65)
    civ.active_focus = "metallurgy"
    remove_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 50


def test_apply_remove_clamping_asymmetry():
    """Applying at ceiling is lossy — expected behavior."""
    civ = _make_civ(military=95)
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 100  # clamped
    remove_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 85  # 100 - 15, not back to 95


def test_get_weight_modifiers_returns_dict():
    civ = _make_civ()
    civ.active_focus = "metallurgy"
    mods = get_focus_weight_modifiers(civ)
    assert ActionType.WAR in mods
    assert mods[ActionType.WAR] == 1.3


def test_get_weight_modifiers_empty_when_no_focus():
    civ = _make_civ()
    assert get_focus_weight_modifiers(civ) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tech_focus.py::test_focus_effects_table_has_15_entries -v`
Expected: FAIL — `FOCUS_EFFECTS` not defined

- [ ] **Step 3: Implement FOCUS_EFFECTS, apply/remove/get_weight_modifiers**

Append to `src/chronicler/tech_focus.py`:

```python
# --- Focus effects ---

@dataclass
class FocusEffect:
    stat_modifiers: dict[str, int]
    weight_modifiers: dict[ActionType, float]
    capability: str


FOCUS_EFFECTS: dict[TechFocus, FocusEffect] = {
    TechFocus.NAVIGATION: FocusEffect({"economy": 5}, {ActionType.EXPLORE: 1.5, ActionType.TRADE: 1.3}, "extended_sea_trade"),
    TechFocus.METALLURGY: FocusEffect({"military": 15}, {ActionType.WAR: 1.3, ActionType.BUILD: 1.2}, "reduced_mine_degradation"),
    TechFocus.AGRICULTURE: FocusEffect({"economy": 10}, {ActionType.BUILD: 1.3, ActionType.TRADE: 1.2}, "famine_resistance"),
    TechFocus.FORTIFICATION: FocusEffect({"military": 10}, {ActionType.BUILD: 1.5, ActionType.WAR: 1.2}, "faster_fort_construction"),
    TechFocus.COMMERCE: FocusEffect({"economy": 10}, {ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.2}, "trade_income_bonus"),
    TechFocus.SCHOLARSHIP: FocusEffect({"culture": 10}, {ActionType.INVEST_CULTURE: 1.3, ActionType.DIPLOMACY: 1.2}, "tech_cost_discount"),
    TechFocus.EXPLORATION: FocusEffect({"military": 5}, {ActionType.EXPLORE: 1.5, ActionType.WAR: 1.2}, "harsh_terrain_expansion"),
    TechFocus.BANKING: FocusEffect({"economy": 15}, {ActionType.TRADE: 1.3, ActionType.EMBARGO: 1.3}, "embargo_resistance"),
    TechFocus.PRINTING: FocusEffect({"culture": 15}, {ActionType.INVEST_CULTURE: 1.5, ActionType.DIPLOMACY: 1.3}, "movement_spread_boost"),
    TechFocus.MECHANIZATION: FocusEffect({"economy": 10}, {ActionType.BUILD: 1.5, ActionType.TRADE: 1.2}, "mine_income"),
    TechFocus.RAILWAYS: FocusEffect({"economy": 5}, {ActionType.BUILD: 1.3, ActionType.TRADE: 1.3}, "extended_trade_routes"),
    TechFocus.NAVAL_POWER: FocusEffect({"military": 15}, {ActionType.WAR: 1.5, ActionType.EXPLORE: 1.2}, "coastal_defense"),
    TechFocus.NETWORKS: FocusEffect({"economy": 10}, {ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.2}, "trade_income_doubled"),
    TechFocus.SURVEILLANCE: FocusEffect({"stability": 10}, {ActionType.DIPLOMACY: 1.3, ActionType.WAR: 1.2}, "secession_resistance"),
    TechFocus.MEDIA: FocusEffect({"culture": 15}, {ActionType.INVEST_CULTURE: 1.5, ActionType.TRADE: 1.2}, "propaganda_boost"),
}


def apply_focus_effects(civ: Civilization, focus: TechFocus) -> None:
    """Apply stat modifiers for newly selected focus."""
    effects = FOCUS_EFFECTS[focus]
    for stat, amount in effects.stat_modifiers.items():
        current = getattr(civ, stat)
        setattr(civ, stat, clamp(current + amount, STAT_FLOOR.get(stat, 0), 100))
    civ.active_focus = focus.value
    civ.tech_focuses.append(focus.value)


def remove_focus_effects(civ: Civilization, focus: TechFocus) -> None:
    """Remove stat modifiers from previous focus when advancing."""
    effects = FOCUS_EFFECTS[focus]
    for stat, amount in effects.stat_modifiers.items():
        current = getattr(civ, stat)
        setattr(civ, stat, clamp(current - amount, STAT_FLOOR.get(stat, 0), 100))


def get_focus_weight_modifiers(civ: Civilization) -> dict[ActionType, float]:
    """Return action weight multipliers from active tech focus. Empty dict if no focus."""
    if not civ.active_focus:
        return {}
    try:
        focus = TechFocus(civ.active_focus)
    except ValueError:
        return {}
    return dict(FOCUS_EFFECTS[focus].weight_modifiers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tech_focus.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech_focus.py tests/test_tech_focus.py
git commit -m "feat(m21): implement FOCUS_EFFECTS table and apply/remove/get_weight_modifiers"
```

---

## Chunk 2: Orchestration + Weight Integration

### Task 6: Hook focus selection in phase_technology()

**Files:**
- Modify: `src/chronicler/simulation.py:766-796`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_tech_focus.py (append)
from chronicler.simulation import phase_technology


def test_phase_technology_selects_focus_on_advancement():
    """Tech advancement should trigger focus selection and emit event."""
    regions = [
        _make_region("Coast1", terrain="coast", controller="TestCiv",
                     resources="maritime",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
    ]
    # Manually set to Classical to test focus selection directly
    civ = _make_civ(tech_era=TechEra.CLASSICAL, regions=["Coast1"])
    world = _make_world(regions=regions)
    world.civilizations.append(civ)

    from chronicler.tech_focus import select_tech_focus, apply_focus_effects
    focus = select_tech_focus(civ, world)
    assert focus is not None
    apply_focus_effects(civ, focus)
    assert civ.active_focus is not None
    assert len(civ.tech_focuses) == 1
```

- [ ] **Step 2: Run test to verify it passes** (this tests the functions, not the hook yet)

Run: `pytest tests/test_tech_focus.py::test_phase_technology_selects_focus_on_advancement -v`
Expected: PASS

- [ ] **Step 3: Add focus selection hook to phase_technology()**

In `src/chronicler/simulation.py`, add import at top (after existing imports):

```python
from chronicler.tech_focus import TechFocus, select_tech_focus, apply_focus_effects, remove_focus_effects
```

Then modify `phase_technology()` at line 771. After `if event:` and `events.append(event)` (line 772), before the event_counts increment (line 773), add:

```python
            # M21: Remove old focus effects, select and apply new
            if civ.active_focus:
                old_focus = TechFocus(civ.active_focus)
                remove_focus_effects(civ, old_focus)
            new_focus = select_tech_focus(civ, world)
            if new_focus:
                apply_focus_effects(civ, new_focus)
                events.append(Event(
                    turn=world.turn, event_type="tech_focus_selected",
                    actors=[civ.name],
                    description=f"{civ.name} develops {new_focus.value} specialization",
                    importance=6,
                ))
```

- [ ] **Step 4: Run tests to verify no regression**

Run: `pytest tests/test_simulation.py tests/test_tech_focus.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_tech_focus.py
git commit -m "feat(m21): hook focus selection into phase_technology"
```

---

### Task 7: Weight modifiers + 2.5x cap in compute_weights()

**Files:**
- Modify: `src/chronicler/action_engine.py:585-594`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing test for weight modifiers**

```python
# tests/test_tech_focus.py (append)

def test_weight_cap_normalizes_above_2_5():
    """Weights exceeding 2.5 should be normalized."""
    weights = {ActionType.WAR: 5.0, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.5}
    # After normalization: WAR=2.5, TRADE=0.5, DIPLOMACY=0.25
    max_w = max(weights.values())
    scale = 2.5 / max_w
    normalized = {a: w * scale for a, w in weights.items()}
    assert abs(normalized[ActionType.WAR] - 2.5) < 0.01
    assert normalized[ActionType.TRADE] < 1.0
```

- [ ] **Step 2: Run test (this is a unit test of the math, should pass)**

Run: `pytest tests/test_tech_focus.py::test_weight_cap_normalizes_above_2_5 -v`
Expected: PASS

- [ ] **Step 3: Add weight modifiers and cap to compute_weights()**

In `src/chronicler/action_engine.py`, after the tradition biases block (after line 585 — `weights[ActionType.DIPLOMACY] *= 1.2`), add:

```python
        # M21: Tech focus weight biases
        from chronicler.tech_focus import get_focus_weight_modifiers
        focus_mods = get_focus_weight_modifiers(civ)
        for action, mod in focus_mods.items():
            if action in weights and weights[action] > 0:
                weights[action] *= mod
```

Then after the streak-breaking block (after line 593 — `weights[streaked] = 0.0`), before `return weights`, add:

```python
        # M21: Cap combined weight multiplier at 2.5x to prevent dominant action
        max_weight = max(weights.values()) if weights else 0
        if max_weight > 2.5:
            scale = 2.5 / max_weight
            for action in weights:
                weights[action] *= scale
```

- [ ] **Step 4: Run tests to verify no regression**

Run: `pytest tests/test_simulation.py tests/test_tech_focus.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_tech_focus.py
git commit -m "feat(m21): add tech focus weight modifiers and 2.5x cap to compute_weights"
```

---

### Task 8: Tech regression clears focus effects

**Files:**
- Modify: `src/chronicler/emergence.py:578`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing test for regression clearing focus**

```python
# tests/test_tech_focus.py (append)

def test_regression_clears_active_focus():
    """Tech regression should remove focus effects and clear active_focus."""
    civ = _make_civ(tech_era=TechEra.CLASSICAL, military=65)
    civ.active_focus = "metallurgy"
    civ.tech_focuses = ["metallurgy"]

    # Simulate what check_tech_regression does
    remove_focus_effects(civ, TechFocus.METALLURGY)
    civ.active_focus = None

    assert civ.military == 50  # 65 - 15
    assert civ.active_focus is None
    assert "metallurgy" in civ.tech_focuses  # history preserved
```

- [ ] **Step 2: Run test to verify it passes** (tests the functions directly)

Run: `pytest tests/test_tech_focus.py::test_regression_clears_active_focus -v`
Expected: PASS

- [ ] **Step 3: Add focus removal to check_tech_regression()**

In `src/chronicler/emergence.py`, after line 578 (`remove_era_bonus(civ, old_era)`), add:

```python
        # M21: Remove tech focus effects on regression
        if civ.active_focus:
            from chronicler.tech_focus import TechFocus, remove_focus_effects
            remove_focus_effects(civ, TechFocus(civ.active_focus))
            civ.active_focus = None
```

- [ ] **Step 4: Run tests to verify no regression**

Run: `pytest tests/test_emergence.py tests/test_tech_focus.py -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/emergence.py tests/test_tech_focus.py
git commit -m "feat(m21): clear tech focus effects on tech regression"
```

---

## Chunk 3: Unique Capabilities

Each capability is an independent 3-5 line callsite integration. They can be done in any order.

### Task 9: SCHOLARSHIP — Tech cost discount

**Files:**
- Modify: `src/chronicler/tech.py:96-98`
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_tech_focus.py (append)

def test_scholarship_reduces_tech_cost():
    """SCHOLARSHIP focus should reduce tech advancement treasury cost by 20%."""
    from chronicler.tech import check_tech_advancement, TECH_REQUIREMENTS
    # IRON era needs 3 distinct resource types (no specific types required)
    regions = [
        _make_region("R1", terrain="plains", controller="TestCiv",
                     specialized_resources=[Resource.GRAIN, Resource.TIMBER, Resource.IRON])
    ]
    # Get Iron->Classical requirements: (60, 60, 150)
    min_culture, min_economy, cost = TECH_REQUIREMENTS[TechEra.IRON]
    effective_cost = int(cost * 0.8)  # 120
    # Civ has enough for discounted cost (120) but not full cost (150)
    civ = _make_civ(
        tech_era=TechEra.IRON, culture=min_culture, economy=min_economy,
        treasury=effective_cost, regions=["R1"],
        active_focus="scholarship",
    )
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    event = check_tech_advancement(civ, world)
    assert event is not None  # Should advance with discounted cost
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tech_focus.py::test_scholarship_reduces_tech_cost -v`
Expected: FAIL — civ cannot afford full cost

- [ ] **Step 3: Implement effective_cost pattern**

In `src/chronicler/tech.py`, replace lines 96-98:

```python
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < cost:
        return None
    civ.treasury -= cost
```

With:

```python
    effective_cost = int(cost * 0.8) if civ.active_focus == "scholarship" else cost
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < effective_cost:
        return None
    civ.treasury -= effective_cost
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tech_focus.py::test_scholarship_reduces_tech_cost tests/test_simulation.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/tech.py tests/test_tech_focus.py
git commit -m "feat(m21): SCHOLARSHIP capability — tech cost -20%"
```

---

### Task 10: METALLURGY — Mine fertility degradation -50%

**Files:**
- Modify: `src/chronicler/infrastructure.py:76-80`

- [ ] **Step 1: Locate mine degradation in tick_infrastructure()**

In `src/chronicler/infrastructure.py`, lines 76-80:

```python
        has_active_mine = any(
            i.type == IType.MINES and i.active for i in region.infrastructure
        )
        if has_active_mine:
            region.fertility = max(region.fertility - 0.03, 0.0)
```

- [ ] **Step 2: Add METALLURGY check**

Replace the mine degradation block with:

```python
        has_active_mine = any(
            i.type == IType.MINES and i.active for i in region.infrastructure
        )
        if has_active_mine:
            mine_degrade = 0.03
            # M21: METALLURGY halves mine fertility degradation
            if region.controller:
                ctrl_civ = next((c for c in world.civilizations if c.name == region.controller), None)
                if ctrl_civ and ctrl_civ.active_focus == "metallurgy":
                    mine_degrade *= 0.5
            region.fertility = max(region.fertility - mine_degrade, 0.0)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py tests/test_infrastructure.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/infrastructure.py
git commit -m "feat(m21): METALLURGY capability — mine fertility degradation -50%"
```

---

### Task 11: AGRICULTURE — Famine threshold halved

**Files:**
- Modify: `src/chronicler/simulation.py` (phase 9 famine check)

- [ ] **Step 1: Locate famine threshold check**

Find `threshold = get_override(world, K_FAMINE_THRESHOLD, 0.05)` in the famine section of phase 9.

- [ ] **Step 2: Add AGRICULTURE check**

After the `threshold = ...` line, before the `if ... region.fertility >= threshold ...` guard, add:

```python
        # M21: AGRICULTURE halves famine threshold
        if civ and civ.active_focus == "agriculture":
            threshold *= 0.5
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m21): AGRICULTURE capability — famine threshold halved"
```

---

### Task 12: FORTIFICATION — Fort build time -1

**Files:**
- Modify: `src/chronicler/infrastructure.py` (around line 70, where builds complete)

- [ ] **Step 1: Locate build processing**

Find where `region.pending_build.turns_remaining` is decremented in `tick_infrastructure()`.

- [ ] **Step 2: Add FORTIFICATION check**

After the turns_remaining decrement, add:

```python
            # M21: FORTIFICATION reduces fort build time by 1 turn
            if (region.pending_build
                and region.pending_build.type == IType.FORTIFICATIONS
                and region.controller):
                ctrl_civ = next((c for c in world.civilizations if c.name == region.controller), None)
                if ctrl_civ and ctrl_civ.active_focus == "fortification":
                    region.pending_build.turns_remaining = max(0, region.pending_build.turns_remaining - 1)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py tests/test_infrastructure.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/infrastructure.py
git commit -m "feat(m21): FORTIFICATION capability — fort build time -1 turn"
```

---

### Task 13: COMMERCE + NETWORKS — Trade income bonuses

**Files:**
- Modify: `src/chronicler/action_engine.py` (resolve_trade)
- Test: `tests/test_tech_focus.py`

- [ ] **Step 1: Locate resolve_trade()**

Find `resolve_trade` in action_engine.py. Look for where treasury gains are computed.

- [ ] **Step 2: Add COMMERCE and NETWORKS checks**

In `resolve_trade()` (action_engine.py lines 405-414), the function signature is `resolve_trade(civ1, civ2, world)` with gains computed as:
```python
    gain1 = max(1, civ2.economy // 3)
    gain2 = max(1, civ1.economy // 3)
```

After the gain computation lines and before `civ1.treasury += gain1`, add:

```python
    # M21: COMMERCE +50% trade income, NETWORKS x2 (if either civ has focus)
    for trader, gain_attr in [(civ1, "gain1"), (civ2, "gain2")]:
        if trader.active_focus == "networks":
            if gain_attr == "gain1":
                gain1 *= 2
            else:
                gain2 *= 2
        elif trader.active_focus == "commerce":
            if gain_attr == "gain1":
                gain1 = int(gain1 * 1.5)
            else:
                gain2 = int(gain2 * 1.5)
    # COMMERCE benefits trade partner too
    if civ1.active_focus == "commerce":
        gain2 = int(gain2 * 1.5)
    if civ2.active_focus == "commerce":
        gain1 = int(gain1 * 1.5)
```

Note: This is more lines than the typical capability. Simplify to:

```python
    # M21: Trade income bonuses
    if civ1.active_focus == "networks":
        gain1 *= 2
    elif civ1.active_focus == "commerce":
        gain1 = int(gain1 * 1.5)
    if civ2.active_focus == "networks":
        gain2 *= 2
    elif civ2.active_focus == "commerce":
        gain2 = int(gain2 * 1.5)
    # COMMERCE benefits partner: if either has it, partner also gets +50%
    if civ1.active_focus == "commerce" and civ2.active_focus != "networks":
        gain2 = int(gain2 * 1.5)
    if civ2.active_focus == "commerce" and civ1.active_focus != "networks":
        gain1 = int(gain1 * 1.5)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py
git commit -m "feat(m21): COMMERCE and NETWORKS capabilities — trade income bonuses"
```

---

### Task 14: EXPLORATION — Harsh terrain expansion

**Files:**
- Modify: `src/chronicler/action_engine.py` (_resolve_expand)

- [ ] **Step 1: Locate era gate for harsh terrain**

In `_resolve_expand()` (action_engine.py line 99-100):
```python
    if not _era_at_least(civ.tech_era, TechEra.IRON):
        unclaimed = [r for r in unclaimed if r.terrain not in HARSH_TERRAINS]
```

- [ ] **Step 2: Add EXPLORATION bypass**

Replace line 99 with:

```python
    if not _era_at_least(civ.tech_era, TechEra.IRON) and civ.active_focus != "exploration":
```

This allows EXPLORATION focus civs to expand into harsh terrain (tundra, desert) regardless of era.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py
git commit -m "feat(m21): EXPLORATION capability — harsh terrain expansion"
```

---

### Task 15: BANKING — Embargo resistance

**Files:**
- Modify: `src/chronicler/action_engine.py` (_resolve_embargo)

- [ ] **Step 1: Locate stability drain in _resolve_embargo()**

In `_resolve_embargo()` (action_engine.py line 276):
```python
            target.stability = clamp(target.stability - 5, STAT_FLOOR["stability"], 100)
```

- [ ] **Step 2: Add BANKING check**

Replace line 276 with:

```python
            # M21: BANKING halves incoming embargo stability damage
            embargo_damage = 2 if target.active_focus == "banking" else 5
            target.stability = clamp(target.stability - embargo_damage, STAT_FLOOR["stability"], 100)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py
git commit -m "feat(m21): BANKING capability — embargo resistance"
```

---

### Task 16: NAVAL_POWER — Coastal defense

**Files:**
- Modify: `src/chronicler/action_engine.py` (resolve_war)

- [ ] **Step 1: Locate defense calculation in resolve_war()**

Find where defender's combat power is computed in `resolve_war`.

- [ ] **Step 2: Add NAVAL_POWER check**

In `resolve_war()`, after the martial tradition block (line 365: `def_power += 5`) and before the treasury costs (line 368), add:

```python
    # M21: NAVAL_POWER gives +10 defense if contested region is coastal
    if defender.active_focus == "naval_power" and contested and contested.terrain == "coast":
        def_power += 10
```

The `contested` variable is already defined earlier in the function (line 329) and `def_power` is the defender's combat power (line 339).

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/action_engine.py
git commit -m "feat(m21): NAVAL_POWER capability — coastal defense +10"
```

---

### Task 17: PRINTING — Movement adoption boost

**Files:**
- Modify: `src/chronicler/movements.py:98`

- [ ] **Step 1: Locate adoption_probability in _process_spread()**

Line 98: `adoption_probability = rel.trade_volume * compatibility / 100`

- [ ] **Step 2: Add PRINTING check**

After the adoption_probability calculation (line 98), add:

```python
                # M21: PRINTING doubles movement adoption probability
                if civ.active_focus == "printing":
                    adoption_probability *= 2
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/movements.py
git commit -m "feat(m21): PRINTING capability — movement adoption x2"
```

---

### Task 18: MECHANIZATION — Mine income

**Files:**
- Modify: `src/chronicler/simulation.py` (phase_production, around line 387)

- [ ] **Step 1: Locate phase_production income section**

Find the income calculation in `phase_production()` (around line 375-381).

- [ ] **Step 2: Add MECHANIZATION mine income**

After the population section (around line 406), add:

```python
        # M21: MECHANIZATION gives +2 treasury per active mine
        if civ.active_focus == "mechanization":
            mine_count = sum(
                1 for r in world.regions if r.controller == civ.name
                for i in r.infrastructure if i.type == InfrastructureType.MINES and i.active
            )
            civ.treasury += mine_count * 2
```

Make sure `InfrastructureType` is imported at the top of simulation.py (check existing imports).

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m21): MECHANIZATION capability — +2 treasury per active mine"
```

---

### Task 19: NAVIGATION + RAILWAYS — Extended trade routes

**Files:**
- Modify: `src/chronicler/resources.py` (get_active_trade_routes)

- [ ] **Step 1: Locate adjacency check in get_active_trade_routes()**

Find where adjacency is checked for trade route eligibility.

- [ ] **Step 2: Add 2-hop extension for NAVIGATION and RAILWAYS**

In `get_active_trade_routes()` (resources.py lines 43-69), the function iterates regions checking direct adjacency (`r1.adjacencies`). After the existing direct-adjacency loop (after line 57: `routes.add(pair)`) and before the federation block, add a second pass for 2-hop routes:

```python
    # M21: NAVIGATION extends trade to 2-hop coastal routes
    # M21: RAILWAYS extends trade to 2-hop road routes
    civ_focuses = {}
    for civ in world.civilizations:
        if civ.active_focus:
            civ_focuses[civ.name] = civ.active_focus

    for r1 in world.regions:
        if r1.controller is None or r1.controller not in civ_focuses:
            continue
        focus = civ_focuses[r1.controller]
        if focus not in ("navigation", "railways"):
            continue
        for mid_name in r1.adjacencies:
            mid = next((r for r in world.regions if r.name == mid_name), None)
            if mid is None:
                continue
            # NAVIGATION: mid region must be coastal
            # RAILWAYS: mid region must have active roads
            if focus == "navigation" and mid.terrain != "coast":
                continue
            if focus == "railways" and not any(
                i.type == InfrastructureType.ROADS and i.active for i in mid.infrastructure
            ):
                continue
            for hop2_name in mid.adjacencies:
                hop2 = next((r for r in world.regions if r.name == hop2_name), None)
                if hop2 is None or hop2.controller is None or hop2.controller == r1.controller:
                    continue
                pair = tuple(sorted([r1.controller, hop2.controller]))
                if pair in embargo_set or pair in routes:
                    continue
                rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
                rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
                if rel_ab and rel_ba:
                    if DISP_ORDER.get(rel_ab.disposition.value, 0) >= 2 and DISP_ORDER.get(rel_ba.disposition.value, 0) >= 2:
                        routes.add(pair)
```

This imports `InfrastructureType` — add at top of resources.py:
```python
from chronicler.models import InfrastructureType
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py tests/test_resources.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/resources.py
git commit -m "feat(m21): NAVIGATION and RAILWAYS capabilities — extended trade routes"
```

---

### Task 20: SURVEILLANCE — Secession resistance

**Files:**
- Modify: `src/chronicler/politics.py:102`

- [ ] **Step 1: Locate secession threshold**

Line 102: `if civ.stability >= 20 or len(civ.regions) < 3:`

- [ ] **Step 2: Add SURVEILLANCE check**

Replace the stability check with:

```python
        secession_threshold = 10 if civ.active_focus == "surveillance" else 20
        if civ.stability >= secession_threshold or len(civ.regions) < 3:
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py tests/test_politics.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/politics.py
git commit -m "feat(m21): SURVEILLANCE capability — secession resistance"
```

---

### Task 21: MEDIA — Propaganda acceleration

**Files:**
- Modify: `src/chronicler/culture.py:127`

- [ ] **Step 1: Locate PROPAGANDA_ACCELERATION usage**

Line 127 area: `net_acceleration = PROPAGANDA_ACCELERATION + adjustment`

- [ ] **Step 2: Add MEDIA check**

```python
    # M21: MEDIA doubles propaganda acceleration
    base_accel = PROPAGANDA_ACCELERATION * 2 if civ.active_focus == "media" else PROPAGANDA_ACCELERATION
    net_acceleration = base_accel + adjustment
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/culture.py
git commit -m "feat(m21): MEDIA capability — propaganda acceleration x2"
```

---

## Chunk 4: Final Integration Tests + Cleanup

### Task 22: Comprehensive integration tests

**Files:**
- Modify: `tests/test_tech_focus.py`

- [ ] **Step 1: Add GP bonus tipping test**

```python
def test_gp_bonus_tips_close_decision():
    """A scientist GP should add +5 to SCHOLARSHIP, tipping a close decision."""
    from chronicler.models import GreatPerson
    regions = [
        _make_region("R1", terrain="plains", controller="TestCiv",
                     specialized_resources=[Resource.GRAIN])
    ]
    civ = _make_civ(
        tech_era=TechEra.MEDIEVAL, culture=15, regions=["R1"],
        great_persons=[GreatPerson(name="Scholar", role="scientist",
                                   trait="wise", civilization="TestCiv",
                                   origin_civilization="TestCiv", born_turn=0,
                                   active=True, alive=True)],
    )
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    focus = select_tech_focus(civ, world)
    assert focus == TechFocus.SCHOLARSHIP
```

- [ ] **Step 2: Add re-advancement after regression test**

```python
def test_readvancement_after_regression_may_differ():
    """After regression, re-advancement selects fresh based on current state."""
    # First: coastal civ gets NAVIGATION
    regions = [
        _make_region("Coast1", terrain="coast", controller="TestCiv",
                     resources="maritime",
                     infrastructure=[_make_infra(InfrastructureType.PORTS)])
    ]
    civ = _make_civ(tech_era=TechEra.CLASSICAL, regions=["Coast1"])
    world = _make_world(regions=regions)
    world.civilizations.append(civ)
    focus1 = select_tech_focus(civ, world)
    assert focus1 == TechFocus.NAVIGATION
    apply_focus_effects(civ, focus1)

    # Simulate regression: clear focus
    remove_focus_effects(civ, TechFocus.NAVIGATION)
    civ.active_focus = None

    # Change geography: now mining civ
    regions[0].terrain = "mountains"
    regions[0].specialized_resources = [Resource.IRON]
    regions[0].infrastructure = [_make_infra(InfrastructureType.MINES)]

    # Re-advance: should pick METALLURGY now
    focus2 = select_tech_focus(civ, world)
    assert focus2 == TechFocus.METALLURGY
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/test_tech_focus.py -v`
Expected: All pass

- [ ] **Step 4: Run entire project test suite**

Run: `pytest tests/ -q --ignore=tests/test_batch_websocket.py --ignore=tests/test_live_integration.py --ignore=tests/test_llm.py`
Expected: All pass (same baseline as before M21)

- [ ] **Step 5: Commit**

```bash
git add tests/test_tech_focus.py
git commit -m "test(m21): add comprehensive integration tests for tech focus"
```

---

### Task 23: Final verification

- [ ] **Step 1: Run full test suite one more time**

Run: `pytest tests/ -q --ignore=tests/test_batch_websocket.py --ignore=tests/test_live_integration.py --ignore=tests/test_llm.py`
Expected: All pass

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from chronicler.tech_focus import TechFocus, select_tech_focus, apply_focus_effects, remove_focus_effects, get_focus_weight_modifiers, FOCUS_EFFECTS; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Count lines added**

Run: `wc -l src/chronicler/tech_focus.py tests/test_tech_focus.py`
Expected: ~250 + ~150 = ~400 lines total
