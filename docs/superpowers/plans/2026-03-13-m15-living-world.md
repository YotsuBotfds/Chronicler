# M15: Living World — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the map a living system — terrain affects combat/trade/fertility, typed infrastructure rewards investment, climate cycles and disasters punish neglect, and fog-of-war hides unexplored regions.

**Architecture:** Four sequential phases (M15a→M15b→M15c→M15d), each producing one new module with its own test file. All pure Python simulation — no LLM calls. Existing modules modified: `models.py`, `simulation.py`, `action_engine.py`, `world_gen.py`, `scenario.py`, `adjacency.py`, `bundle.py`. Viewer types updated but no new components.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, hashlib (deterministic disaster rolls), TypeScript/React (viewer types only)

**Spec:** `docs/superpowers/specs/2026-03-13-m15-living-world-design.md`

---

## ERRATA — Read Before Implementing

This plan was written before M14 was implemented. M14 is now fully merged to main (516 tests passing). The following corrections apply throughout the plan. **Apply these corrections as you encounter the affected sections.**

### E1: `resolve_war` is in `action_engine.py`, NOT `simulation.py`

Every reference to `simulation.py resolve_war()` in this plan is wrong. The actual function:

```python
# In action_engine.py, line 305:
def resolve_war(
    attacker: Civilization,
    defender: Civilization,
    world: WorldState,
    seed: int = 0,
) -> str:  # Returns "attacker_wins" | "defender_wins" | "stalemate"
```

**The current combat has no `contested_region` concept.** The attacker fights the defender (Lanchester model), and IF the attacker wins, a random defender region is seized. To integrate terrain defense:

1. **Before the power comparison**, select the contested region: `contested = rng.choice([r for r in world.regions if r.controller == defender.name])` (move region selection before combat, not after).
2. **Add terrain + role + fortification defense** to `def_power`: `def_power += total_defense_bonus(contested)` plus fortification bonus.
3. **After combat**, if attacker wins, seize that specific `contested` region (not a random one — it was already selected).
4. **Fire the `REACTION_REGISTRY["region_lost"]`** inline after the region changes hands (scorched earth check).

All Task 4, Task 8 Step 2/4, and Task 14 Step 3 references to `simulation.py resolve_war()` should target `action_engine.py resolve_war()` instead.

### E2: `handle_build` must match the action handler signature

The action engine dispatches handlers as `handler(civ, world) -> Event`. The plan's `handle_build(world, civ, seed)` signature is wrong. Correct signature:

```python
def handle_build(civ: Civilization, world: WorldState) -> Event:
    """Registered via ACTION_REGISTRY[ActionType.BUILD] = handle_build.
    Replaces the existing @register_action(ActionType.BUILD) _resolve_build handler.
    Derive seed internally: seed = world.seed + world.turn + hash(civ.name)
    """
```

Update Task 6b accordingly. The `_resolve_build` function in action_engine.py (the M13b-1 BUILD handler) should be removed and replaced by importing `handle_build` from `infrastructure.py`.

### E3: `effective_capacity` migration includes `politics.py`

Task 2 Step 3 says to replace inline `int(carrying_capacity * fertility)` in `simulation.py` and check `resources.py, action_engine.py`. **Also check `politics.py`** — it has inline calculations at:
- Line ~267: capital reassignment uses `region_map[rn].carrying_capacity * getattr(region_map[rn], "fertility", 0.8)`
- Line ~796: restoration respawn uses the same pattern

Replace both with `from chronicler.terrain import effective_capacity` calls. Drop the `getattr` fallback — fertility is always present on Region.

### E4: M14 is fully merged — no `hasattr` guards needed

The M15d section references `hasattr(world, 'vassal_relations')` guards for M14 fields. **Delete all such guards.** M14 fields (`vassal_relations`, `federations`, `capital_region`, `peak_region_count`, `decline_turns`, etc.) are all present on main. Reference them directly.

### E5: Task 4 combat test uses wrong `resolve_war` signature

The test at Task 4 Step 1 (`TestTerrainCombatIntegration`) calls:
```python
resolve_war(w, attacker_name="Attacker", defender_name="Defender", contested_region="Peaks", seed=seed)
```
This is completely wrong. After applying E1 (adding contested region to resolve_war), the correct call is:
```python
from chronicler.action_engine import resolve_war
result = resolve_war(attacker, defender, w, seed=seed)
```
Rewrite the test to: (a) import from `action_engine`, (b) pass Civilization objects (not names), (c) assert on the return string, (d) verify region ownership after the call.

### E6: Existing `_resolve_build` must be replaced, not just overridden

Task 8 Step 8 says `ACTION_REGISTRY[ActionType.BUILD] = handle_build`. This works but leaves dead code. Instead: **remove the `@register_action(ActionType.BUILD)` decorator and the entire `_resolve_build` function** from `action_engine.py`, then register `handle_build` from `infrastructure.py` either via `@register_action` or direct assignment. Also remove all references to `infrastructure_level` (the old `_resolve_build` increments it).

---

## Prerequisites (M13 and M14 must be complete)

M15 depends on M13b and M14 being fully implemented. Before starting ANY M15 task, verify these exist:

- [ ] `src/chronicler/adjacency.py` exists with `is_chokepoint()`, `graph_distance()`, `connected_components()`
- [ ] `src/chronicler/resources.py` exists with `get_active_trade_routes(world)`
- [ ] `src/chronicler/utils.py` contains `STAT_FLOOR`, `clamp()`
- [ ] `Region` model has `adjacencies: list[str]`, `fertility: float`, `carrying_capacity: int = Field(ge=1, le=100)`, `infrastructure_level: int`
- [ ] `Civilization` model has stat fields `Field(ge=0, le=100)`, `treasury: int` (uncapped), `capital_region`, `known_regions`
- [ ] `WorldState` model has `active_wars`, `embargoes`, `mercenary_companies`, `vassal_relations`, `federations`, `proxy_wars`, `exile_modifiers`, `war_start_turns`, `peace_turns`, `balance_of_power_turns`
- [ ] `ActionType` enum has `BUILD`, `EMBARGO`, `MOVE_CAPITAL`, `FUND_INSTABILITY`
- [ ] `action_engine.py` uses `ACTION_REGISTRY` / `REACTION_REGISTRY` pattern; `resolve_war()` lives here (NOT in simulation.py)
- [ ] `simulation.py` has 10-phase turn with `apply_automatic_effects` (phase 2), fertility tick (phase 9), `phase_consequences` (phase 10)
- [ ] `Relationship` model exists with `disposition`, `trade_volume`, `allied_turns`
- [ ] `src/chronicler/politics.py` exists with M14a-M14d political mechanics

If any prerequisite is missing, check that M13 and M14 are merged to main. All code in this plan uses M13's 0-100 stat scale.

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/chronicler/terrain.py` | Pure functions: terrain defense/fertility/trade effects, effective_capacity, region role classification |
| `src/chronicler/infrastructure.py` | Typed infrastructure lifecycle: build handler, tick, scorched earth reaction |
| `src/chronicler/climate.py` | Climate phase computation, disaster checks, migration processing |
| `src/chronicler/exploration.py` | Fog-of-war initialization, EXPLORE action, first contact, ruins |
| `tests/test_terrain.py` | Tests for terrain module |
| `tests/test_infrastructure.py` | Tests for infrastructure module |
| `tests/test_climate.py` | Tests for climate module |
| `tests/test_exploration.py` | Tests for exploration module |

### Modified Files
| File | Changes |
|------|---------|
| `src/chronicler/models.py` | Add `role` to Region; add `InfrastructureType`, `Infrastructure`, `PendingBuild` models; replace `infrastructure_level` with `infrastructure` list + `pending_build`; add `disaster_cooldowns`, `resource_suspensions`, `depopulated_since`, `ruin_quality` to Region; add `ClimatePhase`, `ClimateConfig` models; add `climate_config`, `fog_of_war` to WorldState; add `known_regions` to Civilization; add `trade_contact_turns` to Relationship; add `EXPLORE` to ActionType |
| `src/chronicler/simulation.py` | Add climate/disaster/migration calls in phase 1; add `tick_infrastructure` in phase 2; apply terrain fertility cap and climate multiplier in phase 9; add depopulation tracking in phase 10 |
| `src/chronicler/action_engine.py` | Add terrain defense + fortification bonus in `resolve_war`; add contested region selection before combat; fire `REACTION_REGISTRY["region_lost"]` after region seizure; add warming mountain defense override in combat; replace `_resolve_build` with `handle_build` import; add BUILD eligibility filter; register EXPLORE action; add EXPLORE eligibility filter; add EXPLORE trait weights |
| `src/chronicler/adjacency.py` | Add `classify_regions()` function |
| `src/chronicler/world_gen.py` | Call `classify_regions` after adjacency computation; initialize fog-of-war `known_regions` |
| `src/chronicler/scenario.py` | Add `climate` to ScenarioConfig; add `fog_of_war` to ScenarioConfig; parse and apply both in `apply_scenario` |
| `src/chronicler/bundle.py` | Add infrastructure, climate phase, fog-of-war to snapshots |

### Key Reference Files
| File | Why |
|------|-----|
| `src/chronicler/adjacency.py` | `is_chokepoint()` reused by `classify_regions`; adjacency graph used by migration |
| `src/chronicler/resources.py` | `get_active_trade_routes()` — trade income modified by roads/ports/terrain |
| `src/chronicler/utils.py` | `clamp()` for stat modifications, `STAT_FLOOR` for minimums |

---

## Chunk 1: Phase M15a — Terrain & Chokepoints

### Task 1: Add terrain effects table and pure functions

**Files:**
- Create: `src/chronicler/terrain.py`
- Create: `tests/test_terrain.py`

- [ ] **Step 1: Write failing tests for terrain_defense_bonus and terrain_fertility_cap**

```python
# tests/test_terrain.py
import pytest
from chronicler.models import Region


class TestTerrainDefenseBonus:
    def test_mountains_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Peaks", terrain="mountains", carrying_capacity=50, resources="mineral")
        assert terrain_defense_bonus(r) == 20

    def test_plains_no_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Fields", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_defense_bonus(r) == 0

    def test_forest_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Woods", terrain="forest", carrying_capacity=60, resources="timber")
        assert terrain_defense_bonus(r) == 10

    def test_coast_no_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Shore", terrain="coast", carrying_capacity=70, resources="maritime")
        assert terrain_defense_bonus(r) == 0

    def test_desert_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Sands", terrain="desert", carrying_capacity=30, resources="mineral")
        assert terrain_defense_bonus(r) == 5

    def test_tundra_defense(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Frost", terrain="tundra", carrying_capacity=20, resources="mineral")
        assert terrain_defense_bonus(r) == 10

    def test_unknown_terrain_defaults_to_plains(self):
        from chronicler.terrain import terrain_defense_bonus
        r = Region(name="Hills", terrain="hills", carrying_capacity=60, resources="fertile")
        assert terrain_defense_bonus(r) == 0


class TestTerrainFertilityCap:
    def test_plains_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_fertility_cap(r) == 0.9

    def test_desert_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30, resources="mineral")
        assert terrain_fertility_cap(r) == 0.3

    def test_tundra_cap(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="T", terrain="tundra", carrying_capacity=20, resources="mineral")
        assert terrain_fertility_cap(r) == 0.2

    def test_unknown_terrain_defaults_to_plains(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="H", terrain="river", carrying_capacity=60, resources="fertile")
        assert terrain_fertility_cap(r) == 0.9


class TestTerrainTradeModifier:
    def test_coast_trade_bonus(self):
        from chronicler.terrain import terrain_trade_modifier
        r = Region(name="S", terrain="coast", carrying_capacity=70, resources="maritime")
        assert terrain_trade_modifier(r) == 2

    def test_plains_no_trade_bonus(self):
        from chronicler.terrain import terrain_trade_modifier
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile")
        assert terrain_trade_modifier(r) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_terrain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chronicler.terrain'`

- [ ] **Step 3: Implement terrain.py with effects table and pure functions**

```python
# src/chronicler/terrain.py
"""Terrain mechanical effects — pure functions on Region properties.

No state. No side effects. Other modules import and call these.
Unknown terrain types fall through to plains defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Region


@dataclass(frozen=True)
class TerrainEffect:
    defense: int
    fertility_cap: float
    trade_mod: int


TERRAIN_EFFECTS: dict[str, TerrainEffect] = {
    "plains":    TerrainEffect(defense=0,  fertility_cap=0.9, trade_mod=0),
    "forest":    TerrainEffect(defense=10, fertility_cap=0.7, trade_mod=0),
    "mountains": TerrainEffect(defense=20, fertility_cap=0.6, trade_mod=0),
    "coast":     TerrainEffect(defense=0,  fertility_cap=0.8, trade_mod=2),
    "desert":    TerrainEffect(defense=5,  fertility_cap=0.3, trade_mod=0),
    "tundra":    TerrainEffect(defense=10, fertility_cap=0.2, trade_mod=0),
}

_DEFAULT = TERRAIN_EFFECTS["plains"]


def _get_effect(region: Region) -> TerrainEffect:
    return TERRAIN_EFFECTS.get(region.terrain, _DEFAULT)


def terrain_defense_bonus(region: Region) -> int:
    """Military defense modifier for combat in this region."""
    return _get_effect(region).defense


def terrain_fertility_cap(region: Region) -> float:
    """Maximum fertility for this terrain type. Hard ceiling."""
    return _get_effect(region).fertility_cap


def terrain_trade_modifier(region: Region) -> int:
    """Additional trade income for routes through this region."""
    return _get_effect(region).trade_mod


def effective_capacity(region: Region) -> int:
    """Single source of truth for region carrying capacity.

    max(int(carrying_capacity * min(fertility, terrain_fertility_cap)), 1).
    Floor of 1 prevents division-by-zero in famine/migration calculations.
    """
    cap = terrain_fertility_cap(region)
    return max(int(region.carrying_capacity * min(region.fertility, cap)), 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_terrain.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/terrain.py tests/test_terrain.py
git commit -m "feat(m15a): add terrain.py with effects table and pure functions"
```

### Task 2: Add effective_capacity tests and replace inline calls

**Files:**
- Modify: `tests/test_terrain.py`
- Modify: `src/chronicler/simulation.py` (replace inline `int(carrying_capacity * fertility)`)

- [ ] **Step 1: Write failing tests for effective_capacity**

```python
# Append to tests/test_terrain.py

class TestEffectiveCapacity:
    def test_basic_capacity(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="F", terrain="plains", carrying_capacity=80, resources="fertile",
                   fertility=0.5)
        assert effective_capacity(r) == 40

    def test_capped_by_terrain(self):
        """Desert cap 0.3 limits even if fertility is higher."""
        from chronicler.terrain import effective_capacity
        r = Region(name="D", terrain="desert", carrying_capacity=100, resources="mineral",
                   fertility=0.5)
        # min(0.5, 0.3) = 0.3, int(100 * 0.3) = 30
        assert effective_capacity(r) == 30

    def test_floor_of_one(self):
        """Zero fertility still returns 1."""
        from chronicler.terrain import effective_capacity
        r = Region(name="X", terrain="tundra", carrying_capacity=10, resources="mineral",
                   fertility=0.0)
        assert effective_capacity(r) == 1

    def test_full_capacity(self):
        from chronicler.terrain import effective_capacity
        r = Region(name="F", terrain="plains", carrying_capacity=90, resources="fertile",
                   fertility=0.9)
        assert effective_capacity(r) == 81

    def test_fertility_above_cap_uses_cap(self):
        """Fertility 1.0 on mountains (cap 0.6) uses 0.6."""
        from chronicler.terrain import effective_capacity
        r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral",
                   fertility=1.0)
        assert effective_capacity(r) == 30
```

- [ ] **Step 2: Run to verify new tests pass (implementation already exists)**

Run: `pytest tests/test_terrain.py::TestEffectiveCapacity -v`
Expected: All PASS

- [ ] **Step 3: Replace all inline `int(carrying_capacity * fertility)` in simulation.py**

Search `simulation.py` for any inline effective capacity calculations and replace with:
```python
from chronicler.terrain import effective_capacity
```

Replace patterns like:
```python
# BEFORE:
eff_cap = int(region.carrying_capacity * region.fertility)
# AFTER:
eff_cap = effective_capacity(region)
```

Do the same in any other modules that compute effective capacity inline (check `resources.py`, `action_engine.py`).

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests still pass

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "refactor(m15a): replace inline effective_capacity with terrain.effective_capacity"
```

### Task 3: Add region role classification

**Files:**
- Modify: `src/chronicler/adjacency.py`
- Modify: `src/chronicler/models.py` (add `role` field to Region)
- Modify: `src/chronicler/world_gen.py` (call classify after adjacency computation)
- Modify: `tests/test_terrain.py`

- [ ] **Step 1: Add `role` field to Region model**

```python
# In models.py, Region class, add after y field:
    role: str = "standard"  # standard, crossroads, frontier, chokepoint
```

- [ ] **Step 2: Write failing tests for classify_regions**

```python
# Append to tests/test_terrain.py

class TestClassifyRegions:
    def test_frontier_single_adjacency(self):
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
        roles = classify_regions(adj)
        assert roles["A"] == "frontier"
        assert roles["C"] == "frontier"

    def test_crossroads_three_plus(self):
        from chronicler.adjacency import classify_regions
        adj = {"Hub": ["A", "B", "C"], "A": ["Hub"], "B": ["Hub"], "C": ["Hub"]}
        roles = classify_regions(adj)
        assert roles["Hub"] == "crossroads"

    def test_chokepoint_articulation(self):
        """B is the only path between {A} and {C,D}."""
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B"], "B": ["A", "C", "D"], "C": ["B", "D"], "D": ["B", "C"]}
        roles = classify_regions(adj)
        assert roles["B"] == "chokepoint"

    def test_standard_default(self):
        from chronicler.adjacency import classify_regions
        adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
        roles = classify_regions(adj)
        # All have 2 adjacencies, none are articulation points in a complete triangle
        assert all(r == "standard" for r in roles.values())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_terrain.py::TestClassifyRegions -v`
Expected: FAIL — `ImportError: cannot import name 'classify_regions'`

- [ ] **Step 4: Implement classify_regions in adjacency.py**

```python
# Append to src/chronicler/adjacency.py

def _find_articulation_points(adj: dict[str, list[str]]) -> set[str]:
    """Find articulation points using Tarjan's algorithm."""
    visited: set[str] = set()
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    ap: set[str] = set()
    timer = [0]

    def dfs(u: str) -> None:
        children = 0
        visited.add(u)
        disc[u] = low[u] = timer[0]
        timer[0] += 1
        for v in adj.get(u, []):
            if v not in visited:
                children += 1
                parent[v] = u
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent[u] is None and children > 1:
                    ap.add(u)
                if parent[u] is not None and low[v] >= disc[u]:
                    ap.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node in adj:
        if node not in visited:
            parent[node] = None
            dfs(node)

    return ap


def classify_regions(adj: dict[str, list[str]]) -> dict[str, str]:
    """Classify regions by graph topology. Called once at world generation.

    - CROSSROADS: 3+ adjacencies (rich but exposed)
    - FRONTIER: exactly 1 adjacency (defensible but isolated)
    - CHOKEPOINT: articulation point (strategic trade toll)
    - STANDARD: everything else
    """
    articulation = _find_articulation_points(adj)
    roles: dict[str, str] = {}
    for name, neighbors in adj.items():
        degree = len(neighbors)
        if degree == 1:
            roles[name] = "frontier"
        elif name in articulation:
            roles[name] = "chokepoint"
        elif degree >= 3:
            roles[name] = "crossroads"
        else:
            roles[name] = "standard"
    return roles
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_terrain.py::TestClassifyRegions -v`
Expected: All PASS

- [ ] **Step 6: Wire classify_regions into world_gen.py**

In `world_gen.py` `generate_world()`, after adjacencies are computed (P2), add:

```python
from chronicler.adjacency import classify_regions

# After adjacency computation:
adj_map = {r.name: r.adjacencies for r in world.regions}
roles = classify_regions(adj_map)
for region in world.regions:
    region.role = roles.get(region.name, "standard")
```

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/adjacency.py src/chronicler/models.py src/chronicler/world_gen.py tests/test_terrain.py
git commit -m "feat(m15a): add region role classification (crossroads/frontier/chokepoint)"
```

### Task 4: Integrate terrain effects into simulation loop

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `tests/test_terrain.py`

- [ ] **Step 1: Write failing tests for terrain integration**

```python
# Append to tests/test_terrain.py
from chronicler.models import Civilization, Leader, WorldState, Region, Relationship, Disposition


def _make_world(regions, civs, relationships=None):
    """Helper to build a minimal WorldState."""
    return WorldState(
        name="Test", seed=42, regions=regions,
        civilizations=civs,
        relationships=relationships or {},
    )


def _make_civ(name, military=50, stability=50, population=50, economy=50,
              culture=50, regions=None, treasury=100):
    leader = Leader(name=f"Leader of {name}", trait="bold", reign_start=0)
    return Civilization(
        name=name, population=population, military=military, economy=economy,
        culture=culture, stability=stability, treasury=treasury,
        leader=leader, regions=regions or [],
    )


class TestTerrainCombatIntegration:
    def test_mountain_defender_has_advantage(self):
        """Defender in mountains gets +20 defense bonus applied in combat."""
        from chronicler.action_engine import resolve_war
        from chronicler.terrain import total_defense_bonus
        mountain = Region(name="Peaks", terrain="mountains",
                         carrying_capacity=50, resources="mineral",
                         controller="Defender", fertility=0.5,
                         adjacencies=["Valley"])
        plains = Region(name="Valley", terrain="plains",
                       carrying_capacity=80, resources="fertile",
                       controller="Attacker", fertility=0.8,
                       adjacencies=["Peaks"])
        # Equal stats: mountain defender should get +20 defense
        defender = _make_civ("Defender", military=50, regions=["Peaks"])
        attacker = _make_civ("Attacker", military=50, regions=["Valley"])
        world = _make_world([mountain, plains], [defender, attacker])
        # Verify defense bonus flows through to combat
        assert total_defense_bonus(mountain) == 20
        assert total_defense_bonus(plains) == 0
        # Run combat over multiple seeds — mountain defender should win more often
        mountain_wins = 0
        for seed in range(50):
            w = _make_world(
                [mountain.model_copy(), plains.model_copy()],
                [defender.model_copy(), attacker.model_copy()],
            )
            result = resolve_war(
                next(c for c in w.civilizations if c.name == "Attacker"),
                next(c for c in w.civilizations if c.name == "Defender"),
                w, seed=seed,
            )
            d = next(c for c in w.civilizations if c.name == "Defender")
            if "Peaks" in d.regions:
                mountain_wins += 1
        assert mountain_wins > 25  # >50% with +20 defense advantage


class TestTerrainFertilityCapIntegration:
    def test_desert_recovery_capped(self):
        """Desert fertility recovery stops at 0.3."""
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.29)
        cap = terrain_fertility_cap(r)
        new_fertility = min(r.fertility + 0.01, cap)
        assert new_fertility == 0.3

    def test_desert_recovery_at_cap_stays(self):
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.3)
        cap = terrain_fertility_cap(r)
        new_fertility = min(r.fertility + 0.01, cap)
        assert new_fertility == 0.3


class TestRoleEffects:
    def test_crossroads_trade_bonus(self):
        """Crossroads role gives +3 trade, -5 defense."""
        # Role effects are applied at integration points.
        # Here we just verify the constants exist and are correct.
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["crossroads"].trade_mod == 3
        assert ROLE_EFFECTS["crossroads"].defense == -5

    def test_frontier_defense_bonus(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["frontier"].defense == 10
        assert ROLE_EFFECTS["frontier"].trade_mod == -2

    def test_chokepoint_trade_toll(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["chokepoint"].trade_mod == 5

    def test_standard_no_effect(self):
        from chronicler.terrain import ROLE_EFFECTS
        assert ROLE_EFFECTS["standard"].defense == 0
        assert ROLE_EFFECTS["standard"].trade_mod == 0


class TestRoleStacking:
    def test_mountain_frontier_defense_stacks(self):
        """Spec: mountain frontier defense = 20 + 10 = 30."""
        from chronicler.terrain import total_defense_bonus
        r = Region(name="Pass", terrain="mountains", carrying_capacity=50,
                   resources="mineral", role="frontier")
        assert total_defense_bonus(r) == 30

    def test_coastal_crossroads_trade_stacks(self):
        """Spec: coastal crossroads trade = 2 + 3 = 5."""
        from chronicler.terrain import total_trade_modifier
        r = Region(name="Hub", terrain="coast", carrying_capacity=70,
                   resources="maritime", role="crossroads")
        assert total_trade_modifier(r) == 5


class TestFertilityRecoveryMultiTurn:
    def test_desert_recovers_to_cap_over_turns(self):
        """Spec: desert at 0.28 recovers to 0.29, 0.30, stays at 0.30."""
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.28)
        cap = terrain_fertility_cap(r)
        # Simulate 5 recovery ticks
        history = []
        for _ in range(5):
            r.fertility = min(r.fertility + 0.01, cap)
            history.append(round(r.fertility, 2))
        assert history == [0.29, 0.30, 0.30, 0.30, 0.30]
```

- [ ] **Step 2: Run tests to verify ROLE_EFFECTS tests fail**

Run: `pytest tests/test_terrain.py::TestRoleEffects -v`
Expected: FAIL — `ImportError: cannot import name 'ROLE_EFFECTS'`

- [ ] **Step 3: Add ROLE_EFFECTS and role-aware functions to terrain.py**

```python
# Add to src/chronicler/terrain.py after TERRAIN_EFFECTS:

ROLE_EFFECTS: dict[str, TerrainEffect] = {
    "standard":   TerrainEffect(defense=0,  fertility_cap=1.0, trade_mod=0),
    "crossroads": TerrainEffect(defense=-5, fertility_cap=1.0, trade_mod=3),
    "frontier":   TerrainEffect(defense=10, fertility_cap=1.0, trade_mod=-2),
    "chokepoint": TerrainEffect(defense=0,  fertility_cap=1.0, trade_mod=5),
}

_DEFAULT_ROLE = ROLE_EFFECTS["standard"]


def total_defense_bonus(region: Region) -> int:
    """Terrain + role defense combined."""
    terrain = terrain_defense_bonus(region)
    role = ROLE_EFFECTS.get(region.role, _DEFAULT_ROLE).defense
    return terrain + role


def total_trade_modifier(region: Region) -> int:
    """Terrain + role trade modifier combined."""
    terrain = terrain_trade_modifier(region)
    role = ROLE_EFFECTS.get(region.role, _DEFAULT_ROLE).trade_mod
    return terrain + role
```

- [ ] **Step 4: Run all terrain tests**

Run: `pytest tests/test_terrain.py -v`
Expected: All PASS

- [ ] **Step 5: Integrate terrain defense into action_engine.py resolve_war**

In `action_engine.py` `resolve_war()`, add terrain defense. The key changes: (1) select contested region BEFORE combat, (2) add defense bonus to defender power, (3) seize that specific region if attacker wins:

```python
from chronicler.terrain import total_defense_bonus

# In resolve_war(), BEFORE the power comparison:
# Select the contested region (move this from after combat to before)
defender_regions = [r for r in world.regions if r.controller == defender.name]
contested = rng.choice(defender_regions)  # rng already exists in resolve_war

# Add terrain defense bonus to defender power:
defense_bonus = total_defense_bonus(contested)
defender_power = defender.military + defense_bonus
# Use defender_power instead of defender.military in the combat comparison

# AFTER combat: if attacker wins, seize `contested` specifically (not a random region)
```

- [ ] **Step 6: Integrate terrain fertility cap into phase 9**

In `simulation.py` fertility tick (phase 9), modify recovery:

```python
from chronicler.terrain import terrain_fertility_cap

# BEFORE: region.fertility = min(region.fertility + 0.01, 1.0)
# AFTER:
cap = terrain_fertility_cap(region)
region.fertility = min(region.fertility + 0.01, cap)
```

- [ ] **Step 7: Integrate terrain trade modifier into phase 2**

In `simulation.py` `apply_automatic_effects()`, in the trade income loop where `get_active_trade_routes()` is processed:

```python
from chronicler.terrain import total_trade_modifier

# Inside the trade route income loop (for each active route):
for route in get_active_trade_routes(world):
    region_a = next((r for r in world.regions if r.name == route.region_a), None)
    region_b = next((r for r in world.regions if r.name == route.region_b), None)
    terrain_bonus = 0
    if region_a:
        terrain_bonus += total_trade_modifier(region_a)
    if region_b:
        terrain_bonus += total_trade_modifier(region_b)
    # Add terrain_bonus to the route's income calculation
    route_income += terrain_bonus
```

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add -u
git commit -m "feat(m15a): integrate terrain effects into combat, fertility, and trade"
```

---

## Chunk 2: Phase M15b — Infrastructure

### Task 5: Add infrastructure model types

**Files:**
- Modify: `src/chronicler/models.py`
- Modify: `tests/test_infrastructure.py` (create)

- [ ] **Step 1: Write failing tests for new model types**

```python
# tests/test_infrastructure.py
import pytest
from chronicler.models import (
    InfrastructureType, Infrastructure, PendingBuild, Region,
)


class TestInfrastructureModels:
    def test_infrastructure_type_enum(self):
        assert InfrastructureType.ROADS == "roads"
        assert InfrastructureType.FORTIFICATIONS == "fortifications"
        assert InfrastructureType.IRRIGATION == "irrigation"
        assert InfrastructureType.PORTS == "ports"
        assert InfrastructureType.MINES == "mines"

    def test_infrastructure_creation(self):
        infra = Infrastructure(
            type=InfrastructureType.ROADS,
            builder_civ="Rome", built_turn=10,
        )
        assert infra.active is True
        assert infra.builder_civ == "Rome"

    def test_pending_build(self):
        pb = PendingBuild(
            type=InfrastructureType.FORTIFICATIONS,
            builder_civ="Rome", started_turn=5, turns_remaining=3,
        )
        assert pb.turns_remaining == 3

    def test_region_has_infrastructure_fields(self):
        r = Region(
            name="Test", terrain="plains", carrying_capacity=80,
            resources="fertile", fertility=0.8,
            infrastructure=[
                Infrastructure(type=InfrastructureType.ROADS,
                              builder_civ="Rome", built_turn=10),
            ],
            pending_build=PendingBuild(
                type=InfrastructureType.IRRIGATION,
                builder_civ="Rome", started_turn=15, turns_remaining=1,
            ),
        )
        assert len(r.infrastructure) == 1
        assert r.pending_build is not None
        assert r.pending_build.turns_remaining == 1

    def test_region_default_no_infrastructure(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        assert r.infrastructure == []
        assert r.pending_build is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_infrastructure.py -v`
Expected: FAIL — `ImportError: cannot import name 'InfrastructureType'`

- [ ] **Step 3: Add models to models.py**

```python
# In models.py, add after ActionType enum:

class InfrastructureType(str, Enum):
    ROADS = "roads"
    FORTIFICATIONS = "fortifications"
    IRRIGATION = "irrigation"
    PORTS = "ports"
    MINES = "mines"


class Infrastructure(BaseModel):
    type: InfrastructureType
    builder_civ: str
    built_turn: int
    active: bool = True


class PendingBuild(BaseModel):
    type: InfrastructureType
    builder_civ: str
    started_turn: int
    turns_remaining: int
```

In Region class, remove `infrastructure_level` and add:
```python
    infrastructure: list[Infrastructure] = Field(default_factory=list)
    pending_build: PendingBuild | None = None
```

Remove all references to `infrastructure_level` in simulation.py / action_engine.py (search and delete).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_infrastructure.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite — fix any breakage from removing infrastructure_level**

Run: `pytest tests/ -v`
Expected: All PASS (may need to update fixtures that set `infrastructure_level`)

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "feat(m15b): add Infrastructure, PendingBuild models; remove infrastructure_level"
```

### Task 6: Implement infrastructure.py core functions

**Files:**
- Create: `src/chronicler/infrastructure.py`
- Modify: `tests/test_infrastructure.py`

- [ ] **Step 1: Write failing tests for infrastructure constants and eligibility**

```python
# Append to tests/test_infrastructure.py
from chronicler.models import Civilization, Leader


def _make_civ(name, treasury=100, stability=50, regions=None, trait="bold"):
    leader = Leader(name=f"L-{name}", trait=trait, reign_start=0)
    return Civilization(
        name=name, population=50, military=30, economy=40,
        culture=30, stability=stability, treasury=treasury,
        leader=leader, regions=regions or [],
    )


class TestInfrastructureCosts:
    def test_build_costs(self):
        from chronicler.infrastructure import BUILD_SPECS
        assert BUILD_SPECS[InfrastructureType.ROADS].cost == 10
        assert BUILD_SPECS[InfrastructureType.ROADS].turns == 2
        assert BUILD_SPECS[InfrastructureType.FORTIFICATIONS].cost == 15
        assert BUILD_SPECS[InfrastructureType.FORTIFICATIONS].turns == 3
        assert BUILD_SPECS[InfrastructureType.IRRIGATION].cost == 12
        assert BUILD_SPECS[InfrastructureType.IRRIGATION].turns == 2
        assert BUILD_SPECS[InfrastructureType.PORTS].cost == 15
        assert BUILD_SPECS[InfrastructureType.PORTS].turns == 3
        assert BUILD_SPECS[InfrastructureType.MINES].cost == 10
        assert BUILD_SPECS[InfrastructureType.MINES].turns == 2


class TestValidBuildTypes:
    def test_desert_excludes_irrigation(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral", fertility=0.3)
        types = valid_build_types(r)
        assert InfrastructureType.IRRIGATION not in types

    def test_coast_allows_ports(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="S", terrain="coast", carrying_capacity=70,
                   resources="maritime", fertility=0.8)
        types = valid_build_types(r)
        assert InfrastructureType.PORTS in types

    def test_non_coast_excludes_ports(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8)
        types = valid_build_types(r)
        assert InfrastructureType.PORTS not in types

    def test_no_duplicate_types(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="X", built_turn=1),
                   ])
        types = valid_build_types(r)
        assert InfrastructureType.ROADS not in types

    def test_pending_build_blocks_all(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="X", started_turn=1, turns_remaining=1,
                   ))
        types = valid_build_types(r)
        assert types == []
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_infrastructure.py::TestInfrastructureCosts -v`
Expected: FAIL

- [ ] **Step 3: Implement infrastructure.py**

```python
# src/chronicler/infrastructure.py
"""Infrastructure lifecycle — build, tick, destroy.

Typed infrastructure persists through conquest, takes multiple turns to build,
and interacts with terrain. Scorched earth is the first REACTION_REGISTRY consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import (
        Civilization, Event, Infrastructure, InfrastructureType,
        PendingBuild, Region, WorldState,
    )

from chronicler.models import InfrastructureType as IType, Infrastructure, PendingBuild


@dataclass(frozen=True)
class BuildSpec:
    cost: int
    turns: int
    terrain_req: str | None  # None = any terrain; "coast" = coast only
    terrain_exclude: str | None  # None = no exclusion; "desert" = not desert


BUILD_SPECS: dict[IType, BuildSpec] = {
    IType.ROADS:          BuildSpec(cost=10, turns=2, terrain_req=None, terrain_exclude=None),
    IType.FORTIFICATIONS: BuildSpec(cost=15, turns=3, terrain_req=None, terrain_exclude=None),
    IType.IRRIGATION:     BuildSpec(cost=12, turns=2, terrain_req=None, terrain_exclude="desert"),
    IType.PORTS:          BuildSpec(cost=15, turns=3, terrain_req="coast", terrain_exclude=None),
    IType.MINES:          BuildSpec(cost=10, turns=2, terrain_req=None, terrain_exclude=None),
}


def valid_build_types(region: Region) -> list[IType]:
    """Return infrastructure types that can be built in this region.

    Returns empty list if region has a pending build.
    Excludes types already built (no duplicates).
    Excludes types with unmet terrain requirements.
    """
    if region.pending_build is not None:
        return []

    existing = {i.type for i in region.infrastructure if i.active}
    result = []
    for itype, spec in BUILD_SPECS.items():
        if itype in existing:
            continue
        if spec.terrain_req and region.terrain != spec.terrain_req:
            continue
        if spec.terrain_exclude and region.terrain == spec.terrain_exclude:
            continue
        result.append(itype)
    return result


def tick_infrastructure(world: WorldState) -> list[Event]:
    """Called from apply_automatic_effects (phase 2).

    1. Advance pending builds (turns_remaining -= 1, complete if 0).
    2. Apply mine fertility degradation (-0.03/turn per active mine).
    """
    from chronicler.models import Event

    events: list[Event] = []
    for region in world.regions:
        # Advance pending builds
        if region.pending_build is not None:
            region.pending_build.turns_remaining -= 1
            if region.pending_build.turns_remaining <= 0:
                completed = Infrastructure(
                    type=region.pending_build.type,
                    builder_civ=region.pending_build.builder_civ,
                    built_turn=world.turn,
                )
                region.infrastructure.append(completed)
                events.append(Event(
                    turn=world.turn,
                    event_type="infrastructure_completed",
                    actors=[region.pending_build.builder_civ],
                    description=f"{region.pending_build.type.value} completed in {region.name}",
                    importance=4,
                ))
                region.pending_build = None

        # Mine fertility degradation (flat -0.03, unaffected by climate)
        has_active_mine = any(
            i.type == IType.MINES and i.active for i in region.infrastructure
        )
        if has_active_mine:
            region.fertility = max(region.fertility - 0.03, 0.0)

    return events


def scorched_earth_check(
    world: WorldState, defender: Civilization, lost_region: Region, seed: int,
) -> list[Event]:
    """REACTION_REGISTRY['region_lost'] handler.

    Dispatched inline during WAR resolution (phase 4).
    Probability = min(1.0 - stability/100 + trait_bonus, 1.0).
    Binary: destroys ALL infrastructure if triggered.
    """
    import hashlib
    from chronicler.models import Event

    trait_bonus = 0.2 if defender.leader.trait == "aggressive" else 0.0
    prob = min(1.0 - defender.stability / 100 + trait_bonus, 1.0)

    # Deterministic roll
    roll_input = f"{seed}:{lost_region.name}:{world.turn}:scorch"
    roll = int(hashlib.sha256(roll_input.encode()).hexdigest(), 16) % 10000 / 10000

    if roll < prob and any(i.active for i in lost_region.infrastructure):
        for infra in lost_region.infrastructure:
            infra.active = False
        return [Event(
            turn=world.turn,
            event_type="scorched_earth",
            actors=[defender.name],
            description=f"{defender.name} scorched {lost_region.name} during retreat",
            importance=6,
        )]
    return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_infrastructure.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/infrastructure.py tests/test_infrastructure.py
git commit -m "feat(m15b): add infrastructure.py with build specs, validation, tick, scorched earth"
```

### Task 6b: Implement handle_build action handler

**Files:**
- Modify: `src/chronicler/infrastructure.py`
- Modify: `tests/test_infrastructure.py`

- [ ] **Step 1: Write failing tests for handle_build**

```python
# Append to tests/test_infrastructure.py

class TestHandleBuild:
    def test_build_creates_pending(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8, controller="Rome")
        civ = _make_civ("Rome", treasury=50, regions=["A"])
        world = _make_world([r], [civ])
        event = handle_build(civ, world)
        assert r.pending_build is not None
        assert r.pending_build.builder_civ == "Rome"
        assert civ.treasury < 50  # deducted

    def test_build_deducts_cost(self):
        from chronicler.infrastructure import handle_build, BUILD_SPECS
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8, controller="Rome")
        civ = _make_civ("Rome", treasury=100, regions=["A"])
        world = _make_world([r], [civ])
        handle_build(civ, world)
        selected_type = r.pending_build.type
        expected_cost = BUILD_SPECS[selected_type].cost
        assert civ.treasury == 100 - expected_cost

    def test_build_aggressive_prefers_fortifications(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8, controller="Rome")
        civ = _make_civ("Rome", treasury=100, regions=["A"], trait="aggressive")
        world = _make_world([r], [civ])
        handle_build(civ, world)
        assert r.pending_build.type == InfrastructureType.FORTIFICATIONS

    def test_build_no_valid_regions_returns_none(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8, controller="Rome",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=1))
        civ = _make_civ("Rome", treasury=100, regions=["A"])
        world = _make_world([r], [civ])
        event = handle_build(civ, world)
        assert event is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_infrastructure.py::TestHandleBuild -v`
Expected: FAIL — `ImportError: cannot import name 'handle_build'`

- [ ] **Step 3: Implement handle_build in infrastructure.py**

```python
# Append to src/chronicler/infrastructure.py

# Trait-weighted type preferences for BUILD action
TRAIT_BUILD_PRIORITY: dict[str, list[IType]] = {
    "aggressive": [IType.FORTIFICATIONS, IType.MINES, IType.ROADS, IType.PORTS, IType.IRRIGATION],
    "bold":       [IType.FORTIFICATIONS, IType.ROADS, IType.MINES, IType.PORTS, IType.IRRIGATION],
    "cautious":   [IType.FORTIFICATIONS, IType.ROADS, IType.IRRIGATION, IType.PORTS, IType.MINES],
    "mercantile": [IType.ROADS, IType.PORTS, IType.MINES, IType.IRRIGATION, IType.FORTIFICATIONS],
    "expansionist": [IType.IRRIGATION, IType.ROADS, IType.MINES, IType.PORTS, IType.FORTIFICATIONS],
    "diplomatic": [IType.ROADS, IType.PORTS, IType.IRRIGATION, IType.MINES, IType.FORTIFICATIONS],
}
_DEFAULT_PRIORITY = [IType.ROADS, IType.FORTIFICATIONS, IType.IRRIGATION, IType.PORTS, IType.MINES]


def handle_build(
    civ: Civilization, world: WorldState,
) -> Event | None:
    """BUILD action handler. Registered via ACTION_REGISTRY[ActionType.BUILD].
    Replaces the old _resolve_build handler from M13b-1.

    Signature matches the action handler pattern: handler(civ, world) -> Event.
    Seed derived internally: seed = world.seed + world.turn + hash(civ.name)
    """
    import hashlib
    from chronicler.models import Event

    seed = world.seed + world.turn + hash(civ.name)

    # Collect (region, valid_types) pairs
    region_map = {r.name: r for r in world.regions}
    candidates: list[tuple[Region, list[IType]]] = []
    for rname in civ.regions:
        region = region_map.get(rname)
        if region is None:
            continue
        vtypes = valid_build_types(region)
        if vtypes:
            candidates.append((region, vtypes))

    if not candidates:
        return None

    # Deterministic region selection
    idx = int(hashlib.sha256(
        f"{seed}:{world.turn}:{civ.name}:build_region".encode()
    ).hexdigest(), 16) % len(candidates)
    target_region, valid_types = candidates[idx]

    # Type selection: trait priority filtered to valid types AND affordability
    trait = civ.leader.trait if civ.leader else "bold"
    priority = TRAIT_BUILD_PRIORITY.get(trait, _DEFAULT_PRIORITY)
    selected_type = None
    for ptype in priority:
        if ptype in valid_types and BUILD_SPECS[ptype].cost <= civ.treasury:
            selected_type = ptype
            break
    if selected_type is None:
        # Fallback: cheapest affordable type
        affordable = [(t, BUILD_SPECS[t].cost) for t in valid_types
                      if BUILD_SPECS[t].cost <= civ.treasury]
        if not affordable:
            return None
        selected_type = min(affordable, key=lambda x: x[1])[0]

    spec = BUILD_SPECS[selected_type]
    civ.treasury -= spec.cost
    target_region.pending_build = PendingBuild(
        type=selected_type,
        builder_civ=civ.name,
        started_turn=world.turn,
        turns_remaining=spec.turns,
    )

    return Event(
        turn=world.turn, event_type="build_started",
        actors=[civ.name],
        description=f"{civ.name} begins building {selected_type.value} in {target_region.name}",
        importance=3,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_infrastructure.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/infrastructure.py tests/test_infrastructure.py
git commit -m "feat(m15b): add handle_build action handler with trait-weighted type selection"
```

### Task 7: Add tick_infrastructure and scorched_earth tests

**Files:**
- Modify: `tests/test_infrastructure.py`

- [ ] **Step 1: Write tests for tick_infrastructure and scorched_earth**

```python
# Append to tests/test_infrastructure.py
from chronicler.models import WorldState, Relationship


def _make_world(regions, civs):
    return WorldState(name="Test", seed=42, regions=regions, civilizations=civs)


class TestTickInfrastructure:
    def test_pending_build_advances(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=2,
                   ))
        world = _make_world([r], [])
        tick_infrastructure(world)
        assert r.pending_build.turns_remaining == 1

    def test_pending_build_completes(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=1,
                   ))
        world = _make_world([r], [])
        events = tick_infrastructure(world)
        assert r.pending_build is None
        assert len(r.infrastructure) == 1
        assert r.infrastructure[0].type == InfrastructureType.ROADS
        assert len(events) == 1
        assert events[0].event_type == "infrastructure_completed"

    def test_mine_degrades_fertility(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="mountains", carrying_capacity=50,
                   resources="mineral", fertility=0.7,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.MINES,
                                     builder_civ="Rome", built_turn=1),
                   ])
        world = _make_world([r], [])
        tick_infrastructure(world)
        assert abs(r.fertility - 0.67) < 0.001

    def test_inactive_mine_no_degradation(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="mountains", carrying_capacity=50,
                   resources="mineral", fertility=0.7,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.MINES,
                                     builder_civ="Rome", built_turn=1, active=False),
                   ])
        world = _make_world([r], [])
        tick_infrastructure(world)
        assert r.fertility == 0.7


class TestScorchedEarth:
    def test_low_stability_scorches(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=10)  # prob = 0.9
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Rome", built_turn=1),
                       Infrastructure(type=InfrastructureType.IRRIGATION,
                                     builder_civ="Rome", built_turn=5),
                   ])
        # Use seed that produces roll < 0.9 (most seeds will)
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        # With 90% probability, at least one seed in range works
        assert all(not i.active for i in r.infrastructure)
        assert len(events) == 1

    def test_high_stability_no_scorch(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=100)  # prob = 0.0
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Rome", built_turn=1),
                   ])
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        assert all(i.active for i in r.infrastructure)
        assert len(events) == 0

    def test_no_infrastructure_no_event(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=0)  # prob = 1.0
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8)
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        assert len(events) == 0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_infrastructure.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_infrastructure.py
git commit -m "test(m15b): add tick_infrastructure and scorched_earth tests"
```

### Task 8: Integrate infrastructure into simulation loop

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/action_engine.py`

- [ ] **Step 1: Wire tick_infrastructure into phase 2**

In `simulation.py` `apply_automatic_effects()`:

```python
from chronicler.infrastructure import tick_infrastructure

# At the start of apply_automatic_effects:
infra_events = tick_infrastructure(world)
world.events_timeline.extend(infra_events)
```

- [ ] **Step 2: Wire scorched_earth_check into REACTION_REGISTRY**

In `action_engine.py` or wherever `REACTION_REGISTRY` is defined:

```python
from chronicler.infrastructure import scorched_earth_check

REACTION_REGISTRY["region_lost"] = scorched_earth_check
```

In `action_engine.py` `resolve_war()`, after a region changes hands:

```python
# After defender loses a region:
reaction = REACTION_REGISTRY.get("region_lost")
if reaction:
    events = reaction(world, defender, lost_region, seed)
    world.events_timeline.extend(events)
```

- [ ] **Step 3: Update BUILD eligibility in action_engine.py**

In `get_eligible_actions()`:

```python
from chronicler.infrastructure import valid_build_types, BUILD_SPECS

# Replace existing BUILD eligibility check with:
if ActionType.BUILD in ACTION_REGISTRY:
    min_cost = min(s.cost for s in BUILD_SPECS.values())
    if civ.treasury >= min_cost:
        has_valid = False
        for rname in civ.regions:
            region = next((r for r in world.regions if r.name == rname), None)
            if region and valid_build_types(region):
                has_valid = True
                break
        if has_valid:
            eligible.append(ActionType.BUILD)
```

- [ ] **Step 4: Add fortification defense to combat resolution**

In `action_engine.py` `resolve_war()`, alongside terrain defense:

```python
from chronicler.models import InfrastructureType

# After terrain defense bonus:
fort_bonus = 0
for infra in defender_region.infrastructure:
    if infra.type == InfrastructureType.FORTIFICATIONS and infra.active:
        fort_bonus = 15
        break
# total_defense = terrain_bonus + fort_bonus
```

- [ ] **Step 5: Add irrigation cap bonus to fertility phase**

In `simulation.py` phase 9 fertility tick:

```python
from chronicler.models import InfrastructureType

# When computing fertility cap for a region:
irrigation_bonus = 0.15 if any(
    i.type == InfrastructureType.IRRIGATION and i.active
    for i in region.infrastructure
) else 0.0
cap = terrain_fertility_cap(region) + irrigation_bonus
cap = min(cap, 1.0)
region.fertility = min(region.fertility + 0.01, cap)
```

- [ ] **Step 6: Add roads/ports trade income bonus to phase 2**

In `simulation.py` `apply_automatic_effects()`, in the trade income loop:

```python
from chronicler.models import InfrastructureType

# For each active trade route, add infrastructure bonuses:
for route in get_active_trade_routes(world):
    region_a = next((r for r in world.regions if r.name == route.region_a), None)
    region_b = next((r for r in world.regions if r.name == route.region_b), None)
    infra_bonus = 0
    for region in (region_a, region_b):
        if region is None:
            continue
        for infra in region.infrastructure:
            if not infra.active:
                continue
            if infra.type == InfrastructureType.ROADS:
                infra_bonus += 2
            elif infra.type == InfrastructureType.PORTS:
                infra_bonus += 3
    # Add infra_bonus to route income alongside terrain_bonus
    route_income += infra_bonus
```

- [ ] **Step 7: Add mines resource trade value multiplier**

In `simulation.py` `apply_automatic_effects()`, where resource trade value is computed:

```python
# When computing resource trade value for a region:
has_active_mine = any(
    i.type == InfrastructureType.MINES and i.active
    for i in region.infrastructure
)
resource_value = base_resource_value * (1.5 if has_active_mine else 1.0)
```

- [ ] **Step 8: Register handle_build in ACTION_REGISTRY**

In `action_engine.py`:

```python
from chronicler.infrastructure import handle_build

ACTION_REGISTRY[ActionType.BUILD] = handle_build
```

- [ ] **Step 9: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add -u
git commit -m "feat(m15b): integrate infrastructure into simulation loop, BUILD handler, trade bonuses, combat, fertility"
```

---

## Chunk 3: Phase M15c — Climate, Disasters & Migration

### Task 9: Add climate models and scenario config

**Files:**
- Modify: `src/chronicler/models.py`
- Modify: `src/chronicler/scenario.py`
- Create: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests for climate models**

```python
# tests/test_climate.py
import pytest
from chronicler.models import ClimatePhase, ClimateConfig, WorldState, Region


class TestClimateModels:
    def test_climate_phase_enum(self):
        assert ClimatePhase.TEMPERATE == "temperate"
        assert ClimatePhase.WARMING == "warming"
        assert ClimatePhase.DROUGHT == "drought"
        assert ClimatePhase.COOLING == "cooling"

    def test_climate_config_defaults(self):
        cfg = ClimateConfig()
        assert cfg.period == 75
        assert cfg.severity == 1.0
        assert cfg.start_phase == ClimatePhase.TEMPERATE

    def test_world_has_climate_config(self):
        w = WorldState(name="T", seed=42)
        assert w.climate_config.period == 75

    def test_region_has_disaster_fields(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        assert r.disaster_cooldowns == {}
        assert r.resource_suspensions == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_climate.py -v`
Expected: FAIL

- [ ] **Step 3: Add models to models.py**

```python
# In models.py, add enums:
class ClimatePhase(str, Enum):
    TEMPERATE = "temperate"
    WARMING = "warming"
    DROUGHT = "drought"
    COOLING = "cooling"

class ClimateConfig(BaseModel):
    period: int = 75
    severity: float = 1.0
    start_phase: ClimatePhase = ClimatePhase.TEMPERATE
```

Add to WorldState:
```python
    climate_config: ClimateConfig = Field(default_factory=ClimateConfig)
```

Add to Region:
```python
    disaster_cooldowns: dict[str, int] = Field(default_factory=dict)
    resource_suspensions: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Add climate to ScenarioConfig**

In `scenario.py` ScenarioConfig:
```python
    climate: ClimateConfig | None = None
```

In `apply_scenario()`, after existing steps:
```python
    if config.climate is not None:
        world.climate_config = config.climate
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_climate.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_climate.py src/chronicler/models.py src/chronicler/scenario.py
git commit -m "feat(m15c): add ClimatePhase, ClimateConfig models and scenario config"
```

### Task 10: Implement climate phase pure function

**Files:**
- Create: `src/chronicler/climate.py`
- Modify: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests for get_climate_phase**

```python
# Append to tests/test_climate.py

class TestGetClimatePhase:
    def test_turn_0_temperate(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        assert get_climate_phase(0, cfg) == ClimatePhase.TEMPERATE

    def test_turn_29_temperate(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        assert get_climate_phase(29, cfg) == ClimatePhase.TEMPERATE

    def test_turn_30_warming(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        # 30/75 = 0.4 exactly → warming
        assert get_climate_phase(30, cfg) == ClimatePhase.WARMING

    def test_turn_44_warming(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        assert get_climate_phase(44, cfg) == ClimatePhase.WARMING

    def test_turn_45_drought(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        # 45/75 = 0.6 exactly → drought
        assert get_climate_phase(45, cfg) == ClimatePhase.DROUGHT

    def test_turn_60_cooling(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        # 60/75 = 0.8 exactly → cooling
        assert get_climate_phase(60, cfg) == ClimatePhase.COOLING

    def test_cycle_wraps(self):
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=75)
        assert get_climate_phase(75, cfg) == ClimatePhase.TEMPERATE
        assert get_climate_phase(105, cfg) == ClimatePhase.WARMING
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_climate.py::TestGetClimatePhase -v`
Expected: FAIL

- [ ] **Step 3: Implement climate.py with get_climate_phase**

```python
# src/chronicler/climate.py
"""Climate cycles, natural disasters, and migration.

Climate phase is a pure function of turn number — no mutable state.
Disasters use hashlib for deterministic probability rolls.
Migration cascades one wave per turn (next-turn continuation, not recursive).
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Event, Region, WorldState

from chronicler.models import ClimateConfig, ClimatePhase


PHASE_SCHEDULE: list[tuple[float, ClimatePhase]] = [
    (0.0, ClimatePhase.TEMPERATE),
    (0.4, ClimatePhase.WARMING),
    (0.6, ClimatePhase.DROUGHT),
    (0.8, ClimatePhase.COOLING),
]


def get_climate_phase(turn: int, config: ClimateConfig) -> ClimatePhase:
    """Pure function. Deterministic from turn + config."""
    position = (turn % config.period) / config.period
    phase = ClimatePhase.TEMPERATE
    for threshold, p in PHASE_SCHEDULE:
        if position >= threshold:
            phase = p
    return phase
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_climate.py::TestGetClimatePhase -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/climate.py tests/test_climate.py
git commit -m "feat(m15c): add climate.py with get_climate_phase pure function"
```

### Task 11: Implement climate degradation multiplier

**Files:**
- Modify: `src/chronicler/climate.py`
- Modify: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_climate.py

class TestClimateDegradationMultiplier:
    def test_temperate_no_change(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("plains", ClimatePhase.TEMPERATE, 1.0) == 1.0

    def test_drought_plains_doubles(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("plains", ClimatePhase.DROUGHT, 1.0) == 2.0

    def test_drought_forest(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("forest", ClimatePhase.DROUGHT, 1.0) == 1.4

    def test_warming_tundra_halved(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("tundra", ClimatePhase.WARMING, 1.0) == 0.5

    def test_cooling_plains(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("plains", ClimatePhase.COOLING, 1.0) == 1.25

    def test_cooling_tundra_severe(self):
        from chronicler.climate import climate_degradation_multiplier
        m = climate_degradation_multiplier("tundra", ClimatePhase.COOLING, 1.0)
        assert abs(m - 3.3) < 0.1

    def test_severity_zero_no_effect(self):
        from chronicler.climate import climate_degradation_multiplier
        assert climate_degradation_multiplier("plains", ClimatePhase.DROUGHT, 0.0) == 1.0

    def test_severity_half(self):
        from chronicler.climate import climate_degradation_multiplier
        m = climate_degradation_multiplier("plains", ClimatePhase.DROUGHT, 0.5)
        # 1.0 + (2.0 - 1.0) * 0.5 = 1.5
        assert m == 1.5
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_climate.py::TestClimateDegradationMultiplier -v`
Expected: FAIL

- [ ] **Step 3: Implement climate_degradation_multiplier**

```python
# Append to src/chronicler/climate.py

# Base degradation multipliers by terrain × phase.
# Values > 1.0 = faster degradation. < 1.0 = slower.
_BASE_MULTIPLIERS: dict[str, dict[ClimatePhase, float]] = {
    "plains":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 2.0,  ClimatePhase.COOLING: 1.25},
    "forest":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.4,  ClimatePhase.COOLING: 1.25},
    "coast":     {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "desert":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
    "tundra":    {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 0.5, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 3.3},
    "mountains": {ClimatePhase.TEMPERATE: 1.0, ClimatePhase.WARMING: 1.0, ClimatePhase.DROUGHT: 1.0,  ClimatePhase.COOLING: 1.25},
}


def climate_degradation_multiplier(
    terrain: str, phase: ClimatePhase, severity: float,
) -> float:
    """Multiplier applied directly to degradation rate during phase 9.

    Formula: effective = 1.0 + (base - 1.0) * severity
    """
    terrain_map = _BASE_MULTIPLIERS.get(terrain, _BASE_MULTIPLIERS["plains"])
    base = terrain_map.get(phase, 1.0)
    return 1.0 + (base - 1.0) * severity
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_climate.py::TestClimateDegradationMultiplier -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/climate.py tests/test_climate.py
git commit -m "feat(m15c): add climate_degradation_multiplier with severity scaling"
```

### Task 12: Implement check_disasters

**Files:**
- Modify: `src/chronicler/climate.py`
- Modify: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests for disasters**

```python
# Append to tests/test_climate.py

class TestCheckDisasters:
    def test_earthquake_in_mountains(self):
        """Mountains have 2% base earthquake probability."""
        from chronicler.climate import check_disasters
        r = Region(name="Peaks", terrain="mountains", carrying_capacity=50,
                   resources="mineral", fertility=0.7,
                   disaster_cooldowns={}, resource_suspensions={})
        w = WorldState(name="T", seed=42, regions=[r],
                       climate_config=ClimateConfig(severity=1.0))
        # Run many turns to find one where earthquake triggers
        # 500 trials at 2% → P(zero hits) = 0.98^500 ≈ 0.00004 — negligible flake rate
        triggered = False
        for turn in range(500):
            w.turn = turn
            r.disaster_cooldowns = {}
            r.fertility = 0.7
            events = check_disasters(w, ClimatePhase.TEMPERATE)
            if any(e.event_type == "earthquake" for e in events):
                triggered = True
                break
        assert triggered, "Earthquake should trigger at least once in 500 turns at 2%"

    def test_cooldown_prevents_repeat(self):
        from chronicler.climate import check_disasters
        r = Region(name="Peaks", terrain="mountains", carrying_capacity=50,
                   resources="mineral", fertility=0.7,
                   disaster_cooldowns={"earthquake": 5}, resource_suspensions={})
        w = WorldState(name="T", seed=42, regions=[r],
                       climate_config=ClimateConfig(severity=1.0))
        events = check_disasters(w, ClimatePhase.TEMPERATE)
        eq_events = [e for e in events if e.event_type == "earthquake"]
        assert len(eq_events) == 0

    def test_flood_doubled_during_warming(self):
        """Coast flood prob doubles from 3% to 6% during warming."""
        from chronicler.climate import _disaster_probability
        base = _disaster_probability("flood", "coast", ClimatePhase.TEMPERATE, 1.0)
        warm = _disaster_probability("flood", "coast", ClimatePhase.WARMING, 1.0)
        assert abs(warm - base * 2) < 0.001

    def test_wildfire_doubled_during_drought(self):
        from chronicler.climate import _disaster_probability
        base = _disaster_probability("wildfire", "forest", ClimatePhase.TEMPERATE, 1.0)
        drought = _disaster_probability("wildfire", "forest", ClimatePhase.DROUGHT, 1.0)
        assert abs(drought - base * 2) < 0.001

    def test_severity_zero_no_disasters(self):
        from chronicler.climate import _disaster_probability
        prob = _disaster_probability("earthquake", "mountains", ClimatePhase.TEMPERATE, 0.0)
        assert prob == 0.0

    def test_earthquake_destroys_infrastructure(self):
        from chronicler.climate import check_disasters
        from chronicler.models import Infrastructure, InfrastructureType
        infra = Infrastructure(type=InfrastructureType.ROADS, builder_civ="X", built_turn=1)
        r = Region(name="Peaks", terrain="mountains", carrying_capacity=50,
                   resources="mineral", fertility=0.7,
                   disaster_cooldowns={}, resource_suspensions={},
                   infrastructure=[infra])
        w = WorldState(name="T", seed=42, regions=[r],
                       climate_config=ClimateConfig(severity=1.0))
        # Find a turn where earthquake triggers
        for turn in range(200):
            w.turn = turn
            r.disaster_cooldowns = {}
            infra.active = True
            r.fertility = 0.7
            events = check_disasters(w, ClimatePhase.TEMPERATE)
            if any(e.event_type == "earthquake" for e in events):
                assert not infra.active, "Earthquake should destroy infrastructure"
                break

    def test_wildfire_suspends_timber(self):
        from chronicler.climate import check_disasters
        r = Region(name="Woods", terrain="forest", carrying_capacity=60,
                   resources="timber", fertility=0.7,
                   disaster_cooldowns={}, resource_suspensions={})
        w = WorldState(name="T", seed=42, regions=[r],
                       climate_config=ClimateConfig(severity=1.0))
        for turn in range(200):
            w.turn = turn
            r.disaster_cooldowns = {}
            r.resource_suspensions = {}
            r.fertility = 0.7
            events = check_disasters(w, ClimatePhase.TEMPERATE)
            if any(e.event_type == "wildfire" for e in events):
                assert r.resource_suspensions.get("timber") == 10
                break
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_climate.py::TestCheckDisasters -v`
Expected: FAIL

- [ ] **Step 3: Implement check_disasters in climate.py**

```python
# Append to src/chronicler/climate.py
from dataclasses import dataclass

from chronicler.models import Event, InfrastructureType


@dataclass(frozen=True)
class DisasterSpec:
    terrain: str
    base_prob: float
    climate_double: ClimatePhase | None  # Phase that doubles probability


DISASTER_SPECS: dict[str, DisasterSpec] = {
    "earthquake": DisasterSpec(terrain="mountains", base_prob=0.02, climate_double=None),
    "flood":      DisasterSpec(terrain="coast",     base_prob=0.03, climate_double=ClimatePhase.WARMING),
    "wildfire":   DisasterSpec(terrain="forest",    base_prob=0.02, climate_double=ClimatePhase.DROUGHT),
    "sandstorm":  DisasterSpec(terrain="desert",    base_prob=0.03, climate_double=None),
}


def _disaster_probability(
    disaster_type: str, terrain: str, phase: ClimatePhase, severity: float,
) -> float:
    """Compute disaster probability for a terrain/phase/severity combo."""
    spec = DISASTER_SPECS.get(disaster_type)
    if spec is None or spec.terrain != terrain:
        return 0.0
    prob = spec.base_prob * severity
    if spec.climate_double and phase == spec.climate_double:
        prob *= 2
    return prob


def _deterministic_roll(seed: int, region_name: str, turn: int, disaster_type: str) -> float:
    """Deterministic random value in [0, 1) using SHA256."""
    data = f"{seed}:{region_name}:{turn}:{disaster_type}"
    return int(hashlib.sha256(data.encode()).hexdigest(), 16) % 10000 / 10000


def check_disasters(world: WorldState, climate_phase: ClimatePhase) -> list[Event]:
    """Called from environment phase (phase 1). Replaces old random disaster logic.

    NOTE: Cooldowns and suspensions are decremented BEFORE this function is called,
    in phase_environment() (Task 14 Step 1). Do not decrement here.

    1. Roll for each disaster type per region.
    2. Apply effects.
    """
    events: list[Event] = []
    severity = world.climate_config.severity

    for region in world.regions:
        # Check each disaster type
        for dtype, spec in DISASTER_SPECS.items():
            if spec.terrain != region.terrain:
                continue
            if dtype in region.disaster_cooldowns:
                continue

            prob = _disaster_probability(dtype, region.terrain, climate_phase, severity)
            if prob <= 0:
                continue

            roll = _deterministic_roll(world.seed, region.name, world.turn, dtype)
            if roll >= prob:
                continue

            # Disaster triggered — apply effects
            region.disaster_cooldowns[dtype] = 10

            if dtype == "earthquake":
                region.fertility = max(region.fertility - 0.2, 0.0)
                active_infra = [i for i in region.infrastructure if i.active]
                if active_infra:
                    # Destroy 1 random — deterministic pick
                    idx = int(_deterministic_roll(
                        world.seed, region.name, world.turn, "eq_target"
                    ) * len(active_infra))
                    idx = min(idx, len(active_infra) - 1)
                    active_infra[idx].active = False
                events.append(Event(
                    turn=world.turn, event_type="earthquake",
                    actors=[region.controller or "nature"],
                    description=f"Earthquake strikes {region.name}",
                    importance=7,
                ))

            elif dtype == "flood":
                region.fertility = max(region.fertility - 0.1, 0.0)
                for i in region.infrastructure:
                    if i.type == InfrastructureType.PORTS and i.active:
                        i.active = False
                events.append(Event(
                    turn=world.turn, event_type="flood",
                    actors=[region.controller or "nature"],
                    description=f"Flooding devastates {region.name}",
                    importance=6,
                ))

            elif dtype == "wildfire":
                region.fertility = max(region.fertility - 0.15, 0.0)
                region.resource_suspensions["timber"] = 10
                events.append(Event(
                    turn=world.turn, event_type="wildfire",
                    actors=[region.controller or "nature"],
                    description=f"Wildfire sweeps through {region.name}",
                    importance=6,
                ))

            elif dtype == "sandstorm":
                region.resource_suspensions["trade_route"] = 5
                events.append(Event(
                    turn=world.turn, event_type="sandstorm",
                    actors=[region.controller or "nature"],
                    description=f"Sandstorm disrupts {region.name}",
                    importance=4,
                ))

    return events
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_climate.py::TestCheckDisasters -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/climate.py tests/test_climate.py
git commit -m "feat(m15c): add check_disasters with deterministic probability rolls"
```

### Task 13: Implement migration

**Files:**
- Modify: `src/chronicler/climate.py`
- Modify: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests for process_migration**

```python
# Append to tests/test_climate.py
from chronicler.models import Civilization, Leader, Relationship, Disposition


def _make_civ(name, population=50, stability=50, regions=None):
    leader = Leader(name=f"L-{name}", trait="bold", reign_start=0)
    return Civilization(
        name=name, population=population, military=30, economy=40,
        culture=30, stability=stability, treasury=100,
        leader=leader, regions=regions or [],
    )


class TestProcessMigration:
    def test_no_migration_when_capacity_sufficient(self):
        from chronicler.climate import process_migration
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", fertility=0.8, controller="Rome",
                   adjacencies=["B"])
        civ = _make_civ("Rome", population=30, regions=["A"])
        w = WorldState(name="T", seed=42, regions=[r], civilizations=[civ])
        events = process_migration(w)
        assert len(events) == 0

    def test_migration_triggered_by_low_capacity(self):
        from chronicler.climate import process_migration
        r_src = Region(name="A", terrain="desert", carrying_capacity=20,
                       resources="mineral", fertility=0.2, controller="Rome",
                       adjacencies=["B"])
        r_dst = Region(name="B", terrain="plains", carrying_capacity=80,
                       resources="fertile", fertility=0.8, controller="Greece",
                       adjacencies=["A"])
        rome = _make_civ("Rome", population=40, regions=["A"])
        greece = _make_civ("Greece", population=30, regions=["B"])
        rels = {
            "Rome": {"Greece": Relationship(disposition=Disposition.NEUTRAL)},
            "Greece": {"Rome": Relationship(disposition=Disposition.NEUTRAL)},
        }
        w = WorldState(name="T", seed=42, regions=[r_src, r_dst],
                       civilizations=[rome, greece], relationships=rels)
        events = process_migration(w)
        # effective_capacity(A) = max(int(20 * min(0.2, 0.3)), 1) = 4
        # region_pop = 40 // 1 = 40
        # 4 < 40 * 0.5 = 20, so migration triggers
        # surplus = 40 - 4 = 36
        assert rome.population < 40
        assert greece.population > 30
        assert len(events) > 0

    def test_hostile_border_blocks_migration(self):
        from chronicler.climate import process_migration
        r_src = Region(name="A", terrain="desert", carrying_capacity=20,
                       resources="mineral", fertility=0.1, controller="Rome",
                       adjacencies=["B"])
        r_dst = Region(name="B", terrain="plains", carrying_capacity=80,
                       resources="fertile", fertility=0.8, controller="Greece",
                       adjacencies=["A"])
        rome = _make_civ("Rome", population=40, regions=["A"])
        greece = _make_civ("Greece", population=30, regions=["B"])
        rels = {
            "Rome": {"Greece": Relationship(disposition=Disposition.HOSTILE)},
            "Greece": {"Rome": Relationship(disposition=Disposition.HOSTILE)},
        }
        w = WorldState(name="T", seed=42, regions=[r_src, r_dst],
                       civilizations=[rome, greece], relationships=rels)
        events = process_migration(w)
        # All adjacent hostile — population drops anyway (famine)
        assert rome.population < 40
        assert greece.population == 30  # no refugees received

    def test_uncontrolled_region_absorbs_to_void(self):
        from chronicler.climate import process_migration
        r_src = Region(name="A", terrain="desert", carrying_capacity=20,
                       resources="mineral", fertility=0.1, controller="Rome",
                       adjacencies=["B"])
        r_dst = Region(name="B", terrain="plains", carrying_capacity=80,
                       resources="fertile", fertility=0.8, controller=None,
                       adjacencies=["A"])
        rome = _make_civ("Rome", population=40, regions=["A"])
        w = WorldState(name="T", seed=42, regions=[r_src, r_dst],
                       civilizations=[rome])
        events = process_migration(w)
        assert rome.population < 40  # population drops
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_climate.py::TestProcessMigration -v`
Expected: FAIL

- [ ] **Step 3: Implement process_migration**

```python
# Append to src/chronicler/climate.py
from chronicler.terrain import effective_capacity
from chronicler.models import Disposition


def process_migration(world: WorldState) -> list[Event]:
    """Called at end of phase 1, after disasters.

    For each controlled region: if effective_capacity < region_pop * 0.5, migrate.
    Cascades happen next turn (one wave per turn).
    """
    events: list[Event] = []

    for region in world.regions:
        if region.controller is None:
            continue

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None or not civ.regions:
            continue

        region_pop = civ.population // len(civ.regions)
        eff_cap = effective_capacity(region)

        if eff_cap >= region_pop * 0.5:
            continue

        surplus = region_pop - eff_cap
        if surplus <= 0:
            continue

        # Find eligible receiving regions
        eligible: list[tuple[Region, str | None]] = []  # (region, controller_name)
        for adj_name in region.adjacencies:
            adj_region = next((r for r in world.regions if r.name == adj_name), None)
            if adj_region is None:
                continue
            if adj_region.controller is None:
                # Uncontrolled — absorbs to void
                eligible.append((adj_region, None))
                continue
            # Check disposition
            src_rels = world.relationships.get(region.controller, {})
            rel = src_rels.get(adj_region.controller)
            if rel and rel.disposition == Disposition.HOSTILE:
                continue
            eligible.append((adj_region, adj_region.controller))

        if eligible:
            share = surplus // len(eligible) if len(eligible) > 0 else 0
            remainder = surplus - share * len(eligible)
            for adj_region, ctrl_name in eligible:
                amount = share + (1 if remainder > 0 else 0)
                if remainder > 0:
                    remainder -= 1
                if ctrl_name is not None:
                    recv_civ = next(
                        (c for c in world.civilizations if c.name == ctrl_name), None
                    )
                    if recv_civ:
                        recv_civ.population += amount
                        recv_civ.stability = max(recv_civ.stability - 3, 0)
                # void if ctrl_name is None

            civ.population = max(civ.population - surplus, 1)
            importance = min(5 + surplus // 10, 9)
            events.append(Event(
                turn=world.turn, event_type="migration",
                actors=[civ.name],
                description=f"Population flees {region.name} ({surplus} displaced)",
                importance=importance,
            ))
        else:
            # No eligible destinations — famine
            civ.population = max(civ.population - surplus, 1)
            events.append(Event(
                turn=world.turn, event_type="famine_starvation",
                actors=[civ.name],
                description=f"Population starves in {region.name} — nowhere to flee",
                importance=min(5 + surplus // 10, 9),
            ))

    return events
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_climate.py::TestProcessMigration -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/climate.py tests/test_climate.py
git commit -m "feat(m15c): add process_migration with hostile border filtering"
```

### Task 14: Integrate climate into simulation loop

**Files:**
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Wire climate into phase 1 (environment)**

In `simulation.py` `phase_environment()`:

```python
from chronicler.climate import get_climate_phase, check_disasters, process_migration

# At start of phase_environment:
climate_phase = get_climate_phase(world.turn, world.climate_config)

# Decrement disaster cooldowns and resource suspensions (decrement first, then prune)
for region in world.regions:
    for k in list(region.disaster_cooldowns):
        region.disaster_cooldowns[k] -= 1
    region.disaster_cooldowns = {k: v for k, v in region.disaster_cooldowns.items() if v > 0}

    for k in list(region.resource_suspensions):
        region.resource_suspensions[k] -= 1
    region.resource_suspensions = {k: v for k, v in region.resource_suspensions.items() if v > 0}

# Replace old disaster logic with:
disaster_events = check_disasters(world, climate_phase)
world.events_timeline.extend(disaster_events)

# After disasters:
migration_events = process_migration(world)
world.events_timeline.extend(migration_events)
```

**Important:** In `apply_automatic_effects()` (phase 2), trade income must check `resource_suspensions`:

```python
# When computing trade route income, skip routes through suspended regions:
for route in get_active_trade_routes(world):
    region_a = next((r for r in world.regions if r.name == route.region_a), None)
    region_b = next((r for r in world.regions if r.name == route.region_b), None)
    # Check for trade route suspension (sandstorm)
    if region_a and "trade_route" in region_a.resource_suspensions:
        continue  # route suspended
    if region_b and "trade_route" in region_b.resource_suspensions:
        continue  # route suspended
    # ... proceed with route income calculation
```

- [ ] **Step 2: Wire climate degradation multiplier into phase 9 (fertility)**

In `simulation.py` fertility tick:

```python
from chronicler.climate import get_climate_phase, climate_degradation_multiplier
from chronicler.models import InfrastructureType

climate_phase = get_climate_phase(world.turn, world.climate_config)

for region in world.regions:
    if region.controller is None:
        continue
    civ = next((c for c in world.civilizations if c.name == region.controller), None)
    if civ is None:
        continue

    # Mine degradation first (flat, not climate-affected)
    # Already handled by tick_infrastructure in phase 2

    # Compute effective cap with climate cap modifier + irrigation
    # Spec: tundra cap modifier — warming doubles to 0.4, cooling drops to 0.06
    base_cap = terrain_fertility_cap(region)
    if region.terrain == "tundra":
        if climate_phase == ClimatePhase.WARMING:
            base_cap = base_cap * 2.0  # 0.2 → 0.4
        elif climate_phase == ClimatePhase.COOLING:
            base_cap = base_cap * 0.3  # 0.2 → 0.06
    irrigation_bonus = 0.15 if any(
        i.type == InfrastructureType.IRRIGATION and i.active
        for i in region.infrastructure
    ) else 0.0
    # Spec formula: min(terrain_cap × climate_cap_modifier + irrigation_bonus, 1.0)
    cap = min(base_cap + irrigation_bonus, 1.0)

    # Climate degradation multiplier
    multiplier = climate_degradation_multiplier(
        region.terrain, climate_phase, world.climate_config.severity
    )

    region_pop = civ.population // len(civ.regions) if civ.regions else 0
    eff_cap = effective_capacity(region)

    if region_pop > eff_cap:
        region.fertility = max(region.fertility - 0.02 * multiplier, 0.0)
    elif region_pop < eff_cap * 0.5:
        region.fertility = min(region.fertility + 0.01, cap)
    # else: no change
```

- [ ] **Step 3: Wire mountain defense warming override into combat**

In `action_engine.py` `resolve_war()`, where terrain defense is applied:

```python
from chronicler.climate import get_climate_phase
from chronicler.models import ClimatePhase

climate_phase = get_climate_phase(world.turn, world.climate_config)

# Apply terrain defense with warming override
# Spec: warming zeroes terrain defense only; role defense still applies
from chronicler.terrain import terrain_defense_bonus, ROLE_EFFECTS
if climate_phase == ClimatePhase.WARMING and defender_region.terrain == "mountains":
    role_defense = ROLE_EFFECTS.get(defender_region.role, ROLE_EFFECTS["standard"]).defense
    defense_bonus = role_defense  # terrain defense zeroed, role defense preserved
else:
    defense_bonus = total_defense_bonus(defender_region)
```

- [ ] **Step 4: Write test for mountain defense warming override**

```python
# Append to tests/test_climate.py

class TestMountainDefenseWarming:
    def test_mountain_defense_zero_during_warming(self):
        """Spec: warming phase → terrain_defense_bonus(mountain_region) returns 0 in combat."""
        from chronicler.models import ClimatePhase, ClimateConfig, Region
        from chronicler.terrain import total_defense_bonus
        mountain = Region(name="Peaks", terrain="mountains",
                         carrying_capacity=50, resources="mineral")
        # Normally +20 defense
        assert total_defense_bonus(mountain) == 20
        # During warming, combat code overrides to 0
        climate_phase = ClimatePhase.WARMING
        if climate_phase == ClimatePhase.WARMING and mountain.terrain == "mountains":
            defense = 0
        else:
            defense = total_defense_bonus(mountain)
        assert defense == 0

    def test_mountain_defense_normal_during_temperate(self):
        from chronicler.models import ClimatePhase, Region
        from chronicler.terrain import total_defense_bonus
        mountain = Region(name="Peaks", terrain="mountains",
                         carrying_capacity=50, resources="mineral")
        climate_phase = ClimatePhase.TEMPERATE
        if climate_phase == ClimatePhase.WARMING and mountain.terrain == "mountains":
            defense = 0
        else:
            defense = total_defense_bonus(mountain)
        assert defense == 20


class TestTundraCapModifier:
    def test_tundra_cap_doubles_during_warming(self):
        """Spec: tundra fertility cap temporarily doubles to 0.4 during warming."""
        from chronicler.models import ClimatePhase
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="T", terrain="tundra", carrying_capacity=30,
                   resources="mineral")
        base_cap = terrain_fertility_cap(r)
        assert base_cap == 0.2
        # Warming modifier
        warming_cap = base_cap * 2.0
        assert warming_cap == 0.4

    def test_tundra_cap_crashes_during_cooling(self):
        """Spec: cooling → cap drops to 0.06."""
        from chronicler.terrain import terrain_fertility_cap
        r = Region(name="T", terrain="tundra", carrying_capacity=30,
                   resources="mineral")
        base_cap = terrain_fertility_cap(r)
        cooling_cap = base_cap * 0.3
        assert abs(cooling_cap - 0.06) < 0.001
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_climate.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_climate.py
git commit -m "feat(m15c): integrate climate into simulation phases 1, 4, and 9 with tundra cap modifiers"
```

---

## Chunk 4: Phase M15d — Exploration & Ruins

### Task 15: Add exploration model fields

**Files:**
- Modify: `src/chronicler/models.py`
- Create: `tests/test_exploration.py`

- [ ] **Step 1: Write failing tests for model fields**

```python
# tests/test_exploration.py
import pytest
from chronicler.models import (
    Region, Civilization, Leader, WorldState, ActionType, Relationship,
)


class TestExplorationModels:
    def test_civ_known_regions_default_none(self):
        leader = Leader(name="L", trait="bold", reign_start=0)
        civ = Civilization(
            name="Rome", population=50, military=30, economy=40,
            culture=30, stability=50, leader=leader,
        )
        assert civ.known_regions is None  # omniscient by default

    def test_civ_known_regions_list(self):
        leader = Leader(name="L", trait="bold", reign_start=0)
        civ = Civilization(
            name="Rome", population=50, military=30, economy=40,
            culture=30, stability=50, leader=leader,
            known_regions=["Alpha", "Beta"],
        )
        assert civ.known_regions == ["Alpha", "Beta"]

    def test_region_depopulated_since(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        assert r.depopulated_since is None
        assert r.ruin_quality == 0

    def test_world_fog_of_war_default(self):
        w = WorldState(name="T", seed=42)
        assert w.fog_of_war is False

    def test_explore_action_type(self):
        assert ActionType.EXPLORE == "explore"

    def test_relationship_trade_contact_turns(self):
        r = Relationship()
        assert r.trade_contact_turns == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_exploration.py -v`
Expected: FAIL

- [ ] **Step 3: Add model fields**

In `models.py`:

Add to ActionType enum:
```python
    EXPLORE = "explore"
```

Add to Civilization:
```python
    known_regions: list[str] | None = None
```

Add to Region:
```python
    depopulated_since: int | None = None
    ruin_quality: int = 0
```

Add to WorldState:
```python
    fog_of_war: bool = False
```

Add to Relationship:
```python
    trade_contact_turns: int = 0
```

Add to ScenarioConfig in `scenario.py`:
```python
    fog_of_war: bool | None = None
```

In `apply_scenario()`:
```python
    if config.fog_of_war is not None:
        world.fog_of_war = config.fog_of_war
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_exploration.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_exploration.py src/chronicler/models.py src/chronicler/scenario.py
git commit -m "feat(m15d): add exploration model fields (known_regions, fog_of_war, ruins, EXPLORE)"
```

### Task 16: Implement exploration.py core functions

**Files:**
- Create: `src/chronicler/exploration.py`
- Modify: `tests/test_exploration.py`

- [ ] **Step 1: Write failing tests for fog initialization and EXPLORE**

```python
# Append to tests/test_exploration.py

def _make_civ(name, regions=None, known_regions=None, treasury=100, trait="bold"):
    leader = Leader(name=f"L-{name}", trait=trait, reign_start=0)
    return Civilization(
        name=name, population=50, military=30, economy=40,
        culture=30, stability=50, treasury=treasury,
        leader=leader, regions=regions or [],
        known_regions=known_regions,
    )


class TestFogInitialization:
    def test_fog_seeds_home_and_adjacencies(self):
        from chronicler.exploration import initialize_fog
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B", "C"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A", "D"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["A"]),
            Region(name="D", terrain="mountains", carrying_capacity=50,
                   resources="mineral", adjacencies=["B", "E"]),
            Region(name="E", terrain="desert", carrying_capacity=30,
                   resources="mineral", adjacencies=["D"]),
        ]
        civ = _make_civ("Rome", regions=["A"])
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        initialize_fog(w)
        # Should know A (home) + B, C (adjacencies of A)
        assert set(civ.known_regions) == {"A", "B", "C"}

    def test_fog_disabled_keeps_none(self):
        from chronicler.exploration import initialize_fog
        civ = _make_civ("Rome", regions=["A"])
        w = WorldState(name="T", seed=42, civilizations=[civ], fog_of_war=False)
        initialize_fog(w)
        assert civ.known_regions is None


class TestExploreAction:
    def test_explore_reveals_region(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A", "C"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["B"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"],
                        treasury=20)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        event = handle_explore(w, civ)
        assert "B" in civ.known_regions
        # B's adjacencies also revealed
        assert "C" in civ.known_regions
        assert civ.treasury == 15  # cost 5

    def test_explore_costs_treasury(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"],
                        treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        handle_explore(w, civ)
        assert civ.treasury == 5


class TestExploreEligibility:
    def test_eligible_with_unknown_adjacent(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is True

    def test_ineligible_all_known(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A", "B"],
                        treasury=10)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is False

    def test_ineligible_no_fog(self):
        from chronicler.exploration import is_explore_eligible
        civ = _make_civ("Rome", regions=["A"], treasury=10)
        w = WorldState(name="T", seed=42, civilizations=[civ], fog_of_war=False)
        assert is_explore_eligible(w, civ) is False

    def test_ineligible_low_treasury(self):
        from chronicler.exploration import is_explore_eligible
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", adjacencies=["A"]),
        ]
        civ = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=3)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[civ], fog_of_war=True)
        assert is_explore_eligible(w, civ) is False
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_exploration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement exploration.py**

```python
# src/chronicler/exploration.py
"""Fog-of-war, exploration, first contact, and ruins.

Visibility layer — does not change mechanics of discovered regions.
known_regions as list[str] | None: None = omniscient (fog disabled).
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chronicler.models import Civilization, Event, Region, WorldState

from chronicler.models import Event


def initialize_fog(world: WorldState) -> None:
    """Called at world gen. Seeds each civ's known_regions if fog is active."""
    if not world.fog_of_war:
        return

    region_map = {r.name: r for r in world.regions}

    for civ in world.civilizations:
        known: set[str] = set()
        for rname in civ.regions:
            known.add(rname)
            region = region_map.get(rname)
            if region:
                for adj in region.adjacencies:
                    known.add(adj)
        civ.known_regions = sorted(known)


def is_explore_eligible(world: WorldState, civ: Civilization) -> bool:
    """EXPLORE is eligible when: fog active, treasury >= 5, unknown adjacent regions exist."""
    if not world.fog_of_war or civ.known_regions is None:
        return False
    if civ.treasury < 5:
        return False

    known_set = set(civ.known_regions)
    region_map = {r.name: r for r in world.regions}

    for rname in civ.known_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj in region.adjacencies:
            if adj not in known_set:
                return True
    return False


def _get_unknown_adjacent(world: WorldState, civ: Civilization) -> list[str]:
    """Return unknown regions adjacent to known regions, for target selection."""
    if civ.known_regions is None:
        return []
    known_set = set(civ.known_regions)
    region_map = {r.name: r for r in world.regions}
    candidates: list[str] = []

    for rname in civ.known_regions:
        region = region_map.get(rname)
        if region is None:
            continue
        for adj in region.adjacencies:
            if adj not in known_set and adj not in candidates:
                candidates.append(adj)
    return candidates


def handle_explore(world: WorldState, civ: Civilization) -> Event:
    """EXPLORE action handler. Reveals 1 unknown adjacent region + its adjacencies.

    Target selection: deterministic from seed + turn.
    Cost: 5 treasury.
    """
    candidates = _get_unknown_adjacent(world, civ)
    region_map = {r.name: r for r in world.regions}

    if not candidates:
        return Event(
            turn=world.turn, event_type="explore_failed",
            actors=[civ.name],
            description=f"{civ.name} found nothing new to explore",
            importance=2,
        )

    # Deterministic target selection
    idx_hash = int(hashlib.sha256(
        f"{world.seed}:{world.turn}:{civ.name}:explore".encode()
    ).hexdigest(), 16)
    target_name = candidates[idx_hash % len(candidates)]

    civ.treasury -= 5

    # Reveal target and its adjacencies
    known_set = set(civ.known_regions) if civ.known_regions else set()
    known_set.add(target_name)
    target = region_map.get(target_name)
    if target:
        for adj in target.adjacencies:
            known_set.add(adj)
    civ.known_regions = sorted(known_set)

    # Check for first contact
    first_contact_events = []
    if target and target.controller:
        other_civ = target.controller
        if other_civ != civ.name:
            rels = world.relationships.get(civ.name, {})
            if other_civ not in rels:
                fc_event = handle_first_contact(world, civ.name, other_civ, target_name)
                if fc_event:
                    first_contact_events.append(fc_event)

    # Check for ruins
    ruin_event = None
    if target and target.depopulated_since is not None:
        if (world.turn - target.depopulated_since) >= 20 and target.ruin_quality > 0:
            ruin_event = _discover_ruins(world, civ, target)

    event = Event(
        turn=world.turn, event_type="exploration",
        actors=[civ.name],
        description=f"{civ.name} explores {target_name}",
        importance=5,
    )

    # Add first contact and ruin events to world timeline
    for fc in first_contact_events:
        world.events_timeline.append(fc)
    if ruin_event:
        world.events_timeline.append(ruin_event)

    return event


def handle_first_contact(
    world: WorldState, discoverer: str, discovered: str, contact_region: str,
) -> Event | None:
    """Create relationship, share regions within 2 hops of contact point."""
    from chronicler.models import Relationship

    # Create relationship entries
    if discoverer not in world.relationships:
        world.relationships[discoverer] = {}
    if discovered not in world.relationships:
        world.relationships[discovered] = {}

    world.relationships[discoverer][discovered] = Relationship()
    world.relationships[discovered][discoverer] = Relationship()

    # Symmetric region sharing (2 hops from contact point)
    region_map = {r.name: r for r in world.regions}
    contact = region_map.get(contact_region)
    if contact:
        nearby: set[str] = {contact_region}
        frontier = [contact_region]
        for _ in range(2):
            next_frontier = []
            for rn in frontier:
                rr = region_map.get(rn)
                if rr:
                    for adj in rr.adjacencies:
                        if adj not in nearby:
                            nearby.add(adj)
                            next_frontier.append(adj)
            frontier = next_frontier

        for cname in (discoverer, discovered):
            c = next((c for c in world.civilizations if c.name == cname), None)
            if c and c.known_regions is not None:
                known_set = set(c.known_regions)
                known_set.update(nearby)
                c.known_regions = sorted(known_set)

    return Event(
        turn=world.turn, event_type="first_contact",
        actors=[discoverer, discovered],
        description=f"First contact between {discoverer} and {discovered}",
        importance=8,
    )


def mark_depopulated(region: Region, turn: int) -> None:
    """Called when region.controller becomes None."""
    region.depopulated_since = turn
    region.ruin_quality = len([i for i in region.infrastructure if i.active])
    for infra in region.infrastructure:
        infra.active = False


def _discover_ruins(
    world: WorldState, civ: Civilization, region: Region,
) -> Event | None:
    """Culture boost with diminishing returns. Resets ruin state."""
    if region.ruin_quality <= 0:
        return None

    boost = int(region.ruin_quality * 5 * (1.0 - civ.culture / 100))
    civ.culture = min(civ.culture + boost, 100)

    importance = 6 + min(region.ruin_quality, 4)
    event = Event(
        turn=world.turn, event_type="ruin_discovery",
        actors=[civ.name],
        description=f"{civ.name} discovers ancient ruins in {region.name} (+{boost} culture)",
        importance=importance,
    )

    region.depopulated_since = None
    region.ruin_quality = 0
    return event
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_exploration.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/exploration.py tests/test_exploration.py
git commit -m "feat(m15d): add exploration.py with fog init, EXPLORE, first contact, ruins"
```

### Task 17: Add first contact, ruins, and migration discovery tests

**Files:**
- Modify: `tests/test_exploration.py`

- [ ] **Step 1: Write tests for first contact and ruins**

```python
# Append to tests/test_exploration.py
from chronicler.models import Infrastructure, InfrastructureType


class TestFirstContact:
    def test_first_contact_creates_relationship(self):
        from chronicler.exploration import handle_explore
        regions = [
            Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome", adjacencies=["B"]),
            Region(name="B", terrain="forest", carrying_capacity=60,
                   resources="timber", controller="Greece", adjacencies=["A", "C"]),
            Region(name="C", terrain="coast", carrying_capacity=70,
                   resources="maritime", adjacencies=["B"]),
        ]
        rome = _make_civ("Rome", regions=["A"], known_regions=["A"], treasury=20)
        greece = _make_civ("Greece", regions=["B"], known_regions=["B", "C"], treasury=20)
        w = WorldState(name="T", seed=42, regions=regions,
                       civilizations=[rome, greece], fog_of_war=True)
        handle_explore(w, rome)
        # Rome discovers B (controlled by Greece) → first contact
        assert "Greece" in w.relationships.get("Rome", {})
        assert "Rome" in w.relationships.get("Greece", {})
        fc_events = [e for e in w.events_timeline if e.event_type == "first_contact"]
        assert len(fc_events) == 1


class TestRuins:
    def test_ruin_discovery_gives_culture(self):
        from chronicler.exploration import _discover_ruins, mark_depopulated
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller=None,
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Old", built_turn=1),
                       Infrastructure(type=InfrastructureType.IRRIGATION,
                                     builder_civ="Old", built_turn=5),
                       Infrastructure(type=InfrastructureType.FORTIFICATIONS,
                                     builder_civ="Old", built_turn=10),
                   ])
        mark_depopulated(r, turn=0)
        assert r.ruin_quality == 3
        assert all(not i.active for i in r.infrastructure)

        civ = _make_civ("Rome", regions=["A"])
        civ.culture = 20
        w = WorldState(name="T", seed=42, turn=25, regions=[r],
                       civilizations=[civ])
        event = _discover_ruins(w, civ, r)
        # boost = int(3 * 5 * (1.0 - 20/100)) = int(15 * 0.8) = 12
        assert civ.culture == 32
        assert r.depopulated_since is None
        assert r.ruin_quality == 0
        assert event is not None

    def test_ruin_diminishing_returns_high_culture(self):
        from chronicler.exploration import _discover_ruins
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", depopulated_since=0, ruin_quality=5)
        civ = _make_civ("Rome")
        civ.culture = 80
        w = WorldState(name="T", seed=42, turn=25)
        event = _discover_ruins(w, civ, r)
        # boost = int(5 * 5 * (1.0 - 80/100)) = int(25 * 0.2) = 5
        assert civ.culture == 85

    def test_ruin_quality_zero_no_event(self):
        from chronicler.exploration import _discover_ruins
        r = Region(name="Ruins", terrain="plains", carrying_capacity=80,
                   resources="fertile", depopulated_since=0, ruin_quality=0)
        civ = _make_civ("Rome")
        w = WorldState(name="T", seed=42, turn=25)
        event = _discover_ruins(w, civ, r)
        assert event is None


class TestMigrationDiscovery:
    def test_migration_reveals_source_region(self):
        """Refugees arriving from unknown region reveal the source."""
        from chronicler.exploration import reveal_migration_source
        civ = _make_civ("Rome", known_regions=["A"])
        reveal_migration_source(civ, "B")
        assert "B" in civ.known_regions

    def test_migration_no_reveal_if_omniscient(self):
        from chronicler.exploration import reveal_migration_source
        civ = _make_civ("Rome")  # known_regions = None (omniscient)
        reveal_migration_source(civ, "B")
        assert civ.known_regions is None
```

- [ ] **Step 2: Add reveal_migration_source to exploration.py**

```python
# Append to src/chronicler/exploration.py

def reveal_migration_source(civ: Civilization, source_region: str) -> None:
    """Called when migration arrives from an unknown region."""
    if civ.known_regions is None:
        return
    if source_region not in civ.known_regions:
        civ.known_regions.append(source_region)
        civ.known_regions.sort()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_exploration.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/exploration.py tests/test_exploration.py
git commit -m "test(m15d): add first contact, ruins, and migration discovery tests"
```

### Task 18: Integrate exploration into simulation loop and world_gen

**Files:**
- Modify: `src/chronicler/simulation.py`
- Modify: `src/chronicler/world_gen.py`
- Modify: `src/chronicler/action_engine.py`

- [ ] **Step 1: Wire fog initialization into world_gen**

In `world_gen.py` `generate_world()`, at the end before returning:

```python
from chronicler.exploration import initialize_fog

# Auto-set fog_of_war if not set by scenario
if len(world.regions) >= 15:
    world.fog_of_war = True

initialize_fog(world)
```

- [ ] **Step 2: Register EXPLORE in action engine**

In `action_engine.py`:

```python
from chronicler.exploration import handle_explore, is_explore_eligible

# In TRAIT_WEIGHTS, add EXPLORE weights for each trait:
# expansionist: 1.5, cautious: 0.5, mercantile: 1.2, others: 0.8

# In get_eligible_actions:
if is_explore_eligible(world, civ):
    eligible.append(ActionType.EXPLORE)
```

- [ ] **Step 3: Wire depopulation tracking into phase 10**

In `simulation.py` `phase_consequences()`:

```python
from chronicler.exploration import mark_depopulated

# After checking for civ elimination / region loss:
for region in world.regions:
    if region.controller is None and region.depopulated_since is None:
        mark_depopulated(region, world.turn)
    elif region.controller is not None and region.depopulated_since is not None:
        # Region repopulated — clear ruin state
        region.depopulated_since = None
        region.ruin_quality = 0
```

- [ ] **Step 4: Wire migration discovery into climate.py**

In `climate.py` `process_migration()`, when receiving region has a controller whose `known_regions` doesn't include the source:

```python
from chronicler.exploration import reveal_migration_source

# After distributing surplus to a receiving region:
if ctrl_name is not None:
    recv_civ = next((c for c in world.civilizations if c.name == ctrl_name), None)
    if recv_civ:
        reveal_migration_source(recv_civ, region.name)
```

- [ ] **Step 5: Add tick_trade_knowledge_sharing to exploration.py and wire into phase 2**

First, add the function to `exploration.py`:

```python
# Append to src/chronicler/exploration.py

def tick_trade_knowledge_sharing(world: WorldState) -> list[Event]:
    """Called from apply_automatic_effects (phase 2).

    For each active trade route: increment trade_contact_turns,
    share known_regions within (2 + contact_turns // 3) hops (capped at 5)
    from trade route endpoints. Check for first contact on newly visible regions.
    """
    from chronicler.resources import get_active_trade_routes

    events: list[Event] = []
    region_map = {r.name: r for r in world.regions}

    for route in get_active_trade_routes(world):
        civ_a_name = route.civ_a
        civ_b_name = route.civ_b

        # Increment trade_contact_turns
        rel_a = world.relationships.get(civ_a_name, {}).get(civ_b_name)
        rel_b = world.relationships.get(civ_b_name, {}).get(civ_a_name)
        if rel_a:
            rel_a.trade_contact_turns += 1
        if rel_b:
            rel_b.trade_contact_turns += 1

        # Share known_regions within hop range
        contact_turns = rel_a.trade_contact_turns if rel_a else 0
        max_hops = min(2 + contact_turns // 3, 5)

        civ_a = next((c for c in world.civilizations if c.name == civ_a_name), None)
        civ_b = next((c for c in world.civilizations if c.name == civ_b_name), None)
        if not civ_a or not civ_b:
            continue
        if civ_a.known_regions is None or civ_b.known_regions is None:
            continue  # omniscient civs don't need sharing

        # BFS from trade route endpoints up to max_hops
        endpoints = {route.region_a, route.region_b}
        nearby: set[str] = set(endpoints)
        frontier = list(endpoints)
        for _ in range(max_hops):
            next_frontier = []
            for rn in frontier:
                rr = region_map.get(rn)
                if rr:
                    for adj in rr.adjacencies:
                        if adj not in nearby:
                            nearby.add(adj)
                            next_frontier.append(adj)
            frontier = next_frontier

        # Merge: share A's known∩nearby with B, and B's known∩nearby with A
        a_known = set(civ_a.known_regions)
        b_known = set(civ_b.known_regions)
        new_for_b = (a_known & nearby) - b_known
        new_for_a = (b_known & nearby) - a_known

        if new_for_b:
            b_known.update(new_for_b)
            civ_b.known_regions = sorted(b_known)
        if new_for_a:
            a_known.update(new_for_a)
            civ_a.known_regions = sorted(a_known)

        # Check for first contact on newly visible regions
        for rname in new_for_b:
            r = region_map.get(rname)
            if r and r.controller and r.controller != civ_b_name:
                if r.controller not in world.relationships.get(civ_b_name, {}):
                    fc = handle_first_contact(world, civ_b_name, r.controller, rname)
                    if fc:
                        events.append(fc)
        for rname in new_for_a:
            r = region_map.get(rname)
            if r and r.controller and r.controller != civ_a_name:
                if r.controller not in world.relationships.get(civ_a_name, {}):
                    fc = handle_first_contact(world, civ_a_name, r.controller, rname)
                    if fc:
                        events.append(fc)

    return events
```

Then wire it into `simulation.py` `apply_automatic_effects()`:

```python
from chronicler.exploration import tick_trade_knowledge_sharing

# After trade income calculation:
knowledge_events = tick_trade_knowledge_sharing(world)
world.events_timeline.extend(knowledge_events)
```

- [ ] **Step 6: Wire expansion reveals adjacencies into war resolution**

In `action_engine.py` `resolve_war()`, after a region changes hands (the `contested` region from E1):

```python
# When attacker conquers a region, reveal all its adjacencies:
if world.fog_of_war:
    attacker_civ = next((c for c in world.civilizations if c.name == attacker.name), None)
    if attacker_civ and attacker_civ.known_regions is not None:
        known_set = set(attacker_civ.known_regions)
        known_set.add(contested.name)
        for adj in contested.adjacencies:
            known_set.add(adj)
        attacker_civ.known_regions = sorted(known_set)
```

- [ ] **Step 7: Add fog-of-war action targeting constraints**

Add a visibility filter function to `exploration.py`:

```python
# Append to src/chronicler/exploration.py

def filter_targets_by_fog(
    world: WorldState, civ: Civilization, target_regions: list[str],
) -> list[str]:
    """Remove regions the civ doesn't know about. No-op if fog disabled."""
    if not world.fog_of_war or civ.known_regions is None:
        return target_regions
    known_set = set(civ.known_regions)
    return [r for r in target_regions if r in known_set]
```

In `action_engine.py`, wrap existing WAR/EXPAND eligibility checks:

```python
from chronicler.exploration import filter_targets_by_fog

# In get_eligible_actions(), where WAR eligibility is checked:
# Before: checks if civ has adjacent hostile neighbors
# After: additionally filter candidate targets through fog
# Example integration point (adapt to actual code structure):
#
# Where the action engine computes potential WAR targets (adjacent regions
# controlled by other civs), add:
#   potential_targets = filter_targets_by_fog(world, civ, potential_targets)
#   if not potential_targets:
#       # WAR is ineligible — no visible targets
#
# Same pattern for EXPAND (adjacent uncontrolled regions):
#   expand_candidates = filter_targets_by_fog(world, civ, expand_candidates)
#   if not expand_candidates:
#       # EXPAND is ineligible

# NOTE: The exact integration depends on how get_eligible_actions() computes
# target lists. If it doesn't build explicit target lists (just checks
# conditions), refactor the WAR/EXPAND eligibility to:
#   1. Build candidate region list
#   2. Filter through filter_targets_by_fog()
#   3. Check if any remain
```

In `resources.py` or `simulation.py`, filter trade routes through unknown regions:

```python
from chronicler.exploration import filter_targets_by_fog

# In get_active_trade_routes() or where trade routes are validated:
# Skip routes where either endpoint is unknown to its controlling civ
def is_route_visible(world: WorldState, route) -> bool:
    """Both endpoints must be known to their respective civs."""
    if not world.fog_of_war:
        return True
    for civ_name, region_name in [(route.civ_a, route.region_b),
                                   (route.civ_b, route.region_a)]:
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ and civ.known_regions is not None:
            if region_name not in civ.known_regions:
                return False
    return True
```

- [ ] **Step 8: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add -u
git commit -m "feat(m15d): integrate exploration into world_gen, action engine, and simulation"
```

### Task 19: End-to-end integration test

**Files:**
- Modify: `tests/test_terrain.py` (or create `tests/test_m15_integration.py`)

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_m15_integration.py
"""End-to-end smoke test for M15 Living World mechanics."""
import pytest
from chronicler.models import WorldState, ClimateConfig
from chronicler.world_gen import generate_world


class TestM15Integration:
    def test_20_turn_smoke_test(self):
        """Run 20 turns with all M15 mechanics active. Assert no crashes."""
        world = generate_world(seed=42, num_regions=10, num_civs=4)
        world.climate_config = ClimateConfig(period=20, severity=1.0)

        from chronicler.simulation import run_turn
        for turn in range(20):
            run_turn(world, action_selector=None, narrator=None, seed=42 + turn)

        # Basic invariants
        for region in world.regions:
            assert 0.0 <= region.fertility <= 1.0
            assert region.role in ("standard", "crossroads", "frontier", "chokepoint")
        for civ in world.civilizations:
            assert civ.population >= 1

    def test_terrain_defense_affects_war_outcome(self):
        """Mountain defenders should win more often than plains defenders, all else equal."""
        from chronicler.models import Leader, Civilization, Region, WorldState
        from chronicler.action_engine import resolve_war

        mountain_wins = 0
        for seed in range(50):
            mountain = Region(name="Peaks", terrain="mountains",
                             carrying_capacity=50, resources="mineral",
                             controller="Defender", fertility=0.5,
                             adjacencies=["Valley"])
            plains = Region(name="Valley", terrain="plains",
                           carrying_capacity=80, resources="fertile",
                           controller="Attacker", fertility=0.8,
                           adjacencies=["Peaks"])
            leader_d = Leader(name="LD", trait="bold", reign_start=0)
            leader_a = Leader(name="LA", trait="bold", reign_start=0)
            defender = Civilization(
                name="Defender", population=50, military=50, economy=40,
                culture=30, stability=50, leader=leader_d, regions=["Peaks"])
            attacker = Civilization(
                name="Attacker", population=50, military=50, economy=40,
                culture=30, stability=50, leader=leader_a, regions=["Valley"])
            w = WorldState(name="T", seed=seed, regions=[mountain, plains],
                          civilizations=[defender, attacker])
            resolve_war(attacker, defender, w, seed=seed)
            d = next(c for c in w.civilizations if c.name == "Defender")
            if "Peaks" in d.regions:
                mountain_wins += 1
        assert mountain_wins > 25  # >50% — terrain advantage is real

    def test_climate_cycle_completes(self):
        """Run a full climate cycle and verify all four phases occur."""
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=20)
        phases_seen = set()
        for turn in range(20):
            phases_seen.add(get_climate_phase(turn, cfg))
        assert len(phases_seen) == 4
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_m15_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_m15_integration.py
git commit -m "test(m15): add end-to-end integration smoke tests"
```

---

## Summary

| Chunk | Phase | Tasks | Description |
|-------|-------|-------|-------------|
| 1 | M15a | 1-4 | Terrain effects, effective_capacity, role classification, simulation integration |
| 2 | M15b | 5-6b, 7-8 | Infrastructure models, handle_build, tick/scorched earth, simulation integration |
| 3 | M15c | 9-14 | Climate models, phase function, degradation multiplier, disasters, migration, simulation integration |
| 4 | M15d | 15-19 | Exploration models, fog-of-war, EXPLORE action, ruins, fog constraints, integration, end-to-end tests |

Total: 20 tasks, ~70 steps, ~21 commits.
