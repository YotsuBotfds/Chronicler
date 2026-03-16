# M34: Regional Resources & Seasons — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace abstract ecology-driven economy with concrete resource production, seasonal yield cycles, mineral depletion, and yield-based famine.

**Architecture:** Python-primary. New `ResourceType` int enum and 3-slot resource system on `Region`. Yield formula runs in `tick_ecology()` (Phase 9), writes to Arrow RecordBatch for Rust satisfaction reads. Legacy `specialized_resources` deprecated but retained.

**Tech Stack:** Python (pydantic models, ecology tick), Rust (satisfaction formulas via PyO3/Arrow), pytest

**Spec:** `docs/superpowers/specs/2026-03-16-m34-resources-seasons-design.md`

---

## Chunk 1: Data Model + Resource Assignment

### Task 1: ResourceType Enum and Region Model Extensions

**Files:**
- Modify: `src/chronicler/models.py`
- Test: `tests/test_resources.py`

- [ ] **Step 1: Write test for ResourceType enum**

```python
# tests/test_resources.py — add to existing file
from chronicler.models import ResourceType

def test_resource_type_enum_values():
    assert ResourceType.GRAIN == 0
    assert ResourceType.TIMBER == 1
    assert ResourceType.BOTANICALS == 2
    assert ResourceType.FISH == 3
    assert ResourceType.SALT == 4
    assert ResourceType.ORE == 5
    assert ResourceType.PRECIOUS == 6
    assert ResourceType.EXOTIC == 7
    assert len(ResourceType) == 8
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `python -m pytest tests/test_resources.py::test_resource_type_enum_values -v`
Expected: FAIL — `ImportError: cannot import name 'ResourceType'`

- [ ] **Step 3: Add ResourceType enum to models.py**

Add after the existing `Resource` class (line 36):

```python
class ResourceType(int, Enum):
    """M34: Concrete resource types collapsed by mechanical equivalence."""
    GRAIN = 0
    TIMBER = 1
    BOTANICALS = 2
    FISH = 3
    SALT = 4
    ORE = 5
    PRECIOUS = 6
    EXOTIC = 7

EMPTY_SLOT = 255

# Mechanical class groupings for yield formula dispatch
FOOD_TYPES = frozenset({ResourceType.GRAIN, ResourceType.FISH, ResourceType.BOTANICALS, ResourceType.EXOTIC})
MINERAL_TYPES = frozenset({ResourceType.ORE, ResourceType.PRECIOUS})
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python -m pytest tests/test_resources.py::test_resource_type_enum_values -v`

- [ ] **Step 5: Write test for Region resource fields**

```python
def test_region_resource_fields_defaults():
    from chronicler.models import Region, EMPTY_SLOT
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assert r.resource_types == [EMPTY_SLOT, EMPTY_SLOT, EMPTY_SLOT]
    assert r.resource_base_yields == [0.0, 0.0, 0.0]
    assert r.resource_reserves == [1.0, 1.0, 1.0]
    assert r.route_suspensions == {}
    # resource_suspensions now int-keyed
    assert r.resource_suspensions == {}
```

- [ ] **Step 6: Run test — expect FAIL**

- [ ] **Step 7: Add fields to Region model in models.py**

In the `Region` class (after `resource_suspensions` at line 151), add:

```python
    route_suspensions: dict[str, int] = Field(default_factory=dict)
    # M34: Concrete resource system
    resource_types: list[int] = Field(default_factory=lambda: [255, 255, 255])
    resource_base_yields: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    resource_reserves: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
```

Change `resource_suspensions` type annotation from `dict[str, int]` to `dict[int, int]`:

```python
    resource_suspensions: dict[int, int] = Field(default_factory=dict)
```

- [ ] **Step 8: Run test — expect PASS**

- [ ] **Step 9: Commit**

```bash
git add src/chronicler/models.py tests/test_resources.py
git commit -m "feat(m34): add ResourceType enum and Region resource fields"
```

---

### Task 2: Resource Assignment System

**Files:**
- Modify: `src/chronicler/resources.py`
- Test: `tests/test_resources.py`

- [ ] **Step 1: Write tests for new assignment**

```python
from chronicler.models import Region, ResourceType, EMPTY_SLOT
from chronicler.resources import assign_resource_types

def test_assign_primary_deterministic():
    """Every terrain gets its locked primary resource."""
    terrain_expected = {
        "plains": ResourceType.GRAIN,
        "forest": ResourceType.TIMBER,
        "mountains": ResourceType.ORE,
        "coast": ResourceType.FISH,
        "desert": ResourceType.EXOTIC,
        "tundra": ResourceType.EXOTIC,
        "river": ResourceType.GRAIN,
        "hills": ResourceType.GRAIN,
    }
    for terrain, expected in terrain_expected.items():
        r = Region(name=f"Test_{terrain}", terrain=terrain, carrying_capacity=50, resources="fertile")
        assign_resource_types([r], seed=42)
        assert r.resource_types[0] == expected, f"{terrain} primary should be {expected.name}"

def test_assign_slot1_never_empty():
    """Slot 1 is always filled for any terrain, any seed."""
    for seed in range(100):
        for terrain in ("plains", "forest", "mountains", "coast", "desert", "tundra", "river", "hills"):
            r = Region(name=f"R_{terrain}_{seed}", terrain=terrain, carrying_capacity=50, resources="fertile")
            assign_resource_types([r], seed=seed)
            assert r.resource_types[0] != EMPTY_SLOT, f"Slot 1 empty for {terrain} seed={seed}"

def test_assign_base_yields_variance():
    """Base yields have ±20% variance around RESOURCE_BASE."""
    regions = []
    for i in range(200):
        r = Region(name=f"Plains_{i}", terrain="plains", carrying_capacity=50, resources="fertile")
        regions.append(r)
    assign_resource_types(regions, seed=12345)
    yields = [r.resource_base_yields[0] for r in regions]
    assert min(yields) >= 0.8 * 1.0  # RESOURCE_BASE * 0.8
    assert max(yields) <= 1.2 * 1.0  # RESOURCE_BASE * 1.2
    assert min(yields) < max(yields)  # Not all identical

def test_assign_mineral_reserves_one():
    """All resources start with reserves=1.0."""
    r = Region(name="Peaks", terrain="mountains", carrying_capacity=50, resources="mineral")
    assign_resource_types([r], seed=42)
    assert all(res == 1.0 for res in r.resource_reserves)

def test_assign_idempotent():
    """Calling assign on already-assigned regions doesn't overwrite."""
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assign_resource_types([r], seed=42)
    original = r.resource_types[:]
    assign_resource_types([r], seed=99)  # Different seed
    assert r.resource_types == original
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_resources.py::test_assign_primary_deterministic tests/test_resources.py::test_assign_slot1_never_empty tests/test_resources.py::test_assign_base_yields_variance tests/test_resources.py::test_assign_mineral_reserves_one tests/test_resources.py::test_assign_idempotent -v`

- [ ] **Step 3: Implement assign_resource_types in resources.py**

Add constants and function at the top of `resources.py` (keep existing `assign_resources` for now):

```python
from chronicler.models import EMPTY_SLOT, ResourceType

# --- M34: Resource type constants ---

RESOURCE_BASE: dict[int, float] = {rt: 1.0 for rt in ResourceType}

TERRAIN_PRIMARY: dict[str, int] = {
    "plains": ResourceType.GRAIN, "forest": ResourceType.TIMBER,
    "mountains": ResourceType.ORE, "coast": ResourceType.FISH,
    "desert": ResourceType.EXOTIC, "tundra": ResourceType.EXOTIC,
    "river": ResourceType.GRAIN, "hills": ResourceType.GRAIN,
}

# (resource_type, probability) pairs per terrain
TERRAIN_SECONDARY: dict[str, list[tuple[int, float]]] = {
    "plains": [(ResourceType.BOTANICALS, 0.30)],
    "forest": [(ResourceType.BOTANICALS, 0.50)],
    "mountains": [(ResourceType.PRECIOUS, 0.40)],
    "coast": [(ResourceType.SALT, 0.60)],
    "desert": [(ResourceType.SALT, 0.50)],
    "tundra": [(ResourceType.ORE, 0.15)],
    "river": [(ResourceType.FISH, 0.40)],
    "hills": [(ResourceType.ORE, 0.30)],
}

TERRAIN_TERTIARY: dict[str, list[tuple[int, float]]] = {
    "plains": [(ResourceType.PRECIOUS, 0.05)],
    "forest": [(ResourceType.ORE, 0.10)],
    "mountains": [(ResourceType.SALT, 0.10)],
    "coast": [(ResourceType.BOTANICALS, 0.15)],
    "desert": [(ResourceType.PRECIOUS, 0.20)],
    "tundra": [],
    "river": [(ResourceType.BOTANICALS, 0.20)],
    "hills": [(ResourceType.TIMBER, 0.20)],
}


def assign_resource_types(regions: list[Region], seed: int) -> None:
    """M34: Assign resource_types and resource_base_yields per region."""
    for region in regions:
        if region.resource_types[0] != EMPTY_SLOT:
            continue  # Already assigned
        rng = random.Random(seed + hash(region.name))

        # Slot 1: deterministic primary
        primary = TERRAIN_PRIMARY.get(region.terrain, ResourceType.GRAIN)
        region.resource_types[0] = primary
        variance = rng.uniform(-0.2, 0.2)
        region.resource_base_yields[0] = RESOURCE_BASE[primary] * (1.0 + variance)

        # Slot 2: probabilistic secondary
        for rtype, prob in TERRAIN_SECONDARY.get(region.terrain, []):
            if rng.random() < prob:
                region.resource_types[1] = rtype
                variance = rng.uniform(-0.2, 0.2)
                region.resource_base_yields[1] = RESOURCE_BASE[rtype] * (1.0 + variance)
                break

        # Slot 3: rare tertiary
        for rtype, prob in TERRAIN_TERTIARY.get(region.terrain, []):
            if rng.random() < prob:
                region.resource_types[2] = rtype
                variance = rng.uniform(-0.2, 0.2)
                region.resource_base_yields[2] = RESOURCE_BASE[rtype] * (1.0 + variance)
                break
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/resources.py tests/test_resources.py
git commit -m "feat(m34): add deterministic-primary resource assignment system"
```

---

### Task 3: Backward-Compat Bridge (specialized_resources auto-population)

**Files:**
- Modify: `src/chronicler/resources.py`
- Test: `tests/test_resources.py`

- [ ] **Step 1: Write test for legacy bridge**

```python
from chronicler.models import Resource
from chronicler.resources import assign_resource_types, populate_legacy_resources

def test_legacy_bridge_populates_specialized_resources():
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assign_resource_types([r], seed=42)
    populate_legacy_resources([r])
    assert len(r.specialized_resources) > 0
    assert Resource.GRAIN in r.specialized_resources
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement populate_legacy_resources**

Add to `resources.py`:

```python
# M34→legacy bridge: ResourceType ID → old Resource enum values
_RESOURCE_TYPE_TO_LEGACY: dict[int, list[Resource]] = {
    ResourceType.GRAIN: [Resource.GRAIN],
    ResourceType.TIMBER: [Resource.TIMBER],
    ResourceType.BOTANICALS: [],  # No direct legacy equivalent
    ResourceType.FISH: [],
    ResourceType.SALT: [],
    ResourceType.ORE: [Resource.IRON, Resource.STONE],
    ResourceType.PRECIOUS: [Resource.RARE_MINERALS],
    ResourceType.EXOTIC: [Resource.FUEL],
}


def populate_legacy_resources(regions: list[Region]) -> None:
    """Auto-populate deprecated specialized_resources from resource_types."""
    for region in regions:
        if region.specialized_resources:
            continue
        legacy: list[Resource] = []
        for rtype in region.resource_types:
            if rtype == EMPTY_SLOT:
                continue
            legacy.extend(_RESOURCE_TYPE_TO_LEGACY.get(rtype, []))
        region.specialized_resources = legacy
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/resources.py tests/test_resources.py
git commit -m "feat(m34): add legacy specialized_resources bridge"
```

---

## Chunk 2: Yield Formula + Seasonal Cycle + Famine Migration

### Task 4: Season and Yield Constants

**Files:**
- Modify: `src/chronicler/tuning.py`
- Modify: `src/chronicler/resources.py` (add modifier tables)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write test for season computation**

```python
# tests/test_ecology.py — add to existing file
from chronicler.resources import get_season_id, get_season_step

def test_season_clock():
    assert get_season_step(0) == 0   # Spring turn 0
    assert get_season_id(0) == 0     # Spring
    assert get_season_step(2) == 2   # Spring close
    assert get_season_id(2) == 0     # Still Spring
    assert get_season_step(3) == 3   # Summer open
    assert get_season_id(3) == 1     # Summer
    assert get_season_step(11) == 11 # Winter close
    assert get_season_id(11) == 3    # Winter
    assert get_season_step(12) == 0  # Wraps to Spring
    assert get_season_id(12) == 0

def test_season_modifier_table_shape():
    from chronicler.resources import SEASON_MOD
    assert len(SEASON_MOD) == 8   # 8 resource types
    assert len(SEASON_MOD[0]) == 4  # 4 seasons
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Add season helpers and modifier tables to resources.py**

```python
def get_season_step(turn: int) -> int:
    return turn % 12

def get_season_id(turn: int) -> int:
    return (turn % 12) // 3

# SEASON_MOD[resource_type_id][season_id] — all [CALIBRATE]
SEASON_MOD: list[list[float]] = [
    # Spring Summer Autumn Winter
    [0.8,   1.2,   1.5,   0.3],   # GRAIN
    [0.6,   1.0,   1.2,   0.8],   # TIMBER
    [1.2,   0.8,   0.6,   0.2],   # BOTANICALS
    [1.0,   1.0,   0.8,   0.6],   # FISH
    [0.8,   1.2,   1.0,   1.0],   # SALT
    [0.9,   1.0,   1.0,   0.9],   # ORE
    [0.9,   1.0,   1.0,   1.0],   # PRECIOUS
    [1.0,   0.8,   1.2,   0.6],   # EXOTIC
]

# CLIMATE_CLASS_MOD[class_index][climate_phase_index]
# Classes: 0=Crop, 1=Forestry, 2=Marine, 3=Mineral, 4=Evaporite
# Phases: 0=TEMPERATE, 1=WARMING, 2=DROUGHT, 3=COOLING
CLIMATE_CLASS_MOD: list[list[float]] = [
    [1.0, 0.9, 0.5, 0.7],  # Crop
    [1.0, 0.9, 0.7, 0.8],  # Forestry
    [1.0, 1.0, 0.8, 0.9],  # Marine
    [1.0, 1.0, 1.0, 1.0],  # Mineral
    [1.0, 1.1, 1.2, 0.9],  # Evaporite
]

_CLIMATE_PHASE_INDEX = {"temperate": 0, "warming": 1, "drought": 2, "cooling": 3}

def resource_class_index(rtype: int) -> int:
    """Map ResourceType to mechanical class index for CLIMATE_CLASS_MOD."""
    if rtype in (ResourceType.GRAIN, ResourceType.BOTANICALS, ResourceType.EXOTIC):
        return 0  # Crop
    elif rtype == ResourceType.TIMBER:
        return 1  # Forestry
    elif rtype == ResourceType.FISH:
        return 2  # Marine
    elif rtype in (ResourceType.ORE, ResourceType.PRECIOUS):
        return 3  # Mineral
    elif rtype == ResourceType.SALT:
        return 4  # Evaporite
    return 0  # Fallback
```

- [ ] **Step 4: Add M34 constants to tuning.py**

Add to the constants block and `KNOWN_OVERRIDES`:

```python
K_SUBSISTENCE_BASELINE = "ecology.subsistence_baseline"
K_FAMINE_YIELD_THRESHOLD = "ecology.famine_yield_threshold"
K_PEAK_YIELD = "ecology.peak_yield"
K_DEPLETION_RATE = "ecology.depletion_rate"
```

Add these 4 strings to the `KNOWN_OVERRIDES` set.

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/resources.py src/chronicler/tuning.py tests/test_ecology.py
git commit -m "feat(m34): add season/climate modifier tables and tuning constants"
```

---

### Task 5: Yield Computation Function

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write tests for yield formula**

```python
from chronicler.ecology import compute_resource_yields
from chronicler.models import Region, ResourceType, ClimatePhase, EMPTY_SLOT

def test_yield_crop_autumn_temperate():
    """Crop: base × season × climate × ecology_mod (soil×water)."""
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile")
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.soil = 0.8
    r.ecology.water = 0.7
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.5 (autumn grain) × 1.0 (temperate crop) × (0.8×0.7) × 1.0
    expected = 1.0 * 1.5 * 1.0 * 0.56 * 1.0
    assert abs(yields[0] - expected) < 0.001

def test_yield_timber_uses_forest_cover():
    r = Region(name="F", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_types = [ResourceType.TIMBER, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.forest_cover = 0.4
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.2 (autumn timber) × 1.0 × 0.4 (forest_cover) × 1.0
    expected = 1.0 * 1.2 * 1.0 * 0.4 * 1.0
    assert abs(yields[0] - expected) < 0.001

def test_yield_fish_ecology_mod_one():
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime")
    r.resource_types = [ResourceType.FISH, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.soil = 0.1  # Bad soil shouldn't affect fish
    r.ecology.water = 0.1
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # 1.0 × 1.0 (spring fish) × 1.0 × 1.0 (marine ecology_mod) × 1.0
    assert abs(yields[0] - 1.0) < 0.001

def test_yield_ore_uses_reserve_ramp():
    r = Region(name="M", terrain="mountains", carrying_capacity=60, resources="mineral")
    r.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [0.10, 1.0, 1.0]  # Low reserves
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # reserve_ramp = min(1.0, 0.10/0.25) = 0.4
    # 1.0 × 0.9 (spring ore) × 0.4
    expected = 1.0 * 0.9 * 0.4
    assert abs(yields[0] - expected) < 0.001

def test_yield_empty_slot_zero():
    r = Region(name="T", terrain="tundra", carrying_capacity=20, resources="barren")
    r.resource_types = [ResourceType.EXOTIC, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    assert yields[1] == 0.0
    assert yields[2] == 0.0

def test_yield_suspension_zeroes():
    """Suspended resource yields 0."""
    r = Region(name="F", terrain="forest", carrying_capacity=50, resources="timber")
    r.resource_types = [ResourceType.TIMBER, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.forest_cover = 0.9
    r.resource_suspensions = {ResourceType.TIMBER: 5}
    yields = compute_resource_yields(r, season_id=2, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    assert yields[0] == 0.0

def test_salt_exempt_from_depletion():
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime")
    r.resource_types = [ResourceType.FISH, ResourceType.SALT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 1.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    # Run 500 turns of extraction
    for _ in range(500):
        compute_resource_yields(r, season_id=1, climate_phase=ClimatePhase.TEMPERATE, worker_count=10)
    assert r.resource_reserves[1] == 1.0  # Salt never depletes
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement compute_resource_yields in ecology.py**

```python
from chronicler.models import EMPTY_SLOT, FOOD_TYPES, MINERAL_TYPES, ResourceType
from chronicler.resources import (
    CLIMATE_CLASS_MOD, RESOURCE_BASE, SEASON_MOD,
    _CLIMATE_PHASE_INDEX, resource_class_index,
)
from chronicler.tuning import K_DEPLETION_RATE, K_SUBSISTENCE_BASELINE

def compute_resource_yields(
    region: Region,
    season_id: int,
    climate_phase: ClimatePhase,
    worker_count: int,
    world: WorldState | None = None,
) -> list[float]:
    """Compute current yield per resource slot. Mutates resource_reserves for minerals."""
    phase_idx = _CLIMATE_PHASE_INDEX.get(climate_phase.value, 0)
    yields = [0.0, 0.0, 0.0]

    for slot in range(3):
        rtype = region.resource_types[slot]
        if rtype == EMPTY_SLOT:
            continue

        # Suspension check
        if rtype in region.resource_suspensions:
            continue

        base = region.resource_base_yields[slot]
        season_mod = SEASON_MOD[rtype][season_id]
        class_idx = resource_class_index(rtype)
        climate_mod = CLIMATE_CLASS_MOD[class_idx][phase_idx]

        # ecology_mod by class
        if class_idx == 0:  # Crop
            ecology_mod = region.ecology.soil * region.ecology.water
        elif class_idx == 1:  # Forestry
            ecology_mod = region.ecology.forest_cover
        else:  # Marine, Mineral, Evaporite
            ecology_mod = 1.0

        # reserve_ramp (minerals only)
        reserve_ramp = 1.0
        if rtype in MINERAL_TYPES:
            reserves = region.resource_reserves[slot]
            # Depletion
            if reserves > 0.01:
                target_workers = max(1, effective_capacity(region) // 3)
                extraction = base * (worker_count / target_workers)
                depletion_rate = get_override(world, K_DEPLETION_RATE, 0.009) if world else 0.009
                region.resource_reserves[slot] = max(0.0, reserves - extraction * depletion_rate)
            reserves = region.resource_reserves[slot]
            if reserves < 0.01:
                yields[slot] = base * 0.04  # Exhausted trickle
                continue
            reserve_ramp = min(1.0, reserves / 0.25)
        elif rtype == ResourceType.SALT:
            pass  # Salt: reserves stay 1.0, no depletion

        yields[slot] = base * season_mod * climate_mod * ecology_mod * reserve_ramp

    return yields
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m34): add compute_resource_yields with per-class ecology_mod and depletion"
```

---

### Task 6: Famine Migration + tick_ecology Integration

**Files:**
- Modify: `src/chronicler/ecology.py`
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write famine trigger tests**

```python
def test_famine_yield_based_triggers():
    """Famine fires when food yield < threshold."""
    from chronicler.ecology import check_food_yield
    from chronicler.models import ResourceType, EMPTY_SLOT, ClimatePhase

    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile", controller="Civ1", population=20)
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    # Low yield scenario
    assert check_food_yield(r, [0.05, 0.0, 0.0], ClimatePhase.TEMPERATE) is True   # Below 0.12

def test_famine_yield_based_no_trigger():
    from chronicler.ecology import check_food_yield
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile", controller="Civ1", population=20)
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    assert check_food_yield(r, [0.50, 0.0, 0.0], ClimatePhase.TEMPERATE) is False  # Above 0.12

def test_subsistence_baseline_no_food_slots():
    """Mountains with no food: subsistence baseline kicks in."""
    from chronicler.ecology import check_food_yield
    r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral", controller="Civ1", population=20)
    r.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, EMPTY_SLOT]
    # Temperate: subsistence = 0.15 × 1.0 = 0.15 > 0.12 → no famine
    assert check_food_yield(r, [0.9, 0.5, 0.0], ClimatePhase.TEMPERATE) is False

def test_subsistence_drought_triggers_famine():
    """Mountains during drought: subsistence × 0.5 = 0.075 < 0.12 → famine."""
    from chronicler.ecology import check_food_yield
    r = Region(name="M", terrain="mountains", carrying_capacity=50, resources="mineral", controller="Civ1", population=20)
    r.resource_types = [ResourceType.ORE, ResourceType.PRECIOUS, EMPTY_SLOT]
    assert check_food_yield(r, [0.9, 0.5, 0.0], ClimatePhase.DROUGHT) is True

def test_multifood_uses_max():
    """Coast with Fish + Botanicals: famine reads the better one."""
    from chronicler.ecology import check_food_yield
    r = Region(name="C", terrain="coast", carrying_capacity=50, resources="maritime", controller="Civ1", population=20)
    r.resource_types = [ResourceType.FISH, ResourceType.BOTANICALS, EMPTY_SLOT]
    # Fish yield low (0.05) but Botanicals high (0.50) → no famine
    assert check_food_yield(r, [0.05, 0.50, 0.0], ClimatePhase.TEMPERATE) is False
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement check_food_yield**

Add to `ecology.py`:

```python
def check_food_yield(
    region: Region,
    yields: list[float],
    climate_phase: ClimatePhase,
    threshold: float = 0.12,
    subsistence_base: float = 0.15,
) -> bool:
    """Return True if region should enter famine (food yield below threshold)."""
    phase_idx = _CLIMATE_PHASE_INDEX.get(climate_phase.value, 0)
    crop_climate_mod = CLIMATE_CLASS_MOD[0][phase_idx]  # Crop class

    # Max food yield from slots
    slot_food = max(
        (y for rtype, y in zip(region.resource_types, yields) if rtype in FOOD_TYPES),
        default=0.0,
    )

    # Subsistence baseline affected by climate
    subsistence = subsistence_base * crop_climate_mod
    food_yield = max(subsistence, slot_food)

    return food_yield < threshold
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Implement _check_famine_yield (replaces _check_famine)**

This mirrors the existing `_check_famine` but uses yield-based trigger. Add to `ecology.py`:

```python
def _check_famine_yield(
    world: WorldState,
    region_yields: dict[str, list[float]],
    climate_phase: ClimatePhase,
    threshold: float,
    subsistence_base: float,
    acc=None,
) -> list[Event]:
    """M34: Region-level famine check based on food yield."""
    from chronicler.utils import drain_region_pop, sync_civ_population, add_region_pop, clamp, STAT_FLOOR
    from chronicler.emergence import get_severity_multiplier

    events: list[Event] = []
    for region in world.regions:
        if region.controller is None or region.famine_cooldown > 0:
            continue
        if region.population <= 0:
            continue

        yields = region_yields.get(region.name, [0.0, 0.0, 0.0])
        if not check_food_yield(region, yields, climate_phase, threshold, subsistence_base):
            continue  # No famine

        civ = next((c for c in world.civilizations if c.name == region.controller), None)
        if civ is None:
            continue

        mult = get_severity_multiplier(civ)
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "population", -int(5 * mult), "guard")
        else:
            drain_region_pop(region, int(5 * mult))
            sync_civ_population(civ, world)
        drain = int(get_override(world, "stability.drain.famine_immediate", 3))
        if acc is not None:
            civ_idx = next(i for i, c in enumerate(world.civilizations) if c.name == civ.name)
            acc.add(civ_idx, civ, "stability", -int(drain * mult), "signal")
        else:
            civ.stability = clamp(civ.stability - int(drain * mult), STAT_FLOOR["stability"], 100)
        region.famine_cooldown = 5

        for adj_name in region.adjacencies:
            adj = next((r for r in world.regions if r.name == adj_name), None)
            if adj and adj.controller and adj.controller != civ.name:
                neighbor = next((c for c in world.civilizations if c.name == adj.controller), None)
                if neighbor:
                    add_region_pop(adj, 5)
                    sync_civ_population(neighbor, world)
                    if acc is not None:
                        neighbor_idx = next(i for i, c in enumerate(world.civilizations) if c.name == neighbor.name)
                        acc.add(neighbor_idx, neighbor, "stability", -5, "signal")
                    else:
                        neighbor.stability = clamp(neighbor.stability - 5, STAT_FLOOR["stability"], 100)

        events.append(Event(
            turn=world.turn, event_type="famine", actors=[civ.name],
            description=f"Famine strikes {region.name}, devastating {civ.name}.",
            importance=8,
        ))
    return events
```

- [ ] **Step 6: Integrate into tick_ecology**

Modify `tick_ecology()` in `ecology.py`. After the existing ecology ticks and before the old `_check_famine`, add yield computation and replace the famine call:

```python
def tick_ecology(world: WorldState, climate_phase: ClimatePhase, acc=None) -> list[Event]:
    """Phase 9 ecology tick."""
    from chronicler.resources import get_season_id

    season_id = get_season_id(world.turn)

    # --- Existing ecology ticks (soil/water/forest for controlled regions — unchanged) ---
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

    # Uncontrolled regions: (keep existing block unchanged)
    for region in world.regions:
        if region.controller is not None:
            continue
        # ... existing uncontrolled ecology code stays exactly as-is ...

    # --- M34: Compute resource yields for all regions ---
    region_yields: dict[str, list[float]] = {}
    subsistence_base = get_override(world, K_SUBSISTENCE_BASELINE, 0.15)
    famine_threshold = get_override(world, K_FAMINE_YIELD_THRESHOLD, 0.12)
    for region in world.regions:
        worker_count = 0  # agents=off uses 0; agent_bridge sets this when agents=on
        yields = compute_resource_yields(region, season_id, climate_phase, worker_count, world)
        region_yields[region.name] = yields

    # --- M34: Yield-based famine (replaces old water-sentinel _check_famine) ---
    events = _check_famine_yield(world, region_yields, climate_phase, famine_threshold, subsistence_base, acc)

    from chronicler.traditions import apply_soil_floor
    apply_soil_floor(world)
    _update_ecology_counters(world)
    from chronicler.utils import sync_all_populations
    sync_all_populations(world)
    return events
```

Rename old `_check_famine` to `_check_famine_legacy` and keep it for reference.

- [ ] **Step 6: Run full ecology test suite**

Run: `python -m pytest tests/test_ecology.py -v`
Expected: All existing tests pass + new tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/ecology.py tests/test_ecology.py
git commit -m "feat(m34): integrate yield computation and famine migration into tick_ecology"
```

---

## Chunk 3: Legacy Migration + Suspension Split

### Task 7: Climate Suspension Split

**Files:**
- Modify: `src/chronicler/climate.py`
- Modify: `src/chronicler/simulation.py` (countdown loop)
- Test: `tests/test_ecology.py`

- [ ] **Step 1: Write test for suspension split**

```python
def test_wildfire_writes_int_key_suspension():
    """Wildfire should write ResourceType.TIMBER (int) to resource_suspensions."""
    from chronicler.climate import check_disasters
    from chronicler.models import ResourceType
    # Setup world with a forest region prone to wildfire
    # (use existing test pattern from test_ecology.py)
    # After wildfire triggers, assert:
    # region.resource_suspensions[ResourceType.TIMBER] == 10
    # NOT region.resource_suspensions["timber"]

def test_sandstorm_writes_route_suspension():
    """Sandstorm should write to route_suspensions, not resource_suspensions."""
    # After sandstorm triggers, assert:
    # "trade_route" in region.route_suspensions
    # "trade_route" not in region.resource_suspensions
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Update climate.py**

Change line 146:
```python
# Old: region.resource_suspensions["timber"] = 10
region.resource_suspensions[ResourceType.TIMBER] = 10
```

Change line 155:
```python
# Old: region.resource_suspensions["trade_route"] = 5
region.route_suspensions["trade_route"] = 5
```

Add import: `from chronicler.models import ResourceType`

- [ ] **Step 4: Update simulation.py countdown loop (lines 109-111)**

```python
    for region in world.regions:
        for k in list(region.disaster_cooldowns):
            region.disaster_cooldowns[k] -= 1
        region.disaster_cooldowns = {k: v for k, v in region.disaster_cooldowns.items() if v > 0}
        # M34: resource_suspensions (int keys) + route_suspensions (str keys)
        for k in list(region.resource_suspensions):
            region.resource_suspensions[k] -= 1
        region.resource_suspensions = {k: v for k, v in region.resource_suspensions.items() if v > 0}
        for k in list(region.route_suspensions):
            region.route_suspensions[k] -= 1
        region.route_suspensions = {k: v for k, v in region.route_suspensions.items() if v > 0}
```

- [ ] **Step 5: Run tests — expect PASS**

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/climate.py src/chronicler/simulation.py tests/test_ecology.py
git commit -m "feat(m34): split resource_suspensions into int-keyed + route_suspensions"
```

---

### Task 8: Migrate Downstream Consumers

**Files:**
- Modify: `src/chronicler/tech.py`
- Modify: `src/chronicler/tech_focus.py`
- Modify: `src/chronicler/simulation.py` (economy specialization)
- Modify: `src/chronicler/emergence.py`
- Modify: `src/chronicler/scenario.py`
- Test: Run existing test suite for regression

- [ ] **Step 1: Migrate tech.py RESOURCE_REQUIREMENTS**

Replace old Resource references with ResourceType checks. The key change: `_get_civ_resources` reads `resource_types` instead of `specialized_resources`:

```python
from chronicler.models import EMPTY_SLOT, ResourceType

# Map old requirements to new types
RESOURCE_REQUIREMENTS: dict[TechEra, tuple[set[int] | None, int]] = {
    TechEra.TRIBAL: ({ResourceType.ORE, ResourceType.TIMBER}, 2),
    TechEra.BRONZE: ({ResourceType.ORE, ResourceType.TIMBER, ResourceType.GRAIN}, 3),
    TechEra.IRON: (None, 3),
    TechEra.CLASSICAL: (None, 4),
    TechEra.MEDIEVAL: (None, 4),
    TechEra.RENAISSANCE: (None, 5),
    TechEra.INDUSTRIAL: ({ResourceType.TIMBER}, 5),  # FUEL → TIMBER
}

def _get_civ_resources(civ: Civilization, world: WorldState) -> set[int]:
    resources: set[int] = set()
    for r in world.regions:
        if r.controller == civ.name:
            for rtype in r.resource_types:
                if rtype != EMPTY_SLOT:
                    resources.add(rtype)
    return resources
```

- [ ] **Step 2: Migrate tech_focus.py _count_resource**

```python
def _count_resource(civ: Civilization, world: WorldState, resource: int) -> int:
    return sum(1 for r in world.regions if r.controller == civ.name and resource in r.resource_types)
```

Update callers: `Resource.IRON` → `ResourceType.ORE`, `Resource.GRAIN` → `ResourceType.GRAIN`, etc.

- [ ] **Step 3: Migrate simulation.py economic specialization (lines 249-280)**

Replace `r.specialized_resources` with `r.resource_types` and filter out `EMPTY_SLOT`:

```python
        resource_counts: dict[int, int] = {}
        for r in controlled:
            for rtype in r.resource_types:
                if rtype != EMPTY_SLOT:
                    resource_counts[rtype] = resource_counts.get(rtype, 0) + 1
```

```python
            route_regions = [r for r in world.regions
                            if r.controller in (a, b) and primary in r.resource_types]
```

- [ ] **Step 4: Migrate emergence.py barren check + discovery**

```python
    barren = [r for r in world.regions if r.resource_types[0] == EMPTY_SLOT]
```

```python
    new_resources = rng.sample([ResourceType.TIMBER, ResourceType.PRECIOUS], k=count)
    for i, rtype in enumerate(new_resources):
        # Find first empty slot
        for slot in range(3):
            if region.resource_types[slot] == EMPTY_SLOT:
                region.resource_types[slot] = rtype
                region.resource_base_yields[slot] = RESOURCE_BASE[rtype] * (1.0 + rng.uniform(-0.2, 0.2))
                break
```

Also call `populate_legacy_resources` after discovery for backward compat.

- [ ] **Step 5: Migrate scenario.py**

Support both old string-based and new int-based overrides:

```python
        if reg_override.specialized_resources is not None:
            from chronicler.models import Resource, ResourceType, EMPTY_SLOT
            from chronicler.resources import populate_legacy_resources, RESOURCE_BASE
            # Try new int-based first
            try:
                types = [int(r) for r in reg_override.specialized_resources]
            except (ValueError, TypeError):
                # Fall back to old string-based → legacy
                world.regions[target_idx].specialized_resources = [Resource(r) for r in reg_override.specialized_resources]
                types = None
            if types is not None:
                for i, rtype in enumerate(types[:3]):
                    world.regions[target_idx].resource_types[i] = rtype
                    world.regions[target_idx].resource_base_yields[i] = RESOURCE_BASE.get(rtype, 1.0)
                populate_legacy_resources([world.regions[target_idx]])
```

- [ ] **Step 6: Wire assign_resource_types into world_gen.py and scenario.py**

There are two call sites for `assign_resources`:
1. `world_gen.py` line 202-203: default world generation
2. `scenario.py` line 383-384: scenario-based world generation

In **`world_gen.py`** after line 203:
```python
    from chronicler.resources import assign_resources, assign_resource_types, populate_legacy_resources
    assign_resources(regions, seed=seed)
    assign_resource_types(regions, seed=seed)
    populate_legacy_resources(regions)
```

In **`scenario.py`** after line 384:
```python
    from chronicler.resources import assign_resources, assign_resource_types, populate_legacy_resources
    assign_resources(world.regions, seed=world.seed)
    assign_resource_types(world.regions, seed=world.seed)
    populate_legacy_resources(world.regions)
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -x -v --timeout=60`
Expected: All existing tests pass. Some may need minor adjustments if they create regions without calling assign_resource_types.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/tech.py src/chronicler/tech_focus.py src/chronicler/simulation.py src/chronicler/emergence.py src/chronicler/scenario.py src/chronicler/world_gen.py
git commit -m "feat(m34): migrate all consumers from specialized_resources to resource_types"
```

---

## Chunk 4: Arrow Bridge + Rust Extensions

### Task 9: Extend Arrow RecordBatch

**Files:**
- Modify: `src/chronicler/agent_bridge.py`
- Test: `tests/test_agent_bridge.py`

- [ ] **Step 1: Write test for new columns in region batch**

```python
def test_region_batch_has_resource_columns():
    """M34: Region batch includes resource_types, resource_yields, season, season_id."""
    # Build a minimal world and call build_region_batch
    # Assert columns exist with correct types:
    # "resource_type_0", "resource_type_1", "resource_type_2" → uint8
    # "resource_yield_0", "resource_yield_1", "resource_yield_2" → float32
    # "resource_reserve_0", "resource_reserve_1", "resource_reserve_2" → float32
    # "season" → uint8
    # "season_id" → uint8
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Extend build_region_batch in agent_bridge.py**

Add new columns to the RecordBatch construction:

```python
    # M34: Resource state
    "resource_type_0": pa.array([r.resource_types[0] for r in world.regions], type=pa.uint8()),
    "resource_type_1": pa.array([r.resource_types[1] for r in world.regions], type=pa.uint8()),
    "resource_type_2": pa.array([r.resource_types[2] for r in world.regions], type=pa.uint8()),
    "resource_yield_0": pa.array([0.0 for _ in world.regions], type=pa.float32()),
    "resource_yield_1": pa.array([0.0 for _ in world.regions], type=pa.float32()),
    "resource_yield_2": pa.array([0.0 for _ in world.regions], type=pa.float32()),
    "resource_reserve_0": pa.array([r.resource_reserves[0] for r in world.regions], type=pa.float32()),
    "resource_reserve_1": pa.array([r.resource_reserves[1] for r in world.regions], type=pa.float32()),
    "resource_reserve_2": pa.array([r.resource_reserves[2] for r in world.regions], type=pa.float32()),
    "season": pa.array([get_season_step(world.turn) for _ in world.regions], type=pa.uint8()),
    "season_id": pa.array([get_season_id(world.turn) for _ in world.regions], type=pa.uint8()),
```

Arrow RecordBatches are immutable. The bridge must be called **after** `tick_ecology` computes yields. The `build_region_batch` function should read the yields computed during Phase 9 and stored in a module-level dict (e.g., `ecology._last_region_yields`). In the `AgentBridge.tick()` flow, Phase 9 runs first, then `build_region_batch` picks up the fresh yields:

```python
# In ecology.py, at module level:
_last_region_yields: dict[str, list[float]] = {}

# In tick_ecology, after computing yields:
_last_region_yields.clear()
_last_region_yields.update(region_yields)
```

Then in `build_region_batch`:
```python
from chronicler.ecology import _last_region_yields
for i, r in enumerate(world.regions):
    ry = _last_region_yields.get(r.name, [0.0, 0.0, 0.0])
    # Use ry[0], ry[1], ry[2] for the yield columns
```

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/agent_bridge.py tests/test_agent_bridge.py
git commit -m "feat(m34): extend Arrow RecordBatch with resource/season columns"
```

---

### Task 10: Rust RegionState + Satisfaction Extensions

**Files:**
- Modify: `chronicler-agents/src/region.rs`
- Modify: `chronicler-agents/src/satisfaction.rs`
- Modify: `chronicler-agents/src/ffi.rs` (column extraction)
- Test: `chronicler-agents/src/satisfaction.rs` (inline tests)

- [ ] **Step 1: Add fields to RegionState**

In `region.rs`:

```rust
pub struct RegionState {
    // ... existing fields ...
    // M34: Resource state
    pub resource_types: [u8; 3],
    pub resource_yields: [f32; 3],
    pub resource_reserves: [f32; 3],
    pub season: u8,
    pub season_id: u8,
}
```

Update `RegionState::new()` defaults:
```rust
    resource_types: [255, 255, 255],
    resource_yields: [0.0, 0.0, 0.0],
    resource_reserves: [1.0, 1.0, 1.0],
    season: 0,
    season_id: 0,
```

- [ ] **Step 2: Add resource_satisfaction and trade_satisfaction to satisfaction.rs**

```rust
const FAMINE_YIELD_THRESHOLD: f32 = 0.12;
const PEAK_YIELD: f32 = 1.0;

/// Food types: GRAIN=0, BOTANICALS=2, FISH=3, EXOTIC=7
fn is_food(rtype: u8) -> bool {
    matches!(rtype, 0 | 2 | 3 | 7)
}

pub fn resource_satisfaction(region: &RegionState) -> f32 {
    let primary_yield = region.resource_yields[0];
    let sat = (primary_yield - FAMINE_YIELD_THRESHOLD)
            / (PEAK_YIELD - FAMINE_YIELD_THRESHOLD);
    sat.clamp(0.0, 1.0)
}

pub fn trade_satisfaction(region: &RegionState) -> f32 {
    let mut trade_score: f32 = 0.0;
    for i in 0..3 {
        let rtype = region.resource_types[i];
        let yield_val = region.resource_yields[i];
        if rtype != 255 && yield_val > 0.0 {
            let weight = if is_food(rtype) { 0.15 } else { 0.35 };
            trade_score += weight;
        }
    }
    trade_score.clamp(0.1, 1.0)
}
```

- [ ] **Step 3: Write Rust tests**

```rust
#[cfg(test)]
mod m34_tests {
    use super::*;

    fn make_region_with_resources(types: [u8; 3], yields: [f32; 3]) -> RegionState {
        let mut r = RegionState::new(0);
        r.resource_types = types;
        r.resource_yields = yields;
        r
    }

    #[test]
    fn test_resource_satisfaction_at_peak() {
        let r = make_region_with_resources([0, 255, 255], [1.0, 0.0, 0.0]);
        let sat = resource_satisfaction(&r);
        assert!((sat - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_resource_satisfaction_at_threshold() {
        let r = make_region_with_resources([0, 255, 255], [0.12, 0.0, 0.0]);
        let sat = resource_satisfaction(&r);
        assert!(sat.abs() < 0.01);
    }

    #[test]
    fn test_trade_satisfaction_mountains() {
        // Ore + Precious = 0.35 + 0.35 = 0.7
        let r = make_region_with_resources([5, 6, 255], [0.9, 0.5, 0.0]);
        let sat = trade_satisfaction(&r);
        assert!((sat - 0.7).abs() < 0.01);
    }

    #[test]
    fn test_trade_satisfaction_tundra_exotic_only() {
        // Exotic (food) = 0.15
        let r = make_region_with_resources([7, 255, 255], [0.5, 0.0, 0.0]);
        let sat = trade_satisfaction(&r);
        assert!((sat - 0.15).abs() < 0.01);
    }
}
```

- [ ] **Step 4: Update ffi.rs column extraction**

Add extraction for new columns in the region state update path. Follow existing pattern using the column extraction macros.

- [ ] **Step 5: Build and test Rust crate**

Run: `cd chronicler-agents && cargo test`
Expected: All existing tests pass + new M34 tests pass.

- [ ] **Step 6: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/satisfaction.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m34): add resource/season fields to RegionState + satisfaction formulas"
```

---

## Chunk 5: Validation

### Task 11: Tier 1 Structural Tests (Complete Suite)

**Files:**
- Modify: `tests/test_resources.py`
- Modify: `tests/test_ecology.py`

- [ ] **Step 1: Add remaining Tier 1 tests**

Tests not yet covered by Tasks 1-6:

```python
# Depletion math
def test_depletion_linear_drawdown():
    """Reserves decrease linearly over N turns."""
    r = Region(name="M", terrain="mountains", carrying_capacity=60, resources="mineral")
    r.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    target_workers = max(1, 60 // 3)  # 20
    prev_reserves = 1.0
    for turn in range(50):
        compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=20)
        assert r.resource_reserves[0] < prev_reserves
        prev_reserves = r.resource_reserves[0]

def test_depletion_ramp_at_25_percent():
    r = Region(name="M", terrain="mountains", carrying_capacity=60, resources="mineral")
    r.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [0.20, 1.0, 1.0]  # Below 0.25
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # reserve_ramp = min(1.0, 0.20/0.25) = 0.8
    expected_ramp = 0.8
    expected = 1.0 * 0.9 * 1.0 * expected_ramp  # base × spring_ore × ramp
    assert abs(yields[0] - expected) < 0.001

def test_depletion_exhaustion_floor():
    r = Region(name="M", terrain="mountains", carrying_capacity=60, resources="mineral")
    r.resource_types = [ResourceType.ORE, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [0.005, 1.0, 1.0]  # Below 0.01
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    assert abs(yields[0] - 0.04) < 0.01  # base × 0.04 trickle

# ecology_mod correctness
def test_ecology_mod_crop():
    r = Region(name="P", terrain="plains", carrying_capacity=50, resources="fertile")
    r.resource_types = [ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT]
    r.resource_base_yields = [1.0, 0.0, 0.0]
    r.resource_reserves = [1.0, 1.0, 1.0]
    r.ecology.soil = 0.5
    r.ecology.water = 0.6
    yields = compute_resource_yields(r, season_id=0, climate_phase=ClimatePhase.TEMPERATE, worker_count=0)
    # ecology_mod = 0.5 × 0.6 = 0.3; season = 0.8 (spring grain)
    expected = 1.0 * 0.8 * 1.0 * 0.3
    assert abs(yields[0] - expected) < 0.001
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_resources.py tests/test_ecology.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/test_resources.py tests/test_ecology.py
git commit -m "test(m34): complete Tier 1 structural tests"
```

---

### Task 12: Tier 2 Regression Harness

**Files:**
- Create: `tests/test_m34_regression.py`

- [ ] **Step 1: Write Tier 2 regression tests**

```python
"""M34 Tier 2: Behavioral regression — 200 seeds × 200 turns, --agents=off."""
import pytest
from chronicler.simulation import run_simulation
from chronicler.models import ResourceType, EMPTY_SLOT

SEEDS = range(200)
TURNS = 200

@pytest.fixture(scope="module")
def regression_results():
    """Run 200 seeds and collect aggregate stats."""
    results = []
    for seed in SEEDS:
        world = run_simulation(seed=seed, turns=TURNS, agent_mode="off")
        results.append(world)
    return results

def test_all_resource_types_appear(regression_results):
    seen = set()
    for world in regression_results:
        for r in world.regions:
            for rtype in r.resource_types:
                if rtype != EMPTY_SLOT:
                    seen.add(rtype)
    assert len(seen) == 8, f"Only {len(seen)} of 8 resource types appeared"

def test_slot1_never_empty(regression_results):
    for world in regression_results:
        for r in world.regions:
            assert r.resource_types[0] != EMPTY_SLOT, f"{r.name} has empty slot 1"

def test_famine_frequency_drought(regression_results):
    """DROUGHT phases: 5-15% famine turns."""
    # Count famine events during drought turns across all seeds
    # This test validates the FAMINE_YIELD_THRESHOLD calibration
    pass  # Implement based on event counting from world.events_timeline

def test_aggregate_economy_regression(regression_results):
    """Total economy within ±10% of M23 baseline."""
    # Compare sum of economy stats vs known M23 baseline
    pass  # Implement after establishing baseline
```

- [ ] **Step 2: Run regression (may be slow — run in background)**

Run: `python -m pytest tests/test_m34_regression.py -v --timeout=300`

- [ ] **Step 3: Commit**

```bash
git add tests/test_m34_regression.py
git commit -m "test(m34): add Tier 2 behavioral regression harness"
```

---

## Summary

| Task | Component | Est. Lines | Key Files |
|------|-----------|-----------|-----------|
| 1 | ResourceType enum + Region fields | ~30 | models.py |
| 2 | Resource assignment system | ~80 | resources.py |
| 3 | Legacy bridge (specialized_resources) | ~25 | resources.py |
| 4 | Season/climate modifier tables | ~50 | resources.py, tuning.py |
| 5 | Yield computation function | ~60 | ecology.py |
| 6 | Famine migration + tick integration | ~50 | ecology.py |
| 7 | Climate suspension split | ~15 | climate.py, simulation.py |
| 8 | Downstream consumer migration | ~80 | tech.py, tech_focus.py, simulation.py, emergence.py, scenario.py |
| 9 | Arrow RecordBatch extension | ~20 | agent_bridge.py |
| 10 | Rust RegionState + satisfaction | ~80 | region.rs, satisfaction.rs, ffi.rs |
| 11 | Tier 1 structural tests | ~100 | test_resources.py, test_ecology.py |
| 12 | Tier 2 regression harness | ~50 | test_m34_regression.py |

**Total: ~640 lines** (~475 Python, ~85 Rust, ~80 test infrastructure)

**Execution order:** Tasks 1-3 (data model) → 4-6 (yield formula) → 7-8 (migration) → 9-10 (Rust bridge) → 11-12 (validation). Tasks within each group can run in parallel where indicated.

## Known Deferred Items

These are noted for the implementer but deferred to follow-up tasks:

1. **Occupation demand shifts** (spec: "mineral region → soldier/merchant demand +1 tier") — wires into existing `DemandSignalManager`. Deferred because it requires the Rust agent tick to be running with M34 columns first. Can be a small follow-up PR.
2. **Rust satisfaction wiring** — `resource_satisfaction` and `trade_satisfaction` are added to `satisfaction.rs` but not yet wired into the existing `compute_satisfaction` function's farmer/merchant base formulas. This requires replacing the `0.3×soil + 0.2×water` farmer base with a call to `resource_satisfaction`, which is a behavioral change gated on M32 landing first.
3. **Tier 2 regression stubs** — `test_famine_frequency_drought` and `test_aggregate_economy_regression` need concrete implementations after a baseline is established from a full 200-seed run.
4. **TERRAIN_MAP in agent_bridge.py** — does not include "river" or "hills". Add entries mapping to plains defaults if these terrains appear in scenarios.
5. **hash() determinism** — `assign_resource_types` uses `hash(region.name)` for RNG seeding, matching existing `assign_resources` pattern. Python's `hash()` is non-deterministic across processes unless `PYTHONHASHSEED=0`. Existing precedent accepts this; flag for M47 if reproducibility issues arise.
