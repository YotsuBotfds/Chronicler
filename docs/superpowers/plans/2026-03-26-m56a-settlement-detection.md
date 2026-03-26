# M56a: Settlement Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect, persist, and name settlement structure from M55a's spatial clustering, with lifecycle management and diagnostics.

**Architecture:** Pure Python. New `settlements.py` module handles detection grid, clustering, matching, and lifecycle. Called from `run_turn()` every turn (early-returns on non-detection turns). Models added to `models.py`, snapshot surface added to `TurnSnapshot` in `main.py`, analytics extractor in `analytics.py`.

**Tech Stack:** Python, Pydantic, Arrow (for reading agent snapshot)

**Spec:** `docs/superpowers/specs/2026-03-25-m56a-settlement-detection-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/chronicler/models.py` | Modify | `Settlement`, `SettlementStatus`, `SettlementSummary` models; fields on `Region`, `WorldState`, `TurnSnapshot` |
| `src/chronicler/settlements.py` | Create | Detection grid, connected components, two-pass matching, lifecycle, diagnostics, `run_settlement_tick()` entry point |
| `src/chronicler/simulation.py` | Modify | Add `force_settlement_detection` param to `run_turn()`, call `run_settlement_tick()` |
| `src/chronicler/main.py` | Modify | Pass `force_settlement_detection` on terminal turn, populate settlement fields on `TurnSnapshot` |
| `src/chronicler/analytics.py` | Modify | `extract_settlement_diagnostics()` extractor |
| `tests/test_settlements.py` | Create | All settlement unit, integration, and determinism tests |

---

### Task 1: Data Models

**Files:**
- Modify: `src/chronicler/models.py:41-45` (SettlementStatus enum near other enums), `src/chronicler/models.py:232` (Region), `src/chronicler/models.py:612` (WorldState), `src/chronicler/models.py:749` (TurnSnapshot)
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write test for Settlement model construction**

```python
# tests/test_settlements.py
"""M56a: Settlement detection tests."""
import pytest
from chronicler.models import Settlement, SettlementStatus, SettlementSummary


class TestSettlementModel:
    def test_candidate_construction_with_sentinel_defaults(self):
        """Candidates use settlement_id=0, name='', founding_turn=0."""
        s = Settlement(
            region_name="Nile Delta",
            last_seen_turn=15,
            population_estimate=42,
            centroid_x=0.3,
            centroid_y=0.7,
            candidate_passes=1,
        )
        assert s.settlement_id == 0
        assert s.name == ""
        assert s.founding_turn == 0
        assert s.status == SettlementStatus.CANDIDATE

    def test_active_settlement_construction(self):
        s = Settlement(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            founding_turn=30,
            last_seen_turn=45,
            population_estimate=100,
            peak_population=100,
            centroid_x=0.5,
            centroid_y=0.5,
            footprint_cells=[(5, 5), (5, 6)],
            status=SettlementStatus.ACTIVE,
            inertia=3,
        )
        assert s.settlement_id == 1
        assert s.status == SettlementStatus.ACTIVE
        assert s.footprint_cells == [(5, 5), (5, 6)]

    def test_tombstone_zeroed_lifecycle_fields(self):
        s = Settlement(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            founding_turn=30,
            last_seen_turn=90,
            dissolved_turn=90,
            population_estimate=0,
            peak_population=150,
            centroid_x=0.5,
            centroid_y=0.5,
            status=SettlementStatus.DISSOLVED,
            inertia=0,
            grace_remaining=0,
            candidate_passes=0,
            footprint_cells=[],
        )
        assert s.status == SettlementStatus.DISSOLVED
        assert s.dissolved_turn == 90
        assert s.inertia == 0
        assert s.footprint_cells == []

    def test_settlement_summary_construction(self):
        ss = SettlementSummary(
            settlement_id=1,
            name="Nile Delta Settlement 1",
            region_name="Nile Delta",
            population_estimate=100,
            centroid_x=0.5,
            centroid_y=0.5,
            founding_turn=30,
            status="active",
        )
        assert ss.settlement_id == 1

    def test_status_enum_values(self):
        assert SettlementStatus.CANDIDATE == "candidate"
        assert SettlementStatus.ACTIVE == "active"
        assert SettlementStatus.DISSOLVING == "dissolving"
        assert SettlementStatus.DISSOLVED == "dissolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settlements.py::TestSettlementModel -v`
Expected: FAIL — `ImportError: cannot import name 'Settlement'`

- [ ] **Step 3: Implement models**

In `src/chronicler/models.py`, add near the top (after existing Enum imports around line 30):

```python
class SettlementStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    DISSOLVING = "dissolving"
    DISSOLVED = "dissolved"
```

After existing `RegionAsabiya` class (around line 230):

```python
class Settlement(BaseModel):
    settlement_id: int = 0
    name: str = ""
    display_name: str | None = None
    region_name: str
    founding_turn: int = 0
    last_seen_turn: int
    dissolved_turn: int | None = None
    population_estimate: int = 0
    peak_population: int = 0
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    footprint_cells: list[tuple[int, int]] = Field(default_factory=list)
    status: SettlementStatus = SettlementStatus.CANDIDATE
    inertia: int = 0
    grace_remaining: int = 0
    candidate_passes: int = 0


class SettlementSummary(BaseModel):
    settlement_id: int
    name: str
    region_name: str
    population_estimate: int
    centroid_x: float
    centroid_y: float
    founding_turn: int
    status: str
```

On `Region` class (after `asabiya_state` field, ~line 247):

```python
    settlements: list[Settlement] = Field(default_factory=list)
```

On `WorldState` class (after `artifacts` field, ~line 670):

```python
    # M56a: Settlement detection
    dissolved_settlements: list[Settlement] = Field(default_factory=list)
    next_settlement_id: int = 1
    settlement_naming_counters: dict[str, int] = Field(default_factory=dict)
    settlement_candidates: list[Settlement] = Field(default_factory=list)
```

On `TurnSnapshot` class (after `perception_errors` field, ~line 773):

```python
    # M56a: Settlement summary
    settlement_source_turn: int = 0
    settlement_count: int = 0
    candidate_count: int = 0
    total_settlement_population: int = 0
    active_settlements: list[SettlementSummary] = Field(default_factory=list)
    founded_this_turn: list[int] = Field(default_factory=list)
    dissolved_this_turn: list[int] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settlements.py::TestSettlementModel -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Write test for WorldState and Region field defaults**

```python
class TestModelIntegration:
    def test_region_settlements_default_empty(self):
        from chronicler.models import Region
        r = Region(name="Test", terrain="plains", carrying_capacity=100, resources="fertile")
        assert r.settlements == []

    def test_worldstate_settlement_fields_default(self):
        from chronicler.models import WorldState
        w = WorldState(name="Test", seed=42)
        assert w.dissolved_settlements == []
        assert w.next_settlement_id == 1
        assert w.settlement_naming_counters == {}
        assert w.settlement_candidates == []

    def test_turnsnapshot_settlement_fields_default(self):
        from chronicler.models import TurnSnapshot
        # Construct with only required fields
        snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
        assert snap.settlement_count == 0
        assert snap.candidate_count == 0
        assert snap.active_settlements == []
        assert snap.founded_this_turn == []
        assert snap.dissolved_this_turn == []
        assert snap.settlement_source_turn == 0
```

- [ ] **Step 6: Run test — should pass immediately**

Run: `pytest tests/test_settlements.py::TestModelIntegration -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/models.py tests/test_settlements.py
git commit -m "feat(m56a): add Settlement, SettlementStatus, SettlementSummary models and field additions"
```

---

### Task 2: Detection Grid and Connected Components

**Files:**
- Create: `src/chronicler/settlements.py`
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write test for grid cell assignment**

```python
# Add to tests/test_settlements.py

class TestDetectionGrid:
    def test_cell_assignment_basic(self):
        from chronicler.settlements import assign_cell
        # Position (0.55, 0.73) → cell (5, 7) with GRID_SIZE=10
        assert assign_cell(0.55, 0.73) == (5, 7)

    def test_cell_assignment_origin(self):
        from chronicler.settlements import assign_cell
        assert assign_cell(0.0, 0.0) == (0, 0)

    def test_cell_assignment_near_boundary(self):
        from chronicler.settlements import assign_cell
        # Just below 1.0 should clamp to cell 9
        assert assign_cell(0.999, 0.999) == (9, 9)

    def test_cell_assignment_exact_boundary(self):
        from chronicler.settlements import assign_cell
        # Position 0.5 → cell 5 (int(0.5 * 10) = 5)
        assert assign_cell(0.5, 0.5) == (5, 5)
```

- [ ] **Step 2: Run test — should fail (module not found)**

Run: `pytest tests/test_settlements.py::TestDetectionGrid -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Create `settlements.py` with grid cell assignment**

```python
# src/chronicler/settlements.py
"""M56a: Settlement detection, matching, lifecycle, and diagnostics."""
import logging

logger = logging.getLogger(__name__)

# --- Calibration constants [CALIBRATE M61b] ---
GRID_SIZE = 10
DENSITY_FLOOR = 5
DENSITY_FRACTION = 0.03
SETTLEMENT_DETECTION_INTERVAL = 15
MAX_MATCH_DISTANCE = 0.25
CANDIDATE_PERSISTENCE = 2
BASE_INERTIA_CAP = 3
AGE_BONUS_INTERVAL = 50
POP_BONUS_INTERVAL = 100
MAX_INERTIA_CAP = 10
DISSOLVE_GRACE = 2


def assign_cell(x: float, y: float) -> tuple[int, int]:
    """Map agent (x, y) in [0, 1) to grid cell (cx, cy)."""
    cx = min(int(x * GRID_SIZE), GRID_SIZE - 1)
    cy = min(int(y * GRID_SIZE), GRID_SIZE - 1)
    return (cx, cy)
```

- [ ] **Step 4: Run test — should pass**

Run: `pytest tests/test_settlements.py::TestDetectionGrid -v`
Expected: PASS

- [ ] **Step 5: Write tests for `build_density_grid` and `find_dense_cells`**

```python
class TestDensityGrid:
    def test_build_density_grid_basic(self):
        from chronicler.settlements import build_density_grid
        # 3 agents in cell (5,5), 2 in (5,6), 1 in (0,0)
        agents = [
            (0.55, 0.55), (0.56, 0.55), (0.57, 0.55),  # cell (5,5)
            (0.55, 0.65), (0.56, 0.65),                  # cell (5,6)
            (0.01, 0.01),                                  # cell (0,0)
        ]
        grid = build_density_grid(agents)
        assert grid[(5, 5)] == 3
        assert grid[(5, 6)] == 2
        assert grid[(0, 0)] == 1

    def test_find_dense_cells_with_floor(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 3, (0, 0): 1}
        # total 14 agents, threshold = max(5, 14 * 0.03) = max(5, 0.42) = 5
        dense = find_dense_cells(grid, region_agent_count=14)
        assert (5, 5) in dense
        assert (5, 6) not in dense
        assert (0, 0) not in dense

    def test_find_dense_cells_with_fraction(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 8, (0, 0): 2}
        # total 1000, threshold = max(5, 1000 * 0.03) = max(5, 30) = 30
        # None dense at floor 30
        dense = find_dense_cells(grid, region_agent_count=1000)
        assert len(dense) == 0

    def test_find_dense_cells_all_dense(self):
        from chronicler.settlements import find_dense_cells
        grid = {(5, 5): 10, (5, 6): 8}
        # total 18, threshold = max(5, 18 * 0.03) = 5
        dense = find_dense_cells(grid, region_agent_count=18)
        assert (5, 5) in dense
        assert (5, 6) in dense
```

- [ ] **Step 6: Run — should fail**

Run: `pytest tests/test_settlements.py::TestDensityGrid -v`

- [ ] **Step 7: Implement `build_density_grid` and `find_dense_cells`**

Add to `settlements.py`:

```python
def build_density_grid(agent_positions: list[tuple[float, float]]) -> dict[tuple[int, int], int]:
    """Count agents per grid cell. Returns {(cx, cy): count}."""
    grid: dict[tuple[int, int], int] = {}
    for x, y in agent_positions:
        cell = assign_cell(x, y)
        grid[cell] = grid.get(cell, 0) + 1
    return grid


def find_dense_cells(
    grid: dict[tuple[int, int], int],
    region_agent_count: int,
) -> set[tuple[int, int]]:
    """Return set of cells exceeding density threshold."""
    threshold = max(DENSITY_FLOOR, region_agent_count * DENSITY_FRACTION)
    return {cell for cell, count in grid.items() if count >= threshold}
```

- [ ] **Step 8: Run — should pass**

Run: `pytest tests/test_settlements.py::TestDensityGrid -v`

- [ ] **Step 9: Write tests for connected components**

```python
import math

class TestConnectedComponents:
    def test_single_cell_cluster(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 5)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert components[0] == {(5, 5)}

    def test_two_adjacent_cells(self):
        from chronicler.settlements import find_connected_components
        dense = {(5, 5), (5, 6)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert components[0] == {(5, 5), (5, 6)}

    def test_diagonal_adjacency_connects(self):
        """8-neighbor: diagonals connect."""
        from chronicler.settlements import find_connected_components
        dense = {(5, 5), (6, 6)}
        components = find_connected_components(dense)
        assert len(components) == 1

    def test_two_separate_clusters(self):
        from chronicler.settlements import find_connected_components
        dense = {(0, 0), (0, 1), (8, 8), (9, 8)}
        components = find_connected_components(dense)
        assert len(components) == 2
        cells_0 = components[0]
        cells_1 = components[1]
        # Row-major order: (0,0)/(0,1) found first
        assert (0, 0) in cells_0 or (0, 1) in cells_0
        assert (8, 8) in cells_1 or (9, 8) in cells_1

    def test_l_shape_single_component(self):
        from chronicler.settlements import find_connected_components
        dense = {(3, 3), (4, 3), (5, 3), (5, 4), (5, 5)}
        components = find_connected_components(dense)
        assert len(components) == 1
        assert len(components[0]) == 5

    def test_row_major_discovery_order(self):
        """Component 0 is discovered first in row-major scan."""
        from chronicler.settlements import find_connected_components
        # Row 0 cell first, row 9 cell second
        dense = {(5, 0), (5, 9)}
        components = find_connected_components(dense)
        assert len(components) == 2
        assert (5, 0) in components[0]
        assert (5, 9) in components[1]

    def test_empty_input(self):
        from chronicler.settlements import find_connected_components
        components = find_connected_components(set())
        assert components == []
```

- [ ] **Step 10: Run — should fail**

Run: `pytest tests/test_settlements.py::TestConnectedComponents -v`

- [ ] **Step 11: Implement `find_connected_components`**

Add to `settlements.py`:

```python
def find_connected_components(
    dense_cells: set[tuple[int, int]],
) -> list[set[tuple[int, int]]]:
    """Find connected components of dense cells using 8-neighbor adjacency.

    Scans in row-major order (cy=0..GRID_SIZE-1, cx=0..GRID_SIZE-1) for
    deterministic component discovery order.
    """
    if not dense_cells:
        return []

    visited: set[tuple[int, int]] = set()
    components: list[set[tuple[int, int]]] = []

    # Row-major scan: y first (rows), then x (columns)
    for cy in range(GRID_SIZE):
        for cx in range(GRID_SIZE):
            if (cx, cy) not in dense_cells or (cx, cy) in visited:
                continue
            # BFS from this cell
            component: set[tuple[int, int]] = set()
            queue = [(cx, cy)]
            visited.add((cx, cy))
            while queue:
                cur_x, cur_y = queue.pop(0)
                component.add((cur_x, cur_y))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = cur_x + dx, cur_y + dy
                        if (nx, ny) in dense_cells and (nx, ny) not in visited:
                            visited.add((nx, ny))
                            queue.append((nx, ny))
            components.append(component)

    return components
```

- [ ] **Step 12: Run — should pass**

Run: `pytest tests/test_settlements.py::TestConnectedComponents -v`

- [ ] **Step 13: Write tests for `extract_clusters`**

```python
class TestExtractClusters:
    def test_extract_clusters_basic(self):
        from chronicler.settlements import extract_clusters
        # Agents clustered in two spots
        agents = [
            (0.51, 0.51), (0.52, 0.52), (0.53, 0.51),
            (0.54, 0.52), (0.55, 0.51), (0.56, 0.52),  # 6 agents in cell (5,5)
        ]
        clusters = extract_clusters(agents)
        assert len(clusters) == 1
        c = clusters[0]
        assert c["population"] == 6
        assert c["cells"] == {(5, 5)}
        assert 0.50 < c["centroid_x"] < 0.57
        assert 0.50 < c["centroid_y"] < 0.53

    def test_extract_clusters_no_dense_cells(self):
        from chronicler.settlements import extract_clusters
        # 4 agents spread across 4 cells — below DENSITY_FLOOR=5
        agents = [(0.1, 0.1), (0.3, 0.3), (0.5, 0.5), (0.7, 0.7)]
        clusters = extract_clusters(agents)
        assert clusters == []

    def test_extract_clusters_two_clusters(self):
        from chronicler.settlements import extract_clusters
        # 6 agents in cell (1,1), 6 agents in cell (8,8)
        agents = (
            [(0.11 + i * 0.01, 0.11) for i in range(6)]
            + [(0.81 + i * 0.01, 0.81) for i in range(6)]
        )
        clusters = extract_clusters(agents)
        assert len(clusters) == 2
```

- [ ] **Step 14: Run — should fail**

Run: `pytest tests/test_settlements.py::TestExtractClusters -v`

- [ ] **Step 15: Implement `extract_clusters`**

Add to `settlements.py`:

```python
def extract_clusters(
    agent_positions: list[tuple[float, float]],
) -> list[dict]:
    """Run full detection pipeline on a list of (x, y) positions.

    Returns list of cluster dicts, each with keys:
        - component_id: int (discovery order)
        - population: int
        - centroid_x: float
        - centroid_y: float
        - cells: set[tuple[int, int]]
    """
    if not agent_positions:
        return []

    grid = build_density_grid(agent_positions)
    dense = find_dense_cells(grid, region_agent_count=len(agent_positions))
    if not dense:
        return []

    components = find_connected_components(dense)

    # Map agents to components for centroid/population
    cell_to_component: dict[tuple[int, int], int] = {}
    for comp_id, cells in enumerate(components):
        for cell in cells:
            cell_to_component[cell] = comp_id

    # Accumulate per-component
    comp_sum_x: list[float] = [0.0] * len(components)
    comp_sum_y: list[float] = [0.0] * len(components)
    comp_pop: list[int] = [0] * len(components)

    for x, y in agent_positions:
        cell = assign_cell(x, y)
        comp_id = cell_to_component.get(cell)
        if comp_id is not None:
            comp_sum_x[comp_id] += x
            comp_sum_y[comp_id] += y
            comp_pop[comp_id] += 1

    clusters = []
    for comp_id, cells in enumerate(components):
        pop = comp_pop[comp_id]
        if pop == 0:
            continue
        clusters.append({
            "component_id": comp_id,
            "population": pop,
            "centroid_x": comp_sum_x[comp_id] / pop,
            "centroid_y": comp_sum_y[comp_id] / pop,
            "cells": cells,
        })
    return clusters
```

- [ ] **Step 16: Run — should pass**

Run: `pytest tests/test_settlements.py::TestExtractClusters -v`

- [ ] **Step 17: Commit**

```bash
git add src/chronicler/settlements.py tests/test_settlements.py
git commit -m "feat(m56a): detection grid, density filtering, connected components, cluster extraction"
```

---

### Task 3: Two-Pass Matching

**Files:**
- Modify: `src/chronicler/settlements.py`
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write tests for matching**

```python
class TestMatching:
    def _make_settlement(self, sid, cx, cy, founding, status="active", inertia=3):
        from chronicler.models import Settlement, SettlementStatus
        return Settlement(
            settlement_id=sid, name=f"S{sid}", region_name="R",
            founding_turn=founding, last_seen_turn=founding,
            centroid_x=cx, centroid_y=cy,
            status=SettlementStatus(status), inertia=inertia,
        )

    def _make_cluster(self, cid, cx, cy, pop=10):
        return {
            "component_id": cid, "centroid_x": cx, "centroid_y": cy,
            "population": pop, "cells": {(int(cx * 10), int(cy * 10))},
        }

    def test_match_single_settlement_to_nearest_cluster(self):
        from chronicler.settlements import match_settlements_to_clusters
        settlements = [self._make_settlement(1, 0.5, 0.5, 10)]
        clusters = [
            self._make_cluster(0, 0.52, 0.52),
            self._make_cluster(1, 0.9, 0.9),
        ]
        matched_s, matched_c, unmatched_s, unmatched_c = match_settlements_to_clusters(
            settlements, clusters, source_turn=20
        )
        assert matched_s == {1: 0}  # settlement_id 1 → cluster component_id 0
        assert 1 in unmatched_c     # cluster 1 unmatched

    def test_distance_gate_rejects_far_cluster(self):
        from chronicler.settlements import match_settlements_to_clusters
        settlements = [self._make_settlement(1, 0.1, 0.1, 10)]
        clusters = [self._make_cluster(0, 0.9, 0.9)]  # distance ~1.13 > 0.25
        matched_s, matched_c, unmatched_s, unmatched_c = match_settlements_to_clusters(
            settlements, clusters, source_turn=20
        )
        assert matched_s == {}
        assert 1 in unmatched_s
        assert 0 in unmatched_c

    def test_older_settlement_wins_tie(self):
        from chronicler.settlements import match_settlements_to_clusters
        s_old = self._make_settlement(1, 0.5, 0.5, founding=5)   # age 15
        s_new = self._make_settlement(2, 0.52, 0.52, founding=15)  # age 5
        clusters = [self._make_cluster(0, 0.51, 0.51)]
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [s_old, s_new], clusters, source_turn=20
        )
        assert matched_s == {1: 0}
        assert 2 in unmatched_s

    def test_greedy_no_double_assignment(self):
        from chronicler.settlements import match_settlements_to_clusters
        s1 = self._make_settlement(1, 0.5, 0.5, 10)
        s2 = self._make_settlement(2, 0.55, 0.55, 10)
        clusters = [self._make_cluster(0, 0.52, 0.52)]
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [s1, s2], clusters, source_turn=20
        )
        # Only one settlement matched
        assert len(matched_s) == 1
        assert len(unmatched_s) == 1
```

- [ ] **Step 2: Run — should fail**

Run: `pytest tests/test_settlements.py::TestMatching -v`

- [ ] **Step 3: Implement `match_settlements_to_clusters`**

Add to `settlements.py`:

```python
import math


def _centroid_distance(s, c) -> float:
    dx = s.centroid_x - c["centroid_x"]
    dy = s.centroid_y - c["centroid_y"]
    return math.sqrt(dx * dx + dy * dy)


def match_settlements_to_clusters(
    settlements: list,  # list[Settlement] — active/dissolving
    clusters: list[dict],
    source_turn: int,
) -> tuple[dict[int, int], dict[int, int], set[int], set[int]]:
    """Two-pass matching is handled by the caller. This does Pass 1 (or Pass 2).

    Returns:
        matched_s: {settlement_id (or candidate_index): cluster component_id}
        matched_c: {cluster component_id: settlement_id (or candidate_index)}
        unmatched_s: set of settlement_ids (or candidate_indices) not matched
        unmatched_c: set of cluster component_ids not matched
    """
    pairs = []
    for s_idx, s in enumerate(settlements):
        s_key = s.settlement_id if s.settlement_id != 0 else s_idx
        for c in clusters:
            dist = _centroid_distance(s, c)
            if dist <= MAX_MATCH_DISTANCE:
                if s.settlement_id != 0:
                    # Pass 1: active/dissolving
                    age = source_turn - s.founding_turn
                    pairs.append((dist, -age, s.settlement_id, c["component_id"], s_key))
                else:
                    # Pass 2: candidates
                    pairs.append((dist, -s.candidate_passes, s_idx, c["component_id"], s_idx))

    # Sort: (distance ASC, age/passes DESC via negation ASC, s_key ASC, c_key ASC)
    pairs.sort(key=lambda p: (p[0], p[1], p[2], p[3]))

    matched_s: dict[int, int] = {}  # s_key → component_id
    matched_c: dict[int, int] = {}  # component_id → s_key
    used_s: set[int] = set()
    used_c: set[int] = set()

    for _, _, s_key, c_key, s_key_out in pairs:
        if s_key_out in used_s or c_key in used_c:
            continue
        matched_s[s_key_out] = c_key
        matched_c[c_key] = s_key_out
        used_s.add(s_key_out)
        used_c.add(c_key)

    all_s_keys = {s.settlement_id if s.settlement_id != 0 else i for i, s in enumerate(settlements)}
    all_c_keys = {c["component_id"] for c in clusters}
    unmatched_s = all_s_keys - used_s
    unmatched_c = all_c_keys - used_c

    return matched_s, matched_c, unmatched_s, unmatched_c
```

- [ ] **Step 4: Run — should pass**

Run: `pytest tests/test_settlements.py::TestMatching -v`

- [ ] **Step 5: Write tests for candidate matching (Pass 2)**

```python
class TestCandidateMatching:
    def test_candidate_match_by_proximity(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import match_settlements_to_clusters
        cand = Settlement(
            region_name="R", last_seen_turn=15,
            centroid_x=0.5, centroid_y=0.5, candidate_passes=1,
        )
        cluster = {
            "component_id": 0, "centroid_x": 0.52, "centroid_y": 0.52,
            "population": 10, "cells": {(5, 5)},
        }
        matched_s, _, _, _ = match_settlements_to_clusters(
            [cand], [cluster], source_turn=30
        )
        assert 0 in matched_s  # candidate index 0 matched

    def test_candidate_higher_passes_wins(self):
        from chronicler.models import Settlement
        from chronicler.settlements import match_settlements_to_clusters
        c1 = Settlement(region_name="R", last_seen_turn=15, centroid_x=0.5, centroid_y=0.5, candidate_passes=3)
        c2 = Settlement(region_name="R", last_seen_turn=15, centroid_x=0.52, centroid_y=0.52, candidate_passes=1)
        cluster = {"component_id": 0, "centroid_x": 0.51, "centroid_y": 0.51, "population": 10, "cells": {(5, 5)}}
        matched_s, _, unmatched_s, _ = match_settlements_to_clusters(
            [c1, c2], [cluster], source_turn=30
        )
        assert 0 in matched_s  # c1 (index 0, passes=3) wins over c2 (index 1, passes=1)
        assert 1 in unmatched_s
```

- [ ] **Step 6: Run — should pass**

Run: `pytest tests/test_settlements.py::TestCandidateMatching -v`

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/settlements.py tests/test_settlements.py
git commit -m "feat(m56a): two-pass settlement-to-cluster matching with distance gate and greedy assignment"
```

---

### Task 4: Lifecycle State Machine

**Files:**
- Modify: `src/chronicler/settlements.py`
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write lifecycle tests**

```python
class TestLifecycle:
    def _make_world_stub(self):
        """Minimal world stub for lifecycle testing."""
        from chronicler.models import WorldState, Region
        w = WorldState(name="Test", seed=42)
        r = Region(name="TestRegion", terrain="plains", carrying_capacity=1000, resources="fertile", controller="TestCiv")
        w.regions = [r]
        return w

    def test_candidate_promotion_after_persistence(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, CANDIDATE_PERSISTENCE
        w = self._make_world_stub()
        # Create candidate with passes just below threshold
        cand = Settlement(
            region_name="TestRegion", last_seen_turn=0,
            centroid_x=0.5, centroid_y=0.5, population_estimate=50,
            candidate_passes=CANDIDATE_PERSISTENCE - 1,
        )
        w.settlement_candidates = [cand]
        # Simulate a match: candidate matched to cluster
        matched_candidates = {0: 0}  # candidate_index 0 → cluster 0
        clusters = [{"component_id": 0, "centroid_x": 0.51, "centroid_y": 0.51, "population": 55, "cells": {(5, 5)}}]
        events = process_lifecycle(w, matched_candidates, {}, clusters, set(), set(), source_turn=30)
        # Should have promoted
        assert len(w.settlement_candidates) == 0
        region = w.region_map["TestRegion"]
        assert len(region.settlements) == 1
        s = region.settlements[0]
        assert s.status == SettlementStatus.ACTIVE
        assert s.settlement_id == 1
        assert s.name == "TestRegion Settlement 1"
        assert s.inertia == 1
        assert s.founding_turn == 30
        # Should have emitted founding event
        assert any(e.event_type == "settlement_founded" for e in events)

    def test_candidate_dropped_when_unmatched(self):
        from chronicler.models import Settlement
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        cand = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=1)
        w.settlement_candidates = [cand]
        events = process_lifecycle(w, {}, {}, [], set(), {0}, source_turn=30)
        assert len(w.settlement_candidates) == 0  # silently dropped

    def test_new_candidate_created_from_unclaimed_cluster(self):
        from chronicler.models import SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        clusters = [{"component_id": 0, "centroid_x": 0.3, "centroid_y": 0.4, "population": 30, "cells": {(3, 4)}, "region_name": "TestRegion"}]
        unclaimed_cluster_ids = {0}
        events = process_lifecycle(w, {}, {}, clusters, unclaimed_cluster_ids, set(), source_turn=15)
        assert len(w.settlement_candidates) == 1
        c = w.settlement_candidates[0]
        assert c.status == SettlementStatus.CANDIDATE
        assert c.candidate_passes == 1
        assert c.region_name == "TestRegion"

    def test_active_settlement_inertia_increment(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="TestRegion Settlement 1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25, population_estimate=50,
            status=SettlementStatus.ACTIVE, inertia=2, footprint_cells=[(5, 5)],
        )
        w.regions[0].settlements = [s]
        matched_active = {1: 0}
        clusters = [{"component_id": 0, "centroid_x": 0.52, "centroid_y": 0.52, "population": 60, "cells": {(5, 5)}}]
        process_lifecycle(w, {}, matched_active, clusters, set(), set(), source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.inertia == 3
        assert updated.population_estimate == 60
        assert updated.last_seen_turn == 40

    def test_active_unmatched_enters_dissolving(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, DISSOLVE_GRACE
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25,
            status=SettlementStatus.ACTIVE, inertia=1,
        )
        w.regions[0].settlements = [s]
        unmatched_active = {1}
        process_lifecycle(w, {}, {}, [], set(), unmatched_active, source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.status == SettlementStatus.DISSOLVING
        assert updated.grace_remaining == DISSOLVE_GRACE

    def test_dissolving_revived_on_match(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25,
            status=SettlementStatus.DISSOLVING, grace_remaining=1,
        )
        w.regions[0].settlements = [s]
        matched_active = {1: 0}
        clusters = [{"component_id": 0, "centroid_x": 0.5, "centroid_y": 0.5, "population": 30, "cells": {(5, 5)}}]
        process_lifecycle(w, {}, matched_active, clusters, set(), set(), source_turn=40)
        updated = w.regions[0].settlements[0]
        assert updated.status == SettlementStatus.ACTIVE
        assert updated.inertia == 1

    def test_dissolving_tombstoned_after_grace(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle
        w = self._make_world_stub()
        s = Settlement(
            settlement_id=1, name="S1", region_name="TestRegion",
            founding_turn=10, last_seen_turn=25, peak_population=100,
            status=SettlementStatus.DISSOLVING, grace_remaining=1,
            footprint_cells=[(5, 5)],
        )
        w.regions[0].settlements = [s]
        unmatched_active = {1}
        events = process_lifecycle(w, {}, {}, [], set(), unmatched_active, source_turn=40)
        assert len(w.regions[0].settlements) == 0
        assert len(w.dissolved_settlements) == 1
        tomb = w.dissolved_settlements[0]
        assert tomb.status == SettlementStatus.DISSOLVED
        assert tomb.dissolved_turn == 40
        assert tomb.inertia == 0
        assert tomb.footprint_cells == []
        assert any(e.event_type == "settlement_dissolved" for e in events)

    def test_naming_counter_never_reused(self):
        from chronicler.models import Settlement, SettlementStatus
        from chronicler.settlements import process_lifecycle, CANDIDATE_PERSISTENCE
        w = self._make_world_stub()
        # First promotion
        c1 = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=CANDIDATE_PERSISTENCE - 1)
        w.settlement_candidates = [c1]
        process_lifecycle(w, {0: 0}, {}, [{"component_id": 0, "centroid_x": 0.5, "centroid_y": 0.5, "population": 50, "cells": {(5,5)}}], set(), set(), source_turn=30)
        first_name = w.regions[0].settlements[0].name
        first_id = w.regions[0].settlements[0].settlement_id
        # Second promotion
        c2 = Settlement(region_name="TestRegion", last_seen_turn=0, candidate_passes=CANDIDATE_PERSISTENCE - 1)
        w.settlement_candidates = [c2]
        process_lifecycle(w, {0: 1}, {}, [{"component_id": 1, "centroid_x": 0.8, "centroid_y": 0.8, "population": 50, "cells": {(8,8)}}], set(), set(), source_turn=45)
        second = w.regions[0].settlements[1]
        assert second.settlement_id == first_id + 1
        assert second.name != first_name
        assert "Settlement 2" in second.name

    def test_inertia_cap_scales_with_age_and_population(self):
        from chronicler.settlements import compute_inertia_cap
        # Young small settlement
        cap_young = compute_inertia_cap(age_turns=10, population=30)
        # Old large settlement
        cap_old = compute_inertia_cap(age_turns=200, population=500)
        assert cap_old > cap_young
        assert cap_old <= 10  # MAX_INERTIA_CAP
```

- [ ] **Step 2: Run — should fail**

Run: `pytest tests/test_settlements.py::TestLifecycle -v`

- [ ] **Step 3: Implement `compute_inertia_cap` and `process_lifecycle`**

Add to `settlements.py`:

```python
from chronicler.models import Settlement, SettlementStatus, Event


def compute_inertia_cap(age_turns: int, population: int) -> int:
    return min(
        BASE_INERTIA_CAP + age_turns // AGE_BONUS_INTERVAL + population // POP_BONUS_INTERVAL,
        MAX_INERTIA_CAP,
    )


def _cluster_by_id(clusters: list[dict]) -> dict[int, dict]:
    return {c["component_id"]: c for c in clusters}


def process_lifecycle(
    world,
    matched_candidates: dict[int, int],  # candidate_index → component_id
    matched_active: dict[int, int],       # settlement_id → component_id
    clusters: list[dict],
    unclaimed_cluster_ids: set[int],
    unmatched_settlement_ids: set[int],   # active/dissolving IDs that had no match
    source_turn: int,
) -> list[Event]:
    """Process all lifecycle transitions for one detection pass. Mutates world in-place.

    Also stashes on world:
        _settlement_founded_this_turn: list[int]  (extended, not replaced)
        _settlement_dissolved_this_turn: list[int]  (extended, not replaced)
        _settlement_transitions: list[dict]  (extended, not replaced)
    """
    events: list[Event] = []
    cluster_map = _cluster_by_id(clusters)
    region_map = world.region_map

    # Initialize stash lists if not present (first region call this turn)
    if not hasattr(world, '_settlement_founded_this_turn'):
        world._settlement_founded_this_turn = []
    if not hasattr(world, '_settlement_dissolved_this_turn'):
        world._settlement_dissolved_this_turn = []
    if not hasattr(world, '_settlement_transitions'):
        world._settlement_transitions = []

    # --- 1. Update matched active/dissolving settlements ---
    for region in world.regions:
        for s in region.settlements:
            if s.settlement_id in matched_active:
                c = cluster_map[matched_active[s.settlement_id]]
                s.centroid_x = c["centroid_x"]
                s.centroid_y = c["centroid_y"]
                s.footprint_cells = sorted(c["cells"])
                s.population_estimate = c["population"]
                s.peak_population = max(s.peak_population, c["population"])
                s.last_seen_turn = source_turn
                if s.status == SettlementStatus.DISSOLVING:
                    # Revival
                    s.status = SettlementStatus.ACTIVE
                    s.inertia = 1
                    s.grace_remaining = 0
                else:
                    cap = compute_inertia_cap(source_turn - s.founding_turn, s.population_estimate)
                    s.inertia = min(s.inertia + 1, cap)

    # --- 2. Handle unmatched active/dissolving settlements ---
    for region in world.regions:
        to_remove = []
        for s in region.settlements:
            if s.settlement_id not in unmatched_settlement_ids:
                continue
            if s.status == SettlementStatus.ACTIVE:
                s.inertia -= 1
                if s.inertia <= 0:
                    s.status = SettlementStatus.DISSOLVING
                    s.grace_remaining = DISSOLVE_GRACE
                    s.inertia = 0
            elif s.status == SettlementStatus.DISSOLVING:
                s.grace_remaining -= 1
                if s.grace_remaining <= 0:
                    # Tombstone
                    s.status = SettlementStatus.DISSOLVED
                    s.dissolved_turn = source_turn
                    s.inertia = 0
                    s.grace_remaining = 0
                    s.candidate_passes = 0
                    s.footprint_cells = []
                    world.dissolved_settlements.append(s)
                    to_remove.append(s)
                    controller = region.controller
                    events.append(Event(
                        turn=source_turn,
                        event_type="settlement_dissolved",
                        actors=[controller] if controller else [],
                        description=f"The settlement of {s.name} in {region.name} has been abandoned",
                        importance=3,
                        source="agent",
                    ))
                    world._settlement_dissolved_this_turn.append(s.settlement_id)
                    world._settlement_transitions.append({
                        "settlement_id": s.settlement_id, "name": s.name,
                        "region_name": region.name,
                        "from_status": "dissolving", "to_status": "dissolved",
                        "reason": "dissolved_grace_expired",
                    })
        for s in to_remove:
            region.settlements.remove(s)

    # --- 3. Process matched candidates ---
    promoted_indices: set[int] = set()
    old_candidates = list(world.settlement_candidates)
    for cand_idx, comp_id in matched_candidates.items():
        if cand_idx >= len(old_candidates):
            continue
        cand = old_candidates[cand_idx]
        c = cluster_map.get(comp_id)
        if c is not None:
            cand.centroid_x = c["centroid_x"]
            cand.centroid_y = c["centroid_y"]
            cand.footprint_cells = sorted(c["cells"])
            cand.population_estimate = c["population"]
            cand.last_seen_turn = source_turn
        cand.candidate_passes += 1
        if cand.candidate_passes >= CANDIDATE_PERSISTENCE:
            # Promote
            cand.settlement_id = world.next_settlement_id
            world.next_settlement_id += 1
            seq = world.settlement_naming_counters.get(cand.region_name, 1)
            cand.name = f"{cand.region_name} Settlement {seq}"
            world.settlement_naming_counters[cand.region_name] = seq + 1
            cand.founding_turn = source_turn
            cand.status = SettlementStatus.ACTIVE
            cand.inertia = 1
            cand.candidate_passes = 0
            cand.peak_population = max(cand.peak_population, cand.population_estimate)
            region = region_map.get(cand.region_name)
            if region is not None:
                region.settlements.append(cand)
            promoted_indices.add(cand_idx)
            controller = region.controller if region else None
            events.append(Event(
                turn=source_turn,
                event_type="settlement_founded",
                actors=[controller] if controller else [],
                description=f"A settlement has formed in {cand.region_name}: {cand.name}",
                importance=4,
                source="agent",
            ))
            world._settlement_founded_this_turn.append(cand.settlement_id)
            world._settlement_transitions.append({
                "settlement_id": cand.settlement_id, "name": cand.name,
                "region_name": cand.region_name,
                "from_status": "candidate", "to_status": "active",
                "reason": "promoted_persistence",
            })

    # --- 4. Rebuild candidate list: keep matched non-promoted, drop unmatched, add new ---
    new_candidates = []
    for idx, cand in enumerate(old_candidates):
        if idx in promoted_indices:
            continue  # promoted to active
        if idx in matched_candidates:
            new_candidates.append(cand)  # matched but not yet promoted
        # else: unmatched → silently dropped

    # --- 5. Create new candidates from unclaimed clusters ---
    for comp_id in sorted(unclaimed_cluster_ids):
        c = cluster_map.get(comp_id)
        if c is None:
            continue
        # Determine region_name from cluster — caller must provide region context
        # For now, use world.regions[0].name as placeholder; actual implementation
        # will be per-region in run_settlement_tick
        new_candidates.append(Settlement(
            region_name=c.get("region_name", ""),
            last_seen_turn=source_turn,
            centroid_x=c["centroid_x"],
            centroid_y=c["centroid_y"],
            footprint_cells=sorted(c["cells"]),
            population_estimate=c["population"],
            candidate_passes=1,
        ))

    world.settlement_candidates = new_candidates
    return events
```

- [ ] **Step 4: Run — should pass**

Run: `pytest tests/test_settlements.py::TestLifecycle -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/settlements.py tests/test_settlements.py
git commit -m "feat(m56a): lifecycle state machine — promotion, inertia, dissolution, revival, tombstones"
```

---

### Task 5: Entry Point and Diagnostics

**Files:**
- Modify: `src/chronicler/settlements.py`
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write tests for `run_settlement_tick`**

```python
class TestRunSettlementTick:
    def _make_world_with_snapshot(self, agent_positions_by_region=None):
        """Create a world with a mock agent snapshot.

        agent_positions_by_region: {region_idx: [(x, y), ...]}
        """
        import pyarrow as pa
        from chronicler.models import WorldState, Region

        w = WorldState(name="Test", seed=42, turn=15)
        regions = [
            Region(name="R0", terrain="plains", carrying_capacity=1000, resources="fertile", controller="Civ1"),
            Region(name="R1", terrain="coast", carrying_capacity=500, resources="maritime", controller="Civ2"),
        ]
        w.regions = regions

        if agent_positions_by_region is not None:
            ids, reg_col, xs, ys = [], [], [], []
            agent_id = 1
            for r_idx, positions in agent_positions_by_region.items():
                for x, y in positions:
                    ids.append(agent_id)
                    reg_col.append(r_idx)
                    xs.append(x)
                    ys.append(y)
                    agent_id += 1
            batch = pa.RecordBatch.from_arrays(
                [pa.array(ids, type=pa.uint32()),
                 pa.array(reg_col, type=pa.uint16()),
                 pa.array(xs, type=pa.float32()),
                 pa.array(ys, type=pa.float32())],
                names=["id", "region", "x", "y"],
            )
            w._agent_snapshot = batch
        else:
            w._agent_snapshot = None
        return w

    def test_off_mode_returns_empty_and_sets_diagnostics(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot(None)
        events = run_settlement_tick(w, source_turn=15, force=False)
        assert events == []
        diag = getattr(w, '_settlement_diagnostics', None)
        assert diag is not None
        assert diag["detection_executed"] is False
        assert diag["reason"] == "mode_off_no_snapshot"

    def test_non_detection_turn_skips(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot({0: [(0.5, 0.5)]})
        w.turn = 7  # Not divisible by 15
        events = run_settlement_tick(w, source_turn=7, force=False)
        assert events == []
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is False
        assert diag["reason"] == "not_detection_turn"

    def test_forced_detection_runs(self):
        from chronicler.settlements import run_settlement_tick
        w = self._make_world_with_snapshot({0: [(0.5, 0.5)]})
        w.turn = 7  # Not interval-aligned
        events = run_settlement_tick(w, source_turn=7, force=True)
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is True
        assert diag["reason"] == "forced_terminal"

    def test_detection_with_cluster_creates_candidate(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        # Put enough agents in one cell to exceed DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        assert len(w.settlement_candidates) == 1
        assert w.settlement_candidates[0].region_name == "R0"

    def test_diagnostics_schema_on_detection_pass(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        diag = w._settlement_diagnostics
        assert diag["detection_executed"] is True
        assert "matching_stats" in diag
        assert "per_region" in diag
        assert "global" in diag
        assert "source_turn" in diag
        assert diag["source_turn"] == 15

    def test_source_turn_stashed_on_world(self):
        from chronicler.settlements import run_settlement_tick, DENSITY_FLOOR
        positions = [(0.51 + i * 0.005, 0.51) for i in range(DENSITY_FLOOR + 1)]
        w = self._make_world_with_snapshot({0: positions})
        w.turn = 15
        run_settlement_tick(w, source_turn=15, force=False)
        assert getattr(w, '_settlement_source_turn', None) == 15
```

- [ ] **Step 2: Run — should fail**

Run: `pytest tests/test_settlements.py::TestRunSettlementTick -v`

- [ ] **Step 3: Implement `run_settlement_tick`**

Add to `settlements.py`:

```python
def _parse_snapshot_by_region(snapshot, num_regions: int) -> dict[int, list[tuple[float, float]]]:
    """Extract per-region agent positions from Arrow snapshot."""
    ids = snapshot.column("id").to_pylist()
    regions = snapshot.column("region").to_pylist()
    xs = snapshot.column("x").to_pylist()
    ys = snapshot.column("y").to_pylist()

    by_region: dict[int, list[tuple[float, float]]] = {r: [] for r in range(num_regions)}
    for i in range(len(ids)):
        r = regions[i]
        if r < num_regions:
            by_region[r].append((xs[i], ys[i]))
    return by_region


def run_settlement_tick(
    world,
    source_turn: int,
    force: bool = False,
) -> list[Event]:
    """Entry point called every turn from run_turn().

    Checks snapshot, interval gate, runs detection + lifecycle on detection turns,
    writes diagnostics on every turn. Processes each region independently so
    component_ids stay region-local and never collide.
    """
    snapshot = getattr(world, '_agent_snapshot', None)

    # No snapshot → off mode
    if snapshot is None:
        world._settlement_diagnostics = {
            "detection_executed": False,
            "interval": SETTLEMENT_DETECTION_INTERVAL,
            "reason": "mode_off_no_snapshot",
        }
        world._settlement_source_turn = source_turn
        world._settlement_founded_this_turn = []
        world._settlement_dissolved_this_turn = []
        return []

    # Interval gate
    is_interval = (source_turn % SETTLEMENT_DETECTION_INTERVAL == 0)
    if not is_interval and not force:
        world._settlement_diagnostics = {
            "detection_executed": False,
            "interval": SETTLEMENT_DETECTION_INTERVAL,
            "reason": "not_detection_turn",
        }
        world._settlement_source_turn = source_turn
        world._settlement_founded_this_turn = []
        world._settlement_dissolved_this_turn = []
        return []

    reason = "forced_terminal" if force and not is_interval else "interval_match"

    # --- Detection pass ---
    num_regions = len(world.regions)
    by_region = _parse_snapshot_by_region(snapshot, num_regions)

    # Clear per-tick stash lists (process_lifecycle extends these per-region)
    world._settlement_founded_this_turn = []
    world._settlement_dissolved_this_turn = []
    world._settlement_transitions = []

    all_events: list[Event] = []
    per_region_diag: dict[str, dict] = {}
    stats = {
        "matched_active": 0, "unmatched_active": 0,
        "new_candidates": 0, "promoted": 0, "revived": 0,
        "entered_dissolving": 0, "tombstoned": 0,
    }
    transitions: list[dict] = []

    # Process each region independently — component_ids are region-local
    for r_idx, region in enumerate(world.regions):
        positions = by_region.get(r_idx, [])
        clusters = extract_clusters(positions)

        # Tag clusters with region_name for candidate creation
        for c in clusters:
            c["region_name"] = region.name

        # Pass 1: active/dissolving settlements in this region
        if region.settlements or clusters:
            ms, mc, us, uc = match_settlements_to_clusters(
                region.settlements, clusters, source_turn
            )
        else:
            ms, mc, us, uc = {}, {}, set(), set()

        # Pass 2: candidates for this region
        region_cand_indices = [
            i for i, c in enumerate(world.settlement_candidates)
            if c.region_name == region.name
        ]
        remaining_clusters = [c for c in clusters if c["component_id"] in uc]

        cand_matched: dict[int, int] = {}  # global_cand_index → component_id
        remaining_unclaimed = uc  # default: all unclaimed from Pass 1

        if region_cand_indices and remaining_clusters:
            cand_list = [world.settlement_candidates[i] for i in region_cand_indices]
            mc2, _, _, uc2_clust = match_settlements_to_clusters(
                cand_list, remaining_clusters, source_turn
            )
            for local_idx, comp_id in mc2.items():
                cand_matched[region_cand_indices[local_idx]] = comp_id
            remaining_unclaimed = uc2_clust

        # Run lifecycle for this region (clusters cached from first extraction)
        region_events = process_lifecycle(
            world, cand_matched, ms, clusters,
            remaining_unclaimed, us, source_turn,
        )
        all_events.extend(region_events)

        # Per-region diagnostics (post-lifecycle state)
        per_region_diag[region.name] = {
            "dense_cells": sum(len(c["cells"]) for c in clusters),
            "cluster_count": len(clusters),
            "candidate_count": sum(1 for c in world.settlement_candidates if c.region_name == region.name),
            "active_count": sum(1 for s in region.settlements if s.status == SettlementStatus.ACTIVE),
            "dissolving_count": sum(1 for s in region.settlements if s.status == SettlementStatus.DISSOLVING),
        }
        stats["matched_active"] += len(ms)
        stats["unmatched_active"] += len(us)

    # Aggregate stats from stashed transition data
    founded_ids = getattr(world, '_settlement_founded_this_turn', [])
    dissolved_ids = getattr(world, '_settlement_dissolved_this_turn', [])
    stats["promoted"] = len(founded_ids)
    stats["tombstoned"] = len(dissolved_ids)
    stats["new_candidates"] = sum(1 for c in world.settlement_candidates if c.candidate_passes == 1)
    # revived and entered_dissolving tracked via process_lifecycle transition returns
    stats["revived"] = sum(1 for e in all_events if "revived" in getattr(e, 'description', '').lower())
    stats["entered_dissolving"] = sum(
        1 for r in world.regions for s in r.settlements
        if s.status == SettlementStatus.DISSOLVING and s.grace_remaining == DISSOLVE_GRACE
    )

    # Diagnostics
    world._settlement_diagnostics = {
        "detection_executed": True,
        "interval": SETTLEMENT_DETECTION_INTERVAL,
        "reason": reason,
        "source_turn": source_turn,
        "per_region": per_region_diag,
        "matching_stats": stats,
        "transitions": getattr(world, '_settlement_transitions', []),
        "global": {
            "total_active": sum(
                1 for r in world.regions for s in r.settlements
                if s.status == SettlementStatus.ACTIVE
            ),
            "total_candidates": len(world.settlement_candidates),
            "total_dissolving": sum(
                1 for r in world.regions for s in r.settlements
                if s.status == SettlementStatus.DISSOLVING
            ),
            "total_dissolved_cumulative": len(world.dissolved_settlements),
        },
    }
    world._settlement_source_turn = source_turn

    return all_events
```

- [ ] **Step 4: Run — should pass**

Run: `pytest tests/test_settlements.py::TestRunSettlementTick -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/settlements.py tests/test_settlements.py
git commit -m "feat(m56a): run_settlement_tick entry point with diagnostics, snapshot parsing, per-region detection"
```

---

### Task 6: Wire into `simulation.py` and `main.py`

**Files:**
- Modify: `src/chronicler/simulation.py:1390,1567` (run_turn signature and call site)
- Modify: `src/chronicler/main.py:282,309,327` (run loop terminal turn flag, run_turn call, TurnSnapshot construction)
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write integration test**

```python
class TestIntegration:
    def test_run_turn_accepts_force_settlement_detection(self):
        """Verify run_turn signature accepts the new parameter without error."""
        import inspect
        from chronicler.simulation import run_turn
        sig = inspect.signature(run_turn)
        assert "force_settlement_detection" in sig.parameters

    def test_off_mode_snapshot_shape_stable(self):
        """TurnSnapshot has settlement fields at defaults in off-mode."""
        from chronicler.models import TurnSnapshot
        snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
        assert snap.settlement_count == 0
        assert snap.active_settlements == []
        assert snap.founded_this_turn == []
        assert snap.dissolved_this_turn == []
```

- [ ] **Step 2: Run existing tests first to ensure no regressions**

Run: `pytest tests/ -x --timeout=60 -q`
Expected: All existing tests pass.

- [ ] **Step 3: Add `force_settlement_detection` parameter to `run_turn()`**

In `src/chronicler/simulation.py`, modify the `run_turn` signature (line ~1390):

Add `force_settlement_detection: bool = False,` after `politics_runtime` parameter.

After the economy_result stash (line ~1567), add:

```python
    # M56a: Settlement detection
    from chronicler.settlements import run_settlement_tick
    settlement_events = run_settlement_tick(
        world, source_turn=world.turn, force=force_settlement_detection
    )
    turn_events.extend(settlement_events)
```

- [ ] **Step 4: Thread `force_settlement_detection` in `main.py`**

In `src/chronicler/main.py`, at the `run_turn` call site (line ~309):

Add `force_settlement_detection=(turn_num == num_turns - 1),` to the `run_turn()` call.

- [ ] **Step 5: Add settlement fields to TurnSnapshot construction in `main.py`**

After the existing TurnSnapshot fields (around line ~418, before the closing parenthesis):

```python
            # M56a: Settlement summary
            settlement_source_turn=getattr(world, '_settlement_source_turn', 0),
            settlement_count=sum(
                len([s for s in r.settlements if s.status.value in ("active", "dissolving")])
                for r in world.regions
            ),
            candidate_count=len(world.settlement_candidates),
            total_settlement_population=sum(
                s.population_estimate
                for r in world.regions for s in r.settlements
                if s.status.value in ("active", "dissolving")
            ),
            active_settlements=sorted(
                [
                    SettlementSummary(
                        settlement_id=s.settlement_id, name=s.name,
                        region_name=s.region_name, population_estimate=s.population_estimate,
                        centroid_x=s.centroid_x, centroid_y=s.centroid_y,
                        founding_turn=s.founding_turn, status=s.status.value,
                    )
                    for r in world.regions for s in r.settlements
                    if s.status.value in ("active", "dissolving")
                ],
                key=lambda ss: (ss.region_name, ss.settlement_id),
            ),
            founded_this_turn=sorted(getattr(world, '_settlement_founded_this_turn', [])),
            dissolved_this_turn=sorted(getattr(world, '_settlement_dissolved_this_turn', [])),
```

`process_lifecycle()` stashes settlement IDs on `world._settlement_founded_this_turn` and `world._settlement_dissolved_this_turn` during lifecycle processing. `run_settlement_tick()` initializes these lists at the start of each tick (before per-region processing), so they accumulate across all regions within a single tick.

Add the `SettlementSummary` import at the top of `main.py`:

```python
from chronicler.models import SettlementSummary
```

- [ ] **Step 6: Run integration test**

Run: `pytest tests/test_settlements.py::TestIntegration -v`
Expected: PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `pytest tests/ -x --timeout=120 -q`
Expected: All tests pass (existing + new).

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/main.py tests/test_settlements.py
git commit -m "feat(m56a): wire settlement detection into run_turn and TurnSnapshot"
```

---

### Task 7: Analytics Extractor

**Files:**
- Modify: `src/chronicler/analytics.py`
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write test for `extract_settlement_diagnostics`**

```python
class TestAnalyticsExtractor:
    def test_extract_empty_history(self):
        from chronicler.analytics import extract_settlement_diagnostics
        from chronicler.models import TurnSnapshot
        result = extract_settlement_diagnostics([])
        assert result["settlement_count_series"] == []

    def test_extract_basic_series(self):
        from chronicler.analytics import extract_settlement_diagnostics
        from chronicler.models import TurnSnapshot, SettlementSummary
        history = [
            TurnSnapshot(
                turn=15, civ_stats={}, region_control={}, relationships={},
                settlement_count=1, candidate_count=0,
                total_settlement_population=50,
                active_settlements=[
                    SettlementSummary(settlement_id=1, name="S1", region_name="R",
                                     population_estimate=50, centroid_x=0.5, centroid_y=0.5,
                                     founding_turn=15, status="active")
                ],
            ),
            TurnSnapshot(
                turn=30, civ_stats={}, region_control={}, relationships={},
                settlement_count=1, candidate_count=0,
                total_settlement_population=60,
                active_settlements=[
                    SettlementSummary(settlement_id=1, name="S1", region_name="R",
                                     population_estimate=60, centroid_x=0.5, centroid_y=0.5,
                                     founding_turn=15, status="active")
                ],
            ),
        ]
        result = extract_settlement_diagnostics(history)
        assert len(result["settlement_count_series"]) == 2
        assert result["settlement_count_series"][0] == {"turn": 15, "active": 1, "candidates": 0}
        assert len(result["per_settlement"]) == 1
        assert result["per_settlement"][1]["name"] == "S1"
        assert len(result["per_settlement"][1]["population_series"]) == 2
```

- [ ] **Step 2: Run — should fail**

Run: `pytest tests/test_settlements.py::TestAnalyticsExtractor -v`

- [ ] **Step 3: Implement `extract_settlement_diagnostics`**

Add to `src/chronicler/analytics.py`:

```python
def extract_settlement_diagnostics(history: list) -> dict:
    """Summarize settlement lifecycle from TurnSnapshot history.

    Returns:
        settlement_count_series: [{turn, active, candidates}, ...]
        per_settlement: {settlement_id: {name, region, founding_turn, dissolved_turn, population_series}}
        founding_rate: [{turn, count}, ...]
        dissolution_rate: [{turn, count}, ...]
    """
    count_series = []
    per_settlement: dict[int, dict] = {}
    founding_rate: dict[int, int] = {}
    dissolution_rate: dict[int, int] = {}

    for snap in history:
        count_series.append({
            "turn": snap.turn,
            "active": snap.settlement_count,
            "candidates": snap.candidate_count,
        })

        for ss in snap.active_settlements:
            if ss.settlement_id not in per_settlement:
                per_settlement[ss.settlement_id] = {
                    "name": ss.name,
                    "region": ss.region_name,
                    "founding_turn": ss.founding_turn,
                    "dissolved_turn": None,
                    "population_series": [],
                }
            per_settlement[ss.settlement_id]["population_series"].append({
                "turn": snap.turn,
                "population": ss.population_estimate,
            })

        for sid in snap.founded_this_turn:
            founding_rate[snap.turn] = founding_rate.get(snap.turn, 0) + 1
        for sid in snap.dissolved_this_turn:
            dissolution_rate[snap.turn] = dissolution_rate.get(snap.turn, 0) + 1
            if sid in per_settlement:
                per_settlement[sid]["dissolved_turn"] = snap.turn

    return {
        "settlement_count_series": count_series,
        "per_settlement": per_settlement,
        "founding_rate": [{"turn": t, "count": c} for t, c in sorted(founding_rate.items())],
        "dissolution_rate": [{"turn": t, "count": c} for t, c in sorted(dissolution_rate.items())],
    }
```

- [ ] **Step 4: Run — should pass**

Run: `pytest tests/test_settlements.py::TestAnalyticsExtractor -v`

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_settlements.py
git commit -m "feat(m56a): extract_settlement_diagnostics analytics extractor"
```

---

### Task 8: Determinism and Save/Load Tests

**Files:**
- Test: `tests/test_settlements.py`

- [ ] **Step 1: Write determinism test**

```python
class TestDeterminism:
    def _run_detection_sequence(self, seed=42):
        """Run 3 detection passes on identical input; return settlement state."""
        import pyarrow as pa
        from chronicler.models import WorldState, Region
        from chronicler.settlements import run_settlement_tick, SETTLEMENT_DETECTION_INTERVAL, DENSITY_FLOOR

        w = WorldState(name="Test", seed=seed, turn=0)
        w.regions = [Region(name="R0", terrain="plains", carrying_capacity=1000, resources="fertile", controller="C1")]

        # Dense cluster: enough agents to form a settlement over 2 passes
        cluster_agents = [(0.51 + i * 0.003, 0.51 + (i % 3) * 0.003) for i in range(DENSITY_FLOOR + 5)]

        for pass_num in range(3):
            turn = pass_num * SETTLEMENT_DETECTION_INTERVAL
            w.turn = turn
            batch = pa.RecordBatch.from_arrays(
                [pa.array(list(range(1, len(cluster_agents) + 1)), type=pa.uint32()),
                 pa.array([0] * len(cluster_agents), type=pa.uint16()),
                 pa.array([x for x, y in cluster_agents], type=pa.float32()),
                 pa.array([y for x, y in cluster_agents], type=pa.float32())],
                names=["id", "region", "x", "y"],
            )
            w._agent_snapshot = batch
            run_settlement_tick(w, source_turn=turn, force=False)

        return {
            "candidates": len(w.settlement_candidates),
            "active": [(s.settlement_id, s.name, s.inertia) for r in w.regions for s in r.settlements],
            "dissolved": len(w.dissolved_settlements),
            "next_id": w.next_settlement_id,
            "naming": dict(w.settlement_naming_counters),
        }

    def test_same_seed_produces_identical_results(self):
        r1 = self._run_detection_sequence(seed=42)
        r2 = self._run_detection_sequence(seed=42)
        assert r1 == r2

    def test_different_seed_same_structure(self):
        """Different seeds with same spatial input produce same results (detection is spatial, not RNG)."""
        r1 = self._run_detection_sequence(seed=42)
        r2 = self._run_detection_sequence(seed=99)
        # Same input positions → same clusters → same results
        assert r1 == r2


class TestSaveLoad:
    def test_settlement_fields_round_trip(self):
        """WorldState save/load preserves settlement fields."""
        import tempfile
        from pathlib import Path
        from chronicler.models import WorldState, Region, Settlement, SettlementStatus

        w = WorldState(name="Test", seed=42, turn=30)
        w.regions = [Region(name="R0", terrain="plains", carrying_capacity=100, resources="fertile")]
        w.regions[0].settlements = [Settlement(
            settlement_id=1, name="R0 Settlement 1", region_name="R0",
            founding_turn=15, last_seen_turn=30, population_estimate=50,
            peak_population=50, centroid_x=0.5, centroid_y=0.5,
            footprint_cells=[(5, 5)],
            status=SettlementStatus.ACTIVE, inertia=3,
        )]
        w.next_settlement_id = 2
        w.settlement_naming_counters = {"R0": 2}
        w.settlement_candidates = [Settlement(
            region_name="R0", last_seen_turn=30, candidate_passes=1,
            centroid_x=0.3, centroid_y=0.4,
        )]
        w.dissolved_settlements = [Settlement(
            settlement_id=99, name="R0 Old", region_name="R0",
            founding_turn=5, last_seen_turn=20, dissolved_turn=25,
            status=SettlementStatus.DISSOLVED,
        )]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            w.save(path)
            loaded = WorldState.load(path)

        assert loaded.next_settlement_id == 2
        assert loaded.settlement_naming_counters == {"R0": 2}
        assert len(loaded.regions[0].settlements) == 1
        assert loaded.regions[0].settlements[0].settlement_id == 1
        assert loaded.regions[0].settlements[0].footprint_cells == [(5, 5)]
        assert len(loaded.settlement_candidates) == 1
        assert loaded.settlement_candidates[0].candidate_passes == 1
        assert len(loaded.dissolved_settlements) == 1
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_settlements.py::TestDeterminism tests/test_settlements.py::TestSaveLoad -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_settlements.py
git commit -m "test(m56a): determinism and save/load round-trip tests"
```

---

### Task 9: Full Regression and Cleanup

**Files:**
- All M56a files

- [ ] **Step 1: Run full Python test suite**

Run: `pytest tests/ -x --timeout=120 -q`
Expected: All tests pass.

- [ ] **Step 2: Run Rust test suite (no changes expected, verify no breakage)**

Run: `cargo nextest run`
Expected: All tests pass (M56a has no Rust changes).

- [ ] **Step 3: Verify `--agents=off` compatibility**

Run a quick off-mode simulation to ensure no crash:

```bash
cd /c/Users/tateb/Documents/opusprogram
python -m chronicler --seed 42 --turns 30 --agents off --no-narration 2>&1 | tail -5
```

Expected: Clean run, no settlement-related errors.

- [ ] **Step 4: Verify agent mode produces settlements**

```bash
python -m chronicler --seed 42 --turns 50 --agents hybrid --no-narration 2>&1 | tail -10
```

Expected: Clean run. Check logs for settlement detection diagnostics.

- [ ] **Step 5: Final commit with any cleanup**

If any fixes were needed:

```bash
git add -A
git commit -m "fix(m56a): post-integration cleanup"
```

- [ ] **Step 6: Push**

```bash
git push
```
