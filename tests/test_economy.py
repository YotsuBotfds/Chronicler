"""Unit tests for M42 goods production & trade economy module."""

import math
from unittest.mock import MagicMock

from chronicler.models import RegionStockpile
from chronicler.economy import (
    map_resource_to_category,
    map_resource_to_good,
    CATEGORIES,
    RegionGoods,
    EconomyResult,
    _empty_category_dict,
    compute_production,
    compute_demand,
    compute_prices,
    compute_economy,
    BASE_PRICE,
    decompose_trade_routes,
    allocate_trade_flow,
    derive_farmer_income_modifier,
    derive_merchant_margin,
    derive_merchant_trade_income,
    FARMER_INCOME_MODIFIER_FLOOR,
    FARMER_INCOME_MODIFIER_CAP,
)


# --- Task 1: Category mapping ---

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


def test_map_resource_lookup_ignores_empty_and_unknown_slots():
    assert map_resource_to_category(255) is None
    assert map_resource_to_category(999) is None
    assert map_resource_to_good(255) is None
    assert map_resource_to_good(999) is None


def test_categories_constant():
    """Three categories, ordered."""
    assert CATEGORIES == ("food", "raw_material", "luxury")


# --- Task 2: Data containers ---

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
    assert er.trade_route_counts == {}
    assert er.priest_tithe_shares == {}
    assert er.treasury_tax == {}
    assert er.tithe_base == {}


# --- Task 3: Production ---

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


def test_compute_production_empty_slot_is_safe():
    result = compute_production(resource_type=255, resource_yield=1.5, farmer_count=10)
    assert result == (None, 0.0)


# --- Task 4: Demand ---

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


def test_farmer_income_modifier_is_neutral_for_unknown_resource():
    modifier = derive_farmer_income_modifier(
        255,
        {"food": 10.0, "raw_material": 5.0, "luxury": 2.0},
        {"food": 10.0, "raw_material": 5.0, "luxury": 2.0},
        farmer_count=10,
    )
    assert modifier == 1.0


def test_compute_demand_zero_pop():
    """Zero population → zero food demand."""
    demand = compute_demand(population=0, soldier_count=0, wealthy_count=0)
    assert demand["food"] == 0.0
    assert demand["raw_material"] == 0.0
    assert demand["luxury"] == 0.0


# --- Task 5: Price computation ---

def test_compute_prices_balanced():
    supply = {"food": 50.0, "raw_material": 10.0, "luxury": 5.0}
    demand = {"food": 50.0, "raw_material": 10.0, "luxury": 5.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE
    assert prices["raw_material"] == BASE_PRICE
    assert prices["luxury"] == BASE_PRICE

def test_compute_prices_surplus():
    supply = {"food": 100.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 100.0)

def test_compute_prices_deficit():
    supply = {"food": 25.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 25.0)

def test_compute_prices_zero_supply():
    supply = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 50.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    assert prices["food"] == BASE_PRICE * (50.0 / 0.1)
    assert prices["raw_material"] == 0.0

def test_compute_prices_no_nan():
    supply = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    demand = {"food": 0.0, "raw_material": 0.0, "luxury": 0.0}
    prices = compute_prices(supply, demand)
    for cat in prices:
        assert not math.isnan(prices[cat])
        assert not math.isinf(prices[cat])


# --- Task 6: Trade route decomposition ---

def _make_mock_region(name, adjacency):
    class R:
        pass
    r = R()
    r.name = name
    r.adjacencies = adjacency
    return r

def test_decompose_single_boundary():
    region_map = {
        "A1": _make_mock_region("A1", ["B1", "A2"]),
        "B1": _make_mock_region("B1", ["A1"]),
        "A2": _make_mock_region("A2", ["A1"]),
    }
    pairs = decompose_trade_routes({"A1"}, {"B1"}, region_map)
    assert pairs == [("A1", "B1")]

def test_decompose_long_border():
    region_map = {
        "A1": _make_mock_region("A1", ["B1"]),
        "A2": _make_mock_region("A2", ["B2"]),
        "B1": _make_mock_region("B1", ["A1"]),
        "B2": _make_mock_region("B2", ["A2"]),
    }
    pairs = decompose_trade_routes({"A1", "A2"}, {"B1", "B2"}, region_map)
    assert sorted(pairs) == [("A1", "B1"), ("A2", "B2")]

def test_decompose_no_border():
    region_map = {
        "A1": _make_mock_region("A1", ["A2"]),
        "A2": _make_mock_region("A2", ["A1"]),
        "B1": _make_mock_region("B1", ["B2"]),
        "B2": _make_mock_region("B2", ["B1"]),
    }
    pairs = decompose_trade_routes({"A1", "A2"}, {"B1", "B2"}, region_map)
    assert pairs == []


# --- Task 7: Trade flow allocation ---

def test_allocate_single_route_single_category():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B")],
        origin_prices={"food": 0.5, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={"B": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0}},
        exportable_surplus={"food": 10.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=5,
    )
    assert flow[("A", "B")]["food"] == 5.0

def test_allocate_no_margin():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B")],
        origin_prices={"food": 1.0, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={"B": {"food": 1.0, "raw_material": 1.0, "luxury": 1.0}},
        exportable_surplus={"food": 10.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=5,
    )
    total = sum(flow[("A", "B")].values())
    assert total == 0.0

def test_allocate_negative_margin():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B")],
        origin_prices={"food": 2.0, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={"B": {"food": 0.5, "raw_material": 1.0, "luxury": 1.0}},
        exportable_surplus={"food": 10.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=5,
    )
    assert flow[("A", "B")]["food"] == 0.0

def test_allocate_margin_weighted_split():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B"), ("A", "C")],
        origin_prices={"food": 1.0, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={
            "B": {"food": 3.0, "raw_material": 1.0, "luxury": 1.0},
            "C": {"food": 2.0, "raw_material": 1.0, "luxury": 1.0},
        },
        exportable_surplus={"food": 100.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=10,
    )
    assert flow[("A", "B")]["food"] > flow[("A", "C")]["food"]
    total = flow[("A", "B")]["food"] + flow[("A", "C")]["food"]
    assert abs(total - 10.0) < 0.01

def test_allocate_bounded_by_surplus():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B")],
        origin_prices={"food": 1.0, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={"B": {"food": 10.0, "raw_material": 1.0, "luxury": 1.0}},
        exportable_surplus={"food": 3.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=100,
    )
    assert flow[("A", "B")]["food"] == 3.0

def test_allocate_zero_merchants():
    flow = allocate_trade_flow(
        outbound_routes=[("A", "B")],
        origin_prices={"food": 1.0, "raw_material": 1.0, "luxury": 1.0},
        dest_prices={"B": {"food": 10.0, "raw_material": 1.0, "luxury": 1.0}},
        exportable_surplus={"food": 50.0, "raw_material": 0.0, "luxury": 0.0},
        merchant_count=0,
    )
    assert flow[("A", "B")]["food"] == 0.0


# --- Task 8: Signal derivation ---

def test_farmer_income_modifier_balanced():
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 50.0}, demand={"food": 50.0},
    )
    assert mod == 1.0

def test_farmer_income_modifier_surplus():
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 100.0}, demand={"food": 50.0},
    )
    assert mod == FARMER_INCOME_MODIFIER_FLOOR  # 0.5 < floor

def test_farmer_income_modifier_floor():
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 1000.0}, demand={"food": 1.0},
    )
    assert mod == FARMER_INCOME_MODIFIER_FLOOR

def test_farmer_income_modifier_cap():
    mod = derive_farmer_income_modifier(
        resource_type=0, post_trade_supply={"food": 1.0}, demand={"food": 100.0},
    )
    assert mod == FARMER_INCOME_MODIFIER_CAP

def test_merchant_margin_no_routes():
    m = derive_merchant_margin(total_raw_margin=10.0, route_count=0)
    assert m == 0.0

def test_merchant_margin_bounded():
    m = derive_merchant_margin(total_raw_margin=1000.0, route_count=1)
    assert m <= 1.0
    assert m >= 0.0

def test_merchant_trade_income_basic():
    inc = derive_merchant_trade_income(total_arbitrage=10.0, merchant_count=5)
    assert inc == 2.0

def test_merchant_trade_income_zero_merchants():
    inc = derive_merchant_trade_income(total_arbitrage=10.0, merchant_count=0)
    assert inc == 0.0


# --- Task 10: compute_economy entry point ---

def _make_test_world():
    """Two-region, two-civ world.
    Plains (civ 0): GRAIN, 50 farmers, 10 soldiers, 5 merchants, pop=70
    Hills (civ 1): ORE, 20 farmers, 30 soldiers, 10 merchants, pop=65
    """
    world = MagicMock()
    world.turn = 10
    world.tuning_overrides = {}

    plains = MagicMock()
    plains.name = "Plains"
    plains.adjacencies = ["Hills"]
    plains.resource_types = [0, 1, 3]
    plains.resource_effective_yields = [1.5, 0.5, 0.3]
    plains.terrain = "plains"
    plains.population = 70
    plains.stockpile = RegionStockpile(goods={"grain": 10.0})

    hills = MagicMock()
    hills.name = "Hills"
    hills.adjacencies = ["Plains"]
    hills.resource_types = [5, 1, 4]
    hills.resource_effective_yields = [0.8, 0.6, 0.4]
    hills.terrain = "mountains"
    hills.population = 65
    hills.stockpile = RegionStockpile(goods={"ore": 5.0})

    civ0 = MagicMock()
    civ0.regions = ["Plains"]
    civ0.name = "Agraria"

    civ1 = MagicMock()
    civ1.regions = ["Hills"]
    civ1.name = "Ironhold"

    world.civilizations = [civ0, civ1]
    world.regions = [plains, hills]
    world.rivers = []

    region_map = {"Plains": plains, "Hills": hills}
    return world, region_map


def _make_test_snapshot():
    """Mock snapshot with numpy arrays behind .column().to_numpy()."""
    import numpy as np

    snapshot = MagicMock()
    n = 135
    regions = np.zeros(n, dtype=np.uint16)
    regions[70:] = 1

    occupations = np.zeros(n, dtype=np.uint8)
    occupations[50:60] = 1   # Plains soldiers
    occupations[60:65] = 2   # Plains merchants
    occupations[65:68] = 3   # Plains scholars
    occupations[68:70] = 4   # Plains priests
    occupations[90:120] = 1  # Hills soldiers
    occupations[120:130] = 2 # Hills merchants
    occupations[130:133] = 3 # Hills scholars
    occupations[133:135] = 4 # Hills priests

    civ_affinity = np.zeros(n, dtype=np.uint16)
    civ_affinity[70:] = 1

    wealth = np.full(n, 5.0, dtype=np.float32)
    wealth[60:65] = 15.0   # Plains merchants wealthy
    wealth[120:130] = 20.0 # Hills merchants wealthy

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
    """compute_economy returns EconomyResult with all fields populated."""
    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()
    result = compute_economy(world, snapshot, region_map, agent_mode=True,
                             active_trade_routes=[("Agraria", "Ironhold")])

    assert "Plains" in result.region_goods
    assert "Hills" in result.region_goods

    # Plains produces food (GRAIN), Hills produces raw_material (ORE)
    assert result.region_goods["Plains"].production["food"] > 0
    assert result.region_goods["Hills"].production["raw_material"] > 0

    for region in ["Plains", "Hills"]:
        mod = result.farmer_income_modifiers[region]
        assert FARMER_INCOME_MODIFIER_FLOOR <= mod <= FARMER_INCOME_MODIFIER_CAP
        suf = result.food_sufficiency[region]
        assert 0.0 <= suf <= 2.0
        mm = result.merchant_margins[region]
        assert 0.0 <= mm <= 1.0
        mti = result.merchant_trade_incomes[region]
        assert mti >= 0.0

    assert 0 in result.treasury_tax
    assert 1 in result.treasury_tax
    assert 0 in result.priest_tithe_shares
    assert 1 in result.priest_tithe_shares


def test_compute_economy_agents_off():
    """In agents=off mode, treasury_tax and tithe_base are empty, but signals populated."""
    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()
    result = compute_economy(world, snapshot, region_map, agent_mode=False,
                             active_trade_routes=[])

    assert result.treasury_tax == {}
    assert result.tithe_base == {}
    assert result.priest_tithe_shares == {}
    # Signals should still be populated
    assert "Plains" in result.farmer_income_modifiers
    assert "Hills" in result.food_sufficiency


def test_conservation_exports_equal_imports():
    """Total exports == total imports per category (conservation law)."""
    world, region_map = _make_test_world()
    snapshot = _make_test_snapshot()
    result = compute_economy(world, snapshot, region_map, agent_mode=True,
                             active_trade_routes=[("Agraria", "Ironhold")])

    for cat in CATEGORIES:
        total_exports = sum(rg.exports[cat] for rg in result.region_goods.values())
        total_imports = sum(rg.imports[cat] for rg in result.region_goods.values())
        assert abs(total_exports - total_imports) < 1e-9, (
            f"Conservation violated for {cat}: exports={total_exports} != imports={total_imports}"
        )
