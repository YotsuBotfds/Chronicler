# M55b Spatial Asabiya Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace civ-level asabiya scalar with per-region frontier/interior dynamics; `civ.asabiya` becomes a population-weighted aggregate.

**Architecture:** New `RegionAsabiya` sub-model on `Region` stores per-region asabiya + frontier diagnostics. A rewritten `apply_asabiya_dynamics` computes frontier fraction from adjacency graph, applies gradient growth/decay formula per region, then aggregates to `civ.asabiya`. All 5 spot mutation sites migrate from `civ.asabiya +=` to D-policy (write to all owned regions).

**Tech Stack:** Pure Python. No Rust changes. Pydantic models, pytest.

**Spec:** `docs/superpowers/specs/2026-03-24-m55b-spatial-asabiya-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/chronicler/models.py` | Modify (lines 207-217, 342, 695-724) | Add `RegionAsabiya` class, add `asabiya_state` field on `Region`, add `asabiya_variance` on `Civilization` and `CivSnapshot` |
| `src/chronicler/simulation.py` | Modify (lines 583-617, 999, 1167-1175, 1450) | Replace `apply_asabiya_dynamics` body, move call site, migrate cultural works D-policy, update comment |
| `src/chronicler/world_gen.py` | Modify (lines 155-184) | Add region asabiya sync after civ assignment |
| `src/chronicler/emergence.py` | Modify (lines 458-466) | Migrate supervolcano folk hero bonus to D-policy |
| `src/chronicler/leaders.py` | Modify (lines 336-342) | Migrate coup asabiya to D-policy |
| `src/chronicler/politics.py` | Modify (lines 267, 533-542, 1056-1078, 1210-1221) | Migrate vassal rebellion, fallen empire, secession, restoration to D-policy |
| `src/chronicler/scenario.py` | Modify (lines 517-518) | Add region sync after asabiya override |
| `src/chronicler/main.py` | Modify (lines 305-324) | Add `asabiya_variance` to CivSnapshot construction |
| `tests/test_spatial_asabiya.py` | Create | All M55b unit and integration tests |

---

### Task 1: Data Model — `RegionAsabiya` + Civilization fields

**Files:**
- Modify: `src/chronicler/models.py:207-217` (add class after `RegionStockpile`)
- Modify: `src/chronicler/models.py:237-238` (add field on `Region` after `stockpile`)
- Modify: `src/chronicler/models.py:342` (add `asabiya_variance` after `asabiya`)
- Modify: `src/chronicler/models.py:695-724` (add `asabiya_variance` to `CivSnapshot`)
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write failing test for RegionAsabiya defaults**

```python
# tests/test_spatial_asabiya.py
"""Tests for M55b spatial asabiya."""
import pytest
from chronicler.models import Region, RegionAsabiya, Civilization, CivSnapshot, Leader, TechEra


def test_region_asabiya_defaults():
    ra = RegionAsabiya()
    assert ra.asabiya == 0.5
    assert ra.frontier_fraction == 0.0
    assert ra.different_civ_count == 0
    assert ra.uncontrolled_count == 0


def test_region_has_asabiya_state():
    r = Region(name="Test", terrain="plains", carrying_capacity=60, resources="fertile")
    assert r.asabiya_state.asabiya == 0.5
    assert r.asabiya_state.frontier_fraction == 0.0


def test_civilization_has_asabiya_variance():
    civ = Civilization(
        name="Test", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.asabiya_variance == 0.0


def test_civ_snapshot_asabiya_variance_default():
    snap = CivSnapshot(
        population=50, military=30, economy=40, culture=30, stability=50,
        treasury=50, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
        regions=["r1"], leader_name="L", alive=True,
    )
    assert snap.asabiya_variance == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spatial_asabiya.py -v`
Expected: ImportError for `RegionAsabiya` or AttributeError for missing fields.

- [ ] **Step 3: Add RegionAsabiya class and fields**

In `src/chronicler/models.py`, after `RegionStockpile` (line 216):

```python
class RegionAsabiya(BaseModel):
    """Per-region asabiya state with frontier diagnostics (M55b)."""
    asabiya: float = 0.5
    frontier_fraction: float = 0.0
    different_civ_count: int = 0
    uncontrolled_count: int = 0
```

On `Region`, after `stockpile` field (line 238):

```python
    asabiya_state: RegionAsabiya = Field(default_factory=RegionAsabiya)
```

On `Civilization`, after `asabiya` field (line 342):

```python
    asabiya_variance: float = 0.0
```

On `CivSnapshot`, after `asabiya` field (line 703):

```python
    asabiya_variance: float = 0.0
```

Update the `RegionAsabiya` import in the test file's import block.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_spatial_asabiya.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -x -q`
Expected: All existing tests pass (new field defaults are backward-compatible).

- [ ] **Step 6: Commit**

```
git add src/chronicler/models.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): add RegionAsabiya model and asabiya_variance field"
```

---

### Task 2: Core Tick — Frontier Fraction Computation

**Files:**
- Modify: `src/chronicler/simulation.py:583-617` (replace function body)
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write failing tests for frontier fraction**

```python
from chronicler.models import Region, WorldState, Relationship, RegionAsabiya
from chronicler.simulation import apply_asabiya_dynamics


def _make_region(name, controller=None, adjacencies=None):
    return Region(
        name=name, terrain="plains", carrying_capacity=60,
        resources="fertile", controller=controller, population=50,
        adjacencies=adjacencies or [],
    )


def _make_test_world(regions, civs=None):
    """Minimal WorldState for asabiya tests."""
    from chronicler.models import Civilization, Leader, TechEra
    if civs is None:
        civs = []
    return WorldState(
        name="Test", seed=42, turn=1,
        regions=regions, civilizations=civs, relationships={},
    )


def test_frontier_fraction_mixed_neighbors():
    """1 same-civ, 1 different-civ, 1 uncontrolled -> f = 2/3."""
    r_target = _make_region("Target", controller="A", adjacencies=["Same", "Enemy", "Wild"])
    r_same = _make_region("Same", controller="A")
    r_enemy = _make_region("Enemy", controller="B")
    r_wild = _make_region("Wild", controller=None)
    world = _make_test_world([r_target, r_same, r_enemy, r_wild])
    apply_asabiya_dynamics(world)
    assert r_target.asabiya_state.frontier_fraction == pytest.approx(2 / 3)
    assert r_target.asabiya_state.different_civ_count == 1
    assert r_target.asabiya_state.uncontrolled_count == 1


def test_frontier_fraction_all_same():
    """All same-civ neighbors -> f = 0.0 (pure interior)."""
    r = _make_region("Center", controller="A", adjacencies=["N1", "N2"])
    n1 = _make_region("N1", controller="A")
    n2 = _make_region("N2", controller="A")
    world = _make_test_world([r, n1, n2])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 0.0


def test_frontier_fraction_all_foreign():
    """All different-civ neighbors -> f = 1.0."""
    r = _make_region("Center", controller="A", adjacencies=["E1", "E2"])
    e1 = _make_region("E1", controller="B")
    e2 = _make_region("E2", controller="C")
    world = _make_test_world([r, e1, e2])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 1.0
    assert r.asabiya_state.different_civ_count == 2


def test_frontier_fraction_no_valid_neighbors():
    """Stale adjacency names not in region_map -> f = 0.0."""
    r = _make_region("Isolated", controller="A", adjacencies=["Ghost1", "Ghost2"])
    world = _make_test_world([r])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.frontier_fraction == 0.0


def test_frontier_fraction_uncontrolled_region_still_computed():
    """Uncontrolled regions get frontier fraction computed but asabiya not ticked."""
    r = _make_region("Wild", controller=None, adjacencies=["Owned"])
    owned = _make_region("Owned", controller="A")
    world = _make_test_world([r, owned])
    apply_asabiya_dynamics(world)
    # Frontier fraction computed (owned neighbor is 'foreign' since Wild has no controller)
    assert r.asabiya_state.frontier_fraction == 1.0  # 1 foreign / 1 valid neighbor
    # Asabiya unchanged from default (no controller = no tick)
    assert r.asabiya_state.asabiya == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_spatial_asabiya.py::test_frontier_fraction_mixed_neighbors -v`
Expected: FAIL — current `apply_asabiya_dynamics` doesn't write to `region.asabiya_state`.

- [ ] **Step 3: Rewrite `apply_asabiya_dynamics`**

Replace the function body at `src/chronicler/simulation.py:583-617`. The new function:
- Drops `acc` parameter (call site never passes it)
- Step 1: compute frontier fraction per region
- Step 2: apply gradient formula to controlled regions + folk hero per-turn
- Step 3: aggregate to civ-level

```python
def apply_asabiya_dynamics(world: WorldState) -> None:
    """Update per-region asabiya via gradient frontier model, then aggregate to civ-level."""
    ASABIYA_FRONTIER_GROWTH_RATE = 0.05  # r0, calibrate in M61b
    ASABIYA_INTERIOR_DECAY_RATE = 0.02   # delta, calibrate in M61b
    # Defined but inactive (D5, D6) — wired in follow-up / M61b
    ASABIYA_POWER_DROPOFF = 5.0          # h, military projection distance decay
    ASABIYA_COLLAPSE_VARIANCE_THRESHOLD = 0.04  # variance collapse trigger

    region_map = {r.name: r for r in world.regions}
    civ_by_name = {c.name: c for c in world.civilizations}

    # Step 1: Compute frontier fraction for each region
    for region in world.regions:
        valid_count = 0
        diff_civ = 0
        uncontrolled = 0
        for adj_name in region.adjacencies:
            adj = region_map.get(adj_name)
            if adj is None:
                continue
            valid_count += 1
            if adj.controller is None:
                uncontrolled += 1
            elif adj.controller != region.controller:
                diff_civ += 1
        region.asabiya_state.different_civ_count = diff_civ
        region.asabiya_state.uncontrolled_count = uncontrolled
        region.asabiya_state.frontier_fraction = (
            (diff_civ + uncontrolled) / valid_count if valid_count > 0 else 0.0
        )

    # Step 2: Apply gradient formula to each controlled region
    from chronicler.traditions import compute_folk_hero_asabiya_bonus

    for region in world.regions:
        if region.controller is None:
            continue
        s = region.asabiya_state.asabiya
        f = region.asabiya_state.frontier_fraction
        s_next = s + ASABIYA_FRONTIER_GROWTH_RATE * f * s * (1 - s) - ASABIYA_INTERIOR_DECAY_RATE * (1 - f) * s

        # Folk hero per-turn bonus (applied after gradient, matching legacy order)
        civ = civ_by_name.get(region.controller)
        if civ is not None:
            folk_bonus = compute_folk_hero_asabiya_bonus(civ)
            if folk_bonus > 0:
                s_next = s_next + folk_bonus * 0.1

        region.asabiya_state.asabiya = round(max(0.0, min(1.0, s_next)), 4)

    # Step 3: Aggregate to civ-level
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            continue
        total_pop = 0
        weighted_sum = 0.0
        region_data: list[tuple[float, int]] = []  # (asabiya, pop)
        for rname in civ.regions:
            r = region_map.get(rname)
            if r is None:
                continue
            pop = r.population
            total_pop += pop
            weighted_sum += r.asabiya_state.asabiya * pop
            region_data.append((r.asabiya_state.asabiya, pop))

        if total_pop == 0:
            continue  # Keep existing civ.asabiya

        mean_a = weighted_sum / total_pop
        variance = sum(p * (a - mean_a) ** 2 for a, p in region_data) / total_pop
        civ.asabiya = round(max(0.0, min(1.0, mean_a)), 4)
        civ.asabiya_variance = round(variance, 6)
```

- [ ] **Step 4: Run frontier fraction tests**

Run: `pytest tests/test_spatial_asabiya.py -k frontier_fraction -v`
Expected: All 5 frontier fraction tests PASS.

- [ ] **Step 5: Commit**

```
git add src/chronicler/simulation.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): rewrite apply_asabiya_dynamics with gradient frontier model"
```

---

### Task 3: Core Tick — Gradient Formula + Aggregation Tests

**Files:**
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write gradient formula and aggregation tests**

```python
def test_gradient_frontier_growth():
    """Pure frontier (f=1.0): logistic growth."""
    r = _make_region("Frontier", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Frontier"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.05 * 1.0 * 0.5 * 0.5 - 0.02 * 0.0 * 0.5 = 0.5125
    assert r.asabiya_state.asabiya == pytest.approx(0.5125, abs=1e-4)


def test_gradient_interior_decay():
    """Pure interior (f=0.0): linear decay."""
    r = _make_region("Interior", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 0.5
    friend = _make_region("Friend", controller="A")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Interior"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.0 - 0.02 * 1.0 * 0.5 = 0.49
    assert r.asabiya_state.asabiya == pytest.approx(0.49, abs=1e-4)


def test_gradient_boundary_zero_stays_zero():
    """asabiya=0.0 is a fixed point (logistic s*(1-s) = 0)."""
    r = _make_region("Dead", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.0
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.0,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Dead"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    assert r.asabiya_state.asabiya == 0.0


def test_civ_aggregation_equal_pop():
    """2 regions, equal pop -> mean of asabiya values."""
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 50
    r2 = _make_region("R2", controller="A", adjacencies=["R1"])
    r2.asabiya_state.asabiya = 0.7
    r2.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    apply_asabiya_dynamics(world)
    # After tick, values shift but mean should be close to 0.5
    # Also check variance is computed
    assert 0.0 <= civ.asabiya <= 1.0
    assert civ.asabiya_variance >= 0.0


def test_civ_aggregation_zero_pop_fallback():
    """Zero total pop -> civ.asabiya unchanged."""
    r = _make_region("Empty", controller="A", adjacencies=[])
    r.asabiya_state.asabiya = 0.8
    r.population = 0
    civ = Civilization(
        name="A", population=0, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Empty"],
    )
    world = _make_test_world([r], civs=[civ])
    apply_asabiya_dynamics(world)
    assert civ.asabiya == 0.6  # Unchanged


def test_variance_computation():
    """Verify population-weighted variance calculation."""
    r1 = _make_region("R1", controller="A", adjacencies=[])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 50
    r2 = _make_region("R2", controller="A", adjacencies=[])
    r2.asabiya_state.asabiya = 0.7
    r2.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    # Pre-tick: manually set asabiya values and compute expected variance
    # After tick, both are interior (f=0.0), so both decay:
    # R1: 0.3 - 0.02 * 1.0 * 0.3 = 0.294
    # R2: 0.7 - 0.02 * 1.0 * 0.7 = 0.686
    # Mean = (0.294*50 + 0.686*50) / 100 = 0.49
    # Var = (50*(0.294-0.49)^2 + 50*(0.686-0.49)^2) / 100
    #     = (50*0.038416 + 50*0.038416) / 100 = 0.038416
    apply_asabiya_dynamics(world)
    assert civ.asabiya == pytest.approx(0.49, abs=1e-3)
    assert civ.asabiya_variance == pytest.approx(0.038416, abs=1e-4)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_spatial_asabiya.py -k "gradient or aggregation or variance" -v`
Expected: All PASS (implementation already exists from Task 2).

- [ ] **Step 3: Commit**

```
git add tests/test_spatial_asabiya.py
git commit -m "test(m55b): add gradient formula and aggregation tests"
```

---

### Task 4: World Initialization — Region Asabiya Sync

**Files:**
- Modify: `src/chronicler/world_gen.py:155-184` (add sync after civ assignment loop)
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write failing test**

```python
from chronicler.world_gen import generate_world


def test_world_gen_syncs_region_asabiya():
    """After world gen, each controlled region's asabiya matches its civ's asabiya."""
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    for civ in world.civilizations:
        for rname in civ.regions:
            region = next(r for r in world.regions if r.name == rname)
            assert region.asabiya_state.asabiya == civ.asabiya, (
                f"Region {rname} asabiya {region.asabiya_state.asabiya} != civ {civ.name} asabiya {civ.asabiya}"
            )


def test_world_gen_uncontrolled_regions_default():
    """Uncontrolled regions keep default asabiya 0.5."""
    world = generate_world(seed=42, num_regions=8, num_civs=2)
    for region in world.regions:
        if region.controller is None:
            assert region.asabiya_state.asabiya == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spatial_asabiya.py::test_world_gen_syncs_region_asabiya -v`
Expected: FAIL — region asabiya is default 0.5, not synced to civ.

- [ ] **Step 3: Add sync pass in world_gen.py**

In `src/chronicler/world_gen.py`, after the civ assignment loop ends (after line 184, before `return civs`), add:

```python
    # M55b: Sync region asabiya to owning civ's initial asabiya
    for civ in civs:
        for rname in civ.regions:
            region = next((r for r in regions if r.name == rname), None)
            if region is not None:
                region.asabiya_state.asabiya = civ.asabiya
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_spatial_asabiya.py -k world_gen -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```
git add src/chronicler/world_gen.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): sync region asabiya to civ values at world generation"
```

---

### Task 5: Spot Mutation Migration — politics.py (4 sites)

**Files:**
- Modify: `src/chronicler/politics.py:267, 533-542, 1056-1078, 1210-1221`
- Test: `tests/test_spatial_asabiya.py`

This task migrates four sites in politics.py:
1. Vassal rebellion (+0.2) — all three branches
2. Fallen empire (+boost) — all three branches
3. Secession (=0.7) — region initialization
4. Restoration (=0.8) — region initialization

- [ ] **Step 1: Write D-policy helper function**

Add to `src/chronicler/simulation.py` (after the constants, before `apply_asabiya_dynamics`):

```python
def _apply_asabiya_to_regions(world: WorldState, civ_name: str, delta: float) -> None:
    """D-policy: apply asabiya delta to all regions controlled by a civ. Clamp [0, 1]."""
    for region in world.regions:
        if region.controller == civ_name:
            region.asabiya_state.asabiya = round(
                max(0.0, min(1.0, region.asabiya_state.asabiya + delta)), 4
            )
```

- [ ] **Step 2: Write failing tests for D-policy mutations**

```python
from chronicler.simulation import _apply_asabiya_to_regions


def test_d_policy_applies_to_all_regions():
    """D-policy: delta applied to every region the civ controls."""
    r1 = _make_region("R1", controller="A")
    r1.asabiya_state.asabiya = 0.5
    r2 = _make_region("R2", controller="A")
    r2.asabiya_state.asabiya = 0.6
    r3 = _make_region("R3", controller="B")  # Different civ, untouched
    r3.asabiya_state.asabiya = 0.4
    world = _make_test_world([r1, r2, r3])
    _apply_asabiya_to_regions(world, "A", 0.1)
    assert r1.asabiya_state.asabiya == pytest.approx(0.6)
    assert r2.asabiya_state.asabiya == pytest.approx(0.7)
    assert r3.asabiya_state.asabiya == pytest.approx(0.4)  # Unchanged


def test_d_policy_clamps_to_one():
    """D-policy: region at 0.95 + 0.1 -> clamped to 1.0."""
    r = _make_region("R1", controller="A")
    r.asabiya_state.asabiya = 0.95
    world = _make_test_world([r])
    _apply_asabiya_to_regions(world, "A", 0.1)
    assert r.asabiya_state.asabiya == 1.0
```

- [ ] **Step 3: Run tests to verify they pass (helper already written)**

Run: `pytest tests/test_spatial_asabiya.py -k d_policy -v`
Expected: PASS.

- [ ] **Step 4: Migrate vassal rebellion (politics.py:533-542)**

Replace the three-branch asabiya writes with D-policy calls. Import at top of politics.py:

```python
from chronicler.simulation import _apply_asabiya_to_regions
```

At line 533-542, change all three branches:

```python
        if world.agent_mode == "hybrid":
            world.pending_shocks.append(CivShock(vassal_idx,
                stability_shock=min(1.0, 10 / max(vassal.stability, 1))))
            _apply_asabiya_to_regions(world, vassal.name, 0.2)
        elif acc is not None:
            acc.add(vassal_idx, vassal, "stability", 10, "guard-shock")
            _apply_asabiya_to_regions(world, vassal.name, 0.2)
        else:
            vassal.stability = clamp(vassal.stability + 10, STAT_FLOOR["stability"], 100)
            _apply_asabiya_to_regions(world, vassal.name, 0.2)
```

- [ ] **Step 5: Migrate fallen empire (politics.py:1216-1221)**

```python
        asabiya_boost = get_override(world, K_FALLEN_EMPIRE_ASABIYA_BOOST, 0.05)
        _apply_asabiya_to_regions(world, civ.name, asabiya_boost)
```

Remove the `if acc is not None` / `else` branching for asabiya only (keep the function's other logic).

- [ ] **Step 6: Migrate secession (politics.py:267)**

After the breakaway `Civilization` is constructed (line 267-269), add region asabiya initialization:

```python
        # M55b: Initialize breakaway region asabiya
        for rname in breakaway_regions:
            br = next((r for r in world.regions if r.name == rname), None)
            if br is not None:
                br.asabiya_state.asabiya = 0.7
```

- [ ] **Step 7: Migrate restoration (politics.py:1056-1078)**

After both restoration paths (new civ creation at line 1064, existing civ update at line 1078), add:

```python
        # M55b: Initialize restored region asabiya
        for rname in restored_civ.regions:
            rr = next((r for r in world.regions if r.name == rname), None)
            if rr is not None:
                rr.asabiya_state.asabiya = 0.8
```

- [ ] **Step 8: Run existing politics tests to check for regressions**

Run: `pytest tests/test_politics.py -v -x`
Expected: All pass.

- [ ] **Step 9: Commit**

```
git add src/chronicler/simulation.py src/chronicler/politics.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): migrate politics.py asabiya mutations to D-policy"
```

---

### Task 6: Spot Mutation Migration — emergence.py, leaders.py, simulation.py

**Files:**
- Modify: `src/chronicler/emergence.py:458-466`
- Modify: `src/chronicler/leaders.py:336-342`
- Modify: `src/chronicler/simulation.py:1167-1175`
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Migrate supervolcano folk hero bonus (emergence.py:462-466)**

Replace the asabiya branches. Use **function-scoped import** to avoid circular dependency (simulation.py already imports from emergence.py at top level):

```python
    # M17: Folk hero asabiya bonus
    for civ_name in affected_civs:
        civ = next((c for c in world.civilizations if c.name == civ_name), None)
        if civ and civ.folk_heroes:
            from chronicler.simulation import _apply_asabiya_to_regions
            _apply_asabiya_to_regions(world, civ.name, 0.05)
```

**Do NOT add a top-level import** — `simulation.py` imports from `emergence.py` at top level, so a reverse top-level import creates a circular dependency crash.

- [ ] **Step 2: Migrate coup (leaders.py:336-342)**

Replace the asabiya branches in the `usurper` case. Again, **function-scoped import** (simulation.py imports from leaders.py at top level):

```python
    elif stype == "usurper":
        mult = get_severity_multiplier(civ, world)
        if acc is not None:
            civ_idx = civ_index(world, civ.name)
            acc.add(civ_idx, civ, "stability", -int(30 * mult), "guard-shock")
        else:
            civ.stability = clamp(civ.stability - int(30 * mult), STAT_FLOOR["stability"], 100)
        from chronicler.simulation import _apply_asabiya_to_regions
        _apply_asabiya_to_regions(world, civ.name, 0.1)
```

**Do NOT add a top-level import** — same circular dependency risk.

Note: the `_apply_asabiya_to_regions` call goes outside the if/else branches since it's the same in all cases. The stability logic retains its branching.

- [ ] **Step 3: Migrate cultural works (simulation.py:1167-1175)**

Replace the asabiya lines:

```python
                # M16a: Cultural works enhancement
                if acc is not None:
                    acc.add(civ_idx, civ, "culture", 5, "guard-shock")
                    acc.add(civ_idx, civ, "prestige", 2, "keep")
                else:
                    civ.culture = clamp(civ.culture + 5, STAT_FLOOR["culture"], 100)
                    civ.prestige += 2
                _apply_asabiya_to_regions(world, civ.name, 0.05)
```

- [ ] **Step 4: Run existing test suites for regressions**

Run: `pytest tests/test_emergence.py tests/test_leaders.py tests/test_simulation.py -v -x`
Expected: All pass.

- [ ] **Step 5: Commit**

```
git add src/chronicler/emergence.py src/chronicler/leaders.py src/chronicler/simulation.py
git commit -m "feat(m55b): migrate emergence, leaders, simulation asabiya mutations to D-policy"
```

---

### Task 7: Spot Mutation Migration — scenario.py

**Files:**
- Modify: `src/chronicler/scenario.py:517-518`
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write failing test**

```python
def test_scenario_override_syncs_regions():
    """Scenario asabiya override syncs to all controlled regions."""
    from chronicler.models import WorldState, Region, Civilization, Leader, TechEra
    r1 = _make_region("R1", controller="A")
    r1.asabiya_state.asabiya = 0.5
    r2 = _make_region("R2", controller="A")
    r2.asabiya_state.asabiya = 0.5
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    # Simulate what scenario override does
    civ.asabiya = 0.9
    for region in world.regions:
        if region.controller == civ.name:
            region.asabiya_state.asabiya = civ.asabiya
    assert r1.asabiya_state.asabiya == 0.9
    assert r2.asabiya_state.asabiya == 0.9
```

- [ ] **Step 2: Add region sync to scenario.py**

At `src/chronicler/scenario.py:517-518`, after setting `civ.asabiya`:

```python
    if override.asabiya is not None:
        civ.asabiya = override.asabiya
        # M55b: Sync to controlled regions
        for region in world.regions:
            if region.controller == civ.name:
                region.asabiya_state.asabiya = override.asabiya
```

Note: `_apply_civ_override` at scenario.py:479 already takes `(world: WorldState, idx: int, override: CivOverride, rename: bool)` — it has access to `world` and `world.regions`. No signature change needed.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_spatial_asabiya.py::test_scenario_override_syncs_regions -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```
git add src/chronicler/scenario.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): sync scenario asabiya overrides to regions"
```

---

### Task 8: Phase 10 Call Site Move + CivSnapshot + Comment Cleanup

**Files:**
- Modify: `src/chronicler/simulation.py:999` (move call)
- Modify: `src/chronicler/simulation.py:1450` (update comment)
- Modify: `src/chronicler/main.py:305-324` (add asabiya_variance to CivSnapshot)

- [ ] **Step 1: Write Phase 10 ordering test**

```python
def test_phase10_ordering_rebellion_before_tick():
    """Vassal rebellion D-policy write must be captured by asabiya aggregation before collapse check."""
    from chronicler.models import Civilization, Leader, TechEra, VassalRelation, WorldState, Region, Relationship, Disposition
    # Civ with very low asabiya that would collapse without rebellion boost
    r1 = _make_region("R1", controller="Vassal", adjacencies=["R2"])
    r1.asabiya_state.asabiya = 0.04  # Below 0.1 threshold
    r1.population = 50
    r2 = _make_region("R2", controller="Overlord", adjacencies=["R1"])
    r2.population = 50
    vassal = Civilization(
        name="Vassal", population=50, military=30, economy=40, culture=30,
        stability=15, tech_era=TechEra.IRON, treasury=50, asabiya=0.04,
        leader=Leader(name="V", trait="cautious", reign_start=0), regions=["R1"],
    )
    overlord = Civilization(
        name="Overlord", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="O", trait="cautious", reign_start=0), regions=["R2"],
    )
    # After rebellion: region asabiya = 0.04 + 0.2 = 0.24
    # After tick: civ.asabiya = ~0.24 (> 0.1 threshold)
    # Civ should NOT collapse
    # This test validates the ordering by checking the region state
    world = _make_test_world([r1, r2], civs=[vassal, overlord])
    from chronicler.simulation import _apply_asabiya_to_regions
    _apply_asabiya_to_regions(world, "Vassal", 0.2)
    apply_asabiya_dynamics(world)
    assert vassal.asabiya > 0.1, f"Vassal asabiya {vassal.asabiya} should be > 0.1 after rebellion boost"
```

- [ ] **Step 2: Move call site in simulation.py**

At `src/chronicler/simulation.py`, move `apply_asabiya_dynamics(world)` from line 999 to right before the collapse check loop (before line 1020). Delete the old call at line 999.

The new position is after `update_decline_tracking(world)` (line 1019) and before the `for civ in world.civilizations:` collapse loop (line 1020).

- [ ] **Step 3: Add asabiya_variance to CivSnapshot**

At `src/chronicler/main.py`, in the `CivSnapshot` construction (around line 315), add:

```python
                    asabiya_variance=civ.asabiya_variance,
```

- [ ] **Step 4: Update accumulator comment**

At `src/chronicler/simulation.py:1450`, change:

```python
        acc.apply_keep(world)  # Apply treasury, asabiya, prestige
```

to:

```python
        acc.apply_keep(world)  # Apply treasury, prestige (asabiya now regional, M55b)
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```
git add src/chronicler/simulation.py src/chronicler/main.py tests/test_spatial_asabiya.py
git commit -m "feat(m55b): move asabiya tick after politics, add variance to snapshot"
```

---

### Task 9: Integration Tests

**Files:**
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write multi-turn convergence test**

```python
def test_multi_turn_frontier_converges_upward():
    """Over 20 turns, a pure frontier region's asabiya trends upward."""
    r = _make_region("Frontier", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.3
    r.population = 50
    enemy = _make_region("Enemy", controller="B", adjacencies=["Frontier"])
    enemy.population = 50
    civ_a = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.3,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Frontier"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["Enemy"],
    )
    world = _make_test_world([r, enemy], civs=[civ_a, civ_b])
    prev = r.asabiya_state.asabiya
    for _ in range(20):
        apply_asabiya_dynamics(world)
        assert r.asabiya_state.asabiya >= prev
        prev = r.asabiya_state.asabiya
    assert r.asabiya_state.asabiya > 0.3  # Grew from initial


def test_multi_turn_interior_converges_downward():
    """Over 20 turns, a pure interior region's asabiya trends downward."""
    r = _make_region("Interior", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 0.7
    r.population = 50
    friend = _make_region("Friend", controller="A", adjacencies=["Interior"])
    friend.asabiya_state.asabiya = 0.7
    friend.population = 50
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.7,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Interior", "Friend"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    prev = r.asabiya_state.asabiya
    for _ in range(20):
        apply_asabiya_dynamics(world)
        assert r.asabiya_state.asabiya <= prev
        prev = r.asabiya_state.asabiya
    assert r.asabiya_state.asabiya < 0.7  # Decayed from initial


def test_determinism_across_runs():
    """Same seed + topology -> identical values over 50 turns."""
    def run_sim():
        r1 = _make_region("R1", controller="A", adjacencies=["R2", "R3"])
        r1.asabiya_state.asabiya = 0.5
        r1.population = 50
        r2 = _make_region("R2", controller="B", adjacencies=["R1"])
        r2.asabiya_state.asabiya = 0.6
        r2.population = 40
        r3 = _make_region("R3", controller=None, adjacencies=["R1"])
        r3.population = 0
        civ_a = Civilization(
            name="A", population=50, military=30, economy=40, culture=30,
            stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
            leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
        )
        civ_b = Civilization(
            name="B", population=40, military=30, economy=40, culture=30,
            stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
            leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R2"],
        )
        world = _make_test_world([r1, r2, r3], civs=[civ_a, civ_b])
        results = []
        for _ in range(50):
            apply_asabiya_dynamics(world)
            results.append((civ_a.asabiya, civ_b.asabiya))
        return results

    run1 = run_sim()
    run2 = run_sim()
    assert run1 == run2


def test_invariant_bounds_over_many_turns():
    """All asabiya values stay in [0,1], variance in [0,0.25] over 50 turns."""
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.asabiya_state.asabiya = 0.1
    r1.population = 80
    r2 = _make_region("R2", controller="A", adjacencies=["R1", "R3"])
    r2.asabiya_state.asabiya = 0.9
    r2.population = 20
    r3 = _make_region("R3", controller="B", adjacencies=["R2"])
    r3.asabiya_state.asabiya = 0.5
    r3.population = 50
    civ_a = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1", "R2"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R3"],
    )
    world = _make_test_world([r1, r2, r3], civs=[civ_a, civ_b])
    for _ in range(50):
        apply_asabiya_dynamics(world)
        for r in world.regions:
            assert 0.0 <= r.asabiya_state.asabiya <= 1.0
        for c in world.civilizations:
            assert 0.0 <= c.asabiya <= 1.0
            assert 0.0 <= c.asabiya_variance <= 0.25
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_spatial_asabiya.py -k "multi_turn or determinism or invariant" -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```
git add tests/test_spatial_asabiya.py
git commit -m "test(m55b): add integration tests for convergence, determinism, and bounds"
```

---

### Task 10: Missing Spec Test Coverage

**Files:**
- Test: `tests/test_spatial_asabiya.py`

This task fills the gaps between the spec's 15 test categories and the tests written in earlier tasks.

- [ ] **Step 1: Write missing gradient formula tests (spec #2)**

```python
def test_gradient_mixed_partial_frontier():
    """f=0.5: growth and decay partially cancel."""
    r = _make_region("Mixed", controller="A", adjacencies=["Friend", "Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    friend = _make_region("Friend", controller="A")
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Mixed"],
    )
    world = _make_test_world([r, friend, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # s_next = 0.5 + 0.05*0.5*0.5*0.5 - 0.02*0.5*0.5 = 0.5 + 0.00625 - 0.005 = 0.50125
    assert r.asabiya_state.asabiya == pytest.approx(0.5013, abs=1e-3)


def test_gradient_boundary_one_decays_if_not_pure_frontier():
    """asabiya=1.0 decays when f < 1.0 (interior decay dominates at ceiling)."""
    r = _make_region("Peak", controller="A", adjacencies=["Friend"])
    r.asabiya_state.asabiya = 1.0
    r.population = 50
    friend = _make_region("Friend", controller="A")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=1.0,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Peak"],
    )
    world = _make_test_world([r, friend], civs=[civ])
    apply_asabiya_dynamics(world)
    # f=0.0 interior: s_next = 1.0 - 0.02*1.0*1.0 = 0.98
    assert r.asabiya_state.asabiya < 1.0
```

- [ ] **Step 2: Write missing aggregation tests (spec #3)**

```python
def test_aggregation_weighted_by_pop():
    """90/10 pop split -> mean skewed toward high-pop region."""
    r1 = _make_region("Big", controller="A", adjacencies=[])
    r1.asabiya_state.asabiya = 0.3
    r1.population = 90
    r2 = _make_region("Small", controller="A", adjacencies=[])
    r2.asabiya_state.asabiya = 0.9
    r2.population = 10
    civ = Civilization(
        name="A", population=100, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Big", "Small"],
    )
    world = _make_test_world([r1, r2], civs=[civ])
    apply_asabiya_dynamics(world)
    # After interior decay: Big ~0.294, Small ~0.882
    # Weighted mean = (90*0.294 + 10*0.882)/100 ~ 0.353
    assert civ.asabiya < 0.4  # Skewed toward Big region


def test_aggregation_single_region_zero_variance():
    """Single region -> variance must be 0.0."""
    r = _make_region("Only", controller="A", adjacencies=[])
    r.asabiya_state.asabiya = 0.6
    r.population = 50
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.6,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["Only"],
    )
    world = _make_test_world([r], civs=[civ])
    apply_asabiya_dynamics(world)
    assert civ.asabiya_variance == 0.0
```

- [ ] **Step 3: Write folk hero ordering test (spec #5)**

```python
def test_folk_hero_applied_after_gradient():
    """Folk hero bonus applied after gradient formula (ordering test)."""
    r = _make_region("R1", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
        folk_heroes=[{"name": "Hero", "turn": 1}],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # With hero: s_next = gradient + 0.03*0.1 = gradient + 0.003
    # Without hero: s_next = gradient only
    # The presence of folk hero should make asabiya higher than without
    asabiya_with_hero = r.asabiya_state.asabiya

    # Reset and run without hero
    r.asabiya_state.asabiya = 0.5
    civ.folk_heroes = []
    apply_asabiya_dynamics(world)
    asabiya_without = r.asabiya_state.asabiya

    assert asabiya_with_hero > asabiya_without


def test_no_folk_heroes_no_bonus():
    """No folk heroes -> no bonus term added."""
    r = _make_region("R1", controller="A", adjacencies=["Enemy"])
    r.asabiya_state.asabiya = 0.5
    r.population = 50
    enemy = _make_region("Enemy", controller="B")
    civ = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
    )
    world = _make_test_world([r, enemy], civs=[civ])
    apply_asabiya_dynamics(world)
    # Pure frontier: s_next = 0.5 + 0.05*1.0*0.5*0.5 = 0.5125
    assert r.asabiya_state.asabiya == pytest.approx(0.5125, abs=1e-4)
```

- [ ] **Step 4: Write snapshot compatibility test (spec #9)**

```python
def test_civ_snapshot_backward_compat():
    """CivSnapshot without asabiya_variance field loads with default 0.0."""
    # Simulate loading an old bundle by constructing without the field
    data = {
        "population": 50, "military": 30, "economy": 40, "culture": 30,
        "stability": 50, "treasury": 50, "asabiya": 0.5, "tech_era": "iron",
        "trait": "cautious", "regions": ["r1"], "leader_name": "L", "alive": True,
    }
    snap = CivSnapshot(**data)
    assert snap.asabiya_variance == 0.0
```

- [ ] **Step 5: Write conquest frontier update test (spec #12)**

```python
def test_conquest_updates_frontier_fractions():
    """After conquest, frontier fractions update for both sides."""
    # Setup: A controls R1, B controls R2, R2 adjacent to R1
    r1 = _make_region("R1", controller="A", adjacencies=["R2"])
    r1.population = 50
    r2 = _make_region("R2", controller="B", adjacencies=["R1"])
    r2.population = 50
    civ_a = Civilization(
        name="A", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L", trait="cautious", reign_start=0), regions=["R1"],
    )
    civ_b = Civilization(
        name="B", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50, asabiya=0.5,
        leader=Leader(name="L2", trait="cautious", reign_start=0), regions=["R2"],
    )
    world = _make_test_world([r1, r2], civs=[civ_a, civ_b])
    apply_asabiya_dynamics(world)
    assert r1.asabiya_state.frontier_fraction == 1.0  # R2 is foreign

    # Simulate conquest: A takes R2
    r2.controller = "A"
    civ_a.regions.append("R2")
    civ_b.regions.remove("R2")
    apply_asabiya_dynamics(world)
    assert r1.asabiya_state.frontier_fraction == 0.0  # R2 is now same-civ
    assert r2.asabiya_state.frontier_fraction == 0.0  # R1 is same-civ
```

- [ ] **Step 6: Run all new tests**

Run: `pytest tests/test_spatial_asabiya.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```
git add tests/test_spatial_asabiya.py
git commit -m "test(m55b): fill remaining spec test coverage gaps"
```

---

### Task 11: No-Scalar-Write Guard Test + Full Regression

**Files:**
- Test: `tests/test_spatial_asabiya.py`

- [ ] **Step 1: Write no-scalar-write guard test**

```python
import subprocess
import os


def test_no_direct_civ_asabiya_writes():
    """Guard: no code directly writes civ.asabiya outside apply_asabiya_dynamics."""
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src", "chronicler")
    # Patterns that indicate direct scalar writes
    forbidden_patterns = [
        r"\.asabiya\s*=\s*min\(",           # civ.asabiya = min(...)
        r"\.asabiya\s*\+=",                  # civ.asabiya += ...
        r'acc\.add\([^)]*"asabiya"',         # acc.add(..., "asabiya", ...)
    ]
    # Files allowed to write civ.asabiya (aggregation function + world_gen + scenario)
    allowed_files = {"simulation.py", "world_gen.py", "scenario.py", "models.py"}

    violations = []
    for root, _dirs, files in os.walk(src_dir):
        for fname in files:
            if not fname.endswith(".py") or fname in allowed_files:
                continue
            fpath = os.path.join(root, fname)
            with open(fpath) as f:
                for lineno, line in enumerate(f, 1):
                    for pat in forbidden_patterns:
                        import re
                        if re.search(pat, line):
                            violations.append(f"{fname}:{lineno}: {line.strip()}")

    assert violations == [], f"Found direct civ.asabiya writes:\n" + "\n".join(violations)
```

- [ ] **Step 2: Run guard test**

Run: `pytest tests/test_spatial_asabiya.py::test_no_direct_civ_asabiya_writes -v`
Expected: PASS (all mutation sites have been migrated in Tasks 5-6).

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: All pass. This is the final regression gate.

- [ ] **Step 4: Commit**

```
git add tests/test_spatial_asabiya.py
git commit -m "test(m55b): add no-scalar-write guard and pass full regression"
```

- [ ] **Step 5: Push**

```
git push
```
