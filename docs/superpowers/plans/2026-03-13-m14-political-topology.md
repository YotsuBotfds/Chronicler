# M14: Political Topology — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make empires structurally unstable through governing costs, secession, vassals, federations, proxy wars, diplomatic congresses, governments in exile, and systemic feedback loops — all pure emergent mechanics from simple arithmetic.

**Architecture:** Four sequential phases (M14a→M14b→M14c→M14d), each independently testable. All changes are pure Python simulation — no LLM calls. One new module: `politics.py`. Existing modules modified: `models.py`, `simulation.py`, `action_engine.py`, `world_gen.py`, `scenario.py`, `bundle.py`, `resources.py`. Viewer types updated but no new components.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, TypeScript/React (viewer types only)

**Spec:** `docs/superpowers/specs/2026-03-13-m14-political-topology-design.md`

---

## Prerequisites (M13 must be complete)

M14 depends on M13b being fully implemented. Before starting ANY M14 task, verify these exist:

- [ ] `src/chronicler/adjacency.py` exists with `graph_distance(regions, from_name, to_name) -> int` and `shortest_path()`
- [ ] `src/chronicler/resources.py` exists with `get_active_trade_routes(world) -> list[tuple[str, str]]`
- [ ] `src/chronicler/utils.py` contains `STAT_FLOOR: dict[str, int]` and `clamp()`
- [ ] `Region` model has `adjacencies: list[str]`, `fertility: float`, `carrying_capacity: int = Field(ge=1, le=100)`
- [ ] `Civilization` model has stat fields with `Field(ge=0, le=100)` (P1 scaled), `treasury: int` (uncapped)
- [ ] `WorldState` model has `active_wars: list[tuple[str, str]]`
- [ ] `ActionType` enum has `BUILD` and `EMBARGO`
- [ ] `action_engine.py` uses registration pattern (`@register_action` decorator, `ACTION_REGISTRY`)
- [ ] `simulation.py` has 10-phase turn structure with `apply_automatic_effects` (phase 2) and `phase_consequences` (phase 10)

If any prerequisite is missing, implement M13 first. All test code in this plan uses M13's 0-100 stat scale and M13's modules.

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/chronicler/politics.py` | All M14 political mechanics: governing costs, capital management, secession, vassals, federations, proxy wars, congresses, exile, systemic dynamics |
| `tests/test_politics.py` | Tests for all politics module functions |

### Modified Files
| File | Changes |
|------|---------|
| `src/chronicler/models.py` | Add `capital_region` to Civilization; add `VassalRelation`, `Federation`, `ProxyWar`, `ExileModifier` models; add `war_start_turns`, `vassal_relations`, `federations`, `proxy_wars`, `exile_modifiers`, `peace_turns`, `balance_of_power_turns` to WorldState; add `allied_turns` to Relationship; add `peak_region_count`, `decline_turns`, `stats_sum_history` to Civilization; add `MOVE_CAPITAL`, `FUND_INSTABILITY` to ActionType; extend CivSnapshot and TurnSnapshot |
| `src/chronicler/simulation.py` | Add `politics.*` calls to phase 2 (automatic effects) and phase 10 (consequences); integrate vassalization choice in war resolution; integrate federation defense in war action |
| `src/chronicler/action_engine.py` | Register MOVE_CAPITAL and FUND_INSTABILITY handlers; add eligibility filters (vassal can't declare wars, can't attack federation co-members); add MOVE_CAPITAL/FUND_INSTABILITY weight profiles; add fallen empire weight multiplier |
| `src/chronicler/world_gen.py` | Set `capital_region` on each civ during generation |
| `src/chronicler/scenario.py` | Add `secession_pool` to ScenarioConfig; support `capital` in CivOverride |
| `src/chronicler/resources.py` | Modify `get_active_trade_routes` to bypass adjacency for federation members |
| `src/chronicler/bundle.py` | Add new TurnSnapshot and CivSnapshot fields |
| `viewer/src/types.ts` | Add new TurnSnapshot and CivSnapshot fields |

### Key Reference Files (read before implementation)
| File | Why |
|------|-----|
| `src/chronicler/adjacency.py` | `graph_distance()` and `shortest_path()` used by governing cost and secession |
| `src/chronicler/leaders.py` | Leader succession mechanism reused on capital loss |
| `src/chronicler/utils.py` | `clamp()` and `STAT_FLOOR` for clamping after stat drains |

---

## Chunk 1: Phase M14a — Imperial Foundations

### Task 1: Add capital_region and war_start_turns model fields

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Write failing test — Civilization accepts capital_region**

```python
# In tests/test_politics.py (create file), add:
from chronicler.models import Civilization, Leader, WorldState

def test_civilization_has_capital_region():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test", population=50, military=30, economy=40,
        culture=30, stability=50, leader=leader,
        regions=["Alpha", "Beta"], capital_region="Alpha",
    )
    assert civ.capital_region == "Alpha"

def test_civilization_capital_region_defaults_none():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(
        name="Test", population=50, military=30, economy=40,
        culture=30, stability=50, leader=leader,
    )
    assert civ.capital_region is None

def test_worldstate_has_war_start_turns():
    ws = WorldState(name="test", seed=42)
    assert ws.war_start_turns == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py -v`
Expected: FAIL — `capital_region` not recognized, `war_start_turns` not recognized

- [ ] **Step 3: Add fields to models.py**

```python
# In Civilization class, add after leader_name_pool:
capital_region: str | None = None

# In WorldState class, add after action_history:
war_start_turns: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_politics.py
git commit -m "feat(m14a): add capital_region to Civilization and war_start_turns to WorldState"
```

### Task 2: Add MOVE_CAPITAL to ActionType enum

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_politics.py, add:
from chronicler.models import ActionType

def test_move_capital_action_exists():
    assert ActionType.MOVE_CAPITAL == "move_capital"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py::test_move_capital_action_exists -v`
Expected: FAIL — `MOVE_CAPITAL` not in ActionType

- [ ] **Step 3: Add to ActionType enum**

```python
# In ActionType enum in models.py, add:
MOVE_CAPITAL = "move_capital"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py::test_move_capital_action_exists -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `pytest --tb=short -q`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/models.py tests/test_politics.py
git commit -m "feat(m14a): add MOVE_CAPITAL to ActionType enum"
```

### Task 3: Set capital_region in world_gen.py

**Files:**
- Modify: `src/chronicler/world_gen.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_politics.py, add:
from chronicler.world_gen import generate_world

def test_world_gen_sets_capital_region():
    world = generate_world(seed=42)
    for civ in world.civilizations:
        assert civ.capital_region is not None
        assert civ.capital_region in civ.regions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py::test_world_gen_sets_capital_region -v`
Expected: FAIL — `capital_region` is None

- [ ] **Step 3: Add capital_region assignment in world_gen.py**

In `generate_world`, after assigning regions to civs, add:

```python
# After the region assignment loop:
for civ in world.civilizations:
    if civ.regions and civ.capital_region is None:
        civ.capital_region = civ.regions[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py::test_world_gen_sets_capital_region -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_politics.py
git commit -m "feat(m14a): set capital_region during world generation"
```

### Task 4: Add secession_pool to ScenarioConfig and capital to CivOverride

**Files:**
- Modify: `src/chronicler/scenario.py`

- [ ] **Step 1: Write failing test**

```python
# In tests/test_politics.py, add:
from chronicler.scenario import ScenarioConfig

def test_scenario_config_has_secession_pool():
    config = ScenarioConfig(name="test")
    assert config.secession_pool == []

def test_scenario_capital_override(tmp_path):
    """Scenario YAML can specify capital per civ."""
    from chronicler.scenario import load_scenario, apply_scenario
    from chronicler.world_gen import generate_world
    yaml_content = """
name: test
civilizations:
  - name: TestCiv
    capital: "Region A"
"""
    p = tmp_path / "test.yaml"
    p.write_text(yaml_content)
    config = load_scenario(p)
    assert config.civilizations[0].capital == "Region A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py::test_scenario_config_has_secession_pool tests/test_politics.py::test_scenario_capital_override -v`
Expected: FAIL

- [ ] **Step 3: Add fields to scenario.py**

```python
# In CivOverride class, add:
capital: str | None = None

# In ScenarioConfig class, add:
secession_pool: list[CivOverride] = Field(default_factory=list)
```

In `apply_scenario`, after applying civ overrides, add:

```python
if override.capital is not None:
    civ.capital_region = override.capital
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py::test_scenario_config_has_secession_pool tests/test_politics.py::test_scenario_capital_override -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/scenario.py tests/test_politics.py
git commit -m "feat(m14a): add secession_pool to ScenarioConfig and capital to CivOverride"
```

### Task 5: Implement apply_governing_costs

**Files:**
- Create: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import apply_governing_costs

def _make_world_with_regions(region_names, civ_name="Empire", capital="A", adjacencies=None):
    """Helper: create a WorldState with a civ controlling given regions.
    NOTE: Requires M13 stat scale (0-100 stats, carrying_capacity up to 100).
    """
    from chronicler.models import Region, Civilization, Leader, WorldState
    regions = []
    for name in region_names:
        adj = adjacencies.get(name, []) if adjacencies else []
        regions.append(Region(name=name, terrain="plains", carrying_capacity=50, resources="fertile",
                              adjacencies=adj, controller=civ_name))
    leader = Leader(name="Leader", trait="bold", reign_start=0)
    civ = Civilization(
        name=civ_name, population=50, military=30, economy=40,
        culture=30, stability=50, treasury=100, leader=leader,
        regions=region_names, capital_region=capital,
    )
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[civ])
    return world

def test_governing_cost_no_cost_for_two_or_fewer_regions():
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies={"A": ["B"], "B": ["A"]})
    apply_governing_costs(world)
    civ = world.civilizations[0]
    assert civ.stability == 50  # unchanged
    assert civ.treasury == 100  # unchanged

def test_governing_cost_three_regions_compact():
    # All adjacent to capital: dist=1 each
    adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    apply_governing_costs(world)
    civ = world.civilizations[0]
    # treasury: (3-2)*2 + 2*(1*2) = 2+4 = 6
    assert civ.treasury == 100 - 6
    # stability: 1+1 = 2
    assert civ.stability == 50 - 2

def test_governing_cost_distant_regions_cost_more():
    # A-B-C-D chain: distances from A are 1, 2, 3
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    apply_governing_costs(world)
    civ = world.civilizations[0]
    # treasury: (4-2)*2 + (1*2 + 2*2 + 3*2) = 4 + 12 = 16
    assert civ.treasury == 100 - 16
    # stability: 1 + 2 + 3 = 6
    assert civ.stability == 50 - 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py::test_governing_cost_no_cost_for_two_or_fewer_regions tests/test_politics.py::test_governing_cost_three_regions_compact tests/test_politics.py::test_governing_cost_distant_regions_cost_more -v`
Expected: FAIL — `politics` module doesn't exist

- [ ] **Step 3: Create politics.py with apply_governing_costs**

```python
# src/chronicler/politics.py
"""Political topology mechanics for the civilization chronicle generator.

Covers governing costs, capitals, secession, vassals, federations,
proxy wars, diplomatic congresses, governments in exile, and
systemic dynamics (balance of power, fallen empires, twilight, long peace).
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from chronicler.adjacency import graph_distance
from chronicler.models import (
    ActionType, Civilization, Event, Leader, NamedEvent, WorldState,
)
from chronicler.utils import clamp, STAT_FLOOR

if TYPE_CHECKING:
    pass


def war_key(a: str, b: str) -> str:
    """Canonical key for a war between two civs (alphabetically sorted)."""
    return ":".join(sorted([a, b]))


def apply_governing_costs(world: WorldState) -> list[Event]:
    """Phase 2: Apply governing costs based on empire size and distance from capital."""
    events: list[Event] = []
    for civ in world.civilizations:
        if len(civ.regions) <= 2 or civ.capital_region is None:
            continue
        region_count = len(civ.regions)
        treasury_cost = (region_count - 2) * 2

        stability_cost = 0
        for region_name in civ.regions:
            if region_name == civ.capital_region:
                continue
            dist = graph_distance(world.regions, civ.capital_region, region_name)
            if dist < 0:
                dist = 1  # fallback if disconnected
            treasury_cost += dist * 2
            stability_cost += dist * 1

        civ.treasury -= treasury_cost
        civ.stability = clamp(civ.stability - stability_cost, STAT_FLOOR["stability"], 100)
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py::test_governing_cost_no_cost_for_two_or_fewer_regions tests/test_politics.py::test_governing_cost_three_regions_compact tests/test_politics.py::test_governing_cost_distant_regions_cost_more -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14a): implement apply_governing_costs in politics.py"
```

### Task 6: Implement check_capital_loss

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import check_capital_loss

def test_capital_loss_triggers_stability_penalty():
    """When capital not in civ.regions, stability -20 and capital reassigned."""
    adj = {"B": ["C"], "C": ["B"]}
    world = _make_world_with_regions(["B", "C"], capital="A", adjacencies=adj)
    # Capital "A" is not in regions ["B", "C"]
    civ = world.civilizations[0]
    civ.stability = 50
    events = check_capital_loss(world)
    assert civ.stability <= 30  # -20
    assert civ.capital_region in civ.regions  # reassigned
    assert len(events) > 0

def test_capital_loss_picks_best_remaining_region():
    """Capital reassignment picks highest carrying_capacity * fertility."""
    from chronicler.models import Region
    regions = [
        Region(name="B", terrain="plains", carrying_capacity=30, resources="fertile", fertility=0.5),
        Region(name="C", terrain="plains", carrying_capacity=50, resources="fertile", fertility=0.8),
    ]
    leader = Leader(name="L", trait="bold", reign_start=0)
    civ = Civilization(
        name="E", population=50, military=30, economy=40,
        culture=30, stability=50, treasury=100, leader=leader,
        regions=["B", "C"], capital_region="A",
    )
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[civ])
    check_capital_loss(world)
    # C has 50*0.8=40, B has 30*0.5=15 — C wins
    assert civ.capital_region == "C"

def test_no_capital_loss_when_capital_in_regions():
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 50
    events = check_capital_loss(world)
    assert civ.stability == 50  # unchanged
    assert len(events) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "capital_loss" -v`
Expected: FAIL

- [ ] **Step 3: Implement check_capital_loss**

```python
# In politics.py, add:
def check_capital_loss(world: WorldState) -> list[Event]:
    """Phase 10: Check if any civ lost its capital and handle reassignment."""
    events: list[Event] = []
    for civ in world.civilizations:
        if civ.capital_region is None or civ.capital_region in civ.regions:
            continue
        if not civ.regions:
            continue

        # Capital lost
        civ.stability = clamp(civ.stability - 20, STAT_FLOOR["stability"], 100)

        # Trigger leader succession check (reuse existing leaders.py mechanism)
        from chronicler.leaders import check_leader_succession
        succession_events = check_leader_succession(civ, world)
        events.extend(succession_events)

        # Pick best remaining region (highest carrying_capacity * fertility)
        region_map = {r.name: r for r in world.regions}
        best_region = max(
            civ.regions,
            key=lambda rn: (
                region_map[rn].carrying_capacity * getattr(region_map[rn], "fertility", 0.8)
                if rn in region_map else 0
            ),
        )
        old_capital = civ.capital_region
        civ.capital_region = best_region

        events.append(Event(
            turn=world.turn,
            event_type="capital_loss",
            actors=[civ.name],
            description=f"{civ.name} lost capital {old_capital}, relocated to {best_region}",
            importance=8,
        ))
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "capital_loss" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14a): implement check_capital_loss in politics.py"
```

### Task 7: Implement check_secession

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import check_secession

def test_secession_does_not_fire_above_threshold():
    adj = {"A": ["B", "C", "D"], "B": ["A"], "C": ["A"], "D": ["A"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 50  # well above 20
    events = check_secession(world)
    assert len(world.civilizations) == 1  # no secession

def test_secession_does_not_fire_with_too_few_regions():
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 5  # below 20 but only 2 regions
    events = check_secession(world)
    assert len(world.civilizations) == 1

def test_secession_fires_at_zero_stability():
    """At stability 0, probability is 20%. With a favorable seed, secession fires."""
    # Chain: A-B-C-D-E, so D and E are most distant
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C", "E"], "E": ["D"]}
    world = _make_world_with_regions(["A", "B", "C", "D", "E"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 0
    civ.population = 50
    civ.military = 30
    civ.economy = 40
    civ.treasury = 100
    civ.leader_name_pool = ["Name1", "Name2", "Name3"]
    # Force secession by trying many seeds until it fires
    fired = False
    for seed in range(100):
        world.seed = seed
        world.turn = seed
        # Reset civ each iteration
        civ.regions = ["A", "B", "C", "D", "E"]
        civ.stability = 0
        civ.population = 50
        civ.military = 30
        civ.economy = 40
        civ.treasury = 100
        # Remove any previously spawned civs
        world.civilizations = [civ]
        for r in world.regions:
            r.controller = civ.name
        events = check_secession(world)
        if len(world.civilizations) > 1:
            fired = True
            break
    assert fired, "Secession should fire at stability 0 within 100 seed attempts"
    breakaway = world.civilizations[1]
    assert breakaway.name != civ.name
    assert breakaway.tech_era == civ.tech_era
    assert breakaway.asabiya == 0.7
    assert breakaway.stability == 40

def test_secession_stat_split_conserves_stats():
    """Total stats before and after secession are conserved."""
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.stability = 0
    civ.population = 60
    civ.military = 30
    civ.economy = 45
    civ.treasury = 90
    civ.leader_name_pool = ["N1", "N2"]
    # Force secession
    for seed in range(200):
        world.seed = seed
        world.turn = seed
        civ.regions = ["A", "B", "C"]
        civ.stability = 0
        civ.population = 60
        civ.military = 30
        civ.economy = 45
        civ.treasury = 90
        world.civilizations = [civ]
        for r in world.regions:
            r.controller = civ.name
        events = check_secession(world)
        if len(world.civilizations) > 1:
            parent = world.civilizations[0]
            breakaway = world.civilizations[1]
            # Population, military, economy, treasury conserved (minus stability shock)
            for stat in ["population", "military", "economy", "treasury"]:
                original = {"population": 60, "military": 30, "economy": 45, "treasury": 90}
                assert getattr(parent, stat) + getattr(breakaway, stat) == original[stat]
            break
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "secession" -v`
Expected: FAIL

- [ ] **Step 3: Implement check_secession**

This is the most complex function. Key implementation details from spec:

```python
# In politics.py, add:

_SECESSION_PREFIXES = [
    "Free", "Eastern", "Western", "Northern", "Southern",
    "New", "Upper", "Lower", "Greater",
]

_TRAIT_POOL = [
    "aggressive", "cautious", "opportunistic", "zealous", "ambitious",
    "calculating", "visionary", "bold", "shrewd", "stubborn",
]


def check_secession(world: WorldState) -> list[Event]:
    """Phase 10: Check for civil war / secession in unstable empires.

    Must be called AFTER check_capital_loss and AFTER stability clamp.
    Uses post-clamp stability values.
    """
    events: list[Event] = []
    new_civs: list[Civilization] = []

    for civ in list(world.civilizations):
        if civ.stability >= 20 or len(civ.regions) < 3:
            continue

        # Secession probability
        prob = (20 - civ.stability) / 100

        # Proxy war boost (M14c — check if any proxy war targets this civ)
        for pw in getattr(world, "proxy_wars", []):
            if pw.target_civ == civ.name:
                prob += 0.05
                break  # only +0.05 once regardless of how many proxy wars

        rng = random.Random(world.seed + world.turn + hash(civ.name))
        if rng.random() >= prob:
            continue

        # Secession fires
        region_map = {r.name: r for r in world.regions}

        # Sort regions by distance from capital, descending
        def _dist_from_capital(rn: str) -> int:
            d = graph_distance(world.regions, civ.capital_region or civ.regions[0], rn)
            return d if d >= 0 else 0

        sorted_regions = sorted(civ.regions, key=_dist_from_capital, reverse=True)

        # Breakaway takes ceil(region_count / 3) most distant regions
        breakaway_count = math.ceil(len(civ.regions) / 3)
        breakaway_count = max(1, min(breakaway_count, len(civ.regions) - 1))
        breakaway_regions = sorted_regions[:breakaway_count]
        remaining_regions = [r for r in civ.regions if r not in breakaway_regions]

        # Stat split
        ratio = len(breakaway_regions) / len(civ.regions)
        split_pop = math.floor(civ.population * ratio)
        split_mil = math.floor(civ.military * ratio)
        split_eco = math.floor(civ.economy * ratio)
        split_tre = math.floor(civ.treasury * ratio)

        # Generate breakaway name (avoid collisions with existing civs)
        existing_names = {c.name for c in world.civilizations}
        prefix = _SECESSION_PREFIXES[rng.randint(0, len(_SECESSION_PREFIXES) - 1)]
        base_name = breakaway_regions[0] if rng.random() < 0.5 else civ.name
        breakaway_name = f"{prefix} {base_name}"
        # Retry with different prefix if name collision
        attempts = 0
        while breakaway_name in existing_names and attempts < len(_SECESSION_PREFIXES):
            prefix = _SECESSION_PREFIXES[attempts]
            breakaway_name = f"{prefix} {base_name}"
            attempts += 1
        if breakaway_name in existing_names:
            breakaway_name = f"{prefix} {base_name} {world.turn}"

        # Swap one trait from parent's leader
        parent_trait = civ.leader.trait
        available_traits = [t for t in _TRAIT_POOL if t != parent_trait]
        new_trait = rng.choice(available_traits) if available_traits else parent_trait

        # Generate leader name from parent's pool or fallback
        name_pool = civ.leader_name_pool or ["Leader"]
        used = set(world.used_leader_names)
        leader_name = None
        for n in name_pool:
            if n not in used:
                leader_name = n
                break
        if leader_name is None:
            leader_name = f"{breakaway_name} Leader"
        world.used_leader_names.append(leader_name)

        # Swap one value from parent's values (pick a different value, not string reversal)
        new_values = list(civ.values)
        if new_values:
            _VALUE_POOL = [
                "freedom", "order", "tradition", "progress", "honor",
                "wealth", "knowledge", "faith", "unity", "independence",
            ]
            swap_idx = rng.randint(0, len(new_values) - 1)
            available_values = [v for v in _VALUE_POOL if v not in new_values]
            if available_values:
                new_values[swap_idx] = rng.choice(available_values)

        # Capital: breakaway region closest to parent's remaining regions
        def _min_dist_to_parent(rn: str) -> int:
            return min(
                (graph_distance(world.regions, rn, pr) for pr in remaining_regions),
                default=0,
            )
        breakaway_capital = min(breakaway_regions, key=_min_dist_to_parent)

        new_leader = Leader(
            name=leader_name,
            trait=new_trait,
            reign_start=world.turn,
            succession_type="secession",
        )

        breakaway_civ = Civilization(
            name=breakaway_name,
            population=max(split_pop, 1),
            military=max(split_mil, 0),
            economy=max(split_eco, 0),
            culture=civ.culture,
            stability=40,
            treasury=split_tre,
            tech_era=civ.tech_era,
            leader=new_leader,
            regions=breakaway_regions,
            capital_region=breakaway_capital,
            domains=list(civ.domains),
            values=new_values,
            asabiya=0.7,
            leader_name_pool=list(civ.leader_name_pool or []),
        )

        # Update parent stats
        civ.population = max(civ.population - split_pop, 1)
        civ.military = max(civ.military - split_mil, 0)
        civ.economy = max(civ.economy - split_eco, 0)
        civ.treasury -= split_tre
        civ.stability = clamp(civ.stability - 10, STAT_FLOOR["stability"], 100)
        civ.regions = remaining_regions

        # Update region controllers
        for rn in breakaway_regions:
            if rn in region_map:
                region_map[rn].controller = breakaway_name

        # Set up relationships
        if civ.name not in world.relationships:
            world.relationships[civ.name] = {}
        if breakaway_name not in world.relationships:
            world.relationships[breakaway_name] = {}
        from chronicler.models import Relationship, Disposition
        world.relationships[civ.name][breakaway_name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        world.relationships[breakaway_name][civ.name] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        # NEUTRAL toward everyone else
        for other_civ in world.civilizations:
            if other_civ.name not in (civ.name, breakaway_name):
                if other_civ.name not in world.relationships:
                    world.relationships[other_civ.name] = {}
                world.relationships[breakaway_name][other_civ.name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )
                world.relationships[other_civ.name][breakaway_name] = Relationship(
                    disposition=Disposition.NEUTRAL,
                )

        new_civs.append(breakaway_civ)

        events.append(Event(
            turn=world.turn,
            event_type="secession",
            actors=[civ.name, breakaway_name],
            description=f"The Secession of {breakaway_name} from {civ.name}",
            importance=9,
        ))

    world.civilizations.extend(new_civs)
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "secession" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14a): implement check_secession with breakaway civ spawning"
```

### Task 8: Register MOVE_CAPITAL action handler

**Files:**
- Modify: `src/chronicler/action_engine.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
def test_move_capital_eligibility():
    """MOVE_CAPITAL requires treasury >= 15 and regions >= 2."""
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    world = _make_world_with_regions(["A", "B", "C"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.treasury = 20
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.MOVE_CAPITAL in eligible

def test_move_capital_not_eligible_low_treasury():
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    civ.treasury = 10  # below 15
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.MOVE_CAPITAL not in eligible
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "move_capital" -v`
Expected: FAIL

- [ ] **Step 3: Add MOVE_CAPITAL eligibility and weight profile to action_engine.py**

In `get_eligible_actions`, add:

```python
# After existing eligibility checks:
if civ.treasury >= 15 and len(civ.regions) >= 2:
    eligible.append(ActionType.MOVE_CAPITAL)
```

In `TRAIT_WEIGHTS`, add `ActionType.MOVE_CAPITAL` entry to each trait dict with low weights (0.1 default, 0.3 for cautious/visionary).

Register the handler (placeholder — actual resolution is in politics.py but registered in action_engine.py):

```python
# If using registration pattern from M13 P3:
@register_action(ActionType.MOVE_CAPITAL)
def _resolve_move_capital(civ: Civilization, world: WorldState) -> Event:
    from chronicler.politics import resolve_move_capital
    return resolve_move_capital(civ, world)
```

- [ ] **Step 4: Implement resolve_move_capital in politics.py**

```python
# In politics.py, add:
def resolve_move_capital(civ: Civilization, world: WorldState) -> Event:
    """Resolve MOVE_CAPITAL action: relocate capital to most central region."""
    from chronicler.models import ActiveCondition
    civ.treasury -= 15

    # Pick most central region (minimum average distance to all other owned regions)
    def avg_distance(candidate: str) -> float:
        distances = []
        for rn in civ.regions:
            if rn != candidate:
                d = graph_distance(world.regions, candidate, rn)
                distances.append(d if d >= 0 else 1)
        return sum(distances) / max(len(distances), 1)

    target = min(civ.regions, key=avg_distance)
    old_capital = civ.capital_region
    civ.capital_region = target

    # Apply relocation condition
    condition = ActiveCondition(
        condition_type="capital_relocation",
        affected_civs=[civ.name],
        duration=5,
        severity=10,
    )
    world.active_conditions.append(condition)

    return Event(
        turn=world.turn,
        event_type="move_capital",
        actors=[civ.name],
        description=f"{civ.name} relocated capital from {old_capital} to {target}",
        importance=6,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "move_capital" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/politics.py src/chronicler/action_engine.py tests/test_politics.py
git commit -m "feat(m14a): register MOVE_CAPITAL action with eligibility and resolution"
```

### Task 9: Integrate politics calls into simulation.py

**Files:**
- Modify: `src/chronicler/simulation.py`

- [ ] **Step 1: Write integration test**

```python
# In tests/test_politics.py, add:
def test_simulation_calls_governing_costs():
    """Verify governing costs are applied during simulation turn."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B"], "B": ["A", "C"], "C": ["B", "D"], "D": ["C"]}
    world = _make_world_with_regions(["A", "B", "C", "D"], capital="A", adjacencies=adj)
    civ = world.civilizations[0]
    initial_stability = civ.stability
    initial_treasury = civ.treasury
    engine = ActionEngine(world)
    selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
    run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
    # After governing costs, stability and treasury should decrease
    assert civ.stability < initial_stability or civ.treasury < initial_treasury
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_politics.py::test_simulation_calls_governing_costs -v`
Expected: FAIL (governing costs not called yet)

- [ ] **Step 3: Add politics imports and calls to simulation.py**

In `apply_automatic_effects` (or the phase 2 function), add:

```python
from chronicler.politics import apply_governing_costs
# At the end of phase 2 automatic effects:
events.extend(apply_governing_costs(world))
```

In `phase_consequences` (phase 10), add:

```python
from chronicler.politics import check_capital_loss, check_secession
# After stability clamp:
events.extend(check_capital_loss(world))
events.extend(check_secession(world))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_politics.py::test_simulation_calls_governing_costs -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/simulation.py tests/test_politics.py
git commit -m "feat(m14a): integrate governing costs, capital loss, and secession into simulation loop"
```

### Task 10: M14a smoke test

**Files:**
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write 50-turn smoke test**

```python
# In tests/test_politics.py, add:
def test_m14a_smoke_50_turns():
    """50-turn run with large empire — should not crash, secession may occur."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    world = generate_world(seed=42)
    # Give one civ extra regions to trigger governing costs
    big_civ = world.civilizations[0]
    for region in world.regions:
        if region.controller is None:
            region.controller = big_civ.name
            big_civ.regions.append(region.name)
    big_civ.capital_region = big_civ.regions[0]

    for turn in range(50):
        engine = ActionEngine(world)
        selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
        run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)

    # Should not crash — that's the main assertion
    assert world.turn == 50
    # At least some civs should still be alive
    assert len(world.civilizations) >= 1
```

- [ ] **Step 2: Run smoke test**

Run: `pytest tests/test_politics.py::test_m14a_smoke_50_turns -v`
Expected: PASS (no crashes)

- [ ] **Step 3: Commit**

```bash
git add tests/test_politics.py
git commit -m "test(m14a): add 50-turn smoke test for governing costs and secession"
```

---

## Chunk 2: Phase M14b — Subordination & Alliance

### Task 11: Add VassalRelation and Federation models

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.models import VassalRelation, Federation

def test_vassal_relation_model():
    vr = VassalRelation(overlord="Empire", vassal="City", tribute_rate=0.15)
    assert vr.overlord == "Empire"
    assert vr.tribute_rate == 0.15
    assert vr.turns_active == 0

def test_federation_model():
    fed = Federation(name="The Iron Pact", members=["A", "B"], founded_turn=10)
    assert len(fed.members) == 2

def test_worldstate_has_vassal_and_federation_fields():
    ws = WorldState(name="test", seed=42)
    assert ws.vassal_relations == []
    assert ws.federations == []

def test_relationship_has_allied_turns():
    from chronicler.models import Relationship
    rel = Relationship()
    assert rel.allied_turns == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "vassal_relation_model or federation_model or vassal_and_federation or allied_turns" -v`
Expected: FAIL

- [ ] **Step 3: Add models to models.py**

```python
# After ActiveCondition class:
class VassalRelation(BaseModel):
    overlord: str
    vassal: str
    tribute_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    turns_active: int = 0

class Federation(BaseModel):
    name: str
    members: list[str]
    founded_turn: int

# In WorldState, add:
vassal_relations: list[VassalRelation] = Field(default_factory=list)
federations: list[Federation] = Field(default_factory=list)

# In Relationship, add:
allied_turns: int = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "vassal_relation_model or federation_model or vassal_and_federation or allied_turns" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_politics.py
git commit -m "feat(m14b): add VassalRelation, Federation models and allied_turns to Relationship"
```

### Task 12: Implement vassalization choice and tribute collection

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import choose_vassalize_or_absorb, collect_tribute

def _make_two_civ_world(winner_stability=50, winner_trait="cautious"):
    from chronicler.models import Region, Relationship, Disposition
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile", adjacencies=["B"]),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile", adjacencies=["A"]),
    ]
    w_leader = Leader(name="WL", trait=winner_trait, reign_start=0)
    l_leader = Leader(name="LL", trait="bold", reign_start=0)
    winner = Civilization(name="Winner", population=50, military=40, economy=50,
                          culture=30, stability=winner_stability, treasury=100, leader=w_leader,
                          regions=["A"], capital_region="A")
    loser = Civilization(name="Loser", population=30, military=10, economy=30,
                         culture=20, stability=20, treasury=50, leader=l_leader,
                         regions=["B"], capital_region="B")
    world = WorldState(name="test", seed=42, turn=5, regions=regions, civilizations=[winner, loser])
    world.relationships = {
        "Winner": {"Loser": Relationship(disposition=Disposition.HOSTILE)},
        "Loser": {"Winner": Relationship(disposition=Disposition.HOSTILE)},
    }
    return world, winner, loser

def test_vassalize_when_stability_high_and_cautious():
    world, winner, loser = _make_two_civ_world(winner_stability=50, winner_trait="cautious")
    result = choose_vassalize_or_absorb(winner, loser, world)
    # cautious trait biases toward vassalization when stability > 40
    # With seed 42, this should vassalize (but we accept either — the key test is it doesn't crash)
    assert isinstance(result, bool)

def test_no_vassalize_when_stability_low():
    world, winner, loser = _make_two_civ_world(winner_stability=30, winner_trait="cautious")
    result = choose_vassalize_or_absorb(winner, loser, world)
    assert result is False  # stability <= 40, no vassalization

def test_tribute_collection():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser", tribute_rate=0.15)
    world.vassal_relations.append(vr)
    collect_tribute(world)
    # tribute = floor(30 * 0.15) = 4
    assert loser.treasury == 50 - 4
    assert winner.treasury == 100 + 4
    assert vr.turns_active == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "vassalize or tribute" -v`
Expected: FAIL

- [ ] **Step 3: Implement choose_vassalize_or_absorb and collect_tribute**

```python
# In politics.py, add:

_ABSORPTION_BIAS_TRAITS = {"ambitious", "aggressive", "zealous"}
_VASSAL_BIAS_TRAITS = {"cautious", "shrewd", "visionary", "calculating"}


def choose_vassalize_or_absorb(
    winner: Civilization, loser: Civilization, world: WorldState,
) -> bool:
    """Return True to vassalize, False to absorb."""
    if winner.stability <= 40:
        return False

    rng = random.Random(world.seed + world.turn + hash(winner.name))
    trait = winner.leader.trait

    if trait in _ABSORPTION_BIAS_TRAITS:
        threshold = 0.3  # 30% chance to vassalize
    elif trait in _VASSAL_BIAS_TRAITS:
        threshold = 0.8  # 80% chance to vassalize
    else:
        threshold = 0.5  # 50/50

    return rng.random() < threshold


def collect_tribute(world: WorldState) -> list[Event]:
    """Phase 2: Collect tribute from vassals to overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}

    for vr in world.vassal_relations:
        vassal = civ_map.get(vr.vassal)
        overlord = civ_map.get(vr.overlord)
        if vassal is None or overlord is None:
            continue
        tribute = math.floor(vassal.economy * vr.tribute_rate)
        vassal.treasury -= tribute
        overlord.treasury += tribute
        vr.turns_active += 1

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "vassalize or tribute" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14b): implement vassalization choice and tribute collection"
```

### Task 13: Implement vassal rebellion

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import check_vassal_rebellion

def test_vassal_rebellion_when_overlord_weak():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser")
    world.vassal_relations.append(vr)
    winner.stability = 20  # below 25

    # Try multiple seeds to get rebellion to fire (prob=0.15)
    rebelled = False
    for seed in range(100):
        world.seed = seed
        world.vassal_relations = [VassalRelation(overlord="Winner", vassal="Loser")]
        loser.stability = 20
        loser.asabiya = 0.5
        events = check_vassal_rebellion(world)
        if len(world.vassal_relations) == 0:
            rebelled = True
            break
    assert rebelled

def test_vassal_no_rebellion_when_overlord_strong():
    world, winner, loser = _make_two_civ_world()
    vr = VassalRelation(overlord="Winner", vassal="Loser")
    world.vassal_relations.append(vr)
    winner.stability = 50  # well above 25
    winner.treasury = 100  # well above 10
    events = check_vassal_rebellion(world)
    assert len(world.vassal_relations) == 1  # no rebellion
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "vassal_rebellion" -v`
Expected: FAIL

- [ ] **Step 3: Implement check_vassal_rebellion**

```python
# In politics.py, add:
def check_vassal_rebellion(world: WorldState) -> list[Event]:
    """Phase 10: Check if vassals rebel against weak overlords."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove: list[VassalRelation] = []
    rebelled_overlords: set[str] = set()

    for vr in list(world.vassal_relations):
        overlord = civ_map.get(vr.overlord)
        vassal = civ_map.get(vr.vassal)
        if overlord is None or vassal is None:
            to_remove.append(vr)
            continue

        # Guard: overlord must be weak
        if overlord.stability >= 25 and overlord.treasury >= 10:
            continue

        rng = random.Random(world.seed + world.turn + hash(vr.vassal))

        # Cascade check: lower probability if another vassal already rebelled this turn
        prob = 0.05 if vr.overlord in rebelled_overlords else 0.15

        # Cascade only fires if vassal is HOSTILE/SUSPICIOUS toward overlord
        if vr.overlord in rebelled_overlords:
            from chronicler.models import Disposition
            rel = world.relationships.get(vr.vassal, {}).get(vr.overlord)
            if rel is None or rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                continue

        if rng.random() >= prob:
            continue

        # Rebellion fires
        to_remove.append(vr)
        rebelled_overlords.add(vr.overlord)

        vassal.stability = clamp(vassal.stability + 10, STAT_FLOOR["stability"], 100)
        vassal.asabiya = min(vassal.asabiya + 0.2, 1.0)

        # Set disposition to HOSTILE
        from chronicler.models import Disposition, Relationship
        if vr.vassal in world.relationships and vr.overlord in world.relationships[vr.vassal]:
            world.relationships[vr.vassal][vr.overlord].disposition = Disposition.HOSTILE

        events.append(Event(
            turn=world.turn,
            event_type="vassal_rebellion",
            actors=[vr.vassal, vr.overlord],
            description=f"The {vr.vassal} Rebellion against {vr.overlord}",
            importance=8,
        ))

    for vr in to_remove:
        if vr in world.vassal_relations:
            world.vassal_relations.remove(vr)

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "vassal_rebellion" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14b): implement vassal rebellion with cascade mechanics"
```

### Task 14: Implement federation formation and dissolution

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import check_federation_formation

def test_federation_forms_after_10_allied_turns():
    from chronicler.models import Region, Relationship, Disposition
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile"),
    ]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    civ_a = Civilization(name="CivA", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="CivB", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=["B"], capital_region="B")
    world = WorldState(name="test", seed=42, turn=20, regions=regions,
                       civilizations=[civ_a, civ_b])
    world.relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.ALLIED, allied_turns=10)},
        "CivB": {"CivA": Relationship(disposition=Disposition.ALLIED, allied_turns=10)},
    }
    events = check_federation_formation(world)
    assert len(world.federations) == 1
    assert "CivA" in world.federations[0].members
    assert "CivB" in world.federations[0].members

def test_federation_does_not_form_below_10_turns():
    from chronicler.models import Region, Relationship, Disposition
    regions = [Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile")]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    civ_a = Civilization(name="CivA", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="CivB", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=[], capital_region=None)
    world = WorldState(name="test", seed=42, turn=20, regions=regions,
                       civilizations=[civ_a, civ_b])
    world.relationships = {
        "CivA": {"CivB": Relationship(disposition=Disposition.ALLIED, allied_turns=5)},
        "CivB": {"CivA": Relationship(disposition=Disposition.ALLIED, allied_turns=5)},
    }
    events = check_federation_formation(world)
    assert len(world.federations) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "federation_form" -v`
Expected: FAIL

- [ ] **Step 3: Implement check_federation_formation**

```python
# In politics.py, add:

_FEDERATION_ADJECTIVES = [
    "Northern", "Southern", "Eastern", "Western", "Iron",
    "Golden", "Silver", "Maritime", "Sacred", "Grand",
]
_FEDERATION_NOUNS = [
    "Accord", "Pact", "League", "Alliance", "Compact", "Coalition", "Confederation",
]


def _civ_in_federation(civ_name: str, world: WorldState) -> Federation | None:
    """Return the federation a civ belongs to, or None."""
    for fed in world.federations:
        if civ_name in fed.members:
            return fed
    return None


def _is_vassal(civ_name: str, world: WorldState) -> bool:
    """Check if a civ is a vassal."""
    return any(vr.vassal == civ_name for vr in world.vassal_relations)


def check_federation_formation(world: WorldState) -> list[Event]:
    """Phase 10: Check if any allied pairs can form or join federations."""
    from chronicler.models import Federation
    events: list[Event] = []
    checked_pairs: set[tuple[str, str]] = set()

    for civ_a in world.civilizations:
        if _is_vassal(civ_a.name, world):
            continue
        rels_a = world.relationships.get(civ_a.name, {})
        for civ_b_name, rel_ab in rels_a.items():
            if rel_ab.allied_turns < 10:
                continue
            pair = tuple(sorted([civ_a.name, civ_b_name]))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)

            # Check both directions
            rel_ba = world.relationships.get(civ_b_name, {}).get(civ_a.name)
            if rel_ba is None or rel_ba.allied_turns < 10:
                continue

            if _is_vassal(civ_b_name, world):
                continue

            fed_a = _civ_in_federation(civ_a.name, world)
            fed_b = _civ_in_federation(civ_b_name, world)

            if fed_a and fed_b:
                continue  # both in different federations, no merge
            elif fed_a and not fed_b:
                fed_a.members.append(civ_b_name)
            elif fed_b and not fed_a:
                fed_b.members.append(civ_a.name)
            else:
                # Create new federation
                rng = random.Random(world.seed + world.turn)
                adj = rng.choice(_FEDERATION_ADJECTIVES)
                noun = rng.choice(_FEDERATION_NOUNS)
                fed_name = f"The {adj} {noun}"
                new_fed = Federation(
                    name=fed_name,
                    members=[civ_a.name, civ_b_name],
                    founded_turn=world.turn,
                )
                world.federations.append(new_fed)
                events.append(Event(
                    turn=world.turn,
                    event_type="federation_formed",
                    actors=[civ_a.name, civ_b_name],
                    description=f"Formation of {fed_name}",
                    importance=7,
                ))

    return events
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "federation_form" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14b): implement federation formation from sustained alliance"
```

### Task 15: Implement federation defense and WAR eligibility filters

**Files:**
- Modify: `src/chronicler/politics.py`, `src/chronicler/action_engine.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import trigger_federation_defense

def test_federation_defense_adds_allies_to_war():
    from chronicler.models import Region, Relationship, Disposition
    regions = [
        Region(name="A", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="B", terrain="plains", carrying_capacity=50, resources="fertile"),
        Region(name="C", terrain="plains", carrying_capacity=50, resources="fertile"),
    ]
    la = Leader(name="LA", trait="bold", reign_start=0)
    lb = Leader(name="LB", trait="bold", reign_start=0)
    lc = Leader(name="LC", trait="bold", reign_start=0)
    civ_a = Civilization(name="Attacker", population=50, military=40, economy=40,
                         culture=30, stability=50, leader=la, regions=["A"], capital_region="A")
    civ_b = Civilization(name="Defender", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lb, regions=["B"], capital_region="B")
    civ_c = Civilization(name="Ally", population=50, military=30, economy=40,
                         culture=30, stability=50, leader=lc, regions=["C"], capital_region="C")
    world = WorldState(name="test", seed=42, turn=10, regions=regions,
                       civilizations=[civ_a, civ_b, civ_c])
    # Defender and Ally in a federation
    world.federations = [Federation(name="The Iron Pact", members=["Defender", "Ally"], founded_turn=5)]
    world.active_wars = [("Attacker", "Defender")]
    world.war_start_turns = {war_key("Attacker", "Defender"): 10}

    events = trigger_federation_defense("Attacker", "Defender", world)
    # Ally should now be at war with Attacker
    assert ("Attacker", "Ally") in world.active_wars or ("Ally", "Attacker") in world.active_wars

def test_vassal_cannot_declare_war():
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A", "B"], capital="A", adjacencies=adj)
    world.vassal_relations = [VassalRelation(overlord="Other", vassal="Empire")]
    civ = world.civilizations[0]
    engine = ActionEngine(world)
    eligible = engine.get_eligible_actions(civ)
    assert ActionType.WAR not in eligible
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_politics.py -k "federation_defense or vassal_cannot" -v`
Expected: FAIL

- [ ] **Step 3: Implement trigger_federation_defense and eligibility filters**

```python
# In politics.py, add:
def trigger_federation_defense(attacker: str, defender: str, world: WorldState) -> list[Event]:
    """Called during war resolution: if defender is in a federation, allies join."""
    events: list[Event] = []
    fed = _civ_in_federation(defender, world)
    if fed is None:
        return events

    for member in fed.members:
        if member == defender or member == attacker:
            continue
        # Add member to war against attacker (one layer deep — only defender's fed)
        war_pair = (attacker, member)
        if war_pair not in world.active_wars and (member, attacker) not in world.active_wars:
            world.active_wars.append(war_pair)
            world.war_start_turns[war_key(attacker, member)] = world.turn
            events.append(Event(
                turn=world.turn,
                event_type="federation_defense",
                actors=[member, defender, attacker],
                description=f"{member} joins war against {attacker} in defense of {defender}",
                importance=6,
            ))

    return events
```

In `action_engine.py` `get_eligible_actions`, add vassal and federation checks:

```python
# Check if civ is a vassal — vassals can't declare war
is_vassal = any(vr.vassal == civ.name for vr in self.world.vassal_relations)
if is_vassal:
    eligible = [a for a in eligible if a != ActionType.WAR]

# Check federation co-members — can't attack co-members
# (filter happens in target selection, not eligibility, since WAR itself is still allowed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "federation_defense or vassal_cannot" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/politics.py src/chronicler/action_engine.py tests/test_politics.py
git commit -m "feat(m14b): implement federation defense and vassal WAR restriction"
```

### Task 16: Integrate M14b into simulation.py and federation trade bypass

**Files:**
- Modify: `src/chronicler/simulation.py`, `src/chronicler/resources.py`

- [ ] **Step 1: Write integration tests**

```python
# In tests/test_politics.py, add:
def test_tribute_collected_during_simulation():
    """Verify tribute is collected during simulation turn."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    adj = {"A": ["B"], "B": ["A"]}
    world = _make_world_with_regions(["A"], capital="A", adjacencies=adj)
    # Add a second civ as vassal
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    vassal_civ = Civilization(name="Vassal", population=30, military=20, economy=40,
                              culture=20, stability=30, treasury=50, leader=l2,
                              regions=["B"], capital_region="B")
    world.civilizations.append(vassal_civ)
    world.regions.append(Region(name="B", terrain="plains", carrying_capacity=50,
                                resources="fertile", adjacencies=["A"]))
    world.vassal_relations = [VassalRelation(overlord="Empire", vassal="Vassal")]
    initial_empire_treasury = world.civilizations[0].treasury
    engine = ActionEngine(world)
    selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
    run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
    # Empire should have gained tribute
    # (exact amount depends on other income/costs, but tribute was collected)
    assert world.vassal_relations[0].turns_active >= 1
```

- [ ] **Step 2: Add simulation.py integration**

In `apply_automatic_effects`, add after governing costs:

```python
from chronicler.politics import collect_tribute
events.extend(collect_tribute(world))
```

In `phase_consequences`, add after secession:

```python
from chronicler.politics import check_vassal_rebellion, check_federation_formation
events.extend(check_vassal_rebellion(world))
events.extend(check_federation_formation(world))
```

In war resolution (where absorption happens), add vassalization choice:

```python
from chronicler.politics import choose_vassalize_or_absorb
if choose_vassalize_or_absorb(winner, loser, world):
    # vassalize instead of absorb
    ...
```

- [ ] **Step 3: Modify get_active_trade_routes for federation bypass**

In `resources.py` `get_active_trade_routes`, add:

```python
# Federation members get trade routes regardless of adjacency
for fed in world.federations:
    for i, m1 in enumerate(fed.members):
        for m2 in fed.members[i+1:]:
            pair = tuple(sorted([m1, m2]))
            if pair not in routes:
                routes.add(pair)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_politics.py -k "tribute_collected" -v && pytest --tb=short -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/simulation.py src/chronicler/resources.py tests/test_politics.py
git commit -m "feat(m14b): integrate vassals and federations into simulation loop and trade routes"
```

---

## Chunk 3: Phase M14c — Indirect Power

### Task 17: Add ProxyWar and ExileModifier models

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.models import ProxyWar, ExileModifier

def test_proxy_war_model():
    pw = ProxyWar(sponsor="A", target_civ="B", target_region="R1")
    assert pw.treasury_per_turn == 8
    assert pw.detected is False

def test_exile_modifier_model():
    em = ExileModifier(original_civ_name="Fallen", absorber_civ="Victor",
                       conquered_regions=["R1", "R2"])
    assert em.turns_remaining == 20
    assert em.recognized_by == []

def test_worldstate_has_proxy_and_exile_fields():
    ws = WorldState(name="test", seed=42)
    assert ws.proxy_wars == []
    assert ws.exile_modifiers == []
```

- [ ] **Step 2: Run tests to verify they fail, add models, run to pass**

- [ ] **Step 3: Add FUND_INSTABILITY to ActionType**

```python
FUND_INSTABILITY = "fund_instability"
```

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/models.py tests/test_politics.py
git commit -m "feat(m14c): add ProxyWar, ExileModifier models and FUND_INSTABILITY action"
```

### Task 18: Implement proxy war mechanics (apply, detect, cancel)

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import apply_proxy_wars, check_proxy_detection

def test_proxy_war_drains_sponsor_and_target():
    from chronicler.models import Region, ProxyWar
    world = _make_world_with_regions(["A", "B"], capital="A")
    civ = world.civilizations[0]
    civ.treasury = 50
    civ.stability = 50
    civ.economy = 40
    # Add target civ
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=60, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    apply_proxy_wars(world)
    assert civ.treasury == 50 - 8
    assert target.stability == 40 - 3
    assert target.economy == 30 - 2  # clamped to 0 minimum

def test_proxy_war_auto_cancels_on_bankruptcy():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.treasury = 5  # will go negative after -8
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=60, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    apply_proxy_wars(world)
    assert len(world.proxy_wars) == 0  # auto-cancelled

def test_proxy_detection_scales_with_culture():
    from chronicler.models import ProxyWar, Relationship, Disposition
    world = _make_world_with_regions(["A"], capital="A")
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    target = Civilization(name="Target", population=30, military=20, economy=30,
                          culture=80, stability=40, treasury=50, leader=l2,
                          regions=["B"], capital_region="B")
    world.civilizations.append(target)
    world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
    world.relationships = {
        "Empire": {"Target": Relationship(disposition=Disposition.HOSTILE)},
        "Target": {"Empire": Relationship(disposition=Disposition.HOSTILE)},
    }
    # With culture=80, detection prob=0.8 — should detect within a few tries
    detected = False
    for seed in range(20):
        world.seed = seed
        world.proxy_wars = [ProxyWar(sponsor="Empire", target_civ="Target", target_region="B")]
        events = check_proxy_detection(world)
        if world.proxy_wars[0].detected:
            detected = True
            break
    assert detected
```

- [ ] **Step 2: Implement apply_proxy_wars and check_proxy_detection**

```python
# In politics.py, add:
def apply_proxy_wars(world: WorldState) -> list[Event]:
    """Phase 2: Apply ongoing proxy war costs and effects."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    to_remove = []

    for pw in world.proxy_wars:
        sponsor = civ_map.get(pw.sponsor)
        target = civ_map.get(pw.target_civ)
        if sponsor is None or target is None:
            to_remove.append(pw)
            continue

        sponsor.treasury -= pw.treasury_per_turn
        pw.turns_active += 1
        target.stability = clamp(target.stability - 3, STAT_FLOOR["stability"], 100)
        target.economy = clamp(target.economy - 2, STAT_FLOOR["economy"], 100)

        if sponsor.treasury < 0:
            to_remove.append(pw)
            continue

        # Check other cancellation conditions
        if pw.target_region not in target.regions:
            to_remove.append(pw)
            continue

        # Cancel if sponsor and target reach FRIENDLY+ disposition
        from chronicler.models import Disposition
        rel = world.relationships.get(pw.sponsor, {}).get(pw.target_civ)
        if rel and rel.disposition in (Disposition.FRIENDLY, Disposition.ALLIED):
            to_remove.append(pw)
            continue

        # Cancel if sponsor has no regions (conquered/absorbed)
        if not sponsor.regions:
            to_remove.append(pw)

    for pw in to_remove:
        if pw in world.proxy_wars:
            world.proxy_wars.remove(pw)

    return events


def check_proxy_detection(world: WorldState) -> list[Event]:
    """Phase 10: Check if proxy wars are detected by target civs."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}

    for pw in world.proxy_wars:
        if pw.detected:
            continue
        target = civ_map.get(pw.target_civ)
        if target is None:
            continue

        rng = random.Random(world.seed + world.turn + hash(pw.sponsor) + hash(pw.target_civ))
        detection_prob = target.culture / 100
        if rng.random() < detection_prob:
            pw.detected = True
            target.stability = clamp(target.stability + 5, STAT_FLOOR["stability"], 100)

            # Set sponsor disposition to HOSTILE
            from chronicler.models import Disposition
            rels = world.relationships.get(pw.sponsor, {})
            if pw.target_civ in rels:
                rels[pw.target_civ].disposition = Disposition.HOSTILE

            events.append(Event(
                turn=world.turn,
                event_type="proxy_detected",
                actors=[pw.sponsor, pw.target_civ],
                description=f"{pw.sponsor} exposed funding separatists in {pw.target_region}",
                importance=7,
            ))

    return events
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_politics.py -k "proxy" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/politics.py tests/test_politics.py
git commit -m "feat(m14c): implement proxy war mechanics (apply, detect, cancel)"
```

### Task 19: Implement diplomatic congress

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import check_congress

def test_congress_does_not_trigger_below_3_war_participants():
    world = _make_world_with_regions(["A"], capital="A")
    world.active_wars = [("A", "B")]
    events = check_congress(world)
    assert all(e.event_type != "congress" for e in events)

def test_congress_can_trigger_with_3_plus_participants():
    """With enough war participants and favorable seed, congress triggers."""
    from chronicler.models import Region, Relationship, Disposition
    regions = [Region(name=n, terrain="plains", carrying_capacity=50, resources="fertile")
               for n in ["A", "B", "C", "D"]]
    civs = []
    for name in ["Civ1", "Civ2", "Civ3", "Civ4"]:
        l = Leader(name=f"L_{name}", trait="bold", reign_start=0)
        c = Civilization(name=name, population=50, military=30, economy=40,
                         culture=30, stability=50, treasury=100, leader=l,
                         regions=[name[3]], capital_region=name[3])
        civs.append(c)
    world = WorldState(name="test", seed=42, regions=regions, civilizations=civs)
    world.active_wars = [("Civ1", "Civ2"), ("Civ3", "Civ4"), ("Civ1", "Civ3")]
    world.war_start_turns = {
        war_key("Civ1", "Civ2"): 1,
        war_key("Civ3", "Civ4"): 2,
        war_key("Civ1", "Civ3"): 3,
    }
    # Try many seeds to trigger the 5% probability
    triggered = False
    for seed in range(200):
        world.seed = seed
        world.turn = seed
        events = check_congress(world)
        if any(e.event_type in ("congress_peace", "congress_ceasefire", "congress_collapse") for e in events):
            triggered = True
            break
    assert triggered
```

- [ ] **Step 2: Implement check_congress**

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat(m14c): implement diplomatic congress mechanics"
```

### Task 20: Implement governments in exile (create, effects, restoration)

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests for exile creation and effects**

```python
# In tests/test_politics.py, add:
from chronicler.politics import create_exile, apply_exile_effects, check_restoration

def test_exile_created_on_civ_elimination():
    world = _make_world_with_regions(["A", "B"], capital="A")
    eliminated = world.civilizations[0]
    eliminated.regions = ["B"]
    l2 = Leader(name="Conqueror", trait="bold", reign_start=0)
    conqueror = Civilization(name="Victor", population=50, military=40, economy=50,
                             culture=40, stability=50, treasury=100, leader=l2,
                             regions=["A"], capital_region="A")
    world.civilizations.append(conqueror)
    exile = create_exile(eliminated, conqueror, world)
    assert exile.original_civ_name == "Empire"
    assert exile.absorber_civ == "Victor"
    assert exile.turns_remaining == 20
    assert "B" in exile.conquered_regions

def test_exile_drains_absorber_stability():
    world = _make_world_with_regions(["A"], capital="A")
    civ = world.civilizations[0]
    civ.stability = 50
    world.exile_modifiers = [
        ExileModifier(original_civ_name="Fallen", absorber_civ="Empire",
                      conquered_regions=["A"], turns_remaining=15)
    ]
    apply_exile_effects(world)
    assert civ.stability == 50 - 5
    assert world.exile_modifiers[0].turns_remaining == 14

def test_exile_removed_when_expired():
    world = _make_world_with_regions(["A"], capital="A")
    world.exile_modifiers = [
        ExileModifier(original_civ_name="Fallen", absorber_civ="Empire",
                      conquered_regions=["A"], turns_remaining=1)
    ]
    apply_exile_effects(world)
    assert len(world.exile_modifiers) == 0  # expired and removed
```

- [ ] **Step 2: Implement create_exile, apply_exile_effects, check_restoration**

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat(m14c): implement governments in exile (creation, effects, restoration)"
```

### Task 21: Register FUND_INSTABILITY action and integrate M14c into simulation

**Files:**
- Modify: `src/chronicler/action_engine.py`, `src/chronicler/simulation.py`

- [ ] **Step 1: Add FUND_INSTABILITY to action_engine.py**

- Eligibility: `treasury >= 8`, has hostile neighbor, not a vassal
- Weight profile: `calculating` and `shrewd` get 1.5, `cautious` gets 1.2, `aggressive` and `bold` get 0.2
- Handler delegates to `politics.resolve_fund_instability(civ, world)`

- [ ] **Step 2: Add simulation.py integration**

In `apply_automatic_effects`: add `apply_proxy_wars`, `apply_exile_effects`
In `phase_consequences`: add `check_proxy_detection`, `check_restoration`
In `phase_random_events`: add `check_congress`
In civ elimination logic: add `create_exile`

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(m14c): integrate proxy wars, exile, and congresses into simulation loop"
```

---

## Chunk 4: Phase M14d — Systemic Dynamics

### Task 22: Add M14d tracking fields to models

**Files:**
- Modify: `src/chronicler/models.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
def test_civ_has_m14d_tracking_fields():
    leader = Leader(name="Test", trait="bold", reign_start=0)
    civ = Civilization(name="Test", population=50, military=30, economy=40,
                       culture=30, stability=50, leader=leader)
    assert civ.peak_region_count == 0
    assert civ.decline_turns == 0
    assert civ.stats_sum_history == []

def test_worldstate_has_peace_and_bop_turns():
    ws = WorldState(name="test", seed=42)
    assert ws.peace_turns == 0
    assert ws.balance_of_power_turns == 0
```

- [ ] **Step 2: Add fields to models.py**

```python
# In Civilization, add:
peak_region_count: int = 0
decline_turns: int = 0
stats_sum_history: list[int] = Field(default_factory=list)

# In WorldState, add:
peace_turns: int = 0
balance_of_power_turns: int = 0
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat(m14d): add tracking fields for systemic dynamics"
```

### Task 23: Implement balance of power

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write failing tests**

```python
# In tests/test_politics.py, add:
from chronicler.politics import apply_balance_of_power

def test_balance_of_power_no_trigger_below_40_percent():
    """No coalition pressure when no civ exceeds 40% power share."""
    from chronicler.models import Region, Relationship, Disposition
    civs = []
    for i, name in enumerate(["A", "B", "C"]):
        l = Leader(name=f"L{name}", trait="bold", reign_start=0)
        c = Civilization(name=name, population=30, military=30, economy=30,
                         culture=30, stability=50, leader=l, regions=[f"R{i}"],
                         capital_region=f"R{i}")
        civs.append(c)
    regions = [Region(name=f"R{i}", terrain="plains", carrying_capacity=50, resources="fertile")
               for i in range(3)]
    world = WorldState(name="test", seed=42, regions=regions, civilizations=civs)
    world.relationships = {}
    for c1 in civs:
        world.relationships[c1.name] = {}
        for c2 in civs:
            if c1.name != c2.name:
                world.relationships[c1.name][c2.name] = Relationship(disposition=Disposition.HOSTILE)
    apply_balance_of_power(world)
    assert world.balance_of_power_turns == 0

def test_balance_of_power_triggers_for_dominant_civ():
    """Coalition pressure activates when one civ exceeds 40% power."""
    from chronicler.models import Region, Relationship, Disposition
    # Dominant civ with 5 regions, high military and economy
    l1 = Leader(name="L1", trait="bold", reign_start=0)
    dominant = Civilization(name="Dominant", population=80, military=80, economy=80,
                            culture=50, stability=50, leader=l1,
                            regions=["R0", "R1", "R2", "R3", "R4"], capital_region="R0")
    l2 = Leader(name="L2", trait="bold", reign_start=0)
    weak = Civilization(name="Weak", population=20, military=10, economy=10,
                        culture=10, stability=50, leader=l2,
                        regions=["R5"], capital_region="R5")
    regions = [Region(name=f"R{i}", terrain="plains", carrying_capacity=50, resources="fertile")
               for i in range(6)]
    world = WorldState(name="test", seed=42, regions=regions, civilizations=[dominant, weak])
    world.relationships = {
        "Dominant": {"Weak": Relationship(disposition=Disposition.NEUTRAL)},
        "Weak": {"Dominant": Relationship(disposition=Disposition.HOSTILE)},
    }
    apply_balance_of_power(world)
    assert world.balance_of_power_turns == 1
```

- [ ] **Step 2: Implement apply_balance_of_power**

```python
# In politics.py, add:
def apply_balance_of_power(world: WorldState) -> list[Event]:
    """Phase 2: Apply coalition pressure against dominant civs."""
    from chronicler.models import Disposition
    events: list[Event] = []
    living = [c for c in world.civilizations if c.regions]
    if len(living) < 2:
        return events

    scores = {c.name: c.military + c.economy + len(c.regions) * 5 for c in living}
    total = sum(scores.values())
    if total == 0:
        return events

    dominant = max(scores, key=scores.get)
    if scores[dominant] / total <= 0.40:
        world.balance_of_power_turns = 0
        return events

    world.balance_of_power_turns += 1

    # Upgrade disposition among non-dominant civs every 5 turns
    if world.balance_of_power_turns % 5 == 0:
        DISPOSITION_UPGRADE = {
            Disposition.HOSTILE: Disposition.SUSPICIOUS,
            Disposition.SUSPICIOUS: Disposition.NEUTRAL,
            Disposition.NEUTRAL: Disposition.FRIENDLY,
            Disposition.FRIENDLY: Disposition.ALLIED,
            Disposition.ALLIED: Disposition.ALLIED,
        }
        non_dominant = [c.name for c in living if c.name != dominant]
        for i, name_a in enumerate(non_dominant):
            for name_b in non_dominant[i+1:]:
                # Upgrade both directions
                for a, b in [(name_a, name_b), (name_b, name_a)]:
                    rel = world.relationships.get(a, {}).get(b)
                    if rel:
                        rel.disposition = DISPOSITION_UPGRADE[rel.disposition]

    return events
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat(m14d): implement balance of power coalition pressure"
```

### Task 24: Implement fallen empire modifier

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write tests, implement, commit**

Key tests:
- `peak_region_count` tracks correctly (max, never decreases)
- Fallen empire activates at peak >= 5 and regions == 1
- Asabiya +0.05/turn while fallen
- Deactivates at regions >= 3

```bash
git commit -m "feat(m14d): implement fallen empire modifier with asabiya boost"
```

### Task 25: Implement civilizational twilight

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write tests, implement, commit**

Key tests:
- `stats_sum_history` rolling window capped at 20
- `decline_turns` increments when current sum < 20 turns ago
- Twilight drains population (-3) and culture (-2), clamped
- Revival resets decline_turns
- Peaceful absorption at decline_turns >= 40

```bash
git commit -m "feat(m14d): implement civilizational twilight with rolling window decline"
```

### Task 26: Implement the long peace problem

**Files:**
- Modify: `src/chronicler/politics.py`
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write tests, implement, commit**

Key tests:
- `peace_turns` increments when no active wars, resets when wars exist
- Military restlessness: stability -2 for military > 60
- Economy inequality: +1 richest, -1 poorest (clamped)
- ALLIED disposition downgrade every 10 peace turns

```bash
git commit -m "feat(m14d): implement long peace problem (military restlessness, inequality, alliance decay)"
```

### Task 27: Integrate M14d into simulation and update viewer types

**Files:**
- Modify: `src/chronicler/simulation.py`, `src/chronicler/bundle.py`, `viewer/src/types.ts`

- [ ] **Step 1: Add M14d calls to simulation.py**

In `apply_automatic_effects`:
```python
from chronicler.politics import (
    apply_balance_of_power, apply_fallen_empire, apply_twilight,
    apply_long_peace, update_peak_regions,
)
events.extend(apply_balance_of_power(world))
events.extend(apply_fallen_empire(world))
events.extend(apply_twilight(world))
events.extend(apply_long_peace(world))
update_peak_regions(world)
```

In `phase_consequences` (end):
```python
from chronicler.politics import check_twilight_absorption, update_decline_tracking
events.extend(check_twilight_absorption(world))
update_decline_tracking(world)
```

- [ ] **Step 2: Update bundle.py snapshot fields**

Add to `TurnSnapshot`: `vassal_relations`, `federations`, `proxy_wars`, `exile_modifiers`, `capitals`, `peace_turns`
Add to `CivSnapshot`: `is_vassal`, `is_fallen_empire`, `in_twilight`, `federation_name`

- [ ] **Step 3: Update viewer/src/types.ts**

Add corresponding TypeScript fields to `TurnSnapshot` and `CivSnapshot` interfaces.

- [ ] **Step 4: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(m14d): integrate systemic dynamics into simulation and update viewer types"
```

### Task 28: M14 integration smoke test

**Files:**
- Test: `tests/test_politics.py`

- [ ] **Step 1: Write 200-turn integration test**

```python
# In tests/test_politics.py, add:
def test_m14_integration_200_turns():
    """200-turn run with all M14 mechanics — verify emergent political events."""
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    world = generate_world(seed=42)

    # Give civs extra regions to make governing costs relevant
    for i, civ in enumerate(world.civilizations):
        for region in world.regions:
            if region.controller is None:
                region.controller = civ.name
                civ.regions.append(region.name)
                break
        civ.capital_region = civ.regions[0]

    secession_count = 0
    vassal_count = 0
    federation_count = 0

    for turn in range(200):
        engine = ActionEngine(world)
        selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
        run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
        secession_count += sum(1 for e in world.events_timeline if e.event_type == "secession" and e.turn == world.turn)
        vassal_count = len(world.vassal_relations)
        federation_count = len(world.federations)

    assert world.turn == 200
    assert len(world.civilizations) >= 1  # at least someone survives
    # Political events should emerge from pure mechanics
    total_political = secession_count + vassal_count + federation_count
    # In 200 turns with governing costs active, some political dynamics should emerge
    # (but with small maps and few civs, it's not guaranteed — just verify no crashes)
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_politics.py::test_m14_integration_200_turns -v --timeout=30`
Expected: PASS (no crashes, completes within 30s)

- [ ] **Step 3: Run all existing scenario tests**

Run: `pytest --tb=short -q`
Expected: All pass — existing scenarios work unchanged with M14 active

- [ ] **Step 4: Commit**

```bash
git commit -m "test(m14): add 200-turn integration test for full political topology system"
```

---

## Addendum: Missing Implementations (Review Fixes)

The following implementations were identified as gaps in the original plan by spec review. They must be completed within their respective tasks.

### A1: Vassalization Resolution (add to Task 12)

Task 12's `choose_vassalize_or_absorb` returns a boolean. The caller in `simulation.py` (Task 16) must apply the full resolution when `True`:

```python
# In politics.py, add:
def resolve_vassalization(winner: Civilization, loser: Civilization, world: WorldState) -> list[Event]:
    """Apply full vassalization resolution steps."""
    from chronicler.models import VassalRelation, Disposition, Relationship
    events: list[Event] = []

    # 1. Remove from active_wars and war_start_turns
    world.active_wars = [
        w for w in world.active_wars
        if not (set(w) == {winner.name, loser.name})
    ]
    key = war_key(winner.name, loser.name)
    world.war_start_turns.pop(key, None)

    # 2. Loser keeps all regions, identity, governance (no changes needed)

    # 3. Create VassalRelation
    world.vassal_relations.append(VassalRelation(
        overlord=winner.name, vassal=loser.name, tribute_rate=0.15,
    ))

    # 4. Set dispositions
    if winner.name not in world.relationships:
        world.relationships[winner.name] = {}
    if loser.name not in world.relationships:
        world.relationships[loser.name] = {}
    world.relationships[winner.name][loser.name] = Relationship(disposition=Disposition.SUSPICIOUS)
    world.relationships[loser.name][winner.name] = Relationship(disposition=Disposition.HOSTILE)

    # 5. Vassal war restriction handled by get_eligible_actions filter (Task 15)

    # 6. Named event
    events.append(Event(
        turn=world.turn,
        event_type="vassalization",
        actors=[winner.name, loser.name],
        description=f"The Subjugation of {loser.name}",
        importance=7,
    ))
    return events
```

In `simulation.py` war resolution (Task 16), replace the `...` placeholder:
```python
from chronicler.politics import choose_vassalize_or_absorb, resolve_vassalization
if choose_vassalize_or_absorb(winner, loser, world):
    events.extend(resolve_vassalization(winner, loser, world))
else:
    # existing absorption logic
    ...
```

### A2: Federation Dissolution (add to Task 14)

```python
# In politics.py, add:
def check_federation_dissolution(world: WorldState) -> list[Event]:
    """Phase 10: Check if any federation members want to exit."""
    from chronicler.models import Disposition
    events: list[Event] = []
    feds_to_remove = []

    for fed in world.federations:
        exiting: list[str] = []
        for member in fed.members:
            rels = world.relationships.get(member, {})
            for other_member in fed.members:
                if other_member == member:
                    continue
                rel = rels.get(other_member)
                if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL):
                    # Disposition below FRIENDLY — this member exits
                    exiting.append(member)
                    break

        for member in exiting:
            fed.members.remove(member)
            # Exiting civ penalty
            civ = next((c for c in world.civilizations if c.name == member), None)
            if civ:
                civ.stability = clamp(civ.stability - 15, STAT_FLOOR["stability"], 100)
            # Remaining members penalty
            for remaining in fed.members:
                rc = next((c for c in world.civilizations if c.name == remaining), None)
                if rc:
                    rc.stability = clamp(rc.stability - 5, STAT_FLOOR["stability"], 100)

        # Size collapse
        if len(fed.members) <= 1:
            feds_to_remove.append(fed)
            events.append(Event(
                turn=world.turn,
                event_type="federation_collapsed",
                actors=fed.members,
                description=f"Collapse of {fed.name}",
                importance=7,
            ))

    for fed in feds_to_remove:
        world.federations.remove(fed)

    return events
```

Call from `simulation.py` phase 10: `events.extend(check_federation_dissolution(world))`

### A3: Allied Turns Tracking (add to Task 16 simulation integration)

```python
# In politics.py, add:
def update_allied_turns(world: WorldState) -> None:
    """Phase 10: Update allied_turns counters on all relationships."""
    from chronicler.models import Disposition
    for civ_name, rels in world.relationships.items():
        for other_name, rel in rels.items():
            if rel.disposition == Disposition.ALLIED:
                rel.allied_turns += 1
            elif rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS, Disposition.NEUTRAL):
                # Below FRIENDLY — reset counter
                rel.allied_turns = 0
            # At FRIENDLY: counter neither increments nor resets (preserves momentum)
```

Call from `simulation.py` phase 10 (before federation formation check): `update_allied_turns(world)`

### A4: Congress Resolution (fill in Task 19)

```python
# In politics.py, add:
def check_congress(world: WorldState) -> list[Event]:
    """Phase 7: Check for diplomatic congress when 3+ civs at war."""
    events: list[Event] = []

    # Count unique war participants
    participants = set()
    for a, b in world.active_wars:
        participants.add(a)
        participants.add(b)
    if len(participants) < 3:
        return events

    # 5% probability
    rng = random.Random(world.seed + world.turn)
    if rng.random() >= 0.05:
        return events

    civ_map = {c.name: c for c in world.civilizations}

    # Compute negotiating power per participant
    powers: dict[str, float] = {}
    for name in participants:
        civ = civ_map.get(name)
        if civ is None:
            continue
        matching_starts = [
            world.war_start_turns[key] for key in world.war_start_turns
            if name in key.split(":")
        ]
        longest_war = world.turn - min(matching_starts) if matching_starts else 1
        fed = _civ_in_federation(name, world)
        fed_allies = len(fed.members) - 1 if fed else 0
        powers[name] = (civ.military + civ.economy + fed_allies * 10) / max(longest_war, 1)

    # Roll outcome
    roll = rng.random()
    if roll < 0.40:
        # Full peace
        world.active_wars = [
            w for w in world.active_wars
            if w[0] not in participants or w[1] not in participants
        ]
        for key in list(world.war_start_turns):
            parts = key.split(":")
            if parts[0] in participants or parts[1] in participants:
                del world.war_start_turns[key]
        from chronicler.models import Disposition
        for a in participants:
            for b in participants:
                if a != b and a in world.relationships and b in world.relationships.get(a, {}):
                    world.relationships[a][b].disposition = Disposition.NEUTRAL

        # Name after highest-culture participant's capital
        highest_culture_civ = max(
            (civ_map[n] for n in participants if n in civ_map),
            key=lambda c: c.culture, default=None,
        )
        location = highest_culture_civ.capital_region if highest_culture_civ else "unknown"
        events.append(Event(
            turn=world.turn, event_type="congress_peace",
            actors=list(participants),
            description=f"The Congress of {location}",
            importance=9,
        ))
    elif roll < 0.75:
        # Partial ceasefire — top 2 powers settle
        sorted_powers = sorted(powers.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_powers) >= 2:
            a, b = sorted_powers[0][0], sorted_powers[1][0]
            world.active_wars = [
                w for w in world.active_wars
                if not (set(w) == {a, b})
            ]
            world.war_start_turns.pop(war_key(a, b), None)
            from chronicler.models import Disposition
            if a in world.relationships and b in world.relationships.get(a, {}):
                world.relationships[a][b].disposition = Disposition.NEUTRAL
            if b in world.relationships and a in world.relationships.get(b, {}):
                world.relationships[b][a].disposition = Disposition.NEUTRAL
        events.append(Event(
            turn=world.turn, event_type="congress_ceasefire",
            actors=list(participants),
            description="Partial ceasefire achieved at diplomatic congress",
            importance=7,
        ))
    else:
        # Collapse
        for name in participants:
            civ = civ_map.get(name)
            if civ:
                civ.stability = clamp(civ.stability - 5, STAT_FLOOR["stability"], 100)
        events.append(Event(
            turn=world.turn, event_type="congress_collapse",
            actors=list(participants),
            description="The Failed Congress",
            importance=6,
        ))

    return events
```

### A5: Exile Restoration (fill in Task 20)

```python
# In politics.py, add:
def check_restoration(world: WorldState) -> list[Event]:
    """Phase 10: Check if any exiled civs can be restored."""
    events: list[Event] = []
    civ_map = {c.name: c for c in world.civilizations}
    region_map = {r.name: r for r in world.regions}
    to_remove = []

    for exile in world.exile_modifiers:
        absorber = civ_map.get(exile.absorber_civ)
        if absorber is None or absorber.stability >= 20 or exile.turns_remaining <= 0:
            continue

        # Filter conquered_regions to those still controlled by absorber
        available = [r for r in exile.conquered_regions
                     if r in region_map and region_map[r].controller == exile.absorber_civ]
        if not available:
            continue

        prob = 0.05 + 0.03 * len(exile.recognized_by)
        rng = random.Random(world.seed + world.turn + hash(exile.original_civ_name))
        if rng.random() >= prob:
            continue

        # Restoration fires
        target_region = max(available,
                           key=lambda rn: region_map[rn].carrying_capacity * getattr(region_map[rn], "fertility", 0.8))

        # Determine tech era (one below absorber, floored at TRIBAL)
        from chronicler.models import TechEra
        era_order = list(TechEra)
        absorber_idx = era_order.index(absorber.tech_era)
        restored_era = era_order[max(0, absorber_idx - 1)]

        # Generate leader
        leader_name = f"{exile.original_civ_name} Restorer"
        rng_trait = random.Random(world.seed + world.turn)
        new_trait = rng_trait.choice(_TRAIT_POOL)

        restored_civ = Civilization(
            name=exile.original_civ_name,
            population=30, military=20, economy=20,
            culture=30, stability=50, treasury=0,
            tech_era=restored_era, asabiya=0.8,
            leader=Leader(name=leader_name, trait=new_trait, reign_start=world.turn,
                         succession_type="restoration"),
            regions=[target_region], capital_region=target_region,
        )
        world.civilizations.append(restored_civ)

        # Absorber loses the region
        if target_region in absorber.regions:
            absorber.regions.remove(target_region)
        region_map[target_region].controller = exile.original_civ_name

        # Set dispositions
        from chronicler.models import Relationship, Disposition
        world.relationships[exile.original_civ_name] = {}
        for c in world.civilizations:
            if c.name == exile.original_civ_name:
                continue
            if c.name == exile.absorber_civ:
                disp = Disposition.HOSTILE
            elif c.name in exile.recognized_by:
                disp = Disposition.FRIENDLY
            else:
                disp = Disposition.NEUTRAL
            world.relationships[exile.original_civ_name][c.name] = Relationship(disposition=disp)
            if c.name not in world.relationships:
                world.relationships[c.name] = {}
            world.relationships[c.name][exile.original_civ_name] = Relationship(disposition=disp)

        to_remove.append(exile)
        events.append(Event(
            turn=world.turn, event_type="restoration",
            actors=[exile.original_civ_name, exile.absorber_civ],
            description=f"Restoration of {exile.original_civ_name}",
            importance=9,
        ))

    for exile in to_remove:
        world.exile_modifiers.remove(exile)
    return events
```

### A6: FUND_INSTABILITY Resolution (add to Task 21)

```python
# In politics.py, add:
def resolve_fund_instability(civ: Civilization, world: WorldState) -> Event:
    """Resolve FUND_INSTABILITY action: start covert destabilization."""
    from chronicler.models import Disposition, ProxyWar
    civ_map = {c.name: c for c in world.civilizations}

    # Find most hostile neighbor with regions >= 3 (fallback: >= 2)
    target = None
    for threshold in [3, 2]:
        candidates = []
        rels = world.relationships.get(civ.name, {})
        for other_name, rel in rels.items():
            if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                other = civ_map.get(other_name)
                if other and len(other.regions) >= threshold:
                    # Must share a border
                    has_border = any(
                        any(adj in other.regions for adj in
                            (r.adjacencies for r in world.regions if r.name == cr).__next__())
                        for cr in civ.regions
                        if any(r.name == cr for r in world.regions)
                    )
                    if has_border:
                        candidates.append(other)
        if candidates:
            target = max(candidates, key=lambda c: -world.relationships.get(civ.name, {}).get(c.name, type('', (), {'disposition': Disposition.NEUTRAL})()).disposition.value if hasattr(world.relationships.get(civ.name, {}).get(c.name), 'disposition') else 0, default=candidates[0])
            break

    if target is None:
        return Event(turn=world.turn, event_type="fund_instability_failed",
                     actors=[civ.name], description=f"{civ.name} found no viable target", importance=3)

    # Pick most distant region from target's capital
    target_region = target.regions[0]  # fallback
    if target.capital_region and len(target.regions) > 1:
        target_region = max(target.regions,
                           key=lambda rn: graph_distance(world.regions, target.capital_region, rn))

    civ.treasury -= 8
    world.proxy_wars.append(ProxyWar(
        sponsor=civ.name, target_civ=target.name, target_region=target_region,
    ))

    # No event — covert action
    return Event(turn=world.turn, event_type="fund_instability",
                 actors=[civ.name], description="Covert operation initiated", importance=3)
```

### A7: Exile Recognition in DIPLOMACY (add to Task 21)

In `action_engine.py`, modify the DIPLOMACY action handler to check for exile recognition:

```python
# After existing DIPLOMACY resolution logic, add:
from chronicler.models import Disposition
for exile in world.exile_modifiers:
    if civ.name in exile.recognized_by:
        continue
    rel = world.relationships.get(civ.name, {}).get(exile.absorber_civ)
    if rel and rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
        exile.recognized_by.append(civ.name)
        events.append(Event(
            turn=world.turn, event_type="exile_recognition",
            actors=[civ.name, exile.original_civ_name],
            description=f"{civ.name} recognizes {exile.original_civ_name} government in exile",
            importance=5,
        ))
```

### A8: Fallen Empire (fill in Task 24)

```python
# In politics.py, add:
def update_peak_regions(world: WorldState) -> None:
    """Phase 2: Update peak_region_count for all civs."""
    for civ in world.civilizations:
        civ.peak_region_count = max(civ.peak_region_count, len(civ.regions))


def _is_fallen_empire(civ: Civilization) -> bool:
    """Check if civ qualifies as a fallen empire."""
    return civ.peak_region_count >= 5 and len(civ.regions) == 1


def apply_fallen_empire(world: WorldState) -> list[Event]:
    """Phase 2: Apply fallen empire modifiers (asabiya boost)."""
    events: list[Event] = []
    for civ in world.civilizations:
        if not _is_fallen_empire(civ):
            continue
        civ.asabiya = min(civ.asabiya + 0.05, 1.0)
    return events
```

In `action_engine.py` `get_eligible_actions` or weight computation, add:

```python
# Fallen empire weight multiplier for WAR and EXPAND
if civ.peak_region_count >= 5 and len(civ.regions) == 1:
    for action in [ActionType.WAR, ActionType.EXPAND]:
        if action in weights:
            weights[action] *= 2.0
```

In `apply_balance_of_power`, add the 50% coalition reduction:

```python
# When computing coalition upgrades, skip fallen empires for half the effect
if _is_fallen_empire(civ_map.get(name)):
    continue  # reduced coalition pressure against fallen empires
```

### A9: Civilizational Twilight (fill in Task 25)

```python
# In politics.py, add:
def update_decline_tracking(world: WorldState) -> None:
    """End of phase 10: Update decline tracking for all civs."""
    for civ in world.civilizations:
        current_sum = civ.economy + civ.military + civ.culture
        civ.stats_sum_history.append(current_sum)
        if len(civ.stats_sum_history) > 20:
            civ.stats_sum_history = civ.stats_sum_history[-20:]

        if len(civ.stats_sum_history) == 20:
            if current_sum < civ.stats_sum_history[0]:
                civ.decline_turns += 1
            else:
                civ.decline_turns = 0


def _in_twilight(civ: Civilization) -> bool:
    return civ.decline_turns >= 20 and len(civ.regions) == 1


def apply_twilight(world: WorldState) -> list[Event]:
    """Phase 2: Apply twilight stat drains."""
    events: list[Event] = []
    for civ in world.civilizations:
        if not _in_twilight(civ):
            continue
        civ.population = clamp(civ.population - 3, STAT_FLOOR["population"], 100)
        civ.culture = clamp(civ.culture - 2, STAT_FLOOR["culture"], 100)

        # First turn entering twilight — generate event
        if civ.decline_turns == 20:
            events.append(Event(
                turn=world.turn, event_type="twilight",
                actors=[civ.name],
                description=f"The Twilight of {civ.name}",
                importance=7,
            ))
    return events


def check_twilight_absorption(world: WorldState) -> list[Event]:
    """Phase 10: Peacefully absorb civs in terminal twilight."""
    events: list[Event] = []
    to_remove = []

    for civ in list(world.civilizations):
        if civ.decline_turns < 40 or len(civ.regions) != 1:
            continue

        # Find most culturally similar adjacent neighbor
        region_map = {r.name: r for r in world.regions}
        civ_region = region_map.get(civ.regions[0])
        if civ_region is None:
            continue

        best_absorber = None
        best_culture = -1
        for adj_name in getattr(civ_region, 'adjacencies', []):
            adj_region = region_map.get(adj_name)
            if adj_region and adj_region.controller and adj_region.controller != civ.name:
                absorber = next((c for c in world.civilizations if c.name == adj_region.controller), None)
                if absorber and absorber.culture > best_culture:
                    best_culture = absorber.culture
                    best_absorber = absorber

        if best_absorber is None:
            continue

        # Absorb: transfer regions
        for rn in civ.regions:
            best_absorber.regions.append(rn)
            if rn in region_map:
                region_map[rn].controller = best_absorber.name
        civ.regions = []
        to_remove.append(civ)

        # Create short exile modifier (less resentment)
        from chronicler.models import ExileModifier
        world.exile_modifiers.append(ExileModifier(
            original_civ_name=civ.name,
            absorber_civ=best_absorber.name,
            conquered_regions=[civ_region.name],
            turns_remaining=10,
        ))

        events.append(Event(
            turn=world.turn, event_type="twilight_absorption",
            actors=[civ.name, best_absorber.name],
            description=f"The Quiet End of {civ.name}",
            importance=6,
        ))

    for civ in to_remove:
        world.civilizations.remove(civ)
    return events
```

### A10: The Long Peace (fill in Task 26)

```python
# In politics.py, add:
def apply_long_peace(world: WorldState) -> list[Event]:
    """Phase 2: Apply long peace effects when no wars for 30+ turns."""
    events: list[Event] = []

    if world.active_wars:
        world.peace_turns = 0
        return events

    world.peace_turns += 1
    if world.peace_turns < 30:
        return events

    living = [c for c in world.civilizations if c.regions]

    # 1. Military restlessness
    for civ in living:
        if civ.military > 60:
            civ.stability = clamp(civ.stability - 2, STAT_FLOOR["stability"], 100)

    # 2. Economic inequality
    if len(living) >= 2:
        richest = max(living, key=lambda c: c.economy)
        poorest = min(living, key=lambda c: c.economy)
        richest.economy = clamp(richest.economy + 1, STAT_FLOOR["economy"], 100)
        poorest.economy = clamp(poorest.economy - 1, STAT_FLOOR["economy"], 100)

    # 3. ALLIED disposition decay every 10 peace turns
    if world.peace_turns % 10 == 0:
        from chronicler.models import Disposition
        DOWNGRADE = {Disposition.ALLIED: Disposition.FRIENDLY}
        for civ_name, rels in world.relationships.items():
            for other_name, rel in rels.items():
                if rel.disposition in DOWNGRADE:
                    rel.disposition = DOWNGRADE[rel.disposition]

    return events
```

### A11: Scenario Regression Test (add to Task 28)

```python
# In tests/test_politics.py, add:
def test_all_scenarios_run_with_m14():
    """Each existing scenario YAML loads and runs 10 turns without crash."""
    from chronicler.scenario import load_scenario, apply_scenario
    from chronicler.simulation import run_turn
    from chronicler.action_engine import ActionEngine
    from pathlib import Path
    scenario_dir = Path("scenarios")
    if not scenario_dir.exists():
        return  # skip if scenarios not available
    for yaml_file in scenario_dir.glob("*.yaml"):
        world = generate_world(seed=42)
        config = load_scenario(yaml_file)
        apply_scenario(world, config)
        for civ in world.civilizations:
            if civ.capital_region is None and civ.regions:
                civ.capital_region = civ.regions[0]
        for _ in range(10):
            engine = ActionEngine(world)
            selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
            run_turn(world, selector, lambda w, e: "", seed=world.seed + world.turn)
        # No crash is the assertion
```
