"""Unit tests for M42 goods production & trade economy module."""

from chronicler.economy import (
    map_resource_to_category,
    CATEGORIES,
    RegionGoods,
    EconomyResult,
    _empty_category_dict,
    compute_production,
    compute_demand,
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
