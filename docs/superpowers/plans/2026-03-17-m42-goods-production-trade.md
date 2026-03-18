# M42: Goods Production & Trade — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add regional goods production, merchant trade flows, and supply-demand pricing that drives agent economic behavior through four FFI signals.

**Architecture:** New `economy.py` module owns all goods computation (production → demand → pre-trade prices → trade flow → post-trade prices → signals). Called from `simulation.py` Phase 2 before existing treasury logic. Four per-region signals cross FFI to Rust (`farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`) plus one per-civ signal (`priest_tithe_share`). Rust wealth tick and satisfaction formulas updated to consume these signals. Includes four M41 deferred economic integrations.

**Tech Stack:** Python (economy computation, signal derivation), Rust (wealth accumulation, satisfaction), Arrow FFI (signal transport), PyO3 (bindings)

**Spec:** `docs/superpowers/specs/2026-03-17-m42-goods-production-trade-design.md`

---

## File Structure

| File | Role | Action |
|------|------|--------|
| `src/chronicler/economy.py` | All goods computation: production, demand, prices, trade flow, signals, M41 integrations | **Create** |
| `tests/test_economy.py` | Unit tests for economy module | **Create** |
| `src/chronicler/simulation.py` | Phase 2: call `compute_economy()`, apply results | **Modify** (~line 215) |
| `src/chronicler/agent_bridge.py` | Wire 4 RegionState signals + 1 CivSignals field | **Modify** (`build_region_batch`, `build_signals`) |
| `src/chronicler/factions.py` | Update `compute_tithe_base()` for agent mode | **Modify** (~line 257) |
| `src/chronicler/analytics.py` | Price time series extractors | **Modify** (add extractor) |
| `chronicler-agents/src/region.rs` | Add 4 fields to `RegionState` | **Modify** (~line 54) |
| `chronicler-agents/src/ffi.rs` | Parse 4 new Arrow columns into `RegionState` | **Modify** |
| `chronicler-agents/src/signals.rs` | Add `priest_tithe_share` to `CivSignals` | **Modify** (~line 34) |
| `chronicler-agents/src/agent.rs` | Replace `FARMER_INCOME`/`MINER_INCOME` with `BASE_FARMER_INCOME`; remove `MERCHANT_INCOME`, `MERCHANT_BASELINE`, `is_extractive()` | **Modify** (~lines 147-166) |
| `chronicler-agents/src/tick.rs` | New farmer/merchant/priest income formulas | **Modify** (~lines 361-389) |
| `chronicler-agents/src/satisfaction.rs` | Add `food_sufficiency`/`merchant_margin` to `SatisfactionInputs`; new penalty + replacement | **Modify** |
| `chronicler-agents/tests/` | Rust integration tests for new signals | **Modify** |

---

## Chunk 1: Python Economy Module

### Task 1: Category mapping and constants

**Files:**
- Create: `src/chronicler/economy.py`
- Create: `tests/test_economy.py`

- [ ] **Step 1: Write failing test for `map_resource_to_category`**

```python
# tests/test_economy.py
"""Unit tests for M42 goods production & trade economy module."""

from chronicler.economy import map_resource_to_category, CATEGORIES


def test_map_resource_to_category_food():
    """GRAIN, BOTANICALS, FISH, SALT, EXOTIC → food."""
    assert map_resource_to_category(0) == "food"    # GRAIN
    assert map_resource_to_category(2) == "food"    # BOTANICALS
    assert map_resource_to_category(3) == "food"    # FISH
    assert map_resource_to_category(4) == "food"    # SALT
    assert map_resource_to_category(7) == "food"    # EXOTIC


def test_map_resource_to_category_raw_material():
    """TIMBER, ORE → raw_material."""
    assert map_resource_to_category(1) == "raw_material"  # TIMBER
    assert map_resource_to_category(5) == "raw_material"  # ORE


def test_map_resource_to_category_luxury():
    """PRECIOUS → luxury."""
    assert map_resource_to_category(6) == "luxury"  # PRECIOUS


def test_categories_constant():
    """Three categories, ordered."""
    assert CATEGORIES == ("food", "raw_material", "luxury")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chronicler.economy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/chronicler/economy.py
"""M42: Goods production, trade flow, and supply-demand pricing.

Computes regional goods production from farmer counts × resource yields,
routes surplus along M35 trade corridors via margin-weighted pro-rata
allocation, derives per-region prices from supply/demand ratios, and
produces FFI signals for Rust agent behavior.

Called from simulation.py Phase 2 before existing treasury logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants  [CALIBRATE] — all tunable, see spec for tuning targets
# ---------------------------------------------------------------------------

BASE_PRICE: float = 1.0
PER_CAPITA_FOOD: float = 0.5
RAW_MATERIAL_PER_SOLDIER: float = 0.3
LUXURY_PER_WEALTHY_AGENT: float = 0.2
LUXURY_DEMAND_THRESHOLD: float = 10.0
CARRY_PER_MERCHANT: float = 1.0
FARMER_INCOME_MODIFIER_FLOOR: float = 0.5
FARMER_INCOME_MODIFIER_CAP: float = 3.0
MERCHANT_MARGIN_NORMALIZER: float = 5.0
TAX_RATE: float = 0.05

CATEGORIES: tuple[str, ...] = ("food", "raw_material", "luxury")

_CATEGORY_MAP: dict[int, str] = {
    0: "food",          # GRAIN
    1: "raw_material",  # TIMBER
    2: "food",          # BOTANICALS
    3: "food",          # FISH
    4: "food",          # SALT
    5: "raw_material",  # ORE
    6: "luxury",        # PRECIOUS
    7: "food",          # EXOTIC
}


def map_resource_to_category(resource_type: int) -> str:
    """Map M34 resource type enum value to one of three goods categories."""
    return _CATEGORY_MAP[resource_type]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add economy module with category mapping and constants"
```

---

### Task 2: Data containers

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write test for RegionGoods and EconomyResult construction**

```python
# tests/test_economy.py — append
from chronicler.economy import RegionGoods, EconomyResult, _empty_category_dict


def test_region_goods_construction():
    """RegionGoods holds per-category production, imports, exports, prices."""
    rg = RegionGoods()
    assert rg.production == {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    assert rg.imports == {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    assert rg.exports == {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    assert rg.prices == {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}


def test_economy_result_construction():
    """EconomyResult is a flat container for all Phase 2 outputs."""
    er = EconomyResult()
    assert er.region_goods == {}
    assert er.farmer_income_modifiers == {}
    assert er.food_sufficiency == {}
    assert er.merchant_margins == {}
    assert er.merchant_trade_incomes == {}
    assert er.priest_tithe_shares == {}
    assert er.treasury_tax == {}
    assert er.tithe_base == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py::test_region_goods_construction tests/test_economy.py::test_economy_result_construction -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append after map_resource_to_category

def _empty_category_dict() -> dict[str, float]:
    """Return zeroed dict for all three categories."""
    return {cat: 0.0 for cat in CATEGORIES}


@dataclass
class RegionGoods:
    """Transient per-region goods state for one turn. Not persisted."""

    production: dict[str, float] = field(default_factory=_empty_category_dict)
    imports: dict[str, float] = field(default_factory=_empty_category_dict)
    exports: dict[str, float] = field(default_factory=_empty_category_dict)
    prices: dict[str, float] = field(default_factory=_empty_category_dict)


@dataclass
class EconomyResult:
    """Output of compute_economy(). Consumed by simulation.py, then dropped."""

    region_goods: dict[str, RegionGoods] = field(default_factory=dict)
    farmer_income_modifiers: dict[str, float] = field(default_factory=dict)
    food_sufficiency: dict[str, float] = field(default_factory=dict)
    merchant_margins: dict[str, float] = field(default_factory=dict)
    merchant_trade_incomes: dict[str, float] = field(default_factory=dict)
    trade_route_counts: dict[str, int] = field(default_factory=dict)
    priest_tithe_shares: dict[int, float] = field(default_factory=dict)
    treasury_tax: dict[int, float] = field(default_factory=dict)
    tithe_base: dict[int, float] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add RegionGoods and EconomyResult data containers"
```

---

### Task 3: Production computation

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for `compute_production`**

```python
# tests/test_economy.py — append
from chronicler.economy import compute_production


def test_compute_production_grain_region():
    """Grain region (type 0) with 50 farmers and yield 1.2 → food = 60.0."""
    result = compute_production(resource_type=0, resource_yield=1.2, farmer_count=50)
    assert result == ("food", 60.0)


def test_compute_production_ore_region():
    """Ore region (type 5) with 30 farmers and yield 0.8 → raw_material = 24.0."""
    result = compute_production(resource_type=5, resource_yield=0.8, farmer_count=30)
    assert result == ("raw_material", 24.0)


def test_compute_production_precious_region():
    """Precious region (type 6) with 10 farmers and yield 0.5 → luxury = 5.0."""
    result = compute_production(resource_type=6, resource_yield=0.5, farmer_count=10)
    assert result == ("luxury", 5.0)


def test_compute_production_zero_farmers():
    """Zero farmers → zero production regardless of yield."""
    result = compute_production(resource_type=0, resource_yield=1.5, farmer_count=0)
    assert result == ("food", 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "compute_production" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

def compute_production(
    resource_type: int,
    resource_yield: float,
    farmer_count: int,
) -> tuple[str, float]:
    """Compute goods output for a region.

    Returns (category, amount). Only primary resource slot (index 0) is used.
    """
    category = map_resource_to_category(resource_type)
    amount = resource_yield * farmer_count
    return category, amount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add compute_production function"
```

---

### Task 4: Demand computation

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for `compute_demand`**

```python
# tests/test_economy.py — append
from chronicler.economy import compute_demand


def test_compute_demand_food():
    """Food demand = population × PER_CAPITA_FOOD."""
    demand = compute_demand(population=100, soldier_count=20, wealthy_count=5)
    assert demand["food"] == 100 * 0.5  # PER_CAPITA_FOOD = 0.5


def test_compute_demand_raw_material():
    """Raw material demand = soldier_count × RAW_MATERIAL_PER_SOLDIER."""
    demand = compute_demand(population=100, soldier_count=20, wealthy_count=5)
    assert demand["raw_material"] == 20 * 0.3  # RAW_MATERIAL_PER_SOLDIER = 0.3


def test_compute_demand_luxury():
    """Luxury demand = wealthy_count × LUXURY_PER_WEALTHY_AGENT."""
    demand = compute_demand(population=100, soldier_count=20, wealthy_count=5)
    assert demand["luxury"] == 5 * 0.2  # LUXURY_PER_WEALTHY_AGENT = 0.2


def test_compute_demand_zero_pop():
    """Zero population → zero food demand."""
    demand = compute_demand(population=0, soldier_count=0, wealthy_count=0)
    assert demand["food"] == 0.0
    assert demand["raw_material"] == 0.0
    assert demand["luxury"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "compute_demand" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

def compute_demand(
    population: int,
    soldier_count: int,
    wealthy_count: int,
) -> dict[str, float]:
    """Compute per-region demand for each goods category.

    Args:
        population: total agent count in region (everyone eats)
        soldier_count: agents with occupation == Soldier
        wealthy_count: agents with wealth > LUXURY_DEMAND_THRESHOLD
    """
    return {
        "food": population * PER_CAPITA_FOOD,
        "raw_material": soldier_count * RAW_MATERIAL_PER_SOLDIER,
        "luxury": wealthy_count * LUXURY_PER_WEALTHY_AGENT,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add compute_demand function"
```

---

### Task 5: Price computation (two-pass)

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for `compute_prices`**

```python
# tests/test_economy.py — append
from chronicler.economy import compute_prices, BASE_PRICE


def test_compute_prices_balanced():
    """Equal supply and demand → price = BASE_PRICE."""
    supply = {"food": 50.0, "raw_material": 10.0, "luxury": 5.0}
    demand = {"food": 50.0, "raw_material": 10.0, "luxury": 5.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE
    assert prices["raw_material"] == BASE_PRICE
    assert prices["luxury"] == BASE_PRICE


def test_compute_prices_surplus():
    """Supply > demand → price < BASE_PRICE."""
    supply = {"food": 100.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 100.0)  # 0.5


def test_compute_prices_deficit():
    """Demand > supply → price > BASE_PRICE."""
    supply = {"food": 25.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 25.0)  # 2.0


def test_compute_prices_zero_supply():
    """Zero supply → price uses floor of 0.1 to avoid division by zero."""
    supply = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 0.1)  # 500.0
    assert prices["raw_material"] == 0.0  # 0/0.1 = 0


def test_compute_prices_no_nan():
    """Zero supply AND zero demand → price = 0, not NaN."""
    supply = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    for cat in prices:
        assert not math.isnan(prices[cat])
        assert not math.isinf(prices[cat])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "compute_prices" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

_SUPPLY_FLOOR: float = 0.1


def compute_prices(
    supply: dict[str, float],
    demand: dict[str, float],
) -> dict[str, float]:
    """Compute price per category from supply/demand ratio.

    price = BASE_PRICE × (demand / max(supply, 0.1))

    Used for both pre-trade prices (supply = production only) and
    post-trade prices (supply = production + imports). Caller controls
    what goes into the supply dict.
    """
    prices: dict[str, float] = {}
    for cat in CATEGORIES:
        d = demand.get(cat, 0.0)
        s = max(supply.get(cat, 0.0), _SUPPLY_FLOOR)
        prices[cat] = BASE_PRICE * (d / s)
    return prices
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 19 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add compute_prices function (two-pass compatible)"
```

---

### Task 6: Trade route decomposition

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for `decompose_trade_routes`**

```python
# tests/test_economy.py — append
from chronicler.economy import decompose_trade_routes


def _make_mock_region(name, adjacency, controller):
    """Minimal mock region for trade route tests."""
    class R:
        pass
    r = R()
    r.name = name
    r.adjacency = adjacency
    return r


def test_decompose_single_boundary():
    """Two civs sharing one border → one boundary pair."""
    civ_a_regions = {"A1"}
    region_map = {
        "A1": _make_mock_region("A1", ["B1", "A2"], "civ_a"),
        "B1": _make_mock_region("B1", ["A1"], "civ_b"),
        "A2": _make_mock_region("A2", ["A1"], "civ_a"),
    }
    pairs = decompose_trade_routes(civ_a_regions, {"B1"}, region_map)
    assert pairs == [("A1", "B1")]


def test_decompose_long_border():
    """Long border → multiple boundary pairs."""
    civ_a_regions = {"A1", "A2"}
    civ_b_regions = {"B1", "B2"}
    region_map = {
        "A1": _make_mock_region("A1", ["B1"], "civ_a"),
        "A2": _make_mock_region("A2", ["B2"], "civ_a"),
        "B1": _make_mock_region("B1", ["A1"], "civ_b"),
        "B2": _make_mock_region("B2", ["A2"], "civ_b"),
    }
    pairs = decompose_trade_routes(civ_a_regions, civ_b_regions, region_map)
    assert sorted(pairs) == [("A1", "B1"), ("A2", "B2")]


def test_decompose_no_border():
    """Non-adjacent civs → no boundary pairs."""
    region_map = {
        "A1": _make_mock_region("A1", ["A2"], "civ_a"),
        "A2": _make_mock_region("A2", ["A1"], "civ_a"),
        "B1": _make_mock_region("B1", ["B2"], "civ_b"),
        "B2": _make_mock_region("B2", ["B1"], "civ_b"),
    }
    pairs = decompose_trade_routes({"A1", "A2"}, {"B1", "B2"}, region_map)
    assert pairs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "decompose" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

def decompose_trade_routes(
    civ_a_regions: set[str],
    civ_b_regions: set[str],
    region_map: dict,
) -> list[tuple[str, str]]:
    """Decompose a civ-level trade route into region-level boundary pairs.

    Returns list of (region_a, region_b) where region_a ∈ civ_a,
    region_b ∈ civ_b, and the two regions are adjacent.
    """
    pairs: list[tuple[str, str]] = []
    for region_name in civ_a_regions:
        region = region_map[region_name]
        for neighbor_name in region.adjacency:
            if neighbor_name in civ_b_regions:
                pairs.append((region_name, neighbor_name))
    return pairs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 22 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add decompose_trade_routes for civ→region route resolution"
```

---

### Task 7: Trade flow allocation (log-dampened margin-weighted pro-rata)

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for `allocate_trade_flow`**

```python
# tests/test_economy.py — append
from chronicler.economy import allocate_trade_flow


def test_allocate_single_route_single_category():
    """One route, one category with surplus → full capacity allocated."""
    outbound_routes = [("A", "B")]
    origin_prices = {"food": 0.5, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {"B": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0}}
    surplus = {"food": 10.0, "raw_material": 0.0, "luxury": 0.0}
    merchant_count = 5

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count,
    )
    # 5 merchants × 1.0 carry = 5.0 capacity, surplus = 10.0, so export = 5.0
    assert flow[("A", "B")]["food"] == 5.0


def test_allocate_no_margin():
    """No price differential → zero flow."""
    outbound_routes = [("A", "B")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {"B": {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}}
    surplus = {"food": 10.0, "raw_material": 0.0, "luxury": 0.0}

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count=5,
    )
    total = sum(flow[("A", "B")].values())
    assert total == 0.0


def test_allocate_negative_margin():
    """Destination price lower than origin → zero flow (no negative-margin trade)."""
    outbound_routes = [("A", "B")]
    origin_prices = {"food": 2.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {"B": {"food": 0.5, "raw_material": 1.0, "luxury": 1.0}}
    surplus = {"food": 10.0, "raw_material": 0.0, "luxury": 0.0}

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count=5,
    )
    assert flow[("A", "B")]["food"] == 0.0


def test_allocate_margin_weighted_split():
    """Two routes, higher-margin route gets more flow."""
    outbound_routes = [("A", "B"), ("A", "C")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {
        "B": {"food": 3.0, "raw_material": 1.0, "luxury": 1.0},  # margin 2.0
        "C": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0},  # margin 1.0
    }
    surplus = {"food": 100.0, "raw_material": 0.0, "luxury": 0.0}

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count=10,
    )
    # Log-dampened: ln(1+2) ≈ 1.099, ln(1+1) ≈ 0.693
    # B gets 1.099/(1.099+0.693) ≈ 0.613 of 10 = 6.13
    # C gets 0.693/(1.099+0.693) ≈ 0.387 of 10 = 3.87
    assert flow[("A", "B")]["food"] > flow[("A", "C")]["food"]
    total = flow[("A", "B")]["food"] + flow[("A", "C")]["food"]
    assert abs(total - 10.0) < 0.01  # total = merchant capacity


def test_allocate_bounded_by_surplus():
    """Flow cannot exceed exportable surplus."""
    outbound_routes = [("A", "B")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {"B": {"food": 10.0, "raw_material": 1.0, "luxury": 1.0}}
    surplus = {"food": 3.0, "raw_material": 0.0, "luxury": 0.0}

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count=100,
    )
    # 100 merchants but only 3.0 surplus → export capped at 3.0
    assert flow[("A", "B")]["food"] == 3.0


def test_allocate_zero_merchants():
    """Zero merchants → zero flow."""
    outbound_routes = [("A", "B")]
    origin_prices = {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}
    dest_prices = {"B": {"food": 10.0, "raw_material": 1.0, "luxury": 1.0}}
    surplus = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}

    flow = allocate_trade_flow(
        outbound_routes, origin_prices, dest_prices, surplus, merchant_count=0,
    )
    assert flow[("A", "B")]["food"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "allocate" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

def allocate_trade_flow(
    outbound_routes: list[tuple[str, str]],
    origin_prices: dict[str, float],
    dest_prices: dict[str, dict[str, float]],
    exportable_surplus: dict[str, float],
    merchant_count: int,
) -> dict[tuple[str, str], dict[str, float]]:
    """Two-level log-dampened margin-weighted pro-rata allocation.

    Level 1: allocate merchant capacity across categories by total margin.
    Level 2: allocate each category's budget across routes by per-route margin.

    Uses pre-trade prices for margin computation.
    Log-dampening (ln(1 + margin)) compresses extreme price ratios.

    Args:
        outbound_routes: list of (origin_region, dest_region) pairs
        origin_prices: pre-trade prices at origin, keyed by category
        dest_prices: pre-trade prices at each destination, keyed by dest then category
        exportable_surplus: max(production - demand, 0) per category at origin
        merchant_count: number of merchant agents in origin region

    Returns:
        dict mapping (origin, dest) → {category: flow_amount}
    """
    capacity = merchant_count * CARRY_PER_MERCHANT
    if capacity <= 0 or not outbound_routes:
        return {route: _empty_category_dict() for route in outbound_routes}

    # --- Level 1: cross-category allocation by total margin share ---
    cat_weights: dict[str, float] = {}
    # Per-category per-route raw margins (for Level 2)
    route_margins: dict[str, dict[tuple[str, str], float]] = {
        cat: {} for cat in CATEGORIES
    }

    for cat in CATEGORIES:
        total_w = 0.0
        for route in outbound_routes:
            _, dest = route
            d_prices = dest_prices.get(dest, {})
            raw_margin = max(d_prices.get(cat, 0.0) - origin_prices.get(cat, 0.0), 0.0)
            weight = math.log1p(raw_margin)  # ln(1 + margin)
            route_margins[cat][route] = weight
            total_w += weight
        cat_weights[cat] = total_w

    total_weight = sum(cat_weights.values())
    if total_weight <= 0:
        return {route: _empty_category_dict() for route in outbound_routes}

    # --- Allocate capacity to categories ---
    cat_budgets: dict[str, float] = {}
    for cat in CATEGORIES:
        cat_budgets[cat] = (cat_weights[cat] / total_weight) * capacity

    # --- Level 2: per-route within category ---
    flow: dict[tuple[str, str], dict[str, float]] = {
        route: _empty_category_dict() for route in outbound_routes
    }

    for cat in CATEGORIES:
        budget = cat_budgets[cat]
        surplus = exportable_surplus.get(cat, 0.0)
        if budget <= 0 or surplus <= 0:
            continue

        cat_total_w = cat_weights[cat]
        if cat_total_w <= 0:
            continue

        allocated = 0.0
        for route in outbound_routes:
            w = route_margins[cat][route]
            if w <= 0:
                continue
            amount = (w / cat_total_w) * budget
            flow[route][cat] = amount
            allocated += amount

        # Bound by exportable surplus
        if allocated > surplus:
            scale = surplus / allocated
            for route in outbound_routes:
                flow[route][cat] *= scale

    return flow
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 28 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add allocate_trade_flow with log-dampened margin weighting"
```

---

### Task 8: Signal derivation functions

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

- [ ] **Step 1: Write failing tests for signal derivation**

```python
# tests/test_economy.py — append
from chronicler.economy import (
    derive_farmer_income_modifier,
    derive_food_sufficiency,
    derive_merchant_margin,
    derive_merchant_trade_income,
    FARMER_INCOME_MODIFIER_FLOOR,
    FARMER_INCOME_MODIFIER_CAP,
)


def test_farmer_income_modifier_balanced():
    """Equal supply and demand → modifier = 1.0."""
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 50.0}, demand={"food": 50.0},
    )
    assert mod == 1.0


def test_farmer_income_modifier_surplus():
    """Supply > demand → modifier < 1.0."""
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 100.0}, demand={"food": 50.0},
    )
    assert mod == 0.5


def test_farmer_income_modifier_floor():
    """Extreme surplus → modifier clamped to floor."""
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 1000.0}, demand={"food": 1.0},
    )
    assert mod == FARMER_INCOME_MODIFIER_FLOOR


def test_farmer_income_modifier_cap():
    """Extreme deficit → modifier clamped to cap."""
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 1.0}, demand={"food": 100.0},
    )
    assert mod == FARMER_INCOME_MODIFIER_CAP


def test_food_sufficiency_adequate():
    """Food supply meets demand → sufficiency = 1.0."""
    suf = derive_food_sufficiency(food_supply=50.0, food_demand=50.0)
    assert suf == 1.0


def test_food_sufficiency_shortage():
    """Food supply < demand → sufficiency < 1.0."""
    suf = derive_food_sufficiency(food_supply=25.0, food_demand=50.0)
    assert suf == 0.5


def test_food_sufficiency_capped():
    """Food supply >> demand → sufficiency capped at 2.0."""
    suf = derive_food_sufficiency(food_supply=500.0, food_demand=50.0)
    assert suf == 2.0


def test_merchant_margin_no_routes():
    """No routes → margin = 0.0."""
    m = derive_merchant_margin(total_raw_margin=10.0, route_count=0)
    assert m == 0.0


def test_merchant_margin_bounded():
    """Margin is clamped to [0.0, 1.0]."""
    m = derive_merchant_margin(total_raw_margin=1000.0, route_count=1)
    assert m <= 1.0
    assert m >= 0.0


def test_merchant_trade_income_basic():
    """Per-merchant income = total_arbitrage / merchant_count."""
    inc = derive_merchant_trade_income(total_arbitrage=10.0, merchant_count=5)
    assert inc == 2.0


def test_merchant_trade_income_zero_merchants():
    """Zero merchants → income = 0.0."""
    inc = derive_merchant_trade_income(total_arbitrage=10.0, merchant_count=0)
    assert inc == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "derive_" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/chronicler/economy.py — append

def derive_farmer_income_modifier(
    resource_type: int,
    post_trade_supply: dict[str, float],
    demand: dict[str, float],
) -> float:
    """Derive farmer_income_modifier from post-trade price ratio.

    Uses the category matching the region's primary resource.
    Clamped to [FLOOR, CAP]. Absorbs M41's is_extractive() dispatch.
    """
    cat = map_resource_to_category(resource_type)
    s = max(post_trade_supply.get(cat, 0.0), _SUPPLY_FLOOR)
    d = demand.get(cat, 0.0)
    raw = d / s
    return max(FARMER_INCOME_MODIFIER_FLOOR, min(raw, FARMER_INCOME_MODIFIER_CAP))


def derive_food_sufficiency(food_supply: float, food_demand: float) -> float:
    """Derive food_sufficiency from post-trade food supply/demand ratio.

    Below 1.0 → satisfaction penalty for all agents in region.
    Clamped to [0.0, 2.0].
    """
    d = max(food_demand, _SUPPLY_FLOOR)
    return max(0.0, min(food_supply / d, 2.0))


def derive_merchant_margin(total_raw_margin: float, route_count: int) -> float:
    """Derive merchant_margin from average raw margin per route.

    Normalized to [0.0, 1.0] via MERCHANT_MARGIN_NORMALIZER.
    """
    if route_count <= 0:
        return 0.0
    avg = total_raw_margin / route_count
    return max(0.0, min(avg / MERCHANT_MARGIN_NORMALIZER, 1.0))


def derive_merchant_trade_income(
    total_arbitrage: float,
    merchant_count: int,
) -> float:
    """Derive per-merchant income from total arbitrage profit.

    Not clamped — bounded by MAX_WEALTH in Rust.
    """
    if merchant_count <= 0:
        return 0.0
    return total_arbitrage / merchant_count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: 40 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add signal derivation functions"
```

---

### Task 9: Conservation law test

**Files:**
- Modify: `tests/test_economy.py`

The meaningful conservation property is: **total exports == total imports per category across all regions** (goods aren't created or destroyed in transit). The per-region identity `production = consumption + exports + waste` is algebraically trivially true and verifies nothing. Test the cross-system property instead.

- [ ] **Step 1: Write conservation law test (uses compute_economy from Task 10)**

This test depends on `compute_economy` from Task 10. Write it now, but it will only pass after Task 10 is complete. Skip it during Task 9's test run.

```python
# tests/test_economy.py — append
import pytest

@pytest.mark.skip(reason="Requires compute_economy from Task 10")
def test_conservation_exports_equal_imports():
    """Total exports == total imports per category across all regions.

    Goods are not created or destroyed in transit. This is the meaningful
    conservation law — it verifies the trade flow allocation is consistent.
    """
    from chronicler.economy import compute_economy

    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()
    result = compute_economy(
        world, snapshot, region_map, agent_mode=True,
        active_trade_routes=[("Agraria", "Ironhold")],
    )

    for cat in CATEGORIES:
        total_exports = sum(rg.exports[cat] for rg in result.region_goods.values())
        total_imports = sum(rg.imports[cat] for rg in result.region_goods.values())
        assert abs(total_exports - total_imports) < 1e-9, (
            f"Conservation violated for {cat}: exports={total_exports} != imports={total_imports}"
        )
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_economy.py
git commit -m "test(m42): add conservation law verification (exports == imports)"
```

After Task 10 is complete, remove the `@pytest.mark.skip` decorator and run the test.

---

### Task 10: `compute_economy` entry point

**Files:**
- Modify: `src/chronicler/economy.py`
- Modify: `tests/test_economy.py`

This is the main orchestrator that wires together all the pieces from Tasks 3-8. It reads from the world state and snapshot, runs the Phase 2 sub-sequence (steps 2a-2h), and returns an `EconomyResult`.

- [ ] **Step 1: Write integration test for `compute_economy`**

This test requires mock world state and snapshot. Create a minimal test that exercises the full pipeline with two connected regions:

```python
# tests/test_economy.py — append
from unittest.mock import MagicMock
from chronicler.economy import compute_economy


def _make_test_world():
    """Build a minimal two-region, two-civ world for economy tests.

    Region "Plains" (civ 0): GRAIN, 50 farmers, 10 soldiers, 5 merchants, pop=70
    Region "Hills" (civ 1): ORE, 20 farmers, 30 soldiers, 10 merchants, pop=65
    Active trade route between civ 0 and civ 1.
    """
    world = MagicMock()
    world.turn = 10

    plains = MagicMock()
    plains.name = "Plains"
    plains.adjacency = ["Hills"]
    plains.resource_types = [0, 1, 3]  # GRAIN, TIMBER, FISH
    plains.resource_yields = [1.5, 0.5, 0.3]
    plains.resource_reserves = [100.0, 50.0, 30.0]

    hills = MagicMock()
    hills.name = "Hills"
    hills.adjacency = ["Plains"]
    hills.resource_types = [5, 1, 4]  # ORE, TIMBER, SALT
    hills.resource_yields = [0.8, 0.6, 0.4]
    hills.resource_reserves = [80.0, 60.0, 40.0]

    civ0 = MagicMock()
    civ0.regions = ["Plains"]
    civ0.name = "Agraria"

    civ1 = MagicMock()
    civ1.regions = ["Hills"]
    civ1.name = "Ironhold"

    world.civilizations = [civ0, civ1]
    world.regions = [plains, hills]

    region_map = {"Plains": plains, "Hills": hills}

    return world, region_map


def _make_test_snapshot():
    """Build a mock snapshot with occupation and wealth arrays.

    Region 0 (Plains, civ 0): 50 farmers, 10 soldiers, 5 merchants, 3 scholars, 2 priests
    Region 1 (Hills, civ 1): 20 farmers, 30 soldiers, 10 merchants, 3 scholars, 2 priests
    """
    snapshot = MagicMock()

    # Agent data arrays (70 + 65 = 135 agents)
    # Plains agents: indices 0-69, Hills agents: indices 70-134
    import numpy as np

    n = 135
    regions = np.zeros(n, dtype=np.uint16)
    regions[70:] = 1

    occupations = np.zeros(n, dtype=np.uint8)
    # Plains: 50 farmers (0-49), 10 soldiers (50-59), 5 merchants (60-64), 3 scholars (65-67), 2 priests (68-69)
    occupations[50:60] = 1  # soldiers
    occupations[60:65] = 2  # merchants
    occupations[65:68] = 3  # scholars
    occupations[68:70] = 4  # priests
    # Hills: 20 farmers (70-89), 30 soldiers (90-119), 10 merchants (120-129), 3 scholars (130-132), 2 priests (133-134)
    occupations[90:120] = 1
    occupations[120:130] = 2
    occupations[130:133] = 3
    occupations[133:135] = 4

    civ_affinity = np.zeros(n, dtype=np.uint16)
    civ_affinity[70:] = 1

    wealth = np.full(n, 5.0, dtype=np.float32)
    # Make some merchants wealthy (above LUXURY_DEMAND_THRESHOLD=10.0)
    wealth[60:65] = 15.0  # Plains merchants
    wealth[120:130] = 20.0  # Hills merchants

    def _make_col(arr):
        col = MagicMock()
        col.to_numpy.return_value = arr
        return col

    snapshot.column.side_effect = lambda name: _make_col({
        "region": regions,
        "occupation": occupations,
        "civ_affinity": civ_affinity,
        "wealth": wealth,
    }[name])

    return snapshot


def test_compute_economy_produces_result():
    """compute_economy returns an EconomyResult with all fields populated."""
    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()

    # Mock get_active_trade_routes to return the civ pair
    active_routes = [("Agraria", "Ironhold")]

    result = compute_economy(world, snapshot, region_map, agent_mode=True,
                             active_trade_routes=active_routes)

    # All regions should have goods data
    assert "Plains" in result.region_goods
    assert "Hills" in result.region_goods

    # Plains produces food (GRAIN), Hills produces raw_material (ORE)
    assert result.region_goods["Plains"].production["food"] > 0
    assert result.region_goods["Hills"].production["raw_material"] > 0

    # Signals should be populated
    assert "Plains" in result.farmer_income_modifiers
    assert "Hills" in result.farmer_income_modifiers
    assert "Plains" in result.food_sufficiency
    assert "Hills" in result.food_sufficiency

    # Modifier bounds
    for region in ["Plains", "Hills"]:
        mod = result.farmer_income_modifiers[region]
        assert FARMER_INCOME_MODIFIER_FLOOR <= mod <= FARMER_INCOME_MODIFIER_CAP
        suf = result.food_sufficiency[region]
        assert 0.0 <= suf <= 2.0
        mm = result.merchant_margins[region]
        assert 0.0 <= mm <= 1.0
        mti = result.merchant_trade_incomes[region]
        assert mti >= 0.0

    # Agent mode: treasury tax and tithe base populated
    assert 0 in result.treasury_tax
    assert 1 in result.treasury_tax
    assert 0 in result.priest_tithe_shares
    assert 1 in result.priest_tithe_shares


def test_compute_economy_agents_off():
    """In agents=off mode, treasury_tax and tithe_base are empty."""
    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()

    result = compute_economy(world, snapshot, region_map, agent_mode=False,
                             active_trade_routes=[])

    assert result.treasury_tax == {}
    assert result.tithe_base == {}
    assert result.priest_tithe_shares == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_economy.py -k "compute_economy" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write `compute_economy` implementation**

This is the largest single function. It orchestrates steps 2a-2h:

```python
# src/chronicler/economy.py — append
import numpy as np


def _extract_region_agent_counts_from_arrays(
    regions: np.ndarray,
    occupations: np.ndarray,
    wealth: np.ndarray,
    region_idx: int,
) -> dict:
    """Extract occupation counts and wealthy agent count for a region.

    Takes pre-extracted numpy arrays (extracted once, not per-region).
    """
    mask = regions == region_idx
    occ = occupations[mask]
    w = wealth[mask]

    return {
        "population": int(mask.sum()),
        "farmer_count": int((occ == 0).sum()),
        "soldier_count": int((occ == 1).sum()),
        "merchant_count": int((occ == 2).sum()),
        "scholar_count": int((occ == 3).sum()),
        "priest_count": int((occ == 4).sum()),
        "wealthy_count": int((w > LUXURY_DEMAND_THRESHOLD).sum()),
    }


def _extract_civ_merchant_wealth(
    civ_affinity: np.ndarray,
    occupations: np.ndarray,
    wealth: np.ndarray,
    civ_idx: int,
) -> float:
    """Sum of merchant wealth for a civ. Uses pre-extracted arrays."""
    mask = (civ_affinity == civ_idx) & (occupations == 2)
    return float(np.sum(wealth[mask]))


def _extract_civ_priest_count(
    civ_affinity: np.ndarray,
    occupations: np.ndarray,
    civ_idx: int,
) -> int:
    """Count of priests for a civ. Uses pre-extracted arrays."""
    mask = (civ_affinity == civ_idx) & (occupations == 4)
    return int(mask.sum())


def compute_economy(
    world,
    snapshot,
    region_map: dict,
    agent_mode: bool,
    active_trade_routes: list[tuple[str, str]] | None = None,
) -> EconomyResult:
    """Phase 2 goods sub-sequence: production → demand → prices → trade → signals.

    Implements the two-pass price model:
    - Pre-trade prices (from production alone) drive margin computation
    - Post-trade prices (from production + imports) produce final signals

    Args:
        world: WorldState with civilizations, regions
        snapshot: Arrow RecordBatch with agent data (region, occupation, wealth, civ_affinity)
        region_map: dict mapping region name → Region object
        agent_mode: True if agents are running (enables treasury tax, tithe base)
        active_trade_routes: civ-level trade route pairs; if None, calls get_active_trade_routes

    Returns:
        EconomyResult with all computed data
    """
    if active_trade_routes is None:
        from chronicler.resources import get_active_trade_routes
        active_trade_routes = get_active_trade_routes(world)

    result = EconomyResult()
    regions = world.regions
    civs = world.civilizations

    # Build civ name → (civ_idx, region_set) lookup
    civ_lookup: dict[str, tuple[int, set[str]]] = {}
    for civ_idx, civ in enumerate(civs):
        if len(civ.regions) > 0:
            civ_lookup[civ.name] = (civ_idx, set(civ.regions))

    # Build region name → region index lookup
    region_idx_map: dict[str, int] = {}
    for i, region in enumerate(regions):
        region_idx_map[region.name] = i

    # Extract snapshot arrays ONCE (not per-region — P-5 performance fix)
    snap_regions = snapshot.column("region").to_numpy()
    snap_occupations = snapshot.column("occupation").to_numpy()
    snap_wealth = snapshot.column("wealth").to_numpy()
    snap_civ_affinity = snapshot.column("civ_affinity").to_numpy()

    # --- Step 2a: Production per region ---
    region_production: dict[str, dict[str, float]] = {}
    region_demand: dict[str, dict[str, float]] = {}
    region_agent_data: dict[str, dict] = {}

    for region in regions:
        rname = region.name
        ridx = region_idx_map[rname]
        agent_data = _extract_region_agent_counts_from_arrays(
            snap_regions, snap_occupations, snap_wealth, ridx,
        )
        region_agent_data[rname] = agent_data

        # Production
        prod = _empty_category_dict()
        cat, amount = compute_production(
            region.resource_types[0],
            region.resource_yields[0],
            agent_data["farmer_count"],
        )
        prod[cat] = amount
        region_production[rname] = prod

        # --- Step 2b: Demand ---
        demand = compute_demand(
            agent_data["population"],
            agent_data["soldier_count"],
            agent_data["wealthy_count"],
        )
        region_demand[rname] = demand

    # --- Step 2c: Pre-trade prices ---
    pre_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        pre_trade_prices[rname] = compute_prices(
            region_production[rname],  # supply = production only
            region_demand[rname],
        )

    # --- Step 2d: Exportable surplus + trade flow ---
    exportable_surplus: dict[str, dict[str, float]] = {}
    for rname in region_production:
        exportable_surplus[rname] = {
            cat: max(region_production[rname][cat] - region_demand[rname][cat], 0.0)
            for cat in CATEGORIES
        }

    # Decompose civ-level routes to region-level boundary pairs, grouped by origin
    # Also cache boundary pair count per region for trade_route_count wiring
    origin_routes: dict[str, list[tuple[str, str]]] = {}
    boundary_pair_counts: dict[str, int] = {}

    for civ_a_name, civ_b_name in active_trade_routes:
        if civ_a_name not in civ_lookup or civ_b_name not in civ_lookup:
            continue
        _, a_regions = civ_lookup[civ_a_name]
        _, b_regions = civ_lookup[civ_b_name]
        pairs = decompose_trade_routes(a_regions, b_regions, region_map)
        for origin, dest in pairs:
            origin_routes.setdefault(origin, []).append((origin, dest))
            boundary_pair_counts[origin] = boundary_pair_counts.get(origin, 0) + 1
        # Reverse direction: B→A
        reverse_pairs = decompose_trade_routes(b_regions, a_regions, region_map)
        for origin, dest in reverse_pairs:
            origin_routes.setdefault(origin, []).append((origin, dest))
            boundary_pair_counts[origin] = boundary_pair_counts.get(origin, 0) + 1

    # Compute trade flow per origin region
    region_imports: dict[str, dict[str, float]] = {
        rname: _empty_category_dict() for rname in region_production
    }
    region_exports: dict[str, dict[str, float]] = {
        rname: _empty_category_dict() for rname in region_production
    }
    # Track per-route flow for arbitrage income computation
    all_route_flows: dict[str, dict[tuple[str, str], dict[str, float]]] = {}

    for origin_name, routes in origin_routes.items():
        if origin_name not in region_production:
            continue
        merchant_count = region_agent_data.get(origin_name, {}).get("merchant_count", 0)

        # Build dest prices lookup
        dest_prices: dict[str, dict[str, float]] = {}
        for _, dest in routes:
            if dest in pre_trade_prices:
                dest_prices[dest] = pre_trade_prices[dest]

        flow = allocate_trade_flow(
            routes,
            pre_trade_prices.get(origin_name, _empty_category_dict()),
            dest_prices,
            exportable_surplus.get(origin_name, _empty_category_dict()),
            merchant_count,
        )
        all_route_flows[origin_name] = flow

        # Accumulate exports and imports
        for route, cat_flows in flow.items():
            _, dest = route
            for cat in CATEGORIES:
                amount = cat_flows[cat]
                region_exports[origin_name][cat] += amount
                region_imports.setdefault(dest, _empty_category_dict())
                region_imports[dest][cat] += amount

    # --- Step 2g: Post-trade prices ---
    post_trade_prices: dict[str, dict[str, float]] = {}
    for rname in region_production:
        post_trade_supply = {
            cat: region_production[rname][cat] + region_imports[rname][cat]
            for cat in CATEGORIES
        }
        post_trade_prices[rname] = compute_prices(
            post_trade_supply,
            region_demand[rname],
        )

    # --- Step 2h: Signal derivation ---
    for region in regions:
        rname = region.name
        agent_data = region_agent_data.get(rname, {})
        post_prices = post_trade_prices.get(rname, _empty_category_dict())
        demand = region_demand.get(rname, _empty_category_dict())
        post_supply = {
            cat: region_production.get(rname, _empty_category_dict())[cat]
                 + region_imports.get(rname, _empty_category_dict())[cat]
            for cat in CATEGORIES
        }

        # farmer_income_modifier (post-trade supply)
        result.farmer_income_modifiers[rname] = derive_farmer_income_modifier(
            region.resource_types[0], post_supply, demand,
        )

        # food_sufficiency (post-trade food supply)
        result.food_sufficiency[rname] = derive_food_sufficiency(
            post_supply.get("food", 0.0), demand.get("food", 0.0),
        )

        # merchant_margin (post-trade raw margins)
        routes = origin_routes.get(rname, [])
        total_raw_margin = 0.0
        for route in routes:
            _, dest = route
            dest_post = post_trade_prices.get(dest, _empty_category_dict())
            origin_post = post_prices
            for cat in CATEGORIES:
                total_raw_margin += max(dest_post[cat] - origin_post[cat], 0.0)

        result.merchant_margins[rname] = derive_merchant_margin(
            total_raw_margin, len(routes),
        )

        # merchant_trade_income (route_flow × post-trade margin)
        # Note: route_flow from pre-trade allocation × post-trade margins = intentional
        total_arbitrage = 0.0
        route_flows = all_route_flows.get(rname, {})
        for route, cat_flows in route_flows.items():
            _, dest = route
            dest_post = post_trade_prices.get(dest, _empty_category_dict())
            for cat in CATEGORIES:
                margin = max(dest_post[cat] - post_prices[cat], 0.0)
                total_arbitrage += cat_flows[cat] * margin

        result.merchant_trade_incomes[rname] = derive_merchant_trade_income(
            total_arbitrage, agent_data.get("merchant_count", 0),
        )

        # RegionGoods
        rg = RegionGoods(
            production=region_production.get(rname, _empty_category_dict()),
            imports=region_imports.get(rname, _empty_category_dict()),
            exports=region_exports.get(rname, _empty_category_dict()),
            prices=dict(post_prices),
        )
        result.region_goods[rname] = rg

        # Trade route count (boundary pairs) for wiring to RegionState
        result.trade_route_counts[rname] = boundary_pair_counts.get(rname, 0)

    # --- M41 deferred integrations (agent mode only) ---
    if agent_mode:
        from chronicler.factions import TITHE_RATE

        for civ_name, (civ_idx, _) in civ_lookup.items():
            merchant_wealth = _extract_civ_merchant_wealth(
                snap_civ_affinity, snap_occupations, snap_wealth, civ_idx,
            )
            priest_count = _extract_civ_priest_count(
                snap_civ_affinity, snap_occupations, civ_idx,
            )

            # Treasury tax
            result.treasury_tax[civ_idx] = TAX_RATE * merchant_wealth

            # Tithe base (agent-derived merchant wealth)
            result.tithe_base[civ_idx] = merchant_wealth

            # Priest tithe share
            result.priest_tithe_shares[civ_idx] = (
                TITHE_RATE * merchant_wealth / max(priest_count, 1)
            )

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_economy.py -v`
Expected: All tests PASS (42 total)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/economy.py tests/test_economy.py
git commit -m "feat(m42): add compute_economy entry point with full Phase 2 pipeline"
```

---

## Chunk 2: Rust Changes

### Task 11: RegionState new fields + FFI parsing

**Files:**
- Modify: `chronicler-agents/src/region.rs` (~line 54)
- Modify: `chronicler-agents/src/ffi.rs`

- [ ] **Step 1: Add four new fields to `RegionState`**

In `chronicler-agents/src/region.rs`, after line 54 (after `schism_convert_to: u8`):

```rust
    // M42: Goods economy signals
    pub farmer_income_modifier: f32,
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
    pub merchant_trade_income: f32,
```

- [ ] **Step 2: Add defaults in `RegionState::default()` / constructor**

In the constructor/default (around line 57-61), add defaults:

```rust
    farmer_income_modifier: 1.0,  // neutral modifier
    food_sufficiency: 1.0,         // adequate food
    merchant_margin: 0.0,          // no trade margin
    merchant_trade_income: 0.0,    // no trade income
```

- [ ] **Step 3: Add Arrow column parsing in `ffi.rs`**

In `ffi.rs`, add optional column parsing alongside existing M38b columns. Follow the existing pattern:

```rust
// M42: Goods economy signals (optional, backward compatible)
let farmer_income_modifier_col = rb
    .column_by_name("farmer_income_modifier")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
let food_sufficiency_col = rb
    .column_by_name("food_sufficiency")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
let merchant_margin_col = rb
    .column_by_name("merchant_margin")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
let merchant_trade_income_col = rb
    .column_by_name("merchant_trade_income")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
```

In the `RegionState` **initial construction** loop, add:

```rust
    farmer_income_modifier: farmer_income_modifier_col.map_or(1.0, |arr| arr.value(i)),
    food_sufficiency: food_sufficiency_col.map_or(1.0, |arr| arr.value(i)),
    merchant_margin: merchant_margin_col.map_or(0.0, |arr| arr.value(i)),
    merchant_trade_income: merchant_trade_income_col.map_or(0.0, |arr| arr.value(i)),
```

**IMPORTANT:** Also add to the **update block** (the `else` branch at ~line 481-527 of `ffi.rs`). Every new RegionState field must be updated in BOTH the initial construction AND the subsequent-calls update loop. Missing the update loop means signals are only set on the first tick and never refreshed:

```rust
    // In the update loop:
    if let Some(arr) = farmer_income_modifier_col { state.farmer_income_modifier = arr.value(i); }
    if let Some(arr) = food_sufficiency_col { state.food_sufficiency = arr.value(i); }
    if let Some(arr) = merchant_margin_col { state.merchant_margin = arr.value(i); }
    if let Some(arr) = merchant_trade_income_col { state.merchant_trade_income = arr.value(i); }
```

- [ ] **Step 4: Build and run existing tests**

Run: `cd chronicler-agents && cargo test`
Expected: All existing tests PASS (new fields have backward-compatible defaults)

- [ ] **Step 5: Commit**

```bash
git add chronicler-agents/src/region.rs chronicler-agents/src/ffi.rs
git commit -m "feat(m42): add goods economy fields to RegionState with FFI parsing"
```

---

### Task 12: CivSignals `priest_tithe_share` + constant changes

**Files:**
- Modify: `chronicler-agents/src/signals.rs` (~line 34)
- Modify: `chronicler-agents/src/agent.rs` (~lines 147-166)

- [ ] **Step 1: Add `priest_tithe_share` to `CivSignals` struct**

In `signals.rs`, after line 34 (`conquered_this_turn: bool`):

```rust
    // M42: Priest tithe share
    pub priest_tithe_share: f32,
```

- [ ] **Step 2: Add parsing in `parse_civ_signals()`**

In the parsing function, add optional column:

```rust
let priest_tithe_share_col = batch.column_by_name("priest_tithe_share")
    .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
```

In the `CivSignals` construction:

```rust
    priest_tithe_share: priest_tithe_share_col.map_or(0.0, |arr| arr.value(i)),
```

- [ ] **Step 3: Update `agent.rs` constants**

Replace `FARMER_INCOME` + `MINER_INCOME` with `BASE_FARMER_INCOME`. Remove `MERCHANT_INCOME`, `MERCHANT_BASELINE`, `is_extractive()`:

```rust
// Lines 151-157 become:
pub const BASE_FARMER_INCOME: f32 = 0.30;  // [CALIBRATE] replaces FARMER_INCOME + MINER_INCOME
pub const SOLDIER_INCOME: f32 = 0.15;
pub const AT_WAR_BONUS: f32 = 1.0;
pub const CONQUEST_BONUS: f32 = 3.0;
// MERCHANT_INCOME and MERCHANT_BASELINE removed — merchant income now from FFI signal
pub const SCHOLAR_INCOME: f32 = 0.20;
pub const PRIEST_INCOME: f32 = 0.20;
pub const CLASS_TENSION_WEIGHT: f32 = 0.15;

// Remove is_extractive() function (lines 162-166)
```

- [ ] **Step 4: Build (will fail — tick.rs and satisfaction.rs still reference removed items)**

Run: `cd chronicler-agents && cargo build 2>&1 | head -20`
Expected: Compile errors in `tick.rs` and `satisfaction.rs` referencing `FARMER_INCOME`, `MINER_INCOME`, `MERCHANT_INCOME`, `MERCHANT_BASELINE`, `is_extractive`

This is expected — we fix these in the next tasks.

- [ ] **Step 5: Commit (WIP)**

```bash
git add chronicler-agents/src/signals.rs chronicler-agents/src/agent.rs
git commit -m "wip(m42): add priest_tithe_share signal, update agent constants"
```

---

### Task 13: Rust wealth tick changes

**Files:**
- Modify: `chronicler-agents/src/tick.rs` (~lines 361-389)

- [ ] **Step 1: Update farmer income formula**

Replace the farmer match arm (lines 362-370):

```rust
    0 => {
        // M42: market-derived modifier replaces is_extractive() dispatch
        let yield_val = region.resource_yields[0];
        crate::agent::BASE_FARMER_INCOME * region.farmer_income_modifier * yield_val
    }
```

- [ ] **Step 2: Update merchant income formula**

Replace the merchant match arm (lines 377-380):

```rust
    2 => {
        // M42: arbitrage-driven income from Python-side goods economy
        region.merchant_trade_income
    }
```

- [ ] **Step 3: Update priest income formula**

Replace the priest match arm (lines 385-388). Note: in `wealth_tick`, per-agent civ signals are accessed via `civ_sig` which is an `Option<&CivSignals>` resolved by `signals.civs.iter().find(|c| c.civ_id == civ)` at ~line 357. Follow the same pattern as `conquered_this_turn`:

```rust
    _ => {
        // M42: base income + per-priest tithe share from civ-level signals
        crate::agent::PRIEST_INCOME
            + civ_sig.map_or(0.0, |c| c.priest_tithe_share)
    }
```

- [ ] **Step 4: Build**

Run: `cd chronicler-agents && cargo build`
Expected: May still fail if satisfaction.rs references removed items — proceed to Task 14.

- [ ] **Step 5: Commit (WIP)**

```bash
git add chronicler-agents/src/tick.rs
git commit -m "wip(m42): update wealth tick for market-derived farmer/merchant/priest income"
```

---

### Task 14: Satisfaction formula changes

**Files:**
- Modify: `chronicler-agents/src/satisfaction.rs`

- [ ] **Step 1: Add new fields to `SatisfactionInputs`**

Add after existing fields (around line 148-149):

```rust
    // M42: Goods economy
    pub food_sufficiency: f32,
    pub merchant_margin: f32,
```

- [ ] **Step 2: Update `base_inputs()` test helper**

In the test helper function, add defaults:

```rust
    food_sufficiency: 1.0,
    merchant_margin: 0.0,
```

- [ ] **Step 3: Add food sufficiency penalty (outside 0.40 cap)**

In `compute_satisfaction_with_culture`, after the existing penalty computation, add the food penalty as a separate term outside the social penalty cap:

```rust
    // M42: Food sufficiency — material condition, outside social penalty cap
    let food_penalty = if inp.food_sufficiency < 1.0 {
        (1.0 - inp.food_sufficiency) * FOOD_SHORTAGE_WEIGHT
    } else {
        0.0
    };
```

Add constant at module level:

```rust
const FOOD_SHORTAGE_WEIGHT: f32 = 0.3;  // [CALIBRATE]
```

In `compute_satisfaction_with_culture` (line 200), the final expression is:
`(base_sat - total_non_eco_penalty + temple_bonus).clamp(0.0, 1.0)`

Change to subtract food_penalty **outside** the social penalty cap:
```rust
(base_sat - total_non_eco_penalty + temple_bonus - food_penalty).clamp(0.0, 1.0)
```

- [ ] **Step 4: Replace merchant satisfaction term**

The merchant base satisfaction is in `compute_satisfaction` (line 101), the lower-level function called by `compute_satisfaction_with_culture`. The `SatisfactionInputs` struct is used by `compute_satisfaction_with_culture` which wraps `compute_satisfaction`.

**IMPORTANT:** `compute_satisfaction()` (line 83) is NOT just the occupation base — it includes stability bonus, demand-supply ratio, overcrowding penalty, war penalty, and shock penalty (lines 106-121). Only the merchant trade term (line 101) should change, not the whole function output.

Modify `compute_satisfaction()` itself to accept `merchant_margin: f32` as a new parameter. Replace only the trade term at line 101:

```rust
// In compute_satisfaction() signature, add: merchant_margin: f32

// Line 101 changes from:
2 => 0.4 + (trade_routes as f32 / 3.0).min(1.0) * 0.3,
// To:
2 => 0.4 + merchant_margin * MERCHANT_MARGIN_WEIGHT,
```

All other terms (ecology, war, overcrowding, shock) remain untouched. Update the call in `compute_satisfaction_with_culture` (~line 154) to pass `inp.merchant_margin`.

Add constant:

```rust
const MERCHANT_MARGIN_WEIGHT: f32 = 0.3;  // [CALIBRATE]
```

- [ ] **Step 5: Update `SatisfactionInputs` construction in `tick.rs`**

Where `SatisfactionInputs` is constructed in `update_satisfaction` (tick.rs), add the new fields from `RegionState`:

```rust
    food_sufficiency: region.food_sufficiency,
    merchant_margin: region.merchant_margin,
```

- [ ] **Step 6: Update test call sites**

Update all test files that construct `SatisfactionInputs` to include the new fields:
- `chronicler-agents/src/satisfaction.rs` inline tests
- `chronicler-agents/tests/satisfaction_m38a.rs`

Add to `base_inputs()` and `m38a_base_inputs()` helpers:

```rust
    food_sufficiency: 1.0,
    merchant_margin: 0.0,
```

- [ ] **Step 7: Build and test**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add chronicler-agents/src/satisfaction.rs chronicler-agents/src/tick.rs chronicler-agents/tests/
git commit -m "feat(m42): add food_sufficiency penalty and merchant_margin satisfaction replacement"
```

---

### Task 15: Rust unit tests for new income formulas

**Files:**
- Modify: `chronicler-agents/src/tick.rs` (inline tests) or `chronicler-agents/tests/`

- [ ] **Step 1: Write test for farmer income with modifier**

```rust
#[test]
fn test_farmer_income_uses_modifier() {
    // Farmer income = BASE_FARMER_INCOME × modifier × yield
    // With modifier 2.0 and yield 1.5: 0.30 × 2.0 × 1.5 = 0.90
    let region = RegionState {
        farmer_income_modifier: 2.0,
        resource_yields: [1.5, 0.0, 0.0],
        ..RegionState::default()
    };
    // ... set up pool with one farmer, run wealth_tick, assert wealth increase ≈ 0.90
}
```

- [ ] **Step 2: Write test for merchant income from trade signal**

```rust
#[test]
fn test_merchant_income_from_trade_signal() {
    // Merchant income = merchant_trade_income (from FFI)
    let region = RegionState {
        merchant_trade_income: 5.0,
        ..RegionState::default()
    };
    // ... set up pool with one merchant, run wealth_tick, assert wealth increase ≈ 5.0
}
```

- [ ] **Step 3: Write test for priest income with tithe share**

```rust
#[test]
fn test_priest_income_with_tithe_share() {
    // Priest income = PRIEST_INCOME + priest_tithe_share
    // With tithe_share 0.5: 0.20 + 0.50 = 0.70
    let civ_signals = CivSignals {
        priest_tithe_share: 0.5,
        ..CivSignals::default()
    };
    // ... set up pool with one priest, run wealth_tick, assert wealth increase ≈ 0.70
}
```

- [ ] **Step 4: Write test for food sufficiency penalty**

```rust
#[test]
fn test_food_sufficiency_penalty() {
    let inputs = SatisfactionInputs {
        food_sufficiency: 0.5,  // 50% food → penalty = 0.5 × 0.3 = 0.15
        ..base_inputs()
    };
    let sat_with_shortage = compute_satisfaction_with_culture(&inputs);
    let inputs_ok = SatisfactionInputs {
        food_sufficiency: 1.0,  // adequate food → no penalty
        ..base_inputs()
    };
    let sat_without_shortage = compute_satisfaction_with_culture(&inputs_ok);
    assert!(sat_with_shortage < sat_without_shortage);
}
```

- [ ] **Step 5: Write test for merchant margin satisfaction**

```rust
#[test]
fn test_merchant_margin_satisfaction() {
    // Merchant with high margin should have higher satisfaction
    let high = SatisfactionInputs {
        occupation: 2,
        merchant_margin: 0.8,
        ..base_inputs()
    };
    let low = SatisfactionInputs {
        occupation: 2,
        merchant_margin: 0.2,
        ..base_inputs()
    };
    let sat_high = compute_satisfaction_with_culture(&high);
    let sat_low = compute_satisfaction_with_culture(&low);
    assert!(sat_high > sat_low);
}
```

- [ ] **Step 6: Run all tests**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add chronicler-agents/
git commit -m "test(m42): add Rust unit tests for new income formulas and satisfaction changes"
```

---

## Chunk 3: Python Integration

### Task 16: Wire RegionState signals in `agent_bridge.py`

**Files:**
- Modify: `src/chronicler/agent_bridge.py`

**IMPORTANT:** `build_region_batch` is a **module-level function** (line 104), NOT a method on `AgentBridge`. Its signature is `def build_region_batch(world: WorldState) -> pa.RecordBatch`. It cannot access `self`. The economy result must be passed as an optional parameter.

- [ ] **Step 1: Add `economy_result` parameter to `build_region_batch`**

Change the function signature at line 104:

```python
def build_region_batch(world: WorldState, economy_result=None) -> pa.RecordBatch:
```

- [ ] **Step 2: Add four new Arrow columns inside the function**

In the region iteration loop inside `build_region_batch`, add after existing M38b columns:

```python
# M42: Goods economy signals
farmer_income_modifiers = []
food_sufficiency_vals = []
merchant_margins = []
merchant_trade_incomes = []

for region in world.regions:
    rname = region.name
    if economy_result is not None:
        farmer_income_modifiers.append(
            economy_result.farmer_income_modifiers.get(rname, 1.0)
        )
        food_sufficiency_vals.append(
            economy_result.food_sufficiency.get(rname, 1.0)
        )
        merchant_margins.append(
            economy_result.merchant_margins.get(rname, 0.0)
        )
        merchant_trade_incomes.append(
            economy_result.merchant_trade_incomes.get(rname, 0.0)
        )
    else:
        farmer_income_modifiers.append(1.0)
        food_sufficiency_vals.append(1.0)
        merchant_margins.append(0.0)
        merchant_trade_incomes.append(0.0)
```

Add to the RecordBatch schema and arrays:

```python
pa.field("farmer_income_modifier", pa.float32()),
pa.field("food_sufficiency", pa.float32()),
pa.field("merchant_margin", pa.float32()),
pa.field("merchant_trade_income", pa.float32()),
```

- [ ] **Step 3: Update `trade_route_count` to use real boundary-pair counts**

In `build_region_batch`, replace the hardcoded `[0 for _ in world.regions]` for `trade_route_count` (line 195 of `agent_bridge.py`):

```python
# Change from: [0 for _ in world.regions]
# To:
[economy_result.trade_route_counts.get(r.name, 0) if economy_result else 0
 for r in world.regions]
```

- [ ] **Step 4: Update `AgentBridge.tick()` to pass economy_result**

In `AgentBridge.tick()` (line 361), the call `self._sim.set_region_state(build_region_batch(world))` must pass the economy result. Add storage on the bridge:

```python
# In AgentBridge.__init__:
self._economy_result = None

# Add setter method:
def set_economy_result(self, result):
    self._economy_result = result

# In AgentBridge.tick(), update the call:
self._sim.set_region_state(build_region_batch(world, self._economy_result))
```

- [ ] **Step 5: Run Python test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All existing tests PASS (economy_result defaults to None, backward compatible)

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m42): wire four RegionState economy signals and trade_route_count in agent bridge"
```

---

### Task 17: Wire `priest_tithe_share` on CivSignals

**Files:**
- Modify: `src/chronicler/agent_bridge.py`

**IMPORTANT:** `build_signals` is a **module-level function** (like `build_region_batch`), NOT a method on `AgentBridge`. Its signature is `def build_signals(world, shocks=None, demands=None, conquered=None, gini_by_civ=None)`. It has no `self`.

- [ ] **Step 1: Add `economy_result` parameter to `build_signals`**

Change the function signature:

```python
def build_signals(world, shocks=None, demands=None, conquered=None, gini_by_civ=None, economy_result=None):
```

Add new column inside the function:

```python
# M42: Priest tithe share
priest_tithe_shares = []
for civ_idx in range(len(world.civilizations)):
    if economy_result is not None:
        priest_tithe_shares.append(
            economy_result.priest_tithe_shares.get(civ_idx, 0.0)
        )
    else:
        priest_tithe_shares.append(0.0)
```

Add to schema:

```python
pa.field("priest_tithe_share", pa.float32()),
```

Update the call in `AgentBridge.tick()` to pass `self._economy_result` to `build_signals`.

- [ ] **Step 2: Verify `conquered_this_turn` still clears correctly**

Run existing M41 transient signal test to verify no regression:

Run: `python -m pytest tests/ -k "conquered" -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/agent_bridge.py
git commit -m "feat(m42): wire priest_tithe_share on CivSignals"
```

---

### Task 18: Call `compute_economy` from simulation.py Phase 2

**Files:**
- Modify: `src/chronicler/simulation.py` (~line 215 in `apply_automatic_effects`, and ~line 1176 in `run_turn`)

**IMPORTANT:** `apply_automatic_effects()` does not have access to the agent bridge, snapshot, or region_map. The economy computation must be orchestrated from `run_turn()` (the main turn function, ~line 1175), which has access to the bridge. The economy result is computed in Phase 2, then stored on the bridge for use during the agent tick (between Phase 9 and 10).

- [ ] **Step 1: Add compute_economy call in `run_turn` before Phase 2**

In `run_turn()`, after region_map is built but before `apply_automatic_effects` is called (~line 1203), add the economy computation. The previous turn's snapshot provides agent data (one-turn lag pattern):

```python
    # --- M42: Goods economy (Phase 2 sub-sequence) ---
    economy_result = None
    if agent_bridge is not None:
        snapshot = agent_bridge.get_snapshot()  # previous turn's snapshot
        if snapshot is not None:
            from chronicler.economy import compute_economy
            from chronicler.resources import get_active_trade_routes

            active_routes = get_active_trade_routes(world)
            economy_result = compute_economy(
                world, snapshot, region_map, agent_mode=True,
                active_trade_routes=active_routes,
            )
            # Store on bridge for use in agent tick's build_region_batch
            agent_bridge.set_economy_result(economy_result)

            # Apply treasury tax (M41 deferred integration, "keep" category)
            for civ_idx, tax in economy_result.treasury_tax.items():
                if civ_idx < len(world.civilizations):
                    civ = world.civilizations[civ_idx]
                    if acc is not None:
                        acc.add(civ_idx, civ, "treasury", int(tax), "keep")
                    else:
                        civ.treasury += int(tax)
```

**Notes on variable availability in `run_turn`:**
- `agent_bridge` is a local variable created earlier in the function
- `region_map` does NOT exist in `run_turn` — build it locally: `region_map = {r.name: r for r in world.regions}`
- `acc` (StatAccumulator) is a local variable in `run_turn`
- The snapshot method may be `agent_bridge._sim.get_snapshot()` — check the actual API

**Threading to `tick_factions` (P-7):** `tick_factions` is called from `phase_consequences()` (Phase 10), not directly from `run_turn`. The call chain is: `run_turn()` → `phase_consequences()` → `tick_factions()`. To thread `economy_result`, either: (a) pass it through both function signatures, or (b) store it on the bridge (already done above) and read it in `tick_factions` via the bridge. Option (b) is simpler — `tick_factions` can access `world._agent_bridge._economy_result` if the bridge is stored on world, or accept a parameter.

- [ ] **Step 2: Run simulation smoke test**

Run: `python -m pytest tests/ -k "simulation" -v --timeout=120`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/chronicler/simulation.py
git commit -m "feat(m42): integrate compute_economy into Phase 2 turn loop"
```

---

### Task 19: Update `compute_tithe_base` in factions.py

**Files:**
- Modify: `src/chronicler/factions.py` (~line 257)

- [ ] **Step 1: Update `compute_tithe_base` for agent mode**

Replace lines 257-259:

```python
def compute_tithe_base(civ, snapshot=None, economy_result=None, civ_idx=None):
    """Compute tithe base: agent-derived merchant wealth or trade_income fallback.

    M42: Uses sum of merchant wealth when economy_result is available (agent mode).
    Falls back to trade_income for --agents=off mode.

    Args:
        civ_idx: index into world.civilizations (Civilization has no id field)
    """
    if economy_result is not None and civ_idx is not None:
        if civ_idx in economy_result.tithe_base:
            return economy_result.tithe_base[civ_idx]
    return getattr(civ, 'trade_income', 0) or getattr(civ, 'last_income', 0)
```

- [ ] **Step 2: Update callers of `compute_tithe_base`**

In `tick_factions()` (line 370-372), pass economy_result and civ_idx. The caller iterates civs with an index — thread it through:

```python
    tithe = TITHE_RATE * compute_tithe_base(
        civ, snapshot=snapshot, economy_result=economy_result, civ_idx=civ_idx,
    )
```

The `economy_result` and `civ_idx` parameters need to be threaded from `run_turn` through `tick_factions`. Check the `tick_factions` signature and add the parameter.

- [ ] **Step 3: Run faction tests**

Run: `python -m pytest tests/ -k "faction" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/chronicler/factions.py
git commit -m "feat(m42): update compute_tithe_base for agent-derived merchant wealth"
```

---

### Task 20: Analytics — price time series extractor (DEFERRED)

**Status:** Deferred. `EconomyResult` and `RegionGoods` are transient — they are not persisted in the turn snapshot or bundle. No code currently writes price data to the snapshot format that analytics extractors read from. Writing the extractor now would require inventing a persistence format.

**Deferred to:** When the bundle format is updated to include economy data (potentially M43 or viewer work). Price data is computed and available on `EconomyResult` for debugging during development.

**When implementing:** Follow the existing `extract_stability()` pattern in `analytics.py`. Add a step in the turn snapshot assembly (Phase 10) to persist `{region_name: {category: price}}` from `EconomyResult.region_goods`, then write the extractor to read it.

---

### Task 21: Integration tests

**Files:**
- Create or modify: `tests/test_economy_integration.py`

- [ ] **Step 1: Write price responsiveness integration test**

```python
def test_price_responsiveness():
    """Surplus regions have lower prices than deficit regions for same category."""
    # Set up two food-producing regions:
    # Region A: 100 farmers, 20 pop (surplus)
    # Region B: 10 farmers, 100 pop (deficit)
    # Assert price_A < price_B for food
```

- [ ] **Step 2: Write bidirectional flow test**

```python
def test_bidirectional_flow():
    """Food flows A→B and raw material flows B→A on same route."""
    # Region A: GRAIN (food producer)
    # Region B: ORE (raw material producer)
    # Connected by trade route
    # Assert food exports from A, raw_material exports from B
```

- [ ] **Step 3: Write agents-off invariance test**

```python
def test_agents_off_invariance():
    """Phase 2 treasury unchanged in --agents=off mode."""
    # Run with agent_mode=False, verify treasury_tax is empty
    # Run existing aggregate path, verify identical results
```

- [ ] **Step 4: Write food sufficiency / famine independence test**

```python
def test_food_sufficiency_famine_independence():
    """Good ecology + no farmers → low food_sufficiency but no Phase 9 famine."""
    # Set up region with good ecology (soil, water), zero farmers
    # Assert food_sufficiency < 1.0
    # Assert no famine event from Phase 9
```

- [ ] **Step 5: Run all integration tests**

Run: `python -m pytest tests/test_economy_integration.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_economy_integration.py
git commit -m "test(m42): add integration tests for price responsiveness, bidirectional flow, invariance"
```

---

### Task 22: Full test suite + 200-seed regression baseline

- [ ] **Step 1: Run full Python test suite**

Run: `python -m pytest tests/ -v --timeout=300`
Expected: All tests PASS

- [ ] **Step 2: Run full Rust test suite**

Run: `cd chronicler-agents && cargo test`
Expected: All tests PASS

- [ ] **Step 3: Run 200-seed regression comparison**

Run: `python -m chronicler.regression --seeds=200 --mode=hybrid --compare=baseline`

Key metrics to verify:
- Satisfaction distribution: food sufficiency penalty doesn't crater satisfaction
- Wealth distribution: Gini stays in reasonable range
- Occupation distribution: no degenerate all-farmer or all-merchant
- Rebellion/loyalty: no regression
- Treasury levels: comparable to pre-M42

- [ ] **Step 4: Save regression baseline**

Run: `python -m chronicler.regression --seeds=200 --mode=hybrid --save-baseline=m42`

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(m42): validate full test suite and save 200-seed regression baseline"
```
