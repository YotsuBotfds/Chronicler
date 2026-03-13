# M13: Resource Foundations & Economic Dynamics — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the simulation material economic foundations — resources, trade routes, treasury mechanics, and emergent economic events — so that civ behavior is shaped by geography and economics, not just stat thresholds.

**Architecture:** Six sequential phases (P1→P2→P3→M13a→M13b-1→M13b-2), each independently testable. All changes are pure Python simulation — no LLM calls. New modules: `adjacency.py`, `resources.py`. Existing modules modified: `models.py`, `simulation.py`, `action_engine.py`, `tech.py`, `utils.py`, `scenario.py`, `main.py`, `bundle.py`. Viewer types updated but no new components.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, TypeScript/React (viewer types only)

**Spec:** `docs/superpowers/specs/2026-03-13-m13-resource-economics-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/chronicler/resources.py` | Terrain probability table, auto-generation, trade route computation (Resource enum lives in models.py to avoid circular imports) |
| `src/chronicler/adjacency.py` | Adjacency computation (k-nearest, sea routes), graph utilities (BFS, shortest_path, chokepoint) |
| `tests/test_adjacency.py` | Tests for adjacency module |
| `tests/test_resources.py` | Tests for resource module |

### Modified Files
| File | Changes |
|------|---------|
| `src/chronicler/utils.py` | Add `STAT_FLOOR` dict |
| `src/chronicler/models.py` | Scale stat bounds 0-100, add Resource enum, add Region fields (adjacencies, specialized_resources, fertility, infrastructure_level, famine_cooldown), add WorldState fields (embargoes, active_wars, mercenary_companies), add MercenaryCompany model, add Civ fields (last_income, merc_pressure_turns), INFORMATION era, CivSnapshot/TurnSnapshot extensions |
| `src/chronicler/simulation.py` | Scale all thresholds ×10, update clamp calls to use STAT_FLOOR, add phases (automatic_effects, fertility), restructure run_turn to 10 phases |
| `src/chronicler/action_engine.py` | Scale thresholds ×10, add registration pattern, ActionCategory enum, BUILD/EMBARGO enum variants + weight profiles, eligibility checks |
| `src/chronicler/tech.py` | Scale requirements/bonuses ×10, add INFORMATION era, add resource diversity gate |
| `src/chronicler/events.py` | Scale severity ×10 |
| `src/chronicler/scenario.py` | Scale model bounds, add RegionOverride fields (adjacencies, specialized_resources, fertility), apply new fields in apply_scenario |
| `src/chronicler/world_gen.py` | Scale stat/capacity template values ×10, scale randint ranges ×10, call compute_adjacencies after region placement, call assign_resources |
| `src/chronicler/main.py` | Add `--simulate-only` flag, no-op narrator path |
| `src/chronicler/bundle.py` | Add TurnSnapshot fields (trade_routes, active_wars, embargoes, fertility, mercenary_companies), CivSnapshot fields (last_income, active_trade_routes) |
| `tests/conftest.py` | Scale fixture stat values ×10 |
| `tests/test_simulation.py` | Scale all assertion values ×10 |
| `tests/test_action_engine.py` | Scale thresholds ×10, test registration pattern |
| `tests/test_tech.py` | Scale thresholds ×10, test resource diversity gate, test INFORMATION era |
| `tests/test_scenario.py` | Scale values ×10, test new fields |
| `tests/test_models.py` | Scale bounds tests ×10 |
| `tests/test_events.py` | Scale severity ×10 |
| `tests/test_e2e.py` | Scale values ×10 |
| `tests/test_bundle.py` | Test new snapshot fields |
| `tests/test_main.py` | Test --simulate-only flag |
| `scenarios/*.yaml` | All 6 files: stats ×10, add specialized_resources, adjacencies, fertility where appropriate |
| `viewer/src/types.ts` | Add INFORMATION to TechEra, add new TurnSnapshot fields |
| `viewer/src/lib/format.ts` | Add INFORMATION to ERA_ORDER |

---

## Chunk 1: Phase P1 — Stat Scale Migration

### Task 1: Add STAT_FLOOR and scale utils.py

**Files:**
- Modify: `src/chronicler/utils.py`
- Test: `tests/test_models.py` (existing, will update bounds)

- [ ] **Step 1: Add STAT_FLOOR to utils.py**

```python
# In src/chronicler/utils.py, add after clamp():
STAT_FLOOR: dict[str, int] = {
    "population": 1,
    "military": 0,
    "economy": 0,
    "culture": 0,
    "stability": 0,
}
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/utils.py
git commit -m "feat(p1): add STAT_FLOOR dict to utils"
```

### Task 2: Scale model bounds in models.py

**Files:**
- Modify: `src/chronicler/models.py:67-89` (Civilization), `models.py:45-52` (Region), `models.py:127-131` (ActiveCondition), `models.py:167-180` (CivSnapshot)

- [ ] **Step 1: Write failing test — Civilization accepts 0-100 stats**

```python
# In tests/test_models.py, add:
def test_civilization_accepts_scaled_stats():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test", population=60, military=0, economy=70,
        culture=50, stability=0, leader=leader,
    )
    assert civ.population == 60
    assert civ.military == 0
    assert civ.stability == 0

def test_civilization_rejects_population_zero():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    import pytest
    with pytest.raises(Exception):
        Civilization(name="Test", population=0, military=50, economy=50,
                     culture=50, stability=50, leader=leader)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_civilization_accepts_scaled_stats tests/test_models.py::test_civilization_rejects_population_zero -v`
Expected: FAIL (current bounds reject values > 10 and allow ge=1 for military)

- [ ] **Step 3: Update Civilization field bounds**

In `models.py`, change Civilization fields:
```python
population: int = Field(ge=1, le=100)
military: int = Field(ge=0, le=100)
economy: int = Field(ge=0, le=100)
culture: int = Field(ge=0, le=100)
stability: int = Field(ge=0, le=100)
```

Also update `Region.carrying_capacity`:
```python
carrying_capacity: int = Field(ge=1, le=100)
```

Update `ActiveCondition.severity`:
```python
severity: int = Field(ge=1, le=100)
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `pytest tests/test_models.py::test_civilization_accepts_scaled_stats tests/test_models.py::test_civilization_rejects_population_zero -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_models.py
git commit -m "feat(p1): scale Civilization/Region/ActiveCondition bounds to 0-100"
```

### Task 3: Scale scenario.py model bounds

**Files:**
- Modify: `src/chronicler/scenario.py:37-60` (RegionOverride, CivOverride)

- [ ] **Step 1: Update RegionOverride and CivOverride bounds**

In `scenario.py`:
```python
class RegionOverride(BaseModel):
    name: str
    terrain: str | None = None
    carrying_capacity: int | None = Field(default=None, ge=1, le=100)
    resources: str | None = None
    controller: str | None = None
    x: float | None = None
    y: float | None = None

class CivOverride(BaseModel):
    name: str
    population: int | None = Field(default=None, ge=1, le=100)
    military: int | None = Field(default=None, ge=0, le=100)
    economy: int | None = Field(default=None, ge=0, le=100)
    culture: int | None = Field(default=None, ge=0, le=100)
    stability: int | None = Field(default=None, ge=0, le=100)
    # ... rest unchanged
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/scenario.py
git commit -m "feat(p1): scale scenario override bounds to 0-100"
```

### Task 4: Scale test fixtures in conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Read conftest.py and scale all stat values ×10**

Every fixture that creates Civilizations, Regions, or ActiveConditions needs stats ×10. `carrying_capacity` values ×10. `severity` values ×10. Treasury values that represent absolute amounts ×10.

- [ ] **Step 2: Run full test suite to see what breaks**

Run: `pytest --tb=short -q`
Expected: Many failures from assertion mismatches — this is the baseline for the migration.

- [ ] **Step 3: Commit fixtures**

```bash
git add tests/conftest.py
git commit -m "feat(p1): scale test fixture stat values ×10"
```

### Task 5: Scale simulation.py thresholds and clamp calls

**Files:**
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Import STAT_FLOOR**

Add to imports in simulation.py:
```python
from chronicler.utils import clamp, STAT_FLOOR
```

- [ ] **Step 2: Scale all thresholds ×10 and update clamp calls**

Apply the complete clamp callsite inventory from the spec (spec lines 78-118). Every `clamp(x, 1, 10)` becomes `clamp(x, STAT_FLOOR[stat], 100)` with the appropriate stat key. Every hardcoded threshold (stability <= 2, military >= 3, population >= 8, etc.) scales ×10 per spec lines 124-134.

Key changes:
- `phase_environment`: event stat deltas `±1` → `±10`, `±2` → `±20`
- `phase_production`: income formula `economy + len(regions)` → `economy + len(regions) * 10`, maintenance `military // 2` stays proportional, population thresholds scale, remove treasury cap entirely, growth/decline `±1` → `±5`, max_pop uses `min(100, region_capacity)`, condition penalty `severity // 3` → `severity` directly (**note: this is a formula change, not just scaling — at old scale severity=5 gave penalty 1; at new scale severity=50 gives penalty 50; this is intentional per spec but dramatically increases condition impact; M13b-1 rebalances income to compensate**)
- `_resolve_develop`: cost `3` → `30`, stat increments `+1` → `+10`
- `_resolve_expand`: military threshold `>= 3` → `>= 30`, military cost `-1` → `-10`
- `resolve_war`: military costs `-1`/`-2` → `-10`/`-20`, stability costs `-1` → `-10`, treasury costs `-2`/`-1` → `-20`/`-10`
- `_resolve_diplomacy`: culture threshold `>= 3` → `>= 30`
- `phase_consequences`: collapse thresholds `stability <= 2` → `<= 20`
- `_apply_event_effects`: all `±1`/`±2` → `±10`/`±20`
- `_apply_situational` in action_engine: thresholds scale ×10

- [ ] **Step 3: Scale action_engine.py thresholds**

Update `action_engine.py` thresholds per spec lines 136-142.

- [ ] **Step 4: Scale tech.py requirements and bonuses**

```python
TECH_REQUIREMENTS: dict[TechEra, tuple[int, int, int]] = {
    TechEra.TRIBAL: (40, 40, 100),
    TechEra.BRONZE: (50, 50, 120),
    TechEra.IRON: (60, 60, 150),
    TechEra.CLASSICAL: (70, 70, 180),
    TechEra.MEDIEVAL: (80, 80, 220),
    TechEra.RENAISSANCE: (90, 90, 280),
}

ERA_BONUSES: dict[TechEra, dict[str, int | float]] = {
    TechEra.BRONZE: {"military": 10},
    TechEra.IRON: {"economy": 10},
    TechEra.CLASSICAL: {"culture": 10},
    TechEra.MEDIEVAL: {"military": 10},
    TechEra.RENAISSANCE: {"economy": 20, "culture": 10},
    TechEra.INDUSTRIAL: {"economy": 20, "military": 20},
}
```

Update `apply_era_bonus` to use STAT_FLOOR:
```python
from chronicler.utils import clamp, STAT_FLOOR
# ...
setattr(civ, stat, clamp(current + amount, STAT_FLOOR.get(stat, 0), 100))
```

- [ ] **Step 5: Commit all scaled source files**

```bash
git add src/chronicler/simulation.py src/chronicler/action_engine.py src/chronicler/tech.py
git commit -m "feat(p1): scale all thresholds ×10, update clamp calls to use STAT_FLOOR"
```

### Task 6: Scale all test assertions

**Files:**
- Modify: `tests/test_simulation.py`, `tests/test_action_engine.py`, `tests/test_tech.py`, `tests/test_events.py`, `tests/test_scenario.py`, `tests/test_e2e.py`, `tests/test_bundle.py`, `tests/test_main.py`, and any other test files with absolute stat assertions

- [ ] **Step 1: Scale test assertions ×10**

Every assertion checking absolute stat values (e.g., `assert civ.military == 5` → `assert civ.military == 50`) gets ×10. Relative comparisons stay unchanged. Treasury values in assertions that represent absolute amounts ×10.

- [ ] **Step 2: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "feat(p1): scale all test assertions ×10"
```

### Task 6b: Scale world_gen.py template values and ranges

**Files:**
- Modify: `src/chronicler/world_gen.py`

Without this, `generate_world()` called without a scenario produces civs with stats 2-8 on a 0-100 scale — completely degenerate. This is the most likely-to-be-missed step in the migration.

- [ ] **Step 1: Scale REGION_TEMPLATES carrying_capacity ×10**

Every template entry's `carrying_capacity` (currently 2-8) becomes ×10 (20-80).

- [ ] **Step 2: Scale assign_civilizations stat generation ×10**

`rng.randint(3, 7)` → `rng.randint(30, 70)` for population, military, economy, culture, stability. Treasury `rng.randint(3, 15)` → `rng.randint(30, 150)`. Asabiya stays unchanged (0.4-0.8).

- [ ] **Step 3: Scale CIV_TEMPLATES starting stats ×10**

Any hardcoded stat values in civilization templates get ×10.

- [ ] **Step 4: Verify with a quick generation test**

Run: `pytest tests/test_world_gen.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py
git commit -m "feat(p1): scale world_gen template values and stat ranges ×10"
```

### Task 7: Scale scenario YAML files

**Files:**
- Modify: All 6 files in `scenarios/`

- [ ] **Step 1: Scale all 6 scenario YAML files**

For each YAML file, multiply ×10: `population`, `military`, `economy`, `culture`, `stability`, `carrying_capacity`, `severity` (in starting_conditions).

Treasury values: scale ×10 if they represent starting amounts.

- [ ] **Step 2: Run scenario-specific tests**

Run: `pytest tests/test_scenario.py -v`
Expected: PASS

- [ ] **Step 3: Run a 50-turn smoke test with each scenario**

Run: `pytest tests/test_e2e.py -v`
(If no scenario smoke test exists, verify manually or add one)

- [ ] **Step 4: Commit**

```bash
git add scenarios/
git commit -m "feat(p1): scale all scenario YAML stat values ×10"
```

### Task 8: P1 verification — full suite

- [ ] **Step 1: Run complete test suite**

Run: `pytest -v`
Expected: All 381+ tests pass

- [ ] **Step 2: Verify no regressions with a quick e2e run**

Run: `pytest tests/test_e2e.py -v`

---

## Chunk 2: Phase P2 — Region Adjacency Graph

### Task 9: Add adjacencies field to Region model

**Files:**
- Modify: `src/chronicler/models.py:45-52`

- [ ] **Step 1: Add adjacencies to Region**

```python
class Region(BaseModel):
    name: str
    terrain: str
    carrying_capacity: int = Field(ge=1, le=100)
    resources: str
    controller: Optional[str] = None
    x: float | None = None
    y: float | None = None
    adjacencies: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(p2): add adjacencies field to Region model"
```

### Task 10: Implement adjacency.py — graph utilities

**Files:**
- Create: `src/chronicler/adjacency.py`
- Create: `tests/test_adjacency.py`

- [ ] **Step 1: Write failing tests for graph utilities**

```python
# tests/test_adjacency.py
from chronicler.adjacency import (
    shortest_path, graph_distance, is_chokepoint, connected_components,
)
from chronicler.models import Region

def _make_regions(names_and_adj: dict[str, list[str]]) -> list[Region]:
    """Helper: create regions with given adjacencies."""
    return [
        Region(name=n, terrain="plains", carrying_capacity=50,
               resources="fertile", adjacencies=adj)
        for n, adj in names_and_adj.items()
    ]

def test_shortest_path_direct():
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert shortest_path(regions, "A", "C") == ["A", "B", "C"]

def test_shortest_path_no_path():
    regions = _make_regions({"A": ["B"], "B": ["A"], "C": []})
    assert shortest_path(regions, "A", "C") is None

def test_graph_distance():
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert graph_distance(regions, "A", "C") == 2
    assert graph_distance(regions, "A", "A") == 0

def test_graph_distance_disconnected():
    regions = _make_regions({"A": [], "B": []})
    assert graph_distance(regions, "A", "B") == -1

def test_is_chokepoint():
    # B is the only connection between A and C
    regions = _make_regions({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    assert is_chokepoint(regions, "B") is True
    assert is_chokepoint(regions, "A") is False

def test_connected_components_single():
    regions = _make_regions({"A": ["B"], "B": ["A"]})
    comps = connected_components(regions)
    assert len(comps) == 1

def test_connected_components_multiple():
    regions = _make_regions({"A": ["B"], "B": ["A"], "C": ["D"], "D": ["C"]})
    comps = connected_components(regions)
    assert len(comps) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_adjacency.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement graph utilities**

```python
# src/chronicler/adjacency.py
"""Region adjacency graph — computation and graph utilities."""
from __future__ import annotations

import math
from collections import deque

from chronicler.models import Region

SEA_ROUTE_TERRAINS = {"coast", "river"}
SEA_ROUTE_RESOURCES = {"maritime"}


def _build_adj_map(regions: list[Region]) -> dict[str, set[str]]:
    """Build adjacency map from region list."""
    return {r.name: set(r.adjacencies) for r in regions}


def shortest_path(
    regions: list[Region], from_name: str, to_name: str,
) -> list[str] | None:
    """BFS shortest path. Returns list of region names or None."""
    if from_name == to_name:
        return [from_name]
    adj = _build_adj_map(regions)
    visited: set[str] = {from_name}
    queue: deque[list[str]] = deque([[from_name]])
    while queue:
        path = queue.popleft()
        for neighbor in adj.get(path[-1], set()):
            if neighbor == to_name:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return None


def graph_distance(
    regions: list[Region], from_name: str, to_name: str,
) -> int:
    """Shortest path length, or -1 if disconnected."""
    path = shortest_path(regions, from_name, to_name)
    if path is None:
        return -1
    return len(path) - 1


def is_chokepoint(regions: list[Region], name: str) -> bool:
    """True if removing this region disconnects the graph (articulation point)."""
    remaining = [r for r in regions if r.name != name]
    if len(remaining) <= 1:
        return False
    # Remove edges to the removed region
    for r in remaining:
        r_copy = r.model_copy()
        r_copy.adjacencies = [a for a in r.adjacencies if a != name]
        remaining[remaining.index(r)] = r_copy
    comps = connected_components(remaining)
    return len(comps) > 1


def connected_components(regions: list[Region]) -> list[list[str]]:
    """Return connected components as lists of region names."""
    adj = _build_adj_map(regions)
    visited: set[str] = set()
    components: list[list[str]] = []
    for r in regions:
        if r.name in visited:
            continue
        component: list[str] = []
        queue: deque[str] = deque([r.name])
        visited.add(r.name)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_adjacency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/adjacency.py tests/test_adjacency.py
git commit -m "feat(p2): implement graph utilities (BFS, shortest_path, chokepoint, components)"
```

### Task 11: Implement compute_adjacencies

**Files:**
- Modify: `src/chronicler/adjacency.py`
- Modify: `tests/test_adjacency.py`

- [ ] **Step 1: Write failing tests for compute_adjacencies**

```python
def test_compute_adjacencies_k_nearest():
    """Regions without adjacencies get k-nearest neighbors."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
        Region(name="C", terrain="plains", carrying_capacity=50,
               resources="fertile", x=2.0, y=0.0),
    ]
    compute_adjacencies(regions, k=2)
    assert "B" in regions[0].adjacencies
    assert "A" in regions[1].adjacencies
    assert "C" in regions[1].adjacencies

def test_compute_adjacencies_preserves_explicit():
    """Scenario-authored adjacencies are preserved."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0, adjacencies=["C"]),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
        Region(name="C", terrain="plains", carrying_capacity=50,
               resources="fertile", x=10.0, y=10.0, adjacencies=["A"]),
    ]
    compute_adjacencies(regions, k=2)
    # A's explicit adjacency to C preserved even though C is far away
    assert "C" in regions[0].adjacencies

def test_compute_adjacencies_sea_routes():
    """Coastal/river regions connect to each other."""
    regions = [
        Region(name="Coast1", terrain="coast", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="Coast2", terrain="coast", carrying_capacity=50,
               resources="fertile", x=100.0, y=100.0),
        Region(name="Inland", terrain="plains", carrying_capacity=50,
               resources="fertile", x=1.0, y=0.0),
    ]
    compute_adjacencies(regions, k=2)
    assert "Coast2" in regions[0].adjacencies  # sea route
    assert "Coast1" in regions[1].adjacencies  # sea route

def test_compute_adjacencies_connectivity_repair():
    """Disconnected regions get connected."""
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50,
               resources="fertile", x=0.0, y=0.0),
        Region(name="B", terrain="plains", carrying_capacity=50,
               resources="fertile", x=100.0, y=100.0),
    ]
    compute_adjacencies(regions, k=1)
    # Must be connected despite k=1 and large distance
    comps = connected_components(regions)
    assert len(comps) == 1

def test_compute_adjacencies_k_nearest_fills_gaps_only():
    """k-nearest only adds edges for under-connected regions."""
    regions = [
        Region(name="Hub", terrain="coast", carrying_capacity=50,
               resources="fertile", x=5.0, y=5.0),
        Region(name="Coast2", terrain="coast", carrying_capacity=50,
               resources="fertile", x=6.0, y=5.0),
        Region(name="Coast3", terrain="coast", carrying_capacity=50,
               resources="fertile", x=7.0, y=5.0),
        Region(name="Inland", terrain="plains", carrying_capacity=50,
               resources="fertile", x=5.0, y=6.0),
    ]
    compute_adjacencies(regions, k=3)
    # Hub already has >=3 connections from sea routes, k-nearest shouldn't pile on
    # Inland should still get connections from k-nearest
    assert len([r for r in regions if r.name == "Inland"][0].adjacencies) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_adjacency.py::test_compute_adjacencies_k_nearest -v`
Expected: FAIL

- [ ] **Step 3: Implement compute_adjacencies**

```python
def _euclidean(r1: Region, r2: Region) -> float:
    """Euclidean distance between two regions with coordinates."""
    x1, y1 = r1.x or 0.0, r1.y or 0.0
    x2, y2 = r2.x or 0.0, r2.y or 0.0
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def _is_sea_route_eligible(region: Region) -> bool:
    return region.terrain in SEA_ROUTE_TERRAINS or region.resources in SEA_ROUTE_RESOURCES


def _add_edge(r1: Region, r2: Region) -> None:
    """Add symmetric adjacency edge."""
    if r2.name not in r1.adjacencies:
        r1.adjacencies.append(r2.name)
    if r1.name not in r2.adjacencies:
        r2.adjacencies.append(r1.name)


def compute_adjacencies(regions: list[Region], k: int = 3) -> None:
    """Compute adjacency graph in-place.

    Order: 1) preserve explicit, 2) sea routes, 3) k-nearest fills gaps, 4) symmetrize, 5) validate connectivity.
    """
    region_by_name = {r.name: r for r in regions}
    has_explicit = {r.name for r in regions if r.adjacencies}

    # Step 2: Sea route pass — eligible regions form clique
    # TODO: Future milestones may replace clique with explicit sea lanes
    sea_eligible = [r for r in regions if _is_sea_route_eligible(r)]
    for i, r1 in enumerate(sea_eligible):
        for r2 in sea_eligible[i + 1:]:
            _add_edge(r1, r2)

    # Step 3: k-nearest fills gaps (only for under-connected regions)
    for r in regions:
        if len(r.adjacencies) >= k:
            continue
        # Sort other regions by distance
        others = [(o, _euclidean(r, o)) for o in regions if o.name != r.name]
        others.sort(key=lambda x: x[1])
        needed = k - len(r.adjacencies)
        for o, _ in others[:needed]:
            if o.name not in r.adjacencies:
                _add_edge(r, o)

    # Step 4: Symmetrize (already done by _add_edge, but ensure)
    for r in regions:
        for adj_name in list(r.adjacencies):
            other = region_by_name.get(adj_name)
            if other and r.name not in other.adjacencies:
                other.adjacencies.append(r.name)

    # Step 5: Validate connectivity — repair if disconnected
    comps = connected_components(regions)
    while len(comps) > 1:
        # Connect nearest pair across first two components
        best_dist = float("inf")
        best_pair: tuple[Region, Region] | None = None
        for n1 in comps[0]:
            for n2 in comps[1]:
                d = _euclidean(region_by_name[n1], region_by_name[n2])
                if d < best_dist:
                    best_dist = d
                    best_pair = (region_by_name[n1], region_by_name[n2])
        if best_pair:
            _add_edge(best_pair[0], best_pair[1])
        comps = connected_components(regions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_adjacency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/adjacency.py tests/test_adjacency.py
git commit -m "feat(p2): implement compute_adjacencies with sea routes, k-nearest, connectivity repair"
```

### Task 12: Wire adjacency into world_gen.py and scenario.py

**Files:**
- Modify: `src/chronicler/world_gen.py`
- Modify: `src/chronicler/scenario.py`
- Modify: `tests/test_world_gen.py`

- [ ] **Step 1: Write failing test — generated world has adjacencies**

```python
# In tests/test_world_gen.py, add:
def test_generated_world_has_adjacencies():
    world = generate_world(seed=42, num_regions=6, num_civs=3)
    for region in world.regions:
        assert len(region.adjacencies) > 0, f"{region.name} has no adjacencies"
    # Must be connected
    from chronicler.adjacency import connected_components
    comps = connected_components(world.regions)
    assert len(comps) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_world_gen.py::test_generated_world_has_adjacencies -v`
Expected: FAIL

- [ ] **Step 3: Add compute_adjacencies call to generate_world**

In `world_gen.py`, after regions are created and before returning WorldState:
```python
from chronicler.adjacency import compute_adjacencies
# ... after regions = generate_regions(...)
compute_adjacencies(regions)
```

- [ ] **Step 4: Add adjacencies field to RegionOverride in scenario.py**

```python
class RegionOverride(BaseModel):
    # ... existing fields ...
    adjacencies: list[str] | None = None
```

In `apply_scenario`, where region overrides are applied, add:
```python
if override.adjacencies is not None:
    region.adjacencies = override.adjacencies
```

After all scenario overrides are applied, call `compute_adjacencies` to fill gaps for regions without explicit adjacencies.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_world_gen.py tests/test_scenario.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/world_gen.py src/chronicler/scenario.py tests/test_world_gen.py
git commit -m "feat(p2): wire compute_adjacencies into world generation and scenario loading"
```

### Task 13: P2 verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

---

## Chunk 3: Phase P3 — Action Engine v2

### Task 14: Add ActionCategory enum and new ActionType variants

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Add ActionCategory and expand ActionType**

```python
class ActionCategory(str, Enum):
    AUTOMATIC = "automatic"
    DELIBERATE = "deliberate"
    REACTION = "reaction"

class ActionType(str, Enum):
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    BUILD = "build"
    EMBARGO = "embargo"
```

- [ ] **Step 2: Commit**

```bash
git add src/chronicler/models.py
git commit -m "feat(p3): add ActionCategory enum and BUILD/EMBARGO to ActionType"
```

### Task 15: Implement registration pattern in action_engine.py

**Files:**
- Modify: `src/chronicler/action_engine.py`
- Modify: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test — registry contains existing actions**

```python
# In tests/test_action_engine.py, add:
from chronicler.action_engine import ACTION_REGISTRY
from chronicler.models import ActionType

def test_action_registry_has_base_actions():
    expected = {ActionType.DEVELOP, ActionType.DIPLOMACY, ActionType.EXPAND,
                ActionType.TRADE, ActionType.WAR}
    assert expected.issubset(set(ACTION_REGISTRY.keys()))

def test_action_registry_no_build_embargo_handlers():
    assert ActionType.BUILD not in ACTION_REGISTRY
    assert ActionType.EMBARGO not in ACTION_REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_engine.py::test_action_registry_has_base_actions -v`
Expected: FAIL

- [ ] **Step 3: Implement registration pattern**

**Key decision: move all action handlers from `simulation.py` to `action_engine.py`.** Currently `_resolve_develop`, `_resolve_expand`, `_resolve_trade_action`, `_resolve_diplomacy`, `_resolve_war_action`, `resolve_war`, and `resolve_trade` all live in `simulation.py`. Move them to `action_engine.py` alongside the registry. This avoids circular imports — `simulation.py` imports `ACTION_REGISTRY` from `action_engine.py` (one direction only), `action_engine.py` imports models/utils but NOT simulation.py.

Helper functions needed by handlers (`_get_civ`, `DISPOSITION_ORDER`, `DISPOSITION_UPGRADE`, `resolve_war`, `resolve_trade`) also move to `action_engine.py`. `simulation.py` keeps phase functions (`phase_action`, `run_turn`, etc.) and calls handlers via the registry.

In `action_engine.py`:
1. Add `ACTION_REGISTRY` dict and `register_action` decorator at module level
2. Add `REACTION_REGISTRY` dict (empty)
3. Move all `_resolve_*` handler functions from `simulation.py`
4. Decorate each with `@register_action(ActionType.XXX)`
5. Export `_resolve_action` dispatcher function

```python
from chronicler.utils import clamp, STAT_FLOOR

ACTION_REGISTRY: dict[ActionType, Callable] = {}
REACTION_REGISTRY: dict[str, Callable] = {}

def register_action(action_type: ActionType):
    def decorator(fn):
        ACTION_REGISTRY[action_type] = fn
        return fn
    return decorator

# Move existing handlers here with decorators:
@register_action(ActionType.DEVELOP)
def _resolve_develop(civ: Civilization, world: WorldState) -> Event:
    # ... existing implementation from simulation.py ...

@register_action(ActionType.WAR)
def _resolve_war_action(civ: Civilization, world: WorldState) -> Event:
    # ... wraps resolve_war internally, uses world.turn as seed ...

# ... same for EXPAND, TRADE, DIPLOMACY ...

def resolve_action(civ: Civilization, action: ActionType, world: WorldState) -> Event:
    handler = ACTION_REGISTRY.get(action)
    if handler:
        return handler(civ, world)
    return Event(
        turn=world.turn, event_type="action", actors=[civ.name],
        description=f"{civ.name} rests.", importance=1,
    )
```

In `simulation.py`, `phase_action` now imports and calls `resolve_action` from `action_engine`:
```python
from chronicler.action_engine import resolve_action
# ...
event = resolve_action(civ, action, world)
```

All handler signatures normalized to `(civ: Civilization, world: WorldState) -> Event`. The WAR handler uses `world.turn` as seed internally.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_action_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(p3): replace action dispatch if/else with registration pattern"
```

### Task 16: Add BUILD/EMBARGO weight profiles and eligibility

**Files:**
- Modify: `src/chronicler/action_engine.py`
- Modify: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test — BUILD and EMBARGO in weight profiles**

```python
def test_trait_weights_include_build_embargo():
    for trait, weights in TRAIT_WEIGHTS.items():
        assert ActionType.BUILD in weights, f"{trait} missing BUILD"
        assert ActionType.EMBARGO in weights, f"{trait} missing EMBARGO"

def test_build_eligible_with_treasury_and_regions(sample_world):
    civ = sample_world.civilizations[0]
    civ.treasury = 100
    civ.regions = ["region1"]
    engine = ActionEngine(sample_world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.BUILD in eligible

def test_build_not_eligible_without_treasury(sample_world):
    civ = sample_world.civilizations[0]
    civ.treasury = 5
    engine = ActionEngine(sample_world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.BUILD not in eligible
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_engine.py::test_trait_weights_include_build_embargo -v`

- [ ] **Step 3: Add BUILD and EMBARGO to TRAIT_WEIGHTS**

Add `ActionType.BUILD` and `ActionType.EMBARGO` columns to every trait profile. Reasonable defaults:
- BUILD: cautious=1.5, visionary=1.5, calculating=1.3, ambitious=1.2, bold=0.5, aggressive=0.3, others=1.0
- EMBARGO: shrewd=1.5, calculating=1.3, aggressive=1.2, cautious=0.5, visionary=0.3, others=0.8

- [ ] **Step 4: Add BUILD and EMBARGO eligibility to get_eligible_actions**

```python
# BUILD: treasury >= 10 and has regions
if civ.treasury >= 10 and civ.regions:
    eligible.append(ActionType.BUILD)

# EMBARGO: has trade route and hostile/suspicious neighbor
# (trade routes don't exist until M13a, so this will never trigger yet)
has_trade_routes = False  # placeholder until M13a
if has_trade_routes and has_hostile:
    eligible.append(ActionType.EMBARGO)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_action_engine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_action_engine.py
git commit -m "feat(p3): add BUILD/EMBARGO weight profiles and eligibility checks"
```

### Task 17: Implement apply_automatic_effects and restructure run_turn

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing test — automatic effects apply military maintenance**

```python
# In tests/test_simulation.py, add:
from chronicler.simulation import apply_automatic_effects

def test_automatic_effects_military_maintenance(sample_world):
    civ = sample_world.civilizations[0]
    civ.military = 50  # above 30 threshold
    civ.treasury = 100
    apply_automatic_effects(sample_world)
    # maintenance = (50 - 30) // 10 = 2
    assert civ.treasury == 98

def test_automatic_effects_no_maintenance_below_threshold(sample_world):
    civ = sample_world.civilizations[0]
    civ.military = 30
    civ.treasury = 100
    apply_automatic_effects(sample_world)
    assert civ.treasury == 100  # no maintenance
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulation.py::test_automatic_effects_military_maintenance -v`

- [ ] **Step 3: Implement apply_automatic_effects**

```python
def apply_automatic_effects(world: WorldState) -> list[Event]:
    """Phase 2: Automatic per-turn effects — maintenance, trade income."""
    events: list[Event] = []
    for civ in world.civilizations:
        # Military maintenance: free up to 30, then (mil-30)//10 per turn
        if civ.military > 30:
            cost = (civ.military - 30) // 10
            civ.treasury -= cost
    # Trade income placeholder — no-op until M13a provides get_active_trade_routes
    return events


def phase_fertility(world: WorldState) -> None:
    """Phase 9: Fertility tick — no-op until M13a."""
    pass
```

- [ ] **Step 4: Remove military maintenance from phase_production**

Remove the `maintenance = civ.military // 2; civ.treasury -= maintenance` lines from `phase_production`.

- [ ] **Step 5: Restructure run_turn to 10 phases**

Update `run_turn` to call phases in new order:
```python
def run_turn(world, action_selector, narrator, seed=0):
    turn_events = []
    # Phase 1: Environment
    turn_events.extend(phase_environment(world, seed=seed))
    # Phase 2: Automatic Effects (NEW)
    turn_events.extend(apply_automatic_effects(world))
    # Phase 3: Production
    phase_production(world)
    # Phase 4: Technology
    turn_events.extend(phase_technology(world))
    # Phase 5: Action
    turn_events.extend(phase_action(world, action_selector=action_selector))
    # Phase 6: Cultural Milestones
    turn_events.extend(phase_cultural_milestones(world))
    # Phase 7: Random Events
    turn_events.extend(phase_random_events(world, seed=seed + 100))
    # Phase 8: Leader Dynamics
    turn_events.extend(phase_leader_dynamics(world, seed=seed))
    # Phase 9: Fertility (NEW — no-op until M13a)
    phase_fertility(world)
    # Phase 10: Consequences
    turn_events.extend(phase_consequences(world))
    world.events_timeline.extend(turn_events)
    chronicle_text = narrator(world, turn_events)
    world.turn += 1
    return chronicle_text
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_simulation.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(p3): add apply_automatic_effects, phase_fertility, restructure run_turn to 10 phases"
```

### Task 18: P3 verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 2: Commit if any cleanup needed**

---

## Chunk 4: Phase M13a — Resource Foundations

### Task 19: Add Resource enum to models.py and implement resources.py

**Files:**
- Modify: `src/chronicler/models.py` (add Resource enum)
- Create: `src/chronicler/resources.py` (imports Resource from models.py — no circular import)
- Create: `tests/test_resources.py`

- [ ] **Step 0: Add Resource enum to models.py**

Add after the other enums in `models.py`:
```python
class Resource(str, Enum):
    GRAIN = "grain"
    TIMBER = "timber"
    IRON = "iron"
    FUEL = "fuel"
    STONE = "stone"
    RARE_MINERALS = "rare_minerals"
```

This lives in `models.py` alongside `TechEra`, `Disposition`, `ActionType` etc. The `resources.py` module imports `Resource` from `models.py` — never the reverse. This avoids the circular import that would occur if `models.py` imported from `resources.py`.

- [ ] **Step 1: Write failing tests for resource generation**

```python
# tests/test_resources.py
from chronicler.resources import assign_resources
from chronicler.models import Region, Resource

def test_resource_enum_values():
    assert Resource.GRAIN.value == "grain"
    assert Resource.RARE_MINERALS.value == "rare_minerals"

def test_assign_resources_deterministic():
    regions = [Region(name="Plains1", terrain="plains", carrying_capacity=50, resources="fertile")]
    assign_resources(regions, seed=42)
    result1 = list(regions[0].specialized_resources)
    # Reset and re-run
    regions[0].specialized_resources = []
    assign_resources(regions, seed=42)
    assert regions[0].specialized_resources == result1

def test_assign_resources_minimum_one():
    """Every region gets at least 1 resource."""
    regions = [Region(name=f"R{i}", terrain="desert", carrying_capacity=50,
                      resources="barren") for i in range(20)]
    assign_resources(regions, seed=0)
    for r in regions:
        assert len(r.specialized_resources) >= 1

def test_assign_resources_preserves_explicit():
    """Regions with existing specialized_resources are not overwritten."""
    regions = [Region(name="Authored", terrain="plains", carrying_capacity=50,
                      resources="fertile", specialized_resources=[Resource.IRON])]
    assign_resources(regions, seed=42)
    assert regions[0].specialized_resources == [Resource.IRON]

def test_assign_resources_plains_likely_grain():
    """Plains terrain should produce grain frequently."""
    regions = [Region(name=f"P{i}", terrain="plains", carrying_capacity=50,
                      resources="fertile") for i in range(50)]
    assign_resources(regions, seed=42)
    grain_count = sum(1 for r in regions if Resource.GRAIN in r.specialized_resources)
    assert grain_count > 25  # 80% probability, should be well above 50%
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resources.py -v`

- [ ] **Step 3: Implement resources.py**

```python
"""Resource system — terrain probabilities, auto-generation, trade routes."""
from __future__ import annotations

import random

from chronicler.models import Region, Resource


TERRAIN_RESOURCE_PROBS: dict[str, dict[Resource, float]] = {
    "plains":    {Resource.GRAIN: 0.8, Resource.TIMBER: 0.3, Resource.IRON: 0.1, Resource.FUEL: 0.05, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.02},
    "forest":    {Resource.GRAIN: 0.3, Resource.TIMBER: 0.8, Resource.IRON: 0.1, Resource.FUEL: 0.1, Resource.STONE: 0.05, Resource.RARE_MINERALS: 0.05},
    "mountains": {Resource.GRAIN: 0.05, Resource.TIMBER: 0.1, Resource.IRON: 0.6, Resource.FUEL: 0.1, Resource.STONE: 0.7, Resource.RARE_MINERALS: 0.2},
    "coast":     {Resource.GRAIN: 0.4, Resource.TIMBER: 0.2, Resource.IRON: 0.05, Resource.FUEL: 0.3, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.05},
    "desert":    {Resource.GRAIN: 0.05, Resource.TIMBER: 0.02, Resource.IRON: 0.2, Resource.FUEL: 0.4, Resource.STONE: 0.3, Resource.RARE_MINERALS: 0.15},
    "tundra":    {Resource.GRAIN: 0.02, Resource.TIMBER: 0.1, Resource.IRON: 0.3, Resource.FUEL: 0.3, Resource.STONE: 0.1, Resource.RARE_MINERALS: 0.2},
    "river":     {Resource.GRAIN: 0.7, Resource.TIMBER: 0.3, Resource.IRON: 0.05, Resource.FUEL: 0.05, Resource.STONE: 0.15, Resource.RARE_MINERALS: 0.02},
    "hills":     {Resource.GRAIN: 0.3, Resource.TIMBER: 0.4, Resource.IRON: 0.4, Resource.FUEL: 0.15, Resource.STONE: 0.5, Resource.RARE_MINERALS: 0.1},
}

# Fallback mapping for old resources field
OLD_RESOURCE_MIGRATION: dict[str, list[Resource]] = {
    "fertile": [Resource.GRAIN],
    "mineral": [Resource.IRON, Resource.STONE],
    "timber": [Resource.TIMBER],
    "maritime": [Resource.GRAIN, Resource.FUEL],
    "barren": [],
}


def assign_resources(regions: list[Region], seed: int) -> None:
    """Assign specialized_resources to regions that don't have them."""
    for region in regions:
        if region.specialized_resources:
            continue  # preserve scenario-authored resources
        rng = random.Random(seed + hash(region.name))
        probs = TERRAIN_RESOURCE_PROBS.get(region.terrain, {})
        resources: list[Resource] = []
        for resource, prob in probs.items():
            if rng.random() < prob:
                resources.append(resource)
        # Minimum 1 resource guaranteed
        if not resources:
            # Pick the highest-probability resource for this terrain
            if probs:
                best = max(probs, key=lambda r: probs[r])
                resources.append(best)
            else:
                resources.append(Resource.GRAIN)  # absolute fallback
        region.specialized_resources = resources
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_resources.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/resources.py tests/test_resources.py
git commit -m "feat(m13a): implement Resource enum, terrain probability table, assign_resources"
```

### Task 20: Add Region model fields for M13a

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Add new fields to Region**

`Resource` was already added to `models.py` in Task 19 Step 0. Now add the Region fields:

```python
class Region(BaseModel):
    # ... existing fields ...
    adjacencies: list[str] = Field(default_factory=list)
    specialized_resources: list[Resource] = Field(default_factory=list)
    fertility: float = Field(default=0.8, ge=0.0, le=1.0)
    infrastructure_level: int = Field(default=0, ge=0)
    famine_cooldown: int = Field(default=0, ge=0)
```

No circular import risk — `Resource` is defined in the same file (`models.py`).

- [ ] **Step 2: Add WorldState field for embargoes**

```python
class WorldState(BaseModel):
    # ... existing fields ...
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
```

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/models.py src/chronicler/resources.py
git commit -m "feat(m13a): add Region fields (specialized_resources, fertility, infrastructure_level, famine_cooldown) and WorldState.embargoes"
```

### Task 21: Add INFORMATION era to TechEra

**Files:**
- Modify: `src/chronicler/models.py`, `src/chronicler/tech.py`
- Modify: `tests/test_tech.py`

- [ ] **Step 1: Write failing test**

```python
def test_information_era_advancement(sample_world):
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.INDUSTRIAL
    civ.culture = 90
    civ.economy = 80
    civ.treasury = 350
    # Need 5 unique resources including across regions
    # (resource check added separately)
    event = check_tech_advancement(civ, sample_world)
    assert event is not None
    assert civ.tech_era == TechEra.INFORMATION
```

- [ ] **Step 2: Add INFORMATION to TechEra enum**

```python
class TechEra(str, Enum):
    # ... existing ...
    INDUSTRIAL = "industrial"
    INFORMATION = "information"
```

- [ ] **Step 3: Add TECH_REQUIREMENTS and ERA_BONUSES for INFORMATION**

```python
TECH_REQUIREMENTS[TechEra.INDUSTRIAL] = (90, 80, 350)
ERA_BONUSES[TechEra.INFORMATION] = {"culture": 10, "economy": 5}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tech.py -v`

- [ ] **Step 5: Update viewer types**

In `viewer/src/types.ts`, add `"information"` to the TechEra type.
In `viewer/src/lib/format.ts`, add `"information"` to ERA_ORDER.

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py src/chronicler/tech.py tests/test_tech.py viewer/src/types.ts viewer/src/lib/format.ts
git commit -m "feat(m13a): add INFORMATION era to TechEra, TECH_REQUIREMENTS, ERA_BONUSES, viewer types"
```

### Task 22: Add resource diversity gate to tech advancement

**Files:**
- Modify: `src/chronicler/tech.py`
- Modify: `tests/test_tech.py`

- [ ] **Step 1: Write failing test**

```python
def test_tech_blocked_without_resources(sample_world):
    """BRONZE requires iron + timber — civ without them can't advance."""
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.TRIBAL
    civ.culture = 40
    civ.economy = 40
    civ.treasury = 100
    # No regions with iron/timber
    for r in sample_world.regions:
        if r.controller == civ.name:
            r.specialized_resources = [Resource.GRAIN]
    event = check_tech_advancement(civ, sample_world)
    assert event is None  # blocked by resource requirement

def test_tech_allowed_with_resources(sample_world):
    civ = sample_world.civilizations[0]
    civ.tech_era = TechEra.TRIBAL
    civ.culture = 40
    civ.economy = 40
    civ.treasury = 100
    for r in sample_world.regions:
        if r.controller == civ.name:
            r.specialized_resources = [Resource.IRON, Resource.TIMBER]
            break
    event = check_tech_advancement(civ, sample_world)
    assert event is not None
```

- [ ] **Step 2: Implement resource diversity check**

```python
# In tech.py, add resource requirements table:
from chronicler.resources import Resource

RESOURCE_REQUIREMENTS: dict[TechEra, tuple[set[Resource] | None, int]] = {
    # (required_specific_resources, min_unique_count)
    TechEra.TRIBAL: ({Resource.IRON, Resource.TIMBER}, 2),
    TechEra.BRONZE: ({Resource.IRON, Resource.TIMBER, Resource.GRAIN}, 3),
    TechEra.IRON: (None, 3),       # any 3 unique
    TechEra.CLASSICAL: (None, 4),   # any 4 unique
    TechEra.MEDIEVAL: (None, 4),    # any 4 unique
    TechEra.RENAISSANCE: (None, 5), # any 5 unique
    TechEra.INDUSTRIAL: ({Resource.FUEL}, 5),  # must include fuel + 5 unique
}

def _get_civ_resources(civ, world) -> set[Resource]:
    """Union of specialized_resources across all controlled regions."""
    resources = set()
    for r in world.regions:
        if r.controller == civ.name:
            resources.update(r.specialized_resources)
    return resources

def _check_resource_requirements(civ, world) -> bool:
    reqs = RESOURCE_REQUIREMENTS.get(civ.tech_era)
    if reqs is None:
        return True
    required_types, min_count = reqs
    civ_resources = _get_civ_resources(civ, world)
    if required_types and not required_types.issubset(civ_resources):
        return False
    if len(civ_resources) < min_count:
        return False
    return True
```

Add `_check_resource_requirements(civ, world)` call at the top of `check_tech_advancement`, returning None if it fails.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_tech.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/tech.py tests/test_tech.py
git commit -m "feat(m13a): add resource diversity gate to tech advancement"
```

### Task 23: Implement fertility system

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests**

```python
def test_fertility_degrades_under_overpopulation(sample_world):
    civ = sample_world.civilizations[0]
    civ.population = 80
    civ.regions = ["region1"]
    region = [r for r in sample_world.regions if r.name == "region1"][0]
    region.carrying_capacity = 50
    region.fertility = 0.8  # effective capacity = 40, pop 80 >> 40
    region.controller = civ.name
    phase_fertility(sample_world)
    assert region.fertility < 0.8

def test_fertility_recovers_under_low_population(sample_world):
    civ = sample_world.civilizations[0]
    civ.population = 10
    civ.regions = ["region1"]
    region = [r for r in sample_world.regions if r.name == "region1"][0]
    region.carrying_capacity = 50
    region.fertility = 0.5  # effective capacity = 25, pop 10 < 12.5 (50%)
    region.controller = civ.name
    phase_fertility(sample_world)
    assert region.fertility > 0.5
```

- [ ] **Step 2: Implement phase_fertility**

Replace the placeholder in simulation.py:
```python
def phase_fertility(world: WorldState) -> None:
    """Phase 9: Fertility degradation and recovery."""
    for region in world.regions:
        if region.controller is None:
            continue
        civ = _get_civ(world, region.controller)
        if civ is None or not civ.regions:
            continue
        effective_cap = max(1, int(region.carrying_capacity * region.fertility))
        avg_pop = civ.population / len(civ.regions)
        if avg_pop > effective_cap:
            region.fertility = max(0.0, round(region.fertility - 0.02, 4))
        elif avg_pop < effective_cap * 0.5:
            region.fertility = min(1.0, round(region.fertility + 0.01, 4))
        # Tick famine cooldown
        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1
```

- [ ] **Step 3: Update phase_production to use effective capacity**

In `phase_production`, replace `region_capacity` calculation:
```python
region_capacity = sum(
    max(1, int(r.carrying_capacity * r.fertility))
    for r in world.regions
    if r.controller == civ.name
)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13a): implement fertility system — degradation, recovery, effective capacity"
```

### Task 24: Implement trade routes and update automatic effects

**Files:**
- Modify: `src/chronicler/simulation.py`
- Create or modify: `src/chronicler/resources.py` (add get_active_trade_routes)
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests**

```python
def test_get_active_trade_routes(sample_world):
    """Trade route between adjacent civs with NEUTRAL+ disposition."""
    from chronicler.resources import get_active_trade_routes
    # Set up: two civs control adjacent regions, neutral disposition
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL
    routes = get_active_trade_routes(sample_world)
    assert (civ_a.name, civ_b.name) in routes or (civ_b.name, civ_a.name) in routes

def test_no_trade_route_when_embargoed(sample_world):
    from chronicler.resources import get_active_trade_routes
    # Same setup but add embargo
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL
    sample_world.embargoes = [(civ_a.name, civ_b.name)]
    routes = get_active_trade_routes(sample_world)
    assert len(routes) == 0

def test_automatic_effects_trade_income(sample_world):
    """Trade routes generate treasury income."""
    # Set up active trade route
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.relationships[civ_a.name][civ_b.name].disposition = Disposition.NEUTRAL
    sample_world.relationships[civ_b.name][civ_a.name].disposition = Disposition.NEUTRAL
    treasury_a = civ_a.treasury
    treasury_b = civ_b.treasury
    apply_automatic_effects(sample_world)
    assert civ_a.treasury >= treasury_a + 2  # +2 each for cross-civ route
    assert civ_b.treasury >= treasury_b + 2
```

- [ ] **Step 2: Implement get_active_trade_routes and get_self_trade_civs**

Two separate functions with clear return types — no tuple ambiguity:

```python
# In resources.py, add:
from chronicler.models import Disposition, WorldState

DISP_ORDER = {"hostile": 0, "suspicious": 1, "neutral": 2, "friendly": 3, "allied": 4}

def get_active_trade_routes(world: WorldState) -> list[tuple[str, str]]:
    """Cross-civ trade routes — direct adjacency, neutral+ disposition, no embargo.
    Returns deduplicated (civ_a, civ_b) pairs sorted alphabetically."""
    routes: set[tuple[str, str]] = set()
    embargo_set = {(a, b) for a, b in world.embargoes} | {(b, a) for a, b in world.embargoes}
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = next((r for r in world.regions if r.name == adj_name), None)
            if r2 is None or r2.controller is None or r1.controller == r2.controller:
                continue
            pair = tuple(sorted([r1.controller, r2.controller]))
            if pair in embargo_set:
                continue
            rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
            rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
            if rel_ab and rel_ba:
                if DISP_ORDER.get(rel_ab.disposition.value, 0) >= 2 and DISP_ORDER.get(rel_ba.disposition.value, 0) >= 2:
                    routes.add(pair)
    return list(routes)


def get_self_trade_civs(world: WorldState) -> set[str]:
    """Civs that control both endpoints of an adjacency edge (internal routes, +3 bonus)."""
    self_routes: set[str] = set()
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for adj_name in r1.adjacencies:
            r2 = next((r for r in world.regions if r.name == adj_name), None)
            if r2 and r2.controller == r1.controller:
                self_routes.add(r1.controller)
    return self_routes
```

- [ ] **Step 3: Update apply_automatic_effects with trade income**

Add trade income after military maintenance in `apply_automatic_effects`:
```python
from chronicler.resources import get_active_trade_routes, get_self_trade_civs
# Trade income
cross_routes = get_active_trade_routes(world)
for civ_a, civ_b in cross_routes:
    a = _get_civ(world, civ_a)
    b = _get_civ(world, civ_b)
    if a:
        a.treasury += 2
    if b:
        b.treasury += 2
# Self-controlled routes: +3 per civ
for civ_name in get_self_trade_civs(world):
    c = _get_civ(world, civ_name)
    if c:
        c.treasury += 3
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_simulation.py tests/test_resources.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/resources.py src/chronicler/simulation.py tests/test_simulation.py tests/test_resources.py
git commit -m "feat(m13a): implement trade routes and trade income in automatic effects"
```

### Task 25: Implement EMBARGO action handler

**Files:**
- Modify: `src/chronicler/action_engine.py` or `src/chronicler/simulation.py`
- Modify: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test**

```python
def test_embargo_action_adds_embargo(sample_world):
    from chronicler.action_engine import ACTION_REGISTRY
    civ = sample_world.civilizations[0]
    target = sample_world.civilizations[1]
    # Set hostile disposition
    sample_world.relationships[civ.name][target.name].disposition = Disposition.HOSTILE
    handler = ACTION_REGISTRY[ActionType.EMBARGO]
    event = handler(civ, sample_world)
    assert (civ.name, target.name) in sample_world.embargoes
    assert event.event_type == "embargo"
```

- [ ] **Step 2: Implement EMBARGO handler**

```python
@register_action(ActionType.EMBARGO)
def _resolve_embargo(civ: Civilization, world: WorldState) -> Event:
    """Impose trade embargo on most hostile neighbor."""
    target_name = None
    # Find most hostile neighbor not already embargoed
    if civ.name in world.relationships:
        for other, rel in world.relationships[civ.name].items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                if (civ.name, other) not in world.embargoes:
                    target_name = other
                    break
    if target_name:
        world.embargoes.append((civ.name, target_name))
        target = _get_civ(world, target_name)
        if target:
            target.stability = clamp(target.stability - 5, STAT_FLOOR["stability"], 100)
        return Event(
            turn=world.turn, event_type="embargo", actors=[civ.name, target_name],
            description=f"{civ.name} imposed a trade embargo on {target_name}.",
            importance=6,
        )
    return Event(
        turn=world.turn, event_type="embargo", actors=[civ.name],
        description=f"{civ.name} sought to embargo but found no target.", importance=2,
    )
```

- [ ] **Step 2b: Update EMBARGO eligibility in get_eligible_actions**

Replace the placeholder `has_trade_routes = False` from Task 16 with the real check:
```python
from chronicler.resources import get_active_trade_routes
civ_routes = [r for r in get_active_trade_routes(world) if civ.name in r]
if civ_routes and has_hostile:
    eligible.append(ActionType.EMBARGO)
```

- [ ] **Step 3: Add embargo lifting check to apply_automatic_effects**

At the start of `apply_automatic_effects`:
```python
# Lift embargoes where disposition has reached FRIENDLY+
world.embargoes = [
    (a, b) for a, b in world.embargoes
    if not _should_lift_embargo(a, b, world)
]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_action_engine.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py src/chronicler/simulation.py tests/test_action_engine.py
git commit -m "feat(m13a): implement EMBARGO action handler and auto-lifting"
```

### Task 26: Implement --simulate-only flag

**Files:**
- Modify: `src/chronicler/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

```python
def test_simulate_only_flag(tmp_path):
    """--simulate-only runs without LLM and produces bundle with empty chronicle."""
    # Test that the flag is accepted and produces output
    from chronicler.main import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["--simulate-only", "--turns", "5", "--output", str(tmp_path)])
    assert args.simulate_only is True
```

- [ ] **Step 2: Add --simulate-only to CLI parser**

In `main.py`, add to `_build_parser`:
```python
parser.add_argument("--simulate-only", action="store_true",
                    help="Run simulation without LLM narrative generation")
```

- [ ] **Step 3: Handle --simulate-only in main()**

When `args.simulate_only` is set:
- Pass `narrator=lambda world, events: ""` to `execute_run`
- Skip LLM client creation
- Bundle gets empty `chronicle_entries`

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_main.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m13a): add --simulate-only CLI flag for LLM-free simulation runs"
```

### Task 27: Wire resource generation into world_gen and update scenarios

**Files:**
- Modify: `src/chronicler/world_gen.py`
- Modify: `src/chronicler/scenario.py`
- Modify: All 6 `scenarios/*.yaml`

- [ ] **Step 1: Add assign_resources call to generate_world**

In `world_gen.py`, after `compute_adjacencies`:
```python
from chronicler.resources import assign_resources
assign_resources(regions, seed=seed)
```

- [ ] **Step 2: Add specialized_resources and fertility to RegionOverride**

In `scenario.py`:
```python
class RegionOverride(BaseModel):
    # ... existing fields ...
    specialized_resources: list[str] | None = None
    fertility: float | None = None
```

Apply in `apply_scenario`:
```python
if override.specialized_resources is not None:
    region.specialized_resources = [Resource(r) for r in override.specialized_resources]
if override.fertility is not None:
    region.fertility = override.fertility
```

- [ ] **Step 3: Update scenario YAML files**

Add `specialized_resources`, `adjacencies`, and `fertility` to scenarios where creative intent demands it. Minnesota gets full hand-authored resources and adjacencies. Other scenarios can rely on auto-generation for resources but should get adjacencies where topology matters.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scenario.py tests/test_world_gen.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py src/chronicler/scenario.py scenarios/ tests/
git commit -m "feat(m13a): wire resource generation into world_gen, update scenario YAMLs with resources/adjacencies/fertility"
```

### Task 28: Update bundle.py with new snapshot fields

**Files:**
- Modify: `src/chronicler/models.py` (TurnSnapshot, CivSnapshot)
- Modify: `src/chronicler/bundle.py`
- Modify: `src/chronicler/main.py` (snapshot capture)
- Modify: `viewer/src/types.ts`

- [ ] **Step 1: Extend TurnSnapshot and CivSnapshot**

```python
class TurnSnapshot(BaseModel):
    turn: int
    civ_stats: dict[str, CivSnapshot]
    region_control: dict[str, str | None]
    relationships: dict[str, dict[str, RelationshipSnapshot]]
    trade_routes: list[tuple[str, str]] = Field(default_factory=list)
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
    embargoes: list[tuple[str, str]] = Field(default_factory=list)
    fertility: dict[str, float] = Field(default_factory=dict)
    mercenary_companies: list[dict] = Field(default_factory=list)

class CivSnapshot(BaseModel):
    # ... existing fields ...
    last_income: int = 0
    active_trade_routes: int = 0
```

- [ ] **Step 2: Update snapshot capture in main.py**

Where TurnSnapshot is created each turn, populate new fields from world state.

- [ ] **Step 3: Update viewer types.ts**

Add matching TypeScript interfaces.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_bundle.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py src/chronicler/bundle.py src/chronicler/main.py viewer/src/types.ts tests/test_bundle.py
git commit -m "feat(m13a): extend TurnSnapshot/CivSnapshot with trade routes, fertility, wars, embargoes"
```

### Task 29: M13a verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run performance benchmark**

Run: `time python -m chronicler --simulate-only --turns 500 --civs 5 --regions 12 --seed 42`
Expected: < 5 seconds

---

## Chunk 5: Phase M13b-1 — Treasury Mechanics

### Task 30: Add active_wars to WorldState and wire WAR action

**Files:**
- Modify: `src/chronicler/models.py`
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Add active_wars field**

```python
class WorldState(BaseModel):
    # ... existing fields ...
    active_wars: list[tuple[str, str]] = Field(default_factory=list)
```

- [ ] **Step 2: Write failing test**

```python
def test_war_action_creates_active_war(sample_world):
    civ = sample_world.civilizations[0]
    target = sample_world.civilizations[1]
    sample_world.relationships[civ.name][target.name].disposition = Disposition.HOSTILE
    sample_world.relationships[target.name][civ.name].disposition = Disposition.HOSTILE
    _resolve_war_action(civ, sample_world)
    assert (civ.name, target.name) in sample_world.active_wars

def test_war_declaration_costs_10_treasury(sample_world):
    civ = sample_world.civilizations[0]
    target = sample_world.civilizations[1]
    sample_world.relationships[civ.name][target.name].disposition = Disposition.HOSTILE
    sample_world.relationships[target.name][civ.name].disposition = Disposition.HOSTILE
    civ.treasury = 100
    _resolve_war_action(civ, sample_world)
    # War costs: -10 declaration + war resolution costs
    assert civ.treasury < 100
```

- [ ] **Step 3: Update WAR handler**

- Add `(attacker, defender)` to `world.active_wars` on war declaration
- Change upfront cost from -20 (scaled from -2) to -10 (spec says 10)
- Add war clearing: in `_resolve_diplomacy`, if disposition reaches FRIENDLY+, remove from `active_wars`

- [ ] **Step 4: Add ongoing war costs to apply_automatic_effects**

```python
# Ongoing war costs: -3/turn per active war
for war in world.active_wars:
    for civ_name in war:
        c = _get_civ(world, civ_name)
        if c:
            c.treasury -= 3
            # Bankruptcy pressure
            if c.treasury <= 0:
                for w in world.active_wars:
                    if c.name in w:
                        c.stability = clamp(c.stability - 5, STAT_FLOOR["stability"], 100)
                        break
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b1): add active_wars tracking, war declaration costs, ongoing war drain"
```

### Task 31: Scale development costs and implement BUILD action

**Files:**
- Modify: `src/chronicler/simulation.py` (develop cost)
- Modify: `src/chronicler/action_engine.py` (BUILD handler)
- Modify: `tests/test_action_engine.py`

- [ ] **Step 1: Write failing test for scaled develop cost**

```python
def test_develop_cost_scales_with_economy(sample_world):
    civ = sample_world.civilizations[0]
    civ.economy = 70
    civ.treasury = 100
    _resolve_develop(civ, sample_world)
    # cost = 5 + 70 // 10 = 12
    assert civ.treasury == 88
```

- [ ] **Step 2: Update _resolve_develop cost**

```python
cost = 5 + civ.economy // 10
```

- [ ] **Step 3: Write failing test for BUILD action**

```python
def test_build_action_increases_capacity(sample_world):
    civ = sample_world.civilizations[0]
    civ.treasury = 100
    region = [r for r in sample_world.regions if r.controller == civ.name][0]
    region.fertility = 0.8  # above 0.5, so should increase capacity
    old_cap = region.carrying_capacity
    handler = ACTION_REGISTRY[ActionType.BUILD]
    handler(civ, sample_world)
    assert civ.treasury == 90  # cost 10
    assert region.carrying_capacity == min(100, old_cap + 10) or region.fertility > 0.8

def test_build_action_restores_fertility_when_low(sample_world):
    civ = sample_world.civilizations[0]
    civ.treasury = 100
    civ.leader.trait = "cautious"  # biases toward fertility
    region = [r for r in sample_world.regions if r.controller == civ.name][0]
    region.fertility = 0.3  # below 0.5
    handler = ACTION_REGISTRY[ActionType.BUILD]
    handler(civ, sample_world)
    assert region.fertility == 0.4  # +0.1
```

- [ ] **Step 4: Implement BUILD handler**

```python
@register_action(ActionType.BUILD)
def _resolve_build(civ: Civilization, world: WorldState) -> Event:
    """Build infrastructure in a controlled region."""
    cost = 10
    if civ.treasury < cost or not civ.regions:
        return Event(turn=world.turn, event_type="build", actors=[civ.name],
                     description=f"{civ.name} lacks funds or territory to build.", importance=2)
    civ.treasury -= cost
    # Pick target region (lowest effective capacity)
    controlled = [r for r in world.regions if r.controller == civ.name]
    target = min(controlled, key=lambda r: int(r.carrying_capacity * r.fertility))
    # Trait-weighted choice: fertility vs capacity
    fertility_bias_traits = {"cautious", "visionary"}
    capacity_bias_traits = {"ambitious", "bold", "aggressive"}
    if civ.leader.trait in fertility_bias_traits and target.fertility < 0.8:
        restore_fertility = True
    elif civ.leader.trait in capacity_bias_traits:
        restore_fertility = target.fertility < 0.3  # only if desperate
    else:
        restore_fertility = target.fertility < 0.5  # default tiebreaker
    if restore_fertility:
        target.fertility = min(1.0, round(target.fertility + 0.1, 4))
        action = "restored fertility"
    else:
        target.carrying_capacity = min(100, target.carrying_capacity + 10)
        action = "expanded capacity"
    target.infrastructure_level += 1
    return Event(turn=world.turn, event_type="build", actors=[civ.name],
                 description=f"{civ.name} {action} in {target.name}.", importance=4)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_action_engine.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/action_engine.py tests/test_action_engine.py tests/test_simulation.py
git commit -m "feat(m13b1): scale develop costs, implement BUILD action with trait-weighted choice"
```

### Task 32: Consolidate production phase (M13b-1 formulas)

**Note:** This replaces P1's temporary production formulas. Any `test_simulation.py` tests written in P1 that assert specific treasury/income values from the old formula will need updating here.

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests for new production formulas**

```python
def test_production_base_income_formula(sample_world):
    civ = sample_world.civilizations[0]
    civ.economy = 50
    civ.regions = ["r1", "r2"]
    civ.treasury = 0
    phase_production(sample_world)
    # income = 50 // 5 + 2 * 2 = 14
    assert civ.treasury >= 14  # may have condition penalties

def test_population_decline_threshold_tightened(sample_world):
    civ = sample_world.civilizations[0]
    civ.stability = 15  # above 10, below 20
    civ.population = 50
    phase_production(sample_world)
    assert civ.population == 50  # no decline at stability 15
```

- [ ] **Step 2: Rewrite phase_production**

```python
def phase_production(world: WorldState) -> None:
    for civ in world.civilizations:
        # Base income
        income = civ.economy // 5 + len(civ.regions) * 2
        # Condition penalty
        penalty = sum(c.severity for c in world.active_conditions if civ.name in c.affected_civs)
        civ.treasury += max(0, income - penalty)
        # Track last_income for mercenary spawn
        civ.last_income += max(0, income - penalty)  # accumulated (trade income added in Phase 2)
        # Population
        region_capacity = sum(
            max(1, int(r.carrying_capacity * r.fertility))
            for r in world.regions if r.controller == civ.name
        )
        max_pop = min(100, region_capacity)
        if civ.economy > civ.population and civ.stability > 20 and civ.population < max_pop:
            civ.population = clamp(civ.population + 5, STAT_FLOOR["population"], 100)
        elif civ.stability <= 10 and civ.population > 1:
            civ.population = clamp(civ.population - 5, STAT_FLOOR["population"], 100)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b1): consolidate production phase with final economic formulas"
```

### Task 33: M13b-1 verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

---

## Chunk 6: Phase M13b-2 — Emergent Economic Events

### Task 34: Implement famine events

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing tests**

```python
def test_famine_triggers_at_low_fertility(sample_world):
    region = sample_world.regions[0]
    region.fertility = 0.25
    region.controller = sample_world.civilizations[0].name
    region.famine_cooldown = 0
    civ = sample_world.civilizations[0]
    old_pop = civ.population
    events = check_famine(sample_world)
    assert len(events) > 0
    assert civ.population < old_pop

def test_famine_cooldown_prevents_repeat(sample_world):
    region = sample_world.regions[0]
    region.fertility = 0.25
    region.controller = sample_world.civilizations[0].name
    region.famine_cooldown = 3  # still cooling down
    events = check_famine(sample_world)
    assert len(events) == 0

def test_famine_refugees(sample_world):
    """Adjacent civs gain population from famine refugees."""
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = sample_world.civilizations[0].name
    r2.controller = sample_world.civilizations[1].name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    r1.fertility = 0.25
    r1.famine_cooldown = 0
    neighbor_pop = sample_world.civilizations[1].population
    check_famine(sample_world)
    assert sample_world.civilizations[1].population == neighbor_pop + 5
```

- [ ] **Step 2: Implement check_famine**

```python
def check_famine(world: WorldState) -> list[Event]:
    """Check for famine in low-fertility regions."""
    events = []
    for region in world.regions:
        if region.controller is None or region.fertility >= 0.3 or region.famine_cooldown > 0:
            continue
        civ = _get_civ(world, region.controller)
        if civ is None:
            continue
        # Famine hits
        civ.population = clamp(civ.population - 15, STAT_FLOOR["population"], 100)
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5
        # Refugee effects on adjacent regions
        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = _get_civ(world, adj.controller)
                if neighbor:
                    neighbor.population = clamp(neighbor.population + 5, STAT_FLOOR["population"], 100)
                    neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)
        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
        from chronicler.named_events import generate_battle_name  # reuse name gen pattern
        world.named_events.append(NamedEvent(
            name=f"The {region.name} Famine", event_type="famine", turn=world.turn,
            actors=[civ.name], region=region.name,
            description=f"Famine in {region.name}", importance=8,
        ))
    return events
```

- [ ] **Step 3: Wire check_famine into run_turn**

Call `check_famine` in Phase 9 (Fertility), after the fertility tick:
```python
def phase_fertility(world):
    # ... existing fertility tick ...
    # Check famine after fertility updates
    return check_famine(world)
```

Update `run_turn` to capture famine events:
```python
# Phase 9: Fertility + Famine
famine_events = phase_fertility(world)
turn_events.extend(famine_events)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b2): implement famine events with cooldown and refugee cascades"
```

### Task 35: Implement black markets

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing test**

```python
def test_black_market_leakage(sample_world):
    """Embargoed civ gets 30% trade benefit from adjacent non-embargoed neighbor."""
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    r1 = sample_world.regions[0]
    r2 = sample_world.regions[1]
    r1.controller = civ_a.name
    r2.controller = civ_b.name
    r1.adjacencies = [r2.name]
    r2.adjacencies = [r1.name]
    sample_world.embargoes = [(civ_b.name, civ_a.name)]  # B embargoed A
    treasury_a = civ_a.treasury
    stability_a = civ_a.stability
    apply_automatic_effects(sample_world)
    # A (embargoed) gets 30% of 2 = 0.6, rounded down = min 1
    assert civ_a.treasury >= treasury_a + 1
    assert civ_a.stability < stability_a  # -3 corruption
```

- [ ] **Step 2: Add black market logic to apply_automatic_effects**

After trade route computation, check for black market leakage for embargoed civs.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b2): implement black market leakage for embargoed civs"
```

### Task 36: Implement mercenary companies

**Files:**
- Modify: `src/chronicler/models.py` (MercenaryCompany, Civ fields)
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Add MercenaryCompany model and Civilization fields**

```python
class MercenaryCompany(BaseModel):
    strength: int = Field(ge=0)
    origin_civ: str
    location: str
    available: bool = True
    hired_by: str | None = None

class WorldState(BaseModel):
    # ... existing ...
    mercenary_companies: list[MercenaryCompany] = Field(default_factory=list)

class Civilization(BaseModel):
    # ... existing ...
    last_income: int = 0
    merc_pressure_turns: int = 0
```

- [ ] **Step 2: Write failing tests**

```python
def test_mercenary_spawn_after_pressure(sample_world):
    civ = sample_world.civilizations[0]
    civ.military = 60
    civ.last_income = 10  # military >> income
    civ.merc_pressure_turns = 2
    old_military = civ.military
    apply_automatic_effects(sample_world)
    # Should increment to 3 and spawn
    assert civ.merc_pressure_turns == 0  # reset after spawn
    assert len(sample_world.mercenary_companies) == 1
    assert civ.military < old_military  # lost military to company

def test_mercenary_cap_blocks_spawn(sample_world):
    sample_world.mercenary_companies = [
        MercenaryCompany(strength=5, origin_civ="X", location="R1"),
        MercenaryCompany(strength=5, origin_civ="Y", location="R2"),
        MercenaryCompany(strength=5, origin_civ="Z", location="R3"),
    ]
    civ = sample_world.civilizations[0]
    civ.military = 60
    civ.last_income = 10
    civ.merc_pressure_turns = 2
    apply_automatic_effects(sample_world)
    assert len(sample_world.mercenary_companies) == 3  # no new company

def test_mercenary_hiring_underdog_priority(sample_world):
    civ_a = sample_world.civilizations[0]
    civ_b = sample_world.civilizations[1]
    civ_a.military = 20  # weaker
    civ_b.military = 60  # stronger
    civ_a.treasury = 100
    civ_b.treasury = 100
    sample_world.active_wars = [(civ_a.name, civ_b.name)]
    sample_world.mercenary_companies = [
        MercenaryCompany(strength=5, origin_civ="X", location="R1"),
    ]
    apply_automatic_effects(sample_world)
    # Weaker civ should get the hire
    assert sample_world.mercenary_companies[0].hired_by == civ_a.name

def test_mercenary_decay(sample_world):
    sample_world.mercenary_companies = [
        MercenaryCompany(strength=3, origin_civ="X", location="R1"),
    ]
    apply_automatic_effects(sample_world)
    assert sample_world.mercenary_companies[0].strength == 1  # 3 - 2

def test_mercenary_removed_at_zero(sample_world):
    sample_world.mercenary_companies = [
        MercenaryCompany(strength=1, origin_civ="X", location="R1"),
    ]
    apply_automatic_effects(sample_world)
    assert len(sample_world.mercenary_companies) == 0  # removed (1-2 <= 0)
```

- [ ] **Step 3: Implement mercenary logic in apply_automatic_effects**

Add to `apply_automatic_effects`:
1. Check merc pressure using previous turn's `last_income`
2. Spawn companies when `merc_pressure_turns >= 3` and cap not reached
3. Hiring: sort eligible hirers by military (asc), then treasury (desc)
4. Decay unhired companies by -2 strength, remove at <= 0
5. Disband hired companies whose war has ended
6. Reset `last_income` to 0 (re-accumulated during this turn's Phase 2 trade income and Phase 3 base income)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b2): implement mercenary companies — spawn, hire, decay, cap"
```

### Task 37: Implement economic specialization

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_simulation.py`

- [ ] **Step 1: Write failing test**

```python
def test_economic_specialization_bonus(sample_world):
    """Civ with >60% routes involving primary resource gets economy bonus."""
    civ = sample_world.civilizations[0]
    civ.economy = 70
    # Set up 3 trade routes all through grain-heavy regions
    # (requires detailed setup of regions with resources and adjacencies)
    treasury_before = civ.treasury
    apply_automatic_effects(sample_world)
    # Should get int(70 * 0.15) = 10 bonus
    # (exact assertion depends on full setup)
```

- [ ] **Step 2: Implement specialization check in apply_automatic_effects**

```python
# Economic specialization
for civ in world.civilizations:
    controlled = [r for r in world.regions if r.controller == civ.name]
    if not controlled:
        continue
    # Count resource frequency
    resource_counts: dict[Resource, int] = {}
    for r in controlled:
        for res in r.specialized_resources:
            resource_counts[res] = resource_counts.get(res, 0) + 1
    if not resource_counts:
        continue
    primary = max(resource_counts, key=lambda r: resource_counts[r])
    # Check if >60% of trade routes involve primary resource
    civ_routes = [(a, b) for a, b in cross_routes if civ.name in (a, b)]
    if not civ_routes:
        continue
    primary_routes = 0
    for a, b in civ_routes:
        # Check if any region on this route has the primary resource
        route_regions = [r for r in world.regions
                        if r.controller in (a, b) and primary in r.specialized_resources]
        if route_regions:
            primary_routes += 1
    if len(civ_routes) > 0 and primary_routes / len(civ_routes) > 0.6:
        # Check if primary routes are embargoed
        embargoed_routes = [(a, b) for a, b in civ_routes
                           if (a, b) in embargo_set or (b, a) in embargo_set]
        if embargoed_routes:
            penalty = int(civ.economy * 0.20)
            civ.treasury -= penalty
        else:
            bonus = int(civ.economy * 0.15)
            civ.treasury += bonus
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_simulation.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/simulation.py tests/test_simulation.py
git commit -m "feat(m13b2): implement economic specialization bonus/penalty"
```

### Task 38: M13b-2 verification and scale test

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run performance benchmark**

Run: `time python -m chronicler --simulate-only --turns 500 --civs 5 --regions 12 --seed 42`
Expected: < 5 seconds

- [ ] **Step 3: Run a 100-turn scenario to verify emergent behavior**

Run a simulation and spot-check:
- Civs with long wars go bankrupt
- Famine triggers in overpopulated regions
- Trade routes form between friendly neighbors
- Embargoes leak via black markets

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "milestone: M13 Resource Foundations & Economic Dynamics complete"
```
