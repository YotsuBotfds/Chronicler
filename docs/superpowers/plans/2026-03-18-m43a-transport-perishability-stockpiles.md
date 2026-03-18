# M43a: Transport, Perishability & Stockpiles — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add transport costs, per-good perishability, and persistent stockpiles to M42's goods economy, making geography matter for trade.

**Architecture:** M43a extends `economy.py`'s `compute_economy()` with transport cost filtering (pre-allocation margin reduction), per-good transit decay (post-allocation volume attrition), and a new `RegionStockpile` model persisted on `Region`. All changes are Python-side — no Rust/FFI modifications. The existing `food_sufficiency` signal changes source from single-turn supply to pre-consumption stockpile.

**Tech Stack:** Python 3.12, Pydantic models, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/chronicler/models.py` | `RegionStockpile` model, nest on `Region` | Modify |
| `src/chronicler/economy.py` | Transport cost, perishability, stockpile accumulation/decay/cap/consumption, modified `compute_economy()` | Modify |
| `src/chronicler/world_gen.py` | Stockpile initialization in `generate_world()` | Modify |
| `src/chronicler/simulation.py` | Pass stockpile context to economy | Modify (minor) |
| `src/chronicler/action_engine.py` | Conquest stockpile destruction | Modify |
| `src/chronicler/analytics.py` | Stockpile time series extractors | Modify |
| `tests/test_economy_m43a.py` | All M43a unit + integration tests | Create |

`tests/test_economy_m43a.py` is a separate file from `tests/test_economy.py` (M42 tests). M43a tests are substantial (~300-400 lines) and logically independent from M42's unit tests. The existing M42 tests continue to pass unchanged.

---

## Chunk 1: Data Model, Constants & Helpers

### Task 1: RegionStockpile Model

**Files:**
- Modify: `src/chronicler/models.py:171-175` (after `RegionEcology`, before `River`)
- Modify: `src/chronicler/models.py:195` (add `stockpile` field to `Region`)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_economy_m43a.py
"""M43a: Transport, perishability & stockpiles tests."""

from chronicler.models import RegionStockpile, Region


def test_region_stockpile_default():
    """RegionStockpile initializes with empty goods dict."""
    s = RegionStockpile()
    assert s.goods == {}


def test_region_stockpile_with_goods():
    """RegionStockpile holds per-good float values."""
    s = RegionStockpile(goods={"grain": 50.0, "salt": 10.0})
    assert s.goods["grain"] == 50.0
    assert s.goods["salt"] == 10.0


def test_region_has_stockpile():
    """Region has a stockpile field defaulting to empty RegionStockpile."""
    r = Region(name="Test", terrain="plains", carrying_capacity=50, resources="fertile")
    assert isinstance(r.stockpile, RegionStockpile)
    assert r.stockpile.goods == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: FAIL — `RegionStockpile` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/models.py`, after line 174 (`RegionEcology`), before line 177 (`River`):

```python
class RegionStockpile(BaseModel):
    """Persistent per-region per-good stockpile. Keys are good names (grain, timber, etc.)."""

    goods: dict[str, float] = Field(default_factory=dict)
```

In `src/chronicler/models.py`, after line 195 (`ecology` field on `Region`):

```python
    stockpile: RegionStockpile = Field(default_factory=RegionStockpile)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/models.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add RegionStockpile model, nest on Region"
```

### Task 2: M43a Constants and Good Sets

**Files:**
- Modify: `src/chronicler/economy.py:22-33` (after existing M42 constants)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
from chronicler.economy import (
    FOOD_GOODS,
    ALL_GOODS,
    TRANSIT_DECAY,
    STORAGE_DECAY,
    TERRAIN_COST,
    TRANSPORT_COST_BASE,
    RIVER_DISCOUNT,
    COASTAL_DISCOUNT,
    INFRASTRUCTURE_DISCOUNT,
    WINTER_MODIFIER,
    SALT_PRESERVATION_FACTOR,
    MAX_PRESERVATION,
    PER_CAPITA_FOOD,
    CONQUEST_STOCKPILE_SURVIVAL,
)


def test_food_goods_contains_salt():
    """FOOD_GOODS includes salt (M42 Decision 1)."""
    assert "salt" in FOOD_GOODS
    assert "grain" in FOOD_GOODS
    assert "fish" in FOOD_GOODS
    assert "botanicals" in FOOD_GOODS
    assert "exotic" in FOOD_GOODS
    assert "timber" not in FOOD_GOODS


def test_all_goods_has_8_members():
    """ALL_GOODS covers all 8 resource types."""
    assert len(ALL_GOODS) == 8
    assert ALL_GOODS == frozenset({
        "grain", "timber", "botanicals", "fish",
        "salt", "ore", "precious", "exotic",
    })


def test_transit_decay_rates():
    """Transit decay: food decays, minerals don't."""
    assert TRANSIT_DECAY["grain"] == 0.05
    assert TRANSIT_DECAY["fish"] == 0.08
    assert TRANSIT_DECAY["salt"] == 0.0
    assert TRANSIT_DECAY["ore"] == 0.0
    assert TRANSIT_DECAY["precious"] == 0.0


def test_storage_decay_rates():
    """Storage decay < transit decay for same good."""
    assert STORAGE_DECAY["grain"] == 0.03
    assert STORAGE_DECAY["grain"] < TRANSIT_DECAY["grain"]
    assert STORAGE_DECAY["salt"] == 0.0


def test_terrain_cost_all_terrains():
    """All 6 terrain types have a cost factor."""
    assert set(TERRAIN_COST.keys()) == {"plains", "forest", "desert", "mountains", "tundra", "coast"}
    assert TERRAIN_COST["plains"] == 1.0
    assert TERRAIN_COST["mountains"] == 2.0
    assert TERRAIN_COST["coast"] == 0.6


def test_per_good_cap_factor_derived():
    """PER_GOOD_CAP_FACTOR is derived from PER_CAPITA_FOOD."""
    from chronicler.economy import PER_GOOD_CAP_FACTOR, INITIAL_BUFFER
    assert PER_GOOD_CAP_FACTOR == 5.0 * PER_CAPITA_FOOD
    assert INITIAL_BUFFER == 2.0 * PER_CAPITA_FOOD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_food_goods_contains_salt -v -x`
Expected: FAIL — `FOOD_GOODS` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/economy.py`, after line 33 (`CATEGORIES`), add:

```python
# ---------------------------------------------------------------------------
# M43a Constants  [CALIBRATE]
# ---------------------------------------------------------------------------

FOOD_GOODS: frozenset[str] = frozenset({"grain", "fish", "botanicals", "exotic", "salt"})
ALL_GOODS: frozenset[str] = frozenset({
    "grain", "timber", "botanicals", "fish", "salt", "ore", "precious", "exotic",
})

TERRAIN_COST: dict[str, float] = {
    "plains": 1.0,
    "forest": 1.3,
    "desert": 1.5,
    "mountains": 2.0,
    "tundra": 1.8,
    "coast": 0.6,
}
TRANSPORT_COST_BASE: float = 0.10
RIVER_DISCOUNT: float = 0.5
COASTAL_DISCOUNT: float = 0.6
INFRASTRUCTURE_DISCOUNT: float = 1.0  # placeholder — no roads yet
WINTER_MODIFIER: float = 1.5

TRANSIT_DECAY: dict[str, float] = {
    "grain": 0.05, "fish": 0.08, "botanicals": 0.04, "exotic": 0.06,
    "salt": 0.0, "timber": 0.01, "ore": 0.0, "precious": 0.0,
}
STORAGE_DECAY: dict[str, float] = {
    "grain": 0.03, "fish": 0.06, "botanicals": 0.02, "exotic": 0.04,
    "salt": 0.0, "timber": 0.005, "ore": 0.0, "precious": 0.0,
}

SALT_PRESERVATION_FACTOR: float = 2.5
MAX_PRESERVATION: float = 0.5

PER_GOOD_CAP_FACTOR: float = 5.0 * PER_CAPITA_FOOD
INITIAL_BUFFER: float = 2.0 * PER_CAPITA_FOOD
CONQUEST_STOCKPILE_SURVIVAL: float = 0.5
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS (all tests so far)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add M43a constants — transport, perishability, stockpile"
```

### Task 3: map_resource_to_good()

**Files:**
- Modify: `src/chronicler/economy.py` (after `map_resource_to_category`, ~line 50)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
from chronicler.economy import map_resource_to_good


def test_map_resource_to_good_all_types():
    """All 8 resource types map to the correct good name."""
    assert map_resource_to_good(0) == "grain"
    assert map_resource_to_good(1) == "timber"
    assert map_resource_to_good(2) == "botanicals"
    assert map_resource_to_good(3) == "fish"
    assert map_resource_to_good(4) == "salt"
    assert map_resource_to_good(5) == "ore"
    assert map_resource_to_good(6) == "precious"
    assert map_resource_to_good(7) == "exotic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_map_resource_to_good_all_types -v -x`
Expected: FAIL — `map_resource_to_good` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/economy.py`, after `map_resource_to_category()` (~line 49):

```python
_GOOD_MAP: dict[int, str] = {
    0: "grain", 1: "timber", 2: "botanicals", 3: "fish",
    4: "salt", 5: "ore", 6: "precious", 7: "exotic",
}


def map_resource_to_good(resource_type: int) -> str:
    """Map M34 resource type enum value to per-good stockpile key."""
    return _GOOD_MAP[resource_type]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add map_resource_to_good() mapping function"
```

---

## Chunk 2: Transport Cost

### Task 4: Transport Cost Computation

**Files:**
- Modify: `src/chronicler/economy.py` (add after `map_resource_to_good`, before trade flow section)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.economy import (
    compute_transport_cost,
    build_river_route_set,
    TRANSPORT_COST_BASE,
    TERRAIN_COST,
    RIVER_DISCOUNT,
    COASTAL_DISCOUNT,
    WINTER_MODIFIER,
)


def test_transport_cost_plains_to_plains():
    """Plains-to-plains base cost = TRANSPORT_COST_BASE * 1.0."""
    cost = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    assert cost == TRANSPORT_COST_BASE * 1.0


def test_transport_cost_worst_terrain():
    """Cost uses worst terrain factor of the two endpoints."""
    cost = compute_transport_cost("plains", "mountains", is_river=False, is_coastal=False, is_winter=False)
    assert cost == TRANSPORT_COST_BASE * TERRAIN_COST["mountains"]


def test_transport_cost_river_discount():
    """River route halves the cost."""
    base = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    river = compute_transport_cost("plains", "plains", is_river=True, is_coastal=False, is_winter=False)
    assert river == base * RIVER_DISCOUNT


def test_transport_cost_coastal_discount():
    """Coastal route applies coastal discount."""
    base = compute_transport_cost("coast", "coast", is_river=False, is_coastal=False, is_winter=False)
    coastal = compute_transport_cost("coast", "coast", is_river=False, is_coastal=True, is_winter=False)
    assert coastal == base * COASTAL_DISCOUNT


def test_transport_cost_river_and_coastal_takes_min():
    """When both river and coastal apply, take the better discount."""
    river_only = compute_transport_cost("coast", "coast", is_river=True, is_coastal=False, is_winter=False)
    coastal_only = compute_transport_cost("coast", "coast", is_river=False, is_coastal=True, is_winter=False)
    both = compute_transport_cost("coast", "coast", is_river=True, is_coastal=True, is_winter=False)
    assert both == min(river_only, coastal_only)


def test_transport_cost_winter_modifier():
    """Winter increases transport cost by 50%."""
    base = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=False)
    winter = compute_transport_cost("plains", "plains", is_river=False, is_coastal=False, is_winter=True)
    assert winter == base * WINTER_MODIFIER


def test_build_river_route_set():
    """Builds set of frozensets from River.path pairs."""
    from chronicler.models import River
    rivers = [River(name="Nile", path=["A", "B", "C"])]
    result = build_river_route_set(rivers)
    assert frozenset({"A", "B"}) in result
    assert frozenset({"B", "C"}) in result
    assert frozenset({"A", "C"}) not in result  # not adjacent in path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_economy_m43a.py::test_transport_cost_plains_to_plains -v -x`
Expected: FAIL — `compute_transport_cost` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/economy.py`, after `map_resource_to_good()`:

```python
# ---------------------------------------------------------------------------
# M43a: Transport cost
# ---------------------------------------------------------------------------

def build_river_route_set(rivers: list) -> set[frozenset[str, str]]:
    """Pre-build set of river-connected region pairs for O(1) lookup.

    Each River.path is an ordered list of region names along the river.
    Adjacent pairs in the path are river-connected.
    """
    pairs: set[frozenset] = set()
    for river in rivers:
        path = river.path
        for i in range(len(path) - 1):
            pairs.add(frozenset({path[i], path[i + 1]}))
    return pairs


def compute_transport_cost(
    terrain_a: str,
    terrain_b: str,
    *,
    is_river: bool,
    is_coastal: bool,
    is_winter: bool,
) -> float:
    """Per-route transport cost. Subtracted from raw margin for effective margin.

    Args:
        terrain_a: Terrain type of origin region.
        terrain_b: Terrain type of destination region.
        is_river: Both regions on same river path.
        is_coastal: Both regions are coast terrain.
        is_winter: Current season is winter.
    """
    terrain_factor = max(TERRAIN_COST.get(terrain_a, 1.0), TERRAIN_COST.get(terrain_b, 1.0))
    river = RIVER_DISCOUNT if is_river else 1.0
    coastal = COASTAL_DISCOUNT if is_coastal else 1.0
    seasonal = WINTER_MODIFIER if is_winter else 1.0
    infra = INFRASTRUCTURE_DISCOUNT
    return TRANSPORT_COST_BASE * terrain_factor * infra * min(river, coastal) * seasonal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add transport cost computation and river route lookup"
```

### Task 5: Effective Margin in Trade Flow

**Files:**
- Modify: `src/chronicler/economy.py:157-225` (`allocate_trade_flow()`)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
def test_effective_margin_filters_expensive_routes():
    """Routes where transport cost exceeds price gap get zero flow."""
    from chronicler.economy import allocate_trade_flow

    routes = [("A", "B"), ("A", "C")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    # B has slightly higher food price, C has much higher
    dest_prices = {
        "B": {"food": 1.05, "raw_material": 1.0, "luxury": 1.0},
        "C": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0},
    }
    surplus = {"food": 10.0, "raw_material": 0.0, "luxury": 0.0}
    # Transport cost of 0.10 means B's margin (0.05) is negative after cost
    transport_costs = {("A", "B"): 0.10, ("A", "C"): 0.10}

    flow = allocate_trade_flow(
        routes, origin_prices, dest_prices, surplus,
        merchant_count=5, transport_costs=transport_costs,
    )
    # Route to B should have zero food flow (margin 0.05 < cost 0.10)
    assert flow[("A", "B")]["food"] == 0.0
    # Route to C should have positive food flow (margin 1.0 > cost 0.10)
    assert flow[("A", "C")]["food"] > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_effective_margin_filters_expensive_routes -v -x`
Expected: FAIL — `allocate_trade_flow` doesn't accept `transport_costs` parameter

- [ ] **Step 3: Modify `allocate_trade_flow()`**

In `src/chronicler/economy.py:157`, add `transport_costs` parameter:

```python
def allocate_trade_flow(
    outbound_routes: list[tuple[str, str]],
    origin_prices: dict[str, float],
    dest_prices: dict[str, dict[str, float]],
    exportable_surplus: dict[str, float],
    merchant_count: int,
    transport_costs: dict[tuple[str, str], float] | None = None,
) -> dict[tuple[str, str], dict[str, float]]:
```

In the margin computation loop (~line 183), change:

```python
            raw_margin = max(d_prices.get(cat, 0.0) - origin_prices.get(cat, 0.0), 0.0)
```

To:

```python
            price_gap = d_prices.get(cat, 0.0) - origin_prices.get(cat, 0.0)
            t_cost = transport_costs.get(route, 0.0) if transport_costs else 0.0
            raw_margin = max(price_gap - t_cost, 0.0)
```

This is backward-compatible: when `transport_costs` is `None` (M42 callers), behavior is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py tests/test_economy.py -v -x`
Expected: PASS (both M42 and M43a tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add transport_costs parameter to allocate_trade_flow()"
```

---

## Chunk 3: Perishability and Stockpile Core

### Task 6: Transit Decay

**Files:**
- Modify: `src/chronicler/economy.py` (add function after transport cost section)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.economy import apply_transit_decay, map_resource_to_good, TRANSIT_DECAY


def test_transit_decay_grain():
    """Grain loses 5% in transit."""
    delivered = apply_transit_decay(100.0, "grain")
    assert delivered == 100.0 * (1.0 - TRANSIT_DECAY["grain"])


def test_transit_decay_mineral_no_loss():
    """Ore and precious have zero transit decay."""
    assert apply_transit_decay(100.0, "ore") == 100.0
    assert apply_transit_decay(100.0, "precious") == 100.0


def test_transit_decay_zero_shipped():
    """Zero shipped → zero delivered."""
    assert apply_transit_decay(0.0, "grain") == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_transit_decay_grain -v -x`
Expected: FAIL — `apply_transit_decay` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/economy.py`, after `compute_transport_cost()`:

```python
# ---------------------------------------------------------------------------
# M43a: Perishability — transit decay
# ---------------------------------------------------------------------------

def apply_transit_decay(shipped: float, good: str) -> float:
    """Apply per-good transit decay to shipped volume. Returns delivered amount."""
    rate = TRANSIT_DECAY.get(good, 0.0)
    return shipped * (1.0 - rate)
```

Note: Transit decay is applied per-route-per-good inline in `compute_economy()` (Task 13), not via a separate decomposition helper. Single-resource-slot production means each route delivers one good type.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add transit decay and per-good flow decomposition"
```

### Task 7: Storage Decay with Salt Preservation

**Files:**
- Modify: `src/chronicler/economy.py` (add function after transit decay section)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.economy import (
    apply_storage_decay,
    STORAGE_DECAY,
    SALT_PRESERVATION_FACTOR,
    MAX_PRESERVATION,
    FOOD_GOODS,
)


def test_storage_decay_grain_no_salt():
    """Grain decays at 3% per turn without salt."""
    goods = {"grain": 100.0}
    loss = apply_storage_decay(goods)
    assert abs(goods["grain"] - 97.0) < 0.01
    assert abs(loss - 3.0) < 0.01


def test_storage_decay_salt_no_decay():
    """Salt doesn't decay in storage."""
    goods = {"salt": 100.0}
    loss = apply_storage_decay(goods)
    assert goods["salt"] == 100.0
    assert loss == 0.0


def test_storage_decay_ore_no_decay():
    """Ore doesn't decay."""
    goods = {"ore": 100.0}
    loss = apply_storage_decay(goods)
    assert goods["ore"] == 100.0
    assert loss == 0.0


def test_storage_decay_salt_preserves_food():
    """Salt reduces food decay proportional to salt-to-food ratio."""
    # 20% salt ratio → hits cap (50% reduction)
    goods = {"grain": 80.0, "salt": 20.0}
    apply_storage_decay(goods)
    # With 50% preservation, grain decay = 0.03 * 0.5 = 0.015
    expected = 80.0 * (1.0 - 0.03 * 0.5)
    assert abs(goods["grain"] - expected) < 0.01
    # Salt unchanged
    assert goods["salt"] == 20.0


def test_storage_decay_partial_salt():
    """Low salt ratio gives partial preservation."""
    # 5% salt ratio → preservation = 0.05 * 2.5 = 0.125
    goods = {"grain": 95.0, "salt": 5.0}
    apply_storage_decay(goods)
    expected = 95.0 * (1.0 - 0.03 * (1.0 - 0.125))
    assert abs(goods["grain"] - expected) < 0.01


def test_storage_decay_zero_food_no_division_error():
    """Zero food stockpile doesn't cause division by zero."""
    goods = {"salt": 10.0}
    apply_storage_decay(goods)  # should not raise
    assert goods["salt"] == 10.0


def test_storage_decay_timber_not_salt_affected():
    """Salt preservation only affects food goods, not timber."""
    goods = {"timber": 100.0, "salt": 50.0}
    apply_storage_decay(goods)
    expected = 100.0 * (1.0 - STORAGE_DECAY["timber"])
    assert abs(goods["timber"] - expected) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_storage_decay_grain_no_salt -v -x`
Expected: FAIL — `apply_storage_decay` not found

- [ ] **Step 3: Write implementation**

```python
# ---------------------------------------------------------------------------
# M43a: Perishability — storage decay with salt preservation
# ---------------------------------------------------------------------------

def apply_storage_decay(goods: dict[str, float]) -> float:
    """Apply per-turn storage decay to stockpile goods dict. Mutates in place.

    Salt preservation: proportional to salt-to-food ratio, capped at MAX_PRESERVATION.
    Only affects food goods. Salt itself has zero decay.
    Returns total storage loss (for conservation law verification).
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS if g != "salt")
    salt_amount = goods.get("salt", 0.0)
    salt_ratio = salt_amount / max(total_food, 0.1)
    preservation = min(salt_ratio * SALT_PRESERVATION_FACTOR, MAX_PRESERVATION)

    total_loss = 0.0
    for good in list(goods.keys()):
        if good == "salt":
            continue  # mineral, zero decay
        rate = STORAGE_DECAY.get(good, 0.0)
        if rate <= 0.0:
            continue
        if good in FOOD_GOODS:
            rate *= (1.0 - preservation)
        old = goods[good]
        goods[good] *= (1.0 - rate)
        total_loss += old - goods[good]
    return total_loss
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add storage decay with salt preservation"
```

### Task 8: Stockpile Accumulation

**Files:**
- Modify: `src/chronicler/economy.py` (add function)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.economy import accumulate_stockpile


def test_accumulate_stockpile_basic():
    """Production minus exports plus imports accumulate."""
    goods = {"grain": 10.0}
    accumulate_stockpile(goods, production={"grain": 50.0}, exports={"grain": 20.0}, imports={"grain": 5.0})
    # 10 + (50 - 20) + 5 = 45
    assert abs(goods["grain"] - 45.0) < 0.01


def test_accumulate_stockpile_new_good():
    """Importing a good not yet in stockpile creates the entry."""
    goods = {}
    accumulate_stockpile(goods, production={}, exports={}, imports={"fish": 10.0})
    assert abs(goods["fish"] - 10.0) < 0.01


def test_accumulate_stockpile_export_only():
    """Exporting reduces stockpile to zero floor for that good."""
    goods = {"grain": 5.0}
    accumulate_stockpile(goods, production={"grain": 10.0}, exports={"grain": 15.0}, imports={})
    # 5 + (10 - 15) + 0 = 0. Note: net production can be negative, stockpile can reach 0
    assert abs(goods["grain"] - 0.0) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_accumulate_stockpile_basic -v -x`
Expected: FAIL — `accumulate_stockpile` not found

- [ ] **Step 3: Write implementation**

```python
# ---------------------------------------------------------------------------
# M43a: Stockpile operations
# ---------------------------------------------------------------------------

def accumulate_stockpile(
    goods: dict[str, float],
    production: dict[str, float],
    exports: dict[str, float],
    imports: dict[str, float],
) -> None:
    """Add (production - exports + imports) to stockpile per good. Mutates in place."""
    all_keys = set(goods.keys()) | set(production.keys()) | set(exports.keys()) | set(imports.keys())
    for good in all_keys:
        current = goods.get(good, 0.0)
        produced = production.get(good, 0.0)
        exported = exports.get(good, 0.0)
        imported = imports.get(good, 0.0)
        goods[good] = max(current + (produced - exported) + imported, 0.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add stockpile accumulation function"
```

### Task 9: food_sufficiency from Stockpile + Consumption Drawdown + Cap

**Files:**
- Modify: `src/chronicler/economy.py` (add functions)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing tests**

```python
from chronicler.economy import (
    derive_food_sufficiency_from_stockpile,
    consume_from_stockpile,
    apply_stockpile_cap,
    FOOD_GOODS,
    PER_GOOD_CAP_FACTOR,
)


def test_food_sufficiency_from_stockpile_equilibrium():
    """At equilibrium (stockpile == demand), food_sufficiency = 1.0."""
    goods = {"grain": 50.0}
    food_demand = 50.0
    result = derive_food_sufficiency_from_stockpile(goods, food_demand)
    assert abs(result - 1.0) < 0.01


def test_food_sufficiency_from_stockpile_surplus():
    """Surplus stockpile caps at 2.0."""
    goods = {"grain": 200.0}
    food_demand = 50.0
    result = derive_food_sufficiency_from_stockpile(goods, food_demand)
    assert result == 2.0


def test_food_sufficiency_from_stockpile_deficit():
    """Deficit produces value < 1.0."""
    goods = {"grain": 25.0}
    food_demand = 50.0
    result = derive_food_sufficiency_from_stockpile(goods, food_demand)
    assert abs(result - 0.5) < 0.01


def test_food_sufficiency_empty_stockpile():
    """Empty stockpile → 0.0."""
    goods = {}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert result == 0.0


def test_food_sufficiency_includes_salt():
    """Salt counts as food for sufficiency."""
    goods = {"salt": 50.0}
    result = derive_food_sufficiency_from_stockpile(goods, 50.0)
    assert abs(result - 1.0) < 0.01


def test_consume_from_stockpile_proportional():
    """Consumption is proportional to stockpile composition."""
    goods = {"grain": 60.0, "fish": 40.0}
    consume_from_stockpile(goods, food_demand=50.0)
    # 60% of 50 = 30 from grain, 40% of 50 = 20 from fish
    assert abs(goods["grain"] - 30.0) < 0.01
    assert abs(goods["fish"] - 20.0) < 0.01


def test_consume_from_stockpile_clamped():
    """Consumption can't exceed available stockpile."""
    goods = {"grain": 10.0}
    consume_from_stockpile(goods, food_demand=50.0)
    assert goods["grain"] == 0.0  # can't go negative


def test_consume_from_stockpile_empty():
    """No stockpile → nothing consumed, no error."""
    goods = {}
    consume_from_stockpile(goods, food_demand=50.0)  # should not raise


def test_stockpile_cap():
    """Goods capped at PER_GOOD_CAP_FACTOR * population."""
    goods = {"grain": 1000.0, "timber": 5.0}
    apply_stockpile_cap(goods, population=10)
    expected_cap = PER_GOOD_CAP_FACTOR * 10
    assert goods["grain"] == expected_cap
    assert goods["timber"] == 5.0  # below cap, unchanged


def test_stockpile_cap_zero_population():
    """Zero population → cap is 0, all goods zeroed."""
    goods = {"grain": 100.0}
    apply_stockpile_cap(goods, population=0)
    assert goods["grain"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_food_sufficiency_from_stockpile_equilibrium -v -x`
Expected: FAIL — `derive_food_sufficiency_from_stockpile` not found

- [ ] **Step 3: Write implementation**

```python
def derive_food_sufficiency_from_stockpile(
    goods: dict[str, float],
    food_demand: float,
) -> float:
    """Derive food_sufficiency from pre-consumption stockpile. Clamped [0.0, 2.0].

    Computed BEFORE demand drawdown (Decision 9). Sum all food goods including salt.
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS)
    d = max(food_demand, _SUPPLY_FLOOR)
    return max(0.0, min(total_food / d, 2.0))


def consume_from_stockpile(
    goods: dict[str, float],
    food_demand: float,
) -> float:
    """Draw food demand from stockpile proportional to composition. Mutates in place.

    Clamped: consumption per good can't exceed available stockpile.
    Returns total consumed (for conservation law verification).
    """
    total_food = sum(goods.get(g, 0.0) for g in FOOD_GOODS)
    if total_food <= 0.0 or food_demand <= 0.0:
        return 0.0
    total_consumed = 0.0
    for good in FOOD_GOODS:
        amount = goods.get(good, 0.0)
        if amount <= 0.0:
            continue
        share = amount / total_food
        demand_for_good = food_demand * share
        consumed = min(demand_for_good, amount)
        goods[good] = amount - consumed
        total_consumed += consumed
    return total_consumed


def apply_stockpile_cap(
    goods: dict[str, float],
    population: int,
) -> float:
    """Cap each good at PER_GOOD_CAP_FACTOR * population. Mutates in place.

    Returns total overflow (for conservation law verification).
    """
    cap = PER_GOOD_CAP_FACTOR * population
    total_overflow = 0.0
    for good in list(goods.keys()):
        if goods[good] > cap:
            total_overflow += goods[good] - cap
            goods[good] = cap
    return total_overflow
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add food_sufficiency from stockpile, consumption, and cap"
```

---

## Chunk 4: World Init, Conquest, and Analytics

### Task 10: Stockpile Initialization in world_gen.py

**Files:**
- Modify: `src/chronicler/world_gen.py:253` (after disease baseline init, before M37 faiths)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
def test_stockpile_initialization():
    """generate_world() initializes primary food stockpile for controlled regions."""
    from chronicler.world_gen import generate_world
    from chronicler.economy import map_resource_to_good, INITIAL_BUFFER

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    for region in world.regions:
        if region.controller is not None and region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            expected = INITIAL_BUFFER * region.population
            assert abs(region.stockpile.goods.get(good, 0.0) - expected) < 0.01, (
                f"Region {region.name}: expected {good}={expected}, "
                f"got {region.stockpile.goods}"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_stockpile_initialization -v -x`
Expected: FAIL — stockpile.goods is empty

- [ ] **Step 3: Write implementation**

In `src/chronicler/world_gen.py`, after line 253 (`region.resource_effective_yields = list(region.resource_base_yields)`), add a new loop (lines 243-253 iterate `world.regions` after world is created at line 217):

```python
    # M43a: Initialize stockpile for controlled regions with valid resources
    from chronicler.economy import map_resource_to_good, INITIAL_BUFFER
    for region in world.regions:
        if region.controller is not None and region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            region.stockpile.goods[good] = INITIAL_BUFFER * region.population
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/world_gen.py tests/test_economy_m43a.py
git commit -m "feat(m43a): initialize stockpile in generate_world()"
```

### Task 11: Conquest Stockpile Destruction

**Files:**
- Modify: `src/chronicler/action_engine.py:451` (after `contested.controller = attacker.name`)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
def test_conquest_stockpile_destruction():
    """Conquest destroys 50% of each good in the region's stockpile."""
    from chronicler.models import Region, RegionStockpile
    from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL

    region = Region(name="Heartland", terrain="plains", carrying_capacity=50, resources="fertile")
    region.stockpile = RegionStockpile(goods={"grain": 100.0, "timber": 40.0, "salt": 20.0})

    # Simulate conquest destruction
    for good in region.stockpile.goods:
        region.stockpile.goods[good] *= CONQUEST_STOCKPILE_SURVIVAL

    assert abs(region.stockpile.goods["grain"] - 50.0) < 0.01
    assert abs(region.stockpile.goods["timber"] - 20.0) < 0.01
    assert abs(region.stockpile.goods["salt"] - 10.0) < 0.01
```

- [ ] **Step 2: Run test to verify it passes**

This test uses the constant directly (validating the formula). The actual wiring into `_resolve_war_action()` is verified in Task 15 (integration).

Run: `python -m pytest tests/test_economy_m43a.py::test_conquest_stockpile_destruction -v -x`
Expected: PASS (uses existing model + constant)

- [ ] **Step 3: Wire into action_engine.py**

In `src/chronicler/action_engine.py`, after line 451 (`contested.controller = attacker.name`), add:

```python
            # M43a: Conquest stockpile destruction — 50% of each good lost
            from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL
            for _good in list(contested.stockpile.goods.keys()):
                contested.stockpile.goods[_good] *= CONQUEST_STOCKPILE_SURVIVAL
```

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `python -m pytest tests/ -v -x -k "war or action" --timeout=30`
Expected: PASS — existing war/action tests still pass

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/action_engine.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add conquest stockpile destruction in _resolve_war_action()"
```

### Task 12: Analytics Extractors

**Files:**
- Modify: `src/chronicler/analytics.py` (after existing `extract_resources()` ~line 184)
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write failing test**

```python
def test_extract_stockpiles_structure():
    """extract_stockpiles returns per-region per-good time series."""
    from chronicler.analytics import extract_stockpiles

    # Minimal bundle with one snapshot
    bundle = {
        "world_state": {
            "regions": [
                {"name": "Valley", "stockpile": {"goods": {"grain": 50.0, "salt": 10.0}}},
                {"name": "Hills", "stockpile": {"goods": {"ore": 30.0}}},
            ],
        },
        "history": [
            {"turn": 10, "world_state": {
                "regions": [
                    {"name": "Valley", "stockpile": {"goods": {"grain": 45.0, "salt": 12.0}}},
                    {"name": "Hills", "stockpile": {"goods": {"ore": 28.0}}},
                ],
            }},
        ],
    }
    result = extract_stockpiles([bundle], checkpoints=[10])
    assert "Valley" in result
    assert "grain" in result["Valley"]
    assert result["Valley"]["grain"][10] == 45.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_extract_stockpiles_structure -v -x`
Expected: FAIL — `extract_stockpiles` not found

- [ ] **Step 3: Write implementation**

In `src/chronicler/analytics.py`, after `extract_resources()`:

```python
def extract_stockpiles(
    bundles: list[dict],
    checkpoints: list[int] | None = None,
) -> dict:
    """Per-region per-good stockpile levels at checkpoints.

    Returns: {region_name: {good_name: {turn: level}}}
    """
    if not bundles:
        return {}
    bundle = bundles[0]
    if checkpoints is None:
        checkpoints = [50, 100, 200, 300, 400, 500]

    result: dict[str, dict[str, dict[int, float]]] = {}
    for turn in checkpoints:
        snapshot = _snapshot_at_turn(bundle, turn)
        if snapshot is None:
            continue
        for region_data in snapshot.get("regions", []):
            rname = region_data.get("name", "")
            stockpile = region_data.get("stockpile", {}).get("goods", {})
            if rname not in result:
                result[rname] = {}
            for good, amount in stockpile.items():
                if good not in result[rname]:
                    result[rname][good] = {}
                result[rname][good][turn] = amount
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/analytics.py tests/test_economy_m43a.py
git commit -m "feat(m43a): add extract_stockpiles() analytics extractor"
```

---

## Chunk 5: compute_economy() Integration and Conservation Law

### Task 13: Integrate M43a into compute_economy()

**Files:**
- Modify: `src/chronicler/economy.py:321-517` (`compute_economy()`)
- Test: `tests/test_economy_m43a.py`

This is the central integration task. `compute_economy()` is modified to:
1. Build river route set for transport cost lookups
2. Compute per-route transport costs and pass to `allocate_trade_flow()`
3. Decompose category-level imports to per-good with transit decay
4. Accumulate stockpile (production - exports + imports)
5. Compute `food_sufficiency` from pre-consumption stockpile
6. Draw consumption from stockpile
7. Apply storage decay with salt preservation
8. Cap stockpile

- [ ] **Step 1: Write integration test**

```python
def test_compute_economy_stockpile_integration():
    """compute_economy() accumulates stockpile and derives food_sufficiency from it."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, FOOD_GOODS, PER_CAPITA_FOOD
    from chronicler.models import Region, Civilization, WorldState, RegionStockpile

    # Set up a minimal world with 2 regions, 1 civ
    r1 = Region(name="Valley", terrain="plains", carrying_capacity=50, resources="fertile",
                controller="Aram", resource_types=[0, 255, 255],  # GRAIN
                resource_base_yields=[1.0, 0.0, 0.0],
                resource_effective_yields=[1.0, 0.0, 0.0])
    r1.stockpile = RegionStockpile(goods={"grain": 20.0})
    r1.adjacencies = ["Hills"]

    r2 = Region(name="Hills", terrain="mountains", carrying_capacity=30, resources="mineral",
                controller="Aram", resource_types=[5, 255, 255],  # ORE
                resource_base_yields=[0.5, 0.0, 0.0],
                resource_effective_yields=[0.5, 0.0, 0.0])
    r2.adjacencies = ["Valley"]

    civ = Civilization(name="Aram", regions=["Valley", "Hills"], capital_region="Valley")
    world = MagicMock()
    world.regions = [r1, r2]
    world.civilizations = [civ]
    world.rivers = []
    world.turn = 10

    # Fake snapshot: Valley has 10 farmers, Hills has 5 soldiers
    n_agents = 15
    regions_arr = np.array([0]*10 + [1]*5, dtype=np.int32)
    occupations_arr = np.array([0]*10 + [1]*5, dtype=np.int32)  # 0=farmer, 1=soldier
    wealth_arr = np.zeros(n_agents, dtype=np.float32)
    civ_arr = np.zeros(n_agents, dtype=np.int32)

    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occupations_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })

    region_map = {"Valley": r1, "Hills": r2}
    result = compute_economy(world, snapshot, region_map, agent_mode=True, active_trade_routes=[])

    # Valley should have accumulated grain in stockpile
    assert r1.stockpile.goods.get("grain", 0.0) > 0.0
    # food_sufficiency should be derived from stockpile, not single-turn supply
    assert "Valley" in result.food_sufficiency
    assert result.food_sufficiency["Valley"] > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy_m43a.py::test_compute_economy_stockpile_integration -v -x`
Expected: FAIL — `compute_economy()` doesn't touch stockpile yet

- [ ] **Step 3: Modify compute_economy()**

The modifications to `compute_economy()` in `src/chronicler/economy.py`:

**3a.** Add `from chronicler.resources import get_season_id` at the top of the function.

**3b.** After the civ_lookup/region_idx_map setup (~line 350), build the river route set:

```python
    river_pairs = build_river_route_set(world.rivers) if hasattr(world, 'rivers') and world.rivers else set()
    is_winter = get_season_id(world.turn) == 3
```

**3c.** In the trade flow section (~line 396-438), compute transport costs per route and pass to `allocate_trade_flow()`:

After building `origin_routes` (~line 410), before the flow allocation loop (~line 416), build transport costs:

```python
    # M43a: Compute transport costs per route
    route_transport_costs: dict[tuple[str, str], float] = {}
    for origin_name, routes in origin_routes.items():
        origin_region = region_map.get(origin_name)
        if origin_region is None:
            continue
        for route in routes:
            _, dest_name = route
            dest_region = region_map.get(dest_name)
            if dest_region is None:
                continue
            is_river = frozenset({origin_name, dest_name}) in river_pairs
            is_coastal = origin_region.terrain == "coast" and dest_region.terrain == "coast"
            route_transport_costs[route] = compute_transport_cost(
                origin_region.terrain, dest_region.terrain,
                is_river=is_river, is_coastal=is_coastal, is_winter=is_winter,
            )
```

Then pass `transport_costs=route_transport_costs` to `allocate_trade_flow()` call (~line 425).

**3d.** After the imports aggregation loop (~line 438), add per-good decomposition with transit decay:

```python
    # M43a: Decompose category-level imports to per-good with transit decay
    region_per_good_imports: dict[str, dict[str, float]] = {}
    region_per_good_exports: dict[str, dict[str, float]] = {}
    region_per_good_production: dict[str, dict[str, float]] = {}

    for region in regions:
        rname = region.name
        # Per-good production
        if region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            prod_amount = region_production.get(rname, _empty_category_dict())
            cat = map_resource_to_category(region.resource_types[0])
            region_per_good_production[rname] = {good: prod_amount.get(cat, 0.0)}
        else:
            region_per_good_production[rname] = {}

        # Per-good exports (single resource slot → all exports of that category are one good)
        if region.resource_types[0] != 255:
            good = map_resource_to_good(region.resource_types[0])
            cat = map_resource_to_category(region.resource_types[0])
            region_per_good_exports[rname] = {good: region_exports.get(rname, _empty_category_dict()).get(cat, 0.0)}
        else:
            region_per_good_exports[rname] = {}

    # Per-good imports with transit decay (per-route, per-good, decay before aggregate)
    for rname in region_production:
        region_per_good_imports[rname] = {}

    for origin_name, route_flows in all_route_flows.items():
        origin_region = region_map.get(origin_name)
        if origin_region is None or origin_region.resource_types[0] == 255:
            continue
        source_good = map_resource_to_good(origin_region.resource_types[0])
        for route, cat_flows in route_flows.items():
            _, dest_name = route
            for cat in CATEGORIES:
                shipped = cat_flows[cat]
                if shipped <= 0.0:
                    continue
                if map_resource_to_category(origin_region.resource_types[0]) != cat:
                    continue
                delivered = apply_transit_decay(shipped, source_good)
                dest_imports = region_per_good_imports.setdefault(dest_name, {})
                dest_imports[source_good] = dest_imports.get(source_good, 0.0) + delivered
```

**3e.** After post-trade prices computation (~line 447), add the stockpile sub-sequence (steps 2g-2k):

```python
    # --- M43a: Steps 2g-2k — Stockpile sub-sequence ---
    for region in regions:
        rname = region.name
        demand = region_demand.get(rname, _empty_category_dict())

        # Step 2g: Stockpile accumulation
        accumulate_stockpile(
            region.stockpile.goods,
            production=region_per_good_production.get(rname, {}),
            exports=region_per_good_exports.get(rname, {}),
            imports=region_per_good_imports.get(rname, {}),
        )

        # Step 2h: food_sufficiency from pre-consumption stockpile
        food_demand = demand.get("food", 0.0)
        result.food_sufficiency[rname] = derive_food_sufficiency_from_stockpile(
            region.stockpile.goods, food_demand,
        )

        # Step 2i: Demand drawdown from stockpile (clamped)
        consume_from_stockpile(region.stockpile.goods, food_demand)

        # Step 2j: Storage decay with salt preservation
        apply_storage_decay(region.stockpile.goods)

        # Step 2k: Cap stockpile
        agent_data = region_agent_data.get(rname, {})
        apply_stockpile_cap(region.stockpile.goods, agent_data.get("population", 0))
```

**3f.** In the signal derivation loop (~line 464), remove the old `food_sufficiency` computation (it's now done in the stockpile sub-sequence above). Comment out or delete:

```python
        # REMOVED by M43a — food_sufficiency now derived from stockpile in step 2h
        # result.food_sufficiency[rname] = derive_food_sufficiency(
        #     post_supply.get("food", 0.0), demand.get("food", 0.0),
        # )
```

- [ ] **Step 4: Run M42 regression tests**

Run: `python -m pytest tests/test_economy.py -v -x`
Expected: All M42 tests PASS — backward compatible

- [ ] **Step 5: Run M43a tests**

Run: `python -m pytest tests/test_economy_m43a.py -v -x`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "feat(m43a): integrate stockpile sub-sequence into compute_economy()"
```

### Task 14: Conservation Law Test

**Files:**
- Modify: `src/chronicler/economy.py` (add `conservation_totals` field to `EconomyResult`)
- Test: `tests/test_economy_m43a.py`

The conservation law requires tracking all loss terms: transit loss, consumption, storage loss, cap overflow. These are returned by the helper functions (`apply_storage_decay`, `consume_from_stockpile`, `apply_stockpile_cap`) and accumulated in `compute_economy()` into a new `EconomyResult` field.

- [ ] **Step 1: Add conservation tracking to EconomyResult**

In `src/chronicler/economy.py`, add to `EconomyResult` after `tithe_base`:

```python
    # M43a: Conservation law tracking (for testing)
    conservation: dict[str, float] = field(default_factory=lambda: {
        "transit_loss": 0.0, "consumption": 0.0, "storage_loss": 0.0, "cap_overflow": 0.0,
    })
```

- [ ] **Step 2: Accumulate conservation terms in compute_economy()**

In the stockpile sub-sequence (Task 13 step 3e), update the calls to track losses:

```python
        # Step 2i: Demand drawdown from stockpile (clamped)
        consumed = consume_from_stockpile(region.stockpile.goods, food_demand)
        result.conservation["consumption"] += consumed

        # Step 2j: Storage decay with salt preservation
        storage_loss = apply_storage_decay(region.stockpile.goods)
        result.conservation["storage_loss"] += storage_loss

        # Step 2k: Cap stockpile
        agent_data = region_agent_data.get(rname, {})
        cap_overflow = apply_stockpile_cap(region.stockpile.goods, agent_data.get("population", 0))
        result.conservation["cap_overflow"] += cap_overflow
```

For transit loss, in the per-good import decomposition loop (Task 13 step 3d), track:

```python
                transit_loss = shipped - delivered
                result.conservation["transit_loss"] += transit_loss
```

- [ ] **Step 3: Write conservation law test**

```python
def test_conservation_law():
    """Global balance: old_stockpile + production = new_stockpile + consumption + transit_loss + storage_loss + cap_overflow."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, ALL_GOODS
    from chronicler.models import Region, Civilization, RegionStockpile

    # Two regions, one trade route between them
    r1 = Region(name="Breadbasket", terrain="plains", carrying_capacity=50, resources="fertile",
                controller="Alpha", resource_types=[0, 255, 255],  # GRAIN
                resource_base_yields=[2.0, 0.0, 0.0],
                resource_effective_yields=[2.0, 0.0, 0.0])
    r1.stockpile = RegionStockpile(goods={"grain": 50.0})
    r1.adjacencies = ["Port"]

    r2 = Region(name="Port", terrain="coast", carrying_capacity=30, resources="maritime",
                controller="Beta", resource_types=[3, 255, 255],  # FISH
                resource_base_yields=[1.0, 0.0, 0.0],
                resource_effective_yields=[1.0, 0.0, 0.0])
    r2.stockpile = RegionStockpile(goods={"fish": 20.0})
    r2.adjacencies = ["Breadbasket"]

    civ_a = Civilization(name="Alpha", regions=["Breadbasket"], capital_region="Breadbasket")
    civ_b = Civilization(name="Beta", regions=["Port"], capital_region="Port")
    world = MagicMock()
    world.regions = [r1, r2]
    world.civilizations = [civ_a, civ_b]
    world.rivers = []
    world.turn = 10

    # Record old stockpile totals
    old_total = sum(
        amt for r in [r1, r2] for amt in r.stockpile.goods.values()
    )

    # Snapshot: Breadbasket has 20 farmers + 5 merchants, Port has 10 farmers
    n = 35
    regions_arr = np.array([0]*25 + [1]*10, dtype=np.int32)
    occ_arr = np.array([0]*20 + [2]*5 + [0]*10, dtype=np.int32)
    wealth_arr = np.zeros(n, dtype=np.float32)
    civ_arr = np.array([0]*25 + [1]*10, dtype=np.int32)
    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occ_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })
    region_map = {"Breadbasket": r1, "Port": r2}

    result = compute_economy(
        world, snapshot, region_map, agent_mode=True,
        active_trade_routes=[("Alpha", "Beta")],
    )

    # Record new stockpile totals
    new_total = sum(
        amt for r in [r1, r2] for amt in r.stockpile.goods.values()
    )

    # Compute total production (grain from 20 farmers × 2.0 yield + fish from 10 farmers × 1.0 yield)
    total_production = 20 * 2.0 + 10 * 1.0  # 50 grain + 10 fish = 60

    # Conservation law: old + production = new + consumption + transit_loss + storage_loss + cap_overflow
    c = result.conservation
    inputs = old_total + total_production
    outputs = new_total + c["consumption"] + c["transit_loss"] + c["storage_loss"] + c["cap_overflow"]
    assert abs(inputs - outputs) < 0.01, (
        f"Conservation violated: inputs={inputs:.2f}, outputs={outputs:.2f}, "
        f"diff={abs(inputs - outputs):.4f}, conservation={c}"
    )
    # Also verify no negative stockpiles
    for r in [r1, r2]:
        for good, amt in r.stockpile.goods.items():
            assert amt >= 0.0, f"Negative stockpile: {r.name}.{good} = {amt}"
```

- [ ] **Step 4: Run test**

Run: `python -m pytest tests/test_economy_m43a.py::test_conservation_law -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy_m43a.py
git commit -m "test(m43a): add conservation law test with exact global balance verification"
```

### Task 15: Backward Compatibility Test

**Files:**
- Test: `tests/test_economy_m43a.py`

- [ ] **Step 1: Write backward compat test (full path)**

```python
def test_food_sufficiency_backward_compat_full_path():
    """Full compute_economy at equilibrium produces food_sufficiency ≈ 1.0 (matches M42)."""
    from unittest.mock import MagicMock
    import numpy as np
    import pyarrow as pa
    from chronicler.economy import compute_economy, PER_CAPITA_FOOD
    from chronicler.models import Region, Civilization, RegionStockpile

    # One region, no trade (isolated). Production = demand.
    pop = 20
    food_demand = pop * PER_CAPITA_FOOD
    # Set yield so farmer_count × yield = food_demand
    region = Region(name="Valley", terrain="plains", carrying_capacity=50, resources="fertile",
                    controller="Aram", resource_types=[0, 255, 255],
                    resource_base_yields=[food_demand / pop, 0.0, 0.0],
                    resource_effective_yields=[food_demand / pop, 0.0, 0.0])
    region.stockpile = RegionStockpile(goods={})  # empty — no prior buffer
    civ = Civilization(name="Aram", regions=["Valley"], capital_region="Valley")

    world = MagicMock()
    world.regions = [region]
    world.civilizations = [civ]
    world.rivers = []
    world.turn = 10

    # All agents are farmers
    regions_arr = np.zeros(pop, dtype=np.int32)
    occ_arr = np.zeros(pop, dtype=np.int32)  # 0 = farmer
    wealth_arr = np.zeros(pop, dtype=np.float32)
    civ_arr = np.zeros(pop, dtype=np.int32)
    snapshot = pa.RecordBatch.from_pydict({
        "region": pa.array(regions_arr, type=pa.int32()),
        "occupation": pa.array(occ_arr, type=pa.int32()),
        "wealth": pa.array(wealth_arr, type=pa.float32()),
        "civ_affinity": pa.array(civ_arr, type=pa.int32()),
    })

    result = compute_economy(world, snapshot, {"Valley": region}, agent_mode=True, active_trade_routes=[])
    assert abs(result.food_sufficiency["Valley"] - 1.0) < 0.01, (
        f"Expected food_sufficiency ≈ 1.0, got {result.food_sufficiency['Valley']}"
    )
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_economy_m43a.py::test_food_sufficiency_backward_compat_full_path -v -x`
Expected: PASS

- [ ] **Step 3: Write geographic price gradient test**

```python
def test_transport_cost_mountain_vs_river():
    """Mountain routes are more expensive than river routes."""
    from chronicler.economy import compute_transport_cost

    mountain = compute_transport_cost("plains", "mountains", is_river=False, is_coastal=False, is_winter=False)
    river = compute_transport_cost("plains", "plains", is_river=True, is_coastal=False, is_winter=False)
    assert mountain > river * 3, f"Mountain ({mountain}) should be much more than river ({river})"
```

- [ ] **Step 4: Run all M43a tests**

Run: `python -m pytest tests/test_economy_m43a.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All PASS — no regressions

- [ ] **Step 6: Commit**

```bash
git add tests/test_economy_m43a.py
git commit -m "test(m43a): add backward compatibility and geographic differentiation tests"
```

### Task 16: Wire simulation.py (if needed)

**Files:**
- Modify: `src/chronicler/simulation.py:1204-1217` (Phase 2 economy call)

- [ ] **Step 1: Verify current integration**

Check if `compute_economy()` already receives `world` (which carries `region.stockpile`). Looking at line 1213-1216:

```python
economy_result = compute_economy(
    world, snapshot, region_map, agent_mode=True,
    active_trade_routes=active_routes,
)
```

Since `world.regions` includes each `region.stockpile` (Pydantic models are mutable), and `compute_economy()` already receives `world` and `region_map`, stockpile mutations happen in-place on the region objects. **No additional `simulation.py` changes are needed** — the stockpile is already accessible via `world.regions[i].stockpile`.

- [ ] **Step 2: Run full integration test**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 3: Skip commit if no changes needed**

If `simulation.py` requires no modifications (stockpile is accessible via `world.regions[i].stockpile` which `compute_economy()` already receives), no commit needed.

---

## Summary

| Chunk | Tasks | What it delivers |
|---|---|---|
| 1 | 1-3 | Data model, constants, mapping function |
| 2 | 4-5 | Transport cost computation + effective margin |
| 3 | 6-9 | Transit decay, storage decay, stockpile accumulation, food_sufficiency, consumption, cap |
| 4 | 10-12 | World init, conquest destruction, analytics |
| 5 | 13-16 | compute_economy() integration, conservation law, backward compat, regression check |

**Total: 16 tasks, 5 chunks.** All Python-side, no Rust changes.
