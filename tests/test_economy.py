"""Unit tests for M42 goods production & trade economy module."""

import math

from chronicler.economy import (
    map_resource_to_category,
    CATEGORIES,
    RegionGoods,
    EconomyResult,
    _empty_category_dict,
    compute_production,
    compute_demand,
    compute_prices,
    BASE_PRICE,
    decompose_trade_routes,
    allocate_trade_flow,
    derive_farmer_income_modifier,
    derive_food_sufficiency,
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
    r.adjacency = adjacency
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

def test_food_sufficiency_adequate():
    suf = derive_food_sufficiency(food_supply=50.0, food_demand=50.0)
    assert suf == 1.0

def test_food_sufficiency_shortage():
    suf = derive_food_sufficiency(food_supply=25.0, food_demand=50.0)
    assert suf == 0.5

def test_food_sufficiency_capped():
    suf = derive_food_sufficiency(food_supply=500.0, food_demand=50.0)
    assert suf == 2.0

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
